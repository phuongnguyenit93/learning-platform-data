# Ánh xạ thuộc tính introspection và scope thành GrantedAuthority trong Spring Security WebFlux

## Mục tiêu và phạm vi

Bài học thuộc **Spring Security – reactive**, chủ đề **Resource Server Opaque**. Người học sẽ nắm được:

1. Resource Server xác thực **opaque Bearer token** bằng OAuth 2.0 Token Introspection (RFC 7662), rồi chuyển dữ liệu introspection thành `OAuth2AuthenticatedPrincipal` và `GrantedAuthority` như thế nào.
2. Quy tắc mặc định **scope → `SCOPE_<scope>`**, sự khác nhau giữa `hasAuthority("SCOPE_reports.read")` và `hasRole("ANALYST")`.
3. Cách đọc các thuộc tính `active`, `scope`, `sub`, `client_id`, `aud`, `iss`, `exp`, `tenant` và `app_roles`, đồng thời phân biệt trường chuẩn RFC với trường mở rộng riêng của IdP.
4. Cách viết `ReactiveOpaqueTokenIntrospector` dạng **decorator**: ủy quyền việc xác minh token cho `SpringReactiveOpaqueTokenIntrospector`, sau đó **giữ nguyên scope authorities** và chỉ bổ sung role nghiệp vụ từ allowlist đã kiểm chứng.
5. Cách kết hợp `SecurityWebFilterChain`, `ServerHttpSecurity.oauth2ResourceServer(...).opaqueToken(...)`, `BearerTokenAuthentication`, `@AuthenticationPrincipal`, `WebTestClient` và `StepVerifier`.
6. Xây dựng ví dụ Java 17+ / Spring Boot 3.5.x hoàn chỉnh, kiểm thử với **introspection server giả lập HTTP trên localhost** mà không cần IdP thật.
7. Phân tích rủi ro **privilege escalation**, scope injection, role mapping lỏng, cached introspection với revocation, introspection server downtime, sai audience/tenant, thiếu timeout và lộ token trong logs.
8. Phân biệt rõ **kiểm tra token hợp lệ** với **cấp quyền thao tác**, và khi nào cần kiểm tra quyền theo tài nguyên ở service/database.

> Bản thực hành dùng Spring Boot **3.5.16** / Spring Security **6.5.x**, Java 17+, WebFlux thuần. Spring Boot 3.5.16 là bản OSS cuối của nhánh 3.5; xây hệ thống mới nên dùng bản Spring Boot/Security còn được hỗ trợ. Các API Servlet như `HttpSecurity`, `SecurityFilterChain`, `OpaqueTokenIntrospector` (không có chữ Reactive) và `HttpServletRequest` **không** dùng trong ví dụ reactive này.

---

## 1. Mô hình: từ Bearer token sang authorities

OAuth2 **Authorization Server / Identity Provider (IdP)** cấp access token. Với opaque token, chuỗi token không có cấu trúc claim đáng tin để Resource Server tự đọc. Resource Server gửi token tới **introspection endpoint** của Authorization Server, xác minh trạng thái token và nhận metadata.

```text
Client / Service
   |
   | GET /api/reports
   | Authorization: Bearer <opaque-token>
   v
Spring Security WebFlux Resource Server
   |
   +-- Bearer token authentication filter
   |       |
   |       +-- ReactiveOpaqueTokenIntrospector.introspect(token)
   |              |
   |              +-- POST HTTPS /oauth2/introspect
   |              |   Basic auth của resource server
   |              |
   |              +-- Authorization Server đáp JSON:
   |                  active=true, sub, scope, aud, ...
   |
   +-- OAuth2AuthenticatedPrincipal
   |      - attributes: sub, scope, tenant, app_roles...
   |      - authorities: SCOPE_reports.read, ROLE_ANALYST...
   |
   +-- BearerTokenAuthentication
   |      - principal + attributes + GrantedAuthority
   |
   +-- AuthorizationWebFilter
   |      - hasAuthority("SCOPE_reports.read")
   |      - hasRole("ANALYST")
   |
   +-- Controller / Service / Database (ownership, tenant)
   |
   +-- 200 / 401 / 403
```

**Hai tầng cần được phân biệt:**

- **Authentication:** token có hợp lệ và được Authorization Server chấp nhận không? Spring Security dùng introspector; `active=false` phải bị từ chối. Khi có response hợp lệ, nó tạo `OAuth2AuthenticatedPrincipal` và `BearerTokenAuthentication`.
- **Authorization:** token hợp lệ có được thực hiện việc này không? Spring Security kiểm tra `GrantedAuthority` theo HTTP/method policies; service tiếp tục kiểm tra owner/tenant/resource.

**Không phải mọi thuộc tính introspection đều tự trở thành authority.** Theo mặc định, Spring Security chuyển các scope thành `SCOPE_...`. Các trường như `app_roles`, `groups`, `tenant` hoặc `department` **không tự động** biến thành Spring role.

## 2. Introspection response chuẩn và thuộc tính mở rộng

Một introspection response ví dụ:

```json
{
  "active": true,
  "scope": "reports.read reports.write",
  "client_id": "internal-portal",
  "sub": "alice",
  "aud": "api://reports",
  "iss": "https://idp.example.test",
  "token_type": "Bearer",
  "exp": 1893456000,
  "tenant": "acme",
  "app_roles": ["analyst"]
}
```

Đây là ví dụ minh họa hợp đồng với một IdP giả định, không phải cấu trúc bắt buộc cho mọi provider.

| Trường | Ý nghĩa | Xử lý an toàn |
| --- | --- | --- |
| `active` | Token có đang hợp lệ theo Authorization Server? | `false` → từ chối; không tự tạo principal khi inactive |
| `scope` | Danh sách quyền OAuth2, thường dạng chuỗi phân tách bằng dấu cách | Framework mặc định ánh xạ mỗi scope thành `SCOPE_...` |
| `client_id` | OAuth2 client được cấp token | Không nhầm với end-user hoặc `ROLE_*` |
| `sub` | Chủ thể của token | Dùng làm identity sau authentication; kiểm tra tenant nếu cần |
| `aud` | Resource/API nhận token | Nên so với audience của chính API; có thể là String hoặc collection |
| `iss` | Issuer / nhà phát hành token nếu provider công bố | Chỉ tin issuer đã được cấu hình/cho phép; không phải mọi IdP trả trường này |
| `exp` | Thời điểm hết hạn (epoch seconds) | Đánh giá chính sách IdP và khả năng revocation |
| `token_type` | Loại token | Không đồng nhất với role hoặc scope |
| `tenant` | Thuộc tính mở rộng, ví dụ tenant ID | Không coi client-provided query param là tenant đã chứng thực |
| `app_roles` | Thuộc tính mở rộng role theo hợp đồng IdP | Chỉ map giá trị whitelist, đúng issuer/audience/tenant |

