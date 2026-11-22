# Filter theo environment trong Java Core Logging

## 1. Mục tiêu

**Filter theo environment** là cách xác định những sự kiện log nào được ghi khi ứng dụng chạy trong các môi trường khác nhau: `dev` (phát triển), `test` (kiểm thử), `staging` (tiền sản xuất) và `prod` (sản xuất). Cùng một đoạn mã `logger.debug(...)` hoặc `logger.info(...)` có thể được giữ lại, bỏ qua hoặc chuyển đến những đích khác nhau tùy cấu hình runtime.

Điều quan trọng là phân biệt **lọc theo level** (chẳng hạn bật DEBUG ở dev, chỉ giữ INFO/WARN/ERROR ở prod) với **lọc theo nội dung hoặc thuộc tính event** (chẳng hạn bỏ sự kiện health-check lặp lại, giữ sự kiện lỗi và sự kiện audit). Chúng thường kết hợp, nhưng không thay thế cho nhau.

Kết thúc bài, bạn có thể:
- Xây dựng chính sách log riêng cho `dev`, `test`, `staging` và `prod` dựa trên mục đích vận hành.
- Giải thích thứ tự logger level, logger filter, handler/appender filter và đích xuất log.
- Viết bộ lọc Java 17+ bằng `java.util.logging.Filter`, chạy và kiểm tra đầu ra cho từng environment.
- Cấu hình Logback/Log4j 2 theo environment, biết phần nào cần backend và phần nào thuộc framework như Spring Boot.
- Test chính sách lọc, tránh cấu hình sai, tránh rò rỉ dữ liệu và giữ thông tin cần thiết khi xảy ra sự cố.

## 2. Vì sao môi trường khác nhau cần chính sách khác nhau?

Một dòng log hữu ích khi lập trình có thể trở thành gánh nặng ở production. Ví dụ, mỗi request có 30 dòng DEBUG giúp lần theo dữ liệu trong dev, nhưng ở prod với hàng nghìn request/giây, lượng DEBUG này tốn CPU, lưu trữ và phí thu thập. Ngược lại, tắt quá nhiều log ở prod sẽ khiến điều tra sự cố thiếu chứng cứ.

Bảng sau là **chính sách minh họa**, cần điều chỉnh theo yêu cầu quan sát và độ tin cậy của hệ thống:

| Environment | Mức log phổ biến | Chính sách lọc sự kiện | Đích log | Mục đích |
| --- | --- | --- | --- | --- |
| `dev` | DEBUG hoặc FINE cho mã đang phát triển | Giữ chi tiết cần debug, có thể bỏ sự kiện lặp vô ích | Console/local file | Điều tra từng luồng xử lý |
| `test` | INFO/WARN mặc định, DEBUG theo test | Thu thập event xác định; hạn chế log framework và dữ liệu ngẫu nhiên | In-memory appender/console CI | Assertion ổn định, log hữu ích khi test fail |
| `staging` | INFO/WARN, bật DEBUG có kiểm soát | Bỏ health probe quá thường xuyên; giữ lỗi, request ID, trace | Collector test và console | Kiểm tra hành vi gần production |
| `prod` | INFO hoặc WARN tùy dịch vụ | Giảm log lặp, ưu tiên lỗi/latency bất thường, giới hạn log đắt | Pipeline tập trung với retention | Quan sát, cảnh báo và điều tra sự cố |

Đây **không phải quy tắc cứng**: dịch vụ quan trọng có thể cần INFO cấu trúc ở production; unit test riêng lẻ có thể bật DEBUG. Quyết định phải dựa vào số lượng event, giá trị chẩn đoán, chi phí và yêu cầu lưu giữ.

**Lưu ý:** tên environment chỉ là đầu vào cấu hình. Java SE không tự gán ý nghĩa đặc biệt cho `app.env`, `spring.profiles.active` hay `APP_ENV`. Ứng dụng hoặc framework phải xác định cách đọc và chuyển những giá trị này thành level, filter và appender.

## 3. Phân biệt logger level và filter theo event

Một luồng logging khái quát:

```text
Code gọi logger.debug/info/warn(...)
              |
              v
      Level / filter sớm
              |
       event được chấp nhận?
         |              |
        Không           Có
         |              |
       Bỏ qua           v
                Tạo/capture LogEvent
                        |
                        v
                 Appender/Handler
                   + bộ lọc đích
                        |
                        v
                  Console / file /
                  collector / test
```

