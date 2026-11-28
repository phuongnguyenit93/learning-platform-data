# Cảnh báo mất context hoặc trace đứt đoạn

> **Chương:** Alerting  
> **Bối cảnh:** Spring Modulith giúp quan sát ranh giới application module và tương tác giữa các phần trong ứng dụng Spring Boot. Khi request đi qua nhiều module, executor hoặc service, trace context cần được truyền đúng để các span liên kết thành một trace có thể điều tra. Bài này hướng dẫn phát hiện context bị mất, trace bị chia đoạn và lỗi export; xây metric, alert rule và runbook để đội vận hành xử lý đúng nguyên nhân.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt mất trace context với trace bị sampling, thiếu instrumentation hoặc exporter không gửi được dữ liệu.
2. Nhận diện ranh giới dễ làm đứt context: HTTP, `@Async`, executor, event listener và message broker.
3. Bổ sung metric có cardinality thấp để đếm các trường hợp context bắt buộc nhưng không hiện diện.
4. Tạo Prometheus alert cho context missing, Collector export failure, queue saturation và trace pipeline silence.
5. Thiết kế synthetic trace probe để kiểm tra quan hệ parent-child xuyên service/module.
6. Phân biệt lỗi thật với root span hợp lệ, asynchronous span link và trace không được sample.
7. Viết runbook điều tra, phân cấp severity và xử lý cảnh báo theo bằng chứng.

## 1. Vì sao cần cảnh báo mất context?

Một request đặt hàng có thể đi qua các module:

```text
HTTP POST /orders
└── orders.CheckoutService.checkout
    ├── pricing.QuoteService.quote
    ├── payments.PaymentService.authorize
    └── notifications.ReceiptWorker.send (async)
```

Trace context giúp các span mô tả cùng một luồng xử lý được liên kết. Khi context bị mất ở một ranh giới:

- Log của worker có thể không còn trace ID để tra cứu.
- Span ở service nhận có thể trở thành root của trace mới.
- Trace backend có thể hiển thị hai trace rời nhau cho cùng một hoạt động nghiệp vụ.
- Người trực vận hành khó xác định lỗi bắt đầu ở module nào.
- Thời gian xử lý tổng thể và quan hệ nhân quả có thể bị hiểu sai.

Một trace đứt đoạn không nhất thiết làm nghiệp vụ thất bại. Request, event listener hoặc tác vụ async vẫn có thể hoàn thành, nhưng dữ liệu quan sát không còn mô tả được quan hệ mong muốn.

**Alerting cần phát hiện sự suy giảm khả năng quan sát**, đồng thời giữ riêng cảnh báo lỗi nghiệp vụ. Không dùng trace missing làm đại diện trực tiếp cho mọi lỗi của ứng dụng.

## 2. Phân loại hiện tượng trước khi tạo alert

Các triệu chứng trông giống nhau nhưng nguyên nhân khác nhau:

| Hiện tượng | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| Context không được truyền | Ở boundary bắt buộc phải có parent nhưng current span/context không tồn tại | Kiểm tra propagation, executor, proxy và transport headers |
| Trace bị chia thành trace mới | Span ở downstream có trace ID khác dù cùng một request flow | Kiểm tra inject/extract `traceparent`, B3 hoặc message headers |
| Span không được instrument | Nghiệp vụ chạy nhưng không có span ở một method/module | Kiểm tra module entry instrumentation, Observation handler và proxy boundary |
| Trace bị sampling | Không có trace trên backend theo tỷ lệ lấy mẫu dự kiến | Kiểm tra sampler, parent sampled flag và sampling policy |
| Export thất bại | SDK/Collector ghi timeout, queue full, HTTP/gRPC error | Kiểm tra exporter, Collector và backend |
| Backend chưa hiển thị | Export thành công nhưng trace đến muộn hoặc query không thấy | Kiểm tra ingestion delay, tenant, time range và retention |
| Quan hệ async khác kỳ vọng | Worker tạo root hoặc span link thay vì child | Xác định semantics của event/job và context capture tại thời điểm submit |

Không tạo một alert duy nhất tên “Trace broken” cho tất cả hiện tượng. Mỗi alert nên chỉ ra lớp có khả năng hỏng và tín hiệu đo được.

## 3. Hiểu đúng trace context và parent span

Trace context thường mang:

