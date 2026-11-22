# Pattern layout trong Java Logging: thiết kế và kiểm tra định dạng log

## 1. Pattern layout là gì?

**Pattern layout** là cơ chế biến một **sự kiện logging** thành **chuỗi văn bản có cấu trúc theo mẫu (pattern)**. Một sự kiện thường chứa timestamp, level, tên logger, tên thread, thông điệp đã được thay tham số, MDC/context và ngoại lệ (Throwable). Pattern xác định **trường nào được in, thứ tự xuất hiện, cách căn chỉnh và ký tự phân cách**.

Ví dụ một sự kiện chứa:

- Level: `INFO`
- Logger: `demo.order.OrderService`
- Message: `event=order.created order_id=O-17`
- MDC `trace_id`: `tr-42`

Với pattern minh họa:

```text
%level|%logger{0}|trace=%X{trace_id}|%msg%n
```

Dòng kết quả có thể là:

```text
INFO|OrderService|trace=tr-42|event=order.created order_id=O-17
```

Các dấu `|` và chữ `trace=` là ký tự bình thường; `%level`, `%logger{0}`, `%X{trace_id}`, `%msg`, `%n` là những **conversion word** (mã chuyển đổi) được thư viện logging hiểu.

Pattern layout giải quyết việc **trình bày thông tin nhất quán**, không quyết định sự kiện nào sẽ xảy ra và không thay thế cho xử lý exception. Nó cũng không tự bảo đảm log được lưu, đã vào collector hoặc đã được bảo vệ khỏi rò rỉ dữ liệu.

Trong Java, khái niệm này gặp nhiều ở:

- **Logback Classic:** `PatternLayout` tạo văn bản; `PatternLayoutEncoder` thường dùng để biến kết quả thành byte cho console/file.
- **Log4j 2:** `PatternLayout` được cấu hình trực tiếp trong appender như `Console`, `File` hoặc `RollingFile`.
- **java.util.logging (JUL):** có `Formatter` và `SimpleFormatter`, không dùng nguyên cú pháp `PatternLayout` của Logback/Log4j 2.

Vì các thư viện khác nhau có conversion word và cách cấu hình khác nhau, **không nên sao chép pattern giữa các backend rồi mặc định rằng kết quả giống hệt**.

## 2. Pattern layout nằm ở đâu trong hệ thống logging?

Một đường đi điển hình:

```text
Code Java: logger.info("order={}", orderId)
            |
            v
Logging API: SLF4J hoặc Log4j 2 API
            |
            v
Logger + effective level + filter
            |
            v
Logging event (level, logger, args, MDC, Throwable...)
            |
            v
Appender (quản lý đích xuất)
            |
            v
Layout / Encoder (diễn giải pattern thành text/byte)
            |
            v
Console / file / hệ thống thu thập
```

Bảng phân biệt:

| Thành phần | Chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| `Logger` | Tiếp nhận sự kiện từ mã, áp dụng mức hiệu lực | `com.example.payment.PaymentService` |
| `Log event` | Mang dữ liệu của một lần ghi log | timestamp, level, message, MDC, Throwable |
| `Filter` | Chấp nhận hoặc loại sự kiện | Chỉ WARN trở lên vào một kênh |
| `Appender` | Quản lý nơi ghi và vòng đời xuất | ConsoleAppender, RollingFileAppender |
| `Layout` | Chọn trường, thứ tự, cách định dạng văn bản | PatternLayout |
| `Encoder` | Biến sự kiện thành byte để appender ghi | PatternLayoutEncoder của Logback |
| Collector | Thu thập, parse và lập chỉ mục ngoài JVM | Bộ đọc stdout/file hoặc agent logging |

Nếu một dòng `DEBUG` đã bị logger chặn, sửa `%msg` hay `%level` trong pattern sẽ **không làm nó xuất hiện**. Ngược lại, nếu logger đã chấp nhận sự kiện, việc bỏ `%logger` khỏi pattern chỉ làm mất tên nguồn **trong nội dung hiển thị**, không đồng nghĩa logger không còn tên.

**Pattern layout là bước biểu diễn, không phải cơ chế đo tỷ lệ lỗi.** Một request có thể tạo nhiều bản ghi hoặc không có bản ghi; số dòng ERROR không tự động bằng số request thất bại.

## 3. Đọc một pattern theo từng thành phần

Ví dụ:

```text
%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
```

Có thể đọc từ trái sang phải:

1. `%d{HH:mm:ss.SSS}`: thời gian theo một mẫu giờ-phút-giây-millisecond; bản này **không có ngày hoặc timezone**.
2. Khoảng trắng: dấu cách cố định.
3. `%-5level`: tên level, căn trái trong độ rộng tối thiểu 5 ký tự. Ví dụ `INFO ` có thêm một dấu cách để đủ độ rộng.
4. `[%thread]`: dấu ngoặc vuông là literal; giá trị bên trong là tên thread.
5. `%logger{36}`: tên logger dạng rút gọn theo cơ chế của backend.
6. ` - `: dấu phân cách literal.
7. `%msg`: message đã được định dạng.
8. `%n`: ký tự xuống dòng phù hợp nền tảng.

Dấu `%` thường mở đầu một conversion word. Các dấu ngoặc nhọn `{...}` đi sau conversion word là **tham số cấu hình cho conversion**, không đồng nhất với `{}` dùng trong câu lệnh Java để thay tham số message.

### Conversion word thường dùng

