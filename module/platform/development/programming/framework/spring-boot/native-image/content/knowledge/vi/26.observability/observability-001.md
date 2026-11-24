# Logging và các thành phần cấu hình hoặc layout được nạp động

Spring Boot khởi tạo hệ thống logging rất sớm, trước khi ApplicationContext được tạo. Cấu hình có thể đến từ file trong classpath, file ngoài được chỉ định bằng `logging.config`, hoặc các property như `logging.level.*` và `logging.file.name`. Logback và Log4j2 còn cho phép file cấu hình tham chiếu appender, encoder, layout, converter, filter hoặc plugin bằng tên class.

Với GraalVM Native Image, cần phân biệt hai việc:

- **Nạp cấu hình lúc runtime:** process đọc file XML/properties/YAML ngoài để chọn log level, pattern, appender hoặc file output. Việc này có thể thực hiện nếu file và component cần dùng có sẵn khi process chạy.
- **Nạp code component động:** cấu hình yêu cầu tạo appender, layout, encoder hoặc converter theo tên class. Class đó phải nằm trong tập code được đưa vào native image và các constructor/member được truy cập động phải có metadata phù hợp.

File cấu hình ngoài có thể thay đổi sau phát hành, nhưng không thể thêm bytecode của class mới vào executable đã biên dịch. Reflection hints cũng chỉ mô tả cách truy cập class đã có; chúng không đưa dependency mới vào image.

Bài học thuộc chương **Quan sát** của mô-đun `SPRING_BOOT_NATIVE_IMAGE`. Ta sẽ tìm hiểu thời điểm logging được khởi tạo, cách chọn file cấu hình, cách dùng Logback/Log4j2, các thành phần có thể được cấu hình động, Runtime Hints cần thiết và cách kiểm tra logging trong native executable.

## 1. Logging được khởi tạo trước ApplicationContext

Spring Boot dùng abstraction `LoggingSystem` để chọn và cấu hình logging backend dựa trên classpath. Khi dùng starter thông thường, Logback thường là lựa chọn mặc định. Log4j2 hoặc Java Util Logging có thể được dùng nếu dependency và cấu hình tương ứng có mặt.

Logging được chuẩn bị rất sớm, trước khi ApplicationContext hoàn tất. Vì vậy, không thể dựa vào `@PropertySource` trong một class `@Configuration` để chọn logging system hoặc cung cấp mọi property cần thiết cho bước khởi tạo ban đầu.

Các nguồn cấu hình sớm thường dùng:

- Environment variables, ví dụ `LOGGING_CONFIG` hoặc `LOGGING_LEVEL_COM_EXAMPLE_ORDERS`.
- Java system properties, ví dụ `-Dlogging.config=...`.
- Command-line properties được Spring Boot nhận trong quá trình khởi động.
- File cấu hình ở vị trí chuẩn hoặc vị trí được chỉ định rõ.

| Nhu cầu | Property thường dùng |
| --- | --- |
| Đổi log level của package | `logging.level.com.example.orders=DEBUG` |
| Chọn file logging config | `logging.config=file:/etc/orders/logback-spring.xml` |
| Ghi log ra file | `logging.file.name=/var/log/orders/orders.log` |
| Chọn log level mặc định | `logging.level.root=INFO` |
| Đặt tên ứng dụng | `spring.application.name=orders-service` |

Với native image, các property này vẫn có thể được cung cấp khi process khởi động. Tuy nhiên, nếu file logging tham chiếu class tùy biến, class đó và metadata cần thiết phải được xử lý trong build.

## 2. Phân biệt file cấu hình, resource và code component

Một file logging XML có thể chứa nhiều loại thông tin:

1. **Giá trị cấu hình:** log level, pattern, file path, rolling policy, timeout hoặc endpoint.
2. **Tham chiếu resource:** file include, properties file hoặc file phụ trợ.
3. **Tham chiếu class:** custom appender, encoder, layout, converter, filter hoặc plugin.
4. **Cơ chế reload:** theo dõi file và đọc lại cấu hình khi nội dung thay đổi.

Các nhóm này có yêu cầu native khác nhau:

