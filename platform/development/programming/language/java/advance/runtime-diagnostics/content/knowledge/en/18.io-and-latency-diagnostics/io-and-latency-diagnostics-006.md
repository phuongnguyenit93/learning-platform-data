# 18.6. Đối chiếu số request đang xử lý, pool, hàng đợi và tài nguyên phụ thuộc

## Mục tiêu

Một dịch vụ Java tăng **p95/p99 latency** thường đồng thời có nhiều request chưa hoàn tất, thread pool bận, queue dài hoặc phải chờ tài nguyên bên dưới (database, HTTP/gRPC, Redis, message broker). Nhưng các chỉ số ấy mô tả **những vị trí khác nhau của cùng một pipeline**. Muốn tìm nút thắt cần đối chiếu chúng **theo cùng cửa sổ thời gian, cùng phạm vi request, cùng thứ tự các tầng**, chứ không nhìn một metric độc lập.

Bài tập trung vào **I/O và độ trễ** trên Java 17+: từ yêu cầu đi vào dịch vụ, qua worker/executor và hàng đợi, đến connection pool cùng service phụ thuộc; cuối cùng trả kết quả, timeout hoặc lỗi. Mục đích là biết **request đang ở đâu, chờ cái gì, vì sao số request “đang xử lý” tăng, và khi nào nên backpressure thay vì tăng pool**.

### Kết quả cần nắm

- Phân biệt **in-flight request**, **active worker**, **executor queue**, **pending connection acquisition**, **leased/idle connections**, **downstream in-flight** và **dependency saturation**.
- Đọc đúng những chỉ số **instantaneous gauge** và **cumulative counter/histogram**; nhận biết việc cùng một request có thể xuất hiện ở nhiều tầng mà không được cộng thành số request riêng.
- Sử dụng nguyên lý **Little's Law** để kiểm tra quan hệ giữa throughput, số lượng đang xử lý và latency trong điều kiện phù hợp.
- Chẩn đoán các mẫu nghẽn: server executor, DB connection pool, DB query/lock, downstream HTTP, queue trước gateway, retry/fan-out và CPU/GC pressure.
- Thiết kế đo đạc đủ để phân biệt **thời gian chờ queue**, **thời gian chờ connection**, **thời gian I/O** và **thời gian xử lý thực tế**; có ví dụ Java 17+ chạy độc lập.

## 1. Sơ đồ request đi qua những đâu?

Một pipeline Java đồng bộ điển hình:

```text
Client
  |
  v
Load balancer / gateway   [accepted, queued, rejected, timed out]
  |
  v
HTTP server / ingress     [requests in-flight, request duration]
  |
  +--> dispatch / executor pool
  |       |
  |       +--> worker active?
  |       +--> executor queue waiting?
  |
  +--> business logic
          |
          +--> DB/HTTP/Redis client pool
          |       |
          |       +--> leased / active connections
          |       +--> idle connections
          |       +--> pending acquisition / acquire timeout
          |
          +--> downstream service
                  |
                  +--> in-flight calls / concurrency limit
                  +--> queue / CPU / DB / locks / errors / latency
  |
  v
Response success / error / cancellation / timeout
```

Không phải mọi kiến trúc có đúng đường này:

- **Servlet blocking:** một request thường giữ một worker khi thực thi/chờ I/O đồng bộ; nhưng async servlet có thể giải phóng worker mà request vẫn chưa hoàn thành.
- **Reactive/event-loop:** có thể có hàng nghìn request in-flight trong khi chỉ vài event-loop threads; **in-flight ≠ active threads**.
- **Fan-out:** một request gọi 3 downstream đồng thời hoặc nhiều lần retry, nên **3 downstream calls không tương đương 3 inbound requests**.
- **Streaming/long polling:** một request có thể còn mở trong thời gian dài mà ít dùng CPU/worker, phụ thuộc framework.
- **Shared pool:** scheduler/background jobs có thể dùng chung executor/connection pool với request; không được quy toàn bộ queue và CPU cho request HTTP.

Bước đầu tiên là **vẽ đúng luồng và ranh giới đo** của hệ thống đang điều tra, kể cả gateway/proxy và hệ thống phụ thuộc. Một metric tên “active” chỉ có ý nghĩa sau khi biết nó áp dụng cho request, thread, connection hay query.

## 2. Bảng đối chiếu các chỉ số quan trọng

| Metric | Cấp đo và định nghĩa thực tế | Câu hỏi nó trả lời | Không được suy ra |
| --- | --- | --- | --- |
| **Inbound in-flight requests** | Số request đã được service tính là nhận nhưng chưa hoàn tất tại thời điểm đo | Bao nhiêu request chưa trả kết quả? | Bao nhiêu thread đang chạy CPU hoặc bao nhiêu DB connection được dùng |
| **Request arrival rate** | Request mới/giây, dùng delta của counter theo thời gian | Tải đang đi vào nhanh đến đâu? | Tốc độ hệ thống thực sự xử lý thành công |
| **Completion/throughput rate** | Request kết thúc/giây (phân loại thành công/lỗi/timeout) | Hệ thống thoát backlog nhanh đến đâu? | Không tự nói request có đáp ứng SLA |
| **Executor active workers** | Worker đang chạy task; `ThreadPoolExecutor.getActiveCount()` là **ước lượng** | Có bao nhiêu task đang chiếm worker? | Worker ấy đang dùng CPU; có thể đang block chờ DB |
| **Executor queued tasks** | Task đã đưa vào work queue nhưng chưa bắt đầu chạy | Backlog trước worker lớn đến đâu? | Mọi task đều là inbound HTTP request |
| **Executor pool size/max** | Worker hiện có và cấu hình trần | Còn khả năng tăng worker không? | Pool được phép tăng là có tài nguyên downstream tương ứng |
| **Connection leased/active** | Connection được giao cho caller/đang dùng theo semantics từng client pool | Pool còn bao nhiêu connection sẵn sàng giao? | Tất cả connection đều đang chạy SQL hoặc truyền dữ liệu liên tục |
| **Connection idle** | Connection đã mở nhưng chưa được giao cho caller | Pool có capacity tức thời không? | Downstream không chậm, hoặc không có request chờ |
| **Pending acquisition** | Caller chờ lấy connection/permit từ pool | Có nghẽn trước khi gọi DB/remote không? | Downstream SQL/HTTP processing time tự động dài |
| **Downstream in-flight calls** | RPC/SQL/HTTP calls đang diễn ra trên một dependency | Dependency đang chịu concurrency bao nhiêu? | Cùng số inbound request do retry/fan-out |
| **Queue/pool wait duration** | Phân bố thời gian chờ từng stage | Stage nào tăng p95/p99? | Có thể cộng các percentile stage để ra p99 end-to-end |
| **Request end-to-end duration** | Từ ranh giới ingress đến response/error/cancel được ghi nhận | Người dùng chờ bao lâu ở scope service? | Tự phân chia được từng stage nếu không có spans |

