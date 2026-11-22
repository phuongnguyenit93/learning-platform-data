# System property trong Java Logging

## 1. System property là gì và liên quan gì đến logging?

**Java system property** là một cặp khóa–giá trị kiểu chuỗi thuộc về **một tiến trình JVM**. Ứng dụng và thư viện có thể đọc các giá trị này bằng `System.getProperty(...)`. Khi khởi động chương trình, có thể cung cấp chúng qua tùy chọn JVM `-Dkey=value`:

```bash
java -Dapp.log.level=DEBUG -jar application.jar
```

Ở ví dụ trên, `app.log.level` là khóa **do ứng dụng tự quy ước**. Java không tự bật DEBUG chỉ vì một property tên như vậy xuất hiện; mã ứng dụng hoặc logging framework phải chủ động đọc và dùng nó.

System properties có ích cho logging vì môi trường development, test, staging và production thường cần mức log, cấu hình appender, đường dẫn hoặc format khác nhau mà không cần biên dịch lại code. Một số logging backend có các **khóa đặc biệt** được chúng hỗ trợ sẵn; một số khác là khóa tự đặt để nội suy vào cấu hình.

Phân biệt ba dạng cấu hình thường gặp:

| Nguồn | Cách cung cấp | Java đọc bằng | Ví dụ |
| --- | --- | --- | --- |
| JVM system property | `-Dkey=value` khi chạy JVM hoặc `System.setProperty(...)` trong tiến trình | `System.getProperty("key")` | `-Djava.util.logging.config.file=logging.properties` |
| OS environment variable | Thiết lập trong môi trường của process trước khi JVM chạy | `System.getenv("KEY")` | `LOG_LEVEL=DEBUG` |
| Application argument | Đặt sau tên class hoặc `-jar app.jar` | `main(String[] args)` hoặc framework tự phân tích | `--logging.level.root=DEBUG` trong Spring Boot |

Ba nguồn này **khác nhau**; framework có thể kết hợp chúng thành một mô hình cấu hình nhưng không nên coi mọi `--flag` hay biến môi trường đều là system property. System property thuộc JVM hiện tại, không tự động thay đổi cài đặt toàn hệ thống hay các JVM khác.

## 2. Cú pháp `-D` và thời điểm cung cấp giá trị

Dạng cơ bản:

```text
java [JVM options, gồm -Dkey=value] <main-class> [application arguments]
java [JVM options, gồm -Dkey=value] -jar application.jar [application arguments]
```

Ví dụ đúng:

```bash
java -Ddemo.log.level=FINE SystemPropertyLoggingDemo
java -Dlogging.config=classpath:logback-spring.xml -Dlogging.level.root=INFO -jar application.jar
```

Trong lệnh thứ hai, `logging.config` và `logging.level.root` chỉ có tác dụng nếu chương trình khởi động bằng framework hiểu các khóa đó, chẳng hạn Spring Boot trong trường hợp phù hợp.

Ví dụ dễ nhầm:

```bash
java SystemPropertyLoggingDemo -Ddemo.log.level=FINE
```

Ở đây `-Ddemo.log.level=FINE` nằm **sau tên class**, nên chỉ là phần tử `args` truyền vào `main`, không được JVM diễn giải thành system property. Tương tự, `java -jar application.jar -Dlogging.level.root=DEBUG` truyền chuỗi `-D...` cho ứng dụng và không tự tạo JVM property.

Nếu giá trị có dấu cách hoặc ký tự đặc biệt, cần quote cho đúng shell. Với Windows PowerShell, cú pháp như `java "-Ddemo.log.level=FINE" SystemPropertyLoggingDemo` làm rõ đây là một đối số JVM. Với đường dẫn, dùng đường dẫn thực tế theo môi trường và lưu ý thư mục làm việc hiện tại khi dùng đường dẫn tương đối.

Một vài điểm quan trọng:

- `-Dname=value` tạo/đặt giá trị trước khi chương trình khởi tạo; phù hợp với backend đọc cấu hình lúc startup.
- `-Dname` thường đặt giá trị thành chuỗi rỗng, nhưng cần xác định ứng dụng có chấp nhận chuỗi rỗng hay không.
- Nhiều `-D` có thể xuất hiện trên cùng một lệnh; tránh khai báo trùng khóa vì dễ gây nhầm nguồn giá trị.
- Java `System.getProperty("app.log.level")` trả về `null` khi khóa không tồn tại; overload `System.getProperty("app.log.level", "INFO")` cho phép dùng default.
- `System.setProperty("app.log.level", "DEBUG")` thay đổi giá trị trong JVM đang chạy, nhưng **không bảo đảm logging backend tự nạp lại cấu hình**.

## 3. Java 17: tự đọc system property để thiết lập mức log

Ví dụ đầu tiên dùng **`java.util.logging` (JUL)** có sẵn trong JDK. Chương trình đọc một property tự quy ước, áp dụng level vào logger và xuất bản ghi ra `stderr` với formatter ổn định.

Tạo tệp **`SystemPropertyLoggingDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SystemPropertyLoggingDemo {
    public static void main(String[] args) {
        String configured = System.getProperty("demo.log.level", "INFO");
        Level level = Level.parse(configured);

        Logger logger = Logger.getLogger("demo.runtime");
        logger.setUseParentHandlers(false);
        logger.setLevel(level);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.addHandler(console);
        try {
            logger.fine("detail");
            logger.info("ready");
            logger.warning("retry");
        } finally {
            console.flush();
            logger.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch bằng JDK 17+:

```bash
javac SystemPropertyLoggingDemo.java
```

Chạy khi **không truyền `-D`**:

```bash
java SystemPropertyLoggingDemo
```

Kết quả ở **`stderr`**:

```text
INFO: ready
WARNING: retry
```

Chạy với mức `FINE`:

```bash
java -Ddemo.log.level=FINE SystemPropertyLoggingDemo
```

Kết quả ở **`stderr`**:

```text
FINE: detail
INFO: ready
WARNING: retry
```

Chạy với mức `WARNING`:

```bash
java -Ddemo.log.level=WARNING SystemPropertyLoggingDemo
```

Kết quả ở **`stderr`**:

```text
WARNING: retry
```

Các lệnh trên không chủ động xuất dữ liệu qua `stdout`. `ConsoleHandler` của JUL ghi vào `System.err`; terminal thường hiển thị cả `stdout` và `stderr` nên cần phân biệt khi pipe hoặc redirect.

Giải thích:

1. `System.getProperty("demo.log.level", "INFO")` lấy cấu hình tại thời điểm gọi, mặc định `INFO`.
2. `Level.parse(...)` hiểu các giá trị JUL như `FINE`, `INFO`, `WARNING`, `SEVERE`, `ALL`, `OFF`. `DEBUG` **không phải tên level JUL chuẩn**; `Level.parse("DEBUG")` không hợp lệ nếu ứng dụng không định nghĩa level tùy chỉnh.
3. `logger.setLevel(level)` thiết lập ngưỡng logger; `console.setLevel(Level.ALL)` bảo đảm handler không chặn các sự kiện mà logger đã chấp nhận.
4. `setUseParentHandlers(false)` tránh ghi thêm một bản sao qua root handler mặc định.
5. `Formatter` giúp kết quả minh họa ổn định, không phụ thuộc timestamp hay locale của `SimpleFormatter`.
6. `finally` gỡ và đóng handler do ví dụ tự tạo. Không đóng handler thuộc sở hữu của framework hay ứng dụng khác.

Nếu truyền `-Ddemo.log.level=UNKNOWN`, `Level.parse` sẽ ném `IllegalArgumentException` trước khi logger được cấu hình. Ứng dụng production cần quyết định rõ: từ chối cấu hình sai hay dùng default cùng tín hiệu cảnh báo; không nên âm thầm suy diễn mọi chuỗi thành level hợp lệ.

## 4. System property được JUL hỗ trợ sẵn: `java.util.logging.config.file`

JUL có cơ chế đọc tệp cấu hình `logging.properties` qua **`LogManager`**. Không cần viết Java để tự đọc `-Djava.util.logging.config.file`: khóa này được cơ chế khởi tạo JUL của JDK hiểu.

Tạo tệp **`logging.properties`** trong thư mục làm việc:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO

java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s: %5$s%6$s%n

demo.file.level=FINE
```

