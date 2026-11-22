# Appender là gì? Vai trò, cấu hình và thực hành trong Java Logging

## 1. Khái niệm

Trong các hệ logging như **Apache Log4j 2** và **Logback**, **Appender** là thành phần chịu trách nhiệm **chuyển sự kiện log đến một đích ghi**. Đích đó có thể là stdout/stderr, file, network collector, hệ thống giám sát hoặc một appender khác. Appender thường phối hợp với layout/encoder để biến sự kiện log thành dạng văn bản hay dữ liệu có cấu trúc mà đích nhận có thể sử dụng.

Ví dụ ứng dụng Java ghi:

```java
// Minh họa trong lớp ứng dụng đã có logger Log4j 2.
logger.info("Order {} accepted", "O-17");
```

Câu lệnh trên **không quyết định log được gửi ra đâu**. Cấu hình logging xác định logger nào nhận sự kiện, event được chuyển qua những filter nào và **appender nào được gọi**.

Một ứng dụng có thể gửi sự kiện INFO ra console và chỉ gửi WARN/ERROR vào file. Cũng có thể cho cùng một sự kiện vào hai appender để phục vụ hai mục đích khác nhau.

**Appenders không tự tạo sự kiện nghiệp vụ, không tự retry một tác vụ nghiệp vụ, không tự commit database và không tự bảo đảm bằng chứng kiểm toán.** Chúng là thành phần của pipeline quan sát hệ thống. Lời gọi `logger.info(...)` trả về không đồng nghĩa một kho lưu trữ trung tâm đã xác nhận dữ liệu được lưu bền vững.

## 2. Phân biệt các thành phần logging

```text
Java application / library
          |
          | logger.info(...), logger.warn(...)
          v
Logger / LoggerConfig
  - tên logger
  - level và filter
          |
          v
LogEvent: level, message, timestamp,
          exception, context...
          |
          +----------------------------+
          |                            |
       AppenderRef                 AppenderRef
       Console                     File (WARN+)
          |                            |
       Appender Console            Appender File
          |                            |
       PatternLayout               PatternLayout
          |                            |
        stdout                     log file
          |                            |
       collector                collector/shipper
          +----------------------------+
                         |
                  search/storage
```

| Thành phần | Trách nhiệm chính |
| --- | --- |
| **Logger** | API/code gọi để phát sự kiện; có tên và ngưỡng level. |
| **LogEvent** | Thông tin của một sự kiện: thời gian, level, logger name, message, exception, context. |
| **AppenderRef** (Log4j 2) | Liên kết logger với appender theo tên; có thể giới hạn level/filter riêng. |
| **Appender** | Nhận sự kiện từ pipeline và xuất tới một đích cụ thể hoặc appender tiếp theo. |
| **Layout / Encoder** | Biểu diễn sự kiện thành text hoặc byte (pattern, JSON, v.v.). |
| **Filter** | Chấp nhận hoặc loại sự kiện theo chính sách. Có thể được đặt ở nhiều tầng. |
| **Collector / storage** | Thu log, vận chuyển, lưu trữ, lập chỉ mục và cho truy vấn sau khi appender đã xuất. |

Trong **Log4j 2**, appender triển khai `org.apache.logging.log4j.core.Appender`; các implementation phổ biến có thể dựa trên `AbstractAppender` và sử dụng `Layout` để định dạng. Trong **Logback**, interface tương ứng là `ch.qos.logback.core.Appender<E>`, với phương thức quan trọng `doAppend(E event)`.

Một logger có thể có nhiều appender, và một appender có thể được nhiều logger tham chiếu. **Mỗi appender có tên để cấu hình tham chiếu**, ví dụ `Console`, `WarningFile` hoặc `RemoteLogs`.

## 3. Appender khác Logger như thế nào?

Có thể nhớ:

- **Logger hỏi:** “Sự kiện gì xảy ra, ở level nào, từ thành phần nào?”
- **Appender hỏi:** “Sự kiện được chấp nhận sẽ đi đâu và được xuất như thế nào?”

Giả sử logger `com.example.payment` được đặt mức INFO, có hai appender:

- Console nhận mọi sự kiện logger cho phép, nên INFO/WARN/ERROR đều tới console.
- File chỉ nhận WARN trở lên, nên INFO không xuất vào file.

