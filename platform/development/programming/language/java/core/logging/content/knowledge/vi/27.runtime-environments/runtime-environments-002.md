# Cấu hình test cho Java Core Logging

## 1. Mục tiêu và phạm vi

**Cấu hình test của logging** là bộ quy tắc xác định logger, mức log, appender/handler, định dạng, đích xuất và cách thu thập sự kiện log khi chạy unit test hoặc integration test. Nó thuộc **môi trường chạy**: cùng một lời gọi ghi log trong Java có thể tạo đầu ra khác nhau giữa phát triển, kiểm thử và production vì **classpath, backend và cấu hình khởi động** khác nhau.

Mục tiêu của cấu hình test tốt:
- Có log đủ để chẩn đoán lỗi trong test nhưng không làm console CI ngập thông tin.
- Kiểm tra được **sự kiện và thuộc tính log** một cách ổn định; không phụ thuộc timestamp, ID thread hay thứ tự bất định.
- Không ghi test log vào đường dẫn production hoặc gửi đến log collector thật.
- Tách trạng thái giữa các test, kể cả khi chạy đồng thời.
- Kiểm soát các tình huống log bất đồng bộ, exception, MDC và việc đóng/flushing appender.

Bài này xét **Java 17+** và ba nhóm thường gặp: **Java Util Logging (JUL)** của JDK, **SLF4J + Logback**, và **Log4j 2**. Không cần dùng cả ba trong một ứng dụng; hãy xác định backend thực tế trước khi cấu hình.

## 2. Những thành phần cần phân biệt trước khi cấu hình

Trong Java, lời gọi `logger.info(...)` chưa đủ để xác định đích xuất. Chuỗi điển hình là:

```text
Code nghiệp vụ / test
      |
      v
Logging API (JUL hoặc SLF4J hoặc Log4j API)
      |
      v
Backend logging thực sự (JUL / Logback / Log4j Core / provider khác)
      |
      v
Logger level + filter
      |
      v
Appender / Handler + Encoder / Layout
      |
      v
Console, file tạm, bộ nhớ test, collector...
```

Các điểm cần nhớ:

| Thành phần | Ví dụ | Vai trò khi test |
| --- | --- | --- |
| API | `java.util.logging.Logger`, `org.slf4j.Logger` | Điểm gọi log trong ứng dụng |
| Backend/provider | JUL, Logback Classic, Log4j Core | Đọc cấu hình và thực hiện logging |
| Level/filter | `WARN`, `INFO`, `DEBUG` hoặc JUL `WARNING`/`INFO`/`FINE` | Quyết định event được tạo/ghi |
| Appender/handler | Console, File, ListAppender, JUL Handler | Nhận và xử lý log |
| Layout/formatter | Pattern, JSON, JUL Formatter | Biến event thành text/structured output |
| Context | `requestId`, MDC, `traceId` | Liên kết log với test case/request |

**SLF4J là facade/API**, không tự quyết định cấu hình Logback hay Log4j. Chỉ tạo `logback-test.xml` mới có tác dụng nếu Logback thực sự là backend đang chạy. Tương tự, `log4j2-test.xml` nhắm đến Log4j Core, còn JUL có cơ chế cấu hình riêng.

Trên classpath test nên có **một logging provider/binding chủ đích** cho API được dùng; nếu có nhiều backend, bridge/provider mâu thuẫn hoặc bị chọn khác dự kiến, test có thể đọc cấu hình sai hoặc báo cảnh báo lúc khởi động. Nếu ứng dụng dùng bridge (ví dụ JUL sang SLF4J), phải kiểm tra rõ log đang đi qua đường nào.

## 3. Tách môi trường test khỏi production bằng classpath

### 3.1. Bố trí tài nguyên thông dụng

Với cấu trúc Maven/Gradle thông thường:

```text
src/
  main/
    java/
      ...
    resources/
      logback.xml          # hoặc log4j2.xml cho production
  test/
    java/
      ...
    resources/
      logback-test.xml     # nếu dùng Logback
      # hoặc log4j2-test.xml nếu dùng Log4j 2
```

