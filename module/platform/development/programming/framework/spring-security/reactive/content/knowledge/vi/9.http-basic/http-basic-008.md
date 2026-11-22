# Tùy chỉnh phản hồi lỗi HTTP Basic cho REST API trong Spring Security Reactive

## 1. Mục tiêu và tình huống

Một REST API sử dụng **HTTP Basic Authentication** thường cần phản hồi có cấu trúc ổn định để frontend, ứng dụng di động hoặc hệ thống tích hợp xử lý tự động. Nếu request thiếu tên đăng nhập/mật khẩu, gửi credential sai, hoặc đã đăng nhập nhưng không có quyền, việc chỉ trả mã HTTP trống, trang HTML hoặc nội dung lỗi nội bộ làm client khó phân biệt nguyên nhân và dễ lộ thông tin.

Bài này trình bày cách **tùy chỉnh lỗi HTTP Basic trong Spring Security WebFlux (reactive)** mà vẫn bảo vệ dữ liệu và tuân thủ ngữ nghĩa HTTP:

1. Phân biệt **401 Unauthorized** và **403 Forbidden** trong luồng authentication/authorization.
2. Hiểu vai trò của **WWW-Authenticate: Basic realm="..."** ở phản hồi 401.
3. Phân biệt **ServerAuthenticationEntryPoint**, **ServerAccessDeniedHandler**, **ServerAuthenticationFailureHandler** và bộ xử lý lỗi controller.
4. Cấu hình một JSON error body ổn định, Content-Type đúng, chính sách tránh cache và thông điệp an toàn.
5. Xử lý cả trường hợp **không gửi credential** lẫn **gửi sai credential**, tránh chỉ chỉnh một nửa luồng.
6. Viết demo Java 17+ bằng Spring Boot 3.3.5, WebFlux, BCrypt và HTTP Basic; quan sát bằng curl và WebTestClient.
7. Nhận biết các lỗi phổ biến: dùng API servlet thay API reactive, trả 403 cho credential sai, quên challenge header, trả stack trace hay lộ password trong JSON.

**Đích cuối cùng:** client nhận lỗi có cấu trúc rõ ràng, nhưng không được lấy thêm quyền hoặc thấy thông tin nhạy cảm chỉ vì ta thay cách trình bày lỗi.

## 2. 401 và 403 khác nhau ở đâu?

| Tình huống | Authentication | Authorization | HTTP mong đợi |
| --- | --- | --- | --- |
| Không có Authorization header trên endpoint cần login | Chưa có danh tính xác thực hợp lệ | Endpoint yêu cầu authenticated | **401** |
| Authorization Basic có username/password không đúng | Xác thực thất bại | Không có danh tính hợp lệ để đi tiếp | **401** |
| User đã xác thực nhưng thiếu ROLE_ADMIN | Thành công | Bị từ chối quyền | **403** |
| User đã xác thực và đủ quyền | Thành công | Cho phép | **200** hoặc status nghiệp vụ khác |
| Backend identity provider/database không khả dụng | Không xác minh được vì sự cố kỹ thuật | Không được tự cấp quyền | **5xx** phù hợp, không mặc định 401 |
| URL không tồn tại sau khi đã vượt qua security policy | Có thể đã xác thực | Policy tùy ứng dụng | **404**, không biến mọi 404 thành lỗi đăng nhập |

Tên HTTP **401 Unauthorized** có thể gây nhầm: về ý nghĩa thực tế đây là trường hợp **thiếu hoặc không có bằng chứng xác thực hợp lệ**. **403 Forbidden** là trường hợp caller không được phép thực hiện tác vụ, điển hình là caller đã xác thực nhưng không đủ authority.

Một JSON contract đơn giản:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="reactive-api"
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

Với người đã đăng nhập nhưng không có quyền:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

**Chú ý:** 403 **không cần** thêm challenge Basic trong mẫu xử lý thông thường. Gửi challenge ở mọi 403 khiến client hiểu nhầm đổi mật khẩu có thể tạo quyền mà chính sách chưa cấp.

JSON nên có **mã lỗi máy đọc được** ổn định (code), còn message là lời giải thích an toàn. Có thể bổ sung requestId, timestamp hay trường details do hệ thống kiểm soát, nhưng không nên tùy tiện echo header Authorization hoặc text của exception.

## 3. Vì sao 401 cần WWW-Authenticate?

