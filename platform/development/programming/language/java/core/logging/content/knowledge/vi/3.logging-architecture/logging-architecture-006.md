# Tầng formatter và layout trong kiến trúc Java Logging

## 1. Formatter/layout giải quyết bài toán gì?

Một ứng dụng gọi logger để **phát sinh sự kiện**: “đơn hàng ORD-7 đã được gửi”, “kết nối cơ sở dữ liệu bị lỗi”. Nhưng để đọc được sự kiện đó trên terminal, trong tệp hay hệ thống tìm kiếm log, ta cần quyết định **mỗi bản ghi sẽ được biểu diễn như thế nào**.

Cùng một sự kiện có thể xuất hiện dưới những cách trình bày khác nhau:

```text
INFO | OrderService | order ORD-7 submitted
```

```text
2026-11-09T08:15:03.125Z INFO  [worker-1] OrderService - order ORD-7 submitted
```

```json
{"timestamp":"2026-11-09T08:15:03.125Z","level":"INFO","logger":"OrderService","thread":"worker-1","event":"order_submitted","orderId":"ORD-7"}
```

Ba dòng trên là **ví dụ định dạng**, không phải ba lần chạy của cùng một đoạn mã. Sự kiện nghiệp vụ có thể giống nhau; đầu ra thay đổi theo bộ định dạng, trường dữ liệu sẵn có và cấu hình.

**Formatter** hoặc **layout** là thành phần nhận một đối tượng sự kiện log và chuyển nó thành biểu diễn đầu ra phù hợp, thường là chuỗi hoặc dữ liệu có thể mã hóa thành byte. Nó quyết định thứ tự trường, dấu phân cách, cách viết thời gian, thông điệp, ngoại lệ và dòng kết thúc. Tầng này giúp tách hai mối quan tâm:

- **Ứng dụng nói điều gì đã xảy ra?** Tạo log record/event với level, message, exception, context.
- **Người đọc hoặc công cụ sẽ thấy nó dưới dạng nào?** Định dạng text, pattern hoặc JSON nhất quán.

Một formatter tốt giúp log dễ đọc, dễ truy vấn và dễ liên kết giữa các thành phần. Nhưng formatter **không tự tạo ra thông tin chưa có trong sự kiện**; chẳng hạn không thể tự biết `requestId` nếu mã ứng dụng hoặc hệ thống logging chưa cung cấp nó.

## 2. Vị trí trong pipeline logging

Mô hình khái quát:

```text
Mã ứng dụng
    |
    v
Logger / logging API
    | Tạo sự kiện, xét mức độ và các quy tắc lọc
    v
Handler / Appender
    | Chọn nơi xuất và điều khiển quá trình ghi
    v
Formatter / Layout (+ Encoder nếu có)
    | Tạo chuỗi / byte theo định dạng
    v
Console / File / Collector / Hệ thống nhận log
```

Sơ đồ là cách nhìn logic. Trong triển khai thực tế, **handler/appender thường chủ động gọi formatter, layout hoặc encoder trong lúc ghi**; không phải mọi thư viện có đúng một lớp trung gian riêng và thứ tự vật lý giống hệt sơ đồ. Với appender bất đồng bộ, việc định dạng có thể diễn ra ở luồng xử lý hàng đợi sau khi sự kiện được tạo.

Trong kiến trúc Java Logging thường gặp:

| Hệ sinh thái | Đối tượng sự kiện | Thành phần ghi ra đích | Thành phần định dạng |
|---|---|---|---|
| `java.util.logging` (JUL, JDK) | `LogRecord` | `Handler` như `ConsoleHandler`, `FileHandler` | `java.util.logging.Formatter` |
| SLF4J + Logback | Sự kiện của Logback, ví dụ `ILoggingEvent` | `Appender` | `Layout` và thường là `Encoder`, ví dụ `PatternLayoutEncoder` |
| Log4j 2 | `LogEvent` | `Appender` | `Layout`, ví dụ `PatternLayout` |
| SLF4J API tự nó | Giao diện gọi logging | Do provider/backend đảm nhiệm | Không tự quy định một formatter/layout chung |

**Phân biệt ba trách nhiệm:**

- **Logger:** giao diện để phát sự kiện, có thể quyết định mức độ nào được bật.
- **Handler/appender:** đưa sự kiện tới nơi cần ghi và có thể áp dụng thêm bộ lọc hoặc chính sách gửi.
- **Formatter/layout/encoder:** biến sự kiện thành biểu diễn cuối cùng. `Layout` mô tả cách trình bày; trong Logback, `Encoder` còn chuyển dữ liệu sang byte để appender ghi ra luồng.

