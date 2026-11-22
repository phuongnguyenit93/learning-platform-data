# Structured logging là gì? Cách ghi log có cấu trúc trong Java

## 1. Khái niệm

**Structured logging (ghi log có cấu trúc)** là cách biểu diễn mỗi sự kiện log thành **các trường có tên, kiểu và ý nghĩa rõ ràng** thay vì chỉ ghi một chuỗi văn bản tự do. Một log tốt thường có timestamp, level, service, logger, event_code, message, request_id hoặc trace_id, cùng những dữ liệu nghiệp vụ hữu ích và được phép lưu.

Ví dụ log văn bản:

~~~text
2026-11-09 12:34:56 INFO Checkout created order ORD-42, amount 12500 VND, request req-42
~~~

Cùng sự kiện ở dạng có cấu trúc:

~~~json
{
  "timestamp": "2026-11-09T12:34:56.789Z",
  "level": "INFO",
  "service": "checkout",
  "logger_name": "com.example.orders.OrderService",
  "event_code": "ORDER_CREATED",
  "message": "Order created",
  "request_id": "req-42",
  "order_id": "ORD-42",
  "amount_minor": 12500,
  "currency": "VND",
  "outcome": "success"
}
~~~

Hệ thống thu thập có thể tìm theo **event_code = ORDER_CREATED**, lọc theo currency hoặc tính tổng amount_minor mà không cần parse một câu tiếng Anh có thứ tự từ ngữ thay đổi.

**Structured logging không chỉ là việc đặt dấu ngoặc nhọn JSON quanh message.** Giá trị chính là **schema**, tên trường ổn định, kiểu dữ liệu có ý nghĩa, cách truyền correlation context và khả năng bảo toàn các field xuyên suốt pipeline từ ứng dụng đến collector.

JSON là định dạng phổ biến, nhưng log có cấu trúc cũng có thể dùng **logfmt/key-value** hoặc một định dạng sự kiện khác. Ứng dụng vẫn nên giữ một **message ngắn dễ đọc**, trong khi field và event code phục vụ máy phân tích.

## 2. Vì sao structured logging hữu ích?

### Tìm kiếm theo thuộc tính

Log tự do có thể có nhiều cách viết:

~~~text
Payment retry attempt 2 for ORD-42: gateway timeout
Retry #2 after timeout, order=ORD-43
Gateway error on second request for ORD-44
~~~

Nếu chỉ có text, cần regex hoặc full-text search và dễ bỏ sót. Với một schema thống nhất, các event đều có thể là:

~~~json
{
  "event_code": "PAYMENT_RETRY",
  "operation": "authorize",
  "attempt": 2,
  "reason_code": "GATEWAY_TIMEOUT",
  "outcome": "retrying"
}
~~~

Truy vấn theo **event_code** và **attempt** không phụ thuộc câu message.

### Liên kết nhiều dịch vụ

Một request đi qua Gateway → Order Service → Payment Service có thể phát nhiều log. Nếu các event chia sẻ request_id/trace_id hợp lệ, người vận hành có thể gom chúng lại và xem những bước đã xảy ra.

### Thống kê và cảnh báo

Field có kiểu number/boolean giúp nhóm và lọc theo condition. Event code ổn định làm dashboard ít hỏng khi message thay đổi. Nhưng **structured logs không tự bảo đảm không mất sự kiện**; nếu có sampling, queue drop hay lỗi collector, đếm bản ghi log không phải lúc nào cũng là số request tuyệt đối. Metrics vẫn cần thiết.

### Tối ưu điều tra

Một error event có **operation, reason_code, error_type, release, instance_id** giúp thu hẹp phạm vi rất nhanh. Tuy nhiên, thêm nhiều field không cần thiết có thể làm tăng chi phí và rủi ro lộ dữ liệu. Nên chọn field có giá trị chẩn đoán rõ ràng.

## 3. So sánh với log văn bản truyền thống

