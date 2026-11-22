# Không ghi mật khẩu, Bearer token, cookie hoặc dữ liệu cá nhân vào log

## 1. Mục tiêu bảo mật log trong Spring Security Servlet

Một ứng dụng Spring MVC cần log để theo dõi lỗi, hiệu năng, sự kiện xác thực, quyết định phân quyền và các thay đổi quan trọng. Tuy nhiên, log thường đi qua nhiều hệ thống: JVM console, container stdout, file, collector, APM, SIEM, dashboard, alert, ticket và backup. Một giá trị nhạy cảm bị ghi nhầm sẽ tạo ra nhiều bản sao nằm ngoài cơ sở dữ liệu nghiệp vụ.

Nguyên tắc: **chỉ log những trường thật sự cần thiết và đã được cho phép. Không log mật khẩu, Bearer token, cookie, session ID hoặc dữ liệu cá nhân không cần thiết.** Ưu tiên thiết kế event theo allowlist thay vì ghi toàn bộ request rồi tìm cách che bằng regex.

Bài học này áp dụng cho Java 17+, Spring Boot 3.x, Spring Security 6.x trên Servlet stack. Sau bài học, người đọc có thể phân loại dữ liệu nhạy cảm, thiết kế security audit events an toàn, tránh lộ dữ liệu qua logging framework và HTTP middleware, viết test bằng MockMvc/Logback và vận hành toàn tuyến từ application tới collector.

## 2. Vì sao log lại có rủi ro?

Credential có thể cho phép một chủ thể khác thực hiện thao tác nếu bị đánh cắp. Ví dụ, access token theo Bearer scheme thường được sử dụng chỉ bằng việc sở hữu token hợp lệ; session cookie có thể đại diện cho một phiên đã đăng nhập; password có rủi ro đặc biệt cao khi người dùng sử dụng lại.

| Dữ liệu | Rủi ro |
| --- | --- |
| Password, OTP, recovery code | Có thể hỗ trợ chiếm tài khoản |
| Bearer access/refresh token | Có thể bị dùng lại trong phạm vi/thời gian còn hiệu lực |
| Authorization: Basic | Base64 chỉ là encoding, không phải encryption |
| Cookie, Set-Cookie, JSESSIONID | Có thể hỗ trợ chiếm phiên |
| API key, client secret | Truy cập trái phép tới API/service |
| Email, số điện thoại, địa chỉ | Phishing hoặc vi phạm quyền riêng tư |
| JWT claims, ID khách hàng, route | Có thể liên kết với cá nhân hoặc hoạt động nhạy cảm |
| Query, form data, file name | Có thể chứa token, dữ liệu tìm kiếm, thông tin riêng tư |

Log thường có lượng người được xem và số nơi lưu trữ rộng hơn database. Một token có thể đi từ terminal sang aggregator, ảnh chụp, cảnh báo hoặc ticket. **Ẩn dữ liệu trên dashboard không đồng nghĩa đã xóa bản gốc khỏi collector và backup.**

## 3. Nguồn rò rỉ không chỉ là log.info của ứng dụng

Các dữ liệu nhạy cảm có thể bị ghi ở:

- Application logger tự in password, body, headers, query, Principal hoặc Authentication.
- Spring Security DEBUG/TRACE hoặc custom authentication event listener in toàn bộ event.
- Servlet request logging filter bật ghi payload hoặc headers.
- HTTP client wire logging, interceptors hoặc exception reporting.
- Tomcat, Nginx, Envoy, ingress, CDN/WAF access log có raw URI và query.
- SQL logging với bind parameter chứa dữ liệu người dùng.
- APM, tracing, span attributes, exception events, MDC và baggage.
- CI test report, console, ticket hỗ trợ, export và alert.

Không đủ để sửa duy nhất code controller. Cần kiểm tra từng lớp tự tạo hoặc chuyển tiếp log.

~~~text
HTTP client
    |
    v
CDN / gateway / ingress
    |
    v
Servlet container
    |
    v
