# Cấu hình nhiều chuỗi cho miền API khác nhau và kiểm chứng vùng bao phủ

## 1. Tại sao hệ thống Gateway và nhiều tenant cần nhiều chuỗi bảo mật?

Một ứng dụng Spring WebFlux thường đứng sau API Gateway, phục vụ nhiều miền có security contract khác nhau:
- `/api/admin/**`: quản trị, sử dụng JWT Bearer có `SCOPE_admin.read`.
- `/api/tenant/{tenantId}/items`: API đa tenant, yêu cầu JWT có `SCOPE_tenant.read`, đồng thời user/service phải được phép truy cập tenant thực tế.
- `/api/ping`: endpoint đọc công khai.
- `/ops/status`: endpoint vận hành nội bộ, dùng HTTP Basic **chỉ để minh họa một authentication mechanism khác**.
- `/api/v2/unreviewed` và `/diagnostics/secret`: các handler mới hoặc nhạy cảm **chưa được phê duyệt**, phải bị chặn thay vì tình cờ public.

Với một security chain duy nhất, việc phối hợp JWT, Basic, CORS, CSRF, entry point và nhiều scopes dễ thành một khối khó review. Spring Security Reactive cho phép nhiều `SecurityWebFilterChain` beans, mỗi chain có `securityMatcher` và `@Order` riêng.

Rủi ro cốt lõi: **`anyExchange().denyAll()` trong một SecurityWebFilterChain chỉ bảo vệ các requests match chính chuỗi ấy, không bảo vệ mặc nhiên tất cả URL của ứng dụng.** Nếu các securityMatchers bỏ sót một route, request có thể đi vào handler mà không qua security filters của các chain đó.

Do vậy, phải kiểm **hai tầng**:
1. **Chain selection và coverage:** request đi vào chain nào; có khoảng hở; chain rộng có che chain hẹp không?
2. **Authorization trong chain:** user đã xác thực bằng đúng cơ chế chưa, có đúng scope/role/tenant/ownership chưa?

Bài thuộc nhóm **Gateway và nhiều tenant** của module Spring Security - reactive. Nội dung cung cấp cấu hình Java 17+, các bảng coverage, ứng dụng WebFlux, `WebTestClient` tests và checklist production.

### Kết quả học tập

Sau bài, bạn có thể:
1. Giải thích `securityMatcher(...)` khác `authorizeExchange().pathMatchers(...)`.
2. Dùng `@Order` để chọn chain hẹp trước chain rộng, tuân theo nguyên tắc first-match.
3. Thiết kế fallback chain match-all với `denyAll()`.
4. Cô lập JWT Admin/Tenant API với HTTP Basic Ops.
5. Bảo vệ path roots, methods không được phê duyệt, version mới, URL sau Gateway rewrite.
6. Kiểm tra cả **matcher-level** và **HTTP-level** bằng `WebTestClient`.
7. Ngăn cross-tenant access dù JWT có scope hợp lệ.
8. Nhận biết test mock token không chứng minh chữ ký, issuer, audience hay JWKS thật.
9. Chuẩn bị kiểm thử end-to-end Gateway, CORS, CSRF và monitoring.

## 2. Phân biệt securityMatcher và authorizeExchange.pathMatchers

### 2.1. securityMatcher quyết định **chuỗi nào** được áp dụng

Trong Reactive:
~~~java
@Bean
@Order(1)
SecurityWebFilterChain admin(ServerHttpSecurity http) {
    return http
            .securityMatcher(ServerWebExchangeMatchers.pathMatchers(
                    "/api/admin", "/api/admin/**"))
            .authorizeExchange(ex -> ex
                    .anyExchange().hasAuthority("SCOPE_admin.read"))
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
~~~

Đây là snippet cấu hình; các imports đầy đủ nằm trong project dưới. Khi request đi vào `/api/admin/report`, `securityMatcher` này có thể match. Khi request đi vào `/api/tenant/acme/items`, matcher không match, và Spring Security xét chain sau.

### 2.2. authorizeExchange quyết định **quyền bên trong** chuỗi

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/admin/report")
            .hasAuthority("SCOPE_admin.read")
    .anyExchange().denyAll())
~~~

`anyExchange()` ở đây có nghĩa “mọi request còn lại **trong admin chain đã được chọn**”. Nó không thể thay một catch-all chain cho `/diagnostics/secret` ở ngoài `/api/admin/**`.

### 2.3. Thứ tự chọn chain

Spring Security Reactive dùng `WebFilterChainProxy` duyệt các `SecurityWebFilterChain` theo thứ tự. Nó chọn **chain đầu tiên có `matches(exchange)` trả true**. Không cộng dồn JWT filter của một chain với Basic filter của chain khác.

~~~text
GET /api/admin/report
       |
       v
