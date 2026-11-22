# Tránh duplicate log trong Java Logging: routing đúng, không ghi trùng sự kiện

## 1. Duplicate log là gì?

**Duplicate log** là tình trạng *cùng một sự kiện ghi log* xuất hiện nhiều lần tại cùng đích quan sát ngoài ý muốn. Ví dụ chỉ có **một lời gọi** `log.info("Đã tạo đơn hàng id={}", 42)` nhưng console lại in hai dòng giống nhau; hoặc ứng dụng phát ra một log event duy nhất, trong khi hệ thống tập trung lưu thành hai bản ghi.

Trong Java, duplicate có thể xuất hiện tại nhiều tầng:

- **Tại ứng dụng:** một event được chuyển tới cùng appender/handler hai lần qua cây logger.
- **Tại cấu hình appender:** hai đường khác nhau cùng dẫn tới một sink, ví dụ file được tham chiếu trực tiếp và qua `AsyncAppender`.
- **Tại bridge/provider:** bộ chuyển tiếp hoặc lifecycle khởi tạo logging bị cấu hình nhiều lần, tạo đường route không mong muốn.
- **Tại collection/export:** cùng một event được ingest qua hai pipeline độc lập, chẳng hạn vừa thu stdout vừa nhận bản sao OTLP.
- **Tại lưu trữ/truy vấn:** retry, đọc lại file, ingest trùng hoặc truy vấn hợp nhất nhiều nguồn có thể làm một sự kiện xuất hiện nhiều lần.

**Không phải mọi event hiện diện ở hai nơi đều là lỗi.** Một `ERROR` xuất hiện **một lần ở console** và **một lần trong file** có thể hoàn toàn đúng yêu cầu vận hành. Vấn đề xảy ra khi cùng một đích nhận hai bản không được dự kiến, hoặc backend tập trung coi hai bản của cùng event là hai sự kiện độc lập.

Ví dụ phân biệt:

| Tình huống | Duplicate không? | Vì sao |
| --- | --- | --- |
| Một `log.info`, terminal hiển thị hai dòng giống hệt | Rất có thể | Cùng một sink nhận event hai lần |
| Một event ghi một bản console, một bản rolling file | Chưa chắc | Hai đích khác nhau có thể là chủ đích |
| Hai request độc lập cùng log `GET /health 200` | Không đủ bằng chứng | Text giống nhau nhưng có thể là hai event thật |
| Một event từ stdout và cùng event từ OTLP cùng vào một index | Có nếu không chủ đích | Hai đường thu thập tạo hai bản cho cùng logical event |
| Một exception ghi một message và nhiều dòng stack trace | Không | Stack trace nhiều dòng vẫn có thể là **một** log event |
| Cùng một message tại hai span/request khác nhau | Không tự động | Phải đối chiếu event identity, timestamp và context |

Hậu quả có thể gồm tăng chi phí lưu trữ, nhiễu cảnh báo, sai số đếm lỗi/giao dịch, khó tìm nguyên nhân, cũng như gây hiểu lầm rằng một thao tác nghiệp vụ đã chạy hai lần.

## 2. Mô hình đường đi của một log event

```text
                    [Một lời gọi logger.info()]
                                |
                       Logger effective level
                                |
                  (được cho phép tạo LogEvent)
                                |
                        Logger routing
                    /           |           \
              Logger con    Logger cha     Bridge khác?
                    \           |
                      additivity
                         |
                  Appender references
                    /             \
                Console        AsyncAppender
                                |      |
                              Queue   FileAppender
                                        |
                               File/stdout/network
                                        |
                        Collector / log shipper
                              /        \
                          exporter A  exporter B
                                \       /
                                Backend
```

Có hai câu hỏi cần trả lời tách biệt:

1. **Cùng log event đã được gửi mấy lần tới mỗi appender/sink?** Đây là câu hỏi ở tầng Java logging framework.
2. **Cùng log event đã được collector/backend ghi nhận mấy lần?** Đây là câu hỏi ở tầng pipeline quan sát.

Chỉ quan sát hai dòng trong dashboard không đủ để kết luận sai ở Java logger: có thể Java chỉ ghi một lần, nhưng có hai collector cùng đọc file. Ngược lại, tăng filter/dedup ở backend có thể che lỗi route thật trong ứng dụng.

Một phép chẩn đoán tốt đi **từ nguồn phát sinh tới đích**: xác định số lời gọi log, số lần appender nhận event, số dòng stdout/file và số record ingest.

## 3. Nguyên nhân thường gặp nhất: logger hierarchy và additivity

Trong Logback và Log4j 2, logger được tổ chức theo **cây tên**. Ví dụ:

```text
ROOT
  └─ com
      └─ example
          └─ orders
              └─ OrderService
```

Với logger `com.example.orders.OrderService`, một event được enable có thể đi qua các appender gắn ở logger phù hợp **và các ancestor**. Cơ chế này gọi là **appender additivity** và mặc định thường là `true`.

