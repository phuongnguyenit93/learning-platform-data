# Theo dõi bằng Cloud Logging, Cloud Monitoring và Cloud Trace

Một ứng dụng serverless có thể tạo nhiều instance trong thời gian ngắn, xử lý request đồng thời và gọi qua nhiều dịch vụ cloud. Khi một request chậm hoặc thất bại, việc chỉ đọc log của một container thường không đủ để biết lỗi bắt đầu ở đâu. Đội phát triển cần kết hợp ba tín hiệu quan sát: **logs** cho biết điều gì đã xảy ra, **metrics** cho biết hệ thống đang hoạt động ra sao theo thời gian, và **traces** cho biết một request đi qua những thành phần nào cùng thời gian ở mỗi bước.

Trên Google Cloud, Cloud Logging thu thập log của nền tảng và ứng dụng; Cloud Monitoring tổng hợp metric, dashboard, alert và SLO; Cloud Trace lưu vết phân tán giữa các service. Với Java chạy trên Cloud Run hoặc các môi trường serverless khác, cần chuẩn hóa log có cấu trúc, truyền trace context qua ranh giới HTTP/message, phát metric có nhãn giới hạn và thiết lập cảnh báo gắn với mục tiêu dịch vụ.

Bài học này trình bày cách kết hợp ba dịch vụ để theo dõi ứng dụng Java serverless, từ cấu trúc log, instrumentation OpenTelemetry đến dashboard, alert, truy vấn điều tra và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt logs, metrics và traces, cũng như câu hỏi mỗi tín hiệu trả lời.
- Đọc request log do Cloud Run tạo và container log do ứng dụng ghi.
- Phát structured log JSON để Cloud Logging phân tích được các trường.
- Liên kết log với trace bằng trace ID và span ID.
- Dùng OpenTelemetry để tạo trace và truyền context qua HTTP hoặc message.
- Tạo metric ứng dụng bằng Micrometer hoặc OpenTelemetry.
- Thiết kế dashboard, alert policy và SLI/SLO trong Cloud Monitoring.
- Viết truy vấn Cloud Logging để điều tra lỗi theo service, revision, request và trace.
- Giới hạn dữ liệu nhạy cảm, cardinality và chi phí observability.

## 1. Ba tín hiệu observability

Ba tín hiệu thường được dùng cùng nhau nhưng phục vụ các góc nhìn khác nhau.

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Logs** | Điều gì đã xảy ra tại một thời điểm? | Request bị từ chối vì thiếu quyền; database trả timeout |
| **Metrics** | Sự việc xảy ra thường xuyên đến mức nào và xu hướng ra sao? | Tỷ lệ 5xx tăng từ 0,2% lên 4%; p95 latency vượt 1 giây |
| **Traces** | Một request đi qua những bước nào và thời gian bị tiêu tốn ở đâu? | API mất 800 ms, trong đó 650 ms chờ database |

Có thể hình dung:

~~~mermaid
flowchart LR
    A["Java service / Cloud Run"] --> B["Logs"]
    A --> C["Metrics"]
    A --> D["Traces"]
    B --> E["Cloud Logging"]
    C --> F["Cloud Monitoring"]
    D --> G["Cloud Trace"]
    E --> H["Điều tra một request"]
    F --> H
    G --> H
~~~

Ví dụ, dashboard cho thấy p95 latency tăng. Metrics xác nhận đây là vấn đề trên toàn service hay chỉ một revision. Trace giúp tìm span chậm, chẳng hạn một truy vấn database. Log có trace ID cho biết request cụ thể nào gặp lỗi và thông tin nghiệp vụ liên quan.

Không có một tín hiệu nào thay thế được hai tín hiệu còn lại. Log chi tiết không phù hợp để tính xu hướng tải lớn; metric tổng hợp không giữ đủ bối cảnh của một request; trace không phải kho lưu toàn bộ sự kiện nghiệp vụ.

## 2. Cloud Run tạo những loại log nào?

Khi triển khai service lên Cloud Run, Cloud Logging có thể nhận log từ cả nền tảng và container.

### Request logs

Cloud Run tạo request log cho các request đến service. Log thường chứa các thông tin như:

- HTTP method, URL và status code.
- Latency của request.
- Kích thước response.
- User agent và thông tin mạng phù hợp với cấu hình.
- Service, revision, location và các resource labels liên quan.

Request log giúp trả lời câu hỏi endpoint nào đang lỗi hoặc chậm, kể cả khi ứng dụng chưa ghi log trước khi thất bại.

### Container logs

Ứng dụng ghi ra stdout hoặc stderr; Cloud Run thu thập chúng thành container logs. Với Java, logger thường được cấu hình ghi ra console. Nếu log là một dòng JSON hợp lệ, Cloud Logging có thể phân tích các trường thành `jsonPayload`.

Nên ghi log theo cấu trúc thay vì ghép chuỗi tự do:

~~~json
{
  "severity": "INFO",
  "message": "Order accepted",
  "event": "order.accepted",
  "orderId": "ORD-1042",
  "tenant": "tenant-42",
  "revision": "orders-api-00012-abc",
  "durationMs": 34
}
~~~

Các trường nghiệp vụ có thể lọc và nhóm dễ dàng. Tránh ghi toàn bộ request body, token, password, secret, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết.

### Structured logging và special fields

Cloud Logging nhận diện một số trường đặc biệt trong JSON payload. Các trường thường dùng:

| Trường JSON | Ý nghĩa |
|---|---|
| `severity` | Mức log như DEBUG, INFO, WARNING, ERROR |
| `message` | Nội dung log dễ đọc |
| `logging.googleapis.com/trace` | Đường dẫn trace để liên kết log với Cloud Trace |
| `logging.googleapis.com/spanId` | Span ID liên quan đến log |
| `logging.googleapis.com/trace_sampled` | Cho biết trace có được sample hay không |
| `httpRequest` | Thông tin HTTP nếu ứng dụng tự ghi log request có cấu trúc |

Khi trường trace được nhận diện, Cloud Logging hiển thị liên kết để mở trace tương ứng trong Cloud Trace. Trace path có dạng:

~~~text
projects/PROJECT_ID/traces/TRACE_ID
~~~

Nếu log chỉ chứa một chuỗi message không có cấu trúc, việc lọc theo orderId, event type hoặc trace ID sẽ khó hơn. Hãy thống nhất schema log giữa các service và giữ tên field ổn định.

## 3. Structured logging trong ứng dụng Java

Với Java, có thể dùng SLF4J cùng backend Logback và JSON encoder để ghi log một dòng JSON ra stdout. Một encoder như Logstash Logback Encoder có thể serialize message, level và MDC fields thành JSON.

Ví dụ cấu hình Logback tối giản:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ứng dụng có thể ghi log như sau:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void accept(String orderId) {
        log.atInfo()
                .addKeyValue("event", "order.accepted")
                .addKeyValue("orderId", orderId)
                .log("Order accepted");
    }
}
~~~

Để các key-value được xuất thành JSON fields, cần dùng phiên bản SLF4J và encoder hỗ trợ structured arguments/key-value pairs, đồng thời xác minh output thực tế. Nếu backend chỉ xuất message dạng text, Cloud Logging không thể tự suy ra các trường đó.

### Gắn trace context vào log

Khi dùng OpenTelemetry, có thể lấy trace context hiện tại để gắn trace ID và span ID vào MDC. Logback JSON encoder sẽ xuất MDC thành các trường JSON; Cloud Logging nhận diện các tên trường đặc biệt đã nêu.

Ví dụ minh họa:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import org.slf4j.MDC;

import java.util.Map;

public final class TraceLogContext {
    private TraceLogContext() {
    }

    public static void runWithTraceFields(
            String projectId, Runnable action) {

        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            SpanContext span = Span.current().getSpanContext();

            if (span.isValid()) {
                MDC.put(
                        "logging.googleapis.com/trace",
                        "projects/" + projectId + "/traces/"
                                + span.getTraceId());
                MDC.put(
                        "logging.googleapis.com/spanId",
                        span.getSpanId());
            }

            action.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }
}
~~~

Dùng wrapper này quanh đoạn xử lý cần log hoặc tích hợp tương đương vào servlet filter/interceptor. Phải khôi phục MDC trong `finally` vì thread xử lý request có thể được tái sử dụng cho request khác. Nếu ứng dụng xử lý bất đồng bộ hoặc chuyển sang executor, MDC không tự động truyền sang thread mới; cần context propagation phù hợp.

