# Không làm telemetry chặn request trong Spring Boot

> **Chương:** Hiệu năng observability  
> **Bài:** Không làm telemetry chặn request  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao telemetry không được chặn request?

Observability giúp hiểu ứng dụng đang làm gì, nhưng chính instrumentation và việc gửi telemetry cũng tiêu tốn tài nguyên. Nếu request thread phải chờ exporter gửi span qua mạng, log appender ghi đĩa chậm hoặc metrics registry thực hiện công việc đồng bộ tốn kém, hệ thống quan sát có thể làm tăng latency của chính hệ thống được quan sát.

**Telemetry không chặn request** nghĩa là đường xử lý nghiệp vụ không phải chờ các công việc xuất telemetry tới backend bên ngoài hoàn tất. Ứng dụng vẫn cần tạo metadata và ghi nhận sự kiện trong giới hạn chi phí nhỏ; việc batch, serialize và gửi dữ liệu nên được xử lý theo cơ chế phù hợp, thường là bất đồng bộ.

Các tín hiệu cần xem xét:
- Metrics: cập nhật meter trong process và scrape/export.
- Traces: tạo span, kết thúc span, sampling, batch và export.
- Logs: tạo log event, format, enqueue, ghi file/stdout và ship tới collector.
- Events/audit: có thể có yêu cầu durability khác với telemetry chẩn đoán.

Không phải mọi thao tác telemetry đều tự động bất đồng bộ. Một API instrumentation có thể thực hiện công việc đồng bộ trong request thread; cần hiểu implementation, exporter, appender và registry đang dùng.

~~~mermaid
flowchart LR
  A["Request thread"] --> B["Business operation"]
  B --> C["Record observation / span / log event"]
  C --> D["Bounded in-process buffer"]
  D --> E["Background worker / batch processor"]
  E --> F["OTLP collector / log backend"]
  C --> G["Metrics registry"]
  G --> H["Scrape / export"]
~~~

## 2. Phân biệt chi phí instrumentation và chi phí export

Một request có thể chịu hai nhóm chi phí:

| Nhóm | Ví dụ | Cách kiểm soát |
| --- | --- | --- |
| Instrumentation | Tạo span, đọc clock, thêm attributes, tag lookup | Giữ operation hợp lý, ít allocation, low-cardinality |
| Export | Serialize, batch, network I/O, retry, compression | Batch processor, async exporter, timeout, bounded queue |
| Logging | Format message, evaluate arguments, appender I/O | Async appender, guard expensive formatting |
| Metrics | Update counter/timer, meter lookup, histogram | Reuse meters, tránh dynamic tags và meter creation |

Bất đồng bộ export không làm instrumentation miễn phí. Nếu mỗi request tạo hàng nghìn spans hoặc serialize payload lớn ngay trên request thread, latency vẫn tăng dù network send chạy nền.

Mục tiêu là giữ công việc đồng bộ ngắn, dự đoán được và có giới hạn; các công việc I/O và batch có thể trì hoãn cần được tách khỏi request path.

## 3. Những thao tác telemetry thường gây blocking

Các lỗi thiết kế thường gặp:
- Gọi exporter trực tiếp trong request thread và chờ response.
- Dùng synchronous log appender ghi file hoặc gửi log qua mạng.
- Gọi remote logging/analytics API trong business method.
- Thực hiện DNS/network lookup để resolve metadata mỗi request.
- Serialize object lớn hoặc đọc request/response body chỉ để log.
- Flush exporter sau từng span.
- Retry telemetry không giới hạn khi collector lỗi.
- Dùng queue không giới hạn khiến memory tăng liên tục.
- Tạo meter/span với tags hoặc attributes có cardinality rất cao.

Ví dụ không nên làm:

~~~java
public Order createOrder(Command command) {
    Order order = orderRepository.save(command);

    // Anti-pattern: request thread waits for remote telemetry service.
    telemetryClient.sendBlocking("order.created", order.id());

    return order;
}
~~~

