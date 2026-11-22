# Che giá trị nhạy cảm trong env, configprops và log

> **Chương:** Bảo mật  
> **Module:** SPRING_CLOUD_CORE

Ứng dụng Spring Cloud thường nhận cấu hình chứa mật khẩu database, client secret, access token, API key, cookie ký phiên hoặc URI có thông tin xác thực. Những giá trị này có thể xuất hiện trong nhiều nơi: Spring `Environment`, bean `@ConfigurationProperties`, endpoint Actuator và log ứng dụng. Nếu chỉ che ở một nơi, secret vẫn có thể rò rỉ qua nơi khác.

Spring Boot Actuator mặc định sanitizes giá trị trong `/actuator/env` và `/actuator/configprops`. Có thể điều chỉnh chính sách hiển thị bằng `show-values` và mở rộng quy tắc bằng `SanitizingFunction`. Log ứng dụng là một luồng riêng: sanitization của Actuator không tự động lọc message, exception, HTTP header, MDC hoặc dữ liệu gửi tới hệ thống log tập trung.

Bài này trình bày cách bảo vệ cả ba bề mặt trong **SPRING_CLOUD_CORE**: giữ giá trị cấu hình nhạy cảm ở trạng thái đã che, kiểm soát quyền đọc Actuator, xây dựng quy tắc sanitization riêng, ghi log theo allowlist và kiểm thử để phát hiện secret bị lộ.

## 1. Xác định dữ liệu nào cần được che

Trước khi cấu hình, hãy lập danh sách dữ liệu nhạy cảm mà ứng dụng đang sử dụng. Không chỉ password và token mới là secret. URL kết nối có thể chứa username/password; header có thể chứa bearer token; một số thông tin topology hoặc định danh cá nhân cũng cần giới hạn nơi xuất hiện.

| Nhóm dữ liệu | Ví dụ | Rủi ro khi lộ |
| --- | --- | --- |
| Mật khẩu | `spring.datasource.password` | Truy cập trái phép database hoặc hệ thống dùng chung credential |
| Client secret | `spring.security.oauth2.client.registration.catalog.client-secret` | Giả mạo ứng dụng khi gọi OAuth provider |
| Access/refresh token | `access-token`, `refresh-token` | Chiếm quyền phiên hoặc gọi API thay người dùng |
| API key | `partner.api-key` | Sử dụng trái phép quota hoặc quyền API |
| Khóa mật mã | `jwt.private-key`, `keystore.password` | Ký token hoặc giải mã dữ liệu trái phép |
| Cookie/session ID | `Cookie`, `Set-Cookie`, session identifier | Chiếm phiên đăng nhập |
| Connection string | URI chứa userinfo hoặc query credential | Lộ thông tin kết nối và quyền truy cập |
| Dữ liệu cá nhân | email, số điện thoại, định danh | Rò rỉ thông tin cá nhân và vi phạm chính sách dữ liệu |

Một giá trị có thể nhạy cảm ngay cả khi tên property không chứa từ khóa như `password` hoặc `token`. Ví dụ `catalog.client.endpoint` có thể chứa URI dạng userinfo, còn `tenant-key` có thể là credential riêng của một tenant. Quy tắc tự động giúp giảm rủi ro, nhưng cần được bổ sung bằng danh mục secret cụ thể của hệ thống.

### 1.1. Phân biệt ba bề mặt cần bảo vệ

| Bề mặt | Cách dữ liệu đi vào | Cơ chế bảo vệ chính |
| --- | --- | --- |
| Environment và Config Data | YAML, properties, biến môi trường, JVM argument, Config Server | Quản lý secret source và Actuator sanitization |
| ConfigurationProperties | Binder chuyển property thành field trong bean | Sanitization ở configprops, tránh toString() làm lộ field |
| Log | Code ghi message, exception, header, MDC, request/response | Không ghi secret; lọc dữ liệu trước khi tạo log và tại pipeline |

`SanitizingFunction` phục vụ dữ liệu mà Actuator đưa vào endpoint sanitizable. Nó không phải bộ lọc toàn cục cho mọi chuỗi trong JVM. Đặc biệt, nó không tự sửa log đã được ghi bởi SLF4J, Logback hoặc Log4j2.

