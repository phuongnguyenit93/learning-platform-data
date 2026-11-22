# Viết kiểm thử logging trong Java Core Logging

## 1. Giới thiệu dự án thực hành

Bài học thuộc nhóm **Dự án thực hành**, chủ đề **Viết kiểm thử logging**. Trong một ứng dụng Java, câu lệnh `logger.info(...)` hoặc `logger.error(...)` có thể chạy mà không ném exception, nhưng điều đó không chứng minh log đúng level, đầy đủ context, bảo toàn exception, không chứa thông tin nhạy cảm, không bị nhân đôi, hoặc đã đến đúng file/collector. Để logging trở thành một thành phần vận hành đáng tin cậy, ta cần **kiểm thử hành vi quan sát được**.

Dự án này xây dựng một bộ kiểm thử logging theo ba tầng:

1. **Unit/event test:** Bắt logging event ngay tại logger/handler/appender và xác minh level, message, parameters, exception và số lượng event.
2. **Integration test:** Sử dụng đúng backend (JUL, Logback, Log4j 2), filter, formatter/encoder, routing và async appender để kiểm tra serialized output.
3. **End-to-end test:** Theo dõi một event có ID riêng từ JVM tới agent/collector/index, xác minh schema và khả năng truy vấn trong một deadline.

Bài thực hành chính dùng **Java 17**, thư viện `java.util.logging` có sẵn trong JDK, không cần Maven hoặc broker. Sau đó mở rộng sang **JUnit 5 + SLF4J + Logback** trong project có dependencies tương ứng. Mỗi phần đều chỉ rõ phạm vi điều đã chứng minh, không dùng “test PASS” ở unit để suy ra collector đã lưu log.

### Mục tiêu đầu ra

Sau khi hoàn thành, bạn có thể:

- Tạo test fixture thu `LogRecord` hoặc `ILoggingEvent` mà không dựa vào việc chụp toàn bộ `System.out`.
- Khẳng định đúng `Level`, logger name, event code, message template, parameters và MDC/context.
- Kiểm tra positive **và** negative events: lỗi phải có log; success không có ERROR; INFO bị filter không được phát; một exception không bị log trùng.
- Xác minh `Throwable` được gắn thật, không chỉ có chuỗi `exception.getMessage()`; kiểm tra cause và suppressed exceptions khi phù hợp.
- Kiểm tra không lộ token, mật khẩu, payload hoặc dữ liệu cá nhân từ message, exception và metadata.
- Dọn dẹp appender/handler, level, MDC và global state để test chạy lặp độc lập.
- Tạo regression/contract tests cho structured logs và formatter, tránh test quá phụ thuộc câu văn/line number.
- Xây test cases cho async logging, routing, overload, collector latency, appender failure và CI.
- Hiểu rõ giới hạn: logging là quan sát, **không thay thế** assertion về business outcome hoặc tính bền vững của một giao dịch.

## 2. Đề bài và tiêu chí nghiệm thu

**Bối cảnh:** Một service xử lý checkout cần ghi log khi đơn hàng thành công và khi gặp lỗi thanh toán. Quy ước giả định của bài:

| Sự kiện | Điều kiện | Level | Hợp đồng |
| --- | --- | --- | --- |
| `checkout.succeeded` | Xử lý hoàn tất theo contract của handler | INFO | Có `order_id`, không có Throwable |
| `checkout.failed` | Handler thất bại vì gateway timeout | ERROR trong SLF4J/Logback hoặc SEVERE trong JUL | Có `order_id`, `error_code`, Throwable và cause |
| `checkout.recovered` | Retry/fallback thành công, nếu có | INFO/WARN tùy policy | Không phát terminal failure sai |
| INFO bị effective level WARNING chặn | Logger bị cấu hình chỉ giữ WARNING trở lên | Không phát INFO | Không được xuất vào capture sink |
| Appender filter loại INFO | Filter ở Handler/Appender từ chối record | Không đến sink tương ứng | Phải phân biệt với logger level |
| Secret từ request | Một tham số token giả được truyền vào handler | Không log secret | Bảo vệ cả formatted output và exception chain |

**Acceptance criteria:**

- [ ] Hai lời gọi xử lý trong happy/error path sinh **đúng hai records** ở Handler thử nghiệm.
- [ ] Success là INFO, có message template và order ID trong parameters.
- [ ] Failure là SEVERE, giữ đúng instance Throwable đã ném và root cause.
- [ ] Không có duplicate ERROR và không có success giả cho request lỗi.
- [ ] Token giả `TEST_SECRET_DO_NOT_LOG` không xuất hiện trong bản ghi đã thu.
- [ ] Khi effective level là WARNING, success INFO không đi vào Handler.
- [ ] Khi Handler filter loại INFO, record không tới sink đó.
- [ ] Test cleanup/restore trạng thái logger sau khi chạy.
- [ ] Program Java 17 in `test=PASS` sau các assertions và có stdout xác định.
- [ ] Các tests phụ thuộc backend ngoài được đánh dấu rõ, không trình bày như mã JDK chạy độc lập.

**Không xem là nghiệm thu:** “Ứng dụng chạy không throw”, “console nhìn có chữ ERROR”, “Mockito verify logger được gọi” hoặc “chụp snapshot rồi so toàn bộ timestamp”. Mỗi kiểu này chỉ chứng minh một phần nhỏ của đường logging.

## 3. Hiểu logging pipeline trước khi test

Một đường đi tiêu biểu:

```text
Business code
    |
    +--> Logger call, message template, Throwable, context
    |
    v
Logger level / filter
    |
    v
LogRecord / LoggingEvent
    |
    +--> appender / handler filter
    |
    v
Formatter / JSON encoder
    |
    +--> sync file/stdout OR async queue
    |
    v
Log agent / shipper
    |
    v
Collector / parser / exporter
    |
    v
Index / storage / dashboard / alert
```

Test ở mỗi hop trả lời một câu hỏi khác:

