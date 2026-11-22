# Cấu hình logging bằng code trong Java

## 1. Cấu hình logging bằng code là gì?

**Cấu hình logging bằng code (programmatic logging configuration)** là cách ứng dụng sử dụng Java API để thiết lập hành vi ghi log: logger nào được bật, mức log nào được chấp nhận, sự kiện được gửi tới đâu và được định dạng ra sao. Việc cấu hình có thể diễn ra lúc khởi động hoặc thay đổi có kiểm soát trong lúc ứng dụng đang chạy.

Ví dụ, thay vì khai báo sẵn mức `DEBUG` trong file cấu hình, chương trình có thể bật `DEBUG` cho riêng `com.example.payment` để điều tra một lỗi, rồi trả về mức `INFO`. Hoặc chương trình tự đăng ký một `ConsoleHandler`/`FileHandler` để ghi log ở môi trường không có file cấu hình.

Cần phân biệt **API ghi log** với **bộ máy cấu hình và xuất log**:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Logger | Đầu vào để code nghiệp vụ phát sự kiện | `java.util.logging.Logger`, `org.slf4j.Logger` |
| Level | Ngưỡng nhận sự kiện | JUL: `FINE`, `INFO`, `WARNING`; Logback: `DEBUG`, `INFO`, `WARN` |
| Handler / Appender | Đưa sự kiện tới console, file, network hoặc hệ thống thu thập | JUL: `ConsoleHandler`, `FileHandler`; Logback: `ConsoleAppender`, `FileAppender` |
| Formatter / Encoder / Layout | Biến sự kiện thành text hoặc JSON | JUL `Formatter`; Logback `PatternLayoutEncoder` |
| Filter | Chấp nhận hoặc loại sự kiện theo điều kiện | JUL `Filter`; Logback `Filter` / `TurboFilter` |
| Logging backend | Quản lý chuỗi logger → filter → appender và vòng đời | JUL, Logback Classic, Log4j 2 |

**SLF4J là façade/API trung gian**, không cung cấp một API chung để cấu hình mọi backend. Gọi `LoggerFactory.getLogger(...)` tạo/lấy logger qua SLF4J, nhưng thao tác như `setLevel` hoặc đăng ký appender phải dùng API của backend đang hoạt động. Không ép kiểu logger SLF4J sang Logback khi ứng dụng có thể đang chạy với backend khác.

## 2. Khi nào dùng code thay vì file cấu hình?

Cấu hình bằng code có giá trị khi cần:

- Khởi tạo một ứng dụng nhỏ, công cụ dòng lệnh hoặc bài kiểm thử mà không muốn mang theo file `logging.properties`, `logback.xml` hay `log4j2.xml`.
- Bật/tắt mức log cho một logger cụ thể trong lúc vận hành, với quyền truy cập và thời hạn rõ ràng.
- Tạo appender/handler dựa trên thông tin chỉ có sau khi chương trình khởi động, như một đường dẫn đã được xác thực hoặc môi trường chạy.
- Gắn thêm logging sink dành riêng cho một thư viện hoặc một thành phần mà chương trình trực tiếp sở hữu.

Với ứng dụng lớn, **file cấu hình hoặc configuration properties vẫn thường dễ vận hành hơn**: người quản trị thấy được chính sách trước khi khởi động, dễ so sánh thay đổi và ít cần sửa code. Cấu hình code nên tập trung ở một điểm khởi tạo hoặc một dịch vụ quản trị đã kiểm soát quyền, tránh phân tán nhiều lệnh `setLevel()` khắp code nghiệp vụ.

## 3. Quy trình thiết lập logging bằng code

Một trình tự an toàn thường là:

1. **Xác định backend đang dùng**: JUL, Logback Classic, Log4j 2 hoặc backend khác. Không trộn API cấu hình của nhiều backend.
2. **Chọn phạm vi**: root logger, logger theo package hoặc logger của riêng một thành phần. Thay đổi root tác động rộng, nên hạn chế.
3. **Tạo sink**: handler/appender tới console, file hoặc một nơi khác; chọn ngưỡng và formatter/encoder.
4. **Đăng ký sink vào logger**, điều chỉnh việc truyền tiếp tới parent (JUL) hoặc `additivity` (Logback), tránh ghi trùng.
5. **Thiết lập mức log** ở logger và ở handler/appender nếu backend phân tầng lọc theo nhiều bước.
6. **Kiểm tra bằng một sự kiện thực tế**: đúng level, format, đích ghi, số bản sao và thời điểm.
7. **Quản lý vòng đời**: flush/close khi thích hợp, tránh đăng ký appender lặp lại sau mỗi request hoặc mỗi lần cấu hình lại.

