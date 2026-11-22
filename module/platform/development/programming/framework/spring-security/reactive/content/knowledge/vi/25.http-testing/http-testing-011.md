# Kiểm chứng nhiều SecurityWebFilterChain và chuỗi dự phòng

*Spring Security - reactive · Nhóm Kiểm thử HTTP · Java 17+ · Spring Boot 3.5.16 / Spring Security 6.x.*

## 1. Mục tiêu và bài toán

Một ứng dụng Spring WebFlux có thể có API dành cho quản trị viên, API dành cho người dùng, endpoint công khai và nhiều cơ chế xác thực. Thay vì chỉ có một `SecurityWebFilterChain`, ứng dụng có thể khai báo nhiều chain với `securityMatcher` và thứ tự ưu tiên `@Order`.

**Cơ chế quyết định:** Spring Security xét các `SecurityWebFilterChain` theo ưu tiên, **chọn chain đầu tiên có matcher phù hợp**, rồi áp dụng authentication và authorization bên trong chain đó. Nếu chain đã được chọn trả 401 hoặc 403, Spring Security **không** thử tiếp chain khác để tìm quy tắc dễ dãi hơn.

Nhiệm vụ kiểm thử quan trọng hơn việc nhìn tên bean: phải chứng minh **request được chọn vào chain nào**, đồng thời chứng minh endpoint được cho phép hoặc bị chặn đúng.

Sau bài học, bạn có thể:

1. Hiểu `SecurityWebFilterChain`, `WebFilterChainProxy`, `ServerWebExchangeMatcher`, `@Order`, `securityMatcher` và `authorizeExchange`.
2. Phân biệt `securityMatcher` chọn cả chain với `pathMatchers` chọn rule **sau** khi đã chọn chain.
3. Cấu hình ba chains có overlap: admin `/api/admin/**` ưu tiên cao, API `/api/**` ưu tiên sau, fallback không có matcher riêng.
4. Dùng `anyExchange().denyAll()` cho fallback fail-closed.
5. Kiểm thử chain selection bằng một lab-only response header để không nhầm 403 do authorization với 404 do thiếu handler.
6. Viết Java 17+ Spring Boot WebFlux project và WebTestClient integration tests với Basic authentication thật.
7. Kiểm tra status 200/401/403, path overlap, prefix gần giống, HEAD/POST, header giả X-User/X-Role, fallback bao phủ handler có thật.
8. Phân biệt role/authorization denial với CSRF, CORS, redirect và framework short-circuit.
9. Biết nguy cơ khi không có catch-all chain hoặc dùng fallback `permitAll`.
10. Vận dụng cách kiểm thử này khi thay Basic bằng OAuth2 Resource Server JWT, form login hoặc client certificates.

**Quy tắc:** mỗi request vào **một chain đầu tiên match**, không có “rơi tiếp” xuống fallback sau khi đã bị từ chối. Fallback phải được xem như một phần chính sách bảo mật, không là lựa chọn chữa lỗi vội vàng.

## 2. Kiến trúc nhiều chains

```text
GET /api/admin/report + HTTP Basic alice
                     |
                     v
          Spring Security WebFilterChainProxy
                     |
               @Order(1)
          matcher /api/admin/** ?
                     |
                    YES
                     |
                     v
             adminChain
          anyExchange.hasRole("ADMIN")
                     |
          alice chỉ ROLE_USER
                     |
                     v
                403 Forbidden
                     |
        KHÔNG kiểm tra apiChain/fallbackChain
```

Một request khác:

```text
GET /public/ping
        |
        v
@Order(1) adminChain:   /api/admin/** -> NO
        |
        v
@Order(2) apiChain:     /api/**       -> NO
        |
        v
@Order(3) fallbackChain: match all   -> YES
        |
        v
GET /public/ping permitAll -> HTTP 200
```

`@Order(1)` có ưu tiên cao hơn `@Order(2)`. `/api/admin/report` đồng thời khớp `/api/admin/**` và `/api/**`, nên **adminChain phải đứng trước apiChain**.

### 2.1. `securityMatcher` là điều kiện chọn chain

Ví dụ:

```java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"));
```

Đây là một `ServerWebExchangeMatcher` cho **toàn chain**. Nếu nó không match, Spring Security chuyển sang xét chain có priority tiếp theo.

### 2.2. `pathMatchers` là điều kiện phân quyền bên trong chain

Ví dụ:

```java
http.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
        .anyExchange().denyAll());
```

Các rules chỉ được xét **trong chain đã chọn**. `anyExchange` ở đây có nghĩa request còn lại **của chain này**, không có nghĩa toàn bộ ứng dụng. Nếu adminChain trả 403, request không chạy tiếp vào apiChain để xin quyền khác.

### 2.3. `@Order` khác `SecurityWebFiltersOrder`

- `@Order` trên `@Bean SecurityWebFilterChain` quyết định **xét chain nào trước**.
- `SecurityWebFiltersOrder` dùng trong `ServerHttpSecurity.addFilterAt/Before/After` quyết định **vị trí một WebFilter bên trong chain**.
- Không thể đổi một cái lấy cái còn lại.

### 2.4. Chuỗi dự phòng (fallback)