## 2. Actuator mặc định che giá trị trong env và configprops

Spring Boot Actuator mặc định sanitizes giá trị trả về từ `/actuator/env` và `/actuator/configprops` thành `******`. Quy tắc này áp dụng ngay cả khi endpoint được expose qua HTTP; người vận hành vẫn có thể xem tên property, property source, prefix và cấu trúc bean trong khi giá trị được che.

Ví dụ cấu hình có secret:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: ${ORDERS_DB_PASSWORD}

catalog:
  client:
    base-url: https://catalog.internal
    access-token: ${CATALOG_ACCESS_TOKEN}
~~~

Response của `/actuator/env` hoặc `/actuator/configprops` có thể cho biết property tồn tại nhưng giá trị được thay bằng `******`. Đây là hành vi bảo vệ mặc định của Actuator; không cần tự viết controller riêng chỉ để che các property cơ bản.

### 2.1. Không nhầm sanitization với mã hóa hoặc lưu trữ secret

Sanitization chỉ thay đổi cách giá trị được trình bày trong response endpoint. Nó không:

- Mã hóa giá trị trong file YAML hoặc biến môi trường.
- Thay thế secret manager hoặc hệ thống quản lý khóa.
- Xóa secret khỏi heap của JVM.
- Che giá trị khi code tự ghi log.
- Ngăn người có quyền đọc trực tiếp nguồn cấu hình hoặc hệ thống secret.
- Tự động xoay vòng credential đã bị lộ.

Secret vẫn phải được cung cấp qua nguồn phù hợp như secret manager, Kubernetes Secret được bảo vệ, Vault hoặc cơ chế quản lý secret của nền tảng. Không commit password hoặc token thật vào repository với lý do Actuator đã che chúng.

### 2.2. Exposure và sanitization là hai lớp khác nhau

Để truy cập endpoint qua HTTP, cần expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
          - configprops
~~~

Việc expose chỉ làm endpoint có thể được truy cập qua HTTP. Chính sách sanitization quyết định giá trị có được hiển thị hay không. Authentication/authorization lại là một lớp khác quyết định ai được phép gọi endpoint.

Không mở rộng exposure chỉ để debug nhanh rồi quên thu hẹp lại. env và configprops có thể tiết lộ tên property, tên bean, profile, địa chỉ nội bộ và cấu trúc tích hợp ngay cả khi giá trị secret đã được che.

## 3. Cấu hình show-values cho từng endpoint

Spring Boot hỗ trợ ba lựa chọn cho endpoint sanitizable:

| Giá trị | Hành vi |
| --- | --- |
| `never` | Luôn che giá trị |
| `always` | Hiển thị giá trị gốc cho người gọi endpoint |
| `when-authorized` | Chỉ hiển thị giá trị gốc cho người đã xác thực và có role được cấu hình |

Cấu hình an toàn cho môi trường production:

~~~yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

`never` giữ giá trị đã che kể cả khi người gọi đã đăng nhập. Đây là lựa chọn phù hợp khi không có yêu cầu vận hành cần xem secret qua Actuator.

### 3.1. Dùng when-authorized khi có nhu cầu vận hành

Trong một số môi trường, đội vận hành cần xem một số giá trị cấu hình để điều tra sự cố. Có thể giới hạn bằng role:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - CONFIG_AUDITOR
    configprops:
      show-values: when-authorized
      roles:
        - CONFIG_AUDITOR
~~~

Với HTTP endpoint, người dùng phải được xác thực và có role nằm trong cấu hình endpoint. Nếu không khai báo `roles`, mặc định mọi người dùng đã xác thực đều được xem giá trị gốc khi `show-values` là `when-authorized`. Vì vậy, hãy khai báo role cụ thể thay vì dựa vào mặc định.

Cần phân biệt role của `show-values` với quyền truy cập endpoint trong Spring Security:

- `show-values` và `roles` quyết định giá trị được trả về ở dạng gốc hay đã che.
- Security filter chain quyết định người dùng có được gọi endpoint hay không.
- Exposure quyết định endpoint có được mở qua HTTP hay không.

