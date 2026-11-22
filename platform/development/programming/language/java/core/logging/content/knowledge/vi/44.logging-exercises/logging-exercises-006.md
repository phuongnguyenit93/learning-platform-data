# Thực hành: Thêm JSON output cho Java Core Logging

## 1. Mục tiêu và sản phẩm cuối

Trong dự án Java, log dạng text mặc định thường phù hợp để đọc bằng mắt nhưng khó lọc chính xác theo `service`, `event.name`, `request_id`, `trace_id` hay `error.code` khi hệ thống có nhiều instance. Bài thực hành này chuyển **log output sang JSON Lines** (mỗi log event là một JSON object trên **một dòng vật lý**), đồng thời giữ đúng nghĩa của severity, context và exception.

Sau bài học, bạn có thể:

1. Phân biệt **structured log event**, **JSON encoding** và **dòng text trông giống JSON**.
2. Tạo JSON output có timestamp, severity, logger, service, event name, request ID, trace ID, message, error code và exception type.
3. Chạy chương trình Java 17 chỉ dùng JDK để xem JSON output **xác định, có thể so sánh chính xác**.
4. Đảm bảo dấu nháy, dấu gạch chéo ngược, newline và control characters trong message không phá cấu trúc JSON Lines.
5. Biết tích hợp JSON encoder vào Logback/SLF4J, lưu ý Log4j2 và Spring Boot theo đúng dependency/phiên bản thực tế.
6. Kiểm tra output bằng JSON parser và so sánh schema qua ứng dụng, file/stdout, shipper/Collector và log backend.
7. Tránh sai lầm phổ biến: nối chuỗi JSON thủ công không escape, đẩy secrets vào log, tách stack trace thành nhiều event, làm trùng output hoặc cho rằng file JSON tự bảo đảm log được ingest.

**Kết quả mong đợi:** chạy `javac JsonOutputDemo.java` và `java JsonOutputDemo` sẽ tạo **ba JSON objects hợp lệ trên ba dòng**, có thể tìm theo `event.name`, `request_id` và `error.code`. Không cần cài Maven, Gradle, database hay service logging bên ngoài cho phần thực hành Java thuần.

Bài còn có phần cấu hình Logback với thư viện JSON encoder dành cho ứng dụng sử dụng SLF4J, cùng checklist chuyển đổi một service hiện có sang structured logging an toàn.

## 2. Trước và sau: thay đổi điều gì?

Một text log thông thường:

```text
Jan 01, 2026 10:00:01 AM com.example.PaymentService authorize
WARNING: payment provider timed out, req-101
```

Với text, người đọc có thể hiểu nội dung, nhưng hệ thống tìm kiếm phải phân tích câu chữ để tìm request ID, error code hoặc service. Formatter mặc định có thể thay đổi theo locale/runtime; exception stack trace nhiều dòng cũng dễ bị shipper hiểu thành nhiều event.

Sau khi chuyển thành JSON Lines:

```json
{"timestamp":"2026-01-01T10:00:01Z","severity":"WARNING","logger":"demo.orders","service.name":"orders-api","event.name":"payment.retry","request_id":"req-101","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Retry scheduled","error.code":"DOWNSTREAM_TIMEOUT"}
```

Mỗi trường là một **JSON key/value riêng**, thay vì token tự do trong message. Backend có thể lọc chính xác `event.name=payment.retry` hoặc `error.code=DOWNSTREAM_TIMEOUT` sau khi parser/mapping phù hợp được cấu hình.

Tuy nhiên, **JSON output không tự động là “structured logging đúng nghĩa”**. Nếu Java chỉ ghi:

```text
{"message":"severity=ERROR request_id=req-101 error_code=TIMEOUT"}
```

thì mức severity, request ID và error code vẫn là **một chuỗi message**. Người dùng có thể phải regex để tìm kiếm. Cần đưa các thuộc tính quan trọng ra key có kiểu và ngữ nghĩa rõ ràng.

### Phân biệt ba tầng

| Tầng | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Log event trong JVM | Chứa severity, message, timestamp, exception và context | JUL `LogRecord`, Logback ILoggingEvent |
| Encoder/Formatter | Biến event thành bytes/text theo JSON Lines | JSON formatter/encoder, UTF-8 |
| Shipper/Collector/backend | Thu, parse, enrich, index và search | Container agent, file shipper, OTLP Collector, log store |

Việc thay text layout bằng JSON encoder thay đổi tầng **định dạng**, không nhất thiết thay **transport**. Log vẫn có thể ghi stdout hoặc file và được collector thu như trước. Cũng không nên hiểu JSON Lines là một JSON array: nhiều dòng object riêng lẻ **không** phải một tài liệu JSON duy nhất bao quanh bởi `[ ... ]`.

## 3. Thiết kế schema JSON trước khi viết code

Một schema tối giản, có mục đích rõ:

| Trường | Kiểu | Ý nghĩa | Nguồn tin cậy |
| --- | --- | --- | --- |
| `timestamp` | String ISO-8601 UTC/offset | Thời điểm event xảy ra | Logging framework/JVM |
| `severity` | String | INFO, WARNING, SEVERE… | Logging event |
| `logger` | String | Tên logger phát bản ghi | Framework |
| `service.name` | String | Dịch vụ tạo event | Deployment/application config |
| `event.name` | String | Tên sự kiện ổn định, máy đọc được | Code/event catalog |
| `request_id` | String, tùy event | Liên kết các log của một request | Ingress/correlation context đã kiểm chứng |
| `trace_id` | String, tùy event | Liên kết distributed trace | Trusted trace context |
| `message` | String | Tóm tắt dễ đọc, có thể thay đổi | Code, đã loại dữ liệu nhạy cảm |
| `error.code` | String, tùy event | Mã lỗi ổn định, ví dụ `DOWNSTREAM_TIMEOUT` | Business/exception boundary |
| `exception.type` | String, tùy event | Tên class exception để phân loại | `Throwable.getClass()` |

Đây là **schema minh họa do ứng dụng định nghĩa**, không có nghĩa mọi hệ thống tự nhận các key này như trường chuẩn của OpenTelemetry. Với backend thật, một số trường có thể là resource attributes, log record attributes hoặc các tên đã được quy định bởi tổ chức. Cần thống nhất version, cách serialize và mapping.

### Các quy ước nên chốt

