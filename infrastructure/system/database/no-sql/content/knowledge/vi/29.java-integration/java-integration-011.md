# Giới hạn đồng thời, điều tiết tải và quản lý tài nguyên kết nối

Một ứng dụng Java sử dụng NoSQL thường chạy ổn ở môi trường phát triển nhưng bắt đầu gặp lỗi khi có nhiều người dùng đồng thời: **connection pool hết chỗ, hàng đợi request tăng, timeout lan rộng, retry khiến hệ càng quá tải, CPU ứng dụng không cao nhưng p99 vẫn rất lớn**. Trong nhiều trường hợp, vấn đề không phải “database quá chậm” theo nghĩa đơn giản, mà là ứng dụng **cho phép quá nhiều công việc cùng tranh một tài nguyên hữu hạn**, hoặc quản lý tài nguyên kết nối không đúng vòng đời.

Chẳng hạn, API đọc đơn hàng có 20 instance Java. Mỗi instance tự tạo pool 100 kết nối, nhưng cụm database chỉ có ngân sách kết nối hữu dụng 800. Khi autoscaling và các job nền đồng thời chạy, hệ có thể phải gánh hàng nghìn connections, hàng đợi lấy connection, số lượng truy vấn đang thực thi và retries vượt năng lực xử lý thực tế. **Tăng connection pool hoặc tăng số threads không mặc nhiên tăng throughput**; đôi khi chúng chỉ biến một nút thắt thành một cơn bão request.

Trong chương **Kết nối Java** của module **Database No SQL**, bài này hướng dẫn cách phối hợp ba lớp điều khiển:

1. **Giới hạn đồng thời (concurrency limit):** Có tối đa bao nhiêu thao tác đang thực hiện hoặc đang chờ được nhận?
2. **Điều tiết tải (rate limiting, backpressure, load shedding):** Có cho phép tốc độ yêu cầu mới tiếp tục tăng khi hệ đã sát ngưỡng không?
3. **Quản lý tài nguyên kết nối (connection/session/client lifecycle):** Kết nối, threads, buffers, event loops, cursors và transactions được tạo, tái sử dụng, đóng và quan sát như thế nào?

Các ví dụ tập trung vào Java, các kiểu NoSQL như MongoDB, Cassandra/ScyllaDB, Redis và DynamoDB, đồng thời phân biệt **ngữ nghĩa của connection pool theo driver**. Các giá trị cấu hình trong bài là **con số minh họa**, phải được đo đạc và điều chỉnh theo sản phẩm, phiên bản, topology, consistency, workload và SLO thực tế.

> **Nguyên tắc cốt lõi:** Bảo vệ database bằng **ngân sách công việc có giới hạn và backpressure rõ ràng**, không dùng một queue vô hạn để che giấu quá tải. Đồng thời, tạo client/session/pool đúng vòng đời, đóng tài nguyên theo contract của driver và không retry mù những yêu cầu có thể đã commit.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **connection count**, **in-flight operations**, **concurrent requests**, **threads**, **pending acquires**, **QPS** và **queue depth**.
2. Giải thích vì sao **concurrency limit khác rate limit**; khi nào dùng semaphore, token bucket, queue hữu hạn, bulkhead hoặc load shedding.
3. Ước lượng concurrency bằng **Little’s Law** trong điều kiện ổn định, không nhầm giá trị trung bình với p95/p99.
4. Xác định **ngân sách kết nối toàn cụm** khi có nhiều pods, replica groups, drivers, background jobs và autoscaling.
5. Viết Java code **cấp permit/circuit breaker/timeout với try-finally** và tránh leak permit hoặc tài nguyên.
6. Dùng **bounded ThreadPoolExecutor** hoặc asynchronous APIs mà không vô tình tạo queue công việc không giới hạn.
7. Hiểu quan hệ giữa **pool wait timeout**, **connect timeout**, **read/socket timeout**, **operation deadline** và **server-side timeout**.
8. Xử lý **retry, exponential backoff, jitter, idempotency, unknown write outcome** khi database quá tải.
9. Quản lý vòng đời **MongoClient, CqlSession, Redis connections, async HTTP clients, cursor/result publisher** theo driver.
10. Thiết kế **metrics, alerting, load test và fault injection** để tìm bottleneck và bảo vệ SLO.

## 2. Tình huống xuyên suốt: Order API bị nghẽn dù CPU còn rảnh

Giả sử Order API chạy 12 pods Java, đọc đơn từ một cụm NoSQL:

~~~text
Load balancer
    |
    +-- Order API pod #1  -> Driver/pool -> NoSQL
    +-- Order API pod #2  -> Driver/pool -> NoSQL
    ...
    +-- Order API pod #12 -> Driver/pool -> NoSQL

Daily traffic: thấp
Peak traffic: 4.000 requests/s
Average DB operation time at normal load: 25 ms
Observed at peak:
  p95 API latency: 900 ms
  DB connection acquisition wait: 400 ms
  retries per logical request: 1.4
~~~

Các con số chỉ là một case minh họa. Người vận hành có thể thấy:

- API CPU 40%, chưa có dấu hiệu CPU saturation rõ.
- DB CPU tăng và số operation đang thực thi vượt mức thông thường.
- Thread dumps có nhiều threads chờ connection/permit.
- Pool queue tăng, một phần requests timeout khi **chưa kịp gửi lệnh**.
- Retry từ API gateway và SDK làm tải đến DB tăng thêm.

Điều cần làm không nhất thiết là tăng pool từ 50 lên 200. Phải trả lời: **Có bao nhiêu logical requests/s? Mỗi request tạo bao nhiêu DB calls? Thời gian mỗi call là bao lâu? Có bao nhiêu kết nối thật đang được giữ? Phần thời gian nào nằm ở queue/pool/backend?**

### 2.1. Sơ đồ ba tầng tài nguyên

~~~mermaid
flowchart LR
    A["Incoming requests"] --> B["Admission / rate limit"]
    B --> C["In-flight bulkhead"]
    C --> D["Bounded work queue / executor"]
    D --> E["Driver / connection pool"]
    E --> F["NoSQL coordinator / replicas"]
    F --> G["Disk, CPU, IO, network, partitions"]
    B --> H["Reject / Retry-After"]
    C --> H
    D --> H
~~~

Một request có thể bị nghẽn **trước** connection pool, **khi acquire** connection, **trên coordinator**, hoặc **tại shard nóng**. Không phải mọi hàng đợi đều nằm trong pool; có thể tồn tại đồng thời ở HTTP server, executor, reactive scheduler, SDK và DB.

### 2.2. Một connection không luôn bằng một operation

Tùy driver và protocol:

- Một connection kiểu tuần tự có thể chỉ phục vụ một request tại một thời điểm.
- Một connection có thể **multiplex nhiều in-flight operations** (ví dụ một số driver/protocol async, HTTP/2).
- Một NoSQL client có thể tạo **pool cho từng server/endpoint**, không chỉ một pool cho toàn cluster.
- Một DB query có thể fan-out tới nhiều shards/replicas.
- Một logical HTTP request có thể tạo nhiều DB operations, kể cả retry.

Vì vậy không nên dùng quy tắc tuyệt đối §maxConcurrentQueries == maxConnections§. Cần đọc **driver pool semantics và giới hạn in-flight per connection/node** của phiên bản thực tế.

## 3. Các đại lượng cần đo trước khi chỉnh cấu hình

| Đại lượng | Ý nghĩa | Điều không nên nhầm |
| --- | --- | --- |
| §logicalRequestsPerSecond§ | Số ý định/request mới mỗi giây | Không bằng DB attempts/s |
| §dbOperationsPerRequest§ | Fan-out, read-modify-write, secondary queries | Có thể thay theo endpoint |
| §dbAttemptsPerSecond§ | Tổng số lần gửi tới DB, kể cả retries | Có thể lớn hơn logical QPS |
| §inFlightRequests§ | HTTP/worker requests đang được xử lý | Không đồng nghĩa số connection |
| §inFlightDbOperations§ | DB operations chưa hoàn tất | Có thể nhiều hơn số connections |
| §activeConnections§ | Kết nối đang được dùng trong pool theo driver | Một connection có thể multiplex |
| §idleConnections§ | Kết nối pool giữ sẵn chưa dùng | Vẫn tiêu hao tài nguyên |
| §pendingConnectionAcquires§ | Số tác vụ chờ lấy connection | Nếu tăng, pool/DB đang bị ép |
| §queueDepth§ | Công việc đang đợi ở một tầng | Có thể có nhiều queue |
| §queueWaitTime§ | Đợi trước khi bắt đầu xử lý | Khác DB execution time |
| §connectionAcquisitionTime§ | Thời gian acquire từ pool | Có thể dài dù DB query nhanh |
| §dbOperationDuration§ | Thời gian từ gửi/đợi result theo API driver | Cần phân tách network/server |
| §p50/p95/p99 latency§ | Phân phối độ trễ | Không suy từ average |
| §throttle/rejection rate§ | Requests bị từ chối có chủ đích | Có thể là dấu hiệu hệ tự bảo vệ |
| §retry amplification§ | Attempts trên mỗi logical operation | Tải tăng ẩn dưới retries |

### 3.1. Gọi §QPS§ nhưng tính đơn vị nào?

Một endpoint §GET /orders/{id}§ có thể gửi một lookup. Endpoint §GET /orders/dashboard§ có thể phát **12 queries**. Nếu 1.000 HTTP requests/s với trung bình 3 DB operations:

\[
\text{DB logical operations/s}\approx1000\times3=3000
\]

Nếu trung bình có 1,2 attempts cho mỗi DB operation:

\[
\text{DB RPC attempts/s}\approx3000\times1{,}2=3600
\]

Không sizing connection pool từ **HTTP QPS** nếu chưa tính fan-out và retry.

### 3.2. Phân biệt saturated resource và symptom

Pool acquisition wait tăng có thể do pool quá nhỏ, nhưng cũng có thể vì **operations bị giữ connection quá lâu** khi DB chậm, cursors không đóng, transactions kéo dài, network lỗi hoặc một thread không trả connection về pool.

Tăng §maxPoolSize§ chỉ giải quyết đúng một phần giả thuyết; khi DB đã quá tải, nhiều connections có thể làm queue ở database lớn hơn.

## 4. Little’s Law: quan hệ giữa lưu lượng, thời gian và concurrency

Trong một hệ ổn định theo mô hình trung bình:

\[
L=\lambda W
\]

Trong đó:

- \(L\): **trung bình số công việc đang ở trong hệ**.
- \(\lambda\): **trung bình throughput hoàn thành** (operations/s) trong cùng phạm vi.
- \(W\): **trung bình thời gian mỗi operation ở trong phạm vi đó** (giây).

Ví dụ DB thực hiện 2.000 operations/s, mỗi operation ở trạng thái in-flight trung bình 40 ms:

\[
L=2000\times0{,}040=80
\]

Nghĩa là **trung bình có khoảng 80 DB operations in-flight** trong phạm vi đo.

### 4.1. Chọn đúng ranh giới

Nếu muốn tính concurrency **đang giữ connection**, dùng thời gian giữ tài nguyên tương ứng và tốc độ operation đi qua pool.

Nếu muốn tính concurrency **từ HTTP request nhận vào đến response**, dùng thời gian HTTP request end-to-end và HTTP throughput.

Nếu thời gian \(W\) đã bao gồm **queue wait**, \(L\) tính cả công việc **đang chờ**, không chỉ đang chạy trên DB.

### 4.2. Không thay average bằng p99 trực tiếp

Không nên viết:

~~~text
L = QPS * p99 latency
~~~

rồi gọi đó là Little’s Law chính xác. Công thức cơ bản dùng **trung bình**, còn p95/p99 liên quan sizing headroom và tail-risk theo mô hình/tải. Dùng percentile làm số heuristic có thể có ích nhưng phải **ghi rõ đây là dự phòng hoặc giả định riêng**, không phải định luật.

### 4.3. Kết quả không nói cần đúng 80 connections

Nếu driver multiplex nhiều requests một connection, số connections cần có thể nhỏ hơn số in-flight. Nếu mỗi operation giữ connection suốt truy vấn và một connection chỉ thực thi một operation, hai đại lượng có thể gần nhau. Phải xác minh driver behavior.

### 4.4. Khi hệ không ổn định

Nếu arrival rate liên tục vượt service capacity, queue cứ tăng và không có trạng thái ổn định. Số liệu tại thời điểm đó không còn đủ để dự báo bằng Little’s Law đơn giản; **load shedding hoặc rate control** là cần thiết thay vì chỉ tăng queue.

## 5. Concurrency limit khác rate limit

Hai rào chắn thường bị nhầm:

### 5.1. Concurrency limit

Ví dụ:

~~~text
At most 60 requests can execute this expensive DB operation
at the same time within one API pod.
~~~

Đây là giới hạn **số công việc đang active đồng thời**. Java §Semaphore§ hoặc bulkhead có thể làm việc này.

### 5.2. Rate limit

Ví dụ:

~~~text
At most 1.000 new operations per second are admitted
for this tenant or endpoint, with bounded burst capacity.
~~~

Đây là giới hạn **tốc độ nhận công việc mới theo thời gian**. Token bucket/leaky bucket là mô hình thường gặp.

### 5.3. Vì sao một rào chắn không thay rào chắn kia?

Nếu mỗi operation kéo dài 1 ms, limit 50 concurrent operations về lý thuyết có thể cho rất nhiều operations/s. Nó **không** giới hạn request rate.

Nếu rate limit 1.000/s nhưng DB operation đột ngột kéo dài 10 giây do phân vùng mạng, số in-flight có thể tăng rất lớn. Rate limit **không** tự chặn concurrency.