Cả ba lớp đều cần được cấu hình. Một endpoint có thể được bảo vệ khỏi anonymous access nhưng vẫn cho quá nhiều người dùng đã xác thực xem giá trị gốc nếu role không được giới hạn.

### 3.2. Cẩn thận với JMX

Tài liệu Spring Boot quy định JMX được xem là authorized đối với cơ chế `when-authorized`. Do đó, không được cho rằng role HTTP sẽ bảo vệ dữ liệu khi endpoint được expose qua JMX.

Nếu dùng JMX:

- Kiểm soát ai có thể kết nối tới MBean server.
- Bảo vệ cổng quản trị và cấu hình remote JMX.
- Không expose JMX ra mạng không tin cậy.
- Cân nhắc giữ `show-values: never` cho endpoint có secret.
- Kiểm tra chính sách JMX độc lập với Spring Security HTTP.

### 3.3. Không bật always trong production

`always` hiển thị giá trị cho mọi người có thể gọi endpoint, bất kể role. Nó không phải cách phù hợp để xử lý sự cố production. Nếu cần xác minh cấu hình, hãy xem nguồn secret, trạng thái bean hoặc một cờ kiểm tra không chứa secret, ví dụ `credentialConfigured=true`.

Ngay cả khi `SanitizingFunction` vẫn có thể che một số key, không nên dùng điều đó làm lý do bật `always`. Một key chưa được đưa vào quy tắc tùy chỉnh có thể bị lộ.

## 4. Mở rộng quy tắc bằng SanitizingFunction

Tên property nhạy cảm của mỗi hệ thống không giống nhau. Một ứng dụng có thể dùng `partner-token`, `signing-material`, `private-key-content` hoặc một tên nội bộ không nằm trong nhóm từ khóa mặc định.

Spring Boot cung cấp interface `SanitizingFunction` để tùy chỉnh việc che giá trị trong dữ liệu Actuator. `SanitizableData` cung cấp key, value và PropertySource của dữ liệu cần xử lý. Hàm có thể quyết định che theo tên key, giá trị hoặc nguồn cấu hình.

Ví dụ dùng API fluent có trong Spring Boot 3.5+:

~~~java
import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ActuatorSanitizationConfiguration {

    @Bean
    SanitizingFunction sensitiveConfigurationSanitizer() {
        return SanitizingFunction.sanitizeValue()
                .ifKeyMatches(
                        ".*(password|client[-_.]?secret|access[-_.]?token"
                        + "|refresh[-_.]?token|api[-_.]?key|private[-_.]?key"
                        + "|authorization|cookie).*");
    }
}
~~~

Quy tắc ví dụ tìm các key có tên liên quan đến password, client secret, token, API key, private key, authorization hoặc cookie. `ifKeyMatches` so khớp key không phân biệt chữ hoa/chữ thường trong API hiện hành.

Đây là một quy tắc bổ sung theo naming convention của hệ thống. Hãy điều chỉnh regex theo property thực tế, tránh quy tắc quá rộng làm che cả thông tin không nhạy cảm hoặc quá hẹp khiến một secret không được nhận diện.

### 4.1. Lọc theo key và value

Một số secret không thể nhận diện chỉ bằng tên key. Ví dụ, một property có tên chung `endpoint` nhưng giá trị chứa URI với userinfo hoặc token. `SanitizingFunction` có thể lọc theo value:

~~~java
@Bean
SanitizingFunction redactCredentialLikeValues() {
    return SanitizingFunction.sanitizeValue()
            .ifKeyContains("endpoint", "connection")
            .ifValueStringMatches(".*://[^/]*:[^/@]+@.*");
}
~~~

Các filter fluent được nối để mở rộng tập dữ liệu cần che: ví dụ này che khi key chứa `endpoint`/`connection` hoặc khi value khớp pattern URI. Không hiểu chuỗi filter là yêu cầu cả hai điều kiện phải cùng đúng. Regex URI cũng không bao phủ mọi cách mã hóa credential, query parameter hoặc định dạng kết nối; không dùng một biểu thức đơn lẻ làm bằng chứng rằng mọi URI nhạy cảm đều được phát hiện.

