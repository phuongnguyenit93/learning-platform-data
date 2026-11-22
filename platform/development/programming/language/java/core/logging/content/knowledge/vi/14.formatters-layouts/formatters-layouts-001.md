# Formatter là gì? Vai trò của Formatter và Layout trong Java Logging

**Formatter** là thành phần chuyển một **sự kiện log** thành biểu diễn đầu ra dễ đọc hoặc dễ xử lý. Trong **Java Util Logging (JUL)**, formatter thường là một lớp kế thừa `java.util.logging.Formatter`, nhận `LogRecord` và trả về `String`. Trong các backend khác như **Logback** và **Log4j 2**, vai trò trình bày này thường mang tên **Layout** và kết hợp với **Encoder**.

Một bản ghi chứa nhiều dữ kiện: mức độ INFO/WARNING/SEVERE, mẫu thông điệp, tham số, tên logger, thời điểm, thông tin thread và có thể có `Throwable`. Formatter chọn **trường nào được in, thứ tự, định dạng timestamp, dấu phân cách, cách thoát ký tự và cách trình bày exception**.

Điều quan trọng nhất: **Formatter quyết định hình thức của bản ghi; Logger quyết định có phát log hay không, còn Handler/Appender quyết định lọc ở đích nào và ghi đi đâu.**

## 1. Vị trí của Formatter trong kiến trúc logging

Với JUL, đường đi điển hình:

~~~text
Mã ứng dụng: logger.log(Level.INFO, template, args)
                          |
                          v
                 java.util.logging.Logger
                     Level / Filter
                          |
                          v
                       LogRecord
         message, parameters, level, instant,
          logger name, thread, thrown...
                          |
                          v
                  Handler / Filter
                          |
                          v
                       Formatter
                  format(LogRecord)
                          |
                          v
                  Chuỗi biểu diễn
                          |
                          v
                Console / file / stream
~~~

Trong Logback và Log4j 2, sơ đồ tương tự về mặt trách nhiệm, nhưng thay các kiểu JUL bằng logging event, appender, layout và encoder của implementation tương ứng.

| Câu hỏi | Nơi chịu trách nhiệm chính |
| --- | --- |
| Sự kiện nào nên được ghi, mức nào? | Mã ứng dụng và Logger |
| Event có vượt qua level/filter? | Logger và Handler/Appender theo từng tầng |
| Dòng log gồm những trường nào và định dạng ra sao? | Formatter/Layout/Encoder |
| Ghi ra stderr, file, stream hay hệ thống thu thập? | Handler/Appender và cấu hình |
| Ai quyết định retention/quyền xem log? | Hạ tầng logging và chính sách vận hành |

Nếu Logger đang ở ngưỡng INFO, lời gọi `logger.fine(...)` có thể bị loại **trước khi Formatter tham gia**. Sửa formatter không thể khiến một `LogRecord` chưa được chấp nhận xuất hiện.

Một ứng dụng có thể dùng **nhiều Handler/Appender** với formatter khác nhau: console dùng text ngắn, file dùng timestamp và stack trace, collector dùng JSON. Các sự kiện nghiệp vụ không cần bị sửa nội dung mỗi lần thay cách trình bày.

## 2. Formatter xử lý những dữ liệu nào?

Trong JUL, dữ liệu đầu vào của formatter là `java.util.logging.LogRecord`.

| Dữ kiện | Phương thức JUL | Tại sao hữu ích? |
| --- | --- | --- |
| Level | `record.getLevel()` | Phân biệt INFO, WARNING, SEVERE... |
| Message template | `record.getMessage()` | Nội dung gốc, có thể chứa `{0}` |
| Parameters | `record.getParameters()` | Giá trị chèn vào template |
| Message được định dạng | `formatMessage(record)` | Phối hợp template, parameters và resource bundle |
| Tên logger | `record.getLoggerName()` | Tìm thành phần phát sự kiện |
| Thời điểm | `record.getInstant()` | Timestamp gắn với record |
| Exception | `record.getThrown()` | Nguyên nhân và stack trace nếu có |
| Nguồn gọi | `record.getSourceClassName()`, `getSourceMethodName()` | Vị trí phát sự kiện khi có thông tin |
| Thông tin luồng | Metadata thread của record | Hỗ trợ điều tra concurrency |

