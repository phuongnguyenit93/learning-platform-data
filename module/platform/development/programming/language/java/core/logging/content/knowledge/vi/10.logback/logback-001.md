# Logback là gì? Kiến trúc và cách sử dụng trong Java

**Logback** là một framework logging cho Java, dùng để **nhận, lọc, định dạng và xuất các sự kiện log** đến console, tệp hoặc các đích khác. Trong ứng dụng Java, Logback thường đóng vai trò **logging backend** cho API **SLF4J** (*Simple Logging Facade for Java*). Mã nghiệp vụ gọi `org.slf4j.Logger` để phát sự kiện; Logback là thành phần thực thi việc xử lý sự kiện đó dựa trên cấu hình.

Ví dụ, khi dịch vụ đặt hàng gọi `LOG.info("Order {} accepted", orderId)`, lời gọi sử dụng API SLF4J. Nếu ứng dụng chọn `logback-classic` làm provider/backend, Logback quyết định bản ghi có được chấp nhận theo level, có chuyển tới console hay file, và được trình bày ra sao. Không nên nhầm SLF4J (API/facade) với Logback (implementation).

## 1. Logback giải quyết vấn đề gì?

Khi chỉ dùng `System.out.println(...)`, ứng dụng khó kiểm soát mức độ chi tiết, định tuyến bản ghi, stack trace, định dạng và cấu hình khác nhau giữa môi trường phát triển và production. Logback cung cấp các khả năng cơ bản:

- **Log level**: phân biệt `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, cấu hình cho từng logger/package.
- **Logger có tên**: đặt logger theo class hoặc khu vực chức năng, ví dụ `com.example.orders.OrderService`, để lọc và tìm kiếm.
- **Appender**: xuất log sang console hoặc file; có thể gắn nhiều đích với quy tắc khác nhau.
- **Encoder/layout**: xác định mỗi record trông như thế nào, chẳng hạn timestamp, thread, level, logger name, message, exception.
- **Kế thừa cấu hình và additivity**: áp dụng level theo namespace và quyết định sự kiện có được chuyển đến appender của logger cha hay không.
- **Rolling file**: tạo các thế hệ file theo thời gian/kích thước để giảm rủi ro một tệp tăng vô hạn.
- **MDC** (*Mapped Diagnostic Context*): gắn dữ liệu ngữ cảnh theo luồng, ví dụ `requestId`, để liên hệ log.
- **AsyncAppender và filter**: điều khiển pipeline ghi và tránh chặn luồng nghiệp vụ trong một số trường hợp.

Logging không tự bảo đảm mọi record được lưu vĩnh viễn: sự kiện có thể bị lọc, mất khi tiến trình chết, rơi khỏi hàng đợi async hoặc bị thay khi retention/rotation diễn ra. Audit quan trọng cần thiết kế độ bền và kiểm soát riêng.

## 2. Quan hệ giữa SLF4J và Logback

Hãy hình dung đường đi sau:

```text
Code ứng dụng Java
  |
  | org.slf4j.LoggerFactory.getLogger(...)
  | logger.info("event=order.accepted id={}", id)
  v
SLF4J API (facade)
  |
  | Provider được chọn lúc chạy
  v
Logback Classic
  |
  +--> Logger hierarchy / effective level / TurboFilter
  |
  +--> Logging event
          |
          +--> ConsoleAppender --> Encoder --> stdout/stderr
          |
          +--> RollingFileAppender --> Encoder --> file quay vòng