| Ý nghĩa | Logback Classic (phổ biến) | Log4j 2 PatternLayout (phổ biến) | Lưu ý |
| --- | --- | --- | --- |
| Timestamp | `%d{...}` hoặc `%date{...}` | `%d{...}` hoặc `%date{...}` | Cú pháp format/timezone có thể khác; kiểm tra phiên bản. |
| Level | `%level`, `%p` | `%level`, `%p` | Có thể định dạng độ rộng bằng `%-5level`. |
| Logger | `%logger`, `%c` | `%logger`, `%c` | Hỗ trợ rút gọn, nhưng quy tắc có thể khác. |
| Thread | `%thread`, `%t` | `%thread`, `%t` | Tên thread không cố định giữa các lần chạy. |
| Message | `%msg`, `%message`, `%m` | `%msg`, `%message`, `%m` | Đầu ra đã thay các tham số message khi thích hợp. |
| MDC/context | `%X{trace_id}` | `%X{trace_id}` | Phụ thuộc vào việc đặt đúng ngữ cảnh. |
| Exception | `%ex`, `%exception` | `%ex`, `%throwable` | Đầu ra nhiều dòng; có tùy chọn riêng theo backend. |
| Newline | `%n` | `%n` | Trong log text theo dòng, thường rất quan trọng. |
| Key-value event | `%kvp` (phiên bản hỗ trợ) | Tùy pattern/converter/backend | Đừng giả định cấu trúc key-value tự hiện nếu chưa cấu hình. |

Bảng nhằm hướng dẫn đọc pattern thường gặp, **không phải cam kết mọi alias/tùy chọn có mặt trên mọi phiên bản**. Với converter đặc thù, phải tra tài liệu đúng backend và kiểm tra đầu ra thực tế.

## 4. Pattern, message template và structured logging là ba khái niệm khác nhau

Trong mã Java dùng SLF4J:

```java
log.info("event=order.created order_id={}", orderId);
```

Ở đây `{}` là placeholder để thay một giá trị. Nếu `orderId` bằng `"O-17"` thì message sau khi format là:

```text
event=order.created order_id=O-17
```

Trong `logback.xml`:

```xml
<pattern>%level|%msg%n</pattern>
```

`%msg` là token của **layout**, lấy message đã được chuẩn bị từ logging event. Bởi vậy:

```text
INFO|event=order.created order_id=O-17
```

Không nên nhầm ba lớp:

- **Parameter substitution:** thay `{}` trong message bằng các argument của lời gọi logger.
- **Pattern layout:** chọn và sắp xếp các trường của sự kiện thành chuỗi.
- **Structured logging:** xuất những thuộc tính như `level`, `event_code`, `order_id`, `duration_ms` dưới dạng các trường riêng có kiểu để truy vấn.

Một pattern text như `order={} amount={}` vẫn chỉ tạo **chuỗi**, không bảo đảm hệ thống log tập trung tự hiểu `amount` là số. Muốn truy vấn trường ổn định, nên dùng encoder/layout JSON đáng tin cậy hoặc bộ thu thập có parser được kiểm chứng.

### Vì sao không in sẵn mọi thứ trong mã Java?

Không nên rải mã tự tạo timestamp, thread và tên class tại từng lời gọi:

```java
log.info("[" + Thread.currentThread().getName() + "] "
        + "order=" + orderId);
```

Đây là **đoạn minh họa** trong phương thức đã có `log` và `orderId`. Cách này lặp chức năng của layout, khó thay đổi định dạng toàn hệ thống và có thể tính chuỗi trước khi logger kiểm tra level.

Thay vào đó:

```java
log.info("event=order.created order_id={}", orderId);
```

Sau đó, dùng pattern thêm tên thread, logger, level và thời gian một cách nhất quán. Dù vậy, thông tin nghiệp vụ quan trọng vẫn phải được truyền vào sự kiện; layout không tự suy đoán `order_id` nào đang xử lý.

## 5. Logback: cách cấu hình PatternLayoutEncoder

Với **SLF4J 2.x + Logback Classic** tương thích, một appender console đơn giản:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

**Giải thích:**

- `<configuration>` là phần gốc của `logback.xml`.
- `<appender name="CONSOLE">` tạo đích console; tên `CONSOLE` sẽ được tham chiếu bên dưới.
- `<encoder class="...PatternLayoutEncoder">` chuyển sự kiện thành byte dựa trên pattern; `PatternLayout` là thành phần định dạng text mà encoder dùng.
- `<charset>UTF-8</charset>` định nghĩa mã ký tự của output.
- `%level|%logger{0}|%msg%n` cho một dòng ngắn, ổn định khi debug.
- `<root level="INFO">` là mức mặc định; sự kiện DEBUG thông thường bị loại, INFO/WARN/ERROR được cho phép.
- `<appender-ref ref="CONSOLE" />` gắn đích vào root; chỉ định nghĩa appender mà không gắn vào logger có thể khiến không có dữ liệu.

**Không nên coi pattern bỏ timestamp là cấu hình production tối ưu.** Ví dụ trên phục vụ kiểm tra dễ dự đoán. Trong hệ thống thật thường cần timestamp có ngày/múi giờ, tên service, trace ID, event code và cách biểu diễn exception được thống nhất.

### Logback: điểm khác với Log4j 2

Logback ConsoleAppender/FileAppender thông dụng thường cấu hình **encoder**:

```xml
<encoder>
    <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
</encoder>
```

Log4j 2 thường cấu hình trực tiếp **layout** dưới appender:

```xml
<PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n" />
```

