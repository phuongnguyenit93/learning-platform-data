# Nhiều appender trong Java logging

## 1. Nhiều appender là gì?

Trong hệ thống logging, **appender** là thành phần nhận sự kiện log từ logger và đưa chúng tới một **đích xuất** như console, file, hoặc hệ thống thu thập. **Nhiều appender (multiple appenders)** có nghĩa là một logger hoặc một cấu hình logger có thể phân phối **cùng một sự kiện** tới hai hay nhiều đích, thay vì buộc mã nghiệp vụ gọi một logger khác cho từng nơi muốn ghi.

Ví dụ ứng dụng xử lý đơn hàng:

- `INFO`, `WARN` và `ERROR` được đưa ra **console** để quan sát khi chạy.
- `WARN` và `ERROR` được lưu thêm vào **file** để điều tra.
- Nếu hạ tầng cần dữ liệu có cấu trúc, một đích thu thập khác có thể nhận event theo định dạng JSON.

```text
                         Một sự kiện WARN
                                 │
                            Logger
                                 │
                ┌────────────────┴────────────────┐
                ▼                                 ▼
       Console Appender                     File Appender
         INFO trở lên                       WARN trở lên
                │                                 │
                ▼                                 ▼
              stdout                        warnings.log
```

Khi cùng một `WARN` xuất **một lần trên console và một lần trong file**, đó là **fan-out có chủ đích**. Khi nó xuất **hai lần trên cùng console** vì logger con và root cùng gọi một appender, đó thường là **log trùng do cấu hình**.

**Lưu ý về thuật ngữ:** Log4j2 và Logback gọi thành phần xuất log là **Appender**; thư viện chuẩn JDK `java.util.logging` (JUL) gọi thành phần tương đương là **Handler**. Bài học dùng Log4j2 cho ví dụ chính, sau đó đối chiếu với Logback/JUL. Ba framework không dùng chung cú pháp cấu hình.

## 2. Khi nào cần nhiều appender?

Một số mục tiêu thường gặp:

| Nhu cầu | Đích logging có thể dùng | Điểm cần quản lý |
| --- | --- | --- |
| Quan sát ứng dụng khi phát triển | Console | Level dễ đọc, không quá nhiều noise |
| Theo dõi lỗi trên máy chủ | Console + RollingFile | Rotation, dung lượng đĩa, quyền ghi |
| Thu thập log từ container | Stdout/stderr → collector | Định dạng, nhãn service, instance |
| Phân tích dữ liệu log theo trường | JSON appender/encoder hoặc collector | Schema, correlation ID, dữ liệu nhạy cảm |
| Audit có yêu cầu riêng | Đích audit tách biệt | Quyền, retention, tính toàn vẹn, không coi log thường là audit bền vững |

Không phải cứ nhiều appender là tốt. Nếu nền tảng đã lấy stdout đưa tới một hệ thống tập trung rồi sao chép ra nhiều kho lưu trữ, việc thêm network appender vào JVM có thể tăng độ phức tạp và lưu trùng. Trước khi cấu hình, hãy xác định **ai chịu trách nhiệm phân phối cuối cùng**: ứng dụng, collector hay nền tảng triển khai.

### Các thành phần trong đường đi log

- **Logger:** nhận lời gọi `LOG.info(...)`, `LOG.error(...)` và xác định level hiệu lực.
- **Event:** chứa level, message, logger name, thread, exception, context và metadata tùy framework.
- **Appender:** chuyển event tới một đích; một appender có thể được tham chiếu từ nhiều logger.
- **AppenderRef:** trong Log4j2, kết nối cấu hình logger/root với một appender đã khai báo.
- **Layout/encoder:** định dạng nội dung khi ghi.
- **Filter:** chấp nhận, loại bỏ hoặc cho các bước xử lý tiếp tục đánh giá event.
- **Root logger:** cấu hình chung và là điểm có thể nhận sự kiện của logger con theo quan hệ phân cấp.

**Mã nghiệp vụ phát sự kiện; cấu hình logging chọn đích.** Đó là lý do không nên tạo `consoleLogger` và `fileLogger` riêng rồi gọi cả hai cho mỗi sự kiện.

## 3. Level của logger và mức lọc của appender khác nhau

Đây là lỗi cấu hình dễ gặp nhất khi có nhiều đích.

