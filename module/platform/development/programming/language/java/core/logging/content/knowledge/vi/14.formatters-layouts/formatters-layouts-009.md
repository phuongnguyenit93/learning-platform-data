# Định dạng key-value trong Java Logging: thiết kế, encode và kiểm thử

## 1. Định dạng key-value là gì?

**Key-value logging** là cách trình bày một sự kiện log thành các cặp **tên trường = giá trị trường**, thường viết theo dạng `key=value`. Thay vì chỉ ghi một câu tự do như “Payment provider timed out”, một sự kiện có thể được biểu diễn:

```text
timestamp="2026-11-09T10:15:30Z" level="WARN" service="payment-service" event="GATEWAY_TIMEOUT" orderId="O-17" elapsedMs=3000 action="SELECT_FALLBACK"
```

Mỗi cặp mang một ý nghĩa cụ thể:

- `timestamp`: thời điểm xảy ra sự kiện.
- `level`: mức độ nghiêm trọng, ví dụ INFO/WARN/ERROR; trong JUL dùng INFO/WARNING/SEVERE.
- `service`: hệ thống hoặc thành phần phát sự kiện.
- `event`: mã sự kiện ổn định, dễ tổng hợp.
- `orderId`: mã đơn hàng được phép ghi.
- `elapsedMs`: thời gian thực thi tính theo mili-giây.
- `action`: hành động ứng dụng thực sự đã chọn.

Định dạng này có ba mục tiêu:

1. **Dễ đọc:** kỹ sư nhìn thấy dữ liệu nào đi cùng sự kiện mà không phải phân tích ngữ pháp của một câu văn dài.
2. **Dễ lọc/tổng hợp:** collector có thể tách các trường theo quy ước thống nhất thay vì đoán từ vị trí từ ngữ.
3. **Giảm mơ hồ:** tên trường chỉ rõ “3000” là `elapsedMs`, không phải số lần thử hoặc mã lỗi.

**Điều kiện quan trọng:** `key=value` chỉ là cách biểu diễn, **không tự trở thành structured logging đúng chuẩn**. Muốn machine-parse đáng tin cậy, hai phía phát và nhận log phải thống nhất quy tắc **tên key, ngăn cách cặp, quoting, escaping, kiểu dữ liệu, giá trị thiếu và schema version**. Nếu không có hợp đồng đó, một message chứa dấu cách, dấu bằng hoặc xuống dòng có thể phá parser.

Bài học thuộc chủ đề **Formatter và layout**: chúng ta tập trung vào *cách format một LogEvent/LogRecord thành key-value*. Việc đặt level, lưu file hay thu thập log là các thành phần liên quan, nhưng không thay thế vấn đề encode giá trị ở bài này.

## 2. Một log event đi qua Formatter/Layout như thế nào?

```text
Java code
    |
    | logger.info(...), logger.warn(...)
    v
Logger + level/filter
    |
    v
LogRecord / LogEvent
  - timestamp
  - level
  - logger name
  - message
  - exception
  - attributes / MDC / context
    |
    v
Formatter (JUL) hoặc Layout/Encoder (Log4j 2, Logback)
    |
    | thành một dòng key=value, text hoặc JSON
    v
Handler / Appender
    |
    v
stdout / file / network / collector / storage
```

Các hệ Java có thuật ngữ riêng:

| Hệ thống | Sự kiện | Thành phần biểu diễn | Thành phần xuất đích |
| --- | --- | --- | --- |
| **java.util.logging (JUL)** | `LogRecord` | `java.util.logging.Formatter` | `Handler` |
| **Log4j 2** | `LogEvent` | `Layout`, ví dụ `PatternLayout` hoặc `JsonTemplateLayout` | `Appender` |
| **Logback** | `ILoggingEvent` | `Layout` hoặc `Encoder` | `Appender` |

Trong JUL, lớp `Formatter` có phương thức `String format(LogRecord)`; `formatMessage(LogRecord)` là tiện ích định dạng/localize message, **không tự tạo các cặp key-value có schema riêng**. Muốn format các trường bổ sung trong JUL, ta phải tự quy định cách mang và encode dữ liệu.

Trong Log4j 2, `PatternLayout` có thể in literal `level=`, `logger=`, các conversion như `%p`, `%c`, `%X{traceId}`. Tuy nhiên, ghép literal và biến **chưa đủ để an toàn cho parser** khi giá trị chứa dấu cách hoặc ký tự điều khiển.

Với các pipeline phân tích dữ liệu thực sự, tài liệu Log4j 2 khuyến nghị **JSON Template Layout** thay cho PatternLayout dùng như structured encoder. Dạng key-value dạng text vẫn hữu ích cho các dòng log dễ đọc khi đã có quy tắc quote/escape hoặc cần tương thích với hệ thu thập hỗ trợ logfmt-like formats.

## 3. Thiết kế một quy ước key=value rõ ràng