Không phải bản ghi nào cũng có exception hoặc thông tin nguồn gọi. Formatter nên xử lý trường `null` hợp lý, không ném thêm `NullPointerException` chỉ vì một event không có `Throwable`.

### Template khác chuỗi đã định dạng

Trong JUL:

~~~java
// Đoạn code minh họa trong phương thức đã có logger JUL.
logger.log(java.util.logging.Level.INFO,
        "event=order_accepted orderId={0} units={1}",
        new Object[]{"ord-7", 3});
~~~

Với formatter dùng `formatMessage(record)`, phần message được trình bày thành:

~~~text
event=order_accepted orderId=ord-7 units=3
~~~

Nếu custom formatter chỉ trả `record.getMessage()`, người đọc có thể thấy nguyên `orderId={0}`, vì `getMessage()` trả về mẫu ban đầu. `formatMessage(record)` còn hỗ trợ cơ chế resource bundle/localization của JUL khi được cấu hình.

**JUL dùng placeholder `{0}`, `{1}` trong format message; SLF4J thường dùng `{}`.** Hai kiểu không hoán đổi cú pháp cho nhau.

## 3. Viết một Formatter trong JUL

`java.util.logging.Formatter` là lớp trừu tượng, yêu cầu triển khai:

~~~java
public abstract String format(LogRecord record);
~~~

Một ví dụ tối giản:

~~~java
import java.util.logging.Formatter;
import java.util.logging.LogRecord;

final class CompactFormatter extends Formatter {
    @Override
    public String format(LogRecord record) {
        return record.getLevel().getName()
                + " | " + formatMessage(record)
                + System.lineSeparator();
    }
}
~~~

Đoạn class trên có thể biên dịch khi đặt trong tệp Java thích hợp, nhưng chưa có `main`. Để dùng, gắn nó vào `Handler`:

~~~java
// Trong đoạn cấu hình đã có biến console kiểu ConsoleHandler:
console.setFormatter(new CompactFormatter());
~~~

**Formatter không tự mở file hoặc ghi ra network.** `ConsoleHandler`, `FileHandler` hoặc một Handler khác sử dụng formatter khi xuất record.

Các phương thức liên quan:

- `format(LogRecord)`: tạo biểu diễn của một bản ghi.
- `formatMessage(LogRecord)`: tạo thông điệp đọc được từ template, parameters và resource bundle.
- `getHead(Handler)` và `getTail(Handler)`: nội dung mở đầu/kết thúc cần thiết với một số định dạng kiểu tài liệu hoặc XML.

Một text formatter thường thêm newline sau mỗi event. Nếu bỏ `System.lineSeparator()`, hai event liên tiếp có thể dính thành một dòng khó đọc.

## 4. Ví dụ Java 17+ chạy độc lập

Chương trình sau minh họa **custom JUL Formatter**, hoàn toàn không cần dependency ngoài JDK. Đầu ra được thiết kế xác định để dễ kiểm chứng: level, tên logger, message đã thay tham số, tên lớp exception và việc escape newline từ dữ liệu đầu vào.

Tạo tệp **FormatterDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FormatterDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String message = formatMessage(record)
                        .replace("\\", "\\\\")
                        .replace("\r", "\\r")
                        .replace("\n", "\\n");
                String cause = record.getThrown() == null
                        ? ""
                        : " | cause="
                                + record.getThrown().getClass().getSimpleName();
                return record.getLevel().getName()
                        + " | " + record.getLoggerName()
                        + " | " + message + cause
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        LOG.log(Level.INFO,
                "event=order_accepted orderId={0} units={1}",
                new Object[]{"ord-7", 3});
        LOG.log(Level.WARNING,
                "event=retry_scheduled reason={0} attempt={1}",
                new Object[]{"timeout", 2});
        LOG.log(Level.SEVERE, "event=payment_failed orderId=ord-8",
                new IllegalStateException("gateway unavailable"));
        LOG.log(Level.INFO, "event=user_input value={0}", "hello\nworld");

        LOG.removeHandler(console);
        console.close();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 FormatterDemo.java
java FormatterDemo
~~~

**Output chính xác trên stderr** từ `ConsoleHandler`:

~~~text
INFO | demo.checkout | event=order_accepted orderId=ord-7 units=3
WARNING | demo.checkout | event=retry_scheduled reason=timeout attempt=2
SEVERE | demo.checkout | event=payment_failed orderId=ord-8 | cause=IllegalStateException
INFO | demo.checkout | event=user_input value=hello\nworld
~~~

Phân tích:

1. Formatter gọi `formatMessage(record)` để thay `{0}`, `{1}` trong template.
2. Level và logger name đến từ `LogRecord`; ứng dụng không cần tự chèn chúng vào mỗi message.
3. `getThrown()` cho biết record có exception hay không; ví dụ **chỉ in tên lớp exception** để kết quả ổn định. Điều này **không đủ cho chẩn đoán lỗi production** nếu cần stack trace.
4. Dòng cuối có đầu vào chứa ký tự newline thật. Formatter thay nó thành ký hiệu chữ `\\n`, nên vẫn chỉ có một dòng output cho event.
5. `LOG.setUseParentHandlers(false)` giúp record không đồng thời đi vào Handler của logger cha/root, tránh output trùng trong ví dụ.
6. `ConsoleHandler` mặc định ghi **stderr**, không phải stdout. Đổi formatter không thay đích stream.
7. `LOG.removeHandler(console)` và `console.close()` cho thấy việc dọn tài nguyên khi quản lý Handler trực tiếp.

Ví dụ này đã được biên dịch và chạy với **`javac --release 17`**. Nếu dùng formatter mặc định, kết quả có thể chứa timestamp và định dạng exception khác. Vì timestamp thay đổi theo thời gian thực, ví dụ chọn **không in timestamp** để đầu ra có thể đối chiếu chính xác.

**Giới hạn bảo mật:** các bước `replace` chỉ xử lý backslash, carriage return và newline. Chúng không xử lý toàn bộ ký tự điều khiển, JSON escaping, dữ liệu bí mật hay giới hạn độ dài. Với ứng dụng thực, nên dùng encoder đúng định dạng và chính sách dữ liệu phù hợp.

## 5. Các Formatter có sẵn trong JDK

JUL có hai formatter thường gặp:

| Formatter | Dạng đầu ra | Cách dùng |
| --- | --- | --- |
| `SimpleFormatter` | Text dễ đọc, thường có thời điểm, level, tên nguồn, message và exception | Console, file cho người vận hành |
| `XMLFormatter` | Biểu diễn event theo XML | Hệ thống xử lý log dạng XML |
| Custom `Formatter` | Text hoặc định dạng riêng do ứng dụng định nghĩa | Khi hệ thống có quy ước đầu ra riêng |

Ví dụ cấu hình Handler từ code (đoạn minh họa):

~~~java
java.util.logging.ConsoleHandler handler =
        new java.util.logging.ConsoleHandler();
handler.setFormatter(new java.util.logging.SimpleFormatter());
~~~

Có thể dùng `logging.properties` để cấu hình JUL tập trung:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = ALL
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
~~~

Chạy một chương trình đã biên dịch với file config:

~~~bash
java -Djava.util.logging.config.file=logging.properties MyApplication
~~~

`MyApplication` là class minh họa có `main`; không phải tệp đi kèm ví dụ FormatterDemo. Nếu chương trình sau đó gọi `setFormatter` bằng code, thiết lập code có thể thay formatter được chọn từ properties.

### SimpleFormatter.format có cú pháp riêng

JDK còn có thuộc tính `java.util.logging.SimpleFormatter.format` để đổi format text của `SimpleFormatter`. Ví dụ:

~~~properties
java.util.logging.SimpleFormatter.format = %4$s: %5$s%6$s%n
~~~

Các chỉ số `%4$s`, `%5$s`... thuộc cơ chế `String.format` của SimpleFormatter, khác hẳn `%level` và `%msg` của Logback. Khi sử dụng, tra tài liệu của phiên bản JDK đang chạy và thử **cả bản ghi thường lẫn bản ghi có Throwable**; nếu format bỏ thành phần exception, có thể mất stack trace.

### XMLFormatter, getHead và getTail

Đối với chuỗi event tạo thành XML, formatter có thể cần nội dung mở đầu/kết thúc theo `getHead(Handler)` và `getTail(Handler)`. Không nên tạo XML bằng cách nối chuỗi input trực tiếp vào thẻ, bởi dữ liệu có thể chứa `<`, `>`, `&` hoặc dấu nháy. Cần escaping XML chính xác.