Giả sử logger có level `DEBUG`. Điều đó **không có nghĩa** mọi appender phải in DEBUG. Một cấu hình có thể chọn console chỉ xuất INFO+, file chỉ xuất WARN+. Khi đó:

| Sự kiện phát sinh | Logger DEBUG chấp nhận? | Console INFO+ | File WARN+ |
| --- | --- | --- | --- |
| `LOG.debug("Cache hit")` | Có | Không | Không |
| `LOG.info("Order accepted")` | Có | Có | Không |
| `LOG.warn("Inventory low")` | Có | Có | Có |
| `LOG.error("Payment failed")` | Có | Có | Có |
| `LOG.fatal("Cannot start")` | Có | Có | Có |

Bảng giả định appender đã được tham chiếu đúng, không có filter phụ và đích ghi hoạt động. **Mỗi AppenderRef/appender lọc độc lập**: một event có thể được logger tạo ra nhưng chỉ được một appender nhận.

Trong **Log4j2**, có thể đặt mức lọc ngay trên AppenderRef:

```xml
<Root level="debug">
    <AppenderRef ref="Console" level="info"/>
    <AppenderRef ref="WarningFile" level="warn"/>
</Root>
```

Đây là **mảnh cấu hình**, chưa bao gồm phần khai báo hai appender. Các level trên AppenderRef là ngưỡng của từng đường nhận sự kiện, trong khi `Root level="debug"` là ngưỡng của logger gốc. Nếu root bị nâng lên `ERROR`, event WARN không còn được root chấp nhận; hạ ngưỡng appender xuống WARN **không khôi phục** event đã bị lọc ở logger.

Luồng xử lý khái quát:

```text
LOG.warn(...)
   │
   ▼
Logger có tạo WARN event?
   │ Có
   ▼
Sự kiện WARN
   ├─ Console AppenderRef INFO: chấp nhận ──> Console
   └─ WarningFile AppenderRef WARN: chấp nhận ──> File
```

Ngoài level, filter được đặt ở logger, appender reference hoặc appender có thể thay đổi kết quả. Vì thế hãy xét **từng chặng**, không kết luận chỉ từ mức root.

## 4. Ví dụ Log4j2 Java 17 + Maven: Console và File

Ví dụ độc lập này dùng **Log4j2 API** để tạo log và **Log4j2 Core** để xuất sự kiện. Không cần Spring Boot hay SLF4J. Sau một lần chạy sẽ có log trên console và trong file, nhưng **nội dung mỗi đích khác nhau** do ngưỡng level.

### 4.1. Cấu trúc dự án

```text
multi-appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── MultipleAppendersDemo.java
        └── resources/
            └── log4j2.xml
```

### 4.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-appender-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Các phiên bản được ghim để ví dụ có một bộ dependency rõ ràng; chúng **không phải lời khẳng định về phiên bản mới nhất**. Trong dự án thật, đồng bộ phiên bản Log4j2 theo cấu hình quản lý dependencies và bản vá được duy trì.

### 4.3. Tệp src/main/resources/log4j2.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>

        <File name="WarningFile"
              fileName="logs/application.log"
              append="false">
            <PatternLayout pattern="%level | %msg%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="debug">
            <AppenderRef ref="Console" level="info"/>
            <AppenderRef ref="WarningFile" level="warn"/>
        </Root>
    </Loggers>