| Tiêu chí | Unstructured log | Structured log |
| --- | --- | --- |
| Dữ liệu | Message tự do | Field có tên |
| Truy vấn | Regex/full-text | Truy vấn theo trường |
| Mã sự kiện | Thường nằm trong câu chữ | event_code riêng |
| Kiểu dữ liệu | Phần lớn là String | Number, Boolean, String, null |
| Tương quan | ID nhúng vào message | request_id/trace_id rõ ràng |
| Ổn định | Sửa câu chữ dễ hỏng parser | Schema có thể duy trì tương thích |
| Dung lượng | Có thể ít metadata | Thường nhiều metadata hơn |
| Rủi ro | Khó parse, thiếu context | Cardinality, privacy, schema drift |

Một JSON chỉ chứa:

~~~json
{"message":"Order ORD-42 created for 12500 VND"}
~~~

vẫn buộc parser đọc chuỗi message để biết order_id và amount. Đó là ví dụ **JSON hợp lệ nhưng chưa có cấu trúc trường hữu ích**.

## 4. Các dạng biểu diễn phổ biến

### JSON

JSON hỗ trợ:
- **String:** event_code, service, request_id.
- **Number:** duration_ms, amount_minor, attempt.
- **Boolean:** cache_hit.
- **null:** Giá trị không có, nếu schema cho phép.
- **Object/Array:** Dữ liệu lồng nhau có giới hạn, khi thực sự cần.

~~~json
{
  "event_code": "CACHE_LOOKUP",
  "cache_hit": true,
  "duration_ms": 12,
  "attempt": 1,
  "tags": ["orders", "cache"]
}
~~~

**duration_ms phải là number 12**, không nên là chuỗi **"12ms"** nếu muốn máy tính toán mà không parse lại.

### JSON Lines

File logging thường dùng **mỗi JSON object một dòng**:

~~~json
{"event_code":"ORDER_CREATED","order_id":"ORD-42"}
{"event_code":"PAYMENT_RETRY","attempt":2}
{"event_code":"PAYMENT_FAILED","outcome":"failed"}
~~~

JSON serializer phải escape dấu quote, backslash, newline và control characters. Newline nằm trong một message không được tùy tiện chia thành hai record file. Khi collector đọc theo dòng, một event phải được giữ thành một JSON object hợp lệ.

### Key-value / logfmt

~~~text
level=INFO event_code=ORDER_CREATED order_id=ORD-42 amount_minor=12500 currency=VND
~~~

Kiểu này gọn, dễ xem bằng mắt nhưng parser cần quy ước escape và dữ liệu có kiểu. Không tự cho rằng tất cả hệ thống logfmt hiểu số và Boolean giống nhau.

## 5. Thiết kế schema: những trường thường dùng

| Field | Ví dụ | Công dụng |
| --- | --- | --- |
| **timestamp** | 2026-11-09T12:34:56.789Z | Event time, thường dùng UTC |
| **level** | INFO, WARN, ERROR | Mức ưu tiên |
| **service** | checkout | Nguồn phát |
| **environment** | production | Môi trường |
| **logger_name** | com.example.orders.OrderService | Class/package phát sự kiện |
| **event_code** | ORDER_CREATED | Mã sự kiện ổn định |
| **message** | Order created | Mô tả đọc được |
| **request_id** | req-42 | Liên kết yêu cầu |
| **trace_id / span_id** | ID từ tracing | Liên kết luồng phân tán |
| **operation** | createOrder | Thao tác |
| **outcome** | success, failed, retrying | Kết quả |
| **duration_ms** | 35 | Số đo có đơn vị |
| **error_type** | IOException | Loại exception |
| **reason_code** | GATEWAY_TIMEOUT | Nguyên nhân có thể phân loại |
| **release** | 1.8.3 | Phiên bản ứng dụng |
| **instance_id** | checkout-pod-7 | Instance/pod |

Không bắt buộc mọi event có đủ tất cả các trường. **ORDER_CREATED** nên có order_id; **PAYMENT_RETRY** cần attempt hoặc reason_code; **SERVICE_STARTED** thường có release. Chọn trường theo ý nghĩa sự kiện.

### Quy ước đặt tên

