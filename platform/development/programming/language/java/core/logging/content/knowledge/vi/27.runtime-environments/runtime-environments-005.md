# Profile logging trong Java: cấu hình log theo môi trường chạy

## 1. Profile logging là gì?

**Profile logging** là cách chọn cấu hình ghi log dựa trên **môi trường chạy** hoặc chế độ hoạt động của ứng dụng: `dev`, `test`, `staging`, `prod`. Mỗi môi trường có mục tiêu khác nhau, vì vậy mức độ chi tiết, cách định dạng, nơi gửi log và chính sách lưu trữ có thể khác nhau.

Ví dụ: lúc phát triển, lập trình viên cần thấy thông tin `DEBUG` để tìm lỗi; khi vận hành production, lưu toàn bộ `DEBUG` có thể tạo lượng dữ liệu lớn, gây tốn tài nguyên và vô tình làm lộ dữ liệu. Trong bài kiểm thử tự động, log phải đủ để chẩn đoán khi test thất bại nhưng tránh làm kết quả test lẫn với các log nền.

```text
                 Cùng một code gọi logger
                 log.debug(...)
                 log.info(...)
                 log.warn(...)
                         |
                         v
                 Chọn active profile
                 /        |        \
                /         |         \
             dev         test       prod
         DEBUG+INFO     WARN/INFO   INFO+WARN
         console dễ đọc console gọn stdout/collector
```

Cần phân biệt:

- **Profile** là tên của một bộ cấu hình đang có hiệu lực. Java SE và SLF4J không tự định nghĩa các profile `dev/test/prod`; đó là quy ước của ứng dụng hoặc khả năng do framework như Spring Boot cung cấp.
- **Log level** là ngưỡng để logger quyết định có tạo/phát sự kiện hay không. Ngưỡng càng chi tiết thì lượng log tiềm năng càng lớn.
- **Appender/handler** quyết định đưa log đến console, file hoặc hệ thống thu thập; **encoder/formatter** quyết định dạng văn bản hoặc dữ liệu có cấu trúc.
- **MDC/correlation ID** mô tả ngữ cảnh của một request/tác vụ cụ thể; nó có thể xuất hiện trong mọi profile nhưng không phải chính profile.
- **Environment variables, system properties, file cấu hình và command-line arguments** là những cách cung cấp giá trị cấu hình cho chương trình. Không nên nhầm “tên profile” với “nơi cấu hình được đặt”.

Mục tiêu chính của profile logging là **một codebase, nhiều cách quan sát phù hợp cho từng môi trường**, trong khi quy tắc bảo mật, định danh sự kiện và tên logger vẫn nhất quán.

## 2. Thiết kế chính sách logging theo từng môi trường

Một chính sách khởi đầu có thể là:

| Môi trường | Mức gợi ý | Output | Mục đích | Giới hạn nên có |
| --- | --- | --- | --- | --- |
| `dev` | `DEBUG` cho mã ứng dụng, `INFO` cho thư viện phổ biến | Console dễ đọc, có tên class/thread | Theo dõi luồng xử lý và tìm lỗi | Không đưa bí mật vào log dù chỉ chạy máy cá nhân |
| `test` | `INFO` hoặc `WARN` tùy mục đích test | Console hoặc bộ thu log riêng của test | Chẩn đoán test thất bại, giữ CI dễ đọc | Hạn chế log lặp, tách log giữa các test |
| `staging` | Gần giống `prod`, có thể bật chi tiết trong thời gian ngắn | Console/collector như production | Kiểm tra cấu hình, hiệu năng, tích hợp và vận hành | Không thay đổi mức log lâu dài khi hết điều tra |
| `prod` | `INFO` cho sự kiện vận hành, `WARN`/`ERROR` cho bất thường | Console có collector hoặc sink tập trung | Vận hành, cảnh báo, truy vết sự cố | Ẩn dữ liệu nhạy cảm, giới hạn lượng log và retention |

Đây là **gợi ý**, không phải tiêu chuẩn bắt buộc. `INFO` có thể quá nhiều đối với thư viện nào đó, còn `DEBUG` có thể cần bật có thời hạn khi điều tra production. Hãy điều chỉnh theo sản phẩm và khả năng xử lý của pipeline log.