- **Timestamp:** dùng `Instant`/ISO-8601 có `Z` hoặc offset. Tách event time khỏi ingest time khi đối chiếu.
- **Severity:** giữ một quy ước rõ; JUL có `INFO`/`WARNING`/`SEVERE`, không tự coi chúng là đúng các token `INFO`/`WARN`/`ERROR` của SLF4J nếu chưa mapping.
- **Event name:** danh mục ổn định như `order.accepted`, `payment.retry`, `payment.failed`, không lấy nguyên `exception.getMessage()` làm tên event.
- **Identifiers:** nếu cần, có `event_id` riêng. Một request có thể tạo nhiều events, nên `request_id` không phải luôn là khóa dedup.
- **Optional fields:** có thể **bỏ key** khi không có giá trị hoặc dùng JSON `null` theo contract, nhưng **không dùng chuỗi `"null"`** nếu muốn biểu diễn giá trị vắng mặt.
- **Field types:** status/duration/count nên là số thực hoặc số nguyên JSON, không ép mọi thứ thành string. Ví dụ `"http.status_code":503` và `"duration_ms":12.5`.
- **Payload size:** giới hạn message, exception detail và field do user gửi để tránh encoder/Collector/backend quá tải.
- **Data minimization:** token, session cookie, API key, password, dữ liệu cá nhân không cần thiết **không được đưa vào event**, bất kể formatter có escape được chúng.

Một số JSON backends có cách xử lý dấu chấm trong key khác nhau, ví dụ `service.name` có thể được giữ nguyên hoặc ánh xạ thành nested object theo cấu hình. Phải kiểm output và schema lưu thực tế thay vì dựa vào dấu chấm để suy luận.

## 4. Kiến trúc thực hành

Phần JDK 17 dùng:

```text
JsonOutputDemo.main()
   |
   +-- tạo Context(event, service, request, trace, errorCode)
   |
   +-- tạo java.util.logging.LogRecord
   |     level + timestamp + message + Throwable + context
   |
   +-- java.util.logging.Logger
   |     ngưỡng level + handler chain
   |
   +-- JsonFormatter
   |     JSON escaping + field assembly
   |
   +-- custom Handler -> System.out
         |
         +-- 1 LogRecord = 1 JSON object + '\n'
```

**Vì sao dùng JUL trong ví dụ chính?** JUL nằm sẵn trong JDK 17, giúp thực hành chạy ngay, kiểm soát output xác định và hiểu sự phân tách `LogRecord`, `Formatter`, `Handler`. Sau khi hiểu, cùng schema có thể được hiện thực bằng SLF4J + Logback/Log4j2 hoặc OpenTelemetry SDK/exporter.

Bài triển khai formatter JSON bằng tay **chỉ nhằm giải thích nguyên lý**. Với production, hãy ưu tiên JSON encoder/serializer được kiểm chứng, hỗ trợ Unicode, escaping, exception serialization, performance, cấu hình fields và schema version. Không sao chép formatter tối giản vào hệ thống xử lý input không tin cậy rồi mặc định đã đạt mọi tiêu chuẩn bảo mật/chuẩn hóa.

## 5. Tạo chương trình Java 17 hoàn chỉnh

Tạo file `JsonOutputDemo.java` với mã dưới đây. Chương trình không tạo file bên ngoài, không cần mạng, không đọc biến môi trường và sử dụng timestamp cố định để stdout có thể được kiểm thử trực tiếp.

```java
import java.time.Instant;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JsonOutputDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.orders");

    record Context(
            String eventName,
            String serviceName,
            String requestId,
            String traceId,
            String errorCode) {}

    private static String quote(String text) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
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

    private static void addField(
            StringBuilder out, String name, String value) {
        if (out.length() > 1) {
            out.append(',');
        }
        out.append(quote(name)).append(':').append(quote(value));
    }

    private static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder json = new StringBuilder("{");

            addField(json, "timestamp", record.getInstant().toString());
            addField(json, "severity", record.getLevel().getName());
            addField(json, "logger", record.getLoggerName());

            Object[] params = record.getParameters();
            if (params != null
                    && params.length == 1
                    && params[0] instanceof Context context) {
                addField(json, "service.name", context.serviceName());
                addField(json, "event.name", context.eventName());
                if (context.requestId() != null) {
                    addField(json, "request_id", context.requestId());
                }
                if (context.traceId() != null) {
                    addField(json, "trace_id", context.traceId());
                }
                addField(json, "message", record.getMessage());
                if (context.errorCode() != null) {
                    addField(json, "error.code", context.errorCode());
                }
            } else {
                addField(json, "message", record.getMessage());
            }

            if (record.getThrown() != null) {
                addField(json, "exception.type",
                        record.getThrown().getClass().getName());
            }

            return json.append("}\n").toString();
        }
    }

    private static void publish(
            Level level,
            Instant timestamp,
            Context context,
            String message,
            Throwable error) {
        LogRecord record = new LogRecord(level, message);
        record.setInstant(timestamp);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[] {context});
        record.setThrown(error);
        LOG.log(record);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler console = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.print(getFormatter().format(record));
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };
        console.setLevel(Level.ALL);
        console.setFormatter(new JsonFormatter());
        LOG.addHandler(console);

        String trace = "4bf92f3577b34da6a3ce929d0e0e4736";

        try {
            publish(
                    Level.INFO,
                    Instant.parse("2026-01-01T10:00:00Z"),
                    new Context(
                            "order.accepted", "orders-api",
                            "req-101", trace, null),
                    "Order \"A-42\" accepted\nnext step",
                    null);

            publish(
                    Level.WARNING,
                    Instant.parse("2026-01-01T10:00:01Z"),
                    new Context(
                            "payment.retry", "orders-api",
                            "req-101", trace, "DOWNSTREAM_TIMEOUT"),
                    "Retry scheduled",
                    null);

            publish(
                    Level.SEVERE,
                    Instant.parse("2026-01-01T10:00:02Z"),
                    new Context(
                            "payment.failed", "orders-api",
                            "req-102", trace, "PAYMENT_UNAVAILABLE"),
                    "Provider failed",
                    new IllegalStateException("provider unavailable"));
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac JsonOutputDemo.java
java JsonOutputDemo
```

**Stdout chính xác (ba dòng vật lý):**

```json
{"timestamp":"2026-01-01T10:00:00Z","severity":"INFO","logger":"demo.orders","service.name":"orders-api","event.name":"order.accepted","request_id":"req-101","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Order \"A-42\" accepted\nnext step"}
{"timestamp":"2026-01-01T10:00:01Z","severity":"WARNING","logger":"demo.orders","service.name":"orders-api","event.name":"payment.retry","request_id":"req-101","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Retry scheduled","error.code":"DOWNSTREAM_TIMEOUT"}
{"timestamp":"2026-01-01T10:00:02Z","severity":"SEVERE","logger":"demo.orders","service.name":"orders-api","event.name":"payment.failed","request_id":"req-102","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Provider failed","error.code":"PAYMENT_UNAVAILABLE","exception.type":"java.lang.IllegalStateException"}
```

### Giải thích từng phần