| Thành phần | Ví dụ | Cần xử lý trong native image |
| --- | --- | --- |
| Property | `logging.level.root=DEBUG` | Cung cấp trước/lúc khởi động hoặc qua cơ chế quản lý logger |
| File cấu hình classpath | `logback-spring.xml` | Bảo đảm resource được đóng gói nếu runtime cần đọc |
| File cấu hình ngoài | `/etc/orders/logback-spring.xml` | Mount file và cấp quyền đọc ở runtime |
| Custom appender | `com.example.logging.AuditAppender` | Class phải có trong image; thêm reflection hints nếu cần |
| Custom converter/layout | Class được nêu trong XML | Class và constructor/member cần thiết phải được giữ |
| File include | `logging/includes/console.xml` | Bảo đảm resource có trong image hoặc file ngoài tồn tại |
| Reload file | Logback scan hoặc backend-specific reconfiguration | Chỉ thay đổi cấu hình của component đã có; phải kiểm tra theo backend/version |

Một native executable có thể đọc file ngoài, nhưng classpath của executable đã cố định ở build time. Đây là ranh giới cần giữ rõ trong thiết kế logging.

## 3. Chọn logging config bằng logging.config

Spring Boot tự tìm cấu hình logging theo quy ước của backend. Có thể chỉ định vị trí khác bằng property `logging.config`.

Ví dụ với file ngoài:

```bash
LOGGING_CONFIG=file:/etc/orders/logback-spring.xml ./orders-service
```

Trong môi trường container, file cấu hình có thể được mount từ ConfigMap, volume hoặc deployment artifact riêng. Process cần quyền đọc file và mọi file include mà cấu hình tham chiếu.

```dockerfile
FROM debian:bookworm-slim
WORKDIR /app

COPY orders-service /app/orders-service
ENV LOGGING_CONFIG=file:/etc/orders/logback-spring.xml

ENTRYPOINT ["/app/orders-service"]
```

Có thể mount file khi chạy:

```bash
docker run --rm \
  -v ./logging:/etc/orders:ro \
  -e LOGGING_CONFIG=file:/etc/orders/logback-spring.xml \
  orders-service:native
```

Không đặt kỳ vọng rằng một bean hoặc `@PropertySource` sẽ cung cấp `logging.config` đủ sớm. Hãy dùng nguồn cấu hình có sẵn ngay khi process bắt đầu.

## 4. Dùng logback-spring.xml với Spring Boot

Nếu backend là Logback và cần Spring Boot extensions, dùng `logback-spring.xml`. File chuẩn `logback.xml` được Logback tự đọc quá sớm nên Spring Boot không thể áp dụng đầy đủ các extension của mình.

Ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration scan="false">
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

    <springProperty scope="context"
                    name="applicationName"
                    source="spring.application.name"
                    defaultValue="orders-service"/>

    <springProfile name="dev">
        <logger name="com.example.orders" level="DEBUG"/>
    </springProfile>

    <springProfile name="prod">
        <logger name="com.example.orders" level="INFO"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Ví dụ dùng `<springProperty>` để lấy property từ Spring Environment và `<springProfile>` để áp dụng cấu hình theo profile.

Đặt `scan="false"` khi dùng Spring Boot Logback extensions. Tài liệu Spring Boot nêu rõ các extension này không tương thích với Logback configuration scanning: khi Logback tự đọc lại file, nó không có Spring extension actions và có thể báo lỗi với `springProperty` hoặc `springProfile`.

Profile dùng trong logging phải phù hợp với profile được cung cấp khi khởi động native process. AOT không làm file logging trở thành nơi có thể thêm bean hoặc class mới.

## 5. Đổi log level mà không cần custom layout

Nếu nhu cầu chỉ là đổi mức log hoặc bật/tắt log cho package, không cần tạo custom appender/layout. Dùng property chuẩn:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
```

Có thể override bằng environment variable:

```bash
LOGGING_LEVEL_ROOT=INFO
LOGGING_LEVEL_COM_EXAMPLE_ORDERS=DEBUG
./orders-service
```

Spring Boot cũng hỗ trợ `--debug` và `--trace` cho một số nhóm logger cốt lõi. Chúng không đồng nghĩa bật DEBUG/TRACE cho mọi logger trong ứng dụng.

Với Spring Boot Actuator, endpoint `/actuator/loggers` có thể xem và thay đổi log level lúc runtime. Ví dụ:

```http
POST /actuator/loggers/com.example.orders
Content-Type: application/json

