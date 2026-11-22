# Kiểm thử message trong Java Logging: nội dung, tham số và đầu ra

## 1. “Kiểm thử message” kiểm tra điều gì?

Trong Java Logging, **kiểm thử message** là xác minh ứng dụng phát ra **đúng sự kiện log, đúng mức độ, đúng mẫu thông điệp, đúng tham số/ngữ cảnh và đúng thông tin exception**, đồng thời không phát những nội dung không được phép. Tùy mục đích, bài test có thể kiểm tra đối tượng log event trong bộ nhớ hoặc chuỗi/JSON sau khi formatter, encoder và appender thực sự chạy.

Một lời gọi như:

~~~java
// SLF4J hoặc Log4j 2; log là logger đã khởi tạo.
log.info("order={} state={}", orderId, state);
~~~

có ít nhất ba điều có thể kiểm tra:

1. **Message template:** `"order={} state={}"`.
2. **Arguments:** ví dụ `["ORD-42", "PAID"]`.
3. **Formatted message:** `"order=ORD-42 state=PAID"`.

Nếu chỉ assert rằng `logger.info(...)` được gọi, test có thể không phát hiện formatter sai, logger bị tắt, appender không gắn đúng hoặc text cuối cùng bị biến đổi. Nếu chỉ so nguyên một dòng console có timestamp và thread ID, test thường dễ vỡ khi đổi layout hay timezone.

**Mục tiêu học tập:** xác định tầng nào cần kiểm thử và viết assertion đúng tầng, không mặc định mọi test đều phải đọc console hoặc file thực.

## 2. Phân biệt ba tầng của một log message

~~~text
Business method
    │  log.info(template, arguments, throwable?)
    ▼
Logger facade/API + level + filter
    │
    ▼
Logging event: template + args + level + Throwable + context
    │
    ▼
Formatter / Layout / JSON encoder
    │
    ▼
Appender / Handler / async queue
    │
    ▼
Console, file, memory, socket, collector
~~~

Mỗi tầng trả lời câu hỏi khác nhau:

| Tầng kiểm thử | Câu hỏi trọng tâm | Ví dụ assertion |
| --- | --- | --- |
| **Call site** | Code có quyết định ghi đúng sự kiện? | Method nghiệp vụ tạo event khi trạng thái FAILED |
| **Event object** | Level, template, arguments, cause, MDC có đúng? | `getMessage()` bằng template; `getThrown()` là exception |
| **Formatted output** | Người đọc hay collector nhận nội dung gì? | Text chứa `order=ORD-42 state=PAID`; JSON có `orderId` |
| **Routing/filter** | Event có đến đúng sink, đúng level không? | INFO có, FINE/DEBUG bị chặn |
| **Async delivery** | Event đến sink sau khi worker xử lý chưa? | Chờ tín hiệu completion trước assertion |
| **Security/privacy** | Có dữ liệu bí mật/PII hoặc log injection không? | Output và exception field không chứa sentinel giả |

**Chọn đúng ranh giới:** Với unit test chỉ quan tâm template, một handler/appender in-memory thường đủ. Với yêu cầu kiểm tra JSON schema hoặc file rotation, phải chạy formatter/appender gần production hơn. Với yêu cầu bảo đảm delivery/durability, cần test tích hợp và hợp đồng lưu trữ, không thể suy ra từ một assertion trên event.

## 3. Viết hợp đồng message trước khi viết assertion

Bắt đầu từ mục đích nghiệp vụ, không từ chuỗi log tình cờ đang xuất hiện.

Ví dụ, sau thao tác thanh toán:

| Điều kiện | Event code | Level | Message/field được phép | Không được chứa |
| --- | --- | --- | --- | --- |
| Thanh toán hoàn tất | `PAYMENT_COMPLETED` | INFO | orderId, result, elapsedMs | Card number, token, raw request |
| Thanh toán lỗi tạm thời | `PAYMENT_RETRY` | WARN hoặc DEBUG theo policy | orderId, attempt, reasonCode | Raw exception chứa secrets |
| Thanh toán bị từ chối | `PAYMENT_DENIED` | INFO/WARN theo policy | orderId, reasonCode | CVV, thông tin chủ thẻ |
| Đang tính toán chi tiết | `PAYMENT_DEBUG` | DEBUG/FINE | branch, cache status, rule version | Payload chưa lọc |
| Không có lỗi | Không được phát `PAYMENT_FAILED` | — | — | Bản ghi sai nghĩa |

Với mỗi event hãy xác định:

- **Khi nào được tạo** và điều kiện nào không được tạo.
- **Đếm số event** dự kiến: một lần, mỗi retry hay một lần cho cả workflow?
- **Mức log** và xử lý khi level bị tắt.
- **Mẫu thông điệp** và **tham số**, hoặc danh sách field trong structured log.
- **Exception** có được gắn thật dưới dạng `Throwable` không.
- **Dữ liệu không được phép**: token, password, raw body, header, PII.
- **Sink** nào cần thấy event: console, file, audit, remote collector.

Test tốt thường kết hợp assertion **có nội dung mong muốn** với assertion **không có nội dung cấm**.

## 4. Test message không phải lúc nào cũng test chuỗi hoàn chỉnh

Ví dụ một dòng console:

~~~text
2026-11-10 03:14:02.417 [worker-17] INFO  demo.OrderService - order=ORD-42 state=PAID
~~~

Thời gian, thread, tên class và khoảng trắng có thể thay đổi theo máy. Nếu test phải so nguyên dòng, bạn vô tình đưa rất nhiều chi tiết bố cục không liên quan vào hợp đồng.

Ưu tiên:

- Unit test event: so **template**, **arguments**, **formattedMessage**, **level**, **loggerName**.
- Test formatter: dùng event có timestamp/locale/zone được cố định rõ hoặc assert theo trường, không so clock thời gian thực.
- Test JSON: parse JSON rồi assert field và kiểu dữ liệu, tránh so thứ tự key.
- Test file: dùng thư mục tạm, đợi flush/close, đọc đúng charset.
- Test route: attach appender in-memory vào **logger cụ thể**, không chặn stdout toàn JVM nếu không cần.