HTTP Basic hoạt động theo cơ chế challenge-response. Khi server yêu cầu xác thực, **401 phải có ít nhất một challenge trong WWW-Authenticate** theo HTTP Semantics. Với scheme Basic, challenge có **realm** theo RFC 7617. Ví dụ:

~~~text
WWW-Authenticate: Basic realm="reactive-api"
~~~

- **Basic** nói client biết đây là phương thức username/password Basic.
- **realm** xác định không gian bảo vệ mà server yêu cầu credential.
- Realm nên là một chuỗi tĩnh do hệ thống kiểm soát; không lấy từ tham số URL/header do client cung cấp.
- **Authorization: Basic ...** từ client chứa Base64 của username:password, **không mã hóa bảo mật**. Cần HTTPS/TLS.

Nhiều HTTP client dùng challenge để quyết định có gửi lại credential hay không. Một số trình duyệt có thể hiện hộp thoại HTTP Basic khi thấy WWW-Authenticate. Nếu bỏ header chỉ để ngăn popup, bạn đã đánh đổi tính tương thích với HTTP Basic/HTTP 401. Nếu muốn đăng nhập giao diện tùy biến mà không dựa vào Basic challenge, nên cân nhắc **cơ chế xác thực phù hợp** thay vì âm thầm làm hỏng hợp đồng Basic.

Trong demo, phản hồi 401 **giữ challenge** và đổi body thành JSON. Đây là cách thân thiện với API client mà vẫn phản ánh đúng chuẩn. Khác biệt trong hành vi dialog của từng trình duyệt là đặc tính client, không phải lỗi của JSON.

## 4. Luồng bảo mật WebFlux và điểm can thiệp

Trong Spring Security **Reactive**, request đi qua **SecurityWebFilterChain**. Mô hình khái niệm:

~~~text
Request GET /api/me
        |
        v
WebFlux SecurityWebFilterChain
        |
        +-- HTTP Basic AuthenticationWebFilter
        |       |
        |       +-- Header Basic hợp lệ?
        |       |       |
        |       |       +-- có: ReactiveAuthenticationManager xác minh
        |       |       |       |
        |       |       |       +-- sai -> authentication failure
        |       |       |       +-- đúng -> SecurityContext / chain tiếp tục
        |       |       |
        |       |       +-- không có Basic -> bỏ qua lần thử ở filter này
        |       |
        v
AuthorizationWebFilter / exception translation
        |
        +-- Chưa xác thực nhưng endpoint cần login -> entry point (401)
        |
        +-- Đã xác thực nhưng thiếu quyền -> access denied handler (403)
        |
        +-- Đủ quyền -> controller/service
~~~

Sơ đồ đơn giản hóa thứ tự nội bộ và không phải lời cam kết mọi lỗi sẽ được xử lý ở cùng một handler. Về mặt tùy chỉnh, cần hiểu các hợp đồng:

| Điểm mở rộng reactive | Interface/lớp | Khi sử dụng |
| --- | --- | --- |
| Bắt đầu yêu cầu xác thực / lỗi chưa có credential hợp lệ | **ServerAuthenticationEntryPoint** | Viết status 401, WWW-Authenticate và JSON |
| User đã xác thực nhưng không đủ quyền | **ServerAccessDeniedHandler** | Viết status 403 và JSON |
| Một lần thử authentication cụ thể bị lỗi | **ServerAuthenticationFailureHandler** | Xử lý thất bại trong AuthenticationWebFilter; thường ủy quyền cho entry point |
| Cấu hình vị trí xử lý lỗi ủy quyền | **ServerHttpSecurity.exceptionHandling(...)** | Đăng ký entry point/denied handler |
| Cấu hình lỗi của HTTP Basic | **ServerHttpSecurity.httpBasic(...)** | Thiết lập entry point/failure handler cho Basic |
| Mã nghiệp vụ ở controller | **@RestControllerAdvice** / WebFlux exception handlers | Xử lý lỗi nghiệp vụ sau routing; không thay thế toàn bộ lỗi từ security filters |

**Vì sao cấu hình ở hai nơi?** Khi thiếu credential, bộ kiểm tra quyền có thể chuyển đến entry point của **exceptionHandling**. Khi đã gửi Basic credential sai, chính filter xác thực có thể xử lý thất bại theo entry point/failure handler của **httpBasic**. Chỉ chỉnh một trong hai nơi có thể tạo kết quả JSON không nhất quán.