@Order(1) /api/admin + /api/admin/** -> MATCH -> ADMIN JWT
       |
       X Các chain sau không chạy:
@Order(2) /api + /api/**            -> cũng có thể match về path
@Order(3) /ops + /ops/**
@Order(99) match-all fallback
~~~

Với `GET /api/tenant/acme/items`, admin matcher không khớp, general API matcher khớp. Với `GET /diagnostics/secret`, ba matcher đầu không khớp, catch-all nhận request và denyAll.

**Lưu ý:** first-match là theo `@Order` (số nhỏ hơn thường ưu tiên hơn); không phải theo thứ tự code, độ dài URL hay “mức độ nghiêm ngặt” của luật.

### 2.4. Hai lỗi nguy hiểm

**Sai 1 — chain rộng đứng trước chain hẹp:**

~~~java
// PHẢN VÍ DỤ: không sử dụng thứ tự này.
@Order(1) // broad chain bắt cả /api/admin/**
SecurityWebFilterChain api(...) {
    return http.securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .authorizeExchange(ex ->
                    ex.anyExchange().authenticated())
            .build();
}

@Order(2) // admin chain không bao giờ chạy cho /api/admin/report
SecurityWebFilterChain admin(...) {
    return http.securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/admin/**"))
            .authorizeExchange(ex ->
                    ex.anyExchange().hasAuthority("SCOPE_admin.read"))
            .build();
}
~~~

Token user thường có thể truy cập admin nếu broad chain chỉ đòi authenticated và không có domain controls khác.

**Sai 2 — thiếu catch-all:**

~~~text
Configured: admin matcher /api/admin/**, API matcher /api/**, ops /ops/**
Existing controller: GET /diagnostics/secret
Without fallback: no chain matches /diagnostics/secret
Potential result: controller may run without these security filters
~~~

Không được tin rằng Spring Boot sẽ tự bổ sung một security chain phủ toàn app sau khi ứng dụng đã định nghĩa các custom `SecurityWebFilterChain` beans.

## 3. Thiết kế vùng bao phủ với path, method, auth scheme và tenant

Trước khi viết code, hãy có ma trận security contract:

| Request mẫu | Chọn chain | Authentication | Quyền | Kỳ vọng |
| --- | --- | --- | --- | --- |
| GET `/api/admin/report` | Admin @Order 1 | Bearer JWT | admin.read | 200 khi đủ scope |
| GET `/api/admin/report` token tenant.read | Admin @Order 1 | JWT hợp lệ | Thiếu admin.read | 403 |
| GET `/api/admin` | Admin @Order 1 | Bearer JWT | admin.read | 200 nếu có route |
| GET `/api/tenant/acme/items` | API @Order 2 | Bearer JWT | tenant.read + tenant match | 200 |
| GET `/api/tenant/beta/items`, JWT tenant acme | API @Order 2 | Bearer JWT | tenant mismatch | 403 |
| GET `/api/ping` | API @Order 2 | Anonymous | permitAll | 200 |
| GET `/api/ping` với invalid Bearer | API @Order 2 | Invalid JWT | Authentication failure | 401 |
| POST `/api/ping` | API @Order 2 | JWT | Không có POST rule | 403 |
| GET `/ops/status` | Ops @Order 3 | Basic | ROLE_OPS | 200 |
| GET `/ops/status` với Bearer | Ops @Order 3 | Không phải Basic | ROLE_OPS | 401 |
| GET `/api/admin/report` với Basic | Admin @Order 1 | Không phải Bearer | admin.read | 401 |
| GET `/api/v2/unreviewed` | API @Order 2 | JWT | Unreviewed denyAll | 403 |
| GET `/diagnostics/secret` | Fallback @Order 99 | — | denyAll | 4xx, không được 200 |
| GET `/api-admin/report` | Fallback @Order 99 | — | denyAll | 4xx |
| GET `/api` | API @Order 2 | JWT | Không có allow rule | 403 |
| GET `/api/tenant/acme/items` không token | API @Order 2 | Missing Bearer | tenant.read | 401 |

Hãy thêm các cột external host, internal path sau proxy rewrite, audience, issuer, owner, expected 401/403/200 và testcase vào manifest thật. **Không chỉ liệt kê URL đã công khai**: cả routes chưa review, roots và HTTP methods lạ cũng cần test.

## 4. Tách chain coverage, route authorization và domain ownership

Ba tầng bổ sung cho nhau:

1. **Chain selection:** `ServerWebExchangeMatcher` quyết định filters sẽ chạy: JWT, Basic, CSRF, CORS, headers, error entry points.
2. **Route authorization:** `authorizeExchange` yêu cầu scope/role theo HTTP method/path hoặc denyAll.
3. **Domain authorization:** service kiểm tenant membership và quyền trên resource cụ thể. Path `/api/tenant/beta/items` không làm người mang JWT tenant `acme` tự có quyền tenant beta.

Ví dụ:

~~~text
JWT signature valid, aud=multi-tenant-api, scope=tenant.read,
tenant_id=acme
        |
        v
GET /api/tenant/beta/items
        |
        +-- Chọn API chain: PASS
        +-- JWT verified: PASS
        +-- SCOPE_tenant.read: PASS
        +-- tenant acme == requested beta: FAIL -> 403
~~~

Ở hệ thống thật, claim `tenant_id` có thể là thông tin đầu vào cho lookup, nhưng **quyền trong tenant** vẫn phải dựa trên entitlement và ownership policy tin cậy. Không dùng email domain, hostname, `X-Tenant` hoặc query parameter do caller tự khai để cấp role.

## 5. Cấu trúc dự án Java 17 + Spring Boot 3.5

Ta xây một project WebFlux có **4 SecurityWebFilterChain**:
- Admin hẹp trước general API.
- General API bao phủ cả `/api/**`.
- Ops tách HTTP Basic.
- Fallback phủ mọi URL khác và `denyAll`.

Project:

~~~text
webflux-multi-chain-coverage/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── MultiChainHttpTest.java
        └── ChainCoverageTest.java
~~~

**Giới hạn minh bạch:** `application.yml` dùng issuer/JWKS hostname ví dụ không có IdP thật. WebTestClient HTTP tests mock `ReactiveJwtDecoder`; chúng kiểm filter chain, matcher và authorization, **không xác minh RSA signature/issuer/audience thật**. Cần integration tests với JWKS server và signed tokens khi đưa vào production.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-multi-chain-coverage'
~~~

### 5.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Starter Resource Server cần cho JWT Bearer API; không cần OAuth2 Login client. Chọn phiên bản Boot/Spring Security được tổ chức hỗ trợ và cập nhật bản vá bảo mật phù hợp.

### 5.3. application.yml

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: webflux-multi-chain-coverage
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - multi-tenant-api
~~~

- `issuer-uri`: issuer mà token `iss` phải khớp.
- `jwk-set-uri`: trusted public keys để verify JWS signature.
- `audiences`: resource server yêu cầu token dành cho `multi-tenant-api`.

**Placeholder hostname không dùng để authenticate production.** Khi dùng thật, phải cấu hình issuer/JWKS HTTPS của Authorization Server, algorithm allowlist, key rotation và valid access-token profile. Test mock decoder không kiểm những điều kiện này.

### 5.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

## 6. SecurityConfig.java — cấu hình nhiều SecurityWebFilterChain đầy đủ

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain adminApi(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers(
                                "/api/admin", "/api/admin/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Chỉ Bearer-only, không có browser session login.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/api/admin", "/api/admin/report")
                                .hasAuthority("SCOPE_admin.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain generalApi(ServerHttpSecurity http) {
        return http
                // /api/** cũng bao gồm admin path, nhưng @Order(1) chạy trước.
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers(
                                "/api", "/api/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/api/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/tenant/*/items")
                                .hasAuthority("SCOPE_tenant.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain opsApi(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers(
                                "/ops", "/ops/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Giữ CSRF mặc định cho Basic; demo Ops chỉ có GET.
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/ops/status")
                                .hasRole("OPS")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(99)
    SecurityWebFilterChain catchAllDeny(ServerHttpSecurity http) {
        return http
                // Không giới hạn securityMatcher: match request còn lại.
                .authorizeExchange(ex -> ex
                        .anyExchange().denyAll())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    ReactiveUserDetailsService demoOpsUsers() {
        UserDetails operator = User.withUsername("operator")
                // Demo local ONLY; không triển khai {noop} password.
                .password("{noop}local-demo-only")
                .roles("OPS")
                .build();
        return new MapReactiveUserDetailsService(operator);
    }
}
~~~

### 6.1. Phân tích từng chain

**Admin @Order(1):** matcher nhận `/api/admin` và mọi subpath. Nó chỉ cho GET root và report với `SCOPE_admin.read`. JWT chỉ có tenant.read sẽ bị 403. Basic auth từ Ops không hoạt động trong Admin JWT chain.

**General API @Order(2):** matcher nhận `/api` và các subpaths **chưa được admin chain chọn**. `GET /api/ping` public; `GET /api/tenant/*/items` cần tenant.read; mọi route/method còn lại denyAll. Vì chain này rộng, khi thêm `/api/v2/new` sẽ không được auto-public.

**Ops @Order(3):** matcher chỉ nhận `/ops` và `/ops/**`, dùng Basic + role OPS. Giữ CSRF default; chỉ có GET được phép. Production cần TLS, network isolation và credentials/identity provider mạnh; demo `{noop}` chỉ dành cho học tập, không đưa vào production.

**Catch-all @Order(99):** không có `securityMatcher` hạn chế, nên match mọi URL chưa được một chain trước nhận. Từ chối tất cả, kể cả controller có thật ngoài `/api/**` và `/ops/**`. Không thay bằng `permitAll()`.

### 6.2. Tại sao tách CSRF?

Với JWT API chỉ dùng Bearer Authorization header do client chủ động gửi (không có ambient cookie/browser Basic) thì `csrf(...disable)` có thể hợp lý theo threat model. Với HTTP Basic browser cache hoặc OIDC Login/WebSession, CSRF có thể tồn tại vì browser tự gửi credential. Không tắt CSRF trên mọi chain chỉ vì hệ thống có API Gateway.

### 6.3. Không mở “role OPS” trên API Admin

Việc cấu hình Basic Ops chain không cho phép Basic operator có quyền admin. Cả hai phải tách `securityMatcher` và authentication mechanism. `hasRole("OPS")` trong Ops mặc định kiểm `ROLE_OPS`, còn JWT API yêu cầu `SCOPE_admin.read`/`SCOPE_tenant.read`. Những authorities này không thể hoán đổi.

## 7. ApiController.java — có cả handler cố ý phải bị chặn

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/admin")
    public Mono<String> adminRoot() {
        return Mono.just("admin-root");
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> adminReport(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
                "result", "admin-report",
                "subject", jwt.getSubject()));
    }

    @GetMapping("/api/tenant/{tenantId}/items")
    public Mono<Map<String, Object>> tenantItems(
            @PathVariable String tenantId,
            @AuthenticationPrincipal Jwt jwt) {

        String authenticatedTenant =
                jwt.getClaimAsString("tenant_id");

        if (!tenantId.equals(authenticatedTenant)) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Principal not authorized for this tenant"));
        }

        // Demo only; production cần kiểm object ownership ở service/repo.
        return Mono.just(Map.of(
                "tenant", tenantId,
                "subject", jwt.getSubject(),
                "items", List.of("BOOK", "PEN")));
    }

    @GetMapping("/ops/status")
    public Mono<String> opsStatus() {
        return Mono.just("UP");
    }

    // Các handler này CÓ THẬT để test coverage fail-closed.
    @GetMapping("/api/v2/unreviewed")
    public Mono<String> unreviewedApi() {
        return Mono.just("SHOULD_NOT_BE_EXPOSED");
    }

    @GetMapping("/diagnostics/secret")
    public Mono<String> diagnosticsSecret() {
        return Mono.just("SHOULD_NOT_BE_EXPOSED");
    }

    @GetMapping("/api")
    public Mono<String> apiRoot() {
        return Mono.just("SHOULD_NOT_BE_EXPOSED");
    }
}
~~~