</Configuration>
```

Ý nghĩa cấu hình:

1. `Console` viết ra `SYSTEM_OUT`. `WarningFile` viết vào `logs/application.log` tương đối với thư mục làm việc.
2. Cả hai dùng `PatternLayout` để in một dòng dạng `INFO | message`.
3. Root logger cho phép DEBUG trở lên để event đi tới bước phân phối.
4. AppenderRef Console chỉ chuyển INFO/WARN/ERROR/FATAL.
5. AppenderRef WarningFile chỉ chuyển WARN/ERROR/FATAL.
6. `append="false"` làm file của **demo** được ghi đè khi appender khởi tạo, để kết quả file không cộng dồn qua các lần chạy. Với ứng dụng thực, **không dùng tùy chọn này nếu cần giữ lịch sử**; hãy cấu hình append/rolling phù hợp.

Đây là ví dụ tối giản về phân phối log, chưa có rolling policy, JSON hoặc exception stack trace. Phần bên dưới sẽ giới thiệu các yếu tố đó khi có nhu cầu.

### 4.4. Tệp src/main/java/demo/MultipleAppendersDemo.java

```java
package demo;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class MultipleAppendersDemo {
    private static final Logger LOG =
            LogManager.getLogger(MultipleAppendersDemo.class);

    public static void main(String[] args) {
        String orderId = "ORD-42";

        LOG.debug("Cart validation started");
        LOG.info("Order {} accepted", orderId);
        LOG.warn("Inventory below threshold: {}", 2);
        LOG.error("Payment gateway unavailable for {}", orderId);

        System.out.println("application-finished");
    }
}
```

### 4.5. Chạy và kiểm tra hai đích

Với JDK 17+ và Maven, thực hiện ở thư mục `multi-appender-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.MultipleAppendersDemo
```

**Stdout do chương trình và Console appender tạo ra**, bỏ qua thông báo riêng của Maven:

```text
INFO | Order ORD-42 accepted
WARN | Inventory below threshold: 2
ERROR | Payment gateway unavailable for ORD-42
application-finished
```

**Nội dung file `logs/application.log`:**

```text
WARN | Inventory below threshold: 2
ERROR | Payment gateway unavailable for ORD-42
```

Xem file trên Linux/macOS:

```bash
cat logs/application.log
```

Hoặc trong PowerShell:

```powershell
Get-Content logs/application.log
```

Kết quả đúng khi môi trường tải `log4j2.xml` như đã viết, filesystem cho phép tạo file và không có cấu hình bên ngoài ghi đè. Nếu `DEBUG` xuất trên console, có thể ứng dụng đang dùng cấu hình khác hoặc một appender khác. Nếu file trống hoặc không tồn tại, kiểm tra mức ref, file path, quyền ghi và status logging.

**Tự thử:** đổi `<AppenderRef ref="WarningFile" level="warn"/>` thành `level="info"`, chạy lại và so sánh file: lúc này file dự kiến có thêm dòng INFO. Đổi root thành `level="error"`: cả INFO và WARN đều không xuất dù hai AppenderRef vẫn có ngưỡng thấp hơn.

## 5. Không cần một logger riêng cho từng đích

Nếu muốn ghi cùng sự kiện đến console và file, không nên viết:

```java
consoleLogger.warn("Inventory low");
fileLogger.warn("Inventory low");
```

Hai lời gọi trên là **hai sự kiện khác nhau**, làm logic nghiệp vụ phụ thuộc việc xuất log. Mỗi khi thêm đích thứ ba lại phải đổi source code. Với nhiều appender, chỉ cần:

```java
LOG.warn("Inventory low");
```

và cấu hình chịu trách nhiệm fan-out. Đoạn này giả định biến logger đã được khai báo. **Đích ghi và format thuộc backend, nội dung sự kiện thuộc nghiệp vụ.** Khi muốn gửi tới hệ thống thu thập tập trung, có thể thay cấu hình appender/collector mà không phải sửa mọi lời gọi `LOG.warn(...)`.

Một appender còn có thể được **nhiều logger** tham chiếu. Không nhất thiết tạo một Console appender vật lý riêng cho từng class; dùng chung một đích theo root/package thường đơn giản và nhất quán hơn.

## 6. Additivity: vì sao một dòng bị in trùng?

**Additivity** là cơ chế chuyển event từ cấu hình logger con lên appender của logger cha hoặc root. Nó giúp logger con **kế thừa đường xuất chung**, nhưng cũng có thể gây log trùng.

Ví dụ Log4j2 dễ in trùng nếu appender `Console` được khai báo ở cả logger `demo.payment` và root:

```xml
<Loggers>
    <Logger name="demo.payment" level="debug">
        <AppenderRef ref="Console"/>
    </Logger>
    <Root level="info">
        <AppenderRef ref="Console"/>
    </Root>
</Loggers>
```

Đây là **mảnh XML**, giả định appender `Console` tồn tại. Logger con có thể xử lý một event tại `Console`, sau đó do additivity mặc định tiếp tục đưa tới root và xử lý lại qua `Console`.

**Hai cách khắc phục:**

- **Chỉ gắn appender ở root:** logger con đặt level riêng khi cần nhưng không tham chiếu lại cùng console.
- **Logger con quản lý đích riêng:** đặt `additivity="false"` và tham chiếu **đầy đủ** mọi đích mà nó cần.

Ví dụ phương án thứ hai:

```xml
<Logger name="demo.payment" level="debug" additivity="false">
    <AppenderRef ref="Console" level="info"/>
    <AppenderRef ref="WarningFile" level="warn"/>