**Gauge** (`in-flight`, `active`, `queued`, `pending`) là ảnh chụp tại thời điểm. **Counter** (`accepted_total`, `completed_total`, `rejected_total`, `timeout_total`) là số tích lũy; muốn có rate phải lấy **chênh lệch qua cửa sổ**, xử lý reset khi process restart. **Histogram** cho latency cho phép xem phân bố và tail latency; phải chắc metric chứa cả outcome mình muốn đo (success, error, timeout, reject hay không).

**Không cộng bừa:** một request có thể đồng thời thuộc `in-flight=1`, `active worker=1`, `connection pending=1`. Tổng ba số là 3 nhưng vẫn chỉ có **một inbound request**. Ngược lại một request đang chờ executor queue sẽ chưa xuất hiện trong worker active nhưng vẫn in-flight nếu scope HTTP đã nhận nó.

## 3. Ghép các metric bằng dấu thời gian và mẫu số phù hợp

Không so giá trị từ các cửa sổ/instance khác nhau: request rate lúc 10:00:00 và queue lúc 10:05:00 có thể mô tả những tải khác nhau; metrics theo pod không tự đồng nhất với metrics toàn cluster.

### 3.1. Chọn tập đo tối thiểu

Trong một cửa sổ ví dụ **30 giây** ở mỗi instance/pod:

1. **Ingress:** accepted rate, completed rate, success/error/timeout/reject rate, current in-flight, request duration p50/p95/p99.
2. **Application executor:** pool size, active workers, max, queue size/capacity, rejected count, task queue wait histogram và task execution duration.
3. **Dependency client pool:** active/leased, idle, max, pending waiters, acquisition duration/timeout, connection usage duration.
4. **Remote dependency:** RPC/SQL in-flight, p95/p99 latency, error/timeouts, server queue/DB locks/CPU/disk/connection limits khi có telemetry.
5. **Host/runtime:** CPU throttling, JVM CPU/GC, heap, thread count, I/O/network; tránh tưởng chờ CPU là chờ DB.
6. **Trace/log:** trace ID, attempt/retry count, cancellation/deadline, timestamp tại từng stage.

Gắn nhãn hợp lý theo service, instance, endpoint/route, dependency và **pool name**. Tránh tag theo request ID, user ID hoặc URL raw có độ đa dạng vô hạn (high cardinality); correlation ID nên ở tracing/log, không dùng làm metric label.

### 3.2. Little's Law: số request đang xử lý, throughput và latency

Trong **hệ thống ổn định**, ranh giới đo thống nhất và thời gian đủ dài:

```text
L = λ × W

L = số lượng công việc trung bình trong phạm vi đang đo
λ = tốc độ hoàn tất/đi vào trung bình (work items mỗi giây, khi ổn định)
W = thời gian trung bình mỗi item nằm trong phạm vi đó (giây)
```

Ví dụ **giả định** một endpoint xử lý ổn định **100 request/s**, thời gian nằm trong service trung bình **0,25 s**:

```text
L = 100 request/s × 0,25 s = 25 request in-flight (trung bình)
```

Nếu in-flight trung bình đo được là **120** thay vì **25** trong cùng phạm vi, trước khi quy là lỗi cần xem: latency tăng không? hai số có cùng khoảng thời gian/tập request không? tính cả long polling/cancel/streaming không? có burst hoặc backlog tăng khiến hệ thống **không ở steady state** không?

Áp dụng tương tự riêng cho **queue** nếu định nghĩa nhất quán: số task trong queue trung bình bằng throughput task × thời gian chờ queue trung bình, trong điều kiện ổn định. **Không dùng p99 trong công thức L = λW**, vì `W` phải là **trung bình** của thời gian tương ứng; lấy rate trung bình nhân p99 không cho số in-flight dự kiến.

### 3.3. Backlog và mất cân bằng dòng vào/ra

Cho một queue đơn giản, khi không bị drop/retry/cancel và đếm đúng cùng loại việc:

```text
Δbacklog ≈ arrivals - departures

Nếu λ_in > μ_out kéo dài: queue tăng cho tới khi đầy/reject/timeout.
```

Ví dụ **giả định** 10 giây có **1.200 task đến**, **900 task bắt đầu được worker lấy ra**: backlog trước worker có thể tăng khoảng **300 task** nếu không có trường hợp bị drop/cancel/reject. Nhưng backlog bị giới hạn chỉ **100** thì các task dư có thể bị reject, block producer hoặc xử lý ở caller, tùy rejection policy. Vì vậy **queue đứng yên ở mức 100 không có nghĩa hệ thống khỏe**: nó có thể đã chạm trần và đang reject.