- `traceId`: định danh trace.
- `spanId`: định danh span.
- `parentSpanId`: định danh span cha trực tiếp, nếu có.
- Trace flags, trong đó có sampled bit.
- Baggage hoặc metadata truyền theo context nếu được cấu hình.

Ở HTTP, W3C Trace Context thường dùng header `traceparent`:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Service gửi inject context vào request; service nhận extract context trước khi tạo server span. Nếu header bị proxy xóa, client không dùng instrumentation hoặc server không extract đúng format, trace có thể bị tách.

### 3.1. Cùng trace ID chưa đủ để chứng minh parent-child trực tiếp

Hai span là parent-child trực tiếp khi:

1. Cùng `traceId`.
2. `child.parentSpanId` bằng `parent.spanId`.

Nếu hai span chỉ có cùng trace ID nhưng cùng parent khác, chúng là sibling. Nếu downstream có trace ID mới, có thể context đã mất hoặc ứng dụng cố ý bắt đầu trace mới.

### 3.2. Root span không phải lúc nào cũng là lỗi

Một trace root hợp lệ có thể xuất hiện khi:

- Đây là request đầu tiên của trace.
- Job được khởi chạy độc lập từ scheduler.
- Một message được tạo từ hệ thống không truyền trace context.
- Hệ thống cố ý tách trace và dùng span link để liên hệ công việc.
- Context propagation không được kỳ vọng tại boundary đó.

Chỉ cảnh báo parent missing tại boundary mà kiến trúc quy định phải có parent context. Không cảnh báo mọi root span trên toàn hệ thống.

### 3.3. Async có thể dùng parent-child hoặc span link

Với `@Async` trong cùng request flow, ứng dụng thường muốn truyền context từ thread gửi sang executor để worker tạo span con. Với một workflow message/job độc lập hoặc xử lý bất đồng bộ kéo dài, có thể dùng trace mới và span link để liên hệ trace nguồn.

Alert rule phải dựa trên semantics đã chọn. Không ép mọi tác vụ bất đồng bộ phải có `parentSpanId` trực tiếp nếu thiết kế của hệ thống sử dụng span link hoặc detached trace.

## 4. Những ranh giới dễ làm mất context

### 4.1. HTTP client và server

Kiểm tra:

- Client có dùng builder/instrumentation được Spring Boot cấu hình không?
- Trace propagation format ở hai service có tương thích không?
- Reverse proxy/API gateway có giữ header `traceparent` hoặc B3 không?
- Server có extract context trước khi tạo server span không?

Không tự tạo HTTP client bỏ qua builder auto-configured nếu dự án trông chờ tracing instrumentation tự động.

### 4.2. `@Async` và thread pool

Thread pool tái sử dụng thread. `ThreadLocal` trên request thread không tự chuyển sang executor thread. Với executor phù hợp, dùng `ContextPropagatingTaskDecorator`:

```java
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(100);
executor.setThreadNamePrefix("async-");
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

Gắn decorator vào đúng executor mà `@Async("...")` sử dụng. Nếu dùng Spring Boot auto-configured executor, kiểm tra property propagation có được hỗ trợ ở phiên bản Boot đang chạy.

### 4.3. Spring Modulith event listener

`@ApplicationModuleListener` có semantics bất đồng bộ và transaction riêng theo cấu hình Spring Modulith. Việc listener chạy sau commit không tự bảo đảm trace context của publisher đã được truyền. Kiểm tra executor/dispatcher và propagation mechanism thực tế.

Một event có thể được xử lý thành công nhưng listener span không nằm trong trace request gốc. Đây là vấn đề observability nếu thiết kế yêu cầu liên kết, nhưng không nhất thiết là lỗi nghiệp vụ.

### 4.4. Message broker

Khi publish message, trace context phải được inject vào message headers; consumer phải extract context trước khi tạo consumer span. Cơ chế cụ thể phụ thuộc Kafka, RabbitMQ, JMS hoặc integration được dùng.

Nếu message bị serialize nhưng headers không được truyền, consumer thường tạo trace mới. Nếu hệ thống dùng span link cho consumer, kiểm tra link thay vì chỉ kiểm tra parent ID.

### 4.5. Reactor và callback

Reactor quản lý context qua Reactor `Context`; chuyển qua `ThreadLocal` cần cơ chế context propagation phù hợp. Callback tự tạo, `CompletableFuture`, scheduler hoặc executor ngoài Spring có thể không giữ context nếu không được bọc đúng cách.

## 5. Instrument metric cho context missing

Trace backend không phải lúc nào cũng thuận tiện để tạo alert khi một boundary thiếu parent. Một cách rõ ràng là ghi một counter Micrometer tại boundary mà context được kỳ vọng.

### 5.1. Tạo counter có tag giới hạn

Ví dụ worker receipt phải nhận trace context từ request đã submit task:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;

@Component
class TraceContextDiagnostics {

    private final Tracer tracer;
    private final Counter missingReceiptContext;

    TraceContextDiagnostics(Tracer tracer, MeterRegistry registry) {
        this.tracer = tracer;
        this.missingReceiptContext = Counter.builder("app.observability.context.missing")
                .description("Số lần thiếu trace context tại boundary cần propagation")
                .tag("boundary", "receipt-worker")
                .tag("expected", "present")
                .register(registry);
    }

    void checkReceiptWorkerContext() {
        if (tracer.currentSpan() == null) {
            missingReceiptContext.increment();
        }
    }
}
```