Không có một grammar duy nhất áp dụng cho mọi hệ thống tự gọi là “key-value”. Trước khi code, hãy viết **hợp đồng định dạng**. Ví dụ đề xuất cho một hệ thống nội bộ:

1. **Một log event = một dòng text.** Kết thúc bằng ký tự xuống dòng của record, không để newline từ input tạo record giả.
2. **Các cặp cách nhau bằng đúng một dấu cách ASCII**, không dùng dấu phẩy làm separator trừ khi toàn bộ parser đã hỗ trợ.
3. **Key:** chỉ nhận `[A-Za-z][A-Za-z0-9_]*`; key ổn định, đặt bởi developer, không lấy trực tiếp từ input người dùng.
4. **Dấu `=`** phân tách tên trường và giá trị.
5. **String luôn trong dấu ngoặc kép:** `orderId="O-17"`, `message="Order accepted"`.
6. **Boolean và số hữu hạn có thể để trần:** `success=true`, `elapsedMs=3000`.
7. **Null viết `null` không quote:** khác với string chữ “null” được viết `"null"`.
8. **Escape trong string:** dấu nháy kép thành `\"`, backslash thành `\\`, newline thành `\n`, carriage return thành `\r`, tab thành `\t` và ký tự điều khiển khác bằng `\uXXXX`.
9. **Thứ tự trường ổn định** để dễ so sánh bằng mắt và test; nhưng parser không nên dựa vào vị trí cột.
10. **Không có trường tùy tiện từ object/HTTP request:** dùng allowlist và giới hạn kích thước.

Ví dụ theo quy ước:

```text
timestamp="2026-11-09T10:15:30Z" level="INFO" service="order-service" event="ORDER_ACCEPTED" attempts=1 orderId="O-17" success=true
```

Ở đây người đọc có thể phân biệt string `"1"` với số `1`, string `"false"` với boolean `false`. Tuy nhiên, khi nạp từ một text parser, **kiểu dữ liệu sẽ được giữ hay chuyển lại tùy grammar/collector**; không phải mọi logfmt parser đều tự tạo type tương ứng với Java.

**Không gọi quy ước tự thiết kế này là “logfmt chuẩn duy nhất”.** Logfmt và các định dạng tương tự có những biến thể về dấu nháy và escape. Nếu dùng thư viện parser cụ thể, phải thử đối chiếu trực tiếp grammar của bộ parser đó.

### Phân biệt key, value, event code và message

Một message tự do có thể biến đổi theo từng bản phát hành:

```text
message="Payment was delayed"
message="Timeout while contacting provider"
```

Vì vậy, nên có thêm **mã sự kiện ổn định**:

```text
event="PAYMENT_TIMEOUT" message="Payment provider did not respond"
```

Không lấy chính message làm khóa duy nhất để tính tỷ lệ lỗi dài hạn. Mã sự kiện ổn định thuận tiện cho dashboard và alert, còn message bổ sung ngữ cảnh cho con người.

## 4. Các ca nguy hiểm với separator và escaping

### 4.1. Dấu cách trong value

Cách viết thiếu quote:

```text
service=order-service message=Order accepted
```

Một parser chỉ tách theo dấu cách có thể coi `accepted` là token không có key. Quy ước quote string giải quyết vấn đề:

```text
service="order-service" message="Order accepted"
```

### 4.2. Dấu bằng trong value

Dữ liệu:

```text
query="status=PAID" detail="a=b c=d"
```

Không được split mỗi token bằng **tất cả** dấu bằng rồi coi tất cả mảnh là các cặp mới. Parser chỉ dùng dấu `=` **đầu tiên bên ngoài dấu nháy** làm ranh giới key/value. Các dấu bằng nằm trong string là dữ liệu.

### 4.3. Dấu nháy kép và backslash

Chuỗi chứa dấu nháy và đường dẫn cần được escape đúng quy ước:

```text
message="Invalid field \"amount\"" path="C:\\logs\\orders"
```

Trong đó `\"` biểu diễn dấu nháy *thuộc value*, không kết thúc value; `\\` biểu diễn một dấu backslash. Nếu parser không hỗ trợ escape đó, phải đổi sang encoder/parser tương thích hoặc dùng JSON.

### 4.4. Newline và log injection

Giả sử message gốc có hai dòng:

```text
Order accepted
level=ERROR message="Fake incident"
```

Nếu nối trực tiếp vào text output, người xem có thể nhầm dòng thứ hai thành một sự kiện độc lập. Bộ encode cần chuyển ký tự newline thật thành **hai ký tự hiển thị** `\n`:

```text
message="Order accepted\nlevel=ERROR message=\"Fake incident\""
```

Đây vẫn là **một dòng sự kiện**. Cùng nguyên tắc áp dụng cho carriage return, tab và các ký tự điều khiển khác. Với system ingest yêu cầu mỗi event một dòng, nên test cả `\r`, `\n`, `\t`, NUL và chuỗi Unicode.

