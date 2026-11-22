# Kiểm thử JSON log trong Java Core Logging

## 1. Kiểm thử JSON log là kiểm thử điều gì?

**JSON logging** tạo mỗi log event dưới dạng một đối tượng JSON với các trường có tên, kiểu dữ liệu và ngữ nghĩa rõ ràng. Trong ứng dụng Java, JSON có thể do formatter/handler của `java.util.logging` (JUL), hoặc encoder/appender của Logback, Log4j 2 hay một logging backend khác tạo ra.

Ví dụ một log event đã được cấu trúc:

~~~json
{"timestamp":"2026-01-15T10:00:00Z","level":"INFO","logger":"orders.service","event":"order_loaded","requestId":"req-42","status":200,"durationMs":18}
~~~

Kiểm thử JSON log không dừng ở `logger.info(...)` đã chạy hay một dòng bắt đầu bằng `{`. Cần kiểm tra:

1. **Cú pháp:** mỗi event parse thành JSON hợp lệ.
2. **Schema:** đủ field bắt buộc, tên đúng, kiểu số/string/boolean/array/object/null đúng hợp đồng.
3. **Ngữ nghĩa:** level, event name, outcome, request ID, error code và timestamp đúng tình huống.
4. **Encoding và escaping:** dấu nháy, backslash, newline, tab và Unicode không làm hỏng JSON.
5. **Ranh giới bản ghi:** với NDJSON/JSON Lines, **một event ứng với một dòng vật lý**.
6. **Đường phát log:** logger level, filter, parent handler/additivity, async và file/collector không bỏ hoặc nhân đôi event trái chính sách.
7. **Bảo mật:** không xuất secret, token, dữ liệu cá nhân hoặc body không được phép.
8. **Tương thích:** dashboard, cảnh báo và consumer downstream vẫn đọc được khi schema/version thay đổi.

**JSON hợp lệ chưa chắc là log đúng.** Cả `{"status":200}` và `{"status":"200"}` đều là JSON hợp lệ, nhưng trường thứ hai có kiểu string. Một message sai request ID hoặc chứa password cũng có thể là JSON hợp lệ.

## 2. JSON document và NDJSON khác nhau

| Biểu diễn | Ví dụ | Hợp đồng |
| --- | --- | --- |
| JSON object | `{"level":"INFO"}` | Một tài liệu JSON chứa một object |
| JSON array | `[{"event":"a"},{"event":"b"}]` | Một tài liệu JSON chứa hai object |
| **NDJSON / JSON Lines** | Hai dòng, mỗi dòng một object | Dòng là ranh giới event; thường dùng với log shipper |
| Text log | `INFO request completed` | Không phải JSON, cần bộ kiểm thử khác |

Một NDJSON file hai event:

~~~text
{"event":"request_started","requestId":"req-1"}
{"event":"request_finished","requestId":"req-1"}
~~~

Một message chứa ký tự xuống dòng **phải được JSON serializer escape**. Ví dụ đúng, một dòng vật lý duy nhất:

~~~json
{"level":"WARNING","message":"line one\nline two"}
~~~

Không được in ký tự xuống dòng thô ngay bên trong chuỗi JSON như minh họa sai dưới đây:

~~~text
{"level":"WARNING","message":"line one
line two"}
~~~

Ví dụ sai vừa vi phạm cú pháp JSON vừa chia một event thành hai dòng. Regex `^\{.*\}$` không thể thay thế JSON parser: nó không xác nhận kiểu, escape, nested JSON hay trường thiếu.

**Lưu ý:** NDJSON là một hợp đồng vận chuyển riêng, không phải mọi JSON logger đều bắt buộc phát NDJSON. Test phải khớp định dạng đích nhận mong muốn.

## 3. Thiết kế hợp đồng schema trước khi assert

Một schema log HTTP có thể quy định:

| Field | Kiểu JSON | Quy tắc kiểm thử |
| --- | --- | --- |
| `timestamp` | string | Dạng ISO-8601 có offset/UTC, parse được |
| `level` | string | Thuộc tập tên level do backend quy định |
| `logger` | string | Tên nguồn phát có ý nghĩa, không rỗng nếu bắt buộc |
| `event` | string | Mã event ổn định, ví dụ `http_request_finished` |
| `requestId` | string | Tương quan đúng request, không chứa token |
| `status` | integer | HTTP status ở dạng JSON number, không phải string |
| `durationMs` | number | Không âm, đơn vị mili giây đã định nghĩa |
| `errorType` | string, tùy chọn | Có khi lỗi, vắng khi không lỗi theo policy |
| `schemaVersion` | integer/string theo quy ước | Giúp consumer biết định dạng |

Không có một schema JSON log duy nhất áp dụng cho mọi thư viện. Ví dụ runnable bên dưới cố ý chỉ dùng `timestamp`, `level`, `logger`, `message` và `errorType` tùy chọn; bảng phía trên minh họa một **schema ứng dụng giàu thông tin hơn**.

**Assertion hữu ích:** `json.isObject()`, `json.hasNonNull("timestamp")`, `json.path("status").isIntegralNumber()`, `json.path("durationMs").isNumber()` và giá trị đúng theo nghiệp vụ. `asInt()` đơn lẻ có thể ép kiểu hoặc dùng giá trị mặc định khi trường thiếu; cần kiểm tra **kiểu** trước.

### Trường động

Timestamp, process ID, thread name, duration và trace ID có thể thay đổi giữa các lần chạy. Không nên so sánh nguyên chuỗi JSON chứa dữ liệu động. Thay vào đó:

- Dùng `Clock.fixed(...)` hoặc đặt timestamp trên test `LogRecord` nếu có thể.
- Parse timestamp bằng `Instant.parse`/`OffsetDateTime.parse` theo hợp đồng.
- Kiểm tra duration thuộc khoảng hợp lệ, không assert đúng một giá trị mili giây trên CI.
- Sinh request ID giả cố định trong test hoặc assert format và correlation.
- Parse object JSON rồi assert các field; **thứ tự key** thường không mang ngữ nghĩa.

## 4. Ví dụ chạy được: Java 17, JUL, Jackson và JUnit 5

Java SE 17 có sẵn JUL nhưng **không có JSON serializer/parser tổng quát trong JDK**. Ví dụ dùng Jackson để tránh tự nối chuỗi và dùng JUnit Jupiter để kiểm tra JSON thực sự. Đây là một project Maven có thể chạy `mvn test`, không phải pseudocode.

Cấu trúc:

~~~text
json-log-testing/
|-- pom.xml
|-- src/main/java/example/
|   |-- JsonLogFormatter.java
|   |-- JsonLogDemo.java
|-- src/test/java/example/
    |-- JsonLogFormatterTest.java
~~~

### 4.1. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>json-log-testing</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các phiên bản được ghim để ví dụ có tính tái lập, **không phải khẳng định đó là phiên bản mới nhất**. Dự án production phải cập nhật bản vá và quản lý dependency theo quy trình riêng.

### 4.2. Formatter dùng JSON serializer

Tạo `src/main/java/example/JsonLogFormatter.java`:

~~~java
package example;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.logging.Formatter;
import java.util.logging.LogRecord;

public final class JsonLogFormatter extends Formatter {
    private final ObjectMapper mapper = new ObjectMapper();

    @Override
    public String format(LogRecord record) {
        ObjectNode node = mapper.createObjectNode();
        node.put("timestamp", record.getInstant().toString());
        node.put("level", record.getLevel().getName());
        node.put("logger", record.getLoggerName() == null
                ? "" : record.getLoggerName());
        node.put("message", formatMessage(record));

        if (record.getThrown() != null) {
            node.put("errorType",
                    record.getThrown().getClass().getSimpleName());
        }

        try {
            return mapper.writeValueAsString(node) + "\n";
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot encode JSON log", ex);
        }
    }
}
~~~

`formatMessage(record)` của JUL nội suy các tham số `{0}`, `{1}` khi thích hợp. Jackson escape dấu nháy, backslash, newline và các ký tự JSON cần escape. `"\n"` cuối cùng là **ký tự kết thúc dòng record**; newline **bên trong** giá trị message đã được Jackson biến thành escape.

Formatter chỉ xuất **loại Throwable** qua `errorType`, không xuất `Throwable.getMessage()` hoặc stack trace; đây là chính sách mẫu giảm rò rỉ, không phải yêu cầu mọi ứng dụng phải bỏ stack trace. Khi production cần stack trace, hãy đưa vào JSON đúng cách, giới hạn kích thước và kiểm soát dữ liệu nhạy cảm.

### 4.3. Chạy chương trình tạo JSON

Tạo `src/main/java/example/JsonLogDemo.java`:

~~~java
package example;

import java.time.Instant;
import java.util.logging.Level;
import java.util.logging.LogRecord;

public class JsonLogDemo {
    public static void main(String[] args) {
        LogRecord event = new LogRecord(
                Level.WARNING, "retry {0}\nnext");
        event.setLoggerName("demo.jsonlog");
        event.setParameters(new Object[] {"req-42"});
        event.setInstant(Instant.parse("2026-01-15T10:00:00Z"));

        System.out.print(new JsonLogFormatter().format(event));
    }
}
~~~

Chạy với JDK 17 và Maven:

~~~bash
mvn -q test
mvn -q compile exec:java -Dexec.mainClass=example.JsonLogDemo
~~~

**Payload stdout do chương trình Java tạo ra** là một dòng JSON như sau; `\n` bên trong message là escape trong dòng đó:

~~~json
{"timestamp":"2026-01-15T10:00:00Z","level":"WARNING","logger":"demo.jsonlog","message":"retry req-42\nnext"}
~~~

`mvn -q test` hoàn tất với exit code 0 khi các assertion pass. Maven có thể in diagnostic của công cụ nếu môi trường thiếu dependency hoặc cấu hình gặp lỗi; dòng trên mô tả output của `JsonLogDemo`, không hứa toàn bộ stdout/stderr của lệnh Maven chỉ chứa nó.

## 5. JUnit: test parse JSON, escaping, exception và đường ghi JUL

Tạo `src/test/java/example/JsonLogFormatterTest.java`:

~~~java
package example;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

import static org.junit.jupiter.api.Assertions.*;

class JsonLogFormatterTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void parsesJsonAndEscapesMultilineUnicode() throws Exception {
        LogRecord event = new LogRecord(
                Level.WARNING, "Thử lại {0}\nnext");
        event.setInstant(Instant.parse("2026-01-15T10:00:00Z"));
        event.setLoggerName("demo.orders");
        event.setParameters(new Object[] {"req-42"});

        String output = new JsonLogFormatter().format(event);

        assertTrue(output.endsWith("\n"));
        assertEquals(1, output.chars()
                .filter(ch -> ch == '\n').count());

        JsonNode json = mapper.readTree(output);
        assertTrue(json.isObject());
        assertEquals("2026-01-15T10:00:00Z",
                json.path("timestamp").asText());
        assertEquals("WARNING", json.path("level").asText());
        assertEquals("demo.orders", json.path("logger").asText());
        assertEquals("Thử lại req-42\nnext",
                json.path("message").asText());
        assertEquals(4, json.size());
        assertFalse(json.has("errorType"));
    }

    @Test
    void doesNotCopyRawExceptionMessage() throws Exception {
        LogRecord event = new LogRecord(
                Level.SEVERE, "event=operation_failed");
        event.setLoggerName("demo.orders");
        event.setThrown(new IllegalArgumentException(
                "TEST_ONLY_SECRET_SENTINEL"));

        String output = new JsonLogFormatter().format(event);
        JsonNode json = mapper.readTree(output);

        assertEquals("IllegalArgumentException",
                json.path("errorType").asText());
        assertEquals("event=operation_failed",
                json.path("message").asText());
        assertFalse(output.contains("TEST_ONLY_SECRET_SENTINEL"));
    }

    @Test
    void twoJulEventsBecomeTwoJsonLines() throws Exception {
        Logger logger = Logger.getLogger(
                "test.json." + UUID.randomUUID());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        StreamHandler handler = new StreamHandler(
                bytes, new JsonLogFormatter());
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            logger.info("accepted");
            logger.warning("retry");
            handler.flush();

            String captured = bytes.toString(
                    StandardCharsets.UTF_8);
            String[] lines = captured.split("\n", -1);

            // Hai event va phan tu rong sau newline cuoi.
            assertEquals(3, lines.length);
            assertEquals("", lines[2]);

            JsonNode first = mapper.readTree(lines[0]);
            JsonNode second = mapper.readTree(lines[1]);
            assertTrue(first.isObject());
            assertTrue(second.isObject());
            assertEquals("INFO", first.path("level").asText());
            assertEquals("WARNING",
                    second.path("level").asText());
            assertEquals("accepted",
                    first.path("message").asText());
            assertEquals("retry",
                    second.path("message").asText());
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Những assertion trên được viết để chạy trong **Maven project đầy đủ** đã nêu. Test 1 đặt thời gian cố định để kiểm tra schema/escaping và đếm đúng một newline vật lý; message chứa Unicode và newline được parse lại thành nội dung ban đầu. Test 2 xác định formatter demo không chuyển **message thô** của `Throwable` thành JSON; test 3 kiểm tra đường đi thực `Logger → StreamHandler → Formatter → byte stream`, sau `flush()` có đúng hai dòng JSON.

Việc đếm **số dòng JSON đã parse** quan trọng hơn kiểm tra `logger.getHandlers().length`: số handler không phải số log event. `UUID` trong tên test logger giúp tránh reuse một logger cũ có cấu hình khác. `finally` tháo và đóng handler để không làm nhiễu các test khác.

**Giới hạn của bộ test:** nó chưa kiểm tra một appender production có async queue, MDC hoặc collector thật. Đó là lớp test tích hợp và end-to-end bổ sung, không nên tuyên bố đã hoàn thành chỉ từ test formatter.

## 6. Assertions cho schema ứng dụng có kiểu số và trường optional

Nếu ứng dụng có event HTTP JSON giàu thông tin như phần 3, có thể dùng `JsonNode` để kiểm thử:

~~~java
// Doan tich hop voi JUnit/Jackson.
// json da parse tu log event cua ung dung, co field
// event, status, durationMs, timestamp.
assertTrue(json.isObject());
assertEquals("http_request_finished",
        json.path("event").asText());
assertTrue(json.path("status").isIntegralNumber());
assertEquals(200, json.path("status").asInt());
assertTrue(json.path("durationMs").isNumber());
assertTrue(json.path("durationMs").asDouble() >= 0);
assertDoesNotThrow(() ->
        Instant.parse(json.path("timestamp").asText()));
~~~

Đây là **đoạn mã tích hợp**; formatter mẫu ở phần 4 không tự tạo `event`, `status` hay `durationMs`. Test đúng phải dùng schema của producer thực và không bịa trường mà encoder chưa phát.

Về null và missing:

- `json.has("errorCode")`: có key dù giá trị có thể null.
- `json.hasNonNull("errorCode")`: có key và giá trị không null.
- `json.path("errorCode").isMissingNode()`: không có key.
- Với các field bắt buộc, kiểm tra sự tồn tại **trước** `asText()`/`asInt()`.
- Với JSON number rất lớn, kiểm tra phạm vi/precision để không vô tình tràn kiểu Java.

Về thứ tự property: JSON object không hứa bảo toàn thứ tự key theo nghiệp vụ, nên so sánh **nội dung cây**, không phụ thuộc `{"a":1,"b":2}` phải được in theo đúng thứ tự đó. Nếu hệ thống thực sự yêu cầu canonical JSON cho chữ ký số, đó là một hợp đồng khác cần encoder chuẩn hóa riêng và test riêng.

## 7. Kiểm thử NDJSON khi có nhiều event

Với đầu ra là **một JSON object trên mỗi dòng**, nên parse tất cả các dòng không rỗng và đối chiếu số lượng. Một đoạn JUnit tích hợp:

~~~java
// capturedLog: chuoi UTF-8 da doc tu test sink.
// expectedCount: so event test du kien.
String[] lines = capturedLog.split("\n", -1);
int count = 0;

for (int i = 0; i < lines.length; i++) {
    if (i == lines.length - 1 && lines[i].isEmpty()) {
        continue; // newline ket thuc file.
    }
    assertFalse(lines[i].isEmpty());
    JsonNode event = mapper.readTree(lines[i]);
    assertTrue(event.isObject());
    count++;
}
assertEquals(expectedCount, count);
~~~

Phải phân biệt **newline kết thúc event cuối** với **dòng trống bất thường ở giữa**. Bỏ qua mọi dòng rỗng vô điều kiện có thể che lỗi của encoder hoặc collector.

Các tình huống đầu vào cần thử:

| Dữ liệu / trường hợp | Kết quả mong đợi |
| --- | --- |
| Message chứa dấu `"` | Không làm đóng sớm JSON string |
| Message chứa backslash | Được escape, parse lại đúng ký tự |
| Newline/tab/carriage return | Không tách một event thành nhiều dòng NDJSON |
| Tiếng Việt và emoji | Bảo toàn Unicode sau UTF-8 encode/decode |
| Exception multiline | Lưu trong JSON string hoặc mảng frame đúng schema |
| Hai event liên tiếp | Có hai dòng riêng, không dính object vào nhau |
| JSON bị cắt vì giới hạn kích thước | Test phải phát hiện record không hợp lệ |
| File dùng CRLF | Đích nhận xử lý theo policy cụ thể |
| Logger ghi song song từ nhiều thread | Không xen byte khiến hai JSON object trộn vào nhau |
| Input rất dài hoặc ký tự điều khiển | Có giới hạn/escaping; không tạo log injection |

**Không sửa lỗi JSON bằng cách xóa newline khỏi chuỗi đã xuất.** Cần sửa tại serializer, formatter hoặc encoder và test bằng parser để xác minh dữ liệu gốc được biểu diễn đúng.

## 8. Kiểm thử Throwable và stack trace

Một số encoder thêm field `stackTrace`, `errorType`, `cause`, `errorMessage`, hoặc `exception`. Cần xác định hợp đồng:

1. Không có exception: field bị bỏ hay có giá trị `null`?
2. Có exception: dùng **class/type** và error code ổn định hay thêm cả message?
3. Stack trace được lưu như **một string với newline escaped** hay một array frame?
4. Giới hạn kích thước stack trace, độ sâu cause và suppressed exception thế nào?
5. Exception message có chứa query string, token, PII hoặc payload không?
6. Backend xử lý lỗi serialization và thất bại ghi log ra sao?

Ví dụ event lỗi:

~~~json
{"timestamp":"2026-01-15T10:00:00Z","level":"SEVERE","event":"dependency_failed","requestId":"req-42","errorCode":"TIMEOUT","errorType":"TimeoutException"}
~~~

Đây là **schema minh họa mở rộng**, không phải output của formatter ngắn ở phần 4. Nếu test cần stack trace, so sánh các thuộc tính có ý nghĩa (có frame phù hợp, không lộ secret, dạng dữ liệu đúng), tránh hard-code toàn bộ chuỗi stack trace thay đổi theo JVM, đường build hoặc phiên bản thư viện.

**Escaping khác redaction:** serializer có thể biến secret thành một JSON string hợp lệ nhưng không hề xóa nội dung bí mật. Bảo mật phải được quyết định ở caller và encoder theo chính sách.

## 9. Kiểm thử MDC, request context và trace ID

Với SLF4J/Logback hoặc Log4j 2, ứng dụng có thể gắn `requestId`, `traceId`, `tenant` qua MDC/ThreadContext rồi đưa vào JSON. **JUL thuần không cung cấp MDC tiêu chuẩn chung**; project demo không có cơ chế này.

Test tích hợp nên xác minh:

- Hai request liên tiếp có request ID riêng, không bị lẫn.
- Trong thread pool, request A không rò context sang request B khi thread tái sử dụng.
- Context được dọn đúng scope, thường qua `finally`.
- Async task có propagation rõ ràng; không mặc định mọi ThreadLocal sẽ tự đi theo task.
- Field MDC chỉ gồm metadata đã phê duyệt; không có token/cookie/email.
- Các key bổ sung từ MDC không ghi đè `timestamp`, `level`, `event` hoặc các field hệ thống khác.

Ví dụ pattern (đoạn mã **tích hợp**, yêu cầu thư viện SLF4J):

~~~java
try {
    org.slf4j.MDC.put("requestId", requestId);
    // Xu ly request va phat log.
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

Đừng chỉ kiểm tra `MDC.get("requestId")` trong test; hãy kiểm tra **JSON thực tế từ appender**, vì layout/encoder có thể không hề xuất MDC hoặc xuất sai key/kiểu.

## 10. Từ unit test đến integration và end-to-end

Kiểm thử JSON logging nên có ít nhất ba tầng tùy độ quan trọng:

| Tầng | Đích kiểm tra | Điều chưa chứng minh |
| --- | --- | --- |
| **Unit formatter/encoder** | Cú pháp, schema, escaping, Throwable, kiểu JSON | Chưa biết logger/filter/sink có phát đúng không |
| **Integration logger + handler/appender** | Level, additivity, số event, flush, charset, routing | Chưa biết shipper/collector có lưu đúng không |
| **End-to-end log pipeline** | File/stdout → agent → collector → truy vấn/retention | Cần môi trường thực và xác nhận theo hợp đồng |

Những lỗi unit test formatter không bắt được:

- Level của logger hoặc handler lọc mất event.
- Logger child và root cùng ghi do parent handler/additivity, sinh duplicate.
- Appender ghi JSON ra file nhưng stdout vẫn ở format text, trong khi collector chỉ thu stdout.
- Một async queue chưa drain nên test đọc buffer quá sớm.
- Sự kiện bị truncation hoặc biến đổi trong collector.
- Clock/charset khác cấu hình test.
- Sự kiện được gửi tới hai sink rồi đồng bộ hai lần vào cùng index.

Với backend async, đừng dùng `Thread.sleep(100)` làm bảo đảm flush. Dùng API shutdown/drain, test sink có await có timeout, và xác nhận số event ở **đích cần kiểm thử**. Sau test, gỡ appender/handler, hoàn nguyên logger config và dọn các thread/tài nguyên.

**Kiểm tra đúng số event:** một event được fan-out tới console và file hợp lệ có thể tạo hai bản ở hai sink; đó không hẳn là lỗi. Nhưng cùng sink có hai bản mà policy chỉ cho một là dấu hiệu duplicate. Các test concurrency không nên assert global ordering giữa nhiều thread khi backend không hứa thứ tự; kiểm tra `eventId`, event count và tính toàn vẹn từng dòng.

## 11. Bảo vệ dữ liệu cá nhân trong bài test

JSON dễ tìm kiếm và xuất sang hệ thống tập trung, vì vậy các field nhạy cảm càng cần kiểm soát. Nên dùng **giá trị giả** với sentinel để phát hiện rò rỉ:

~~~java
// Doan tich hop JUnit, khong doc lap.
// capturedLog duoc lay tu flow ung dung voi gia tri gia.
assertFalse(capturedLog.contains("person@example.test"));
assertFalse(capturedLog.contains("TEST_ONLY_SECRET_SENTINEL"));
~~~

Test formatter mẫu ở phần 5 chỉ đảm bảo **`Throwable.getMessage()` không được serialize** theo chính sách của formatter. Nếu caller đã gọi `logger.info("token=" + token)`, message vẫn có token và serializer sẽ biến nó thành JSON **hợp lệ nhưng không an toàn**. Vì vậy test phải chạy qua producer của ứng dụng, cả đường thành công và đường lỗi.

Những nguồn cần kiểm tra:

- Raw request body, headers `Authorization`, `Cookie`, access token, refresh token.
- `toString()` của DTO/record có email, phone, địa chỉ hoặc số tài khoản.
- Exception message, URL có query, raw SQL và parameter.
- MDC/ThreadContext, field tự thêm từ framework, stack trace.
- Bản sao ở stdout, file, collector, alert/ticket và backup.

Kiểm thử riêng việc phân quyền, retention, mã hóa và khả năng xóa log ở hệ thống cuối; một unit test JSON không chứng minh các thuộc tính vận hành đó.

## 12. Contract testing và tương thích schema

Một thay đổi nhỏ như đổi `durationMs` thành `duration`, thay `status` số bằng string, hoặc đổi `event` có thể khiến dashboard và alert hỏng mặc dù JSON vẫn hợp lệ.

Nên:

1. Version hóa schema, xác định field bắt buộc/tùy chọn và kiểu rõ ràng.
2. Dùng JSON Schema validator hoặc test `JsonNode` theo contract với consumer khi hợp lý.
3. Test thêm field/enum mới trong thời gian chạy song song nhiều phiên bản.
4. Xác định quy tắc backward compatibility khi bỏ/đổi tên field.
5. Đưa sample event vào integration test của collector/query nếu có thể.
6. Kiểm tra field mới có phải PII hoặc metric label cardinality cao không.
7. Chỉ dùng snapshot nguyên JSON cho trường hợp thực sự có output ổn định; ưu tiên parse và normalize các trường động.

**Snapshot test** giúp phát hiện thay đổi ngoài ý muốn nhưng không thay thế test semantic: snapshot có thể “đúng chuỗi” trong khi status/outcome theo nghiệp vụ sai.

## 13. Sai lầm thường gặp

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| `assertTrue(line.startsWith("{"))` | Không kiểm tra cú pháp JSON thật | Parse bằng thư viện JSON |
| So sánh nguyên raw JSON | Key order và field động khiến test giòn | So sánh `JsonNode`/schema |
| Chỉ dùng `asInt()` | Field string hoặc thiếu có thể bị ép kiểu | Dùng `isIntegralNumber()` trước |
| Chỉ test formatter | Bỏ sót filter, hierarchy, duplicate, flush | Thêm test logger+handler/appender |
| Đọc ngay sau log ở backend async | Dữ liệu còn nằm trong queue | Await/drain với timeout |
| Sửa escaping bằng regex sau serialization | Có thể làm sai dữ liệu và che bug | Dùng JSON encoder chuẩn |
| Log nguyên exception message | PII/token dễ lọt vào collector | Mã lỗi, allowlist, redaction |
| Không test Unicode/newline | NDJSON bị cắt hoặc sai encoding | Round-trip parse và đếm dòng |
| Không dọn MDC và test handler | Test sau bị nhiễm state | `finally` cleanup + logger riêng |
| Chỉ đếm logger handler | Số handler không phải số event | Đếm JSON record ở đúng sink |
| Bỏ qua collector | Sự kiện có thể bị sửa/mất sau appender | E2E query log theo event ID |
| Mọi schema mới đều được phép | Có thể thêm field bí mật hoặc đổi kiểu | Contract review + test field allowlist |

## 14. Checklist áp dụng

- [ ] Xác định JSON document hay NDJSON một event/dòng.
- [ ] Parse mỗi event bằng JSON parser thực, không dựa vào regex.
- [ ] Test field bắt buộc, optional, null, missing và kiểu dữ liệu.
- [ ] Test timestamp, level, event code, correlation ID, status và duration.
- [ ] Test newline, quote, backslash, Unicode, UTF-8 và kích thước event.
- [ ] Test exception/stack trace, mã lỗi và quy tắc che dữ liệu.
- [ ] Capture qua logger và handler/appender thật, xác minh filter/level/duplicate.
- [ ] Dùng flush/drain phù hợp khi có stream/async, dọn tài nguyên test.
- [ ] Kiểm tra MDC/ThreadContext có đúng scope và không chứa secret.
- [ ] Test event trong môi trường nhiều thread mà không giả định ordering không có thật.
- [ ] Test các đích file, stdout và collector khi đường pipeline quan trọng.
- [ ] Version hóa schema và kiểm thử tương thích với consumer.

### Tự kiểm tra

**Câu 1.** `{"status":"200"}` parse được; có đúng hợp đồng status dạng số không?  
**Đáp:** Không. Phải assert kiểu JSON number nguyên, không chỉ gọi `asInt()`.

**Câu 2.** Vì sao NDJSON không thể mặc định parse nguyên file như một JSON array?  
**Đáp:** Vì nó gồm nhiều JSON document độc lập, mỗi dòng là một event.

**Câu 3.** Message có newline có bắt buộc chiếm hai dòng log không?  
**Đáp:** Không. Serializer phải escape newline trong JSON string để giữ một dòng vật lý/event.

**Câu 4.** Formatter test pass nhưng collector thiếu log; có mâu thuẫn không?  
**Đáp:** Không. Unit test không kiểm tra async queue, vận chuyển hay collector cuối.

**Câu 5.** JSON escaping có tự che token/password không?  
**Đáp:** Không. Escaping chỉ bảo đảm cú pháp; dữ liệu nhạy cảm cần được loại/che bằng chính sách riêng.

**Câu 6.** Có nên assert thứ tự mọi event từ nhiều thread theo thứ tự gọi `logger.info` không?  
**Đáp:** Không mặc định; điều đó phụ thuộc bảo đảm ordering của backend.

**Ghi nhớ:** Kiểm thử JSON log phải xác nhận **cú pháp, schema, ngữ nghĩa, escaping, số lượng event và quyền riêng tư**. Kết hợp test formatter, test qua logger/handler thực và test pipeline downstream khi cần; không nhầm JSON hợp lệ với dữ liệu log đúng hoặc lời gọi logger thành công với bằng chứng log đã được lưu bền vững.