Gọi check ở đầu worker:

```java
@Async("contextAwareExecutor")
public CompletableFuture<Void> sendReceipt(UUID orderId) {
    traceContextDiagnostics.checkReceiptWorkerContext();
    // Thực hiện gửi receipt.
    return CompletableFuture.completedFuture(null);
}
```

Đây là metric chẩn đoán tại một boundary cụ thể. Tùy tracer bridge và sampler, context không sampled vẫn có thể được biểu diễn bằng non-recording span thay vì `null`. Vì vậy, cần kiểm thử hành vi của implementation đang dùng; `currentSpan() == null` chỉ đo absence theo contract quan sát của boundary, không phải phép đo sampled flag.

Nếu cần kiểm tra sampled state, parent-child hoặc trace ID xuyên transport, dùng API/context phù hợp và synthetic integration test; không suy diễn từ `currentSpan() == null`.

### 5.2. Metric name trên Prometheus

Micrometer meter:

```text
app.observability.context.missing
```

Khi xuất qua Prometheus registry, counter thường được chuẩn hóa thành:

```text
app_observability_context_missing_total
```

Tên thực tế cần xác nhận từ `/actuator/prometheus`, vì naming convention/registry có thể thay đổi.

### 5.3. Giữ cardinality thấp

Tag nên dùng các giá trị hữu hạn:

```text
boundary = receipt-worker | payment-client | order-event-consumer
expected = present
service  = shop-service
```

Không đưa các giá trị sau vào metric tag:

- `traceId` hoặc `spanId`.
- `orderId`, `userId`, email hoặc tenant ID không giới hạn.
- URL có path parameter.
- Exception message hoặc stack trace.
- Tên class/method được tạo động từ dữ liệu đầu vào.

Metric tag có cardinality cao có thể làm Prometheus và metrics backend tăng số time series nhanh chóng. Dữ liệu định danh một request nên nằm trong log/trace có kiểm soát, không phải label của counter.

### 5.4. Không đếm context missing ở mọi nơi

Chỉ tăng counter khi boundary có hợp đồng rõ ràng rằng context phải hiện diện. Ví dụ:

- Async task được submit từ một request đang có trace.
- HTTP client call được thực hiện trong một request đã instrument.
- Consumer phải nhận trace header do producer nội bộ gửi.

Không tăng counter cho scheduler job root, cron task độc lập hoặc message consumer độc lập không có trace metadata nếu thiết kế không yêu cầu parent.

## 6. Kiểm tra trace bị đứt bằng synthetic probe

Metric context missing chỉ quan sát code path được instrument. Một synthetic probe có thể kiểm tra toàn bộ đường đi:

1. Gửi request qua gateway/service nguồn.
2. Đi qua một module bean boundary.
3. Gọi downstream service hoặc enqueue message.
4. Chờ worker/consumer hoàn tất.
5. Truy vấn trace backend theo correlation marker của lần probe.
6. Kiểm tra các span có cùng trace ID và quan hệ parent-child/span link đúng thiết kế.

### 6.1. Những assertion nên có