Nếu có một property source chuyên chứa secret, có thể dựa vào `SanitizableData.getPropertySource()` để che toàn bộ giá trị từ nguồn đó. Cách này hữu ích khi tên key không theo quy ước thống nhất, nhưng cần kiểm tra tên/loại PropertySource thực tế của môi trường.

### 4.2. SanitizingFunction không thay thế show-values

Ngay cả khi `show-values` được đặt thành `always` hoặc `when-authorized`, sanitization do custom `SanitizingFunction` áp dụng vẫn có hiệu lực. Điều này cho phép giữ một nhóm key luôn bị che, kể cả khi người dùng có quyền xem các giá trị cấu hình khác.

Ngược lại, nếu custom function không nhận diện một secret, không thể mặc định rằng secret đó sẽ luôn bị che trong mọi cấu hình `show-values`. Hãy giữ `never` làm chính sách mặc định và kiểm thử các key nhạy cảm quan trọng.

### 4.3. Khác biệt API theo phiên bản Spring Boot

`SanitizingFunction` có từ các phiên bản Spring Boot trước, nhưng các helper fluent như `ifKeyContains`, `ifKeyMatches` và `ifLikelyCredential` được bổ sung ở các phiên bản mới hơn, trong đó có Spring Boot 3.5.

Nếu module phải hỗ trợ release cũ, hãy đối chiếu API đúng với BOM đang dùng. Có thể triển khai trực tiếp functional interface bằng `SanitizableData.getKey()` và `withSanitizedValue()` nếu các method đó có trong phiên bản mục tiêu. Không sao chép code dùng helper mới vào một nhánh Spring Boot cũ mà chưa compile kiểm tra.

Ví dụ triển khai trực tiếp, không dùng helper fluent:

~~~java
import java.util.Locale;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacySanitizationConfiguration {

    @Bean
    SanitizingFunction sensitiveKeysSanitizer() {
        return data -> {
            String key = data.getKey().toLowerCase(Locale.ROOT);
            if (key.contains("client-secret")
                    || key.contains("access-token")
                    || key.endsWith(".password")
                    || key.endsWith(".api-key")) {
                return data.withSanitizedValue();
            }
            return data;
        };
    }
}
~~~

Đoạn code minh họa dùng `withSanitizedValue()`; hãy xác nhận method có trong phiên bản Spring Boot mục tiêu. Các `SanitizingFunction` tùy chỉnh được áp dụng theo thứ tự cho tới khi một function thay đổi giá trị, vì vậy cần tránh nhiều function có quy tắc xung đột hoặc kiểm tra chúng như một tập hợp.

## 5. Viết test cho sanitization của Actuator

Không nên chỉ nhìn một response trên môi trường local rồi kết luận đã che đúng. Hãy tạo test với một giá trị canary giả, sau đó xác nhận response không chứa canary và có giá trị thay thế đã che.

Ví dụ cấu hình test:

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public class CatalogClientProperties {

    private String accessToken;

    public String getAccessToken() {
        return accessToken;
    }

    public void setAccessToken(String accessToken) {
        this.accessToken = accessToken;
    }
}
~~~

Test endpoint với `show-values: never`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "catalog.client.access-token=actuator-test-secret-123",
        "management.endpoints.web.exposure.include=env,configprops",
        "management.endpoint.env.show-values=never",
        "management.endpoint.configprops.show-values=never"
})
@AutoConfigureMockMvc
class ActuatorSanitizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void envDoesNotExposeSecretValue() throws Exception {
        mockMvc.perform(get("/actuator/env/catalog.client.access-token"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("actuator-test-secret-123"))))
                .andExpect(content().string(containsString("******")));
    }

    @Test
    void configpropsDoesNotExposeSecretValue() throws Exception {
        mockMvc.perform(get("/actuator/configprops"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("actuator-test-secret-123"))));
    }
}
~~~

