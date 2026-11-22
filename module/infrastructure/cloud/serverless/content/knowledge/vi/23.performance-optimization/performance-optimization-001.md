# Đo latency percentile và phân rã thời gian toàn luồng

Một API serverless có thể có thời gian xử lý trung vị chỉ 80 ms nhưng vẫn khiến một phần người dùng chờ hơn 2 giây. Trung bình (average) thường che khuất nhóm request chậm này. Để hiểu trải nghiệm thực tế, đội phát triển cần đo **latency percentile** như p50, p90, p95 và p99, sau đó phân rã một request thành các khoảng thời gian có thể quan sát: chờ tại gateway, khởi tạo instance, xử lý trong Java, gọi database/API, serialize response và truyền kết quả về client.

Trong hệ thống event-driven, cần đo thêm thời gian message nằm trong queue và thời gian từ lúc event được tạo đến khi nghiệp vụ hoàn tất. Một consumer xử lý message trong 40 ms vẫn có thể tạo ra trải nghiệm chậm nếu message đã chờ 15 giây trong queue.

Bài học này tập trung vào cách xác định ranh giới đo, đọc percentile đúng cách, kết hợp metrics/logs/traces và instrument Java function để tìm bước tạo ra tail latency. Mục tiêu là đo toàn luồng theo cùng một định nghĩa, rồi dùng dữ liệu để cải thiện SLO và hiệu năng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích p50, p90, p95 và p99 bằng phân phối latency.
- Phân biệt latency, duration, throughput và queue wait.
- Chọn ranh giới đo cho HTTP request và asynchronous event.
- Phân rã end-to-end latency thành các span hoặc stage có ý nghĩa.
- Hiểu vì sao không thể cộng p95 của từng dependency để suy ra p95 toàn request.
- Dùng histogram và sample count để theo dõi percentile qua nhiều instance.
- Đo duration trong Java bằng `System.nanoTime()`, Micrometer và OpenTelemetry.
- Phân biệt cold start, handler duration, dependency latency và network overhead.
- Xác định critical path khi một request gọi nhiều dependency tuần tự hoặc song song.
- Thiết kế load test, dashboard, SLI/SLO và cảnh báo cho tail latency.

## 1. Latency và các percentile

**Latency** là thời gian từ một điểm bắt đầu đến một điểm kết thúc đã được định nghĩa. Ví dụ, HTTP end-to-end latency có thể được đo từ lúc client gửi request đến khi client nhận response hoàn chỉnh. Server processing duration có thể chỉ đo từ lúc ứng dụng nhận request đến lúc tạo response.

Hai phép đo này không giống nhau. Khi so sánh số liệu, phải biết mỗi metric bắt đầu và kết thúc ở đâu.

### p50, p90, p95 và p99

Percentile là giá trị mà một tỷ lệ phần trăm quan sát nằm bằng hoặc thấp hơn nó.

| Chỉ số | Diễn giải | Dùng để hiểu |
|---|---|---|
| **p50** | 50% request có latency bằng hoặc thấp hơn giá trị này | Trải nghiệm điển hình ở giữa phân phối |
| **p90** | 90% request bằng hoặc thấp hơn | Nhóm chậm hơn mức phổ biến |
| **p95** | 95% request bằng hoặc thấp hơn | Tail latency thường dùng trong SLO |
| **p99** | 99% request bằng hoặc thấp hơn | Nhóm request rất chậm |

Ví dụ một service có 10.000 request trong cửa sổ đo:

- p50 = 90 ms: khoảng một nửa request hoàn tất trong 90 ms hoặc ít hơn.
- p95 = 650 ms: khoảng 95% request hoàn tất trong 650 ms hoặc ít hơn.
- p99 = 1.800 ms: khoảng 99% request hoàn tất trong 1,8 giây hoặc ít hơn.

Phần còn lại của phân phối có thể có latency lớn hơn nhiều. Một số request có thể mất 5 giây do cold start, connection pool chờ, database lock hoặc retry.

~~~mermaid
flowchart LR
    A["Nhanh nhất"] --> B["p50"]
    B --> C["p90"]
    C --> D["p95"]
    D --> E["p99"]
    E --> F["1% request chậm nhất"]
~~~

Percentile không phải tỷ lệ lỗi. p99 = 1,8 giây không có nghĩa 1% request lỗi; nó có nghĩa 1% request nằm phía trên mốc latency đó. Cần theo dõi error rate riêng.

### Vì sao average dễ gây hiểu nhầm?

Giả sử có 100 request: 99 request mất 50 ms và một request mất 5.000 ms.

- Average xấp xỉ 99,5 ms.
- p50 xấp xỉ 50 ms.
- p99 phụ thuộc quy tắc percentile của hệ thống thống kê, nhưng sẽ phản ánh phần đuôi chậm gần 5 giây.

Average có thể trông khá tốt trong khi một request trong 100 request rất chậm. Với service có fan-out hoặc traffic lớn, một tỷ lệ nhỏ request chậm vẫn có thể ảnh hưởng nhiều người dùng.

Average vẫn hữu ích để tính tổng tài nguyên hoặc xu hướng tổng quát. Nhưng để đánh giá trải nghiệm và tail latency, hãy xem percentile cùng sample count và error rate.

### Percentile phụ thuộc số lượng mẫu