### Các mức thường gặp

Trong hệ sinh thái SLF4J/Logback, thứ tự mức chi tiết thường là:

```text
TRACE  ->  DEBUG  ->  INFO  ->  WARN  ->  ERROR
chi tiết nhất                         nghiêm trọng hơn
```

Logger đặt ở `INFO` thường cho qua `INFO`, `WARN` và `ERROR`; không phát `DEBUG` hoặc `TRACE`. Logger đặt ở `DEBUG` cho phép thêm `DEBUG`. Thứ tự và tên level của `java.util.logging` (JUL) khác: `FINE` thường tương đương nhu cầu chẩn đoán gần `DEBUG`, `INFO` và `WARNING` gần các mức cùng ý nghĩa.

Cần xem thêm mức lọc tại **handler/appender**: logger cho phép một event không có nghĩa mọi sink đều ghi event ấy. Filter, appender threshold, sampling và cơ chế async discard đều có thể loại hoặc chuyển hướng sự kiện sau đó.

### Một số nguyên tắc đặt cấu hình

1. Đặt mức mặc định an toàn, thường là `INFO`; tăng độ chi tiết có phạm vi, chẳng hạn package `com.example.payment`, thay vì bật `DEBUG` cho toàn bộ framework.
2. Giữ chung tên logger, tên trường như `requestId`, `traceId` và quy tắc cấu trúc sự kiện giữa môi trường để việc truy vấn log nhất quán.
3. Khác biệt rõ ràng về **mức độ và nơi nhận**, tránh để profile thay đổi cả ý nghĩa nghiệp vụ của câu log.
4. Cấu hình production thiên về log có cấu trúc, có thể gửi stdout cho log collector của container/platform; chỉ khẳng định log là JSON khi đã có encoder JSON đúng và được kiểm chứng.
5. Xem chính sách lưu trữ, phân quyền và xử lý dữ liệu nhạy cảm là phần của logging, không chỉ là một dòng `logging.level`.

## 3. Ví dụ Java 17 chạy độc lập với java.util.logging

Trong Java SE không có khái niệm active profile tích hợp sẵn. Ứng dụng có thể định nghĩa một system property, chẳng hạn `app.profile`, rồi chọn cấu hình `java.util.logging` tương ứng.

Ví dụ dưới đây **không cần Maven hay thư viện bên ngoài**. Nó dùng `java.util.logging.Logger`, `ConsoleHandler` và `Formatter` để minh họa cách ngưỡng log thay đổi giữa `dev`, `test`, `prod`.

Tạo tệp `ProfileLoggingDemo.java`:

```java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ProfileLoggingDemo {
    public static void main(String[] args) {
        String profile = System.getProperty("app.profile", "prod")
                .trim()
                .toLowerCase(Locale.ROOT);

        Level minimumLevel = switch (profile) {
            case "dev" -> Level.FINE;
            case "test" -> Level.WARNING;
            case "prod" -> Level.INFO;
            default -> throw new IllegalArgumentException(
                    "Unsupported logging profile: " + profile);
        };

        Logger logger = Logger.getLogger("example.profile");
        logger.setUseParentHandlers(false);
        logger.setLevel(minimumLevel);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(console);

        try {
            logger.fine("Loading local options");
            logger.info("Service ready");
            logger.warning("Retry scheduled");
        } finally {
            logger.removeHandler(console);
            console.close();
        }
    }
}
```

Biên dịch:

```bash
javac ProfileLoggingDemo.java
```

Chạy lần lượt:

```bash
java -Dapp.profile=dev ProfileLoggingDemo
java -Dapp.profile=test ProfileLoggingDemo
java -Dapp.profile=prod ProfileLoggingDemo
```

Kết quả **trên console (stderr)** khi chạy **riêng từng lệnh**:

```text
# dev
FINE Loading local options
INFO Service ready
WARNING Retry scheduled

# test
WARNING Retry scheduled

# prod
INFO Service ready
WARNING Retry scheduled
```