Nếu muốn ghi thêm `logging.googleapis.com/trace_sampled`, hãy cấu hình encoder để xuất trường này thành JSON boolean; MDC thông thường biểu diễn giá trị dưới dạng chuỗi.

Tên project ID phải lấy từ cấu hình môi trường đã kiểm soát. Không ghi access token hoặc toàn bộ span attributes vào log.

## 4. Truy vấn Cloud Logging

Cloud Logging Logs Explorer hỗ trợ truy vấn theo resource type, labels, severity và payload fields.

### Tìm lỗi của một Cloud Run service

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
~~~

Truy vấn này giới hạn log theo service và mức độ ERROR trở lên.

### Tìm request HTTP 5xx

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
httpRequest.status>=500
~~~

Request log có trường HTTP giúp tìm status code, latency và endpoint liên quan.

### Tìm một đơn hàng trong structured logs

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
jsonPayload.orderId="ORD-1042"
~~~

### Tìm log của một trace

~~~text
trace="projects/PROJECT_ID/traces/TRACE_ID"
~~~

Thay PROJECT_ID và TRACE_ID bằng giá trị thực. Nếu ứng dụng không ghi trace field hoặc context không được truyền đến log, truy vấn này sẽ không tìm được container log tương ứng dù request log vẫn tồn tại.

### Lọc theo revision

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
resource.labels.revision_name="orders-api-00012-abc"
severity>=WARNING
~~~

Revision label hữu ích khi canary hoặc rollback: so sánh lỗi của revision mới với revision đang ổn định.

### Mẹo điều tra

- Bắt đầu từ service và khoảng thời gian có vấn đề.
- Lọc request 5xx hoặc severity ERROR.
- Mở một log entry và lấy trace ID/correlation ID.
- Mở trace để xem các span và dependency.
- Quay lại log theo trace ID để đọc lỗi cụ thể.
- So sánh revision và thời điểm triển khai để tìm tương quan.

Không nên truy vấn bằng một ID có cardinality cao trên toàn bộ thời gian lưu log nếu chưa giới hạn resource và time range. Bộ lọc hẹp giúp điều tra nhanh hơn và giảm lượng dữ liệu phải đọc.

## 5. Cloud Monitoring: metrics, dashboard và alert

Cloud Monitoring nhận metric từ dịch vụ Google Cloud và từ instrumentation của ứng dụng. Metric được lưu dưới dạng time series có metric type, resource type, labels và điểm dữ liệu theo thời gian.

Một time series thường được xác định bởi metric cùng monitored resource và tập labels. Labels giúp phân tích theo service, revision, region hoặc kết quả, nhưng mỗi tổ hợp label có thể tạo một time series riêng. Vì vậy, không đưa orderId, userId, email hoặc requestId vào metric labels.

### Các metric quan trọng của Cloud Run

Cloud Run cung cấp metric nền tảng để theo dõi request và container. Tên metric cụ thể có thể thay đổi theo loại service và phiên bản tài liệu; tra Metric Explorer hoặc metric catalog trong project trước khi tạo policy.

| Nhóm | Theo dõi điều gì? | Cách dùng |
|---|---|---|
| Request count | Số request theo service/revision/status | Phát hiện tải tăng hoặc request giảm bất thường |
| Request latency | Phân bố độ trễ request | Theo dõi p50/p95/p99 và SLO |
| Instance count | Số instance đang chạy | Xem autoscaling và giới hạn capacity |
| CPU utilization | Mức sử dụng CPU | Tìm instance bị nghẽn CPU |
| Memory utilization | Mức sử dụng bộ nhớ | Phát hiện memory pressure hoặc rủi ro OOM |
| Startup latency | Thời gian instance khởi động | Đánh giá cold start và hiệu quả tối ưu |
| Container/request errors | Lỗi container và lỗi phục vụ | Phát hiện revision hoặc dependency bất ổn |

Nên phân tích metric theo service, region và revision. Nếu một revision có latency cao hơn rõ rệt sau deployment, có thể khoanh vùng regression mà không bị số liệu của các revision khác che khuất.

