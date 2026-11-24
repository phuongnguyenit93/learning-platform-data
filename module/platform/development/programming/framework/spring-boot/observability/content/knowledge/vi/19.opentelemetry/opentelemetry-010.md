# SdkLoggerProvider

Trong chương **OpenTelemetry** của mô-đun **SPRING_BOOT_OBSERVABILITY**, SdkLoggerProvider là thành phần trung tâm của OpenTelemetry Java SDK dùng để tạo các logger phát hành log records. Provider quản lý cấu hình chung như resource, instrumentation scope và log record processors. Processor nhận records, xử lý theo chính sách phù hợp rồi chuyển tới exporter hoặc đích tiếp theo.

Khi thiết lập observability cho Spring Boot bằng **Micrometer Observation, metrics, logs và distributed tracing**, cần hiểu riêng pipeline logs. Micrometer Observation thường giúp đo hoạt động và tạo spans/metrics qua handlers; SLF4J/Logback tiếp tục tiếp nhận log statements của ứng dụng; OpenTelemetry Logs SDK cung cấp API và pipeline chuẩn để phát log records tới Collector/backend. **Cấu hình OTLP tracing không tự động có nghĩa logs đã được xuất qua OTLP.**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của SdkLoggerProvider trong OpenTelemetry Logs SDK.
2. Phân biệt LoggerProvider, Logger, LogRecordBuilder, LogRecordProcessor và LogRecordExporter.
3. Hiểu Resource attributes và instrumentation scope được gắn vào log record.
4. Cấu hình exporter cùng batch processor để xuất logs qua OTLP.
5. Quản lý vòng đời provider và đóng tài nguyên khi ứng dụng shutdown.
6. Phân biệt logging bằng SLF4J/Logback với việc phát log record qua OpenTelemetry API.
7. Chọn cách tích hợp logging framework với OpenTelemetry cho Spring Boot.
8. Kiểm tra logs ở exporter/Collector/backend và định vị lỗi pipeline.
9. Kiểm soát attributes, cardinality, dữ liệu nhạy cảm, batching và chi phí lưu trữ.
10. Kết hợp logs với trace context, metrics và distributed tracing để điều tra sự cố.

## 2. SdkLoggerProvider trong logs pipeline

| Thành phần | Trách nhiệm |
| --- | --- |
| **SdkLoggerProvider** | Tạo Logger, quản lý Resource, cấu hình LogRecordProcessors và chính sách chung. |
| **Logger** | Tạo log records theo instrumentation scope. |
| **LogRecordBuilder** | Tạo record với body, severity, timestamp và attributes trước khi emit. |
| **LogRecordProcessor** | Nhận record và xử lý; có thể chuyển trực tiếp hoặc gom batch trước khi export. |
| **LogRecordExporter** | Gửi records tới đích như OTLP receiver. |
| **Resource** | Mô tả nguồn phát telemetry: service name, version, environment. |
| **Instrumentation scope** | Mô tả thư viện/module tạo telemetry, thường gồm tên và phiên bản. |

~~~mermaid
flowchart LR
    App["Ứng dụng / instrumentation"] --> Provider["SdkLoggerProvider"]
    Provider --> Logger["Logger"]
    Logger --> Builder["LogRecordBuilder"]
    Builder --> Emit["emit()"]
    Emit --> Processor["LogRecordProcessor"]
    Processor --> Exporter["LogRecordExporter"]
    Exporter --> Collector["OTLP Collector"]
    Collector --> Backend["Logs backend"]
~~~

Provider tạo logger và kết nối processor với exporter. Logger tạo records; processor quyết định record được xử lý ngay hay được batch; exporter vận chuyển. Collector/backend nhận, xử lý, lưu và cho phép truy vấn dữ liệu.