{
  "configuredLevel": "DEBUG"
}
```

Đây là thay đổi trạng thái logger trong process đang chạy, không phải tải một class layout mới. Chỉ expose endpoint quản trị trên network tin cậy, áp dụng authentication/authorization phù hợp và tránh công khai endpoint này không kiểm soát.

Khi process restart, log level trở lại theo cấu hình startup trừ khi hệ thống quản lý cấu hình cấp lại giá trị mới.

## 6. Thành phần nào được nạp động từ logging configuration?

Các logging backend thường cho phép cấu hình tham chiếu class theo tên:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Appender | Gửi log đến console, file, socket hoặc hệ thống ngoài | `AuditAppender` |
| Encoder | Chuyển logging event thành bytes/text | `PatternLayoutEncoder` |
| Layout | Định dạng event thành chuỗi hoặc cấu trúc | `JsonLayout` |
| Converter | Chuyển token pattern thành giá trị | Custom Logback converter |
| Filter | Quyết định event có được chấp nhận | Custom threshold/tenant filter |
| Plugin | Thành phần mở rộng theo cơ chế backend | Log4j2 plugin |
| Configurator/Provider | Tham gia khởi tạo backend | Logback Configurator qua service provider |

Ví dụ Logback XML tham chiếu custom appender:

```xml
<appender name="AUDIT"
          class="com.example.logging.AuditAppender">
    <destination>/var/log/orders/audit.log</destination>
</appender>
```

Backend phải tạo instance của class và cấu hình property tương ứng. Quá trình này có thể dựa vào reflection hoặc cơ chế discovery riêng. Native Image không thể mặc nhiên suy ra mọi class chỉ xuất hiện trong XML string.

Để dùng component tùy biến trong native image, cần kiểm tra:

1. Class có nằm trong source/dependency của build không?
2. Class có được giữ trong native executable không?
3. Logging framework khởi tạo class bằng reflection, service loading hay plugin registry?
4. Constructor, setter hoặc member nào được truy cập động?
5. Dependency đã cung cấp reachability metadata chưa?
6. Nếu chưa, ứng dụng có cần khai báo Runtime Hints không?

## 7. Ví dụ custom Logback appender

Giả sử ứng dụng có appender ghi audit event ra file riêng. Đây là ví dụ rút gọn để minh họa class được XML tham chiếu:

```java
package com.example.logging;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;

public class AuditAppender extends AppenderBase<ILoggingEvent> {

    private String destination;

    public void setDestination(String destination) {
        this.destination = destination;
    }