```

**Các module/thành phần cần phân biệt:**

| Thành phần | Vai trò |
| --- | --- |
| `slf4j-api` | API cho code ứng dụng; chứa `Logger`, `LoggerFactory`, MDC và các phương thức ghi log. |
| `logback-classic` | Triển khai logging theo mô hình Logback cho SLF4J; quản lý logger context, level, event. |
| `logback-core` | Hạ tầng chung cho appender, encoder, policy và thành phần cấu hình; được Classic sử dụng. |
| `logback-access` | Module liên quan HTTP access logging, khác luồng log ứng dụng thông thường; mức độ hỗ trợ/tích hợp tùy phiên bản và môi trường. |
| `logback.xml` | File cấu hình Logback phổ biến trên classpath; khai báo appender, encoder, level và root logger. |

Khi khai báo dependency Maven `logback-classic`, thông thường các dependency cần thiết như `logback-core` và `slf4j-api` được kéo theo. Không thêm nhiều provider SLF4J cạnh tranh nhau mà không có chủ đích.

### SLF4J 1.x và 2.x

Với **SLF4J 2.x**, backend được tìm bằng cơ chế **provider** (thường qua `ServiceLoader`); các dòng Logback Classic tương thích SLF4J 2.x cung cấp provider tương ứng. Ở hệ sinh thái cũ, SLF4J 1.7 dùng cơ chế binding khác. Vì vậy khi thấy cảnh báo về provider/binding, phải kiểm tra **cặp phiên bản thực tế** thay vì chỉ thêm JAR ngẫu nhiên.

Một tổ hợp chạy được trên Java 17 được minh họa bên dưới bằng Logback Classic **1.5.18**. Đây là **phiên bản cố định cho bài thực hành, không khẳng định là bản mới nhất**. Khi nâng cấp trong dự án thật, phải đối chiếu release notes, Java baseline, tương thích SLF4J và phụ thuộc bảo mật.

## 3. Các khái niệm cốt lõi trong Logback

| Thuật ngữ | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| **Logger** | Đối tượng phát sự kiện có tên ổn định, thường theo class. | `com.example.orders.OrderService` |
| **Logging event** | Một lần ghi log có level, message, thời gian, thread, exception và context. | `event=order.accepted orderId=42` |
| **Level** | Ngưỡng quan trọng để chọn bản ghi cần xuất. | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| **Appender** | Đích/đường xử lý xuất log. | `ConsoleAppender`, `FileAppender`, `RollingFileAppender` |
| **Encoder** | Chuyển logging event thành bytes cho appender ghi, thường dùng pattern. | `PatternLayoutEncoder` |
| **Layout** | Tạo biểu diễn text từ event; encoder có thể sử dụng layout. | `PatternLayout` |
| **Filter** | Chấp nhận/từ chối event dựa trên điều kiện bổ sung. | `ThresholdFilter`, `LevelFilter` |
| **Root logger** | Logger gốc của hierarchy, thường xác định level/appender mặc định. | `<root level="INFO">` |
| **Additivity** | Quy định appender của logger cha có tiếp tục nhận event của con hay không. | `additivity="false"` |
| **MDC** | Ngữ cảnh có khóa/giá trị thường gắn với luồng xử lý hiện tại. | `requestId=req-17` |
| **Rolling policy** | Chính sách luân phiên file và quản lý lịch sử. | `SizeAndTimeBasedRollingPolicy` |

Tên logger không nên chứa dữ liệu biến động như request ID hoặc mã người dùng. Một logger tên `com.example.orders.OrderService` có thể phát vô số sự kiện; đối tượng nào được xử lý phải nằm trong message hoặc field/context riêng.

## 4. Level và quan hệ logger cha–con

Các level thông dụng trong Logback Classic, từ chi tiết nhất đến nghiêm trọng nhất:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

Ngưỡng `INFO` thường cho phép `INFO`, `WARN` và `ERROR`, nhưng loại `TRACE` và `DEBUG`. Logback còn có các giá trị đặc biệt như `ALL`/`OFF` phục vụ cấu hình. **Không có phương thức `fatal()` chuẩn trên API SLF4J thông dụng**; đừng tự giả định các mức khác của Log4j 2 được hỗ trợ y nguyên.

Các logger có tên tạo hierarchy theo dấu chấm:

```text
ROOT
└── com
    └── example
        ├── orders
        │   ├── OrderService
        │   └── OrderRepository
        └── payments
            └── PaymentService
