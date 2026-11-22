# Drop log không cần thiết trong Java Core Logging

## Mục tiêu bài học

Chủ đề **Filtering → Drop log không cần thiết** giúp bạn giảm lượng log dư thừa trong ứng dụng Java mà vẫn giữ đủ dữ liệu để chẩn đoán lỗi, kiểm tra hệ thống và đáp ứng yêu cầu audit. Sau bài này, bạn có thể:

- Xác định log nào nên bỏ, giữ, lấy mẫu hoặc tổng hợp thay vì ghi từng sự kiện.
- Chọn đúng vị trí lọc: trước khi tạo sự kiện log, ở logger, tại appender hoặc ở collector.
- Hiểu sự khác nhau giữa **lọc chủ động** và **mất log ngoài ý muốn** khi queue/collector quá tải.
- Sử dụng log level, package-specific logger, bộ lọc có điều kiện, sampling và rate limiting.
- Viết ví dụ Java 17 chạy độc lập bằng `java.util.logging.Filter` và biết áp dụng cùng tư duy với SLF4J, Logback, Log4j 2.
- Đo hiệu quả giảm log nhưng vẫn xác minh cảnh báo, exception, giao dịch quan trọng và khả năng truy vết được giữ lại.

**Nguyên tắc:** Chỉ drop khi biết rõ lý do và phạm vi. Tiết kiệm CPU, I/O, dung lượng và chi phí tìm kiếm là mục tiêu hợp lý; việc che mất lỗi hoặc dữ liệu kiểm toán có thể khiến hệ thống khó vận hành hơn nhiều so với chi phí tiết kiệm được.

## 1. “Drop log không cần thiết” nghĩa là gì?

**Drop** ở đây là quyết định **không phát hành hoặc không lưu** một sự kiện log vì nó ít giá trị so với chi phí. Ví dụ: bộ kiểm tra sức khỏe trả `200 OK` mỗi giây; ghi mỗi lần thành một dòng `INFO` có thể tạo ra hàng triệu dòng tương tự, trong khi các lần kiểm tra **thất bại** cần được ghi.

Có các hình thức khác nhau:

| Hình thức | Ví dụ | Hệ quả |
| --- | --- | --- |
| **Suppress theo log level** | Tắt `DEBUG` của thư viện HTTP khi bình thường | Lời gọi log ở mức thấp hơn ngưỡng không tạo event đầy đủ ở logging pipeline (chi phí tính đối số Java vẫn có thể phát sinh). |
| **Drop có điều kiện** | Bỏ `INFO healthcheck.ok`, giữ `WARN healthcheck.failed` | Loại riêng một loại event theo package, marker hoặc event code. |
| **Sampling** | Chỉ ghi khoảng 1% các request thành công | Giảm số log dạng thống kê nhưng không còn toàn bộ sự kiện thành công. |
| **Rate limiting** | Giới hạn log lặp của một lỗi phụ trợ, đồng thời đếm số lần bị giới hạn | Khống chế log storm, nhưng phải giữ tín hiệu lỗi và tổng số lần xảy ra. |
| **Aggregation** | Thay 10.000 dòng “cache hit” bằng metric/cache hit count | Giữ thông tin tổng hợp, mất chi tiết từng event. |
| **Routing/filter theo sink** | Audit event đến audit store, log kỹ thuật khác đến stdout | Một sự kiện có thể bị loại ở một appender nhưng vẫn được lưu ở đích khác. |
| **Drop do queue đầy/pipeline lỗi** | Async appender tự discard hoặc collector quá tải | Đây là mất dữ liệu vận hành, cần đo/cảnh báo; không nên nhầm với chính sách lọc đã duyệt. |

Nói “drop 90% log” chưa đủ để đánh giá thành công. Cần biết 90% đó là `DEBUG` vô ích hay là sự kiện `ERROR`, số lượng log còn lại có giúp truy vết hay không, và có cách nhìn thấy lượng sự kiện bị bỏ hay không.

### Log nào thường có thể giảm?

- Log `DEBUG` trong vòng lặp nóng, poll liên tục hoặc truy xuất cache bình thường.
- Thông báo health/readiness check **thành công** lặp đi lặp lại, khi số lượng/tỷ lệ thành công đã được phản ánh ở metrics.
- Thư viện bên thứ ba in quá nhiều thông tin cấp `INFO` mà ứng dụng không dùng để chẩn đoán.
- Log “vào method”, “ra method” cho mọi lần gọi, đặc biệt khi đã có tracing/profiling phù hợp.
- Log trùng nội dung do cùng exception bị ghi ở nhiều tầng của cùng một đường xử lý.
- Các sự kiện success có số lượng rất lớn, ít giá trị điều tra từng cái và đã có cơ chế quan sát khác.

### Log nào không được bỏ bừa?