Nếu telemetry backend chậm, business request cũng chậm. Nếu telemetry backend down, request nghiệp vụ có thể thất bại dù database đã lưu order thành công. Đây là coupling không cần thiết.

## 4. Batch và asynchronous span export

Với OpenTelemetry SDK, BatchSpanProcessor thường được dùng để gom ended spans rồi export ở background. Ứng dụng không phải gửi từng span đồng bộ tới collector.

~~~java
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .addSpanProcessor(
                BatchSpanProcessor.builder(otlpExporter)
                        .setScheduleDelay( Duration.ofSeconds(5))
                        .setMaxQueueSize(2048)
                        .setMaxExportBatchSize(512)
                        .build())
        .build();
~~~

Đây là ví dụ API OpenTelemetry SDK; trong Spring Boot, ưu tiên auto-configuration hoặc starter tương thích thay vì tự tạo thêm SDK/tracer provider nếu Boot đã quản lý. Không đăng ký hai tracer providers cho cùng application.

Batch processor thường có queue hữu hạn. Khi queue đầy, spans mới có thể bị drop theo policy; exporter có thể retry theo giới hạn riêng. Điều này bảo vệ memory và request latency, nhưng cần theo dõi dropped spans và queue saturation.

Tên method/configuration có thể thay đổi theo OTel SDK version. Dùng BOM tương thích và kiểm tra tài liệu version đang triển khai.

## 5. Queue phải có giới hạn

Một async pipeline cần buffer giữa producer (request thread) và consumer (background exporter). Nếu buffer không giới hạn, khi backend chậm hơn tốc độ tạo telemetry, dữ liệu tích tụ đến khi JVM thiếu memory.

Ví dụ:
- Application tạo 10.000 spans/s.
- Exporter chỉ gửi được 4.000 spans/s.
- Backlog tăng 6.000 spans/s.
- Sau 60 giây có thêm khoảng 360.000 spans chờ.

Buffer hữu hạn buộc hệ thống phải có policy khi đầy:
- Drop newest hoặc drop oldest.
- Block producer (thường không phù hợp với request telemetry).
- Sampling/priority policy trước khi enqueue.
- Giảm payload hoặc export rate.
- Tăng consumer capacity có kiểm soát.

Với telemetry chẩn đoán, drop có chủ đích thường tốt hơn làm chậm hoặc làm sập business request. Với audit/business events cần durability, dùng một pipeline lưu trữ bền vững riêng và định nghĩa delivery guarantee rõ ràng.

## 6. Backpressure và overload policy

Backpressure là cách điều chỉnh producer khi consumer không theo kịp. Trong request path, không nên để một telemetry queue gây blocking vô hạn. Chọn overload policy dựa trên loại dữ liệu:

| Dữ liệu | Policy có thể phù hợp |
| --- | --- |
| Debug logs | Drop/sample khi overload |
| Trace spans | Bounded queue, sampling, drop counter |
| Metrics | Aggregation trong process, scrape/export theo chu kỳ |
| Audit records bắt buộc | Durable queue/outbox với retry và delivery policy |
| Security events | Pipeline riêng có kiểm soát loss, alert khi pipeline lỗi |

Không gộp audit event bắt buộc với trace/debug telemetry rồi áp dụng drop policy chung. Mỗi loại dữ liệu có yêu cầu durability và privacy khác nhau.

Theo dõi queue depth, enqueue failure, dropped event count, exporter errors, export duration và worker utilization. Không tạo thêm log đồng bộ cho mỗi lần telemetry queue drop; dùng counter/gauge và log có sampling để tránh overload thứ cấp.

## 7. Micrometer Observation trong request path

Micrometer Observation cung cấp lifecycle để ghi nhận operation. Observation có thể được xử lý bởi handlers tạo metrics và tracing. Phần tạo observation/low-cardinality key values vẫn có chi phí trong thread thực thi.