Dấu `# dev`, `# test`, `# prod` chỉ là nhãn phân tách ba lần chạy trong tài liệu, không phải output do chương trình in. `ConsoleHandler` mặc định ghi vào `System.err`; không nên mô tả kết quả này là stdout. Thông điệp và thứ tự ba lệnh log trong mỗi lần chạy là cố định vì ví dụ chạy tuần tự trên một thread.

Giải thích các quyết định:

- `System.getProperty("app.profile", "prod")` chọn `prod` nếu người chạy không truyền giá trị; đây là **quyết định của ví dụ**, không phải hành vi mặc định của Java SE.
- `Locale.ROOT` giúp chuẩn hóa tên profile ổn định, không phụ thuộc ngôn ngữ/locale của máy.
- `switch` từ chối giá trị không hỗ trợ. Điều này tránh trường hợp gõ nhầm profile mà ứng dụng lại âm thầm bật cấu hình log quá chi tiết.
- `logger.setLevel(minimumLevel)` là ngưỡng tại logger; `console.setLevel(Level.ALL)` cho phép handler nhận mọi sự kiện đã vượt qua ngưỡng logger.
- `setUseParentHandlers(false)` tránh sự kiện bị ghi lặp qua các handler của logger cha.
- `finally` gỡ và đóng handler tạo riêng cho ví dụ. Ứng dụng thật nên khởi tạo logging một lần tại bootstrap và quản lý vòng đời của handler qua cấu hình phù hợp.

Với một ứng dụng lớn, không nên tự nhân bản hàng chục đoạn `switch(profile)`. Hãy đọc cấu hình tập trung rồi truyền cùng chính sách cho hệ thống logging. Trong dự án Spring Boot có SLF4J/Logback, cơ chế profile của Spring sẽ giúp quản lý việc này.

## 4. Spring Boot: cấu hình mức log bằng application-<profile>.yml

Spring Boot hỗ trợ profile và cơ chế cấu hình nhiều nguồn. Với logging đơn giản, phần lớn trường hợp chỉ cần các tệp `application.yml` và `application-{profile}.yml`; không nhất thiết phải tạo ngay một file cấu hình Logback riêng.

Ví dụ dự án có package ứng dụng `com.example`.

`src/main/resources/application.yml` — mặc định:

```yaml
spring:
  application:
    name: example-service

logging:
  level:
    root: INFO
    com.example: INFO
```

`src/main/resources/application-dev.yml` — thấy chi tiết hơn ở mã ứng dụng:

```yaml
logging:
  level:
    root: INFO
    com.example: DEBUG
```

`src/main/resources/application-test.yml` — giữ output CI gọn nhưng vẫn cho phép log ứng dụng:

```yaml
logging:
  level:
    root: WARN
    com.example: INFO
```

`src/main/resources/application-prod.yml` — giữ mức log phù hợp vận hành:

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
```

Ý nghĩa:

- `logging.level.root` là ngưỡng cho logger gốc. Những logger cụ thể như `com.example` có thể được đặt ngưỡng khác.
- Logger con trong `com.example` kế thừa mức đã cấu hình của logger cha gần nhất trong cây tên logger, trừ khi có cấu hình cụ thể hơn.
- Các giá trị trong `application-{profile}.yml` ghi đè **những khóa trùng** của cấu hình chung khi profile đó được kích hoạt, theo cơ chế độ ưu tiên nguồn cấu hình của Spring Boot.
- Tên `com.example` chỉ là ví dụ; phải thay bằng package thực tế. Bật `DEBUG` cho package ứng dụng thường ít tốn hơn bật `DEBUG` cho `root`.
- Nếu dự án đã cấu hình level bằng một cơ chế khác hoặc qua biến môi trường/cờ dòng lệnh, cần hiểu thứ tự ưu tiên để xác định giá trị hiệu lực. Đừng nhìn riêng một tệp YAML rồi kết luận đó là level đang chạy.

### Kích hoạt profile từ bên ngoài ứng dụng

Với JAR Spring Boot đã được đóng gói, ví dụ:

```bash
java -jar example-service.jar --spring.profiles.active=dev
java -jar example-service.jar --spring.profiles.active=test
java -jar example-service.jar --spring.profiles.active=prod
```

Hoặc trên shell POSIX:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar example-service.jar
```