### 4.5. Missing, null, empty string

Ba trạng thái khác nhau:

```text
# Không có key userId: unknown hoặc không được thu thập.
event="ORDER_CREATED"

# Có key và giá trị null.
event="ORDER_CREATED" userId=null

# Có key và chuỗi rỗng.
event="ORDER_CREATED" userId=""
```

Chúng **không nên bị tự ý đồng nhất** trong pipeline nếu nghiệp vụ cần phân biệt. Tùy chính sách riêng tư, nhiều trường định danh cá nhân cần **vắng mặt hoàn toàn** chứ không phải ghi null.

## 5. Các trường key-value hữu ích trong service Java

Một schema mẫu:

| Trường | Giá trị ví dụ | Lý do |
| --- | --- | --- |
| `timestamp` | `"2026-11-09T10:15:30Z"` | Thời điểm; ưu tiên UTC hoặc offset rõ ràng. |
| `level` | `"WARN"` | Severity, tên level tùy API. |
| `service` | `"payment-service"` | Phân biệt dịch vụ/instance. |
| `environment` | `"production"` | Phân biệt môi trường. |
| `logger` | `"com.example.payment.Client"` | Vị trí thành phần phát event. |
| `event` | `"PAYMENT_TIMEOUT"` | Mã ổn định để tìm kiếm/alert. |
| `correlationId` | `"req-1001"` | Theo dõi chuỗi xử lý cùng request. |
| `traceId` | `"4bf92f..."` | Liên kết tracing nếu có. |
| `orderId` | `"O-17"` | ID nghiệp vụ được phép ghi, thay vì toàn bộ entity. |
| `elapsedMs` | `3000` | Có đơn vị thời gian rõ ràng. |
| `attempt` | `2` | Số lần thử, type số. |
| `success` | `false` | Kết quả dưới dạng boolean. |
| `action` | `"SELECT_FALLBACK"` | Hành động hệ thống đã chọn. |
| `message` | `"Provider timed out"` | Mô tả có thể đọc. |
| `errorType` | `"java.net.SocketTimeoutException"` | Loại exception khi cần điều tra. |

**Không đưa mọi thuộc tính vào một event**. Chọn những trường thực sự hỗ trợ điều tra và đặt giới hạn kích thước. `traceId` và `correlationId` thường rất hữu ích, nhưng không nên biến mọi ID duy nhất thành nhãn metric có cardinality cực cao.

### Tên trường và chuẩn hóa

- Chọn một quy tắc đặt tên, ví dụ `camelCase` hoặc `snake_case`, dùng nhất quán trong toàn bộ hệ thống.
- Không thay `elapsedMs` thành `duration` mà không nói rõ đơn vị; số 100 không thể tự cho biết giây hay mili-giây.
- Tránh key tùy ý dạng `featureFlag.<dynamicName>` nếu parser/index không được thiết kế cho điều đó.
- Với schema thay đổi lớn, thêm `schemaVersion` để collector/consumer biết cách diễn giải.
- Giữ tên `level`, `event`, `timestamp` là field có ý nghĩa ổn định.
- Khi nội dung chỉ cần cho phép tìm bằng ID, không ghi raw email, số điện thoại hoặc dữ liệu cá nhân khác.

## 6. Ví dụ Java 17 chạy độc lập: custom JUL Formatter tạo key=value

JDK 17 có sẵn **java.util.logging (JUL)**. Ví dụ không cần Maven hoặc thư viện bên thứ ba; nó mô phỏng **LogRecord chứa event code và một map thuộc tính**, sau đó custom `Formatter` đưa record thành **một dòng key=value**. Đây là bài học về định dạng, không phải một logging framework đầy đủ.

Quy tắc của formatter:

- `timestamp`, `level`, `event` luôn đứng trước các trường khác.
- Các trường động được sắp xếp theo key bằng `TreeMap` để output có thứ tự xác định.
- String **luôn quote** và escape ký tự đặc biệt.
- Boolean và Number hữu hạn để dạng chữ không quote.
- Null xuất `null`; string chữ “null” xuất `"null"`.
- Key bị giới hạn theo một pattern; không cho tùy ý chèn separator hay tạo key trùng các trường hệ thống.
- `LogRecord.getParameters()` được dùng như một **quy ước chỉ dành cho demo** để chứa map, không phải chuẩn structured logging chính thức của JUL.

### 6.1. Tệp KvLoggingDemo.java

