# Cloud logging configuration trong môi trường chạy Java

## 1. Khái niệm và mục tiêu

**Cloud logging configuration** là cách tổ chức cấu hình để ứng dụng Java tạo log, truyền log, gắn ngữ cảnh, lưu trữ và truy vấn log khi chạy trên hạ tầng cloud: virtual machine, container, Kubernetes, serverless hoặc managed application platform. Log có giá trị khi người vận hành có thể truy tìm một sự kiện theo service, phiên bản triển khai, thời gian, request và trace, ngay cả sau khi instance phát log đã bị thay thế.

Trên máy phát triển, ghi vào console hoặc file có thể đủ để xem vấn đề. Trong cloud, container có thể bị restart, autoscale hoặc xóa, và filesystem cục bộ thường không phải nơi lưu log lâu dài. Vì vậy, cần thiết kế **đường đi end-to-end** từ lời gọi `logger.info(...)` tới kho log tập trung, cùng định dạng sự kiện, quyền truy cập, retention, khả năng chịu lỗi và chi phí.

Một cấu hình hoàn chỉnh trả lời các câu hỏi:

- Ứng dụng dùng JUL, SLF4J + Logback/Log4j2 hay OpenTelemetry để tạo event? Mức `DEBUG`, `INFO`, `WARN`, `ERROR` được quyết định ở đâu?
- Log đi ra stdout/stderr, file, appender mạng hay OTLP exporter? Có thành phần nào thu thập stream/file đó không?
- Agent/Collector parse JSON, bổ sung service metadata, lọc thông tin nhạy cảm, batch/retry và đưa log tới backend nào?
- Backend lưu log thuộc project/account/workspace, vùng địa lý, quyền truy cập và thời hạn lưu nào?
- Có đo được dropped logs, ingest errors, queue backlog, độ trễ và chi phí ingest không?

**Không tồn tại một chuẩn file config tự động dùng chung cho mọi logging framework và cloud provider.** Logback, Log4j2, JUL, Spring Boot, container runtime, OpenTelemetry và backend cloud có trách nhiệm khác nhau; phải chỉ ra rõ thành phần nào thực hiện mỗi bước.

## 2. Hai kiến trúc truyền log phổ biến

### A. JSON Lines trên stdout/stderr

```text
Java service
  -> logging API / backend / structured encoder
  -> stdout hoặc stderr (mỗi JSON event một dòng)
  -> container/VM runtime log stream
  -> managed logging integration hoặc agent
  -> parser + resource enrichment + routing
  -> cloud log backend
```

Đây là cách khởi đầu phù hợp với nhiều nền tảng container hoặc dịch vụ được quản lý **khi nền tảng có cơ chế thu thập console output**. Ứng dụng xuất bản ghi cấu trúc; runtime và agent xử lý việc vận chuyển. Ứng dụng ít phải phụ thuộc SDK của một nhà cung cấp cloud.

Lợi ích: code dễ chạy local, chuyển môi trường thuận tiện, nhiều thành phần vận hành tách khỏi JVM. Giới hạn: `println` thành công không chứng minh cloud đã nhận được dữ liệu. Runtime có thể giới hạn độ dài event, agent có thể bị lỗi, và nhiều log không tự được parse thành structured fields nếu encoder/parser chưa cấu hình.

**Một sự kiện = một dòng JSON** là quy ước hữu ích. Nếu message chứa newline hoặc exception nhiều dòng, encoder phải escape chúng thành một chuỗi JSON, tránh để agent theo dòng tách thành nhiều event thiếu thông tin.

### B. Xuất bản ghi qua OTLP/Collector hoặc cloud exporter

```text
Java service
  -> logging instrumentation / OTel Logs SDK / appender
  -> OTLP qua HTTP hoặc gRPC
  -> OpenTelemetry Collector
  -> processors: memory limit, batch, filter, enrich, retry
  -> exporter
  -> cloud log backend
```

