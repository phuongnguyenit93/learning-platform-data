# Kiểm thử log level trong Java

## Mục tiêu bài học

**Kiểm thử log level** là kiểm tra xem những sự kiện ghi log ở các mức **TRACE, DEBUG, INFO, WARN, ERROR** (hoặc các mức tương ứng trong **java.util.logging**) có thực sự được chấp nhận và xuất đến đúng đích theo cấu hình dự định hay không.

Trong module **Java Core Logging**, đây là một phần quan trọng của **Testing logging**: không chỉ chứng minh rằng một lời gọi logger được thực thi, mà còn phải chứng minh **mức thấp bị chặn**, **mức quan trọng được giữ**, **logger con kế thừa đúng**, và **handler/appender/filter không làm lệch kết quả**.

Sau bài này, bạn có thể:

1. Hiểu sự khác biệt giữa mức của sự kiện, mức cấu hình trực tiếp, **effective level** và ngưỡng của handler/appender.
2. Viết test **cho phép** và test **loại bỏ** cùng một logger; tránh kết quả dương tính giả.
3. Thực hành bảy ca kiểm thử **Java 17 thuần JDK**, có assertion và stdout ổn định.
4. Kiểm thử **Logback với JUnit 5 + ListAppender**, cũng như cấu hình Log4j2 và Spring Boot.
5. Kiểm soát sự tương tác giữa root logger, package logger, additivity, filters và các môi trường dev/test/prod.
6. Giải quyết các ca khó: async logging, output khác stream, test chạy song song, backend sai, config reload.
7. Tạo bộ test bảo đảm WARN/ERROR hữu ích không bị mất mà DEBUG/TRACE không bị bật tràn lan ngoài ý muốn.

## 1. Log level và kết quả của một lời gọi logger

Ví dụ một ứng dụng dùng SLF4J:

~~~java
// Minh họa bên trong class đã có logger SLF4J và biến orderId.
log.trace("Validate step 1 for orderId={}", orderId);
log.debug("Validation details, orderId={}", orderId);
log.info("Order accepted, orderId={}", orderId);
log.warn("Inventory latency is high, orderId={}", orderId);
log.error("Order failed, orderId={}", orderId, exception);
~~~

Nếu **effective logger level = INFO**, các lời gọi TRACE/DEBUG thường bị loại ở logger; INFO/WARN/ERROR có thể đi tiếp đến appender.

**Có thể đi tiếp** không đồng nghĩa chắc chắn đã được lưu trong file hoặc backend tập trung. Một appender filter khác, queue đầy, lỗi disk hoặc collector có thể làm record không xuất hiện ở nơi truy vấn.

Cần phân biệt:

| Khái niệm | Câu hỏi |
| --- | --- |
| **Event level** | Lời gọi tạo một sự kiện ở mức nào? |
| **Configured logger level** | Đặt trực tiếp mức nào cho logger đó? |
| **Effective logger level** | Sau kế thừa, logger thực tế đang dùng mức nào? |
| **Handler/appender threshold** | Đích nhận event có loại tiếp mức thấp không? |
| **Filter** | Có quy tắc dựa trên message, marker, MDC hoặc metadata không? |
| **Routing** | Event đủ điều kiện được gửi đến console, file hoặc collector nào? |
| **Delivery** | Sink/queue có xử lý thành công hay chỉ mới nhận event vào RAM? |

Một unit test cấp logger có thể kiểm tra ba cột đầu. Để xác nhận record thật sự được xuất, hãy gắn **test handler/appender**. Để xác nhận collector hoặc storage, cần integration test ở đường đi tương ứng.

## 2. Các hệ thống có tập level khác nhau

Với Logback Classic và SLF4J thông dụng:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

Với Log4j2, ngoài các mức trên thường còn có **FATAL, ALL, OFF** và khả năng định nghĩa custom levels. Không áp dụng mù bảng mức của Logback cho mọi backend.

**java.util.logging (JUL)** thuộc JDK dùng các mức khác:

| JUL Level | Giá trị intValue | Cách dùng thường gặp |
| --- | ---: | --- |
| **SEVERE** | 1000 | Lỗi nghiêm trọng |
| **WARNING** | 900 | Cảnh báo |
| **INFO** | 800 | Thông tin hoạt động |
| **CONFIG** | 700 | Thông tin cấu hình |
| **FINE** | 500 | Chi tiết gỡ lỗi |
| **FINER** | 400 | Chi tiết hơn |
| **FINEST** | 300 | Mức chi tiết rất sâu |
| **OFF** | Integer.MAX_VALUE | Chặn sự kiện tại ngưỡng này |
| **ALL** | Integer.MIN_VALUE | Không loại level tại ngưỡng này |

**FINE** gần với DEBUG về mục đích, **SEVERE** gần với ERROR, nhưng không có quy tắc chung yêu cầu mọi bridge/provider phải ánh xạ giống nhau. Một ứng dụng chuyển JUL qua SLF4J hoặc Log4j2 cần test trên **backend thật**.

### 2.1. Ma trận cơ bản cho Logback

Không có filter đặc biệt, một logger với effective level thông thường có hành vi:

| Logger effective level | TRACE | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- |
| TRACE | Có | Có | Có | Có | Có |
| DEBUG | Không | Có | Có | Có | Có |
| INFO | Không | Không | Có | Có | Có |
| WARN | Không | Không | Không | Có | Có |
| ERROR | Không | Không | Không | Không | Có |
| OFF | Không | Không | Không | Không | Không |

Đây là **ma trận logger threshold**, chưa bao gồm appender filter, marker, sampling, async queue hoặc custom level.