```java
import java.time.Instant;
import java.util.Map;
import java.util.TreeMap;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class KvLoggingDemo {

    private KvLoggingDemo() {
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.keyvalue");
        logger.setUseParentHandlers(false);

        // Không sử dụng handler đã tồn tại của logger demo.
        for (Handler h : logger.getHandlers()) {
            logger.removeHandler(h);
        }
        logger.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new KvFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        emit(logger, Level.INFO, "ORDER_ACCEPTED",
                Instant.parse("2026-11-09T10:15:30Z"),
                Map.of(
                        "orderId", "O-17",
                        "attempts", 1,
                        "success", true));

        emit(logger, Level.WARNING, "GATEWAY_FALLBACK",
                Instant.parse("2026-11-09T10:15:31Z"),
                Map.of(
                        "orderId", "O-18",
                        "dependency", "primary gateway",
                        "reason", "timeout\nretry"));
    }

    private static void emit(Logger logger, Level level,
                             String event, Instant when,
                             Map<String, ?> attributes) {
        LogRecord record = new LogRecord(level, event);
        record.setInstant(when);
        record.setParameters(new Object[]{attributes});
        logger.log(record);
    }

    private static final class KvFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder line = new StringBuilder();

            line.append("timestamp=")
                    .append(quote(record.getInstant().toString()));
            line.append(" level=")
                    .append(quote(record.getLevel().getName()));
            line.append(" event=")
                    .append(quote(record.getMessage()));

            Object[] parameters = record.getParameters();
            if (parameters != null && parameters.length > 0
                    && parameters[0] instanceof Map<?, ?> fields) {

                // TreeMap giúp output ổn định, không phụ thuộc
                // thứ tự duyệt Map.of() trong JVM.
                TreeMap<String, Object> sorted = new TreeMap<>();

                for (Map.Entry<?, ?> entry : fields.entrySet()) {
                    if (!(entry.getKey() instanceof String key)
                            || !key.matches("[A-Za-z][A-Za-z0-9_]*")) {
                        throw new IllegalArgumentException(
                                "Invalid log field key");
                    }
                    if (key.equals("timestamp")
                            || key.equals("level")
                            || key.equals("event")) {
                        throw new IllegalArgumentException(
                                "Reserved log field key: " + key);
                    }
                    sorted.put(key, entry.getValue());
                }

                for (Map.Entry<String, Object> entry
                        : sorted.entrySet()) {
                    line.append(' ').append(entry.getKey())
                            .append('=')
                            .append(formatValue(entry.getValue()));
                }
            }
            return line.append('\n').toString();
        }

        private static String formatValue(Object value) {
            if (value == null) {
                return "null";
            }
            // NaN/Infinity không phải số hữu hạn.
            if (value instanceof Double d && !Double.isFinite(d)) {
                return quote(d.toString());
            }
            if (value instanceof Float f && !Float.isFinite(f)) {
                return quote(f.toString());
            }
            if (value instanceof Number || value instanceof Boolean) {
                return value.toString();
            }
            return quote(String.valueOf(value));
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
                            out.append(String.format(
                                    Locale.ROOT, "\\u%04x", (int) c));
                        } else {
                            out.append(c);
                        }
                    }
                }
            }
            return out.append('"').toString();
        }
    }
}
```

### 6.2. Biên dịch và chạy bằng JDK 17+

Lưu tệp đúng tên `KvLoggingDemo.java`, sau đó chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 KvLoggingDemo.java
java KvLoggingDemo
```

**Stdout chính xác** của chương trình:

```text
timestamp="2026-11-09T10:15:30Z" level="INFO" event="ORDER_ACCEPTED" attempts=1 orderId="O-17" success=true
timestamp="2026-11-09T10:15:31Z" level="WARNING" event="GATEWAY_FALLBACK" dependency="primary gateway" orderId="O-18" reason="timeout\nretry"
```

Hai dòng trên là **hai record**, dù giá trị `reason` trong Java chứa newline thật. Formatter đã escape thành hai ký tự `\n`, vì vậy không có dòng log thứ ba giả mạo.

### 6.3. Phân tích code

1. `LogRecord` chứa level, event code và instant. Timestamp trong ví dụ được **đặt cố định** để stdout lặp lại chính xác; trong ứng dụng thật nên sử dụng thời điểm sự kiện thực tế, không hard-code.
2. `record.setParameters(new Object[]{attributes})` đưa map vào record để custom formatter đọc. Đây là **hợp đồng nội bộ của ví dụ**, không phải kiểu structured attribute của JUL chuẩn; nếu thay formatter khác, map có thể không được xuất.
3. `TreeMap` đảm bảo thứ tự `attempts`, `orderId`, `success` ở record đầu bất kể `Map.of(...)` duyệt theo thứ tự nào.
4. `quote(...)` xử lý dấu nháy kép, backslash, newline, tab, carriage return và các ký tự điều khiển nhỏ hơn `U+0020`. Nó không cắt một dòng log chỉ vì input chứa newline.
5. `formatValue(...)` giữ Number/Boolean ở dạng không quote, nhưng chuỗi như `"true"` được quote, tránh nhầm kiểu trong parser có hỗ trợ. Với giá trị số vô hạn hoặc NaN, demo đưa về string để không giả định là số hợp lệ.
6. `logger.setUseParentHandlers(false)` tránh output bổ sung từ logger cha/root. Handler `StreamHandler(System.out,...)` chủ động hướng stdout và được `flush()` sau mỗi `publish` để bài học quan sát được kết quả; `ConsoleHandler` của JUL mặc định thường hướng stderr.
7. Chương trình chỉ có một thread, không chạy network/file I/O và không phụ thuộc timezone hệ điều hành vì dùng `Instant` UTC cố định.

**Giới hạn cần hiểu:** formatter này dành cho mục đích học tập. Nó không giải quyết toàn bộ Unicode surrogate bất thường, policy giới hạn kích thước, dữ liệu nhạy cảm, cách encode stack trace, context propagation hay các dạng `Number` tùy biến. Để sản xuất dữ liệu cho pipeline lớn, ưu tiên encoder được bảo trì và kiểm thử cùng parser thực tế; nếu consumer yêu cầu JSON, phải dùng JSON serializer chứ không đưa chuỗi key=value này cho JSON parser.

### 6.4. Thử nghiệm thêm

- Đổi `reason` thành `"bad=\"yes\"\nnext=ERROR"`: kết quả phải **vẫn là một dòng** với dấu `\"` và `\n`.
- Thêm trường kiểu số `elapsedMs=3000`, Boolean `fallback=true`: xác nhận không có dấu quote quanh số/Boolean.
- Thử key `"client id"` hoặc `"x=y"`: formatter trong demo từ chối bằng lỗi validate key, tránh tạo cặp giả.
- Với `Map` cho phép null, thêm giá trị null: output `field=null`, không nhầm với string `"null"`.
- Bật lọc level ở logger hoặc handler: chỉ các record được chấp nhận mới tới stdout; formatter không thể “phục hồi” record đã bị loại.