Nếu muốn quy ra throughput của service, phải phân biệt **task dequeue** với **request completion**. Một request có thể sinh nhiều task, task có thể hoàn tất không đồng nghĩa response đã được gửi.

## 4. Tầng request: khi nào in-flight tăng?

**In-flight request** được định nghĩa từ một điểm bắt đầu (ví dụ handler nhận request) đến một điểm kết thúc (response hoàn tất hoặc được hủy). Cần giữ cách đếm nhất quán:

- Tăng gauge **một lần** ở ranh giới nhận request hợp lệ theo scope mình chọn.
- Giảm gauge **một lần** ở mọi đường kết thúc: success, error, timeout, cancel, connection closed; dùng `try/finally` cho xử lý đồng bộ và callback completion cho async.
- Với async/streaming, **không giảm khi method handler trả về** nếu response chưa thực sự kết thúc.
- Nếu gateway đã nhận 10.000 request nhưng service chỉ nhận 6.000, `in-flight` của service không bao phủ 4.000 request đang chờ/bị từ chối **trước service**.
- Nếu chỉ đo `active request` ở filter HTTP của một framework, phải biết có tính các request còn chờ executor (chưa vào filter) không.

Để phân biệt việc dồn queue trước service, xem **gateway pending/connection backlog**, accepted rate ở service, rate upstream và timeout phía client. Một server in-flight thấp cùng client latency cao chưa chắc dịch vụ đã không nghẽn: request có thể chưa tới được handler.

### In-flight cao có thể là bốn hiện tượng rất khác

1. **Work thật nhiều:** throughput và concurrency tăng tương ứng, latency ổn, ít timeout; có thể là tải hợp lệ.
2. **Server worker queue:** request đã nhận nhưng chờ worker; `executor.queued` và queue wait tăng.
3. **Blocked I/O:** worker hoặc async request giữ trạng thái in-flight do chờ connection, DB lock hoặc remote socket; CPU có thể thấp.
4. **Long-lived request:** streaming/SSE/long polling giữ connection lâu nhưng không có vấn đề; cần metric tách theo route và traffic class.

Chỉ nhìn một gauge `in-flight=500` không phân biệt được bốn tình huống này.

## 5. Tầng worker/executor: pool bận và queue tích tụ

Với một `java.util.concurrent.ThreadPoolExecutor` đã được gắn vào request processing, các chỉ số có sẵn:

| API | Nội dung |
| --- | --- |
| `getPoolSize()` | Số worker thread hiện có |
| `getCorePoolSize()` / `getMaximumPoolSize()` | Giới hạn core/max được cấu hình |
| `getActiveCount()` | **Ước lượng** số worker đang chạy task; không phải CPU usage |
| `getQueue().size()` | Số task đang chờ trong executor work queue tại lúc hỏi |
| `getQueue().remainingCapacity()` | Capacity còn lại của queue nếu queue hỗ trợ |
| `getCompletedTaskCount()` | **Ước lượng** tổng task đã hoàn tất |
| `getTaskCount()` | **Ước lượng** số task từng được scheduled |

**Chú ý queue policy:**

- Với **bounded `ArrayBlockingQueue`** và finite max workers, pool/queue đầy có thể **reject task**, tùy `RejectedExecutionHandler`. Cần metric riêng cho rejections và cách map chúng ra HTTP error/backpressure.
- Với **unbounded `LinkedBlockingQueue`** (ví dụ cách cấu hình của `Executors.newFixedThreadPool`), task có thể tích tụ rất lâu, tăng latency và bộ nhớ mà không reject sớm. Khi queue luôn nhận được task, `maximumPoolSize` cao hơn core cũng có thể **không có tác dụng** với chiến lược xếp hàng ấy.
- Với `SynchronousQueue`, không có backlog lưu trong queue theo cách thông thường; nếu không thể bàn giao task trực tiếp, pool phải có worker mới hoặc reject.
- `CallerRunsPolicy` có thể chạy task trên thread **gửi công việc**, đẩy áp lực ngược lên caller; số `active worker` của executor không phản ánh các task được chạy bởi caller.
- Nếu ứng dụng dùng **ForkJoinPool, virtual threads (JDK mới hơn), event loop** hoặc framework dispatcher riêng, không áp một-một các metric của `ThreadPoolExecutor`. Xem cách framework đo queue và concurrency của nó.

**Active worker là “đang giữ slot”, không phải “đang dùng CPU”.** Worker có thể chờ `DataSource.getConnection()`, `Socket.read()`, `Future.get()`, `LockSupport.park()` hoặc request đến dịch vụ khác. Tăng số worker khi các worker cũ đang chờ DB pool có thể chỉ chuyển bottleneck xuống DB và làm tăng queue connection.

### Dấu hiệu nghẽn executor

```text
active ~= max
queued tăng
task_queue_wait p95/p99 tăng
accepted_rate > task_start_rate trong nhiều cửa sổ
rejected_total tăng khi queue đầy
```

Đây là dấu hiệu **backlog trước worker**. Bước tiếp theo vẫn phải xác định **vì sao worker bận lâu**: CPU-bound, I/O-blocked, lock contention, GC, downstream chậm hay điều kiện tải. Đừng tăng worker trước khi nhìn stack và dependency metrics.

## 6. Tầng connection pool: active/idle/pending khác nhau

Giả sử một request cần kết nối đến DB qua connection pool:

```text
worker đang xử lý request
    |
    +-- acquire(connection) 
    |       |
    |       +-- idle có sẵn      -> trả connection ngay
    |       +-- có thể mở mới    -> connect/authenticate (có thể chậm)
    |       +-- max đã đạt       -> đợi trong pending/acquire queue
    |
    +-- có connection         -> gửi query/transaction
    |       |
    |       +-- DB đang chạy/đợi lock/disk/CPU
    |
    +-- release connection    -> trả về pool
```

