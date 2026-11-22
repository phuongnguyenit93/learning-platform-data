# Cấu hình theo appender trong Java Logging

## 1. Appender là gì và vì sao phải cấu hình riêng?

Trong Java Logging, **logger** là điểm mà mã ứng dụng gọi để phát sinh thông điệp như `log.info("Created order")`. **Appender** là thành phần nhận một *logging event* đã được cho phép và **ghi nó tới một đích cụ thể**: terminal, file, rolling file, socket, hệ thống telemetry hoặc một appender khác. Trong `java.util.logging` (JUL), thành phần cùng vai trò có tên là **Handler**.

Một ứng dụng thường cần nhiều đích ghi với chính sách khác nhau:

- **Console**: chủ yếu hiển thị `WARN`/`ERROR` để đội vận hành theo dõi nhanh.
- **File**: lưu cả `INFO` trở lên, có timestamp, tên logger và thông tin trace.
- **Audit**: ghi sự kiện nghiệp vụ được định nghĩa riêng, có kiểm soát truy cập, lưu trữ và retention riêng.
- **Async**: đặt hàng đợi ở trước sink đắt đỏ để thread nghiệp vụ không phải trực tiếp chờ mọi I/O.

Vì vậy, “cấu hình theo appender” nghĩa là **mỗi đích có tên, layout/encoder, filter, chính sách ghi, giới hạn lưu trữ và cách gắn với logger** tương ứng. Không nên cố gắng giải quyết mọi yêu cầu bằng một `root level` toàn cục.

Ví dụ mong muốn:

| Event | Console | File ứng dụng | Audit |
| --- | --- | --- | --- |
| `com.example.orders` – `DEBUG` | Không | Không (nếu logger chỉ ở INFO) | Không |
| `com.example.orders` – `INFO` | Không | Có | Không |
| `com.example.orders` – `ERROR` | Có | Có | Không |
| `com.example.payment` – `DEBUG` | Không | Có (khi package logger ở DEBUG) | Không |
| `com.example.audit` – `INFO` | Không | Không nếu cấu hình `additivity=false` | Có |

Kết quả trên phụ thuộc **toàn bộ chuỗi quyết định** của logger và appender; việc khai báo một appender trong XML chưa khiến nó tự ghi log. Logger phải **tham chiếu** tới nó.

## 2. Chuỗi quyết định: logger level, routing, appender filter, output

```text
Application: logger.info("message")
            │
            ▼
Logger effective level có cho phép event?
     ├── Không: dừng tại đây
     └── Có: tạo LogEvent
                 │
                 ▼
       Logger/appender references + additivity
                 │
         ┌───────┴──────────┬────────────────┐
         ▼                  ▼                ▼
   CONSOLE appender     FILE appender    AUDIT appender
   threshold WARN       threshold INFO   audit route
   pattern ngắn         pattern chi tiết  policy riêng
         │                  │                │
      stdout/stderr       rolling file    file/kênh audit
```

**Logger level** điều khiển *event có được sinh/cho phép hay không*. Logback có quy tắc cơ bản: event ở level `p` được enable nếu `p` lớn hơn hoặc bằng **effective level** `q` của logger. Logger có thể kế thừa level của cha nếu chưa gán level riêng.

**Appender filter/threshold** quyết định *đích nào nhận một event đã được tạo*. Ví dụ root logger ở `INFO`, appender Console chỉ nhận `WARN` trở lên còn File nhận `INFO` trở lên. Event `DEBUG` từ một logger hiệu lực `INFO` **không được tạo**; appender File có đặt “DEBUG” cũng không thể phục hồi event ấy. Ngược lại, khi một logger con ở `DEBUG`, event `DEBUG` đã được enable có thể đi tới appender của root qua cơ chế additivity, nếu appender filter cho phép.

**Layout/encoder** định nghĩa một event trở thành bytes như thế nào: pattern text, JSON, encoding và ký tự xuống dòng. Nó không quyết định event có được tạo hay không. Với Logback, `PatternLayoutEncoder` vừa áp dụng pattern vừa mã hóa; với Log4j 2 là `PatternLayout` hoặc JSON layout phù hợp.

