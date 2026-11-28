# Batch export và backpressure

> **Chương:** Hiệu năng  
> **Bối cảnh:** Spring Modulith Documentation & Observability — tối ưu đường xuất telemetry của module spans, traces, logs và metrics bằng batching, queue có giới hạn, retry và chính sách backpressure phù hợp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả luồng từ module entry observation của Spring Modulith đến trace backend.
2. Giải thích vì sao exporter gom span thành batch và gửi bất đồng bộ.
3. Phân biệt batch size, schedule delay, queue size và export timeout.
4. Cấu hình OpenTelemetry BatchSpanProcessor trong Spring Boot.
5. Ước lượng thời gian queue bị đầy khi tốc độ tạo span vượt tốc độ export.
6. Nhận biết lúc nào telemetry bị drop, retry hoặc export chậm.
7. Thiết kế backpressure để bảo vệ application thread và giới hạn bộ nhớ.
8. Tách backpressure của telemetry khỏi cơ chế giao nhận domain event của Spring Modulith.
9. Kiểm tra shutdown/flush, theo dõi exporter health và điều chỉnh cấu hình dựa trên số liệu.

## 2. Batch export giải quyết vấn đề gì?

Spring Modulith có thể tạo span khi một Spring component thuộc API của application module được gọi. Một request đặt hàng có thể tạo nhiều module entry spans:

~~~mermaid
flowchart LR
    HTTP["HTTP request"] --> Orders["orders"]
    Orders --> Inventory["inventory"]
    Orders --> Payments["payments"]
    Orders --> Event["OrderPlaced"]
    Event --> Notify["notifications listener"]
    Orders -. "module spans" .-> SDK["Tracing SDK"]
    Inventory -. "module spans" .-> SDK
    Payments -. "module spans" .-> SDK
    Notify -. "module spans" .-> SDK
    SDK --> Queue["Bounded span queue"]
    Queue --> Batch["BatchSpanProcessor"]
    Batch --> OTLP["OTLP exporter"]
    OTLP --> Collector["OpenTelemetry Collector"]
    Collector --> Backend["Trace backend"]
~~~

Nếu gửi từng span ngay khi kết thúc, ứng dụng phải thực hiện rất nhiều lần gửi nhỏ. Mỗi lần gửi có chi phí kết nối, serialization, network round trip và xử lý phía collector.

Batch export gom nhiều span vào một request:

- Giảm số lần gọi exporter và network round trip.
- Tận dụng payload lớn hơn nhưng vẫn nằm trong giới hạn request.
- Tách công việc export khỏi luồng đang xử lý nghiệp vụ.
- Cho phép điều chỉnh giữa độ trễ hiển thị trace, throughput và mức dùng bộ nhớ.

Batch export không làm mất chi phí tạo span, ghi attribute hay kết thúc observation. Nó chủ yếu tối ưu giai đoạn chuyển telemetry ra khỏi tiến trình.

## 3. Phân biệt ba pipeline telemetry

Một ứng dụng có thể xuất traces, logs và metrics qua các pipeline khác nhau:

| Tín hiệu | Thành phần batch/export thường gặp | Dữ liệu |
| --- | --- | --- |
| Traces | BatchSpanProcessor + SpanExporter | Span của HTTP request, module invocation và client call |
| Logs | BatchLogRecordProcessor + LogRecordExporter | Log record có trace/span correlation |
| Metrics | MeterReader/PeriodicMetricReader + MetricExporter | Counter, Timer, histogram và gauge |

Các pipeline có queue, lịch export và timeout riêng. Không giả định một cấu hình queue của traces sẽ tự áp dụng cho logs hoặc metrics.

Trong bài này, ví dụ tập trung vào traces của Spring Modulith. Phần logs đề cập riêng ở mục 10. Metrics thường được scrape qua Prometheus hoặc export theo chu kỳ; nó không đi qua BatchSpanProcessor.

## 4. Spring Modulith tạo telemetry ở đâu?

Spring Modulith observability có thể instrument các Spring component thuộc API của application module và tạo Micrometer spans cho module entry. Các span mang metadata như:

- `module.identifier`: định danh kỹ thuật của module.
- `module.name`: tên hiển thị.
- `module.invocation-type`: `bean` hoặc `event listener`.
- `module.method`: method được thực thi.

