# Không ghi mật khẩu vào log, response hoặc dữ liệu kiểm thử được công khai

## 1. Vấn đề: mật khẩu có thể bị rò ở những chỗ tưởng như vô hại

Một ứng dụng Spring Boot có thể lưu mật khẩu đúng cách bằng BCrypt nhưng vẫn làm lộ mật khẩu khi developer bật debug, in object request, trả nguyên entity User qua API hoặc commit dữ liệu kiểm thử chứa credentials thật. Trong nhiều hệ thống, log và test artifacts được gửi tới các dịch vụ có nhiều người truy cập hơn cơ sở dữ liệu production. Vì vậy bảo vệ bảng password_hash mới chỉ là một phần của bảo vệ thông tin đăng nhập.

Ví dụ có một endpoint đăng nhập nhận username và password. Developer có thể vô tình thực hiện:

~~~java
// ANTI-PATTERN: tuyệt đối không đưa vào code triển khai.
log.debug("Login input: {}", loginRequest);
log.info("Credentials: {}", authentication);
return ResponseEntity.ok(userEntity);
~~~

Vấn đề không chỉ là lệnh log có chữ “password” hay không:

- **loginRequest.toString()** do record, Lombok hoặc IDE sinh có thể in toàn bộ field, trong đó có mật khẩu.
- **Authentication** có thể mang credentials, principal hoặc details; tùy implementation, việc stringify có thể lộ dữ liệu khác nhau.
- **UserEntity** thường chứa passwordHash, thông tin cá nhân và quan hệ JPA; Jackson có thể serialize các getter công khai.
- Một exception, HTTP debugging filter hoặc APM plugin có thể ghi lại request body và header ngay cả khi Controller không log.
- Báo cáo test hoặc CI có thể in command-line arguments, environment, HTTP exchange, failure diff, screenshot, HAR hoặc fixture có mật khẩu.

**Nguyên tắc học tập:** mật khẩu gốc (**raw password**), password hash, reset token, access/refresh token, API key, session cookie và mã xác thực là **dữ liệu bí mật hoặc credential nhạy cảm**. Chỉ gửi/lưu chúng ở nơi thực sự cần cho xác thực, đúng vòng đời; không để lọt vào **log, HTTP response công khai, mã nguồn/test fixture được chia sẻ hoặc build artifacts có thể tải xuống**.

Bài thuộc chủ đề **Spring Security - fundamentals → Mật khẩu**. Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet, SLF4J và MockMvc**. Nội dung nêu rõ đâu là code chạy trong dự án, đâu là snippet minh họa. Không dùng một mật khẩu thật hoặc mật khẩu mẫu cố định trong mã nguồn và các lệnh curl.

### Sau bài học, bạn có thể

1. Chỉ ra các bề mặt rò rỉ mật khẩu ở Controller, filter, service, logging config, proxy, APM và CI.
2. Giải thích vì sao **hash mật khẩu vẫn không được coi là dữ liệu công khai**.
3. Thiết kế response DTO theo danh sách trường được phép thay vì trả nguyên Authentication, UserDetails hoặc entity.
4. Log sự kiện xác thực bằng **event type, outcome và request ID an toàn**, không log raw credential.
5. Tránh các bẫy của toString, Java record, Lombok @Data, exception.getMessage và HTTP request/response body logging.
6. Tạo ví dụ Spring Boot nhận credential demo từ cấu hình runtime; mã nguồn không chứa password thật hoặc fixture tĩnh.
7. Dùng MockMvc kiểm thử response không echo mật khẩu, hash hoặc dữ liệu nội bộ và dùng output capture kiểm tra log của ứng dụng.
8. Biết giới hạn của phép kiểm thử, đồng thời rà soát reverse proxy, central logging, tracing, CI reports và test-data exports.
9. Thiết kế secret scanning, quy trình xoay vòng credential và xử lý khi phát hiện credential đã bị lộ.
10. Hiểu rõ bảo vệ thông tin đăng nhập là yêu cầu xuyên suốt từ lúc nhận request đến khi xóa dữ liệu kiểm thử.

## 2. Phân loại dữ liệu: thứ gì được phép lưu ở đâu?

| Dữ liệu | Dùng vào việc gì | Log? | Trả response? | Commit vào repo? |
| --- | --- | --- | --- | --- |
| Raw password | Chứng minh người dùng biết bí mật | **Không** | **Không** | **Không** |
| Encoded password/BCrypt hash | Provider kiểm tra ứng viên password | **Không** | **Không** | Tránh dùng hash thật; test chỉ dùng giá trị sinh tạm |
| Password reset token | Xác minh yêu cầu đặt lại mật khẩu | **Không** | Không echo lại theo cách làm lộ token | **Không** |
| OTP/MFA recovery code | Thực hiện bước xác thực bổ sung | **Không** | Chỉ gửi theo kênh và giao thức có kiểm soát | **Không** |
| Access token/refresh token | Chứng cứ truy cập hoặc cấp lại token | **Không** | Chỉ ở endpoint issuance theo giao thức; không echo bừa bãi | **Không** |
| Session cookie/session ID | Liên kết phiên đã xác thực | **Không** | Cookie được phát theo cơ chế HTTP an toàn, không nhúng vào JSON tùy ý | **Không** |
| Username hoặc email | Tìm danh tính tài khoản | Hạn chế, theo policy dữ liệu cá nhân | Có điều kiện | Không dùng dữ liệu thật của người dùng |
| Internal user ID | Phân biệt user/authorization | Có điều kiện, không phải secret nhưng vẫn có thể là dữ liệu cá nhân | Chỉ khi client cần | ID giả lập được phép khi không gắn người thật |
| Request ID tạo phía server | Điều tra sự cố và liên kết các log | Thường có | Có thể có theo hợp đồng API | Được nếu không chứa secret |
| Event category: auth.failure | Phân tích hoạt động bảo mật | **Nên** | Có thể là error code công khai nếu phù hợp | Được |
| HTTP status 200/401/403 | Quan sát kết quả request | **Nên** | Theo giao thức | Được |
| Nội dung exception/stack trace | Chẩn đoán sự cố nội bộ | Có kiểm soát, cần redaction | **Không** ở public API | Không lưu artifact chứa secret |

Bảng “không trả response” nói về **các API công khai hoặc response không có chức năng phát credential**. Ví dụ giao thức đăng nhập bằng token có thể **cố ý phát access token** sau khi xác thực; đó là một hợp đồng bảo mật riêng, có TLS, scope, thời hạn và cách lưu client phù hợp. Không suy ra “mọi response có token đều sai”; sai là **vô tình echo secret vào API khác, log hoặc kết quả test công khai**.

### 2.1. Password hash vẫn nhạy cảm

Hash BCrypt/Argon2/PBKDF2 không phải plaintext và không được dùng như raw password cho login thông thường. Nhưng nếu hash rò rỉ, attacker có thể thử đoán password ngoại tuyến, khai thác mật khẩu yếu hoặc ghép dữ liệu bị lộ từ nơi khác. Vì thế:

- Database phải hạn chế quyền truy cập cột password_hash.
- Backup phải có mã hóa và kiểm soát quyền tải/xem.
- Không in hash để “xem encoder hoạt động hay chưa”.
- Không trả hash trong DTO, GraphQL schema, debug endpoint hay admin export thông thường.
- Không đưa hash vào event bus/queue/cache chỉ để frontend tiện kiểm tra.
- Nếu cần kiểm tra logic mã hóa, test **matches** và format/algorithm ID, không xuất toàn bộ hash ra console.

