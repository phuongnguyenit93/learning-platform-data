# Field message trong JSON Logging của Java

## 1. Field `message` là gì?

Trong **JSON logging**, một log event thường được biểu diễn thành một JSON object. Trường **`message`** (thường là một chuỗi) mang **lời mô tả dễ đọc của sự kiện**: điều gì vừa xảy ra, thao tác nào thành công, hoặc dấu hiệu lỗi nào cần chú ý. Nó giúp người đọc hiểu nhanh ngữ cảnh ngay cả khi chưa biết toàn bộ schema.

Ví dụ:

```json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","service":"order-service","event":"ORDER_ACCEPTED","orderId":"O-17","message":"Order accepted"}
```

Trong event này:

- `timestamp` là thời điểm sự kiện xảy ra, dùng UTC rõ ràng.
- `level` là mức log; ví dụ INFO, WARN, ERROR ở Log4j/Logback, hoặc INFO, WARNING, SEVERE ở JUL.
- `service` cho biết dịch vụ phát event.
- `event` là **mã sự kiện ổn định** cho truy vấn, dashboard và cảnh báo.
- `orderId` là **thuộc tính nghiệp vụ riêng** để lọc sự kiện.
- `message` là **câu mô tả**; có thể được viết lại để rõ hơn mà không nhất thiết thay đổi mã sự kiện.

**Field message không phải toàn bộ log event.** Nó khác với các trường metadata, context, exception và business attributes. Cách dùng tốt là cho người vận hành đọc được ngay ý nghĩa sự kiện, đồng thời giữ dữ liệu cần lọc/tổng hợp trong các field riêng.

### Tại sao dùng JSON thay vì chỉ một dòng văn bản?

Dòng text như:

```text
2026-11-09 WARN Order O-17 failed after 3000ms
```

đọc được nhưng khó phân tích tự động một cách chắc chắn nếu vị trí từ thay đổi. JSON có tên trường rõ ràng:

```json
{"timestamp":"2026-11-09T10:15:30Z","level":"WARN","event":"ORDER_TIMEOUT","orderId":"O-17","elapsedMs":3000,"message":"Order processing timed out"}
```

Lúc này, collector có thể đọc `elapsedMs` như number, `event` như string và không cần đoán `3000ms` từ một câu. **Việc log là JSON chỉ tạo điều kiện để có dữ liệu cấu trúc; một message dài vẫn không tự biến mọi thông tin bên trong nó thành field riêng.**

## 2. Vai trò và nội dung nên có của `message`

Một thông điệp tốt phải nói rõ **sự kiện thực tế đã xảy ra** ở mức độ phù hợp với level, không khẳng định điều chưa được kiểm chứng. Một số ví dụ:

| Tình huống | Message nên dùng | Vì sao |
| --- | --- | --- |
| Tạo đơn hàng thành công | `"Order accepted"` | Trạng thái hoàn tất rõ, không cần nhét order ID vào câu. |
| Gọi backend quá hạn | `"Payment gateway request timed out"` | Mô tả sự kiện, không tự suy ra giao dịch đã thất bại vĩnh viễn. |
| Chuyển sang nhánh dự phòng | `"Fallback provider selected"` | Mô tả hành động cụ thể. |
| Không tìm thấy cấu hình tùy chọn | `"Optional configuration missing; using default"` | Có hậu quả vận hành rõ. |
| Tác vụ bị từ chối do validation | `"Request validation failed"` | Không tiết lộ toàn bộ dữ liệu người dùng. |
| Kết nối bị đóng bất ngờ | `"Upstream connection closed unexpectedly"` | Tránh từ mơ hồ như “something wrong”. |

Một message nên:

1. **Ngắn nhưng đủ ý**; thường là một câu diễn đạt sự kiện, không phải bản dump của entity/request.
2. **Có chủ ngữ hoặc ngữ cảnh hợp lý** nếu mã event chưa đủ.
3. **Mô tả điều đã xảy ra**, không hứa retry đã thành công khi mới bắt đầu retry.
4. **Tránh dữ liệu bí mật**, message có thể được gửi đến nhiều sink và nhiều nhóm người xem.
5. **Không chứa quá nhiều biến động không cần thiết** nếu mục tiêu là nhóm/tổng hợp log.
6. **Không thay thế event code ổn định**, đặc biệt khi muốn tạo dashboard, alert theo loại sự kiện.

Ví dụ tốt cho một event:

```json
{"level":"WARN","event":"PAYMENT_GATEWAY_TIMEOUT","gateway":"primary","elapsedMs":3000,"retryable":true,"message":"Payment gateway did not respond before deadline"}
```

Không cần biến message thành:

```text
Payment gateway primary timed out after 3000ms, retryable=true, requestId=..., orderId=..., ...
```

khi các thuộc tính đó đã nằm trong field riêng. Lặp toàn bộ dữ liệu vào message làm log dài, khó che thông tin nhạy cảm và tăng chi phí lưu trữ.

## 3. Kiểu dữ liệu của field message

### 3.1. Ưu tiên chuỗi JSON ổn định

Với schema thông thường, quy ước:

```json
{"message":"Order accepted"}
```

tức **`message` là string**. JSON hỗ trợ object, array, number, boolean và null, nhưng **một trường nên giữ cùng kiểu dữ liệu** giữa các sự kiện nếu hệ lưu trữ lập chỉ mục theo schema, đặc biệt khi backend có mapping/typing cố định.