Chẳng hạn, đổi formatter từ text sang JSON **không đồng nghĩa** với việc thay mức log, đổi đích ghi, bật lưu trữ lâu dài hay bảo đảm không mất bản ghi.

## 3. Dữ liệu đầu vào của tầng định dạng

Một log event thường đã chứa hoặc cho phép truy cập các trường sau:

| Trường | Giá trị minh họa | Ý nghĩa khi định dạng |
|---|---|---|
| Timestamp | `2026-11-09T08:15:03.125Z` | Biết thời điểm sự kiện, chọn timezone và độ chính xác |
| Level | `INFO`, `WARNING`, `SEVERE` | Lọc và làm nổi bật mức độ |
| Logger name | `com.example.OrderService` | Nhận diện nơi phát ra sự kiện |
| Message/parameters | `"order {0} submitted"`, `["ORD-7"]` | Tạo thông điệp đã nội suy khi cần |
| Throwable | `IllegalStateException` | Hiển thị loại lỗi, thông điệp và stack trace |
| Thread/context | `worker-1`, `requestId=req-42` | Phục vụ truy vết theo luồng hoặc request |
| Thuộc tính bổ sung | `traceId`, `orderId`, marker | Tạo trường có cấu trúc cho hệ thống tìm kiếm |

Các trường thực tế phụ thuộc API/backend. Ví dụ, JUL `LogRecord` có level, logger name, message, parameters, timestamp và throwable; còn MDC (Mapped Diagnostic Context) thường được sử dụng với SLF4J/Logback/Log4j 2, **không phải thuộc tính có sẵn của `LogRecord` trong JUL**.

Formatter cần định nghĩa cách xử lý trường thiếu: để trống, bỏ khóa, dùng giá trị mặc định hoặc hiển thị dấu nhận biết. Không nên giả định mọi event đều có stack trace hay correlation ID.

## 4. JUL: `java.util.logging.Formatter` và `LogRecord`

Với logging có sẵn trong JDK, lớp trừu tượng `Formatter` cung cấp điểm mở rộng để biến `LogRecord` thành text. API quan trọng:

- `String format(LogRecord record)`: phương thức bắt buộc khi tạo formatter cụ thể; trả về toàn bộ phần text được ghi cho record.
- `String formatMessage(LogRecord record)`: hỗ trợ xử lý resource bundle và tham số trong message theo quy tắc của JUL. Nếu gọi `record.getMessage()` trực tiếp, ta có thể chỉ nhận bản mẫu như `order {0} submitted`.
- `getHead(Handler handler)` và `getTail(Handler handler)`: có thể cung cấp header/footer khi handler xuất một chuỗi bản ghi thành tài liệu có cấu trúc, chẳng hạn XML. Với log một dòng thông thường, thường không cần ghi đè.

Một vài dữ liệu hay dùng từ `LogRecord`:

```java
record.getLevel();
record.getLoggerName();
record.getInstant();      // Instant từ JDK 9+
record.getMessage();
record.getParameters();
record.getThrown();
```

Các dòng trên **chỉ là minh họa API**, không phải chương trình độc lập. Với timestamp, ưu tiên ghi rõ timezone (thường UTC) và định dạng có thể được parser nhận diện; đừng gán giờ địa phương mà không khai báo múi giờ.

### 4.1. Ví dụ Java 17+ chạy độc lập

Ví dụ sau tạo formatter một dòng cho mỗi event và thêm một dòng nguyên nhân khi có exception. Mã cố ý không in timestamp để kết quả chạy ổn định, dễ đối chiếu; hệ thống thực tế nên bổ sung timestamp, correlation ID và chính sách stack trace.

Lưu vào `FormatterLayoutDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class FormatterLayoutDemo {
    private static final Logger LOG =
            Logger.getLogger(FormatterLayoutDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new ReadableFormatter());
        LOG.addHandler(console);

        LOG.log(Level.INFO,
                "order {0} submitted", new Object[]{"ORD-7"});

        try {
            throw new IllegalStateException("inventory offline");
        } catch (IllegalStateException error) {
            LOG.log(Level.SEVERE, "order ORD-7 failed", error);
        }

        console.flush();
    }

    private static final class ReadableFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            String message = oneLine(formatMessage(record));

            String text = record.getLevel().getName()
                    + " | " + record.getLoggerName()
                    + " | " + message + System.lineSeparator();

            Throwable error = record.getThrown();
            if (error != null) {
                text += "cause=" + error.getClass().getSimpleName()
                        + ": " + oneLine(error.getMessage())
                        + System.lineSeparator();
            }
            return text;
        }

        private String oneLine(String value) {
            if (value == null) {
                return "";
            }
            return value.replace("\r", "\\r")
                    .replace("\n", "\\n");
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac FormatterLayoutDemo.java
java FormatterLayoutDemo
```