Sự kiện DEBUG bị **logger** chặn trước khi đến cả hai nơi. Sự kiện INFO được logger chấp nhận nhưng **đường dẫn tới file** chặn vì ngưỡng WARN. Điều này cho thấy **logger bật INFO không bắt buộc mọi appender cũng ghi INFO**.

Các backend có thể cho phép filter ở nhiều chỗ: logger, appender reference hoặc bản thân appender. Khi kiểm tra vì sao mất log, cần tìm đúng tầng đã loại event.

## 4. Những loại Appender thường gặp

| Appender | Đích/chức năng | Khi dùng | Giới hạn chính |
| --- | --- | --- | --- |
| **ConsoleAppender** | Stdout hoặc stderr. | Container, development và vận hành có collector thu stream. | Không tự đảm bảo lưu lâu dài. |
| **FileAppender** | Một file. | Ứng dụng cần log cục bộ/tệp được collector tail. | Không mặc định tự xoay vòng file. |
| **RollingFileAppender** | File đang ghi + archive luân phiên theo policy. | Log tăng đều cần rotation. | Phải kiểm soát retention, archive và dung lượng. |
| **AsyncAppender** | Buffer/queue rồi chuyển tới appender downstream. | Tách thời gian ghi sink khỏi thread nghiệp vụ. | Queue hữu hạn, có rủi ro overload và crash. |
| **Socket/network appender** | Gửi log qua kết nối mạng. | Collector hoặc dịch vụ logging bên ngoài. | Phụ thuộc timeout, TLS, retry/ACK và kết nối. |
| **Các appender đặc thù** | Đích database, email hoặc hệ thống khác tùy plugin/backend. | Tích hợp một sink chuyên biệt. | Không được mặc định có độ bền giao dịch hoặc chi phí thấp. |

### ConsoleAppender

Console appender thường xuất tới `System.out` hoặc `System.err`. Với Docker/Kubernetes, đây là cách phổ biến để platform thu thập log. Tuy nhiên, console appender **chỉ đưa log ra stream**; để còn tìm được log sau khi container bị hủy cần có collector và chính sách lưu trữ riêng.

### FileAppender và RollingFileAppender

File appender ghi file theo đường dẫn được cấu hình. Cần xác minh quyền ghi, đường dẫn, encoding, flush và dung lượng đĩa. Nếu file tiếp tục tăng, cân nhắc RollingFileAppender với *triggering policy* (theo kích thước, thời gian hoặc điều kiện phù hợp).

Ví dụ minh họa trong Log4j 2:

```xml
<RollingFile name="Rolling"
             fileName="logs/app.log"
             filePattern="logs/app-%d{yyyy-MM-dd}-%i.log.gz">
    <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
    <Policies>
        <SizeBasedTriggeringPolicy size="10 MB"/>
    </Policies>
    <DefaultRolloverStrategy max="10"/>
</RollingFile>
```

Đây là **đoạn cấu hình** trong `<Appenders>` của Log4j 2, không phải file XML hoàn chỉnh. Ký hiệu `max="10"` liên quan tới cơ chế rollover/đếm archive; **không đồng nghĩa dữ liệu được giữ đúng 10 ngày**. Retention theo thời gian và xóa archive phải được cấu hình/kiểm chứng riêng.

### AsyncAppender

AsyncAppender thường đặt một buffer trước các appender đích, giúp thread gọi logger không phải luôn chờ I/O sink. Nếu appender downstream chậm hơn tốc độ tạo event, buffer sẽ đầy. Tùy framework và chính sách, thread có thể phải chờ, có thể xảy ra fallback hoặc event bị bỏ. Không coi AsyncAppender là lưu trữ bền vững.

Trong Log4j 2, **Async Logger** sử dụng LMAX Disruptor ở cấp logger là cơ chế khác với AsyncAppender. Không chồng hai cơ chế bất đồng bộ chỉ vì kỳ vọng tăng hiệu năng mà chưa đo latency, throughput, queue drop và cách shutdown.

## 5. Định tuyến qua AppenderRef, level và Filter trong Log4j 2

Log4j 2 cấu hình appender dưới `<Appenders>` rồi tham chiếu từ `<Loggers>`:

```xml
<Appenders>
    <Console name="Console" target="SYSTEM_OUT">
        <PatternLayout pattern="%p|%m%n"/>
    </Console>
</Appenders>
<Loggers>
    <Root level="INFO">
        <AppenderRef ref="Console"/>
    </Root>
</Loggers>
```

Đây là một **đoạn XML**; để chạy độc lập phải đặt trong `<Configuration>` hoàn chỉnh. `Console` là tên appender; `ref="Console"` là liên kết. Nếu viết sai tên `ref`, logger không được nối với appender mong muốn.

Log4j 2 hỗ trợ `level` ngay trên AppenderRef:

```xml
<Logger name="com.example.order" level="INFO"
        additivity="false">
    <AppenderRef ref="Console"/>
    <AppenderRef ref="WarningFile" level="WARN"/>
</Logger>
```

Theo cấu hình này:

- DEBUG thấp hơn INFO nên logger không chuyển đi.
- INFO tới Console nhưng không tới WarningFile.
- WARN và ERROR tới cả hai, nếu không bị filter khác loại.

**Level ở logger và level ở AppenderRef có mục đích khác nhau.** Ngoài ra, filter có thể chạy tại logger configuration, AppenderRef và appender. AppenderRef level là một cách thuận tiện để cắt các sự kiện không cần ở tuyến đích; không phải mọi backend đều dùng cú pháp này.

Nếu cần lọc theo event/marker/context phức tạp, dùng filter được framework hỗ trợ thay vì chỉ so chuỗi message tự do. Nhưng khi vấn đề là rò dữ liệu nhạy cảm, hãy **ngăn dữ liệu đi vào log từ nguồn**, không trông cậy collector lọc sau khi console/file đã nhận.

## 6. Ví dụ thực hành Java 17: Console và File Appender

Bài thực hành tạo một project Java 17 bằng Maven sử dụng **Log4j 2 API + Core**. Cùng một logger ghi INFO/WARN/ERROR lên console, trong khi **chỉ WARN/ERROR được đưa tới file**. Đây là ví dụ appender **đồng bộ**, không dùng AsyncAppender.

Ví dụ pin `log4j-api:2.26.1` và `log4j-core:2.26.1`, là các bản đã phát hành. Số version cố định giúp ví dụ tái lập, **không có nghĩa chúng luôn là bản mới nhất**; ứng dụng thực tế cần tuân theo BOM và chính sách cập nhật bảo mật.

### 6.1. Cấu trúc thư mục

```text
appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── AppenderDemo.java
        └── resources/
            └── log4j2.xml
```

### 6.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>appender-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.26.1</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.26.1</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.AppenderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. File src/main/resources/log4j2.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="CONSOLE|%p|%m%n"/>
        </Console>

        <File name="WarningFile"
              fileName="warning-demo.log"
              append="false">
            <PatternLayout pattern="FILE|%p|%m%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Logger name="demo.AppenderDemo" level="INFO"
                additivity="false">
            <AppenderRef ref="Console"/>
            <AppenderRef ref="WarningFile" level="WARN"/>
        </Logger>
        <Root level="ERROR">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

Đọc cấu hình từ trên xuống:

1. `<Console>` định nghĩa appender xuất stdout và dùng layout `CONSOLE|...`.
2. `<File>` định nghĩa appender ghi tệp `warning-demo.log` trong thư mục làm việc của chương trình.
3. `append="false"` cho phép demo mở file mới thay vì tiếp tục thêm vào file cũ; **không nên copy vào production nếu cần giữ lịch sử log**.
4. `Logger name="demo.AppenderDemo"` khớp tên class Java và có mức INFO; DEBUG bị loại ở logger.
5. Console có tham chiếu không hạn chế thêm; WarningFile có AppenderRef ngưỡng WARN.
6. `additivity="false"` tránh event của logger này tiếp tục đi lên root và bị ghi console trùng.
7. Layout cố ý không dùng timestamp hoặc thread name để stdout demo có thể kiểm tra chính xác. Trong production cần timestamp/UTC, service, logger name, correlation ID và các trường liên quan.

### 6.4. File src/main/java/demo/AppenderDemo.java