</Logger>
```

**Cảnh báo:** nếu tắt additivity nhưng chỉ tham chiếu Console, event của logger này sẽ không đi lên WarningFile chỉ có ở root. Không dùng `additivity="false"` một cách máy móc; trước hết phải vẽ đường đi thực tế của event.

Phân biệt rõ:

- **Fan-out đúng:** một WARN xuất ở console và file, mỗi đích một lần.
- **Duplicate sai:** một WARN xuất hai lần trong console vì hai tầng cùng tham chiếu console.
- **Duplicate từ application code:** exception bị log ở repository, service và controller, tạo ba sự kiện độc lập, rồi mỗi sự kiện lại được phân phối tới hai appender.

## 7. Mỗi appender có thể có layout và chính sách khác nhau

Một event không nhất thiết phải có cùng định dạng tại mọi đích:

| Đích | Định dạng gợi ý | Vì sao? |
| --- | --- | --- |
| Console | Ngắn: level, logger, message | Dễ xem trong terminal |
| File điều tra | Timestamp, thread, logger, message, stack trace | Hỗ trợ truy tìm lỗi |
| Collector | Structured JSON theo schema | Tìm kiếm theo field và correlation ID |
| Audit chuyên biệt | Các trường được chọn, có bảo vệ | Yêu cầu tuân thủ và truy vết |

Mảnh cấu hình Log4j2 minh họa hai pattern khác nhau, đặt bên trong phần `<Appenders>` của một file đầy đủ:

```xml
<Console name="ReadableConsole" target="SYSTEM_OUT">
    <PatternLayout
        pattern="%d{HH:mm:ss} %-5level %logger{1} - %msg%n"/>
</Console>

<File name="DetailedFile" fileName="logs/detailed.log">
    <PatternLayout
        pattern="%d{ISO8601} %-5level [%t] %logger requestId=%X{requestId} - %msg%n%ex"/>
</File>
```

Một số ký hiệu: `%d` là thời gian; `%t` là tên thread; `%logger` là logger name; `%msg` là message; `%n` là xuống dòng; `%ex` là exception stack trace; `%X{requestId}` là trường context nếu được đặt.

Trong Log4j2, API `ThreadContext` cung cấp dữ liệu tương quan; tương tự, thế giới SLF4J/Logback thường nói đến **MDC (Mapped Diagnostic Context)**. Context có thể khác nhau theo backend và bridge. Muốn một trường xuất ở đích nào, layout/encoder của **đích đó** cần hỗ trợ. Không mặc định việc có `requestId` trong bộ nhớ sẽ làm mọi appender tự in nó.

Để dùng output JSON, chọn module/layout thích hợp như `JsonTemplateLayout` và module `log4j-layout-template-json` (nếu phiên bản/thiết kế hỗ trợ), thay vì tưởng rằng mọi appender mặc định tạo JSON. Các trường nhạy cảm cần bị loại hoặc che từ lúc phát event; chỉ trông vào layout không phải biện pháp bảo vệ đầy đủ.

## 8. RollingFile: đừng để file tăng mãi

File appender trong demo đủ để hiểu phân phối event, nhưng không tự bảo đảm rotation/retention. Với production, **RollingFile** thường phù hợp hơn một file tăng vô hạn.

Mảnh cấu hình Log4j2 trong `<Appenders>`:

```xml
<RollingFile name="RollingFile"
             fileName="logs/application.log"
             filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
    <PatternLayout
        pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
    <Policies>
        <SizeBasedTriggeringPolicy size="10 MB"/>
        <TimeBasedTriggeringPolicy/>
    </Policies>
    <DefaultRolloverStrategy max="5"/>