Không nên phát ngẫu nhiên cả hai dạng:

```json
{"message":"Order accepted"}
```

và:

```json
{"message":{"action":"accept","orderId":"O-17"}}
```

Dòng thứ hai có thể là JSON hợp lệ, nhưng một bộ lập chỉ mục đã định nghĩa `message` kiểu string có thể gặp **mapping conflict** khi nhận object. Đây là lỗi schema chứ không phải lỗi parser JSON.

**Khuyến nghị:** giữ `message` là string cho sự kiện thông thường; nếu cần metadata dạng object, đưa nó sang một nhánh riêng như `attributes`, `context` hoặc tên field phù hợp với schema đã thống nhất.

### 3.2. Phân biệt absent, null và empty string

Ba trường hợp không tương đương:

```json
{"event":"ORDER_ACCEPTED"}
```

```json
{"event":"ORDER_ACCEPTED","message":null}
```

```json
{"event":"ORDER_ACCEPTED","message":""}
```

- **Absent:** không có trường `message` (có thể do encoder bỏ qua hoặc producer không cung cấp).
- **Null:** field có mặt, nhưng không có giá trị string.
- **Empty string:** có một string với độ dài bằng 0.

Một số hệ ingest coi các giá trị trên khác nhau. Khi ứng dụng yêu cầu message luôn có mặt, nên thiết kế fallback có chủ đích, chẳng hạn một câu an toàn dựa trên event code. **Không tự gán “null” hay “unknown” nếu nó che mất lỗi producer hoặc làm sai ý nghĩa sự kiện.**

### 3.3. Unicode và ngôn ngữ

JSON hỗ trợ Unicode. Message tiếng Việt hoàn toàn hợp lệ:

```json
{"level":"WARN","message":"Kết nối đến dịch vụ thanh toán bị gián đoạn"}
```

Ưu tiên encoding **UTF-8** xuyên suốt ứng dụng, stdout/file, collector và storage. Nếu hệ thống dùng tên event code tiếng Anh ổn định để phân tích, `message` vẫn có thể là tiếng Việt tùy yêu cầu tổ chức; dashboard không nên dùng message tự do làm định danh duy nhất.

## 4. Message gốc, message template và formatted message

Đây là phần dễ gây nhầm nhất khi dùng các logging API của Java.

### Message viết trực tiếp

```java
// Ví dụ khi logger là Logger của SLF4J hoặc Log4j 2.
logger.info("Order accepted");
```

Message đầu vào là chuỗi cố định. Encoder JSON có thể đưa nó thành:

```json
{"message":"Order accepted"}
```

### Message theo template với tham số

Trong SLF4J và Log4j 2 thường thấy:

```java
logger.info("Order {} accepted", orderId);
```

Ở đây:

- **Template:** `Order {} accepted`.
- **Argument:** giá trị `orderId` tại thời điểm gọi.
- **Formatted message:** ví dụ `Order O-17 accepted` nếu `orderId="O-17"`.

Tùy framework và layout, JSON field `message` thường được cấu hình để chứa **formatted message**. Nhưng không được coi việc log có template `{}` là đảm bảo producer tự tạo riêng một JSON field `orderId`. Nếu cần tìm theo mã đơn hàng, hãy ghi `orderId` qua một **structured attribute/MDC** được encoder hỗ trợ.

Với **JUL (java.util.logging)**, phương thức `Formatter.formatMessage(LogRecord)` có thể áp dụng `java.text.MessageFormat` cho mẫu như:

```java
// Mẫu của JUL, không phải cú pháp placeholder SLF4J.
logger.log(java.util.logging.Level.INFO,
           "Order {0} accepted", "O-17");
```

Nếu formatter gọi `record.getMessage()` mà không `formatMessage(record)`, nó có thể xuất nguyên `Order {0} accepted` thay vì nội dung đã thay tham số. **Phải hiểu quy ước placeholder của đúng logging API**; JUL dùng `{0}`, SLF4J dùng `{}`, không tráo hai kiểu.

### Không tự nối dữ liệu động vào message khi chưa cần

```java
// Tránh ghép chuỗi không cần thiết trước khi backend lọc level.
logger.debug("Full order=" + order.toString());

// Thường tốt hơn khi chỉ cần ID được phép log.
logger.debug("Order id={}", orderId);
```

Phép nối chuỗi trong biểu thức `+` có thể xảy ra **trước khi** logger quyết định không ghi DEBUG, và một `toString()` tùy ý có thể tiết lộ dữ liệu hoặc tốn chi phí. Parameterized logging thường tránh tạo chuỗi cuối quá sớm, nhưng **các đối số Java được tính trước lời gọi**; nếu lập tham số bằng `expensive()` thì hàm đó vẫn chạy trừ khi dùng cơ chế lazy/supplier hoặc guard phù hợp.

## 5. Message khác field cấu trúc và mã sự kiện

Một event hữu ích thường có cả:

```json
{
  "timestamp":"2026-11-09T10:15:30Z",
  "level":"INFO",
  "event":"ORDER_ACCEPTED",
  "service":"order-service",
  "orderId":"O-17",
  "message":"Order accepted"
}
```

Đây là **một JSON object được trình bày nhiều dòng cho dễ đọc**, không phải ví dụ JSON Lines dùng trực tiếp cho collector. Trong JSON Lines, nó cần được serialize thành một dòng vật lý.