Ví dụ metric thường gặp từ các pool (HikariCP, JDBC pool, HTTP client pool, Redis pool...), **tên chính xác khác tùy framework/version**:

- **max/size:** số connection được cấu hình cho pool hoặc số đang mở; hai số không nhất thiết giống nhau.
- **active/leased:** số connection đã được giao cho caller. Có thể caller đang **không gửi query** nhưng vẫn giữ connection trong transaction lâu hoặc quên close.
- **idle:** connection có thể lấy dùng lại ngay tại thời điểm đo.
- **pending/waiting:** số caller đang chờ mượn connection. Có thể lớn hơn số worker nếu có async callers hoặc các API không chặn; có thể bị đếm khác nhau giữa pool.
- **acquire wait duration:** chờ đến khi mượn được connection, tính cả đợi slot hoặc thời gian thiết lập connection tùy instrumentation.
- **usage/hold duration:** thời gian caller giữ connection sau khi mượn; không phải toàn bộ SQL execution time.
- **acquire timeout / errors:** không mượn được trước deadline; có thể kéo theo request failure.

**Mẫu nghẽn pool điển hình**: `active ~= max`, `idle=0`, `pending>0`, `acquire_p95` tăng, worker stack tập trung tại acquire. Đây là nút cổ chai ở **khả năng cấp connection**. Muốn tìm nguyên nhân gốc, xem connection được giữ vì query/lock lâu, transaction dài, connection leak hay max pool quá nhỏ so với tải hợp lệ.

**Không suy ngược** rằng DB CPU cao vì connection pool active=max. Một DB có thể ít CPU nhưng các connection bị giữ do lock, slow I/O, network hoặc transaction idle. Hãy đối chiếu DB active sessions, wait events, locks, query latency và số connection theo cả hai phía.

### Một công thức kiểm tra capacity mang tính xấp xỉ

Giả sử **8 connection** được dùng liên tục, mỗi lần mượn giữ trung bình **80 ms**:

```text
Tối đa lý tưởng ~= 8 connections / 0,080 s = 100 lượt mượn/s
```

Công thức dùng **thời gian giữ connection trung bình**, không phải end-to-end request latency; nó chỉ là bound trực giác trong tải đủ lớn và điều kiện lý tưởng, **không phải cam kết throughput**. Nếu request có nhiều DB calls hoặc retries, tốc độ “lượt mượn” khác request/s. Nếu DB chỉ chịu được 60 query/s, việc tăng pool lên 16 không làm DB xử lý 200 query/s; có thể làm nghẽn nghiêm trọng hơn.

## 7. Tầng tài nguyên phụ thuộc: không chỉ số connection

Pool trong ứng dụng có thể rất khỏe mà downstream vẫn chậm vì:

- **DB:** lock wait, transaction kéo dài, slow query/index, connection setup, CPU/disk I/O, replication, checkpoint, connection/session limit.
- **HTTP/gRPC dependency:** server queue, connection establishment, DNS, TLS, TCP retransmit, network latency, upstream rate limit; HTTP/2 multiplexing có thể mang nhiều concurrent streams trên một connection nên “connection count” ≠ “request count”.
- **Redis/cache:** pool acquire nhanh nhưng operation bị slow command, block, network hoặc single-thread event loop của dependency.
- **Message broker:** producer queue/batch/acks, in-flight requests, retry và broker partition/replication; thời gian publish không đồng nhất consumer processing.
- **Thread/CPU/GC phía chính ứng dụng:** đôi khi outbound chậm vì worker thiếu CPU để gửi/đọc response hoặc callback không được scheduling; không nên quy tất cả thời gian chờ cho downstream.

Phải quan sát **cùng dependency cả bên client lẫn server**: số request outbound, latency/error/timeout ở client; in-flight, queue, CPU/locks/query metrics ở server. Có thể dependency trả lời chậm vì thực sự xử lý lâu, hoặc client mất thời gian **trước khi gửi** do chờ pool/circuit breaker/rate limiter.

### Retry và fan-out làm số liệu “lệch”

Ví dụ một inbound request gọi song song 3 HTTP endpoints và retry một endpoint 2 lần:

- **Inbound requests = 1**.
- **Outbound attempts có thể = 5** (3 lần đầu + 2 lần retry), không nhất thiết diễn ra cùng lúc.
- **Downstream in-flight** tại một thời điểm có thể > inbound in-flight, nhưng không bằng tổng attempts.
- Nếu retry đúng lúc dependency chậm, số attempt tăng có thể **khuếch đại tải** (retry storm) và kéo dài in-flight/queues.

Nên gắn `dependency`, `operation`, `attempt`, `timeout`, `retry_reason` trong tracing/log; metric label chỉ chọn những chiều có cardinality kiểm soát được. Dùng **retry budget, exponential backoff với jitter và deadline tổng**, tránh cấu hình mỗi tầng retry vô hạn.

## 8. Đặt timeout, queue capacity và backpressure theo toàn chuỗi

Ba lỗi thiết kế dễ làm latency bùng nổ:

1. **Chấp nhận vô hạn:** queue chờ nhiều giây nhưng client đã hết deadline; worker tiếp tục xử lý những request không còn giá trị.
2. **Không có ngân sách timeout end-to-end:** 200 ms chờ worker + 500 ms chờ DB connection + 3 s query + retry thêm 3 s = p99 rất cao, dù từng timeout riêng lẻ đều “hợp lý”.
3. **Tăng mọi pool cùng lúc:** nhiều worker hơn làm số caller chờ connection tăng; nhiều connection hơn làm DB overload; queue lớn hơn chỉ giấu lỗi bằng thời gian chờ.

### Thực hành tốt