| Assertion | Điều cần xác nhận |
| --- | --- |
| Root span tồn tại | Ingress instrumentation tạo span đầu vào |
| Downstream server span có cùng trace ID | HTTP propagation hoạt động |
| Parent ID đúng | Quan hệ parent-child trực tiếp đúng kỳ vọng |
| Async worker có context hoặc link | Executor/event/message propagation đúng semantics |
| Module entry span xuất hiện | Spring Modulith instrumentation bao phủ boundary đã thử |
| Trace được export | SDK/Collector/backend tiếp nhận dữ liệu |

Không chỉ kiểm tra “có trace”. Hai trace độc lập vẫn có thể cùng xuất hiện cho một business flow mà không được liên kết.

### 6.2. Chọn correlation marker an toàn

Để tìm trace của probe, dùng một marker không nhạy cảm và có thời hạn, ví dụ tên operation cố định hoặc test run ID trong log. Nếu cần gắn ID vào span, dùng attribute có kiểm soát và không dùng giá trị này làm Prometheus label.

Không đưa token, email, dữ liệu khách hàng hoặc nội dung message vào span attribute chỉ để synthetic test dễ tìm.

### 6.3. Tần suất probe

Chọn tần suất đủ phát hiện lỗi mà không gây tải không cần thiết. Một probe mỗi vài phút cho mỗi môi trường thường dễ vận hành hơn việc tạo hàng trăm trace thử mỗi giây. Tần suất cụ thể phụ thuộc latency yêu cầu và chi phí backend.

Synthetic probe cần có timeout tổng thể và dọn dữ liệu thử. Nếu worker bất đồng bộ chậm, phân biệt probe timeout với trace context missing.

## 7. Cảnh báo cho trace exporter và Collector

Một trace có thể bị mất sau khi context đã được truyền đúng. Cần alert riêng cho pipeline export.

### 7.1. Các tín hiệu nên theo dõi

Tùy phiên bản OpenTelemetry SDK/Collector và cấu hình internal telemetry, các metric thường gặp gồm:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| SDK span queue size/capacity | Số span đang chờ và sức chứa queue trong ứng dụng |
| SDK dropped/processed/exported spans | Số span được xử lý, drop hoặc export theo định nghĩa của SDK |
| Collector receiver accepted/refused spans | Span Collector nhận hoặc từ chối |
| Collector processor dropped spans | Span bị processor loại |
| Collector exporter send failed spans | Span export tới backend thất bại |
| Collector exporter queue size/capacity | Áp lực queue ở exporter Collector |
| Export duration | Thời gian gửi batch |

Tên metric và label có thể đổi theo phiên bản Collector/SDK hoặc Prometheus naming convention. Trước khi tạo alert, đọc output metrics thực tế của Collector và ứng dụng.

### 7.2. Ví dụ metric Collector thường gặp

Một số bản OpenTelemetry Collector expose các metric như:

```text
otelcol_receiver_accepted_spans
otelcol_receiver_refused_spans
otelcol_processor_dropped_spans
otelcol_exporter_send_failed_spans
otelcol_exporter_queue_size
otelcol_exporter_queue_capacity
```

Chỉ dùng các tên/label sau khi xác nhận chúng tồn tại trên endpoint telemetry của bản Collector đang triển khai. Một số metric có thể bị tắt, đổi tên hoặc không có trong bản phân phối đang dùng.

## 8. Prometheus alert rules

Ví dụ sau giả định Prometheus scrape được metric Micrometer context guard và telemetry metrics của Collector. Đây là mẫu để điều chỉnh theo tên metric thực tế.

### 8.1. Cảnh báo context missing tại worker

```yaml
groups:
  - name: application-trace-context
    rules:
      - alert: ExpectedTraceContextMissing
        expr: increase(app_observability_context_missing_total{boundary="receipt-worker"}[5m]) > 0
        for: 1m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Trace context missing at receipt worker"
          description: "Async receipt worker received tasks without the expected trace context."
          runbook_url: "https://runbooks.example/trace-context-missing"
```

Alert kích hoạt khi counter tăng trong cửa sổ 5 phút và tồn tại ít nhất 1 phút. Nếu boundary có tần suất rất thấp, cân nhắc bỏ `for` hoặc điều chỉnh cửa sổ để không làm trễ cảnh báo.

### 8.2. Cảnh báo Collector export failure

