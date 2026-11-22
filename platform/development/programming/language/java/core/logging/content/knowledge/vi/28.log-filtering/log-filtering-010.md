# Kiểm thử filter trong hệ thống logging Java

## 1. Vì sao phải kiểm thử filter?

Logging filter quyết định **sự kiện log nào được chuyển tiếp hoặc bị loại** theo level, nguồn phát, marker, MDC, nội dung hoặc chính sách riêng của ứng dụng. Một cấu hình filter sai có thể khiến log quan trọng biến mất, log chẩn đoán tràn ngập hệ thống hoặc thông tin nhạy cảm xuất hiện ở nơi không được phép.

Ví dụ: một dịch vụ muốn loại log kiểm tra sức khỏe định kỳ mang `channel=health` nhưng vẫn giữ sự kiện nghiệp vụ mang `channel=orders`. Mục tiêu kiểm thử là xác nhận đúng **sự kiện được nhận ở appender**, không chỉ xác nhận phương thức tính điều kiện của filter trả về một giá trị.

Trong Java, không có một cơ chế filter logging duy nhất cho mọi thư viện:

- **`java.util.logging` (JUL)** có `java.util.logging.Filter` với `isLoggable(LogRecord)` và cơ chế level/handler của riêng nó.
- **SLF4J** là facade. Trong ví dụ thực hành, **Logback** là backend thực thi logger, appender và `Filter<ILoggingEvent>`.
- **Log4j2** có filter và cơ chế đánh giá riêng; không sử dụng trực tiếp class Logback khi ứng dụng dùng Log4j2.

Bài này lấy **SLF4J + Logback** làm mô hình kiểm thử cụ thể, sau đó nêu cách áp dụng nguyên tắc tương tự cho JUL, async logging và cấu hình nhiều môi trường.

### Một sự kiện log đi qua những đâu?

```text
Code nghiệp vụ
    |
    v
logger.info(...), logger.debug(...)
    |
    v
Quyết định ở logger (level, có thể TurboFilter của Logback)
    |  -- bị từ chối --> không tạo/chuyển sự kiện
    v
Sự kiện ILoggingEvent
    |
    v
Appender A -- filter A --> sink A (console/file/collector)
    |
    +----> Appender B -- filter B --> sink B
```

Có thể có nhiều appender cùng nhận một sự kiện. Một filter gắn trên appender A chỉ chi phối việc ghi ở **A**; nó không tự ngăn appender B. Khi filter ở vị trí khác nhau trong pipeline, đối tượng được test và điều kiện chờ sự kiện cũng khác nhau.

## 2. Hiểu đúng level và bộ lọc ba kết quả

Đừng nhầm **ngưỡng logger** với **filter trên appender**.

- Ngưỡng logger kiểm tra event có đủ điều kiện để logger phát không. Ví dụ logger `WARN` thông thường không tạo/chuyển event `INFO`.
- Filter trên appender chạy sau khi sự kiện tới appender. Nó có thể loại event ở đúng sink này, kể cả khi logger đã cho qua.
- Một Logback `TurboFilter` được hỏi sớm hơn trong quá trình quyết định bật/tắt logging. TurboFilter có thể tác động đến kiểm tra level, vì vậy cần kiểm thử riêng nếu ứng dụng dùng nó.

Với `ch.qos.logback.core.filter.Filter`, phương thức `decide(event)` trả về một trong ba giá trị `FilterReply`:

| Kết quả | Ý nghĩa trong chuỗi filter của một appender | Kỳ vọng kiểm thử |
| --- | --- | --- |
| `DENY` | Bác bỏ event tại appender đó | Sink không nhận event |
| `NEUTRAL` | Chưa quyết định; xét filter tiếp theo | Không tự xác định accept/drop |
| `ACCEPT` | Chấp nhận event và kết thúc xét các filter còn lại của appender đó | Nếu đã đến appender hoạt động, sink nhận event |