### Metric nghiệp vụ của ứng dụng

Metric nền tảng cho biết service hoạt động ra sao; metric nghiệp vụ cho biết ứng dụng đang hoàn thành công việc hay không.

Ví dụ:

- Số đơn hàng được chấp nhận hoặc từ chối.
- Tỷ lệ thanh toán thành công.
- Thời gian xử lý đơn hàng.
- Số message retry hoặc đưa vào dead-letter queue.
- Số lần gọi dependency thất bại.

Có thể dùng Micrometer trong Spring Boot:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrderMetrics {
    private final Counter accepted;
    private final Counter rejected;
    private final Timer processingTime;

    public OrderMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("orders.accepted")
                .description("Accepted order requests")
                .register(registry);

        this.rejected = Counter.builder("orders.rejected")
                .description("Rejected order requests")
                .register(registry);

        this.processingTime = Timer.builder("orders.processing")
                .description("Order processing duration")
                .register(registry);
    }

    public void markAccepted() {
        accepted.increment();
    }

    public void markRejected() {
        rejected.increment();
    }

    public void recordProcessing(Runnable operation) {
        processingTime.record(operation);
    }
}
~~~

Đoạn code minh họa instrumentation; cần cấu hình registry/exporter phù hợp để metric được gửi đến backend quan sát, ví dụ Google Cloud Monitoring qua exporter được hỗ trợ hoặc qua OpenTelemetry Collector. Chỉ thêm MeterRegistry trong ứng dụng chưa có nghĩa metric đã xuất hiện trong Cloud Monitoring.

### Cardinality và metric labels

Metric nên có labels với tập giá trị nhỏ, ổn định:

| Label tốt | Vì sao |
|---|---|
| `operation=read_order/write_order` | Tập thao tác hữu hạn |
| `outcome=success/failure` | Có số lượng trạng thái giới hạn |
| `dependency=database/payment` | Danh mục dependency nhỏ |
| `revision=stable/canary` hoặc revision label do nền tảng cung cấp | Phục vụ so sánh release |

Không dùng orderId, email, userId, requestId hoặc raw URL có path parameter làm metric labels. Ví dụ mỗi orderId tạo một time series mới sẽ làm cardinality và chi phí tăng nhanh. Các giá trị đó phù hợp hơn trong log hoặc trace attributes có kiểm soát.

## 6. Dashboard cho service serverless

Một dashboard hữu ích nên giúp người trực vận hành trả lời nhanh bốn câu hỏi: service có khỏe không, người dùng có bị ảnh hưởng không, instance có đủ năng lực không, và dependency nào đang gây chậm.

Gợi ý bố cục:

| Khu vực dashboard | Widget | Mục đích |
|---|---|---|
| Traffic | Request count theo thời gian | Nhận biết burst, traffic giảm hoặc mất request |
| Reliability | 4xx, 5xx và tỷ lệ lỗi | Theo dõi lỗi theo revision |
| Latency | p50/p95/p99 request latency | Phát hiện suy giảm trải nghiệm |
| Capacity | Instance count, concurrency, CPU, memory | Biết service có đang chạm giới hạn |
| Startup | Startup latency và số instance mới | Theo dõi cold start |
| Dependencies | Database/API latency và error rate | Tách lỗi ứng dụng khỏi lỗi phụ thuộc |
| Business | Order accepted, payment success, queue age | Xác nhận hệ thống hoàn thành nghiệp vụ |
| Release | So sánh stable/canary revision | Phát hiện regression sau deploy |

Đặt bộ lọc theo project, region, service và revision để dashboard có thể tái sử dụng giữa staging và production. Với nhiều service, có thể tạo dashboard tổng quan và dashboard chi tiết cho từng workload quan trọng.

## 7. Alerting và SLO

Alert tốt phải gắn với ảnh hưởng thực tế. Một cảnh báo chỉ vì CPU tăng có thể tạo nhiều false positive nếu request vẫn nhanh và không có lỗi. Ngược lại, tỷ lệ lỗi tăng hoặc p95 latency vượt mục tiêu có thể ảnh hưởng trực tiếp đến người dùng.

### Các loại alert thường cần