Giải nghĩa:

- `handlers`: các handler của root logger trong cấu hình JUL.
- `.level=INFO`: mức của root logger.
- `java.util.logging.ConsoleHandler.level=FINE`: handler chấp nhận log từ mức `FINE` trở lên; nếu handler vẫn để `INFO`, log `FINE` của logger con có thể bị chặn.
- `java.util.logging.ConsoleHandler.formatter`: tên class formatter.
- `java.util.logging.SimpleFormatter.format`: định dạng theo các đối số được tài liệu `SimpleFormatter` hỗ trợ. `%4$s` là level, `%5$s` là message, `%6$s` là exception text (nếu có), `%n` là xuống dòng.
- `demo.file.level=FINE`: level của logger có tên `demo.file`.

Lưu chương trình **`JulFileConfigDemo.java`**:

```java
import java.util.logging.Logger;

public class JulFileConfigDemo {
    private static final Logger LOG = Logger.getLogger("demo.file");

    public static void main(String[] args) {
        LOG.fine("detail");
        LOG.info("ready");
        LOG.warning("slow sink");
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac JulFileConfigDemo.java
java -Djava.util.logging.config.file=logging.properties JulFileConfigDemo
```

Dòng được ghi ra **`stderr`** khi JUL đọc được đúng tệp cấu hình trên:

```text
FINE: detail
INFO: ready
WARNING: slow sink
```

Cơ chế hoạt động:

1. JVM nhận system property `java.util.logging.config.file` trước khi tải class ứng dụng.
2. JUL `LogManager` đọc cấu hình tệp theo cơ chế khởi tạo của nó.
3. Logger `demo.file` có level `FINE`, root handler cũng chấp nhận `FINE`.
4. `SimpleFormatter` sử dụng định dạng đã chỉ định nên đầu ra không kèm thời gian.

`java.util.logging.config.file` là **đường dẫn tệp cấu hình JUL**, không phải tên logger. Nếu đường dẫn sai, không đọc được file hoặc nội dung có lỗi, logging có thể chạy với cấu hình khác dự kiến; hãy kiểm tra đường dẫn, thư mục hiện hành, quyền đọc, thông báo khởi tạo và sự kiện thử.

Có thể dùng đường dẫn tuyệt đối khi chạy ở container hoặc service để tránh phụ thuộc `working directory`:

```bash
java -Djava.util.logging.config.file=/opt/app/conf/logging.properties -jar application.jar
```

Lệnh chỉ có ý nghĩa khi `application.jar` dùng JUL hoặc một giải pháp nối/bridge tương ứng; nếu logger của ứng dụng được xử lý bởi một backend khác, chỉ đổi file JUL chưa chắc điều khiển được các logger đó.

### 4.1. Các system property JUL khác đáng biết

- `java.util.logging.config.class`: yêu cầu JUL sử dụng một class cấu hình tùy chỉnh theo cơ chế `LogManager`; đây là hướng nâng cao, cần class khả dụng khi khởi tạo và biết rõ thứ tự cấu hình.
- `java.util.logging.SimpleFormatter.format`: cung cấp chuỗi định dạng cho `SimpleFormatter`; có thể dùng trực tiếp dưới dạng system property. Cú pháp có `$` và dấu `%`, nên cần quote cẩn thận khi đi qua shell; dùng `logging.properties` thường dễ kiểm soát hơn.
- `java.util.logging.config.file`: lựa chọn tệp cấu hình lúc JUL khởi tạo; **đặt property sau thời điểm JUL đã cấu hình không tự động kích hoạt reload**.

Không nhầm `java.util.logging.ConsoleHandler.level` trong tệp `logging.properties` với một `-D...` được JUL bảo đảm đọc trực tiếp mọi lúc. Nhiều dòng cấu hình JUL là **properties trong tệp do LogManager đọc**, không phải tất cả đều là JVM system properties đặc biệt.