Hai đoạn minh họa thuộc **hai định dạng cấu hình khác nhau**, không được đặt nhầm vào tệp backend kia. Thấy `<PatternLayout>` không có nghĩa mọi hệ thống đang chạy Log4j 2, nhưng tên tag, vị trí và class trong các mẫu giúp nhận biết backend đang dùng.

## 6. Ví dụ Java 17 có thể chạy: PatternLayout của Logback

Ví dụ này minh họa đầy đủ: Maven dependency, `logback.xml`, ứng dụng Java, MDC và kết quả console. Để các dòng dự đoán được, pattern không in thời gian hoặc tên thread.

**Điều kiện:** JDK 17 trở lên, Maven và khả năng lấy dependency Maven. Dùng bản thư viện xác định trong ví dụ để dễ tái lập, không khẳng định đó là bản mới nhất hoặc phù hợp với mọi dự án hiện tại.

Cấu trúc thư mục:

```text
pattern-layout-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── logging/
        │           └── PatternLayoutDemo.java
        └── resources/
            └── logback.xml
```

### 6.1. Tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>pattern-layout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
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

`logback-classic` cung cấp backend và provider SLF4J tương ứng, đồng thời kéo những dependency cần thiết. Nếu ứng dụng đã dùng framework quản lý phiên bản logging, hãy theo dependency management của framework thay vì thêm provider thứ hai hoặc tự trộn các phiên bản API.

### 6.2. Tạo `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|trace=%X{trace_id}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Điểm đáng chú ý: `%X{trace_id}` lấy giá trị từ **MDC** (Mapped Diagnostic Context) mà ứng dụng đặt khi xử lý yêu cầu. Nếu không có khóa này, phần chuyển đổi thường là chuỗi rỗng. Do vậy, khi message sau cleanup vẫn được in, cột `trace=` sẽ không có giá trị.

### 6.3. Tạo `src/main/java/demo/logging/PatternLayoutDemo.java`

```java
package demo.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class PatternLayoutDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(PatternLayoutDemo.class);

    private PatternLayoutDemo() {
    }

    public static void main(String[] args) {
        MDC.put("trace_id", "tr-42");
        try {
            LOG.info("event=order.created order_id={}", "O-17");
            LOG.warn("event=stock.low sku={} remaining={}",
                    "SKU-9", 2);
            LOG.debug("event=debug.hidden");
        } finally {
            MDC.remove("trace_id");
        }

        LOG.info("event=request.finished");
    }
}
```

### 6.4. Biên dịch và chạy

Từ thư mục `pattern-layout-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.logging.PatternLayoutDemo
```

**Ba dòng logging do ứng dụng phát theo cấu hình mẫu:**

```text
INFO|PatternLayoutDemo|trace=tr-42|event=order.created order_id=O-17
WARN|PatternLayoutDemo|trace=tr-42|event=stock.low sku=SKU-9 remaining=2
INFO|PatternLayoutDemo|trace=|event=request.finished
```

Maven và môi trường chạy có thể in thêm thông báo riêng. Kết quả trên liệt kê **những dòng của ứng dụng** khi chỉ có cấu hình mẫu được nạp; không bao gồm output nội bộ của Maven.

### 6.5. Giải thích từng dòng

1. `PatternLayoutDemo.class` tạo logger tên `demo.logging.PatternLayoutDemo`; `%logger{0}` làm output hiển thị tên ngắn `PatternLayoutDemo`.
2. `LOG.info` và `LOG.warn` vượt ngưỡng `INFO` ở root; `LOG.debug` bị loại nên không có dòng `event=debug.hidden`.
3. `MDC.put("trace_id", "tr-42")` đặt ngữ cảnh cho thread đang thực thi. Hai sự kiện đầu có `trace=tr-42`.
4. `%msg` lấy message đã thay `{}` bằng `O-17`, `SKU-9` và số `2`.
5. `finally` gọi `MDC.remove`, làm ngữ cảnh được dọn sau khi phần xử lý kết thúc. Dòng cuối được ghi sau cleanup nên `trace=` rỗng. Đây là cách giúp minh họa nguy cơ MDC bị giữ lại khi một thread xử lý nhiều request.
6. `%n` làm ba sự kiện tách dòng.
7. Đây là ví dụ **logging text**; dữ liệu `trace_id` mới chỉ được **in trong chuỗi**. Việc nó có trở thành field riêng của collector hay không phụ thuộc parser hoặc encoder có cấu trúc.

### 6.6. Thử thay pattern

Thay:

```xml
<pattern>%level|%logger{0}|trace=%X{trace_id}|%msg%n</pattern>
```

bằng:

```xml
<pattern>%level|%msg%n</pattern>
```

và chạy lại. Khi đó dòng đầu trở thành:

```text
INFO|event=order.created order_id=O-17
```

Sự kiện nghiệp vụ không thay đổi; chỉ **cách trình bày** bỏ tên logger và trace khỏi output. Đây là lợi ích của pattern layout: thống nhất biểu diễn từ một nơi.

Nếu đổi `root level="INFO"` thành `DEBUG`, lời gọi `LOG.debug` có thể xuất ra, vì đây là thay đổi chính sách **level**, không phải do pattern. Phải phân biệt hai loại chỉnh sửa này khi kiểm thử.

## 7. Log4j 2: PatternLayout trong `log4j2.xml`

Nếu ứng dụng dùng **Log4j 2 Core**, cú pháp tương đương về ý nghĩa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%level|%c{1}|trace=%X{trace_id}|%msg%n"
                charset="UTF-8" />
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE" />
        </Root>
    </Loggers>
