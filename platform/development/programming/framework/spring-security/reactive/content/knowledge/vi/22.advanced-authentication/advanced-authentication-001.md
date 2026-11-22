# Thiết kế cơ chế xác thực riêng bằng AuthenticationWebFilter trong Spring Security WebFlux

## Mục tiêu

Bài học thuộc **Xác thực mở rộng** của module **Spring Security - reactive**. Trong ứng dụng WebFlux, khi cần hỗ trợ một loại credential không có sẵn trong HTTP Basic, OAuth2, OIDC hay JWT Resource Server, ta có thể tích hợp vào **Spring Security reactive chain** bằng `AuthenticationWebFilter` thay vì viết một bộ lọc toàn cục tự đặt biến “đã đăng nhập”.

Sau bài học, bạn có thể:

1. Giải thích nhiệm vụ của `AuthenticationWebFilter`, `ServerAuthenticationConverter`, `ReactiveAuthenticationManager`, `Authentication`, `ServerSecurityContextRepository`, success/failure handler và `AuthorizationWebFilter`.
2. Phân biệt `Mono.empty()`, `Mono.just(unauthenticatedToken)`, `Mono.error(AuthenticationException)` ở converter và manager.
3. Tạo `Authentication` chưa được xác minh từ header request; chỉ manager đáng tin mới tạo token authenticated với principal và GrantedAuthority.
4. Dùng `setRequiresAuthenticationMatcher`, `setServerAuthenticationConverter`, `setAuthenticationSuccessHandler`, `setAuthenticationFailureHandler`, `setSecurityContextRepository` và `addFilterAt` đúng ngữ nghĩa WebFlux.
5. Hiểu khi nào dùng `NoOpServerSecurityContextRepository` (stateless mỗi request) hoặc `WebSessionServerSecurityContextRepository` (login phiên).
6. Viết ứng dụng **Java 17+, Spring Boot 3.3.13, WebFlux, Spring Security 6.3.x** minh họa `Authorization: DemoKey ...`.
7. Xác minh quyền `SCOPE_orders:read`, danh tính client, tenant và ownership của order; không nhầm AuthN với AuthZ.
8. Dùng `ReactiveSecurityContextHolder` trong service thay vì Servlet `SecurityContextHolder`.
9. Kiểm thử bằng `WebTestClient` và `StepVerifier`: public, missing key, malformed key, wrong key, authenticated, insufficient authority, tenant/owner, stateless.
10. Triển khai production an toàn với HTTPS, secret entropy, hashed key store, rotation, expiry, revocation, rate limiting, CORS/CSRF, multi-chain và logs đã redact.

**Phạm vi bảo mật:** `DemoKey` ở đây là giao thức **giả lập phục vụ bài lab**, không phải lời khuyên tự phát minh một auth scheme production. Nếu use case được đáp ứng bởi OAuth2 client credentials, mTLS, JWT/opaque token Resource Server hay gateway identity đã được kiểm chứng, hãy ưu tiên chúng. `AuthenticationWebFilter` là điểm tích hợp kỹ thuật, không làm một credential format yếu trở nên an toàn.

## 1. Xác thực và phân quyền là hai công đoạn

**Xác thực (Authentication)** trả lời: ai đang gọi? Credential do caller mang đến có khớp khóa/identity record, chưa bị thu hồi, không hết hạn, được phép dùng trong ngữ cảnh này hay không?

**Phân quyền (Authorization)** trả lời: identity đã xác thực có thể đọc hoặc thay đổi **tài nguyên cụ thể** hay không?

Một API key hợp lệ cho `partner-a` trong `tenant-a` không có nghĩa partner ấy được đọc toàn bộ orders. Hãy tách:

- Credential validation: API key đúng, active, chưa bị revoke, server tìm ra principal `partner-a`.
- Scope check: Authentication chứa `SCOPE_orders:read`.
- Tenant/owner check: bản ghi `A-100` phải thuộc `tenant-a/partner-a`.

Có thể đạt HTTP 200 khi cả ba đều đúng; trả 401 nếu thiếu/sai credential, 403 nếu authenticated nhưng thiếu authority, và có thể trả 404 nếu order không tồn tại **hoặc không thuộc quyền**, tùy response policy.

**Đặc biệt:** `authentication.isAuthenticated()` chỉ có ý nghĩa sau khi token được tạo bởi manager đã kiểm chứng; không được lấy giá trị Boolean từ request header. Một `Authentication` đã authenticated cũng **không tự động** có quyền truy cập mọi route/tenant.

## 2. Kiến trúc AuthenticationWebFilter reactive

```text
Client request
    |
    v
WebFilterChainProxy -> SecurityWebFilterChain
    |
    v
AuthenticationWebFilter
    |
    +-- requiresAuthenticationMatcher(exchange)?
    |      no => tiếp tục chain
    |      yes
    |
    +-- ServerAuthenticationConverter.convert(exchange)
    |      Mono.empty()              => không thử authentication
    |      Mono.error(AuthException) => authentication failure
    |      Mono.just(candidate)      => candidate.isAuthenticated() = false
    |
    +-- ReactiveAuthenticationManager.authenticate(candidate)
    |      Mono.empty()              => manager không xử lý candidate
    |      Mono.error(AuthException) => authentication failure
    |      Mono.just(verified)       => verified.isAuthenticated() = true
    |
    +-- SecurityContextRepository / Reactor Context
    |      NoOp: không lưu qua request khác
    |      WebSession: có thể lưu và nạp từ cookie/session
    |
    +-- success handler: tiếp tục chain hoặc chủ động chốt response
    |      v
    +-- AuthorizationWebFilter: .authenticated(), .hasAuthority(...)
    |      v
    +-- Controller -> Service -> data permission
    |
    v
HTTP response
```

Đây là **sơ đồ logic**, không phải ghi lại chính xác thứ tự từng lời gọi nội bộ. Đối với WebFlux, Spring đặt Authentication vào **Reactor Context** của subscriber hiện tại. Không tự đặt một biến `ThreadLocal` hoặc attribute tùy tiện rồi cho rằng `authorizeExchange` sẽ hiểu nó.

### 2.1. Trách nhiệm của từng thành phần

| Thành phần | Chịu trách nhiệm | Không được làm |
| --- | --- | --- |
| `ServerWebExchangeMatcher` | Chọn path/method nên thử AuthN | Kiểm secret, tự tạo role |
| `ServerAuthenticationConverter` | Parse credential/cú pháp từ request, tạo candidate | Trả trusted token trước xác minh |
| `ReactiveAuthenticationManager` | Verify credential, dựng principal+authorities từ dữ liệu server | Block JDBC/event loop hoặc fail-open |
| `ServerAuthenticationSuccessHandler` | Tiếp tục chain hoặc kết thúc login response hợp lệ | Bypass authorization không có chủ đích |
| `ServerAuthenticationFailureHandler` | Chốt kết quả AuthN lỗi | Echo raw credential/stack trace |
| `ServerAuthenticationEntryPoint` | Challenge khi tài nguyên cần auth mà request chưa authenticated | Tự coi request missing key là success |
| `ServerSecurityContextRepository` | Lưu/nạp security context giữa requests nếu cần | Vô tình tạo session cho API stateless |
| `authorizeExchange` | Kiểm authority, role, pattern, method | Thay thế tenant/record ownership check |