### 2.2. Không coi Base64 hoặc mã hóa reversible là redaction

HTTP Basic dùng Base64(username:password). Base64 có thể giải mã trực tiếp. Log toàn bộ Authorization: Basic header tương đương log credential có thể tái sử dụng. Ghi một JWT/Bearer token rồi thay vài ký tự đầu chưa chắc đã đủ che secret nếu phần còn lại có giá trị sử dụng hoặc tiết lộ claims.

**Redaction** là loại bỏ hoặc thay giá trị nhạy cảm trước khi nó đến hệ thống log/response, không đơn thuần encode thành một biểu diễn khác.

## 3. Luồng Spring Security và các điểm có thể rò rỉ

~~~text
Client gửi thông tin xác thực
       |
       v
Servlet container / reverse proxy
       |     Rủi ro: access log toàn URL/query, headers
       v
FilterChainProxy / authentication filter
       |     Rủi ro: dump request/response, Authorization, body
       v
AuthenticationManager / AuthenticationProvider
       |     Rủi ro: debug credentials, exception detail
       v
UserDetailsService / PasswordEncoder / database
       |     Rủi ro: log SQL params, hash, entity.toString
       v
Authentication / SecurityContext
       |     Rủi ro: serialize principal, details, token
       v
Controller / business service
       |     Rủi ro: response return entity, broad DTO
       v
HTTP response / API gateway / frontend
       |     Rủi ro: error body, browser console, HAR
       v
Monitoring, APM, logging collector, CI/test artifacts
             Rủi ro: sao chép dữ liệu sang nhiều kho
~~~

Trong Spring Security, **UserDetailsService** cung cấp UserDetails, có thể bao gồm password hash cho DaoAuthenticationProvider. **PasswordEncoder.matches(raw, storedHash)** kiểm tra credential. Sau khi xác thực, **Authentication** chứa thông tin danh tính/quyền, và framework có cơ chế xử lý credential erasure. Nhưng không thể suy ra mọi bản sao raw password hoặc hash đều đã biến mất khỏi mọi lớp.

Không nên dựa vào **Authentication.toString() “thường che credentials”** như một bảo đảm: principal, details hoặc custom implementation vẫn có thể chứa dữ liệu nhạy cảm; một bản nâng cấp framework cũng có thể thay đổi nội dung được in.

### 3.1. Ranh giới quan trọng

1. **Request boundary:** Nhận password để xác minh, không đăng ký nó thành dữ liệu dùng cho log hoặc analytics.
2. **Authentication boundary:** Credential được dùng khi cần; provider không chia sẻ raw password cho Controller nghiệp vụ.
3. **Response boundary:** Chỉ xuất DTO đã cho phép; không serialize framework object.
4. **Observability boundary:** Chỉ log các trường đã được kiểm tra và phân loại an toàn.
5. **Test/build boundary:** Test dùng credential tạm, không đẩy nó vào stdout, reports, screenshots hoặc thư viện fixtures công khai.

## 4. Ghi log đúng: sự kiện hữu ích, không chứa bí mật

Một hệ thống vẫn cần log **thành công/thất bại xác thực, truy cập bị từ chối, nghi ngờ brute force, thay đổi role, lỗi hạ tầng** để phát hiện sự cố. “Không log password” không có nghĩa là tắt mọi security logging.

### 4.1. Những cách log nguy hiểm

~~~java
// ANTI-PATTERN: tất cả lệnh dưới đây đều cần tránh.
log.debug("login request={}", loginRequest);
log.info("password={}", rawPassword);
log.warn("authentication={}", authentication);
log.error("failed: {}", exception.getMessage());
log.trace("request headers={}", headers);
log.debug("saved user={}", userEntity);
~~~

Dù mã không trực tiếp viết password literal, một giá trị toString/exception/header có thể chứa secret. Không để logging framework quyết định thay bạn trường nào an toàn.

### 4.2. Log theo allowlist

Thay vào đó, tạo event có các trường cố định và chọn theo policy:

~~~java
// Ví dụ nằm trong một service dùng SLF4J.
private static final Logger log =
    LoggerFactory.getLogger(LoginAudit.class);

void loginRejected() {
    log.warn("event=authentication_failed outcome=rejected");
}

void accessGranted() {
    log.info("event=protected_resource_access outcome=success");
}
~~~

Đây là **snippet**, chưa phải file Java độc lập; cần class LoginAudit và imports org.slf4j.Logger/LoggerFactory. Điều quan trọng là **không đưa raw password, hash, request DTO hoặc token vào placeholders của logger**.

Trong hệ thống thật có thể thêm **server-generated correlation ID**, route pattern và policy outcome. Request ID có thể đi qua tracing, nhưng không lấy nguyên ID do client tùy ý gửi mà không validate kích thước/ký tự; điều đó có thể gây log injection hoặc phá cấu trúc log.

### 4.3. Chọn event và mức log

| Sự kiện | Mức gợi ý | Ví dụ trường an toàn |
| --- | --- | --- |
| Đăng nhập thành công | INFO hoặc audit pipeline | event=auth.success, result=allow, requestId |
| Đăng nhập thất bại | WARN/audit tùy tần suất | event=auth.failure, result=deny, category chung |
| Thiếu role | WARN/audit | event=authz.denied, permission code |
| Password được đổi | INFO/audit | event=credential.rotated, outcome=success |
| Reset token yêu cầu | INFO/audit có rate limiting | event=recovery.requested, outcome=accepted |
| DB truy vấn tài khoản lỗi | ERROR | event=identity_store.failure, error category, correlation ID |
| Bất thường số lần login | Metric/alert | số lượng thất bại theo cửa sổ thời gian |

Đây là **gợi ý**, không phải mức log cố định bắt buộc. Với hệ thống có nhiều request thất bại, ghi WARN cho mọi attempt có thể làm đầy log/chi phí. Cần aggregation, sampling phù hợp và audit riêng để vẫn phát hiện brute force mà không gây DoS qua logging.

### 4.4. Allowlist tốt hơn chỉ blacklist chuỗi

Một giải pháp “mask các key có tên password” bằng regex không bắt được mọi bí mật:

- Tên field là pwd, passcode, oldSecret, confirmation hoặc nested JSON khác.
- Header có Authorization, Proxy-Authorization, Cookie, X-API-Key hoặc Set-Cookie.
- Một token nằm trong URL query, path, exception, attribute hay request body không có key rõ ràng.
- Logging library stringify object trước khi mask field.
- Stack trace chứa tên file/path, request parameters hoặc values ở message.
- Trường khác chứa value của password do attacker cố ý đưa vào.

**Cách chính:** xây log event bằng các trường được phép xuất phát từ logic nghiệp vụ. Redaction ở collector là lớp dự phòng, không nên là kiểm soát duy nhất.

## 5. Các bẫy Spring Boot, Java và logging framework

### 5.1. Java record tự sinh toString

Một Java record mang field password có thể tự sinh toString bao gồm field đó. Ví dụ:

~~~java
record ChangePasswordRequest(
    String currentPassword,
    String newPassword
) {}
~~~

