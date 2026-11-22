# Field `level` trong JSON logging: chuẩn hóa mức độ nghiêm trọng của log

Trong **JSON logging**, mỗi bản ghi nên có một trường riêng để biểu thị **mức độ nghiêm trọng của sự kiện**, thường tên là `level`. Thay vì gộp chữ `INFO`, `WARN` hay `ERROR` vào một dòng text khó phân tích, structured log dùng **key và value có kiểu dữ liệu rõ ràng**, cho phép tìm kiếm, lọc, nhóm và xây dựng cảnh báo tự động.

Ví dụ:

```json
{"timestamp":"2026-11-09T03:15:30.123Z","level":"WARN","service":"order-service","event":"inventory_retry","requestId":"req-17","attempt":2}
```

Đây là **JSON minh họa**. Trường `level` có giá trị `"WARN"` dạng **JSON string**, không phải một enum do JSON định nghĩa sẵn. Ứng dụng và hệ thống thu thập phải thống nhất tập giá trị, cách viết hoa, quy tắc chuyển đổi từ logging API nguồn và chính sách xử lý mức chưa biết.

Bài học thuộc nhóm **JSON logging** và tập trung vào **field `level`**: ý nghĩa, kiểu dữ liệu, naming, bộ giá trị, cách ánh xạ mức JUL/SLF4J/Log4j 2, mối quan hệ với lọc level, đối chiếu OpenTelemetry/ECS, cách phát JSON một dòng an toàn bằng Java 17 và cách kiểm tra kết quả từ collector.

## 1. `level` là field gì, và khác message thế nào?

Một bản ghi structured logging có thể có:

```json
{
  "timestamp": "2026-11-09T03:15:30.123Z",
  "level": "ERROR",
  "logger": "com.example.order.OrderService",
  "service": "order-service",
  "event": "checkout_failed",
  "requestId": "req-17",
  "errorCode": "UPSTREAM_TIMEOUT",
  "message": "Cannot complete checkout"
}
```

Ý nghĩa các field:

| Field | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `timestamp` | Sự kiện được ghi nhận vào lúc nào? | `2026-11-09T03:15:30.123Z` |
| **`level`** | Sự kiện được phân loại nghiêm trọng đến mức nào? | `ERROR` |
| `logger` | Logger/category nào phát sự kiện? | `com.example.order.OrderService` |
| `service` | Ứng dụng/dịch vụ nào tạo log? | `order-service` |
| `event` | Loại sự kiện ổn định nào đã xảy ra? | `checkout_failed` |
| `requestId` | Đây là request nào? | `req-17` |
| `errorCode` | Nhóm lỗi nghiệp vụ/kỹ thuật nào? | `UPSTREAM_TIMEOUT` |
| `message` | Mô tả sự kiện để con người đọc | `Cannot complete checkout` |

**Điểm quan trọng:** `level` là **đánh giá mức độ/ưu tiên quan sát của log event**, không phải `errorCode`, không phải HTTP status, không phải logger name, và cũng không phải cơ chế phân loại dữ liệu mật.

Ví dụ một request HTTP trả `404` có thể được ghi ở mức `INFO` khi đó là tình huống dự kiến; một lỗi nội bộ `500` có thể được ghi `ERROR`. Không có quy tắc tự động rằng `HTTP status = 4xx` luôn tương đương `WARN` hoặc rằng mọi exception đều phải là `ERROR`.

### Vì sao phải dùng field riêng?

Với text log:

```text
2026-11-09 10:15:30 ERROR com.example.OrderService - checkout failed
```

Hệ thống tìm kiếm thường phải parse dựa vào vị trí hoặc regex. Nếu message chứa chữ `ERROR`, một truy vấn text đơn giản có thể tạo false positive.

Với JSON:

```json
{"level":"INFO","message":"Previous ERROR was recovered"}
```

Hệ thống đọc đúng trường `level` sẽ biết đây là **INFO**, dù `message` chứa chữ `ERROR`. Sự khác biệt này rất quan trọng khi thống kê tỷ lệ lỗi hoặc kích hoạt alert.

## 2. Contract đề xuất cho field `level`

Nếu ứng dụng tự sở hữu JSON schema và chưa phải theo schema bên ngoài, một contract đơn giản là:

- **Key:** `level` — cố định, chữ thường, không tự ý đổi thành `logLevel` ở một số service.
- **Kiểu dữ liệu:** **JSON string**.
- **Giá trị cơ bản:** `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`.
- **Giá trị bổ sung:** `FATAL` nếu API/backend và chính sách thực sự phân biệt mức fatal; không tự thêm khi không có ý nghĩa.
- **Casing:** chữ in hoa thống nhất, ví dụ `WARN` thay vì nơi ghi `warning`, nơi ghi `Warn`.
- **Ý nghĩa:** level của **event đã được phát**; không phải ngưỡng cấu hình hiện hành của cả ứng dụng.
- **Giá trị chưa biết:** có chính sách xử lý rõ ràng; không âm thầm thay mọi mức lạ thành `ERROR`.