</RollingFile>
```

Và trong một logger/root:

```xml
<AppenderRef ref="RollingFile" level="warn"/>
```

`RollingFile` có thể xoay theo kích thước, thời gian và chiến lược đã cấu hình. Tuy nhiên, `max="5"` trong chiến lược rollover **không đương nhiên có nghĩa giữ log đúng năm ngày**. Cần kiểm tra pattern, số phiên bản, chính sách xóa file và quyền truy cập thực tế.

Trong container, một số hệ thống ưu tiên stdout/stderr do nền tảng thu thập. Việc đồng thời ghi file cục bộ và collector bên ngoài có thể tăng đĩa/I/O mà không đem lại lợi ích nếu file không được lưu bền vững sau khi container thay thế.

## 9. Ví dụ với Logback: cùng khái niệm, khác cú pháp

Nếu ứng dụng dùng facade **SLF4J** và backend **Logback Classic**, appender vẫn có vai trò tương tự nhưng cấu hình là `logback.xml`, không phải `log4j2.xml`.

Đoạn XML sau là **một file cấu hình Logback minh họa**:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>INFO</level>
        </filter>
        <encoder>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="WARNING_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/warnings.log</file>
        <append>true</append>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="DEBUG">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="WARNING_FILE"/>
    </root>
</configuration>
```

`ThresholdFilter` ở Console chỉ cho INFO trở lên, còn filter ở file chỉ cho WARN trở lên. Root DEBUG là ngưỡng đầu vào của pipeline.

**Đừng sao chép thuộc tính `level` của `AppenderRef` trong Log4j2 sang `appender-ref` của Logback** rồi kỳ vọng ngưỡng được áp giống nhau. Cú pháp và filter giữa các backend khác nhau. Logback `FileAppender` cũng không tự rolling; khi cần chuyển file, dùng `RollingFileAppender` và rolling policy được cấu hình đúng.

Nếu ứng dụng Spring Boot dùng Logback mặc định, thay `log4j2.xml` của ví dụ chính bằng file Logback ở trên mà không thay backend thì phần Log4j2 XML không có tác dụng. Luôn xác định implementation đang được nạp.

## 10. JUL: nhiều handler thay vì nhiều appender

JUL thuộc JDK dùng `Handler` cho chức năng đưa log tới nhiều đích. Tên API khác nhưng nguyên tắc **một logger → nhiều nơi nhận** vẫn đúng.

Ví dụ Java 17 đầy đủ, không cần dependency ngoài JDK. Tạo file `MultiHandlerDemo.java`:

```java
import java.io.IOException;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MultiHandlerDemo {
    public static void main(String[] args) throws IOException {
        Logger logger = Logger.getLogger("demo.MultiHandlerDemo");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        Formatter shortFormat = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        };

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(shortFormat);

        FileHandler file = new FileHandler("jul-events.log", false);
        file.setLevel(Level.WARNING);
        file.setFormatter(shortFormat);

        logger.addHandler(console);
        logger.addHandler(file);

        try {
            logger.fine("Hidden detail");
            logger.info("Order accepted");
            logger.warning("Inventory low");
            logger.severe("Payment failed");
            System.out.println("jul-finished");
        } finally {
            logger.removeHandler(console);
            logger.removeHandler(file);
            console.close();
            file.close();
        }
    }
}
```

Chạy:

```bash
javac MultiHandlerDemo.java
java MultiHandlerDemo
```

**Các dòng `ConsoleHandler` trên stderr:**

```text
INFO | Order accepted
WARNING | Inventory low
SEVERE | Payment failed
```

**Stdout do chương trình in:**

```text
jul-finished
```

**Tệp `jul-events.log`:**

```text
WARNING | Inventory low
SEVERE | Payment failed
```

`ConsoleHandler` của JUL mặc định ghi **stderr**, khác với `SYSTEM_OUT` trong ví dụ Log4j2. Vì stderr/stdout là hai luồng riêng, không giả định thứ tự hiển thị kết hợp là tuyệt đối trong mọi terminal. `FileHandler` ở đây ghi file mới và có thể tạo file khóa nội bộ tạm thời trong quá trình chạy; ví dụ đóng handler khi hoàn tất.

Chú ý `logger.setUseParentHandlers(false)` để tránh bản ghi tiếp tục tới handler mặc định của root JUL, có thể gây in trùng. Đây là ví dụ chương trình độc lập; trong ứng dụng thực, hãy lưu/khôi phục cấu hình khi cần và quản lý handler theo vòng đời. **Level logger và level từng handler là hai bước lọc riêng**, giống nguyên tắc của nhiều appender.