Dùng `AuthenticationWebFilter` từ `org.springframework.security.web.server.authentication`. Đừng nhầm với Servlet `AuthenticationFilter` hoặc `UsernamePasswordAuthenticationFilter`; WebFlux sử dụng `ServerHttpSecurity`/`SecurityWebFilterChain`, không sử dụng `HttpSecurity`/Servlet FilterChain.

### 2.2. Mono.empty và Mono.error rất khác nhau

Ở converter:

```java
return Mono.empty(); // Không có credential thuộc loại mà converter nhận
return Mono.just(candidate); // Có credential, chưa kiểm tra đúng/sai
return Mono.error(new BadCredentialsException("Malformed credential"));
```

Nếu trả `Mono.empty()`, filter không cố gắng xác thực thêm. Request sẽ đi tiếp; một route đòi `.authenticated()` vẫn phải **401** nhờ authorization/entry point. Nếu route vô tình `permitAll()`, empty sẽ cho request đi qua — vì thế **deny by default** quan trọng.

Nếu credential đã được nhận diện nhưng sai, manager phải trả:

```java
return Mono.error(new BadCredentialsException("Invalid credential"));
```

**Không** trả `Mono.empty()` để che sai key/password của scheme mình hỗ trợ. Empty ở manager thường có nghĩa **manager này không hỗ trợ loại candidate**, giúp chaining nhiều managers khi có chủ đích.

### 2.3. Kết quả trusted

Chỉ tạo authenticated token sau khi kiểm:
- Secret/key/digest;
- Trạng thái key active, chưa revoke/expire;
- Client/tenant/scope/audience đã đăng ký;
- Credential format và loại token đúng;
- Những điều kiện bổ sung như mTLS binding hoặc signed request nếu protocol yêu cầu.

Authorization manager phải dùng **GrantedAuthority** do server map, không dùng `roles=admin` lấy từ một header do caller tự khai.

## 3. Chọn kiểu authentication trước khi viết code

Có hai mô hình thường gặp.

**Per-request stateless API**: Mỗi request gửi `Authorization: DemoKey ...`. AuthenticationWebFilter kiểm key mỗi lần hoặc qua cache đúng lifecycle; kết quả không lưu vào session. Request kế tiếp không có key vẫn 401. Dùng `NoOpServerSecurityContextRepository`.

**Interactive session login**: Một request `POST /session/login` xác minh password/OTP/assertion, tạo session. Browser gửi cookie session ở các request sau. Dùng `WebSessionServerSecurityContextRepository` và bảo vệ cookie/CSRF/session fixation/logout. Success handler thường redirect hoặc trả response login, khác success handler tiếp tục chain của API key.

**Chọn một contract rõ ràng**, không vô tình biến API key thành cookie-based login. Spring Security `AuthenticationWebFilter` mặc định có `NoOpServerSecurityContextRepository`; nếu muốn persist login, phải đổi repository ở đúng filter **và** config nơi load SecurityContext.

## 4. Thiết kế demo `Authorization: DemoKey ...`

Client gửi:

```http
GET /api/whoami HTTP/1.1
Host: localhost:8080
Authorization: DemoKey local-example-token
```

Tên `DemoKey` chỉ để nhìn thấy rõ custom converter. API key thực là một **bearer secret**, phải truyền qua HTTPS, có entropy đủ lớn và lifecycle gồm tạo, cấp phát, rotate, revoke, expire, theo dõi misuse, tenant/scope policy. Không truyền qua `?api_key=...` vì query bị ghi vào logs/history/referrer.

**Phân loại Header:**
- Không có Authorization → converter empty → route protected trả 401.
- Authorization thuộc scheme `Basic`/`Bearer` → converter của DemoKey không xử lý → route protected vẫn 401 khi không có mechanism khác.
- `DemoKey correct-secret` → candidate chưa auth → manager verify → principal trusted.
- `DemoKey wrong-secret` → manager ném BadCredentials → 401.
- `DemoKey` sai format (rỗng, quá dài, chứa whitespace trái schema) → converter phát BadCredentials → 401.
- Hai Authorization headers → từ chối vì mơ hồ và tránh header smuggling.

Ở production có nhiều auth schemes, việc converter trả empty phải được thiết kế theo **matcher/chain riêng**, không để fallback weaker mechanism tạo authentication không mong muốn.

## 5. Dự án runnable Java 17+ / Spring Boot WebFlux

Cây thư mục:

```text
custom-auth-webflux/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/customauth/
    CustomAuthApplication.java
    ApiKeyPrincipal.java
    ApiKeyAuthenticationToken.java
    DemoKeyServerAuthenticationConverter.java
    DemoKeyReactiveAuthenticationManager.java
    SecurityConfig.java
    CurrentCallerService.java
    OrderService.java
    DemoController.java
  src/test/java/example/customauth/
    CustomAuthApplicationTests.java
    AuthenticationManagerTests.java
```

Ví dụ có một partner `partner-a` trong `tenant-a` với `SCOPE_orders:read`. Demo database là `Map` in-memory để tập trung vào filter; production phải thay bằng storage/policy đúng. Secret chỉ lấy từ biến môi trường `DEMO_API_KEY`, không commit.

### 5.1. settings.gradle

```groovy
rootProject.name = 'custom-auth-webflux'
```

### 5.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không dùng `spring-boot-starter-web` của Servlet và không copy servlet `AuthenticationFilter`/`HttpSecurity`. Spring Boot 3.3.13 BOM quản lý Spring Security 6.3.x, Netty và Reactor tương thích. Khi dùng dự án mới nên ưu tiên release còn được bảo trì; ví dụ này được cố định để tái lập lab.

### 5.3. application.yml

```yaml
server:
  port: 8080

demo:
  api-key: "${DEMO_API_KEY:}"
```

Nếu `DEMO_API_KEY` không có, giá trị rỗng và AuthenticationManager bean sẽ từ chối khởi động. Đây là **fail closed** thay vì chấp nhận credential rỗng. Trong unit/integration tests, property này được truyền bằng `@SpringBootTest(properties = ...)`. Không lưu secret production vào YAML.

### 5.4. CustomAuthApplication.java

```java
package example.customauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomAuthApplication.class, args);
    }
}
```

### 5.5. ApiKeyPrincipal.java

```java
package example.customauth;

public record ApiKeyPrincipal(String clientId, String tenantId) {
}
```

Principal lưu **danh tính public/tenant đã xác minh**, không lưu raw key. Record Java 17 bất biến giúp giữ dữ liệu rõ ràng. Một key của một partner có thể có nhiều authorities khác nhau tùy chính sách server.

### 5.6. ApiKeyAuthenticationToken.java

