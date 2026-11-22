# Structured logging, trace context và OpenTelemetry cho Java

Một yêu cầu tạo đơn hàng đi qua API Java, truy vấn Cloud SQL, gọi dịch vụ thanh toán rồi gửi sự kiện đến Pub/Sub. Khi khách hàng báo “đơn hàng bị chậm”, một log `ERROR payment timeout` chưa đủ để biết request nào thất bại, dependency nào chậm, lỗi xuất hiện sau bản phát hành nào và bao nhiêu request khác cùng chịu ảnh hưởng.

**Structured logging** giúp biến log thành dữ liệu có cấu trúc để truy vấn theo trường. **Trace context** giúp liên kết những hoạt động thuộc cùng một request, kể cả khi request đi qua nhiều service. **OpenTelemetry (OTel)** cung cấp API, SDK, Java Agent và giao thức truyền telemetry để thu thập trace, metric và log theo cách ít phụ thuộc nhà cung cấp. Kết hợp ba thành phần, đội vận hành có thể đi từ một log lỗi tới trace của request, rồi tới các span của database, HTTP client và workload liên quan.

Bài học thuộc chương **Java và Spring trên GCP** trong module **CLOUD_PROVIDERS_GCP**. Module khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Đây là nền tảng observability để biến dữ liệu thực thi của ứng dụng Java thành bằng chứng phục vụ điều tra và ra quyết định.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt log dạng văn bản với log JSON có cấu trúc trong Cloud Logging.
- Sử dụng các trường đặc biệt `severity`, `message`, `logging.googleapis.com/trace` và `logging.googleapis.com/spanId`.
- Giải thích quan hệ giữa trace ID, span ID, parent span, trace context, sampling và log correlation.
- Cấu hình OpenTelemetry Java Agent cho ứng dụng Java/Spring Boot.
- Tạo log JSON kèm trace context hiện hành và dùng SLF4J để ghi log nghiệp vụ.
- Truyền ngữ cảnh qua HTTP, gRPC, thread pool và xử lý bất đồng bộ.
- Định tuyến telemetry tới Cloud Logging, Cloud Monitoring và Cloud Trace.
- Truy vấn, đối chiếu log–trace và khắc phục những lỗi cấu hình phổ biến.
- Xây dựng chính sách bảo mật, chi phí và vận hành telemetry cho production.

## 1. Bài toán: quan sát một request qua nhiều dịch vụ

Giả sử API `orders-api` chạy trên Cloud Run. Khi nhận `POST /v1/orders`, ứng dụng:

1. Xác thực request.
2. Đọc trạng thái tồn kho từ Cloud SQL.
3. Gọi `payment-api` qua HTTP.
4. Gửi sự kiện `order.created` đến Pub/Sub.
5. Trả kết quả về client.

Nếu chỉ ghi những dòng:

~~~text
INFO  create order
INFO  select inventory
ERROR payment timeout
~~~

bạn không biết dòng nào thuộc request nào khi có hàng trăm request chạy đồng thời. Ngoài ra, log không cho thấy call nào chiếm phần lớn độ trễ.

Một thiết kế quan sát tốt bổ sung:

- **Log có cấu trúc:** `service`, `environment`, `event`, `route`, `status`, `duration_ms`, `trace`, `spanId`.
- **Distributed trace:** một trace đại diện cho luồng xử lý request, gồm các span con như `POST /v1/orders`, `SELECT inventory`, `POST /charge`.
- **Metric:** số request, tỷ lệ lỗi, latency và saturation để biết vấn đề có lan rộng hay không.
- **Alert/runbook:** cảnh báo khi tỷ lệ lỗi hoặc latency vượt ngưỡng và liên kết đến Logs Explorer, Trace Explorer.

### Sơ đồ quan sát end-to-end

~~~mermaid
flowchart LR
  A[HTTP client] --> B[Java / Spring API]
  B --> C[Cloud SQL]
  B --> D[Payment API]
  B --> E[Pub/Sub]
  B --> F[JSON logs → stdout]
  F --> G[Cloud Logging]
  B --> H[OpenTelemetry Java Agent / SDK]
  H --> I[OTLP exporter]
  I --> J[OpenTelemetry Collector]
  J --> K[Cloud Trace]
  J --> L[Cloud Monitoring]
  G -. trace ID .-> K
  K -. trace / span .-> G
~~~

Sơ đồ thể hiện một phương án: log JSON được thu từ `stdout`, còn trace và metric đi qua OTLP/Collector. Có thể gửi cả ba loại tín hiệu qua OTLP nếu hệ thống và Collector được cấu hình phù hợp, nhưng không nên mặc định dùng đồng thời nhiều đường ingest cho cùng một log vì có thể tạo bản ghi trùng lặp.

## 2. Structured logging trong Cloud Logging

### Text log và JSON log

Cloud Logging lưu log ở dạng `LogEntry`. Hai kiểu payload thường gặp:

| Kiểu | Ví dụ | Khả năng truy vấn |
|---|---|---|
| `textPayload` | `Payment failed after 1200 ms` | Tìm chuỗi và dùng các metadata chuẩn |
| `jsonPayload` | `{"event":"payment.failed","duration_ms":1200}` | Lọc chính xác theo `jsonPayload.event`, `jsonPayload.duration_ms` |

Với structured logging, ứng dụng phát ra **một đối tượng JSON trên một dòng**, thay vì một chuỗi văn bản chứa nhiều phần được ghép bằng dấu cách. Các field có tên và kiểu dữ liệu ổn định sẽ giúp truy vấn, tổng hợp và xây log-based metrics đáng tin cậy.

Ví dụ dòng log JSON cho một request thất bại:

~~~json
{
  "severity": "ERROR",
  "message": "Payment provider timed out",
  "service": "orders-api",
  "environment": "staging",
  "event": "payment.timeout",
  "route": "/v1/orders",
  "duration_ms": 1200,
  "payment_provider": "provider-a",
  "logging.googleapis.com/trace": "projects/demo-observability/traces/4bf92f3577b34da6a3ce929d0e0e4736",
  "logging.googleapis.com/spanId": "00f067aa0ba902b7",
  "logging.googleapis.com/trace_sampled": true
}
~~~

