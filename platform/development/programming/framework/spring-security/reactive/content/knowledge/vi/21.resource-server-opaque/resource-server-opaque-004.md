# ReactiveOpaqueTokenIntrospector và OAuth2AuthenticatedPrincipal — Spring Security Reactive

> **Bối cảnh:** Spring WebFlux, OAuth2 Resource Server xác minh opaque access token, Spring Security 6.x và Java 17+. Mốc code là Spring Boot 3.3.13/Spring Security 6.3.x để học API. Không giữ nguyên phiên bản cũ cho production; luôn dùng bản đang được hỗ trợ và đã nhận bản vá bảo mật.

## 1. Tại sao cần introspection?

Một client gọi API:

```http
GET /api/reports HTTP/1.1
Authorization: Bearer Sx7V-p9a8-kZ0...
Accept: application/json
```

Chuỗi `Sx7V-p9a8-kZ0...` chỉ là **bearer token**. Nếu đó là **opaque access token**, resource server không thể đọc chữ ký/claims trực tiếp để biết:

- Token còn **active** không, đã hết hạn hoặc bị thu hồi chưa?
- Token được cấp cho subject/client nào?
- Token có scope để đọc báo cáo không?
- Token có được dùng cho **đúng resource/audience** không?
- User thuộc tenant nào, được đọc bản ghi nào?

Thay vì tự đoán, Spring Security hỏi một nguồn tin cậy, thường là **OAuth2 Authorization Server introspection endpoint** theo RFC 7662.

```text
HTTP client                  Spring WebFlux Resource Server           Authorization Server
    |                                       |                              |
    | Authorization: Bearer opaque-value   |                              |
    |-------------------------------------->|                              |
    |                               Bearer authentication                  |
    |                                       |                              |
    |                           ReactiveOpaqueTokenIntrospector          |
    |                               introspect(token)                     |
    |                                       |---- POST /introspect ------->|
    |                                       |  client id + secret/other    |
    |                                       |<--- active, scope, sub, ... -|
    |                                       |                              |
    |                           OAuth2AuthenticatedPrincipal             |
    |                                       |                              |
    |                           BearerTokenAuthentication               |
    |                                       |                              |
    |                        authorizeExchange / method security         |
    |                                       |                              |
    |<----------------- 200 / 401 / 403 ----|                              |
```

**Nguyên tắc:** một `ReactiveOpaqueTokenIntrospector` trả principal thành công nghĩa là implementation đã **xác minh token**. Không được viết implementation trả `Mono.just(adminPrincipal)` cho mọi token hoặc khi AS timeout.

## 2. So sánh opaque introspection với JWT decoding

| Tiêu chí | Opaque Resource Server | JWT Resource Server |
|---|---|---|
| Token gửi từ client | Thường là chuỗi không tự mô tả | JWT được ký |
| Thành phần kiểm chứng | `ReactiveOpaqueTokenIntrospector` | `ReactiveJwtDecoder` |
| Tác vụ | Hỏi introspection endpoint hoặc token store đáng tin | Kiểm chữ ký, thời gian, issuer, validators |
| Có gọi mạng mỗi request? | Thường có, nếu không cache | Thường không, khi JWKS đã cache |
| Phát hiện revoke | Có thể nhanh khi AS phản hồi trạng thái mới | Cần biện pháp bổ sung cho JWT chưa hết hạn |
| Principal | `OAuth2AuthenticatedPrincipal` | `Jwt` |
| Authentication | `BearerTokenAuthentication` | `JwtAuthenticationToken` |
| Quyền mặc định | Introspection scope → `SCOPE_...` | JWT scope/scp → `SCOPE_...` khi converter phù hợp |
| Chi phí | Latency, availability AS, credential introspection | Signature verification, key rotation, validation |

Tên “opaque-token” nói lên **cơ chế xác minh của Resource Server**, không bắt buộc bearer token phải là chuỗi không có cấu trúc. Nếu chọn kiểm JWT qua introspection vì cần revoke, Spring Security vẫn có thể gửi chuỗi JWT đó cho AS và tin **response introspection**, không tự lấy JWT claims làm kết quả đã xác minh.

**Không gửi OIDC ID Token thay cho access token API.** ID Token dành cho client xác thực user, còn resource server cần access token đúng mục đích, scope và audience.

## 3. RFC 7662: Request và response mẫu