Mô hình này phù hợp khi muốn pipeline telemetry tập trung, route nhiều đích, chuẩn hóa resource, và cấu hình kiểm soát việc vận chuyển độc lập với ứng dụng. **Phải có instrumentation, SDK hoặc appender thật sự chuyển logging events thành OpenTelemetry log records.** Chỉ đặt biến môi trường `OTEL_LOGS_EXPORTER=otlp` không tự biến mọi `System.out.println` thành OTLP.

Hai đường có thể kết hợp, nhưng nếu cùng một sự kiện được xuất theo OTLP và đồng thời bị agent thu từ stdout, log backend có thể nhận **hai bản sao**. Trước khi bật cả hai, kiểm tra source và quy tắc loại trùng.

| Bối cảnh | Đường truyền thường cân nhắc | Lưu ý |
| --- | --- | --- |
| Container/serverless có sẵn bắt console | JSON stdout/stderr → integration | Xác minh thật sự có collector và parser |
| Kubernetes | Container stream → node agent/Collector | Pod restart, log rotation, namespace/pod metadata |
| VM ghi file | File appender → agent theo dõi file | Quyền đọc, offset, rotation, đường dẫn bền vững |
| Hệ thống có OTLP/Collector | OTel log exporter → Collector | Đúng protocol, endpoint, auth, queue và không duplicate |
| Audit hoặc bằng chứng giao dịch | Luồng sự kiện có yêu cầu durability riêng | Không mặc định stdout/queue async bảo đảm không mất |

## 3. Cấu hình đúng theo trách nhiệm từng lớp

| Lớp | Quyết định chính | Ví dụ |
| --- | --- | --- |
| **Ứng dụng Java** | Message, event name, logger level, exception, context | SLF4J, JUL, Logback/Log4j2, MDC |
| **Structured encoder** | Schema JSON, timestamp, severity, escaping, stack trace | JSON console appender hoặc logging exporter |
| **Container/runtime** | Thu thập stdout/stderr, metadata instance, local rotation | Docker/Kubernetes/managed runtime |
| **Agent hoặc Collector** | Parse, enrich, filter, batch, retry, quota, route | Fluent Bit, cloud agent, OpenTelemetry Collector |
| **Cloud backend** | Project/workspace, retention, index, RBAC/IAM, alert | CloudWatch Logs, Cloud Logging, Azure Monitor Logs, hoặc backend khác |

Hãy xác định một nơi chịu trách nhiệm chọn logger backend và một pipeline vận chuyển chủ đạo. Nếu nhiều appender cùng ghi tới một đích, log có thể lặp; nếu file logger ghi vào filesystem tạm mà không có agent, log có thể mất khi container bị xóa.

Tham số chạy theo môi trường cần có nguồn rõ ràng, ví dụ mức log, tên service, phiên bản, environment, region, collector endpoint. Một biến môi trường mang tên `LOG_LEVEL` **không tự có tác dụng trong Java nói chung**. Nó cần được backend hoặc framework tham chiếu. Spring Boot có cơ chế quản lý `logging.*` riêng; Logback hỗ trợ property substitution; JUL thuần dùng cách cấu hình khác.

## 4. Schema structured logging