**Từ RFC 7662:** `active` là trường cốt lõi; các trường như `scope`, `client_id`, `sub`, `aud`, `iss`, `exp` có thể được trả về tùy token/IdP. `tenant` và `app_roles` là dữ liệu **mở rộng riêng**, không phải claim chuẩn mà mọi introspection endpoint đều có.

### Vì sao không đọc scope trực tiếp từ token opaque?

Chuỗi opaque như `opaque-token-abc` không chứa scope có thể tin cậy dưới định dạng chuẩn. Nếu client gửi thêm:

```http
GET /api/reports HTTP/1.1
Authorization: Bearer opaque-token-abc
X-User-Role: ADMIN
X-Scope: reports.admin
```

thì `X-User-Role` và `X-Scope` là **header do client kiểm soát**. Không thể cấp ROLE_ADMIN/SCOPE_reports.admin chỉ dựa vào chúng. Quyền phải bắt nguồn từ introspection server tin cậy hoặc một authorization service đã xác minh, và được kiểm tra bởi policy.

## 3. Scope được chuyển thành GrantedAuthority mặc định

Spring Security reactive opaque token support:

1. Gửi token qua `ReactiveOpaqueTokenIntrospector`.
2. Với token active, lấy scope do introspection endpoint trả.
3. Chuyển từng scope thành một `SimpleGrantedAuthority` với tiền tố **`SCOPE_`**.
4. Đưa chúng vào `OAuth2AuthenticatedPrincipal.getAuthorities()` và `BearerTokenAuthentication.getAuthorities()`.

Ví dụ introspection:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "reports.read reports.write"
}
```

Kết quả authority mặc định về mặt ý nghĩa:

```text
SCOPE_reports.read
SCOPE_reports.write
```

**Không có quyền `ROLE_ANALYST` ở ví dụ này**, dù resource server đã xác minh được token.

| Introspection scope | GrantedAuthority | Rule tương ứng |
| --- | --- | --- |
| `reports.read` | `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` |
| `reports.write` | `SCOPE_reports.write` | `hasAuthority("SCOPE_reports.write")` |
| `message:read` | `SCOPE_message:read` | `hasAuthority("SCOPE_message:read")` |
| Không có scope | Không có SCOPE authority tương ứng | Rule yêu cầu scope phải từ chối |

**Phân biệt quyền:** `hasRole("ANALYST")` trong cấu hình thông thường kiểm tra `ROLE_ANALYST`, **không** kiểm tra `SCOPE_ANALYST`. Còn `hasAuthority("ROLE_ANALYST")` kiểm tra đúng chuỗi authority. Spring Security thường áp `ROLE_` cho role matcher, không tự hiểu scope là role.

Thay vì `hasAuthority`, có thể dùng helper `OAuth2ReactiveAuthorizationManagers.hasScope("reports.read")` trong `.access(...)`. Từ góc nhìn ứng dụng, cách đó vẫn dựa trên scope đã ánh xạ.

### Ví dụ HTTP policy

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/api/reports")
            .hasAuthority("SCOPE_reports.read")
        .pathMatchers(HttpMethod.GET, "/api/analyst")
            .hasRole("ANALYST")
        .anyExchange().denyAll()
)
```

Đây là **fragment** bên trong `ServerHttpSecurity`, không phải chương trình Java độc lập. Các rule này khác nhau: một token có scope `reports.read` vẫn có thể không có role analyst; ngược lại role analyst không tự tạo scope `reports.read` nếu mapping không cấp scope đó.

## 4. ReactiveOpaqueTokenIntrospector và DefaultOAuth2AuthenticatedPrincipal

Ở Spring Security 6.5, interface reactive có chữ ký:

```java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
```

Nằm trong package:

```java
org.springframework.security.oauth2.server.resource.introspection
```

Với `SpringReactiveOpaqueTokenIntrospector`, Spring gọi introspection endpoint và trả một principal **đã qua bước xác minh token**. Nếu inactive/không hợp lệ, nó không nên trả một principal được coi là authenticated.

**Không tự làm:**

```java
// Anti-pattern: không hề xác minh token với Authorization Server.
return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        Map.of("scope", "reports.admin"),
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
```

Mẫu trên có thể biến một token rác thành principal có quyền cao nếu được dùng làm introspector production. Một mock introspector chỉ được phép dùng trong unit tests, không được deploy thay verification thật.

**Cách mở rộng đúng:** bọc một introspector thật:

```java
return trustedDelegate.introspect(token)
        .map(principal -> new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                remapAuthorities(principal)));
```

Trong pipeline này:

- `trustedDelegate` xác minh tính active qua IdP trước.
- `principal.getAttributes()` giữ nguyên claims đã được IdP trả.
- `principal.getAuthorities()` chứa scope authorities mặc định.
- `remapAuthorities(...)` chỉ **bổ sung hoặc giới hạn** authorities theo hợp đồng rõ ràng; không tạo role tùy ý từ user input.

Lỗi nghiêm trọng thường gặp là tạo collection mới chứa chỉ `ROLE_ANALYST` rồi **làm mất tất cả `SCOPE_...`** hoặc ngược lại sao chép raw `app_roles` mà không giới hạn prefix/value.

## 5. Quy tắc mapping an toàn cho thuộc tính mở rộng

Giả sử IdP cam kết thêm:

```json
{
  "active": true,
  "sub": "alice",
  "aud": "api://reports",
  "scope": "reports.read",
  "tenant": "acme",
  "app_roles": ["analyst", "viewer"]
}
```

Policy của API:

- **Audience phải là** `api://reports`. Token dành cho resource khác bị 401 dù active.
- **Scope reports.read** tạo `SCOPE_reports.read` do Spring Security mặc định cung cấp.
- Chỉ khi `tenant=acme` và `app_roles` thực sự là **collection** chứa chuỗi chính xác `analyst`, thêm `ROLE_ANALYST`.
- Không tự nhận `admin`, `ROLE_ADMIN`, `root`, `superuser` hay chuỗi role bất kỳ.
- Không biến một role string do client gửi qua HTTP parameter thành authority.
- Nếu policy đa tenant thực sự, tenant phải được so khớp với resource trong service/DB; ví dụ role mapping cứng `acme` chỉ phục vụ lab.

### Tại sao phải giữ nguyên scope authorities?

Giả sử delegate đã tạo:

```text
SCOPE_reports.read
SCOPE_profile
```

Mapper đúng sau khi thêm analyst:

```text
SCOPE_reports.read
SCOPE_profile
ROLE_ANALYST
```

Mapper sai thay thế toàn bộ:

```text
ROLE_ANALYST
```

Khi đó endpoint `hasAuthority("SCOPE_reports.read")` có thể trả 403 dù token có scope đúng. Cách an toàn là dùng `LinkedHashSet<GrantedAuthority>` khởi tạo từ `principal.getAuthorities()` rồi thêm đúng role được whitelist, tránh trùng lặp.

### Schema attribute phải được kiểm tra