Introspection endpoint của Authorization Server thường được gọi bằng POST có body form-URL-encoded; resource server cũng xác thực chính mình theo cơ chế IdP cho phép, ví dụ HTTP Basic:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic <introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=Sx7V-p9a8-kZ0...
```

Khi token hợp lệ, một IdP có thể trả:

```json
{
  "active": true,
  "scope": "messages.read reports.read",
  "sub": "user-alice-42",
  "client_id": "portal-web",
  "token_type": "Bearer",
  "exp": 1980000000,
  "iat": 1979996400,
  "aud": ["reports-api"],
  "iss": "https://idp.example.com",
  "tenant_id": "north"
}
```

Khi token không hoạt động:

```json
{"active": false}
```

Các giá trị ở trên là **giả định minh họa**; không phải mọi provider trả đủ claims. Phân biệt:

- `active` xác nhận trạng thái mà AS biết tại thời điểm introspect. Nếu false thì **từ chối token**.
- `scope` thường là các scope ngăn bởi dấu cách. Introspector có thể chuyển nó sang danh sách nội bộ.
- `sub` xác định subject, không mặc định là email/username hoặc người dùng (client credentials có thể đại diện service).
- `client_id` trong response là client được cấp token; **không giống** client ID Resource Server sử dụng để được phép introspect.
- `aud` chỉ đích của access token. AS trả active=true không nhất thiết chứng minh token đúng audience của API hiện tại.
- `iss` là issuer; phải xác định nguồn tin cậy nếu dùng claim để phân quyền.
- `exp`, `nbf`, `iat` là thời gian khi được trả; kiểu được convert có thể khác chuỗi JSON gốc.
- `tenant_id`, `roles` là claims tùy chỉnh; chỉ tin khi AS hoặc entitlement backend đáng tin cấp.
- Credential introspection **không** được xuất qua response hay gửi đến downstream API.

Trong sản phẩm multi-tenant, cần kiểm chính sách audience/issuer/tenant/record-level ngoài việc token có active hay không.

## 4. ReactiveOpaqueTokenIntrospector: hợp đồng cốt lõi

Package:

```java
org.springframework.security.oauth2.server.resource.introspection
```

Signature rút gọn:

```java
@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

Đây là API của thư viện, **không tạo lại interface** trong source dự án.

### Input và output

`introspect(String token)` nhận raw bearer access token và trả `Mono<OAuth2AuthenticatedPrincipal>` chỉ sau khi verify thành công. Nó không đơn thuần decode một chuỗi.

- Token active được xác nhận → `Mono` phát một principal.
- Token invalid/revoked/expired → phát lỗi tương ứng, ví dụ `BadOpaqueTokenException`.
- AS down/network timeout → **fail closed**, không tạo principal tự động.
- Không trả “anonymous principal” từ introspector rồi để chain coi đó là login thành công.
- Không gọi `block()` bên trong WebFlux security pipeline.
- Nếu backend token store dùng JDBC/JPA đồng bộ, phải giới hạn blocking I/O qua scheduler/adapter; ưu tiên backend reactive.

### Một implementation cố tình không an toàn

```java
// PHẢN VÍ DỤ — TUYỆT ĐỐI KHÔNG DÙNG TRONG PRODUCTION.
@Bean
ReactiveOpaqueTokenIntrospector acceptEverything() {
    return token -> Mono.just(
        new DefaultOAuth2AuthenticatedPrincipal(
            "admin",
            Map.of("sub", "admin"),
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
}
```

Bất kỳ token nào, kể cả attacker gửi một chuỗi tự nghĩ ra, đều thành admin. Một stub introspector **chỉ dùng trong test context** có thể có allowlist token fixtures, nhưng không được đóng gói vào jar production.

## 5. Lựa chọn implementation theo phiên bản

Spring Security có một số implementation:

- `NimbusReactiveOpaqueTokenIntrospector` xuất hiện ở các phiên bản 6.x và có constructor `(introspectionUri, clientId, clientSecret)`; trong 6.5 bị đánh dấu deprecated.
- `SpringReactiveOpaqueTokenIntrospector` được Spring Security sử dụng làm implementation reactive. Nó tồn tại từ trước 6.5, có các constructor tương ứng.
- `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` là **builder từ 6.5**. **Không sao chép builder này vào Boot 3.3 / Spring Security 6.3** mà không nâng version.

Ví dụ cho **Spring Security 6.5+**, không phải file chạy của demo 3.3:

```java
ReactiveOpaqueTokenIntrospector introspector =
    SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
```

Trong dự án Boot 3.3 ở mục 9, cấu hình bằng **Spring Boot properties** để Boot tạo bean đúng implementation tương ứng thay vì gọi constructor/builder theo phiên bản. Khi nâng cấp, kiểm Javadoc chính xác của dependency, không suy từ trang docs “current”.

## 6. OAuth2AuthenticatedPrincipal là gì?

Package:

```java
org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal
```

Principal lưu **danh tính và thuộc tính đã được introspector chấp nhận**. Những phương thức cần biết:

```java
String name = principal.getName();
Map<String, Object> attributes = principal.getAttributes();
String subject = principal.getAttribute("sub");
String tenant = principal.getAttribute("tenant_id");
Collection<? extends GrantedAuthority> granted =
    principal.getAuthorities();
```

Các dòng này là mảnh Java cần có biến `principal` và imports.

| API | Nội dung | Điểm cần nhớ |
|---|---|---|
| `getName()` | Principal name ứng dụng thấy | Mặc định thường dựa `sub`; custom mapping có thể khác |
| `getAttributes()` | Các metadata/token claims đã chấp nhận | Không trả nguyên Map ra public JSON |
| `getAttribute("sub")` | Subject nếu AS cung cấp | Có thể vắng hoặc sai kiểu trong custom provider |
| `getAttribute("scope")` | Scopes sau chuyển đổi | Có thể là `List<String>`, không mặc định String |
| `getAttribute("tenant_id")` | Tenant nếu AS cung cấp | Không đồng nghĩa client được chọn tenant khác |
| `getAttribute("exp")` | Thông tin expiry nếu có | Cần xem kiểu `Instant`/số theo implementation |
| `getAuthorities()` | Spring GrantedAuthority | Dùng `hasAuthority(...)` và method security |