- Sự kiện `ERROR` liên quan thất bại thực tế, thay đổi trạng thái quan trọng, giao dịch không hoàn tất.
- Cảnh báo về tài nguyên, timeout, retry exhausted, lỗi tích hợp và hành vi bất thường cần điều tra.
- Security alert, hành vi truy cập trái phép, vi phạm chính sách và các sự kiện đáp ứng yêu cầu pháp lý.
- Audit trail bắt buộc, nhất là khi cần tính toàn vẹn, lưu trữ bền vững và khả năng truy xét.
- Thông tin correlation thiết yếu như trace ID/request ID dùng để liên kết chuỗi lỗi.

Một log chi tiết đôi khi thực sự quan trọng trong giai đoạn điều tra. Vì vậy mức log và bộ lọc nên có khả năng cấu hình theo môi trường, package và thời gian, với kiểm thử trước khi phát hành.

## 2. Lọc xảy ra ở đâu trong pipeline?

Pipeline khái niệm:

```text
Ứng dụng / thư viện
    |
    |  1. Kiểm tra level hoặc quyết định không gọi logger
    v
Logger / bộ lọc sớm
    |
    |  2. Tạo LogRecord/LoggingEvent, capture context
    v
LoggerConfig / appender filter
    |
    |  3. Encode, format, enqueue nếu async
    v
Console / file / network appender
    |
    |  4. Agent / collector / ingest filter
    v
Storage / search / dashboard
```

Tên các giai đoạn và vị trí chính xác thay đổi theo JUL, Logback, Log4j 2 và cấu hình async. Tuy vậy, quy tắc chi phí có tính tổng quát: **lọc càng sớm càng tránh được nhiều công việc phía sau**.

- Lọc trước khi tạo event có thể tiết kiệm cấp phát event, lấy MDC/context, serialize và enqueue.
- Lọc ở appender tiết kiệm việc ghi vào sink đó nhưng ứng dụng có thể đã trả giá tạo event; nếu có nhiều appender, event có thể vẫn xuất ở appender khác.
- Lọc ở collector giảm lưu trữ/index nhưng ứng dụng đã format và truyền bytes trên mạng hoặc stdout; không sửa được chi phí producer.
- Log level là lớp lọc đầu tiên đơn giản và rất hiệu quả cho mức chi tiết.
- Bộ lọc theo event code, marker hoặc logger name đáng tin cậy hơn việc phân tích chuỗi message tự do đã được format.

### Chi phí còn tồn tại ngay cả khi log bị drop

Java tính các đối số trước khi gọi method. Ví dụ sau vẫn chạy hàm tốn kém nếu mức `DEBUG` đang tắt:

```java
logger.debug("state=" + expensiveToString());
```

Dạng parameterized logging tránh nối chuỗi sớm, nhưng biểu thức tạo đối số vẫn được tính:

```java
logger.debug("state={}", expensiveToString());
```

Nếu việc tính dữ liệu đắt đỏ, hãy để nó bên trong một điều kiện kiểm tra cấp log:

```java
if (logger.isDebugEnabled()) {
    logger.debug("state={}", expensiveToString());
}
```

Đây là **đoạn mã minh họa** dùng API SLF4J, cần dependency SLF4J và một backend để chạy. Với API fluent của SLF4J 2, cũng có thể dùng lazy supplier phù hợp với backend, nhưng phải kiểm tra rằng supplier thực sự được đánh giá lười và không tự thực hiện công việc trước đó. Không nên xây chuỗi JSON, stack trace hay dump object lớn chỉ để filter loại event ở cuối pipeline.

## 3. Lọc bằng log level và package/logger

Các mức thường gặp ở SLF4J/Logback/Log4j 2 theo thứ tự tăng mức nghiêm trọng: `TRACE < DEBUG < INFO < WARN < ERROR`. Nếu logger có effective level `INFO`, các log `TRACE` và `DEBUG` thông thường bị loại; `INFO`, `WARN` và `ERROR` được xét tiếp tùy các filter/appender. Framework có thể hỗ trợ `OFF` để tắt hoặc `ALL` để nhận mọi mức.

Đối với Java Util Logging (JUL), các mức phổ biến gồm `FINEST`, `FINER`, `FINE`, `INFO`, `WARNING`, `SEVERE`; tên và cách cấu hình khác. Đừng giả định JUL có hằng số `DEBUG` hoặc `ERROR`.

Ví dụ cấu hình Spring Boot cho ứng dụng dùng SLF4J:

```yaml
logging:
  level:
    root: INFO
    org.hibernate.SQL: WARN
    org.apache.http: WARN
    com.example.checkout: INFO
    com.example.checkout.diagnostics: DEBUG
```

Đây là một đoạn `application.yml`/`application-staging.yml`, **không phải ứng dụng Java độc lập**. Tên package của thư viện và cách phân cấp logger có thể thay đổi theo dependency/phiên bản. Ý nghĩa:

1. Root ở `INFO` để giảm log chi tiết toàn hệ thống.
2. Hạn chế log SQL/HTTP quá ồn xuống `WARN` trong môi trường cần thiết, nhưng vẫn giữ cảnh báo và lỗi.
3. Mở `DEBUG` chỉ cho package chẩn đoán đang điều tra, rồi hoàn nguyên khi xong.
4. Log level áp dụng theo logger, còn filter theo event có thể xử lý các bản ghi cùng level nhưng giá trị vận hành khác nhau.

**Không dùng `root: ERROR` để “giảm log” một cách tùy tiện.** Cách này có thể làm biến mất cả tín hiệu `WARN`, startup/configuration hoặc những thông báo hữu ích cho điều tra. Nên bắt đầu từ việc thống kê các logger phát nhiều event nhất.

## 4. Drop theo điều kiện: event code, marker, context

Khi cùng mức `INFO` có cả “healthcheck thành công” lặp lại và “đã tạo đơn hàng”, tắt toàn bộ `INFO` là quá rộng. Thay vào đó, sử dụng điều kiện ổn định:

```text
IF level == INFO
   AND logger == "com.example.monitor.HealthProbe"
   AND event_code == "healthcheck.ok"
THEN DROP
ELSE KEEP
```

Một nguyên tắc tốt là **allowlist/bộ lọc theo đúng điều kiện** cho event ít giá trị, thay vì `message.contains("health")`. Điều kiện theo chuỗi tự do có thể vô tình loại `healthcheck.failed` hoặc các dòng lỗi có từ khóa tương tự.

Nếu framework hỗ trợ **marker** hoặc structured key-value, nên phát event có mã ổn định như `event=healthcheck.ok`, `event=cache.hit`. Context như `service`, `environment`, `component` hoặc trạng thái HTTP có thể là bộ tiêu chí phụ, nhưng phải cân nhắc rằng MDC/tracing có thể chưa được set ở thời điểm lọc và có thể thay đổi qua async boundary.

**Nơi đặt filter ảnh hưởng phạm vi:**

- Logger-level/global filter: có thể chặn một event trên mọi appender được áp dụng.
- Appender-level filter: chỉ điều khiển event tới appender đó; một appender khác có thể vẫn ghi.
- Agent/collector rule: ảnh hưởng dữ liệu lưu trữ và truy vấn, nhưng vẫn tiêu thụ chi phí ứng dụng và đường vận chuyển trước collector.

Nếu hệ thống có audit store riêng, tuyệt đối không áp dụng một global filter làm mất audit event chỉ vì giảm log kỹ thuật. Tách luồng hoặc tiêu chí phân loại và xác minh ở tất cả đích ghi.

## 5. Java 17 chạy độc lập: drop heartbeat thành công bằng JUL Filter

Chương trình sau chỉ cần JDK 17+, không cần Maven, Spring Boot hay dependency SLF4J. Nó cho thấy **hai tầng lọc**:

1. `Logger.setLevel(Level.INFO)` bỏ log `FINE` trước khi gọi `Filter`.
2. `Logger.setFilter(...)` chỉ bỏ event `INFO healthcheck.ok`; vẫn giữ log nghiệp vụ và cảnh báo healthcheck thất bại.

Bộ đếm `droppedByFilter` giúp biết có đúng một event bị lọc theo điều kiện. Bộ đếm này **không tính** event `FINE` đã bị loại bởi level trước khi `Filter` chạy; vì vậy một bộ đếm đơn lẻ không thể được xem là số event “ứng dụng đã định ghi nhưng không lưu” trong mọi trường hợp.

Tạo file **`DropUnnecessaryLogsDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DropUnnecessaryLogsDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.filtering");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger droppedByFilter = new AtomicInteger();
        logger.setFilter(record -> {
            boolean noise =
                    record.getLevel().equals(Level.INFO)
                    && "healthcheck.ok".equals(record.getMessage());

            if (noise) {
                droppedByFilter.incrementAndGet();
            }
            return !noise;
        });

        Handler stdout = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(
                            record.getLevel().getName()
                            + " event=" + record.getMessage());
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        stdout.setLevel(Level.ALL);
        logger.addHandler(stdout);

        try {
            logger.fine("cache.detail");
            logger.info("healthcheck.ok");
            logger.info("order.created");
            logger.warning("healthcheck.failed");
            logger.severe("payment.unavailable");
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
            logger.setFilter(null);
        }

        System.out.println("droppedByFilter=" + droppedByFilter.get());
    }
}
```

Biên dịch và chạy:

```bash
javac DropUnnecessaryLogsDemo.java
java DropUnnecessaryLogsDemo
```

**stdout chính xác**:

```text
INFO event=order.created
WARNING event=healthcheck.failed
SEVERE event=payment.unavailable
droppedByFilter=1
```

Giải thích:

- `logger.fine("cache.detail")` không xuất vì logger effective level là `INFO`. Event này không qua custom filter nên bộ đếm không tăng.
- `logger.info("healthcheck.ok")` vượt qua level nhưng bị filter trả `false`, nên không chuyển tới Handler.
- `logger.info("order.created")`, `logger.warning("healthcheck.failed")` và `logger.severe("payment.unavailable")` được giữ. Điều kiện **chỉ** loại một INFO success cụ thể.
- `setUseParentHandlers(false)` ngăn event đi tiếp tới parent handler (tránh log xuất trùng với JUL root handler mặc định). Handler tự in `System.out` và không có timestamp nên output ổn định.
- `Handler.isLoggable(record)` tôn trọng level/filter của chính handler; ở ví dụ, handler nhận mọi level còn lại do `Level.ALL`.
- `finally` gỡ handler và filter được cài trong chương trình. Việc thay đổi global/shared logger configuration trong ứng dụng thực tế phải được quản lý lúc khởi tạo, tránh các thread đồng thời vô tình thấy cấu hình thay đổi.

**Thử nghiệm:** sửa `"healthcheck.ok"` thành `"healthcheck.failed"` trong điều kiện lọc để thấy log cảnh báo có được giữ hay không. Vì bộ lọc còn đòi mức `INFO`, cảnh báo `WARNING healthcheck.failed` vẫn không bị loại. Điều này minh họa giá trị của điều kiện theo cả **level lẫn mã event**.

Bài học của ví dụ là **lọc một mẫu log đã biết**, không phải tự động suy đoán log nào “không cần thiết”. JUL `Filter` nhận `LogRecord` sau khi qua kiểm tra level; trong các framework khác, điểm chặn có thể diễn ra sớm hơn.

## 6. Logback: filter tại appender và TurboFilter

Khi ứng dụng dùng **SLF4J + Logback**, Logback Classic có hai cơ chế quan trọng:

- **Regular Filter** ở appender: nhận `ILoggingEvent` đã được tạo, trả `DENY`, `NEUTRAL` hoặc `ACCEPT`. Phù hợp khi muốn một sink bỏ event nào đó nhưng vẫn có thể cho sink khác nhận.
- **TurboFilter**: đặt ở logging context và được xét trước khi tạo event ở nhiều đường gọi logger. Có thể tiết kiệm chi phí tạo/capture event hơn khi loại log tại nguồn.

Ý nghĩa ba quyết định trong Logback:

| Kết quả | Hành vi |
| --- | --- |
| `DENY` | Loại event ở giai đoạn lọc đó, bỏ qua các filter tiếp theo trong chuỗi tương ứng. |
| `NEUTRAL` | Không quyết định, tiếp tục xét filter/logic mặc định kế tiếp. |
| `ACCEPT` | Chấp nhận ở giai đoạn đó, bỏ qua các filter tiếp theo cùng chuỗi; phạm vi ảnh hưởng tùy vị trí. |

**Lưu ý:** `ACCEPT` không đồng nghĩa vượt qua mọi filter và mọi sink trong pipeline. Một event có thể qua filter ở một tầng rồi bị chặn ở tầng khác. Tùy code và cấu hình, filter có thể áp dụng cho toàn logger context hay chỉ cho một appender.

### Ví dụ regular Filter chỉ bỏ INFO healthcheck.ok

Đây là lớp **tích hợp Logback**, cần dependency `logback-classic`/`logback-core`/SLF4J tương thích trên classpath. Nó không phải code thuần JDK.

Tạo file `src/main/java/com/example/logging/IgnoreHealthSuccessFilter.java`:

```java
package com.example.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public class IgnoreHealthSuccessFilter
        extends Filter<ILoggingEvent> {

    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (event.getLevel() == Level.INFO
                && "com.example.monitor.HealthProbe"
                        .equals(event.getLoggerName())
                && "healthcheck.ok".equals(event.getMessage())) {
            return FilterReply.DENY;
        }
        return FilterReply.NEUTRAL;
    }
}
```

Đoạn `logback.xml` hoàn chỉnh ở mức cấu hình appender đơn giản:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <filter class="com.example.logging.IgnoreHealthSuccessFilter"/>

        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Cách hoạt động:

1. Logger `com.example.monitor.HealthProbe` phát một thông báo `INFO` có template đúng `healthcheck.ok`.
2. Bộ lọc trả `DENY` trước khi event đi vào encoder của appender `STDOUT`; message đó không xuất ở console này.
3. Một `WARN healthcheck.failed` hoặc `ERROR` từ cùng logger vẫn được xét bình thường vì điều kiện không trùng.
4. Nếu cấu hình có appender khác **không** gắn filter, event bị loại ở `STDOUT` vẫn có thể được ghi ở appender đó. Khi thiết kế phải kiểm tra đủ các sink.
5. So sánh `event.getMessage()` thường kiểm tra **mẫu message gốc** trong Logback. Nếu dùng parameterized message, không nên dựa vào output đã format để tạo rule mong manh.

