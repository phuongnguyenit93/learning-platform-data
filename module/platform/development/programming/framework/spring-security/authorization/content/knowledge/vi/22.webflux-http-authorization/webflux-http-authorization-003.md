# anyExchange và phạm vi mặc định từ chối trong Spring Security WebFlux

## 1. Khi thêm API mới, điều gì bảo vệ API đó?

Một ứng dụng Spring WebFlux có các endpoint đã được phê duyệt:

```http
GET /public/ping
GET /api/profile
GET /api/reports/monthly
POST /api/reports
```

Sau một lần triển khai, developer thêm `GET /api/preview`, `GET /api/admin/restricted` và `GET /internal/diagnostics`. Nếu filter chỉ dùng:

```java
.authorizeExchange(ex -> ex
    .anyExchange().authenticated()
)
```

mọi route chưa có chính sách hẹp đều có thể đi qua với **bất kỳ người dùng đã đăng nhập**, dù nhóm bảo mật chưa duyệt quyền của route mới.

Mục tiêu của chủ đề này là xây **allowlist HTTP**: chỉ cho phép những path và method được xét tường minh; còn lại mặc định từ chối.

```java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/profile")
        .authenticated()
    .pathMatchers(HttpMethod.GET, "/api/reports/{period}")
        .hasRole("AUDITOR")
    .pathMatchers(HttpMethod.POST, "/api/reports")
        .hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

Đây là đoạn DSL minh họa, chưa là class độc lập. `anyExchange().denyAll()` là rule **catch-all**: trong phạm vi của **SecurityWebFilterChain đang xử lý request**, những exchange chưa match rule nào ở trước sẽ bị từ chối kể cả khi người gọi là admin.

Nhưng **không được hiểu** `anyExchange` là bảo vệ toàn bộ cổng HTTP mà không cần xét `securityMatcher` và thứ tự nhiều chains. Đó là bẫy chính mà bài này giải quyết.

**Kết quả học tập:** xác định phạm vi của `anyExchange`; phân biệt `denyAll`/`authenticated`/`permitAll`; viết matchers theo đúng thứ tự; cấu hình nhiều `SecurityWebFilterChain` không tạo vùng hở; kiểm thử GET/POST/HEAD, route chưa cấp phép, CSRF và cả fallback chain bằng **WebTestClient**.

## 2. Cơ chế WebFlux: chọn chain trước, xét rule sau

Spring Security WebFlux không sử dụng `HttpSecurity` và `SecurityFilterChain` theo kiểu Servlet. Các lớp chủ đạo:

| Thành phần WebFlux | Vai trò |
|---|---|
| `ServerHttpSecurity` | Builder cho reactive HTTP security |
| `SecurityWebFilterChain` | Một chuỗi WebFilters bảo vệ các exchanges khớp chain |
| `securityMatcher(...)` | Chỉ định request thuộc **chain** nào |
| `authorizeExchange(...)` | Quy định policy của các exchanges **đã vào chain** |
| `pathMatchers(...)` | Khớp HTTP path và, nếu chỉ định, HTTP method |
| `anyExchange()` | Rule “còn lại” trong một authorization specification |
| `ReactiveAuthorizationManager` | API để kiểm tra quyền phản ứng bất đồng bộ |
| `WebTestClient` | Kiểm thử WebFlux application/filter chain |
| `ReactiveSecurityContextHolder` | SecurityContext trong Reactor Context |

Luồng cơ bản:

```text
HTTP Request (ServerWebExchange)
          |
          v
[Chọn SecurityWebFilterChain đầu tiên khớp securityMatcher]
          |
          v
[Áp dụng authorizeExchange của chain vừa được chọn]
          |
       ┌──┴─────────────────────────┐
       v                            v
pathMatchers cụ thể          anyExchange (còn lại)
       |                            |
       v                            v
permitAll / authenticated   denyAll
/ hasRole / access               |
       |                            v
       v                        403 hoặc 401 tùy auth/entrypoint
     ALLOW
       |
       v
  WebFlux handler / reactive service
```

**Hai tầng matching** phải được kiểm tra độc lập:

1. `securityMatcher(...)` của chain quyết định **chain có tham gia hay không**.
2. `pathMatchers(...)` và `anyExchange()` quyết định **policy bên trong chain đã được chọn**.

Nếu không có chain nào match request, không thể giả định `anyExchange().denyAll()` của một chain khác sẽ bảo vệ nó. Phải thiết kế catch-all chain hoặc một chain không giới hạn phạm vi.

### 2.1. Với một chain không đặt securityMatcher

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET, "/public/ping")
                .permitAll()
            .anyExchange().denyAll()
        )
        .build();
}
```