- **Bounded queues và admission control:** bảo vệ CPU/RAM và làm lỗi overload trở nên rõ ràng; xác định hành vi reject (HTTP 429/503, retry-after theo chính sách) thay vì treo lâu.
- **Deadlines truyền xuyên tầng:** một request có tổng deadline 1,5 s thì thời gian chờ executor, mượn connection, query và retry phải tiêu ngân sách đó; không khởi động lại 1,5 s ở từng tầng.
- **Queue wait timeout/cancel:** khi client hủy, đảm bảo task chưa chạy và future/outbound call được hủy phù hợp; cleanup nguồn lực trong `finally`/callback, không tự động coi cancel đã hủy query downstream.
- **Pool sizing theo tài nguyên yếu nhất:** tăng server workers chỉ khi CPU/I/O và downstream có headroom; điều chỉnh connection pool kèm quan sát DB/server limits.
- **Bulkhead/circuit breaker/rate limit:** cách ly các dependency chậm; tránh một API làm đầy executor/connection pool chung gây ảnh hưởng toàn dịch vụ.
- **Tách request classes:** streaming và request ngắn, read và write, heavy batch và interactive traffic có thể cần pool/budget/queue khác nhau.
- **Theo dõi thành công, lỗi và từ chối:** throughput thành công không được che việc timeout/reject tăng; xem cả saturation và user-facing SLA.

Backpressure làm hệ thống **từ chối nhanh có kiểm soát** khi không còn khả năng phục vụ, thường tốt hơn chấp nhận vô hạn rồi để timeout dây chuyền. Tuy nhiên chọn cơ chế phản hồi và retry phụ thuộc hợp đồng API; không thể coi mọi 503 là retry được ngay.

## 9. Java 17: mô phỏng bốn request trong hai tầng chờ

Ví dụ này **chạy độc lập** với JDK 17+ và không cần DB/network. Mục đích là nhìn thấy **ba trạng thái khác nhau**:

- Hai worker của executor đang chạy task (active).
- Hai request còn nằm trong queue chưa có worker.
- Một worker đã chiếm “connection” và một worker đang chờ permit của pool phụ thuộc.

`Semaphore` chỉ **mô phỏng giới hạn connection**; không phải JDBC connection pool thật. Các phép đọc `getActiveCount()` và `getQueueLength()` mang tính **ước lượng** khi hệ thống đang thay đổi.

Tạo file **`RequestPoolSnapshot.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class RequestPoolSnapshot {
    private static final ThreadPoolExecutor WORKERS =
            new ThreadPoolExecutor(
                    2, 2, 0L, TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<>(2),
                    new ThreadPoolExecutor.AbortPolicy());

    // Giả lập pool chỉ có đúng 1 connection/permit.
    private static final Semaphore DEPENDENCY = new Semaphore(1, true);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final CountDownLatch FIRST_LEASED = new CountDownLatch(1);
    private static final CountDownLatch SECOND_STARTED = new CountDownLatch(1);
    private static final AtomicInteger IN_FLIGHT = new AtomicInteger();

    private static void accept(boolean first, boolean second) {
        IN_FLIGHT.incrementAndGet();
        try {
            WORKERS.execute(() -> {
                boolean leased = false;
                try {
                    if (second) {
                        SECOND_STARTED.countDown();
                    }
                    DEPENDENCY.acquire();
                    leased = true;
                    if (first) {
                        FIRST_LEASED.countDown();
                    }
                    RELEASE.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    if (leased) {
                        DEPENDENCY.release();
                    }
                    IN_FLIGHT.decrementAndGet();
                }
            });
        } catch (RejectedExecutionException e) {
            // Đã bị từ chối, không còn thuộc tập admitted in-flight.
            IN_FLIGHT.decrementAndGet();
            throw e;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try {
            accept(true, false);
            if (!FIRST_LEASED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task did not start");
            }

            accept(false, true);
            if (!SECOND_STARTED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Second task did not start");
            }

            // Hai worker đang bận. Hai task tiếp theo vào queue.
            accept(false, false);
            accept(false, false);

            // Chờ best-effort để worker thứ hai xếp hàng ở Semaphore.
            for (int i = 0; i < 100 && !DEPENDENCY.hasQueuedThreads(); i++) {
                Thread.sleep(10);
            }

            System.out.println("inFlight=" + IN_FLIGHT.get());
            System.out.println("workersActiveApprox=" + WORKERS.getActiveCount());
            System.out.println("executorQueued=" + WORKERS.getQueue().size());
            System.out.println("dependencyLeased=" + (1 - DEPENDENCY.availablePermits()));
            System.out.println("dependencyPendingApprox=" + DEPENDENCY.getQueueLength());
        } finally {
            RELEASE.countDown();
            WORKERS.shutdown();
            if (!WORKERS.awaitTermination(5, TimeUnit.SECONDS)) {
                WORKERS.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 RequestPoolSnapshot.java
java RequestPoolSnapshot
```

Khi chạy bình thường, các dòng **`inFlight=4`**, **`executorQueued=2`**, **`dependencyLeased=1`** được thiết kế để ổn định ở thời điểm quan sát. Ví dụ đầu ra **thường thấy**:

```text
inFlight=4
workersActiveApprox=2
executorQueued=2
dependencyLeased=1
dependencyPendingApprox=1
```

`getActiveCount()` và `getQueueLength()` là API quan sát/ước lượng; trong môi trường scheduler bất thường hoặc thực thi bị gián đoạn, giá trị của những dòng có hậu tố `Approx` có thể khác. Nếu JVM không có đủ tài nguyên khởi động thread trong vòng 5 giây, chương trình báo lỗi thay vì giả vờ snapshot đáng tin.

**Giải thích tại sao số liệu không cộng thành tám request:**