Các giá trị ở trên chỉ dùng minh họa; không phải trace đang tồn tại thật. Trong Cloud Logging, những field đặc biệt được tách ra thành metadata của `LogEntry`, còn các field như `event`, `route`, `duration_ms` thường nằm trong `jsonPayload`.

### Trường đặc biệt cần ghi đúng

| Trường trong JSON | Field sau khi Cloud Logging parse | Lưu ý |
|---|---|---|
| `severity` | `LogEntry.severity` | Dùng `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`... |
| `message` | Thông điệp chính khi hiển thị | Viết ngắn gọn, không đưa secret |
| `timestamp` hoặc `time` | `LogEntry.timestamp` | Dùng timestamp ISO 8601 có timezone nếu tự cung cấp |
| `httpRequest` | `LogEntry.httpRequest` | Thông tin HTTP khi có schema phù hợp |
| `logging.googleapis.com/trace` | `LogEntry.trace` | Đầy đủ `projects/PROJECT_ID/traces/TRACE_ID` |
| `logging.googleapis.com/spanId` | `LogEntry.spanId` | Span ID 16 ký tự hex |
| `logging.googleapis.com/trace_sampled` | `LogEntry.traceSampled` | **Boolean** `true`/`false`, không phải chuỗi |
| `logging.googleapis.com/labels` | `LogEntry.labels` | Map nhãn có giá trị dạng string |
| Trường nghiệp vụ khác | `LogEntry.jsonPayload` | Lưu dữ liệu có thể lọc/query |

Lưu ý mapping trên áp dụng cho JSON một dòng khi được built-in logging agent của Cloud Run/GKE thu thập. Nếu ứng dụng gửi log trực tiếp bằng Cloud Logging API hoặc OTLP, sơ đồ ánh xạ dựa trên client/receiver tương ứng; hãy xác nhận đường ingest thay vì cho rằng mọi backend đều chuyển đổi field giống nhau.

### Thiết kế schema log ổn định

Một log nghiệp vụ tốt thường có:

- `event`: tên sự kiện ổn định, chẳng hạn `order.create.failed`.
- `service`, `service_version`, `environment`: thông tin vận hành.
- `route`: **route template** (`/v1/orders/{id}`) thay vì URL có ID thực.
- `duration_ms`: thời lượng dạng số, không phải chuỗi `"1200ms"`.
- `error_type`: loại lỗi ổn định như `UPSTREAM_TIMEOUT`.
- `retryable`: boolean nếu cần xử lý retry.
- `trace` và `spanId`: các liên kết kỹ thuật tới trace/span hiện hành.

Dùng cùng tên field giữa các service để một truy vấn có thể tìm đúng nhóm sự kiện. Tránh ghi toàn bộ request/response body chỉ để “dễ debug”: payload có thể chứa token, email, thông tin thanh toán hoặc dữ liệu nhạy cảm.

## 3. Cloud Run, GKE và Compute Engine thu nhận log khác nhau

### Cloud Run

Cloud Run tự thu thập log từ `stdout`/`stderr` của container. Một dòng JSON hợp lệ được parse thành structured log; log thường có `resource.type="cloud_run_revision"`, tên service và revision tương ứng. Cloud Run còn có **request log** do nền tảng tạo và **system log** riêng.

Không cần cài thêm Ops Agent vào Cloud Run chỉ để thu stdout. Nếu dùng Cloud Logging API hoặc một exporter khác đồng thời với stdout, cần tránh ghi cùng event hai lần.

### GKE

Với GKE có cơ chế logging được bật, stdout/stderr của container được thu từ node và đưa vào Cloud Logging. Resource label của log phụ thuộc mô hình collection và cấu hình cluster; thường liên quan `k8s_container` và các nhãn namespace, pod, container.

Đội vận hành nên chuẩn hóa `service.name` ở OTel và `service` trong application log, đồng thời kiểm tra nhãn workload thực tế để truy vấn không lẫn các deployment.

### Compute Engine

VM không có hành vi giống Cloud Run. Đối với log file trên VM, cấu hình **Ops Agent** với receiver và `parse_json` processor nếu cần nhận dạng JSON; kiểm tra đường dẫn, quyền đọc và cấu hình pipeline. Ops Agent có thể thu thêm host metrics và OTLP traces/metrics theo phiên bản và cấu hình.

| Môi trường | Đường log thường dùng | Điều cần kiểm tra |
|---|---|---|
| Cloud Run | Container stdout/stderr → Cloud Logging | JSON một dòng, trace field và request correlation |
| GKE | Container stdout/stderr → logging pipeline của cluster | Logging bật, resource labels và không trùng exporter |
| Compute Engine | Ops Agent đọc file hoặc nguồn phù hợp | Receiver, parse JSON, permissions và agent status |
| Local Java | Console hoặc file JSON | Local viewer / collector, chưa chắc có Cloud Logging |

## 4. Trace, span và trace context

### Distributed trace là gì?

Một **trace** đại diện cho luồng xử lý của một thao tác xuyên nhiều service. Trong trace có nhiều **span**; mỗi span ghi nhận công việc riêng, ví dụ xử lý controller, truy vấn SQL hoặc gọi HTTP.

- **Trace ID:** 16 byte, thường hiển thị dưới dạng 32 ký tự hex; giữ nguyên trong toàn trace.
- **Span ID:** 8 byte, 16 ký tự hex; khác nhau giữa các span.
- **Parent span:** định danh quan hệ cha–con để dựng waterfall.
- **Attributes:** thông tin như `http.request.method`, route, database system hoặc peer service, theo semantic conventions.
- **Events:** mốc quan trọng bên trong span.
- **Status:** trạng thái span, có thể gắn lỗi và exception khi cần.