Đây là **một mẫu cấu hình** cho ứng dụng một chain. Khi không giới hạn `securityMatcher` riêng, chain thường match mọi request của web application, do đó catch-all áp dụng cho phần còn lại của ứng dụng đó.

### 2.2. Với chain chỉ khớp /api/**

```java
@Bean
SecurityWebFilterChain apiOnly(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().denyAll()
        )
        .build();
}
```

Đoạn này **không đủ làm toàn bộ cấu hình security của ứng dụng** nếu còn routes ngoài `/api/**`. `GET /internal/diagnostics` không được chain `apiOnly` chọn. Nếu không còn fallback `SecurityWebFilterChain` nào, request có nguy cơ không được bảo vệ bởi Spring Security.

**Kết luận:** `denyAll` mạnh đến đâu cũng không có tác dụng với request **không đi qua chain chứa nó**.

## 3. So sánh ba catch-all phổ biến

```java
.anyExchange().permitAll()
```

Cho exchange còn lại đi qua **authorization decision** này mà không đòi authenticated. Đây thường không phù hợp với backend có dữ liệu nhạy cảm.

```java
.anyExchange().authenticated()
```

Chỉ đòi caller đã xác thực; route mới bất kỳ có thể được mọi tài khoản đăng nhập truy cập. Đây là **default requiring authentication**, không phải **explicit allowlist**.

```java
.anyExchange().denyAll()
```

Không cấp quyền cho exchange còn lại, kể cả admin. Chỉ thêm một endpoint vào controller không làm endpoint đó tự được phép. Nhóm phát triển phải thêm rule rõ ràng và regression test.

| Exchange chưa có matcher riêng | permitAll | authenticated | denyAll |
|---|---|---|---|
| Anonymous GET /api/preview | Có thể qua authorization | Chặn/đòi login | Chặn |
| User GET /api/preview | Có thể qua | Có thể qua | Chặn |
| Admin GET /api/preview | Có thể qua | Có thể qua | Chặn |
| User POST /api/preview | Có thể qua authorization (CSRF có thể chặn riêng) | Có thể qua authorization | Chặn |
| Route mới sau deploy | Không tự yêu cầu phê duyệt | Mở cho user authenticated | Mặc định đóng |

**Lưu ý:** `permitAll` không vô hiệu hóa CSRF, CORS, security headers, request validation hay routing. Ngược lại, `denyAll` trong một chain không thay thế tenant/object-level checks ở những endpoint đã được allow.

### 3.1. denyAll không đồng nghĩa một status code cố định

Với người dùng **đã xác thực**, thường là HTTP **403 Forbidden**. Với người dùng **chưa xác thực**, authentication entry point có thể tạo HTTP **401 Unauthorized** (HTTP Basic/Bearer) hoặc redirect (form login). Không khẳng định mọi lần denyAll đều trả 403.

## 4. Matcher order: rule nào khớp trước được áp dụng trước

Một cấu hình an toàn:

```java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/profile")
        .authenticated()
    .pathMatchers(HttpMethod.GET, "/api/reports/{period}")
        .hasRole("AUDITOR")
    .pathMatchers(HttpMethod.POST, "/api/reports")
        .hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

Một cấu hình nguy hiểm:

```java
// Phản ví dụ: rule rộng che policy hẹp.
.authorizeExchange(ex -> ex
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

Khi `/api/admin/x` đã khớp `/api/**`, việc có `hasRole("ADMIN")` ở dưới không có nghĩa hai rule được **AND** với nhau; rule sau có thể không được xét. `anyExchange().denyAll()` cũng không thể thu hồi quyền từ một matcher đã allow trước đó.

**Quy tắc:** matcher hẹp, nhạy cảm trước; matcher rộng sau; `anyExchange().denyAll()` ở **cuối cùng**. Cố đặt rule sau `anyExchange` có thể bị builder từ chối vì unreachable.

### 4.1. HTTP method là một phần của policy

```java
.pathMatchers(HttpMethod.GET, "/api/profile")
    .authenticated()
```

Chỉ mô tả GET:
- `GET /api/profile` của user authenticated: có thể đi tiếp.
- `POST /api/profile`: không match, rơi vào deny.
- `DELETE /api/profile`: không match, rơi vào deny.
- `HEAD /api/profile`: cần test phương thức riêng; đừng tự coi GET rule trong security là HEAD rule.
- Query `GET /api/profile?debug=true`: path vẫn là `/api/profile`, nên nếu debug bật nội dung nhạy cảm, cần kiểm tra thêm tại handler/service.

Các route nested không tự được mở: pattern `/api/reports/{period}` khớp một segment period như `monthly`, không bao phủ `/api/reports/monthly/details`.

### 4.2. Role prefix

`hasRole("AUDITOR")` thường tương đương kiểm tra `ROLE_AUDITOR`. `hasAuthority("report:read")` lại so khớp chuỗi authority chính xác. User có `ROLE_ADMIN` không tự có `ROLE_AUDITOR` trừ khi app cấu hình role hierarchy phù hợp.

`anyExchange().denyAll()` không có ngoại lệ ngầm dành cho `ROLE_ADMIN` hoặc `ROLE_SUPER_ADMIN`.

## 5. Nhiều chain và một fallback mặc định từ chối

Khi có nhiều `SecurityWebFilterChain`, Spring Security xét theo thứ tự `@Order` và chọn **chain đầu tiên khớp** `securityMatcher`. Nó **không** lấy giao các chính sách của tất cả chains.

Thiết kế đề xuất:

```text
Incoming request
   |
   +-- @Order(1) API chain, securityMatcher("/api/**")
   |       |
   |       +-- API role/path rules
   |       +-- anyExchange().denyAll()
   |
   +-- @Order(2) catch-all fallback (không securityMatcher hẹp)
           |
           +-- GET /public/ping permitAll()
           +-- anyExchange().denyAll()
```

Tức là:
- `GET /api/reports/monthly` được quyết định bởi API chain.
- `GET /public/ping` không vào API chain, được xét ở fallback và permit.
- `GET /internal/diagnostics` không vào API chain, vào fallback và deny.
- Nếu `GET /api/preview` được thêm mà không sửa policy, API chain deny.
- Admin cũng không được truy cập một route chưa có rule explicit.

**Không đặt catch-all permitAll ở độ ưu tiên cao nhất**, vì nó có thể che luôn chain API. Đừng nghĩ fallback chain sẽ “sửa” kết quả của API chain: một khi API chain được chọn, fallback không được dùng cho cùng exchange.

## 6. Bảng quyết định trước khi code

| Method + path | Chain | Điều kiện | Kỳ vọng |
|---|---|---|---|
| GET /public/ping | Fallback | Public | Allow |
| POST /public/ping | Fallback | Chưa phê duyệt | Deny |
| GET /api/profile | API | Authenticated | Allow nếu đăng nhập |
| GET /api/reports/monthly | API | ROLE_AUDITOR | Allow với Auditor |
| POST /api/reports | API | ROLE_ADMIN + CSRF khi áp dụng | Allow với Admin |
| GET /api/reports | API | Không có GET rule | Deny |
| GET /api/reports/monthly/details | API | Nested path chưa có rule | Deny |
| GET /api/preview | API | Route mới chưa duyệt | Deny |
| GET /api/admin/restricted | API | Tên route không phải authority | Deny kể cả Admin |
| GET /internal/diagnostics | Fallback | Không public | Deny |
| GET /public/secret | Fallback | Không public | Deny |
| GET /actuator/health | Fallback | Không có rule trong demo | Deny nếu cùng context/chain |

Đây là **policy cho demo**, không phải khuyến nghị bắt buộc chặn mọi health endpoint. Nếu health cần public để load balancer kiểm tra, thêm rule **hẹp** theo đúng endpoint và method, sau khi xét topology và thông tin được lộ.

## 7. Dự án mẫu Java 17 + Spring Boot 3.5.6 + Spring Security 6.5.x

Bộ demo gồm **hai chains**, một WebFlux controller với cả route được phép lẫn route cố ý bị deny, và bộ kiểm thử **JUnit 5 + WebTestClient**. Chỉ thêm `spring-boot-starter-webflux`, không thêm `spring-boot-starter-web` để giữ đúng web application type **REACTIVE**.

### 7.1. Cấu trúc thư mục

```text
webflux-default-deny/
  pom.xml
  src/main/java/com/example/webflux/
    WebfluxDefaultDenyApplication.java
    SecurityConfiguration.java
    ApiController.java
  src/test/java/com/example/webflux/
    WebFluxAuthorizationTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>webflux-default-deny</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

### 7.3. Main

**`src/main/java/com/example/webflux/WebfluxDefaultDenyApplication.java`**

```java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxDefaultDenyApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxDefaultDenyApplication.class, args);
    }
}
```

### 7.4. SecurityConfiguration

**`src/main/java/com/example/webflux/SecurityConfiguration.java`**

```java
package com.example.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**")
            )
            .authorizeExchange(ex -> ex
                .pathMatchers(
                    HttpMethod.GET, "/api/profile"
                ).authenticated()
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/{period}"
                ).hasRole("AUDITOR")
                .pathMatchers(
                    HttpMethod.POST, "/api/reports"
                ).hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        // Không set securityMatcher: match phần còn lại.
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(
                    HttpMethod.GET, "/public/ping"
                ).permitAll()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();
        UserDetails auditor = User.withUsername("auditor")
            .password(encoder.encode("auditor-pass"))
            .roles("AUDITOR")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            alice, auditor, admin
        );
    }
}
```

**Tại sao cấu hình này an toàn hơn một chain API đơn độc?**

- `apiChain` chỉ áp dụng cho `/api/**`, xét đầu tiên theo `@Order(1)`.
- Bên trong API chain, `anyExchange().denyAll()` từ chối mọi route/method chưa được duyệt.
- `fallbackChain` không có matcher hẹp, nên nhận request không thuộc API chain.
- Fallback cho đúng `GET /public/ping` public rồi từ chối phần còn lại.
- `httpBasic` chỉ minh họa một cơ chế xác thực; dùng JWT/OAuth2 trong production phải verify token và scope riêng.
- CSRF **được giữ mặc định**. Test POST có CSRF token hợp lệ để phân biệt lỗi CSRF với lỗi quyền.

`MapReactiveUserDetailsService` có 3 tài khoản local demo để dùng khi chạy `spring-boot:run`; mật khẩu được mã hóa bằng `DelegatingPasswordEncoder`. Không dùng các tài khoản này trong production.

### 7.5. API controller

**`src/main/java/com/example/webflux/ApiController.java`**

```java
package com.example.webflux;

import java.security.Principal;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @PostMapping("/public/ping")
    public Mono<String> pingWrite() {
        return Mono.just("not allowed");
    }

    @GetMapping("/public/secret")
    public Mono<String> publicSecret() {
        return Mono.just("sensitive");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile(Principal principal) {
        return Mono.just("profile:" + principal.getName());
    }

    @GetMapping("/api/profile/extra")
    public Mono<String> profileExtra() {
        return Mono.just("sensitive profile data");
    }

    @GetMapping("/api/reports/{period}")
    public Mono<String> report(
            @PathVariable("period") String period) {
        return Mono.just("report:" + period);
    }

    @GetMapping("/api/reports/{period}/details")
    public Mono<String> details() {
        return Mono.just("not approved");
    }

    @PostMapping("/api/reports")
    public Mono<ResponseEntity<String>> createReport() {
        return Mono.just(ResponseEntity.accepted().body("queued"));
    }

    @GetMapping("/api/preview")
    public Mono<String> preview() {
        return Mono.just("preview not released");
    }

    @GetMapping("/api/admin/restricted")
    public Mono<String> adminRestricted() {
        return Mono.just("restricted admin data");
    }

    @GetMapping("/internal/diagnostics")
    public Mono<String> diagnostics() {
        return Mono.just("internal data");
    }
}
```

Các handler `/api/preview`, `/api/admin/restricted` và `/internal/diagnostics` **cố ý tồn tại** nhưng không có allow rule. Nếu test nhận 403, đó là bằng chứng security chặn route đã tồn tại, không chỉ là 404 vì controller chưa có endpoint.

### 7.6. WebTestClient: unit/integration tests cho từng nhánh

**`src/test/java/com/example/webflux/WebFluxAuthorizationTest.java`**

```java
package com.example.webflux;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringBootTest
class WebFluxAuthorizationTest {
    @Autowired ApplicationContext context;
    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient as(String username, String role) {
        return client.mutateWith(mockUser(username).roles(role));
    }

    private WebTestClient withCsrf(String username, String role) {
        return as(username, role).mutateWith(csrf());
    }

    @Test
    void anonymousCanPingPublicEndpoint() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void authenticatedCanAlsoPingPublicEndpoint() {
        as("alice", "USER").get().uri("/public/ping")
            .exchange().expectStatus().isOk();
    }

    @Test
    void unauthenticatedProfileIsChallenged() {
        client.get().uri("/api/profile")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserCanReadProfile() {
        as("alice", "USER").get().uri("/api/profile")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("profile:alice");
    }

    @Test
    void auditorMayReadReport() {
        as("auditor", "AUDITOR")
            .get().uri("/api/reports/monthly")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:monthly");
    }

    @Test
    void userCannotReadAuditorReport() {
        as("alice", "USER")
            .get().uri("/api/reports/monthly")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminDoesNotAutomaticallyHaveAuditorRole() {
        as("admin", "ADMIN")
            .get().uri("/api/reports/monthly")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void nestedReportDoesNotMatchSingleSegmentPattern() {
        as("auditor", "AUDITOR")
            .get().uri("/api/reports/monthly/details")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void extraProfilePathNotWhitelisted() {
        as("admin", "ADMIN")
            .get().uri("/api/profile/extra")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void unreleasedPreviewIsDeniedForAdmin() {
        as("admin", "ADMIN")
            .get().uri("/api/preview")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminNamedPathIsNotAutomaticallyAllowed() {
        as("admin", "ADMIN")
            .get().uri("/api/admin/restricted")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminCanPostReportWithCsrf() {
        withCsrf("admin", "ADMIN")
            .post().uri("/api/reports")
            .exchange().expectStatus().isAccepted()
            .expectBody(String.class).isEqualTo("queued");
    }

    @Test
    void ordinaryUserCannotPostReportWithCsrf() {
        withCsrf("alice", "USER")
            .post().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void auditorCannotPostReportWithCsrf() {
        withCsrf("auditor", "AUDITOR")
            .post().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminWithoutCsrfCannotPost() {
        as("admin", "ADMIN")
            .post().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void getReportCollectionIsNotImplicitlyAllowed() {
        as("admin", "ADMIN")
            .get().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void postProfileRemainsDenied() {
        withCsrf("admin", "ADMIN")
            .post().uri("/api/profile")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void postPublicPingDeniedEvenWithCsrf() {
        withCsrf("alice", "USER")
            .post().uri("/public/ping")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void internalDiagnosticsDeniedByFallback() {
        as("admin", "ADMIN")
            .get().uri("/internal/diagnostics")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void publicSecretIsNotPartOfPublicAllowlist() {
        as("admin", "ADMIN")
            .get().uri("/public/secret")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void unlistedApiPathDenied() {
        as("admin", "ADMIN")
            .get().uri("/api/unknown")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void unlistedNonApiPathDenied() {
        as("admin", "ADMIN")
            .get().uri("/unknown")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void actuatorStylePathDeniedByFallback() {
        as("admin", "ADMIN")
            .get().uri("/actuator/health")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void headDoesNotGetGetMethodPermissionByDefault() {
        as("admin", "ADMIN")
            .head().uri("/api/profile")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void queryParameterDoesNotChangeProfilePathRule() {
        as("alice", "USER")
            .get().uri("/api/profile?view=normal")
            .exchange().expectStatus().isOk();
    }

    @Test
    void auditorReportQueryParameterRemainsAllowed() {
        as("auditor", "AUDITOR")
            .get().uri("/api/reports/monthly?format=text")
            .exchange().expectStatus().isOk();
    }

    @Test
    void postToGetOnlyReportPathDenied() {
        withCsrf("admin", "ADMIN")
            .post().uri("/api/reports/monthly")
            .exchange().expectStatus().isForbidden();
    }
}
```

**Vì sao dùng cách setup này?** `WebTestClient.bindToApplicationContext` dựng WebFlux handler/filter chain từ Spring ApplicationContext; `apply(springSecurity())` bật integration test security; `mockUser` tạo principal giả trong test; `csrf()` giúp chứng minh lệnh POST bị chặn/được phép theo role **thay vì** đều bị 403 do thiếu CSRF.

Đây là integration tests trên application context, không phải end-to-end test HTTP Basic qua TCP, reverse proxy hay JWT cryptographic validation. Production cần thêm test qua network và gateway cấu hình thật.

### 7.7. Cách chạy và kết quả dự kiến

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Các phương thức `@Test` phía trên dự kiến pass theo chính sách đã mô tả. **Chưa thực thi Maven**, vì vậy không trình bày đây là kết quả đo đạc thực tế. Khi chạy trên môi trường của bạn, đối chiếu JUnit output và xác minh startup WebFlux reactive thay vì Servlet MVC.

Để chạy ứng dụng:

```bash
mvn spring-boot:run
```

Ví dụ kiểm tra GET:

```bash
curl -i http://localhost:8080/public/ping
curl -i -u alice:alice-pass http://localhost:8080/api/profile
curl -i -u auditor:auditor-pass \
  http://localhost:8080/api/reports/monthly
curl -i -u admin:admin-pass \
  http://localhost:8080/api/preview
curl -i -u admin:admin-pass \
  http://localhost:8080/internal/diagnostics
```

Theo code, các status dự kiến tương ứng: **200**, **200**, **200**, **403**, **403**. Không xem đây là transcript stdout được chạy thật. Với POST dùng Basic/cookie, CSRF token cần được cung cấp theo cơ chế đã cấu hình; WebTestClient test phía trên xử lý phần này.

## 8. Ranh giới với những kiểm soát khác

### 8.1. anyExchange không thay object-level authorization

Một route:

```java
.pathMatchers(HttpMethod.GET, "/api/documents/{id}")
    .authenticated()
```

chỉ buộc user đăng nhập để dùng route. Nó **không** xác minh Document#123 thuộc tenant nào, user có quyền READ tài liệu đó hay không. Nếu handler `repository.findById(id)` bỏ tenant predicate, vẫn có lỗ hổng **IDOR/BOLA** ngay trên route được phép.

Để bảo vệ object-level:
- Xác minh resource ID và tenant canonical từ DB server-side.
- Kiểm tra membership và owner/share/role theo action thực tế.
- Dùng reactive service-level authorization khi phù hợp.
- Đưa tenant/authorization predicate xuống query của repository, đặc biệt cho list, update, delete.
- Không tin client-provided `tenantId`/`owner` như bằng chứng quyền.

### 8.2. Reactive Method Security là lớp bổ sung

Đối với service trả `Mono`/`Flux`, có thể bật:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodConfig {
}
```

Và khai báo:

```java
@Service
class ConfidentialService {
    @PreAuthorize("hasRole('AUDITOR')")
    public Mono<String> readInternal() {
        return Mono.just("auditor-only");
    }
}
```

Hai đoạn trên là **mẫu minh họa, không phải file độc lập** vì chưa kèm imports và wiring. Trong WebFlux, reactive method security sử dụng Reactor Context; không nên giả định chỉ đọc `ThreadLocal SecurityContextHolder` xuyên mọi asynchronous boundary là đúng.

Nếu `anyExchange().denyAll()` đã chặn request, method không chạy. Nếu HTTP route đã được allow, service vẫn có thể áp `@PreAuthorize` theo role/resource. Không dùng `@PostAuthorize` trên method có side effect trước khi deny mà không xét transaction và quyền truy cập.

### 8.3. CSRF

`CsrfWebFilter` có thể từ chối POST/PUT/DELETE trước khi rule authorization theo role được xét. Vì thế các test muốn kiểm tra role cho POST phải gửi CSRF token hợp lệ. Không tự động gọi `csrf.disable()` chỉ vì API trả JSON; đánh giá việc credential có thể được browser tự gửi như cookie/basic authentication hay không.

Với một API stateless chỉ dùng bearer tokens trong Authorization header, threat model CSRF có thể khác, nhưng phải đưa ra quyết định cấu hình dựa trên cơ chế xác thực và risk thật.

### 8.4. CORS, OPTIONS, static resources và Actuator

Một preflight CORS thường dùng OPTIONS. Đừng giải quyết mọi lỗi bằng một `pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` thiếu kiểm soát. Hãy cấu hình CORS origins/methods/headers cụ thể, test request preflight và request thực.

Tương tự:
- Static assets, favicon, login/logout, callback routes phải được xem xét explicit.
- Actuator health có thể cần public cho load balancer, nhưng không nên mở cùng cách với metrics/env.
- Nếu management server chạy **port/application context khác**, chain này không tự bao phủ cổng đó.
- WebSocket handshake có thể đi qua HTTP security; việc authorize từng message cần kiểm soát riêng.
- Functional routing (`RouterFunction`) cũng có thể tạo routes mới, phải kiểm tra chain coverage tương tự annotated controllers.

### 8.5. Proxy, base path và encoding

Security matcher được áp dụng trên request mà WebFlux nhận, có thể khác path bên ngoài gateway nếu proxy rewrite. Cần test:
- URL được proxy prefix/rewrite.
- Slash cuối, nhiều slash, encoded segments và path variables.
- Query parameters có làm thay đổi nội dung nhạy cảm không.
- HTTP methods ít gặp: HEAD, OPTIONS, PATCH, DELETE.
- Routes mới từ dependency, management, functional endpoint hoặc feature flag.

Không tự dùng `String.startsWith("/api/admin")` trên raw URL cho authorization nếu chưa canonicalize và kiểm soát path parsing tương ứng.

## 9. Trường hợp mở rộng: authorization động trong WebFlux

Nếu quyền phụ thuộc resource/tenant và cần gọi data source reactive, có thể triển khai `ReactiveAuthorizationManager<AuthorizationContext>` và đưa vào DSL thông qua `access(...)`. Mẫu khái niệm:

```java
public final class DocumentAccessManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final ReactiveDocumentPolicy policy;

    public DocumentAccessManager(ReactiveDocumentPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {
        return authentication
            .flatMap(auth -> policy.allowed(
                auth, context.getExchange()))
            .map(AuthorizationDecision::new)
            .defaultIfEmpty(new AuthorizationDecision(false))
            .onErrorReturn(new AuthorizationDecision(false));
    }
}
```

Đây là **mẫu API để đọc**, chưa thuộc project runnable vì cần định nghĩa `ReactiveDocumentPolicy`, imports và bean configuration. Kiểm tra chữ ký `ReactiveAuthorizationManager` theo version đang dùng; không nhầm với manager Servlet nhận `Supplier<Authentication>`. Mục tiêu:
- Không gọi `block()` trên event-loop để truy cập permission DB.
- Dùng principal/context thật và canonical object data.
- Thiếu quyết định hoặc lỗi downstream phải **fail-closed** nếu là policy bảo mật bắt buộc.
- Dùng timeout có giới hạn, observability và batch/filter trước phân trang khi danh sách lớn.

Với policy chỉ cần phân biệt HTTP methods và role, `pathMatchers(...).hasRole(...)` thường đơn giản và dễ audit hơn custom manager.

## 10. Cách review thay đổi security chain

Trước một pull request thêm endpoint:
1. Xác định endpoint dùng WebFlux annotated controller hay RouterFunction.
2. Tìm chain nào match request (cả `securityMatcher`, port và `@Order`).
3. Tìm **matcher đầu tiên** match method/path trong chain đó.
4. Nếu route public, giới hạn theo đúng path/method và thông tin được trả.
5. Nếu route cần quyền, chọn authority/role hoặc object-level check phù hợp.
6. Thêm test **allow** cho actor đúng và test **deny** cho anonymous, actor sai role, actor khác tenant.
7. Thêm test cho HTTP method chưa được cấp quyền, query/path nested, route dự phòng.
8. Nếu có CSRF, cung cấp token khi test role trên unsafe methods.
9. Không bỏ fallback catch-all, không chuyển blanket authenticated/permitAll để “sửa 403” mà không review.
10. Test thật với gateway/actuator/management port khi thay topology.

**Phương pháp tự kiểm tra:** cố ý tạo một handler không có allow rule trong mỗi chain và xác nhận request authenticated vẫn bị 403. Demo có `/api/preview` (API chain) và `/internal/diagnostics` (fallback chain), nên chứng minh được catch-all đang thực thi chứ không chỉ là 404 do không có handler.

## 11. Sai lầm phổ biến

| Sai lầm | Rủi ro | Cách sửa |
|---|---|---|
| `anyExchange().authenticated()` thay cho denyAll | Mọi route mới có thể mở cho tất cả user đã login | Dùng explicit allowlist rồi denyAll |
| `/api/** permitAll` trước `/api/admin/**` | Rule rộng che role hẹp | Đặt matcher đặc biệt trước |
| Chỉ có chain `securityMatcher("/api/**")` | Route ngoài API không có chain bảo vệ | Catch-all fallback |
| Catch-all `permitAll` đặt ưu tiên cao | Chain hẹp phía sau không được chọn | Xem lại `@Order` và matcher |
| Giả định mọi chain đều được cộng dồn | Hiểu sai kết quả khi nhiều chains | First matching chain |
| Gọi GET rule là đủ cho POST/HEAD | Method khác vô tình thiếu policy rõ | Match method, test HEAD/POST |
| Cấm GET nhưng để route POST permit rộng | Tồn tại alternate operation | Kiểm tra mọi HTTP method được hỗ trợ |
| Tên route có `admin` nên cho admin | Không có security semantics trong tên | Role rule explicit |
| Chỉ test URL không có handler | 404 không chứng minh denyAll | Test handler có thật nhưng chưa allow |
| Cho public toàn `/public/**` | Có thể lộ `/public/secret` | Public exact method/path |
| Bỏ CSRF để test POST thành công | Có thể gây CSRF vulnerability | Dùng `csrf()` trong WebTestClient |
| Dùng `HttpSecurity`/`MockMvc` cho WebFlux | Sai security stack | `ServerHttpSecurity`/`WebTestClient` |
| Role ADMIN mặc định bao hàm AUDITOR | Sai authority mapping | Explicit role hierarchy nếu cần |
| Chỉ kiểm tra route chứ không kiểm tra document ID | BOLA/IDOR | Tenant và object-level authorization |
| Để management port không có policy | Endpoint hệ thống lộ ngoài ý muốn | Kiểm tra security theo từng context/port |
| Bỏ qua proxy path rewrite | Matcher bảo vệ khác path thực | Integration tests qua gateway |
| Tạo custom reactive policy bằng `block()` | Chặn event-loop, giảm throughput | Mono/Flux và Reactor Context |

## 12. Checklist

- [ ] Dùng đúng Spring WebFlux/`ServerHttpSecurity`, không nhầm Servlet.
- [ ] `authorizeExchange` có matcher theo path và HTTP method.
- [ ] Các matcher đặc thù xuất hiện trước matcher tổng quát.
- [ ] `anyExchange().denyAll()` đặt cuối mỗi chain cần explicit allowlist.
- [ ] Mọi `SecurityWebFilterChain` có `@Order`/`securityMatcher` được review.
- [ ] Có catch-all fallback chain cho request không vào chains chuyên biệt.
- [ ] Không cho rằng `anyExchange` bảo vệ ngoài chain chứa nó.
- [ ] `permitAll` chỉ áp dụng cho endpoint public chính xác.
- [ ] `authenticated` không được dùng để vô tình mở mọi API mới.
- [ ] Có kiểm thử request authenticated cho route có handler nhưng chưa cấp phép.
- [ ] Test GET/POST/HEAD, role, query, nested path và unknown path.
- [ ] Test 401 với anonymous khi entry point yêu cầu xác thực và 403 với user không đủ quyền.
- [ ] CSRF/CORS được kiểm soát độc lập, không blanket disable.
- [ ] Route đã mở vẫn kiểm tra permission từng object/tenant.
- [ ] Management port, gateway, WebSocket và background access có security riêng khi cần.
- [ ] Logs/metrics theo dõi 401/403 và policy changes, không in secrets.
- [ ] Policy thay đổi phải có review, negative tests và regression suite.

## 13. Câu hỏi tự kiểm tra

**1.** `anyExchange().denyAll()` trong chain chỉ match `/api/**` có chặn `/internal/diagnostics` không?

**Đáp án:** Không. Request đó không được API chain chọn. Cần fallback catch-all chain hoặc một chain bao phủ toàn ứng dụng.

**2.** `anyExchange().authenticated()` có phải một allowlist “chỉ endpoint đã phê duyệt” không?

**Đáp án:** Không. Nó yêu cầu đăng nhập nhưng không tự phân biệt route đã duyệt/chưa duyệt.

**3.** Vì sao `/api/admin/restricted` có thể bị 403 ngay cả khi caller có `ROLE_ADMIN`?

**Đáp án:** Vì thiếu allow rule cho route. `anyExchange().denyAll()` không có ngoại lệ admin.

**4.** GET `/api/reports/monthly` được cấp `ROLE_AUDITOR`. POST vào cùng path có tự được cấp không?

**Đáp án:** Không; rule có giới hạn HTTP GET, method POST phải có rule riêng, nếu không sẽ bị deny.

**5.** Tại sao phải gửi CSRF token khi test POST có role đúng?

**Đáp án:** Nếu thiếu CSRF, filter có thể chặn trước khi kiểm tra authorization. Thêm token để test thật sự kiểm chứng role/matcher.

**6.** Mở `GET /api/documents/{id}` cho user authenticated đã đủ bảo vệ dữ liệu từng tenant chưa?

**Đáp án:** Chưa. Còn phải kiểm tra tenant canonical của document, membership, owner/share và action permission. `anyExchange` là HTTP-route authorization chứ không tự giải quyết BOLA.

## 14. Tài liệu chính thức

- [Spring Security 6.5 — Reactive Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, `anyExchange` và quyết định quyền.
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): `SecurityWebFilterChain`, `ServerHttpSecurity`, nhiều chains và `@Order`.
- [Spring Security 6.5 — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor Context, reactive method checks và `@PreAuthorize`.
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `bindToApplicationContext`, `springSecurity()`.
- [Spring Security 6.5 — Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): reactive `mockUser()` và `@WithMockUser`.
- [Spring Security 6.5 — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `csrf()` trong WebTestClient.

**Ghi nhớ:** `anyExchange().denyAll()` chỉ chặn exchange còn lại **bên trong `SecurityWebFilterChain` đang được chọn**. Muốn bảo vệ WebFlux mặc định từ chối, phải phối hợp **matcher hẹp theo method/path**, **đúng thứ tự first-match**, **fallback chain bao phủ các request ngoài phạm vi chain chuyên biệt**, **WebTestClient negative tests** và **object-level checks** cho các routes đã được mở.