Fallback không gọi `.securityMatcher(...)`; matcher mặc định của `ServerHttpSecurity` khớp mọi request. Đặt nó **cuối**.

```java
@Bean
@Order(3)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers(HttpMethod.GET,
                            "/public/ping").permitAll()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Snippet trên chưa có imports/config hoàn chỉnh; file chạy đầy đủ ở mục 7. Fallback này chỉ công khai GET `/public/ping`, **không** cho phép mọi authenticated user truy cập endpoint chưa được kiểm kê.

Nếu **không có chain nào match** một request, Spring Security WebFilterChain không bảo vệ request đó (trừ những biện pháp khác ngoài chain). Vì vậy thiếu fallback hoặc matcher quá hẹp có thể để lộ handler. Một 404 vì không có handler **không phải bằng chứng** rằng endpoint có authorization.

## 3. Thiết kế minh họa: admin, api và fallback

### 3.1. `adminChain`, @Order(1)

- Matcher `/api/admin/**`.
- HTTP Basic xác minh Alice/Admin với user store BCrypt.
- Mọi request vào chain cần `hasRole("ADMIN")`.
- Header quan sát `X-Lab-Security-Chain: admin`.
- GET `/api/admin/report` có handler thật.
- GET `/api/admin/public` cũng có handler thật, **tên chứa public nhưng không tự public**.

### 3.2. `apiChain`, @Order(2)

- Matcher `/api/**`, chứa cả `/api/admin/**` nhưng priority thấp hơn admin.
- GET `/api/public`: permitAll.
- GET `/api/me`: authenticated.
- `anyExchange().denyAll()`: tất cả methods/routes khác.
- Header quan sát `X-Lab-Security-Chain: api`.
- GET `/api/hidden` có handler thật nhưng bị denyAll.
- GET `/api/adminX/data` có handler thật; segment `adminX` **không** match `/api/admin/**`, nên đi vào API chain và bị denyAll.

### 3.3. `fallbackChain`, @Order(3)

- Không khai báo securityMatcher; match mọi request chưa vào hai chain trên.
- GET `/public/ping`: permitAll.
- `anyExchange().denyAll()`: route khác bị từ chối kể cả admin.
- Header quan sát `X-Lab-Security-Chain: fallback`.
- GET `/hidden` có handler thật nhưng bị denyAll.

### 3.4. Ma trận cần kiểm chứng

| Method / path | Chain | Principal | Expected |
| --- | --- | --- | --- |
| GET /public/ping | fallback | anonymous | 200 |
| GET /api/public | api | anonymous | 200 |
| GET /api/me | api | anonymous | 401 |
| GET /api/me | api | alice | 200, principal alice |
| GET /api/me | api | sai Basic password | 401 |
| GET /api/admin/report | admin | anonymous | 401 |
| GET /api/admin/report | admin | alice | 403 |
| GET /api/admin/report | admin | admin | 200 |
| GET /api/admin/public | admin | anonymous | 401 |
| GET /api/hidden | api | alice | 403 |
| GET /api/adminX/data | api | alice | 403 |
| GET /hidden | fallback | alice | 403 |
| GET /hidden | fallback | admin | 403 |
| GET /missing | fallback | admin | 403 |
| GET /hidden | fallback | anonymous | 401 |
| HEAD /api/public | api | alice | 403 |
| POST /api/public | api | alice | 403 |
| GET /api/admin/report + X-Role ADMIN | admin | alice | 403 |

Status chỉ là một phần. Test phải assert thêm **chain marker** tương ứng, nếu không một 403 có thể đến từ chain hoàn toàn khác hoặc từ CSRF/handler/edge.

## 4. Vì sao cần dấu nhận diện chain trong tests?

Một test thấy `/api/admin/report` trả 403 chưa chứng minh `adminChain` đã được chọn. Có thể:
- API chain rộng nhận request và denyAll.
- Fallback chain được áp dụng.
- Request bị CSRF/CORS/filter khác từ chối sớm.
- Không có controller nên 404.

Ta đặt một `WebFilter` lab-only **bên trong từng chain** và đặt response header `X-Lab-Security-Chain` bằng `response.beforeCommit`. Giá trị là `admin`, `api`, hoặc `fallback`. Filter **không** xác thực, phân quyền, đọc raw credentials hay sửa `SecurityContext`.

Marker được thêm ở `SecurityWebFiltersOrder.FIRST` trong chain. Khi một GET request hợp lệ đi vào chain rồi bị Basic hoặc authorizeExchange chặn, callback beforeCommit vẫn có cơ hội thêm dấu. Nếu request bị HTTP parser, gateway hoặc firewall từ chối **trước chain**, marker có thể vắng mặt; đó là tình huống cần điều tra riêng, không suy đoán chain selection.

**Chỉ dùng marker trong demo/test.** Production không nên tiết lộ tên chain, role policies, token payloads hoặc nội bộ security infrastructure trong response headers.

## 5. Các bẫy về thứ tự và phạm vi

### 5.1. Chain rộng đặt trước chain hẹp

Antipattern:

```java
// SAI VỀ THỨ TỰ: /api/** có thể che /api/admin/**.
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher(
                            "/api/**"))
            .authorizeExchange(ex -> ex
                    .anyExchange().authenticated())
            .build();
}
```

Nếu API chain chỉ yêu cầu authenticated và được xét trước, Alice có thể đến controller admin dù không có ROLE_ADMIN. **Không có fallback sang adminChain để “sửa” quyền**. Test overlap với marker admin và Alice -> 403 là hàng rào phát hiện bug.

### 5.2. Quên fallback

Antipattern:

```java
@Bean
SecurityWebFilterChain onlyApi(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher(
                            "/api/**"))
            .authorizeExchange(ex -> ex
                    .anyExchange().authenticated())
            .build();
}
```

Nếu chỉ có chain này, request `/hidden` không được Spring Security web chain bảo vệ. Nếu `/hidden` có controller trả dữ liệu, có nguy cơ 200. Không mặc định rằng Spring Boot tạo thêm một chain catch-all khi đã có custom chain beans.

Cách kiểm tra đúng: có một handler `/hidden` **thực sự tồn tại**, gửi Basic valid và mong **403 với marker fallback**. Không chỉ test một URL không có controller rồi nhận 404.

### 5.3. Fallback authenticated vs denyAll

- `.anyExchange().authenticated()` ở fallback cho phép **mọi user đã login** gọi các endpoint chưa được liệt kê.
- `.anyExchange().permitAll()` mở toàn bộ fallback công khai.
- `.anyExchange().denyAll()` chặn mặc định; các URL public riêng dùng `pathMatchers(...).permitAll()` đặt trước.
- Không đổi sang permitAll chỉ để cho một test bị 401/403 “pass”.

### 5.4. Method-specific allowlist

```java
.pathMatchers(HttpMethod.GET, "/api/public").permitAll()
```

không tự mở HEAD hay POST. Framework controller có thể tự xử lý HEAD cho một @GetMapping, nhưng **authorization matcher vẫn phân biệt HTTP method**. Với POST, CSRF filter cũng có thể chặn trước rule denyAll, nên chỉ nhìn status 403 không thể biết rule nào từ chối.

### 5.5. Prefix và normalized paths

`/api/admin/report` thuộc admin. `/api/adminX/data` thuộc api, không phải admin. `/api`, `/api/`, trailing slash, encoded slash/dot, case sensitivity và forwarded prefix cần test theo deployment thực; đừng tự viết `startsWith("/api/admin")` nếu cần path segment boundary.

Các request chứa `%2e`, `%2f`, `//` hoặc ký tự bất thường có thể bị WebFlux/proxy/firewall trả 400/404 **trước security chain**. Không ép mọi input bị từ chối phải có 401/403; điều cần bảo đảm là **không có bypass thành HTTP 200 ngoài chính sách**.

## 6. Phân biệt 401/403/404/302 trong nhiều chains

| Status | Ý nghĩa thường gặp | Có chứng minh chain đúng? |
| --- | --- | --- |
| 200 | Request được xử lý | Không, phải kiểm tra marker/identity |
| 401 | Thiếu/không hợp lệ Authentication | Không, có thể do một chain khác hoặc upstream |
| 403 | Authenticated nhưng không đủ quyền, hoặc CSRF/security denial | Không, cần marker và nguyên nhân |
| 404 | Không có handler/resource | **Không**, có thể xảy ra khi thiếu chain |
| 302 | Redirect, ví dụ formLogin | Không; cần kiểm tra cơ chế auth và chain |
| 400 | Malformed request | Có thể do parser/firewall trước security chain |

Trong demo, mọi chain đều bật HTTP Basic, tắt formLogin nên các protected GET không redirect HTML. Cơ chế 401 (Basic challenge) và 403 (AccessDenied) khác nhau. Đừng bỏ Basic credentials vào một test rồi dùng 403 của CSRF để kết luận role rule đã chạy.

## 7. Dự án Java 17+ / Spring Boot WebFlux

Cấu trúc:

```text
multi-chain-webflux/
├── settings.gradle
├── build.gradle
├── src/main/java/example/chains/ChainsApplication.java
├── src/main/java/example/chains/SecurityConfig.java
├── src/main/java/example/chains/ChainMarkerFilter.java
├── src/main/java/example/chains/ApiController.java
└── src/test/java/example/chains/MultipleChainsIntegrationTest.java
```

Dùng **Spring Boot 3.5.16**, Java 17+, Gradle 8.4+ tương thích. `spring-boot-starter-webflux` là Reactive stack; không thêm `spring-boot-starter-web` Servlet MVC. Project không cần database, IdP hoặc API ngoài. User store in-memory phục vụ kiểm thử Basic authentication.

### 7.1. settings.gradle

```groovy
rootProject.name = 'multi-chain-webflux'
```

### 7.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
```

Dependency `spring-boot-starter-test` mang JUnit 5, WebTestClient hỗ trợ tests thực. Không cần `spring-security-test` nếu đang gửi HTTP Basic credentials thực qua server; có thể dùng `mockUser`/`mockJwt` ở suite controller hoặc authorization khác nhưng mock credentials không chứng minh password/JWT decoder thật đã chạy.

### 7.3. ChainsApplication.java

```java
package example.chains;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ChainsApplication.class, args);
    }
}
```

### 7.4. ChainMarkerFilter.java

```java
package example.chains;

import java.util.Objects;

import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class ChainMarkerFilter implements WebFilter {

    public static final String HEADER = "X-Lab-Security-Chain";

    private final String chainName;

    public ChainMarkerFilter(String chainName) {
        this.chainName = Objects.requireNonNull(chainName);
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders().set(
                    HEADER, chainName);
            return Mono.empty();
        });

        return chain.filter(exchange);
    }
}
```

`ChainMarkerFilter` **không** có @Component/@Bean để tránh bị WebFlux đăng ký thành global WebFilter và chạy ngoài các security chains. Từng chain tạo instance riêng. `beforeCommit` giúp response header được gắn trước HTTP response commit; `doFinally` thường quá muộn để set headers. Không đọc Authorization/X-User; không tạo Authentication.

### 7.5. SecurityConfig.java

```java
package example.chains;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userStore(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/admin/**"))
                .authorizeExchange(ex -> ex
                        .anyExchange().hasRole("ADMIN"))
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .addFilterAt(
                        new ChainMarkerFilter("admin"),
                        SecurityWebFiltersOrder.FIRST)
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/**"))
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/api/public").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/me").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .addFilterAt(
                        new ChainMarkerFilter("api"),
                        SecurityWebFiltersOrder.FIRST)
                .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                // Không có securityMatcher:
                // matcher mặc định bắt request còn lại.
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .addFilterAt(
                        new ChainMarkerFilter("fallback"),
                        SecurityWebFiltersOrder.FIRST)
                .build();
    }
}
```

**Rà soát bảo mật của cấu hình:**

1. `adminChain` có @Order(1) và matcher riêng, phải thắng `/api/**`.
2. `apiChain` có @Order(2), chỉ cho phép đúng GET `/api/public` và GET `/api/me`, còn lại denyAll.
3. `fallbackChain` có @Order(3) và **không có securityMatcher riêng**.
4. Fallback chỉ cho GET `/public/ping`, chặn `/hidden` dù user có ROLE_ADMIN.
5. HTTP Basic được Spring Security xác minh qua MapReactiveUserDetailsService + BCrypt; không tự đọc X-Role.
6. `formLogin` disable có chủ đích; Basic GET không redirect về trang login.
7. Không tắt CSRF/global headers để “làm cho test chạy”. Project chỉ có GET controllers; các POST vẫn phải bị từ chối.
8. Marker nằm ở `SecurityWebFiltersOrder.FIRST`, **không phải một global WebFilter**.
9. Không tự tái sử dụng một `ServerHttpSecurity` mutable instance giữa các beans; tham số được Spring inject cho từng chain.
10. Authorization rules được đánh giá trong chain đã chọn, không có fallback sau một quyết định deny.

### 7.6. ApiController.java

```java
package example.chains;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> publicPing() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/public")
    public Mono<Map<String, String>> apiPublic() {
        return Mono.just(Map.of("kind", "api-public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p ->
                Map.of("principal", p.getName()));
    }

    @GetMapping({
        "/api/admin/report",
        "/api/admin/public"
    })
    public Mono<Map<String, String>> adminReport() {
        return Mono.just(Map.of("result", "admin-ok"));
    }

    @GetMapping("/api/hidden")
    public Mono<Map<String, String>> hiddenApi() {
        return Mono.just(Map.of("secret", "api-secret"));
    }

    @GetMapping("/api/adminX/data")
    public Mono<Map<String, String>> closePrefix() {
        return Mono.just(Map.of("secret", "prefix-secret"));
    }

    @GetMapping("/hidden")
    public Mono<Map<String, String>> hiddenFallback() {
        return Mono.just(Map.of("secret", "fallback-secret"));
    }
}
```

**Vì sao có hidden handlers?** `/api/hidden` và `/hidden` có handler thật nhưng **không nằm trong danh sách allow**. Test thấy chúng bị 403 giúp chứng minh security rule, không phải 404 do không tìm thấy controller.

`/api/admin/public` có chữ public trong tên nhưng nằm dưới admin matcher, không tự được mở. `/api/adminX/data` có prefix gần giống nhưng không phải segment `/api/admin/`, phải vào apiChain.

Controller `me` lấy `Mono<Principal>` đã được Spring Security xác thực, không đọc X-User tự khai. Không `.block()` trong WebFlux handler.

## 8. Chạy curl để đối chiếu

Khởi động:

```bash
gradle bootRun
```

User fixtures (chỉ dùng local):

```text
alice / alice-pass -> ROLE_USER
admin / admin-pass -> ROLE_USER + ROLE_ADMIN
```

### 8.1. Fallback public

```bash
curl -i http://localhost:8080/public/ping
```

Kỳ vọng:

```http
HTTP/1.1 200 OK
X-Lab-Security-Chain: fallback
Content-Type: application/json

{"status":"ok"}
```

### 8.2. API public

```bash
curl -i http://localhost:8080/api/public
```

Kỳ vọng 200, `X-Lab-Security-Chain: api`, JSON kind=api-public.

### 8.3. Private API

```bash
curl -i http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/me
```

Request anonymous: 401, marker api. Request Alice: 200, marker api, JSON principal=alice.

### 8.4. Admin overlap

```bash
curl -i -u alice:alice-pass \
  http://localhost:8080/api/admin/report

curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/report
```

Alice: 403, marker **admin**; admin: 200, marker **admin**, body result=admin-ok. Đây là minh chứng chain ưu tiên cao không bị chain API rộng che.

### 8.5. Fallback denyAll với handler thật

```bash
curl -i -u admin:admin-pass http://localhost:8080/hidden
```

Kỳ vọng **403, marker fallback**, dù admin có ROLE_ADMIN. Chỉ GET `/public/ping` được mở bởi fallback.

### 8.6. Giả mạo header không tăng quyền

```bash
curl -i -u alice:alice-pass \
  -H "X-User: admin" -H "X-Role: ADMIN" \
  http://localhost:8080/api/admin/report
```

Vẫn nhận 403, marker admin, vì user thực là Alice.

### 8.7. POST vào GET-only public

```bash
curl -i -u alice:alice-pass -X POST \
  http://localhost:8080/api/public
```

Kỳ vọng 403. Lỗi có thể đến từ CSRF trước authorization, hoặc denyAll; muốn xác định nguyên nhân cần test riêng CSRF token/matcher thay vì suy từ status.

**Cảnh báo:** Basic credentials trong HTTP chỉ được Base64-encode, không tự mã hóa transport. Demo giới hạn localhost; production bắt buộc HTTPS/TLS, secret management, rate limiting và không log raw Authorization/Cookie. Bash dùng dấu backslash nối dòng; trên Windows dùng curl.exe hoặc điều chỉnh shell syntax.

## 9. Kiểm thử tích hợp WebTestClient

`@SpringBootTest(webEnvironment=RANDOM_PORT)` mở ứng dụng WebFlux với Spring Security thật. `@AutoConfigureWebTestClient` inject một WebTestClient. Test sử dụng Basic credentials thật, giúp kiểm tra PasswordEncoder, SecurityWebFilterChain, `securityMatcher`, `authorizeExchange`, 401/403 và header marker.

Nếu chỉ unit-test method controller hoặc dùng `mockUser()` cho mọi test, bạn có thể bỏ qua authentication pipeline và không thấy lỗi chain-order thực sự. Mock user vẫn hữu ích cho unit tests về authorization riêng, nhưng bài này cần **integration-level request**.

### 9.1. MultipleChainsIntegrationTest.java

Đường dẫn: `src/test/java/example/chains/MultipleChainsIntegrationTest.java`

```java
package example.chains;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MultipleChainsIntegrationTest {

    @Autowired
    WebTestClient client;

    private static final String CHAIN_HEADER =
            ChainMarkerFilter.HEADER;

    @Test
    void fallbackPublicWorksAndIsSelected() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback")
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void apiPublicUsesApiChain() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(CHAIN_HEADER, "api")
                .expectBody()
                .jsonPath("$.kind").isEqualTo("api-public");
    }

    @Test
    void apiPrivateAnonymousGets401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "api")
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void apiPrivateAliceGets200() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(CHAIN_HEADER, "api")
                .expectBody()
                .jsonPath("$.principal").isEqualTo("alice");
    }

    @Test
    void apiInvalidBasicPasswordGets401() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void adminAnonymousGets401InAdminChain() {
        client.get().uri("/api/admin/report")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }

    @Test
    void adminRouteDeniesAliceWith403() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }

    @Test
    void adminRouteAllowsAdminWith200() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin")
                .expectBody()
                .jsonPath("$.result").isEqualTo("admin-ok");
    }

    @Test
    void adminPublicLookingNameIsStillProtected() {
        client.get().uri("/api/admin/public")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }

    @Test
    void forgedRoleCannotElevateAliceInAdminChain() {
        client.get().uri("/api/admin/report")
                .headers(h -> {
                    h.setBasicAuth("alice", "alice-pass");
                    h.set("X-User", "admin");
                    h.set("X-Role", "ADMIN");
                })
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }

    @Test
    void forgedUserDoesNotChangeApiPrincipal() {
        client.get().uri("/api/me")
                .headers(h -> {
                    h.setBasicAuth("alice", "alice-pass");
                    h.set("X-User", "admin");
                })
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(CHAIN_HEADER, "api")
                .expectBody()
                .jsonPath("$.principal").isEqualTo("alice");
    }

    @Test
    void existingApiHandlerIsDenied() {
        client.get().uri("/api/hidden")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void nearAdminPrefixBelongsToApiChain() {
        client.get().uri("/api/adminX/data")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void existingFallbackHandlerIsDenied() {
        client.get().uri("/hidden")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback");
    }

    @Test
    void unknownUrlIsAlsoHandledByFallback() {
        client.get().uri("/missing")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback");
    }

    @Test
    void fallbackAnonymousHiddenHandlerRequiresAuthentication() {
        client.get().uri("/hidden")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback");
    }

    @Test
    void headDoesNotInheritGetOnlyPublicRule() {
        client.head().uri("/api/public")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void postToGetOnlyPathIsNotOpened() {
        client.post().uri("/api/public")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void fallbackDenyAllAlsoBlocksAdminUser() {
        client.get().uri("/hidden")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback");
    }

    @Test
    void noCredentialPlusFakeAdminHeadersIsStill401() {
        client.get().uri("/api/admin/report")
                .header("X-User", "admin")
                .header("X-Role", "ADMIN")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }
}
```

### 9.2. Chạy test

```bash
gradle test
```

Bộ mã **thiết kế 20 JUnit tests**. Kỳ vọng là BUILD SUCCESSFUL và 20 tests PASS khi JDK/Gradle/dependencies tương thích. Đây **không phải khẳng định đã thực sự chạy Gradle** trong lúc viết bài. Tất cả HTTP Basic credentials chỉ là fixtures local.

### 9.3. Những điều bộ test chứng minh

| Test group | Chứng minh |
| --- | --- |
| Public fallback và API | Hai URL anonymous nhận 200 trong **hai chains khác nhau** |
| Private API anonymous và Alice | 401/200; marker api và principal đã verify |
| Basic password sai | 401, không coi header tự khai là login |
| Admin overlap | Alice 403, Admin 200, marker **admin**, không bị API chain che |
| Đường dẫn tên public trong vùng admin | Route name không tự thay admin matcher |
| Fake X-User/X-Role | Không tạo ROLE_ADMIN hoặc thay principal Alice |
| API handler tồn tại nhưng không allowlisted | 403 và marker api |
| Prefix adminX | Vào apiChain thay vì adminChain |
| Fallback handler tồn tại | Bị 403 dù controller có thể trả dữ liệu |
| Fallback URL không có handler | Vẫn 403 cho authenticated user, cho thấy policy chạy trước handler lookup |
| HEAD/POST vào GET-only | Không được public chỉ vì cùng path |
| Admin user ở fallback | Vẫn denyAll, không có đặc quyền toàn cục |
| Anonymous ở fallback | Basic entry point có thể trả 401 |
| Nhận diện chain qua header | Không dựa riêng vào status 401/403 |

### 9.4. Không dùng 404 làm bằng chứng bảo vệ

Nếu `GET /missing` trả 404, đó có thể chỉ là không có handler, ngay cả khi **không chain nào match**. Vì vậy cần handler thật `/hidden` và test nó bị fallback denyAll chặn. Test `unknownUrlIsAlsoHandledByFallback` bổ sung kiểm chứng route coverage, nhưng **không thay** bài test handler thật.

### 9.5. Phân tích lỗi theo thứ tự

Nếu một test fail:

1. Kiểm tra HTTP method, path, Basic credential trong test.
2. Đọc `X-Lab-Security-Chain`: admin/api/fallback? Có marker không?
3. Marker sai -> xem `@Order` và `.securityMatcher(...)`.
4. Marker đúng nhưng 200/403 sai -> xem `.authorizeExchange(...)` và authorities.
5. Basic sai nhưng 200 -> kiểm tra auth manager/mocked security/chain selection.
6. POST 403 -> kiểm tra CSRF trước khi kết luận matcher denyAll.
7. 302 -> có thể một chain bật formLogin/redirect.
8. 404 -> có thể handler không tồn tại hoặc request bị chặn trước chain; không coi 404 là QA pass.
9. Không marker -> có thể HTTP parser, firewall, gateway, CORS hoặc chain registration lỗi; cần phân lớp.
10. Không sửa bằng cách bỏ fallback, tắt Spring Security hoặc chuyển `denyAll` thành `permitAll`.

### 9.6. Vì sao không chỉ đọc `@Order` trên beans?

Một code review thấy `adminChain @Order(1)` vẫn có thể bỏ sót:
- Matcher gõ sai `/api/administration/**`.
- Một bean khác có @Order(0) match all.
- Fallback được khai báo ở vị trí quá cao.
- Global WebFilter hoặc HTTP proxy rewrite path.
- Test không sử dụng đầy đủ Spring Security infrastructure.
- URL mới không nằm trong bất kỳ matcher nào.

Integration tests gửi request thật và kiểm tra marker trực tiếp giải quyết những trường hợp trên tốt hơn việc chỉ assert bean definitions.

## 10. Kiểm thử boundaries ngoài ví dụ

### 10.1. Trailing slash và encoded path

Nên thêm một bảng cases theo proxy/Framework hiện tại cho:
- `/api/admin`, `/api/admin/`, `/api/admin/report`.
- `/api/adminX/data`, `/api/administrator/report`.
- Encoded slash/dot, `//`, case changes, trailing slash.
- Context path, base path, forwarded prefix nếu có load balancer.

**Không** đoán mọi encoded-path phải 401/403. Một request malformed có thể bị HTTP parser/firewall chặn với 400/404 trước Spring Security chain. Điều bất biến là không có request ngoài policy được phép nhận dữ liệu nhạy cảm.

### 10.2. Method restrictions

Với public rule chỉ GET, test HEAD, POST, PUT, DELETE ở những URL có nguy cơ thao tác trạng thái. Test POST cần xét CSRF riêng. Nếu test JSON REST API token-based, các quy tắc CSRF có thể khác; chỉ disable CSRF khi threat model cho phép và test đủ các phương thức state-changing.

### 10.3. CORS và OPTIONS

Preflight OPTIONS có thể được xử lý bởi CORS WebFilter trước authentication/authorization. Nếu chain A và B khai báo CORS khác nhau, browser có thể lỗi trong khi curl GET hoạt động. Test `Origin`, `Access-Control-Request-Method`, allow-origin, allow-credentials và preflight status theo từng chain. Không tự phản chiếu Origin hoặc trả wildcard origin cùng credentials.

### 10.4. Login endpoints do framework sinh ra

Khi bật `formLogin`, `oauth2Login`, OAuth2 authorization code callback, logout hoặc request cache, nhiều endpoint thuộc security framework, không có controller riêng. Nếu những endpoints đó nằm **ngoài securityMatcher của chain** cần chúng, flow có thể trả 404 hoặc đi nhầm fallback.

Demo cố ý chỉ dùng HTTP Basic, tắt formLogin trong cả ba chains để không có trang login/redirect không được tính đến. Trong hệ thực, hãy test login callback/logout/session renewal cùng matcher và CSRF đúng của chain.

### 10.5. SecurityContext repository và session

Chia nhiều chains không tự tạo kho users/sessions độc lập. Cùng WebSession có thể mang SecurityContext nếu ứng dụng dùng session-based auth, nhưng quyền vẫn phải do chain được chọn và authorize rules quyết định. Nếu cần tenant/session isolation, hãy thiết kế authentication, repositories và trust boundaries riêng thay vì dựa vào `@Order`.

### 10.6. Dùng OAuth2 Bearer JWT cho API chain

Một thiết kế production phổ biến:
- `/api/**` -> OAuth2 Resource Server JWT, Bearer challenge.
- `/portal/**` -> form login/WebSession.
- catch-all -> denyAll, mở chính xác health/assets cần thiết.

Snippet thay cơ chế auth trong API chain (cần `spring-boot-starter-oauth2-resource-server`, `ReactiveJwtDecoder` trusted, issuer, audience, expiry validators và test riêng):

```java
@Bean
@Order(1)
SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth -> oauth
            .jwt(Customizer.withDefaults()))
        .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}
```

Đây là **snippet phương án khác**, không thêm vào project Basic phía trên. Spring Security Test `mockJwt()` hữu ích khi kiểm thử authority/route, nhưng **có thể bypass decoder**. Muốn kiểm chứng JWT thật phải thêm signed JWT/JWKS test với signature, issuer, audience, expiry và scope cases. Giữ chain selection tests và cập nhật credential/header expectations.

## 11. Các lỗi hay gặp

| Lỗi | Tác hại | Biện pháp |
| --- | --- | --- |
| `apiChain` ưu tiên cao hơn `adminChain` | Chain rộng che admin | @Order hẹp trước rộng + overlap test |
| Không có catch-all fallback | URL ngoài matchers thiếu Spring Security protection | Fallback không matcher riêng |
| Fallback `anyExchange().permitAll()` | Endpoint mới bất ngờ public | denyAll và explicit allowlist |
| Tưởng 403 sẽ thử chain khác | Hiểu sai chain selection | Chain đầu match thắng |
| Dùng pathMatchers thay securityMatcher để chọn chain | Chain có thể match mọi URL | Đúng tầng matcher |
| Tin 404 là security chặn | Có thể thiếu handler | Test handler thật bị deny |
| Chỉ assert 200 | Không thấy authorization bypass | Kiểm thử 401/403 và marker |
| Không test prefix gần giống | Có thể match sai segment | PathPatternParser + boundary tests |
| Quên HTTP methods | HEAD/POST vô tình public | Method-specific allowlists |
| Tắt CSRF để POST không 403 | Mất bảo vệ browser | CSRF policy/tests rõ |
| Dùng Servlet HttpSecurity trong WebFlux | Khác stack | ServerHttpSecurity |
| Cho X-User/X-Role thành authority | Privilege escalation | Verified Authentication |
| Marker WebFilter vừa global vừa addFilterAt | Header trùng/sai chain | Marker chỉ nằm trong chain |
| Không kiểm tra Basic challenge | 302 hoặc 403 thay 401 | Test auth mechanism mỗi chain |
| Đổi thành authenticated fallback | User đã login thấy URL chưa kiểm kê | denyAll nếu muốn fail-closed |
| Không kiểm thử login/callback endpoints | 404 hoặc wrong chain | Tính endpoint framework vào matcher |
| Test mock user mà kết luận password đúng | Bypass real auth in test | WebTestClient Basic thực |
| Chuyển JWT nhưng chỉ dùng mockJwt | Không test signature validation | Real signed token/JWKS tests |
| Tiết lộ lab chain header ở production | Fingerprinting internals | Loại trước triển khai |
| Quên sửa tests khi thay chain priorities | Phân quyền sai âm thầm | Review matrix + CI tests |

## 12. Checklist QA trước production

1. Liệt kê tất cả SecurityWebFilterChain beans, matcher và @Order.
2. Đặt matcher hẹp và nhạy cảm trước matcher rộng.
3. Có fallback no-securityMatcher ở cuối, denyAll trừ route public chủ đích.
4. Phân biệt chain selection và authorization rule selection.
5. Test route overlap phải vào đúng chain ưu tiên.
6. Test prefix gần giống không rơi nhầm chain.
7. Test fallback trên handler **có thật** không được allow.
8. Test 401 anonymous/bad credential và 403 authenticated thiếu role.
9. Test valid users/roles nhận 200 ở đúng chain.
10. Test HTTP methods khác GET trên public path.
11. Test CSRF/CORS/preflight nếu dùng browser credentials.
12. Test security headers, redirect/login/logout endpoints theo từng chain.
13. Test URL normalization, proxy path rewrite, base path, encoded paths trong staging.
14. Không dựa vào 404 làm bằng chứng authorization.
15. Không tin user/role từ raw headers hoặc query.
16. Dùng authenticated Principal và role policy đã verify.
17. Nếu JWT, validate issuer/audience/signature/expiry, không chỉ mockJwt.
18. Không đăng ký debug WebFilter global khi muốn quan sát một chain.
19. Loại bỏ lab-only response marker ở production.
20. Khi nâng phiên bản Spring, chạy lại full test matrix và xem release security advisories.

## 13. Bài tập và đáp án ngắn

1. Vì sao `/api/admin/**` phải ưu tiên trước `/api/**`? — Vì hai matchers overlap và chain đầu match thắng.
2. Nếu adminChain trả 403, apiChain có được thử tiếp không? — Không.
3. `securityMatcher` khác `pathMatchers` ở đâu? — Một cái chọn chain, một cái phân quyền request trong chain.
4. `anyExchange()` bao phủ tất cả app không? — Chỉ toàn bộ requests còn lại của chain đã chọn.
5. Fallback không có matcher có vai trò gì? — Bao phủ các request không match chain trước.
6. Tại sao fallback denyAll tốt hơn authenticated trong fail-closed policy? — Authenticated sẽ mở mọi endpoint mới cho người đăng nhập.
7. Thiếu fallback có thể gây gì? — Một số URL không được Spring Security web chain bảo vệ.
8. Vì sao chỉ kiểm tra 404 không đủ? — Không có controller cũng 404 khi không security.
9. Marker header có phải production security header không? — Không, chỉ lab/test.
10. Test nào phát hiện chain A/B bị đảo? — GET /api/admin/report với Alice/Admin và marker expected admin.
11. `/api/adminX/data` nên dùng chain nào? — API chain.
12. `/api/hidden` có handler nhưng Basic Alice được gọi không? — Không, API anyExchange denyAll -> 403.
13. Admin có thể gọi `/hidden` không? — Không, fallback denyAll -> 403.
14. GET public có nghĩa POST public không? — Không nếu rule giới hạn HttpMethod.GET.
15. POST 403 có thể đến từ đâu? — CSRF hoặc authorization.
16. Vì sao X-Role: ADMIN không thay đổi quyền? — Header do client tự khai chưa verify.
17. `@Order` khác `SecurityWebFiltersOrder` thế nào? — Chọn chain vs sắp WebFilter trong chain.
18. Khi dùng JWT, `mockJwt()` đã test signature thật chưa? — Chưa.
19. Vì sao form login endpoints cần tính vào chain matcher? — Framework sinh route login/callback và có thể bị fallback chặn.
20. Nếu request không có marker thì kết luận gì? — Chưa đủ, có thể bị chặn trước chain; cần điều tra.
21. Có phải Basic tự mã hóa mật khẩu khi truyền HTTP không? — Không, cần TLS.
22. Lý do dùng handler `/hidden` thật trong test? — Chứng minh fallback bảo vệ resource thực.
23. `@Order(1)` và `@Order(2)` cùng không match URL thì sao? — Fallback được xét.
24. Vì sao nhiều chains không tự tách WebSession? — Chúng là các policy/filter paths, không mặc định các session stores riêng.
25. Chọn kết quả test nào khi user Basic sai vào `/api/me`? — 401 và marker api.

## 14. Tài liệu tham khảo

- Spring Security 6.5 — WebFlux Security, Multiple Chains Support: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security — Reactive Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — WebTestClient Setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Reactive HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/passwords/basic.html
- Spring Security 6.5 Javadoc — ServerHttpSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 Javadoc — PathPatternParserServerWebExchangeMatcher: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html
- Spring Security 6.5 Javadoc — SecurityWebFilterChain: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html
- Spring Boot 3.5 — Gradle plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Kết luận:** Trong Spring Security Reactive, nhiều `SecurityWebFilterChain` đòi hai lớp kiểm chứng: (1) request được chọn vào **chain đúng**, theo `@Order` + `securityMatcher`; (2) chain đó **authorize đúng**, theo `authorizeExchange`. Luôn đặt matcher hẹp trước matcher rộng, có fallback catch-all denyAll, và kiểm thử WebTestClient với 200/401/403, handler có thật, overlapping path prefixes và debug marker chỉ dùng cho test. Một 404 không chứng minh chain bảo vệ, và một 403 không tự chứng minh chain đã được chọn đúng.