Trong bài này dùng **cùng một ServerAuthenticationEntryPoint** cho cả hai luồng, và **một ServerAccessDeniedHandler riêng** cho 403.

### 4.1. API nào là servlet, API nào là reactive?

| Không dùng trực tiếp cho WebFlux | Đúng loại reactive |
| --- | --- |
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| AuthenticationEntryPoint với HttpServletRequest/HttpServletResponse | ServerAuthenticationEntryPoint với ServerWebExchange |
| AccessDeniedHandler của servlet | ServerAccessDeniedHandler |
| OncePerRequestFilter | WebFilter / AuthenticationWebFilter |

Các ví dụ dùng **jakarta.servlet.http.HttpServletResponse** thuộc Servlet stack, sẽ không ghép trực tiếp vào ứng dụng chỉ dùng spring-boot-starter-webflux. Khi tìm hướng dẫn trên mạng, luôn kiểm tra đường dẫn package và signature.

## 5. Thiết kế JSON error contract cho API

Ví dụ chọn một cấu trúc tối thiểu:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Authentication required"
}
~~~

và:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Access denied"
}
~~~

Các yêu cầu chất lượng:

- **Status phải đúng**: 401 cho authentication, 403 cho authorization, 5xx cho lỗi nội bộ không thể xác minh vì hỏng hạ tầng.
- **Content-Type**: application/json; byte body sử dụng UTF-8.
- **Header challenge**: đặt WWW-Authenticate có Basic realm ở mọi nhánh 401 tương ứng.
- **Không cache**: Cache-Control: no-store để hạn chế lưu phản hồi có liên quan trạng thái xác thực.
- **Không tiết lộ**: tuyệt đối không đưa username có/không tồn tại, raw password, Basic header, token, stack trace, class lỗi hay nội dung truy vấn DB vào JSON.
- **Ổn định hợp đồng**: client kiểm tra code thay vì phân tích message thay đổi theo ngôn ngữ.
- **Đúng quyền**: lỗi trả ra không được làm pipeline tiếp tục phát tài nguyên được bảo vệ.

Nếu muốn dùng **application/problem+json (RFC 9457)**, hãy xây theo đúng cấu trúc problem details (type, title, status, detail, instance) và content type tương ứng, không chỉ đổi header trong khi body vẫn là schema tự đặt. Bài demo chọn application/json để giữ trọng tâm vào HTTP Basic security.

Không phản hồi lỗi bằng status 200 và body {"success":false}. Điều đó che giấu kết quả HTTP khỏi client, proxy, metric và chính sách retry.

## 6. Hai lỗi 401: thiếu credential và credential không hợp lệ

**Thiếu Authorization header:** AuthenticationWebFilter của HTTP Basic không tạo được đề nghị xác thực từ header Basic. Khi request đi tới endpoint yêu cầu authenticated, luồng authorization sẽ yêu cầu xác thực thông qua entry point.

**Sai username/password:** converter đọc Basic credential và manager xác minh thất bại. Filter xác thực chuyển lỗi tới cơ chế xử lý thất bại tương ứng, dùng entry point đã chỉ định.

Tại client, cả hai có thể nhận cùng JSON:

~~~json
{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

Không công khai thông tin “tên người dùng đúng, mật khẩu sai” so với “tài khoản không tồn tại”. Phân loại chi tiết nếu cần nên nằm ở log/metric server đã loại bỏ dữ liệu nhạy cảm, có chống enumeration và giới hạn tải.

**Không bắt mọi AuthenticationException rồi trả 401 một cách mù quáng**: có loại thể hiện sự cố dịch vụ xác thực, chẳng hạn AuthenticationServiceException. Trong Spring Security, handler mặc định có thể phát tán lỗi kỹ thuật thay vì biến nó thành Basic challenge; khi viết custom failure handler, phải giữ nguyên phân biệt này và ánh xạ 5xx phù hợp. Demo không mô phỏng lỗi hệ thống danh tính.

## 7. Demo hoàn chỉnh Java 17+: Spring Boot WebFlux trả JSON 401/403

Ví dụ dùng **Spring Boot 3.3.5**, **Java 17+**, Gradle 8.x, **spring-boot-starter-webflux** và **spring-boot-starter-security**. Hai user thử nghiệm:

| User | Password demo | Authority |
| --- | --- | --- |
| reader | reader-pass | ROLE_USER |
| admin | admin-pass | ROLE_USER, ROLE_ADMIN |

API:

- GET **/public/ping**: công khai.
- GET **/api/me**: chỉ cần đăng nhập.
- GET **/api/admin/report**: phải có ROLE_ADMIN.

Cấu trúc file:

~~~text
basic-json-errors/
├── settings.gradle
├── build.gradle
├── src/main/java/example/basic/BasicJsonErrorsApplication.java
├── src/main/java/example/basic/SecurityConfig.java
├── src/main/java/example/basic/ApiController.java
└── src/test/java/example/basic/BasicErrorResponseTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'basic-json-errors'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.3. BasicJsonErrorsApplication.java

~~~java
package example.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicJsonErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicJsonErrorsApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfig.java — trung tâm bài học

~~~java
package example.basic;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    private static final String BASIC_CHALLENGE =
            "Basic realm=\"reactive-api\"";

    private static final String UNAUTHORIZED_JSON =
            "{\"code\":\"AUTHENTICATION_REQUIRED\","
                    + "\"message\":\"Authentication required\"}";

    private static final String FORBIDDEN_JSON =
            "{\"code\":\"ACCESS_DENIED\","
                    + "\"message\":\"Access denied\"}";

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ServerAuthenticationEntryPoint restAuthenticationEntryPoint() {
        return (exchange, authError) ->
                writeJsonError(exchange,
                        HttpStatus.UNAUTHORIZED,
                        UNAUTHORIZED_JSON,
                        true);
    }

    @Bean
    ServerAccessDeniedHandler restAccessDeniedHandler() {
        return (exchange, deniedError) ->
                writeJsonError(exchange,
                        HttpStatus.FORBIDDEN,
                        FORBIDDEN_JSON,
                        false);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerAuthenticationEntryPoint restAuthenticationEntryPoint,
            ServerAccessDeniedHandler restAccessDeniedHandler) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(basic ->
                        basic.authenticationEntryPoint(
                                restAuthenticationEntryPoint))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                restAuthenticationEntryPoint)
                        .accessDeniedHandler(
                                restAccessDeniedHandler))
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    private static Mono<Void> writeJsonError(
            ServerWebExchange exchange,
            HttpStatus status,
            String json,
            boolean includeBasicChallenge) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);

        HttpHeaders headers = response.getHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set(HttpHeaders.CACHE_CONTROL, "no-store");

        if (includeBasicChallenge) {
            headers.set(
                    HttpHeaders.WWW_AUTHENTICATE,
                    BASIC_CHALLENGE);
        }

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        headers.setContentLength(bytes.length);
        return response.writeWith(Mono.just(
                response.bufferFactory().wrap(bytes)));
    }
}
~~~

**Điểm quan trọng trong code:**

