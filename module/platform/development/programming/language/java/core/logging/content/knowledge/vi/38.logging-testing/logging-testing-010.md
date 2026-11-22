# Tránh test quá phụ thuộc format khi kiểm thử logging trong Java

## 1. Vấn đề: test pass hay fail vì cách in log, không phải vì hành vi

Khi kiểm thử logging, một cách làm hấp dẫn là thu stdout hoặc nội dung file rồi so sánh **nguyên một dòng log** với chuỗi mong đợi:

```text
2026-01-01 10:00:00.123 INFO [main] example.OrderService - Cancel rejected: orderId=O-42
```

Tuy nhiên, chuỗi trên chứa nhiều thành phần *trình bày*: timestamp, múi giờ, tên thread, logger name, khoảng trắng, dấu phân cách, format message. Chỉ cần đổi pattern Logback, đổi locale/timezone, chạy qua thread pool, thay encoder JSON hoặc cập nhật thư viện là test có thể thất bại mặc dù **sự kiện nghiệp vụ và quyết định logging không đổi**.

Ngược lại, một test chỉ kiểm tra chuỗi chứa `"ERROR"` cũng có thể pass sai khi code phát một message khác có chữ ERROR, dù **level thực tế là INFO** hoặc Throwable đã bị mất.

**Mục tiêu:** kiểm thử **hợp đồng quan sát được** của ứng dụng thay vì đóng băng toàn bộ cách render log. Với hầu hết unit/integration test nghiệp vụ, cần hỏi:

- Sự kiện có được phát không, và đúng **số lần** không?
- Event có **level** đúng không?
- Event gắn với **logger/component** phù hợp không?
- **Action, outcome, reasonCode, resourceId và correlation ID** có đúng không?
- Khi cần chẩn đoán lỗi kỹ thuật, **Throwable/cause** có được đính kèm không?
- Event nhạy cảm có bị **loại hoặc che dữ liệu** đúng chính sách không?
- Nếu logger/filter/tầng delivery bị chặn, điều gì thực sự đến được **sink**?

Chỉ nên kiểm tra **format chính xác** khi format chính là một phần của yêu cầu, ví dụ contract JSON log ingest, escaping chống log injection, tên trường của parser hoặc format audit được khách hàng/hệ thống downstream cam kết.

## 2. Tách ba lớp: sự kiện, trình bày và vận chuyển

Một đường đi logging thông thường:

```text
Business code
    |
    | logger.info("action={} outcome={}", action, outcome)
    v
[SEMANTIC EVENT]
  level, loggerName, template, arguments,
  MDC, marker, throwable, timestamp...
    |
    v
[ENCODER / FORMATTER]
  PatternLayout / JSON encoder / custom formatter
    |
    v
[DELIVERY]
  console, file, async queue, agent, network collector
    |
    v
[OBSERVED OUTPUT]
  text line, JSON object, indexed log, alert
```

Các lớp khác nhau nên có bài test phù hợp:

| Lớp | Câu hỏi kiểm thử | Cách quan sát ưu tiên |
| --- | --- | --- |
| **Event semantics** | Có log đúng level, message template, tham số và context? | Capture `ILoggingEvent` hoặc `LogRecord` trong bộ nhớ |
| **Logging policy/filter** | Event nào được phép tới một appender? | Capture appender sau filter, kiểm tra tập event |
| **Encoder** | Output có field JSON, escaping, timestamp đúng contract? | Cấp event cố định cho encoder, parse output theo cấu trúc |
| **Transport/delivery** | Log đến file/collector, drain sau async, xử lý lỗi ra sao? | Integration test tại sink thực, timeout/ack/fault injection |
| **Audit/business result** | Trạng thái nghiệp vụ và audit event có khớp? | So database/result với event, không chỉ mock logger |

Nếu yêu cầu là “thao tác bị từ chối phải có reasonCode”, unit test không nên thất bại chỉ vì đổi pattern từ `%d %-5level %msg%n` sang JSON. Nhưng nếu hệ thống ingest buộc trường JSON tên `reasonCode` kiểu string, đó **là hợp đồng format** và cần test riêng.

## 3. Những thành phần khiến so sánh nguyên dòng dễ giòn

| Thành phần | Vì sao thay đổi dù ứng dụng đúng | Khuyến nghị |
| --- | --- | --- |
| Timestamp và độ chính xác | Đồng hồ, timezone, kiểu format, độ phân giải | Kiểm tra có timestamp hợp lệ hoặc inject `Clock`; không hardcode “giờ hiện tại” |
| Thread name | JUnit runner, executor, virtual threads, thread pool | Chỉ assert thread khi yêu cầu; không phụ thuộc `main` |
| Logger name | Refactor package/class, wrapper logger | Assert namespace/loại event nếu đó là contract |
| Level text/padding | `INFO`, `INFO `, alignment, color ANSI | Assert enum level của event |
| Whitespace/line endings | Linux `\n`, Windows `\r\n`, layout thay đổi | Parse dữ liệu hoặc chuẩn hóa khi format thực sự cần |
| Throwable/stack trace | Tên class, số dòng, suppressed/cause, JDK | Assert exception type/cause, không so toàn bộ trace |
| Ordering | Async appender, nhiều thread, batching | Đối chiếu theo ID/set; chỉ kiểm tra thứ tự có bảo đảm |
| Localized message | Locale và message bundle | Assert reasonCode hoặc loại lỗi |
| MDC fields | Context propagation, key thêm/bớt | Assert field bắt buộc, không so mọi field |
| JSON field order | Serializer thường không cam kết thứ tự key | Parse JSON, so các field, không so chuỗi JSON |
| Escaping | Encoder đổi thứ tự/kiểu escape tương đương | Parse output rồi so ý nghĩa; test escaping ở cấp encoder |
| Log pattern | Thêm `traceId`, `spanId`, đổi layout | Test semantic event độc lập pattern |