```java
package example.customauth;

import java.util.Collection;
import java.util.List;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final Object principal;
    private Object credentials;

    private ApiKeyAuthenticationToken(
            Object principal,
            Object credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(verified);
    }

    public static ApiKeyAuthenticationToken presented(String key) {
        return new ApiKeyAuthenticationToken(
                null, key, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            ApiKeyPrincipal principal,
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
        return credentials;
    }

    @Override
    public String getName() {
        if (principal instanceof ApiKeyPrincipal p) {
            return p.clientId();
        }
        return "unverified-key";
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                    "Use verified factory after authentication");
        }
        super.setAuthenticated(false);
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }
}
```

Giải thích:
1. `presented` tạo candidate với `isAuthenticated=false` và raw credential chỉ ở trường `credentials`.
2. `verified` tạo Authentication mới với principal đã xác minh, authorities từ server, `credentials=null`.
3. Không được cho caller tự đặt `isAuthenticated=true`; override `setAuthenticated` chặn thao tác này. Constructor private dùng `super.setAuthenticated(verified)` sau khi gọi factory nội bộ.
4. `getName()` của verified token là `clientId`, không phải secret.
5. `eraseCredentials()` xóa reference nội bộ, nhưng Java `String` và request headers có thể vẫn tồn tại tới GC; **bảo vệ toàn bộ logs/traces/heap dumps**, không xem việc erase như bảo đảm xóa vật lý.
6. Vì factory `verified(...)` public để manager demo gọi, codebase thật phải giới hạn trusted call sites bằng package/module/design review; không cho request handler dựng token verified tùy ý.

### 5.7. DemoKeyServerAuthenticationConverter.java

```java
package example.customauth;

import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class DemoKeyServerAuthenticationConverter
        implements ServerAuthenticationConverter {

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> values = exchange.getRequest()
                .getHeaders().get(HttpHeaders.AUTHORIZATION);

        if (values == null || values.isEmpty()) {
            return Mono.empty();
        }
        if (values.size() != 1) {
            return Mono.error(new BadCredentialsException(
                    "Ambiguous Authorization headers"));
        }

        String header = values.get(0);
        int space = header.indexOf(' ');

        if (space < 0 ||
                !header.substring(0, space)
                        .equalsIgnoreCase("DemoKey")) {
            return Mono.empty();
        }

        String key = header.substring(space + 1);
        if (key.isBlank() || key.length() > 256
                || key.indexOf(' ') >= 0
                || key.indexOf('\t') >= 0) {
            return Mono.error(new BadCredentialsException(
                    "Malformed DemoKey credential"));
        }

        return Mono.just(ApiKeyAuthenticationToken.presented(key));
    }
}
```

Converter xử lý **cú pháp HTTP**, không biết key đúng hay sai. Có header DemoKey phù hợp format thì gửi candidate cho manager. Không có header hoặc Basic/Bearer khác thì trả empty; `authorizeExchange` đảm bảo API protected không 200. Header DemoKey không kèm dấu cách cũng sẽ bị bỏ qua rồi nhận 401 từ entry point vì route protected.

**Header normalization:** Một số proxies gộp header trùng thành một chuỗi comma-separated. Converter trong lab vẫn từ chối chuỗi chứa whitespace không hợp lệ, nhưng production phải có policy rõ tại gateway cho duplicate/smuggling, không dựa vào một phép đếm duy nhất.

Không đưa raw key vào logs/error messages. Không đọc key từ query parameters hay JSON body cho API request auth dạng này.

### 5.8. DemoKeyReactiveAuthenticationManager.java

```java
package example.customauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DemoKeyReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final byte[] expectedDigest;

    public DemoKeyReactiveAuthenticationManager(
            @Value("${demo.api-key}") String expectedKey) {
        if (expectedKey == null || expectedKey.isBlank()) {
            throw new IllegalStateException(
                    "DEMO_API_KEY must be set");
        }
        expectedDigest = hash(expectedKey);
    }

    @Override
    public Mono<Authentication> authenticate(Authentication candidate) {
        if (!(candidate instanceof ApiKeyAuthenticationToken token)
                || candidate.isAuthenticated()) {
            return Mono.empty();
        }

        Object raw = token.getCredentials();
        if (!(raw instanceof String key) || key.isBlank()) {
            return Mono.error(new BadCredentialsException("Invalid API key"));
        }

        return Mono.fromSupplier(
                        () -> MessageDigest.isEqual(
                                hash(key), expectedDigest))
                .flatMap(valid -> {
                    if (!valid) {
                        return Mono.<Authentication>error(
                                new BadCredentialsException(
                                        "Invalid API key"));
                    }
                    return Mono.<Authentication>just(
                            ApiKeyAuthenticationToken.verified(
                                    new ApiKeyPrincipal(
                                            "partner-a", "tenant-a"),
                                    List.of(new SimpleGrantedAuthority(
                                            "SCOPE_orders:read"))));
                });
    }

    private static byte[] hash(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }
}
```

**Những điều cần hiểu:**

- Manager chỉ nhận loại `ApiKeyAuthenticationToken` candidate chưa verified. Loại khác trả `Mono.empty()` để manager này không xử lý. Một key sai thuộc scheme này phải phát `BadCredentialsException`, **không trả empty**.
- Server so digest bằng `MessageDigest.isEqual` để hạn chế timing leakage ở comparison. SHA-256 phù hợp khi key **ngẫu nhiên, đủ entropy**; không dùng fast hash đơn thuần cho password do user tự chọn.
- Principal/tenant/scope do server gán. Không đọc `X-Role: ADMIN`, `X-Tenant` hoặc `scope` từ header do client tạo để mở quyền.
- `Mono.fromSupplier` trì hoãn phép hash nhanh tới lúc subscribe; nó không tạo blocking database I/O trên event loop.
- Nếu kiểm key qua JDBC/LDAP/KMS blocking, dùng reactive client hoặc `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` kèm concurrency/timeouts, không gọi blocking trực tiếp trước khi trả Mono.
- Production cần key IDs, identity store nhiều keys, revoke/expire/rotation, quotas, audit, cache invalidation và secret manager; ví dụ một key trong env chỉ là lab.

### 5.9. SecurityConfig.java

```java
package example.customauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authentication.WebFilterChainServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            DemoKeyReactiveAuthenticationManager manager,
            DemoKeyServerAuthenticationConverter converter) {

        var noSession =
                NoOpServerSecurityContextRepository.getInstance();

        ServerAuthenticationEntryPoint entryPoint =
                (exchange, exception) -> {
                    var response = exchange.getResponse();
                    response.setStatusCode(HttpStatus.UNAUTHORIZED);
                    response.getHeaders().set(
                            HttpHeaders.WWW_AUTHENTICATE,
                            "DemoKey realm=\"learning-api\"");
                    return response.setComplete();
                };

        AuthenticationWebFilter filter =
                new AuthenticationWebFilter(manager);

        filter.setRequiresAuthenticationMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                        "/api/**"));
        filter.setServerAuthenticationConverter(converter);
        filter.setSecurityContextRepository(noSession);
        filter.setAuthenticationSuccessHandler(
                new WebFilterChainServerAuthenticationSuccessHandler());
        filter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(
                        entryPoint));

        return http
                .securityContextRepository(noSession)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/public/ping")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/whoami")
                        .authenticated()
                        .pathMatchers(
                                HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .logout(logout -> logout.disable())
                // Chỉ cho API stateless header-only trong lab:
                .csrf(csrf -> csrf.disable())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(entryPoint))
                .addFilterAt(
                        filter, SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
```