Bảng tham khảo:

| Level chuẩn hóa | Khi nào có ích | Mức độ ưu tiên thường thấy |
| --- | --- | --- |
| `TRACE` | Diễn tiến cực chi tiết ở mức thấp | Thường tắt trong production |
| `DEBUG` | Thông tin giúp lập trình viên điều tra | Bật có kiểm soát |
| `INFO` | Sự kiện vận hành bình thường nhưng có ích | Thường được giữ |
| `WARN` | Tình huống bất thường, rủi ro, retry hoặc suy giảm | Nên theo dõi tần suất |
| `ERROR` | Thao tác thất bại hoặc vấn đề cần điều tra | Thường cần alert theo ngữ cảnh |
| `FATAL` (tùy hệ) | Sự cố nghiêm trọng khiến tiến trình/hệ thống không thể tiếp tục | Không phải mọi API đều hỗ trợ riêng |

**Không tự coi `FATAL` là mức mặc định của SLF4J**: SLF4J API thông thường cung cấp `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`; Log4j 2 có thêm `FATAL`. Mapping phải xuất phát từ **API nguồn** và contract của hệ thống thu thập, không dựa vào một bảng tưởng tượng chung cho mọi backend.

Nếu hệ thống cần cả mức **gốc** và mức **chuẩn hóa**, có thể dùng:

```json
{"level":"WARN","original_level":"WARNING","message":"Slow dependency response"}
```

Trong ví dụ này, `WARNING` là tên level nguyên gốc của **JUL**, còn `WARN` là giá trị chuẩn hóa cho việc truy vấn thống nhất giữa service. Hai field có trách nhiệm khác nhau. Đừng lưu hai trường mâu thuẫn mà không định nghĩa quy tắc mapping.

## 3. Lưu `level` là string hay number?

Có nhiều cách biểu diễn mức độ nghiêm trọng:

```json
{"level":"ERROR"}
```

```json
{"severity_number":17}
```

Đây là **hai schema ví dụ khác nhau**, không có nghĩa `17` là cách mã hóa `ERROR` bắt buộc cho mọi backend. Kiểu **string** thường dễ đọc và phù hợp khi chỉ có vài level; numeric severity có thể hữu ích cho sắp xếp/so sánh và chuẩn telemetry đã quy định dải số.

**Quy tắc: không trộn type cho cùng một key.** Đây là hai event không nên tồn tại lẫn lộn trong một index/schema nếu `level` được khai báo là string:

```json
{"level":"ERROR"}
{"level":1000}
```

`1000` có thể là `Level.SEVERE.intValue()` của JUL, nhưng **không đồng nghĩa** với `ERROR` trong chuẩn JSON do nhóm tự chọn hoặc `SeverityNumber` của OpenTelemetry. Nếu muốn lưu số gốc của JUL, dùng tên rõ ràng như `jul_level_value` và mô tả đơn vị/hệ mức.

### OpenTelemetry Logs: `SeverityText` và `SeverityNumber`

OpenTelemetry định nghĩa hai khái niệm:

- **`SeverityText`**: chuỗi mức log **gốc** như nguồn cung cấp (tên không cần khớp một enum toàn cầu).
- **`SeverityNumber`**: số mức độ nghiêm trọng **chuẩn hóa** trong model OpenTelemetry.

Các dải số trong OpenTelemetry Logs Data Model:

| Dải `SeverityNumber` | Nhóm mức |
| --- | --- |
| `1–4` | TRACE |
| `5–8` | DEBUG |
| `9–12` | INFO |
| `13–16` | WARN |
| `17–20` | ERROR |
| `21–24` | FATAL |

Giá trị `0` có thể dùng khi mức không được xác định theo quy tắc của model. **Không suy ra** JUL `SEVERE = 1000` thành `SeverityNumber = 1000`: phải áp dụng mapping của logging source sang dải OTel phù hợp. Trong bản ghi JSON do ứng dụng tự thiết kế, việc đặt tên `severity_number` chỉ hợp lệ khi có contract xác nhận đang dùng **cùng ngữ nghĩa** với OTel; không tự xưng là bản ghi OpenTelemetry gốc chỉ vì có tên gần giống.

### Elastic Common Schema: `log.level`

Nếu mục tiêu là **Elastic Common Schema (ECS)**, `log.level` là trường dạng keyword cho **mức log gốc** của sự kiện. Khi biểu diễn ECS dưới dạng JSON, object có thể có cấu trúc:

```json
{"log":{"level":"WARNING"},"message":"Slow dependency response"}
```

Một số pipeline dùng cú pháp field path `log.level` khi mapping/search; biểu diễn JSON nested và tên field có dấu chấm cần tuân theo contract của hệ đích. **Không coi một field tùy biến `level` là tự động tương đương ECS `log.level`** mà chưa cấu hình mapping. ECS `event.severity` còn có ý nghĩa số theo nguồn event, không phải một alias số học tùy ý của JUL level.