```

Đây là phân cấp **tên logger**, không phải quan hệ kế thừa class Java. Một cấu hình ở `com.example.orders` có thể điều chỉnh log cho những logger con như `com.example.orders.OrderService`. Logger con không đặt level riêng sẽ lấy **effective level** từ tổ tiên gần nhất có level xác định.

Ví dụ:

```xml
<logger name="com.example.orders" level="DEBUG"/>
<root level="INFO">
    <appender-ref ref="STDOUT"/>
</root>
```

Đoạn này **chỉ minh họa một phần** của `logback.xml`, vì appender `STDOUT` còn phải được khai báo. Các logger dưới `com.example.orders` có thể phát `DEBUG`, trong khi `com.example.payments` kế thừa `INFO` từ root.

**Điểm quan trọng:** Event được logger con chấp nhận theo effective level rồi có thể đi đến appender của tổ tiên. Root đặt `INFO` không nhất thiết loại lại sự kiện `DEBUG` đã được logger `com.example.orders` chấp nhận khi event truyền lên appender root. Nếu appender có `ThresholdFilter` riêng ở mức `INFO`, nó vẫn có thể loại DEBUG.

### Additivity và hiện tượng ghi trùng

Mặc định, logger con thường có **additivity=true**: ngoài appender gắn trực tiếp vào logger con, sự kiện có thể đi đến appender của tổ tiên. Ví dụ, nếu cùng một `ConsoleAppender` hoặc các appender cùng xuất console được gắn cả ở logger con và root, một event có thể xuất hiện hai lần.

Khi thật sự cần tách biệt đầu ra:

```xml
<logger name="com.example.audit"
        level="INFO"
        additivity="false">
    <appender-ref ref="AUDIT_FILE"/>
</logger>
```

Đây là đoạn cấu hình **minh họa**, giả sử appender `AUDIT_FILE` đã được định nghĩa. `additivity="false"` chặn truyền tới appender của tổ tiên; nó **không có nghĩa là ngừng kế thừa level**. Đồng thời, đặt tên logger chứa `audit` không tự bảo đảm lưu bền, chống sửa đổi hay đáp ứng yêu cầu audit pháp lý.

## 5. Appender và encoder: Logback xuất dữ liệu ra đâu?

Appender quyết định nơi sự kiện được xuất. Encoder quyết định dạng bytes của bản ghi trước khi ghi.

| Appender | Công dụng | Lưu ý |
| --- | --- | --- |
| `ConsoleAppender` | Xuất log ra console (thường stdout; có thể cấu hình stderr). | Phù hợp với container khi có log collector. |
| `FileAppender` | Ghi vào tệp được chỉ định. | Cần quản lý dung lượng, quyền ghi và vòng đời. |
| `RollingFileAppender` | Ghi file và luân phiên theo rolling policy. | Chính sách rollover/retention phải tương ứng lưu lượng. |
| `AsyncAppender` | Đưa event vào hàng đợi để appender phía sau xử lý. | Có thể mất/dropping log khi quá tải hoặc shutdown; không đồng nghĩa với ghi bền. |

### PatternLayoutEncoder

Một dạng cấu hình console thường thấy:

```xml
<appender name="STDOUT"
          class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
        <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
    </encoder>
