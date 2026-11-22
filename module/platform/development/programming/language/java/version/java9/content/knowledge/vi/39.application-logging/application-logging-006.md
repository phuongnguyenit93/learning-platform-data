# System.LoggerFinder và dịch vụ chuyển tiếp

Java 9 giới thiệu Platform Logging API và service trong JEP 264. API này cung cấp **System.Logger** để các lớp trong Java platform và thư viện có thể phát log mà không phụ thuộc trực tiếp vào một logging framework cụ thể. **System.LoggerFinder** là SPI cho phép ứng dụng chọn backend và chuyển tiếp những log message đó đến framework mà ứng dụng đang sử dụng.

Luồng cơ bản là: code gọi System.getLogger(), runtime chuyển yêu cầu đến LoggerFinder, LoggerFinder trả về một System.Logger, rồi logger chuyển message đến backend. Một provider có thể nối API này với java.util.logging, SLF4J, Log4j 2 hoặc một backend khác.

System.LoggerFinder là điểm tích hợp cho Platform Logging API. Nó không thay thế facade logging mà ứng dụng đang dùng và cũng không tự cấu hình backend. Ứng dụng vẫn có thể ghi log nghiệp vụ qua facade của framework; LoggerFinder giúp log từ JDK và thư viện dùng System.Logger đi vào cùng hệ thống log.

## 1. Platform Logging API giải quyết vấn đề gì?

Trước Java 9, một thư viện hoặc lớp trong JDK muốn ghi log thường phải chọn một API cụ thể, chẳng hạn java.util.logging. Nếu ứng dụng dùng framework khác, log từ platform và log của ứng dụng có thể đi qua hai backend hoặc hai cấu hình riêng.

JEP 264 đưa ra một API nhỏ, độc lập với backend:

- **System.Logger** định nghĩa các thao tác log tối thiểu.
- **System.LoggerFinder** là service tạo logger cho từng tên và module.
- **LoggerFinder provider** kết nối System.Logger với backend do ứng dụng chọn.
- Backend chịu trách nhiệm lọc level, cấu hình output, format, lưu trữ và rotation.

Ví dụ, một thư viện dùng System.getLogger("com.example.http") không cần biết ứng dụng đang dùng JUL hay Log4j. Khi ứng dụng cài provider phù hợp, message từ thư viện có thể được chuyển đến backend đó.

Platform Logging API hướng đến nhu cầu log của Java platform và các thư viện. Nó không phải một framework đầy đủ thay thế mọi facade logging. Ứng dụng thường vẫn dùng API của backend đã chọn cho log nghiệp vụ, vì những API đó có thể cung cấp thêm marker, structured logging, context, configuration hoặc tích hợp riêng.

## 2. Quan hệ giữa System.getLogger(), LoggerFinder và backend

Luồng gọi điển hình:

~~~text
JDK class / library / application
              |
              v
       System.getLogger(name)
              |
              v
 System.LoggerFinder.getLogger(name, module)
              |
              v
        System.Logger
              |
              v
     Forwarding adapter
              |
              v
 JUL / SLF4J / Log4j 2 / backend khác
~~~

System.getLogger(name) là điểm vào thông dụng. Runtime xác định module của caller và yêu cầu LoggerFinder tạo logger phù hợp với cặp tên và module đó.

LoggerFinder trả về một đối tượng System.Logger. Logger có thể là adapter mỏng quanh logger của backend. Khi nhận lệnh log, adapter chuyển level, message, tham số, ResourceBundle và Throwable sang API backend.

Có thể gọi trực tiếp System.LoggerFinder.getLoggerFinder() để lấy finder đang hoạt động. Lệnh này có thể kích hoạt việc nạp và khởi tạo logging system ngay lập tức. Trong code ứng dụng thông thường, hãy lấy logger bằng System.getLogger() và để runtime quản lý vòng đời khởi tạo.

Một JVM chỉ có một LoggerFinder cấp hệ thống. Các module và thư viện trong cùng runtime dùng finder đã được chọn đó.

## 3. System.Logger và các mức log

System.Logger cung cấp bảy mức theo thứ tự severity tăng dần:

| System.Logger.Level | Ý nghĩa thường dùng | java.util.logging.Level tương ứng |
|---|---|---|
| ALL | Cho phép mọi mức | ALL |
| TRACE | Thông tin chẩn đoán chi tiết | FINER |
| DEBUG | Thông tin debug | FINE |
| INFO | Thông tin vận hành | INFO |
| WARNING | Tình huống cần chú ý | WARNING |
| ERROR | Lỗi cần xử lý | SEVERE |
| OFF | Tắt mọi mức | OFF |

