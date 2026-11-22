# Layout là gì trong Java Logging?

**Layout** là thành phần quyết định **một sự kiện log được biểu diễn như thế nào khi xuất ra ngoài**. Khi ứng dụng ghi `logger.info("Order {} accepted", orderId)`, hệ thống logging thường có một sự kiện chứa level, thời điểm, tên logger, thread, message, exception và ngữ cảnh request. Layout chọn những dữ liệu nào được hiển thị, thứ tự, dấu phân cách và kiểu định dạng: một dòng văn bản dễ đọc, JSON có cấu trúc, hoặc một biểu diễn khác.

Layout **không phải nơi quyết định thao tác nghiệp vụ có thành công hay không**, cũng không phải nơi quyết định chính một event có cần được tạo. Level và filter tham gia chọn event, appender/handler quyết định đích ghi; layout biến event thành nội dung để gửi đến đích đó. Trong Java, tên API cụ thể khác nhau: **JUL dùng `Formatter`**, **Logback có `Layout` kết hợp `Encoder`**, còn **Log4j 2 có `Layout`** được cấu hình bên trong appender. Ba hệ sinh thái có mục đích tương tự nhưng không dùng cùng một class hay cú pháp cấu hình.

## 1. Bức tranh tổng thể: từ lời gọi logger đến một dòng log

```text
Java application
    |
    | logger.info("event=order.accepted orderId={}", orderId)
    v
Logger / logging API
    |
    +-- effective level, filter? --> Có thể bỏ qua
    |
    v
Logging event / LogRecord
    |  level, timestamp, logger, thread, message,
    |  Throwable, context (nếu có)
    v
Appender / Handler
    |  mức/filter của đích xuất
    v
Layout / Formatter / Encoder
    |  tạo text hoặc bytes theo định dạng
    v
stdout, stderr, file, collector hoặc sink khác
```

Sơ đồ mô tả trách nhiệm để học; thứ tự nội bộ của filter, layout và encoder phụ thuộc framework, không nên coi đây là thuật toán chính xác cho mọi implementation.

Ví dụ một sự kiện có thông tin:

```text
timestamp = 2026-03-05T08:20:10.123Z
level     = INFO
logger    = com.example.orders.OrderService
thread    = http-worker-2
event     = order.accepted
orderId   = ord-42
requestId = req-17
```

Một **text layout** có thể biến event thành:

```text
2026-03-05T08:20:10.123Z INFO [http-worker-2] OrderService requestId=req-17 - event=order.accepted orderId=ord-42
```

Một **JSON layout** có thể biểu diễn cùng ý nghĩa như sau:

```json
{"timestamp":"2026-03-05T08:20:10.123Z","level":"INFO","logger":"com.example.orders.OrderService","thread":"http-worker-2","requestId":"req-17","event":"order.accepted","orderId":"ord-42"}
```

Đây là **dữ liệu minh họa tĩnh**, không phải output của một chương trình bên dưới. Nội dung event và những field thực sự xuất hiện phụ thuộc API, logging backend, layout/encoder và việc ứng dụng có gắn context/structured attributes đúng cách hay không. Đổi layout không tự biến chuỗi message chứa `orderId=...` thành một JSON field `orderId`.

## 2. Phân biệt Layout, Formatter, Encoder, Appender và Logger

| Thành phần | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| **Logger** | Sự kiện từ thành phần nào, có vượt ngưỡng ghi không? | `com.example.orders.OrderService` |
| **Log event / LogRecord** | Event chứa dữ liệu gì? | `INFO`, message, `Throwable`, timestamp, context |
| **Filter** | Event nào được chấp nhận hoặc từ chối? | Chỉ nhận từ `WARN` trở lên ở một đích |
| **Layout** | Bản ghi được trình bày theo cấu trúc nào? | `%d %-5level %logger - %msg%n` |
| **Formatter** | Định dạng record ra chuỗi theo API JUL. | `java.util.logging.SimpleFormatter` |
| **Encoder** | Chuyển biểu diễn của event thành byte để appender xuất. | `PatternLayoutEncoder` trong Logback |
| **Appender / Handler** | Đưa nội dung ra đâu, quản lý I/O và vòng đời thế nào? | Console, file, rolling file |
| **Collector** | Thu, lưu, gắn nhãn hoặc chuyển tiếp dữ liệu từ ứng dụng. | Agent nhận stdout/file hoặc hệ thống tập trung |