Tại sao không chỉ ghi message?

- **Cảnh báo:** tạo alert theo mã `ORDER_ACCEPTED`/`PAYMENT_TIMEOUT` ít phụ thuộc chuyện sửa câu chữ.
- **Lọc:** tìm `orderId="O-17"` chính xác, thay vì tìm substring trong message.
- **Aggregation:** đếm theo `event` hoặc `level`, tránh mỗi order ID tạo một nhóm message riêng.
- **Truy vết:** `traceId`, `spanId`, `correlationId` có thể liên kết event giữa các service.
- **Hiệu năng:** các field đã kiểu hóa như `elapsedMs` (number) hỗ trợ tính toán trực tiếp.
- **Bảo mật:** kiểm soát thuộc tính được phép log dễ hơn việc đưa object tùy ý vào chuỗi tự do.

Không lấy `message` làm metric label nếu nó chứa ID/URL/path khác nhau theo từng request: điều đó tạo **high cardinality**. Thay bằng nhãn event code ổn định và chỉ lưu message như dữ liệu log.

## 6. JSON escaping: bảo toàn ý nghĩa của message

Vì `message` là một chuỗi nằm trong JSON, nội dung cần được **encode theo quy tắc JSON string**. Không viết:

```java
// SAI: có thể tạo JSON không hợp lệ và gây log injection.
String json = "{\"message\":\"" + message + "\"}";
```

Giả sử message chứa dấu nháy kép:

```text
Invalid field "name"
```

Nếu nối trực tiếp, kết quả sai:

```text
{"message":"Invalid field "name""}
```

Một encoder JSON đúng sẽ viết:

```json
{"message":"Invalid field \"name\""}
```

### Các ký tự cần escape

| Dữ liệu trong message | Chuỗi escape trong JSON | Tại sao |
| --- | --- | --- |
| Dấu nháy kép `"` | `\"` | Không kết thúc string ngoài ý muốn. |
| Backslash `\` | `\\` | Không bị hiểu là mở đầu escape. |
| Newline (LF) | `\n` | Không tạo dòng vật lý mới giữa record. |
| Carriage return (CR) | `\r` | Không làm ảnh hưởng ranh giới record/display. |
| Tab | `\t` | Giữ nội dung mà không tạo separator khó kiểm soát. |
| Backspace/form feed | `\b` / `\f` | Escape các ký tự điều khiển tương ứng. |
| Control character khác U+0000–U+001F | `\u00XX` | JSON string không chứa control character thô. |

Dấu `/` thường không bắt buộc phải escape. Ký tự Unicode hợp lệ có thể được ghi trực tiếp bằng UTF-8 hoặc dưới dạng `\uXXXX` tùy serializer. Đặc biệt, cần xử lý **surrogate không hợp lệ** khi chuỗi Java chứa cặp UTF-16 bị hỏng; thư viện JSON được bảo trì thường có chính sách xử lý hoặc từ chối dữ liệu không hợp lệ.

### Newline, JSON Lines và log forging

Nếu message gốc là:

```text
Payment attempt failed
{"level":"INFO","message":"Everything succeeded"}
```

thì **không thể** cho ký tự newline gốc chui vào một JSON string mà không escape. Dạng đúng trên một dòng JSON Lines:

```json
{"level":"ERROR","message":"Payment attempt failed\n{\"level\":\"INFO\",\"message\":\"Everything succeeded\"}"}
```

Đây vẫn là **một sự kiện ERROR**, không phải hai event độc lập. Với collector dùng NDJSON/JSON Lines, mỗi event được serialize thành một **JSON object trên một dòng**, kết thúc bằng một newline *ngoài* JSON string.

**Không trông chờ PatternLayout thuần văn bản tự trở thành JSON encoder**. Hãy dùng JsonTemplateLayout, JSON encoder hoặc thư viện JSON serializer đúng framework. Tự viết escape chỉ nên dùng cho ví dụ học tập có kiểm thử rõ ràng.

## 7. Ví dụ Java 17 chạy độc lập: JUL Formatter xuất message thành JSON Lines

Chương trình sau dùng **JDK 17 thuần**, không cần Maven, Log4j 2 hay Jackson. Nó minh họa đường đi:

```text
Logger.log(LogRecord)
    -> JUL StreamHandler
    -> JsonLineFormatter.format(record)
    -> encode string JSON
    -> stdout: mỗi event một JSON object trên một dòng