Đây là mapping severity chính thức của JDK khi dùng java.util.logging. Provider chuyển sang backend khác phải tự định nghĩa mapping tương đương, bảo đảm severity không bị đảo thứ tự hoặc làm mất mức cần thiết.

Các thao tác chính của System.Logger:

- getName() trả về tên logger.
- isLoggable(level) cho biết level hiện tại có được ghi hay không.
- log(level, message) ghi message.
- log(level, format, parameters) ghi message với tham số.
- log(level, message, throwable) gắn exception vào log event.
- log(level, supplier) tạo message theo kiểu lazy.
- Hai overload nhận ResourceBundle hỗ trợ localization.

Các overload đơn giản là default method và cuối cùng chuyển về hai phương thức log có ResourceBundle. Provider thường chỉ cần triển khai hai phương thức log nền tảng, getName() và isLoggable().

## 4. Message, tham số, localization và Supplier

Overload nhận format và parameters của System.Logger dùng quy tắc **MessageFormat**, không dùng cú pháp printf.

~~~java
System.Logger logger = System.getLogger("com.example.payment");

logger.log(System.Logger.Level.INFO,
        "Processed {0} payments for account {1}",
        new Object[] {12, "A-102"});
~~~

Khi chuyển tiếp sang backend, adapter nên giữ nguyên format và Object[] parameters nếu backend hỗ trợ message formatting. Không nên tự nối chuỗi hoặc format sớm nếu muốn backend thực hiện localization, formatting hoặc xử lý tham số theo cấu hình của nó.

Nếu có ResourceBundle, message được xem là key trong bundle:

~~~java
logger.log(System.Logger.Level.INFO, bundle,
        "payment.completed", new Object[] {paymentId});
~~~

Provider phải chuyển ResourceBundle và parameters sang backend. Nếu bỏ bundle, backend sẽ không thể dịch key theo locale như mong đợi.

System.LoggerFinder.getLocalizedLogger(name, bundle, module) mặc định gọi getLogger() rồi bọc logger để các lệnh log không truyền bundle sẽ dùng bundle đã cung cấp. Provider có thể override phương thức này nếu backend có cơ chế localization riêng. Supplier trả về một String đã được dựng sẵn mặc định không được xem như message key để dịch.

Supplier giúp tránh tạo message khi level đang bị tắt:

~~~java
logger.log(System.Logger.Level.DEBUG,
        () -> buildExpensiveDiagnosticMessage());
~~~

Default method chỉ gọi supplier nếu isLoggable(DEBUG) trả về true. Vì vậy, isLoggable() của adapter phải phản ánh đúng trạng thái backend. Nếu adapter trả true sai, công việc tạo message có thể xảy ra dù backend sẽ bỏ message.

## 5. LoggerFinder provider được nạp như thế nào?

Java Runtime duy trì một LoggerFinder duy nhất cho mỗi lần chạy JVM. Khi cần finder, runtime tìm provider tùy chỉnh bằng **ServiceLoader** với **system class loader**. Nếu không tìm thấy provider, runtime dùng implementation mặc định.

Implementation mặc định:

- Nếu module java.logging có mặt, backend là java.util.logging.
- Nếu java.logging không có mặt, runtime dùng simple logger ghi các message từ INFO trở lên ra System.err.

Logger được trả về không phải nơi cấu hình logging. Việc đặt level, handler, file output, formatter hoặc destination thuộc trách nhiệm backend. Với JUL, cấu hình bằng java.util.logging; với framework khác, dùng API hoặc cấu hình của framework đó.

Provider phải có constructor không tham số. Nên giữ constructor nhẹ, tránh khởi tạo kết nối, đọc file cấu hình lớn hoặc gọi logger khác trong constructor. Javadoc cảnh báo khởi tạo nặng có thể gây deadlock hoặc vòng lặp class loading khi service provider đang được tạo.

Không nên gọi System.getLogger() từ chính provider để ghi log nội bộ. Lệnh đó quay lại LoggerFinder đang khởi tạo và có thể tạo vòng lặp đệ quy. Provider cần dùng trực tiếp backend mà nó đang chuyển tiếp đến.

## 6. Đăng ký provider trên class path

