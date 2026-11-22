# Kiểm tra cấu hình logging thực tế trong Java

## Mục tiêu

Một tệp `logback.xml`, `log4j2.xml` hoặc `logging.properties` trông đúng **không đủ để kết luận** ứng dụng đang ghi log theo cấu hình đó. Khi chạy, Java có thể nạp một tệp khác, chọn logging provider khác, áp dụng profile/biến môi trường, kế thừa log level từ logger cha, lọc thêm ở appender hoặc xuất log tới một đích không như dự kiến.

Bài học này hướng dẫn **kiểm tra cấu hình thực tế (effective/runtime logging configuration)** của ứng dụng Java: xác nhận công nghệ logging đang hoạt động, nguồn cấu hình được nạp, mức log thực sự có hiệu lực, handler/appender, cách kế thừa và nơi log thực sự xuất hiện. Trọng tâm là **quan sát và đối chiếu cấu hình đang chạy**, sau đó tìm nguyên nhân khi log bị thiếu, bị lặp hoặc đi sai đích.

Sau bài học, bạn có thể:

- Phân biệt *configured level* (mức khai báo trực tiếp), *effective level* (mức có hiệu lực từ hệ phân cấp) và bộ lọc của handler/appender.
- Kiểm tra runtime logging với Java 17 `java.util.logging` (JUL), SLF4J + Logback, Log4j 2 và ứng dụng Spring Boot.
- Tạo một phép thử log có dấu nhận diện để xác nhận từ API tới đích ghi thực tế.
- Chẩn đoán các trường hợp file cấu hình đúng nhưng runtime chạy khác dự kiến.

## 1. “Cấu hình thực tế” gồm những gì?

Một thông điệp logging thông thường đi qua nhiều quyết định:

```text
Mã Java gọi logger
        |
        v
Logging API / facade (ví dụ SLF4J)
        |
        v
Backend/provider đang được chọn
        |
        v
Tên logger + level kế thừa + filter
        |
        v
Handler/Appender + level/filter riêng + additivity
        |
        v
Layout/Encoder + File/Console/Network destination
        |
        v
stdout, stderr, file, collector hoặc backend log
```

Nếu `logger.info("ready")` không xuất hiện, nguyên nhân có thể nằm ở **bất kỳ** mắt xích nào. Chẳng hạn, logger chấp nhận `INFO` nhưng appender chỉ chấp nhận từ `WARN`; hoặc ứng dụng ghi vào `stderr` trong khi người vận hành chỉ tìm trong tệp.

Các câu hỏi phải trả lời từ **process đang chạy**:

| Cần xác minh | Ví dụ |
| --- | --- |
| API và backend | SLF4J dùng Logback, Log4j 2, JUL hay provider khác? |
| Nguồn cấu hình đã nạp | File trong JAR, file ngoài, cấu hình theo profile, cấu hình mặc định? |
| Logger cụ thể | `com.example.orders` có level khai báo riêng hay kế thừa? |
| Level có hiệu lực | `INFO` thực sự được cho phép ở logger không? |
| Đường tới sink | Logger truyền event cho appender/handler nào? Có truyền lên cha không? |
| Filter bổ sung | Appender/handler có threshold, marker, filter hoặc sampling riêng không? |
| Đích và định dạng | `stdout`, `stderr`, đường dẫn file tuyệt đối, rolling file, JSON hay mạng? |
| Khả năng ghi thật | Tài khoản process có quyền ghi? Log event đã đến đích hoặc collector chưa? |

**Không có một “mức log chung” duy nhất**: level có thể được quyết định ở logger, handler/appender, filter và hệ thống thu thập log. Một phép kiểm tra chỉ nhìn tên file hoặc biến môi trường chưa đủ.

## 2. Tìm đúng provider và nguồn cấu hình đang chạy

### 2.1. Xác định logging stack

Hệ sinh thái Java thường gặp:

- **JUL (`java.util.logging`)**: API và implementation thuộc JDK, điều khiển bằng `LogManager`, `Logger` và `Handler`.
- **SLF4J**: facade logging; hành vi cuối phụ thuộc provider/backend trên classpath, ví dụ Logback hoặc Log4j 2. SLF4J bản thân nó không tự xác nhận file Logback nào đã nạp.
- **Logback**: backend thường dùng với SLF4J, có logger hierarchy, `LoggerContext` và các `Appender`.
- **Log4j 2**: dùng Log4j API/Core hoặc cầu nối từ facade; có `Configuration`, `LoggerConfig`, `Appender`, `Filter`.
- **Framework như Spring Boot**: có thể quyết định cấu hình dựa trên starter, property nguồn ưu tiên cao, active profile và lifecycle của framework.

Nếu ứng dụng dùng SLF4J, tại runtime có thể in **tên class của factory đang được dùng**:

```java
import org.slf4j.ILoggerFactory;
import org.slf4j.LoggerFactory;

public class IdentifyLoggingBackend {
    public static void main(String[] args) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();
        System.out.println(factory.getClass().getName());
    }
}
```

Đây là **ví dụ cần dependency SLF4J**, không phải chương trình chỉ dùng JDK. Đầu ra phụ thuộc provider trên classpath; không được hứa một chuỗi kết quả cố định. Nếu provider không đúng kỳ vọng, kiểm tra các dependency, các bridge logging và thông báo khởi tạo SLF4J. Đừng nhầm “API sử dụng trong source code” với “backend thực sự nhận log”.

### 2.2. Truy vết file cấu hình

Các nguồn cấu hình thường gặp:

1. File đóng gói cùng ứng dụng (`src/main/resources` rồi vào classpath/JAR).
2. File nằm ngoài JAR được chỉ định qua JVM system property hoặc cơ chế cấu hình của backend.
3. Property từ môi trường/framework, profile hoặc cấu hình runtime.
4. Cấu hình mặc định khi backend không tìm được file hợp lệ.
5. Thay đổi level bằng API, giao diện quản trị hoặc một thành phần runtime sau khi ứng dụng khởi động.

**Đọc file trên máy đang vận hành không chứng minh process đã nạp file đó.** Phải kiểm tra đường dẫn nguồn cấu hình và các thông báo chẩn đoán từ **chính process**. Cẩn thận với nhiều tệp cùng tên ở classpath hoặc JAR được đóng gói lại. Khi chạy bằng IDE, Gradle, Docker hoặc lệnh `java -jar`, working directory và classpath có thể khác nhau.

Với JUL, system property tiêu biểu là `java.util.logging.config.file`; với các backend khác, cách đặt tên thuộc tính tùy sản phẩm và phiên bản. Hãy dùng tài liệu của phiên bản đang chạy và đọc log chẩn đoán khi backend khởi động để biết cấu hình nào được chọn.

## 3. Hiểu đúng level kế thừa và bộ lọc

Cấu hình logging thường dựa trên hệ phân cấp tên logger, ví dụ:

```text
(root)
  └── com
       └── com.example
            └── com.example.orders
```

Logger con có thể không khai báo level; khi đó một level từ tổ tiên quyết định xem log có được chấp nhận hay không. **“Level cấu hình trực tiếp = null” không nhất thiết là lỗi**: với JUL/Logback đó có thể là biểu hiện của kế thừa.

Giả sử:

- Logger cha `com.example` có mức `WARN`.
- Logger `com.example.orders` không đặt level riêng.
- Appender tệp chỉ nhận `ERROR` trở lên.

Khi gọi:

| Event | Qua logger? | Qua appender tệp? | Kết quả |
| --- | --- | --- | --- |
| `INFO` | Không | Không xét tiếp | Không xuất |
| `WARN` | Có | Không | Không xuất vào tệp |
| `ERROR` | Có | Có | Có thể xuất nếu các filter/I/O khác cho phép |

Cần kiểm tra **cả logger threshold và appender threshold**. Với Logback, cần kiểm tra thêm `additivity`: khi bật, event có thể truyền lên appender ở tổ tiên và gây log trùng nếu cùng một sink được nối nhiều nơi. Với JUL, cơ chế tương tự là `useParentHandlers`.

Đối với JUL, hàm `logger.isLoggable(level)` trả lời quyết định ở **logger**. Nó không tính đầy đủ quyết định của mọi handler, handler filter hoặc đích xuất. Đối với Logback/Log4j 2, level, additivity và filter cũng cần được xem theo mô hình thực tế của từng backend, không áp đặt semantics của JUL cho mọi thư viện.