</appender>
```

Ý nghĩa các ký hiệu trong pattern:

| Ký hiệu | Tác dụng |
| --- | --- |
| `%d{HH:mm:ss.SSS}` | Thời gian của event, định dạng giờ:phút:giây.millisecond; muốn UTC/timezone rõ ràng thì cấu hình thích hợp. |
| `%-5level` | Level căn trái với chiều rộng tối thiểu 5 ký tự, ví dụ `INFO `, `WARN `, `ERROR`. |
| `%thread` | Tên thread phát sinh event. |
| `%logger{36}` | Tên logger được rút gọn khi cần theo quy tắc pattern. |
| `%msg` hoặc `%message` | Message đã định dạng bằng tham số của SLF4J. |
| `%n` | Ký tự xuống dòng phù hợp môi trường. |
| `%ex` / `%exception` | Thông tin exception/stack trace, dùng khi cần kiểm soát phần throwable. |
| `%X{requestId}` | Trường `requestId` từ MDC nếu có; nếu không thiết lập, giá trị trống. |

Pattern text log hữu ích cho người đọc nhưng **không tự biến thành JSON có trường riêng**. Nếu hệ thống cần structured log, phải dùng encoder/provider hoặc cơ chế field có cấu trúc tương thích với phiên bản Logback và pipeline thu thập.

Với exception, hãy truyền `Throwable` đúng API, ví dụ `LOG.error("event=payment.failed id={}", id, ex)`. Logback có cơ chế format throwable qua pattern/encoder; nếu tự viết formatter chỉ xuất `%msg` theo cách bỏ throwable hoặc pipeline loại stack trace, có thể đánh mất bằng chứng điều tra. Hãy kiểm tra đầu ra thực tế, không chỉ nhìn lời gọi API.

## 6. logback.xml: nơi đặt cấu hình

Ứng dụng Java thông thường đặt `logback.xml` trong `src/main/resources` để Maven đóng gói file vào classpath. Logback cũng có thể dùng `logback-test.xml` cho các bài test; cấu hình được ưu tiên tìm theo quy tắc của Logback và hệ sinh thái đang dùng.

Ví dụ một cấu hình cơ bản hoàn chỉnh:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Ý nghĩa:

1. `STDOUT` là tên appender console, được root tham chiếu bằng `appender-ref`.
2. Encoder in ba phần: level, logger name và message; không in timestamp để dễ đối chiếu trong ví dụ học tập.
3. Namespace `demo.orders` có level `DEBUG` và các logger con kế thừa nếu không override.
4. Root ở `INFO` nên namespace khác như `demo.billing` thường không in DEBUG.
5. Các event từ `demo.orders` đến console qua appender root nhờ additivity mặc định; không cần gắn `STDOUT` lần nữa ở logger con.
6. Đây là cấu hình **dành cho demo**, không phải pattern đề xuất đầy đủ cho production. Hệ thống thật thường cần timestamp có timezone, thread, correlation/trace ID và chính sách nhạy cảm dữ liệu.

**Lưu ý môi trường:** Spring Boot có thêm các tiện ích cấu hình logging riêng như `logback-spring.xml` khi dùng Logback. Đừng áp dụng mù quáng mọi extension của Spring Boot vào một ứng dụng Java thuần. Nếu framework cấu hình lại logging lúc chạy, file XML và level thực tế có thể khác dự kiến.

## 7. Thực hành Java 17: ứng dụng Maven dùng SLF4J + Logback

Đây là **ví dụ chạy độc lập**, dùng JDK 17 và Maven để tải dependency. Để output ổn định, chương trình chỉ ghi các event có giá trị cố định; console pattern không có timestamp và thread name. File `logback.xml` được đặt đúng classpath.

### 7.1. Cấu trúc dự án

```text
logback-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LogbackDemo.java
        └── resources/
            └── logback.xml
```

### 7.2. pom.xml

Lưu nội dung sau thành `pom.xml`. Phiên bản `1.5.18` chỉ được cố định để bài học tái lập được; dự án thực tế cần chọn phiên bản đang được hỗ trợ và tương thích với các dependency khác.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>logback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
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
                <configuration>
                    <mainClass>demo.LogbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` kéo theo các dependency logging cần thiết như Logback Core và SLF4J API theo Maven dependency graph. Dự án lớn thường quản lý phiên bản qua BOM hoặc dependency management, tránh cùng classpath có nhiều provider/binding không tương thích.

### 7.3. src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