| Kiểu test | Assert được | Không tự chứng minh |
| --- | --- | --- |
| Test nghiệp vụ | Thao tác success/failure/rollback có đúng | Log được gửi hay chưa |
| Verify logger mock | Code gọi API logger với arguments nào | Backend thực có tạo event không |
| In-memory JUL Handler | `LogRecord` thực được publish, gồm level/message/Throwable | Console/file/collector có nhận không |
| Logback ListAppender | `ILoggingEvent` với level/template/MDC/ThrowableProxy | JSON serialization và remote sink |
| Encoder/formatter integration | Serialized text/JSON đúng schema và escaping | Remote collector nhận/đã index |
| File/stdout integration | Local sink nhận log | Agent có đọc và gửi đúng không |
| End-to-end canary | Event cụ thể tìm thấy ở backend trong thời hạn | Mọi event khác chắc chắn không mất |
| Load/failure injection | Queue/drop/blocked/write failure theo policy | Sẽ không có sự cố logging tương lai |

**Nguyên tắc thiết kế assertion:** Không dùng bằng chứng ở một hop để kết luận thay cho các hop phía sau. Appender đã enqueue log không đồng nghĩa durable storage; collector trả 2xx không tự bảo đảm event đã searchable, trừ khi contract của backend nói vậy.

### Test dương và test âm

Một test tốt gồm:

- **Positive:** Khi exception xảy ra, có `checkout.failed` đúng level, order ID và Throwable.
- **Negative:** Không có `checkout.succeeded` cho đơn lỗi; không log token; không in hai stack traces; INFO bị filter không đến sink.
- **Count:** Khi policy chỉ cho một terminal event, assert đúng **1** event loại đó, không chỉ `>=1`.
- **Identity/context:** Cùng request ID/order ID ở đúng records, không bị MDC của request khác dính vào.
- **Boundary:** Nếu test async, phải quan sát sau một drain/ack phù hợp, không kết luận chỉ vì 50 ms chưa thấy.

## 4. Cấu trúc đề xuất cho dự án

Bài chính tạo một file Java 17 chạy trực tiếp:

```text
logging-test-lab/
  LoggingTestLab.java
```

Biên dịch `javac LoggingTestLab.java` và chạy `java LoggingTestLab`. Không cần JUnit vì đây là **executable self-checking harness**: mỗi điều kiện dùng assertion và process kết thúc có lỗi nếu không đạt.

Khi đưa vào một project Maven/Gradle thực tế, có thể mở rộng:

```text
src/
  main/java/com/example/checkout/CheckoutService.java
  test/java/com/example/checkout/CheckoutLoggingTest.java
  test/resources/logback-test.xml
```

Dùng JUnit Jupiter và backend thực, tách fixtures/helper classes khi cần. Đừng dùng root logger chung cho nhiều test đang chạy song song vì có thể tạo race hoặc dính state.

### Test naming

Tên test nên mô tả **hành vi quan sát được**:

- `shouldEmitInfoWithOrderIdOnSuccess`
- `shouldAttachThrowableOnFailure`
- `shouldNotLogSecretToken`
- `shouldNotEmitInfoWhenDisabled`
- `shouldNotDuplicateTerminalFailure`
- `shouldRestoreLoggerConfiguration`
- `shouldSerializeErrorAsStructuredJson`
- `shouldKeepTraceContextForAsyncWork`

Tránh tên chung chung như `testLog()` hoặc chỉ kiểm tra snapshot của text, khiến người sau không biết hợp đồng nào đang được bảo vệ.

## 5. Java 17 chạy độc lập: viết bộ test logging thật

Chương trình dùng một `java.util.logging.Handler` in-memory. Handler giữ danh sách `LogRecord` mà JUL thực sự gửi tới nó. Service ghi một event INFO khi thành công, một event SEVERE với Throwable khi thất bại.

**Giới hạn:** Đây là unit/event test cho JUL, không phải giả lập durable file, JSON log, network collector hoặc logging async. Program chạy một thread; `ArrayList` an toàn trong phạm vi demo này nhưng không tự thread-safe khi dùng shared Handler với nhiều threads.

Tạo file **`LoggingTestLab.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingTestLab {
    static final class MemoryHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<>();

        MemoryHandler() {
            setLevel(Level.ALL);
        }

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

    static final class CheckoutException extends RuntimeException {
        CheckoutException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class CheckoutService {
        private final Logger logger;

        CheckoutService(Logger logger) {
            this.logger = logger;
        }

        void checkout(String orderId, String secret, boolean shouldFail) {
            // secret deliberately never goes into a log record.
            if (!shouldFail) {
                logger.log(Level.INFO,
                        "event=checkout.succeeded order_id={0}",
                        orderId);
                return;
            }

            try {
                throw new IllegalStateException("gateway timeout");
            } catch (IllegalStateException cause) {
                CheckoutException failure = new CheckoutException(
                        "checkout failed", cause);
                logger.log(Level.SEVERE,
                        "event=checkout.failed order_id=" + orderId
                        + " error_code=GATEWAY_TIMEOUT", failure);
                throw failure;
            }
        }
    }

    static void require(boolean condition, String description) {
        if (!condition) {
            throw new IllegalStateException(
                    "Assertion failed: " + description);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lab.checkout");
        Level originalLevel = logger.getLevel();
        boolean originalParentSetting = logger.getUseParentHandlers();

        MemoryHandler capture = new MemoryHandler();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        logger.addHandler(capture);

        String testSecret = "TEST_SECRET_DO_NOT_LOG";
        CheckoutService service = new CheckoutService(logger);

        try {
            service.checkout("order-7", testSecret, false);

            CheckoutException caught = null;
            try {
                service.checkout("order-8", testSecret, true);
            } catch (CheckoutException failure) {
                caught = failure;
            }

            require(caught != null, "exception propagated");

            List<LogRecord> events = capture.snapshot();
            require(events.size() == 2, "exactly two events");

            LogRecord success = events.get(0);
            LogRecord failure = events.get(1);

            require(success.getLevel() == Level.INFO, "success level");
            require("event=checkout.succeeded order_id={0}"
                    .equals(success.getMessage()), "success template");
            require(success.getParameters() != null
                    && success.getParameters().length == 1
                    && "order-7".equals(
                        success.getParameters()[0]), "success order id");
            require(success.getThrown() == null,
                    "success has no exception");

            require(failure.getLevel() == Level.SEVERE,
                    "failure level");
            require("event=checkout.failed order_id=order-8"
                    .concat(" error_code=GATEWAY_TIMEOUT")
                    .equals(failure.getMessage()), "failure message");
            require(failure.getThrown() == caught,
                    "Throwable identity");
            require(caught.getCause() instanceof IllegalStateException,
                    "root cause type");
            require("gateway timeout".equals(
                    caught.getCause().getMessage()), "root cause message");

            for (LogRecord event : events) {
                String text = event.getMessage();
                require(!text.contains(testSecret), "secret in message");
                Throwable thrown = event.getThrown();
                if (thrown != null) {
                    require(!String.valueOf(thrown.getMessage())
                            .contains(testSecret), "secret in exception");
                    if (thrown.getCause() != null) {
                        require(!String.valueOf(
                                thrown.getCause().getMessage())
                                .contains(testSecret), "secret in cause");
                    }
                }
            }

            // Negative case 1: logger level blocks INFO.
            logger.setLevel(Level.WARNING);
            service.checkout("order-9", testSecret, false);
            require(capture.snapshot().size() == 2,
                    "logger level excludes INFO");

            // Negative case 2: Handler filter rejects INFO.
            logger.setLevel(Level.ALL);
            Filter onlySevere = record ->
                    record.getLevel().intValue() >= Level.SEVERE.intValue();
            capture.setFilter(onlySevere);
            service.checkout("order-10", testSecret, false);
            require(capture.snapshot().size() == 2,
                    "handler filter excludes INFO");

            System.out.println("events=" + events.size());
            System.out.println("success_level="
                    + success.getLevel().getName());
            System.out.println("success_order="
                    + success.getParameters()[0]);
            System.out.println("failure_level="
                    + failure.getLevel().getName());
            System.out.println("failure_exception="
                    + caught.getClass().getSimpleName());
            System.out.println("cause="
                    + caught.getCause().getClass().getSimpleName());
            System.out.println("logger_filtered_info=PASS");
            System.out.println("handler_filtered_info=PASS");
            System.out.println("secret_absent=PASS");
            System.out.println("duplicate_absent=PASS");
            System.out.println("test=PASS");
        } finally {
            capture.setFilter(null);
            logger.removeHandler(capture);
            capture.close();
            logger.setLevel(originalLevel);
            logger.setUseParentHandlers(originalParentSetting);
        }
    }
}
```