Nếu dùng PowerShell, có thể đặt biến môi trường cho phiên terminal trước khi chạy:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar example-service.jar
```

Các lệnh trên giả định **một ứng dụng Spring Boot đã có sẵn**, không phải lệnh chạy trực tiếp ví dụ `ProfileLoggingDemo.java` ở phần trước.

Lưu ý quan trọng: `spring.profiles.active=prod` kích hoạt **toàn bộ cấu hình ứng dụng** cho profile `prod` (database, endpoint, feature flags nếu có), không chỉ cài đặt logging. Vì vậy, không bật profile production trên máy local chỉ để nhìn định dạng log, trừ khi đã hiểu các phụ thuộc và môi trường sẽ kết nối tới đâu.

Không đặt `spring.profiles.active` bên trong chính `application-prod.yml` hoặc tài liệu YAML chỉ có hiệu lực theo profile để “tự bật” profile. Hãy chọn active profile từ cấu hình chung hợp lệ hoặc từ môi trường triển khai. Khi dùng nhiều profile đồng thời, phải kiểm tra quy tắc override và tránh cấu hình các profile trái mục đích.

## 5. Khi appender hoặc định dạng khác nhau: logback-spring.xml

`logging.level.*` đủ để đổi ngưỡng của logger. Nếu `dev` cần pattern ngắn, `prod` cần thêm correlation ID, hoặc mỗi môi trường phải dùng appender khác nhau, Spring Boot với **Logback** có thể dùng `logback-spring.xml` và phần tử `<springProfile>`.

Đây là **một cách cấu hình thay thế/hoàn chỉnh** cho phần cấu hình level đơn giản bằng YAML phía trên. Không nên đồng thời đặt các mức logger/root mâu thuẫn ở YAML và XML; hãy chọn nơi chịu trách nhiệm rõ ràng cho từng cài đặt.

Ví dụ `src/main/resources/logback-spring.xml` (chỉ dùng với Spring Boot + Logback):

```xml
<configuration>
    <springProfile name="dev">
        <appender name="DEV_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <logger name="com.example" level="DEBUG"/>
        <root level="INFO">
            <appender-ref ref="DEV_CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="test">
        <appender name="TEST_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%-5level %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <logger name="com.example" level="INFO"/>
        <root level="WARN">
            <appender-ref ref="TEST_CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="prod">
        <appender name="PROD_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{ISO8601} %-5level requestId=%X{requestId} %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <logger name="com.example" level="INFO"/>
        <root level="INFO">
            <appender-ref ref="PROD_CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="!dev &amp; !test &amp; !prod">
        <appender name="DEFAULT_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{ISO8601} %-5level %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="DEFAULT_CONSOLE"/>
        </root>
    </springProfile>