### 7.4. src/main/java/demo/LogbackDemo.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LogbackDemo {
    private static final Logger ORDERS =
            LoggerFactory.getLogger("demo.orders.OrderService");
    private static final Logger BILLING =
            LoggerFactory.getLogger("demo.billing.PaymentService");

    public static void main(String[] args) {
        ORDERS.debug("event=order.validated orderId={}", "ord-42");
        ORDERS.info("event=order.accepted orderId={}", "ord-42");

        // BILLING kế thừa mức INFO của root, nên DEBUG bị loại.
        BILLING.debug("event=payment.debug_suppressed");

        BILLING.warn(
                "event=payment.retry paymentId={} attempt={}",
                "pay-7",
                2
        );
    }
}
```

### 7.5. Biên dịch và chạy

Mở terminal tại thư mục chứa `pom.xml` (cần JDK 17 và Maven đã cài, lần đầu Maven có thể cần mạng để tải dependency):

```bash
mvn -q compile exec:java
```

**Standard output từ chương trình** với đúng `logback.xml` ở trên (không tính thông báo riêng của Maven, nếu có):

```text
DEBUG | demo.orders.OrderService | event=order.validated orderId=ord-42
INFO | demo.orders.OrderService | event=order.accepted orderId=ord-42
WARN | demo.billing.PaymentService | event=payment.retry paymentId=pay-7 attempt=2
```

Giải thích kết quả:

1. `ORDERS` thuộc prefix `demo.orders`, được cấu hình ở `DEBUG`. Do đó cả DEBUG và INFO được ghi.
2. `BILLING` ở nhánh khác, kế thừa `INFO` từ root; sự kiện DEBUG của BILLING không in.
3. `BILLING.warn(...)` tạo event WARN, có mức cao hơn INFO nên được xuất.
4. Cả hai logger đều chuyển sự kiện đến `STDOUT` ở root do additivity mặc định. Root không lọc lại mức DEBUG đã được ORDERS chấp nhận; appender không có `ThresholdFilter` nên vẫn ghi.
5. Placeholder `{}` được SLF4J thay bằng tham số; không dùng `{0}` của JUL trong code này.
6. Pattern `%level | %logger | %msg%n` cho đầu ra ổn định, không sinh timestamp ngẫu nhiên. Trong production cần thêm các field hỗ trợ điều tra.

**Điều cần ghi nhớ khi chạy:** Java code chỉ import `org.slf4j.*`, không import lớp nội bộ Logback. Nhờ vậy có thể đổi backend mà không phải sửa mọi lời gọi log, dù cấu hình backend và các tính năng nâng cao vẫn khác nhau.

## 8. Ghi log ra file và luân phiên với RollingFileAppender

`FileAppender` ghi file; `RollingFileAppender` kết hợp rolling policy để tạo thế hệ file theo thời gian và/hoặc dung lượng. Ví dụ cấu hình dưới đây dùng `SizeAndTimeBasedRollingPolicy`, phù hợp khi cần quay vòng theo ngày **và** vượt ngưỡng kích thước.

Đây là **đoạn cấu hình minh họa để đưa vào phần `<configuration>`**, thay vì một `logback.xml` chạy độc lập. Phần appender cần được một logger/root tham chiếu mới nhận event:

```xml
<appender name="FILE"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>

    <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>10MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

Các thông số:

- `file`: file đang được ghi, ví dụ `logs/application.log`.
- `fileNamePattern`: tên file lưu lịch sử; `%d` biểu diễn ngày của kỳ rollover; `%i` là chỉ số file trong cùng kỳ khi vượt ngưỡng size; `.gz` cho biết mong muốn nén file lịch sử.
- `maxFileSize`: ngưỡng được dùng để rollover theo dung lượng trong một kỳ; giới hạn không phải cam kết từng byte và phụ thuộc kích thước event.
- `maxHistory`: số kỳ lịch sử cần giữ theo chính sách của rolling policy, không nhất thiết là số file tuyệt đối.
- `totalSizeCap`: giới hạn tổng dung lượng lịch sử theo chính sách dọn của rolling policy; không phải hệ thống cảnh báo đầy ổ đĩa hay quota tuyệt đối tức thời.
- `encoder`: định dạng nội dung file; có thể thay bằng encoder phù hợp hệ thống thu thập log.

