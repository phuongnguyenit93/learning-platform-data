# Che bí mật trong Actuator `env`, `configprops`, log và thông báo lỗi

Spring Cloud Config tập trung nhiều thuộc tính nhạy cảm như mật khẩu database, API token, client secret và thông tin kết nối dịch vụ. Config Server có thể giải mã giá trị `{cipher}` trước khi trả cho Config Client, vì vậy plaintext có thể xuất hiện trong `Environment` và các bean đã bind của ứng dụng đang chạy. Nếu Actuator, log hoặc thông báo lỗi hiển thị những giá trị này, người không có quyền đọc repository vẫn có thể lấy được bí mật từ bề mặt vận hành.

Spring Boot Actuator có cơ chế sanitize cho một số endpoint, nhưng cơ chế này không thay thế việc giới hạn endpoint và không tự lọc log hay response lỗi tùy chỉnh. Cần bảo vệ theo từng bề mặt: `env` và `configprops`, quyền truy cập management, log ứng dụng và nền tảng thu thập log, cùng error response gửi ra client.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện dữ liệu nhạy cảm có thể xuất hiện trong `/actuator/env` và `/actuator/configprops`.
- Cấu hình `show-values` để giữ giá trị được sanitize và giới hạn quyền xem khi cần chẩn đoán.
- Mở rộng quy tắc sanitize bằng `SanitizingFunction` cho các key riêng của ứng dụng.
- Phân biệt sanitize của Actuator với việc lọc log và thông báo lỗi.
- Giới hạn endpoint management bằng exposure, endpoint access, Spring Security và mạng nội bộ.
- Tránh ghi secret trong log, request/response body, stack trace và validation error.
- Kiểm thử để chứng minh một giá trị canary không xuất hiện trên các bề mặt vận hành.

## Những bề mặt có thể làm lộ bí mật

Một secret không chỉ có thể lộ từ repository. Khi ứng dụng đã nạp cấu hình, nhiều thành phần có thể đọc hoặc sao chép giá trị đó:

| Bề mặt | Nội dung có thể lộ | Ví dụ |
|---|---|---|
| Actuator `env` | Property source, tên key, origin và giá trị trong `Environment` | `spring.datasource.password`, `payment.api-token` |
| Actuator `configprops` | Các bean `@ConfigurationProperties` sau binding | `DataSourceProperties`, `PaymentProperties` |
| Log ứng dụng | Nội dung object, header, request body, URL, exception message và stack trace | `Authorization`, JDBC URL có credential, token trong query string |
| Error response | Message, exception class, binding errors, rejected value và stack trace | Lỗi kết nối có URL nội bộ hoặc validation echo password |
| Log/access log/APM tập trung | Bản sao log, HTTP exchange, trace attribute và context field | Log đã bị đẩy sang SIEM hoặc dịch vụ quan sát bên ngoài |

Với Spring Cloud Config, cần rà soát cả Config Server lẫn Config Client. Server có thể giữ khóa mã hóa và credential truy cập Git; client có thể nhận plaintext sau khi server giải mã. Bảo vệ một phía không ngăn endpoint hoặc log của phía còn lại tiết lộ giá trị.

## Hiểu `env` và `configprops`

`/actuator/env` hiển thị các property source trong Spring `Environment`, cùng thông tin về nguồn và thứ tự ưu tiên. Endpoint có thể giúp tìm giá trị đến từ Config Server, biến môi trường, system property hay file cục bộ.

`/actuator/configprops` hiển thị các bean được bind bằng `@ConfigurationProperties`. Nó giúp kiểm tra cấu hình ứng dụng đã được bind ra sao, nhưng cũng có thể chứa các trường như username, password, API key hoặc endpoint nội bộ.

Ví dụ một Config Client nhận cấu hình sau từ Config Server:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: order_app
    password: ${ORDER_DB_PASSWORD}

payment:
  gateway:
    api-token: ${PAYMENT_GATEWAY_TOKEN}
