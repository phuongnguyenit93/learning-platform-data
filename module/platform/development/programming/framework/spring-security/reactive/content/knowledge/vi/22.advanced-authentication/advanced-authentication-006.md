# Phối hợp cơ chế tùy chỉnh với HTTP Basic hoặc Bearer token

> **Chủ đề cha:** Xác thực mở rộng. **Nền tảng:** Spring Security reactive / Spring WebFlux, Java 17+, Spring Boot 3.x, Spring Security 6.5.x. Bài này triển khai cơ chế API key tùy chỉnh bên cạnh **HTTP Basic** và **OAuth2 Bearer token**, giải thích converter, manager, WebFilter order, quyết định khi credential không phù hợp hoặc không hợp lệ, authorization theo role/scope, kiểm thử và vận hành. Ví dụ sử dụng custom authentication scheme `Authorization: ApiKey <key>` — một quy ước demo có chủ đích, **không phải OAuth2 Bearer token** hay chuẩn API key chung cho mọi hệ thống.

## 1. Mục tiêu

Sau bài này bạn sẽ:

1. Hiểu một request WebFlux có thể dùng **một trong các cơ chế** Basic, Bearer JWT, ApiKey, nhưng không được tùy tiện ghép hay fallback khi xác thực sai.
2. Phân biệt **authentication** (xác minh danh tính) với **authorization** (kiểm quyền) trên cùng endpoint.
3. Biết `ServerAuthenticationConverter` tạo đối tượng Authentication **chưa xác thực**, `ReactiveAuthenticationManager` kiểm tra và trả Authentication đã xác thực.
4. Phân biệt `Mono.empty()` khi scheme không khớp với `Mono.error(AuthenticationException)` khi credential đã nhận diện nhưng sai.
5. Cấu hình `AuthenticationWebFilter` tùy chỉnh trong `SecurityWebFilterChain` mà **không làm hỏng** HTTP Basic hoặc JWT Resource Server sẵn có.
6. Đặt filter tại `SecurityWebFiltersOrder.AUTHENTICATION`, biết tại sao không thể dựa vào thứ tự giữa hai filters có cùng order.
7. Bảo vệ API bằng `hasAnyAuthority` với authorities đáng tin cậy được cấp từ các cơ chế khác nhau; API key read-only không thể tự thành admin.
8. Kiểm 401/403 và từ chối nhiều Authorization headers mâu thuẫn.
9. Dùng `WebTestClient` kiểm Basic đúng/sai, JWT đúng/sai/thiếu scope, ApiKey đúng/sai, duplicate header và quyền admin.
10. Hiểu biến thể **HTTP Basic + custom**, **Bearer + custom**, **JWT vs opaque**, và kiến trúc nhiều security chains theo URL.
11. Bảo vệ credentials qua TLS, secret store, key rotation, scopes, JWT issuer/audience, CORS/CSRF và logs không chứa secret.

**Quy tắc chính:** Scheme không khớp thì bỏ qua filter; scheme khớp nhưng xác thực sai thì **fail closed**. Không âm thầm biến lỗi thành một cơ hội thử cơ chế kém an toàn hơn.

## 2. Ba loại Authorization credential

```http
# HTTP Basic: credentials là username:password được mã hóa Base64
Authorization: Basic <BASE64_CREDENTIALS>

# OAuth2 Bearer: access token do IdP/Authorization Server cấp
Authorization: Bearer <ACCESS_TOKEN>

# Tùy chỉnh: key do hệ thống của bạn cấp và quản lý
Authorization: ApiKey <HIGH_ENTROPY_API_KEY>
```

**Lưu ý:** HTTP Basic Base64 **không bảo mật** thông tin nếu truyền trên HTTP không có TLS. OAuth2 Bearer có ý nghĩa protocol theo RFC 6750, phải được Resource Server kiểm bằng JWT signature/claims hoặc opaque introspection. Custom ApiKey là một contract riêng; không lấy key bất kỳ rồi đặt trong Bearer để tránh xác minh JWT.

### 2.1 Authentication không phải authorization

| Danh tính | Cách xác thực | Authority sau khi xác minh | Route được phép |
| --- | --- | --- | --- |
| `reader` | Basic password đúng | `ROLE_BASIC_READ` | `GET /api/read` |
| `administrator` | Basic password đúng | `ROLE_BASIC_READ`, `ROLE_ADMIN` | Đọc và `GET /api/admin` |
| `jwt-alice` | Bearer JWT hợp lệ | `SCOPE_messages.read` | `GET /api/read` |
| `jwt-admin` | Bearer JWT hợp lệ có scope admin | `SCOPE_api.admin` | `GET /api/admin` |
| `partner-integration` | API key đúng | `ROLE_PARTNER_READ` | `GET /api/read`, **không** được admin |

Một key đã hợp lệ không có nghĩa được cấp mọi quyền; tương tự Bearer token có thể active nhưng thiếu scope. Những authorities trong bảng chỉ được tạo **sau khi nguồn xác thực đáng tin cậy kiểm chứng**.

### 2.2 Vì sao cần nhiều cơ chế?

Trong giai đoạn migration, internal clients có thể còn dùng Basic, web/mobile clients dùng Bearer, một số tích hợp đối tác dùng API key. Có thể chấp nhận chúng cùng endpoint khi đã đánh giá trust boundary, hoặc tách URL/security chain cho rõ ràng. Thông thường nên ưu tiên OAuth2 client_credentials cho machine clients mới khi hệ sinh thái hỗ trợ, thay vì xây cả token lifecycle tùy chỉnh.

## 3. Pipeline reactive và API liên quan

```text
HTTP Request
   |
   | Authorization: Basic / Bearer / ApiKey
   v
Spring Security SecurityWebFilterChain
   |
   +-- HTTP Basic AuthenticationWebFilter
   |      -> Basic converter -> username/password -> password encoder
   |      -> success / AuthenticationException
   |
   +-- OAuth2 Resource Server Bearer authentication
   |      -> Bearer token converter
   |      -> ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector
   |      -> success / AuthenticationException
   |
   +-- Custom AuthenticationWebFilter
   |      -> ServerAuthenticationConverter cho ApiKey
   |      -> ApiKeyAuthenticationToken chưa xác thực
   |      -> ApiKeyAuthenticationManager so với server-side key
   |      -> trusted Authentication với ROLE_PARTNER_READ
   |
   v
ReactiveSecurityContextHolder / SecurityContext
   |
   v
authorizeExchange: HTTP method, path, authorities
   |
   +-- đủ quyền -> Controller
   +-- thiếu quyền -> 403
   +-- không xác thực được -> 401
```