    @Override
    protected void append(ILoggingEvent event) {
        if (destination == null || destination.isBlank()) {
            addError("Audit destination is not configured");
            return;
        }

        try {
            Path path = Path.of(destination);
            Path parent = path.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            Files.writeString(
                    path,
                    event.getFormattedMessage() + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        }
        catch (IOException ex) {
            addError("Cannot write audit event", ex);
        }
    }
}
```

Trong ứng dụng thực tế, appender cần xử lý lifecycle, buffering, concurrency, backpressure, lỗi I/O và dữ liệu nhạy cảm. Ví dụ trên chỉ làm rõ class và setter mà Logback có thể tạo/cấu hình từ XML.

Cấu hình:

```xml
<appender name="AUDIT"
          class="com.example.logging.AuditAppender">
    <destination>/var/log/orders/audit.log</destination>
</appender>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="AUDIT"/>
</root>
```

Class `AuditAppender` phải nằm trong dependency graph trước khi native image được tạo. Việc thay file XML sau phát hành để trỏ sang `com.vendor.NewAppender` không thể làm class đó xuất hiện trong executable nếu nó chưa được build cùng ứng dụng.

## 8. Bổ sung Runtime Hints cho custom logging component

Nếu Logback khởi tạo appender qua reflection và Spring AOT/dependency metadata chưa mô tả constructor hoặc setter cần dùng, ứng dụng có thể đăng ký hints.

```java
package com.example.logging;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class LoggingRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                AuditAppender.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Gắn registrar vào AOT configuration:

```java
package com.example.logging;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(LoggingRuntimeHints.class)
public class LoggingNativeConfiguration {
}
```

Ví dụ đăng ký constructor và public methods vì Logback cần tạo appender và gọi setter `setDestination`. Hãy chọn category theo cách backend thực sự truy cập class. Không đăng ký toàn bộ member của mọi logging class theo thói quen.

Nếu dependency đã đóng gói metadata native cho component đó, không cần sao chép hint vào ứng dụng. Nếu class được nêu trong XML nhưng không được tham chiếu trực tiếp ở nơi khác, việc có hint vẫn cần được xác minh bằng native build và test. Hint không thể thay thế dependency hoặc đưa class không có trong build vào executable.

## 9. File cấu hình classpath và file cấu hình ngoài

Có hai cách cung cấp cấu hình:

| Nguồn | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Classpath resource | `src/main/resources/logback-spring.xml` | Được đóng gói trong artifact; sửa file thường cần build lại |
| External file | `/etc/orders/logback-spring.xml` | Có thể mount/thay đổi độc lập với native executable |
| External include | `/etc/orders/includes/audit.xml` | Phải tồn tại và có quyền đọc ở runtime |
| External properties | `/etc/orders/logging.properties` | Có thể được backend hỗ trợ theo format/cơ chế tương ứng |

Nếu file classpath được logging backend đọc bằng tên resource động, hãy xác minh resource đã được đưa vào native image. Spring AOT có thể tự suy ra một số resource từ integration mà framework nhận biết, nhưng không nên giả định mọi file được đọc bởi thư viện bên thứ ba đều được phát hiện.

Nếu thiếu resource hint, có thể khai báo:

```java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

class LoggingResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("logback-spring.xml");
        hints.resources().registerPattern("logging/includes/audit.xml");
    }
}
```

Chỉ đăng ký resource classpath thật sự được dùng. Với file ngoài như `/etc/orders/logback-spring.xml`, file không cần được nhúng vào executable; nó cần có mặt trong filesystem của container/máy chạy và process đọc được.

Không đưa file cấu hình chứa credential, token hoặc endpoint nội bộ nhạy cảm vào image layer nếu không cần thiết. Cấp giá trị nhạy cảm qua secret/config mechanism ở runtime.

## 10. Tham chiếu property trong Logback configuration

Spring Boot chuyển một số property logging sang system properties để backend có thể sử dụng. Ví dụ `logging.file.name` có thể cung cấp `LOG_FILE`; `logging.pattern.console` cung cấp `CONSOLE_LOG_PATTERN`.

Một cấu hình có thể dùng các property này:

```xml
<configuration scan="false">
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

    <property name="AUDIT_LOG" value="${LOG_PATH:-/var/log/orders}/audit.log"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Cần chú ý cú pháp placeholder. Trong Logback XML, cú pháp mặc định của Logback thường dùng `:-`. Khi dùng placeholder trong property do Spring Boot xử lý, hãy dùng cú pháp Spring Boot tương ứng và không trộn lẫn tùy tiện. Đọc tài liệu backend cho từng loại property.

Một số property Spring Boot chuyển sang system properties:

| Spring Environment property | System property thường dùng |
| --- | --- |
| `logging.file.name` | `LOG_FILE` |
| `logging.file.path` | `LOG_PATH` |
| `logging.pattern.console` | `CONSOLE_LOG_PATTERN` |
| `logging.pattern.file` | `FILE_LOG_PATTERN` |
| `logging.charset.console` | `CONSOLE_LOG_CHARSET` |
| `logging.pattern.level` | `LOG_LEVEL_PATTERN` |

Các property này giúp thay đổi giá trị runtime mà không phải thay class encoder/layout. Nếu chỉ cần thay pattern hoặc đường dẫn file, ưu tiên property đã được hỗ trợ trước khi tạo custom component.

## 11. Dynamic reload với Logback scan

Logback hỗ trợ theo dõi file cấu hình và đọc lại khi file thay đổi thông qua thuộc tính `scan`:

```xml
<configuration scan="true" scanPeriod="30 seconds">
    <!-- appender và logger configuration -->
</configuration>
```

Cơ chế này có thể hữu ích khi ứng dụng chạy JVM và cần reload cấu hình ngoài. Tuy nhiên, có các giới hạn quan trọng:

- Spring Boot extensions như `<springProfile>` và `<springProperty>` không tương thích với Logback configuration scanning.
- Khi Logback tự parse lại file, quá trình reload không nhất thiết đi qua Spring Boot logging extensions.
- Reload có thể thay đổi mức log, appender hoặc pattern đã có; nó không thêm bytecode class mới vào native executable.
- File classpath nằm trong executable không phải file mutable bên ngoài mà operator có thể sửa trực tiếp.
- Custom component được cấu hình lại vẫn phải có class và metadata cần thiết trong binary.

Với `logback-spring.xml` dùng Spring extensions, giữ `scan="false"`. Nếu cần reload cấu hình, kiểm tra cơ chế của backend và version cụ thể bằng native executable thực tế; không suy luận rằng hành vi JVM sẽ giống hệt native.

Nếu mục tiêu chỉ là đổi log level, Actuator Loggers endpoint hoặc property cấp lại khi restart thường dễ kiểm soát hơn việc reload toàn bộ XML.

## 12. Log4j2 và plugin configuration

Nếu ứng dụng dùng Log4j2, Spring Boot hỗ trợ file `log4j2-spring.xml` để sử dụng các extension như profile và lookup từ Spring Environment. File `log4j2.xml` chuẩn được Log4j2 đọc quá sớm để Spring Boot áp dụng đầy đủ extension.

Log4j2 có cơ chế plugin riêng. Plugin thường được phát hiện qua metadata do annotation processor/plugin tooling tạo, chẳng hạn plugin cache trong JAR. Khi dùng custom appender, layout hoặc filter của Log4j2, cần:

1. Đảm bảo plugin được compile/đóng gói đúng cách.
2. Đảm bảo plugin metadata được tạo và nằm trong dependency/artifact.
3. Kiểm tra reachability metadata hoặc hints cần thiết cho native image.
4. Build và chạy native test với đúng plugin configuration.
5. Kiểm tra dependency bắc cầu của appender/layout có trong runtime image.

Không áp dụng Runtime Hints của Logback một cách máy móc cho Log4j2. Hai backend có cơ chế discovery, plugin registry và khởi tạo component khác nhau. Hãy dùng plugin mechanism và native metadata được hỗ trợ bởi phiên bản Log4j2 đang dùng.

## 13. Custom structured logging formatter

Các phiên bản Spring Boot có structured logging API cho phép chọn format như ECS, GELF hoặc Logstash. Nếu cần format riêng, có thể triển khai `StructuredLogFormatter` phù hợp với backend.

Ví dụ với Logback:

```java
import ch.qos.logback.classic.spi.ILoggingEvent;
import org.springframework.boot.logging.structured.StructuredLogFormatter;

public class AuditJsonFormatter
        implements StructuredLogFormatter<ILoggingEvent> {

    @Override
    public String format(ILoggingEvent event) {
        return "{\"level\":\"" + event.getLevel()
                + "\",\"message\":\""
                + escape(event.getFormattedMessage()) + "\"}";
    }

    private String escape(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"");
    }
}
```

Có thể chọn formatter theo tên class qua property structured logging tương ứng, ví dụ `logging.structured.format.console` hoặc `logging.structured.format.file`. Property có thể nhận identifier format tích hợp hoặc tên class formatter tùy phiên bản Spring Boot.

Vì class tùy biến được chọn bằng tên cấu hình, phải bảo đảm class có trong build và constructor/metadata cần thiết được native image giữ. Nếu formatter có constructor phụ thuộc hoặc cần cấu hình phức tạp, kiểm tra contract instantiation của phiên bản Spring Boot đang dùng thay vì giả định nó được tạo như một Spring bean thông thường.

Structured logging cũng cần kiểm tra escaping, newline, Unicode, exception/stack trace, MDC và dữ liệu nhạy cảm. Ghép JSON bằng chuỗi chỉ là ví dụ tối giản; production nên dùng serializer phù hợp để tránh JSON không hợp lệ.

## 14. Chọn cơ chế theo mức độ thay đổi cần thiết

Không phải mọi yêu cầu "đổi logging runtime" đều cần reload XML hoặc custom layout.

| Nhu cầu vận hành | Cơ chế nên cân nhắc | Có cần rebuild native không? |
| --- | --- | --- |
| Đổi log level root/package | Environment/property lúc startup hoặc Actuator Loggers | Không |
| Đổi file output/path | `logging.file.name` hoặc external config | Không, nếu backend hỗ trợ và đường dẫn hợp lệ |
| Đổi pattern/rolling policy | Property Spring Boot hoặc external config | Không, nếu chỉ thay giá trị và component đã có |
| Chọn appender đã có trong binary | External config nếu backend hỗ trợ | Không |
| Chọn custom appender mới chưa có trong image | Thêm dependency/code rồi build native lại | Có |
| Đổi custom formatter/layout sang class mới | Thêm class và metadata, build lại | Có |
| Cài logging plugin tùy ý sau deploy | Native executable không phải classloader plugin host mặc định | Cần build lại hoặc tách plugin process/service |
| Thay secret/endpoint của appender | Secret/config mount runtime nếu component hỗ trợ | Không, nhưng có thể cần restart/reload |
| Reload XML ngoài | Backend-specific scan/reconfiguration; kiểm tra native behavior | Thường không nếu chỉ dùng component có sẵn |

Quy tắc thực tế: **configuration có thể thay đổi dữ liệu và lựa chọn; code component phải nằm trong tập code đã build**.

## 15. Kiểm thử logging configuration trong native image

Nên kiểm tra theo nhiều tầng:

1. JVM startup test để xác nhận file XML hợp lệ và backend khởi tạo đúng.
2. AOT/native build để phát hiện class/resource động chưa có metadata.
3. Native executable test để xác nhận appender/layout được tạo và ghi log.
4. Runtime configuration test với external config mount nếu production dùng file ngoài.
5. Reload test nếu thật sự bật scanning/reconfiguration.

Một test hành vi có thể xác nhận custom appender ghi được event:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

class AuditLoggingTests {

    @Test
    void writesAuditMessage() {
        Logger logger = LoggerFactory.getLogger("com.example.orders.audit");
        logger.info("invoice-created");

        Path output = Path.of("/tmp/orders-audit.log");
        await().atMost(Duration.ofSeconds(3))
                .untilAsserted(() ->
                        assertThat(Files.readString(output))
                                .contains("invoice-created"));
    }
}
```

