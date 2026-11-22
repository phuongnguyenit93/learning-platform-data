# Thực hành liên kết logs, metrics và traces bằng OpenTelemetry

Trong module `CLOUD_PROVIDERS_GCP`, bạn khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Khi các workload này giao tiếp với nhau, một request có thể đi qua nhiều service, queue và database. Nếu log, metric và trace được thu thập rời rạc, đội vận hành khó xác định một biểu đồ tăng đột biến liên quan đến request nào và lỗi cụ thể xuất hiện ở bước nào.

Bài thực hành này dùng OpenTelemetry (OTel) để tạo và liên kết ba tín hiệu trong cùng một luồng xử lý. Bạn sẽ instrument một ứng dụng Java/Spring Boot, truyền trace context qua các thành phần, ghi log JSON có trace ID và span ID, ghi histogram metric trong context của span để tạo exemplar, rồi gửi telemetry qua OpenTelemetry Collector đến Google Cloud Observability.

## 1. Kết quả mong đợi và mô hình liên kết

Sau khi hoàn thành bài thực hành, một request đến `checkout-api` sẽ tạo ra:

- Một trace chứa span HTTP server và các span nghiệp vụ như `payment.authorize`.
- Log JSON ghi sự kiện trong lúc xử lý, có trace ID và span ID của span đang hoạt động.
- Histogram metric ghi thời gian xử lý thanh toán và exemplar trỏ đến một span mẫu trong trace.

Ba mối liên kết có cơ chế khác nhau:

| Liên kết | Cơ chế | Kết quả |
| --- | --- | --- |
| Logs ↔ Traces | Ghi trace ID và span ID vào log record hoặc Cloud Logging `LogEntry`. | Từ log mở được trace; từ trace xem được log của request. |
| Metrics ↔ Traces | Ghi histogram trong context của span để SDK tạo exemplar. | Từ điểm dữ liệu trên biểu đồ metric mở được trace đại diện. |
| Traces ↔ Traces | Truyền W3C Trace Context qua HTTP hoặc message metadata. | Các service và worker xuất hiện trong cùng trace với quan hệ parent-child hoặc liên kết phù hợp. |

Sơ đồ luồng dữ liệu:

~~~mermaid
flowchart LR
  REQ[HTTP request] --> APP[Spring Boot + OTel Java Agent]
  APP --> SPAN[Server span and business spans]
  APP --> METRIC[Histogram and counter]
  APP --> LOG[Structured JSON log]
  SPAN -->|OTLP| COL[OpenTelemetry Collector]
  METRIC -->|OTLP with exemplars| COL
  LOG -->|stdout / log agent| LOGGING[Cloud Logging]
  COL --> TRACE[Cloud Trace]
  COL --> MON[Cloud Monitoring]
  LOGGING -->|trace and span fields| TRACE
  MON -->|exemplar trace link| TRACE
~~~

Điểm quan trọng là các tín hiệu phải được tạo trong cùng một execution context. Nếu log được ghi sau khi context đã đóng, hoặc metric được ghi mà không truyền context của span, dữ liệu vẫn có thể được lưu nhưng liên kết sẽ bị mất.

## 2. Chuẩn bị Google Cloud project

Chọn một project dùng cho bài thực hành. Bật các API cần thiết:

~~~bash
gcloud config set project PROJECT_ID

gcloud services enable \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com
~~~

Nếu dùng một service account riêng cho Collector để gửi cả logs, metrics và traces qua Telemetry API, cấp các quyền ghi tương ứng trên project:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:otel-collector@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:otel-collector@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:otel-collector@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/telemetry.tracesWriter"
~~~

Thay `PROJECT_ID` bằng project ID thật và bảo đảm service account đã được tạo. Trên Cloud Run hoặc GKE, gắn service account này cho Collector theo cơ chế service identity hoặc Workload Identity phù hợp. Với môi trường local, dùng Application Default Credentials (ADC) của tài khoản phát triển trong lúc thử nghiệm. Không nhúng key JSON của service account vào image hoặc repository.

Người đọc kết quả cần quyền xem tương ứng:

| Nhu cầu | IAM role |
| --- | --- |
| Xem log | Logs Viewer — `roles/logging.viewer` |
| Xem metric và dashboard | Monitoring Viewer — `roles/monitoring.viewer` |
| Xem trace | Cloud Trace User — `roles/cloudtrace.user` |