## 7. Với Log4j 2: PatternLayout tạo key=value để đọc bằng mắt

Log4j 2 cho phép dùng `PatternLayout` với chữ literal và pattern converter:

```xml
<Console name="Console" target="SYSTEM_OUT">
    <PatternLayout
        pattern="level=%p logger=%c traceId=%X{traceId} message=%m%n"/>
</Console>
```

Ở đây:

- `%p`: level của event.
- `%c`: logger name.
- `%X{traceId}`: giá trị `traceId` trong Thread Context Map/MDC.
- `%m`: formatted message.
- `%n`: separator xuống dòng của nền tảng.

Ví dụ sử dụng ThreadContext trong code:

```java
// Đoạn minh họa trong service dùng Log4j 2, không phải file độc lập.
import org.apache.logging.log4j.CloseableThreadContext;

try (CloseableThreadContext.Instance scope =
        CloseableThreadContext.put("traceId", "req-1001")) {
    logger.info("Order {} accepted", "O-17");
}
```

Lưu ý **bài toán format vẫn chưa được giải quyết triệt để**: nếu `%m` hoặc `%X{traceId}` chứa dấu cách/newline, PatternLayout trên **không tự thêm quote cho từng giá trị theo grammar mục 3**. Đây là **pseudo key-value dễ đọc** chứ không đủ để gọi là encoding machine-safe. Dùng pattern này để học converter, không mặc định dùng làm hợp đồng ingest cho dữ liệu không đáng tin.

Log4j 2 có converter `%enc{...}{CRLF}` hỗ trợ escape newline/carriage return trong phần được bao, ví dụ `%enc{%m}{CRLF}`. Tuy nhiên, chỉ escape CR/LF **không tự xử lý dấu nháy/backslash hoặc tạo đầy đủ grammar key-value của hệ thống**. Khi dữ liệu phải parse tin cậy, nên dùng layout có cấu trúc (đặc biệt `JsonTemplateLayout`) hoặc encoder key-value chuyên dụng đã được kiểm thử.

**Không nhầm:** `%X{traceId}` dùng cho context map; `%K{key}` của PatternLayout có ý nghĩa khác, dùng cho một số dạng `MapMessage`. Việc gõ hai converter giống nhau sẽ không bảo đảm đọc cùng nguồn dữ liệu. Hãy xem tài liệu PatternLayout của đúng phiên bản backend.

### Vì sao không chỉ nối `key=value` trong message?

```java
// Chỉ tạo một string, backend không tự biết các field riêng.
logger.info("orderId=" + orderId + " elapsedMs=" + elapsedMs);
```

Nó có thể **dễ đọc** nhưng không bảo đảm backend lưu thành hai attribute cấu trúc. Thêm nữa, phép nối `+` xảy ra ở caller trước khi backend lọc log level, có thể lãng phí nếu toán hạng đắt hoặc log bị tắt. Ưu tiên API logging theo tham số với các biến đã có, và giữ structured attributes theo API/encoder được hỗ trợ khi muốn truy vấn theo field.

## 8. Với SLF4J 2: key-value là attribute, không chỉ là câu text

SLF4J 2.x có **fluent logging API** cho phép bổ sung cặp key-value vào event:

```java
// Minh họa trong ứng dụng đã có SLF4J 2.x và provider/backend phù hợp.
logger.atInfo()
      .addKeyValue("orderId", "O-17")
      .addKeyValue("elapsedMs", 125)
      .log("Order processed");
```

API này mang key-value theo metadata của sự kiện; nó **không có nghĩa mọi provider sẽ tự in `orderId="O-17"` hay đưa `elapsedMs` vào JSON dưới cùng một tên trường**. Cách hiển thị phụ thuộc provider, encoder/layout, phiên bản và cấu hình. Ví dụ `slf4j-simple` có cách format riêng; Logback/Log4j 2 có hệ layout riêng và khả năng giữ key-value khác nhau.

Một cách viết chỉ nhét placeholder trong message:

```java
logger.info("Order {} processed in {} ms", orderId, elapsedMs);
```

giúp tránh ghép chuỗi chủ động, nhưng **không bảo đảm** collector nhìn thấy `orderId` và `elapsedMs` như hai field riêng. Cần phân biệt:
- **Parameterized message:** template và arguments để dựng ra message.
- **Structured key-value attributes:** cặp tên trường/giá trị được mang riêng trong event và được encoder hỗ trợ.

Với SLF4J 1.7, fluent API `atInfo().addKeyValue(...)` không tồn tại. Khi nâng cấp code, đối chiếu phiên bản API runtime và provider/backend để tránh lỗi `NoSuchMethodError` hoặc log metadata bị bỏ qua.

## 9. Với Logback: Pattern và cấu hình key-value

Logback thường là backend của SLF4J. Trong Logback, `PatternLayoutEncoder` hoặc các encoder khác chuyển event thành text/bytes để appender ghi. Ví dụ layout cơ bản:

```xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>level=%level logger=%logger message=%msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

Đây là file cấu hình Logback minh họa, **không phải chương trình Java độc lập**; cần SLF4J và Logback phiên bản tương thích. Cũng như ví dụ Log4j 2, dữ liệu `%msg` chưa được quote/escape theo hợp đồng key-value của mục 3, vì vậy chỉ dùng như **pattern dễ đọc**.

Một số phiên bản Logback hiện đại hỗ trợ conversion word hoặc encoder chuyên xử lý key-value pairs từ SLF4J fluent API. **Không giả định mọi version Logback có cùng converter/cú pháp.** Phải đọc tài liệu của phiên bản đang dùng và test cả trường hợp key/value chứa khoảng trắng, dấu nháy và newline.

Nếu cần structured ingest trong production, cân nhắc JSON encoder dành cho Logback phù hợp với version và yêu cầu schema, hoặc tổ chức collector có parser chính thức đã được kiểm chứng. Không copy `log4j2.xml` của Log4j 2 thành `logback.xml`: hai hệ dùng cú pháp khác nhau.

## 10. Key-value text so với JSON Lines

Cùng một sự kiện có thể biểu diễn theo hai dạng.

**Key-value text theo grammar bài học:**

```text
level="WARN" event="PAYMENT_TIMEOUT" orderId="O-17" elapsedMs=3000 action="SELECT_FALLBACK"
```

**JSON Lines (một JSON object trên một dòng):**

```json
{"level":"WARN","event":"PAYMENT_TIMEOUT","orderId":"O-17","elapsedMs":3000,"action":"SELECT_FALLBACK"}
```

| Tiêu chí | Key-value text | JSON Lines |
| --- | --- | --- |
| Dễ đọc thủ công | Gọn, ít dấu cú pháp. | Vẫn đọc được, nhưng nhiều dấu ngoặc/nháy. |
| Grammar chuẩn hóa | Phụ thuộc quy ước logfmt-like và parser cụ thể. | JSON có chuẩn cú pháp rõ ràng. |
| Number/Boolean/Null | Tùy quy tắc và parser. | Có các literal được JSON xác định. |
| Dữ liệu lồng nhau | Cần quy ước flatten hoặc string encode riêng. | Hỗ trợ object/array lồng nhau. |
| Escaping | Phải thống nhất, dễ sai khi làm thủ công. | Serializer JSON xử lý theo chuẩn nếu dùng đúng. |
| Ingest/query | Cần parser tương thích. | Dễ tích hợp với hệ thống hỗ trợ JSON. |
| Tương thích nhiều backend | Cần thống nhất template/encoder. | Thường có encoder JSON hoặc plugin phù hợp. |

**Quyết định thực tế:** dùng key=value khi mục tiêu là dòng ngắn, dễ grep và hệ thống đã có grammar/parser thống nhất. Chọn **JSON structured logging** khi cần schema chặt chẽ, trường lồng nhau, đa hệ thống ingest và công cụ phân tích ổn định. Không nên tự viết JSON bằng nối chuỗi và không nên coi một pattern text có chữ `key=` là structured logging đầy đủ.

## 11. Context propagation, MDC và trường liên kết

Trong hệ thống có nhiều service, một chuỗi request có thể phát hàng trăm event. Các trường như `correlationId`, `traceId` hoặc `spanId` cho phép lọc những event có liên quan.

Với Log4j 2, `ThreadContext` giữ map/stack theo ngữ cảnh thực thi hiện tại. Với SLF4J/Logback thường có `MDC`. Tuy nhiên, nhiều implementation dựa vào thread-local; khi chạy executor, CompletableFuture hoặc reactive pipeline, context **không nhất thiết tự đi theo** luồng xử lý.

Các nguyên tắc:

1. Gắn correlation ID từ ranh giới request, không phát sinh ID mới ở mọi layer.
2. Truyền context khi chạy công việc qua thread khác theo cơ chế runtime đang dùng.
3. Khôi phục/clear context trong `finally` hoặc scope hỗ trợ, để thread pool không làm lẫn request.
4. Không tự động đưa toàn bộ HTTP headers, cookies hoặc request body vào MDC.
5. Khi dùng async logging, chú ý thời điểm snapshot dữ liệu để sự kiện không đổi sau lúc tạo.

**Trường key=value nên mang trạng thái ở thời điểm log**, không phụ thuộc object mutable bị thay đổi trước khi encoder chạy trên background thread. Nếu điều tra sự cố cần chính xác, tạo snapshot gọn, bất biến, được phép ghi.

## 12. Bảo mật, PII và log injection

Structured hay key-value logging đều có thể làm rò bí mật nếu event được tạo sai.

### Dữ liệu không được phép

Không đưa vào log: password, OTP, access token, refresh token, session cookie, private key, toàn bộ thông tin thanh toán nhạy cảm hoặc dữ liệu cá nhân vượt nhu cầu điều tra. Với object domain, không tin rằng `toString()` mặc định đã redaction an toàn.

**Tốt hơn:** chỉ đưa những ID và thông số đã được cho phép vào allowlist như `orderId`, `event`, `elapsedMs`, `outcome`. Thiết lập quyền truy cập kho log, retention, mã hóa khi truyền và lưu theo quy định.

### Escaping phải xảy ra trước khi xuất

Nếu input có newline, dấu nháy hoặc backslash, phải encode theo grammar chung **trước khi handler/appender ghi**. Filter ở collector chạy sau đó không thể xóa dữ liệu bí mật đã nằm trong stdout/file trước collector.

### Truncate và giới hạn kích thước

Một trường message quá lớn có thể khiến collector cắt byte, phá quote hoặc làm mất các trường cuối; nếu chọn truncate, phải định nghĩa giới hạn theo **byte hay ký tự**, giữ cú pháp hợp lệ và thêm tín hiệu `truncated=true` khi cần. Tránh cắt giữa UTF-8 multibyte, Unicode surrogate hoặc escape sequence. Với nhiều hệ thống, giảm event size ở nguồn và chuyển dữ liệu chi tiết tới kho chuyên biệt tốt hơn việc cố ghi toàn bộ payload vào log.

### Không để trường động gây cardinality vô hạn

Key nên là danh sách hữu hạn đã được code review. Đưa tên khách hàng, email hoặc URL truy vấn thành **tên field** là lỗi thiết kế; khiến collector/index phình to và tạo rủi ro lộ dữ liệu. Giá trị ID có cardinality cao cũng cần được sử dụng đúng (để tìm kiếm theo event, không tự biến thành label metric vô hạn).

## 13. Kiểm thử formatter và hệ thống ingest

Một formatter chỉ “đẹp khi nhìn” chưa đủ. Với key-value, cần test cả **round-trip**: encode event → parser nhận → decode đúng field và giá trị ban đầu.

| Ca thử | Kỳ vọng |
| --- | --- |
| String không dấu cách | Có quote theo grammar hoặc được parser nhận đúng. |
| String chứa space/tab | Không sinh token/cặp giả. |
| Dấu nháy kép trong value | Escape và decode lại đúng chuỗi gốc. |
| Backslash trong path | Không bị nuốt hoặc nhân đôi sai khi parse. |
| Newline/CR/LF | Một event không bị biến thành nhiều dòng. |
| Dấu bằng trong value | Không tạo thêm key-value mới. |
| Unicode tiếng Việt | Giữ nguyên dấu, đọc/ghi UTF-8 đúng, không cắt giữa byte. |
| Boolean, integer, decimal | Có quy tắc kiểu dữ liệu và đơn vị rõ ràng. |
| Missing/null/empty string | Được phân biệt đúng theo schema. |
| Key không hợp lệ/dynamic | Bị từ chối hoặc chuẩn hóa theo chính sách đã định. |
| Exception | Có mã lỗi và stack trace theo cách được encoder/collector hỗ trợ. |
| Concurrent/async logging | Không lẫn correlation ID hoặc giá trị mutable giữa requests. |
| Structured attributes vs message | Provider/layout thực tế bảo toàn những cặp cần truy vấn. |
| Collector/parser | Đọc đúng field và giới hạn event size; báo lỗi parse thay vì im lặng. |

Với demo JUL ở mục 6, có thể chạy chương trình và so sánh stdout nguyên văn. Một bước nâng cao là viết decoder cho grammar quy định, sau đó test thuộc tính:

```text
decode(encode("a b=\n\"c")) == "a b=\n\"c"
```

Đây là **mệnh đề kiểm thử**, không phải source Java độc lập. Test theo bảng ký tự đặc biệt, nhiều chuỗi ngẫu nhiên và trường hợp thiếu dữ liệu sẽ phát hiện lỗi escaping hiệu quả hơn vài ví dụ thông thường.

**Khi backend không xuất được field:** kiểm tra theo thứ tự code có tạo attribute chưa → logger level/filter → provider nhận đúng key-value chưa → layout/encoder có hỗ trợ chưa → appender sink → collector parse → index/query. Đừng suy ra dữ liệu đã được lưu chỉ vì source code dùng `addKeyValue(...)`.

## 14. Những lỗi thường gặp

1. **Nối trực tiếp `message=hello world` mà không quote:** parser tách thành nhiều token.
2. **Đưa user input vào key:** làm schema thay đổi, dễ injection hoặc tạo quá nhiều field.
3. **Chỉ escape dấu nháy, bỏ qua newline/backslash:** log có thể bị giả mạo hoặc parser giải sai.
4. **Chỉ có `logger.info("id={}", id)` rồi tưởng collector có field `id`:** đó có thể chỉ là formatted message.
5. **Dùng PatternLayout với `level=%p msg=%m` như một encoder cấu trúc hoàn chỉnh:** dấu cách và dòng mới vẫn có thể phá grammar.
6. **Không phân biệt null, empty string và missing field:** làm mất ý nghĩa nghiệp vụ.
7. **Đổi tên field/đơn vị tùy ý giữa các module:** dashboard và alert khó so sánh.
8. **Ghi quá nhiều fields hoặc object nguyên vẹn:** tăng chi phí, vượt limit, lộ PII.
9. **Không kiểm tra phiên bản backend:** converter key-value có thể không được hỗ trợ hoặc hành vi khác bản bạn đang chạy.
10. **Chỉ thử console, không kiểm thử parser/collector:** một log “đẹp” chưa chắc đã tìm được trong kho.
11. **Tạo message trong thread khác sau khi object mutable thay đổi:** timestamp/context và giá trị không phản ánh event time.
12. **Để key-value là nguồn audit duy nhất:** log text không mặc nhiên bảo đảm tính toàn vẹn, không mất/trùng hay đã commit giao dịch.

## 15. Checklist áp dụng trong production

- [ ] Có hợp đồng định dạng key=value được mô tả rõ, bao gồm quote/escape/separator/null/kiểu dữ liệu.
- [ ] Chọn tên field ổn định, quy định đơn vị và schema version khi thay đổi phá tương thích.
- [ ] Mỗi log event chỉ chiếm một record logic, không bị newline trong input tạo record giả.
- [ ] Dùng formatter/layout đúng framework (JUL Formatter, Log4j 2 Layout, Logback Encoder).
- [ ] Hiểu rõ tham số trong message khác với metadata key-value được backend hỗ trợ.
- [ ] Có timestamp UTC/offset, level, service, event code và correlation ID khi cần.
- [ ] Không dùng input làm key; có allowlist, giới hạn kích thước, redaction và quyền truy cập.
- [ ] Có test encode/decode và thử dữ liệu khó: space, `=`, `"`, `\\`, Unicode, newline, null.
- [ ] Kiểm thử provider/encoder/collector bằng artifact cuối và cấu hình production tương đương.
- [ ] Khi cần structured ingest nghiêm ngặt, đánh giá JSON encoder thay vì chỉ PatternLayout text.
- [ ] Có quan sát parse errors, drop rate, ingest lag, retention và độ bền của từng sink.

## Tài liệu tham khảo

- [Java 17 — Formatter của java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html)
- [Apache Log4j 2 — Pattern Layout và các converter MDC](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html)
- [Apache Log4j 2 — Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html)
- [Apache Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [SLF4J 2 — Fluent API và key-value pairs](https://www.slf4j.org/manual.html)
- [Logback — Layouts và PatternLayout](https://logback.qos.ch/manual/layouts.html)

**Ghi nhớ:** key-value giúp log rõ ràng và dễ phân tích **chỉ khi tên trường, kiểu dữ liệu và quy tắc encode được thống nhất**. Một formatter có thể in `orderId="O-17" elapsedMs=3000`, nhưng sự kiện chỉ thật sự “structured” đối với hệ thu thập khi metadata, escaping và parser cùng hiểu một hợp đồng. Khi yêu cầu độ tin cậy và khả năng truy vấn cao, ưu tiên encoder có cấu trúc được hỗ trợ chính thức và kiểm thử end-to-end.