**Destination/retention** quy định log đi tới đâu, khi nào rollover, lưu bao lâu, ai có quyền đọc, và điều gì xảy ra khi sink bị đầy hoặc lỗi. Đây thường là thuộc tính **riêng từng appender**.

## 3. Các nhóm appender hay dùng

| Appender / Handler | Đích ghi | Cấu hình quan trọng | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `ConsoleAppender` (Logback/Log4j 2), `ConsoleHandler` (JUL) | stdout/stderr | Target, layout, level/filter | Container, local development, terminal |
| `FileAppender` / `FileHandler` | Một hoặc nhiều file | Đường dẫn, append/overwrite, encoding, lock, level | Công cụ hoặc ứng dụng đơn giản |
| `RollingFileAppender` / `RollingFile` | File hiện hành và file archive | File name pattern, trigger, max size, history, compression | Ứng dụng ghi nhiều log cần giới hạn disk |
| `AsyncAppender` | Hàng đợi trước appender khác | Capacity, discard/full policy, flush timeout | Đầu ra có I/O đáng kể, cho phép đánh đổi |
| Network/OTLP appender hoặc bridge | Endpoint/Collector | Timeout, batch, retry, TLS, auth, batching | Telemetry tập trung |
| Routing/Sifting appender | Chọn appender đích theo context | Routing key, lifecycle và số lượng route | Cần tách luồng log theo tenant/case đã kiểm soát |

Không phải framework nào cũng có cùng tên hoặc cùng mặc định. Ví dụ, JUL `FileHandler` hỗ trợ giới hạn kích thước/count và xoay theo số file, nhưng không tương đương hoàn toàn với `SizeAndTimeBasedRollingPolicy` của Logback.

## 4. Ví dụ Logback: mỗi appender một chính sách

Giả sử ứng dụng Spring Boot sử dụng SLF4J và backend Logback. Tạo `src/main/resources/logback-spring.xml`. Ví dụ sau bao gồm:

- `CONSOLE` chỉ in `WARN` trở lên;
- `APP_FILE` lưu `INFO` trở lên mặc định, riêng package payment được phép `DEBUG`;
- `AUDIT_FILE` dành cho logger `com.example.audit`, tách khỏi các appender của root.

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="APP_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>20MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} trace_id=%X{trace_id} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="AUDIT_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/audit.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/audit.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>30</maxHistory>
            <totalSizeCap>500MB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="DEBUG"/>

    <logger name="com.example.audit"
            level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="APP_FILE"/>
    </root>
</configuration>
```

Đây là **cấu hình để đặt trong một ứng dụng Spring Boot đã có Logback**, không phải mã Java standalone. Thư mục `logs/` tính theo working directory của tiến trình; thư mục cha phải có quyền tạo/ghi và đủ disk. Khi triển khai trong container, phải quyết định có ghi file nội bộ hay chỉ ghi stdout rồi để nền tảng thu thập.

### 4.1. Phân tích từng phần

**`CONSOLE`:** `ThresholdFilter` bỏ các event dưới `WARN`. Logback `ThresholdFilter` sẽ trả `DENY` với level thấp hơn ngưỡng và `NEUTRAL` với event đạt ngưỡng. Level `WARN`/`ERROR` đã được logger cho phép mới tới được bước này. Pattern in level, thread, logger và message; thời điểm in là thời điểm của logging event.

**`APP_FILE`:** `RollingFileAppender` giữ file đang mở ở `logs/application.log`. `SizeAndTimeBasedRollingPolicy` tạo archive theo ngày và chỉ số `%i` khi file vượt kích thước cấu hình trong cùng ngày. Ký hiệu `%d` và `%i` là bắt buộc cho kiểu phối hợp ngày + kích thước. `maxHistory=14` giữ tối đa 14 chu kỳ ngày lịch sử, `totalSizeCap=1GB` giới hạn tổng dung lượng archive theo cơ chế của Logback; nó **không bảo đảm file đang ghi hiện tại** luôn dưới giới hạn ngay lập tức hoặc tổng disk usage chính xác bằng 1GB.

**`AUDIT_FILE`:** lưu ngày và retention riêng; audit logger có `additivity=false` nên log được gắn vào `AUDIT_FILE` **không đi tiếp** tới `CONSOLE`/`APP_FILE` của root. Đây là thao tác route, không phải cơ chế đảm bảo audit bền vững hay chống chỉnh sửa. Với audit bắt buộc theo quy định, còn cần xác nhận durable write, bảo vệ truy cập, retention pháp lý và pipeline riêng.

**`com.example.payment`:** được đặt `DEBUG` và vẫn kế thừa appender của root (do additivity mặc định là `true`). Khi package phát sinh `DEBUG`, `APP_FILE` vẫn ghi vì appender không có filter riêng cấm DEBUG; `CONSOLE` lọc nó vì chỉ nhận WARN trở lên. Root ở INFO **không lọc lại DEBUG** đã được enable ở logger con trong Logback. Không nên mặc định rằng root INFO sẽ chặn mọi DEBUG từ logger con.

**`trace_id=%X{trace_id}`:** chỉ có dữ liệu nếu MDC đã được ứng dụng hoặc instrumentation điền đúng. Pattern theo appender không tự sinh trace ID. Khi trống, phải xem lại propagation/MDC trước khi kết luận appender lỗi.

### 4.2. Mối quan hệ giữa logger level và appender filter

Giả sử có các lời gọi:

```java
private static final org.slf4j.Logger ORDER =
        org.slf4j.LoggerFactory.getLogger("com.example.orders.OrderService");