**SdkLoggerProvider không phải logging backend và cũng không phải Logback appender.** Nó là một phần của SDK pipeline. Để log statements vốn được ghi bằng SLF4J/Logback đi vào pipeline OpenTelemetry, cần một thành phần tích hợp tương ứng, chẳng hạn appender/bridge. Nếu chỉ tạo SdkLoggerProvider mà không có code gọi OpenTelemetry Logger API hoặc logging bridge, các lệnh log thông thường chưa chắc xuất hiện trong pipeline này.

## 3. Resource và instrumentation scope

### Resource mô tả service phát telemetry

Resource gắn với provider giúp backend phân biệt dữ liệu đến từ dịch vụ, phiên bản và môi trường nào:

~~~java
Resource resource = Resource.getDefault().merge(
        Resource.create(Attributes.of(
                AttributeKey.stringKey("service.name"), "order-api",
                AttributeKey.stringKey("service.version"), "1.4.2",
                AttributeKey.stringKey("deployment.environment"), "production"
        ))
);
~~~

Đây là ví dụ minh họa. Trong môi trường thật, không hard-code version/environment trong source nếu chúng thay đổi theo deployment; có thể cấp qua environment variables, build metadata hoặc cấu hình nền tảng.

Nên giữ resource identity ổn định:
- service.name là tên service nhất quán giữa logs, metrics và traces.
- service.version cho biết phiên bản đang chạy.
- environment/namespace dùng để lọc dữ liệu theo môi trường.
- host/pod/instance attributes chỉ thêm khi thực sự hữu ích.

Không đưa user ID, request ID, order ID hoặc dữ liệu thay đổi theo từng request vào Resource. Resource mô tả thực thể phát telemetry; thông tin request thuộc log record/span tương ứng.

### Instrumentation scope mô tả nơi tạo record

Logger được lấy từ provider với tên scope. Scope có thể là thư viện hoặc module tạo log records, không nhất thiết giống service name:

~~~java
Logger logger = loggerProvider.get("com.example.order.instrumentation");
~~~

Nếu cần version scope, dùng API tương ứng với phiên bản OpenTelemetry SDK của dự án. Không gắn request ID hoặc tên khách hàng vào instrumentation scope; scope là metadata tương đối ổn định.

## 4. Tạo SdkLoggerProvider và exporter OTLP

Ví dụ Java minh họa cấu hình OpenTelemetry Logs SDK với OTLP gRPC exporter và batch processor. Các API/package cụ thể cần được quản lý cùng một phiên bản OpenTelemetry BOM tương thích:

~~~java
import java.time.Duration;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.logs.Logger;
import io.opentelemetry.api.logs.Severity;
import io.opentelemetry.exporter.otlp.logs.OtlpGrpcLogRecordExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.logs.SdkLoggerProvider;
import io.opentelemetry.sdk.logs.export.BatchLogRecordProcessor;
import io.opentelemetry.sdk.resources.Resource;

public final class LogsSdkExample {

    public static void main(String[] args) {
        Resource resource = Resource.getDefault().merge(
                Resource.create(Attributes.of(
                        AttributeKey.stringKey("service.name"), "order-api",
                        AttributeKey.stringKey("service.version"), "1.4.2"
                ))
        );

        var exporter = OtlpGrpcLogRecordExporter.builder()
                .setEndpoint("http://localhost:4317")
                .setTimeout(Duration.ofSeconds(5))
                .build();

        var processor = BatchLogRecordProcessor.builder(exporter)
                .setScheduleDelay(Duration.ofSeconds(1))
                .setMaxQueueSize(2048)
                .setMaxExportBatchSize(512)
                .build();

        SdkLoggerProvider loggerProvider =
                SdkLoggerProvider.builder()
                        .setResource(resource)
                        .addLogRecordProcessor(processor)
                        .build();

        OpenTelemetrySdk openTelemetry = OpenTelemetrySdk.builder()
                .setLoggerProvider(loggerProvider)
                .build();

        Logger logger = openTelemetry.getLogsBridge()
                .get("com.example.order");

        logger.logRecordBuilder()
                .setSeverity(Severity.INFO)
                .setSeverityText("INFO")
                .setBody("Order validation completed")
                .setAttribute(AttributeKey.stringKey("operation"), "validate")
                .setAttribute(AttributeKey.stringKey("outcome"), "success")
                .emit();

        loggerProvider.close();
    }
}
~~~