Vòng đi của một sự kiện có thể hình dung:

```text
code nghiệp vụ gọi logger.info(...)
           |
           v
   Logger / mức / filter
           |
           v
    Handler hoặc Appender
           |
           v
    Formatter hoặc Encoder
           |
           v
 Console / file / network sink
```

Các backend có khác biệt về thứ tự kiểm tra level và filter. Sơ đồ trên mô tả ý tưởng chung, không thay thế tài liệu vòng xử lý chính xác của từng backend.

## 4. Java 17: cấu hình java.util.logging hoàn toàn bằng code

`java.util.logging` (JUL) thuộc JDK, không cần thêm dependency. Ví dụ sau cố tình định dạng ngắn gọn để đầu ra có thể kiểm tra chính xác, đồng thời tắt đường gửi lên logger cha để không bị nhân đôi log từ root handler.

Lưu tệp **`JulProgrammaticConfigDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulProgrammaticConfigDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.orders");

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.FINE);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " [" + record.getLoggerName() + "] "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.addHandler(console);

        logger.fine("Connection opened");
        logger.info("Order accepted");
        logger.warning("Retrying supplier");

        console.flush();
        logger.removeHandler(console);
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac JulProgrammaticConfigDemo.java
java JulProgrammaticConfigDemo
```

**Kết quả trên `stderr`** (vì JUL `ConsoleHandler` mặc định ghi tới luồng lỗi chuẩn):

```text
FINE [demo.orders] Connection opened
INFO [demo.orders] Order accepted
WARNING [demo.orders] Retrying supplier
```

Trong ví dụ này, `stdout` không có nội dung. Terminal thông thường vẫn hiển thị các dòng `stderr`; nếu chuyển hướng luồng khi chạy, cần phân biệt hai luồng.

Giải thích các dòng cấu hình quan trọng:

- `Logger.getLogger("demo.orders")` lấy logger có tên cụ thể; hệ thống logger JUL hỗ trợ cây tên phân cấp như `demo`, `demo.orders`.
- `setUseParentHandlers(false)` ngăn sự kiện được gửi tiếp tới handler của logger cha/root, tránh log trùng qua root console handler. Nó không làm mất khả năng kế thừa **level**; việc kế thừa level được điều khiển riêng bằng `setLevel()`.
- `logger.setLevel(Level.FINE)` cho logger nhận cả `FINE`, `INFO`, `WARNING`.
- `console.setLevel(Level.FINE)` cho phép handler xuất cả ba mức này; chỉ hạ level của logger mà handler vẫn giữ `INFO` thì `FINE` vẫn không xuất hiện.
- `setFormatter(...)` quyết định từng dòng text. `formatMessage(record)` xử lý thông điệp của `LogRecord` theo quy tắc JUL.
- `logger.addHandler(console)` gắn handler vào logger; `removeHandler` gỡ liên kết khi bài demo hoàn thành.

Ví dụ chạy một lần trong JVM mới nên không gặp handler cũ đã được gắn trước đó. Trong ứng dụng dài hạn, code sở hữu logger/handler cần định nghĩa rõ ai đăng ký, ai gỡ và ai đóng tài nguyên; không tự xóa/đóng handler do thành phần khác sở hữu.

### 4.1. Hai lớp lọc level trong JUL

Với JUL, một sự kiện thường phải vượt **level của logger** trước, rồi vượt **level của handler** (ngoài các filter có thể có). Chẳng hạn:

| Logger level | ConsoleHandler level | `logger.fine(...)` xuất ra? | `logger.warning(...)` xuất ra? |
| --- | --- | --- | --- |
| `INFO` | `ALL` | Không | Có |
| `FINE` | `INFO` | Không | Có |
| `FINE` | `FINE` | Có | Có |
| `OFF` | `ALL` | Không | Không |

Bảng giả định không có filter khác và handler được gắn trực tiếp vào logger. `Level.ALL` ở handler không thể phục hồi sự kiện đã bị logger chặn; `Level.OFF` ở logger tắt các lời gọi logging thông thường.

Các mức chuẩn của JUL theo thứ tự tăng dần thông thường: `FINEST`, `FINER`, `FINE`, `CONFIG`, `INFO`, `WARNING`, `SEVERE` (ngoài `ALL`/`OFF`). JUL không có sẵn enum `DEBUG` hay `ERROR` với tên như Logback; nếu cần quy ước tương ứng, thường dùng `FINE` gần với DEBUG và `SEVERE` gần với ERROR, nhưng không coi đó là ánh xạ tuyệt đối giữa mọi framework.