private static final org.slf4j.Logger PAYMENT =
        org.slf4j.LoggerFactory.getLogger("com.example.payment.PaymentService");
private static final org.slf4j.Logger AUDIT =
        org.slf4j.LoggerFactory.getLogger("com.example.audit.ChangeLog");

public void process() {
    ORDER.debug("Order cache lookup");
    ORDER.info("Order created");
    ORDER.error("Order submission failed");
    PAYMENT.debug("Payment attempt prepared");
    AUDIT.info("Role changed");
}
```

Đoạn này là **method minh họa thuộc class đã khai báo ba field logger**; để chạy cần dependency SLF4J, Logback và lớp ứng dụng thực. Không thể copy riêng đoạn này vào file rồi chạy bằng `javac` không classpath.

Theo cấu hình ở trên, các event sẽ đi như sau:

| Lời gọi | Enabled tại logger? | `CONSOLE` | `APP_FILE` | `AUDIT_FILE` |
| --- | --- | --- | --- | --- |
| `ORDER.debug` | Không, effective INFO | Không | Không | Không |
| `ORDER.info` | Có | Không, dưới WARN | Có | Không |
| `ORDER.error` | Có | Có | Có | Không |
| `PAYMENT.debug` | Có, logger DEBUG | Không, dưới WARN | Có | Không |
| `AUDIT.info` | Có | Không, additivity false | Không, additivity false | Có |

Không dựa vào bảng này để xác định “mỗi log chỉ xuất hiện đúng một lần”: một event có thể được gửi tới **hai đích có chủ ý** (console + file). Hiện tượng *duplicate* là hai bản không mong muốn ở **cùng một sink hoặc cùng pipeline ingest** do cấu hình route/appender/collector trùng lặp.

## 5. Lọc theo appender: ThresholdFilter, LevelFilter, Filter chain

Trong Logback:

- `ThresholdFilter` cho phép event ở **mức từ ngưỡng trở lên** tiếp tục đi qua (chẳng hạn WARN/ERROR vào console).
- `LevelFilter` so sánh **bằng một level duy nhất**. Muốn chỉ lưu ERROR, có thể chọn level ERROR, `onMatch=ACCEPT`, `onMismatch=DENY`.
- Mỗi filter trả một trong `DENY`, `NEUTRAL`, `ACCEPT`. `DENY` chặn; `ACCEPT` cho phép; `NEUTRAL` để bộ lọc tiếp tục xem xét. Khi phối nhiều filter, thứ tự và trạng thái kết quả quan trọng.

Ví dụ appender chỉ nhận đúng `ERROR`, bỏ `WARN`, `INFO`, `DEBUG`:

```xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>ERROR</level>
    <onMatch>ACCEPT</onMatch>
    <onMismatch>DENY</onMismatch>
