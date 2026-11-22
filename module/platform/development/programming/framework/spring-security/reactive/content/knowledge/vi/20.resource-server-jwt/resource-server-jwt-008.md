# Chuyển đổi JWT thành Authentication bằng bộ chuyển đổi reactive

## 1. Tổng quan bài học

Trong Spring Security WebFlux, Resource Server nhận request có header `Authorization: Bearer <access-token>`. Khi access token là JWT, hệ thống phải làm hai việc khác nhau:

1. **Xác minh token**: kiểm chữ ký JWS bằng public key tin cậy, thuật toán, issuer (`iss`), audience (`aud`), thời hạn (`exp`), thời điểm bắt đầu (`nbf`) và profile token khi cần. Đây là trách nhiệm của `ReactiveJwtDecoder` và JWT validators.
2. **Chuyển JWT hợp lệ thành Authentication**: tạo tên principal, các `GrantedAuthority` và `AbstractAuthenticationToken` cho Spring Security. Đây là trách nhiệm của **reactive JWT authentication converter**.

Giả sử access token đã được issuer tin cậy ký và có claims:

~~~json
{
  "iss": "https://issuer.example.test/realms/lab",
  "sub": "alice-sub",
  "aud": ["report-api"],
  "scope": "report.read profile",
  "app_roles": ["AUDITOR"],
  "preferred_username": "alice"
}
~~~

Mục tiêu:
- `Authentication.getName()` là `alice-sub`, không phụ thuộc username hay email có thể đổi.
- Scope `report.read` thành authority `SCOPE_report.read`.
- Role `AUDITOR` từ claim đã được xác minh, khi được policy cho phép, thành `ROLE_AUDITOR`.
- Role `ADMIN` **không tự** thành `ROLE_ADMIN` nếu Resource Server không cho phép mapping ấy.
- `GET /api/reports` đòi `SCOPE_report.read`; `GET /api/audit` đòi `ROLE_AUDITOR`.
- JWT có quyền chung vẫn phải chịu kiểm tra ownership/tenant khi truy cập tài nguyên cụ thể.

**Trọng tâm:** Reactive converter phải được đặt sau decoder; nó không phải cách bỏ qua việc xác minh JWT và không thể biến claim do client tự khai thành quyền tin cậy.

### Kết quả học tập

Sau bài này bạn có thể:
1. Giải thích `JwtReactiveAuthenticationManager`, `ReactiveJwtDecoder`, `JwtAuthenticationToken`, `ReactiveSecurityContextHolder`.
2. Dùng `ReactiveJwtAuthenticationConverter` và cấu hình `jwtAuthenticationConverter(...)` trong `ServerHttpSecurity`.
3. Phân biệt `JwtAuthenticationConverter` đồng bộ với `ReactiveJwtAuthenticationConverterAdapter`.
4. Hiểu kiểu `Converter<Jwt, Mono<AbstractAuthenticationToken>>` và `Converter<Jwt, Flux<GrantedAuthority>>`.
5. Kết hợp scopes mặc định với custom role claims an toàn, không đánh mất authorities có sẵn.
6. Xây converter nonblocking có thể compose với R2DBC/WebClient để tra quyền nội bộ.
7. Tách authentication, HTTP authorization và object/tenant authorization.
8. Viết project Java 17+ Spring Boot WebFlux với mã và Gradle đầy đủ.
9. Viết `StepVerifier` unit test cho converter và `WebTestClient` integration tests với JWT RSA ký thật.
10. Phân biệt test `mockJwt()` chỉ mô phỏng Authentication với test thực sự chạy decoder và converter.

## 2. JWT đi qua các tầng reactive security như thế nào?

~~~text
Client
  │ GET /api/reports
  │ Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
  ▼
Spring Security WebFilterChain
  │
  ├─ Trích Bearer access token
  ▼
JwtReactiveAuthenticationManager
  │
  ├─ ReactiveJwtDecoder.decode(rawToken)
  │    ├─ Parse JWT/JWS
  │    ├─ Verify chữ ký bằng trusted public key/JWKS
  │    ├─ Kiểm exp/nbf/iss/aud, thuật toán
  │    └─ Mono<Jwt> đáng tin cho API
  ▼
Converter<Jwt, Mono<AbstractAuthenticationToken>>
  │
  ├─ Lấy sub làm principal name
  ├─ Scope → SCOPE_report.read
  ├─ app_roles có allowlist → ROLE_AUDITOR
  └─ Tuỳ chọn: reactive DB entitlement lookup
  ▼
JwtAuthenticationToken
  │
  ▼
SecurityContext trong Reactor Context
  │
  ▼
authorizeExchange / ReactiveAuthorizationManager
  │
  ├─ JWT không hợp lệ/thiếu      → 401
  ├─ JWT hợp lệ nhưng thiếu quyền → 403
  └─ JWT và quyền phù hợp        → controller/service
~~~

Điều kiện quan trọng:
- Converter nhận **`Jwt` từ decoder** trong pipeline mặc định, không nhận raw token để tự Base64-decode.
- `JwtReactiveAuthenticationManager` làm việc theo `Mono`; converter không được tự `subscribe()` hay `block()`.
- `JwtAuthenticationToken` thường giữ principal kiểu `Jwt` và tên principal từ claim `sub`.
- `ReactiveSecurityContextHolder` lưu/đọc context theo Reactor, không dựa vào Servlet ThreadLocal.
- `GrantedAuthority` là các chuỗi quyền đã qua mapping. Chúng không thay thế quyền truy cập vào resource ID/tenant cụ thể.

### 2.1. Ranh giới giữa xác minh và mapping