Introspection endpoint khác nhau có thể trả `scope` dưới dạng string hoặc collection sau khi framework chuẩn hóa; trường mở rộng `app_roles` có thể là list JSON, chuỗi, map hoặc không có. **Không cast bừa**:

```java
// Không an toàn và dễ ClassCastException nếu provider đổi định dạng:
List<String> roles = (List<String>) principal.getAttribute("app_roles");
```

Tốt hơn: kiểm tra `instanceof Collection<?>`, duyệt các giá trị được hỗ trợ và xử lý field thiếu theo chính sách deny. Nếu IdP có định dạng role khác, định nghĩa adapter cho đúng schema đã thỏa thuận thay vì nới lỏng tùy tiện.

## 6. Project Java 17+ runnable: Spring WebFlux Resource Server Opaque

Project hoàn chỉnh này có:

- Ứng dụng Spring Boot WebFlux dùng opaque token introspection thật qua HTTP client reactive.
- Một decorator `ScopeAndRoleIntrospector` bổ sung `ROLE_ANALYST` từ thuộc tính introspection allowlisted, **giữ lại SCOPE authorities mặc định**.
- Kiểm tra audience `api://reports` của mọi token trước khi cấp Authentication.
- API `/api/reports` yêu cầu scope reports.read, `/api/analyst` yêu cầu role ANALYST, `/api/me` cho xem metadata không nhạy cảm.
- `MockWebServer` trong test mô phỏng IdP trả `active=true/false` và các attributes, kiểm chứng 401/403/200/role spoofing.

**Chỉ trong kiểm thử**, introspection endpoint là HTTP trên `127.0.0.1`. **Production bắt buộc dùng HTTPS** và credentials được quản lý an toàn; dự án không cấp token thật và không tạo Authorization Server.

### 6.1. Cấu trúc thư mục

```text
opaque-authorities-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/opaquelab/
        OpaqueAuthoritiesApplication.java
        SecurityConfiguration.java
        ScopeAndRoleIntrospector.java
        ReportsController.java
      resources/
        application.yml
    test/
      java/example/opaquelab/
        OpaqueAuthoritiesIntegrationTest.java
```

Không dùng `spring-boot-starter-web`. Nếu thêm cả MVC lẫn WebFlux lên classpath, Spring Boot thường ưu tiên Servlet, làm sai stack và các filter types dự kiến.

### 6.2. Gradle Groovy DSL

**`settings.gradle`:**

```groovy
rootProject.name = 'opaque-authorities-lab'
```

**`build.gradle`:**

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot 3.5.16 được chọn để có baseline chính xác cho Spring Security 6.5.x, không phải lời khuyên dùng một dòng đã hết OSS support trong sản phẩm mới. Dự án cần JDK 17+ và Gradle/Gradle Wrapper tương thích.

### 6.3. application.yml

**`src/main/resources/application.yml`:**

```yaml
server:
  port: 8080

spring:
  application:
    name: opaque-authorities-lab
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${INTROSPECTION_URI:https://idp.example.invalid/oauth2/introspect}
          client-id: ${INTROSPECTION_CLIENT_ID:resource-api}
          client-secret: ${INTROSPECTION_CLIENT_SECRET:demo-only-not-production}
```

Cú pháp `${...}` của Spring placeholder được resolve từ environment; các giá trị default chỉ để chạy **lab local**, không phải bí mật thực. Nếu `bootRun` ngoài test rồi gọi `/api/reports` bằng token, app sẽ cố gọi `idp.example.invalid` và **không có dữ liệu bảo vệ được trả** vì domain không phải IdP. Cần cấu hình một Authorization Server thật để sử dụng ngoài tests.

Trong integration tests, `@DynamicPropertySource` override cả introspection URI, client-id và client-secret để trỏ tới MockWebServer. **Không cần cấu hình IdP thật để chạy `./gradlew test`.**

### 6.4. Main class

**`src/main/java/example/opaquelab/OpaqueAuthoritiesApplication.java`:**

```java
package example.opaquelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueAuthoritiesApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueAuthoritiesApplication.class, args);
    }
}
```

### 6.5. ScopeAndRoleIntrospector: decorator giữ scope, thêm role có điều kiện

**`src/main/java/example/opaquelab/ScopeAndRoleIntrospector.java`:**

```java
package example.opaquelab;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.user.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class ScopeAndRoleIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private static final String EXPECTED_AUDIENCE = "api://reports";

    private final ReactiveOpaqueTokenIntrospector delegate;

    public ScopeAndRoleIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token).flatMap(principal -> {
            Object audience = principal.getAttribute("aud");

            if (!audienceMatches(audience, EXPECTED_AUDIENCE)) {
                return Mono.error(new OAuth2AuthenticationException(
                        new OAuth2Error("invalid_token",
                                "Token audience is not this API", null)));
            }

            // Bảo toàn SCOPE_... do Spring introspector chuẩn đã tạo.
            Set<GrantedAuthority> authorities =
                    new LinkedHashSet<>(principal.getAuthorities());

            Object rawRoles = principal.getAttribute("app_roles");
            Object tenant = principal.getAttribute("tenant");

            // Chỉ cho role đã khai báo rõ, đúng tenant của lab.
            if ("acme".equals(tenant)
                    && rawRoles instanceof Collection<?> roles
                    && roles.contains("analyst")) {
                authorities.add(
                        new SimpleGrantedAuthority("ROLE_ANALYST"));
            }

            return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                    principal.getName(),
                    principal.getAttributes(),
                    authorities));
        });
    }

    private static boolean audienceMatches(
            Object audience, String expected) {
        if (audience instanceof String value) {
            return expected.equals(value);
        }
        if (audience instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false; // missing/unknown format -> deny
    }
}
```

**Giải thích cẩn thận:**

1. `delegate.introspect(token)` phải thành công trước khi code mapping chạy. Nếu token inactive/invalid, **không có principal** để cấp thêm role.
2. `audienceMatches` xử lý `aud` kiểu string hoặc collection; nếu thiếu, malformed hoặc không khớp, phát `OAuth2AuthenticationException` với `invalid_token`. Đây là **policy bổ sung do app quyết định**, không phải kiểm tra audience mặc định của mọi opaque introspector.
3. Dùng `new LinkedHashSet<>(principal.getAuthorities())` để giữ mọi `SCOPE_...` đã được delegate map, không tạo scope từ header/query do client cung cấp.
4. Chỉ giá trị `"analyst"` bên trong collection `app_roles` **và** `tenant="acme"` mới tạo `ROLE_ANALYST`. Giá trị `"admin"` hoặc `"ROLE_ANALYST"` không được tự động cấp quyền.
5. `new DefaultOAuth2AuthenticatedPrincipal(principal.getName(), principal.getAttributes(), authorities)` giữ cả tên principal lẫn các attributes đã được introspection server công bố, thay đổi duy nhất là collection authorities.
6. `flatMap` giữ pipeline reactive; không `block()`, không tự `subscribe()` và không dùng ThreadLocal làm security context.
7. `EXPECTED_AUDIENCE` và điều kiện tenant được hardcode vì đây là **lab một API, một tenant**. Ứng dụng thực phải lấy từ policy/config đáng tin và kiểm tra tenant ở resource/service, không dựa vào một kiểm tra role toàn cục.

