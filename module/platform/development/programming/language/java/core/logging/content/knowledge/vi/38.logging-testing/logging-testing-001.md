# Kiểm thử logger được gọi trong Java (Testing logging)

## 1. Mục tiêu: “logger được gọi” nghĩa là gì?

Khi một unit test yêu cầu **kiểm thử logger được gọi**, câu hỏi đầu tiên là: **cần xác minh lời gọi vào Logging API, sự kiện được backend chấp nhận, hay dữ liệu đã thật sự được ghi ra đích?** Ba ý nghĩa đó khác nhau.

Ví dụ trong một service:

```java
// Đoạn minh họa, phụ thuộc logger và biến nghiệp vụ.
logger.info("order_created id={}", orderId);
```

Có ba ranh giới:

1. **Invocation** — mã ứng dụng có gọi `logger.info(...)` với template và argument mong đợi không? Có thể kiểm tra bằng Mockito/mock logger. Điều này **không chứng minh** event được ghi.
2. **Emitted event** — logger/backend, sau khi xét level/filter, có tạo và gửi event đến handler/appender thử nghiệm không? Có thể bắt `LogRecord` (JUL) hoặc `ILoggingEvent` (Logback).
3. **Output/delivery** — console, file, JSON encoder, async queue hoặc collector đã nhận dữ liệu gì? Cần integration test ở đúng điểm đích, vì một lời gọi thành công không chứng minh file/collector đã lưu bền vững.

Bài học thuộc nhóm **Testing logging** và tập trung vào cách chọn test phù hợp, viết test đáng tin, tránh phụ thuộc implementation và tránh tình huống test pass nhưng thực tế không có log.

Sau bài này, bạn có thể:
- Dùng `Mockito.verify(...)` để kiểm tra lời gọi logger theo số lần, mức, template và argument.
- Viết ví dụ Java 17+ **chạy độc lập** dùng JUL `Handler` để bắt event và phân biệt invocation với event được phát.
- Tích hợp JUnit 5 + Logback `ListAppender` để assert level/logger/message/exception/context.
- Hiểu ảnh hưởng của level/filter, SLF4J backend, parameterized logging, async logging và test chạy song song.
- Chọn khi nào nên test logging và khi nào nên test hành vi nghiệp vụ thay vì nội bộ logger.
- Kiểm thử những điều không được log, ví dụ token/password hoặc dữ liệu nhạy cảm, mà không đưa bí mật thật vào test.

## 2. Chọn đúng đối tượng kiểm thử

| Điều cần chứng minh | Cấp độ | Cách làm | Không chứng minh được |
| --- | --- | --- | --- |
| Code gọi `info("...", args)` một lần | Unit | Mockito mock/spy `org.slf4j.Logger` được inject | Backend có ghi event |
| Không gọi `warn/error` trong nhánh thành công | Unit | `verify(..., never())` hoặc event assertions | Toàn bộ hệ thống không log warn |
| Event INFO có đúng template, tham số, throwable | Unit/integration | JUL `Handler` hoặc Logback `ListAppender` | File hoặc collector đã lưu |
| File/console có JSON đúng schema | Integration | Test encoder + appender ở thư mục tạm / sink test | Tất cả request ngoài đời luôn được log |
| Async event đến đích sau worker | Integration | Chờ event có timeout, flush/drain theo backend | Đảm bảo durability khi process crash |
| Audit log bắt buộc được lưu an toàn | Integration/E2E | Đường ghi audit thật/giả lập, ack, retention và quyền | Chỉ `verify(logger)` là đủ |

**Khuyến nghị:** nếu log là hợp đồng cần thiết cho vận hành hoặc an ninh, ưu tiên test **event** và những field ổn định thay vì chỉ test một method logger cụ thể. Nếu bạn thật sự cần biết code có gọi một API wrapper theo hợp đồng hay không, mock là lựa chọn đơn giản và nhanh.

Tránh biến mọi lời gọi DEBUG thành assertion bắt buộc. Nếu test fail mỗi khi đổi nội dung log chẩn đoán nhưng hành vi nghiệp vụ vẫn đúng, test đang ràng buộc quá sâu vào implementation.

## 3. Phân biệt API, backend và cấu hình test

Trong hệ sinh thái Java thường gặp:
- **JUL**: `java.util.logging.Logger`, `LogRecord`, `Handler`, `Filter`; có sẵn trong JDK.
- **SLF4J**: `org.slf4j.Logger` là facade/API. Với Mockito mock logger SLF4J, bạn đang kiểm tra method trên interface này, **không cần backend thực để xác minh invocation**.
- **Logback Classic**: backend hay đi cùng SLF4J; cung cấp `ch.qos.logback.classic.Logger`, `ILoggingEvent`, `ListAppender`.
- **Log4j 2 Core**: backend khác, có cấu hình appender/filters và `LogEvent` riêng. Không thể ép cast Log4j Logger thành Logback Logger.
- **Spring Boot**: tích hợp cấu hình logging và `OutputCaptureExtension` cho test console; việc capture phụ thuộc backend/console configuration.

Luồng xử lý khái quát:

```text
Code nghiệp vụ
    |
    v
Logging API: logger.info(...)
    |
    +--> Mockito mock: ghi nhận method invocation, không qua backend thật
    |
    +--> Logger thật: level/filter
                    |
                    v
                 LogEvent
                    |
                    v
              Appender/Handler
                    |
                    v
              Console/File/Queue
                    |
                    v
                  Collector
```

Khi Mockito verify pass, điều chắc chắn nhất là **mock đã nhận lời gọi phù hợp**. Khi `ListAppender` thấy event, có thể khẳng định event đã tới appender này, **không** tự suy luận mọi appender khác cũng đã nhận.

### Ví dụ cùng một lời gọi nhưng kết quả khác

Giả sử code gọi `logger.info("order_created")`:
- Logger **mock**: Mockito ghi nhận lời gọi, kể cả không có backend.
- Logger thật level **WARN**: `info` được gọi từ code, nhưng event INFO có thể bị loại trước khi tạo event.
- Logger thật level **INFO**, appender threshold **WARN**: backend có thể tạo event nhưng appender này không nhận.
- Logger thật async: event có thể được enqueue nhưng chưa đến sink ở thời điểm test assert.
- Logger thật file appender lỗi I/O: lời gọi có thể trả về nhưng file không chứa event.

Vì thế dùng `verify(logger).info(...)` để chứng minh “đã ghi file” là một assertion không hợp lệ.

## 4. Dùng Mockito kiểm tra lời gọi logger

### 4.1. Thiết kế để test được: inject logger khi phù hợp

Với code cần kiểm thử chính sách phát sự kiện, có thể truyền `org.slf4j.Logger` qua constructor hoặc inject một interface nhỏ do ứng dụng sở hữu. Ví dụ **JUnit 5 + Mockito + SLF4J API**, chia thành hai file trong cùng package hoặc đặt cùng test source theo quy tắc Java:

File **`OrderService.java`**:

```java
import org.slf4j.Logger;

public final class OrderService {
    private final Logger logger;

    public OrderService(Logger logger) {
        this.logger = java.util.Objects.requireNonNull(logger);
    }

    public void createOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Invalid orderId");
        }

        // Ví dụ tối giản: ứng dụng thật còn có nghiệp vụ tạo đơn hàng.
        logger.info("order_created id={}", orderId);
    }
}
```

File **`OrderServiceTest.java`**:

```java
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

class OrderServiceTest {
    @Test
    void invokesInfoExactlyOnce() {
        Logger logger = mock(Logger.class);
        OrderService service = new OrderService(logger);

        service.createOrder("42");

        verify(logger, times(1))
                .info("order_created id={}", "42");
    }

    @Test
    void doesNotLogInvalidOrderId() {
        Logger logger = mock(Logger.class);
        OrderService service = new OrderService(logger);

        assertThrows(IllegalArgumentException.class,
                () -> service.createOrder(" "));

        verifyNoInteractions(logger);
    }
}
```

**Phụ thuộc:** `slf4j-api` và dependencies test của JUnit Jupiter/Mockito; các file này **không biên dịch bằng JDK thuần**. Dùng version được dự án quản lý để tránh xung đột. Khi dùng Mockito mock `Logger`, không nhất thiết cần Logback chỉ để gọi `verify`, nhưng những phần khác của ứng dụng có thể yêu cầu provider.

Giải thích:
1. `mock(Logger.class)` tạo một mock của interface SLF4J, không ghi console/file.
2. `service.createOrder("42")` thực thi code được test.
3. `verify(logger, times(1)).info("order_created id={}", "42")` xác minh **chính xác một invocation**, bao gồm template và argument ở call site.
4. `verifyNoInteractions(logger)` có ý nghĩa cho nhánh input không hợp lệ bởi service được thiết kế không động chạm logger trong nhánh đó.
5. Nếu dùng `verify(logger).info(...)` mà không chỉ định mode, Mockito mặc định kiểm tra một lần. `times(n)` làm số lần mong đợi rõ ràng.

**Không bắt buộc phải inject `Logger` cho mọi class.** Nếu class chỉ dùng logger `private static final` theo convention, thay đổi thiết kế solely để mock một lời gọi DEBUG thường không đáng. Cân nhắc bắt event ở backend test hoặc kiểm tra hành vi nghiệp vụ.

### 4.2. `verify`, `never`, `atLeastOnce` và `ArgumentCaptor`

Các chế độ thường dùng:

```java
// Các đoạn sau giả định "logger" là mock SLF4J Logger.
verify(logger, times(1)).info("order_created id={}", "42");
verify(logger, never()).warn("unsafe_input");
verify(logger, atLeastOnce()).info(anyString(), any());
```

**Lưu ý overload:** SLF4J có nhiều overload (`info(String)`, `info(String,Object)`, `info(String,Object,Object)`, varargs). Test phải verify **đúng overload được production code gọi**. Một lời gọi hai argument được hiểu khác với một mảng arguments hoặc fluent builder.

`ArgumentCaptor` hữu ích khi argument có cấu trúc hoặc khi chỉ một vài field cần kiểm tra:

```java
import org.mockito.ArgumentCaptor;

ArgumentCaptor<String> template =
        ArgumentCaptor.forClass(String.class);

// Minh họa với logger mock, sau khi code đã phát một info(String).
verify(logger).info(template.capture());
org.junit.jupiter.api.Assertions.assertTrue(
        template.getValue().startsWith("event="));
```

Đây là **đoạn tích hợp riêng**, chỉ đúng khi production gọi overload `info(String)`. Đừng copy nó vào code đã dùng `info(String,Object)` rồi mong captor bắt được call khác chữ ký.

Với `verifyNoMoreInteractions`, tránh lạm dụng vì một câu log chẩn đoán mới sẽ làm test fail dù hợp đồng quan trọng vẫn đúng. Dùng khi mục tiêu là ràng buộc chính xác mọi tương tác, không phải mặc định.

### 4.3. `isInfoEnabled()` và mock mặc định

Nếu code production có guard:

```java
if (logger.isInfoEnabled()) {
    logger.info("details={}", buildSummary());
}
```

Mockito mock trả mặc định `false` cho boolean khi chưa stub. Do đó lời gọi `info` **không xảy ra**, dù service đúng với điều kiện giả định. Nếu muốn test nhánh enabled, stub:

```java
when(logger.isInfoEnabled()).thenReturn(true);
```

Đối với SLF4J 2.x fluent API, `logger.atInfo()` trả về một `LoggingEventBuilder`. Mock thường không tự cung cấp builder có hành vi thật; cần stub builder/chain hoặc chuyển sang integration test bắt event. **Đừng verify `logger.info(...)` nếu production dùng `logger.atInfo().log(...)`:** chúng là hai đường gọi API khác nhau.

### 4.4. Vì sao không nên mock `LoggerFactory` bừa bãi?

Mẫu thường gặp:

```java
private static final Logger LOG =
        LoggerFactory.getLogger(OrderService.class);
```

Logger được khởi tạo tại thời điểm nạp class; test dùng mock static `LoggerFactory` **sau khi class đã khởi tạo** thường không thể thay giá trị của field. Cố sửa field private static final bằng reflection hoặc thay root logger có thể gây flaky test, ảnh hưởng suite song song.

Có ba lựa chọn hợp lý:
- Nếu log là hợp đồng nghiệp vụ quan trọng, inject một logging/audit facade do ứng dụng sở hữu.
- Nếu muốn xác nhận event thực, dùng appender/handler tại logger thật mà class đang dùng.
- Nếu log không thiết yếu, test behavior của service và bỏ assertion gọi logger.

## 5. Ví dụ Java 17+ độc lập: bắt LogRecord bằng JUL

Ví dụ này chỉ dùng JDK, không cần Mockito/JUnit/SLF4J. Nó chứng minh **lời gọi trong code** và **sự kiện thực sự đến handler** là hai việc khác nhau.

Tạo file **`LoggerInvocationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggerInvocationDemo {
    static final class MemoryHandler extends Handler {
        private final List<LogRecord> events = new ArrayList<>();

        @Override
        public synchronized void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record);
            }
        }

        @Override public void flush() {}
        @Override public void close() {}

        synchronized List<LogRecord> snapshot() {
            return List.copyOf(events);
        }
    }

    static void createOrder(Logger logger, String orderId) {
        logger.log(Level.INFO, "order_created id={0}", orderId);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        MemoryHandler capture = new MemoryHandler();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        try {
            createOrder(logger, "42");
            List<LogRecord> observed = capture.snapshot();
            if (observed.size() != 1) {
                throw new AssertionError(
                        "Expected one emitted INFO record");
            }

            LogRecord event = observed.get(0);
            if (event.getLevel() != Level.INFO
                    || !"order_created id={0}".equals(
                            event.getMessage())
                    || event.getParameters() == null
                    || event.getParameters().length != 1
                    || !"42".equals(event.getParameters()[0])) {
                throw new AssertionError(
                        "Unexpected record fields");
            }

            System.out.println(
                    "captured_info_events=" + observed.size());
            System.out.println("level=" + event.getLevel());
            System.out.println("template=" + event.getMessage());
            System.out.println(
                    "parameter=" + event.getParameters()[0]);

            logger.setLevel(Level.WARNING);
            createOrder(logger, "43");
            if (capture.snapshot().size() != 1) {
                throw new AssertionError(
                        "INFO must be filtered by logger level");
            }
            System.out.println(
                    "after_info_disabled=" + capture.snapshot().size());
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LoggerInvocationDemo.java
java LoggerInvocationDemo
```

**Standard output chính xác:**

```text
captured_info_events=1
level=INFO
template=order_created id={0}
parameter=42
after_info_disabled=1
```

### Ý nghĩa kết quả