```java
package demo;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class AppenderDemo {

    private static final Logger LOG =
            LogManager.getLogger(AppenderDemo.class);

    private AppenderDemo() {
    }

    public static void main(String[] args) {
        LOG.debug("Debug detail");
        LOG.info("Order {} accepted", "O-17");
        LOG.warn("Gateway latency high: {} ms", 3000);
        LOG.error("Payment failed for orderId={}", "O-18");

        // Demo độc lập: kết thúc logging context sau các event.
        LogManager.shutdown();
    }
}
```

### 6.5. Build, chạy và kết quả

Trong thư mục chứa `pom.xml`, cần Maven, JDK 17 trở lên và khả năng tải dependency:

```bash
mvn -q clean compile exec:java
```

Nếu `log4j2.xml` được đọc đúng và không có cấu hình runtime nào ghi đè, ba dòng do ứng dụng ghi trên **stdout** là:

```text
CONSOLE|INFO|Order O-17 accepted
CONSOLE|WARN|Gateway latency high: 3000 ms
CONSOLE|ERROR|Payment failed for orderId=O-18
```

Nội dung file `warning-demo.log` sau lần chạy thành công:

```text
FILE|WARN|Gateway latency high: 3000 ms
FILE|ERROR|Payment failed for orderId=O-18
```

Đây là **hai đầu ra khác nhau**: ba dòng console và hai dòng file, không phải năm dòng stdout. Tool build có thể in thông báo ngoài ba dòng ứng dụng nếu cấu hình khác.

Vì sao kết quả như vậy?

| Lời gọi | Logger INFO | Console | WarningFile (WARN+) |
| --- | --- | --- | --- |
| `LOG.debug("Debug detail")` | Loại | Không | Không |
| `LOG.info("Order...")` | Nhận | Ghi INFO | Loại tại AppenderRef |
| `LOG.warn("Gateway...")` | Nhận | Ghi WARN | Ghi WARN |
| `LOG.error("Payment...")` | Nhận | Ghi ERROR | Ghi ERROR |

Bạn có thể đổi ngưỡng AppenderRef của WarningFile thành ERROR: file chỉ còn dòng ERROR nhưng console không thay đổi. Ngược lại, nâng ngưỡng **logger** từ INFO lên WARN sẽ loại INFO trước khi event đến cả hai đích.

**Giới hạn:** ví dụ không tạo HTTP request, không kết nối collector, không mô phỏng mạng lỗi và không kiểm chứng durability. Nó minh họa định tuyến appender và format text. Không cần gọi trực tiếp class FileAppender trong code Java vì cấu hình XML đã quản lý nó.

## 7. Appender và Handler của java.util.logging (JUL)

JDK cung cấp `java.util.logging`. Trong JUL, thành phần đóng vai trò tương tự appender là **`java.util.logging.Handler`**.

| Khái niệm | Log4j 2 / Logback | JUL |
| --- | --- | --- |
| Nơi phát log | `Logger` | `java.util.logging.Logger` |
| Bản ghi sự kiện | `LogEvent` hoặc `ILoggingEvent` | `LogRecord` |
| Đưa bản ghi tới đích | **Appender** | **Handler** |
| Chuyển bản ghi thành text | Layout/Encoder | `Formatter` |
| Mức nghiêm trọng | `WARN`, `ERROR`... | `WARNING`, `SEVERE`... |
| Gắn đích | AppenderRef/Logger config | `logger.addHandler(handler)` |

Đoạn mã JUL sau chỉ **minh họa** API handler trong một ứng dụng (không phải một class độc lập):

```java
java.util.logging.Logger jul =
        java.util.logging.Logger.getLogger("demo.order");
java.util.logging.ConsoleHandler sink =
        new java.util.logging.ConsoleHandler();
sink.setLevel(java.util.logging.Level.WARNING);
jul.addHandler(sink);
```

`ConsoleHandler` có ngưỡng riêng. Mặc định nó thường xuất stderr, không phải stdout; parent handlers cũng có thể khiến một record được ghi nhiều lần. Khi cần một demo JUL chạy độc lập phải thiết lập logger, formatter, handler, propagation và vòng đời đầy đủ.

**Không thể cast** `java.util.logging.Handler` sang `org.apache.logging.log4j.core.Appender`. Hai framework có ý tưởng tương tự nhưng các API là khác nhau.

## 8. Logback Appender có gì khác Log4j 2?