</configuration>
```

**Cách đọc cấu hình:**

1. `<springProfile name="dev">` chỉ được áp dụng khi profile `dev` đang active. `test` và `prod` tương tự.
2. Trong `dev`, mã ứng dụng `com.example` cho phép `DEBUG`, còn root là `INFO`. Những thư viện không có cấu hình mức cụ thể sẽ dùng ngưỡng gần nhất theo cây logger.
3. Trong `prod`, `%X{requestId}` chèn giá trị MDC ở sự kiện log hiện tại. Nếu không có khóa đó, trường này có thể rỗng. **Đưa `requestId` vào pattern không tự truyền context qua thread hoặc service.**
4. Profile expression `!dev &amp; !test &amp; !prod` tạo một cấu hình console `INFO` khi cả ba profile được nêu đều không active. Dấu `&amp;` là cách escape bắt buộc của ký tự `&` trong thuộc tính XML.
5. Những pattern này vẫn là **log văn bản**, không phải JSON. Muốn log JSON cần encoder/layout hỗ trợ định dạng JSON và phải kiểm tra event thực tế ở collector.
6. Ví dụ giả định **chỉ một trong các profile `dev/test/prod` được active ở một thời điểm**. Nếu `dev` và `prod` cùng active, cả hai khối có thể đóng góp logger/root/appender và hành vi không còn theo một chính sách đơn nhất. Hãy xác định profile deployment rõ ràng hoặc dùng biểu thức loại trừ cho các nhóm môi trường.

Tên file **`logback-spring.xml`** có ý nghĩa: phần tử `springProfile` là mở rộng Spring Boot cho Logback, không phải cú pháp Logback thuần. Không dùng nó trong `logback.xml` thông thường rồi mặc định chờ Spring xử lý; tránh bật tự quét lại cấu hình `scan="true"` của Logback cùng các thẻ mở rộng Spring vì cơ chế reconfiguration mặc định của Logback không hiểu các thẻ ấy. Khi dùng Log4j2 hoặc JUL, cần API và cấu hình tương ứng; `springProfile` ở đây không áp dụng nguyên xi cho mọi backend.

### Chọn output console, file hay collector

- **Container/Kubernetes:** ghi stdout/stderr thường giúp nền tảng thu thập tập trung. Cần bảo đảm collector nắm được timestamp, service name, environment và correlation ID.
- **Chạy như tiến trình trên VM:** có thể dùng file rolling appender nếu hạ tầng yêu cầu; cấu hình đường dẫn, giới hạn kích thước và retention phải phù hợp quyền file hệ điều hành.
- **Production có log có cấu trúc:** chọn encoder JSON được hỗ trợ, thống nhất các khóa như `timestamp`, `level`, `logger`, `message` và `traceId`; kiểm tra pipeline index/ingest và trường có khả năng chứa dữ liệu nhạy cảm.
- **Test tự động:** thường dùng console hoặc appender in-memory/temporary file, không gọi dịch vụ log bên ngoài nếu chỉ muốn kiểm tra logic ứng dụng.

Không giả định việc lệnh `logger.info(...)` trở về đồng nghĩa log đã ghi bền vững nếu backend đang dùng async appender hoặc có buffer; khi test phải có bước chờ, flush hay dừng phù hợp với implementation.

## 6. Cấu hình nào có hiệu lực khi khởi động?

Một lỗi rất phổ biến là sửa đúng file nhưng chạy sai profile, hoặc level bị một nguồn cấu hình khác ghi đè. Để chẩn đoán, cần phân biệt **profile active** và **level hiệu lực của logger**.

Trong Spring Boot, ví dụ các nguồn có thể góp giá trị là:

```text
application.yml                 -> cấu hình chung
application-dev.yml             -> khóa áp dụng khi dev active
environment / system property   -> cấu hình do môi trường cấp
command-line arguments          -> ví dụ --logging.level.com.example=DEBUG
logging backend configuration   -> appender, filter, encoder và có thể level
                     |
                     v
       Logger / appender hiệu lực lúc chạy
```

Thứ tự ở sơ đồ là minh họa **các nguồn tham gia**, không phải một danh sách độ ưu tiên đầy đủ cho mọi tình huống. Spring Boot có quy tắc ưu tiên cấu hình riêng; logging backend cũng có cấu hình của nó. Nếu một mức log xuất hiện ở nhiều nơi, hãy kiểm tra thứ tự áp dụng ở phiên bản framework đang dùng thay vì kết luận từ thứ tự tên file.

Ví dụ kích hoạt profile và ghi đè level của package trong một lần chạy:

```bash
java -jar example-service.jar \
  --spring.profiles.active=prod \
  --logging.level.com.example.payment=DEBUG