Giả sử cả `com.example.orders` và `ROOT` cùng tham chiếu appender `STDOUT`:

```text
OrderService.info("created")
   |
   +--> com.example.orders  --[STDOUT]--> một dòng
   |
   +--> ROOT                --[STDOUT]--> dòng thứ hai
```

Khi đó **một lời gọi log có thể khiến cùng appender ghi hai lần**. Cơ chế này được mô tả trực tiếp trong tài liệu chính thức của Logback và Log4j 2.

Hai cách sửa phổ biến:

- **Ưu tiên route qua root:** nếu logger con không cần đích riêng, **bỏ appender reference trùng ở logger con**, giữ `additivity=true`.
- **Route riêng tại logger con:** nếu logger con có chính sách output khác, gắn các appender cần thiết ở logger đó và đặt `additivity=false` để không đi tiếp tới ancestor.

Đặt `additivity=false` bừa bãi có thể làm **mất log** ở console/file/audit vốn được gắn ở root. Cần hiểu đích cuối cùng mong muốn trước khi chỉnh.

### 3.1. Logger level không phải công cụ chống duplicate

`root level="INFO"`, `logger level="DEBUG"` hoặc `appender ThresholdFilter` kiểm soát event nào được tạo/ghi. Chúng không giải quyết tận gốc một route bị tham chiếu hai lần. Giảm level xuống WARN có thể làm bớt dòng trùng nhưng cũng làm mất INFO có giá trị.

Tương tự, thêm một filter theo message để nuốt bản ghi thứ hai không bảo đảm đúng: filter thông thường không biết event đã được gửi qua đường khác hay chưa. Hãy sửa **đồ thị routing**, rồi mới xét filter nếu cần.

## 4. Logback: cấu hình gây duplicate và cách sửa

Giả sử ứng dụng Spring Boot dùng **SLF4J + Logback** và có `logback-spring.xml`.

### 4.1. Cấu hình sai: gắn STDOUT ở root và logger con

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Logger con gắn STDOUT; additivity mặc định true -->
    <logger name="com.example.orders" level="INFO">
        <appender-ref ref="STDOUT"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Lời gọi minh họa trong class ở package `com.example.orders`:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

public void createOrder(long id) {
    LOG.info("Đã tạo đơn hàng id={}", id);
}
```

Đây là **đoạn thành viên class trong dự án đã có SLF4J/Logback**, không phải chương trình chạy độc lập bằng `javac`. Nếu chỉ gọi `createOrder(42)` một lần, console có thể in hai dòng như dưới đây (timestamp là minh họa):

```text
10:15:00.100 INFO com.example.orders.OrderService - Đã tạo đơn hàng id=42
10:15:00.100 INFO com.example.orders.OrderService - Đã tạo đơn hàng id=42
```

Hai dòng này có thể dùng **cùng timestamp gốc của event**, vì không nhất thiết là hai lời gọi tạo event khác nhau.

### 4.2. Cách sửa A: bỏ reference trùng ở logger con

Nếu chỉ cần log đi theo root, cấu hình đơn giản nhất:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Logger này chỉ đổi level; kế thừa STDOUT từ root -->
    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

`com.example.orders` được phép tạo DEBUG và chuyển event tới appender STDOUT của root. **Root INFO không lọc lại** một DEBUG đã được enable ở logger con trong cách truyền appender của Logback. Không có reference STDOUT lặp ở logger con nên event chỉ đi qua một đường đến STDOUT.

### 4.3. Cách sửa B: route riêng và additivity=false

Nếu muốn namespace orders dùng console và file riêng (không đi tới root), khai báo rõ:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ORDER_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/orders.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders"
            level="INFO" additivity="false">
        <appender-ref ref="STDOUT"/>
        <appender-ref ref="ORDER_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Event từ `com.example.orders` ghi một lần lên console và một lần vào `orders.log` — **đây là hai output khác nhau theo thiết kế**. Vì `additivity=false` nên nó không quay lên root để ghi console lần nữa.

Đoạn này dùng `FileAppender` đơn giản cho việc giải thích route. File production cần rolling/retention, quyền truy cập và giám sát dung lượng. Nếu cấu hình riêng bị lỗi đường dẫn hoặc appender không khởi tạo, `additivity=false` có thể khiến log orders mất cả đường fallback từ root; phải kiểm tra status khi khởi động.

**Không mặc định áp `additivity=false` cho mọi logger.** Chỉ áp ở những namespace có đích riêng đã được xác định, và kiểm thử cả log từ logger con của chúng.

## 5. Log4j 2: duplicate do LoggerConfig và AppenderRef

Log4j 2 cũng có additivity trên `LoggerConfig`. Ví dụ cấu hình sai trong `log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%level %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.orders" level="info">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Vì `Logger` không đặt `additivity=false`, event của `com.example.orders` có thể đến `CONSOLE` từ cấu hình con và root.

