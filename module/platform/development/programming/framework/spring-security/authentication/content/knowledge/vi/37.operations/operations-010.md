# Kiểm soát log DEBUG, TRACE và dữ liệu nhạy cảm khi điều tra sự cố Spring Security

## 1. Mục tiêu: điều tra được lỗi mà không tạo thêm sự cố rò rỉ

Khi ứng dụng Spring Security gặp lỗi “đúng mật khẩu vẫn không đăng nhập được”, HTTP 401/403 bất thường, redirect vòng lặp hoặc JWT/LDAP xác thực lỗi, việc đầu tiên của nhiều nhóm là đổi mức log từ `INFO` sang `DEBUG` hoặc `TRACE`. Điều này có thể giúp tìm nhanh filter chain, authentication manager, CSRF và authorization decision. Nhưng **log là một nơi lưu trữ dữ liệu**: bật log quá rộng có thể đưa cookie phiên, Bearer token, password, mã OTP, API key, session ID, email, tham số URL và stack trace nhạy cảm vào console, file, cloud logging hoặc hệ thống giám sát.

**Chủ đề Vận hành này yêu cầu cân bằng hai mục tiêu:**

1. **Khả năng quan sát (observability):** biết request đi qua filter nào, authentication/authorization thất bại vì đâu, phiên/IdP/DB có vấn đề hay không.
2. **Giảm lộ lọt (data minimization):** chỉ ghi các sự kiện, mã kết quả và metadata **được cho phép**, không ghi raw credentials, token hay payload do người dùng cung cấp.

Một nguyên tắc cần nhớ: **DEBUG/TRACE không mặc nhiên an toàn**; thứ tự ưu tiên là **metric và sự kiện audit tối thiểu → log có cấu trúc của ứng dụng → DEBUG theo logger cụ thể, có thời hạn → TRACE chỉ trong môi trường cô lập sau khi đánh giá rủi ro**. Bật DEBUG không được coi là lý do bỏ qua chính sách bảo mật dữ liệu.

**Phạm vi:** Spring Boot **3.5.x**, Spring Security **6.5.x**, Java **17+**, ứng dụng Servlet; một phần cách xử lý vẫn áp dụng cho Spring Security 7 hoặc WebFlux nhưng tên class/logger, mức chi tiết và filter chain cần đối chiếu đúng phiên bản. Có ví dụ Maven/Java có thể chạy, kiểm thử log bằng JUnit và Logback, một chương trình Java thuần minh họa allowlist cùng runbook xử lý sự cố.

## 2. Phân biệt các cấp log với debug mode

| Mức | Nên ghi gì | Rủi ro nếu áp quá rộng |
| --- | --- | --- |
| `ERROR` | Lỗi dịch vụ cần can thiệp, sự kiện không thể hoàn tất | Stack trace/message có thể chứa secrets |
| `WARN` | Sự kiện bất thường, từ chối authentication có ý nghĩa | PII, username enumeration, noise do attacker gây |
| `INFO` | Audit đã chuẩn hóa, trạng thái vận hành, thay đổi cấu hình quan trọng | Quá nhiều dữ liệu hay duy trì lâu |
| `DEBUG` | Đường đi filter, quyết định config, thông tin phục vụ debug | URL, nguyên nhân nội bộ, danh tính hoặc context |
| `TRACE` | Bước thực thi chi tiết hơn của thư viện/framework | Lượng log rất lớn, chứa thông tin nhạy cảm tùy logger |

**Mức log không phải nhãn độ nhạy.** Một developer có thể vô tình ghi password ở `INFO`, hoặc một framework TRACE chỉ ghi tên class. Luôn đánh giá **nội dung thực tế** ở logger và phiên bản đang dùng.

### 2.1. Bốn cách bật log thường bị nhầm

| Cách | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| `logging.level.org.springframework.security=DEBUG` | Tăng mức cho cả package Spring Security | Chỉ dùng lab hoặc incident đã kiểm phạm vi |
| `logging.level.org.springframework.security.web.FilterChainProxy=DEBUG` | Tăng mức cho một logger filter chain | Ưu tiên cách khoanh vùng để điều tra chain |
| Spring Boot `--debug` / `debug=true` | Bật thêm một **tập logger** của Boot, không phải toàn bộ logger trên hệ thống | Không đồng nghĩa DEBUG mọi package |
| Spring Boot `--trace` / `trace=true` | Bật trace cho tập logger framework rộng hơn | Rủi ro và overhead cao, hạn chế môi trường cô lập |
| `@EnableWebSecurity(debug = true)` | Bật hạ tầng debug của Spring Security web filters | **Không dùng trong production**, có thể ghi request headers/parameters nhạy cảm |

Tài liệu Spring Security cảnh báo hạ tầng debug web có thể hiển thị **request parameters và headers**, vì thế chỉ nên dùng trong môi trường development. Cấu hình `@EnableWebSecurity(debug=true)` **khác** với đặt một logger cụ thể ở DEBUG; đừng dùng hai lựa chọn như thể chúng giống nhau.

**Lưu ý phiên bản:** cú pháp logging của Spring Boot thường là properties/YAML, nhưng logger/class nào phát nội dung gì phụ thuộc phiên bản Spring Security, servlet container và các thư viện tích hợp. Luôn xem output đã sanitize ở môi trường giả lập trước khi áp tại production.

## 3. Vì sao log xác thực dễ chứa dữ liệu bí mật?

Một request đăng nhập hoặc gọi API có thể có:

~~~http
POST /login HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=REDACTED
Authorization: Bearer REDACTED
Content-Type: application/x-www-form-urlencoded

username=user@example.test&password=REDACTED&_csrf=REDACTED
~~~

Đây là **request minh họa với dữ liệu đã che**. Nếu log request nguyên văn, dữ liệu có thể bị nhân bản qua:

- stdout/console và log file trên máy chủ;
- agent thu thập log, container logs, Kubernetes log collectors;
- APM/tracing/span attributes và exception monitoring;
- proxy, load balancer, WAF/access logs;
- message broker, SIEM, data lake, cloud logging;
- tickets/screenshots/support chat và bản xuất CSV.

Một secret có thể bị copy nhiều lần ngay cả khi ứng dụng đã xóa khỏi console. Quyền truy cập vào log thường rộng hơn quyền vào database hoặc secret store, vì thế **không được biến hệ thống log thành kho lưu credentials**.

### 3.1. Danh mục tuyệt đối không ghi nguyên văn

| Loại dữ liệu | Ví dụ | Thay thế nên dùng |
| --- | --- | --- |
| Password / PIN | Mật khẩu đăng nhập, mật khẩu hiện tại, PIN | `reasonCategory=BAD_CREDENTIALS` |
| Bearer / OAuth tokens | JWT, opaque access token, refresh token, ID token | `tokenValidation=EXPIRED/INVALID_AUDIENCE` |
| Cookie / session identifiers | `Cookie`, `Set-Cookie`, `JSESSIONID` | `sessionPresent=true`, ID correlation riêng |
| MFA / recovery secrets | OTP, TOTP seed, recovery code, magic link token | `factorType=OTT`, `verificationResult=FAILED` |
| API keys / client secrets | `X-API-Key`, `client_secret` | `clientType=service` nếu đã được phân loại |
| CSRF / anti-forgery values | `_csrf`, `X-CSRF-TOKEN`, `XSRF-TOKEN` | `csrfResult=MISSING/INVALID/VALID` |
| Private keys / keystore | PEM, JWK private material, HSM keys | `keyId` đã được kiểm soát, trạng thái ký |
| PII | Email đầy đủ, phone, địa chỉ, giấy tờ định danh | Internal user reference được bảo vệ, bucket/counter |
| URL chứa secret | `/reset?token=...`, `/callback?code=...` | Route template `/reset`, `/callback` |
| Authentication object | `Authentication.toString()`, `getCredentials()`, `getDetails()` | Event type, policy outcome, principalKnown boolean |
| HTTP body / SQL bind values | JSON đăng nhập, `password=...`, query parameters | Route/method/status đã allowlist |

Các trường như IP, User-Agent, account ID, device identifier, error message, tenant ID và exact URL **cũng có thể là PII hoặc dễ bị lạm dụng**; không tự coi chúng an toàn chỉ vì không phải password.

OWASP Logging Cheat Sheet khuyến nghị loại bỏ, mask, sanitize, hash hoặc encrypt session identifiers, access tokens, passwords, encryption keys và PII nhạy cảm. Trong nhiều trường hợp **không ghi** tốt hơn ghi rồi cố che.

### 3.2. Vì sao regex “thay password=…” không đủ?

Token có thể xuất hiện trong:

- Header khác kiểu chữ: `authorization`, `Proxy-Authorization` hoặc custom headers.
- JSON lồng nhiều cấp, XML, multipart form, GraphQL variables.
- Query string hoặc URL-encoded/double-encoded payload.
- Exception messages, request wrappers, debug toString.
- Tham số chứa dữ liệu nhạy cảm nhưng tên không phải `password`, ví dụ `credential`, `secret`, `otp`, `code`.
- Session/trace attributes của thư viện khác mà regex không nhìn thấy.

**Ưu tiên dựng log từ danh sách trường cho phép (allowlist)** và **không đưa request/response body vào message**. Một regex masking trên output chỉ nên là **defense in depth**, không phải ranh giới an toàn duy nhất.

## 4. Các logger Spring Security cần biết khi điều tra

Spring Security có các thành phần rất hữu ích để khoanh vùng:

| Logger / thành phần | Câu hỏi điều tra | Thận trọng |
| --- | --- | --- |
| `org.springframework.security.web.FilterChainProxy` | Request được bảo vệ bằng security filter chain nào? | Có thể chứa đường dẫn request |
| `org.springframework.security.web.DefaultSecurityFilterChain` | Filter nào được xếp vào chain ở startup? | Không đồng nghĩa filter chạy trên mọi request |
| `org.springframework.security.web.access.ExceptionTranslationFilter` | Vì sao entry point/AccessDenied được gọi? | Message/URL tùy phiên bản |
| `org.springframework.security.web.csrf.CsrfFilter` | CSRF thiếu/sai hay request nằm trong matcher khác? | Không log raw CSRF token |
| `org.springframework.security.authentication.ProviderManager` | Authentication provider nào xử lý request? | Không log full Authentication |
| `org.springframework.security.web.authentication` | Form login success/failure flow và handlers | Có thể ghi URL/exception thông tin |
| `org.springframework.security.oauth2.server.resource` | Bearer/JWT validation flow | **Không log token/JWT claims nguyên vẹn** |
| `org.springframework.security.saml2` | SAML login validation | XML assertions chứa danh tính/claims |
| `org.springframework.security.ldap` | LDAP/AD bind và user lookup | DN, endpoint, username có thể nhạy cảm |

Tên logger và số lượng message **không phải API cố định**. Có logger không in gì ở mức DEBUG với đường request đang xét; đừng tăng toàn bộ lên TRACE vì “chưa thấy log” mà chưa xác nhận filter chain, code path và môi trường.

### 4.1. Đọc danh sách filter ở startup

Ở mức DEBUG cho `DefaultSecurityFilterChain`, Spring Security có thể xuất dòng kiểu:

~~~text
Will secure any request with [
  SecurityContextHolderFilter,
  CsrfFilter,
  LogoutFilter,
  UsernamePasswordAuthenticationFilter,
  ExceptionTranslationFilter,
  AuthorizationFilter
]
~~~

Đây là **ví dụ rút gọn** (filter khác còn tùy config). Nó giúp phát hiện thiếu/sai filter như `CsrfFilter`, `BasicAuthenticationFilter` hoặc một custom filter.