Lệnh chạy:

```bash
javac LoggingTestLab.java
java LoggingTestLab
```

**stdout chính xác:**

```text
events=2
success_level=INFO
success_order=order-7
failure_level=SEVERE
failure_exception=CheckoutException
cause=IllegalStateException
logger_filtered_info=PASS
handler_filtered_info=PASS
secret_absent=PASS
duplicate_absent=PASS
test=PASS
```

### Vì sao chương trình in đúng kết quả?

1. `Logger` được đặt `Level.ALL` và Handler `Level.ALL`. Mỗi event tới Handler ngay trong cùng thread vì đây là JUL Handler đồng bộ của demo.
2. Success ghi `Level.INFO` với **message template** và một parameter `order-7`. `LogRecord.getMessage()` trả template, không nhất thiết là text đã format.
3. Failure tạo `IllegalStateException` làm cause, wrap trong `CheckoutException`, gọi overload `logger.log(Level, String, Throwable)` rồi rethrow **cùng instance**. `getThrown() == caught` phải đúng.
4. Danh sách có đúng hai records sau hai nghiệp vụ. Nếu code log terminal failure hai lần, assertion count sẽ fail.
5. Secret giả được truyền vào hàm nhưng không đưa vào message hay exception. Đây là bài test bảo vệ những fields đang được capture, **không thay thế** kiểm tra toàn bộ JSON encoder/MDC/sink trong production.
6. Sau đó logger đổi `Level.WARNING`, lời gọi INFO từ success bị chặn **trước Handler**, nên số records không tăng.
7. Logger trở lại ALL, nhưng Handler có filter chỉ chấp nhận `SEVERE` trở lên. Success INFO có thể được tạo ở logger nhưng **không được thêm vào capture**.
8. `setUseParentHandlers(false)` tránh JUL parent handlers in thêm log lên stderr. `finally` restore level, parent handlers và tháo Handler để tránh leak sang test khác.
9. Không in timestamp/thread IDs và không dùng random, nên stdout không phụ thuộc thời gian/locale.
10. Chỉ khi **mọi assertion** đạt, dòng `test=PASS` mới xuất hiện.

**Lưu ý kỹ thuật:** Vì `java.util.logging.Logger` dùng hierarchy và configuration có thể bị thay từ nơi khác, demo bảo đảm fixture tại logger `lab.checkout` trong một JVM chạy độc lập. Với test suite song song, không nên dùng chung logger name hoặc thay root logger vì nguy cơ race; hãy tạo logger riêng/isolation phù hợp.

### Thử sửa để thấy test bắt lỗi

- Đổi `Level.SEVERE` thành `Level.INFO` trong failure: assertion `failure level` sai.
- Đổi `logger.log(Level.SEVERE, message, failure)` thành `logger.severe(failure.getMessage())`: `getThrown()` mất, test lỗi.
- Ghi thêm một ERROR trước khi rethrow: `events.size() == 2` không đạt.
- Nối `testSecret` vào message: assertion security fail.
- Bỏ `setUseParentHandlers(false)`: stdout vẫn có thể giống nhưng stderr/root appender xuất thêm log; cần integration test nếu routing parent là contract.
- Bỏ filter ở Handler: success `order-10` được capture, negative assertion fail.
- Thay success template bằng câu văn khác nhưng vẫn contract event code: test strict template sẽ fail; cân nhắc test dựa event code/fields khi project dùng structured logging, tránh phụ thuộc không cần thiết vào câu wording.

## 6. Giải thích sự khác nhau giữa level filter và Handler filter

Trong JUL:

- `Logger.setLevel(Level.WARNING)` quyết định những records được logger chấp nhận theo effective level. INFO bị bỏ trước khi Handler nhận.
- `Handler.setLevel(...)` và `Handler.setFilter(...)` kiểm soát những records **được Handler cụ thể xử lý**. Một logger có thể fan-out tới nhiều handlers với rules khác nhau.
- `Logger.setUseParentHandlers(false)` chặn propagation tới parent handlers; nếu bật parent và các handlers cũng được gắn ở logger con, có thể có output trùng ở nhiều sinks.

Điều này tạo ra hai bài test khác nhau:

1. **Không tạo:** INFO bị level chặn ngay tại logger.
2. **Không tới sink:** INFO qua logger nhưng bị Handler filter từ chối.

Nếu chỉ assert “không tìm thấy ở file X”, bạn chưa biết nó bị lọc ở logger, bị route sang file Y, bị appender drop hay chưa searchable ở backend.