~~~java
Observation.createNotStarted("orders.create", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(() -> orderService.create(command));
~~~

Ví dụ minh họa API đồng bộ. Handler có thể tạo span và cập nhật metrics. Export span có thể được batch/async tùy tracing bridge và exporter configuration.

Để giảm overhead:
- Chỉ instrument boundary có ý nghĩa.
- Dùng low-cardinality values hữu hạn.
- Không tạo hàng loạt child spans cho từng dòng dữ liệu nhỏ.
- Tránh tính attribute đắt tiền nếu span bị unsampled và giá trị không cần cho metrics.
- Không gọi remote service để bổ sung tags.
- Dùng convention để chuẩn hóa metadata thay vì lặp logic phức tạp.

Không tự viết Observation handler có thao tác network đồng bộ. Handler chạy trong lifecycle start/stop và có thể ảnh hưởng trực tiếp tới request nếu implementation blocking.

## 8. Sampling giúp giảm chi phí như thế nào?

Sampling quyết định trace nào được giữ/export. Head sampling có thể quyết định sớm khi trace bắt đầu; tail sampling thường quyết định sau khi collector nhận đủ spans hoặc chờ một cửa sổ.

Ví dụ head sampling probability 10% có thể giảm số traces export trong tải bình thường. Tuy nhiên, nếu cần giữ tất cả lỗi hoặc slow traces, cần policy phù hợp hơn hoặc tail sampling tại collector.

Sampling không nên được hiểu là bảo đảm giữ chính xác 10% mọi nhóm traffic. Kết quả phụ thuộc sampler, parent-based behavior, trace flags và distribution.

Các lưu ý:
- Giữ trace context propagation kể cả khi trace không được export nếu integration hỗ trợ.
- Không dùng sampling để thay metrics counters.
- Đừng tạo span chỉ để đếm số request; dùng Counter.
- Tránh log trace body/attributes nhạy cảm trước khi sampling.
- Theo dõi sampled/dropped trace rates.

Sampling giảm export load nhưng không loại bỏ mọi chi phí instrumentation, và không thay thế queue capacity planning.

## 9. Metrics: cập nhật tại chỗ, export riêng

Micrometer Counter/Timer thường cập nhật state trong process. Với Prometheus, scraper đọc metrics qua endpoint; request nghiệp vụ không cần gọi Prometheus cho mỗi counter increment.

~~~java
@Component
public class OrderMetrics {

    private final Counter created;

    public OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
                .tag("channel", "web")
                .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }
}
~~~

Tạo meter một lần và tái sử dụng. Không tạo tag value động theo order ID hoặc user ID. Dynamic meter creation có thể làm registry phình to và tốn CPU/memory.

Histogram/percentile configuration có chi phí CPU và memory. Chỉ bật buckets phù hợp cho các latency quan trọng; tránh hàng trăm buckets cho hàng nghìn tag combinations.

## 10. Logging bất đồng bộ

Logging có thể trở thành bottleneck nếu request thread chờ file I/O, network appender hoặc format message lớn.

Các lựa chọn:
- Ghi stdout/stderr để runtime/agent thu thập, nếu platform logging pipeline hỗ trợ.
- Dùng async appender với queue hữu hạn.
- Tránh synchronous network appender trong request path.
- Giảm log volume ở hot path.
- Dùng parameterized logging để tránh format khi level bị tắt.
- Không log payload hoặc stack trace lặp lại ở mọi layer.

Ví dụ parameterized logging:

~~~java
log.debug("Order created id={} channel={}", orderId, channel);
~~~

Nếu DEBUG bị tắt, logging framework có thể tránh format message. Nhưng biểu thức argument được tính trước khi gọi method; tránh gọi function đắt tiền trong argument:

~~~java
// Avoid expensive work on every request:
log.debug("Request details={}", buildLargeDiagnosticPayload());
~~~

Có thể kiểm tra log level trước khi tính payload, hoặc tốt hơn bỏ payload khỏi hot path và ghi metadata nhỏ đã chuẩn hóa.