Nhưng **danh sách filter có mặt trong chain không chứng minh request đi đúng chain** khi ứng dụng có nhiều `SecurityFilterChain`. Hãy kết hợp với matcher, request method/route template, status và test integration.

### 4.2. DEBUG có thể giúp gì ở HTTP 401/403?

Ví dụ tình huống:

- **401 Unauthorized:** chưa có chứng cứ authentication hợp lệ, Bearer token không đạt validation, HTTP Basic sai password hoặc request dùng entry point.
- **403 Forbidden:** có thể thiếu authority/role hoặc CSRF bị chặn; đừng tự suy từ status.
- **302 /login:** request web chưa login chuyển sang form login; không mặc định là lỗi.
- **Redirect loop:** cookie không được gửi, session không persist, saved request/host/scheme sai.
- **LDAP/IdP timeout:** service/provider lỗi, không nên coi mọi lỗi là `BadCredentialsException`.

Ưu tiên log **reason category** và **kết quả security decision** thay vì exception.toString() hoặc raw request.

## 5. Chính sách log tối thiểu theo môi trường

Một chính sách minh họa:

| Môi trường | Mức mặc định | Khi điều tra | Điều kiện |
| --- | --- | --- | --- |
| Unit/Local | INFO, DEBUG theo class | DEBUG/TRACE có thể bật ngắn hạn với dữ liệu giả | Không dùng secrets thật |
| CI/Integration | INFO + event categories | DEBUG có điều kiện cho test thất bại | Artifact/log phải được kiểm và redacted |
| Staging | INFO | DEBUG logger hẹp, có approval/TTL | Tốt nhất dùng dữ liệu giả |
| Production | INFO/WARN/ERROR | DEBUG **có kiểm soát**, TRACE cực kỳ ngoại lệ | Owner, mục tiêu, thời hạn, phân quyền, rollback |
| Incident handling | Audit baseline luôn bật | Tăng log từng logger và trong thời gian giới hạn | Theo dõi rò rỉ, dung lượng, rollback, retention |

**Không** để `logging.level.root=TRACE` hoặc `logging.level.org.springframework=TRACE` nằm thường trực trong cấu hình production. Điều này làm tăng chi phí, độ trễ, nguy cơ lộ thông tin và giảm khả năng tìm tín hiệu thật.

### 5.1. application.properties mặc định

~~~properties
spring.application.name=safe-auth-log-lab
server.port=8080

# Baseline an toàn hơn cho lab và ứng dụng mới.
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.level.demo.audit=INFO

# Không kích hoạt Boot --trace/--debug toàn cục.
debug=false
trace=false
~~~

Trong production, INFO **không bảo đảm dữ liệu sẽ tự sạch**. Logger của ứng dụng vẫn phải thiết kế allowlist; framework logs bên thứ ba cần review trước khi bật ở môi trường chứa dữ liệu thật.

### 5.2. Chỉ tăng một logger cụ thể

Tạo `src/main/resources/application-diagnostics.properties` dành riêng cho lab:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.access.ExceptionTranslationFilter=DEBUG

# Không bật TRACE toàn org.springframework.security.
# Không dùng @EnableWebSecurity(debug = true).
~~~

Chạy local:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=diagnostics
~~~

Với Windows PowerShell hoặc shell có cách xử lý JVM/Maven flags khác, cũng có thể chạy JAR đã build:

~~~bash
java -jar target/safe-auth-log-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=diagnostics
~~~

Đây là **cấu hình phục vụ kiểm thử với dữ liệu giả**. Trong môi trường có dữ liệu thật, chỉ chọn logger sau khi review output có thể in và phải có thời hạn tự thu hồi.

## 6. Logging ở application layer: sự kiện allowlist

Ví dụ một record audit thích hợp:

~~~json
{
  "event": "AUTH_FAILURE",
  "outcome": "DENIED",
  "reasonCategory": "BAD_CREDENTIALS",
  "authMethod": "HTTP_BASIC",
  "route": "/api/me",
  "correlationId": "opaque-internal-id",
  "timestamp": "2026-11-06T03:00:00Z"
}
~~~

Đây là **JSON minh họa schema**, không có username, password hay token.

Không lấy `reasonCategory` hay `authMethod` từ form do client tự khai. Chúng phải do server suy từ kết quả authentication/authorization đã kiểm. `route` là **mẫu đường dẫn** đã nhận diện từ router, không phải raw URL có query/path chứa identifiers. `correlationId` nên được sinh server-side hoặc kiểm chặt format/độ dài nếu đi qua proxy.

### 6.1. Authentication event khác HTTP log

Spring Security phát các event như:

- `AuthenticationSuccessEvent` khi manager đã authenticate thành công.
- `AuthenticationFailureBadCredentialsEvent` cho bad credentials.
- `AuthenticationFailureLockedEvent` cho locked account.
- Các subtype khác của `AbstractAuthenticationFailureEvent` tùy exception mapping.

**Authentication event không phải HTTP request/access log**: sự kiện phát khi có authentication attempt, không phải mọi GET. Ví dụ HTTP Basic có thể xác thực nhiều lần, còn session form login thường xác thực khi submit; không đếm event như số user active.

Một listener có thể log **event type, outcome, safe category** mà không đọc `event.getAuthentication().getCredentials()`. Nếu custom manager không gắn `AuthenticationEventPublisher`, event có thể không được phát; log không có event chưa chắc user đã đăng nhập thành công hay thất bại.

### 6.2. Sự kiện authorization và CSRF

Thiếu `ROLE_ADMIN` khi đã authenticated có thể là **authorization denied**, không phải bad password. POST thiếu CSRF có thể bị `CsrfFilter` từ chối **trước** khi credentials được đưa tới `AuthenticationManager`. Vì vậy nên có taxonomy rõ:

~~~text
AUTH_SUCCESS
AUTH_FAILURE / BAD_CREDENTIALS
AUTH_FAILURE / ACCOUNT_LOCKED
AUTH_FAILURE / PROVIDER_UNAVAILABLE
AUTHZ_DENIED / MISSING_AUTHORITY
CSRF_DENIED / MISSING_OR_INVALID
SESSION_EXPIRED
BEARER_DENIED / INVALID_SIGNATURE | EXPIRED | BAD_AUDIENCE
CONFIG_CHANGED / LOGGER_LEVEL
~~~

Các mã trên là **taxonomy đề xuất cho ứng dụng**, không phải danh sách event type mặc định của mọi Spring Security version. Với event audit quan trọng, không phụ thuộc hoàn toàn vào thay đổi mức DEBUG của framework.

## 7. Ví dụ runnable: Spring Boot 3.5 + Java 17 chỉ ghi audit an toàn

Mục tiêu ví dụ:

- App đơn giản có HTTP Basic; account lab `learner` / `lab-password`.
- `DefaultAuthenticationEventPublisher` do Spring Boot tự cấu hình trong trường hợp thông thường, cung cấp success/failure events.
- Listener chỉ ghi **hằng số sự kiện và mã lỗi allowlist**, không ghi principal, password, token, session ID, full Authentication hoặc exception message.
- Bộ JUnit 5 dùng MockMvc + Logback ListAppender kiểm **có sự kiện** nhưng **không rò bí mật**.
- Tùy chọn profile `diagnostics` chỉ tăng DEBUG cho hai logger Spring Security trong lab.

HTTP Basic được chọn vì dễ tạo tình huống đúng/sai credentials trong test. **Không gửi HTTP Basic qua kết nối không mã hóa ở production**; demo localhost HTTP chỉ để học tập. Với form login, OAuth2 hoặc LDAP, thay cơ chế authentication nhưng giữ nguyên tư duy audit cho phép trường nào được ghi.

### 7.1. Cấu trúc thư mục

~~~text
safe-auth-log-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/audit/SafeAuthLogApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── application-diagnostics.properties
    └── test/
        └── java/demo/audit/SafeAuthLogTests.java
~~~

### 7.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>safe-auth-log-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nếu dùng một patch Boot 3.5.x mới hơn, hãy giữ BOM Spring Security tương thích, không tự override Spring Security core xuống nhánh khác chỉ để sửa dependency.

### 7.3. Java source: SafeAuthLogApplication.java

~~~java
package demo.audit;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeAuthLogApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeAuthLogApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("lab-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @RestController
    static class LabApi {
        @GetMapping("/health")
        String health() {
            return "ready";
        }

        @GetMapping("/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("user", authentication.getName());
        }
    }

    @Component
    static class SafeSecurityAudit {
        private static final Logger log =
            LoggerFactory.getLogger(SafeSecurityAudit.class);

        @EventListener
        void success(AuthenticationSuccessEvent event) {
            // Chỉ log thông tin được phép; không ghi principal.
            log.info("event=AUTH_SUCCESS outcome=SUCCESS");
        }

        @EventListener
        void failure(AbstractAuthenticationFailureEvent event) {
            var error = event.getException();
            String category;

            if (error instanceof BadCredentialsException) {
                category = "BAD_CREDENTIALS";
            } else if (error instanceof LockedException) {
                category = "ACCOUNT_LOCKED";
            } else if (error instanceof AuthenticationServiceException) {
                category = "PROVIDER_ERROR";
            } else {
                category = "OTHER_AUTH_FAILURE";
            }

            // Không gọi toString/getMessage trên Authentication,
            // password, exception hay HTTP request.
            log.warn("event=AUTH_FAILURE outcome=DENIED reason={}",
                category);
        }
    }
}
~~~

**Vì sao đây là cách an toàn hơn raw request logging?**

1. `SafeSecurityAudit` chỉ ghi **các giá trị cố định** và một `reason` từ danh sách category trong code.
2. Listener không dùng `event.getAuthentication().getCredentials()`, `getDetails()`, `getPrincipal()` hay `event.getException().getMessage()`.
3. `BadCredentialsException` được gộp vào category chung để không tiết lộ “user không tồn tại” hay password sai qua log có quyền truy cập rộng.
4. UserDetailsService dùng BCrypt cho lab, không ghi password hash vào log.
5. HTTP Basic vẫn phải chạy HTTPS thực tế nếu triển khai ngoài localhost; ví dụ không thay thế rate limiting, session policy hoặc monitoring production.

Spring Boot trong cấu hình thông thường cung cấp `DefaultAuthenticationEventPublisher` nếu chưa có bean publisher khác. Nếu ứng dụng tự tạo `ProviderManager`, phải nối publisher tường minh; nếu không listener có thể không nhận event.

### 7.4. File cấu hình

`src/main/resources/application.properties`:

~~~properties
spring.application.name=safe-auth-log-lab
server.port=8080
logging.level.root=INFO
logging.level.org.springframework.security=INFO
logging.level.demo.audit=INFO
debug=false
trace=false
~~~

`src/main/resources/application-diagnostics.properties`:

~~~properties
# Chỉ dùng trên local với credential giả, không cấu hình production.
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.access.ExceptionTranslationFilter=DEBUG
~~~

Không bật `@EnableWebSecurity(debug=true)` và không đặt `logging.level.org.springframework=TRACE` vì thông tin log có thể vượt quá phạm vi cần thiết.

### 7.5. JUnit kiểm không log password, username và Bearer token

Tệp `src/test/java/demo/audit/SafeAuthLogTests.java`:

~~~java
package demo.audit;

