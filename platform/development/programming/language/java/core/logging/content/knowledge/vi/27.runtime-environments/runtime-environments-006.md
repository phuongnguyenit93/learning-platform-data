# Biến môi trường trong Java Core Logging

## 1. Biến môi trường liên quan gì đến logging?

Một chương trình Java thường chạy ở nhiều môi trường: máy phát triển, máy kiểm thử, staging, production, container hoặc máy chủ CI. Cùng một đoạn code ghi log có thể cần các chính sách khác nhau:

- **Development:** xuất log chi tiết (`DEBUG`, `TRACE` hoặc `FINE`, tùy thư viện) để tìm lỗi nhanh.
- **Production:** ưu tiên `INFO`, `WARN`/`WARNING` hoặc `ERROR`/`SEVERE`; hạn chế khối lượng log và dữ liệu nhạy cảm.
- **Container:** thường gửi log ra stdout/stderr để hệ thống triển khai thu thập.
- **Điều tra sự cố tạm thời:** thay đổi mức log cho một nhóm thành phần, có kiểm soát thời hạn và chi phí.

**Biến môi trường (environment variable)** là một cặp tên–giá trị dạng chuỗi được hệ điều hành hoặc công cụ khởi chạy cung cấp cho **tiến trình** Java. Ứng dụng đọc biến để chọn cấu hình khi chạy, thay vì phải sửa mã nguồn hay biên dịch lại chỉ vì thay đổi mức logging.

Ví dụ đặt biến `APP_LOG_LEVEL=FINE` trước khi khởi động ứng dụng. Nếu code hoặc logging backend được cấu hình để đọc biến đó, ứng dụng có thể bật log chi tiết. **Bản thân JDK không quy định `APP_LOG_LEVEL` là biến logging chuẩn.** Đặt tên biến không tự làm mọi Logger đổi level.

Điều cốt lõi cần nhớ: biến môi trường chỉ là **đầu vào cấu hình**; ứng dụng, framework hoặc backend phải chủ động **đọc và áp dụng** nó.

## 2. Phân biệt biến môi trường, JVM system property và file cấu hình

| Cơ chế | Cách đọc trong Java | Ví dụ | Phạm vi |
| --- | --- | --- | --- |
| OS environment variable | `System.getenv("APP_LOG_LEVEL")` | `APP_LOG_LEVEL=INFO` | Được cung cấp cho tiến trình từ lúc khởi chạy |
| JVM system property | `System.getProperty("app.log.level")` | `java -Dapp.log.level=FINE ...` | Bảng thuộc tính của JVM, có thể được thay đổi bằng API |
| File cấu hình | Logging backend hoặc code đọc file | `logging.properties`, `logback.xml`, `log4j2.xml` | Quy tắc logger, handler/appender, layout, filter, đường dẫn |
| Cấu hình framework | Framework tổng hợp nhiều nguồn | `LOGGING_LEVEL_ROOT=DEBUG` trong Spring Boot | Phụ thuộc quy tắc ánh xạ, ưu tiên và vòng đời framework |

**`System.getenv` khác `System.getProperty`:**

~~~java
String fromEnvironment = System.getenv("APP_LOG_LEVEL");
String fromJvmProperty = System.getProperty("app.log.level");
~~~

Hai lệnh đọc hai kho cấu hình khác nhau. Nếu chương trình chỉ gọi `System.getenv("APP_LOG_LEVEL")`, tham số `-Dapp.log.level=FINE` **không có tác dụng**, trừ khi code hoặc framework có cơ chế đọc system property tương ứng. Tương tự, `System.setProperty("app.log.level", "FINE")` không sửa biến môi trường của hệ điều hành.

**Phạm vi và thời điểm:** tiến trình Java thường nhận một bản môi trường khi được khởi chạy. Đặt hoặc sửa biến ở một terminal khác **sau khi Java đã chạy** không khiến `System.getenv()` trong tiến trình đang chạy tự cập nhật. Với framework có reload hoặc management API, việc đổi cấu hình runtime có thể khả thi qua **cơ chế riêng của framework**, không phải nhờ môi trường của tiến trình tự thay đổi.