### Negative assertions cần chờ đúng boundary

Ở demo Handler đồng bộ, đọc snapshot sau lời gọi logger là đủ. Với async appender, một event có thể nằm trong queue; muốn chứng minh không đến sink, phải biết queue đã drain/flush theo semantics và đã qua deadline quan sát. `Thread.sleep(100)` không phải một bảo đảm trên CI.

## 7. Kiểm thử exception: gắn Throwable thật

Một bug phổ biến với SLF4J:

```java
// Chỉ truyền text: nhiều backend sẽ không có Throwable.
logger.error("Checkout failed: {}", exception.getMessage());
```

Trong khi:

```java
// Truyền Throwable: backend có thể render stack trace/cause.
logger.error("Checkout failed", exception);
```

Hai đoạn là **trích đoạn SLF4J**, cần logger và exception đã được khai báo. Một test chỉ thấy `Checkout failed` trong output sẽ không phát hiện biến thể đầu tiên mất stack trace.

Cần kiểm tra:

- Exception type đúng.
- Outer exception/cause chain đúng.
- Suppressed exceptions nếu code dùng try-with-resources/`addSuppressed`.
- Exception được gắn vào logging event, không chỉ format thành string.
- Error code/outcome có nghĩa theo nghiệp vụ.
- Stack trace ở encoder thật có được render/ẩn theo chính sách.
- Không có secret trong `Throwable.getMessage()`, cause/suppressed hoặc structured stacktrace fields.

Không hard-code line numbers stack trace làm golden string: đổi một dòng source sẽ làm test fail vô ích. Kiểm thử model bằng API, layout/encoder bằng những thuộc tính bền vững.

### Một exception có thể được log nhiều lần

```text
Repository throws
     |
Service logs ERROR and rethrows
     |
ControllerAdvice logs ERROR again
     |
Container logs another ERROR
```

Ba dòng lỗi giống nhau có thể làm alert đếm ba lần dù chỉ có một request thất bại. Nên xác định **ranh giới sở hữu terminal error**. Tầng thấp có thể ném exception kèm cause mà không log; tầng boundary phát một event đầy đủ. Khi retry có thể ghi attempt events riêng và một terminal event khi hết retry.

Không có quy tắc tuyệt đối một exception trên toàn hệ phân tán chỉ được log một lần: nhiều service có thể cần event riêng với context khác. Test cần assert **số logical events dự kiến theo scope**.

## 8. Chuyển sang JUnit 5 + SLF4J + Logback

Trong ứng dụng thực dùng SLF4J với Logback Classic, `ch.qos.logback.core.read.ListAppender` có thể thu `ILoggingEvent` thay vì `System.out`. Ví dụ sau **không chạy chỉ với JDK**; cần JUnit Jupiter, `slf4j-api`, `logback-classic` và `logback-core` phiên bản tương thích trong test classpath.

### Test class mẫu

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.*;

class CheckoutLogbackTest {
    @Test
    void attachesThrowableAndKeepsRequiredFields() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                "test.checkout.logging.example");

        Level previousLevel = logger.getLevel();
        boolean previousAdditivity = logger.isAdditive();

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.setContext(logger.getLoggerContext());
        appender.start();

        logger.setLevel(Level.ERROR);
        logger.setAdditive(false);
        logger.addAppender(appender);

        try {
            IllegalStateException cause =
                    new IllegalStateException("gateway unavailable");

            logger.error("event={} order_id={}",
                    "checkout.failed", "order-7", cause);

            assertEquals(1, appender.list.size());
            ILoggingEvent event = appender.list.get(0);

            assertEquals(Level.ERROR, event.getLevel());
            assertEquals("test.checkout.logging.example",
                    event.getLoggerName());
            assertEquals("event=checkout.failed order_id=order-7",
                    event.getFormattedMessage());

            assertNotNull(event.getThrowableProxy());
            assertEquals(IllegalStateException.class.getName(),
                    event.getThrowableProxy().getClassName());
        } finally {
            logger.detachAppender(appender);
            appender.stop();
            logger.setLevel(previousLevel);
            logger.setAdditive(previousAdditivity);
        }
    }
}
```

**Giải thích:**

- Test dùng tên logger riêng, không thay root logger của ứng dụng.
- `getFormattedMessage()` kiểm tra placeholder rendering; `getMessage()` ở JUL/Logback là hai API với ngữ nghĩa khác nhau cần đọc tài liệu backend.
- `getThrowableProxy()` là biểu diễn Throwable của Logback, không phải luôn cùng Java object identity với exception gốc.
- `setAdditive(false)` ngăn record test lan lên root appenders; phải restore sau test.
- `finally` tháo và stop appender, restore level/additivity để các tests khác không chịu ảnh hưởng.
- Một test unit pass ở ListAppender **không chứng minh** file/JSON encoder/collector đã nhận event.

### Cấu hình dependency cần lưu ý

Với Maven, project cần JUnit Jupiter cho tests và SLF4J + một backend Logback tương thích. Với Gradle, thêm tương đương trong `testImplementation` hoặc runtime theo build setup. **Không buộc người học copy một version không được kiểm chứng**: lựa chọn version tương thích với Spring Boot/BOM hoặc nền tảng đang dùng, xem dependency tree để tránh nhiều SLF4J providers cùng lúc.

Khi dùng Log4j 2 backend, **không ép cast logger thành `ch.qos.logback.classic.Logger`**. Hãy dùng fixture theo Log4j 2 API/implementation hoặc một abstraction kiểm thử khác. Một chương trình sử dụng SLF4J façade không nhất thiết dùng Logback trong runtime.

## 9. Kiểm thử MDC/correlation ID

Log phục vụ observability cần context, ví dụ `request_id`, `trace_id`, `message_id` hoặc `operation_id`. Nếu thiếu hoặc sai context, dashboard có thể ghép log của hai người dùng vào cùng trace.

Với SLF4J, có thể scope một MDC key:

```java
String prior = org.slf4j.MDC.get("request_id");
try {
    org.slf4j.MDC.put("request_id", "req-test-7");
    // Gọi code phát log trong scope này.
} finally {
    if (prior == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", prior);
    }
}
```

Đây là **đoạn tích hợp**, không phải standalone Java JDK. Nếu nhiều keys, nên restore context map/closeable scope phù hợp theo backend.

Các test cần có:

1. Event khi request A chạy có `request_id=A`.
2. Sau khi scope A kết thúc, request B không còn mang ID A.
3. Nếu worker xử lý ở thread khác, context được propagate theo thiết kế.
4. Nếu trace context thiếu hoặc không đáng tin, log có fallback rõ ràng.
5. Không để password, token, email hoặc raw payload vào MDC.
6. Encoder thực sự xuất những keys cần query; một `%msg`-only layout có thể bỏ qua MDC.
7. Multi-tenant/authorization data không bị lấy từ untrusted header mà không validate.

**Không tự giả định MDC lan qua mọi `ExecutorService`/`CompletableFuture`.** Test nên kiểm tra case thread pool reuse và cleanup; use instrumentation đúng framework thay vì phụ thuộc hành vi may rủi của ThreadLocal.

## 10. Viết test cho structured JSON logs

Khi chuyển từ text sang JSON, phải test **schema**, không chỉ substring.

Một event minh họa:

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event_code": "checkout.failed",
  "order_id": "order-7",
  "error_code": "GATEWAY_TIMEOUT",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "exception_type": "java.lang.IllegalStateException",
  "duration_ms": 245
}
```