</Configuration>
```

Ở đây `<PatternLayout>` nằm **trực tiếp trong `<Console>`**; không dùng `PatternLayoutEncoder` của Logback. Log4j 2 cần `log4j-api` và `log4j-core` (hoặc các module/provider thích hợp) để sử dụng cấu hình này.

Nếu mã dùng trực tiếp Log4j 2 API:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.ThreadContext;

Logger log = LogManager.getLogger("demo.payment");
ThreadContext.put("trace_id", "tr-42");
try {
    log.info("event=payment.completed order_id={}", "O-17");
} finally {
    ThreadContext.remove("trace_id");
}
```

Đây là đoạn **minh họa nằm trong một phương thức**, không phải một file Java độc lập: các package cần thư viện Log4j 2 và mã còn cần đặt trong class/phương thức. Với `%c{1}`, tên logger `demo.payment` được rút theo quy tắc tên logger của Log4j 2; đừng dựa vào cách rút gọn này để làm ID duy nhất nếu nhiều logger có tên cuối giống nhau.

**Điểm quan trọng:** `MDC` của SLF4J và `ThreadContext` của Log4j 2 đều phục vụ ngữ cảnh logging, nhưng không phải hai class có thể thay trực tiếp cho nhau bất kể backend. Khi dùng SLF4J → Log4j 2, cần kiểm tra provider và cơ chế đồng bộ ngữ cảnh của cấu hình thực tế.

### Logback và Log4j 2 có dùng chung mọi converter không?

Không. Các converter cơ bản như `%d`, `%level`, `%logger`, `%msg` và `%n` có vẻ giống nhau, nhưng:

- Quy tắc rút gọn tên logger, tùy chọn ngày giờ và timezone có thể khác.
- Tên converter mở rộng và cách tham số hóa khác nhau.
- Cách tự động thêm exception/Throwable vào output không được giả định giống nhau.
- Một số converter cần module hoặc phiên bản cụ thể.
- Tên file cấu hình và vị trí XML khác nhau.

Khi thay backend, hãy **chuyển đổi cấu hình và thử lại output**, không chỉ đổi tên `logback.xml` thành `log4j2.xml`.

## 8. Căn chỉnh, cắt độ dài và khả năng đọc

Pattern layout thường được dùng để tạo dòng console dễ quét bằng mắt.

Ví dụ:

```text
%-5level [%thread] %-30logger - %msg%n
```

Các ký hiệu:

- `-` trong `%-5level` là căn trái.
- `5` là độ rộng tối thiểu; nếu tên level ngắn hơn, layout thêm khoảng trắng.
- `%-30logger` hướng đến cột logger tối thiểu 30 ký tự; tên dài hơn có thể vượt độ rộng.
- Những dấu `[`, `]` và ` - ` là ký tự literal giúp tách trường.

**Độ rộng tối thiểu khác giới hạn tối đa.** `%-30logger` không mặc nhiên bảo đảm tên logger chỉ còn 30 ký tự. Nếu muốn rút gọn hoặc giới hạn, hãy dùng tùy chọn được backend hỗ trợ và kiểm tra chuỗi dài thực tế. Trong Logback, `%logger{36}` có cơ chế rút gọn tên; trong Log4j 2, các tùy chọn logger abbreviation có thể khác.

Thích hợp để căn cột khi chủ yếu đọc bằng terminal. Tuy nhiên, log dùng để xử lý tự động không nên dựa vào khoảng trắng căn lề để parse. Một giá trị như tên thread hoặc message có thể chứa khoảng trắng, dấu phân cách hoặc ký tự xuống dòng.

### Khi nào giữ nguyên tên logger?

Với console dành cho developer, `%logger{0}` hoặc tương đương ngắn gọn, dễ nhìn. Trong kho log tập trung cần điều tra theo package/lớp, nên cân nhắc **giữ logger đầy đủ ở field riêng** để phân biệt hai class cùng tên ngắn nhưng ở package khác nhau.

Ví dụ:

```text
com.example.orders.Service
com.example.payments.Service
```

Nếu chỉ hiển thị `Service`, hai nguồn có thể bị nhầm. Tên logger thường không phải danh tính service/instance: để liên kết máy và bản triển khai, cần thêm các trường `service`, `environment` và `version` khi phù hợp.

## 9. Timestamp và múi giờ trong pattern

Một pattern thời gian như:

```text
%d{HH:mm:ss.SSS}
```

có ích khi nhìn terminal trong thời gian ngắn nhưng chưa đủ cho hệ thống chạy nhiều ngày hoặc đa vùng.

Trong production, nên đặt các yêu cầu rõ:

1. Có **ngày** và giờ, không chỉ giờ trong ngày.
2. Có **múi giờ/offset**, hoặc thống nhất UTC trong toàn pipeline.
3. Có độ chính xác phù hợp, thường millisecond; không giả định mọi backend giữ được nanosecond.
4. Phân biệt **thời gian sự kiện được tạo** với **thời gian collector nhận**.
5. Kiểm tra đúng pattern date/time và timezone của **backend và phiên bản đang chạy**.

Ví dụ **đoạn cấu hình riêng cho Logback** (sử dụng cú pháp pattern thời gian của Logback):

```xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level %logger - %msg%n</pattern>
```

Đây chỉ là nội dung trong một encoder/layout đúng kiểu của Logback. Với Log4j 2, cách truyền timezone và format có thể dùng cú pháp khác; không tự sao chép cấu trúc `,UTC` của Logback nếu chưa kiểm tra tài liệu Log4j 2.