p99 trên 100 request chỉ có rất ít quan sát ở phần đuôi; kết quả có thể dao động mạnh. Khi traffic thấp, hãy hiển thị sample count và chọn cửa sổ đủ dài để có dữ liệu đáng tin cậy. Không diễn giải một percentile được tính từ vài request như một SLO ổn định.

Các hệ thống có thể dùng quy tắc nội suy hoặc nearest-rank khác nhau. Khi so sánh dashboard hoặc môi trường, dùng cùng metric definition và cùng phương pháp tính.

## 2. Định nghĩa ranh giới đo trước khi instrument

Trước khi thêm timer, hãy trả lời hai câu hỏi:

1. **Bắt đầu đo ở đâu?**
2. **Kết thúc đo ở đâu?**

Một API có thể có nhiều phép đo hợp lệ:

| Phép đo | Bắt đầu | Kết thúc |
|---|---|---|
| Client-perceived latency | Client bắt đầu gửi request | Client nhận response hoàn chỉnh |
| Gateway/request latency | Gateway nhận request | Gateway trả response |
| Application duration | Handler bắt đầu xử lý | Handler tạo kết quả hoặc response |
| Dependency duration | Bắt đầu gọi database/API | Nhận kết quả hoặc timeout |
| Queue wait | Broker chấp nhận message | Consumer bắt đầu xử lý |
| Consumer processing duration | Consumer bắt đầu xử lý | Consumer ack/commit theo định nghĩa |
| Business end-to-end latency | Event nghiệp vụ xảy ra | Kết quả nghiệp vụ hoàn tất |

Không gọi tất cả các giá trị này là `latency` mà không ghi rõ scope. Tên metric nên thể hiện ranh giới, ví dụ `http.server.request.duration`, `orders.queue.wait` hoặc `orders.business.completion.duration`.

### Đồng nhất đơn vị và clock

- Dùng milliseconds hoặc seconds nhất quán trong dashboard và SLO.
- Đối với duration trong cùng process, ưu tiên monotonic clock như `System.nanoTime()`.
- Đối với timestamp dùng để tương quan giữa service, dùng UTC và đồng bộ clock của máy chủ.
- Không lấy timestamp từ hai máy khác nhau rồi trừ trực tiếp nếu chưa xét clock skew.
- Không dùng thời gian wall-clock để đo duration ngắn trong cùng JVM.

`System.currentTimeMillis()` và `Instant.now()` biểu diễn thời gian lịch; chúng có thể bị điều chỉnh bởi đồng bộ thời gian hoặc thay đổi clock. `System.nanoTime()` chỉ phù hợp để tính khoảng thời gian, không phải timestamp có thể gửi sang service khác.

## 3. Phân rã HTTP request end-to-end

Một HTTP request đến Java function hoặc Cloud Run service có thể đi qua nhiều stage:

~~~mermaid
flowchart TD
    A["Client: DNS / connect / TLS"] --> B["Edge / API Gateway / load balancer"]
    B --> C["Platform routing / instance selection"]
    C --> D["Cold start hoặc warm instance"]
    D --> E["Java handler / HTTP server"]
    E --> F["Authentication / validation / business logic"]
    F --> G["Database / cache / external API"]
    G --> H["Serialize response"]
    H --> I["Network response về client"]
~~~

Một cách phân rã đơn giản:

```text
Client-perceived latency
  = client/network setup
  + gateway/edge time
  + platform dispatch and queueing
  + instance initialization (nếu có)
  + application processing
  + response transfer
```

Đây là mô hình khái niệm. Một số stage có thể chồng lấn, được đo ở các ranh giới khác nhau hoặc đã nằm trong metric của gateway/platform. Không cộng các metric có phạm vi bao trùm nhau vì sẽ double-count.

### Những stage thường cần quan sát

| Stage | Điều cần đo | Dấu hiệu chậm |
|---|---|---|
| DNS/connect/TLS | Thời gian client thiết lập kết nối | Chậm trước khi request đến server |
| Gateway/edge | Request latency và integration latency nếu có | Gateway policy, authorizer hoặc upstream chậm |
| Platform dispatch | Thời gian chờ instance sẵn sàng | Tải tăng, thiếu capacity, scale-out |
| Cold start/init | Thời gian khởi tạo runtime và ứng dụng | Image/JAR lớn, Spring context nặng, init remote call |
| Handler | Tổng thời gian xử lý trong ứng dụng | CPU, lock, validation hoặc code chậm |
| Database | Connection acquisition, query và transaction | Pool cạn, lock, query thiếu index |
| External API | Connect, TLS, server response, retry | Rate limit, network, upstream degradation |
| Serialization | Chuyển object thành JSON/protobuf | Payload lớn, reflection hoặc copy dữ liệu |
| Response transfer | Kích thước và thời gian truyền response | Response lớn, bandwidth hoặc client chậm |

### Không cộng metric chồng lấn

Ví dụ API Gateway integration latency có thể đã bao gồm phần lớn thời gian Lambda thực thi và round trip. Nếu cộng integration latency với Lambda duration, bạn có thể đếm phần xử lý Lambda hai lần.

Trước khi xây dashboard, ghi lại định nghĩa của từng metric từ provider: resource, start/end point, đơn vị, aggregation và phần nào đã bao gồm. Nếu không biết ranh giới, hãy xem metric như một góc nhìn độc lập thay vì cộng nó vào công thức.

## 4. Phân rã event-driven end-to-end

