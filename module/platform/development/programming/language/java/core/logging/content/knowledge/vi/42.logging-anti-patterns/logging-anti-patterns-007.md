# Phụ thuộc format không ổn định trong Java Core Logging

## Mục tiêu học tập

Bài thuộc nhóm **Anti-pattern logging**, chủ đề **Phụ thuộc format không ổn định**. Hệ thống Java có thể ghi log đầy đủ nhưng monitoring, alerts, dashboards hoặc quy trình điều tra vẫn hỏng nếu các thành phần phía sau **phụ thuộc vào cách dòng log được hiển thị**. Thay một câu thông báo, thêm trace ID vào pattern, đổi locale/timezone, chuyển text sang JSON hoặc nâng version logging backend có thể phá vỡ bộ phân tích log mà ứng dụng không hề báo lỗi.

Sau bài này, bạn có thể:

- Phân biệt **ý nghĩa sự kiện**, **message template**, **formatted message**, **logging event**, **structured fields** và **encoder/layout**.
- Nhận diện anti-pattern dựa vào vị trí token, regex text, chuỗi exception, stack trace/line number, timestamp locale, thread name và thứ tự JSON fields.
- Định nghĩa event code, error code, field types, timestamp semantics, schema version và compatibility rules.
- Hiểu cách JUL, SLF4J, Logback, Log4j 2 và log collector xử lý fields, không tự giả định metadata ở source luôn tới được backend.
- Chạy Java 17 demo độc lập chứng minh classifier dựa câu chữ bỏ sót một event dù structured metadata vẫn mô tả cùng lỗi.
- Thiết kế migration v1/v2, consumer contract tests, canary và monitoring cho format drift.
- Ngăn thay format gây log injection, lộ bí mật, mất audit/alert hoặc đếm trùng events.

**Nguyên tắc chính:** Human-readable message được phép thay đổi. Machine consumers phải dựa trên **hợp đồng dữ liệu có cấu trúc, được version hóa và kiểm thử**, không tự biến presentation format thành API ngầm.

## 1. Một thay đổi nhỏ có thể làm mất cảnh báo

Ban đầu app ghi:

```text
2026-11-10 09:00:00 ERROR [checkout] Order failed: order-42
```

Một hệ thống alert áp quy tắc:

```text
line contains "ERROR [checkout] Order failed:"
```

Khi đội Java chuyển sang structured JSON, event thành:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event_code": "order.processing_failed",
  "order_id": "order-42",
  "error_code": "DOWNSTREAM_TIMEOUT",
  "message": "Payment provider timed out"
}
```

Về nghiệp vụ, lỗi vẫn tồn tại. Nhưng alert cũ mất match vì layout và lời văn đã đổi. Dashboard có thể hiển thị “0 errors” trong khi HTTP 5xx và các business metrics vẫn tăng.

**Lỗi thiết kế không nằm ở JSON.** Một thành phần downstream đã phụ thuộc text layout mà không có schema contract, test hoặc migration.

Các thay đổi thường gây format drift:

1. Thêm `trace_id`, `span_id`, MDC, thread name hoặc marker vào prefix.
2. Chuyển PatternLayout text sang JSON encoder, hoặc đổi structured field names.
3. Nâng JDK/Logback/Log4j 2, thay backend hoặc log shipper.
4. Sửa wording tiếng Anh sang tiếng Việt, hoặc thay tên exception.
5. Đổi timezone, Locale, date precision, daylight-saving display.
6. Thêm cause/suppressed exceptions làm stack trace dài hoặc multiline.
7. Log collector thay cách flatten nested JSON, rename fields hoặc filter.
8. Chuyển nguồn stdout/file/HTTP, thay framing và serialization.
9. Rollout nhiều instance khiến v1 và v2 cùng tồn tại.
10. Security redaction làm nội dung message thay đổi, làm parser regex không còn match.

Một số thay đổi là cần thiết và có lợi. Ta cần **bảo vệ consumers khỏi phụ thuộc sai**, không phải đóng băng mọi format mãi mãi.

## 2. Đâu là hợp đồng dữ liệu, đâu chỉ là cách trình bày?

Một pipeline logging phổ biến:

```text
Java application
  |
  +-- event meaning / code / attributes / exception / context
  |
  v
JUL LogRecord / SLF4J event / Log4j 2 LogEvent
  |
  +-- effective level, filters, sampling, routing
  |
  v
Formatter / Encoder / Layout
  |
  +-- text pattern, JSON, XML, binary representation
  |
  v
file / stdout / network appender
  |
  v
agent / collector (parse, transform, enrich, filter)
  |
  v