### 5.4. Ví dụ phối hợp

~~~text
Tenant rate budget:
  500 operations/s with burst tokens 100

Per-instance DB bulkhead:
  40 in-flight operations

Bounded waiting:
  at most 20 pending tasks

If overloaded:
  reject with defined retry policy
~~~

Giới hạn thực tế nên gắn với throughput/cost và SLO của từng tài nguyên, không tùy ý copy cấu hình giữa các service.

## 6. Admission control và load shedding

**Admission control** quyết định có tiếp nhận công việc hay không **trước khi nó chiếm tài nguyên đắt tiền**.

~~~mermaid
flowchart TD
    A["Incoming operation"] --> B{"Global / tenant rate budget?"}
    B -->|No| X["429 or policy-specific rejection"]
    B -->|Yes| C{"Bulkhead permit available?"}
    C -->|No| Y["Fast-fail / bounded queue"]
    C -->|Yes| D["Driver operation within deadline"]
    D --> E["Success / known failure / unknown outcome"]
    E --> F["Release resources"]
~~~

### 6.1. Từ chối sớm đôi khi tốt hơn chờ timeout

Giả sử endpoint có deadline 300 ms. Nếu queue đã dài 2 giây, giữ request trong queue để rồi trả timeout chỉ tiêu hao memory, thread, socket và làm client chờ vô ích. Trả một lỗi **được định nghĩa rõ** sớm hơn có thể bảo vệ hệ và giúp client giảm tải.

### 6.2. HTTP 429 hay 503?

- **429 Too Many Requests:** Thường dùng khi vượt rate/quota theo caller/tenant hoặc giới hạn áp dụng rõ.
- **503 Service Unavailable:** Có thể phù hợp khi service tạm thiếu capacity, circuit open hoặc dependency quá tải.

Chọn theo API contract. Nếu gửi §Retry-After§, client vẫn cần **jitter, deadline và retry budget**; nhiều clients cùng retry đúng một thời điểm có thể tạo “retry storm”.

### 6.3. Chờ có giới hạn

Không phải lúc nào cũng fast-fail. Một hàng đợi ngắn có thể hấp thụ burst và tăng utilization. Nhưng phải có:

- **Max queue depth**.
- **Max queue wait**.
- Deadline xuyên suốt.
- Policy hủy request khi client đã bỏ đi.
- Quan sát số rejected/expired.

### 6.4. Hàng đợi vô hạn là rủi ro

Một §LinkedBlockingQueue§ không truyền capacity có thể giữ gần như vô hạn tasks theo memory; ở tải cao backlog tăng cho đến OOM hoặc timeout hàng loạt. Không dựa vào “thread pool giới hạn 16 threads” nếu nó đứng trước **queue không giới hạn**.

### 6.5. Shed công việc nào?

Một hệ có thể ưu tiên:

- Thanh toán/checkout hơn analytics làm giàu dữ liệu.
- Read critical hơn background reindex.
- Interactive requests hơn bulk exports.
- Các tenants theo quota riêng.

Nhưng policy phải rõ và có fairness. Không để một tenant nóng chiếm toàn bộ in-flight permits làm người dùng khác mất SLO.

## 7. Java: bulkhead bằng Semaphore với fast-fail

§Semaphore§ giới hạn số operation code đang đi vào một khu vực. Ví dụ sau không xếp hàng chờ permit; nếu đã đầy thì từ chối ngay.

~~~java
import java.util.Objects;
import java.util.concurrent.Semaphore;

public final class BoundedOrderReader {
    private final OrderRepository repository;
    private final Semaphore permits;

    public BoundedOrderReader(OrderRepository repository, int maxInFlight) {
        this.repository = Objects.requireNonNull(repository);
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.permits = new Semaphore(maxInFlight, true);
    }

    public Order read(String orderId) {
        if (!permits.tryAcquire()) {
            throw new OverloadedException("ORDER_DB_BULKHEAD_FULL");
        }

        try {
            return repository.findById(orderId);
        } finally {
            permits.release();
        }
    }
}
~~~

§OrderRepository§, §Order§ và §OverloadedException§ là các kiểu domain giả định. Việc xử lý §OverloadedException§ tại HTTP boundary cần ánh xạ sang response đúng API, ví dụ 503 hoặc 429 theo chính sách.

### 7.1. Vì sao phải có finally?

Nếu §repository.findById§ ném exception hoặc timeout, không có §finally§ sẽ làm mất permit:

~~~text
maxInFlight = 40
40 operations throw an exception without release
availablePermits = 0 forever
~~~

Một bulkhead có leak permit sẽ tự biến thành outage dù DB đã phục hồi.

### 7.2. Vì sao dùng fair semaphore?

§new Semaphore(n,true)§ cung cấp fairness theo quy tắc tài liệu Java khi có waiters; nhưng §tryAcquire()§ không thời hạn có thể không tuân fairness theo cách bạn mong đợi trong mọi đường API. Trong ví dụ fast-fail không có hàng chờ. Nếu cần fairness/priority thực sự, cần thiết kế ở lớp admission/queue.

### 7.3. Permit thuộc phạm vi nào?

Đây là giới hạn **trong một JVM instance**. Với 12 pods, mỗi pod 40 permits, toàn bộ cluster API có thể có tối đa 480 operations cùng đi vào bulkhead này:

\[
12\times40=480
\]

Chưa tính background jobs, pods đang rollout hoặc service khác dùng DB. **Semaphore local không phải distributed global concurrency limiter.**

### 7.4. Một phép gọi có nhiều DB operations

Nếu §read()§ bên trong chạy ba queries liên tiếp, semaphore bảo vệ **một request logic** chứ không tự giới hạn số RPC riêng ở một thời điểm khi queries song song bên trong. Tính giới hạn theo **critical resource thực sự**, không chỉ tên method.

### 7.5. Có nên dùng một semaphore cho cả read và write?

Không luôn. Read ngắn có thể bị write batch lâu chiếm hết permits. Dùng **bulkhead theo operation class** (read-critical, write-critical, batch, analytics) khi cần, kết hợp một giới hạn tổng để tránh cộng các bulkheads vượt khả năng DB.

## 8. Java: permit chờ có deadline và xử lý interruption

Một số endpoint có thể chờ rất ngắn để hấp thụ burst:

~~~java
import java.time.Duration;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class BoundedWriter {
    private final Semaphore permits = new Semaphore(32);
    private final OrderRepository repository;

    public BoundedWriter(OrderRepository repository) {
        this.repository = repository;
    }

    public WriteResult update(String orderId, Duration waitBudget)
            throws InterruptedException {
        long nanos = Math.max(0L, waitBudget.toNanos());

        boolean acquired = permits.tryAcquire(
            nanos, TimeUnit.NANOSECONDS
        );
        if (!acquired) {
            throw new OverloadedException("NO_WRITE_CAPACITY");
        }

        try {
            return repository.conditionalUpdate(orderId);
        } finally {
            permits.release();
        }
    }
}
~~~

### 8.1. Chờ permit không tự có giới hạn số waiters

Đoạn trên giới hạn **active permits**, nhưng nếu 10.000 threads cùng chờ §tryAcquire(timeout)§ thì 10.000 waiter objects/threads vẫn tồn tại. Muốn giới hạn cả **queued/waiting requests** cần admission layer hoặc executor queue hữu hạn.

### 8.2. Interruption phải có semantics

§InterruptedException§ có thể báo yêu cầu bị hủy khi chờ permit. Không được gọi §permits.release()§ nếu **chưa acquire thành công**. Trong code trên, §finally§ chỉ chạy sau khi §acquired=true§.

Nếu bạn catch interruption và không ném lại, thường cần khôi phục cờ bằng §Thread.currentThread().interrupt()§, nhưng phải theo convention/contract của framework. Không nuốt interruption rồi tiếp tục write ngoài ý muốn.

### 8.3. Không sử dụng waitBudget dài hơn request deadline

Nếu HTTP deadline còn 120 ms, chờ permit 500 ms là vô nghĩa. Tất cả giới hạn chờ nên dùng **remaining deadline** tính từ đầu logical operation, không tính độc lập một timeout mới cho mỗi retry.

## 9. Java: ThreadPoolExecutor có queue hữu hạn

Ứng dụng dùng blocking drivers có thể tách I/O khỏi request event loop bằng một executor riêng. Giới hạn §maximumPoolSize§ **chưa đủ** nếu hàng đợi không có capacity.

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor dbExecutor = new ThreadPoolExecutor(
    16,                                  // core workers
    16,                                  // max workers
    30, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(64),        // bounded queue
    new ThreadPoolExecutor.AbortPolicy()
);

// Later, when the application shuts down:
dbExecutor.shutdown();
~~~

Thực tế §AbortPolicy§ là nested class của §ThreadPoolExecutor§; khi dùng imports tối thiểu, tham chiếu đầy đủ như trong constructor là đủ. Một task bị từ chối tạo §RejectedExecutionException§; application cần ánh xạ thành load-shedding response theo contract.

### 9.1. Tính số lượng công việc tối đa

Với 16 workers và queue 64, nhiều nhất có khoảng **80 tasks đang chạy hoặc chờ trong executor này** (bỏ qua những caller bị block ở phía trước). Nhưng điều đó không bao gồm:

- HTTP server request queue.
- Client requests đang giữ trong framework.
- Driver connection pending-acquire queue.
- DB server queue.

Một executor hữu hạn chỉ giới hạn **một tầng**.

### 9.2. Vì sao CallerRunsPolicy có thể nguy hiểm?

§CallerRunsPolicy§ có thể chạy task ngay trên **thread gọi submit** khi pool đầy. Đó là một dạng backpressure, nhưng nếu caller là **Netty event-loop thread** hoặc thread quản lý HTTP I/O, chạy blocking DB operation ở đó có thể làm nghẽn cả server.

Chỉ dùng khi hiểu caller thread và latency implications; một policy reject rõ ràng thường an toàn hơn ở event-loop frameworks.

### 9.3. Không tạo executor trên mỗi request

Sai:

~~~java
public Order handle(String id) {
    var pool = java.util.concurrent.Executors.newFixedThreadPool(16);
    // submit one job...
    // never shutdown
    return ...;
}
~~~

Điều này có thể tạo hàng nghìn threads/pools và leak tài nguyên. Executor nên có **vòng đời theo application/component**, được đóng khi shutdown.

### 9.4. Không gọi blocking driver trên event loop

Trong Netty/WebFlux/reactive frameworks, một blocking DB call chạy trên event loop có thể chặn nhiều unrelated requests. Cần dùng async driver thực sự hoặc offload sang **bounded scheduler/executor**. Reactive streams không tự biến blocking I/O thành non-blocking.

## 10. Java virtual threads không làm database có thêm capacity

Từ Java 21, **virtual threads** giúp ứng dụng xử lý nhiều blocking tasks mà không cần một platform thread cho từng request đang chờ I/O. Tuy nhiên:

~~~text
10.000 virtual threads
  -> 10.000 concurrent DB operations
  -> same NoSQL connection pool and backend
~~~

Nếu không giới hạn, database vẫn quá tải. Virtual threads thay đổi **chi phí của threads**, không thay:

- Connection pool limits.
- DB query throughput.
- Hot partition capacity.
- Network bandwidth.
- Server-side concurrency.
- Request deadline.

### 10.1. Ví dụ phối hợp virtual threads với semaphore

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;

var dbBulkhead = new Semaphore(64);

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (String orderId : orderIds) {
        executor.submit(() -> {
            if (!dbBulkhead.tryAcquire()) {
                return; // record a defined overload outcome
            }

            try {
                blockingRepository.findById(orderId);
            } finally {
                dbBulkhead.release();
            }
        });
    }
}
~~~

**Lưu ý:** §orderIds§ và §blockingRepository§ giả định đã được khai báo. Đây là mẫu minh họa; code thực phải có timeout, đếm rejection, bảo vệ exception, quyền hủy và kiểm soát số tasks vừa được tạo. Một danh sách 1 triệu IDs vẫn có thể tạo 1 triệu virtual-thread tasks dù semaphore chỉ cho 64 vào DB.

### 10.2. Thread pinning và synchronized

Virtual threads có những chi tiết về blocking/pinning phụ thuộc JDK; một đoạn code giữ monitor hoặc gọi native/blocking APIs có thể ảnh hưởng scalability. Không dùng “virtual threads rẻ” làm lý do bỏ load test hoặc coi mọi driver đều tương thích hoàn hảo.

### 10.3. Phần nên bounded vẫn phải bounded

Để tránh tạo vô hạn tasks, dùng bounded producer/executor/admission ngay **trước khi tạo hoặc submit** virtual-thread task, hoặc xử lý bằng streaming với giới hạn in-flight.

## 11. Connection pool trong Java NoSQL driver

**Connection pool** là nhóm kết nối mạng được driver tạo và tái sử dụng để tránh mỗi request phải thực hiện DNS lookup, TCP/TLS handshake, authentication và protocol setup. Một pool có các trạng thái thường gặp:

~~~text
NEW / CONNECTING
       |
       v
AVAILABLE / IDLE
       |
       +--> ACQUIRED / IN_USE --> RETURNED --> IDLE
       |
       +--> STALE / FAILED --> CLOSED

Pending acquirer:
  waiting until a suitable connection is available
  or until its wait deadline expires
~~~

### 11.1. Các knobs cần hiểu