Với queue hoặc event bus, thời gian từ producer đến kết quả nghiệp vụ thường gồm:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker / Queue
    participant C as Consumer function
    participant D as Database / API
    P->>B: Publish event
    Note over B: Message wait / backlog
    B->>C: Deliver message
    Note over C: Cold start / dispatch
    C->>D: Process business operation
    D-->>C: Result
    C-->>B: Ack / commit
~~~

Nên tách ít nhất ba phép đo:

1. **Publish duration:** producer mất bao lâu để gửi event và nhận xác nhận từ broker.
2. **Queue wait/age:** message chờ bao lâu từ lúc broker nhận đến lúc consumer bắt đầu.
3. **Processing duration:** consumer xử lý bao lâu từ lúc bắt đầu đến khi hoàn tất/ack theo semantics của trigger.

Ngoài ra có thể đo **business completion latency** từ lúc nghiệp vụ phát sinh đến lúc toàn bộ quy trình kết thúc. Ví dụ order được tạo lúc 10:00:00 nhưng payment và inventory hoàn tất lúc 10:00:12 thì business completion latency là khoảng 12 giây.

Không đồng nhất consumer processing duration với end-to-end latency. Một consumer chạy 30 ms vẫn có thể xử lý message đã chờ 20 giây.

### Timestamp và clock skew

Nếu producer ghi `occurredAt` và consumer ghi `processedAt`, phép trừ hai timestamp phụ thuộc đồng bộ clock giữa các host. Sai lệch vài trăm milliseconds có thể làm số liệu queue wait sai, đặc biệt khi latency thật rất ngắn.

Ưu tiên:

- Dùng timestamp enqueue/delivery do broker cung cấp khi có.
- Dùng trace/span timestamps có đồng bộ clock và xem xét skew.
- Ghi nhận event occurred time riêng với broker publish time.
- Dùng monotonic clock để đo processing duration trong một invocation.
- Giữ event ID/correlation ID để nối log và trace, không dựa duy nhất vào timestamp.

Nếu cần đo business completion qua nhiều service, xác định nguồn timestamp chuẩn và sai số chấp nhận được. Không dùng timestamp client do người dùng gửi làm mốc tin cậy cho SLO.

## 5. Waterfall trace và critical path

Distributed trace biểu diễn request thành các span có thời gian bắt đầu, kết thúc và quan hệ cha-con. Waterfall view cho biết các stage chạy tuần tự hay song song.

Ví dụ một handler gọi database rồi gọi payment API tuần tự:

~~~text
HTTP server span       |-----------------------------|  420 ms
  validate             |--|                              15 ms
  database query       |--------|                         95 ms
  payment API          |----------------|                210 ms
  map + serialize      |---|                              30 ms
  other/overhead       |-------|                          70 ms
~~~

Trong ví dụ, payment API là dependency chiếm thời gian lớn nhất. Tối ưu validation 15 ms không cải thiện nhiều tổng latency nếu payment API vẫn mất 210 ms.

### Tuần tự và song song

Nếu hai dependency chạy tuần tự, tổng duration gần bằng tổng duration từng bước cộng overhead.

Nếu hai dependency chạy song song, thời gian của nhánh song song gần bằng nhánh chậm nhất, không phải tổng cả hai.

```text
Sequential:
  total ≈ A + B + C + overhead

Parallel:
  total ≈ max(A, B) + join/overhead
```

Critical path là chuỗi thao tác quyết định thời gian hoàn tất cuối cùng. Một trace tốt giúp nhìn ra critical path thay vì chỉ xếp hạng dependency theo duration riêng lẻ.

Không chuyển lời gọi sang song song nếu chúng có phụ thuộc dữ liệu, side effect không an toàn hoặc làm tăng tải lên backend. Tối ưu latency phải giữ nguyên correctness và giới hạn concurrency.

### Không cộng p95 của từng span

Giả sử p95 database query là 100 ms và p95 payment API là 300 ms. Không thể kết luận p95 toàn request là 400 ms. Hai percentile có thể thuộc hai request khác nhau; phân phối và tương quan giữa các stage quyết định percentile của tổng.

Để biết p95 end-to-end, đo trực tiếp duration của root request. Dùng child spans để giải thích các request nằm trong tail. Có thể cộng duration trên cùng một trace khi các span tuần tự và không chồng lấn, nhưng percentile của từng span riêng lẻ không thể cộng để tạo percentile tổng.

## 6. Histogram, percentile và aggregation

Để tính percentile trên nhiều instance, hệ thống thường cần histogram hoặc dữ liệu phân phối có thể tổng hợp.

### Histogram

Histogram chia duration thành các bucket. Ví dụ:

| Khoảng latency | Số request |
|---|---:|
| ≤ 50 ms | 120 |
| > 50 đến ≤ 100 ms | 460 |
| > 100 đến ≤ 250 ms | 310 |
| > 250 đến ≤ 500 ms | 80 |
| > 500 ms đến ≤ 1 s | 25 |
| > 1 s | 5 |

Histogram cho biết phân phối và có thể gộp số đếm từ nhiều instance theo cùng bucket boundaries. Backend có thể ước lượng percentile từ histogram.

### Percentile summary và histogram khác nhau

Một percentile được tính cục bộ ở mỗi instance thường không thể gộp chính xác bằng cách lấy trung bình các percentile đó.

