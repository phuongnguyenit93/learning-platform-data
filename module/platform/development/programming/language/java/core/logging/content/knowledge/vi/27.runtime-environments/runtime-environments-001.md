# Cấu hình development cho Java Core Logging

## 1. Mục tiêu của logging ở môi trường development

**Development** là môi trường lập trình, chạy thử và gỡ lỗi cục bộ. Cấu hình logging ở đây cần trả lời nhanh: *đoạn mã nào chạy, tại thời điểm nào, trên thread nào, với dữ liệu định danh nào và tại sao lỗi xảy ra?* Mục tiêu là quan sát rõ luồng xử lý mà không phải thêm `System.out.println(...)` ở nhiều nơi.

Một cấu hình development hữu ích nên có:

- **Console dễ đọc:** thời gian, mức log, thread, tên logger/class, thông điệp và stack trace khi có exception.
- **Mức log có chọn lọc:** root thường để `INFO`; bật `DEBUG` cho package ứng dụng đang điều tra, chỉ bật `TRACE` trong phạm vi rất hẹp khi thật sự cần.
- **Dễ thay đổi theo môi trường:** log chi tiết trong `dev` nhưng tránh để mức này vô tình lan sang `test`/`staging`/`production`.
- **Tương quan giữa các log:** có `requestId`/`traceId`/`jobId` để nối các sự kiện thuộc cùng một request hoặc task.
- **Không lộ dữ liệu nhạy cảm:** dev vẫn có dữ liệu thật trong một số trường hợp; không ghi password, token, cookie, khóa API hay toàn bộ payload tùy tiện.
- **Không tạo nhiễu không cần thiết:** tránh log trùng, dòng cực dài, thư viện bên thứ ba phát DEBUG ồ ạt và ghi file tràn ổ đĩa.

Trong Java, **API logging** là cách code phát sự kiện (ví dụ SLF4J hoặc `java.util.logging`), còn **backend/handler/appender** quyết định lọc, định dạng và đích xuất. Tệp cấu hình phải phù hợp với backend thật sự có trong classpath. Ví dụ `logback.xml` không điều khiển một ứng dụng chỉ dùng `java.util.logging` chưa được bridge.

## 2. Chọn mức log đúng khi phát triển

Với SLF4J/Logback và Log4j 2, thứ tự thông thường là:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

| Mức | Khi nào dùng trong development | Ví dụ |
| --- | --- | --- |
| `ERROR` | Một thao tác thất bại cần xử lý | Không ghi được dữ liệu; đính kèm exception |
| `WARN` | Bất thường có thể khôi phục, kết quả không như kỳ vọng | Retry, fallback hoặc cấu hình thiếu |
| `INFO` | Mốc nghiệp vụ hoặc vòng đời có ý nghĩa | Khởi động xong, nhận job, hoàn tất đơn hàng |
| `DEBUG` | Chi tiết phục vụ tìm nguyên nhân | Cache miss, nhánh điều kiện, tham số đã rút gọn |
| `TRACE` | Diễn biến rất chi tiết, có thể số lượng lớn | Đi từng bước qua parser/algorithm |

Nếu root là `INFO` và logger `com.example.checkout` là `DEBUG`, các class trong package `com.example.checkout` có thể hiện DEBUG; các package khác vẫn thường chỉ hiện INFO trở lên. Logger con kế thừa mức của tổ tiên gần nhất có cấu hình nếu không khai báo mức riêng.

**Phân biệt hai khái niệm:**

1. **Logger level** quyết định sự kiện có được tạo/đi tiếp hay không, theo tên logger và cây kế thừa.
2. **Appender/handler level hoặc filter** có thể lọc thêm sau đó. Vì vậy việc nâng logger lên DEBUG **chưa đủ** nếu ConsoleHandler/appender vẫn chặn DEBUG.