Một chuỗi cố định thích hợp để assert khi nó là **một phần của hợp đồng**: mã sự kiện, tiền tố, template, tên field hoặc câu thông báo được dùng bởi parser downstream. Những text chỉ để dev đọc có thể được phép thay đổi mà không làm hỏng test nghiệp vụ.

## 5. Java 17 độc lập: bắt và kiểm tra LogRecord bằng Handler trong bộ nhớ

Ví dụ này **không dùng JUnit** và không cần thư viện bên ngoài. Chương trình tự thực thi các assertion bằng Java 17, thoát mã khác 0 nếu có lỗi. Nó kiểm tra cả sự kiện xuất hiện, sự kiện không xuất hiện và thông tin bảo mật.

Tạo tệp **MessageLoggingTest.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class MessageLoggingTest {
    private static final Logger LOG = Logger.getLogger("demo.message");

    record Captured(Level level, String template, Object[] arguments,
                    String rendered, Throwable thrown) {}

    static final class CapturingHandler extends Handler {
        private final List<Captured> events = new ArrayList<>();
        private final Formatter renderer = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record);
            }
        };

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            Object[] params = record.getParameters();
            events.add(new Captured(record.getLevel(), record.getMessage(),
                    params == null ? new Object[0] : params.clone(),
                    renderer.format(record), record.getThrown()));
        }

        @Override public void flush() {}
        @Override public void close() {}
        List<Captured> snapshot() { return List.copyOf(events); }
    }

    private static void check(boolean passed, String description) {
        if (!passed) throw new AssertionError(description);
    }

    public static void main(String[] args) {
        CapturingHandler capture = new CapturingHandler();
        capture.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(capture);

        try {
            LOG.log(Level.INFO, "order={0} state={1}",
                    new Object[]{"ORD-42", "PAID"});
            IllegalStateException cause = new IllegalStateException("failure");
            LOG.log(Level.WARNING, "send failed", cause);

            AtomicInteger supplierCalls = new AtomicInteger();
            LOG.fine(() -> {
                supplierCalls.incrementAndGet();
                return "expensive diagnostics";
            });

            String secret = "TEST_SECRET_DO_NOT_LOG";
            LOG.log(Level.INFO, "credentialPresent={0}",
                    new Object[]{!secret.isEmpty()});

            List<Captured> result = capture.snapshot();
            check(result.size() == 3, "number of events");
            Captured first = result.get(0);
            check(first.level() == Level.INFO
                    && first.template().equals("order={0} state={1}")
                    && Arrays.equals(first.arguments(),
                            new Object[]{"ORD-42", "PAID"})
                    && first.rendered().equals("order=ORD-42 state=PAID"),
                    "template/arguments/rendered");
            check(result.get(1).level() == Level.WARNING
                    && result.get(1).template().equals("send failed")
                    && result.get(1).thrown() == cause,
                    "Throwable preserved");
            check(supplierCalls.get() == 0
                    && result.stream().noneMatch(e -> e.level() == Level.FINE),
                    "disabled fine event");
            check(result.stream().noneMatch(e ->
                    e.rendered().contains(secret)
                    || e.template().contains(secret)),
                    "secret absent");

            System.out.println("PASS: template, arguments, formatted message");
            System.out.println("PASS: throwable and level");
            System.out.println("PASS: disabled FINE and lazy supplier");
            System.out.println("PASS: secret not logged");
            System.out.println("captured=" + result.size());
        } finally {
            LOG.removeHandler(capture);
            capture.close();
        }
    }
}
~~~

Chạy trong thư mục chứa file:

~~~bash
javac --release 17 MessageLoggingTest.java
java MessageLoggingTest
~~~

**Standard output (stdout) chính xác:**

~~~text
PASS: template, arguments, formatted message
PASS: throwable and level
PASS: disabled FINE and lazy supplier
PASS: secret not logged
captured=3
~~~

**Standard error (stderr):** trống khi test thành công. **Exit code:** `0`. Nếu assertion sai, chương trình ném `AssertionError`, JVM có kết quả thất bại và in stack trace ra stderr.

### Cách hiểu test

1. `LOG.setLevel(Level.INFO)` bật INFO/WARNING nhưng tắt FINE.
2. `capture.setLevel(Level.ALL)` không chặn sự kiện do level của handler.
3. `setUseParentHandlers(false)` tránh root logger in thêm vào console, giúp test cô lập.
4. `CapturingHandler.publish` nhận `LogRecord`, kiểm tra `isLoggable` và sao chép array parameters để tránh giữ cùng tham chiếu array có thể thay đổi sau này.
5. `record.getMessage()` trả template JUL `"order={0} state={1}"`; `Formatter.formatMessage(record)` tạo chuỗi đã thay `{0}` và `{1}`.
6. `record.getThrown()` giữ cùng đối tượng `IllegalStateException` được truyền vào overload `log(Level, String, Throwable)`.
7. Supplier của `LOG.fine(() -> ...)` không chạy vì FINE tắt; `supplierCalls==0` và không có event FINE.
8. Biến `secret` không được đưa vào logger; chỉ truyền boolean `credentialPresent`. Assertion kiểm tra sentinel không xuất hiện trong template hoặc message đã định dạng.
9. `result.size()==3` bắt được lỗi ghi dư hoặc thiếu một số event trong chính phạm vi test.

**Giới hạn:** Handler dùng `ArrayList` để minh họa xử lý đồng bộ theo một luồng, **không phải collector thread-safe**. Với logging đồng thời, dùng hàng đợi thread-safe và cơ chế chờ hoàn tất. Việc clone `Object[]` là **sao chép nông**; object phần tử mutable vẫn có thể thay đổi. Trong demo các đối số là chuỗi/boolean bất biến nên không gây vấn đề.

