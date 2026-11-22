# Chọn đầu ra stdout, stderr hoặc tệp

Trong JVM, logging có thể được gửi tới standard output (`stdout`), standard error (`stderr`) hoặc một hay nhiều tệp log. Với Java Logging API (`java.util.logging`, thường gọi là JUL), việc định tuyến được thực hiện qua `Handler`: `ConsoleHandler` ghi ra console theo quy ước của JUL là `System.err`, còn `FileHandler` ghi ra tệp. Nếu muốn ghi riêng ra `System.out`, có thể dùng `StreamHandler` với output stream là `System.out`.

Chọn đích log là quyết định vận hành. Ứng dụng chạy trong container thường để runtime thu thập stdout/stderr; dịch vụ chạy trên máy chủ có thể cần file rotation và chính sách lưu trữ. Có thể gửi cùng một record tới nhiều handler, nhưng phải kiểm soát mức log, duplicate propagation, quyền ghi tệp và vòng đời handler.

## Mục tiêu

- Phân biệt stdout, stderr và file output.
- Hiểu vai trò của `Logger`, `Handler`, `Formatter`, `Filter` và `LogRecord` trong JUL.
- Biết `ConsoleHandler` ghi vào stderr.
- Tạo handler ghi vào stdout bằng `StreamHandler`.
- Ghi log ra file bằng `FileHandler` và cấu hình rotation.
- Chọn một đích hoặc fan-out cùng record tới nhiều đích.
- Kiểm soát logger level, handler level và parent handlers.
- Cấu hình logging bằng code hoặc `logging.properties`.
- Hiểu `System.Logger` trong Java 9 và quan hệ với backend.
- Đóng handler đúng cách và tránh mất log hoặc rò rỉ file descriptor.

## 1. Ba đích đầu ra

| Đích | Vai trò thường gặp | Cách ghi trong JUL |
| --- | --- | --- |
| `stdout` | Thông tin vận hành, output được nền tảng/container thu thập | `StreamHandler(System.out, formatter)` |
| `stderr` | Cảnh báo, lỗi và chẩn đoán | `ConsoleHandler` |
| File | Lưu log cục bộ, rotation và lưu trữ theo chính sách | `FileHandler` |

`stdout` và `stderr` là hai luồng output chuẩn của process. Chúng có thể được shell, service manager, IDE hoặc container runtime thu thập và chuyển hướng. File output được ghi trực tiếp vào đường dẫn mà ứng dụng hoặc cấu hình logging chỉ định.

Không có một đích luôn đúng cho mọi môi trường. Hãy chọn theo nơi vận hành thu thập log, chính sách retention, quyền filesystem và cách triển khai ứng dụng.

## 2. Kiến trúc logging của java.util.logging

JUL tách nơi phát sinh log khỏi nơi ghi log:

- `Logger` tạo `LogRecord` với level, message, logger name, thời điểm và thông tin nguồn nếu có.
- `Handler` nhận record và quyết định nơi ghi.
- `Formatter` chuyển record thành chuỗi hoặc dạng trình bày phù hợp.
- `Filter` có thể loại record trước khi logger hoặc handler xử lý.
- `Level` quyết định ngưỡng record được chấp nhận.

Một logger có thể gắn nhiều handler. Khi một record được log, handler của logger xử lý record; theo mặc định, record còn có thể truyền lên parent logger. Vì vậy cùng một record có thể xuất hiện nhiều lần nếu vừa gắn handler trực tiếp vừa để propagation tới root logger.

## 3. Ghi ra stderr bằng ConsoleHandler

`ConsoleHandler` là handler console chuẩn của JUL và ghi vào `System.err`. Đây là lựa chọn phù hợp cho cảnh báo và lỗi khi môi trường chạy thu thập stderr riêng.

~~~java
Logger logger = Logger.getLogger("com.example.service");
ConsoleHandler handler = new ConsoleHandler();
handler.setLevel(Level.WARNING);
handler.setFormatter(new SimpleFormatter());

logger.addHandler(handler);
logger.setLevel(Level.ALL);
logger.setUseParentHandlers(false);

logger.warning("disk usage is high");
~~~

Trong ví dụ, handler chỉ nhận record từ `WARNING` trở lên. `logger.setLevel(Level.ALL)` cho phép logger chuyển các level tới handler; ngưỡng của handler tiếp tục lọc record.

`ConsoleHandler` không có tham số chọn stdout hay stderr. Theo hợp đồng API, nó dùng `System.err`. Nếu muốn stdout, tạo `StreamHandler` với `System.out` như phần tiếp theo.