1. `createOrder(logger, "42")` gọi `Logger.log(Level.INFO, String, Object)`. Với level INFO và handler ALL, một `LogRecord` đến `MemoryHandler`.
2. `LogRecord.getMessage()` chứa **template** `order_created id={0}`, không phải text đã được `Formatter` thay `{0}`. Parameter `42` nằm ở `getParameters()[0]`; test xác minh riêng cả hai.
3. `logger.setLevel(Level.WARNING)` sau đó tắt INFO. `createOrder(logger, "43")` vẫn **gọi method log**, nhưng logger loại event, nên handler vẫn chỉ có **một** record.
4. Vì `setUseParentHandlers(false)`, root ConsoleHandler của JUL không in thêm dòng vào stderr.
5. `snapshot()` trả bản sao danh sách để test không làm hỏng collection nội bộ; đồng bộ method giúp thao tác thêm/lấy bản sao an toàn khi nhiều thread dùng chung handler. Test này thực hiện đồng bộ, không có bất đồng bộ appender.
6. `finally` tháo handler để tránh lưu trạng thái khi chạy trong suite; logger được tạo riêng bằng `getAnonymousLogger()` nên không làm thay đổi logger có tên dùng bởi ứng dụng khác.

**Đây là kiểm thử event nhận bởi handler, không phải Mockito verify lời gọi.** Nó gần với hành vi runtime hơn nhưng vẫn **không chứng minh file/collector đã nhận log**. Khi có filter tại handler, level hoặc formatter khác, cần kiểm tra ngữ nghĩa ở chính điểm mình muốn bảo đảm.

## 6. JUL trong unit test thực tế

Để test một class dùng JUL có logger thật, có thể dùng handler in-memory được gắn vào **đúng logger của class** trong phạm vi test.

Quy trình:
1. Lấy logger theo tên hoặc qua cách inject mà ứng dụng hỗ trợ.
2. Lưu `logger.getLevel()`, `logger.getUseParentHandlers()` và những state sẽ thay đổi.
3. Gắn `Handler` test với `Level.ALL`, đặt logger level đủ cho event cần kiểm tra.
4. Gọi hành động nghiệp vụ, thu `LogRecord`.
5. Assert level, logger name, template, parameters, `getThrown()` và message key quan trọng.
6. Trong `finally`, remove handler, restore level/parent state, close handler.

Nếu logger có `Filter` đang hoạt động hoặc handler khác, một thay đổi level có thể chưa đủ để event đến test handler. Chỉ thay filter khi thật sự cần và nhớ khôi phục. Tránh `LogManager.reset()` trong mỗi test vì thao tác đó ảnh hưởng **toàn JVM**, gây race và làm mất handler của test khác.

### Kiểm tra ngoại lệ

Với JUL:

```java
// Đoạn tích hợp bên trong method đang xử lý exception.
try {
    riskyOperation();
} catch (RuntimeException ex) {
    logger.log(Level.SEVERE, "order_processing_failed", ex);
    throw ex;
}
```

`LogRecord.getThrown()` cho phép assert loại exception, trong khi formatter có thể thay đổi cách xuất stack trace. Ưu tiên assert loại lỗi/field quan trọng thay vì so nguyên văn stack trace gồm vị trí source line.

## 7. Logback ListAppender: kiểm thử sự kiện thực

Với **SLF4J + Logback Classic**, có thể dùng `ch.qos.logback.core.read.ListAppender<ILoggingEvent>` để thu event trước khi formatter console biến chúng thành text. Cách này phù hợp khi code production có logger `private static final` và không muốn mock private field.

