# Kiểm thử exception trong Java Core Logging

## Mục tiêu học tập

Bài thuộc nhóm **Testing logging**, chủ đề **Kiểm thử exception**. Khi một ứng dụng Java gặp exception, hệ thống logging phải cung cấp đủ dấu vết để điều tra mà không tạo thông tin sai, ghi trùng quá nhiều lần hoặc tiết lộ dữ liệu nhạy cảm. Một phép kiểm thử chỉ tìm chuỗi `"ERROR"` trong console thường không đủ: exception có thể bị log sai level, mất `Throwable`/stack trace, bị lọc ở appender, ghi trùng vì nhiều tầng cùng log, hoặc đến backend trễ qua pipeline async.

Sau bài này, bạn có thể:

- Phân biệt kiểm thử **exception được ném**, **exception được bắt/xử lý** và **exception được ghi log**.
- Xác minh `level`, logger name, event code, message template/structured fields, exception class, `Throwable`, cause chain và suppressed exceptions.
- Hiểu khi nào nên ghi `ERROR`/`WARN`, khi nào exception được xử lý thành công nên không tạo log lỗi giả.
- Viết bài kiểm thử Java 17 chỉ dùng JDK để thu `java.util.logging.LogRecord` bằng `Handler` và khẳng định kết quả chính xác.
- Dùng `ListAppender` của Logback với JUnit 5 để kiểm tra event mà không dựa vào text của console; nhận diện khác biệt khi backend là Log4j 2.
- Phát hiện duplicate logs, log trùng stack trace, lỗi MDC/correlation, log injection, lộ secret và thay đổi ngoài ý muốn về cách encode stack trace.
- Kiểm thử logging bất đồng bộ theo deadline và kiểm tra đường log từ logger tới appender, collector/index.
- Xây dựng test matrix cho lỗi nghiệp vụ, rollback, retry, exception chain, failure in logging sink và regression.

**Nguyên tắc cốt lõi:** Test phải chứng minh điều hệ thống **thực sự phát ra** và điều hệ thống **không được phép phát ra**. Một exception được ném chưa chắc đã được log; một event log tồn tại chưa chắc đã tới hệ thống giám sát; một dòng `ERROR` không chứng minh rằng stack trace hoặc ngữ cảnh đã đúng.

## 1. Ba thứ khác nhau: throw, handle và log

Trong Java:

- **Throw:** `throw new IllegalStateException(...)` chuyển quyền điều khiển qua exception propagation.
- **Handle:** `catch` xử lý, chuyển thành kết quả khác, retry, bù trừ hoặc rethrow. Việc bắt exception không mặc nhiên có nghĩa lỗi đã được khắc phục.
- **Log:** logger được gọi và logging pipeline có thể tạo `LogRecord`/`LoggingEvent` rồi gửi tới handler/appender/sink.

Ba hoạt động này độc lập ở mức độ nhất định. Xét ví dụ:

```java
try {
    service.process(command);
} catch (IllegalStateException ex) {
    logger.error("event=command.failed command_id={}", commandId, ex);
    throw ex;
}
```

Đây là **trích đoạn SLF4J**, cần biến và dependency tương ứng, không phải chương trình độc lập. Nếu global exception handler cũng log exception đó khi rethrow, cùng một lỗi có thể tạo **hai event ERROR giống nhau**. Có thể hợp lệ nếu hai event thêm ý nghĩa khác nhau và được policy cho phép, nhưng mặc định nên chọn một ranh giới có trách nhiệm ghi lỗi đầy đủ.

Ngược lại, một exception có thể được xử lý và ứng dụng phục hồi:

```java
try {
    cached = remoteCache.get(key);
} catch (CacheUnavailableException ex) {
    cached = localFallback.get(key);
    // Có thể tăng metric và ghi một WARN được giới hạn tần suất.
    // Không nhất thiết ERROR nếu yêu cầu vẫn thành công theo SLA.
}
```

Đây là pseudocode Java có kiểu giả định. Nếu gọi `ERROR` rồi lại xử lý thành công bình thường, dashboard có thể tăng cảnh báo giả. Chính sách mức log cần dựa trên **tác động nghiệp vụ** và việc lỗi đã được xử lý hay chưa, không chỉ sự tồn tại của một `catch`.

### Điều kiện đúng cần test

| Tình huống | Outcome ứng dụng | Hành vi logging kỳ vọng |
| --- | --- | --- |
| Không lỗi | SUCCESS | Không có `exception.failed`; có thể có log success theo policy |
| Exception được xử lý và fallback thành công | RECOVERED | WARN/INFO hoặc metric tùy policy, không mặc định ERROR |
| Exception không được xử lý, request fail | FAILED | Một event lỗi đầy đủ ở ranh giới thích hợp, với Throwable và correlation ID |
| Exception được wrap rồi propagate | FAILED | Log outer exception cùng cause chain, không chỉ message string |
| Lỗi transient đang retry | RETRY_PENDING | Log attempt vừa đủ, tránh stack trace ERROR lặp mỗi lượt |
| Hết retry | EXHAUSTED | Event terminal rõ ràng, đủ nguyên nhân và attempt count |
| Exception do input không hợp lệ dự kiến | REJECTED | Có thể WARN/INFO, không phải lúc nào cũng là sự cố hệ thống |
| Exception từ logging appender | LOGGING_FAILURE | Báo qua status/monitoring của pipeline; không tạo vòng đệ quy log lỗi |
| Exception chứa secret | FAILED | Không rò secret trong message, stack trace, MDC hoặc encoded output |

Không dùng một assert “đã có exception” thay cho assert “có event log đúng”. Một unit test của business logic và một test logging có thể bổ trợ nhau nhưng kiểm tra hai hợp đồng khác nhau.

## 2. Các tầng kiểm thử trong logging pipeline

Một pipeline logging khái niệm:

```text
Business code -> Logger call -> level/filter -> LogRecord/LoggingEvent
                                            |
                                            v
                                       Handler/Appender
                                            |
                      +---------------------+---------------------+
                      |                     |                     |
                  stdout/file          async queue          network exporter
                      |                     |                     |
                      +---------------------+---------------------+
                                            |
                                       agent/collector
                                            |
                                      index/query/alert
```

Các điểm khác nhau cần test riêng:

| Tầng | Test cho biết gì? | Không khẳng định được gì? |
| --- | --- | --- |
| Unit test mã nghiệp vụ | Exception nào ném, bắt, wrap, outcome nào trả ra | Logging event có xuất đúng sink không |
| Test event in-memory | Logger/Handler/Appender nhận event với level, template, Throwable, MDC nào | File/console/collector/index đã nhận hay chưa |
| Test encoder/layout | Text/JSON có field, stack trace, escape và redaction đúng | Sự kiện đã truyền thành công qua network chưa |
| Integration test sink | Console/file/appender thật nhận các bản ghi nào | Backend có thể tìm được log hay chưa |
| End-to-end log pipeline | Event xuất hiện tại collector/index trong thời hạn với schema đúng | Mọi event tương lai chắc chắn không bao giờ mất |
| Load/failure test | Async buffering, dropping, retry, blocking khi quá tải | Correctness không cần test ở tải bình thường |