- `inFlight=4` gồm cả 4 task đã được chấp nhận: 2 đang chạy, 2 đang chờ executor. Đây là bộ đếm tự khai báo của chương trình.
- `workersActiveApprox=2` là 2 worker giữ slot: một worker giữ permit và đợi `RELEASE`, worker thứ hai chờ lấy permit. **Cả hai không phải đang bận CPU**.
- `executorQueued=2` là **hai request khác** chưa được worker bắt đầu, không phải các thread chờ semaphore.
- `dependencyLeased=1` là **một resource** đang được chiếm, còn `dependencyPendingApprox=1` biểu thị thread thứ hai đang chờ acquire. Hai số ấy không đếm thêm inbound requests.
- Nhìn mỗi `workerActive=2` có thể lầm tưởng “pool server bận nên tăng threads”; nhưng **nguyên nhân giữ worker** ở demo là dependency permit và chờ theo điều kiện mô phỏng.

Thí nghiệm cũng minh họa giới hạn đo: `getQueue().size()` đếm task chờ **trong executor này**, không đếm queue của gateway, pending của DB, message broker hoặc request async nằm ngoài executor. Khi thay mock semaphore bằng HikariCP/HTTP client thật, phải dùng metric gốc của chính pool đó.

## 10. Cách đo theo stage trong ứng dụng thật

Để tránh đo gộp, đặt instrumentation tại các ranh giới:

```text
t0 ingress_received
t1 task_enqueued
t2 task_dequeued / execution_started
t3 dependency_acquire_started
t4 dependency_acquired
t5 outbound_call_started
t6 outbound_call_completed
t7 dependency_released
t8 response_completed
```

Các đại lượng hữu ích cho một request đồng bộ tuyến tính:

| Đo lường | Khoảng thời gian | Ý nghĩa |
| --- | --- | --- |
| Admission/dispatch delay | `t1 - t0` | Trước khi enqueue/dispatch |
| Executor queue wait | `t2 - t1` | Chờ worker |
| Dependency acquisition wait | `t4 - t3` | Chờ connection/permit hoặc connect theo pool |
| Downstream call duration | `t6 - t5` | Thời gian call do HTTP/JDBC client thấy |
| Connection hold duration | `t7 - t4` | Thời gian leased, gồm những thao tác khác nếu caller giữ |
| End-to-end service duration | `t8 - t0` | Tổng latency theo scope service |

**Lưu ý:**

- Các khoảng trên **không tạo thành một phép cộng đúng cho mọi kiến trúc**: giữa chúng có thể có logic khác, overlap bất đồng bộ, nhiều dependencies song song hoặc retry.
- Dùng **`System.nanoTime()`** để tính elapsed duration trong cùng JVM, không dùng `System.currentTimeMillis()` làm thước đo elapsed do wall clock có thể bị điều chỉnh.
- **Histograms riêng theo stage** cộng với distributed tracing là cách phân biệt p99 do queue, acquire hay downstream. **Không cộng p99 stage** để “tính p99 tổng”; percentile không tuyến tính.
- Với async, khai báo ranh giới và đảm bảo metrics đóng khi **response thực sự hoàn tất/cancel**, không chỉ khi thread handler return.
- Nếu request timeout trước lúc được worker lấy từ queue, phải có cơ chế loại bỏ/cancel thích hợp và metric timeout; không để stale work chạy vô hạn.
- Với N attempts, ghi rõ attempt index và total budget; không gộp lại thành “một query chậm” rồi bỏ mất các retry.

### Quan sát stack và JFR để biết worker chờ gì

Với HotSpot JDK 17, PID minh họa `12345`:

```bash
jcmd 12345 Thread.print -l
jcmd 12345 JFR.start name=io-diag settings=profile duration=60s filename=io-diag.jfr
```

Sau khi recording kết thúc:

```bash
jfr summary io-diag.jfr
jfr print --events "jdk.SocketRead,jdk.SocketWrite,jdk.ThreadPark" io-diag.jfr
```

- Thread dump giúp tìm worker stack tại `DataSource.getConnection()`, JDBC driver, `Socket.read()`, `CompletableFuture.join()` hoặc lock wait; **một snapshot không đủ để kết luận thời gian chờ kéo dài**.
- JFR có event về socket I/O, thread park và synchronization, tùy event có được **bật và ghi thành instance** trong recording. `jfr summary` xác nhận file thật sự có event trước khi phân tích.
- CPU thấp cùng nhiều thread `WAITING`/`TIMED_WAITING` có thể là I/O wait/condition wait; không đồng nghĩa lỗi do CPU. `RUNNABLE` cũng không bảo đảm thread đang chạy trên CPU vì có native I/O.
- Nếu nghi downstream DB, lấy thêm **DB-side query/lock/session metrics** và tracing, vì thread dump của Java không cho biết nguyên nhân SQL server đang xử lý chậm.
- Dùng `jcmd ... JFR.start` và event settings theo quyền vận hành, dung lượng file, overhead; tránh bật thu thập nặng không kiểm soát trong production.

## 11. Ma trận suy luận nút nghẽn