Cấu hình này giả định thư mục log có thể được tạo hoặc sử dụng với quyền phù hợp trong môi trường triển khai. Chính sách dọn lịch sử thường gắn với rollover hoặc cấu hình cleanup; **đừng giả định file cũ được xóa đúng thời điểm lịch nếu không có sự kiện logging/rollover tương ứng**.

Rotation khác retention pháp lý, backup và tính toàn vẹn. Một rolling file cấu hình tốt vẫn không bảo đảm event sống qua mất ổ đĩa hay hệ thống log tập trung bị gián đoạn.

## 9. MDC: thêm request ID mà không đổi tên logger

Khi một request qua nhiều lớp, `requestId` hoặc `traceId` giúp liên hệ các log của cùng luồng. Với SLF4J, MDC thường được sử dụng để gắn một số khóa/giá trị theo ngữ cảnh xử lý:

```java
// Đoạn minh họa trong phương thức; LOG và requestId phải tồn tại.
import org.slf4j.MDC;

MDC.put("requestId", requestId);
try {
    LOG.info("event=order.created orderId={}", "ord-42");
} finally {
    MDC.remove("requestId");
}
```

Đoạn trên **không phải chương trình độc lập**; phần `import` phải đặt ở đầu tệp khi đưa vào mã thực tế. Trong pattern Logback có thể thêm `%X{requestId}`:

```xml
<pattern>%level requestId=%X{requestId} %logger - %msg%n</pattern>
```

Với request đã có `requestId=req-17`, event có thể được xuất theo kiểu `INFO requestId=req-17 ...`. Nếu request ID không tồn tại, trường trong pattern có thể rỗng. Chỉ gắn những định danh được phép lưu trong hệ thống log, không dùng token hay dữ liệu nhạy cảm làm correlation ID.

**Quan trọng về concurrency:** MDC thường gắn với thread/context hiện tại, không tự được truyền qua mọi cơ chế `ExecutorService`, `CompletableFuture`, reactive pipeline hoặc virtual thread. Cần cơ chế propagation tương ứng khi tác vụ đổi ngữ cảnh thực thi, và luôn dọn MDC sau request để tránh lẫn ID của các request khác. Với async appender, xem tài liệu backend về thời điểm chụp dữ liệu MDC của logging event.

## 10. AsyncAppender và tác động đến độ bền

Khi appender ghi file, console hoặc mạng có I/O, luồng nghiệp vụ có thể bị chặn. `AsyncAppender` của Logback cho phép một hàng đợi tiếp nhận event để luồng xử lý khác chuyển đến appender đích.

Sơ đồ:

```text
Request thread
  |
  | LOG.info(...)
  v
AsyncAppender (queue)
  |
  v
Worker thread
  |
  v
ConsoleAppender / FileAppender
```

Điều cần lưu ý:

- Async giảm công việc ghi I/O trên luồng caller trong nhiều tình huống, nhưng vẫn có chi phí tạo event và đưa vào queue.
- Khi queue đầy, tùy cấu hình Logback, event có thể bị loại hoặc caller bị chặn; hiểu `discardingThreshold`, `neverBlock` và mức ưu tiên của event trước khi chọn.
- Khi process chết đột ngột, event còn trong queue có thể mất. Lúc dừng bình thường cần lifecycle shutdown phù hợp và thời gian để worker flush.
- Async không bảo đảm thứ tự toàn cục của log giữa nhiều JVM hoặc các đích khác nhau.
- Không dùng log async thông thường thay cho transaction journal hay audit storage đòi hỏi độ bền.
- Benchmark trên tải thực tế và tính toán lượng dữ liệu; không bật async chỉ vì tên nghe nhanh hơn.

## 11. Logback, JUL và Log4j 2 khác nhau thế nào?