## 4. Ghi ra stdout bằng StreamHandler

`StreamHandler` ghi record vào một `OutputStream`. Có thể truyền `System.out` và formatter mong muốn:

~~~java
StreamHandler handler = new StreamHandler(System.out, new SimpleFormatter());
~~~

Để publish và flush ngay sau mỗi record, tạo subclass nhỏ:

~~~java
private static final class StdoutHandler extends StreamHandler {
    StdoutHandler() {
        super(System.out, new SimpleFormatter());
    }

    @Override
    public synchronized void publish(LogRecord record) {
        super.publish(record);
        flush();
    }

    @Override
    public synchronized void close() {
        flush();
    }
}
~~~

`StreamHandler` thường buffer output; gọi `flush()` sau `publish()` giúp record xuất hiện kịp thời khi process hoặc collector đọc stdout. `close()` ở subclass chỉ flush, không đóng `System.out`, vì đây là stream chuẩn do JVM/runtime quản lý chứ không phải stream riêng của handler.

Nếu không cần flush sau mỗi record, có thể flush theo batch để giảm chi phí I/O. Cần cân bằng độ trễ quan sát với thông lượng.

## 5. Ghi ra file bằng FileHandler

`FileHandler` ghi log vào tệp và hỗ trợ giới hạn dung lượng cùng rotation:

~~~java
Files.createDirectories(Paths.get("logs"));

FileHandler handler = new FileHandler(
    "logs/application-%g.log",
    1024 * 1024,
    3,
    true
);
handler.setLevel(Level.ALL);
handler.setFormatter(new SimpleFormatter());

Logger logger = Logger.getLogger("com.example.file");
logger.setUseParentHandlers(false);
logger.addHandler(handler);
logger.info("application started");

handler.flush();
handler.close();
~~~

Constructor bốn tham số có ý nghĩa:

| Tham số | Ý nghĩa |
| --- | --- |
| `pattern` | Mẫu đường dẫn tệp log |
| `limit` | Giới hạn dung lượng mỗi file, tính bằng byte; `0` nghĩa là không giới hạn |
| `count` | Số file generation được quản lý; phải ít nhất là 1 |
| `append` | Có nối thêm vào file hiện có hay bắt đầu file mới |

Trong pattern, `%g` là số generation dùng cho rotation. Ví dụ `application-%g.log` có thể tạo `application-0.log`, `application-1.log` và `application-2.log`. Khi file đạt giới hạn, handler chuyển sang generation tiếp theo theo chính sách của `FileHandler`.

`FileHandler` có thể cần tạo lock file và cần quyền ghi vào thư mục. Hãy tạo thư mục trước, kiểm tra quyền filesystem và xử lý `IOException`/`SecurityException` ở bước khởi tạo. Đường dẫn tương đối được tính từ working directory của process; trong production, nên cấu hình đường dẫn rõ ràng.

## 6. Gửi một record tới một hoặc nhiều đích

JUL cho phép một logger gắn nhiều handler. Điều này hữu ích khi muốn tee cùng một record tới console và file:

~~~java
logger.addHandler(new ConsoleHandler());
logger.addHandler(new FileHandler("logs/app-%g.log", 0, 1, true));
~~~

Trong trường hợp đó, mỗi handler có formatter và level riêng. Một record có thể được ghi ra cả stderr và file. Nếu muốn chọn đúng một đích cho từng nhóm log, có thể dùng logger riêng hoặc cấu hình handler/filter theo loại record.

Không tạo handler cho mỗi lần gọi log. Tạo và cấu hình handler một lần trong giai đoạn khởi động, sau đó tái sử dụng. Nhiều handler trùng nhau làm tăng I/O, có thể tạo log duplicate và giữ file descriptor không cần thiết.

## 7. Logger level, Handler level và propagation

Để một record được ghi, nó phải vượt qua ngưỡng level của logger và handler. Ví dụ logger ở `INFO` sẽ không chuyển record `FINE` tới handler, kể cả handler đang đặt `ALL`.

| Level | Ý nghĩa khái quát |
| --- | --- |
| `SEVERE` | Lỗi nghiêm trọng |
| `WARNING` | Cảnh báo cần chú ý |
| `INFO` | Thông tin vận hành |
| `CONFIG` | Thông tin cấu hình |
| `FINE`, `FINER`, `FINEST` | Chi tiết chẩn đoán tăng dần |
| `ALL` | Chấp nhận mọi level |
| `OFF` | Tắt log |

Ví dụ đặt ngưỡng khác nhau:

~~~java
logger.setLevel(Level.INFO);
consoleHandler.setLevel(Level.WARNING);
fileHandler.setLevel(Level.FINE);
~~~

Logger không chuyển record `FINE` vì ngưỡng logger là `INFO`; file handler đặt `FINE` không thể nhận record đã bị logger loại.

### 7.1. Tránh ghi duplicate qua parent logger

Logger có tên phân cấp theo dấu chấm. Theo mặc định, record có thể được chuyển tới parent logger và root logger. Nếu ứng dụng tự gắn handler trực tiếp nhưng vẫn để parent handlers hoạt động, record có thể được ghi thêm lần nữa bởi handler ở cấp cha.

~~~java
logger.setUseParentHandlers(false);
~~~

Dùng dòng này khi logger chịu trách nhiệm hoàn toàn về các handler của nó. Nếu muốn kế thừa cấu hình root logger, không tắt propagation và tránh gắn thêm handler trùng.

## 8. Cấu hình bằng logging.properties

JUL có thể được cấu hình bằng file properties thay vì tạo handler bằng code. Ví dụ cấu hình console stderr và file rotation:

~~~properties
handlers=java.util.logging.ConsoleHandler,java.util.logging.FileHandler
.level=INFO

java.util.logging.ConsoleHandler.level=WARNING
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

java.util.logging.FileHandler.level=ALL
java.util.logging.FileHandler.pattern=logs/application-%g.log
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=3
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
~~~

Khởi chạy JVM với file cấu hình:

~~~text
java -Djava.util.logging.config.file=logging.properties -jar application.jar
~~~

Property phải được thiết lập trước khi JUL khởi tạo `LogManager` và đọc cấu hình. Nếu ứng dụng cần nạp lại cấu hình lúc chạy, có thể dùng `LogManager.readConfiguration(InputStream)` theo lifecycle được kiểm soát.

Cấu hình mẫu trên dùng `ConsoleHandler`, nên console output là stderr. Để đưa log ra stdout, cần handler dựa trên `StreamHandler` và cấu hình class handler phù hợp, hoặc tạo handler trong code như ví dụ runnable.

## 9. System.Logger trong Java 9

Java 9 bổ sung `System.Logger` như một logging facade trong JDK:

~~~java
System.Logger logger = System.getLogger("com.example.service");
logger.log(System.Logger.Level.INFO, "application started");
logger.log(System.Logger.Level.WARNING, "disk usage high");
~~~

`System.Logger` cho phép code sử dụng API logging của JDK mà không phụ thuộc trực tiếp vào các lớp JUL. `System.LoggerFinder` xác định provider cung cấp logger. Đích stdout/stderr/file do provider hoặc backend cấu hình quyết định; bản thân `System.Logger` không cung cấp phương thức gắn `ConsoleHandler` hay `FileHandler`.

Nếu cần cấu hình đích log trực tiếp bằng JUL, dùng `Logger` và `Handler`. Nếu thư viện cần một facade ổn định và để ứng dụng chọn provider, `System.Logger` là lựa chọn phù hợp từ Java 9.

## 10. Phân biệt logging với System.out và System.err

`System.out.println()` và `System.err.println()` ghi trực tiếp ra stream chuẩn, không tạo `LogRecord`. Chúng không tự cung cấp level, logger name, formatter, filter, rotation hoặc cấu hình handler.

~~~java
System.out.println("plain output");
System.err.println("diagnostic output");
~~~

Đây là cách hợp lệ cho output CLI mà người dùng cần đọc, nhưng với log vận hành nên dùng logging framework để có level và metadata.

`System.setOut()` và `System.setErr()` thay stream chuẩn toàn cục của JVM. Không dùng chúng để định tuyến log riêng cho một class hoặc một logger vì mọi thành phần trong process đều bị ảnh hưởng và có thể phát sinh vấn đề đồng bộ.

Shell và container cũng có thể chuyển hướng hai stream ở bên ngoài JVM:

~~~text
java -jar application.jar > application.out 2> application.err
~~~

Trong ví dụ trên, stdout và stderr được chuyển thành hai file bởi shell. Đây là cơ chế chuyển hướng process, khác với `FileHandler` tự quản lý file và rotation bên trong ứng dụng.

## 11. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ sau tạo ba logger độc lập:

- Logger `demo.stdout` gửi `INFO` tới `System.out` qua `StreamHandler` tùy chỉnh.
- Logger `demo.stderr` gửi `WARNING` tới `System.err` qua `ConsoleHandler`.
- Logger `demo.file` gửi `SEVERE` tới file qua `FileHandler` có rotation.