Đây là ví dụ tạo provider độc lập để hiểu các thành phần. Trong ứng dụng Spring Boot, không tạo provider mới mỗi request hoặc mỗi lần gọi service. Provider nên được tạo một lần, chia sẻ trong application context và đóng khi ứng dụng shutdown. Với server, cần bảo đảm shutdown hook/lifecycle gọi close sau khi không còn công việc phát log cần hoàn tất.

Lưu ý:

- Endpoint gRPC mẫu dùng localhost cổng 4317; Collector phải bật OTLP gRPC receiver tại địa chỉ đó.
- Nếu dùng OTLP/HTTP, chọn exporter HTTP phù hợp và cấu hình endpoint/path đúng cho logs. Không chỉ đổi số port trong URL mà không đổi transport.
- Batch processor gom records trước khi export để giảm chi phí network; tham số phải dựa trên throughput, memory và latency chấp nhận được.
- SDK versions và package names cần đồng bộ; tránh ghép exporter/API versions tùy ý.
- Production cần TLS/auth và secret management; HTTP localhost chỉ dành cho lab được kiểm soát.

### Vì sao dùng BatchLogRecordProcessor?

Batch processor phù hợp với ứng dụng server có nhiều log records. Nó gom records trước khi export để giảm overhead gửi từng record. Đổi lại, records có thể nằm trong queue một khoảng thời gian và cần được flush đúng lúc shutdown.

Processor batch cần giới hạn queue/batch size. Nếu queue đầy hoặc exporter lỗi kéo dài, records mới có thể bị drop. Cần theo dõi exporter failures, queue pressure và dropped records theo khả năng của SDK/version.

Một processor đồng bộ có thể hữu ích trong test hoặc debug vì record được gửi ngay. Tuy nhiên, export trực tiếp trên đường ghi log có thể tăng latency thread nghiệp vụ và khiến ứng dụng phụ thuộc tình trạng backend. Không coi synchronous export là production mặc định nếu chưa có capacity test.

## 5. Phát log record qua OpenTelemetry API

Sau khi có provider, tạo logger theo instrumentation scope và phát record:

~~~java
Logger logger = loggerProvider.get("com.example.payment");

logger.logRecordBuilder()
        .setSeverity(Severity.WARN)
        .setSeverityText("WARN")
        .setBody("Payment authorization requires review")
        .setAttribute(AttributeKey.stringKey("payment.operation"), "authorize")
        .setAttribute(AttributeKey.stringKey("payment.outcome"), "review")
        .emit();
~~~

Các thành phần của record:

- **Body:** nội dung log dạng text hoặc kiểu dữ liệu được API hỗ trợ.
- **Severity:** mức độ như TRACE, DEBUG, INFO, WARN, ERROR.
- **Severity text:** biểu diễn mức độ gốc nếu cần giữ nguyên cách gọi từ logging framework.
- **Attributes:** trường có cấu trúc giúp tìm kiếm/lọc.
- **Timestamp/observed timestamp:** thời điểm sự kiện xảy ra và/hoặc thời điểm SDK quan sát, tùy API.
- **Trace context:** trace ID/span ID/flags nếu record được phát trong context tracing hiện hành và SDK tích hợp context tương ứng.

Không chỉ ghi một câu dài rồi kỳ vọng backend phân tích mọi thành phần. Dùng attributes cho các trường ổn định và có ý nghĩa, đồng thời kiểm soát cardinality và dữ liệu nhạy cảm.

### Severity phản ánh ý nghĩa vận hành