| Bước | Nhiệm vụ | Thành phần |
| --- | --- | --- |
| Verify JWS | Chữ ký đúng, key/alg trusted | `NimbusReactiveJwtDecoder` |
| Validate claims | Issuer, audience, time, token purpose | `OAuth2TokenValidator<Jwt>` |
| Map Authentication | Subject name, scopes, roles, authorities | `ReactiveJwtAuthenticationConverter` |
| HTTP authorization | Route cần authority nào? | `authorizeExchange` |
| Object authorization | User có được thao tác đúng tài nguyên? | Service/DB/ACL |
| Audit | Actor ID, decision và trace ID đã lọc | Audit logging |

Sai lầm thường thấy:

~~~java
// PHẢN VÍ DỤ: payload JWT đọc được không có nghĩa đáng tin.
String payloadBase64 = bearerToken.split("\\.")[1];
// Decode và đọc app_roles để tạo ROLE_ADMIN
// mà KHÔNG verify signature, iss, aud, exp là sai.
~~~

JWT payload được Base64URL-encoded **không phải mã hóa bí mật**. Attacker có thể tạo claim bất kỳ. Mọi role phải xuất phát từ token được decoder xác minh và nguồn issuer có quyền cấp role đó.

## 3. Mặc định Spring Security tạo Authentication nào?

Cấu hình WebFlux thông dụng:

~~~java
return http
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()))
    .build();
~~~

Trong cấu hình Resource Server JWT phổ biến:
- `JwtAuthenticationToken` đại diện Authentication thành công.
- `getPrincipal()` là đối tượng `Jwt`.
- `getName()` mặc định là claim `sub`.
- `getAuthorities()` có các scopes trong `scope` hoặc `scp`, thêm prefix `SCOPE_`.

Ví dụ token có:

~~~json
{"sub":"user-42","scope":"report.read report.write"}
~~~

Kết quả thông dụng:

~~~text
Authentication: JwtAuthenticationToken
principal: Jwt (đã xác minh)
name: user-42
authorities:
  SCOPE_report.read
  SCOPE_report.write
~~~

Một rule đúng:

~~~java
.pathMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_report.read")
~~~

Một rule dễ nhầm:

~~~java
.hasRole("report.read")
~~~

`hasRole("report.read")` thường tìm `ROLE_report.read`, **khác** `SCOPE_report.read`. Khi chuyển scopes sang authorities, cần thống nhất prefix, matcher và tên quyền.

**Không** coi `Authentication.isAuthenticated()` là “được đọc mọi document”. Nó chỉ xác nhận authentication đã được chấp nhận; route/object permissions kiểm riêng.

## 4. Các API converter trong WebFlux

### 4.1. ReactiveJwtAuthenticationConverter trực tiếp

Spring Security 6.3.x có:

~~~java
ReactiveJwtAuthenticationConverter reactive =
    new ReactiveJwtAuthenticationConverter();
~~~

Nó implement:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>>
~~~

Có hai điểm cấu hình chính:
- `setPrincipalClaimName(String)`: claim sử dụng làm `Authentication.getName()`, default `sub`.
- `setJwtGrantedAuthoritiesConverter(Converter<Jwt, Flux<GrantedAuthority>>)`: cách trích authorities dưới dạng reactive publisher.

Ví dụ custom claim `permissions` chứa các permissions hợp lệ:

~~~java
JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERM_");

ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();

converter.setJwtGrantedAuthoritiesConverter(jwt ->
    Flux.fromIterable(permissions.convert(jwt)));
~~~

Đây là đoạn code **không độc lập**; cần imports và security config. Chú ý thay thế authorities converter như vậy có thể làm mất default scopes nếu không ghép streams.

### 4.2. ReactiveJwtAuthenticationConverterAdapter cho mapper đồng bộ

Khi project có sẵn `JwtAuthenticationConverter` kiểu đồng bộ:

~~~java
JwtAuthenticationConverter sync =
    new JwtAuthenticationConverter();

JwtGrantedAuthoritiesConverter permissionMapper =
    new JwtGrantedAuthoritiesConverter();
permissionMapper.setAuthoritiesClaimName("permissions");
permissionMapper.setAuthorityPrefix("PERM_");

sync.setJwtGrantedAuthoritiesConverter(permissionMapper);
sync.setPrincipalClaimName("sub");

Converter<Jwt, Mono<AbstractAuthenticationToken>> adapted =
    new ReactiveJwtAuthenticationConverterAdapter(sync);
~~~

Dùng trong WebFlux:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(adapted)))
~~~

Adapter chuyển **interface converter đồng bộ không blocking** sang interface reactive. Nó **không biến JDBC, HTTP blocking hoặc `Thread.sleep` thành I/O nonblocking**. Nếu converter cũ gọi database đồng bộ, cần thiết kế lại hoặc cô lập blocking I/O có kiểm soát, không giả định adapter tự làm việc đó.

### 4.3. Converter tùy biến hoàn toàn

Có thể tự viết:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>> custom =
    jwt -> Mono.just(jwt)
        .map(value -> new JwtAuthenticationToken(
            value,
            List.of(new SimpleGrantedAuthority("SCOPE_demo.read")),
            value.getSubject()));
~~~

**Đây chỉ là minh họa type signature**; cấp cố định một scope cho mọi JWT hợp lệ không phù hợp với nhiều hệ thống. Production cần map đúng scopes/roles và quyền nội bộ.

Custom converter cần:
- Trả `Mono<AbstractAuthenticationToken>`, không return token trực tiếp.
- Không tự `subscribe()`.
- Không gọi `block()` trong event loop.
- Không bỏ qua issuer/audience/signature validation, vốn là trách nhiệm của decoder.
- Không tự cấp `ROLE_ADMIN` trên lỗi lookup hoặc claim không hợp lệ.
- Nếu đổi `Authentication.getPrincipal()` sang custom local user, phải cập nhật các controller đang dùng `@AuthenticationPrincipal Jwt`.

## 5. Mapping scopes và roles an toàn

Giả sử JWT đã validated:

~~~json
{
  "scope":"report.read profile",
  "app_roles":["AUDITOR","REVIEWER"]
}
~~~

