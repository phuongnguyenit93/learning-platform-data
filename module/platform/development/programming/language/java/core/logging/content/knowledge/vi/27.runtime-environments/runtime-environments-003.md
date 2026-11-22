# Cấu hình staging cho Java Core Logging

## Mục tiêu

Bài học thuộc nhóm **Môi trường chạy**, chủ đề **Cấu hình staging** của Java Core Logging. Sau khi hoàn thành, bạn có thể thiết kế và kiểm tra cấu hình ghi log cho môi trường staging, phân biệt các lựa chọn phù hợp giữa development, staging và production, bật log chi tiết có kiểm soát, xác minh luồng log từ JVM tới hệ thống quan sát, và hạn chế rò rỉ dữ liệu nhạy cảm hoặc mất log khi triển khai.

**Staging** là môi trường kiểm thử trước production, thường có cùng kiến trúc triển khai, framework logging, cách đóng gói, cấu trúc log và đường thu thập log như production. Staging không nhất thiết có cùng quy mô hay dữ liệu production. Mục tiêu của log staging là phát hiện lỗi cấu hình, tích hợp, hiệu năng và khả năng quan sát **trước khi phát hành**, trong khi vẫn giữ mức nhiễu, chi phí và rủi ro hợp lý.

Cấu hình staging của ứng dụng cần trả lời rõ:

1. Log nào được tạo (log level, logger/package, filter)?
2. Event được biểu diễn thế nào (timestamp, level, service, environment, trace/correlation ID, message, exception)?
3. Log đi đâu (stdout, file, collector, hệ thống tìm kiếm)?
4. Điều gì xảy ra khi sink chậm hoặc lỗi (backpressure, retry, drop, shutdown)?
5. Ai được đọc log, giữ bao lâu và dữ liệu nào tuyệt đối không được ghi?
6. Làm cách nào chứng minh đúng cấu hình và không gây tác dụng phụ khi chạy ở tải staging?

## 1. Staging khác development và production ở điểm nào?

| Tiêu chí | Development | Staging | Production |
| --- | --- | --- | --- |
| Mục đích | Debug tại máy lập trình | Xác nhận release, cấu hình, tích hợp và khả năng vận hành | Vận hành dịch vụ thật |
| Mức log mặc định tham khảo | `DEBUG` cho package đang làm; `INFO` cho phần còn lại | `INFO` toàn hệ thống, `DEBUG` tạm thời cho package cụ thể | `INFO` hoặc `WARN` theo nhu cầu vận hành và volume |
| Định dạng | Text dễ đọc có thể đủ | **Càng giống production càng tốt**, ưu tiên structured logging nếu production dùng JSON | Structured logging thống nhất |
| Output | Console IDE hoặc local file | stdout/collector tương tự production | stdout/collector hoặc sink được quản lý |
| Trace/correlation ID | Hữu ích | Cần kiểm tra đầy đủ luồng truyền và lập chỉ mục | Cần vận hành ổn định |
| Retention và quyền truy cập | Giới hạn cục bộ | Có chính sách riêng, giới hạn quyền và thời gian lưu | Theo yêu cầu sản phẩm, vận hành và pháp lý |
| Chi tiết lỗi | Có thể bật khi debug | Bật có chọn lọc, giới hạn thời gian và tránh dữ liệu nhạy cảm | Kiểm soát nghiêm ngặt |

Đây là **gợi ý thiết kế**, không phải luật cố định của Java, SLF4J hoặc Spring Boot. Staging không có nghĩa cứ bật `TRACE`/`DEBUG` cho tất cả package. Làm vậy tạo quá nhiều log, che lỗi quan trọng, tăng chi phí và có thể làm thay đổi hiệu năng so với production.

Cần giữ nhất quán các thuộc tính sẽ ảnh hưởng trực tiếp đến chất lượng kiểm thử: tên field JSON, cách timestamp, MDC/tracing, cách lấy stdout, format exception, behavior của appender, giới hạn kích thước và chiến lược khi queue đầy. Những khác biệt cố ý giữa staging và production phải được ghi nhận và có lý do.