**Lưu ý:** thư viện/introspection endpoint có thể thay đổi cách chuẩn hóa claims. Nếu `app_roles` là CSV string hoặc nested JSON khác, **không** nới `instanceof` bằng cast bừa. Hợp đồng API với IdP phải chỉ rõ định dạng và dữ liệu nào được phép cấp role.

### 6.6. SecurityConfiguration: introspection thật + mapping

**`src/main/java/example/opaquelab/SecurityConfiguration.java`:**

```java
package example.opaquelab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                    String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                    String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                    String clientSecret) {

        ReactiveOpaqueTokenIntrospector delegate =
                SpringReactiveOpaqueTokenIntrospector
                        .withIntrospectionUri(uri)
                        .clientId(clientId)
                        .clientSecret(clientSecret)
                        .build();

        return new ScopeAndRoleIntrospector(delegate);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/reports")
                            .hasAuthority("SCOPE_reports.read")
                        .pathMatchers(HttpMethod.GET, "/api/analyst")
                            .hasRole("ANALYST")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

**Các điểm bắt buộc:**

- Cấu hình `spring.security.oauth2.resourceserver.opaquetoken.*` đúng namespace Spring Boot. `@Value` lấy các giá trị từ property/environment; client secret của IdP thật phải được quản lý bằng secret manager.
- Bean `ReactiveOpaqueTokenIntrospector` của ứng dụng **thay thế default introspector** mà Boot có thể tạo. Không đồng thời đăng ký hai introspector với nghĩa không rõ hoặc gọi trực tiếp constructor Servlet `SpringOpaqueTokenIntrospector`.
- `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` là client reactive gọi endpoint thật; Spring Security thực hiện client authentication với IdP theo cấu hình.
- `SecurityWebFilterChain` dùng `.opaqueToken(Customizer.withDefaults())` để lấy bean `ReactiveOpaqueTokenIntrospector` tương thích.
- `/api/reports` yêu cầu **SCOPE_reports.read**, `/api/analyst` yêu cầu **ROLE_ANALYST**, `/api/me` cần token hợp lệ sau audience check.
- Không bật login form hoặc session cho demo, cũng không dùng JWT decoder; token được xác minh qua introspection.
- Chỉ có GET endpoints trong demo, nên CSRF mặc định không chặn nghiệp vụ. Nếu có browser ambient cookies hoặc unsafe methods phải phân tích CSRF riêng, không tắt bừa.

**Sự khác nhau giữa bean và DSL:** có thể gọi trực tiếp `.opaqueToken(opaque -> opaque.introspector(customBean))`; tuy nhiên chỉ cần tạo đúng một bean `ReactiveOpaqueTokenIntrospector` và dùng `Customizer.withDefaults()` như project này. Không cần cấu hình cùng một policy trong nhiều chỗ.

### 6.7. ReportsController: đọc principal và authorities

**`src/main/java/example/opaquelab/ReportsController.java`:**

```java
package example.opaquelab;

import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/reports")
    public Mono<String> reports(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Mono.just("reports-for-" + principal.getName());
    }

    @GetMapping("/api/analyst")
    public Mono<String> analyst() {
        return Mono.just("analyst-only");
    }

    @GetMapping("/api/me")
    public Mono<Map<String, Object>> me(
            BearerTokenAuthentication authentication) {

        var authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();

        return Mono.just(Map.of(
                "name", authentication.getName(),
                "authorities", authorities,
                "tenant", String.valueOf(
                        authentication.getTokenAttributes().get("tenant"))));
    }
}
```

**Đây là API kiểm thử với dữ liệu giả.** `/api/me` chỉ trả principal name, authorities và tenant để người học quan sát. Ở production không nên expose introspection attributes và role data bừa bãi; cần schema/authorization/logging policy. Đặc biệt không trả opaque Bearer token hay `client_secret`.

Spring Security đặt `BearerTokenAuthentication` vào Reactor Context sau introspection thành công. Trong WebFlux, `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` là cách lấy attributes; không dùng Servlet request/session APIs.

### 6.8. Luồng một request thành công

Ví dụ client gọi:

```http
GET /api/reports HTTP/1.1
Authorization: Bearer reader-token
```

Trong test, MockWebServer trả:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "reports.read",
  "aud": "api://reports",
  "tenant": "acme",
  "app_roles": ["viewer"]
}
```

Delegate tạo `SCOPE_reports.read`. Decorator audience check pass, không thêm `ROLE_ANALYST` vì không có role analyst. Kết quả:

- `GET /api/reports` → **200**, body `reports-for-alice`.
- `GET /api/analyst` → **403**, vì token hợp lệ nhưng không có ROLE_ANALYST.
- `GET /api/me` → **200**, danh sách authorities chứa `SCOPE_reports.read`.

Với `analyst-token`, introspection trả scope reports.read và `app_roles:["analyst"]`, `tenant=acme`, khi đó decorator thêm `ROLE_ANALYST` và cả hai endpoints protected được phép.

## 7. Integration test: MockWebServer cho introspection thật

Bài này **không dùng mock Authentication để bỏ qua introspection**. Nó dùng MockWebServer của OkHttp phục vụ HTTP endpoint cục bộ do test kiểm soát. Resource Server gọi endpoint đó bằng client reactive thật; các rule HTTP được kiểm tra bằng `WebTestClient` chạy Netty trên port ngẫu nhiên.

**`src/test/java/example/opaquelab/OpaqueAuthoritiesIntegrationTest.java`:**