Đây là mẫu minh họa với mã event literal. Trong dự án thật nên dùng **structured event code/marker** nhất quán, có test trên appender thật. Không dựa vào `message.contains("ok")` hay regex rộng để loại nhầm event quan trọng.

### Khi nào cần TurboFilter?

Nếu log success được gọi hàng nghìn lần/giây, regular filter chạy **sau** khi event được tạo, do đó còn chi phí cấp phát/capture event. TurboFilter có thể quyết định sớm hơn dựa trên logger name, level, marker, format template hoặc tham số. Chẳng hạn triển khai `TurboFilter.decide(Marker, Logger, Level, String, Object[], Throwable)` có thể trả `DENY` khi:

```text
level = INFO
loggerName = "com.example.monitor.HealthProbe"
messageTemplate = "healthcheck.ok"
```

TurboFilter có phạm vi rộng hơn appender filter, nên cần kiểm tra ảnh hưởng tới những đích bắt buộc giữ event. Ngoài ra, nó không thể hoàn tác chi phí của **biểu thức Java đã tính trước khi gọi logger**. Khi logic lọc phức tạp, đo CPU và allocation; chính filter có thể trở thành nút thắt.

## 7. Log4j 2: chọn đúng tầng lọc

Log4j 2 cho phép đặt bộ lọc ở các tầng như global Logger, LoggerConfig, AppenderRef và Appender. Các filter phổ biến gồm level/threshold, marker và bộ lọc theo ngữ cảnh phù hợp với phiên bản đang chạy.

Log4j 2 cũng dùng kết quả `ACCEPT`, `DENY` và `NEUTRAL`; ý nghĩa cụ thể phải xét theo tầng. Ở một số giai đoạn, `ACCEPT` có thể khiến kiểm tra level của chính giai đoạn đó được bỏ qua, nên không tự thiết lập một global `ACCEPT` quá rộng rồi nghĩ rằng các mức khác vẫn bị chặn như trước. Theo tài liệu Log4j 2, lọc sớm trong pipeline thường tiết kiệm nhiều overhead hơn lọc ở appender sau khi event đã tạo.

Ví dụ cấu hình **Log4j 2 XML** chỉ dùng logger threshold:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="org.hibernate.SQL"
                level="warn"
                additivity="false">
            <AppenderRef ref="Console"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

Ví dụ này **không tự động bỏ riêng event healthcheck.ok**; nó đặt logger `org.hibernate.SQL` ở mức `WARN` để giảm thông tin SQL thông thường. Nếu cần drop theo loại event, thêm filter có điều kiện tại tầng phù hợp và kiểm tra đúng phiên bản/plugin đang dùng.

Log4j 2 có cơ chế rate-limit như `BurstFilter`. Tuy nhiên, điều kiện về ngưỡng level, `rate` và `maxBurst` quyết định loại event nào chịu giới hạn; phải kiểm thử riêng trường hợp cảnh báo và lỗi nghiêm trọng. Không copy nguyên cấu hình rate limit từ một môi trường sang môi trường khác mà không xác minh rằng `ERROR`/security event vẫn còn.

## 8. Sampling và rate limiting: giảm log nhưng giữ tín hiệu

**Sampling** chọn một phần sự kiện để ghi. **Rate limiting** giới hạn tần suất sự kiện được phép ghi. Chúng giải quyết vấn đề log volume lớn theo những cách khác nhau.

| Tình huống | Cách tiếp cận | Rủi ro cần quản lý |
| --- | --- | --- |
| 100.000 request thành công/phút | Sampling có kiểm soát, giữ metrics đếm toàn bộ request | Log từng request không còn đầy đủ; mẫu có thể thiên lệch. |
| Một health probe thành công mỗi giây | Drop success detail, giữ counter/tỷ lệ và failure log | Không biết chi tiết từng success, thường chấp nhận được. |
| Một exception lặp hàng nghìn lần/giây | Rate limit bản ghi chi tiết, tạo aggregate count/alert riêng | Có thể bỏ mất sự thay đổi lỗi nếu group theo key quá rộng. |
| Retry từng bước | Log khi retry policy bắt đầu, retry exhausted, transition, tổng số retry | Mất chi tiết từng lần thử nếu không có tracing/metric bổ sung. |
| Audit giao dịch | Không sampling tùy tiện; thiết kế audit store đúng yêu cầu | Thiếu event có thể làm mất khả năng đối soát. |

### 8.1. Khi sampling, cần biết “1%” là 1% của cái gì