Thứ tự chi tiết **phụ thuộc backend**:
- Với **JUL** (`java.util.logging`), `Logger` có level và `Filter`; `Handler` cũng có level và `Filter`. Nếu logger từ chối một event theo level, chỉ đặt filter ở handler không thể lấy lại nó.
- Với **Logback**, logger level quyết định mức log cơ bản. `TurboFilter` có thể can thiệp sớm trước khi tạo event; bộ lọc thông thường ở appender được đánh giá sau khi event đến appender. Kết quả filter dùng `DENY`, `NEUTRAL` và `ACCEPT`.
- Với **Log4j 2**, có các tầng filter tại global/logger/logger configuration/appender reference/appender. `DENY` loại event; `NEUTRAL` cho các quy tắc tiếp theo xét; `ACCEPT` có ngữ nghĩa tùy tầng, không nên mặc định rằng nó luôn phải đi qua một kiểm tra level giống nhau.

**Lọc sớm** thường tiết kiệm chi phí hơn: không cần tạo event hoặc đưa vào hàng đợi async khi đã biết log không cần ghi. **Lọc tại appender** phù hợp khi một sự kiện cần đến file nhưng không nên xuất hiện ở console; mặt trái là chi phí tạo event có thể đã phát sinh.

### Level, marker và context

| Tiêu chí | Ví dụ | Trường hợp áp dụng |
| --- | --- | --- |
| Level | DEBUG, INFO, WARN, ERROR; JUL: FINE, INFO, WARNING, SEVERE | Phân biệt độ chi tiết và mức nghiêm trọng |
| Logger name/package | `com.example.order` | Bật DEBUG tạm thời cho module cụ thể |
| Marker/event type | `HEALTHCHECK`, `PAYMENT_FAILED` | Bỏ probe lặp, giữ lỗi có ý nghĩa |
| Context | `requestId`, `tenantId`, `traceId` | Tìm kiếm, định tuyến hoặc giới hạn theo ngữ cảnh |
| Environment | `dev`, `test`, `staging`, `prod` | Chọn policy phù hợp thời điểm triển khai |
| Destination | Console, file, audit sink | Mỗi đích nhận tập event riêng |

Không suy diễn chỉ từ level: một event INFO có thể là thông tin nghiệp vụ quan trọng; một event WARN có thể là cảnh báo quen thuộc nhưng vẫn cần giữ để phát hiện xu hướng. Nếu mục tiêu là tách audit bắt buộc khỏi log chẩn đoán, sử dụng đường ghi đáng tin cậy riêng, không để filter chung vô tình loại bỏ audit.

## 4. Thiết kế chính sách trước khi viết mã

Một cách làm rõ ràng là đặt **ma trận policy** được review cùng ứng dụng. Ví dụ cho một dịch vụ xử lý đơn hàng:

| Event | Level | Dev | Test | Staging | Prod |
| --- | --- | --- | --- | --- | --- |
| `debug_cache` | DEBUG/FINE | Giữ | Bỏ mặc định | Bỏ | Bỏ |
| `order_created` | INFO | Giữ | Giữ | Giữ | Giữ nếu có nhu cầu theo dõi nghiệp vụ |
| `health_probe` | INFO | Có thể giữ | Có thể giữ | Bỏ hoặc sampling | Bỏ hoặc đo bằng metrics |
| `order_failed` | ERROR/WARNING | Giữ | Giữ | Giữ | Giữ và tạo cảnh báo khi cần |
| `security_audit` | Tách kênh audit | Giữ | Dữ liệu test | Giữ | Đảm bảo chính sách retention và độ bền |

Đặt rõ **ai sở hữu chính sách** và các ràng buộc:
1. Environment lấy từ nguồn cấu hình **được kiểm soát lúc deploy**, không lấy từ HTTP header do client tùy ý gửi.
2. Giá trị environment được chuẩn hóa và kiểm tra với danh sách hợp lệ. Với tên không biết, có thể fail fast lúc khởi động hoặc dùng policy bảo thủ đã xác định rõ; tránh mặc định DEBUG.
3. Giữ tên sự kiện/marker ổn định theo hợp đồng, đừng chỉ tìm một từ bất kỳ bên trong chuỗi message người dùng.
4. Chỉ thay đổi scope log cần điều tra, kèm giới hạn thời gian và cơ chế khôi phục sau sự cố.
5. Bảo toàn WARN/ERROR có ý nghĩa, exception và audit theo yêu cầu nghiệp vụ. Không xem việc lọc log là cơ chế bảo mật dữ liệu.