## 6. JUL: template, parameters và formatter là ba thứ khác nhau

`java.util.logging.LogRecord` chứa:

- `getMessage()`: text **chưa format**, có thể là key của resource bundle.
- `getParameters()`: mảng đối số, hoặc null.
- `getThrown()`: Throwable gắn với event, hoặc null.
- `getLevel()` và `getLoggerName()`: thuộc tính của sự kiện.
- `getInstant()`/`getLongThreadID()`: metadata, nếu cần kiểm tra.

JUL thông thường dùng placeholder `{0}`, `{1}` theo `MessageFormat`. Khác với SLF4J/Log4j 2 thường dùng `{}`.

Ví dụ:

~~~java
LOG.log(Level.INFO, "user={0} action={1}",
        new Object[]{"usr-42", "EXPORT"});
~~~

Phần này là minh họa trong class đã định nghĩa `LOG`/`Level`. Khi `LogRecord` được tạo, `getMessage()` có thể là `"user={0} action={1}"`; sau `formatMessage`, chuỗi là `"user=usr-42 action=EXPORT"`.

Đừng viết test như:

~~~java
// Sai kỳ vọng với JUL: getMessage không tự thay placeholder.
check(record.getMessage().equals("user=usr-42 action=EXPORT"), "message");
~~~

Chọn `formatMessage(record)` khi muốn test output dạng text; chọn `getMessage()` và `getParameters()` khi muốn test hợp đồng template.

**Localization:** Khi Logger/LogRecord có resource bundle, formatter có thể thay message key thành chuỗi theo locale. Khi đó test phải kiểm soát bundle/locale và xác định mình đang test key hay text đã bản địa hóa.

**Mutable LogRecord:** Javadoc JDK khuyến nghị client không tiếp tục thay đổi LogRecord sau khi gửi vào logging framework. Nếu một handler chuyển record sang thread khác, cần snapshot/prepare metadata trước; không giữ tham chiếu tùy tiện rồi giả định trường không thay đổi.

## 7. Kiểm thử mức log và sự kiện không được phát

Một message test tốt không chỉ xác minh `INFO` có mặt. Cần xác minh:

- Khi `DEBUG/FINE` tắt, event debug không xuất hiện.
- Khi `WARN/WARNING` được bật, sự kiện cảnh báo xuất đúng level.
- Logger và handler/appender có thể có **hai ngưỡng level riêng**.
- Filter tại logger hoặc appender có thể chặn event dù level cho phép.
- Khi additivity/parent handlers bật, event có thể bị in trùng ở nhiều sink.

**Có hai kiểu negative assertion khác nhau:**

1. **Không có event:** logger bị tắt/đã filter, nên collector không nhận record.
2. **Có event nhưng field không chứa giá trị cấm:** event vẫn xuất, nhưng không lộ secret.

Không kiểm tra hai trường hợp này bằng cùng một câu `assertFalse(console.contains(...))` rồi coi là đủ; nếu appender bị cấu hình sai và không ghi **bất kỳ** event nào, privacy test sẽ PASS giả. Cần có một positive assertion chứng minh sink thật sự hoạt động.

Test với Supplier ở JUL/SLF4J Fluent/Log4j 2 Supplier còn có thể xác minh **biểu thức đắt không được chạy** khi level tắt. Việc không xuất message không tự chứng minh các argument đã được tính lazily: nếu viết `log.debug("value={}", expensive())`, Java vẫn gọi `expensive()` trước.

## 8. Kiểm thử Throwable: message text không thay thế exception

Hai lời gọi này khác nhau:

~~~java
// JUL: chỉ text mô tả exception; LogRecord.thrown vẫn null.
LOG.warning("failed: " + exception);

// JUL: exception được gắn đúng vào event.
LOG.log(Level.WARNING, "failed", exception);
~~~

Đây là minh họa, `exception` là `Throwable` có sẵn. Test chỉ so chữ `"failed"` sẽ **không** biết exception có bị mất hay không.

Với JUL test:

~~~java
check(captured.thrown() == exception, "Throwable identity");
~~~

Đoạn này đòi hỏi `captured` là snapshot của event và `exception` ở phạm vi test. So identity phù hợp khi muốn bảo đảm truyền đúng object. Có thể kiểm tra type, cause chain và message/class nếu cần; tránh assert toàn bộ stack trace khi không có hợp đồng ổn định về số dòng/source line.

Với SLF4J/Logback, kiểm tra `ILoggingEvent.getThrowableProxy()` hoặc cause field đúng API. Với Log4j 2 Core, kiểm tra `LogEvent.getThrown()` hoặc event throwable proxy theo phiên bản. **Đừng chỉ tìm tên exception trong text**: một tên class viết trong message không chứng minh backend nhận Throwable đúng cấu trúc.

**Privacy:** Exception message, suppressed exceptions, MDC và stack trace có thể mang token hoặc PII. Test event “không lộ secret” phải kiểm tra phần exception được xuất bởi encoder, không chỉ `getFormattedMessage()`.

## 9. SLF4J: mock lời gọi hay bắt event thực?

SLF4J là **facade**. Bản thân lời gọi `logger.info(...)` có thể được chuyển đến Logback, Log4j 2 hoặc provider khác.

Hai cách test:

**A. Mock logger/call site:** Hữu ích khi code thiết kế với một interface nhỏ như `EventLogger` hoặc `AuditRecorder` được inject. Bạn có thể verify method được gọi với `eventCode` và args đúng. Cách này nhanh nhưng không chứng minh provider, level, layout, sink hoặc stack trace.

**B. Bắt event từ backend thật:** Gắn test appender vào logger được chỉ định, gọi nghiệp vụ rồi assert `ILoggingEvent`/`LogEvent`. Đây là cách phù hợp khi mục tiêu là **kiểm thử message** ở cấp event và xác nhận routing.

Ví dụ một business method sử dụng SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class OrderPublisher {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderPublisher.class);

    void reportSuccess(String orderId) {
        LOG.info("order={} state={}", orderId, "PAID");
    }
}
~~~