- Sampling ngẫu nhiên theo event không đảm bảo mọi transaction được quan sát có đủ các log liên quan.
- Sampling **nhất quán theo trace ID** có thể giữ các log trong cùng một trace được chọn, hữu ích cho việc điều tra hành trình; vẫn có ngoại lệ policy cho `ERROR` hoặc event đặc biệt. Trace sampling và log sampling không phải cùng cơ chế, cần thiết kế rõ.
- Nếu dùng hash/modulo ID để sampling, phải dùng hash ổn định, phân bố đủ đều và xử lý trường hợp thiếu ID; không lấy một phần ID làm ngưỡng khi không hiểu phân bố.
- Đừng chỉ đo latency hay số lỗi trên những event đã được sample rồi suy ra toàn bộ hệ thống không có vấn đề. Metrics riêng phải theo dõi tổng lượng sự kiện.

Ví dụ chính sách mô tả bằng điều kiện, không phải cú pháp trực tiếp của một framework:

```text
if event.level in {ERROR, WARN}:
    keep
else if event.type == "healthcheck.ok":
    drop
else if event.type == "request.success":
    keep only when stableHash(traceId) falls into selected 1%
else:
    keep according to configured log level
```

Đây là **pseudocode chính sách**. Nếu `WARN` quá lớn đến mức cần giới hạn, xem xét thiết kế alert/aggregate riêng theo ý nghĩa nghiệp vụ; không tự đổi mọi `WARN` thành sự kiện có thể bỏ.

### 8.2. Rate limiting theo key

Một token bucket hoặc leaky bucket có thể giới hạn `N` log/giây cho mỗi nhóm event. Key nên dựa trên loại lỗi, component hoặc mã event ổn định. Nếu key bao gồm user ID hay Trace ID riêng của từng request, cardinality có thể tăng mạnh khiến rate limit kém hiệu quả và tốn bộ nhớ.

Khi giới hạn, ghi thêm **số event bị suppress** dưới dạng metric hoặc thông báo tổng hợp định kỳ. Ví dụ:

```text
WARN event=downstream-timeout detail=first-occurrence
WARN event=downstream-timeout-summary suppressed=124 interval=60s
```

Các dòng trên là ví dụ cấu trúc, **không phải output mặc định**. Không triển khai bộ đếm bằng cách tạo một log cho từng log đã bỏ; điều này sẽ tái tạo log storm. Bộ đếm phải thread-safe khi nhiều request cùng phát sự kiện, và cardinality của nhãn metric phải được giữ trong giới hạn.

## 9. Tránh nhầm lọc chủ động với mất log do async overflow

Một async appender có queue hữu hạn. Khi sink chậm hoặc volume tăng đột biến, queue có thể đầy. Tùy cấu hình framework, producer có thể **block**, drop event, discard level thấp hoặc fallback synchronous. Đây là tình huống **backpressure/overload**, không phải cùng ý nghĩa với filter đã quyết định bỏ `healthcheck.ok`.

Với một hệ thống dùng async logging, cần theo dõi tách biệt:

- `filtered_by_policy`: số event bị bỏ bởi rule do nhóm chủ động cấu hình, theo event type/level.
- `sampled_out` hoặc `rate_limited`: số event đã bị loại bởi chính sách lấy mẫu hoặc hạn tốc.
- `queue_dropped` / `appender_errors`: số event mất vì quá tải/lỗi runtime.
- `emitted`, `accepted`, `written` hoặc số được collector ghi nhận, với định nghĩa cụ thể cho từng mốc.
- `queue_depth`, `enqueue_block_duration`, `sink_write_latency` và `end_to_end_visibility_latency`.

Không phải framework nào cũng cung cấp các bộ đếm này. Có thể cần instrumentation ở call site, appender, agent hoặc collector. Nếu một log đã bị loại **trước khi tạo LogRecord/LoggingEvent**, một filter đặt sau đó không thể biết nó từng tồn tại. Đừng tạo metric “100% log delivered” từ việc đếm duy nhất các event đã tới sink.

**Ví dụ:** Nếu sink xử lý 2.000 log/s còn ứng dụng tạo 5.000 log/s, tăng queue size chỉ trì hoãn lúc queue đầy. Loại bớt 4.000 log/s ít giá trị từ nguồn có thể đưa tải về dưới khả năng sink. Nhưng phải xác minh 4.000 log/s đó thực sự có thể bỏ, và giữ mọi exception/critical event theo policy. Nếu chỉ để queue tự drop khi đầy, không kiểm soát được chính xác những log nào sẽ mất.

## 10. Tránh log trùng lặp mà không mất thông tin

Một nguồn noise khác là **ghi cùng một lỗi ở nhiều tầng**:

```text
Repository: ERROR database timeout
Service:    ERROR database timeout
Controller: ERROR database timeout
Global handler: ERROR request failed: database timeout
```