Không ghi mọi lỗi nghiệp vụ ở ERROR nếu hệ thống coi đó là kết quả bình thường. Giao dịch bị từ chối do hạn mức có thể là WARN hoặc INFO tùy semantics. Lỗi kết nối downstream hoặc exception không xử lý thường cần severity cao hơn. Quy ước nên thống nhất giữa các service để alert và truy vấn có ý nghĩa.

## 6. Tạo provider như Spring bean và quản lý lifecycle

Trong Spring Boot, provider nên có lifecycle gắn với ứng dụng. Ví dụ cấu trúc cấu hình:

~~~java
import java.time.Duration;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.exporter.otlp.logs.OtlpGrpcLogRecordExporter;
import io.opentelemetry.sdk.logs.SdkLoggerProvider;
import io.opentelemetry.sdk.logs.export.BatchLogRecordProcessor;
import io.opentelemetry.sdk.resources.Resource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OpenTelemetryLogsConfiguration {

    @Bean(destroyMethod = "close")
    SdkLoggerProvider sdkLoggerProvider() {
        Resource resource = Resource.getDefault().merge(
                Resource.create(Attributes.of(
                        AttributeKey.stringKey("service.name"), "order-api"
                ))
        );

        var exporter = OtlpGrpcLogRecordExporter.builder()
                .setEndpoint("http://otel-collector:4317")
                .setTimeout(Duration.ofSeconds(5))
                .build();

        var processor = BatchLogRecordProcessor.builder(exporter)
                .setScheduleDelay(Duration.ofSeconds(1))
                .build();

        return SdkLoggerProvider.builder()
                .setResource(resource)
                .addLogRecordProcessor(processor)
                .build();
    }
}
~~~

Bean trên minh họa lifecycle của riêng SdkLoggerProvider. **Không tự ý thêm cấu hình này vào ứng dụng đã có OpenTelemetry SDK do Spring Boot, agent hoặc starter khác quản lý.** Hai provider riêng có thể tạo logs/traces đi theo pipeline khác nhau, gây trùng, thiếu context hoặc khó shutdown.

Trước khi tự khai báo bean, xác định ai đang sở hữu OpenTelemetry instance và provider trong ứng dụng. Nếu hệ thống đã có SDK thống nhất, hãy tích hợp logger provider vào SDK đó hoặc dùng cơ chế autoconfiguration tương ứng. Chỉ tạo provider độc lập khi có chủ đích và đã kiểm tra không tạo pipeline cạnh tranh.

### Đóng provider ở đâu?

Khai báo destroy method close cho Spring quản lý close khi application context shutdown. Provider close có thể yêu cầu processor flush/shutdown exporter theo implementation. Không đóng provider sau mỗi log statement hoặc giữa các request đang chạy.

Nếu khởi tạo thủ công ngoài Spring, dùng try/finally hoặc lifecycle owner rõ ràng. Khi shutdown, cho request đang xử lý hoàn tất theo graceful shutdown policy trước khi đóng pipeline logs.

## 7. SdkLoggerProvider và SLF4J/Logback trong Spring Boot

Phần lớn ứng dụng Spring Boot ghi log như sau:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

log.info("Order accepted: {}", orderId);
~~~

Đây là logging facade SLF4J đi tới logging backend như Logback. Đoạn code trên **không tự động gọi Logger của OpenTelemetry Logs API** chỉ vì ứng dụng có dependency SdkLoggerProvider.

Có hai hướng thường gặp:

| Hướng | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| Gọi OpenTelemetry Logs API trực tiếp | Code dùng OpenTelemetry Logger để tạo log record. | Instrumentation/thư viện cần phát OTel log record có cấu trúc trực tiếp. |
| Bridge/appender từ logging framework | SLF4J/Logback tiếp tục là API ghi log; appender/bridge chuyển event sang OpenTelemetry pipeline. | Ứng dụng đã có nhiều log statements và muốn giữ cách sử dụng logging. |