Một policy production không nhất thiết “chỉ WARN trở lên”. Ví dụ có thể giữ INFO cấu trúc cho đơn hàng nhưng lọc sự kiện health-check ở cùng level; khi đó filter dựa trên loại event là cần thiết.

## 5. Ví dụ Java 17+ chạy độc lập: lọc level và event theo environment

Ví dụ dùng **Java Util Logging** có sẵn trong JDK, không cần thư viện. Chương trình:
- Đọc system property `app.env`; mặc định chọn `prod` khi thiếu; từ chối giá trị không biết.
- Đặt level của logger theo môi trường.
- Gắn `java.util.logging.Filter` để bỏ event `health_probe` trên `staging`/`prod`.
- Gắn `Handler` riêng in ra stdout, không truyền lên root handler nên không bị in trùng.
- Không giữ state toàn JVM sau ví dụ; logger được tạo riêng bằng `getAnonymousLogger()`.

Tạo file **`EnvironmentLogFilterDemo.java`**:

```java
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class EnvironmentLogFilterDemo {
    enum Environment { DEV, TEST, STAGING, PROD }

    static Environment readEnvironment(String raw) {
        String value = raw.trim().toLowerCase(Locale.ROOT);
        return switch (value) {
            case "dev" -> Environment.DEV;
            case "test" -> Environment.TEST;
            case "staging" -> Environment.STAGING;
            case "prod" -> Environment.PROD;
            default -> throw new IllegalArgumentException(
                    "Unknown app.env: " + raw);
        };
    }

    static Level minimumLevel(Environment env) {
        return switch (env) {
            case DEV -> Level.FINE;
            case TEST, STAGING -> Level.INFO;
            case PROD -> Level.WARNING;
        };
    }

    static boolean allowEvent(Environment env, LogRecord record) {
        if ((env == Environment.STAGING
                || env == Environment.PROD)
                && "health_probe".equals(record.getMessage())) {
            return false;
        }
        return true;
    }

    public static void main(String[] args) {
        Environment env = readEnvironment(
                System.getProperty("app.env", "prod"));

        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(minimumLevel(env));
        logger.setFilter(record -> allowEvent(env, record));

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        sink.setLevel(Level.ALL);
        logger.addHandler(sink);

        try {
            logger.fine("debug_cache");
            logger.info("order_created");
            logger.info("health_probe");
            logger.warning("order_failed");
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac EnvironmentLogFilterDemo.java
```

Chạy riêng từng environment (tham số `-D` phải đứng **trước** tên class):

```bash
java -Dapp.env=dev EnvironmentLogFilterDemo
java -Dapp.env=test EnvironmentLogFilterDemo
java -Dapp.env=staging EnvironmentLogFilterDemo
java -Dapp.env=prod EnvironmentLogFilterDemo
```

**Kết quả chuẩn, mỗi lần chạy là một lệnh độc lập.**

`dev`:

```text
FINE debug_cache
INFO order_created
INFO health_probe
WARNING order_failed
```

`test`:

```text
INFO order_created
INFO health_probe
WARNING order_failed
```

`staging`:

```text
INFO order_created
WARNING order_failed
```

`prod`:

```text
WARNING order_failed
```

Diễn giải:
- `dev` đặt `Level.FINE` nên giữ cả FINE, INFO và WARNING; filter cũng không loại health-check.
- `test` đặt `Level.INFO` nên FINE bị loại ở logger trước khi đến `Filter`.
- `staging` giữ INFO và WARNING nhưng `allowEvent` loại riêng `health_probe`.
- `prod` đặt `Level.WARNING` nên cả INFO và FINE bị loại theo level; điều kiện loại `health_probe` trong filter không còn phải quyết định cho dòng INFO đó.
- Mặc định khi không truyền `-Dapp.env` là `prod`; truyền giá trị sai như `-Dapp.env=production` sẽ ném `IllegalArgumentException` để người triển khai phát hiện sai cấu hình.