**Sửa khi cần một route qua root:** bỏ `AppenderRef` trong logger con:

```xml
<Loggers>
    <Logger name="com.example.orders" level="debug"/>
    <Root level="info">
        <AppenderRef ref="CONSOLE"/>
    </Root>
</Loggers>
```

Đây là phần `<Loggers>` **thay thế** trong cấu hình đã khai báo `CONSOLE`, không phải file XML độc lập.

**Sửa khi logger con thật sự cần appender riêng:** giữ `AppenderRef` và khai báo:

```xml
<Logger name="com.example.orders" level="info" additivity="false">
    <AppenderRef ref="CONSOLE"/>
</Logger>
```

Khi `additivity=false`, logger này không tiếp tục gửi tới appender của tổ tiên. Nếu root còn gắn file hoặc hệ thống xuất OTLP, cũng phải quyết định có cần gắn rõ các đích ấy cho logger con hay không, nếu không chúng sẽ **không nhận event** của namespace orders.

Cần nhớ: Log4j 2 có thể đặt filter/level ở Logger, Appender hoặc AppenderRef. Các filter này thay đổi việc nhận event, còn nguyên nhân duplicate nói ở đây là **các đường appender tham chiếu chồng nhau**.

## 6. Java 17+ không thư viện ngoài: tự tái hiện lỗi và sửa với JUL

`java.util.logging` (JUL) gọi thành phần output là **Handler**, không phải Appender. Nó cũng có cơ chế gửi `LogRecord` tới handler của logger hiện tại và logger cha khi `useParentHandlers=true`.

Ví dụ sau cố ý gắn **cùng một ConsoleHandler** vào logger con và logger cha để tạo duplicate. Sau đó bỏ handler ở con, cho log đi qua cha để hết trùng. Đây là chương trình độc lập có thể chạy trên JDK 17.

Tạo file `DuplicateLogDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DuplicateLogDemo {
    private static final class CompactFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName() + " "
                    + formatMessage(record) + "\n";
        }
    }

    public static void main(String[] args) {
        Logger parent = Logger.getLogger("demo.routing");
        Logger child = Logger.getLogger("demo.routing.OrderService");

        parent.setUseParentHandlers(false);
        parent.setLevel(Level.ALL);
        child.setLevel(Level.ALL);
        child.setUseParentHandlers(true);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new CompactFormatter());

        parent.addHandler(console);
        child.addHandler(console); // Cùng một Handler ở hai cấp.

        try {
            System.err.println("BEFORE");
            child.info("order=42");

            child.removeHandler(console); // Chỉ kế thừa qua parent.
            System.err.println("AFTER");
            child.info("order=43");
        } finally {
            child.removeHandler(console);
            parent.removeHandler(console);
            console.close();
        }
    }
}
```

Chạy:

```bash
javac --release 17 DuplicateLogDemo.java
java DuplicateLogDemo
```

JUL `ConsoleHandler` mặc định ghi sang **stderr**. Stdout của `java DuplicateLogDemo` là rỗng; stderr có nội dung chính xác:

```text
BEFORE
INFO order=42
INFO order=42
AFTER
INFO order=43
```

Giải thích:

1. `child.info("order=42")` chỉ tạo **một LogRecord**.
2. `child` gửi record tới handler của nó.
3. Vì `useParentHandlers=true`, record tiếp tục tới handler ở `parent`; cùng đối tượng `console` được gọi lần thứ hai.
4. `child.removeHandler(console)` loại đường ghi trực tiếp của child. Lời gọi `order=43` chỉ đi qua handler tại parent.
5. `parent.setUseParentHandlers(false)` dừng truyền sang root, tránh console mặc định của JUL in thêm một bản.

Ví dụ đóng handler trong `finally` để tránh rò rỉ tài nguyên. Trong chương trình production, nên quản lý handler/LoggerContext theo vòng đời ứng dụng, không tự thay đổi logger toàn cục tùy tiện trong mỗi request.

### 6.1. Sửa bằng setUseParentHandlers(false) có khác gì?

Đối với JUL, có thể giữ handler trực tiếp ở child và gọi:

```java
child.setUseParentHandlers(false);
```

Khi đó child không gửi record lên parent; route chỉ còn handler ở child. Đây là cơ chế tương tự về **ý đồ routing** với `additivity=false` của Logback/Log4j 2. Cách nào đúng tùy chủ ý: cần kế thừa output của cha hay cần output riêng ở con.

### 6.2. Hai Handler khác nhau cùng ghi ra stderr thì sao?

Ngay cả khi không gắn lại cùng một object `ConsoleHandler`, hai handler khác nhau cùng ghi vào stderr vẫn có thể tạo **hai dòng giống nhau**. Vì vậy, khi kiểm tra duplicate, cần so **đích vật lý**, không chỉ tên hoặc identity object appender/handler.