## 6. Formatter và Layout trong Logback

Logback thường sử dụng SLF4J làm facade, nhưng **không dùng `java.util.logging.Formatter` làm trình định dạng chính**. Thay vào đó:

- **`PatternLayout`** biến logging event thành text theo pattern.
- **`Encoder`** chuyển biểu diễn event thành byte để ghi ra `OutputStream`.
- **`PatternLayoutEncoder`** kết hợp pattern layout và encoder cho ConsoleAppender/FileAppender.
- **`Appender`** là thành phần ghi ra console, file hoặc nơi nhận khác.

Một cấu hình `src/main/resources/logback.xml`:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Cách đọc các token:

| Token | Ý nghĩa |
| --- | --- |
| `%d{ISO8601}` | Timestamp được format theo quy tắc Logback |
| `%-5level` | Level căn trái trong độ rộng tối thiểu 5 |
| `%thread` | Tên thread |
| `%logger{36}` | Tên logger được rút gọn theo quy tắc Logback |
| `%msg` | Nội dung message |
| `%n` | Newline |
| `%ex` | Exception/stack trace theo converter của Logback |

Đây là **cấu hình Logback độc lập** khi ứng dụng thực sự dùng Logback backend. Đầu ra cụ thể còn phụ thuộc timestamp, thread, logger và các giá trị runtime, nên không có một stdout cố định đáng tin để sao chép cho mọi máy.

**Thay đổi pattern không tự bật DEBUG.** Nếu root logger ở INFO, application DEBUG vẫn bị chặn. Nếu Logback không phải backend thực tế, `logback.xml` cũng không quyết định output của JUL hoặc Log4j 2.

### Layout khác Encoder thế nào?

**Layout** giải thích **nội dung sẽ trông như thế nào**, thường tạo chuỗi. **Encoder** giải thích **cách biến event thành byte** và có thể bổ sung header/footer hoặc cấu trúc dữ liệu chuyên biệt. Appender cần byte để ghi stream; vì vậy Logback thường cấu hình `<encoder>` thay vì gắn một JUL `Formatter`.

Không suy ra mọi encoder đều chỉ dùng PatternLayout; có các encoder khác để xuất log có cấu trúc. Cần kiểm tra dependency, version và cấu hình cụ thể.

## 7. Layout trong Log4j 2

Log4j 2 cũng có **`PatternLayout`**, nhưng API và cú pháp cấu hình không hoàn toàn giống Logback. Ví dụ `log4j2.xml` cho backend Log4j 2:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5level [%t] %c - %m%n%throwable"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

`Console` appender ghi ra `SYSTEM_OUT`, còn `PatternLayout` quyết định pattern. `%m` là message, `%c` là logger, `%t` là thread name, `%n` là newline, `%throwable` biểu diễn exception.

Nếu ứng dụng gọi SLF4J API nhưng muốn dùng Log4j 2 Core, nó cần **SLF4J provider/binding tương thích** để chuyển event tới Log4j 2. File `log4j2.xml` không tự bảo đảm SLF4J đã chọn Log4j 2 làm backend.

## 8. SLF4J template có phải Formatter?

Không. Mã ứng dụng có thể gọi:

~~~java
// Minh họa trong phương thức có logger kiểu org.slf4j.Logger.
logger.info("event=order_accepted orderId={} units={}", orderId, units);
~~~

SLF4J cung cấp facade và tham số hóa thông điệp; nó **không chuẩn hóa một layout console/file duy nhất**. Mức độ, thời gian, logger name, thread name, exception và JSON/text output phụ thuộc backend/config.

Ba khái niệm không nên nhập làm một:

1. **Thông tin nghiệp vụ:** ứng dụng chọn event, outcome, ID và message phù hợp.
2. **Định dạng message template:** JUL dùng `{0}`; SLF4J thường dùng `{}`.
3. **Trình bày event cuối:** JUL Formatter, Logback Layout/Encoder hoặc Log4j 2 Layout.

Cũng đừng nhầm **Logback pattern `%msg`** với **mẫu tham số `{}`**. Pattern `%msg` yêu cầu layout chèn nội dung message vào dòng cuối; nó không viết thay message cho ứng dụng.

## 9. Text format và structured logging

Một bản ghi dạng text thường có các phần:

~~~text
2026-11-09T10:15:30Z INFO demo.OrderService - Order ord-7 accepted
~~~

Kiểu này dễ đọc thủ công và tìm kiếm bằng text. Khi cần query/filter chính xác theo `requestId`, `orderId`, `durationMs` và trace ID, dữ liệu có cấu trúc thường hữu ích hơn.

Ví dụ JSON minh họa, không phải output mặc định của JUL/Logback:

~~~json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "INFO",
  "logger": "demo.OrderService",
  "event": "order_accepted",
  "message": "Order accepted",
  "orderId": "ord-7",
  "units": 3
}
~~~

Ưu điểm của structured fields:

- Có thể giữ `units` là số, không chỉ chuỗi.
- Có thể truy vấn theo tên event ổn định dù câu message được thay đổi.
- Correlation ID/trace ID trở thành field riêng.
- JSON encoder đúng chuẩn xử lý dấu nháy, newline, backslash và các ký tự điều khiển có hệ thống.

**Đừng tự ghép JSON bằng các phép nối chuỗi không escape.** Một message chứa dấu nháy hoặc newline có thể làm JSON không parse được; một input độc hại có thể phá ranh giới bản ghi. Tương tự, tự bao text bằng dấu `{}` không làm một event thành JSON có cấu trúc.

Chọn encoder JSON tương thích với backend và phiên bản đang dùng. Khả năng typed fields không tự xuất hiện chỉ nhờ thay pattern; phía ứng dụng cần cung cấp field đúng cách.

## 10. Exception, stack trace và multiline

Một LogRecord có `record.getThrown()` nhưng custom Formatter **không tự động bắt buộc phải in** nó. Nếu chỉ trả `formatMessage(record)`, người đọc có thể không thấy stack trace của lỗi.

Ví dụ chính chỉ xuất `cause=IllegalStateException` để kết quả cố định; production thường cần thêm thông tin. Đoạn mã minh họa trong `format(LogRecord record)`:

~~~java
if (record.getThrown() != null) {
    java.io.StringWriter buffer = new java.io.StringWriter();
    java.io.PrintWriter writer = new java.io.PrintWriter(buffer);
    record.getThrown().printStackTrace(writer);
    writer.flush();
    String stackTrace = buffer.toString();
    // Nối stackTrace vào output theo chính sách ứng dụng.
}
~~~

Đây **không phải chương trình độc lập**. Nội dung stack trace thay đổi theo call stack, class và line number, nên không có output cố định.

Có thể chọn:

| Cách xuất | Ưu điểm | Rủi ro cần xử lý |
| --- | --- | --- |
| Text một dòng/event | Dễ grep/ingest theo dòng | Phải escape newline trong dữ liệu |
| Stack trace nhiều dòng | Dễ đọc khi debug | Collector phải ghép multiline đúng event |
| JSON Lines | Dễ parse thành field | Cần encoder JSON hợp lệ và escape đầy đủ |
| XML records | Phù hợp hệ xử lý XML | Cần cấu trúc tài liệu, XML escaping và head/tail |

Stack trace có thể chứa đường dẫn, URL hoặc dữ liệu nhạy cảm trong exception message. Cần kiểm soát quyền truy cập và retention, không giả định formatter chỉ có thông tin công khai.

## 11. Timestamp, timezone và vị trí gọi

Formatter production nên có timestamp dễ so sánh giữa các hệ thống. Với JUL, dùng **`record.getInstant()`** thay vì gọi `Instant.now()` ở thời điểm formatter được chạy: đặc biệt khi có async logging, hai thời điểm có thể khác nhau.

Một đoạn minh họa:

~~~java
// Bên trong format(LogRecord record):
String timestamp = java.time.format.DateTimeFormatter.ISO_INSTANT
        .format(record.getInstant());
~~~

`ISO_INSTANT` cho timestamp theo UTC, có chỉ dấu timezone rõ ràng. Nếu cần hiển thị theo múi giờ cụ thể, đặt offset/zone và ghi thống nhất với các service khác. Không lẫn thời gian local không timezone với UTC khi phân tích thứ tự sự kiện.

**Caller location** như file/method/line number có thể tốn chi phí nếu backend phải truy ngược stack; đừng luôn bật khi không cần. **Thread name** hữu ích nhưng không thay `requestId`/trace ID, vì thread pool có thể tái sử dụng cùng thread cho nhiều request.