Spring Security filters -> Spring MVC controller/service
    |
    +--> application logs
    +--> exception reporter
    +--> APM and traces
    |
    v
log collector -> storage -> dashboard / alert / backup
~~~

Ở mỗi bước hãy hỏi: dữ liệu được capture vào lúc nào, ai xem được, có thể export ra đâu, giữ trong bao lâu và khi cần xóa thì xử lý thế nào?

## 4. Không ghi các trường nào?

**Credential và token cần tránh tuyệt đối theo mặc định:** password, passwordConfirmation, OTP, recovery code, MFA secret, reset token, API key, private key, access token, refresh token, client secret, Authorization, Proxy-Authorization, Cookie, Set-Cookie, JSESSIONID.

**Không serialize nguyên object:** HttpServletRequest, HttpHeaders, Authentication, SecurityContext, Jwt, OAuth2User, UserDetails hoặc request/response DTO chứa dữ liệu chưa duyệt. Một toString() có thể chứa password hash, token claims, email, authorities hoặc details. Đừng dựa vào giả định rằng mọi implementation đều che credentials.

**Dữ liệu cá nhân chỉ có thể ghi khi thật cần và được kiểm soát:** email, tên, số điện thoại, địa chỉ, IP, user ID, tenant ID, subject, document ID, search terms, filename, HTTP Referer. UUID và hash email có thể vẫn là dữ liệu liên kết được với cá nhân.

**Exception message chưa mặc nhiên an toàn.** Validation exception có thể chứa rejected value; SQL exception chứa query; HTTP exception chứa URL query; custom exception có thể nối raw input.

## 5. Những mẫu code phải tránh

Mã dưới đây là ví dụ về lỗi, không phải code để áp dụng:

~~~java
// SAI: ghi mật khẩu do người dùng nhập.
log.info("user={} password={}", username, submittedPassword);

// SAI: ghi header có credential.
log.debug("Authorization={}",
    request.getHeader("Authorization"));

// SAI: ghi mọi header hoặc toàn bộ request.
log.debug("Headers={}", headers);

// SAI: body có thể chứa secret hoặc PII.
log.info("Request body={}", body);

// SAI: không kiểm soát toString của Authentication.
log.info("Authentication={}", authentication);

// SAI: raw URI/query có thể chứa token hoặc email.
log.info("Request={} query={}",
    request.getRequestURI(), request.getQueryString());
~~~

Parameter substitution trong logging framework giúp format/hiệu năng, **không tự làm sạch đối số**. Nếu đối số chứa Bearer token thì log vẫn có token.

Bộ lọc regex tìm từ password hoặc Bearer thường bỏ sót trường mới, custom header, escaped JSON, URL encoding, Unicode, token trong path hoặc exception. Redaction có thể là lớp bổ sung, không phải cơ chế phòng vệ chính.

## 6. Dùng allowlist schema cho sự kiện vận hành

Thay vì tạo event từ raw request, chỉ cho phép một tập trường:

~~~text
eventCode=AUTHENTICATION_REJECTED
outcomeCode=DENIED
reasonCode=BAD_CREDENTIALS
requestId=generated-by-server
httpStatus=401
routeTemplate=/api/login
durationMs=14
~~~

Các trường eventCode, outcomeCode, reasonCode phải được quyết định bởi logic server, không lấy nguyên chuỗi do client gửi. requestId nên được tạo ở server hoặc được xác thực cẩn thận theo trust boundary; routeTemplate an toàn hơn raw URL trong nhiều trường hợp.

Định nghĩa thông điệp log theo **tập trường cho phép**:

~~~text
ALLOWED:
  eventCode, outcomeCode, reasonCode
  requestId, status, durationMs
  httpMethod, approvedRouteTemplate

DISALLOWED AS RAW VALUES:
  Authorization, Cookie, Set-Cookie
  requestBody, responseBody
  HttpServletRequest, Authentication, Jwt
  raw URL and query string
  uncontrolled exception message
~~~

Không phải mọi trường trong ALLOWED đều cần có ở mỗi log. Hãy ghi đúng những gì phục vụ việc điều tra và tránh tăng độ nhạy cảm không cần thiết.