Ví dụ **JUnit 5 + SLF4J + Logback Classic**:

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LogbackEventTest {
    @Test
    void emitsAnInfoEvent() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                "test.order.logging");

        Level oldLevel = logger.getLevel();
        boolean oldAdditivity = logger.isAdditive();

        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.start();
        logger.setLevel(Level.INFO);
        logger.setAdditive(false);
        logger.addAppender(capture);

        try {
            logger.info("order_created id={}", "42");

            assertEquals(1, capture.list.size());
            ILoggingEvent event = capture.list.get(0);

            assertEquals(Level.INFO, event.getLevel());
            assertEquals("test.order.logging",
                         event.getLoggerName());
            assertEquals("order_created id=42",
                         event.getFormattedMessage());
        } finally {
            logger.detachAppender(capture);
            logger.setLevel(oldLevel);
            logger.setAdditive(oldAdditivity);
            capture.stop();
        }
    }
}
```

Ví dụ ở trên thực hiện **lời gọi trực tiếp vào logger thật** để cô lập minh họa. Trong test nghiệp vụ, thay dòng `logger.info(...)` bằng hành động có thể kích hoạt log, và gắn `ListAppender` vào logger mà class ứng dụng thực sự sử dụng.

Ý nghĩa:
- `LoggerFactory.getLogger(...)` trả SLF4J logger; ép sang `ch.qos.logback.classic.Logger` chỉ đúng nếu **provider hiện tại là Logback Classic**.
- `ListAppender` ghi lại `ILoggingEvent`, có thể kiểm tra `getLevel()`, `getFormattedMessage()`, `getLoggerName()` và với ngoại lệ là `getThrowableProxy()`.
- `setAdditive(false)` tránh event cũng đi lên parent appender, phù hợp test cục bộ; cần restore để không ảnh hưởng test khác.
- `capture.start()` được gọi trước khi gắn; `detachAppender`/`stop()` trong `finally` giúp tránh giữ bộ nhớ và event của test tiếp theo.
- `capture.list` không nên đọc khi async worker còn ghi hoặc nhiều test dùng cùng logger; ví dụ này dùng logging đồng bộ.

**Đừng xem cast thất bại là lỗi của Mockito.** Nó chứng tỏ runtime provider không phải Logback hoặc classpath không khớp. Nếu backend là Log4j 2, dùng appender/test utilities của Log4j 2 thay vì `ListAppender` Logback.

### Event chưa chắc đã được format như bạn nghĩ

`ILoggingEvent.getMessage()` thường là template (ví dụ `order_created id={}`), còn `getFormattedMessage()` trả chuỗi đã điền argument. Với JUL, `LogRecord.getMessage()` có thể chứa template `{0}` và `getParameters()` chứa parameters. Bởi vậy cùng “kiểm thử nội dung log” nhưng API kiểm tra khác nhau.

Đối với structured logging (SLF4J 2.x key/value, Log4j 2 JSON layout, MDC), cần xác minh từng field/context tại event hoặc JSON output thực. Chỉ khớp một substring không chứng minh đầy đủ schema hoặc privacy.

## 8. Spring Boot: kiểm thử text ở console

Nếu mục tiêu là “console output của ứng dụng có chứa thông báo mong đợi”, Spring Boot hỗ trợ `OutputCaptureExtension` của JUnit 5 để thu `System.out`/`System.err`.

Ví dụ **đoạn tích hợp** cần Spring Boot test, JUnit Jupiter, AssertJ và một console appender phù hợp:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class ConsoleLoggingTest {
    @Test
    void containsWarning(CapturedOutput output) {
        // Chỉ minh họa khi backend gửi WARN ra console.
        org.slf4j.LoggerFactory.getLogger("test.console")
                .warn("order_retry_scheduled");

        assertThat(output).contains("order_retry_scheduled");
    }
}
```

Cách này phụ thuộc việc logger được cấu hình ra console với level phù hợp. Nó **không** xác minh số lần gọi logger trong code và có thể dễ bị nhiễu nếu các test khác cũng ghi vào stdout/stderr trong cùng JVM.

Spring Boot tài liệu nêu rằng capture JUL/Log4j 2 có thể cần cấu hình bổ sung vì handler/appender giữ tham chiếu stream khác với stream extension tạm thay. **Không tùy tiện reset global LogManager trong test parallel** chỉ để capture được stdout; ưu tiên handler/appender cục bộ hoặc môi trường test/fork được cô lập.

Nếu chỉ cần xác minh event ở mức logger, `ListAppender`/memory handler thường rõ và ổn định hơn capture console text.

## 9. Những assertion nào có giá trị?

### 9.1. Khi kiểm thử lời gọi API

Với mock logger, assertion có thể tập trung vào:
- Method log có đúng level API (`debug`, `info`, `warn`, `error`) không?
- Template/event code có đúng với hợp đồng không?
- Argument quan trọng (ID, error code, enum outcome) có được truyền đúng không?
- Một nhánh chỉ gọi một lần hay không gọi?
- Lời gọi có xảy ra **sau** hành động nghiệp vụ thành công hoặc ở nhánh lỗi không?

Ví dụ test hữu ích: khi validation thất bại, ứng dụng phải gọi logger WARN với error code `INVALID_ORDER`, nhưng không gọi `order_created`.

Hạn chế:
- Mockito chỉ xác nhận đúng object mock đã nhận lời gọi.
- Tính đúng của template formatting/JSON/schema không được kiểm chứng.
- Logger/provider thực có thể tắt level hoặc filter event.
- Nếu code chỉ ghi một chuỗi “success” nhưng không thực hiện nghiệp vụ, test mock vẫn có thể pass. **Luôn kết hợp với assertion nghiệp vụ.**

### 9.2. Khi kiểm thử event

Với `LogRecord`/`ILoggingEvent`:
- `level`, `loggerName`, `message template`, formatted message cần thiết.
- Parameters/key-value, error code, `requestId`/trace ID theo schema.
- `Throwable`/`ThrowableProxy` ở event lỗi (thay vì chỉ message text).
- Số lượng event trong phạm vi một hành động đã cô lập.
- Không xuất hiện secret/PII/raw payload không được phép.
- Sự kiện có thật sự đi qua filter/threshold trong cấu hình test không?

Đừng assert toàn bộ chuỗi đã format có timestamp, thread ID, line number, location hoặc stack trace text thay đổi theo JVM/build. Thời gian và ID ngẫu nhiên nên kiểm tra theo pattern/type/range thay vì một giá trị cứng.

### 9.3. Khi kiểm thử file/collector

Nếu yêu cầu là “ghi một event JSON ra file”:
1. Tạo thư mục tạm dành riêng cho test, thiết lập appender và logger ở trạng thái có thể kiểm soát.
2. Gọi hành động nghiệp vụ.
3. Chờ event được ghi và flush/drain nếu async; dùng timeout theo contract.
4. Parse JSON theo schema, kiểm tra field cần thiết và secret giả không xuất hiện.
5. Close appender, xóa temp file theo lifecycle và restore logger config.
6. Với collector, dùng sink test thay vì endpoint production.