```yaml
groups:
  - name: otel-collector
    rules:
      - alert: OTelExporterSendFailures
        expr: increase(otelcol_exporter_send_failed_spans[5m]) > 0
        for: 2m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "OpenTelemetry Collector cannot export spans"
          description: "Collector exporter has failed to send spans during the last five minutes."
```

Metric name có thể khác ở bản Collector. Khi dùng exporter nhiều backend, nên thêm label exporter phù hợp để xác định đích bị lỗi.

### 8.3. Cảnh báo queue gần đầy

```yaml
groups:
  - name: otel-collector
    rules:
      - alert: OTelExporterQueueNearCapacity
        expr: |
          otelcol_exporter_queue_capacity > 0
          and
          otelcol_exporter_queue_size / otelcol_exporter_queue_capacity > 0.8
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "OpenTelemetry exporter queue is near capacity"
          description: "Exporter queue usage is above 80 percent for five minutes."
```

Nếu queue metric không được bật, dùng exporter metrics tương đương của phiên bản đang chạy. Khi queue gần đầy, xem throughput backend, retry, network và kích thước batch.

### 8.4. Cảnh báo Collector từ chối spans

```yaml
groups:
  - name: otel-collector
    rules:
      - alert: OTelReceiverRefusingSpans
        expr: increase(otelcol_receiver_refused_spans[5m]) > 0
        for: 1m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "OpenTelemetry Collector refused spans"
          description: "The Collector refused incoming spans; inspect receiver limits and memory pressure."
```

### 8.5. Cảnh báo trace pipeline im lặng

Không nên alert chỉ vì số span bằng 0: service có thể không có traffic, trace có thể bị sampling hoặc backend có độ trễ ingest. Cần kết hợp tín hiệu traffic với span metrics và một ngưỡng đủ lớn.

Ví dụ nếu đã cấu hình Collector spanmetrics connector và có HTTP request counter:

```promql
sum(rate(traces_spanmetrics_calls_total[10m])) == 0
and
sum(rate(http_server_requests_seconds_count[10m])) > 1
```

Đây là biểu thức minh họa. Tên metric spanmetrics phụ thuộc connector/exporter và naming convention; điều kiện traffic cần phù hợp với service. Với sampling thấp, điều chỉnh ngưỡng hoặc ưu tiên synthetic probe thay vì alert zero spans.

## 9. Không dùng high-cardinality ID trong alert

Alert label được dùng để group, deduplicate và route notification. Nếu đưa `traceId`, `spanId`, `orderId` hoặc request ID vào label, mỗi sự kiện có thể tạo một alert instance mới.

Dùng label ổn định:

```yaml
labels:
  service: shop-service
  boundary: receipt-worker
  severity: warning
  team: platform
```

Đưa trace ID hoặc correlation ID vào annotation/log khi có giá trị điều tra và hệ thống có thể cung cấp an toàn. Không đưa dữ liệu cá nhân hoặc secret vào alert payload.

## 10. Severity và routing

Không phải mọi context missing đều có cùng mức độ nghiêm trọng.

| Mức | Ví dụ | Hành động |
| --- | --- | --- |
| Info | Synthetic probe thỉnh thoảng thất bại trong môi trường test | Ghi nhận và kiểm tra ở giờ làm việc |
| Warning | Context missing tăng ở một async boundary nhưng nghiệp vụ vẫn chạy | Điều tra executor/propagation trong ca trực |
| Critical | Nhiều service bị mất trace context đồng thời, làm mất khả năng điều tra sự cố đang diễn ra | Kích hoạt incident platform/observability |
| Critical | Collector không export spans, queue gần đầy và drop đang tăng trên production | Ưu tiên khôi phục pipeline telemetry |

Alert nên route theo ownership:

- Application team nhận cảnh báo context missing tại boundary do họ sở hữu.
- Platform/observability team nhận exporter/Collector/backend alert.
- On-call service nhận cảnh báo business SLO riêng.

Không route mọi lỗi tracing về cùng một nhóm nếu quyền sở hữu và khả năng xử lý khác nhau.

## 11. Phân biệt sampling với mất context

Đây là lỗi chẩn đoán thường gặp.