### 4.2. Kế thừa mức log và tác dụng của tên logger

Trong JUL, `logger.setLevel(null)` cho phép logger **kế thừa effective level từ cha**. Điều này khác `logger.setUseParentHandlers(false)`, vốn điều khiển việc đưa sự kiện lên handler của cha.

Ví dụ nếu package `demo` đặt `INFO` và `demo.orders` không đặt level riêng, logger con sẽ chịu ảnh hưởng mức hiệu lực từ cây logger. Khi đặt `demo.orders` thành `FINE`, phạm vi ghi chi tiết có thể giới hạn ở một nhánh; handler vẫn cần có cấu hình tương thích để thấy các sự kiện `FINE`.

Tránh cho nhiều thư viện không liên quan cùng thay đổi root logger trong lúc chạy. Một thay đổi ở root có thể làm tăng lượng log của toàn ứng dụng, ảnh hưởng CPU/I/O, chi phí lưu trữ và cả dữ liệu được phát ra ngoài.

## 5. Ghi file bằng FileHandler của JUL

JUL hỗ trợ `FileHandler`, có thể tạo bằng code và đặt rotation cơ bản. Đây là **đoạn mã tích hợp**, giả sử đã có biến `Logger logger` do ứng dụng quản lý; nó không phải chương trình độc lập.

```java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.SimpleFormatter;

// Chỉ chạy khi thư mục "logs" đã tồn tại và tiến trình có quyền ghi.
FileHandler file = new FileHandler(
        "logs/application-%u.%g.log",
        1_048_576,
        3,
        true
);
file.setLevel(Level.INFO);
file.setFormatter(new SimpleFormatter());
logger.addHandler(file);
```

- `1_048_576` là giới hạn xấp xỉ 1 MiB cho từng file trước khi xoay (theo giới hạn byte của FileHandler).
- `3` là số file được dùng trong cơ chế rotation theo `FileHandler`.
- `true` yêu cầu chế độ append.
- `%u` giúp tránh xung đột tên file khi có nhiều FileHandler/process; `%g` thể hiện generation của vòng rotation.
- `SimpleFormatter` có thể ghi timestamp, class và level; đầu ra phụ thuộc thời gian và cấu hình, nên không có một `stdout` cố định.

Ví dụ cần xử lý `IOException` ở phương thức bao quanh hoặc khai báo `throws IOException`; các import/biến thực tế phải được tích hợp vào class. Khi ngừng dùng, phải gỡ và **đóng FileHandler** do chương trình sở hữu để giải phóng file handle/lock. Đừng đóng handler chung của hệ thống chỉ vì muốn thay đổi level của một logger.

`FileHandler` là công cụ logging file cơ bản, không tự mang đủ chính sách retention, upload, bảo mật và khả năng xử lý lỗi của một log pipeline production.

## 6. Cấu hình Logback bằng code khi sử dụng SLF4J

Trong nhiều ứng dụng Java, code nghiệp vụ dùng `org.slf4j.Logger` để tránh phụ thuộc trực tiếp vào backend. Khi backend là **Logback Classic**, phần cấu hình cần dùng lớp của Logback, như `LoggerContext`, `ConsoleAppender` và `PatternLayoutEncoder`.

Ví dụ sau là **chương trình Java 17 hoàn chỉnh trong một dự án đã có dependency SLF4J + Logback Classic tương thích**. Nó không biên dịch chỉ với JDK thuần. Tệp **`LogbackProgrammaticDemo.java`**:

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.encoder.PatternLayoutEncoder;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.ConsoleAppender;
import org.slf4j.ILoggerFactory;
import org.slf4j.LoggerFactory;

public class LogbackProgrammaticDemo {
    public static void main(String[] args) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();

        if (!(factory instanceof LoggerContext context)) {
            throw new IllegalStateException(
                    "The active SLF4J provider is not Logback Classic");
        }

        Logger logger = context.getLogger("demo.payment");
        logger.setLevel(Level.DEBUG);
        logger.setAdditive(false);