## 5. System property trong Logback và SLF4J

Trong dự án dùng **SLF4J + Logback Classic**, `org.slf4j.Logger` dùng để ghi log, còn **Logback** quyết định mức, appender và pattern. Logback có system property thường dùng:

```text
logback.configurationFile
```

Ví dụ khởi chạy một ứng dụng đã được đóng gói và cấu hình để sử dụng Logback:

```bash
java -Dlogback.configurationFile=/opt/app/conf/logback.xml -jar application.jar
```

Tệp này phải tồn tại, đọc được và phù hợp với phiên bản Logback đang chạy. Thuộc tính `logback.configurationFile` phải được cung cấp **trước khi Logback tự khởi tạo** nếu muốn thay đổi nơi nó nạp cấu hình ở startup.

Một ví dụ `logback.xml` đầy đủ và tối giản:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="${app.log.level:-INFO}"/>

    <root level="WARN">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Lệnh chạy:

```bash
java -Dlogback.configurationFile=/opt/app/conf/logback.xml -Dapp.log.level=DEBUG -jar application.jar
```

Trong trường hợp Logback nạp file trên và nội suy property thành công:

- `app.log.level` là **khóa do chúng ta tự chọn**, dùng bởi biểu thức `${app.log.level:-INFO}`.
- `:-INFO` là giá trị dự phòng theo cú pháp thay thế biến của Logback khi không tìm thấy giá trị được định nghĩa.
- Logger `com.example.orders` có mức `DEBUG`; root có mức `WARN`.
- Logger con mặc định có **additivity**, nên sự kiện đã được logger này nhận có thể đi tới appender của root. Do đó `DEBUG` vẫn có thể xuất hiện qua appender `STDOUT`, tùy những filter khác đã được cấu hình. Root level không nhất thiết lọc lại sự kiện đã chấp nhận ở logger con trước khi truyền qua appender.
- Đây là cấu hình **Logback**, không thể sao chép nguyên tên thuộc tính sang mọi logging backend.

Không thể chạy riêng ví dụ XML chỉ bằng `java` nếu chưa có ứng dụng, dependency và class main hoặc JAR hợp lệ. Cũng không có một `stdout` cố định vì thông điệp và thời gian đến từ ứng dụng thật.

### 5.1. Đừng hiểu nhầm SLF4J có system property thống nhất cho mọi backend

SLF4J là façade, nên `-Dapp.log.level=DEBUG` tự thân **không bắt buộc** bất kỳ SLF4J provider nào thay đổi level. Nó chỉ có tác dụng khi cấu hình Logback, Log4j 2, Spring Boot hoặc ứng dụng đang đọc property đó.

Nếu ứng dụng chỉ có SLF4J API nhưng thiếu một provider/backend phù hợp, cấu hình Logback không thể phát huy tác dụng như dự tính. Kiểm tra dependency và provider thực tế; tránh nạp nhiều provider không tương thích.

## 6. Log4j 2: chọn file cấu hình qua JVM property

Trong ứng dụng đang dùng Log4j 2, property phổ biến để chỉ định nguồn cấu hình là:

```bash
java -Dlog4j2.configurationFile=/opt/app/conf/log4j2.xml -jar application.jar
```

Đây là khóa dành cho **Log4j 2**. Giá trị trỏ tới cấu hình mà phiên bản Log4j 2 đang dùng có khả năng truy cập. Nó khác với `logback.configurationFile` và khác với `java.util.logging.config.file`.

Để sử dụng giá trị system property **bên trong** cấu hình Log4j 2, framework có cơ chế tra cứu thuộc tính (lookup) theo syntax và phiên bản của Log4j 2. Một ví dụ khái niệm trong cấu hình XML hỗ trợ lookup:

```xml
<Root level="${sys:app.log.level:-INFO}">
    <AppenderRef ref="Console"/>
</Root>
```

Đây là **một mảnh cấu hình**, chỉ hợp lệ khi nằm đúng chỗ trong file Log4j 2, có appender tên `Console` và phiên bản hỗ trợ syntax thay thế đó. Không sử dụng `<Root>` của Log4j 2 làm phần tử `<root>` của Logback; schema và tên thuộc tính khác nhau.