| Các tín hiệu xuất hiện **cùng lúc** | Giả thuyết ưu tiên | Kiểm chứng tiếp và hướng xử lý |
| --- | --- | --- |
| In-flight ↑, executor queue ↑, active≈max, dependency pending thấp | Nghẽn trước worker hoặc worker làm việc chậm | Thread dump, CPU/GC, queue wait histogram; phân tích work per task, pool/CPU quota |
| In-flight ↑, active≈max, DB pool active=max, idle=0, pending ↑ | Worker bị giữ khi chờ connection | Connection-acquire p95, transaction duration, JDBC stacks, DB wait events; chưa tăng worker |
| DB pool active=max, pending=0, DB latency ↑ | Connection được sử dụng lâu hoặc DB đang chậm, chưa chắc pool admission nghẽn | Query plans, DB lock/CPU/I/O, connection hold duration |
| Executor queue ngắn, HTTP in-flight ↑, async dependency waits ↑ | Async I/O hoặc remote dependency chậm | Client spans, remote p95/p99, retry count; đừng dùng active threads làm đại diện in-flight |
| Gateway pending ↑, app request rate thấp | Queue/admission ở tầng trước ứng dụng | Gateway accept/backlog, load balancing, network, app capacity, pod readiness |
| Pending connection ↑, acquire timeouts ↑ nhưng DB CPU thấp | Transaction giữ connection, lock hoặc network, chưa chắc CPU DB | DB locks/sessions/idle-in-transaction, client connection usage |
| Outbound attempts tăng nhanh hơn inbound rate | Retry/fan-out amplification | Retry count, attempt spans, deadline/budget, circuit breaker |
| App request rate tăng, throughput không tăng, queue=max, rejects ↑ | Service quá tải/bounded queue | Admission policy, rate limits, capacity thực, 429/503 |
| p99 ↑, CPU throttled ↑, GC/threads chờ scheduling | Container CPU quota pressure | cgroup CPU statistics, CPU limit, thread states, GC pauses |
| p99 ↑, in-flight ↑ nhưng throughput vẫn ổn | Latency hoặc long-lived requests tăng; có thể thay đổi traffic mix | Breakdown theo endpoint, streaming class, stage latency và số in-flight |

**Không chọn một giả thuyết chỉ vì một hàng “khớp”**. Tìm mối liên hệ thời gian và kiểm tra stage đầu tiên phát sinh queue/wait trước khi suy ra nguyên nhân sâu hơn.

## 12. Tình huống minh họa: DB pool là nút thắt, không phải thread pool

Dữ liệu **giả định** của service Java khi p99 tăng:

| Metric | Trước spike | Trong spike |
| --- | ---: | ---: |
| Inbound completed/s | 80 | 78 |
| In-flight requests | 24 | 150 |
| Request p99 | 280 ms | 2.4 s |
| Server active worker / max | 18 / 64 | 63 / 64 |
| Executor queued tasks | 0 | 70 |
| DB pool active / max | 7 / 12 | 12 / 12 |
| DB pool idle | 5 | 0 |
| DB pool pending | 0 | 45 |
| DB connection-acquire p95 | 5 ms | 850 ms |
| DB server query p95 | 25 ms | 240 ms |

### Suy luận theo tầng

1. **Ingress:** completed rate gần như không tăng nhưng in-flight tăng mạnh → thời gian request nằm trong service kéo dài; chưa khẳng định nghẽn ở đâu.
2. **Executor:** worker gần max, queue có backlog. Đây là dấu hiệu nhiều task chưa có worker, nhưng không tự chứng minh tăng worker là đủ.
3. **DB connection pool:** active=max, idle=0, pending=45, acquire wait p95=850 ms → nhiều worker chờ mượn DB connection. Đây là một trong những nút nghẽn **quan sát được trực tiếp**.
4. **DB query:** p95 cũng tăng từ 25 ms lên 240 ms, nên connection bị giữ lâu hơn có thể làm thiếu connection. Cần điều tra **slow query/locks/DB load/transaction hold**, hoặc thay đổi loại request gây query nặng.
5. **Hướng ưu tiên:** trace request chậm, kiểm tra DB server, timeout/retry và connection hold; giảm query/transaction duration nếu có thể. **Không tăng server worker max 64 lên 256 ngay**, vì chỉ có thể đẩy thêm caller vào pending DB.
6. **Sau điều chỉnh:** so sánh cùng tải, cùng thời gian lấy mẫu: DB acquire p95, pending, executor queue, throughput success, request p95/p99, timeout/reject và DB server metrics.

**Đừng coi p99=2,4 s có thể tính bằng cách cộng 850 ms p95 acquisition + 240 ms p95 query.** Đây là những percentile khác scope/distribution; cần tracing end-to-end của **cùng request** để phân tích nguyên nhân của tail latency.

## 13. Quy trình điều tra 10 phút khi p99 bùng nổ

1. **Khoanh đúng service/endpoint/pod và cửa sổ thời gian.** Xem load balancer, request attempts, throughput, error/timeout/rejection, p50/p95/p99. Xác định client nhận timeout trước hay sau khi service thực sự bắt đầu xử lý.
2. **Xác minh in-flight theo định nghĩa:** đếm ở ingress nào? có async/streaming? gồm requests cancel? có tính queue trước handler? Tránh dùng một metric chưa rõ scope.
3. **Đo executor:** active/max, queue size/capacity, rejected count, queue-wait duration; phân biệt queue “đã đầy nhưng không tăng” với queue thấp thật.
4. **Đo dependency pool:** active/max, idle, pending, acquisition wait/timeout; nếu có nhiều pool, tách từng pool theo tên, không cộng thành “DB connections” chung.
5. **Kiểm tra tài nguyên phụ thuộc:** query/locks/remote latency, server queue, CPU, disk, pool/session limits; ghép đúng dependency qua trace.
6. **Lấy mẫu thread và JFR phù hợp:** xem worker đang chạy CPU, chờ pool hay socket; tránh dùng thread state đơn lẻ làm kết luận.
7. **Tính kiểm tra đơn giản:** throughput × latency **trung bình** ≈ in-flight trung bình (khi ổn định); xem queue arrivals/departures và backlog trong cùng khoảng.
8. **Kiểm tra CPU quotas/GC, retry amplification và lock contention.** Một dependency chậm có thể bắt đầu từ CPU throttling hoặc GC của chính service.
9. **Chọn can thiệp ít rủi ro:** giới hạn request inflow, cancel stale work, timeout đúng stage, isolate slow dependency; fix slow query/leak; chỉ chỉnh pool sau khi xác minh capacity cả hệ thống.
10. **Đo lại trước–sau:** cùng workload, cùng route/dependency, xem tail latency, success throughput, queue/pending, errors, resource utilization và chi phí.