| Cấu hình khái niệm | Mục tiêu | Rủi ro khi đặt không phù hợp |
| --- | --- | --- |
| §maxPoolSize§ / max connections | Giới hạn connections của pool | Quá nhỏ gây acquire wait, quá lớn gây backend overload |
| §minPoolSize§ / minIdle | Giữ sẵn một số connections | Tạo quá nhiều idle connections khi scale pods |
| §maxConnectionIdleTime§ | Đóng kết nối nhàn rỗi quá lâu | Quá ngắn tạo handshake churn |
| §maxConnectionLifetime§ | Tái tạo connection định kỳ | Churn hoặc mass reconnect nếu đồng bộ |
| §maxConnecting§ | Giới hạn connections cùng được thiết lập | Startup/failover quá chậm hoặc connect storm |
| §maxWaitTime§ | Giới hạn thời gian acquire | Chờ vô hạn hoặc reject quá sớm |
| Connection establish timeout | Giới hạn TCP/TLS/protocol setup | Không đồng nhất với query deadline |
| Socket/read timeout | Giới hạn một số đường network wait | Không tự chứng minh server đã hủy operation |
| Operation deadline | Deadline từ client cho logical operation | Không được reset sau mỗi retry |
| Max in-flight/streams | Số requests hoạt động trên connection/node | Khác max số sockets |

**Tên field thay đổi theo driver**. Có driver chọn pool theo node, có driver dùng event loop và HTTP connection manager, có driver thực hiện multiplex, có driver cho nhiều logical streams trên một connection.

### 11.2. Max pool là ngân sách theo scope nào?

Một client kết nối đến cụm 3 servers có thể giữ **pool riêng cho mỗi server**. Giá trị §maxPoolSize=40§ có thể nghĩa tối đa 40 connections **cho mỗi server**, không phải 40 connections toàn cluster.

Trong môi trường sharded cluster, nhiều servers/routers/replicas và monitoring sockets khiến số connection thực khác phép nhân đơn giản §pods×40§.

### 11.3. MaxPoolSize không phải max DB operations

Một số driver có khả năng multiplex requests; trong trường hợp đó 40 TCP connections có thể phục vụ hơn 40 in-flight operations. Ngược lại, một query scan/transaction dài có thể giữ tài nguyên khiến pool cạn dù QPS không lớn.

Mọi bảng sizing phải dựa vào **driver pool telemetry, pending requests và server-side active work**, không chỉ một biến cấu hình.

### 11.4. Pool wait là một hàng đợi cần quan sát

Nếu một operation chờ pool 350 ms rồi server xử lý 30 ms, tổng request có thể chậm gần 400 ms dù query execution nhanh. Nếu chỉ đo query time sau khi lấy connection, bạn sẽ **không thấy bottleneck chính**.

### 11.5. Leaked connections là sự cố vòng đời

Cursors, streams, explicit sessions, transactions hoặc resource handles chưa đóng có thể giữ connection/transaction state lâu hơn cần thiết tùy driver. Cần:

- §try-with-resources§ nếu resource hỗ trợ §AutoCloseable§.
- §finally§/callbacks có đường cleanup khi exception/cancellation.
- Close client/pool **khi ứng dụng shutdown**, không close trên từng request.
- Theo dõi active connections không giảm sau khi load hết.
- Đặt transaction timeout và tránh session sống lâu quá.

## 12. Nguyên tắc vòng đời: một client lâu dài, tài nguyên theo request ngắn

Một pattern thường đúng là:

~~~text
Application starts
    |
    +-- Create/configure ONE shared driver client or session component
    |
    +-- Request 1: borrow/use connection transparently, release
    +-- Request 2: borrow/use connection transparently, release
    +-- Request 3: borrow/use connection transparently, release
    |
Application shuts down
    |
    +-- Stop accepting work
    +-- Drain/cancel in-flight work within deadline
    +-- Close client/session/pool and executors
~~~

### 12.1. Không tạo database client cho từng HTTP request

Sai về vòng đời:

~~~java
public Order handle(String id) {
    // Illustrative anti-pattern: creating an entire connection
    // manager and pool for every HTTP request.
    var client = createNewDatabaseClient();
    return client.findOrder(id);
    // client may never be closed
}
~~~

Hậu quả có thể là:

- TCP/TLS handshake mỗi request.
- Authentication overhead.
- Quá nhiều background monitor threads.
- Pool fragmentation.
- File descriptor/socket leak.
- Reconnect storm khi database failover.

### 12.2. Shared client nhưng không shared request-local state

Client/session thread safety phụ thuộc driver. Nhiều **driver client objects** được thiết kế để tái sử dụng, nhưng:

- Explicit transaction/session có thể không thread-safe cho concurrent operations.
- Cursor/iterator thường có state theo request.
- Redis connection ở transaction/pubsub mode có thể không dùng chung theo cùng cách với connection thông thường.
- Mutating request builder/command context có thể không thread-safe.

Đọc documentation theo **loại object**, không suy “client thread-safe” nghĩa mọi object do client tạo đều thread-safe.

### 12.3. Graceful shutdown

Thứ tự khái niệm:

~~~text
1. Mark instance not ready for new traffic.
2. Stop accepting new operations.
3. Wait a bounded time for in-flight operations.
4. Cancel or mark PENDING operations whose outcome is unknown.
5. Close cursors/sessions/subscriptions.
6. Close clients, pools, event loops and executors.
7. Terminate process.
~~~

Không đóng pool ngay khi Kubernetes gửi shutdown signal rồi làm tất cả in-flight requests timeout, nếu có thể drain an toàn. Nhưng cũng không chờ vô hạn; phải có deadline, recovery/idempotency path.

## 13. MongoDB Java Sync Driver: cấu hình pool theo client

Ví dụ cấu hình cơ bản cho MongoDB Java synchronous driver theo API hiện diện trong nhiều phiên bản hiện đại:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.concurrent.TimeUnit;

String uri = System.getenv("MONGODB_URI");

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool -> pool
        .maxSize(40)
        .minSize(0)
        .maxWaitTime(200, TimeUnit.MILLISECONDS))
    .build();

MongoClient client = MongoClients.create(settings);

// Reuse "client" in application-scoped repository/service.
// During application shutdown:
client.close();
~~~

Đây là ví dụ cấu hình **trên một §MongoClient§**, không phải hướng dẫn tạo client per request. Tùy bản driver, cấu hình còn có §maxConnecting§, event listeners, connection lifetime/idle và retry options.

### 13.1. Driver tự quản lý per-server pools

Khi kết nối replica set hoặc sharded topology, driver có thể tạo pool/monitoring connections theo server. §maxSize=40§ không nên được tính là chính xác 40 sockets cho toàn bộ cluster. Cần xem metrics per server, total sockets và topology.

### 13.2. Cursor phải được đóng đúng cách

~~~java
import com.mongodb.client.MongoCursor;
import org.bson.Document;

try (MongoCursor<Document> cursor =
         collection.find(filter).iterator()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        process(doc);
    }
}
~~~

§collection§, §filter§, §process§ là các thành phần minh họa đã được cung cấp từ application. Ý tưởng chính: **không giữ cursor sống qua thời gian dài vô hạn**, và đóng resource khi exception.

### 13.3. Long-running transactions có thể ảnh hưởng pool

Transaction mở trong lúc gọi HTTP API bên ngoài hoặc chờ user input có thể giữ snapshot/locks/resources lâu, gây conflict và giảm throughput. Nên giữ transaction ngắn, chỉ bao gồm các DB operations thật sự cần atomicity.

### 13.4. MaxWaitTime khác query maxTime

- §maxWaitTime§ liên quan **chờ connection trong pool**.
- §maxTimeMS§/operation-specific timeout (nếu API hỗ trợ) liên quan **giới hạn execution** theo server/driver semantics.
- Socket timeout và operation timeout có thể khác nhau.

Không đổi một config duy nhất rồi kỳ vọng toàn bộ HTTP deadline được cưỡng chế.

## 14. Cassandra/ScyllaDB Java driver: coordinator, multiplex và session

Cassandra Java driver sử dụng **§CqlSession§** như một đối tượng ứng dụng cấp cao thường được tái sử dụng, quản lý connections/metadata tới cluster.

Ví dụ theo phong cách API:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
    .withLocalDatacenter("dc1")
    .build();

// Reuse session to execute prepared statements / queries.
// On application shutdown:
session.close();
~~~

Các giá trị contact point/DC chỉ là mẫu để minh họa cấu trúc; môi trường thật phải dùng topology, TLS, authentication và routing của cluster.

### 14.1. Connection multiplexing

Với protocol/driver cho phép nhiều in-flight requests trên một connection, số requests tối đa chịu ảnh hưởng của:

- Max requests per connection/node.
- Number of connections per node.
- In-flight request limiting.
- Coordinator availability.
- Token-aware load balancing.
- Per-request timeout và speculative execution policy.

Không sizing bằng “mỗi query cần một TCP connection”.

### 14.2. Một truy vấn chậm ở coordinator

Query có partition key không phù hợp, quá nhiều tombstones, compaction pressure hoặc một partition cực nóng có thể làm coordinator giữ request lâu. Tăng client connections có thể đưa thêm công việc vào cùng bottleneck.

### 14.3. Retry/speculative execution

Một số driver hỗ trợ **speculative execution** để giảm tail latency cho những operation phù hợp, nhưng nó có thể tạo thêm attempts gửi tới nhiều coordinators.

Với writes không idempotent, retry/speculative behavior cần đặc biệt thận trọng. Phải đọc docs của driver và **đánh dấu idempotence đúng semantics**; không tự đánh dấu một counter increment hoặc external business effect là idempotent chỉ để được retry.

### 14.4. Async session

§executeAsync§ không chặn thread đợi kết quả, nhưng vẫn có **in-flight requests, network buffers, callbacks và backend capacity**. Một vòng lặp tạo 100.000 futures không có limit vẫn có thể làm session/driver overload.

### 14.5. Closing session

Không gọi §session.close()§ sau mỗi query. Đóng khi component/application kết thúc, sau khi stop new traffic và xử lý in-flight requests theo deadline.

## 15. Redis: kết nối theo chế độ sử dụng

Redis clients khác nhau có cách chia sẻ connection khác nhau.

### 15.1. Jedis pool và try-with-resources

Một ví dụ theo dạng §JedisPool§:

~~~java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;

JedisPool pool = new JedisPool("127.0.0.1", 6379);

// Per operation:
try (Jedis jedis = pool.getResource()) {
    String value = jedis.get("order:O900");
    use(value);
}

// Close once during application shutdown:
pool.close();
~~~

§use§ là callback/domain function giả định. Trong code thật, dùng TLS/auth/config đầy đủ. §close()§ của resource lấy từ pool trả resource theo contract của client; §pool.close()§ đóng toàn pool.

### 15.2. Lettuce và connection sharing

Lettuce có cách sử dụng asynchronous/reactive và hỗ trợ reuse một số loại connection tùy command/state. Tuy nhiên Pub/Sub, transactions, blocking operations hoặc các chế độ stateful có thể cần **connection riêng hoặc quy tắc không dùng chung**.

Không mặc định một connection có thể được gọi concurrently với mọi Redis commands mà không ảnh hưởng semantics.

### 15.3. Blocking Redis commands

Các thao tác như blocking pop hoặc long-lived subscription có thể chiếm connection lâu. Không để chúng lấy hết cùng pool với short GET/SET requests. Tách connection class/pool nếu driver/protocol yêu cầu.

### 15.4. Pipeline không tự là backpressure

Redis pipelining giảm round trips, nhưng bơm quá nhiều commands chưa đọc response có thể làm tăng memory/network buffers ở cả client và Redis. Cần giới hạn batch size, pending replies và deadline; command ordering và failure handling theo connection/protocol.

## 16. DynamoDB Java SDK: HTTP client capacity và service throttling

DynamoDB là managed service; ứng dụng **không mở socket trực tiếp tới một partition server** như nhiều self-managed NoSQL databases. Java SDK sử dụng HTTP connection manager/event loops cho endpoints.

### 16.1. Sync và async khác nhau

**Synchronous client:** Một thread thường chờ HTTP response; sizing liên quan thread count và HTTP connection pool.

**Asynchronous client:** Một số lượng event-loop threads nhỏ có thể phục vụ nhiều pending requests; cần giới hạn **max concurrency, pending acquires, memory và callback work**.

### 16.2. Ví dụ async HTTP client cấu hình giới hạn

Tùy phiên bản AWS SDK for Java v2, một hướng cấu hình là:

~~~java
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.services.dynamodb.DynamoDbAsyncClient;

DynamoDbAsyncClient client = DynamoDbAsyncClient.builder()
    .httpClientBuilder(
        NettyNioAsyncHttpClient.builder()
            .maxConcurrency(60)
            .maxPendingConnectionAcquires(120))
    .build();

// Application-wide client; close during shutdown:
client.close();
~~~

Đây là mẫu cho **Java SDK async HTTP transport**, không phải cú pháp chung cho mọi SDK version/service. Các giới hạn và API/cấu hình thực tế phải tra theo SDK đang triển khai.

### 16.3. HTTP maxConcurrency không phải DynamoDB partition throughput

§maxConcurrency=60§ kiểm soát năng lực **HTTP requests của client transport** theo semantics SDK. Nó không tăng giới hạn read/write capacity của một partition key, không sửa hot partition và không tự kiểm soát toàn bộ pods.

### 16.4. SDK adaptive retries và throttling

DynamoDB có thể trả throttling khi capacity/hot partition bị vượt. SDK có retry strategies, backoff và các mode đặc thù. Điều quan trọng:

- Không xây thêm một retry loop ngoài SDK mà quên tổng attempt budget.
- Đọc hành vi retry mode đang dùng, trong cả latency và token budget.
- Tránh đánh dấu mọi §ConditionalCheckFailed§ thành transient retry.
- Dùng key design/backpressure thay vì chỉ tăng số HTTP connections.

### 16.5. Deadline và cancellation trong async SDK