Với provider đóng gói trên class path, ServiceLoader cần một provider-configuration file trong thư mục META-INF/services.

Đường dẫn file phải dùng **binary name** của service type. Vì LoggerFinder là nested class của System, tên file có dấu dollar:

~~~text
META-INF/services/java.lang.System$LoggerFinder
~~~

Nội dung file là tên đầy đủ của provider, mỗi provider một dòng. Với ví dụ trong bài:

~~~text
demo.logging.LoggerFinderDemo$Finder
~~~

Đặt file trong resource directory của JAR, ví dụ:

~~~text
src/main/resources/META-INF/services/java.lang.System$LoggerFinder
~~~

JAR chứa provider phải nằm trên class path khi khởi chạy JVM và provider phải nhìn thấy được từ system class loader. Một provider chỉ được nạp bởi child class loader riêng của ứng dụng có thể không được phát hiện bởi cơ chế này.

Trong một JVM, nên đóng gói một provider LoggerFinder được lựa chọn rõ ràng. Đừng dựa vào thứ tự không ổn định nếu nhiều JAR cùng khai báo các provider cạnh tranh.

## 7. Đăng ký provider trong named module

Nếu provider được đóng gói thành named module, khai báo service trong module-info.java:

~~~java
module demo.logging.provider {
    requires java.logging;

    provides java.lang.System.LoggerFinder
        with demo.logging.LoggerFinderDemo.Finder;
}
~~~

Tên service trong module descriptor dùng tên Java source với dấu chấm giữa System và LoggerFinder. Tên provider là tên đầy đủ của class provider; nếu provider là nested class static thì dùng dấu chấm trong module descriptor.

Module chứa provider cần được resolve vào module layer khởi động để system class loader có thể phát hiện provider. Khi triển khai bằng module path, bảo đảm module provider nằm trong module graph lúc JVM khởi chạy.

Classpath service descriptor và module-info provides là hai cách đóng gói khác nhau. Chọn cách phù hợp với kiểu triển khai của ứng dụng.

## 8. Vai trò của tham số Module

Phương thức SPI có chữ ký:

~~~java
System.Logger getLogger(String name, Module module)
~~~

Tham số module là module của caller đã yêu cầu logger. Đây là thông tin quan trọng vì log từ JDK hoặc module hệ thống có thể cần cách xử lý khác log từ ứng dụng.

Provider có thể dùng module để:

- Tách namespace backend theo module.
- Gắn module name vào metadata của log event.
- Áp dụng cấu hình hoặc routing riêng cho từng module.
- Phân biệt log của platform với log của ứng dụng nếu backend hỗ trợ.
- Giữ lại thông tin nguồn để phục vụ truy vết.

Module name chỉ là metadata định danh trong runtime. Không xem nó như một credential hoặc ranh giới phân quyền độc lập. Nếu backend cần kiểm soát quyền cấu hình hoặc truy cập log, chính backend phải thực thi policy đó.

Ví dụ trong bài thêm module name vào backend logger name. Khi caller thuộc unnamed module, tên được gắn tiền tố ALL-UNNAMED; khi caller ở named module, tên module được dùng làm tiền tố.

## 9. Thiết kế một dịch vụ chuyển tiếp đúng cách

Một forwarding provider nên giữ adapter đơn giản và chuyển đầy đủ thông tin log sang backend.

**Mapping level:** ánh xạ từng System.Logger.Level sang severity tương ứng của backend. Bảng mapping phải giữ thứ tự ALL, TRACE, DEBUG, INFO, WARNING, ERROR, OFF.

**isLoggable():** hỏi backend xem level có bật hay không. Default method của System.Logger dùng kết quả này để quyết định có gọi Supplier hay không.

**Parameters:** giữ nguyên message format và mảng tham số. Với JUL, có thể dùng LogRecord.setParameters() để formatter xử lý.

**ResourceBundle:** truyền bundle đến backend thay vì bỏ nó hoặc tự dịch bằng locale không đúng.

**Throwable:** gắn Throwable vào trường exception của log event. Không chuyển exception thành một tham số chuỗi vì backend có thể cần stack trace và cause chain.

**Module context:** lưu module hoặc đưa module name vào backend logger/metadata. Không bỏ qua module một cách vô tình.

**Thread safety:** logger adapter có thể được gọi đồng thời từ nhiều thread. Giữ adapter immutable và dùng backend có thread safety phù hợp.