`getAttribute(name)` là generic accessor, có thể trả `null`. Không ép kiểu tùy ý khi provider khác nhau; validate claims bắt buộc rồi mới xử lý.

### DefaultOAuth2AuthenticatedPrincipal

Class `DefaultOAuth2AuthenticatedPrincipal` là implementation phổ biến:

```java
OAuth2AuthenticatedPrincipal alice =
    new DefaultOAuth2AuthenticatedPrincipal(
        "alice-id-42",
        Map.of(
            "sub", "alice-id-42",
            "tenant_id", "north"),
        List.of(new SimpleGrantedAuthority("SCOPE_reports.read")));
```

Mảnh code này có thể chạy khi ở trong class có imports và Spring Security dependencies. Constructor có `name` là cách giữ principal name tường minh; constructor nhận `Map, Collection` cũng tồn tại.

**Principal không phải Authentication.** Nó biểu diễn subject/attributes/authorities; Security dùng nó để dựng Authentication của một request đã xác minh.

## 7. BearerTokenAuthentication và Reactive SecurityContext

Sau khi introspection thành công, Spring Security tạo `BearerTokenAuthentication`, chứa:

```text
BearerTokenAuthentication
  principal      -> OAuth2AuthenticatedPrincipal
  authorities    -> GrantedAuthority collection
  tokenAttributes-> principal's attributes
  credentials    -> token-associated data (nhạy cảm)
```

`Authentication.getName()` thường dựa principal name; `BearerTokenAuthentication.getTokenAttributes()` trả các attribute đã được accepted. Trong WebFlux, `SecurityContext` được truyền qua **Reactor Context**.

Hai cách dùng ở controller:

```java
@GetMapping("/api/me")
public Mono<String> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    String sub = principal.getAttribute("sub");
    return Mono.just("subject=" + sub);
}
```

```java
@GetMapping("/api/meta")
public Mono<String> meta(BearerTokenAuthentication authentication) {
    Object subject = authentication.getTokenAttributes().get("sub");
    return Mono.just("subject=" + subject);
}
```

Đây là hai **method minh họa**, không phải Java file độc lập. Chỉ expose chúng trên endpoint đã được bảo vệ. Khi cần log, chỉ log mã request hoặc subject đã được hạn chế theo policy; **không log `getCredentials()`, token value hoặc toàn bộ authentication**.

### Tránh nhầm các loại principal

| Tình huống | Principal/Authentication thường gặp |
|---|---|
| Resource Server opaque | `OAuth2AuthenticatedPrincipal` / `BearerTokenAuthentication` |
| Resource Server JWT | `Jwt` / `JwtAuthenticationToken` |
| OAuth2 Login | `OAuth2User` / `OAuth2AuthenticationToken` |
| OIDC Login | `OidcUser` / `OAuth2AuthenticationToken` |
| Basic username/password | `UserDetails` hoặc principal do provider tạo |

Không dùng `@AuthenticationPrincipal Jwt` trên một route chỉ cấu hình opaque introspection rồi mặc định không null. Và đừng xem opaque token principal là user có quyền admin chỉ vì `authenticated()` trả true.

## 8. Mapping scope thành authorities: 401 hay 403?

Introspection response ví dụ:

```json
{"active":true,"sub":"alice","scope":"messages.read reports.read"}
```

Spring Security mặc định ánh xạ scopes sang:

```text
SCOPE_messages.read
SCOPE_reports.read
```

Và policy:

```java
.pathMatchers(HttpMethod.GET, "/api/messages")
    .hasAuthority("SCOPE_messages.read")
.pathMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_reports.read")
```

**`hasRole("ADMIN")` thường kiểm `ROLE_ADMIN`, không phải `SCOPE_admin`.** Nếu dữ liệu role đến từ AS/trusted entitlement service, cần map authority tường minh, có allowlist; không đọc role từ header do client tự gửi.

| Trường hợp | HTTP status thông thường | Lý do |
|---|---|---|
| Không có bearer trên route protected | 401 | Chưa authenticated |
| Token inactive/unknown/expired | 401 | Authentication thất bại |
| Token active thiếu scope | 403 | Authenticated nhưng không đủ authority |
| Token active có scope nhưng ngoài tenant | 403 hoặc 404 theo policy | Business authorization |
| Token active và đủ quyền | 200 khi business thành công | Cho phép |
| AS timeout/malformed reply | Fail closed; response tùy failure handler | Không phát authenticated principal |

**Điểm an toàn then chốt:** trả `active:true` không tự bảo đảm token đúng audience của từng API. Nếu AS có nhiều resource, API phải enforce `aud`/`resource`, issuer/client, tenant và quyền dữ liệu khi chính sách yêu cầu.

## 9. Dự án Java 17+ Spring Boot WebFlux đầy đủ

Demo có các endpoint public, profile, messages, admin và report theo tenant. Spring Boot tạo introspector thật từ properties; test dùng introspector giả **chỉ trong test** để kiểm đường đi bearer → principal → authorization mà không cần IdP thật.

### 9.1 Cấu trúc project