Dù dùng timezone nào, hãy kiểm chứng một bản ghi thật có timestamp chính xác và có thể parse. Đừng hard-code một timestamp động trong expected output của unit test: bài test sẽ sai ở lần chạy sau dù cấu hình đúng.

## 10. MDC, trace ID và giới hạn ngữ cảnh theo thread

Một phần rất hữu ích của pattern layout là thêm thông tin theo request mà không phải lặp nó trong mọi lời gọi logger:

```text
%X{trace_id} %X{request_id} %msg%n
```

Với Logback + SLF4J, các giá trị thường do `MDC.put` quản lý trong phạm vi thực thi. Một cách dùng đúng là:

```java
MDC.put("trace_id", traceId);
try {
    service.handleRequest();
} finally {
    MDC.remove("trace_id");
}
```

Đây là đoạn minh họa khi đã có `traceId` và `service`. Nó cần xử lý thêm nếu một request có nhiều MDC key hoặc có context tồn tại từ trước.

**Ngữ cảnh không tự lan truyền qua mọi thread.** Khi dùng `CompletableFuture`, thread pool, executor hoặc cơ chế reactive, có thể xảy ra:

- Logger ở thread con không thấy `trace_id`.
- Thread được tái sử dụng vẫn giữ dữ liệu của request cũ nếu quên cleanup.
- Công việc bất đồng bộ hoàn tất sau khi request gốc kết thúc, cần cơ chế context propagation cụ thể.

Cần dùng cơ chế truyền context được framework/backend hỗ trợ và kiểm tra đường chạy thật. Không giả định `MDC.put` ở request thread sẽ tự xuất ở mọi task bất đồng bộ.

### ID liên kết không đồng nghĩa với event code

- `trace_id` liên kết các bước thuộc một luồng xử lý, thường có nhiều sự kiện cùng ID.
- `request_id` định danh một request cụ thể theo quy ước hệ thống.
- `event_code` mô tả *loại sự kiện*, ví dụ `payment.failed` hoặc `order.created`.
- `error_code` phân loại nguyên nhân thất bại, ví dụ `UPSTREAM_TIMEOUT`.

Pattern text có thể in chúng cạnh nhau, nhưng việc **giữ tên field riêng** trong logging cấu trúc giúp truy vấn đáng tin hơn. Không tạo một logger name hoặc một event code duy nhất cho mỗi request — điều đó làm khó nhóm dữ liệu.

## 11. Throwable và stack trace: pattern phải được kiểm tra bằng lỗi thật

Một lỗi phổ biến là message đã rõ mà stack trace lại thiếu hoặc nhân đôi. Ví dụ trong ứng dụng dùng SLF4J:

```java
try {
    gateway.charge(orderId);
} catch (GatewayException failure) {
    log.error("event=payment.failed order_id={}", orderId, failure);
    throw failure;
}
```

Đây là **mã minh họa**, chưa biên dịch độc lập vì `gateway`, `GatewayException`, `log` và `orderId` thuộc ứng dụng thật.

Với lời gọi này, đối tượng `Throwable` được truyền để backend có thể lưu loại exception, cause chain và stack trace. Nếu code chỉ dùng:

```java
log.error("payment failed: {}", failure.getMessage());
```

thì message chỉ là một chuỗi; backend không tự có exception gốc để xuất stack trace.

Pattern text có thể khai báo converter ngoại lệ:

```text
%d{HH:mm:ss.SSS} %-5level %logger - %msg%n%ex
```

Tuy nhiên cần hiểu các điểm sau:

- **Có Throwable trong event khác với Throwable đã được in.** Layout/encoder và collector có thể giới hạn hoặc loại exception.
- Logback Classic và Log4j 2 có cơ chế tự thêm stack trace khi pattern chưa khai báo converter ngoại lệ trong những trường hợp/phiên bản nhất định. Đừng khẳng định “bỏ `%ex` luôn mất stack trace”; phải xem cấu hình thực.
- Stack trace thường **nhiều dòng vật lý** dù thuộc một sự kiện logic. Collector đọc text cần multiline hoặc framing phù hợp.
- Exception message và cause có thể chứa URL mang token, SQL có giá trị nhạy cảm hoặc dữ liệu cá nhân. Không log mọi Throwable một cách thiếu kiểm soát.
- Nếu các tầng repository, service và controller đều `log.error + rethrow` cùng một exception, layout sẽ định dạng cả ba sự kiện; nó không tự khử trùng lặp.

**Chiến lược tốt:** kiểm tra sự kiện ở appender test để biết có Throwable, sau đó kiểm tra **byte/output cuối** để biết stack trace được thể hiện đúng. Đừng lấy việc unit test thấy `getThrowableProxy() != null` làm bằng chứng rằng collector đã nhận đủ ngoại lệ.

### Lựa chọn chi tiết exception

Nhiều backend hỗ trợ tùy chọn độ dài hoặc cách rút ngắn exception. Những lựa chọn đó có thể giúp giảm log ồn, nhưng không nên cắt mất nguyên nhân cần chẩn đoán. Với lỗi hiếm và nghiêm trọng, giữ đủ chuỗi nguyên nhân; với retry tần suất cao, cần cân đối số lần ghi stack trace và ý nghĩa của từng sự kiện.

## 12. Pattern text, JSON Lines và rủi ro log injection

Pattern layout giỏi tạo văn bản dễ đọc. Nó không tự đảm bảo đầu ra là một đối tượng JSON hợp lệ, cũng không tự escape giá trị để parser đọc được.

