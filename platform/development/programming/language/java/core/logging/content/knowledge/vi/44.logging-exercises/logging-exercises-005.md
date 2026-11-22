# Dự án thực hành: Chuyển Java Logging từ text sang structured log

## 1. Bài toán và kết quả cần đạt

Giả sử một ứng dụng Java đang ghi log dạng text:

```text
2026-01-01 10:00:00 INFO OrderService - Cancel order O-7 failed: already shipped
2026-01-01 10:00:01 WARN OrderService - Invalid comment from req-18
```

Đây là dữ liệu hữu ích cho người đọc, nhưng máy tìm kiếm, dashboard, SIEM hoặc công cụ alert phải **đoán** các trường bằng regex. Khi một developer đổi câu chữ, thứ tự dữ liệu, cách viết level hoặc locale, parser có thể hỏng. Khi cùng một message chứa dấu xuống dòng, log injection hoặc stack trace, ranh giới giữa các event càng khó xác định.

**Structured logging** là cách biểu diễn sự kiện bằng các **trường có tên và kiểu dữ liệu xác định**: `timestamp`, `level`, `service`, `eventType`, `action`, `outcome`, `reasonCode`, `requestId`, `operationId`, `durationMs`. JSON Lines/NDJSON (mỗi event một JSON object trên một dòng) là một định dạng phổ biến, nhưng **structured log không đồng nghĩa tuyệt đối với JSON**: schema và contract mới là phần cốt lõi.

Sau bài thực hành, học viên có thể:

1. Kiểm kê các log text hiện tại và xác định consumer đang phụ thuộc vào message format.
2. Thiết kế schema log có type, ý nghĩa, version, yêu cầu bảo mật và correlation IDs rõ.
3. Phát structured event bằng Java 17, hiểu quy tắc escape và dữ liệu null/number.
4. Cấu hình ứng dụng dùng SLF4J 2.x + Logback + JSON encoder, phân biệt facade và backend.
5. Chuyển từng call site từ ghép chuỗi sang trường có cấu trúc, không làm sai control flow.
6. Kiểm thử field/type, JSON encoding, exception, MDC, log filtering, dữ liệu nhạy cảm và duplicate events.
7. Triển khai theo giai đoạn, theo dõi chất lượng pipeline và rollback mà không mất khả năng điều tra.

**Tiêu chí nghiệm thu:** log JSON có thể parse, đúng schema tối thiểu, có thông tin correlation khi hợp lệ, không lộ secret, không làm đổi kết quả nghiệp vụ, và vẫn được giao tới sink mong muốn với mức độ tin cậy đã định nghĩa. Chuyển định dạng **không tự tạo bảo đảm lưu bền vững**: appender, agent, collector, index và retention vẫn là những tầng riêng.

## 2. Phân biệt text log, parameterized log và structured log

Ba cách viết sau **không tương đương**:

### A. Nối chuỗi text

```java
// Không nên dùng như contract machine-readable.
logger.info("Cancel order " + orderId
        + " rejected because " + reasonCode);
```

Câu này tạo message text và có thể tốn chi phí xây string ngay cả khi INFO bị tắt. Nếu `reasonCode` hoặc `orderId` đến từ input không được kiểm soát, có rủi ro log injection hoặc rò dữ liệu.

### B. Parameterized text với SLF4J

```java
logger.info(
    "Cancel order {} rejected because {}",
    safeOrderId, reasonCode);
```

Cách này giúp đưa argument vào API logging theo placeholder `{}` và có thể giảm eager string concatenation. Tuy nhiên **output cuối có thể vẫn chỉ là một chuỗi**; downstream không tự nhận được field `orderId`/`reasonCode` riêng nếu encoder không hỗ trợ.

### C. Structured event

```java
// SLF4J 2.x fluent API; cần backend/encoder hỗ trợ output fields.
logger.atInfo()
    .addKeyValue("eventType", "ORDER_CANCEL_RESULT")
    .addKeyValue("action", "ORDER_CANCEL")
    .addKeyValue("orderId", safeOrderId)
    .addKeyValue("outcome", "REJECTED")
    .addKeyValue("reasonCode", reasonCode)
    .log("Cancellation rejected");
```

Lời gọi trên biểu diễn **cặp key–value** ở logging event. Việc chúng xuất hiện trong JSON như các field có thể truy vấn phụ thuộc **provider/encoder đang chạy**. Không kết luận “đã có structured log” chỉ từ việc gọi `addKeyValue`; phải **kiểm tra record thực tế tại sink**.

Một JSON kết quả mong muốn:

```json
{
  "schemaVersion": 1,
  "@timestamp": "2026-01-01T10:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "eventType": "ORDER_CANCEL_RESULT",
  "action": "ORDER_CANCEL",
  "orderId": "O-7",
  "outcome": "REJECTED",
  "reasonCode": "ORDER_ALREADY_SHIPPED",
  "message": "Cancellation rejected"
}
```

Tên `@timestamp` chỉ là **một lựa chọn schema**; demo JDK ở phần 7 dùng `timestamp`. Cần chọn **một contract công bố** hoặc một phép ánh xạ có version; đừng để hai tên đồng thời xuất hiện không có chủ đích. JSON này là ví dụ định dạng, không phải lời hứa chính xác về mọi field mặc định của Logback encoder.

## 3. Kiểm kê hệ thống trước khi migration

Đầu tiên, tìm **những gì đang tồn tại và phụ thuộc vào chúng**. Một bảng kiểm kê ví dụ:

| Điểm phát | Log hiện tại | Người dùng/consumer | Rủi ro khi đổi |
| --- | --- | --- | --- |
| HTTP boundary | Method, path, status, duration text | Dashboard latency, support | Parser regex hỏng, URL lộ query secret |
| Domain service | `Order O-7 rejected` | Business ops | Thiếu `reasonCode`, khó group |
| Payment client | Error + stack | On-call alert | Stack lộ token/URL, alert count thay đổi |
| Message consumer | `Processed msg-1` | Debug retry | Không tách message ID và attempt |
| Security boundary | `Access denied` | Audit/SIEM | Thiếu trusted actor/action/outcome |
| Background job | `Job finished` | SLO vận hành | Không biết pending, partial, failed |
| Application startup | Config summary | On-call | Config có thể chứa secret |

Với mỗi điểm phát, ghi lại:
- Tên logger/category, effective level và profile hiện tại.
- Appender/formatter/encoder, sink đích, sampling/filter/retention.
- Trường nào thực sự cần truy vấn, cảnh báo hoặc tương quan.
- Người tiêu thụ text pattern: saved query, alert rule, regex, parser, script, dữ liệu export.
- Trường nào nhạy cảm, ai được xem và chính sách che/loại.
- Có event nào là **audit bắt buộc** không; mức độ bền vững của audit có cần khác operational log không.
- Độ trễ và số lượng log ở peak để ước lượng tác động ingest/index.

**Không bắt đầu bằng việc đổi `logback.xml` trong production ngay.** Nếu downstream đang parse pattern cũ, một lần chuyển tất cả sang JSON có thể làm dashboard trống dù ứng dụng vẫn ghi log bình thường.

### Đường baseline có thể đo