```java
package example.opaquelab;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OpaqueAuthoritiesIntegrationTest {

    private static final String BASIC =
            "Basic " + Base64.getEncoder().encodeToString(
                    "resource-api:test-secret".getBytes(StandardCharsets.UTF_8));

    private static final MockWebServer IDP = startIdp();

    @DynamicPropertySource
    static void overrideIdp(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri",
                () -> IDP.url("/introspect").toString());
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.client-id",
                () -> "resource-api");
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.client-secret",
                () -> "test-secret");
    }

    @LocalServerPort int port;

    @Autowired
    ReactiveOpaqueTokenIntrospector introspector;

    private WebTestClient client;

    @BeforeEach
    void prepare() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @AfterAll
    static void stopIdp() throws IOException {
        IDP.shutdown();
    }

    private static MockWebServer startIdp() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                if (!"POST".equals(request.getMethod())
                        || !"/introspect".equals(request.getPath())) {
                    return new MockResponse().setResponseCode(404);
                }
                if (!BASIC.equals(request.getHeader("Authorization"))) {
                    return new MockResponse().setResponseCode(401);
                }

                String body = request.getBody().readUtf8();
                String token = Arrays.stream(body.split("&"))
                        .filter(part -> part.startsWith("token="))
                        .map(part -> URLDecoder.decode(
                                part.substring(6), StandardCharsets.UTF_8))
                        .findFirst().orElse("");

                return new MockResponse()
                        .setResponseCode(200)
                        .setHeader("Content-Type", "application/json")
                        .setBody(responseFor(token));
            }
        });

        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static String responseFor(String token) {
        return switch (token) {
            case "reader-token" -> """
                {
                  "active": true,
                  "sub": "alice",
                  "scope": "reports.read",
                  "aud": "api://reports",
                  "tenant": "acme",
                  "app_roles": ["viewer"]
                }
                """;
            case "analyst-token" -> """
                {
                  "active": true,
                  "sub": "ann",
                  "scope": "reports.read",
                  "aud": ["api://reports"],
                  "tenant": "acme",
                  "app_roles": ["analyst"]
                }
                """;
            case "spoof-role-token" -> """
                {
                  "active": true,
                  "sub": "bob",
                  "scope": "reports.read",
                  "aud": "api://reports",
                  "tenant": "acme",
                  "app_roles": ["ROLE_ANALYST", "admin"]
                }
                """;
            case "other-tenant-token" -> """
                {
                  "active": true,
                  "sub": "carol",
                  "scope": "reports.read",
                  "aud": "api://reports",
                  "tenant": "other",
                  "app_roles": ["analyst"]
                }
                """;
            case "write-only-token" -> """
                {
                  "active": true,
                  "sub": "dave",
                  "scope": "reports.write",
                  "aud": "api://reports",
                  "tenant": "acme",
                  "app_roles": ["viewer"]
                }
                """;
            case "wrong-audience-token" -> """
                {
                  "active": true,
                  "sub": "erin",
                  "scope": "reports.read",
                  "aud": "api://billing",
                  "tenant": "acme",
                  "app_roles": ["analyst"]
                }
                """;
            default -> """
                { "active": false }
                """;
        };
    }

    @Test
    void publicPingDoesNotNeedBearer() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void absentBearerTokenIs401() {
        client.get().uri("/api/reports")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void inactiveOpaqueTokenIs401() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("inactive-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerScopeAllowsReports() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reports-for-alice");
    }

    @Test
    void readerCannotAccessAnalystRoute() {
        client.get().uri("/api/analyst")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void analystRoleAllowsAnalystRoute() {
        client.get().uri("/api/analyst")
                .headers(h -> h.setBearerAuth("analyst-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("analyst-only");
    }

    @Test
    void analystStillHasOriginalScope() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("analyst-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reports-for-ann");
    }

    @Test
    void attackerStyleRoleStringDoesNotUpgradeRole() {
        client.get().uri("/api/analyst")
                .headers(h -> h.setBearerAuth("spoof-role-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void otherTenantDoesNotReceiveAnalystRole() {
        client.get().uri("/api/analyst")
                .headers(h -> h.setBearerAuth("other-tenant-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void validTokenWithoutReadScopeReturns403() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("write-only-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongAudienceIs401() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("wrong-audience-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void inspectorOutputContainsScopeAndMappedRole() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth("analyst-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("ann")
                .jsonPath("$.authorities[0]").isEqualTo("ROLE_ANALYST")
                .jsonPath("$.authorities[1]").isEqualTo("SCOPE_reports.read")
                .jsonPath("$.tenant").isEqualTo("acme");
    }

    @Test
    void stepVerifierSeesMappedAuthoritiesAndAttributes() {
        StepVerifier.create(introspector.introspect("analyst-token"))
                .assertNext(principal -> {
                    assertEquals("ann", principal.getName());
                    assertEquals("acme",
                            principal.getAttribute("tenant"));
                    var names = principal.getAuthorities().stream()
                            .map(a -> a.getAuthority()).toList();
                    assertTrue(names.contains("SCOPE_reports.read"));
                    assertTrue(names.contains("ROLE_ANALYST"));
                })
                .verifyComplete();
    }

    @Test
    void stepVerifierRejectsWrongAudience() {
        StepVerifier.create(introspector.introspect(
                        "wrong-audience-token"))
                .expectError(OAuth2AuthenticationException.class)
                .verify();
    }
}
```

### 7.1. Vì sao bộ test đáng tin cho bài toán mapping?

MockWebServer được tạo với port động bằng `server.start()`. `@DynamicPropertySource` đưa URL của nó vào bean introspector ngay từ lúc Spring Boot tạo ApplicationContext. Dù JWT/opaque token do test tự đặt, **SpringReactiveOpaqueTokenIntrospector vẫn thật sự gửi POST /introspect** qua HTTP client của Spring và nhận JSON như IdP.

- Test yêu cầu HTTP Basic `resource-api:test-secret` tại mock IdP; nếu Resource Server thiếu client credentials, mock trả 401.
- `reader-token` active, có scope reports.read nhưng không có role analyst.
- `analyst-token` active, có scope và role analyst, audience là **list**, kiểm tra được mapper xử lý nhiều dạng aud.
- `spoof-role-token` cố đưa string `ROLE_ANALYST` / `admin` vào attributes; allowlist không cấp quyền.
- `other-tenant-token` có `app_roles:["analyst"]` nhưng tenant khác acme, nên không có ROLE_ANALYST.
- `write-only-token` active nhưng chỉ có scope reports.write; endpoint yêu cầu reports.read nên bị 403.
- `wrong-audience-token` active và có role analyst nhưng không đúng Resource Server audience nên bị **401 trước authorization**.
- `inactive-token` có `active:false`, không được Spring coi là principal authenticated.

**Không nhầm kiểm thử này với IdP production:** mock IdP không thực hiện cấp token, không có revoke thật, không có network/TLS/certificate production. Mục tiêu là test chuỗi **introspection response → principal → GrantedAuthority → HTTP authorization** đúng.

### 7.2. Chạy tests

Từ thư mục project có Gradle Wrapper:

```bash
./gradlew test --tests example.opaquelab.OpaqueAuthoritiesIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.opaquelab.OpaqueAuthoritiesIntegrationTest
```

Nếu Gradle đã được cài tương thích:

```bash
gradle test --tests example.opaquelab.OpaqueAuthoritiesIntegrationTest
```

**Kết quả dự kiến:** 14 test PASS với project, dependencies và runtime Java phù hợp, khi có quyền bind cổng loopback. Đây là kết quả *kỳ vọng từ code*, **chưa phải log biên dịch/kiểm thử thực tế** trong workspace của người học.

Lưu ý vòng đời test: `IDP` là static MockWebServer và được đóng tại `@AfterAll`; chỉ một test class sử dụng nó, không chia sẻ với các context khác có vòng đời dài hơn. Tests không dựa vào thứ tự chạy vì dispatcher trả JSON bất biến theo tên token.

### 7.3. Những giới hạn cần hiểu