## 7. Java 17 độc lập: formatter không nhận secret

File SafeEventDemo.java:

~~~java
public class SafeEventDemo {

    enum EventCode {
        AUTHENTICATION_REJECTED,
        ACTION_ACCEPTED
    }

    enum Outcome {
        DENIED,
        SUCCESS
    }

    static String format(EventCode event, Outcome outcome) {
        return "event=" + event.name()
            + " outcome=" + outcome.name();
    }

    public static void main(String[] args) {
        System.out.println(
            format(
                EventCode.AUTHENTICATION_REJECTED,
                Outcome.DENIED
            )
        );
        System.out.println(
            format(
                EventCode.ACTION_ACCEPTED,
                Outcome.SUCCESS
            )
        );
    }
}
~~~

Chạy:

~~~bash
javac SafeEventDemo.java
java SafeEventDemo
~~~

Stdout chính xác:

~~~text
event=AUTHENTICATION_REJECTED outcome=DENIED
event=ACTION_ACCEPTED outcome=SUCCESS
~~~

Hàm nhận hai enum chứ không nhận password, token hay request body. Đây là ví dụ cho hợp đồng logging an toàn; sản phẩm thật nên dùng framework logging và audit storage phù hợp, không coi System.out là hệ thống audit.

## 8. Mẫu Spring Boot 3: tạo request ID, audit event và REST endpoint

Dự án Spring Boot 3.x sử dụng Java 17+ và những dependency trong build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Các file trong package demo.safelog. Để chạy cần plugin Spring Boot, dependency management và Gradle wrapper của dự án.

### 8.1. Application

File src/main/java/demo/safelog/SafeLogApplication.java:

~~~java
package demo.safelog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLogApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeLogApplication.class, args);
    }
}
~~~

### 8.2. RequestIdFilter: tự tạo ID, dọn MDC

File src/main/java/demo/safelog/RequestIdFilter.java:

~~~java
package demo.safelog;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String id = UUID.randomUUID().toString();
        MDC.put("requestId", id);
        response.setHeader("X-Request-ID", id);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Filter dùng UUID do server tạo. Không đưa trực tiếp X-Request-ID từ client vào MDC: client có thể dùng giá trị rất dài hoặc ký tự điều khiển để gây log injection. Dọn MDC trong finally giúp tránh lẫn ID giữa requests trên servlet thread được tái sử dụng. Nếu có @Async, Executor hoặc dispatch bất đồng bộ, cần xử lý propagation riêng; MDC không tự theo mọi thread.

### 8.3. SafeAuditService: chỉ nhận enum

File src/main/java/demo/safelog/SafeAuditService.java:

~~~java
package demo.safelog;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;

@Service
public class SafeAuditService {

    private static final Logger log =
        LoggerFactory.getLogger(SafeAuditService.class);

    public enum EventCode {
        ACTION_ACCEPTED,
        AUTHENTICATION_REJECTED,
        AUTHORIZATION_DENIED
    }

    public enum OutcomeCode {
        SUCCESS,
        DENIED
    }

    public void record(EventCode event, OutcomeCode outcome) {
        log.info(
            "security_event={} outcome={} requestId={}",
            event.name(),
            outcome.name(),
            MDC.get("requestId")
        );
    }
}
~~~

Logger không có tham số HttpServletRequest, body, header, Authentication hoặc Jwt. Nó chỉ nhận mã sự kiện đã định nghĩa sẵn và request ID do server tạo. Có thể chuyển key=value sang JSON structured logging, nhưng encoder JSON vẫn phải theo schema cho phép.

### 8.4. SecurityConfig bảo vệ controller

File src/main/java/demo/safelog/SecurityConfig.java:

~~~java
package demo.safelog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/health")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/api/actions")
                    .hasRole("OPERATOR")
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