§CompletableFuture.cancel()§ không nhất thiết chứng minh server chưa thực hiện operation. Với writes, timeout/cancellation có thể dẫn đến **unknown commit outcome**; cần idempotency/conditional write theo business semantics.

## 17. Connection startup, warm-up và reconnect storm

Một lỗi vận hành thường gặp khi autoscaling:

~~~text
10 pods start simultaneously.
Each pod minIdle=60 connections.
All pods connect to same cluster.
=> 600 connections established in a short burst.
~~~

Nếu DB vừa failover hoặc TLS/authentication tốn CPU, việc khởi tạo connections đồng loạt có thể khiến service chậm khởi động, timeout, rồi retry tạo thêm connections.

### 17.1. Các biện pháp

- Dùng **minIdle vừa đủ**, không warm toàn bộ maxPoolSize nếu không cần.
- Giới hạn tốc độ thiết lập connections nếu driver hỗ trợ.
- Startup/readiness probes phân biệt việc khởi tạo bình thường và outage.
- Rolling deployment tránh tăng đột ngột cả old/new pods.
- Thêm jitter vào background reconnect/retry.
- Theo dõi connection creation rate và authentication errors.

### 17.2. Keepalive, idle timeout và load balancer

Kết nối nhàn rỗi có thể bị LB/NAT/firewall đóng trước khi driver biết. Một số drivers phát hiện socket stale và reconnect, nhưng request đầu có thể bị lỗi/timeout.

Cần phối hợp:

~~~text
client pool idle/lifetime policy
network LB idle timeout
TCP keepalive settings
driver health checks
server connection timeout
~~~

Không đặt §maxConnectionLifetime§ bằng một con số tùy ý mà bỏ qua topology/handshake cost.

### 17.3. DNS và endpoint rotation

Khi node được thay, driver topology discovery/DNS caching có thể ảnh hưởng khả năng kết nối. Không hardcode IP của shard/replica khi sản phẩm dùng endpoint discovery; đọc driver reconnect behavior và cloud service guidance.

## 18. Resource leak không chỉ là socket leak

Ứng dụng Java có thể giữ các tài nguyên khác:

- Database cursor/stream chưa đóng.
- Transaction/session bị bỏ dở.
- Futures/callback chains chưa được giải phóng.
- Event-loop group do mỗi client tự tạo.
- ThreadPoolExecutor chưa shutdown.
- Buffers/byte arrays giữ trong queue.
- Retry tasks đã hết deadline nhưng chưa bị hủy.
- Listeners/subscriptions được đăng ký nhiều lần.
- Permit của semaphore bị mất do exception.
- Metrics/tracing contexts giữ references tới payload lớn.

### 18.1. Dấu hiệu tài nguyên rò rỉ

~~~text
Traffic returns to idle.
But activeConnections remains high.
InFlight does not decline.
Queue depth never returns to zero.
Heap retained objects grow.
Thread count increases over time.
~~~

Nếu hệ vẫn giữ subscription/cursor cố ý, không nhất thiết là leak; cần phân biệt **long-lived resources hợp lệ** và những resource không được giải phóng.

### 18.2. Một shutdown hook không thay vòng đời framework

Trong Spring Boot/Micronaut/Quarkus, client có thể được quản lý bởi dependency injection/container lifecycle. Đừng đăng ký nhiều shutdown hooks độc lập gây close hai lần hoặc race với in-flight requests. Dùng cơ chế lifecycle chính thức của framework/driver.

### 18.3. Không close shared client trong một request

Ngược lại với leak là close quá sớm:

~~~text
Request A finishes -> closes shared client
Request B still using same client -> fails
~~~

Tái sử dụng client trong toàn service và chỉ close khi **owner component của client** kết thúc.

## 19. Timeout và deadline: tránh cộng dồn hàng chờ

Một request có thể bị giới hạn ở nhiều tầng:

~~~text
API request deadline
    |
    +-- waiting for admission / semaphore
    +-- waiting in executor queue
    +-- waiting for DB connection from pool
    +-- DNS/TCP/TLS/connect
    +-- waiting for DB query execution / network response
    +-- mapping and serialization
    +-- optional retry with backoff
~~~

Nếu mỗi tầng được cấu hình timeout 1 giây **độc lập**, tổng thời gian thực tế có thể vượt xa SLO. Thay vì “mỗi lần retry có 1 giây mới”, dùng **end-to-end deadline** cho logical operation.

### 19.1. Ví dụ phân bổ ngân sách 800 ms

| Thành phần | Ngân sách ví dụ | Ghi chú |
| --- | --- | --- |
| HTTP end-to-end deadline | 800 ms | Giới hạn tổng, không phải cộng độc lập |
| Admission + queue wait | tối đa 50 ms | Fail fast khi không có chỗ |
| Pool acquisition | tối đa 100 ms | Không vượt remaining deadline |
| DB request attempt | tối đa 400 ms | Theo API/driver/server semantics |
| Serialization/response | dự phòng 100 ms | Cần headroom |
| Retry/backoff | dùng phần **còn lại** | Không tự reset 800 ms |

Các số không phải tuning mặc định. Tổng “các max timeout” không thể tự bảo đảm bằng 800 ms nếu các thành phần không chia sẻ cùng deadline; cần tính **remaining budget** tại thời điểm bắt đầu mỗi bước.

### 19.2. Deadline monotonic trong Java

§System.nanoTime()§ thích hợp để đo **elapsed duration trong một process**, tránh lỗi do wall-clock thay đổi.

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class Deadline {
    private final long startedNanos = System.nanoTime();
    private final long budgetNanos;

    public Deadline(Duration totalBudget) {
        if (totalBudget.isNegative()) {
            throw new IllegalArgumentException("negative budget");
        }
        this.budgetNanos = totalBudget.toNanos();
    }

    public long remainingNanos() {
        long elapsed = System.nanoTime() - startedNanos;
        return Math.max(0L, budgetNanos - Math.max(0L, elapsed));
    }

    public long remainingMillis() {
        return TimeUnit.NANOSECONDS.toMillis(remainingNanos());
    }

    public boolean expired() {
        return remainingNanos() == 0L;
    }
}
~~~

Đây là một ví dụ giáo dục: khi budget cực lớn, §Duration.toNanos()§ có thể overflow; trong library production cần xử lý overflow, cancellation và context propagation. Deadline chia sẻ giữa nhiều processes qua network cần **header/relative timeout/clock uncertainty policy** thích hợp, không truyền raw §nanoTime()§ của JVM A sang JVM B.

### 19.3. Timeout không phải hủy transaction

Nếu client timeout/cancel sau khi gửi write:

~~~text
T0: Client submits UPDATE.
T1: Server commits UPDATE.
T2: Network response lost.
T3: Client reports TIMEOUT.
~~~

Không được diễn giải TIMEOUT là DB đã rollback. Với operation có side effect, cần idempotency key, conditional mutation hoặc outcome lookup theo driver/product contract.

### 19.4. Quá nhiều timeout còn có thể gây retry storm

Khi database chậm, request timeout sớm; gateway gửi lại; SDK cũng retry; số attempts tăng khiến database càng chậm. Chỉ tăng timeout có thể khiến queue dài hơn. Phải đồng thời xét **admission, request budget và retry policy**.

## 20. Rate limiting bằng token bucket

**Token bucket** có:

- Tốc độ bổ sung token trung bình \(r\) token/s.
- Dung lượng bucket tối đa \(B\) token.
- Mỗi operation tiêu thụ một hoặc nhiều token.
- Nếu không đủ token: reject, chờ có giới hạn hoặc theo policy khác.

Ví dụ:

~~~text
refillRate = 500 tokens/s
capacity   = 100 tokens
cost       = 1 token per read request
~~~

Bucket cho phép **burst ngắn** trong giới hạn token còn sẵn, trong khi tốc độ bền vững theo \(r\). Đây là hạn chế **arrival rate**, không đặt trần trực tiếp cho in-flight operations.

### 20.1. Java: token bucket cục bộ đơn giản

~~~java
public final class LocalTokenBucket {
    private final double refillPerSecond;
    private final double capacity;
    private double tokens;
    private long lastRefillNanos;

    public LocalTokenBucket(double refillPerSecond, double capacity) {
        if (refillPerSecond <= 0 || capacity <= 0) {
            throw new IllegalArgumentException("positive parameters required");
        }
        this.refillPerSecond = refillPerSecond;
        this.capacity = capacity;
        this.tokens = capacity;
        this.lastRefillNanos = System.nanoTime();
    }

    public synchronized boolean tryAcquire(double cost) {
        if (cost <= 0 || cost > capacity) {
            throw new IllegalArgumentException("invalid token cost");
        }

        long now = System.nanoTime();
        long elapsedNanos = Math.max(0L, now - lastRefillNanos);
        double elapsedSeconds = elapsedNanos / 1_000_000_000.0;

        tokens = Math.min(
            capacity, tokens + elapsedSeconds * refillPerSecond
        );
        lastRefillNanos = now;

        if (tokens < cost) {
            return false;
        }
        tokens -= cost;
        return true;
    }
}
~~~

Đây là rate limiter **trong một JVM**, không phải quota toàn cluster. Mã còn cần xử lý lifecycle, update config, fairness, metrics, số nguyên/cost và edge cases nếu được đưa vào thư viện production.

### 20.2. Mỗi tenant có một bucket hay chung?

Một bucket global có thể bị tenant đông nhất dùng hết. Per-tenant buckets hỗ trợ isolation nhưng tăng metadata và yêu cầu eviction/retention cho tenants ít hoạt động.

Một chính sách kết hợp:

~~~text
Global database rate budget
  AND
Per-tenant budget
  AND
Per-operation-class budget
~~~

Muốn kiểm soát quota trên nhiều pods cần **distributed limiter, gateway hoặc hệ phân phối budget** với consistency/availability contract rõ; copy cùng limit 500/s vào mỗi pod không tạo global limit 500/s.

### 20.3. Weighted token costs

Không phải mọi operation cùng chi phí:

~~~text
point GET       -> cost 1
small range GET -> cost 3
bulk export     -> cost 20
write transaction -> cost based on measured resource usage
~~~

Weighted limiter có thể giúp phân bổ tài nguyên, nhưng trọng số phải đo thực tế, không tự coi một query “rất dài” luôn bằng đúng 20 point reads.

### 20.4. Rate limiter vs rate capacity của database

Một NoSQL service có thể throttle theo **partition key, table, region, tenant hoặc account quota**. Một token bucket ở API chỉ bảo vệ những routes nó kiểm soát; batch jobs, CDC connectors và services khác vẫn có thể vượt quota.

## 21. Backpressure cho async và reactive Java

Async API có thể làm code trông “không chờ”:

~~~java
for (String orderId : allOrderIds) {
    asyncRepository.findById(orderId);
}
~~~

Nếu §allOrderIds§ có 100.000 phần tử, loop có thể tạo 100.000 in-flight/pending operations rất nhanh. **Không block calling thread không đồng nghĩa backend không tốn tài nguyên.**

### 21.1. Semaphore cho CompletionStage

~~~java
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Semaphore;

public final class BoundedAsyncReader {
    private final AsyncOrderRepository repository;
    private final Semaphore permits = new Semaphore(64);

    public BoundedAsyncReader(AsyncOrderRepository repository) {
        this.repository = repository;
    }

    public CompletionStage<Order> find(String orderId) {
        if (!permits.tryAcquire()) {
            throw new OverloadedException("ASYNC_DB_LIMIT");
        }

        CompletionStage<Order> call;
        try {
            call = repository.findByIdAsync(orderId);
        } catch (RuntimeException | Error failure) {
            permits.release();
            throw failure;
        }

        return call.whenComplete((value, error) -> permits.release());
    }
}
~~~

Điểm cần nắm:

- Permit được lấy **trước khi submit** async DB call.
- Nếu việc tạo call thất bại đồng bộ, release permit ngay.
- Với operation được submit, release trong **completion callback**, không release khi method §find§ vừa trả về future.
- Không release hai lần.
- Cancellation và driver-level completion semantics phải được hiểu: hủy future ở tầng HTTP không luôn dừng server-side work.

### 21.2. Không giữ permit suốt chuỗi tính toán nếu chỉ muốn giới hạn DB

Nếu một future tiếp tục xử lý CPU nặng sau DB response, có thể release DB permit ngay khi DB stage hoàn tất rồi dùng executor khác cho CPU work. Giữ permit tới khi toàn bộ workflow xử lý xong khiến giới hạn DB bị dùng để đo cả CPU/HTTP.

### 21.3. Reactive flatMap concurrency

Với Reactor-like API, một cơ chế giới hạn có thể là:

~~~java
Flux.fromIterable(orderIds)
    .flatMap(id -> reactiveRepository.findById(id), 32)
    .collectList();
~~~

§flatMap(...,32)§ minh họa giới hạn concurrency của stage đó, **không thay toàn bộ driver/client request limits** nếu nguồn hoặc operators khác vẫn tạo thêm work. Không nên §block()§ trên event loop để “đợi đủ chỗ”.

### 21.4. Demand/backpressure không tự bảo đảm end-to-end

Reactive Streams có tín hiệu demand giữa publisher/subscriber, nhưng driver, broker, network và upstream source có **buffering rules** khác nhau. Cần đọc prefetch, concurrency và buffer sizes; tránh operator tự tạo queue vô hạn hoặc prefetch lớn không cần thiết.

### 21.5. Callback phải đủ nhẹ

Không làm parsing CPU nặng hoặc blocking network call trong thread event-loop callback của driver. Offload sang bounded executor/scheduler phù hợp, giữ context của tracing và deadline.

## 22. Circuit breaker khác bulkhead và rate limiter