Có thể cải thiện theo chính sách:

1. Ở tầng thấp, **ném exception kèm nguyên nhân** và bổ sung context bằng exception type hoặc error code khi cần; không tự động log `ERROR` rồi rethrow ở mọi lớp.
2. Tại **ranh giới chịu trách nhiệm xử lý lỗi**, log một event lỗi đầy đủ với trace ID, mã lỗi, tác động và stack trace thích hợp.
3. Nếu tầng thấp thực hiện recover/retry, log chuyển trạng thái quan trọng khi hữu ích (ví dụ retry exhausted), không lặp lại toàn bộ stack trace mỗi lần thử.
4. Duy trì metric để biết lỗi lặp bao nhiêu lần, ngay cả khi bản ghi chi tiết bị rate limit.

Không có quy tắc “chỉ được log một lần” áp dụng cho mọi hệ thống phân tán. Một sự kiện lỗi có thể cần xuất hiện ở nhiều service với ngữ cảnh khác nhau. Mục tiêu là tránh **cùng thông tin trùng không thêm giá trị** trong một đường xử lý, đồng thời giữ đủ dấu vết ở các ranh giới service.

## 11. Bảo mật: giảm noise không thay thế redaction

Filter theo log level không đảm bảo dữ liệu nhạy cảm không lọt vào log khác. Một sự kiện `ERROR` có thể vô tình chứa password, bearer token, cookie, access key, chuỗi kết nối hoặc request body. Cần áp dụng nguyên tắc **không log secret từ đầu**, sau đó redaction/masking tại những điểm phù hợp để giảm rủi ro còn lại.

Các chính sách nên phân biệt:

- **Drop event** vì thông tin không cần thiết, ví dụ healthcheck success lặp lại.
- **Redact field** vì event vẫn cần nhưng có trường nhạy cảm, ví dụ mã giao dịch được giữ còn token bị loại.
- **Không phát sinh dữ liệu nhạy cảm**: tốt hơn masking sau khi đã chuyển qua pipeline.
- **Giữ audit**: security/audit log có đường quản trị, quyền truy cập và retention riêng; không bị filter kỹ thuật thông thường làm mất.

Với log từ input không tin cậy, tránh nối chuỗi có ký tự xuống dòng tự do vì có thể gây log injection hoặc phá structured format. Sử dụng encoder có escape đúng và schema ổn định. Khi triển khai filter trên message, không dùng giá trị chứa dữ liệu cá nhân làm khóa quyết định nếu không có lý do hợp lệ và cơ chế bảo vệ.

## 12. Đo lường hiệu quả trước và sau khi lọc

Một phép thử filtering cần đánh giá **giá trị thông tin được giữ lại**, không chỉ số byte giảm. Nên đo trên cùng workload, thời gian và cấu hình sink:

| Chỉ số | Tại sao cần |
| --- | --- |
| Log events/s theo level/logger/event code | Tìm nguồn noise lớn nhất và xác định rule có đúng đối tượng. |
| Tổng bytes/s, index storage, network egress | Đánh giá tiết kiệm thực tế. |
| CPU, allocation, GC pause, logger call p95/p99 | Kiểm tra lợi ích chi phí trên JVM; lọc ở collector thường không giảm CPU producer nhiều. |
| Queue occupancy, enqueue blocking, async drop | Phân biệt chủ động drop noise với mất log do overload. |
| ERROR/WARN event counts và latency phát hiện lỗi | Xác minh log quan trọng vẫn còn và không làm alert mù. |
| Coverage truy vết theo trace/request ID | Kiểm tra có đủ dữ liệu để debug sự cố thật. |
| Dropped-by-rule/sampling counters | Biết chính sách nào tạo mức giảm và phát hiện cấu hình sai. |

Quy trình:

1. Thu số liệu baseline; dùng top-N logger/package/event code theo volume để tìm điểm gây noise.
2. Chọn rule cụ thể và ghi rõ **tiêu chí**, **phạm vi**, **lý do**, **owner**, **cách khôi phục**.
3. Kiểm thử với các event gần nhau nhưng khác ý nghĩa: `healthcheck.ok`, `healthcheck.failed`, `payment.failed`, `payment.retry`, `order.created`.
4. Đo lại log volume, chi phí và p95/p99 trong workload tương đương. Kiểm tra aggregate metrics và alert.
5. Tạo một lỗi kiểm thử có trace ID; xác minh log chẩn đoán tồn tại ở nguồn, collector và hệ thống tìm kiếm.
6. Kiểm tra behavior khi traffic burst, deploy/restart, collector lỗi hoặc queue đầy. Báo cáo rõ lượng log bị **filter** và lượng log bị **mất**.
7. Triển khai có version và rollback. Theo dõi chỉ số giảm volume cùng việc phát hiện lỗi trong vài chu kỳ vận hành.