## 7. Một event, nhiều appender: tránh hiểu nhầm

Giả sử root định nghĩa:

```xml
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="ROLLING_FILE"/>
</root>
```

Đây là **đoạn cấu hình Logback bên trong file đã khai báo CONSOLE và ROLLING_FILE**. Khi chỉ gọi `log.info` một lần:

- CONSOLE ghi một bản ra stdout.
- ROLLING_FILE ghi một bản ra file.

Điều này là **fan-out có chủ đích**. Nó chỉ trở thành duplicate ở backend nếu pipeline ingest hai bản vào cùng một luồng/index như hai sự kiện khác nhau mà không có thiết kế tương ứng.

Có thể hai bản chứa timestamp và message giống nhau nhưng khác pattern, MDC hoặc encoding. Phương pháp dedup chỉ so sánh string nguyên văn sẽ không nhận ra chúng. Vì vậy, khi định nghĩa “duplicate” cho hệ thống, cần nói rõ phạm vi: **một lần ở từng sink**, hay **một logical event trong index cuối cùng**.

### 7.1. Lỗi gắn file trực tiếp và qua AsyncAppender

Ví dụ sai về route khi `ASYNC_FILE` bọc `FILE` nhưng root đồng thời tham chiếu cả hai:

```xml
<appender name="ASYNC_FILE"
          class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <appender-ref ref="FILE"/>
</appender>

<root level="INFO">
    <appender-ref ref="FILE"/>
    <appender-ref ref="ASYNC_FILE"/>
</root>
```

Đây là **đoạn thuộc cấu hình Logback có appender FILE đã khai báo**. Một event được gửi trực tiếp tới FILE rồi đi qua queue của ASYNC_FILE để **cùng FILE ghi lần nữa**. Hai bản có thể đến cách nhau một khoảng thời gian, nên nhìn timestamp tại đầu ra chưa đủ để xác nhận nguồn gốc.

Nếu mục tiêu là file async, root chỉ tham chiếu `ASYNC_FILE`:

```xml
<root level="INFO">
    <appender-ref ref="ASYNC_FILE"/>
</root>
```

Không nên thêm nhiều lớp async quanh cùng một sink khi chưa có nhu cầu đã đo đạc. Queue và retry có thể khiến thứ tự hiển thị khác đi, nhưng không tự khử duplicate.

### 7.2. Appender có tên khác vẫn có thể cùng đích

`CONSOLE_A` và `CONSOLE_B` có thể đều ghi `System.out`; `FILE_A` và `FILE_B` có thể dùng cùng đường dẫn file; hai exporter có thể gửi cùng event vào cùng backend. **Tên khác nhau không chứng minh đích khác nhau.**

Tài liệu thiết kế nên có bảng routing ánh xạ logger → appender → sink vật lý → collector → backend. Khi nhìn thấy hai bản log, xác định xem chúng có nhập vào cùng sink từ hai đường hay không.

## 8. Spring Boot: tránh cấu hình mặc định và cấu hình tùy chỉnh chồng nhau

Spring Boot có cơ chế cấu hình logging sẵn có, thường dùng Logback khi ứng dụng giữ starter mặc định. Các yếu tố cần kiểm tra:

- **Backend thực tế:** Logback hay Log4j 2, classpath/provider SLF4J nào được chọn? Không giả định đặt `log4j2.xml` thì ứng dụng chắc chắn đang dùng Log4j 2.
- **File cấu hình có hiệu lực:** `logback-spring.xml`, `logback.xml`, `logging.config` hoặc cấu hình bên ngoài nào thực sự được load? Tránh giữ nhiều file khác nhau rồi sửa sai file.
- **Appender references hiện hành:** root có cả console mặc định hoặc console do mình thêm không? Logger con có trùng reference hay không?
- **Profiles/môi trường:** `springProfile` trong `logback-spring.xml` hoặc overlay config có thể khiến nhiều appender hoạt động ở một profile cụ thể.
- **Khởi tạo lại context:** test suite, container hoặc mã cấu hình programmatic có thể gắn lại handler/appender sau mỗi lần init nếu lifecycle không dọn cũ.
- **Loggers của thư viện:** một thư viện gắn handler riêng với root cũng có sink riêng có thể tạo bản sao.

Ví dụ trong ứng dụng đã có Logback được Spring Boot quản lý, cách đơn giản để nâng mức log của một package là cấu hình:

```properties
logging.level.com.example.orders=DEBUG
```

Nếu chỉ cần thay level, **không cần tạo thêm console appender** tại package. Level riêng và route output là hai quyết định độc lập.