Đây là **type minh họa**, không phải đoạn nên log. Nếu dùng log.info("{}", request), cả hai field có thể bị in. Java record không tự che dữ liệu nhạy cảm.

Hướng xử lý: **không log request object**. Nếu thật sự cần toString riêng, chỉ trả marker đã che; nhưng **toString an toàn không thay thế JSON serialization an toàn**.

### 5.2. Lombok @Data và @ToString

Lombok có thể sinh toString, equals và accessors. Nếu class request/entity chứa password mà dùng @Data hoặc @ToString không kiểm soát, developer khác rất dễ in cả object.

Có thể dùng Lombok @ToString.Exclude trên field nhạy cảm như một lớp phụ, nhưng cách tốt hơn là **không log nguyên DTO**, không trả entity và không dựa vào annotation đơn lẻ để bảo đảm bí mật không đi qua Jackson, logging, serialization hoặc tracing.

### 5.3. UserDetails, Authentication và Principal

DaoAuthenticationProvider cần UserDetails có encoded password để kiểm tra. Spring Security cố giảm thời gian lưu credentials trong một số Authentication thông qua **CredentialsContainer / ProviderManager**. Nhưng:

- Principal tùy biến có thể mang field nhạy cảm.
- UserDetails được cache có thể chứa password hash.
- Authentication.details có thể mang IP, session metadata hoặc custom data.
- JWT/OIDC Authentication có thể tham chiếu claims và token.
- Custom toString hoặc serializer có thể in dữ liệu ngoài dự kiến.

Vì vậy không làm:

~~~java
@GetMapping("/me")
Authentication unsafe(Authentication authentication) {
    return authentication;
}
~~~

Đây là **anti-pattern**. Không return SecurityContext, UserDetails hay UserEntity để “debug nhanh”.

### 5.4. Logging HTTP body/header

Trong Spring MVC, developer có thể thêm CommonsRequestLoggingFilter, OncePerRequestFilter, ContentCachingRequestWrapper hoặc interceptor để log request/response. Với endpoint nhận password, các cấu hình ghi **payload**, **Authorization**, **Cookie** hay query string đều cần đặc biệt cẩn thận.

Không khuyến nghị bật includePayload/includeHeaders cho toàn bộ ứng dụng và không sao chép raw header map vào log. Nếu cần observability HTTP, ưu tiên **method, route template, status, duration và request ID**. Hạn chế query parameters vì token/reset link có thể nằm trong URL.

Một access log server/proxy có thể ghi **request target** gồm path/query; vì vậy hạn chế truyền secret qua query ngay từ thiết kế API.

### 5.5. Spring Security DEBUG/TRACE

Logging DEBUG có thể rất hữu ích để xác định filter chain, authentication provider, authorization rule. Tuy nhiên mức log, nội dung log và các thư viện liên quan thay đổi theo version/cấu hình, nên **không mặc định TRACE an toàn khi production traffic chứa credential thật**.

Nếu cần điều tra sự cố:

1. Dùng môi trường thử riêng và account giả.
2. Giới hạn phạm vi/mức log, thời gian bật và quyền đọc.
3. Không dump request body, raw headers, password hoặc hash.
4. Rà soát logging ở gateway, servlet container, APM và collector.
5. Tắt cấu hình debug sau khi kết thúc điều tra và kiểm tra retention.

### 5.6. Các cơ chế APM, Actuator và tracing

Spring Boot Actuator có thể ghi lại HTTP exchanges nếu tính năng được cấu hình và bật. Tùy nội dung collector có thể có URI, header, principal hoặc session metadata. APM/tracing từ bên thứ ba cũng có thể tự thu thập body, exception hoặc attributes.

**Không có bảo đảm rằng Controller không log thì cả hệ thống không log.** Hãy kiểm tra cấu hình thực tế của proxy, service mesh, servlet filters, Actuator HTTP exchanges, OpenTelemetry instrumentation, error reporting và central logging.

### 5.7. Exception và validation errors

Một validation layer có thể đưa **rejectedValue** hoặc field value vào exception. Nếu global handler trả exception.getMessage() hoặc binding errors nguyên dạng, mật khẩu có thể xuất hiện ở HTTP error JSON.

Ví dụ không nên dùng:

~~~java
// ANTI-PATTERN: có thể lộ nội dung exception.
return ResponseEntity.badRequest()
    .body(Map.of("message", exception.getMessage()));
~~~

Tạo error response với **code/message tĩnh phù hợp ngữ cảnh**, còn lỗi chi tiết chỉ đi vào kênh nội bộ đã được phân loại và redact.

## 6. HTTP response: chỉ xuất trường được phép

### 6.1. Thiết kế response DTO

Một endpoint trả trạng thái đăng nhập có thể chỉ cần:

~~~java
record IdentityStatus(boolean authenticated) {}

@GetMapping("/me")
IdentityStatus currentIdentity() {
    return new IdentityStatus(true);
}
~~~

Đây là snippet đặt trong một @RestController đã được Spring Security bảo vệ. Nó không cần password/hash/email/token để cho frontend biết request đã xác thực.

Một response an toàn trong bài:

~~~json
{
  "authenticated": true
}
~~~

Nếu frontend thật sự cần username, display name hoặc role, hãy quyết định từng trường theo hợp đồng API, quyền người gọi và nguyên tắc tối thiểu. Không để Jackson tự quyết định danh sách trường từ entity hoặc framework object.

### 6.2. Không nhúng password vào trường tưởng an toàn

Một số cách gây rò:

- Trả echo request JSON sau login để debug.
- Trả passwordHash trong /me, /users/{id}, GraphQL hoặc admin export.
- Trả exception message chứa rejected password.
- Trả reset code/token trong response của một endpoint không được thiết kế phát secret.
- Đặt credential trong Location header hoặc query khi redirect.
- Đưa secret vào X-Debug-*, Server-Timing hoặc custom headers.
- Dùng ResponseEntity.ok(loginRequest) hoặc ResponseEntity.ok(userEntity) vì “tiện”.

Có thể dùng các annotation Jackson như JsonProperty(access=WRITE_ONLY) để giảm nguy cơ serializer vô tình ghi field password, nhưng **đó chỉ là lớp dự phòng**: request DTO vẫn có thể bị in bởi toString, AOP, tracing, mapper khác hoặc JSON serializer khác. Biện pháp chính là **response DTO riêng chỉ có trường được phép**.

### 6.3. AuthenticationEntryPoint và lỗi 401

Với HTTP Basic, khi thiếu/sai credentials, AuthenticationEntryPoint có thể tạo HTTP 401. Cần chọn public error body chung, không đưa username hay password do client gửi lên vào body.

Ví dụ expected:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="lesson"
Cache-Control: no-store

{"error":"authentication_required"}
~~~

Không dùng exception.toString() làm body. Trong flow form login, dùng FailureHandler/redirect thống nhất. Khi người dùng đã xác thực nhưng thiếu quyền, đó là Authorization failure, thường HTTP 403; không cần biến mọi 403 thành 401.

### 6.4. Cache, CORS và trình duyệt

Thông tin cá nhân trong /me hoặc response auth cần chính sách caching thích hợp; API nhạy cảm thường dùng **Cache-Control: no-store**. CORS không bảo vệ credential nếu bạn cho phép origin không tin cậy hoặc vô tình gửi dữ liệu nhạy cảm; phải xác định origin và credentials policy.