`spring-modulith-starter-insight` cung cấp Actuator và observability support. Để export traces tới backend, ứng dụng vẫn cần tracer/exporter infrastructure phù hợp theo Spring Boot version.

Một trace có thể bao gồm:

~~~text
HTTP POST /orders
└── orders.placeOrder
    ├── inventory.reserve
    ├── payments.authorize
    └── notifications.onOrderPlaced
~~~

Đây là tên operation minh họa. Mỗi module entry span được kết thúc sẽ trở thành dữ liệu đầu vào cho tracing pipeline nếu span được sampler giữ lại.

### 4.1. Sampling và batching là hai bước khác nhau

Sampling quyết định trace/span nào được ghi nhận hoặc export. Batching quyết định cách gom các span đã được chọn để gửi đi.

- Giảm sampling làm giảm số span đi vào queue.
- Tăng batch size làm tăng số span trong mỗi lần export.
- Tăng queue size giúp hấp thụ burst trong thời gian ngắn.
- Tăng schedule delay có thể gom batch lớn hơn nhưng làm trace xuất hiện muộn hơn.

Batching không thay thế sampling. Nếu lượng span đầu vào vượt năng lực export trong thời gian dài, chỉ tăng batch size hoặc queue size sẽ trì hoãn lúc queue đầy.

## 5. BatchSpanProcessor hoạt động như thế nào?

`BatchSpanProcessor` nhận span khi span kết thúc, đưa span vào queue có giới hạn và dùng worker riêng để export batch.

~~~mermaid
flowchart TD
    End["Span ended"] --> Sample{"Span được sample?"}
    Sample -- "Không" --> Discard["Không đưa vào export queue"]
    Sample -- "Có" --> Offer["Thêm span vào bounded queue"]
    Offer --> Full{"Queue đầy?"}
    Full -- "Có" --> Drop["Drop span và tăng dropped counter"]
    Full -- "Không" --> Trigger{"Đủ batch size hoặc hết schedule delay?"}
    Trigger -- "Chưa" --> Offer
    Trigger -- "Rồi" --> Export["Worker lấy batch và gọi exporter"]
    Export --> Result{"Export thành công?"}
    Result -- "Có" --> Continue["Tiếp tục nhận span"]
    Result -- "Không" --> Retry["Exporter xử lý retry/timeout theo policy"]
    Retry --> Continue
~~~

Với OpenTelemetry Java BatchSpanProcessor:

- Queue có kích thước tối đa.
- Span mới được thêm vào queue bằng thao tác không chờ.
- Nếu queue đã đầy, span mới bị drop.
- Worker lấy span theo batch và export tuần tự; các lệnh export không được gọi đồng thời từ processor.
- Batch có thể được gửi khi đủ số span, hết schedule delay hoặc có yêu cầu force flush.

Điều này bảo vệ application thread khỏi việc chờ network cho từng span. Đổi lại, khi exporter chậm hơn tốc độ tạo span đủ lâu, telemetry sẽ bị drop thay vì làm request nghiệp vụ bị block.

## 6. Bốn tham số điều khiển batch

Spring Boot 4.2 cung cấp các property OpenTelemetry tracing export sau:

| Property | Default | Ý nghĩa |
| --- | ---: | --- |
| `management.opentelemetry.tracing.export.max-queue-size` | 2048 | Số span tối đa được giữ trong queue trước khi span mới bị drop |
| `management.opentelemetry.tracing.export.max-batch-size` | 512 | Số span tối đa trong một batch export |
| `management.opentelemetry.tracing.export.schedule-delay` | 5s | Khoảng delay giữa các lần export theo lịch |
| `management.opentelemetry.tracing.export.timeout` | 30s | Thời gian tối đa cho một lần export trước khi bị hủy |

`max-batch-size` phải nhỏ hơn hoặc bằng `max-queue-size`.

Ý nghĩa vận hành:

- **Queue size** quyết định burst có thể hấp thụ trước khi drop.
- **Batch size** quyết định lượng span tối đa gửi trong một request.
- **Schedule delay** ảnh hưởng độ trễ xuất trace khi batch chưa đầy.
- **Export timeout** giới hạn thời gian worker chờ một lần export.