Một appender có thể dùng layout để ghi console hoặc file; **cùng một event** có thể được gửi đến hai appender với **hai layout khác nhau**. Ví dụ console dùng format dễ đọc, file dùng structured JSON cho hệ thống tìm kiếm. Khi không cần fan-out, chỉ cấu hình một sink để tránh thêm I/O và dữ liệu trùng.

**Layout không đồng nghĩa severity.** Nếu event được đánh `INFO`, thay pattern không biến nó thành sự kiện `ERROR`; layout chỉ hiển thị nội dung. **Layout cũng không đồng nghĩa retention/rotation.** Ghi ra JSON không tự giới hạn kích thước file; chính sách lưu trữ thuộc appender và hạ tầng.

## 3. Layout là một phép chuyển dữ liệu có đầu vào và đầu ra

Có thể hình dung:

```text
format(loggingEvent, configuration) -> rendered representation
```

Đầu vào có thể gồm:

- **Level**: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR` (theo framework), hoặc `FINE`, `INFO`, `WARNING`, `SEVERE` trong JUL.
- **Thời điểm**: timestamp sự kiện; cần nhất quán timezone và độ chính xác.
- **Nguồn**: logger name, class, method nếu có metadata và collector tương ứng.
- **Thread**: tên hoặc ID luồng, hữu ích khi chẩn đoán concurrency.
- **Message**: mẫu thông điệp và các tham số đã được format phù hợp với API.
- **Throwable**: stack trace, cause, suppressed exception khi framework lưu và layout thể hiện chúng.
- **Context/attributes**: `requestId`, `traceId`, `spanId`, `tenantId`, `eventName`... khi được gắn đúng cách.
- **Marker/metadata phụ**: tùy thư viện và bản cấu hình.

Đầu ra có thể là một dòng text, một đối tượng JSON trên mỗi dòng, XML hoặc bytes của một định dạng khác. Chọn kiểu nào phải xét đích thu thập log và nhu cầu của người đọc.

### Text layout

Ưu điểm: dễ đọc bằng terminal, `grep`, debug trên máy cá nhân. Nhược điểm: dấu phân cách có thể mơ hồ, message có ký tự xuống dòng làm nhiều dòng, khó truy vấn field độc lập.

### Structured layout

Ưu điểm: collector có thể parse theo field `level`, `requestId` hoặc `durationMs`; dễ dựng dashboard và alert dựa trên thuộc tính ổn định. Nhược điểm: cần schema, encoder phù hợp, cách xử lý dữ liệu động và chính sách dữ liệu nhạy cảm; JSON không tự giải quyết mọi vấn đề vận hành.

### XML hoặc biểu diễn khác

Một số hệ sinh thái có formatter/XML output. Ví dụ `java.util.logging.XMLFormatter` của JUL xuất XML theo thiết kế của nó. XML không phải “sai”, nhưng phải khớp với công cụ phân tích và mục tiêu vận hành, tương tự JSON hoặc text.

## 4. Pattern layout: hiểu các placeholder

Trong Logback và Log4j 2, **PatternLayout** dùng các conversion pattern để tạo một chuỗi text theo khuôn mẫu. Ví dụ khái niệm:

```text
%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n
```

Trong các pattern phổ biến, ý nghĩa thường là:

| Pattern | Ý nghĩa | Ví dụ nội dung |
| --- | --- | --- |
| `%d{...}` | Thời gian theo format được cấu hình. | `2026-03-05 08:20:10.123` |
| `%level` hoặc `%p` | Level của event. | `INFO` |
| `%-5level` | Level căn trái tối thiểu năm ký tự. | `INFO ` |
| `%thread` hoặc `%t` | Thread phát event. | `http-worker-2` |
| `%logger` hoặc `%c` | Tên logger. | `com.example.orders.OrderService` |
| `%logger{36}` | Tên logger rút gọn theo quy tắc framework khi cần. | Một tên ngắn để tiết kiệm cột hiển thị |
| `%msg` hoặc `%m` | Message đã format từ tham số. | `Order ord-42 accepted` |
| `%n` | Ký tự xuống dòng theo nền tảng. | Kết thúc record |
| `%ex` / `%exception` | Thông tin `Throwable` nếu có. | Stack trace và chuỗi nguyên nhân |
| `%X{requestId}` | Trường `requestId` từ MDC/ThreadContext nếu có. | `req-17` |

**Lưu ý:** Chi tiết pattern, tên converter và cú pháp option khác nhau theo backend/phiên bản. Đừng sao chép nguyên pattern Logback sang JUL hoặc giả định mọi converter Log4j 2 đều được Logback hỗ trợ. Ví dụ `{0}` trong JUL là placeholder **message parameter**, không phải pattern converter cho layout.

Một pattern dùng nhiều field thường phù hợp hơn chỉ ghi `%msg%n`. Tuy nhiên, chỉ thêm `%X{requestId}` không tạo ra request ID; ứng dụng hoặc middleware phải gắn context trước khi phát event.

## 5. Layout cho stack trace và ngoại lệ

Khi xảy ra lỗi, message `"Save failed"` không cho biết tầng nào ném exception. Nếu API ghi log nhận đúng `Throwable`, layout/formatter phù hợp có thể đưa stack trace, cause và suppressed exception vào output.

Ví dụ sử dụng SLF4J trong ngữ cảnh đã có `LOG`, `orderId` và `ex`:

```java
LOG.error("event=order.save_failed orderId={}", orderId, ex);
```

Mã trên là **đoạn minh họa**, không phải chương trình độc lập. `ex` phải được truyền dưới dạng `Throwable` theo overload/quy tắc của API, không chỉ ghép `ex.getMessage()` vào chuỗi.

Nếu layout chỉ xuất message mà không đưa thông tin thrown (hoặc một pipeline phía sau cắt bỏ trường exception), dữ liệu điều tra có thể mất. Ngược lại, một số layout của backend tự thêm exception theo quy tắc mặc định ngay cả khi pattern không viết rõ conversion exception; vì vậy **luôn kiểm tra output thực tế theo đúng version**.

### Dòng log nhiều dòng và parser

Stack trace text thường trải qua nhiều dòng. Điều này dễ đọc trong console nhưng collector “mỗi dòng là một event” có thể tách một exception thành nhiều record giả. Có thể dùng structured layout để đặt stack trace trong một trường hoặc cấu hình multiline parser của collector. Không xóa stack trace của lỗi quan trọng chỉ để giữ một dòng; cần thiết kế ingestion phù hợp.

### Chọn mức log và format độc lập

Một lỗi input được từ chối theo hợp đồng có thể không cần `ERROR` hay stack trace; thất bại giao dịch không phục hồi được thường cần event mức cao hơn và context đủ điều tra. Layout không phải nơi thay đổi ý nghĩa nghiệp vụ của level.

## 6. JUL dùng Formatter thay vì Layout

Thư viện chuẩn `java.util.logging` đi theo mô hình:

```text
java.util.logging.Logger
    -> LogRecord
    -> Handler (ConsoleHandler / FileHandler / StreamHandler)
    -> Formatter
    -> output