**Giải thích wiring:**

1. `new AuthenticationWebFilter(manager)` nhận `ReactiveAuthenticationManager`, không phải Servlet `AuthenticationManager`.
2. `setRequiresAuthenticationMatcher("/api/**")` chỉ thử parse credential trên API paths; `/public/ping` không bị custom filter đụng tới.
3. `setServerAuthenticationConverter(converter)` thay converter mặc định Basic trong AuthenticationWebFilter; nếu thiếu, filter không hiểu DemoKey.
4. `setSecurityContextRepository(NoOp...)` bảo đảm custom filter không lưu Authentication sang request sau; `http.securityContextRepository(noSession)` thống nhất cơ chế load.
5. `WebFilterChainServerAuthenticationSuccessHandler` tiếp tục chain, để `AuthorizationWebFilter` chạy sau AuthN. Nếu success handler trả 204 sớm, nó có thể ngăn controller chạy.
6. `ServerAuthenticationEntryPointFailureHandler` xử lý key sai/malformed thành 401. `exceptionHandling.authenticationEntryPoint` xử lý missing key thành 401 do authorization phát hiện unauthenticated.
7. `WWW-Authenticate: DemoKey realm="learning-api"` ở đây là challenge của scheme lab, không phải `Bearer` hoặc `Basic` đã chuẩn hóa.
8. `SecurityWebFiltersOrder.AUTHENTICATION` đặt filter bên trong Spring Security chain trước authorization. Không đăng ký thêm filter như global `WebFilter` bean để tránh double execution.
9. `authorizeExchange` bảo vệ whoami bằng authenticated, bảo vệ order bằng authority, deny những URL/method khác.
10. `httpBasic`, `formLogin` và `logout` bị tắt cho lab chỉ dùng DemoKey; không để một Basic filter khác vô tình chấp nhận user/password.
11. `csrf.disable()` **chỉ hợp lý nếu thực sự là stateless API không dùng browser auto-sent session/cookies**. Khi có browser login, hãy bật CSRF và tách security chain.
12. Thiết kế này không sử dụng cookie để xác thực. Request sau không header vẫn 401 dù request trước đã 200.

### 5.10. CurrentCallerService.java

```java
package example.customauth;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentCallerService {

    public Mono<Caller> requireCaller() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authentication required")))
                .flatMap(auth -> {
                    if (!auth.isAuthenticated()
                            || !(auth.getPrincipal()
                                    instanceof ApiKeyPrincipal principal)) {
                        return Mono.error(new AccessDeniedException(
                                "Verified API client required"));
                    }

                    return Mono.just(new Caller(
                            principal.clientId(),
                            principal.tenantId()));
                });
    }

    public record Caller(String clientId, String tenantId) {}
}
```

Service đọc `Authentication` trong **Reactor Context** của subscriber; không gọi `SecurityContextHolder.getContext()` kiểu Servlet ThreadLocal và không `block()`/`subscribe()` thủ công. Method sẽ fail-closed nếu context thiếu hoặc principal không phải ApiKeyPrincipal; đây là lớp bảo vệ thêm khi service được dùng lại trong môi trường có nhiều auth mechanisms.

Nếu tầng domain không muốn phụ thuộc Spring, có thể nhận `Caller` bất biến từ application boundary đã xác thực và không nhận Caller DTO trực tiếp do HTTP client tự khai.

### 5.11. OrderService.java

```java
package example.customauth;

import java.util.Map;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final CurrentCallerService callerService;

    private final Map<String, Order> orders = Map.of(
            "A-100", new Order(
                    "A-100", "tenant-a", "partner-a", "READY"),
            "A-101", new Order(
                    "A-101", "tenant-a", "partner-b", "PAID"),
            "B-200", new Order(
                    "B-200", "tenant-b", "partner-a", "PENDING"));

    public OrderService(CurrentCallerService callerService) {
        this.callerService = callerService;
    }

    public Mono<OrderView> readOwned(String id) {
        return callerService.requireCaller()
                .flatMap(caller -> Mono.justOrEmpty(orders.get(id))
                        .filter(order ->
                                order.tenantId().equals(caller.tenantId())
                                && order.ownerId().equals(caller.clientId()))
                        .map(order -> new OrderView(
                                order.id(), order.status())));
    }

    private record Order(
            String id, String tenantId, String ownerId,
            String status) {
    }

    public record OrderView(String id, String status) {}
}
```

Manager xác thực `partner-a/tenant-a`, nên:
- `A-100` trả 200;
- `A-101` 404 vì khác owner;
- `B-200` 404 vì khác tenant.

Trong database thực, cần dùng R2DBC prepared/bind parameters và **đưa tenant+owner vào WHERE**:

```sql
SELECT id, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :verifiedTenantId
  AND owner_id = :verifiedClientId;
```

Đừng chỉ query theo `id` rồi trả entity trước khi kiểm tenant. Một API key có `SCOPE_orders:read` chỉ cho phép kiểu thao tác, không đồng nghĩa được đọc order của bất kỳ tenant nào.

### 5.12. DemoController.java

```java
package example.customauth;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final CurrentCallerService callers;
    private final OrderService orders;

    public DemoController(
            CurrentCallerService callers, OrderService orders) {
        this.callers = callers;
        this.orders = orders;
    }

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "PONG");
    }

    @GetMapping("/api/whoami")
    public Mono<CurrentCallerService.Caller> whoami() {
        return callers.requireCaller();
    }

    @GetMapping("/api/orders/{id}")
    public Mono<OrderService.OrderView> order(@PathVariable String id) {
        return orders.readOwned(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Order not found")));
    }
}
```

Không có code đọc raw API key trong controller. Filter đã xác thực trước khi vào controller; service còn kiểm loại principal. JSON `whoami` chỉ chứa clientId/tenantId, không chứa raw key hoặc Authentication.getCredentials().

### 5.13. Chạy demo

Yêu cầu JDK 17+ và Gradle tương thích với Boot 3.3.13. Linux/macOS:

```bash
export DEMO_API_KEY='local-example-only-demo-key'
gradle bootRun
```

Windows PowerShell:

```powershell
$env:DEMO_API_KEY = "local-example-only-demo-key"
gradle bootRun
```

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` hoặc `gradlew.bat bootRun`. Lệnh chạy này chỉ dành localhost; **không gửi credential minh họa qua HTTP Internet**.

Thử public:

```bash
curl -i http://localhost:8080/public/ping
```

Dự kiến 200:

```json
{"message":"PONG"}
```

Không có key:

```bash
curl -i http://localhost:8080/api/whoami
```

Dự kiến 401 và header:

```http
WWW-Authenticate: DemoKey realm="learning-api"
```

Có key đúng:

```bash
curl -i -H 'Authorization: DemoKey local-example-only-demo-key' \
  http://localhost:8080/api/whoami