Không phát cùng một log event qua cả appender cũ và OTel appender rồi export cả hai nếu backend không có chính sách deduplication. Điều đó có thể tạo bản ghi trùng và tăng chi phí.

### Không nhầm với Micrometer Tracing log correlation

Micrometer Tracing có thể tích hợp trace ID/span ID vào logging context/MDC. Log pattern hiển thị trace ID giúp liên kết logs với traces, nhưng **correlation không đồng nghĩa OTLP log export**. Logs vẫn có thể được thu thập bởi agent, appender hoặc pipeline khác.

Tương tự, OTLP tracing exporter gửi spans không tự gửi SLF4J events thành OTLP logs. Nếu muốn logs tới cùng Collector, phải cấu hình pipeline logs riêng và kiểm tra Collector có logs receiver/exporter tương ứng.

## 8. Trace context trong log record

Một log record được phát khi trace/span hiện hành có thể mang trace context để backend liên kết log với trace. Điều này phụ thuộc context active và cách logging API/bridge lấy context.

Các trường hữu ích:
- Trace ID để tìm trace phân tán.
- Span ID để xác định span gắn với sự kiện.
- Service name/version để lọc đúng service.
- Operation, outcome và error category với giá trị có kiểm soát.
- Timestamp để đối chiếu timeline giữa logs, metrics và spans.

Không tự tạo trace ID ngẫu nhiên rồi gán vào record như thể đó là trace context thật. Nếu cần correlation ID riêng, đặt tên field riêng và không nhầm nó với Trace ID chuẩn.

Nếu log được phát trên thread không mang context, trace ID/span ID có thể vắng mặt. Với async/reactive, cần bảo đảm context propagation tới execution context thực sự tạo log. MDC có giá trị trên thread gọi không chứng minh giá trị đã được truyền sang thread worker.

## 9. Attributes, cardinality và quyền riêng tư

Log attributes giúp backend tìm kiếm nhanh hơn, nhưng mỗi attribute tăng dung lượng, index cost và rủi ro lộ dữ liệu.

| Attribute | Mức độ phù hợp | Ghi chú |
| --- | --- | --- |
| operation=authorize | Thường phù hợp | Tập giá trị hữu hạn. |
| outcome=success/error/review | Thường phù hợp | Hữu ích cho lọc và thống kê. |
| service.name=order-api | Resource phù hợp | Mô tả service, không phải request. |
| request.id dạng UUID | Chỉ khi có mục đích rõ | Cardinality cao; cân nhắc logs riêng với retention/access phù hợp. |
| customer.email | Không nên mặc định | Dữ liệu cá nhân. |
| authorization | Không | Credential/secret. |
| Request body đầy đủ | Không nên mặc định | Có thể chứa PII, secrets và payload lớn. |

Nguyên tắc:
- Chỉ ghi attributes cần cho điều tra.
- Dùng tên field ổn định và kiểu dữ liệu nhất quán.
- Không lưu access token, cookie, password, API key, session secret hoặc dữ liệu thanh toán nhạy cảm.
- Mask/redact dữ liệu cá nhân theo policy trước khi export.
- Hạn chế log stack trace lặp lại hoặc payload rất lớn.
- Đặt retention và quyền truy cập phù hợp; logs thường chứa thông tin nhạy cảm hơn metrics.
- Không tự động copy toàn bộ baggage hoặc gRPC metadata vào log records.

Sampling traces không thay thế chính sách lọc logs. Một log record vẫn có thể chứa dữ liệu nhạy cảm ngay cả khi trace gắn với nó bị sample out.

## 10. Batching, queue và lỗi exporter

BatchLogRecordProcessor giảm overhead gửi từng record nhưng tạo queue tạm thời và có thể drop record nếu queue đầy hoặc exporter liên tục thất bại.

Những tín hiệu cần theo dõi:
- Export success/failure và timeout.
- Queue saturation hoặc dropped log records.
- Batch size và schedule delay.
- Collector accepted/refused/dropped records.
- Network latency, TLS/authentication errors.
- Backend ingestion rate, storage growth và indexing delay.