Demo sẽ tạo:

~~~text
SCOPE_report.read
SCOPE_profile
ROLE_AUDITOR
ROLE_REVIEWER
~~~

Ta không tự map mọi string thành authority:

| Claim | Policy | Authority |
| --- | --- | --- |
| `scope="report.read"` | Mapping chuẩn | `SCOPE_report.read` |
| `scope="profile"` | Mapping chuẩn | `SCOPE_profile` |
| `app_roles=["AUDITOR"]` | Allowlist | `ROLE_AUDITOR` |
| `app_roles=["REVIEWER"]` | Allowlist | `ROLE_REVIEWER` |
| `app_roles=["ADMIN"]` | Không có trong allowlist mẫu | Không cấp role |
| `app_roles=["ROLE_AUDITOR"]` | Không đúng giá trị được chấp nhận | Không cấp role |
| `email="admin@example.org"` | Dữ liệu hồ sơ | Không tự cấp quyền |
| `tenant_id="tenant-a"` | Tenant context đã validated | Không tự cấp quyền tenant-b |

### 5.1. Tại sao phải giữ scopes khi thêm roles?

Một custom authorities converter chỉ trả roles có thể vô tình loại bỏ `SCOPE_report.read` từ JWT. Khi đó endpoint bảo vệ bằng scope sẽ từ 200 thành 403 dù token có `scope=report.read`.

Nếu ứng dụng cần cả hai, hãy ghép kết quả `JwtGrantedAuthoritiesConverter` mặc định với roles đã map, rồi loại duplicate. Full implementation ở mục 6 dùng `Flux.concat(...).distinct(...)`.

### 5.2. Role không phải một claim toàn năng

Một trusted issuer có thể ký token chứa role, nhưng Resource Server vẫn cần quyết định:
- Issuer này có được **khẳng định** role AUDITOR không?
- Role có áp dụng cho toàn ứng dụng hay một tenant/organization cụ thể?
- Claim format là list hay string?
- Role có bị revoke sau khi JWT đã phát không?
- Role nội bộ có được kết hợp với token scope như điều kiện **giao nhau**, không phải quyền thay thế mọi scope?

Với một operation ghi dữ liệu:

~~~text
ALLOW_WRITE =
    JWT hợp lệ cho đúng API
AND SCOPE_report.write
AND local user ACTIVE
AND tenant membership hợp lệ
AND owner/editor permission trên report thực tế
~~~

Chỉ có `ROLE_AUDITOR` không bảo đảm được sửa mọi tài liệu, đặc biệt khi dữ liệu ở tenant khác.

### 5.3. Sai kiểu claim và chính sách fail-closed

Claim `app_roles` có thể bị thiếu hoặc sai kiểu:
- Thiếu role: không cấp role từ nguồn này.
- List có phần tử không phải string: không tự ép thành authority.
- Claim string thay vì list nhưng contract yêu cầu list: không cấp quyền; nếu format là điều kiện bắt buộc, đặt validator để reject token sớm.
- Role lạ: không cấp role cao hơn mặc định.
- Không tồn tại user trong local DB: tùy policy, từ chối thay vì tự tạo admin.
- DB unavailable: fail closed, không dùng `onErrorReturn(ROLE_ADMIN)`.

Một JWT signature hợp lệ chưa nói rằng mọi claim của nó đều có ý nghĩa quyền trong mọi resource server.

## 6. Project Java 17+ Spring Boot WebFlux

Dự án mẫu dùng Spring Boot **3.3.13**, Gradle 8.x, Java 17+ để nhất quán với Spring Security 6.3. Phiên bản cố định vì mục đích học; môi trường production cần dùng dòng Spring Boot/Security còn được hỗ trợ và kiểm thử nâng cấp.

Các API:
- `GET /health`: public.
- `GET /api/me`: JWT authentication hợp lệ, trả principal name và authorities dạng demo.
- `GET /api/reports`: cần `SCOPE_report.read`.
- `GET /api/audit`: cần `ROLE_AUDITOR`.
- `GET /api/admin`: cần `ROLE_ADMIN`; mapper cố ý không chấp nhận ADMIN.
- `anyExchange().denyAll()`: deny routes chưa cấu hình.

### 6.1. Cấu trúc

~~~text
webflux-jwt-reactive-auth/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── JwtReactiveApp.java
    │   │   ├── SecurityConfig.java
    │   │   └── ReportController.java
    │   └── resources/application.yml
    └── test/java/demo/
        └── JwtConverterTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-jwt-reactive-auth'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Resource Server starter kéo modules `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose` cần cho JWT. Không thêm `spring-boot-starter-web` Servlet nếu mục tiêu là reactive WebFlux.

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/lab
          jwk-set-uri: https://issuer.example.test/realms/lab/jwks
          audiences:
            - report-api
~~~

Đây là endpoint minh họa, chưa có IdP thật. Khi chạy với issuer production, thay bằng issuer và HTTPS JWKS URL đáng tin:
- `issuer-uri` kiểm `iss`.
- `jwk-set-uri` chỉ nguồn public keys được phê duyệt.
- `audiences` yêu cầu token dành cho `report-api`.
- Decoder có thể cần fetch JWKS/key rotation qua mạng; test offline dùng test decoder riêng.
- Không cho JWT header `jku` hoặc `x5u` tự chỉ URL lấy public key.
- Resource Server production **không cần private signing key**.

### 6.2. Main class