Trong production, cấp quyền cho đúng nhóm vận hành hoặc service account, theo nguyên tắc tối thiểu. Quyền ghi telemetry của Collector và quyền đọc telemetry của người trực ca là hai nhiệm vụ riêng.

## 3. Instrument ứng dụng Java bằng OpenTelemetry

Bài thực hành dùng Spring Boot làm ví dụ. OpenTelemetry Java Agent tự động tạo span cho các framework được hỗ trợ, bao gồm request HTTP vào và một số lời gọi HTTP/database ra. Ta bổ sung một span nghiệp vụ và metric histogram để quan sát bước thanh toán.

### 3.1. Khởi chạy bằng OpenTelemetry Java Agent

Đặt file Java agent tại một đường dẫn ổn định trong image hoặc môi trường chạy, sau đó khởi chạy ứng dụng với tùy chọn `-javaagent`.

~~~bash
java -javaagent:/opt/otel/opentelemetry-javaagent.jar -jar app.jar
~~~

Cấu hình resource identity và OTLP exporter bằng biến môi trường:

~~~bash
OTEL_SERVICE_NAME=checkout-api
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,deployment.environment.name=lab,service.version=1.0.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_PROPAGATORS=tracecontext,baggage
OTEL_METRICS_EXEMPLAR_FILTER=trace_based
~~~

Trong ví dụ này Collector chạy cùng host, Pod hoặc Cloud Run instance và lắng nghe cổng gRPC 4317. Nếu Collector ở một địa chỉ khác, thay endpoint bằng địa chỉ nội bộ có thể truy cập. Không mở OTLP receiver ra Internet công cộng nếu chưa có xác thực, TLS và kiểm soát mạng phù hợp.

Java agent tự động instrument các framework đã hỗ trợ. Để tạo span và metric phản ánh quy tắc nghiệp vụ riêng, ứng dụng dùng OpenTelemetry API. Thêm dependency `opentelemetry-api` tương thích với phiên bản Java agent/SDK mà hệ thống chuẩn hóa; không khởi tạo một SDK độc lập thứ hai khi agent đã quản lý OpenTelemetry global instance.

### 3.2. Tạo span và histogram trong cùng context

Ví dụ service dưới đây tạo span `payment.authorize`, ghi log trong lúc span đang hoạt động và ghi metric trước khi kết thúc span. Các import được rút gọn để tập trung vào luồng telemetry.

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class PaymentService {
    private static final Logger logger =
        LoggerFactory.getLogger(PaymentService.class);

    private static final String INSTRUMENTATION_SCOPE =
        "com.example.checkout";

    private final io.opentelemetry.api.trace.Tracer tracer =
        GlobalOpenTelemetry.get().getTracer(INSTRUMENTATION_SCOPE);

    private final io.opentelemetry.api.metrics.Meter meter =
        GlobalOpenTelemetry.get().getMeter(INSTRUMENTATION_SCOPE);

    private final DoubleHistogram authorizationDuration =
        meter.histogramBuilder("payment.authorization.duration")
            .setDescription("Thời gian gọi nhà cung cấp thanh toán")
            .setUnit("s")
            .build();

    private final LongCounter authorizationCalls =
        meter.counterBuilder("payment.authorization.calls")
            .setDescription("Số lần gọi nhà cung cấp thanh toán")
            .build();

    public void authorize(String orderId) {
        Span span = tracer.spanBuilder("payment.authorize").startSpan();
        long startNanos = System.nanoTime();
        String result = "error";

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("payment.provider", "demo");

            try {
                logger.info(
                    "payment_authorization_started orderId={}", orderId);

                callPaymentProvider(orderId);

                result = "success";
                span.setStatus(StatusCode.OK);
                logger.info(
                    "payment_authorization_completed orderId={}", orderId);
            } catch (RuntimeException exception) {
                span.recordException(exception);
                span.setStatus(StatusCode.ERROR);
                logger.error(
                    "payment_authorization_failed orderId={}",
                    orderId,
                    exception);
                throw exception;
            } finally {
                Attributes attributes = Attributes.of(
                    AttributeKey.stringKey("provider"), "demo",
                    AttributeKey.stringKey("result"), result
                );

                // Context.current() chứa span payment.authorize đang hoạt động.
                Context context = Context.current();

                authorizationCalls.add(1, attributes, context);

                double elapsedSeconds =
                    (System.nanoTime() - startNanos) / 1_000_000_000.0;

                // Truyền context để SDK có thể gắn exemplar đến span hiện tại.
                authorizationDuration.record(
                    elapsedSeconds, attributes, context);
            }
        } finally {
            span.end();
        }
    }

    private void callPaymentProvider(String orderId) {
        // Thay bằng lời gọi HTTP/gRPC thật trong ứng dụng.
    }
}
~~~