Khi exporter không kết nối, không để logging làm treo request nghiệp vụ vô thời hạn. Timeout/retry/queue phải có giới hạn và behavior khi quá tải. Logs observability cũng cần monitoring độc lập; nếu chỉ dựa vào chính logs để báo log exporter đang mất logs, có thể không thấy lỗi.

Tăng queue size có thể trì hoãn thời điểm drop nhưng cũng tăng memory. Hãy xác định nguyên nhân downstream chậm, chỉnh batch/throughput hoặc capacity, đồng thời giữ giới hạn để bảo vệ ứng dụng.

## 11. Kiểm thử SdkLoggerProvider

Một test hữu ích xác minh record được tạo, processor nhận record và exporter nhận payload. Có thể dùng exporter giả hoặc test exporter tương thích phiên bản SDK để không phụ thuộc Collector thật trong unit test.

Các assertion nên gồm:
1. Resource attributes có service name và version đúng.
2. Instrumentation scope có tên module dự kiến.
3. Body và severity đúng.
4. Attributes cần thiết được export với kiểu dữ liệu mong muốn.
5. Trace context được gắn khi log phát trong active span và integration hỗ trợ.
6. Provider flush/close không bỏ records đang chờ.
7. Khi exporter lỗi, ứng dụng không bị treo ngoài timeout/queue policy.

~~~mermaid
sequenceDiagram
    participant T as Test / Spring Boot app
    participant P as SdkLoggerProvider
    participant E as OTLP exporter
    participant C as Collector
    participant B as Test backend

    T->>P: Emit log record
    P->>E: Processor export batch
    E->>C: OTLP logs request
    C->>B: Forward log record
    B-->>T: Test query finds record
~~~

Collector nhận request chưa đủ chứng minh backend đã index log. Kiểm thử end-to-end cần truy vấn được record sau export, hoặc ít nhất xác minh Collector accepted và forwarded theo topology test.

### Phân biệt lỗi ghi record với lỗi export

| Kết quả | Diễn giải |
| --- | --- |
| Không tạo được logger | Provider chưa cấu hình/đóng hoặc dependency/API không tương thích. |
| Emit record nhưng exporter không được gọi | Processor chưa gắn, provider khác đang được dùng hoặc processor đã shutdown. |
| Exporter nhận record nhưng Collector không nhận | Sai endpoint/transport, TLS/auth, network hoặc receiver chưa bật. |
| Collector nhận record nhưng backend không thấy | Pipeline logs chưa có exporter phù hợp, record bị filter hoặc backend index chậm. |
| Backend thấy log nhưng thiếu trace ID | Log phát ngoài active trace context hoặc bridge chưa gắn context. |
| Backend có record trùng | Log event được gửi qua nhiều appender/pipeline đồng thời. |

## 12. Kết hợp SdkLoggerProvider với Micrometer Observation

Micrometer Observation mô tả hoạt động và có thể tạo metrics/tracing thông qua handlers. SdkLoggerProvider phát logs qua OpenTelemetry Logs API. Hai thành phần có thể cùng phục vụ một operation nhưng không thay thế nhau.

~~~text
Operation: order.authorize
  Observation:
    - Timer / metrics
    - Span / distributed trace
  Log records:
    - authorization started
    - authorization failed
    - attributes: operation, outcome, error.type
~~~

Một workflow điều tra:
1. Metrics chỉ ra error ratio tăng trên route thanh toán.
2. Logs cho biết loại lỗi và timestamp, có trace ID/span ID khi correlation hoạt động.
3. Traces cho thấy dependency nào gây chậm hoặc lỗi.
4. Baggage/attributes nhỏ đã xác minh giúp nhóm sự kiện theo request class/region nếu cần.
5. Sau xử lý, metrics xác nhận error ratio và latency trở lại ngưỡng.