`src/main/java/demo/JwtReactiveApp.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtReactiveApp {
    public static void main(String[] args) {
        SpringApplication.run(JwtReactiveApp.class, args);
    }
}
~~~

### 6.3. SecurityConfig: scope + custom role converter

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    private static final Set<String> ALLOWED_ROLES =
        Set.of("AUDITOR", "REVIEWER");

    @Bean
    Converter<Jwt, Mono<AbstractAuthenticationToken>>
    jwtAuthenticationConverter() {

        JwtGrantedAuthoritiesConverter scopeMapper =
            new JwtGrantedAuthoritiesConverter();

        ReactiveJwtAuthenticationConverter reactive =
            new ReactiveJwtAuthenticationConverter();

        reactive.setJwtGrantedAuthoritiesConverter(jwt -> {
            Flux<GrantedAuthority> scopes =
                Flux.fromIterable(scopeMapper.convert(jwt));

            Object rawRoles = jwt.getClaims().get("app_roles");

            Flux<GrantedAuthority> roles =
                rawRoles instanceof List<?> values
                    ? Flux.fromIterable(values)
                        .ofType(String.class)
                        .filter(ALLOWED_ROLES::contains)
                        .map(role -> (GrantedAuthority)
                            new SimpleGrantedAuthority("ROLE_" + role))
                    : Flux.empty();

            return Flux.concat(scopes, roles)
                .distinct(GrantedAuthority::getAuthority);
        });

        reactive.setPrincipalClaimName("sub");
        return reactive;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            Converter<Jwt, Mono<AbstractAuthenticationToken>>
                jwtAuthenticationConverter) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_report.read")
                .pathMatchers(HttpMethod.GET, "/api/audit")
                    .hasAuthority("ROLE_AUDITOR")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("ROLE_ADMIN")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter)))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

**Phân tích cấu hình:**
1. `ReactiveJwtAuthenticationConverter` trả publisher đúng kiểu `Mono<AbstractAuthenticationToken>`.
2. `JwtGrantedAuthoritiesConverter` giữ scopes `SCOPE_*` mặc định.
3. `app_roles` chỉ được đọc nếu là `List<?>`. Những phần tử không phải string bị lọc; contract production nên có validator nếu cần reject sai kiểu.
4. `ALLOWED_ROLES` chặn ADMIN và chuỗi prefixed `ROLE_AUDITOR`; chỉ raw value AUDITOR/REVIEWER được chuyển thành authority.
5. `Flux.concat(...).distinct(...)` ghép scopes và roles mà không trùng tên.
6. `setPrincipalClaimName("sub")` giữ định danh tương đối ổn định trong issuer namespace.
7. `jwtAuthenticationConverter(...)` phải được đăng ký vào đúng JWT DSL của WebFlux chain.
8. `httpBasic` và `formLogin` tắt vì demo dùng Bearer-only. Đừng dùng username/password/cookie để giả JWT.
9. Bài demo chỉ có GET nên không cần tắt CSRF; khi thêm unsafe methods, xem xét CSRF theo ambient browser credentials.
10. `ROLE_ADMIN` route không có token nào được map qua custom role allowlist trong bài. Ở production, quyền admin cần role model được quản trị.
11. Không gọi `block()` hoặc tự `subscribe()` bên trong security config.
12. Multi-tenant/object authorization không được giải quyết chỉ bằng role.

### 6.4. Controller đọc SecurityContext đúng cách

`src/main/java/demo/ReportController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class ReportController {

    public record IdentityView(
        String name, String subject, List<String> authorities) {}

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/me")
    Mono<IdentityView> me(@AuthenticationPrincipal Jwt jwt) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> new IdentityView(
                context.getAuthentication().getName(),
                jwt.getSubject(),
                context.getAuthentication().getAuthorities()
                    .stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList()
            ));
    }

    @GetMapping("/api/reports")
    Mono<Map<String, String>> reports() {
        return Mono.just(Map.of("result", "report.read allowed"));
    }

    @GetMapping("/api/audit")
    Mono<Map<String, String>> audit() {
        return Mono.just(Map.of("result", "ROLE_AUDITOR allowed"));
    }

    @GetMapping("/api/admin")
    Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("result", "ROLE_ADMIN allowed"));
    }
}
~~~

Vì Authentication vẫn là `JwtAuthenticationToken`, `@AuthenticationPrincipal Jwt` có thể được Spring Security WebFlux cung cấp. `ReactiveSecurityContextHolder` đọc Authentication theo Reactor Context, không dùng ThreadLocal Servlet.

**`/api/me` chỉ dành cho bài học**; không public dump token, raw `Authorization`, private key hay toàn bộ claims nhạy cảm. Trong sản phẩm thật, permissions có thể nhạy cảm và không nên trả nguyên danh sách nếu không cần.

## 7. Bộ kiểm thử: StepVerifier + JWT ký RSA thật + WebTestClient

Có ba mức kiểm thử:

1. **Direct converter unit test**: tạo `Jwt` fixture rồi dùng `StepVerifier` kiểm `Mono<AbstractAuthenticationToken>`, tên principal và authorities. Nó kiểm conversion, **không** kiểm signature.
2. **Signed JWT integration tests**: tạo JWT JWS ký RSA bằng test-only private key; decoder `NimbusReactiveJwtDecoder` chỉ tin public RSA key tương ứng, kiểm issuer, audience, time; WebTestClient đi qua filters và converter thật.
3. **`mockJwt()` security test**: tạo Authentication/authorities giả cho authorization tests. Nó có thể bỏ qua decoder/converter; test này ghi rõ giới hạn.

### 7.1. File test đầy đủ

`src/test/java/demo/JwtConverterTests.java`:

~~~java
package demo;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(JwtConverterTests.OfflineKeys.class)
class JwtConverterTests {

    private static final String ISSUER =
        "https://issuer.example.test/realms/lab";

    @Autowired
    ApplicationContext context;

    @Autowired
    JwtEncoder jwtEncoder;

    @Autowired
    Converter<Jwt, Mono<AbstractAuthenticationToken>> mapping;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class OfflineKeys {

        @Bean
        KeyPair keyPair() {
            try {
                KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("RSA");
                generator.initialize(2048);
                return generator.generateKeyPair();
            }
            catch (GeneralSecurityException error) {
                throw new IllegalStateException(error);
            }
        }

        @Bean
        JwtEncoder jwtEncoder(KeyPair keys) {
            RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) keys.getPublic())
                .privateKey((RSAPrivateKey) keys.getPrivate())
                .keyID("test-key")
                .build();