## 11. AsyncAppender: phân phối không đồng nghĩa luôn đồng bộ

Khi có nhiều đích, tổng chi phí có thể tăng: mỗi event có thể cần format nhiều lần và ghi vào nhiều thiết bị. Nếu một appender ghi file/network chậm, thời gian xử lý log có thể ảnh hưởng luồng nghiệp vụ.

Log4j2 cung cấp cơ chế **AsyncAppender** và **AsyncLogger**. Chúng không phải là cùng một thành phần:

- **AsyncAppender:** một appender bất đồng bộ nhận event rồi chuyển qua hàng đợi tới các appender đích.
- **AsyncLogger:** cơ chế xử lý bất đồng bộ tại tầng logger, có yêu cầu dependency/cấu hình riêng theo phiên bản.

Mảnh XML minh họa:

```xml
<Async name="AsyncWarningFile">
    <AppenderRef ref="RollingFile"/>
</Async>
```

Logger muốn xuất bất đồng bộ tới file cần tham chiếu `AsyncWarningFile` thay vì tham chiếu `RollingFile` trực tiếp trên cùng đường log. Nếu **cả hai** cùng được tham chiếu, một event có thể ghi file **hai lần**.

Không có cam kết rằng async **luôn nhanh hơn**: phải đo throughput, latency và độ đầy hàng đợi. Khi JVM crash hoặc bị kill đột ngột, event còn trong queue/buffer có thể chưa tới đích. Khi nhiều appender chạy bất đồng bộ, thứ tự bản ghi quan sát được giữa hai đích cũng có thể khác nhau. Hãy kiểm thử overflow, shutdown/flush và khả năng vận hành thực tế.

## 12. Bảo mật và độ tin cậy khi ghi nhiều đích

**Nhiều bản sao log đồng nghĩa nhiều nơi cần kiểm soát truy cập.** Một event có thể chứa stack trace, đường dẫn file, query hoặc dữ liệu người dùng. Console, file và collector có thể có retention/quyền đọc khác nhau. Không ghi password, token, API key, cookie xác thực hay thông tin cá nhân nhạy cảm rồi chỉ mong một appender che được chúng.

Một số nguyên tắc:

1. **Ẩn dữ liệu tại nguồn:** không xây message chứa bí mật; dùng correlation ID an toàn.
2. **Đặt level hợp lý theo đích:** tránh đưa TRACE/DEBUG nhạy cảm ra file/collector không cần thiết.
3. **Giới hạn file:** rotation, retention, quyền ghi/đọc và giám sát ổ đĩa.
4. **Kiểm tra lỗi appender:** file không có quyền ghi, collector không khả dụng, hàng đợi đầy.
5. **Đừng nhầm hai đích với sao lưu bền vững:** console+file trên cùng máy không thay thế transaction, outbox hoặc kho audit chống sửa đổi.
6. **Bảo vệ cấu hình:** chỉ người có quyền được đổi appender/level và nơi nhận log.
7. **Kiểm thử exception:** cùng một Throwable có thể đi tới nhiều layout; phải bảo đảm stack trace không bị bỏ hoặc vô tình in trùng.
8. **Hạn chế log trùng ở tầng mã:** nếu repository và controller cùng log đầy đủ exception rồi mỗi event tới hai appender, số dòng có thể tăng nhanh.

Với các sự kiện có ý nghĩa audit bắt buộc, cần một thiết kế lưu trữ đáng tin cậy có chính sách tính toàn vẹn, kiểm soát quyền và retention riêng. **Appender thông thường không tự cung cấp bảo đảm audit bất biến**.