Nếu tất cả filter trả `NEUTRAL`, appender tiếp tục xử lý event theo cơ chế mặc định. **`ACCEPT` của appender filter không thể hồi sinh event đã bị logger level chặn trước khi tới appender.** Ngược lại, trong Logback, quyết định `ACCEPT` của **TurboFilter** ở tầng sớm có thể thay đổi cách đánh giá ngưỡng logger, vì vậy không được suy luận từ appender filter sang TurboFilter.

Thứ tự filter là một phần của hợp đồng: gặp `DENY` hoặc `ACCEPT` thì không xét tiếp các filter sau ở cùng chuỗi; gặp `NEUTRAL` thì tiếp tục. Không nên thiết kế filter dựa vào side effect vì filter sau có thể không được gọi.

## 3. Lập ma trận test từ yêu cầu thật

Giả sử yêu cầu là **không ghi log kiểm tra sức khỏe định kỳ ở một appender, còn các log khác được giữ lại**. Quy tắc Logback được chọn:

```text
event.MDC["channel"] == "health"  -> DENY
các trường hợp khác               -> NEUTRAL
```

Một ma trận test tối thiểu:

| Case | Level logger | MDC `channel` | Level event | Filter trả | Event có ở sink? |
| --- | --- | --- | --- | --- | --- |
| 1 | `DEBUG` | `health` | `INFO` | `DENY` | Không |
| 2 | `DEBUG` | `orders` | `INFO` | `NEUTRAL` | Có |
| 3 | `DEBUG` | không có khóa | `WARN` | `NEUTRAL` | Có |
| 4 | `WARN` | bất kỳ | `INFO` | filter có thể không được gọi | Không |
| 5 | `WARN` | bất kỳ | `WARN` | `NEUTRAL/ACCEPT` theo filter | Có |
| 6 | `INFO` | bất kỳ | `DEBUG` | không tới appender filter thông thường | Không |

Ngoài đường đi thông thường, cần xem các trường hợp biên: MDC map trống, khóa không tồn tại, giá trị rỗng hoặc sai chữ hoa/thường, filter kết hợp, thay đổi cấu hình, nhiều thread và lỗi của appender. Không thêm ngầm chính sách bỏ mọi chuỗi như `healthcheck` nếu quy tắc chỉ so giá trị chính xác `health`.

Các assertion nên bám vào **đầu ra quan sát được** và mức tương tác phù hợp. Unit test một `decide(...)` nhanh và dễ phân tích, nhưng integration test qua logger/appender mới xác nhận filter đã được gắn đúng chỗ.

## 4. Ví dụ Java 17 + JUnit 5: kiểm tra filter trên Logback appender

Ví dụ tự chứa trong một dự án Maven nhỏ, dùng Java 17, Logback và JUnit Jupiter. Test sử dụng appender trong bộ nhớ nên không phụ thuộc console, file, timestamp hoặc lịch thực thi của hệ điều hành.

### 4.1. Cấu trúc và dependencies

```text
logging-filter-test/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── LoggingFilterTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>logging-filter-test</artifactId>
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

Các phiên bản trên phục vụ ví dụ có thể tái lập, không có ý khẳng định là phiên bản mới nhất. Dự án thật nên sử dụng dependency management thống nhất và tránh đưa hai SLF4J provider cạnh tranh vào classpath.

### 4.2. Test filter và chuỗi quyết định

Tạo `src/test/java/example/LoggingFilterTest.java`:

```java
package example;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.*;

class LoggingFilterTest {

    // Chỉ loại event có MDC channel = health.
    static final class DenyHealthFilter extends Filter<ILoggingEvent> {
        @Override
        public FilterReply decide(ILoggingEvent event) {
            String channel = event.getMDCPropertyMap().get("channel");
            return "health".equals(channel)
                    ? FilterReply.DENY
                    : FilterReply.NEUTRAL;
        }
    }

