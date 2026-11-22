# Kiểm thử structured field trong Java Logging

## 1. Structured field là gì và vì sao phải kiểm thử?

**Structured logging** biểu diễn sự kiện dưới dạng **các trường có tên, kiểu dữ liệu và ngữ nghĩa rõ**, thay vì chỉ một câu văn không ổn định. Ví dụ:

```text
2026-11-10 INFO checkout completed status=200 took 17 ms
```

Dòng trên dễ đọc nhưng hệ thống phân tích phải suy diễn bằng regex. Với log cấu trúc, có thể ghi:

```json
{"timestamp":"2026-11-10T03:15:00Z","level":"INFO","event.name":"checkout.completed","service.name":"checkout-api","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","http.status_code":200,"duration_ms":17,"success":true}
```

Các trường `http.status_code` và `duration_ms` là **number**, `success` là **boolean**, còn timestamp, level và trace ID là **string**. Backend có thể lọc, nhóm và tính toán đúng kiểu mà không cần phân tích message tự do.

**Kiểm thử structured field** là kiểm tra từ lúc ứng dụng xây event đến khi dữ liệu được encoder/collector xuất thành định dạng cuối rằng:

- Đúng **tên trường, kiểu, giá trị, đơn vị đo** và ý nghĩa nghiệp vụ.
- Các trường **bắt buộc không thiếu**, trường tùy chọn xử lý đúng `null`/vắng mặt.
- Không có **trường bí mật hoặc dữ liệu ngoài allowlist** bị thêm vào.
- Chuỗi được **escape đúng**; một event không làm vỡ JSON Lines, không chèn log giả.
- `trace_id`/`span_id`, request ID và MDC được gắn từ **đúng request/thread**.
- Schema không bị thay đổi ngầm do encoder, appender, logging level, async queue hoặc collector.
- Các sự kiện cần ghi thật sự được phát và nhận đúng; không chỉ “mock logger được gọi”.

Tên trường minh họa trong bài là một **contract do ứng dụng chọn**. OpenTelemetry, ECS, Logstash và các nền tảng quan sát có những conventions riêng, có thể đổi theo phiên bản. Hãy chốt contract thực tế trước khi viết assertion.

## 2. Phân biệt ba tầng kiểm thử

Một hệ thống Java có thể đi qua:

```text
Business code (action, outcome, timing)
   │
   ▼
Event builder / structured fields / MDC
   │
   ▼
SLF4J facade + backend (Logback / Log4j2 / JUL)
   │
   ▼
Encoder / JSON layout
   │
   ▼
Appender / async queue / file / stdout
   │
   ▼
Collector / parser / enrichment
   │
   ▼
Search / dashboard / alert / export
```

| Tầng kiểm thử | Kiểm tra | Không chứng minh được |
| --- | --- | --- |
| **Unit test event builder** | Field name/type/value; thiếu/sai schema bị từ chối | JSON encoder thật tạo đúng byte, appender có ghi hay không |
| **Integration test backend/encoder** | Chuỗi JSONL/file/stdout, MDC, exception, escape, level/filter | Collector có ingest/index đúng hoặc mất log khi overload không |
| **End-to-end / contract test** | Dữ liệu qua collector đến backend, mapping/index/retention, dashboard query | Mọi bản ghi luôn bền vững dưới mọi tình huống crash nếu chưa kiểm thử |

**Chọn tầng đúng câu hỏi.** Mock `logger.info(...)` kiểm tra rằng API log được gọi, nhưng **không xác nhận** trường `duration_ms` trong JSON cuối là number. Ngược lại, so JSON từ encoder chưa chứng minh collector không chuyển number thành string.

Một bộ test tốt thường có nhiều tầng nhưng **không sao chép toàn bộ test case ở mọi tầng**: unit test kiểm phần logic; một số integration/end-to-end case đại diện kiểm wiring và contract.

## 3. Định nghĩa schema contract trước khi viết test

Chẳng hạn service `checkout-api` chọn contract:

| Trường | Kiểu JSON | Required? | Quy tắc quan trọng |
| --- | --- | --- | --- |
| `timestamp` | string | Có | ISO-8601 có timezone rõ; không phụ thuộc locale máy |
| `level` | string | Có | Tập giá trị thống nhất, ví dụ INFO/WARN/ERROR |
| `event.name` | string | Có | Mã có kiểm soát: `checkout.completed` hoặc `checkout.failed` |
| `service.name` | string | Có | Danh tính service do cấu hình đáng tin, không lấy từ HTTP header |
| `trace_id` | string | Có với các HTTP event trong ví dụ | 32 chữ số hex lowercase theo policy đã chọn |
| `http.status_code` | integer | Có | Mã HTTP 100–599, không phải string `"200"` |
| `duration_ms` | integer | Có | Thời gian không âm, đơn vị mili giây |
| `success` | boolean | Có | `true`/`false`, không phải `"true"` |
| `message` | string | Có trong ví dụ | Thông điệp ngắn an toàn; không chứa raw secret |
| `error.code` | string | Tùy chọn | Mã lỗi ổn định, chỉ có ở event phù hợp |
| `user.id` | string | Tùy chính sách | Có thể là PII; lấy từ principal đáng tin, retention phù hợp |

**Đừng mặc định mọi hệ thống có cùng required fields.** Một log khởi động JVM không có HTTP context thường không có trace ID; lỗi trước khi request đi vào tracing instrumentation cũng vậy. Có thể cần schema theo `event.name`/`event.kind` hoặc chính sách null rõ ràng.