## 13. Chẩn đoán sự cố nhiều appender

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| INFO có trên console nhưng không có trong file | File AppenderRef ở WARN | Nếu cần INFO trong file, đổi đúng ngưỡng |
| DEBUG không ra dù root DEBUG | Các AppenderRef INFO/WARN chặn DEBUG | Kiểm tra level theo từng đích |
| WARN hiện hai lần trên console | Logger con và root đều tham chiếu console, additivity bật | Giữ một đường ref hoặc tắt additivity khi có đầy đủ đích |
| WARN xuất một lần trên console, một trong file | Hai appender được cấu hình nhận WARN | Đây là fan-out đúng |
| File bị mất sau mỗi lần chạy | `append="false"` làm ghi đè file | Dùng append/rolling theo yêu cầu vận hành |
| File không tạo | Cấu hình không được nạp, thiếu quyền, sai path hoặc không event qua mức lọc | Kiểm tra runtime config, directory, status log |
| Layout của file thiếu stack trace | Không truyền Throwable hoặc layout không xuất exception | Dùng overload nhận Throwable, kiểm tra converter |
| Thêm async làm file ghi hai lần | Tham chiếu cả AsyncAppender và appender đích | Giữ một đường đến sink khi cần |
| File tăng không kiểm soát | Chỉ dùng FileAppender, chưa có rolling/retention | Cấu hình RollingFile và kiểm chứng rotation |
| `log4j2.xml` thay đổi nhưng output không đổi | Ứng dụng dùng Logback/JUL hoặc file config khác | Xác minh backend thực tế và runtime classpath |
| Dòng bị thiếu khi JVM dừng | Queue/buffer chưa flush, lỗi đích | Kiểm thử shutdown và chính sách độ bền |
| Mọi appender đều im lặng | Event bị logger lọc từ đầu | Kiểm tra logger level/filter trước khi xem sink |

### Checklist theo đường đi event

1. Kiểm tra ứng dụng thực sự dùng Log4j2, Logback hay JUL.
2. Xác định logger name và level hiệu lực.
3. Kiểm tra tệp cấu hình thật được nạp vào runtime.
4. Liệt kê tất cả AppenderRef/handler tại logger hiện tại và các cha có thể nhận.
5. Xét `additivity` (Log4j2/Logback) hoặc `useParentHandlers` (JUL).
6. Kiểm tra level/filter tại **mỗi** AppenderRef/appender.
7. Kiểm tra layout, exception, context (MDC/ThreadContext) và đường dẫn đích.
8. Kiểm tra trạng thái backend, quyền ghi, file rotation và collector.
9. Tạo sự kiện thử ở DEBUG/INFO/WARN/ERROR rồi đối chiếu console với file.

## 14. Câu hỏi tự kiểm tra

**Câu 1:** Root logger DEBUG, Console AppenderRef INFO, File AppenderRef WARN. `LOG.info(...)` đi đâu?  
**Đáp án:** Chỉ console. File chặn vì ngưỡng WARN.

**Câu 2:** Cùng cấu hình, `LOG.error(...)` đi đâu?  
**Đáp án:** Cả console lẫn file nếu không có filter khác và các đích hoạt động.

**Câu 3:** Vì sao `LOG.debug(...)` không xuất mặc dù root ở DEBUG?  
**Đáp án:** AppenderRef của cả hai đích đều đặt ngưỡng cao hơn DEBUG.

**Câu 4:** Nếu một sự kiện WARN hiện hai lần trên console, có chắc là fan-out đúng không?  
**Đáp án:** Không. Fan-out mong muốn ở ví dụ là một bản ở console và một ở file. Hai dòng cùng console có thể do additivity hoặc code log hai lần.

**Câu 5:** Dùng `additivity="false"` lúc nào?  
**Đáp án:** Khi logger có appender riêng và không muốn event tiếp tục lên appender cha/root; phải khai báo đủ những đích muốn giữ.

**Câu 6:** Với JUL, nhiều appender tương ứng với khái niệm nào?  
**Đáp án:** Nhiều `Handler`, có thể dùng `Logger.addHandler(...)` và đặt level/formatter cho từng handler.

**Câu 7:** Có phải chỉ cần hai appender là log không bao giờ mất?  
**Đáp án:** Không. Lỗi hạ tầng, quyền ghi, crash hoặc bộ đệm vẫn có thể làm mất log.

**Câu 8:** Vì sao không nên dùng `append="false"` trong file log production cần lưu lịch sử?  
**Đáp án:** Vì nội dung file có thể bị ghi đè mỗi khi appender khởi tạo; cần append/rolling/retention được thiết kế rõ.

**Ghi nhớ:** **Nhiều appender cho phép một log event được phân phối tới nhiều đích độc lập**. Muốn vận hành chính xác phải xét **logger level**, **ngưỡng/filter ở từng đích**, **layout**, **additivity**, và vòng đời file/async. Phân biệt fan-out đúng với log trùng, bảo vệ dữ liệu và xác minh output của từng appender.