```

Các formatter có sẵn:

- `SimpleFormatter`: xuất text theo cấu hình `java.util.logging.SimpleFormatter.format`; thường có timestamp, source, level, message, exception.
- `XMLFormatter`: xuất XML theo định dạng JUL.
- `Formatter` tùy chỉnh: override `format(LogRecord)` để tạo text theo yêu cầu, có thể gọi `formatMessage(record)` để xử lý parameters và resource bundle.

Ví dụ minh họa JUL trong một method:

```java
java.util.logging.ConsoleHandler console =
        new java.util.logging.ConsoleHandler();
console.setFormatter(new java.util.logging.SimpleFormatter());

java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("demo.checkout");
logger.addHandler(console);
```

Đây là **đoạn minh họa**, chưa gồm quản lý level, parent handlers và lifecycle. `ConsoleHandler` trong JUL thường xuất qua stderr; không mặc định ghi stdout. `FileHandler` trong JUL thường có formatter mặc định XML, vì vậy một file `.log` không chắc đã chứa các dòng text đơn giản.

### Đổi SimpleFormatter bằng thuộc tính cấu hình

JUL hỗ trợ định nghĩa pattern `printf` cho `SimpleFormatter` qua thuộc tính hệ thống hoặc `logging.properties`. Ví dụ:

```properties
java.util.logging.SimpleFormatter.format=%4$s | %5$s%6$s%n
```

Trong format của `SimpleFormatter`, `%4$s` là level, `%5$s` là message, `%6$s` là thông tin throwable được formatter đưa vào khi có. **Đây là cú pháp `String.format` của JUL**, không phải `%level`/`%msg` của Logback.

Không dùng cú pháp `%-5level` của Logback để cấu hình `SimpleFormatter.format` vì hai cơ chế xử lý khác nhau. Hơn nữa, `SimpleFormatter` format được đọc và diễn giải theo cấu hình của JVM; nếu ứng dụng có framework logging khác, thuộc tính JUL không tự thay đổi Logback/Log4j 2.

## 7. Ví dụ Java 17 chạy độc lập: cùng một event, hai formatter

Chương trình sau chỉ dùng JDK 17 (không cần Maven). Nó tạo hai `StreamHandler` cho **cùng một logger**. Một handler dùng text formatter, handler kia dùng formatter JSON minh họa. Hai handler ghi vào hai `ByteArrayOutputStream` khác nhau để kiểm tra đầu ra mà không cần tệp; chương trình in kết quả sau khi flush. Cùng một event được biểu diễn hai cách.

**Lưu thành `LayoutDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LayoutDemo {
    private static String escapeJson(String value) {
        StringBuilder out = new StringBuilder();
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
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        ByteArrayOutputStream textBytes = new ByteArrayOutputStream();
        ByteArrayOutputStream jsonBytes = new ByteArrayOutputStream();

        Handler textHandler = new StreamHandler(
                textBytes,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName()
                                + " | " + record.getLoggerName()
                                + " | " + formatMessage(record) + "\n";
                    }
                }
        );

        Handler jsonHandler = new StreamHandler(
                jsonBytes,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return "{\"level\":\""
                                + escapeJson(record.getLevel().getName())
                                + "\",\"logger\":\""
                                + escapeJson(record.getLoggerName())
                                + "\",\"message\":\""
                                + escapeJson(formatMessage(record))
                                + "\"}\n";
                    }
                }
        );

        textHandler.setLevel(Level.INFO);
        jsonHandler.setLevel(Level.INFO);
        logger.addHandler(textHandler);
        logger.addHandler(jsonHandler);

        try {
            logger.fine("event=debug.filtered");
            logger.log(
                    Level.INFO,
                    "event=checkout.completed orderId={0}",
                    "ord-42"
            );
        } finally {
            logger.removeHandler(textHandler);
            logger.removeHandler(jsonHandler);
            textHandler.close();
            jsonHandler.close();
        }

        System.out.print("TEXT\n");
        System.out.print(textBytes.toString(StandardCharsets.UTF_8));
        System.out.print("JSON\n");
        System.out.print(jsonBytes.toString(StandardCharsets.UTF_8));
    }
}
```

Biên dịch và chạy:

```bash
javac LayoutDemo.java
java LayoutDemo
```

**Standard output chính xác** khi chạy thành công:

```text
TEXT
INFO | demo.checkout | event=checkout.completed orderId=ord-42
JSON
{"level":"INFO","logger":"demo.checkout","message":"event=checkout.completed orderId=ord-42"}
```

### Giải thích từng bước

1. `logger.setLevel(Level.INFO)` khiến event `FINE` bị loại; không có dòng `event=debug.filtered`.
2. Logger có **hai handler**, mỗi handler có formatter riêng, nên **một event INFO** được định dạng thành hai output độc lập.
3. `Formatter.formatMessage(record)` dùng quy ước placeholder `{0}` của JUL để thay bằng `ord-42`. Trong SLF4J/Log4j2, code thường dùng `{}` thay cho `{0}`.
4. Hai formatter chọn cùng ba thông tin: level, logger, message; text dùng ` | `, JSON dùng object với các key cố định. Chính layout/formatter làm thay đổi biểu diễn, không thay đổi level hay message gốc.
5. Hai `StreamHandler` viết vào `ByteArrayOutputStream` nên chương trình có thể đóng handler và đọc byte bằng UTF-8 trước khi in ra stdout. Không có timestamp/thread nên kết quả ổn định.
6. `logger.setUseParentHandlers(false)` ngăn bản ghi tiếp tục đến handler của logger cha và gây output ngoài dự kiến.
7. Hàm `escapeJson` chỉ phục vụ giảng dạy: xử lý các ký tự JSON thường gây lỗi như dấu ngoặc kép, backslash, newline và control characters. Trong production, dùng thư viện JSON/structured layout chuẩn, không duy trì serializer tự viết.
8. Chương trình không nhằm chứng minh `JUL có class mang tên Layout`. Trong JUL, chúng ta tự tạo **Formatter**, là thành phần tương đương về mục đích biểu diễn record.

Trong sản phẩm thật, không tạo handler mới cho mỗi request như ví dụ học tập. Đặt cấu hình handler/formatter ở bước khởi động, theo vòng đời ứng dụng, và quản lý shutdown cùng tài nguyên.

## 8. Logback: Layout và Encoder phối hợp ra sao?

**Logback Classic** thường nhận lời gọi từ **SLF4J** và dùng appender cùng encoder để ghi dữ liệu. Trong Logback, `PatternLayout` định dạng event ra chuỗi; `PatternLayoutEncoder` cung cấp đường từ layout kiểu pattern đến bytes cho các appender. Vì thế các ví dụ phổ biến cấu hình `<encoder>` thay vì gắn trực tiếp `<layout>` vào `FileAppender`.

Ví dụ `src/main/resources/logback.xml` hoàn chỉnh, dành cho ứng dụng dùng SLF4J với Logback provider:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level
                [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

XML ở trên được chia nhiều dòng cho dễ đọc, nhưng **khoảng trắng và xuống dòng trong phần `<pattern>` có thể ảnh hưởng output tùy cách parser xử lý**. Trong mã thực tế, nên giữ pattern trên **một dòng** để tránh tạo khoảng trắng ngoài ý muốn, ví dụ:

```xml
<pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
```

Nếu muốn cùng một event có layout khác nhau ở console và file, khai báo hai appender, mỗi appender có encoder riêng, rồi tham chiếu cả hai dưới root/LoggerConfig. **Đừng gắn cùng appender ở logger con và root đồng thời để tránh log trùng do additivity**.

### Logback không đồng nghĩa SLF4J

`slf4j-api` là facade; Logback Classic là một provider/backend. Trong code ứng dụng thường gọi:

```java
// Đoạn minh họa trong class OrderService, cần SLF4J dependency.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