Trước cutover, ghi tối thiểu:
- Số event/s theo level/service.
- Tỷ lệ parse fail, field missing, event có newline không escape.
- Volume bytes/s, queue depth, appender drop, collector errors.
- Query/alert đang chạy và ngưỡng hiện tại.
- Trace/request correlation coverage.
- Tỷ lệ dữ liệu nhạy cảm trong các ví dụ thử đã được phê duyệt.

Dữ liệu baseline sẽ được so sau migration, tránh đánh giá “JSON nhìn đẹp” là đủ bằng chứng thành công.

## 4. Thiết kế một schema có ý nghĩa và version

Đề xuất schema cho ví dụ `order-service`:

| Field | Kiểu | Bắt buộc? | Ý nghĩa |
| --- | --- | --- | --- |
| `schemaVersion` | number/integer | Có | Phiên bản hợp đồng log |
| `timestamp` hoặc `@timestamp` | string ISO-8601 UTC | Có | Thời điểm event ở nguồn; định nghĩa timezone/precision |
| `level` | string enum | Có | Mức độ vận hành INFO/WARN/ERROR... |
| `service` | string | Có | Component/service phát event |
| `environment` | string | Có khi phân môi trường | dev/staging/prod... |
| `eventType` | string enum | Có với business event | Tên loại event ổn định, không dùng câu tự do |
| `message` | string | Có thể có | Câu tóm tắt an toàn cho con người |
| `action` | string | Khi là thao tác nghiệp vụ | ORDER_CANCEL, PAYMENT_CAPTURE... |
| `outcome` | string enum | Khi có kết quả | SUCCEEDED/REJECTED/DENIED/FAILED... |
| `reasonCode` | string hoặc null | Khi áp dụng | Mã lý do ổn định |
| `requestId` | string hoặc null | Khi có HTTP request | ID truy vết đã validate |
| `traceId`/`spanId` | string hoặc null | Khi có tracing | ID theo context tracing đáng tin |
| `operationId` | string hoặc null | Khi có workflow | Liên kết retry/async cùng hành động |
| `resourceType`/`resourceId` | string | Khi cần | Đối tượng; đánh giá quyền riêng tư |
| `durationMs` | number/integer | Khi đo thời gian | Độ trễ của một phạm vi rõ ràng |
| `error.type` | string | Khi là technical error | Loại exception đã được phân loại |
| `error.stack` | string, optional | Chỉ khi cần | Thông tin chẩn đoán được kiểm soát |

**Tính nhất quán:** sử dụng cùng key/kiểu trên mọi service nếu cùng nghĩa. `durationMs` nên luôn là số, không lúc là `"12ms"`, lúc `12`. `status` dễ gây nhập nhằng giữa HTTP code, order status và business outcome; đặt tên cụ thể như `httpStatus` hoặc `orderStatus`.

**Null hay bỏ field?** Cả hai có thể chấp nhận nếu contract xác định. Ví dụ không có `reasonCode` khi `SUCCEEDED` có thể được biểu diễn bằng `null` hoặc field absent. Nhưng consumer không nên phải đoán vì service A dùng empty string, service B null và service C không có key.

### Bộ mã sự kiện và mã lỗi

`eventType` trả lời “loại sự kiện nào?”, còn `outcome` trả lời “kết quả nghiệp vụ gì?”. `reasonCode` giải thích kết quả theo mã ổn định.

Ví dụ:
- `eventType=ORDER_CANCEL_RESULT`
- `action=ORDER_CANCEL`
- `outcome=REJECTED`
- `reasonCode=ORDER_ALREADY_SHIPPED`

Không dùng `logger.error(...)` để mã hóa outcome: một business rejection có thể ghi INFO, còn một exception sau commit có thể cần ERROR nhưng nghiệp vụ trước đó vẫn đã hoàn thành. **Structured logging chỉ có ích nếu semantics đúng trước khi serialize.**

### Versioning

Khi thêm field optional, consumer cũ có thể tiếp tục hoạt động nếu đã thiết kế chịu được unknown keys. Khi **đổi tên/kiểu/ý nghĩa field bắt buộc**, cần migration có version, kiểm thử compatibility và thời gian chuyển đổi. Không âm thầm đổi `durationMs` thành `durationSeconds` mà giữ nguyên tên, hoặc đổi nghĩa `FAILED` thành `REJECTED` không có thông báo.

## 5. Chọn định dạng đầu ra: JSON Lines, text song song và collector

Một mục tiêu phổ biến là **mỗi event được encode thành đúng một JSON object trên đúng một dòng** (NDJSON). Ví dụ:

```json
{"schemaVersion":1,"timestamp":"2026-01-01T10:00:00Z","level":"INFO","service":"order-service","eventType":"ORDER_CANCEL_RESULT","outcome":"REJECTED"}
{"schemaVersion":1,"timestamp":"2026-01-01T10:00:01Z","level":"WARN","service":"order-service","eventType":"VALIDATION_RESULT","outcome":"REJECTED"}
```

Nếu field `message` chứa dấu xuống dòng, JSON encoder phải escape thành các ký tự `\n` trong **cùng một dòng JSON**, không in raw newline làm collector tưởng có hai event. Dấu nháy kép và backslash cũng phải escape.

### Quy tắc định dạng cần chốt

1. Charset UTF-8 xuyên pipeline.
2. Một event = một JSON object/line tại sink đang chuẩn hóa theo dòng.
3. Timestamp có timezone rõ (thường UTC), parse được, độ chính xác nhất quán.
4. Kiểu số giữ là number, Boolean giữ boolean, null có nghĩa được định nghĩa.
5. Keys ổn định và không va chạm tên metadata do encoder tự sinh.
6. Exception được encode theo policy: field type, message đã review, stack optional.
7. Không có raw ANSI color escape từ console pattern trong JSON production.
8. Có `schemaVersion` hoặc metadata cấu hình đủ để consumer nhận biết hợp đồng.

### Có nên dual-write text và JSON?

Trong một giai đoạn, có thể phát sang **hai appender** hoặc hai sink để xác minh consumer. Nhưng cần hiểu:
- Một business event có thể tồn tại hai bản; dashboard không được đếm như hai operation.
- Hai pipeline có thể có mức độ bền, filter, latency khác nhau.
- Tăng ingest volume và chi phí, đặc biệt lúc DEBUG/TRACE cao.
- Phải có thời hạn kết thúc dual-write và cơ chế xác minh data parity.

Một lựa chọn khác là **một JSON sink chính** và view/query tạo cột message cho người đọc, không cần nhân đôi log. Chọn dựa trên khả năng của collector và yêu cầu tương thích.

## 6. Phân chia vai trò: SLF4J, Logback, encoder và collector

Trong Java, cấu trúc triển khai thường như sau:

```text
Application code
   |
   +-- SLF4J 2.x fluent API / Logger
   |
   v
Logback backend (classic)
   |
   v
JSON encoder (ví dụ logstash-logback-encoder)
   |
   v
ConsoleAppender / FileAppender / AsyncAppender
   |
   v
Container runtime / log agent
   |
   v
Collector -> storage / index -> query / alert
```