Test giả định `CatalogClientProperties` đã được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Nếu dùng `configprops` filter theo prefix, điều chỉnh URL và JSON assertion theo phiên bản Spring Boot. Không cần assert toàn bộ response; điều quan trọng là canary secret không xuất hiện.

### 5.1. Kiểm thử role của when-authorized

Với `show-values: when-authorized`, nên có ít nhất ba trường hợp:

| Người gọi | Kết quả mong đợi |
| --- | --- |
| Chưa xác thực | Bị Security chặn theo policy |
| Đã xác thực nhưng thiếu role `CONFIG_AUDITOR` | Endpoint có thể trả metadata nhưng giá trị secret vẫn bị che |
| Đã xác thực và có role `CONFIG_AUDITOR` | Có thể xem giá trị theo policy nếu không có SanitizingFunction áp dụng |

Test cần kiểm tra cả endpoint authorization và show-values. Nếu chỉ test người có role, ta có thể bỏ sót việc user thông thường cũng xem được secret.

## 6. Log ứng dụng không dùng sanitization của Actuator

Đây là ranh giới quan trọng nhất của bài. `SanitizingFunction` chỉ xử lý dữ liệu mà các Actuator endpoint hỗ trợ đưa qua sanitizer. Nó không chạy trên mọi lệnh:

~~~java
log.info("Catalog configuration: {}", catalogClientProperties);
log.debug("Resolved environment: {}", environment);
log.error("Catalog request failed: {}", exception.getMessage());
~~~

Các dòng như trên có thể làm lộ secret nếu `toString()` chứa field credential, nếu object chứa toàn bộ Environment hoặc nếu exception message chứa URL/header có thông tin xác thực.

Việc `/actuator/env` trả `******` không có nghĩa cùng property sẽ được che trong log. Nếu code ghi giá trị gốc ra log, log appender sẽ nhận giá trị gốc.

### 6.1. Không ghi secret ngay từ đầu

Cách tốt nhất là không đưa secret vào log message. Thay vì log token hoặc password, hãy log trạng thái cấu hình và thông tin chẩn đoán không nhạy cảm:

~~~java
log.info(
        "Catalog client initialized: credentialConfigured={}, timeoutMs={}",
        hasAccessToken,
        properties.getConnectTimeout().toMillis());
~~~

Ví dụ này cung cấp tín hiệu vận hành mà không ghi token. Nếu cần xác định cấu hình đang dùng, có thể log tên property, profile, tên nguồn cấu hình hoặc một mã cấu hình không nhạy cảm. Không log hash yếu của secret như một cách thay thế nếu hash đó có thể dùng để dò đoán hoặc liên kết credential.

### 6.2. Những dữ liệu không nên ghi log

Tránh ghi trực tiếp:

- `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`.
- Access token, refresh token, API key, client secret và password.
- Toàn bộ `Environment`, `PropertySource` hoặc object `@ConfigurationProperties` có field secret.
- HTTP request/response body có thể chứa credential hoặc dữ liệu cá nhân.
- URL có userinfo hoặc query parameter chứa key/token.
- Biến môi trường toàn bộ của process/container.
- Secret trong MDC, tracing baggage hoặc structured log key/value.
- Exception message nếu nó có thể chứa URL, header hoặc payload nhạy cảm.

Đặc biệt cẩn thận với HTTP wiretap và request/response logging filter. Một chế độ debug có thể ghi toàn bộ header và body; nếu cần bật tạm thời, hãy giới hạn môi trường, thời gian, endpoint và dữ liệu được capture.

### 6.3. Cẩn thận với toString() của configuration bean

Các thư viện sinh `toString()` tự động có thể đưa mọi field vào log. Ví dụ Lombok `@Data` hoặc `@ToString` có thể bao gồm field access token nếu không loại trừ.

Nếu dùng Lombok, loại secret khỏi `toString()`:

~~~java
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString
public class CatalogCredentials {

    private String clientId;

    @ToString.Exclude
    private String clientSecret;
}
~~~

Với class tự viết, hãy tạo `toString()` chỉ chứa các field an toàn hoặc không override nếu không cần. Không dùng log object như một cách nhanh để xem toàn bộ cấu hình.

### 6.4. Xử lý exception và URL