Cấu hình ví dụ đặt authorization cho endpoint và giữ các security filters mặc định được HttpSecurity cung cấp theo framework version. Phần test dùng @WithMockUser và csrf() để kiểm tra controller/safe logging; **không kiểm thử password thật hoặc JWT verification**. Trong một ứng dụng triển khai thực, cần chọn và cấu hình authentication mechanism cụ thể (form, Basic, Resource Server...) và chính sách session/CSRF tương ứng. Không tắt authentication/CSRF chỉ để làm test pass.

### 8.5. Controller không ghi nội dung do client gửi

File src/main/java/demo/safelog/ActionController.java:

~~~java
package demo.safelog;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import demo.safelog.SafeAuditService.EventCode;
import demo.safelog.SafeAuditService.OutcomeCode;

@RestController
@RequestMapping("/api")
public class ActionController {

    private final SafeAuditService audit;

    public ActionController(SafeAuditService audit) {
        this.audit = audit;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @PostMapping("/actions")
    public ResponseEntity<Map<String, String>> action(
            @RequestBody ActionInput input) {

        // Không đưa input.label hoặc object input vào log.
        audit.record(EventCode.ACTION_ACCEPTED, OutcomeCode.SUCCESS);

        return ResponseEntity
            .status(HttpStatus.ACCEPTED)
            .body(Map.of("status", "accepted"));
    }

    public record ActionInput(String label) {}
}
~~~

Endpoint minh họa chỉ xác nhận request, chưa có database/hàng đợi. Không coi response 202 là bảo đảm công việc đã được lưu bền vững. Trong sản phẩm thật cần validation, permission trên đối tượng và nghiệp vụ tương ứng.

### 8.6. Logging pattern có correlation ID

Trong src/main/resources/application.properties:

~~~properties
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.pattern.console=%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level requestId=%X{requestId} %logger{36} - %msg%n
~~~

Pattern chỉ định format message và requestId; **không tự che được bí mật nếu một logger khác đã đưa credential vào message**.

## 9. Test chống leak bằng MockMvc và ListAppender

Test dưới đây sử dụng các marker **giả lập** trong request body và một custom header, rồi capture riêng logger SafeAuditService. Không dùng credential khách hàng thật.

File src/test/java/demo/safelog/SafeLoggingTest.java:

~~~java
package demo.safelog;

import java.util.stream.Collectors;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;

import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeLoggingTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "test-user", roles = "OPERATOR")
    void loggerDoesNotPrintClientInput() throws Exception {
        Logger logger =
            (Logger) LoggerFactory.getLogger(SafeAuditService.class);

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        try {
            mvc.perform(post("/api/actions")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"label\":\"SYNTHETIC_BODY_MARKER\"}")
                    .header("X-Debug-Marker", "SYNTHETIC_HEADER_MARKER"))
                .andExpect(status().isAccepted());

            String captured = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));

            assertTrue(captured.contains("security_event=ACTION_ACCEPTED"));
            assertFalse(captured.contains("SYNTHETIC_BODY_MARKER"));
            assertFalse(captured.contains("SYNTHETIC_HEADER_MARKER"));
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

Test có SpringBootTest, AutoConfigureMockMvc, Spring Security Test, Logback ListAppender. @WithMockUser tạo Authentication giả lập; csrf() thêm token cho request POST trong MockMvc.

**Giới hạn:** appender chỉ capture SafeAuditService, không có Tomcat access log, proxy, APM, collector hoặc mọi logger framework. Do đó test pass chỉ chứng minh đường log đã được kiểm tra, **không chứng minh toàn pipeline sạch mọi secret**.

Chạy khi dự án có Gradle wrapper:

~~~bash
./gradlew test --tests demo.safelog.SafeLoggingTest
~~~

Kết quả thực tế phụ thuộc dependency/version/cấu hình. Nếu logging backend không phải Logback, cần test adapter tương đương.

## 10. Authentication, JWT và exception messages

Spring Security Authentication có thể chứa principal, credentials, authorities và details. Trong Resource Server, Jwt có claims như sub, email, aud, scopes và dữ liệu tùy biến. **Không log Authentication/Jwt object nguyên vẹn**:

~~~java
// KHÔNG NÊN:
log.info("Authentication={}", authentication);
log.debug("Context={}",
    SecurityContextHolder.getContext());
log.info("Claims={}", jwt.getClaims());
log.warn("Failure={}", exception.getMessage());
~~~

Có thể ghi event code và reason code an toàn do server phân loại:

~~~text
security_event=AUTHENTICATION_REJECTED
reasonCode=INVALID_CREDENTIALS
outcome=DENIED
requestId=generated-by-server
~~~

Một exception message có thể chứa rejected input, SQL query, path hoặc header. Nếu cần stack trace, phải xem nguồn tạo message và quyền truy cập hệ thống error reporting. Không in exception object tự động nếu chưa biết thông tin nào có thể bị đính kèm.

## 11. HTTP headers, URL và query thường bị quên

Các header cần tránh log giá trị: Authorization, Proxy-Authorization, Cookie, Set-Cookie, X-Api-Key, X-Auth-Token, X-CSRF-TOKEN, X-XSRF-TOKEN. Referer, User-Agent, X-Forwarded-For và tracing baggage có thể chứa thông tin cá nhân hoặc input bị thao túng.

Tên header không phân biệt hoa thường; regex chỉ tìm một cách viết có thể bỏ sót.

Ví dụ URL có thông tin nhạy cảm:

~~~text
GET /users/alice@example.org
GET /reset?token=synthetic-value
GET /search?q=private-information
~~~

Ưu tiên log method/status và **route template** thay vì raw URL:

~~~text
method=GET route=/users/{userId} status=200
method=GET route=/reset status=400
method=GET route=/search status=200
~~~

Route template chỉ có sau khi MVC đã chọn handler; request không match có thể dùng category UNKNOWN. Không cắt raw path một cách tùy tiện rồi mặc định rằng đã loại PII.

Một proxy có thể ghi query trước khi request vào JVM. Không đưa credential vào URL ngay từ thiết kế client.

## 12. Log injection và nguồn input không tin cậy

Custom header, User-Agent, Referer, query và request body có thể chứa newline hoặc control characters. Nếu log nguyên chuỗi, attacker có thể tạo log giả giống một sự kiện khác.

Biện pháp:

1. Ưu tiên mã sự kiện ổn định do server tạo.
2. Không log raw input không cần thiết.
3. Khi phải ghi một field do client cung cấp, giới hạn độ dài và tập ký tự.
4. Dùng structured encoder có escaping đúng.
5. Không thực thi shell/SQL hoặc render HTML chưa escape dựa trên log.
6. Kiểm soát log volume/cardinality để không bị bơm dữ liệu.

Structured JSON giúp schema/escaping nhưng **không tự mã hóa hoặc che token** nếu token vẫn nằm trong một field.

## 13. MDC và tracing: chỉ đưa metadata được duyệt

MDC có thể lan sang nhiều bản ghi. Không đưa Authorization, Cookie hoặc email vào MDC:

~~~java
// Phù hợp hơn:
MDC.put("requestId", UUID.randomUUID().toString());

// Không nên:
MDC.put("cookie", request.getHeader("Cookie"));
MDC.put("authorization", request.getHeader("Authorization"));
~~~

OpenTelemetry/APM có thể capture span attributes, baggage, headers và exception events. Phải kiểm tra cấu hình riêng. Với @Async, Executor hoặc xử lý bất đồng bộ, MDC không tự lan mọi thread; chỉ truyền requestId/metadata được phê duyệt bằng context propagation có kiểm soát.

## 14. Audit có cần định danh tác nhân không?

Một sự kiện đổi quyền có thể cần biết người thực hiện. Nhưng đừng mặc định phải ghi email, tên thật hoặc toàn bộ JWT.

Cân nhắc ID nội bộ, issuer+subject khi policy cho phép, hoặc pseudonymous ID được bảo vệ bởi hệ thống ánh xạ riêng. Nếu dùng HMAC với khóa bí mật để liên kết sự kiện, cần quản lý khóa và nhớ rằng pseudonymous identifier vẫn có thể liên kết tới cá nhân.