**Lazy initialization:** constructor của finder nên nhẹ. Khởi tạo backend ở thời điểm thích hợp và tránh phụ thuộc vào việc logging đã sẵn sàng trong giai đoạn bootstrap.

**Tránh vòng lặp:** bên trong provider, gọi API backend đích trực tiếp. Không gọi System.getLogger() hoặc lấy lại LoggerFinder để chuyển tiếp message.

**Source attribution:** System.Logger không truyền source class và method trong các overload log. Một backend có thể tự suy luận caller và nhìn thấy adapter là caller. Nếu cần source attribution chính xác, adapter phải dùng API chuyên biệt của backend hoặc cơ chế lấy caller có chủ đích, sau khi cân nhắc chi phí.

## 10. Ví dụ hoàn chỉnh: LoggerFinder chuyển tiếp sang JUL

Ví dụ dưới đây triển khai một provider dùng java.util.logging làm backend. Provider dùng module name để tạo namespace backend, ánh xạ level, giữ ResourceBundle, parameters và Throwable.

Đặt source tại:

~~~text
src/main/java/demo/logging/LoggerFinderDemo.java
~~~

~~~java
package demo.logging;

import java.util.Objects;
import java.util.ResourceBundle;
import java.util.ListResourceBundle;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.Formatter;

public class LoggerFinderDemo {
    public static final class Finder extends System.LoggerFinder {
        @Override
        public System.Logger getLogger(String name, Module module) {
            Objects.requireNonNull(name);
            Objects.requireNonNull(module);
            String moduleName = module.isNamed()
                    ? module.getName() : "ALL-UNNAMED";
            return new JulSystemLogger(
                    name, Logger.getLogger(moduleName + "." + name));
        }
    }

    private static final class JulSystemLogger implements System.Logger {
        private final String name;
        private final Logger backend;

        JulSystemLogger(String name, Logger backend) {
            this.name = name;
            this.backend = backend;
        }

        @Override
        public String getName() {
            return name;
        }

        @Override
        public boolean isLoggable(System.Logger.Level level) {
            return backend.isLoggable(toJulLevel(level));
        }

        @Override
        public void log(System.Logger.Level level, ResourceBundle bundle,
                        String message, Throwable thrown) {
            if (!isLoggable(level)) {
                return;
            }
            LogRecord record = new LogRecord(toJulLevel(level), message);
            record.setLoggerName(backend.getName());
            record.setResourceBundle(bundle);
            record.setThrown(thrown);
            backend.log(record);
        }

        @Override
        public void log(System.Logger.Level level, ResourceBundle bundle,
                        String format, Object... parameters) {
            if (!isLoggable(level)) {
                return;
            }
            LogRecord record = new LogRecord(toJulLevel(level), format);
            record.setLoggerName(backend.getName());
            record.setResourceBundle(bundle);
            record.setParameters(parameters);
            backend.log(record);
        }

        private static java.util.logging.Level toJulLevel(
                System.Logger.Level level) {
            switch (level) {
                case ALL: return java.util.logging.Level.ALL;
                case TRACE: return java.util.logging.Level.FINER;
                case DEBUG: return java.util.logging.Level.FINE;
                case INFO: return java.util.logging.Level.INFO;
                case WARNING: return java.util.logging.Level.WARNING;
                case ERROR: return java.util.logging.Level.SEVERE;
                case OFF: return java.util.logging.Level.OFF;
                default: throw new AssertionError(level);
            }
        }
    }

    public static final class Messages extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                {"connected", "connected to {0}"}
            };
        }
    }

    public static void main(String[] args) {
        Logger root = Logger.getLogger("");
        root.setLevel(java.util.logging.Level.ALL);
        for (Handler handler : root.getHandlers()) {
            handler.setLevel(java.util.logging.Level.ALL);
            handler.setFormatter(new Formatter() {
                @Override
                public String format(LogRecord record) {
                    String text = formatMessage(record);
                    Throwable thrown = record.getThrown();
                    if (thrown != null) {
                        text += " (" + thrown.getClass().getSimpleName() + ")";
                    }
                    return record.getLevel().getName() + " "
                            + record.getLoggerName() + " "
                            + text + System.lineSeparator();
                }
            });
        }

        System.out.println("finder: " +
                System.LoggerFinder.getLoggerFinder().getClass().getName());

        System.Logger logger = System.getLogger("demo");
        logger.log(System.Logger.Level.INFO, "startup complete");
        logger.log(System.Logger.Level.DEBUG,
                "cache hit {0}", new Object[] {3});
        logger.log(System.Logger.Level.INFO, new Messages(),
                "connected", new Object[] {"database"});
        logger.log(System.Logger.Level.ERROR, "request failed",
                new IllegalStateException("offline"));

        AtomicInteger supplierCalls = new AtomicInteger();
        logger.log(System.Logger.Level.DEBUG, () -> {
            supplierCalls.incrementAndGet();
            return "lazy diagnostic";
        });
        System.out.println("supplier calls: " + supplierCalls.get());
    }
}
~~~