| Dấu hiệu | Sampling | Mất context |
| --- | --- | --- |
| Request vẫn chạy | Có | Có |
| Span được tạo/record | Có thể bị sampler loại từ đầu | Có thể span vẫn được tạo nhưng thiếu parent |
| Trace ID | Có thể không xuất hiện trong backend | Downstream có thể có trace ID mới |
| Parent relationship | Các span được sample thường theo quyết định parent-based | Parent thiếu hoặc trace bị chia tại boundary |
| Collector thấy span | Không nếu SDK drop trước export | Có thể thấy các span rời nhau |
| Cách xác nhận | Sampler config, sampled flag và sampling metrics | Context guard, synthetic trace assertion, trace/span IDs |

Đặt sampling probability lên 100% trong một lần kiểm thử có kiểm soát có thể giúp loại trừ head sampling. Không giữ cấu hình 100% trong production nếu chưa đánh giá lưu lượng, chi phí và chính sách dữ liệu.

## 12. Runbook: khi alert ExpectedTraceContextMissing kích hoạt

### Bước 1 — Xác định phạm vi

- Xem service, boundary và môi trường trong alert labels.
- Xem thời điểm bắt đầu, số lần tăng counter và replica bị ảnh hưởng.
- Kiểm tra có deploy/scale/restart hoặc thay đổi executor gần thời điểm đó không.

### Bước 2 — Xác nhận boundary có yêu cầu context

- Worker có được gọi từ request đang có trace không?
- Có task nào chạy độc lập từ scheduler hoặc retry queue không?
- Thiết kế dùng parent-child hay span link?
- Có upstream message không truyền trace headers không?

Nếu boundary không yêu cầu parent, sửa instrumentation/alert condition thay vì coi root span hợp lệ là lỗi.

### Bước 3 — Kiểm tra propagation mechanism

Với `@Async`:

- Xác nhận `@EnableAsync` và lời gọi qua Spring proxy.
- Xác định executor thực sự được chọn bởi `@Async("...")`.
- Kiểm tra `ContextPropagatingTaskDecorator` hoặc Boot property đúng phiên bản.
- Kiểm tra task có bị chuyển qua executor thứ hai không.

Với HTTP:

- Kiểm tra `traceparent`/B3 có được gửi và nhận không.
- Kiểm tra client builder/instrumentation và gateway headers.
- Kiểm tra propagation format giữa các service.

Với messaging:

- Kiểm tra producer inject headers.
- Kiểm tra broker có giữ headers.
- Kiểm tra consumer extract context trước khi tạo span.
- Kiểm tra semantics parent-child/span link.

### Bước 4 — Kiểm tra trace backend

- Tìm trace theo service và khoảng thời gian.
- So sánh `traceId` ở upstream/downstream nếu log có ghi.
- Kiểm tra `parentSpanId` hoặc span link.
- Xác nhận trace không bị sampling hoặc exporter drop.

### Bước 5 — Kiểm tra Collector/exporter

- Xem send failed, refused, dropped spans.
- Xem exporter queue size/capacity và duration.
- Kiểm tra DNS, TLS, authentication, endpoint và backend throttling.
- Xem restart hoặc memory pressure của Collector.

### Bước 6 — Khôi phục và xác nhận

- Sửa đúng boundary/executor/transport gây mất context.
- Chạy synthetic probe hoặc integration test.
- Xác nhận trace có quan hệ đúng trên backend.
- Theo dõi counter missing không tăng thêm.
- Ghi lại nguyên nhân và thay đổi cấu hình/code liên quan.

## 13. Runbook: khi alert Collector export failure kích hoạt

1. Xác định exporter và backend đích bị lỗi.
2. Kiểm tra Collector logs/status code và network/TLS.
3. Kiểm tra queue size/capacity, retry và send duration.
4. Kiểm tra backend ingestion limit, quota, rate limit và tình trạng dịch vụ.
5. Khôi phục đường export hoặc scale Collector/backend theo tải.
6. Theo dõi queue giảm và send failure ngừng tăng.
7. Kiểm tra trace mới xuất hiện trên backend.

Không chỉ tăng queue hoặc timeout khi backend đang quá tải kéo dài. Queue trong RAM chỉ hấp thụ gián đoạn ngắn; tăng queue không sửa được throughput thấp hơn tốc độ sinh span.

## 14. Thiết kế alert tránh false positive

### 14.1. Chỉ cảnh báo tại boundary có kỳ vọng rõ ràng