```

Các tiêu chí của ví dụ:

1. Một event gồm `timestamp`, `level`, `logger`, `message` với **thứ tự field cố định**.
2. Trường `message` lấy từ **`formatMessage(record)`** để minh họa thay tham số `{0}` của JUL.
3. Dấu nháy, backslash, newline và control characters được escape.
4. Các thời điểm được đặt cố định để stdout **tất định**.
5. Logger không truyền event tới parent handlers, tránh log trùng ở stderr.
6. StreamHandler được flush sau mỗi event trong chương trình demo. Chỉ tạo output qua một thread.

### 7.1. Tệp `JsonMessageDemo.java`

```java
import java.time.Instant;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class JsonMessageDemo {

    private JsonMessageDemo() {
    }

    public static void main(String[] args) throws Exception {
        Logger logger = Logger.getLogger("demo.json.message");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        for (Handler previous : logger.getHandlers()) {
            logger.removeHandler(previous);
        }

        Handler output = new StreamHandler(System.out,
                                          new JsonLineFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        output.setEncoding("UTF-8");
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        emit(logger, Level.INFO,
             "2026-11-09T10:15:30Z",
             "Order {0} accepted", "O-17");

        emit(logger, Level.WARNING,
             "2026-11-09T10:15:31Z",
             "Invalid field \"name\"\nnext=C:\\logs");

        emit(logger, Level.SEVERE,
             "2026-11-09T10:15:32Z",
             "");

        output.flush();
        logger.removeHandler(output);
        // Không close output: StreamHandler.close() có thể
        // đóng luôn System.out là tài nguyên chia sẻ.
    }

    private static void emit(Logger logger, Level level,
                             String when, String template,
                             Object... arguments) {
        LogRecord record = new LogRecord(level, template);
        record.setLoggerName(logger.getName());
        record.setInstant(Instant.parse(when));
        record.setParameters(arguments);
        logger.log(record);
    }

    private static final class JsonLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return "{"
                 + "\"timestamp\":" + json(record.getInstant().toString())
                 + ",\"level\":" + json(record.getLevel().getName())
                 + ",\"logger\":" + json(record.getLoggerName())
                 + ",\"message\":" + json(formatMessage(record))
                 + "}\n";
        }

        private static String json(String value) {
            if (value == null) {
                return "null";
            }

            StringBuilder out = new StringBuilder("\"");

            for (int i = 0; i < value.length(); i++) {
                char ch = value.charAt(i);

                switch (ch) {
                    case '"'  -> out.append("\\\"");
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
                        } else if (Character.isHighSurrogate(ch)) {
                            if (i + 1 < value.length()
                                    && Character.isLowSurrogate(
                                            value.charAt(i + 1))) {
                                out.append(ch)
                                   .append(value.charAt(++i));
                            } else {
                                out.append("\\uFFFD");
                            }
                        } else if (Character.isLowSurrogate(ch)) {
                            out.append("\\uFFFD");
                        } else {
                            out.append(ch);
                        }
                    }
                }
            }
            return out.append('"').toString();
        }
    }
}
```

### 7.2. Biên dịch và chạy

Lưu tệp đúng tên `JsonMessageDemo.java`, rồi dùng Java 17 trở lên:

```bash
javac -encoding UTF-8 JsonMessageDemo.java
java JsonMessageDemo
```

**Stdout chính xác của chương trình** (mỗi dòng bên dưới là **một JSON object hoàn chỉnh**):

```json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","logger":"demo.json.message","message":"Order O-17 accepted"}
{"timestamp":"2026-11-09T10:15:31Z","level":"WARNING","logger":"demo.json.message","message":"Invalid field \"name\"\nnext=C:\\logs"}
{"timestamp":"2026-11-09T10:15:32Z","level":"SEVERE","logger":"demo.json.message","message":""}
```

### 7.3. Vì sao đầu ra như vậy?

- **Dòng 1:** `formatMessage(record)` nhận mẫu JUL `Order {0} accepted` và tham số `O-17`, cho `Order O-17 accepted`.
- **Dòng 2:** chuỗi Java có **dấu nháy thật, newline thật và backslash thật**. Hàm `json(...)` thay chúng bằng escape JSON (`\"`, `\n`, `\\`). Vì vậy vẫn chỉ có **một dòng vật lý**.
- **Dòng 3:** message rỗng vẫn được biểu diễn hợp lệ thành `"message":""`; không bị nhầm thành `null` hay field vắng mặt.
- `Level.WARNING` và `Level.SEVERE` là tên mức **JUL**. Nếu sử dụng Log4j 2 hoặc SLF4J, tên thường là WARN/ERROR; không tự thay bằng các tên đó trong output của JUL.
- `logger.setUseParentHandlers(false)` ngăn logger cha in thêm bản ghi qua handler mặc định.
- `StreamHandler` flush sau `publish`, để các dòng xuất hiện trước khi chương trình dừng. Trong code demo không đóng `System.out` dùng chung.
- Timestamp dùng `Instant.parse` nên không thay đổi theo timezone máy.

**Ranh giới của demo:** đây là một formatter học tập, không phải JSON encoder được chứng nhận để triển khai production. Nó chưa có giới hạn kích thước, chính sách redaction, fallback cho message bất thường, stack trace structured, JSON schema registry, metrics, async backpressure hay collector. Khi sản xuất cần một serializer và encoder được bảo trì, test tương thích giữa các thành phần và schema của nền tảng log.

### 7.4. Bài tập kiểm thử bổ sung

Thử thêm một message:

```java
// Minh họa giá trị trong một lời gọi emit bổ sung:
"Line 1\r\nLine 2\tpath=C:\\temp"
```

Kỳ vọng JSON string có lần lượt các escape `\r\n`, `\t` và `\\` thay vì chứa control characters thô. Với ký tự Unicode tiếng Việt, test đọc lại bằng parser JSON đúng chuẩn UTF-8. Với cặp UTF-16 surrogate không hợp lệ, demo chọn xuất `\uFFFD` (Unicode replacement character) thay vì giữ một code unit không hợp lệ.

Một kiểm thử mạnh là **round-trip**: tạo message đầu vào → encode thành JSON → parser JSON đọc lại → message giải mã phải bằng input hợp lệ ban đầu. Ngoại lệ duy nhất trong demo: surrogate đơn lẻ bị chuyển sang replacement character theo chính sách đã nêu.