**SLF4J là facade**, không trực tiếp quyết định JSON file cuối. Logback là backend, encoder chịu trách nhiệm chuyển event thành JSON. Nếu backend thực là Log4j2, cấu hình và API khác; không cast Log4j2 logger sang Logback `LoggerContext`.

Một số cách cung cấp structured fields:
- SLF4J 2.x fluent `atInfo().addKeyValue(...).log(...)`.
- MDC chứa correlation context có phạm vi (chỉ key nhỏ, an toàn, có cleanup).
- Encoder hỗ trợ key–value pairs, markers hoặc structured arguments phù hợp phiên bản đang dùng.
- Một custom event/publisher model được serialize qua JSON library tại tầng application/transport khi có hợp đồng dữ liệu riêng.

**Điểm dễ sai:** SLF4J có cặp key–value trong event nhưng encoder chỉ in `message` và bỏ `keyValuePairs`. Chỉ có integration test với **đúng encoder, dependency và cấu hình production** mới chứng minh field thực sự có ở JSON output. Đừng coi việc code compile là đủ.

## 7. Java 17 độc lập: tạo JSON có field và escape đúng

Trước khi thêm framework, chương trình này giúp hiểu sự khác nhau giữa **dữ liệu event** và **format văn bản**. Nó tạo hai `LogEvent` có các field typed, rồi ghi một JSON object trên mỗi dòng. Trường `message` thứ hai có nháy kép và newline để thấy cách escape.

**Quan trọng:** đây là bộ serialize JSON **tối giản cho học tập**, không phải khuyến nghị tự viết JSON encoder production. Khi làm dự án thật, dùng Jackson/Gson hoặc JSON encoder của logging backend đã được kiểm thử và cập nhật bảo mật.

### 7.1. Tệp `StructuredLogMigrationDemo.java`

```java
import java.time.Instant;

public class StructuredLogMigrationDemo {
    record LogEvent(
            Instant timestamp,
            String level,
            String service,
            String eventType,
            String action,
            String outcome,
            String reasonCode,
            String requestId,
            String operationId,
            String message,
            long durationMs
    ) {}

    // JSON escaping cho String. Một record trong một dòng.
    private static String quote(String value) {
        if (value == null) {
            return "null";
        }

        StringBuilder output = new StringBuilder();
        output.append('"');

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);

            switch (c) {
                case '"' -> output.append("\\\"");
                case '\\' -> output.append("\\\\");
                case '\n' -> output.append("\\n");
                case '\r' -> output.append("\\r");
                case '\t' -> output.append("\\t");
                case '\b' -> output.append("\\b");
                case '\f' -> output.append("\\f");
                default -> {
                    if (c < 0x20) {
                        output.append('\\').append('u');
                        String hex = Integer.toHexString(c);
                        for (int n = hex.length(); n < 4; n++) {
                            output.append('0');
                        }
                        output.append(hex);
                    } else {
                        output.append(c);
                    }
                }
            }
        }

        return output.append('"').toString();
    }

    static String toJson(LogEvent e) {
        return "{\"schemaVersion\":1"
                + ",\"timestamp\":" + quote(e.timestamp().toString())
                + ",\"level\":" + quote(e.level())
                + ",\"service\":" + quote(e.service())
                + ",\"eventType\":" + quote(e.eventType())
                + ",\"action\":" + quote(e.action())
                + ",\"outcome\":" + quote(e.outcome())
                + ",\"reasonCode\":" + quote(e.reasonCode())
                + ",\"requestId\":" + quote(e.requestId())
                + ",\"operationId\":" + quote(e.operationId())
                + ",\"message\":" + quote(e.message())
                + ",\"durationMs\":" + e.durationMs()
                + "}";
    }

    public static void main(String[] args) {
        Instant base = Instant.parse("2026-01-01T10:00:00Z");

        LogEvent rejected = new LogEvent(
                base, "INFO", "order-service",
                "ORDER_CANCEL_RESULT", "ORDER_CANCEL",
                "REJECTED", "ORDER_ALREADY_SHIPPED",
                "req-17", "op-7", "Cancel rejected", 12
        );

        LogEvent invalid = new LogEvent(
                base.plusSeconds(1), "WARN", "order-service",
                "VALIDATION_RESULT", "ORDER_CREATE",
                "REJECTED", "INVALID_COMMENT",
                "req-18", "op-8",
                "Input: \"test\"\nnext", 3
        );

        System.out.println(toJson(rejected));
        System.out.println(toJson(invalid));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac StructuredLogMigrationDemo.java
java StructuredLogMigrationDemo
```

**Stdout chính xác (hai dòng JSON, newline trong message được escape):**

```json
{"schemaVersion":1,"timestamp":"2026-01-01T10:00:00Z","level":"INFO","service":"order-service","eventType":"ORDER_CANCEL_RESULT","action":"ORDER_CANCEL","outcome":"REJECTED","reasonCode":"ORDER_ALREADY_SHIPPED","requestId":"req-17","operationId":"op-7","message":"Cancel rejected","durationMs":12}
{"schemaVersion":1,"timestamp":"2026-01-01T10:00:01Z","level":"WARN","service":"order-service","eventType":"VALIDATION_RESULT","action":"ORDER_CREATE","outcome":"REJECTED","reasonCode":"INVALID_COMMENT","requestId":"req-18","operationId":"op-8","message":"Input: \"test\"\nnext","durationMs":3}
```

### 7.2. Giải thích chi tiết

- `LogEvent` là Java record chứa **dữ liệu có nghĩa**, không phải một câu message khó parse.
- `durationMs` được ghi bằng JSON number, không phải string `"12ms"`.
- `quote` escape dấu nháy kép, backslash, newline, carriage return, tab, backspace, form feed và các ký tự điều khiển U+0000–U+001F. Vì vậy record thứ hai vẫn nằm trên **một dòng stdout**.
- Trường `message` phục vụ người đọc. Field `reasonCode` ổn định giúp group/alert mà không parse message.
- Hai event có timestamp cố định nên output tái lập được; trong production cần clock đáng tin, format timestamp và trace context theo contract.
- Hàm `toJson` không phản ánh ngầm việc log đã bền vững. `System.out.println` chỉ viết qua stdout; agent/collector/index là bước tiếp theo.
- `record` chứa field immutable theo reference, nhưng không tự biến thành audit event có ACID/retention.

**Giới hạn kỹ thuật quan trọng:** ví dụ chưa có schema validation, size limits, chuẩn hóa chuỗi Unicode không hợp lệ, cấu trúc nested, special number, redaction, streaming/backpressure hoặc error recovery. Không dùng `quote` tự viết này làm serializer production, đặc biệt với input không đáng tin hay các type phức tạp. Hãy dùng thư viện JSON trưởng thành và test output theo yêu cầu.

## 8. Dự án Maven sử dụng SLF4J 2 và Logback JSON encoder

Một triển khai thực dụng dùng:
- Java 17;
- SLF4J 2.x API;
- Logback Classic 1.5.x tương thích;
- `logstash-logback-encoder` phiên bản tương thích với Logback/Java đang dùng;
- ConsoleAppender phát JSON một dòng/event, agent của nền tảng thu stdout.