```

Sau khi placeholder được phân giải và cấu hình được bind, các giá trị thật có thể nằm trong `Environment` hoặc bean cấu hình. Vì vậy, việc không commit plaintext vào Git không đủ để bảo vệ chúng khi runtime.

## Sanitize giá trị trong Actuator

Tài liệu Spring Boot hiện hành cho các dòng 3.4/3.5 và 4.x quy định giá trị của các endpoint sanitize như `env`, `configprops` và `quartz` được che mặc định bằng `******`. Có thể kiểm soát bằng thuộc tính `show-values`:

- `never`: luôn che giá trị.
- `always`: hiển thị giá trị cho mọi người gọi, nếu không có `SanitizingFunction` áp dụng.
- `when-authorized`: chỉ hiển thị giá trị cho người gọi đã xác thực và có role được cấu hình, nếu không có `SanitizingFunction` áp dụng.

Trong production, nên khai báo rõ `never` cho cả `env` và `configprops`, kể cả khi phiên bản hiện tại đã sanitize mặc định. Cấu hình tường minh giúp chính sách dễ đọc và giảm nguy cơ thay đổi ngoài ý muốn khi nâng cấp hoặc thay security configuration.

```yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Nếu nhóm vận hành cần xem một số giá trị không nhạy cảm khi chẩn đoán, cân nhắc chỉ cấp quyền theo role và vẫn giữ quy tắc sanitize tùy chỉnh cho key nhạy cảm:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: ACTUATOR_ADMIN
    configprops:
      show-values: when-authorized
      roles: ACTUATOR_ADMIN
```

Ở đây chỉ người dùng đã xác thực và có role `ACTUATOR_ADMIN` mới được phép xem các giá trị không bị quy tắc sanitize khác che. Hãy cấp role này cho nhóm vận hành có trách nhiệm, không cấp rộng cho tài khoản ứng dụng hoặc người dùng cuối.

Lưu ý: với JMX, Spring Boot xem mọi người gọi là đã được authorize cho `when-authorized`. Nếu không có nhu cầu đọc giá trị qua JMX, hãy không expose các endpoint này qua JMX hoặc bảo vệ JMX bằng cơ chế truy cập riêng. Đừng giả định role HTTP cũng giới hạn được JMX.

## Chỉ expose endpoint thực sự cần thiết

Mặc định, Spring Boot chỉ expose `health` qua HTTP. Không nên bật `env` và `configprops` chỉ để tiện quan sát thường xuyên. Nếu dashboard chỉ cần health và info, hãy giới hạn exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Nếu một quy trình chẩn đoán cần `env` hoặc `configprops`, bật tạm thời trong môi trường được bảo vệ, giữ `show-values: never`, giới hạn quyền và tắt lại sau khi hoàn tất. Có thể loại trừ rõ các endpoint nhạy cảm khi danh sách include rộng hơn:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: env,configprops,heapdump,logfile
```

`*` có ý nghĩa đặc biệt trong YAML nên phải đặt trong dấu nháy. Danh sách exclude có ưu tiên cao hơn include.

Từ Spring Boot 3.4, có thể áp dụng endpoint access theo hướng opt-in. Ví dụ chỉ cho phép health read-only và vô hiệu hóa env/configprops:

```yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    env:
      access: none
    configprops:
      access: none
```

Endpoint có access `none` bị loại khỏi application context. Nếu cần dùng `env` trong một đợt điều tra, có thể thay đổi cấu hình triển khai có kiểm soát rồi hoàn nguyên sau đó. Với Spring Boot cũ chưa hỗ trợ endpoint access, sử dụng `exposure.include`/`exclude` và Spring Security để kiểm soát.

## Giới hạn management bằng mạng và cổng riêng

Có thể tách management endpoint khỏi cổng nghiệp vụ:

```yaml
management:
  server:
    port: 9001
    address: 10.20.0.15
```

Địa chỉ trên chỉ là ví dụ mạng nội bộ; chọn interface thực tế của môi trường triển khai. Cổng riêng không tự làm endpoint an toàn. Cần thêm firewall, network policy, security group hoặc ingress rule để chỉ monitoring/operations network được kết nối. Nếu dùng reverse proxy hoặc service mesh, không route management port ra Internet và không cho người dùng bên ngoài truy cập qua một đường dẫn phụ.

Nếu management endpoint dùng chung cổng với API nghiệp vụ, bảo đảm gateway và security filter không tạo route bỏ qua xác thực. Kiểm tra cả HTTP lẫn JMX; chỉ chặn `/actuator/env` ở ingress nhưng để JMX mở vẫn có thể làm lộ cùng dữ liệu.