index / search / dashboard / alert
```

Cần phân biệt:

| Thành phần | Vai trò | Có nên làm khóa semantic ổn định? |
| --- | --- | --- |
| `event_code` | Mã nhận dạng loại event, ví dụ `order.processing_failed` | Có, theo contract |
| `error_code` | Loại lỗi, ví dụ `DOWNSTREAM_TIMEOUT` | Có, theo enum đã định nghĩa |
| `message template` | `"Order {} failed"` | Không mặc định |
| `formatted message` | `"Order order-42 failed"` | Không, thường phục vụ người đọc |
| `logger name` | Package/class gọi logger | Không làm business ID |
| `thread name` | Thread xử lý tại một thời điểm | Không làm operation ID |
| `exception message` | Chi tiết chẩn đoán từ thư viện/ứng dụng | Không làm stable error code |
| `stack trace` | Call frames/cause/suppressed | Không parse như protocol nghiệp vụ |
| `trace_id` | Correlation liên service | Có theo giao thức trace, nhưng không phải ID event duy nhất |
| `timestamp` | Event/ingest time theo schema | Có nếu semantics/timezone/precision rõ |
| `schema_version` | Chọn cách diễn giải fields | Có |

Có structured fields tại source chưa đủ: layout/encoder phải serialize chúng, collector phải parse đúng, index phải giữ đúng types, và dashboard phải query đúng tên.

**Structured logging cũng có thể bất ổn** nếu team tùy tiện đổi `duration_ms` thành `duration` hoặc number thành string. JSON là phương tiện thể hiện, không thay thế schema governance.

## 3. Anti-pattern: split log theo vị trí

```java
// Anti-pattern, không phải cách parse log production đáng tin.
String[] tokens = line.split(" ");
String severity = tokens[2];
String owner = tokens[3];
```

Nếu pattern từ `timestamp level logger message` đổi sang `timestamp trace_id level thread logger message`, token positions lệch. Dấu cách trong timestamp hoặc message, newline trong exception, delimiter trong input làm việc split càng dễ sai.

**Thay bằng:** structured fields có key và type. Nếu bắt buộc xử lý legacy text, cần một grammar versioned, quoting/escaping, test malformed input và metrics parse errors; không âm thầm trả dữ liệu giả khi parser hỏng.

| Cách parse mong manh | Thay đổi làm vỡ |
| --- | --- |
| `line.split(" ")[2]` | Thêm field vào prefix |
| `contains("Order failed")` | Dịch hoặc sửa câu |
| `substring(indexOf("user="))` | Giá trị user chứa delimiter |
| `split(",")` | Message có dấu phẩy hoặc CSV quoting |
| `grep "ERROR"` | JUL dùng `SEVERE` hoặc text chứa ERROR |
| `split("\n")` | Stack trace có nhiều dòng |
| Regex exact timestamp | Timezone/locale/precision đổi |
| Regex stack frame | Class/file/line refactor |

## 4. Anti-pattern: phụ thuộc lời văn message

Một lỗi có thể được diễn đạt:

```text
Order failed: order-42
Đơn hàng order-42 xử lý thất bại
Payment provider did not answer in time
```

Nếu monitoring chỉ tìm `"Order failed:"`, hai câu sau bị bỏ sót. Ngôn ngữ/copywriting không phải định danh event.

Mô hình ổn định:

```text
event_code=order.processing_failed
order_id=order-42
error_code=DOWNSTREAM_TIMEOUT
```

Lời văn vẫn có thể được cải thiện. **Event code giữ nguyên khi ý nghĩa không đổi**, và đổi code/version khi thật sự đổi semantic.

Định danh event nên:

- Có namespace theo domain: `auth.access_denied`, `payment.authorization_failed`.
- Không chứa ID động; `order.failed.order-42` gây cardinality cao.
- Không dựa vào tên class/method sẽ thay khi refactor.
- Phân biệt `attempted`, `accepted`, `committed`, `rolled_back`, `unknown`.
- Có owner, tài liệu, retention và chính sách version/deprecation.
- Không dùng exception.getMessage() làm enum error code.

Một `TimeoutException` có thể xuất hiện khi remote đã thực hiện side effect nhưng client không nhận response. Log should mô tả **timeout/UNKNOWN outcome**, không tự suy từ exception string rằng business operation chắc chắn thất bại.

## 5. Anti-pattern: dùng stack trace như API

```text
java.lang.IllegalStateException: checkout failed
    at com.example.OrderService.process(OrderService.java:77)
Caused by: java.net.SocketTimeoutException: remote timeout
    at com.example.Client.call(Client.java:135)
    Suppressed: java.io.IOException: cleanup failed