**Tóm lại:** Bạn có thể chọn `level` dạng uppercase string cho schema nội bộ, nhưng nếu gửi tới OTel/ECS cần **mapping explicit**: tên trường, type, preservation của raw severity và ngữ nghĩa numeric severity.

## 4. Mapping level giữa JUL, SLF4J, Logback và Log4j 2

Các framework Java có tên mức và API khác nhau. Dưới đây là **bảng gợi ý chuẩn hóa**, không phải hợp đồng bắt buộc cho mọi bridge.

| JUL (`java.util.logging.Level`) | SLF4J / Logback thông dụng | JSON `level` ví dụ | Ghi chú |
| --- | --- | --- | --- |
| `SEVERE` | `ERROR` | `ERROR` | Lỗi nghiêm trọng theo JUL |
| `WARNING` | `WARN` | `WARN` | Không ghi `WARNING` ở service khác rồi coi là `WARN` nếu chưa mapping |
| `INFO` | `INFO` | `INFO` | Sự kiện thông tin |
| `FINE` | `DEBUG` | `DEBUG` | Tương ứng gần đúng |
| `FINER` / `FINEST` | `TRACE` hoặc mức chi tiết gần đó | `TRACE` | Tùy policy và độ chi tiết |
| `CONFIG` | Không có mức tương đương bắt buộc | Theo policy hoặc lưu `CONFIG` gốc | Đừng âm thầm coi là `ERROR` |
| `OFF` / `ALL` | Mức cấu hình ngưỡng | **Không phải event thông thường** | Dùng để điều khiển lọc |

Với **Log4j 2**, các tên level thông dụng gồm `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`, cùng `OFF`, `ALL` phục vụ cấu hình. Một số framework còn cho phép custom level. Với **SLF4J 2.x**, các lời gọi thông thường gồm:

```java
// Fragment trong lớp đã khai báo org.slf4j.Logger LOG.
LOG.trace("event=trace_probe");
LOG.debug("event=inventory_lookup");
LOG.info("event=order_created");
LOG.warn("event=retry_scheduled");
LOG.error("event=payment_failed");
```

Đoạn này cần SLF4J API và một provider trong dự án, không phải chương trình JDK thuần.

**Quan trọng:** Bridge giữa API có thể chuyển level theo quy tắc của chính bridge. Vì thế JSON field `level` do backend cuối sinh ra có thể phản ánh **level đã được chuyển** chứ không giống 100% tên level ban đầu. Nếu cần audit về nguồn, giữ `original_level` khi mapping và bảo đảm được backend/pipeline thực sự cung cấp dữ liệu đó.

### Đừng nhầm level với exception type hoặc HTTP status

```json
{"level":"WARN","http.status_code":429,"errorCode":"RATE_LIMITED","event":"request_rejected"}
```

```json
{"level":"ERROR","http.status_code":500,"exceptionType":"IllegalStateException","event":"request_failed"}
```

Các object trên minh họa. HTTP `429` có thể là một kết quả rate limiting dự kiến; `500` thường biểu thị lỗi server cần chú ý. Nhưng level phải dựa vào **mức ảnh hưởng và chính sách vận hành**, không phải chỉ dựa vào sự tồn tại của `Throwable`.

Một `IllegalArgumentException` ở biên validation không nhất thiết là `ERROR`; ngược lại, một tiến trình không bắt được lỗi nghiêm trọng có thể cần mức cao hơn. Phân loại theo **outcome thực tế, khả năng phục hồi, mức độ bất thường và nhu cầu điều tra**.

## 5. Ngưỡng log (threshold) khác field `level`

Có hai thời điểm:

1. **Trước khi event được ghi:** logger/provider/handler quyết định event có vượt ngưỡng lọc hay không.
2. **Khi event được serialize:** encoder xuất field `level` của **event đã được chấp nhận**.

Ví dụ:

```text
Logger level = INFO
     |
     +-- DEBUG: không phát ra JSON từ logger này
     +-- INFO : có thể được ghi (nếu handler/appender cho phép)
     +-- WARN : có thể được ghi
     +-- ERROR: có thể được ghi
```

Nếu một event `DEBUG` bị filter **trước khi đến encoder**, việc dashboard truy vấn `level=DEBUG` không thể tìm lại event đó. Tăng retention, sửa JSON parser hay bật field `level` trong dashboard **không khôi phục log chưa từng được tạo**.

Trong JUL còn có mức ở `Logger` và mức ở từng `Handler`. Cả hai phải cho phép record thì nó mới tới formatter. Với Logback/Log4j 2, còn có level hierarchy, appender filters, threshold filters hoặc async pipeline tùy cấu hình.

**Không nhầm** giá trị trong JSON `"level":"INFO"` với giá trị `root.level=INFO`. Giá trị thứ nhất là **metadata của một record**; giá trị thứ hai là **chính sách lọc** ảnh hưởng tới những record nào được tạo/ghi.

### Level trong event đã phát nên nhất quán

Nếu ứng dụng ghi:

```json
{"level":"INFO","event":"startup_complete"}
```