Đây là snippet **cần `slf4j-api` và provider**. Nếu dùng static logger, mock trực tiếp có thể khó hoặc làm test phụ thuộc implementation; test appender ở backend cụ thể thường đơn giản hơn cho kiểm tra event.

Tuy nhiên test backend phải tương thích phiên bản. Không dùng `ListAppender` của Logback khi production/test runtime thực tế đang chạy Log4j 2 backend.

## 10. Logback Classic: ví dụ JUnit 5 với ListAppender

Khi ứng dụng dùng **SLF4J + Logback Classic** và JUnit Jupiter, có thể gắn `ch.qos.logback.core.read.ListAppender<ILoggingEvent>`. Nó thu các event vào danh sách trong bộ nhớ, cho phép kiểm tra cả template và message sau định dạng.

Ví dụ test class **LogbackMessageTest.java**:

~~~java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.*;

class LogbackMessageTest {
    @Test
    void capturesMessageTemplateAndArguments() {
        Logger logger =
                (Logger) LoggerFactory.getLogger("test.orders.message");
        Level previousLevel = logger.getLevel();
        boolean previousAdditivity = logger.isAdditive();

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.setContext(logger.getLoggerContext());
        appender.start();
        logger.setLevel(Level.INFO);
        logger.setAdditive(false);
        logger.addAppender(appender);
        try {
            logger.info("order={} state={}", "ORD-42", "PAID");

            assertEquals(1, appender.list.size());
            ILoggingEvent event = appender.list.get(0);
            assertEquals(Level.INFO, event.getLevel());
            assertEquals("order={} state={}", event.getMessage());
            assertArrayEquals(
                    new Object[]{"ORD-42", "PAID"},
                    event.getArgumentArray());
            assertEquals("order=ORD-42 state=PAID",
                    event.getFormattedMessage());
        } finally {
            logger.detachAppender(appender);
            appender.stop();
            logger.setLevel(previousLevel);
            logger.setAdditive(previousAdditivity);
        }
    }
}
~~~

**Điều kiện chạy:** Dự án cần JUnit 5, `slf4j-api` và `logback-classic`/`logback-core` tương thích với nhau; đây **không** phải mã dùng chỉ với JDK. Chạy theo cấu hình Maven/Gradle của dự án. `LoggerFactory.getLogger(...)` phải trả Logback `Logger`; nếu backend khác, phép cast sẽ thất bại.

**Tại sao đoạn test này hữu ích:**

- Kiểm tra event do **logger/backend thật** tạo, không chỉ verify mock được gọi.
- So `getMessage()` (template `{}`), `getArgumentArray()` (đối số) và `getFormattedMessage()` (chuỗi hoàn chỉnh).
- Chứng minh đúng `INFO` và số event.
- Gắn appender vào một logger test chuyên dụng, `additive=false` để tránh sự kiện chạy lên root.
- `finally` detach/stop appender và khôi phục level/additivity để tránh ảnh hưởng test tiếp theo.

**Giới hạn:** `ListAppender` là collector in-memory, **không** tự chứng minh output JSON, encoding, file flush hay việc một remote sink nhận event. `ListAppender.list` là danh sách thường, không nên đọc/ghi không đồng bộ từ nhiều thread mà không có cơ chế đồng bộ; với async cần chờ và bộ sưu tập thread-safe hoặc appender test phù hợp.

Khi test suite chạy song song, việc đổi cấu hình của một logger tên cố định có thể gây can thiệp. Dùng logger riêng cho từng test hoặc cô lập `LoggerContext` và quản lý lifecycle.

## 11. Logback: MDC, Throwable và điều kiện không có log

Với Logback `ILoggingEvent` có thêm:

- `getLoggerName()`: tên logger thực phát.
- `getMDCPropertyMap()`: context key-value ở event; cần kiểm tra việc propagate/snapshot.
- `getThrowableProxy()`: thông tin exception cho formatter.
- `getThreadName()`: tên thread nguồn theo event; không nên assert tên tự sinh nếu không kiểm soát.
- `getMarkerList()` hoặc API marker tương ứng theo phiên bản.

Test MDC không nên chỉ assert text layout chứa `requestId`. Nếu mục tiêu là context, kiểm tra field ở event, sau đó có thể test layout riêng:

~~~java
// Minh họa trong JUnit/Logback test có biến event đã thu được.
assertEquals("req-91",
        event.getMDCPropertyMap().get("requestId"));
~~~

Ở code ứng dụng, dùng `MDC.putCloseable(...)` hoặc `try/finally` để tránh context rò từ test này sang test khác. Đừng để một test quên `MDC.clear()/remove()` rồi khiến test sau PASS nhầm do dữ liệu cũ.

Kiểm thử exception:

~~~java
// Kiểm tra proxy không null khi log.warn("...", exception) đúng cách.
assertNotNull(event.getThrowableProxy());
~~~

Đây là fragment trong test đã có `event` kiểu `ILoggingEvent`. Nếu cần xác nhận loại exception, đọc `getClassName()` trên proxy. So toàn stack trace line-by-line thường quá dễ vỡ.

**Negative level test:** `logger.setLevel(Level.INFO)`, phát `debug(...)` và assert danh sách appender không thêm event. Nhưng phải tạo một sự kiện INFO để xác minh appender hoạt động; nếu không, empty-list test có thể PASS giả khi appender chưa start.

## 12. Log4j 2 Core: kiểm thử bằng appender test, không đoán stdout

Nếu backend là Log4j 2, dùng `org.apache.logging.log4j.core.LogEvent` và một appender in-memory hoặc test appender được gắn vào **LoggerContext/LoggerConfig** riêng cho test.

Một appender kiểm thử có thể thu snapshot bất biến ở phương thức `append`:

~~~java
// Fragment minh họa bên trong appender custom của Log4j 2 Core.
// Không phải một class Java độc lập: cần khai báo class, lifecycle,
// thread-safe collection và kết nối appender với LoggerConfig.
@Override
public void append(org.apache.logging.log4j.core.LogEvent event) {
    capturedEvents.add(event.toImmutable());
}
~~~

Ở test, kiểm tra:

- `event.getLevel()` và `event.getLoggerName()`.
- `event.getMessage().getFormat()`: text định dạng gốc/mẫu theo loại Message.
- `event.getMessage().getFormattedMessage()`: text đã format.
- `event.getThrown()`: Throwable thật.
- `event.getContextData()`: context map dạng `ReadOnlyStringMap`, kiểm tra trường cấu trúc như traceId.
- Marker, source, timestamp, thread name chỉ khi thuộc hợp đồng.

Không giả định mọi subtype `Message` có cùng cú pháp `{}`: `ParameterizedMessage` khác `StringFormattedMessage` hoặc `MapMessage`. Nếu ứng dụng dùng message factory khác, cần assertion tương ứng.

**Quan trọng với Async Logger/ReusableMessage:** Không giữ tham chiếu `LogEvent` hoặc mảng parameters mutable rồi assert muộn trên thread test. Snapshot ở ranh giới appender, ví dụ `event.toImmutable()`, hoặc thiết kế collector lưu riêng các trường bất biến. Xác minh SDK/backend version trước khi dùng API nội bộ.

Khi cần kiểm tra JSON Template Layout, **kiểm tra output thực từ layout** bằng cách parse JSON. Test ở cấp `LogEvent` không chứng minh template JSON, exception resolver, context fields hoặc key encoding đúng.

## 13. Test message text, layout và structured JSON

**Text layout:** Một event có thể đúng ở API nhưng bị in sai vì pattern. Ví dụ pattern Logback/Log4j 2 thiếu `%msg`, sai newline hoặc encoder dùng charset khác.

Nên có test tại layout/sink:

~~~text
eventCode=ORDER_PAID orderId=ORD-42 state=PAID
~~~

Trên đường production, chuỗi này có thể được bọc bởi timestamp/level. Assert phần message và semantic fields, trừ khi format toàn dòng là hợp đồng chính thức với parser downstream.

**JSON layout:** Structured logging có thể tạo:

~~~json
{
  "eventCode": "ORDER_PAID",
  "level": "INFO",
  "orderId": "ORD-42",
  "state": "PAID",
  "attempt": 1,
  "credentialPresent": false
}
~~~

Test nên parse JSON rồi xác minh:

1. `eventCode` là chuỗi đúng.
2. `attempt` là **number**, không phải chuỗi `"1"` nếu schema quy định number.
3. `credentialPresent` là boolean.
4. Không có key bí mật như `password` hoặc `authorization`.
5. Có đúng trường correlation cần thiết.
6. Dấu tiếng Việt, Unicode, newline và dấu ngoặc kép được escape/encode đúng.
7. Không có event thừa hoặc thiếu khi nhiều message được ghi.

Hai JSON có thứ tự key khác nhau vẫn có thể tương đương ngữ nghĩa. So toàn bộ chuỗi JSON theo thứ tự field dễ làm test vỡ không cần thiết.

**Schema/version:** Khi log được collector hoặc hệ thống audit đọc tự động, field names, types và `schemaVersion` trở thành hợp đồng ổn định; test nghiêm ngặt hơn text debug tự do.

## 14. Khi nào phải đọc file thật hoặc console thật?

**Đọc file** phù hợp để xác minh:

- File appender đã tạo đúng đường dẫn và charset.
- Pattern/JSON encoder thật có ghi text/field dự kiến.
- Rotation hoặc policies tạo file đúng quy tắc.
- Flush/close xả dữ liệu sau khi test yêu cầu.
- Có tách audit/app/diagnostic sink đúng cấu hình.

Dùng thư mục tạm (JUnit `@TempDir`), tránh đường dẫn log production, tên file cố định hoặc xóa dữ liệu của test khác. Sau khi ghi, **chờ xử lý và đóng/flush** appender theo API tương ứng rồi mới đọc `Files.readString(path, UTF_8)`. Nếu appender có queue async, flush stream không tự đồng nghĩa queue đã drain.

**Console/stderr:** Đổi `System.out/System.err` toàn JVM trong test có thể can thiệp test khác, đặc biệt khi chạy song song. Với JUL, `ConsoleHandler` thường ghi stderr; với Logback/Log4j 2, sink phụ thuộc cấu hình. Chỉ redirect console trong integration test đã kiểm soát isolation và restore streams trong `finally`.

**Remote collector:** Nếu nghiệp vụ yêu cầu log đến collector, test bằng mock HTTP sink/ephemeral collector hoặc test environment; cần phân biệt “request gửi đi” với “đã được index và query”. Không dựa vào một giây ngủ cố định để kết luận dữ liệu đã đến.

## 15. Logging bất đồng bộ: đồng bộ hóa test đúng cách

Với `AsyncAppender`, AsyncLogger, background writer hoặc gửi qua mạng, việc gọi `log.info(...)` xong rồi ngay lập tức assert collector có event thường tạo **flaky test**.

Sai về đồng bộ:

~~~java
// Đoạn minh họa: thời gian ngẫu nhiên, phụ thuộc máy CI.
log.info("job={}", jobId);
Thread.sleep(100);
assertEquals(1, captured.size());
~~~

Cách đúng là dùng **mốc hoàn tất có ý nghĩa**:

- `CountDownLatch` được countdown khi test appender **thật sự nhận event**.
- `CompletableFuture`/test probe để chờ event với **deadline** rõ.
- Cơ chế `stop/drain/flush` của backend khi test toàn lifecycle.
- Với collector từ xa: poll có thời hạn và ID test duy nhất, sau đó xác minh nội dung.

Ví dụ fragment ý tưởng:

~~~java
// Ở test appender khi nhận đúng eventId:
latch.countDown();