- Tỷ lệ HTTP 5xx vượt ngưỡng trong một cửa sổ thời gian.
- p95 hoặc p99 latency vượt mục tiêu liên tục.
- Instance count chạm max instances trong khi request latency hoặc error rate tăng.
- CPU hoặc memory duy trì ở mức cao.
- Startup probe thất bại hoặc container restart tăng.
- Queue age hoặc số message retry tăng nếu service xử lý event.
- Metric nghiệp vụ như payment success giảm bất thường.
- Không có dữ liệu metric khi service đáng lẽ phải có traffic.

Alert cần có duration window, threshold, alignment/reducer và notification channel phù hợp. Tránh gửi thông báo cho một spike ngắn không gây tác động. Với cảnh báo nghiêm trọng, ghi rõ service/revision, query hoặc dashboard liên quan và bước xử lý đầu tiên.

### SLI và SLO

**SLI (Service Level Indicator)** là phép đo chất lượng dịch vụ, ví dụ tỷ lệ request thành công hoặc tỷ lệ request hoàn tất dưới một ngưỡng latency.

**SLO (Service Level Objective)** là mục tiêu nội bộ cho SLI trong một khoảng thời gian, ví dụ 99,9% request hợp lệ hoàn tất thành công trong 30 ngày. Đây là ví dụ mục tiêu minh họa, không phải cam kết mặc định của Cloud Run.

Ví dụ:

- Availability SLI = số request tốt / tổng request đủ điều kiện.
- Latency SLI = số request có latency dưới ngưỡng / tổng request đủ điều kiện.
- Error budget = phần ngân sách lỗi còn lại trong cửa sổ SLO.

Có thể dùng Cloud Monitoring Service Monitoring để định nghĩa service, SLI, SLO và theo dõi error budget. Khi error budget tiêu hao nhanh, đội phát triển có thể giảm tốc độ phát hành tính năng và ưu tiên độ tin cậy.

Định nghĩa rõ request nào được tính vào mẫu số. Không loại mọi lỗi server khỏi SLI chỉ để làm tỷ lệ đẹp hơn; chỉ loại các trường hợp đã được quy định trước và có lý do nghiệp vụ.

## 8. Cloud Trace và distributed tracing

Một request thường đi qua API Gateway/load balancer, Cloud Run service, database, cache và service khác. Distributed trace biểu diễn hành trình đó bằng các **span** có quan hệ cha-con.

- **Trace:** toàn bộ hành trình của một request hoặc một đơn vị công việc phân tán.
- **Span:** một thao tác có thời gian bắt đầu/kết thúc, tên và attributes.
- **Parent/child:** quan hệ giữa span gọi và span được gọi.
- **Trace context:** metadata giúp service sau tiếp tục đúng trace.

Ví dụ một request:

~~~mermaid
flowchart TD
    A["HTTP server span"] --> B["Validate order span"]
    B --> C["Database query span"]
    B --> D["Payment API client span"]
    D --> E["Payment service span"]
    A --> F["HTTP response"]
~~~

Trace giúp tìm xem thời gian bị tiêu tốn trong Java code, truy vấn database hay lời gọi API ngoài. Nó cũng cho thấy lỗi ở service nào và request có bị retry qua nhiều bước không.

### Instrumentation bằng OpenTelemetry

OpenTelemetry cung cấp API và SDK để tạo trace, metric và context propagation theo chuẩn. Java có thể dùng Java agent để tự động instrument một số framework HTTP, client và thư viện được hỗ trợ; có thể thêm manual span cho bước nghiệp vụ quan trọng.

Khởi chạy ứng dụng với Java agent có dạng:

~~~bash
java -javaagent:/otel/opentelemetry-javaagent.jar -jar app.jar
~~~

Agent cần được đóng gói vào image và cấu hình exporter, resource attributes, endpoint cùng sampling phù hợp. Có thể xuất telemetry đến Google Cloud bằng exporter tương thích hoặc OpenTelemetry Collector được cấu hình để gửi đến Cloud Trace/Cloud Monitoring. Chọn một pipeline rõ ràng và tránh instrument trùng lặp cùng một thư viện.