**`Context`:** record chứa những trường thuộc một log event có nghĩa. Ở ví dụ này, `eventName`, `requestId`, `traceId` và `errorCode` được đặt trong `LogRecord.parameters` như một cách truyền context đơn giản. Đây **không phải cơ chế MDC tiêu chuẩn của JUL** và không phải một quy tắc định nghĩa chung cho mọi JUL formatter. Trong ứng dụng thật cần event API/schema và context propagation phù hợp, không tùy tiện dùng `LogRecord.parameters` để mang object nếu formatter/bridge khác có thể diễn giải nó theo cách khác.

**`LogRecord`:** mang `Level`, timestamp, logger, message, parameters và Throwable. `setInstant` có trong Java 17; việc đặt timestamp cố định giúp kiểm output. Event thật nên dùng thời gian thực với UTC/offset rõ ràng.

**`JsonFormatter`:** tạo một JSON object/record, escape key/value bằng `quote`, chỉ thêm `error.code` và `exception.type` khi có. Hàm `addField` đặt dấu phẩy giữa các trường để tránh JSON lỗi do dấu phẩy thừa trước dấu `}`.

**`quote`:** biến `"` thành `\\"`, newline thành `\\n`, backslash thành `\\\\` trong JSON output. Vì message đầu chứa dấu nháy và newline nhưng formatter giữ chúng ở dạng escaped, **JSON Lines vẫn chỉ có ba dòng vật lý**.

**`Handler`:** in một dòng từ formatter cho mỗi record được phép. `LOG.setUseParentHandlers(false)` tránh thêm output từ parent handlers; `LOG.setLevel(Level.INFO)` cho phép cả INFO/WARNING/SEVERE, còn handler ALL không chặn ba mức này. Không dùng `ConsoleHandler` mặc định vì nó thường ghi vào stderr và có formatter/behavior mặc định khác.

**`Throwable`:** ví dụ chỉ ghi `exception.type`, không in stack trace để output nhỏ và ổn định. Sản phẩm thật thường cần stack trace được encoder xử lý trong một field (hoặc các trường có cấu trúc) với sanitization và giới hạn kích thước. **Không tự chuyển toàn bộ stack trace thành nhiều log events độc lập.**

### Giới hạn kỹ thuật của formatter minh họa

- `quote` xử lý control characters phổ biến và các ký tự dưới U+0020, nhưng **không thực hiện validation toàn diện chuỗi Unicode**, chẳng hạn chuỗi có unpaired surrogate hoặc quá lớn. Production nên dùng thư viện JSON được kiểm chứng và policy dữ liệu.
- `format` giả định `record.getInstant()`, logger name và message hợp lệ theo dữ liệu demo. Với log records từ nguồn khác, cần xử lý null/giá trị bất thường theo schema contract.
- Không đưa thông điệp exception hoặc stack trace đầy đủ vào output. Nếu hệ thống cần forensic details, nên dùng encoder hỗ trợ Throwable và giới hạn thông tin nhạy cảm.
- Handler in bằng `System.out.print` là mô hình học tập; thực tế cần chú ý charset UTF-8, batching, flush/shutdown, queue và lỗi I/O.
- Không có retry/ACK, file checkpoint hoặc Collector. **In thành công ra stdout không chứng minh log đã được ingest bền vững ở backend.**
- `LogRecord.parameters` được sử dụng như một container context chuyên biệt của bài. Không thể suy ra mọi JUL handler sẽ hiểu các tham số đó.
- Một trace ID chỉ nên đi theo request/trace thực. Demo dùng chuỗi cố định cho hai request để dễ nhìn; **trong production không được dùng một trace ID cho mọi request**. Thông thường request khác nhau có trace context riêng, trừ khi có một quan hệ trace được xác định.
- Dữ liệu ví dụ mang ASCII để stdout nhất quán trên nhiều terminal. Với tiếng Việt, đảm bảo cả nguồn, encoder và file/console dùng UTF-8.

## 6. Kiểm tra JSON output thay vì chỉ nhìn bằng mắt

### Kiểm số dòng vật lý

Bạn cần thấy đúng **ba dòng**, dù message đầu có newline **logic**. Chuỗi `\\n` bên trong JSON là hai ký tự in ra `\` và `n`; nó không phải byte LF kết thúc một record. Nếu một log event bị vỡ thành hai dòng vật lý, shippers line-oriented có thể parse sai.

Trên shell POSIX có thể lưu output và đếm dòng:

```bash
java JsonOutputDemo > logs.jsonl
wc -l logs.jsonl
```

Kết quả kỳ vọng ở `wc -l` là 3 dòng (cách hiển thị filename/phần spacing tùy shell). Trên PowerShell, có thể dùng:

```powershell
java JsonOutputDemo | Set-Content -Encoding utf8 logs.jsonl
(Get-Content logs.jsonl).Count
```

Kết quả đếm kỳ vọng là `3`. Cách PowerShell mã hóa stdout và redirection có thể khác giữa phiên bản PowerShell/console, nên kiểm UTF-8 khi log thực sự chứa tiếng Việt.

### Parse từng dòng JSON

Nếu máy có Python 3, có thể thử parser tiêu chuẩn; lệnh này chỉ là bước **kiểm thử** output của ví dụ, không phải dependency của chương trình Java:

```python
import json

with open("logs.jsonl", encoding="utf-8-sig") as f:
    events = [json.loads(line) for line in f if line.strip()]

assert len(events) == 3
assert events[0]["event.name"] == "order.accepted"
assert events[0]["message"] == 'Order "A-42" accepted\nnext step'
assert events[1]["error.code"] == "DOWNSTREAM_TIMEOUT"
assert events[2]["severity"] == "SEVERE"
assert events[2]["exception.type"] == "java.lang.IllegalStateException"
print("JSONL_VALID events=3")
```

**Stdout kỳ vọng** nếu mọi assertion đạt:

```text
JSONL_VALID events=3
```

Chú ý dùng `json.loads(line)` cho **từng dòng**, không dùng `json.load(file)` cho toàn bộ JSON Lines file như thể nó là một JSON object/array đơn. Nếu parser báo `Extra data` ở dòng đầu tiên khi load cả file, chưa chắc JSON Lines sai — có thể đơn giản là dùng sai cách parse.

### Kiểm bằng test có chủ đích

Ngoài parser, cần kiểm những đặc điểm nghiệp vụ:

1. Mỗi log event có đủ các trường bắt buộc.
2. Timestamp có offset và đúng thời điểm record được tạo.
3. `severity` giữ đúng mapping của JUL/backend.
4. `event.name` nằm trong danh mục đã quản lý, không thay đổi bất chợt theo message.
5. `error.code` có ở event lỗi tương ứng, không bị đặt `"null"`.
6. `request_id` và `trace_id` không bị trộn khi nhiều request chạy đồng thời.
7. Message có dấu nháy, backslash, newline, Unicode vẫn được parse đúng.
8. Stack trace và exception cause không làm vỡ JSON Lines.
9. Không có password/token/PII ngoài policy.
10. Collector/backend parse thành **field có thể query**, không chỉ giữ một chuỗi JSON trong `message`.

## 7. Thêm JSON output vào ứng dụng SLF4J + Logback

Với ứng dụng thực dùng SLF4J và Logback, nên dùng **JSON encoder chuyên dụng** thay vì tự viết `Formatter` và gắn vào JUL. Cách lựa chọn cụ thể phụ thuộc backend logging, dependency và phiên bản dự án.

Một ví dụ phổ biến là **Logstash Logback Encoder** qua dependency `net.logstash.logback:logstash-logback-encoder`. Bạn cần chọn phiên bản **tương thích** với Logback/SLF4J/Jackson/Java đang dùng; không nên copy một số version bất kỳ mà chưa kiểm dependency tree và yêu cầu Java tối thiểu.

Giả sử dependency đã được thêm và tương thích, file `logback.xml` hoặc `logback-spring.xml` có thể sử dụng:

```xml
<configuration>
    <appender name="JSON_STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_STDOUT"/>
    </root>