**Một lựa chọn đúng:** Dùng in-memory appender để kiểm tra chính xác Throwable nhanh và không flaky; dùng integration test riêng cho file/JSON; dùng end-to-end test riêng để chứng minh forwarding/ingestion. Tránh bắt buộc mọi unit test phải đợi log collector bên ngoài.

### Positive và negative assertions

Một test tốt khẳng định hai chiều:

- **Positive:** Khi checkout thất bại, có đúng một `event=checkout.failed` với `ERROR` và nguyên nhân phù hợp.
- **Negative:** Không có `checkout.succeeded`, không có hai event lỗi trùng, không log token, không gửi exception sang sink audit sai.
- **Số lượng:** Nếu policy yêu cầu một event tại một boundary, assert chính xác count = 1, không chỉ `>=1`.
- **Đối tượng:** Với hai request song song, event của request A mang ID của A, không bị MDC của B lẫn vào.
- **Thời gian:** Trong async logging, assertion vắng mặt chỉ có giá trị khi đã flush/drain và quan sát đủ deadline.

Một string search trong output không tự phân biệt event đã bị log hai lần, xuất ở logger cha, hay được encode từ hai exception khác nhau cùng message.

## 3. Kiểm tra các thuộc tính của exception log

### 3.1. Level

Các backend SLF4J/Logback/Log4j 2 thường dùng `TRACE`, `DEBUG`, `INFO`, `WARN` và `ERROR`. Trong JUL, các mức tương ứng về ý nghĩa có `FINE`, `INFO`, `WARNING` và `SEVERE`; JUL **không có** `Level.ERROR` hay `Level.DEBUG`.

Test level theo chính sách:

- Lỗi làm request thất bại và cần can thiệp: `ERROR` hoặc `SEVERE`.
- Timeout tạm thời có retry và dự kiến hồi phục: `WARN` hoặc mức thấp hơn theo noise budget.
- Validation failure dự kiến: có thể `INFO`/`WARN` hoặc audit riêng.
- Error đã được recover: không tự động giữ `ERROR` nếu nó khiến cảnh báo hiểu lầm.
- Security decision/audit có đường sự kiện/retention riêng; level không được thay thế policy audit.

Test nên tìm **enum level** của event thay vì so chuỗi `"ERROR"` có thể xuất hiện bên trong message. Đồng thời, một event có level đúng nhưng bị effective logger level hoặc appender filter loại thì vẫn không có log ở đích; cần test cấu hình thực tế.

### 3.2. Logger name, event code, message và metadata

Test các field ổn định:

- `loggerName`/package để phân biệt nguồn.
- `event_code` hoặc marker chuẩn như `order.failed`, không phụ thuộc toàn bộ câu văn dịch/format.
- `request_id`, `operation_id`, `message_id` hoặc `trace_id` tùy ngữ cảnh.
- Resource ID được phép lưu, service, environment, error category.
- `outcome` không sai lệch so với trạng thái nghiệp vụ.

Có thể test **message template** tại logger và **formatted message** tại appender, nhưng đó là hai giai đoạn khác nhau. Một test chỉ khẳng định text template nguyên gốc, chưa kiểm tra placeholder có được render đúng trong output cuối hay không. Một test chỉ tìm output text không nhất thiết phát hiện mất structured field hoặc Throwable.

**Không test toàn bộ timestamp, thread ID hoặc location line number** bằng giá trị cố định nếu những trường này không phải contract của bài. Timestamp/stack frame phụ thuộc máy, version, cách biên dịch và điều kiện chạy. Với test cần thời gian xác định, tiêm `Clock.fixed` vào nơi tạo timestamp ứng dụng; không giả định timestamp của mọi logging backend dùng Clock đó.

### 3.3. Throwable và stack trace

Trong JUL, `LogRecord.getThrown()` cho biết `Throwable` được gắn với bản ghi. Trong Logback, `ILoggingEvent.getThrowableProxy()` và `IThrowableProxy` phản ánh exception mà backend capture. Kiểm tra:

1. Có Throwable/exception proxy, không chỉ một chuỗi `ex.getMessage()`.
2. Loại exception đúng ở **ngoài cùng**; nếu wrap thì cause chain còn nguyên.
3. Stack trace có frame phục vụ điều tra; không mất nguyên nhân gốc vì dùng sai overload logger.
4. Suppressed exceptions có được bảo toàn trong Throwable, nếu luồng dùng try-with-resources hoặc manual suppression.
5. Không có message/stack trace chứa secret khi encoder hoặc policy yêu cầu redaction.
6. Bản ghi không bị nhân đôi bởi log-and-rethrow ở nhiều tầng, additivity hoặc collector ingest trùng.

Trong nhiều framework, gọi:

```java
logger.error("Processing failed: {}", exception.getMessage());
```

chỉ tạo **text thông báo**, không gắn `Throwable` để backend in stack trace; ngược lại:

```java
logger.error("Processing failed", exception);
```

gắn exception vào logging event theo API SLF4J thông dụng. Đây là trích đoạn SLF4J, không phải Java thuần JDK. Với parameterized logging, SLF4J thường nhận Throwable ở vị trí cuối, nhưng phải xác minh overload/phiên bản của backend đang chạy. Đừng nhầm một Throwable bị truyền như đối số format thông thường với việc backend thật sự nhận một exception cause.

### 3.4. Cause và suppressed exceptions

Một lỗi hiện đại có thể có:

```text
IllegalArgumentException: order processing failed
  caused by IllegalStateException: database unavailable
    suppressed IOException: resource close failed
```

Với Throwable gốc, test:

- `outer.getCause()` là đúng loại nguyên nhân.
- `outer.getCause().getSuppressed()` chứa exception phụ nếu đã thêm.
- Exception bị wrap không thay thế toàn bộ root cause bằng message string.
- Nếu encoder có giới hạn độ sâu stack trace, test trường hợp cause chain dài theo policy, nhưng đừng cố in stack trace vô hạn hoặc payload nhạy cảm.

Suppressed exception **khác** cause: `getSuppressed()` là một mảng của chính Throwable được gắn suppressed, không mặc nhiên nằm ở outer exception. Stack trace formatter có thể trình bày chúng ở vị trí khác nhau; kiểm thử model bằng API thường bền vững hơn so với so toàn bộ văn bản trace.

## 4. Java 17 chạy độc lập: kiểm thử LogRecord và Throwable

Ví dụ này dùng **chỉ JDK 17+**, không cần Maven, JUnit, Spring Boot, Logback hay Log4j 2. Nó dùng `java.util.logging.Logger` và một `Handler` in-memory để ghi nhận bản ghi thực sự được JUL phát tới handler. Chương trình mô phỏng repository báo lỗi, service wrap exception rồi log **một lần** tại ranh giới xử lý và propagate.

Mục tiêu test:

- Đúng một record được handler nhận.
- Level `SEVERE`, logger name và message đúng.
- `LogRecord.getThrown()` là **cùng instance** với exception mà caller bắt.
- Cause là `IllegalStateException` và có một suppressed `IOException`.
- Không có output từ parent handler; stdout chỉ in kết quả assertion.
- Thay một chi tiết quan trọng (level, message hoặc cause) sẽ khiến test dừng với `IllegalStateException`.