Khi một bộ thu thập log xử lý dữ liệu từ nhiều máy, sai lệch đồng hồ vẫn tồn tại; correlation ID và distributed tracing giúp liên hệ event đáng tin hơn chỉ dựa timestamp.

## 12. Hiệu năng và concurrency

Một formatter được gọi nhiều lần trong ứng dụng có lưu lượng lớn. Một số nguyên tắc:

- **Không serialize cả object graph** nếu chỉ cần ID và vài giá trị chẩn đoán.
- **Không làm I/O trong `format()`** để gọi database/network hoặc ghi file ngoài handler; formatter nên tập trung xử lý biểu diễn.
- **Dùng formatter ít trạng thái chia sẻ**, vì nhiều thread có thể dùng chung handler/formatter. Biến cục bộ và `DateTimeFormatter` bất biến thường dễ an toàn hơn formatter thời gian mutable chia sẻ.
- **Không gọi ngược vào cùng hệ logging từ Formatter để báo lỗi định dạng** nếu nó có thể tạo vòng lặp/đệ quy.
- **Không đổ mọi chi phí log cho Formatter**: tạo message trước logger, stack trace, encoder JSON, appender file, async queue và network có thể ảnh hưởng nhiều hơn.
- **Không giả định placeholder là lazy:** một đối số gọi hàm nặng có thể được Java tính trước khi logger kiểm tra level; dùng supplier/level check thích hợp ở nguồn.

Ví dụ cách tránh tính debug dump quá sớm (đoạn minh họa SLF4J):

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("event=state_inspected data={}", buildExpensiveDump());
}
~~~

Dù pattern/layout rất gọn, việc tạo dữ liệu trước khi qua logger vẫn có thể tốn CPU. Cần đo hiệu năng trên workload thực, thay vì chỉ so độ dài pattern.

## 13. Formatter không thay thế bảo mật dữ liệu log

Formatter có thể escape giá trị cho đúng định dạng, nhưng **không thể quyết định thay cho nghiệp vụ dữ liệu nào được phép ghi**.

Ở nguồn phát log, hãy ưu tiên allowlist: event, reason code, ID nội bộ phù hợp, trạng thái, thời lượng. Tránh password, token, Authorization header, session cookie, dữ liệu thẻ, payload nhạy cảm hoặc chuỗi `toString()` của object lớn.

Rủi ro **log injection** xảy ra khi input từ bên ngoài chứa newline, dấu nháy hoặc các ký tự điều khiển khiến record text bị chia sai, hoặc giá trị giả giống `ERROR` của một event khác. Ví dụ custom formatter đã escape newline ở mức minh họa; production nên sử dụng encoder đúng định dạng và kiểm tra cả trường không tin cậy khác.

**Không xem JUL `{0}` hoặc SLF4J `{}` là công cụ tự động che secrets.** Chúng là cú pháp thay tham số, không phải lớp kiểm soát truy cập hay bộ lọc dữ liệu nhạy cảm.

## 14. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Kiểm tra hoặc sửa |
| --- | --- | --- |
| Dòng JUL vẫn in `{0}` | Formatter dùng `getMessage()` thay vì `formatMessage(record)` | Dùng formatMessage khi muốn giá trị đã thay |
| Mất stack trace | Custom Formatter không xử lý `getThrown()` | Trình bày Throwable hoặc chọn formatter có hỗ trợ |
| Nhiều record dính một dòng | Không thêm newline trong `format()` | Thêm `System.lineSeparator()`/`%n` |
| Không thấy DEBUG/FINE | Logger/Handler/Appender chặn event trước formatter | Kiểm tra level và filter ở từng tầng |
| JUL `{}` không được thay | Dùng cú pháp SLF4J trong JUL | Dùng `{0}`, `{1}` đúng JUL |
| Log xuất trùng | Nhiều Handler/Appender hoặc chuyển tiếp cha | Kiểm tra parent handlers, additivity |
| JSON không parse được | Tự ghép JSON không escape | Dùng encoder JSON chuyên dụng |
| Stack trace thành nhiều event | Collector không cấu hình multiline | Dùng structured logging hoặc multiline parser |
| Timestamp lệch nhiều giờ | Múi giờ định dạng khác nhau | Chuẩn hóa UTC/offset |
| Hiệu năng giảm | Formatter nặng, caller lookup, stack trace hoặc serialization | Đo profile và giảm dữ liệu không cần |
| Có text nhưng thiếu logger name/level | Pattern không in metadata đó | Thêm field tương ứng |
| Log JUL ra stderr không phải stdout | `ConsoleHandler` thường dùng stderr | Kiểm tra Handler/output, không chỉ Formatter |
| Pattern Logback không tác dụng | Runtime đang dùng backend khác | Kiểm tra provider và tệp cấu hình thật sự nạp |
| Dữ liệu nhạy cảm xuất hiện | Nguồn phát log ghi payload/secret | Allowlist/redact tại nguồn và giới hạn truy cập |