Bản ghi JSON mang cấu trúc dễ lọc hơn một chuỗi message chứa nhiều thông tin ngẫu nhiên. Ví dụ:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "severity": "INFO",
  "service.name": "orders-api",
  "service.version": "1.0.0",
  "deployment.environment.name": "prod",
  "event.name": "order.accepted",
  "request_id": "req-42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message": "Order accepted"
}
```

Đây là **schema JSON minh họa của ứng dụng**. Không nên giả định mọi backend tự động ánh xạ các tên trường này sang metadata đặc biệt. Chẳng hạn có hệ thống cần trường severity hoặc trường trace theo định dạng riêng, có hệ thống giữ toàn bộ trong JSON payload. Kiểm tra bản ghi đã ingest và quy tắc mapping của backend đang dùng.

Các trường nên thiết kế nhất quán:

1. **`timestamp`**: thời điểm phát sinh, dùng UTC hoặc offset đầy đủ (ISO-8601/RFC 3339). Phân biệt event timestamp với ingestion timestamp, nhất là khi pipeline bị trễ.
2. **`severity` / `level`**: mức độ, mapping nhất quán giữa backend Java và cloud. Không mặc định mọi cloud coi stderr tương đương ERROR.
3. **Service resource**: tên service, version, môi trường, cluster/namespace/pod/container, region/instance. Một số metadata nên do deployment/agent gắn để tránh hardcode.
4. **Correlation**: `trace_id`, `span_id`, `request_id`. Theo W3C Trace Context, trace ID thường là 32 ký tự hex và span ID là 16 ký tự hex; chỉ lấy ID hợp lệ từ context.
5. **Sự kiện ổn định**: `event.name`, operation name, error code. Message diễn đạt chi tiết; tên sự kiện ổn định giúp phân tích theo loại.
6. **Lỗi**: exception type, stack trace cần thiết và message đã làm sạch. Tránh ghi toàn bộ request, secrets hay PII.
7. **Kích thước giới hạn**: xem giới hạn line/event của agent/backend; log payload quá lớn có thể bị truncate hoặc từ chối.

**Nhóm log theo request không có nghĩa mọi log đều chung span ID.** Một trace chứa nhiều span; span ID nên phản ánh span đang hoạt động khi phát event. Nếu trace bị sampling và không lưu, log mang trace ID vẫn có thể được truy vấn, nhưng việc click sang trace có thể không có kết quả.

## 5. Ví dụ Java 17 chạy độc lập: JSON Lines cho cloud collector

Để hiểu đầu ra trước khi dùng framework, chương trình sau sử dụng API JDK, phát hai JSON event ra stdout và escape thông điệp có dấu ngoặc kép/newline. Đây là **mô phỏng định dạng**, không phải thư viện JSON encoder production. Ứng dụng thật nên dùng structured encoder đã được kiểm chứng để xử lý performance, Unicode, exception, timestamp và context đầy đủ.

Lưu tệp `CloudLogDemo.java`:

```java
import java.util.Locale;

public final class CloudLogDemo {
    private record TraceContext(
            String traceId, String spanId, String requestId) {}

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        out.append(String.format(
                                Locale.ROOT, "\\u%04x", (int) ch));
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static String field(String key, String value) {
        return quote(key) + ":" + quote(value);
    }

    private static void log(
            String severity, String event, String message,
            TraceContext context) {
        String line = "{"
                + field("timestamp", "2026-01-01T00:00:00Z") + ","
                + field("severity", severity) + ","
                + field("service.name", "orders-api") + ","
                + field("service.version", "1.0.0") + ","
                + field("deployment.environment.name", "demo") + ","
                + field("trace_id", context.traceId()) + ","
                + field("span_id", context.spanId()) + ","
                + field("request_id", context.requestId()) + ","
                + field("event.name", event) + ","
                + field("message", message)
                + "}";
        System.out.println(line);
    }

    public static void main(String[] args) {
        TraceContext context = new TraceContext(
                "4bf92f3577b34da6a3ce929d0e0e4736",
                "00f067aa0ba902b7", "req-42");

        log("INFO", "order.accepted",
                "Order 42 accepted", context);
        log("ERROR", "payment.failed",
                "Gateway said \"denied\"\nretry scheduled", context);
    }
}
```

Biên dịch và chạy:

```bash
javac CloudLogDemo.java
java CloudLogDemo
```

**Stdout chính xác**, gồm hai dòng JSON vật lý:

```json
{"timestamp":"2026-01-01T00:00:00Z","severity":"INFO","service.name":"orders-api","service.version":"1.0.0","deployment.environment.name":"demo","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","request_id":"req-42","event.name":"order.accepted","message":"Order 42 accepted"}
{"timestamp":"2026-01-01T00:00:00Z","severity":"ERROR","service.name":"orders-api","service.version":"1.0.0","deployment.environment.name":"demo","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","request_id":"req-42","event.name":"payment.failed","message":"Gateway said \"denied\"\nretry scheduled"}
```

Vì mã Java ghi dấu nháy thành `\"` và newline thành `\n`, event thứ hai **không bị tách thành hai dòng console**. Hàm `quote` xử lý các ký tự điều khiển ASCII và dấu backslash để tạo JSON string hợp lệ. Các trace/span ID được cố định để kiểm chứng đầu ra; trong sản xuất phải lấy từ context đang hoạt động, không hardcode. Thời điểm `timestamp` cố định chỉ để ví dụ có đầu ra chính xác; thực tế sử dụng timestamp tại lúc phát log, chẳng hạn `Instant.now().toString()`.