1. **restAuthenticationEntryPoint** trả 401 với JSON cố định và Basic challenge. Không dùng raw exception message làm body.
2. **restAccessDeniedHandler** trả 403 với JSON khác; không thêm challenge khi user đã xác thực nhưng thiếu quyền.
3. **httpBasic(basic -> basic.authenticationEntryPoint(...))** xử lý nhánh liên quan HTTP Basic, bao gồm thất bại của lần thử xác thực.
4. **exceptionHandling(errors -> errors.authenticationEntryPoint(...))** xử lý tình huống authorization đòi login khi request chưa có credential phù hợp.
5. **exceptionHandling(...accessDeniedHandler(...))** xử lý thiếu quyền (403).
6. **writeJsonError** dùng ServerHttpResponse reactive và Mono<Void>, không gọi block(), không dùng HttpServletResponse.
7. **ROLE_ADMIN** được kiểm tra trước rule rộng /api/**, tránh vô tình cho phép chỉ vì caller đã login.
8. Response đặt JSON và no-store, chỉ ghi byte nội dung đã được hệ thống định nghĩa sẵn. Khi schema động, dùng serializer an toàn như Jackson để escape dữ liệu, không tự nối chuỗi từ input.

Để code dễ học, hai tài khoản và mật khẩu được đặt trong source. Chúng **chỉ dành cho localhost/demo**; production cần identity store/IdP và quản lý secret, không commit mật khẩu thật.

### 7.5. ApiController.java

~~~java
package example.basic;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(user ->
                Map.of("username", user.getName()));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> report() {
        return Mono.just(Map.of("report", "ok"));
    }
}
~~~

Controller không tự kiểm tra password. Nếu quyền không đủ, request bị chặn bởi WebFilter trước khi vào handler. **Mono<Principal>** do WebFlux cung cấp phản ánh danh tính đã được xử lý trong security chain của request.

### 7.6. Khởi động và thử curl

Từ thư mục **basic-json-errors**, sử dụng JDK 17+ và Gradle 8.x tương thích với Spring Boot 3.3.5:

~~~bash
gradle bootRun
~~~

Ở terminal khác:

~~~bash
# 1. URL công khai: 200
curl -i http://localhost:8080/public/ping

# 2. Không có Basic credential: 401 + JSON + WWW-Authenticate
curl -i http://localhost:8080/api/me

# 3. Sai mật khẩu: 401 + cùng JSON và challenge
curl -i -u reader:wrong-pass http://localhost:8080/api/me

# 4. Reader đăng nhập đúng: 200
curl -i -u reader:reader-pass http://localhost:8080/api/me

# 5. Reader thiếu ROLE_ADMIN: 403 + JSON, không cần challenge
curl -i -u reader:reader-pass http://localhost:8080/api/admin/report

# 6. Admin đủ quyền: 200
curl -i -u admin:admin-pass http://localhost:8080/api/admin/report
~~~

**Các phần chính của kết quả dự kiến**, bỏ qua header do container/server tự thêm như Date hoặc Transfer-Encoding:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok"}
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="reactive-api"
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"username":"reader"}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"report":"ok"}
~~~

Đây là các **giá trị dự kiến từ cấu hình demo**, không phải bản capture một máy chủ đang chạy. Trên PowerShell có thể dùng **curl.exe**; lệnh trong bài là cho Bash/curl và dùng -i để hiển thị status/headers/body. Bộ mã HTTP còn tùy các thành phần khác mà ứng dụng triển khai thêm như reverse proxy, CORS, error handler hoặc SecurityWebFilterChain khác.

## 8. Kiểm thử tự động với WebTestClient

Cần test đủ **hai nhánh 401** và **nhánh 403**. Nếu chỉ test sai mật khẩu mà bỏ quên request không có Authorization header, ta có thể vô tình cấu hình JSON cho một nhánh và nhận response khác ở nhánh kia.

### 8.1. BasicErrorResponseTest.java

~~~java
package example.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BasicErrorResponseTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotRequireLogin() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void missingCredentialsProduceJson401AndBasicChallenge() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"reactive-api\"")
                .expectHeader().contentType(MediaType.APPLICATION_JSON)
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED")
                .jsonPath("$.message")
                .isEqualTo("Authentication required");
    }

    @Test
    void wrongPasswordUsesTheSameSafeJson401() {
        client.get().uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"reactive-api\"")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void validUserCanReadOwnIdentity() {
        client.get().uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void authenticatedUserWithoutRoleGetsJson403() {
        client.get().uri("/api/admin/report")
                .headers(headers ->
                        headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.WWW_AUTHENTICATE)
                .expectBody()
                .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
                .jsonPath("$.message").isEqualTo("Access denied");
    }

    @Test
    void adminCanReadReport() {
        client.get().uri("/api/admin/report")
                .headers(headers ->
                        headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.report").isEqualTo("ok");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kết quả dự kiến:** sáu test PASS; Gradle kết thúc với BUILD SUCCESSFUL nếu dự án được nhập đúng và dependencies tải thành công. Bài test tạo một WebFlux application context và gửi request tới cổng ngẫu nhiên, không cần bật riêng server demo trên 8080.

### 8.2. Một ma trận test nên có trong sản phẩm thật

| Request | Mong đợi |
| --- | --- |
| GET public không Authorization | 200, response nghiệp vụ |
| GET protected không Authorization | 401, JSON code, WWW-Authenticate Basic |
| GET protected Basic sai password | 401, cùng dạng JSON, không lộ user tồn tại hay không |
| GET protected Basic username không tồn tại | 401, nội dung công khai không khác biệt có ích cho user enumeration |
| GET protected Basic hợp lệ | 200, dữ liệu theo quyền |
| GET admin bằng ROLE_USER | 403, JSON ACCESS_DENIED, không challenge |
| GET admin bằng ROLE_ADMIN | 200 |
| Basic header malformed/không hợp lệ | Không truy cập được tài nguyên; hành vi lỗi được kiểm chứng theo converter của cấu hình |
| Identity store lỗi/timeout | Không trả 200, không giả mạo đăng nhập; ánh xạ lỗi hạ tầng thích hợp |
| Request có phương thức khác GET | Xét 405/CSRF/authorization phù hợp, không gom mọi lỗi thành 401 |

**Trường hợp malformed header** có thể khác chi tiết theo converter và filter, nên test request thực tế thay vì đoán rằng mọi chuỗi Authorization bất kỳ đều được xem là password sai. Nếu có nhiều SecurityWebFilterChain, xác minh chain nào đang match endpoint được test.

## 9. Những hướng tùy chỉnh khác và giới hạn

### 9.1. Dùng ServerAuthenticationFailureHandler riêng

Trong WebFlux, **ServerAuthenticationFailureHandler** có chữ ký khái niệm:

~~~java
Mono<Void> onAuthenticationFailure(
        WebFilterExchange filterExchange,
        AuthenticationException exception);
~~~

Nó xử lý lỗi của **lần thử xác thực ở AuthenticationWebFilter**. Nếu chỉ muốn đổi cách xử lý password sai cho một authentication mechanism, đây là điểm mở rộng phù hợp. Nhưng endpoint không gửi credential và bị authorization chặn có thể đi theo entry point của exception translation. Vì thế tùy chỉnh failure handler **không thay thế hoàn toàn** ServerAuthenticationEntryPoint.

**ServerAuthenticationEntryPointFailureHandler** là adapter để đưa ServerAuthenticationEntryPoint vào vị trí failure handler. Adapter có thể được cấu hình để **rethrow AuthenticationServiceException** thay vì coi lỗi hạ tầng là credential sai. Không tùy tiện thay cơ chế này bằng một handler luôn trả 401; nó che giấu sự cố identity service và làm metric sai.

### 9.2. @RestControllerAdvice có đủ không?

**Không đủ cho toàn bộ authentication/authorization.** Lỗi phát sinh ở các WebFilter thường xảy ra trước khi controller được gọi, nên @ExceptionHandler trong @RestControllerAdvice không chắc nhìn thấy lỗi mà entry point/failure handler/denied handler đã xử lý.

Dùng đúng trách nhiệm:

- **SecurityWebFilterChain**: authentication và URL authorization.
- **ServerAuthenticationEntryPoint**: phản hồi khi cần xác thực.
- **ServerAccessDeniedHandler**: phản hồi từ chối quyền.
- **@RestControllerAdvice**: lỗi nghiệp vụ, validation, domain exception trong controller/service.
- **Gateway/reverse proxy**: giới hạn tải, TLS, và các lỗi proxy riêng; không tự giả định mọi lỗi ở gateway đều do Spring Security tạo.

Một API có thể dùng cùng schema JSON ở các tầng này, nhưng mỗi tầng cần cấu hình/mapper tương ứng.

### 9.3. Có nên thay WWW-Authenticate bằng JSON-only?

Nếu vẫn dùng Basic, câu trả lời thường là **không**. Theo ngữ nghĩa HTTP, 401 phải có challenge; RFC Basic yêu cầu realm. Việc xóa header có thể hạn chế popup trên một số browser nhưng làm mất tương thích với các client Basic tiêu chuẩn. Nếu ứng dụng là browser SPA và không muốn trình duyệt quản lý credential Basic, nên cân nhắc cookie session có CSRF đúng, OAuth2/OIDC hoặc bearer token qua API phù hợp với kiến trúc.

### 9.4. Khi API có nhiều authentication mechanism

Một API có thể dùng bearer token cho /api/** và Basic cho /admin/**, hoặc có nhiều SecurityWebFilterChain. Lúc đó:

- Ràng buộc **securityMatcher** và thứ tự chain một cách rõ ràng.
- Mỗi chain cần entry point/challenge phù hợp với scheme mà nó hỗ trợ.
- Không trả Basic challenge ở một endpoint chỉ chấp nhận Bearer.
- Đừng áp handler trả JSON cho tất cả mọi chain nếu ứng dụng vẫn có trang đăng nhập browser cần redirect.
- Test độc lập URL công khai, URL Basic và URL Bearer.

Đừng cấu hình HTTP Basic bật mọi nơi theo quán tính nếu bảo mật yêu cầu scheme khác.

### 9.5. Cảnh báo về Response đã committed

Trong HTTP streaming, nếu controller đã bắt đầu gửi byte nội dung, status/header có thể đã được commit. Lỗi xảy ra **sau khi bắt đầu stream** không phải lúc nào còn đổi được thành JSON 401/403 đầy đủ. Vì thế phải kiểm tra authentication/authorization **trước khi phát dữ liệu nhạy cảm**, và xử lý quyền theo đối tượng khi có streaming phức tạp.

## 10. Bảo mật khi xử lý lỗi HTTP Basic

| Rủi ro | Hành động an toàn |
| --- | --- |
| Lộ thông tin tồn tại username | Trả thông điệp public giống nhau cho user không tồn tại/sai password |
| Lộ raw Authorization hoặc password | Không log header/credential; mask trong observability |
| Trả stack trace/cause trong JSON | Dùng code/message cố định, log nội bộ có lọc |
| Trả 200 cho authentication failure | Giữ status 401 và WWW-Authenticate |
| Trả 403 cho sai mật khẩu | Dùng 401 cho trường hợp không có bằng chứng xác thực hợp lệ |
| Trả 401 cho người thiếu ROLE_ADMIN | Dùng 403 để phản ánh đã login nhưng bị deny |
| Thất bại identity provider được coi là cho phép | Fail closed; trả lỗi kỹ thuật an toàn và cảnh báo |
| Xóa WWW-Authenticate chỉ để tắt browser popup | Cân nhắc chuyển authentication scheme nếu cần |
| Cache phản hồi có thông tin bảo mật | Cache-Control: no-store |
| Nối chuỗi JSON từ input không escape | Dùng serializer JSON chuẩn |
| Credential Basic đi qua HTTP không TLS | HTTPS/TLS, hạn chế đăng nhập bằng password qua kênh yếu |
| Password hash sai cấu hình | Dùng PasswordEncoder phù hợp, BCrypt/DelegatingPasswordEncoder theo chính sách |
| Basic login bị brute-force | Rate limit, theo dõi thất bại, lockout/challenge phù hợp |
| Role admin được client tự gửi qua header | Lấy GrantedAuthority từ nguồn server đáng tin |
| CSRF bị tắt máy móc | Đánh giá browser credential, cookie và các phương thức ghi thực tế |

**CSRF:** Basic là scheme mà browser có thể tự gửi lại credential theo ngữ cảnh đã xác thực; với request thay đổi trạng thái từ browser, không thể kết luận CSRF luôn vô hại. Demo chỉ có GET nên giữ default security config. Nếu triển khai POST/PUT/PATCH/DELETE, thiết kế CSRF dựa trên mô hình client thực tế thay vì sao chép cấu hình disable() không suy xét.

**CORS:** CORS là chính sách trình duyệt, không phải authentication. Preflight OPTIONS có thể không chứa credential. Nếu browser client gọi API cross-origin, phải cấu hình CORS và thứ tự WebFilter phù hợp, tránh chặn preflight do chưa có Basic credential; đồng thời giới hạn allowed origins/methods/headers theo yêu cầu.

**Logging:** có thể log result category, endpoint template, correlation/request ID và thời gian xử lý; tránh raw Authorization, password, Cookie và chi tiết exception chứa secret. Không nên trả cùng một ID audit cho mọi request; request ID nếu thêm vào JSON phải được tạo/vệ sinh ở phía server.

## 11. Gỡ lỗi khi vẫn nhận HTML hoặc body rỗng

Nếu code đã tùy chỉnh nhưng client còn nhận body rỗng hoặc HTML, kiểm tra:

1. **Đúng stack?** Sử dụng ServerHttpSecurity và SecurityWebFilterChain, không phải HttpSecurity/servlet.
2. **Có đúng chain đang chạy?** Nếu có nhiều chain, matcher/priority có thể khiến cấu hình khác được chọn.
3. **Đã cấu hình cả httpBasic và exceptionHandling?** Một nhánh credential sai và nhánh thiếu credential có thể đi theo handler khác nhau.
4. **Có formLogin?** Nếu form login vẫn bật trên đường đó, response có thể redirect tới trang login.
5. **Response đã committed?** Một WebFilter/controller trước đó có thể đã ghi byte hoặc status.
6. **Handler có trả Mono<Void> mà được subscribe qua pipeline?** Không gọi subscribe() thủ công hay block() để write response.
7. **Mã JSON và Content-Type có khớp?** Header application/json nhưng body HTML là không nhất quán.
8. **Có exception handler/proxy khác ghi đè?** Kiểm tra test với WebTestClient tại ứng dụng, sau đó so sánh khi qua gateway.
9. **Credential hỏng theo cách nào?** Header Basic malformed có thể đi vào converter path khác so với password sai.
10. **Có AuthenticationServiceException hoặc lỗi kết nối kho user?** Tránh đổi lỗi hạ tầng thành credential invalid.
11. **WWW-Authenticate có đúng scheme và realm?** Đối chiếu response header, không chỉ body JSON.
12. **Có bị chính sách CORS hoặc CSRF tác động?** Đặc biệt với browser và phương thức ghi.

Dùng curl -i quan sát đầy đủ headers và body. Dùng WebTestClient để cố định behavior, vì chỉ nhìn message trên frontend dễ nhầm lỗi của frontend với response của security chain.

## 12. Bài tập thực hành

1. Thay realm trong SecurityConfig thành một chuỗi tĩnh khác và xác minh WWW-Authenticate trên cả request thiếu credential và password sai.
2. Mở rộng response body 401 thêm trường requestId được tạo từ hệ thống; đảm bảo không echo Authorization header.
3. Thử thêm user có role REVIEWER và một endpoint /api/reviews/** chỉ cần REVIEWER. Phân biệt phản hồi 401/403.
4. Viết WebTestClient test cho username không tồn tại và so sánh mã lỗi public với password sai.
5. Cố tình bỏ phần .httpBasic(basic -> basic.authenticationEntryPoint(...)), xem nhánh nào không còn nhận JSON như mong đợi rồi khôi phục.
6. Cố tình bỏ phần exceptionHandling().authenticationEntryPoint(...), quan sát request không credential và khôi phục.
7. Thay body bằng schema Problem Details với application/problem+json và cập nhật test tương ứng.
8. Tạo mô phỏng ReactiveAuthenticationManager báo lỗi hạ tầng; thiết kế kiểm tra rằng response không thể là 200 hoặc cấp quyền.
9. Giải thích vì sao trả 200 cùng {"error":"invalid"} làm client, tracing và monitoring khó hoạt động.
10. Giải thích vì sao WWW-Authenticate cần giữ cho Basic dù một số browser có thể hiển thị dialog.

**Gợi ý đáp án:**

- (1) Basic realm là tham số challenge, không phải username hoặc password.
- (2) requestId thuộc dữ liệu do server kiểm soát và cần encode an toàn.
- (3) 401 khi chưa có credential hợp lệ, 403 khi đã xác thực nhưng thiếu role.
- (4) dùng thông điệp chung để hạn chế user enumeration.
- (5) nhánh failure trong HTTP Basic có thể quay về entry point mặc định.
- (6) nhánh authorization phát hiện anonymous có thể quay về entry point khác.
- (7) Content-Type và nội dung JSON phải cùng tuân theo RFC của schema.
- (8) lỗi kỹ thuật phải fail closed, ghi nhận/ánh xạ 5xx phù hợp.
- (9) status 200 che giấu failure khỏi cơ chế HTTP.
- (10) Basic dùng cơ chế challenge-response theo chuẩn.

## 13. Tài liệu tham khảo

- Spring Security Javadoc — ServerHttpSecurity.HttpBasicSpec: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security Javadoc — ServerHttpSecurity.ExceptionHandlingSpec: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security Javadoc — ServerAuthenticationEntryPointFailureHandler: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- RFC 7617 — The Basic HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617.html
- RFC 9110 — HTTP Semantics (401/403 và WWW-Authenticate): https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html

**Kết luận:** Để tùy chỉnh lỗi HTTP Basic cho REST API WebFlux, hãy dùng **ServerAuthenticationEntryPoint** cho 401 và **ServerAccessDeniedHandler** cho 403, cấu hình nhất quán ở **httpBasic** lẫn **exceptionHandling**, giữ **WWW-Authenticate: Basic realm="..."** trên 401 và trả JSON có schema ổn định, không lộ thông tin bí mật. Cần kiểm thử riêng thiếu credential, sai credential, thiếu quyền và lỗi kỹ thuật; thay đổi cách trình bày không được thay đổi nguyên tắc xác thực và phân quyền.