**Vì sao có handler “SHOULD_NOT_BE_EXPOSED”?** Một đường dẫn không có controller trả 404 dù không có security; test 404 không chứng minh vùng bao phủ. Với handler thật, nếu fallback bị xóa hoặc đổi `permitAll`, request có thể trả 200 và test sẽ phát hiện.

### 7.1. Tenant check đúng hướng, nhưng chưa phải chính sách đầy đủ

`tenant_id` ở JWT chỉ đáng tin sau signature/issuer/audience/timestamp validation. Demo so sánh với path variable để thấy ý nghĩa **authorization sau route scope**. Trong ứng dụng thật:
- Principal có thể thuộc nhiều tenants, cần tra membership/entitlements.
- Data queries phải được scope theo tenant và object owner.
- Client không được dùng `X-Tenant`, query parameter hay hostname giả để chọn một tenant không được cấp phép.
- Không dựa trên email domain để cấp role.
- 403 và 404 có thể là các lựa chọn che tồn tại object tùy API contract.
- Kiểm tra tenant tại service/data layer, không tin route matcher là tenant isolation.

## 8. MultiChainHttpTest.java — kiểm tra hành vi HTTP thật qua WebFilters

Test dùng `WebTestClient.bindToApplicationContext(context).apply(springSecurity())`, gửi các request bằng GET/POST và Authorization headers. Bean `ReactiveJwtDecoder` được mock bằng `@MockitoBean` thuộc Spring Framework Test 6.2+/Spring Boot 3.5, chỉ trong test context.