**SHA-256(email) không tự là ẩn danh**: email dễ bị thử từ điển, hash ổn định còn cho phép liên kết hoạt động.

Ví dụ sự kiện đã giảm thiểu dữ liệu:

~~~json
{
  "eventCode": "ROLE_CHANGED",
  "outcome": "SUCCESS",
  "requestId": "server-id",
  "actorRef": "approved-internal-reference",
  "targetType": "USER_ACCOUNT"
}
~~~

Security audit có thể có RBAC và retention khác operational logs, nhưng cả hai đều không cần password hoặc session cookie.

## 15. Authentication failure events của Spring Security

Spring Security có cơ chế sự kiện xác thực tùy AuthenticationEventPublisher và manager configuration. Một listener có thể ghi lý do thất bại theo mã cố định, nhưng không nên serialize toàn event hoặc exception.

Phần listener khái quát:

~~~java
@EventListener
public void onFailure(AbstractAuthenticationFailureEvent ignored) {
    audit.record(
        SafeAuditService.EventCode.AUTHENTICATION_REJECTED,
        SafeAuditService.OutcomeCode.DENIED
    );
}
~~~

Đây chỉ là method minh họa đặt trong Spring-managed component với imports/bean phù hợp. Không khẳng định mọi lỗi HttpFirewall, Resource Server hoặc proxy sẽ phát loại event này. Kiểm tra event publisher thực tế và không gọi getException().getMessage() vào log một cách mù quáng.

## 16. Kiểm tra toàn bộ pipeline vận hành

| Tầng | Điều cần kiểm tra |
| --- | --- |
| Frontend/mobile | Không in token, password vào console, crash report |
| CDN, WAF, gateway | Request body/header capture, access logs |
| Reverse proxy/ingress | Raw URI/query, Cookie, Authorization |
| Servlet container | Access logs, request dump filters, error logs |
| Spring Security | TRACE/DEBUG, authentication events, custom filters |
| Application | Raw DTOs, Authentication/Jwt, request/response logging |
| HTTP clients | Wire logging, outbound Authorization/API key |
| ORM/JDBC | SQL parameters chứa PII |
| APM/Tracing | Span attributes, baggage, error context |
| Collector | Scrubbing/drop rules, export và backup |
| Dashboard | Access control, downloads, sharing, retention |
| CI/Support | Test output, ticket/screenshot, raw diagnostic files |

Một canary test hữu ích có thể gửi các marker giả vào body, headers, query và exception, rồi tìm chúng ở log storage. **Không có marker trong một test không chứng minh mọi dạng dữ liệu nhạy cảm đều không thể lọt ra**. Kết hợp source review, cấu hình collectors và kiểm tra định kỳ.

## 17. Quyền truy cập, retention và ứng phó sự cố

Chính sách logging cần quy định: mục đích, trường được phép, người xem, quyền tải/export, mã hóa, nơi chuyển dữ liệu, thời gian lưu và quy trình xóa. Không có thời hạn retention cố định phù hợp mọi tổ chức; lựa chọn dựa trên mục đích, rủi ro, hợp đồng và nghĩa vụ pháp lý.

Nếu phát hiện secret đã vào log:

1. Ngừng nguồn phát sinh bằng thay đổi code/config có kiểm soát.
2. Xác định loại secret, khoảng thời gian và các bản sao ở collector, dashboard, alert, backup.
3. Revoke/rotate/invalidate token, API key, session hoặc credential theo mức rủi ro.
4. Giới hạn quyền truy cập raw logs, kiểm tra lịch sử xem và export.
5. Xử lý/xóa bản sao theo chính sách; masking ở dashboard không đủ.
6. Đánh giá nghĩa vụ bảo mật và thông báo liên quan dữ liệu cá nhân.
7. Giám sát bất thường bằng telemetry được phép.
8. Bổ sung automated tests và quy tắc review để phòng tái phát.

Không đính kèm nguyên bản log có credential thật vào ticket chung. Chỉ chia sẻ bản đã làm sạch; nếu cần giữ bằng chứng, dùng kênh điều tra truy cập hạn chế.