Một log không tự biến thành span. Một trace ID được ghi vào log chỉ là **mối liên kết** để tìm dữ liệu liên quan; phải có span được tạo, được sampling/export và được ingest thành công thì Trace Explorer mới hiển thị trace hoàn chỉnh.

### W3C Trace Context

OpenTelemetry Java Agent thường dùng chuẩn W3C Trace Context để truyền ngữ cảnh qua HTTP. Header minh họa:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Ý nghĩa:

| Thành phần | Giá trị minh họa | Vai trò |
|---|---|---|
| version | `00` | Phiên bản format |
| trace-id | `4bf92f3577b34da6a3ce929d0e0e4736` | Kết nối các span cùng trace |
| parent-id | `00f067aa0ba902b7` | Span của caller |
| trace-flags | `01` | Bit sampled trong header |

Header `tracestate` bổ sung thông tin của vendor khi cần. `baggage` truyền key/value qua service boundary; **không** dùng baggage để chứa mật khẩu, token hoặc dữ liệu cá nhân, vì nó có thể đi tiếp sang hệ thống khác.

### Trace context khác correlation ID

Một ứng dụng có thể dùng `X-Request-Id` do load balancer hoặc gateway cấp. Đây là correlation ID hữu ích nhưng **không tương đương trace ID**. Request ID có thể thay đổi ở mỗi hop; trace ID thường giữ nguyên qua các span của cùng distributed trace.

Có thể lưu cả request ID và trace ID trong log, miễn chúng là các field tách biệt và có quy tắc tạo/kiểm tra rõ ràng.

### X-Cloud-Trace-Context trên Cloud Run

Cloud Run có header `X-Cloud-Trace-Context` và request logs có thể liên kết theo trace của nền tảng. Đối với container log JSON, trường `logging.googleapis.com/trace` cần có **trace ID trùng với request log** để Logs Explorer nhóm log con bên dưới request log.

Khi dùng OTel Java Agent với W3C `traceparent`, cần xác nhận trace context của ứng dụng và request log nền tảng có cùng trace ID. Nếu các propagator hoặc header đầu vào tạo hai trace khác nhau, container logs vẫn có trace ID hợp lệ nhưng sẽ không nằm dưới request log mong đợi. Không tự động “vá” bằng cách ghi một ID ngẫu nhiên vào trace field.

## 5. Ba tín hiệu trong OpenTelemetry

OpenTelemetry chuẩn hóa ba tín hiệu chính:

| Signal | Dữ liệu | Nơi điều tra trên GCP |
|---|---|---|
| Traces | Trace, spans, parent relationships, span events | Cloud Trace / Trace Explorer |
| Metrics | Counter, histogram, gauge và time series | Cloud Monitoring / Metrics Explorer |
| Logs | Log records, severity, attributes và trace context | Cloud Logging / Logs Explorer |

Các thành phần:

- **API:** được gọi từ mã ứng dụng để tạo instrumentation.
- **SDK:** hiện thực thu thập, sampling, batching và exporting.
- **Java Agent:** tự instrument nhiều thư viện phổ biến bằng bytecode instrumentation, giảm nhu cầu sửa source.
- **OTLP:** giao thức đưa telemetry từ SDK/Agent tới Collector hoặc endpoint hỗ trợ.
- **Collector:** nhận, xử lý, batch, lọc và export các signal tới backend.
- **Semantic conventions:** quy ước tên attribute cho HTTP, RPC, DB và messaging để các hệ thống hiểu thống nhất.

### Instrumentation tự động và thủ công

**Automatic instrumentation** bằng Java Agent có thể tạo span cho inbound HTTP, outbound HTTP, JDBC, gRPC và một số thư viện được hỗ trợ. Cách này tạo lớp quan sát cơ bản mà không sửa code nghiệp vụ.

**Manual instrumentation** dùng API `Tracer`, `Span` và `Context` để bổ sung span cho những bước nghiệp vụ có ý nghĩa, ví dụ `reserve-inventory` hoặc `validate-order`.

Hai cách có thể kết hợp: Java Agent ghi các span hạ tầng; manual spans mô tả công việc nghiệp vụ. Tránh tạo nhiều span trùng chức năng vì chúng làm trace rối và tăng dữ liệu ingest.

## 6. Cấu hình OpenTelemetry Java Agent

### Chuẩn bị

- Java và framework trong phạm vi phiên bản Java Agent hỗ trợ.
- Ứng dụng Spring Boot hoặc Java HTTP server.
- File `opentelemetry-javaagent.jar` được tải từ release chính thức và **pin phiên bản cụ thể**.
- Endpoint OTLP của Collector hoặc backend được hỗ trợ.
- Quyền IAM của danh tính xuất telemetry.

### Kích hoạt agent

Trên JVM, thêm `-javaagent`:

~~~bash
java -javaagent:/opt/otel/opentelemetry-javaagent.jar -jar orders-api.jar
~~~

Hoặc dùng biến môi trường:

~~~bash
export JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/opentelemetry-javaagent.jar"
java -jar orders-api.jar
~~~

Trong container image, copy file agent vào image một cách có kiểm soát. Không download một URL `latest` chưa pin ở mỗi lần khởi động production; nên xác minh checksum và xây image bất biến.

### Biến môi trường OTLP mẫu

Ví dụ Collector chạy trên hostname `otel-collector` và nhận **OTLP HTTP/protobuf** qua cổng 4318:

~~~bash
export OTEL_SERVICE_NAME="orders-api"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=staging,service.version=1.2.3"
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_METRICS_EXPORTER="otlp"
export OTEL_LOGS_EXPORTER="none"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4318"
export JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/opentelemetry-javaagent.jar"
~~~

Giải thích:

- `OTEL_SERVICE_NAME` là tên service được dùng để nhóm trace/metric.
- `OTEL_RESOURCE_ATTRIBUTES` gắn môi trường và phiên bản phát hành, giúp so sánh before/after deployment.
- `OTEL_TRACES_EXPORTER` và `OTEL_METRICS_EXPORTER` đưa hai signal vào OTLP.
- `OTEL_LOGS_EXPORTER=none` chỉ tắt **OTLP log export** từ Agent trong mô hình này; ứng dụng vẫn ghi structured JSON ra stdout để Cloud Run thu nhận.
- `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` tương ứng cổng 4318. Nếu Collector nhận gRPC (thường cổng 4317), phải dùng cấu hình protocol và endpoint gRPC phù hợp.
- DNS `otel-collector` chỉ là ví dụ. Trong Cloud Run sidecar có thể dùng localhost; trên GKE thường dùng địa chỉ Service. Chọn đường truyền theo kiến trúc thật.

Không gửi OTLP không mã hóa qua mạng công cộng. Với Collector ngoài localhost hoặc mạng tin cậy, cấu hình TLS, auth và egress policy phù hợp.

### Sampling

Sampling giảm lượng span được ghi nhận và xuất đi. Ví dụ cấu hình sampling theo tỷ lệ 10% (chỉ nên dùng sau khi hiểu lưu lượng và yêu cầu điều tra):

~~~bash
export OTEL_TRACES_SAMPLER="parentbased_traceidratio"
export OTEL_TRACES_SAMPLER_ARG="0.10"
~~~

`parentbased_traceidratio` giúp tôn trọng sampling decision từ parent khi có remote parent hợp lệ. Log vẫn có thể được ghi cho request không được sampled; khi đó trace ID trong log **không bảo đảm** có trace tương ứng trong Cloud Trace.

## 7. Structured JSON logging trong ứng dụng Java/Spring

Có hai lối triển khai phổ biến:

1. Dùng SLF4J với Logback hoặc Log4j2 JSON layout; Java Agent có thể đưa trace context vào MDC và JSON encoder ánh xạ sang field chuẩn của Cloud Logging.
2. Tự tạo một JSON log entry với structured fields và trace context lấy từ `Span.current()`. Cách thứ hai hữu ích để hiểu định dạng; với production nên chọn logger/encoder đã được kiểm thử.

### Lựa chọn A: SLF4J + Log4j2 JSON Template Layout

Trong Spring Boot, nếu sử dụng Log4j2 thay cho Logback mặc định, cấu hình dependency theo BOM tương thích: loại starter logging mặc định khi cần và thêm `spring-boot-starter-log4j2`. JSON Template Layout yêu cầu module `log4j-layout-template-json` tương ứng với phiên bản Log4j2.

Ví dụ file `log4j2.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="JSON" target="SYSTEM_OUT">
      <JsonTemplateLayout eventTemplateUri="classpath:GcpLayout.json"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="INFO">
      <AppenderRef ref="JSON"/>
    </Root>
  </Loggers>
</Configuration>
~~~

`GcpLayout.json` là **template tùy chỉnh phải được đóng gói** vào classpath. Template cần ánh xạ severity và message, lấy MDC trace ID/span ID, tạo trace resource name `projects/PROJECT_ID/traces/TRACE_ID`, và đưa sampled flag thành boolean. Cấu hình XML phía trên **không đủ để chạy một mình** nếu thiếu template và module JSON Template Layout.

Google Cloud cung cấp một mẫu Spring Boot dùng chính cách tiếp cận này. Có thể chạy mẫu và xem cấu hình template thật tại tài liệu [Java instrumentation sample](https://cloud.google.com/trace/docs/setup/java-ot); tránh sao chép một template cũ mà không xác nhận cách MDC của phiên bản Java Agent đang dùng được đặt tên.

Trong mã nghiệp vụ, ghi log qua SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger logger =
        LoggerFactory.getLogger(OrderService.class);

    public void submitOrder(int itemCount) {
        logger.info("Submitting order with itemCount={}", itemCount);
        // Logic nghiệp vụ.
    }
}
~~~

Với Java Agent được cấu hình phù hợp, MDC chứa thông tin active span. JSON layout chịu trách nhiệm chuyển MDC thành field tương ứng. Việc có trace ID trong MDC **không tự động** làm log thành structured JSON; phải có encoder/layout xuất đúng format.

### Lựa chọn B: tạo JSON event có trace context hiện hành

Đoạn Java sau minh họa định dạng độc lập với một JSON logging framework cụ thể. Nó dùng Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper`), OpenTelemetry API và xuất **một JSON object trên một dòng**. Trong dự án dùng Jackson 3, điều chỉnh package/API tương ứng.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import java.util.LinkedHashMap;
import java.util.Map;

public final class GcpJsonEvents {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private final String projectId;

    public GcpJsonEvents(String projectId) {
        if (projectId == null || projectId.isBlank()) {
            throw new IllegalArgumentException("projectId is required");
        }
        this.projectId = projectId;
    }

    public void log(
        String severity,
        String event,
        String message,
        String route,
        long durationMs
    ) {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("severity", severity);
        entry.put("message", message);
        entry.put("service", "orders-api");
        entry.put("event", event);
        entry.put("route", route);
        entry.put("duration_ms", durationMs);

        SpanContext context = Span.current().getSpanContext();
        if (context.isValid()) {
            entry.put(
                "logging.googleapis.com/trace",
                "projects/" + projectId + "/traces/" + context.getTraceId()
            );
            entry.put(
                "logging.googleapis.com/spanId", context.getSpanId()
            );
            entry.put(
                "logging.googleapis.com/trace_sampled", context.isSampled()
            );
        }

        try {
            System.out.println(MAPPER.writeValueAsString(entry));
        } catch (JsonProcessingException error) {
            System.err.println(
                "{\"severity\":\"ERROR\",\"message\":\"log serialization failed\"}"
            );
        }
    }
}
~~~

Cách gọi trong code đã instrument:

~~~java
GcpJsonEvents events = new GcpJsonEvents("PROJECT_ID");

events.log(
    "WARNING",
    "order.payment.retry",
    "Payment timed out; retry scheduled",
    "/v1/orders",
    1200L
);
~~~