Class Finder là public static nested class và có constructor không tham số mặc định. Class JulSystemLogger triển khai hai overload log nền tảng cùng getName() và isLoggable(); các overload còn lại được System.Logger cung cấp dưới dạng default method.

## 11. Biên dịch, đăng ký và chạy ví dụ

Biên dịch source với Java 9 API:

~~~bash
javac --release 9 -d out src/main/java/demo/logging/LoggerFinderDemo.java
~~~

Tạo service descriptor:

~~~text
out/META-INF/services/java.lang.System$LoggerFinder
~~~

Nội dung file:

~~~text
demo.logging.LoggerFinderDemo$Finder
~~~

Sau khi resource đã được copy vào thư mục out, chạy:

~~~bash
java -cp out demo.logging.LoggerFinderDemo
~~~

Kết quả stdout:

~~~text
finder: demo.logging.LoggerFinderDemo$Finder
INFO ALL-UNNAMED.demo startup complete
FINE ALL-UNNAMED.demo cache hit 3
INFO ALL-UNNAMED.demo connected to database
SEVERE ALL-UNNAMED.demo request failed (IllegalStateException)
FINE ALL-UNNAMED.demo lazy diagnostic
supplier calls: 1
~~~

Kết quả cho thấy:

- Runtime đã nạp Finder tùy chỉnh từ service descriptor.
- INFO được ánh xạ sang JUL INFO.
- DEBUG được ánh xạ sang JUL FINE.
- ResourceBundle được dùng để dịch key connected thành connected to database.
- Throwable vẫn được giữ trong LogRecord.
- Supplier được gọi khi DEBUG đang bật.

Nếu chạy cùng provider trong named module, logger name ở backend sẽ có prefix là tên module thay vì ALL-UNNAMED. Ví dụ module demo.logging.provider tạo backend logger demo.logging.provider.demo.

## 12. Triển khai cùng named module

Có thể dùng cùng source code nhưng thay service descriptor bằng module-info.java:

~~~java
module demo.logging.provider {
    requires java.logging;

    provides java.lang.System.LoggerFinder
        with demo.logging.LoggerFinderDemo.Finder;
}
~~~

Biên dịch module:

~~~bash
javac --release 9 -d out \
    src/module-info.java \
    src/main/java/demo/logging/LoggerFinderDemo.java
~~~

Chạy module provider:

~~~bash
java --module-path out \
    -m demo.logging.provider/demo.logging.LoggerFinderDemo
~~~

Trong module descriptor, provider được khai báo bằng tên Java source demo.logging.LoggerFinderDemo.Finder. Nếu đóng gói dạng JAR, module descriptor phải nằm ở root của modular JAR và module provider phải được resolve khi khởi chạy.

## 13. Khi nào cần provider tùy chỉnh?

Nếu ứng dụng chỉ cần log của JDK qua java.util.logging, provider mặc định đã thực hiện việc chuyển tiếp đó khi module java.logging có mặt. Không cần tạo LoggerFinder mới chỉ để làm lại cùng một đường đi.

Provider tùy chỉnh hữu ích khi ứng dụng muốn:

- Chuyển log từ System.Logger sang SLF4J hoặc Log4j 2.
- Gom log từ JDK, thư viện và framework vào một backend.
- Áp dụng naming convention hoặc routing theo module.
- Dùng cùng cấu hình level và destination cho log platform và log ứng dụng.
- Bổ sung metadata của module hoặc context runtime vào log event.

Trong triển khai thực tế, thay phần JulSystemLogger bằng adapter của backend mục tiêu. Không cần thay đổi code gọi System.getLogger() trong thư viện.