</configuration>
```

Đây là **cấu hình minh họa phụ thuộc thư viện ngoài**, không phải ví dụ Java 17 JDK-only. Kiểm đúng encoder class, classpath, API Logback/provider, file config được load và tên fields thực sự được sinh trong phiên bản đã chọn.

### Checklist phụ thuộc

- Đã có SLF4J API và **một provider/backend phù hợp** trên classpath?
- `logback-classic` và `logback-core` có cùng dòng phiên bản tương thích?
- JSON encoder có hỗ trợ đúng Logback version đang dùng?
- Không có hai SLF4J providers cạnh tranh hoặc bridge tạo vòng lặp?
- Nếu ứng dụng dùng Spring Boot, config nằm ở tên/đường dẫn được Boot nhận?
- Dependency chứa encoder có mặt **ở runtime**, không chỉ test scope?
- Startup logs có báo lỗi khởi tạo appender/encoder hoặc tự fallback sang console pattern cũ?

Thêm dependency qua Maven/Gradle theo version đã được dự án quản lý; nếu backend thiếu encoder, XML có thể vẫn tồn tại nhưng runtime không tạo JSON output đúng mong đợi. **Phải chạy ứng dụng và parse một vài log events thật**.

### Làm sao bổ sung fields?

Trong Logback, có thể dùng **MDC** và/hoặc structured arguments/key-value logging tùy encoder và SLF4J version. Ví dụ SLF4J:

```java
logger.info("event=order.accepted orderId={}", orderId);
```

Đây là **fragment**, không chạy độc lập: cần `logger`/`orderId` và dependencies. Nếu formatter chỉ biến message thành chuỗi JSON, `orderId` có thể vẫn nằm trong `message` chứ không thành key JSON riêng. Để có schema đúng, cần dùng khả năng structured fields của encoder hoặc một event wrapper giữ trường riêng.

Ví dụ với MDC khi framework đang dùng SLF4J:

```java
try (var ignored = org.slf4j.MDC.putCloseable("request_id", requestId)) {
    logger.info("order accepted");
}
```

Fragment cần dependencies SLF4J và biến `requestId`; output có field `request_id` **chỉ khi encoder đang cấu hình ghi MDC**. Với `putCloseable`, key được remove khi resource đóng; trong production, phải xem **context trước đó có cần khôi phục không**, đặc biệt code lồng scope, và quản lý đúng propagation qua async tasks. Không coi MDC như bằng chứng xác thực actor.

### Mỗi level có một schema hay sao?

Thường nên dùng **schema nhất quán giữa INFO/WARN/ERROR**, thêm các field tùy tình huống. Ví dụ `error.code` và `exception.type` có mặt khi thật sự có lỗi, trong khi `event.name`/`service.name`/timestamp luôn có.

Không biến mỗi severity thành một định dạng JSON hoàn toàn khác khiến collector phải giữ nhiều parser. Đồng thời không cần bơm `"exception":""` vào INFO không lỗi chỉ để đủ key. Hãy định nghĩa field bắt buộc/tùy chọn rõ trong contract.

## 8. Log4j2 và các stack Java khác

Nếu dự án sử dụng Log4j2, không dùng file Logback XML vừa nêu. Log4j2 hỗ trợ các lựa chọn JSON layout; một phương án là **JsonTemplateLayout** với module `log4j-layout-template-json` tương ứng.

Mảnh cấu hình Log4j2 minh họa:

```xml
<Configuration status="WARN">
  <Appenders>
    <Console name="JSON" target="SYSTEM_OUT">
      <JsonTemplateLayout eventTemplateUri="classpath:EcsLayout.json"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="JSON"/>
    </Root>
  </Loggers>