### File `ExceptionLoggingTestDemo.java`

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ExceptionLoggingTestDemo {
    private static final class MemoryHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<>();

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

    private static void repositoryWrite() {
        IllegalStateException root =
                new IllegalStateException("database unavailable");
        root.addSuppressed(new IOException("cleanup failed"));
        throw root;
    }

    private static void processOrder(Logger logger) {
        try {
            repositoryWrite();
        } catch (IllegalStateException root) {
            IllegalArgumentException outer =
                    new IllegalArgumentException(
                            "order processing failed", root);
            logger.log(Level.SEVERE,
                    "event=order.failed order_id=order-7", outer);
            throw outer;
        }
    }

    private static void require(boolean condition, String name) {
        if (!condition) {
            throw new IllegalStateException(
                    "assertion failed: " + name);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.exception.boundary");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        MemoryHandler capture = new MemoryHandler();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        try {
            IllegalArgumentException caught = null;
            try {
                processOrder(logger);
            } catch (IllegalArgumentException failure) {
                caught = failure;
            }

            require(caught != null, "exception propagated");

            List<LogRecord> records = capture.snapshot();
            require(records.size() == 1, "one event");

            LogRecord record = records.get(0);
            require(record.getLevel().equals(Level.SEVERE), "level");
            require("demo.exception.boundary".equals(
                    record.getLoggerName()), "logger name");
            require("event=order.failed order_id=order-7"
                    .equals(record.getMessage()), "message");
            require(record.getThrown() == caught, "throwable identity");

            Throwable cause = caught.getCause();
            require(cause instanceof IllegalStateException, "cause");
            require(cause.getSuppressed().length == 1, "suppressed");
            require(cause.getSuppressed()[0] instanceof IOException,
                    "suppressed type");

            System.out.println("record_count=" + records.size());
            System.out.println("level=" + record.getLevel().getName());
            System.out.println("logger=" + record.getLoggerName());
            System.out.println("message=" + record.getMessage());
            System.out.println("exception="
                    + record.getThrown().getClass().getSimpleName());
            System.out.println("cause="
                    + cause.getClass().getSimpleName());
            System.out.println("suppressed_on_cause="
                    + cause.getSuppressed().length);
            System.out.println("parent_handlers="
                    + logger.getUseParentHandlers());
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
javac ExceptionLoggingTestDemo.java
java ExceptionLoggingTestDemo
```

**stdout chính xác:**

```text
record_count=1
level=SEVERE
logger=demo.exception.boundary
message=event=order.failed order_id=order-7
exception=IllegalArgumentException
cause=IllegalStateException
suppressed_on_cause=1
parent_handlers=false
test=PASS
```

**Vì sao output xác định?**

1. Chương trình tự tạo và gọi code trong **một thread**, dùng `Handler` lưu record vào `ArrayList`; không có async queue và timestamp in ra.
2. `Logger#setUseParentHandlers(false)` ngăn record tiếp tục được chuyển tới JUL root/parent handlers, nên không có thông báo SEVERE mặc định chen vào stdout/stderr.
3. Logger level `INFO` cho phép `SEVERE`; handler level `ALL` không chặn record. Mỗi lần gọi `processOrder` chỉ phát một event.
4. `logger.log(Level.SEVERE, message, outer)` dùng overload nhận `Throwable`, do đó `LogRecord.getThrown()` chính là `outer`. Caller `catch` nhận lại cùng instance vì code rethrow nó.
5. `root.addSuppressed(...)` gắn IOException vào nguyên nhân gốc; khi wrap bằng `IllegalArgumentException(message, root)`, chuỗi cause/suppressed vẫn còn.
6. `snapshot` được gọi sau khi lời gọi logger đồng bộ đã trở lại và trong cùng một thread. Nó không chứng minh thread safety nếu dùng nhiều thread; appender/handler test concurrent cần collection đồng bộ hoặc kiểm tra sau khi worker hoàn tất.
7. `test=PASS` chỉ xuất hiện sau khi **tất cả assertions đều qua**. Nếu code thay đổi đến mức không log hoặc mất Throwable, chương trình ném lỗi trước dòng PASS.

### Thử các lỗi để hiểu test bắt được gì

- Đổi `Level.SEVERE` trong `processOrder` thành `Level.FINE`: logger effective level `INFO` sẽ loại event; assertion `one event` thất bại.
- Đổi `logger.log(Level.SEVERE, "...", outer)` thành `logger.severe(outer.getMessage())`: record không gắn Throwable; assertion identity thất bại, và message khác.
- Bỏ `outer` khi rethrow và ném một exception mới không có cause: assertion cause hoặc identity thất bại.
- Gọi logger hai lần cùng event: assertion `records.size() == 1` phát hiện duplicate.
- Bật `setUseParentHandlers(true)`: test hiện tại in `parent_handlers=true` nhưng **không tự phát hiện bản sao ở parent handler**. Để kiểm tra trùng ở sink ngoài, cần integration test cho parent/console; một in-memory handler chỉ thấy bản ghi tới chính nó.

**Giới hạn ví dụ:** Đây là **kiểm thử nội dung JUL LogRecord**; nó không test text stack trace do Formatter render, file permissions, JSON serialization, collector ingestion hoặc mức độ bền vững. Các tầng đó cần test tiếp bên dưới. Nó cũng không chứng minh chính sách bảo mật vì chuỗi exception trong chương trình chỉ chứa dữ liệu giả.

## 5. Logback + SLF4J + JUnit 5: bắt event bằng ListAppender

Khi ứng dụng dùng SLF4J với Logback Classic, nên kiểm tra `ILoggingEvent` thay vì bắt `System.out`. Một cách thông dụng là gắn `ch.qos.logback.core.read.ListAppender` vào một logger dành riêng cho test.

Ví dụ dưới đây **không phải Java thuần JDK**. Nó cần project có JUnit Jupiter, `slf4j-api` và `logback-classic`/`logback-core` tương thích trên test classpath. Mã minh họa một test class trong dự án Maven/Gradle đã cấu hình dependency; không phải chương trình chạy bằng `javac` độc lập.

### Ví dụ JUnit 5 / Logback Classic

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.*;

class ExceptionLogbackTest {
    @Test
    void capturesThrowableAndFormattedMessage() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                "example.test.exception.capture");

        Level oldLevel = logger.getLevel();
        boolean oldAdditivity = logger.isAdditive();

        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.setContext(logger.getLoggerContext());
        capture.start();

        logger.setLevel(Level.ERROR);
        logger.setAdditive(false);
        logger.addAppender(capture);

        try {
            IllegalStateException failure =
                    new IllegalStateException("db unavailable");

            logger.error("event=order.failed order_id={}",
                    "order-7", failure);

            assertEquals(1, capture.list.size());
            ILoggingEvent event = capture.list.get(0);

            assertEquals(Level.ERROR, event.getLevel());
            assertEquals("example.test.exception.capture",
                    event.getLoggerName());
            assertEquals("event=order.failed order_id=order-7",
                    event.getFormattedMessage());

            assertNotNull(event.getThrowableProxy());
            assertEquals(IllegalStateException.class.getName(),
                    event.getThrowableProxy().getClassName());
        } finally {
            logger.detachAppender(capture);
            capture.stop();
            logger.setLevel(oldLevel);
            logger.setAdditive(oldAdditivity);
        }
    }
}
```

Phân tích:

- Dùng logger name riêng để test không bám vào một logger nghiệp vụ toàn cục đang dùng bởi các test khác.
- `setAdditive(false)` giúp event của logger test không lan lên appenders cha trong lúc test; sau đó khôi phục giá trị cũ.
- `setLevel(ERROR)` bảo đảm event minh họa được tạo; test khác có thể kiểm tra negative case khi level chặn.
- `getFormattedMessage()` kiểm tra placeholder đã được render thành ID mong đợi.
- `getThrowableProxy()` cho thấy Logback đã nhận Throwable, khác việc chỉ có text exception message.
- `finally` detach/stop appender và khôi phục level/additivity để test không gây side effect lên các test kế tiếp.

**Điểm cần lưu ý:** `ILoggingEvent.getThrowableProxy()` là representation của Logback, không phải `java.lang.Throwable` gốc. Khi cần kiểm tra cause chain, có thể kiểm tra `IThrowableProxy.getCause()` và các thông tin class/message phù hợp; nếu cần identity chính xác của Throwable trong unit test, giữ reference tại call site hoặc dùng một capture layer thích hợp. Không giả định mọi backend giữ cùng một object identity hoặc cùng cách format stack trace.

Nếu suite chạy song song và cùng cấu hình logger, việc thay level/additivity có thể gây race. Dùng logger name duy nhất, cấu hình test riêng, test isolation của framework hoặc serialize đúng phạm vi; tránh thay root logger tùy tiện trong mọi test. Với Spring Boot, `@SpringBootTest` có thể khởi chạy logging config từ profile; cần kiểm tra test nào thực sự dùng `logback-test.xml`, `logback-spring.xml` hoặc override khác.

## 6. Kiểm thử cause chain, suppressed và formatting của stack trace

Ở tầng model, kiểm tra cause/suppressed bằng API; ở tầng layout, kiểm tra output theo **đặc tính ổn định**. Một exception stack trace thường chứa:

- Dòng exception ngoài cùng, tên class và message.
- Một hoặc nhiều stack frames cho đường gọi.
- `Caused by:` và nguyên nhân sâu hơn nếu formatter xuất đầy đủ.
- `Suppressed:` nếu suppressed exceptions tồn tại và formatter hỗ trợ.
- Thông tin từ MDC/structured fields khi layout có cấu hình phù hợp.

Ví dụ output console **minh họa**:

```text
ERROR event=order.failed order_id=order-7
java.lang.IllegalArgumentException: order processing failed
    at demo.OrderService.process(OrderService.java:42)
Caused by: java.lang.IllegalStateException: database unavailable
    at demo.OrderRepository.write(OrderRepository.java:17)
    Suppressed: java.io.IOException: cleanup failed
```

**Không dùng số dòng 42/17 hay hình thức indent ở trên làm golden string cho mọi JDK/backend.** Các formatter có thể rút gọn common frames, đổi màu, đổi kiểu timestamp hoặc giới hạn độ sâu cause. Không phải `Throwable` nào cũng có stack trace thông thường, ví dụ có code vô hiệu hóa stack trace hoặc bị giới hạn bởi backend.

### Mức assert khuyến nghị

- **Unit:** Throwable không null, class/cause/suppressed đúng, được gắn vào event.
- **Layout integration:** output có dấu hiệu stack trace/`Caused by`/`Suppressed` khi policy yêu cầu; format JSON chứa field exception đúng schema.
- **End-to-end:** collector/index lưu và hiển thị được exception type, message đã mask, stack trace hoặc các trường lỗi được phép.
- **Security:** không xuất password/token/PII trong **bất kỳ** phần nào của formatted log, kể cả message exception lồng nhau.

Nếu hệ thống cố ý cắt stack trace để giới hạn kích thước, test phải khẳng định chính sách cắt đúng và vẫn giữ mã lỗi/trace ID/causes cần điều tra. Đừng yêu cầu phải lưu toàn bộ trace của mọi exception nếu điều đó vượt chính sách dữ liệu hoặc ngân sách log volume.

## 7. Bắt stdout/stderr có ích khi nào?

Một số hệ thống legacy viết `ex.printStackTrace()` trực tiếp ra `System.err`; một số chương trình nhỏ dùng `ConsoleHandler` của JUL hoặc `ConsoleAppender`. Khi cần xác minh output cuối cùng có thể capture stdout/stderr, nhưng test này dễ nhầm và flaky:

- `java.util.logging.ConsoleHandler` mặc định thường ghi **stderr**, không nhất thiết stdout.
- `System.setOut(...)`/`System.setErr(...)` là **global state** của JVM; test parallel có thể can thiệp nhau.
- Một appender có thể giữ reference tới stream cũ khi được khởi tạo, vì vậy đổi `System.out` lúc test bắt đầu không nhất thiết capture nó.
- Async logging có thể ghi sau khi test đã restore stream.
- Text output còn phụ thuộc layout, timezone, locale, timestamp và định dạng stack trace.
- Framework có thể log qua socket/file thay vì console, khiến console test không chứng minh gì về sink thật.

**Ưu tiên** in-memory event capture cho unit test, và kiểm thử stdout/stderr ở process test tách biệt (ví dụ chạy CLI trong subprocess) khi **đường console là contract cần xác minh**. Nếu bắt global streams trong cùng JVM, phải restore trong `finally` và bảo đảm suite không chạy chồng lên các test khác ảnh hưởng streams.

Đừng dùng `printStackTrace()` như hệ thống logging nghiệp vụ. Nó thiếu structured context, routing, level/filter và chính sách riêng về sensitive data. Khi exception đã được log qua một structured logger, `printStackTrace()` bổ sung thường gây trùng và khó quản trị.

## 8. Test “log đúng một lần” và ranh giới xử lý lỗi

Một lỗi có thể xuất hiện ở ba tầng:

```text
Repository -> Service -> HTTP Controller / Global Exception Handler
    |            |                    |
  throw         wrap                 respond
                 |
              log?                log?
```

Nếu Repository log ERROR rồi throw, Service log ERROR rồi throw, Global Handler log ERROR lần nữa, một exception có thể tạo ba sự kiện giống nhau. Điều này gây noise và tăng chi phí collector, đồng thời làm người vận hành tưởng có ba lỗi độc lập.

Thiết kế thường hữu ích:

1. Tầng thấp **throw exception có cause** và error code phù hợp, không nhất thiết log nếu không tự xử lý.
2. Ranh giới nhận trách nhiệm xử lý request/job ghi một event lỗi với operation ID, event code và Throwable một lần.
3. Nếu tầng dưới thực hiện retry/recovery, log các mốc chuyển trạng thái cần thiết và tổng số lần retry, không in stack trace ERROR ở mỗi bước.
4. Hệ thống tracing/metrics có thể thu các tín hiệu riêng; exception logging không thay thế tất cả.

**Không có quy tắc tuyệt đối “mỗi exception toàn hệ phân tán chỉ log một lần”.** Service A và service B có thể cần log riêng ở ranh giới service với context khác nhau. Test cần biết hợp đồng: một exception cho một request/operation có bao nhiêu **logical events** được kỳ vọng, ở đâu.

### Cách test duplicate

- Phát một request có `test_request_id`/`operation_id` duy nhất.
- Capture danh sách event ở logger/appender được kiểm thử.
- Lọc theo `event_code` và ID; assert số event thuộc loại được kỳ vọng.
- Tìm ở các sink khác và kiểm tra additivity/fan-out có chủ đích.
- Với collector, kiểm tra duplicate do agent đọc cả stdout và file.
- Nếu retry, phân biệt **attempt event** hợp lệ với **terminal failure event**; không đếm mọi WARN attempt là terminal ERROR.

**Đừng dùng riêng message text làm khóa dedup:** hai request thật có thể cùng text, còn một request có thể tạo nhiều event code. Kết hợp event ID/request ID/operation ID và chính sách routing.

## 9. Kiểm thử “không log” là một yêu cầu thực sự

Một bộ kiểm thử exception tốt không chỉ kiểm tra event được phát. Nó còn phải chứng minh **không có event trong những trường hợp cần giữ im lặng**:

- Đường success không có ERROR.
- Exception được recover không bị log thành terminal failure.
- Exception bị handler chuyển thành một response nghiệp vụ dự kiến không tạo stack trace ERROR vô ích.
- Exception của thư viện bị catch rồi handled chỉ còn metric/INFO theo policy.
- Không ghi lộ dữ liệu nhạy cảm trong error path.
- Không xuất event audit nhạy cảm sang logger stdout chung khi routing yêu cầu tách biệt.
- Không có ERROR lặp nhiều lần do additivity hoặc nhiều exception handlers.

Ví dụ ma trận:

| Case | Expected ERROR | Expected WARN | Những điều cấm |
| --- | ---: | ---: | --- |
| Handler success | 0 | 0 | Không có stack trace |
| Retry transient attempt | 0 theo policy | 1 | Không báo terminal failure sớm |
| Retry exhausted | 1 | Có thể có attempt summary | Không có hai terminal ERROR |
| Validation rejection expected | 0 hoặc policy cụ thể | 0/1 | Không log raw request body |
| Auth rejected | Audit/security theo policy | Tùy policy | Không tiết lộ token |
| Unexpected failure | 1 | Không bắt buộc | Không mất Throwable |
| Failed sink | Báo qua status/metrics riêng | Tùy pipeline | Không recursive logger failure |

Các con số là **ví dụ chính sách của một hệ thống**. Nếu chính sách dự án khác, cần viết explicit expected events trước rồi test đúng contract. Negative assertion phải quan sát đủ phạm vi; “không thấy ở ListAppender A” không có nghĩa event không lọt sang appender B.

## 10. Các lỗi riêng khi dùng JUnit/Mockito để test logging

Một số nhóm chỉ mock `Logger` và verify:

```java
verify(logger).error("operation failed", exception);
```

Đây là **trích đoạn Mockito/SLF4J giả định**, cần mock logger và các biến được khai báo. Nó có thể hữu ích để kiểm tra **business code gọi API logger**, nhưng không xác nhận backend đã tạo LoggingEvent, đã format message, đã giữ cause hay đã gửi tới sink. Nếu mock một logger mà production khởi tạo qua `LoggerFactory` static/final, việc thay mock cũng có thể cần thiết kế inject logger/test seam khác với code thực.

Nên phân tầng:

- Mock verify cho logic “có gọi logging API này hay không” khi việc đó là yêu cầu của unit.
- In-memory Appender/Handler để kiểm tra **actual emitted event**.
- Integration test cho encoder/filter/routing thật.
- End-to-end test cho agent/collector/index.

**Đừng overfit test vào phương thức log cụ thể** nếu contract chỉ là event code và level. Những refactor như dùng SLF4J fluent API, chuyển logger wrapper hoặc đổi template có thể khiến Mockito verify fail dù người vận hành vẫn thấy cùng event hợp lệ. Tập trung vào hành vi có giá trị nghiệp vụ.

### Tránh state leak giữa unit tests

- Khi gắn appender trong test, detach và stop nó trong `finally`.
- Khi thay level, additivity hoặc filter, restore giá trị cũ.
- Không thay root logger trên toàn bộ test suite nếu không có isolation.
- Dùng logger name riêng cho từng suite hoặc setup fixture chuyên biệt.
- Với test song song, dùng appender thread-safe hoặc setup test per process/context.
- Không dựa vào thứ tự các test nếu chúng share static logger/global configuration.

Nếu có nhiều test gắn `ListAppender` lên cùng logger mà không detach, một event của test B có thể nằm trong buffer của test A, gây false positives hoặc log volume bất thường.

## 11. Kiểm thử MDC, trace ID và exception ở luồng bất đồng bộ

Exception không phải lúc nào cũng xảy ra trên thread ban đầu. Với `ExecutorService`, `CompletableFuture`, message listener hoặc scheduler, có thể có thread boundary:

```text
HTTP request thread
  MDC: request_id=req-17
       |
       v
Submit async task
       |
       v
Worker thread
  MDC: absent / propagated / stale
       |
       v
Exception thrown -> log ERROR
```

Các lỗi cần phát hiện:

- Event ERROR thiếu `trace_id`/`request_id` vì context không được propagate.
- Worker thread còn MDC của message/request trước, dẫn đến gắn nhầm tenant hoặc actor.
- Exception được wrap trong `CompletionException`/`ExecutionException` nhưng log chỉ chứa wrapper message, mất cause.
- Async failure bị swallow khi `Future` không được observe, không có log hoặc metric.
- Log được phát nhưng appender async chưa drain khi test kết thúc.

### Test context propagation

Với Logback/SLF4J, `MDC.getCopyOfContextMap()` có thể trả map hoặc null; test nên dùng cơ chế propagation phù hợp với framework và loại executor. Không tự giả định MDC lan sang thread pool. Khi cần scope:

```java
// Trích đoạn SLF4J, giả sử MDC đã được tích hợp.
String previous = org.slf4j.MDC.get("request_id");
try {
    org.slf4j.MDC.put("request_id", "req-17");
    // Gọi code trong phạm vi request.
} finally {
    if (previous == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", previous);
    }
}
```

Đây không phải một chương trình độc lập. Nếu có nhiều MDC keys, dùng scope/restore toàn bộ map thích hợp; nếu cần chạy async, carry context có kiểm soát và cleanup trong worker. **Đừng đưa token, password hoặc raw payload vào MDC**, vì mọi log trong scope có thể thừa hưởng chúng.

### Assertion với asynchronous appender

Với async logging, event có thể được tạo trên caller nhưng appender thực thi sau. Test cần:

1. Một `test_event_id` riêng để xác định event.
2. Deadline hữu hạn hoặc cơ chế flush/drain được backend hỗ trợ.
3. Kiểm tra trạng thái của queue/worker và số event rơi rớt nếu overload.
4. Phân biệt event **chưa đến** với event **bị filter/drop**.
5. Assert vắng mặt ở sink sai **sau** khi pipeline đủ thời gian xử lý.

**Không dùng `Thread.sleep(100)` rồi giả định sẽ luôn có log**. Trên CI chậm hoặc khi load tăng, thời gian xử lý có thể khác. Dùng polling có timeout và cơ chế chờ cụ thể; nếu backend không expose flush, thiết kế một test sink có signal về việc đã nhận event.

## 12. Kiểm thử redaction và log injection ở exception path

Đây là phần dễ bỏ sót nhất: thông tin nhạy cảm có thể nằm trong **exception message**, **cause chain**, **suppressed exception**, **stack trace fields**, **MDC**, hoặc **request object** đã được truyền vào logger.

### Canary secret và kiểm thử âm

Dùng một chuỗi giả như `TEST_SECRET_DO_NOT_EMIT` trong input mô phỏng:

```text
Input:
  authorization_header = "Bearer TEST_SECRET_DO_NOT_EMIT"
  account_id = "acct-test-7"

Expected log:
  event=remote.call.failed
  account_id=acct-test-7
  error_code=HTTP_TIMEOUT

Forbidden anywhere in emitted/logged output:
  TEST_SECRET_DO_NOT_EMIT
  Authorization: Bearer
```

Đây là **đầu vào/kỳ vọng thử nghiệm**, không phải dữ liệu thật. Test có thể quét toàn bộ formatted output của **mọi appender đích**, không chỉ `getFormattedMessage()`. Nếu encoder tự in `ThrowableProxy`, chuỗi canary có thể nằm trong cause text dù message template đã mask.

**Các biện pháp đúng** theo thứ tự ưu tiên:

1. **Không đưa secret vào exception message hay logger argument từ đầu.**
2. Dùng mã lỗi, loại exception, ID đã được phép lưu và metadata tối thiểu.
3. Nếu cần mask/redact, thực hiện nhất quán ở các đường output; test cả message, exception và structured fields.
4. Kiểm tra encoder có escape ký tự xuống dòng và dấu điều khiển nếu nhận input không tin cậy.
5. Tách đường audit/security và quyền đọc log theo policy, retention phù hợp.

### Log injection

Một chuỗi từ user có thể chứa dấu xuống dòng:

```text
username = "bob\nERROR admin-access-granted"
```

Nếu logger ghi trực tiếp chuỗi đó vào text line không escape, kẻ tấn công có thể khiến output trông như nhiều bản ghi hoặc chèn nhãn mức độ lỗi giả. Structured JSON encoder đúng chuẩn thường escape các ký tự này theo JSON, nhưng vẫn phải test implementation thực tế. Đừng tự nghĩ “dùng JSON” bảo đảm an toàn nếu code nối tay JSON mà không escape.

Test injection bằng input giả, tìm đúng **một event JSON parse được** và nội dung nằm trong một field thay vì tạo dòng log thứ hai. Với log text, kiểm tra bộ escaping/sanitization đã được tổ chức phê duyệt. Đừng sửa nguyên nhân bằng cách tùy tiện bỏ toàn bộ context hữu ích mà không thay bằng mã lỗi an toàn.

## 13. Kiểm thử exception khi JSON/structured logging

Nhiều hệ thống production dùng JSON logs; một output minh họa:

```json
{
  "timestamp": "2026-11-10T02:00:00.000Z",
  "level": "ERROR",
  "logger": "com.example.checkout.OrderService",
  "service": "checkout",
  "event_code": "order.failed",
  "request_id": "req-test-17",
  "order_id": "order-7",
  "exception_type": "java.lang.IllegalStateException",
  "error_code": "DB_UNAVAILABLE",
  "exception_message": "database unavailable"
}
```

Đây là **JSON minh họa**, không phải schema mặc định của Logback/Log4j 2/OpenTelemetry. Khi test output structured, ưu tiên parse JSON thành object rồi assert theo key/value thay vì so toàn bộ chuỗi: thứ tự fields, khoảng trắng hoặc format timestamp có thể thay đổi hợp lệ.

### Checklist JSON

- Có các trường `timestamp`, `level`, `logger`, `event_code` và request/operation ID phù hợp.
- Exception được thể hiện đúng qua `exception.type`/`exception.stacktrace`/`exception.message` **theo schema đã chọn**, không tự đoán tên field.
- Trường chứa secret bị loại/mask; không copy toàn bộ object/request không kiểm soát.
- Phần stack trace có thể chứa newline đã escape trong JSON; output vẫn parse được.
- Logger/collector không chẻ một event thành nhiều record ngoài ý muốn.
- Không lẫn event của nhiều threads do encoder hoặc context capture sai.
- Cause chain/suppressed được giữ hoặc tóm tắt theo policy; không vô tình mất thông tin khi đổi encoder.
- Parser ở collector/index giữ nguyên event code, error code, trace ID và status cần truy vấn.

Cẩn thận khi dùng `getMessage()` của `Throwable` làm một trường trực tiếp; nếu exception message chứa URL/query/token, serializer sẽ chép nguyên văn trừ khi có redaction từ trước. Test bảo mật phải xét case này.

## 14. Khi lỗi ghi log xảy ra, ứng dụng nên phản ứng ra sao?

Một appender/handler cũng có thể lỗi:

- File không ghi được, disk full, thiếu permission.
- Console/stdout bị nghẽn hoặc ghi bị block.
- Network collector timeout hoặc từ chối kết nối.
- Async queue đầy, event bị drop hoặc producer bị chặn.
- Encoder bị exception khi serialize object hoặc xử lý dữ liệu không mong đợi.
- Lỗi trong custom filter/formatter gây reentrant logging hoặc recursion.

**Không giả định một logger sẽ luôn ném exception cho caller khi sink lỗi.** Một số framework xử lý lỗi nội bộ bằng `ErrorHandler`/status logger, cảnh báo hoặc drop tùy cấu hình. Đó là lý do cần test **sự kiện tới sink và metrics lỗi**, không chỉ assert hàm business không throw.

Một failure-injection test có thể:

1. Gắn sink giả lập thất bại tại một điểm được phép kiểm thử.
2. Gây exception nghiệp vụ và gọi logger.
3. Quan sát contract: caller có block/throw không, lỗi được báo qua status/metric nào.
4. Đảm bảo không có vòng đệ quy “logging failure → log error via same failing sink → logging failure”.
5. Xác minh audit/critical log có đường lưu và policy riêng nếu bắt buộc.
6. Khôi phục sink, kiểm tra cơ chế retry/buffer/drain và đối chiếu số event.

Mục tiêu không phải “nuốt mọi lỗi logging” cho mọi ứng dụng. Với audit bắt buộc có chính sách fail-closed, không lưu được audit có thể khiến nghiệp vụ phải từ chối giao dịch. Đây là quyết định kiến trúc dựa trên yêu cầu, không thể suy ra từ một logger API.

## 15. Test exception ở các ranh giới thực tế

### 15.1. HTTP/controller/global exception handler

Với Spring MVC hoặc framework tương tự, exception có thể bị xử lý ở:

- Service layer.
- Controller.
- Filter/interceptor.
- `@ControllerAdvice`/global exception handler.
- Web container và reverse proxy.

Chọn ranh giới ghi log rõ ràng. Một test end-to-end nên xác minh:

1. Response status đúng theo loại lỗi.
2. Có một event lỗi thích hợp với request ID.
3. Không lộ exception message, stack trace hoặc dữ liệu nội bộ vào HTTP response khi không được phép.
4. Không xuất bản ghi ERROR trùng từ service và global handler nếu chính sách chỉ cho một event.
5. Validation/business errors dự kiến không đổ stack trace hàng loạt.
6. Request context được clear sau khi xử lý.

Test controller mà chỉ assert HTTP 500 không đảm bảo log có stack trace; ngược lại event ERROR tồn tại không chứng minh response mapping đúng.

### 15.2. Message listener/consumer

Với Kafka/RabbitMQ/JMS:

- Một processing attempt thất bại có thể làm message retry, NACK/requeue, chuyển DLQ hoặc retry topic.
- Log nên giữ `message_id`/`operation_id`, `attempt`, error code và trạng thái đã biết.
- Không log `message.processed` success nếu handler đã throw.
- Không log `dlq_confirmed` khi mới yêu cầu DLQ nhưng chưa có xác nhận.
- Nếu cùng message retry nhiều lần, test phân biệt log attempt và terminal failure.
- Khi handler thành công nhưng ACK/offset commit thất bại, message có thể redeliver; cần idempotency, không kết luận có hai side effects chỉ từ hai log.

Các khẳng định này liên quan tới exception logging, nhưng **broker acknowledgements cần integration test**. In-memory logger test không chứng minh Kafka commit offset hoặc RabbitMQ ACK thực sự xảy ra.

### 15.3. Scheduled tasks/background worker

Một exception không được bắt trong scheduler hoặc async task có thể:

- Bị framework ghi riêng rồi bỏ qua/tạm dừng job.
- Được lưu trong `Future`, chỉ hiện khi gọi `get()`.
- Bị wrap trong `ExecutionException` hoặc `CompletionException`.
- Kích hoạt `UncaughtExceptionHandler` nếu thực sự là uncaught exception trên thread.

Test phải xác định **ai là chủ sở hữu xử lý lỗi cuối cùng**, tránh vừa log trong task vừa log lại khi future được await. Với `Future.get()`, cần unwrap cause đúng và log context của job; `Future.get()` cũng có thể ném `InterruptedException`, đòi chính sách giữ interrupt flag khi thích hợp.

### 15.4. Startup/shutdown

Exception xảy ra lúc hệ thống chưa cấu hình logging hoặc đang shutdown có thể không tới appender bình thường. Integration tests cần xét initialization order, fallback status/error output, flush/drain khi dừng, mức log lúc startup và khả năng còn dữ liệu ở queue khi process bị kill. Không test “exception được log” bằng cách kiểm tra ngay sau `System.exit` mà không có cơ chế quan sát của process/sink.

## 16. Ma trận kiểm thử exception logging

| ID | Kịch bản | Kiểm tra tích cực | Kiểm tra phủ định |
| --- | --- | --- | --- |
| E1 | Xử lý thành công | Có log success/metric theo chính sách | Không có ERROR hoặc exception |
| E2 | Unexpected exception | Một event ERROR, đúng exception class/cause | Không mất Throwable, không log trùng |
| E3 | Exception wrap | Cause chain và error code được giữ | Không chỉ có outer message |
| E4 | try-with-resources close failure | Suppressed được nhận diện theo chính sách | Không nhầm suppressed với root cause |
| E5 | Fallback recover | Outcome RECOVERED, WARN/metric theo policy | Không có terminal failure giả |
| E6 | Validation exception | 4xx/REJECTED theo app contract, mức log phù hợp | Không in raw input/stack trace không cần |
| E7 | Retry rồi thành công | Các attempt hợp lệ, một final success | Không có terminal ERROR khi đã recover |
| E8 | Retry exhausted | Một terminal event và attempt count | Không phát lại nhiều terminal events |
| E9 | Rethrow qua nhiều tầng | Log đúng tại boundary, correlation tồn tại | Không 2–3 stack traces giống nhau ngoài policy |
| E10 | Logger effective level tắt | Event không được tạo theo rule | Không vô tình phát INFO/DEBUG |
| E11 | Appender filter từ chối | Event không tới sink bị loại | Không nhầm “logger called” với delivered |
| E12 | Async appender delay | Event được nhận trước deadline | Không test flaky bằng sleep cố định |
| E13 | Async queue full | Policy block/drop đúng, có telemetry | Không báo 100% delivered khi có drop |
| E14 | Root/additivity | Đúng số event ở từng appender | Không có bản sao ngoài dự kiến |
| E15 | Exception chứa canary token giả | Log metadata an toàn, redaction qua mọi sink | Không có canary trong message/stack/MDC |
| E16 | Newline injection trong input | JSON/text đã escape/sanitize đúng | Không tạo dòng log giả |
| E17 | Thread pool tái sử dụng | Request/message ID đúng cho từng thread | Không dính MDC của request trước |
| E18 | Exception của logging sink | Status/metric lỗi, recovery theo policy | Không recursive log storm |
| E19 | Collector/index lỗi | Phân biệt sink emitted và ingested | Không kết luận thiếu log là nghiệp vụ không lỗi |
| E20 | Version/backend migration | Level, event code, Throwable, schema tương thích | Không mất nguyên nhân hoặc thay đổi routing âm thầm |

Ma trận là điểm bắt đầu. Tổ chức có thể thêm yêu cầu lưu audit, security log hoặc stack trace sanitization. Các event và levels phải được chuẩn hóa theo hợp đồng logging thực tế, không giả định mọi framework có cùng cấu hình.

## 17. Test asynchronous logging đúng cách

Giả sử ứng dụng dùng Logback AsyncAppender, Log4j 2 AsyncLogger hoặc exporter bất đồng bộ. Khi `logger.error(...)` trả về:

- Event có thể mới được đưa vào hàng đợi trong bộ nhớ.
- Worker formatter/sink chưa hoàn thành ghi.
- Collector có thể chưa ingest.
- Index có thể chưa searchable.

Test không nên assert ngay trong cùng milliseconds rằng backend đã nhận event. Cách thực hiện có kỷ luật:

1. Phát event có `test_event_id` duy nhất.
2. Xác định **bản ghi cần xuất hiện ở hop nào** theo test, ví dụ appender in-memory, file, collector hoặc index.
3. Nếu có API flush/drain hợp lệ của backend, dùng nó theo đúng semantics; không tự hiểu `flush()` là đã durable ở tất cả các hop.
4. Poll có deadline hữu hạn, khoảng nghỉ hợp lý và hủy/cleanup khi test kết thúc.
5. Kiểm tra cả positive event và các forbidden events ở sink sai.
6. Nếu không thấy event, xem metric filter, queue drops, appender errors, collector ingest lag và indexing.
7. Báo rõ kết quả: **not emitted**, **emitted but not delivered**, **delivered but not searchable**, hoặc **observed**.

**Không dùng `Thread.sleep(500)` như bảo đảm correctness** trong CI. Nó có thể vừa làm test chậm vừa flaky khi máy quá tải.

### Khi tải cao

Một event exception thường có stack trace dài hơn event info. Burst lỗi có thể khiến logging pipeline chuyển từ trạng thái bình thường sang queue full, làm app thread block hoặc drop event tùy policy. Vì vậy performance test nên đo:

- Exception events/s, bytes/s và kích thước trung bình/p95 log payload.
- CPU/allocations cho exception capture và stack formatting.
- Appender queue depth, blocked enqueue duration, dropped events.
- Sink write latency, collector/index visibility latency.
- Request/consumer p95/p99 và total terminal failures.
- Mức độ giữ log ERROR/critical theo chính sách, không suy ra từ việc có ít log hơn.

Không làm mất audit/security exception logs chỉ để tăng throughput nếu không có quyết định policy phù hợp.

## 18. Regression test cho thay đổi logging framework hoặc encoder

Khi nâng cấp Logback, Log4j 2, SLF4J, JDK hoặc chuyển layout text sang JSON, những khác biệt sau có thể xuất hiện:

- Message format và cách nhận Throwable từ varargs thay đổi nếu dùng sai overload.
- Stack trace converter có thể rút gọn, giới hạn chiều sâu hoặc bỏ `Caused by`.
- JSON field names có thể đổi từ `exception` sang `exception.type`/`error.type`.
- MDC key bị rename, mất trong async context hoặc bị overwrite.
- Root/additivity/appender refs làm tăng số log hoặc khiến log tới sai sink.
- Level/filter thay đổi khiến event lỗi không đến console/file.
- Test dùng exact string/line number bị vỡ dù contract thực tế vẫn đúng.

Để regression ít flaky, tách:

1. **Contract assertions:** event code, level, exception type/cause, safe metadata, count và routing.
2. **Formatter assertions:** JSON parse/schema, stack trace presence, redaction, newline escaping.
3. **Environment assertions:** appender activated, config profile, destination và ingestion path.
4. **Nonfunctional checks:** performance, queue behavior, retention/audit requirements.

Với output snapshot/golden file, chỉ snapshot những phần ổn định hoặc normalize timestamp/thread ID và vị trí stack frame theo quy tắc rõ. Không normalize mất chính field cần test, ví dụ exception type hoặc trace ID, khiến regression không phát hiện lỗi.

## 19. Runbook khi một exception “không thấy trong log”

1. **Xác minh lỗi thật đã xảy ra:** status/metric/trace, exception handler, business outcome. Đừng coi không có dòng ERROR là không có lỗi.
2. **Xem nơi bắt exception:** handler có nuốt/recover không, framework có global exception handler khác không, có wrap `CompletionException`/`ExecutionException` không?
3. **Kiểm tra lời gọi logger:** đúng overload gắn `Throwable` chưa, message template/structured fields có bị rỗng?
4. **Kiểm tra effective log level và filters:** event có được tạo, có `DENY` ở logger/turbo filter/appender không?
5. **Kiểm tra logger hierarchy/additivity:** event đi sang parent/appender khác hoặc ghi trùng?
6. **Kiểm tra async queue/sink:** log có bị drop, chưa drain, file không ghi được, stdout/agent nghẽn?
7. **Kiểm tra collector/index:** parser lỗi, mất JSON field, sai namespace, clock skew hoặc ingest delay?
8. **Kiểm tra redaction/security:** message có bị mask hoặc bị policy loại vì chứa sensitive data, và policy đó có đúng không?
9. **Khôi phục bằng case test:** phát exception có ID/test metadata duy nhất trong môi trường cho phép, tìm theo từng hop.
10. **Phòng tái diễn:** thêm regression test theo đúng tầng lỗi và dashboard metrics, tránh thêm log bừa bãi gây noise.

Nếu lỗi chỉ xuất hiện sau deploy, kiểm tra profile logging, versions/dependencies và config đang được load, không chỉ file cấu hình trong repository. Một ứng dụng có nhiều SLF4J providers hoặc binding sai có thể phát cảnh báo startup và đi qua backend khác với dự kiến.

## 20. Checklist trước khi chốt QA exception logging

- [ ] Có test cho path success, failure, handled/recovered, expected rejection và retry exhausted?
- [ ] Mức log và logger name được assert từ event thực, không chỉ tìm từ khóa trong chuỗi?
- [ ] Mọi event lỗi cần thiết có đúng event code, request ID/correlation ID và outcome?
- [ ] Throwable được gắn vào event đúng overload API, không chỉ có `exception.getMessage()`?
- [ ] Cause chain và suppressed exceptions được giữ đúng ở tầng model và layout theo policy?
- [ ] Có test số lượng event và negative assertion để bắt log trùng?
- [ ] Có test parent/additivity/routing khi nhiều appenders/sinks?
- [ ] Có test redaction cho canary secret trong message, Throwable, cause, suppressed và MDC?
- [ ] Structured JSON parse được; newline/control characters không tạo log injection?
- [ ] Async logging có deadline/flush phù hợp; không dựa vào sleep cố định?
- [ ] Test cleanup appender, level, filter, MDC và global streams trong `finally`?
- [ ] Test không phụ thuộc timestamp thật, line number stack trace và thứ tự test suite?
- [ ] Có integration/end-to-end test nếu cần chứng minh log đến file/collector/index?
- [ ] Có cơ chế giám sát khi chính appender, collector hoặc queue bị lỗi?
- [ ] Với audit/security event, quyền lưu/truy cập và retention được kiểm tra riêng?
- [ ] Kết quả kiểm thử phân biệt rõ **logger call**, **event emitted**, **sink received**, **backend searchable**?

**Tiêu chí hoàn thành:** Bạn có thể viết test phát một exception có cause, dùng Handler/ListAppender khẳng định chính xác một event lỗi với `Throwable` đầy đủ, kiểm tra được trường hợp không log, bảo vệ dữ liệu nhạy cảm và xác minh thêm các sink bất đồng bộ khi cần.

## 21. Câu hỏi tự kiểm tra

1. Tại sao `assertThrows(...)` không chứng minh exception đã được log?
2. Sự khác nhau giữa `logger.error("failed: {}", ex.getMessage())` và `logger.error("failed", ex)` là gì?
3. Trong JUL, làm sao lấy `Throwable` từ một `LogRecord`?
4. Vì sao nên assert exception/cause bằng API trước khi so toàn bộ stack trace đã format?
5. Suppressed exception nằm ở `getSuppressed()` của đối tượng nào?
6. Một service recover thành công sau cache timeout: có bắt buộc phải log ERROR không?
7. Vì sao một in-memory ListAppender không chứng minh file/collector đã nhận event?
8. Khi root logger và logger con đều có appender, additivity có thể ảnh hưởng số lượng log như thế nào?
9. Làm sao xác minh một exception có chứa token giả không rò vào stack trace của JSON encoder?
10. Test logging bất đồng bộ nên thay `Thread.sleep(100)` bằng cách quan sát nào?
11. Trong `CompletableFuture`, khi exception bị bọc bởi `CompletionException`, cách khôi phục cause trong test là gì?
12. Vì sao log exception ở mọi tầng của một đường request có thể tạo cảnh báo sai?
13. Test chỉ nhìn số lượng ERROR logs có thể bỏ sót trường hợp rò request ID giữa threads như thế nào?
14. Nếu event ERROR đã xuất tới console nhưng không tìm thấy trong index, cần kiểm tra những hop nào?
15. Tại sao không nên cho logger đang bị lỗi ghi một exception mới vào chính appender lỗi đó?

## Tài liệu tham khảo

- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html) — cause, stack trace và suppressed exceptions.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html) — `getThrown()`, level và logger name.
- [Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — `log(Level, String, Throwable)` và effective level.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — `publish` và filter/handler behavior.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — hierarchy, additivity và selection rule.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — appender filters và TurboFilter.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — appender/sink và async behavior.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — parameterized logging, Throwable handling và API.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — viết và tổ chức test.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — dữ liệu nhạy cảm, log injection và bảo vệ log.