```text
webflux-opaque-principal/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/opaque/OpaqueApplication.java
  src/main/java/example/opaque/SecurityConfiguration.java
  src/main/java/example/opaque/OpaqueController.java
  src/test/java/example/opaque/OpaqueSecurityTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-opaque-principal'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.opaque'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**src/main/resources/application.yml**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.invalid/oauth2/introspect
          client-id: training-introspection
          client-secret: training-not-a-real-secret
```

Host `idp.example.invalid` **không có IdP thật**; project có thể boot và trả public/401 cho request không bearer, nhưng một bearer thật không thể introspect đến khi cấu hình một AS thực. Các tests import stub introspector và không gọi endpoint này. Trong production, dùng:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${INTROSPECTION_URI}
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Ba biến cấu hình phải được cấp qua secret/config management; bắt buộc HTTPS/trust và least privilege cho introspection client.

### 9.2 Main application

**src/main/java/example/opaque/OpaqueApplication.java**

```java
package example.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueApplication.class, args);
    }
}
```

### 9.3 SecurityConfiguration.java

**src/main/java/example/opaque/SecurityConfiguration.java**

```java
package example.opaque;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/messages")
                    .hasAuthority("SCOPE_messages.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_admin.read")
                .pathMatchers(HttpMethod.GET,
                    "/api/tenant/{tenantId}/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Điểm cần đọc:

1. `@EnableWebFluxSecurity` + `SecurityWebFilterChain` là cơ chế reactive, không dùng Servlet `HttpSecurity`.
2. `.oauth2ResourceServer(...opaqueToken(...))` kích hoạt opaque token introspection.
3. `.hasAuthority("SCOPE_messages.read")` quyết định quyền theo scope trusted, **không** theo query param client.
4. Route tenant cần scope nhưng vẫn kiểm `tenant_id` ở controller/service.
5. Với token Bearer **không hợp lệ**, authentication filter có thể trả 401 ngay cả trên route `permitAll`; public nghĩa là không cần token, **không** nghĩa token giả được chấp nhận.
6. Demo chỉ có GET nên không dùng CSRF token; ứng dụng có unsafe methods và browser-managed credentials cần xét CSRF theo threat model.

### 9.4 OpaqueController.java

**src/main/java/example/opaque/OpaqueController.java**

```java
package example.opaque;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class OpaqueController {

    public record Message(String message) {}
    public record Profile(
        String subject, String tenant, List<String> authorities) {}

    @GetMapping("/api/public")
    public Mono<Message> publicEndpoint() {
        return Mono.just(new Message("public"));
    }

    @GetMapping("/api/me")
    public Mono<Profile> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal,
            BearerTokenAuthentication authentication) {
        String subject = principal.getAttribute("sub");
        String tenant = principal.getAttribute("tenant_id");
        List<String> authorities = authentication.getAuthorities()
            .stream().map(a -> a.getAuthority()).sorted().toList();

        // Không serialize nguyên Authentication/opaque token.
        return Mono.just(new Profile(subject, tenant, authorities));
    }

    @GetMapping("/api/messages")
    public Mono<Message> messages(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(new Message(
            "messages for " + principal.getName()));
    }

    @GetMapping("/api/admin")
    public Mono<Message> admin() {
        return Mono.just(new Message("admin-area"));
    }

    @GetMapping("/api/tenant/{tenantId}/reports")
    public Mono<Message> tenantReports(
            @PathVariable String tenantId,
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        String allowedTenant = principal.getAttribute("tenant_id");
        if (allowedTenant == null || !allowedTenant.equals(tenantId)) {
            return Mono.error(
                new ResponseStatusException(HttpStatus.FORBIDDEN));
        }
        return Mono.just(new Message("reports for " + allowedTenant));
    }
}
```

**Giới hạn demo:** controller so tenant chỉ để thấy ranh giới. Production nên enforce tenant/owner ở query repository và kiểm đúng issuer+subject/internal account mapping. Không nên gọi `findAll()` rồi lọc kết quả sau khi DB đã trả mọi tenant.

### 9.5 OpaqueSecurityTest.java — WebTestClient qua Security WebFilters

**src/test/java/example/opaque/OpaqueSecurityTest.java**

```java
package example.opaque;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
@Import(OpaqueSecurityTest.TestIntrospector.class)
class OpaqueSecurityTest {

    @Autowired
    WebTestClient client;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestIntrospector {

        private static OAuth2AuthenticatedPrincipal principal(
                String user, String tenant, String... granted) {
            List<GrantedAuthority> authorities = new ArrayList<>();
            for (String name : granted) {
                authorities.add(new SimpleGrantedAuthority(name));
            }
            return new DefaultOAuth2AuthenticatedPrincipal(
                user,
                Map.of("sub", user, "tenant_id", tenant),
                authorities);
        }

        @Bean
        ReactiveOpaqueTokenIntrospector testOpaqueTokenIntrospector() {
            // Chỉ có trong test context. Không xác minh token thật!
            return token -> Mono.defer(() -> switch (token) {
                case "alice-token" -> Mono.just(principal(
                    "alice", "north",
                    "SCOPE_messages.read", "SCOPE_reports.read"));
                case "bob-token" -> Mono.just(principal(
                    "bob", "south",
                    "SCOPE_messages.read", "SCOPE_reports.read"));
                case "admin-token" -> Mono.just(principal(
                    "admin", "north", "SCOPE_admin.read"));
                case "viewer-token" -> Mono.just(principal(
                    "viewer", "north"));
                case "revoked-token", "expired-token" -> Mono.error(
                    new BadOpaqueTokenException("Inactive token"));
                default -> Mono.error(
                    new BadOpaqueTokenException("Unrecognized token"));
            });
        }
    }