Ví dụ nguy hiểm:

```xml
<pattern>{"level":"%level","message":"%msg"}%n</pattern>
```

Nếu message chứa dấu nháy, gạch chéo ngược hoặc xuống dòng, JSON ghép thủ công có thể **không hợp lệ**, hoặc làm thay đổi ranh giới giữa các bản ghi. Trong một số cấu hình XML, còn phải escape các ký tự dành riêng cho XML. Do đó, **không dùng nối chuỗi pattern để tự viết JSON một cách tổng quát**.

Ví dụ nội dung JSON có cấu trúc mong muốn:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "logger": "com.example.payment.PaymentService",
  "service": "checkout",
  "event_code": "payment.failed",
  "order_id": "O-17",
  "trace_id": "tr-42",
  "error_code": "UPSTREAM_TIMEOUT",
  "message": "Không thể hoàn tất thanh toán"
}
```

Đây là **ví dụ schema**, không phải output mặc định của PatternLayout. Muốn dữ liệu có kiểu và escaping đáng tin, chọn JSON encoder/layout tương thích với backend và phiên bản dự án:

- Với Logback, có thể dùng một thư viện encoder JSON phù hợp, chẳng hạn `logstash-logback-encoder` với dependency tương thích.
- Với Log4j 2, có các lựa chọn JSON layout/JsonTemplateLayout trong module phù hợp.
- Dù chọn backend nào, phải kiểm tra trường được xuất, kiểu dữ liệu, exception và kết quả parse ở collector.

**Thêm JSON encoder không tự tạo event code:** ứng dụng vẫn phải cung cấp `event_code` và các trường ngữ cảnh cần thiết. Tùy API, có thể dùng cặp key-value, MDC/ThreadContext hoặc một cơ chế structured logging riêng.

### Dấu xuống dòng và “một dòng = một sự kiện”

`%n` giúp **kết thúc** một dòng text, nhưng nếu `%msg` chứa ký tự xuống dòng hoặc stack trace nhiều dòng thì một sự kiện vẫn tạo nhiều dòng. Một parser đơn giản lấy từng dòng có thể hiểu sai số sự kiện. Với JSON Lines, encoder cần escape newline nằm trong string để mỗi object là một record hoàn chỉnh; với text cần cấu hình multiline thích hợp.

### Log injection và dữ liệu nhạy cảm

Kẻ tấn công có thể gửi đầu vào chứa:

```text
invalid value
ERROR ADMIN LOGIN SUCCESS
```

Nếu nối thẳng vào message dạng text, nội dung này có thể trông giống nhiều bản ghi. Pattern layout không tự phân biệt đâu là dấu xuống dòng thực do logger thêm và đâu là dữ liệu người dùng. Vì thế:

1. Không ghi toàn bộ input/payload nhạy cảm.
2. Dùng field dữ liệu có kiểu và encoder escaping đáng tin.
3. Có chính sách thay thế hoặc loại bỏ ký tự điều khiển khi cần.
4. Giữ quyền đọc log, retention và quy tắc bảo mật ở mọi kênh.
5. Kiểm thử với dữ liệu giả chứa token, dấu nháy, Unicode và newline.

Không dựa duy nhất vào một biểu thức thay thế regex trong pattern để bảo vệ mọi bí mật; các trường exception, MDC và nhánh output khác vẫn có thể chứa dữ liệu.

## 13. Hiệu năng và vận hành của pattern layout

Định dạng sự kiện có chi phí. Với mỗi bản ghi được chấp nhận, backend có thể cần:

- Format timestamp và timezone.
- Chuyển level, thread, logger name và MDC thành chuỗi.
- Thay các argument vào message.
- Format Throwable/stack trace khi có.
- Chuyển chuỗi thành byte theo charset.
- Ghi ra console, file, socket hoặc hàng đợi.

Những nguyên tắc vận hành:

| Vấn đề | Tác động | Hướng xử lý |
| --- | --- | --- |
| Pattern quá nhiều trường | Dòng dài, chi phí format và lưu trữ tăng | Chỉ chọn thông tin có ích cho điều tra. |
| Stack trace lặp lại qua nhiều tầng | Log ồn, tăng chi phí và sai phép đếm | Xác định ranh giới ghi sự kiện lỗi cuối. |
| Ghi DEBUG/TRACE quá nhiều | Tăng CPU, I/O và dung lượng | Bật theo package/cửa sổ thời gian có kiểm soát. |
| Ghi message có object `toString()` đắt | Tăng độ trễ và khả năng lỗi do serialize | Truyền giá trị đơn giản được phép, tránh tính toán nặng. |
| Appender đồng bộ chậm | Thread nghiệp vụ có thể chờ I/O | Đo thực tế, cân nhắc async với chính sách buffer/drop. |
| Async queue đầy | Có thể bỏ log theo chính sách | Theo dõi lượng bị bỏ và quy trình shutdown. |
| Console/file sai charset | Chữ tiếng Việt biến dạng | Thống nhất UTF-8 ở đầu ra và bộ thu thập. |
| Collector parse sai multiline | Một event thành nhiều event giả | Dùng framing/multiline hoặc encoder JSON phù hợp. |

**Pattern không phải mức log.** Khi level DEBUG bị tắt, việc sửa pattern không làm sự kiện DEBUG xuất hiện. Nếu tham số trong lời gọi Java là `expensive()`, Java vẫn đánh giá nó trước khi gọi logger; message formatting bằng placeholder có thể tránh format chuỗi khi log bị chặn, nhưng không tự trì hoãn tính toán đối số.

**Không có bảo đảm exactly-once.** Một lời gọi logger có thể bị mất trong pipeline hoặc được nhân đôi do collector retry, cấu hình appender/additivity hoặc log nhiều lần ở mã. Nếu cần kiểm toán nghiệp vụ không được phép mất dữ liệu, phải có cơ chế lưu/gửi chuyên biệt hơn logging thông thường.

## 14. Kiểm thử pattern layout theo từng lớp

Nên tách ít nhất ba mức kiểm thử.

### 14.1. Kiểm tra sự kiện trước khi layout

Với Logback, một `ListAppender<ILoggingEvent>` trong test có thể kiểm tra:

- `level` của event.
- `getLoggerName()`.
- `getFormattedMessage()`.
- `getMDCPropertyMap()`.
- `getThrowableProxy()` khi có exception.

Test này chứng minh **logger tạo event đúng**, không chứng minh layout đã tạo byte đúng.

### 14.2. Kiểm tra output của layout/encoder

Cho một event mẫu đi qua appender có layout/encoder thực, giữ byte trong buffer rồi giải mã bằng charset đã cấu hình. Kiểm tra:

- Ký tự `|` và thứ tự các trường.
- Tên logger rút gọn/full name đúng kỳ vọng.
- Khoảng trắng và căn lề nếu đó là hợp đồng.
- Có newline khi cần.
- Ký tự tiếng Việt không bị biến dạng.
- Chìa khóa MDC hiện đúng và không bị lưu sau cleanup.
- Exception/stack trace được thể hiện chính xác theo mục tiêu.
- Không có secret giả ở bất kỳ kênh nào.

Khi pattern chứa `%d` hoặc `%thread`, không so sánh toàn bộ output với chuỗi cố định dễ vỡ. Parse trường và assert giá trị có nghĩa hoặc kiểm tra timestamp trong khoảng hợp lý.

### 14.3. Kiểm tra collector thực

Trong staging, phát một sự kiện có `event_code` và `trace_id` dễ tìm, sau đó đối chiếu:

1. Ứng dụng có phát event không?
2. Appender thực sự ghi ở stdout/file nào?
3. Bộ thu thập có lấy đúng nguồn và giải mã UTF-8 không?
4. Dữ liệu có bị tách sai vì newline/stack trace không?
5. Trường có cấu trúc có được parse và lập chỉ mục không?
6. Số bản ghi ở đích có phù hợp chính sách fan-out/retry không?
7. Giao diện truy vấn có quyền truy cập, environment và khoảng thời gian đúng không?

Thấy một event trên console **không chứng minh** nó đã tới hệ thống tập trung. Ngược lại, thấy hai kết quả tìm kiếm không đủ kết luận layout tạo trùng: có thể do tuyến appender hoặc pipeline.

## 15. Chẩn đoán lỗi khi pattern không hoạt động

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Sửa `logback.xml` mà không đổi output | Backend đang dùng không phải Logback, file khác được nạp hoặc process chưa reload | Xác định provider, classpath và cấu hình runtime. |
| Pattern chứa `%logger{0}` nhưng hiển thị sai | Backend khác, tên logger khác dự kiến hoặc quy tắc rút gọn khác | Kiểm tra logger name gốc và converter thực. |
| Không thấy DEBUG | Logger level hoặc filter chặn | Kiểm tra mức và tuyến appender trước khi sửa pattern. |
| Có log nhưng không thấy `trace_id` | Chưa đặt MDC, không truyền qua async hoặc dùng sai khóa | Kiểm tra MDC/ThreadContext và vòng đời context. |
| Chữ Việt lỗi | Encoder/terminal/collector không thống nhất charset | Xác nhận byte UTF-8 và cách giải mã. |
| Hai dòng dính nhau | Thiếu `%n` hoặc framing sai | Thêm newline hoặc dùng encoder có framing phù hợp. |
| Một exception thành nhiều dòng ở collector | Stack trace multiline bị parser hiểu nhầm | Bật multiline hoặc dùng JSON escaping đúng. |
| Không thấy stack trace | Throwable không được truyền hoặc layout/collector bỏ exception | Kiểm tra API, event, converter và collector. |
| Log có dấu `%`, converter lạ | Sai token, sai XML hoặc không hỗ trợ trên backend/phiên bản | Kiểm tra tài liệu converter và status log. |
| Tìm theo order ID nhưng không có trường | ID chỉ nằm trong `%msg`; parser không tách | Dùng structured logging hoặc parser có kiểm thử. |
| Appender output trùng | Additivity, appender gắn ở con và root hoặc collector retry | Kiểm tra tuyến logger/appender và từng đích. |
| Log file dài bất thường | Pattern chứa nhiều trường, Throwable lớn hoặc lượng log cao | Đo volume, level, retention và hiệu năng. |
| Pattern “JSON tự ghép” bị lỗi cú pháp | Message không được escape theo JSON | Dùng JSON encoder/layout chuyên dụng. |

### Quy trình tìm lỗi theo đường đi

```text
Code có gọi logger?
   |
   +-- Không --> Kiểm tra nhánh code / exception / kết quả nghiệp vụ
   |
   +-- Có --> Level và filter có chấp nhận?
                |
                +-- Không --> Kiểm tra logger name, level, filter
                |
                +-- Có --> Appender có nhận?
                             |
                             +-- Không --> Kiểm tra AppenderRef, additivity, route
                             |
                             +-- Có --> Layout/encoder có xuất đúng byte?
                                          |
                                          +-- Không --> Kiểm tra pattern, charset, converter, Throwable
                                          |
                                          +-- Có --> Collector có đọc và parse đúng?
                                                       |
                                                       +-- Không --> Kiểm tra nguồn, multiline, index, retention
                                                       |
                                                       +-- Có --> Kiểm tra truy vấn, thời gian, quyền đọc