Đừng dùng `verify(logger).info(...)` rồi kết luận file/collector đã nhận event, và cũng không dùng việc file tồn tại làm bằng chứng mọi event được ghi.

## 10. Lưu ý về logger level và filter

Logger có thể được **gọi** mà không phát event:

```text
Code: logger.info("ready")
  |
  +--> Mockito mock: invocation được ghi nhận
  |
  +--> Real logger level=ERROR: INFO bị loại
  |
  +--> Real logger level=INFO: tạo event
                                 |
                                 +--> appender filter DENY: sink không nhận
                                 |
                                 +--> appender accept: sink nhận
```

Với JUL, cả `Logger.setLevel` và `Handler.setLevel` đều cần xét. Với Logback, logger level, turbo filter và appender filter là các tầng khác nhau. Với Log4j 2, filter có thể đặt ở nhiều tầng.

Một test muốn chứng minh **“đã gọi DEBUG khi feature flag bật”** nên dùng mock nếu log call là hợp đồng. Một test muốn chứng minh **“DEBUG không xuất hiện ở production”** phải dùng backend/config thực và assert event/output, không thể chỉ verify code không gọi `debug` vì ứng dụng có thể gọi và backend loại.

Tránh để test phụ thuộc level của root logger trên máy developer/CI. Đặt `logback-test.xml` hoặc config test phù hợp ở `src/test/resources` và kiểm tra rằng test runtime classpath thực sự nạp file đó. Với JUL, dùng logger cục bộ như mục 5 nếu không cần toàn bộ `LogManager`.

## 11. Async logging, parallel tests và điều kiện chờ

### 11.1. Vì sao test thỉnh thoảng fail?

Async logger/appender thường đưa event vào queue, rồi worker mới ghi. Code có thể chạy:

```java
service.process();
assertEquals(1, capturedEvents.size());
```

và fail không ổn định vì worker **chưa chuyển event vào appender test**. Hoặc nếu appender chọn drop khi queue đầy, event có thể thật sự mất.

Cách đúng:
- Với **mock logger**, `verify` diễn ra sau khi code gọi method; nếu code chính cũng async (executor/future), phải chờ công việc kích hoạt log hoàn tất.
- Với **real async appender**, dùng `CountDownLatch`, test appender có tín hiệu, poll với deadline, hoặc backend-specific flush/drain theo API. Chờ event đến đúng sink, không ngủ một khoảng tùy ý.
- Đặt timeout hữu hạn và thông báo lỗi rõ; không chờ vô hạn khiến CI treo.
- Phân biệt “chưa đến” với “đã drop” khi queue đầy hoặc event bị filter.
- Nếu test yêu cầu kiểm chứng shutdown/flush, đó là integration test riêng, không lẫn vào một unit test mock.

**Không dùng `Thread.sleep(100)` rồi coi đó là bảo đảm event đã ghi**. Trên máy CI chậm, thời gian queue hoặc scheduler có thể dài hơn.

### 11.2. Global logger state có thể làm test nhiễm nhau

Các thao tác sau thường ảnh hưởng nhiều test trong cùng JVM:
- Đổi root level hoặc gắn appender/handler vào root logger.
- Đổi `System.out`/`System.err`, `System.setProperty` cho logging backend.
- Gọi `LogManager.reset()` hoặc reconfigure một LoggerContext dùng chung.
- Gắn `ListAppender` vào logger tên cố định trong nhiều test chạy parallel.
- Đặt MDC/ThreadContext rồi quên clear/restore.

Biện pháp:
1. Dùng logger/test context riêng khi có thể.
2. Nếu sửa level/filter, ghi nhớ giá trị cũ và hoàn nguyên trong `finally`.
3. Detach/stop appender, remove/close handler ngay sau test.
4. Khôi phục MDC cũ hoặc clear key thuộc test; chú ý context propagation trong executor/virtual thread.
5. Với integration test cần thay global config, cân nhắc test fork/process riêng hoặc điều phối không chạy song song.
6. Không assert tổng số log của framework/SDK trong khi thread khác vẫn có thể ghi.

**ListAppender có danh sách event**, không phải cơ chế an toàn mặc định cho nhiều worker ghi đồng thời. Khi async hoặc parallel, phải có collection/thread-safety, snapshot và deadline rõ trước khi assert.

## 12. Kiểm thử exception và nhánh lỗi

Một logger được gọi trong catch block không chứng minh code đã xử lý exception đúng. Nên test cả:
- Exception nghiệp vụ được throw/return đúng theo contract.
- WARN/ERROR có code và ID hợp lệ.
- Throwable được truyền vào logging API đúng overload, không chỉ nối `ex.getMessage()` rồi làm mất stack trace.
- Không có log “success” giả ở nhánh lỗi.
- Không lộ secret trong exception message, argument, MDC hoặc formatted output.

Ví dụ concept cho SLF4J:

```java
// Đoạn minh họa tích hợp trong service.
try {
    saveOrder(order);
} catch (RuntimeException error) {
    LOG.error("order_save_failed orderId={}", orderId, error);
    throw error;
}
```

Lưu ý overload của SLF4J với argument/Throwable: cần dùng đúng API/version; `error` được xử lý như throwable bởi SLF4J trong overload phù hợp, còn `orderId` là argument. Khi mock verify, chọn đúng method signature và matcher; ở integration test kiểm tra `ILoggingEvent.getThrowableProxy()` thay vì bắt buộc so toàn bộ stack trace.

Nếu một thư viện log thay bạn, ví dụ HTTP filter, job framework hoặc transaction manager, test **event ở đúng logger/backend**; đừng verify mock logger mà ứng dụng không bao giờ dùng.

## 13. Test riêng tư và thông tin không được log

Testing logging cũng cần **negative assertions** về dữ liệu:
- Không ghi password, token, Authorization header, Cookie, toàn bộ request/response body hoặc thông tin thanh toán.
- Không ghi raw user input chứa CR/LF làm giả dòng log.
- Không đưa object DTO đầy field nhạy cảm vào `toString()`.
- Không sao chép toàn bộ MDC/headers khi chưa có allowlist.
- Không log ID người dùng/email trừ khi có mục đích và policy phù hợp.

Test với **canary giả**, không dùng credential thật:
1. Tạo payload giả có `token=TEST_ONLY_SECRET`.
2. Chạy đường code thành công/lỗi.
3. Bắt event hoặc formatted output sau encoder.
4. Assert canary **không xuất hiện**, field định danh chỉ theo schema được duyệt.
5. Nếu có nhiều appender hoặc collector, kiểm tra **tất cả tuyến nhận** tương ứng.

Chỉ kiểm tra `verify(logger).info("...", safeField)` là chưa đủ: một logging interceptor khác vẫn có thể tự ghi request body; hoặc appender khác có pattern `%X` đưa MDC nhạy cảm ra file. Cần integration test đến điểm cuối của pipeline khi bảo mật/riêng tư là mục tiêu.

## 14. Chọn giải pháp theo tình huống

| Tình huống | Cách kiểm thử phù hợp nhất | Ghi chú |
| --- | --- | --- |
| Service được inject logger và cần kiểm tra gọi INFO một lần | Mockito `verify` | Nhanh; chỉ xác nhận invocation |
| Class dùng `private static final Logger` | Logback ListAppender/JUL Handler | Tránh reflection sửa field static final |
| Muốn test logger INFO bị lọc ở WARN | Event capture với config level thật | Mock không mô phỏng backend |
| Muốn test template, MDC, throwable | Capture `ILoggingEvent`/`LogRecord` | Kiểm tra field, không phụ thuộc console |
| Muốn test JSON và masking | Encoder/appender test | Parse JSON; test canary |
| Muốn test đúng text console ở Spring Boot | `OutputCaptureExtension` | Chỉ khi có console backend đúng |
| Muốn test async delivery/flush | Integration test sink và deadline | Không chỉ `verify` |
| Muốn test nghiệp vụ tạo đơn hàng | Assert kết quả/DB/invocation collaborator | Logging là assertion bổ sung nếu cần |
| Muốn chứng minh audit bền vững | Test audit pipeline/transaction | Logger call là điều kiện không đủ |

Nhìn chung nên có **ít unit test gắn chặt với log text**, thay vào đó chỉ test những sự kiện bắt buộc cho vận hành/safety/compliance; các log chẩn đoán thông thường có thể được xem như implementation detail. Với hệ thống cần cấu trúc log ổn định, duy trì schema và integration tests thay vì chỉ verify số lời gọi.

## 15. Những lỗi phổ biến và cách khắc phục

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `verify(logger).info(...)` và kết luận file đã ghi | Mock không đi qua backend | Test appender/file/collector riêng |
| Gắn handler nhưng logger level là WARN, event INFO bị bỏ | Không có record để bắt | Đặt level test rõ hoặc test behavior lọc |
| Dùng mock Logger nhưng code guard `isInfoEnabled()` | Mock boolean mặc định false | Stub guard theo nhánh cần test |
| Verify overload `info(String)` trong khi code dùng `info(String,Object)` | Mockito khớp chữ ký khác | Verify template và argument đúng overload |
| Mock `LoggerFactory` sau khi static logger đã khởi tạo | Không thay field đã cache | Inject abstraction hoặc bắt event thật |
| Đổi root logger trong test parallel | Test khác bị nhiễm | Logger riêng/context riêng và cleanup |
| Không detach/stop ListAppender | Memory leak, bắt event test sau | Cleanup trong `finally` |
| Đọc `capture.list` trước async completion | Race/flaky | Wait theo event + timeout |
| So timestamp/thread/stack trace toàn chuỗi | Kết quả biến động theo môi trường | Assert field ổn định |
| Assert mọi DEBUG phải xuất hiện | Log bị level/filter tắt hợp lệ | Xác định rõ test invocation hay emission |
| `verifyNoMoreInteractions` quá rộng | Log mới làm fail test không cần thiết | Chỉ ràng buộc tương tác quan trọng |
| Dùng console capture cho Log4j/JUL nhưng không thấy output | Stream bị handler/appender giữ trước capture | Cấu hình backend hoặc dùng event capture |
| Test pass vì chỉ gọi `logger.info` thay vì hành động service | Không kiểm tra đường nghiệp vụ | Gọi code under test thật |
| Lỗi mock provider không khớp Logback cast | Backend thực không phải Logback | Dùng backend test đúng provider |
| Chỉ kiểm tra message, bỏ qua dữ liệu nhạy cảm ở MDC | Có thể rò qua layout/pipeline | Test mọi event field và output |