Dòng `System.out.println` minh họa việc phát stdout; một Collector hoặc runtime cloud chỉ nhận chúng nếu đã được cấu hình thu thập. Để phân tích end-to-end, phải tìm được chính hai sự kiện này ở backend, không chỉ thấy trên console.

## 6. Cấu hình SLF4J/Logback, JUL và Log4j2

### Cấu hình Logback console appender

Nếu ứng dụng dùng SLF4J với Logback Classic tương thích, có thể đặt `logback.xml` trong `src/main/resources`. Ví dụ sau dùng **text pattern để minh họa cấu hình**, không phải JSON encoder:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%date %-5level service=orders-api trace_id=%X{trace_id} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="${LOG_LEVEL:-INFO}">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Trong Logback, `${LOG_LEVEL:-INFO}` cho phép cấu hình log level theo property/biến môi trường nếu được cung cấp đúng thời điểm, mặc định `INFO` ở đây. Pattern `%X{trace_id}` đọc từ MDC khi đã có context. Để output JSON production, thay encoder bằng **JSON encoder tương thích với Logback và phiên bản dependency**, kiểm tra exception serialization, field mapping, escaping và message length. Đừng gọi pattern text trên là structured JSON.

Với **Log4j2**, định nghĩa Console appender/JSON layout hoặc template layout bằng cú pháp của Log4j2; không sử dụng trực tiếp `logback.xml`. Với **java.util.logging (JUL)**, dùng `LogManager`, handler và formatter; JUL thuần không tự hiểu `logback.xml` hoặc `LOG_LEVEL`. **SLF4J là facade**: phải có provider/backend phù hợp, tránh nhiều provider hoặc cầu nối tạo vòng route log.

Trong Spring Boot, `logging.level.*`, `logging.config` và `logback-spring.xml` được xử lý theo cơ chế của Spring Boot. Cần xác nhận thứ tự khởi tạo logger và các property thực sự có hiệu lực; không mặc định quy tắc của Spring Boot áp dụng cho Java application thuần.

### Level và policy

| Event | Hướng xử lý thường gặp | Giới hạn |
| --- | --- | --- |
| `TRACE` / `DEBUG` | Tắt mặc định ở production; bật tạm cho phạm vi hẹp | Tránh bùng nổ dữ liệu và lộ thông tin |
| `INFO` nghiệp vụ | Giữ event quan trọng; cân nhắc sampling event lặp lại | Không dựa vào tập mẫu để tính metric chính xác |
| `WARN` / `ERROR` | Giữ đủ thông tin điều tra, tạo alert phù hợp | Kiểm soát trùng stack trace và thông tin nhạy cảm |
| Audit/bảo mật/giao dịch bắt buộc | Luồng lưu giữ theo hợp đồng riêng | Không sampling tùy ý nếu yêu cầu phải đầy đủ |

Việc giảm logging có thể xảy ra ở Java logger, appender, Collector hay backend. Điểm lọc càng muộn thì ứng dụng/agent càng có thể đã trả chi phí serialize và truyền event. Cần đo lợi ích và khả năng điều tra sau khi thay level.

## 7. Context propagation và correlation trên cloud

Trong distributed system, ngữ cảnh request thường được truyền qua HTTP/gRPC bằng cơ chế propagation như W3C Trace Context. Appender hoặc instrumentation có thể thêm `trace_id` và `span_id` của span hiện tại. Đừng tự tạo một ID mới cho mỗi log vì điều đó phá liên kết giữa các service.