Hai file `logback-test.xml` và `log4j2-test.xml` ở trên là **hai phương án thay thế theo backend**; đừng thêm cả hai nếu dự án chỉ dùng một backend.

Khi chạy test, `src/test/resources` thường được thêm vào test runtime classpath; khi đóng gói ứng dụng production bằng cấu hình build thông thường, tài nguyên test không đi vào artifact chính. Nếu build tự tùy chỉnh resources, shading, packaging hoặc classpath, hãy kiểm tra lại thay vì giả định.

### 3.2. Quy tắc chọn cấu hình

- **Logback Classic:** khi auto-configure theo cơ chế mặc định, Logback ưu tiên `logback-test.xml` hơn `logback.xml`. File test thường đặt ở `src/test/resources` để cấu hình test được tìm thấy mà không vào gói production.
- **Log4j 2 Core:** cơ chế tìm cấu hình trên classpath ưu tiên các biến thể tên `log4j2-test...` trước `log4j2...`. File `log4j2-test.xml` là lựa chọn thường dùng cho test. Tên có context và định dạng khác cũng được hỗ trợ; tránh đặt nhiều file cùng vai trò để việc chọn trở nên khó dự đoán.
- **JUL:** không tự đọc hai file XML trên. JUL dùng `java.util.logging.config.file` hoặc các API `LogManager`/`Logger`/`Handler`; đường dẫn cấu hình nên được quyết định **trước khi LogManager khởi tạo**.
- **Override:** system property, custom configurator, framework hoặc test runner có thể thay đổi quy tắc trên. Nên có kiểm tra “test đã nạp đúng cấu hình chưa?” ở lần thiết lập đầu tiên.

Không sửa `src/main/resources` để giảm level cho test. Không vô tình đóng gói endpoint, API key hoặc cấu hình collector production trong test resources.

### 3.3. Có cần cấu hình theo profile?

Trong ứng dụng sử dụng framework (ví dụ Spring Boot), có thể có `application-test.yml` hoặc profile test để chỉnh `logging.level`, biến môi trường hay các bean chuyên biệt. Đây là **lớp cấu hình của framework**; nó có thể bổ sung hoặc ghi đè một phần nhưng không thay thế quy tắc lựa chọn backend, file XML hoặc test runtime classpath. Java SE thuần không tự hiểu “profile test”.

## 4. Ví dụ file cấu hình test với Logback

Nếu ứng dụng dùng **SLF4J + Logback Classic**, tạo `src/test/resources/logback-test.xml`:

```xml
<configuration>
    <appender name="TEST_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <pattern>%level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Bật chi tiết hơn cho package cần điều tra. -->
    <logger name="com.example.orders" level="DEBUG"/>

    <!-- Phần còn lại của test suite chỉ in WARN trở lên. -->
    <root level="WARN">
        <appender-ref ref="TEST_CONSOLE"/>
    </root>
</configuration>
```

Ý nghĩa:
- Root `WARN` giảm nhiễu log của thư viện và các test khác.
- Logger `com.example.orders` cho phép DEBUG trong package này. Vì logger kế thừa appender theo cơ chế additivity mặc định, các event phù hợp vẫn đi đến `TEST_CONSOLE` của root.
- Pattern cố ý ngắn cho CI. Nếu cần ghép log khi test lỗi đồng thời, bổ sung `%thread`, test/request ID hoặc MDC `%X{requestId}`; đừng assert toàn bộ dòng log có thời gian/thread biến động.
- Không tạo `FileAppender` trỏ vào đường dẫn dùng chung production chỉ để xem log test.

Đây là cấu hình **Logback**, chỉ hoạt động khi Logback Classic và dependency liên quan được đưa vào test runtime. Trong build nhiều module, mỗi module cần xác định tài nguyên test của module nào có hiệu lực; đừng phụ thuộc vào thứ tự classpath ngẫu nhiên khi trùng tên file.