Trong hệ thống dùng cơ chế auto-reload, cấu hình mới có thể ghi đè mức đã thay đổi runtime. Khi dùng system properties để quyết định cấu hình startup, cần biết rõ **cấu hình có được nạp lại hay không** và các thay đổi runtime được quản lý ra sao.

## 7. Spring Boot: system property đi qua Environment

Spring Boot có hệ thống cấu hình ứng dụng riêng. Một JVM system property thường trở thành **một nguồn cấu hình của Spring Environment** và có thể được dùng để thiết lập logging. Ví dụ đối với ứng dụng Spring Boot đã đóng gói:

```bash
java -Dlogging.level.root=INFO -Dlogging.level.com.example.payment=DEBUG -jar application.jar
```

Theo cách Spring Boot ánh xạ các thuộc tính logging tương ứng:

- `logging.level.root=INFO`: mức log gốc.
- `logging.level.com.example.payment=DEBUG`: mức log dành cho logger/package tương ứng.
- `logging.file.name=/var/log/app/application.log`: ví dụ chỉ định tên file nếu cấu hình backend và môi trường triển khai phù hợp.
- `logging.config=classpath:logback-spring.xml`: ví dụ chỉ định vị trí cấu hình logging; tài nguyên phải thực sự có trên classpath và tương thích backend.

Cũng có thể truyền **application arguments**:

```bash
java -jar application.jar --logging.level.root=INFO --logging.level.com.example.payment=DEBUG
```

Trong Spring Boot, cú pháp `--logging.level...` được phân tích như một nguồn cấu hình ứng dụng; đó **không phải** system property được JVM tạo bởi `-D`. Nguồn nào có ưu tiên cao hơn phụ thuộc vào thứ tự cấu hình của phiên bản/framework và các cách override khác mà ứng dụng dùng. Không nên khai báo cùng một khóa với giá trị mâu thuẫn ở nhiều nguồn.

Trong Spring Boot, logging thường được khởi tạo **rất sớm**. Một lệnh `System.setProperty("logging.level.root","DEBUG")` sau khi ứng dụng đã chạy không tự bảo đảm logging system đổi level tức thì; cần cơ chế quản lý cấu hình runtime mà phiên bản Boot/backend hỗ trợ. Đặc biệt, `logback-spring.xml` là quy ước Spring Boot, không phải tệp cấu hình JUL chuẩn.

## 8. `System.getProperty` khác `System.getenv` như thế nào?

Ví dụ Java 17 độc lập, lưu thành **`LoggingPropertySourcesDemo.java`**:

```java
public class LoggingPropertySourcesDemo {
    public static void main(String[] args) {
        String jvmLevel = System.getProperty("app.log.level", "UNSET");
        String envLevel = System.getenv("APP_LOG_LEVEL");

        System.out.println("JVM property: " + jvmLevel);
        System.out.println("Environment defined: " + (envLevel != null));
    }
}
```

Biên dịch:

```bash
javac LoggingPropertySourcesDemo.java
```

Nếu môi trường chạy **không có** `APP_LOG_LEVEL` và thực hiện:

```bash
java -Dapp.log.level=DEBUG LoggingPropertySourcesDemo
```

Thì `stdout` là:

```text
JVM property: DEBUG
Environment defined: false
```

Nếu OS có `APP_LOG_LEVEL`, dòng `Environment defined` sẽ thành `true`, nhưng giá trị JVM property vẫn là `DEBUG`. Ví dụ chỉ in tình trạng có/không của environment variable để tránh giả định một hệ thống OS cụ thể.

Một hệ thống có thể tự quy định chính sách ưu tiên, chẳng hạn: JVM property `app.log.level` → environment variable `APP_LOG_LEVEL` → giá trị mặc định `INFO`. Đây là **quy ước do ứng dụng viết**; JVM không tự ánh xạ hai tên này thành một.

`System.setProperty` thay đổi bảng properties trong JVM hiện tại; `System.getenv` đọc environment của process và không có API Java chuẩn tương đương để tự thay đổi environment cho toàn tiến trình một cách phổ quát.