Ví dụ:
- Instance A có p95 = 100 ms với 10 request.
- Instance B có p95 = 1.000 ms với 10.000 request.

Average của hai p95 là 550 ms, nhưng đó không phải p95 của toàn bộ 10.010 request.

Với hệ thống phân tán, ưu tiên histogram có bucket phù hợp hoặc backend hỗ trợ phân phối có thể merge. Nếu dùng client-side percentile, hãy hiểu rằng percentile có thể chỉ phản ánh từng instance/process và không được tổng hợp chính xác ở cấp service.

### Chọn bucket phù hợp

Bucket cần tập trung quanh vùng latency quan trọng đối với SLO. Nếu mục tiêu là 300 ms, cần có bucket đủ dày quanh 100–500 ms. Bucket quá thưa làm percentile ước lượng kém chính xác; bucket quá nhiều có thể tăng số time series và chi phí.

Giữ cùng bucket boundaries giữa các revision và môi trường nếu muốn so sánh. Đơn vị phải thống nhất, tránh một metric ghi milliseconds và metric khác ghi seconds.

## 7. Đo duration trong Java bằng monotonic clock

Với đoạn code đồng bộ trong một JVM, dùng `System.nanoTime()` để đo elapsed time.

~~~java
import java.util.concurrent.TimeUnit;

public final class TimedOrderService {
    private final OrderService delegate;
    private final LatencyMetrics metrics;

    public TimedOrderService(
            OrderService delegate,
            LatencyMetrics metrics) {
        this.delegate = delegate;
        this.metrics = metrics;
    }