### Điều kiện hợp lệ cần được mô tả cụ thể

- **Tên trường:** `http.status_code` khác `httpStatus` và `status`. Chỉ đổi tên một field có thể làm dashboard hỏng.
- **Kiểu:** `200` là number, `"200"` là string. `null`, thiếu key và chuỗi rỗng không đồng nghĩa.
- **Ngữ nghĩa:** `duration_ms=17` chỉ đúng khi phép đo có cùng thời điểm bắt đầu/kết thúc và đơn vị.
- **Enum:** `level` có thể dùng `WARN` nhưng backend khác dùng `WARNING`; cần adapter/contract rõ.
- **Timestamp:** chuỗi có timezone và parse được; không test bằng `toString()` của ngày theo locale.
- **Correlation:** trace ID đúng format **chưa đủ** để chứng minh thuộc request hiện tại; test cả propagation và isolation.
- **Privacy:** field như `authorization`, `password`, `cookie` không được xuất nếu contract loại chúng.
- **Không tự thêm trường:** thay encoder hoặc library version có thể phát `threadName`, `logger_name`, `caller_data`; xác định trường nào được chấp nhận hay cần normalize.

Khi team dùng JSON Schema, có thể mô tả type, required, patterns và `additionalProperties`. Nhưng phải quyết định có cho backend bổ sung các field hạ tầng như `host.name` hay không; đừng khóa cứng một schema khi hệ thống chủ đích thêm metadata ở collector.

## 4. Test positive, negative và boundary

Một test suite chỉ kiểm `assertEquals("INFO", event.level)` là chưa đủ.

| Nhóm test | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Positive | Status 200, duration 17, trace ID hợp lệ | Đủ field, đúng kiểu và giá trị |
| Missing required | Không có `event.name` hoặc `trace_id` khi contract yêu cầu | Bị từ chối hoặc báo validation failure rõ |
| Wrong type | `"http.status_code":"200"` | Bị từ chối; không âm thầm ép string |
| Wrong unit | Duration đo nanosecond nhưng gán `duration_ms` | Test logic/unit conversion phát hiện |
| Invalid value | Status 0 hoặc 700, duration âm | Bị từ chối hoặc được xử lý theo policy rõ |
| Unknown field | `authorization`, `password`, typo `duraton_ms` | Không được phát; không vô tình trở thành field của sự kiện |
| Null/optional | Không có error code với success | Vắng mặt hoặc null theo contract, không có hai kiểu lẫn lộn |
| Escape | Message có quote, backslash, newline | JSON hợp lệ; một dòng JSONL không bị tách |
| Unicode | Message có tiếng Việt, emoji | Nội dung khớp và encoder không làm hỏng UTF-8 |
| Long payload | Chuỗi rất dài, nested object | Có giới hạn theo policy, không gây tăng bộ nhớ vô hạn |
| Context isolation | Request A/B khác trace/tenant | Không lẫn MDC/field khi thread pool tái sử dụng |
| Security | Canary token trong request | Không xuất hiện ở bất kỳ trường log không được phép |
| Async | Nhiều event được enqueue | Bản ghi nhận được đầy đủ theo policy và sau drain |
| Version drift | Thay encoder/layout/backend | Contract test phát hiện thay tên/kiểu/mất trường |

**Nên test dựa trên object đã parse**, không chỉ `jsonLine.contains("status")`. Substring có thể trùng trong message, JSON string escape, field khác hoặc string `"200"` dù yêu cầu số 200.

## 5. JSON Lines, escape và tính một-event-một-dòng

Phổ biến nhất trong hệ thống logs là **JSONL**: mỗi event là một JSON object, một dòng vật lý, kết thúc bằng newline. Các ký tự xuống dòng trong `message` phải được encode thành hai ký tự `\n` trong JSON string thay vì newline thô làm tách event.

Ví dụ hợp lệ:

```json
{"event.name":"checkout.completed","message":"checkout\ncompleted","http.status_code":200}
```

Giá trị JSON của `message` khi parse sẽ chứa một newline logic, nhưng bản ghi JSONL vẫn chiếm **một dòng vật lý**.

Các thuộc tính cần thử:

1. JSON có thể parse bởi thư viện độc lập như Jackson.
2. Mỗi dòng tương ứng đúng một object, không có prefix timestamp text ngoài JSON trừ khi pipeline contract yêu cầu.
3. Dấu `"`, `\`, CR, LF, tab và control characters được escape đúng.
4. UTF-8 không mất dấu tiếng Việt hoặc cắt hỏng surrogate pair.
5. Trường số và boolean không bị quote nhầm.
6. Không có trailing garbage hoặc dòng log text lẫn vào stream JSONL.
7. Các bản ghi exception có shape thống nhất thay vì stack trace tự do nhiều dòng ngoài JSON.

**Không tự viết serializer cho production** khi đã có Jackson hoặc encoder JSON đáng tin. Ví dụ JDK thuần bên dưới chỉ minh họa loại assertion; integration test thực tế phải dùng đúng encoder/layout ứng dụng triển khai.

## 6. Java 17 runnable: tự kiểm schema, type, escape và canary

Ví dụ độc lập dùng **Java 17**, không cần Maven/Gradle hay thư viện ngoài. Nó có ba phần:

- `buildEvent` chọn trường theo allowlist, không sử dụng raw Authorization/body của request.
- `validate` xác nhận tập field chính xác, type, enum, range, timestamp và trace ID.
- `toJson` là **encoder tối giản dành cho học tập** rồi test các ký tự escape và JSON value shape. Không dùng encoder tự viết này làm thư viện production.

Để kết quả tái lập được, timestamp, duration, status, trace ID và request được đặt cố định. In ra stdout chỉ các thông báo PASS; không in token canary.

Lưu thành file **`StructuredFieldsTestDemo.java`**:

```java
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class StructuredFieldsTestDemo {
    private static final Set<String> FIELDS = Set.of(
            "timestamp", "level", "event.name", "service.name",
            "trace_id", "http.status_code", "duration_ms",
            "success", "message");

    private static final Set<String> EVENT_NAMES = Set.of(
            "checkout.completed", "checkout.failed");

    private static final Pattern TRACE_ID =
            Pattern.compile("[0-9a-f]{32}");

    // Hai field nhạy cảm hiện diện ở input, nhưng không được copy vào event.
    record HttpContext(
            String trustedRoute,
            int status,
            long durationMs,
            String traceId,
            String authorization,
            String body) {}

    static Map<String, Object> buildEvent(HttpContext request) {
        if (!"/checkout".equals(request.trustedRoute())) {
            throw new IllegalArgumentException("Unexpected route");
        }

        Map<String, Object> event = new LinkedHashMap<>();
        event.put("timestamp", "2026-11-10T03:15:00Z");
        event.put("level", "INFO");
        event.put("event.name", "checkout.completed");
        event.put("service.name", "checkout-api");
        event.put("trace_id", request.traceId());
        event.put("http.status_code", request.status());
        event.put("duration_ms", request.durationMs());
        event.put("success", Boolean.TRUE);
        event.put("message", "checkout\ncompleted");
        return event;
    }

    private static String requiredText(
            Map<String, Object> event, String key) {
        Object value = event.get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException("Invalid string: " + key);
        }
        return text;
    }

    static void validate(Map<String, Object> event) {
        if (!event.keySet().equals(FIELDS)) {
            throw new IllegalArgumentException("Unexpected field set");
        }

        try {
            Instant.parse(requiredText(event, "timestamp"));
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException("Invalid timestamp", ex);
        }

        if (!Set.of("INFO", "WARN", "ERROR").contains(
                requiredText(event, "level"))) {
            throw new IllegalArgumentException("Invalid level");
        }
        if (!EVENT_NAMES.contains(
                requiredText(event, "event.name"))) {
            throw new IllegalArgumentException("Invalid event name");
        }
        requiredText(event, "service.name");

        if (!TRACE_ID.matcher(
                requiredText(event, "trace_id")).matches()) {
            throw new IllegalArgumentException("Invalid trace id");
        }

        Object status = event.get("http.status_code");
        if (!(status instanceof Integer code)
                || code < 100 || code > 599) {
            throw new IllegalArgumentException("Invalid status");
        }

        Object duration = event.get("duration_ms");
        if (!(duration instanceof Long millis) || millis < 0) {
            throw new IllegalArgumentException("Invalid duration");
        }

        if (!(event.get("success") instanceof Boolean)) {
            throw new IllegalArgumentException("Invalid boolean");
        }
        if (requiredText(event, "message").length() > 200) {
            throw new IllegalArgumentException("Message too long");
        }
    }

    // Chỉ dành cho bộ type String/Integer/Long/Boolean của bài học.
    private static String jsonValue(Object value) {
        if (value instanceof String text) {
            return quote(text);
        }
        if (value instanceof Integer || value instanceof Long
                || value instanceof Boolean) {
            return value.toString();
        }
        throw new IllegalArgumentException("Unsupported type");
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        String hex = Integer.toHexString(c);
                        out.append("\\u")
                                .append("0".repeat(4 - hex.length()))
                                .append(hex);
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    static String toJson(Map<String, Object> event) {
        validate(event);
        StringBuilder out = new StringBuilder("{");
        boolean first = true;

        for (Map.Entry<String, Object> field : event.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote(field.getKey()))
                    .append(':')
                    .append(jsonValue(field.getValue()));
        }
        return out.append('}').toString();
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectInvalid(Map<String, Object> event) {
        try {
            validate(event);
            throw new AssertionError("Invalid event was accepted");
        } catch (IllegalArgumentException expected) {
            // Validation có trách nhiệm từ chối event sai.
        }
    }

    public static void main(String[] args) {
        String secret = "SENSITIVE_CANARY_314";
        HttpContext request = new HttpContext(
                "/checkout", 200, 17L,
                "4bf92f3577b34da6a3ce929d0e0e4736",
                "Bearer " + secret,
                "card=" + secret);

        Map<String, Object> good = buildEvent(request);
        validate(good);

        check(good.get("http.status_code") instanceof Integer,
                "status must be integer");
        check(good.get("duration_ms") instanceof Long,
                "duration must be long");
        check(good.get("success") instanceof Boolean,
                "success must be boolean");
        System.out.println("PASS 1: schema and types");

        String json = toJson(good);
        check(json.contains("\"http.status_code\":200"),
                "numeric status lost");
        check(json.contains("\"duration_ms\":17"),
                "numeric duration lost");
        check(json.contains("\"success\":true"),
                "boolean lost");
        check(json.contains("\"message\":\"checkout\\ncompleted\""),
                "newline was not escaped");
        check(json.indexOf('\n') < 0 && json.indexOf('\r') < 0,
                "one event must occupy one physical line");
        System.out.println("PASS 2: JSON values and escaping");

        Map<String, Object> missing = new LinkedHashMap<>(good);
        missing.remove("trace_id");
        expectInvalid(missing);

        Map<String, Object> wrongType = new LinkedHashMap<>(good);
        wrongType.put("http.status_code", "200");
        expectInvalid(wrongType);

        Map<String, Object> extra = new LinkedHashMap<>(good);
        extra.put("authorization", request.authorization());
        expectInvalid(extra);
        System.out.println("PASS 3: missing, wrong-type and extra fields");

        check(!json.contains(secret), "secret leaked");
        check(!json.contains("authorization"), "sensitive key leaked");
        check(!json.contains("\"body\""), "body key leaked");
        System.out.println("PASS 4: sensitive data excluded");

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Lệnh chạy với JDK 17+:

```bash
javac --release 17 StructuredFieldsTestDemo.java
java StructuredFieldsTestDemo
```

**Stdout chính xác:**

```text
PASS 1: schema and types
PASS 2: JSON values and escaping
PASS 3: missing, wrong-type and extra fields
PASS 4: sensitive data excluded
ALL CHECKS PASSED
```

**Vì sao ví dụ đúng phạm vi?**

- `Set.of(...)` được dùng như contract required+allowed fields cho một **loại event cụ thể**, không phải schema chung của mọi log.
- `LinkedHashMap` giữ thứ tự trong encoder demo để thuận tiện kiểm tra, nhưng **thứ tự key JSON không mang ý nghĩa ngữ nghĩa**; test production không nên bắt thứ tự.
- `http.status_code` là `Integer`, `duration_ms` là `Long` và `success` là `Boolean`; `toJson` không đặt dấu nháy quanh number/boolean.
- `message` có một newline trong giá trị Java. Khi serialized, nó thành chuỗi literal `\n`, không tách JSONL thành hai dòng.
- Missing trace ID, status string và trường nhạy cảm ngoài allowlist bị từ chối ở `expectInvalid`.
- `HttpContext` có Authorization và body chứa canary, nhưng `buildEvent` **không đọc hai thuộc tính đó** để phát log.
- `Instant.parse` xác nhận timestamp parse được; timestamp cố định để stdout deterministic, không phải phương án lấy timestamp production.

**Giới hạn:** bộ encoder `quote(...)` ở ví dụ chỉ xử lý subset String/Integer/Long/Boolean và escape các control characters phổ biến. Nó **chưa là JSON serializer tổng quát**, ví dụ chưa kiểm tra Unicode surrogate không hợp lệ, cấu trúc nested/array, số thực và các trường hợp khác. Production nên dùng encoder JSON chuyên dụng và **kiểm thử JSON đã parse bằng thư viện độc lập**, như phần tiếp theo. Chương trình cũng không thực sự ghi file, không dùng Logback và không kiểm chứng collector.

## 7. Integration test JSON output bằng JUnit 5 và Jackson

Để kiểm tra **actual output của encoder**, cần lấy dòng JSON thực từ appender hoặc file, parse bằng một JSON parser có hỗ trợ kiểu dữ liệu. Ví dụ sau là **trích đoạn test**, yêu cầu JUnit Jupiter và Jackson Databind, đồng thời một hàm `captureActualJsonLine()` do test fixture của hệ thống cung cấp. Nó **không phải chương trình độc lập**, vì mục tiêu là chỉ rõ kiểu assertion trên JSON đã encode:

```java
// Imports minh họa:
// import com.fasterxml.jackson.databind.JsonNode;
// import com.fasterxml.jackson.databind.ObjectMapper;
// import org.junit.jupiter.api.Test;
// import static org.junit.jupiter.api.Assertions.*;

@Test
void structuredOutputHasContractTypes() throws Exception {
    String line = captureActualJsonLine(); // Fixture từ appender/file thực.
    JsonNode root = new ObjectMapper().readTree(line);

    assertTrue(root.isObject());
    assertEquals("checkout.completed", root.path("event.name").asText());
    assertEquals("checkout-api", root.path("service.name").asText());

    JsonNode status = root.path("http.status_code");
    assertTrue(status.isIntegralNumber());
    assertEquals(200, status.intValue());

    JsonNode duration = root.path("duration_ms");
    assertTrue(duration.isIntegralNumber());
    assertEquals(17L, duration.longValue());

    JsonNode success = root.path("success");
    assertTrue(success.isBoolean());
    assertTrue(success.booleanValue());

    assertFalse(root.has("authorization"));
    assertFalse(root.has("password"));
    assertFalse(root.has("cookie"));
    assertFalse(line.contains("SENSITIVE_CANARY_314"));
}
```

**Quan trọng:** `root.path("duration_ms").asLong()` tự nó không đủ để kiểm kiểu, vì một số API chuyển đổi có thể chấp nhận chuỗi số. Hãy kiểm `isIntegralNumber()` trước; tương tự `isBoolean()` trước `booleanValue()`.

Khi dùng thư viện backend, JSON event có thể có nested object thay vì key chứa dấu chấm, ví dụ:

```json
{"http":{"status_code":200},"duration_ms":17}
```

Khi đó assertion cần truy `root.path("http").path("status_code")`; **không** tự gộp nested thành flat key nếu contract quy định nested. Phải thống nhất shape với pipeline/collector thực tế.

### Test contract, không test formatting ngoài contract

Đừng so chuỗi JSON đầy đủ nếu thứ tự field, spacing hoặc field metadata thay đổi mà vẫn hợp lệ theo contract. Parse thành JSON tree rồi so giá trị/type. Chỉ test byte-to-byte nếu quy trình yêu cầu format canonical (ví dụ chữ ký/HMAC) và đã tài liệu hóa serialization.

Test timestamps bằng parser thời gian và tolerance phù hợp, không dùng `assertEquals(Instant.now().toString(), timestamp)`, vì clock đang trôi khi test. Có thể inject `Clock.fixed(...)` vào event builder để kiểm giá trị ổn định.

## 8. Logback ListAppender: kiểm tra event trước encoder

Khi ứng dụng dùng SLF4J + Logback-classic, có thể gắn `ListAppender<ILoggingEvent>` vào logger trong test để đọc event đã phát. Ví dụ **trích đoạn JUnit**, cần Logback và SLF4J thật trên test classpath:

```java
// Trích đoạn JUnit 5; imports được rút gọn:
// ch.qos.logback.classic.Logger;
// ch.qos.logback.classic.spi.ILoggingEvent;
// ch.qos.logback.core.read.ListAppender;
// org.slf4j.LoggerFactory;
// static org.junit.jupiter.api.Assertions.*;

ch.qos.logback.classic.Logger logger =
        (ch.qos.logback.classic.Logger)
        org.slf4j.LoggerFactory.getLogger("test.structured");

var appender = new ch.qos.logback.core.read
        .ListAppender<ch.qos.logback.classic.spi.ILoggingEvent>();

appender.start();
logger.addAppender(appender);
try {
    logger.info("checkout.completed");
    assertEquals(1, appender.list.size());
    assertEquals("checkout.completed",
            appender.list.get(0).getFormattedMessage());
} finally {
    logger.detachAppender(appender);
    appender.stop();
}
```

Đoạn này kiểm tra **event được Logback nhận** và message đã format, **chưa kiểm tra field JSON đầu ra**. Nếu muốn test `trace_id` từ MDC, có thể kiểm `getMDCPropertyMap()` với việc set/restore MDC đúng scope trong test. Nếu ứng dụng sử dụng fluent API `logger.atInfo().addKeyValue(...)` của SLF4J 2.x, cần xác định backend/encoder có preserve key-value pairs hay không; chỉ gọi `addKeyValue` không bảo đảm chúng hiện thành field JSON.

**Để kiểm encoder thật:** cấu hình encoder production trong test, gắn một `OutputStreamAppender` với `ByteArrayOutputStream` hoặc ghi file tạm, phát một event, flush/stop theo semantics backend, sau đó parse từng dòng bằng Jackson. Đây mới kiểm tra được key name/type/shape cuối cùng.

### Quản lý test isolation

- Không để appender test gắn trên logger static sau khi test kết thúc.
- Lưu và khôi phục logger level, additivity, MDC/context nếu test thay chúng.
- Đừng cho nhiều test song song chỉnh chung root logger rồi mong assertion ổn định.
- Với async logger, `ListAppender` ở phía nào (trước/ sau queue) quyết định bạn đang đo sự kiện được nhận hay thực sự đã encode/xuất.

## 9. Ví dụ SLF4J 2.x: structured key-value fields

SLF4J 2.x hỗ trợ fluent logging API có thể gắn key-value pairs:

```java
// Trích đoạn tích hợp cần SLF4J 2.x + backend có hỗ trợ lưu fields.
org.slf4j.Logger logger =
        org.slf4j.LoggerFactory.getLogger("checkout");

logger.atInfo()
      .addKeyValue("event.name", "checkout.completed")
      .addKeyValue("http.status_code", 200)
      .addKeyValue("duration_ms", 17L)
      .addKeyValue("success", true)
      .log("Checkout completed");
```

**Điểm phải kiểm thử:** backend có thể hỗ trợ hoặc không hỗ trợ việc serialize những pairs này thành **các key JSON có kiểu đúng**. Một pattern text có thể chỉ in `key=value` thành chuỗi; một encoder khác có thể lồng các pair vào `fields` hoặc thay tên key. Vì vậy **việc API chấp nhận arguments chưa chứng minh structured output đúng contract**.

Bộ test cần khẳng định:

- Event có đúng `event.name`, `http.status_code`, `duration_ms`, `success`.
- Không có duplicate key hay collision với trường mặc định của encoder.
- Số nguyên vẫn là JSON number, boolean vẫn là JSON boolean.
- Event level INFO được phát khi logger/config cho phép; không bị filter/appender chặn ngoài ý muốn.
- Message được escape và không mang raw token/PII.
- Với DEBUG disabled, các biểu thức eager gây side-effect không được dùng trong assertions để suy ra event đã phát.

## 10. Test MDC và correlation fields

Logging request thường đính `trace_id`, `span_id`, `request_id`, `tenant_id` thông qua MDC hoặc OpenTelemetry. Thử những tình huống sau:

1. **Một request:** các event trong cùng request giữ đúng trace ID.
2. **Hai request đồng thời:** trace/tenant của request A không xuất hiện trong event request B.
3. **Thread pool reuse:** request sau không thừa MDC từ request trước.
4. **Async producer/consumer:** event phải snapshot context từ producer đúng lúc; không để worker đọc thread-local của chính nó.
5. **No context:** log ngoài HTTP request (startup/scheduler) tuân theo policy field optional, không ghi trace ID rác hoặc value `null` mơ hồ.
6. **Untrusted headers:** `traceparent`/`X-Request-ID` từ client phải được parse/validate; không tự coi ID hợp format là bằng chứng actor identity.
7. **Tenant boundary:** tenant ID phải lấy từ context đã xác thực, không từ raw request query.

Một mẫu thiết lập/dọn MDC trong test:

```java
// Trích đoạn cần SLF4J; không phải chương trình độc lập.
String previous = org.slf4j.MDC.get("request_id");
org.slf4j.MDC.put("request_id", "req_101");
try {
    runRequestAndCaptureLogs();
} finally {
    if (previous == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", previous);
    }
}
```

Đoạn này chỉ minh họa **save/restore cho một key**; trong production/test đa key dùng scoped MDC, map snapshot hoặc integration phù hợp. Nếu thiếu `finally`, một test có thể làm bẩn context của test khác. Nếu backend hỗ trợ asynchronous logger, bảo đảm event snapshot có giá trị trước khi publish.

**Test identity ≠ test correlation.** Trace ID đúng vẫn không chứng minh user đã xác thực; không lấy actor ID từ header giả và nhầm nó với principal.

## 11. Test security và bí mật trong structured fields

Với API nhạy cảm, một log có JSON hợp lệ vẫn là log **không an toàn** nếu chứa token. Những trường thường cần exclude:

- `authorization`, `password`, `cookie`, `set_cookie`, `refresh_token`.
- Raw request/response body, OTP, session ID, API key, payment PAN/CVV.
- Raw URL/query có token hoặc path variable mang email/secret.
- Exception/stack trace hoặc `toString()` có nội dung bí mật.
- MDC baggage chứa dữ liệu cá nhân.

**Canary test:** đặt chuỗi **giả** `SENSITIVE_CANARY_314` vào input của một endpoint test; kiểm tra nó **không xuất hiện** ở event builder, JSON line thực, file/stdout, collector, backend, dashboard và export trong phạm vi test được phép. Đừng dùng credential thật.

Không chỉ assert `!root.has("password")`: secret có thể nằm trong `message`, `exception.stacktrace` hoặc key khác. Kiểm tra **toàn JSON string** bằng canary, đồng thời kiểm allowlist field.

**Log forging:** message có CRLF, tab, quote, backslash, Unicode line separators hoặc control characters phải được encode an toàn cho JSONL và cho viewer/CSV downstream. Jackson escaping xử lý JSON syntax; dashboard vẫn cần HTML escaping, CSV export cần chống formula interpretation theo ứng dụng.

Test có thể cố đưa thêm key `authorization` qua fluent API, custom field provider hoặc MDC để chắc encoder/policy không vô tình xuất dữ liệu cấm.

## 12. Test lỗi, stack trace và optional fields

Khi nghiệp vụ thất bại, một event có thể chứa:

```json
{"event.name":"checkout.failed","level":"ERROR","error.code":"PAYMENT_TIMEOUT","http.status_code":504,"success":false}
```

Các vấn đề phải định nghĩa:

- `error.code` có ở event thất bại, nhưng vắng ở event thành công.
- `error.message` là chuỗi kiểm soát, không là exception message thô từ dependency nếu có secret.
- `exception.type` có thể dùng tên class; `stack_trace` chỉ có khi policy cho phép và có quyền xem phù hợp.
- Status 504 không có nghĩa đương nhiên “payment timeout”; reason phải đến từ logic tương ứng.
- `duration_ms` có thể thiếu ở event chưa hoàn tất; đó có phải schema lỗi hay một loại event khác?
- Khi hai exception có stack trace nhiều dòng, JSONL vẫn phải là một object/dòng vật lý.
- `null` có thể được ghi rõ hoặc key bị bỏ; test phải quyết định nhất quán, không dùng `asText()` mặc định che lỗi.

Nếu dùng cấu trúc nested fields, test đường dẫn đầy đủ thay vì tìm `error` trong JSON string. Một số encoder phát thêm `throwable` hoặc `stack_trace` tự động; phải review chính sách dữ liệu và kích thước event.

## 13. Test async logging: đừng assert trước khi consumer ghi xong

Với `AsyncAppender`, một lời gọi `logger.info(...)` có thể chỉ **enqueue** event. Đọc `ByteArrayOutputStream` ngay lập tức rồi assert đủ dòng có thể tạo flaky test dù hệ thống đang hoạt động đúng.

Thiết kế test ổn định:

1. Gửi `N` sự kiện có `event.id` duy nhất, với nhiều `trace_id` hoặc transaction ID.
2. Dùng **lifecycle/drain mechanism chính thức** của backend hoặc test-specific synchronization để xác nhận consumer đã xử lý. Không chỉ `Thread.sleep(100)` vì phụ thuộc tốc độ máy CI.
3. Parse mọi dòng JSON đầu ra, kiểm đủ số lượng và mỗi event ID xuất hiện theo policy; không bắt buộc thứ tự toàn cục nếu nhiều producer/consumer.
4. Nếu hệ thống có drop/discard khi queue đầy, test phải xác định **chính sách expected** (chấp nhận drop hay yêu cầu no-loss) và đo counters; không lẫn lỗi test với chính sách vận hành.
5. Tắt appender/consumer có kiểm soát sau test để không làm test sau bị lẫn.
6. Thử overload/burst, sink chậm, file rotation, shutdown bình thường và crash riêng ở integration/chaos test.

**Hàng đợi được nhận ≠ sink đã ghi ≠ backend đã index.** Khi kiểm contract parser ở collector, cần đợi điểm xác nhận phù hợp thay vì chỉ nhìn producer return.

### Tránh test dựa vào global order

Khi nhiều thread phát event, thứ tự toàn cục có thể khác thứ tự xử lý tại appender. Test thường nên khẳng định **tập ID, số lượng, nội dung từng ID**, hoặc thứ tự trong một stream có bảo đảm rõ, thay vì so thứ tự toàn bộ các request.

## 14. Contract test từ collector và backend tìm kiếm

Ngay cả khi JSON encoder ra đúng number/boolean, collector có thể:

- Chuyển field thành string, đổi tên key hoặc lồng sai object.
- Ghi đè `service.name`, `trace_id` hoặc `timestamp` bằng metadata khác.
- Giảm precision timestamp, đổi timezone hoặc đơn vị duration.
- Làm mất field do parser lỗi, giới hạn kích thước hoặc mapping conflict.
- Nhân đôi dòng khi cả file tailer và stdout collector cùng thu một event.
- Cắt event hoặc drop khi queue/ingest quá tải.

Vì vậy end-to-end contract test nên:

1. Sinh một **event có ID duy nhất** và các trường type/units đại diện.
2. Chờ backend trả dữ liệu theo phương pháp retry có hạn và deadline (không sleep vô hạn).
3. Query theo event ID và service/environment.
4. So mapping field, type, giá trị, timestamp, tenant và nested shape ở backend.
5. Xác nhận canary không xuất hiện ở các sink cấm.
6. Nếu ingest phải exactly-once, kiểm dedup policy; đừng giả định tính chất đó chỉ vì JSONL.
7. Thu bằng chứng lỗi: raw encoder output, collector parse error, backend event và config version.

**Không dùng kết quả search bằng từ khóa trong message để chứng minh mapping numeric.** Hãy kiểm chính trường và kiểu trong index/query API khi hệ thống hỗ trợ.

## 15. Schema evolution và tương thích ngược

Structured fields trở thành API dữ liệu cho dashboard, alert, báo cáo và hệ thống bảo mật. Thay đổi nhỏ cũng có thể gây lỗi:

| Thay đổi | Nguy cơ | Cách kiểm |
| --- | --- | --- |
| `duration_ms` đổi thành `duration_ns` | Tính latency sai đơn vị | Contract test + version/migration rõ |
| `http.status_code` từ number sang string | Aggregation/histogram không hoạt động | Type assertion |
| `event.name` đổi từ `checkout.failed` sang `checkout.error` | Alert/filter bỏ sót | Enum/compatibility check |
| `trace_id` bị chuyển sang key khác | Mất correlation log/trace | Integration contract |
| `error.code` từ optional thành required | Success event không còn hợp lệ | Schema test từng event type |
| Thêm field chứa PII | Lộ dữ liệu và retention thay đổi | Allowlist + privacy review |
| JSON flat thành nested | Query cũ không còn trả | Shape-specific test |
| Thêm field mặc định của encoder | Collision/duplicate key | Kiểm tra final JSON, parse tree và metadata |

Có thể dùng `schema.version` và hợp đồng theo `event.name`, giữ khả năng đọc phiên bản cũ trong thời gian chuyển đổi. **Không mặc định thêm field là thay đổi tương thích** nếu collector/index có `additionalProperties=false`, giới hạn field cardinality hoặc field mới là dữ liệu nhạy cảm.

Khi nâng cấp JDK, Logback, Log4j2, encoder JSON hay collector, chạy lại contract tests để phát hiện khác biệt. Đừng giữ một “golden snapshot” cứng toàn bộ JSON nếu metadata có chủ đích thay đổi mà không ảnh hưởng contract.

## 16. Các lỗi test thường gặp

| Triệu chứng | Lỗi trong test hoặc hệ thống | Cách sửa |
| --- | --- | --- |
| Test PASS dù status là string | Dùng `asText()` hoặc substring thay vì type assertion | `isIntegralNumber()` rồi so số |
| Chỉ kiểm mock logger | Không đo encoder/appender thật | Capture actual JSONL và parse |
| Test phụ thuộc thứ tự field | JSON object không yêu cầu thứ tự key | So field tree theo schema |
| Test flaky trên CI | Sleep cố định trước khi async drain | Dùng synchronization/lifecycle, timeout có hạn |
| Missing trace ID nhưng test vẫn PASS | Có `root.path(...).asText()` mặc định rỗng | Kiểm `hasNonNull` và format |
| Event có key trùng | Nhiều field provider cùng ghi key | Review encoder mapping, parser duplicate-key strict nếu cần |
| Log không hiện nhưng business test vẫn xanh | Logger level/filter/appender không phát event | Integration test cấu hình backend |
| Secret không ở key `password` nhưng trong `message` | Chỉ test danh sách tên field | Quét canary trên toàn payload và pipeline |
| Runtime đổi schema khi bật exception | Encoder thêm stack trace fields | Test success, error và exception |
| MDC tenant của request A vào B | Không restore ThreadLocal | Scoped context, concurrent test |
| Hai event giống nhau khi collector ingest | File + stdout cùng được tail, retry không dedup | Canonical source/ID và test pipeline |
| Thêm HTTP 404 không có route | Policy giả định mọi request có matched route | Optional/UNKNOWN policy |
| Test timestamp không ổn định | So trực tiếp với `Instant.now()` | Inject `Clock` hoặc tolerance có kiểm soát |
| Test duration từ nanoTime nhưng đặt unit ms sai | Bug ở conversion | Kiểm ngưỡng/boundary với fake clock |
| JSON trên stdout trộn dòng text khác | Appender không dùng JSON layout đồng nhất | Tách stream hoặc chuẩn hóa encoder |
| Schema test bị thắt chặt quá mức | Framework bổ sung metadata hợp lệ | Contract core fields vs extension fields rõ |

## 17. Ma trận test tối thiểu cho một service web

| Kịch bản | Level/event | Field cần kiểm |
| --- | --- | --- |
| HTTP 200 thành công | `checkout.completed` / INFO | service, status 200 number, duration >=0, success true |
| HTTP 504 lỗi | `checkout.failed` / ERROR | error code, status number, success false, trace |
| Request bị từ chối trước controller | `authorization_denied` | Actor verified/anonymous, route UNKNOWN nếu thiếu |
| Không có tracing context | Startup/scheduler event | Trace ID optional đúng policy, không chuỗi rỗng giả |
| Hai request song song | Nhiều trace/tenant | Không rò MDC/correlation |
| Body chứa canary | Auth/payment event | Không lộ canary, token hoặc raw body |
| Message chứa newline/quote | Event text/JSON | JSONL vẫn một dòng, parse ra chuỗi đúng |
| Async queue và shutdown | N sự kiện | Số lượng và drop theo policy, không flaky |
| Encoder nâng cấp | Cùng fixture | Core contract types/names giữ nguyên |
| Collector nâng cấp | E2E event | Mapping, timestamp, nested shape và ID đúng |

Trong CI, chạy unit test thường xuyên và integration test encoder ở mỗi thay đổi logging. E2E collector có thể tốn tài nguyên hơn; nên chạy tại pipeline thích hợp với backend test cô lập và có cleanup.

## 18. Nguyên tắc tổ chức test và dữ liệu thử

- **Mỗi test một mục tiêu rõ:** type, field presence, secrecy, correlation, async delivery, schema migration.
- **Fixture dữ liệu an toàn:** dùng canary/ID giả, không dùng token, password hay hồ sơ người dùng thật.
- **Test isolation:** tách logger config, MDC, appender, file temp và namespace index giữa các test.
- **Gắn schema/encoder version:** biết binary test và backend thực tế đang chạy.
- **Không giấu lỗi:** khi parse fail, báo event ID và thông tin đã sanitize; tránh in raw secret vào CI logs.
- **Giảm false positive:** assert ngữ nghĩa và type, không phụ thuộc thứ tự key/spacing JSON.
- **Giảm false negative:** không chỉ test message text, phải kiểm nested fields, exception metadata, MDC và collector mapping.
- **Tối ưu thời gian chạy:** unit tests cho toàn bộ trường; integration/E2E chọn scenario đại diện và negative tests quan trọng.
- **Test hành vi thiếu dữ liệu:** thiếu required phải bị từ chối; thiếu optional phải có semantics thống nhất.
- **Đảm bảo khả năng nâng cấp:** schema change được review và có migration/compatibility plan.

### Khi structured log phục vụ audit hoặc bảo mật

Một log có field `actor.id` đẹp chưa chứng minh actor đáng tin: cần lấy từ authentication context, tránh ID tự khai trong header; event cần ghi đúng outcome và có chính sách lưu bền vững, phát hiện mất/sửa và phân quyền. **Kiểm thử structured field là điều kiện cần, không thay thế threat model logging hay audit trail correctness**.

## 19. Checklist thực hành

- [ ] Có danh mục event types, required/optional fields, field names và types được tài liệu hóa.
- [ ] Timestamp parse được, timezone rõ và không bị phụ thuộc locale.
- [ ] Duration có đơn vị đúng; status là number, success là boolean.
- [ ] Kiểm thử vắng/sai kiểu/null/giá trị biên và field ngoài allowlist.
- [ ] JSON Lines hợp lệ, một event trên một dòng vật lý và escaping đúng.
- [ ] Có integration test với actual backend/encoder, không chỉ mock logger.
- [ ] Kiểm thử nested shape và duplicate/collision fields theo contract.
- [ ] Correlation MDC/trace không lẫn giữa thread, request hoặc tenant.
- [ ] Async logging được drain/đồng bộ đúng trước assertion; không dựa sleep cố định.
- [ ] Canary bí mật không xuất hiện trong message, exception, MDC, JSONL hoặc backend.
- [ ] Logger level/filter/appender phù hợp với yêu cầu phát event.
- [ ] Có end-to-end test mapping và ingestion sau khi thay collector.
- [ ] Schema evolution được version hóa/review và không đổi type/units ngầm.
- [ ] Output thất bại của test không vô tình in secret vào CI log.

**Ghi nhớ:** kiểm thử structured field không dừng ở “logger đã được gọi”. Phải kiểm tra **đúng tên và kiểu trường ở event builder, JSON encoder thực, context khi chạy, dữ liệu nhạy cảm và mapping sau collector**. Một structured log chỉ đáng tin khi đúng ngữ nghĩa, không bị lẫn nguồn, parse được và đến đích theo hợp đồng đã thiết kế.

### Tài liệu tham khảo

- [SLF4J 2.x Manual — Fluent Logging API](https://www.slf4j.org/manual.html)
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html)
- [Apache Log4j2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [Jackson Databind — JsonNode API](https://github.com/FasterXML/jackson-databind)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