    @Test
    void publicRouteAllowsAnonymous() {
        client.get().uri("/api/public").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void protectedRouteWithoutTokenIs401() {
        client.get().uri("/api/me").exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void principalExposesVerifiedSubjectAndAuthorities() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("alice-token"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice")
            .jsonPath("$.tenant").isEqualTo("north")
            .jsonPath("$.authorities[0]")
                .isEqualTo("SCOPE_messages.read");
    }

    @Test
    void scopeAllowsMessages() {
        client.get().uri("/api/messages")
            .headers(h -> h.setBearerAuth("bob-token"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("messages for bob");
    }

    @Test
    void tokenWithoutScopeGets403() {
        client.get().uri("/api/messages")
            .headers(h -> h.setBearerAuth("viewer-token"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void revokedTokenGets401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("revoked-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredTokenGets401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("expired-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void adminScopeAllowsAdminRoute() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("admin-token"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("admin-area");
    }

    @Test
    void aliceCannotUseAdminRoute() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("alice-token"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tenantConstraintStillAppliesWithValidScope() {
        client.get().uri("/api/tenant/north/reports")
            .headers(h -> h.setBearerAuth("alice-token"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/tenant/south/reports")
            .headers(h -> h.setBearerAuth("alice-token"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownTokenCannotBecomeAuthenticated() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("random-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**11 test methods** kiểm tra public, 401 thiếu credential, principal/authority extraction, 403 thiếu scope, revoked/expired/unknown tokens, role Admin và tenant isolation. Test stub chỉ nhận token fixtures cố định và phát lỗi cho mọi token khác.

Vì `@TestConfiguration` chỉ được `@Import` ở test, nó **không thay thế introspector production trong `bootRun`**. Đây là test của **WebFilter bearer parsing + authentication + authorization**, không phải test HTTP introspection RFC 7662 thật.

**Chạy:**

```bash
gradle test
```

Có thể dùng `./gradlew test` khi có Wrapper đúng phiên bản, hoặc `gradlew.bat test` trên Windows.

**Không tuyên bố đã chạy Gradle:** test là kết quả dự kiến sau khi rà soát API/cú pháp. Khi chạy thực tế phải kiểm dependency tree, lỗi compile và assertion cụ thể. Test này không chứng minh AS thật cấp/revoke token, cấu hình TLS, Basic introspection credentials, latency hoặc retry đúng.

### 9.6 Chạy app và gọi endpoint khi có IdP thật

```bash
gradle bootRun

curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me

# Sau khi thay YAML bằng introspection URI và credential thật:
curl -i -H "Authorization: Bearer <ACCESS_TOKEN>" \
  http://localhost:8080/api/me
```

`<ACCESS_TOKEN>` chỉ là placeholder, không dùng raw token thật trong tài liệu hoặc chia sẻ logs. `curl -i` hiển thị response status; nếu token thiếu hoặc inactive, kỳ vọng 401, nếu token active nhưng thiếu quyền route, kỳ vọng 403.

## 10. Tuỳ chỉnh introspector để map authority

Nhiều doanh nghiệp muốn kiểm claim tenant hoặc chuyển scope thành role. Cách đáng tin là **decorator** gọi delegate introspection **trước**, rồi mới map.

**src/main/java/example/policy/TenantPolicyIntrospector.java** (một ví dụ thay thế, **không thêm trực tiếp vào project mục 9**):

```java
package example.policy;

import java.util.ArrayList;
import java.util.Collection;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class TenantPolicyIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public TenantPolicyIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token).map(principal -> {
            Object value = principal.getAttributes().get("tenant_id");
            if (!(value instanceof String tenant)
                    || tenant.isBlank()) {
                throw new BadOpaqueTokenException(
                    "Required verified tenant is missing");
            }

            Collection<GrantedAuthority> authorities =
                new ArrayList<>(principal.getAuthorities());

            boolean canRead = authorities.stream().anyMatch(a ->
                "SCOPE_reports.read".equals(a.getAuthority()));

            if (canRead) {
                authorities.add(
                    new SimpleGrantedAuthority("ROLE_REPORT_VIEWER"));
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                authorities);
        });
    }
}
```

Class chỉ map một role có thể kiểm chứng từ scope của AS. Nó **không tự cấp quyền admin** và không tạo principal nếu tenant không tồn tại. Một source claim `roles` của AS có thể dùng, nhưng phải xác định format, issuer và allowlist role chính thức.

### Tránh vòng phụ thuộc bean

Không viết:

```java
// CÓ NGUY CƠ CIRCULAR DEPENDENCY:
@Bean
ReactiveOpaqueTokenIntrospector wrapper(
        ReactiveOpaqueTokenIntrospector sameBean) {
    return new TenantPolicyIntrospector(sameBean);
}
```

Thay vào đó, **xây delegate rõ ràng** từ introspection URL và credentials, rồi publish đúng một bean cuối cùng, hoặc khai báo hai bean có qualifier tách biệt. Boot auto-configuration sẽ back off khi app cung cấp custom introspector bean; không mặc định nó tạo sẵn delegate cho custom wrapper của bạn.

Trong Boot 3.3 có thể xây delegate với implementation/constructor tương thích 6.3; trong Spring Security 6.5+ có builder mới. Kiểm đúng version trước khi viết factory.

## 11. Unit test trực tiếp ReactiveOpaqueTokenIntrospector bằng StepVerifier

Ví dụ mảnh test cho decorator với fake delegate, không cần Spring ApplicationContext:

```java
ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        Map.of("sub", "alice", "tenant_id", "north"),
        List.of(
            new SimpleGrantedAuthority("SCOPE_reports.read"))));

TenantPolicyIntrospector policy =
    new TenantPolicyIntrospector(delegate);

StepVerifier.create(policy.introspect("fixture"))
    .assertNext(p -> {
        boolean mapped = p.getAuthorities().stream()
            .anyMatch(a ->
                "ROLE_REPORT_VIEWER".equals(a.getAuthority()));
        org.junit.jupiter.api.Assertions.assertTrue(mapped);
    })
    .verifyComplete();
```

Đây là **mảnh test** cần imports (`Map`, `List`, `Mono`, `StepVerifier`) và class test chứa nó. Bài tập mở rộng: delegate không có `tenant_id` phải phát `BadOpaqueTokenException`; delegate lỗi 5xx/timeout phải lan lỗi chứ không tạo principal.

**Không được sử dụng stub always-accept ở production.** Unit test kiểm code decorator, không thay thế HTTP integration test với AS.

## 12. Test nhanh bằng Spring Security mockOpaqueToken()

Khi mục tiêu chỉ là kiểm controller hoặc method authorization, Spring Security Test có:

```groovy
testImplementation 'org.springframework.security:spring-security-test'
```

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

// Mảnh code WebTestClient mock-based:
client.mutateWith(mockOpaqueToken())
    .get().uri("/api/me")
    .exchange()
    .expectStatus().isOk();
```

`mockOpaqueToken()` dựng `BearerTokenAuthentication` giả với principal/authorities cho request test. Nó **bỏ qua introspection thật**, giúp unit test nhanh nhưng không chứng minh `active:false`, client secret, HTTP body hay AS error được xử lý đúng.

So sánh hai cấp:

- `mockOpaqueToken()`: test controller với security context đã giả lập, nhanh.
- Fake `ReactiveOpaqueTokenIntrospector` + Bearer header như mục 9: test request đi qua filter pipeline và gọi introspector stub, không cần AS.
- Mock HTTP AS/WireMock/MockWebServer: test RFC 7662 network, credentials, active true/false, timeout, scope mapping; thích hợp integration.
- AS staging/thật: test thực tế rotation, TTL, revocation và environment.

## 13. Hiệu năng, revocation và AS outage

Opaque token introspection thường có thêm một network call trong critical path:

```text
Client HTTP request -> Resource Server -> Authorization Server
                                         introspection
                       <- active / claims
                     authorization + domain DB
Client <- 200 / 401 / 403
```

Nếu mỗi API request đều introspect và QPS lớn, chi phí lên cả AS và Resource Server:

- Thời gian tăng: DNS/TLS/network/JSON parsing.
- AS outage có thể tác động toàn bộ protected API.
- Credential introspection có thể bị sai/rotate và gây nhiều lỗi 401/5xx.
- Cache kết quả giúp giảm tải nhưng **có thể làm token đã revoke tiếp tục được chấp nhận** đến lúc TTL hết.

### Fail closed, timeout, retry

1. Giới hạn timeout/connect/read/total, connection pool và concurrency.
2. Khi AS trả invalid/inactive: không retry liên tục để cố lấy active=true.
3. Khi AS trả 5xx hoặc timeout: xử lý bằng backoff/circuit-breaker có giới hạn, **không cho qua request không được xác thực**.
4. Phân biệt failure do introspection transport và failure do token invalid trong log/metrics nội bộ.
5. Không log token, client secret, Authorization header, raw introspection body.
6. Chỉ dùng HTTPS với certificate validation; không tắt TLS check cho dễ chạy.
7. Nếu cần retry, không retry vô hạn trên từng bearer sai vì có thể gây amplification DoS.

### Cache introspection có rủi ro nào?

```text
10:00 Token X active=true, cache TTL 5 phút
10:01 User logout/revoke Token X
10:02 Cache vẫn trả active=true
10:05 TTL hết -> hỏi AS -> active=false
```

Nếu yêu cầu thu hồi gần tức thời, cache dài không phù hợp.

- TTL phải không vượt token `exp` và phù hợp revocation SLA.
- Token thiếu `exp` không nên cache vô hạn.
- Không dùng raw access token làm metric label, log text hoặc public Redis key.
- Cache key nên partition theo issuer/introspection endpoint/tenant và có HMAC/digest an toàn khi cần.
- Xem xét cache invalidation khi permission/role/tenant thay đổi.
- Kiểm multi-node cache, clock skew, idempotency và negative caching.
- Tài liệu Spring Security không hứa một TTL cache mặc định phù hợp mọi môi trường; đo và thiết kế theo threat model.

## 14. Active không thay được audience và object-level authorization

Token có thể `active:true` vì vẫn hợp lệ tại AS, nhưng được cấp cho **resource khác**:

```text
token: active=true, aud=["inventory-api"]
request: Payroll API /payroll/users

Chỉ kiểm active+authenticated -> có nguy cơ nhận sai token
Phải kiểm aud/resource/scope/issuer theo chính sách Payroll.
```

Nếu introspection response không có `aud`, và resource API đòi audience isolation, cần yêu cầu AS trả claims phù hợp hoặc có một policy khác xác minh token dành cho API này. Không tự mặc định “claim thiếu = mọi resource đều được phép”.

**Multi-tenant:** scope `reports.read` chỉ là quyền tổng quát. Query dữ liệu nên ràng buộc tenant/owner, ví dụ pseudo R2DBC:

```java
Flux<Report> findVisibleReports(
        String trustedTenantId, String trustedUserId) {
    return repository.findAllByTenantIdAndOwnerId(
        trustedTenantId, trustedUserId);
}
```

Đây là mảnh code không biên dịch độc lập; repository cần được khai báo theo entity thật. `trustedTenantId` và `trustedUserId` phải đến từ principal đã xác minh và policy mapping, không lấy trực tiếp query param.

## 15. Reactive và Servlet khác nhau

| Yếu tố | Spring WebFlux | Spring MVC / Servlet |
|---|---|---|
| Security builder | `ServerHttpSecurity` | `HttpSecurity` |
| Chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Introspector | `ReactiveOpaqueTokenIntrospector` | `OpaqueTokenIntrospector` |
| Return | `Mono<OAuth2AuthenticatedPrincipal>` | `OAuth2AuthenticatedPrincipal` |
| Request | `ServerWebExchange` | Servlet request |
| Principal | `OAuth2AuthenticatedPrincipal` | `OAuth2AuthenticatedPrincipal` (cùng interface) |
| Authenticated token | `BearerTokenAuthentication` | `BearerTokenAuthentication` (cùng type) |
| Authentication context | Reactor Context | ThreadLocal trong Servlet flow |
| Test | WebTestClient | MockMvc |

Đừng import một implementation Servlet rồi bọc `Mono.just(...)` quanh kết quả gọi blocking trong event loop; nguy cơ block và timeout. Nếu backend introspection thực chất synchronous, cân nhắc giải pháp reactive WebClient hoặc scheduler boundary được giới hạn và quan sát.

## 16. Những lỗi thường gặp

| Triệu chứng | Chẩn đoán |
|---|---|
| Bearer luôn 401 | AS trả inactive, URI sai, introspection credentials sai, TTL hết, token khác issuer |
| Token active nhưng 403 | Thiếu `SCOPE_...` hoặc policy tenant/role từ chối |
| `hasRole("ADMIN")` sai | Claim scope chỉ map `SCOPE_admin`, không phải `ROLE_ADMIN` |
| Get `scope` bị ClassCastException | Introspector đã convert kiểu sang List; không cast sang String vô điều kiện |
| `getName()` không đúng user | AS dùng claim khác `sub`; cần trusted name mapping |
| Từ bên ngoài dùng token của API khác | Thiếu audience/resource check |
| Public endpoint 401 khi gửi bearer rác | Filter vẫn thử authenticate bearer không hợp lệ |
| AS down toàn bộ protected API lỗi | Resource Server phụ thuộc introspection; cần availability/timeout |
| Đã revoke nhưng vẫn được 200 | Cache dương quá dài hoặc AS chưa cập nhật |
| Token hợp lệ nhưng sai tenant vẫn đọc được | Scope-only authorization, query không lọc tenant |
| `@AuthenticationPrincipal Jwt` null | Đang cấu hình opaque, principal không phải Jwt |
| Mọi token thành admin trong test nhưng production sai | Stub always-accept bị đặt nhầm context |
| Dùng builder 6.5 trên Security 6.3 | Không có method `withIntrospectionUri`; dùng Boot properties/constructor đúng version |
| 401/403 không phân biệt | Đọc authentication failure vs authorization denied |
| Test `mockOpaqueToken()` pass nhưng integration fail | Test bỏ qua introspection HTTP/credential |
| Lộ token trong log | Redact raw HTTP headers, principal/credentials, token attributes nhạy cảm |
| Multiple SecurityWebFilterChain chọn sai | Kiểm `securityMatcher`, `@Order` và fallback |
| Issuer/tenant claims không đúng kiểu | Validate required claims trước khi tạo principal |

Đừng “sửa” các lỗi trên bằng cách đặt `.anyExchange().permitAll()`, bỏ kiểm token, hoặc `onErrorResume(e -> Mono.just(adminPrincipal))`.

## 17. Ma trận test production đề nghị

1. Không có Bearer → 401.
2. Bearer malformed/invalid → 401, không gọi controller.
3. Token active scope hợp lệ → 200.
4. Token active thiếu scope → 403.
5. AS trả `active:false` → 401.
6. Token revoke giữa hai request → request sau phải bị chặn theo revocation SLA.
7. Token hết hạn → 401.
8. AS 401 do introspection client secret sai → không tạo principal.
9. AS 429/500/timeout/malformed JSON → fail closed, metrics phân loại.
10. Claims `sub`/`tenant_id` thiếu hoặc sai kiểu → deny khi chính sách bắt buộc.
11. Audience/issuer sai → deny, dù active=true.
12. Route khác tenant/owner → deny ở service/repository.
13. Scope có dấu `.`/`:` được map đúng prefix.
14. Mọi response đều không lộ token/secret.
15. Load test trên AS introspection endpoint: QPS, p95/p99, connection pool, backoff.
16. Cache TTL và multi-pod consistency sau revoke.
17. Runbook credential rotation, issuer migration và AS outage.
18. Dependency upgrades Spring Security 6.3→6.5/7.x với test introspector implementation/builder.

## 18. Checklist áp dụng

- Chọn đúng mô hình: opaque introspection hay JWT signature decoding.
- Bật `oauth2ResourceServer().opaqueToken()` trên đúng WebFlux chain.
- Dùng `ReactiveOpaqueTokenIntrospector` và `OAuth2AuthenticatedPrincipal` đúng package.
- Tạo introspection URI, client-id, client-secret từ nguồn đáng tin, dùng TLS.
- Định nghĩa required attributes, principal name và scopes/roles rõ ràng.
- Từ chối token inactive và lỗi introspection; không fail open.
- Kiểm audience, issuer, tenant, client và record ownership theo policy.
- Dùng DTO allowlist trong JSON; không xuất principal/token raw.
- Bảo vệ event loop, timeout, backpressure, circuit breaker và AS availability.
- Nếu cache, xác định revocation window và TTL không vượt `exp`.
- Test WebTestClient bearer header thật + fake introspector, test mockOpaqueToken riêng, HTTP introspection integration với AS mock/thật.
- Khi nâng cấp, kiểm biến thể `NimbusReactiveOpaqueTokenIntrospector`/`SpringReactiveOpaqueTokenIntrospector` và builder API.
- Duy trì phiên bản Spring Security còn hỗ trợ bảo mật trong production.

## 19. Bài tập thực hành

1. Viết giải thích vì sao opaque token không tự cung cấp subject/scopes nếu thiếu introspection.
2. So sánh `ReactiveOpaqueTokenIntrospector` với `ReactiveJwtDecoder` về revocation và network cost.
3. Tạo `DefaultOAuth2AuthenticatedPrincipal` có `sub`/`tenant_id` và hai scopes.
4. Trong WebTestClient, đổi `alice-token` sang `viewer-token` trên `/api/messages`. Vì sao nhận 403?
5. Kiểm active token ngoài tenant bị 403 dù có `SCOPE_reports.read`.
6. Bổ sung case introspector trả `Mono.error(new BadOpaqueTokenException(...))` và bảo đảm HTTP 401.
7. Dùng `mockOpaqueToken()` và chỉ ra vì sao không chứng minh introspection network hoạt động.
8. Viết unit test StepVerifier cho `TenantPolicyIntrospector` không có tenant.
9. Dựng mock AS trả active:true và active:false, xác minh client authentication và form-encoded request.
10. Viết policy audience cho Reports API chỉ chấp nhận `aud=reports-api`.
11. Đo chi phí của 1000 request khi mỗi request phải introspect; thảo luận TTL cache và revocation.
12. Thiết kế fallback an toàn khi AS timeout, không trả 200 hoặc role mặc định.
13. So sánh error 401, 403 và 5xx/AS outage trong báo cáo vận hành.
14. Rà soát khả năng lộ token qua HTTP logs, traces, test reports và exception handling.
15. Nâng Spring Security 6.3 sang bản mới và sửa cách dựng introspector theo Javadoc.

## Kết luận

**`ReactiveOpaqueTokenIntrospector`** xác minh một bearer access token trong **Spring Security WebFlux**, trả `Mono<OAuth2AuthenticatedPrincipal>` khi thành công. Principal mang **attributes và authorities** để Spring tạo `BearerTokenAuthentication` và kiểm quyền; token inactive/không được xác minh phải bị từ chối. Theo policy thông thường, **401** dành cho yêu cầu chưa xác thực hoặc bearer không hợp lệ, còn **403** dành cho principal đã xác thực nhưng không đủ scope/tenant permission. Introspection hỗ trợ phát hiện thu hồi token nhưng làm tăng latency và phụ thuộc Authorization Server. Hệ thống production cần TLS, secrets, audience validation, tenant checks, fail closed, kiểm caching TTL và negative tests đầy đủ.

## Tài liệu chính thức

1. Spring Security 6.5 — Reactive Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
2. Spring Security — ReactiveOpaqueTokenIntrospector Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
3. Spring Security — SpringReactiveOpaqueTokenIntrospector.Builder (Since 6.5): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.Builder.html
4. Spring Security — DefaultOAuth2AuthenticatedPrincipal Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html
5. Spring Security — Reactive OAuth2 testing, mockOpaqueToken: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
6. Spring Security 6.3 — Introspection package Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/oauth2/server/resource/introspection/package-summary.html
7. Spring Boot 3.3 — WebFlux Security/OAuth2 Resource Server: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
8. RFC 7662 — OAuth2 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
9. RFC 6750 — OAuth2 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