- Dùng một phong cách nhất quán như **snake_case**.
- Với số đo, đặt tên có đơn vị như **duration_ms**, **size_bytes** hoặc **amount_minor**.
- Không để cùng field lúc mang number **200**, lúc mang String **"success"**.
- Đặt **event_code** trong tập giá trị ổn định, không sinh tên mới chứa request_id.
- Phân biệt **status_code** với **outcome**; hai trường không có cùng ý nghĩa.
- Tránh copy toàn bộ Java object/domain entity vào JSON nếu chỉ cần vài trường.
- Không đưa secret, dữ liệu nhạy cảm hoặc payload chưa được phê duyệt vào field.

## 6. Event code và message

**Event code** dùng cho máy phân loại; **message** dùng cho con người.

Ví dụ các event code:
- SERVICE_STARTED
- ORDER_CREATED
- ORDER_VALIDATION_FAILED
- PAYMENT_RETRY
- PAYMENT_AUTHORIZATION_FAILED
- PAYMENT_RECOVERED

Nếu lập trình viên sửa message từ **Payment failed** thành **Payment authorization failed**, truy vấn theo event_code không cần đổi. Đây là một trong những lợi ích thiết yếu của structured logging.

Không đặt event_code thành giá trị động như **PAYMENT_FAILED_ORD-42**. Khi đó mỗi order có thể tạo một event code duy nhất, khiến phân nhóm không còn ý nghĩa.

## 7. Timestamp trong structured log

Dạng **UTC ISO 8601** dễ trao đổi:

~~~text
2026-11-09T12:34:56.789Z
~~~

Ký hiệu Z biểu thị UTC. Nếu lưu thời gian địa phương, cần UTC offset/ZoneId rõ ràng. Không để timestamp không timezone rồi yêu cầu người xem đoán máy phát log thuộc vùng nào.

Phân biệt:
- **Event time:** Khi ứng dụng ghi nhận sự kiện.
- **Ingestion time:** Khi hệ thống collector nhận dữ liệu.

Chúng khác nhau khi có queue, mạng hoặc batch. Nếu cần giữ cả hai, đặt tên field khác nhau, tránh thay thế event time bằng ingestion time.

Khi đo duration trong Java, dùng nguồn phù hợp như **System.nanoTime()** để đo khoảng thời gian, không lấy giá trị đó làm Unix timestamp. Một field **duration_ms** cần thực sự là số milli giây.

## 8. Level vẫn có vai trò

Structured logging không xóa bỏ khái niệm INFO, WARN, ERROR hay DEBUG.

| Tình huống | Level thường phù hợp |
| --- | --- |
| Startup và sự kiện vận hành quan trọng | INFO |
| Retry tạm thời được phục hồi | DEBUG hoặc WARN tùy ảnh hưởng |
| Fallback dẫn tới suy giảm | WARN |
| Thao tác cuối cùng thất bại | ERROR |
| Chẩn đoán nội bộ chi tiết | DEBUG/TRACE |

Với JUL, tên mức thường là **INFO, WARNING, SEVERE, FINE**; trong SLF4J thường là **INFO, WARN, ERROR, DEBUG**. Khi nhiều backend đổ vào một schema chung, cần quy định cách biểu diễn severity.

**Không coi mỗi lần retry lỗi là một operation cuối thất bại.** Một request có thể retry hai lần rồi thành công; event_code và outcome phải phản ánh đúng kết quả.

## 9. Java 17: ví dụ độc lập tạo structured JSON

Ví dụ dùng **java.util.logging** có sẵn trong JDK 17. Một Handler đọc các field theo quy ước của ví dụ và ghi một JSON object trên mỗi dòng **stdout**. Timestamp cố định để kiểm tra kết quả; dữ liệu số vẫn là Number. Đây là demo giáo dục, không phải JSON serializer production đầy đủ.

Tạo file **StructuredLoggingDemo.java**:

~~~java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class StructuredLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.orders.OrderService");

    public static void main(String[] args) {
        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.println(toJson(record));
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

        output.setLevel(Level.ALL);
        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(output);

        try {
            Map<String, Object> order = new LinkedHashMap<>();
            order.put("order_id", "ORD-42");
            order.put("amount_minor", 12500);
            order.put("currency", "VND");

            emit(Level.INFO, "2026-11-09T12:34:56.789Z",
                    "ORDER_CREATED", "Order created", "req-42", order);

            Map<String, Object> retry = new LinkedHashMap<>();
            retry.put("attempt", 2);
            retry.put("reason", "retry after \"timeout\"");

            emit(Level.WARNING, "2026-11-09T12:34:56.790Z",
                    "PAYMENT_RETRY", "Gateway timeout; retrying",
                    "req-42", retry);
        } finally {
            LOG.removeHandler(output);
            output.close();
        }
    }

    private static void emit(
            Level level,
            String timestamp,
            String code,
            String message,
            String requestId,
            Map<String, Object> fields) {

        LogRecord record = new LogRecord(level, message);
        record.setLoggerName(LOG.getName());
        record.setInstant(Instant.parse(timestamp));
        record.setParameters(new Object[] {code, requestId, fields});
        LOG.log(record);
    }

    private static String toJson(LogRecord record) {
        Object[] values = record.getParameters();
        String code = (String) values[0];
        String requestId = (String) values[1];
        Map<?, ?> fields = (Map<?, ?>) values[2];

        return "{"
                + "\"timestamp\":" + quote(record.getInstant().toString())
                + ",\"level\":" + quote(record.getLevel().getName())
                + ",\"logger_name\":" + quote(record.getLoggerName())
                + ",\"service\":\"checkout\""
                + ",\"environment\":\"demo\""
                + ",\"event_code\":" + quote(code)
                + ",\"message\":" + quote(record.getMessage())
                + ",\"request_id\":" + quote(requestId)
                + ",\"fields\":" + fieldsJson(fields)
                + "}";
    }

    private static String fieldsJson(Map<?, ?> fields) {
        StringBuilder out = new StringBuilder("{");
        boolean first = true;

        for (Map.Entry<?, ?> entry : fields.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote((String) entry.getKey()))
                    .append(':')
                    .append(valueJson(entry.getValue()));
        }

        return out.append('}').toString();
    }

    private static String valueJson(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String) {
            return quote((String) value);
        }
        if (value instanceof Integer
                || value instanceof Long
                || value instanceof Boolean) {
            return value.toString();
        }
        throw new IllegalArgumentException(
                "Unsupported demo JSON type: " + value.getClass());
    }

    private static String quote(String text) {
        StringBuilder out = new StringBuilder("\"");

        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);

            switch (c) {
                case '"':
                    out.append("\\\"");
                    break;
                case '\\':
                    out.append("\\\\");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        String hex = Integer.toHexString(c);
                        out.append("\\u");
                        for (int j = hex.length(); j < 4; j++) {
                            out.append('0');
                        }
                        out.append(hex);
                    } else {
                        out.append(c);
                    }
            }
        }

        return out.append('"').toString();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StructuredLoggingDemo.java
java StructuredLoggingDemo
~~~

**Stdout chính xác:**

~~~json
{"timestamp":"2026-11-09T12:34:56.789Z","level":"INFO","logger_name":"demo.orders.OrderService","service":"checkout","environment":"demo","event_code":"ORDER_CREATED","message":"Order created","request_id":"req-42","fields":{"order_id":"ORD-42","amount_minor":12500,"currency":"VND"}}
{"timestamp":"2026-11-09T12:34:56.790Z","level":"WARNING","logger_name":"demo.orders.OrderService","service":"checkout","environment":"demo","event_code":"PAYMENT_RETRY","message":"Gateway timeout; retrying","request_id":"req-42","fields":{"attempt":2,"reason":"retry after \"timeout\""}}
~~~

**Giải thích từng phần:**