Đừng tạo log record cho mọi event chỉ để thay metrics. Counter/timer phù hợp thống kê; logs phù hợp sự kiện có ngữ nghĩa; traces phù hợp mô tả đường thực thi. Mỗi tín hiệu cần mức chi tiết và retention riêng.

## 13. Lỗi thường gặp khi triển khai SdkLoggerProvider

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| SLF4J logs không xuất hiện qua OTLP | Chỉ tạo SdkLoggerProvider nhưng chưa có bridge/appender hoặc code chưa dùng OTel Logs API. | Kiểm tra đường từ logging framework tới OTel pipeline. |
| Traces có nhưng logs trống | Chỉ cấu hình tracing exporter; logs pipeline chưa bật. | Kiểm tra logger provider, processor, exporter và Collector logs receiver. |
| Provider tạo hai pipeline | SDK/provider tự tạo cạnh tranh với auto-configuration hoặc agent. | Xác định một lifecycle owner và instance dùng chung. |
| Logs thiếu service.name | Resource không gắn vào provider hoặc sai SDK instance. | Kiểm tra Resource trong payload. |
| Logs thiếu trace ID | Không có active context hoặc bridge không lấy trace context. | Kiểm tra span scope, async propagation và log instrumentation. |
| Logs xuất trùng | Appender cũ và OTel appender cùng forward event. | Rà soát appender/pipeline và duplicate forwarding. |
| Mất log khi shutdown | Processor chưa flush/close đúng lifecycle hoặc shutdown quá gấp. | Quản lý provider lifecycle và graceful shutdown. |
| Queue đầy | Collector/backend chậm, timeout hoặc throughput thấp. | Kiểm tra queue, exporter retry, batch size và capacity. |
| Collector nhận nhưng backend không thấy | Pipeline logs filter/drop hoặc backend ingestion/index lỗi. | Kiểm tra Collector pipeline và backend. |
| Payload có PII/secret | Attributes/body được ghi không lọc. | Redact ở nguồn, processor và rà soát access/retention. |

## 14. Runbook: logs không xuất hiện trong backend

1. **Xác định nguồn log:** code đang gọi SLF4J/Logback hay OpenTelemetry Logger API?
2. **Kiểm tra provider:** đúng SdkLoggerProvider có được tạo và logger lấy từ provider đó không?
3. **Kiểm tra processor:** batch/simple processor đã gắn trước khi provider build chưa?
4. **Kiểm tra exporter:** endpoint, protocol, TLS, credentials và timeout có hợp lệ không?
5. **Kiểm tra Collector:** logs receiver có bật và logs pipeline có processor/exporter tương ứng không?
6. **Kiểm tra backend:** ingestion, filtering, indexing, retention và query time range.
7. **Kiểm tra trace correlation:** log phát trong active span/context hay trên thread khác?
8. **Kiểm tra trùng hoặc lọc:** appender cũ, bridge và Collector processors có drop/duplicate event không?
9. **Kiểm thử shutdown:** phát một record, flush/close provider đúng cách, xác minh record cuối đã export.
10. **Kiểm tra bảo mật:** credentials/TLS đúng và payload không chứa secrets/PII ngoài policy.

Tìm ranh giới đầu tiên không có bằng chứng thay vì thêm dependency hoặc tạo provider khác ngay lập tức. Một pipeline có thể nhận traces tốt nhưng chưa có cấu hình logs.

## 15. Bài tập tự kiểm tra

### Bài 1 — Provider có đủ để nhận SLF4J không?

Ứng dụng tạo SdkLoggerProvider và exporter OTLP. Các service vẫn chỉ gọi SLF4J Logger. Có thể kết luận logs đã được xuất chưa?

**Đáp án:** Chưa. Cần logging bridge/appender hoặc instrumentation tích hợp chuyển log events từ SLF4J/Logback vào OpenTelemetry Logs pipeline. Chỉ tạo provider không tự chuyển mọi logging calls.