## 9. Khởi tạo, cache và thay đổi logging khi đang chạy

Cần tách hai câu hỏi:

1. **Property hiện đang có giá trị gì?** `System.getProperty("app.log.level")` trả lời ở thời điểm đọc.
2. **Logging backend hiện đang áp dụng level/config nào?** Chỉ có thể biết bằng cách xem trạng thái của backend và cấu hình đang có hiệu lực.

Ví dụ:

```java
System.setProperty("app.log.level", "DEBUG");
```

Lệnh trên cập nhật property, nhưng logger có thể đã đọc mức `INFO` từ startup. Không có quy tắc chung yêu cầu mọi backend phải tự gọi `System.getProperty` lại sau mỗi sự kiện log.

Các cách thay đổi thực sự phụ thuộc framework:

- **JUL:** `logger.setLevel(Level.FINE)` trực tiếp tác động lên logger đang dùng; `LogManager.readConfiguration(...)` có thể nạp lại cấu hình JUL trên phạm vi rộng, nên phải hiểu tác động tới các handler khác.
- **Logback:** thay level trên `ch.qos.logback.classic.Logger` hoặc nạp lại cấu hình theo API/vòng đời Logback.
- **Log4j 2:** dùng API cấu hình được hỗ trợ như `Configurator`, hoặc thay đổi nguồn cấu hình theo cơ chế reload của backend.
- **Spring Boot:** quản lý mức log bằng cấu hình và cơ chế runtime tương ứng (nếu được bật), hạn chế sửa system properties tùy tiện trong controller nghiệp vụ.

Vì system properties là **trạng thái chia sẻ cho cả JVM**, nhiều thread và thư viện đều có thể đọc hoặc thay đổi chúng. Không dùng `System.setProperty` cho một request cụ thể để lưu correlation ID: giá trị sẽ không được cô lập theo thread và có thể làm lẫn dữ liệu giữa request. Hãy dùng context/logging MDC hoặc cơ chế trace propagation dành cho logging, đồng thời dọn context đúng vòng đời.

Khi cập nhật mức log tạm thời, cần lưu mức ban đầu, giới hạn thời hạn, điều phối thay đổi đồng thời và trả về trạng thái cũ một cách an toàn. Việc tự đổi root logger trên môi trường nhiều thành phần có thể tạo đột biến log, tăng chi phí I/O hoặc lộ dữ liệu debug.

## 10. Gỡ lỗi khi system property không tác động tới log

Khi truyền `-D` nhưng log vẫn ở mức cũ, kiểm tra theo thứ tự:

1. **Vị trí của đối số:** `-D` phải nằm trong phần JVM options, trước tên main class hoặc trước `-jar`.
2. **Đúng tên khóa:** `java.util.logging.config.file` dùng cho JUL, `logback.configurationFile` cho Logback, `log4j2.configurationFile` cho Log4j 2, `logging.level.*` là quy ước Spring Boot. Các khóa không tự thay thế lẫn nhau.
3. **Đúng backend đang hoạt động:** SLF4J có thể kết nối Logback hoặc backend khác; một file JUL không nhất thiết điều chỉnh được logger qua provider khác.
4. **Có code/cấu hình đọc property không:** khóa tùy biến `app.log.level` chỉ hoạt động nếu được tiêu thụ qua mã hoặc cơ chế substitution.
5. **Có được đặt trước lúc logger/backend khởi tạo không:** gọi `System.setProperty` quá muộn thường không tác động tới cấu hình đã được nạp.
6. **Giá trị hợp lệ không:** JUL dùng `FINE`, `WARNING`, `SEVERE`; Logback thường dùng `DEBUG`, `WARN`, `ERROR`. Không truyền tùy tiện các tên level giữa framework.
7. **Đường dẫn hoặc resource có tồn tại không:** nếu config file không đọc được hoặc sai định dạng, backend có thể chạy fallback và có log khởi tạo trên kênh khác.
8. **Level có bị chặn ở sink không:** logger bật `FINE` nhưng JUL handler để `INFO` thì vẫn không thấy `FINE`.
9. **Có nguồn cấu hình khác ghi đè không:** một config file, biến môi trường, framework bootstrap hay reload có thể quyết định giá trị cuối.
10. **Có thật log được tạo và được thu thập không:** kiểm tra package logger, filter, appender, `stdout`/`stderr`, async queue và collector.