## 4. Ví dụ Java 17 chạy độc lập: kiểm tra cấu hình JUL tại runtime

Ví dụ này dùng JDK thuần, không cần Maven hoặc thư viện ngoài. Nó tạo logger cha `lesson.shop` và logger con `lesson.shop.checkout`, đặt:

- Cha có level `WARNING`.
- Con **kế thừa** level của cha.
- Con không gửi event tới handler của cha.
- Con có một `ConsoleHandler` chỉ chấp nhận `SEVERE` trở lên.

Nhờ in các giá trị *từ object đang chạy*, chúng ta thấy rõ vì sao một log `WARNING` có thể được logger chấp nhận nhưng không xuất ra console.

Lưu thành tệp `InspectLoggingConfig.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class InspectLoggingConfig {
    public static void main(String[] args) {
        Logger parent = Logger.getLogger("lesson.shop");
        Logger logger = Logger.getLogger("lesson.shop.checkout");

        parent.setLevel(Level.WARNING);
        logger.setLevel(null); // Kế thừa level.
        logger.setUseParentHandlers(false);

        Handler handler = new ConsoleHandler();
        handler.setLevel(Level.SEVERE);
        logger.addHandler(handler);

        try {
            System.out.println("logger.name=" + logger.getName());
            System.out.println("logger.configured=" +
                    (logger.getLevel() == null
                            ? "<inherit>" : logger.getLevel().getName()));
            System.out.println("parent.name=" +
                    logger.getParent().getName());
            System.out.println("parent.level=" +
                    logger.getParent().getLevel().getName());
            System.out.println("logger.INFO=" +
                    logger.isLoggable(Level.INFO));
            System.out.println("logger.WARNING=" +
                    logger.isLoggable(Level.WARNING));
            System.out.println("logger.SEVERE=" +
                    logger.isLoggable(Level.SEVERE));
            System.out.println("use.parent.handlers=" +
                    logger.getUseParentHandlers());
            System.out.println("local.handler.count=" +
                    logger.getHandlers().length);
            System.out.println("handler.type=" +
                    handler.getClass().getSimpleName());
            System.out.println("handler.level=" +
                    handler.getLevel().getName());
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+ trong một JVM mới với cấu hình JUL mặc định:

```bash
javac InspectLoggingConfig.java
java InspectLoggingConfig
```

Stdout:

```text
logger.name=lesson.shop.checkout
logger.configured=<inherit>
parent.name=lesson.shop
parent.level=WARNING
logger.INFO=false
logger.WARNING=true
logger.SEVERE=true
use.parent.handlers=false
local.handler.count=1
handler.type=ConsoleHandler
handler.level=SEVERE
```

Giải thích từng kết quả:

1. `logger.getLevel() == null` cho biết **logger con chưa đặt mức trực tiếp**; nó kế thừa `WARNING` từ cha.
2. `logger.isLoggable(Level.INFO)` là `false`, còn `WARNING` và `SEVERE` là `true`, vì quyết định của logger dựa trên level được kế thừa.
3. `logger.getUseParentHandlers() == false` cho biết event không được chuyển tiếp tới handler của cha.
4. Logger con có một `ConsoleHandler` với level `SEVERE`. Vì thế, nếu gọi `logger.warning("...")`, logger sẽ chấp nhận tạo record, nhưng **handler này** không publish nó. `logger.severe("...")` qua được cả hai điều kiện (nếu không có filter khác). Ví dụ không phát ra log thực để giữ stdout ổn định và tránh timestamp/`stderr` từ formatter.
5. `finally` tách và đóng handler mà chương trình đã tạo, phù hợp nguyên tắc tài nguyên do ai tạo thì người đó đóng.

**Giới hạn tính xác định:** ví dụ giả định một JVM mới với cấu hình JUL mặc định, không có cấu hình ngoài tự thêm handler vào logger `lesson.shop.checkout`. Một ứng dụng thực có thể đã đăng ký handler/filter từ trước; lúc đó số handler và đích ghi cần kiểm tra trực tiếp, không giả định bằng 1. `isLoggable` chỉ kiểm tra logger, không thay cho kiểm tra việc publish tới sink.

### 4.1. Kiểm tra `logging.properties` với JUL

Một file JUL có thể khai báo các property như:

```properties
.level=INFO
handlers=java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level=WARNING
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
com.example.orders.level=FINE
```

Để chỉ định file cho một ứng dụng JUL, ví dụ:

```bash
java -Djava.util.logging.config.file=logging.properties -cp . YourMainClass
```

`YourMainClass` là tên lớp main của **ứng dụng thực**, không phải tên chương trình mẫu ở trên. Nên xác minh option JVM được truyền ở lúc khởi động và chạy vào đúng tệp trong working directory hoặc dùng đường dẫn tuyệt đối. Các logger/handler tạo lúc khởi động sẽ nhận cấu hình theo cơ chế JUL; thay đổi file sau đó không tự bảo đảm cấu hình đang chạy được cập nhật. Nếu ứng dụng gọi `LogManager.readConfiguration()` hoặc tự cấu hình programmatically, trạng thái runtime có thể khác file ban đầu.

**Đặc biệt:** level `FINE` tương ứng mức chi tiết hơn `INFO` ở JUL; tên level của JUL không hoàn toàn trùng tên level của Logback hay Log4j 2. Không so sánh raw string mà bỏ qua semantics từng backend.

## 5. Kiểm tra SLF4J và Logback khi ứng dụng đang chạy

Nếu Logback Classic là backend, có thể kiểm tra context và logger bằng API runtime. Đoạn dưới là **mã tích hợp** cho dự án đã có SLF4J cùng Logback Classic; nó không phải chương trình Java thuần độc lập.

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.ILoggerFactory;
import org.slf4j.LoggerFactory;

import java.util.Iterator;

public final class InspectLogback {
    public static void show(String loggerName) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();

        if (!(factory instanceof LoggerContext context)) {
            System.out.println("Active SLF4J backend is not Logback");
            return;
        }

        Logger logger = context.getLogger(loggerName);
        Level configured = logger.getLevel();
        System.out.println("configured=" +
                (configured == null ? "<inherit>" : configured));
        System.out.println("effective=" + logger.getEffectiveLevel());
        System.out.println("additive=" + logger.isAdditive());

        Iterator<ch.qos.logback.core.Appender<
                ch.qos.logback.classic.spi.ILoggingEvent>> it =
                logger.iteratorForAppenders();
        while (it.hasNext()) {
            var appender = it.next();
            System.out.println("local appender=" + appender.getName()
                    + ", started=" + appender.isStarted());
        }
    }
}
```