Khi request HTTP đi vào controller, Java agent tạo server span. Vì `spanBuilder(...).startSpan()` lấy context hiện tại làm parent mặc định, span `payment.authorize` trở thành span con của request. `span.makeCurrent()` đưa span nghiệp vụ vào context hiện tại; mọi log và metric được ghi trong phạm vi này có thể dùng cùng trace context.

Trong code, metric chỉ dùng các thuộc tính có tập giá trị giới hạn như `provider` và `result`. Không thêm `orderId`, email, request ID hoặc trace ID vào metric labels vì mỗi giá trị riêng có thể tạo một time series mới và làm tăng cardinality.

### 3.3. Truyền context qua lời gọi downstream

Khi Java agent instrument HTTP client được hỗ trợ, nó có thể tự chèn W3C `traceparent` vào request ra. Dịch vụ nhận sẽ đọc header này và tạo span con nếu nó cũng được instrument.

Một header W3C Trace Context có dạng minh họa:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Trong đó trace ID được giữ xuyên suốt request; span ID thay đổi ở mỗi thao tác; cờ cuối biểu diễn trace flags, bao gồm thông tin sampled. Không tự tạo trace ID mới cho mỗi service nếu các service đang xử lý cùng một request.

Với công việc bất đồng bộ, context không phải lúc nào cũng tự đi theo khi chuyển sang executor hoặc thread khác. Hãy capture context tại nơi tạo công việc và khôi phục nó ở worker. Ví dụ với Java OpenTelemetry Context:

~~~java
Context captured = Context.current();

executor.submit(captured.wrap(() -> {
    logger.info("background task started");
    processMessage();
}));
~~~

Với Pub/Sub hoặc message broker, truyền trace context qua message attributes/headers theo W3C Trace Context và trích xuất ở consumer. Nếu một message đại diện cho nhiều request hoặc fan-in từ nhiều nguồn, có thể cần span links thay vì ép tất cả thành một quan hệ parent-child đơn giản.

## 4. Liên kết log với trace bằng structured logging

OpenTelemetry Java Agent có thể đưa thông tin span hiện tại vào MDC (Mapped Diagnostic Context) của các logging framework được hỗ trợ. Với Logback hoặc Log4j2, các field thường có sẵn là:

- `trace_id`: trace ID của span hiện tại.
- `span_id`: span ID của span hiện tại.
- `trace_flags`: trace flags của context hiện tại.

Để Cloud Logging tự liên kết log với trace, JSON log cần có các special fields tương ứng:

| JSON field | Ý nghĩa |
| --- | --- |
| `logging.googleapis.com/trace` | Resource name của trace, thường có dạng `projects/PROJECT_ID/traces/TRACE_ID`. |
| `logging.googleapis.com/spanId` | Span ID gồm 16 ký tự hexadecimal. |
| `logging.googleapis.com/trace_sampled` | Boolean cho biết trace đã được sample để lưu hay chưa. |

Ví dụ log JSON sau khi logging layout ánh xạ MDC sang special fields:

~~~json
{
  "severity": "INFO",
  "message": "Payment authorization completed",
  "event": "payment_authorization_completed",
  "service": "checkout-api",
  "environment": "lab",
  "order_id": "order-demo-42",
  "logging.googleapis.com/trace": "projects/PROJECT_ID/traces/4bf92f3577b34da6a3ce929d0e0e4736",
  "logging.googleapis.com/spanId": "00f067aa0ba902b7",
  "logging.googleapis.com/trace_sampled": true
}
~~~

Đây là cấu trúc đầu ra minh họa. Trong ứng dụng thật, dùng Log4j2 JSON Template Layout hoặc cấu hình logging tương đương để lấy `trace_id`, `span_id`, `trace_flags` từ MDC và ánh xạ sang các field Cloud Logging. Giá trị sampled trong `trace_flags` cần được chuyển thành boolean `true` hoặc `false`. Google Cloud có mẫu `GcpLayout.json` cho Log4j2. Nếu chỉ ghi `trace_id` như một field JSON thông thường mà không ánh xạ thành `logging.googleapis.com/trace`, Logs Explorer có thể hiển thị log nhưng không tạo liên kết trace như mong đợi.