Đoạn filter so sánh `LogRecord.getMessage()` bằng chuỗi chính xác **chỉ để minh họa**. Trong ứng dụng lớn, hãy dùng event code, marker hoặc structured field được định nghĩa thống nhất; message tự do có thể bị đổi do localization, tham số hoặc refactor.

Ví dụ dùng `Logger.getAnonymousLogger()` nhằm tránh ảnh hưởng đến logger đã được các test hoặc framework dùng. Với logger có tên trong ứng dụng thật, nhớ rằng level, filter và handler có thể được cấu hình ở nhiều tầng; đừng thay đổi global root logger từ code nghiệp vụ.

## 6. JUL: cấu hình file và vị trí gắn filter

JUL hỗ trợ cấu hình level và handler bằng file properties. Ví dụ tài nguyên dành riêng cho production **`config/logging-prod.properties`**:

```properties
handlers = java.util.logging.ConsoleHandler
.level = WARNING
java.util.logging.ConsoleHandler.level = WARNING
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
com.example.orders.level = INFO
```

Lưu ý: logger `com.example.orders` đặt INFO, nhưng handler root đặt WARNING nên event INFO của logger này **không xuất hiện ở ConsoleHandler**. Muốn INFO đến console, phải điều chỉnh mức handler; đây là ví dụ cố ý cho thấy **hai điểm lọc khác nhau**.

Chạy ứng dụng sử dụng JUL (lệnh minh họa launcher, `com.example.Main` là class ứng dụng của bạn):

```bash
java -Djava.util.logging.config.file=config/logging-prod.properties com.example.Main
```

Phải cung cấp property trước lúc `LogManager` khởi tạo; một ứng dụng thực còn cần classpath/module path đúng. Nếu deploy bằng container hoặc service manager, đường dẫn file cần tồn tại tại môi trường đó, không tự suy đoán working directory.

Hai vị trí gắn filter bằng code:
- `Logger.setFilter(Filter)`: quyết định event được logger hiện tại phát ra hay bỏ.
- `Handler.setFilter(Filter)`: quyết định một handler/sink cụ thể có nhận event hay không.

Vì cả logger và handler có điều kiện nhận event, đặt filter nhận INFO tại handler không thể “khôi phục” INFO đã bị logger bỏ theo level. Không dựa vào filter của một parent logger để thay thế mọi quy tắc của child logger; hãy kiểm tra mô hình hierarchy và handler propagation của JUL khi triển khai.

Khi test, dùng handler in-memory và trả lại cấu hình cũ trong `finally`. Tránh gọi `LogManager.reset()` ở một test chạy song song vì nó tác động đến logging toàn JVM.

## 7. Logback: cấu hình theo environment

Với ứng dụng dùng SLF4J + Logback Classic, **SLF4J** cung cấp API; **Logback** chịu trách nhiệm đọc file và quyết định level/filter. Có hai cách phổ biến:
1. Dùng những file cấu hình riêng (`logback-dev.xml`, `logback-test.xml`, `logback-prod.xml`) và chọn file lúc khởi động.
2. Dùng một cấu hình có tham số level/đích, nhận giá trị từ hệ thống deploy hoặc từ cơ chế cấu hình của framework.

Ví dụ **`config/logback-prod.xml`**:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <pattern>%level %logger{32} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Điều xảy ra:
- Root level `INFO` cho phép INFO, WARN và ERROR đi qua điểm kiểm tra level của logger.
- `ThresholdFilter` ở ConsoleAppender **loại event dưới WARN** chỉ tại đích console này.
- Nếu còn một appender khác nhận INFO, có thể giữ event đó ở đích khác. Nếu **chỉ có console** và không cần INFO ở bất kỳ đích nào, đặt root `WARN` sớm hơn sẽ thường tiết kiệm chi phí tạo/chuyển event.
- `ThresholdFilter` trả về `DENY` cho mức thấp hơn ngưỡng, `NEUTRAL` cho các mức còn lại; đây không phải bộ lọc bỏ mọi event khác WARN.

Với Logback cấu hình mặc định (không bị framework/custom configurator ghi đè), có thể chọn file khi khởi động:

```bash
java -Dlogback.configurationFile=config/logback-prod.xml -jar app.jar
```