1. Logger ở **INFO**, nên cả INFO và WARNING được chấp nhận.
2. Handler tự viết xuất **System.out**, tránh khác biệt của ConsoleHandler JUL vốn thường xuất stderr.
3. **LOG.setUseParentHandlers(false)** ngăn Logger cha xuất thêm bản ghi trùng.
4. **setInstant(...)** sử dụng timestamp cố định nhằm làm stdout có thể kiểm chứng.
5. **setParameters(...)** lưu event code, request ID và Map theo **quy ước của ví dụ**; JUL không mặc định cung cấp schema JSON nghiệp vụ này.
6. **LinkedHashMap** bảo đảm thứ tự trường nghiệp vụ trong stdout.
7. **amount_minor** và **attempt** là số JSON, không phải chuỗi.
8. Phương thức **quote** escape dấu ngoặc kép và control characters; vì thế reason có chứa **"timeout"** vẫn được xuất hợp lệ.
9. Demo không dùng thư viện JSON ngoài và không mở file. Trong production, chọn serializer/encoder JSON đã được kiểm thử thay vì dùng phương thức quote tự viết này cho mọi kiểu dữ liệu.
10. Với ký tự Unicode surrogate không hợp lệ, object lồng nhau hoặc dữ liệu từ bên ngoài, cần một encoder JSON chuẩn có validation và quy tắc giới hạn kích thước.

**Sự khác biệt lớn:** Việc JUL có **LogRecord.parameters** không biến JUL thành một API structured JSON đầy đủ. Mã demo chủ động diễn giải parameters thành field. Khi dùng backend thực tế, nên chuẩn hóa cách truyền field và output.

## 10. SLF4J 2.x và key-value pairs

**SLF4J** là logging facade; trong **SLF4J 2.x**, fluent API hỗ trợ thêm field có tên:

~~~java
log.atInfo()
        .addKeyValue("event_code", "ORDER_CREATED")
        .addKeyValue("order_id", orderId)
        .addKeyValue("amount_minor", amountMinor)
        .addKeyValue("currency", "VND")
        .log("Order created");
~~~

Đây là đoạn mã minh họa trong class có Logger **log** và các biến liên quan. Nó cần SLF4J 2.x; không phải chương trình độc lập.

**addKeyValue không tự bảo đảm output JSON.** Provider/Backend và encoder/layout phải được cấu hình để xuất các key-value pairs vào stdout, file hoặc collector.

Với exception:

~~~java
log.atError()
        .addKeyValue("event_code", "ORDER_SAVE_FAILED")
        .addKeyValue("order_id", orderId)
        .addKeyValue("outcome", "failed")
        .setCause(exception)
        .log("Failed to persist order");
~~~

**setCause(exception)** giữ Throwable để backend có thể xuất stack trace và cause chain. Tránh chỉ truyền **exception.getMessage()** khi cần nguyên nhân kỹ thuật.

SLF4J 1.7 không có API fluent giống SLF4J 2.x; nó thường dùng các overload logger với placeholder và Throwable. Trước khi sao chép ví dụ, phải xác định thế hệ SLF4J của dự án và provider đã chọn.

## 11. MDC, ThreadContext và correlation

**MDC (Mapped Diagnostic Context)** của SLF4J thường dùng để lưu ngữ cảnh request:

~~~java
import org.slf4j.MDC;

MDC.put("requestId", requestId);
try {
    processRequest();
} finally {
    MDC.remove("requestId");
}
~~~

Đây là đoạn minh họa yêu cầu biến/method tương ứng. Encoder/layout phải được cấu hình lấy dữ liệu MDC; chỉ gọi MDC.put không đảm bảo log đã có field JSON request_id.

Với Log4j 2, một API tương tự là **ThreadContext**:

~~~java
import org.apache.logging.log4j.ThreadContext;

try (var scope = ThreadContext.putCloseable("requestId", requestId)) {
    processRequest();
}
~~~

Đoạn này yêu cầu Log4j 2 API; scope dùng để quản lý vòng đời context.

### Ranh giới bất đồng bộ

Không mặc định MDC truyền qua **ExecutorService, CompletableFuture, message queue** hoặc process khác. Khi cần cùng request_id/trace_id, phải có cơ chế context propagation hợp lệ. Với distributed tracing, ưu tiên lấy trace_id/span_id từ tracing context thực thay vì tự tạo ID không liên quan rồi gọi nó là trace.

Thread pool có thể tái sử dụng thread. **Luôn dọn MDC theo lifecycle**, tránh một request có ID của request trước. Không đặt token hoặc dữ liệu nhạy cảm trong MDC vì giá trị có thể xuất hiện ở mọi dòng log.

### Request ID và trace ID khác gì?