Kết quả gồm chính xác các dòng sau; `ConsoleHandler` của JUL mặc định ghi vào **`System.err`**, nên đây là output trên console nhưng thuộc luồng `stderr`, không phải `stdout`:

```text
INFO | FormatterLayoutDemo | order ORD-7 submitted
SEVERE | FormatterLayoutDemo | order ORD-7 failed
cause=IllegalStateException: inventory offline
```

**Vì sao kết quả như vậy?**

1. `LOG.log(Level.INFO, "order {0} submitted", new Object[]{"ORD-7"})` tạo một `LogRecord` mang bản mẫu và tham số. `formatMessage(record)` tạo text `order ORD-7 submitted`.
2. `getLevel().getName()` cung cấp `INFO` hoặc `SEVERE`, `getLoggerName()` cung cấp `FormatterLayoutDemo`.
3. `System.lineSeparator()` kết thúc một bản ghi trên hệ điều hành đang chạy. Sự khác nhau giữa LF và CRLF không làm thay đổi nội dung từng dòng được hiển thị.
4. Với sự kiện lỗi, `record.getThrown()` chứa exception. Formatter ví dụ chỉ in tên lớp và thông điệp để kết quả dự đoán được; **đây không phải cách lưu đầy đủ stack trace cho vận hành**.
5. `LOG.setUseParentHandlers(false)` tránh để cùng event đồng thời đi qua các handler của logger cha trong chương trình demo. Đây là cấu hình riêng của JUL, không phải cách sửa mọi trường hợp log bị trùng ở backend khác.

Cơ chế xử lý log vẫn hoạt động nếu thay `ReadableFormatter` bằng một formatter khác. Phần phát sự kiện không cần biết thông điệp sẽ có dấu `|`, timestamp hay JSON.

### 4.2. Giữ thông tin exception khi viết formatter thật

Một formatter tự viết rất dễ **làm mất stack trace** nếu chỉ dùng `record.getThrown().getMessage()`. Muốn giữ toàn bộ đường đi của exception, có thể chuyển `Throwable` thành text bằng `StringWriter` và `PrintWriter`, rồi nối vào bản ghi. Ví dụ đoạn mã sau là **phần minh họa bên trong `format(LogRecord)`**, không phải chương trình độc lập:

```java
if (record.getThrown() != null) {
    java.io.StringWriter buffer = new java.io.StringWriter();
    java.io.PrintWriter writer = new java.io.PrintWriter(buffer);
    record.getThrown().printStackTrace(writer);
    writer.flush();
    text += buffer.toString();
}
```

Với định dạng nhiều dòng, hãy bảo đảm hệ thống thu thập log hiểu stack trace thuộc cùng một event; nếu không, mỗi dòng stack trace có thể bị tách thành bản ghi riêng. Formatter chuyên dụng hoặc JSON encoder có trường exception riêng thường giúp giải quyết vấn đề này tốt hơn việc tự ghép chuỗi.

### 4.3. Formatter có sẵn trong JUL

JUL đã cung cấp các triển khai thông dụng:

- `SimpleFormatter`: đầu ra text đọc được, thường có level, message và thông tin nguồn; định dạng có thể tùy biến qua cấu hình `java.util.logging.SimpleFormatter.format`.
- `XMLFormatter`: tạo biểu diễn XML cho các record, hữu ích khi cần đầu ra có cấu trúc XML. Handler hỗ trợ header/footer sẽ tham gia tạo tài liệu phù hợp.
- `ConsoleHandler` và `FileHandler`: **handler**, không phải formatter; chúng chọn nơi ghi và sử dụng formatter tương ứng. Thay handler hoặc formatter là hai quyết định khác nhau.

Khi dùng formatter tích hợp, vẫn cần kiểm tra encoding, nơi xuất, quyền ghi, rotate log và cách hệ thống nhận log. Những việc đó nằm ngoài trách nhiệm biến record thành text.

## 5. Logback: Layout và Encoder phối hợp thế nào?

Khi ứng dụng gọi SLF4J và dùng Logback làm backend, mô hình thường thấy là:

```text
SLF4J call
   -> Logback event
   -> Appender
   -> Encoder (có thể dùng Layout)
   -> Byte stream / log destination
```

Một **layout** tạo biểu diễn có thể đọc được từ event; một **encoder** phụ trách mã hóa biểu diễn đó thành byte để appender ghi. Với Logback, `PatternLayoutEncoder` là lựa chọn phổ biến cho text vì nó kết hợp pattern layout với chức năng encoder. Đừng nhầm `java.util.logging.Formatter` với interface/class của Logback; chúng thuộc các hệ sinh thái khác nhau.

### 5.1. Pattern layout

Pattern quyết định trường nào xuất hiện và theo thứ tự nào. Một số conversion word phổ biến trong Logback:

| Pattern | Ý nghĩa |
|---|---|
| `%d{yyyy-MM-dd HH:mm:ss.SSS}` | Thời gian theo mẫu |
| `%-5level` | Level căn trái, độ rộng tối thiểu 5 ký tự |
| `%thread` hoặc `%t` | Tên thread |
| `%logger{36}` | Tên logger, có thể rút gọn đến độ dài mục tiêu |
| `%msg` hoặc `%m` | Message đã định dạng |
| `%X{traceId}` | Giá trị MDC có khóa `traceId`, nếu đã được gán |
| `%ex` | Thông tin throwable/stack trace |
| `%n` | Ký tự xuống dòng phù hợp nền tảng |

Đây là các ký hiệu **của Logback**; không lấy nguyên pattern này đưa vào một `java.util.logging.Formatter`.

### 5.2. Cấu hình Logback mẫu