Đây là ví dụ minh họa; cần cấu hình appender destination và test dependency tương ứng. Trong CI, dùng thư mục tạm riêng cho mỗi test, dọn file sau khi chạy và tránh phụ thuộc đường dẫn cố định trên máy developer.

Đối với native executable, kiểm tra:

- Process khởi động với file cấu hình đúng.
- Custom appender/layout class được tạo.
- Event được ghi đúng output.
- Log level và pattern theo cấu hình.
- File include/resource được tìm thấy.
- Process chạy dưới UID thực tế của container có quyền ghi.
- External config được đọc đúng.
- Nếu dùng reload, thay đổi được áp dụng mà không tạo lỗi Spring extension.

Không chỉ kiểm tra log "Started" ở console. Một appender tùy biến có thể fail sau đó khi ghi event đầu tiên.

## 16. Điều tra lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Native image không tìm thấy file Logback XML | Resource classpath chưa được đưa vào image hoặc `logging.config` sai | Kiểm tra resource hint, output AOT và đường dẫn runtime |
| External config không được đọc | `LOGGING_CONFIG` chưa có ở thời điểm logging init hoặc file không mount | Cấp biến trước khi process start và kiểm tra quyền đọc |
| `springProperty`/`springProfile` báo lỗi khi reload | Logback scan tự parse lại file mà không có Spring extensions | Tắt `scan` hoặc dùng cơ chế reload phù hợp |
| Custom appender không được tạo | Class không có trong image hoặc thiếu constructor/member metadata | Kiểm tra dependency, Runtime Hints và native stack trace |
| Appender được tạo nhưng setter không chạy | Reflection access cho public methods/property setter chưa đủ hoặc XML property sai | Kiểm tra setter và metadata chính xác |
| Custom converter không được nhận diện | Conversion rule chưa đăng ký hoặc class không có trong binary | Kiểm tra XML, converter class và hints |
| Log4j2 không tìm thấy plugin | Plugin metadata/cache không được tạo hoặc đóng gói | Kiểm tra annotation processor, plugin cache và dependency |
| Log file không được ghi trong container | Directory không tồn tại hoặc UID không có quyền ghi | Tạo/mount directory và cấp permission phù hợp |
| Reload XML không làm thay class | Class mới chưa nằm trong native executable | Build lại với class/dependency mới |
| Actuator không đổi log level | Endpoint chưa expose/authorized hoặc logger name không đúng | Kiểm tra management endpoint và security policy |