Nếu backend có bridge JUL-to-SLF4J hoặc SLF4J-to-JUL, hãy kiểm tra hướng bridge để tránh vòng lặp. Ví dụ, provider chuyển System.Logger sang JUL, trong khi JUL handler lại chuyển về một facade gọi ngược System.Logger, có thể tạo vòng lặp ghi log. Chỉ thiết lập một hướng chuyển tiếp rõ ràng.

## 14. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đặt sai tên service descriptor | ServiceLoader không tìm thấy provider | Dùng chính xác META-INF/services/java.lang.System$LoggerFinder |
| Dùng dấu chấm thay dấu dollar trong tên file service | Sai binary name của nested service type | Tên file dùng java.lang.System$LoggerFinder |
| Provider không public hoặc không có constructor không tham số | ServiceLoader không thể khởi tạo provider | Dùng class public và constructor không tham số |
| Đặt provider chỉ trong child class loader | System class loader không nhìn thấy provider | Đặt provider trên class path hoặc module path lúc khởi chạy |
| Có nhiều provider cạnh tranh | Backend được chọn có thể không như dự kiến | Chỉ đóng gói một provider được chọn rõ ràng |
| Khởi tạo backend nặng trong constructor | Có nguy cơ deadlock hoặc class loading cycle | Giữ constructor nhẹ và khởi tạo backend khi cần |
| Gọi System.getLogger() bên trong provider | Có thể quay lại chính LoggerFinder và gây recursion | Gọi trực tiếp facade của backend |
| Mapping level sai | DEBUG có thể bị nâng thành INFO hoặc ERROR bị hạ severity | Ánh xạ theo severity và kiểm thử từng mức |
| isLoggable() không khớp backend | Supplier chạy thừa hoặc log bị mất | Lấy trạng thái từ backend và kiểm tra lại khi ghi |
| Format message bằng printf | Placeholder không được xử lý theo MessageFormat | Dùng MessageFormat semantics hoặc để backend format |
| Bỏ ResourceBundle hoặc parameters | Mất localization và dữ liệu format | Chuyển bundle cùng parameters sang backend |
| Chuyển Throwable thành chuỗi | Mất exception object và stack trace | Đặt Throwable vào trường exception của log event |
| Bỏ qua module parameter | Mất khả năng phân biệt nguồn log theo module | Giữ module trong logger namespace hoặc metadata |
| Cấu hình qua System.Logger | API không cung cấp cấu hình backend tổng quát | Cấu hình qua API riêng của backend |
| Dùng LoggerFinder làm facade nghiệp vụ duy nhất | Thiếu các tính năng riêng của framework | Dùng facade backend cho log nghiệp vụ, LoggerFinder cho Platform Logging API |

## 15. Ghi nhớ

- System.Logger và System.LoggerFinder được giới thiệu trong Java 9 qua JEP 264.
- LoggerFinder là service provider tạo System.Logger và nối nó với backend.
- Mỗi JVM chỉ có một LoggerFinder cấp hệ thống.
- Runtime tìm provider bằng ServiceLoader và system class loader; không tìm thấy thì dùng implementation mặc định.
- Default backend là java.util.logging nếu module java.logging có mặt; nếu không, simple logger ghi INFO trở lên ra System.err.
- Classpath provider dùng META-INF/services/java.lang.System$LoggerFinder; modular provider dùng provides java.lang.System.LoggerFinder with ...
- getLogger(name, module) nhận module của caller; provider nên giữ context này.
- Map level theo severity, giữ ResourceBundle, parameters và Throwable.
- isLoggable() phải phản ánh backend để lazy Supplier hoạt động đúng.
- Không gọi System.getLogger() từ bên trong provider và tránh khởi tạo nặng khi service được nạp.
- Cấu hình logging thuộc backend; System.LoggerFinder không phải API cấu hình framework.
- Dùng LoggerFinder để chuyển tiếp Platform Logging API; dùng facade của framework cho log nghiệp vụ.
- Kiểm tra bridge direction để tránh vòng lặp giữa JUL, SLF4J và Log4j.

## Tài liệu tham khảo

- [JEP 264 — Platform Logging API and Service](https://openjdk.org/jeps/264)
- [System.LoggerFinder — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/System.LoggerFinder.html)
- [System.LoggerFinder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.LoggerFinder.html)
- [System.Logger — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/System.Logger.html)
- [System.Logger — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.Logger.html)
- [System.Logger.Level — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.Logger.Level.html)
- [System — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html)
- [ServiceLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [java.util.logging — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/package-summary.html)