```

Dấu gạch chéo ngược cuối dòng là cú pháp tiếp dòng cho shell POSIX; trên Windows hãy đặt lệnh trên một dòng hoặc dùng cú pháp tiếp dòng của shell tương ứng. Chỉ bật `DEBUG` có phạm vi và thời hạn có chủ đích: thay đổi này có thể làm tăng lượng log của request production.

### Những cách xác minh không cần đoán

1. **Xác nhận active profile** từ cấu hình triển khai, startup log hoặc `Environment.getActiveProfiles()` trong Spring Boot (khi ứng dụng cho phép xem thông tin này).
2. **Kiểm tra level hiệu lực** của đúng logger sau khi hệ thống logging khởi tạo; đừng chỉ xem `logging.level.root` nếu có mức riêng cho package/class.
3. **Phát một event thăm dò không nhạy cảm** ở mức dự kiến, tìm ở đúng sink/collector và xác nhận các trường cơ bản. Không sử dụng token, mật khẩu hoặc dữ liệu khách hàng làm “dữ liệu test”.
4. **Kiểm tra filter/appender** khi event không xuất hiện dù level logger cho phép; với queue async cần xác định event đã được xử lý hay chưa.
5. **Đối chiếu log khi khởi động** với config thực tế từ image/JAR và nguồn environment; file local được sửa không có tác dụng nếu artifact triển khai chưa chứa phiên bản mới.

Nếu ứng dụng bật Spring Boot Actuator endpoint `/actuator/loggers` và cho phép truy cập, endpoint này có thể cho xem hoặc đổi mức logger ở runtime theo cấu hình quyền truy cập. Đây là tính năng cần kiểm soát truy cập; nó không thay thế việc quản lý profile và cấu hình lâu dài, và mức đổi động có thể mất khi khởi động lại.

## 7. Kiểm thử profile logging

Kiểm thử nên bao phủ hai mặt: **chọn đúng profile/cấu hình** và **event thực sự được ghi đúng ở nơi nhận**.

### 7.1. Ma trận kiểm thử

| Tình huống | Kỳ vọng |
| --- | --- |
| `dev`; package ứng dụng `DEBUG` | Log `DEBUG` của mã ứng dụng xuất hiện ở console |
| `test`; root `WARN` và package ứng dụng `INFO` | `DEBUG` ứng dụng bị lọc, `INFO` ứng dụng hiện; log `INFO` của thư viện root có thể bị lọc |
| `prod`; root `INFO` | Event `INFO/WARN/ERROR` phù hợp xuất hiện; `DEBUG` không xuất hiện nếu không override |
| Không chỉ định profile; cấu hình fallback an toàn | Không tự bật mức chi tiết ngoài chủ đích |
| Profile không được hỗ trợ trong ví dụ Java SE | Fail fast với thông báo cấu hình sai |
| Có correlation ID | Pattern nhận đúng field MDC, không lộ thông tin bí mật |
| Chạy trong container | Collector thực sự nhận log và parse đúng định dạng đã thỏa thuận |
| Chuyển đổi hoặc override log level tại runtime | Level hiệu lực thay đổi đúng phạm vi; biết cách khôi phục |

Với Spring Boot, có thể dùng `@ActiveProfiles("test")` trong integration test để kích hoạt profile. Một test đọc `Environment.getActiveProfiles()` chỉ chứng minh **profile có active**, chưa chứng minh đúng pattern và appender. Để xác minh logging, cần kiểm tra level hiệu lực hoặc chụp event từ sink phù hợp.

### 7.2. Ví dụ kiểm tra level trong dự án Spring Boot + Logback

Đoạn sau là **mẫu test tích hợp dành cho dự án Spring Boot đã có ứng dụng và dependency `spring-boot-starter-test`**; đây không phải một file Java độc lập có thể chạy ngoài dự án.

```java
import ch.qos.logback.classic.Level;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class LoggingProfileIntegrationTest {
    @Test
    void applicationLoggerUsesInfoLevel() {
        ch.qos.logback.classic.Logger logger =
                (ch.qos.logback.classic.Logger)
                        LoggerFactory.getLogger("com.example.OrderService");

        assertEquals(Level.INFO, logger.getEffectiveLevel());
    }
}
```

Test này kỳ vọng package `com.example` được đặt `INFO` trong `application-test.yml` hoặc profile `test` của `logback-spring.xml`. Nếu ứng dụng sử dụng backend khác Logback, không được ép kiểu sang `ch.qos.logback.classic.Logger`; hãy dùng API kiểm tra cấu hình tương ứng. Vì test liên quan cấu hình logging **toàn ứng dụng**, tránh chạy nhiều test thay đổi root logger/song song mà không cô lập ngữ cảnh.

Đối với việc xác minh nội dung log, nên gắn appender test riêng vào logger có tên xác định hoặc dùng tiện ích capture log của framework. Với async logging, chờ event bằng tín hiệu/bộ thu có timeout trước khi assert; tránh `Thread.sleep(...)` tùy ý.

### 7.3. Kiểm thử không lộ dữ liệu nhạy cảm

Một test âm tính hữu ích là tạo request giả chứa chuỗi token/PII đặc trưng do test tự đặt, cho ứng dụng chạy code logging, rồi xác nhận chuỗi đó **không** xuất hiện ở output thu được. Kết hợp review các câu log và quy tắc mask/redact: chỉ dựa vào profile `prod` với mức `INFO` **không bảo đảm** dữ liệu nhạy cảm không bị ghi vào một log `INFO`.

## 8. Lỗi phổ biến và hướng xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Đã chọn `dev` nhưng không thấy `DEBUG` | Level cấu hình tại root/package khác, filter ở appender, hoặc profile chưa active | Kiểm tra profile và effective level của logger cụ thể, rồi kiểm tra appender |
| Production xuất hiện rất nhiều `DEBUG` | Override còn sót từ CLI/env, XML và YAML mâu thuẫn, hoặc nhiều profile active | Truy nguồn giá trị hiệu lực; bỏ override, chỉ bật chẩn đoán có phạm vi |
| Log xuất hiện hai lần | Appender gắn cả logger con và root, cộng với `additivity=true` | Kiểm tra cây logger và appender-ref; đặt `additivity=false` khi thực sự cần |
| Ứng dụng không đọc `<springProfile>` | Dùng file Logback thuần, sai tên file hoặc bật cơ chế scan không tương thích | Dùng `logback-spring.xml` trong Spring Boot và kiểm tra startup diagnostic |
| Format production khó parse | Dùng pattern text nhưng collector kỳ vọng JSON | Cấu hình JSON encoder/structured logging đúng phiên bản, test ingest end-to-end |
| File log không xuất hiện | Đường dẫn không có quyền, thư mục không tồn tại, cấu hình appender không được active | Kiểm tra lỗi appender khi khởi động, quyền ghi và chính sách container |
| Không thấy log từ tác vụ async | Context chưa truyền, appender chưa drain, hoặc overflow policy bỏ sự kiện | Tách lỗi MDC khỏi lỗi giao event; kiểm tra worker, queue, filter và flush |
| CI lỗi ngẫu nhiên khi assert log | Test khác sửa root logger hoặc assert trước khi async sink nhận event | Cô lập logger/context, khôi phục cấu hình, chờ đúng tín hiệu có timeout |
| Sửa `application-prod.yml` không có tác dụng | Profile khác active, artifact cũ, hoặc nguồn cấu hình ưu tiên cao hơn | Xem active profiles, nguồn cấp config và effective level tại runtime |
| Test local chạm dịch vụ production | Dùng `spring.profiles.active=prod` chỉ để xem log | Tạo cấu hình log có thể thử độc lập, không bật toàn bộ profile prod một cách tùy tiện |

## 9. Vận hành và bảo mật

Logging là một phần của khả năng quan sát hệ thống, nên profile cần đi kèm kỷ luật vận hành:

- **Không ghi secret** như password, API key, session token, cookie, access token, connection string có thông tin xác thực. Không được dựa vào việc “production tắt DEBUG” để bảo đảm an toàn.
- **Giữ correlation ID nhất quán** qua thread/process/service theo cơ chế context propagation. Dùng MDC/tracing framework đúng cách; một profile không tự tạo hoặc truyền trace ID.
- **Kiểm soát khối lượng:** tăng DEBUG, stack trace lớn, object `toString()` và request/response body có thể làm tăng CPU, I/O, dung lượng lưu trữ và phí ingest.
- **Phân quyền và retention:** log production có thể chứa thông tin nhạy cảm dù đã cố gắng giảm thiểu; giới hạn người đọc, thời gian lưu và nơi sao chép.
- **Dùng cùng bộ trường log cơ bản** giữa staging và production để dashboard/alert không phải có truy vấn hoàn toàn khác nhau.
- **Ghi lại những lần đổi log level tạm thời:** lý do, phạm vi package, thời điểm bắt đầu, người/điều kiện khôi phục. Đối với thay đổi runtime, xác minh lại sau restart.
- **Không nuốt lỗi kinh doanh bằng logging:** nếu cần retry, rollback hay trả response lỗi, code nghiệp vụ vẫn phải xử lý; mức `ERROR` chỉ biểu thị sự kiện để quan sát, không tự thực thi xử lý lỗi.
- **Sẵn sàng cho hạ tầng khác nhau:** máy phát triển có thể dùng console giàu ngữ cảnh, nhưng production/container cần phù hợp cơ chế thu thập, rotation và monitoring thực tế.

## 10. Tình huống áp dụng từ đầu đến cuối

Giả sử dịch vụ `OrderService` có ba dòng log:

```java
log.debug("Validated order fields for orderId={}", orderId);
log.info("Order accepted: orderId={}", orderId);
log.warn("Order validation retried: orderId={}", orderId);
```

Đây là đoạn mã **minh họa trong ứng dụng có logger SLF4J được khởi tạo**, không phải chương trình Java độc lập. `orderId` chỉ nên là mã định danh đã được đánh giá an toàn để ghi log; không đưa nội dung đơn hàng hoặc dữ liệu thanh toán vào log một cách tùy tiện.

Với chính sách ví dụ:

- **`dev`:** logger `com.example` đặt `DEBUG`, thấy cả ba event, giúp phân tích đường đi của request.
- **`test`:** logger `com.example` đặt `INFO`, chỉ thấy `INFO` và `WARN`; output của các thư viện khác có thể ít hơn nhờ root `WARN`.
- **`prod`:** logger `com.example` đặt `INFO`, thấy `INFO` và `WARN`, không thấy `DEBUG`; nếu dùng pattern có `requestId`, log còn có trường này khi MDC đã được cài đúng.

Khi có sự cố production, đội vận hành có thể tạm bật `DEBUG` cho `com.example.order` ở nguồn cấu hình hoặc công cụ runtime được phép, kiểm tra event đã đến collector, sau đó khôi phục `INFO`. Không nên bật `DEBUG` cho root hoặc thay toàn bộ active profile từ `prod` sang `dev`, vì điều đó có thể ảnh hưởng các cấu hình khác ngoài logging.

## 11. Checklist trước khi đưa profile logging vào dự án

- [ ] Tên và mục đích các profile (`dev`, `test`, `staging`, `prod`) đã được định nghĩa.
- [ ] Mức mặc định an toàn, cách override từng package và nơi quản lý từng cài đặt đã rõ.
- [ ] Nơi nhận log phù hợp môi trường: console, file hoặc collector; định dạng đã được kiểm tra.
- [ ] Spring Boot dùng đúng `application-{profile}.yml` và, nếu cần, `logback-spring.xml`; không cấu hình mâu thuẫn.
- [ ] Môi trường triển khai chủ động đặt active profile, xác nhận profile hiệu lực khi khởi động.
- [ ] Profile logging không bị nhầm với MDC, distributed tracing hoặc async log delivery.
- [ ] Có kiểm thử mức log, event thực tế và chính sách không ghi secret; test async chờ đúng sink.
- [ ] Có quy trình bật chi tiết tạm thời, theo dõi lượng log và hoàn nguyên cấu hình.
- [ ] Mọi thay đổi cấu hình production đều được kiểm tra trên staging hoặc môi trường tương đương trước khi áp dụng, khi thích hợp.

**Ghi nhớ:** một câu lệnh logger có thể giữ nguyên từ local đến production; chính **profile, level, appender và encoder** quyết định log nào xuất hiện và xuất hiện ở đâu. Thiết kế profile rõ ràng giúp chẩn đoán hiệu quả, giảm log không cần thiết và bảo vệ dữ liệu mà không phải sửa code mỗi lần chuyển môi trường.