- Dùng HTTP loopback cho introspection test; production phải HTTPS và xác minh server certificate.
- Không test timeout, rate limit, cache, multiple instances hoặc token revocation tại IdP thật.
- `SpringReactiveOpaqueTokenIntrospector` quyết định parse các trường và scope theo implementation 6.5; test thực tế phải được chạy trên dependency versions cụ thể.
- Mọi role trong ví dụ chỉ là tên giả và một tenant `acme`. Production cần business policy riêng, tenant-aware storage, auditing và quyền theo tài nguyên.
- Không dùng `mockOpaqueToken()` trong bài test end-to-end introspection này, vì nó có thể bypass introspector; tuy nhiên `mockOpaqueToken()` vẫn rất hữu ích khi **chỉ muốn unit-test authorization mapping** mà không cần network.

## 8. Không đánh đồng introspection, scope và business permission

### Ví dụ sai về quyền theo bản ghi

Một token có:

```text
SCOPE_reports.read
ROLE_ANALYST
tenant = acme
sub = alice
```

Token này **không tự cho phép** đọc báo cáo của mọi tenant hoặc mọi người dùng. Nếu service thực hiện:

```java
// Anti-pattern minh họa: không kiểm tra tenant/owner.
return reportRepository.findById(reportId);
```

thì có thể xảy ra IDOR, dù token active, scope và role đều đúng.

Một hướng thiết kế tốt hơn là lấy tenant/user đã xác minh từ `Authentication` và đưa vào query theo ownership:

```java
// Fragment minh họa, reportRepository phải được định nghĩa trong app thật.
return reportRepository.findByIdAndTenantId(reportId, authenticatedTenant)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
```

Cách này giúp quyền theo dữ liệu được kiểm tra ở truy vấn, tránh tình trạng đọc record trước rồi mới so sánh tenant hoặc lộ tồn tại tài nguyên không được phép.

**Không nhầm `tenant` là role.** Tenant là namespace xác định dữ liệu/khách hàng; role là capability trong namespace đó. `SCOPE_reports.read` có thể là quyền cấp ở OAuth2 Client/Resource Server, nhưng ownership phải được áp theo thực tế.

### Service method security

Trong WebFlux, có thể bật reactive method security và áp `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` ở service khi phù hợp. Tuy nhiên, annotation không thay dữ liệu tenant trong query và phải đảm bảo method trả `Mono`/`Flux` theo hợp đồng Reactor Context, không làm mất SecurityContext giữa threads.

Cấu hình WebFlux reactive method security khác Servlet (sử dụng `@EnableReactiveMethodSecurity`). Hãy test authorization tại HTTP layer và service layer nếu cả hai cùng được cấu hình.

## 9. Role mapping sai có thể nâng quyền thế nào?

### 9.1. Sao chép chuỗi role tùy ý

Sai:

```java
// Anti-pattern: mọi giá trị roles từ IdP đều được nâng thành Spring role.
for (String role : roles) {
    authorities.add(new SimpleGrantedAuthority("ROLE_" + role));
}
```

Nếu client kiểm soát nguồn role, hoặc IdP định nghĩa role với semantics khác, có thể cấp quyền vượt mong muốn. Nên map **giá trị đã whitelist** vào **authority cụ thể**:

```java
if (roles.contains("analyst")
        && "acme".equals(tenant)) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ANALYST"));
}
```

Với production, kiểm tra thêm issuer/client_id/audience, tenant/resource policy và trust boundary. Không tự cấp ROLE_ADMIN từ một chuỗi trông có vẻ hợp lệ.

### 9.2. Làm mất scope sau khi custom

Sai:

```java
return new DefaultOAuth2AuthenticatedPrincipal(
        principal.getName(),
        principal.getAttributes(),
        List.of(new SimpleGrantedAuthority("ROLE_ANALYST")));
```

Đoạn này **ghi đè** scope authorities đã có. Kết quả `hasAuthority("SCOPE_reports.read")` thất bại dù token có scope đọc. Trong bài lab, mapper khởi tạo Set từ `principal.getAuthorities()` để bảo toàn scope, rồi mới thêm ROLE_ANALYST theo policy.

### 9.3. Bỏ qua `active` hoặc tưởng chỉ scope là đủ

Một introspection response inactive:

```json
{"active":false}
```

không được phép tạo principal có authorities. **Chỉ mã kiểm tra sau khi delegate xác minh token mới được map scopes/roles**. Nếu bạn tự viết một introspector trả principal mà không kiểm tra active, sẽ biến bất kỳ Bearer token thành authenticated.

### 9.4. Trộn role của người dùng và client

`client_credentials` có thể là service-to-service token, không nhất thiết có Resource Owner `sub` giống user token. Nếu code thấy `client_id=reports-worker` rồi cấp ROLE_ANALYST tương tự user analyst, có thể tạo confused deputy hoặc overly privileged service. Cần chính sách riêng cho service identities, scopes/audience và caller type.

### 9.5. Chấp nhận `aud` không phù hợp

Một introspection response active với scope reports.read nhưng `aud=api://billing` không được dùng để gọi API reports. Bộ kiểm tra audience trong decorator là chủ ý. Một số Authorization Server không trả `aud`; khi đó cần hợp đồng riêng về resource indicator, client binding, issuer/trust và scope policy, **không mặc định bỏ audience check khi thay provider**.

## 10. 401, 403 và HTTP flow trong Resource Server Opaque

| Request / token | Introspection | Authorities | Kết quả |
| --- | --- | --- | --- |
| Không Bearer | Không cần introspect | Không có | 401 cho protected endpoint |
| Bearer token không active | `active=false` | Không tạo principal | 401 |
| Token active nhưng audience sai | Verify active, custom reject | Không cấp authorities | 401 |
| Token active, scope `reports.write` | Pass | `SCOPE_reports.write` | 403 khi endpoint cần reports.read |
| Token active, `reports.read` | Pass | `SCOPE_reports.read` | 200 ở /api/reports |
| Token active, role analyst đúng policy | Pass | `SCOPE_reports.read`, `ROLE_ANALYST` | 200 ở /api/analyst |
| Token active, role string "admin" ngoài allowlist | Pass | Giữ scope, không ROLE_ANALYST | 403 ở /api/analyst |
| Introspection timeout/down | Không xác minh được token | Không được cấp quyền | Từ chối; mã HTTP tùy error handling |

Đừng mặc định mọi lỗi introspection timeout **luôn** trả 401: nếu exception xảy ra trong service integration, status có thể là 5xx tùy pipeline/error translation. Bất biến bảo mật là **không trả dữ liệu bảo vệ khi không xác minh được token**.

### Không coi CORS là bảo vệ token

CORS áp cho browser JS cross-origin; cURL/máy chủ khác có thể không gửi Origin. Resource Server phải **luôn** kiểm tra Bearer token và authorities, độc lập với CORS. Nếu API đồng thời dùng session cookie/browser auth, cũng cần đánh giá CSRF cho unsafe methods; opaque Bearer token truyền bằng header không tự động đồng nghĩa mọi browser attack vector đều biến mất.