    public OrderResult place(PlaceOrderCommand command) {
        long started = System.nanoTime();
        try {
            return delegate.place(command);
        } finally {
            long elapsed = System.nanoTime() - started;
            metrics.recordHandlerDuration(
                    elapsed, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Dùng `finally` để ghi duration cả khi xử lý thất bại. Nếu chỉ ghi khi thành công, dashboard sẽ bỏ sót latency của request lỗi hoặc timeout.

Không dùng `System.nanoTime()` làm timestamp event hoặc gửi giá trị này sang process khác. Nó chỉ có ý nghĩa tương đối trong cùng JVM/process.

### Đo từng dependency

Có thể bọc lời gọi dependency bằng một helper hoặc instrumentation chung:

~~~java
long started = System.nanoTime();
try {
    return paymentClient.authorize(request);
} finally {
    long elapsed = System.nanoTime() - started;
    paymentMetrics.recordAuthorizeDuration(
            elapsed, TimeUnit.NANOSECONDS);
}
~~~

Tên metric cần thể hiện dependency và operation. Không thêm orderId, userId hoặc URL đầy đủ làm metric tag. Các ID cụ thể nên nằm trong trace/log có kiểm soát.

## 8. Dùng Micrometer Timer để đo percentile

Spring Boot thường tích hợp Micrometer. `Timer` ghi nhận count, total time và phân phối duration. Cấu hình registry/exporter quyết định metric được gửi đến backend nào.

Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class OrderMetrics {
    private final Timer handlerTimer;
    private final Timer databaseTimer;

    public OrderMetrics(MeterRegistry registry) {
        this.handlerTimer = Timer.builder("orders.handler.duration")
                .description("Order handler duration")
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        java.time.Duration.ofMillis(100),
                        java.time.Duration.ofMillis(250),
                        java.time.Duration.ofMillis(500),
                        java.time.Duration.ofSeconds(1))
                .register(registry);

        this.databaseTimer = Timer.builder("orders.database.duration")
                .description("Order database operation duration")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void recordHandlerDuration(long amount, TimeUnit unit) {
        handlerTimer.record(amount, unit);
    }

    public <T> T recordDatabase(java.util.concurrent.Callable<T> action)
            throws Exception {
        return databaseTimer.recordCallable(action);
    }
}
~~~

Histogram và SLO buckets cần được cấu hình phù hợp với registry/backend. Không phải exporter nào cũng xử lý histogram theo cùng cách; hãy kiểm tra metric thực tế trong Cloud Monitoring hoặc hệ thống metrics đang dùng.

Một số registry hỗ trợ client-side percentile qua `publishPercentiles(0.50, 0.90, 0.95, 0.99)`. Các giá trị đó hữu ích cho process-local view nhưng không nên giả định có thể gộp chính xác giữa nhiều instance. Nếu cần percentile ở cấp service, ưu tiên histogram/distribution aggregation được backend hỗ trợ.

### Giới hạn cardinality

Metric tags phải có tập giá trị nhỏ, ổn định:

- `operation=place_order`
- `dependency=database`
- `outcome=success|failure`
- `revision=stable|canary` hoặc nhãn revision được backend quản lý

Không dùng `orderId`, `customerId`, email, request ID hoặc raw URL path làm tag. Mỗi giá trị mới có thể tạo time series riêng, khiến chi phí và truy vấn tăng nhanh.

## 9. Distributed tracing bằng OpenTelemetry

Metrics cho biết service có tail latency; trace giúp giải thích một request cụ thể chậm ở đâu.

Một trace nên có:
- Root server span cho request hoặc consumer invocation.
- Child span cho các bước nghiệp vụ quan trọng.
- Client span cho database, HTTP API hoặc message publish nếu instrumentation hỗ trợ.
- Error status và exception event khi thao tác thất bại.
- Attributes có giá trị chẩn đoán và cardinality được kiểm soát.

Ví dụ tạo span thủ công trong Java:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class InventoryService {
    private final Tracer tracer;

    public InventoryService(Tracer tracer) {
        this.tracer = tracer;
    }

    public Reservation reserve(String sku, int quantity) {
        Span span = tracer.spanBuilder("inventory.reserve").startSpan();

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("inventory.operation", "reserve");
            span.setAttribute("inventory.quantity", quantity);

            return reserveInternal(sku, quantity);
        } catch (RuntimeException error) {
            span.recordException(error);
            span.setStatus(StatusCode.ERROR, "Inventory reservation failed");
            throw error;
        } finally {
            span.end();
        }
    }

    private Reservation reserveInternal(String sku, int quantity) {
        // Gọi repository và áp dụng quy tắc giữ hàng.
        return new Reservation(sku, quantity, true);
    }
}

record Reservation(String sku, int quantity, boolean reserved) {
}
~~~

Ứng dụng cần OpenTelemetry SDK hoặc Java agent cùng exporter được cấu hình. Chỉ gọi API tạo span mà không có SDK/exporter hoạt động thì span có thể không xuất hiện ở backend.

Không ghi SKU nhạy cảm, customer ID, token hoặc payload đầy đủ vào span nếu không cần. Nếu cần correlation với entity cụ thể, hãy cân nhắc policy dữ liệu và dùng log có kiểm soát.

### Truyền trace context qua ranh giới

Với HTTP, OpenTelemetry thường truyền W3C Trace Context qua `traceparent` và `tracestate` khi instrumentation được cấu hình cho client/server library.

Với queue/event, producer phải truyền trace context qua message attributes theo convention của broker/instrumentation. Consumer trích xuất context và tạo consumer span hoặc span link phù hợp. Nếu context bị mất, trace của producer và consumer có thể tách rời dù event ID giống nhau.

Giữ `eventId` và `correlationId` riêng với trace ID. Trace sampling có thể bỏ một trace; event ID vẫn cần cho deduplication, replay và điều tra nghiệp vụ.

### Sampling và tail latency

Nếu chỉ sample ngẫu nhiên một tỷ lệ nhỏ, request rất chậm có thể không được lưu trace. Có thể:
- Tăng sampling trong môi trường test hoặc khi điều tra.
- Dùng tail-based sampling trong collector nếu kiến trúc hỗ trợ, giữ lại trace lỗi hoặc vượt latency threshold.
- Dựa vào histogram/metrics để phát hiện tail, rồi truy vấn log/trace tương ứng.
- Giữ sampling policy ổn định khi so sánh trước/sau release.

Sampling ảnh hưởng khả năng quan sát, không làm thay đổi latency của request theo định nghĩa metric. Tuy nhiên, instrumentation quá nặng hoặc export đồng bộ có thể ảnh hưởng hiệu năng; exporter nên hoạt động bất đồng bộ theo hướng dẫn SDK.

## 10. Cold start, warm start và initialization

Trong serverless, request đầu tiên trên một instance mới có thể phải trả chi phí khởi tạo runtime và ứng dụng.

Các nguồn cold start thường gặp:

- Tạo execution environment/container mới.
- Khởi động JVM và class loading.
- Khởi tạo Spring application context.
- Nạp dependency, cấu hình và secret.
- Tạo connection pool hoặc client.
- Tải image/container layer hoặc runtime artifact.
- Khởi tạo network interface hoặc kết nối private.

Phân biệt:
- **Initialization duration:** thời gian từ lúc runtime/instance bắt đầu khởi tạo đến khi sẵn sàng.
- **Handler duration:** thời gian code xử lý invocation/request.
- **End-to-end latency:** thời gian caller thực sự chờ, có thể bao gồm init và platform overhead.

Không phải mọi request đầu tiên của user đều là cold start; một instance warm có thể xử lý request ngay. Ngược lại, scale-out có thể tạo một số instance mới ngay cả khi service đã có traffic.

### Đo cold start riêng

Ghi startup duration bằng lifecycle hook hoặc metric của nền tảng. Đối chiếu request latency với log/trace để xác định request có chạy trên instance mới hay không.

Với AWS Lambda, log REPORT có thể hiển thị `Init Duration` cho invocation khởi tạo environment; metric `Duration` chủ yếu phản ánh thời gian thực thi handler. Với Cloud Run, quan sát container startup/instance metrics và request logs; định nghĩa metric nền tảng cần được kiểm tra theo loại service và cấu hình.

Không cộng init duration vào handler duration nếu metric request/platform đã bao gồm thời gian đó. Xác định rõ phần nào đang được tính trong từng metric.

### Cải thiện cold start

- Giảm kích thước artifact/image và dependency không cần thiết.
- Tránh remote call nặng trong static initializer hoặc constructor.
- Tái sử dụng SDK client thread-safe qua warm invocations.
- Giảm thời gian khởi tạo framework và bean.
- Chỉ dùng minimum/provisioned capacity khi latency mục tiêu biện minh cho chi phí.
- Đo lại p95/p99 và startup duration sau mỗi thay đổi.

Không trì hoãn kiểm tra cấu hình hoặc bảo mật thiết yếu chỉ để giảm startup. Function phải fail rõ nếu không thể chạy an toàn.

## 11. Database và connection pool là nguồn tail latency phổ biến

Handler duration tăng không nhất thiết do CPU. Một request có thể dành phần lớn thời gian chờ connection hoặc database.

Tách các phép đo:

1. **Connection acquisition:** thời gian chờ lấy connection từ pool.
2. **Query execution:** thời gian database thực thi truy vấn.
3. **Result transfer/mapping:** thời gian nhận và chuyển kết quả thành object.
4. **Transaction commit:** thời gian commit nếu đo riêng.
5. **Pool wait/timeout:** số request phải chờ hoặc không lấy được connection.

Nếu connection pool nhỏ, concurrency cao có thể làm queue bên trong pool tăng. Nếu pool quá lớn trên mỗi instance, tổng số connection khi autoscale có thể vượt giới hạn database.

Ước lượng giới hạn:
```text
Potential connections ≈ max instances × pool size per instance
```

Đây là giới hạn lý thuyết; số connection thực tế phụ thuộc số instance và cách pool mở kết nối. Hãy đặt max instances, pool size và database connection budget cùng nhau.

### Ví dụ trace cho database

Một trace có thể cho thấy:
- HTTP server span: 900 ms.
- Connection acquire: 520 ms.
- SQL query: 180 ms.
- Serialize/other: 100 ms.

Tối ưu index không giải quyết phần 520 ms chờ pool. Cần điều tra số connection, concurrency, leak, transaction giữ connection quá lâu và max instance count.

## 12. External API, retry và timeout budget

Một dependency bên ngoài có thể có latency biến động và rate limit. Đo riêng:
- DNS/connect/TLS nếu client expose.
- Time to first byte hoặc response duration.
- Số lần retry.
- Backoff time.
- Timeout count.
- Status/error category.

Một logical request retry ba lần có thể có tổng latency lớn hơn nhiều so với một attempt. Dashboard nên phân biệt:
- Duration mỗi attempt.
- Tổng thời gian dependency bao gồm retry.
- Số attempt trên một logical operation.

Đặt timeout dependency thấp hơn timeout tổng request để còn thời gian xử lý fallback và trả response. Exponential backoff có jitter giúp tránh retry đồng loạt, nhưng retry chỉ nên áp dụng cho lỗi tạm thời và thao tác có thể retry an toàn.

Nếu request có timeout 5 giây, không nên để database timeout 5 giây rồi mới bắt đầu serialize response. Cần phân bổ budget cho authentication, database, API ngoài và overhead.

Ví dụ budget:

| Stage | Budget minh họa |
|---|---:|
| Gateway/authentication | 100 ms |
| Java validation/business | 150 ms |
| Database | 700 ms |
| Payment API | 1.500 ms |
| Serialize/response overhead | 150 ms |
| Safety margin | 400 ms |
| **Tổng** | **3.000 ms** |

Đây là budget giả định để minh họa. Budget thật phải dựa trên SLA, percentile đo được và timeout của từng dependency. Các stage song song có thể dùng budget khác với stage tuần tự.

## 13. Queue wait, backlog và consumer processing

Với queue-based function, queue wait thường là một trong những nguyên nhân chính làm tăng business latency.

Theo dõi:
- Message age hoặc oldest unprocessed message.
- Queue depth/backlog.
- Publish-to-consume delay.
- Consumer processing duration.
- Batch size và batch duration.
- Retry count, visibility/ack deadline và DLQ depth.
- Consumer concurrency và số instance.

Nếu queue depth tăng nhưng processing duration ổn định, có thể consumer capacity thấp hơn arrival rate. Nếu queue depth ổn định nhưng message age tăng, có thể có partition/shard bị nghẽn hoặc message bị retry liên tục.

Một consumer batch có thể xử lý nhiều message trong một invocation. Đừng chia tổng batch duration cho số message rồi gọi đó là latency từng message nếu các message có thời điểm đến khác nhau hoặc được xử lý song song. Ghi nhận enqueue timestamp và per-message processing time nếu cần phân tích chính xác.

### Arrival rate và service rate

Nếu tốc độ message đến lớn hơn tốc độ xử lý trong thời gian dài, backlog sẽ tăng.

```text
Backlog growth ≈ arrival rate - processing rate
```

Khi arrival rate cao hơn processing rate, tăng concurrency hoặc số consumer có thể giúp, nhưng phải kiểm tra capacity database/API phía sau. Nếu dependency đã chạm giới hạn, scale consumer chỉ chuyển backlog thành connection storm hoặc throttling.

## 14. Phân tích percentile theo route, revision và dependency

Một p95 tổng của service có thể che một route rất chậm. Hãy phân nhóm theo chiều có giá trị vận hành:

- Route/operation (dùng route template, không dùng raw path ID).
- Revision/version.
- Region.
- Kết quả success/failure.
- Dependency hoặc operation type.
- Trigger type hoặc event type.
- Cold/warm classification nếu nền tảng cung cấp tín hiệu đáng tin.

Ví dụ dashboard:

| Nhóm | p50 | p95 | p99 | Count |
|---|---:|---:|---:|---:|
| GET /orders/{id} | 45 ms | 180 ms | 450 ms | 20.000 |
| POST /orders | 90 ms | 620 ms | 1.900 ms | 8.000 |
| POST /payments | 140 ms | 1.100 ms | 3.200 ms | 2.000 |

Các số liệu là minh họa. POST /payments có p95 cao hơn, nhưng cần xem trace để biết phần chậm nằm ở payment provider, retry hay database.

Đừng tạo metric label theo userId, orderId hoặc requestId. Những dimension đó làm cardinality tăng nhanh. Dùng trace/log để điều tra từng request.

## 15. Cloud metrics, logs và traces

Ba tín hiệu quan sát bổ sung cho nhau:

| Tín hiệu | Vai trò trong phân tích latency |
|---|---|
| Metrics/histogram | Cho biết p50/p95/p99, count, throughput và xu hướng theo thời gian |
| Request/container logs | Cung cấp request ID, revision, status, error và mốc thời gian |
| Distributed traces | Phân rã một request thành các span và chỉ ra critical path |

Trên AWS Lambda, có thể đối chiếu invocation count, duration, error, throttles và concurrent executions với logs/trace. Init duration có thể được thể hiện riêng trong log/telemetry tùy runtime và cấu hình.

Trên Cloud Run, kết hợp request latency, instance count, CPU/memory, startup metrics và structured container logs. Với event-driven workloads, theo dõi queue age/backlog ở broker cùng consumer duration.

Tên metric, đơn vị, resource labels và aggregation khác nhau theo provider và loại integration. Trước khi tạo SLO, xác minh metric đang đo server processing hay caller-perceived latency. Nếu cần trải nghiệm người dùng thực tế, có thể bổ sung client-side measurement hoặc synthetic monitoring.

### Truy vấn log hỗ trợ điều tra

Một log entry hữu ích thường có:
- Trace ID/span ID.
- Request/correlation ID.
- Service và revision.
- Route template hoặc event type.
- Duration và status/outcome.
- Dependency name và error category.

Không log token, secret, payload nhạy cảm hoặc thông tin cá nhân không cần thiết. Log duration nên dùng một đơn vị nhất quán và field name có ý nghĩa.

## 16. Thiết kế SLI/SLO cho latency

SLI latency thường là tỷ lệ request đủ điều kiện hoàn tất dưới ngưỡng.

Ví dụ:
- 99% request hợp lệ hoàn tất trong 500 ms trong cửa sổ 30 ngày.
- 95% request tạo đơn hoàn tất trong 1 giây.
- 99% event được xử lý trong 30 giây kể từ lúc broker nhận message.

Các mục tiêu này là ví dụ, không phải mặc định của nền tảng. Định nghĩa rõ:
- Request/event nào thuộc mẫu số.
- Timeout và lỗi có được tính là bad event không.
- Có tách route/priority tier không.
- Đo từ client, gateway, broker hay application.
- Cửa sổ thời gian và cách tính percentile/histogram.
- Cách xử lý request bị hủy hoặc client disconnect.

Một SLO kiểu “99% request dưới 500 ms” có thể dùng histogram bucket tại 500 ms để tính tỷ lệ good events. Cách này thường dễ tổng hợp qua nhiều instance hơn là cố gắng lấy trung bình p95 của từng instance.

### Tail latency và user impact

Nếu một trang web gọi 20 service song song, xác suất ít nhất một dependency chậm có thể cao ngay cả khi mỗi service có p99 tốt. Fan-out làm tail latency khuếch đại. Hãy đo root request end-to-end và critical path, không chỉ SLO từng dependency.

## 17. Load test để đo percentile đáng tin cậy

Đo latency bằng một vài request thủ công không đủ. Cần load test phản ánh traffic thực tế.

### Các kiểu test

| Kiểu test | Mục tiêu |
|---|---|
| Baseline | Đo service ở tải thấp và cấu hình chuẩn |
| Load test | Xác định latency/throughput ở tải dự kiến |
| Stress test | Tìm điểm bão hòa và hành vi khi vượt capacity |
| Spike test | Quan sát burst traffic và scale-out |
| Soak test | Tìm leak, pool exhaustion hoặc suy giảm theo thời gian |
| Cold-start test | Đo request trên instance mới và startup duration |
| Dependency degradation | Xem hệ thống phản ứng khi database/API chậm hoặc timeout |

### Kịch bản cần giữ thực tế

- Payload, response size và route mix tương tự production.
- Tốc độ đến request (arrival rate) có kiểm soát; không chỉ dùng closed-loop client.
- Concurrency và ramp-up mô phỏng traffic tăng thật.
- Database, cache và external API có behavior gần production.
- Ghi nhận error rate, throughput và percentile cùng lúc.
- Đủ sample count để p95/p99 có ý nghĩa.
- Tách warm run và cold-start run.
- Chạy ở region và network path phù hợp với môi trường đích.

Closed-loop load generator gửi request mới sau khi request trước hoàn tất có thể giảm tốc độ gửi khi service chậm, khiến thiếu tải đúng lúc hệ thống bị nghẽn (coordinated omission). Arrival-rate based test giúp kiểm soát tốc độ request độc lập với thời gian phản hồi.

Không dùng production traffic hoặc dữ liệu nhạy cảm khi chưa có phê duyệt và bảo vệ phù hợp. Không tạo tải lớn lên dependency thật nếu chưa giới hạn và phối hợp với owner.

## 18. Ví dụ điều tra tail latency

### Tình huống A: p50 ổn định, p99 tăng mạnh

- p50 vẫn 80 ms.
- p99 tăng từ 500 ms lên 3 giây.
- Error rate chưa tăng.

Khả năng:
- Cold start khi scale-out.
- Một số request chờ connection pool.
- GC pause hoặc thread contention.
- External API có tail latency.
- Retry/backoff chỉ xảy ra ở một phần request.

Bước điều tra:
1. Chia latency theo revision, route và instance/cold-start indicator.
2. Tìm trace của request trên 1 giây.
3. So sánh child span, pool wait và dependency attempt.
4. Kiểm tra startup log, GC/heap và concurrency.
5. Chạy load test tái hiện ở cùng traffic pattern.

### Tình huống B: handler nhanh nhưng event hoàn tất chậm

- Consumer processing p95 = 70 ms.
- Oldest message age = 25 giây.
- Queue depth tăng liên tục.

Nguyên nhân có thể là consumer throughput thấp hơn arrival rate hoặc giới hạn concurrency. Tối ưu Java handler 10 ms có thể chưa đủ; cần điều chỉnh consumer capacity và dependency budget.

### Tình huống C: toàn request chậm, database span bình thường

- Root HTTP span = 1,2 giây.
- Database span = 80 ms.
- Payment span = 200 ms.

Phần còn lại có thể nằm ở connection acquisition không được instrument, lock trong ứng dụng, auth call, retry, serialization hoặc platform overhead. Kiểm tra span coverage và log stage timing trước khi kết luận.

## 19. Những sai lầm khi đo latency

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ xem average | Che tail latency | Theo dõi p50/p95/p99 và count |
| So sánh percentile từ cửa sổ/sample khác nhau | Kết luận sai | Cùng window, dimension và sample count |
| Lấy trung bình p95 các instance | Không ra p95 toàn service | Dùng histogram/distribution aggregation |
| Cộng p95 của dependency | Không ra p95 end-to-end | Đo root span và phân tích từng trace |
| Dùng wall-clock để đo duration trong JVM | Bị ảnh hưởng clock adjustment | Dùng nanoTime |
| Trừ timestamp từ hai host không đồng bộ | Queue wait sai | Broker timestamp, clock sync và trace |
| Gộp cold start với handler duration | Không biết bottleneck | Đo init riêng |
| Chỉ đo handler, bỏ queue wait | Bỏ sót backlog | Đo event age và queue delay |
| Metric tag chứa request ID | Cardinality bùng nổ | Đưa ID vào log/trace |
| Load test quá ít request | p99 không ổn định | Tăng sample count và lặp lại |
| Retry không được tính vào tổng duration | Đánh giá thấp latency | Đo attempt và logical operation |
| Chỉ xem service metric, không xem client | Bỏ qua network/gateway | Synthetic hoặc client-side latency |

## 20. Checklist đo và tối ưu latency

- [ ] Mỗi metric có định nghĩa start/end, đơn vị và resource scope.
- [ ] Phân biệt client latency, server duration, queue wait và business completion.
- [ ] Có p50, p90/p95, p99 cùng request count.
- [ ] Percentile được tổng hợp từ histogram/distribution phù hợp.
- [ ] Không lấy trung bình percentile của các instance.
- [ ] Root request có trace và child spans cho dependency quan trọng.
- [ ] HTTP và message propagation giữ trace context/correlation ID.
- [ ] Duration trong JVM dùng monotonic clock.
- [ ] Cold start/init được đo riêng với handler duration.
- [ ] Database connection acquisition và query duration được tách.
- [ ] Dependency retry, timeout và attempt count được ghi nhận.
- [ ] Queue age/backlog được theo dõi cùng consumer processing duration.
- [ ] Critical path được xác định trước khi tối ưu.
- [ ] Metric labels có cardinality thấp và không chứa dữ liệu nhạy cảm.
- [ ] SLO latency định nghĩa rõ mẫu số, ngưỡng và cửa sổ.
- [ ] Load test có baseline, load, spike, soak và cold-start scenarios.
- [ ] Sau tối ưu, chạy lại cùng workload và so sánh percentile/error/throughput.

## Tự kiểm tra

1. p50 và p99 mô tả hai phần nào của phân phối latency?
2. Vì sao average có thể tốt dù một nhóm request rất chậm?
3. Client-perceived latency khác application duration như thế nào?
4. Một message có consumer processing duration 40 ms nhưng queue wait 20 giây thì business latency là bao nhiêu?
5. Vì sao không thể cộng p95 database với p95 payment API để suy ra p95 root request?
6. Histogram có ưu điểm gì khi tổng hợp latency từ nhiều instance?
7. Khi đo duration trong JVM, vì sao nên dùng `System.nanoTime()`?
8. Cold start/init duration khác handler duration ở điểm nào?
9. Nếu queue age tăng nhưng consumer processing duration ổn định, cần điều tra điều gì?
10. Vì sao load test theo arrival rate có thể phát hiện tail latency tốt hơn closed-loop test?
11. Khi request gọi nhiều dependency song song, critical path được xác định ra sao?
12. Một SLO “99% request dưới 500 ms” cần xác định rõ những yếu tố nào?

Đo latency hiệu quả bắt đầu từ việc định nghĩa đúng ranh giới. Percentile cho biết phần đuôi của phân phối; histogram giúp tổng hợp giữa nhiều instance; trace cho biết request cụ thể đã dành thời gian ở đâu. Khi đo riêng cold start, handler, dependency, queue wait và business completion, đội phát triển có thể tìm đúng critical path, thiết lập SLO thực tế và xác minh mỗi tối ưu bằng cùng một workload.