Đây là lệnh minh họa cho ứng dụng đã đóng gói thành `app.jar` có Logback trên runtime classpath. Property cần được thiết lập **trước khi Logback khởi tạo**. Logback có cơ chế tìm `logback-test.xml` và `logback.xml` trên classpath nếu không có cấu hình được chọn khác; test resource không được đóng gói nhầm vào production.

**Muốn dev nhận DEBUG:** tạo cấu hình dev có root DEBUG và ngưỡng console DEBUG (hoặc bỏ ThresholdFilter nếu không cần). Giữ cấu hình level và filter như dữ liệu triển khai thay vì viết `if (env) log(...)` rải rác trong logic nghiệp vụ.

### Khi cần lọc theo loại sự kiện

Nếu muốn prod nhận INFO đơn hàng nhưng bỏ riêng INFO health-check, `ThresholdFilter` không đủ: cả hai cùng level. Có thể dùng **marker/MDC và custom Logback Filter**, hoặc một appender riêng cho loại event tương ứng. Filter thông thường của Logback mở rộng `ch.qos.logback.core.filter.Filter<ILoggingEvent>` và trả về `DENY`, `NEUTRAL` hoặc `ACCEPT`. Hãy gắn ở đúng appender, kiểm tra level upstream và hành vi additivity. Với nhu cầu lọc sớm trước khi tạo event, cân nhắc `TurboFilter` theo tài liệu của phiên bản Logback đang dùng.

Không đặt một filter dùng string chứa nội dung bí mật để “lọc tránh rò rỉ”; dữ liệu có thể đã được dựng trong message trước khi appender từ chối nó.

## 8. Log4j 2: dùng marker để lọc sự kiện theo environment

Log4j 2 Core có sẵn `MarkerFilter`. Ví dụ cấu hình production **`config/log4j2-prod.xml`** bỏ event mang marker `HEALTHCHECK` tại console, giữ các event INFO/WARN khác:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <MarkerFilter marker="HEALTHCHECK"
                          onMatch="DENY"
                          onMismatch="NEUTRAL"/>
            <PatternLayout pattern="%p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Ở phía ứng dụng dùng **Log4j 2 API**, đánh dấu event:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.Marker;
import org.apache.logging.log4j.MarkerManager;

// Đoạn minh họa tích hợp; cần Log4j API/Core trong dự án.
Logger logger = LogManager.getLogger("com.example.health");
Marker health = MarkerManager.getMarker("HEALTHCHECK");

