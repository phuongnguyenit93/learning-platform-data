# ServerHttpSecurity, SecurityWebFilterChain và authorizeExchange

> **Bối cảnh:** Spring Security – authorization → **HTTP trên WebFlux**. Bài hướng dẫn cấu hình quyền truy cập HTTP trong ứng dụng Spring WebFlux bằng `ServerHttpSecurity`, `SecurityWebFilterChain` và DSL `authorizeExchange`; phân biệt chọn **filter chain** với chọn **rule** bên trong chain, giải thích cơ chế reactive, bảo vệ endpoint mặc định, nhiều chain, authentication, CSRF, CORS, tùy biến `ReactiveAuthorizationManager` và kiểm thử với `WebTestClient`. Ví dụ chính dùng Java 17+, Spring Boot 3.x và Spring Security 6.x. Các đoạn mở rộng OAuth2/JWT được ghi riêng để không nhầm với ứng dụng HTTP Basic chạy độc lập.

## 1. Ba thành phần giải quyết ba việc khác nhau

Hãy xem một ứng dụng WebFlux có các URL:

~~~text
GET  /health                   public
GET  /api/public/ping          public
GET  /api/reports/summary      yêu cầu REPORT_READ
POST /api/reports/publish      yêu cầu ROLE_ADMIN + CSRF token
GET  /api/admin/dashboard      yêu cầu ROLE_ADMIN
GET  /ui/profile               yêu cầu authenticated
GET  /internal/status          deny mặc định
~~~

Ta cần trả lời ba câu hỏi:

1. **Request này thuộc cấu hình bảo mật nào?** Chọn `SecurityWebFilterChain` bằng `securityMatcher(...)` và thứ tự `@Order`.
2. **Trong chain được chọn, URL/method khớp rule nào?** `authorizeExchange` với `pathMatchers(...)`, `matchers(...)` hoặc `anyExchange()`.
3. **Rule đó yêu cầu gì?** `permitAll`, `authenticated`, `hasAuthority`, `hasRole`, `denyAll` hoặc `access(ReactiveAuthorizationManager)`.