Đây là **schema ví dụ**, không phải output mặc định của Logback/Log4j 2/OpenTelemetry. Test đúng nên:

- Parse serialized output bằng thư viện JSON của project, rồi assert required keys và **types**.
- Kiểm tra timestamp có offset/UTC rõ, không phụ thuộc timezone host.
- Kiểm tra `duration_ms` là number, `order_id` là string để giữ leading zero.
- Kiểm tra event code/error code và enum values ổn định.
- Kiểm tra `exception_type` và stack trace/cause theo policy.
- Kiểm tra `trace_id` khi có context, missing/null semantics khi không.
- Kiểm tra không có secret trong **toàn bộ** output kể cả exception/MDC.
- Kiểm tra quotes, backslash, newline và Unicode được escape đúng.
- Nếu NDJSON dùng một event một dòng, test multiline stack trace không bị chia thành nhiều logical events.
- Kiểm tra collector transform/index mapping không làm thay đổi type/field name ngoài contract.

Một test như `assertTrue(jsonText.contains("error_code"))` quá yếu: `"error_code"` có thể chỉ nằm trong field message. Phải parse và assert `$.error_code` ở vị trí đã thống nhất.

### Schema version và compatibility

Một thay đổi `"duration_ms": 245` thành `"duration_ms": "245ms"` có thể phá dashboards/aggregations. Thêm field optional có thể compatible nếu consumer bỏ qua unknown fields; đổi type, rename required field, thay meaning của `timestamp` thường là breaking. Viết contract tests với fixtures v1/v2 và migration rules, không tự coi “có JSON” là đủ ổn định.

## 11. Kiểm thử các mức độ log và logger hierarchy

Một bộ tests thực tế cần trả lời:

| Kịch bản | Assert |
| --- | --- |
| Logger level INFO | DEBUG/FINE không phát, INFO/WARN/ERROR có thể phát theo backend |
| Logger level WARN | INFO không qua effective level |
| Handler/Appender filter | Event bị từ chối không tới **sink đó** |
| Logger con với additivity | Record có/không tới parent như cấu hình |
| Hai appenders | Đúng routing, không nhân đôi bất ngờ |
| Root logger level khác con | Effective level/route theo framework, không dựa trực giác |
| Async appender | Đúng quyết định enqueue/flush/drain và drops |
| Logger configuration reload | Level/filter thay đổi theo policy, không mất critical events |

Lưu ý JUL dùng `FINE/INFO/WARNING/SEVERE`, còn SLF4J/Logback thường dùng `DEBUG/INFO/WARN/ERROR`. Test nên dựa trên enum level/backend thực tế, không tìm chuỗi `"ERROR"` trong message.

### Additivity và duplicate

Trong Logback, một logger con có appender và additive=true có thể chuyển cùng event lên parent appender. Nếu cả hai cùng gửi vào cùng collector, nhìn từ backend có thể thấy hai records tương đương. Không kết luận business lỗi hai lần chỉ vì có hai ERROR lines.

Muốn phát hiện duplicate:

- Phát event có `event_id`/`operation_id` duy nhất.
- Lọc theo `event_code` + ID + route.
- Assert count ở từng appender/sink và count tổng theo fan-out policy.
- Kiểm tra agent có thu cả file và stdout từ cùng một nguồn không.
- Với retry, phân biệt **attempt events** hợp lệ với **terminal failure** chỉ được phát một lần theo contract.

## 12. Test exception cause, suppressed và lỗi đã xử lý

Một exception có thể được wrap:

```text
CheckoutException: checkout failed
  Caused by IllegalStateException: gateway timeout
    Suppressed IOException: cleanup failure
```

Muốn test đúng:

- `outer.getCause()` đúng type/error code.
- `outer.getSuppressed()` hoặc `cause.getSuppressed()` ở đúng object được gắn suppressed; chúng không tự động chuyển sang outer.
- Logging event có Throwable hoặc ThrowableProxy, không chỉ text.
- Formatted stack trace có `Caused by`/`Suppressed` nếu encoder policy yêu cầu, nhưng không assert exact source line numbers.
- Nếu exception bị handled/recovered, policy level/outcome phản ánh **đã hồi phục** chứ không tạo terminal error giả.

Đừng gọi `printStackTrace()` rồi logger.error(...) cùng Throwable ở mọi tầng. Nó gây duplicate, thiếu structured metadata và khó quản lý dữ liệu nhạy cảm.

### Test retry

Với message-driven/HTTP retry:

1. Attempt đầu gặp transient failure, có log `retry_planned` theo policy.
2. Các attempt sau có `attempt`, error category, backoff.
3. Nếu thành công ở attempt 3, có success/recovered outcome; không có terminal `retry_exhausted`.
4. Nếu hết budget, có đúng một terminal failure event và policy DLQ.
5. Không ghi “retry đã được broker xác nhận” chỉ vì application quyết định retry.
6. Nếu timeout remote side effect, outcome có thể UNKNOWN; log không được khẳng định business rollback chắc chắn.

Event codes trong đoạn này là **ví dụ contract ứng dụng**, không phải event sẵn có của Java logging.

## 13. Kiểm thử security và redaction

Đây là một trong những lý do quan trọng nhất để test logging: ngoại lệ có thể mang thông tin nhạy cảm dù lập trình viên không chủ ý.

### Canary secret