Giá trị mặc định là điểm bắt đầu, không phải cấu hình tối ưu cho mọi service.

## 7. Cấu hình OTLP batch export trong Spring Boot

Với Spring Boot 4.2 và OpenTelemetry OTLP, dependency tracing được tài liệu Spring Boot hướng dẫn là:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-opentelemetry")
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
}
~~~

Các version cần được quản lý bởi Spring Boot/Spring Modulith BOM tương thích của dự án. Nếu dùng Spring Boot 3.x, dependency và property namespace có thể khác; không sao chép nguyên cấu hình 4.2 sang version cũ.

Ví dụ profile production-like:

~~~yaml
management:
  opentelemetry:
    enabled: true
    tracing:
      export:
        max-queue-size: 4096
        max-batch-size: 512
        schedule-delay: 2s
        timeout: 20s
        otlp:
          endpoint: "http://otel-collector:4318/v1/traces"
          transport: http
          compression: gzip
          connect-timeout: 3s
          timeout: 10s
~~~

Đây là cấu hình ví dụ để minh họa cách tách queue/batch settings khỏi OTLP transport settings. Endpoint, timeout và queue size phải được chọn theo collector, network, request volume và latency budget của service.

Spring Boot 4.2 cũng ánh xạ các biến OpenTelemetry chuẩn:

| Environment variable | Spring Boot property |
| --- | --- |
| `OTEL_BSP_SCHEDULE_DELAY` | `management.opentelemetry.tracing.export.schedule-delay` |
| `OTEL_BSP_EXPORT_TIMEOUT` | `management.opentelemetry.tracing.export.timeout` |
| `OTEL_BSP_MAX_QUEUE_SIZE` | `management.opentelemetry.tracing.export.max-queue-size` |
| `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` | `management.opentelemetry.tracing.export.max-batch-size` |

Khi dùng environment variables, ghi lại nguồn override trong deployment documentation để người vận hành biết giá trị nào đang thắng.

## 8. Ước lượng queue size theo tải thực tế

Queue size cần đủ lớn để hấp thụ burst ngắn, nhưng không nên tăng vô hạn. Một cách ước lượng ban đầu là so sánh tốc độ tạo span với tốc độ export:

- λ (lambda): số span mới đi vào queue mỗi giây.
- μ (mu): số span được export thành công mỗi giây.
- Q: số slot còn trống trong queue.

Khi λ lớn hơn μ trong một khoảng thời gian, queue tăng xấp xỉ theo chênh lệch:

~~~text
queue growth ≈ λ - μ
time to fill ≈ available queue slots / (λ - μ)
~~~

Ví dụ:

~~~text
Incoming spans (λ) = 1.200 spans/second
Export capacity (μ) =   900 spans/second
Queue capacity        = 2.048 spans

Time to fill ≈ 2.048 / (1.200 - 900)
             ≈ 6,8 seconds
~~~

Đây là mô hình gần đúng khi tốc độ tương đối ổn định và queue ban đầu còn trống. Trong thực tế, span size, export batch, retry, scheduling và collector load làm tốc độ thay đổi.

Nếu μ lớn hơn λ trong thời gian đủ dài, worker có thể xử lý hết backlog. Nếu λ luôn lớn hơn μ, mọi queue hữu hạn cuối cùng đều đầy.

### 8.1. Ước lượng bộ nhớ

Queue giữ span objects trước khi serialize. Bộ nhớ phụ thuộc số attribute, event, link, stack trace và cấu trúc object; không thể suy ra chính xác chỉ từ số span.

Ước lượng sơ bộ:

~~~text
Queue memory ≈ maxQueueSize × average in-memory span size
~~~

Ví dụ nếu mỗi span chiếm trung bình 2 KiB trong heap và queue giữ 4.096 span:

~~~text
4.096 × 2 KiB ≈ 8 MiB
~~~

Con số này chỉ minh họa, chưa gồm batch đang export, object overhead, exporter buffers, serialization buffers và các queue khác. Hãy đo heap trong load test với số attribute/event gần production.

### 8.2. Batch size và schedule delay ảnh hưởng latency ra sao?

Một batch có thể được export khi đạt batch size hoặc khi hết schedule delay. Do đó:

- Batch size lớn tăng hiệu quả network khi có traffic cao.
- Batch size nhỏ giúp batch được gửi sớm hơn khi tải thấp, nhưng có thể tạo nhiều request hơn.
- Schedule delay ngắn giảm thời gian chờ trace ở queue.
- Schedule delay dài có thể gom batch lớn hơn trong tải thấp, nhưng trace xuất hiện muộn hơn.

Nếu collector xử lý tốt nhưng trace chỉ xuất hiện sau vài giây, kiểm tra schedule delay và thời gian export trước khi tăng queue.

## 9. Retry, timeout và lỗi collector

Exporter có thể gặp lỗi tạm thời:

- Collector restart hoặc rolling upgrade.
- Network timeout, DNS hoặc connection reset.
- Collector trả HTTP 429, 502, 503 hoặc 504.
- Backend phía sau collector bị quá tải.

OTLP specification yêu cầu retry cho transient errors bằng exponential backoff có jitter. Tổng thời gian các lần thử và khoảng chờ retry phải nằm trong export timeout; timeout tổng không được reset sau mỗi request attempt.

Một số nguyên tắc:

1. Retry chỉ có ích khi lỗi có khả năng hồi phục.
2. Backoff và jitter tránh nhiều instance retry cùng lúc tạo thêm một đợt tải.
3. Export timeout phải đủ cho request và retry budget, nhưng không quá dài đến mức worker bị giữ quá lâu.
4. Lỗi dữ liệu không hợp lệ hoặc lỗi xác thực thường không tự hồi phục bằng retry liên tục.
5. Khi export thất bại, kiểm tra processor/exporter metrics và log để biết batch có được retry hay đã thất bại.

Với OTLP/HTTP, các status 429, 502, 503 và 504 có thể retry theo specification. Nếu server trả Retry-After, client nên tôn trọng thời gian đó. Với OTLP/gRPC, retry phụ thuộc status code và thông tin recovery như RetryInfo.

### 9.1. Partial success không giống transient failure

OTLP có thể trả response partial_success để báo một phần telemetry bị từ chối. Theo specification, client không được retry request khi nhận partial success response có trường partial_success được điền.

Vì vậy, nếu exporter/backend báo rejected spans hoặc attributes, hãy xử lý nguyên nhân dữ liệu/giới hạn ở server. Retry cùng batch không giải quyết được phần dữ liệu đã bị từ chối.

## 10. Batch export cho logs và metrics

### 10.1. Logs

Nếu bật OpenTelemetry log export trong Spring Boot 4.2, pipeline log có cấu hình riêng:

| Property | Default | Ý nghĩa |
| --- | ---: | --- |
| management.opentelemetry.logging.export.max-queue-size | 2048 | Số log record tối đa giữ trong queue |
| management.opentelemetry.logging.export.max-batch-size | 512 | Số record tối đa trong một batch |
| management.opentelemetry.logging.export.schedule-delay | 1s | Delay giữa các lần export theo lịch |
| management.opentelemetry.logging.export.timeout | 30s | Thời gian tối đa cho export |

Log có thể phát sinh với tốc độ cao hơn trace, đặc biệt khi bật DEBUG/TRACE. Nếu log queue đầy, một số log record có thể bị drop. Tránh tăng log verbosity trên production mà không kiểm tra năng lực exporter và collector.

### 10.2. Metrics

Metrics thường được export theo chu kỳ thông qua metric reader/exporter hoặc scrape bởi Prometheus. Cần phân biệt:

- Timer/counter được cập nhật trong ứng dụng.
- Reader thu thập dữ liệu theo chu kỳ.
- Exporter gửi metric payload tới backend.
- Backend ingest và lưu time series.

Queue/batch của BatchSpanProcessor không điều khiển metric export. Với Prometheus pull, Prometheus scrape endpoint theo scrape interval; backpressure chủ yếu thể hiện qua scrape chậm/lỗi và tải endpoint. Với OTLP metrics push, theo dõi export interval, timeout và exporter-specific settings theo đúng version.

## 11. Phân biệt telemetry backpressure và business event backpressure

Trong Spring Modulith, có hai loại dữ liệu bất đồng bộ dễ bị nhầm:

| Đường xử lý | Mục tiêu | Khi queue đầy hoặc downstream chậm |
| --- | --- | --- |
| Telemetry export | Gửi span/log/metric để quan sát | Có thể drop telemetry theo processor policy; nghiệp vụ vẫn tiếp tục |
| Business event delivery | Giao domain event tới listener hoặc external consumer | Cần bảo toàn semantics nghiệp vụ, retry, trạng thái publication và recovery |

Ví dụ module.events.published là metric đếm event publication. Nó không phải queue chứa event và cũng không phải cơ chế batch export trace.

Không áp dụng chính sách drop span của BatchSpanProcessor cho domain events. Event nghiệp vụ có thể đại diện cho thanh toán, hoàn tất đơn hàng hoặc cập nhật tồn kho; việc bỏ event cần được xử lý theo thiết kế giao nhận, Event Publication Registry, transaction/outbox và retry policy của ứng dụng.

Ngược lại, không nên để một telemetry exporter chậm làm request đặt hàng phải chờ network gửi trace. Telemetry nên được xử lý qua pipeline bất đồng bộ có queue hữu hạn.

## 12. Context propagation qua executor và listener

Batch export chỉ nhận được trace context đúng nếu span được tạo trong đúng context. Khi công việc chuyển sang thread khác, context propagation cần được cấu hình phù hợp.

Spring Boot tự propagate trace qua HTTP khi dùng các builder được auto-configure như RestClient.Builder hoặc WebClient.Builder. Nếu tự tạo client không qua builder đó, propagation có thể không hoạt động.

Với task executor, Spring Framework cung cấp ContextPropagatingTaskDecorator để capture và restore context khi task được submit và chạy trên worker thread.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class TaskExecutionConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Đây là ví dụ cấu hình executor. Số thread và queue capacity cần được chọn theo workload; queue của executor xử lý business tasks, không phải queue telemetry của BatchSpanProcessor.

### 12.1. Queue business task cũng cần backpressure

Với executor có queue hữu hạn:

- Khi worker xử lý kịp, task được xếp hàng và chạy sau.
- Khi queue đầy, rejection policy quyết định task tiếp theo được xử lý thế nào.
- CallerRunsPolicy có thể khiến thread submit chạy task, tạo backpressure lên caller nhưng làm tăng latency của request.
- AbortPolicy từ chối task bằng exception; ứng dụng phải xử lý rejection phù hợp với semantics.
- Queue vô hạn có thể che giấu downstream chậm bằng cách tích lũy task và làm heap tăng dần.

Chọn policy dựa trên nghiệp vụ và khả năng retry/durable delivery. Không dùng một policy chung cho mọi event listener.

## 13. Collector cũng cần giới hạn tài nguyên

Nếu ứng dụng gửi được nhiều telemetry hơn collector xử lý, queue phía collector cũng có thể đầy. Một collector pipeline thường cần:

- Memory limiter để giới hạn mức dùng RAM.
- Batch processor để gom telemetry trước khi gửi tiếp.
- Exporter queue có giới hạn nếu exporter hỗ trợ.
- Retry policy có backoff và giới hạn thời gian.
- Monitoring cho refused/dropped telemetry, queue size, send failures và exporter latency.

Ví dụ cấu trúc pipeline traces minh họa:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    timeout: 5s
    send_batch_size: 512
    send_batch_max_size: 1024

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [debug]
~~~

Đây là cấu hình học tập dùng debug exporter. Khi chạy production, thay exporter bằng backend thực tế, cấu hình TLS/auth, queue/retry theo exporter hỗ trợ và giới hạn tài nguyên theo tải. Xác minh component names và fields theo bản OpenTelemetry Collector distribution/version đang triển khai.

send_batch_size là ngưỡng kích hoạt gửi batch; send_batch_max_size là giới hạn trên của batch. Nó không đồng nghĩa với max-batch-size của ứng dụng Java.

## 14. Theo dõi chính BatchSpanProcessor

Không thể tối ưu queue nếu chỉ nhìn latency của request. Cần quan sát chính tracing SDK và exporter.

OpenTelemetry Java SDK có self-observability metrics cho processor và exporter. Tùy schema/version, tên có thể khác nhau:

| Schema | Metric | Ý nghĩa |
| --- | --- | --- |
| Legacy | queueSize | Số span hiện đang chờ trong queue |
| Legacy | processedSpans | Số span đã được processor xử lý; có thể có thuộc tính phân biệt dropped |
| Latest | otel.sdk.processor.span.queue.size | Số span trong queue |
| Latest | otel.sdk.processor.span.queue.capacity | Dung lượng queue |
| Latest | otel.sdk.processor.span.processed | Số span đã xử lý, kèm error.type khi thất bại |
| Latest | otel.sdk.exporter.span.inflight | Số span đang được exporter xử lý |
| Latest | otel.sdk.exporter.span.exported | Số span được exporter xử lý |
| Latest | otel.sdk.exporter.operation.duration | Thời lượng thao tác export |

Trong schema latest, error.type có thể mang giá trị queue_full khi span bị drop vì queue đầy hoặc already_shutdown khi processor đã đóng. Các self-metrics và schema có thể cần bật/configure; không giả định mọi ứng dụng Spring Boot đều expose chúng mặc định. Xác minh bằng metrics endpoint hoặc telemetry backend của SDK đang dùng.

Các panel hữu ích:

- Queue size và queue capacity trên cùng biểu đồ để thấy tỷ lệ sử dụng.
- Tốc độ span được tạo so với tốc độ span được export.
- Số span xử lý với error.type=queue_full.
- Export duration p95/p99 và số lần export thất bại.
- Collector refused/dropped spans và exporter queue utilization.

Nếu không có self-metrics, dùng log cảnh báo của processor, exporter diagnostics và collector telemetry để xác định tình trạng. Đừng tạo dashboard dựa trên metric name chưa xuất hiện trong runtime.

## 15. Shutdown và force flush

Khi ứng dụng dừng, queue có thể còn span chưa export. OpenTelemetry SDK hỗ trợ ForceFlush để yêu cầu processor export dữ liệu đang chờ; shutdown của BatchSpanProcessor thực hiện flush trước khi đóng exporter.

Trong môi trường container/Kubernetes:

1. Khi nhận SIGTERM, ứng dụng cần có thời gian graceful shutdown.
2. Các request đang xử lý cần hoàn tất trong shutdown budget.
3. Tracing provider/processor cần flush các span còn trong queue.
4. Exporter cần thời gian hoàn tất request hoặc timeout.
5. Sau đó tiến trình mới nên kết thúc.

Nếu container bị SIGKILL, node mất điện hoặc termination grace period quá ngắn, queue trong memory có thể mất mà không được flush.

Ví dụ cấu hình Kubernetes:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: shop-service
      lifecycle:
        preStop:
          exec:
            command: ["sh", "-c", "sleep 5"]
~~~

Đây chỉ là ví dụ minh họa khoảng thời gian dừng; preStop sleep không tự gọi ForceFlush. Chọn grace period theo thời gian drain request, export timeout và shutdown behavior thực tế của Spring Boot/SDK. Tránh dùng một khoảng chờ cố định nếu ứng dụng không cần nó.

### 15.1. Kiểm thử flush khi shutdown

Trong môi trường thử nghiệm:

1. Gửi request tạo ra một số module spans.
2. Dừng ứng dụng bằng SIGTERM hoặc lệnh stop bình thường.
3. Kiểm tra trace backend có nhận đủ các span đã kết thúc trước khi shutdown hay không.
4. Lặp lại với collector chậm hoặc không truy cập được.
5. Xác nhận shutdown hoàn tất trong grace period và log ghi nhận export failure nếu có.

## 16. Quy trình tuning theo từng bước

Điều chỉnh batch export theo thứ tự sau:

1. **Đo đầu vào:** xác định số span/giây ở tải bình thường và peak; kiểm tra sampling và số span trung bình mỗi request.
2. **Đo năng lực export:** đo batch throughput, export duration, lỗi, retry và tốc độ collector ingest.
3. **Xác định mục tiêu:** trace cần xuất hiện trong bao lâu, mất telemetry tối đa chấp nhận được là bao nhiêu và heap budget dành cho queue là bao nhiêu.
4. **Chọn schedule delay:** đặt theo độ trễ quan sát mong muốn; tải thấp thường cần delay ngắn hơn để trace không nằm chờ lâu.
5. **Chọn batch size:** đảm bảo batch đủ hiệu quả nhưng không vượt giới hạn request hoặc năng lực collector.
6. **Chọn queue size:** dựa trên burst cần hấp thụ và chênh lệch tốc độ tạo/export; giữ queue hữu hạn.
7. **Chọn timeout:** dựa trên thời gian network/collector và retry budget; tránh timeout dài làm worker bị chiếm quá lâu.
8. **Giảm đầu vào khi cần:** điều chỉnh sampling, span limits hoặc bỏ instrumentation không mang lại giá trị.
9. **Tăng năng lực downstream:** scale collector, điều chỉnh exporter queue và backend ingestion nếu đó là nút thắt.
10. **Load test và fault test:** mô phỏng burst, collector restart, network latency và backend throttling trước khi đưa cấu hình vào production.

Không tăng queue size đầu tiên khi queue liên tục đầy. Trước hết cần xác định exporter có thể xử lý được bao nhiêu span mỗi giây và vì sao tốc độ đó thấp hơn đầu vào.

### 16.1. Công thức ước lượng burst buffer

Nếu dự kiến tốc độ span đầu vào cực đại là λpeak, năng lực export là μ và cần hấp thụ burst trong T giây, số slot queue bổ sung tối thiểu theo mô hình đơn giản là:

~~~text
required queue headroom ≈ max(0, λpeak - μ) × T
~~~

Ví dụ λpeak = 1.500 spans/s, μ = 1.200 spans/s và muốn hấp thụ burst 5 giây:

~~~text
headroom ≈ (1.500 - 1.200) × 5
         ≈ 1.500 spans
~~~

Cộng thêm mức queue đang sử dụng và headroom cho biến động, sau đó kiểm tra heap. Đây là mô hình sizing ban đầu, không thay thế load test.

## 17. Chẩn đoán các vấn đề thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Trace xuất hiện trễ nhưng không có lỗi | Schedule delay dài hoặc batch chờ đủ size | Xem schedule delay, batch occupancy và export duration |
| Trace bị thiếu khi tải tăng | Queue đầy, sampling thay đổi hoặc exporter thất bại | Xem queue size/capacity, dropped counter, sampler và exporter logs |
| Application latency tăng cùng lúc collector chậm | Exporter/processor đang chặn hoặc custom processor chạy đồng bộ | Kiểm tra SDK, custom SpanProcessor và thread dump; tránh export đồng bộ trên request thread |
| Heap tăng dần | Queue quá lớn, span có nhiều attributes/events hoặc collector chậm kéo dài | Đo heap, queue utilization, span size; giảm payload hoặc tăng năng lực export |
| Export request bị từ chối do payload lớn | Batch quá lớn hoặc giới hạn request của collector | Giảm batch size, kiểm tra OTLP max request size và collector limits |
| Exporter retry liên tục | Collector/network không ổn định hoặc backend throttling | Xem status code, Retry-After, timeout và retry duration |
| Queue luôn thấp nhưng trace vẫn thiếu | Sampling drop, export error hoặc trace backend ingest issue | Kiểm tra sampling decision, exporter response và collector rejected spans |
| Log có traceId nhưng backend không có trace | Trace chưa được sample hoặc export bị thất bại | Đối chiếu sampling, dropped metrics và trace exporter logs |
| Trace module listener không nối với parent trace | Context không được propagate qua executor/event boundary | Kiểm tra TaskDecorator, message headers và tracing instrumentation |
| Shutdown làm mất trace cuối | Tiến trình bị kill trước khi flush hoàn tất | Kiểm tra SIGTERM, grace period, force flush và exporter timeout |

## 18. Bài thực hành: mô phỏng collector chậm và queue saturation

**Bối cảnh:** ứng dụng Spring Modulith có các module orders, payments và notifications. Module entry observations tạo spans và ứng dụng export qua OTLP tới OpenTelemetry Collector.

Thực hiện:

1. Cài Spring Modulith Insight và Spring Boot OpenTelemetry starter theo version tương thích.
2. Cấu hình collector endpoint, batch processor queue size 2.048, batch size 512 và schedule delay 5 giây ở profile thử nghiệm.
3. Tạo request đặt hàng để sinh trace có các module entry spans.
4. Đo span rate, export rate, export duration và queue size ở tải bình thường.
5. Tăng request rate hoặc tạo burst để queue tăng nhanh.
6. Làm collector chậm hoặc tạm dừng collector trong môi trường thử nghiệm.
7. Quan sát queue utilization, dropped spans, exporter retry và application latency.
8. Khôi phục collector; đo thời gian queue drain và xác nhận trace mới được export.
9. Thử tăng queue size và so sánh heap usage, thời gian trước khi queue đầy.
10. Thử giảm sampling hoặc giảm attribute/event payload; đánh giá tác động đến export throughput.
11. Dừng ứng dụng bằng SIGTERM khi queue còn span; xác nhận flush và shutdown behavior.
12. Tạo một executor có ContextPropagatingTaskDecorator và xác nhận span worker còn trace context phù hợp.
13. Kiểm tra domain event publication vẫn được xử lý theo semantics riêng, không bị drop theo chính sách telemetry.

Mẫu bảng ghi kết quả:

| Chỉ số | Bình thường | Collector chậm | Sau khi khôi phục |
| --- | --- | --- | --- |
| Incoming spans/sec | Ghi baseline | Ghi peak | Ghi tải hiện tại |
| Exported spans/sec | Ghi baseline | Ghi mức suy giảm | Ghi tốc độ drain |
| Queue size/capacity | Thấp/ổn định | Tăng | Giảm dần |
| Dropped spans | 0 hoặc baseline | Tăng nếu queue đầy | Không tăng thêm khi ổn định |
| Export duration | Baseline | Tăng/timeout | Trở về baseline |
| Application latency | Baseline | Kiểm tra có bị ảnh hưởng | Trở về bình thường |
| Shutdown flush | Thành công | Có thể timeout | Được xác minh riêng |

**Tiêu chí hoàn thành:** giải thích được vì sao queue tăng, ước lượng thời gian queue đầy, nhận diện span bị drop, điều chỉnh được batch/queue/timeout và xác minh trace export sau khi collector hồi phục.

## 19. Ghi nhớ

~~~text
MODULE ENTRY OBSERVATIONS
        ↓
SAMPLING
        ↓
BOUNDED BATCH QUEUE
        ↓
BATCH EXPORT + RETRY/TIMEOUT
        ↓
OTLP COLLECTOR
        ↓
TRACE BACKEND
~~~

Batch export giảm chi phí gửi từng span, còn queue hữu hạn hấp thụ burst ngắn. Khi tốc độ tạo span vượt tốc độ export kéo dài, queue sẽ đầy và telemetry có thể bị drop. Tăng queue chỉ mua thêm thời gian; cần xử lý nút thắt exporter/collector hoặc giảm đầu vào bằng sampling và giới hạn span payload.

Trong Spring Modulith, module entry spans và event publication metrics là hai tín hiệu khác nhau. Bảo vệ application thread bằng telemetry pipeline bất đồng bộ, nhưng giữ semantics giao nhận domain event bằng cơ chế retry/durable delivery của nghiệp vụ.

### Tài liệu tham khảo

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — OpenTelemetry OTLP starter, export properties, sampling và context propagation.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html) — tracing/logging queue, batch size, schedule delay và timeout properties.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — module entry spans, event publication metrics và Insight starter.
- [OpenTelemetry — Tracing SDK](https://opentelemetry.io/docs/specs/otel/trace/sdk/) — BatchSpanProcessor, queue, export schedule, force flush và shutdown.
- [OpenTelemetry — OTLP Exporter](https://opentelemetry.io/docs/specs/otel/protocol/exporter/) — exporter timeout, retry và exponential backoff.
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/) — retryable errors, throttling, Retry-After và partial success.
- [OpenTelemetry — Java SDK](https://opentelemetry.io/docs/languages/java/sdk/) — SDK self-observability metrics và batch processor metrics.
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html) — propagation context trong các execution boundary.

> **Lưu ý phiên bản:** property names, starter và self-observability metrics phụ thuộc Spring Boot/OpenTelemetry SDK version. Các giá trị mặc định trong bài tham chiếu Spring Boot 4.2/OpenTelemetry Java hiện hành; xác minh configuration metadata và runtime metrics của version production trước khi áp dụng. Bài được soạn trong STEP 4; Content QA chuyên môn thuộc bước riêng.