Trong mã ứng dụng có lifecycle logging đang hoạt động, có thể gọi `InspectLogback.show("com.example.orders")` ở một điểm chẩn đoán được bảo vệ hoặc trong test tích hợp.

Cách đọc kết quả:

- `configured` là level đặt trực tiếp tại logger; `<inherit>` nghĩa là lấy từ tổ tiên.
- `effective` là mức đã tính kế thừa và có ý nghĩa trực tiếp hơn khi hỏi logger sẽ nhận mức nào.
- `additive` cho biết sự kiện có đi lên appender của tổ tiên hay không.
- `iteratorForAppenders()` chỉ liệt kê appender **gắn trực tiếp** vào logger được hỏi. Nếu không thấy appender ở logger này, nó vẫn có thể ghi ra appender của tổ tiên khi additivity đang bật.
- `started=false` gợi ý appender chưa/không còn hoạt động; vẫn cần xem lifecycle, filters và lỗi I/O.

Chú ý: `context.getLogger(name)` có thể tạo logger tương ứng nếu chưa tồn tại; khi chỉ thanh tra logger đã đăng ký, có thể dùng API truy xuất không tạo mới của đúng phiên bản Logback. Không gọi các phương thức stop, reset, reconfigure chỉ để kiểm tra, vì chúng làm thay đổi logging runtime.

### 5.1. Đọc cấu hình Logback và xác nhận thực thi