Một test hoàn chỉnh phải kiểm tra **hai chiều**: event dự kiến xuất hiện **thật sự xuất hiện**, và event dự kiến bị chặn **thật sự không xuất hiện**. Chỉ kiểm tra chiều âm dễ gây **false positive** khi cả hệ thống logging đã bị tắt.

## 3. Kiểm thử logger level hay output cuối?

Có ít nhất ba mục tiêu kiểm thử khác nhau.

**Mục tiêu A — cấu hình:** xác nhận package **com.example.orders** đang ở DEBUG, root ở INFO. Test này có thể đọc effective level. Nó nhanh nhưng chưa chứng minh output.

**Mục tiêu B — phát và lọc sự kiện:** gọi DEBUG, INFO, WARN; dùng một appender trong RAM để kiểm tra event nào đã đi qua. Đây là cách phù hợp cho đa số unit test.

**Mục tiêu C — toàn pipeline:** xác minh console/file/collector thật sự ghi record và không tạo trùng. Cần integration test với appender/encoder/collector đang được dùng.

~~~text
Code gọi log.debug()
       │
       ▼
Logger effective level
       │
       ▼
Logger filter / backend rule
       │
       ▼
Event được tạo
       │
       ▼
Handler / Appender threshold + filter
       │
       ▼
Async queue (nếu có)
       │
       ▼
Console / File / Collector
       │
       ▼
Storage / Query
~~~

Mỗi mốc có thể loại event. Vì vậy một thử nghiệm **không thấy DEBUG ở stdout** không thể tự kết luận nguyên nhân là logger.INFO: có thể handler ghi stderr, không có provider, appender không gắn hoặc queue chưa drain.

## 4. Kế thừa và logger hierarchy

Giả sử cấu hình như sau:

~~~text
root                              INFO
└── com.example
    ├── com.example.orders        DEBUG
    │   ├── OrderService          kế thừa DEBUG
    │   └── workflow.Checkout     kế thừa DEBUG
    └── com.example.payments      kế thừa INFO
        └── PaymentService        kế thừa INFO
~~~

Kỳ vọng:

- **com.example.orders.OrderService** cho DEBUG trở lên.
- **com.example.orders.workflow.Checkout** kế thừa ngưỡng DEBUG.
- **com.example.payments.PaymentService** không phát DEBUG nhưng vẫn phát INFO/WARN/ERROR.
- Một class có level override trực tiếp dùng level riêng, không nhất thiết theo package.
- Một logger tên **business** không tự thuộc hierarchy com.example.orders chỉ vì nó được khai báo trong class ở package orders.

### 4.1. JUL getLevel() trả null

Trong JUL, một logger con có thể có:

~~~java
// Minh họa, không phải main hoàn chỉnh.
java.util.logging.Logger child =
        java.util.logging.Logger.getLogger(
                "com.example.orders.OrderService");
System.out.println(child.getLevel());
~~~

Nếu kết quả là **null**, điều này thông thường có nghĩa logger **kế thừa level từ cha**, **không phải** logger bị tắt. Test không được dùng null làm dấu hiệu OFF.

Logback tương tự ở khía cạnh configured level có thể null; để kiểm tra mức cuối dùng API **getEffectiveLevel()** của Logback. Log4j2 dùng kiến trúc LoggerConfig khác; tránh đoán effective level từ một config object không thực sự áp dụng cho logger cần test.

### 4.2. Logger cha không nhất thiết lọc lại record đã được logger con chấp nhận

Một điểm dễ sai:

~~~text
JUL parent logger level = WARNING
JUL child logger level  = FINE
JUL parent handler      = ALL
child.fine("details")
~~~

Record **FINE** từ child có thể tới handler gắn ở parent, vì việc chuyển record lên parent handler **không đồng nghĩa kiểm tra lại level parent logger**. Handler có level riêng nên với ALL nó cho phép record.

Trong Logback, khi logger con DEBUG đã chấp nhận event, event có thể đến appender gắn ở root INFO thông qua additivity. Muốn một appender chỉ nhận WARN/ERROR, hãy đặt threshold/filter ở chính appender hoặc vị trí lọc phù hợp.

**Bài học:** test mức logger và test mức handler/appender là hai bài test khác nhau.

## 5. Ma trận test cần chuẩn bị

| Ca | Thiết lập | Kết quả đúng |
| --- | --- | --- |
| Logger INFO | Logger INFO, handler ALL | FINE bị chặn; INFO/WARNING/SEVERE được ghi. |
| Handler WARNING | Logger FINE, handler WARNING | FINE/INFO bị chặn tại handler, WARNING/SEVERE được ghi. |
| Inherit | Parent WARNING, child null | Child chỉ phát WARNING/SEVERE. |
| Override | Parent WARNING, child FINE, handler ALL | Child phát FINE/INFO/WARNING/SEVERE. |
| Handler filter | Logger INFO, handler ALL, filter loại message INFO | INFO bị filter loại, WARNING/SEVERE được giữ. |
| OFF | Parent OFF, child inherit | Không sự kiện nào được ghi. |
| ALL | Parent ALL, handler ALL | Bốn event từ FINE đến SEVERE đều được ghi. |
| Package scope | Chỉ orders DEBUG | Payments không phát DEBUG. |
| Async | Bật AsyncAppender/AsyncLogger | Test chờ điều kiện hoàn thành, không assert quá sớm. |
| Root/additivity | Child có appender riêng | Đúng số bản ghi dự định ở mỗi sink. |
| Environment | Profile production | Effective level khớp chính sách sau mọi override. |

Với một test âm (event không xuất hiện), luôn thêm ít nhất **một positive control** cho thấy cùng handler/appender đang hoạt động. Nếu không, test có thể vô tình pass khi không có appender nào.