Vì token `admin-token` là chuỗi tùy chọn không phải JWT ký số, test này kiểm **Bearer extraction → mocked decoder → authorities → chain-specific authorization**, không kiểm signature/JWKS thật.

`src/test/java/demo/MultiChainHttpTest.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class MultiChainHttpTest {

    @Autowired
    ApplicationContext context;

    @MockitoBean
    ReactiveJwtDecoder decoder;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();

        when(decoder.decode("admin-token"))
                .thenReturn(Mono.just(jwt(
                        "admin-token", "admin.read", "acme")));
        when(decoder.decode("tenant-token"))
                .thenReturn(Mono.just(jwt(
                        "tenant-token", "tenant.read", "acme")));
        when(decoder.decode("other-token"))
                .thenReturn(Mono.just(jwt(
                        "other-token", "profile", "beta")));
        when(decoder.decode("bad-token"))
                .thenReturn(Mono.error(
                        new BadJwtException("invalid test token")));
    }

    private Jwt jwt(String value, String scope, String tenant) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("iss", "https://idp.example.test/issuer")
                .claim("sub", "user-42")
                .claim("aud", List.of("multi-tenant-api"))
                .claim("scope", scope)
                .claim("tenant_id", tenant)
                .issuedAt(now.minusSeconds(30))
                .expiresAt(now.plusSeconds(600))
                .build();
    }

    @Test
    void publicPingIs200() {
        client.get().uri("/api/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void badBearerOnPublicPingStillGets401() {
        client.get().uri("/api/ping")
                .headers(h -> h.setBearerAuth("bad-token"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void adminWithoutBearerIs401() {
        client.get().uri("/api/admin/report")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void tenantScopeCannotEnterAdminChain() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminScopeCanReadAdminReport() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.result")
                .isEqualTo("admin-report");
    }

    @Test
    void adminRootCannotBypassAdminChain() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-root");
    }

    @Test
    void tenantApiWithoutBearerIs401() {
        client.get().uri("/api/tenant/acme/items")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validTenantScopeCanReadSameTenant() {
        client.get().uri("/api/tenant/acme/items")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.tenant").isEqualTo("acme");
    }

    @Test
    void validTenantScopeCannotReadOtherTenant() {
        client.get().uri("/api/tenant/beta/items")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminScopeAloneDoesNotGrantTenantScope() {
        client.get().uri("/api/tenant/acme/items")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void basicCannotEnterJwtAdminChain() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth(
                        "operator", "local-demo-only"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void opsWithoutBasicIs401() {
        client.get().uri("/ops/status")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void correctBasicCanAccessOps() {
        client.get().uri("/ops/status")
                .headers(h -> h.setBasicAuth(
                        "operator", "local-demo-only"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("UP");
    }

    @Test
    void wrongBasicPasswordGets401() {
        client.get().uri("/ops/status")
                .headers(h -> h.setBasicAuth(
                        "operator", "wrong"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void bearerCannotEnterBasicOpsChain() {
        client.get().uri("/ops/status")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void mappedButUnreviewedApiIsDenied() {
        client.get().uri("/api/v2/unreviewed")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void apiRootIsDeniedWithJwt() {
        client.get().uri("/api")
                .headers(h -> h.setBearerAuth("admin-token"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void postToPublicGetEndpointIsDenied() {
        client.post().uri("/api/ping")
                .headers(h -> h.setBearerAuth("tenant-token"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("body")
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void catchAllBlocksRealDiagnosticsHandler() {
        client.get().uri("/diagnostics/secret")
                .exchange().expectStatus().is4xxClientError();
    }
}
~~~

Mã trên có **19 phương thức @Test**. Các ca kiểm thử quan trọng:
- Bearer tenant.read bị từ chối ở Admin chain.
- JWT có scope đúng nhưng claim tenant không khớp vẫn bị 403.
- Basic không mở JWT API, Bearer không mở Basic Ops.
- Một handler mới nằm trong `/api/**` nhưng chưa có rule vẫn bị 403.
- Một handler ngoài các prefix được match vào fallback và không trả 200.
- `permitAll` không phải bỏ authentication filter: bad Bearer trên public API path vẫn có thể 401.

**Các JWT test ở đây đều là mock decoder.** Không thể dùng chuỗi `tenant-token` trong app runtime và kết luận Spring Security đã verify chữ ký thật.

## 9. ChainCoverageTest.java — kiểm tra first-match order và vùng bao phủ

HTTP tests có thể trả 403 do một chain **sai** đang denyAll, nên chỉ xét status chưa xác định được chain được chọn. Test thứ hai kiểm trực tiếp `SecurityWebFilterChain.matches(ServerWebExchange)`.

Lưu ý API types:
- `SecurityWebFilterChain.matches(exchange)` trả `Mono<Boolean>`.
- `ServerWebExchangeMatcher.matches(exchange)` trả `Mono<MatchResult>`.

Không dùng nhầm kiểu return. Trong JUnit test, `block(Duration)` để chờ matcher Mono ngoài request event-loop là chấp nhận được; **không dùng `block()` trong production WebFlux handlers hoặc filters**.

`src/test/java/demo/ChainCoverageTest.java`:

~~~java
package demo;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ChainCoverageTest {

    @Autowired
    List<SecurityWebFilterChain> chainsByOrder;

    private int firstMatch(String path) {
        ServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get(path).build());

        for (int i = 0; i < chainsByOrder.size(); i++) {
            Boolean match = chainsByOrder.get(i)
                    .matches(exchange)
                    .block(Duration.ofSeconds(2));
            if (Boolean.TRUE.equals(match)) {
                return i;
            }
        }
        return -1;
    }

    @Test
    void exactlyFourChainsAreRegistered() {
        assertEquals(4, chainsByOrder.size());
    }

    @Test
    void adminPathUsesFirstChain() {
        assertEquals(0, firstMatch("/api/admin"));
        assertEquals(0, firstMatch("/api/admin/report"));
    }

    @Test
    void normalApiPathsUseSecondChain() {
        assertEquals(1, firstMatch("/api"));
        assertEquals(1, firstMatch("/api/ping"));
        assertEquals(1, firstMatch("/api/tenant/acme/items"));
        assertEquals(1, firstMatch("/api/v2/unreviewed"));
    }

    @Test
    void opsPathUsesThirdChain() {
        assertEquals(2, firstMatch("/ops"));
        assertEquals(2, firstMatch("/ops/status"));
    }

    @Test
    void pathsOutsideKnownFamiliesUseFallback() {
        assertEquals(3, firstMatch("/diagnostics/secret"));
        assertEquals(3, firstMatch("/api-admin/report"));
        assertEquals(3, firstMatch("/unlisted"));
    }

    @Test
    void everyRepresentativeRequestHasSomeChain() {
        for (String path : List.of(
                "/api/admin/report",
                "/api/tenant/acme/items",
                "/api/ping",
                "/ops/status",
                "/api/v2/unreviewed",
                "/diagnostics/secret",
                "/unlisted")) {
            assertTrue(firstMatch(path) >= 0, path);
        }
    }
}
~~~

Đây là **6 bài test** bổ sung. Tổng project mẫu có **25 @Test methods** (19 + 6). Test `exactlyFourChainsAreRegistered` yêu cầu code review khi ai đó bổ sung/loại bỏ một chain; test first-match phát hiện thứ tự admin và general bị đảo; test fallback phát hiện path chưa phủ.

**Không xem test danh sách 7–10 URL là chứng minh toán học về mọi URL byte-level encoding.** Bổ sung method, path, host và Gateway E2E coverage cho dự án thật.

## 10. Chạy project và quan sát HTTP

Trong thư mục project:

~~~bash
gradle test
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew test` trên Linux/macOS hoặc `gradlew.bat test` trên Windows. **Không có khẳng định Gradle đã được thực thi trong môi trường tạo bài này.** Kết quả kỳ vọng: 25 test methods kiểm security routing, permissions và representative coverage; compile/runtime vẫn cần được người học xác nhận.

Public API:

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Kỳ vọng **200 OK**, body:

~~~text
pong
~~~

Ops Basic chưa đăng nhập:

~~~bash
curl -i http://localhost:8080/ops/status
~~~

Kỳ vọng **401 Unauthorized** với Basic challenge theo Spring Security.

Ops Basic dùng **demo-only credentials**:

~~~bash
curl -i -u operator:local-demo-only \
  http://localhost:8080/ops/status
~~~

Kỳ vọng HTTP **200**, body:

~~~text
UP
~~~

Admin không Bearer:

~~~bash
curl -i http://localhost:8080/api/admin/report
~~~

Kỳ vọng **401 Unauthorized** với Bearer challenge.

~~~bash
curl -i http://localhost:8080/diagnostics/secret
~~~

Kỳ vọng **4xx**, không được trả body `SHOULD_NOT_BE_EXPOSED`. Đây là một handler có thật để xác nhận catch-all hoạt động.

### 10.1. JWT runtime cần issuer/JWKS thật

`application.yml` dùng hostname ví dụ, nên không có access token thật được cung cấp. Đừng thử `Authorization: Bearer tenant-token` rồi kỳ vọng 200 vì đó là token string chỉ được mock decoder trong test chấp nhận.

Trong staging, cấu hình issuer/JWKS tin cậy và lấy access token có `aud=multi-tenant-api` cùng scope đúng, sau đó gọi:

~~~bash
curl -i https://api-staging.example.test/api/tenant/acme/items \
  -H 'Authorization: Bearer <valid-staging-access-token>'
~~~

Đây là lệnh mẫu; không có credential thật. Không lưu Bearer token production trong logs, ticket hoặc source control.

## 11. CORS, CSRF và các cơ chế xác thực khác nhau

### 11.1. CSRF không giống API authentication

Trong demo:
- Admin/General JWT chains chỉ nhận Bearer header do client chủ động gửi, nên tắt CSRF theo giả định **không có ambient browser credentials**.
- Ops Basic chain giữ CSRF default; Basic được browser nhớ có thể tạo CSRF risk nếu thêm unsafe methods.
- Catch-all chain chỉ deny và không cần disable CSRF.

Nếu application kết hợp OAuth2 Login/WebSession/cookie và JWT Resource Server, phải threat-model riêng từng chain. Không áp một lệnh `csrf(disable)` toàn cục vô điều kiện.

### 11.2. CORS preflight không mang JWT

Browser SPA gọi API khác origin thường gửi:

~~~http
OPTIONS /api/tenant/acme/items HTTP/1.1
Origin: https://frontend.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thường **không** kèm access token. Cấu hình WebFlux CORS trước auth theo tài liệu, allowlist origins/methods/headers và kiểm actual GET vẫn phải xác minh JWT. Không dùng `permitAll OPTIONS /**` thay cho CORS policy; CORS cũng không ngăn curl/non-browser clients.

### 11.3. permitAll vẫn có thể chạy authentication filters

`GET /api/ping` được `permitAll()`, nên anonymous request 200. Nhưng nếu client gửi `Authorization: Bearer bad-token`, JWT filter của general chain có thể xác thực thất bại và trả 401 trước authorization decision. Public route trong một JWT chain **không đồng nghĩa bỏ hoàn toàn security filters**.

Nếu sản phẩm cần bỏ Bearer parsing riêng cho một public endpoint, cân nhắc public-only chain được match sớm với phạm vi cực hẹp, kiểm method và catch-all; không mở rộng một public matcher bao trùm các route khác.

## 12. Multi-tenancy: chain selector không phải tenant selector

Một `/api/**` chain thường đủ cho nhiều tenants cùng cơ chế JWT. Không cần tạo hàng nghìn `SecurityWebFilterChain` cho mỗi tenant. Việc xác minh identity và authorization vẫn có thể theo:
- Issuer/audience/algorithm/key policy.
- Scope/role.
- Entitlements nhiều tenant.
- Resource ownership.
- Database scoping.
- Rate limits/quotas per tenant và audit.

Khi mỗi tenant có issuer/JWKS riêng, Spring Security Reactive có `JwtIssuerReactiveAuthenticationManagerResolver` để xử lý nhiều trusted issuers. **Không tự load JWKS từ issuer URL tùy ý trong JWT chưa verify hoặc từ `X-Tenant` header.** Chỉ tin issuer allowlist và kiểm audience riêng của API.

Nếu Admin và Tenant là hai logical resource servers độc lập, có thể dùng audiences như `admin-api` và `tenant-api` với validators/decoders khác nhau. Project mẫu dùng một audience `multi-tenant-api` để tập trung vào chain coverage; không có nghĩa mọi miền production phải chia sẻ audience hoặc mọi admin token có quyền tenant.

### 12.1. Gateway có thể rewrite URL

Ví dụ:

~~~text
https://admin.example.test/reports
          -> gateway -> /api/admin/report

https://tenant.example.test/acme/items
          -> gateway -> /api/tenant/acme/items
~~~

Security matcher trong ứng dụng thường nhìn path **sau rewrite**, không nhất thiết thấy original external URL. Nếu Gateway đổi path normalization, tenantId, route prefix, forwarded host hoặc method, tests chỉ chạy trực tiếp WebTestClient không thể chứng minh chính sách edge đã đúng.

Đừng tin `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto` hay `X-Tenant` do caller tự đưa vào làm role. Gắn identity/tenant từ credential đã verify và chính sách application.

## 13. Ranh giới URL: roots, prefix, case và encoding

Những biến thể cần review/test ở production:
- `/api/admin` và `/api/admin/`.
- `/api` và `/api/`.
- `/api-admin/report`: **khác** prefix `/api/**`.
- `/api//admin/report`: double slash/normalization.
- `/api/%61dmin/report`: encoded characters.
- `/API/admin/report`: case sensitivity.
- Semicolons/path parameters.
- HTTP methods GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE.
- Gateway path rewrite, contextPath, forwarded host.
- Functional routes, GraphQL/WebSocket/management port ngoài annotated controller.

Dùng `ServerWebExchangeMatchers.pathMatchers(...)` hoặc `PathPatternParserServerWebExchangeMatcher`, không tự viết `request.getPath().toString().startsWith("/api")` rồi suy đoán prefix boundaries. Giữ `ServerWebExchangeFirewall` và thử các variant qua gateway thật; một số URL sẽ bị firewall reject 400, một số có thể normalize khác nhau.

**Đừng vô hiệu firewall để “sửa” một test encoded path**, vì có thể mở bypass qua các tầng xử lý URI không thống nhất.

## 14. HTTP status không đủ chứng minh chain đúng

| Kết quả | Có thể nghĩa là | Phải kiểm thêm |
| --- | --- | --- |
| 200 | Handler chạy và response thành công | Có đúng chain, đúng scope, tenant/ownership không |
| 401 | Missing/invalid authentication | JWT Bearer hay Basic challenge, decoder/issuer |
| 403 | Không đủ quyền, denyAll hoặc CSRF | Có đúng chain không, quyền nào thiếu |
| 404 | Handler không tồn tại hoặc hide existence | **Không chứng minh có security coverage** |
| 405 | HTTP method không có handler | Có security filter nào chạy trước không |
| 400 | Request malformed hoặc firewall reject | URI encoding/normalization/network |
| TLS failure | Chưa tới HTTP request | Gateway/client certificates/transport |

Một request trả 403 có thể là **generic fallback denyAll**, dù bạn muốn Admin chain. Vì vậy, test `firstMatch(...)` là phần bắt buộc cho hệ thống nhạy cảm; còn test HTTP phải có positive và negative rules để kiểm tác động thật.

### 14.1. Dấu hiệu auth scheme sai

- Admin Bearer API missing token thường trả `WWW-Authenticate: Bearer`.
- Ops Basic missing credentials thường trả `WWW-Authenticate: Basic`.

Nếu Admin route không token lại nhận Basic challenge, điều tra `securityMatcher`/`@Order` và gateway rewrite trước khi đổi controller. Header cũng không chứng minh đầy đủ tenant/object authorization.

## 15. Các lỗi phổ biến

| Lỗi | Tác động | Cách phòng |
| --- | --- | --- |
| Generic /api/** chain đứng trước /api/admin/** | Admin policy không chạy | Đặt matcher hẹp trước |
| Tưởng anyExchange denyAll áp mọi URL của app | Route ngoài matcher thiếu filters | Catch-all chain cuối |
| Thiếu fallback match-all | Route mới có thể public | Catch-all denyAll, test handler thật |
| Catch-all permitAll | Mọi route ngoài prefix mở | Fallback denyAll |
| Hai chain không có @Order rõ | Priority khó review | Đặt priorities riêng, test order |
| Chỉ test 403 cho admin | Generic denyAll cũng có thể 403 | Test first-match trực tiếp |
| Chỉ test URL không có controller | 404 không chứng minh security | Mapped sentinel endpoint |
| Không test /api root | Root path có thể bị xử lý khác | Root matchers + negative test |
| Không test POST/OPTIONS | Method khác bị hở hoặc SPA lỗi | Test methods + CORS config |
| Tenant chỉ dựa trên path | Cross-tenant data leakage | Verified identity + ownership |
| Tin X-Tenant/Host từ request | Caller impersonation tenant | Trusted claims/membership |
| Chấp nhận JWT wrong aud | Token của API khác dùng chéo | Issuer/audience validators |
| Dùng ID token thay access token | Token substitution | Resource-server access token |
| Basic auth áp toàn API | Ops credentials mở rộng | Auth mechanism tách chain |
| Disable CSRF cho browser cookie/Basic | CSRF risk | Policy theo credential type |
| Tự parse JWT payload thành role | Privilege escalation | ReactiveJwtDecoder + validators |
| Bỏ Gateway E2E tests | Rewrite thay đổi matcher | Test external→internal routes |
| Sử dụng mockJwt làm chứng minh chữ ký | Validation chưa được test | Signed JWT/JWKS integration |
| block() trong event loop | Chặn Reactive pipeline | Mono/Flux và Reactor context |

## 16. Troubleshooting với hệ thống Gateway và tenant

### 16.1. Admin route trả 200 cho token chỉ tenant.read

Kiểm:
1. `adminApi` có priority cao hơn `generalApi` không?
2. Admin path sau proxy rewrite có còn là `/api/admin/report`?
3. General chain có đặt `authenticated()` quá rộng không?
4. JWT test có vô tình chứa cả admin.read và tenant.read?
5. Có custom `ReactiveAuthorizationManager` cho phép từ nguồn không tin cậy?
6. Controller có bypass authorization bằng một route alias khác?
7. Matcher-level test có fail không?

Không chữa bằng cách chỉ sửa status/body 403 nếu chain selection vẫn sai.

### 16.2. /diagnostics/secret trả 200 ngoài auth

Kiểm fallback bean còn tồn tại, không bị profile/conditional config tắt; có `anyExchange().denyAll()`; không có public chain match-all ưu tiên cao hơn. Kiểm direct backend ingress và management port khác. Thêm handler sentinel có thật để test, không chỉ kiểm 404.

### 16.3. /ops/status không nhận Basic

Kiểm `@Order(3)`, matcher `/ops/**`, HTTP Basic enabled, user details service và password encoder. Nếu response có Bearer challenge, có thể một JWT chain match nhầm Ops trước. Không mở Basic trên mọi URL để sửa.

### 16.4. JWT hợp lệ nhưng tenant Items 403

Phân loại:
- JWT không có `SCOPE_tenant.read`.
- `tenant_id` khác path tenant.
- User membership bị revoke.
- Data/object ownership deny.
- Query được scope theo tenant khác.
- Token audience/issuer sai: thường là 401 trước khi đến controller.
- Proxy rewrite biến `/api/tenant/acme` thành path của beta.

Giữ tenant policy; sửa identity mapping hoặc authorization grants thay vì tắt kiểm ownership.

### 16.5. SPA preflight OPTIONS 401

Đừng cố gắn token vào CORS preflight. Cấu hình `CorsWebFilter`/WebFlux CORS thích hợp cho allowed origins/methods/headers và xử lý trước authentication. Actual API request vẫn phải có access token và quyền.

## 17. Coverage là một security contract của CI

Trong repo thật nên có route inventory:
- External host/path/method.
- Internal path sau Gateway rewrite.
- Expected first matching chain.
- Authentication scheme (JWT, Basic, OIDC, mTLS).
- Trusted issuer/audience/algorithms.
- Required scopes/roles.
- Tenant membership/object ownership check.
- Anonymous/invalid/valid-but-unauthorized expected status.
- CORS/CSRF expectation.
- Responsible owner và test case ID.

Mỗi khi thêm một `@GetMapping`, `RouterFunction`, Actuator endpoint, REST version mới hoặc Proxy route:
1. Cập nhật inventory.
2. Chạy ChainCoverageTest trực tiếp.
3. Chạy HTTP positive/negative WebTestClient.
4. Chạy JWT signed-token/issuer/audience integration test khi đổi security mechanism.
5. Chạy Gateway E2E với external paths và forwarded headers.
6. Kiểm client credential isolation và tenant boundaries.
7. Kiểm methods/trailing slash/encoded variants.
8. Chặn deploy nếu một handler nhạy cảm nằm ngoài mọi chain hoặc không có policy.

**Không cần mỗi tenant một security chain.** Với nhiều tenants cùng JWT framework, một chain + chính sách tenant/ownership ở service thường hợp lý hơn. Với nhiều issuers, dùng trusted-issuer resolution, không sinh decoder tùy ý từ unverified claims.

## 18. Checklist review production

### Chain routing
- [ ] Mỗi SecurityWebFilterChain có @Order rõ và khác nhau.
- [ ] Admin matcher hẹp chạy trước generic API matcher.
- [ ] Có chain cuối match-all `denyAll()`.
- [ ] Không có fallback permitAll.
- [ ] Mọi handler public được allow bằng rule chính xác theo method/path.
- [ ] Handler chưa review bị deny ngay cả khi tồn tại.
- [ ] Root, trailing slash, prefix boundary, encoding đã được thử.
- [ ] WebFlux.fn, management port, actuator, WebSocket/GraphQL inventory được review.

### Authentication và authorization
- [ ] JWT issuer/JWKS/audience/expiration/signature policy được xác minh.
- [ ] Admin scope khác Tenant scope; Basic không mở JWT route.
- [ ] Ops Basic chỉ ở miền nội bộ được bảo vệ bởi TLS/mTLS/network policy.
- [ ] Tenant claim/membership được so với requested tenant và resource owner.
- [ ] Không coi X-Tenant/X-Forwarded-Host là identity proof.
- [ ] Role/authority được map từ claims đáng tin hoặc entitlement service.
- [ ] Không đặt token raw/PII vào logs hoặc error bodies.

### Browser/gateway
- [ ] CORS preflight hoạt động; request thật vẫn yêu cầu authorization.
- [ ] CSRF policy phù hợp từng auth scheme, đặc biệt Basic và cookie.
- [ ] Proxy rewrites được kiểm E2E, không chỉ direct WebTestClient.
- [ ] Direct backend ingress/alternate ports không bypass trust boundary.
- [ ] Gateway kiểm certificates/headers đúng contract nếu dùng mTLS.

### Tests
- [ ] First-match order được kiểm qua SecurityWebFilterChain.matches().
- [ ] WebTestClient kiểm 200/401/403 cho mỗi miền.
- [ ] Test token thiếu scope và tenant mismatch.
- [ ] Test mapped sentinel trong fallback không được 2xx.
- [ ] Test API version/method mới bị deny.
- [ ] Test wrong scheme: Basic→Admin, Bearer→Ops.
- [ ] Test JWT thật với signature, issuer, audience, expiry riêng.
- [ ] Test Gateway rewrite và edge cases.

## 19. Câu hỏi ôn tập

**1. securityMatcher khác pathMatchers thế nào?**

> securityMatcher chọn SecurityWebFilterChain cho request; pathMatchers trong authorizeExchange chọn authorization rule trong chuỗi đã chọn.

**2. Hai chains cùng match một URL thì chain nào chạy?**

> Chuỗi được xét trước theo @Order và có matches(exchange)=true; các chuỗi sau không được cộng dồn.

**3. Tại sao /api/admin/** cần đứng trước /api/**?**

> Vì matcher rộng có thể che matcher admin hẹp và khiến admin không áp policy mạnh hơn.

**4. anyExchange().denyAll() trong Admin chain bảo vệ /diagnostics/secret không?**

> Không. Nó chỉ áp dụng cho request đã vào admin chain.

**5. Làm sao tránh URL mới nằm ngoài mọi security chain?**

> Có catch-all match-all cuối cùng với denyAll và test controller sentinel thật.

**6. Một 403 có chứng minh đã chọn đúng chain không?**

> Không. Generic denyAll cũng có thể trả 403; cần matcher-level test.

**7. Một 404 có chứng minh endpoint được bảo vệ không?**

> Không. Nó có thể chỉ do controller không tồn tại.

**8. JWT tenant.read có quyền đọc mọi tenant?**

> Không. Cần kiểm membership và object ownership ở domain layer.

**9. Vì sao permitAll /api/ping vẫn có thể 401 với Bearer invalid?**

> Authentication filter của chain vẫn có thể chạy trước authorization rule permitAll.

**10. Vì sao Basic OPS không mở JWT Admin?**

> Authentication mechanism được cấu hình riêng theo chain/matcher, JWT Admin không bật Basic.

**11. Trong ChainCoverageTest, matches(exchange) trả Mono gì?**

> SecurityWebFilterChain.matches trả Mono<Boolean>, không phải Mono<MatchResult> của ServerWebExchangeMatcher.

**12. Có nên disable CSRF toàn app vì một JWT API không?**

> Không. Basic/browser cookie/OIDC session routes có threat model khác.

**13. Vì sao Gateway rewrite ảnh hưởng coverage?**

> Matcher nhìn internal path thực tế mà app nhận, có thể khác external URL.

**14. mockJwt hoặc @MockitoBean decoder chứng minh signature/issuer/audience không?**

> Không. Cần test decoder thật với signed JWT/JWKS và negative fixtures.

**15. Có nên tạo một SecurityWebFilterChain cho mỗi tenant trong DB không?**

> Thường không nếu auth scheme giống nhau. Dùng tenant policy ở service; chỉ tách chains khi trust/auth behavior thực sự khác.

**16. Đâu là ba lớp test cần dùng?**

> Matcher first-match, HTTP WebTestClient authorization, và E2E Gateway/real token validation.

## 20. Tổng kết

Nhiều chuỗi Spring Security WebFlux giúp tách các miền API nhưng **không tự chứng minh chúng bao phủ mọi URL**. Một thiết kế chắc chắn gồm:

~~~text
Incoming request
     |
     v
@Order(1) /api/admin, /api/admin/** ?
       YES -> Admin JWT + admin scope
       NO
     v
@Order(2) /api, /api/** ?
       YES -> Tenant JWT / exact public GET / deny unreviewed
       NO
     v
@Order(3) /ops, /ops/** ?
       YES -> Ops HTTP Basic + ROLE_OPS
       NO
     v
@Order(99) match-all fallback
       -> denyAll
~~~

Ba nguyên tắc cần giữ:
1. **First-match wins:** matcher hẹp ưu tiên trước rộng và @Order được test.
2. **Fail closed:** `anyExchange().denyAll()` trong mỗi chain và một catch-all cuối cùng; route chưa review không tự public.
3. **Kiểm vùng bao phủ + quyền thực tế:** test `SecurityWebFilterChain.matches(ServerWebExchange)`, HTTP auth/status, tenant/object ownership và E2E Gateway rewrite.

Ví dụ có **25 bài test** theo hai lớp HTTP và matcher, nhưng JWT decoder ở HTTP test đã được mock nên chưa chứng minh chữ ký/issuer/audience thật. Không tuyên bố đã chạy Gradle: cần thực thi build/tests và staging E2E trước khi triển khai.

### Tài liệu tham khảo chính thức

- Spring Security 6.5 — WebFlux Security / Multiple Chains Support: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Reactive Resource Server Multitenancy: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html
- Spring Security 6.5 — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security 6.5 — Testing Reactive OAuth2/JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security 6.5 — Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — Reactive CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 — Reactive CORS: https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html
- Spring Security API — SecurityWebFilterChain: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/SecurityWebFilterChain.html
- Spring Security API — ServerWebExchangeMatchers: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html
- Spring Security API — ServerHttpSecurity: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Boot 3.5 — Security Reference: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725