### 3.1 Phân vai class

| Spring type | Vai trò |
| --- | --- |
| `ServerHttpSecurity` | Cấu hình chuỗi WebFlux security |
| `SecurityWebFilterChain` | Chọn WebFilters áp dụng cho request |
| `AuthenticationWebFilter` | WebFilter cho một loại authentication attempt |
| `ServerAuthenticationConverter` | Chuyển `ServerWebExchange` thành Authentication chưa xác thực |
| `ReactiveAuthenticationManager` | Xác minh credentials, tạo principal và authorities |
| `AbstractAuthenticationToken` | Base class để tạo custom Authentication object |
| `SecurityWebFiltersOrder` | Gắn custom filter vào đúng phase |
| `ReactiveSecurityContextHolder` | Truy cập SecurityContext trong Reactor Context |
| `MapReactiveUserDetailsService` | Tập user/password dành cho HTTP Basic demo |
| `ReactiveJwtDecoder` | Xác minh JWT của Bearer Resource Server |
| `ServerBearerTokenAuthenticationConverter` | Trích Bearer token trong WebFlux |
| `ServerAuthenticationEntryPointFailureHandler` | Chuyển authentication failure thành HTTP entrypoint |
| `NoOpServerSecurityContextRepository` | Tránh lưu authentication vào session |

**Không dùng Servlet classes** như `HttpSecurity`, `OncePerRequestFilter` và `SecurityFilterChain` cho WebFlux Netty. Cấu hình reactive cần `ServerHttpSecurity` và `SecurityWebFilterChain`.

### 3.2 Quy tắc Mono của converter và manager

| Request header | Custom ApiKey converter | Manager / xử lý tiếp |
| --- | --- | --- |
| Không có Authorization | `Mono.empty()` | Không có attempt ApiKey; endpoint protected sẽ yêu cầu auth |
| `Basic ...` | `Mono.empty()` | Built-in Basic filter xử lý |
| `Bearer ...` | `Mono.empty()` | OAuth2 Resource Server filter xử lý |
| `ApiKey <correct>` | `Mono.just(ApiKeyAuthenticationToken.unauthenticated(key))` | Manager xác minh key, cấp principal |
| `ApiKey <incorrect>` | Tạo token chưa xác thực | Manager phát `BadCredentialsException`, trả 401 |
| `ApiKey` không có value | `Mono.error(BadCredentialsException)` | 401, không được chuyển sang anonymous |
| Nhiều Authorization header fields | Guard sớm từ chối | 400 theo policy demo |

Với manager:

- `Mono.just(authenticated)` = đã verify credential thành công.
- `Mono.empty()` = manager **không hỗ trợ loại Authentication** này; không có quyết định.
- `Mono.error(AuthenticationException)` = đã có attempt nhưng thất bại. **Không chuyển thành empty** để thử provider yếu hơn.

### 3.3 Ví dụ fallback sai

```java
// KHÔNG DÙNG: swallowing authentication failure
return apiKeyManager.authenticate(input)
    .onErrorResume(ex -> basicManager.authenticate(input));
```

Credential ApiKey sai không được tạo cơ hội thử Basic hoặc dùng session cũ. Phân tuyến dựa trên **scheme** trước khi xác minh. Với `DelegatingReactiveAuthenticationManager` cũng phải giữ nghĩa `Mono.empty` là unsupported, `Mono.error` là failure; `setContinueOnError(true)` cần threat model riêng, không bật chỉ để “có fallback”.

## 4. Một chain hay nhiều security chains?

### 4.1 Một chain cho cả ba cơ chế

Có thể dùng chung `GET /api/read`:

```text
Authorization: Basic valid    -> ROLE_BASIC_READ -> 200
Authorization: Bearer valid   -> SCOPE_messages.read -> 200
Authorization: ApiKey valid   -> ROLE_PARTNER_READ -> 200
Credential sai/malformed     -> 401
Credential đúng thiếu quyền -> 403
```

Cách này phù hợp migration hoặc endpoint thực sự yêu cầu chấp nhận nhiều loại client. Nhược điểm là các test/guard về scheme, duplicate header và authorities phải chi tiết.

### 4.2 Tách chain khi trust boundary khác nhau

Ví dụ:

```text
/internal/**  -> Basic + mạng nội bộ
/api/**       -> Bearer JWT/opaque Resource Server
/partner/**   -> ApiKey custom hoặc OAuth2 client_credentials
/**           -> denyAll
```

Spring Security WebFlux hỗ trợ nhiều `SecurityWebFilterChain` beans với `@Order` và `securityMatcher(...)`. Mỗi request chọn **chain đầu tiên khớp matcher**; authentication failure **không làm Spring chạy chain tiếp theo**. Dùng catch-all denyAll cuối, không mở mặc định bằng permitAll.

Bài thực hành chính dưới đây dùng **một chain**, sau đó trình bày biến thể tách chain.

## 5. Project Java 17+ hỗ trợ Basic, Bearer JWT và custom ApiKey

Ví dụ có năm classes:

```text
src/main/java/com/example/multiauth/
  MultiAuthApplication.java
  ApiKeyAuthenticationToken.java
  ApiKeyAuthenticationManager.java
  MultiAuthSecurityConfig.java
  ReadController.java
src/main/resources/
  application.yml
src/test/java/com/example/multiauth/
  MultiAuthHttpTest.java
```

Các file cần dependency Spring Boot/WebFlux/Security, nên không thể chỉ chạy `javac` thiếu classpath. Để kiểm JWT offline, test inject fake decoder **chỉ trong test source set**. Production phải dùng JWT decoder thật với trusted IdP/JWKS, issuer, expiry và audience validation.

### 5.1 build.gradle dependencies