## 2. Thiết kế cấu hình theo nguyên tắc một bản build, nhiều môi trường

Cùng một file JAR nên có thể chạy ở staging và production với **cấu hình triển khai khác nhau**, thay vì rebuild để đổi một hằng số log level. Một số nguồn cấu hình thường gặp:

- File cấu hình trong ứng dụng, như `application.yml` và `application-staging.yml` đối với Spring Boot.
- Environment variable, JVM system property hoặc command-line argument do hệ thống triển khai cấp.
- Cấu hình logging library như `logback-spring.xml`, `logback.xml` hoặc `log4j2.xml`.
- ConfigMap, secret manager, cấu hình runtime của container/orchestrator.

**Tách chức năng**: file profile khai báo level, endpoint và chính sách; encoder/appender xác định định dạng và đường ghi log. Không nhúng mật khẩu, access token, connection string có credential hoặc khóa API vào file logging hay thông điệp log. Secret nên đến từ cơ chế quản lý bí mật được phép và không được in ra ở log khởi động.

Nên chuẩn hóa một bộ tham số vận hành có ý nghĩa, ví dụ:

| Tham số | Vai trò | Gợi ý staging |
| --- | --- | --- |
| `APP_ENV` | Nhãn môi trường ghi trong log | `staging` |
| `SPRING_PROFILES_ACTIVE` | Chọn Spring profile (nếu dùng Spring Boot) | `staging` |
| `spring.application.name` | Tên service ổn định giữa log và metrics/traces | Ví dụ `checkout-service` |
| `logging.level.root` | Mức log nền | `INFO` |
| `logging.level.com.example.checkout` | Log chi tiết cho đúng phạm vi điều tra | `DEBUG` khi cần |
| Collector endpoint | Đường đi của log | Kết nối staging observability; cấu hình qua deployment |
| Retention/access | Quyền và thời gian lưu | Chính sách staging riêng, có thời hạn |

Khi đổi level runtime, cần hiểu quy tắc ưu tiên cấu hình của framework thực tế. Với Spring Boot, command-line arguments, environment variables và file cấu hình có thứ tự ưu tiên, nhưng không nên dự đoán mù khi có nhiều nguồn trùng tên. Hãy kiểm tra **giá trị hiệu lực** bằng cấu hình/diagnostics có kiểm soát và đối chiếu hành vi log, không in toàn bộ environment hoặc secret ra console.

## 3. Log event chuẩn trong staging cần có gì?

Một bản ghi hữu ích cho việc kiểm thử tích hợp thường có:

- **timestamp** có múi giờ rõ ràng và đủ độ chính xác; nên chuẩn hóa UTC trong pipeline nếu phù hợp.
- **level**: `ERROR`, `WARN`, `INFO`, `DEBUG` hoặc `TRACE`.
- **service**, **environment**, **version/release** và instance/pod nếu hạ tầng cung cấp.
- **logger**, **thread** hoặc execution context khi hữu ích.
- **trace_id**, **span_id** hoặc `correlation_id` nếu tác vụ đang có context hợp lệ.
- **event/message** ngắn gọn, có ngữ nghĩa; mã lỗi hoặc trạng thái ở các field riêng nếu hệ thống dùng structured logging.
- **exception type/stack trace** theo log level và chính sách bảo vệ thông tin.

Ví dụ **JSON minh họa** (không phải output mặc định của Logback):

```json
{
  "timestamp": "2026-11-10T02:30:14.123Z",
  "level": "WARN",
  "service": "checkout-service",
  "environment": "staging",
  "release": "2026.11.10-rc1",
  "logger": "com.example.checkout.PaymentClient",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event": "payment-retry",
  "attempt": 2,
  "status": 503
}
```