thì collector không nên tự thay thành `ERROR` chỉ vì message có chữ `failed` hoặc tên service chứa từ `error`. Nếu muốn enrich hoặc reroute một sự kiện tới stream ưu tiên, hãy dùng **field khác** như `alert.priority` hoặc mapping có nguồn gốc, không phá dữ liệu level gốc mà không giải thích.

## 6. Ví dụ chạy được trên Java 17: JUL xuất JSON có `level`

Chương trình sau **không cần thư viện ngoài JDK**. Nó dùng JUL `Logger`, `ConsoleHandler`, `Formatter` và `LogRecord` để:

- Ghi mỗi event thành **một JSON object trên một dòng**.
- Tạo `level` **chuẩn hóa** và `original_level` **giữ tên level JUL**.
- Cho thấy ánh xạ `WARNING → WARN` và `SEVERE → ERROR`.
- Escape dấu nháy, backslash, newline và các control characters cơ bản để message không phá JSON.
- Dùng timestamp cố định của `LogRecord` để **đầu ra có thể kiểm chứng**.
- Đặt ngưỡng logger/handler là INFO để chứng minh `FINE` không được xuất.

Đây là code học thuật để thấy dữ liệu của event được định dạng thế nào. Trong production nên sử dụng **JSON encoder/serializer được duy trì**, thay vì duy trì một JSON serializer tự viết.

Lưu file **`JsonLevelDemo.java`**:

```java
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JsonLevelDemo {
    private static final Logger LOG =
            Logger.getLogger(JsonLevelDemo.class.getName());

    private static final DateTimeFormatter TIME =
            new DateTimeFormatterBuilder()
                    .appendInstant(3)
                    .toFormatter();

    private JsonLevelDemo() {
    }

    private static String normalizedLevel(Level level) {
        if (level == Level.SEVERE) return "ERROR";
        if (level == Level.WARNING) return "WARN";
        if (level == Level.INFO) return "INFO";
        if (level == Level.FINE) return "DEBUG";
        if (level == Level.FINER || level == Level.FINEST) return "TRACE";

        // Với CONFIG/custom Level: giữ nguyên tên gốc.
        return level.getName();
    }

    private static String jsonString(String value) {
        StringBuilder out = new StringBuilder("\"");
        String hex = "0123456789abcdef";

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
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
                        out.append("\\u00")
                           .append(hex.charAt((c >>> 4) & 15))
                           .append(hex.charAt(c & 15));
                    } else {
                        out.append(c);
                    }
            }
        }

        return out.append('"').toString();
    }

    private static void emit(Level level, Instant timestamp, String message) {
        LogRecord record = new LogRecord(level, message);
        record.setInstant(timestamp);
        record.setLoggerName(LOG.getName());
        LOG.log(record);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "{"
                        + "\"timestamp\":"
                        + jsonString(TIME.format(record.getInstant()))
                        + ",\"level\":"
                        + jsonString(normalizedLevel(record.getLevel()))
                        + ",\"original_level\":"
                        + jsonString(record.getLevel().getName())
                        + ",\"logger\":"
                        + jsonString(record.getLoggerName())
                        + ",\"message\":"
                        + jsonString(formatMessage(record))
                        + "}"
                        + System.lineSeparator();
            }
        });

        LOG.addHandler(console);
        try {
            Instant t = Instant.parse("2026-11-09T03:15:30.123Z");

            emit(Level.INFO, t, "event=created orderId=ord-7");
            emit(Level.WARNING, t.plusMillis(1),
                    "input=\"bad\"\nnext-line");
            emit(Level.SEVERE, t.plusMillis(2),
                    "event=checkout_failed");
            emit(Level.FINE, t.plusMillis(3),
                    "event=debug_hidden");
        } finally {
            LOG.removeHandler(console);
            console.close();
        }

        System.out.println("done=true");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 JsonLevelDemo.java
java JsonLevelDemo
```

**Các dòng JSON do chương trình ghi trên `stderr`:**

```json
{"timestamp":"2026-11-09T03:15:30.123Z","level":"INFO","original_level":"INFO","logger":"JsonLevelDemo","message":"event=created orderId=ord-7"}
{"timestamp":"2026-11-09T03:15:30.124Z","level":"WARN","original_level":"WARNING","logger":"JsonLevelDemo","message":"input=\"bad\"\nnext-line"}
{"timestamp":"2026-11-09T03:15:30.125Z","level":"ERROR","original_level":"SEVERE","logger":"JsonLevelDemo","message":"event=checkout_failed"}
```

Ở dòng thứ hai, các ký tự `\\\"` và `\\n` là **phần escape trong JSON string**; chúng không tạo một record JSON thứ hai. Lệnh `emit(Level.FINE,...)` không tạo output vì bị ngưỡng INFO lọc.

**`stdout` do chương trình chủ động ghi:**

```text
done=true
```

