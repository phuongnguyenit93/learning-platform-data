# Log aggregation trong Java: thu gom, chuẩn hóa và truy vấn log tập trung

## 1. Log aggregation là gì?

**Log aggregation** là quá trình **thu thập các bản ghi log từ nhiều tiến trình, máy chủ, container và dịch vụ**, chuẩn hóa chúng thành dữ liệu có thể tìm kiếm, chuyển qua pipeline đáng quan sát và lưu tại một hoặc nhiều hệ thống tập trung. Mục tiêu không chỉ là gom text vào một file lớn, mà là trả lời được: *Yêu cầu nào thất bại? Dịch vụ nào liên quan? Các sự kiện xảy ra theo trình tự nào? Có log bị mất, trùng hoặc chứa dữ liệu không được phép không?*

Trong một ứng dụng Java nhỏ chạy trên máy cá nhân, có thể xem log trực tiếp từ console hoặc một file. Khi hệ thống gồm nhiều instance, microservices, Kubernetes pods, scheduled jobs hoặc message consumers, cách đó không còn đủ:

- Một lỗi có thể trải qua HTTP gateway → Java service → queue → worker → database.
- Instance có thể tự động scale hoặc restart, làm log cục bộ không còn sẵn.
- Mỗi service có thể dùng JUL, SLF4J/Logback, Log4j 2 hay thư viện khác.
- Có dịch vụ dùng stdout/stderr, dịch vụ dùng file hoặc gửi telemetry trực tiếp.
- Truy vấn cần lọc theo `service.name`, `environment`, `trace_id`, `event.code`, level và khoảng thời gian.

**Aggregation khác với logging API.** JUL/SLF4J/Log4j 2 giúp phát sự kiện; shipper/agent/Collector giúp vận chuyển và biến đổi; index/storage/search giúp lưu và truy vấn. Một lời gọi `log.info(...)` **không tự chứng minh** event đã vào kho tập trung.

Bài này tập trung vào thiết kế và kiểm thử **đường đi của log Java đến hệ thống aggregation**, không chọn một nhà cung cấp cụ thể làm đáp án duy nhất.

## 2. Kiến trúc tổng quát và các ranh giới trách nhiệm

~~~text
┌───────────────────────────────────────────────┐
│ Java services / jobs / message consumers      │
│ JUL, SLF4J+Logback, Log4j 2                   │
│ eventCode, severity, timestamp, traceId ...   │
└───────────────────────┬───────────────────────┘
                        │ stdout/stderr, file, OTLP ...
                        ▼
         Container runtime / file / agent
                        │
                        ▼
           Shipper / OpenTelemetry Collector
           ├─ receiver: tail file / OTLP / API
           ├─ parse JSON, multiline, normalize
           ├─ enrich resource/service metadata
           ├─ redact/drop theo policy
           ├─ batch, retry, bounded queue
           └─ exporter: backend / gateway
                        │
                        ▼
              Central log storage
           Index + retention + access control
                        │
                        ▼
           Query, dashboards, alerts, audit
                        │
                        └── liên kết traces/metrics
~~~

**Những câu hỏi riêng ở từng chặng:**

1. *Application:* record có được tạo? Level/filter có cho phép xuất? Body và attributes có an toàn?
2. *Runtime:* byte đã đi đến stdout/file chưa? Container runtime có tiếp nhận không?
3. *Shipper/agent:* đã đọc log line? Parse thành công? File cursor/checkpoint ở đâu?
4. *Collector:* đã xử lý và gửi? Có retry, queue, drop, filter hoặc lỗi exporter?
5. *Backend:* đã nhận? Đã index? Có thể query theo field? Dữ liệu lưu bao lâu?
6. *UI/alert:* quyền truy cập, thời gian query và cảnh báo có đúng nhu cầu?

**Không đồng nhất “đã enqueue” với “đã lưu bền vững”.** Mỗi tầng có buffer, timeout, xác nhận và chính sách lỗi riêng. Trong nhiều đường đi, sau mất mạng có thể có **mất hoặc trùng bản ghi**; mục tiêu phải là một hợp đồng tin cậy rõ ràng, không phải giả định exactly-once.

## 3. Ba kiểu nguồn log Java thường gặp

| Nguồn ứng dụng | Cách gom | Phù hợp | Cần lưu ý |
| --- | --- | --- | --- |
| **stdout/stderr** | Container runtime hoặc systemd/journald ghi, agent theo dõi | Container, Kubernetes, nền tảng cloud-native | Phân biệt log ứng dụng với stderr chẩn đoán, giới hạn kích thước dòng, runtime rotation |
| **File** | Agent tail file, theo dõi vị trí/rotation | VM/bare metal, ứng dụng legacy, yêu cầu file nội bộ | Path/quyền, disk full, inode, copytruncate/rename rotation, multiline |
| **OTLP/direct export** | SDK/bridge/exporter → OTLP receiver hoặc logging service | Dự án có OpenTelemetry và tracing/metrics cùng hệ | Batch/queue/timeout, mạng, TLS/auth, tính tương thích và lifecycle exporter |
| **Syslog/legacy endpoint** | Receiver/forwarder nhận rồi normalize | Nền tảng cũ, thiết bị và ứng dụng hỗn hợp | Cấu trúc trường, timezone, framing, độ tin cậy transport |

**Chọn một đường mặc định rõ ràng cho mỗi nhóm ứng dụng.** Nếu vừa ship file vừa ship stdout có cùng nội dung, một event có thể bị thu gom **hai lần**. Nếu còn một kênh audit riêng, cần định danh và policy độc lập thay vì gộp lẫn tất cả log.

Với container Java, **stdout/stderr + agent theo node** thường là điểm bắt đầu đơn giản. Với ứng dụng cần thuộc tính dữ liệu chuẩn hóa theo OpenTelemetry, một bridge/exporter OTLP có thể phù hợp; cần tránh cấu hình gửi trùng qua cả hai đường.

## 4. Dữ liệu log tốt phải có cấu trúc trước khi aggregation

Một chuỗi như:

~~~text
Something failed for order 42
~~~

khó tìm hơn event có trường ổn định. Khi không có cấu trúc, collector phải dùng regex để đoán dữ liệu, dễ sai khi thay đổi message hoặc có ký tự lạ.

Ví dụ JSON Lines một record trên mỗi dòng:

~~~json
{"timestamp":"2026-11-10T02:00:00Z","service.name":"checkout-service","severity":"INFO","event.code":"ORDER_ACCEPTED","trace_id":"0123456789abcdef0123456789abcdef","order_ref":"ord-42","outcome":"SUCCESS","body":"order accepted"}
~~~

Đây là schema minh họa. Dùng JSONL/NDJSON có ích vì **mỗi dòng vật lý là một đối tượng JSON hoàn chỉnh**, kể cả khi `body` chứa newline đã escape. Nhưng **“JSON text” không tự biến thành OpenTelemetry Logs Data Model hoặc OTLP**: collector phải parse và mapping các field vào dữ liệu đích theo contract.

Lợi ích:

- Query `service.name = checkout-service AND event.code = ORDER_ACCEPTED`.
- Đếm `outcome` theo môi trường, service hoặc khoảng thời gian.
- Liên kết với trace qua `trace_id` (nếu có).
- Áp policy giữ/xóa/mask field nhất quán.
- Định dạng tồn tại độc lập với câu message dành cho con người.

Đừng tự động serialize mọi DTO hoặc raw exception vào JSON: việc “đã có schema” không ngăn bí mật hoặc PII đi vào log.

## 5. Schema thực tế: trường nào cần, trường nào chỉ tùy chọn?

| Field/nhóm | Ý nghĩa | Gợi ý |
| --- | --- | --- |
| `timestamp` | Thời điểm sự kiện thực sự xảy ra | UTC, ISO 8601/RFC 3339, không dựa vào timezone mặc định |
| `observedTimestamp` | Thời điểm Collector nhận/quan sát | Giữ riêng khi cần chẩn đoán độ trễ shipper |
| `service.name` | Tên workload/dịch vụ | Tên ổn định qua pod/instance |
| `service.version` | Phiên bản release | Hữu ích khi so sự cố sau deploy |
| `deployment.environment.name` hoặc tương đương | Prod/staging/dev | Tránh trộn môi trường |
| `severity`/`severityText` | Mức log | Chuẩn hóa JUL WARNING ↔ WARN ở backend, không xóa raw level nếu cần |
| `logger` | Nguồn phát trong code | Có thể là package/class/logger category |
| `event.code` | Định danh sự kiện ổn định | Enum/allowlist như `PAYMENT_RETRY` |
| `body` | Thông điệp người đọc | Nội dung đã kiểm soát, không chứa secret |
| `trace_id` / `span_id` | Liên kết request/span | Dùng format đúng hệ tracing, không tự là định danh user |
| `request_id` / `message_id` | Correlation nghiệp vụ/vận chuyển | Phân biệt request ID và business event ID |
| `outcome` / `reason_code` | Kết quả và nguyên nhân phân loại | Không chứa raw exception message |
| `host.name`, `k8s.pod.name`, `container.id` | Metadata hạ tầng | Agent/collector thường bổ sung tốt hơn ứng dụng |
| `tenant_ref` / `user_ref` | Truy vết có kiểm soát | Chỉ khi policy cho phép; hạn chế dữ liệu cá nhân |
| `schemaVersion` | Phiên bản schema log do dự án định nghĩa | Cần khi có downstream parser hoặc pipeline migration |

**Tránh biến `trace_id`, `order_ref` hoặc message ID thành labels của hệ metric**: giá trị có cardinality rất cao. Trong kho log, chỉ lập index những field thực sự cần query; giá thành lưu/truy vấn tùy backend.

**Đừng dùng tên field “chuẩn” tùy tiện.** Ví dụ `service.name` là semantic convention trong OpenTelemetry, nhưng JSON schema tùy chỉnh chỉ đơn giản có một key mang tên đó. Muốn chuyển đúng mô hình OpenTelemetry, cần map sang **Resource attributes** thay vì chỉ giữ nó trong `Body`.

## 6. Cơ chế timestamp, severity và thứ tự event

### Timestamp do producer tạo và thời điểm collector nhìn thấy

- **Event time:** timestamp do JVM tạo lúc phát sự kiện.
- **Observed/ingest time:** timestamp khi agent/collector nhận.
- **Indexed time:** thời điểm backend sẵn sàng query, có thể muộn hơn.

Nếu clock JVM lệch hoặc network chậm, event có thể đến kho **không đúng thứ tự thời gian sự kiện**. Một aggregation pipeline không thể bảo đảm ordering toàn cục giữa nhiều thread, service và region nếu không có thiết kế riêng.

Đối với duration, đo bằng `System.nanoTime()` hoặc API monotonic clock thích hợp; không lấy hiệu hai timestamp từ hai máy khác nhau để khẳng định latency chính xác khi clock có thể lệch.

### Mapping severity

| JUL | Ý nghĩa gần đúng | Hệ thống khác thường dùng |
| --- | --- | --- |
| `SEVERE` | Lỗi nghiêm trọng | ERROR |
| `WARNING` | Cảnh báo | WARN |
| `INFO` | Thông tin | INFO |
| `CONFIG` | Thông tin cấu hình | Không có mapping 1:1 phổ quát |
| `FINE` | Chẩn đoán | DEBUG |
| `FINER` / `FINEST` | Chẩn đoán chi tiết | TRACE |

OpenTelemetry có `SeverityText` và `SeverityNumber`, không chỉ có một chuỗi `severity`. Mapping nên do bridge/collector thực hiện theo API và version; không ép tất cả các backend dùng cùng bảng bằng thay thế text đơn giản.

## 7. Ví dụ Java 17 độc lập: JSON Lines trên stdout

Để minh họa cấu trúc log dễ aggregation, chương trình sau chỉ dùng **JDK 17**, không cần thư viện ngoài. Nó:

1. Dùng JUL `Logger` và `Handler` tùy biến để xuất JSONL ra stdout.
2. Gắn `timestamp`, service, severity, tên logger, event code, trace ID, order reference, outcome và body.
3. Escape `"`, dấu backslash, newline, tab, CR và các control characters để **một event không bẻ thành nhiều dòng vật lý**.
4. Chỉ truyền dữ liệu an toàn ở `SafeEvent`; không đưa secret giả vào log.
5. Dùng timestamp **cố định** cho kết quả kiểm thử chính xác; trong ứng dụng thật tạo event time lúc log được phát, không hard-code.
6. Không tự gửi OTLP hoặc kết nối kho log; đây chỉ là **nguồn JSONL**, để agent có thể ship/parse.

Tạo tệp **LogAggregationDemo.java**:

~~~java
import java.time.Instant;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogAggregationDemo {
    private static final Logger LOG = Logger.getLogger("demo.aggregation");

    record SafeEvent(String eventCode, String traceId,
                     String orderRef, String outcome) {}

    static final class JsonFormatter extends Formatter {
        private static void field(StringBuilder out, String key, String value,
                                  boolean comma) {
            if (comma) out.append(',');
            quote(out, key);
            out.append(':');
            quote(out, value);
        }

        private static void quote(StringBuilder out, String input) {
            out.append('"');
            for (int i = 0; i < input.length(); i++) {
                char c = input.charAt(i);
                switch (c) {
                    case '"': out.append("\\\""); break;
                    case '\\': out.append("\\\\"); break;
                    case '\n': out.append("\\n"); break;
                    case '\r': out.append("\\r"); break;
                    case '\t': out.append("\\t"); break;
                    default:
                        if (c < 0x20) {
                            out.append(String.format("\\u%04x", (int)c));
                        } else {
                            out.append(c);
                        }
                }
            }
            out.append('"');
        }

        @Override
        public String format(LogRecord record) {
            Object[] parameters = record.getParameters();
            if (parameters == null || parameters.length != 1 ||
                    !(parameters[0] instanceof SafeEvent)) {
                throw new IllegalArgumentException("SafeEvent required");
            }
            SafeEvent data = (SafeEvent) parameters[0];
            StringBuilder out = new StringBuilder(256);
            out.append('{');
            field(out, "timestamp", record.getInstant().toString(), false);
            field(out, "service.name", "checkout-service", true);
            field(out, "severity", record.getLevel().getName(), true);
            field(out, "logger", record.getLoggerName(), true);
            field(out, "event.code", data.eventCode(), true);
            field(out, "trace_id", data.traceId(), true);
            field(out, "order_ref", data.orderRef(), true);
            field(out, "outcome", data.outcome(), true);
            field(out, "body", record.getMessage(), true);
            out.append('}').append(System.lineSeparator());
            return out.toString();
        }
    }

    static final class StdoutHandler extends Handler {
        StdoutHandler() {
            setLevel(Level.ALL);
            setFormatter(new JsonFormatter());
        }
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.print(getFormatter().format(record));
            }
        }
        @Override public void flush() { System.out.flush(); }
        @Override public void close() { flush(); }
    }

    private static void emit(Level level, String body,
                             SafeEvent safe, Instant time) {
        LogRecord record = new LogRecord(level, body);
        record.setLoggerName(LOG.getName());
        record.setInstant(time);
        record.setParameters(new Object[]{safe});
        LOG.log(record);
    }

    public static void main(String[] args) {
        Handler handler = new StdoutHandler();
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(handler);
        try {
            String sensitive = "TEST_SECRET_DO_NOT_LOG";
            boolean credentialPresent = !sensitive.isEmpty();
            if (!credentialPresent) throw new IllegalStateException();
            String trace = "0123456789abcdef0123456789abcdef";
            emit(Level.INFO, "order accepted",
                    new SafeEvent("ORDER_ACCEPTED", trace, "ord-42",
                            "SUCCESS"), Instant.parse("2026-11-10T02:00:00Z"));
            emit(Level.WARNING, "provider said \"retry\"\nrequest queued",
                    new SafeEvent("PAYMENT_RETRY", trace, "ord-42",
                            "PENDING"), Instant.parse("2026-11-10T02:00:01Z"));
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 LogAggregationDemo.java
java LogAggregationDemo
~~~

**Standard output (stdout) chính xác** ở môi trường UTF-8/JDK bình thường:

~~~json
{"timestamp":"2026-11-10T02:00:00Z","service.name":"checkout-service","severity":"INFO","logger":"demo.aggregation","event.code":"ORDER_ACCEPTED","trace_id":"0123456789abcdef0123456789abcdef","order_ref":"ord-42","outcome":"SUCCESS","body":"order accepted"}
{"timestamp":"2026-11-10T02:00:01Z","service.name":"checkout-service","severity":"WARNING","logger":"demo.aggregation","event.code":"PAYMENT_RETRY","trace_id":"0123456789abcdef0123456789abcdef","order_ref":"ord-42","outcome":"PENDING","body":"provider said \"retry\"\nrequest queued"}
~~~

**Standard error (stderr):** trống, **exit code:** `0`.

Lưu ý: hai dòng trên chứa ký tự **backslash-n** trong chuỗi JSON thứ hai; chúng không có newline vật lý bên trong body. Khi một JSON parser giải mã `body`, giá trị sẽ có một newline thật.

### 7.1. Phân tích cơ chế

- `LOG.setUseParentHandlers(false)` ngăn root logger viết thêm bản sao log định dạng khác.
- `StdoutHandler.publish` gọi formatter rồi ghi `System.out`. Đây là handler **để học**, không có hàng đợi, bộ đệm thông minh, xử lý lỗi I/O hay batch exporter.
- `JsonFormatter.quote` escape những ký tự JSON cơ bản. Với dữ liệu Unicode phức tạp và production, **dùng JSON encoder được bảo trì** thay vì tự viết serializer.
- `SafeEvent` dùng các field đã được lựa chọn có chủ đích. `LogRecord.getParameters()` ở đây được dùng như cách chuyên biệt để truyền data vào demo; nó **không phải cơ chế structured attributes chuẩn của JUL**.
- `record.getInstant()` là event time; timestamp cố định chỉ giúp output so khớp được trong test.
- `sensitive` không đi vào `SafeEvent`, body hay parameters; chỉ dùng để minh họa việc có dữ liệu bí mật trong scope ứng dụng **không đồng nghĩa phải ghi nó vào log**.

Đừng áp dụng nguyên xi `StdoutHandler` và `JsonFormatter` này làm logging framework production: cần cân nhắc backend giàu tính năng hơn, batching, error handling, đồng bộ giữa threads, sampling, exception rendering, escaping Unicode, masking và chính sách rollover/collector.

## 8. Kiểm thử JSONL trước khi nối vào aggregator

Có thể chuyển stdout của demo sang file thử nghiệm và parse **từng dòng**:

~~~bash
java LogAggregationDemo > app.jsonl
~~~

Kiểm tra nên xác nhận:

1. File có đúng **hai dòng vật lý**, mỗi dòng parse thành một JSON object.
2. `event.code` lần lượt là `ORDER_ACCEPTED` và `PAYMENT_RETRY`.
3. `timestamp` hợp lệ, level lần lượt `INFO`/`WARNING`.
4. `trace_id` nhất quán giữa các event cùng request.
5. `body` của dòng hai khi parse có dấu ngoặc kép và newline, nhưng file không bị tách thành dòng thứ ba.
6. Không có sentinel `TEST_SECRET_DO_NOT_LOG` trong **bất kỳ dòng nào**.
7. Không có các field raw như `password`, `access_token`, `Authorization` hoặc toàn bộ payload.
8. Nếu export qua collector, field types và mapping sang backend được xác nhận sau khi ingest.

Một dòng JSONL parse được **không** chứng minh nó đã được ship hoặc index. Hãy test từng ranh giới. Trong CI, kiểm tra cả dòng log của collector khi cấu hình sai và phản ứng lúc downstream không sẵn sàng.

## 9. Logback và Log4j 2: dùng encoder/layout phù hợp

Ứng dụng Java phổ biến thường gọi logging qua **SLF4J**, sau đó dùng Logback Classic hoặc một provider/bridge sang Log4j 2 để ghi ra đích.

**SLF4J application call:**

~~~java
// Minh họa cần SLF4J và các biến an toàn đã được tạo.
LOG.info("orderRef={} outcome={} traceId={}",
        safeOrderRef, "SUCCESS", traceId);
~~~

Parameterized logging giúp trì hoãn format khi level bị tắt; **nó không tự sinh JSON object có field tên `orderRef`**. Muốn kho log query được field riêng, dùng structured key-value (SLF4J 2.x fluent), MDC có kiểm soát hoặc encoder/layout JSON đúng schema.

**Logback ConsoleAppender dạng text đơn giản:**

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Cấu hình này cần Logback Classic tương thích. Nó in **text** chứ không phải JSONL; collector muốn query theo trường sẽ phải parse hoặc thêm JSON encoder. Nếu chọn JSON encoder của Logback ecosystem, cần kiểm tra version, phụ thuộc, cách xuất stack trace và MDC; không mặc định cứ bật encoder JSON là không rò dữ liệu.

**Log4j 2 PatternLayout text:**

~~~xml
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Nếu dùng Log4j 2 **JSON Template Layout**, xây template schema và kiểm tra layout/encoder output cùng dependency tương ứng `log4j-layout-template-json`. Không ghép JSON bằng `String.format` ở mỗi chỗ log để tạo schema tùy hứng; tránh duplicate escaping/thiếu field.

**Tách kênh khi cần:** console stdout cho app logs, sink riêng cho audit/security nếu yêu cầu khác về retention và tính toàn vẹn. Đừng ship một nguồn hai lần qua stdout **và** file rồi nhận lại duplicate.

## 10. Kubernetes: stdout/stderr, node agent và log rotation

Kubernetes khuyến nghị ứng dụng container thường ghi log ra **stdout/stderr**. Container runtime ghi lại stream này theo cơ chế phù hợp, kubelet cho phép lấy một phần qua `kubectl logs`. Tuy nhiên **Kubernetes không cung cấp sẵn một kho lưu và truy vấn log tập trung cho toàn cluster**; cần backend aggregation riêng.

~~~text
Java container stdout/stderr
   -> container runtime / CRI log file trên node
   -> DaemonSet agent tail/parse logs
   -> gateway/Collector
   -> durable backend/index
   -> search/dashboards
~~~

Theo mô hình phổ biến, node-level agent có thể là một **DaemonSet** đọc log của tất cả pods trên node. Một phương án khác là sidecar đọc file của ứng dụng hoặc app gửi trực tiếp tới backend. Mỗi phương án có chi phí và độ phức tạp khác nhau.

**Điểm dễ nhầm:**

- `kubectl logs` rất hữu ích để debug nhưng **không thay thế retention/search tập trung**.
- Pod bị xóa, node hỏng hay container log bị xoay có thể khiến dữ liệu không còn trên node.
- Runtime tạo các dòng theo **CRI format** với metadata stream/timestamp; một agent phải bóc lớp này **trước hoặc trong quá trình parse JSON của ứng dụng**.
- Log có thể bị tách thành **partial records** khi quá dài; collector/agent cần hỗ trợ ghép/giới hạn phù hợp.
- Kubelet có cơ chế **container log rotation**, nên việc agent đọc file phải theo inode/path/checkpoint, tránh đọc trùng hoặc bỏ sót khi rename/truncate.
- Một container có thể viết ra stdout và stderr; aggregation schema nên giữ nguồn stream nếu có ích nhưng không coi `stderr` đồng nghĩa với ERROR trong mọi thư viện.

Nếu còn các service ghi file nội bộ trong container, phải chọn đường ship riêng và tránh vô tình mất log khi container bị thay thế.

## 11. Shipper, Collector, gateway và backend khác nhau

| Thành phần | Vai trò | Ví dụ phổ biến |
| --- | --- | --- |
| **Node agent / shipper** | Đọc file/stdout/CRI, thêm metadata, gửi tiếp | Fluent Bit, Vector, Filebeat, OpenTelemetry Collector với receiver phù hợp |
| **Collector/processor** | Nhận dữ liệu, batch, transform, redact, route, retry | OpenTelemetry Collector, một pipeline ingest chuyên dụng |
| **Gateway** | Điểm tập trung nhận telemetry từ nhiều agents/services | Collector gateway được scale ngang |
| **Transport buffer** | Giảm mất lúc backend chậm, chuyển tải giữa vùng | Queue/broker bền vững khi phù hợp |
| **Log backend** | Lưu trữ, index, retention, tìm kiếm và dashboard | Elasticsearch/OpenSearch, Loki, dịch vụ log cloud |
| **Alert/incident platform** | Biến event tổng hợp thành cảnh báo và workflow | Alert rule, notification, incident management |

Không có “stack tốt nhất cho mọi dự án”. Lựa chọn phụ thuộc throughput, chi phí index, mô hình truy vấn, đa tenant, yêu cầu compliance, hệ sinh thái sẵn có và kỹ năng vận hành.

Một logger Java có thể chỉ cần ghi stdout đúng schema, còn agent/Collector/Backend được nhóm nền tảng vận hành. Khi nhiều đội cùng phụ trách, hãy có **hợp đồng schema, ownership và SLO của pipeline**; nếu không mỗi bên tưởng đã hoàn thành trách nhiệm khi chuyển dữ liệu sang chặng tiếp theo.

## 12. OpenTelemetry Logs Data Model và OTLP

OpenTelemetry định nghĩa **mô hình log record** có các trường:

- `Timestamp` và `ObservedTimestamp`.
- `SeverityText` và `SeverityNumber`.
- `Body`.
- `Resource` (ví dụ `service.name`, metadata triển khai).
- `Attributes`, `InstrumentationScope`.
- `TraceId`, `SpanId` và trace flags khi có.
- `EventName` ở những sự kiện có tên.

Đây là **mô hình dữ liệu**, không phải cam kết mọi JSON object có tên key tương tự sẽ tự được hiểu là OTLP.

~~~text
JSONL trong stdout (bài demo)
       │
       ▼
filelog receiver / agent parse JSON
       │
       ▼
Map timestamp, level, body, trace_id, service.name...
       │
       ▼
OpenTelemetry LogRecord data model
       │
       ▼
OTLP exporter / backend
~~~

Một đường khác:

~~~text
Java app + SDK/bridge/exporter đã cấu hình
       │
       ▼
OTLP/gRPC hoặc OTLP/HTTP
       │
       ▼
OpenTelemetry Collector OTLP receiver
       │
       ▼
Backend
~~~

**Không kết nối nhầm:** Collector `otlp` receiver **không tự tail stdout JSONL** của ví dụ Java ở mục 7. Muốn dùng stdout cần runtime/agent/filelog receiver; muốn dùng OTLP receiver thì ứng dụng hoặc agent phải gửi **payload theo giao thức OTLP**.

OpenTelemetry còn có Java logging bridges/instrumentation tùy framework và phiên bản. Hãy xác minh library đang dùng, ngữ nghĩa truyền context và exporter trước khi định tuyến cùng event qua hai đường (có thể tạo duplicate).

## 13. Ví dụ Collector cấu hình OTLP để kiểm tra pipeline

Ví dụ **otel-collector.yaml** dưới đây là pipeline **test OTLP logs**, không phải cấu hình đọc stdout JSONL của bài demo. Cần phiên bản Collector có `otlp` receiver, `batch` processor và `debug` exporter. Chỉ bind loopback trong môi trường phát triển:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 256

exporters:
  debug:
    verbosity: normal

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

**Diễn giải:**

- Receiver nhận log **theo OTLP**, không nhận raw `System.out.println(...)`.
- Batch có thể gom log cho hiệu quả, nhưng khi process chết đột ngột, event còn trong RAM vẫn có thể mất.
- Debug exporter dành cho kiểm tra đường đi; **không dùng làm kho lưu production**.
- Trong Kubernetes, `127.0.0.1` chỉ nhận kết nối trong network namespace tương ứng. Nếu ứng dụng ở pod khác, cần endpoint accessible và kiểm soát TLS/auth/network policy; **không tự đổi thành `0.0.0.0` công khai mà không bảo vệ**.
- Để nhận file/CRI, dùng **filelog receiver** ở distribution có component đó (thường Collector Contrib), xử lý parsing, partial records và metadata theo cách runtime ghi file; đó là **một pipeline khác**.
- Component chỉ được kích hoạt khi được liệt kê trong `service.pipelines.logs`. Một receiver khai báo nhưng không có trong pipeline sẽ không nhận dữ liệu cho luồng đã định.

Kiểm tra trước khi triển khai: Collector binary/distribution có các component này không, version config có tương thích không, mạng/TLS/credentials có đúng không và backend thật có ACK theo yêu cầu không.

## 14. Parsing, multiline và log event boundary

Một vấn đề phổ biến là **stack trace nhiều dòng**:

~~~text
ERROR payment failed
java.lang.IllegalStateException: invalid state
    at com.example.PaymentService.process(PaymentService.java:42)
    at ...
~~~

Nếu agent coi mỗi dòng vật lý là một event độc lập, phần stack trace mất level/timestamp và khó tìm cùng lỗi. Có các hướng:

1. **JSONL:** encode body/exception thành field JSON có newline escaped, mỗi event vẫn nằm trên một dòng vật lý.
2. **Multiline parser:** khi không thể đổi nguồn text, agent ghép dựa vào timestamp/pattern bắt đầu event, với timeout và giới hạn kích thước.
3. **OTLP/native structured:** truyền exception type/message/stack trace dưới dạng attributes/body theo schema phù hợp; không buộc parser đoán event boundary từ newline.

Multiline parser cũng có rủi ro:

- Ghép nhầm dòng của hai sự kiện nếu nhiều threads ghi interleaved.
- Giữ quá nhiều bytes trong RAM khi stack trace dài.
- Hết thời hạn ghép làm mất/tách event.
- Regex nhận diện timestamp bị sai khi locale thay đổi.
- Input độc hại chứa newline giả hoặc header giả.

Nếu có quyền thay logger Java, **định dạng một JSON object trên mỗi dòng và dùng encoder chuẩn** thường đơn giản hơn việc khôi phục cấu trúc từ text nhiều dòng. Test cả CRLF/LF, Unicode, dấu quote và dữ liệu lớn.

## 15. Enrichment và semantic metadata: thêm ở nơi đúng

Một số metadata thuộc về ứng dụng:

- `event.code`, `operation`, `outcome`, reason code.
- `request_id`, `message_id`, `trace_id` khi có context.
- Tham chiếu nghiệp vụ an toàn, không phải raw entity.

Một số metadata thuộc về môi trường triển khai:

- `k8s.namespace.name`, `k8s.pod.name`, `k8s.container.name`.
- `host.name`, `cloud.region`, `deployment.environment.name`.
- Collector instance hoặc đường ingest khi cần troubleshooting.

Agent/Collector có thể thêm metadata hạ tầng đáng tin cậy hơn là mỗi Java app tự lấy hostname/pod name tùy tiện. Tuy nhiên nếu schema hạ tầng sai hoặc pod metadata cũ, sẽ tạo thông tin không khớp; cần kiểm tra enrichment theo UID, instance và thời gian.

**Không tự động coi một field có tên chuẩn là đúng semantic conventions.** Ví dụ `service.name` có thể do resource attributes trong OpenTelemetry truyền qua đường OTLP; với JSONL tùy chỉnh, bạn phải map chính xác. Nếu tên app từ nhiều nơi khác nhau (Spring application name, service name, Kubernetes label), xác định một nguồn ưu tiên và chính sách xung đột.

## 16. Correlation giữa logs, metrics và distributed traces

Aggregation mạnh hơn nhiều khi có thể chuyển từ một log line sang toàn bộ request trace:

~~~text
HTTP request
   trace_id=0123456789abcdef0123456789abcdef
       │
       ├── API service log: REQUEST_ACCEPTED
       │
       ├── Payment service log: PAYMENT_RETRY
       │
       ├── Broker producer log: MESSAGE_ACKED
       │
       └── Consumer log: ORDER_UPDATED
       │
       ▼
Search query: trace_id = ...
       │
       ▼
Pivot to trace/spans + metrics + relevant logs
~~~

Nguyên tắc:

1. Dùng tracing instrumentation hoặc W3C Trace Context phù hợp để tạo/propagate trace IDs; **đừng tự dùng một UUID tùy ý và gọi đó là trace ID chuẩn**.
2. Khi gửi message, đưa context qua headers/envelope theo API và security policy; consumer extract context rõ ràng.
3. Với thread pool, async callbacks, virtual threads hoặc reactive flows, **ThreadLocal/MDC không tự động đi qua mọi ranh giới**. Test propagation, cleanup và scope.
4. Lưu trace ID vào log event/attributes khi có, nhưng không coi trace sampling là đảm bảo retention của log.
5. Không đưa raw user/token/PII vào baggage, MDC hoặc metric labels.
6. Đừng dùng `trace_id` làm partition key/index mọi nơi nếu không thực sự cần; số lượng giá trị lớn có thể làm tăng chi phí.

Nếu log thiếu trace ID, vẫn nên có event ID, service, timestamp và error code để điều tra. Đừng vì tracing instrumentation tạm không có mà dừng toàn bộ logging.

## 17. Buffer, batch, backpressure và chính sách mất log

Aggregation có thể giảm I/O bằng **batch** và hàng đợi:

~~~text
Java log call → appender queue → stdout/file/OTLP
                                  ↓
                               agent queue
                                  ↓
                              collector queue
                                  ↓
                             backend indexing
~~~

Mỗi queue có mức bảo đảm khác:

| Tình huống | Hậu quả khả dĩ | Cách ứng phó |
| --- | --- | --- |
| Backend chậm | Collector queue tăng, latency tăng | Batch có giới hạn, backpressure, tăng throughput |
| Backend lỗi vài phút | Retry tăng, queue đầy | Durable queue nếu được hỗ trợ, cảnh báo backlog, giới hạn retry |
| Application log nhanh hơn stdout/file sink | Appender queue và runtime buffer tăng | Rate limit debug, kiểm soát lượng event, monitor discard |
| Container bị SIGKILL | Dữ liệu còn trong process queue mất | Không dựa vào memory-only queue cho audit bắt buộc |
| Agent/node restart | Cursor/checkpoint hoặc buffer chưa bền vững | Checkpoint được quản lý, queue bền vững khi cần |
| Mạng trả lỗi/ACK không rõ | Có thể retry và tạo duplicate | Event ID, dedup theo nhu cầu |
| Disk full | Agent không giữ thêm dữ liệu | Disk quota, retention, health alert |
| Parser reject | Record bị drop/quarantine | Dead-letter/quarantine có kiểm soát, metric parse error |

**Batch size/timeout** là đánh đổi giữa throughput, memory và latency. **Retry** cải thiện khả năng chịu lỗi ngắn hạn nhưng không tạo vô hạn bộ đệm: cuối cùng disk/queue vẫn có giới hạn. **Backpressure** có thể bảo vệ pipeline khỏi mất dữ liệu bằng cách làm chậm nguồn, nhưng cũng có thể ảnh hưởng latency của business request.

Chọn chính sách theo event class: debug có thể sampling, audit quan trọng có thể cần durable outbox/store khác, không nên dựa vào aggregator best-effort để đảm bảo lịch sử nghiệp vụ.

## 18. Delivery semantics: at-most-once, at-least-once và duplicate

Một câu thường gặp là “đã thu gom log rồi thì chắc chắn không mất và không trùng”. Điều đó không đúng.

- **At-most-once:** không retry hoặc chấp nhận drop; ít duplicate hơn nhưng có thể mất event.
- **At-least-once:** retry khi không rõ đã nhận; tăng khả năng giao hàng nhưng có thể gửi trùng.
- **Exactly-once end-to-end:** cần phối hợp ứng dụng, transport, store và dedup/transaction; không tự xuất hiện từ một log shipper.

Ví dụ:

~~~text
Agent gửi eventId=EVT-42 -> backend lưu thành công
      │
      └─ ACK bị mất, agent retry eventId=EVT-42
               │
               ▼
          Backend có thể nhận hai bản copy
~~~

Giải pháp có thể là event ID bất biến + dedup theo hợp đồng. Nhưng nhiều log chẩn đoán thông thường không có ID unique; **đừng xóa các dòng giống nhau chỉ bằng body + timestamp** vì hai hành động thực có thể tạo text trùng. Định nghĩa dedup dựa trên event ID hoặc key có cơ sở rõ ràng.

Ordering giữa nhiều host/region/partition không chắc được bảo đảm. Nếu workflow cần phục dựng thứ tự, dùng timestamps đã đồng bộ, sequence number theo phạm vi phù hợp và mốc giao dịch được định nghĩa.

**Aggregation không thay thế transaction outbox** khi phải lưu một business event cùng thay đổi database. Một log line trên stdout không phải bằng chứng event đã được broker hoặc audit store commit.

## 19. Bảo mật: dữ liệu bí mật không được đi vào pipeline

Một kho log tập trung tạo **một nơi chứa dữ liệu từ rất nhiều hệ thống**, nên rủi ro dữ liệu và phân quyền tăng theo quy mô.

Không ghi thô:

- Password, OTP, PIN, bearer/refresh tokens, API keys, cookies, private keys.
- HTTP Authorization header, request/response body chứa PII hoặc thông tin thanh toán.
- JDBC URL chứa credential hoặc SQL bind values nhạy cảm.
- `Throwable.getMessage()`/stack trace khi có thể chứa URL token hay dữ liệu người dùng.
- MDC/baggage/headers không được duyệt hoặc `toString()` của domain object có secret.

**Ưu tiên phòng vệ theo thứ tự:**

1. **Data minimization tại nguồn:** chỉ log các field đã cho phép.
2. **Validation/structured encoding:** event code, reason code từ allowlist, giới hạn độ dài và JSON escape đúng chuẩn.
3. **Redaction/transform ở Collector:** lớp phụ, giúp bắt các mẫu đã biết trước khi export; không thay thế chính sách nguồn.
4. **Transport security:** TLS/mTLS, xác thực exporters/receivers, secret từ secret manager, không hard-code.
5. **Storage security:** RBAC, giới hạn tenant, encryption at rest, audit quyền xem/xuất log.
6. **Lifecycle:** retention, purge/delete phù hợp, policy backup/archive và bản export.

Mask trên dashboard **không xóa** dữ liệu gốc ở index, file, log shipper buffer hoặc backup. Nếu phát hiện secret đã vào log, phải xử lý như một sự cố bảo mật: hạn chế phân phối, xem phạm vi bản sao, thu hồi/rotate credential khi cần và thực hiện quy trình pháp lý/nội bộ áp dụng.

**Multi-tenancy:** một query log sai filter hoặc token quyền quá rộng có thể làm lộ sự kiện tenant khác. Cần phân quyền tại backend và gateway, không chỉ giấu tenant selector trong UI.

## 20. Log injection, dữ liệu lớn và schema evolution

Một user-controlled value có thể chứa:

~~~text
invalid input
ERROR admin authenticated
~~~

Nếu nối trực tiếp vào text log theo dòng, downstream có thể hiểu thành **hai event**. Với JSONL, encoder đúng sẽ escape newline trong giá trị string để không phá ranh giới dòng vật lý; nhưng **JSON escaping không tự loại token hay PII**.

Các guardrail nên có:

- Kiểm soát CR/LF và control chars khi xuất text.
- JSON serializer chuẩn; không ghép raw input vào JSON bằng dấu cộng.
- Giới hạn kích thước field/event và có quy tắc cắt có kiểm soát với marker metadata như `truncated=true` nếu business cho phép.
- Định dạng timestamp/number bất biến theo locale nếu là contract.
- Schema version và khả năng tương thích khi thêm/đổi tên field.
- Hợp đồng chuẩn hóa null/missing/empty: ba trạng thái có thể mang nghĩa khác.
- Test Unicode, emoji, nhiều dòng, quotes, backslash và ngoại lệ có cause.
- Không lưu binary/blob hoặc stack trace không giới hạn vào mỗi event.

**Không lẫn lỗi parser với lỗi ứng dụng.** Nếu sự kiện `ORDER_ACCEPTED` có thật nhưng parser bỏ do dữ liệu quá dài, dashboard có thể cho cảm giác nghiệp vụ không chạy. Pipeline cần metric parse reject/quarantine.

## 21. Retention, indexing và tối ưu chi phí

Log aggregation thường tốn chi phí ở **ingest**, **index**, **storage** và **query**. Không phải mọi field cần lập index hoặc giữ lâu.

Mẫu phân loại:

| Nhóm log | Nhu cầu truy vấn | Chính sách xem xét |
| --- | --- | --- |
| DEBUG/TRACE | Điều tra ngắn hạn, nhiều volume | Có thể sampling, retention ngắn, search theo thời gian/service |
| INFO vận hành | Phân tích hoạt động và incident | Batch, metadata chuẩn, retention theo nhu cầu |
| WARN/ERROR | Điều tra và cảnh báo | Giữ đủ ngữ cảnh, tránh duplicate, truy vấn nhanh |
| Security/audit | Truy vết theo mục đích và quy định | Retention/quyền/integrity riêng, không tự sampling |
| Access logs | HTTP route/status/latency | Không log raw query/cookie, giới hạn cardinality |
| Platform/collector logs | Sức khỏe pipeline | Lưu riêng để điều tra missing logs |

Ví dụ kế hoạch:

- Lưu **hot** log ngắn hạn để query tương tác, **warm/cold** log phục vụ tra cứu hiếm hơn khi có yêu cầu.
- Index `service.name`, severity, event.code, thời gian và một số context đã chấp thuận; tránh lập index mọi JSON key.
- Đo tỷ lệ byte/s, event/s, tỷ lệ nén, index size và query latency trước khi thay policy.
- Không định ra một con số ngày lưu “chuẩn cho mọi tổ chức”; chọn theo risk, policy, hợp đồng, luật áp dụng và quyền riêng tư.

Một backend như Loki, OpenSearch hoặc dịch vụ cloud có chiến lược index khác nhau; cách tối ưu field/cardinality phải dựa trên tài liệu backend thực tế.

## 22. Kiểm thử end-to-end của pipeline aggregation

Unit test Java chỉ chứng minh **source event**. Integration test phải xác minh toàn bộ đường đi đến nơi truy vấn.

| Kiểm thử | Thao tác | Assertion |
| --- | --- | --- |
| JSONL source | Chạy `LogAggregationDemo` | Hai dòng, mỗi dòng JSON hợp lệ, không chứa secret |
| Parse CRI/file | Đưa fixture qua agent | Timestamp/stream/body được parse đúng, không chèn wrapper vào JSON |
| Normalization | Map event tùy chỉnh → schema đích | `service.name`, severity, event.code có kiểu và vị trí đúng |
| Trace correlation | Gửi 2 event cùng traceId | Query trả đúng cả hai event và trace link khi có |
| Multiline | Body có `\n` và quote | Một event duy nhất, giữ body logic |
| Unicode | Message tiếng Việt/emoji | Không lỗi encoding, không tách sai dòng |
| Missing optional field | Không có spanId | Collector xử lý theo contract, không drop ngoài ý định |
| Bad timestamp | Event time invalid | Có reject/quarantine/metric, không âm thầm giả giờ |
| Network outage | Ngắt backend tạm thời | Retry/backlog/drop theo policy; alert hoạt động |
| Agent restart | Restart trước/đang rotate file | Event có thể trùng/mất trong giới hạn đã công bố |
| Pod restart | Container kết thúc | Log được thu nếu đã tới runtime; không nhầm với durable guarantee |
| Very large record | Body vượt giới hạn | Cắt/drop/quarantine theo policy, không crash agent |
| Redaction | Event chứa sentinel giả | Sentinel không ở index, export, dashboard, fallback logs |
| Authorization | User role không được xem tenant khác | Backend từ chối query/exfiltration |
| Retention | Event hết hạn bảo quản | Dữ liệu được xóa theo policy ở các tầng áp dụng |
| Duplicate | ACK bị mất rồi retry | Dedup/đếm theo hợp đồng |
| High throughput | Tăng tốc phát logs có kiểm soát | Bounded memory/queue, không gây OOM, đo ingest delay |

**Đừng dùng `Thread.sleep(1000)` là bằng chứng event đã được index.** Với pipeline async, query theo event ID test có giới hạn thời gian, theo dõi completion/ACK và ghi nhận elapsed time. Negative test phải chờ ranh giới ổn định phù hợp; “chưa thấy ngay” không chứng minh bị filter.

## 23. Quan sát chính hệ thống aggregation

Log pipeline cũng có thể hỏng mà ứng dụng vẫn chạy. Vì vậy hãy đo **telemetry của telemetry pipeline**:

- Số records/bytes nhận vào mỗi receiver.
- Số records được export thành công, số lỗi export và retries.
- Pending queue depth, dropped records, buffer disk usage.
- Parse error rate, số event không mapping được hoặc quá dài.
- `ingest_delay = observed/indexed time - event time`, có xét clock skew.
- Disk remaining, rotation lag và checkpoint persistence.
- Collector CPU, memory, restart count, readiness/health.
- Tỷ lệ log thiếu trace_id/schema version hoặc sai type.
- Số duplicate theo event ID (nếu có).
- Chi phí ingest/index và p95/p99 query latency.

Alert ví dụ: **backend exporter lỗi liên tục**, queue tăng mãi, ingestion delay vượt ngưỡng hoặc số source event nhận được giảm mạnh trong khi app request rate vẫn bình thường.

**Tránh vòng lặp logging:** Collector bị lỗi → in log lỗi quá nhiều vào chính pipeline đang lỗi → tăng tải pipeline → lỗi nặng hơn. Nên có rate limit và kênh chẩn đoán tối thiểu độc lập.

## 24. Quy trình điều tra “ứng dụng có log nhưng dashboard không thấy”

Thay vì tăng level DEBUG vô hạn, điều tra theo từng hop:

1. **Tại JVM:** logger có enabled không? Có filter? Handler/appender có start? Log có đi stdout hay file nào?
2. **Tại container:** `kubectl logs` thấy event không? Runtime có rotate? Stream stdout/stderr có được giữ đúng?
3. **Tại agent:** filelog include path đúng, có đọc được file, có checkpoint và quyền truy cập không? Có parse error?
4. **Tại Collector:** receiver có được bật trong `service.pipelines.logs`? Có processor drop field/event? Queue, retries, exporter báo gì?
5. **Tại backend:** ingest có chấp nhận schema/timestamp không? Có bị routing sai tenant/index? Retention đã xóa? Query đang lọc nhầm thời gian/môi trường?
6. **Tại dashboard:** quyền, timezone hiển thị, sampling, search delay hoặc trace linking có gây hiểu nhầm không?

Bảng triệu chứng:

| Triệu chứng | Nguyên nhân thường gặp | Xác minh |
| --- | --- | --- |
| `kubectl logs` có, backend không có | Agent path/permission/collector pipeline hoặc exporter lỗi | Check file cursor, receiver metrics, exporter errors |
| Log có ở backend nhưng không query theo field | JSON được giữ như body text, chưa parse/map | Xem record thô/schema mapping |
| Chỉ có vài dòng đầu stack trace | Multiline parser sai hoặc partial records | So raw CRI log và event sau parser |
| Log timestamp nằm ngoài khoảng query | Clock skew, zone hoặc parse timestamp sai | So event/observed/index time |
| Cùng event xuất hiện hai lần | Ship stdout+file hoặc retry sau ACK mất | Xem source labels và event ID |
| Thỉnh thoảng mất log khi tải cao | Async queue/agent buffer drop, rotation, backend throttling | Kiểm tra drop metrics, queue và rate |
| Trace ID không liên kết | Context không propagate hoặc format/mapping khác | So IDs ở source, agent và backend |
| Query chậm/chi phí lớn | Quá nhiều index/high-cardinality fields | Xem index và query plans của backend |
| Secret xuất trong index dù dashboard đã mask | Mask UI-only hoặc sink khác không redact | Truy xuất bản ghi thô, kiểm tra pipeline từ nguồn |

Không “chữa” bằng cách chỉ tăng `retention` hoặc `queueSize` khi chưa biết event đang mất ở hop nào; thay đổi có thể tăng chi phí mà không giải quyết gốc.

## 25. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Cho rằng log lên stdout đồng nghĩa đã vào dashboard | Thiếu agent/Collector/backend | Test end-to-end |
| Giả định mọi JSONL là OTLP | Receiver OTLP không đọc JSONL thô | Dùng filelog/agent parser hoặc OTLP exporter thật |
| Ghi text tự do và regex parse mọi thứ | Lỗi khi format/locale thay đổi | Structured schema và JSON encoder chuẩn |
| Bỏ qua runtime CRI wrapper | JSON parser nhận sai envelope | Parse container log trước application body |
| Ship cùng file và stdout | Duplicate event | Chọn source/route và dedup |
| Quá tin vào `kubectl logs` | Không có cluster-level retention | Backend log tập trung |
| Coi `flush()` là fsync/remote commit | Sai durability guarantee | Xác định từng ACK/queue/storage boundary |
| Không quản lý multiline | Stack trace bị chia thành nhiều records | JSONL có escaping hoặc multiline parser |
| Không đặt `service.name` và event code | Khó query cross-service | Schema và resource enrichment |
| Đặt raw message ID thành metric label | Cardinality cao | Low-cardinality metrics; ID để ở logs/traces |
| Log nguyên payload/exception/headers | Rò PII và credentials | Field allowlist và redaction từ nguồn |
| Dùng dashboard masking làm lớp duy nhất | Raw secrets còn ở index/backup | Sanitization trước ingest và quyền truy cập |
| Retry không giới hạn trong RAM | OOM, log storm, tăng latency | Bounded queue, backpressure và alert |
| Cho rằng retry không tạo duplicate | Đếm sai, workflow bị nhiễu | Event ID và dedup theo nhu cầu |
| Dùng timestamp ingest làm event time | Sai thứ tự nghiệp vụ khi delay | Giữ cả event/observed time |
| Tắt audit bằng sampling DEBUG | Mất bằng chứng sự kiện bắt buộc | Audit pipeline riêng theo policy |
| Test bằng sleep rồi assert ngay | Test flaky | Await có deadline và query xác minh |
| Không monitor collector | Pipeline im lặng mất log | Metrics + health + alert độc lập |

## 26. Checklist triển khai log aggregation cho Java

1. Xác định **log sources**: stdout/stderr, file, OTLP; tránh collect trùng.
2. Chọn **schema version**, tên field, kiểu dữ liệu, event code và resource attributes.
3. Quy định timestamp UTC; phân biệt event vs observed/ingest time.
4. Đảm bảo structured formatter/encoder đúng framework và không phá JSONL.
5. Không ghi secret/PII không cần thiết; có test sentinel ở source và sink.
6. Xác định collector agent/gateway deployment và quyền đọc file/metadata.
7. Nếu dùng Kubernetes, xử lý CRI format, partial records, rotation và lifecycle pods.
8. Nếu dùng OpenTelemetry, phân biệt JSONL parse path và OTLP receiver path.
9. Đặt giới hạn batch, queue, retry và memory/disk; đo backpressure/drop.
10. Định nghĩa bảo đảm giao nhận và cách xử lý duplicate; không hứa exactly-once khi chưa có bằng chứng.
11. Propagate trace context/correlation ID với thread async và message brokers.
12. Chọn index fields phù hợp, retention và quyền truy cập theo từng nhóm log.
13. Thiết lập TLS/auth/mTLS, tenant isolation, secret management và audit truy cập.
14. Có kiểm thử end-to-end qua app → agent → collector → backend/query.
15. Có metric/alert về ingest errors, delay, drop, duplicate, queue và disk.
16. Có runbook điều tra missing logs dựa trên từng hop và kế hoạch phục hồi outage.
17. Phân biệt observability logs với audit events bắt buộc; chọn durable recorder khi có yêu cầu.
18. Đánh giá chi phí và throughput trước khi bật DEBUG/TRACE trên nhiều instance.

## 27. Câu hỏi tự kiểm tra

1. “Log aggregation” khác `Logger.info(...)` và “tập trung vào một file” như thế nào?
2. Tại sao JSON object trên stdout không tự thành OpenTelemetry LogRecord?
3. Trong Kubernetes, `kubectl logs` có thay thế central log backend không?
4. Những field nào giúp tìm tất cả log liên quan đến một trace?
5. Phân biệt event timestamp và observed timestamp khi mạng chậm?
6. Tại sao `getLoggerName()` và `service.name` không phải cùng khái niệm?
7. Với một body chứa newline, cách nào đảm bảo một JSONL event không bị tách thành hai dòng?
8. Vì sao log INFO đã được emit nhưng collector vẫn có thể không nhận được?
9. Khi exporter retry vì ACK bị mất, điều gì có thể xảy ra?
10. Nếu cần tìm `order_ref`, có nên tạo metric label chứa giá trị này không?
11. Tại sao sampling DEBUG không phù hợp làm chính sách duy nhất cho audit bắt buộc?
12. Khi dashboard không thấy log, tại sao cần kiểm tra agent checkpoint và Collector pipeline?
13. `SeverityText` khác `SeverityNumber` trong OpenTelemetry thế nào?
14. Việc ghi `trace_id` vào JSON có tự chứng minh trace ID hợp lệ không?
15. Test JSON parse được có đủ chứng minh backend đã index đúng field không?
16. Vì sao mask ở dashboard không thể xử lý hết rò rỉ đã xảy ra?
17. Tại sao Collector cần có telemetry riêng để theo dõi chính pipeline?
18. Một JVM demo gọi `System.out.print(...)` có bảo đảm file đã durable trên node hay không?

**Gợi ý:** (1) gom qua nhiều nguồn, chuẩn hóa, vận chuyển, lưu và query; (2) cần parser/mapping hoặc OTLP exporter; (3) không, Kubernetes không có sẵn kho log tập trung; (4) trace ID với service/time/event code; (5) phát tại JVM vs thấy tại collector; (6) class/logger category vs resource dịch vụ; (7) JSON escaping hoặc structured encoding đúng; (8) còn runtime/agent/queue/net/backend; (9) duplicate; (10) không, cardinality cao; (11) audit có policy khác; (12) kiểm tra từng hop; (13) text gốc vs mức chuẩn hóa; (14) không; (15) chưa; (16) raw index và backup còn giữ; (17) phát hiện mất dữ liệu im lặng; (18) không.

## 28. Tài liệu tham khảo

- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): stdout/stderr, CRI logs, rotation, node agent, sidecar và cluster-level logging.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): Timestamp, ObservedTimestamp, SeverityText/Number, Body, Resource, Attributes, TraceId và SpanId.
- [OpenTelemetry — Logs Concepts](https://opentelemetry.io/docs/concepts/signals/logs/): các khái niệm log signal, bridges và exporters.
- [OpenTelemetry — Collector Architecture](https://opentelemetry.io/docs/collector/architecture/): receivers, processors, exporters và pipelines.
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): khai báo components, service pipelines và cấu hình cơ bản.
- [OpenTelemetry — Install Collector with Docker](https://opentelemetry.io/docs/collector/install/docker/): ví dụ cấu hình OTLP receiver và debug exporter.
- [OpenTelemetry — Collector Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): chẩn đoán dữ liệu không nhận, không xử lý hoặc không export.
- [OpenTelemetry — Agent-to-Gateway Pattern](https://opentelemetry.io/docs/collector/deploy/other/agent-to-gateway/): tách agent/gateway và đánh đổi vận hành.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): ghi `LogRecord` và level.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): timestamp, logger name, parameters và thông tin sự kiện.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `flush`, lifecycle.
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html): console/file/async appenders và cấu hình.
- [Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): structured JSON layout và schema.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu nhạy cảm, injection, bảo vệ logs và vận hành logging.