        if (logger.getAppender("DEMO_STDOUT") == null) {
            PatternLayoutEncoder encoder = new PatternLayoutEncoder();
            encoder.setContext(context);
            encoder.setPattern("%level [%thread] %logger - %msg%n");
            encoder.start();

            ConsoleAppender<ILoggingEvent> appender =
                    new ConsoleAppender<>();
            appender.setName("DEMO_STDOUT");
            appender.setContext(context);
            appender.setEncoder(encoder);
            appender.start();

            logger.addAppender(appender);
        }

        logger.debug("Payment {} started", 42);
    }
}
```

Với console appender chạy theo cấu hình vừa tạo, `stdout` của sự kiện ví dụ là:

```text
DEBUG [main] demo.payment - Payment 42 started
```

Nếu ứng dụng có appender phụ hoặc cấu hình đặc biệt do runtime đã nạp, kết quả ngoài phạm vi demo có thể khác. Mẫu code chủ động:

1. Xác nhận SLF4J đang kết nối với Logback; nếu không, báo lỗi rõ thay vì cast mù.
2. Lấy logger riêng `demo.payment` chứ không `context.reset()` hoặc viết lại root logger.
3. Bật `DEBUG` cho logger đó và tắt **additivity** để không đồng thời gửi sự kiện lên appender của root.
4. Tạo encoder trước, rồi console appender; cả hai được gắn `LoggerContext` và `start()`.
5. Kiểm tra tên appender `DEMO_STDOUT` trước khi thêm, giúp tránh gắn trùng cùng tên nếu đoạn khởi tạo được gọi lại trong cùng context.

Trong mã trên, `Logger` import từ `ch.qos.logback.classic.Logger` là logger của backend để cấu hình. Tại nơi viết nghiệp vụ, tiếp tục ưu tiên `org.slf4j.Logger` và `LoggerFactory.getLogger(...)` để giảm phụ thuộc vào backend.

**Vòng đời:** khi ứng dụng kết thúc hoặc thay đổi cấu hình, code sở hữu appender phải `stop()` và gỡ nó theo cơ chế lifecycle của Logback. Đừng `context.stop()` hoặc `context.reset()` tùy tiện giữa lúc các thành phần khác đang dùng cùng logging context.

### 6.1. Thay đổi mức log Logback khi đang chạy

Nếu Logback đã được khởi tạo và ứng dụng chỉ cần đổi mức cho một tên logger, không cần tạo appender mới:

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.LoggerFactory;

LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();

Logger target = context.getLogger("com.example.payment");
Level previous = target.getLevel();
target.setLevel(Level.DEBUG);

try {
    // Giai đoạn điều tra có giới hạn, do ứng dụng kiểm soát.
} finally {
    target.setLevel(previous);
}
```

Đây là **mã minh họa tích hợp**. `getLevel()` trả về mức được cấu hình **trực tiếp** tại logger và có thể là `null` nếu logger đang kế thừa mức từ cha. Khôi phục đúng giá trị `previous`, kể cả `null`, sẽ giữ lại chế độ kế thừa ban đầu. Nếu nhiều người/tác vụ thay level đồng thời, mô hình “lưu rồi khôi phục” không đủ để phối hợp; cần một bộ quản lý thay đổi có đồng bộ, quyền hạn và thời hạn.

Không thực hiện thay level trên mỗi request. Những thay đổi runtime nên có audit trail, giới hạn phạm vi, thời gian tự hết hiệu lực và cảnh báo khi mức log quá chi tiết.

### 6.2. Khi backend là Log4j 2

Nếu ứng dụng thực sự dùng **Log4j 2 Core**, có thể điều chỉnh level bằng API `Configurator` của backend. Đoạn sau **không phải chương trình độc lập** và yêu cầu dependency Log4j 2 Core tương thích:

```java
import org.apache.logging.log4j.Level;
import org.apache.logging.log4j.core.config.Configurator;

Configurator.setLevel("com.example.payment", Level.DEBUG);
```

Lệnh này thay đổi cấu hình mức log của logger có tên chỉ định. Nếu cần khởi tạo appender/layout hoàn toàn bằng code, Log4j 2 có API cấu hình riêng; không sử dụng `ConsoleHandler` của JUL hoặc `ConsoleAppender` của Logback để cấu hình một `LoggerContext` Log4j 2. `Configurator.setRootLevel(...)` có phạm vi rộng và cần được kiểm soát kỹ.

## 7. Cấu hình theo môi trường và các nguồn xung đột

Một ứng dụng có thể có nhiều nguồn cấu hình: `logging.properties`, `logback.xml`, `logback-spring.xml`, `log4j2.xml`, properties của framework, biến môi trường và API cập nhật động. **Thứ tự khởi tạo và khả năng nạp lại cấu hình quyết định giá trị nào có hiệu lực**, nên không thể giả định một lời gọi `setLevel()` luôn thắng mọi nguồn mãi mãi.