Trình tự điều tra: xác nhận lệnh logger chạy → level/filter cho phép event → xác định backend → kiểm tra handler/appender → xác định formatter/layout/encoder được gắn → thử event có parameter, Throwable và newline → kiểm tra output trên stderr/stdout/file/collector.

Không sửa cả level lẫn formatter cùng lúc nếu chưa biết record **bị loại trước** hay **được xuất nhưng trình bày sai**.

## 15. Bài tập tự kiểm tra

Cho Formatter JUL như sau:

~~~java
@Override
public String format(java.util.logging.LogRecord record) {
    return record.getLevel() + " " + record.getMessage();
}
~~~

Một lớp phát:

~~~java
logger.log(java.util.logging.Level.WARNING,
        "event=retry attempt={0}", 2);
~~~

Đây là hai đoạn minh họa, không phải một chương trình độc lập.

Hãy trả lời:

1. Tại sao `{0}` có thể vẫn còn trong đầu ra?
2. Vì sao hai sự kiện có thể dính vào một dòng?
3. Tại sao không có stack trace dù record có Throwable?
4. Nếu Logger đang OFF, chỉ sửa Formatter có làm event INFO xuất không?
5. Nếu cần JSON, tại sao không thể chỉ nối `"{\\"message\\":\\"" + value + "\\"}"`?

**Đáp án:**

1. `getMessage()` trả template. Dùng `formatMessage(record)`.
2. `format()` không thêm newline.
3. Không gọi `record.getThrown()` để xử lý exception.
4. Không. Logger đã loại event trước Formatter.
5. Vì value có thể chứa dấu nháy, backslash, newline và control characters; cần JSON encoder hợp lệ.

Một phiên bản text formatter cải thiện:

~~~java
@Override
public String format(java.util.logging.LogRecord record) {
    return record.getLevel().getName()
            + " " + formatMessage(record)
            + System.lineSeparator();
}
~~~

Nó giải quyết template và newline nhưng chưa bổ sung timestamp, Throwable hoặc escaping dữ liệu không tin cậy.

## 16. Checklist khi thiết kế Formatter và Layout

- Biết chính xác hệ logging đang dùng: **JUL, Logback hay Log4j 2**.
- Phân biệt **event, handler/appender và định dạng**.
- Hiển thị **level, timestamp có timezone, tên logger và message** phù hợp.
- Dùng **đúng template theo API** và kiểm tra giá trị đã được thay.
- Xử lý **Throwable và stack trace** theo nhu cầu chẩn đoán.
- Quy định rõ **một dòng/event hay multiline**, tương thích collector.
- Dùng escaping đúng định dạng; ưu tiên encoder JSON/XML có sẵn.
- Không ghi secrets hoặc raw payload; kiểm soát quyền truy cập log.
- Tránh chi phí format quá lớn, xử lý stateful không thread-safe và logging đệ quy.
- Kiểm thử với INFO/WARNING/SEVERE, parameters, exception và input có newline.
- Xác nhận bản ghi xuất **đúng đích** thay vì chỉ đẹp về hình thức.

**Kết luận:** Formatter là **bộ phận trình bày của một log event**. JUL dùng `Formatter` gắn vào `Handler`; Logback và Log4j 2 dùng các `Layout/Encoder` thích hợp. Formatter tốt giúp bản ghi nhất quán, dễ đọc, dễ tìm và an toàn về định dạng, nhưng **không thay thế việc chọn sự kiện, lọc level, cấu hình đích ghi hay bảo vệ dữ liệu ngay tại nguồn**.