## 16. Checklist cho test đáng tin

- [ ] Xác định rõ mục tiêu: **API invocation**, emitted event hay output/delivery.
- [ ] Dùng đúng API: JUL, SLF4J, Logback hay Log4j 2; kiểm tra backend/version.
- [ ] Với Mockito, verify đúng overload, template, arguments, số lần và guard.
- [ ] Với handler/appender, thiết lập level/filter chính xác và bắt event từ **logger của code cần test**.
- [ ] Có assertion nghiệp vụ; không test log thay cho kết quả xử lý chính.
- [ ] Với exception, kiểm tra error code và throwable riêng, tránh full stack trace string.
- [ ] Với MDC, chỉ assert field được duyệt; cleanup context.
- [ ] Test privacy/log injection bằng dữ liệu giả và ở đúng điểm output.
- [ ] Với async, có deadline và signal đến sink; không dùng `Thread.sleep` cố định.
- [ ] Khôi phục level, additivity, handler/appender, system/global state và file tạm.
- [ ] Không sửa shared root logger trong suite parallel khi không được cô lập.
- [ ] Chạy ở CI với test runtime logging config giống thiết kế, không phụ thuộc IDE.

## 17. Bài tập thực hành

1. Chạy `LoggerInvocationDemo`. Giải thích vì sao method `createOrder` được gọi hai lần nhưng `MemoryHandler` chỉ thu một event khi INFO bị tắt ở lần thứ hai.
2. Trong `OrderServiceTest`, thay `times(1)` bằng `times(2)` và xem test fail. Sau đó gọi `createOrder` hai lần để quan sát khác biệt.
3. Thêm nhánh `isInfoEnabled()` vào service dùng mock logger, chạy test khi chưa stub và sau khi `when(logger.isInfoEnabled()).thenReturn(true)`.
4. Với Logback, gắn `ListAppender` vào logger của service thật. Thử INFO và WARN, xác minh `getLevel` và `getFormattedMessage`.
5. Thiết lập logger thật ở WARN rồi gọi INFO. Viết hai test: một test verify invocation bằng mock, một test assert không có emitted INFO event.
6. Trong một nhánh lỗi, phát `LOG.error(..., throwable)`, assert có `ThrowableProxy` và error code; không so full stack trace.
7. Với async appender, viết test sink dùng CountDownLatch/timeout; so với test dùng sleep cố định và giải thích vì sao sleep flaky.
8. Tạo payload có `TEST_ONLY_SECRET` và input có newline, xác minh logger event/output không ghi raw data này.
9. Chạy hai test parallel cùng tên logger để thấy nguy cơ state leakage; sửa bằng logger riêng, cleanup hoặc test JVM cô lập.
10. Tự phân loại năm yêu cầu test logging thành invocation, emission và delivery. Giải thích vì sao một loại test không tự chứng minh loại còn lại.

## 18. Ghi nhớ

- **“Logger được gọi”** có thể chỉ là lời gọi API; mock verification không đồng nghĩa event đã được tạo hoặc ghi đến sink.
- Với Mockito, `verify(logger)` kiểm tra đúng method/arguments/invocation count, thuận tiện nếu logger hoặc logging facade được inject.
- Với JUL `Handler` và Logback `ListAppender`, kiểm tra **emitted events** và level/template/parameters/throwable thật.
- Logger level/filter, appender threshold, async queue và lỗi I/O có thể khiến cùng một lời gọi logger không tạo ra output như dự đoán.
- Test ổn định cần cô lập logger, khôi phục state, chờ async theo điều kiện có timeout, không assert timestamp/stack trace bất định.
- Không biến mọi DEBUG thành test brittle; ưu tiên assertion nghiệp vụ và các log event thực sự là hợp đồng vận hành, an ninh hoặc audit.

### Tài liệu tham khảo

- Mockito 5 — `verify`, `times`, `never`, `ArgumentCaptor`: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html
- JUnit 5 — *User Guide*: https://junit.org/junit5/docs/current/user-guide/
- SLF4J — *User Manual*: https://www.slf4j.org/manual.html
- Logback — *Manual* và appender API: https://logback.qos.ch/manual/appenders.html
- Oracle Java 17 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 — `java.util.logging.LogRecord`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
- Spring Boot — *Test Utilities / OutputCaptureExtension*: https://docs.spring.io/spring-boot/reference/testing/test-utilities.html