- **request_id:** ID của một yêu cầu theo ứng dụng.
- **trace_id:** ID chung cho một trace xuyên nhiều dịch vụ.
- **span_id:** ID của một span cụ thể.
- **correlation_id:** ID theo hợp đồng nghiệp vụ/hệ tích hợp.

Chúng có thể hỗ trợ nhau nhưng không hoàn toàn thay thế nhau. Một request có thể phát nhiều span hoặc thông điệp bất đồng bộ; cần định nghĩa phạm vi từng ID.

## 12. Logback và Log4j 2 có cấu hình gì?

### Logback

Logback có Appender và Encoder. **PatternLayoutEncoder** chủ yếu tạo văn bản; muốn JSON có cấu trúc nên dùng JSON encoder được hỗ trợ và kiểm thử tương thích với phiên bản Logback của dự án.

Ví dụ dưới đây minh họa một cấu hình **text** trong logback.xml, **không phải JSON**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} trace=%X{traceId} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Pattern có MDC traceId nhưng không tự biến toàn bộ dữ liệu thành các JSON field. Muốn structured JSON phải cấu hình encoder/layout thật sự hỗ trợ JSON, đồng thời kiểm tra key-value pairs, MDC và Throwable có được giữ đúng không.

### Log4j 2

Log4j 2 hỗ trợ các Layout, trong đó có lựa chọn như **JsonTemplateLayout** khi module phù hợp được cài đặt. Có thể thiết kế template để ghi timestamp, level, logger, context và exception theo schema yêu cầu. Cấu hình log4j2.xml, dependency và layout khác Logback.

Không thêm tùy tiện nhiều provider SLF4J hoặc bridge hai chiều trong một ứng dụng, vì sự kiện có thể bị định tuyến sai, lặp hoặc không xuất hiện.

### Kiểm thử thật

Đừng kết luận structured logging đã hoạt động chỉ vì API gọi addKeyValue. Cần đọc file/stdout, parse JSON và xác minh field đã xuất đúng tên, kiểu, giá trị và context. Sau đó đưa qua collector thử nghiệm để xác nhận không bị bỏ hoặc đổi type.

## 13. Structured exception logging

Một event lỗi nên mô tả:
- **operation:** Thao tác thất bại.
- **event_code:** Mã lỗi ổn định.
- **reason_code:** Phân loại có kiểm soát.
- **error_type:** Loại Throwable.
- **outcome:** Thất bại cuối hay chỉ một attempt retry.
- **request_id/trace_id:** Ngữ cảnh điều tra.
- **cause/stack trace:** Thông tin kỹ thuật nếu cần.

~~~json
{
  "level": "ERROR",
  "event_code": "PAYMENT_AUTHORIZATION_FAILED",
  "reason_code": "GATEWAY_TIMEOUT",
  "error_type": "IOException",
  "operation": "authorize",
  "outcome": "failed",
  "request_id": "req-42",
  "message": "Authorization failed"
}
~~~

Đây là một ví dụ event; trường chứa stack trace phụ thuộc encoder thực tế. Không nên log ERROR cho mọi retry đã phục hồi. Một thao tác có thể thất bại ba attempt nhưng cuối cùng thành công; nếu dashboard đếm mỗi attempt thành operation failed thì tỷ lệ lỗi bị sai.

Tránh cùng một exception được ghi ở Repository, Service và Controller mà không thêm thông tin hữu ích. Chọn ranh giới chịu trách nhiệm kết quả cuối; ghi chẩn đoán chi tiết ở mức phù hợp và giữ Throwable đúng cách.

## 14. Cardinality và index

**Cardinality** là số giá trị phân biệt của một field. Những trường như **level**, **outcome**, **event_code**, **service** thường có tập giá trị hữu hạn. **request_id, trace_id, order_id** có thể chứa rất nhiều giá trị khác nhau.

Cardinality cao không có nghĩa trường đó vô ích: request_id rất hữu ích để tìm một yêu cầu. Tuy nhiên không nên đưa request_id vào **metric label** có cardinality cực cao khiến số time series bùng nổ.

Phân biệt:
- Trường được lưu trong log.
- Trường được index để tìm kiếm.
- Metric label dùng để nhóm số liệu.