Khi ứng dụng **đã có Logback trên classpath**, có thể đặt file `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} traceId=%X{traceId} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

File này là **cấu hình framework**, không phải chương trình Java độc lập và không thể chạy chỉ bằng lệnh `javac`. Nó điều khiển định dạng text cho appender console:

- `%d` cho thời gian; hãy quy định timezone khi cần so sánh nhiều server, nếu không sẽ phụ thuộc cấu hình thời gian của môi trường/backend.
- `%-5level` giúp cột level dễ quét bằng mắt.
- `%X{traceId}` đọc MDC, **không tự sinh ra trace ID**. Nếu chưa gán hoặc chưa truyền MDC sang luồng bất đồng bộ thì phần này có thể trống.
- `%msg%n` xuất thông điệp và kết thúc dòng.
- `%ex` cho phép in throwable khi có; stack trace có thể gồm nhiều dòng và cần cơ chế gom dòng ở collector.

Để dùng MDC một cách có trách nhiệm, ứng dụng cần thêm giá trị vào đúng phạm vi xử lý và dọn ngữ cảnh sau khi hoàn tất. Một request trên thread pool không được phép “thừa hưởng” nhầm định danh của request trước.

### 5.3. Log4j 2 có Layout nhưng cách cấu hình riêng

Với Log4j 2, appender thường dùng `PatternLayout` hoặc layout dữ liệu có cấu trúc. Dù một số placeholder tương tự Logback (`%d`, `%p`, `%m`, `%n`, `%X`), **không giả định mọi ký hiệu, option hay file cấu hình đều tương thích một-một**. Log4j 2 có định nghĩa và cách đăng ký layout riêng. Cần đọc tài liệu đúng phiên bản backend trước khi sao chép cấu hình giữa Logback và Log4j 2.

SLF4J chỉ đóng vai trò API/facade ở phía ứng dụng; thay provider/backend có thể làm thay đổi hoàn toàn kiểu appender và formatter/layout được hỗ trợ.

## 6. Định dạng text, pattern và structured logging

### 6.1. Text hoặc pattern: dành cho người đọc

Một layout text nhất quán có thể tạo:

```text
2026-11-09 15:15:03.125 INFO  [http-17] OrderService traceId=trace-7 - Order accepted
```

Ưu điểm: dễ đọc trực tiếp khi phát triển hoặc dùng `tail`. Hạn chế: parser có thể phải dựa vào dấu cách, dấu `|`, regex hoặc quy tắc escape; thông điệp chứa xuống dòng/ký tự đặc biệt dễ làm sai cấu trúc.

### 6.2. JSON: dành cho máy phân tích

Một JSON encoder/layout có thể xuất một object cho mỗi event:

```json
{"timestamp":"2026-11-09T08:15:03.125Z","level":"INFO","logger":"OrderService","thread":"http-17","traceId":"trace-7","event":"order_accepted","orderId":"ORD-7","message":"Order accepted"}
```

Đây là **đầu ra minh họa**, không phải định dạng tự động của JUL hay của mọi bản Logback/Log4j 2.

JSON có lợi thế là các trường có tên rõ ràng, dễ lọc, gom nhóm và thống kê. Nhưng JSON chỉ thật sự hữu ích khi:

- Giữ **schema nhất quán** (ví dụ `timestamp`, `level`, `logger`, `traceId`); thống nhất kiểu dữ liệu và format thời gian.
- Escape đúng dấu ngoặc kép, dấu gạch chéo ngược, control characters và xuống dòng; dùng encoder/serializer tin cậy, tránh tự nối JSON.
- Định nghĩa cách biểu diễn `Throwable`, stack trace, exception type, thông điệp và stack của nested cause.
- Quản lý trường tùy biến để tránh trùng khóa, dữ liệu quá lớn hoặc nhét đối tượng không cần thiết vào log.
- Chọn chính sách thời gian và Unicode rõ ràng, thường ISO 8601 với UTC và UTF-8.

**Định dạng có cấu trúc không tương đương với lưu trữ đáng tin cậy**. Collector vẫn có thể mất sự kiện, chậm ghi, giới hạn kích thước hoặc áp dụng chính sách giữ dữ liệu.

### 6.3. Phân biệt message template với chuỗi đã render

Trước định dạng, lời gọi log có thể chứa **message template + parameters**, ví dụ `"order {0} submitted"` và `"ORD-7"` ở JUL hoặc placeholder `{}` trong một số API khác. Khi render, formatter tạo text cụ thể. Structured logging có thể giữ cả template, tham số và trường có tên nếu backend hỗ trợ.

Không nên giả định `{}` của SLF4J hoạt động trong `java.util.logging.Formatter.formatMessage`: JUL thường dùng cú pháp tham số tương thích `MessageFormat` như `{0}`. Cú pháp thuộc API, không phải một đặc tả chung cho mọi thư viện logging.

## 7. Thiết kế formatter/layout an toàn và hữu ích

### 7.1. Giữ schema ổn định, đủ ngữ cảnh

Chọn trường theo nhu cầu điều tra thật: thời điểm, level, logger, thông điệp, exception, định danh request/trace và một vài khóa nghiệp vụ cần thiết. Không cố đưa toàn bộ trạng thái chương trình vào mỗi record.

Nếu nhiều service cùng gửi vào một collector, thống nhất tên khóa và timezone. Chẳng hạn service A dùng `requestId` còn service B dùng `request_id` mà không có quy tắc chuyển đổi sẽ làm việc truy vấn khó hơn.

### 7.2. Bảo vệ dữ liệu và chống log injection

Thông điệp, tham số hoặc exception có thể chứa dữ liệu bên ngoài. Khi đưa vào log text, ký tự xuống dòng hoặc control characters có thể tạo cảm giác một dòng input là nhiều sự kiện khác nhau. Hãy escape hoặc chuẩn hóa chúng khi cần và dùng JSON encoder có escape đúng chuẩn nếu xuất JSON.

Tuy nhiên, chỉ thay format **không bảo đảm bí mật được che giấu**. Không ghi access token, mật khẩu, dữ liệu thẻ, khóa truy cập hoặc thông tin cá nhân không cần thiết ngay từ nguồn. Nếu có masking/redaction, phải kiểm chứng cả message, tham số, MDC và exception.

### 7.3. Bảo toàn exception và khả năng liên kết

Mỗi exception có thể gồm class, message, stack trace, cause chain và suppressed exceptions. Một layout chỉ xuất `error.getMessage()` sẽ bỏ mất nhiều bằng chứng. Cần quyết định khi nào ghi stack trace đầy đủ, khi nào chỉ ghi summary, và tránh ghi lặp cùng lỗi ở mọi tầng.

Trong hệ thống bất đồng bộ, phải chắc chắn dữ liệu context như MDC đã được chụp/di chuyển đúng trước khi thread gốc kết thúc hoặc dọn context. Formatter chỉ đọc những gì sự kiện đang có; nó không tự khôi phục các trường đã mất khi chuyển luồng.

### 7.4. Kiểm soát hiệu năng

Định dạng timestamp, stack trace, JSON serialization và đối tượng lớn đều tốn CPU/bộ nhớ. Chỉ xử lý đầy đủ các event thật sự được chọn để ghi; dùng API message template hoặc lazy evaluation khi phù hợp.

Đừng đưa thao tác mạng, truy vấn cơ sở dữ liệu hay tính toán phức tạp vào `Formatter.format`. Thành phần định dạng có thể được gọi rất thường xuyên, kể cả khi ứng dụng chịu tải cao. Với log bất đồng bộ, cách tổ chức hàng đợi và thời điểm snapshot dữ liệu còn tác động đến tính nhất quán.

### 7.5. Xuống dòng và thời gian

- **Newline:** thiếu `%n` hoặc `System.lineSeparator()` có thể khiến các event dính vào nhau. Một exception nhiều dòng cần collector hỗ trợ multiline hoặc xuất thành một event có cấu trúc.
- **Timestamp:** xác định timestamp đo tại thời điểm sự kiện hay thời điểm backend thực sự ghi. Nếu queue chờ lâu, hai thời điểm khác nhau.
- **Timezone:** ưu tiên UTC hoặc ghi offset rõ; không so sánh ngày giờ địa phương không có timezone giữa các máy.
- **Độ phân giải:** không bịa độ chính xác micro/nanosecond nếu dữ liệu và backend chỉ cung cấp độ chính xác thấp hơn.

## 8. Các lỗi thường gặp khi cấu hình tầng định dạng

| Dấu hiệu | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Log xuất theo format mặc định | File cấu hình không được nạp hoặc appender/handler chưa gắn layout mong muốn | Kiểm tra backend thực tế, file cấu hình được nạp và handler đang nhận event |
| Có `{0}` chưa thay tham số ở JUL | Formatter dùng `getMessage()` hoặc sự kiện không có parameters | Dùng `formatMessage(record)`, kiểm tra cách gọi logger |
| `traceId` trống | MDC không được gán/truyền hoặc tên khóa không khớp | Kiểm tra ngữ cảnh trong cùng luồng và lúc tạo event |
| Không thấy stack trace | Formatter bỏ `getThrown()`, layout không xuất throwable hoặc exception chưa được truyền | Xác nhận cách gọi logger và cấu hình throwable converter |
| Các dòng log dính nhau | Quên ký tự kết thúc dòng | Dùng `%n` hoặc `System.lineSeparator()` phù hợp |
| Log trùng lặp | Event đi qua nhiều handler/appender hoặc cộng dồn tới logger cha | Kiểm tra cấu hình handler, appender và tính kế thừa/additivity |
| Dòng JSON không parse được | Tự nối chuỗi sai escape hoặc trộn text ngoài JSON | Dùng serializer/encoder chuẩn và kiểm tra đầu ra bằng JSON parser |
| Thời gian lệch nhau | Timezone/cấu hình timestamp không thống nhất hoặc đồng hồ lệch | Ghi UTC/offset rõ và đối chiếu đồng bộ đồng hồ |

Không sửa “thiếu log” bằng cách thay formatter ngay lập tức: trước tiên kiểm tra logger có phát event hay không, level/filter có bỏ event không và appender/handler có đang ghi đúng đích không. Nếu **sự kiện không đến được tầng định dạng**, layout đẹp đến đâu cũng không thể xuất nó.

## 9. Checklist tự kiểm tra sau khi thay formatter/layout

1. **Đủ event:** log ở level được bật có xuất hiện, không trùng, không thay đổi hành vi nghiệp vụ.
2. **Đúng nội dung:** message template được render như mong đợi; dữ liệu ngoại lệ và ngữ cảnh quan trọng không bị rơi.
3. **Đúng cấu trúc:** mỗi event phân tách rõ; JSON parse được; parser/collector nhận đúng trường và kiểu dữ liệu.
4. **Đúng thời gian:** timezone, offset và độ chính xác thống nhất giữa các service.
5. **Đúng an toàn:** không lộ secret, không cho phép input phá cấu trúc hoặc giả mạo bản ghi.
6. **Đúng hiệu năng:** định dạng chịu được tải dự kiến, không tạo quá nhiều dữ liệu hoặc xử lý tốn kém vô ích.
7. **Đúng vận hành:** đích ghi, rotation, retention, quyền truy cập và cơ chế thu thập được kiểm tra ở **tầng output**, thay vì giả định layout tự giải quyết.

Formatter/layout là **tầng trình bày của log event**. Một logger có thể phát cùng loại sự kiện trong nhiều môi trường; nhờ tách tầng định dạng, ứng dụng có thể chọn text dễ đọc lúc phát triển và cấu trúc ổn định để thu thập tập trung khi vận hành, trong khi phần mã phát sự kiện vẫn nhất quán.