```

Line numbers, package names, call frames, wrapping và cách rút gọn frames có thể đổi sau refactor, JDK update hoặc thư viện thay implementation. Một regex `"OrderService.java:77"` không ổn định để phân loại lỗi.

Thay vào đó:

- `event_code` cho sự kiện.
- `error_code` cho error category.
- `exception_type`, `cause_type` hoặc cause fields theo schema.
- `stack_trace` dành để chẩn đoán, có thể truncate/redact.
- `trace_id`/`operation_id` để ghép luồng.

Kiểm thử Throwable/cause/suppressed bằng API ở tầng model trước, rồi test serializer layout riêng. Không buộc format full stack trace trở thành golden string khi không phải public contract.

### Multiline

Một stack trace có thể có hàng trăm dòng. Shipper line-oriented có thể chia một exception thành hàng trăm events, còn NDJSON hợp lệ thường encode newline trong string. Khi chuyển format, cần update multiline parser và kiểm tra **số logical events** ở backend, không chỉ kiểm tra source đã in exception.

## 6. Anti-pattern: timestamp và locale không rõ ràng

Hai định dạng:

```text
10/11/2026 09:30:00
2026-11-10T02:30:00Z
```

Nếu dòng đầu dùng giờ Việt Nam và ngày/tháng tương ứng, chúng có thể cùng thời điểm; tuy nhiên dòng đầu **không mang offset/timezone**. `10/11` còn có thể hiểu theo thứ tự ngày/tháng khác.

Trong Java:

- `Instant` đại diện một thời điểm trên UTC timeline.
- `OffsetDateTime` có offset.
- `ZonedDateTime` có zone phù hợp để hiển thị/logic lịch.
- `LocalDateTime` không có offset/zone, không đủ làm global event timestamp.
- `System.nanoTime()` để đo elapsed duration, không ghi timestamp epoch across hosts.

Đoạn tích hợp Java 17:

```java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant occurredAt = Instant.now(clock);
String eventTimestamp = occurredAt.toString();
```

Đây là trích đoạn, không phải một class runnable độc lập. Schema phải phân biệt `event_timestamp` và `observed_timestamp`/ingest timestamp. Nếu một upgrade đổi ý nghĩa `timestamp` từ lúc event xảy ra sang lúc collector nhận, đây là **semantic breaking change** dù cùng là ISO-8601.

Clock skew giữa hosts có thể làm các mốc dường như ngược nhau; ordering nghiệp vụ có thể cần aggregate version/sequence chứ không chỉ sort timestamp.

## 7. Anti-pattern: parser phụ thuộc text severity

JUL có `Level.SEVERE` và `Level.WARNING`; SLF4J/Logback thường dùng `ERROR` và `WARN`. Nếu một parser chỉ chấp nhận `ERROR`, nó có thể bỏ sót JUL SEVERE sau khi đổi bridge/backend.

**Giải pháp:** Normalize severity theo mapping được công bố và test. Phân biệt raw source severity với canonical `severity` field nếu pipeline có nhiều backend. Đừng parse bằng việc tìm token `ERROR` trong message: một INFO message cũng có thể chứa chữ “ERROR”.

Logger name, thread name, hostname, stack frame và version-specific placeholders đều là metadata hữu ích nhưng không tự làm identity của business operation.

## 8. Thiết kế structured logging contract

Một event mẫu:

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-10T02:30:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event_code": "order.processing_failed",
  "order_id": "order-42",
  "error_code": "DOWNSTREAM_TIMEOUT",
  "retry_count": 2,
  "duration_ms": 350,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Payment provider did not answer in time"
}
```

Đây là **JSON minh họa do bài học đề xuất**; không phải output mặc định của JUL/Logback/Log4j 2.

| Field | Contract nên định nghĩa | Anti-pattern |
| --- | --- | --- |
| `schema_version` | Phiên bản schema | Đổi breaking fields không version |
| `timestamp` | Instant/offset rõ, precision theo yêu cầu | Chuyển thành local date string |
| `level` | Enum canonical | Lẫn `WARN`/`WARNING` không mapping |
| `event_code` | Ý nghĩa ổn định | Đổi theo wording/copywriting |
| `order_id` | String, giữ leading zero | Ép thành number |
| `error_code` | Enum low-cardinality | Raw exception.getMessage() |
| `retry_count` | Number, số attempts/retries được định nghĩa | String `"two"` |
| `duration_ms` | Number tính bằng milliseconds | String `"350ms"` |
| `trace_id` | Correlation, có null policy | Dùng làm unique event ID |
| `message` | Text phục vụ người đọc | Machine parser lệ thuộc câu văn |

### Types, nullability, version

Các kiểu JSON khác nhau:

```json
{"duration_ms": 250, "retryable": true, "order_id": "00042"}
```

và:

```json
{"duration_ms": "250ms", "retryable": "yes", "order_id": 42}
```

Không tương thích với downstream tính toán latency, boolean filtering và ID có leading zero. **Đổi type hoặc units thường là breaking change.**

Ba trạng thái dưới đây cũng có thể khác nghĩa:

```json
{"trace_id": null}
```

```json
{"trace_id": ""}
```

```json
{}
```

Consumer phải biết required/optional fields, nullability và fallback. Thêm field optional có thể tương thích nếu consumers bỏ qua unknown fields; xóa required field hoặc rename/đổi semantic cần migration. Thêm enum value cũng có thể phá consumer dùng exhaustive matching.

### Nested và flattened fields

```json
{"error": {"code": "DOWNSTREAM_TIMEOUT"}}
```

và:

```json
{"error.code": "DOWNSTREAM_TIMEOUT"}
```

là hai biểu diễn cần được thống nhất. Một backend coi dấu chấm là nested path; backend khác có thể dùng literal key. Không giả định cả hai truy vấn giống nhau.

**JSON object key order không phải contract ổn định.** Test theo field name/type, không theo thứ tự key trong raw string.

## 9. Java 17 độc lập: message thay đổi, event code không đổi

Ví dụ dùng **chỉ JDK 17+ và java.util.logging**, không cần SLF4J, Logback, Maven hoặc collector. Hai log records có cùng loại lỗi và metadata, nhưng formatted message khác ngôn ngữ. Bộ lọc dựa vào chữ tiếng Anh chỉ nhận 1/2; bộ đếm đọc `EventData.eventCode` nhận 2/2.

**Giới hạn:** `LogRecord.getParameters()` cho phép gắn parameters, nhưng Formatter/Handler mặc định **không tự bảo đảm** serialize object thành structured JSON. Trong ví dụ, một Handler in-memory đọc parameters. Production muốn query `event_code` ở backend phải có formatter/exporter được cấu hình đúng và integration test.

Tạo file **`LogFormatContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogFormatContractDemo {
    record EventData(int schemaVersion,
                     String eventCode,
                     String orderId,
                     String errorCode) {
    }

    static final class CaptureHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<>();

        CaptureHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
            }
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }

        List<LogRecord> snapshot() {
            return List.copyOf(records);
        }
    }

    static EventData dataOf(LogRecord record) {
        Object[] parameters = record.getParameters();
        if (parameters == null || parameters.length != 1
                || !(parameters[0] instanceof EventData data)) {
            throw new IllegalStateException(
                    "Missing structured EventData");
        }
        return data;
    }

    static void require(boolean condition, String label) {
        if (!condition) {
            throw new IllegalStateException(
                    "Assertion failed: " + label);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger(
                "demo.logging.format.contract");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CaptureHandler capture = new CaptureHandler();
        logger.addHandler(capture);

        EventData stable = new EventData(
                1,
                "order.processing_failed",
                "order-42",
                "DOWNSTREAM_TIMEOUT");

        try {
            logger.log(Level.WARNING,
                    "Order failed: order-42", stable);
            logger.log(Level.WARNING,
                    "Đơn hàng order-42 xử lý thất bại", stable);

            List<LogRecord> actual = capture.snapshot();
            require(actual.size() == 2, "record count");

            int fragileTextMatches = 0;
            int stableCodeMatches = 0;

            for (LogRecord record : actual) {
                require(record.getLevel() == Level.WARNING,
                        "warning level");
                if (record.getMessage().startsWith("Order failed:")) {
                    fragileTextMatches++;
                }

                EventData data = dataOf(record);
                require(data.schemaVersion() == 1,
                        "schema version");
                require("order-42".equals(data.orderId()),
                        "order ID");
                require("DOWNSTREAM_TIMEOUT".equals(data.errorCode()),
                        "error code");
                if ("order.processing_failed"
                        .equals(data.eventCode())) {
                    stableCodeMatches++;
                }
            }

            require(fragileTextMatches == 1, "fragile parser");
            require(stableCodeMatches == 2, "stable event code");

            System.out.println("log_records=" + actual.size());
            System.out.println("matched_by_english_text="
                    + fragileTextMatches);
            System.out.println("matched_by_event_code="
                    + stableCodeMatches);
            System.out.println("schema_version="
                    + stable.schemaVersion());
            System.out.println("stable_error_code="
                    + stable.errorCode());
            System.out.println("test=PASS");
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LogFormatContractDemo.java
java LogFormatContractDemo
```

**stdout chính xác:**

```text
log_records=2
matched_by_english_text=1
matched_by_event_code=2
schema_version=1
stable_error_code=DOWNSTREAM_TIMEOUT
test=PASS
```

### Vì sao kết quả đúng?

1. Logger và Handler dùng `Level.ALL`, cho phép cả hai WARNING records.
2. Overload `Logger.log(Level, String, Object)` tạo LogRecord có mảng parameters chứa object `EventData`.
3. Message thứ nhất có prefix `Order failed:`; message thứ hai không có, vì vậy text classifier chỉ nhận một event.
4. `eventCode` của hai records cùng bằng `order.processing_failed`, nên semantic classifier nhận cả hai.
5. `setUseParentHandlers(false)` tránh JUL parent handlers tự in warning ra stderr; stdout chỉ có sáu dòng từ chương trình.
6. Assertions kiểm tra level, schema version, ID và error code. Chỉ sau khi qua tất cả mới in `test=PASS`.
7. `CaptureHandler` dùng `ArrayList` vì demo một thread; Handler concurrent thật cần synchronization/collection phù hợp.
8. Đây chỉ là **bài test in-memory**, không chứng minh JSON output, collector ingestion hay index durability.