Không index mọi field vô điều kiện. Chọn theo nhu cầu truy vấn và chi phí thực. Một event_code không nên kèm dữ liệu động như **ORDER_CREATED_ORD-42** vì như thế làm danh mục mã sự kiện mất ý nghĩa.

### Dung lượng

Giả sử ứng dụng xuất **1.000 JSON events/giây**, mỗi dòng có trung bình **700 byte** sau UTF-8 encoding:

~~~text
1.000 × 700 = 700.000 byte/giây
700.000 × 86.400 = 60,48 GB/ngày dữ liệu thô
~~~

Chưa tính index, sao chép và retention. Structured log có thể nhiều metadata hơn plain text, nên cân bằng giữa độ chi tiết, chi phí ingest, khả năng tìm kiếm và thời gian lưu.

## 15. Quy tắc bảo vệ dữ liệu

Structured logging làm dữ liệu dễ truy vấn hơn, nên **bảo vệ dữ liệu** rất quan trọng:

- Không log mật khẩu, API key, access token, refresh token, private key.
- Không ghi nguyên cookie, Authorization header hoặc thông tin thanh toán nhạy cảm.
- Không copy raw request/response body nếu không có mục đích được phê duyệt.
- Chỉ giữ các ID kỹ thuật cần thiết và được phép.
- Có redaction/allowlist field, access control, retention và audit truy cập.
- Giới hạn kích thước message/field để tránh log quá lớn hoặc log injection.

**UTF-8 và JSON không phải encryption.** Dữ liệu nhạy cảm trong JSON vẫn có thể bị đọc nếu một tài khoản có quyền xem log. Hash một trường không mặc nhiên làm nó an toàn hoặc không thể tái định danh.

### Log injection

Một message do người dùng cung cấp có thể chứa newline, quote hoặc ký tự điều khiển, làm hỏng JSON lines hoặc tạo dòng giả dạng ERROR. Dùng serializer JSON chuẩn để escape và validate dữ liệu, không nối trực tiếp raw input vào cấu trúc output.

## 16. Collector và chất lượng dữ liệu đầu cuối

Pipeline thường có dạng:

~~~text
Java application
      |
      v
JSON log trên stdout hoặc file
      |
      v
Agent/collector
      |
      v
Parser/schema mapping
      |
      v
Storage và index
      |
      v
Query/dashboard/alert
~~~

Các lỗi có thể xảy ra:
- JSON writer vô tình in prefix text trước dấu mở object.
- Message có newline không escape.
- Collector biến number thành string.
- Có field bị bỏ do giới hạn kích thước hoặc whitelist.
- Trường timestamp bị thay bằng ingestion timestamp.
- Nhiều dịch vụ dùng cùng field name nhưng khác type.
- Bản ghi bị cắt do rotation hoặc quá tải.

Vì vậy integration test nên kiểm tra cả **field type và giá trị sau khi ingest**, không chỉ nội dung trong bộ nhớ ứng dụng. Ví dụ trường **attempt: 2** phải vẫn là Number khi truy vấn trong collector.

## 17. Structured logging, metrics và traces

Structured logs, metrics và traces bổ sung cho nhau:

| Nguồn | Mục đích |
| --- | --- |
| **Log** | Bằng chứng sự kiện có ngữ cảnh chi tiết |
| **Metric** | Số lượng, tỷ lệ, latency, SLO |
| **Trace** | Luồng request và các span xuyên dịch vụ |

Nếu một dependency retry ba lần nhưng yêu cầu cuối thành công, log giúp xem nguyên nhân từng retry, metric đo retry rate/latency và trace cho thấy khoảng thời gian của từng bước.

Không dựa hoàn toàn vào số dòng log để suy ra số request: log có thể sampling/drop hoặc ghi trùng một lỗi ở nhiều tầng. Với sự kiện audit bắt buộc, cần pipeline có độ bền và chính sách lưu giữ được xác định riêng; structured logging không tự đảm bảo lưu trữ bất biến.