Nếu ứng dụng dùng **SLF4J + Logback**, code nghiệp vụ gọi SLF4J; Logback cung cấp appender thực hiện ghi. File cấu hình điển hình là `logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>CONSOLE|%level|%msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Đây là một ví dụ **cấu hình Logback riêng**, không phải `log4j2.xml`. Khi muốn chỉ ghi WARN trở lên vào appender, Logback có thể dùng `ThresholdFilter` bên trong appender. Không giả định thuộc tính `level="WARN"` của AppenderRef Log4j 2 có cùng cách xử lý ở mọi backend.

Về class/API:

- Logback: `ch.qos.logback.core.Appender<E>`, `doAppend(E)`, các base class như `AppenderBase<E>`/`UnsynchronizedAppenderBase<E>`.
- Log4j 2: `org.apache.logging.log4j.core.Appender`, `append(LogEvent)`, `AbstractAppender`.
- JUL: `java.util.logging.Handler`, `publish(LogRecord)`, `flush()`, `close()`.

Trong nhiều ứng dụng Java, **SLF4J là facade** và Logback/Log4j2 là backend. Có `slf4j-api` không có nghĩa ứng dụng đã dùng Logback; phải xem provider runtime thực tế, các bridge và cấu hình. Nếu một ứng dụng có nhiều provider, logging behavior có thể không như dự kiến.

## 9. Layout, context và bảo mật

### 9.1. PatternLayout

Ví dụ đoạn bên trong Console appender của Log4j 2:

```xml
<Console name="Console" target="SYSTEM_OUT">
    <PatternLayout pattern="%d{ISO8601} [%t] %-5p %c - %m%n"/>
</Console>
```

Mỗi dòng có timestamp, thread, level, logger và message. Pattern thuận tiện để đọc bằng mắt, nhưng khó truy vấn sâu nếu message có nhiều biến được nối chung hoặc chứa dấu phân cách.

### 9.2. JSON/structured log

Nếu cần lọc theo service, event code, request ID, order ID, latency, nên dùng layout/encoder có cấu trúc thích hợp với backend. Với Log4j 2 có thể dùng JSON layout phù hợp hoặc JsonTemplateLayout cùng module tương ứng. Một ví dụ **dữ liệu mong muốn**, không phải output của chương trình ở mục 6:

```json
{
  "timestamp": "2026-11-09T08:00:00Z",
  "level": "WARN",
  "service": "order-service",
  "event": "GATEWAY_LATENCY_HIGH",
  "correlationId": "req-100",
  "orderId": "O-17",
  "durationMs": 3000
}
```

Timestamp và ID là dữ liệu giả định. Trong ứng dụng thật phải lấy timestamp từ sự kiện, gắn correlation ID nhất quán qua các lớp, và tránh lẫn thông tin giữa các request khi dùng thread pool.

### 9.3. Bảo vệ dữ liệu ngay trước sink

Không ghi mật khẩu, OTP, access token, refresh token, cookie, private key hoặc nguyên request body nhạy cảm. Appender có thể ghi cùng message tới **nhiều đích**, tăng phạm vi rủi ro. Nên dùng allowlist trường ở nơi tạo event, redaction đáng tin cậy, mã hóa vận chuyển và quyền truy cập kho log.

Với text log, input chứa newline, backslash hoặc ký tự điều khiển có thể tạo cảm giác có nhiều record. Structured encoder phải escape đúng chuẩn, không ghép JSON thủ công từ chuỗi chưa kiểm soát. **Filter ở collector chạy sau khi appender đã đưa dữ liệu ra stdout/file, vì vậy không thể thay cho biện pháp phòng ngừa rò rỉ tại nguồn.**

## 10. Additivity, trùng log và routing nhiều đích

Trong Log4j 2 và Logback, logger thường tổ chức thành cây theo tên. Ví dụ:

```text
Root
  |
  +-- com.example
       |
       +-- com.example.orders
```

Nếu root tham chiếu Console appender và logger `com.example.orders` cũng tham chiếu Console, khi **additivity=true** sự kiện có thể đi qua các appender của logger con rồi tiếp tục tới appender của logger cha, tạo bản ghi trùng.

Cấu hình:

```xml
<Logger name="com.example.orders"
        level="INFO"
        additivity="false">
    <AppenderRef ref="Console"/>