Async appender có trade-off: queue đầy có thể drop log, và log có thể chưa được ghi khi process crash. Chọn queue size, discard policy, shutdown flush và durability theo yêu cầu.

## 11. Không dùng remote logging như business dependency

Không gọi HTTP endpoint của log analytics trực tiếp trong controller/service để ghi từng event. Việc đó biến telemetry backend thành dependency đồng bộ.

~~~java
// Avoid this pattern in request handling:
logAnalyticsClient.publishBlocking(event);
~~~

Dùng logging framework/appender hoặc agent/collector phù hợp. Nếu event cần đảm bảo không mất (ví dụ audit), persist nó theo transaction/outbox hoặc durable messaging rồi xử lý riêng.

Không nên đánh đổi consistency nghiệp vụ lấy việc gửi log thành công. Một request tạo order không nên trả 500 chỉ vì log collector đang unavailable sau khi order đã được commit.

## 12. Timeout, retry và circuit breaker cho exporter

Exporter gọi collector/backend cần timeout hữu hạn. Retry phải có giới hạn, backoff và jitter; retry vô hạn làm backlog và network pressure tăng.

Cần xác định:
- Export timeout.
- Retry max attempts hoặc retry duration.
- Exponential backoff/jitter.
- Queue capacity.
- Export batch size.
- Behavior khi collector unavailable.
- Shutdown flush deadline.

Circuit breaker có thể ngăn exporter liên tục gọi một endpoint lỗi, nhưng cần hiểu exporter SDK đã có retry policy chưa. Tránh thêm nhiều tầng retry làm nhân số requests.

Telemetry export failure thường không nên làm business request fail. Có thể tăng exporter error metric và báo alert qua một kênh độc lập.

## 13. Context propagation khi chuyển sang background worker

Khi span được tạo trong request và export ở background thread, exporter cần nhận đúng span context đã được capture trong span data. Không dựa vào ThreadLocal/MDC của request thread còn tồn tại khi worker chạy.

Với custom async processing:
- Capture context tại boundary thích hợp.
- Propagate context qua executor/reactive context theo integration.
- Khôi phục/clear context sau task để tránh rò context giữa requests.
- Không gắn traceId bằng static mutable variable.
- Không tự tạo parent-child relationship sai khi batch nhiều spans.

Một log được ghi ở background thread có thể thiếu MDC traceId nếu context không được propagate. Điều này không nên được sửa bằng cách giữ nguyên ThreadLocal của request thread sau khi request kết thúc.

## 14. Shutdown và flush telemetry

Khi JVM shutdown, batch processor có thể còn spans/logs trong queue. Cần flush trong thời hạn hữu hạn để tránh mất dữ liệu cuối cùng.

Quy trình:
1. Ngừng nhận request mới hoặc bắt đầu graceful shutdown.
2. Hoàn tất các operation đang chạy theo shutdown budget.
3. Flush/shutdown exporter và async appenders.
4. Chờ tối đa thời gian cấu hình.
5. Đóng resources và dừng process.

Không gọi forceFlush sau mỗi request. Flush định kỳ hoặc khi shutdown theo SDK lifecycle. Shutdown timeout phải nhỏ hơn platform termination grace period để process có thời gian hoàn tất.

Nếu collector đang down, flush có thể timeout. Business shutdown vẫn cần kết thúc đúng hạn; không chờ vô hạn chỉ để gửi hết telemetry.

## 15. Đo overhead của observability

Không đánh giá instrumentation chỉ bằng cảm giác. So sánh workload giống nhau ở các cấu hình:
- Telemetry disabled (baseline).
- Metrics only.
- Tracing với sampling.
- Logging ở mức thông thường.
- Full observability/export enabled.
- Collector chậm hoặc unavailable.

Đo:
- Request p50/p95/p99.
- Throughput.
- CPU và allocation rate.
- GC pause/heap.
- Request thread utilization.
- Telemetry queue depth/drop count.
- Export duration/errors.
- Log queue saturation.
- Memory khi collector unavailable.