Lưu ý: cảnh báo kiểu “multiple SLF4J providers/bindings” là dấu hiệu cấu hình dependency cần xử lý, nhưng **không tự động chứng minh một lời gọi log được ghi hai lần**. SLF4J thông thường chọn provider theo cơ chế của phiên bản đang dùng; duplicate cần được xác định bằng đường đi thực tế. Đồng thời, nếu cấu hình bridge JUL ↔ SLF4J hoặc chuyển tiếp giữa framework thành vòng lặp, có thể gây đệ quy hoặc lỗi nghiêm trọng, không chỉ thêm một dòng trùng. Chỉ bật những hướng chuyển tiếp có chủ đích.

## 9. Duplicate do ghi log nhiều lần trong mã nghiệp vụ

Không phải mọi duplicate đều do framework. Cần phân biệt **cùng một LogEvent được route hai lần** với **hai LogEvent khác nhau được tạo từ hai lời gọi log**.

Ví dụ:

```java
try {
    paymentGateway.charge(orderId);
} catch (RuntimeException ex) {
    log.error("Payment failed, order={}", orderId, ex);
    throw ex;
}
```

Nếu controller hoặc global exception handler cũng gọi:

```java
log.error("Payment failed, order={}", orderId, exception);
```

thì có **hai lần gọi logger**. Đây không phải lỗi additivity. Có thể cả hai đúng nếu một log bổ sung context ở tầng khác, nhưng thường nên chọn một nơi ghi ERROR kèm stack trace đầy đủ, các tầng còn lại dùng trace context hoặc logging ở level khác nếu có giá trị chẩn đoán.

Các trường hợp thường thấy:

- Một filter/interceptor log request và controller cũng log cùng câu.
- Retry client ghi “failed” cho mỗi lần thử, rồi ghi thêm “failed” cho request tổng; đây có thể là các **sự kiện khác nhau**, nên có `attemptNumber` để phân biệt.
- Một exception bị catch–log–rethrow qua nhiều tầng: mỗi tầng in cùng stack trace.
- Một message listener nhận lại cùng message do cơ chế at-least-once delivery; thực tế handler nghiệp vụ chạy nhiều lần, **không thể xử lý bằng appender additivity**.
- Một scheduled job chạy trên nhiều instance cùng log một mốc; có thể là nhiều execution thật.

Sửa bằng cách xác định **owner** của mỗi loại log nghiệp vụ, phân biệt “attempt”, “request” và “final outcome”, và gắn request/trace/event ID phù hợp. Nếu thực sự có xử lý nghiệp vụ lặp, cần xem idempotency, retry và consumer semantics thay vì chỉ lọc log.

## 10. Duplicate ở Collector và hệ thống quan sát

Ngay cả khi Java chỉ ghi một dòng stdout, backend vẫn có thể thấy hai record. Ví dụ:

```text
                  Java application
                    /          \
        Logback stdout       OTel log appender
              |                    |
       Filelog/agent tail          OTLP
              |                    |
            Collector A         Collector B
                  \               /
                    Same log index
                     -> 2 records
```

Hai workflow thường dùng khi tích hợp OpenTelemetry:

1. **Via stdout/file:** logging framework ghi ra stdout/file; một agent/Collector đọc, parse, thêm resource attributes và gửi backend.
2. **Direct to Collector:** một logging appender/bridge chuyển event thành OTel LogRecord và SDK/exporter gửi qua OTLP.

Cả hai đều hợp lệ. Nhưng nếu **cùng một logical event** được cấu hình đưa vào cùng backend qua **cả hai**, backend có thể lưu hai bản. Khi đó cần chọn một đường ingest chính cho loại event ấy hoặc thiết kế route/dedup có chủ đích. Không nhất thiết tắt traces: log export và trace export là các signal khác nhau.

Các nguyên nhân khác ở tầng collection:

- Hai log collector/sidecar cùng đọc một file hoặc cùng nguồn stdout.
- Một daemonset agent và một forwarder độc lập đều đẩy log container lên cùng hệ thống.
- Một file bị tail lại từ offset cũ khi checkpoint/position state mất, rotate hoặc đổi tên file không được quản lý đúng.
- Collector exporter retry khi trạng thái ACK không rõ; backend có thể nhận lại cùng record, tùy cơ chế delivery và idempotency.
- Một receiver ghi tới hai pipeline/exporter mà kết quả lại hợp nhất ở cùng sink. **Fan-out tới hai backend riêng** là hợp lệ; fan-out quay về **cùng index** dễ tạo trùng.
- Query/dashboard kết hợp nhiều index/data source có chứa bản sao cùng event.

Do đó phải theo dõi cả **cấu hình exporter/receiver** và **query/data source**, không chỉ kiểm tra `logback-spring.xml`.

### 10.1. Dấu hiệu gợi ý tầng gây trùng