    static final class AcceptAllFilter extends Filter<ILoggingEvent> {
        @Override
        public FilterReply decide(ILoggingEvent event) {
            return FilterReply.ACCEPT;
        }
    }

    static final class DenyAllFilter extends Filter<ILoggingEvent> {
        @Override
        public FilterReply decide(ILoggingEvent event) {
            return FilterReply.DENY;
        }
    }

    // Sink của test chỉ lưu event đã qua mọi filter của appender.
    static final class MemoryAppender extends AppenderBase<ILoggingEvent> {
        private final CopyOnWriteArrayList<ILoggingEvent> events =
                new CopyOnWriteArrayList<>();

        @Override
        protected void append(ILoggingEvent event) {
            event.prepareForDeferredProcessing();
            events.add(event);
        }

        List<ILoggingEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    // Mỗi test nhận logger riêng; appender được gỡ khi kết thúc.
    static final class Rig implements AutoCloseable {
        final Logger logger;
        final MemoryAppender sink;

        @SafeVarargs
        Rig(Level level, Filter<ILoggingEvent>... filters) {
            LoggerContext context =
                    (LoggerContext) LoggerFactory.getILoggerFactory();
            logger = context.getLogger(
                    "example.logging.filter." + UUID.randomUUID());
            logger.setLevel(level);
            logger.setAdditive(false);

            sink = new MemoryAppender();
            sink.setContext(context);
            sink.setName("memory-" + UUID.randomUUID());

            for (Filter<ILoggingEvent> filter : filters) {
                filter.setContext(context);
                filter.start();
                sink.addFilter(filter);
            }
            sink.start();
            logger.addAppender(sink);
        }

        @Override
        public void close() {
            logger.detachAppender(sink);
            sink.stop();
        }
    }

    @Test
    void deniesHealthButKeepsBusinessAndMissingMdc() {
        Map<String, String> before = MDC.getCopyOfContextMap();
        try (Rig rig = new Rig(Level.DEBUG, new DenyHealthFilter())) {
            MDC.put("channel", "health");
            rig.logger.info("health probe ok");

            MDC.put("channel", "orders");
            rig.logger.info("order accepted {}", 42);

            MDC.remove("channel");
            rig.logger.warn("retry scheduled");

            List<ILoggingEvent> events = rig.sink.snapshot();
            assertEquals(2, events.size());

            assertEquals(
                    List.of("order accepted 42", "retry scheduled"),
                    events.stream()
                            .map(ILoggingEvent::getFormattedMessage)
                            .toList());

            assertEquals(Level.INFO, events.get(0).getLevel());
            assertEquals(Level.WARN, events.get(1).getLevel());
            assertEquals("orders",
                    events.get(0).getMDCPropertyMap().get("channel"));
            assertFalse(
                    events.get(1).getMDCPropertyMap().containsKey("channel"));
        } finally {
            if (before == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(before);
            }
        }
    }

    @Test
    void appenderAcceptCannotUndoLoggerLevel() {
        try (Rig rig = new Rig(Level.WARN, new AcceptAllFilter())) {
            rig.logger.info("not created for this appender");
            rig.logger.warn("visible warning");

            assertEquals(
                    List.of("visible warning"),
                    rig.sink.snapshot().stream()
                            .map(ILoggingEvent::getFormattedMessage)
                            .toList());
        }
    }