Tạo project Spring Initializr với Spring Boot 3.x, Java 17+, Gradle, Reactive Web, Security và OAuth2 Resource Server. Trong file `build.gradle` đã có Spring Boot plugin và dependency management, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` nếu app phải chạy WebFlux, vì khi cả MVC/WebFlux có mặt Spring Boot thường chọn MVC mặc định.

### 5.2 application.yml

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks

app:
  security:
    api-key: ${DEMO_API_KEY}
```

- `issuer-uri` là giá trị tin cậy của claim `iss`; `jwk-set-uri` trỏ tới bộ khóa verify chữ ký.
- Khi có cả issuer và JWKS URI, Spring Security tiếp tục kiểm issuer, chứ không bỏ issuer validation.
- API production phải kiểm thêm `aud`, `exp`, `nbf`, allowed algorithms và JWK rotation phù hợp với IdP.
- `example.test` là domain minh họa không có service chạy thật; thay bằng IdP đã đăng ký khi làm integration.
- `DEMO_API_KEY` là key từ environment hoặc secrets manager; **không commit production key vào YAML/repo**. Mẫu một-key dùng digest trong RAM để minh họa, không phải kiến trúc key registry production.

### 5.3 MultiAuthApplication.java

`src/main/java/com/example/multiauth/MultiAuthApplication.java`:

```java
package com.example.multiauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiAuthApplication.class, args);
    }
}
```

### 5.4 ApiKeyAuthenticationToken.java

Custom Authentication phải tách **chưa xác thực** và **đã xác thực**. Đừng tạo principal có authority từ request header khi key chưa được verify.

`src/main/java/com/example/multiauth/ApiKeyAuthenticationToken.java`:

```java
package com.example.multiauth;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private String apiKey;

    private ApiKeyAuthenticationToken(
            String principal,
            String apiKey,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {

        super(authorities);
        this.principal = principal;
        this.apiKey = apiKey;
        if (verified) {
            // Only trusted factory path should set this true.
            super.setAuthenticated(true);
        }
    }

    public static ApiKeyAuthenticationToken unauthenticated(String key) {
        return new ApiKeyAuthenticationToken(
            "unverified", key, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {

        return new ApiKeyAuthenticationToken(
            principal, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return apiKey;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        apiKey = null;
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                "Cannot mark an unverified API key as authenticated");
        }
        super.setAuthenticated(false);
    }

    @Override
    public String toString() {
        return "ApiKeyAuthenticationToken[credentials=REDACTED]";
    }
}
```

**Giải thích:**

1. `unauthenticated(key)` chỉ là attempt, chưa có authorities.
2. `verified(...)` chỉ dùng **sau khi manager kiểm key**, trả principal do backend xác định và không giữ key raw trong authenticated object.
3. Override setter ngăn một caller bình thường gọi `setAuthenticated(true)` trên attempt.
4. `toString()` không in key; `eraseCredentials()` xóa key khỏi reference của object.
5. Factory public trong demo giúp dễ học, nhưng production nên **giới hạn việc tạo trusted token** trong security module (package-private hoặc builder nội bộ) và không cho business code lấy principal/authorities từ client rồi tự gọi `verified`.

### 5.5 ApiKeyAuthenticationManager.java

Manager này tự xử lý `ApiKeyAuthenticationToken`, không xử lý `UsernamePasswordAuthenticationToken` của Basic hoặc `BearerTokenAuthenticationToken` của OAuth2.

`src/main/java/com/example/multiauth/ApiKeyAuthenticationManager.java`:

```java
package com.example.multiauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import reactor.core.publisher.Mono;

public final class ApiKeyAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final byte[] expectedDigest;

    public ApiKeyAuthenticationManager(String serverSecret) {
        if (serverSecret == null || serverSecret.length() < 32) {
            throw new IllegalArgumentException(
                "Demo API key must be a high-entropy secret");
        }
        this.expectedDigest = sha256(serverSecret);
    }

    @Override
    public Mono<Authentication> authenticate(Authentication input) {
        if (!(input instanceof ApiKeyAuthenticationToken token)) {
            // Unsupported Authentication type, not invalid API key.
            return Mono.empty();
        }

        return Mono.defer(() -> {
            Object supplied = token.getCredentials();
            if (!(supplied instanceof String raw)
                    || raw.isBlank()
                    || raw.length() > 256) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            boolean matches = MessageDigest.isEqual(
                expectedDigest, sha256(raw));

            if (!matches) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            return Mono.just((Authentication)
                ApiKeyAuthenticationToken.verified(
                    "partner-integration",
                    List.of(new SimpleGrantedAuthority(
                        "ROLE_PARTNER_READ"))
                )
            );
        });
    }

    private static byte[] sha256(String input) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(input.getBytes(StandardCharsets.UTF_8));
        }
        catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
```

**Phân tích bảo mật:**

- Nếu manager không hỗ trợ Authentication type, `Mono.empty()` là hợp lý.
- Nếu attempt là ApiKey mà raw key sai/thiếu, manager **phát BadCredentialsException** → HTTP 401.
- `MessageDigest.isEqual` so digests theo cách giảm rò rỉ thông tin thời gian so sánh, không thay thế bảo mật secrets, rate limit hoặc key entropy.
- `ROLE_PARTNER_READ` chỉ do backend gán; client không thể tự gửi `X-Role: ADMIN` để biến thành admin.
- API key phải **ngẫu nhiên có entropy cao**, không lấy password ngắn rồi nghĩ SHA-256 giải quyết được offline guessing.
- Production thường lưu **hash/HMAC của key**, key ID, key status, expiry, rotation/overlap, customer/tenant mapping và quota trong storage quản lý an toàn. Mẫu chỉ dùng một key từ environment để đơn giản hóa học tập.
- Nếu kiểm key từ database hoặc KMS, dùng reactive client (Redis/R2DBC hoặc async APIs), không `block()` trên Netty event-loop.
- **Không đăng ký manager này làm `@Bean ReactiveAuthenticationManager` toàn cục** trong demo: Basic phải dùng provider/manager kiểm password riêng; tạo instance custom manager bên trong custom filter.

## 6. MultiAuthSecurityConfig.java: phối hợp ba cơ chế

`src/main/java/com/example/multiauth/MultiAuthSecurityConfig.java`:

```java
package com.example.multiauth;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.server.WebFilter;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class MultiAuthSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("BASIC_READ")
            .build();

        var admin = User.withUsername("administrator")
            .password(encoder.encode("admin-demo-password"))
            .roles("BASIC_READ", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            @Value("${app.security.api-key}") String apiKeySecret) {

        // Do NOT register the custom manager as the global Basic manager.
        var apiKeyManager = new ApiKeyAuthenticationManager(apiKeySecret);
        var apiKeyFilter = buildApiKeyFilter(apiKeyManager);

        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .addFilterAt(
                rejectAmbiguousAuthorizationHeaders(),
                SecurityWebFiltersOrder.FIRST
            )
            .addFilterAt(
                apiKeyFilter,
                SecurityWebFiltersOrder.AUTHENTICATION
            )
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/read")
                    .hasAnyAuthority(
                        "ROLE_BASIC_READ",
                        "ROLE_PARTNER_READ",
                        "SCOPE_messages.read"
                    )
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAnyAuthority("ROLE_ADMIN", "SCOPE_api.admin")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    private AuthenticationWebFilter buildApiKeyFilter(
            ApiKeyAuthenticationManager manager) {

        var filter = new AuthenticationWebFilter(manager);

        filter.setServerAuthenticationConverter(exchange -> {
            String header = exchange.getRequest().getHeaders()
                .getFirst(HttpHeaders.AUTHORIZATION);

            // Only the ApiKey scheme belongs to this converter.
            if (header == null ||
                    !header.regionMatches(true, 0, "ApiKey", 0, 6)) {
                return Mono.empty();
            }

            // Scheme recognized but value malformed: fail closed.
            if (!header.regionMatches(true, 0, "ApiKey ", 0, 7)
                    || header.length() <= 7
                    || header.length() > 263) {
                return Mono.error(new BadCredentialsException(
                    "Malformed API key"));
            }

            String key = header.substring(7);
            if (key.isBlank() || key.contains(" ")
                    || key.contains("\t")
                    || !key.equals(key.strip())) {
                return Mono.error(new BadCredentialsException(
                    "Malformed API key"));
            }

            return Mono.just(
                ApiKeyAuthenticationToken.unauthenticated(key)
            );
        });

        filter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
            )
        );
        filter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        return filter;
    }

    private WebFilter rejectAmbiguousAuthorizationHeaders() {
        return (exchange, chain) -> {
            List<String> headers = exchange.getRequest().getHeaders()
                .getOrEmpty(HttpHeaders.AUTHORIZATION);

            // Demo policy: exactly one Authorization value at most.
            if (headers.size() > 1 ||
                    (headers.size() == 1
                        && headers.get(0) != null
                        && headers.get(0).contains(","))) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.BAD_REQUEST);
                return exchange.getResponse().setComplete();
            }
            return chain.filter(exchange);
        };
    }
}
```

### 6.1 Cách phối hợp thực tế

- Request `Basic ...` → converter ApiKey trả `Mono.empty()`; Basic auth filter kiểm username/password bằng `MapReactiveUserDetailsService` và password encoder.
- Request `Bearer ...` → converter ApiKey trả `Mono.empty()`; JWT Resource Server filter dùng `ReactiveJwtDecoder` từ Boot config.
- Request `ApiKey ...` → Basic/Bearer không xử lý scheme này; custom converter tạo unauthenticated ApiKey token và custom manager kiểm key.
- Request `ApiKey` thiếu value → custom converter phát exception, không fallback.
- Request có hai Authorization header fields → guard từ chối trước authentication.
- Nếu không có credential ở protected endpoint, authorization flow trả 401 theo entry point đang áp dụng.
- Rule `hasAnyAuthority` kiểm những authorities mà **mỗi cơ chế cấp riêng**. Không có chỗ nào cho caller tự chọn role/scope.

### 6.2 Tại sao dùng SecurityWebFiltersOrder.AUTHENTICATION?

`AuthenticationWebFilter` cần hoạt động sau khi đã có request/security context setup nhưng **trước authorization**. `addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)` là vị trí đúng cho custom authentication trong WebFlux chain.

Các filters có cùng authentication order không nên được dùng như một quy tắc thứ tự security mạnh/yếu. Ví dụ này phân tuyến bằng **header scheme disjoint**: custom filter chỉ xử lý `ApiKey`; built-ins xử lý `Basic` và `Bearer`. Vì vậy kết quả không phụ thuộc “cơ chế nào thử trước”.

`SecurityWebFiltersOrder.FIRST` ở guard giúp xử lý các Authorization headers mâu thuẫn sớm. Ở production, ingress/proxy cũng cần kiểm multiple Authorization header values và hành vi coalescing trên HTTP/1.1/HTTP/2.

### 6.3 Stateless authentication

`NoOpServerSecurityContextRepository` tránh lưu SecurityContext giữa requests. Một `Authentication` đã xác thực được đưa vào **Reactor Context của request hiện tại**, không mặc định được dùng lại như session login. Đây là lựa chọn phù hợp với API sử dụng credentials trên từng request.

HTTP Basic có thể được browser gửi lặp lại do browser quản lý credential cache; nếu dùng mutation endpoints, **CSRF policy vẫn cần threat model**. Một API không dùng session không tự động có nghĩa không có bất kỳ CSRF risk nào.

### 6.4 Nhầm lẫn giữa manager bean và manager cục bộ

Nếu viết:

```java
@Bean
ReactiveAuthenticationManager customManager(...) {
    return new ApiKeyAuthenticationManager(...);
}
```

rồi Spring Security tự chọn nó làm **default authentication manager**, HTTP Basic có thể không còn xử lý UsernamePasswordAuthenticationToken như dự định. Trong mẫu chính, ta **không** đăng ký custom manager toàn cục; instance được truyền trực tiếp vào `new AuthenticationWebFilter(manager)`.

Nếu production cần nhiều manager beans, cấu hình rõ `@Qualifier` và **từng filter sử dụng đúng manager**, đừng dựa vào auto-wiring mơ hồ.

## 7. ReadController.java

`src/main/java/com/example/multiauth/ReadController.java`:

```java
package com.example.multiauth;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReadController {

    public record Result(String principal, String operation) {}

    @GetMapping(
        value = "/public/health",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping(
        value = "/api/read",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Result> read(Principal principal) {
        return Mono.just(new Result(principal.getName(), "read"));
    }

    @GetMapping(
        value = "/api/admin",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Result> admin(Principal principal) {
        return Mono.just(new Result(principal.getName(), "admin"));
    }
}
```

`Principal` được cung cấp từ SecurityContext của Spring Security, **không lấy từ HTTP header X-User**. Với Basic, name là username đã xác thực; với JWT, thường là JWT `sub`; với ApiKey demo, name do custom manager gán `partner-integration`. Đừng nhầm principal name với dữ liệu đã chứng minh quyền sở hữu mọi resource/tenant.

## 8. Kiểm thử WebTestClient: 15 trường hợp

Tạo test source `src/test/java/com/example/multiauth/MultiAuthHttpTest.java`.

Bộ test dùng `WebTestClient.bindToApplicationContext(...)` + `springSecurity()`. Để không cần IdP/JWKS thật, một `@TestConfiguration` tạo fake `ReactiveJwtDecoder` **chỉ ở test context**. Fake decoder cho phép kiểm logic Bearer filter/authorities, nhưng **không verify JWT cryptography**; phần cuối nói về test JWT thật.

### 8.1 MultiAuthHttpTest.java

```java
package com.example.multiauth;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import java.time.Instant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = {
        "app.security.api-key=local-test-api-key-0123456789-ABCDEFabcdef",
        "spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.test/issuer",
        "spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://idp.example.test/issuer/jwks"
    }
)
@Import(MultiAuthHttpTest.TestJwtDecoder.class)
class MultiAuthHttpTest {

    private static final String API_KEY =
        "local-test-api-key-0123456789-ABCDEFabcdef";

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestJwtDecoder {

        @Bean
        @Primary
        ReactiveJwtDecoder fakeDecoder() {
            return raw -> {
                String scope;
                switch (raw) {
                    case "jwt-reader" -> scope = "messages.read";
                    case "jwt-admin" -> scope = "api.admin";
                    case "jwt-other" -> scope = "profile.read";
                    default -> {
                        return Mono.error(
                            new BadJwtException("Invalid test JWT"));
                    }
                }

                Instant now = Instant.now();
                Jwt jwt = Jwt.withTokenValue(raw)
                    .header("alg", "RS256")
                    .claim("sub", "jwt-alice")
                    .claim("scope", scope)
                    .issuedAt(now.minusSeconds(30))
                    .expiresAt(now.plusSeconds(1800))
                    .build();

                return Mono.just(jwt);
            };
        }
    }

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHealthNeedsNoCredentials() {
        client.get().uri("/public/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void noCredentialsCannotRead() {
        client.get().uri("/api/read")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicReaderCanRead() {
        client.get().uri("/api/read")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principal").isEqualTo("reader");
    }

    @Test
    void wrongBasicPasswordReturns401() {
        client.get().uri("/api/read")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void administratorCanAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "administrator", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.operation").isEqualTo("admin");
    }

    @Test
    void correctApiKeyCanRead() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "ApiKey " + API_KEY)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principal").isEqualTo("partner-integration");
    }

    @Test
    void wrongApiKeyFailsWithoutFallback() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION,
                "ApiKey wrong-example-secret")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedApiKeyFails() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "ApiKey")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void apiKeyCannotAdmin() {
        client.get().uri("/api/admin")
            .header(HttpHeaders.AUTHORIZATION, "ApiKey " + API_KEY)
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void bearerWithReadScopeCanRead() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "Bearer jwt-reader")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principal").isEqualTo("jwt-alice");
    }

    @Test
    void bearerMissingScopeGets403() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "Bearer jwt-other")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void invalidBearerGets401() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-test-jwt")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void bearerWithAdminScopeCanAdmin() {
        client.get().uri("/api/admin")
            .header(HttpHeaders.AUTHORIZATION, "Bearer jwt-admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.operation").isEqualTo("admin");
    }

    @Test
    void duplicateAuthorizationHeadersAreRejected() {
        client.get().uri("/api/read")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer jwt-reader",
                "ApiKey " + API_KEY)
            .exchange()
            .expectStatus().isBadRequest();
    }
}
```

Chạy:

```bash
./gradlew test --tests '*MultiAuthHttpTest'
```

Windows:

```powershell
.\gradlew.bat test --tests '*MultiAuthHttpTest'
```

Đây là **15 test cases và các HTTP assertions dự kiến**, không phải Gradle stdout đã chạy trong môi trường biên soạn. Mã ví dụ đã được rà soát theo API Spring Security 6.5, nhưng bạn vẫn cần chạy test với phiên bản Boot/dependencies thực tế để xác minh.

### 8.2 Vì sao có 401 và 403 khác nhau?

- Basic/password sai → **authentication failure**, 401.
- JWT malformed/không hợp lệ → **authentication failure**, 401.
- API key sai → **authentication failure**, 401.
- Token/key/password đúng nhưng route cần authority chưa được cấp → **authorization denial**, thường 403.
- Multiple Authorization header values → request mâu thuẫn, guard demo trả **400** trước authentication.
- CORS preflight có thể cần xử lý riêng; nó không tự biến credential sai thành đúng.

Trong Spring Security, status thực tế còn phụ thuộc entrypoint/chain/exception handling, nhất là khi request anonymous. Tests minh họa chủ đích nhưng không yêu cầu mọi ứng dụng có cùng WWW-Authenticate challenge.

### 8.3 Vì sao fake ReactiveJwtDecoder chỉ có ở test?

Fake decoder có thể chấp nhận chuỗi `jwt-reader` dù đây không phải JWT được ký. Nó giúp test filter routing và scope authorities offline, **nhưng không chứng minh an toàn JWT production**.

Staging integration test cần **decoder thật** và signed JWTs với:
- JWS signature đúng/sai;
- trusted issuer `iss`;
- JWT `exp` và `nbf`;
- resource audience `aud` đúng/sai;
- trusted `alg`/key ID;
- key rotation/JWKS caching;
- không nhầm token issuer A sang issuer B;
- scopes/roles được map đúng.