Các giá trị timestamp, release, service và ID trong ví dụ là **dữ liệu minh họa**. Trong ứng dụng thật, cần encoder JSON của logging stack hoặc giải pháp structured logging phù hợp; không chỉ thêm dấu ngoặc JSON quanh chuỗi tự nối rồi coi là an toàn. Chuỗi, exception và ký tự xuống dòng phải được escape đúng.

**Phân biệt field và dữ liệu nhạy cảm:** Trace ID/correlation ID giúp ghép log nhưng không phải mã xác thực; không đưa bearer token, mật khẩu, cookie phiên, Authorization header, toàn bộ request/response body, số thẻ hoặc dữ liệu cá nhân vào log. Staging đôi khi chứa dữ liệu từ tích hợp thật hoặc bản sao dữ liệu thật, vì thế vẫn phải áp dụng chính sách bảo mật.

**Trường context không tự xuất hiện.** MDC chỉ hoạt động khi ứng dụng hoặc instrumentation đưa đúng giá trị vào đó. Thêm `trace_id=%X{trace_id}` vào Logback pattern sẽ cho trường rỗng nếu không có context injection. Khi dùng tác vụ bất đồng bộ hoặc thread pool, cần propagation phù hợp và khôi phục/xóa MDC để tránh mang nhầm ID giữa các request.

## 4. Spring Boot: cấu hình staging với Logback

Đây là một cách thực hành khi ứng dụng dùng **Spring Boot + SLF4J + Logback**. Cấu hình có hai phần: chọn level theo profile, và định dạng/đích xuất log. Ví dụ không thêm dependency ngoài các thành phần logging có sẵn trong starter tương ứng; dự án dùng Log4j 2 hoặc loại bỏ Logback phải dùng cấu hình khác.

### 4.1. File `application-staging.yml`

Đặt tại `src/main/resources/application-staging.yml`:

```yaml
spring:
  config:
    activate:
      on-profile: staging

logging:
  level:
    root: INFO
    com.example.checkout: DEBUG
    org.springframework: INFO
```

Giải thích:

- `spring.config.activate.on-profile: staging` giới hạn tài liệu cấu hình này cho staging. Không đặt `spring.profiles.active` bên trong chính profile-specific file để tự kích hoạt nó.
- `root: INFO` giữ lượng log chung trong mức kiểm soát.
- `com.example.checkout: DEBUG` chỉ bật thông tin debug trong namespace ứng dụng cần quan sát. Đây là **package minh họa**; thay bằng package của dịch vụ thật, không mở toàn bộ `org.springframework` hay Hibernate lên `DEBUG` theo mặc định.
- Các logger khác vẫn theo level thừa kế thích hợp. Nếu package con khai báo mức cụ thể khác, mức hiệu lực do hệ phân cấp logger và cấu hình runtime quyết định.

Bật profile khi chạy:

```bash
APP_ENV=staging SPRING_PROFILES_ACTIVE=staging java -jar app.jar
```

Lệnh trên theo cú pháp shell POSIX (Linux/macOS). Trên Windows PowerShell:

```powershell
$env:APP_ENV = "staging"
$env:SPRING_PROFILES_ACTIVE = "staging"
java -jar app.jar
```

Tên `app.jar` mang ý nghĩa file build được triển khai. Chỉ dùng một nguồn active profile được kiểm soát bởi deployment; khi có cấu hình khác ghi đè, kiểm tra giá trị thực sự đang hoạt động. Không cần rebuild JAR mỗi lần đổi log level.

**Lưu ý:** File `application-staging.yml` là ví dụ dành cho Spring Boot. Java SE thông thường không tự đọc file đó; nếu không dùng Boot cần cấu hình logging framework hoặc code khởi tạo riêng.

### 4.2. File `logback-spring.xml`

Đặt tại `src/main/resources/logback-spring.xml`:

```xml
<configuration>
    <springProperty scope="context"
                    name="APP_NAME"
                    source="spring.application.name"
                    defaultValue="java-service"/>

    <property name="ENV" value="${APP_ENV:-unknown}"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{ISO8601} level=%-5level env=${ENV} service=${APP_NAME} thread=%thread trace_id=%X{trace_id} span_id=%X{span_id} logger=%logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Trong ví dụ:

- `ConsoleAppender` ghi ra console, phù hợp với mô hình container nơi runtime/agent thu stdout. Vẫn cần kiểm tra pipeline để chắc log thực sự được gom và tìm kiếm.
- `springProperty` lấy tên service từ Spring Environment; chỉ hoạt động với cách nạp cấu hình hỗ trợ extension của Spring Boot, chẳng hạn `logback-spring.xml`. Không sao chép nguyên thẻ này vào `logback.xml` thuần rồi kỳ vọng nó chạy.
- `APP_ENV` được cung cấp bởi deployment; nếu thiếu, pattern ghi `unknown` để lỗi gắn nhãn môi trường dễ thấy. Không hard-code `env=staging` vào cấu hình dùng chung cho tất cả môi trường.
- `%X{trace_id}` và `%X{span_id}` đọc từ MDC tại lúc log event được tạo/capture. Việc có giá trị phụ thuộc instrumentation ứng dụng.
- `%msg%n` xuất message và xuống dòng; khi ghi text, message chứa newline có thể làm một event trải nhiều dòng. Structured JSON encoder giúp pipeline thu thập ổn định hơn nếu production dùng JSON.

Các level cụ thể trong `application-staging.yml` có thể được Spring Boot áp dụng lên logger; root `INFO` trong XML tạo baseline. Nếu ứng dụng sử dụng thêm `logging.config` hoặc thư viện logging khác, cần kiểm tra đường cấu hình thực tế và tránh định nghĩa appender trùng gây log lặp.

**Không bật scanning tự động của Logback một cách tùy tiện** khi dùng các Spring Boot extension trong `logback-spring.xml`. Nếu muốn thay đổi log level runtime, dùng cơ chế quản lý cấu hình được hệ thống hỗ trợ, có quyền hạn và audit rõ ràng; tránh đổi file trong container mà không kiểm soát version.

### 4.3. Khi cần structured JSON

Nếu production đang xuất JSON, staging nên dùng **cùng encoder/schema** để kiểm thử parsing, truy vấn, correlation và dashboard; không nên lấy ví dụ pattern text ở trên làm chuẩn cuối cùng. Chọn JSON encoder tương thích với phiên bản Spring Boot/Logback đang chạy, rồi kiểm tra output thực tế bao gồm timestamp, level, service, env, trace fields và exception.

Lý do cần kiểm tra schema: thay đổi tên `trace_id` thành `traceId` hoặc chuỗi `status` thành kiểu số có thể làm query, alert và dashboard hỏng dù log vẫn được ghi thành công. Với JSON, một log event lý tưởng là một JSON object trên một dòng (JSON Lines), không phải nhiều mảnh JSON phân tán theo stack trace.

## 5. Java thuần và các logging stack khác

Không phải ứng dụng Java nào cũng dùng Spring Boot:

| Stack | Cách tổ chức staging | Điều cần kiểm tra |
| --- | --- | --- |
| **Java Util Logging (JUL)** | `logging.properties` hoặc cấu hình qua code/JVM | Logger/handler level, filter, format và handler output |
| **SLF4J + Logback** không có Boot | `logback.xml` hoặc cấu hình được nạp riêng khi chạy | Không dùng `springProfile`, `springProperty` trong Logback thuần |
| **Log4j 2** | `log4j2.xml` hoặc cách cấu hình tương ứng | LoggerConfig, Appender, PatternLayout/JsonTemplateLayout, async mode |
| **Spring Boot** | `application-staging.yml` + cấu hình logging phù hợp | Profile thực sự hoạt động, precedence, backend logging trên classpath |

Với **Logback thuần**, có thể nạp cấu hình staging riêng khi chạy, nếu file có thật:

```bash
java -Dlogback.configurationFile=/opt/app/conf/logback-staging.xml -jar app.jar
```

Đây là ví dụ đường dẫn dành cho hệ thống được triển khai sẵn; không phải lệnh độc lập có thể chạy khi chưa có JAR, thư viện và file XML. Tránh dùng đường dẫn file cứng từ máy developer trong Docker image. Các đường dẫn ngoài image nên được quản lý bằng deployment manifests hoặc mount có version.

Đừng dùng đồng thời nhiều backend SLF4J ngoài ý muốn. Chạy với logging backend khác với dự tính có thể khiến file XML không được đọc hoặc log định dạng bất ngờ. Khi điều tra staging, xem startup diagnostics của logging framework và dependency tree của build ở phạm vi có thể truy cập.

## 6. Java 17 chạy độc lập: mô phỏng bật mức chi tiết cho staging

Ví dụ này chỉ dùng **JDK 17+** và `java.util.logging` để minh họa cách chọn log level theo môi trường, định dạng field môi trường và gửi log ra `stdout`. Nó **không** thực thi cấu hình Spring Boot/Logback ở mục trước, không giả định có JSON encoder hoặc log collector.

Tạo file `StagingLoggingDemo.java`:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class StagingLoggingDemo {
    public static void main(String[] args) {
        String environment = System.getProperty("app.env", "staging");

        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel("staging".equals(environment)
                ? Level.FINE : Level.INFO);

        Handler stdout = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "env=" + environment
                        + " level=" + record.getLevel().getName()
                        + " event=" + record.getMessage()
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }

            @Override
            public synchronized void close() {
                flush();
            }
        };

        stdout.setLevel(Level.ALL);
        logger.addHandler(stdout);
        try {
            logger.info("service-started");
            logger.fine("cache-check");
            logger.warning("retrying-downstream");
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
        }
    }
}
```