</Logger>
```

giúp cô lập routing của logger con. Tuy nhiên, **không tắt additivity trên mọi logger theo thói quen**: nhiều hệ thống cố ý dùng một appender ở root để có log tổng quát, còn logger con bổ sung file riêng. Vấn đề cần kiểm tra là event được gửi tới đích nào, có bao nhiêu lần và có đúng chủ ý hay không.

Nếu cần hai đích khác nhau, tham chiếu hai appender có tên khác nhau; không tạo hai tuyến ghi giống hệt một cách vô ý.

## 11. Vòng đời và lỗi khi ghi log

### Lifecycle

Appender được cấu hình/khởi tạo, sử dụng và dừng/đóng theo vòng đời logging context. Với file hoặc socket, cần giải phóng file descriptor, buffer, kết nối và lock. Không tạo một FileAppender cho **mỗi request** khi muốn ghi log: cách đó dễ tạo rò tài nguyên và tranh file.

Trong ứng dụng có framework/container, logging lifecycle thường do hệ thống quản lý; tránh tự đóng appender dùng chung giữa các service hoặc classloader.

### Khi sink lỗi

Các tình huống: permission denied, đầy đĩa, file path không hợp lệ, mất network, collector timeout hoặc format lỗi. Ở nhiều appender Log4j 2, tùy thuộc `ignoreExceptions`, lỗi có thể được ghi qua **Status Logger**, bị giữ trong logging subsystem hoặc truyền lên caller theo cấu hình.

**Không giả định gọi `logger.error(...)` sẽ throw một exception nếu file chưa ghi được.** Với AsyncAppender, lỗi còn có thể xảy ra trên thread nền và không quay lại đúng stack của request.

Do đó cần quan sát: số event phát từ ứng dụng so với số tới sink, lỗi appender, số queue drop, thời gian ingest, file permissions/disk usage và tình trạng collector.

### Flush không bảo đảm lưu bền vững

```text
LogEvent -> Appender accepted -> Buffered -> Stream/File write
                                            |
                                      Collector received
                                            |
                                      Storage indexed
```

Một lời gọi flush có thể đẩy buffer xuống tầng dưới, nhưng **không tự đồng nghĩa fsync**, xác nhận lưu an toàn sau mất điện, đã được collector nhận hoặc đã lập chỉ mục. Audit logging bắt buộc phải có kiến trúc bảo đảm bằng chứng riêng theo chính sách, ví dụ transactional outbox, kho append-only, chính sách tính toàn vẹn và phân quyền phù hợp. Không lấy FileAppender cục bộ làm nguồn kiểm toán duy nhất mà không đánh giá rủi ro.

## 12. Hiệu năng: synchronous và asynchronous appender

```text
Synchronous:
request -> logger -> FileAppender -> file/network (có thể chậm)

Asynchronous:
request -> logger -> AsyncAppender -> bounded queue
                                         |
                                       worker
                                         |
                                     FileAppender