**Thử sửa:** Đổi câu tiếng Anh sang câu khác; bộ lọc text thay đổi, trong khi event code có thể giữ nguyên nếu semantic giống. Đổi code một record thành mã khác sẽ khiến assertion stable count fail. Nếu tắt WARNING bằng logger level SEVERE, cả hai biến mất; structured data không tự vượt filter.

## 10. SLF4J 2.x và Logback: metadata cần encoder

SLF4J 2.x hỗ trợ fluent key-value pairs:

```java
// Trích đoạn tích hợp SLF4J 2.x, cần logger và backend.
logger.atWarn()
      .addKeyValue("event_code", "order.processing_failed")
      .addKeyValue("order_id", "order-42")
      .addKeyValue("error_code", "DOWNSTREAM_TIMEOUT")
      .log("Payment provider did not answer in time");
```

Các attributes đã được đính vào logging event **không tự động** hiện thành JSON fields ở mọi layout. Ví dụ appender chỉ có `%msg%n` có thể không in chúng. Cần cấu hình encoder xuất fields đúng và integration test raw output.

### MDC

```java
// Trích đoạn SLF4J, yêu cầu logger và traceId có sẵn.
try (org.slf4j.MDC.MDCCloseable scope =
             org.slf4j.MDC.putCloseable("trace_id", traceId)) {
    logger.warn("event_code={} error_code={}",
            "order.processing_failed", "DOWNSTREAM_TIMEOUT");
}
```

MDC hữu ích cho correlation nhưng không tự propagate qua mọi executor hoặc CompletableFuture. Với thread pool reuse, cần cleanup/restore để tránh gắn trace ID của request trước. Không đưa password, bearer token hoặc raw payload vào MDC. Nếu encoder mới tự xuất toàn bộ MDC, có thể lộ thông tin trước đây không in: **format migration phải kiểm tra security**.

Message template như `"retry_count={}"` không tự bảo đảm JSON field `retry_count` là number. Dùng structured encoder với typed fields khi consumers cần tính toán.

## 11. Logback PatternLayout dễ làm legacy regex hỏng

Pattern text cũ:

```xml
<encoder>
    <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
</encoder>
```

Pattern mới:

```xml
<encoder>
    <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level trace=%X{trace_id} %logger - %msg%n</pattern>
</encoder>
```

Đây là **trích đoạn XML encoder**, không phải một file `logback.xml` đầy đủ. Khi triển khai phải kiểm tra version, timezone, appender, status và effective config.

Parser cố định thứ tự `TIMESTAMP LEVEL [THREAD] LOGGER - MESSAGE` sẽ không còn đúng khi thread bị bỏ hoặc trace ID chèn thêm. Nhiều pods cùng chạy v1/v2 còn có thể phát hai format xen kẽ trong rolling deployment.

Nếu raw text là **wire contract bắt buộc**, không nên sửa pattern tùy ý: version, documented grammar, escaping, contract tests, rollout và deprecation window. Nếu text chỉ phục vụ người đọc, hãy tách consumer sang structured fields.

### Log4j 2 khác Logback

Log4j 2 có PatternLayout và các dạng layout có cấu trúc; API/config không đồng nhất với Logback. Không copy tokens/XML của Logback sang Log4j 2 mà không test. Chú ý severity mapping JUL `WARNING/SEVERE` so với SLF4J `WARN/ERROR` và việc exception/markers/MDC có được serialize hay không.

## 12. Chuyển text → JSON còn những rủi ro gì?

### JSON escaping

```java
// Anti-pattern: nối JSON bằng raw input.
String json = "{\"user\":\"" + userInput + "\"}";
```

Khi `userInput` chứa dấu nháy, newline, backslash hoặc control character, output có thể invalid hoặc gây log injection. Dùng encoder/serializer đúng chuẩn và kiểm thử Unicode, quotes, CR/LF, kích thước record, truncation.

### NDJSON và multiline

Một structured log JSON có thể chứa stack trace nhiều dòng trong **một JSON string field escaped**. Nếu formatter pretty-print object ra nhiều dòng còn shipper vẫn đọc từng dòng, nó có thể phá record framing. Cần test một logical event có ra đúng một structured record ở sink/index không.

### Nested vs flattened

```json
{"error": {"code": "DOWNSTREAM_TIMEOUT"}}
```

Khác với:

```json
{"error.code": "DOWNSTREAM_TIMEOUT"}
```

Backend có thể diễn giải dotted key khác nhau. Không đoán rằng query path sẽ giữ nguyên khi đổi collector/encoder.

### Không test bằng raw string exact

JSON key order và khoảng trắng không nên thành hợp đồng. Parse JSON thành object rồi assert keys, types và values. Chỉ dùng golden raw snapshot khi chính raw byte layout là một giao diện đã công bố; nếu không, snapshot timestamp, thread và stack frames thường flaky.

## 13. Versioned event catalog

Một catalog nên định nghĩa:

- Event code và nghĩa stable; ví dụ `order.processing_failed` khác `order.processing_retried`.
- Schema version (theo event family hoặc stream).
- Required/optional attributes, type, nullability, units.
- Timestamp source và precision.
- Severity mapping khi nhiều logging backends.
- Exception type/cause/stack trace policy.
- Correlation IDs và trust level của incoming headers.
- Masking/PII, retention và quyền đọc theo category.
- Owner, review, deprecation, migration và rollback.

### Những thay đổi thường cần version mới

| Thay đổi | Tác động |
| --- | --- |
| Thêm optional field | Có thể backward-compatible nếu consumer bỏ qua unknown fields |
| Xóa required field | Breaking |
| Rename `error_code` | Breaking với queries cũ |
| `duration_ms` number → string | Breaking về type |
| milliseconds → seconds mà giữ tên cũ | Breaking về semantics |
| `timestamp` event-time → ingest-time | Breaking về meaning |
| Thêm enum value | Có thể breaking với exhaustive consumers |
| Đổi message wording nhưng giữ semantics | Thường không breaking nếu message là presentation |
| Thêm cause field optional | Thường có thể compatible nếu policy cho phép |
| Thay route/tenant/retention | Có thể ảnh hưởng security/compliance, cần review độc lập |

Version không giải quyết mọi việc tự động. Consumer cần test các version được hỗ trợ; parser không được im lặng map “unknown” thành một giá trị business sai.

## 14. Migration v1/v2 có kiểm soát

**Giai đoạn 1 — Kiểm kê:** Liệt kê parsers, alert rules, dashboards, SIEM detections, saved searches, batch exports, operator scripts, tests và runbooks. Một consumer legacy đang grep log có thể rất quan trọng cho incident response.

**Giai đoạn 2 — Contract:** Chốt event codes, schema versions, field types, nullability, timestamps, error/severity semantics, security và owner.

**Giai đoạn 3 — Phát thử:** Dùng staging để phát event qua encoder thật; đọc output tại stdout/file/collector, parse, validate và kiểm tra data minimization.

**Giai đoạn 4 — Dual-run:** Khi cần, cho phép v1 và v2 trong compatibility window. Tách index/route hoặc dùng event ID để tránh double-count; kiểm tra cả security sinks.

**Giai đoạn 5 — Migrate consumers:** Chuyển alert/dashboard/SIEM sang structured fields, không dựa human text. Có fixtures cho cả v1/v2 và positive/negative tests.

**Giai đoạn 6 — Cutover:** Theo dõi parser rejections, index mapping errors, required-field missing, canary và event counts. Phải xác định rollback path và dữ liệu hai versions có thể cùng tồn tại đến hết retention.

**Giai đoạn 7 — Loại legacy:** Chỉ dừng v1 sau khi mọi consumer bắt buộc đã chuyển và migration window kết thúc.

Không tạo thêm business events chỉ để đổi format. Một source event được fan-out sang hai sink có thể tạo **hai bản thể hiện**; cần quy định dedup/route và không coi đó là hai business operations.

## 15. Contract tests thay vì snapshot dễ vỡ

### Source unit tests

- Sự kiện có đúng `event_code`, `error_code`, `outcome`.
- Metadata required đầy đủ, type và unit đúng.
- Exception cause/type được gắn, không chỉ có exception message.
- Dynamic IDs không bị chèn vào event code.
- Success không emit terminal error; rollback không emit committed success.
- Sensitive data bị loại/mask.
- Đổi wording không phá semantic assertions.

### Encoder integration tests

1. Gắn test appender/handler hoặc test sink.
2. Phát event đã biết, kể cả Throwable có cause và suppressed exceptions.
3. Đọc **serialized output thật**, parse JSON bằng thư viện chuẩn của project.
4. Assert keys/types, timestamp, severity mapping, correlation, redaction.
5. Thử quotes, backslash, newline, Unicode và oversized payload.
6. Đảm bảo output không bị tách multiline ngoài policy.
7. Kiểm tra duplicate/routing và appender filter.
8. Thử backend/framework phiên bản thực tế của production.

### Consumer contract fixtures

```text
v1 legacy input      -> parsed while supported
v2 structured input  -> schema-valid
malformed JSON       -> explicit parse error
missing required     -> visible validation failure
wrong numeric type   -> validation failure
unknown enum         -> documented fallback/version
newline injection    -> safe escaping
multiline exception  -> logical event count as expected
```

Không bắt buộc reject unknown optional fields nếu contract cho phép mở rộng. Nhưng thiếu required field hoặc mapping sai không được âm thầm trả giá trị mặc định có vẻ thành công.

### End-to-end tests

Phát canary có `event_id` riêng qua JVM → appender → shipper → collector → backend. Query **structured attributes** `event_code`/`error_code`/`schema_version`, kiểm tra types, đúng tenant, không bị duplicate hoặc lộ secret. Pipeline có thể eventual-consistent nên dùng polling có deadline, tách **not emitted**, **not ingested**, **not searchable** và **query error**.