```

Dự kiến:

```json
{"clientId":"partner-a","tenantId":"tenant-a"}
```

Đọc order đúng/sai chủ sở hữu:

```bash
curl -i -H 'Authorization: DemoKey local-example-only-demo-key' \
  http://localhost:8080/api/orders/A-100

curl -i -H 'Authorization: DemoKey local-example-only-demo-key' \
  http://localhost:8080/api/orders/A-101

curl -i -H 'Authorization: DemoKey local-example-only-demo-key' \
  http://localhost:8080/api/orders/B-200
```

Kết quả dự kiến: 200/404/404. Body của `A-100`:

```json
{"id":"A-100","status":"READY"}
```

Key sai:

```bash
curl -i -H 'Authorization: DemoKey wrong-key' \
  http://localhost:8080/api/whoami
```

Dự kiến 401, không echo key. Trên PowerShell, dùng `curl.exe` nếu cần đúng syntax curl Unix; `Invoke-WebRequest` có API header dictionary riêng. Shell history/process arguments có thể lưu raw credential, chỉ sử dụng demo key trong lab.

**Đây là output dự kiến của code**, không phải tuyên bố đã chạy server bên ngoài bài học.

## 6. Kiểm thử integration bằng WebTestClient

Tạo `src/test/java/example/customauth/CustomAuthApplicationTests.java`:

```java
package example.customauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = "demo.api-key=integration-test-key")
@AutoConfigureWebTestClient
class CustomAuthApplicationTests {