Một exception từ HTTP client có thể chứa URI đầy đủ hoặc một phần request. Nếu URI có userinfo hoặc token trong query string, log stack trace hoặc message có thể làm lộ secret.

Ưu tiên ghi:

- Loại exception.
- Mã lỗi hoặc status HTTP.
- Route template thay vì URL đầy đủ.
- Correlation ID hoặc trace ID không chứa credential.
- Tên dependency hoặc service ID nếu thông tin đó được phép công bố.

Nếu cần lưu stack trace để chẩn đoán, bảo đảm exception đã loại bỏ credential khỏi URL/header/body trước khi ghi. Không log `exception.getMessage()` một cách vô điều kiện.

## 7. Structured logging và redaction ở pipeline

Log có cấu trúc giúp hệ thống thu thập log xử lý từng field thay vì phải phân tích một chuỗi tự do. Spring Boot hỗ trợ các định dạng JSON như ECS, GELF và Logstash trong các phiên bản có structured logging.

Ví dụ bật Logstash JSON:

~~~yaml
logging:
  structured:
    format:
      console: logstash
      file: logstash
~~~

Nếu ứng dụng tự đưa các field vào JSON, có thể loại bỏ một số đường dẫn bằng `logging.structured.json.exclude`:

~~~yaml
logging:
  structured:
    json:
      exclude:
        - http.request.headers.authorization
        - http.request.headers.cookie
        - request.query.access_token
~~~

Tên path phải khớp với field thực tế được ghi vào JSON. Ví dụ trên chỉ có tác dụng nếu các field tương ứng tồn tại trong structured log. Nó không tự tìm và che mọi token nằm trong chuỗi `message`.

### 7.1. Exclude field không giống mask một phần chuỗi

`logging.structured.json.exclude` loại bỏ các member theo path. Nếu message đã chứa token như:

~~~text
Calling partner with access token abc123...
~~~

thì loại bỏ một field header không làm chuỗi message đó biến mất. Cần sửa code tạo log message hoặc áp dụng customizer/formatter phù hợp cho format đang dùng.

Spring Boot cung cấp `StructuredLoggingJsonMembersCustomizer` cho nhu cầu tùy chỉnh JSON nâng cao. Với Logback hoặc Log4j2, cũng có thể cấu hình encoder/layout/filter theo framework. Hãy kiểm tra output cuối cùng sau mọi bước format; không giả định một cấu hình exclude bao phủ tất cả log destination.

### 7.2. Defense in depth ở hệ thống thu thập log

Ngoài ứng dụng, pipeline thu thập log có thể có lớp redaction bổ sung trước khi lưu trữ hoặc hiển thị. Lớp này hữu ích khi một thư viện bên thứ ba vô tình ghi dữ liệu nhạy cảm.

Tuy nhiên, redaction sau khi thu thập chỉ là lớp bổ sung. Secret có thể đã đi qua stdout, agent, buffer, queue hoặc một kho lưu trữ trung gian trước khi bị che. Hãy giảm thiểu dữ liệu nhạy cảm ngay tại nguồn và giới hạn quyền đọc log, thời gian lưu giữ, quyền tải xuống và quyền truy vấn.

### 7.3. Tránh regex redaction không có kiểm thử

Một bộ lọc regex có thể không nhận diện được token đã encode, JSON lồng nhau, URL encoding hoặc format thay đổi. Regex quá rộng có thể xóa dữ liệu hữu ích; regex quá hẹp có thể để lọt secret.

Hãy ưu tiên cấu trúc field rõ ràng và allowlist dữ liệu được phép ghi. Nếu bắt buộc dùng regex, kiểm thử nhiều dạng dữ liệu thực tế và kiểm tra log sau khi đã đi qua encoder cùng pipeline.

## 8. Ghi log an toàn cho request HTTP

Trong ứng dụng Spring Cloud, request giữa các service thường mang header xác thực. Khi ghi log request, nên chọn field theo allowlist:

~~~java
log.info(
        "Outbound request: dependency={}, method={}, route={}, status={}, traceId={}",
        "catalog-service",
        method,
        "/api/catalog/{id}",
        statusCode,
        traceId);