## 16. Ma trận kiểm thử format drift

| Mã | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| F1 | Đổi thông báo tiếng Anh sang tiếng Việt | Event code giữ nguyên |
| F2 | Thêm trace ID trong text pattern | Structured query không phụ thuộc token position |
| F3 | Đổi timezone và locale hiển thị | Machine timestamp vẫn rõ nghĩa |
| F4 | Đổi precision thời gian | Schema parser xử lý theo version |
| F5 | Exception thêm cause/suppressed | Exception type và error code vẫn đúng |
| F6 | Input chứa quote, comma, newline | JSON hợp lệ và không injection |
| F7 | Count/duration number thành string | Validation phát hiện breaking change |
| F8 | Optional field missing/null/empty | Đúng nullability policy |
| F9 | Thêm enum outcome | Consumer có compatibility handling |
| F10 | Rename event code | Contract test fail nếu chưa migrate |
| F11 | Rolling deploy v1/v2 | Alert không đứt và không double-count |
| F12 | MDC trace ID missing/leak | Không gắn nhầm user/request |
| F13 | JUL SEVERE / SLF4J ERROR | Severity mapping đúng |
| F14 | Nested vs flattened JSON | Query hiểu đúng cấu trúc |
| F15 | Multiline stack trace | Một logical exception event theo policy |
| F16 | Encoder xuất thêm MDC fields | Không lộ token/PII |
| F17 | Queue drop hoặc sampling | Phân biệt deliberate filtering và loss |
| F18 | Collector parser sai nhưng không throw | Semantic assertions bắt được |
| F19 | JSON key order thay | Parser theo key không hỏng |
| F20 | Backfill/replay legacy logs | Giữ event time, version, ID và dedup |

## 17. Giám sát format drift trong production

Tình huống khó nhất là **silent failure**: ứng dụng vẫn ghi log nhưng parser không còn tạo field mà dashboard đang dùng. Cần kết hợp metrics và canary:

| Metric gợi ý | Phát hiện |
| --- | --- |
| `log_events_emitted_total` | Đã emit bao nhiêu event ở source instrumentation |
| `log_events_ingested_total` | Collector nhận bao nhiêu |
| `log_parse_failures_total` | Parser không hiểu input |
| `log_schema_validation_failures_total` | Field/type/enum sai |
| `log_required_field_missing_total` | Thiếu event code/timestamp/service |
| `log_index_rejections_total` | Index mapping hoặc validation reject |
| `log_multiline_fragments_total` | Một exception bị split |
| `log_events_sampled_out_total` | Sampling có chủ đích |
| `log_queue_dropped_total` | Queue loss ngoài ý muốn |
| `log_canary_missing_total` | Synthetic event không đến sink đúng deadline |

**Các tên trên chỉ là gợi ý**, không tự có trong mọi framework/distribution. Giới hạn metric labels ở service, environment, schema version, error category; không dùng message_id, trace_id, user_id hoặc raw exception message làm labels.

Canary minh họa:

```json
{
  "schema_version": 1,
  "event_code": "logging.contract.canary",
  "event_id": "canary-20261110-001",
  "service": "checkout",
  "timestamp": "2026-11-10T02:30:00Z",
  "probe": true
}
```

Checker độc lập truy vấn theo field, không chỉ `message contains "canary"`. Nếu event đến nhưng field sai type: **SCHEMA_FAILURE**. Nếu backend query không hoạt động: **QUERY_ERROR/UNKNOWN**, không tự khẳng định tất cả log đã mất. Canary đi qua đúng route, không chứa secret và có chính sách sampling rõ.

## 18. Runbook khi dashboard bỗng không có ERROR

Ví dụ giả định: một release vừa deploy, số lỗi trong dashboard giảm về 0 nhưng HTTP 5xx metrics tăng.

1. **Xác minh lỗi nghiệp vụ** từ metrics/trace thay vì kết luận chỉ theo log counts.
2. **Khoanh vùng** service, release, instance, environment, thời gian thay đổi.
3. **Tìm raw event** ở stdout/file trước agent: logger level/filter/sampling có đổi không?
4. **Kiểm tra effective format**: PatternLayout, encoder, schema version, timestamp, log provider.
5. **Kiểm tra collector**: parse/rejection counters, mapping, multiline, transforms, routing.
6. **Kiểm tra backend**: index/tenant, search permissions, ingest lag, missing required fields.
7. **Đọc alert query**: có còn grep text `Order failed` hoặc phụ thuộc token index không?
8. **Khắc phục có kiểm soát**: sửa parser/query hoặc rollback format theo compatibility plan, không tắt logging security.
9. **Đối chiếu** source, collector, index counts và canary; lưu ý sampling/duplicate.
10. **Postmortem**: cập nhật contract fixtures, schema validation, alert và deprecation checklist.

Nếu reprocess legacy logs, giữ original timestamps và event IDs; không replay business commands chỉ để “lấp log”. Dữ liệu log không được tự làm phát sinh một side effect nghiệp vụ mới.