| Dấu hiệu | Hướng kiểm tra trước |
| --- | --- |
| Console của một JVM đã có hai dòng | Logger/additivity, appender, handler, mã gọi log |
| Console một dòng, file hai dòng | File appender reference trực tiếp + async/route kép; nhiều writer |
| stdout và file mỗi nơi một dòng, dashboard hai record | Hai đường thu thập từ stdout và file |
| stdout chỉ một dòng, dashboard hai record cùng resource | Collector, exporter retry, tailing/checkpoint hoặc query hợp nhất |
| Hai record có trace_id giống nhưng span_id khác | Có thể là **hai event/span khác nhau**; chưa đủ kết luận duplicate |
| Hai record có message giống nhưng instance khác | Kiểm tra hai pod/process/request hoặc retry nghiệp vụ |
| Trùng xuất hiện sau rolling restart | Collector đọc lại file/offset, hoặc nhiều instance chạy song song |

Không lấy sự giống nhau của `trace_id` làm bằng chứng duy nhất cho duplicate: một request có thể phát hàng chục log event hợp lệ với cùng trace ID.

## 11. Cách định danh và đo duplicate

Để chẩn đoán, phân biệt các lớp identity:

- **Log statement identity:** vị trí trong code/logger name và message template; cùng statement có thể chạy nhiều lần.
- **Event identity:** một lần phát sinh LogEvent cụ thể ở một thread/timestamp.
- **Execution identity:** `trace_id`, `span_id`, `request_id`, `attempt_no`, `message_id` hoặc `job_run_id`.
- **Source identity:** `service.name`, instance/pod ID, process ID, host, stream/file path.
- **Ingestion identity:** collector instance, receiver, exporter, index, pipeline và lần retry.

Nếu nghiệp vụ cần chống trùng chặt chẽ (ví dụ audit event), có thể sinh **event ID ổn định** ngay tại nguồn cho logical business event và bảo toàn ID qua retry/forward. Log thông thường không nhất thiết cần UUID mới cho mọi dòng; chi phí và tính duy nhất của event ID phải được cân nhắc.

Tránh dedup với khóa chỉ là **message + timestamp làm tròn theo giây**: hai sự kiện hợp lệ có thể có cùng text trong cùng giây và bị loại nhầm. Cũng không nên dedup theo trace ID đơn lẻ: một trace chứa nhiều log event.

Khi đo thực tế, có thể so:

```text
Một lần gọi log (đã được enable)
    -> số event được từng appender nhận
    -> số dòng/record vật lý ở source
    -> số record collector đã nhận
    -> số record backend đã lưu
```

Nếu sự trùng bắt đầu trước collector, ưu tiên sửa Java route; nếu chỉ xuất hiện sau collector, tập trung vào pipeline/ingestion. Đừng che lỗi ở nguồn bằng dedup downstream khi còn có thể sửa trực tiếp.

## 12. Quy trình chẩn đoán từng bước

### Bước 1: dùng event kiểm thử dễ phân biệt

Trong môi trường thử nghiệm, cho ứng dụng ghi một event có marker riêng và request ID đã kiểm soát:

```java
log.info("ROUTING_CHECK requestId={} stage={}", "probe-42", "single-call");
```

Đây là lời gọi **trong ứng dụng có SLF4J logger**, không phải standalone. Cần chắc chắn chỉ gọi **một lần** từ một request/một instance trong ca kiểm thử. Không dùng dữ liệu nhạy cảm trong marker.

### Bước 2: kiểm tra lần phát sinh

Tìm các lần gọi logger cùng ý nghĩa trong controller, service, exception handler, filter, interceptor và retry listener. Nếu source đã gọi hai lần, sửa ownership của sự kiện trước khi đổi appender.

### Bước 3: vẽ cây logger và reference

Ví dụ:

```text
ROOT                   -> CONSOLE, APP_FILE
com.example.orders     -> CONSOLE        (additivity=true)
com.example.audit      -> AUDIT_FILE     (additivity=false)
```

Ở cấu hình này, orders có đường CONSOLE bị trùng, trong khi audit đi route riêng. Xác nhận **cấu hình runtime được nạp**, không chỉ file trong source control. Với nhiều profiles, cần kiểm tra profile thực tế.

### Bước 4: kiểm tra sink và pipeline

Xác định stdout, stderr, file active/archive, OTLP và log shipper. Nếu cùng event đi qua hai tuyến, xem chúng có gặp lại ở cùng backend hay không. Đặc biệt kiểm tra các appender wrapper (`AsyncAppender`, routing/sifting) và một sink được tham chiếu hai lần.

### Bước 5: chạy lại và đối chiếu

Sau khi sửa, lặp lại một test ID mới để tránh nhầm với record cũ. Đếm kết quả tại **từng tầng** và kiểm tra cả các logger khác để chắc chắn thay đổi `additivity` không làm mất log hợp lệ.

### Bước 6: kiểm tra tải, retry, restart

Một bản sửa đúng với một request chưa chắc giải quyết trùng khi restart/rolling log hoặc khi collector retry. Chạy kiểm tra có burst, nhiều instance và restart collector với checkpoint theo đúng hệ thống thực.

## 13. Các mẫu cấu hình nên dùng