```

Tránh chữa lỗi bằng cách thêm `System.out.println` vào mã nghiệp vụ ở khắp nơi. Khi cấu hình logging có vấn đề, nên xác định **tầng gây lỗi** và kiểm tra từ logger đến collector.

## 16. Bài tập thực hành

### Bài 1 — Đọc pattern

Với:

```text
%level|%logger{0}|%msg%n
```

và sự kiện:

- Logger: `com.example.orders.OrderService`
- Level: `WARN`
- Message: `event=inventory.low remaining=2`

**Kết quả dự kiến** ở Logback:

```text
WARN|OrderService|event=inventory.low remaining=2
```

Lý do: `%level` hiện level, `%logger{0}` rút tên logger, `%msg` hiện message và `%n` kết thúc dòng.

### Bài 2 — Phân biệt template và pattern

Giả sử mã Java:

```java
log.info("order={} status={}", "O-17", "CREATED");
```

và pattern:

```text
[%level] %msg%n
```

**Đáp án:** message là `order=O-17 status=CREATED`; output của layout là:

```text
[INFO] order=O-17 status=CREATED
```

`{}` thuộc message template; `%level` và `%msg` thuộc layout.

### Bài 3 — Thêm correlation ID

Hãy sửa cấu hình Logback để hiển thị `trace_id` ngay sau level. Với sự kiện có MDC `trace_id=tr-42`, ví dụ:

```xml
<pattern>%level|trace=%X{trace_id}|%msg%n</pattern>
```

Khi xử lý xong request, phải làm gì? **Gợi ý:** dọn MDC trong `finally` hoặc cơ chế lifecycle tương đương; kiểm tra việc truyền context qua thread pool.

### Bài 4 — Tại sao test string đầy đủ dễ vỡ?

Pattern:

```text
%d{HH:mm:ss.SSS} [%thread] %msg%n
```

thay đổi theo thời gian và thread. **Gợi ý:** kiểm tra từng thành phần ổn định, timestamp hợp lệ và tên logger/event code khi cần. Không so sánh cả chuỗi với một timestamp hard-code.

### Bài 5 — Log text và JSON

Một nhóm muốn truy vấn `error_code` dưới dạng trường riêng, nhưng chỉ đang in `error_code=...` trong `%msg`. Cần làm gì?

**Gợi ý:** dùng structured logging/encoder JSON phù hợp và kiểm tra collector parse đúng field. Pattern text có thể giúp đọc nhưng không tự tạo typed field.

### Bài 6 — Stack trace mất

Đã gọi `log.error("failed", exception)`, nhưng giao diện tập trung không thấy stack trace. Có thể khẳng định do thiếu `%ex` trong pattern không?

**Gợi ý:** Không. Kiểm tra event có Throwable, layout/encoder thực, cơ chế tự thêm exception của backend, multiline/parser, giới hạn kích thước, và quyền/truy vấn ở collector.

### Bài 7 — Bảo mật

Message chứa dữ liệu giả: `token=SECRET_TEST_TOKEN_123`, và pattern đang in `%msg`. Có tự an toàn vì dùng parameter substitution không?

**Gợi ý:** Không. Cần loại/che dữ liệu trước khi phát event hoặc dùng cơ chế kiểm soát đã kiểm chứng; thử trên mọi appender/encoder, kể cả exception và MDC. Tránh đưa token thật vào bài test.

## 17. Checklist áp dụng vào dự án thật

1. **Xác định backend:** Logback, Log4j 2 hay JUL? Đúng provider ở runtime và đúng tên file cấu hình chưa?
2. **Xác định mục đích:** console cho developer, file vận hành hay collector? Người hay máy là người đọc chủ yếu?
3. **Chọn trường:** thời gian có ngày/múi giờ, level, logger/service, event code, message, trace/request ID và Throwable khi phù hợp.
4. **Thiết kế ranh giới:** delimiter, căn lề, newline, multiline; tránh dựa vào dấu cách để parse tự động.
5. **Kiểm tra encoding:** UTF-8 từ encoder qua file/console đến collector.
6. **Tách text và structured:** nếu cần truy vấn nhiều field, chọn encoder JSON/layout chuyên biệt và kiểm tra kiểu dữ liệu.
7. **Kiểm soát riêng tư:** không ghi token, mật khẩu, dữ liệu thẻ hoặc payload nhạy cảm ở bất cứ nhánh nào.
8. **Kiểm thử bằng sự kiện mẫu:** INFO/WARN/ERROR, MDC có và không có, message Unicode, exception, ký tự đặc biệt.
9. **Kiểm tra hiệu năng và volume:** tránh pattern nặng, log trùng, stack trace quá nhiều và queue bị đầy.
10. **Xác nhận vận hành:** appender và collector có nhận đúng, parser không sai, retention và quyền đọc phù hợp.

**Kết luận:** Pattern layout là cách kiểm soát **biểu diễn** của một logging event. Hãy phân biệt **`{}` của message**, **`%conversion` của layout** và **field có kiểu của structured logging**; sau đó kiểm chứng level, nguồn sự kiện, MDC, Throwable, charset và output cuối để log vừa đọc được vừa hữu ích khi điều tra.