Một consumer độc lập không có incoming trace là hợp lệ. Không dùng tỷ lệ root span toàn hệ thống làm cảnh báo context loss nếu ứng dụng có scheduler, batch jobs hoặc message consumers độc lập.

### 14.2. Dùng cửa sổ và ngưỡng phù hợp

Counter tăng một lần có thể là lỗi thật nhưng cũng có thể là một task độc lập. Kết hợp:

- Boundary cụ thể.
- Số lần tăng trong cửa sổ thời gian.
- Tỷ lệ missing trên tổng số task/request tại boundary.
- Mức độ ảnh hưởng nghiệp vụ.

Ví dụ ratio nếu có cả hai counter:

```promql
sum(rate(app_observability_context_missing_total{boundary="receipt-worker"}[10m]))
/
clamp_min(sum(rate(app_async_tasks_total{boundary="receipt-worker"}[10m])), 0.001)
> 0.05
```

Tên metric `app_async_tasks_total` là ví dụ; cần instrument task count và xác nhận Prometheus exposition. Ratio này chỉ có ý nghĩa nếu hai counter đo cùng một tập task.

### 14.3. Im lặng không có nghĩa là khỏe

Nếu context guard không được gọi do worker không chạy, counter missing có thể đứng yên. Cần theo dõi cả:

- Số task được submit.
- Số task hoàn tất/thất bại.
- Synthetic probe success.
- Collector exporter status.

Không có metric mới trong lúc không có traffic không phải bằng chứng hệ thống khỏe. Synthetic probe giúp kiểm tra đường đi ngay cả khi traffic tự nhiên thấp.

### 14.4. Dùng `for` để giảm alert flapping

`for` yêu cầu biểu thức duy trì trạng thái đủ lâu trước khi alert firing. Dùng khoảng thời gian ngắn cho lỗi drop liên tục, dài hơn cho tín hiệu dao động. Không đặt `for` dài đến mức che giấu sự cố cần xử lý ngay.

## 15. Kiểm tra rule và notification

Với Prometheus:

```bash
promtool check rules alerting-rules.yml
```

Sau khi load rule:

1. Kiểm tra trang Alerts của Prometheus.
2. Kiểm tra trạng thái inactive/pending/firing.
3. Kiểm tra Alertmanager nhận alert.
4. Kiểm tra grouping, inhibition và route.
5. Dùng test alert hoặc môi trường staging để xác nhận notification đến đúng team.

Không chỉ kiểm tra cú pháp YAML. Một rule có thể hợp lệ nhưng metric name sai, label không tồn tại hoặc biểu thức không bao giờ match.

### 15.1. Test điều kiện context missing

Trong môi trường test, gọi boundary có context guard mà không tạo current trace context. Xác nhận counter tăng đúng một lần. Sau đó gọi cùng boundary trong một request có trace context và xác nhận counter không tăng.

Không tạo tình huống mất context trên production chỉ để thử alert. Dùng integration test hoặc staging có thể kiểm soát.

### 15.2. Test exporter failure

Có thể dùng Collector/backend test trong staging để tạo lỗi export có kiểm soát, sau đó xác nhận:

- Collector send failure metric tăng.
- Queue có xu hướng tăng nếu exporter không thoát batch.
- Alert firing theo rule.
- Notification được route đúng.
- Khi backend phục hồi, queue giảm và alert resolve.

## 16. Bài tập tự kiểm tra

**Câu 1.** Một async worker tạo trace ID mới, nhưng nghiệp vụ hoàn tất thành công. Hãy nêu hai khả năng giải thích và cách xác định đó có phải lỗi không.

**Câu 2.** Vì sao không nên đưa `traceId` vào tag của counter `app.observability.context.missing`?

**Câu 3.** `tracer.currentSpan()` trả `null` trong worker. Có thể kết luận trace đã bị sampling drop không?

**Câu 4.** Counter context missing không tăng, nhưng synthetic probe không tìm thấy trace. Cần kiểm tra những lớp nào?

**Câu 5.** Collector `otelcol_exporter_send_failed_spans` tăng và queue usage đạt 95%. Alert nào nên kích hoạt và team nào nên nhận?

**Câu 6.** Một message consumer độc lập tạo root span không có parent. Có nên tăng context missing counter không?

**Câu 7.** Trace có cùng `traceId` nhưng child span có `parentSpanId` trỏ tới span khác với parent dự kiến. Cần kiểm tra điều gì?