Ba công cụ kiểm soát các vấn đề khác nhau:

| Cơ chế | Mục đích chính | Kết quả khi vượt ngưỡng |
| --- | --- | --- |
| **Concurrency limiter/bulkhead** | Giới hạn active work và cách ly workloads | Không cấp thêm permit |
| **Rate limiter** | Giới hạn tốc độ nhận work | Reject/delay |
| **Circuit breaker** | Dừng thử phụ thuộc đang có tỷ lệ lỗi/latency bất thường | Fast-fail có thời hạn, sau đó thăm dò |
| **Timeout/deadline** | Giới hạn thời gian một ý định có thể chờ | Cancel/report unknown per contract |
| **Retry policy** | Phục hồi transient failure có điều kiện | Tăng attempts, cần budget |
| **Queue/buffer** | Hấp thụ burst tạm thời | Có thể đầy, cần policy |

### 22.1. Circuit breaker states

~~~mermaid
flowchart LR
    C["CLOSED: requests flow"] -->|Failure/latency threshold| O["OPEN: fast-fail"]
    O -->|Cooldown| H["HALF_OPEN: bounded probes"]
    H -->|Healthy probes| C
    H -->|Failed probes| O
~~~

Điều này chỉ minh họa mô hình phổ biến. Ngưỡng/window/probe semantics phụ thuộc thư viện.

### 22.2. Circuit breaker không bảo vệ mọi operation như nhau

Nếu một shard bị lỗi nhưng các shards khác vẫn khỏe, một **global circuit breaker** có thể làm hỏng cả hệ không cần thiết. Có thể dùng breaker theo dependency/endpoint/shard group hoặc operation class, tùy routing và cardinality.

### 22.3. Một breaker OPEN không chứng minh request trước đó chưa commit

Breaker chỉ kiểm soát request mới. Một write trước khi breaker mở có thể có **unknown outcome**. Không được gửi cùng business mutation sang một server khác mà bỏ qua idempotency.

### 22.4. Bảo vệ probe traffic

Khi breaker chuyển HALF_OPEN, không cho tất cả threads cùng probe. Nếu 10.000 requests cùng thử lại, database vừa phục hồi sẽ bị đánh gục. Cần **giới hạn probe concurrency**, jitter và admission budget.

## 23. Retry: giới hạn, backoff, jitter và idempotency

Mục tiêu retry là phục hồi **lỗi tạm thời thực sự có khả năng thành công ở lần sau**, chứ không phải ép tất cả lỗi thành SUCCESS.

### 23.1. Không retry mọi lỗi

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Business conflict | Version CAS mismatch | Re-read/re-evaluate intent |
| Validation error | Invalid partition key/payload | Không retry |
| Auth/permission | Sai credentials/ACL | Sửa config, không retry dồn dập |
| Known overload/throttle | Capacity exceeded | Bounded retry với backoff hoặc reject |
| Transient network connect failure trước gửi | Connect failed | Retry theo driver contract |
| Timeout sau gửi write | Outcome có thể UNKNOWN | Idempotency/outcome lookup |
| Non-idempotent counter update | Increment có thể đã commit | Không retry mù |
| Server unavailable lâu | Dependency outage | Circuit breaker/backpressure |

### 23.2. Exponential backoff với full jitter

Ví dụ delay cap:

\[
d_n = \min(d_{\max}, d_{\text{base}}\times 2^n)
\]

Full jitter:

~~~text
sleep randomly within [0, d_n]
~~~

Nên tính n theo attempt index, giới hạn multiplication overflow và số attempts. Retry chỉ thực hiện nếu **remaining deadline đủ**; không để một request đã quá deadline vẫn đợi thêm 30 giây để thử lại.

### 23.3. Retry amplification qua nhiều tầng

Ví dụ:

~~~text
API gateway retries up to 3
  Service retry wrapper retries up to 3
    SDK retries up to 3
~~~

Trong tình huống xấu, một logical user operation có thể tạo **tới 27 attempts ở đường sâu nhất** nếu mỗi tầng đều thực hiện đủ retries. Không để mỗi tầng sở hữu budget độc lập mà không biết các tầng khác.

### 23.4. Đọc default retry policy của SDK

Một số SDK tự retry throttling/connection issues, có thể thực hiện thêm requests ngầm. Cần đo §attempts per logical request§ thay vì chỉ đếm số lần controller gọi repository.

### 23.5. Idempotent read khác idempotent write

Một point read không side effect có thể phù hợp hơn để retry. Nhưng write:

~~~text
DECREMENT inventory
INCREMENT counter
CAPTURE payment
~~~

có thể tạo tác động trùng. Nếu không có idempotency token/dedup hoặc conditional source state, timeout không phải tín hiệu cho phép thử lại mù.

### 23.6. Retry budget cho toàn service

Ngoài số attempts mỗi request, có thể giới hạn **tỷ lệ retry toàn hệ**:

~~~text
Retries allowed per second <= fraction of normal traffic
~~~

Khi dependency lỗi hàng loạt, policy này ngăn retries chiếm hết capacity của requests mới hoặc quá trình phục hồi.

## 24. Ngân sách kết nối toàn cụm và autoscaling

Giả sử:

~~~text
Maximum useful connections the DB can support: 1.000
Reserved for administrators/monitoring:         100
Reserved for batch/CDC/migration jobs:           150
Available application connection budget:         750
Expected max concurrent API pods:                20
~~~

Nếu mỗi pod có một pool dùng cùng endpoint:

\[
\text{Per-pod budget}\le \left\lfloor\frac{750}{20}\right\rfloor=37
\]

Đây là phép chia khái niệm để bắt đầu phân bổ, chưa tính **per-server pools, extra monitoring connections, connection setup bursts, deployment overlap hoặc client khác**.

### 24.1. Rollout có thể làm gấp đôi số pods tạm thời

Nếu 20 pods cũ và 10 pods mới cùng tồn tại trong rolling deploy, số client/pool tăng trong giai đoạn ngắn. Không tính budgets chỉ từ replicaCount ổn định.

### 24.2. Autoscale ứng dụng không tạo thêm database capacity

Khi thêm API pods, aggregate concurrency và connection attempts tăng nếu mỗi pod có cùng limit. Nếu DB đang saturated, autoscale vì CPU/latency ở app có thể làm tình hình xấu hơn.

Một hệ cần phối hợp:

- Pod scaling theo business load và dependency health.
- Per-pod concurrency/pool budget.
- Shared/global rate budget hoặc quota.
- Autoscale database/capacity nếu sản phẩm hỗ trợ.
- Load shedding khi không thể mở rộng DB ngay.

### 24.3. Mối quan hệ với replicas

Với MongoDB replica set, read preference quyết định đọc từ primary/secondary và các pools liên quan. Với Cassandra, driver có connections per node và coordinator selection. Với DynamoDB, HTTP transport dùng endpoints và capacity theo table/partition. Không dùng một công thức “DB có N nodes => maxPool×N” cho mọi engine.

### 24.4. Global quota với nhiều API services

Giả sử:

~~~text
Order API
Inventory API
Admin export job
Reconciliation worker
Analytics ingest
~~~

cùng dùng một cụm NoSQL. Nếu mỗi service tự đặt limit bằng **toàn bộ database budget**, tổng cộng vẫn quá tải. Cần **phân chia ngân sách** và tổ chức quyền ưu tiên giữa workloads.

### 24.5. Distributed limiter có trade-off

Nếu dùng Redis/coordination service để cấp permit toàn cụm, limiter đó có **network latency, failure, stale lease, timeout và consistency semantics**. Nó có thể trở thành một phụ thuộc mới trên hot path. Trong một số hệ, phân bổ budget tĩnh/động theo pods với tổng headroom đủ là đơn giản và robust hơn.

## 25. Hệ NoSQL thường nghẽn ở shard/partition chứ không phải tổng kết nối

Một cụm 20 nodes có thể còn CPU trung bình 35% nhưng một **hot partition key** đang quá tải.

~~~text
tenantId = "super-tenant"
  -> same partition / same shard routing hot spot
  -> 90% reads/writes to one small area
~~~

Tăng client concurrency có thể chỉ tăng queue tại coordinator/shard nóng.

### 25.1. Ví dụ hot key

Một API đếm view thực hiện:

~~~text
UPDATE counters
SET views = views + 1
WHERE id = "global-homepage";
~~~

Nếu mọi requests ghi cùng một counter, có thể tạo contention trên một key. Các phương án:

- Sharded counters nếu business semantics cho phép.
- Buffer/aggregate events rồi batch update.
- CQRS/read model cho dashboard.
- Per-key rate limit.
- Bounded write queues.
- Chọn data model phù hợp partition-key distribution.

### 25.2. Không đổi key bừa khi cần atomicity

Sharding một counter thành 100 keys có thể tăng throughput, nhưng số tổng là eventual aggregation; không tự dùng kết quả đó làm **nguồn authoritative cho quyết định inventory còn một sản phẩm**.

### 25.3. Transaction contention khác connection saturation

Nhiều concurrent transactions cùng update một document có thể gây conflicts/aborts. Pool vẫn có idle connections, nhưng throughput không tăng. Cần giảm contention hoặc đổi aggregate/data model; tăng connection count không sửa logic tranh chấp.

### 25.4. Tombstones, indexes và query shape

Range scan lớn, fan-out không có partition key, secondary-index overload, tombstones/compaction hoặc thiếu index có thể làm mỗi operation chậm hơn, kéo tăng concurrency cần thiết theo Little’s Law. Giải pháp có thể nằm ở **query/access-pattern redesign** chứ không phải một semaphore.

## 26. Queueing và “đầu gối” của đường cong latency

Khi một resource gần đạt capacity, thêm rất ít arrival load có thể làm **queue wait tăng mạnh**.

Trong mô hình **M/M/1 lý tưởng hóa** với arrival rate \(\lambda\) nhỏ hơn service rate \(\mu\):

\[
W=\frac{1}{\mu-\lambda}
\]

Trong đó \(W\) là mean time in system, gồm chờ và phục vụ, theo giả định arrival/processing distributions, một server và trạng thái ổn định của mô hình. Đây **không phải công thức tuning trực tiếp cho một cluster NoSQL có nhiều connections/servers**.

Ví dụ minh họa:

| Arrival \(\lambda\) | Service rate \(\mu\) | Mean W trong M/M/1 |
| --- | --- | --- |
| 50 req/s | 100 req/s | 20 ms |
| 80 req/s | 100 req/s | 50 ms |
| 90 req/s | 100 req/s | 100 ms |
| 95 req/s | 100 req/s | 200 ms |
| 99 req/s | 100 req/s | 1.000 ms |

Nhìn một mô hình đơn giản cũng thấy: **latency có thể tăng phi tuyến khi utilization tiến gần 100%**. Trên hệ thật, burstiness, lock contention, hot keys, compaction, GC và query mix còn làm tail latency khác biệt đáng kể.

### 26.1. Vì sao không nên nhắm utilization 100%?

Một hệ cần headroom cho:

- Bursts bất ngờ.
- Leader failover/rebalance.
- Queries chậm và long-tail.
- Backups/compaction/repair.
- Retry traffic hợp lệ.
- Thay đổi query mix.

Mức headroom phù hợp phải đo theo SLO, capacity model và các lỗi muốn chịu được; không có một ngưỡng 70% hay 80% đúng cho mọi NoSQL.

### 26.2. Một queue ngắn có thể hữu ích

Nếu request burst trong 50 ms rồi trở lại bình thường, queue nhỏ có thể hấp thụ spike. Nhưng nếu arrival rate cao hơn capacity trong hàng phút, queue chỉ **dồn nợ latency**.

### 26.3. Queue delay thuộc SLO

Nếu queue wait là 180 ms và query execution 20 ms, người dùng đã phải đợi hơn 200 ms. Monitor cần tách hai thành phần để không báo “DB query chỉ 20 ms nên không có vấn đề”.

## 27. Adaptive concurrency limiting: điều chỉnh theo tín hiệu đo

Giới hạn cố định như §maxInFlight=40§ đơn giản và dễ dự đoán, nhưng capacity thực tế có thể thay đổi theo query mix, read/write quorum, partitions và node failures.

Một **adaptive limiter** có thể tăng/giảm concurrency dựa trên:

- Latency tối thiểu/đường cơ sở.
- Queue wait hoặc dấu hiệu saturation.
- Error/throttle rate.
- In-flight requests và completed throughput.
- Tỷ lệ deadline expired.

### 27.1. Một hướng điều chỉnh đơn giản

Ví dụ ý tưởng, **không phải thuật toán production đầy đủ**:

~~~text
Every evaluation window:
  if latency stable AND rejection low AND queue empty:
       cautiously increase concurrency limit
  else if p95/p99 rises sharply OR throttling increases:
       reduce limit faster
~~~

Một số thuật toán có tinh thần additive increase/multiplicative decrease (AIMD) hoặc gradient/latency-based. Phải kiểm tra stability, sampling, fairness và impact khi traffic thấp.

### 27.2. Rủi ro oscillation

Nếu mọi pod cùng tăng limit khi latency tốt và cùng giảm khi DB chậm, toàn cluster có thể dao động:

~~~text
Increase -> saturation -> decrease -> low latency
-> increase again -> saturation ...
~~~

Cần smoothing, step size hợp lý, hysteresis, jitter và có thể **budget coordinator** để tránh các instance phản ứng đồng loạt.

### 27.3. Adaptive concurrency không thay global quota

Mỗi pod tự điều chỉnh từ 40 lên 100 có thể làm total concurrency tăng vượt ngân sách khi autoscaling. Adaptive limiter cần một **hard cap và hệ thống visibility toàn cluster**.