JUL `ConsoleHandler` xuất log qua **stderr**; `System.out.println` sử dụng stdout. Khi terminal gộp hai stream, thứ tự xen kẽ không được bảo đảm tuyệt đối, nhưng ba record JSON kể trên được ghi theo thứ tự của các lời gọi `emit` trong ví dụ đồng bộ.

### Phân tích kết quả

1. `INFO` vẫn là `INFO` sau chuẩn hóa.
2. `WARNING` của JUL trở thành `WARN` trong field `level`, nhưng field `original_level` giữ nguyên `WARNING`.
3. `SEVERE` trở thành `ERROR` để các service dùng schema chung có thể tìm theo `level=ERROR`.
4. `LOG.setLevel(INFO)` và `console.setLevel(INFO)` đều ảnh hưởng đến việc event có được ghi. `FINE` bị loại trước formatter.
5. `record.getInstant()` là timestamp đã gắn với `LogRecord`; việc format từ field này không gọi lại đồng hồ hệ thống khi encoder chạy.
6. `jsonString` escape message có nháy kép và newline, giữ **một event = một dòng JSON** trong trường hợp ví dụ.
7. `LOG.setUseParentHandlers(false)` tránh các handler cha ghi thêm output khác định dạng; trong ứng dụng thật phải theo kiến trúc logging chung, không vô hiệu propagation tùy tiện.

**Giới hạn của JSON serializer trong demo:** Hàm `jsonString` xử lý các ký tự điều khiển thông dụng và `U+0000` tới `U+001F`, nhưng không kiểm tra mọi trường hợp Unicode lỗi (ví dụ isolated surrogate), giới hạn message size, nội dung nhạy cảm, kiểu dữ liệu tùy ý hoặc các loại field phức tạp. Nếu message được lấy từ request/nguồn không tin cậy, production cần **JSON serializer chính thức, redaction, byte limits, schema validation và kiểm thử collector**. Không đưa toàn bộ request body/token vào log chỉ vì encoder có escaping.

## 7. Khi dùng SLF4J, Logback và Log4j 2 thật

Với ứng dụng đã dùng SLF4J hoặc Log4j 2, thường **không cần tự viết formatter** như demo. Hãy dùng provider/backend và encoder có hỗ trợ structured logging phù hợp phiên bản và schema mong muốn.

### SLF4J 2.x

```java
// Fragment trong lớp có org.slf4j.Logger LOG.
LOG.atWarn()
   .addKeyValue("event", "inventory_retry")
   .addKeyValue("attempt", 2)
   .log("Inventory temporarily unavailable");
```

Đây là API fluent của **SLF4J 2.x**; không chạy độc lập với JDK. `atWarn()` chọn mức WARN, `addKeyValue` thêm những cặp key-value vào logging event theo khả năng của API/provider. **Việc key-value xuất thành JSON field thật hay chỉ nằm trong text phụ thuộc encoder/backend**. Đừng suy ra từ lời gọi này rằng provider đã mặc định serialize mọi trường theo schema JSON.

Đối tượng `Logger` phải đến từ SLF4J API, và runtime cần một provider tương thích. Trong môi trường dùng Logback/Log4j Core, chọn JSON encoder/layout theo phiên bản và kiểm tra output thực tế.

### Logback

Trong Logback, level thường xuất phát từ event `ILoggingEvent` của Logback classic, do API/provider xử lý. Với JSON encoder phù hợp, có thể ánh xạ nó thành key `level`:

```json
{"level":"WARN","logger":"com.example.InventoryService","message":"Retry scheduled"}
```

Đây là **output minh họa**, không phải giá trị mặc định cố định cho mọi phiên bản Logback. Một số encoder chọn key `level`, `level_value`, `severity` hoặc thêm metadata khác; cần kiểm tra schema. **`level_value`** (nếu có) là số nội bộ của backend, không tự đồng nhất với OpenTelemetry `SeverityNumber`.

Với Spring Boot có backend Logback mặc định, chính sách level có thể được điều chỉnh qua `logging.level.root`, `logging.level.com.example` và cơ chế cấu hình của Boot; nhưng **bật JSON output** cần encoder/layout/integration được phiên bản framework hỗ trợ. File `logback-spring.xml` giúp cấu hình Logback với Spring extensions, không tự bảo đảm JSON format nếu chưa dùng encoder tương ứng.

### Log4j 2

Log4j 2 có `Log4j API`, Log4j Core và các layout/encoder cho JSON theo phiên bản. Trường level thường lấy từ **`LogEvent.getLevel()`** hoặc tương đương của backend; custom levels có thể tồn tại:

```json
{"level":"ERROR","logger":"com.example.PaymentService","message":"Gateway timeout"}
```

Đây cũng là JSON minh họa. Nếu dùng JSON Template Layout, cần cấu hình field resolver, tên key và vị trí của các trường theo schema; không mặc định mọi Log4j layout đều phát `level` dạng uppercase string. Đừng mang `<encoder>` của Logback sang XML Log4j 2 hoặc nhầm `log4j-to-slf4j` với provider `log4j-slf4j2-impl`.