## 6. Java 17 thuần JDK: bộ bảy test có thể chạy độc lập

Đây là chương trình hoàn chỉnh, chỉ cần **JDK 17**. Nó không cần JUnit, Maven, Spring Boot, Logback hay dependency ngoài.

Chương trình tạo **logger cha theo tên của từng test**, **logger con giả lập một class trong package**, và một **CaptureHandler** lưu LogRecord đi qua handler vào danh sách. Mỗi ca đặt logger level, handler level và filter rồi so sánh với kết quả mong đợi bằng **AssertionError**. Không dùng lệnh assert Java vì lệnh đó mặc định có thể không được JVM bật nếu thiếu tham số -ea.

### 6.1. Toàn bộ mã nguồn

Lưu thành file **LogLevelTestDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogLevelTestDemo {

    private static int sequence = 0;

    static final class CaptureHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        CaptureHandler(Level level, Filter filter) {
            setLevel(level);
            setFilter(filter);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + ":" + record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Khong co I/O trong demo.
        }

        @Override
        public void close() {
            // Chi su dung danh sach trong RAM.
        }

        List<String> captured() {
            return List.copyOf(events);
        }
    }

    static void check(
            String label,
            Level parentLevel,
            Level handlerLevel,
            Level childLevel,
            Filter filter,
            List<String> expected) {

        String name = "demo.level.case" + (++sequence);
        Logger parent = Logger.getLogger(name);
        Logger child = Logger.getLogger(name + ".OrderService");

        Level previousParent = parent.getLevel();
        Level previousChild = child.getLevel();
        boolean previousParentUse =
                parent.getUseParentHandlers();
        boolean previousChildUse =
                child.getUseParentHandlers();

        CaptureHandler capture = new CaptureHandler(
                handlerLevel, filter);

        try {
            parent.setUseParentHandlers(false);
            child.setUseParentHandlers(true);
            parent.setLevel(parentLevel);
            child.setLevel(childLevel);  // null = ke thua
            parent.addHandler(capture);

            child.fine("fine");
            child.info("info");
            child.warning("warning");
            child.severe("severe");

            List<String> actual = capture.captured();
            if (!expected.equals(actual)) {
                throw new AssertionError(
                        label + " expected=" + expected
                        + " actual=" + actual);
            }
            System.out.println("PASS " + label);
        } finally {
            parent.removeHandler(capture);
            capture.close();

            parent.setLevel(previousParent);
            child.setLevel(previousChild);
            parent.setUseParentHandlers(previousParentUse);
            child.setUseParentHandlers(previousChildUse);
        }
    }

    public static void main(String[] args) {
        List<String> all = List.of(
                "FINE:fine",
                "INFO:info",
                "WARNING:warning",
                "SEVERE:severe");

        check("logger INFO",
                Level.INFO, Level.ALL, null, null,
                List.of("INFO:info",
                        "WARNING:warning",
                        "SEVERE:severe"));

        check("handler WARNING",
                Level.FINE, Level.WARNING, null, null,
                List.of("WARNING:warning", "SEVERE:severe"));

        check("inherit WARNING",
                Level.WARNING, Level.ALL, null, null,
                List.of("WARNING:warning", "SEVERE:severe"));

        check("child overrides FINE",
                Level.WARNING, Level.ALL, Level.FINE, null,
                all);

        check("handler filter INFO",
                Level.INFO, Level.ALL, null,
                record -> !"info".equals(record.getMessage()),
                List.of("WARNING:warning", "SEVERE:severe"));

        check("logger OFF",
                Level.OFF, Level.ALL, null, null,
                List.of());

        check("logger ALL",
                Level.ALL, Level.ALL, null, null,
                all);

        System.out.println("ALL 7 TESTS PASSED");
    }
}
~~~

### 6.2. Lệnh biên dịch và chạy

~~~bash
javac LogLevelTestDemo.java
java LogLevelTestDemo
~~~

**stdout dự kiến, khi chạy bình thường với JDK 17:**

~~~text
PASS logger INFO
PASS handler WARNING
PASS inherit WARNING
PASS child overrides FINE
PASS handler filter INFO
PASS logger OFF
PASS logger ALL
ALL 7 TESTS PASSED
~~~

Không có timestamp, port, thread ID hoặc đường dẫn ngẫu nhiên. Nếu một test fail, chương trình ném **AssertionError** cùng expected/actual thay vì in PASS. Exit code khi đó khác 0.

### 6.3. Phân tích bảy ca

**Ca logger INFO:** FINE bị chặn tại logger, trước khi tới handler. INFO, WARNING, SEVERE vượt ngưỡng và được handler ALL giữ lại.

**Ca handler WARNING:** Logger FINE chấp nhận cả bốn event, nhưng handler chỉ ghi WARNING và SEVERE. Đây là ví dụ vì sao **Logger.isLoggable(Level.FINE)** không đủ để khẳng định đã có log ở sink.

**Ca inherit WARNING:** Child có level null và kế thừa từ parent WARNING, nên INFO/FINE không đi tiếp.

**Ca child overrides FINE:** Parent WARNING, child FINE. Parent handler ALL vẫn nhận được FINE của child khi parent handlers được bật, vì parent logger không lọc lại event theo level WARNING ở bước phân phối đó.

**Ca handler filter INFO:** Logger INFO chấp nhận INFO, WARNING, SEVERE. Handler filter chủ động loại message **info**, nên capture chỉ còn WARNING và SEVERE. Test này phân biệt **level filtering** với **filtering theo thuộc tính record**.

**Ca OFF:** Parent OFF, child không override, không event nào xuất hiện, kể cả SEVERE.