| Nhu cầu | Mẫu cấu hình | Lý do |
| --- | --- | --- |
| Hầu hết logger cùng ghi console | Gắn console vào root, logger con chỉ điều chỉnh level | Tránh lặp AppenderRef |
| Một namespace cần file riêng và không lên root | Namespace có appender riêng + `additivity=false` | Route rõ, tránh ancestor nhận thêm |
| Một event cần console và rolling file | Root gắn **hai appender khác sink** | Fan-out có chủ đích |
| File cần async | Root gắn **AsyncAppender**, wrapper gắn FileAppender | Không vừa gửi trực tiếp vừa gửi qua queue tới cùng file |
| Log tập trung dùng stdout/file shipper | Export log theo một tuyến stdout/file với collector duy nhất đúng scope | Tránh ingest cùng log từ OTLP và filelog |
| Log tập trung dùng OTLP trực tiếp | Bridge/appender + SDK exporter theo một tuyến log rõ ràng | Tránh ship lại cùng stdout khi pipeline đã nhận OTLP |
| Retry message/transaction | Ghi attempt ID, event ID; nghiệp vụ bảo đảm idempotency | Trùng thực thi không phải lỗi logger |
| Audit cần chống trùng | Bản ghi có event ID và durable storage/unique constraint phù hợp | Dedup mang ngữ nghĩa nghiệp vụ, khác text match |

**Không có một cờ “disable duplicate log” toàn cục** giải quyết mọi tầng. Cách đúng là thiết kế và kiểm tra luồng định tuyến từ logger tới nơi ingest.

## 14. Test chống duplicate trong dự án

Một bảng kiểm có giá trị học tập:

| Case | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Một INFO bình thường | Logger con kế thừa root console | Một event ở console |
| Một ERROR bình thường | Root console + file | Một event mỗi sink, tổng hai đích có chủ ý |
| Logger con có appender riêng | `additivity=false` | Không đi tiếp tới ancestor |
| Logger con chỉ đổi DEBUG level | Không gắn appender riêng | Event DEBUG đi qua route root đúng một lần |
| Async file | Root chỉ tham chiếu wrapper | File nhận một bản cho mỗi event accepted |
| Graceful restart | Dừng/start logging context | Không tích lũy handler/appender duplicate |
| Hai instance | Mỗi instance có instance ID | Phân biệt hai event thật |
| Collector thu stdout | Chỉ một receiver/tailer có ownership rõ | Backend nhận một record mỗi event nguồn |
| OTLP direct và stdout | Kiểm tra route của cùng event | Không ingest hai bản vào cùng index ngoài chủ đích |
| Exception nhiều tầng | Catch–log–rethrow | Chỉ có log theo quy định ownership hoặc có thông tin thêm rõ ràng |

Không chỉ assert rằng **“message xuất hiện đúng một lần ở tất cả mọi nơi”**: ứng dụng có thể chủ đích ghi cùng event vào console và file. Test nên assert **số bản theo từng destination**.

Với kiểm thử tích hợp Logback, có thể gắn appender quan sát vào đúng logger và kiểm tra số lần event đi qua route. Nhưng nếu chính appender kiểm thử lại được gắn ở cả con và cha, test có thể tạo duplicate giả. Hãy chọn một điểm quan sát và reset/close logging context sau test để tránh rò cấu hình sang test khác.

### 14.1. Checklist trước khi đưa cấu hình vào production

1. Đã xác định backend/logging provider thực sự và file cấu hình đang có hiệu lực.
2. Logger con không gắn trùng appender của ancestor khi additivity còn bật.
3. Mỗi appender wrapper và appender đích chỉ được tham chiếu theo route mong muốn.
4. `additivity=false` chỉ đặt nơi có đầy đủ output cần thiết.
5. Không có vòng bridge giữa các logging framework.
6. Một logical log event không bị ingest lặp qua stdout/file/OTLP vào cùng backend.
7. Collector tailing, retry, restart và log rotation đã có checkpoint/ownership được kiểm thử.
8. Có metadata service/instance/trace/request/event ID thích hợp để điều tra trùng thật.
9. Cảnh báo và dashboard đếm từ đúng pipeline, không hợp nhất index trùng không kiểm soát.
10. Log được phép ghi đúng level, không mất ERROR/audit sau khi sửa routing.

## 15. Những lỗi sửa duplicate dễ gây hậu quả

**Sai lầm 1 – đặt `additivity=false` cho mọi namespace.** Có thể khiến một logger chỉ cấu hình level, không có appender riêng, không ghi log ra bất kỳ đâu. Muốn giữ một route qua root thì thường chỉ cần **xóa AppenderRef ở con**.

**Sai lầm 2 – xóa appender console vì thấy hai dòng console.** Nếu nguyên nhân là interceptor log hai lần hoặc collector ingest trùng, xóa console có thể làm mất đường quan sát chính.