## 8. Field message trong Log4j 2 JSON Template Layout

Khi ứng dụng dùng **Apache Log4j 2**, JSON nên được tạo bằng một **Layout** phù hợp thay vì nối chuỗi bằng tay. Log4j 2 cung cấp **`JsonTemplateLayout`** có thể dùng resolver `message`.

Một event template minh họa đặt trong file `src/main/resources/message-event-template.json`:

```json
{
  "timestamp": {
    "$resolver": "timestamp",
    "pattern": {
      "format": "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
      "timeZone": "UTC"
    }
  },
  "level": {
    "$resolver": "level",
    "field": "name"
  },
  "logger": {
    "$resolver": "logger",
    "field": "name"
  },
  "message": {
    "$resolver": "message",
    "stringified": true
  }
}
```

Đoạn cấu hình trong `log4j2.xml`:

```xml
<Console name="JSON_CONSOLE" target="SYSTEM_OUT">
    <JsonTemplateLayout
        eventTemplateUri="classpath:message-event-template.json"/>
</Console>
```

Đây là **đoạn bên trong `<Appenders>`**, chưa phải file `log4j2.xml` độc lập; còn cần khai báo logger/AppenderRef và dependency Log4j 2 phù hợp. Để dùng `JsonTemplateLayout` cần module runtime:

```text
org.apache.logging.log4j:log4j-layout-template-json
```

quản lý phiên bản cùng các module Log4j 2 tương ứng, tốt nhất qua Log4j BOM hoặc dependency management của framework.

**Ý nghĩa của `"stringified": true`:** resolver `message` xuất nội dung dưới dạng **chuỗi JSON** thay vì giữ object/list khi event dùng loại Message có hỗ trợ dữ liệu cấu trúc. Điều này giúp duy trì kiểu của field `message` nhất quán trong các hệ index cứng.

Nếu bỏ `stringified: true`, một số kiểu `ObjectMessage`/`MapMessage` có thể được thể hiện thành JSON object thay vì string. Điều đó có thể hữu ích cho một schema có chủ đích, nhưng nếu field `message` lúc là string lúc là object, storage như Elasticsearch có thể gặp xung đột mapping. Cách chọn nên đến từ **schema của hệ thống nhận**, không phải từ giả định “object luôn tốt hơn”.

**Đừng nhầm resolver message với trường parameters:** Log4j 2 có cơ chế truy cập message parameters riêng, nhưng dùng resolver đó không đồng nghĩa đã có field `orderId` rõ nghĩa. Hãy dùng MDC/context map hoặc structured message với schema phù hợp khi cần tách thuộc tính, và để message vẫn là lời mô tả ngắn.

Với ứng dụng dùng **SLF4J → Log4j 2**, còn phải cấu hình đúng adapter/provider theo thế hệ SLF4J để các log thực sự tới Log4j backend. Không thể chỉ thêm `log4j-layout-template-json` rồi mặc nhiên thay được pipeline.

## 9. Field message trong SLF4J 2 và Logback

SLF4J là API facade: nó truyền lời gọi logging tới provider/backend. Trong SLF4J 2, một lời gọi:

```java
// Đoạn minh họa, logger là org.slf4j.Logger phiên bản 2.x.
logger.atInfo()
      .addKeyValue("orderId", "O-17")
      .addKeyValue("elapsedMs", 125)
      .log("Order processed");
```

có **hai loại dữ liệu**:

- **Message:** `Order processed`.
- **Key-value attributes:** `orderId="O-17"` và `elapsedMs=125`.

Một backend/encoder có thể giữ các cặp riêng biệt, nhưng **không phải mọi provider hoặc layout tự xuất chúng thành JSON object với tên field giống nhau**. Cần kiểm tra cấu hình thật của Logback/Log4j2/provider đang chạy. Thêm `addKeyValue(...)` không tự bảo đảm xuất được trường trong kho tìm kiếm.

Trong **Logback**, `PatternLayoutEncoder` vốn tạo **text**. Nếu pattern chỉ gồm `%msg%n`, một collector sẽ nhận câu message chứ không phải JSON object có field `message`; không nên cố tạo JSON bằng cách ghép literal `{"message":"%msg"}`, vì giá trị `%msg` có thể chứa dấu nháy hoặc newline.

Nếu dùng JSON encoder/layout của Logback, phải kiểm tra plugin/phiên bản phù hợp với SLF4J API, schema và yêu cầu lưu metadata/exception. Các thư viện encoder khác nhau có thể gọi field là `message`, `formattedMessage` hoặc cấu trúc khác. **Không giả định tên trường và cách escape là giống nhau giữa mọi encoder**.

## 10. Tách thông điệp khỏi exception

Một lỗi thường cần cả **message ngắn** và **thông tin ngoại lệ có cấu trúc**:

```json
{"timestamp":"2026-11-09T10:15:32Z","level":"ERROR","event":"ORDER_SUBMISSION_FAILED","orderId":"O-18","message":"Order submission failed","error":{"type":"java.net.SocketTimeoutException","message":"Read timed out"}}
```

Mục tiêu:

- `message` ở cấp top-level cho biết **sự kiện nghiệp vụ**.
- `error.type` cho biết loại exception; có thể dùng để nhóm nguyên nhân.
- `error.message` mô tả lỗi kỹ thuật, **phải kiểm soát nguy cơ chứa URL/token/input người dùng**.
- Stack trace có thể nằm ở trường khác như `stackTrace`, `error.stack_trace` hoặc một cấu trúc array theo schema.
- `orderId` nằm riêng để truy vấn thay vì chèn vào mọi message.

Trong API logging:

```java
// Minh họa trong catch (Exception ex) của ứng dụng:
logger.error("Order submission failed for id={}", orderId, ex);
```

Với API hỗ trợ signature này, chuyển `Throwable` thành tham số riêng giúp backend lấy stack trace đúng cách. Ngược lại, chỉ ghi:

```java
logger.error("Order submission failed: " + ex);
```

có thể chỉ giữ `ex.toString()`, không còn đầy đủ stack trace hoặc structured exception. **Tùy encoder**, stack trace có thể xuất thành text string, array, hoặc field khác; cần kiểm tra output thực tế.

**Không copy stack trace vào `message` nếu đã có trường exception riêng và không có yêu cầu rõ.** Nó làm message quá dài, có thể tạo newline và làm dashboard khó đọc. Nếu nền tảng ingest yêu cầu stack trace nằm trong message (một số integration đặc thù), đó phải là quy tắc schema có chủ đích, không áp dụng máy móc cho mọi hệ thống.

## 11. Thread Context / MDC và message

Khi ứng dụng phục vụ nhiều request, message nên kết hợp với **correlation metadata** được mang riêng.

Ví dụ:

```json
{"level":"INFO","traceId":"4bf92f3577b34da6a3ce929d0e0e4736","orderId":"O-17","message":"Order accepted"}
```

Với Log4j 2 có **ThreadContext**; với SLF4J/Logback có **MDC**. Chúng cho phép gắn metadata theo ngữ cảnh xử lý. Tuy nhiên, ở nhiều implementation context dựa vào thread-local; khi chạy qua executor, CompletableFuture hoặc reactive scheduler, context **không tự động lan truyền trong mọi tình huống**.

Những nguyên tắc:

1. Gắn trace/correlation ID một lần tại ranh giới request theo thiết kế tracing.
2. Truyền context đúng cách khi chuyển thread/async, không để thread pool giữ ID của request trước.
3. Dọn context khi rời scope xử lý, nhất là khi dùng thread pool.
4. Không đưa toàn bộ HTTP headers, request body hoặc cookie vào MDC.
5. Đảm bảo encoder xuất context dưới các field có tên hợp đồng thống nhất.
6. Nếu object có thể mutate, tạo snapshot gọn và an toàn ở thời điểm event được tạo.

Một log có message giống nhau ở hàng nghìn request vẫn có thể điều tra được nếu mỗi event có timestamp, trace ID và business ID thích hợp. **Giải pháp không phải chèn toàn bộ request vào `message`.**

## 12. Bảo mật: message là nơi dễ vô tình lộ dữ liệu

Field `message` thường bị xem như “chỉ là text”, nhưng chính vì vậy nhiều lập trình viên vô tình ghi:

- Toàn bộ URL chứa query token hoặc mã reset mật khẩu.
- HTTP Authorization header, session cookie hoặc refresh token.
- Mật khẩu, OTP, private key, thông tin thanh toán nhạy cảm.
- Dữ liệu cá nhân không cần thiết để điều tra.
- Nội dung raw payload lớn, không có giới hạn, chứa dữ liệu người dùng.
- Throwable message lồng các giá trị bí mật do thư viện bên thứ ba sinh ra.

Ví dụ không nên:

```java
logger.warn("Failed request: {}", request.toString());
```

vì `request.toString()` có thể chứa các trường không được phép lưu log. Thay bằng:

```java
logger.warn("Request validation failed: errorCode={}", safeErrorCode);
```

và thêm các field an toàn như event code, correlation ID, endpoint template hoặc status nếu cần.

**JSON escaping không phải redaction.** Một chuỗi có thể hoàn toàn hợp lệ về cú pháp JSON nhưng vẫn rò rỉ access token. Thực hiện allowlist/redaction ở nguồn, rồi áp dụng serializer JSON đúng chuẩn. Không xem việc xóa log theo retention sau 30 ngày là biện pháp bảo mật đủ.

### Log injection

Một attacker có thể gửi message chứa newline và chuỗi giả danh log ERROR/INFO. JSON Lines serializer đúng sẽ escape control characters và giữ tất cả trong **một JSON string**, nhưng vẫn cần xác minh collector không tách lại message thô trước khi parser.

### Giới hạn kích thước

Một message quá dài làm tăng bandwidth, allocation, chi phí lưu, độ trễ ingest và có thể bị cắt ở collector. Nếu cần truncate:

- Quy định giới hạn theo **ký tự Unicode, UTF-16 hay byte UTF-8**, không gọi chung là “max 1000 chars”.
- Truncate **giá trị trước khi serialize** hoặc dùng encoder có chiến lược an toàn; không cắt chuỗi JSON đã encode giữa dấu escape, surrogate hoặc UTF-8 multibyte.
- Nếu có truncation, cân nhắc field như `messageTruncated=true` để người điều tra biết nội dung không đầy đủ.
- Không lưu thêm bản message raw đầy đủ ở nơi khác trừ khi có quyền và retention thích hợp.