Ví dụ minh họa `logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Cấu hình này **dự định** cho phép `DEBUG` ở `com.example.orders` rồi chuyển lên root appender nếu additivity vẫn bật. Nhưng để biết có hiệu lực hay không, cần xem backend thực tế có phải Logback, file có được nạp, runtime effective level có phải DEBUG, CONSOLE đã start, và log event có xuất hiện ở đúng stream hay không.

Khi file không nạp như mong muốn, xem **status/internal diagnostics** của Logback ở quá trình khởi động hoặc công cụ status phù hợp phiên bản; chúng thường chỉ ra lỗi parse, thiếu appender, resource được chọn hoặc lỗi mở file. Không dựa vào việc “đã có file `logback.xml` trong repository” vì bản build/deployment có thể sử dụng tài nguyên khác.

## 6. Kiểm tra Log4j 2

Với Log4j 2, cần kiểm tra ít nhất ba lớp:

1. **Logger đang dùng**: source tạo logger qua Log4j API hay qua một bridge SLF4J? Backend đang nhận sự kiện có đúng là Log4j 2 Core không?
2. **Configuration/LoggerConfig được chọn**: logger name có match cấu hình riêng không, level thừa kế từ LoggerConfig nào, additivity và filter ra sao?
3. **Appender đã nối và đang hoạt động**: console/file/rolling/async appender nào nhận sự kiện; có `ThresholdFilter` hoặc filter khác chặn một level cụ thể không?

Ví dụ ý tưởng cấu hình `log4j2.xml`:

```xml
<Configuration status="WARN">
  <Appenders>
    <Console name="Console" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="com.example.orders" level="debug" additivity="false">
      <AppenderRef ref="Console"/>
    </Logger>
    <Root level="info">
      <AppenderRef ref="Console"/>
    </Root>
  </Loggers>
</Configuration>
```

Trong ví dụ, logger `com.example.orders` có appender riêng và `additivity="false"` để tránh truyền sự kiện lên root. Tuy nhiên, kết luận đúng phải dựa vào context/configuration đang chạy và một event thực tế, không chỉ dựa vào XML. Khi nghi ngờ sai resource hoặc parse error, bật **chẩn đoán nội bộ của Log4j 2** theo đúng tài liệu phiên bản đang dùng và quan sát quá trình bootstrap.

Đừng bê nguyên cơ chế `Logback LoggerContext` sang Log4j 2; API, cấu trúc configuration và cách tương tác filter không giống nhau. Đặc biệt, nếu nhiều logging bridge/provider được khai báo, hãy xác định backend thực tế trước khi phân tích level.

## 7. Trường hợp Spring Boot: cấu hình đến từ nhiều nguồn

Trong ứng dụng Spring Boot, cấu hình có thể chịu ảnh hưởng của:

- File `application.properties` hoặc `application.yml`.
- Profile đang active và các tệp theo profile.
- Biến môi trường, tham số startup, JVM system properties hoặc config bên ngoài.
- File logging backend riêng mà framework chọn để khởi tạo.
- Thay đổi level sau khởi động qua API quản trị hoặc cơ chế cấu hình động, nếu được bật.

Ví dụ một cấu hình Spring Boot thông dụng:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
  file:
    name: logs/application.log
```

Đây là **cấu hình dự định**, không tự chứng minh runtime đang ghi DEBUG vào tệp ở vị trí nào. Đường dẫn tương đối như `logs/application.log` được hiểu trong ngữ cảnh môi trường chạy; cần xác minh vị trí thực tế, quyền ghi và rotation.

Khi Spring Boot Actuator được cài đặt, cấu hình và endpoint logging được phép truy cập, endpoint `/actuator/loggers` có thể hỗ trợ xem logger level hiện tại. Một response thường có khái niệm `configuredLevel` và `effectiveLevel`. Chỉ dùng endpoint này theo cấu hình bảo mật và phiên bản Actuator đang chạy. Endpoint cấp quyền thay đổi level có tác động runtime; không dùng thao tác cập nhật chỉ để “kiểm tra”.

Cần phân biệt:
- “Property đang có trong Environment” với “logging backend đã đọc và áp dụng property”.
- “Configured level trong Actuator” với “log đã đến appender”.
- “Log file path khai báo” với “đường dẫn thật trong container hoặc host”.

Nếu đổi config mà hành vi không đổi, kiểm tra lại đúng process, active profiles, nguồn property có ưu tiên cao hơn, thời điểm khởi tạo logging và có cần restart/reconfigure hay không.