**Sai lầm 3 – giảm level từ INFO lên ERROR.** Nó giảm số bản được nhìn thấy nhưng không sửa số đường route; đồng thời làm mất thông tin INFO hợp lệ.

**Sai lầm 4 – dùng regex loại thông điệp giống nhau.** Hai request hợp lệ cùng message vẫn phải được ghi. Dedup theo text có thể che lỗi retry thật hoặc mất dữ liệu phục vụ audit.

**Sai lầm 5 – thêm cả sync lẫn async vào cùng file.** AsyncAppender không thay thế route cũ tự động; cần loại reference trực tiếp nếu muốn wrapper làm đường duy nhất.

**Sai lầm 6 – suy luận từ dashboard mà bỏ qua source.** Collector có thể nhân bản record sau khi Java ghi một bản. Cần xác minh ở stdout/file trước.

**Sai lầm 7 – gắn cùng một handler trong init nhiều lần.** Một số API/framework có thể xử lý việc thêm cùng object khác nhau; còn việc tạo **đối tượng handler mới ở mỗi lần init** thường tích lũy đường ghi. Cần quản lý lifecycle, tránh add mới mỗi lần request hoặc mỗi vòng refresh config.

**Sai lầm 8 – tắt toàn bộ log export khi cần giữ trace.** Export logs, metrics và traces là các kênh tách biệt trong nhiều hệ thống. Hãy quyết định chính sách cho **logs signal** và theo dõi ảnh hưởng tới correlation.

## 16. Một tình huống thực tế: một ERROR, hai dòng ở dashboard

Giả sử một service thanh toán có Logback root console và OTLP logging appender. Đồng thời cluster chạy collector đọc stdout của container. Dashboard báo hai record `ERROR Payment timeout` với cùng `trace_id`, timestamp gần nhau.

Cách xử lý:

1. Xác minh ở stdout của **đúng container instance**: chỉ có một dòng ERROR.
2. Kiểm tra log bridge/appender của ứng dụng: cùng LogEvent có thể đã được xuất thẳng qua OTLP.
3. Kiểm tra collector: receiver stdout và receiver OTLP có cùng gửi đến một logs backend/index không.
4. Xác định kiến trúc mong muốn: giữ stdout → collector hoặc direct OTLP cho sự kiện đó; tránh hai tuyến cùng nhập một index.
5. Triển khai thay đổi, tạo một request kiểm thử mới và xác minh chỉ một logical record ở backend.
6. Kiểm tra rằng trace vẫn được xuất, log vẫn chứa trace context nếu cần, và việc bỏ một log pipeline không làm mất ERROR quan trọng.

Nếu ngay tại stdout đã có hai bản, quay lại kiểm tra `root`/logger con, file cấu hình và hai lời gọi log trong code. **Chỉ tắt một exporter ở Collector không sửa được lỗi gốc trong ứng dụng.**

## 17. Tự kiểm tra kiến thức

1. Khi nào console và rolling file cùng có một event là hành vi đúng?
2. Vì sao chỉ có một lời gọi `logger.info()` nhưng gắn chung appender ở logger con và root lại có thể tạo hai dòng?
3. Nếu muốn logger con chỉ dùng appender riêng, `additivity=false` có tác dụng gì và có thể làm mất output nào?
4. Với Logback `AsyncAppender` bọc file appender, tại sao root không nên tham chiếu đồng thời cả wrapper và file?
5. Console chỉ có một bản nhưng backend có hai: bước điều tra đầu tiên ở tầng nào?
6. Vì sao dedup theo `message` hoặc chỉ `trace_id` có thể xóa mất log hợp lệ?
7. Trường hợp nào duplicate thật sự là biểu hiện của nghiệp vụ bị xử lý/retry hai lần thay vì lỗi logging framework?

**Nguyên tắc cần nhớ:** mỗi logical event phải có **đường đi rõ ràng đến từng sink dự kiến**. Kiểm tra logger hierarchy, appender/handler references, wrapper và pipeline ingest theo thứ tự; sửa nơi phát sinh đường trùng thay vì bỏ log bằng filter không có ngữ nghĩa.

## Tài liệu tham khảo

- [Logback – Architecture và appender additivity](https://logback.qos.ch/manual/architecture.html).
- [Logback – Configuration: ví dụ duplicate appender reference](https://logback.qos.ch/manual/configuration-xml.html).
- [Logback – AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html).
- [Apache Log4j 2 – Architecture, Appender Additivity](https://logging.apache.org/log4j/2.x/manual/architecture.html).
- [Apache Log4j 2 – Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html).
- [Java Platform – java.util.logging.Logger](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Logger.html).
- [Java Platform – java.util.logging.ConsoleHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/ConsoleHandler.html).
- [OpenTelemetry – Java log instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/).
- [OpenTelemetry – Logs overview, stdout/file và direct collector](https://opentelemetry.io/docs/specs/otel/logs/).