| Tiêu chí | JUL (`java.util.logging`) | Logback | Log4j 2 |
| --- | --- | --- | --- |
| Có sẵn trong JDK | Có | Không; cần dependency | Không; cần dependency |
| API gọi phổ biến | `java.util.logging.Logger` | Thường là `org.slf4j.Logger` | API Log4j 2 hoặc facade khác, tùy tích hợp |
| Cấu hình | `logging.properties` hoặc Java API | `logback.xml`, tích hợp theo framework | Định dạng cấu hình riêng của Log4j 2 |
| Đích xuất | `Handler`, ví dụ `ConsoleHandler`, `FileHandler` | `Appender`, ví dụ `ConsoleAppender`, `RollingFileAppender` | `Appender` của Log4j 2 |
| Mức thường thấy | `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`... | `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE` | Bao gồm các mức và tính năng riêng của Log4j 2 |
| Sử dụng với SLF4J | Cần backend/bridge phù hợp nếu muốn đi qua SLF4J | Logback Classic là backend phổ biến | Có thể chọn provider/adapter phù hợp |

**Không mặc định rằng logger JUL sẽ xuất qua Logback.** Lời gọi `java.util.logging.Logger.getLogger(...)` vẫn đi theo JUL nếu chưa cấu hình bridge phù hợp. Khi tích hợp bridge, cần tránh chu trình chuyển log (ví dụ dùng đồng thời các bridge ngược chiều có thể tạo vòng lặp).

Chọn công cụ dựa trên dependency hiện có, mức kiểm soát cần thiết, chính sách vận hành và khả năng tích hợp; không có một lựa chọn duy nhất đúng cho mọi ứng dụng.

## 12. Nguyên tắc ghi log tốt khi dùng Logback

1. **Đặt logger theo class:** ví dụ `LoggerFactory.getLogger(OrderService.class)` thay vì `getLogger("order-" + requestId)`. Tên ổn định giúp quản lý theo package.
2. **Chọn level theo kết quả:** INFO cho cột mốc đáng ghi, WARN cho suy giảm cần quan sát, ERROR cho thất bại thực tế; DEBUG/TRACE cho chẩn đoán. Không log ERROR cho mọi exception nếu fallback đã thành công.
3. **Dùng parameterized logging:** `LOG.info("orderId={}", orderId)` thay vì nối chuỗi khi không cần. Biểu thức tham số vẫn được Java đánh giá trước khi gọi, nên phép tính thực sự đắt cần `isDebugEnabled()` hoặc cơ chế lazy thích hợp.
4. **Truyền `Throwable` đúng cách:** `LOG.error("event=checkout.failed orderId={}", orderId, ex)` để backend có thể in stack trace/cause.
5. **Không log trùng:** phân định tầng chịu trách nhiệm lỗi cuối cùng; kiểm tra additivity và appender để tránh một event xuất nhiều lần.
6. **Tách cấu hình theo môi trường:** mở DEBUG cho namespace cần điều tra với phạm vi và thời hạn rõ ràng; không bật TRACE toàn hệ thống lâu dài.
7. **Bảo vệ dữ liệu:** không đưa password, token, cookie phiên, private key hoặc toàn bộ dữ liệu cá nhân vào log. Kiểm soát cả stack trace/exception message và input có ký tự xuống dòng.
8. **Theo dõi chi phí:** mức log, encoder, file rotation, queue async, retention và dung lượng đĩa đều cần giám sát.
9. **Tối ưu khả năng tìm kiếm:** thống nhất tên `event`, mã lỗi, `requestId`, `traceId`, `durationMs` và đơn vị. Dùng structured logging phù hợp nếu cần truy vấn theo field, không chỉ ghép JSON bằng chuỗi.
10. **Kiểm tra đầu ra thực tế:** chạy ứng dụng tại cấu hình tương đương production, đọc console/file và thử lỗi kèm Throwable để biết stack trace có được giữ không.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| SLF4J báo không có provider | Chỉ thêm `slf4j-api`, thiếu backend hoặc version không khớp. | Kiểm tra dependency graph, thêm **một** provider tương thích như `logback-classic`. |
| Cảnh báo nhiều provider/binding | Classpath chứa nhiều backend cho cùng facade. | Loại dependency thừa; kiểm tra bản SLF4J 1.x hay 2.x. |
| Không thấy DEBUG | Effective level đang INFO; appender có filter; cấu hình khác được nạp. | Xem logger name, level hierarchy, filter và file cấu hình runtime. |
| Một dòng xuất hai lần | Appender được tham chiếu ở nhiều cấp và additivity vẫn bật; hoặc nhiều pipeline cùng ghi. | Kiểm tra root/logger appender và `additivity`. |
| Có message nhưng thiếu stack trace | Chỉ log `ex.getMessage()` hoặc encoder/pipeline bỏ throwable. | Truyền `Throwable` đúng API và xem format cuối cùng. |
| File log không được tạo | Không tham chiếu appender FILE, path/quyền ghi sai, rolling policy cấu hình lỗi. | Xem internal status, quyền ghi, working directory, path và config. |
| Log XML không có tác dụng | `logback.xml` không nằm trên classpath, bị framework override hoặc đặt sai cấu trúc. | Kiểm tra `src/main/resources`, cấu hình active và trạng thái Logback. |
| App không dùng Logback dù đã thêm JAR | Backend khác đang hoạt động hoặc code dùng JUL trực tiếp. | Kiểm tra provider SLF4J, bridges và logging stack của framework. |
| File quá lớn hoặc mất lịch sử sớm | Không cấu hình rolling/retention phù hợp, lưu lượng cao. | Rà rolling policy, maxHistory, totalSizeCap, đường dẫn file và collector. |
| Request ID bị lẫn/thiếu | MDC không được dọn hoặc chưa truyền qua executor/task. | Dùng `try/finally` để xóa context, thêm propagation có kiểm soát. |
| Log làm chậm dịch vụ | Quá nhiều event, tạo message đắt, I/O đồng bộ hoặc queue async quá tải. | Đo đạc, điều chỉnh level, batching/async và volume log theo nhu cầu. |