MDC (Mapped Diagnostic Context) thường có ngữ nghĩa theo thread; với `ExecutorService`, `CompletableFuture` hoặc reactive pipeline, context **không mặc nhiên** được truyền sang thread khác. Cần context-aware executor/instrumentation phù hợp, và khôi phục/xóa MDC trong `finally` để request tiếp theo không mang ID cũ. Test ít nhất trường hợp một thread pool xử lý các request liên tiếp và tác vụ chạy bất đồng bộ.

Nếu backend có UI liên kết log và trace, nó có thể đòi hỏi một field trace theo format riêng hoặc metadata project/resource. **Có `trace_id` trong JSON không bảo đảm nút “View trace” hoạt động**; phải đối chiếu backend mapping. Sampling trace và sampling log là hai chính sách độc lập: một request không được lưu trace vẫn có thể có ERROR log. Không lọc ERROR chỉ dựa vào cờ sampled.

## 8. Thiết lập theo môi trường chạy

### Container và serverless

- Ưu tiên stdout/stderr nếu cloud runtime có tích hợp thu log, dùng encoder JSON Lines và schema ổn định.
- Không dựa vào file trong writable layer tạm của container làm nơi lưu log duy nhất.
- Kiểm tra giới hạn độ dài một event, buffering, phân loại stdout/stderr và thông tin metadata mà runtime thực tế bổ sung.
- Cần xử lý shutdown/flush theo hợp đồng backend; không giả định một dòng vừa được phát đã đến kho lưu trữ.

### Kubernetes

`kubectl logs` giúp xem stream log của container còn khả dụng; nó **không thay thế** kho log có retention khi pod đã bị xóa. Pipeline có thể dùng node-level logging agent/DaemonSet, managed cluster integration hoặc Collector đọc container log stream, bổ sung namespace/pod/container metadata rồi gửi đến backend.

Một phần env của container trong Pod spec có thể như sau:

```yaml
env:
  - name: LOG_LEVEL
    value: "INFO"
  - name: SERVICE_NAME
    value: "orders-api"
  - name: DEPLOYMENT_ENVIRONMENT
    value: "prod"
```

Đây là **đoạn YAML của container `env`**, chưa phải Deployment hoàn chỉnh. Phải cấu hình logging/backend/Collector thực sự sử dụng các biến đó. Với Kubernetes, cần kiểm tra agent đọc đúng stream sau pod restart, log rotation, giới hạn quyền và khả năng ingest khi node mất kết nối.

### VM hoặc file log

Nếu không có managed stdout collector, có thể dùng file appender và logging agent theo dõi file. Cần xác định path, quyền đọc của agent, quyền ghi của ứng dụng, rotation, checkpoint/offset, restart và quota đĩa. Nếu file nằm trong container khác, phải có volume chia sẻ đúng; mỗi container không tự nhìn thấy filesystem của container khác.

### Cấu hình external và môi trường

Nên để artifact ứng dụng dùng được cho dev/staging/prod, truyền level, endpoint, service version và metadata môi trường qua deployment configuration. Secrets hoặc credentials nên đến từ cloud identity/secret manager; không đóng vào JAR hay console output. Khi đổi cấu hình động, phải biết backend có hỗ trợ reload hay cần restart; resource trong JAR không tự sửa tại runtime.

## 9. OpenTelemetry trong Java: điều kiện để cấu hình hoạt động

OpenTelemetry mô tả log records, resource attributes, trace context và giao thức OTLP. Java agent, SDK và appender là những thành phần khác nhau. Muốn xuất log qua Collector cần bật **thành phần phát log OTel phù hợp**, không chỉ thêm dependency API mà không cấu hình exporter/instrumentation.

Ví dụ các biến môi trường dành cho runtime **đã có OpenTelemetry Java instrumentation hoặc SDK autoconfigure phù hợp**:

```dotenv
OTEL_SERVICE_NAME=orders-api
OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=prod,service.version=1.0.0
OTEL_LOGS_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Các dòng trên không phải file mà JVM tự động nạp; môi trường chạy phải đưa biến vào process và thư viện/agent phải hỗ trợ chúng. `4318` thường là cổng OTLP/HTTP, trong khi `4317` thường dùng cho OTLP/gRPC; protocol và endpoint phải khớp receiver đã mở. Trong production, dùng TLS/xác thực thích hợp, nhất là khi dữ liệu đi qua mạng không đáng tin cậy.

Collector có thể batch, retry, enrich resource, filter/redact và route. Không phải bản phân phối Collector nào cũng có mọi processor/exporter; phụ thuộc phiên bản và distribution. Queue, buffer và retry phải có giới hạn; nếu downstream không sẵn sàng lâu, không thể giả định Collector giữ dữ liệu vô hạn.

Nếu cùng event được xuất qua OTLP và bị thu từ stdout, có thể xảy ra duplicate ingestion. Kiểm tra toàn tuyến trước khi bật hai đường xuất đồng thời.

## 10. Gắn với từng cloud backend

| Backend | Thành phần cần xác định | Kiểm chứng |
| --- | --- | --- |
| **AWS CloudWatch Logs** | Account/region, log group và stream, quyền IAM, agent hoặc integration | Log vào đúng group/region và retention phù hợp |
| **Google Cloud Logging** | Project, monitored resource, log name, structured payload và quyền | Severity, trace mapping và resource được nhận dạng đúng |
| **Azure Monitor Logs** | Workspace/table, data collection/integration và quyền truy cập | Đúng workspace/schema và retention |
| **OpenSearch/Elasticsearch/Loki/SaaS** | Index/dataset/tenant, auth, quota, schema và retention | Không mất event, query theo service/trace và chi phí trong giới hạn |

Các mục trên là **khái niệm cấu hình**, không phải lệnh API cố định áp dụng cho mọi phiên bản cloud. Nhà cung cấp khác nhau về cách thu stdout, cách parse JSON, định dạng trường trace, giới hạn và phí. Khi triển khai phải kiểm thử theo đúng runtime, tài khoản, vùng và phiên bản dịch vụ hiện dùng.

## 11. Bảo mật, retention và chi phí

Log tập trung có thể chứa dữ liệu của nhiều khách hàng. Quy tắc quan trọng nhất là **không phát dữ liệu không cần thiết từ ứng dụng**. Redaction ở Collector là lớp bổ sung vì dữ liệu có thể đã rời JVM hoặc nằm trong buffer trước khi được lọc.

- Không log mật khẩu, session cookie, access token, private key, connection string có secret, dữ liệu thanh toán nhạy cảm hoặc payload cá nhân không cần thiết. Kiểm tra cả exception text, URL query, HTTP headers và MDC/baggage.
- Dùng workload identity/service account/managed identity hoặc cơ chế tương đương; phân tách quyền **ghi** log với quyền **đọc/xuất/xóa** log; cấp quyền tối thiểu đúng phạm vi.
- Bảo vệ đường truyền bằng TLS và giới hạn mạng phù hợp. Tách quyền production khỏi non-production bằng IAM/RBAC thật, không chỉ dựa vào trường `environment`.
- Xác định retention, vùng lưu dữ liệu, data residency, quy trình xóa và audit truy cập; retention của file local, agent spool và cloud backend là các lớp khác nhau.
- Theo dõi ingest bytes/events, indexed fields, retention cost, storage và query cost. Tránh index mọi trường thay đổi liên tục nếu backend không cần; đặc biệt không dùng trace/request ID làm metric label có cardinality quá cao.
- Nếu log INFO lặp quá nhiều, cân nhắc sampling/aggregation theo request hoặc loại sự kiện, nhưng giữ đủ lỗi nghiêm trọng và các luồng audit bắt buộc theo policy.

Pipeline logging cũng tiêu thụ CPU, heap, network và I/O. Async appender với queue có thể giảm thời gian chờ của request, nhưng khi đầy queue hệ thống phải theo một chính sách block/drop/retry. Cần biết sự kiện nào được phép bỏ và đo dropped records; không tuyên bố **exactly-once** khi pipeline chỉ có retry at-least-once hay cơ chế chuyển không bảo đảm.

## 12. Chẩn đoán và kiểm thử end-to-end

Một phép thử hoàn chỉnh phải chứng minh log **đã tới backend cloud** theo schema mong đợi:

1. Phát một event thử với `service.name`, environment, `event.name=cloud.logging.probe`, request ID và timestamp rõ ràng; không chứa dữ liệu nhạy cảm.
2. Xác nhận event có cấu trúc JSON hợp lệ ở đầu ra logger hoặc exporter; exception/newline không bị tách sai thành nhiều dòng.
3. Xác nhận runtime/agent/Collector đang thu đúng source, parse đúng fields, không có exporter errors hay permission errors.
4. Truy vấn cloud backend trong khoảng thời gian tương ứng; xác nhận severity, metadata, request/trace ID, sự kiện xuất hiện đúng số lần và không bị route sang project/workspace khác.
5. Tạo burst log, restart container, lỗi endpoint tạm thời và thay đổi mức log; kiểm tra queue/drop/retry, thời gian ingest và behavior của shutdown/flush.
6. Đối chiếu IAM/RBAC, retention, region và dashboard cảnh báo ingest failures. Kiểm tra metrics độc lập nếu log đã sampling.

Bảng lỗi thường gặp:

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `kubectl logs` thấy log, backend cloud không thấy | Agent không thu, endpoint/quyền sai hoặc route sai | Kiểm agent health, Collector errors, đích project/region |
| Log vào backend nhưng thiếu JSON fields | Console đang in text hoặc parser chưa nhận JSON | Kiểm raw output, encoder và JSON parsing |
| Stack trace bị tách thành nhiều event | Log nhiều dòng nhưng collector theo dòng | Dùng JSON Lines có escape hoặc multiline parser phù hợp |
| Log bị nhân đôi | Hai appender/pipeline cùng gửi một event | Sơ đồ hóa tuyến dữ liệu và bỏ route trùng |
| Không có trace link | Thiếu context propagation hoặc backend cần field khác | Kiểm trace ID, span ID và mapping theo backend |
| Severity sai | Mapping level hoặc stdout/stderr không đúng | Kiểm raw severity và quy tắc ingest của nền tảng |
| Production mất log, local vẫn chạy | File cấu hình/provider không được đóng gói hoặc thiếu env | Kiểm artifact, cách khởi chạy và startup diagnostics |
| Log đến chậm/mất khi tải cao | Queue đầy, rate limit, parser lỗi, network/retry thất bại | Theo dõi backlog, dropped records, throttling và tăng độ bền theo yêu cầu |
| Hóa đơn log tăng cao | DEBUG rộng, payload lớn, retention/index quá dài | Đo volume theo service/level, điều chỉnh sampling/retention |
| Log chứa bí mật | Payload, exception hoặc MDC chưa được làm sạch | Ngăn phát từ nguồn, redact và xử lý dữ liệu đã lộ theo policy |

**Các lỗi nhận thức cần tránh:** nhìn thấy stdout rồi kết luận cloud đã ingest; nghĩ `LOG_LEVEL` luôn được Java nhận; gắn `trace_id` là đã có trace link; cho rằng mọi queue async giữ mọi log; xem `kubectl logs` như hệ thống retention; hoặc dựa vào log đã sampling để tính traffic/error rate chính xác.

**Ghi nhớ:** cấu hình cloud logging cho Java bao gồm **định dạng và level tại ứng dụng**, **vận chuyển qua runtime/agent/Collector**, và **quyền truy cập, retention, truy vấn tại backend cloud**. Một pipeline tốt chỉ được xác nhận khi sự kiện ở đích cuối có đúng nội dung, ngữ cảnh, quyền và thời hạn lưu theo chính sách.