Ví dụ trong Spring Boot, `logging.level.com.example.payment=DEBUG` là một lựa chọn cấu hình quen thuộc để thiết lập level lúc khởi động. Khi thật sự cần thay level trong runtime, có thể dùng API logging system của Spring Boot hoặc API backend tùy kiến trúc; phải kiểm tra phiên bản và cơ chế reload/management. Tránh cấu hình lặp ở nhiều nơi và không dựa vào tên class của backend nếu deployment có thể thay provider.

Để cấu hình bằng code một cách có kiểm soát:

- Xác định rõ **nguồn sự thật (source of truth)** của level và đích ghi.
- Chỉ nhận giá trị từ danh sách level được phép; xử lý cấu hình thiếu/sai.
- Áp dụng một lần trong bootstrap hoặc trong endpoint vận hành có xác thực, phân quyền và ghi audit.
- Khi reload file hoặc thay backend, áp dụng lại cấu hình nếu đó là hợp đồng thiết kế; không dựa vào một thay đổi runtime bị mất sau restart.
- Không ghi secret, token hay thông tin khách hàng vào thông báo chẩn đoán cấu hình.

Ví dụ ánh xạ một biến môi trường chung sang level JUL, để tránh nhầm `DEBUG` của ứng dụng với `Level.parse("DEBUG")` vốn không phải một level chuẩn JUL. Đây là **hàm minh họa tích hợp** vào class Java 17:

```java
import java.util.Locale;
import java.util.logging.Level;

static Level toJulLevel(String raw) {
    return switch (raw.trim().toUpperCase(Locale.ROOT)) {
        case "TRACE" -> Level.FINEST;
        case "DEBUG" -> Level.FINE;
        case "INFO"  -> Level.INFO;
        case "WARN"  -> Level.WARNING;
        case "ERROR" -> Level.SEVERE;
        default -> throw new IllegalArgumentException(
                "Unsupported logging level");
    };
}
```

Ứng dụng phải xác định chính sách cho giá trị `null`/trống (ví dụ dùng mức mặc định và cảnh báo quản trị); hàm trên kỳ vọng tham số không phải `null`. Mức được chọn vẫn phải phù hợp với handler và filter thực tế, nếu không một sự kiện có thể bị chặn ở tầng sau.

## 8. Filters, format và thông tin ngữ cảnh

Ngoài level, cấu hình bằng code thường cần formatter hoặc filter cho yêu cầu cụ thể:

- **Formatter/encoder:** nhất quán timestamp, level, logger name, thread name, message, exception stack trace; log dạng JSON nên có schema ổn định.
- **Filter:** lựa chọn loại sự kiện theo điều kiện, nhưng không nên đưa business logic quan trọng vào filter của logging pipeline.
- **MDC/correlation context:** bổ sung request/trace ID cho các log liên quan cùng tác vụ. Đây là dữ liệu ngữ cảnh lúc phát log, không đồng nghĩa việc cấu hình level/appender. Với các task bất đồng bộ, context có thể cần được truyền rõ ràng và dọn trong `finally`.
- **Mức log riêng cho package:** giảm nhiễu từ dependency bằng cách nâng ngưỡng package ngoài, giữ chi tiết cho package cần điều tra.

Không tạo formatter/handler mới mỗi khi ghi một sự kiện. Những đối tượng này thường được cấu hình **một lần**, sau đó được nhiều lần gọi logger sử dụng. Với logging không đồng bộ, thay đổi appender đang chạy còn cần xét queue, flush và shutdown để không mất log trong thời gian chuyển tiếp.

## 9. Kiểm tra cấu hình đang có hiệu lực

Thử nghiệm tối thiểu nên chứng minh được cả đường phát và đường ghi:

1. Phát một log **dưới** ngưỡng và một log **trên** ngưỡng, rồi kiểm tra đúng sự kiện xuất hiện.
2. Kiểm tra cấp logger và cấp handler/appender. Với JUL, `logger.isLoggable(Level.FINE)` chỉ nói về phía logger, **chưa chứng minh** handler sẽ thực sự xuất bản ghi.
3. Kiểm tra logger con và parent/root có ghi trùng không; thử bật/tắt `setUseParentHandlers` (JUL) hoặc `setAdditive` (Logback) theo thiết kế.
4. Xác nhận console thật sự ghi `stdout` hay `stderr`; điều này quan trọng với Docker, CI và hệ thống thu thập log.
5. Với file, thử đường dẫn, quyền ghi, rotation, encoding, lock, tình trạng đĩa đầy và đóng file khi dừng.
6. Nếu runtime đổi level, kiểm tra kết quả thay đổi ngay, cách khôi phục, restart và reload cấu hình.
7. Khi test cùng JVM, cô lập logger hoặc hoàn nguyên thay đổi cấu hình trong `finally`; không phá root logger khiến test khác bị ảnh hưởng.

