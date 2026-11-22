# `pathMatchers`, HTTP method và thứ tự quy tắc trong Spring Security WebFlux

## Mục tiêu và một lỗi phân quyền thực tế

Một dịch vụ báo cáo có các API:

| Request | Chính sách |
| --- | --- |
| `GET /api/status` | Công khai |
| `GET /api/reports/public/guide` | Công khai |
| `GET /api/reports/admin/audit` | Chỉ `ROLE_ADMIN` |
| `GET /api/reports/42` | Authority `report:read` |
| `POST /api/reports` | Authority `report:write` |
| `DELETE /api/reports/42` | Authority `report:delete` |
| Các method/path còn lại | Từ chối |

Nếu cấu hình:

```java
// SAI: rule GET rộng ở trên che rule admin bên dưới.
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("report:read")
    .pathMatchers(HttpMethod.GET, "/api/reports/admin/**")
        .hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

thì một người chỉ có `report:read` có thể qua HTTP authorization ở `GET /api/reports/admin/audit`: matcher `GET /api/reports/**` đã khớp trước. **Spring Security xét các rule theo thứ tự khai báo, không tự chọn rule có đường dẫn cụ thể nhất.**

Đổi thứ tự:

```java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/reports/admin/**")
        .hasRole("ADMIN")
    .pathMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("report:read")
    .anyExchange().denyAll()
)
```

là cách giải quyết đúng trong một chain.

Bài này nằm trong nhóm **HTTP trên WebFlux** của Spring Security authorization, tập trung vào:

1. Các overload của `pathMatchers`, cách khớp HTTP method và các ký hiệu đường dẫn.
2. Quy tắc **first matching rule wins** trong `authorizeExchange`.
3. Phân biệt `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, `denyAll`.
4. Mối quan hệ giữa `SecurityWebFilterChain`, `securityMatcher`, `@Order` và rule bên trong chain.
5. Cấu hình ứng dụng Spring Boot 3.5.8/Java 17 chạy WebFlux thật.
6. Integration tests với `WebTestClient`, `mockUser` và CSRF cho GET/POST/DELETE, public và admin.
7. Các lỗi bảo mật phát sinh từ fallback rộng, CORS, HEAD/OPTIONS, URL normalization và thiếu object-level authorization.

Nguyên tắc: **đặt rule cần bảo vệ đặc biệt trước rule rộng, chỉ mở đúng tổ hợp method/path, đặt fallback deny ở cuối, và kiểm thử các trường hợp overlap.**

## 1. WebFlux khác Servlet: không nhầm hai DSL

| Spring MVC / Servlet | Spring WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| `requestMatchers(...)` | `pathMatchers(...)`, `matchers(...)` |
| `HttpServletRequest` | `ServerWebExchange` |
| `MockMvc` | `WebTestClient` |
| `AuthorizationManager` | `ReactiveAuthorizationManager` |

WebFlux sử dụng reactive `WebFilter`; không thay tên `HttpSecurity` thành `ServerHttpSecurity` rồi giữ nguyên các method của Servlet DSL. Các ví dụ sau chỉ dùng Spring WebFlux.

Một request đi qua:

```text
Client / HTTP request
         |
         v
WebFilterChainProxy
         |
         v
Chọn SecurityWebFilterChain đầu tiên khớp
    dựa trên securityMatcher và @Order
         |
         v
Authentication + CSRF/CORS + các WebFilter
         |
         v
authorizeExchange trong chain đã chọn
         |
   Duyệt các rule theo thứ tự khai báo
         |
         v
Rule khớp đầu tiên -> ALLOW hoặc DENY
         |
         +--> ALLOW: controller / WebFlux handler
         |
         +--> DENY: authentication entry point
                    hoặc access-denied handler
```

**Hai thứ tự khác nhau:**

- **Thứ tự chọn chain:** các `SecurityWebFilterChain` có `@Order`; `securityMatcher` xác định request có thuộc chain hay không.
- **Thứ tự chọn rule:** sau khi chọn chain, `authorizeExchange` xét các matcher của chain ấy theo đúng thứ tự bạn khai báo.

Spring không cộng dồn quyền ở tất cả chain và cũng không áp dụng tất cả rule từng khớp.

## 2. Hiểu các dạng `pathMatchers`

### 2.1. Chỉ có path, không giới hạn HTTP method

```java
.pathMatchers("/api/reports/**").authenticated()
```

Rule này không phân biệt GET, POST, PUT, PATCH, DELETE hay HEAD. Nếu nó đứng trước rule DELETE cần `report:delete`, một người chỉ đăng nhập có thể qua HTTP authorization khi gọi DELETE, vì rule rộng đã cho phép.

Đừng dùng đường dẫn chung cho tất cả method nếu mỗi action có mức quyền riêng.

### 2.2. Có method và path

```java
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:read")
.pathMatchers(HttpMethod.POST, "/api/reports")
    .hasAuthority("report:write")
.pathMatchers(HttpMethod.DELETE, "/api/reports/*")
    .hasAuthority("report:delete")
```

Mỗi matcher cần đồng thời khớp **HTTP method và path**.

| Request | Khớp rule GET? | Khớp rule POST? | Khớp rule DELETE? |
| --- | --- | --- | --- |
| `GET /api/reports/42` | Có | Không | Không |
| `POST /api/reports` | Không | Có | Không |
| `DELETE /api/reports/42` | Không | Không | Có |
| `PATCH /api/reports/42` | Không | Không | Không |
| `GET /api/reports/admin/audit` | Có nếu rule GET rộng đứng trước rule admin | Không | Không |

Các method không khớp sẽ tiếp tục xuống rule sau. Nếu fallback là `denyAll`, chúng bị từ chối thay vì tự dùng quyền của GET.

### 2.3. Chỉ có method

```java
.pathMatchers(HttpMethod.GET)
    .hasAuthority("report:read")
```

Có thể match **mọi GET trong chain**, kể cả URL không liên quan tới báo cáo. Không đặt rule kiểu này trước ngoại lệ public/admin nếu không chủ ý áp quyền cho toàn bộ GET.

### 2.4. Catch-all với `anyExchange`

```java
.anyExchange().denyAll()
```

Nó dùng cho những request chưa khớp ở chain hiện tại. Đặt cuối để tránh che mọi rule phía sau.

Có thể dùng `.anyExchange().authenticated()` trong ứng dụng có chủ đích cho mọi URL mới chỉ cần login, nhưng với API theo allowlist, **`denyAll()` an toàn hơn khi thêm endpoint mới**. Không dùng `.anyExchange().permitAll()` như fallback cho API nhạy cảm.

### 2.5. `matchers` với `ServerWebExchangeMatcher`

```java
.matchers(customServerWebExchangeMatcher)
    .access(customReactiveAuthorizationManager)
```

Đây là **mảnh cấu hình**, không phải file Java độc lập. Dùng khi path + method không đủ mô tả ngữ cảnh. Matcher/manager phải lấy user/tenant/resource từ nguồn tin cậy, không coi một header do client gửi là bằng chứng đã xác thực.

## 3. Cú pháp path: `*`, `**`, `{id}`

`pathMatchers` của WebFlux dùng `PathPatternParserServerWebExchangeMatcher`, dựa trên cơ chế `PathPattern` của Spring.

| Pattern | Ý nghĩa điển hình |
| --- | --- |
| `/api/status` | Một path cụ thể |
| `/api/reports/*` | Một segment ngay sau `/api/reports/` |
| `/api/reports/{id}` | Một segment và tên biến `id` |
| `/api/reports/**` | Các path trong nhánh reports, gồm phần sâu hơn |
| `/api/reports/admin/**` | Các path trong nhánh admin |
| `/api/**` | Nhánh API rộng |
| `/**` | Catch-all path |

Đường `/api/reports/admin/audit` có nhiều segment sau `/api/reports`, vì vậy rule `/api/reports/**` cũng có thể khớp nó. Spring Security không tự ưu tiên `/api/reports/admin/**` nếu bạn đặt nó sau.

**Không giả định `PathPattern` là hệ thống glob file hoặc mọi quy tắc của `AntPathMatcher`.** Các dấu `**` cần ở vị trí được parser hỗ trợ. Hãy dùng những pattern đơn giản và integration test với path thực tế.

### 3.1. Matcher security và route controller không phải một

Controller có thể khai:

```java
@GetMapping("/api/reports/admin/audit")
public Mono<String> audit() {
    return Mono.just("AUDIT");
}
```

WebFlux chọn handler theo route mapping, còn `authorizeExchange` chọn rule theo **thứ tự cấu hình security**. Controller route hẹp không khiến rule security hẹp tự được xét trước.

### 3.2. Dấu slash cuối, chữ hoa, URL encoding

Các trường hợp `/api/status` và `/api/status/`, chữ hoa/thường, đường dẫn đã percent-encode, semicolon, double slash hay reverse-proxy rewrite có thể được parser và gateway xử lý khác nhau. Không suy luận chúng tương đương khi thiết kế bảo mật.

Với API quan trọng, test đường dẫn sau khi qua proxy và kiểm tra Spring Security thực sự nhìn thấy path/method nào. Không vá lỗi route bằng việc mở một `permitAll("/api/**")` rộng.

## 4. Quy tắc đầu tiên khớp: các cách cấu hình sai

### Sai A: Rule báo cáo rộng trước admin

```java
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:read")
.pathMatchers(HttpMethod.GET, "/api/reports/admin/**")
    .hasRole("ADMIN")
```

User chỉ có `report:read` được áp quyền đọc thông thường cho URL admin. Đổi vị trí để admin trước report.

### Sai B: Public rộng trước private

```java
.pathMatchers("/api/**").permitAll()
.pathMatchers("/api/admin/**").hasRole("ADMIN")
```

Rule thứ hai bị che. Client có thể vào các URL API theo rule public. `permitAll` chỉ nên áp những URL/method thực sự public.

### Sai C: `authenticated()` trước quyền ghi

```java
.pathMatchers("/api/reports/**").authenticated()
.pathMatchers(HttpMethod.DELETE, "/api/reports/*")
    .hasAuthority("report:delete")
```

Một người đăng nhập mà không có quyền delete có thể qua HTTP authorization ở rule đầu. `authenticated` **không phải** `report:delete`.

### Sai D: Method-only GET public ở đầu

```java
.pathMatchers(HttpMethod.GET).permitAll()
.pathMatchers(HttpMethod.GET, "/api/reports/admin/**")
    .hasRole("ADMIN")
```

Mọi GET trong chain có thể qua dưới quyền public, kể cả nhánh admin.

### Sai E: Fallback quá mở

```java
.anyExchange().authenticated()
```

Một controller mới `/api/reports/export` hoặc HTTP method mới có thể được mở cho mọi user đăng nhập mà chưa qua review. Với policy allowlist, prefer:

```java
.anyExchange().denyAll()
```

### Sai F: Catch-all khai trước rule

```java
.anyExchange().denyAll()
.pathMatchers("/api/status").permitAll()
```

Catch-all phải nằm cuối. Tùy phiên bản DSL, khai rule sau catch-all có thể bị chặn ở cấu hình hoặc không đạt ý định; không dựa vào hành vi tình cờ.

## 5. `hasRole` so với `hasAuthority`

```java
.hasRole("ADMIN")
```

mặc định yêu cầu `GrantedAuthority` là **`ROLE_ADMIN`**, không phải `"ADMIN"`.

```java
.hasAuthority("ROLE_ADMIN")
```

yêu cầu đúng chuỗi `ROLE_ADMIN` và thường tương đương `hasRole("ADMIN")` nếu prefix mặc định được giữ.

```java
.hasAuthority("report:read")
```

yêu cầu đúng authority `report:read`, không tự thêm `ROLE_`.

| API | Authority được yêu cầu theo cấu hình mặc định |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ADMIN")` | `ADMIN` |
| `hasAuthority("report:read")` | `report:read` |

Nếu ứng dụng tùy chỉnh role prefix hoặc ánh xạ JWT scopes/roles riêng, phải đối chiếu authority thực tế từ authentication. Không dựa vào tên hiển thị role trên frontend.

## 6. Chọn rule theo HTTP method: GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS

Một resource có thể có:

```text
GET    /api/reports/42 -> report:read
DELETE /api/reports/42 -> report:delete
PUT    /api/reports/42 -> chưa hỗ trợ, deny
```

**DELETE không được kế thừa quyền GET.** Sử dụng method matcher để ràng buộc hành động.

### 6.1. HEAD

HEAD có thể tiết lộ metadata như ETag, content length hoặc sự tồn tại của object. Đừng mặc định một rule GET tự bao gồm HEAD ở tầng security. Nếu API hỗ trợ HEAD, cấu hình và kiểm thử rõ:

```java
// MẢNH BỔ SUNG, phải đặt đúng thứ tự với public/admin.
.pathMatchers(HttpMethod.HEAD, "/api/reports/**")
    .hasAuthority("report:read")
```

Route/handler có thể hỗ trợ HEAD theo quy tắc riêng của WebFlux, nhưng **security matcher vẫn cần kiểm tra method theo contract**.

### 6.2. OPTIONS và CORS

Browser có thể gửi preflight:

```http
OPTIONS /api/reports
Origin: https://client.example
Access-Control-Request-Method: POST
```

Nếu CORS không cấu hình đúng, browser có thể chặn request thật, kể cả user có quyền. Nhưng **CORS không phải cơ chế authentication/authorization** và không bảo vệ client ngoài browser.

Cấu hình CORS theo origin, methods, headers và credentials thật sự cần, xử lý preflight qua cơ chế WebFlux/Spring Security phù hợp. Không “sửa” bằng blanket `permitAll` hoặc wildcard origins kèm credentials.

### 6.3. CSRF và POST/DELETE

Spring Security WebFlux bật CSRF protection theo mặc định. POST, PUT, PATCH, DELETE của ứng dụng cookie/session thường cần token. Vì vậy một người có quyền `report:write` vẫn có thể nhận **403 do thiếu CSRF**, không phải do `hasAuthority` sai.

Trong integration tests, dùng:

```java
client.mutateWith(mockUser("writer")
        .authorities(new SimpleGrantedAuthority("report:write")))
    .mutateWith(csrf())
    .post()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Đây là **mảnh test**, với `client` đã gắn `springSecurity()`; ví dụ hoàn chỉnh bên dưới.

Không tắt CSRF chỉ vì test POST không qua. Với API bearer-token stateless không dùng cookie, threat model khác, nhưng cần quyết định dựa trên cách xác thực và client thực tế.

## 7. Demo hoàn chỉnh: Spring Boot 3.5.8 + Java 17 + WebFlux

Dự án sau tập trung kiểm chứng **HTTP authorization rules**; các handler trả chuỗi demo, không đụng database. Do đó ví dụ chứng minh route/security matcher, **không tự chứng minh object-level authorization trên reportId, owner hoặc tenant**.

### 7.1. Cấu trúc

```text
reactive-path-matcher-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PathMatcherApplication.java
    │   ├── WebSecurityConfig.java
    │   └── ReportController.java
    └── test/java/demo/
        └── PathMatcherSecurityTest.java
```

### 7.2. `settings.gradle`

```groovy
rootProject.name = 'reactive-path-matcher-demo'
```

### 7.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chỉ khai báo WebFlux starter, không trộn `spring-boot-starter-web` (Servlet) vào ví dụ.

### 7.4. Spring Boot application

**`src/main/java/demo/PathMatcherApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathMatcherApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathMatcherApplication.class, args);
    }
}
```

### 7.5. Security config: rule cụ thể trước, rộng sau

**`src/main/java/demo/WebSecurityConfig.java`:**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/status")
                    .permitAll()
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/public/**")
                    .permitAll()
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/admin/**")
                    .hasRole("ADMIN")
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .pathMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("report:write")
                .pathMatchers(
                    HttpMethod.DELETE, "/api/reports/*")
                    .hasAuthority("report:delete")
                .pathMatchers("/api/**")
                    .denyAll()
                .anyExchange()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {

        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader-pass")
            .authorities("report:read")
            .build();

        UserDetails writer = User.withUsername("writer")
            .password("{noop}writer-pass")
            .authorities("report:write")
            .build();

        UserDetails deleter = User.withUsername("deleter")
            .password("{noop}deleter-pass")
            .authorities("report:delete")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            reader, writer, deleter, admin);
    }
}
```

**Giải thích:**

1. GET status và GET public là ngoại lệ công khai có method cụ thể.
2. GET admin đứng **trước** GET reports rộng, chặn reader thường vào admin.
3. GET reports có `report:read`, POST reports có `report:write`, DELETE một report có `report:delete`.
4. `/api/**` và mọi URL khác được deny nếu chưa được cho phép.
5. `httpBasic` cung cấp authentication cho demo; user chỉ có quyền được seed, không tự có thêm quyền khác.
6. Không có `.csrf(...disable...)`; CSRF mặc định vẫn áp dụng.
7. `"{noop}"` và mật khẩu demo **chỉ dùng để học**, không dùng ở production. Production phải dùng password hashing an toàn hoặc OIDC/OAuth2/JWT với identity provider phù hợp.

### 7.6. Controller reactive

**`src/main/java/demo/ReportController.java`:**

```java
package demo;

import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/status")
    public Mono<String> status() {
        return Mono.just("OK");
    }

    @GetMapping("/api/reports/public/{name}")
    public Mono<String> publicReport(
            @PathVariable String name) {
        return Mono.just("PUBLIC:" + name);
    }

    @GetMapping("/api/reports/admin/audit")
    public Mono<String> audit() {
        return Mono.just("AUDIT");
    }

    @GetMapping("/api/reports/{id}")
    public Mono<String> report(
            @PathVariable Long id) {
        return Mono.just("REPORT:" + id);
    }

    @PostMapping("/api/reports")
    public Mono<String> create() {
        return Mono.just("CREATED");
    }

    @DeleteMapping("/api/reports/{id}")
    public Mono<String> delete(
            @PathVariable Long id) {
        return Mono.just("DELETED:" + id);
    }
}
```

Controller trả `Mono<String>` và không thực hiện blocking I/O. `GET /api/reports/admin/audit` có handler cụ thể, nhưng authorization vẫn phụ thuộc vào **thứ tự matcher trong config**; mapping controller không tự sửa quyền.

## 8. Integration test với `WebTestClient`

Spring Security có WebFlux test support `springSecurity()`, `mockUser()` và `csrf()`.

**`src/test/java/demo/PathMatcherSecurityTest.java`:**

```java
package demo;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class PathMatcherSecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient reader() {
        return client.mutateWith(
            mockUser("reader").authorities(
                new SimpleGrantedAuthority("report:read"))
        );
    }

    private WebTestClient writer() {
        return client.mutateWith(
            mockUser("writer").authorities(
                new SimpleGrantedAuthority("report:write"))
        );
    }

    private WebTestClient deleter() {
        return client.mutateWith(
            mockUser("deleter").authorities(
                new SimpleGrantedAuthority("report:delete"))
        );
    }

    private WebTestClient admin() {
        return client.mutateWith(
            mockUser("admin").roles("ADMIN")
        );
    }

    @Test
    void publicGetIsAvailableToAnonymous() {
        client.get().uri("/api/status").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");

        client.get().uri("/api/reports/public/guide").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("PUBLIC:guide");
    }

    @Test
    void reportReadUsesReadAuthority() {
        reader().get().uri("/api/reports/42").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("REPORT:42");

        writer().get().uri("/api/reports/42").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRuleWinsBeforeBroadGetReports() {
        // Có report:read nhưng thiếu ROLE_ADMIN.
        reader().get().uri("/api/reports/admin/audit").exchange()
            .expectStatus().isForbidden();

        // Admin chỉ có ROLE_ADMIN, không có report:read.
        admin().get().uri("/api/reports/admin/audit").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("AUDIT");
    }

    @Test
    void postAndDeleteHaveIndependentAuthorities() {
        writer().mutateWith(csrf())
            .post().uri("/api/reports").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("CREATED");

        reader().mutateWith(csrf())
            .post().uri("/api/reports").exchange()
            .expectStatus().isForbidden();

        deleter().mutateWith(csrf())
            .delete().uri("/api/reports/42").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("DELETED:42");

        reader().mutateWith(csrf())
            .delete().uri("/api/reports/42").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void csrfRemainsEnabled() {
        writer().post().uri("/api/reports").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownMethodAndPathsFailClosed() {
        reader().mutateWith(csrf())
            .put().uri("/api/reports/42").exchange()
            .expectStatus().isForbidden();

        reader().get().uri("/api/unlisted").exchange()
            .expectStatus().isForbidden();

        reader().get().uri("/outside-api").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousCannotReadProtectedReport() {
        client.get().uri("/api/reports/42").exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Vì sao test này đáng tin hơn chỉ test controller?**

- `@SpringBootTest` tải cấu hình bảo mật và handler thật.
- `bindToApplicationContext(...).apply(springSecurity())` đưa reactive WebFilter security vào WebTestClient.
- `mockUser` chỉ cung cấp authorities đã chỉ định; không tự cấp `report:read` cho writer.
- Test admin-without-read **chứng minh rule admin được xét trước GET reports rộng**.
- Test reader-on-admin **bắt được lỗi đảo thứ tự**, thay vì chỉ kiểm tra admin vào được.
- `csrf()` tách lỗi thiếu CSRF khỏi lỗi thiếu authority trong các test POST/DELETE.
- Deny tests có authenticated user để kiểm chứng HTTP 403 theo cấu hình; anonymous protected GET kiểm chứng entry point 401.

Đây là integration tests của **HTTP authorization**, không thay kiểm thử service/DB ownership. Ví dụ handler chỉ trả text, không ghi/xóa dữ liệu thật.

### 8.1. Chạy chương trình và test

Trong thư mục có `build.gradle`, nếu đã có Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Nếu chưa có wrapper, cần dùng Gradle tương thích để tạo wrapper hoặc chạy `gradle test`/`gradle bootRun` khi đã cài.

Sau khi server chạy, thử:

```bash
curl -i http://localhost:8080/api/status
curl -i http://localhost:8080/api/reports/public/guide
curl -i -u reader:reader-pass http://localhost:8080/api/reports/42
curl -i -u admin:admin-pass http://localhost:8080/api/reports/admin/audit
```

Đây là HTTP Basic demo; **không** dùng `{noop}`/plain password trong production. Với POST/DELETE, một `curl -u` chỉ kèm Basic credentials có thể bị 403 do thiếu CSRF token: hãy dùng test WebTestClient ở trên hoặc tích hợp cơ chế CSRF thực tế của frontend.

### 8.2. Ma trận kỳ vọng

| User | Request | HTTP dự kiến |
| --- | --- | ---: |
| Anonymous | `GET /api/status` | `200` |
| Anonymous | `GET /api/reports/public/guide` | `200` |
| Reader | `GET /api/reports/42` | `200` |
| Writer | `GET /api/reports/42` | `403` |
| Reader | `GET /api/reports/admin/audit` | `403` |
| Admin | `GET /api/reports/admin/audit` | `200` |
| Writer + CSRF | `POST /api/reports` | `200` |
| Reader + CSRF | `POST /api/reports` | `403` |
| Deleter + CSRF | `DELETE /api/reports/42` | `200` |
| Reader + CSRF | `DELETE /api/reports/42` | `403` |
| Writer, thiếu CSRF | `POST /api/reports` | `403` |
| Reader + CSRF | `PUT /api/reports/42` | `403` |
| Reader | `GET /api/unlisted` | `403` |
| Reader | `GET /outside-api` | `403` |
| Anonymous | `GET /api/reports/42` | `401` theo HTTP Basic demo |

Những status trên là **kết quả dự kiến theo mã nguồn**, không phải tuyên bố đã chạy test trong môi trường này. Với authentication entry point khác (Bearer, form login, session), 401/403/redirect có thể khác; chính sách ALLOW/DENY phải được kiểm tra theo contract sản phẩm.

## 9. Nhiều `SecurityWebFilterChain`: `@Order` và `securityMatcher`

Một ứng dụng có thể có chain riêng cho API và chain fallback. **Không chèn cấu hình sau đồng thời với bean securityWebFilterChain trong demo ở mục 7**: đây là phương án thay thế để giải thích chọn chain.

```java
// MẢNH CẤU HÌNH TƯ DUY: imports và userDetailsService
// cần được thêm nếu tách thành project độc lập.
@Configuration
@EnableWebFluxSecurity
class MultipleChains {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/**"))
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/status")
                    .permitAll()
                .pathMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .anyExchange()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

- Với `GET /api/status`, chain `@Order(1)` match `/api/**`, rule status cho public.
- Với `GET /api/admin/audit`, cũng vào chain API, rule admin yêu cầu `ROLE_ADMIN`.
- Với `GET /outside-api`, chain API không match, fallback chain từ chối.
- `anyExchange()` bên trong chain API **không** có nghĩa là mọi request toàn hệ thống: chain chỉ được chọn nếu khớp `securityMatcher("/api/**")`.

**Bẫy:** nếu một chain catch-all có `@Order(1)` và chain `/api/**` có `@Order(2)`, catch-all có thể được chọn trước cho tất cả request. Các rule chặt chẽ của chain API sẽ không được dùng. Sắp chain có matcher hẹp trước, fallback rộng sau.

Cũng cần kiểm tra **coverage**: nếu không có chain nào match một URL, request đó có thể không đi qua các Spring Security WebFilters như bạn kỳ vọng. Một fallback chain rõ ràng giúp tránh khoảng trống khi thêm URL mới.

Cấu hình nhiều chain ở trên intentionally không cho phép report endpoints vì chỉ minh họa thứ tự chain. Khi dùng với sản phẩm, thêm các rule report thực vào chain API theo policy đã thiết kế và vẫn kết thúc bằng deny all.

## 10. Path variables, `ReactiveAuthorizationManager` và quyền trên dữ liệu

Matcher URL không tự kiểm tra ownership. Ví dụ:

```java
.pathMatchers(HttpMethod.GET, "/api/reports/{id}")
    .hasAuthority("report:read")
```

Rule này yêu cầu `report:read` nhưng **không** xác minh báo cáo `{id}` thuộc tenant của caller hoặc người ấy có ACE READ. Đối với API dữ liệu thực, cần thêm policy ở service/repository hoặc custom `ReactiveAuthorizationManager<AuthorizationContext>`.

Ví dụ **mảnh cấu hình** so tên user trong path với identity đã xác thực:

```java
.pathMatchers(
    HttpMethod.GET, "/api/users/{name}/profile"
)
.access((authentication, context) ->
    authentication
        .map(auth -> new AuthorizationDecision(
            auth.getName().equals(
                context.getVariables().get("name"))
        ))
        .defaultIfEmpty(new AuthorizationDecision(false))
)
```

`AuthorizationContext.getVariables()` cung cấp URI template variables. Đoạn này chỉ minh họa ràng buộc name; production cần xử lý anonymous và stable user identity, không dùng username chỉ có tính duy nhất theo tenant hoặc do client tự khai.

Khi quyền phụ thuộc database, tránh blocking JDBC trong reactive WebFilter event loop. Ưu tiên reactive data access/policy service non-blocking hoặc thích nghi có kiểm soát. Với update nhạy cảm, phải kiểm tra lại quyền và trạng thái trong transaction/conditional SQL gần thời điểm mutation, tránh **TOCTOU**.

`@EnableWebFluxSecurity` chỉ bật web security; nếu muốn `@PreAuthorize` ở **reactive service**, hãy xem `@EnableReactiveMethodSecurity` cùng contract của reactive return type. Không lấy HTTP path authorization thay cho quyền trên object.

## 11. CORS, CSRF, proxy rewrite và cách kiểm tra regression

Một API triển khai sau gateway có thể nhận `/api/reports/42` dù URL bên ngoài là `/service/api/reports/42`; matcher sẽ xét request/path mà backend Spring WebFlux thực sự thấy. Test qua proxy trong môi trường tích hợp để tránh giả định sai về base path, encoded slashes, double slash, semicolon và trailing slash.

CORS kiểm soát browser cross-origin behavior; nó không cấp authority `report:read`. CSRF bảo vệ state-changing request trong threat model cookie/session. Hai cơ chế này tương tác với web security nhưng **không thay thế** role/object authorization.

Checklist tối thiểu mỗi khi đổi routes, rule hoặc version framework:

1. Test anonymous và authenticated cho **mọi ngoại lệ public**.
2. Test user chỉ có `report:read` **không** vào admin path.
3. Test admin không có read vẫn vào admin path đúng theo yêu cầu nghiệp vụ.
4. Test GET/POST/DELETE cùng nhánh URL có **permissions khác nhau**.
5. Test PUT/PATCH/HEAD/OPTIONS không được mở ngoài ý định; bổ sung CORS/HEAD rules có chủ đích khi cần.
6. Test route mới không lọt qua fallback `authenticated` hoặc `permitAll`.
7. Với nhiều chains, test `@Order`, `securityMatcher` và fallback bao phủ các URL còn lại.
8. Test CSRF bằng request có token để kiểm tra authorization riêng, và request thiếu token để kiểm tra exploit protection.
9. Test path sau reverse proxy rewrite và những biến thể URL mà ứng dụng hỗ trợ.
10. Test quyền trên object/tenant/ACL ở service, không chỉ HTTP status.

### Lỗi phổ biến

| Vấn đề | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Reader mở được URL admin | Rule GET rộng đứng trước admin | Admin rule trước rule reports |
| DELETE dùng quyền READ | `pathMatchers("/api/reports/**").authenticated()` đứng trước | Method-specific authority rules |
| Bất kỳ GET nào cũng public | `.pathMatchers(HttpMethod.GET).permitAll()` | Chỉ public path/method cụ thể |
| Endpoint mới tự được mở | `.anyExchange().authenticated()` hoặc `.permitAll()` | Default deny, explicit allowlist |
| Admin bị 403 dù có `ADMIN` | `hasRole` tìm `ROLE_ADMIN` mặc định | Map authorities đúng |
| POST bị 403 dù đủ write | Thiếu CSRF token | Test token, đánh giá CSRF policy |
| API chain không được chọn | Chain catch-all có `@Order` cao hơn | Hẹp trước, rộng sau |
| Route ngoài chain không bảo vệ | Thiếu fallback `SecurityWebFilterChain` | Fallback chain deny |
| Test controller pass nhưng security sai | Test không gắn WebFilter chain | `.apply(springSecurity())` |
| User có read xem tài liệu tenant khác | HTTP rule không xét object ID | Tenant-scoped service/repository |
| Chậm khi policy truy vấn DB | Blocking IO trong reactive filter | Reactive access, giới hạn timeout |
| Kết quả khác sau gateway | Normalization/rewrite path | Integration test URL thực |

## 12. Câu hỏi tự đánh giá

**1.** Hai rule dưới đây có cộng dồn không?

```java
.pathMatchers("/api/**").authenticated()
.pathMatchers("/api/admin/**").hasRole("ADMIN")
```

**Trả lời:** Không. `/api/**` khớp trước; quyền admin phía sau bị che. Chuyển rule admin lên trước.

**2.** `pathMatchers(HttpMethod.GET, "/api/reports/**")` có khớp `DELETE /api/reports/42` không?

**Trả lời:** Không. Method phải là GET.

**3.** `.pathMatchers("/api/reports/**").hasAuthority("report:read")` có đủ bảo vệ DELETE không?

**Trả lời:** Không nếu nghiệp vụ yêu cầu `report:delete`; path-only matcher không phân biệt method.

**4.** Khi một user có `ROLE_ADMIN`, `.hasRole("ADMIN")` có thỏa không?

**Trả lời:** Có khi dùng role prefix mặc định; `.hasAuthority("ADMIN")` khác.

**5.** Tại sao `GET /api/reports/admin/audit` cần test với reader không có admin role?

**Trả lời:** Để phát hiện lỗi GET reports rộng che rule admin.

**6.** `anyExchange().denyAll()` cần đặt ở đâu?

**Trả lời:** Cuối danh sách rule của chain, sau các allowlist.

**7.** Với hai `SecurityWebFilterChain`, rule nào chạy đầu?

**Trả lời:** Phải chọn chain theo `@Order` và `securityMatcher` trước, sau đó mới xét các rule bên trong chain đã chọn.

**8.** Một request POST có authority hợp lệ nhưng thiếu CSRF token nhận 403 có đồng nghĩa matcher sai?

**Trả lời:** Không; CSRF có thể chặn. Test với `csrf()` để xét authority riêng.

**9.** API `GET /api/reports/42` có authority READ đã đủ an toàn dữ liệu chưa?

**Trả lời:** Chưa. Cần kiểm tra report ID, tenant, owner/ACL và resource policy thật.

**10.** Khi user có nhiều tenant, có thể lấy tenant từ query parameter đưa thẳng vào policy không?

**Trả lời:** Không. Tenant phải được xác minh qua membership/identity server và resource authoritative.

## 13. Tài liệu chính thức

- [Spring Security 6.5 – Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): cú pháp `authorizeExchange`, `pathMatchers` và thứ tự rule.
- [Spring Security 6.5 – WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): `SecurityWebFilterChain`, `@EnableWebFluxSecurity`, nhiều chains và `@Order`.
- [Spring Security API – AbstractServerWebExchangeMatcherRegistry](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/AbstractServerWebExchangeMatcherRegistry.html): overload `pathMatchers` và `anyExchange`.
- [Spring Security API – ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): `ServerHttpSecurity` reactive DSL.
- [Spring Security 6.5 – WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `.apply(springSecurity())` cho WebFlux tests.
- [Spring Security 6.5 – Testing WebFlux Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`, `@WithMockUser`.
- [Spring Security 6.5 – Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `mutateWith(csrf())`.
- [Spring Security 6.5 – CSRF for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html): bảo vệ POST/PUT/DELETE theo threat model.
- [Spring Framework – WebFlux Request Mapping](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): phân biệt route mapping và security matching.

**Kết luận:** WebFlux `pathMatchers` kiểm tra path và tùy chọn HTTP method; các matcher được xét **theo thứ tự khai báo**, rule đầu tiên khớp được dùng. Đặt nhánh đặc biệt trước nhánh rộng, tách quyền READ/WRITE/DELETE, giữ `anyExchange().denyAll()` cuối cùng, kiểm tra thêm thứ tự nhiều `SecurityWebFilterChain` bằng `@Order` và luôn thử các ca reader/admin overlap bằng `WebTestClient`. HTTP-level authorization không thay quyền trên object/tenant; các thao tác dữ liệu vẫn cần policy ở service và DB.