**Câu 8.** Vì sao không nên alert khi tổng số trace trong backend bằng 0 mà không xét traffic và sampling?

### Gợi ý đáp án

1. Có thể executor không propagate context; hoặc task được thiết kế thành trace mới/span link. Xác định hợp đồng tracing của boundary, kiểm tra trace ID/parent ID/link và context propagation.
2. Mỗi trace ID tạo một time series riêng, làm cardinality tăng rất lớn. Đưa ID vào log/trace có kiểm soát, giữ metric tag ở boundary/service cố định.
3. Không. Có thể context thực sự không tồn tại, boundary là root hợp lệ hoặc implementation tracer biểu diễn context không sampled theo cách khác. Kiểm tra sampled flag, tracer implementation và thiết kế boundary.
4. Kiểm tra synthetic request, sampling, instrumentation, exporter/Collector, ingestion delay, backend query và tenant.
5. Cảnh báo exporter failure và queue saturation; route cho platform/observability on-call, đồng thời đánh giá ảnh hưởng tới khả năng điều tra.
6. Không nếu consumer được thiết kế độc lập và không có trace header kỳ vọng. Root span là hợp lệ.
7. Kiểm tra scope nesting, async context capture, span links, instrumentation tự động và việc có span trung gian trong trace tree.
8. Có thể không có traffic, sampling drop, ingestion delay hoặc backend query sai. Kết hợp request rate, sampling policy và synthetic probe.

## 17. Checklist vận hành

- [ ] Đã định nghĩa boundary nào bắt buộc có trace context và boundary nào được phép là root.
- [ ] Đã chọn parent-child hoặc span link cho async/message flow theo semantics rõ ràng.
- [ ] Đã kiểm tra HTTP/message propagation headers và executor context propagation.
- [ ] Đã instrument counter context missing với tag cardinality thấp.
- [ ] Đã xác nhận hành vi `currentSpan()` với tracer bridge và sampler đang dùng.
- [ ] Đã theo dõi SDK queue/drop và Collector accepted/refused/dropped/send-failed spans.
- [ ] Đã có alert riêng cho context missing, exporter failure, queue saturation và telemetry silence.
- [ ] Đã dùng traffic-aware condition hoặc synthetic probe để tránh false positive.
- [ ] Đã loại trace ID, span ID, order ID và PII khỏi metric labels.
- [ ] Alert có owner, severity, runbook URL và route rõ ràng.
- [ ] Đã kiểm tra Prometheus rules bằng `promtool`.
- [ ] Đã thử notification và alert resolution trong staging.
- [ ] Đã xác nhận trace liên kết đúng trên backend sau khi sửa lỗi.

## 18. Ghi nhớ

Cảnh báo mất context cần dựa trên hợp đồng tracing của từng boundary. `currentSpan()` không có giá trị ở một async worker chỉ là tín hiệu chẩn đoán; cần biết task có được kỳ vọng kế thừa context hay được thiết kế thành root/span link. Sampling, instrumentation, exporter và backend là các lớp riêng, không thể gộp thành một lỗi.

Hãy dùng counter Micrometer có tag cardinality thấp để đo context missing tại boundary cần propagation, kết hợp synthetic trace probe để xác minh trace ID và quan hệ parent-child/span link. Theo dõi riêng SDK/Collector queue, refused/dropped spans và exporter failures. Alert nên có owner, severity và runbook cụ thể; không đưa trace ID hoặc dữ liệu cá nhân vào metric labels. Khi điều tra, đi lần lượt từ boundary, propagation, sampling, exporter đến Collector và backend.

### Tài liệu tham khảo

- [Micrometer Tracing — Context Propagation](https://docs.micrometer.io/tracing/reference/): current span, scope và tích hợp tracing context.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing propagation, sampling và exporter configuration.
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html): `ContextPropagatingTaskDecorator` và context qua executor.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module entry spans và event metrics.
- [OpenTelemetry Collector — Internal Telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/): Collector metrics/logs/traces và giám sát pipeline.
- [OpenTelemetry — Trace Context](https://opentelemetry.io/docs/concepts/context-propagation/): inject/extract context qua process và service boundary.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, trace ID, parent ID và trace flags.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): biểu thức alert, `for`, labels và annotations.
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/): grouping, routing, inhibition và notification.