Với `java.util.logging` (JUL), tên mức tương ứng là `FINE`, `FINER`, `FINEST`, `INFO`, `WARNING`, `SEVERE`. Không nhầm `FINE` với một hằng `DEBUG` không tồn tại trong JUL.

## 3. Logback độc lập: cấu hình console cho development

**Phạm vi ví dụ:** ứng dụng Java dùng **SLF4J API + Logback Classic**. Cần có các dependency tương thích trên classpath; XML bên dưới không tự bổ sung thư viện. Tạo file **`logback-dev.xml`**:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} requestId=%X{requestId} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <!-- Chỉ package do mình sở hữu mới bật DEBUG -->
    <logger name="com.example" level="DEBUG"/>

    <!-- Thư viện phát nhiều log có thể giảm về WARN -->
    <logger name="org.apache.http" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đối với ứng dụng Java độc lập có SLF4J + Logback, có thể chọn file này khi khởi chạy:

~~~bash
java -Dlogback.configurationFile=logback-dev.xml -cp "..." com.example.Main
~~~

`...` là **classpath do build tool/ứng dụng thật cung cấp**; câu lệnh này chỉ minh họa cách chỉ định file cấu hình, chưa phải lệnh chạy độc lập. Với Gradle/Maven, cách truyền VM option tùy task/plugin/IDE. Đừng nhầm tùy chọn JVM `-D...` (trước class chính hoặc `-jar`) với tham số ứng dụng.

Các phần cần hiểu trong XML:

- `ConsoleAppender` xuất log ra console, phù hợp khi chạy bằng IDE/terminal. `encoder` định dạng thành chuỗi UTF-8.
- `%d{HH:mm:ss.SSS}` là timestamp cục bộ (giờ:phút:giây.mili giây), `[%thread]` là thread hiện tại, `%-5level` là mức log, `%logger{36}` rút gọn tên logger, `%msg` là thông điệp, `%n` là xuống dòng.
- `%X{requestId}` lấy request ID từ MDC nếu có. Trường có thể rỗng nếu chưa được thiết lập; cấu hình pattern **không tự tạo hoặc truyền** request ID.
- `%ex` hiển thị exception/stack trace khi record có throwable. Không cần tự nối `exception.toString()` rồi làm mất stack trace.
- `<logger name="com.example" level="DEBUG"/>` chỉ nâng mức cho namespace ứng dụng. Root có một appender console để nhận cả log được kích hoạt từ logger con.

Ví dụ với code SLF4J trong class (snippet phụ thuộc thư viện, **không phải chương trình Java độc lập**):

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class CheckoutService {
    private static final Logger LOG =
            LoggerFactory.getLogger(CheckoutService.class);

    void submit(String requestId, String orderId) {
        LOG.debug("event=submit_started requestId={} orderId={}",
                requestId, orderId);
        try {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is blank");
            }
            LOG.info("event=order_submitted requestId={} orderId={}",
                    requestId, orderId);
        } catch (RuntimeException e) {
            LOG.error("event=order_submit_failed requestId={} orderId={}",
                    requestId, orderId, e);
            throw e;
        }
    }
}
~~~

Mẫu này dùng placeholder `{}` của SLF4J và truyền exception làm **tham số cuối** để backend có thể ghi stack trace. `requestId` được truyền rõ trong lời log; nếu muốn sử dụng `%X{requestId}` trong pattern, ứng dụng phải đặt MDC tương ứng (xem phần sau). Chọn một nơi chịu trách nhiệm log stack trace: đừng ghi lại nguyên exception nhiều lần ở các lớp caller rồi gây log trùng.

### Kế thừa logger và log xuất hiện hai lần

Logger con trong Logback thường có `additivity=true`: event đi qua appender gắn trực tiếp với nó và các appender của logger tổ tiên. Nếu đã gắn `CONSOLE` vào `root` thì **không cần** thêm cùng appender vào `com.example`. Gắn ở cả hai nơi có thể khiến một event in hai dòng. Chỉ dùng `additivity=false` khi cố ý tách một nhánh log sang appender riêng; lúc đó phải gắn đủ appender cho nhánh đó, nếu không có thể mất output.