**Thử cơ bản:** chạy test dùng logger `com.example.orders`, phát một DEBUG và một WARN. Đối chiếu level, logger name và số lần in; nếu không thấy DEBUG, kiểm tra package, backend thực tế, level của appender/filter và việc file test được nạp.

## 5. Ví dụ file cấu hình test với Log4j 2

Nếu ứng dụng dùng **Log4j 2 Core**, đặt `src/test/resources/log4j2-test.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="TEST_CONSOLE" target="SYSTEM_ERR">
            <PatternLayout pattern="%p %c - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="com.example.orders" level="debug"/>
        <Root level="warn">
            <AppenderRef ref="TEST_CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Ở đây, root logger chỉ xuất WARN trở lên theo mức được đặt; logger `com.example.orders` cho phép DEBUG và, khi không tắt additivity, event vẫn tới appender được root tham chiếu. Nếu một logger có appender riêng **và** additivity vẫn bật, một event có thể đi qua nhiều appender; hãy kiểm tra trước khi kết luận “log trùng do test chạy hai lần”.

Log4j Core có thể được chỉ định file cấu hình tường minh bằng system property `log4j2.configurationFile`. Nếu file test không được chọn, kiểm tra property, context và test classpath. Cấu hình XML này không áp dụng cho Log4j 1 hoặc cho JUL.

Với **async logger/appender**, test cần đợi sự kiện thật sự đến appender đích hoặc áp dụng barrier/flush phù hợp. Chỉ gọi `logger.info(...)` xong không đảm bảo đã nhận được log ở worker.

## 6. Ví dụ test configuration cho Java Util Logging (JUL)

JUL có sẵn trong JDK, không cần SLF4J. Có thể cấu hình bằng properties trước khi khởi tạo `LogManager`.

Ví dụ `src/test/resources/logging-test.properties`:

```properties
handlers = java.util.logging.ConsoleHandler
.level = WARNING
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
com.example.orders.level = FINE
```

Giải thích:
- `.level = WARNING` là mức mặc định của root logger.
- `com.example.orders.level = FINE` cho phép log chi tiết hơn tại logger/package đó.
- `ConsoleHandler.level = FINE` để handler không loại mất sự kiện FINE của logger con. Trong JUL, cần xét **cả level của logger lẫn handler**, không chỉ một phía.
- `SimpleFormatter` tạo text dễ đọc, nhưng định dạng và timestamp không nên được dùng làm điều kiện assert cứng.

Khi chạy ứng dụng Java từ thư mục gốc dự án, có thể dùng đường dẫn này (thay `AppMain` bằng class có thật trong dự án):

```bash
java -Djava.util.logging.config.file=src/test/resources/logging-test.properties AppMain
```

Lệnh trên minh họa **cách truyền property**; ứng dụng thật còn cần classpath/module path đã biên dịch. Trong IDE/CI, working directory có thể khác; dùng đường dẫn tuyệt đối hoặc cấu hình build/test launcher tương ứng. Đặt property sau khi JUL đã khởi tạo có thể không có tác dụng đối với lần khởi tạo ban đầu.

Có thể dùng `LogManager.readConfiguration(InputStream)` để tải lại cấu hình trong test, nhưng thao tác đó tác động đến hệ thống JUL toàn JVM và có thể đặt lại handlers/levels của logger khác. Với suite chạy song song, ưu tiên cấu hình **trước khi fork test JVM** hoặc kiểm soát riêng logger/handler trong một phạm vi nhỏ; tránh gọi `LogManager.reset()` trong `@BeforeEach`.

## 7. Ví dụ Java 17+ chạy độc lập: cấu hình logger cục bộ và kiểm tra sự kiện

Ví dụ này chỉ dùng JDK, không cần JUnit. Nó tạo một `Handler` thu thập `LogRecord` trong bộ nhớ, bật INFO trở lên cho logger test, tắt truyền lên parent để không in trùng, kiểm tra kết quả rồi khôi phục trạng thái.

Tạo tệp **`JulLoggingTestDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulLoggingTestDemo {
    static final class CapturingHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<>();

        @Override
        public synchronized void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
            }
        }

        @Override
        public void flush() {
            // Không có buffer cần flush trong handler này.
        }

        @Override
        public void close() {
            // Không giữ file hoặc tài nguyên ngoài.
        }

        synchronized List<LogRecord> snapshot() {
            return List.copyOf(records);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.test.orders");
        Level previousLevel = logger.getLevel();
        boolean previousParent = logger.getUseParentHandlers();

        CapturingHandler capture = new CapturingHandler();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        try {
            logger.fine("diagnostic");
            logger.info("order_created id=42");
            logger.warning("retry_scheduled id=42");

            List<LogRecord> events = capture.snapshot();
            if (events.size() != 2
                    || events.get(0).getLevel() != Level.INFO
                    || !"order_created id=42".equals(
                            events.get(0).getMessage())
                    || events.get(1).getLevel() != Level.WARNING) {
                throw new AssertionError("Unexpected logs: " + events);
            }

            System.out.println("captured=" + events.size());
            for (LogRecord event : events) {
                System.out.println(
                        event.getLevel() + " " + event.getMessage());
            }
        } finally {
            logger.removeHandler(capture);
            logger.setLevel(previousLevel);
            logger.setUseParentHandlers(previousParent);
            capture.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac JulLoggingTestDemo.java
java JulLoggingTestDemo
```

**Standard output (stdout) xác định của ví dụ:**

```text
captured=2
INFO order_created id=42
WARNING retry_scheduled id=42
```

Tại sao kết quả là hai event?
1. `FINE` có mức thấp hơn `INFO` nên bị logger lọc.
2. `INFO` và `WARNING` được chuyển cho handler với mức `ALL`.
3. Handler thu thập `LogRecord`, không cần parse text đã format hay so sánh timestamp.
4. `setUseParentHandlers(false)` tránh root ConsoleHandler in thêm log ra stderr.
5. `finally` tháo handler và khôi phục level/additivity tương đương JUL (`useParentHandlers`) cho logger. Ví dụ chạy trong một JVM đơn; khi nhiều test cùng sửa **chính logger này** đồng thời, vẫn cần điều phối để tránh tranh chấp.

Trong test thực tế, thường đặt logic kiểm tra trong JUnit/AssertJ thay cho `throw new AssertionError(...)`. Điều cần học là **assert trên event**, tránh assert nguyên dòng console có timestamp, vị trí mã hoặc thread name.

## 8. Bắt log bằng JUnit và Logback: đoạn tích hợp thực tế

Khi dùng JUnit 5 + SLF4J + Logback Classic, có thể dùng `ListAppender<ILoggingEvent>` của Logback để kiểm tra event ngay trong bộ nhớ. Đây là **ví dụ test class phụ thuộc thư viện**, không biên dịch với JDK thuần; cần JUnit Jupiter, SLF4J API và Logback Classic trên test classpath.

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderLogTest {
    @Test
    void capturesWarning() {
        // Chọn tên logger dành riêng cho test này.
        Logger logger = (Logger) LoggerFactory.getLogger(
                "test.case.order");

        Level previousLevel = logger.getLevel();
        boolean previousAdditivity = logger.isAdditive();
        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.start();

        logger.setAdditive(false);
        logger.setLevel(Level.WARN);
        logger.addAppender(capture);

        try {
            logger.warn("retry_scheduled id={}", 42);

            assertEquals(1, capture.list.size());
            ILoggingEvent event = capture.list.get(0);
            assertEquals(Level.WARN, event.getLevel());
            assertEquals("retry_scheduled id=42",
                    event.getFormattedMessage());
        } finally {
            logger.detachAppender(capture);
            logger.setLevel(previousLevel);
            logger.setAdditive(previousAdditivity);
            capture.stop();
        }
    }
}
```

Tại sao test này ổn định hơn so sánh console?
- Event chưa bị biến thành chuỗi có timestamp/thread không cố định; có thể kiểm tra level và thông điệp riêng.
- Dùng logger riêng, detach và stop appender ở `finally` để giảm ảnh hưởng đến test khác.
- Không sửa root logger toàn cục trong test. Nếu suite có test khác cùng tên logger hoặc cùng context chạy song song, cần cô lập thêm bằng logger name/context hoặc thực thi tuần tự phù hợp.

Đoạn này kiểm tra **lời gọi log** và cách bắt event; muốn kiểm tra hành vi nghiệp vụ thực, thay lời gọi `logger.warn(...)` bằng hành động trên đối tượng ứng dụng phát sinh log rồi assert event mong đợi.

**Chú ý với async:** `ListAppender` gắn trực tiếp vào logger có thể nhận event đồng bộ tùy cách cấu hình; nếu logger/appender hoạt động bất đồng bộ, việc đọc `capture.list` ngay lập tức có thể race với worker. Dùng cơ chế chờ có timeout/barrier cụ thể trước khi assert và đảm bảo appender đã drain, thay vì `Thread.sleep(100)` tùy ý.

## 9. Cấu hình test cho async logging, MDC và chạy song song

### 9.1. Logging bất đồng bộ

Một lời gọi logging trả về có thể chỉ chứng minh event được **enqueue**. Với `AsyncAppender` hoặc async logger, test cần chờ theo điều kiện có thể kiểm tra:

```text
trigger business action
  -> đợi worker kết thúc / đợi event xuất hiện với deadline
  -> assert level/message/context
  -> drain hoặc stop appender thử nghiệm theo API backend
  -> dọn tài nguyên
```

Nên dùng callback, latch, tín hiệu hoàn tất hoặc thư viện polling có timeout rõ ràng. Tránh sleep cố định gây flaky test trên CI chậm. Nếu appender có chính sách drop khi queue đầy, test integration riêng phải kiểm tra đúng policy; không coi mọi thiếu event là lỗi race đơn thuần.

Phân biệt hai kiểu test:
- **Unit test hành vi log:** bắt event bằng handler/appender trong bộ nhớ; nên tách khỏi file/network và async không cần thiết.
- **Integration test pipeline async:** bật backend thật, queue và đích mô phỏng; test drain, drop/backpressure, lỗi I/O, retry, shutdown theo contract. Đây là bài kiểm tra riêng, có timeout và cleanup.

### 9.2. MDC / request context

Nếu dùng SLF4J MDC hoặc Log4j ThreadContext:
- Đặt `requestId` cố định trong test, ví dụ `test-req-001`, để có thể so sánh.
- Khôi phục context cũ hoặc gọi `MDC.remove("requestId")`/`MDC.clear()` trong `finally` theo phạm vi sở hữu; tránh làm mất context không thuộc test.
- Khi tạo thread mới hoặc giao task cho executor, cần truyền context theo cơ chế framework/adapter; đừng suy luận context tự xuất hiện chỉ vì test chính đã `put`.
- Trong log async, nhiều backend capture MDC tại lúc tạo event; kiểm tra backend/phiên bản cụ thể nếu test yêu cầu giá trị ở thời điểm enqueue.

Không đưa token, mật khẩu, cookie hoặc dữ liệu cá nhân thật vào MDC/log test; dùng dữ liệu giả và kiểm tra redaction trong test chuyên biệt.

### 9.3. Parallel test và global state

Các thao tác sau thường ảnh hưởng cả process/test suite, không phải riêng một test:
- `System.setProperty(...)` cho logging configuration hay provider.
- `LogManager.reset()`, tải lại cấu hình JUL, thay root logger.
- Đổi level/root appender hoặc shutdown toàn bộ logger context.
- `System.setOut` / `System.setErr` để chụp text console.

Với parallel test, hạn chế chúng ở bootstrap hoặc test fork độc lập; nếu buộc phải thay đổi, có khóa/điều phối hợp lý và hoàn nguyên trong `finally`. **Không dùng assert trên stdout/stderr toàn JVM** nếu các test khác đang in đồng thời, vì đầu ra xen kẽ và không có ranh giới test rõ.

Khi cần file log, chọn đường dẫn tạm **riêng theo test**, ví dụ thư mục tạo bởi JUnit `@TempDir`, đóng appender trước khi xóa file; không dùng file chung giữa nhiều test. Không kiểm tra thời gian/cấu trúc chính xác của tên file rolling appender nếu không gắn clock/test fixture kiểm soát được.

## 10. Thiết kế ba mức kiểm thử phù hợp

| Mức | Điều nên kiểm tra | Đích log / cấu hình phù hợp |
| --- | --- | --- |
| **Unit** | Code phát đúng level, event, exception và trường context; không phát dữ liệu nhạy cảm | In-memory handler/ListAppender; không cần network, console ít |
| **Integration** | Backend nạp đúng file test, filter, layout JSON, async queue, appender, rolling, flush | Tệp/thư mục tạm, sink giả, collector test |
| **End-to-end/CI** | Từ request đến hệ thống thu thập có field `traceId`/`requestId` và thời gian nhận đáp ứng mục tiêu | Collector riêng cho test, dữ liệu giả và cleanup |

Không nên kiểm tra mọi thứ bằng một test tích hợp lớn. Ví dụ muốn xác nhận “khi order thất bại thì ghi WARN có orderId”, in-memory event đủ tốt; muốn xác nhận JSON layout chứa `requestId` đúng trường mới cần kiểm tra sau encoder hoặc tại sink. Nếu log là audit có yêu cầu bền vững, unit test logger không chứng minh được durability hoặc delivery cuối đường.

### Những assertion nên và không nên dùng

**Nên:**
- Level, logger name, mã sự kiện cố định, message template/field mong đợi.
- Exception/stack trace ở dạng `Throwable` của event nếu backend cung cấp.
- Tính có mặt của `requestId` và quy tắc ẩn dữ liệu nhạy cảm.
- Số event khi số lần gọi được xác định và không có async/drop; khi async, chờ điều kiện có deadline.
- Format JSON bằng cách parse JSON và so sánh các trường cần thiết.

**Tránh:**
- Assert nguyên dòng chứa timestamp tuyệt đối, thread ID hoặc vị trí dòng mã.
- Assert thứ tự giữa nhiều task chạy đồng thời trừ khi có contract bảo đảm thứ tự.
- Dựa vào số lần xuất hiện log của framework không thuộc phạm vi test.
- Thay đổi cấu hình root ở `@BeforeEach` trong suite parallel rồi quên hoàn nguyên.
- Ghi file/collector production từ bài test.

## 11. Kiểm tra sự cố thường gặp khi test log “không ra”

| Triệu chứng | Cần kiểm tra trước |
| --- | --- |
| Có file `logback-test.xml` nhưng bị bỏ qua | Backend có thật là Logback? File nằm trên **test runtime classpath**? Có override/configurator khác? |
| `log4j2-test.xml` không có tác dụng | Có `log4j-core`? API có đang bridge sang backend khác? Có `log4j2.configurationFile`/context override? |
| DEBUG/FINE không xuất hiện | Logger level, handler/appender threshold/filter, package/name và additivity |
| Một event xuất hiện hai lần | Appender gắn ở logger con và root, additivity, hoặc bridge tạo vòng/đường lặp |
| Test pass trên máy nhưng fail trên CI | Working directory, classpath, charset, config profile, async timing, parallel output |
| Log xuất hiện sau khi assert | Async queue/worker chưa drain; dùng deadline và tín hiệu hoàn tất |
| Test sau bị nhiễm level/MDC/handler | Chưa detach, stop, restore, clear/khôi phục context ở `finally` |
| Logger test in ra tệp production | FileAppender/đường dẫn environment bị dùng lại; thiếu test override hoặc temp dir |
| Có event nhưng không thấy stack trace | Logger gọi chỉ với message thay vì truyền throwable; layout/encoder chưa cấu hình exception |
| Kết quả khác nhau theo lần chạy | Sử dụng timestamp, thread name, global logger state, random ID hoặc ngủ chờ cố định |

Nếu bị nghi không nạp đúng file, có thể tạm bật **diagnostic/status của chính backend** trong test được cô lập, in đường dẫn cấu hình và tên provider đang chạy, sau đó tắt khi vấn đề đã được giải quyết. Đừng tăng DEBUG của toàn ứng dụng trước khi xác định backend thật.

## 12. Checklist áp dụng cho dự án Java

1. Xác định ứng dụng dùng JUL, SLF4J + Logback hay Log4j 2; kiểm tra classpath test và tránh provider ngoài dự kiến.
2. Đặt đúng file `logback-test.xml` hoặc `log4j2-test.xml` trong test resources; với JUL, thiết lập `java.util.logging.config.file` sớm hoặc dùng handler cục bộ.
3. Mặc định root `WARN` cho test suite và chỉ nâng level ở package cần kiểm tra. Không gửi test log tới collector production.
4. Dùng dữ liệu test cố định, ID giả; bắt event dưới dạng record/object để assert những trường ổn định.
5. Tạo logger/appender/handler riêng, tháo ra và khôi phục trạng thái trong `finally`; chú ý global state khi chạy song song.
6. Với async log, kiểm tra event ở điểm nhận thích hợp sau khi drain/await; đặt timeout rõ, đo drop và không chờ bằng sleep tùy ý.
7. Với test file/JSON/collector, dùng temp directory và sink test, parse field cần kiểm tra, đóng tài nguyên và dọn sau test.
8. Chạy test trên local và CI bằng cùng backend/version/test resources; xác nhận cả trường hợp pass lẫn failure để bảo đảm log đủ thông tin điều tra.

## 13. Câu hỏi tự luyện

**Tình huống 1:** Test đặt `logback-test.xml` trong `src/main/resources`. Vấn đề là gì?

Tệp dành cho test có thể bị đưa vào runtime/artifact production, ảnh hưởng level và đích xuất. Đặt trong `src/test/resources` và kiểm tra cấu hình packaging.

**Tình huống 2:** Test gắn `ListAppender` lên root, chạy parallel rồi assert log có đúng hai event. Vì sao flaky?

Root nhận event từ nhiều logger/test, nên kết quả có thể chứa log khác. Dùng logger riêng hoặc context cô lập; nếu cần sửa trạng thái chung thì điều phối/fork, cleanup đúng cách.

**Tình huống 3:** Một test async gọi `log.info(...)` xong kiểm tra danh sách event rỗng và fail. Sửa thế nào?

Có thể worker chưa xử lý queue. Chờ hoàn tất bằng điều kiện và deadline, kiểm tra cấu hình async/queue/drop, rồi mới assert. Không mặc định mọi log enqueue đều đến sink thành công.

**Tình huống 4:** `com.example.orders` được đặt `FINE` trong JUL nhưng console không thấy FINE. Kiểm tra gì?

Kiểm tra level của `ConsoleHandler`, level/filter của logger, parent propagation và file JUL đã được nạp trước `LogManager` khởi tạo; logger level thấp hơn không tự nâng threshold của handler.

## 14. Ghi nhớ

- **Cấu hình test là cấu hình của runtime test**, phụ thuộc backend và classpath, không phải một công tắc chung cho mọi logging API.
- Tách test resources, log sink và mức log khỏi production. Root yên tĩnh; chỉ bật chi tiết có mục đích.
- Test sự kiện logging bằng level/message/context/throwable, tránh so sánh text có timestamp/thread biến động.
- Khôi phục mọi handler/appender/level/MDC đã thay đổi; tránh thao tác global trong parallel test.
- Async logging cần xác minh **event đến nơi nhận**, không chỉ lời gọi logger hoàn thành.

### Tài liệu tham khảo

- Logback, *Configuration*: https://logback.qos.ch/manual/configuration.html
- Logback, *Appenders* và AsyncAppender: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2, *Configuration*: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Apache Log4j 2, *Getting Started* (test configuration): https://logging.apache.org/log4j/2.x/manual/getting-started.html
- Oracle, `java.util.logging.LogManager`: https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/LogManager.html
- Oracle, `java.util.logging.Handler`: https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Handler.html