Mỗi phát biểu trong báo cáo nên có **metric/trace tại thời điểm cụ thể**, ranh giới đo và giả thuyết đã kiểm tra. Không đổi cấu hình pool dựa trên một snapshot hoặc một biểu đồ thiếu time alignment.

## 14. Các ngộ nhận phổ biến

1. **“500 in-flight nghĩa là 500 worker threads chạy.”** Sai với async, queue và long-lived connections.
2. **“Active workers gần max nghĩa là CPU gần 100%.”** Sai: worker có thể đang block ở connection pool/I/O.
3. **“Queue executor tăng nên tăng max threads.”** Chưa chắc; nếu worker chờ DB pool, tăng workers thường chuyển/đẩy nghẽn xuống dependency.
4. **“DB pool active=max chứng tỏ DB đang chạy max queries.”** Sai: leased connection có thể đang giữ bởi transaction/logic không phát query.
5. **“Không có connection pending thì DB không chậm.”** Sai: connection đã leased có thể chờ SQL/lock/network rất lâu.
6. **“Pool có 20 connections nên tối đa 20 inbound requests.”** Sai với requests không dùng DB, async multiplexing và nhiều lượt mượn theo request; scope khác nhau.
7. **“p99 stage A + p99 stage B = p99 request.”** Sai; percentile không cộng tuyến tính và có overlap.
8. **“Little's Law dùng p99 latency.”** Sai: dùng **trung bình** và giả thiết phù hợp.
9. **“Queue đứng ở max nhưng không tăng là hệ thống ổn định.”** Sai: có thể liên tục reject/cancel/timeout.
10. **“Cứ nâng queue lớn sẽ xử lý hết spike.”** Có thể chỉ đổi lỗi reject thành chờ quá hạn và tăng RAM.
11. **“Timeout từ client hủy ngay DB query.”** Không bảo đảm; cần cơ chế propagation/cancellation cụ thể.
12. **“Một request ứng với một downstream call.”** Sai với fan-out, retries, streaming và background work.
13. **“Throughput chỉ gồm responses 2xx.”** Chỉ đúng nếu metric định nghĩa như vậy; khi đo tốc độ rời hệ thống cần tính các outcome phù hợp.
14. **“HTTP request latency không liên quan gateway.”** Nếu queue trước service, metric service có thể bỏ sót thời gian người dùng chờ.
15. **“Semaphore demo là HikariCP thật.”** Không: demo chỉ minh họa hai queue khác nhau, không đo SQL, socket hay connection lifetime thật.
16. **“Chỉ cần thread dump một lần.”** Không đủ: snapshot phải gắn timeline với queue/pool/duration để tránh nhầm một wait ngắn thành bottleneck kéo dài.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Service có 200 in-flight requests, executor active=16, queued=20. Có thể kết luận 164 request bị mất không?  
**Đáp án:** Không. Các request khác có thể đang xử lý async, chờ dependency, streaming hoặc nằm ở stage ngoài executor. Phải biết định nghĩa từng metric và trace.

**Câu 2.** DB pool max=10, active=10, idle=0, pending=35, acquisition p95 tăng. Tăng server workers có xử lý nghẽn gốc không?  
**Đáp án:** Không bảo đảm, thường làm pending cao hơn. Điều tra connection hold time, DB query/locks, transaction và sizing theo toàn hệ thống trước.

**Câu 3.** Throughput ổn định 120 req/s, mean latency 0,5 s. Little's Law dự đoán số in-flight trung bình?  
**Đáp án:** `L = 120 × 0,5 = 60`, khi dùng cùng boundary và hệ thống ổn định. Không thay mean latency bằng p99.

**Câu 4.** Worker active=max nhưng CPU thấp, thread dumps thấy nhiều worker chờ `DataSource.getConnection()`. Điều này gợi ý gì?  
**Đáp án:** Worker đang giữ slot để chờ connection. Đo pending/acquire p95, active/max và DB-side metrics để tìm nguyên nhân thực tế.

**Câu 5.** Queue size không đổi ở 100/100, nhưng rejected total tăng mạnh. Service có hết nghẽn chưa?  
**Đáp án:** Chưa. Queue đầy, task mới đang bị từ chối; cần nhìn rejection rate, deadlines, throughput và capacity.

**Câu 6.** Một HTTP request gọi 3 dịch vụ và retry một dịch vụ thêm hai lần. Có phải inbound=5 không?  
**Đáp án:** Không. Inbound=1; outbound attempts có thể tới 5. Nên tách metric attempt khỏi request.

**Câu 7.** p99 request=2 s, acquisition p99=800 ms, query p99=900 ms. Có thể suy phần “khác” luôn là 300 ms?  
**Đáp án:** Không. Percentile từ các phân bố khác nhau không cộng/trừ tuyến tính; dùng trace của cùng request.

**Câu 8.** Tăng DB pool từ 8 lên 32, DB server CPU đã 100% và query latency tăng. Có chắc throughput sẽ tăng?  
**Đáp án:** Không. Concurrency cao hơn có thể tăng contention/queue ở DB và làm tail latency tệ hơn; cần đo capacity thật.

## Tài liệu tham khảo

- [Java SE 17 — `ThreadPoolExecutor`: pool size, active count, queue, rejection policies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — `Semaphore`: available permits và queue-length estimates](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 17 — `CountDownLatch`: điều phối thí nghiệm đồng thời](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Oracle JDK 17 — `jcmd`: `Thread.print` và `JFR.start`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — `jfr`: `summary` và `print`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Little (1961), "A Proof for the Queuing Formula: L = λW"](https://doi.org/10.1287/opre.9.3.383)
- [Micrometer — Meter Types: Gauge, Counter, Timer](https://docs.micrometer.io/micrometer/reference/concepts.html)