logger.info(health, "health_probe"); // Bị bỏ ở ConsoleAppender prod.
logger.info("order_created");        // Vẫn được ConsoleAppender nhận.
logger.warn("order_failed");         // Vẫn được ConsoleAppender nhận.
```

Các lệnh trên là **đoạn mã tích hợp**, không phải chương trình độc lập để chạy với JDK thuần. Để lựa chọn cấu hình bên ngoài khi dùng Log4j Core:

```bash
java -Dlog4j2.configurationFile=config/log4j2-prod.xml -jar app.jar
```

Trong dev, có thể dùng `log4j2-dev.xml` không gắn `MarkerFilter` loại health-check và đặt level DEBUG theo nhu cầu.

**Điểm cần thận trọng:** filter tại appender chỉ ảnh hưởng appender đó, không tự động ngăn event tới các appender khác. Log4j 2 có các tầng filter toàn cục, ở logger, ở appender reference và tại appender. `ACCEPT` và `NEUTRAL` không đồng nghĩa trong mọi tầng: đặc biệt ở tầng global, `ACCEPT` có thể cho event đi tiếp mà bỏ qua một phép so level tại tầng đó. Với quy tắc “không khớp thì tiếp tục xử lý bình thường”, dùng `NEUTRAL` theo tài liệu thay vì `ACCEPT` một cách máy móc.

## 9. Framework và nguồn chọn environment

### 9.1. Java SE, Maven, Gradle, container

Trong Java thuần, bạn tự định nghĩa `app.env` hoặc sử dụng biến môi trường được hệ thống deploy cung cấp. Ví dụ:

```bash
java -Dapp.env=staging EnvironmentLogFilterDemo
```

`app.env` là property **tự đặt trong ví dụ**, không phải property tự động hiểu bởi Logback hoặc Log4j 2. Nếu muốn backend nạp một file cụ thể, dùng property riêng của backend (`logback.configurationFile` / `log4j2.configurationFile`) hay cơ chế do framework hỗ trợ.

Dùng pipeline triển khai để cấp cấu hình:
- Môi trường test chỉ gửi log đến console test hoặc sink giả.
- Staging gửi đến collector staging, không dùng credential/endpoint production.
- Production dùng collector production, retention, rate limit và alert đúng chính sách.
- Biến môi trường và system property nên có danh sách giá trị hợp lệ; ghi lại tên policy/phiên bản cấu hình đã nạp khi ứng dụng khởi động (không in secret).

Đổi biến môi trường của hệ điều hành **sau khi process đã chạy** thường không khiến logger tự động tải lại cấu hình. Reload/hot-update chỉ xảy ra nếu backend/framework và cấu hình cụ thể hỗ trợ. Thay đổi runtime level trong một service cần có kiểm soát, kiểm tra hiệu lực và cơ chế revert.

### 9.2. Spring Boot (nếu dự án dùng Spring Boot)

Spring Boot có thể chọn `application-dev.properties`, `application-test.properties`, `application-prod.properties` bằng active profile. Chẳng hạn file **`application-prod.properties`**:

```properties
logging.level.root=WARN
logging.level.com.example.orders=INFO
```

Đây là **lọc theo level** qua Spring Environment. Khi cần filter theo marker/MDC hoặc appender-specific, vẫn cần cấu hình backend phù hợp, ví dụ `logback-spring.xml`/`logging.config` theo phiên bản. Thành phần mở rộng của Spring Boot không có sẵn trong Logback thuần.

Không nhầm `spring.profiles.active` với `app.env` trong ví dụ Java SE. Chúng do hai cơ chế khác nhau đọc. Trên ứng dụng Boot, đừng tùy ý ghép nhiều lối cấu hình nếu chưa xác định ưu tiên giữa profile, property, file backend và cấu hình được framework nạp lúc khởi động.

## 10. Filter, logging bất đồng bộ và hiệu năng

Khi có async logger hoặc async appender, thời điểm lọc ảnh hưởng chi phí và cách quan sát log:

```text
Application thread
   |
   +-- early level / filter --> bỏ event: thường tránh tạo/copy/enqueue
   |
   +-- tạo event --> async queue --> worker --> appender filter --> sink
                                                  |
                                                  +--> có thể bỏ event sau enqueue