**Test giòn** là test thường xuyên fail vì thay đổi không thuộc hành vi cần bảo vệ. **Test quá lỏng** lại pass khi log thiếu dữ liệu quan trọng. Giải pháp không phải bỏ hết assertion, mà là chọn **hợp đồng đúng tầng**.

## 4. Khi nào nên assert chính xác, khi nào chỉ assert semantics?

Một quy tắc thực dụng:

- **Nên assert chính xác** các mã có hợp đồng ổn định: `action=ORDER_CANCEL`, `outcome=REJECTED`, `reasonCode=ORDER_ALREADY_SHIPPED`, enum level, số event, ID cần có.
- **Không nên assert chính xác** toàn bộ timestamp thật, tên thread do JUnit cấp, class/method/line của call stack, vị trí khoảng trắng và đường dẫn file nếu chúng không phải contract.
- **Chỉ assert message template** khi template thực sự là một contract được kiểm soát (ví dụ downstream parser vẫn dựa vào template) hoặc khi test muốn chứng minh tham số được truyền đúng. Với hệ thống có structured fields, ưu tiên assert fields hơn template văn bản.
- **Chỉ assert thứ tự** khi quan hệ nhân quả hoặc giao thức quy định. Event `STARTED` của một operation phải trước `FINISHED` có thể là contract; thứ tự giữa hai request độc lập chạy song song thường không phải.
- **Chỉ assert exception class/cause** khi test contract xử lý lỗi; không cố định từng frame của stack trace.
- **Nên có một vài snapshot/golden test riêng** cho format có yêu cầu tương thích (JSON exporter, hệ thống audit, giao thức gửi log). Giữ chúng ở tầng encoder, không nhân bản trong mọi unit test nghiệp vụ.

Ví dụ nhận xét hai cách kiểm thử:

```java
// Giòn: timestamp, thread, logger layout đều bị khóa.
assertEquals(
    "2026-01-01 10:00:00 INFO [main] OrderService - Rejected order O-42",
    capturedConsoleLine);

// Bền hơn: khi dùng Logback ILoggingEvent trong test.
assertEquals(Level.INFO, event.getLevel());
assertEquals("ORDER_ALREADY_SHIPPED",
             event.getMDCPropertyMap().get("reasonCode"));
```

Đây là **snippet minh họa**, không phải file Java độc lập. Điều kiện quan trọng: để assert MDC, event phải được capture từ đúng thread/thời điểm và có chính sách đưa `reasonCode` vào MDC; nếu ứng dụng không dùng MDC cho field đó thì hãy kiểm tra structured key/value hoặc tham số message tương ứng. Đừng đưa mọi business field vào MDC chỉ để làm test thuận tiện.

## 5. Hiểu cấu trúc log ở JUL và Logback

Java có nhiều hệ sinh thái logging:

- **`java.util.logging` (JUL)** trong JDK có `Logger`, `LogRecord`, `Handler`, `Formatter`. `LogRecord` chứa level, logger name, message, parameters, thrown và thời gian.
- **SLF4J** là facade. `logger.info("item={} status={}", item, status)` là lời gọi facade, còn cách event được lưu phụ thuộc backend.
- **Logback** cung cấp `ILoggingEvent` với level, loggerName, template `getMessage()`, `getArgumentArray()`, `getFormattedMessage()`, `getMDCPropertyMap()` và `getThrowableProxy()`.
- **Log4j2** có event/appenders và test APIs riêng; không thể trực tiếp cast event sang Logback `ILoggingEvent` nếu backend là Log4j2.

Với mục tiêu test semantics, hãy capture ở **điểm gần event nhất** mà vẫn xác minh được integration. Khi muốn test console JSON, kiểm tra thêm encoder; khi muốn test mất collector, kiểm tra thêm sink/transport. Không biến test về một business rule thành integration test mọi tầng nếu không cần.

## 6. Java 17 chạy độc lập: kiểm tra log event thay vì chuỗi formatter

Ví dụ JDK thuần sau minh họa cách thu `LogRecord` với một `Handler` trong bộ nhớ. Không cần SLF4J, Logback hay Maven. Chương trình cố ý **không tạo console pattern**: nó đọc trực tiếp level, template, tham số và Throwable của event, nên thay `Formatter` không ảnh hưởng đến các kiểm tra.