**Nguyên tắc:** Level phải được lấy từ **metadata của log event**, không phân tích từ text message bằng regex, và serializer phải xuất đúng field/type mà collector đã thỏa thuận.

## 8. Cách lọc theo field `level` trong JSON Lines

Một cách triển khai phổ biến là **mỗi log event = một JSON object trên một dòng** (JSON Lines/NDJSON). Khi đó có thể dùng JSON parser thay vì tìm chuỗi `ERROR` trên toàn bộ message.

Với công cụ `jq` (phải được cài riêng, không nằm trong JDK) và file `app.jsonl` gồm một JSON object mỗi dòng:

```bash
jq -c 'select(.level == "ERROR")' app.jsonl
```

Lệnh lọc những object có field `level` đúng bằng string `ERROR` (phân biệt chữ hoa/chữ thường). Nó không chọn record `INFO` chỉ vì message chứa từ ERROR. Đếm các record theo level:

```bash
jq -r '.level // "UNKNOWN"' app.jsonl | sort | uniq -c
```

Lệnh này là **công cụ minh họa trên môi trường Unix-like**, không phải Java code. Nó giả định mỗi dòng là JSON hợp lệ và `.level` là string hoặc null; nếu giá trị là số/object, bản tổng hợp cần kiểm tra schema. Đối với hệ logging nhiều triệu events, truy vấn bằng log storage/collector có index đúng field thường hiệu quả hơn việc tải toàn bộ file qua terminal.

### Lọc trong ứng dụng Java bằng parser JSON

Nếu một service cần nhận JSON log từ hệ thống khác, có thể dùng Jackson (dependency ngoài JDK), một parser JSON phù hợp và validation cho schema. Không tự `split(",")` hoặc dùng regex chỉ để đọc JSON:

```json
{"level":"INFO","message":"ERROR was retried, then recovered"}
```

Tách chuỗi theo dấu phẩy hoặc tìm literal `ERROR` trên toàn dòng có thể đếm nhầm hoặc phá trường có dấu phẩy trong message. **Parser JSON** phải xác định level theo key và kiểu đúng; collector nên xử lý record không hợp lệ, thiếu key hoặc sai schema mà không làm cả pipeline thất bại.

### Kết quả phụ thuộc việc index field

Nếu dashboard không tìm được event `ERROR`, cần xác định:

1. Logger có thật sự phát event ở mức ERROR không?
2. Backend/provider có lọc event trước khi encoder không?
3. Encoder có xuất `level` dạng string không?
4. Collector có rename/drop/map field `level` sang nơi khác như `log.level` hay `SeverityText` không?
5. Storage có index/mapping đúng kiểu keyword/string không?
6. Dashboard/query có dùng field name và điều kiện case-sensitive chính xác không?
7. Có nhầm **event time** và ingestion time dẫn đến chọn sai khoảng thời gian không?

Đừng tăng retention rồi kỳ vọng tìm được event đã bị filter trước khi ghi; cũng đừng tự sửa message chỉ để parser nhận đúng level.

## 9. Chọn level theo tình huống thực tế

Giả sử ứng dụng ghi JSON cho một luồng xử lý đơn hàng:

```json
{"level":"INFO","event":"request_received","requestId":"req-17","route":"/orders/{id}"}
{"level":"DEBUG","event":"discount_rule_applied","requestId":"req-17","rule":"seasonal"}
{"level":"WARN","event":"inventory_retry","requestId":"req-17","attempt":1}
{"level":"INFO","event":"order_completed","requestId":"req-17","durationMs":128}
```

Đây là **một kịch bản minh họa**; trong một môi trường production với threshold INFO, event DEBUG có thể không xuất hiện. Nếu retry thành công, không nên tự gắn `ERROR` cho toàn bộ request chỉ vì từng có một bước retry. Ngược lại, khi retry hết giới hạn và request thất bại cuối cùng, hệ thống có thể ghi một event `ERROR` kèm error code, dependency và Throwable.

Một số quy tắc đánh giá:

- **`TRACE`/`DEBUG`:** chỉ lưu điều gì có ích cho điều tra; không log mọi tham số, body, mật khẩu hoặc token.
- **`INFO`:** các mốc vận hành đáng quan tâm; tránh tạo một INFO cho mỗi thao tác quá nhỏ nếu traffic lớn.
- **`WARN`:** sự kiện cần để ý nhưng ứng dụng vẫn tiếp tục hoặc đang có cơ chế phục hồi; retry ngắn hạn không nhất thiết là lỗi cuối.
- **`ERROR`:** thao tác thất bại hoặc vấn đề ngoài dự kiến cần điều tra; giữ `Throwable` và `errorCode` khi phù hợp.
- **`FATAL`:** chỉ dùng khi logging framework và quy ước tổ chức hỗ trợ mức này; không tự coi `FATAL` có nghĩa JVM chắc chắn thoát.
- **Audit/security events:** có thể có chính sách riêng về ghi đủ, retention và cảnh báo; đừng dùng sampling/filter theo level một cách vô ý khiến mất bằng chứng cần giữ.