Không đưa password vào URL vì URL dễ nằm trong browser history, access logs, proxy, referrer hoặc analytics. Hãy dùng HTTPS, request body/header theo protocol thích hợp và bảo vệ cả browser-side console/storage.

## 7. Ví dụ Spring Boot 3.x có thể chạy, không hard-code mật khẩu

Ví dụ này dùng Spring Boot Security với HTTP Basic. **Mật khẩu demo được nhập qua cấu hình runtime**, thay vì viết chuỗi password trong source, file property commit lên Git hoặc lệnh curl có password rõ ràng.

Ứng dụng chỉ giữ encoded password trong InMemoryUserDetailsManager; Controller trả DTO tối giản, log một sự kiện cố định và error handler trả JSON cố định. Nó minh họa các biện pháp ở **tầng ứng dụng**, còn proxy/APM/CI phải được cấu hình riêng.

### 7.1. Tạo project và dependencies

Tạo project **Java 17+, Spring Boot 3.x, Spring MVC/Servlet, Gradle Groovy DSL** bằng Spring Initializr với Gradle Wrapper. Trong phần **dependencies** của build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **phần dependencies trong dự án Boot đã thiết lập plugin/BOM**; không phải build.gradle độc lập. Spring Security Test cần cho httpBasic() MockMvc request post-processor trong test bên dưới.

### 7.2. Java source đầy đủ

Tạo file **src/main/java/com/example/credential/SafeCredentialApplication.java**:

~~~java
package com.example.credential;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeCredentialApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeCredentialApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder, Environment env) {
        // Spring Boot ánh xạ DEMO_AUTH_PASSWORD sang demo.auth.password.
        String password = env.getRequiredProperty("demo.auth.password");

        if (password.isBlank()) {
            throw new IllegalStateException(
                "Missing local demo credential");
        }

        return new InMemoryUserDetailsManager(
            User.withUsername("demo-user")
                .password(encoder.encode(password))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationEntryPoint genericEntryPoint() {
        return (request, response, failure) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader(
                HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"lesson\"");
            response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
            response.getWriter()
                .write("{\"error\":\"authentication_required\"}");
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, AuthenticationEntryPoint genericEntryPoint)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(genericEntryPoint)
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(genericEntryPoint)
                .accessDeniedHandler((request, response, failure) -> {
                    response.setStatus(
                        HttpServletResponse.SC_FORBIDDEN);
                    response.setContentType(
                        MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name());
                    response.setHeader(
                        HttpHeaders.CACHE_CONTROL, "no-store");
                    response.getWriter()
                        .write("{\"error\":\"access_denied\"}");
                })
            )
            .formLogin(form -> form.disable())
            .build();
    }
}

@RestController
class SafeIdentityController {

    private static final Logger log =
        LoggerFactory.getLogger(SafeIdentityController.class);

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    IdentityStatus identity() {
        log.info("event=identity_view outcome=success");
        return new IdentityStatus(true);
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}

record IdentityStatus(boolean authenticated) {}
~~~

Đây là **một file Java hoàn chỉnh trong dự án Spring Boot đã tạo**. Public class SafeCredentialApplication trùng tên file; Controller và record package-private cùng package. Bean PasswordEncoder dùng BCrypt; bean UserDetailsService băm password demo trước khi lưu vào in-memory store.

**Không có password literal trong file Java hoặc build.gradle.** Password được lấy từ cấu hình runtime dưới tên demo.auth.password, có thể được Spring Boot map từ biến môi trường DEMO_AUTH_PASSWORD. Nếu biến cấu hình không tồn tại, ứng dụng fail-fast thay vì bí mật dùng một password mặc định.

### 7.3. Tại sao response không lộ bí mật?

- GET /me trả IdentityStatus(true), không trả Authentication, UserDetails, PasswordEncoder hay UserEntity.
- Không có getter nào trong response DTO đọc raw password hoặc hash.
- Khi login thất bại, entry point trả error code cố định, không dùng failure.getMessage().
- Khi user đúng password nhưng thiếu role ADMIN, handler trả JSON access_denied cố định.
- Logger chỉ in event=identity_view outcome=success, không có user, password, hash, request payload hay headers.

**Giới hạn:** Đây là sự bảo vệ tại code ứng dụng trong ví dụ. Nếu reverse proxy, servlet access log hoặc APM được cấu hình thu thập Authorization/header/body, secret vẫn có thể bị lộ ngoài Controller. Cần áp chính sách log ở toàn bộ đường đi.

### 7.4. Chạy bằng credential cấp từ runtime

Trong môi trường local, truyền một mật khẩu demo tạm thời bằng **DEMO_AUTH_PASSWORD** thông qua môi trường chạy. Không đặt giá trị vào application.properties được commit, Gradle arguments, terminal command line, URL hoặc README.

Ví dụ trong **Bash** cho phiên lab cô lập:

~~~bash
read -r -s -p "Temporary demo password: " DEMO_AUTH_PASSWORD
printf "\n"
export DEMO_AUTH_PASSWORD
./gradlew bootRun
unset DEMO_AUTH_PASSWORD
~~~

Lệnh read -s không echo ký tự khi nhập. Giá trị biến môi trường vẫn tồn tại trong process của shell và ứng dụng trong thời gian chạy; đây là phương án **demo**, không phải thay thế hoàn chỉnh cho Secret Manager trong production. Dừng server sau khi thử.

Trên **Windows PowerShell 5.1+**, có thể nhập không hiển thị:

~~~powershell
$secure = Read-Host "Temporary demo password" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:DEMO_AUTH_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    .\gradlew.bat bootRun
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    Remove-Item Env:DEMO_AUTH_PASSWORD -ErrorAction SilentlyContinue
}
~~~

Dòng chuyển SecureString thành environment variable tạm có nghĩa là raw password tồn tại trong process memory. Không dùng dữ liệu thật; production nên dùng secret store/identity provider theo kiến trúc, kiểm soát quyền đọc environment/process dumps. Việc xóa environment variable không thể đảm bảo mọi bản sao Java String đã bị xóa khỏi JVM heap.

### 7.5. Gọi curl mà không đặt password trong command history

Khi server chạy localhost:8080:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u demo-user http://localhost:8080/me
curl -i -u demo-user http://localhost:8080/admin
~~~

**curl -u demo-user** yêu cầu nhập password trong terminal nếu không truyền phần sau dấu hai chấm. Trên Windows PowerShell có thể cần **curl.exe** vì curl là alias. Tránh dạng curl -u user:password vì command history/process listing có thể lưu nguyên credential.

HTTP Basic mã hóa dạng Base64, **không bảo mật nội dung**. Với mạng thật phải dùng HTTPS/TLS và các kiểm soát phù hợp. Không dùng password demo để truy cập bất kỳ hệ thống thật nào.

### 7.6. Kết quả dự kiến

| Request | HTTP status kỳ vọng | Body |
| --- | --- | --- |
| GET /public anonymous | **200** | public OK |
| GET /me anonymous | **401** | {"error":"authentication_required"} |
| GET /me demo-user password đúng | **200** | {"authenticated":true} |
| GET /me demo-user password sai | **401** | {"error":"authentication_required"} |
| GET /admin demo-user password đúng | **403** | {"error":"access_denied"} |