### 6.1. Tệp `SemanticLogDemo.java`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SemanticLogDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.logging.semantic");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        List<LogRecord> captured = new ArrayList<>();

        Handler memory = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    captured.add(record);
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        memory.setLevel(Level.ALL);
        logger.addHandler(memory);

        try {
            logger.log(
                Level.INFO,
                "action={0} outcome={1}",
                new Object[] {"ORDER_CANCEL", "REJECTED"});

            logger.log(
                Level.SEVERE,
                "dependency failed",
                new IllegalStateException("simulated"));

            LogRecord businessEvent = captured.get(0);
            LogRecord errorEvent = captured.get(1);

            System.out.println("events=" + captured.size());
            System.out.println("firstLevel="
                    + businessEvent.getLevel().getName());
            System.out.println("firstTemplate="
                    + businessEvent.getMessage());
            System.out.println("action="
                    + businessEvent.getParameters()[0]);
            System.out.println("outcome="
                    + businessEvent.getParameters()[1]);
            System.out.println("hasThrowable="
                    + (errorEvent.getThrown() != null));

            logger.setLevel(Level.WARNING);
            logger.info("ignored by level");
            System.out.println("afterDisabledInfo="
                    + captured.size());
        } finally {
            logger.removeHandler(memory);
            memory.close();
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac SemanticLogDemo.java
java SemanticLogDemo
```

**Stdout kỳ vọng chính xác** khi chạy riêng chương trình:

```text
events=2
firstLevel=INFO
firstTemplate=action={0} outcome={1}
action=ORDER_CANCEL
outcome=REJECTED
hasThrowable=true
afterDisabledInfo=2
```

Giải thích:

1. `Handler` nhận đúng hai `LogRecord` ban đầu vì logger và handler đều cho phép từ `Level.ALL`.
2. `LogRecord.getMessage()` trả **message template**, không phải nguyên dòng console. Tham số vẫn được truy cập qua `getParameters()`.
3. `LogRecord.getThrown()` kiểm tra Throwable có được gắn vào event mà không render stack trace.
4. Khi chuyển logger sang `Level.WARNING`, lời gọi `logger.info(...)` bị chặn và số event vẫn là hai.
5. `Logger.setUseParentHandlers(false)` tránh root handler tạo output khác; `finally` gỡ handler để không để lại appender thử nghiệm.

Đây là demo **một thread** với sink trong bộ nhớ. Nó không chứng minh format JSON hoặc console chính xác, cũng không chứng minh collector đã lưu. Trong test thật với nhiều thread, cần collector thread-safe và quy tắc hoàn tất rõ ràng. Không dùng demo `ArrayList` làm appender production.

**Đáng chú ý:** chương trình không assert tên thread, thời gian hay chuỗi format cuối. Nó kiểm tra điều **phải đúng dù format thay đổi**.

## 7. JUnit 5 + SLF4J/Logback: capture `ILoggingEvent` đúng cách

Trong dự án dùng SLF4J với Logback, có thể gắn một appender thu event vào **logger riêng dành cho test**. Khi đó test kiểm tra level, template, arguments, MDC và Throwable mà không phụ thuộc `PatternLayout`.

### 7.1. Cấu trúc Maven

```text
log-semantic-tests/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── LoggingContractTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>log-semantic-tests</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Các version cố định nhằm minh họa một môi trường có thể tái lập, **không ngụ ý là version mới nhất**. Với ứng dụng thật, nên dùng dependency management thống nhất, bảo đảm chỉ có một SLF4J provider chủ động trên classpath.

### 7.2. Mã test đầy đủ

Lưu `src/test/java/example/LoggingContractTest.java`:

```java
package example;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.*;

class LoggingContractTest {

    // Thu event SAU level/filter của logger và appender.
    static final class CaptureAppender
            extends AppenderBase<ILoggingEvent> {
        private final CopyOnWriteArrayList<ILoggingEvent> events =
                new CopyOnWriteArrayList<>();

        @Override
        protected void append(ILoggingEvent event) {
            // Đóng băng thông tin lười như formatted message/MDC
            // khi event còn ở ngữ cảnh thread phát sinh.
            event.prepareForDeferredProcessing();
            events.add(event);
        }

        List<ILoggingEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    static final class Rig implements AutoCloseable {
        final Logger logger;
        final CaptureAppender capture;

        Rig() {
            LoggerContext context =
                    (LoggerContext) LoggerFactory.getILoggerFactory();

            logger = context.getLogger(
                    "example.test.logging." + UUID.randomUUID());
            logger.setLevel(Level.TRACE);
            logger.setAdditive(false);

            capture = new CaptureAppender();
            capture.setContext(context);
            capture.setName("capture-" + UUID.randomUUID());
            capture.start();

            logger.addAppender(capture);
        }

        @Override
        public void close() {
            logger.detachAppender(capture);
            capture.stop();
        }
    }

    @Test
    void checksLevelArgumentsAndMdcInsteadOfRenderedLine() {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try (Rig rig = new Rig()) {
            MDC.put("requestId", "req-17");

            rig.logger.info(
                    "action={} outcome={}",
                    "ORDER_CANCEL", "REJECTED");

            List<ILoggingEvent> events = rig.capture.snapshot();
            assertEquals(1, events.size());

            ILoggingEvent event = events.get(0);
            assertEquals(Level.INFO, event.getLevel());
            assertEquals(
                    "action={} outcome={}", event.getMessage());
            assertArrayEquals(
                    new Object[] {"ORDER_CANCEL", "REJECTED"},
                    event.getArgumentArray());
            assertEquals(
                    "req-17",
                    event.getMDCPropertyMap().get("requestId"));
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }

    @Test
    void keepsTheRealThrowableWithoutCheckingStackFrames() {
        try (Rig rig = new Rig()) {
            IllegalStateException problem =
                    new IllegalStateException("simulated");

            rig.logger.error(
                    "Payment failed id={}", "pay-7", problem);

            ILoggingEvent event = rig.capture.snapshot().get(0);

            assertEquals(Level.ERROR, event.getLevel());
            assertEquals("Payment failed id={}", event.getMessage());
            assertNotNull(event.getThrowableProxy());
            assertEquals(
                    IllegalStateException.class.getName(),
                    event.getThrowableProxy().getClassName());
        }
    }

    @Test
    void confirmsDisabledLevelProducesNoInfoEvent() {
        try (Rig rig = new Rig()) {
            rig.logger.setLevel(Level.WARN);

            rig.logger.info("Not visible {}", "detail");
            rig.logger.warn("Degraded dependency {}", "storage");

            List<ILoggingEvent> events = rig.capture.snapshot();
            assertEquals(1, events.size());
            assertEquals(Level.WARN, events.get(0).getLevel());
            assertEquals(
                    "Degraded dependency {}",
                    events.get(0).getMessage());
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

```bash
mvn test
```

**Kỳ vọng:** 3 test pass và Maven báo `BUILD SUCCESS` nếu các dependency tải được và môi trường chạy đúng. Phần hiển thị chi tiết của Maven/Surefire không cố định; xem `target/surefire-reports` khi có assertion thất bại.

### 7.3. Vì sao cách này giảm test giòn?

- Test thứ nhất assert **level** bằng enum và **template + argument array** thay vì toàn bộ dòng đã format. Khi đổi pattern console hoặc thêm timestamp, test vẫn có thể đúng.
- Test thứ hai assert **ThrowableProxy** có đúng class exception. Không bắt test so số dòng stack, file path hay thứ tự frame JVM.
- Test thứ ba xác nhận logger level chặn `INFO`, và `WARN` còn lại. Nó không suy luận filter từ việc stdout vắng dòng nào đó.
- Logger test có **tên riêng** và `additive=false` để event không tự trôi qua root appender gây nhiễu. `try-with-resources` luôn gỡ appender sau mỗi test.
- `prepareForDeferredProcessing()` được gọi trong `append` để dữ liệu như MDC được snapshot khi còn ở ngữ cảnh producer; nếu chỉ giữ tham chiếu event rồi đọc MDC ở thời điểm khác, dữ liệu lười có thể gây test sai.
- `CopyOnWriteArrayList` phù hợp để capture lượng nhỏ trong test. Nó không phải sink hiệu năng cao cho benchmark/traffic production.

**Giới hạn:** Đây là integration test mức logging backend chạy trong bộ nhớ, không kiểm thử encoder JSON, file hay collector từ xa. Tên logger ngẫu nhiên nhằm cô lập test, nên nếu ứng dụng có filter dựa trên tên logger cố định, cần test chính sách đó riêng với tên logger phù hợp.

## 8. Đừng mock logger quá mức

Một kiểu test thường thấy:

```java
// Mã minh họa Mockito trong dự án đã cấu hình mocks.
verify(logger).info(
    "Order {} rejected because {}",
    "O-42", "ORDER_ALREADY_SHIPPED");
```

Kiểm tra này có thể hữu ích nếu **template chính là contract** của một adapter, nhưng có nhiều hạn chế:

- Test khóa việc sử dụng đúng một method overload và đúng số argument, dù log ở sink có thể vẫn đúng sau refactor.
- Không xác minh logger có level đang bật, filter/appender gắn đúng hay event cuối đến được sink.
- Không xác minh MDC, marker, Throwable hoặc encoder nếu các yếu tố này không nằm trong mock.
- Có thể fail vì đổi cách viết câu trong message mà không thay đổi kết quả nghiệp vụ.
- Nếu mock dùng chung, số lần gọi dễ bị ảnh hưởng bởi code hỗ trợ hoặc retry nội bộ.

**Ưu tiên kiểm thử behavior của component trước.** Với yêu cầu “mỗi business rejection phát một audit event”, capture event thật hoặc audit publisher interface rồi assert action/outcome/reasonCode/số lần, thay vì bắt toàn bộ message text phải giống một câu tiếng Anh.

Mocking vẫn phù hợp ở unit test của **một logging adapter** khi cần xác nhận dữ liệu được chuyển vào interface. Nhưng đó là test adapter contract, không thay thế integration test của backend.

## 9. Kiểm tra giá trị có ý nghĩa: đừng chỉ dùng `contains` quá rộng

Tránh chuyển từ test quá chính xác sang test quá lỏng:

```java
assertTrue(line.contains("ERROR"));
assertTrue(line.contains("order"));
```

Hai assertion có thể pass với message `"order not found ERROR_LABEL"` dù level thực tế là INFO, hoặc khi event là đơn hàng khác. Tương tự, `assertNotNull(event)` không kiểm chứng lý do lỗi hay correlation ID.

### Cách chọn assertion

- **Level:** so `event.getLevel()` thay vì tìm từ `ERROR` trong message.
- **Message template/argument:** so tuple `(template, arguments)` nếu ứng dụng còn truyền field theo placeholder; hoặc so structured fields theo key/type.
- **Business outcome:** so `eventType`, `action`, `outcome`, `reasonCode`, resource ID được cho phép.
- **Exception:** so class/cause/chuỗi nguyên nhân theo hợp đồng, không so mọi frame.
- **Count:** `assertEquals(1, events.size())` khi đúng một event là contract; tránh chỉ assert `anyMatch` nếu duplicate là bug.
- **Presence/absence:** test cả trường hợp phát đúng và trường hợp **không được phát** (level/filter/secret).
- **Causality:** chỉ assert thứ tự giữa những mốc được contract bảo đảm.

Nếu đã xây một lớp `AuditEvent` riêng, hãy test object đó như dữ liệu nghiệp vụ — code, enum, ID, timestamp — và test logging adapter chuyển nó sang sink ở một lớp khác. Cách này bền hơn việc parse ngược message từ một console line.

## 10. Structured logging và JSON: test schema, không test thứ tự key

Một sự kiện JSON được formatter xuất ra:

```json
{
  "timestamp": "2026-01-01T10:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "eventType": "BUSINESS_OPERATION_RESULT",
  "action": "ORDER_CANCEL",
  "outcome": "REJECTED",
  "reasonCode": "ORDER_ALREADY_SHIPPED",
  "requestId": "req-17"
}
```

Nếu hệ thống downstream cần các field này, **format JSON là một contract thật**. Nhưng so chuỗi JSON nguyên vẹn vẫn không cần thiết: thứ tự key, indentation hoặc encoding escape tương đương có thể thay đổi trong khi JSON semantics giữ nguyên.

Ví dụ trong dự án đã dùng Jackson:

```java
// Snippet minh họa; cần ObjectMapper, JsonNode,
// outputJson và các import Jackson phù hợp.
JsonNode node = objectMapper.readTree(outputJson);

assertEquals("INFO", node.path("level").asText());
assertEquals("BUSINESS_OPERATION_RESULT",
             node.path("eventType").asText());
assertEquals("ORDER_CANCEL",
             node.path("action").asText());
assertEquals("REJECTED",
             node.path("outcome").asText());
assertEquals("ORDER_ALREADY_SHIPPED",
             node.path("reasonCode").asText());
assertTrue(node.path("timestamp").isTextual());
```

**Lưu ý:** `path(...).asText()` có thể trả chuỗi rỗng khi thiếu trường. Khi schema yêu cầu bắt buộc và kiểu cụ thể, bổ sung `hasNonNull`, `isTextual` và validation schema. Không coi chỉ một số assertion trên là JSON schema validation hoàn chỉnh.

Nếu contract yêu cầu JSON **mỗi event một dòng** (NDJSON), test có thể kiểm tra từng dòng parse được thành một object JSON và không có ký tự điều khiển làm vỡ record; không bắt whitespace hoặc thứ tự key phải giống bản golden text.

### Test những thứ encoder thật sự phải đảm bảo

| Requirement | Cách test |
| --- | --- |
| Field `timestamp` hợp lệ | Parse ISO-8601 và kiểm tra phạm vi/clock khi có |
| `level` và `reasonCode` | Kiểm tra key và kiểu/value |
| `requestId` không bị bỏ | `hasNonNull` + kiểu string |
| Message chứa `\r\n` | Serialize/parse giữ một JSON object, escaping hợp lệ |
| Unicode tiếng Việt | Parse round trip và so nội dung |
| Throwable | Kiểm tra field exception/type/stack theo schema, không phụ thuộc line numbers |
| Version schema | Assert `schemaVersion` và tính tương thích theo version |
| Thông tin nhạy cảm | Dùng token giả, kiểm tra field/output ở mọi sink cần bảo vệ |

Nếu có consumer không kiểm soát được hoặc format là định dạng legacy cố định từng byte, có thể cần **golden-file test** của output nguyên văn. Đó là ngoại lệ có lý do cụ thể, không phải mặc định cho mọi test logging.

## 11. Timestamp, Clock và timezone: test có kiểm soát

Tránh:

```java
assertEquals(
    "2026-01-01 10:00:00.000",
    extractTimestamp(logLine));
```

nếu ứng dụng thực sự dùng `Instant.now()`. Hệ thống CI chạy ở múi giờ khác, scheduler chậm, precision khác sẽ khiến test lỗi ngẫu nhiên.

Ba chiến lược:

1. **Inject `Clock`:** lớp nghiệp vụ/event producer tạo timestamp bằng `Instant.now(clock)`. Trong test dùng `Clock.fixed(...)`; chỉ assert timestamp cố định khi đã kiểm soát nguồn thời gian.
2. **Assert tính hợp lệ:** parse timestamp và kiểm tra nó nằm trong khoảng trước–sau phép thử với sai số hợp lý, nếu contract không cần thời điểm chính xác.
3. **Test formatter riêng:** cấp một event có timestamp cố định vào encoder rồi kiểm tra timezone/format được quy định.

Mã minh họa Java 17:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-01-01T10:00:00Z"),
    ZoneOffset.UTC);
Instant occurredAt = Instant.now(fixed);
assertEquals(
    Instant.parse("2026-01-01T10:00:00Z"),
    occurredAt);
```

Đoạn này dùng `Clock`, `Instant`, `ZoneOffset` và `assertEquals` từ JUnit; nó không phải một chương trình độc lập. Với backend logger, event timestamp có thể do framework tạo thay vì `Clock` của ứng dụng; nếu cần test đúng formatter timestamp, hãy kiểm soát event/encoder chứ không cố thay đồng hồ hệ thống thật.

Không tự normalize mọi timestamp thành một giá trị chung ở production: test chỉ kiểm soát đồng hồ trong phạm vi fixture.

## 12. Exception và stack trace: test bản chất, không test frame

Exception stack trace có thể thay đổi khi:

- Refactor method/package hoặc thêm wrapper.
- JDK/compiler thay đổi dòng/số frame.
- Chạy qua reflection, proxy, Spring AOP hoặc thread pool.
- Logger/encoder thay đổi cách render `cause` và `suppressed`.
- Cùng một Throwable được log ở các tầng khác nhau.

Ví dụ giòn:

```java
assertTrue(text.contains("at com.example.PaymentService.pay(PaymentService.java:87)"));
```

Chỉ đổi vị trí code hoặc thêm một dòng là test thất bại. Nếu yêu cầu thực tế là “lỗi dependency giữ nguyên cause”, kiểm tra:

```java
assertEquals(Level.ERROR, event.getLevel());
assertNotNull(event.getThrowableProxy());
assertEquals(
    "java.net.SocketTimeoutException",
    event.getThrowableProxy().getClassName());
```

Đây là snippet dựa trên `ILoggingEvent` của Logback và cần thực sự ném/gắn `SocketTimeoutException` trong fixture. Nếu ứng dụng bọc exception, test cần kiểm tra **cause chain** theo contract, không buộc top-level class giống root cause.

Một số lời khuyên:

- Với **business error** dự kiến, thường chỉ cần `reasonCode`/outcome, không bắt buộc full stack.
- Với **technical failure** bất thường, nên giữ Throwable có nguyên nhân hữu ích ở một boundary chịu trách nhiệm, tránh log trùng nhiều tầng.
- Nếu requirement đòi encoder in exception, test encoder **có field/section exception**, không so toàn bộ byte của stack trace trừ khi có lý do đặc biệt.
- Đừng assert line number của caller trừ khi đó chính là feature được kiểm tra, ví dụ một thư viện công cụ debug cần định vị call site.

## 13. MDC, correlation ID và thread propagation

Một hệ thống cần `requestId` hoặc `traceId` để ghép log qua service. Test đúng cách nên:

1. Đặt giá trị correlation giả như `req-17`.
2. Thực thi hành động trong phạm vi MDC phù hợp.
3. Capture event khi context còn chính xác.
4. Assert **MDC map của event**, không tìm một chuỗi trong output phụ thuộc pattern `%X{requestId}`.
5. Khôi phục MDC trong `finally` để không nhiễm các test khác.

Với SLF4J:

```java
Map<String, String> before = MDC.getCopyOfContextMap();

try {
    MDC.put("requestId", "req-17");
    service.handle(command);
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
```

Đây là snippet trong ứng dụng đã có `MDC`, `Map`, `service` và `command`. Đừng giả định `requestId` tự có ở worker của `ExecutorService`, `CompletableFuture` hoặc reactive pipeline; context có thể cần truyền rõ ràng. Nếu test cần xác minh **context propagation**, hãy dùng executor thật với thread khác, capture event trong thread đó và kiểm tra ID đúng, rồi kiểm tra ID không rò sang task tiếp theo.

**Không dùng requestId thật hoặc bearer token trong fixture**. ID test nên không nhạy cảm, đúng schema và có thể lặp lại.

## 14. Async logging: đừng assert ngay và đừng `Thread.sleep`

Khi backend dùng async appender, sự kiện có thể được đưa vào queue rồi một thread khác mới append vào sink. Test:

```java
logger.info("Operation completed");
assertEquals(1, sink.events().size()); // Có thể chạy quá sớm.
```

không ổn định vì collector được gọi trước khi worker kịp xử lý. Thêm `Thread.sleep(200)` chỉ giảm xác suất fail, **không tạo bảo đảm**.

### Cách đợi có ranh giới

- Dùng `BlockingQueue<ILoggingEvent>` trong appender thử; test gọi `poll(timeout)` để chờ **event đã đến sink**.
- Hoặc dùng `CountDownLatch` được count down tại `append(...)`, chờ với timeout hữu hạn.
- Hoặc dùng API flush/drain/await của hệ thống nếu có contract hỗ trợ.
- Đối với collector mạng, chỉ dùng “sink nhận được” khi cần kiểm tra delivery, không suy từ producer queue trống.

Mã thu event minh họa dành cho Logback:

```java
// Snippet, cần import AppenderBase, ILoggingEvent,
// BlockingQueue, LinkedBlockingQueue và TimeUnit.
final class QueueAppender extends AppenderBase<ILoggingEvent> {
    final BlockingQueue<ILoggingEvent> received =
            new LinkedBlockingQueue<>();

    @Override
    protected void append(ILoggingEvent event) {
        event.prepareForDeferredProcessing();
        received.offer(event);
    }
}

// Sau khi đã gắn appender vào đúng pipeline và start:
ILoggingEvent event = appender.received.poll(
        2, TimeUnit.SECONDS);
assertNotNull(event);
assertEquals("OPERATION_FINISHED", event.getMessage());
```

Đoạn này **không độc lập** (biến `appender`, `assertNotNull`/`assertEquals` và việc gắn appender chưa được khai báo đầy đủ). Test cần chọn timeout theo môi trường và cuối cùng `stop()` appender/async worker trong `finally`.

### Cẩn trọng với assertion “không có event”

Việc `queue.poll(100ms) == null` **không tự chứng minh** event bị filter; worker có thể đơn giản đang chậm. Nếu backend có một queue FIFO và consumer tuần tự, có thể gửi một **sentinel event** được chấp nhận *sau* sự kiện cần kiểm tra, chờ sentinel đến sink rồi kiểm tra tập event đã xử lý trước đó. Điều này chỉ đúng khi contract queue/sink và các filter không phá giả định FIFO; không áp dụng mù quáng cho nhiều worker/partition.

Nếu backend có discard policy hoặc queue overflow, mất event có thể do quá tải chứ không do filter. Muốn test filter, tạo môi trường không discard hoặc kiểm soát riêng chính sách queue.

## 15. Test level, filter và nhiều appender

Một event có thể bị loại tại nhiều điểm:

```text
logger.info(...)
  |
  v
Logger level / TurboFilter
  |
  v
Logging event
  |
  +--> ConsoleAppender -- filter A --> console
  |
  +--> FileAppender ---- filter B --> file
```

Giả sử `filter A` chặn log sức khỏe định kỳ, `filter B` không chặn. Không thể assert “log không tồn tại trong hệ thống” chỉ vì console không thấy nó. Bài test phải xác định **sink đích đang kiểm tra**.

Trong Logback, appender filter có kết quả `DENY`, `NEUTRAL`, `ACCEPT`. Nếu một logger bị level chặn trước, `ACCEPT` trên appender filter không làm event xuất hiện lại. `TurboFilter` hoạt động sớm hơn và có semantics cần kiểm tra riêng.

Chiến lược:

- **Logger-level test:** đặt level dự định, emit nhiều mức, assert số event tại một appender không có filter khác.
- **Appender filter test:** đặt logger ở mức cho phép, gắn filter vào appender cụ thể, test sự kiện nhận/bị loại tại appender đó.
- **Multiple appender test:** capture từng sink và so các tập event riêng; không trộn log từ root và logger con.
- **Configuration test:** nếu filter định nghĩa trong `logback-spring.xml` theo profile, dùng integration test Spring Boot với profile phù hợp. Không kiểm tra bằng cách chỉ gọi method `filter.decide` rồi suy cấu hình production đúng.
- **TurboFilter test:** cô lập `LoggerContext` và kiểm tra semantics tại tầng sớm. Không reset root context dùng chung của test suite mà không kiểm soát.

**Giữ test đúng scope:** thay pattern console không nên làm fail logger-level test. Ngược lại, đổi filter một sink phải làm fail test của sink đó nếu thay đổi contract.

## 16. So sánh sự kiện khi có nhiều thread

Một test giòn khác là so thứ tự event toàn cục:

```java
assertEquals(List.of("worker-A-start", "worker-B-start"),
             receivedMessages);
```

Nếu hai worker chạy song song, scheduler có thể cho B log trước A mà không có lỗi. Với concurrency:

- Gán `operationId`/`taskId` duy nhất cho từng workflow.
- Đợi mọi task hoàn tất và sink xử lý đủ event theo contract.
- So **set/multiset** theo ID hoặc đếm theo actor/task, không theo thứ tự giao nhau không được bảo đảm.
- Nếu cần bảo đảm thứ tự trong **một** task, nhóm theo task ID và kiểm tra quan hệ `STARTED -> FINISHED`.
- Dùng collector thread-safe và snapshot sau khi đồng bộ hoàn tất.
- Đừng giả định timestamp của nhiều host cho tổng thứ tự chính xác khi clock lệch.

Một lưu ý quan trọng: **set** sẽ che duplicate. Nếu requirement là “mỗi operation có đúng một terminal event”, hãy kiểm tra **multiset/count** chứ không chỉ các ID độc nhất. Có thể dùng map `operationId -> count` và assert đúng số event cho từng operation.

## 17. Khi nào golden/snapshot test thật sự hữu ích?

Snapshot không phải luôn xấu. Nó hữu ích khi người tiêu thụ log có hợp đồng trình bày cụ thể:

- Một exporter phát text log cho hệ thống legacy chỉ đọc một pattern cố định.
- Một JSON encoder có schema được version hóa và parser downstream nhạy với kiểu trường.
- Một dòng audit theo chuẩn nội bộ bắt buộc tên trường, escaping hoặc delimiter.
- Một tính năng SDK mà output log chính là sản phẩm cho người dùng.

Nhưng cần thiết kế golden test thông minh:

1. Cấp **event fixture cố định** (timestamp, level, logger, MDC, exception).
2. Chỉ snapshot **output của formatter/encoder**, không snapshot tất cả unit test nghiệp vụ.
3. Với JSON, parse object và so schema/value thay vì raw string nếu không cần kiểm tra byte-level.
4. Nếu output thực sự yêu cầu byte-level, ghi rõ lý do: delimiter, field order, newline, encoding hoặc chữ ký.
5. Thay đổi golden file chỉ sau khi review ý nghĩa và hợp đồng consumer, không bấm “update snapshots” để làm CI xanh khi chưa hiểu sai khác.
6. Bảo vệ fixture khỏi secret thật và dữ liệu cá nhân.

Nên có ít golden test nhưng đúng trọng tâm, thay vì hàng trăm assertion lặp lại cùng một pattern console.

## 18. Các kiểu test thất bại phổ biến và cách sửa

| Kiểu test | Vấn đề | Cách sửa |
| --- | --- | --- |
| `assertEquals(fullConsoleLine, actual)` | Timestamp/thread/pattern dễ đổi | Capture event semantic |
| So toàn bộ stack trace | Refactor/JDK làm đổi frames | Assert Throwable type/cause |
| `assertTrue(text.contains("ERROR"))` | Message có chữ ERROR nhưng level không phải ERROR | Assert enum level |
| `assertTrue(text.contains("id=42"))` | Có thể match ID khác hoặc field khác | Assert field/value rõ ràng |
| Mock chính xác mọi lời gọi logger | Khóa template/overload, không kiểm tra sink | Test adapter contract và capture event thật |
| So thứ tự giữa thread độc lập | Scheduler không bảo đảm | So count/multiset; order chỉ trong scope có bảo đảm |
| `Thread.sleep` chờ async | Flaky khi CI chậm | Latch/queue/ack với timeout |
| Chờ 100ms rồi assert không event | Có thể event chỉ đến muộn | Barrier/sentinel và contract FIFO |
| So JSON string nguyên văn | Key order/whitespace thay đổi | Parse JSON và so schema |
| Test timestamp `now()` bằng chuỗi cố định | Clock và timezone thay đổi | Inject Clock hoặc parse/phạm vi |
| Đọc MDC sau khi thread đã clear | Event có thể chưa snapshot MDC | Prepare event trước khi deferred, test đúng thread |
| Gắn appender vào root không cleanup | Log từ test khác tràn vào | Logger riêng, `additive=false`, detach/stop |
| Test thiếu event chỉ bằng mock logger | Không kiểm tra filter, queue, sink | Quan sát sau tầng cần bảo vệ |
| Assert có ít nhất một event | Không phát hiện duplicate | Assert số event khi contract yêu cầu |
| Chỉ kiểm tra success path | Không biết level/secret/filter khi lỗi | Test failure, negative và security cases |

## 19. Ma trận kiểm thử thực tế cho logging ít phụ thuộc format

Giả sử ứng dụng cần log kết quả hủy đơn. Một bảng test có thể dùng:

| Tình huống | Hành vi business | Event contract | Không bắt buộc |
| --- | --- | --- | --- |
| Hủy thành công | Đơn chuyển `CANCELLED` | 1 event `ORDER_CANCEL/SUCCEEDED`, requestId đúng | Timestamp dạng `yyyy-MM-dd HH:mm:ss` |
| Đơn đã giao | Không đổi | `REJECTED`, `reasonCode=ALREADY_SHIPPED`, `INFO` theo policy | Chuỗi câu tiếng Việt/Anh giống 100% |
| Lỗi storage | Không commit | `FAILED`, `ERROR`, Throwable/cause phù hợp | Mỗi stack frame và line number |
| Logger DEBUG tắt | Không có DEBUG event tại sink | Count đúng với logger level | Dòng console đầy đủ |
| Filter health-check | Event thường còn, health bị loại ở đúng appender | Tập ID được nhận | Thứ tự log ở appender khác |
| Async delivery | Terminal event đến sink trong timeout | Đúng ID, outcome, count | Event xuất hiện ngay sau lời gọi |
| Concurrent requests | Mỗi operation có đúng terminal event | Multiset ID, không mất/trùng | Tổng thứ tự xuyên threads |
| JSON exporter | Field/schema và escaping hợp lệ | Parse JSON, types/required keys | Key order, indentation |
| Input chứa CR/LF | Không tạo record giả | Escaping/validation đúng sink | Cách JSON viết `\\n` hay mã escape tương đương |
| Token giả trong request | Không lộ ở sink được bảo vệ | Không có token giả trong output cuối | Từ ngữ message chính xác |

Ma trận này tách **business correctness**, **event semantics**, **encoder correctness** và **delivery**. Mỗi lớp có oracle riêng nên khi test fail, người bảo trì biết cần điều tra ở đâu.

### Tiêu chí chấp nhận một test logging

Một test tốt cần:

- Fail khi **hành vi logging quan trọng** đổi sai (mất exception, sai severity, thiếu reasonCode, leak secret, duplicate event).
- Vẫn pass khi chỉ **trang trí output** đổi mà không ảnh hưởng contract (khoảng trắng, timestamp runtime, tên thread).
- Có fixture/hạ tầng **cô lập** và cleanup đáng tin, không gây flaky khi chạy toàn test suite hoặc CI song song.
- Có thông báo thất bại đủ chỉ ra **field/event** sai, không chỉ dump hàng nghìn dòng log.
- Có boundary rõ giữa unit test event semantics và integration test encoder/collector.

## 20. Bảo mật: tránh dùng format test để che rò dữ liệu

Một lý do thật sự cần kiểm tra output cuối là **secret redaction và log injection**. Nhưng đây không phải lý do để khóa toàn bộ dòng log ở mọi test.

- Dùng **secret giả duy nhất** trong fixture, chẳng hạn `FAKE_TOKEN_TEST_73`, không dùng mật khẩu hay credential thật.
- Nếu requirement là “token không được vào collector”, test event ở đầu pipeline chưa đủ; cần kiểm tra **sink cuối có thể nhận token** và mọi appender liên quan.
- Nếu input chứa `\r`/`\n`, kiểm tra encoder hoặc schema bảo đảm không tạo log entry giả. Với JSON encoder, parse round-trip và kiểm tra message vẫn là một trường.
- Nếu có email, ID, địa chỉ hoặc payload nhạy cảm, dùng allowlist trường được phép thay vì log toàn DTO rồi viết test che từng chuỗi.
- Không ghi raw log có secret giả vào báo cáo CI nơi rộng người xem nếu không cần, dù secret giả vẫn nên được đặt dễ nhận diện.
- Một `logger.info` có thể phát ra multiple sinks. Chỉ vì một sink đã redacted không chứng minh mọi sink khác đều an toàn.

### Phân biệt hai bài toán

**Brittle format testing** làm chậm refactor vì thay đổi layout hợp lệ gây fail. **Security output testing** lại là bảo vệ contract thực sự và có thể cần chính xác ở tầng encoder/sink. Không nên bỏ security test với lý do “test quá phụ thuộc format”; chỉ cần đặt assertion đúng vị trí.

## 21. Checklist trước khi merge một thay đổi logging

- [ ] Xác định rõ test bảo vệ event semantics, filter, encoder, transport hay audit.
- [ ] Không so toàn bộ dòng console nếu timestamp/thread/pattern không phải contract.
- [ ] So level bằng enum/API, không suy từ chữ trong message.
- [ ] So action/outcome/reasonCode/ID theo fields hoặc template/arguments phù hợp.
- [ ] Nếu cần exception, assert type/cause, không khóa mọi stack frame.
- [ ] Nếu cần JSON schema, parse JSON và assert kiểu/field, không khóa thứ tự key.
- [ ] Khi có async, dùng latch/queue/ack/timeout, không dựa vào sleep cố định.
- [ ] Khi có concurrency, so tập đếm/multiset và chỉ áp ordering khi có bảo đảm.
- [ ] Test ghi log đúng số lần, không chỉ “có ít nhất một log”.
- [ ] Logger/appender dùng cho test được cô lập, detach/stop và MDC được restore.
- [ ] Có negative tests cho level/filter và dữ liệu nhạy cảm.
- [ ] Test input CR/LF, Unicode và exception ở tầng encoder nếu có yêu cầu format.
- [ ] Test dùng secret giả, không copy dữ liệu production vào fixture.
- [ ] Chỉ cập nhật snapshot/golden khi đã review contract với consumer.
- [ ] Khi đổi backend, xem lại API capture (JUL/Logback/Log4j2), đừng cast sai loại event.

**Ghi nhớ:** test logging bền vững không đồng nghĩa “ít assert”. Hãy assert **mạnh vào hành vi có ý nghĩa** — event nào, level gì, trường nào, exception nào, đến sink nào — và **lỏng có chủ đích ở yếu tố trình bày không có hợp đồng**. Chỉ khóa byte-level format khi chính format là sản phẩm/API cần bảo vệ; phần còn lại nên được test bằng cấu trúc sự kiện và các ranh giới delivery rõ ràng.