Mẫu có mục tiêu giáo dục về schema, không phải thay thế đầy đủ logging library trong production. Với ứng dụng có throughput lớn, dùng logger bất đồng bộ hoặc JSON encoder phù hợp để bảo đảm flush, backpressure, exception handling và metadata nhất quán. Đừng tạo `ObjectMapper` mới cho từng request.

Nếu `Span.current().getSpanContext().isValid()` là `false`, đoạn mã không tự bịa trace ID. Hãy kiểm tra agent, active context và thời điểm ghi log. Với Cloud Run, cũng cần xác nhận trace ID xuất ra khớp trace của request log nền tảng nếu muốn log được xếp dưới request.

### Dùng SLF4J MDC thủ công khi cần

`MDC` (Mapped Diagnostic Context) giữ các key/value liên quan đến luồng thực thi hiện hành để logging framework thêm vào mỗi log. Ví dụ:

~~~java
import org.slf4j.MDC;

public void processOrder(String routeTemplate) {
    try {
        MDC.put("route", routeTemplate);
        MDC.put("component", "order-service");
        // Logger/JSON encoder sẽ lấy MDC khi ghi log.
        logger.info("Processing order");
    } finally {
        MDC.remove("route");
        MDC.remove("component");
    }
}
~~~

Không gọi `MDC.clear()` một cách tùy tiện nếu có Java Agent hoặc filter khác đã đặt trace metadata, vì điều đó có thể xóa giá trị do thành phần khác quản lý. Hãy chỉ remove những key do chính code này thêm, hoặc dùng cơ chế scoped MDC phù hợp.

MDC thường dùng `ThreadLocal`, không tự di chuyển an toàn qua mọi executor, coroutine hoặc reactive pipeline. Với WebFlux/Reactor, dùng tích hợp context propagation được hỗ trợ thay vì giả định `MDC.put` trên request thread sẽ có mặt trong mọi callback.

## 8. Manual instrumentation và truyền context

### Thêm span nghiệp vụ

Khi Java Agent đã tạo span HTTP server, bạn có thể thêm span con cho một bước quan trọng:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class InventoryTrace {
    private static final Tracer TRACER =
        GlobalOpenTelemetry.getTracer("orders-api");

    public void reserveInventory(Runnable operation) {
        Span span = TRACER.spanBuilder("reserve-inventory").startSpan();
        try (Scope ignored = span.makeCurrent()) {
            operation.run();
            span.setAttribute("inventory.operation", "reserve");
        } catch (RuntimeException failure) {
            span.recordException(failure);
            span.setStatus(StatusCode.ERROR);
            throw failure;
        } finally {
            span.end();
        }
    }
}
~~~

`Scope` đưa span thành current trong khối `try`. Khi log được ghi bên trong scope, `Span.current()` có thể lấy đúng context. `span.end()` cần được gọi kể cả khi xảy ra lỗi.

Không gắn order ID, email hay token vào span attributes chỉ để tiện tìm kiếm. Nếu cần một định danh nghiệp vụ, đánh giá nhạy cảm, chính sách truy cập và cardinality trước khi thêm; nhiều tình huống chỉ cần `route`, `operation` hoặc `error.type`.

### Context propagation qua HTTP/gRPC

Khi ứng dụng dùng HTTP client hoặc gRPC được Java Agent hỗ trợ, instrumentation có thể tự inject trace context vào outbound request. Service đích dùng propagator để extract context và tạo span con có parent phù hợp.

Nếu gọi HTTP bằng thư viện tự viết hoặc qua một framework chưa được instrument, có thể cần inject/extract thủ công bằng OpenTelemetry propagators. Không tạo một trace ID mới cho mỗi hop; hãy truyền context hiện hành.

### Thread pool và tác vụ bất đồng bộ

Với một số executor được Java Agent instrument, context propagation diễn ra tự động. Nhưng nếu bạn giữ tác vụ để chạy sau, đưa vào một hàng đợi hoặc chuyển sang thread tự quản lý, cần kiểm tra propagation.

Mẫu thủ công có thể dùng `Context.current().wrap(runnable)`:

~~~java
import io.opentelemetry.context.Context;
import java.util.concurrent.ExecutorService;

public void submitWork(ExecutorService pool, Runnable task) {
    Runnable withContext = Context.current().wrap(task);
    pool.submit(withContext);
}
~~~

`Context.current()` cần được capture **tại thời điểm đang ở trong active span của caller**. Với công việc chạy rất lâu sau request, hãy cân nhắc tạo trace mới có link tới context trước đó, thay vì giữ nguyên một parent span đã kết thúc mà không rõ quan hệ nhân quả.

### Messaging qua Pub/Sub

Với Pub/Sub, thông tin trace context cần được truyền qua message attributes hoặc integration có hỗ trợ propagator. Consumer phải extract context rồi tạo span xử lý message. Không nên giả định việc Pub/Sub chứa cùng một message ID khiến trace tự liên kết.

Nếu có retries hoặc dead-letter delivery, cần phân biệt trace cho lần publish và các lần consume. Có thể dùng span links khi phù hợp để mô tả nhiều quan hệ nhân quả, thay vì ép mọi lần xử lý thành một chuỗi cha–con.

## 9. Đưa telemetry tới Google Cloud

Có hai mô hình phổ biến:

### Mô hình A: stdout logs + OTLP traces/metrics

~~~text
Java / Spring
  ├─ SLF4J + JSON encoder → stdout → Cloud Logging
  └─ OTel Java Agent/SDK → OTLP → Collector → Cloud Trace / Monitoring
~~~

Ưu điểm là phù hợp với Cloud Run và GKE vốn đã có log collection. Logs được ingest theo cơ chế native platform, trong khi traces/metrics linh hoạt qua Collector. Đây là mô hình chính của bài thực hành.

### Mô hình B: OTLP cả logs, traces và metrics

~~~text
Java OTel SDK / Agent
  └─ OTLP → Collector → Telemetry API / Cloud Logging / Cloud Trace / Monitoring