### Tạo span thủ công trong Java

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class OrderValidator {
    private static final Tracer TRACER =
            GlobalOpenTelemetry.getTracer("orders-api");

    public void validate(String orderType) {
        Span span = TRACER.spanBuilder("order.validate").startSpan();

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("order.type", orderType);
            // Thực hiện validation nghiệp vụ.
            validateRules(orderType);
        } catch (RuntimeException error) {
            span.recordException(error);
            span.setStatus(StatusCode.ERROR, "Order validation failed");
            throw error;
        } finally {
            span.end();
        }
    }

    private void validateRules(String orderType) {
        if (orderType == null || orderType.isBlank()) {
            throw new IllegalArgumentException("orderType is required");
        }
    }
}
~~~

Đoạn code sử dụng OpenTelemetry API; ứng dụng cần cấu hình SDK hoặc agent để có tracer provider và exporter hoạt động. Nếu chỉ dùng API mà chưa cấu hình SDK/exporter, span có thể không được gửi đến Cloud Trace.

Chỉ thêm attributes có ích cho điều tra. Không đưa password, token, dữ liệu cá nhân hoặc payload lớn vào span. Với ID có cardinality cao như orderId, cân nhắc yêu cầu bảo mật, retention và chi phí trước khi thêm.

## 9. Truyền trace context qua HTTP và message

Trace chỉ liên kết được các service nếu context được truyền qua ranh giới gọi.

### HTTP

W3C Trace Context dùng header `traceparent` và tùy chọn `tracestate`. Một số thành phần Google Cloud cũng dùng header tương thích `X-Cloud-Trace-Context`. OpenTelemetry instrumentation cho HTTP server/client có thể trích xuất và inject context tự động khi thư viện được hỗ trợ và cấu hình đúng.

Khi service A gọi service B:

1. A có active span cho request hiện tại.
2. HTTP instrumentation inject trace context vào outbound request.
3. B trích xuất context từ request header.
4. B tạo server span là child của trace hiện tại.
5. Log trong B ghi cùng trace ID, giúp điều tra xuyên service.

Không tự tạo trace ID mới cho mỗi service nếu mục tiêu là một distributed trace. Nếu có gateway hoặc proxy xóa header, trace có thể bị đứt thành nhiều trace độc lập.

### Queue và event

Với Pub/Sub hoặc queue, message có thể được xử lý sau một khoảng thời gian hoặc bởi một instance khác. HTTP instrumentation không tự động truyền context qua message broker trong mọi trường hợp.

Khi publish event, có thể đưa trace context vào message attributes theo quy ước đã thống nhất, ví dụ:

~~~text
traceparent: 00-<trace-id>-<span-id>-01
eventId: evt-8f31
correlationId: corr-71a9
~~~

Consumer đọc attributes, trích xuất context rồi tạo consumer span. Nếu event được xử lý theo batch, có thể có nhiều trace context trong cùng batch; cần tạo span phù hợp cho từng message hoặc dùng span liên kết (links) theo mô hình xử lý, thay vì ép mọi message vào một trace cha duy nhất.

Giữ eventId và correlationId riêng với trace ID. Trace có thể được sample hoặc hết thời hạn lưu; eventId vẫn là định danh nghiệp vụ để deduplicate và replay.

## 10. Sampling và giới hạn dữ liệu trace

Không nhất thiết phải lưu mọi trace. Sampling quyết định trace nào được ghi và xuất, dựa trên cấu hình của SDK/agent hoặc backend.

- Sampling thấp giảm chi phí và lượng dữ liệu.
- Sampling cao tăng khả năng quan sát nhưng có thể tăng ingest/storage cost.
- Sampling theo xác suất có thể bỏ qua một request lỗi hiếm.
- Tail-based sampling có thể giữ lại trace có lỗi hoặc latency cao nếu kiến trúc collector hỗ trợ.

Nếu trace không xuất hiện trong Cloud Trace, điều đó không chứng minh request không xảy ra. Có thể trace chưa được sample, context không được truyền hoặc exporter gặp lỗi. Dùng request logs và metrics để đối chiếu.

Tránh ghi payload đầy đủ hoặc thông tin nhạy cảm vào span. Chỉ thêm attributes giúp phân tích: operation, dependency, result category, revision hoặc loại event. Dữ liệu nhận dạng cá nhân cần được loại bỏ hoặc bảo vệ theo chính sách.