</Configuration>
```

Đây là **cấu hình cần kiểm theo version/dependency thực tế**. Template `EcsLayout.json` là một template mẫu thường được cung cấp qua module liên quan trong các bản hỗ trợ; không nên giả định bản Log4j2/packaging nào cũng có template này trên classpath. Có thể dùng template khác theo schema của tổ chức.

Một hệ thống sử dụng JUL có thể giữ Handler/Formatter riêng, hoặc dùng bridge/provider phù hợp để đưa JUL logs vào backend chung. **Không bật hai tuyến song song mà không xem có trùng events hoặc bridge loop hay không.**

Một ứng dụng Spring Boot có thể hỗ trợ structured logging theo phiên bản/stack, nhưng chi tiết property và format thay đổi qua bản phát hành. Ưu tiên khả năng được framework hỗ trợ khi tương thích, hoặc dùng một JSON encoder được nhóm vận hành đã chuẩn hóa. Sau thay đổi, kiểm schema và field names **bằng output thực**.

## 9. Timestamp, severity và tên trường chuẩn

### Timestamp

`Instant.now()` tạo thời điểm thực tế ở JVM; formatter nên xuất dạng UTC/offset được backend parser hiểu. Event time khác ingest time:

```text
event happened:    2026-01-01T10:00:00Z
collector received:2026-01-01T10:00:03Z
searchable:        2026-01-01T10:00:07Z
```

Nếu dashboard dùng event time, record thuộc phút 10:00; nếu tìm theo ingest time, nó thuộc khoảng khác. Khi debug “log bị mất”, luôn kiểm timezone và khoảng thời gian có bao gồm ingest lag hay không.

### Severity

JUL dùng `WARNING`/`SEVERE`; SLF4J dùng `WARN`/`ERROR`. Tổ chức có thể map chúng sang giá trị severity chung theo chuẩn backend/OTel, nhưng **không đổi tên bừa** làm log search/alert bị sai. Nếu JSON encoder phát `level`, backend dự kiến `severity`, cần rõ một bước mapping hoặc schema adapter.

### Field types và optional values

Trong JSON hợp lệ:

```json
{"http.status_code":503,"duration_ms":12.5,"retryable":false}
```

Các giá trị là số/boolean thật, thích hợp cho range/aggregation. Ngược lại:

```json
{"http.status_code":"503","duration_ms":"12.5","retryable":"false"}
```

Tất cả là string: một số backend vẫn convert được, một số gây lỗi schema hoặc query/sort sai. Trong demo JDK-only, các trường có mặt đều là string vì mục tiêu là escape và JSON Lines; **khi mở rộng schema thật cần hỗ trợ typed JSON values** và không ép mọi metric field thành string.

### Keys chứa dấu chấm

`service.name`, `event.name` và `exception.type` là những key dễ hiểu, nhưng backend khác nhau có thể yêu cầu mapping. Nếu hệ thống dùng OpenTelemetry log records, resource attributes và record attributes cũng có vị trí riêng. Không tự biến JSON object phẳng thành OTel log model chỉ bằng việc đặt tên key có dấu chấm.

## 10. Exception và stack trace khi chuyển sang JSON

Một exception trong Java thường mang:

- Class/type: `java.net.SocketTimeoutException`, `IllegalStateException`…
- Message, có thể chứa nội dung người dùng hoặc thông tin hạ tầng.
- Cause chain, suppressed exceptions.
- Stack trace gồm nhiều frame và ký tự newline.

Nếu format text rồi ship theo từng LF, một exception có thể thành **nhiều events rời rạc**, làm sai số lượng log và correlation. JSON encoder nên giữ exception trong **một log event** với field thích hợp; newline được escape thành `\n` bên trong chuỗi JSON. Một số encoder hỗ trợ các trường root-cause, stack-trace array hoặc nested structure; không có một schema duy nhất áp dụng cho mọi backend.

### Chọn mức log theo kết quả cuối

- Timeout một attempt nhưng sẽ retry: có thể ghi WARN hoặc diagnostic event; **không coi request cuối là ERROR** nếu retry thành công.
- Retry hết lượt và request/job thất bại: ERROR tại final boundary, chứa error code và Throwable cần thiết.
- Validation 400 do người dùng: không nhất thiết là server ERROR dù có exception.
- Async job lỗi sau HTTP 202: log/metric outcome ở job worker, không tự thay status HTTP đã trả.

Nếu một exception bị log đầy đủ ở DAO, service và controller, JSON output vẫn là **ba events riêng**. Chuyển sang JSON không tự giải quyết duplicate semantic logging; nên chọn owner tại boundary và event names khác nhau nếu cần log cả attempt lẫn final outcome.

### Đừng đưa toàn bộ Throwable vào field chưa kiểm soát

`Throwable.toString()` hoặc stack trace có thể lộ paths, SQL hoặc payload. Cần giới hạn size, redaction và retention; một số lỗi rất lớn có thể vượt max record size của agent/Collector. Không đặt toàn bộ stack trace thành metric label.

## 11. Correlation fields và MDC/ThreadContext

Một log JSON hữu ích thường bao gồm `request_id`, `trace_id`, `span_id` khi một request đi qua nhiều components. Dù vậy, các IDs phải được **tạo hoặc xác minh tại điểm ingress đáng tin**; không dùng trực tiếp client-supplied header chưa kiểm tra để quyết định tenant/actor/quyền truy cập.

Trong Logback qua SLF4J, `MDC` giúp bổ sung context:

```java
org.slf4j.MDC.put("request_id", requestId);
try {
    logger.info("event=order.accepted");
} finally {
    org.slf4j.MDC.remove("request_id");
}
```

Mã này là **fragment**, không độc lập và không xử lý khôi phục giá trị trước đó nếu có nested MDC scope. Việc encoder có xuất MDC hay không phụ thuộc cấu hình. **MDC thường gắn với thread**: nếu chuyển qua `ExecutorService`, `CompletableFuture` hoặc reactive chain, context không tự truyền qua mọi tác vụ. Dùng framework/context propagation phù hợp, cleanup đúng khi thread pool tái sử dụng.

Một request có thể tạo nhiều JSON events và một trace gồm nhiều spans. **Không dùng trace ID hoặc request ID làm metric labels** vì cardinality sẽ tăng theo số request; giữ ID trong log/trace để tìm kiếm.

### Khi không có request context

Startup event hoặc background scheduler có thể không có request ID. Hãy cho phép field optional **vắng mặt** hoặc dùng giá trị context có nghĩa theo contract, không tự tạo `"request_id":"null"` như một định danh thật. Đừng đánh đồng job ID với request ID nếu semantics khác nhau.

## 12. Ghi JSON ra stdout hay file?

### Stdout/stderr

Trong container/Kubernetes, Java app thường ghi stdout/stderr, container runtime/node agent thu để gửi tập trung. Ưu điểm: không cần quản lý rolling file bên trong container; pipeline thu có thể gắn metadata pod/service. Tuy nhiên cần kiểm log lines, charset, runtime rotation, event size, shutdown/flush và collector processing.

Đừng tự động phát cùng event ra stdout **và** file rồi để hai agents thu, trừ khi có chính sách distinct sinks/dedup. Cả hai có thể ingest cùng một JSON event tạo dữ liệu trùng.

### File

Nếu ứng dụng cần file output, có thể dùng JUL `FileHandler` hoặc Logback RollingFileAppender với JSON formatter/encoder. Cần lưu ý:

- UTF-8 encoding trong handler/encoder; tránh ký tự tiếng Việt bị sai.
- JSON Lines một event/một dòng, có newline cuối bản ghi.
- Rolling file policy (rename/create hoặc copytruncate) và file identity của shipper.
- Checkpoint/offset theo **byte**, partial lines, multiline và max record size.
- Flush/close vào shutdown và failure policy khi disk đầy.
- Quyền ghi/đọc, retention cục bộ và redaction tại nguồn.

JSON output **không giải quyết** vấn đề file shipper bỏ sót log khi rotation hoặc backpressure. Đó là bài toán delivery, không phải format.

### OTLP logs

Một số ứng dụng gửi LogRecord qua SDK/appender/exporter tương thích OpenTelemetry trực tiếp tới Collector mà không tạo JSON Lines file. Khi đó JSON output **không phải yêu cầu bắt buộc**; signal có thể được truyền bằng OTLP và chuyển sang định dạng backend ở nơi thích hợp. Nếu mục tiêu bài thực hành là “thêm JSON output”, hãy xác định sink đang cần JSON ở đâu: stdout, file, Collector output hay storage backend. Không bắt buộc serialize JSON rồi lại bọc vào OTLP khi pipeline đã hỗ trợ structured attributes.

## 13. Tích hợp với shipper và Collector

Một tuyến điển hình:

```text
Java JSON stdout
    |
container runtime / local file
    |