Khi lỗi chỉ xảy ra trên native, xác định nó nằm ở bước đọc resource, khởi tạo class, reflection, file I/O hay loader. Không thêm hints cho mọi logging package trước khi biết thao tác nào thiếu metadata.

## 17. Quy trình triển khai có thể tái lập

1. Chọn backend và phiên bản tương thích với Spring Boot/GraalVM.
2. Dùng property chuẩn cho log level, file output và pattern nếu đủ nhu cầu.
3. Nếu cần cấu hình chi tiết, chọn `logback-spring.xml` hoặc `log4j2-spring.xml`.
4. Quyết định file cấu hình nằm trong classpath hay được mount ngoài.
5. Liệt kê custom appender, encoder, layout, converter, filter hoặc plugin được XML tham chiếu.
6. Xác minh class và dependency nằm trong build input.
7. Kiểm tra metadata có sẵn; chỉ thêm Runtime Hints cho truy cập động còn thiếu.
8. Chạy JVM logging test và Spring AOT/native build.
9. Chạy native executable trong môi trường giống production.
10. Kiểm tra log output, file permission, rolling policy và external config.
11. Nếu dùng reload, kiểm tra riêng behavior trên đúng backend/version/native image.
12. Version hóa file config, plugin và toolchain để có thể tái lập release.