### 27.4. Không tối ưu chỉ vì throughput

Limiter có thể thấy throughput tăng khi cho nhiều queries đồng thời, nhưng p99 và error rate xấu hơn. Đích tối ưu là **throughput hữu ích trong SLO**, không phải số attempts được gửi cao nhất.

## 28. Bulkhead phân lớp và công bằng giữa tenants

Nếu toàn service chỉ có một semaphore 100 permits, một batch export có thể chiếm toàn bộ. Interactive Order reads bị từ chối dù cần ít tài nguyên.

Một thiết kế tham khảo:

~~~text
Global DB permits: 150
  |
  +-- interactive reads: max 100
  +-- critical writes:  max 60
  +-- background jobs:  max 20
~~~

Các giới hạn lớp **không cộng độc lập** thành 180 active operations; tất cả còn phải đi qua global limit 150. Ví dụ còn lại chỉ nói cách tổ chức, không phải config có sẵn của driver.

### 28.1. Acquire hai tầng

~~~text
1. Acquire global permit.
2. Acquire class-specific permit.
3. Execute operation.
4. Release class permit.
5. Release global permit.
~~~

Phải có cùng thứ tự acquire trong mọi code path và release nếu bước sau thất bại để tránh leak/deadlock.

### 28.2. Deadlock vì giữ permit khi chờ loại permit khác

Ví dụ service A giữ 100 global permits rồi chờ class permits chưa rảnh; service B cần global permit để giải phóng class-dependent work. Nếu permit graph tạo vòng chờ, hệ có thể deadlock. Cần thiết kế acquisition order, timeout và khả năng hủy.

### 28.3. Tenant quotas

Per-tenant rate limits/concurrency quotas giúp hạn chế một tenant chiếm tài nguyên của tenants khác. Cần:

- Chính sách default cho tenant chưa biết.
- Giới hạn số bucket/tenant states trong RAM.
- Eviction của idle tenant state.
- Quota tier rõ, audit và metrics.
- Fairness khi tenants có trọng số khác nhau.

### 28.4. Không mặc định FIFO là công bằng đủ

Một queue FIFO dài chứa 10.000 tasks từ tenant A có thể khiến một request tenant B chờ rất lâu. Per-tenant queues/weighted fair queuing hoặc admission quotas có thể phù hợp hơn, nhưng phức tạp và cần được đo.

## 29. SLO-driven capacity planning

Giả sử SLO:

~~~text
GET /orders/{id}:
  p99 < 250 ms
  error rate < 0.1% under expected load

POST /orders/{id}/confirm:
  p99 < 500 ms
  no duplicate business transition

Background analytics:
  completed within 20 minutes
~~~

Không nên dùng một pool/queue/retry policy giống hệt cho ba workload trên:

- Interactive GET cần độ trễ thấp, queue rất ngắn hoặc fast-fail.
- Critical write cần idempotency/CAS, ngân sách timeout hợp lý và outcome reconciliation.
- Background analytics có thể chờ/giảm tốc lâu hơn nhưng không được hút hết DB capacity.

### 29.1. Các bước tính công suất

1. Đo arrivals/s và concurrency theo endpoint.
2. Tách read/write/batch và hot keys.
3. Đo operation latency **khi DB chưa saturated**.
4. Dùng Little’s Law ước lượng in-flight trung bình ở từng scope.
5. Đo throughput/latency/error tại nhiều mức concurrency, tìm điểm bắt đầu queueing mạnh.
6. Chọn limit có headroom cho failover/bursts.
7. Phân bổ pool/permits theo **max pods khi rollout**, không chỉ pods hiện tại.
8. Xác minh reconnect/connection creation rate khi scale.
9. Load test với driver và consistency mode thực tế.
10. Quan sát business SLO và idempotency khi retries/cancellations.

### 29.2. Không dùng công thức để thay load test

Little’s Law là quan hệ trung bình. Capacity của NoSQL còn phụ thuộc data locality, replica selection, compaction, network, transaction contention và data model. Có thể bắt đầu từ ước lượng, nhưng phải **đo thực tế**.

### 29.3. Tính số permits theo service time

Nếu database hoàn tất trung bình 800 operations/s tại thời gian xử lý 50 ms:

\[
L=800\times0{,}05=40
\]

Một bulkhead 40 concurrent operations có thể là **mốc bắt đầu khảo sát**, không phải cấu hình chứng minh tối ưu. Nếu p99 vượt deadline, có thể cần limit thấp hơn hoặc tối ưu query; nếu multiplex/parallel DB capacity khác giả định, giới hạn cũng khác.

## 30. Metrics và dashboard vận hành

### 30.1. Metrics lớp HTTP/admission

| Metric | Mục đích |
| --- | --- |
| §incoming_requests_total§ | Arrival rate theo endpoint |
| §admitted_requests_total§ | Lượng đã nhận |
| §overload_rejections_total§ | Shed vì capacity |
| §rate_limit_rejections_total§ | Shed vì quota |
| §inflight_requests§ | Work đang chạy |
| §request_queue_depth§ | Hàng đợi đầu vào |
| §request_queue_wait_ms§ | Thời gian chờ |
| §request_end_to_end_latency_ms§ | Trải nghiệm người dùng |
| §deadline_exceeded_total§ | Quá deadline |
| §client_cancellations_total§ | Client bỏ request |

### 30.2. Metrics lớp driver/pool

| Metric | Mục đích |
| --- | --- |
| §db_pool_max_connections§ | Cấu hình pool theo scope |
| §db_pool_open_connections§ | Sockets đang mở |
| §db_pool_active_connections§ | Connections in use |
| §db_pool_idle_connections§ | Connections idle |
| §db_pool_pending_acquires§ | Hàng chờ lấy connection |
| §db_pool_acquire_wait_ms§ | Pool wait latency |
| §db_connections_created_total§ | Connection churn |
| §db_connection_creation_failures_total§ | TLS/auth/network issues |
| §db_operations_inflight§ | Requests gửi chưa hoàn tất |
| §db_operation_latency_ms§ | DB call latency |
| §db_operation_timeout_total§ | Timeouts |
| §db_retry_attempts_total§ | Attempts do retry |
| §db_speculative_attempts_total§ | Attempts song song nếu có |
| §db_circuit_breaker_state§ | OPEN/HALF_OPEN/CLOSED |

Tên metric thực phụ thuộc instrumentation driver/Micrometer/OpenTelemetry. Không phải mọi driver đều xuất đầy đủ các biến này; cần custom wrappers nếu thiếu.

### 30.3. Metrics lớp database

- CPU/memory/GC/server threads/event loops.
- Active queries/coordinators/replica lag.
- Per-node/partition/shard throughput.
- Hot key/partition throttling.
- Disk I/O, compaction, tombstones, background operations.
- Open connections theo node.
- Query plan/fan-out và long-running operations.
- Lock/transaction conflicts, quorum failures.
- Database-side latency distribution.

### 30.4. Bốn đồ thị nên xem cùng nhau

~~~text
Top: HTTP logical QPS and p99
Second: In-flight count and bulkhead rejections
Third: Pool active/pending/acquire-wait
Fourth: DB server throughput/throttle/latency
~~~

Nếu p99 tăng cùng pending acquire nhưng DB throughput đứng yên, cần điều tra pool hoặc backend bottleneck. Nếu p99 tăng cùng retry attempts, cần xem retry storm. Nếu chỉ một shard bị throttle, tăng global pool ít có ích.

### 30.5. Một biểu thức khuếch đại retry

\[
\text{Retry amplification}
= \frac{\text{DB RPC attempts}}{\text{logical DB operations}}
\]

Ví dụ 12.000 attempts cho 10.000 logical operations:

\[
\frac{12000}{10000}=1{,}2
\]

Nếu chưa định nghĩa “logical DB operation” nhất quán, metric này có thể vô nghĩa. Tránh cộng attempts từ nhiều operations khác nhau thành một.

### 30.6. Logging có giới hạn cardinality

Không gắn raw userId/orderId/tenantId vào metric labels nếu có hàng triệu giá trị. Dùng operation class, shard/node, error reason và sampled traces có request IDs với kiểm soát dữ liệu nhạy cảm.

## 31. Các dấu hiệu phân biệt bottleneck

| Triệu chứng | Giả thuyết | Bước xác minh |
| --- | --- | --- |
| Pool active=max, pending tăng, DB CPU thấp | Pool limit quá thấp hoặc leaks/long-held connections | Acquisition time, lifetime, traces |
| Pool còn idle, DB p99 cao | Backend/hot key/query issue | Per-shard latency, query shape |
| CPU API thấp, requests timeout | Blocking waits hoặc downstream saturation | Thread dumps, queue/pool wait |
| CPU API cao, DB nhanh | Serialization/compression/CPU tasks | Profiling, GC |
| Tăng pods rồi DB tệ hơn | Global concurrency tăng quá mức | Pods×pool/permits, retries |
| Reconnect failures sau rollout | Startup connection storm | Creation rate, TLS/auth logs |
| Một tenant chậm, tenants khác ổn | Hot partition/tenant quota | Per-tenant load, partition health |
| Nhiều 429 nhưng DB khỏe | Admission quá chặt hoặc mapping quota sai | Rejection vs utilization |
| Không có 429 nhưng p99 hàng giây | Queue không bounded, timeout quá dài | Queue depth/wait |
| Retry rate tăng sau failover | Client/SDK retry storm | Error classification and backoff |
| Open connections tăng mãi sau traffic | Client/session/cursor leak | Heap/thread dump, pool metrics |
| Dư nhiều connections nhưng low throughput | Lock contention hoặc serial bottleneck | Transaction conflicts, hot keys |
| Async memory tăng nhưng thread count ổn | Unbounded futures/buffers | In-flight tasks, heap retained |
| Throttle dù tổng cluster còn capacity | Per-partition/table/tenant service quota | Service metrics and key distribution |

### 31.1. Diagnose từ ngoài vào trong

Một trình tự hữu ích:

1. HTTP requests/s, error codes, p95/p99.
2. Admission rejections, in-flight, queue wait.
3. Executor queue depth, worker utilization, thread blocking.
4. Driver pool acquired/pending/creation rate.
5. DB attempts, retries, speculative requests.
6. Per-node/partition latency và throttling.
7. Query shape, index, transaction duration.
8. Resource leaks, GC, network and connection churn.

Không tuyên bố “cần tăng maxPoolSize” trước khi xác định **hàng đợi đầu tiên và tài nguyên thực đang saturated**.

## 32. Kiểm thử tải và fault injection có kiểm soát

Để lựa chọn giới hạn đồng thời và connection pool, cần biết **hệ thực sự phản ứng như thế nào khi tăng tải hoặc mất thành phần**. Các bài kiểm thử nên chạy trên môi trường riêng, dữ liệu giả và topology càng gần production càng hữu ích. Không gây network partition hay kill database production chỉ để kiểm tra.

### 32.1. Baseline: đo hệ khi chưa quá tải

1. Tạo dữ liệu đại diện: số partition, kích thước document, indexes, hot keys.
2. Chạy query mix tương tự traffic: read/write, transactions, scans.
3. Warm up JIT, connection pools và caches theo policy.
4. Giữ tải ổn định ở mức vừa phải.
5. Ghi p50/p95/p99, pool acquire latency, DB execution time, active connections, CPU/IO.
6. Xác định baseline trước khi thay concurrency limit.

**Không đo chỉ một loại point read rồi suy capacity cho một workload nhiều writes/transactions.**

### 32.2. Step-load test

Tăng arrivals từng bậc, ví dụ:

~~~text
500 req/s for 5 min
750 req/s for 5 min
1000 req/s for 5 min
1250 req/s for 5 min
1500 req/s for 5 min
~~~

Đo:

- Throughput hữu ích thực sự hoàn thành.
- p95/p99 và queue wait.
- Saturation của resource.
- Số load-shed responses và rate of timeouts.
- Retry amplification.
- Tình trạng downstream database.

Tìm vùng mà **latency bắt đầu tăng nhanh hơn throughput**. Sau đó chọn concurrency/rate limit có headroom và phù hợp SLO.

### 32.3. Spike/burst test

Cho arrivals tăng gấp 3 trong 10–30 giây rồi trở về bình thường. Kiểm tra:

- Queue depth không tăng vô hạn.
- Hệ reject sớm khi vượt ngân sách.
- Backlog tiêu dần và p99 phục hồi.
- Không có reconnect storm hoặc hàng nghìn requests còn chạy sau khi client đã timeout.

### 32.4. Soak test

Chạy tải gần mức dự kiến trong nhiều giờ. Quan sát:

~~~text
Active connections return to baseline after quiet period.
Heap retained objects do not grow without bound.
In-flight and queue-depth gauges settle.
Threads and event loops remain bounded.
No gradual permit leakage or pool acquire starvation.
~~~

Nếu metrics tăng dần sau mỗi vòng GC/traffic burst, cần điều tra leaked cursors, unclosed sessions, subscriptions hoặc futures giữ references.

### 32.5. Slow database test

Giả lập backend latency tăng từ 20 ms lên 500 ms. Cùng request rate, Little’s Law cho thấy in-flight demand tăng mạnh.

Kiểm tra:

- Bulkhead ngăn in-flight vượt giới hạn.
- Deadline/bounded queue không cho thời gian chờ tăng vô hạn.
- Circuit breaker có policy probe an toàn.
- Retry không tăng tải vào DB đã chậm.
- Critical writes có idempotency/unknown outcome path.

### 32.6. Failover/rebalance test

Giả lập một leader/replica failover hoặc thay topology theo test setup:

1. Quan sát DNS/topology refresh của driver.
2. Connection creation/reconnect rate.
3. In-flight request outcomes: success, known failure, unknown.
4. Retry policy và circuit breaker state.
5. Concurrency giới hạn ở mức an toàn.
6. Query/transaction correctness sau recovery.

Nếu driver giữ stale connections một thời gian, không được xây ứng dụng chỉ dựa vào TCP §connected=true§ để kết luận query sẽ thành công.

### 32.7. Autoscale test

Chuyển từ 5 pods → 20 pods, mỗi pod có pool và bulkhead:

- Có vượt connection budget DB?
- Có thấy TLS/auth startup storms?
- Per-pod limiter có khiến tổng in-flight tăng gấp 4 không?
- Rollout old+new pods có tạo peak ngoài dự kiến?
- Global quota/fairness còn hiệu lực không?

### 32.8. Timeout/cancellation test với writes

1. Client gửi một write có logicalOperationId.
2. Server commit nhưng response bị mất trong lab.
3. Client deadline expired.
4. Retry path chạy theo policy.
5. Kiểm tra side effect chỉ được áp theo business invariant, hoặc outcome UNKNOWN/PENDING được đối soát.

Đây không chỉ là kiểm thử performance: **khi tải cao, retry/cancellation có thể biến thành lỗi dữ liệu nếu code không có idempotency**.

### 32.9. Noisy tenant test

Cho tenant A gửi 90% traffic, tenant B gửi 10%:

- Rate limit toàn hệ có đủ bảo vệ B?
- Per-tenant quotas có làm A thua hợp lý?
- Một hot partition của A có lây latency sang B không?
- Bộ đệm có fairness không?

### 32.10. Bounded executor test

Gửi hơn §workers+queueCapacity§ tasks để kích hoạt §RejectedExecutionException§. Kiểm tra:

- Request được ánh xạ thành response overload rõ.
- Không chạy blocking DB trên event-loop caller.
- Queue memory không vượt giới hạn.
- Không rò permit khi submit/task bị reject.

## 33. Anti-pattern và cách sửa

| Anti-pattern | Tác hại | Hướng khắc phục |
| --- | --- | --- |
| Tạo client mỗi request | Connection churn, leaks, auth overhead | Application-scoped client |
| Không close cursor/session | Pool exhausted, memory/transaction leak | try-with-resources/finally |
| Close shared client sau mỗi operation | Các requests khác bị lỗi | Owner-managed lifecycle |
| Pool cực lớn để “tăng throughput” | DB overload, failover storms | Capacity-budgeted max |
| MinIdle quá cao trên nhiều pods | Idle sockets và startup surge | Warm-up theo nhu cầu |
| Thread pool có unbounded queue | Latency debt, OOM | Bounded queue + rejection |
| Semaphore limit không release khi exception | Permanent saturation | finally/completion handler |
| Giới hạn per-pod nhưng quên max pods | Global overload sau autoscale | Cluster budget |
| Rate limit thay thế concurrency limit | In-flight vẫn tăng khi DB chậm | Kết hợp cả hai |
| Concurrency limit thay rate limit | Fast operations vẫn có QPS rất lớn | Thêm token bucket/quota |
| Retry mọi timeout write | Double business effect | Idempotency/outcome lookup |
| Nhiều tầng retry không phối hợp | Retry storm | Shared attempt/deadline budget |
| Đợi permit vô hạn | Requests treo dài | Bounded wait/deadline |
| Đặt timeout từng bước độc lập | End-to-end vượt SLO | Propagate remaining deadline |
| Xem cancellation là rollback | DB có thể đã commit | Unknown outcome semantics |
| Dùng virtual threads bỏ hết giới hạn | Quá nhiều in-flight requests | Admission/bulkhead |
| Blocking DB call trong event loop | Stall nhiều unrelated requests | Async driver/bounded offload |
| Async future fan-out vô hạn | Queue/buffer memory pressure | Concurrency-controlled pipeline |
| Redis blocking commands chung với GET pool | Pool starvation | Separate connections/roles |
| Cassandra retry/speculation không xét idempotence | Duplicate effects, added load | Driver policy + operation semantics |
| Tăng pool khi bottleneck là hot partition | Throttle nặng hơn | Partition-key/data-model fix |
| Query scan quá lớn trong interactive endpoint | Giữ resource lâu | Pagination/batch/index redesign |
| Một bulkhead chung cho mọi traffic | Batch chiếm permits của checkout | Critical/batch isolation |
| Chỉ đo average latency | Không thấy tail/queue | p95/p99 + queue metrics |
| Chỉ nhìn database CPU | Bỏ qua pool/client wait | End-to-end tracing |
| Healthcheck chỉ ping DB | Không biết workflow saturated | Dependency readiness và SLO metrics |
| Chưa warm/test reconnect | Thất bại khi rollout/failover | Controlled warm-up + chaos lab |

## 34. Bài tập thực hành

### Bài 1 — Phân biệt concurrency và rate

Một service có rate limit 2.000 requests/s, còn mỗi DB request kéo dài trung bình 200 ms khi backend chậm:

1. Ước lượng average in-flight theo Little’s Law nếu thông lượng ổn định ở 2.000/s.
2. Rate limit này có chặn in-flight tại 100 không?
3. Đề xuất thêm một concurrency limit.
4. Nếu mỗi request tạo hai DB operations, cần phân biệt loại concurrency nào?

### Bài 2 — Little’s Law trong hai phạm vi

HTTP QPS = 1.000/s, HTTP mean latency 120 ms. Mỗi request có một DB query mean in-flight duration 40 ms.

1. Tính average HTTP in-flight.
2. Tính average DB operations in-flight nếu thông lượng DB bằng HTTP QPS.
3. Vì sao hai con số khác nhau?
4. Nếu pool acquisition wait 80 ms được thêm vào DB-operation duration, phép tính phải đổi thế nào?

### Bài 3 — Autoscale và connection budget

Database có ngân sách 900 application connections. Hệ có 15 API pods ở bình thường, 25 pods khi rollout; ngoài ra 100 connections dành cho batch.

1. Ngân sách còn cho API khi rollout?
2. Mốc per-pod average budget là bao nhiêu nếu chia đều?
3. Vì sao driver per-server pool làm phép chia này chỉ là ước lượng?
4. Cần reserve thêm cho monitoring và hot failover không?

### Bài 4 — Semaphore leak

Đoạn code:

~~~java
if (permits.tryAcquire()) {
    return repository.findById(id);
}
throw new OverloadedException();
~~~

1. Khi nào permit bị leak?
2. Viết lại bằng §try/finally§.
3. Nếu §tryAcquire()§ trả false, có được release permit không?
4. Nếu async DB call trả future, release đặt ở đâu?

### Bài 5 — Queue không giới hạn

Executor có 16 threads và §LinkedBlockingQueue§ không ghi capacity.

1. Khi requests đến nhanh hơn năng lực xử lý, điều gì xảy ra?
2. Vì sao chỉ đặt §maximumPoolSize=16§ không kiểm soát memory?
3. Thay bằng §ArrayBlockingQueue(64)§ sẽ thay failure mode thế nào?
4. Cần ánh xạ rejection sang HTTP response nào theo contract?

### Bài 6 — Virtual threads

Một batch 100.000 IDs tạo 100.000 virtual threads, tất cả cùng muốn query NoSQL.

- JVM có thể không cần 100.000 platform threads, nhưng điều gì vẫn bị giới hạn?
- Dùng bulkhead và bounded producer thế nào?
- Nếu một query timeout sau commit write, virtual thread có giải quyết outcome không?

### Bài 7 — MongoDB Java pool

Một §MongoClient§ kết nối replica set 3 servers, config §maxSize=50§.

1. Có chắc toàn bộ cluster client mở tối đa 50 sockets không?
2. §maxWaitTime§ điều khiển tầng nào?
3. Vì sao cursor phải được close?
4. Vì sao không nên tạo §MongoClient§ trong từng REST controller request?

### Bài 8 — Cassandra async

Service gọi §session.executeAsync§ cho 50.000 statements rồi mới chờ futures:

1. Tại sao “async” không có nghĩa ít memory/in-flight?
2. Driver có thể multiplex connections không?
3. Nếu bật speculative execution, RPC attempts thay đổi ra sao?
4. Những writes nào cần quan tâm idempotence?

### Bài 9 — Redis pool

Một pool 20 connections dùng cho cả §GET§ nhanh và blocking subscriptions.

- Vì sao GET có thể phải chờ dù Redis khỏe?
- Nên tách connection roles thế nào?
- Jedis pooled connection nên được trả về pool khi nào?
- Pipelining có thể làm buffer memory tăng thế nào?

### Bài 10 — DynamoDB HTTP client

Một service đặt §maxConcurrency=100§ cho HTTP client, nhưng chỉ một partition key bị throttling.

1. Tăng lên 500 có chắc cải thiện throughput không?
2. Phân biệt HTTP pending acquisition và service-side throttling.
3. Retry mode và attempt budget ảnh hưởng thế nào?
4. Cần thay partition key/workload ra sao?

### Bài 11 — Deadline

HTTP deadline = 500 ms. Request đã chờ admission 150 ms, đợi pool thêm 100 ms, còn cần một DB call và serialize result.

1. Còn bao nhiêu thời gian end-to-end lý thuyết?
2. Có được bắt đầu một DB call có timeout độc lập 500 ms không?
3. Nếu client timeout trong lúc DB write, outcome là gì?
4. Tại sao dùng monotonic elapsed time trong cùng process?

### Bài 12 — Retry storm

Gateway retry tối đa 3 lần; application service retry 4 lần; DB SDK retry 3 lần.

- Số attempts tối đa ở đường sâu nhất nếu mọi tầng đều chạy đủ?
- Nếu 1.000 logical requests/s, tải xấu nhất có thể ra sao?
- Đề xuất shared retry budget, backoff và circuit breaker.
- Những operation nào không nên retry mù?

### Bài 13 — Rate limiter local

Có 10 pods, mỗi pod token bucket 500 tokens/s.

1. Có bảo đảm global rate ≤500/s không?
2. Upper bound lý thuyết ở mức ổn định là bao nhiêu nếu pods có đủ traffic?
3. Muốn global quota 500/s, các hướng thiết kế nào?
4. Distributed limiter trên hot path có failure mode gì?

### Bài 14 — Hot key

Toàn cụm NoSQL có 70% CPU rảnh nhưng một partition key phục vụ 90% write traffic.

1. Vì sao tăng max pool có thể làm throttle nặng hơn?
2. Một sharded counter có giúp không?
3. Vì sao không dùng sharded eventual counter làm authority cho stock cuối cùng?
4. Cần metrics per-partition nào?

### Bài 15 — Adaptive limiter

Limiter tăng concurrent limit từ 40 lên 100. Throughput tăng 10% nhưng p99 tăng từ 100 ms lên 1.000 ms.

- Mục tiêu tối ưu theo SLO nên là gì?
- Giảm limit dựa trên signal nào?
- Làm sao tránh oscillation?
- Có nên cho từng pod tự tăng không giới hạn?

### Bài 16 — Tìm leak

Sau 3 giờ tải, requests/s trở về 0 nhưng:

~~~text
pool active = 50/50
pending acquire = 0
open cursors = many
heap gradually increases
~~~

1. Có những giả thuyết gì?
2. Vì sao active connections không về baseline?
3. Dùng tracing/thread dump/driver metrics thế nào?
4. Sửa vòng đời cursor/session ở đâu?

### Bài 17 — Bounded retry với write

Client gửi §reserveInventory(requestId=R42)§, DB commit rồi response mất.

1. Tại sao timeout không chứng minh no-op?
2. Nếu retry với request ID mới, hậu quả?
3. Thiết kế idempotency ledger/conditional inventory reservation.
4. Nếu SDK cũng retry tự động, application cần biết gì?

### Bài 18 — Thiết kế end-to-end

Một dịch vụ có:

~~~text
GET /orders/{id}:  2000 req/s, p99 target <250 ms
POST /orders:      300 req/s, p99 target <500 ms
Batch export:      100 jobs/min, can finish in 10 min
12–24 pods
NoSQL backend with hot tenants and failover events
~~~

Hãy đề xuất:

1. Rate budget theo endpoint/tenant.
2. Concurrency bulkheads global + per class.
3. Driver connection pool sizing theo 24 pods và rollout.
4. Bounded executor/async queue/cancellation.
5. Timeout/deadline cho interactive vs batch.
6. Idempotency và retry semantics của POST.
7. Monitoring dashboards/alerts.
8. Fault injection khi DB chậm, hot key, failover và reconnect.

### Bài 19 — Java review: bốn lỗi trong một handler

~~~java
public Order process(String id) {
    ExecutorService executor = Executors.newFixedThreadPool(100);
    MongoClient client = MongoClients.create(uri);
    var cursor = client.getDatabase("app")
        .getCollection("orders").find().iterator();

    // Scan all orders, then pick the matching one.
    Order order = findInCursor(cursor, id);
    executor.submit(() -> sendMetrics(order));
    return order;
}
~~~

Hãy tìm ít nhất:

- Những lifecycle leaks.
- Vì sao scan toàn collection có thể làm latency cao?
- Vì sao tạo executor mỗi request có hại?
- Vì sao một shared client/repository + targeted query tốt hơn?
- Vì sao metrics async cũng cần queue/worker giới hạn?

### Bài 20 — Test plan

Thiết kế một lab gồm ba stages:

1. Tải ổn định, chọn concurrency limit tối ưu theo p99.
2. DB latency tăng 10 lần và nửa số server không reachable.
3. Autoscale từ 8 lên 24 pods trong lúc SDK đang retry.

Hãy định nghĩa:

- Giới hạn in-flight/pending across all pods.
- Cách không vượt database connection budget.
- Expected 429/503/retry behavior.
- Assertions về memory/connection leaks sau recovery.
- Assertions về unknown write outcome và idempotency.
- Metrics/traces cần thu.

## 35. Gợi ý giải một số bài tính và tình huống

### 35.1. Bài 1 — Average concurrency

Với 2.000 requests/s và mean duration 0,2 s trong cùng phạm vi đo:

\[
L=2000\times0{,}2=400
\]

Rate limit 2.000/s **không** giới hạn in-flight ở 100. Nếu database chỉ chịu khoảng 100 concurrent operations ổn định ở SLO được chọn, cần bulkhead khoảng phạm vi đó (và tiếp tục đo); chờ hoặc shed khi hết capacity.

### 35.2. Bài 2 — Phân biệt hai thời gian

HTTP average in-flight:

\[
L_{\text{http}}=1000\times0{,}120=120
\]

DB average in-flight:

\[
L_{\text{db}}=1000\times0{,}040=40
\]

Hai con số khác vì scope của \(W\) khác nhau. Nếu DB operation duration tăng do pool wait, phải xác định đang tính **in-flight thực thi trên DB** hay **toàn thời gian một DB call chờ và chạy**.

### 35.3. Bài 3 — Budget trong rollout

Nếu 900 application connections là ngân sách còn lại trước khi trừ batch, dành 100 cho batch:

\[
900-100=800
\]

Tại 25 pods:

\[
\left\lfloor800/25\right\rfloor=32
\]

32 chỉ là **mốc chia đều ban đầu**. Per-server pools, monitoring sockets, nhiều clients, topology failover và workload khác có thể yêu cầu hạn mức thấp hơn hoặc phân bổ khác.

### 35.4. Bài 12 — Retry nhiều tầng

Gateway 3 × service 4 × SDK 3 có thể dẫn tới:

\[
3\times4\times3=36
\]

attempts sâu nhất trong tình huống mỗi tầng lặp hết số lần và tất cả gọi tầng tiếp theo. 1.000 logical requests/s khi bị lỗi đồng loạt có thể khuếch đại đến **36.000 attempts/s** theo mô hình này, lớn hơn rất nhiều request rate ban đầu. Thực tế phụ thuộc timeout, SDK behavior, retry budget và cách các tầng phân phối requests.

### 35.5. Bài 13 — Limiter theo pod

10 pods × 500 tokens/s cho phép **tới khoảng 5.000 tokens/s** ở trạng thái ổn định nếu tất cả pods đủ traffic và dùng rate limit local độc lập. Đây **không** phải global quota 500/s.

Để có global quota, có thể dùng gateway limiter, distributed token bucket có hợp đồng nhất quán, hoặc phân bổ mỗi pod một phần budget có thể cập nhật khi scale; mọi giải pháp đều có trade-offs về latency, availability và fairness.

### 35.6. Bài 4 — Permit và exception

~~~java
if (!permits.tryAcquire()) {
    throw new OverloadedException("BUSY");
}
try {
    return repository.findById(id);
} finally {
    permits.release();
}
~~~

Chỉ release sau khi acquire thành công, cả khi DB call throw. Với async API, release khi underlying operation hoàn tất hoặc được xác minh đã không bắt đầu, không release ngay sau khi trả future.

### 35.7. Bài 17 — Write timeout

Nếu DB commit rồi client timeout, retry §reserveInventory§ bằng ID khác có thể reserve hai lần. Giữ cùng §requestId=R42§ và dùng ledger/conditional reservation phù hợp, trong phạm vi atomicity được product contract bảo đảm. Khi không biết outcome, trạng thái phải là **UNKNOWN/PENDING hoặc tra lại nguồn**, không tuyên bố FAILED chắc chắn.

## 36. Runbook khi p99 DB đột ngột tăng

Một runbook đơn giản giúp đội vận hành phản ứng có trật tự, tránh tăng pool size theo bản năng.

### Bước 1 — Phân biệt spike và sustained overload

Xem arrival rate, request mix, p99 và error rate trong 5–15 phút gần nhất. Có deploy, autoscale, batch jobs hoặc query shape mới không?

### Bước 2 — Tìm hàng đợi đầu tiên

~~~text
HTTP admission queue?
Executor queue?
Driver pool pending acquisitions?
Driver in-flight requests?
Coordinator queue?
One hot shard/partition?
~~~

Hàng đợi **xuất hiện đầu tiên** thường là manh mối tốt để xác định tài nguyên đang tranh chấp, nhưng vẫn cần hiểu luồng request thực tế.

### Bước 3 — Ngăn khuếch đại lỗi

- Hạn chế retries theo budget.
- Shed noncritical batch/analytics.
- Giảm concurrency nếu đang bơm quá nhiều DB operations.
- Kiểm tra circuit breaker state.
- Giữ critical writes có idempotency, tránh retry mù.

### Bước 4 — Chẩn đoán backend

Xem hot partitions, server-side timeouts, query fan-out, compaction, transactions, replica lag, throttling và authentication/connectivity issues.

### Bước 5 — Phục hồi có kiểm soát

- Không mở toàn bộ permits đồng thời sau outage.
- Tăng capacity/limit có bước nhỏ và metrics.
- Cho background jobs hồi phục theo budget riêng.
- Đối soát những writes timeout có unknown outcome.
- Theo dõi queue drain và tail latency về mức bình thường.

### Bước 6 — Hậu kiểm

Thu:

~~~text
What changed?
Which queue first saturated?
How many logical operations and DB attempts occurred?
Did retry amplify the outage?
Were any connections/sessions leaked?
Were unknown write outcomes reconciled?
Which SLOs and tenants were affected?
What limit/runbook/config should change?
~~~

## 37. Checklist triển khai Java NoSQL

### Phân bổ công suất

1. Đã xác định **logical QPS, DB operations/s và RPC attempts/s** chưa?
2. Có đo operation duration **bao gồm đúng scope** muốn tính concurrency chưa?
3. Có phân biệt average, p95 và p99 không?
4. Đã kiểm tra capacity theo shard/partition, không chỉ tổng DB chưa?
5. Có xác định ngân sách tổng **connections + in-flight** theo max pods/rollout không?
6. Đã tính background jobs, migrations, CDC và service khác dùng DB chưa?

### Admission và backpressure

7. Có concurrency limit/bulkhead trước tài nguyên đắt tiền không?
8. Có rate limit khi cần giới hạn throughput/quota không?
9. Có bounded queue và bounded wait time không?
10. Có fast-fail/429/503 theo API contract khi overload không?
11. Có fairness/tenant isolation nếu workload nhiều tenants không?
12. Bulkheads theo operation class có tổng hard cap không?
13. Nếu adaptive limit, có hard cap và chống oscillation không?

### Driver, pool và vòng đời

14. Database client/session được tạo **ở application scope** không?
15. Cấu hình §maxPoolSize§/§maxConcurrency§ được hiểu theo **driver scope** chưa?
16. Có biết driver tạo bao nhiêu per-server pools/monitoring connections không?
17. §minIdle§ và connection creation rate có an toàn lúc scale/failover không?
18. Cursors, sessions, transactions, subscriptions được đóng đúng không?
19. Semaphore permits luôn release trong §finally§ hoặc async completion không?
20. Executors và event loops được shutdown đúng vòng đời không?
21. Có tránh blocking DB work trên event-loop threads không?
22. Có giới hạn async/virtual-thread task creation không?

### Deadline, retry và correctness

23. Có một **overall request deadline** được truyền đến từng tầng không?
24. Pool wait, connect, socket/read, operation timeout có vai trò rõ ràng không?
25. Retry không tự reset deadline phải không?
26. SDK auto-retry/speculative execution đã được tính vào attempt budget chưa?
27. Có exponential backoff + jitter khi phù hợp không?
28. Business conflicts được phân biệt với transient failures không?
29. Unknown write outcome có idempotency/conditional update/outcome lookup không?
30. Có circuit breaker nhưng không làm mất định nghĩa outcome của writes không?

### Quan sát và xác minh

31. Có metrics pool active/idle/pending/acquire wait không?
32. Có đo in-flight, queue depth, shed count và retry amplification không?
33. Có dashboard p99 theo endpoint, DB operation class và shard/tenant grouping không?
34. Có alert reconnect storms, leak và persistent saturation không?
35. Có load tests step/spike/soak, failover và autoscaling không?
36. Có fault-injection test khi response mất sau write commit không?
37. Có chọn SLO **throughput hữu ích** thay vì tối đa DB attempts không?

## 38. Một phương án kiến trúc tham khảo

Giả sử Order Service có REST API, 20 pods Java ở mức rollout cao nhất, MongoDB/Cassandra/Redis/DynamoDB là những backend tùy deployment. Một kiến trúc khởi đầu có thể:

~~~mermaid
flowchart TD
    LB["Load balancer"] --> HTTP["HTTP admission"]
    HTTP --> Q["Tenant / API rate budget"]
    Q --> G["Global per-pod DB bulkhead"]
    G --> R["Critical read bulkhead"]
    G --> W["Critical write bulkhead"]
    G --> B["Batch bulkhead"]
    R --> D["Shared NoSQL driver client / pool"]
    W --> D
    B --> D
    D --> DB["NoSQL backend / replicas / partitions"]
    HTTP --> REJ["Overload response when not admitted"]
    Q --> REJ
    G --> REJ
~~~

### 38.1. Một số giá trị minh họa

~~~yaml
deployment:
  maximumPodsDuringRollout: 20

db:
  connectionBudgetForThisService: 700
  # Per-pod sizing below is only a starting hypothesis.
  targetPoolConnectionsPerPod: 30

admission:
  globalDbInFlightPerPod: 60
  criticalReadInFlightPerPod: 40
  criticalWriteInFlightPerPod: 25
  batchInFlightPerPod: 10
  maxPendingRequestsPerPod: 20

timeouts:
  httpRequestBudgetMs: 500
  maxAdmissionWaitMs: 20
  maxConnectionAcquireWaitMs: 80

retry:
  overallAttemptBudget: 2
  useBackoffWithJitter: true
  requireIdempotencyForRiskyWrites: true
~~~

Đây là **mô hình cấu hình minh họa**, không phải file cấu hình chạy được của driver/framework. Đặc biệt, §globalDbInFlightPerPod=60§ có thể lớn hơn §targetPoolConnectionsPerPod=30§ nếu protocol multiplex requests; chỉ hợp lệ nếu driver/backend hỗ trợ và load test chứng minh. Per-class caps cùng dùng một global cap, không cộng độc lập.

### 38.2. Điều cần tùy chỉnh

- Backend là managed HTTP API hay self-managed cluster?
- Có bao nhiêu per-server pools?
- Reads có phân tán sang replicas không?
- Writes có yêu cầu quorum/transaction không?
- Traffic có hot keys/tenants không?
- SDK có retry/speculative execution không?
- Application dùng blocking threads, virtual threads hay reactive?
- Có operations cần read-your-writes, idempotency hay strict business consistency không?

Chỉ sau khi trả lời và đo thực tế mới biến các số minh họa thành production policy.

## Kết luận

Trong ứng dụng Java kết nối NoSQL, **khả năng phục vụ tải ổn định** không đến từ việc mở càng nhiều connections hoặc threads càng tốt. Nó đến từ việc xác định tài nguyên hữu hạn, đặt **ngân sách đồng thời và tốc độ nhận work có giới hạn**, kiểm soát hàng đợi, và quản lý đúng vòng đời client/session/connection.

Những ý chính cần ghi nhớ:

- **Concurrency khác QPS.** Rate limit kiểm soát arrivals, bulkhead kiểm soát active operations; một hệ chịu tải thường cần cả hai.
- **Little’s Law dùng trung bình và đúng phạm vi đo.** Nó giúp ước lượng in-flight work, không tự chỉ ra số connections tối ưu.
- **Connection không đồng nghĩa DB request.** Tùy driver có per-server pools, multiplexing, HTTP async transports và nhiều coordinator/replicas.
- **Một client/session cấp ứng dụng thường cần được tái sử dụng**, còn cursors, transactions và request-scoped resources phải được đóng đúng cách.
- **Pool size quá lớn có thể làm backend quá tải**; tăng pool không sửa được hot partition, transaction contention hoặc query scan chậm.
- **Bounded queue và load shedding bảo vệ SLO.** Queue vô hạn chỉ làm thời gian chờ, bộ nhớ và số timeout phình to.
- **Virtual threads và async APIs không tạo thêm database capacity.** Vẫn cần giới hạn in-flight và pending tasks.
- **Deadline phải xuyên suốt** từ admission đến DB và retry, không cộng dồn các timeout độc lập.
- **Retry cần budget, backoff, jitter và hiểu idempotency**; timeout sau write có thể là unknown commit outcome.
- **Autoscaling pods tăng tổng connections/in-flight** nếu không có global budget hoặc per-pod phân bổ phù hợp.
- **Đo hàng đợi đầu tiên bị nghẽn**, p95/p99, pool acquisition, retry amplification và per-partition throttling trước khi chỉnh cấu hình.
- **Kiểm thử failover, reconnect, spike và soak**, không chỉ benchmark point read trong trạng thái khỏe.

Một câu hỏi tốt khi tối ưu kết nối Java–NoSQL không phải “Tăng §maxPoolSize§ lên bao nhiêu?”, mà là: **“Tại mỗi tầng có bao nhiêu công việc đang chạy và đang chờ, tài nguyên nào thật sự đã bão hòa, ngân sách toàn cụm là bao nhiêu, và khi vượt giới hạn thì ứng dụng có từ chối/giảm tốc an toàn mà vẫn giữ được bất biến nghiệp vụ hay không?”**