import java.util.stream.Collectors;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeAuthLogTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHealthNeedsNoCredentials() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk());
    }

    @Test
    void protectedEndpointWithoutCredentialsIsDenied()
            throws Exception {
        mvc.perform(get("/me")).andExpect(status().isUnauthorized());
    }

    @Test
    void auditLogShowsEventsButNotSecrets() throws Exception {
        Logger logger = (Logger) LoggerFactory.getLogger(
            SafeAuthLogApplication.SafeSecurityAudit.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        String marker = "wrong-password-SECRET-MARKER";
        String bearerMarker = "Bearer DO-NOT-LOG-THIS";

        try {
            mvc.perform(get("/me")
                    .with(httpBasic("learner", "lab-password")))
                .andExpect(status().isOk());

            mvc.perform(get("/me")
                    .with(httpBasic("learner", marker)))
                .andExpect(status().isUnauthorized());

            String recorded = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));

            assertTrue(recorded.contains("event=AUTH_SUCCESS"));
            assertTrue(recorded.contains("event=AUTH_FAILURE"));
            assertTrue(recorded.contains("reason=BAD_CREDENTIALS"));

            assertFalse(recorded.contains(marker));
            assertFalse(recorded.contains("lab-password"));
            assertFalse(recorded.contains("learner"));
            assertFalse(recorded.contains(bearerMarker));
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

**Ý nghĩa test:**

- Hai request qua HTTP Basic thực sự kích hoạt authentication flow, thay vì dùng `@WithMockUser` để đặt sẵn principal.
- `ListAppender` chỉ được gắn vào **logger SafeSecurityAudit**. Test chứng minh listener này không ghi secrets; nó **không chứng minh tất cả logger khác, reverse proxy, APM hoặc các appenders trong production đều an toàn**.
- Các chuỗi cố tình chứa marker trong test giúp phát hiện lỗi nếu developer sau này thêm `event.getAuthentication()` hoặc exception message vào logger.
- Test dùng credential lab, không dùng tài khoản thật, và không phát HTTP ra Internet.

Có thể mở rộng bằng test static/dynamic scan log files của toàn bộ ứng dụng, test integration ở ingress, policy logback và DLP trên pipeline trước khi bật debug production.

### 7.6. Chạy demo

Trong project với JDK 17+ và Maven:

~~~bash
mvn test
mvn spring-boot:run
~~~

Kỳ vọng khi chạy tests với dependencies đúng:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kết quả kỳ vọng**, không phải log build đã được thu thập; Maven còn in tên class, thời gian và startup diagnostics.

Thử endpoint bằng curl trên máy local:

~~~bash
curl -i http://localhost:8080/health
curl -i --user learner:lab-password http://localhost:8080/me
curl -i --user learner:wrong-password http://localhost:8080/me
~~~

Body thành công mẫu:

~~~json
{"user":"learner"}
~~~

Listener sẽ ghi các dòng ý nghĩa tương tự:

~~~text
event=AUTH_SUCCESS outcome=SUCCESS
event=AUTH_FAILURE outcome=DENIED reason=BAD_CREDENTIALS
~~~

Spring Boot thêm timestamp, thread, logger và log level vào mỗi dòng. **Không copy nguyên file log HTTP headers/cookie/password vào tài liệu**. Với curl và Basic, password trong command line có thể xuất hiện trong shell history/process list: chỉ dùng credential lab, không dùng cách này với production secrets.

### 7.7. Bật chẩn đoán ở môi trường giả lập

Chạy profile dành cho local:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=diagnostics
~~~

Quan sát logger `FilterChainProxy` tại DEBUG. Log có thể cho thấy request nào đi vào chain; **không** kỳ vọng hay lưu toàn bộ raw request body. Sau khi kiểm xong, tắt profile và trở lại baseline INFO.

**Không dùng stdout từ ví dụ để kết luận Spring Security không thể rò token ở các logger/framework khác:** kết quả audit listener an toàn phải kết hợp với policy của toàn bộ stack.

## 8. Java 17 thuần: allowlist thay vì redact request body

Đoạn Java này chạy **không cần Spring** để chứng minh nguyên tắc xây log từ dữ liệu đáng tin. Tệp `SafeAuditLineDemo.java`:

~~~java
public class SafeAuditLineDemo {

    record SafeAuditLine(String event,
                         String outcome,
                         String reason,
                         String requestId) {

        String encode() {
            return "event=" + event
                + " outcome=" + outcome
                + " reason=" + reason
                + " requestId=" + requestId;
        }
    }

    public static void main(String[] args) {
        String rawPassword = "PRIVATE-PASSWORD-DO-NOT-LOG";
        String rawToken = "Bearer PRIVATE-TOKEN-DO-NOT-LOG";

        SafeAuditLine audit = new SafeAuditLine(
            "AUTH_FAILURE", "DENIED", "BAD_CREDENTIALS", "req-42");

        String output = audit.encode();
        System.out.println(output);
        System.out.println("leaked=" +
            (output.contains(rawPassword) || output.contains(rawToken)));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SafeAuditLineDemo.java
java SafeAuditLineDemo
~~~

**Stdout chính xác:**

~~~text
event=AUTH_FAILURE outcome=DENIED reason=BAD_CREDENTIALS requestId=req-42
leaked=false
~~~

Bài học: các giá trị nhạy cảm **không được đưa vào record audit**, thay vì log tất cả rồi áp regex xóa. Trong ứng dụng thật, `requestId` có thể sinh server-side bằng UUID/trace context được kiểm soát; không chấp nhận chuỗi bất kỳ từ header client để tránh log injection hoặc cardinality abuse.

**Phạm vi ví dụ:** các trường hằng số do code tự đặt. Khi build audit từ giá trị không tin cậy, vẫn phải validate/encode và giới hạn độ dài; không cho dữ liệu chứa CRLF tạo log giả.

## 9. Actuator loggers: đổi level khi đang chạy mà không sửa cấu hình

Spring Boot Actuator có endpoint `/actuator/loggers` để xem và (nếu được cho phép) điều chỉnh mức log runtime. Ví dụ request body:

~~~json
{"configuredLevel": "DEBUG"}
~~~

Khi POST tới endpoint cho một logger cụ thể (có authentication/authorization và CSRF/network controls phù hợp), level có thể được đổi sang DEBUG. Có thể reset mức đã cấu hình:

~~~json
{"configuredLevel": null}
~~~

**Quan trọng:** HTTP POST thay đổi cấu hình log là **thao tác quản trị nhạy cảm**. Không mở public anonymous `/actuator/loggers/**` và không expose tất cả Actuator endpoints bằng `include=*` trong production.

### 9.1. Nếu thêm Actuator

Trong Maven có thể thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Đây là **mảnh dependency**, không tự thêm vào project demo ở mục 7. Default Spring Boot thường chỉ expose health qua HTTP; để dùng loggers phải cấu hình exposure **và** access/security theo policy. Một ví dụ policy concept:

~~~properties
# Chỉ cấu hình trên management interface đã kiểm soát.
management.endpoints.web.exposure.include=health,loggers

# Không tự đưa management endpoints ra Internet.
# Dùng authn + role OPS, allowlisted network, TLS và audit.
~~~

Nếu app có custom `SecurityFilterChain`, Boot Security auto-config có thể không còn bảo vệ endpoint đúng ý nếu không viết matcher tương ứng. Cần explicit authorization cho đường management, tốt nhất tách network/port và giới hạn role. Với cookie-based management UI, POST đổi logger level vẫn cần CSRF protection; không disable CSRF chỉ để lệnh đổi level chạy được.

### 9.2. Runbook đổi mức log

Trước khi bật:

1. **Ticket/incident ID:** ghi rõ lỗi, mục đích, người phê duyệt, service/replica/env.
2. **Data classification:** logger có khả năng in headers, claims, request parameters hay PII không?
3. **Scope:** ưu tiên một class/logger hoặc một replica ở staging, tránh root/global.
4. **Timebox:** ví dụ 10–15 phút theo policy, có owner và thời điểm phải rollback.
5. **Access:** giới hạn ai đọc được log/Actuator, lưu audit thay đổi logger level.
6. **Dry run:** với dữ liệu giả, kiểm log có secrets và log volume.
7. **Kích hoạt:** áp DEBUG logger hẹp; quan sát status, latency, throughput, disk/ingestion.
8. **Thu thập:** chỉ xuất **đoạn tối thiểu**, loại bỏ secret và kiểm retention.
9. **Rollback:** set `configuredLevel=null` hoặc baseline INFO, kiểm effective level đã phục hồi.
10. **Post-incident:** ghi RCA, test hồi quy, rà soát có log nhạy cảm đã lan truyền, đóng ticket.

Timebox phải được **thực thi bằng quy trình/automation**; Actuator không tự quay về INFO chỉ vì trong ticket có ghi “15 phút”. Cấu hình động có thể bị mất khi restart hoặc bị overwrite bởi hệ config khác, nên ghi nhận cả desired/effective level.

### 9.3. Khi nào không nên dùng Actuator để debug?

Nếu chưa có cơ chế bảo vệ endpoint và audit thay đổi, **không mở loggers chỉ để tiện điều tra**. Có thể dùng cấu hình qua deployment pipeline kiểm soát thay vì tạo một API quyền cao ở production. Runtime log-level là khả năng vận hành nhưng cũng là đường để attacker (nếu chiếm quyền quản trị) cố kích hoạt logging secrets.

## 10. Những nơi thường rò bí mật ngoài log của Spring Security

Ngay cả khi code event listener an toàn, vẫn phải rà soát:

| Nguồn | Rủi ro cụ thể | Cách khống chế |
| --- | --- | --- |
| Servlet/access log | Raw URI/query chứa `token`, `code`, email | Log route template, query stripped |
| Reverse proxy/WAF | Authorization/Cookie hoặc full request capture | Header allowlist, masking, retention |
| APM/tracing | URL query, baggage, span attrs, errors | Attribute filtering, collector policy |
| HTTP client wire logging | HTTP body với password/client secret | Tắt wire/body logs, synthetic tests |
| Logback/Log4j pattern | MDC chứa user/token/PII | Chỉ add MDC fields đã validate |
| Hibernate SQL binder TRACE | Email/password hash/PII ở bind variables | Tắt SQL bind TRACE trong production |
| OAuth2/OIDC client | Authorization code, state, ID token, SAML response | Không ghi full callback/query/assertion |
| JWT failure exception | Raw token trong error context | Map lỗi sang safe reason |
| Session debugging | JSESSIONID và session attributes | Chỉ log presence/trạng thái |
| CSRF debugging | Raw CSRF token trong request params | Chỉ log missing/invalid category |
| Exception handler | Stack trace/request body bị in tự động | Sanitize cause/response/log |
| Actuator env/configprops/heapdump | Secrets và đối tượng nhớ | Không expose tùy tiện, RBAC/network |
| CI artifact/support dump | Token/credentials trong test logs | Scan/redact và kiểm truy cập |

**Chú ý đặc biệt:** OpenTelemetry/APM và logging agent có thể thu dữ liệu **trước khi ứng dụng mask ở appender**, nên cần cấu hình an toàn ở từng điểm thu thập, không chỉ Logback.

### 10.1. Correlation ID và MDC

Correlation giúp kết nối nhiều log mà không ghi session ID. Cách tốt:

- Server/edge tin cậy sinh ID ngẫu nhiên hoặc dùng tracing ID được xác minh.
- Validate incoming ID theo độ dài, ký tự, trust boundary; không tin bất kỳ header `X-Request-ID` từ Internet.
- Ghi `correlationId` nhất quán qua service, dùng retention/role controls.
- Với SLF4J MDC, luôn clear trong `finally` để không nhiễm request khác khi servlet threads được tái sử dụng.
- Không đưa raw principal/email/token vào MDC hay trace baggage; propagation có thể đi qua nhiều hệ thống.

Ví dụ fragment:

~~~java
String requestId = java.util.UUID.randomUUID().toString();
org.slf4j.MDC.put("requestId", requestId);
try {
    // Gọi tiếp xử lý trong filter/service.
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

**Đây là mảnh code**, không phải Servlet Filter hoàn chỉnh. Trong reactive code, thread-local MDC không tự truyền qua mọi thread; cần Reactor context/tracing integration phù hợp.

## 11. Log injection và dữ liệu không đáng tin

Nếu code ghi trực tiếp:

~~~java
// PHẢN VÍ DỤ: username đến từ client có thể chứa CRLF.
log.warn("login failed for " + inputUsername);
~~~

Một chuỗi chứa xuống dòng có thể tạo nhiều dòng log giả, đánh lừa dashboard hoặc parser. Các trường client-supplied cũng có thể gây log flooding, high cardinality metrics và lộ PII.

Ưu tiên:

- Category/enum cố định do server suy luận.
- Structured JSON logs với field-level encoding và size limits.
- Không ghi raw usernames trong metric labels.
- Nếu cần referent để điều tra, dùng internal ID được phân quyền/giả danh theo policy; HMAC pseudonymization vẫn có rủi ro privacy và phải quản lý khóa.
- Tách log sự kiện an ninh khỏi log debug framework bằng sink/retention/RBAC tương ứng.
- Không thực hiện authn/authz decision dựa vào một log event do client có thể tạo.

## 12. Incident playbook: xử lý “403 không rõ nguyên nhân”

### 12.1. Thu thập ban đầu, không bật TRACE

Giả sử người dùng báo `POST /api/profile` bị 403.

1. Xác định timestamp, service, environment, HTTP method, **route template** và correlation ID đã sanitize.
2. Xem metric và audit category: `CSRF_DENIED`, `AUTHZ_DENIED` hay `AUTH_FAILURE`?
3. Kiểm controller/filter chain matcher; với session auth, có cookie phiên không (boolean), CSRF token được gửi đúng không (boolean), không ghi giá trị.
4. Kiểm `SecurityContext` có authenticated principal không theo **flag** hoặc internal reference được phép; kiểm authorities dạng category/role **chỉ nếu chính sách audit cho phép**.
5. Nếu là resource server, kiểm validation result `issuer/audience/expiry/signature` theo category, không dump JWT.
6. Nếu thiếu tín hiệu, bật DEBUG theo logger cụ thể với owner/timebox.

### 12.2. Tăng mức từng phần

Thứ tự ưu tiên:

~~~text
A. Baseline INFO + audit events đã chuẩn hóa
B. DEBUG FilterChainProxy cho filter/matcher
C. DEBUG ExceptionTranslationFilter/CsrfFilter khi cần
D. DEBUG provider tương ứng trong môi trường kiểm soát
E. TRACE chỉ sau phê duyệt, synthetic traffic/cô lập
~~~

Bước E không phải mặc định. Khi có credential thật, xem xét **không bật TRACE**, dùng reproduction an toàn hoặc instrument event category riêng.

### 12.3. Một số chẩn đoán thường gặp

| Triệu chứng | Tín hiệu nên lấy | Không nên lấy |
| --- | --- | --- |
| Login form POST 403 | CSRF result, route, sessionPresent | CSRF token/password |
| Login form 302 loop | Session cookie flags, saved URL sanitized, context persistence | JSESSIONID nguyên văn |
| OAuth JWT 401 | Reason category, issuer key-set status, clock skew bounds | JWT raw, Authorization header |
| LDAP login fail | Provider availability, bind outcome category | DN đầy đủ/password LDAP |
| Admin endpoint 403 | Role/policy decision category, tenant access result | Entire Authentication object |
| Session lost after login | Session store health, cookie path/domain, fixation event | Session values |
| SSO callback error | IdP state/nonce validation outcome | Authorization code/ID token |
| Many bad-password events | Count bucketed by source/account risk | Password guesses, usernames as metrics labels |

### 12.4. Sau khi phát hiện log đã chứa secret

Nếu secret đã vào logging pipeline:

1. **Dừng nguồn ghi** (rollback level, sửa logger/handler).
2. **Phân loại dữ liệu và phạm vi**: token loại nào, còn hiệu lực không, ở sinks nào, đã export/tải về chưa.
3. **Thu hồi/rotate** credentials, refresh tokens, API keys hoặc session IDs khi cần theo mức phơi lộ.
4. **Giới hạn quyền truy cập** và đóng các đường export, giữ bằng chứng phục vụ điều tra theo policy (không xóa bừa làm mất chain-of-custody).
5. **Xử lý bản sao** ở log storage, backups, CI artifacts, tickets theo quy trình retention/redaction và yêu cầu pháp lý.
6. **Thông báo** cho đội security/privacy/legal và chủ thể dữ liệu khi chính sách hoặc luật yêu cầu.
7. **Viết regression test** cấm credential fields, bổ sung guardrails ở exporter/proxy và review logging config.
8. **Postmortem**: sự cố rò log là một security incident, không chỉ “bật nhầm DEBUG”.

## 13. Checklist QA bảo mật cho logging pipeline

### 13.1. Mức log và cấu hình

- [ ] Default INFO/WARN/ERROR, không bật global TRACE ở production.
- [ ] Debug mode của Spring Security web chỉ dùng development.
- [ ] DEBUG production nếu thực sự cần chỉ giới hạn logger, thời gian, scope, owner.
- [ ] Logger changes qua Actuator/config được authentication, authorization, audit và rollback.
- [ ] Không expose `/actuator/loggers`, `env`, `heapdump` hay trace endpoints công khai.
- [ ] Kiểm baseline/effective level sau incident, cả sau restart/redeploy.
- [ ] Theo dõi log volume, disk/ingestion và login latency.

### 13.2. Data minimization

- [ ] Không ghi raw password, PIN, OAuth tokens, refresh tokens, session IDs, Cookie/Set-Cookie, CSRF, OTP, recovery codes.
- [ ] Không log raw Authorization, Proxy-Authorization, X-API-Key hoặc request body.
- [ ] URL/query strings chứa secrets được bỏ hoặc thay route template.
- [ ] Event log chỉ dùng allowlist fields, category enum và correlation ID an toàn.
- [ ] Stack trace/exception message được rà soát trước khi xuất; không dựa hoàn toàn regex.
- [ ] Log fields chịu kiểm length/encoding, chống CRLF injection.
- [ ] Phân quyền sink, giới hạn retention, mã hóa log at rest/in transit.
- [ ] Rà soát proxy, APM, tracing, SQL bind logger, CI artifacts và support exports.

### 13.3. Khả năng điều tra

- [ ] Phân biệt authentication failure, authorization denied và CSRF denied.
- [ ] Có correlation ID không sử dụng session token làm định danh.
- [ ] Không dùng count authentication events làm số users đang online.
- [ ] Có triage playbook cho 401, 403, 302 loop, token/JWK, LDAP, session.
- [ ] Có synthetic traffic để tái hiện và kiểm log DEBUG trước production.
- [ ] Các unit/integration tests xác nhận safe listener không ghi secrets.
- [ ] Có kế hoạch ứng phó khi secret lọt vào logs và kiểm lại sau fix.

## 14. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao nguy hiểm/sai | Cách sửa |
| --- | --- | --- |
| Bật `logging.level.root=TRACE` | In mọi package, nhiều PII/overhead | Chỉ chọn logger hẹp, thời gian ngắn |
| Bật `@EnableWebSecurity(debug=true)` ở prod | Có thể in request headers/parameters | Chỉ development với data giả |
| Cho rằng `--debug` bật DEBUG toàn app | Boot chỉ bật tập logger được chọn | Dùng logger-specific levels |
| Log `request.getHeader("Authorization")` | Rò Bearer token | Log token validation outcome |
| Log `Cookie`/`Set-Cookie` | Rò JSESSIONID/session | Log sessionPresent/flags |
| Log `Authentication.toString()` | Có thể chứa principal/details/credentials | Allowlist safe fields |
| Log exception `getMessage()` mọi lỗi | Lộ dữ liệu từ provider/DB/IdP | Map sang failure category |
| Chỉ che chuỗi `password=...` | Miss JSON/header/encoded tokens | Không log body, field allowlist |
| Ghi email đầy đủ trong metric labels | PII, high-cardinality, cost | Buckets/aggregates/safe IDs |
| Sử dụng IP từ `X-Forwarded-For` bất kỳ | Attacker giả IP điều tra | Trusted proxy chain |
| Cho phép public POST /actuator/loggers | Attacker thay level thu thập secrets | Role OPS, network/TLS/CSRF, audit |
| Quên rollback DEBUG sau incident | Duy trì leakage và ingestion cost | Timebox/runbook/automation |
| Thấy không có event rồi coi authn không chạy | Custom manager chưa nối publisher | Kiểm manager wiring |
| Chỉ test Logback appender của ứng dụng | Proxy/APM có thể vẫn leak | Scan end-to-end pipeline |
| Xóa logs ngay khi lộ token | Có thể mất bằng chứng điều tra | Preserve/contain theo incident policy |

## 15. Câu hỏi tự kiểm tra

1. Vì sao đặt `logging.level.org.springframework.security=TRACE` khác với tăng một logger `FilterChainProxy`?
2. Spring Boot `--debug` có làm mọi logger DEBUG không?
3. Vì sao Spring Security `@EnableWebSecurity(debug=true)` không nên dùng production?
4. Những header nào tuyệt đối không nên dump vào log?
5. `JSESSIONID` và `XSRF-TOKEN` có được coi là thông tin log công khai không?
6. Vì sao `Authentication.toString()` có thể làm lộ thông tin?
7. OWASP khuyến nghị xử lý session IDs, passwords và access tokens ra sao trước khi ghi log?
8. Chỉ regex xóa `password=...` có đủ cho JSON/OAuth callback không?
9. 401 khác 403 thế nào, và CSRF 403 có phải bad credentials không?
10. Vì sao cần phân biệt authentication event với authorization denied?
11. Event log chỉ ghi `reasonCategory` có ưu điểm gì so với exception message?
12. Tại sao metrics label username dễ tạo rủi ro PII và cardinality?
13. `/actuator/loggers` cần kiểm soát những quyền nào?
14. Tại sao rollback logger level phải có người chịu trách nhiệm và thời hạn rõ?
15. Debug test bằng Logback ListAppender chứng minh được điều gì? Không chứng minh được điều gì?
16. Nếu log token đã được gửi lên cloud collector, cần xử lý thêm những bản sao nào?
17. Tại sao correlation ID không nên lấy thẳng từ header không tin cậy?
18. Bật TRACE để tìm lỗi JWT sai audience có cần in raw JWT không?

**Kết luận:** DEBUG/TRACE là công cụ điều tra mạnh nhưng cũng có thể biến log thành kho chứa secrets. Thiết kế đúng là **audit có cấu trúc, allowlist dữ liệu, baseline INFO, logger-specific DEBUG có timebox/approval, kiểm soát Actuator/collectors, rollback và test không rò dữ liệu**. Khi xử lý sự cố Spring Security, tìm **nguyên nhân xác thực/ủy quyền theo category**, không thu thập raw password, token hoặc cookie.

## 16. Tài liệu chính thức và tham khảo bảo mật

- [Spring Security 6.5 — Servlet Security Architecture and Logging](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Web Application Security namespace debug warning](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/namespace/http.html)
- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 — Actuator Loggers](https://docs.spring.io/spring-boot/3.5/reference/actuator/loggers.html)
- [Spring Boot 3.5 — Actuator Endpoint Exposure and Access](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