## 8. Thực hiện phép kiểm tra đầu cuối (end-to-end)

Kiểm tra cấu hình là kiểm tra hành vi, không chỉ đọc metadata. Quy trình thực tế:

**Bước 1 — Xác định process và phiên bản:** ghi nhận command line startup, PID/container instance, bản build/JAR, phiên bản JDK, provider/backend và profile. Tránh kiểm tra nhầm process cũ hoặc một pod khác.

**Bước 2 — Xác định kỳ vọng:** chọn một logger namespace cụ thể, level dự kiến, appender, format, nơi xuất và điều kiện filter. Ví dụ `com.example.orders.CheckoutService` ở INFO phải hiện trên console và có trường `trace_id` khi đang có trace.

**Bước 3 — Thu thập cấu hình runtime:** xem configured/effective level, logger hierarchy, additivity, appender/handler, trạng thái started, nguồn file config và thông báo chẩn đoán. Kiểm tra cả root logger nếu logger con kế thừa.

**Bước 4 — Phát sinh một log kiểm tra có dấu nhận diện:** ở môi trường test hoặc kịch bản an toàn, ghi một thông điệp duy nhất kèm ID:

```java
// Đoạn tích hợp trong ứng dụng có SLF4J và biến logger hợp lệ.
logger.info("LOG_CONFIG_PROBE id={} component={}",
        "probe-2026-11-a1", "checkout");
```

Đây không phải một chương trình độc lập; có thể dùng timestamp/ID động theo lần thử để không nhầm log cũ. Tránh ghi thông tin bí mật hoặc tạo log quá nhiều ở production.

**Bước 5 — Tìm log tại đích thực tế:** tìm cùng probe ID ở console container, tệp được mount, hoặc nền tảng tập trung. Nếu mất log, quan sát ở từng tầng: logger có nhận INFO không? Filter? Appender started? Ghi tới stdout hay stderr? File có quyền/đúng path? Collector có thu thập đúng stream/path?

**Bước 6 — Đối chiếu:** kiểm tra level, timestamp, tên logger, thread, exception stack trace, encoder và context fields. Với async appender có thể có độ trễ; tránh kết luận “không ghi” trước khi pipeline flush hoặc đủ thời gian để xuất.

**Bước 7 — Kết thúc kiểm tra:** nếu đã thay đổi tạm level hoặc bật diagnostics, khôi phục theo quy trình vận hành và ghi nhận bằng chứng: process, logger name, effective level, appender, target, probe ID và kết quả.

Bằng chứng tối thiểu cho một lần kiểm tra có thể ghi:

```text
Process: orders-service instance A / build 2026.11
Backend: SLF4J + Logback
Logger: com.example.orders.CheckoutService
Configured level: <inherit>
Effective level: INFO
Appender path: logger -> root -> CONSOLE
Target: container stdout
Probe ID: probe-2026-11-a1
Observed: one matching event at the expected destination
```

Đây là **ví dụ biểu mẫu**, không phải kết quả đo từ một ứng dụng đã chạy. Dòng “Observed” chỉ được ghi như vậy khi thực tế đã tra cứu và thấy bản ghi tương ứng.

## 9. Các lỗi phổ biến và đường kiểm tra