Không lấy `message` từ dữ liệu không đáng tin rồi dùng làm trường metric label. Nó gây cardinality cao và có thể chứa nội dung cá nhân.

## 13. Thiết kế schema: một message field nên có hợp đồng

Một hợp đồng tối thiểu cho JSON logging có thể ghi:

| Thuộc tính | Đề xuất |
| --- | --- |
| Tên field | `message`, viết thường thống nhất toàn hệ thống. |
| Kiểu | String UTF-8 hợp lệ khi serialize; xử lý null/missing theo policy. |
| Nội dung | Câu mô tả một event, không dump toàn bộ object. |
| Giá trị mặc định | Không ngầm bịa “success” khi thiếu message. |
| Escape | JSON serializer, kiểm tra quote/backslash/newline/Unicode. |
| Mã sự kiện | Field riêng `event` hoặc `event.code` theo schema. |
| Thuộc tính động | Field riêng như `orderId`, `elapsedMs`, `traceId`. |
| Exception | Field lỗi riêng hoặc cấu trúc do encoder hỗ trợ. |
| Giới hạn độ dài | Có policy và dấu hiệu khi cắt. |
| Bảo mật | Allowlist/redaction trước serialize, giới hạn quyền truy cập. |
| Kiểm thử | JSON parse thành công và `message` có kiểu string. |

**Tương thích schema:** khi đổi encoder, framework hoặc thêm structured `Message`, hãy kiểm tra xem `message` vẫn là string và có cùng semantic hay không. Đổi từ “formatted message” sang “template gốc” có thể làm nhiều dashboard hiển thị `Order {} accepted` thay vì câu thực tế, dù JSON vẫn hợp lệ.

Một số hệ thống có thể chọn giữ đồng thời:

```json
{"message":"Order O-17 accepted","messageTemplate":"Order {} accepted","orderId":"O-17"}
```

nếu encoder và chính sách bảo mật hỗ trợ. Nhưng **không tự viết messageTemplate vào output chỉ vì nó tồn tại trong lời gọi logging**; phải kiểm tra backend có cung cấp nó đáng tin và bảo toàn tham số theo schema định nghĩa hay không.

## 14. Cách kiểm tra field message khi triển khai

### Kiểm tra ở mức producer

- Lời gọi logger có thực sự xảy ra không?
- Level/filter có loại event trước khi đến appender/handler?
- Template có được format đúng theo JUL hay SLF4J/Log4j 2?
- Exception có đi qua tham số Throwable, không chỉ bị nối vào string?
- Message có field chứa token, PII hoặc dữ liệu không cần thiết?
- Message có thể null/rỗng không, và cần chính sách gì?

### Kiểm tra ở mức encoder

- JSON object có field `message` đúng tên, đúng kiểu hay không?
- Thử input có `"`, `\`, CR, LF, tab, Unicode và surrogate không hợp lệ.
- Tất cả các record có serialize một object mỗi dòng nếu dùng JSON Lines?
- Nếu dùng Log4j2 JsonTemplateLayout, `message` resolver có đặt `stringified=true` khi schema yêu cầu string?
- Nếu dùng Logback JSON encoder, provider/version có xuất đúng field và không bỏ structured attributes?
- Có giới hạn kích thước, JSON escaping và redaction theo yêu cầu?

### Kiểm tra ở mức sink/collector

- Stdout/stderr, file hoặc network có thực sự nhận record?
- Collector parser có đọc được tất cả JSON objects mà không cắt/hợp nhất sai?
- Hệ thống index `message` thành kiểu string và các field khác đúng mapping?
- Newline trong nội dung message có làm giả một record mới không?
- Có dữ liệu bị drop do async queue, quá kích thước hoặc lỗi backend?
- Sau khi ingest, có truy vấn tìm được message với trace/correlation ID?

**Không lấy “ứng dụng chạy không exception” làm bằng chứng JSON hợp lệ hoặc log đã tới kho.** Cần test một sự kiện có ID biết trước, đi hết pipeline tới storage.

## 15. Bảng test cho field message

| Test case | Dữ liệu đầu vào | Điều cần xác nhận |
| --- | --- | --- |
| Message bình thường | `Order accepted` | Output string đúng nguyên nội dung. |
| Template JUL | `Order {0} accepted` + `O-17` | Output đã format, không còn placeholder. |
| Template SLF4J | `Order {} accepted` + `O-17` | Backend dùng đúng format của SLF4J. |
| Dấu nháy kép | `Invalid field "name"` | JSON string có escape `\"`. |
| Backslash | `C:\logs` | JSON string có escape `\\`. |
| Newline | Text có LF/CR | Một event vẫn một dòng vật lý. |
| Tab/control char | Tab hoặc U+0000 | Escape đúng theo JSON grammar. |
| Tiếng Việt có dấu | `Đơn hàng đã được chấp nhận` | UTF-8 parse được, không mất dấu. |
| Message rỗng | `""` | Không bị tự coi là null. |
| Null/missing | null/không có field | Xử lý theo schema; khác empty string. |
| ObjectMessage | MapMessage hoặc custom Message | Không làm kiểu field đổi ngoài ý định. |
| Exception | Throwable có stack trace | Message và lỗi kỹ thuật tách rõ. |
| Dữ liệu nhạy cảm | Token/OTP trong object | Bị redaction/không xuất ở message. |
| Message rất dài | Hơn hạn mức collector | Có chính sách truncate/size rõ, JSON vẫn hợp lệ. |
| Async/multithreading | Nhiều requests với trace IDs | Không lẫn context, event đầy đủ theo policy. |
| End-to-end | Event code và ID cố định | Tìm được trong log storage, mapping đúng. |