Level thể hiện **mức độ của event**, không trực tiếp xác định người chịu trách nhiệm, mức độ ưu tiên của ticket hoặc sự cố toàn hệ thống. Những quyết định alert nên kết hợp errorCode, rate, service, route, impacted users và SLO, thay vì chỉ so `level="ERROR"`.

## 10. Hạn chế cardinality, field pollution và dữ liệu không tin cậy

`level` nên thuộc một **tập giá trị nhỏ, ổn định**. Những cách làm không nên áp dụng:

```json
{"level":"ERROR-request-92742"}
```

```json
{"level":"Failed for customer 123"}
```

Tạo một giá trị level theo request/user làm tăng cardinality, khó nhóm/tổng hợp, và trộn dữ liệu nghiệp vụ vào metadata kỹ thuật. Với structured logging:

```json
{"level":"ERROR","event":"checkout_failed","requestId":"req-17","errorCode":"UPSTREAM_TIMEOUT"}
```

Đây là cách tách thông tin dễ kiểm soát hơn. Tuy nhiên, `requestId` hay các field khác vẫn có thể là dữ liệu cần phân quyền và retention phù hợp.

### Log injection và JSON escaping

Nếu input chứa ký tự xuống dòng hoặc nháy kép, encoder phải escape đúng:

```json
{"level":"WARN","message":"client sent: \"bad\"\nvalidation failed"}
```

Dòng trên là **một object JSON**, trong đó `\\n` là ký tự backslash + n trong văn bản JSON chứ không phải một newline vật lý. Nếu tự ghép JSON với chuỗi nhập từ người dùng mà không escape, có thể gây JSON không hợp lệ, tách record hoặc cố gắng giả mạo field `level`.

Không lấy mức từ một trường do client cung cấp như `X-Log-Level: ERROR` để tin rằng sự kiện là ERROR. Mức độ nghiêm trọng phải do **ứng dụng/hệ observability có quyền** đặt theo chính sách. Không cho user tùy ý thay đổi logger configuration hoặc chọn level gây spam.

Không ghi token, cookie phiên, mật khẩu, header `Authorization`, payload cá nhân nhạy cảm. JSON serializer chỉ giải quyết encoding, **không giải quyết redaction hoặc quyền truy cập**.

## 11. Migration từ text logging sang JSON logging

Khi chuyển một hệ Java từ text sang structured JSON, cần có kế hoạch cho field `level` để dashboard cũ không hỏng.

**Bước 1 — kiểm kê nguồn:** xác định ứng dụng đang dùng JUL, SLF4J, Logback, Log4j 2 và bridge nào. Level từ backend nào là nguồn sự thật của event?

**Bước 2 — định nghĩa schema:** chọn `level` uppercase string hoặc quy ước field theo ECS/OTel. Nếu đổi tên `severity`, `severity_text`, `log.level`, phải ghi rõ mapping.

**Bước 3 — quyết định giá trị gốc:** có giữ `original_level` không? Ví dụ JUL `WARNING` được chuẩn hóa thành `WARN`. Với custom `Level`, chọn policy thay vì ép thành `ERROR` mà không biết nghĩa.

**Bước 4 — cấu hình serializer:** formatter/encoder phải lấy `Level` từ event; ghi **mỗi JSON object trên một dòng** nếu collector nhận JSON Lines, và giữ Throwable/stack trace trong dữ liệu có cấu trúc.

**Bước 5 — cấu hình collector/index:** chọn đúng field, đúng type. Khi có old/new schema song song, tránh để cùng key lúc là string, lúc là number trong một index.

**Bước 6 — kiểm thử end-to-end:** phát INFO, WARN, ERROR; một DEBUG được bật và một DEBUG bị tắt; xác minh event, type, casing, số lượng, timestamp và index.

**Bước 7 — rà cảnh báo và retention:** alert không nên phụ thuộc vào regex text khi đã có field; xem lại error rate, dropped events và ảnh hưởng cardinality trước/sau migration.

Đừng chỉ đổi formatter rồi coi việc chuyển sang JSON đã hoàn tất. **Contract phải được kiểm tra ở đầu ra thực tế của collector và dashboard**, đặc biệt khi nhiều ngôn ngữ/libraries cùng gửi log.