Biên dịch và chạy mặc định:

```bash
javac StagingLoggingDemo.java
java StagingLoggingDemo
```

**stdout** chính xác cho giá trị mặc định `app.env=staging`:

```text
env=staging level=INFO event=service-started
env=staging level=FINE event=cache-check
env=staging level=WARNING event=retrying-downstream
```

Chạy ở chế độ khác để quan sát việc ẩn log chi tiết:

```bash
java -Dapp.env=production StagingLoggingDemo
```

**stdout** khi dùng `app.env=production`:

```text
env=production level=INFO event=service-started
env=production level=WARNING event=retrying-downstream
```

Giải thích:

1. Logger `demo.checkout` tắt parent handlers để tránh in trùng với root logger. Handler `StreamHandler(System.out, ...)` được cấu hình để xuất ra stdout và gọi `flush()` sau từng event, giúp ví dụ deterministic.
2. JUL dùng `FINE` tương đương mức log chi tiết hơn `INFO`; tên level trong output là `FINE`, **không phải** `DEBUG` như SLF4J/Logback.
3. Ở staging, logger level là `FINE` nên cả ba event đều được xuất; ở production, `FINE` bị lọc. `WARNING` của JUL gần với `WARN` trong nhiều logging stack.
4. Ví dụ ghi các event literal không chứa dữ liệu người dùng, chỉ để dễ đối chiếu. Trong code thực tế, cần formatter/structured logger xử lý escape, dữ liệu nhạy cảm và exception đúng cách. Đừng tự nối text từ input không tin cậy rồi gọi đó là JSON an toàn.
5. Đây là chương trình chạy trên một JVM, không có concurrency, network collector hay chi phí thực của AsyncAppender. Muốn đánh giá staging logging thực tế phải thử với stack và workload thật.

Thử nghiệm thêm: chạy `java -Dapp.env=staging StagingLoggingDemo` và `java -Dapp.env=test StagingLoggingDemo`. Ở `test`, `FINE` bị ẩn vì chương trình chỉ bật mức này khi environment chính xác bằng `staging`. Kiểm tra điều kiện bằng so sánh chuỗi chính xác giúp tránh hiểu nhầm tên môi trường.

## 7. Async logging ở staging: kiểm tra hiệu năng và mất log