**Ca ALL:** Parent ALL và handler ALL, cả bốn event đều được chấp nhận.

### 6.4. Vì sao test có tính độc lập?

- Mỗi case tạo tên logger riêng với số thứ tự; không dùng root logger toàn ứng dụng.
- Parent và child được giữ trong biến cục bộ, không để mất quan hệ logger hierarchy trong khi chạy case.
- Parent có **setUseParentHandlers(false)** nên record không bị in thêm qua handler của root.
- Handler chỉ lưu level và message; không format ngày giờ hoặc phụ thuộc stdout/stderr của logging backend.
- Các lời gọi là đồng bộ một thread; không có queue hoặc concurrent writer.
- **finally** tháo handler và phục hồi level, useParentHandlers để tránh để lại cấu hình test.
- Test không sử dụng **assert** của Java; assertion luôn được kiểm tra khi chạy chương trình.

### 6.5. Giới hạn của ví dụ

Demo chứng minh ngưỡng của **JUL logger và JUL handler**. Nó không chứng minh rằng:

- Logback hoặc Log4j2 đang được ứng dụng dùng thật.
- ConsoleAppender/FileAppender của production xuất message.
- JSON encoder đúng schema hay dữ liệu đã được redacted.
- Async queue đã drain, file đã flush, collector đã nhận.
- Spring Boot active profile và override đúng.
- Một logger tên package khác cũng có chính sách như mong đợi.

Mỗi giới hạn cần test ở cấp phù hợp, không cố dùng một unit test để thay thế mọi kiểm thử integration.

## 7. JUnit 5 và cách test có cấu trúc

Trong dự án thật, nên dùng test runner như **JUnit Jupiter** kết hợp Maven/Gradle và CI.

Mẫu tổ chức:

~~~text
Arrange: tạo capture, đặt level và filter
Act:     gọi code gây sự kiện
Assert:  level, logger, message/fields, số lượng
Finally: detach/close capture, restore config
~~~

Nếu dùng JUL, có thể chuyển hàm check trong demo thành một test class JUnit 5 và thay AssertionError viết tay bằng **assertEquals(expected, actual)**.

Một unit test tốt thường **không ghi file thật** nếu mục tiêu chỉ là level. Test file/collector tách riêng giúp chạy nhanh và giảm flaky.

### 7.1. Kiểm thử Logback bằng ListAppender

Với dự án có **SLF4J + Logback Classic + JUnit 5**, Logback cung cấp **ListAppender**, một appender in-memory lưu các **ILoggingEvent**.

Ví dụ class test, đặt dưới test source root với tên **LogbackLevelTest.java**:

~~~java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class LogbackLevelTest {

    @Test
    void infoLoggerRejectsDebug() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                "tests.logging.orders.LevelProbe");

        Level oldLevel = logger.getLevel();
        ListAppender<ILoggingEvent> capture =
                new ListAppender<>();
        capture.start();
        logger.addAppender(capture);

        try {
            logger.setLevel(Level.INFO);

            logger.debug("debug-should-not-appear");
            logger.info("order-accepted");
            logger.warn("inventory-slow");

            assertEquals(2, capture.list.size());
            assertEquals(Level.INFO,
                    capture.list.get(0).getLevel());
            assertEquals("order-accepted",
                    capture.list.get(0).getFormattedMessage());
            assertEquals(Level.WARN,
                    capture.list.get(1).getLevel());
        } finally {
            logger.detachAppender(capture);
            capture.stop();
            logger.setLevel(oldLevel);
        }
    }
}
~~~

Đây là **class test có thể chạy trong project đã cấu hình dependencies**, không phải chương trình độc lập với classpath JDK. Kết quả dự kiến là **JUnit test PASS** khi Logback backend hoạt động và không có turbo filter/custom filter toàn cục thay đổi hành vi.

Điểm mạnh của ListAppender:

- Bắt được **ILoggingEvent** chứ không chỉ đọc text console.
- Kiểm tra **getLevel**, **getFormattedMessage**, **getLoggerName**.
- Khi có exception, kiểm tra **getThrowableProxy()** thay vì suy đoán chỉ từ chuỗi message.
- Không cần timestamp hoặc I/O file.
- Dễ kiểm tra message thực tế đã được format từ SLF4J placeholders.

**Giới hạn:** ListAppender gắn trực tiếp vào logger chưa bảo đảm event vượt qua appender/filter khác của production; test về **console threshold, file encoding, rotation, collector** phải thực hiện ở vị trí tương ứng.

### 7.2. Cleanup quan trọng hơn việc test chạy xanh một lần

Trong Logback, **setLevel(null)** có thể trả logger về chế độ kế thừa mức cha. Vì vậy lưu và phục hồi **oldLevel**, kể cả khi nó là null. Không để mức INFO/DEBUG vừa bật còn ảnh hưởng test khác.

Nếu test buộc sử dụng cùng logger với code production, cần bảo đảm không có test chạy song song nào đang thay level hoặc appender của logger đó. Có thể tạo logger tên riêng trong unit test, hoặc cô lập context cho integration test.

## 8. Kế thừa logger và Logback test configuration

Ví dụ **logback-test.xml** cho một dự án Logback (đây là XML cấu hình, không phải Java source):

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Test cần xác nhận:

- Logger con **com.example.orders.OrderService** chấp nhận DEBUG.
- Logger khác **com.example.payments.PaymentService** không chấp nhận DEBUG vì root INFO.
- INFO/WARN/ERROR có mặt tại CONSOLE nếu không có filter khác.
- Package gần giống **com.example.order** không tự nhận mức DEBUG.
- Một logger con có override thì hành vi theo override, không chỉ level của package cha.