Dùng một chuỗi giả:

```text
TEST_SECRET_DO_NOT_LOG
```

Gây lỗi có input chứa chuỗi này rồi kiểm tra **mọi trường output**:

- Message/formatted message.
- MDC/structured arguments.
- Exception text, cause, suppressed và stack trace.
- HTTP header/query/URL fields.
- File/stdout, agent export và index.
- Internal status/error channel của logging backend khi phù hợp.

Test phải khẳng định **không có** chuỗi canary ở những sink không được phép, nhưng không làm thất thoát secret thật trong test fixtures.

### Log injection

Input chứa newline:

```text
username=bob
ERROR admin granted
```

Nếu text appender ghi trực tiếp không escape, output có thể trông như một log ERROR mới. JSON encoder chuẩn sẽ escape newline trong string nếu được cấu hình đúng. Test phải parse được một event JSON hợp lệ, không tạo một logical event giả. Không ghép JSON thủ công từ raw input hoặc truyền nguyên object chứa token cho logger.

### Data minimization

- Chỉ ghi IDs/metadata đã được cho phép.
- Tránh password, token, private key, cookie, card number và PII.
- Dùng error code thay cho raw exception message khi có thể.
- Tránh đưa user IDs/raw message strings làm Prometheus labels do cardinality và privacy.
- Audit/security logs có retention/access/integrity policy riêng, không chung quyết định sampling DEBUG/INFO.

**Sampling không làm log secret trở nên an toàn**: một event được giữ với xác suất 1% vẫn có thể rò dữ liệu.

## 14. Async logging: test đúng thời điểm

Với Logback AsyncAppender, Log4j 2 AsyncLogger hoặc một network exporter:

```text
caller -> enqueue -> writer thread -> sink -> agent -> collector -> index
```

Khi `logger.error(...)` trả về, event có thể chỉ mới nằm trong queue. Assertion ngay sau đó rằng backend “không nhận” sẽ flaky.

Một test đúng nên:

1. Gắn `test_event_id` duy nhất.
2. Xác định **hop** đang kiểm tra: queue accepted, file written, collector acknowledged hay searchable.
3. Dùng flush/drain/ack theo semantics backend nếu có.
4. Poll có **deadline hữu hạn**, không chỉ `Thread.sleep(100)`.
5. Khi deadline hết, phân biệt `NOT_EMITTED`, `FILTERED`, `DROPPED`, `NOT_DELIVERED`, `NOT_SEARCHABLE` hoặc `QUERY_ERROR` nếu có evidence.
6. Đo drop/queue depth/blocked enqueue duration, nhất là khi tải cao.
7. Test shutdown khi còn pending events theo policy.

**Không gọi appender accepted = durable storage.** Một write vào OS buffer, một publish confirm của network client hoặc một HTTP 2xx không nhất thiết có cùng durability semantics ở mọi backend.

### Failure injection

Tạo lỗi trong staging hoặc isolated test fixture:

| Lỗi | Assert cần thiết |
| --- | --- |
| Appender file permission denied | Status/error counter tăng; business response theo fail-open/closed policy |
| Disk full/read-only | Write/flush failure có tín hiệu, không recursive logging |
| Async queue full | Bị block/drop theo policy, có counter riêng |
| Collector timeout | Retry/backoff bounded; queue age/backlog quan sát được |
| TLS/auth failure | Không fallback sang plaintext hoặc sink rộng quyền |
| Log shipper down | Canary missing, backlog/recovery rõ |
| Index reject schema | Rejected/parse error metrics tăng |
| Duplicate delivery | Stable event ID/dedup policy hoạt động |
| Formatter exception | Không làm vòng log error recursion |
| Abrupt shutdown | Biết giới hạn flush/durability |

Không chủ động làm đầy disk hoặc kill collector production chỉ để test. Dùng staging/isolated environment và một rollback plan rõ ràng.

## 15. Tích hợp Maven/Gradle và CI

Một dự án production nên có các lớp tests:

- **Unit nhanh:** In-memory Handler/ListAppender, business error classification, exception propagation.
- **Encoder integration:** JSON schema, level filter, MDC, stack trace, sensitive data masking.
- **Infrastructure integration:** File appender, rotation, stdout/shipper, queue behavior.
- **End-to-end có deadline:** Collector/index canary và alert rule.
- **Performance/chaos:** Burst exceptions, queue full, blocked callers, retry/export outage.

Không nhất thiết mỗi Pull Request đều chạy E2E với collector thật; nhưng khi thay logging config, encoder, schema, bridge hoặc agent, cần có pipeline phù hợp để chứng minh compatibility.

### Các cách giữ tests không flaky

1. Dùng IDs duy nhất cho từng test.
2. Tránh phụ thuộc thứ tự tests.
3. Dùng `Clock.fixed(...)` khi timestamp **của ứng dụng** là dữ liệu cần test; logger backend có thể dùng clock riêng.
4. Không assert exact timestamp hiện tại, tên thread hoặc stack frame line number nếu không phải contract.
5. Dọn appender/handler, restore levels, filters và additivity trong `finally`.
6. Không dùng `System.setOut`/`System.setErr` trên toàn suite song song trừ khi cô lập process.
7. Dùng logger name riêng hoặc test context để tránh shared static config.
8. Với async, chờ bằng signal/timeout thay vì sleep cố định.
9. Dùng dummy tokens, không dùng secret production trong fixtures.
10. Kiểm tra warning từ nhiều SLF4J providers/bindings và backend thực dùng trong CI giống kỳ vọng.

### Artifact cho review

Một Pull Request triển khai testing logging nên có:

- Danh sách acceptance criteria/từng event contract.
- Test code và cách chạy.
- Kết quả unit và integration tests.
- Mẫu serialized log **giả lập an toàn** minh họa schema.
- Ghi chú về async/durability boundary không được test tại unit.
- Tài liệu các lỗi logging đã bắt được và những việc còn thuộc vận hành.
- Không kèm token, raw customer payload hoặc stack traces chứa dữ liệu thật.

## 16. Ma trận kiểm thử tổng hợp