    @Test
    void acceptStopsRemainingAppenderFilters() {
        // ACCEPT ở filter đầu chấm dứt chuỗi: DenyAll không được áp dụng.
        try (Rig rig = new Rig(
                Level.INFO, new AcceptAllFilter(), new DenyAllFilter())) {
            rig.logger.info("accepted first");
            assertEquals(
                    List.of("accepted first"),
                    rig.sink.snapshot().stream()
                            .map(ILoggingEvent::getFormattedMessage)
                            .toList());
        }
    }
}
```

Chạy tại thư mục `logging-filter-test` với JDK 17 trở lên và Maven:

```bash
mvn test
```

Kết quả mong đợi là **3 test thành công** và Maven báo `BUILD SUCCESS`. Thời gian chạy, dòng Maven tải dependency và định dạng chi tiết của báo cáo không cố định; xem `target/surefire-reports/` khi một assertion thất bại.

### 4.3. Đọc kết quả test

**Test 1 — lọc theo MDC:** Lệnh log mang `channel=health` bị `DenyHealthFilter` loại trước khi vào `MemoryAppender.append(...)`. Hai event còn lại tồn tại đúng thứ tự, đúng level và message, và có/không có trường MDC phù hợp. Việc dùng `"health".equals(channel)` an toàn cả khi khóa `channel` không hiện diện.

**Test 2 — level của logger:** Logger `WARN` loại lệnh `INFO` trước khi appender filter `AcceptAllFilter` có cơ hội can thiệp. Một appender filter trả `ACCEPT` không vượt qua được tầng kiểm tra level trước đó.

**Test 3 — thứ tự filter:** `AcceptAllFilter` đứng trước `DenyAllFilter`; sau quyết định `ACCEPT`, appender không cần gọi filter sau. Test xác minh **event được ghi**, tức kết quả quan sát được của chuỗi filter.

**Tại sao test này ổn định?** Appender là sink trong bộ nhớ hoạt động đồng bộ với lời gọi logger; test đọc dữ liệu sau khi lệnh logger trả về. `CopyOnWriteArrayList` bảo đảm việc thu thập an toàn nếu sau này có nhiều producer; đây là lựa chọn phù hợp cho test chức năng nhỏ, không phải collector tốt cho benchmark tải lớn. Logger được đặt tên riêng và `additive=false` để không bị root appender trộn event của các test khác. `try-with-resources` luôn gỡ appender; phần MDC được khôi phục trong `finally`.

**Giới hạn ví dụ:** code kiểm tra appender filter của Logback. Nó không chứng minh filter cấu hình trong file thật đã được kích hoạt, không thử gửi log qua mạng và không đo độ trễ của async logging. Những yêu cầu đó cần integration test phù hợp.

## 5. Đọc trực tiếp giá trị trả về: unit test của chính sách filter

Nếu logic lọc có nhiều nhánh (ví dụ điều kiện theo message, marker, user type hoặc cấu hình), unit test `decide(...)` giúp kiểm tra các ca biên nhanh hơn integration test toàn logging pipeline.

Nhưng test gọi `decide` chỉ xác minh **quy tắc**, chưa chứng minh filter được gắn vào đúng appender, đúng thứ tự, hoặc một log đã vượt qua level/encoder. Hãy kết hợp:

1. **Unit test:** kiểm tra bảng đầu vào → `DENY/NEUTRAL/ACCEPT`, kể cả null, chuỗi trống, chữ hoa/thường, cấu hình thiếu.
2. **Integration test với in-memory appender:** kiểm tra chính logger phát các event mong đợi, đúng số lượng, level, MDC và message.
3. **Configuration test:** khởi tạo context từ cấu hình thật, kiểm tra logger/appender/filter hiệu lực.
4. **End-to-end test:** nếu yêu cầu liên quan collector hoặc file, tạo môi trường/sink thử riêng và xác nhận đầu ra cuối.

Không gắn assertion vô nghĩa kiểu “`decide` trả `DENY` nên mọi appender trong ứng dụng không nhận log”. Một appender khác không có filter đó vẫn có thể ghi sự kiện.

### Các trường hợp biên đáng thử

- MDC map không có khóa, giá trị `""`, khoảng trắng hoặc khác chữ hoa/thường: cần xác nhận luật chuẩn hóa hoặc so sánh chính xác.
- Filter phụ thuộc message đã format: phân biệt `event.getMessage()` (template) và `event.getFormattedMessage()` (đã thay tham số) ở thời điểm filter chạy.
- Quy tắc sử dụng marker: kiểm tra marker được gắn đúng vào sự kiện và cách xử lý khi không có marker.
- Nhiều filter: một `NEUTRAL` chuyển tiếp, `ACCEPT` và `DENY` kết thúc; thay thứ tự có thể thay kết quả.
- Logger level không phù hợp: event có thể không đến filter; không suy ra bug trong filter chỉ vì counter số lần `decide(...)` không tăng.
- Nhiều appender: một sự kiện có thể được nhận bởi file appender nhưng bị loại ở console appender.
- Appender chưa `start()` hoặc đã `stop()`: không coi việc không thấy event là bằng chứng filter hoạt động chính xác.

## 6. Test filter khai báo trong cấu hình Logback

Nhiều ứng dụng không tạo filter bằng code mà khai báo trong `logback.xml` hoặc `logback-spring.xml`. Cần kiểm tra **cấu hình thực sự đang hoạt động**, vì class tên đúng nhưng chưa được gắn vào appender thì chính sách không có hiệu lực.

Ví dụ `logback.xml` chỉ cho console nhận event từ `WARN` trở lên, trong khi logger gốc cho phép từ `INFO`:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <pattern>%-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Với cấu hình này:

- `logger.info("ready")` được logger gốc cho phép, nhưng `ThresholdFilter` tại `CONSOLE` từ chối event dưới `WARN`.
- `logger.warn("retry")` và `logger.error("failed")` được console nhận, trừ khi có filter khác.
- Nếu tồn tại thêm file appender không gắn `ThresholdFilter`, file đó có thể vẫn ghi `INFO`.

Một loại filter khác là `LevelFilter`, dùng so sánh **một level cụ thể** và phản hồi phù hợp:

```xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>INFO</level>
    <onMatch>DENY</onMatch>
    <onMismatch>NEUTRAL</onMismatch>
</filter>
```

Đặt filter này trong appender sẽ loại **đúng mức INFO**, nhưng không tự loại `DEBUG` hoặc `WARN`; những mức đó vẫn phụ thuộc ngưỡng logger và các filter khác. Khác với `ThresholdFilter`, nó không phải là cách biểu diễn ngưỡng tối thiểu.

### Kiểm tra cấu hình mà không làm nhiễu toàn bộ test suite

Một test cấu hình độc lập có thể:

1. Tạo một `LoggerContext` dành riêng cho test.
2. Dùng công cụ cấu hình Logback của phiên bản đang dùng để nạp `logback.xml` thử nghiệm.
3. Gắn appender thu sự kiện hoặc đọc thông tin filter/level hiệu lực trong context đó.
4. Gửi `INFO/WARN/ERROR` và xác nhận đúng sink.
5. `stop()` context trong `finally`, không thay đổi root logger/context toàn cục đang phục vụ các test khác.

Khi dùng `logback-spring.xml` có thẻ `<springProfile>`, việc nạp bằng bộ parser Logback thuần có thể không hiểu phần mở rộng Spring Boot. Với trường hợp đó, dùng integration test khởi động ứng dụng Spring Boot với `@ActiveProfiles("test")` (hoặc profile cần thử), rồi kiểm tra level, appender và filter hiệu lực. Chỉ kiểm tra `Environment.getActiveProfiles()` chưa đủ để khẳng định log cuối cùng đã được lọc đúng.

Nếu ứng dụng có khả năng thay level hoặc filter ở runtime, tạo test riêng cho trạng thái trước–sau và khôi phục toàn bộ cài đặt đã thay; tránh để các test sửa cùng một root logger song song.

## 7. TurboFilter và khác biệt về thời điểm đánh giá

Logback `TurboFilter` được gọi sớm hơn appender filter, có thể quyết định trước khi sự kiện được tạo. Nó có thể giúp tránh chi phí tạo event với các log chắc chắn sẽ bị bỏ, hoặc áp dụng chính sách toàn context.

Để test TurboFilter, cần kiểm tra các tình huống riêng:

| Điều kiện | Kỳ vọng cần xác minh |
| --- | --- |
| TurboFilter trả `DENY` | Lời gọi log không đi tới appender, kể cả level thông thường cho phép |
| TurboFilter trả `NEUTRAL` | Logback tiếp tục quyết định theo ngưỡng level thông thường |
| TurboFilter trả `ACCEPT` | Logback có thể cho phép event dù ngưỡng logger thông thường không đủ |
| TurboFilter sử dụng marker/MDC | Điều kiện lấy đúng context tại **thread gọi logger** |
| Một TurboFilter đứng trước filter khác | Kết quả cuối và thứ tự quyết định phù hợp với chuỗi được cấu hình |

Điều này khác với `ACCEPT` của **appender filter** trong Test 2. Một integration test TurboFilter nên đo kết quả thực tế của lời gọi logger ở mức vốn bị chặn và kiểm tra trạng thái bật/tắt qua API tương ứng. Đừng mặc định mọi backend hoặc facade có thứ tự xử lý giống Logback.

Để tránh rò cấu hình, kiểm thử TurboFilter nên sử dụng `LoggerContext` riêng hoặc đăng ký và gỡ filter một cách có kiểm soát. Không tùy tiện sửa danh sách TurboFilter toàn ứng dụng khi các test khác chạy song song.

## 8. Filter khi dùng logging bất đồng bộ

Trong Logback có thể dùng `AsyncAppender`: log event đi vào queue, sau đó worker chuyển sang appender đích. **Vị trí gắn filter quyết định lúc filter chạy:**

```text
Producer thread
    |
    v
Logger level / TurboFilter
    |
    v
AsyncAppender
   |  (Filter gắn ở AsyncAppender: lọc trước khi vào queue)
   v
Queue
    |
    v
Worker thread
    |
    v
Appender đích
   |  (Filter gắn ở appender đích: lọc sau khi lấy khỏi queue)
   v
Sink
```

Bởi vậy, cùng một điều kiện lọc nhưng chi phí queue, luồng thực thi và lúc quan sát event có thể khác nhau. Một event bị loại trước queue thường không đi vào backlog; một event bị loại ở appender đích có thể vẫn chiếm chỗ queue trước đó.

### Cách kiểm thử async filter đáng tin cậy

- Dùng `BlockingQueue<ILoggingEvent>` hoặc một bộ thu có latch trong appender thử. Gọi `poll(timeout)` để chờ **event được giao đến sink**; không assert ngay sau `logger.info(...)`.
- Với trường hợp event **bị DENY**, không thể chỉ chờ một khoảng ngắn rồi kết luận nó sẽ không bao giờ tới. Dùng một **barrier/sentinel event** chắc chắn được chấp nhận trên **cùng queue và cùng consumer có thứ tự**; khi sentinel đã đến sink, những event đã xếp trước đó và có thể tới sink phải được xử lý theo thứ tự bảo đảm của implementation. Sau đó mới assert số lượng và event bị loại.
- Với queue có chính sách discard hoặc overload, phải cấu hình rõ hành vi và đặt công suất đủ cho test chức năng. Nếu mục tiêu là test filter, không để sự kiện mất do queue đầy rồi nhầm thành kết quả `DENY`.
- Đặt timeout hữu hạn và cleanup `AsyncAppender.stop()` trong `finally`; khi kiểm tra shutdown, hiểu `maxFlushTime` và các bảo đảm flush của phiên bản Logback dùng.
- Dữ liệu MDC cần được kiểm tra trên event đã được chuẩn bị/chụp khi producer tạo log. `ILoggingEvent.getThreadName()` phản ánh thread nguồn của event; nếu muốn kiểm tra worker thực sự append, ghi `Thread.currentThread().getName()` bên trong appender thử.

**Đặc biệt với MDC:** lọc theo `MDC["requestId"]` trong appender async cần dựa vào snapshot sự kiện, không đọc tùy tiện `MDC.get(...)` của worker rồi coi đó là MDC của producer. MDC thường gắn với thread hiện tại; worker có thể không có context của thread tạo log.

## 9. Kiểm thử với nhiều thread và nhiều appender

Một hệ thống có nhiều request đồng thời cần tránh filter đọc trạng thái chung không được đồng bộ. Filter càng đơn giản, không trạng thái và bất biến càng dễ tin cậy.

Một kịch bản:

1. Tạo một logger test riêng với `MemoryAppender`, policy không discard và `N` producer.
2. Mỗi producer phát những event có ID duy nhất như `P0-0`, `P0-1`, ...; một nửa event được đánh dấu `channel=health`, còn lại `channel=orders`.
3. Bắt đầu producer bằng `CountDownLatch`, chờ tất cả `Future.get(timeout)`; mỗi task tự cài và dọn `MDC` của thread mình trong `try/finally`.
4. Sau khi sink đã nhận hết event được phép theo cách đồng bộ hóa thích hợp, so sánh **tập ID được nhận** với tập dự kiến. Phát hiện được event thừa, thiếu hoặc trùng mà không dựa vào thứ tự xen kẽ giữa producer.
5. Nếu có console và file appender cùng hoạt động, thu kết quả **từng appender** để chứng minh filter chỉ áp dụng cho sink được gắn.

Đừng bắt buộc thứ tự toàn cục giữa các producer; scheduler có thể xen kẽ hợp lệ. Nếu backend bảo đảm FIFO theo một queue và mỗi producer nộp sự kiện tuần tự, có thể kiểm tra **thứ tự riêng từng producer**. Trong test có nhiều thread, appender thử cần collector thread-safe và trạng thái đã được xuất bản an toàn.

Test đo hiệu năng phải tách khỏi test đúng/sai: `CopyOnWriteArrayList` hữu ích cho vài event trong test nhưng chi phí sao chép tăng mạnh nếu ghi hàng trăm nghìn event. Với benchmark, dùng collector và tải phù hợp, warm-up JVM và thống kê nhiều lần đo.

## 10. Những lỗi phổ biến khi kiểm thử filter

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Filter trả `DENY` nhưng vẫn thấy log | Có appender khác không gắn filter, logger bị additivity hoặc cấu hình khác active | Kiểm tra đúng logger, từng appender và cấu hình thực tế |
| Filter chưa được gọi | Logger level chặn trước, appender chưa start hoặc chưa gắn filter | Kiểm tra tầng level và lifecycle trước |
| `ACCEPT` tưởng có thể ghi lại một `DEBUG` bị chặn ở logger | Nhầm appender filter với TurboFilter | Tách test theo vị trí trong pipeline |
| Có event thừa khi chạy cả test suite | Chia sẻ root appender và không cleanup | Dùng tên logger riêng, `additive=false`, gỡ appender |
| Test async thỉnh thoảng thất bại | Assert trước khi worker append, hoặc queue drop event | Chờ sink/sentinel với timeout và cấu hình queue rõ |
| Filter theo MDC sai giữa request | Thread pool tái sử dụng thread, không restore MDC | Thiết lập và dọn MDC ở ranh giới task |
| Filter dùng message không nhận ra biến | So template `getMessage()` với chuỗi đã format | Dùng đúng trường event và test tham số hóa |
| Test chỉ kiểm tra return của `decide` nhưng production không lọc | Filter chưa được cấu hình hoặc thứ tự sai | Thêm integration test dùng cấu hình thực tế |
| Log ở file và console khác nhau | Filter ở từng sink khác nhau | Kiểm chứng từng appender, level và encoder |
| Test làm nhiều logger khác thất bại | Reset `LoggerContext` toàn cục hoặc thay root giữa test | Cô lập context, restore trong `finally` |
| Cấu hình “ẩn secret” vẫn lộ dữ liệu | Chỉ giảm log level hoặc lọc một vài message | Kiểm tra redaction tại nguồn và trường output cuối |

### Những điều không nên làm

Không dùng `Thread.sleep(500)` như bảo đảm filter async đã hoàn tất. Không bắt toàn bộ `Exception` ở filter rồi mặc nhiên trả `ACCEPT` mà không có quyết định an toàn và quan sát lỗi. Không kiểm thử an toàn dữ liệu bằng cách chỉ xác nhận một cụm từ không xuất hiện trong một appender nếu còn appender khác có thể ghi nó.

Filter nên tránh thao tác I/O nặng, truy vấn database, tạo exception liên tục, phụ thuộc vào thời gian dễ thay đổi hoặc sửa đổi object sự kiện không đúng hợp đồng. Filter nằm trên đường đi nóng của logging; nếu chính filter bị chậm hay treo, nó có thể ảnh hưởng trực tiếp đến ứng dụng hoặc hàng đợi async.

## 11. Bảo mật: filter không thay thế quy tắc không ghi dữ liệu nhạy cảm

Một số ứng dụng định dùng filter để loại log chứa password, token hoặc thông tin cá nhân. Đây là lớp phòng vệ bổ sung, **không phải bảo đảm đầy đủ**:

- Filter đặt tại một appender có thể không bảo vệ appender khác.
- Chuỗi đã format và object serialization có thể làm lộ dữ liệu theo cách luật lọc không dự tính.
- Stack trace, marker và MDC có thể mang dữ liệu nhạy cảm ngoài `message`.
- Logger khác hoặc backend khác có thể không sử dụng filter đó.
- Nếu muốn redaction, cần chính sách kiểm tra dữ liệu tại nguồn, encoder/structured-logging phù hợp và kiểm thử ở sink cuối.

Test an toàn nên dùng **chuỗi bí mật giả do test tự đặt**, tạo event qua đường đi thật, và xác minh chuỗi đó không xuất hiện ở mọi sink có khả năng truy cập theo hợp đồng. Tuyệt đối không đưa secret thật vào test fixture hoặc log.

## 12. Checklist trước khi chấp nhận một filter logging

- [ ] Xác định rõ mục đích: lọc theo level, MDC, marker, message, package hay chính sách khác.
- [ ] Biết filter gắn ở logger/TurboFilter hay appender nào; hiểu thứ tự áp dụng.
- [ ] Có ca `DENY`, `NEUTRAL`, `ACCEPT` và phân biệt level gating với filter.
- [ ] Có test tích cực (event được giữ) và tiêu cực (event bị loại), kể cả input null/thiếu.
- [ ] Test unit kiểm tra quyết định; test integration kiểm tra event đến đúng sink.
- [ ] Các test được cô lập logger, MDC và lifecycle, không làm nhiễu root logger toàn ứng dụng.
- [ ] Nếu dùng async, có chờ tín hiệu sink/sentinel, timeout và cấu hình queue rõ ràng.
- [ ] Nếu nhiều thread, bộ thu an toàn đồng thời và không khẳng định thứ tự xuyên producer.
- [ ] Nếu có nhiều appender, kiểm tra riêng các sink và chính sách lọc từng nơi.
- [ ] Bảo đảm thông tin nhạy cảm được xử lý ở cả nguồn và pipeline log.
- [ ] Khi đổi cấu hình profile hoặc logging backend, test lại filter và level hiệu lực.

**Ghi nhớ:** `FilterReply` là một quyết định trong **một tầng** của pipeline logging; muốn biết filter thật sự hoạt động, phải kiểm tra event nào tới được **đúng appender** trong đúng cấu hình. Test ổn định tách rõ level, filter, async delivery, MDC và chính sách của mỗi sink.