### Cách nạp cấu hình theo môi trường

Có hai cách dễ kiểm soát:

1. **Ứng dụng Java thuần:** giữ file riêng như `logback-dev.xml` và chỉ định bằng VM option ở cấu hình chạy dev; production dùng file/giá trị khác.
2. **Spring Boot:** ưu tiên `application-dev.properties` hoặc `application-dev.yml` để đổi `logging.level.*` theo profile; dùng `logback-spring.xml` nếu cần layout/appender đặc thù có hỗ trợ phần mở rộng Spring.

Không nên bỏ file cấu hình dev có root DEBUG vào runtime production mà không có cơ chế chọn môi trường đáng tin cậy.

## 4. Spring Boot: bật mức log theo profile development

Nếu module dùng **Spring Boot với Logback mặc định**, đặt các file dưới `src/main/resources`:

**`application.properties`** — giá trị cơ sở cho các môi trường:

~~~properties
logging.level.root=INFO
logging.level.com.example=INFO
logging.level.org.springframework=WARN
~~~

**`application-dev.properties`** — chỉ áp dụng khi profile `dev` đang hoạt động:

~~~properties
logging.level.root=INFO
logging.level.com.example=DEBUG
logging.level.org.springframework.web=INFO
logging.level.org.hibernate.SQL=WARN
~~~

Chạy ứng dụng Spring Boot đã build ở profile dev:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

`app.jar` đại diện cho executable JAR đã được build của ứng dụng, không phải file mẫu có sẵn. Cách khác là đặt biến môi trường `SPRING_PROFILES_ACTIVE=dev` ở cấu hình chạy IDE/container. Không đặt `spring.profiles.active` bên trong chính `application-dev.properties` rồi kỳ vọng nó kích hoạt được file của mình; profile phải được chọn từ nguồn cấu hình hợp lệ bên ngoài profile-specific document.

**Thứ tự hiệu lực:** Spring Boot nạp cấu hình cơ sở và cấu hình áp dụng cho các profile đang bật, sau đó xử lý độ ưu tiên của các nguồn thuộc tính như command-line/environment; một giá trị `logging.level.com.example=DEBUG` ở profile dev có thể ghi đè giá trị cơ sở `INFO`. Khi đồng thời có nhiều profile, cần kiểm tra chính sách thứ tự của ứng dụng.

Khi chỉ cần chỉnh mức log, `logging.level.*` là lựa chọn dễ bảo trì. Đừng vừa cấu hình root/appender phức tạp trong XML vừa đặt nhiều mức ghi đè ở nhiều nguồn mà không biết giá trị cuối cùng.

Nếu cần nhiều layout, màu sắc hoặc filter chuyên biệt, dùng **`logback-spring.xml`** để Spring Boot có thể quản lý sớm logging và các phần mở rộng như `<springProfile>`. File `logback.xml` truyền thống không hỗ trợ các phần mở rộng Spring Boot giống `logback-spring.xml`. Tên file và khả năng cấu hình còn tùy backend được dùng (Logback hay Log4j 2); đừng áp dụng quy tắc Logback cho mọi backend.

### Lựa chọn console và file khi phát triển

Thông thường **console là đủ** cho chạy local và debug trong IDE: log hiện cạnh stdout/stderr, không cần quản lý dung lượng file. Khi cần lưu lịch sử dài hơn vòng đời terminal, mới thêm `FileAppender`/`RollingFileAppender` với giới hạn kích thước, số phiên bản và thời gian lưu. Không bắt đầu bằng ghi file vô hạn vào thư mục dự án hoặc commit file log vào Git.

Có thể dùng màu ANSI để dễ nhận mức log trong terminal, nhưng màu phụ thuộc IDE/terminal/backend; log gửi tới pipeline văn bản/JSON nên tránh escape code nếu không cần thiết. Giờ log, timezone và định dạng timestamp cần thống nhất khi đối chiếu nhiều ứng dụng.