**Ví dụ định lượng:** Một ứng dụng ghi 10.000 event/s, trong đó 7.000 event/s là `INFO healthcheck.ok`. Nếu bỏ chính xác loại event đó, lượng event phải ghi xuống sink còn khoảng 3.000/s, tức giảm 70% **số event**. Không thể tự kết luận giảm 70% **dung lượng**, vì mỗi event có kích thước khác nhau; cũng không tự kết luận giảm 70% CPU, vì lượng công việc tiết kiệm phụ thuộc nơi lọc.

## 13. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Không còn log cảnh báo healthcheck | Rule quá rộng, chỉ dựa vào `message.contains("health")` | Dùng level + logger + event code chính xác; test success và failed riêng. |
| Volume giảm nhưng CPU không giảm | Drop ở appender/collector, hoặc ứng dụng vẫn tạo message đắt tiền | Lọc sớm, sử dụng log level, loại bỏ tính toán không cần thiết và benchmark. |
| Log `DEBUG` không được xuất dù filter trả `ACCEPT` | Level/giai đoạn lọc khác còn chặn; hành vi `ACCEPT` phụ thuộc nơi đặt | Kiểm tra effective level và toàn bộ filter chain theo framework. |
| Log vẫn hiện ở sink thứ hai | Filter chỉ gắn với một appender | Kiểm tra additivity/routing và tất cả appender paths. |
| Chỉ thấy một phần log trong đợt lỗi lớn | Rate limit hoặc async overflow | So sánh `rate_limited` và `queue_dropped`; xác định chính sách. |
| Event code không match | Message format đã đổi, rule dựa text | Dùng structured code hoặc marker ổn định; thêm regression test. |
| Bộ đếm drop bằng 0 nhưng volume giảm | Event bị bỏ trước khi filter/counter chạy | Gắn instrumentation ở đúng tầng hoặc dựa vào metrics nghiệp vụ. |
| Thiếu audit/critical events | Filter toàn cục hoặc sampling quá rộng | Tách audit pipeline; đặt allowlist/exception policy; kiểm thử bền vững. |
| Logging filter gây chậm request | Regex/serialization/lock phức tạp mỗi log call | Dùng điều kiện nhẹ, key ổn định, giảm cấp phát và đo p99. |
| DEBUG tắt nhưng có side effect của biểu thức | Argument expression đã chạy trước method call | Dùng `isDebugEnabled()` hoặc API lazy supplier tương thích. |
| Thay đổi config không có hiệu lực | Override profile/property, logger name sai, backend khác dự định | Kiểm tra effective logger level, appender attachment, config được nạp. |

## 14. Checklist review một rule drop log

Trước khi merge hoặc bật một rule filtering ở production, hãy trả lời được:

1. **Event nào?** Có ví dụ cụ thể và khóa nhận dạng ổn định không?
2. **Được phép mất không?** Có liên quan bảo mật, audit, giao dịch, lỗi hay chẩn đoán sự cố không?
3. **Đặt rule ở tầng nào?** Có tiết kiệm chi phí mong muốn và có ảnh hưởng tất cả sink không?
4. **Giữ gì thay thế?** Counter, metric, summary, trace sample hoặc một event đại diện nào vẫn phản ánh tình trạng?
5. **Có trường hợp ngoại lệ?** `WARN`/`ERROR`, lần thất bại, retry exhausted và security event có được giữ không?
6. **Đếm được log bị bỏ không?** Có tách policy drop với overflow/drop tại queue và collector không?
7. **Test được không?** Có ví dụ success/noise và failure/critical để chứng minh đúng hành vi không?
8. **Rollback thế nào?** Khi điều tra cần tăng verbosity, có thể nới rule theo package và thời gian mà không rebuild nguy hiểm không?
9. **Hiệu quả thực tế?** Đã so sánh event/s, bytes, CPU, latency, khả năng phát hiện lỗi và storage trên workload đại diện chưa?

**Tiêu chí đạt:** Bạn lọc đúng event ít giá trị, giữ được log quan trọng, hiểu chi phí phát sinh ở từng tầng và chứng minh bằng test/metrics rằng tỷ lệ log giảm không phải do hệ thống âm thầm đánh mất dữ liệu cần thiết.

## Tài liệu tham khảo

- [Oracle Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — kiểm tra level, tạo LogRecord và áp dụng Logger Filter.
- [Oracle Java SE 17 — Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Filter.html) — `isLoggable(LogRecord)`.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — Filter, TurboFilter, `DENY`, `ACCEPT`, `NEUTRAL`.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — log level, logger hierarchy và selection rule.
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html) — các giai đoạn filtering, level, filter result và overhead.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html) — queue, overload/backpressure và các điểm cần đo khi async logging.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — API logger, parameterized messages và fluent API.