Trong demo, demo-user chỉ có ROLE_USER. Vì vậy /admin yêu cầu ROLE_ADMIN sẽ trả 403 ngay cả khi password đã xác minh. Nếu client gửi credentials sai tới /public, BasicAuthenticationFilter cũng có thể thử xác thực và trả 401 trước khi permitAll được xét.

Bảng là **kết quả suy ra từ code**, chưa phải output đo từ một server đang chạy trong bài viết. Chính sách HTTP thực tế có thể thay đổi khi thêm filter, exception handler hoặc proxy.

## 8. Kiểm thử MockMvc: credential sinh trong RAM, không commit vào source

Một bài test tốt không cần commit password test cố định, không cần đưa credential vào shell arguments và không cần ghi hash ra console. Với JUnit, có thể **sinh chuỗi tạm bằng UUID ở runtime**; nó không đại diện cho tài khoản thật và chỉ dùng trong test context.

Để kiểm thử app của mục 7, tạo file **src/test/java/com/example/credential/SafeCredentialApplicationTest.java**:

~~~java
package com.example.credential;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeCredentialApplicationTest {

    // Sinh ở runtime: không có secret cố định trong repository.
    private static final String EPHEMERAL =
        UUID.randomUUID().toString();

    @DynamicPropertySource
    static void supplyCredential(DynamicPropertyRegistry registry) {
        registry.add("demo.auth.password", () -> EPHEMERAL);
    }

    @Autowired MockMvc mvc;
    @Autowired UserDetailsService users;

    @Test
    void successResponseAndCapturedLogContainNoPassword(
            CapturedOutput output) throws Exception {

        String encoded = users.loadUserByUsername("demo-user")
            .getPassword();

        MvcResult result = mvc.perform(get("/me")
                .with(httpBasic("demo-user", EPHEMERAL)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.authenticated").value(true))
            .andReturn();

        String body = result.getResponse().getContentAsString();

        assertEquals("{\"authenticated\":true}", body);
        assertFalse(body.contains(EPHEMERAL));
        assertFalse(body.contains(encoded));
        assertFalse(output.getAll().contains(EPHEMERAL));
        assertFalse(output.getAll().contains(encoded));
    }

    @Test
    void failureResponseIsGenericAndDoesNotEchoInput(
            CapturedOutput output) throws Exception {

        String wrongPassword = UUID.randomUUID().toString();

        MvcResult result = mvc.perform(get("/me")
                .with(httpBasic("demo-user", wrongPassword)))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String body = result.getResponse().getContentAsString();

        assertEquals("{\"error\":\"authentication_required\"}", body);
        assertEquals("Basic realm=\"lesson\"",
            result.getResponse()
                .getHeader(HttpHeaders.WWW_AUTHENTICATE));
        assertFalse(body.contains(wrongPassword));
        assertFalse(output.getAll().contains(wrongPassword));
    }

    @Test
    void authorizationFailureDoesNotLeakSecret(
            CapturedOutput output) throws Exception {

        MvcResult result = mvc.perform(get("/admin")
                .with(httpBasic("demo-user", EPHEMERAL)))
            .andExpect(status().isForbidden())
            .andReturn();

        String body = result.getResponse().getContentAsString();

        assertEquals("{\"error\":\"access_denied\"}", body);
        assertFalse(body.contains(EPHEMERAL));
        assertFalse(output.getAll().contains(EPHEMERAL));
    }
}
~~~

### 8.1. Chạy test

~~~bash
./gradlew test
~~~

PowerShell: **.\gradlew.bat test**.

Test dùng **@DynamicPropertySource** để cung cấp demo.auth.password trước khi Spring tạo UserDetailsService trong test context; không cần biến môi trường demo của người phát triển. MockMvc dùng SecurityMockMvcRequestPostProcessors.httpBasic để tạo đúng header, và OutputCaptureExtension để thu log/stdout/stderr mà bài test quan sát được.

### 8.2. Vì sao test không hard-code password?

EPHEMERAL được sinh bằng UUID.randomUUID tại runtime. Test đưa chuỗi này vào property của app, rồi sử dụng nó để gọi HTTP Basic. Code repository chỉ chứa logic sinh credential, không chứa password thử nghiệm cố định hoặc bất kỳ secret production nào.

Đây là cách **giảm nguy cơ lộ test credential công khai**, không phải một cơ chế tạo password production hoàn chỉnh; UUID làm test value là đủ để xác minh cơ chế trong bộ nhớ. Với cần secret thực như API key hay token tích hợp bên thứ ba, dùng **secret manager/CI secret binding** thay vì hard-code vào test fixture.

### 8.3. Test chứng minh những gì?

- GET /me với credential đúng trả DTO chỉ có authenticated=true.
- Body không chứa raw password thử hoặc encoded password trong UserDetails.
- Nhánh sai password trả status 401 và body chung, không echo đầu vào.
- Nhánh đã xác thực nhưng thiếu quyền trả status 403 và body chung.
- Log được OutputCaptureExtension thu trong các lệnh test không chứa raw test password hoặc hash đã lấy.

### 8.4. Test chưa chứng minh những gì?

**Rất quan trọng:** output capture chỉ kiểm tra những log mà extension thu được trong phạm vi test. Nó không tự thấy:

- Raw access log của reverse proxy hoặc API gateway.
- Log của servlet container bên ngoài test process.
- Dữ liệu do agent APM hoặc collector ở production ghi.
- Tracing spans/baggage gửi ra bên ngoài.
- Browser console, HAR, screenshots hay screen recordings.
- Git history và CI logs của các lần build khác.
- Một logging path không được kích hoạt trong ba request test.

Nó cũng không chứng minh password không còn trong JVM heap hoặc không có bản sao ở các lớp cần thiết cho xác thực. **Kết quả test xanh là bằng chứng giới hạn của đường đi được kiểm tra, không phải chứng nhận bí mật tuyệt đối.**

### 8.5. Tránh viết assertion làm lộ secret khi fail

Một assertion so sánh raw password với response body theo cách in cả expected/actual có thể khiến framework in secret vào JUnit failure report nếu test thất bại. Trong ví dụ, ta kiểm tra boolean bằng assertFalse(body.contains(EPHEMERAL)) và không đưa EPHEMERAL vào message của assertion.

Với tool test có snapshot diff, không snapshot request có raw password hoặc full Authorization header. Không attach failure screenshot của form chứa password chưa được che.

## 9. Test fixtures, seed data và dữ liệu công khai

### 9.1. Vì sao “chỉ là mật khẩu test” vẫn phải cẩn thận?

Một mật khẩu mẫu cố định, được commit công khai, có thể bị copy sang staging/production vì tiện. Một số đội còn dùng lại test credential để kết nối database, e2e account hoặc integration service có thật. Khi đó nó không còn là dữ liệu vô hại.

Hãy phân biệt:

- **Unit test thuần:** dùng data sinh ngay trong test, không phụ thuộc account thật.
- **Integration test local:** dùng database/container cô lập, seed user với mật khẩu sinh tạm.
- **End-to-end trên staging:** dùng account riêng, quyền tối thiểu, secret lưu trong CI/secret manager, rotate và teardown.
- **Production smoke test:** dùng cơ chế identity được phép, không đưa credential vào test report hoặc screenshot.

Một trường username demo, fake user ID và tên role có thể xuất hiện trong test data. Nhưng raw password, API key, access token hoặc reset token dùng được phải được xử lý như secret, dù môi trường chỉ là staging.

### 9.2. Tránh các bề mặt test thường bị bỏ sót

| Nơi | Nguy cơ | Cách giảm rủi ro |
| --- | --- | --- |
| src/test/resources/*.json | Password literal được commit | Tạo credential khi test setup, dùng secret fixture an toàn |
| application-test.properties | DB/API password cố định | CI secret injection hoặc Testcontainers credential tạm |
| Postman collection/environment | Export kèm token/password | Tách secret variables, kiểm tra bản export |
| JUnit failure report | Assertion diff in dữ liệu nhạy cảm | Không đưa secret vào expected/actual/message |
| MockMvc print() / andDo(print()) | Có thể in request headers/body | Không print request auth thật hoặc che trước |
| RestAssured logging | Log entire request/response | Tắt hoặc redact credentials |
| WireMock request journal | Lưu Authorization/body | Giới hạn dữ liệu và retention |
| Testcontainers logs | DB/container output có credential | Không dump env/config/command secrets |
| CI console | Command-line args, echo, set -x | Dùng secret binding, mask và không echo |
| Screenshot/video e2e | Password field hoặc token UI | Mask input, không capture trang chứa secret |
| HAR/network recordings | Authorization/cookies/bodies | Sanitize hoặc không export |
| Coverage/test artifact | Embedded captured output | Scan report trước khi publish |
| Shared sample YAML/.env | Password bị đẩy lên Git | Ignore secret file, cung cấp file example chỉ có key |

### 9.3. Đừng dựa vào .gitignore cho file đã commit

Nếu secret đã được Git theo dõi, thêm nó vào .gitignore **không xóa bản sao trong repository history hoặc clone cũ**. Phải coi credential đã lộ, thu hồi hoặc rotate và cân nhắc xử lý history/artifacts theo chính sách, quyền và tác động tới cộng tác viên.

Không tự force-push history trên repository dùng chung nếu chưa có quy trình điều phối; thay lịch sử làm các clone và PR hiện có cần cập nhật. **Rotation/revocation là việc ưu tiên khi có secret dùng được đã lộ**, không phải chỉ xóa một dòng source code.

## 10. Logging ở lớp hạ tầng và observability

### 10.1. Reverse proxy và ingress

Reverse proxy có thể ghi request path/query, response status, latency, client IP và user agent. Nếu hệ thống lỡ truyền reset token/password trong query, access logs có thể lưu nó rất lâu, ngay cả khi Java app không log.

Ở API gateway, không bật body logging cho login/reset/token endpoints. Tránh collect Authorization, Cookie, Set-Cookie và custom auth headers. Xem chính sách retention, quyền truy cập log và dữ liệu được forward tới bên thứ ba.

### 10.2. OpenTelemetry, tracing và MDC

Tracing giúp theo dõi request end-to-end nhưng **span attributes, baggage, MDC** cũng có thể được lưu trữ và nhân bản. Không đưa password, raw token, full Authorization header hoặc request body vào attributes. Chỉ đưa metadata đã được duyệt, ví dụ route template, status và server-generated traceId.

Với userId, sessionId, IP hoặc email, cần chính sách riêng về dữ liệu cá nhân và quyền truy cập. Đừng xem userId là “không nhạy cảm” chỉ vì không phải password.

### 10.3. Logs tập trung và backup

Nếu secret vào log, nó có thể đi qua buffer cục bộ, collector, message queue, index, archive và backup. Xóa log trên một máy không xóa được tất cả bản sao.

Thiết kế:

1. **Ngăn trước khi ghi:** allowlist fields trong app và giảm logging body/header.
2. **Redact khi thu thập:** thêm rule ở gateway/collector cho trường hợp lọt qua.
3. **Hạn chế quyền đọc:** phân quyền dashboards, điều tra và export.
4. **Giới hạn retention:** đủ cho điều tra/tuân thủ nhưng không giữ vô hạn.
5. **Cảnh báo secret detection:** phát hiện credential pattern, kiểm soát false positives.
6. **Kế hoạch xử lý sự cố:** rotate, vô hiệu hóa và truy tìm nơi lưu/đã tải xuống.

### 10.4. Có nên hash username/password để log không?

**Không bao giờ hash trực tiếp password rồi log hash** như một correlation ID. Hash có thể bị dùng cho offline guessing. Với username/email, nếu thật sự cần liên kết events, có thể dùng một định danh nội bộ có kiểm soát hoặc pseudonymization được thiết kế theo policy; tránh tự dùng SHA-256(email) vì dictionary attack có thể tái xác định email phổ biến.

Đối với sự kiện login thất bại từ anonymous, đôi khi chỉ event type, request ID, client risk signals đã được giới hạn và counters đủ cho điều tra. Chi tiết cần thiết khác phải được bảo vệ trong audit store riêng.

## 11. Khác nhau giữa redaction và data minimization

| Chiến lược | Ý nghĩa | Rủi ro nếu chỉ dùng riêng |
| --- | --- | --- |
| **Data minimization** | Không tạo/giữ/chuyển secret khi không cần | Có thể bỏ sót đường log đã tồn tại |
| **Allowlist fields** | Chỉ chọn trường an toàn để log/return | Cần duy trì schema và review khi thêm field |
| **Redaction/masking** | Xóa hoặc che secret trước khi ghi | Regex có thể bỏ sót nested data/format mới |
| **Encryption at rest** | Bảo vệ log/database khi lưu | Người có quyền giải mã vẫn có thể thấy secret |
| **Access control** | Giới hạn ai xem log/artifact | Không sửa việc secret đã bị thu thập |
| **Retention/rotation** | Giảm thời gian giữ dữ liệu | Không tránh được rò rỉ ngay khi ghi |
| **Secret scanning** | Phát hiện secret trong source/artifact | Không chứng minh đã chặn mọi loại credential |

Khi phát triển, nên kết hợp nhiều lớp. Ví dụ **Controller trả DTO không chứa hash** là tốt hơn việc trả nguyên entity rồi hy vọng serializer tự che passwordHash; thêm Jackson write-only/redaction là lớp phụ để giảm rủi ro do thay đổi sau này.

## 12. Các hành vi nguy hiểm trong code và cách thay

### 12.1. Log toàn bộ request object

**Sai:**

~~~java
log.info("password change request={}", changePasswordRequest);
~~~

**Đúng hơn:**

~~~java
log.info("event=password_change_requested");
~~~

Nếu cần correlation, thêm traceId server-generated đã được validate. Không log raw currentPassword/newPassword dù event thành công hay thất bại.

### 12.2. Trả UserDetails hoặc UserEntity

**Sai:**

~~~java
@GetMapping("/account")
Object account(Authentication authentication) {
    return authentication.getPrincipal();
}
~~~

**Đúng hơn:**

~~~java
record AccountView(boolean authenticated) {}

@GetMapping("/account")
AccountView account() {
    return new AccountView(true);
}
~~~

Các snippet nằm trong @RestController có imports phù hợp, không phải file Java độc lập. Ví dụ đúng không lấy password hoặc hash từ Authentication.

### 12.3. Đính kèm raw input vào error

**Sai:**

~~~java
throw new IllegalArgumentException(
    "Rejected password value=" + rawPassword);
~~~

**Đúng hơn:**

~~~java
throw new IllegalArgumentException(
    "Password did not satisfy the configured policy");
~~~

Ứng dụng thật nên dùng validation/error code chuẩn và bảo đảm nội dung không chứa giá trị đầu vào. Chú ý exception có thể bị framework tự log kèm message.

### 12.4. Cấu hình logging filter quá rộng

**Nguy hiểm:** thêm filter ghi toàn bộ headers + body cho mọi URL để debug. Dù Controller không in gì, filter chạy trước có thể ghi raw password từ /login, /change-password hoặc Authorization header.

**Hướng sửa:** tắt body/header capture trên các đường nhạy cảm và ưu tiên record allowlist method/route/status/duration. Với request logging framework có option includePayload/includeHeaders, đánh giá tác động trước khi bật và không xem default của mọi version đều giống nhau.

### 12.5. Dùng test password cố định từ tài liệu công khai cho môi trường staging

**Sai về quy trình:** nhập một password đã có trong README/demo vào tài khoản staging có quyền thật rồi không đổi lại.

**Hướng đúng:** tạo account test riêng, password qua secret manager, scope/TTL rõ, không export; có teardown/rotation. Test data công khai chỉ mô tả **cách sinh**, không chứa một credential còn sử dụng được.

## 13. Quy trình review Pull Request và CI

Một PR thay đổi login/password handling nên được review với các câu hỏi:

1. Request DTO có password, confirmation hoặc OTP không? Nó có bị log qua toString/AOP không?
2. Có filter/interceptor bật request/response body logging không?
3. Có logging config mới bật TRACE, includeHeaders/includePayload hoặc serialize Authentication không?
4. Có endpoint trả UserDetails, Authentication, Jwt, OidcUser hoặc entity chứa hash không?
5. Có global exception handler trả exception.getMessage hoặc rejectedValue không?
6. Có secret/credential thật trong source, test fixtures, YAML, JSON, SQL seed, Postman hoặc docs không?
7. Test có andDo(print()), debug capture, snapshot diff hoặc failure message chứa raw secret không?
8. E2E screenshots, browser HAR hoặc pipeline artifacts có chứa token/cookie không?
9. CI dùng command line hoặc environment dumps có in credential ra console không?
10. Logs/metrics/traces xuất sang nhà cung cấp nào? Có access control và retention chưa?
11. Nếu phát hiện leak, có quy trình rotate/revoke ngay và ngăn tái xuất hiện không?
12. Có test response contract và audit logs cho các nhánh login success/failure/403 không?

### 13.1. Secret scanning

Dùng secret scanning trong CI/pre-commit phù hợp repo để phát hiện API key, token, private key hoặc password cấu hình. Nó rất có ích nhưng không bắt được mọi password, nhất là chuỗi ngắn có tên không giống secret.

Vì vậy kết hợp:

- Static analysis để phát hiện log nhạy cảm và trả raw entities.
- Code review các luồng auth/error/serialization.
- Tests theo hợp đồng HTTP và dữ liệu log.
- Kiểm tra artifacts được upload sau build.
- Rà soát cấu hình APM/proxy/logging collector.

Không đưa giá trị secret thật làm “test case” công khai để xem scanner có bắt được không. Dùng synthetic examples không có giá trị sử dụng thực tế, hoặc công cụ kiểm thử trong môi trường riêng được phân quyền.

### 13.2. CI masking không phải biện pháp duy nhất

CI có chức năng mask secret nhưng có thể bị qua mặt bởi biến đổi chuỗi (Base64, URL encode), split string, output dạng JSON hoặc tooling khác. Không chủ động echo secret rồi hy vọng CI che. Những người có quyền xem pipeline, download artifacts hoặc export logs có thể nhìn thấy dữ liệu trước/trong quá trình mask ở một số hệ thống.

### 13.3. Kiểm tra báo cáo thử nghiệm trước khi publish

Trước khi gửi test report, screenshots, sample logs hoặc README ra ngoài tổ chức, kiểm tra:

- Có HTTP Authorization/Cookie/Set-Cookie nào không?
- Có stack trace chứa rejectedValue hoặc raw request body không?
- Có encoded password hash hay reset token không?
- Có database connection string chứa credential không?
- Có credential trong image, video, HAR hoặc file đính kèm không?
- Có token từ chính môi trường kiểm thử còn hạn sử dụng không?
- Có ID cá nhân thật vượt yêu cầu chia sẻ không?

Nếu có dữ liệu thật, xử lý theo quy trình bảo mật và chỉ chia sẻ phiên bản đã được làm sạch; không chỉ đổi tên file thành “sanitized”.

## 14. Khi phát hiện mật khẩu hoặc token đã vào log/repository

Cần phân biệt **biện pháp ngăn lặp lại** với **xử lý dữ liệu đã lộ**.

1. **Đánh giá secret còn sử dụng được không:** raw password, refresh token, API key, private key hay reset code? Xác định nguồn và phạm vi bị ảnh hưởng.
2. **Thu hồi/rotate:** với credential còn hiệu lực, ưu tiên vô hiệu hóa/đổi mật khẩu, key hoặc token theo quy trình được phép. Nếu password dùng lại ở nơi khác, xem xét hướng dẫn người dùng đổi.
3. **Xác định nơi secret đã đi qua:** app log, proxy, collector, SIEM, APM, CI, artifacts, Git history, external exports.
4. **Giới hạn truy cập và lưu trữ:** ngăn tiếp tục phát tán, áp retention/deletion theo nghĩa vụ và quyền hạn.
5. **Sửa nguồn phát tán:** bỏ log object, thay response DTO, cập nhật filter/serializer, không chỉ thêm regex sau log.
6. **Xây test phòng hồi quy:** dùng secret test tạm, xác minh body/log an toàn, scan artifact.
7. **Audit và thông báo:** làm theo quy trình ứng phó của tổ chức, nghĩa vụ pháp lý và phân loại sự cố.

**Xóa một dòng log hoặc commit không khôi phục tính bí mật của credential đã lộ.** Đặc biệt với raw password/access token, cần nghĩ đến bản sao ở log aggregation, backup và clone cũ. Không tự xóa hoặc viết lại lịch sử Git dùng chung khi chưa có cơ chế phối hợp.

Nếu chỉ có **password hash** bị lộ, không thể coi là vô hại; cần đánh giá thuật toán/cost, quyền xem dữ liệu, khả năng đoán offline, nguy cơ password yếu/tái sử dụng và phương án giảm thiểu phù hợp.

## 15. Những hiểu nhầm thường gặp

**“Tôi chỉ log request ở DEBUG, production log level INFO nên an toàn.”** Không chắc. Developer có thể bật DEBUG để điều tra, service khác có mức log riêng hoặc dữ liệu đã ghi ở môi trường staging thật. Phải sửa nguyên nhân và kiểm soát configuration.

**“Authentication.toString tự che credentials nên có thể log mọi Authentication.”** Không nên. Principal/details và custom objects vẫn có thể chứa dữ liệu nhạy cảm.

**“Hash BCrypt không phải mật khẩu, có thể public để debug.”** Sai. Hash là dữ liệu credential nhạy cảm, có giá trị với offline guessing nếu lộ.

**“Chỉ cần @JsonIgnore trên field password.”** Chưa đủ. Nó không bảo vệ các serializer khác, logs, toString, tracing, cache hoặc field khác.

**“Test dùng password giả nên không sao nếu in ra CI.”** Không phải lúc nào cũng đúng; fixture có thể bị tái sử dụng hoặc test dùng tài khoản staging thật. Nên không log secret và sinh/tiêm credential từ cơ chế được bảo vệ.

**“Không có lệnh log trong Controller thì password không vào log.”** Sai. Proxy, filter, APM, request logging, exception và container có thể ghi dữ liệu.

**“Đổi tên key password thành p sẽ qua được scanner.”** Đó là che giấu lỗi, không giảm rủi ro.

**“Secret trong biến môi trường là an toàn tuyệt đối.”** Không. Environment có thể bị lộ qua process inspection, crash dump hoặc diagnostics nếu quyền/quy trình sai. Nó giảm nguy cơ commit vào source khi dùng đúng, nhưng production cần secret management thích hợp.

**“Test response không chứa password chứng minh password đã bị xóa khỏi JVM.”** Sai. Test chỉ kiểm tra đúng kênh output được quan sát, không bảo đảm quản lý bộ nhớ.

**“Không log gì thì audit tốt.”** Không. Cần log các sự kiện bảo mật an toàn và có cấu trúc, đồng thời bảo vệ log khỏi lộ secret.

## 16. Bài tập tự thực hành và câu hỏi

### 16.1. Bài tập A — Rà soát lộ credential trong DTO

Một API trả UserEntity có trường passwordHash và phone. Hãy đổi response thành DTO chỉ chứa những trường giao diện được quyền xem. Viết MockMvc test bảo đảm response không có passwordHash hoặc trường nhạy cảm. Không dùng một password thật làm fixture.

### 16.2. Bài tập B — Audit login thất bại

Định nghĩa event auth.failure với request ID, result và reason category nội bộ. Chỉ dùng metadata đã được cho phép, không đưa username/password/token vào log mặc định. Thử bật DEBUG ở môi trường test và rà soát log do filter/exception sinh.

### 16.3. Bài tập C — Kiểm tra CI artifacts

Lấy một pipeline chạy trên dữ liệu **giả lập trong môi trường được phân quyền**. Kiểm tra JUnit XML, build console, screenshots, HTTP recordings và log collector để xác nhận không có password/token. Khi test cố ý tạo một credential tạm, bảo đảm output không in giá trị đó.

### 16.4. Câu hỏi và đáp án

**Câu 1.** Vì sao log loginRequest bằng toString có thể nguy hiểm?  
**Đáp:** Request có thể chứa raw password; Java record/Lombok toString có thể in field đó.

**Câu 2.** BCrypt hash có nên được trả về /me không?  
**Đáp:** Không. Hash là dữ liệu credential nhạy cảm và không phục vụ giao diện xác định user.

**Câu 3.** Vì sao không được log HTTP Basic Authorization header?  
**Đáp:** Base64 giải mã trực tiếp ra username/password.

**Câu 4.** Nếu Controller không log, proxy vẫn có thể làm lộ mật khẩu không?  
**Đáp:** Có, nhất là khi bật headers/body logging hoặc secret nằm trong URL.

**Câu 5.** Có nên dùng ResponseEntity.ok(authentication) để debug?  
**Đáp:** Không. Framework object có thể chứa principal, credentials, details và token.

**Câu 6.** PasswordEditor/PasswordEncoder dùng gì để so password?  
**Đáp:** PasswordEncoder.matches(rawPassword, storedHash) trong cơ chế authentication phù hợp; không cần trả hash ra client.

**Câu 7.** Tại sao test dùng UUID.randomUUID sinh password?  
**Đáp:** Tránh commit một giá trị credential test cố định; test chỉ cần một credential tạm để kiểm chứng.

**Câu 8.** OutputCaptureExtension kiểm tra được mọi proxy/APM logs chứ?  
**Đáp:** Không. Nó chỉ quan sát những log/stdout/stderr trong phạm vi nó capture ở test.

**Câu 9.** Vì sao assertFalse(body.contains(secret)) có lợi hơn assertEquals(secret, body)?  
**Đáp:** Nó tránh đưa giá trị secret vào expected/actual của failure diff khi test sai.

**Câu 10.** Nếu credential đã bị commit, thêm .gitignore có đủ không?  
**Đáp:** Không. Credential có thể vẫn nằm trong history/clones; cần rotate/revoke và xử lý bản sao.

**Câu 11.** Access denied 403 có nghĩa mật khẩu sai không?  
**Đáp:** Không. Một request đã xác thực có thể thiếu role hoặc quyền nghiệp vụ.

**Câu 12.** Chỉ dùng regex để che trường password có đủ an toàn không?  
**Đáp:** Không. Secret có thể nằm ở header, object nested, exception, token hoặc key tên khác; cần allowlist.

**Câu 13.** Có nên để raw password trong URL để dễ kiểm thử curl không?  
**Đáp:** Không. URL dễ nằm trong history, logs, referrer, APM hoặc analytics.

**Câu 14.** Có cần log authentication success/failure không?  
**Đáp:** Nên có audit/monitoring hợp lý, nhưng chỉ gồm metadata tối thiểu được phép và không chứa credentials.

**Câu 15.** Nếu test xanh và response không có secret, có thể khẳng định production không rò rỉ không?  
**Đáp:** Không. Cần review filter/proxy/CI/APM, error handlers, log settings và kiểm thử trên đường đi thực tế.

## 17. Checklist cuối trước khi triển khai

- [ ] Không hard-code raw password/API key/token dùng được vào source, example, fixture, YAML hoặc Postman exports.
- [ ] Không log toàn bộ request DTO, Authentication, UserDetails, UserEntity, Jwt/OidcUser hoặc password hash.
- [ ] Không log Authorization, Cookie, Set-Cookie, token/reset link hoặc credential từ query/body.
- [ ] Kiểm tra Java record/Lombok toString và AOP interception trên code có field nhạy cảm.
- [ ] Dùng response DTO allowlist; không serialize entity/framework object.
- [ ] Error response dùng code/message phù hợp, không echo input/exception/rejectedValue.
- [ ] UserDetailsService/provider dùng encoded password; Controller không tự trả hash.
- [ ] Dùng TLS, hạn chế cache, session/token và cấu hình CORS phù hợp.
- [ ] Kiểm tra log settings ở reverse proxy, API gateway, Actuator, APM, tracing và error reporting.
- [ ] Test credential được sinh ở runtime hoặc lấy từ secret manager với quyền tối thiểu.
- [ ] MockMvc/RestAssured/test reports không in Authorization/body nhạy cảm khi failure.
- [ ] Kiểm tra CI artifacts, screenshots, HAR, log archive và exports trước khi chia sẻ.
- [ ] Có secret scanning + code review + tests; không chỉ dựa vào regex masking.
- [ ] Có quy trình rotate/revoke khi secret bị lộ và quản lý retention/backup.
- [ ] Log đủ metadata để phát hiện tấn công nhưng không thu thập dữ liệu vượt nhu cầu.

## 18. Tài liệu tham khảo

- OWASP Logging Cheat Sheet (Data to Exclude, log event design): https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Secrets Management Cheat Sheet (CI/CD, vòng đời secret): https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Boot — Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot — HTTP Exchanges actuator API: https://docs.spring.io/spring-boot/api/rest/actuator/httpexchanges.html