            return new NimbusJwtEncoder(
                new ImmutableJWKSet<SecurityContext>(
                    new JWKSet(jwk)));
        }

        @Bean
        ReactiveJwtDecoder jwtDecoder(KeyPair keys) {
            NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withPublicKey(
                    (RSAPublicKey) keys.getPublic())
                    .build();

            OAuth2TokenValidator<Jwt> audience =
                jwt -> jwt.getAudience() != null
                    && jwt.getAudience().contains("report-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                "invalid_token",
                                "Missing report-api audience",
                                null));

            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(
                        "https://issuer.example.test/realms/lab"),
                    audience));

            return decoder;
        }
    }

    private String signed(
            JwtEncoder signer,
            String issuer,
            String audience,
            String scope,
            List<String> roles,
            String username,
            Instant expiry) {

        Instant now = Instant.now();

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice-sub")
            .audience(List.of(audience))
            .issuedAt(now.minusSeconds(10))
            .notBefore(now.minusSeconds(10))
            .expiresAt(expiry)
            .claim("scope", scope)
            .claim("app_roles", roles)
            .claim("preferred_username", username)
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return signer.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private String valid(String scope, List<String> roles) {
        return signed(
            jwtEncoder, ISSUER, "report-api",
            scope, roles, "display-alice",
            Instant.now().plusSeconds(600));
    }

    @Test
    void directReactiveConverterMapsScopeAndRole() {
        // Unit test: fixture Jwt không có signature verification.
        Jwt jwt = Jwt.withTokenValue("test-only")
            .header("alg", "RS256")
            .claim("sub", "alice-sub")
            .claim("scope", "report.read")
            .claim("app_roles", List.of("AUDITOR"))
            .build();

        StepVerifier.create(mapping.convert(jwt))
            .assertNext(authentication -> {
                assertThat(authentication)
                    .isInstanceOf(JwtAuthenticationToken.class);
                assertThat(authentication.getName())
                    .isEqualTo("alice-sub");
                assertThat(authentication.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains("SCOPE_report.read", "ROLE_AUDITOR");
            })
            .verifyComplete();
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void protectedEndpointWithoutJwtIs401() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedJwtIs401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("not-a-jwt"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void signedJwtCreatesAuthenticationWithSubName() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(
                valid("report.read", List.of("AUDITOR"))))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice-sub")
            .jsonPath("$.subject").isEqualTo("alice-sub")
            .jsonPath("$.authorities").isArray();
    }

    @Test
    void preferredUsernameDoesNotOverridePrincipalName() {
        String token = signed(
            jwtEncoder, ISSUER, "report-api", "profile",
            List.of(), "pretend-admin",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice-sub");
    }

    @Test
    void reportReadScopeAllowsReading() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                valid("report.read profile", List.of())))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.result")
                .isEqualTo("report.read allowed");
    }

    @Test
    void missingReportReadScopeIs403() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                valid("profile", List.of("AUDITOR"))))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void auditorRoleAllowsAudit() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(
                valid("profile", List.of("AUDITOR"))))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.result")
                .isEqualTo("ROLE_AUDITOR allowed");
    }

    @Test
    void reviewerDoesNotHaveAuditorRole() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(
                valid("report.read", List.of("REVIEWER"))))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unapprovedAdminDoesNotGetRoleAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth(
                valid("report.read", List.of("ADMIN"))))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void rolePrefixStringCannotBypassAllowlist() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(
                valid("profile", List.of("ROLE_AUDITOR"))))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongIssuerIs401() {
        String token = signed(
            jwtEncoder, "https://evil.example", "report-api",
            "report.read", List.of("AUDITOR"), "alice",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIs401() {
        String token = signed(
            jwtEncoder, ISSUER, "other-api",
            "report.read", List.of("AUDITOR"), "alice",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredTokenIs401() {
        String token = signed(
            jwtEncoder, ISSUER, "report-api",
            "report.read", List.of("AUDITOR"), "alice",
            Instant.now().minusSeconds(600));

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongRsaSigningKeyIs401() {
        KeyPair other;
        try {
            KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            other = generator.generateKeyPair();
        }
        catch (GeneralSecurityException error) {
            throw new IllegalStateException(error);
        }

        RSAKey jwk = new RSAKey.Builder(
            (RSAPublicKey) other.getPublic())
            .privateKey((RSAPrivateKey) other.getPrivate())
            .keyID("test-key")
            .build();

        JwtEncoder wrongEncoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<SecurityContext>(
                new JWKSet(jwk)));

        String forged = signed(
            wrongEncoder, ISSUER, "report-api",
            "report.read", List.of("AUDITOR"), "alice",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(forged))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockJwtSkipsRealDecoderAndCustomRoleMapping() {
        // mockJwt chứa claim app_roles nhưng không chạy real
        // JWT authentication converter của resource server.
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim(
                    "app_roles", List.of("AUDITOR"))))
            .get().uri("/api/audit")
            .exchange()
            .expectStatus().isForbidden();

        // Mock được cấp sẵn authority để test route rule.
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("ROLE_AUDITOR")))
            .get().uri("/api/audit")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

### 7.2. Bộ test và kết quả kỳ vọng

| Test | Kỳ vọng |
| --- | --- |
| `directReactiveConverterMapsScopeAndRole` | `StepVerifier` xác nhận token, sub và 2 authorities |
| `healthIsPublic` | 200 |
| `protectedEndpointWithoutJwtIs401` | 401 |
| `malformedJwtIs401` | 401 |
| `signedJwtCreatesAuthenticationWithSubName` | 200, name = sub |
| `preferredUsernameDoesNotOverridePrincipalName` | 200, không lấy username |
| `reportReadScopeAllowsReading` | 200 |
| `missingReportReadScopeIs403` | 403 |
| `auditorRoleAllowsAudit` | 200 |
| `reviewerDoesNotHaveAuditorRole` | 403 |
| `unapprovedAdminDoesNotGetRoleAdmin` | 403 |
| `rolePrefixStringCannotBypassAllowlist` | 403 |
| `wrongIssuerIs401` | 401 |
| `wrongAudienceIs401` | 401 |
| `expiredTokenIs401` | 401 |
| `wrongRsaSigningKeyIs401` | 401 |
| `mockJwtSkipsRealDecoderAndCustomRoleMapping` | 403, rồi 200 với mock authority |

Có **17 phương thức test**. Các tests với Bearer string ký thật đi qua decoder và converter thật; test `mockJwt()` cố ý bỏ qua đường ấy. Direct `StepVerifier` test chỉ kiểm converter, không phải signature.

### 7.3. Chạy

~~~bash
gradle test
~~~

Nếu có Gradle Wrapper: `./gradlew test` trên Linux/macOS, hoặc `gradlew.bat test` trên Windows. Chưa có kết quả build thật trong bài viết; phải chạy trong môi trường Java/Gradle tương thích để xác nhận các tests pass. Tests dùng keypair test-only trong JVM, không cần IdP/JWKS ngoài sau khi đã tải dependencies.

Để chạy API với IdP thật:
1. Thay `issuer-uri`/`jwk-set-uri`/`audiences` bằng giá trị đã được phê duyệt.
2. Kiểm HTTPS/JWKS/issuer metadata và trusted certificates.
3. Chạy `gradle bootRun`.
4. Gọi public endpoint:

~~~bash
curl -i http://localhost:8080/health
~~~

5. Gọi protected endpoint không token thường nhận 401:

~~~bash
curl -i http://localhost:8080/api/reports
~~~

6. Gọi với access token thật được issuer cấp cho `report-api` và có scope `report.read`:

~~~bash
curl -i \
  -H "Authorization: Bearer ACCESS_TOKEN_FROM_TRUSTED_AS" \
  http://localhost:8080/api/reports
~~~

`ACCESS_TOKEN_FROM_TRUSTED_AS` chỉ là placeholder. Token test signed với keypair nội bộ không phải token production. Không ghi raw access token vào logs/screenshots và dùng HTTPS trong môi trường ngoài local.

## 8. Khi cần truy vấn database trong converter

Nếu quyền không nằm hoàn toàn trong JWT hoặc cần revoke nhanh, bạn có thể tra local user/tenant membership theo verified `(iss,sub)` bằng R2DBC, hoặc gọi entitlement service reactive.

**Đoạn sau là snippet kiến trúc**, không thuộc runnable project vì service implementation phụ thuộc DB/business cụ thể.

~~~java
interface ReactiveMembershipService {
    Mono<List<GrantedAuthority>> authoritiesFor(
        String verifiedIssuer, String verifiedSubject);
}

Converter<Jwt, Mono<AbstractAuthenticationToken>>
    lookupConverter(ReactiveMembershipService service) {

    return jwt -> service.authoritiesFor(
            jwt.getIssuer().toString(),
            jwt.getSubject())
        .switchIfEmpty(Mono.error(
            new BadCredentialsException(
                "Local identity not available")))
        .map(authorities -> new JwtAuthenticationToken(
            jwt, authorities, jwt.getSubject()));
}
~~~

Những lưu ý:
1. Chỉ gọi với Jwt đã được decoder validate; không tin `iss/sub` từ token tự parse.
2. Dùng cặp issuer+subject, không lookup bằng email.
3. Account disabled không được nhận quyền chỉ vì JWT chưa hết hạn.
4. DB error phải **fail closed**, không tự cấp quyền.
5. Không `block()` hoặc `subscribe()`; trả publisher cho security pipeline.
6. Lookup trên mọi request làm tăng latency và dependency vào DB; cân nhắc cache ngắn hạn và invalidation cho revoke.
7. Nếu JWT scope chỉ cho đọc, đừng biến DB role editor thành quyền ghi vượt scope. Kết hợp scope **và** local permissions.
8. Kiểm quyền object/tenant ở service/repository khi cần resourceId, không cố đưa tất cả object IDs vào Authentication.
9. Custom converter exception cần error handling rõ; không khẳng định mọi lỗi luôn trả 401 hoặc 403.

### 8.1. Anti-pattern blocking I/O

Sai:

~~~java
// PHẢN VÍ DỤ: blocking DB call ngay khi tạo Mono.
return jwt -> Mono.just(
    jdbcRepository.findRoles(jwt.getSubject())
).map(roles -> new JwtAuthenticationToken(jwt, roles));
~~~

`findRoles` chạy trước khi tạo Mono, có thể block event loop. Với legacy JDBC, nếu chưa thể thay bằng R2DBC, isolate rõ trên boundedElastic với capacity/timeout được kiểm soát; đừng coi đó là nonblocking I/O thật. Phương án lâu dài là service/reactive repository.

Sai:

~~~java
// PHẢN VÍ DỤ: subscribe tách tác vụ khỏi lifecycle request.
service.authoritiesFor(issuer, subject)
    .subscribe(roles -> cache.put(subject, roles));

return Mono.just(new JwtAuthenticationToken(jwt));
~~~

Framework phải chịu trách nhiệm subscribe; converter trả publisher chỉ hoàn thành khi các điều kiện xác thực cần thiết đã hoàn tất.

### 8.2. Account disabled và lỗi DB

Nếu local user bị khóa sau khi token phát, JWT có thể vẫn hợp lệ cryptographically. Converter chỉ đọc claims không biết điều đó. Cần:
- Short token TTL/revocation strategy.
- Tra user status/entitlements ở backend cho nghiệp vụ nhạy cảm.
- Cache và invalidate có kiểm soát.
- Fail-closed khi DB outage, nhưng phân biệt lỗi hạ tầng và lỗi quyền trong logs/metrics.
- Test race khi role bị revoke, account disabled, tenant bị tách.

## 9. Principal name và danh tính ổn định

`Authentication.getName()` mặc định lấy `sub` và có thể đổi:

~~~java
ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
~~~

Nhưng `preferred_username`, email hoặc name có thể đổi; không dùng làm ownership ID lâu dài. `sub` cũng chỉ unique trong namespace issuer. Ví dụ:

~~~text
(iss=https://issuer-a.example, sub=123) → User A
(iss=https://issuer-b.example, sub=123) → User B
~~~

Không hợp nhất hai user đó chỉ vì sub trùng. Hệ thống có local users nên lưu mapping `(verified iss, sub) → local UUID`. Business tables dùng local UUID cho ownership/foreign keys; scopes và roles không thay data authorization.

Với multi-issuer, không tạo decoder tùy ý từ một issuer do attacker khai trong JWT. Sử dụng trusted issuer allowlist và cấu hình public keys/algorithms/audience tương ứng, rồi mới convert authorities.

## 10. Kiểm soát role, scope và tenant

Một token có:
- `scope=report.read`, không có write.
- `app_roles=["AUDITOR"]`.
- `tenant_id=tenant-a`.

Không có nghĩa người dùng:
- Được ghi report vì có role AUDITOR.
- Được đọc dữ liệu tenant-b.
- Được tự cấp quyền admin.
- Được truy cập report thuộc một user khác.

Một policy an toàn cho update có thể là:

~~~text
ALLOW_UPDATE =
    JWT valid + đúng audience
AND SCOPE_report.write
AND local user ACTIVE
AND tenant membership ACTIVE
AND service kiểm editor/owner trên report cụ thể
~~~

Role claims có thể stale. Nếu quyền phải revoke ngay, chỉ tin JWT roles với TTL phù hợp là chưa đủ; cần kiểm lại permission server/DB hoặc revocation design.

## 11. Phân biệt lỗi trong security pipeline

| Kết quả | Nguyên nhân điển hình | Nơi kiểm |
| --- | --- | --- |
| **401** | Không có Bearer trên protected route | Authentication entry point |
| **401** | JWT malformed, signature sai | `ReactiveJwtDecoder` |
| **401** | Issuer/audience/time không đạt | JWT validators |
| **403** | JWT hợp lệ nhưng thiếu `SCOPE_report.read` | `authorizeExchange` |
| **403** | JWT hợp lệ nhưng thiếu `ROLE_AUDITOR` | Role mapping/authorization |
| **403/404** | Khác tenant/owner, theo policy | Resource authorization |
| **5xx hoặc status tùy handler** | Custom converter/entitlement service lỗi | Exception handling, DB/network |
| **200** | JWT valid, converter tạo authority cần thiết | Controller chạy |

Không đồng nhất mọi 403 với CSRF: có thể do authority, tenant, CORS hoặc policy khác.

### 11.1. Debug thiếu role

1. Xác nhận access token thật được issuer ký, audience đúng và còn hạn.
2. Kiểm JWT đã vào đúng `SecurityWebFilterChain` và converter đăng ký bằng `jwtAuthenticationConverter(...)`.
3. Kiểm tên claim: `app_roles` hay `roles`, `realm_access.roles`?
4. Kiểm kiểu claim: String, List, nested object?
5. Kiểm role nằm trong allowlist không.
6. Kiểm prefix `ROLE_`/`SCOPE_`/`PERM_`.
7. Kiểm route dùng `hasRole` hay `hasAuthority`.
8. Kiểm object-level/tenant rules.
9. Tránh chỉ test `mockJwt()`; chạy Bearer JWT signed thật.
10. Không log raw token, access token scopes/PII không cần thiết hoặc private key.

## 12. So sánh các converter

| Cách | Phù hợp | Hạn chế |
| --- | --- | --- |
| `JwtAuthenticationConverter` + `ReactiveJwtAuthenticationConverterAdapter` | Đã có mapper đồng bộ xử lý claims trong bộ nhớ | Adapter không giải quyết blocking JDBC |
| `ReactiveJwtAuthenticationConverter` | Mapping scopes/roles bằng Flux và set principal claim | Vẫn cần decoder/authorization độc lập |
| Tự viết `Converter<Jwt, Mono<AbstractAuthenticationToken>>` | Local principal/DB entitlement/WebClient reactive | Phức tạp, dễ fail-open hoặc tăng latency |

Chọn cách **đơn giản nhất vẫn đáp ứng policy**. Không viết converter mới nếu default scope mapping đã đủ.

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Tự Base64URL decode JWT để cấp role | Không verify signature | Dùng `ReactiveJwtDecoder` |
| Quên `aud` khi custom decoder | Nhận token dành cho API khác | Audience validator |
| Bỏ scopes khi thêm custom roles | `SCOPE_*` biến mất | Ghép default scopes và roles |
| Nhầm `ROLE_` với `SCOPE_` | Route 403 không mong muốn | Đồng bộ authority prefix |
| Role lạ tự thành ADMIN | Privilege escalation | Role allowlist/issuer trust |
| Mapper chấp nhận `ROLE_ADMIN` từ claim string | Prefix injection | Bám exact contract, không tin prefixed input |
| Email làm principal/owner | Có thể đổi/tái sử dụng | Verified `(iss,sub)` → local UUID |
| Blocking JDBC trong adapter | Chặn event loop | R2DBC/WebClient hoặc isolation rõ |
| Tự `subscribe()` | Race/lifecycle sai | Compose `Mono/Flux` |
| `onErrorReturn(ROLE_ADMIN)` | Fail-open khi DB lỗi | Fail closed |
| Chỉ dùng `mockJwt()` | Không chạy decoder/converter thật | Signed JWT integration tests |
| Quyền tenant chỉ dựa vào role | IDOR/BOLA | Resource-level owner/tenant checks |
| JWT roles cũ vẫn dùng sau revoke | Stale authorities | TTL/revocation/recheck |
| Dùng `HttpSecurity` của Servlet | Không đúng WebFlux | `ServerHttpSecurity` |
| Log toàn bộ JWT để debug | Lộ credentials/claims | Structured logs đã lọc |

## 14. Bài tập và đáp án

**Câu 1.** JWT có `scope=report.read report.export`. Converter mặc định tạo gì?

**Đáp án:** `SCOPE_report.read` và `SCOPE_report.export` nếu JWT đã validate và mapping default được giữ.

**Câu 2.** Vì sao `hasRole("report.read")` không khớp `SCOPE_report.read`?

**Đáp án:** `hasRole` thường yêu cầu `ROLE_report.read`, còn scopes có prefix `SCOPE_`.

**Câu 3.** JWT có `app_roles=["AUDITOR"]`, route cần `ROLE_AUDITOR`. Cần gì ngoài signature?

**Đáp án:** Issuer/audience/time đúng và converter policy cho phép map role AUDITOR.

**Câu 4.** JWT có `app_roles=["ADMIN"]` có tự trở thành `ROLE_ADMIN` không?

**Đáp án:** Không, demo chỉ whitelist AUDITOR/REVIEWER.

**Câu 5.** Vì sao mapper chỉ trả roles làm endpoint scope bị 403?

**Đáp án:** Default scope authorities bị mất. Ghép scopes+roles đúng.

**Câu 6.** JWT có chữ ký đúng nhưng sai audience thì converter có nên chạy?

**Đáp án:** Không; decoder phải từ chối token trước bước mapping.

**Câu 7.** Adapter có làm JDBC blocking thành nonblocking không?

**Đáp án:** Không; dùng reactive DB hoặc isolation được review.

**Câu 8.** Test `mockJwt().authorities(ROLE_AUDITOR)` có chứng minh role claim được map đúng không?

**Đáp án:** Không. Mock cấp authority trực tiếp, có thể bypass converter.

**Câu 9.** Khi cần test converter độc lập, dùng gì?

**Đáp án:** Tạo `Jwt` fixture, gọi converter và dùng `StepVerifier` để assert Authentication/authorities. Nó không kiểm signature.

**Câu 10.** Nếu JWT có sub giống từ hai issuer khác nhau, có thể coi là cùng người không?

**Đáp án:** Không; key là issuer+subject đã verified.

**Câu 11.** Converter làm DB lookup rồi trả `Mono.empty()` cho user chưa tồn tại, có rõ ràng không?

**Đáp án:** Không; nên định nghĩa failure/denial tường minh và test.

**Câu 12.** DB timeout có nên cấp role mặc định để tăng availability không?

**Đáp án:** Không nếu role đó mở quyền ngoài policy. Fail closed và xử lý lỗi hạ tầng đúng.

**Câu 13.** JWT có ROLE_AUDITOR trong tenant A có tự đọc được tenant B không?

**Đáp án:** Không; cần kiểm membership/owner của resource.

**Câu 14.** JWT valid nhưng account bị khóa trong local DB, converter đọc claims có tự biết không?

**Đáp án:** Không; cần revoke/TTL hoặc permission/account-status recheck.

**Câu 15.** Đổi principal claim sang email có đổi authorities không?

**Đáp án:** Không. Principal name và granted authorities là hai cấu hình khác nhau.

## 15. Checklist triển khai

- [ ] Resource Server chỉ dùng JWT sau signature, issuer, audience và time validation.
- [ ] Đúng OAuth2 access token dành cho API, không lấy ID Token thay.
- [ ] JWT converter gắn đúng `SecurityWebFilterChain` WebFlux.
- [ ] Default scopes `SCOPE_*` được giữ khi thêm roles.
- [ ] Chỉ map role values trong allowlist từ issuer đáng tin.
- [ ] Không auto-grant role từ email, username, header hoặc request body.
- [ ] Principal/owner ID dựa trên verified identity và local mapping ổn định.
- [ ] Ràng buộc tenant/resource owner được kiểm độc lập.
- [ ] Không blocking I/O, không tự `subscribe()`, không fail-open.
- [ ] Có cache/revocation/disabled user policy khi cần dynamic roles.
- [ ] Có unit test StepVerifier cho converter.
- [ ] Có integration tests Bearer RSA signed JWT cho decoder+mapping.
- [ ] Test 401 với token thiếu/sai signature/issuer/audience/expiry.
- [ ] Test 403 khi JWT hợp lệ thiếu scope/role/tenant permission.
- [ ] Test unknown role/prefix injection.
- [ ] Ghi rõ giới hạn test `mockJwt()`.
- [ ] Không log raw token, secrets hoặc private key.
- [ ] Test lại sau nâng version Spring Security.

## 16. Tài liệu tham khảo

- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.3 — ReactiveJwtAuthenticationConverter: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverter.html
- Spring Security 6.3 — ReactiveJwtAuthenticationConverterAdapter: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html
- Spring Security 6.3 — JwtReactiveAuthenticationManager: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html
- Spring Security — JWT testing with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot 3.3 — Resource Server Auto Configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 9068 — OAuth2 JWT Access Token Profile: https://www.rfc-editor.org/rfc/rfc9068
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Ghi nhớ:** `ReactiveJwtDecoder` xác minh JWT; **reactive JWT authentication converter** mới quyết định principal và authorities của JWT hợp lệ. Với WebFlux, dùng `ReactiveJwtAuthenticationConverter` cho scopes/roles, adapter cho converter đồng bộ không blocking, hoặc custom `Converter<Jwt, Mono<AbstractAuthenticationToken>>` khi cần tra quyền reactive. Luôn giữ các lớp signature/issuer/audience validation và resource/tenant authorization riêng biệt.