### Bài 2 — Có traces nhưng không có logs

Backend tìm thấy spans của order-api nhưng không có log records. Nguyên nhân nào nên kiểm tra đầu tiên?

**Đáp án:** Tracing exporter và logs exporter là hai pipeline riêng. Kiểm tra SdkLoggerProvider, LogRecordProcessor, exporter và Collector logs receiver/pipeline.

### Bài 3 — Vì sao không tạo provider mỗi request?

Một service xây SdkLoggerProvider mới trong mỗi request để thêm request ID vào resource. Thiết kế này có vấn đề gì?

**Đáp án:** Resource mô tả service/process, không phải từng request. Tạo provider liên tục gây overhead, nhiều exporters/processors, khó close và tăng rủi ro mất log. Request metadata nên ở log attributes/context phù hợp và phải kiểm soát cardinality/privacy.

### Bài 4 — Logs bị trùng

Một log xuất hiện hai lần trong backend sau khi thêm OTel appender. Nguyên nhân có thể là gì?

**Đáp án:** Cùng event được gửi qua appender cũ và OTel appender hoặc nhiều bridge/pipeline cùng forward. Rà soát logger hierarchy, additivity và appender forwarding.

### Bài 5 — Trace ID trống

Log record được export nhưng không có trace ID/span ID. Điều đó có chứng minh exporter sai không?

**Đáp án:** Không. Record có thể được tạo ngoài active span, trên thread bị mất context hoặc bằng logger không đọc trace context. Kiểm tra scope và context propagation trước exporter.

### Bài 6 — Queue đầy

Batch processor drop records khi Collector chậm. Có nên tăng queue vô hạn không?

**Đáp án:** Không. Queue vô hạn có thể làm cạn memory ứng dụng. Cần giới hạn queue, đo throughput, timeout/retry, batch size, Collector/backend capacity và policy khi quá tải.

## 16. Checklist triển khai

- [ ] Xác định logging source: SLF4J/Logback hay OpenTelemetry Logs API.
- [ ] SdkLoggerProvider được quản lý bởi một lifecycle owner rõ ràng.
- [ ] Logger lấy từ đúng provider và instrumentation scope ổn định.
- [ ] Resource có service.name/version/environment phù hợp.
- [ ] LogRecordProcessor được gắn trước khi provider build.
- [ ] Exporter dùng đúng OTLP transport, endpoint, TLS/auth và timeout.
- [ ] Batch queue/batch size/schedule delay được capacity planning.
- [ ] Spring logging framework có bridge/appender khi muốn forward SLF4J events.
- [ ] Không tạo provider độc lập cạnh tranh với SDK/agent đã được quản lý.
- [ ] Provider flush/close đúng lifecycle và graceful shutdown.
- [ ] Log body/severity/attributes có cấu trúc, cardinality và privacy được kiểm soát.
- [ ] Trace context được liên kết khi record phát trong active span và integration hỗ trợ.
- [ ] Collector có logs receiver và pipeline logs riêng, không chỉ traces pipeline.
- [ ] Có kiểm thử unit và end-to-end xác minh record tới backend.
- [ ] Theo dõi exporter errors, queue pressure, dropped records và backend ingestion.
- [ ] Logs, metrics và traces được dùng đúng vai trò trong runbook điều tra.

**Ghi nhớ:** SdkLoggerProvider là provider của OpenTelemetry Logs SDK: nó tạo Logger và kết nối log records với processor/exporter. Trong Spring Boot, hãy xác định log đi từ SLF4J/Logback hay OpenTelemetry API, quản lý provider theo lifecycle ứng dụng, cấu hình OTLP logs pipeline riêng và kiểm chứng đến Collector/backend. Khi logs có resource, severity, attributes và trace correlation phù hợp, chúng bổ sung cho metrics và distributed tracing để điều tra sự cố mà vẫn kiểm soát chi phí và dữ liệu nhạy cảm.