void accept(String orderId) {
    LOG.info("event=order.accepted orderId={}", orderId);
}
```

Nếu runtime chọn backend khác (ví dụ Log4j2 provider cho SLF4J), file `logback.xml` không tự điều khiển backend đó. Muốn layout có tác dụng, phải xác nhận provider, phiên bản, file cấu hình đang được nạp và sink đang nhận log.

### Structured JSON với Logback

Một `PatternLayoutEncoder` xuất text pattern, không tự biến dữ liệu thành JSON field. Muốn JSON ổn định cho collector cần encoder/layout JSON tương thích với phiên bản Logback và dependencies đã chọn, mapping field rõ ràng và escaping hợp lệ. Cần kiểm tra stack trace, MDC, timestamp, schema và kích thước record ở output thực tế.

Không coi một pattern kiểu `{"message":"%msg"}` là JSON an toàn: message có dấu `"`, `\\` hoặc xuống dòng có thể làm sai JSON nếu không được escape đúng cách.

## 9. Log4j 2: Layout nằm trong Appender

Log4j 2 Core có các layout như `PatternLayout` và, khi có module cần thiết, `JsonTemplateLayout`. Một cấu hình console với PatternLayout (ứng dụng dùng Log4j2 API/Core) có thể là:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5level [%t] %c - %m%ex%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="STDOUT"/>
        </Root>
    </Loggers>