| Triệu chứng | Giả thuyết cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| File cấu hình đã sửa nhưng runtime không đổi | Process nạp file khác, chưa restart, profile khác, cấu hình runtime override | Xem source config thực nạp, command line, profile, internal diagnostics và effective level |
| `DEBUG` không xuất | Level cha vẫn INFO/WARN, provider khác, handler/appender có threshold | Kiểm tra effective level tại đúng logger và filters/appender |
| `INFO` được `isLoggable` nhưng không thấy log | Handler không nhận INFO; không có appender; sai sink | Kiểm tra trực tiếp handler/appender, additivity, output path và probe |
| Log trùng hai lần | Appender nối ở con và cha; additivity bật | Kiểm tra hierarchy và appender refs ở tất cả các tầng |
| Chỉ thấy log trên IDE, không thấy khi chạy JAR | Working directory/classpath/env khác | Đối chiếu lệnh khởi động, file đóng gói, file ngoài và stream |
| Log ghi ra tệp khác mong đợi | Path tương đối, profile, volume mount, rolling strategy | Xác nhận absolute path của process và nơi mount file |
| Log không có `trace_id` | MDC/context chưa được set, async truyền context sai | Kiểm tra lúc tạo event, thread chuyển giao và cấu hình encoder |
| Lỗi cấu hình bị im lặng | Backend fallback/default, diagnostics không bật | Kiểm tra status/internal logger và stderr của quá trình bootstrap |
| Log đến appender nhưng mất ở hệ thống tập trung | Agent/collector lọc, permission, network, pipeline chậm | So sánh local sink với collector/backend theo cùng probe ID |
| Level thay đổi sau khởi động | Actuator/admin API/code thay đổi runtime | Đọc trạng thái tại thời điểm quan sát, kiểm tra audit/config reload |
| Ứng dụng không đóng file log | Backend/handler chưa được stop hoặc flush đúng lifecycle | Kiểm tra shutdown order, appender lifecycle và queue pending |
| Log lỗi cắt stack trace | Encoder, multiline collection, truncation hoặc log pipeline | Kiểm tra record ở appender nguồn và parser downstream |

## 10. Những giới hạn cần nhớ khi chẩn đoán

**Cấu hình runtime có thể thay đổi:** Một snapshot level tại thời điểm A không bảo đảm giống thời điểm B khi ứng dụng hỗ trợ chỉnh level động, hot reload hoặc framework quản lý lại logger.

**Async logging không tức thời:** Logger và appender có thể đã chấp nhận event nhưng nó vẫn ở queue, buffer hoặc collector. Kiểm thử cần xét timeout, queue overflow và cơ chế flush. Sự kiện không thấy ngay chưa đủ kết luận bị drop.

**Không được tự làm lộ cấu hình nhạy cảm:** Trong môi trường production, tránh in username/password trong endpoint appender, URI chứa token, toàn bộ environment hay cấu hình bí mật. Endpoint quản trị logging cần được bảo vệ; thay level trên production có thể tạo lượng log lớn và rò rỉ dữ liệu.

**Chưa thấy event không đồng nghĩa code không chạy:** Phân biệt chưa thực thi nhánh ứng dụng, logger level từ chối, filter bỏ, appender lỗi, filesystem không ghi, collector không lấy và thao tác truy vấn sai khoảng thời gian/instance.

**Không đóng/reset backend để chẩn đoán read-only:** Những phương thức như `LoggerContext.stop()` hay reset/reconfigure làm thay đổi hệ thống đang chạy. Khi cần thay đổi để khắc phục, thực hiện theo quy trình riêng sau khi đã có bằng chứng.

**Không suy diễn thông số giữa các thư viện:** JUL dùng `FINE/INFO/WARNING/SEVERE`, Logback/Log4j 2 thường dùng `TRACE/DEBUG/INFO/WARN/ERROR`; cấu trúc hierarchy, handler/appender và filter có khác nhau. Dùng API của backend đang hoạt động.

## 11. Checklist kiểm tra cấu hình thực tế

Một kết luận “logging đã được cấu hình đúng” nên đi kèm bằng chứng cho các mục:

1. Đã xác định **đúng process/instance**, JDK, build và active backend/provider.
2. Đã xác nhận **nguồn config thực tế** cùng các override/profile có ảnh hưởng.
3. Đã đọc **logger cụ thể**, level khai báo và **effective level**; hiểu đường kế thừa.
4. Đã xem **handler/appender**, filter, additivity, trạng thái hoạt động và đích xuất.
5. Đã tạo **log probe an toàn**, quan sát nó ở sink mong đợi và đối chiếu ID/thời gian.
6. Đã kiểm tra **độ trễ async**, đường dẫn file/permission và downstream collector khi liên quan.
7. Đã ghi nhận bằng chứng và các thay đổi tạm thời đã được xử lý đúng lifecycle.

Kiểm tra cấu hình logging thực tế là đối chiếu **cấu hình đã nạp → quyết định của logger → quyết định của handler/appender → bản ghi ở đích cuối**. Chỉ khi có bằng chứng ở các tầng đó mới giải thích đáng tin cậy vì sao một mức log xuất hiện, biến mất, bị lặp hoặc đi sai nơi.