```

Đây là **sơ đồ khái quát**; backend thực tế có thể đặt một số filter trước hoặc sau queue. Nếu chỉ lọc ở appender cuối, event đã dùng CPU/heap và có thể đã chiếm chỗ trong queue dù cuối cùng bị bỏ.

Vì thế:
- **Tối ưu đầu vào:** tắt DEBUG/TRACE sớm cho môi trường không cần, dùng parameterized/lazy logging để tránh tính toán message không cần thiết.
- **Giữ thông tin hữu ích:** nếu cần một số INFO có cấu trúc trong prod, đừng đặt root WARN một cách mù quáng; cân nhắc logger/category cụ thể và marker.
- **Kiểm tra queue đầy:** async có thể block, drop hoặc fallback sync theo policy; filter theo environment không bảo đảm log đã enqueue sẽ đến collector.
- **Đếm sự kiện bị loại:** phân biệt do level/filter chủ động, do lấy mẫu (sampling), do queue đầy và do I/O/collector lỗi. Nếu backend không cung cấp metric trực tiếp, dùng instrumentation phù hợp thay vì dựa vào số dòng ở console.
- **Đánh giá cả hệ thống:** đo requests/s, log generated/accepted/written/dropped, appender latency, p95/p99 request latency, CPU, heap và lỗi thu thập.

Ví dụ khi thử nghiệm giảm health-check từ 100 event/s còn 1 event/s bằng sampling, hãy xác nhận hệ thống metrics vẫn ghi nhận trạng thái sức khỏe; không xóa sạch tín hiệu cần để phát hiện sự cố.

## 11. Test ma trận filter theo environment

Một chính sách lọc nên có **test tự động** cho mỗi environment, thay vì chỉ mở console kiểm tra thủ công.

### 11.1. Ma trận mong đợi từ ví dụ JUL

| Environment | `debug_cache` | `order_created` | `health_probe` | `order_failed` |
| --- | --- | --- | --- | --- |
| dev | Có | Có | Có | Có |
| test | Không | Có | Có | Có |
| staging | Không | Có | Không | Có |
| prod | Không | Không | Không | Có |

Với file Java ở mục 5, có thể chạy bốn lệnh và đối chiếu chính xác kết quả ở mỗi trường hợp. Thử thêm trường hợp thiếu `app.env` và giá trị lạ để xác minh fallback prod hoặc fail fast theo thiết kế.

### 11.2. Kiểm tra ở mức event và backend

Unit test tốt nhất nên assert **LogRecord/ILoggingEvent/LogEvent** hoặc marker/level đã thu thập, thay vì so toàn bộ dòng log có timestamp hay thread ID biến động.

Ví dụ những kiểm tra có ý nghĩa:
1. Prod bỏ `health_probe` nhưng giữ `order_failed`, không làm mất stack trace.
2. Một event INFO trong logger chuyên biệt vẫn đến sink phù hợp nếu policy yêu cầu.
3. Filter đặt ở console không làm mất event ở audit sink khác.
4. Khi đổi environment, cấu hình thực sự được nạp đúng từ test runtime/deployment.
5. Khi dùng async, test đợi worker drain hoặc event xuất hiện với timeout; không dùng `Thread.sleep` cố định rồi giả định log đã flush.

Tránh để các test song song cùng sửa root level/global appender hoặc system property và không khôi phục. Nếu cần kiểm tra cấu hình nạp lúc khởi động, hãy chạy JVM riêng cho mỗi environment để kết quả không phụ thuộc thứ tự test.

### 11.3. Kiểm tra hành vi vận hành

Ngoài unit test, chạy một bài test tích hợp có log thật:
- Tạo một event cùng level nhưng khác marker, xác nhận filter chỉ loại loại sự kiện cần bỏ.
- Tạo exception có stack trace, xác nhận sự kiện vẫn đến sink phù hợp trong prod.
- Gửi log vào collector staging, xác minh không lẫn endpoint/credential production.
- Thử tải cao; quan sát throughput, queue, sampling và tỷ lệ mất log.
- Tắt ứng dụng đúng cách, xác minh flush/drain theo khả năng backend, không tuyên bố đã lưu bền vững chỉ vì logger method trả về.

## 12. Bảo mật và yêu cầu kiểm toán

**Filter theo environment không phải biện pháp ngăn lộ dữ liệu bí mật.** Dữ liệu nhạy cảm có thể đã được ghép thành chuỗi, lưu trong event, xuất sang appender khác hoặc gửi qua pipeline trước khi filter mong muốn chặn nó.

Cách an toàn hơn:
- Không tạo log chứa password, token, session cookie, khóa API, thông tin thanh toán hoặc payload nhạy cảm.
- Chuẩn hóa redaction/masking và sử dụng dữ liệu giả cho test. Review các đường log ngoại lệ vì stack trace đôi khi có thông tin nội bộ.
- Tách audit bắt buộc khỏi log DEBUG/INFO thông thường; chỉ dùng sampling/drop nếu chính sách nghiệp vụ cho phép.
- Không cho client quyết định environment, mức debug toàn cục hoặc tên collector.
- Giới hạn quyền chỉnh sửa config và bật cơ chế ghi nhận thay đổi level/filter khi vận hành production.
- Không để cấu hình test/staging vô tình trỏ về destination hoặc credentials thật của production.

Một sự kiện log bị loại có thể làm mất dấu nguyên nhân sự cố; với sự kiện bảo mật và audit, cần thiết kế pipeline có mức độ tin cậy phù hợp, không chỉ dựa vào queue RAM hoặc một dòng INFO.

## 13. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Prod vẫn in DEBUG | Nạp sai file, bật override hoặc đang dùng backend khác | Kiểm tra config path/backend/profile và effective logger level |
| Staging không còn cả WARN | Filter trả về DENY quá rộng, threshold đặt sai hoặc cấu hình logger/appender chồng nhau | Kiểm tra từng tầng, thử một WARN và một INFO riêng |
| Đặt Handler filter cho INFO nhưng không thấy INFO | Logger đã loại event theo level trước | Hạ ngưỡng logger phù hợp, rồi kiểm tra handler level/filter |
| Một event xuất hiện hai lần | Gắn nhiều appender/handler, additivity hoặc bridge | Kiểm tra đường đi và tham chiếu parent |
| Bỏ health-check cũng bỏ nhầm sự kiện nghiệp vụ | Dùng `contains("health")` trên message tự do | Dùng marker/event code ổn định thay cho từ khóa |
| Test pass local nhưng fail CI | Chọn env sai, system property khác, shared root state, async chưa drain | Dùng config test rõ ràng, chạy JVM riêng, chờ điều kiện có timeout |
| Đổi environment nhưng log vẫn như cũ | Backend khởi tạo trước khi đặt property hoặc không tự reload | Cấp config sớm, restart hoặc dùng cơ chế reconfigure được hỗ trợ |
| Prod vừa bật DEBUG thì latency tăng | Tạo/format quá nhiều event, appender/queue không theo kịp | Giới hạn phạm vi/thời gian DEBUG, theo dõi throughput và drop |
| Có logger INFO nhưng console không có dòng nào | Appender ThresholdFilter/Filter loại INFO hoặc logger additivity | Kiểm tra cả logger và đích xuất |
| “Không thấy log” được hiểu là sự kiện chưa xảy ra | Log có thể bị filter, sampling hoặc async drop | Dùng traces/metrics và event source để đối chiếu |

**Cách điều tra hiệu quả:** xác định backend/provider thực chạy; đọc environment/profile có hiệu lực; xác nhận file được nạp; kiểm tra logger level trước; kiểm tra filter từng tầng và appender/sink sau; cuối cùng kiểm tra async queue, collector và retention. Chỉ tăng DEBUG cho đúng package/scope khi cần.

## 14. Bài tập thực hành

1. Chạy `EnvironmentLogFilterDemo` trên `dev`, `test`, `staging`, `prod`. Giải thích vì sao FINE chỉ có ở dev và health-check không có ở staging.
2. Đổi chính sách prod sang INFO nhưng vẫn bỏ `health_probe`. Cập nhật `minimumLevel` và kiểm tra output; giữ nguyên `allowEvent`.
3. Thêm một loại event `db_ping` lặp nhiều. Thiết kế event code ổn định và policy theo environment, tránh lọc bằng một từ có thể xuất hiện trong message của nghiệp vụ khác.
4. Với dự án Logback, cấu hình một ConsoleAppender nhận WARN trở lên và một đích test nhận INFO. Kiểm tra rằng appender filter chỉ tác động đích tương ứng.
5. Với Log4j 2, gắn marker `HEALTHCHECK`, chọn `log4j2-prod.xml` và `log4j2-dev.xml` khác nhau; đối chiếu số event theo từng level và marker.
6. Viết test cho environment không hợp lệ và thiếu environment. Xác nhận ứng dụng từ chối config sai hoặc dùng fallback an toàn đã quy định.
7. Thử async logging dưới burst; xác nhận log bị filter sớm không chiếm queue và đo rõ những event bị loại do filter so với những event bị drop khi queue đầy.

## 15. Ghi nhớ

- **Environment** quyết định policy quan sát; **level** quyết định độ chi tiết; **event filter/marker** phân biệt các loại sự kiện có cùng level; **appender filter** quyết định đích nào nhận chúng.
- Lọc sớm thường tiết kiệm chi phí hơn lọc muộn, nhất là khi có async queue.
- Cấu hình nên nằm ở runtime/deployment, có giá trị hợp lệ, được test qua ma trận môi trường và có phương án hoàn nguyên.
- Không để lọc log xóa dấu vết lỗi quan trọng, audit hoặc dữ liệu cần quan sát trong production.
- Cần biết đúng backend (JUL, Logback hay Log4j 2) trước khi áp dụng file cấu hình. Cơ chế profile của Spring Boot là một lớp riêng.

### Tài liệu tham khảo

- Oracle Java SE 21 — `java.util.logging.Filter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Filter.html
- Oracle Java SE 21 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Logger.html
- Logback — *Filters*: https://logback.qos.ch/manual/filters.html
- Logback — *Configuration*: https://logback.qos.ch/manual/configuration.html
- Apache Log4j 2 — *Filters*: https://logging.apache.org/log4j/2.x/manual/filters.html
- Apache Log4j 2 — *Configuration*: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Spring Boot — *Logging*: https://docs.spring.io/spring-boot/reference/features/logging.html