Nếu log được gửi trực tiếp bằng Cloud Logging client library, có thể đặt các field `trace`, `spanId` và `traceSampled` trong `LogEntry`. Nếu log được gửi bằng OTLP Logs, bảo đảm LogRecord được phát ra trong OpenTelemetry Context đang chứa span; trace ID và span ID sẽ đi cùng log record. Với ứng dụng dùng log framework truyền thống, structured JSON stdout là cách đơn giản và phổ biến: Cloud Run/GKE thu thập stdout/stderr tự động; trên Compute Engine, dùng Ops Agent hoặc agent thu thập log phù hợp.

Không ghi access token, session cookie, mật khẩu, thông tin thanh toán đầy đủ hoặc dữ liệu cá nhân vào log. Trace ID và order ID trong ví dụ chỉ dùng để liên kết và minh họa; trong production, chọn định danh nghiệp vụ không nhạy cảm và giới hạn quyền đọc log.

## 5. Liên kết metric với trace bằng exemplars

Metric là dữ liệu tổng hợp. Histogram có thể ghi hàng nghìn lần đo trong một khoảng thời gian, nhưng biểu đồ chỉ hiển thị phân phối. Exemplar là một mẫu đo đại diện có thể gắn trace ID của request tương ứng. Nhờ vậy, người vận hành có thể chọn một điểm trên biểu đồ latency và mở trace của request mẫu.

Để tạo exemplar từ OpenTelemetry:

1. Cấu hình cả OpenTelemetry trace SDK và metric SDK.
2. Ghi metric trong lúc span đang hoạt động.
3. Truyền `Context.current()` của span vào thao tác ghi metric.
4. Dùng histogram/distribution metric và cấu hình exemplar filter phù hợp, thường là `trace_based`.
5. Đảm bảo trace được sample và được export thành công; exemplar không thể mở một trace chưa được lưu.

Ví dụ trong service ở mục 3, lời gọi sau nằm bên trong `span.makeCurrent()`:

~~~java
authorizationDuration.record(
    elapsedSeconds,
    attributes,
    Context.current()
);
~~~

Đây là chi tiết quyết định. Nếu bỏ context và chỉ ghi `authorizationDuration.record(elapsedSeconds)`, histogram vẫn có thể nhận số đo nhưng SDK không có context của span để gắn exemplar theo trace.

Trong Cloud Monitoring, histogram/distribution thường hiển thị dưới dạng heatmap. Khi metric data point có exemplar, biểu đồ có thể đánh dấu một điểm; chọn điểm đó để xem thông tin mẫu và mở trace liên quan. Không thêm trace ID vào metric label để thay thế exemplar. Trace ID có cardinality rất cao và làm metric trở nên khó tổng hợp.

Exemplar là một mẫu đại diện, không phải liên kết đến mọi lần ghi metric. Vì vậy, không phải mỗi request đều xuất hiện thành một dấu chấm trên biểu đồ. Số exemplar còn phụ thuộc sampling, exemplar reservoir, loại metric và khả năng lưu trữ/hiển thị của backend.

## 6. Thu thập và gửi telemetry bằng OpenTelemetry Collector

Collector nhận OTLP từ ứng dụng, áp dụng processor rồi gửi đến Google Cloud Telemetry API. Mô hình này giữ ứng dụng tương đối trung lập với backend; Collector chịu trách nhiệm xác thực và export.

### 6.1. Cấu hình Collector tối giản cho bài lab

Ví dụ sau minh họa receiver OTLP gRPC và exporter OTLP gRPC đến Google Cloud. Dùng Google-Built OpenTelemetry Collector có sẵn extension xác thực Google Cloud. Đây là cấu hình học tập để làm rõ đường đi của telemetry; môi trường production nên bắt đầu từ cấu hình khuyến nghị của Google-Built Collector và giữ các processor, health check, resource detection, memory limiter và batch settings cần thiết.

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 65
    spike_limit_percentage: 20
  batch:
    timeout: 5s

exporters:
  otlp_grpc:
    endpoint: telemetry.googleapis.com:443
    balancer_name: pick_first
    auth:
      authenticator: googleclientauth

extensions:
  googleclientauth:

service:
  extensions: [googleclientauth]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_grpc]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_grpc]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_grpc]
~~~