## 11. Vận hành: mỗi request có thể gây introspection

### 11.1. Độ trễ và số lượng request

Với phương pháp introspection, Resource Server thường **hỏi Authorization Server về trạng thái token** thay vì tự verify JWT chữ ký offline. Điều này thuận tiện khi cần trạng thái thu hồi, nhưng tạo phụ thuộc mạng:

- Latency của Authorization Server tăng thời gian phản hồi API.
- Introspection endpoint down có thể làm request hợp lệ bị từ chối.
- Rất nhiều API requests có thể gây tải lớn lên introspection service nếu không có cache hoặc tầng tối ưu.
- IdP có thể áp rate limit, timeout, backpressure và quota.

Không viết code `block()` trong Reactor event-loop khi gọi HTTP introspection. SpringReactiveOpaqueTokenIntrospector dùng reactive client; nếu có custom enrichment tới API/DB khác, cũng compose `Mono.flatMap` và giới hạn concurrency.

### 11.2. Cache introspection vs revocation

Cache có thể cải thiện latency nhưng giảm độ mới của trạng thái `active`, audience/roles/scopes, đặc biệt khi token bị revoke hoặc user bị gỡ quyền.

| Cấu hình cache | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Không cache response | Kiểm tra active hiện tại mỗi lần introspection | Tăng phụ thuộc mạng và latency |
| Cache TTL ngắn | Giảm tải, latency | Quyền/token có thể còn hiệu lực trong TTL sau revoke |
| Cache TTL dài | Hiệu năng cao | Cửa sổ revocation stale lớn, role thay đổi không được cập nhật kịp |
| Cache key thiếu ngữ cảnh | Đơn giản hóa sai | Trộn token/tenant/issuer, có thể cấp nhầm quyền |

Cần quyết định TTL theo chính sách thu hồi token của IdP, token `exp`, audit và service-level risk. Đừng cache active=true vô thời hạn. Nếu cache key dựa trên token, **đừng log hoặc phát token raw**; dùng hash/HMAC phù hợp cho observability, và áp isolation theo issuer/client/tenant trong cache design.

### 11.3. Bảo vệ introspection credentials

Resource Server thường cần `client-id` và `client-secret` để xác thực với introspection endpoint. Đây là **credential của API khi gọi IdP**, khác với Bearer token người dùng gửi vào.

- Không commit secret vào Git, config mẫu hoặc README.
- Đặt secret trong secret manager/env với rotation policy.
- Chỉ gọi `https://...` có TLS certificate validation và hostname validation khi production.
- Không gửi secret vào logs/traces và không trả HTTP Basic header của backend ra client.
- Khi provider hỗ trợ client authentication mạnh hơn (mTLS/private_key_jwt), chọn cơ chế phù hợp với policy IdP và Spring API tương ứng.
- Xem network egress allowlist, DNS và proxy security để không bị redirect secret sang host khác.

### 11.4. Xác thực thêm `exp` / `aud` / `iss` thế nào?

Trong opaque introspection, **Authorization Server là nguồn quyết định active**, nhưng các yêu cầu policy riêng của Resource Server (API audience, tenant, issuer) vẫn cần kiểm tra nếu response cung cấp dữ liệu. Không đánh đồng "active=true" với "token dành cho API này và có đủ quyền".

Một số IdP trả `aud` dạng list, một số string; format cần được thỏa thuận. Nếu bắt buộc kiểm tra `iss`, đừng giả định mọi provider đều trả iss. Nếu `exp` hiện diện nhưng đã quá hạn, nên có policy rõ cùng IdP; không tự cấp quyền dựa vào claim mà chưa được introspection xác nhận. Trong code sản xuất, cần xử lý clock skew hợp lý, token_type/client restrictions nếu hợp đồng yêu cầu.

### 11.5. Multi-tenant, multi-issuer

Nếu Resource Server phục vụ nhiều tenant/issuer, không dùng một global `ROLE_ANALYST` mà bỏ qua tenant. Thiết kế mapping:

- Xác định trust domain của introspection endpoint và principal.
- Kiểm tra audience/resource ID chính xác.
- Xác định tenant identity đã được chứng thực và ràng buộc tenant với tài nguyên.
- Role mapping phải nằm trong namespace/tenant được cho phép.
- Nếu nhiều IdP, dùng resolver/manager selection dựa trên cấu hình allowlist, **không dùng arbitrary URL từ request** để gọi introspection (SSRF/credential leakage).
- Không tự cho user nhập client_id/introspection URL để lấy quyền của một provider khác.

## 12. Trường hợp khác: introspection cả JWT

Cách Resource Server xử lý dựa vào **chiến lược xác thực**, không hoàn toàn dựa vào hình dạng token. Một JWT access token có thể được gửi tới **introspection endpoint** để kiểm tra revocation thay vì chỉ verify chữ ký local. Spring Security opaque token support có thể áp dụng chiến lược đó dù token nhìn giống JWT.

Tuy nhiên:

- Không dùng decoded JWT payload **chưa verify** làm nguồn cấp `GrantedAuthority`.
- Một introspector có thể nhận active=true và trả attributes; các thuộc tính đó phải được xem là dữ liệu từ trusted Authorization Server.
- Nếu cần thêm claims của JWT, phải có thiết kế rõ signature/claim validation hoặc bảo đảm introspection hoàn toàn quyết định và thông tin bổ sung không dùng để cấp quyền vượt chính sách.
- Đừng copy một ví dụ "parse-only JWT" rồi vô tình đưa claims chưa verify thành ROLE_ADMIN.
- Nếu dùng JWT offline Resource Server, `ReactiveJwtDecoder` và JWT validators là cơ chế khác với `ReactiveOpaqueTokenIntrospector`.

## 13. Các lỗi thường gặp