</Configuration>
```

Lưu trong `src/main/resources/log4j2.xml` để Log4j2 Core tìm thấy trên classpath theo cấu hình thông thường. `Logger` trong mã sử dụng `org.apache.logging.log4j.LogManager` và phương thức `logger.info(...)` tương ứng. Nếu runtime đang dùng Logback làm backend, cấu hình `log4j2.xml` không tự áp dụng.

Trong Log4j2, muốn file và console có layout khác nhau có thể khai báo đồng thời `Console` và `RollingFile` với các `PatternLayout` riêng, sau đó gắn bằng `AppenderRef`. Level và filter ở logger/ref/appender quyết định event đến sink nào; layout chỉ làm phần trình bày.

### Structured JSON với JsonTemplateLayout

Log4j2 có module template JSON layout (ví dụ `log4j-layout-template-json` trong các phiên bản tương ứng), không nhất thiết nằm sẵn trong `log4j-core`. Cấu hình và schema event-template cần chọn theo tài liệu version sử dụng. Kết quả là các JSON records có key rõ ràng, thích hợp ingestion khi collector được cấu hình đúng.

**JSON layout không có nghĩa mọi giá trị đã là field riêng.** Chẳng hạn một message text `"event=order.accepted orderId=42"` có thể vẫn nằm trong trường `message` duy nhất. Để `orderId` thành một thuộc tính riêng, ứng dụng phải phát structured data hoặc context phù hợp và cấu hình template/encoder đưa field đó vào JSON.

## 10. Layout và dữ liệu ngữ cảnh: MDC, ThreadContext, trace ID

Các thông tin như `requestId`, `traceId` và `spanId` giúp nối log giữa nhiều lớp và service. Chúng không nên nằm trong tên logger hoặc bị sao chép ngẫu nhiên vào mọi chuỗi message nếu framework có context API phù hợp.

Với **SLF4J**, ngữ cảnh có thể được gắn bằng MDC:

```java
// Đoạn minh họa trong method; LOG và requestId đã có.
org.slf4j.MDC.put("requestId", requestId);
try {
    LOG.info("event=order.accepted orderId={}", "ord-42");
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

Trong PatternLayout của Logback có thể dùng `%X{requestId}` để in giá trị. Với **Log4j2**, API tương ứng thường là `ThreadContext.put(...)`, và pattern `%X{requestId}` có thể lấy context map theo cấu hình.

**Không mặc định context tự truyền qua mọi luồng.** `ExecutorService`, `CompletableFuture`, reactive pipelines và virtual threads có thể thay đổi ngữ cảnh thực thi. Cần propagation thích hợp và phải dọn context ở `finally`/scope để tránh log của request trước lẫn với request sau.

Với tracing, nên thống nhất tên field giữa các service, ví dụ `traceId`, `spanId`, `service`, `environment`. Layout có thể hiển thị những field này nhưng **không tự tạo trace ID**; instrument/middleware hoặc code phải cung cấp dữ liệu trước.

## 11. Text layout hay JSON layout: chọn thế nào?

| Tiêu chí | Text/PatternLayout | JSON/structured layout |
| --- | --- | --- |
| Đọc trực tiếp trên terminal | Thường dễ và gọn. | Dài hơn, đôi khi cần formatter để xem. |
| Tìm theo từ khóa | Dễ cho `grep` đơn giản. | Có thể tìm text nhưng giá trị chính nằm ở truy vấn field. |
| Phân tích theo trường | Phụ thuộc pattern/parser; có thể mơ hồ. | Tốt nếu field được định nghĩa và collector parse chuẩn. |
| Escaping | Có thể gặp multiline và log injection. | JSON encoder chuẩn có escaping, nhưng schema vẫn phải được kiểm soát. |
| Exception | Text stack trace dễ đọc nhưng nhiều dòng. | Có thể chứa trường stack trace hoặc cause, tùy layout. |
| Dữ liệu thiếu | Field vắng mặt có thể làm pattern rỗng. | Có thể chọn bỏ field hoặc đặt `null`, tùy schema. |
| Khả năng tương thích | Phụ thuộc pattern và parser downstream. | Phụ thuộc schema, version template và downstream consumer. |
| Dung lượng/CPU | Thường gọn, nhưng tùy pattern. | Có thể nhiều byte hơn do key và escaping; cần benchmark. |

**Chọn theo mục tiêu vận hành**, không phải chỉ theo hình thức. Một CLI có thể phù hợp text; ứng dụng phân tán có observability platform thường hưởng lợi từ structured logging. Cũng có thể dùng **hai layout khác nhau cho hai appender** khi cần, nhưng phải cân nhắc I/O, chi phí và việc trùng dữ liệu.

### Một record JSON trên một dòng

Nhiều hệ thống ingest theo NDJSON: mỗi dòng là **một object JSON hoàn chỉnh**. Nếu serializer có newline chưa được escape hoặc có nhiều object trên một dòng, parsing có thể thất bại. Hãy kiểm tra đầu ra thật bằng parser JSON, không chỉ nhìn phần mở rộng file.

## 12. Thiết kế layout có giá trị vận hành

Một layout tốt nên trả lời nhanh các câu hỏi:

1. **Khi nào?** Timestamp có timezone/offset, độ chính xác phù hợp và nhất quán giữa service.
2. **Ở đâu?** Service, môi trường, tên logger, instance/pod nếu cần.
3. **Mức độ?** Level thể hiện ảnh hưởng của event, không dùng ERROR cho hoạt động bình thường.
4. **Sự kiện gì?** `eventName` hoặc mã sự kiện ổn định; message rõ hành động và kết quả.
5. **Liên quan request nào?** `requestId` hoặc `traceId/spanId` được truyền qua luồng xử lý.
6. **Đối tượng nào?** Các ID có giá trị chẩn đoán, không lộ thông tin không được phép.
7. **Kết quả ra sao?** `outcome`, `errorCode`, `attempt`, `durationMs` với đơn vị nhất quán.
8. **Tại sao thất bại?** Throwable/stack trace/cause được giữ đúng trong sự kiện lỗi thực sự.
9. **Đường đi nào?** Collector có thể parse output mà không phải suy đoán từ chuỗi text.

Ví dụ một structured event hữu ích (dữ liệu minh họa):

```json
{
  "timestamp": "2026-03-05T08:20:10.123Z",
  "level": "INFO",
  "service": "checkout-service",
  "logger": "com.example.checkout.CheckoutService",
  "eventName": "checkout.completed",
  "requestId": "req-17",
  "orderId": "ord-42",
  "outcome": "success",
  "durationMs": 23
}
```

Event này có trường `durationMs` kiểu số và `eventName` riêng; nó không phải sản phẩm tự động của `PatternLayout` khi chỉ truyền một string message. Ứng dụng/backend phải tạo field thực và layout phải serialize đúng schema.

## 13. Lỗi thường gặp khi làm việc với layout

| Hiện tượng | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| Log không xuất hiện | Logger/handler/appender level hoặc filter loại record, không phải do layout. | Kiểm tra effective level, filter và sink trước khi sửa pattern. |
| Output thiếu logger/thread | Pattern không chứa converter tương ứng. | Thêm `%logger` / `%thread` hoặc field JSON theo schema. |
| Pattern converter in nguyên chữ hoặc báo lỗi | Dùng cú pháp của backend khác hoặc option không được hỗ trợ. | Xác nhận Logback, Log4j2 hay JUL và kiểm tra version/converter. |
| Có message nhưng thiếu stack trace | Chỉ log `ex.getMessage()` hoặc formatter không xuất throwable. | Truyền `Throwable` đúng API; kiểm tra layout và collector. |
| Stack trace bị chia thành nhiều event | In text nhiều dòng nhưng collector ingest mỗi dòng. | Cấu hình multiline parser hoặc structured exception field. |
| JSON không parse được | Tự ghép JSON text, escaping sai, hoặc nhiều bản ghi dính nhau. | Dùng JSON layout/encoder chuẩn, test parser và schema. |
| Field requestId luôn trống | Chưa gắn MDC/ThreadContext hoặc context không qua thread. | Đặt field trước khi log, propagate và dọn đúng scope. |
| Log bị lặp trên cùng sink | Gắn appender ở nhiều cấp logger và bật additivity. | Kiểm tra appender refs/parent handlers; không sửa layout để che triệu chứng. |
| Timezone không rõ | Chỉ ghi giờ địa phương không offset. | Chuẩn hóa UTC hoặc timestamp có timezone và lưu version schema. |
| Tệp .json vẫn chứa text | Chỉ đổi phần mở rộng, không đổi layout. | Cấu hình structured layout/encoder, xác minh từng record. |
| Collector không tìm thấy field `orderId` | `orderId` nằm trong message text chứ không phải JSON field. | Phát structured attributes và cấu hình schema để xuất field. |
| Mức log quá ồn sau khi thêm layout | Vấn đề level/tần suất, không phải định dạng. | Cấu hình level/metrics, sampling/rate limit khi phù hợp. |
| Lỗi encoding tiếng Việt | Encoding writer và reader không khớp. | Thống nhất UTF-8 trong appender/encoder và collector. |

## 14. Bảo mật, hiệu năng và khả năng tương thích

### Dữ liệu nhạy cảm

Layout có thể làm thông tin trở nên dễ tìm kiếm hơn, nhưng không tự phân loại dữ liệu an toàn. **Không ghi mật khẩu, token, session cookie, private key, toàn bộ payload cá nhân hoặc thông tin thanh toán không cần thiết** vào message, MDC hay exception. Stack trace và error message của thư viện cũng có thể chứa URL có query, tên file hoặc thông tin kết nối nhạy cảm.

Ưu tiên thiết kế nội dung log an toàn tại nơi phát sự kiện. Có thể bổ sung masking/redaction trong pipeline, nhưng không dùng masking như lý do cho phép dữ liệu bí mật vào mọi log thô. Hạn chế quyền truy cập, đặt retention và kiểm soát gửi log đến hệ thống bên thứ ba.

### Log injection và escaping

Nếu message lấy từ input người dùng chứa ký tự xuống dòng hoặc ký tự điều khiển, text layout có thể khiến **một sự kiện trông như nhiều sự kiện khác**. Structured encoder chuẩn thường escape JSON strings đúng quy tắc, nhưng vẫn cần giới hạn kích thước field, kiểm soát dữ liệu nguồn và cảnh giác với payload đặc biệt. Đừng dùng `String.replace` thủ công như một giải pháp đầy đủ cho structured logging production.

### Hiệu năng

Pattern phức tạp, việc lấy call-site/class/method ở runtime, serializing JSON, in stack trace dài và ghi nhiều appender đều có thể tạo CPU/I/O. Một số thông tin caller location tốn kém, đặc biệt trong logging bất đồng bộ; chỉ bật khi thực sự cần. Đừng giảm mọi log xuống chỉ có message để tối ưu nếu điều đó làm mất khả năng điều tra. Benchmark theo tải thật và chính sách retention.

### Tương thích

- Cấu hình JUL `SimpleFormatter.format` không giống pattern Logback/Log4j 2.
- Một số converter/JSON layout cần dependency hay phiên bản cụ thể.
- Framework như Spring Boot có thể cung cấp file cấu hình hoặc pattern mặc định riêng; xác nhận cấu hình active.
- Appender và encoder có thể không hỗ trợ mọi kiểu layout; chọn API phù hợp với backend và sink.
- Khi đổi schema JSON, lưu ý dashboard, alert, pipeline và saved queries có thể phụ thuộc tên trường trước đó.

## 15. Checklist trước khi triển khai

- [ ] Đã xác định backend thực tế: JUL, Logback hay Log4j2?
- [ ] Logger/appender nhận được đúng level và event chưa?
- [ ] Layout thể hiện đủ timestamp, level, logger, event, context và exception theo nhu cầu?
- [ ] Định dạng timestamp có timezone và độ chính xác nhất quán không?
- [ ] Nếu xuất JSON: mỗi record hợp lệ, schema rõ, field dữ liệu thật chứ không chỉ là message?
- [ ] Formatter/encoder đúng phiên bản và tương thích với appender/sink?
- [ ] MDC/ThreadContext được đặt, truyền qua luồng và dọn đúng lúc?
- [ ] Stack trace/cause không bị mất hoặc bị collector tách nhầm?
- [ ] Dữ liệu nhạy cảm và input nhiều dòng đã được kiểm soát?
- [ ] Encoding UTF-8, mức dung lượng và chi phí I/O đã được kiểm thử?
- [ ] Khi đổi layout, dashboard, alert, parser và ứng dụng đọc log đã được cập nhật?
- [ ] Đã chạy thử với event bình thường, event lỗi, ký tự tiếng Việt, dấu ngoặc kép, dấu xuống dòng và request ID vắng mặt?

**Kết luận:** **Layout là cách biểu diễn một sự kiện log**, không phải bộ phận quyết định tính nghiêm trọng hay đích lưu trữ. Trong JUL, vai trò này do **Formatter** đảm nhiệm; trong Logback, **Layout/Encoder** làm việc với Appender; trong Log4j2, **Layout** được gắn vào Appender. Chọn layout dựa trên nhu cầu đọc, truy vấn và vận hành; luôn kiểm chứng event và dữ liệu exception/context có thật trong output.