```

Synchronous appender đơn giản hơn về luồng kiểm soát nhưng I/O chậm có thể tăng latency. AsyncAppender giảm thời gian chờ ở caller trong nhiều điều kiện, song xuất hiện queue hữu hạn, giới hạn bộ nhớ và nguy cơ thất lạc record khi process crash trước lúc drain.

Cần xác định rõ:

1. Dung lượng queue và kích thước/số lượng event trong peak burst.
2. Chính sách khi đầy: block, discard có kiểm soát, fallback hoặc spool bền vững.
3. Khi shutdown: drain, timeout, ngắt cưỡng bức và giới hạn mất dữ liệu.
4. Khi network/file lỗi: thông báo, retry, failover, metrics và alert.
5. Dữ liệu mutable và context có được chụp đúng tại thời điểm tạo sự kiện hay không.
6. Mức độ cần giữ các log audit/security so với log debug thông thường.

Không kết luận “cứ thêm AsyncAppender là tốt hơn” nếu không đo **throughput của sink, p95/p99 request latency, CPU, memory, drop rate và ingestion lag**.

## 13. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/khắc phục |
| --- | --- | --- |
| Logger đã gọi nhưng không thấy log | Logger level hoặc filter loại event. | Kiểm tra logger name, effective level và filter. |
| Console có INFO nhưng file không có | AppenderRef file đặt WARN. | Xác định ngưỡng định tuyến có đúng chủ ý. |
| Định nghĩa Appender nhưng không dùng | Không có AppenderRef phù hợp. | Đối chiếu tên `ref`, logger và scope. |
| Log xuất hai lần | Additivity hoặc hai appender cùng sink. | Kiểm tra cây logger, root và AppenderRef. |
| File không xuất hiện | Sai đường dẫn, quyền ghi hoặc bị filter hết. | Kiểm tra fileName, working directory, Status Logger. |
| File tăng không kiểm soát | Dùng FileAppender thường. | Cân nhắc RollingFile và cleanup/retention. |
| Mất log khi shutdown | Async queue chưa drain hoặc appender chưa flush. | Kiểm tra shutdown hook, timeout và forced termination. |
| Lỗi chỉ xuất hiện ở production | Backend/provider/classpath hoặc appender plugin khác môi trường dev. | Kiểm tra artifact triển khai, runtime dependencies và cấu hình thật. |
| Log có dữ liệu nhạy cảm | Log message chứa token, cookie, PII. | Dùng allowlist và redaction từ nơi tạo event. |
| Log file có nhưng kho tìm kiếm không có | Collector, parser, index, retention lỗi. | Theo dõi pipeline sau appender. |
| Nhiều log nhưng khó truy vấn | Text pattern thiếu trường cấu trúc và correlation ID. | Chuẩn hóa event schema và encoder phù hợp. |

**Quy trình debug không thấy log:** code thực sự chạy → logger name/level → filter → AppenderRef name/level → appender filter → layout/encoding → sink và quyền ghi → queue/flush → collector/storage/retention. Đừng chỉ nhìn `logger.isInfoEnabled()` rồi kết luận appender chắc chắn đã ghi.

## 14. Bài tập và checklist triển khai

**Bài tập 1:** chạy Maven demo ở mục 6. Giải thích vì sao Console có INFO/WARN/ERROR nhưng file chỉ có WARN/ERROR.

**Bài tập 2:** đổi `<AppenderRef ref="WarningFile" level="WARN"/>` thành ERROR. Dự đoán output mới của file mà không thay đổi output console.

**Bài tập 3:** thêm một appender Console khác vào logger con và để additivity tới root Console; mô tả khi nào xảy ra log trùng, sau đó sửa bằng cách chọn routing hợp lý.

**Bài tập 4:** thay FileAppender bằng RollingFileAppender với policy theo kích thước. Phân biệt rõ rollover và retention theo thời gian.

**Checklist trước production:**

- [ ] Đã biết đang dùng JUL, SLF4J + Logback hay Log4j 2 và provider runtime thực tế.
- [ ] Mỗi appender có tên và đích rõ ràng; các AppenderRef khớp đúng logger.
- [ ] Level/filter ở logger, AppenderRef và appender được kiểm thử.
- [ ] Không ghi trùng ngoài ý muốn do additivity hoặc nhiều đường cùng đích.
- [ ] Layout/encoder có timestamp UTC, event code, logger/service và correlation ID khi cần.
- [ ] Không ghi dữ liệu nhạy cảm; chuỗi không đáng tin được escape/serialize an toàn.
- [ ] File output có đường dẫn, quyền truy cập, rotation, retention và phương án thu thập.
- [ ] Async sink có queue full policy, metric drop/error, shutdown/drain rõ ràng.
- [ ] Khi sink lỗi, có tín hiệu quan sát; không đánh đồng gọi logger với lưu bền vững.
- [ ] Đã kiểm tra sự kiện thực tế từ ứng dụng tới nơi truy vấn cuối cùng.

## Tài liệu tham khảo

- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html)
- [Apache Log4j 2 — Configuration / AppenderRef](https://logging.apache.org/log4j/2.x/manual/configuration.html)
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html)
- [Apache Log4j 2 — File appenders](https://logging.apache.org/log4j/2.x/manual/appenders/file.html)
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Java 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html)

**Kết luận:** Logger phát sự kiện; **Appender đưa LogEvent tới một hoặc nhiều đích nhận theo cấu hình**. Hiểu appender là gì phải đi cùng việc hiểu AppenderRef, level, filter, layout, additivity, lifecycle, các loại sink và giới hạn độ bền, nhờ đó log thực sự hữu ích cho vận hành và điều tra.