Khi cần xác nhận một property cụ thể trong code, có thể đọc giá trị đó một cách có kiểm soát:

```java
String level = System.getProperty("app.log.level", "<unset>");
System.out.println("Configured level property = " + level);
```

Đây là **mảnh mã minh họa**, không phải chương trình độc lập. Chỉ in các property đã được xác định là không nhạy cảm. Tránh dump toàn bộ `System.getProperties()` vào log: có thể chứa đường dẫn nội bộ, thông tin hệ thống hoặc dữ liệu bí mật nếu ứng dụng truyền secret qua `-D`.

## 11. Bảo mật và vận hành

- **Không truyền mật khẩu/token qua `-D` nếu có lựa chọn quản lý secret phù hợp.** JVM arguments có thể xuất hiện trong một số công cụ kiểm tra process, thông tin chẩn đoán và lịch sử lệnh.
- **Không dùng system property làm kho lưu trạng thái request/thread.** Chúng có phạm vi JVM và có thể bị ghi đè bởi luồng khác.
- **Không tin đầu vào tùy ý cho đường dẫn file logging.** Kiểm tra đường dẫn, quyền đọc/ghi và khu vực được phép trước khi nạp một cấu hình bên ngoài.
- **Không cho mọi người bật TRACE/DEBUG trên production vô thời hạn.** Log chi tiết có thể làm tăng I/O, phát tán thông tin nhạy cảm và khiến async logging bị backpressure.
- **Gắn thay đổi runtime với quyền hạn và audit.** Khi nhiều người đổi level đồng thời, quy tắc hoàn nguyên phải rõ ràng.
- **Đừng dựa vào system properties như nguồn bền vững.** Giá trị đặt bằng `System.setProperty` thường mất khi JVM kết thúc; cấu hình cần được cung cấp lại khi khởi động tiến trình mới.
- **Phân biệt giá trị của JVM với trạng thái backend.** Chẩn đoán cả giá trị property, file cấu hình được nạp, effective logger level và handler/appender thực tế.

## 12. Tình huống thực tế

**Tình huống A — Chạy công cụ Java nhỏ:** dùng `-Ddemo.log.level=FINE` và `System.getProperty` trong code như ví dụ đầu. Đây là cách rõ ràng để điều chỉnh mức log từ lệnh chạy mà không cần thêm dependency.

**Tình huống B — Dùng JUL trong một service:** tạo `logging.properties` và cung cấp `-Djava.util.logging.config.file=...` trước khi process khởi động. Kiểm tra logger level, handler level, format và vị trí file. Nếu deploy nhiều instance, mỗi instance nhận system properties từ lệnh khởi chạy của chính nó.

**Tình huống C — Dùng SLF4J + Logback:** chỉ định `-Dlogback.configurationFile=...` và nội suy property tự đặt vào `logback.xml`. Điều này cho phép cùng một artifact chạy với mức logging khác nhau giữa các môi trường.

**Tình huống D — Dùng Spring Boot:** sử dụng `-Dlogging.level.com.example.payment=DEBUG` hoặc nguồn cấu hình `--logging.level.com.example.payment=DEBUG` theo mô hình quản lý cấu hình của Spring Boot. Khi cần thay đổi lúc runtime, dùng giao diện quản trị/logging system phù hợp thay vì giả định `System.setProperty` tự kích hoạt reload.

**Nguyên tắc cốt lõi:** `-D` cung cấp một giá trị cấu hình cho JVM, nhưng việc nó có làm thay đổi logging hay không phụ thuộc vào **đúng khóa, đúng backend, đúng thời điểm khởi tạo và đúng mức/filter ở nơi xuất log**. Chỉ cần kiểm tra bốn yếu tố này đã giải quyết được phần lớn lỗi cấu hình logging bằng system property.