| ID | Kịch bản | Assertion dương | Assertion âm |
| --- | --- | --- | --- |
| L1 | Checkout success | Một INFO `checkout.succeeded` với ID | Không có ERROR/Throwable |
| L2 | Checkout fail | Một SEVERE/ERROR với Throwable và cause | Không success giả |
| L3 | Error ở service rồi propagate | Boundary có terminal event | Không log 2–3 lần cùng error ngoài policy |
| L4 | INFO disabled | Không tới Handler vì logger level | Không suy nhầm là sink lỗi |
| L5 | Handler filter deny INFO | Sink target không nhận | Event vẫn có thể route sang sink khác theo policy |
| L6 | Exception wrap | Cause/suppressed được giữ | Không chỉ có outer message |
| L7 | Recovery success | Outcome RECOVERED và mức log phù hợp | Không terminal failure giả |
| L8 | Retry exhausted | Một terminal event và attempt count | Không thử quá budget |
| L9 | Appender additivity | Đúng routes/count | Không duplicate ngoài policy |
| L10 | MDC scope | Request A/B có context đúng | Không leak ID cross-thread |
| L11 | Logger config reload | Effective level và filters đúng | Không silent drop critical events |
| L12 | JSON encoder | Required fields/types/timestamp đúng | Không string hóa numeric fields |
| L13 | Input chứa newline/quote | JSON parse hợp lệ | Không log injection |
| L14 | Input chứa secret giả | Redaction đúng ở mọi sink | Không rò secret trong cause/MDC |
| L15 | Stack trace dài/multiline | Có exception type và logical record đúng | Không split thành nhiều events ngoài policy |
| L16 | Async delivery | Event tới hop đã định trong deadline | Không dùng sleep suy đoán |
| L17 | Collector down | Có retry/backlog/alert | Không giả định logger call là indexed |
| L18 | Full async queue | Block/drop theo policy, metrics đúng | Không mất critical events im lặng |
| L19 | Source log vs indexed log | Đối chiếu event ID/schema | Không đếm duplicate như business lỗi |
| L20 | Logging status/handler failure | Internal health/metrics phát hiện | Không recursive logging |
| L21 | Framework upgrade | Contract fields và severity mapping còn đúng | Không dựa raw message snapshot |
| L22 | Shutdown/restart | Expected flush/recovery theo contract | Không khẳng định durability khi chưa có ACK |
| L23 | Security audit | Route/retention/access đúng | Không sample bắt buộc ngoài policy |
| L24 | Không có traffic | Không có false alert khi idle | Canary/health vẫn phát hiện hỏng pipeline |

Mỗi project nên ghi rõ **ý nghĩa của event và expected count** trước khi chạy test. Một chính sách INFO/WARN ở ví dụ có thể khác với hệ thống thật; tests phải kiểm tra contract thực, không biến convention minh họa thành quy tắc bắt buộc cho mọi service.

## 17. Debug khi kiểm thử logging thất bại

### Test báo “expected 1 event, got 0”

Kiểm tra lần lượt:

1. Code thực sự đi vào nhánh ghi log chưa?
2. Logger name và logger instance có đúng không?
3. Effective logger level có lọc event không?
4. Logger/appender filter có `DENY` không?
5. Appender/Handler đã start và attach trước khi gọi code chưa?
6. Root/additivity hoặc routing có gửi sang sink khác không?
7. Test có dùng backend khác với cast Logback giả định không?
8. Với async, event đã được drain hay chưa?
9. Collector/index có parse/schema/query error không nếu test E2E?

Đừng vội sửa acceptance criteria thành `>=0` hoặc thêm `Thread.sleep(1000)` để “pass”.

### Test báo “expected 1 event, got 2”

- Code có log-and-rethrow ở nhiều tầng?
- Logger con và root có gắn appender nhận cùng event?
- Appender test đã được attach lần trước mà chưa detach?
- Agent có thu cả stdout và file?
- Một retry/duplicate message có tạo event mới hợp lệ?
- Test suite song song có dùng chung logger name và capture list?

Dùng `event_code`, `operation_id` và `test_event_id` để xác định duplicate logic hay fan-out được phép.

### Test có message nhưng thiếu stack trace

- Có truyền `Throwable` vào đúng overload logger chưa?
- Exception bị chuyển thành `exception.getMessage()` text?
- Encoder bị cấu hình không in Throwable?
- Formatter cắt stack trace hoặc output size limit?
- Collector transform đã loại `exception.stacktrace`?
- Cause chain có bị mất khi code wrap/rethrow?

### Test security fail

- Thông tin nằm trong message, parameters, MDC, exception message hay suppressed?
- Encoder mới có tự serialize thêm headers hoặc object fields không?
- Redaction chạy ở source, appender, collector hay chỉ ở UI?
- Sink nào nhận raw event trước khi redaction?
- Dữ liệu nhạy cảm có xuất sang internal status/metrics không?

Nếu token giả lọt qua, sửa ở nguồn hoặc allowlist/redaction thích hợp; **không giảm tỷ lệ sampling để “giảm khả năng lộ”**.

## 18. Bài tập tự luyện và mở rộng

### Bài tập A — Viết thêm một unit test negative

Sửa chương trình Java 17 để một logger chỉ cho `Level.SEVERE`. Gọi success và failure trên hai orders mới. Assert rằng chỉ có failure record và không có success event ở Handler. Lưu ý khởi tạo một capture riêng để không lẫn records cũ.

**Kết quả mong muốn:** Correct count, failure có Throwable, service behavior không phụ thuộc việc INFO bị filter.

### Bài tập B — Kiểm tra suppressed exception

Trong failure path, thêm một suppressed `IOException` vào cause. Test:

- Cause vẫn `IllegalStateException`.
- `cause.getSuppressed().length == 1`.
- Suppressed type `IOException`.
- Log event giữ cùng outer Throwable.
- Không assert exact text stack trace line numbers.

### Bài tập C — Kết hợp structured encoder

Dùng encoder JSON phù hợp với backend. Test ít nhất:

```json
{
  "event_code": "checkout.failed",
  "order_id": "order-8",
  "error_code": "GATEWAY_TIMEOUT",
  "level": "ERROR"
}
```

Đây là **subset schema minh họa**, không phải output JUL. Parse JSON thành object và assert field types/name, không dùng `contains("checkout.failed")` như assertion duy nhất. Kiểm tra thêm `trace_id`/timestamp/exception theo contract.

### Bài tập D — Detect duplicate do additivity

Gắn appender vào logger con và logger cha trong một test Logback riêng, để additive=true rồi ghi một event. Quan sát hai sinks; sau đó set additive=false, chạy lại và assert routing đúng. Khôi phục config trong `finally`.

### Bài tập E — Async collector canary