// Ở test thread, chỉ PASS khi sự kiện thực sự được nhận:
boolean arrived = latch.await(3, java.util.concurrent.TimeUnit.SECONDS);
assertTrue(arrived);
~~~

Đây là **fragment**, cần `latch` và `assertTrue` từ test framework. Không gọi `latch.countDown()` ngay ở nơi phát log; như vậy chỉ chứng minh caller đã chạy, không chứng minh appender nhận.

**Negative test async khó hơn positive test.** Không thấy event ngay có thể là chưa xử lý xong. Muốn chứng minh message bị filter, kiểm tra điều kiện filter/level độc lập hoặc đợi barrier/drain xác định rồi assert không xuất hiện. Một fixed sleep 50ms không phải hàng rào xử lý.

**Event order:** Khi nhiều thread hoặc nhiều consumer async, không tùy tiện assert toàn bộ thứ tự log. Nếu hệ thống chỉ cam kết thứ tự trong một partition hay một logger, test theo phạm vi đó; nếu không, so tập event theo event ID.

## 16. Kiểm thử message lặp lại, số lượng và tính không trùng

Chỉ `assertContains("failed")` không bắt được duplicate logging.

Ví dụ một exception đi qua nhiều tầng:

~~~text
Controller: log.error("failed")
Service:    log.error("failed")
Retry:      log.warn("failed")
~~~

Nếu contract quy định **một error event ở ranh giới request**, test nên assert:

- Số event ERROR đúng 1.
- Có event code và request ID thống nhất.
- Không in stack trace lặp nhiều lần qua cùng đường đi nếu policy cấm.
- Retry debug/metric có mã sự kiện riêng; không bị đếm thành business failure mới.

Nếu nghiệp vụ quy định một log mỗi retry, test nên assert **đúng ba lần với attempt 1, 2, 3** chứ không cố loại hết duplicate. Phân biệt **logical event ID** với **transport attempt**.

Có thể lọc captured events theo `eventCode` hoặc template và đếm, thay vì `list.size()` của toàn bộ sink khi có các event không liên quan. Trong demo thuần JDK ở phần 5, `size()==3` là hợp lý vì logger test được cô lập và chỉ phát ba sự kiện.

## 17. Log message và bảo mật: test không có secret thật

Sử dụng sentinel giả:

~~~text
TEST_SECRET_DO_NOT_LOG
TEST_PASSWORD_ONLY_FOR_TEST
TEST_CARD_NUMBER_NOT_REAL
~~~

Dùng fake data do test tự tạo, **không copy credential/PII production** vào fixture hoặc CI log. Assertion nên tìm sentinel trong mọi output có thể tiếp cận:

- Formatted message và template.
- Arguments, key-value fields, MDC/ThreadContext.
- Throwable message, cause và suppressed exceptions.
- JSON encoder/PatternLayout output cuối.
- Console/file và bản ghi collector trong integration test.

Một test chỉ kiểm tra `message.contains("TEST_SECRET") == false` có thể PASS giả nếu event không được xuất. Kết hợp assertion **event expected vẫn tồn tại** và **secret không có**.

Đừng chỉ dựa vào regex ở layout: log event có thể đi qua appender khác, JSON encoder khác hoặc bộ gom log trước khi được mask. Ưu tiên **minimization/allowlist tại nguồn**, dùng redaction ở sink làm lớp bổ sung.

Test cả **log forging**: input chứa `\nERROR forged`, CR, ký tự điều khiển hoặc chuỗi JSON escape có thể tạo thông điệp giả nếu formatter không an toàn. Assertion cần kiểm tra output đúng định dạng và không sinh thêm bản ghi giả.

## 18. Kiểm thử message parameterization và lazy evaluation

Những điều không nên nhầm:

| API | Template | Cơ chế |
| --- | --- | --- |
| JUL | `"id={0}"` | `MessageFormat`/`Formatter.formatMessage` |
| SLF4J | `"id={}"` | `{}` với backend/provider |
| Log4j 2 mặc định | `"id={}"` | Thường qua `ParameterizedMessage` |
| `String.format` chạy ở caller | `"id=%s"` | Tạo chuỗi **trước** lời gọi logger nếu gọi trực tiếp |

Khi level tắt:

~~~java
// Sai nếu mục đích là tránh hàm đắt:
log.debug("snapshot={}", expensiveSnapshot());
~~~

Dù dùng placeholder, Java vẫn đánh giá `expensiveSnapshot()` trước khi gọi method. Với SLF4J 2.x fluent builder:

~~~java
log.atDebug().addArgument(() -> expensiveSnapshot())
        .log("snapshot={}");
~~~

Đây là snippet cần SLF4J 2.x và logger tương ứng. Với JUL, có `Logger.log(Level, Supplier<String>)`. Test có thể tăng một counter trong supplier rồi assert **counter bằng 0** khi level tắt và **bằng 1** khi level bật. Demo phần 5 đã kiểm tra phía tắt.

Không test “lazy” bằng cách chỉ assert không có formatted text; hàm đắt có thể vẫn chạy dù logger cuối cùng bỏ event.

## 19. Tránh các assertion dễ vỡ theo môi trường

Các yếu tố thường làm text log khác nhau giữa laptop và CI:

- Timestamp, timezone, locale và DST.
- Thread name, thread ID, virtual thread, pool index.
- Địa chỉ IP, hostname, process ID, port tự cấp.
- Thứ tự map/JSON fields, exception source line numbers.
- Đường dẫn Windows/Linux, ký tự phân cách, newline CRLF/LF.
- Format number/date theo locale và các kiểu `toString()`.
- Logger hierarchy/level thay đổi bởi test khác.
- Asynchronous batch, sampling, rate limiting, buffer/flush.
- Phiên bản của SLF4J, Logback, Log4j 2 hoặc JSON encoder.

Biện pháp:

1. Cố định giá trị domain của fixture và locale/timezone **khi chúng là một phần hợp đồng test**.
2. Assert các field mang nghĩa, không phụ thuộc toàn bộ câu log nếu chưa được chuẩn hóa.
3. Dùng logger riêng để tránh cấu hình toàn cục ngoài phạm vi.
4. Với stack trace, kiểm tra type/cause/metadata thay vì so mọi dòng và số line.
5. Dùng timeout có hạn cho async, không `Thread.sleep` đoán thời gian.
6. Test Unicode và nhiều hệ điều hành nếu message được xử lý bởi parser/collector khác.
7. Khôi phục logger level, additivity, appender và MDC sau mỗi test.

Nếu hợp đồng yêu cầu **định dạng byte-level**, test byte-level là đúng, nhưng phải xác định charset, newline, zone và version thay vì mặc định chúng không đổi.

## 20. Unit test, component test và integration test khác nhau thế nào?

| Loại | Cấu hình | Bắt được | Không chứng minh |
| --- | --- | --- | --- |
| Unit test JUL in-memory handler | Không cần dependency ngoài JDK | Template, level, arguments, Throwable, số event | File/stdout/collector |
| Unit test mocked AuditRecorder/EventLogger | Interface fake/mock | Nhánh nghiệp vụ gọi đúng recorder | Logger backend đã nhận |
| Component test Logback ListAppender | SLF4J + Logback test runtime | Event backend, MDC, level, Throwable proxy | JSON/file output cuối |
| Component test Log4j 2 appender | Log4j 2 Core config cô lập | LogEvent và route | Remote delivery |
| Formatter/encoder test | Layout thật, input xác định | Formatted text/JSON schema, escape | Hoàn tất network/storage |
| File sink integration test | FileAppender/FileHandler + temp dir | Đường dẫn, charset, flush/close | Durability khi máy chết |
| Collector end-to-end test | Broker/agent/collector test environment | Ingest, parsing, index, correlation | Mọi crash/permission state production |

Không đặt hết mọi yêu cầu vào một test khổng lồ. Nên có nhiều test có phạm vi rõ, chia trách nhiệm giữa business logic, event contract và cấu hình môi trường.

## 21. Mở rộng ví dụ với JUnit 5 và test fixture

Khi chuyển demo `MessageLoggingTest` thành unit test JUnit:

- Đặt khởi tạo test handler trong `@BeforeEach` hoặc trong test method.
- Dùng `@AfterEach` hoặc `try/finally` để detach handler/restore level.
- Dùng `assertEquals`, `assertSame`, `assertArrayEquals` và `assertFalse` thay vì `check`.
- Dùng `@TempDir` nếu test có file output.
- Nếu xử lý async, thêm latches/futures trong fixture và giới hạn deadline.
- Không sử dụng logger tên `""`/root chung cho tất cả test khi muốn chạy song song.

**Đảm bảo cô lập:** Logger của JUL có thể được dùng lại từ `LogManager` theo tên, nên không đủ chỉ tạo biến `Logger` mới trong test mà bỏ qua trạng thái global. Khi sửa level, filter, parent handlers hoặc attached handlers, phải lưu giá trị cũ và khôi phục ở cuối test.

Một fixture tốt chỉ bắt event của ứng dụng đang kiểm thử, không làm thay đổi log của framework test runner và không in bản ghi bí mật vào console trong CI.

## 22. Bộ test cases nên có cho log message

| Test case | Kích thích | Assertion |
| --- | --- | --- |
| Message INFO thông thường | Operation thành công | Template, args, formatted text và count đúng |
| Placeholder có nhiều tham số | 2–3 arguments | Không mất/tráo vị trí giá trị |
| Dữ liệu null | Field thiếu | Formatter không crash, render theo contract |
| Ký tự Unicode | Tiếng Việt, emoji | Không lỗi charset, text/JSON đúng |
| Message có quote/newline | Untrusted input giả | Escaping an toàn, không giả mạo dòng |
| Exception trực tiếp | `IllegalStateException` | Throwable field/proxy chính xác |
| Exception có cause | Wrapper exception | Cause chain được bảo toàn khi policy yêu cầu |
| Level FINE/DEBUG tắt | Log debug | Không phát event; Supplier không chạy |
| Level FINE/DEBUG bật | Log debug | Có event đúng logger/level |
| Filter/marker | Event match/non-match | Được giữ/loại đúng sink |
| MDC | requestId xuất và cleanup | Không lẫn request/test khác |
| Duplicate | Một operation phát nhiều lần | Count theo contract, không log dư |
| Privacy | Sentinel token/password giả | Không có ở event/sink |
| Formatter | PatternLayout hoặc formatter riêng | Text đúng, không xuất thêm Throwable ngoài ý muốn |
| JSON schema | Key và type xác định | Parse JSON, assert fields, không so thứ tự key |
| Async | Ghi vào queue | Chờ appender với deadline, không sleep mù |
| File sink | Flush/close qua temp dir | Đọc được nội dung đúng charset |
| Collector | Tích hợp ứng dụng → ingest | Event đến collector với event ID |
| Configuration off | Level/filter/sink khác | Phát hiện việc logger im lặng ngoài mong muốn |
| Parallel tests | Nhiều logger/test cases | Không leak handler, MDC hoặc thay đổi level |

Không phải dự án nào cũng cần mọi test. Chọn mức độ theo rủi ro: audit/security message hoặc định dạng log là contract với collector cần kiểm thử nghiêm ngặt hơn debug text chỉ dành cho con người.

## 23. Những sai lầm phổ biến