~~~

Không ghi toàn bộ header map. Nếu cần ghi một số header kỹ thuật, hãy chọn rõ từng header an toàn như `Content-Type` hoặc một correlation ID đã được kiểm soát.

Đối với request inbound, ghi route template thay vì raw URL nếu query string có thể chứa dữ liệu nhạy cảm. Không ghi body mặc định; chỉ ghi field đã được duyệt và đã loại bỏ dữ liệu cá nhân/secret.

### 8.1. Không đưa secret vào MDC hoặc tracing baggage

MDC và tracing baggage thường được sao chép vào structured log hoặc trace exporter. Vì vậy:

- Chỉ đưa correlation ID, request ID và actor ID đã được phép vào MDC.
- Không đưa Authorization header, session token hoặc client secret vào MDC.
- Không đưa password hoặc dữ liệu nhạy cảm vào span attribute.
- Kiểm tra cấu hình export trace và quyền truy cập hệ thống observability.
- Dùng identifier giả danh nếu không cần lưu định danh trực tiếp.

Nếu một giá trị được xem là secret trong log message thì nó cũng là secret khi được thêm vào MDC hoặc tracing baggage.

## 9. Kiểm thử để chắc chắn log không chứa secret

Một test đơn giản có thể dùng Spring Boot `OutputCaptureExtension` để bắt log phát sinh trong test và xác nhận canary secret không xuất hiện.

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class CatalogLoggingSecurityTest {

    @Test
    void startupLogDoesNotContainClientSecret(CapturedOutput output) {
        String fakeSecret = "log-test-secret-456";

        CatalogStartupLogger logger =
                new CatalogStartupLogger(fakeSecret);

        logger.logConfigurationSummary();

        assertThat(output.getOut())
                .doesNotContain(fakeSecret);
        assertThat(output.getErr())
                .doesNotContain(fakeSecret);
    }
}
~~~

`CatalogStartupLogger` là class minh họa cần được thay bằng component thực tế đang ghi log trong ứng dụng. Test phải gọi đúng code path cần bảo vệ; chỉ tạo một chuỗi rồi không kích hoạt logger sẽ không kiểm tra được gì.

### 9.1. Kiểm thử cả message và exception

Bổ sung các tình huống:

- Startup log khi có credential.
- HTTP request log có Authorization/Cookie.
- Exception từ HTTP client có URI hoặc query parameter.
- Log debug khi bật wiretap.
- MDC/tracing baggage được chuyển vào structured log.
- Log ở nhánh retry, timeout và circuit breaker.
- Log khi cấu hình refresh hoặc bean được tạo lại.

Tìm canary secret trong cả stdout, stderr và file appender. Nếu ứng dụng gửi log tới agent hoặc hệ thống tập trung, kiểm tra bản ghi cuối cùng sau pipeline.

### 9.2. Kiểm thử sanitization của endpoint

Với `env` và `configprops`, kiểm tra response không chứa canary secret trong cả cấu hình `never` và `when-authorized` với người dùng thiếu role. Khi có custom `SanitizingFunction`, kiểm tra key riêng của ứng dụng cũng được che.

Không dùng một test thành công của Actuator để suy ra log an toàn. Hai đường dữ liệu cần bộ kiểm thử riêng.

## 10. Quy trình xử lý khi phát hiện secret đã bị ghi log

Nếu secret đã xuất hiện trong endpoint hoặc log:

1. Xác định loại credential và hệ thống mà nó cấp quyền.
2. Thu hồi hoặc xoay vòng credential theo quy trình của provider.
3. Xác định log xuất hiện ở stdout, file, agent, queue, kho tập trung, bản sao và backup nào.
4. Hạn chế quyền truy cập và tải xuống các bản ghi liên quan.
5. Xóa hoặc xử lý dữ liệu theo chính sách retention, pháp lý và khả năng kiểm toán.
6. Sửa nguồn phát sinh: property naming/sanitization, logger, request filter, exception hoặc MDC.
7. Thêm test hồi quy dùng canary value.
8. Kiểm tra các hệ thống khác có nhận cùng credential hay không.