Dùng load test có warm-up, concurrency và traffic mix ổn định. Kiểm tra cả steady state và burst; async queue có thể che latency trong thời gian ngắn nhưng backlog sẽ tăng nếu consumer không theo kịp.

## 16. Troubleshooting telemetry làm chậm request

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| p95 tăng khi bật tracing | Span creation/attributes quá nhiều hoặc exporter sync | Profile request thread, inspect processor |
| Request chậm khi collector down | Exporter blocking/retry trong request path | Async batch, timeout, bounded queue |
| Heap tăng dần | Queue không giới hạn hoặc backlog không drain | Queue size, drop policy, export rate |
| CPU tăng mạnh | Serialization, compression, cardinality hoặc log formatting | CPU profile, batch size, tags |
| Log request bị trễ | Sync file/network appender hoặc queue backlog | Appender config và queue metrics |
| Trace bị mất khi tải cao | Batch queue đầy hoặc sampler drop | Dropped spans, queue saturation |
| Shutdown mất spans cuối | Chưa flush hoặc deadline quá ngắn | SDK lifecycle, shutdown timeout |
| Trace ID mất ở worker | Context không được propagate | Executor/Reactor context integration |
| Request fail khi telemetry backend lỗi | Telemetry bị đặt trong critical path | Tách async/durable pipeline |
| Metrics registry phình to | Dynamic tags/meter creation | Tag cardinality và meter filters |
| Duplicate export/request retries | Retry chồng tầng hoặc nhiều SDK | Exporter config và ownership |
| Async log mất event khi crash | Queue chưa flush/durability không đủ | Chọn durable path nếu event bắt buộc |

### Quy trình điều tra

1. So sánh latency với telemetry tắt và bật từng signal.
2. Profile request threads để tìm network/file I/O hoặc serialization.
3. Kiểm tra exporter/appender có chạy đồng bộ không.
4. Xem queue capacity, backlog, drop count và export throughput.
5. Kiểm tra retries/timeouts khi collector unavailable.
6. Rà soát span count, attributes, log volume và metric cardinality.
7. Kiểm tra context propagation qua background worker.
8. Test graceful shutdown và flush deadline.
9. Lặp lại load test với cùng workload sau khi sửa.

## 17. Tình huống thực tế: collector chậm làm API tăng latency

**Bối cảnh:** order-service bật tracing và export OTLP. Khi collector bị quá tải, p95 API tăng từ 120 ms lên 900 ms. CPU tăng và request threads có nhiều stack đang chờ network.

### Bước 1 — tìm I/O trong request path

Thread dump/profile cho thấy exporter được gọi đồng bộ khi span kết thúc. Mỗi request chờ collector response.

### Bước 2 — chuyển sang batch/async processor

Dùng BatchSpanProcessor phù hợp SDK/Boot integration, queue hữu hạn và batch size hợp lý. Không tự tạo tracer provider thứ hai nếu auto-configuration đã quản lý SDK.

### Bước 3 — thiết lập overload policy

Đặt queue capacity, export timeout và retry giới hạn. Theo dõi dropped spans khi collector không theo kịp. Không block request thread để chờ queue có chỗ.

### Bước 4 — giảm chi phí instrumentation

Loại span quá chi tiết, bỏ attributes đắt tiền và kiểm soát sampling. Dùng metrics để giữ request/error counts đầy đủ.

### Bước 5 — kiểm chứng

Mô phỏng collector chậm/down. So sánh request p95/p99, CPU, queue depth, dropped spans và export errors. API phải tiếp tục phục vụ request trong giới hạn tài nguyên; telemetry có thể suy giảm theo overload policy đã chọn.

**Kết quả mong muốn:** lỗi của telemetry backend không biến thành lỗi hoặc latency tăng dây chuyền của business API; hệ thống vẫn đo được mức telemetry bị drop.

## 18. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — đo baseline

Chạy load test với telemetry tắt, sau đó bật metrics, tracing và logging từng bước. So sánh p95/p99, CPU, allocations và throughput.