## 19. Bảo mật khi format thay đổi

Một JSON encoder mới có thể phát toàn bộ MDC hoặc structured arguments trước đây không hiện trong text. Các rủi ro:

- Token/cookie/password/private key từ headers bị lộ.
- Exception message chứa URL/query, SQL hoặc dữ liệu cá nhân.
- User input có newline tạo log injection nếu text serializer không escape.
- Field schema đổi làm log bị route sang index/tenant rộng quyền.
- Redaction chỉ hoạt động trên message nhưng không lọc JSON fields/MDC.
- Sampling ít hơn khiến team nhầm rằng dữ liệu nhạy cảm “hiếm khi bị lộ” nên được chấp nhận.
- Alert/metrics vô tình dùng raw exception message làm label, gây rò và cardinality cao.

Test canary secret giả ở mọi field, exception và sink; dùng allowlist dữ liệu, retention và RBAC. Không bao giờ coi việc chuyển sang structured JSON là tự động an toàn hoặc tự động đáp ứng audit.

## 20. Checklist triển khai

- [ ] Đã kiểm kê mọi consumer đọc raw log text/regex/positions?
- [ ] Có event code và error code ổn định?
- [ ] Có schema version, types, units, required/optional/nullability?
- [ ] Timestamp có source, timezone/offset và precision rõ?
- [ ] Không dùng message text, exception message, line number làm business ID?
- [ ] Formatter/encoder thật sự serialize structured fields?
- [ ] Có severity mapping JUL/SLF4J/Log4j 2 được test?
- [ ] JSON có escaping và multiline framing đúng?
- [ ] Không phát token/PII mới do thay encoder/MDC?
- [ ] Consumer tests bao gồm v1/v2, missing fields và unknown enum?
- [ ] Golden snapshots chỉ khóa những fields thực sự thuộc contract?
- [ ] Có canary end-to-end query bằng event_code và schema_version?
- [ ] Có metrics parse/schema/index rejection và queue/sampling loss riêng?
- [ ] Có compatibility window và rollback cho rolling deployment?
- [ ] Alert/SIEM không phụ thuộc câu diễn đạt có thể dịch?
- [ ] Không dùng diagnostic log làm source of truth cho audit/transaction?
- [ ] Có owner và review cho breaking schema changes?
- [ ] Có kiểm tra cả positive và negative events, duplicate/routing?
- [ ] Có quy trình hồi phục và data backfill an toàn nếu format drift?
- [ ] Dashboard phân biệt không có event với ingestion/query failure?

**Tiêu chí hoàn thành:** Bạn phân biệt được presentation format với event contract; biết vì sao regex/text parser/stack trace dễ vỡ; chạy được chương trình Java 17 cho kết quả **một text match nhưng hai event-code matches**; và thiết kế được schema, tests và migration mà không làm đứt observability.

## 21. Câu hỏi tự kiểm tra

1. Vì sao thêm trace ID vào PatternLayout có thể phá parser dù event không đổi?
2. Sự khác nhau giữa message template, formatted message và structured field?
3. Nếu team đổi tiếng Anh sang tiếng Việt, alert nên tìm event code hay chuỗi message?
4. Vì sao exception.getMessage() không nên làm stable error code?
5. Stack trace line numbers có thích hợp làm khóa nhận dạng lỗi lâu dài không?
6. `Instant` khác `LocalDateTime` thế nào khi các hosts ở nhiều timezones?
7. Tại sao JSON key order và whitespace không nên dùng làm schema?
8. Đổi `duration_ms` thành string `"250ms"` có breaking không?
9. Nếu SLF4J gắn key-value nhưng encoder không serialize, collector có field đó không?
10. JUL WARNING/SEVERE mapping với backend WARN/ERROR cần làm gì?
11. Vì sao parser không báo lỗi vẫn có thể map sai business semantics?
12. Multiline stack trace có thể tạo sai bao nhiêu records?
13. Vì sao dual-route migration có nguy cơ double-count?
14. Golden snapshot có ích khi nào, và nên tránh khóa gì?
15. Một release khiến dashboard ERROR giảm 0 nhưng 5xx tăng: kiểm tra những hop nào?
16. Structured JSON mới xuất toàn bộ MDC có nguy cơ gì?
17. Vì sao canary query theo raw message không đủ chứng minh schema đúng?
18. Nên theo dõi metric nào để phát hiện missing required field?
19. Một trace có nhiều log: trace ID có phải unique event ID không?
20. Nếu backend query unavailable, checker nên kết luận MISSING hay UNKNOWN?

## Tài liệu tham khảo

- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html) — message, parameters, Throwable.
- [Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — overload log và routing.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html) — format record.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — timestamp UTC.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — fluent key-value API.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html) — PatternLayout/MDC.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — logger hierarchy/levels.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html) — format/encoder.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — structured log fields và timestamps.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — log security/injection.