### 8.1. Thêm appender threshold

Nếu CONSOLE được đặt một **ThresholdFilter** ở WARN:

~~~xml
<filter class="ch.qos.logback.classic.filter.ThresholdFilter">
    <level>WARN</level>
</filter>
~~~

Mảnh XML này **phải đặt bên trong appender hợp lệ**, không thể dùng một mình làm file config.

Khi đó logger orders vẫn có **effective level DEBUG**, nhưng CONSOLE không in DEBUG hoặc INFO. Test đọc effective level có thể PASS; test đầu ra console sẽ chỉ thấy WARN/ERROR. **Đây không phải mâu thuẫn**, mà là hai lớp lọc riêng.

### 8.2. Cẩn thận additivity

Nếu logger orders có appender riêng và **additivity=true**, event có thể tiếp tục lên appender của root. Test nên xác minh một event đến từng sink theo số bản ghi đã định. Nếu gắn cùng console appender nhiều cấp, có thể tạo dòng trùng.

Với **additivity=false**, logger con phải có appender phù hợp; nếu không, event có thể không tới đích nào dù level cho phép.

### 8.3. logback-test.xml khác production config

Logback có cơ chế tìm cấu hình khi chạy test và production. **logback-test.xml** trong test classpath có thể khiến test chạy với chính sách khác file **logback.xml** hoặc **logback-spring.xml** của ứng dụng triển khai.

Unit test kiểm tra logic với logback-test.xml không tự chứng minh runtime production đúng. Muốn xác minh production config, dùng integration/smoke test với **artifact, profile và dependency tương ứng**.

## 9. Log4j2: test LoggerConfig và AppenderRef

Với Log4j2, định tuyến và lọc có thể nằm ở **LoggerConfig**, filter của LoggerConfig, **AppenderRef** hoặc appender. Một cấu hình minh họa cho test là **log4j2-test.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.orders" level="debug"
                additivity="false">
            <AppenderRef ref="CONSOLE"/>
        </Logger>

        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Kỳ vọng:

- DEBUG tại **com.example.orders.OrderService** có thể đi đến CONSOLE.
- DEBUG tại **com.example.payments.PaymentService** bị chặn theo root INFO.
- Logger orders không gửi tiếp lên root vì additivity=false, nhưng đã có CONSOLE riêng nên có đích.
- INFO/WARN/ERROR được xử lý theo policy và filters nếu có.

Không dùng XML Logback rồi nghĩ Log4j2 sẽ hiểu tương tự mọi chi tiết. Khi test programmatic level change, cần API cập nhật context/config đúng với phiên bản Log4j2.

Nếu test dùng async loggers hoặc async appenders của Log4j2, **event đã được chấp nhận** có thể chưa được viết ngay. Chờ completion trong timeout thích hợp hoặc dùng appender test phù hợp, không dùng sleep ngẫu nhiên.

## 10. Spring Boot: test level theo profile và property sources

Spring Boot thường cho phép cấu hình:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
logging.level.com.example.payments=WARN
~~~

File này là **mẫu policy**, không phải giá trị mặc định bắt buộc. Có thể thay đổi theo các profile:

~~~properties
# application-dev.properties
logging.level.com.example.orders=DEBUG
~~~

~~~properties
# application-prod.properties
logging.level.com.example.orders=INFO
~~~

Khi chạy test, một property được nạp **chưa chắc là giá trị cuối** nếu còn nguồn có độ ưu tiên cao hơn như command-line override, environment variable hoặc runtime dynamic changes.

### 10.1. Kịch bản test profile

| Bối cảnh | Điều cần xác minh |
| --- | --- |
| dev | Package debug được phép có DEBUG, các package còn lại giữ mức chuẩn. |
| test | Không có DEBUG thừa từ thư viện và application ngoài phạm vi cần assert. |
| staging | Mức và sink gần chính sách production, khác biệt được phê duyệt. |
| prod | Root INFO; không có package bật DEBUG ngoài danh sách cho phép. |
| Thiếu profile | Base config an toàn và hành vi startup đúng quy ước. |
| Profile xung đột | Cấu hình hiệu lực được xác định; hệ thống phát hiện trường hợp sai nếu policy yêu cầu. |
| Runtime override | Mức thực thay đổi và được khôi phục đúng, có audit nếu cần. |

Một test dùng **@SpringBootTest(properties = "logging.level.com.example.orders=DEBUG")** có thể kiểm tra môi trường Spring, nhưng không nên chỉ assert:

~~~java
// Minh họa trong test có Spring Environment.
assertEquals("DEBUG",
        environment.getProperty(
                "logging.level.com.example.orders"));
~~~

Câu lệnh đó kiểm tra **giá trị property đọc được**, không chứng minh Logback/Log4j2/JUL thật sự xuất DEBUG ra appender. Test phải kiểm tra **effective level** ở backend và **event capture**.

### 10.2. Actuator loggers

Khi ứng dụng có Spring Boot Actuator và endpoint **/actuator/loggers** được bật/phơi bày, người có quyền phù hợp có thể xem và thay đổi level tại runtime.

Nếu kiểm thử:

1. Bảo vệ endpoint, không mở công khai.
2. Đọc level ban đầu.
3. Bật DEBUG tạm thời ở một package đã được phép.
4. Xác nhận DEBUG xuất hiện qua appender mục tiêu.
5. Trả level về ban đầu bằng finally/cleanup.
6. Xác minh package khác không bị tác động.
7. Không chạy song song test khác sửa cùng logging context.

**Không dùng production làm nơi kiểm thử cấp quyền bật DEBUG** nếu có thể ghi thông tin nhạy cảm hoặc tăng volume. Dùng môi trường thử được kiểm soát.