Pipeline `logs` trong cấu hình trên nhận log record được gửi bằng OTLP. Nếu ứng dụng đang ghi JSON ra stdout, hãy bảo đảm nền tảng hoặc filelog receiver thu thập stdout đó; không có receiver nào trong cấu hình tối giản này tự đọc file log. Dù dùng đường đi nào, log phải giữ trace context hoặc special fields để liên kết với trace.

Với Google-Built Collector, exporter `otlp_grpc` gửi telemetry đến `telemetry.googleapis.com:443` và dùng `googleclientauth` để xác thực bằng ADC/service identity. Collector cần được chạy dưới danh tính có quyền ghi phù hợp. Cấu hình receiver ở `0.0.0.0` chỉ nên được dùng trong mạng nội bộ đã kiểm soát; giới hạn truy cập cổng 4317/4318 cho workload tin cậy.

### 6.2. Chọn đường đi cho logs

Có hai cách phổ biến:

| Cách thu thập log | Luồng | Khi dùng |
| --- | --- | --- |
| Structured stdout | Java logger → JSON stdout → Cloud Run/GKE logging agent hoặc Ops Agent → Cloud Logging | Ứng dụng đã dùng SLF4J/Logback/Log4j2 và muốn giữ logging framework hiện tại. |
| OTLP Logs | OTel Logs SDK/appender → OTLP receiver → Collector → Telemetry API | Muốn gửi LogRecord theo chuẩn OTel qua cùng pipeline Collector. |

Không gửi cùng một log qua cả stdout agent và OTLP pipeline nếu chưa chủ ý xử lý trùng lặp. Hãy chọn một đường ghi chính và xác minh trace context được bảo toàn ở đường đó.

### 6.3. Flush và vòng đời ứng dụng

Khi ứng dụng hoặc Collector dừng, dữ liệu đang nằm trong batch có thể chưa được export. SDK cần shutdown đúng cách để flush các processor/exporter; Collector cũng cần nhận tín hiệu dừng và hoàn tất batch trong khoảng thời gian cho phép. Với container bị terminate, cấu hình termination grace period đủ để ứng dụng và Collector đóng sạch.

Theo dõi chính Collector bằng health check và self-observability metrics. Nếu collector hết bộ nhớ, không thể xác thực hoặc mất kết nối đến Telemetry API, cả ba tín hiệu có thể ngừng xuất hiện dù ứng dụng vẫn chạy.

## 7. Thực hành end-to-end

Dùng một endpoint Spring Boot có thể gọi bước thanh toán. Giả sử controller có route `GET /orders/{id}` và gọi `paymentService.authorize(id)`.

### Bước 1: Chạy ứng dụng và Collector

- Khởi chạy Collector với cấu hình ở mục 6.
- Khởi chạy Spring Boot bằng OpenTelemetry Java Agent.
- Đặt `OTEL_SERVICE_NAME=checkout-api`, resource attributes cho environment/version và endpoint OTLP trỏ đến Collector.
- Bảo đảm service account của Collector có quyền ghi telemetry.

### Bước 2: Tạo lưu lượng thử nghiệm

Gửi nhiều request thành công và một số request gây lỗi có kiểm soát. Ví dụ:

~~~bash
curl http://localhost:8080/orders/order-demo-42
curl http://localhost:8080/orders/order-demo-43
curl http://localhost:8080/orders/order-demo-fail?simulateFailure=true
~~~

Điều chỉnh route và cách tạo lỗi theo ứng dụng mẫu. Không dùng dữ liệu production thật để chạy thử.

### Bước 3: Kiểm tra trace

Trong Google Cloud Console:

1. Mở **Trace → Trace Explorer**.
2. Chọn project và khoảng thời gian vừa gửi request.
3. Lọc theo service `checkout-api` hoặc tìm span `payment.authorize`.
4. Mở trace và xác minh span HTTP server là parent của span nghiệp vụ.
5. Nếu request gọi service downstream, xác minh trace ID được giữ nguyên và có span của service đó.

### Bước 4: Kiểm tra log liên kết

Mở **Logging → Logs Explorer**, lọc theo service và sự kiện:

~~~text
resource.type="cloud_run_revision"
jsonPayload.service="checkout-api"
jsonPayload.event="payment_authorization_completed"
~~~

Nếu chạy trên GKE hoặc Compute Engine, thay `resource.type` và field theo loại resource thực tế. Mở log entry và kiểm tra trường `trace` cùng `spanId`. Chọn liên kết trace hoặc mở Trace Explorer bằng trace ID để xem waterfall tương ứng.