Chỉ xóa log ở một nơi không bảo đảm secret đã biến mất khỏi bản sao hoặc hệ thống downstream. Cần đánh giá phạm vi lan truyền trước khi kết luận sự cố đã được xử lý.

## 11. Lỗi thường gặp và cách tránh

1. **Cho rằng Actuator che cả log:** `SanitizingFunction` không lọc SLF4J, Logback hoặc Log4j2.
2. **Bật `show-values: always` để debug:** giữ `never` hoặc dùng `when-authorized` với role hẹp.
3. **Không khai báo `roles` khi dùng `when-authorized`:** mọi người dùng HTTP đã xác thực có thể được xem giá trị gốc theo mặc định.
4. **Quên JMX:** JMX được xem là authorized trong cơ chế `when-authorized`; cần bảo vệ MBean server riêng.
5. **Chỉ bảo vệ endpoint bằng authentication:** còn cần giới hạn exposure và quyền đọc giá trị.
6. **Tin quy tắc key mặc định phát hiện mọi secret:** thêm naming convention riêng và test các key nội bộ.
7. **Dùng custom sanitizer như bộ lọc log:** chỉ áp dụng cho dữ liệu Actuator tương ứng.
8. **Log toàn bộ configuration bean:** `toString()` có thể đưa password hoặc token ra log.
9. **Log toàn bộ HTTP header/body:** chỉ ghi allowlist field cần thiết.
10. **Ghi exception message không kiểm tra:** message có thể chứa URL, credential hoặc payload.
11. **Đưa token vào MDC/tracing baggage:** các field này có thể được xuất ra nhiều hệ thống.
12. **Chỉ redaction ở log collector:** secret đã đi qua các buffer hoặc hệ thống trung gian trước khi được che.
13. **Dùng regex mà không test:** có thể bỏ sót format hoặc xóa nhầm dữ liệu.
14. **Không kiểm tra file appender và log tập trung:** stdout an toàn không chứng minh mọi destination đều an toàn.

## 12. Quy trình triển khai bảo vệ đồng bộ

Khi cấu hình một ứng dụng Spring Cloud:

1. Liệt kê password, token, API key, client secret, private key, cookie và connection string.
2. Cung cấp secret từ secret manager hoặc nguồn được kiểm soát; tránh commit giá trị thật.
3. Giữ `management.endpoint.env.show-values` và `management.endpoint.configprops.show-values` ở `never` làm mặc định.
4. Chỉ dùng `when-authorized` khi có nhu cầu rõ ràng; khai báo role cụ thể và cấu hình Security filter chain.
5. Kiểm soát JMX độc lập với HTTP.
6. Bổ sung `SanitizingFunction` cho key hoặc source đặc thù.
7. Không log raw Environment, ConfigurationProperties, header, body, URL có credential hoặc exception message chưa kiểm tra.
8. Thiết kế log theo allowlist và structured field.
9. Bổ sung redaction ở encoder/pipeline như lớp phòng vệ bổ sung.
10. Viết test canary cho Actuator response và log output.
11. Kiểm tra stdout, file, agent, queue, log store và trace exporter.
12. Xoay vòng secret nếu phát hiện dữ liệu đã bị lộ.

**Điểm cần ghi nhớ:** `env` và `configprops` của Spring Boot Actuator mặc định che giá trị; `show-values` và `SanitizingFunction` điều khiển việc hiển thị dữ liệu của các endpoint này. Log ứng dụng là bề mặt độc lập: cách an toàn nhất là không ghi secret, chỉ log field được phép, kiểm soát header/body/exception/MDC và kiểm thử output ở mọi destination. Bảo vệ đồng thời cấu hình, endpoint quản trị và log giúp giảm nguy cơ lộ credential trong **SPRING_CLOUD_CORE**.

## Tài liệu tham khảo

- [Spring Boot — Actuator Endpoints: Sanitize Sensitive Values](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Customizing Sanitization](https://docs.spring.io/spring-boot/how-to/actuator.html)
- [Spring Boot API — SanitizingFunction](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/endpoint/SanitizingFunction.html)
- [Spring Boot — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