## 5. Ví dụ Java 17 độc lập, không cần dependency: JUL với file cấu hình dev

Ví dụ này dùng `java.util.logging` có sẵn trong JDK để chứng minh **root level**, **logger level** và **handler level** cùng ảnh hưởng đến output. Nó không dùng SLF4J/Logback; các mức `FINE`/`WARNING` tương đương về mục đích với DEBUG/WARN trong ví dụ phía trên.

Tạo file **`logging-dev.properties`** ở thư mục chạy:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding=UTF-8
java.util.logging.SimpleFormatter.format=%4$s [%3$s] %5$s%6$s%n

com.example.catalog.level=FINE
~~~

Ở đây:

- `.level=INFO` là mức mặc định của root logger;
- `com.example.catalog.level=FINE` cho phép log chi tiết ở logger này;
- `java.util.logging.ConsoleHandler.level=ALL` đảm bảo handler không chặn `FINE` đã được logger con cho qua;
- `SimpleFormatter.format` quy định mức, tên logger, message và throwable. Cấu hình console này ghi ra **stderr**, khác với `System.out.println`.

Tạo file **`DevelopmentLoggingDemo.java`**:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

public class DevelopmentLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("com.example.catalog");

    public static void main(String[] args) {
        LOG.info("event=app_started env=dev");
        LOG.fine("event=cache_miss key=item-42");

        try {
            validate(-1);
        } catch (IllegalArgumentException error) {
            LOG.log(Level.WARNING,
                    "event=validation_rejected requestId=req-42", error);
        }

        System.out.println("demo_done");
    }

    private static void validate(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa hai file:

~~~bash
javac -encoding UTF-8 DevelopmentLoggingDemo.java
java -Djava.util.logging.config.file=logging-dev.properties DevelopmentLoggingDemo
~~~

**Stdout chính xác** (chỉ riêng `System.out`):

~~~text
demo_done
~~~

Các bản ghi JUL đi vào **stderr**. Trích đoạn message dự kiến (stack trace có vị trí dòng tùy cách lưu file):

~~~text
INFO [com.example.catalog] event=app_started env=dev
FINE [com.example.catalog] event=cache_miss key=item-42
WARNING [com.example.catalog] event=validation_rejected requestId=req-42
java.lang.IllegalArgumentException: id must be positive
    at DevelopmentLoggingDemo.validate(...)
    at DevelopmentLoggingDemo.main(...)
~~~

Đây là trích đoạn minh họa của stderr, **không phải stdout đầy đủ để so khớp ký tự**. Nếu bỏ VM option `-Djava.util.logging.config.file=...`, JVM dùng cấu hình logging mặc định (hoặc cấu hình do môi trường cung cấp) nên `FINE` thường không hiện. Nếu đổi `ConsoleHandler.level` từ `ALL` sang `INFO`, event `FINE` có thể bị lọc dù logger cho phép; nếu đổi mức của `com.example.catalog` thành `INFO`, event bị loại ngay ở logger.

`java.util.logging.config.file` là **system property của JDK**; Logback sẽ không đọc `logging-dev.properties` bằng cơ chế đó. Đây là điểm giúp nhận diện trường hợp chỉnh một cấu hình nhưng ứng dụng thật dùng framework khác.

## 6. Request ID, thread và MDC trong development

Đối với server chạy nhiều request đồng thời, log chỉ có thời gian và thread chưa đủ. Tên thread có thể được tái sử dụng cho nhiều request. Định danh riêng (`requestId`, `traceId`, `jobId`) giúp lọc các sự kiện liên quan.

Với **SLF4J MDC** và backend hỗ trợ MDC, có thể đặt request ID trong phạm vi xử lý rồi dọn ở `finally`:

~~~java
import org.slf4j.MDC;

// Đoạn minh họa trong bộ xử lý request, không phải chương trình độc lập.
static void withRequestId(String requestId, Runnable action) {
    try {
        MDC.put("requestId", requestId);
        action.run();
    } finally {
        MDC.remove("requestId");
    }
}
~~~

Pattern `%X{requestId}` trong Logback sẽ xuất giá trị MDC ở **thread đang log**. MDC không tự đi từ thread gửi task sang worker của `ExecutorService`/`CompletableFuture`; phải truyền context một cách có chủ đích và dọn sau mỗi task để tránh sót dữ liệu của request trước. Nếu một luồng có nhiều context lồng nhau, thay vì xóa mù, cần lưu và khôi phục giá trị trước đó. Đừng ghi ID nhận từ người dùng mà không giới hạn độ dài hoặc loại bỏ ký tự điều khiển gây log injection.

## 7. Giữ log dev đủ chi tiết nhưng vẫn an toàn

Một số lỗi rất dễ xảy ra khi DEBUG được bật:

- **Rò rỉ dữ liệu:** đối số phương thức, URL query, header Authorization, cookie, mật khẩu, OTP, token, thông tin cá nhân, chuỗi kết nối có secret hoặc full request/response body. Chỉ log field đã chọn, che/redact trước khi đưa vào logger.
- **Nhiễu thông điệp:** bật `logging.level.root=DEBUG` làm mọi thư viện phát log rất nhiều. Hãy giữ root INFO và nâng đúng namespace mình đang điều tra.
- **Sai mức:** `ERROR` cho mọi lỗi nhập liệu hợp lệ sẽ làm dashboard báo động; `INFO` cho từng item trong vòng lặp có thể tạo lượng log khổng lồ.
- **Thiếu stack trace:** `LOG.error("failed: {}", error.getMessage())` chỉ ghi message. Để điều tra exception, truyền đối tượng exception theo API thích hợp, ví dụ `LOG.error("failed", error)`.
- **Log trùng:** cùng một throwable bị log ở repository, service và controller; mỗi lớp nên thêm ngữ cảnh nếu thật sự cần, thống nhất điểm chịu trách nhiệm ghi lỗi.
- **Ghép chuỗi tốn tài nguyên:** `LOG.debug("data=" + expensiveToString())` tính chuỗi trước khi backend biết có xuất DEBUG hay không. Dùng placeholder hoặc kiểm tra `isDebugEnabled()` cho thao tác thực sự tốn kém.
- **Không xác định backend:** thêm nhiều SLF4J provider/binding hoặc bridge chồng chéo dẫn đến cảnh báo, log lặp hoặc cấu hình không được dùng. Kiểm tra dependency tree, output lúc startup và backend đang active.
- **Chỉnh file config nhưng không thấy tác dụng:** file không ở classpath, sai tên file, profile chưa bật, IDE không truyền VM option, filter/appender chặn mức log hoặc ứng dụng không sử dụng thư viện đó.
- **Màu và encoding:** UTF-8 trong logger không tự khắc phục terminal không hiển thị Unicode; kiểm tra charset file, console và công cụ đọc log.
- **Chỉ debug bằng log:** khi cần xem trạng thái tại đúng thời điểm, debugger, unit test hoặc trace có thể phù hợp hơn log TRACE kéo dài.

Đừng coi môi trường dev là nơi mặc định được ghi mọi dữ liệu. Ưu tiên dữ liệu giả lập cho thử nghiệm, giới hạn quyền đọc log, tránh phát tán ảnh chụp log chứa thông tin thật và loại bỏ log nhạy cảm trước khi commit.

## 8. Cách kiểm tra cấu hình có hiệu lực

### Kiểm tra nhanh theo thứ tự

1. **Xác định backend thực tế:** ứng dụng Java thuần dùng JUL hay SLF4J + Logback/Log4j 2? Nếu là Spring Boot, kiểm tra starter/dependency tree và tệp cấu hình logging đang được nạp.
2. **Kiểm tra đúng môi trường:** đã chọn profile `dev`, truyền đúng VM option và file nằm đúng classpath/đường dẫn chưa?
3. **Phát hai event có chủ đích:** một INFO và một DEBUG/FINE từ chính package ứng dụng. Đúng cấu hình ví dụ, cả hai đều xuất ở dev.
4. **Phát event từ package khác:** root INFO vẫn lọc DEBUG ngoài package đã chọn. Kiểm tra lại logger hierarchy nếu khác kỳ vọng.
5. **Kiểm tra format:** thời gian, level, thread, logger, requestId (khi có) và stack trace khi có exception.
6. **Kiểm tra không lộ dữ liệu:** dùng dữ liệu kiểm thử có marker giả như `TEST_TOKEN_DO_NOT_LOG`, xác nhận backend không ghi giá trị đó; kiểm tra cả header và stack trace.
7. **Kiểm tra log trùng và hiệu năng:** mỗi event xuất đúng số lần dự kiến, không bị chặn request vì log quá nhiều.
8. **Chuyển sang cấu hình không phải dev:** chứng minh DEBUG/FINE không còn xuất đại trà và cấu hình chi tiết chỉ bật nơi được phép.

### Bảng chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra/sửa |
| --- | --- | --- |
| INFO hiện, DEBUG không hiện | Root/package ở INFO, handler filter ở INFO | Kiểm tra cả logger và appender/handler |
| Không có log nào | Backend chưa nạp, không gắn appender/handler, sai file | Xác nhận classpath, VM options và startup diagnostics |
| Một event in hai lần | Appender gắn cả logger con và root, hoặc nhiều bridge/provider | Kiểm tra additivity và dependency |
| Thay `application-dev.properties` nhưng mức không đổi | Profile dev chưa active hoặc giá trị bị nguồn cấu hình ưu tiên cao hơn ghi đè | Kiểm tra active profiles và effective config |
| Có requestId trong request thread, mất trong worker | MDC không tự động propagate qua async boundary | Capture, truyền, thiết lập và dọn context theo task |
| Log quá nhiều/chạy chậm | Root DEBUG/TRACE, SQL/body logs hoặc format quá nặng | Hạ root về INFO, bật hẹp package, giảm payload |
| Log thiếu stack trace | Chỉ log exception message | Truyền throwable tới API log |
| Dev log lọt production | Cấu hình dev nằm trong classpath và được nạp mặc định | Tách theo profile/VM option, kiểm tra quy trình deploy |

## 9. Cấu hình gợi ý cho việc phát triển hằng ngày

Một baseline dễ bắt đầu là:

~~~text
Output       : console; UTF-8; timestamp, level, thread, logger, requestId
Root level   : INFO
Own package  : DEBUG khi cần điều tra; về INFO sau khi xong
Third-party  : INFO hoặc WARN tùy độ nhiễu
Exceptions   : có stack trace tại boundary xử lý rõ ràng
Security     : không log secret hay full payload nhạy cảm
Environment  : tách dev bằng profile hoặc VM option
Validation   : kiểm tra log mong đợi, log không mong đợi và log trùng
~~~

Không có cấu hình DEBUG tối ưu cho mọi dự án: mục tiêu là **mức thông tin vừa đủ để tái dựng sự cố** mà không làm chậm chương trình hay che khuất thông tin quan trọng. Bắt đầu từ root INFO, bật DEBUG tại đúng namespace, và có quy trình xác nhận dev settings không ảnh hưởng production.

### Tài liệu tham khảo chính thức

- Logback Manual — [configuration và console appender](https://logback.qos.ch/manual/configuration.html), [logger hierarchy, level và additivity](https://logback.qos.ch/manual/architecture.html).
- Spring Boot — [logging properties và tệp cấu hình](https://docs.spring.io/spring-boot/reference/features/logging.html), [profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html).
- Java 17 — [java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html), [ConsoleHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html).