## 11. Kết hợp logs, metrics và traces khi điều tra

Một quy trình điều tra có thể đi từ triệu chứng tổng quát đến request cụ thể:

1. **Nhìn metric:** xác định thời điểm latency hoặc error rate bắt đầu tăng.
2. **Khoanh revision:** xem vấn đề xuất hiện ở revision mới hay mọi revision.
3. **Tìm request log:** lọc request 5xx hoặc latency cao trong Cloud Logging.
4. **Mở trace:** theo trace ID để tìm span chậm hoặc thất bại.
5. **Đọc container log:** lọc cùng trace ID hoặc correlation ID để xem exception và bối cảnh.
6. **Kiểm tra dependency:** so sánh database/API latency và lỗi ở cùng khoảng thời gian.
7. **Xác minh nghiệp vụ:** kiểm tra event/order có được commit, retry hoặc đưa vào DLQ không.

Ví dụ: p95 latency tăng sau khi triển khai revision mới. Dashboard cho thấy revision mới có request latency cao và CPU thấp. Trace cho thấy span gọi database chiếm phần lớn thời gian. Container log cùng trace ID ghi connection acquisition timeout. Điều tra tiếp có thể phát hiện connection pool quá nhỏ hoặc database đã chạm giới hạn kết nối.

Nếu chỉ nhìn CPU, đội có thể tăng CPU vô ích. Nếu chỉ nhìn log, có thể khó biết vấn đề ảnh hưởng bao nhiêu phần trăm request. Kết hợp ba tín hiệu giúp xác định phạm vi và nguyên nhân nhanh hơn.

## 12. Alert thực tế cho Java serverless

Một bộ cảnh báo ban đầu có thể gồm:

| Alert | Điều kiện gợi ý | Hành động đầu tiên |
|---|---|---|
| Error rate cao | Tỷ lệ 5xx vượt SLO trong vài phút | So sánh revision, xem trace lỗi và log exception |
| Latency cao | p95 vượt ngưỡng liên tục | Tìm span chậm và dependency latency |
| Instance chạm giới hạn | Instance count gần max trong khi latency tăng | Kiểm tra concurrency, quota và backend capacity |
| Memory pressure | Memory cao kéo dài hoặc restart tăng | Xem heap, thread, leak và payload size |
| Startup failure | Startup probe thất bại hoặc startup latency tăng | Kiểm tra image, startup logs và dependency initialization |
| Message backlog | Queue age/depth tăng | Kiểm tra consumer errors, retry, concurrency và DLQ |
| Business failure | Payment success hoặc order completion giảm | Kiểm tra lỗi nghiệp vụ và dependency thanh toán |

Ngưỡng cụ thể cần dựa trên baseline và SLO của service. Không copy một con số chung cho mọi service vì tải, SLA và chi phí khác nhau.

Mỗi alert nên có owner, severity, notification channel, dashboard và runbook. Nếu cảnh báo không yêu cầu hành động, cân nhắc chuyển thành dashboard hoặc thông báo mức thấp để giảm alert fatigue.

## 13. Quyền truy cập cho observability

Cloud Run tự thu thập stdout/stderr và request logs vào Cloud Logging theo tích hợp nền tảng. Nếu ứng dụng gửi log trực tiếp qua Logging API, runtime service account cần quyền ghi log phù hợp, thường là `roles/logging.logWriter`.

Tương tự:

- Export custom metrics trực tiếp đến Cloud Monitoring cần quyền ghi metric phù hợp, thường là `roles/monitoring.metricWriter`.
- Gửi trace trực tiếp qua Cloud Trace API cần quyền ghi trace phù hợp, thường dùng `roles/cloudtrace.agent`.
- Nếu telemetry đi qua OpenTelemetry Collector hoặc một pipeline trung gian, quyền được cấp cho identity thực sự gửi dữ liệu.

Chỉ cấp quyền cần thiết cho runtime service account hoặc collector identity. Không cấp Editor/Owner chỉ để telemetry xuất hiện. Kiểm tra cả IAM policy, service account đang gắn với revision và cấu hình exporter khi dữ liệu không được gửi.

## 14. Kiểm soát chi phí và retention