Trên Linux/macOS, tên biến môi trường thường **phân biệt chữ hoa–thường**. Trên Windows, quy tắc tên môi trường của hệ điều hành khác; để dễ triển khai đa nền tảng, nên nhất quán dùng tên như `APP_LOG_LEVEL` và tránh tạo biến chỉ khác nhau ở chữ hoa–thường. Giá trị đọc từ môi trường luôn là chuỗi và cần được kiểm tra trước khi chuyển thành enum, level hoặc đường dẫn.

## 3. Ví dụ Java 17 chạy độc lập: điều khiển logger từ môi trường

Ví dụ dưới đây dùng **`java.util.logging` (JUL)**, có sẵn trong JDK. Ta tự định nghĩa quy tắc ưu tiên:

1. Nếu có JVM property `app.log.level` khác rỗng, dùng giá trị đó.
2. Nếu không có, dùng environment variable `APP_LOG_LEVEL` khác rỗng.
3. Nếu cả hai không có, mặc định `INFO`.

Để minh họa chính xác, chương trình chấp nhận bốn giá trị JUL: `FINE`, `INFO`, `WARNING`, `SEVERE`. Nếu giá trị khác, nó báo lỗi cấu hình thay vì âm thầm đoán level. Các giá trị `DEBUG` và `ERROR` thường thấy trong Logback/Log4j 2 **không được dùng trực tiếp trong ví dụ JUL này**.

Tạo tệp `EnvLoggingDemo.java`:

~~~java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class EnvLoggingDemo {
    private static Level configuredLevel() {
        String value = System.getProperty("app.log.level");
        if (value == null || value.isBlank()) {
            value = System.getenv("APP_LOG_LEVEL");
        }
        if (value == null || value.isBlank()) {
            value = "INFO";
        }

        return switch (value.trim().toUpperCase(Locale.ROOT)) {
            case "FINE" -> Level.FINE;
            case "INFO" -> Level.INFO;
            case "WARNING" -> Level.WARNING;
            case "SEVERE" -> Level.SEVERE;
            default -> throw new IllegalArgumentException(
                    "Unsupported log level: " + value);
        };
    }

    public static void main(String[] args) {
        Level level = configuredLevel();
        Logger logger = Logger.getLogger("demo.env");

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        logger.setUseParentHandlers(false);
        logger.setLevel(level);
        logger.addHandler(handler);

        try {
            System.out.println("effectiveLevel=" + level.getName());

            logger.fine("loading configuration");
            logger.info("service started");
            logger.warning("retry scheduled");
        } finally {
            handler.flush();
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

**Giải thích:**

- `configuredLevel()` đọc hai nguồn theo quy tắc do **ứng dụng tự đặt**. Đây không phải thứ tự ưu tiên chung cho mọi framework.
- `isBlank()` xử lý giá trị chỉ gồm khoảng trắng; `trim().toUpperCase(Locale.ROOT)` chuẩn hóa giá trị nhập.
- `switch` trả về đối tượng `java.util.logging.Level`. Dùng tập giá trị hạn chế giúp cấu hình sai được phát hiện rõ.
- `logger.setLevel(level)` quyết định mức tối thiểu của **logger nguồn**; `handler.setLevel(Level.ALL)` bảo đảm handler không lọc thêm các sự kiện được logger cho phép.
- `setUseParentHandlers(false)` tránh một event bị ghi thêm qua handler gắn trên logger cha trong ví dụ.
- `Formatter` in đúng `LEVEL: message`; `ConsoleHandler` của JUL xuất ra **stderr**. Dòng `effectiveLevel` in ra **stdout**.
- Khi kết thúc, handler được flush, gỡ ra khỏi logger và đóng. Đây là một chương trình demo độc lập; ứng dụng server thực tế thường để logging framework quản lý vòng đời handler.

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac EnvLoggingDemo.java
~~~

Nếu **không có** `APP_LOG_LEVEL` và `app.log.level`, chạy:

~~~bash
java EnvLoggingDemo
~~~

Stdout:

~~~text
effectiveLevel=INFO
~~~

Stderr:

~~~text
INFO: service started
WARNING: retry scheduled
~~~

Dòng `FINE` không xuất hiện vì logger đang ở mức `INFO`. Hai luồng stdout và stderr có thể được hệ điều hành hoặc terminal gộp theo thứ tự hiển thị khác nhau; ở đây chúng được trình bày **riêng từng luồng** để kết quả kiểm chứng rõ ràng.

## 4. Thiết lập biến môi trường trước khi khởi động Java

### 4.1. Linux/macOS: shell Bash hoặc tương tự

~~~bash
export APP_LOG_LEVEL=FINE
java EnvLoggingDemo
~~~

Stdout:

~~~text
effectiveLevel=FINE
~~~

Stderr:

~~~text
FINE: loading configuration
INFO: service started
WARNING: retry scheduled
~~~

Bạn cũng có thể chỉ đặt biến cho **một lần gọi tiến trình**:

~~~bash
APP_LOG_LEVEL=WARNING java EnvLoggingDemo
~~~

Khi đó stdout là `effectiveLevel=WARNING`, còn stderr chỉ có `WARNING: retry scheduled`. Lệnh gán biến đặt ngay trước `java` theo cú pháp shell này không tự thay đổi môi trường của các tiến trình khác.

Để bỏ biến đã `export` trong shell hiện tại, dùng `unset APP_LOG_LEVEL`.

### 4.2. Windows PowerShell

~~~powershell
$env:APP_LOG_LEVEL = "FINE"
java EnvLoggingDemo
~~~

Kết quả stdout/stderr giống trường hợp `FINE` ở mục 4.1. Khi không còn cần giá trị này trong phiên PowerShell hiện tại:

~~~powershell
Remove-Item Env:APP_LOG_LEVEL
~~~

Trong Windows CMD, cú pháp khác:

~~~bat
set APP_LOG_LEVEL=FINE
java EnvLoggingDemo
~~~

**Không dùng** `export APP_LOG_LEVEL=FINE` trong PowerShell hoặc CMD; cũng không dùng lệnh `set APP_LOG_LEVEL=FINE` của CMD để thay thế cú pháp shell Bash. Trên Windows, `setx` thiết lập môi trường cho **các tiến trình được mở về sau**, không cập nhật ngay môi trường của shell đang chạy.

### 4.3. JVM property `-D` và thứ tự ưu tiên trong ví dụ

Giả sử `APP_LOG_LEVEL=FINE` đã được đặt. Chạy:

~~~bash
java -Dapp.log.level=WARNING EnvLoggingDemo
~~~

Trong ví dụ, stdout là:

~~~text
effectiveLevel=WARNING
~~~

Stderr:

~~~text
WARNING: retry scheduled
~~~

JVM property thắng vì code kiểm tra `System.getProperty("app.log.level")` trước `System.getenv("APP_LOG_LEVEL")`. Nếu thiết kế ứng dụng chọn ưu tiên khác, kết quả sẽ khác. Đặt `-Dapp.log.level=WARNING` **trước tên lớp main**; khi đặt sau `EnvLoggingDemo`, chuỗi đó trở thành đối số dòng lệnh của `main` và không còn là JVM option.

**Câu hỏi tự kiểm tra:** Nếu `APP_LOG_LEVEL=FINE` nhưng `-Dapp.log.level=INFO` được truyền, `FINE` có in không? Không. Code lấy `INFO` từ system property, bỏ qua biến môi trường trong trường hợp này.

## 5. Biến môi trường và `logging.properties` của JUL

JUL có cơ chế chọn file cấu hình bằng **JVM system property** chuẩn:

~~~bash
java -Djava.util.logging.config.file=config/logging.properties MyApplication
~~~

Điều này khác hoàn toàn với việc đặt:

~~~text
JAVA_UTIL_LOGGING_CONFIG_FILE=config/logging.properties
~~~

Biến môi trường có tên tùy ý ở dòng thứ hai **không tự được JUL nhận diện** như một cờ chọn file. Nếu muốn chọn đường dẫn qua biến môi trường, **script khởi chạy** có thể chuyển giá trị sang JVM option:

~~~bash
export APP_JUL_CONFIG=config/logging.properties
java "-Djava.util.logging.config.file=$APP_JUL_CONFIG" MyApplication
~~~

Ví dụ này chỉ có thể chạy khi đã có `MyApplication` và file `config/logging.properties` hợp lệ. Đối với Windows PowerShell, cú pháp truyền tương đương là:

~~~powershell
$env:APP_JUL_CONFIG = "C:/app/config/logging.properties"
java "-Djava.util.logging.config.file=$env:APP_JUL_CONFIG" MyApplication
~~~

Cơ chế hoạt động:

~~~text
APP_JUL_CONFIG (bien moi truong)
             |
             v
Script khoi dong doc gia tri
             |
             v
-Djava.util.logging.config.file=<duong-dan>
             |
             v
JUL LogManager nap logging.properties
             |
             v
Logger/Handler/Formatter duoc cau hinh
~~~

Trong `logging.properties`, có thể đặt mức cho logger và handler như:

~~~properties
.level = INFO
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = FINE
demo.env.level = FINE
~~~

**Lưu ý:** khi chương trình tự tạo handler, tự đổi level hoặc vô hiệu hóa parent handler (như `EnvLoggingDemo`), các lệnh cấu hình trong code sẽ ảnh hưởng đến kết quả cuối cùng. Vì thế không nên dùng chính chương trình demo để suy luận rằng mọi thiết lập từ file luôn thắng cấu hình trong code. Với sản phẩm thực tế, nên có **một chủ thể quản lý cấu hình** rõ ràng để tránh nhiều nơi ghi đè lẫn nhau.

## 6. Logback, Log4j 2 và Spring Boot đọc biến môi trường ra sao?

Mỗi logging backend có cú pháp và cơ chế riêng. Biến môi trường **chỉ có tác dụng nếu backend hoặc framework đọc nó**.

### 6.1. Logback (thường đi cùng SLF4J)

Ví dụ cấu hình `logback.xml` với root level lấy từ `APP_LOG_LEVEL` và mặc định `INFO`:

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="${APP_LOG_LEVEL:-INFO}">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Trong cấu hình Logback, cú pháp thay thế thuộc tính `${APP_LOG_LEVEL:-INFO}` yêu cầu Logback có thể tìm giá trị trong các nguồn thuộc tính mà nó hỗ trợ, trong đó có biến môi trường của tiến trình. Với Logback, giá trị level là `DEBUG`, `INFO`, `WARN`, `ERROR`, `TRACE`... chứ không tương ứng một-một với level của JUL. Nếu `APP_LOG_LEVEL=DEBUG`, root logger có thể cho phép log debug khi runtime thực sự dùng Logback và nạp đúng `logback.xml`.

Đặt `logback.xml` trên classpath (thường `src/main/resources` trong dự án Maven/Gradle) hoặc cấu hình một vị trí file ngoài theo cơ chế backend. **SLF4J là API**, nên chỉ thêm dependency `slf4j-api` không bảo đảm có Logback: cần có provider/backend phù hợp.

### 6.2. Log4j 2

Trong `log4j2.xml`, Log4j 2 hỗ trợ lookup dành cho môi trường thông qua tiền tố `env:`. Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%p %c - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="${env:APP_LOG_LEVEL:-info}">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Cú pháp `${env:APP_LOG_LEVEL:-info}` dùng environment lookup và giá trị mặc định `info` khi không có biến. Ví dụ này chỉ có tác dụng với chương trình chạy Log4j 2 đúng phiên bản/cấu hình hỗ trợ các lookup đó. Đừng dùng `log4j2.xml` để cấu hình Logback hoặc JUL.

### 6.3. Spring Boot

Spring Boot có cơ chế externalized configuration: thuộc tính `logging.level.root` có thể được cung cấp qua biến môi trường theo quy tắc chuyển tên thuộc tính, chẳng hạn:

~~~bash
LOGGING_LEVEL_ROOT=DEBUG java -jar app.jar
~~~

Với PowerShell:

~~~powershell
$env:LOGGING_LEVEL_ROOT = "DEBUG"
java -jar app.jar
~~~

Nếu ứng dụng Spring Boot có logging system phù hợp và không có nguồn cấu hình ưu tiên cao hơn ghi đè, biến `LOGGING_LEVEL_ROOT` sẽ tác động đến root log level. Trong `application.properties`, giá trị tương đương về mặt tên thuộc tính là:

~~~properties
logging.level.root=DEBUG
~~~

**Chú ý:** Spring Boot có nhiều nguồn thuộc tính như command-line arguments, system properties, environment variables và config files; **thứ tự ưu tiên do Spring Boot quy định**. Không được mặc định rằng ưu tiên `-D` trước môi trường giống chương trình `EnvLoggingDemo`. Các mức log của Boot thường theo backend đã cấu hình, và không phải lúc nào cũng là tên mức JUL.

Nếu cấu hình theo tên logger/class cụ thể có chữ hoa, tên biến môi trường có thể bị quy tắc binding chuẩn hóa thành chữ thường; trong một số trường hợp cần dùng cấu hình khác (ví dụ `SPRING_APPLICATION_JSON`) để giữ chính xác tên logger. Còn `LOGGING_LEVEL_ROOT` là trường hợp đơn giản, dễ kiểm tra.

## 7. Triển khai theo môi trường: terminal, IDE, Docker và dịch vụ

**Terminal/IDE.** Biến môi trường phải được truyền cho đúng tiến trình Java. IDE thường có phần “Environment variables” trong cấu hình chạy. Nếu biến đã đặt trong một terminal nhưng ứng dụng chạy bằng IDE mở trước đó, không thể mặc định IDE sẽ thừa hưởng giá trị mới. Kiểm tra trực tiếp môi trường của tiến trình mà IDE/service đã khởi chạy.

**Docker.** Với một image chứa ứng dụng có hỗ trợ `APP_LOG_LEVEL`:

~~~bash
docker run --rm -e APP_LOG_LEVEL=INFO my-app-image
~~~

Lệnh minh họa giả định image `my-app-image` đã tồn tại. Docker chỉ cung cấp biến cho tiến trình bên trong container; ứng dụng vẫn phải đọc biến hoặc logging backend phải được cấu hình để đọc. Nếu dùng Docker Compose, có thể truyền như sau:

~~~yaml
services:
  app:
    image: my-app-image
    environment:
      APP_LOG_LEVEL: INFO
~~~

File YAML là **đoạn cấu hình tích hợp**, không phải ứng dụng độc lập. Khi đổi giá trị, có thể cần tạo lại container hoặc khởi động lại ứng dụng tùy mô hình triển khai. Không kỳ vọng một thay đổi trên shell host lập tức được truyền vào tiến trình Java đã chạy trong container.

**Máy chủ/CI/Kubernetes.** Mỗi nền tảng có cách gán biến trước lúc chạy (service manager, pipeline config, Deployment, ConfigMap...). Nguyên tắc chung là xác định **nguồn giá trị được triển khai**, **tiến trình nhận giá trị** và **thời điểm nó được khởi động lại**. Chỉ sửa file hoặc biến trên host chưa đủ để kết luận Java đã nạp thay đổi.

**Một số thiết kế cấu hình nên nhất quán:**

- Dùng tên dễ hiểu và có namespace (`APP_LOG_LEVEL`, `APP_LOG_FORMAT`) để tránh trùng tên giữa các thành phần.
- Chỉ cho phép các level hợp lệ của backend đang dùng; ghi thông báo lỗi rõ khi giá trị sai.
- Quy định giá trị mặc định bảo thủ (ví dụ `INFO`) và tài liệu hóa thứ tự ưu tiên.
- Ở production, cân nhắc stdout/stderr cùng hệ thống thu thập log; định dạng và nơi xuất phụ thuộc yêu cầu vận hành.
- Đừng dùng biến môi trường để lưu một mã **request ID/trace ID duy nhất** cho tất cả request. ID tương quan của từng yêu cầu thuộc request context/MDC/tracing, không phải cấu hình toàn tiến trình.

## 8. Bảo mật, hiệu năng và giới hạn của cấu hình qua môi trường

**Cấu hình level cũng có tác động bảo mật.** `DEBUG`/`TRACE` hoặc `FINE` có thể vô tình in payload, đường dẫn, dữ liệu người dùng hoặc thông tin hệ thống. Khi bật log chi tiết để điều tra sự cố, cần giới hạn phạm vi, xác định thời điểm tắt và kiểm tra cơ chế che thông tin nhạy cảm.

Không ghi mật khẩu, token hoặc secret vào giá trị log chỉ để xác minh biến môi trường. Một số nền tảng có thể hiển thị environment variables trong giao diện quản trị, công cụ chẩn đoán, crash dump hoặc qua người có quyền truy cập hệ thống. Dù level không phải secret, hãy tránh đưa bí mật vào cấu hình logging hay log output.

**Hiệu năng:** biến môi trường không làm logging miễn phí. Khi bật mức chi tiết, số sự kiện được tạo và chi phí định dạng, I/O, mạng, bộ đệm đều có thể tăng đáng kể. Với async logging, còn phải xem queue có bị đầy, bị block hoặc discard hay không. Trong đường đi nóng, nên đọc cấu hình **một lần lúc khởi tạo hoặc qua cơ chế quản lý config phù hợp**, thay vì đọc `System.getenv()` cho mỗi log event.

**Thay đổi runtime:** system property có thể được chỉnh trong JVM bằng API, nhưng logger/backend có thể đã đọc và lưu cấu hình lúc khởi tạo. Thay đổi thuộc tính **không bảo đảm** hệ thống logging tự reload. Cần xác nhận khả năng reconfiguration của hệ logging đang sử dụng, và có kế hoạch rollback khi thay đổi mức log hoặc nơi xuất.

## 9. Bảng khắc phục sự cố

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `APP_LOG_LEVEL` đã đặt nhưng log không đổi | Ứng dụng/backend không hề đọc biến đó | Kiểm tra code `System.getenv`, XML lookup, Spring property mapping |
| Terminal có biến nhưng Java đọc `null` | Đặt biến ở phiên khác hoặc sau khi tiến trình khởi động | Đặt biến ở đúng parent process, khởi động lại |
| `APP_LOG_LEVEL=DEBUG` bị báo sai | JUL dùng `FINE` thay cho `DEBUG` trong ví dụ Java thuần | Dùng giá trị hợp lệ của backend hoặc viết lớp ánh xạ rõ ràng |
| Truyền `-D...` không có tác dụng | Cờ đặt sau tên main/JAR, dùng sai key hoặc code không đọc key đó | Đặt `-D` trước class/`-jar`, xác minh key |
| Log `FINE` vẫn không xuất hiện | Handler đã chặn, hoặc logger hiệu lực không ở mức `FINE` | Kiểm tra cả logger level và handler/appender/filter |
| Đặt `LOGGING_LEVEL_ROOT` nhưng không đổi | Không chạy Spring Boot, có nguồn cấu hình khác ưu tiên cao hơn, hoặc backend khác dự kiến | Xác nhận framework và nguồn config cuối cùng |
| Chạy Docker nhưng log không theo cấu hình | Biến chưa truyền đúng cho container, container chưa được tạo lại | Kiểm tra cấu hình triển khai và restart/recreate khi cần |
| Đổi biến ở máy chủ nhưng dịch vụ vẫn log như cũ | Tiến trình đang chạy với môi trường cũ hoặc backend không reload | Áp dụng thay đổi qua cơ chế hỗ trợ và xác minh restart |
| Log quá nhiều hoặc chứa dữ liệu nhạy cảm | Bật level quá chi tiết trên production | Giảm level, lọc/redact dữ liệu, giới hạn thời gian bật |
| Dòng log không chứa request/trace ID | Chưa cấu hình MDC/tracing propagation | Thiết lập context theo request, không dùng biến toàn tiến trình |

## 10. Bài tập tự kiểm tra

1. **Không có biến hoặc property:** `java EnvLoggingDemo` dùng level nào? → `INFO`, in hai log `INFO` và `WARNING` vào stderr.
2. **Có `APP_LOG_LEVEL=FINE`:** Log nào được in? → `FINE`, `INFO`, `WARNING`; stdout ghi `effectiveLevel=FINE`.
3. **Có cả environment `FINE` và JVM property `WARNING`:** Giá trị nào thắng? → `WARNING`, vì code chủ động ưu tiên `System.getProperty`.
4. **Truyền `APP_LOG_LEVEL=DEBUG` vào chương trình JUL ví dụ:** Kết quả? → Phát sinh `IllegalArgumentException` trước khi tạo log vì `DEBUG` nằm ngoài danh sách cho phép.
5. **Chỉ đặt `APP_JUL_CONFIG` mà không chuyển sang JVM `-Djava.util.logging.config.file`:** JUL có tự nạp file đó không? → Không, nếu không có script/code hỗ trợ.
6. **Đổi biến trong terminal khi JVM vẫn chạy:** Mọi log về sau có tự đổi level? → Không thể giả định. Cần cơ chế reload hoặc khởi động lại phù hợp.

**Ghi nhớ:** Biến môi trường là kênh đưa cấu hình vào tiến trình, còn logger/framework quyết định cách sử dụng. Để điều khiển Java logging an toàn theo môi trường, hãy xác định backend thực tế, tên biến được hỗ trợ, thứ tự ưu tiên, level hợp lệ và thời điểm nạp lại cấu hình.