~~~

Phương án này cho phép xử lý tập trung bằng Collector nhưng cần đảm bảo pipeline logs được hỗ trợ và không đồng thời để stdout ingestion ghi lại cùng log record. Cách map OTLP log attributes sang `LogEntry` khác cách built-in agent parse JSON.

### Chọn Collector hay in-process exporter

Google Cloud khuyến nghị dùng Collector khi môi trường cho phép, vì instrumentation của app ít phụ thuộc backend và Collector có thể batch, retry, route và filter telemetry. Ở môi trường không phù hợp để chạy Collector, có thể dùng OTLP in-process exporter trực tiếp tới endpoint Telemetry API theo hướng dẫn hiện hành.

Trên Compute Engine, Ops Agent có thể nhận OTLP traces/metrics; lưu ý OTLP receiver của Ops Agent không dùng để nhận OTLP logs. Logs trên VM được thu qua logging receivers riêng.

### Bật API

Ví dụ bật các API cần thiết cho môi trường lab:

~~~bash
gcloud services enable \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com \
  --project=PROJECT_ID
~~~

### Quyền IAM theo đường ingest

| Thành phần | Quyền tham khảo | Lưu ý |
|---|---|---|
| Collector ghi metric | `roles/monitoring.metricWriter` | Trên project ingest metric |
| Collector/OTLP ghi trace qua Telemetry API | `roles/telemetry.tracesWriter` | Dùng khi xuất trace qua Telemetry API |
| Collector ghi log qua Logging API | `roles/logging.logWriter` | Khi dùng API trực tiếp; stdout Cloud Run có cơ chế thu riêng |
| Ingest trace qua Cloud Trace API cũ | `roles/cloudtrace.agent` | Tùy API/exporter thực tế, không thay thế `roles/telemetry.tracesWriter` cho Telemetry API |
| Người xem log | `roles/logging.viewer` | Có thể cần thêm quyền với restricted log views |
| Người xem trace | `roles/cloudtrace.user` | Đọc trace theo chính sách IAM |
| Người xem metric | `roles/monitoring.viewer` | Xem Metrics Explorer và dashboard |

Nếu dùng quota project riêng, danh tính ghi telemetry có thể cần `roles/serviceusage.serviceUsageConsumer` trên quota project. Nên dùng service account của Cloud Run/Collector hoặc Workload Identity Federation for GKE; không đưa service account key vào image, source code hay Dockerfile.

### Thiết kế đường mạng

- Với OTLP HTTP/protobuf, endpoint thường là `http://COLLECTOR_HOST:4318` trong mạng tin cậy.
- Với OTLP gRPC, cổng thường là `4317`.
- Collector phải có đường egress và xác thực tới endpoint Google Cloud theo cấu hình exporter.
- Nếu dùng VPC Service Controls, Cloud NAT, proxy, private egress hoặc sidecar, cần kiểm tra ingress/egress policy và service identity.
- Nếu Collector tắt hoặc backpressure, kiểm tra log exporter, queue và retry; telemetry có thể bị rơi hoặc đến muộn.

## 10. Thực hành: Java API trên Cloud Run

Bài lab triển khai ý tưởng trên một API Java/Spring Boot và project thử nghiệm riêng. Bạn có thể dùng chính API đang học hoặc mẫu Spring Boot chính thức của Google Cloud. Không yêu cầu thay đổi một hệ thống production.

### Bước 1: Chuẩn bị project và workload

1. Chọn project thử nghiệm, bảo đảm billing và các API cần thiết đã bật.
2. Có ứng dụng Spring Boot với endpoint `GET /hello` hoặc `POST /v1/orders`.
3. Xác định project ID và runtime service account.
4. Tạo cấu hình nhận OTLP: Collector trong môi trường lab hoặc endpoint được hỗ trợ.
5. Cấp IAM tối thiểu cho đường xuất trace/metric.
6. Cấu hình một JSON encoder hoặc mã minh họa `GcpJsonEvents`.

### Bước 2: Tạo log khi có request

Ví dụ controller:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    private static final Logger log =
        LoggerFactory.getLogger(HelloController.class);

    @GetMapping("/hello")
    public String hello() {
        log.info("hello endpoint invoked");
        return "hello";
    }
}
~~~

Để thấy log có cấu trúc, framework logging phải có JSON layout theo phần 7 hoặc dùng helper JSON. Chỉ viết `logger.info(...)` nhưng giữ console text layout mặc định sẽ tạo `textPayload`, không phải structured `jsonPayload`.

### Bước 3: Kích hoạt OTel Agent