### Khả năng chẩn đoán cấu hình

Khi không hiểu vì sao cấu hình không có tác dụng, hãy tìm **internal status của Logback**, thông báo lỗi parsing XML và appender đã được gắn. Có thể bật thêm status output khi điều tra (tùy phiên bản/cấu hình), nhưng không đưa dữ liệu nhạy cảm vào file cấu hình chỉ vì mong muốn xem debug. Một số hệ thống cho phép quét và nạp lại cấu hình, chẳng hạn tùy chọn `scan`; điều này cần được kiểm tra trong môi trường thật để không tạo thay đổi bất ngờ khi đang vận hành.

## 14. Checklist tự đánh giá

Sau khi hoàn thành bài, hãy tự trả lời:

- SLF4J và Logback khác nhau ở tầng nào? Nếu chỉ có `slf4j-api` thì ai xuất log?
- Tại sao Logback Classic cần phối hợp đúng phiên bản với SLF4J API/provider?
- Một event từ `demo.orders.OrderService` có thể xuất DEBUG dù root INFO vì sao?
- `additivity="false"` tác động đến appender propagation hay effective level?
- Vì sao appender cần encoder và pattern `%msg%n`?
- Sự khác nhau giữa `FileAppender` và `RollingFileAppender` là gì? Rotation có đồng nghĩa retention không?
- `requestId` nên đặt trong logger name, message hay MDC/structured field?
- Làm sao biết code dùng JUL trực tiếp có thực sự đi qua Logback hay không?
- Một exception được log bằng `ex.getMessage()` có thể mất thông tin gì?
- Khi AsyncAppender queue đầy hoặc tiến trình dừng đột ngột, event có còn được bảo đảm lưu không?

**Kết luận:** Logback là **bộ máy ghi log** trong hệ sinh thái Java; SLF4J thường là **API mà code nghiệp vụ gọi**. Hiểu logger, level, appender, encoder, cấu hình và context giúp ta tạo log có giá trị vận hành, không bị trùng, không quá ồn và có thể điều tra khi có sự cố.