## 11. Testing có hai chiều: positive và negative

**Positive assertion:** event ở mức cho phép được capture, ví dụ **INFO:order-created**.

**Negative assertion:** event ở mức thấp hơn ngưỡng không xuất hiện, ví dụ **DEBUG:validation-details**.

Cả hai cần cùng một test harness hoặc cùng đường ghi đã xác minh. Nếu chỉ có negative assertion, test có thể PASS vì appender bị gỡ hoàn toàn.

Ví dụ policy logger INFO với event:

~~~text
DEBUG validation.details
INFO  order.accepted
WARN  inventory.slow
ERROR dependency.unavailable
~~~

Test cần xác nhận:

- DEBUG không có.
- INFO/WARN/ERROR có.
- Không có duplicate ngoài thiết kế.
- Level và logger name của từng event đúng.
- Trường hợp ERROR có exception, throwable/cause được giữ nếu policy yêu cầu.

### 11.1. Tránh test brittle

Nên assert các thuộc tính ổn định:

- Event level chính xác.
- Logger name và event name.
- Stable error code.
- Số lần event xuất hiện trong một test-case đã xác định.
- Có/không có Throwable.
- Structured fields quan trọng và sự vắng mặt của dữ liệu nhạy cảm.

Hạn chế assert:

- Timestamp tuyệt đối.
- Số dòng stack trace.
- Thread ID phụ thuộc môi trường.
- Toàn bộ message ngôn ngữ tự nhiên dễ thay đổi.
- Thứ tự toàn cục giữa các threads khác nhau.
- Khoảng trắng trong layout khi format không thuộc contract.

Đừng viết test phụ thuộc vào log từ các thư viện ngoài nếu mình không sở hữu format/level của chúng và không có hợp đồng ổn định.

## 12. Kiểm thử log exception và severity

**Loại exception Java không tự quyết định log level.** Một business conflict bình thường có thể được log INFO/WARN; một lỗi hệ thống chưa xử lý có thể được log ERROR; một attempt retry tạm thời không nhất thiết nên ghi ERROR.

Ví dụ:

~~~java
// Minh họa, cần SLF4J logger, orderId và Throwable trong ứng dụng.
logger.error("Order failed, id={}", orderId, exception);
~~~

Nếu ứng dụng dùng Logback, test có thể xác nhận:

- Event ở **ERROR**.
- Logger name đúng.
- **ILoggingEvent.getThrowableProxy()** không null khi cần cause.
- Không có ba stack trace cho cùng failure chain do service/controller/advice cùng log rồi throw.
- Event được ghi tại boundary thích hợp.

Với JUL, dùng **LogRecord.getThrown()** để kiểm tra Throwable đã được đính kèm. Chỉ assert text từ **exception.getMessage()** không chứng minh stack/cause đã được giữ.

Một error record ở level ERROR không có nghĩa HTTP response phải là 500, và HTTP 404 cũng không buộc log ERROR. **HTTP status, business outcome và log severity là ba chiều khác nhau**.

## 13. Kiểm thử console, file và stderr đúng cách

Trong JUL, **ConsoleHandler thường ghi System.err**. Logback hoặc Log4j2 ConsoleAppender có thể ghi stdout hoặc stderr theo cấu hình.

Nếu test chỉ redirect System.out, bạn có thể không bắt được JUL log. Nếu appender giữ tham chiếu tới stream cũ được khởi tạo trước khi redirect, thay System.out sau đó vẫn có thể không tác dụng.

**Cách chọn đúng công cụ:**

- Test level: gắn **in-memory Handler/ListAppender**.
- Test formatter: dùng appender test với encoder/formatter mục tiêu.
- Test console: xác định rõ stdout hay stderr, thời điểm appender được khởi tạo.
- Test file: dùng thư mục tạm riêng, close/flush trước khi đọc file.
- Test collector: dùng integration environment và event ID riêng.
- Test async: chờ completion bằng condition/latch có timeout.

Không đổi **System.out/System.err** toàn JVM ở các test chạy song song mà thiếu isolation; việc này có thể làm mất output của test khác.

## 14. Async logging và thời điểm assertion

Trong async logging, lời gọi logger có thể được enqueue trước khi worker viết event:

~~~text
Test thread                  Worker thread
-----------                  -------------
logger.info("created")
assert 1 event   ← có thể quá sớm
                             dequeue
                             appender ghi
~~~

Nếu test assert ngay, kết quả có thể **flaky**, nhất là khi CI chịu tải.

Nên:

1. Chọn điểm capture mà bạn thực sự muốn đo.
2. Chờ **CountDownLatch** hoặc một điều kiện đã được test appender báo, có timeout giới hạn.
3. Không dùng Thread.sleep(1000) làm bằng chứng worker đã hoàn tất.
4. Nếu test shutdown, stop context/appender theo lifecycle đúng và kiểm tra queue được drain.
5. Test queue overflow/drop riêng, không trộn vào test đơn giản về level.
6. Dọn worker, appender và logging context sau test.

**Một sự kiện không xuất hiện trong timeout** có thể do queue chưa drain, appender lỗi hoặc bị drop, không tự chứng minh logger level quá cao. Muốn kết luận, cần metric hoặc kiểm tra từng tầng.

## 15. Test isolation và cleanup

Logger và logging backend thường là tài nguyên **có trạng thái chung trong một JVM/classloader**. Một test bật root DEBUG có thể làm mọi test khác in thêm log. Một Handler/Listener không được tháo có thể khiến event xuất hiện hai lần.

Bảng trạng thái cần phục hồi:

| Trạng thái | Việc cần làm |
| --- | --- |
| Logger level | Lưu giá trị cũ, restore kể cả null. |
| Root/package appender | Gỡ chỉ appender test tự gắn; không xóa appender framework sở hữu. |
| Handler level/filter | Dùng instance riêng và close đúng cách. |
| Parent handlers/additivity | Restore giá trị trước test. |
| MDC / ThreadContext | Xóa hoặc restore các key mà test đã thêm. |
| Async queue/context | Stop/drain ở đúng thời điểm, tránh giữ thread sống. |
| System properties | Restore nếu test đã thay. |
| File output | Dùng path tạm riêng, cleanup. |
| Runtime level override | Trả lại level sau test, không để lại DEBUG. |

Với JUnit 5, có thể dùng **@AfterEach**, nhưng **finally** ngay trong test thường bảo đảm cleanup kể cả khi assertion ném lỗi. Khi test cần thay root/global LogManager, hãy tách execution hoặc dùng cơ chế resource lock của test framework; không giả định hai test thay global logging có thể chạy song song an toàn.

## 16. Level theo package và logger name thực tế

Giả sử Spring Boot có:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
~~~

Test:

- **com.example.orders.OrderService** có DEBUG.
- **com.example.orders.validation.Validator** có DEBUG.
- **com.example.payments.PaymentService** không có DEBUG.
- **com.example.order.OrderService** (khác orders) không tự được áp dụng rule.
- Một class dùng LoggerFactory.getLogger("business") không tự thuộc nhánh orders.
- Logger do library tạo có thể dùng namespace tùy ý.

Không suy ra logger hierarchy từ file Java nếu code tạo logger bằng một string tên tùy ý. Khi test không thấy event, **in hoặc kiểm tra logger name thực** ở capture.

## 17. Bảo mật: tắt DEBUG không đủ để bảo vệ secrets

DEBUG/TRACE thường có nhiều dữ liệu chẩn đoán, nên kiểm thử level ở production góp phần giảm nguy cơ lộ dữ liệu. Nhưng không được xem đây là biện pháp duy nhất.

Những thông tin không nên đưa vào log ở mọi level:

- Password, API keys, bearer tokens, session cookies.
- Raw request/response body chứa PII.
- Thông tin thanh toán hoặc bí mật tích hợp.
- SQL parameters chứa thông tin người dùng không cần thiết.
- Exception message từ API bên ngoài không được đánh giá.
- Dữ liệu người dùng chứa CR/LF có thể tạo **log injection** trong text layout.

Một privacy test nên dùng **dữ liệu giả** như dummy-token-for-test, bật DEBUG trong môi trường cô lập, rồi xác nhận output **không chứa token giả thô** sau encoder. Chỉ kiểm tra ở logger INFO khi DEBUG đang tắt có thể bỏ qua vấn đề thật khi operator tạm bật DEBUG.

Mẫu kiểm tra:

- Dữ liệu nhạy cảm không xuất hiện trong INFO/WARN/ERROR.
- Khi DEBUG bật có chủ đích, redaction vẫn hoạt động.
- MDC/correlation ID được validate; input chứa CRLF không tạo event giả.
- Event log đúng environment/sink, không gửi dữ liệu thử sang production.
- Test đã tắt/gỡ các level overrides sau khi hoàn tất.

## 18. Xác minh logging ở môi trường triển khai

Một unit test trên máy developer không chứng minh **cấu hình runtime production** đúng. Các nguồn cấu hình khác nhau có thể ghi đè nhau:

- logback-test.xml trong test classpath.
- logback.xml, logback-spring.xml hoặc log4j2.xml trong artifact.
- application-dev.yml, application-prod.yml.
- Environment variables như **LOGGING_LEVEL_ROOT**.
- JVM system properties hoặc command-line overrides.
- Dynamic level changes từ endpoint quản trị.

Smoke test nên xác minh:

1. Application đang sử dụng **đúng backend/provider**.
2. Active environment/profile đã được chọn đúng.
3. Effective root/package levels sau startup khớp policy.
4. DEBUG không xuất ở package khác.
5. WARN/ERROR quan trọng còn được ghi qua appender mục tiêu.
6. Đích/namespace collector đúng environment.
7. Nếu runtime level thay đổi, khả năng trở lại policy ban đầu có thể kiểm chứng.

**Không thử bật DEBUG trực tiếp trên production chỉ để chứng minh test**, vì có thể gây log flooding hoặc lộ thông tin. Sử dụng staging/test đã được cấp quyền.

## 19. Các lỗi test thường gặp

**1. Chỉ đọc Logger.getLevel().** Với logger kế thừa, getLevel có thể null; phải xét effective level hoặc hành vi thực tế.

**2. Không có positive control.** Test "DEBUG không xuất" pass dù logging tắt toàn bộ.

**3. Quên handler/appender threshold.** Logger DEBUG không chắc sink cũng nhận DEBUG.

**4. Quên filter.** Event có thể bị loại do marker/message/MDC dù level cho phép.

**5. Nhầm root INFO chặn lại mọi DEBUG của con.** Trong JUL/Logback, sự kiện đã được con chấp nhận có thể tới handler/appender của cha qua propagation.

**6. Bật root DEBUG để test một package.** Dễ ảnh hưởng test khác và tạo nhiều log không cần thiết.

**7. Không restore level/appender.** Làm test sau flaky hoặc có log trùng.

**8. Assert stdout khi backend ghi stderr.** Không thấy log không có nghĩa logger filter đúng.

**9. Dùng Thread.sleep cho async.** Kết quả không ổn định giữa local và CI.

**10. Test file cấu hình test rồi khẳng định production đúng.** Cần smoke test artifact/runtime thật.