    private static final String GOOD = "DemoKey integration-test-key";

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteWorksWithoutCredential() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PONG");
    }

    @Test
    void noCredentialIs401() {
        client.get().uri("/api/whoami")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "DemoKey realm=\"learning-api\"");
    }

    @Test
    void correctKeyGivesOnlyMinimalPublicIdentity() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.clientId").isEqualTo("partner-a")
                .jsonPath("$.tenantId").isEqualTo("tenant-a")
                .jsonPath("$.credentials").doesNotExist();
    }

    @Test
    void wrongKeyIs401() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION,
                        "DemoKey wrong-key")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void emptyKeyIs401() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "DemoKey ")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void basicOrBearerAreNotDemoKey() {
        client.get().uri("/api/whoami")
                .headers(h -> h.setBasicAuth("user", "pass"))
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer fake-jwt")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void multipleAuthorizationHeadersAreRejected() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, GOOD, GOOD)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void ownedOrderCanBeRead() {
        client.get().uri("/api/orders/A-100")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("A-100");
    }

    @Test
    void anotherPartnerOrderIsNotVisible() {
        client.get().uri("/api/orders/A-101")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void anotherTenantOrderIsNotVisible() {
        client.get().uri("/api/orders/B-200")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void postNotEnabledEvenWithKey() {
        client.post().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void requestDoesNotPersistLoginForNextRequest() {
        client.get().uri("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, GOOD)
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/whoami")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
gradle test
```

**Giới hạn:** `WebTestClient` kiểm pipeline Spring Security HTTP, nhưng không chứng minh HTTPS production, rotation/revocation, rate limits hoặc trust của một external identity provider. Test duplicate header phụ thuộc cách mock HTTP client biểu diễn values; ở gateway thực cần kiểm thêm trường hợp proxy merge duplicates.

## 7. Kiểm thử manager độc lập với StepVerifier

Tạo `src/test/java/example/customauth/AuthenticationManagerTests.java`:

```java
package example.customauth;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuthenticationManagerTests {

    private final DemoKeyReactiveAuthenticationManager manager =
            new DemoKeyReactiveAuthenticationManager("expected-key");

    @Test
    void candidateIsNotAuthenticated() {
        var token = ApiKeyAuthenticationToken.presented("expected-key");
        assertFalse(token.isAuthenticated());
        assertThrows(IllegalArgumentException.class,
                () -> token.setAuthenticated(true));
    }

    @Test
    void correctKeyCreatesVerifiedPrincipalWithoutCredential() {
        StepVerifier.create(manager.authenticate(
                ApiKeyAuthenticationToken.presented("expected-key")))
                .assertNext(auth -> {
                    assertTrue(auth.isAuthenticated());
                    assertNull(auth.getCredentials());
                    assertEquals("partner-a", auth.getName());
                    assertTrue(auth.getAuthorities().stream()
                            .anyMatch(a -> a.getAuthority()
                                    .equals("SCOPE_orders:read")));
                })
                .verifyComplete();
    }

    @Test
    void wrongKeyFailsInsteadOfEmpty() {
        StepVerifier.create(manager.authenticate(
                ApiKeyAuthenticationToken.presented("wrong")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unsupportedAuthenticationTypeReturnsEmpty() {
        StepVerifier.create(manager.authenticate(
                new TestingAuthenticationToken("user", "secret")))
                .verifyComplete();
    }
}
```

Test manager làm rõ:
- Candidate không tự đánh dấu verified.
- Secret đúng tạo Authentication mới, credentials null và authorities do server gán.
- Sai key phát `BadCredentialsException` thay vì `Mono.empty()`.
- Token type không hỗ trợ trả `Mono.empty()`.
- Không cần Spring Context cho test thuần manager, tiết kiệm thời gian.

Có thể kiểm `CurrentCallerService` riêng bằng:

```java
// MẢNH TEST minh họa, cần import các class/Assertions.
var verified = ApiKeyAuthenticationToken.verified(
        new ApiKeyPrincipal("partner-a", "tenant-a"),
        java.util.List.of(
                new org.springframework.security.core.authority
                        .SimpleGrantedAuthority("SCOPE_orders:read")));

StepVerifier.create(new CurrentCallerService()
        .requireCaller()
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(verified)))
        .assertNext(caller -> assertEquals(
                "partner-a", caller.clientId()))
        .verifyComplete();
```

Đoạn trên không phải file runnable độc lập: cần imports `StepVerifier`, `ReactiveSecurityContextHolder` và `assertEquals`. Test missing context tương tự nên chờ `AccessDeniedException`. Không dùng `SecurityContextHolder` ThreadLocal trong WebFlux service.

## 8. Test matrix ngắn để xác minh đường đi

| HTTP request | Converter | Manager | Authorization | Kết quả dự kiến |
| --- | --- | --- | --- | --- |
| GET `/public/ping` không header | Không match | Không | permitAll | 200 |
| GET `/api/whoami` không key | Empty | Không | unauthenticated | 401 |
| GET `/api/whoami` key đúng | Candidate | verified | authenticated | 200 |
| GET `/api/whoami` key sai | Candidate | BadCredentials | failure handler | 401 |
| GET `/api/whoami` Basic | Empty | Không | unauthenticated | 401 |
| GET `/api/orders/A-100` đúng key | Candidate | verified, scope read | own order | 200 |
| GET `/api/orders/A-101` đúng key | Candidate | verified, scope read | khác owner | 404 |
| GET `/api/orders/B-200` đúng key | Candidate | verified, scope read | khác tenant | 404 |
| POST `/api/whoami` đúng key | Candidate | verified | denyAll | 403 |
| GET `/api/whoami` sau request trước đã auth nhưng không key | Empty | Không | NoOp/unauthenticated | 401 |

Không khẳng định mọi request route không tồn tại đều 404: nếu `anyExchange().denyAll()` kiểm trước handler, caller authenticated có thể nhận 403 theo policy. Với multi-chain hay filter/handler khác, kết quả cần kiểm theo environment.

## 9. Chọn stateless hoặc WebSession đúng cách

### 9.1. Stateless NoOp

Trong ví dụ:
- `filter.setSecurityContextRepository(noSession)`;
- `http.securityContextRepository(noSession)`;
- Mỗi HTTP request có key thì tự xác thực;
- Không key thì không thừa hưởng Authentication cũ.

Một số framework components khác có thể tạo WebSession vì mục đích riêng; điều quan trọng là **SecurityContext authentication không được lưu giữa requests**, không phải lời hứa không có một session object nào trên toàn ứng dụng.

### 9.2. Stateful form login

Nếu thực sự muốn lưu đăng nhập sau một request `POST /session/login`, có thể dùng:

```java
// MẢNH CẤU HÌNH: chỉ minh họa thay đổi kiến trúc.
var repository =
        new WebSessionServerSecurityContextRepository();

filter.setSecurityContextRepository(repository);
http.securityContextRepository(repository);
```

Nhưng phải đổi matcher sang login processing URL, converter sang form/body phù hợp, success/failure handler sang redirect/JSON hợp lệ và bổ sung:
- CSRF token cho browser requests thay đổi trạng thái;
- Secure/HttpOnly/SameSite cookie;
- session fixation protection;
- logout/invalidation;
- session timeout/rotation;
- shared store khi chạy nhiều nodes;
- tránh open redirect sau login.

**Không copy hai dòng trên vào API key per-request nếu chưa muốn browser gọi API không có Authorization sau một lần xác thực.**

### 9.3. Success handler khác nhau

**API per request:** dùng `WebFilterChainServerAuthenticationSuccessHandler` để request được xuống `AuthorizationWebFilter`, rồi controller.

**Login endpoint:** có thể chọn success handler kết thúc bằng 200/204 hoặc redirect, vì đây là action đăng nhập riêng. Nếu áp handler chốt 204 vào filter nhận credential trên **tất cả /api/**, mọi request đúng key sẽ bị chặn trước controller; authorization theo order không chạy như mong muốn.

### 9.4. Failure handler và entry point

Failure handler xử lý **attempt xác thực sai**. Entry point xử lý **request chưa authenticated nhưng tài nguyên đòi auth**. Thiếu header thường làm converter empty, **không đi vào failure handler**; vì vậy entry point phải trả 401.

Một 401 tối giản:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DemoKey realm="learning-api"
```

Không echo body chứa secret, policy details hoặc stack trace. 403 dành cho một principal đã xác thực nhưng thiếu authority, không dùng 403 thay cho mọi invalid key.

## 10. Nhiều SecurityWebFilterChain và sự phối hợp các cơ chế

Một ứng dụng thực tế có thể có:
- `/api/partners/**` dùng API key/mTLS;
- `/api/clients/**` dùng JWT bearer;
- `/web/**` dùng OIDC session login;
- `/public/**` permitAll.

Với nhiều `SecurityWebFilterChain`, Spring Security chọn **chain đầu tiên match request**; không mặc định chạy cả ba.

```java
// MẢNH KIẾN TRÚC, không runnable riêng.
@Bean
@Order(1)
SecurityWebFilterChain partners(ServerHttpSecurity http) {
    return http.securityMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                    "/api/partners/**"))
            // addFilterAt(customFilter, AUTHENTICATION)
            // authorizeExchange ...
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain others(ServerHttpSecurity http) {
    return http.securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/**"))
            // oauth2ResourceServer, oauth2Login hoặc rules...
            .build();
}
```

Đây là fragment không copy nguyên làm project runnable; cần wiring filters/bean/policy tương ứng. Trong production:
1. Match chain hẹp trước chain rộng.
2. Test start/callback/login/API paths của từng mechanism.
3. Không để chain `/**` cướp request đáng lẽ dùng partner filter.
4. CORS/preflight phải qua chain/policy xử lý đúng.
5. Không đưa candidate DemoKey vào manager xử lý JWT hoặc ngược lại.

Nếu một chain thực sự hỗ trợ nhiều token types, xem `DelegatingServerAuthenticationConverter`, `DelegatingReactiveAuthenticationManager` và `ReactiveAuthenticationManagerResolver<ServerWebExchange>`. Khi credential được nhận diện nhưng **sai**, không âm thầm downgrade sang scheme yếu.

**Tránh global double registration:** Một `AuthenticationWebFilter` khai như bean `WebFilter` có thể được WebFlux đăng ký toàn cục, rồi lại được chèn bằng `addFilterAt` gây chạy hai lần. Demo tạo filter **bên trong `SecurityWebFilterChain` bean**, không khai filter như global component.

## 11. CSRF, CORS, HTTPS và trust boundaries

### 11.1. CSRF

Trong API stateless mà client tự gắn Authorization header, có thể xem xét tắt CSRF **riêng chain đó** sau khi xác minh không có cookie/session credential được browser tự gửi. Nhưng với form login hoặc cookie authentication, cần CSRF protection cho request thay đổi trạng thái. Dùng OAuth2/OIDC cũng không tự thay thế CSRF cho các mutation qua cookie.

### 11.2. CORS preflight

Browser gọi cross-origin với Authorization header thường gửi `OPTIONS` preflight **không chứa actual key**. Nếu `/api/**` matcher bắt OPTIONS và `anyExchange().denyAll()` từ chối trước CORS, browser có thể báo CORS error.

Giải pháp: cấu hình `CorsWebFilter` hoặc `ServerHttpSecurity.cors(...)` với allowed origins/methods/headers có allowlist, xử lý preflight trước authentication filter. Không bật `Access-Control-Allow-Origin: *` + credentials tùy tiện. CORS chỉ kiểm browser JS đọc cross-origin response, **không thay Authentication** và không cản server clients dùng curl.

### 11.3. HTTPS

API key là bearer secret: ai lấy được key có thể sử dụng lại. Bắt buộc HTTPS qua Internet, TLS termination/gateway đáng tin, xóa/ghi đè các header không tin cậy và hạn chế log. Không chấp nhận `X-Authenticated-User`, `X-Tenant`, `X-Role` từ external request như bằng chứng xác thực.

### 11.4. Replay và brute force

Một secret dài chống đoán nhưng không chống việc **key bị đánh cắp**. Cần:
- CSPRNG và key entropy cao;
- key ID + digest, rotation/revocation;
- expiry, grant scope tối thiểu, per-key tenant;
- rate limiting, audit, alerts;
- optional mTLS-bound token/DPoP hoặc request signatures khi threat model yêu cầu;
- chống replay bằng nonce/timestamp/canonicalization/anti-replay store nếu tự thiết kế signed request; không chỉ thêm timestamp không verify.

### 11.5. Logging

Không:

```java
log.info("Authorization={}",
        exchange.getRequest().getHeaders()
                .getFirst(HttpHeaders.AUTHORIZATION));
```

Không bật HTTP wiretap/trace headers/body của token endpoint/proxy trong production nếu chưa redact. Chỉ log event category, request ID, verified client ID/tenant alias theo policy, latency, failure reason chuẩn hóa (invalid credential vs identity store unavailable), không log raw credential, hash, session ID hay email không cần thiết.

## 12. ReactiveAuthenticationManager với external identity store

Ví dụ manager đã làm SHA-256 nhanh và không blocking. Khi xác minh credential bằng R2DBC/Redis/IdP:

```java
// MẢNH MINH HỌA: repository, verifyAndBuildAuth cần tự định nghĩa.
return repository.findByKeyId(keyId)
        .switchIfEmpty(Mono.error(
                new BadCredentialsException("Invalid API key")))
        .flatMap(record -> verifyAndBuildAuth(record, presentedKey));
```

Phải kiểm:
- record tồn tại, active, chưa expired/revoked;
- digest/credential match constant time hoặc KDF phù hợp;
- tenant/client còn hoạt động;
- permissions từ trusted store;
- concurrent rate limit/backpressure;
- timeout/circuit breaker;
- cache invalidation đúng revocation SLA.

Sai:

```java
// SAI trong event loop WebFlux:
User user = jdbcTemplate.queryForObject("SELECT ...", ...);
return Mono.just(authenticated(user));
```

Gọi JDBC diễn ra **trước** khi tạo Mono và block thread. Nếu buộc phải dùng SDK blocking:

```java
// MẢNH MINH HỌA, cần định nghĩa blockingVerifier/verifiedAuth.
return Mono.fromCallable(() -> blockingVerifier.verify(key))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(result -> result.isValid()
                ? Mono.just(verifiedAuth(result))
                : Mono.error(new BadCredentialsException("Invalid key")));
```

Giới hạn concurrency, timeout và dùng executor riêng nếu throughput lớn; `boundedElastic` không có nghĩa tài nguyên vô hạn. Không tự gọi `block()` hoặc `subscribe()` trong AuthenticationManager.

**Lỗi IdP/DB outage phải fail-closed.** Nếu không thể kiểm credential, không tự tạo trusted Authentication. Phân biệt invalid credential với lỗi hạ tầng (ví dụ `AuthenticationServiceException`) cho metrics/alert nhưng response ra client không rò rỉ nội bộ.

## 13. Hướng dẫn production API key lifecycle

Schema khái niệm:

```text
credential_registry
  key_id
  key_digest
  client_id
  tenant_id
  granted_scopes
  status                 (active, suspended, revoked)
  expires_at
  created_at
  rotated_at
```

Flow:
1. Converter parse auth scheme/format, tách `key_id` nếu có, giới hạn length.
2. Manager lookup qua key ID bằng repository reactive.
3. Verify digest, active/expiry/revocation và rate-limit.
4. Tạo principal đã xác thực, authorities từ record server.
5. Không lưu raw secret; chỉ trả identity tối thiểu.
6. Resource service luôn kiểm tenant/owner/permissions.
7. Khi revoke/rotate, invalidate cache theo policy.
8. Phát metrics/audit đã redact, không tạo timing oracle cho enumeration.

Không dùng SHA-256 đơn giản cho **password entropy thấp**; dùng PBKDF2/BCrypt/Argon2 và kiểm theo policy. Với API key CSPRNG entropy cao, digest SHA-256 được cân nhắc cùng các yêu cầu storage/constant-time comparison. Một key ID public không phải quyền; key secret phải còn được xác minh.

Để rotation không gián đoạn:
- Tạo key mới với validity riêng;
- Phân phát qua secure secret manager;
- Cho khoảng chuyển đổi theo chính sách nếu có thể;
- Theo dõi traffic key cũ;
- Thu hồi key cũ đúng deadline;
- Xử lý incident revocation ngay nếu key bị lộ.

**Nếu có thể dùng OAuth2 client credentials + HTTPS/mTLS, hãy ưu tiên chuẩn thay vì tạo API-key protocol mới**. Filter vẫn hữu ích để tích hợp một legacy trust system khi không thể chuyển đổi ngay.

## 14. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Converter không chạy | Matcher `/api/**` không khớp, filter ngoài chain | Kiểm `setRequiresAuthenticationMatcher` và `addFilterAt` |
| Manager không chạy | Converter trả empty hoặc lỗi trước manager | Test convert empty/value/error |
| Key sai vẫn 200 | Manager tạo verified token quá sớm hoặc route permitAll | Fail closed, test wrong key |
| Key sai trả 403 | Entry point/failure handler sai hoặc authenticated giả | Sửa exception/401 mapping |
| Thiếu key vẫn 200 | Rule quên `authenticated` | Deny by default |
| Controller không chạy dù key đúng | Success handler kết thúc response sớm | Dùng `WebFilterChainServerAuthenticationSuccessHandler` |
| Request 2 không giữ login | NoOp repository, đúng với stateless | Gửi key mỗi request hoặc thiết kế session rõ |
| Request 2 không key vẫn 200 | Vô tình lưu WebSession | Dùng NoOp và test stateless |
| Principal null trong service | Dùng Servlet ThreadLocal, tự subscribe, context mất | `ReactiveSecurityContextHolder` |
| `SCOPE_orders:read` có nhưng không đọc được order | Tenant/owner mismatch | Kiểm policy DB, không bỏ filter |
| CORS OPTIONS trả 401/403 | Chưa xử lý preflight trước AuthN | Config CORS đúng chain |
| Key hợp lệ trên dev nhưng sai prod | Secret/rotation/env khác | Quản lý config theo môi trường |
| Header Duplicate xử lý không rõ | Proxy normalize/smuggling | Quy định một credential và test gateway |
| 500 khi DB auth lỗi | Blocking IO hoặc exception không phân loại | Reactive client, timeouts, fail-closed |
| Auth A lộ sang B | Cache static/global Authentication | Không lưu context dùng chung requests |
| Log lộ secret | In Authorization header/raw Authentication | Redact, hạn chế wiretap |
| User đã xác thực nhưng không có role | GrantedAuthority từ server thiếu hoặc mapper sai | Kiểm policy, không tin raw role header |
| Multi-chain bắt sai URL | Chain order/matcher rộng | Chain hẹp trước, test URL |
| Cấu hình csrf.disable vào cookie login | Bỏ CSRF defense | Tách stateless chain và browser chain |

## 15. Checklist QA và bảo mật

1. Chỉ đúng paths dùng custom scheme được custom filter xử lý.
2. Input parser giới hạn length, format, duplicate Authorization headers.
3. Candidate từ client luôn `isAuthenticated=false`.
4. Manager không trả authenticated khi credential sai, revoked, expired hoặc identity store unavailable.
5. Manager chỉ dùng `Mono.empty()` cho unsupported token types, không che wrong credential.
6. Verified Authentication không giữ raw key; principal/authorities từ server.
7. Success handler tiếp tục chain khi auth per request.
8. Failure handler và entry point trả 401 không leak secrets.
9. `authorizeExchange` deny by default, đúng scopes/methods.
10. Tenant/owner/record permission được kiểm ở service/DB.
11. NoOp repository nếu per-request stateless; không giữ Authentication giữa requests.
12. WebSession repository chỉ khi thiết kế login session và áp CSRF/cookie/logout protections.
13. Không dùng Servlet ThreadLocal `SecurityContextHolder` cho WebFlux.
14. Không block event loop; code xác thực I/O dùng reactive SDK hoặc bounded, timed offload.
15. Test no header, wrong header, missing key, valid key, unknown scheme, duplicate headers, wrong method, wrong tenant/owner.
16. HTTPS và proxy trust boundary bắt buộc trong production.
17. Secret lifecycle có strong generation, hashed storage, rotation, revocation, expiry, monitoring.
18. CORS preflight có policy riêng trước AuthN; không dùng CORS làm AuthN.
19. Credential values không vào URL, response body, logs, metrics, traces hoặc exception messages.
20. Có test integration qua ingress và monitoring rate/latency/bulkheads khi có remote verifier.

## 16. Câu hỏi tự kiểm tra

**1. AuthenticationWebFilter tự xác minh API key không?**  
Không. Nó điều phối matcher/converter/manager/handlers. `ReactiveAuthenticationManager` kiểm credential.

**2. Vì sao không gọi `setAuthenticated(true)` trên candidate của request?**  
Vì credential chưa được xác minh. Chỉ trusted manager được tạo token authenticated với authorities server-side.

**3. Converter trả Mono.empty nghĩa là gì?**  
Không tạo authentication attempt. Route protected vẫn phải trả 401 khi chưa có Authentication.

**4. Manager nhận DemoKey sai thì nên trả gì?**  
`Mono.error(new BadCredentialsException(...))`, không phải `Mono.empty()` hoặc trusted token.

**5. Khi nào manager nên trả empty?**  
Khi manager không hỗ trợ loại Authentication được chuyển vào.

**6. API key stateless dùng repository nào?**  
`NoOpServerSecurityContextRepository.getInstance()` cho custom filter và HTTP security context loading.

**7. Vì sao request thứ hai không có key phải 401 dù request đầu 200?**  
NoOp không lưu authentication sang request sau; key được gửi mỗi request.

**8. Filter phải được chèn ở thứ tự nào?**  
`SecurityWebFiltersOrder.AUTHENTICATION`, trước authorization.

**9. setRequiresAuthenticationMatcher làm gì?**  
Chọn requests filter cần thử xác thực, tránh chạy nhầm trên public/login paths.

**10. Controller đọc danh tính trong WebFlux service thế nào?**  
`ReactiveSecurityContextHolder.getContext()` trong publisher hoặc truyền immutable verified identity từ boundary.

**11. Vì sao không dùng Servlet SecurityContextHolder ThreadLocal?**  
Reactor có thể đổi threads và giữ context theo subscription, không theo một ThreadLocal cố định.

**12. 401 và 403 khác nhau?**  
401 cho chưa có credential hợp lệ; 403 cho đã authenticated nhưng thiếu permission.

**13. Key đúng nhưng order thuộc tenant khác trả gì?**  
Demo trả 404, không đọc record không thuộc quyền.

**14. Vì sao CORS OPTIONS không gửi DemoKey?**  
Preflight chỉ hỏi quyền cross-origin, không phải actual API request; cần xử lý CORS trước filter auth.

**15. Khi nào CSRF không thể tùy tiện disable?**  
Khi ứng dụng dùng browser session/cookie hoặc credential được browser tự gắn cho state-changing requests.

**16. Có nên đưa expected API key vào application.yml?**  
Không. Lab đọc biến môi trường; production dùng secret manager/identity store.

**17. Có phải SHA-256 đủ cho password do người dùng tự chọn?**  
Không. Password entropy thấp cần adaptive KDF và rate limiting; API key random entropy cao có threat model khác.

**18. Có cần test tenant/owner nếu đã có scope?**  
Có. Scope là loại thao tác, không chứng minh quyền trên record cụ thể.

**19. Vì sao không nên khai AuthenticationWebFilter global bean rồi addFilterAt lại?**  
Có thể double-register và chạy ngoài thứ tự/security context mong muốn.

**20. Lỗi identity store down có nên cho key cũ qua để giữ availability?**  
Không. Nếu không xác minh được thì fail-closed theo policy, không tự cấp identity.

**21. Khi hệ thống đã có JWT Resource Server, có nên thay bằng DemoKey?**  
Không. Ưu tiên `oauth2ResourceServer().jwt()` nếu đúng use case; custom filter chỉ khi có lý do cụ thể.

**22. WebTestClient và StepVerifier khác gì?**  
WebTestClient kiểm HTTP/security chain/controller; StepVerifier kiểm manager publisher và empty/error/verified transitions.

**23. Success handler trả 204 ngay có phù hợp với mọi API key request không?**  
Không. Nó kết thúc trước controller nếu mục đích là cho phép xử lý business; dùng success handler tiếp tục chain.

**24. Principal có nên chứa key secret?**  
Không. Chỉ chứa identity/tenant đã xác minh, credential nullable/erased.

**25. Yếu tố quan trọng nhất trong custom authentication?**  
Fail-closed, trusted manager là nơi duy nhất chứng minh credential, authorities do server cấp, đúng Reactor Context, giới hạn permission và kiểm negative tests.

**Ghi nhớ:** Trong **Spring Security WebFlux**, custom authentication được thiết kế thành **matcher → converter → unauthenticated candidate → ReactiveAuthenticationManager → verified Authentication → success/failure → Reactor SecurityContext → authorization**. Luôn phân biệt empty/error, chỉ cấp authorities từ nguồn đáng tin, không lưu identity nhầm giữa requests, không block event loop và kiểm quyền theo tenant/owner. `AuthenticationWebFilter` tích hợp scheme tùy biến vào chain, nhưng **không thay thế** secret lifecycle, HTTPS và authorization.

## Tài liệu tham khảo

- [Spring Security 6.3 — AuthenticationWebFilter API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): matcher, converter, manager, success/failure, repository.
- [Spring Security — ServerAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html): convert và `Mono.empty()`.
- [Spring Security — ServerHttpSecurity](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.html): `addFilterAt`, `authorizeExchange`, context repository.
- [Spring Security — SecurityWebFiltersOrder](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html): filter order.
- [Spring Security — NoOpServerSecurityContextRepository](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html): stateless repository.
- [Spring Security — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html): stateful repository.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context và method authorization.
- [Spring Security — WebFlux Test](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): WebTestClient security tests.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): browser sessions và CSRF.
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): preflight trước authentication.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): ServerWebExchange/WebFilter.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscriber Context.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): auth error policy, rate limiting.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): HTTPS, API auth, input validation.