Dưới đây là **một dự án tham khảo độc lập**. Những phiên bản cố định giúp ví dụ có môi trường xác định, **không khẳng định là phiên bản mới nhất hoặc phù hợp bảo mật cho mọi thời điểm**. Trong production, chọn/kiểm tra phiên bản theo dependency management, CVE và nền tảng thực tế.

### 8.1. Cấu trúc thư mục

```text
structured-log-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── StructuredLoggingApp.java
        └── resources/
            └── logback.xml
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>structured-log-lab</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>

        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>

        <dependency>
            <groupId>net.logstash.logback</groupId>
            <artifactId>logstash-logback-encoder</artifactId>
            <version>8.0</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Lưu ý:** không đồng thời kéo thêm một binding/provider SLF4J khác vào runtime, chẳng hạn Log4j2 binding không cần thiết. Một ứng dụng Spring Boot thực tế thường đã quản lý version và cấu hình Logback; tránh thêm dependency trùng hoặc lệch. Kiểm tra `mvn dependency:tree` trong dự án thật để biết provider/encoder nào được dùng.

### 8.3. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <logger name="example" level="INFO"/>

    <root level="WARN">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
```

Cấu hình này định nghĩa stdout encoder JSON. Nó **không tự thêm các field `schemaVersion`, `service`, `environment`** trừ khi bạn cấu hình encoder provider/customFields hoặc code phát ra chúng. Các tên mặc định như `@timestamp`, `logger_name`, `thread_name` phụ thuộc encoder/version; **không ép giả định tên field dựa trên bảng demo JDK**. Muốn thống nhất schema giữa services, cần một config được review và test.

### 8.4. `src/main/java/example/StructuredLoggingApp.java`

```java
package example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class StructuredLoggingApp {
    private static final Logger LOG =
            LoggerFactory.getLogger(StructuredLoggingApp.class);

    public static void main(String[] args) {
        MDC.put("requestId", "req-17");

        try {
            LOG.atInfo()
                .addKeyValue("schemaVersion", 1)
                .addKeyValue("service", "order-service")
                .addKeyValue("environment", "demo")
                .addKeyValue("eventType", "ORDER_CANCEL_RESULT")
                .addKeyValue("action", "ORDER_CANCEL")
                .addKeyValue("operationId", "op-7")
                .addKeyValue("outcome", "REJECTED")
                .addKeyValue(
                        "reasonCode", "ORDER_ALREADY_SHIPPED")
                .addKeyValue("durationMs", 12)
                .log("Cancellation rejected");
        } finally {
            MDC.clear();
        }
    }
}
```

### 8.5. Chạy và xác minh

Trong thư mục `structured-log-lab`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.StructuredLoggingApp
```

Ứng dụng sẽ phát một event INFO qua cấu hình Logback ở trên. **Không chốt stdout nguyên văn** của logstash encoder vì timestamp runtime, logger name, thread và các provider có thể thay đổi. Nghiệm thu đúng là: mỗi dòng ứng dụng là JSON hợp lệ; có `eventType`, `outcome`, `reasonCode`, `operationId`, `durationMs` với kiểu/giá trị phù hợp và `requestId` khi MDC được hỗ trợ/configured trong encoder.

Nếu field nào không xuất hiện, **không im lặng kết luận migration thành công**: kiểm tra encoder/provider `keyValuePairs`, `mdc` và phiên bản backend. Với cấu hình encoder composite, cần khai báo provider tương ứng; một số encoder chỉ xử lý message hoặc structured arguments theo cách riêng. Test trên output thực sự là nguồn sự thật.

### Vì sao vẫn có `message`?

Structured event không cấm câu mô tả. `message` nên ngắn, an toàn, hướng tới người đọc và **không** được parse để suy `outcome` hay `reasonCode`. Nếu message thay đổi từ “Cancellation rejected” thành “Cancel not allowed”, business metrics dựa vào `reasonCode` vẫn phải ổn.

## 9. Từ ứng dụng hiện tại sang fluent structured logging

Chuyển một log call site theo các bước:

### Trước: text ghép nhiều thông tin

```java
logger.warn(
    "Cannot cancel " + orderId
        + " because status " + status
        + ", request " + requestId);
```

### Sau: business outcome tách khỏi log

```java
CancelResult result = orderService.cancel(command);

// LOG chỉ phản ánh kết quả đã có.
logger.atInfo()
    .addKeyValue("eventType", "ORDER_CANCEL_RESULT")
    .addKeyValue("action", "ORDER_CANCEL")
    .addKeyValue("resourceId", safeOrderId)
    .addKeyValue("outcome", result.outcome())
    .addKeyValue("reasonCode", result.reasonCode())
    .log("Cancel operation finished");
```

Đây là **snippet phụ thuộc project** với `CancelResult`, `orderService` và `safeOrderId`, không phải class Java độc lập. Nếu xử lý còn transaction, đừng phát `SUCCEEDED` trước khi commit; nếu commit chưa rõ, dùng `UNKNOWN`/đối soát thay vì tự đoán.

### Khi nào không cần chuyển mọi log?

- Những log debug nội bộ ít quan trọng có thể giữ message text nếu không có yêu cầu truy vấn field.
- Stack trace kỹ thuật vẫn có giá trị; có thể được ghi trong trường exception có kiểm soát.
- Một ứng dụng legacy có parser phụ thuộc pattern cần giai đoạn tương thích.
- Với event audit đã có repository chuẩn hóa, không nhất thiết nhét mọi event vào operational logger; giữ nguồn sự thật audit riêng.

**Không biến mọi từ trong câu text thành một field mới.** Chọn field có ý nghĩa truy vấn, khối lượng có thể quản lý, độ nhạy an toàn và contract ổn định.

## 10. Correlation ID và MDC: đúng scope, không rò chéo thread

Trong hệ thống phân tán, `requestId`, `traceId`, `spanId` và `operationId` giúp ghép event qua các service. MDC của SLF4J là cơ chế thông dụng để giữ context **gắn với thread hiện tại**, nhưng không tự tạo một distributed trace hoàn chỉnh.

Ví dụ trong một handler:

```java
// Snippet trong ứng dụng SLF4J.
Map<String, String> before = MDC.getCopyOfContextMap();