Nếu production dùng asynchronous logging, staging nên thử đúng cơ chế queue/worker/sink đó. Async logging thường giảm thời gian caller chờ ghi log **khi queue còn khả năng tiếp nhận**, nhưng không đảm bảo sự kiện đã bền vững ở nơi nhận khi `logger.info(...)` trả về.

Đo ít nhất:

- **Caller latency** của lời gọi log và tác động lên p95/p99 endpoint.
- **Queue occupancy**, high-water mark, enqueue blocking, throughput của worker và sink.
- **Dropped/discarded events**, retry, lỗi writer/collector.
- **Event-to-searchable latency**: từ thời điểm sinh log đến lúc có thể truy vấn trên hệ thống tập trung.
- **Shutdown drain**: số event đã phát/đã nhận/đã viết, thời gian worker xử lý các event còn lại.

Chính sách khi queue đầy có thể là block, drop, discard log level thấp hoặc fallback synchronous tùy logging stack. Cấu hình giảm block có thể tăng tỷ lệ mất log; cấu hình chống drop có thể làm chậm request khi sink nghẽn. **Không đánh giá async logging chỉ bằng throughput của producer**; một benchmark phát log nhanh nhưng drop phần lớn event là kết quả không đáng tin.

Các kiểm thử nên bao gồm tải ổn định, burst nhiều log, chậm filesystem/stdout, collector unreachable và graceful shutdown. Với log audit cần bảo đảm bền vững, queue trong RAM không thay thế được một đường lưu durable có chính sách riêng.

## 8. Dữ liệu nhạy cảm và quyền truy cập staging

Mặc định coi staging là môi trường có thể chứa dữ liệu cần bảo vệ:

- Không log password, API key, OAuth token, cookie phiên, Authorization header, mã xác thực, thông tin thanh toán hoặc toàn bộ request body.
- Nếu cần quan sát một request, ưu tiên **request ID/trace ID** và event code; dữ liệu cá nhân chỉ lưu khi được phép, tối thiểu hóa và có masking/redaction kiểm thử được.
- Kiểm tra cả **exception messages**, stack trace và HTTP client interceptors: thư viện đôi khi in URL có query chứa token, header hoặc payload dù code nghiệp vụ không gọi log trực tiếp.
- Áp dụng quyền truy cập, retention, phân vùng dữ liệu và mã hóa đường vận chuyển tương ứng với chính sách staging. Không tự động chuyển log staging sang production index hoặc ngược lại.
- Với log level `DEBUG` tạm thời, quy định phạm vi package, thời điểm bắt đầu/kết thúc, owner và cách xác minh đã tắt. Tránh để verbose logging tồn tại lâu rồi thành mặc định.

**Redaction nên được thực hiện trước khi log rời ứng dụng hoặc ở vị trí pipeline được kiểm soát**, và phải thử bằng dữ liệu test có cấu trúc đại diện. Chỉ dựa vào việc “không ai xem log staging” là không đủ, vì log vẫn có thể được sao chép, forward hoặc lưu lâu.

## 9. Quy trình kiểm chứng cấu hình staging

Thực hiện kiểm thử sau mỗi lần thay config hoặc logging dependency. Mục tiêu là kiểm tra **giá trị thực tế**, không chỉ nhìn vào file YAML/XML:

| Kiểm tra | Cách làm | Kết quả mong muốn |
| --- | --- | --- |
| Profile | Khởi động cùng image bằng `SPRING_PROFILES_ACTIVE=staging`, xác minh qua hành vi/diagnostics an toàn | Staging config được kích hoạt, không bị cấu hình khác ghi đè |
| Level mặc định | Phát log `INFO`/`WARN` và `DEBUG` từ package không được bật chi tiết | `INFO`/`WARN` xuất hiện, `DEBUG` ngoài phạm vi bị lọc |
| Level cụ thể | Phát `DEBUG` từ package được cấu hình | Debug đúng package xuất hiện; không có flood từ thư viện nền |
| Field log | Phát event mẫu có release/service/environment | Có timestamp, level, service, env và schema hợp lệ |
| Trace/MDC | Một request đi qua hai service và xử lý async | Trace ID nhất quán trong cùng trace; không rò ID giữa các request |
| Exception | Gây lỗi kiểm thử đã biết | Event có loại lỗi và stack trace hữu ích, không lộ secret |
| Collector | Tra một event ID test duy nhất ở backend | Nhận và tìm được event trong khoảng thời gian mong đợi |
| Overload | Tạo burst vượt khả năng sink | Ghi nhận queue, block/drop theo chính sách, không mất log âm thầm |
| Shutdown | Dừng service một cách graceful | Appender/worker có cơ hội flush, các giới hạn mất log được ghi nhận |
| Security | Gửi payload chứa token giả và dữ liệu nhạy cảm mô phỏng | Không tìm thấy raw token/PII trong output, collector hoặc index |

Nên gửi một **event thử nghiệm có ID riêng**, sau đó kiểm tra từ đầu đến cuối: ứng dụng tạo → console/file có event → agent/collector tiếp nhận → backend index → truy vấn/dashboard đọc được. Cần phân biệt timestamp do ứng dụng tạo và thời điểm backend cho phép tìm kiếm. Nếu chỉ thấy log trên console mà không thấy trong dashboard, có thể lỗi ở agent, parser, transport, index mapping, retention hoặc quyền truy cập.

Khi kiểm tra mức log bằng trace hoặc debug, chọn request/test data an toàn và giữ tốc độ phát trong giới hạn để không vô tình tạo hàng triệu dòng. Nếu dùng container, xác minh stdout/stderr được gom đúng và dòng log không bị cắt vì vượt giới hạn kích thước.

### Smoke test trước phát hành

1. Triển khai cùng bản build dự định lên staging, xác minh service name, env=staging và release được gắn đúng.
2. Sinh một request thành công và một lỗi kiểm soát; xác nhận level, message, exception và correlation.
3. Phát log từ package đang bật `DEBUG` rồi từ package không bật; xác nhận bộ lọc hoạt động.
4. Truy vấn event ở log backend; kiểm tra độ trễ nhận/index và định dạng field.
5. Gửi dữ liệu giả có cấu trúc như secret để chứng minh masking; không dùng credential thật cho test.
6. Kiểm tra metrics về log volume, dropped events và endpoint latency trong tình huống burst.
7. Khôi phục level của các package tăng verbosity khi đã kết thúc điều tra; ghi nhận bản config triển khai và cách rollback.

## 10. Những lỗi cấu hình staging thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Staging chỉ in `INFO` dù YAML có `DEBUG` | Profile không active, logger name sai hoặc nguồn cấu hình ưu tiên cao hơn | Kiểm tra active profile, effective level và package thật |
| Cấu hình có `springProfile` nhưng báo lỗi khi khởi động | Dùng Logback thuần hoặc `logback.xml` không hỗ trợ Spring extension | Dùng `logback-spring.xml` trong Spring Boot hoặc cấu hình Logback thuần |
| Cùng event xuất hiện hai lần | Gắn hai appender cùng sink, additivity hoặc parent handler không đúng | Kiểm tra logger hierarchy và các appender tham chiếu |
| `trace_id` luôn trống | Chưa có MDC/trace context injection hoặc xử lý async làm mất context | Kiểm tra instrumentation, propagation và scope |
| Log trên console có nhưng không thấy ở backend | Collector không ship, parser/index/drop/permission lỗi | Kiểm tra từng đoạn pipeline bằng event ID kiểm thử |
| Log staging bị gắn nhãn production | Biến môi trường sai, field hard-code hoặc override profile | Dùng env chuẩn hóa và đối chiếu output thật |
| Backend không parse được JSON | Text pattern trông giống JSON nhưng escape sai hoặc schema đổi | Dùng encoder JSON tương thích; xác minh parser bằng payload test |
| Log quá nhiều, p99 request tăng | Bật DEBUG toàn hệ thống, stack trace lớn, sink chậm hoặc queue đầy | Giới hạn logger, giảm dữ liệu, đo queue/sink, chỉnh policy |
| Mất log lúc container dừng | Async queue chưa drain hoặc shutdown grace period quá ngắn | Cấu hình graceful stop và đối chiếu số event; đánh giá durable sink |
| Secret xuất hiện trong error log | HTTP interceptor, exception hoặc filter in raw input | Redact/mask từ nguồn và kiểm tra ở từng điểm capture |