Observability có giá trị nhưng cũng tạo chi phí ingest, lưu trữ, truy vấn và export.

### Cloud Logging

- Ghi log có cấu trúc và chỉ giữ trường cần điều tra.
- Tránh log từng bước quá chi tiết cho mọi request ở production.
- Dùng log exclusion cho dữ liệu nhiễu nếu vẫn giữ đủ tín hiệu vận hành.
- Chọn log bucket, retention và region theo yêu cầu lưu trữ.
- Dùng sink để export log sang BigQuery hoặc hệ thống khác khi có nhu cầu phân tích dài hạn.

### Cloud Monitoring

- Giữ metric labels có cardinality thấp.
- Không tạo time series theo từng user, order hoặc request.
- Dùng dashboard tổng hợp thay vì tạo metric riêng cho mọi đối tượng nghiệp vụ.
- Rà soát metric tùy chỉnh không còn được dùng.

### Cloud Trace

- Chọn sampling phù hợp với traffic và yêu cầu điều tra.
- Chỉ tạo span cho ranh giới có ý nghĩa, tránh span quá nhỏ cho mọi dòng code.
- Không gắn payload lớn hoặc dữ liệu nhạy cảm.
- Giữ attributes ổn định và hữu ích.

Đừng giảm sampling hoặc loại log chỉ để giảm chi phí khi đang có sự cố. Hãy xác định dữ liệu nào thực sự cần, thời hạn lưu và ai sử dụng chúng trước khi thay đổi retention hoặc exclusion.

## 15. Checklist observability cho Java serverless

- [ ] Cloud Run request logs và container logs xuất hiện trong đúng project.
- [ ] Ứng dụng ghi structured JSON với severity, message và field nghiệp vụ hữu ích.
- [ ] Log không chứa token, secret, password hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Log có trace ID/span ID khi active trace context tồn tại.
- [ ] HTTP instrumentation truyền trace context giữa các service.
- [ ] Message attributes giữ trace context, eventId và correlationId qua queue/event.
- [ ] OpenTelemetry SDK/agent được cấu hình exporter và sampling phù hợp.
- [ ] Custom metrics có tên, đơn vị, mô tả và labels ổn định.
- [ ] Metric labels không chứa userId, orderId, email hoặc requestId.
- [ ] Dashboard có traffic, error rate, latency, instance, CPU/memory và dependency.
- [ ] Alert policy gắn với SLO hoặc tác động người dùng và có runbook.
- [ ] Có thể truy vấn log theo service, revision, severity và trace.
- [ ] Runtime identity chỉ có quyền ghi telemetry cần thiết.
- [ ] Log retention, exclusion, metric cardinality và trace sampling được rà soát chi phí.
- [ ] Đã diễn tập điều tra một request lỗi từ metric đến log và trace.

## Tự kiểm tra

1. Logs, metrics và traces khác nhau như thế nào trong việc điều tra một request chậm?
2. Cloud Run request logs và container logs đến từ đâu?
3. Vì sao structured JSON hữu ích hơn log chỉ có message text?
4. Cloud Logging dùng trường nào để liên kết log entry với Cloud Trace?
5. OpenTelemetry context propagation giúp liên kết trace qua HTTP và message ra sao?
6. Vì sao trace có thể không xuất hiện dù request đã thực sự chạy?
7. Metric label chứa orderId hoặc userId có thể gây vấn đề gì?
8. Làm thế nào thiết kế SLI cho availability và latency của API?
9. Khi p95 latency tăng sau deployment, nên kết hợp dashboard, trace và log theo trình tự nào?
10. Những quyền IAM nào cần thiết nếu ứng dụng tự gửi log, metric hoặc trace qua API?

Cloud Logging, Cloud Monitoring và Cloud Trace bổ sung cho nhau để tạo một bức tranh vận hành đầy đủ. Log có cấu trúc và trace context giúp tìm đúng request; metric và SLO cho biết mức ảnh hưởng; distributed trace chỉ ra bước hoặc dependency gây chậm. Khi Java service truyền context đúng, phát telemetry có kiểm soát và gắn alert với hành động cụ thể, đội phát triển có thể điều tra sự cố nhanh mà vẫn kiểm soát dữ liệu và chi phí observability.