try {
    MDC.put("requestId", validatedRequestId);
    MDC.put("operationId", trustedOperationId);
    handleRequest();
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
```

Cần import `java.util.Map`, `org.slf4j.MDC` và có các biến/method thực trong ứng dụng. Phần `finally` giúp tránh request B kế thừa requestId của request A khi thread pool tái sử dụng thread.

### Không tự tin MDC sẽ lan truyền qua mọi async boundary

`CompletableFuture`, `ExecutorService`, thread pool và reactive frameworks có cơ chế context khác nhau. Nếu xử lý tiếp tục ở thread khác, capture/restore context theo API hỗ trợ của framework hoặc dùng instrumentation/tracing chuyên dụng. Đừng assume MDC tự sang thread con.

### Trường correlation từ client phải được đánh giá

Không copy raw `X-Request-ID` không giới hạn độ dài hoặc có newline vào MDC. Chọn ID server-generated hoặc validate theo format/length. Không dùng bearer token, session cookie hoặc email làm traceId chỉ để tiện truy vấn. Nếu trace context theo W3C Trace Context, dùng instrumentation/library đã hỗ trợ các header/trạng thái hợp lệ, không tự parse bằng regex đơn giản.

### Request ID khác operation ID

Một operation async có thể trải qua nhiều HTTP requests và retries; `operationId` có thể giữ qua những lần thử, trong khi `requestId` đổi. `eventId` là ID một event, không tự bằng `messageId`/`operationId`. Đặt tên field rõ để consumer không gộp sai số lần xử lý.

## 11. Exception và stack trace trong structured event

Một error log không nên chỉ còn:

```json
{"level":"ERROR","message":"Something failed"}
```

nếu đội vận hành cần biết loại lỗi, dịch vụ phụ thuộc và correlation. Nhưng cũng không nên copy raw exception message chứa URL, SQL, token hoặc payload mà chưa rà soát.

Một hợp đồng khả thi:

```json
{
  "eventType": "DEPENDENCY_CALL_RESULT",
  "level": "ERROR",
  "outcome": "FAILED",
  "reasonCode": "DEPENDENCY_TIMEOUT",
  "dependency": "payment-gateway",
  "requestId": "req-91",
  "error": {
    "type": "SocketTimeoutException",
    "message": "Dependency call timed out"
  }
}
```

Đây là mẫu schema minh họa; output thực phụ thuộc encoder. Một số encoder Logback đưa stack trace vào field dạng string ở top-level, không tự tạo object `error` nested như ví dụ.

### Mẫu logging trong SLF4J

```java
// Snippet trong ứng dụng có exception và các biến.
logger.atError()
    .addKeyValue("eventType", "DEPENDENCY_CALL_RESULT")
    .addKeyValue("outcome", "FAILED")
    .addKeyValue("reasonCode", "DEPENDENCY_TIMEOUT")
    .addKeyValue("dependency", "payment-gateway")
    .setCause(exception)
    .log("Dependency request failed");
```

SLF4J 2.x fluent `setCause(Throwable)` giúp gắn exception vào event. Encoder phải được kiểm tra để biết các trường exception và stack được render ra sao. Đừng serialize `exception.toString()` như một field thay thế nếu bạn cần cause chain; nó có thể bỏ thông tin quan trọng hoặc lộ dữ liệu.

### Log một lỗi ở boundary hợp lý

Nếu repository, service và controller đều ghi cùng Throwable, một lỗi có thể xuất hiện ba lần trên dashboard và đẩy tăng cảnh báo. Chọn boundary chịu trách nhiệm; những tầng khác có thể propagate exception/cause mà không log trùng. Business rejection dự kiến thường không cần full stack ở INFO, nhưng security audit có thể cần event riêng.

## 12. Bảo mật khi chuyển sang JSON: tránh biến rò dữ liệu thành dễ truy vấn

Structured logging giúp search dễ hơn; vì thế nếu log lộ secret thì **secret cũng dễ tìm và xuất hàng loạt hơn**. Migration phải đi kèm policy dữ liệu.

### Allowlist thay vì dump object

Không nên:

```java
logger.atDebug()
    .addKeyValue("request", requestDto)
    .log("Payment request");
```

`requestDto.toString()` hoặc encoder serializer có thể chứa họ tên, địa chỉ, token, số thẻ, email. Ưu tiên allowlist:

```java
logger.atDebug()
    .addKeyValue("paymentMethodRef", safeMethodRef)
    .addKeyValue("amountMinorUnits", amountMinorUnits)
    .addKeyValue("currency", currencyCode)
    .addKeyValue("requestId", validatedRequestId)
    .log("Payment request received");
```

Đoạn code là snippet, không độc lập. Với thông tin tiền, phân biệt kiểu số/đơn vị; không serialize nhầm tiền theo floating-point thiếu precision.

### Dữ liệu không nên ghi

- Password, OTP, API key, access/refresh token, session cookie, Authorization header.
- Private key, secret config, credential trong URL/DB connection string.
- Raw request/response body có thể chứa PII hoặc payment data.
- Full stack trace/exception message nếu chưa đánh giá nội dung và quyền.
- Dữ liệu tùy ý do client gửi vào structured fields không có giới hạn kích thước/encoding.
- ID nhạy cảm trong metric labels có cardinality cao.

### Log injection và JSON escaping

Input có dấu `\r`/`\n`, dấu nháy hoặc backslash phải được encode đúng. JSON encoder giúp escape chuỗi nhưng **không tự giải quyết** dữ liệu nhạy cảm, ID giả, duplicate keys, control char trong name hoặc truy cập trái phép vào sink.

Nếu field `message` chứa chuỗi `\n` sau escape, downstream parse một JSON record thay vì nhiều dòng. Cần **integration test ở output cuối** để bảo đảm agent/collector không phân cắt sai.

### Quyền và retention

JSON event có thể chứa định danh actor/resource; quyền xem/index/export phải được quản lý, retention theo loại dữ liệu và environment. Với audit có nghĩa vụ pháp lý, structured JSON không thay thế integrity, access audit và durability controls.

## 13. Migration theo bước: từ baseline tới cutover

Một dự án thực hành nên chia thành các đợt có kết quả kiểm chứng được.

### Giai đoạn A — Inventory và contract

- Danh sách event quan trọng và consumer của log cũ.
- Version schema, required/optional fields, field types và naming conventions.
- Quy tắc exception, MDC, correlation, PII, retention.
- Chọn encoder và xác minh dependency tương thích Java/backend.
- Danh sách alert/query/regex sẽ cần cập nhật.
- Baseline volume, parse rate và delivery latency.

### Giai đoạn B — PoC một service hoặc endpoint

Chọn một service nhỏ, một eventType có nghiệp vụ rõ, ví dụ `ORDER_CANCEL_RESULT`.

- Phát field `action`, `outcome`, `reasonCode`, `operationId` đúng semantics.
- Chạy unit/integration tests, parse NDJSON output.
- Xác minh event đến collector và có thể query theo key/type.
- So số operation từ nguồn nghiệp vụ với số unique event ở sink khi có event ID.
- Kiểm tra exception, Unicode, newline, null và token giả.

### Giai đoạn C — Parallel/compatibility có giới hạn

Nếu cần duy trì consumer cũ, giữ text và JSON trong thời gian chuyển tiếp hoặc cho collector transform JSON thành view text. Đếm theo unique event ID để không nhân đôi dashboard. Ghi rõ ngày tắt parser text, phạm vi dual-write, điểm chịu trách nhiệm rollback.

### Giai đoạn D — Rollout từng phần

- Staging với dữ liệu thử → canary một pod/instance → một phần traffic → toàn service → nhiều services.
- Xác minh logger profile và appender path ở môi trường cần thiết.
- Theo dõi ingest volume, parse errors, latency, queue drop, schema field coverage và alert health.
- Nếu collector không hỗ trợ cấu trúc như mong muốn, rollback encoder hoặc sửa pipeline trong phạm vi đã duyệt.

### Giai đoạn E — Cutover và dọn phụ thuộc

- Chuyển dashboards, saved searches, alert rules sang structured fields.
- Review lại sampling/filter để không bỏ các event critical.
- Tắt dual-write sau thời gian xác minh.
- Xóa regex/parser text cũ khi tất cả consumer đã được chuyển đổi.
- Lưu tài liệu schema, ownership, release version và runbook.

**Điều kiện không nên cutover:** thiếu field cần thiết, parse error còn cao, data leak, event count sai, mất SLO quan trọng hoặc chưa có cơ chế rollback.

## 14. Kiểm thử: schema/field/type thay vì khóa nguyên dòng JSON

Một test giòn:

```java
assertEquals(
    "{\"level\":\"INFO\",\"outcome\":\"REJECTED\"}",
    actualLine);
```

Thứ tự keys, timestamp và field bổ sung có thể thay đổi dù event vẫn hợp lệ. Với schema JSON, nên **parse rồi assert cấu trúc**.

Ví dụ với Jackson + JUnit 5 trong dự án có dependency tương ứng:

```java
// Test snippet, cần ObjectMapper, JsonNode,
// outputJson và JUnit Jupiter được khai báo/import.
JsonNode event = new ObjectMapper().readTree(outputJson);

assertEquals("ORDER_CANCEL_RESULT",
             event.path("eventType").asText());
assertEquals("REJECTED",
             event.path("outcome").asText());
assertEquals("ORDER_ALREADY_SHIPPED",
             event.path("reasonCode").asText());
assertTrue(event.path("durationMs").isIntegralNumber());
assertEquals(12L, event.path("durationMs").asLong());
assertTrue(event.path("timestamp").isTextual());
```

**Đừng dừng ở `path(...).asText()`**, vì khi field thiếu, Jackson có thể trả default làm test pass sai trong vài trường hợp. Bổ sung `hasNonNull`, `isTextual`, schema validation và check giá trị enum; phần trên minh họa hướng tiếp cận chứ không phải bộ schema validator đầy đủ.

### Ma trận test đề xuất

| Case | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Normal success | `outcome=SUCCEEDED` | JSON hợp lệ, đúng field/type |
| Business rejection | `REJECTED/ORDER_ALREADY_SHIPPED` | Không parse reason từ message text |
| Technical failure | Throwable `SocketTimeoutException` | Exception type/cause được giữ theo policy |
| Null/optional field | Không có requestId | Contract null/omission đúng |
| Number vs string | `durationMs=12` | JSON number, không `"12ms"` |
| Unicode | Message tiếng Việt | Parse round-trip chính xác |
| Dấu quote/backslash | `"x"` hoặc `\` | JSON escaping đúng |
| CR/LF | Input chứa newline | Một JSON object/event, không log injection |
| Token giả | `FAKE_TOKEN_TEST_73` trong raw payload | Không lộ trong sink nếu policy cấm |
| MDC context | Hai request trên thread pool | ID đúng request, không rò context |
| Logger level/filter | INFO bị tắt, ERROR được bật | Không ảnh hưởng kết quả nghiệp vụ |
| Async appender | Event đến muộn | Đợi sink với timeout/latch; không sleep may rủi |
| Dual-write | Cùng operation ra hai sinks | Dashboard không double-count |
| Parser downstream | Consumer JSON field | Truy vấn/alert vẫn nhận đúng data |
| Rollback | Chuyển lại encoder cũ | Không thay đổi business processing |

### Test một record trên một dòng

Ví dụ với output của `StructuredLogMigrationDemo` ở phần 7, có thể dùng một JSON parser (Jackson trong Java hoặc công cụ parser đã có) để parse từng line. Kỳ vọng có đúng **hai JSON objects**, `message` thứ hai chứa newline *sau khi decode* nhưng dòng stdout vẫn là **một JSON line**.

Không kết luận “JSON hợp lệ” bằng `line.startsWith("{")` và `line.endsWith("}")`: chuỗi giữa có thể sai escape hoặc type.

## 15. Kiểm thử logging với JUL/Logback và không làm giòn test

Tại unit test domain, kiểm tra hành vi nghiệp vụ riêng trước. Tại logging test, nên capture **event trước encoder** khi muốn kiểm tra level/template/key–value/MDC/Throwable; tại encoder test thì parse output JSON; tại delivery test thì kiểm tra sink thật.

Với Logback:
- Có thể gắn một `AppenderBase<ILoggingEvent>` trong bộ nhớ và assert `getLevel()`, `getMessage()`, `getMDCPropertyMap()`, `getKeyValuePairs()` nếu backend/version hỗ trợ.
- Dùng logger riêng/cô lập, `additive=false` để tránh root appender làm nhiễu.
- Gỡ/dừng appender và restore MDC trong `finally`.
- Nếu event được xử lý bất đồng bộ, gọi `prepareForDeferredProcessing()` tại ranh giới thích hợp để snapshot dữ liệu lười như MDC khi cần; tránh đọc context đã clear từ thread khác.
- Test message template/structured fields có ý nghĩa; không assert đầy đủ timestamp, thread name và mọi stack frame.

Đối với `java.util.logging`:
- `Handler` thu `LogRecord`, kiểm tra `Level`, `getMessage()`, `getParameters()`, `getThrown()`.
- `LogRecord`/JUL formatter không đồng nhất với Logback event; không cast sai API.
- Một chương trình dùng JUL bridge tới SLF4J có thể đòi kiểm tra bridge/handler riêng.

Nếu test chỉ `verify(logger).info(...)`, nó chưa chứng minh encoder phát field đúng, sink nhận log hoặc data được redacted. **Mỗi lớp nên có một oracle kiểm thử riêng.**

## 16. Performance và volume: JSON không tự “nhẹ hơn” text

Migration có thể làm JSON event **dài hơn** vì lặp tên key, metadata, MDC và exception. Mặt khác, JSON giúp tránh regex parse phức tạp ở collector và cải thiện chất lượng truy vấn. Không khẳng định luôn nhanh hơn hay chậm hơn: cần đo.

Các số liệu cần theo dõi:

| Metric | Vấn đề muốn phát hiện |
| --- | --- |
| Events/s theo service/level | Sự thay đổi volume sau migration |
| Bytes/event, bytes/s | Chi phí encode, network, lưu/index |
| CPU/allocations/GC | Serializer, caller data, stack trace overhead |
| Request p95/p99 | Block vì sync appender hoặc queue đầy |
| Async queue depth/dropped events | Backpressure hoặc mất event |
| Collector 429/5xx/retry | Transport/ingest quá tải |
| Parse error ratio | Event malformed/unsupported |
| Required-field coverage | Key thiếu hoặc null bất thường |
| Query latency | Field/index design có phù hợp không |
| Log cost/retention | Budget storage và compliance |

### AsyncAppender không làm event durable

Logback `AsyncAppender` có queue trong RAM. `queueSize`, `discardingThreshold`, `neverBlock` và `maxFlushTime` ảnh hưởng drop, blocking và shutdown; chúng **không tự bảo đảm event đã bền vững ở collector**. Khi queue đầy, tùy cấu hình event có thể bị discard hoặc application thread bị block.

JSON encoder có thể chạy ở thread appender; tăng field quá nhiều hoặc serialize object lớn sẽ làm worker chậm và queue backlog. Chỉ đưa field cần thiết, giới hạn kích thước giá trị, tránh serialize cả DTO hoặc stack trace khổng lồ cho business rejection thường gặp.

### Logger level có thể giảm công việc nhưng không bảo đảm toàn bộ

Với `logger.debug("payload {}", expensiveOperation())`, Java vẫn đánh giá argument trước khi gọi logger; nếu `expensiveOperation()` có side effect hoặc chi phí cao, DEBUG tắt **không ngăn** phép tính đó. Sử dụng guard/lazy API cho diagnostic thuần túy, không cho logic nghiệp vụ.

## 17. Monitoring chất lượng structured logging sau triển khai

Có thể theo dõi:

- `log_json_parse_errors_total` — số record không parse được.
- `log_required_field_missing_total{field}` — thiếu field bắt buộc; label field từ tập hữu hạn.
- `log_schema_version_total{version}` — phân bố schema versions.
- `log_pipeline_dropped_total{stage}` — event bị drop tại nơi có thể quan sát.
- `log_collector_ingest_errors_total` — lỗi collector.
- `log_event_delivery_latency_seconds` — độ trễ từ source tới mốc đích đã định nghĩa.
- `log_canary_delivery_total{result}` — canary tốt/xấu từ ứng dụng tới sink.
- `log_structured_event_count{eventType,outcome}` — phân bố nghiệp vụ, nếu đúng nguồn và sampling policy.

Đây là **tên metric minh họa**, không tự có trong SLF4J/Logback. Đừng đưa `requestId`, `orderId`, `userId` hoặc message text vào metric label vì cardinality cao và rủi ro lộ dữ liệu.

Một dashboard cần phân biệt:
1. **Source event count** (nếu có nguồn đáng tin, ví dụ audit outbox).
2. **Delivered/ingested unique event count**.
3. **Parseable/queryable event count**.
4. **Missing/late/duplicate** sau khi đối soát cùng event ID/cohort.

Chỉ chia “số JSON parse OK / số JSON đã tới collector” không thể phát hiện event bị drop trước collector. Với event critical, dùng source IDs, reconciler hoặc canary end-to-end; không tuyên bố log pipeline 100% đáng tin vì parse error bằng 0.

### Một số ngưỡng cảnh báo

- Tỷ lệ parse fail tăng sau rollout.
- `reasonCode`/`outcome` biến mất khỏi query dù console còn log.
- Ingest rate/volume tăng vượt ngân sách.
- Số canary tới sink giảm hoặc trễ.
- Event exception quá nhiều do log duplicate ở nhiều tầng.
- Dữ liệu nhạy cảm xuất hiện trong sink theo test giả đã được phê duyệt.
- MDC rò requestId giữa hai task.

Ngưỡng cụ thể cần theo traffic, SLO và mức ưu tiên của từng loại log, không chọn một con số chung vô căn cứ.

## 18. Troubleshooting khi JSON xuất hiện không như mong đợi

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Vẫn là text console | `logback.xml` không load, backend khác, appender sai | Xác minh provider, config active, root appender |
| JSON parse lỗi | Formatter thêm text/ANSI hoặc newline raw | Kiểm tra từng line, JSON encoder và upstream driver |
| `addKeyValue` không ra field | Encoder/provider không xuất key–value pairs | Dùng đúng provider, test version/config |
| `requestId` không có | MDC chưa set hoặc bị clear/không propagate | Kiểm tra context tại thread phát event |
| Field `durationMs` thành string | Code/encoder serialize khác schema | Giữ numeric field, schema test |
| Field trùng keys hoặc bị ghi đè | MDC/customFields va chạm reserved keys | Đổi tên, có policy namespace, test conflicts |
| JSON hợp lệ nhưng dashboard trống | Parser/index mapping/query cũ dùng regex | Cập nhật mapping/query, kiểm tra pipeline từng chặng |
| Tăng log volume mạnh | Thêm field, duplicate appender hoặc TRACE bật | Kiểm tra additivity/filters, chỉ giữ field cần thiết |
| Exception mất stack | Encoder/proxy/filter không include throwable | Test `Throwable` ở event và output theo policy |
| Stack chứa secret | Raw exception payload/header bị copy | Redaction/allowlist, xử lý sự cố lộ dữ liệu |
| Log bị mất ngẫu nhiên | Async queue drop, agent rate-limit, collector lỗi | Drop/backpressure metrics, delivery design |
| Event xuất hiện hai lần | Dual-write, additivity, transport retry | Phân biệt bản sao và event IDs |
| Order giữa event đổi | Async/multi-thread/batching | Dùng IDs và causal boundaries, không suy từ thứ tự hiển thị |
| Logback config áp một pod | Config drift, pod restart hoặc deployment chưa đều | Xác minh service/version/instance |
| Rollback parser không phục hồi | Consumer text đã tắt quá sớm | Giữ kế hoạch tương thích có kiểm chứng |

### Không sửa lỗi bằng cách mở root TRACE ngay

Nếu JSON thiếu một field, vấn đề có thể ở **encoder/provider**, không phải logger level. Mở TRACE chỉ làm tăng volume và có nguy cơ lộ dữ liệu. Hãy dùng event thử nhỏ, schema và kiểm tra pipeline theo ranh giới.

## 19. Rollback an toàn và bảo toàn khả năng quan sát

Migration có thể phải rollback khi:
- JSON làm parser/alert trọng yếu không hoạt động.
- Số event/field bắt buộc thiếu hoặc sai kiểu.
- Encoder gây tăng latency/CPU hoặc queue drop.
- Event chứa thông tin nhạy cảm do code/config mới.
- Một phần cluster có JSON, phần khác text mà collector không phân loại được.

Phương án rollback gồm:

1. Giữ cấu hình encoder cũ có version và cơ chế deploy/flag được kiểm soát.
2. Dự phòng parser/ingest hỗ trợ hai format trong thời gian chuyển tiếp khi cần.
3. Không xóa mapping/index cũ trước khi kiểm chứng các consumer.
4. Rollback encoder hoặc route có phạm vi, không thay đổi business logic chỉ để sửa log.
5. Kiểm tra alert quan trọng, event source-to-sink và secret policy sau rollback.
6. Ghi rõ event nào phát text, event nào phát JSON trong khoảng chuyển đổi.
7. Tắt dual-write khi đã xác nhận số liệu và hành vi ổn định, tránh chi phí kéo dài.

**Rollback format không nhất thiết rollback schema business.** Nếu version event mới đã được consumer dùng, giữ cơ chế chuyển đổi phù hợp; không im lặng đổi nghĩa `outcome` hoặc `reasonCode`.

### Có nên rollback ngay khi một JSON line sai?

Cần xét tác động, mức độ lỗi và điều kiện dừng đã định nghĩa. Một event bị lỗi escaping ở luồng ít quan trọng khác với việc audit log bị loại toàn bộ. Nếu có nguy cơ secret leak, phản ứng an toàn thường ưu tiên dừng phát dữ liệu nhạy cảm và triển khai incident response, không chờ đủ volume.

## 20. Bảo đảm structured log không thay control flow

Một migration thành công không được vô tình biến logging thành cơ chế ra quyết định. Các anti-pattern cần tránh:

```java
// SAI: ghi kết quả thay vì trả kết quả.
if (!authorized) {
    logger.atWarn()
        .addKeyValue("outcome", "DENIED")
        .log("Access denied");
}
return secretData;
```

Structured JSON dù đúng schema **không thay authorization enforcement**. Phải `return`/`throw` hoặc chặn ở policy layer.

Tương tự:
- `outcome=SUCCEEDED` trước transaction commit không đáng tin.
- Ghi `PROCESSING_COMPLETED` không thay broker ACK/offset commit.
- Ghi `RETRY_SCHEDULED` không thực sự tạo retry job.
- Ghi `AUDIT_EVENT` trên async best-effort không tự bảo đảm bằng chứng bền vững.
- Tắt DEBUG không được thay đổi tác dụng của command.

**Nguồn sự thật nghiệp vụ** phải được giữ bằng transaction, result, state store, domain event và hợp đồng delivery. Logging chỉ quan sát.

## 21. Bài tập nâng cao và tiêu chí nghiệm thu

### Bài tập A — Field semantics

Chọn ba event text hiện tại (success, rejection, technical failure). Chuyển sang JSON với `eventType`, `outcome`, `reasonCode` và IDs. Tự giải thích vì sao business `REJECTED` không nhất thiết phải là ERROR.

**Đạt:** dashboard group theo `reasonCode` mà không cần regex trên message.

### Bài tập B — Unicode, newline và log injection

Cho message chứa:
- tiếng Việt có dấu;
- dấu nháy kép và backslash;
- ký tự xuống dòng;
- ID có ký tự điều khiển bị từ chối hoặc escape.

**Đạt:** mỗi event là một JSON record parse được, không tạo record giả và không làm thay đổi schema.

### Bài tập C — MDC và concurrency

Chạy hai request trên thread pool, mỗi request có ID khác nhau. Thu event từ sink.

**Đạt:** event A không mang requestId B, event B không mang requestId A; context được restore/clear sau task, kể cả khi exception.

### Bài tập D — Exception và redaction

Tạo exception giả có message chứa `FAKE_TOKEN_TEST_73` và error type rõ. Cấu hình policy không gửi raw secret tới sink.

**Đạt:** log vẫn có `reasonCode`/`error.type` hữu ích nhưng không lộ token giả tại bất cứ sink nào trong phạm vi bảo vệ.

### Bài tập E — Delivery và rollback

Tắt collector trong môi trường test, phát event critical có ID. Khôi phục collector rồi kiểm tra policy retry/backpressure/spool. Thử rollback encoder về text trong canary.

**Đạt:** có số liệu chính xác về event lost/late/duplicate, không tuyên bố guarantee cao hơn những gì đã kiểm chứng; rollback không làm business state sai.

### Bài tập F — Kiểm tra tương thích query

Chuyển saved search/alert từ `message contains "already shipped"` sang `eventType=ORDER_CANCEL_RESULT` + `reasonCode=ORDER_ALREADY_SHIPPED`.

**Đạt:** đổi cách viết `message` mà alert/query vẫn đúng. Đồng thời có test schema/version để tránh field rename âm thầm.

## 22. Tổng hợp lỗi phổ biến và cách tránh

| Sai lầm | Tác hại | Phòng ngừa |
| --- | --- | --- |
| Nghĩ `logger.info("x={}", x)` đã là structured field | Downstream chỉ thấy text | Dùng key–value event + encoder hỗ trợ, kiểm tra sink |
| Đổi formatter mà không review parser | Dashboard/alert đột ngột trống | Inventory consumer và rollout canary |
| Dùng `message` làm nguồn query chính | Refactor câu chữ làm hỏng search | `eventType`/`reasonCode` có contract |
| Chọn field type không nhất quán | Index mapping conflict | Schema tests, versioning |
| Serialize nguyên DTO/exception | Lộ token/PII, tăng volume | Field allowlist và redaction |
| Không escape newline/control chars | Split event sai, log injection | JSON encoder, test Unicode/CRLF |
| Không cleanup MDC | Rò requestId giữa threads | `finally`/context propagation test |
| Đếm dual-write như hai operations | Dashboard tăng giả | Unique event ID/dedup |
| Giữ cả text/JSON vô thời hạn | Tăng chi phí/khó vận hành | Ngày cutover và plan deprecation |
| Coi JSON output là durable | Audit có thể mất khi appender/collector lỗi | Outbox/ack/retention theo contract |
| Bật DEBUG/TRACE để test field | Tăng tải/lộ dữ liệu | Synthetic event và encoder integration test |
| Chỉ snapshot raw JSON string | Fail vì key order/timestamp | Parse field/type/schema |
| Không test collector outage | Silent drop không bị phát hiện | Fault injection và source-to-sink measurement |
| Không có rollback | Incident kéo dài khi encoder lỗi | Versioned config, staged rollout |
| Không giới hạn cardinality/value size | Index/cost tăng vọt | Schema allowlist, size limits, metric label policy |

## 23. Checklist trước khi merge và triển khai

- [ ] Đã kiểm kê logger, appender, collector, parser và alert đang phụ thuộc log text.
- [ ] Có schema versioned, tên field và type nhất quán.
- [ ] Định nghĩa rõ eventType, action, outcome, reasonCode và correlation IDs.
- [ ] Không parse message text để suy nghiệp vụ sau migration.
- [ ] Runtime chỉ có một SLF4J backend/provider phù hợp.
- [ ] Encoder thật xuất `keyValuePairs` và MDC theo yêu cầu, không chỉ message.
- [ ] Một event/một JSON line tại sink; escaping Unicode/CRLF/dấu nháy chính xác.
- [ ] Kiểu số/boolean/null được giữ, không lẫn string.
- [ ] Có test parse JSON, schema required fields, exception và field type.
- [ ] Có test không lộ fake secret ở mọi sink cần bảo vệ.
- [ ] MDC được validate, propagate đúng async context và cleanup.
- [ ] Business outcome/transaction/ACK không phụ thuộc logging.
- [ ] Đã đánh giá volume/latency, queue drop, ingest quota và retention.
- [ ] Có canary, metrics parse errors, field coverage, source-to-sink checks.
- [ ] Có rollout từng giai đoạn, thời hạn dual-write và kế hoạch rollback.
- [ ] Consumer dashboard/search/alert mới đã được kiểm thử trước cutover.
- [ ] Audit quan trọng có reliability/retention/access controls riêng.
- [ ] Schema/encoder/config được review và có người sở hữu dài hạn.

**Kết luận:** chuyển từ text log sang structured log là **một thay đổi hợp đồng dữ liệu và vận hành**, không chỉ thay pattern console bằng JSON. Hãy bắt đầu từ event semantics, field types và consumer; sử dụng SLF4J/backend/encoder đúng khả năng, test JSON tại sink, bảo vệ dữ liệu nhạy cảm, triển khai từng giai đoạn và giữ khả năng rollback. Khi đó log mới vừa đọc được bởi người, vừa truy vấn được bởi hệ thống mà không làm sai control flow hay đánh đồng “đã log” với “đã lưu bền vững”.