Phát một synthetic event có `test_event_id` riêng. Chờ event xuất hiện trong index trong deadline 30 giây hoặc deadline phù hợp môi trường. Nếu query hỏng, phân biệt `QUERY_ERROR` với `MISSING`; nếu timeout, ghi rõ hop cuối đã xác nhận được.

Không thực hiện fault injection gây outage trên production nếu chưa được phê duyệt.

## 19. Những anti-pattern kiểm thử cần tránh

| Anti-pattern | Rủi ro | Cách cải thiện |
| --- | --- | --- |
| Chỉ tìm chữ `"ERROR"` trong console | Message INFO cũng có thể chứa chữ này | Assert enum level của event |
| Chỉ verify logger mock | Backend/encoder/filter chưa được kiểm thử | Thêm Handler/ListAppender integration |
| Snapshot cả dòng gồm timestamp | Test flaky khi đổi thời gian/locale | Assert stable contract fields |
| Test không detach appender | Event của test khác bị capture/trùng | Dùng `finally` để cleanup |
| Thay root logger toàn suite | Parallel tests can thiệp nhau | Logger riêng/test context |
| Bắt `System.out` toàn cục | Global state và async output gây race | In-memory event capture hoặc subprocess test |
| So toàn bộ stack trace | Refactor làm line/frame đổi | Assert Throwable/cause, layout properties |
| Bỏ negative assertions | Không bắt success giả, duplicate, leak | Assert absence và exact counts |
| Ngủ cố định để đợi async | CI chậm/flaky | Poll với deadline/signal/drain |
| Log secret để test redaction | Có thể rò vào test logs/CI | Dùng token giả |
| JSON substring assertions | Field có thể chỉ nằm trong message | Parse object và validate schema |
| Dùng `trace_id` làm metric label | Cardinality cao và privacy risk | Dùng bounded labels |
| Đếm sampled log lines làm error rate | Sampling/loss làm sai số | Metrics nghiệp vụ authoritative |
| Test audit bằng diagnostic logger | Không bảo đảm bền vững/compliance | Audit path/transactional contract riêng |
| Coi enqueue == persisted | Log có thể mất sau enqueue | Test từng ACK boundary |

## 20. Checklist trước khi hoàn thành dự án

- [ ] Có định nghĩa contract cho log success/failure, event code và error code?
- [ ] Unit test ghi đúng level, logger name, message/parameters và outcome?
- [ ] Failure test xác minh Throwable thật và cause chain?
- [ ] Test exact count và không có terminal log trùng?
- [ ] Có negative test cho logger level và handler/appender filter?
- [ ] Test không làm lộ canary secret trong messages/exceptions/metadata?
- [ ] Handler/appender được attach trước và detach sau test?
- [ ] Logger level, filter, parent/additivity được restore?
- [ ] Không sử dụng raw timestamp hoặc stack line numbers làm primary assertions?
- [ ] Có JDK 17 demo biên dịch và stdout theo tài liệu?
- [ ] Với SLF4J/Logback, ListAppender đọc đúng LoggingEvent và ThrowableProxy?
- [ ] Backend test không cast Log4j 2 thành Logback logger?
- [ ] JSON schema tests parse required fields/types và escaping?
- [ ] MDC context được propagate và cleanup qua thread pool/async?
- [ ] Có tests cho log routing và duplicate ingestion?
- [ ] Có async deadlines/drain và queue drop metrics khi cần?
- [ ] Có canary E2E khi cần chứng minh collector/index thật nhận dữ liệu?
- [ ] Alerting và business error rate không chỉ dựa vào số log lines?
- [ ] Không log production secrets/PII trong test fixture hoặc CI artifacts?
- [ ] Có runbook khi test bị thiếu/thừa event hoặc structured fields?
- [ ] Khi nâng framework/encoder, có regression contract tests?

**Tiêu chí hoàn thành:** Bạn chạy được `LoggingTestLab.java` với tất cả assertions đạt, diễn giải được tại sao từng assertion cần thiết, và biết cách mở rộng sang Logback/JUnit, structured JSON và end-to-end thay vì đánh đồng logger call với log delivery.

## 21. Câu hỏi tự kiểm tra

1. `assertThrows(...)` có chứng minh một event log được tạo và xuất ra sink không?
2. JUL `LogRecord.getMessage()` chứa template hay formatted message trong demo?
3. Làm sao kiểm tra `Throwable` đúng instance mà code đã rethrow?
4. Vì sao test số lượng event phải dùng exact count ở một boundary đã định?
5. Logger level filter khác Handler filter thế nào?
6. Vì sao một ListAppender PASS không chứng minh collector nhận log?
7. Khi exception bị wrap, cần kiểm tra cause/suppressed ở đâu?
8. Việc sửa text message có nên làm fail semantic logging contract test không?
9. Vì sao mock logger không đủ để kiểm tra JSON encoder?
10. Test nào phát hiện MDC của request A dính sang request B?
11. Có nên dùng `Thread.sleep(100)` làm đảm bảo cho async appender không?
12. Khi một event xuất ở appender con và cha, có thể là duplicate do additivity hay lỗi nghiệp vụ lặp?
13. Vì sao sampling 10% làm sai phép tính error rate từ số log lines?
14. Test secret canary chỉ kiểm tra `getFormattedMessage()` đã đủ chưa?
15. Khi collector query lỗi, canary checker nên trả `MISSING` hay `UNKNOWN`?
16. JSON output có `duration_ms` dạng string thì schema tests cần làm gì?
17. Một log lỗi được viết vào stdout có đồng nghĩa searchable ở index không?
18. Khi test log bị thiếu, cần phân biệt level, filter, routing, queue và collector thế nào?
19. Vì sao không nên đặt token/PII vào MDC của một test production-like?
20. Nếu audit log bắt buộc không lưu được, diagnostic logger test có chứng minh compliance không?

## Tài liệu tham khảo

- [Oracle Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — các overload, effective level và parent handlers.
- [Oracle Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — publish, filter, close/flush.
- [Oracle Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html) — message, parameters, level và thrown exception.
- [Oracle Java SE 17 — Level](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html) — INFO/WARNING/SEVERE.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — logging facade, parameterized logging và MDC.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — logging events, hierarchy và additivity.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — appender lifecycles, async logging.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — filtering levels và TurboFilter.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — test fixtures và assertions.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — cấu trúc và semantics của log records.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — log security và data minimization.