**11. So sánh stack trace/timestamp chính xác tuyệt đối.** Dễ gãy khi đổi JDK, thread, pattern.

**12. Không kiểm tra package con hoặc tên tương tự.** Dễ cấu hình DEBUG quá rộng.

**13. Đếm log ERROR như số request lỗi.** Một lỗi có thể được log nhiều lần ở nhiều tầng hoặc bị sampling/drop.

**14. Không gắn Throwable trong test ERROR.** Bài kiểm tra text pass nhưng mất cause cần điều tra.

**15. Chạy song song nhiều test sửa cùng logger.** Gây race và kết quả khó tái lập.

**16. Không xác minh SLF4J provider.** Có API nhưng không có backend phù hợp, test không thấy log.

**17. Xem ListAppender là chứng nhận durability.** Nó chỉ capture trong RAM.

**18. Mặc định mọi 4xx phải log WARN/ERROR.** HTTP status và log level khác nhau.

**19. Không test hành vi override runtime.** Một biến môi trường có thể bật DEBUG ngoài ý muốn dù file prod nói INFO.

**20. Dùng secrets thật làm dữ liệu test.** Luôn dùng chuỗi giả và test chống lộ dữ liệu.

## 20. Checklist review bài test logging

Trước khi merge một test log level, hãy kiểm tra:

- [ ] Test xác định đúng backend và logger name.
- [ ] Test biết configured level hay effective level đang được kiểm tra.
- [ ] Có **positive assertion** cho sự kiện phải được ghi.
- [ ] Có **negative assertion** cho mức phải bị chặn.
- [ ] Có xét handler/appender threshold và filter nếu ảnh hưởng đến kỳ vọng.
- [ ] Có xác định routing qua parent handlers/additivity.
- [ ] Nếu capture message, kiểm tra đúng formatted/original message theo mục tiêu.
- [ ] Nếu test exception, kiểm tra level và Throwable/cause.
- [ ] Test không phụ thuộc timestamp/stack line/thread order không ổn định.
- [ ] Async test có completion condition và timeout.
- [ ] Cleanup logger level, filter, appender/handler, MDC, stream và file tạm.
- [ ] Test không đụng root/global logger cùng lúc với test khác.
- [ ] Profile và runtime overrides được test nếu policy môi trường là yêu cầu.
- [ ] Không đưa secret/PII vào dữ liệu kiểm thử.
- [ ] Có integration/smoke test riêng khi mục tiêu là file/collector thật.

## 21. Bài tập thực hành

1. Chạy **LogLevelTestDemo.java**, ghi lại bảy dòng PASS và giải thích từng ca.
2. Đổi logger INFO thành WARNING nhưng giữ expected cũ. Test nào fail và actual còn những event nào?
3. Đổi Handler WARNING thành ALL ở ca 2. Vì sao FINE và INFO xuất hiện thêm?
4. Trong ca child override, đặt level con thành INFO. Vì sao parent WARNING không tự chặn event INFO đã được con chấp nhận và chuyển tới handler ALL?
5. Thêm JUL CONFIG ở logger INFO; dự đoán CONFIG có xuất hiện không và vì sao.
6. Đặt setUseParentHandlers(false) ở child. Handler gắn ở parent có còn nhận event không?
7. Thay filter ở ca 5 thành loại WARNING. Expected mới là gì?
8. Tạo JUnit test Logback với ListAppender, chuyển logger sang DEBUG rồi xác nhận event DEBUG xuất hiện. Phải restore gì trong finally?
9. Thêm ThresholdFilter WARN vào CONSOLE trong logback-test.xml. Vì sao đọc effective level có thể cho kết quả khác output?
10. Tạo logger com.example.order và com.example.orders; kiểm tra không nhầm rule theo package.
11. Thiết kế một async test dùng CountDownLatch thay cho Thread.sleep để xác nhận appender nhận event.
12. Lập smoke test production profile: root INFO, một package DEBUG có phê duyệt, các package khác không phát DEBUG; kiểm tra đúng provider, đích log và redaction.

## 22. Tổng kết

**Kiểm thử log level là kiểm thử kết quả lọc và định tuyến sự kiện**, không chỉ xem một dòng cấu hình. Có ba quy tắc quan trọng:

1. **Effective logger level** quyết định event có vượt qua logger nguồn; logger con có thể kế thừa hoặc override cha.
2. **Handler/appender threshold, filter và propagation** quyết định event đã được chấp nhận sẽ đi đâu và có bị chặn thêm hay không.
3. **Positive + negative assertions, cô lập trạng thái và cleanup** giúp test đáng tin; với async, file, collector và runtime config cần integration test tương ứng.

Ví dụ Java 17 sử dụng JUL giúp nhìn rõ các ngưỡng độc lập. Với Logback dùng ListAppender và JUnit; với Log4j2 hay Spring Boot phải xác minh backend/config thực chạy. Đừng để một test "không thấy DEBUG" che lấp lỗi nghiêm trọng hơn: **toàn bộ logging không hoạt động hoặc WARN/ERROR cũng bị mất**.

### Tài liệu tham khảo

- Java SE 17 Level: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html
- Java SE 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Java SE 17 Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- Logback architecture và additivity: https://logback.qos.ch/manual/architecture.html
- Logback filters: https://logback.qos.ch/manual/filters.html
- Logback configuration: https://logback.qos.ch/manual/configuration.html
- Logback ListAppender source: https://logback.qos.ch/xref/ch/qos/logback/core/read/ListAppender.html
- Log4j2 configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Log4j2 filters: https://logging.apache.org/log4j/2.x/manual/filters.html
- Spring Boot logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot Actuator Loggers: https://docs.spring.io/spring-boot/reference/actuator/loggers.html
- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html