Một kiểm thử round-trip quan trọng:

```text
originalMessage
    -> JSON serialize
    -> JSON parse
    -> parsed["message"]
    == originalMessage
```

Trong trường hợp chuỗi Unicode hợp lệ và không có truncation/redaction, message sau parse phải trùng message đã format trước serialize, kể cả dấu nháy, backslash và newline logic. Nếu có redaction/truncate, **phải định nghĩa lại giá trị kỳ vọng** và có metadata chính sách.

## 16. Những lỗi phổ biến cần tránh

1. **Cho rằng `message` chính là toàn bộ record.** JSON event còn timestamp, level, logger, context, attributes và exception.
2. **Lúc ghi string, lúc ghi object vào `message`.** Storage có schema cứng có thể bị mapping conflict.
3. **Tự ghép `{"message":"..."}` bằng nối chuỗi.** Dấu nháy và newline làm hỏng JSON/log injection.
4. **Đưa mọi biến động vào message, không tách field riêng.** Khó lọc, khó tổng hợp và dễ lộ dữ liệu.
5. **Dùng formatted message làm event code hoặc metric label.** Message thay đổi và có cardinality cao.
6. **Nhầm placeholder JUL `{0}` và SLF4J `{}`.** Nội dung `message` không được format như kỳ vọng.
7. **Dùng `record.getMessage()` rồi tưởng đó là formatted text trong mọi JUL Formatter.** Cần hiểu `formatMessage(record)`.
8. **Dùng `PatternLayout` text rồi coi là JSON encoder an toàn.** Pattern không tự escape toàn bộ string JSON.
9. **Đưa stack trace dài và nội dung bí mật vào message.** Nên sử dụng trường lỗi riêng và redaction.
10. **Chỉ test parse, không test kiểu field.** JSON hợp lệ vẫn có thể sai mapping hoặc schema.
11. **Không kiểm tra file/stdout/collector sau khi đổi layout.** Producer không chứng minh ingestion hoàn tất.
12. **Coi SLF4J fluent `addKeyValue` tự xuất vào JSON bất kể backend.** Phải kiểm chứng encoder.
13. **Cắt JSON output sau khi encode bằng substring.** Có thể cắt giữa escape/UTF-8 khiến JSON hỏng.
14. **Ghi raw request hoặc exception.toString() không kiểm soát.** Có thể lộ token, URL nhạy cảm hoặc PII.
15. **Tưởng message rỗng là message bị thiếu.** `""`, `null` và absent khác nhau.

## 17. Checklist trước khi đưa vào production

- [ ] Trường `message` có kiểu string nhất quán, có quy tắc khi rỗng/missing/null.
- [ ] Nội dung mô tả đúng sự kiện, không khẳng định kết quả chưa được xác minh.
- [ ] Có mã `event` ổn định và các field nghiệp vụ riêng khi cần truy vấn.
- [ ] Template được format đúng theo API (JUL/SLF4J/Log4j 2).
- [ ] Encoder tạo JSON hợp lệ, escape quote/backslash/control chars và hỗ trợ UTF-8.
- [ ] Nếu dùng JSON Lines, mỗi event chiếm một dòng vật lý.
- [ ] Log4j2 JsonTemplateLayout và Logback encoder tuân thủ schema của collector.
- [ ] Structured message không vô tình làm `message` chuyển thành object/array.
- [ ] Stack trace và error type nằm ở vị trí rõ ràng, không mất khi xử lý Throwable.
- [ ] Có allowlist/redaction để ngăn token, password, OTP, cookie và PII không cần thiết.
- [ ] Có giới hạn kích thước, chính sách truncate và marker khi bị cắt.
- [ ] Context/traceId được truyền đúng qua thread pool hoặc async pipeline.
- [ ] Có unit test escaping và round-trip JSON parse.
- [ ] Có integration test gửi log tới sink/collector/index và truy vấn lại được.
- [ ] Có metric theo dõi parse error, dropped events, ingest lag, schema conflict.
- [ ] Đã xác nhận output của **artifact deploy thật**, không chỉ chạy code từ IDE.

## Tài liệu tham khảo

- [Java 17 — Formatter.formatMessage(LogRecord)](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html)
- [Java 17 — LogRecord và parameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html)
- [Apache Log4j 2 — JSON Template Layout, message resolver và stringified](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [Apache Log4j 2 — Layouts và PatternLayout](https://logging.apache.org/log4j/2.x/manual/layouts.html)
- [SLF4J Manual — Parameterized Logging và Fluent API](https://www.slf4j.org/manual.html)
- [Logback — Layouts](https://logback.qos.ch/manual/layouts.html)

**Ghi nhớ:** Trong JSON logging, **`message` nên là lời mô tả dễ đọc, có kiểu dữ liệu ổn định**, không phải nơi dồn toàn bộ context hoặc data của ứng dụng. Hãy tách mã sự kiện và các thuộc tính cần truy vấn, để encoder JSON xử lý escaping, kiểm tra schema với sink thực tế và không đưa dữ liệu nhạy cảm vào message.