file shipper / node agent / Collector filelog receiver
    |
JSON parser
    |
resource enrichment + privacy filter + routing
    |
backend ingest + index
    |
search by service.name/event.name/request_id
```

Ở tầng shipper/Collector cần kiểm:

1. **Reader framing:** mỗi LF là một record; embedded newline trong message phải được escape.
2. **JSON parsing:** parse thành structured fields, không để nguyên JSON thành chuỗi `body` duy nhất nếu backend cần query fields.
3. **Timestamp mapping:** dùng thời gian từ event khi đáng tin, giữ ingest time riêng.
4. **Severity mapping:** JUL `SEVERE` có thể được map sang mức ERROR của backend; cách mapping tùy processor/schema.
5. **Resource metadata:** service, environment, host, pod, container và version từ nguồn tin cậy.
6. **Redaction/filter:** không đưa token/PII ra backend; chặn dữ liệu nhạy cảm càng gần nguồn càng tốt.
7. **Transport/ACK:** gửi được lên Collector không tự chứng minh đã index và query được ở storage.
8. **Cardinality:** không dùng `request_id` hoặc `trace_id` làm stream/metric labels tạo vô số series.
9. **Parse failures:** log có dòng quá dài, JSON hỏng hoặc type mismatch cần counters, cảnh báo và policy xử lý.
10. **Retention/permission:** quyền ingest và search/export không giống nhau; phân quyền theo tenant/environment.

**Không có một YAML chung đúng cho mọi Filebeat, Fluent Bit, Vector hoặc OpenTelemetry Collector.** Chọn parser/input/output của đúng version và distribution rồi test bằng event canary có ID duy nhất, query lại ở backend trong một deadline có đo.

## 14. Chuyển đổi theo từng bước trong một service có sẵn

Một cách rollout an toàn:

### Bước 1 — Kiểm hiện trạng

Ghi nhận logger facade/backend, output sinks, log formats, số records/giây, bytes/giây, exception handling, MDC fields, file rotation, Collector parser và dashboard searches đang dùng. Xác định ai phụ thuộc vào text pattern cũ.

### Bước 2 — Chốt schema và data policy

Tạo event catalog: `event.name`, severity, service, timestamp, request/trace IDs, outcome/error code, exception type, optional fields. Xác định tên/kiểu/nguồn field, version, giới hạn size và redaction/retention.

### Bước 3 — Chọn encoder tương thích

- **JDK-only/prototype:** thử formatter như chương trình ở mục 5.
- **SLF4J + Logback:** JSON encoder được kiểm chứng, có dependency tương thích.
- **Log4j2:** JSON layout/template phù hợp với version và schema.
- **Spring Boot:** xem structured logging support và provider đúng bản đang dùng.
- **OTel instrumentation:** nếu đã có OTLP log pipeline, cân nhắc giữ structured attributes thay vì ép JSON text.

### Bước 4 — Test tại local và staging

Đảm bảo một event là một JSON line parse được; giá trị optional, exception, Unicode, newline và quotes đúng. Kiểm context qua thread pool, 404/401/403, async jobs và source redaction.

### Bước 5 — Đồng bộ parser và saved queries

Nếu trước đây backend dùng regex parser cho text, phải đổi sang JSON parser/mapping tương ứng **trước hoặc cùng lúc** rollout. Một thời gian có thể có cả JSON và text từ nhiều version; dùng field `schema_version` hoặc source/version/format discriminator nếu backend cần.

### Bước 6 — Canary deployment

Bật JSON output cho một instance/nhóm nhỏ. So sánh log event count, parse errors, ingest lag, dropped records, bytes/s, CPU/GC, latency và khả năng tìm theo request/trace ID. Đảm bảo event ERROR không bị mất vì logger/appender cấu hình sai.

### Bước 7 — Mở rộng và rollback

Mở dần số instance, có cách quay về cấu hình cũ mà không phá dashboards/alerts. Sau khi tất cả clients/collectors chuyển xong, loại parser cũ theo kế hoạch; không xóa dữ liệu cũ trước retention. Ghi lại schema và quy trình vận hành cho các service khác.

**Không chuyển production bằng cách đổi file pattern thành chuỗi JSON tự lắp ghép rồi deploy ngay.** Sự thay đổi format có thể ảnh hưởng alert, pipeline, chi phí và quyền truy vấn dù logic nghiệp vụ không đổi.

## 15. Phát hiện JSON hỏng và log injection

Các trường hợp thường gây lỗi:

| Input | Nếu xử lý sai | Cách làm đúng |
| --- | --- | --- |
| Dấu nháy kép `"` | JSON string kết thúc sớm | Escape thành `\"` |
| Backslash `\` | Escape sequence không hợp lệ | Escape thành `\\` |
| Newline/CR | Một event bị tách thành nhiều dòng | Encode `\n`/`\r` trong string |
| Tab/control characters | JSON parser từ chối record | Escape control chars theo JSON |
| UTF-8 đa byte | Ký tự bị hỏng khi encode/decode sai | Dùng UTF-8 và decoder policy nhất quán |
| Chuỗi quá dài | Collector truncate/drop hoặc ingest quota | Size limits + parse/drop counters |
| Unexpected field type | Mapping conflict, query sai | Schema validation/typed serializer |
| Nested object/array | Text formatting hỏng | JSON serializer hỗ trợ cấu trúc |
| Throwable với nhiều frame | Một exception thành nhiều log lines | Encode stack trong một field/event |
| Input giả timestamp/level | Gây log injection nếu nối text | Server-side metadata và JSON encoding |

**Escaping không thay thế sanitization.** Chuỗi token được encode JSON hợp lệ vẫn là token bị lộ. Không lưu raw header `Authorization`, cookie, password, signed URL, private key, SQL params nhạy cảm hoặc toàn bộ request body không cần thiết.

Nếu message do user cung cấp chứa giá trị trông giống `"severity":"ERROR"`, JSON escaping đảm bảo nó chỉ là **nội dung trường message**, không thể thoát ra thành key cấp cao. Tuy nhiên nếu ứng dụng cho client ghi đè trực tiếp context fields `severity`/`service.name`/`tenant_id` thì encoder không thể sửa vấn đề tính tin cậy đó.

## 16. Log level và JSON output không thay thế nhau

Khi bật JSON output, logger level vẫn hoạt động:

- JUL `INFO` cho phép INFO, WARNING và SEVERE; `FINE` có thể bị chặn.
- SLF4J `INFO` cho phép INFO/WARN/ERROR, tùy backend filter.
- Encoder/handler có level/filter riêng và có thể loại record ngay cả khi logger cho phép.
- JSON format không làm DEBUG bị tự động bật, cũng không khiến ERROR chắc chắn tới backend.
- Các call sites sử dụng eager argument evaluation vẫn có thể thực hiện công việc đắt dù level bị tắt.

Ví dụ về eager logging:

```java
logger.fine("state=" + expensiveSnapshot());
```

Nếu `FINE` disabled, `expensiveSnapshot()` vẫn được đánh giá trước khi gọi logger. JUL hỗ trợ supplier:

```java
logger.log(Level.FINE, () -> "state=" + expensiveSnapshot());
```

Đoạn này chỉ là minh họa (cần logger và function), và supplier có thể giúp tránh tạo message khi level tắt. Với SLF4J, parameterized logging giúp trì hoãn formatting trong backend, nhưng biểu thức truyền làm argument vẫn chạy trước khi gọi method trừ khi có supplier/guard phù hợp.

JSON encode có thể tốn CPU và allocation hơn một pattern đơn giản tùy library, field count và workload. Đo trên stack thật, tránh kết luận JSON luôn nhanh hơn hoặc chậm hơn text chỉ từ một test nhỏ.

## 17. Chi phí, độ trễ và độ bền

Một thay đổi encoder có thể làm kích thước record tăng vì key names và structured metadata, hoặc giảm nếu bỏ nhiều message trùng/stack trace không cần thiết. Cần đo:

- Log events/s và average/percentile bytes per event.
- Formatter/encoder CPU, allocations/op, GC, throughput.
- Số lượng request logs và exceptions; log level không tạo ra business SLIs.
- Async queue depth, drops, backpressure, export retries.
- Collector parse errors, mapping rejects, ingest lag.
- Storage/index cost và query latency.
- Impact đến p95/p99 request latency trong trường hợp sink chậm.
- Encoding/decoding tiếng Việt và các trường đặc biệt.

Một event JSON lớn được in ra stdout có thể vẫn được container runtime chia chunk khi vượt giới hạn của logging driver hoặc Collector. **Một lần gọi `System.out.print` không phải hợp đồng giao log nguyên tử end-to-end** trên mọi môi trường. Vì vậy hạn chế record size, kiểm framing/aggregation, chọn shipper và sink đúng tải.

### Delivery semantics

Có thể có các tình huống:

- App in xong nhưng process crash trước khi agent đọc.
- Agent đọc nhưng ACK đích chưa tới, sau đó retry tạo duplicate.
- Collector nhận nhưng backend chưa index; search ngay có thể trả rỗng.
- Log sample/filter làm event không được sinh hoặc không được giữ.
- File rotate/xóa trước khi shipper đọc phần còn lại.

JSON output giải quyết **format/schema**, không tự bảo đảm **at-least-once**, exactly-once hay atomicity với transaction nghiệp vụ. Với audit bắt buộc, cần audit store/outbox và hợp đồng durability riêng, không chỉ một JSON INFO event.

## 18. Tình huống chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm |
| --- | --- | --- |
| Console vẫn là text | Encoder không được load, sai config path, nhầm backend | Kiểm dependency, provider, startup config diagnostics |
| Không có log nào | Logger/appender level lọc, appender không gắn root | Kiểm logger + handler/appender + additivity |
| JSON không parse được | Nối chuỗi thô, dấu nháy/newline không escape, record bị cắt | Parse từng dòng, kiểm encoder, max size |
| Stack trace thành nhiều records | Dùng text formatter/shipper line input | JSON exception converter hoặc multiline policy |
| Backend chỉ có field `message` chứa JSON text | Collector chưa parse/mapping | Kiểm parser/transform và index fields |
| `request_id` có trong code nhưng không có ở output | Encoder không xuất MDC/context | Kiểm context + encoder + output bytes |
| Request IDs bị lẫn giữa thread | MDC leak hoặc async propagation thiếu | Context scopes, cleanup và tests |
| INFO có nhưng ERROR thiếu | Filter/sampling/output routing cấu hình sai | Kiểm logger/appender, Collector và backend rules |
| Trùng 2 JSON events giống nhau | Root+named logger appenders, stdout+file hoặc shipper retry | Kiểm additivity, source ownership, event IDs |
| JSON parser lỗi vì type | Schema drift hoặc index mapping conflict | Kiểm field types, version và migrations |
| JSON hợp lệ nhưng search không thấy | Ingest lag, sai project/tenant/time, retention/quyền | Xem event vs ingest time, agent/backend metrics |
| Log có token/PII | Call site dump request, encoder ghi mọi MDC field | Data minimization, redaction, field allowlist |
| Tiếng Việt hỏng ký tự | Mismatch charset JDK/terminal/file/agent | Thiết lập UTF-8 xuyên tuyến |
| Backend chi phí tăng mạnh | JSON keys, fields rộng, exceptions lớn, duplicate | Đo bytes/event, event rate và sampling policy |
| JSON output trên local ổn nhưng container bị split | Event quá dài/runtime logging limit | Size cap và integration test trên runtime thật |

Khi incident, đi từ **ứng dụng → encoder → stdout/file → shipper/Collector → backend**. Xác định bước đầu tiên mà event ID không còn thấy được, đừng sửa dashboard query trước khi biết dữ liệu đã được ingest đúng schema hay chưa.

## 19. Kịch bản kiểm thử thực hành

### A. Kiểm giá trị và escaping

- [ ] Có đúng 3 dòng JSON vật lý sau khi chạy demo.
- [ ] Mỗi dòng được parse thành một JSON object.
- [ ] `timestamp` là ISO-8601 có `Z`.
- [ ] Severity là `INFO`, `WARNING`, `SEVERE` theo thứ tự.
- [ ] `event.name` lần lượt `order.accepted`, `payment.retry`, `payment.failed`.
- [ ] Event đầu có message chứa dấu nháy và newline **logic** nhưng chỉ một line vật lý.
- [ ] Event thứ hai có `error.code=DOWNSTREAM_TIMEOUT`.
- [ ] Event thứ ba có `exception.type=java.lang.IllegalStateException`.
- [ ] Không có string `"null"` hoặc dấu phẩy thừa trong JSON.
- [ ] Không có output từ parent JUL handler làm xuất text thêm.

### B. Kiểm framework

- [ ] Logback/Log4j2 config load đúng, encoder dependency có ở runtime.
- [ ] JSON fields được backend parse theo schema đã chốt.
- [ ] Logger severity, exception formatting và MDC được encode đúng.
- [ ] Parent/additivity và stdout/file ownership không làm duplicate.
- [ ] Switch giữa text và JSON có rollout/rollback, không phá alert/search query.
- [ ] Log source có thống nhất UTF-8 và line framing.
- [ ] Đã thử secret/PII redaction tại nguồn và ở Collector.
- [ ] Source metadata service/environment/version đáng tin và không bị client ghi đè.

### C. Kiểm lỗi và quan sát end-to-end

- [ ] Gửi event canary có event ID duy nhất, tìm lại trong backend bằng ID.
- [ ] Collector parse lỗi JSON sẽ báo metric/alert chứ không âm thầm bỏ.
- [ ] Mất network, backend 429/503, queue full, restart không dẫn tới kết luận giả về delivery.
- [ ] Log retention và quyền search/export đúng scope.
- [ ] Thread pool/async requests không trộn request/trace IDs.
- [ ] Event size limit và Throwable stack lớn được xử lý đúng policy.
- [ ] Request metrics (count/error/latency) được kiểm độc lập với log line counts.
- [ ] Với audit/security events bắt buộc, đường lưu bền không phụ thuộc INFO filtering/sampling.

## 20. Bài mở rộng: tăng độ thực tế cho JSON output

Sau khi demo cơ bản chạy đúng, có thể tiến hành những mở rộng sau theo từng bước và kiểm bằng parser/tests:

1. **Thêm `schema_version`:** giúp backend xử lý migration khi thêm/bớt/đổi tên fields.
2. **Thêm trường số:** `http.status_code` dạng number và `duration_ms` dạng numeric, không ép thành string.
3. **Thêm Throwable stack trace:** encode trong một JSON string field đã redaction và giới hạn kích thước.
4. **Thêm context propagation:** request ID/trace ID riêng cho mỗi request, dùng scope và cleanup đúng qua async tasks.
5. **Thêm formatter UTF-8/file sink:** lưu JSONL và kiểm shipper đọc theo byte offset/rotation.
6. **Thêm schema contract tests:** fail build nếu event quan trọng thiếu field hoặc sai type.
7. **Thêm integration test Collector:** event vào backend truy được theo `event.name`/`request_id` với timeout và self-metrics.
8. **Thêm JSON encoder production:** thay custom formatter bằng thư viện được kiểm chứng, so sánh output/số trường/hiệu năng.
9. **Thêm security tests:** token, raw URL và secret trong exception không lọt qua formatter/collector.
10. **Thêm dashboard/query:** tìm `payment.failed` theo service và time window, nhóm theo error code, nối trace khi có.

Không xem thay đổi thành công chỉ vì stdout bắt đầu bằng ký tự `{`. Mốc hoàn thành là **parse đúng từng event, schema ổn định, context đáng tin, không lộ dữ liệu nhạy cảm và event thật sự truy vấn được ở đích**.

## 21. Các sai lầm thường gặp khi “thêm JSON output”

| Sai lầm | Hệ quả | Giải pháp |
| --- | --- | --- |
| Tự nối string `"{\"message\":\"" + message + "\"}"` | Quotes/newline phá JSON, log injection | Dùng JSON encoder/serializer chuẩn |
| Chỉ bọc message text trong JSON | Không có structured fields để search | Event name, code, service, correlation là keys riêng |
| Dùng `json.load` cho toàn JSONL file | Parser báo dữ liệu dư | Parse từng dòng bằng `json.loads` |
| Ghi stack trace thành nhiều dòng vật lý | Một lỗi thành nhiều events | Escape stack trong field hoặc multiline handling |
| Ghi `"status":"503"` khi schema yêu cầu number | Range/aggregation có thể sai | Serialize đúng JSON type |
| Mọi field tùy chọn đều là `"null"` | Query nhầm giá trị thiếu thành literal | Omit hoặc dùng JSON null theo schema |
| Không cấu hình encoder vào root appender | Vẫn thấy text logs | Kiểm backend/runtime config |
| Chuyển Logback XML sang Log4j2 | Layout/plugin không nhận | Dùng cấu hình đúng backend |
| Cho rằng SLF4J placeholder tự thành JSON fields | Message vẫn là string | Structured arguments/MDC với encoder phù hợp |
| Gắn toàn bộ MDC vào output không lọc | Có thể lộ token/tenant data | MDC allowlist, trusted fields, cleanup |
| Dùng trace ID cố định cho mọi request | Correlation sai | Propagate trace context thực |
| Log raw request body/headers ở DEBUG | Lộ secret khi bật diagnostic | Data minimization ở mọi level |
| Không chỉnh Collector parser | JSON nằm nguyên trong message, search field không có | JSON parsing/enrichment/mapping |
| Thu cùng event từ file và stdout | Duplicate records, tăng chi phí | Single collection path/dedup |
| Giả định JSON đã bảo đảm audit durability | Log vẫn mất vì crash/filter/drop | Outbox/audit storage riêng |
| Không kiểm ingest lag/retention | Nghĩ log không xuất hiện là không có event | Event ID canary và pipeline metrics |

## 22. Checklist hoàn thành bài thực hành

- [ ] Đã biên dịch và chạy thành công `JsonOutputDemo.java` bằng Java 17+?
- [ ] Output là **3 JSON Lines**, mỗi log record một dòng vật lý?
- [ ] Message có dấu nháy/newline được escape, parser không lỗi?
- [ ] Có timestamp, severity, logger, service, event name và correlation fields?
- [ ] Error code và exception type chỉ xuất khi có ý nghĩa?
- [ ] Đã phân biệt key có kiểu và message text; không “giả structured” bằng regex?
- [ ] Đã biết schema output cần phù hợp với index/Collector/backend?
- [ ] Có quyết định stdout/file/OTLP phù hợp và tránh thu thập trùng?
- [ ] Nếu dùng Logback/Log4j2, JSON encoder/layout và dependency đúng phiên bản?
- [ ] Đã kiểm logger/handler/appender level và output thật, không chỉ XML?
- [ ] Có giới hạn field size, escaped control chars, xử lý UTF-8 và Throwable?
- [ ] Không có token, password, cookie hoặc PII không cần thiết trong logs?
- [ ] Correlation ID đến từ context đáng tin và không bị leak qua thread pool?
- [ ] Có parser/test để chứng minh mỗi dòng JSON hợp lệ và schema đúng?
- [ ] Có end-to-end canary chứng minh log được ingest/query ở backend?
- [ ] Đã đo parse failures, drops, queue, throughput và log cost sau rollout?
- [ ] Audit bắt buộc được bảo vệ bằng tuyến lưu giữ/durability riêng nếu cần?

**Kết luận:** thêm JSON output là bước chuyển từ **dòng text khó phân tích** sang **log events có cấu trúc**. Trong Java, điều quan trọng không chỉ là một formatter xuất dấu `{` và `}`, mà là **một event/một dòng JSON hợp lệ**, schema với trường có nghĩa, escape đúng, dữ liệu nhạy cảm được loại từ nguồn và parser/backend hiểu đúng field. Hãy bắt đầu từ ví dụ JUL chạy độc lập, kiểm JSON Lines bằng parser, sau đó dùng JSON encoder phù hợp với Logback/Log4j2 hoặc telemetry stack trong production. Đó mới là nền tảng để search, correlate, alert và điều tra sự cố đáng tin.