Ví dụ chẩn đoán JUL bên trong một class có biến `Logger logger`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;

System.out.println("Direct logger level = " + logger.getLevel());
System.out.println("FINE enabled = " + logger.isLoggable(Level.FINE));

for (Handler handler : logger.getHandlers()) {
    System.out.println("Handler = "
            + handler.getClass().getSimpleName()
            + ", level = " + handler.getLevel());
}
```

Kết quả phụ thuộc vào trạng thái logger và các handler đang được gắn; nếu logger kế thừa level, `getLevel()` có thể là `null`. `getHandlers()` chỉ liệt kê handler gắn trực tiếp, không tự liệt kê handler ở logger cha.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy `FINE` sau khi gọi `setLevel(FINE)` | Handler vẫn chặn dưới `INFO`; filter loại sự kiện | Kiểm tra cả logger, handler và filter |
| Cùng thông điệp xuất hiện hai lần | Logger con và root cùng ghi hoặc appender được thêm lặp | Kiểm tra parent handlers/additivity và điểm bootstrap |
| Log chỉ thấy trong terminal, không tới collector | Ghi sang `stderr` thay vì `stdout`, hoặc agent không thu thập đúng stream | Kiểm tra target và cấu hình thu thập |
| Ép kiểu Logback thất bại | SLF4J đang dùng backend khác, thiếu backend hoặc xung đột provider | Kiểm tra provider thực tế và dependency |
| Sau reload mức log trở lại như cũ | File/properties được nạp lại và ghi đè cấu hình runtime | Xác định nguồn cấu hình, hook reload và quyền sở hữu |
| Logger trong package khác thay đổi ngoài dự kiến | Chỉnh root hoặc logger cha quá rộng | Giới hạn theo tên logger cụ thể |
| File log không được tạo | Thiếu thư mục, quyền ghi, lỗi lock/rotation | Bắt và báo lỗi I/O qua kênh phù hợp |
| Ghi log làm ứng dụng chậm | Formatter nặng, appender đồng bộ, sink chậm, log burst | Đo logging cost, throughput và chính sách async |
| Sau test, test khác có log sai | Đã đổi singleton logging context mà không phục hồi | Dùng logger riêng và cleanup trong `finally` |

**Không dùng một logger lỗi để báo lỗi bên trong chính appender/handler đang lỗi** nếu có thể tạo vòng lặp đệ quy. Với thành phần logging nội bộ, hãy dùng status channel, counter hoặc kênh chẩn đoán được thiết kế để tránh recursion.

## 11. Khuyến nghị thực hành

- Để học cơ chế nền tảng Java, bắt đầu với **JUL** vì API có sẵn trong JDK, đồng thời hiểu sự khác nhau giữa logger level và handler level.
- Khi ứng dụng đã chọn **SLF4J + Logback**, để code nghiệp vụ dùng SLF4J, còn module cấu hình tập trung dùng API Logback. Kiểm tra provider trước khi ép kiểu.
- Giữ cấu hình ở một chỗ, dùng tên appender/handler rõ ràng và tránh đăng ký nhiều lần.
- Ưu tiên sửa logger/package cụ thể, tránh reset toàn cục khi nhiều thành phần dùng chung logging context.
- Gắn thay đổi log level runtime với người thực hiện, lý do, phạm vi và thời hạn; hoàn nguyên cấu hình khi không còn cần điều tra.
- Nếu log thuộc nhóm **audit/bắt buộc lưu**, cấu hình một appender best-effort chưa đủ để bảo đảm bền vững: cần chính sách lưu trữ và xác nhận riêng.

Cấu hình logging bằng code cho phép điều chỉnh linh hoạt nhưng đi kèm trách nhiệm về **backend, scope, mức log, chuỗi handler/appender và vòng đời tài nguyên**. Khi nắm rõ các lớp này, có thể xác định chính xác vì sao một dòng log được ghi, bị lọc, ghi trùng hoặc xuất hiện ở sai đích.