</filter>
```

Đoạn này đặt **bên trong appender** cần lọc. Không ghép thêm nguyên appender mới nếu đã có sink tương ứng. Hãy thử cả event ở mức ERROR và WARN để xác nhận bộ lọc đúng; filter của appender hoạt động sau cổng enabled của logger.

Với nhiều appender, chính sách “console WARN, file INFO” nên thể hiện ngay trên từng appender/filter (hoặc trên appender reference nếu framework hỗ trợ), trong khi logger level mô tả mức log nghiệp vụ được phép tạo.

## 6. Cấu hình một package chỉ ghi vào một đích

Khi cần tách log một package khỏi root, có thể cấu hình:

```xml
<logger name="com.example.audit"
        level="INFO" additivity="false">
    <appender-ref ref="AUDIT_FILE"/>
</logger>
```

Ý nghĩa:
- Logger có tên bắt đầu bằng package `com.example.audit`, nếu kế thừa theo cấu trúc logger phù hợp, sẽ chọn cấu hình này.
- `additivity=false` ngăn truyền event tiếp lên appender của tổ tiên (bao gồm root).
- Nếu quên tham chiếu `AUDIT_FILE`, event có thể không tới bất kỳ đích ghi mong muốn nào.
- Nếu giữ `additivity=true` và đồng thời gắn `AUDIT_FILE` vào một ancestor, dễ gửi trùng event tới cùng appender hoặc thêm đường ra ngoài dự kiến.

Một tình huống khác: vừa muốn log audit riêng, **vừa** muốn WARN/ERROR audit lên console vận hành. Khi đó có thể tham chiếu trực tiếp cả `AUDIT_FILE` và `CONSOLE` ở logger audit với `additivity=false`; filter `CONSOLE` vẫn chỉ nhận WARN trở lên. Đừng đổi `additivity` toàn cục nếu chỉ một namespace cần route đặc biệt.

### 6.1. Kế thừa level không đồng nghĩa kế thừa layout

Logger con có thể kế thừa **effective level** từ cha và nhận event qua appender gắn ở các ancestor. Nhưng pattern/encoder của `CONSOLE` vẫn là pattern của console; pattern/encoder của `APP_FILE` vẫn là của file. Logger không có một “layout cấp cha” để áp lên mọi appender. Nhờ đó một event có thể xuất hiện ngắn gọn ở terminal và có nhiều metadata hơn trong file.

## 7. Ví dụ tương đương trong Log4j 2

Log4j 2 dùng `Appender`, `AppenderRef` và các filter/level trên logger hoặc reference. Ví dụ file `src/main/resources/log4j2.xml` trong ứng dụng **đã chọn Log4j 2 Core làm backend**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout charset="UTF-8"
                pattern="%d{HH:mm:ss.SSS} %-5level %c{1.} - %msg%n"/>
        </Console>

        <RollingFile name="APP_FILE"
            fileName="logs/application.log"
            filePattern="logs/application-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout charset="UTF-8"
                pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%t] %c - %msg%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="20MB"/>
            </Policies>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Logger name="com.example.payment" level="DEBUG"/>

        <Root level="INFO">
            <AppenderRef ref="CONSOLE" level="WARN"/>
            <AppenderRef ref="APP_FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

Ở đây `CONSOLE` là một appender với pattern riêng; `AppenderRef ref="CONSOLE" level="WARN"` lọc **tại reference từ root tới console**, thay vì dùng Logback `ThresholdFilter` bên trong appender. `APP_FILE` lưu từ INFO cho logger thông thường; event DEBUG từ `com.example.payment` cũng tới `APP_FILE` qua additivity. Không dùng đồng thời Logback và Log4j 2 backend trong cùng application chỉ để áp dụng hai ví dụ này.

Lưu ý quan trọng với `RollingFile`:

- `TimeBasedTriggeringPolicy` và `SizeBasedTriggeringPolicy` được đặt cùng dưới `Policies`. `%d` thể hiện thời gian archive, `%i` là chỉ số tăng cho các rollover nhiều lần trong cùng kỳ.
- **Rollover không tự động bằng retention vô hạn hay 14/30 ngày**. Muốn xóa archive theo tuổi/dung lượng tổng phải cấu hình `RolloverStrategy`/`Delete` phù hợp hoặc quản lý retention bên ngoài; ví dụ này chưa đưa retention hoàn chỉnh để tránh đồng nhất `max index` với “số ngày lưu”.
- Khi thêm JSON layout, kiểm tra dependency/layout thực sự có trên classpath (ví dụ `JsonTemplateLayout` thường cần module riêng). `PatternLayout` trong ví dụ đủ để chạy trên cấu hình Log4j 2 Core thông thường.
- Log4j 2 hỗ trợ filter ở các vị trí khác nhau (global, logger, appender, appender reference); một filter tại reference không nhất thiết ảnh hưởng các logger tham chiếu trực tiếp cùng appender.

Nếu dùng Spring Boot, phải chọn starter/backend tương thích và tránh giữ thêm Logback trên classpath gây xung đột lựa chọn binding SLF4J. File cấu hình cần đúng tên và vị trí theo backend đang dùng.

## 8. Java chuẩn: ví dụ chạy được với từng Handler

Không cần thư viện ngoài để thấy nguyên lý “logger cho phép event, mỗi đích lại lọc riêng”. JUL dùng `java.util.logging.Logger` và `java.util.logging.Handler`. Ví dụ sau cấu hình **console chỉ WARNING trở lên**, **file nhận INFO trở lên**; logger cho phép từ FINE trở lên.

Lưu thành `PerHandlerDemo.java`:

```java
import java.io.IOException;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PerHandlerDemo {
    private static final class OneLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName()
                    + " " + formatMessage(record) + "\n";
        }
    }

    public static void main(String[] args) throws IOException {
        Logger logger = Logger.getLogger("demo.application");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        Handler console = new ConsoleHandler();
        console.setLevel(Level.WARNING);
        console.setFormatter(new OneLineFormatter());

        FileHandler file = new FileHandler("demo.log", false);
        file.setLevel(Level.INFO);
        file.setEncoding("UTF-8");
        file.setFormatter(new OneLineFormatter());

        logger.addHandler(console);
        logger.addHandler(file);

        try {
            logger.info("Started");
            logger.fine("Cache detail");
            logger.warning("Disk nearly full");
        } finally {
            logger.removeHandler(console);
            logger.removeHandler(file);
            console.close();
            file.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+ ở thư mục có quyền ghi file:

```bash
javac --release 17 PerHandlerDemo.java
java PerHandlerDemo
cat demo.log
```

`ConsoleHandler` mặc định ghi ra **stderr**, vì vậy riêng lệnh `java PerHandlerDemo` không ghi gì ra stdout. Output stderr của lệnh Java:

```text
WARNING Disk nearly full
```

Sau đó nội dung `demo.log` (đồng thời là stdout của lệnh `cat demo.log`):

```text
INFO Started
WARNING Disk nearly full
```

`FINE Cache detail` bị loại tại cả hai handler, mặc dù logger đã cho phép event FINE. Đối với console, `INFO Started` bị loại vì ngưỡng WARNING. Với file, INFO và WARNING đều đạt ngưỡng. `setUseParentHandlers(false)` ngăn handler của logger cha in thêm một bản nữa. Khi chương trình kết thúc, `close()` flush và đóng hai handler; không nên để mở handler file không cần thiết.

Trong PowerShell có thể dùng:

```powershell
javac --release 17 PerHandlerDemo.java
java PerHandlerDemo
Get-Content demo.log
```

Nếu chạy nhiều lần, `new FileHandler("demo.log", false)` sẽ **ghi lại** file thay vì append; điều này chỉ để kết quả ví dụ dễ đối chiếu. Không áp dụng `append=false` cho file log production nếu không muốn mất log cũ mỗi lần khởi động. Khi file đang bị process khác khóa, JUL có thể chọn tên file khác theo quy tắc unique lock hoặc không tạo được; ví dụ giả định không có process khác dùng `demo.log`.

Đối chiếu thuật ngữ:

| JUL | Logback/Log4j 2 | Ý nghĩa |
| --- | --- | --- |
| `Logger` | Logger | Phát event và kiểm tra effective level |
| `Handler` | Appender | Đưa event tới destination |
| `Handler.setLevel(...)` | Filter/threshold hoặc reference level | Lọc theo đích |
| `Formatter` | Layout/Encoder | Chuyển event thành text/bytes |
| `setUseParentHandlers(false)` | `additivity=false` (khái niệm gần tương tự) | Ngăn gửi event tới handler/appender của cha |
| `FileHandler` | File/Rolling appender | Đầu ra file, nhưng tính năng rolling không giống nhau |

## 9. Đặt AsyncAppender ở đâu trong thiết kế?

Một appender async **không phải đích lưu trữ cuối cùng**. Nó thường là lớp trung gian có queue và worker, phía sau là file/console/network appender. Với Logback, thay appender-ref ở root từ sink trực tiếp sang async:

```xml
<appender name="ASYNC_FILE" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>10000</maxFlushTime>
    <appender-ref ref="APP_FILE"/>
</appender>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="ASYNC_FILE"/>
</root>
```

Đoạn này dùng **cùng APP_FILE đã định nghĩa trước đó** và minh họa việc thay thế riêng phần root; trong cấu hình đầy đủ phải tránh để root vẫn tham chiếu trực tiếp `APP_FILE` cùng lúc, nếu không một event có thể ghi file hai lần.

- `queueSize` tính theo event; không phải MB.
- `discardingThreshold=0` tắt cơ chế bỏ log mức thấp khi queue còn ít chỗ, nhưng không bảo đảm zero-loss.
- `neverBlock=false` cho phép thread gọi log chờ khi queue đầy; `true` ưu tiên giảm chờ bằng cách có thể bỏ event.
- `maxFlushTime` là hạn chờ lúc dừng appender, không phải timeout mỗi lần ghi.

Đích console ở root vẫn đồng bộ trong ví dụ. Nếu vừa muốn file async vừa muốn console async, cần cân nhắc tạo tuyến rõ ràng và đo queue/drop ở từng tuyến; không phải cứ bọc tất cả bằng async là tốt.

**Log4j 2 AsyncAppender và AsyncLogger khác nhau.** AsyncAppender bọc một hoặc nhiều appenders; AsyncLogger là cơ chế logger bất đồng bộ dựa trên ring buffer/Disruptor. Nếu ứng dụng đã dùng AsyncLogger, đừng thêm AsyncAppender chồng lên mọi sink mà không đo lợi ích và policy khi queue đầy.

## 10. Layout và dữ liệu context nên đặt theo từng đích

Hai appender có thể dùng cùng level nhưng biểu diễn khác nhau:

- **Terminal:** pattern ngắn để đọc nhanh, ví dụ thời gian, level, logger rút gọn, message.
- **File phục vụ truy vết:** pattern chi tiết hoặc JSON có thời gian ISO, logger, thread, `trace_id`, `span_id`, exception.
- **Hệ thống ingest tập trung:** log record có schema xác định, field types nhất quán, timestamp chuẩn; có thể chọn OTel logs bridge/exporter tùy kiến trúc.

Ví dụ pattern Logback có MDC:

```xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] trace_id=%X{trace_id} span_id=%X{span_id} %logger{36} - %msg%n</pattern>
```

`%X{trace_id}` chỉ đọc MDC; nó **không tự truyền trace context** qua thread hoặc HTTP. Nếu log message chứa newline/ký tự đặc biệt, output dạng text có thể khó parse hoặc bị log injection khi dữ liệu không tin cậy được ghép trực tiếp. Với collector cần phân tích chính xác, dùng encoder JSON đủ khả năng escape thông tin và chuẩn hóa field names.

Đặt charset UTF-8 tường minh để giảm lỗi tiếng Việt khi chuyển máy, kết hợp locale/timezone nhất quán giữa service và backend. Không ghi mật khẩu, access token, session cookie hay nội dung nhạy cảm vào log; cần mask trước khi đưa event tới bất kỳ appender nào. Một policy mask ở appender file không đảm bảo appender console khác cũng che thông tin.

## 11. File appender: rotation, retention và quyền truy cập

**Rotation** (rollover) là đổi file đang ghi sang archive khi đến thời gian/kích thước. **Retention** là quyết định archive nào được giữ/xóa. Chúng là hai khái niệm riêng:

- Logback `SizeAndTimeBasedRollingPolicy` có `maxFileSize`, `fileNamePattern` với `%d` và `%i`, `maxHistory`, `totalSizeCap`.
- Log4j 2 `RollingFile` dùng `Policies` để trigger và `RolloverStrategy`/delete action để quản lý tập archive.
- JUL `FileHandler` có size limit và count, nhưng không giả định tính năng xóa theo tuổi giống các rolling policy ở trên.

Hãy kiểm tra bốn vấn đề:

1. **Đường dẫn:** working directory, biến môi trường, mount volume, quyền file và folder. Dùng path tuyệt đối khi cần dự đoán chính xác nơi ghi.
2. **Dung lượng:** log hiện hành, archive, compression, batch/backup cùng dùng disk. Alert trước khi disk full; tổng giới hạn archive không bao phủ mọi file ngoài phạm vi.
3. **Nhiều process:** hai JVM cùng ghi một file có thể cạnh tranh khóa, gây hỏng thứ tự hoặc làm rollover khó dự đoán. Ưu tiên mỗi instance một stdout/file riêng hoặc cơ chế chia sẻ được tài liệu của framework hỗ trợ.
4. **Shutdown:** flush/close appender theo lifecycle. Với async, dừng khi queue còn event có thể khiến log cuối bị mất. Flush ở mức Java không tự bảo đảm backend xa đã lưu bền vững.

Nếu ứng dụng chạy trong Kubernetes/container, phương án phổ biến là ghi stdout/stderr và để tầng triển khai quản lý collection/rotation. Khi vẫn dùng RollingFileAppender, cần đảm bảo log directory được mount/quản lý đúng, tránh mất log khi container bị thay thế.

## 12. Kiểm tra cấu hình theo appender một cách có hệ thống

Đặt một bảng kiểm thử nhỏ với bốn event cùng logger/package:

```java
log.debug("cache hit");
log.info("request accepted");
log.warn("upstream slow");
log.error("operation failed", exception);
```

Đây là **đoạn minh họa trong method có biến `log` và `exception` hợp lệ**, không phải chương trình độc lập. Chạy trong ứng dụng thực và kiểm tra:

1. **Logger level:** trong namespace ở INFO, DEBUG không sinh; trong namespace DEBUG, DEBUG được sinh và còn phải qua filter từng sink.
2. **Từng destination:** ở cấu hình mẫu, console chỉ có WARN/ERROR, application file có INFO/WARN/ERROR (và DEBUG riêng cho payment).
3. **Audit routing:** event audit xuất hiện tại audit file, không tràn sang console/file chính khi `additivity=false`.
4. **Không duplicate:** nếu thấy hai bản của cùng event tại một file, kiểm tra root + child appender references, additivity, hai async đường vào cùng sink và log shipper ingest trùng.
5. **Rollover:** tạo đủ event để kích hoạt chính sách kích thước, xác nhận archive đúng `%d`/`%i` và retention sau rollover; đừng đánh giá chỉ từ tên file mẫu.
6. **Metadata:** timestamp, level, thread, logger, exception stack trace và MDC/trace ID có đúng từ lúc event được tạo?
7. **Lỗi sink:** làm đầy disk giả lập trong môi trường kiểm thử hoặc thay quyền ghi, theo dõi status/error reporting và tác động lên request latency.
8. **Shutdown:** dừng mềm khi có backlog, đo thời gian drain, xác nhận policy loss có thể chấp nhận.

Không dùng một dòng log “đã in lên terminal” làm bằng chứng file hay OTLP đã nhận event: mỗi appender là một đường delivery riêng.

## 13. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân điển hình | Cách xác minh/sửa |
| --- | --- | --- |
| Có log console nhưng file trống | Appender File chưa được tham chiếu; path không ghi được; filter/level | Kiểm tra cấu hình runtime và quyền thư mục, thử event đúng level |
| DEBUG không ghi dù file “cho DEBUG” | Logger effective level là INFO | Đặt logger/package đủ thấp rồi kiểm tra filter phía file |
| INFO vẫn xuất hiện trên console | Chưa đặt ThresholdFilter/reference level, hoặc có console appender khác | In danh sách appender được gắn, kiểm tra effective config |
| Log xuất hiện hai lần | Appender được tham chiếu trực tiếp và qua root/async; additivity; hai pipeline | Kiểm tra đường route và bộ thu |
| Không có stack trace đầy đủ | Pattern/layout không xử lý throwable; exception log sai tham số | Dùng overload nhận Throwable, kiểm tra encoder/layout thực tế |
| File tăng vô hạn | Chỉ dùng FileAppender hoặc chưa có retention/delete | Bật rolling + retention thật sự và giám sát disk |
| Archive đè lên nhau | Thiếu `%i` khi dùng đồng thời time/size; pattern trùng giữa instance | Kiểm tra fileNamePattern và từng process |
| Log chậm dù đã async | Sink nghẽn làm queue đầy, producer block | Đo queue depth, policy khi full, I/O thực tế |
| MDC/trace_id trống trong file | Context chưa được gán/propagate, hoặc pattern sai | Kiểm tra producer context, instrumentation và MDC key |
| Cấu hình XML không được áp dụng | Sai tên file, backend, package binding hoặc lỗi cú pháp | Kiểm tra startup status/config debug của backend |

Tránh đặt cả Logback lẫn Log4j 2 binding làm backend hoạt động cùng lúc; SLF4J chỉ nên có một provider phù hợp. Khi dùng Spring Boot, đừng thay đổi `logback-spring.xml` và `log4j2.xml` cùng lúc rồi kết luận từ file nào “trông đúng” — xác định backend thực sự đã được ứng dụng load.

## 14. Quy trình chọn cấu hình theo appender

Một trình tự thực dụng khi thiết kế:

1. **Liệt kê đầu ra:** console, rolling application file, audit file, collector, hệ thống quản trị.
2. **Quy định sự kiện nào cần tới mỗi đích:** mức log, namespace, môi trường, chính sách dữ liệu nhạy cảm.
3. **Đặt logger level đủ để tạo event cần thiết**, sau đó áp filter/reference level riêng từng destination.
4. **Định nghĩa format/schema** cho từng đích, bảo đảm tương thích trình đọc và trace correlation.
5. **Đặt rotation, retention, quyền ghi và resource limits**, nhất là với file và async queue.
6. **Kiểm tra additivity/route** để không mất event hoặc tạo bản sao bất ngờ.
7. **Thử tải, failure và graceful shutdown**, xác minh số event vào/ra và mất log.

Một cấu hình được coi là đúng khi log đi tới **đúng đích, đúng mức, đúng format**, với giới hạn tài nguyên và tác động tới ứng dụng được hiểu rõ. Appender là nơi gắn chính sách của từng output; logger level và routing quyết định luồng event mà các chính sách đó được áp dụng.

## Tài liệu tham khảo

- [Logback – Architecture: logger level và additivity](https://logback.qos.ch/manual/architecture.html)
- [Logback – RollingFileAppender, rolling policies và retention](https://logback.qos.ch/manual/appenders-rolling.html)
- [Logback – Filter, ThresholdFilter, LevelFilter](https://logback.qos.ch/manual/filters.html)
- [Apache Log4j 2 – Cấu hình logger, AppenderRef, additivity](https://logging.apache.org/log4j/2.x/manual/configuration.html)
- [Apache Log4j 2 – Rolling file appenders và triggering policies](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html)
- [JDK 21 – java.util.logging.Handler](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Handler.html)
- [JDK 21 – java.util.logging.FileHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/FileHandler.html)