### Bài tập B — collector unavailable

Ngắt collector trong môi trường test. Quan sát request latency, exporter queue, retry, drop count và heap. Xác minh request không chờ network export.

### Bài tập C — bounded queue

Tạo tốc độ span generation cao hơn export throughput. Quan sát queue đầy và policy drop. Tính backlog growth và xác định capacity/alert phù hợp.

### Bài tập D — async logging

So sánh synchronous appender với async appender dưới tải. Mô phỏng queue saturation và process shutdown. Xác định log nào được phép drop và log nào cần durable storage.

### Bài tập E — context propagation

Tạo request span, schedule background task và ghi log trong worker. Xác minh trace context đúng, không rò MDC giữa tasks và không tạo parent span sai.

### Bài tập F — graceful shutdown

Tạo spans còn trong batch queue rồi gửi SIGTERM. Xác minh flush hoàn tất trong termination grace period và process vẫn shutdown nếu collector không phản hồi.

### Câu hỏi tự kiểm tra

1. Vì sao async export không làm instrumentation miễn phí?
2. BatchSpanProcessor giúp gì cho request latency?
3. Queue không giới hạn gây rủi ro gì?
4. Khi telemetry queue đầy, những overload policy nào có thể dùng?
5. Vì sao audit events không nên dùng chung drop policy với debug traces?
6. Micrometer Observation có thể gây chi phí đồng bộ nào?
7. Metrics Counter khác span export thế nào?
8. Async logging có trade-off durability nào?
9. Vì sao không gọi remote log API đồng bộ trong controller?
10. Sampling giảm chi phí nào và không giảm chi phí nào?
11. Timeout/retry exporter cần giới hạn ra sao?
12. Context cần được propagate thế nào tới background worker?
13. Vì sao không flush exporter sau từng request?
14. Shutdown cần flush telemetry trong budget nào?
15. Làm thế nào chứng minh telemetry không làm request chậm dưới tải?

**Tiêu chí hoàn thành:** phân biệt instrumentation và export cost; cấu hình batch/async exporter; dùng bounded queue và overload policy; không gọi telemetry backend đồng bộ trong request; kiểm soát logging, sampling, retry và cardinality; propagate context; flush khi shutdown; benchmark khi collector chậm hoặc unavailable.

## 19. Ghi nhớ

- Telemetry không được làm business request chờ network/file export hoàn tất.
- Instrumentation vẫn có chi phí CPU/allocation dù exporter chạy bất đồng bộ.
- Batch exporter gom spans và gửi ở background; cần queue hữu hạn và export timeout.
- Queue không giới hạn có thể làm heap tăng đến OOM khi backend chậm.
- Khi overload, chọn drop/sampling policy cho telemetry chẩn đoán; dữ liệu audit bắt buộc cần durable pipeline riêng.
- Micrometer Observation handlers không nên thực hiện network I/O đồng bộ trong start/stop callbacks.
- Metrics thường cập nhật registry tại chỗ; tránh dynamic meter/tag creation.
- Async logging giảm blocking nhưng có trade-off queue loss và shutdown durability.
- Sampling giảm export volume nhưng không thay metrics và không loại bỏ toàn bộ instrumentation cost.
- Retry/timeout exporter phải bounded; telemetry backend lỗi không nên làm business API fail.
- Context propagation phải đúng khi chuyển sang worker thread; không giữ ThreadLocal/MDC sau request.
- Flush telemetry có deadline khi shutdown; không chờ vô hạn.
- Dùng load test và profiling để đo p95/p99, CPU, heap, queue saturation và dropped telemetry.

## Tài liệu tham khảo

- [OpenTelemetry Java — Exporters and SDK](https://opentelemetry.io/docs/languages/java/sdk/)
- [OpenTelemetry Java — BatchSpanProcessor](https://opentelemetry.io/docs/languages/java/sdk/#span-processors)
- [OpenTelemetry Collector — Scaling and Resiliency](https://opentelemetry.io/docs/collector/resiliency/)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/)