## 12. Những lỗi thường gặp với field `level`

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Có nơi ghi `WARN`, nơi ghi `WARNING` | JUL và SLF4J không dùng cùng tên | Chuẩn hóa giá trị, giữ mức gốc nếu cần |
| Lúc `level` là string, lúc là number | Schema/encoder không thống nhất | Chọn type; mapping số riêng, tránh type conflict |
| DEBUG không xuất hiện dù JSON encoder có field `level` | Backend filter sự kiện từ trước | Kiểm tra logger threshold, handler/appender filter |
| Event INFO có message chứa ERROR bị đếm sai | Dashboard tìm text thay vì JSON field | Query chính xác theo `level` hoặc `log.level` |
| Collector hiển thị `severity_text` mà không có `level` | Mapping OTel đã đổi tên field | Kiểm tra mapping/schema của pipeline |
| `level=1000` bị coi là ERROR chuẩn | Nhầm JUL intValue với SeverityNumber | Áp mapping chuẩn, không dùng nguyên số của JUL |
| `FATAL` không được framework hỗ trợ | API nguồn không có FATAL | Dùng mức được hỗ trợ hoặc mapping có chính sách |
| `original_level` không giống `level` | Có chuẩn hóa từ WARNING → WARN | Phân biệt tên raw và normalized; đây có thể là đúng |
| Một exception bị ghi nhiều ERROR | Các tầng cùng log rồi rethrow | Quy định điểm ghi lỗi đầy đủ, giữ cause và correlation |
| Không tìm được JSON trong index | Backend xuất text hoặc collector parse hỏng | Xác nhận decoder/schema từ output gốc |
| Stack trace biến thành nhiều event | Encoder text multiline/collector parse theo dòng | Compact JSON, escape newline hoặc cấu hình multiline |
| Sự kiện bị thiếu khi traffic cao | Rate limiting, async queue drop, ingest quota | Theo dõi drop metrics và chính sách queue |
| Custom level biến thành `ERROR` không có căn cứ | Normalizer có fallback quá rộng | Giữ giá trị gốc hoặc báo unmapped theo policy |
| JSON có key `level` hai lần | Ghép thủ công/merge object không kiểm soát | Dùng serializer/schema validation, tránh duplicate keys |
| Severity tăng nhưng alert không chạy | Query sai field/casing, sampling hoặc routing | Kiểm tra pipeline, threshold và alert rule |
| Thông tin nhạy cảm xuất hiện trong JSON | Cho toàn bộ object/request vào encoder | Allowlist/redaction và retention phù hợp |

**Lưu ý về duplicate keys:** JSON object chứa hai key `level` khác nhau có thể được các parser xử lý không thống nhất; tránh phát output kiểu `{"level":"INFO","level":"ERROR"}`. Field severity cần **một nguồn sự thật** để truy vấn và cảnh báo không mơ hồ.

## 13. Checklist kiểm chứng field `level` trước production

1. **Tên field:** `level` hay `log.level`/`SeverityText`? Contract và pipeline mapping đã rõ chưa?
2. **Type:** JSON string hay numeric severity được chuẩn hóa theo một model cụ thể?
3. **Giá trị hợp lệ:** `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` (nếu có) có casing thống nhất?
4. **Nguồn level:** giá trị lấy từ event metadata của backend, không regex từ message hoặc header client?
5. **Mapping API:** JUL `WARNING`/`SEVERE`, SLF4J `WARN`/`ERROR`, Log4j custom levels được xử lý theo policy?
6. **Giá trị gốc:** nếu chuẩn hóa, có giữ `original_level` hoặc `SeverityText` đúng ngữ nghĩa khi cần?
7. **Filtering:** thử level bị tắt và level được bật; không nhầm việc có field với sự tồn tại của event?
8. **Một event/một record:** JSON encoder escape newline, quotes, backslash, Throwable đúng chuẩn?
9. **Dữ liệu nhạy cảm:** message, MDC, HTTP fields được lọc; không cho input người dùng ghi đè `level`?
10. **Collector/storage:** index đúng field/type, các dashboards và alerts không bị thay đổi ngoài ý muốn?
11. **Quan sát chất lượng:** thống kê level counts, log volume, drop metrics, tỷ lệ field null/unmapped và mức độ duplicate?
12. **Schema migration:** có version, tài liệu mapping, test với các backend/language khác?
13. **Vận hành:** ERROR không tự đồng nghĩa sự cố nghiêm trọng toàn hệ thống; alert nên gắn với tín hiệu nghiệp vụ, SLO và tỷ lệ lỗi.

**Kết luận:** Field `level` trong JSON logging là **mức nghiêm trọng của từng log event ở dạng dữ liệu có cấu trúc**. Chọn một kiểu và tập giá trị ổn định, ánh xạ cẩn thận từ logging API nguồn, giữ nguyên raw severity khi có nhu cầu, và không nhầm nó với threshold của logger hay giá trị `SeverityNumber` thuộc một chuẩn khác. Khi backend, encoder và collector cùng tôn trọng contract, việc tìm kiếm, đếm và cảnh báo theo level sẽ chính xác hơn so với phân tích chuỗi text tự do.

## Tài liệu tham khảo

- Oracle Java 17 — `LogRecord`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
- Oracle Java 17 — `java.util.logging.Level`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html
- OpenTelemetry — Logs Data Model (SeverityText/SeverityNumber): https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Elastic — ECS Log Fields (log.level): https://www.elastic.co/docs/reference/ecs/ecs-log
- SLF4J Manual: https://www.slf4j.org/manual.html
- Logback Architecture: https://logback.qos.ch/manual/architecture.html
- Apache Log4j 2 — Log levels: https://logging.apache.org/log4j/2.x/manual/customloglevels.html