Nếu log không có special fields, kiểm tra logging layout và MDC mapping. Nếu log được gửi qua OTLP, kiểm tra LogRecord có trace context. Chỉ việc đặt `trace_id` trong message text không tạo liên kết tự động.

### Bước 5: Kiểm tra metric và exemplar

Mở **Monitoring → Metrics Explorer**:

1. Tìm metric `payment.authorization.duration` hoặc tên metric tương ứng sau khi OTLP mapping.
2. Chọn biểu đồ histogram/distribution và phạm vi thời gian của bài lab.
3. Kiểm tra metric có dữ liệu và các resource labels nhận diện đúng service/environment.
4. Nếu có exemplar, chọn dấu đánh dấu trên heatmap để mở trace mẫu.
5. Đối chiếu trace với log có cùng trace ID và span ID.

Không thấy exemplar chưa chắc metric export bị lỗi. Kiểm tra trước xem measurement có được ghi trong active span, có truyền context, span có được sample và export, metric có phải histogram/distribution và exemplar filter có được bật không.

## 8. Truy vấn và đối chiếu ba tín hiệu

Khi đã có dữ liệu, dùng các trường chung để chuyển từ tín hiệu này sang tín hiệu khác.

| Mục tiêu | Điểm bắt đầu | Trường dùng để đối chiếu |
| --- | --- | --- |
| Từ log mở trace | Logs Explorer | `trace`, `spanId`, `traceSampled` |
| Từ trace tìm log | Trace Explorer → Logs & Events | Trace ID, span ID và khoảng thời gian |
| Từ metric mở trace | Metrics Explorer histogram exemplar | Trace ID trong exemplar |
| Tìm lỗi theo service version | Logs Explorer hoặc Metrics Explorer | `service.name`, `service.version`, environment |
| Theo request qua nhiều service | Trace Explorer | Trace ID, parent span ID và span links |

Ví dụ lọc log của một trace cụ thể trong Logs Explorer:

~~~text
trace="projects/PROJECT_ID/traces/TRACE_ID"
~~~

Ví dụ lọc log lỗi của service trong một khoảng thời gian:

~~~text
resource.type="cloud_run_revision"
severity>=ERROR
jsonPayload.service="checkout-api"
jsonPayload.environment="production"
~~~

Các field trong `jsonPayload` phụ thuộc schema log mà ứng dụng ghi ra. Trường `trace` là field cấp LogEntry; đừng nhầm nó với `jsonPayload.trace_id` nếu ứng dụng chỉ ghi trace ID như một thuộc tính JSON bình thường.

## 9. Xử lý lỗi liên kết thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Trace có nhưng log không gắn trace | Logging layout không xuất trace/span special fields; log được ghi ngoài active span. | Kiểm tra MDC, `logging.googleapis.com/trace`, `spanId` và vị trí ghi log. |
| Log có trace ID nhưng Trace Explorer không tìm thấy trace | Trace chưa được sample/export, sai project ID hoặc exporter lỗi. | Kiểm tra `trace_sampled`, Collector logs, ADC và trace ID. |
| Mỗi service tạo một trace riêng | Trace context không được truyền qua HTTP hoặc message metadata. | Kiểm tra `traceparent`, propagator và instrumentation của client/server. |
| Metric có dữ liệu nhưng không có exemplar | Histogram được ghi ngoài span, không truyền Context, trace không sampled hoặc exemplar filter tắt. | Ghi metric bên trong span, truyền context và kiểm tra cấu hình exemplar. |
| Log của async worker không có trace cha | Context bị mất khi chuyển thread hoặc qua queue. | Capture/restore Context hoặc inject/extract W3C context qua message attributes. |
| Chỉ một phần telemetry đến Google Cloud | Collector pipeline thiếu signal, exporter lỗi, quyền IAM thiếu hoặc batch chưa flush. | Kiểm tra receiver/pipeline/exporter, quyền ghi, health endpoint và shutdown. |
| Log xuất hiện hai lần | Vừa gửi stdout qua agent vừa gửi cùng record qua OTLP Logs. | Chọn một đường thu thập chính hoặc lọc duplicate có chủ đích. |
| Dashboard metric có quá nhiều time series | Dùng ID duy nhất làm metric attribute. | Bỏ user/request/trace ID khỏi metric labels; giữ ID trong logs/traces. |