## 11. Cách quản lý thay đổi để staging luôn hữu ích

Lưu cấu hình dạng code và review cùng thay đổi ứng dụng; khi phải bật DEBUG tạm thời, ghi rõ package, lý do, thời gian và người chịu trách nhiệm. Tự động kiểm tra schema/event test khi triển khai và so sánh với production để tìm lệch cấu hình. Không thay đổi thủ công trong một pod rồi tưởng tất cả instance đã thống nhất; autoscaling có thể làm phiên bản cấu hình không đồng đều.

Chỉ tách khỏi production những giá trị thực sự phụ thuộc môi trường: level, nơi gửi log, retention, quyền truy cập, sample rate và mức verbosity của một số package. Giữ cùng format/field semantics nếu các dashboard hoặc alert sẽ được dùng ở production. Nếu staging đang test một thay đổi logging lớn, triển khai có version, tạo metric kiểm tra và chuẩn bị rollback theo release, không đánh giá bằng cảm giác “log nhiều hơn là tốt hơn”.

Về vận hành, các yêu cầu nên được diễn đạt thành kết quả đo được, chẳng hạn: “Trong tải kiểm thử tiêu chuẩn, mọi event mức ERROR được pipeline nhận hoặc có chỉ báo lỗi rõ ràng; event thử nghiệm tìm được trong thời gian SLO đã định; không lộ chuỗi token giả; p99 endpoint không vượt ngân sách”. Các ngưỡng cụ thể phải do sản phẩm và hạ tầng quyết định. Mục tiêu là staging giúp phát hiện chính xác lỗi trước khi release, với đủ dữ liệu chẩn đoán và rủi ro đã được kiểm soát.

## 12. Câu hỏi tự kiểm tra

1. Tại sao staging nên giữ log schema giống production trong khi level có thể khác?
2. Nếu `logger.debug` không hiện dù đã cấu hình `DEBUG` trong `application-staging.yml`, bạn kiểm tra những gì trước?
3. Vì sao `%X{trace_id}` trong Logback pattern có thể cho giá trị trống, và điều gì thay đổi khi dùng `ExecutorService`?
4. Tại sao bật `DEBUG` cho toàn bộ Hibernate hoặc Spring có thể làm phép đo hiệu năng staging không đại diện production?
5. Một log xuất hiện trên stdout nhưng chưa tìm thấy trong log backend: bạn kiểm tra những bước pipeline nào?
6. Làm thế nào chứng minh masking hoạt động đối với exception, HTTP client và structured logging?
7. Khi AsyncAppender có queue trong bộ nhớ, lý do nào khiến event đã enqueue vẫn có thể mất sau khi container bị kill?

**Tiêu chí hoàn thành:** Bạn kích hoạt được cấu hình staging phù hợp với stack, giải thích được level và output thực sự có hiệu lực, đọc được log event có context, xác nhận collector tìm thấy log, kiểm tra rủi ro dữ liệu và nhận diện đường xử lý khi log bị chậm, mất hoặc lặp.

## Tài liệu tham khảo

- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) — cấu hình logging, backend và logging levels.
- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) — kích hoạt và giới hạn cấu hình theo profile.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html) — logger, appender và cấu hình XML.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — ConsoleAppender, file và AsyncAppender.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html) — cấu hình logger, appender và layout.
- [Java SE 17 — java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html) — API logging có sẵn trong JDK.