| Sai lầm | Vấn đề | Khắc phục |
| --- | --- | --- |
| Chỉ verify `log.info(...)` được gọi | Không biết level/backend có phát event không | Capture LogRecord/ILoggingEvent/LogEvent |
| So `LogRecord.getMessage()` với text đã thay `{0}` | So nhầm template và formatted output | Dùng `Formatter.formatMessage` |
| Dùng `{}` trong JUL | Sai placeholder API | Dùng `{0}`, `{1}` |
| So toàn dòng console có timestamp thật | Flaky theo clock/locale/thread | So semantic fields hoặc cố định metadata |
| Test Logback bằng appender gắn root | Đụng test khác, gây duplicate | Logger riêng, detach trong finally |
| Không start appender | Event không đến, negative test PASS giả | Assert có event positive trước |
| Coi ListAppender = test JSON output | Không kiểm tra encoder/layout | Test JSON encoder trực tiếp |
| Giữ LogEvent mutable qua async | Trường có thể được tái sử dụng/thay đổi | Snapshot/memento khi append |
| `Thread.sleep(100)` chờ async | CI chậm/nhanh khác nhau | Latch/Future/barrier có deadline |
| Assert không có log ngay sau call async | Event có thể vẫn chờ | Drain/await trước negative assertion |
| Chỉ assert `contains("failed")` | Không bắt duplicate/sai event code | Assert count, level, template, args |
| Chỉ test message khi có exception | Không biết Throwable thực được gắn | Assert `getThrown/getThrowableProxy` |
| Bỏ qua MDC/ThreadContext | Có thể rò hoặc lẫn ngữ cảnh | Test propagation và cleanup |
| Log raw token giả để test privacy ở console chung | Dễ leak vào CI | In-memory capture, test sentinel, không dùng secret thật |
| Không restore logger config | Test khác bị sai, rất khó tái hiện | try/finally hoặc test fixture lifecycle |
| Dùng test output để suy ra durability | Đã render không phải đã fsync/commit | Test hợp đồng sink riêng |

## 24. Checklist code review trước khi thêm test logging

1. Bài test xác định **mức kiểm thử** là call site, event, formatter, sink hay collector?
2. Có hợp đồng về event code, template, arguments, level, count và Throwable không?
3. Có dùng đúng placeholder của API: JUL `{0}`, SLF4J/Log4j 2 `{}`?
4. Có phân biệt `getMessage()` với `getFormattedMessage()`/`formatMessage()`?
5. Có một positive assertion chứng minh appender thật sự nhận event không?
6. Có negative assertion về event thừa, level bị tắt và secret giả không?
7. Handler/appender có được gắn vào đúng logger, khởi động và cleanup không?
8. Test có vô tình sửa root level, stdout/stderr hoặc global configuration không?
9. Exception có được gắn đúng vào event; cause và MDC có được kiểm tra khi cần không?
10. Với JSON, có parse và assert key/type/escaping thay vì so nguyên chuỗi không?
11. Với async, có đợi một completion/barrier đáng tin trước assertion không?
12. Với file/collector, có thư mục và môi trường test riêng không?
13. Có dùng dữ liệu giả, không có password/token/PII thật trong fixture và CI logs không?
14. Có test Unicode, null, đa tham số, escaping và logger hierarchy không?
15. Khi đổi backend/version, test có nêu rõ giả định và package API cụ thể không?
16. Kết quả test có đáng tin qua các lần chạy song song và nhiều hệ điều hành không?

## 25. Câu hỏi tự kiểm tra

1. Trong JUL, `LogRecord.getMessage()` khác `Formatter.formatMessage(record)` như thế nào?
2. Tại sao mock verify `logger.info(...)` không đủ chứng minh event được ghi ở file?
3. Khi DEBUG bị tắt, log message không xuất hiện có chứng minh `expensive()` không chạy không?
4. Khi log lỗi, làm sao biết `Throwable` đã được gắn vào event chứ không chỉ được nối vào text?
5. Tại sao `ListAppender` của Logback không đủ để chứng minh JSON encoder xuất đúng schema?
6. Vì sao nên attach test appender vào logger riêng và restore level/additivity trong `finally`?
7. Test event ở pipeline async phải dùng cơ chế chờ gì thay `Thread.sleep`?
8. Vì sao negative assertion ngay sau async log call dễ PASS giả?
9. Nên test structured JSON bằng so chuỗi hay parse JSON? Vì sao?
10. Vì sao privacy test cần cả positive assertion event có mặt và negative assertion không chứa sentinel?
11. Khi một business operation log ERROR hai lần qua controller và service, assertion `contains("failed")` bỏ sót vấn đề gì?
12. Khi dùng `Log4j 2 LogEvent` qua async appender, vì sao có thể cần `toImmutable()`?
13. Thời gian, timezone, thread ID và stack trace line number có nên luôn được hard-code trong expected message không?
14. Có thể suy ra file đã durable trên đĩa chỉ vì test appender nhận event không?

**Gợi ý:** (1) template thô và text đã định dạng; (2) còn filter, layout, sink và lỗi ghi; (3) không, đối số có thể eager; (4) assert `getThrown`/Throwable proxy; (5) chưa chạy JSON encoder; (6) cô lập trạng thái; (7) latch/future/barrier có deadline; (8) event có thể chưa đến; (9) parse và so field/type; (10) tránh PASS giả nếu sink im lặng; (11) duplicate; (12) tránh giữ event mutable/reused; (13) chỉ khi contract yêu cầu và metadata được cố định; (14) không.

## 26. Tài liệu tham khảo chính thức

- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): `getMessage()`, `getParameters()`, `getThrown()`, level, timestamp.
- [Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): overload logging, levels, `Supplier` và handlers.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `isLoggable`, lifecycle.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): `formatMessage(LogRecord)` và localization.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging, fluent API, provider/backend.
- [Logback — Manual](https://logback.qos.ch/manual/index.html): cấu hình logger/appenders, layouts và MDC.
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html): appender lifecycle/filters, điểm thu sự kiện.
- [Log4j 2 — API](https://logging.apache.org/log4j/2.x/manual/api.html): Logger, Message, Throwable và API event.
- [Log4j 2 — Messages](https://logging.apache.org/log4j/2.x/manual/messages.html): message templates và kiểu Message.
- [Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): schema, field resolution và JSON encoding.
- [JUnit User Guide](https://docs.junit.org/current/user-guide/): JUnit Jupiter assertions, lifecycle và `@TempDir`.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên log, sanitization và log injection.