## 18. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Một JSON chỉ có message | Không truy vấn field được | Tách event_code, outcome, ID |
| amount là "12500 VND" | Khó tính toán | amount_minor number + currency |
| level/outcome không nhất quán | Dashboard sai | Schema chung |
| event_code chứa request ID | Cardinality bùng nổ | Mã ổn định |
| Chỉ gọi addKeyValue nhưng layout bỏ field | Mất dữ liệu | Kiểm tra backend/encoder |
| Không dọn MDC trong thread pool | Sai correlation | finally hoặc scope |
| Không truyền context qua async boundary | Trace bị đứt | Propagation phù hợp |
| Không truyền Throwable | Thiếu stack trace | setCause/overload Throwable |
| Ghi lặp exception nhiều tầng | Nhiễu log | Chọn boundary chịu trách nhiệm |
| Copy toàn bộ payload | Lộ thông tin nhạy cảm | Field allowlist, redaction |
| Nối JSON không escape | Invalid JSON/injection | Serializer chuẩn |
| Không kiểm thử collector | Field/type bị mất | Integration test |
| Index tất cả giá trị động | Chi phí cao | Chọn index theo nhu cầu |
| Chỉ nhìn ERROR để paging | Nhiều cảnh báo giả | Dựa trên impact và metric |
| Dùng JSON log như audit bền vững | Có thể mất sự kiện | Pipeline audit riêng |

## 19. Checklist triển khai structured logging

1. Xác định rõ backend: JUL, SLF4J + Logback, Log4j 2 hoặc stack khác.
2. Định nghĩa schema nền tảng và event_code ổn định.
3. Dùng Number/Boolean/String đúng loại, có đơn vị khi cần.
4. Dùng timestamp UTC rõ timezone.
5. Truyền request_id/trace_id qua các boundary, quản lý lifecycle MDC.
6. Chọn encoder/layout JSON được hỗ trợ và UTF-8 đúng.
7. Gắn Throwable với lỗi cuối, tránh log lặp không giá trị.
8. Không ghi secret, dữ liệu thanh toán hoặc payload nhạy cảm.
9. Thiết lập chính sách schema change, index, cardinality và retention.
10. Kiểm thử collector và truy vấn với dữ liệu thật.
11. Kết hợp metrics/traces để hiểu tỷ lệ lỗi và hành trình request.
12. Theo dõi volume, backpressure, dropped events và parser errors.

## 20. Câu hỏi tự kiểm tra

**1. Structured logging có phải chỉ là in JSON không?**  
Không. Nó cần một schema có field, type và ý nghĩa rõ ràng, được bảo toàn khi lưu trữ.

**2. Vì sao dùng event_code thay vì tìm theo message?**  
Event code ổn định khi câu message thay đổi, giúp truy vấn/alert dễ duy trì.

**3. Vì sao amount_minor nên là number?**  
Để so sánh/tính toán trực tiếp, trong khi currency là field riêng.

**4. SLF4J 2.x addKeyValue có tự xuất JSON không?**  
Không. Provider và encoder/layout phải hỗ trợ.

**5. MDC có tự động truyền qua ExecutorService không?**  
Không nên giả định. Cần context propagation và dọn lifecycle.

**6. Vì sao request_id hữu ích trong log nhưng thường không nên là metric label?**  
Vì cardinality rất cao có thể gây quá nhiều time series.

**7. Structured JSON có bảo vệ access token không?**  
Không. Cần chọn field, redaction, giới hạn quyền và retention.

**8. Tại sao đọc được JSON trong file chưa chắc collector hoạt động đúng?**  
Collector có thể bỏ field, đổi type hoặc parse sai, nên cần test end-to-end.

**9. Ví dụ JUL có nghĩa mọi LogRecord đều có sẵn event_code và order_id?**  
Không. Code demo gắn chúng vào parameters theo quy ước, rồi Handler tự chuyển thành JSON.

**Ghi nhớ:** Structured logging biến sự kiện thành **dữ liệu có thể tìm kiếm và phân tích**, không chỉ là một chuỗi JSON. Thành công phụ thuộc schema rõ ràng, event_code ổn định, context đúng, dữ liệu an toàn, Throwable phù hợp và pipeline giữ nguyên field/type. Khi kết hợp với metrics và traces, log có cấu trúc giúp điều tra ứng dụng Java hiệu quả hơn.