## 18. Checklist trước khi phát hành

- [ ] Logging backend và dependency được chọn rõ ràng.
- [ ] `logging.config` được cấp trước khi logging system khởi tạo.
- [ ] `logback-spring.xml` hoặc `log4j2-spring.xml` được dùng khi cần Spring extensions.
- [ ] Logback `scan` không được bật nếu dùng Spring Boot Logback extensions.
- [ ] File classpath cần thiết có trong native image; file ngoài có mount và permission đúng.
- [ ] Custom appender/layout/encoder/converter/plugin nằm trong build input.
- [ ] Reflection hints chỉ bao gồm constructor/member thực sự được truy cập động.
- [ ] Dependency metadata được kiểm tra trước khi tạo hints trùng lặp.
- [ ] Custom structured formatter được kiểm tra theo Spring Boot version.
- [ ] Logger level, pattern, file output và rolling policy đã được test trên native executable.
- [ ] Actuator Loggers endpoint được bảo vệ nếu bật thay đổi log level runtime.
- [ ] Không kỳ vọng external XML có thể nạp class chưa được biên dịch vào executable.
- [ ] Không ghi credentials, token hoặc dữ liệu nhạy cảm vào log.
- [ ] Container UID có quyền ghi log file hoặc log được xuất qua stdout/stderr theo nền tảng vận hành.

### Câu hỏi tự đánh giá

1. Vì sao `logging.config` cần được cung cấp trước khi ApplicationContext được tạo?
2. Khác biệt giữa thay log level bằng property và nạp một custom appender theo tên class là gì?
3. Vì sao `logback-spring.xml` cần lưu ý với thuộc tính `scan`?
4. Một file XML ngoài có thể thay đổi sau deploy, nhưng vì sao nó không thể thêm custom layout class mới vào native executable?
5. Khi nào cần Runtime Hints cho custom appender hoặc converter?
6. Vì sao resource hint cho file classpath và mount external config là hai việc khác nhau?
7. Spring Boot Actuator Loggers thay đổi được điều gì và không thay đổi được điều gì?
8. Khi native logging lỗi, nên kiểm tra resource, class reachability, reflection hay file permission theo thứ tự nào?

## Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging system, `logging.config`, Logback/Log4j2 configuration, structured logging và Actuator integration.
- [Spring Boot — Logging How-to](https://docs.spring.io/spring-boot/how-to/logging.html): cấu hình Logback, file include, custom logging configuration và structured format.
- [Spring Boot — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): closed-world, classpath cố định và yêu cầu metadata cho truy cập động.
- [Spring Boot — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): Runtime Hints, resource hints và kiểm thử custom hints.
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html): cách Logback tìm, đọc và reload file cấu hình.
- [Logback — Configuration XML](https://logback.qos.ch/manual/configuration-xml.html): appender, encoder, layout, converter và XML elements.

**Kết quả cần đạt:** có thể cấu hình logging bằng property hoặc file ngoài trong native executable, hiểu khi nào cần resource/reflection hints cho custom component và nhận diện giới hạn của việc reload hoặc nạp class động. File cấu hình có thể thay đổi ở runtime, còn code appender/layout/converter cần có trong native image từ lúc build.