| API | Package / bản chất | Chức năng |
| --- | --- | --- |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server`; builder | Cấu hình WebFlux web filters, CSRF, HTTP Basic, form login, OAuth2, authorization |
| `SecurityWebFilterChain` | `org.springframework.security.web.server`; interface | Đối tượng filter chain được `http.build()` tạo, kèm matcher và danh sách reactive `WebFilter` |
| `authorizeExchange` | DSL của `ServerHttpSecurity` | Khai báo quyết định quyền đối với `ServerWebExchange` trong chain đó |
| `ServerWebExchangeMatcher` | Matcher reactive | Xác định một exchange có thuộc chain/rule hay không |
| `ReactiveAuthorizationManager<AuthorizationContext>` | Reactive authorization contract | Cho phép kiểm tra quyền bất đồng bộ, trả `Mono<AuthorizationDecision>` trong Spring Security 6.x |
| `WebFilterChainProxy` | WebFlux security infrastructure | Chọn/áp dụng `SecurityWebFilterChain` thích hợp |
| `AuthenticationWebFilter` và `AuthorizationWebFilter` | Reactive WebFilters | Xác thực và thực thi authorization ở vị trí thích hợp |

**Không trộn với Servlet:** `HttpSecurity`, `SecurityFilterChain`, `authorizeHttpRequests` và `HttpServletRequest` thuộc servlet stack. Trên WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `authorizeExchange` và `ServerWebExchange`. Các class tuy có tên gần nhau nhưng không hoán đổi trực tiếp được.

## 2. Luồng bảo mật WebFlux hoạt động thế nào?

~~~text
HTTP request
     |
     v
Spring WebFlux WebFilter chain
     |
     v
Spring Security WebFilterChainProxy
     |
     +-- chọn chain theo @Order + securityMatcher
     |       |-- /api/** -> API SecurityWebFilterChain
     |       +-- còn lại -> fallback SecurityWebFilterChain
     |
     v
Các WebFilters của chain đã chọn
     |
     +-- SecurityContext / Authentication
     +-- CSRF, headers và các cơ chế bảo vệ khác
     +-- AuthorizationWebFilter theo authorizeExchange
     |
     +-- DENY -> AuthenticationEntryPoint/AccessDeniedHandler
     |
     +-- ALLOW -> DispatcherHandler -> Controller/RouterFunction
                                         |
                                         v
                                    Mono / Flux
~~~

Bảo mật WebFlux sử dụng `WebFilter` và reactive stream, không chạy qua servlet `FilterChainProxy`. Authentication/authorization và những thông tin bảo mật liên quan thường được truyền bằng **Reactor Context**. Không đọc `SecurityContextHolder` dạng ThreadLocal như một cơ chế mặc định trong service WebFlux rồi mặc định cùng principal xuất hiện sau các lần chuyển scheduler.

### 2.1. Builder không phải kết quả cuối

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

`ServerHttpSecurity` là **builder cấu hình**; `build()` tạo `SecurityWebFilterChain` để framework dùng khi có request. Thay đổi builder sau build không phải cách cập nhật chính sách lúc chạy; nếu cần policy động, `access(...)` nên gọi một policy source/PDP có quy tắc nhất quán.

### 2.2. `@EnableWebFluxSecurity` làm gì?

~~~java
@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {
    // Các @Bean SecurityWebFilterChain
}
~~~

Annotation nhập các thành phần Spring Security cần cho WebFlux. Một cấu hình tối thiểu có thể để Spring Security cung cấp cơ chế xác thực/headers/CSRF mặc định, nhưng trong ứng dụng thực tế nên khai báo chain và rule rõ ràng để kiểm soát hành vi. Với Spring Boot starter, các auto-configuration có thể cung cấp mặc định nếu bạn chưa tự định nghĩa beans; **đừng dựa vào suy đoán mặc định** khi endpoint có yêu cầu cụ thể.

Không dùng `@EnableWebSecurity` cho đoạn cấu hình WebFlux này; annotation đó thuộc servlet stack. Nếu cần Method Security cho `Mono`/`Flux`, xem `@EnableReactiveMethodSecurity` ở mục sau.

## 3. `authorizeExchange`: những rule thường dùng

Một chain đơn giản:

~~~java
@Bean
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/health", "/public/**").permitAll()
                    .pathMatchers("/admin/**").hasRole("ADMIN")
                    .pathMatchers("/reports/**").hasAuthority("REPORT_READ")
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

| Rule | Ý nghĩa | Ghi nhớ |
| --- | --- | --- |
| `permitAll()` | Không yêu cầu authorization | Chỉ khai cho endpoint thật sự public |
| `authenticated()` | Yêu cầu Authentication hợp lệ | Không tự biết user có quyền với object nào |
| `hasRole("ADMIN")` | Yêu cầu authority `ROLE_ADMIN` mặc định | Không thêm `ROLE_` vào argument của `hasRole` |
| `hasAuthority("REPORT_READ")` | So đúng chuỗi authority | Không tự thêm prefix |
| `hasAnyRole("USER","ADMIN")` | Một trong nhiều roles | Vẫn là role chung, không phải object-level scope |
| `denyAll()` | Từ chối mọi caller | Hữu ích làm catch-all nhạy cảm |
| `access(manager)` | Áp dụng custom reactive policy | Phải xử lý missing/timeout và fail closed |

### 3.1. Rule xét theo thứ tự khai báo

Ví dụ **sai**:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

`/api/admin/dashboard` khớp `/api/**` trước. Nếu chỉ yêu cầu authenticated, admin rule sau không được chọn. **Quy tắc cụ thể phải đứng trước quy tắc rộng.**

Đúng:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

Cũng cần chú ý method-specific rules: nếu `GET /api/reports/**` chỉ cho người đọc, đừng đặt một rule `/api/reports/**` permitAll ở phía trên rồi mới bảo vệ POST. Test cả GET/POST/PUT/DELETE và các path biến thể.

### 3.2. `pathMatchers` có thể xét HTTP method

~~~java
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("REPORT_READ")
.pathMatchers(HttpMethod.POST, "/api/reports/**")
    .hasRole("ADMIN")
.anyExchange().denyAll()
~~~

Sự phân chia này cho phép cùng một đường URL có các yêu cầu khác nhau tùy HTTP method. `HEAD` và `OPTIONS` cũng cần được cân nhắc khi public API có hỗ trợ; đừng mặc nhiên cho mọi method vì chỉ nghĩ đến GET.

### 3.3. Không biết endpoint thì deny

~~~java
.anyExchange().denyAll()
~~~

Rule cuối giúp một controller được bổ sung sau này **không tự mở quyền** vì rơi vào catch-all `authenticated` quá rộng. Nếu ứng dụng cố ý cần mọi endpoint khác chỉ xác thực, `anyExchange().authenticated()` cũng là lựa chọn hợp lệ nhưng khác policy. Trong môi trường học tập có admin/data sensitive paths, chọn deny-by-default giúp reviewer thấy rõ endpoint mới cần được khai báo.

### 3.4. Trạng thái HTTP và cơ chế khác nhau

| Tình huống | Kỳ vọng thường gặp |
| --- | --- |
| Chưa đăng nhập, endpoint đòi authenticated/authority, HTTP Basic | 401 và challenge phù hợp |
| Đã đăng nhập, thiếu `ROLE_ADMIN` hoặc authority | 403 |
| POST có quyền nhưng không có CSRF token trong cấu hình bật CSRF | 403 |
| Endpoint public | 200 nếu controller xử lý thành công; có thể 404 nếu route không tồn tại |
| Catch-all `denyAll` cho user đã đăng nhập | 403 |
| Lỗi dữ liệu/service ở controller | Mã lỗi theo ứng dụng, không tự là lỗi authentication |

401/403 chịu ảnh hưởng `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, mechanism và error handling đang cấu hình. Không viết test giả định tất cả lỗi đều trả cùng mã.

## 4. Hai cấp chọn rule: `securityMatcher` và `pathMatchers`

Đây là chỗ dễ nhầm nhất.

**Cấp 1 – chọn SecurityWebFilterChain:**

~~~java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"));
~~~

Matcher quyết định **chain này có áp dụng cho request hay không**.

**Cấp 2 – authorizeExchange bên trong chain đã chọn:**

~~~java
http.authorizeExchange(ex -> ex
        .pathMatchers("/api/public/**").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll());
~~~

Rules ở cấp 2 **chỉ được xét khi request đã vào chain đó**.

~~~text
Request GET /api/admin/dashboard
       |
       v
Chain #1 matcher /api/** -> MATCH
       |
       v
Rule /api/public/**     -> no
Rule /api/admin/**      -> yes, require ROLE_ADMIN
Rule anyExchange        -> not reached
       |
       v
Authentication + authorization decision
~~~

Nếu chain #1 không match, Spring Security thử chain kế tiếp theo thứ tự. Nếu **không chain nào match**, request đó có thể không được Spring Security bảo vệ. Vì vậy hãy có catch-all fallback chain, và test các URL ngoài `/api/**`. Đừng tưởng `anyExchange().denyAll()` trong một chain chỉ match `/api/**` sẽ tự bảo vệ cả `/internal/**`.

### 4.1. Thứ tự `@Order`

~~~java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    // chỉ /api/**
}

@Bean
@Order(2)
SecurityWebFilterChain fallback(ServerHttpSecurity http) {
    // áp dụng phần còn lại
}
~~~

Spring Security chọn chain đầu tiên match; sau khi đã chọn, không cộng/ghép permissions từ các chains đứng sau. Một fallback chain không có `securityMatcher` thường match mọi exchange. Đặt fallback ở cuối để tránh nuốt mọi request trước khi API chain được xét.

### 4.2. Chính sách giữa các chain có thể khác

| Phạm vi | Authentication | CSRF | Authorization |
| --- | --- | --- | --- |
| `/api/**` phục vụ browser + HTTP Basic demo | HTTP Basic | Giữ bật để minh họa POST an toàn | GET public, REPORT_READ, ADMIN, deny unknown |
| `/ui/**` | HTTP Basic trong demo, thực tế có thể form login/session | Giữ bật khi browser dùng cookies/session | Authenticated |
| `/internal/**` | Không tạo đường truy cập | N/A | `denyAll` trong fallback |
| `/health` | Public | Không có unsafe method | `permitAll` |
| API bearer token thực sự stateless | OAuth2 resource server | Có thể cân nhắc tắt khi **chỉ** dùng Authorization header không tự gửi bằng browser | Scope/roles + object policy |

HTTP Basic **không tự đồng nghĩa** API stateless miễn CSRF: trình duyệt có thể tự gắn Basic credentials, nên cần cân nhắc CSRF với endpoint state-changing. Bài mẫu **không tắt CSRF** và sẽ kiểm thử trường hợp thiếu token.

## 5. Ví dụ chạy được: Spring Boot 3.x + WebFlux + HTTP Basic

Bài mẫu có đầy đủ các files và tests. Chọn:
- Java 17;
- Gradle;
- Spring Boot `3.3.5` (một bản Boot 3.x cụ thể cho ví dụ, có dependency management của Spring Security 6.x);
- Spring WebFlux, không dùng `spring-boot-starter-web`;
- `MapReactiveUserDetailsService` với mật khẩu bcrypt để demo;
- Hai `SecurityWebFilterChain` và các reactive controllers trả `Mono<String>`.

**Không dùng danh sách user này cho production**; credentials chỉ phục vụ bài học và integration tests. Production cần nguồn identity, mật khẩu, MFA, rate limit, token/session management phù hợp.

### 5.1. `settings.gradle`

~~~groovy
rootProject.name = 'webflux-security-demo'
~~~

### 5.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.webflux'
version = '1.0.0'

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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu project đã dùng Spring Boot 3.3.x/3.4.x/3.5.x khác, nên để Boot BOM quản lý versions tương thích; không tự chèn Spring Security 7.x lên Boot 3.x. Với ứng dụng production đang dùng phiên bản khác, kiểm tra DSL/API cụ thể trước khi copy.

### 5.3. `src/main/java/demo/webflux/WebFluxSecurityApplication.java`

~~~java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxSecurityApplication.class, args);
    }
}
~~~

### 5.4. `src/main/java/demo/webflux/SecurityConfiguration.java`

~~~java
package demo.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/api/public/**")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/reports/**")
                        .hasAuthority("REPORT_READ")
                        .pathMatchers(
                                HttpMethod.POST, "/api/reports/**")
                        .hasRole("ADMIN")
                        .pathMatchers("/api/admin/**")
                        .hasRole("ADMIN")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // CSRF giữ giá trị mặc định: bật.
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/health")
                        .permitAll()
                        .pathMatchers("/ui/**")
                        .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .authorities("REPORT_READ")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .authorities("REPORT_READ", "ROLE_ADMIN")
                .build();

        return new MapReactiveUserDetailsService(viewer, admin);
    }
}
~~~

**Đọc từng phần:**

1. `@EnableWebFluxSecurity` khởi tạo WebFlux security infrastructure.
2. `apiSecurity` ở `@Order(1)` chỉ nhận path khớp `/api/**`.
3. `authorizeExchange` của API phân biệt GET public, GET reports, POST reports và admin routes; cuối cùng deny mọi URL/method khác của API.
4. `httpBasic(withDefaults())` bật HTTP Basic; `formLogin(form -> form.disable())` ngăn trả HTML login page khi API client chưa xác thực.
5. Không khai báo `csrf(...disable())` nên WebFlux CSRF mặc định **vẫn bật** cho unsafe methods.
6. `fallbackSecurity` ở `@Order(2)` không hạn chế matcher và bao phủ request không vào API chain.
7. `/health` public, `/ui/**` cần authenticated, mọi thứ khác trong fallback denied.
8. `MapReactiveUserDetailsService` là user store trong RAM (reactive contract). Mật khẩu dùng encoder có prefix phù hợp; đừng dùng `{noop}` trong sản phẩm thật.
9. `hasRole("ADMIN")` tìm `ROLE_ADMIN`, nên admin có đúng authority đó; viewer chỉ có `REPORT_READ`.

**Điểm về `/api` (không có slash kết thúc):** `/api/**` không nên được dùng như một giả định bảo vệ mọi biến thể `/api`, `/api/`, case khác nhau hoặc URL encoded. Cần test những path mà gateway/framework thực sự định tuyến. Fallback với `denyAll` giúp ngăn một URL lạ vô tình lọt khỏi bảo vệ.

### 5.5. `src/main/java/demo/webflux/ExampleController.java`

~~~java
package demo.webflux;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ExampleController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/public/ping")
    public Mono<String> publicPing() {
        return Mono.just("PONG");
    }

    @GetMapping("/api/reports/summary")
    public Mono<String> reportSummary() {
        return Mono.just("summary");
    }

    @PostMapping("/api/reports/publish")
    public Mono<String> publishReport() {
        // Demo chỉ trả chuỗi; production phải authorize cả
        // tài nguyên đích và thao tác nghiệp vụ.
        return Mono.just("published");
    }

    @GetMapping("/api/admin/dashboard")
    public Mono<String> adminDashboard() {
        return Mono.just("dashboard");
    }

    @GetMapping("/ui/profile")
    public Mono<String> profile() {
        return Mono.just("profile");
    }

    @GetMapping("/api/unknown")
    public Mono<String> unknownApi() {
        return Mono.just("should-not-be-accessible");
    }

    @GetMapping("/internal/status")
    public Mono<String> internalStatus() {
        return Mono.just("internal-secret");
    }
}
~~~

Việc **tạo route không làm route được cấp quyền**. Hai route cuối cố ý tồn tại để test deny-by-default ngay cả khi request thực sự có handler.

Controller trả `Mono` đơn giản, tránh side effect để bài tập tập trung vào HTTP authorization. Trong hệ thống thực, service nghiệp vụ vẫn phải kiểm tra quyền object-level với tenant, owner, status và permission; quyền `ROLE_ADMIN` ở HTTP layer **không mặc nhiên** cho quyền với mọi tài liệu.

## 6. Integration tests: `WebTestClient` với Spring Security thật

Spring Security cung cấp hỗ trợ test cho reactive HTTP. Một lựa chọn mạnh là:

~~~java
WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
~~~

Cách này tạo client đi qua WebFlux application context và security filters, không cần mở TCP port. `WebTestClient.bindToController(new Controller())` **một mình** không tự chứng minh security chain của toàn application được gắn đúng.

### 6.1. `src/test/java/demo/webflux/WebFluxSecurityTests.java`

~~~java
package demo.webflux;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest(
        classes = WebFluxSecurityApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class WebFluxSecurityTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void healthIsPublicThroughFallbackChain() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void publicApiIsPublicWithoutCredentials() {
        client.get().uri("/api/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void protectedReportWithoutAuthenticationReturns401() {
        client.get().uri("/api/reports/summary")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void viewerMayReadReports() {
        client.get().uri("/api/reports/summary")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("summary");
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() {
        client.get().uri("/api/reports/summary")
                .headers(h -> h.setBasicAuth(
                        "viewer", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void viewerCannotAccessAdminDashboard() {
        client.get().uri("/api/admin/dashboard")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminMayAccessAdminDashboard() {
        client.get().uri("/api/admin/dashboard")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("dashboard");
    }

    @Test
    void viewerCannotPublishEvenWithCsrfToken() {
        client.mutateWith(csrf())
                .post().uri("/api/reports/publish")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminWithoutCsrfCannotPublish() {
        client.post().uri("/api/reports/publish")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminWithCsrfMayPublish() {
        client.mutateWith(csrf())
                .post().uri("/api/reports/publish")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("published");
    }

    @Test
    void viewerCanAccessAuthenticatedUi() {
        client.get().uri("/ui/profile")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("profile");
    }

    @Test
    void uiRequiresAuthentication() {
        client.get().uri("/ui/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserCannotAccessUnknownApi() {
        client.get().uri("/api/unknown")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void authenticatedAdminCannotBypassFallbackDenyAll() {
        client.get().uri("/internal/status")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

**Hai static imports bị ngắt dòng ở vị trí Java cho phép:** đây là lưu ý quan trọng khi copy source. Trong Java, `import static org.springframework.security.test.web.reactive.server` xuống dòng rồi `.SecurityMockServerConfigurers.springSecurity;` có dấu chấm đầu đoạn; để tránh nhầm lẫn và tiện copy, hãy viết nguyên một dòng như sau khi đưa vào IDE:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
~~~

Đây là **hai imports thực tế cần sử dụng** trong file kiểm thử trên. Mục đích của `springSecurity()` là gắn Spring Security test support vào client; `csrf()` tạo CSRF test token phù hợp để phân biệt denial do CSRF và denial do role.

### 6.2. Ma trận test

| Request | Caller | CSRF | Kỳ vọng |
| --- | --- | --- | --- |
| GET /health | Anonymous | N/A | 200 |
| GET /api/public/ping | Anonymous | N/A | 200 |
| GET /api/reports/summary | Anonymous | N/A | 401 |
| GET /api/reports/summary | viewer (REPORT_READ) | N/A | 200 |
| GET /api/reports/summary | viewer mật khẩu sai | N/A | 401 |
| GET /api/admin/dashboard | viewer | N/A | 403 |
| GET /api/admin/dashboard | admin | N/A | 200 |
| POST /api/reports/publish | viewer | Hợp lệ | 403 vì không có ROLE_ADMIN |
| POST /api/reports/publish | admin | Thiếu | 403 vì CSRF |
| POST /api/reports/publish | admin | Hợp lệ | 200 |
| GET /ui/profile | viewer | N/A | 200 |
| GET /ui/profile | Anonymous | N/A | 401 |
| GET /api/unknown | admin | N/A | 403 |
| GET /internal/status | admin | N/A | 403 |

Việc kiểm cả **người thiếu quyền** và **người đủ quyền nhưng thiếu CSRF** giúp tránh kết luận sai: một lỗi 403 không nhất thiết phát sinh từ `authorizeExchange`. Debug security logs và tests cần phân biệt authentication, authorization, CSRF và controller routing.

### 6.3. Chạy thử

Với Gradle wrapper của project:

~~~bash
./gradlew test --tests demo.webflux.WebFluxSecurityTests
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.webflux.WebFluxSecurityTests
gradlew.bat bootRun
~~~

Gọi thử khi server đang chạy:

~~~bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/public/ping
curl -i -u viewer:viewer-pass http://localhost:8080/api/reports/summary
curl -i -u viewer:viewer-pass http://localhost:8080/api/admin/dashboard
curl -i -u admin:admin-pass http://localhost:8080/api/admin/dashboard
~~~

Những lệnh GET trên dự kiến trả body lần lượt `OK`, `PONG`, `summary`, 403, `dashboard`. Với `curl`, thông tin credentials sau `-u` chỉ dành cho local demo; không đặt mật khẩu thật vào shell history hoặc public logs. POST dùng CSRF cần token/session tương ứng; test `mutateWith(csrf())` đã minh họa chính xác điều kiện ấy.

Bài không chứa `System.out.println` nên stdout của JVM/server phụ thuộc Gradle, logging và phiên bản. Kết quả cố định chỉ là **HTTP status/body mà tests xác nhận**, không phải các dòng log khởi động.

## 7. Giải thích sâu hơn về hai tầng lựa chọn

### 7.1. Vì sao fallback `denyAll` quan trọng?

Nếu chỉ khai báo:

~~~java
@Bean
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .build();
}
~~~

thì `/health`, `/internal/status`, `/ui/profile` không vào chain `/api/**`. Nếu không còn chain khác match, chúng **có thể nằm ngoài bảo vệ của Spring Security**. Vì vậy không thể coi `anyExchange().authenticated()` bên trong chain này là “mọi request ứng dụng phải xác thực”. Nó có nghĩa **mọi exchange đã được chọn vào chain** phải xác thực.

### 7.2. Nếu fallback ở `@Order(1)` thì sao?

~~~text
Chain fallback: match all, @Order(1)
Chain API:      match /api/**, @Order(2)
GET /api/admin/dashboard
   |
   +-- fallback match-all trước -> chọn fallback
   +-- API chain không còn được xét
~~~

Ngay cả khi chain API có rule `hasRole("ADMIN")` chặt chẽ, nó sẽ không thực thi cho request này. Cần test các path ở ranh giới và xác nhận thứ tự chains.

### 7.3. Vì sao `anyExchange` phải ở cuối?

Trong `authorizeExchange`, thứ tự declaration quyết định rule được thử đầu tiên. Nếu đặt `anyExchange().authenticated()` trước `pathMatchers("/api/admin/**").hasRole("ADMIN")`, mọi request đã thỏa rule rộng, làm rule admin bị che. Một số DSL có thể báo lỗi với các rule được thêm sau terminal matcher; dù cách xử lý thay đổi theo version, **thiết kế vẫn phải đặt catch-all cuối**.

### 7.4. Đa ứng dụng và gateway routing

Nếu gateway rewrite URL trước khi WebFlux nhận, pattern cần khớp **path thực tế trong Spring Security server**, không chỉ URL công khai bên ngoài. Security path matching thường không hiểu rằng `/gateway/api/admin` đã được rewrite thành `/api/admin` trừ khi Spring exchange phản ánh đúng path. Kiểm thử với gateway integration/case và encoded path, không dùng prefix string `startsWith("/api")` tùy tiện thay cho matcher framework.

## 8. `hasRole`, `hasAuthority` và scope nghiệp vụ

Trong ví dụ:

~~~text
viewer authorities = [REPORT_READ]
admin  authorities = [REPORT_READ, ROLE_ADMIN]
~~~

- `hasAuthority("REPORT_READ")` yêu cầu đúng chuỗi `REPORT_READ`.
- `hasRole("ADMIN")` thường tự xét `ROLE_ADMIN`.
- `hasRole("ROLE_ADMIN")` có thể bị coi là đưa prefix trùng/sai; dùng `hasAuthority("ROLE_ADMIN")` nếu muốn khớp chuỗi đầy đủ.
- `authenticated()` chỉ đòi người gọi được xác thực, không xét object owner/tenant.

Nếu report thuộc tenant `acme` còn người gọi thuộc `beta`, `REPORT_READ` chung có thể **chưa đủ**. Cần thêm policy theo resource và tenant **ở service** hoặc custom manager. Không xem HTTP rule là thay thế cho object-level authorization.

Ví dụ dịch vụ truy cập tài liệu cần kiểm:

~~~text
authenticated user
AND has REPORT_READ
AND resource.tenantId == actor.activeTenant
AND user has allowed permission for resource
AND document not archived/locked as business rule
~~~

Tài nguyên có thể được truy cập từ background jobs, message consumers hoặc GraphQL, do đó chốt ở service giúp không phụ thuộc hoàn toàn vào URI.

## 9. Custom `ReactiveAuthorizationManager` với `access(...)`

Khi rule đơn giản không đủ, `authorizeExchange` hỗ trợ custom reactive authorization manager. Trong Spring Security 6.x, contract nhận `Mono<Authentication>` và `AuthorizationContext`, trả `Mono<AuthorizationDecision>` (có thể hoàn thành không decision tùy framework semantics, nên hãy thiết kế trả DENY rõ ràng khi dữ liệu thiếu).

### 9.1. Ví dụ có thể đưa vào cấu hình như một `@Bean`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

@Bean
ReactiveAuthorizationManager<AuthorizationContext> exportPolicy() {
    return (authentication, context) -> authentication
            .map(auth -> new AuthorizationDecision(
                    auth.isAuthenticated()
                    && auth.getAuthorities().stream()
                        .anyMatch(a ->
                            "EXPORT_REPORTS".equals(a.getAuthority()))))
            .defaultIfEmpty(new AuthorizationDecision(false));
}
~~~

Cấu hình sử dụng:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/exports/**")
        .access(exportPolicy)
        .anyExchange().denyAll())
~~~

**Đây là các đoạn tích hợp minh họa, không phải file Java độc lập.** Bean `exportPolicy` có thể inject qua parameter của method cấu hình chain hoặc field constructor. Nếu đặt vào cùng class SecurityConfiguration của ví dụ, cần thêm route `/api/exports/**`, bean/parameter thích hợp và đặt rule trước catch-all. Method `exportPolicy()` trên class Configuration có thể được quản lý làm bean, nhưng đừng tùy tiện gọi một helper bên ngoài Spring context rồi nghĩ các interceptor vẫn áp dụng.

### 9.2. Quyết định async lấy dữ liệu từ WebFlux và repository

Một policy thực tế có thể cần R2DBC, Redis hoặc HTTP PDP:

~~~java
// MINH HỌA logic, không phải class độc lập.
return authentication
        .flatMap(auth ->
                reactivePolicyRepository.canExport(
                        auth.getName(),
                        tenantFromTrustedContext,
                        resourceId))
        .map(AuthorizationDecision::new)
        .defaultIfEmpty(new AuthorizationDecision(false))
        .onErrorReturn(new AuthorizationDecision(false));
~~~

Các biến `reactivePolicyRepository`, `tenantFromTrustedContext` và `resourceId` cần được định nghĩa từ nguồn đáng tin. `onErrorReturn(deny)` là một lựa chọn fail-closed; trong sản phẩm thật có thể phân biệt “không quyền” (403) với “policy service không khả dụng” (503), nhưng **không** biến timeout thành allow.

**Không gọi `.block()` ngay trong event-loop** để lấy kết quả policy. Nếu policy cần JDBC blocking, nên chuyển tác vụ blocking sang scheduler thích hợp một cách có kiểm soát hoặc ưu tiên driver/reactive repository thực sự; đừng làm thread Netty bị block. Với remote PDP, đặt timeout, circuit breaker, caching có version, audit và retries không gây bão.

### 9.3. Vì sao không tự suy ra tenant từ path?

`AuthorizationContext` cung cấp `ServerWebExchange` và thông tin request; nhưng một `tenantId` xuất hiện trong URL **không chứng minh** user được phép truy cập tenant đó. Phải kiểm tra membership từ trusted principal và xác định resource thuộc tenant nào từ database. Đặc biệt đừng dùng request header tùy ý làm bằng chứng `ROLE_ADMIN` hoặc tenant membership.

## 10. HTTP Basic, form login, JWT resource server: chọn cơ chế phù hợp

### HTTP Basic ở bài mẫu

`httpBasic(withDefaults())` giúp quan sát 401/403 dễ dàng. Tuy nhiên Basic mang credentials trên mỗi request, phải dùng HTTPS và rate-limit phù hợp; secret không được đặt sẵn trong source production. Browser có thể tự gửi Basic credentials, nên không tắt CSRF một cách máy móc khi có state-changing endpoints.

### Form login/session

`formLogin(withDefaults())` có thể phù hợp ứng dụng browser. Khi login bằng form/session cookie, CSRF là thành phần quan trọng. Với SPA và cookie, cần hiểu cookie SameSite, CSRF token repository, CORS và session fixation; không đánh đồng CORS với CSRF.

### OAuth2 resource server JWT cho API bearer

Trong production, API stateless sử dụng Bearer tokens thường phù hợp với:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

Và thêm một chain API đã được cấu hình:

~~~java
// MINH HỌA BỔ SUNG: thay HTTP Basic của API chain
// bằng OAuth2 resource server với JWT verifier phù hợp.
http
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
            org.springframework.security.config.Customizer.withDefaults()));
~~~

Issuer URL được xác minh theo identity provider của dự án, ví dụ trong `application.properties`:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.invalid/issuer
~~~

`example.invalid` là địa chỉ minh họa, không phải endpoint JWT thật; phải dùng issuer thực trong môi trường triển khai. Khi dùng bearer token qua Authorization header và không dùng cookie/browser credential tự động, có thể xem xét vô hiệu CSRF **cho chain stateless cụ thể**; nếu cùng chain còn nhận cookie/session, phải đánh giá lại. Không tắt CSRF chỉ vì request body là JSON.

Không trộn cấu hình JWT chưa có issuer/JWK verifier với ví dụ HTTP Basic rồi tuyên bố project test độc lập vẫn chạy. Hai mô hình là hai phương án triển khai khác nhau.

## 11. CSRF trên WebFlux: authorization có thể đúng mà POST vẫn bị chặn

Mặc định Spring Security WebFlux bật CSRF. CSRF có mục tiêu ngăn website độc hại dụ browser đã có credentials tự động thực hiện một thay đổi trạng thái.

~~~text
POST /api/reports/publish
Authorization: Basic (admin)
CSRF header/token: missing
  |
  +-- Authentication valid
  +-- ROLE_ADMIN true
  +-- CsrfWebFilter denies
  |
  v
403 Forbidden
~~~

Thêm token phù hợp:

~~~java
client.mutateWith(csrf())
        .post().uri("/api/reports/publish")
        .headers(h -> h.setBasicAuth("admin", "admin-pass"))
        .exchange()
        .expectStatus().isOk();
~~~

Ở ứng dụng browser/session thật, token phải được cấp và gửi theo repository/handler cấu hình; `mutateWith(csrf())` là **test helper**, không phải cách client production gửi token.

### Những câu hỏi trước khi disable CSRF

1. Authentication có đến từ cookie hoặc cơ chế browser tự gửi không?
2. Có unsafe methods POST/PUT/PATCH/DELETE xử lý từ browser không?
3. API có nhận Basic Authorization mà browser có thể tự gửi không?
4. Client chỉ dùng Bearer Authorization header tự gắn bởi JavaScript/mobile client hay có hỗn hợp cơ chế?
5. Có cross-origin requests/SSO hoặc proxy/gateway ảnh hưởng header không?
6. Có integration tests chứng minh CSRF không gây bypass, không chặn nhầm endpoint hợp lệ không?

Chỉ khi mô hình đe dọa cho phép, mới tắt CSRF **ở đúng chain cần thiết**:

~~~java
// MINH HỌA cho API stateless, không dùng browser-auto credentials:
http.csrf(csrf -> csrf.disable());
~~~

Nếu tắt trên fallback chain browser, có thể khiến session-based UI không còn lớp bảo vệ cần thiết. Bài mẫu **giữ CSRF bật**.

## 12. CORS và preflight không phải authorization

Browser có thể gửi:

~~~text
OPTIONS /api/reports/summary
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: Authorization
~~~

CORS quyết định **trình duyệt** được phép chia sẻ response giữa các origin nào. Nó không phải policy cấp quyền đọc report. Một request không cần CORS (curl/service-to-service) vẫn phải được kiểm tra Authentication và Authorization.

Một cấu hình reactive CORS minh họa:

~~~java
// MINH HỌA trong @Configuration:
@Bean
org.springframework.web.cors.reactive.CorsConfigurationSource corsSource() {
    var cors = new org.springframework.web.cors.CorsConfiguration();
    cors.setAllowedOrigins(
            java.util.List.of("https://app.example.com"));
    cors.setAllowedMethods(
            java.util.List.of("GET", "POST", "OPTIONS"));
    cors.setAllowedHeaders(
            java.util.List.of("Authorization", "Content-Type",
                    "X-CSRF-TOKEN"));

    var source = new org.springframework.web.cors.reactive
            .UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

**Lưu ý khi copy:** để đoạn trên biên dịch, phải đặt tên class `UrlBasedCorsConfigurationSource` cùng dòng import hoặc fully qualified name không ngắt ở giữa tên package bằng cú pháp Java sai. Dùng đoạn chính xác:

~~~java
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
~~~

Sau đó thêm `http.cors(withDefaults())` cho chain tương ứng và cấu hình nguồn CORS theo yêu cầu Spring Security version đang dùng. Nếu preflight bị chặn bởi authorization trước khi CORS được xử lý đúng, browser sẽ báo lỗi; đừng xử lý bằng cách mở rộng `permitAll("/**")`. Chỉ cho origin/method/header cần thiết, và với cookie phải kiểm tra `allowCredentials` + allowed origins cụ thể (không dùng wildcard thiếu kiểm soát).

## 13. Reactive Method Security và object-level permissions

HTTP layer thường chỉ nhìn URI, method và authorities; quyền đối với một Document cụ thể cần xét resource.

Spring Security WebFlux có:

~~~java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
~~~

Một service đơn giản:

~~~java
@Service
public class DocumentReader {
    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> readDocument(String id) {
        return repository.findById(id)
                .map(Document::getContent);
    }
}
~~~

**Đây là đoạn mô hình**, `repository` và `Document` cần định nghĩa. Annotation chỉ xét authority `DOC_READ`, **chưa kiểm tenant/owner của ID**. Nếu muốn bảo vệ object-level, thêm policy bean với reactive lookup đáng tin hoặc query hạn chế theo tenant/owner và deny khi không tìm thấy. Không dùng `@EnableMethodSecurity` của servlet khi cố ý triển khai reactive method authorization; dùng cấu hình reactive tương ứng cho stack này.

### Reactor Context thay vì ThreadLocal chủ quan

Trong reactive flow, user context có thể nằm trong `ReactiveSecurityContextHolder`:

~~~java
// ĐOẠN MINH HỌA trong reactive service:
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
~~~

Nếu tạo thread mới hoặc tự gọi `subscribe()` bên trong service, có thể mất context hoặc phá vòng đời transaction/error. Nên compose `Mono`/`Flux` và để framework subscribe. Không dùng `Thread.sleep()`, `block()` hoặc repository JDBC blocking trực tiếp trên Netty event loop.

## 14. Functional endpoints cũng cần security

WebFlux có thể dùng annotated controllers hoặc RouterFunctions:

~~~java
// MINH HỌA router function:
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
            RequestPredicates.GET("/api/public/fn"),
            request -> ServerResponse.ok()
                    .bodyValue("fn"));
}
~~~

WebFlux Security dựa trên `WebFilter` nên áp dụng cả handler function khi request đi qua cùng WebFlux application. Tuy nhiên, router function không có `@PreAuthorize` trên một controller method tương ứng; object-level authorization cần ở service/handler hoặc custom manager. Test route mới dưới cùng `SecurityWebFilterChain`.

## 15. Những lỗi cấu hình hay gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| IDE không tìm thấy `ServerHttpSecurity` | Dùng starter servlet/thiếu Spring Security WebFlux | Dùng `spring-boot-starter-webflux` + security |
| Có `HttpSecurity` trong WebFlux config | Trộn stack Servlet với Reactive | Đổi sang `ServerHttpSecurity` và `SecurityWebFilterChain` |
| 401 cho request chưa login | Authentication chưa có | Xác thực đúng HTTP Basic/JWT; kiểm entry point |
| 403 dù đã login | Thiếu role/authority hoặc CSRF | Phân biệt bằng GET/POST và security logs |
| Mọi request vào fallback thay vì API chain | `@Order` sai; fallback match-all ở trước | Đặt API chain ưu tiên cao |
| `/internal/**` không được bảo vệ | Chỉ có chain match `/api/**` | Thêm fallback chain denyAll |
| `/api/admin/**` chỉ cần đăng nhập | Rule `/api/** authenticated` đặt trước | Sắp xếp specific trước general |
| Role ADMIN không match | Dùng `hasRole("ROLE_ADMIN")` hoặc authority thiếu prefix | `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Path `/api` xử lý khác `/api/**` | Pattern/route khác dự kiến | Test cả slash/encoded/path variables |
| POST admin trả 403 nhưng GET admin 200 | CSRF token thiếu hoặc rule POST khác | Giữ CSRF và gửi token đúng |
| POST viewer có token vẫn 403 | Không có ROLE_ADMIN | Đây là authorization deny hợp lý |
| `WebTestClient` test pass nhưng security không chạy | BindToController không gắn security | Bind application context và apply springSecurity |
| Mở `permitAll("/**")` để sửa CORS | CORS và authorization bị nhầm | Cấu hình CorsConfigurationSource/preflight đúng |
| API Basic tắt CSRF vô điều kiện | Browser có thể tự gửi Basic credentials | Threat model; giữ CSRF cho browser-auto credentials |
| Controller dùng `.block()` | Blocking Netty event loop | Compose Mono/Flux, reactive driver hoặc boundedElastic có kiểm soát |
| Lấy principal bằng Servlet ThreadLocal | Reactor Context khác ThreadLocal | `ReactiveSecurityContextHolder` và reactive composition |
| `@PreAuthorize` trên Mono không hoạt động | Chưa bật Reactive Method Security/proxy sai | `@EnableReactiveMethodSecurity`, test Spring context |
| Endpoint mới bỗng mở quyền | Catch-all authenticated/permitAll quá rộng | Deny-by-default, negative tests |
| JWT chuyển sang Basic không rõ | Trộn filter mechanisms và config giữa chains | Tách chain theo path, cơ chế auth rõ ràng |
| Quyền HTTP pass nhưng sửa được object người khác | Chỉ xét role chung | Service-level resource/tenant authorization |
| Log lộ Authorization header | Debug ghi raw credentials | Redact tokens, không log secrets |

## 16. Checklist review trước production

1. Ứng dụng thật sự chạy WebFlux, không vô tình kéo servlet stack và dùng nhầm `HttpSecurity`?
2. Các beans `SecurityWebFilterChain` có matcher và `@Order` rõ ràng?
3. Có một fallback chain bảo vệ request không khớp chain chuyên biệt?
4. `authorizeExchange` sắp xếp specific rule trước general rule?
5. Có `anyExchange().denyAll()` hoặc catch-all có chủ đích?
6. `hasRole`/`hasAuthority` có thống nhất `ROLE_` prefix và token mapping?
7. HTTP methods GET/HEAD/OPTIONS/POST/PUT/PATCH/DELETE được test theo hợp đồng?
8. API state-changing dùng browser-auto credentials có CSRF token?
9. CORS được đặt theo trusted origins, không dùng `permitAll("/**")` thay thế?
10. Cơ chế authentication giữa HTTP Basic/form/JWT được phân định và TLS được bật ở production?
11. Tất cả endpoints có object-level policies tại service khi cần?
12. Security context được chuyển qua Reactor Context, không tự block/subscribe?
13. Các remote/repository-based reactive authorization managers có timeout và fail-closed?
14. WebTestClient test cùng Spring Security filters thật, đủ positive và negative cases?
15. Có test chain selection, fallback, admin route và route mới bị deny?
16. Có kiểm tra CSRF 403 khác với role 403?
17. Gateway rewrite/forwarded headers có được test theo path Spring thực nhận?
18. Actuator/health/metrics có policy tương ứng chứ không chỉ whitelist mơ hồ?
19. Error handling không lộ resource metadata hoặc principal/token trong logs?
20. Phân quyền có được review khi nâng Spring Security 6.x sang 7.x không?

## 17. Bài tập tự luyện

**Bài 1 – Thứ tự rule.** Cố tình đưa `.pathMatchers("/api/**").authenticated()` lên trước `/api/admin/**`. Viết test với viewer truy cập dashboard, quan sát sai khác; sau đó sửa và giữ test regression.

**Bài 2 – Cấp chain.** Đổi `@Order(1)` sang fallback chain, giữ API chain ở Order 2. Kiểm tra request `/api/admin/dashboard` dùng rule nào; sửa thứ tự và giải thích chain selection khác rule selection.

**Bài 3 – Chặn endpoint mới.** Tạo GET `/api/debug/secrets`, chưa khai rule. Người dùng admin vẫn phải nhận 403 do `anyExchange().denyAll()`. Khi có yêu cầu chính thức mới bổ sung rule hẹp.

**Bài 4 – Phân quyền theo method.** Bổ sung DELETE `/api/reports/{id}`, chỉ cho `REPORT_DELETE`. Test viewer chỉ có `REPORT_READ` bị từ chối, admin không tự có DELETE nếu chưa được cấp.

**Bài 5 – CSRF.** Giữ Basic và CSRF mặc định. Viết hai test POST của admin có/không `mutateWith(csrf())`; kết quả phải khác nhau. Giải thích tại sao không tắt CSRF chỉ vì controller nhận JSON.

**Bài 6 – JWT.** Tạo chain `/api/**` riêng cho OAuth2 resource server, thêm starter resource-server và issuer verifier hợp lệ. Test expired token, token sai chữ ký, scope thiếu, request không token, và tenant object-level deny.

**Bài 7 – Custom reactive manager.** Viết `ReactiveAuthorizationManager<AuthorizationContext>` đọc policy repository bằng R2DBC. Trả DENY khi không có rule và không trả allow khi timeout. Dùng `.access(manager)` trước `anyExchange()`.

**Bài 8 – Resource scope.** Viết service đọc Document theo `id + tenantId` và active membership của principal. Chứng minh role `REPORT_READ` không cho user tenant A đọc dữ liệu tenant B.

**Bài 9 – CORS.** Chỉ cho `https://app.example.com` dùng Authorization header. Test preflight hợp lệ/không hợp lệ và xác nhận GET vẫn yêu cầu authentication khi request thực đi tới server.

**Bài 10 – Reactive Context.** Tạo service dùng `ReactiveSecurityContextHolder` lấy principal; kết hợp `flatMap` với repository. So sánh với việc tự `subscribe()` hoặc `block()` và giải thích rủi ro.

**Tiêu chí hoàn thành:** tạo và giải thích được `SecurityWebFilterChain` từ `ServerHttpSecurity`, phân biệt `securityMatcher` và `authorizeExchange.pathMatchers`, nắm chain/rule ordering, deny-by-default, cấu hình Basic/CSRF đúng, kiểm thử bằng `WebTestClient` cùng Spring Security test support và không nhầm WebFlux với Servlet hoặc HTTP authorization với object-level policy.

## 18. Tài liệu tham khảo chính thức

- Spring Security 6.5 – **WebFlux Security**, explicit config và multiple chains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security – **Authorize ServerHttpRequest** và `authorizeExchange`: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 – **ServerHttpSecurity API**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security – **Testing Authentication on WebFlux**, `WebTestClient`, `mockUser`: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security – **WebTestClient Security Setup**: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security 6.5 – **CSRF for WebFlux**: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security – **Reactive Method Security**: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Framework – **WebTestClient**, binding to ApplicationContext: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security 6.5 – **Migration to Spring Security 7 Configuration**, lambda DSL: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