Một trace có thể không được lưu dù log vẫn được ghi. Nếu sampling loại bỏ trace, log vẫn có thể mang trace ID nhưng liên kết mở trace sẽ không có kết quả. Điều này là hành vi có thể xảy ra khi sampling được bật, không nhất thiết là lỗi logging.

## 10. Thực hành tốt khi vận hành

- **Dùng cùng resource identity:** `service.name`, namespace, version và environment phải nhất quán giữa logs, metrics và traces.
- **Truyền context xuyên suốt:** dùng W3C Trace Context cho HTTP và message metadata; bảo đảm context được khôi phục ở worker bất đồng bộ.
- **Ghi log trong span phù hợp:** log lỗi ở đúng span đang xử lý dependency hoặc nghiệp vụ để span ID giúp xác định vị trí phát sinh.
- **Dùng exemplar cho metric:** ghi histogram trong active span và truyền context; không đưa trace ID vào metric label.
- **Giữ metric cardinality thấp:** dùng route template, status class, provider và result có tập giá trị giới hạn.
- **Thiết kế sampling có chủ đích:** trace quan trọng cho điều tra phải có cơ hội được lưu; các dịch vụ downstream cần tôn trọng sampling context.
- **Bảo vệ dữ liệu:** không ghi secret hoặc dữ liệu cá nhân nhạy cảm; giới hạn IAM, bảo vệ OTLP endpoint và log storage.
- **Giám sát pipeline:** theo dõi Collector health, memory, export errors, dropped spans/metrics/logs và thời gian batch.
- **Kiểm tra sau phát hành:** chạy thử một request và xác minh đủ ba tín hiệu, trace-log link và metric exemplar trong môi trường staging trước khi rollout rộng.

## 11. Checklist hoàn thành bài thực hành

- [ ] Bật Logging, Monitoring, Trace và Telemetry APIs.
- [ ] Gán quyền ghi telemetry cho service account của Collector.
- [ ] Chạy ứng dụng bằng OpenTelemetry Java Agent và cấu hình OTLP endpoint.
- [ ] Xác nhận server span và span nghiệp vụ `payment.authorize` xuất hiện trong cùng trace.
- [ ] Truyền trace context qua lời gọi downstream hoặc message metadata.
- [ ] Ghi log JSON trong active span và ánh xạ trace/span sang special fields của Cloud Logging.
- [ ] Ghi histogram metric trong active span với `Context.current()`.
- [ ] Bật trace-based exemplar filter và kiểm tra exemplar trên histogram.
- [ ] Mở được trace từ log và từ exemplar.
- [ ] Kiểm tra Collector health, quyền IAM, sampling và cardinality.
- [ ] Thử một request lỗi và xác minh log, span status, exception và metric phản ánh đúng kết quả.

## Tài liệu tham khảo

- [Java instrumentation sample for Cloud Trace](https://docs.cloud.google.com/trace/docs/setup/java-ot) — dùng OpenTelemetry Java Agent, cấu hình structured JSON logs và liên kết log với trace.
- [Link log entries with traces](https://docs.cloud.google.com/trace/docs/trace-log-integration) — các field `trace`, `spanId`, `traceSampled` và cách liên kết log entry.
- [Correlate metrics and traces by using exemplars](https://docs.cloud.google.com/stackdriver/docs/instrumentation/advanced-topics/exemplars) — điều kiện tạo exemplar từ metric measurement và span context.
- [Google-Built OpenTelemetry Collector](https://docs.cloud.google.com/stackdriver/docs/instrumentation/google-built-otel) — Collector, receiver, processor và exporter cho Google Cloud.
- [Collector-based instrumentation samples](https://docs.cloud.google.com/trace/docs/setup/sample-overview) — kiến trúc OTLP, quyền IAM, API và mẫu cho Java.
- [Choose an instrumentation approach](https://docs.cloud.google.com/stackdriver/docs/instrumentation/choose-approach) — lựa chọn collector-based export và direct export.
- [Structured logging](https://docs.cloud.google.com/logging/docs/structured-logging) — JSON payload và các special fields của Cloud Logging.
- [OpenTelemetry Java SDK](https://opentelemetry.io/docs/languages/java/sdk/) — SDK, tracer provider, meter provider, logger provider và context propagation.
- [OpenTelemetry Java instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/) — agent, instrumentation libraries và context propagation.