Không copy `fakeDecoder()` từ test sang main code hoặc bật một `ReactiveJwtDecoder` chỉ trả `Mono.just(...)` trong production.

## 9. Chạy thủ công qua curl

Chạy app ở localhost với key demo:

```bash
export DEMO_API_KEY="local-test-api-key-0123456789-ABCDEFabcdef"
./gradlew bootRun
```

PowerShell:

```powershell
$env:DEMO_API_KEY = "local-test-api-key-0123456789-ABCDEFabcdef"
.\gradlew.bat bootRun
```

### 9.1 HTTP Basic

```bash
curl -i -u reader http://localhost:8080/api/read
```

Curl hỏi password, nhập `reader-demo-password`. Kỳ vọng 200 với `"principal":"reader"`. Gọi `/api/admin` với reader sẽ bị 403; dùng tài khoản administrator và password demo `admin-demo-password` sẽ được 200.

**Không gửi Basic password qua HTTP trên mạng thật.** Lệnh localhost chỉ để học; trong production HTTPS/TLS đúng trust boundary là bắt buộc.

### 9.2 Custom ApiKey

```bash
curl -i http://localhost:8080/api/read \
  -H "Authorization: ApiKey local-test-api-key-0123456789-ABCDEFabcdef"
```

Kỳ vọng 200 với `partner-integration`. Thay một ký tự sẽ bị 401; gọi `/api/admin` bằng key đúng bị 403 vì không có ROLE_ADMIN.

Đừng đưa API key production vào một câu lệnh có thể bị shell history/process inspection, ticket hay log. Dùng secret injection phù hợp hệ thống.

### 9.3 Bearer JWT

```bash
curl -i http://localhost:8080/api/read \
  -H "Authorization: Bearer <SIGNED_ACCESS_TOKEN_FROM_IDP>"
```

Chỉ thành công với IdP/JWKS thật được cấu hình và token có issuer, audience, signature, scope đúng. Chuỗi `jwt-reader` trong test không phải token thật; server production sẽ không chấp nhận nó.

## 10. Nếu chỉ cần custom + HTTP Basic

Nếu hệ thống chưa cần Bearer:
- Bỏ OAuth2 Resource Server starter nếu không còn dùng ở nơi khác.
- Bỏ `spring.security.oauth2.resourceserver.jwt.*`.
- Bỏ `.oauth2ResourceServer(...jwt(...))`.
- Giữ `httpBasic(Customizer.withDefaults())`, custom AuthenticationWebFilter và API-key manager.
- Dùng authority rule chỉ gồm `ROLE_BASIC_READ` hoặc `ROLE_PARTNER_READ`.

Khi Bearer token gửi tới hệ thống chỉ hỗ trợ Basic+ApiKey, không filter nào xác minh nó và protected API sẽ từ chối. **Không thử coi Bearer token là API key**.

### 10.1 Nếu công ty dùng X-API-Key header

Có thể thay converter custom bằng header `X-API-Key`. Khi đó, một request có thể đồng thời gửi `Authorization: Bearer ...` và `X-API-Key: ...`; điều này dễ tạo ambiguous authentication. Nên từ chối ngay nếu cả hai xuất hiện, thay vì chọn “credential hợp lệ nào cũng được”.

Pseudocode:

```text
if X-API-Key absent:
    custom converter -> Mono.empty()
else if Authorization present:
    reject mixed credentials early -> 400/401
else if X-API-Key malformed:
    custom converter -> AuthenticationException
else:
    custom converter -> unauthenticated ApiKeyAuthenticationToken
    manager -> verify -> authenticated principal/authorities
```

Với custom header, guard cần đặt **trước tất cả authentication filters**, không dựa vào thứ tự giữa Bearer filter và custom filter cùng order. API-key rate limit, storage và rotation vẫn cần như custom Authorization scheme.

## 11. Nếu cần custom + Bearer opaque thay vì JWT

Nếu Authorization Server cấp **opaque access tokens**, thay JWT Resource Server bằng introspection:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

và properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Đây là **biến thể thay thế JWT**, không phải hướng dẫn bật cả JWT và opaque trên cùng Bearer resolver. `ReactiveOpaqueTokenIntrospector` dùng RFC 7662 introspection endpoint để xác minh trạng thái token, sau đó scopes có thể map thành `SCOPE_...`. Mọi `active:false` phải fail authentication; không fallback sang ApiKey hoặc Basic.

**Bảo mật secret:** `client-id`/`client-secret` ở đây là credential để Resource Server hỏi IdP, **không phải** Bearer token của caller. Dùng HTTPS và secret manager, timeout/retry có giới hạn, không fail open khi IdP timeout.

## 12. Tách nhiều SecurityWebFilterChain theo path

Nếu Basic dành cho nội bộ còn Bearer dành cho public API, tốt hơn tách chains:

```java
@Bean
@Order(1)
SecurityWebFilterChain publicApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex
            .anyExchange().hasAuthority("SCOPE_messages.read"))
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Đây là **bean snippet**, cần imports `Bean`, `Order`, `SecurityWebFilterChain`, `PathPatternParserServerWebExchangeMatcher` và `Customizer`. Tạo chain khác cho `/internal/**` dùng Basic, chain khác cho `/partner/**` dùng custom API key, sau cùng catch-all `denyAll`.

**Cần nhớ:** `securityMatcher` chọn chain, còn `authorizeExchange` kiểm quyền trong chain. Spring Security chỉ chạy **chain đầu tiên match**; một Bearer sai trong chain `/api/**` **không** khiến request chạy tiếp tới chain Basic. Điều này là cơ sở ngăn auth downgrade.

### 12.1 So sánh kiến trúc

| Nhu cầu | Gợi ý | Lưu ý |
| --- | --- | --- |
| Một endpoint đang migration Basic → Bearer | Một chain với disjoint converters | Thử mọi positive/negative/scheme conflicts |
| Bearer API public, Basic admin internal | Nhiều chains theo URL | Matchers/order/catch-all rõ ràng |
| Partner API key chỉ read-only | Chain riêng hoặc common chain với authority riêng | Quota/key rotation + 403 cho admin |
| Nhiều issuers/tenants | Trusted routing, resolvers hoặc chains | Không chọn issuer từ untrusted token payload |
| Browser session/OIDC | Chain với session/CSRF đúng | Không gộp vô tội vạ với stateless bearer |
| Chưa chắc token là JWT hay opaque | Chọn một validation strategy phù hợp | Không bỏ JWT validation khi token sai |

## 13. Những lỗi và rủi ro thường gặp

### 13.1 Chuyển bad credentials thành Mono.empty

Sai:

```java
if (badKey) {
    return Mono.empty();
}
```

Đúng:

```java
if (badKey) {
    return Mono.error(new BadCredentialsException("Invalid API key"));
}
```

Một credential đã được nhận diện nhưng sai phải tạo authentication failure, không phải “chưa thấy credential”.

### 13.2 Dùng một manager cho mọi credential

Đừng ghép Basic username/password, JWT access token và API key thành một chuỗi rồi if/else tùy ý. Giữ:
- HTTP Basic dùng user details/password encoder.
- Bearer dùng Resource Server JWT decoder/opaque introspection.
- ApiKey dùng custom manager kiểm secret.
- Authority và domain authorization riêng.

### 13.3 Trust role từ request

Không tạo principal ADMIN vì client gửi `X-Role: ADMIN` hoặc `?role=admin`. Custom manager phải gán quyền từ server-side record đã xác minh. JWT authorities phải đến từ **verified claims**, không phải Base64 payload đọc không kiểm chữ ký.

### 13.4 Key lưu plaintext, không rotation

Demo dùng một key từ environment và hash trong RAM. Production cần key registry, key ID, hashed storage, expiry/revocation, high entropy, rate/usage limit và phương án rotation không làm gián đoạn toàn bộ clients. `MessageDigest.isEqual` giúp so sánh digest, nhưng **không** cứu một key yếu hoặc brute-force attack.

### 13.5 Authorization header ambiguity

Hai Authorization values có thể bị gateway ghép hoặc xử lý khác nhau qua HTTP/1.1 và HTTP/2. Nên kiểm ở ingress và ở app, test raw requests qua proxy thực. Demo guard trả 400 cho multiple values hoặc dấu phẩy trong một value, áp dụng cho ba schemes đã chọn chứ không phải tuyên bố mọi auth scheme HTTP trên đời đều cấm dấu phẩy.

### 13.6 HTTP Basic/TLS

`Basic <base64>` không mã hóa username/password; chỉ dùng qua HTTPS đúng validation, tránh log raw Authorization và có rate limits/chính sách password. Browser có thể tự gửi lại Basic credentials, cần đánh giá CSRF khi có mutation endpoints.

### 13.7 JWT validation không đầy đủ

Không dùng fake `ReactiveJwtDecoder` của test trong production. Cần trusted issuer, JWKS/signature, allowed algorithms, expiry, audience, scope, key rotation và HTTPS. Nếu Resource Server nhận JWT cho API khác audience, không được “vì chữ ký hợp lệ” mà cho phép truy cập API này.

### 13.8 Authentication success không phải quyền mọi nơi

Một key có `ROLE_PARTNER_READ` chỉ nên đọc route đã cho phép. Với dữ liệu nhiều tenants cần kiểm tài nguyên/owner/tenant cụ thể, không chỉ `hasAuthority` chung.

### 13.9 CSRF, CORS và HTTPS là các lớp khác

- **CORS:** browser có được gửi/read cross-origin hay không; preflight không mang credential thông thường nên cần xử lý sớm.
- **CSRF:** browser request side effects có thể lợi dụng ambient credentials, cần policy theo loại client/route.
- **TLS:** bảo vệ credentials trên đường truyền.
- **Authentication:** xác minh Basic/Bearer/ApiKey.
- **Authorization:** xác minh quyền scope/role và data ownership.

Không sửa lỗi OPTIONS 401 bằng cách `anyExchange().permitAll()`; không disable CSRF toàn app chỉ vì test POST 403.

## 14. Bảng troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Basic đúng nhận 401 sau khi thêm custom manager | Custom manager bị Spring dùng làm default | Không global-register, gắn trực tiếp vào custom filter |
| ApiKey sai vẫn trả 200 | Converter trả empty hoặc endpoint permitAll | Phát BadCredentialsException; test negative |
| ApiKey thiếu value không báo lỗi | Scheme malformed được bỏ qua | Phân biệt recognized scheme vs unsupported |
| Bearer JWT đúng bị 401 | Issuer/audience/expiry/signature/JWKS sai | Test real decoder và IdP |
| Bearer thiếu scope vẫn 200 | Rule chỉ dùng authenticated | Dùng `hasAuthority("SCOPE_...")` |
| ApiKey có thể gọi admin | Manager cấp authority quá mạnh | Scope/key registry với least privilege |
| 2 Authorization headers có kết quả không ổn định | Gateway/header parsing khác nhau | Reject duplicate ở edge/app |
| Filter custom không chạy | Không addFilterAt trong đúng chain | Kiểm SecurityWebFiltersOrder và matcher |
| Auth fail rồi fallback Basic | onErrorResume nuốt BadCredentials | Không fallback trên error |
| Browser CORS lỗi dù curl 200 | CORS khác authentication | Kiểm OPTIONS/Access-Control-* |
| POST gặp 403 trong browser | CSRF hoặc role denial | Phân loại security failure đúng |
| JWT test mock pass, staging 401 | Fake decoder bypass cryptography | Integration test IdP/JWKS thật |
| API key leak trong logs | Ghi raw Authorization | Redact, chỉ log key ID sau auth |
| Key bị lộ vẫn dùng được lâu | Không có revoke/rotation | Versioned keys/TTL/incident runbook |
| Latency cao khi lookup key | Blocking DB trong Netty thread | Reactive DB client, timeout/bulkhead |
| Một chain không match nhưng route lại public | Catch-all chain permitAll | Catch-all denyAll |
| HTTP Basic hoạt động qua HTTP | Credential có thể bị nghe lén | HTTPS ở ingress và nội bộ |
| Resource Server trả 503 khi IdP down | Introspection/JWKS dependency lỗi | Fail closed, SLO/timeouts; không tạo anonymous auth thành trusted |

## 15. Câu hỏi ôn tập

**1. `Mono.empty()` của custom converter có nghĩa key sai?** Không. Nó nghĩa converter **không nhận diện credential của mình** (ví dụ Basic/Bearer). Key sai phải phát AuthenticationException.

**2. Basic manager có nên xử lý ApiKeyAuthenticationToken?** Không trong demo. Basic xác thực password từ user details; API key có manager riêng.

**3. Khi nào trả 401?** Khi chưa xác thực được: thiếu/sai Basic, Bearer invalid, ApiKey sai/malformed. Entry point có thể khác nhau nhưng phải fail closed.

**4. Khi nào trả 403?** Principal đã xác thực nhưng thiếu required authority/role/scope hoặc domain policy từ chối.

**5. Bearer token trông như JWT có đủ tin cậy?** Không. Phải verify chữ ký, issuer, audience, expiry và claims theo Resource Server.

**6. Vì sao không đặt API key trong Bearer rồi nếu JWT sai mới so key?** Nó làm lẫn OAuth2 Bearer semantics với custom key, tạo nguy cơ downgrade và bypass signature validation.

**7. Vì sao custom manager không nên là default ReactiveAuthenticationManager bean?** Có thể làm Basic filter dùng nhầm manager không hỗ trợ username/password.

**8. Tại sao dùng ApiKeyAuthenticationToken chưa authenticated?** Vì credential lấy từ HTTP client chưa đáng tin. Chỉ sau manager verify mới tạo trusted token và authorities.

**9. API key đúng có tự được ROLE_ADMIN?** Không. Demo chỉ cấp ROLE_PARTNER_READ, admin endpoint vẫn 403.

**10. Vì sao phải kiểm duplicate Authorization headers?** Tránh parser/gateway chọn credential khác nhau gây confused deputy hoặc auth bypass.

**11. Một chain và nhiều chains khác nhau thế nào?** Một chain có thể hỗ trợ nhiều schemes trên cùng path; nhiều chains được chọn theo securityMatcher và @Order, giúp tách trust boundary.

**12. `X-API-Key` có thể song song với `Authorization: Basic`?** Về HTTP có thể, nhưng policy bảo mật nên chặn mixed credentials nếu không có thiết kế rõ; guard phải chạy trước cả hai.

**13. HTTP Basic Base64 có mã hóa không?** Không. Cần TLS và bảo vệ password.

**14. `SecurityWebFiltersOrder.AUTHENTICATION` quan trọng gì?** Đặt custom filter ở phase xác thực, trước authorization. Không dùng nó để ngầm bảo đảm thứ tự những filters cùng order.

**15. `mockJwt()` hoặc fake JWT decoder có đủ test crypto thật?** Không. Chúng kiểm policy/routing; cần decoder thật và signed tokens trong integration tests.

## 16. Checklist production

- [ ] Định nghĩa rõ các schemes theo path/client, không chấp nhận mọi scheme tùy tiện.
- [ ] Custom converter trả `Mono.empty` khi scheme không khớp; trả error khi scheme đã nhận diện nhưng credential sai.
- [ ] Custom manager chỉ nhận custom Authentication type, không làm hỏng Basic/JWT managers.
- [ ] Authentication chưa xác thực không chứa authorities; authenticated token được tạo từ verification server-side.
- [ ] Custom AuthenticationWebFilter nằm trong SecurityWebFilterChain ở authentication phase.
- [ ] Không dựa vào thứ tự filters để làm fallback hoặc chọn auth mạnh/yếu.
- [ ] Chặn mixed/duplicate Authorization credentials và test qua gateway thực tế.
- [ ] Basic dùng password encoder/user service; không lưu mật khẩu thật trong source.
- [ ] Bearer dùng JWT signature + issuer/audience/expiry hoặc opaque introspection; không tự parse payload chưa verify.
- [ ] API key có entropy cao, hash/secret storage, versioning, revoke/rotation và per-client quota.
- [ ] Mỗi cơ chế cấp authorities tối thiểu; endpoint có role/scope/domain rules rõ.
- [ ] Có positive/negative tests cho Basic, Bearer và ApiKey, cả 401/403 và duplicate headers.
- [ ] Có integration JWT verification tests ngoài fake decoder; IdP/JWKS/clock/key rotation được kiểm.
- [ ] HTTPS/TLS được enforce, không log credentials và có rate limits.
- [ ] CORS preflight không bị auth chặn; CSRF policy cho browser mutations được đánh giá.
- [ ] Nếu multi-chain, @Order/securityMatcher chuẩn và catch-all denyAll.
- [ ] Không gọi `block()` trong reactive authentication path khi lookup secret từ DB/KMS.
- [ ] Có metrics sanitized cho auth scheme, success/failure, latency, suspicious attempts và incident response.

## 17. Tổng kết

**Phối hợp xác thực tùy chỉnh với HTTP Basic hoặc Bearer token** trong WebFlux không có nghĩa tự viết một authentication manager nhận mọi chuỗi secret và thử provider đến khi pass. Hãy để Spring Security xử lý các cơ chế chuẩn:
- `httpBasic()` xác minh Basic username/password bằng password encoder/user details;
- `oauth2ResourceServer().jwt()` hoặc `opaqueToken()` xác minh Bearer access token theo trust policy;
- `AuthenticationWebFilter + ServerAuthenticationConverter + ReactiveAuthenticationManager` cho custom scheme được nhận diện tường minh.

**Ba điểm quan trọng nhất:** (1) scheme không khớp → `Mono.empty`; scheme khớp nhưng credential sai → `AuthenticationException`, (2) authentication thành công chưa đủ, cần authorization theo role/scope/tenant/resource, và (3) đừng trộn credentials hoặc fallback từ cơ chế mạnh sang yếu. Khi các nhóm client có trust boundary khác nhau, tách nhiều `SecurityWebFilterChain` theo URL là lựa chọn dễ audit hơn.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — Reactive HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/passwords/basic.html)
- [Spring Security 6.5 — JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Opaque Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security 6.5 — SecurityWebFiltersOrder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html)
- [Spring Security 6.5 — ServerAuthenticationConverter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html)
- [Spring Security 6.5 — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security 6.5 — Reactive OAuth2 Tests](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