## 18. Những nhầm lẫn cần tránh

**“Log ở DEBUG không sao.”** DEBUG có thể được bật tạm rồi quên tắt; dữ liệu vẫn tới storage.

**“JWT có chữ ký nên có thể in.”** JWT vẫn là Bearer credential, claims có thể đọc được.

**“Cookie chỉ là identifier.”** Session ID có thể đại diện quyền truy cập một phiên.

**“Regex mask mọi chuỗi Bearer là đủ.”** Secret còn có thể nằm trong header tùy biến, query, body, exception hoặc encoding khác.

**“Chỉ không log body là xong.”** Raw URI, Authorization, Cookie, JDBC và APM vẫn có thể rò.

**“Hash email không còn là dữ liệu cá nhân.”** Hash có thể bị liên kết và thử từ điển.

**“Test ListAppender đã chứng minh production an toàn.”** Nó chỉ thấy logger mà test bắt, không quan sát proxy/container/collector.

**“Structured JSON tự làm sạch secret.”** JSON format không loại bỏ dữ liệu nhạy cảm nếu code vẫn truyền raw values.

**“Audit phải ghi đủ principal object.”** Audit cần các trường tối thiểu phục vụ mục đích, không cần credential.

## 19. Checklist trước khi merge hoặc bật log production

- [ ] Không có password, OTP, access/refresh token, API key hay session cookie trong log arguments.
- [ ] Không serialize HttpServletRequest, HttpHeaders, Authentication, Jwt hoặc SecurityContext.
- [ ] Raw request body, query, path và exception message được loại khỏi logger chung.
- [ ] Event, outcome, reason code do server quyết định theo allowlist.
- [ ] Request ID không bị client thao túng; MDC dọn trong finally.
- [ ] Không đưa secret/PII không cần thiết vào tracing attributes hoặc baggage.
- [ ] Cấu hình Spring Security, HTTP wire, SQL bind logging đã được kiểm tra.
- [ ] Gateway và Servlet access logs không ghi raw credential.
- [ ] Có regression tests bằng marker giả trong application logger và pipeline.
- [ ] Audit có purpose, RBAC, encryption, retention và export policy.
- [ ] Có quy trình revoke/rotate và xử lý bản sao nếu secret bị log nhầm.

## 20. Tự kiểm tra và kết luận

**Câu hỏi 1.** Vì sao Authorization: Bearer là dữ liệu tuyệt đối không nên ghi giá trị?

Vì nó là credential có thể dùng để gọi API trong phạm vi hiệu lực. Ghi vào log tạo thêm bản sao có thể bị truy cập trái phép.

**Câu hỏi 2.** Nếu ứng dụng không log request body nhưng proxy ghi raw URL thì đã an toàn chưa?

Chưa. URL/query có thể chứa email, reset token hoặc thông tin riêng tư; phải sửa cả cấu hình proxy và thiết kế client.

**Câu hỏi 3.** Khi muốn biết ai đổi role, có bắt buộc ghi email?

Không. Có thể dùng ID nội bộ hoặc pseudonymous reference đã được phê duyệt, audit storage có quyền truy cập và retention phù hợp.

**Câu hỏi 4.** Vì sao cần dùng allowlist event codes?

Nó giảm khả năng raw request input được truyền vào logger, giúp schema ổn định và dễ kiểm thử.

**Câu hỏi 5.** Vì sao phải kiểm tra cả MDC, APM và collector?

Vì chúng có thể tự sao chép metadata, headers hoặc exception data ngay cả khi logger nghiệp vụ an toàn.

**Kết luận:** Với Spring Security Servlet, không ghi mật khẩu, Bearer token, cookie hoặc dữ liệu cá nhân không cần thiết vào application logs, access logs, audit, exception hay traces. Ghi **event code, outcome, reason code, route template và request ID an toàn**, thiết kế allowlist từ nguồn phát, dùng test synthetic markers, kiểm tra toàn pipeline và bảo vệ log storage bằng quyền truy cập/retention/incident response rõ ràng.