| Lỗi | Biểu hiện | Cách sửa |
| --- | --- | --- |
| Dùng `OpaqueTokenIntrospector` Servlet | Sai reactive stack | Dùng `ReactiveOpaqueTokenIntrospector` |
| Sai `opaquetoken` property | Boot không cấu hình đúng | Dùng `spring.security.oauth2.resourceserver.opaquetoken.*` |
| Introspection URI trỏ token endpoint | 401/404/parse lỗi | Dùng endpoint RFC 7662 thật |
| Bỏ client-id/client-secret | IdP không cho introspect | Cấu hình client credentials từ secret manager |
| Active=false vẫn tạo principal | Lỗ hổng authentication | Dùng trusted delegate, fail closed |
| Tự tạo `SCOPE_` từ query/header | Privilege escalation | Chỉ dùng verified introspection scope |
| Dùng `hasRole("reports.read")` | So sánh ROLE_ sai nghĩa | Dùng `hasAuthority("SCOPE_reports.read")` |
| Dùng `hasAuthority("analyst")` nhưng mapper tạo ROLE_ANALYST | String không khớp | Dùng `hasRole("ANALYST")` hoặc exact ROLE_ANALYST |
| Custom mapper làm mất authorities mặc định | Scope route thành 403 | Bắt đầu từ `principal.getAuthorities()` |
| `app_roles` cast List<String> bừa | ClassCastException | `instanceof Collection<?>`, schema validation |
| Copy raw role names thành `ROLE_*` | Overprivilege | Allowlist role values + context |
| Audience không kiểm tra | Token dành cho API khác dùng được | Kiểm tra `aud` theo resource policy |
| Tenant không kiểm tra ở database | IDOR, cross-tenant data | Predicate tenant/owner ở repository/service |
| Tin `client_id` như user name | Confused deputy | Phân biệt service client vs resource owner |
| Introspection timeout bị trả 200 fallback | Lỗ hổng fail-open | Error handling fail closed |
| Cache `active=true` lâu | Token revoke vẫn có quyền | TTL ngắn theo chính sách, invalidate |
| Cache theo registrationId thay token/principal | Trộn identity | Key đầy đủ, isolation |
| Log `Authorization: Bearer` | Lộ access token | Redact token và credentials |
| Endpoint introspection HTTP public | MITM/credential theft | HTTPS + cert/hostname verify |
| Test chỉ dùng mockOpaqueToken | Không kiểm tra call introspection thật | Thêm MockWebServer integration test |
| Role analyst ở tenant khác có quyền acme | Cross-tenant privilege | Tenant-aware mapping và data auth |
| Dùng `block()` trong Netty | Event loop bị chặn | Compose reactive Mono/Flux |
| Đặt token trong URL | Token rò qua logs/history | Authorization Bearer header |
| Lấy toàn bộ attrs trả cho client | Rò thông tin IdP | Tối thiểu hóa response/PII |
| Sai phân biệt 401 và 403 | Khó debug | Tách authentication vs authorization |
| Tắt mọi security vì introspection 5xx | Bypass token validation | Fix endpoint/TLS/client auth/timeout |

## 14. Checklist review và bài tập

### Checklist production

1. Resource Server dùng WebFlux, `SecurityWebFilterChain` và `ReactiveOpaqueTokenIntrospector`, không trộn Servlet.
2. Introspection endpoint HTTPS đáng tin, client credentials trong secret manager.
3. `active=false`, lỗi token hoặc lỗi mạng **không được cấp quyền**.
4. Default scope mapping được giữ hoặc thay đổi có chủ đích; có test `SCOPE_...`.
5. Role mapping chỉ lấy từ các attributes đã xác minh, whitelist chặt giá trị role và tenant.
6. Audience/resource/client restrictions được kiểm tra theo hợp đồng IdP.
7. `Authentication.getName()`/sub được định nghĩa rõ cho user token và service token.
8. Scope ở HTTP, owner/tenant/resource ở service/DB được kiểm tra đầy đủ.
9. Token/secret không xuất hiện trong log, URL hoặc public JSON.
10. Introspection timeout, rate limit, caching, revocation và key isolation được giám sát.
11. Negative tests: no bearer, inactive, wrong aud, no scope, spoofed role, wrong tenant, 401/403.
12. Test actual HTTP introspection và client authentication, không chỉ mockUser/mockOpaqueToken.
13. Không gửi token/secret tới endpoint IdP bất kỳ do user chỉ định.
14. Audit quyền đặc biệt (admin/analyst), xem xét deny-by-default và least privilege.
15. Tăng coverage nếu có method security, multi-chain hoặc đa tenant.

### Bài tập

1. Với response `scope="reports.read reports.write"`, liệt kê hai authorities mặc định và viết biểu thức `hasAuthority` tương ứng.
2. Giải thích vì sao `hasRole("ANALYST")` không được thỏa chỉ bởi scope `reports.read`.
3. Thêm role `reviewer` vào allowlist theo hợp đồng IdP, map thành `ROLE_REVIEWER` chỉ cho tenant acme.
4. Thử bỏ dòng `new LinkedHashSet<>(principal.getAuthorities())` rồi chạy test: vì sao SCOPE_reports.read mất?
5. Thêm token `active=false` nhưng chứa `scope:reports.admin`: đảm bảo 401.
6. Thay `aud` bằng `api://billing`: vì sao token active vẫn bị từ chối?
7. Thử `app_roles:["ROLE_ANALYST"]`, chỉ rõ tại sao mapper không cấp ROLE_ANALYST.
8. Chuyển app sang multi-tenant, cập nhật mapping để kiểm tra tenant theo resource thay vì hardcode một tenant.
9. Thêm WebTestClient test cho `/api/me` không có token, xác nhận 401.
10. Dùng StepVerifier trực tiếp trên introspector, kiểm tra metadata vẫn giữ `sub` và tenant.
11. Mô phỏng IdP timeout/500 bằng MockWebServer, xác minh fail closed và không gọi controller.
12. Đánh giá cache TTL theo yêu cầu token revocation (30 giây, 5 phút, không cache) và ảnh hưởng lên availability.
13. So sánh `ReactiveOpaqueTokenIntrospector` với `ReactiveJwtDecoder`: khi nào cần network, chữ ký và revoke?
14. Thêm endpoint theo tài nguyên ID, truy vấn `findByIdAndTenantId` để chống IDOR.
15. So sánh chỉ test `mockOpaqueToken()` với integration test MockWebServer trong bài: test nào xác thực được việc gọi introspection endpoint?

## Tổng kết

**Spring Security WebFlux Resource Server Opaque** xác thực Bearer token qua `ReactiveOpaqueTokenIntrospector`. Khi Authorization Server trả token active cùng scope, Spring chuyển mỗi scope thành `SCOPE_<scope>`, rồi đặt các authority đó trên `OAuth2AuthenticatedPrincipal` / `BearerTokenAuthentication`. Các trường như `tenant` hoặc `app_roles` **không tự trở thành role**.

Để bổ sung role, dùng **decorator** bọc introspector thật, **giữ nguyên authorities mặc định**, kiểm tra audience/tenant/schema của thuộc tính đã tin cậy và chỉ ánh xạ những role được allowlist. `hasAuthority("SCOPE_reports.read")` và `hasRole("ANALYST")` áp dụng hai chính sách khác nhau; cả hai vẫn không thay thế kiểm tra owner/tenant của tài nguyên.

Khi introspection fail hoặc token inactive, **không cấp quyền**. Trong môi trường production, bổ sung HTTPS, quản lý credentials, cache/revocation/timeout, monitoring và negative tests.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Reactive OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — OAuth2 WebFlux Overview](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [Spring Security — ReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security — SpringReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security — OAuth2AuthenticatedPrincipal Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html)
- [Spring Security — DefaultOAuth2AuthenticatedPrincipal Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/user/DefaultOAuth2AuthenticatedPrincipal.html)
- [Spring Security — BearerTokenAuthentication Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html)
- [Spring Security — Reactive Web Test Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Boot 3.5 — Spring Security for Reactive Web](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