Đóng gói một phiên bản Java Agent đã pin vào image. Khi chạy JVM, truyền `JAVA_TOOL_OPTIONS`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_EXPORTER_OTLP_ENDPOINT` và protocol tương ứng. Trên Cloud Run, chọn collector sidecar hoặc endpoint có thể truy cập; đừng copy hostname lab vào production.

### Bước 4: Gửi traffic

Ví dụ với service URL của môi trường test:

~~~bash
curl -i https://YOUR_CLOUD_RUN_URL/hello
~~~

Gửi nhiều lần để tạo request logs, container logs, spans và metrics. Có thể thêm một endpoint tạo lỗi mô phỏng trong staging, nhưng không đưa logic lỗi thử nghiệm vào production.

### Bước 5: Xác minh log JSON

Trong Logs Explorer:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
~~~

Mở một container log. Kiểm tra:

- Payload là `jsonPayload`, không chỉ `textPayload`.
- `severity` xuất hiện ở metadata chuẩn.
- `jsonPayload.event` hoặc `jsonPayload.service` có giá trị mong đợi.
- `trace` mang dạng `projects/PROJECT_ID/traces/TRACE_ID` khi có active span.
- `spanId` có giá trị khi đang ở trong span hợp lệ.
- Request logs và container logs có thể được nhóm dưới cùng trace nếu context khớp.

### Bước 6: Kiểm tra Cloud Trace

Mở Trace Explorer và tìm `orders-api`, thời gian gần nhất và endpoint `/hello`. Chọn một trace và xem:

1. Span HTTP server.
2. Các span outbound HTTP/JDBC nếu lab có dependency.
3. Duration, attributes và status.
4. Mối quan hệ parent–child.
5. Log liên quan nếu có cùng trace ID.

Với sampling, một số request có log nhưng không có trace được xuất. Đây không nhất thiết là lỗi; xem `trace_sampled`, sampler và exporter.

### Bước 7: Kiểm tra log–trace correlation

Sao chép trace resource name từ một log và lọc:

~~~text
trace="projects/PROJECT_ID/traces/TRACE_ID"
~~~

Sau đó mở trace trong Trace Explorer. Nếu có trace nhưng log không được nhóm dưới request log, so sánh trace IDs ở `LogEntry.trace`, header `X-Cloud-Trace-Context` và context từ Java Agent.

### Bước 8: Dọn dẹp

Xóa các resource lab khi không dùng nữa: Cloud Run service, Collector, test project hoặc log/metric/tracing configuration chỉ tạo cho bài thực hành. Kiểm tra lại billing và tránh để subscription hoặc exporter thử nghiệm tạo chi phí không mong muốn.

## 11. Truy vấn Logs Explorer phục vụ điều tra

Cloud Logging query language cho phép lọc theo cả metadata chuẩn và JSON fields.

### Lỗi trong một Cloud Run service

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
~~~

### Tìm event nghiệp vụ

~~~text
resource.type="cloud_run_revision"
jsonPayload.event="payment.timeout"
~~~

### Tìm request chậm

~~~text
resource.type="cloud_run_revision"
jsonPayload.duration_ms>1000
~~~

### Theo một trace

~~~text
trace="projects/PROJECT_ID/traces/TRACE_ID"
~~~

### Lọc theo service và phiên bản

~~~text
jsonPayload.service="orders-api"
jsonPayload.service_version="1.2.3"
~~~

Nếu field không nằm trong `jsonPayload`, hãy mở log entry ở chế độ JSON và kiểm tra vị trí thực tế. Ví dụ `severity` hoặc `trace` thường là field top-level, không nằm trong `jsonPayload` sau khi được parse thành metadata chuẩn.

Trong truy vấn, `trace` là giá trị đầy đủ có project prefix. Chỉ tìm trace ID trần có thể không khớp nếu không dùng cú pháp phù hợp.

## 12. Sampling, retention, chi phí và bảo mật

### Sampling traces và log filtering

Trace sampling giúp giảm lượng span và chi phí ingest/storage. Tuy nhiên:

- Log INFO/ERROR không nhất thiết bị sample cùng trace.
- Một trace ID hợp lệ trong log không bảo đảm trace đã được ingest.
- Sampling theo tỷ lệ có thể bỏ lỡ một số request hiếm nhưng quan trọng.
- Cần đánh giá tail sampling hoặc các chính sách ưu tiên lỗi nếu có kiến trúc Collector hỗ trợ, đồng thời kiểm tra khả năng triển khai và tài nguyên.

Đối với logs, đặt mức log hợp lý (`INFO`/ `WARN`/ `ERROR` ở production), tránh log DEBUG tràn lan. Dùng log exclusions hoặc filtering có kiểm soát; không loại bỏ mọi error log chỉ để giảm chi phí.

### Cardinality và dữ liệu nhạy cảm

Không đưa thông tin sau vào log labels, span attributes hoặc baggage nếu không có yêu cầu và biện pháp bảo vệ:

- Password, API key, bearer token, cookie, session ID.
- Thông tin thanh toán, tài liệu định danh hoặc dữ liệu sức khỏe.
- Full URL chứa token hoặc thông tin định danh trong query string.
- Request body/response body nguyên vẹn.
- Email, user ID, order ID trong các high-cardinality metric labels.

Có thể dùng mã lỗi, route template, loại nghiệp vụ hoặc nhóm khách hàng không nhạy cảm. Với exception, loại bỏ hoặc che giá trị secret khỏi message, stack trace và nested cause.

### Access, retention và audit

- Giới hạn quyền `roles/logging.viewer`, `roles/cloudtrace.user`, `roles/monitoring.viewer` theo vai trò.
- Áp dụng log bucket retention và region phù hợp với yêu cầu của tổ chức.
- Kiểm tra Logs Router, sink và đích xuất log để tránh phát tán dữ liệu ngoài phạm vi cho phép.
- Với log có nội dung nhạy cảm, dùng restricted log views và quyền phù hợp.
- Kiểm tra thời gian lưu trace và metric theo cấu hình, loại tín hiệu và chính sách hiện hành.
- Gắn owner cho pipeline telemetry; theo dõi chi phí ingest, số lượng span, log volume và lỗi exporter.

## 13. Sự cố cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Log xuất hiện dưới `textPayload` | Logger ghi text hoặc JSON bị chia nhiều dòng | Kiểm tra stdout thực tế và JSON encoder |
| `severity` vẫn là DEFAULT | Không có field `severity` chuẩn hoặc JSON parse sai | Kiểm tra key, kiểu dữ liệu, receiver |
| Không có `trace` trong log | Không có active span hoặc JSON layout bỏ trace field | Kiểm tra agent, MDC, `SpanContext.isValid()` |
| Log có trace nhưng không có span trong Trace Explorer | Span không sampled, không export hoặc ingest lỗi | Kiểm tra sampler, Collector, IAM và egress |
| Container logs không nhóm dưới request logs | Trace ID không khớp request log nền tảng | So sánh trace ID, header và propagator |
| Trace bị chia thành nhiều trace | Thiếu propagation qua HTTP/gRPC, queue hoặc async | Kiểm tra `traceparent`, extract/inject, context |
| Span con có parent sai | Tạo span ngoài active context hoặc mất `Scope` | Kiểm tra `makeCurrent`, executor và lifecycle |
| Trace thiếu HTTP client/JDBC spans | Agent không chạy hoặc phiên bản thư viện chưa được instrument | Kiểm tra startup logs, Java Agent compatibility |
| Trùng hai log entry | Cùng event xuất stdout và OTLP/Logging API | Chọn một đường ingest hoặc lọc trùng |
| Collector không gửi được trace | Endpoint/protocol sai, thiếu auth, thiếu IAM hoặc mạng chặn | Xem exporter logs, TLS, retry và quota |
| Chi phí Cloud Logging tăng mạnh | Log DEBUG/INFO quá nhiều, retry loop, event payload lớn | Đo log volume, lọc hợp lý và sửa nguồn |
| Field JSON bị trộn kiểu | Cùng key lúc ghi số, lúc ghi string | Chuẩn hóa schema, kiểm tra serializer |
| Traces thiếu route hoặc service name | Resource attributes thiếu hoặc instrumenter không đặt semantic fields | Kiểm tra `OTEL_SERVICE_NAME` và attributes |
| Async logs mất trace context | ThreadLocal/MDC không được propagate | Dùng OTel Context propagation cho executor/Reactor |

### Quy trình chẩn đoán ngắn

1. **Có log không?** Nếu không, kiểm tra stdout/file/receiver.
2. **Có JSON đúng không?** Nếu không, kiểm tra layout và formatter.
3. **Có trace context không?** Nếu không, kiểm tra Agent, Scope và MDC.
4. **Có span trong Cloud Trace không?** Nếu không, kiểm tra sampling/export/Collector.
5. **Có liên kết đúng cùng request không?** Nếu không, so sánh trace ID giữa các hệ thống.
6. **Có đủ dữ liệu điều tra không?** Nếu không, bổ sung field có ý nghĩa nhưng không chứa secret.

## 14. Thực hành tốt cho đội Java/Spring

- Dùng **schema log thống nhất**: `event`, `service`, `environment`, `route`, `duration_ms`, `error_type`.
- Dùng **JSON một dòng** trên Cloud Run/GKE để Cloud Logging parse dễ dàng.
- Ghi `logging.googleapis.com/trace` dưới dạng full resource name; `spanId` 16 ký tự hex; `trace_sampled` là boolean.
- Dùng Java Agent để có span HTTP/JDBC cơ bản, sau đó thêm manual span có giá trị nghiệp vụ.
- Đồng bộ `service.name`, service version và environment trên logs, metrics và traces.
- Kiểm chứng propagation qua cả HTTP, gRPC, Pub/Sub và asynchronous code.
- Không xem trace ID trong log là bằng chứng trace đã được ingest.
- Tránh vừa export log bằng OTLP vừa thu lại cùng log từ stdout.
- Dùng service account/Workload Identity thay cho long-lived key.
- Không log secrets, token, body nhạy cảm hoặc raw URL không được kiểm soát.
- Thiết lập sampling, retention và log filtering theo nhu cầu điều tra lẫn ngân sách.
- Tạo dashboard/alert liên kết Logs Explorer và Trace Explorer, có owner và runbook.

## Câu hỏi ôn tập

1. `jsonPayload` khác `textPayload` như thế nào và ưu điểm khi lọc theo `event` là gì?
2. Vì sao `logging.googleapis.com/trace` cần chứa project prefix thay vì chỉ có trace ID?
3. Một log có trace ID nhưng Trace Explorer không hiển thị trace: có ít nhất ba nguyên nhân gì?
4. `traceparent` có nhiệm vụ gì trong một request qua nhiều service?
5. Điều gì xảy ra khi MDC không được truyền qua thread pool hoặc Reactor pipeline?
6. Vì sao không nên đồng thời gửi cùng một log qua stdout và OTLP log exporter?
7. Khi nào dùng Java Agent tự động và khi nào cần manual span?
8. Trên Cloud Run, làm thế nào để kiểm tra container log thuộc đúng request log?

## Kết luận

**Structured logging** giúp Java/Spring ứng dụng xuất log thành dữ liệu JSON có thể truy vấn. **Trace context** giữ mối liên hệ giữa các hoạt động của một request và cho phép nối log với span. **OpenTelemetry** cung cấp instrumentation và giao thức chuẩn, giúp thu thập traces và metrics, đồng thời có thể hỗ trợ log correlation qua MDC.

Trên Google Cloud, một kiến trúc thực tế là dùng JSON logs trên stdout của Cloud Run/GKE và dùng OpenTelemetry Java Agent/Collector cho traces và metrics. Khi trường trace có đúng resource name, trace ID được propagate xuyên service và spans được export thành công, đội vận hành có thể đi từ log lỗi sang Cloud Trace, tìm ra dependency hoặc bước nghiệp vụ gây chậm, rồi dùng metrics để đánh giá mức độ ảnh hưởng. Thiết kế này chỉ đáng tin cậy khi dữ liệu được bảo vệ, sampling được hiểu rõ và pipeline được kiểm tra từ đầu tới cuối.

## Tài liệu tham khảo

- [Cloud Logging: Structured logging](https://cloud.google.com/logging/docs/structured-logging)
- [Cloud Run: Logging and viewing logs](https://cloud.google.com/run/docs/logging)
- [Cloud Trace: Java instrumentation sample](https://cloud.google.com/trace/docs/setup/java-ot)
- [Google Cloud: Choose an instrumentation approach](https://cloud.google.com/stackdriver/docs/instrumentation/choose-instrumentation)
- [Cloud Trace: Instrument for Cloud Trace](https://cloud.google.com/trace/docs/setup)
- [Cloud Logging: LogEntry fields](https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry)
- [OpenTelemetry: Java zero-code instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/)
- [OpenTelemetry: Java manual instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/)
- [OpenTelemetry: Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [Google Cloud: Collect OTLP metrics and traces with Ops Agent](https://cloud.google.com/stackdriver/docs/solutions/agents/ops-agent/otlp)
- [Cloud Logging: Query and view logs](https://cloud.google.com/logging/docs/view/logging-query-language)