Parent handlers được tắt để tránh record bị ghi thêm qua root logger. Handler được detach và đóng trong `finally`; stdout handler chỉ flush, không đóng `System.out`.

**Tệp:** `LoggingOutputDemo.java`

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggingOutputDemo {
    private static final class CompactFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName() + " "
                + formatMessage(record) + System.lineSeparator();
        }
    }

    private static final class StdoutHandler extends StreamHandler {
        StdoutHandler() {
            super(System.out, new CompactFormatter());
            setLevel(Level.ALL);
        }

        @Override
        public synchronized void publish(LogRecord record) {
            super.publish(record);
            flush();
        }

        @Override
        public synchronized void close() {
            flush();
        }
    }

    private static Logger loggerFor(String name, Handler handler) {
        Logger logger = Logger.getLogger(name);
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        logger.addHandler(handler);
        return logger;
    }

    public static void main(String[] args) throws IOException {
        Path logDirectory = Paths.get("logs");
        Files.createDirectories(logDirectory);

        CompactFormatter formatter = new CompactFormatter();
        StdoutHandler stdoutHandler = new StdoutHandler();

        ConsoleHandler stderrHandler = new ConsoleHandler();
        stderrHandler.setLevel(Level.ALL);
        stderrHandler.setFormatter(formatter);

        Path logPattern = logDirectory.resolve("application-%g.log");
        Handler fileHandler = new java.util.logging.FileHandler(
            logPattern.toString(), 1024 * 1024, 3, true);
        fileHandler.setLevel(Level.ALL);
        fileHandler.setFormatter(formatter);

        Logger stdoutLogger = loggerFor("demo.stdout", stdoutHandler);
        Logger stderrLogger = loggerFor("demo.stderr", stderrHandler);
        Logger fileLogger = loggerFor("demo.file", fileHandler);

        try {
            stdoutLogger.info("application started");
            stderrLogger.warning("disk usage high");
            fileLogger.severe("database unavailable");
        } finally {
            stdoutLogger.removeHandler(stdoutHandler);
            stderrLogger.removeHandler(stderrHandler);
            fileLogger.removeHandler(fileHandler);
            stdoutHandler.close();
            stderrHandler.close();
            fileHandler.close();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~text
javac --release 9 LoggingOutputDemo.java
java LoggingOutputDemo
~~~

Output trên stdout:

~~~text
INFO application started
~~~

Output trên stderr:

~~~text
WARNING disk usage high
~~~

Nội dung file `logs/application-0.log`:

~~~text
SEVERE database unavailable
~~~

Trong môi trường terminal, stdout và stderr có thể được hiển thị cùng cửa sổ nên nhìn giống một luồng. Khi cần kiểm chứng, chuyển hướng chúng riêng như lệnh `java ... 1>stdout.txt 2>stderr.txt`, rồi kiểm tra file log độc lập.

## 12. Vòng đời Handler và đóng tài nguyên

`FileHandler` giữ tài nguyên file và lock trong thời gian hoạt động. Khi ứng dụng kết thúc một logger hoặc thay cấu hình, cần:

1. Ngừng gửi record mới tới handler.
2. Gỡ handler khỏi logger bằng `removeHandler()` nếu không dùng nữa.
3. Gọi `flush()` khi cần đẩy dữ liệu buffer.
4. Gọi `close()` để giải phóng tài nguyên handler.

Không đóng `System.out` hoặc `System.err` do JVM quản lý. Với handler tự tạo trên `System.out`, override `close()` để flush nhưng giữ stream chuẩn mở. Với `FileHandler`, gọi `close()` để đóng file và giải phóng lock.

Không tạo và đóng FileHandler cho từng record. Chi phí mở file, lock và formatter có thể lớn; đồng thời rotation và thứ tự ghi trở nên khó kiểm soát.

## 13. Lưu ý vận hành và bảo mật

- Chỉ ghi thông tin cần thiết để chẩn đoán; không ghi password, token, secret hoặc dữ liệu cá nhân nhạy cảm.
- Dùng log level phù hợp; tránh bật `FINEST` liên tục trong production nếu lượng log lớn.
- Đặt giới hạn file, số generation và chính sách lưu trữ; giám sát dung lượng đĩa.
- Đảm bảo user chạy JVM có quyền ghi thư mục log.
- Chọn đường dẫn ổn định, không dựa vào working directory tình cờ của IDE.
- Dùng formatter nhất quán; thêm timestamp, thread name, correlation ID nếu hệ thống cần truy vết.
- Nếu log được thu thập bởi container, thường để process ghi stdout/stderr và để nền tảng xử lý rotation/retention.
- Nếu dùng file, xác định ai rotate, ai archive và cách xử lý file lock.
- Không để hai framework cùng cấu hình handler cho cùng logger nếu không có chủ đích.
- Kiểm tra cả logger level và handler level khi một record không xuất hiện.

## 14. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mong `ConsoleHandler` ghi stdout | ConsoleHandler của JUL ghi `System.err` | Dùng `StreamHandler(System.out, formatter)` |
| Log xuất hiện hai lần | Parent logger cũng nhận record | Kiểm tra `setUseParentHandlers(false)` và root handlers |
| Không thấy log `FINE` | Logger level chặn trước handler | Kiểm tra cả logger level và handler level |
| File log không tạo được | Thư mục chưa tồn tại hoặc thiếu quyền ghi | Tạo thư mục và xử lý `IOException`/`SecurityException` |
| File tăng không giới hạn | Không cấu hình rotation | Dùng `FileHandler` limit/count hoặc hệ thống rotate bên ngoài |
| Mất log cuối khi process dừng | Buffer chưa flush hoặc handler chưa close | Flush/close trong lifecycle shutdown được kiểm soát |
| Đóng `System.out` khi đóng handler | Handler đóng stream chuẩn dùng chung | Override close chỉ flush cho stdout handler |
| Log file bị giữ lock | FileHandler chưa được close | Gỡ handler và close khi ngừng sử dụng |
| Gọi `System.setOut()` để đổi đích một logger | Thay đổi stream toàn cục | Định tuyến bằng handler riêng |
| Cấu hình properties không có tác dụng | JUL đã khởi tạo trước khi property được đặt | Đặt `java.util.logging.config.file` lúc khởi chạy JVM |
| Cùng record vừa console vừa file ngoài ý muốn | Gắn nhiều handler hoặc propagation | Kiểm tra handler trực tiếp và parent hierarchy |

## 15. Quy tắc thực hành

1. Dùng `ConsoleHandler` khi muốn JUL ghi vào stderr.
2. Dùng `StreamHandler` với `System.out` khi muốn stdout; flush theo chính sách latency/throughput.
3. Dùng `FileHandler` khi cần file output và rotation do ứng dụng quản lý.
4. Chọn một đích hoặc nhiều handler có chủ đích; tránh duplicate propagation.
5. Đặt logger level và handler level theo cùng một chính sách rõ ràng.
6. Cấu hình logging trước khi logger được sử dụng lần đầu.
7. Tạo handler một lần, tái sử dụng và đóng đúng lifecycle.
8. Không đóng stream chuẩn do JVM quản lý.
9. Với container, cân nhắc stdout/stderr để nền tảng thu thập; với file, quản lý quota và retention.
10. Không ghi secret hoặc dữ liệu nhạy cảm vào bất kỳ đích log nào.
11. Dùng `System.Logger` khi cần facade; cấu hình backend/provider để quyết định đích.
12. Kiểm chứng riêng stdout, stderr và file khi test cấu hình logging.

## 16. Tự kiểm tra

- `ConsoleHandler` của JUL ghi vào đâu? `System.err`.
- Muốn JUL ghi stdout thì dùng gì? `StreamHandler` gắn với `System.out`.
- `FileHandler` hỗ trợ gì ngoài ghi file? Giới hạn dung lượng và rotation qua pattern/limit/count.
- `%g` trong pattern là gì? Số generation của file rotation.
- Vì sao cần `setUseParentHandlers(false)`? Để tránh record truyền lên parent/root và bị ghi duplicate khi logger có handler riêng.
- Record có thể bị chặn ở những đâu? Logger level, filter và handler level/filter.
- Có nên đóng `System.out` trong `Handler.close()` không? Không; chỉ flush stream chuẩn.
- `System.setOut()` có thay đổi riêng một logger không? Không, nó thay stream chuẩn toàn cục.
- `System.Logger` có API gắn FileHandler không? Không; provider/backend quyết định đích log.
- Khi nào nên dùng stdout/stderr trong container? Khi runtime hoặc agent thu thập process streams.
- Khi nào cần FileHandler? Khi ứng dụng phải tự quản lý file log và rotation.

Điểm cốt lõi: **Trong JUL, `ConsoleHandler` ghi stderr, `StreamHandler` có thể ghi stdout và `FileHandler` ghi tệp.** Chọn handler theo môi trường chạy, kiểm soát level/propagation và đóng handler đúng vòng đời.