## Bảo vệ endpoint bằng Spring Security

Khi Spring Security có trên classpath và ứng dụng chưa khai báo `SecurityFilterChain` tùy chỉnh, Spring Boot tự bảo vệ các Actuator endpoint ngoài health. Nếu định nghĩa một `SecurityFilterChain`, auto-configuration bảo mật Actuator sẽ lùi lại; ứng dụng phải tự cấu hình quy tắc cho các endpoint và phần còn lại của ứng dụng.

Ví dụ một filter chain dành cho Actuator:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("ACTUATOR_ADMIN"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây chỉ là chain dành cho Actuator. Khi ứng dụng có chain tùy chỉnh, cần thêm chain riêng với matcher và rule phù hợp cho API nghiệp vụ; không để các request không khớp chain nào rơi vào cấu hình cho phép ngoài ý muốn. Trong môi trường production, ưu tiên cơ chế xác thực của tổ chức như OAuth2 Resource Server, mTLS hoặc identity-aware proxy thay cho tài khoản dùng chung.

Role trong ví dụ là `ACTUATOR_ADMIN`; Spring Security `hasRole` sẽ kiểm tra authority theo quy ước `ROLE_ACTUATOR_ADMIN`. Nếu cấu hình `management.endpoint.env.roles`, dùng cùng tên role theo quy tắc của Actuator.

## Mở rộng quy tắc sanitize bằng `SanitizingFunction`

Các quy tắc mặc định nhận diện nhiều tên key phổ biến như password hoặc secret, nhưng ứng dụng có thể dùng tên riêng như `partner.access-code`, `signingMaterial`, `tenantCredential` hoặc `x-api-token`. Không nên giả định mọi key nhạy cảm đều được tự động nhận diện.

Từ Spring Boot 3.5, có thể khai báo `SanitizingFunction` bằng helper `sanitizeValue()` và điều kiện `ifKeyContains()`:

```java
import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ActuatorSanitizationConfiguration {

    @Bean
    SanitizingFunction redactApplicationSecrets() {
        return SanitizingFunction.sanitizeValue()
            .ifKeyContains(
                "password",
                "secret",
                "token",
                "credential",
                "api-key",
                "access-code",
                "private-key",
                "signing-material",
                "authorization",
                "client-secret"
            );
    }
}
```

`ifKeyContains()` so khớp không phân biệt chữ hoa/chữ thường. Khi key phù hợp, giá trị được thay bằng giá trị đã sanitize. Các `SanitizingFunction` được gọi theo thứ tự cho đến khi một function thay đổi giá trị. Tên key trong danh sách cần được điều chỉnh theo quy ước đặt tên thực tế của module và các thư viện tích hợp.

Với Spring Boot trước 3.5, `SanitizingFunction` đã có từ các phiên bản trước, nhưng một số helper tiện dụng như `ifKeyContains()` chưa có. Có thể triển khai bằng lambda dựa trên `SanitizableData`:

```java
@Bean
SanitizingFunction redactLegacyKeys() {
    return SanitizingFunction.of(data -> {
        String key = data.getKey().toLowerCase(java.util.Locale.ROOT);
        boolean sensitive = key.contains("password")
                || key.contains("secret")
                || key.contains("token")
                || key.contains("credential")
                || key.contains("api-key")
                || key.contains("private-key");
        return sensitive ? data.withSanitizedValue() : data;
    });
}
```

Ví dụ này dùng `withSanitizedValue()` để giữ cơ chế che giá trị của Spring Boot. Cần kiểm thử danh sách key riêng của ứng dụng; bộ lọc theo tên không thể nhận ra một secret được lưu dưới tên vô hại như `partner.value`.

`SanitizingFunction` áp dụng cho các endpoint có hỗ trợ sanitize như `env`, `configprops` và `quartz`. Nó không tự động sửa nội dung log, HTTP response nghiệp vụ, message broker hoặc exception message. Không dùng nó như một bộ lọc dữ liệu toàn hệ thống.

## Không để secret đi vào log

Actuator sanitization không tác động đến SLF4J, Logback, Log4j2 hoặc log do thư viện ghi. Ứng dụng phải kiểm soát nội dung log ngay tại nơi phát sinh.

### Tránh log object cấu hình và giá trị nhạy cảm

Không log toàn bộ `Environment`, `Binder`, bean `@ConfigurationProperties`, request DTO hoặc object chứa credential. Một câu lệnh `toString()` tưởng như tiện lợi có thể in mọi field:

```java
// Không nên: object có thể chứa apiToken hoặc clientSecret
log.debug("Payment configuration: {}", paymentProperties);

// Nên: chỉ ghi metadata không nhạy cảm
log.info("Payment gateway configured; provider={}, timeout={}",
        paymentProperties.getProvider(),
        paymentProperties.getTimeout());
```

Với cấu hình chứa secret, không sinh `toString()` tự động có tất cả field. Có thể loại field nhạy cảm khỏi Lombok `@ToString`, record log, debugger renderer và diagnostic dump. Không truyền password hoặc token làm tham số log kể cả ở level DEBUG/TRACE vì production có thể bật level đó trong quá trình điều tra.

### Không ghi header, body và URL có credential

Các dữ liệu sau không nên được log nguyên dạng:

- Header `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie` và header API key riêng.
- Request/response body có password, access token, thông tin cá nhân hoặc payload thanh toán.
- URL có user-info hoặc token trong query string.
- JDBC URL, connection string hoặc cloud endpoint có embedded credential.
- Form validation object có `rejectedValue` là password/token.

Nếu cần log HTTP exchange, chỉ chọn allowlist các trường như method, route template, status, duration, request ID và service name. Không log body mặc định. Nếu bắt buộc debug body, chỉ thực hiện trong môi trường cô lập với dữ liệu giả, thời gian ngắn và cơ chế xóa sau kiểm thử.

### Log lỗi có kiểm soát

Không ghép `exception.getMessage()` vào response hoặc log nếu exception có thể chứa URL, header hay payload nhạy cảm. Có thể ghi loại lỗi, service đích, operation, status và correlation ID; giữ stack trace trong hệ thống nội bộ chỉ khi đã đánh giá dữ liệu exception.

```java
try {
    paymentClient.authorize(command);
} catch (PaymentGatewayException ex) {
    log.error("Payment authorization failed; provider={}, requestId={}, causeType={}",
            providerName,
            requestId,
            ex.getClass().getSimpleName());
    throw new PaymentUnavailableException("PAYMENT_PROVIDER_UNAVAILABLE", ex);
}
```

Nếu cần stack trace để điều tra, hãy bảo đảm exception không chứa secret hoặc dùng exception wrapper đã loại bỏ thông tin nhạy cảm. Không log nguyên request command. Log nội bộ vẫn phải được bảo vệ bằng quyền truy cập, retention, mã hóa và audit; “chỉ log nội bộ” không đồng nghĩa dữ liệu an toàn.

### Kiểm soát structured logging và hệ thống thu thập log

Spring Boot hỗ trợ structured logging JSON. Có thể loại bỏ một số field khỏi JSON output bằng `logging.structured.json.exclude`, nhưng tùy chọn này lọc member theo đường dẫn JSON; nó không tự tìm và che secret được nhúng trong chuỗi message. Vì vậy, không xem cấu hình exclude là giải pháp thay cho việc không log dữ liệu nhạy cảm ngay từ đầu.

Kiểm tra toàn bộ đường đi của log: console/stdout, file, rolling archive, container runtime, sidecar, log forwarder, APM, trace, SIEM và bản backup. Một giá trị bị loại khỏi dashboard vẫn có thể còn trong raw event hoặc archive. Đặt retention phù hợp, hạn chế quyền đọc và có quy trình xóa/điều tra khi phát hiện rò rỉ.

## Che thông tin trong error response

Spring Boot có thể trả thông tin lỗi qua `/error`, bao gồm message, exception, binding errors hoặc stack trace tùy cấu hình. Trong production, không trả những chi tiết này cho client. Với Spring Boot 3.x, có thể cấu hình:

```yaml
server:
  error:
    include-message: never
    include-binding-errors: never
    include-exception: false
    include-stacktrace: never
```

Trong Spring Boot 4.x, nhóm thuộc tính error được chuyển sang prefix `spring.web.error`:

```yaml
spring:
  web:
    error:
      include-message: never
      include-binding-errors: never
      include-exception: false
      include-stacktrace: never
```

Các giá trị `never` ngăn default error response đưa message, binding errors và stack trace ra ngoài. `include-exception: false` không thêm tên exception vào response. Hãy xác nhận prefix theo major version Spring Boot đang dùng; không chép cấu hình Boot 3 sang Boot 4 mà không kiểm tra metadata của phiên bản.

Với API do ứng dụng tự xử lý, dùng `@RestControllerAdvice` hoặc cơ chế Problem Details để trả mã lỗi ổn định và nội dung an toàn:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(PaymentUnavailableException.class)
    ResponseEntity<ProblemDetail> handlePaymentUnavailable(
            PaymentUnavailableException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Payment service unavailable");
        problem.setDetail("The payment request could not be completed.");
        problem.setProperty("code", ex.getErrorCode());
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}
```

Không dùng `ex.getMessage()` làm `detail`, không trả stack trace và không thêm request body vào extension property. Nếu cần hỗ trợ, thêm correlation ID để đội vận hành tìm log nội bộ. Với validation error, chỉ trả tên field và mã lỗi đã chuẩn hóa; không trả `rejectedValue` vì nó có thể là password hoặc token.

## Kiểm tra các endpoint và log có liên quan

Ngoài `env` và `configprops`, hãy rà soát các endpoint và thành phần có thể làm lộ dữ liệu:

| Endpoint/thành phần | Rủi ro | Cách xử lý |
|---|---|---|
| `/actuator/env` | Giá trị Environment và property source | Giữ `show-values: never`, không expose mặc định |
| `/actuator/configprops` | Giá trị bean đã bind | Giữ `show-values: never`, giới hạn role/exposure |
| `/actuator/logfile` | Đọc toàn bộ log file | Không expose nếu không cần; bảo vệ như kho log |
| `/actuator/httpexchanges` | Request/response metadata, có thể chứa URI/header tùy repository/filter | Không ghi header/body nhạy cảm vào repository |
| `/actuator/heapdump` | Heap có thể chứa plaintext, token và object runtime | Không expose công khai; giới hạn truy cập và lưu trữ an toàn |
| `/actuator/threaddump` | Có thể lộ thông tin thread, argument và trạng thái nội bộ | Chỉ cấp quyền cho nhóm vận hành |
| `/actuator/info` | Có thể hiển thị `info.*` và metadata tùy chỉnh | Không đặt secret trong `info.*` |
| JMX | Có thể truy cập endpoint ngoài HTTP | Kiểm soát JMX riêng hoặc tắt exposure không cần thiết |

Heap dump đặc biệt nhạy cảm: dù response không hiển thị password, dump có thể chứa object và chuỗi plaintext trong bộ nhớ. Cần hạn chế quyền tạo/tải, mã hóa nơi lưu và xóa bản dump theo retention.

## Kiểm thử để chứng minh không rò rỉ

Không chỉ dựa vào việc cấu hình có vẻ đúng. Tạo một giá trị canary giả, không phải secret thật, rồi kiểm tra toàn bộ bề mặt:

```yaml
app:
  integration:
    api-token: ACTUATOR_SECRET_CANARY_7f3d9a
```

Checklist kiểm thử:

1. Gọi `/actuator/env` và `/actuator/configprops` bằng tài khoản thường; xác nhận endpoint không expose hoặc giá trị canary được che.
2. Gọi lại bằng tài khoản vận hành; xác nhận role và `show-values` hoạt động đúng chính sách.
3. Nếu có JMX, kiểm tra đường truy cập JMX và bảo đảm không lộ canary ngoài dự kiến.
4. Gọi API nghiệp vụ gây lỗi validation và lỗi upstream; xác nhận response không chứa canary, message nội bộ hoặc stack trace.
5. Tạo request có header/body giả lập; kiểm tra application log, access log, HTTP exchange, trace và log tập trung không chứa canary.
6. Bật DEBUG/TRACE trong môi trường thử nghiệm và chạy lại; bảo đảm log vẫn không ghi giá trị nhạy cảm.
7. Kiểm tra log archive, backup và công cụ tìm kiếm log, không chỉ console hiện tại.
8. Thử với key có tên riêng của ứng dụng để xác nhận `SanitizingFunction` bắt được các trường hợp không nằm trong mặc định.
9. Xác nhận endpoint management không thể truy cập từ mạng người dùng cuối.
10. Xóa canary và dữ liệu thử nghiệm sau khi hoàn tất.

Có thể dùng tìm kiếm chuỗi canary trong log thử nghiệm:

```bash
grep -R "ACTUATOR_SECRET_CANARY_7f3d9a" ./logs
```

Trong môi trường Windows, có thể dùng `Select-String` trên thư mục log thử nghiệm. Không chạy tìm kiếm trên kho log production bằng một lệnh có thể vô tình in secret thật ra terminal hoặc lưu vào history.

## Khi phát hiện bí mật đã bị lộ

Nếu secret xuất hiện trong Actuator response, log, trace hoặc error response, hãy xử lý như một sự cố credential:

1. Thu hồi hoặc rotate credential ở hệ thống đích trước khi dọn bản sao dữ liệu.
2. Xác định key, giá trị, thời điểm, instance, endpoint và nhóm người có thể đã truy cập.
3. Kiểm tra access log, reverse proxy, JMX, log pipeline, APM, archive và backup.
4. Gỡ hoặc giới hạn endpoint gây lộ; sửa sanitizer, logging code hoặc error handler.
5. Làm sạch bản sao log theo chính sách retention và quy trình incident response; giữ lại bằng chứng cần thiết đã được bảo vệ.
6. Kiểm thử lại bằng canary mới và xác nhận các instance đã nhận cấu hình bảo vệ.
7. Ghi nhận nguyên nhân gốc và bổ sung regression test để ngăn tái diễn.

Chỉ xóa dòng log hoặc che endpoint sau sự cố không làm credential đã lộ trở nên an toàn. Nếu secret có thể đã được đọc, phải rotate/revoke và đánh giá phạm vi ảnh hưởng.

## Checklist cấu hình production

- [ ] Chỉ expose endpoint Actuator thực sự cần thiết.
- [ ] `env.show-values` và `configprops.show-values` được đặt `never` theo mặc định production.
- [ ] Nếu dùng `when-authorized`, endpoint có role cụ thể và chỉ cấp cho nhóm được ủy quyền.
- [ ] JMX không vô tình mở giá trị cho người gọi không được phép.
- [ ] Có `SanitizingFunction` cho tên key riêng của ứng dụng.
- [ ] Management port/address chỉ truy cập từ mạng quản trị.
- [ ] Spring Security bảo vệ endpoint; custom `SecurityFilterChain` đã cấu hình cả actuator và API nghiệp vụ.
- [ ] Không log object cấu hình, secret, authorization header, cookie, body hoặc URL chứa token.
- [ ] Error response không bao gồm message, exception, binding value hay stack trace.
- [ ] Log, trace, HTTP exchange, archive và backup có quyền truy cập/retention phù hợp.
- [ ] Heap dump và logfile endpoint không được expose rộng.
- [ ] Có kiểm thử canary xác nhận không rò rỉ trên tất cả bề mặt.
- [ ] Có quy trình rotate/revoke khi phát hiện lộ secret.

## Kết luận

Actuator `env` và `configprops` có thể hiển thị giá trị đã được Config Client nạp và bind, bao gồm secret được Config Server giải mã. Spring Boot hỗ trợ sanitize và `show-values`, nhưng cần giữ `never` trong production, giới hạn exposure, bảo vệ bằng role và mạng, đồng thời mở rộng `SanitizingFunction` cho các tên key riêng.

Sanitize của Actuator không lọc log hay error response. Ứng dụng phải chủ động không ghi secret, header, body hoặc exception message nhạy cảm; response lỗi cần trả mã lỗi và correlation ID thay vì chi tiết nội bộ. Kiểm thử bằng canary trên Actuator, log, trace và response là cách xác nhận chính sách thực sự hoạt động.

## Tài liệu tham khảo

- [Spring Boot – Actuator Endpoints và Sanitization](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot – Customizing Sanitization](https://docs.spring.io/spring-boot/how-to/actuator.html#actuator.endpoints.customizing-sanitization)
- [Spring Boot – Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot – Servlet Error Handling](https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.error-handling)
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties.html)
- [Spring Boot 4.0 – Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties.html)
