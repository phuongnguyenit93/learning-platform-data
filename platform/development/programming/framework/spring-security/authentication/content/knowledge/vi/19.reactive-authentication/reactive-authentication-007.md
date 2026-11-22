# ReactiveAuthenticationManagerResolver chọn manager theo ngữ cảnh yêu cầu

## Mục tiêu bài học

Trong **Spring Security WebFlux**, ứng dụng đôi khi phải xác thực các request theo **những chiến lược khác nhau**. Chẳng hạn, tenant A và tenant B có kho API key riêng; hoặc Resource Server cần chấp nhận JWT từ hai Identity Provider với issuer/JWK Set khác nhau.

`ReactiveAuthenticationManagerResolver<C>` giải quyết đúng nhu cầu đó: **chọn một ReactiveAuthenticationManager dựa trên ngữ cảnh**. Với HTTP WebFlux, ngữ cảnh thông dụng là `ServerWebExchange`. Resolver chọn **bên nào thực hiện xác thực**; chính manager được chọn mới quyết định credential hợp lệ hay không.

Sau bài này, bạn có thể:

1. Phân biệt `ReactiveAuthenticationManagerResolver`, `ReactiveAuthenticationManager`, `ServerAuthenticationConverter`, `AuthenticationWebFilter` và `SecurityWebFilterChain`.
2. Giải thích hợp đồng trả về `Mono<ReactiveAuthenticationManager>` của `resolve(context)`, không nhầm với kết quả `Mono<Authentication>` của `authenticate(input)`.
3. Viết resolver chọn manager theo exact URL path hoặc ngữ cảnh tenant đã kiểm soát.
4. Tích hợp resolver vào ứng dụng Spring Boot WebFlux bằng Java 17+, chạy được và kiểm thử bằng curl/WebTestClient.
5. Dùng `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` cho Resource Server có nhiều JWT issuer.
6. Phát hiện rủi ro khi tin header/claim chưa được xác minh, tự tạo JWT decoder cho issuer bất kỳ, làm blocking I/O trong event loop hoặc cấp authority cho nhầm tenant.

**Phạm vi:** Spring Security 6.5.x, Spring Boot 3.5.x, Java 17+ và **Reactive WebFlux**. Các khái niệm của Servlet như `HttpSecurity`, `SecurityFilterChain`, `AuthenticationManagerResolver<HttpServletRequest>` hay `OncePerRequestFilter` là **API khác**, không được thay thế một cách máy móc.

## 1. Vì sao chọn manager theo request?

Giả sử một API phục vụ hai khách hàng doanh nghiệp:

~~~text
GET /api/alpha/me
  Authorization: Bearer <credential alpha>
  -> cần manager xác thực alpha

GET /api/beta/me
  Authorization: Bearer <credential beta>
  -> cần manager xác thực beta
~~~

Nếu dùng một manager chấp nhận mọi credential, ứng dụng có thể vô tình cho key alpha truy cập tài nguyên beta. Chọn manager riêng giúp làm rõ ranh giới, nhưng **không thay thế authorization**: sau khi key được xác thực, vẫn phải kiểm tra người dùng/ứng dụng có quyền truy cập đúng tenant và tài nguyên hay không.

Một Resource Server nhiều issuer có thể nhận:

~~~text
JWT A: iss = https://identity.example.org/issuer-a
JWT B: iss = https://identity.example.org/issuer-b

Issuer A: khóa ký/JWKS, audience và chính sách roles A
Issuer B: khóa ký/JWKS, audience và chính sách roles B
~~~

Manager A và manager B có thể dùng decoder và validator riêng. Resolver giúp chọn đúng manager theo ngữ cảnh; token tiếp tục phải được **kiểm tra chữ ký, issuer, audience và thời hạn** trong manager.

### Không nên dùng resolver khi nào?

Nếu hệ thống chỉ có một cơ chế và một issuer, có thể dùng một `ReactiveAuthenticationManager` hoặc cấu hình Resource Server `jwt()` thông thường. Resolver thêm độ phức tạp cho trust boundary, cache, failure handling và unit test; chỉ dùng khi có yêu cầu thay đổi strategy theo request.

## 2. API contract của resolver và manager

Hợp đồng Java:

~~~java
public interface ReactiveAuthenticationManagerResolver<C> {
    Mono<ReactiveAuthenticationManager> resolve(C context);
}

public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Các interface thuộc package `org.springframework.security.authentication`. Trong WebFlux:

~~~java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver;

Mono<ReactiveAuthenticationManager> managerMono =
    resolver.resolve(exchange);
~~~

| Thành phần | Đầu vào | Đầu ra | Trách nhiệm |
| --- | --- | --- | --- |
| `ServerAuthenticationConverter` | `ServerWebExchange` | `Mono<Authentication>` chưa trusted | Trích credential từ request |
| `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | Ngữ cảnh request | `Mono<ReactiveAuthenticationManager>` | Chọn manager sẽ kiểm tra |
| `ReactiveAuthenticationManager` | Token yêu cầu xác thực | `Mono<Authentication>` | Xác minh credential hoặc từ chối |
| `AuthenticationWebFilter` | Exchange và converter/resolver/manager | Response hoặc tiếp tục filter chain | Điều phối authentication, failure/success |
| `SecurityWebFilterChain` | Exchange | Chuỗi WebFilter phù hợp | Bảo vệ route và chính sách authorization |

**Điểm then chốt:** `resolve()` trả về **một manager**, không phải kết quả đăng nhập. Chỉ sau khi manager chạy `authenticate()` thành công mới có một `Authentication` đáng tin.

### Ba dạng kết quả reactive

- `Mono.just(manager)`: chọn được manager.
- `Mono.error(exception)`: context không hợp lệ hoặc hệ thống không thể chọn strategy.
- `Mono.empty()`: không chọn được manager. **Đừng hiểu empty = cho phép truy cập**; hành vi tùy thành phần sử dụng resolver và authorization phải fail closed.

Tương tự, với manager:

- `Mono.just(authenticatedResult)`: đã xác thực thành công.
- `Mono.error(AuthenticationException)`: credential không hợp lệ hoặc trạng thái không cho phép.
- `Mono.empty()`: manager không đưa ra kết quả; không dùng như một cách báo “xác thực thành công”.

Không được biến một input token `authenticated=false` thành true ngay trong converter chỉ vì request có header. Mọi principal và authority trong result phải được manager xác minh/cấp từ nguồn đáng tin phía server.

## 3. Luồng request trong Spring Security WebFlux

~~~text
HTTP request
      |
      v
SecurityWebFilterChain
      |
      v
AuthenticationWebFilter
      |
      +--> ServerAuthenticationConverter
      |        -> Mono<Authentication> (chưa trusted)
      |
      +--> ReactiveAuthenticationManagerResolver<ServerWebExchange>
      |        -> đọc request context
      |        -> chọn Mono<ReactiveAuthenticationManager>
      |
      +--> selectedManager.authenticate(input)
      |        -> kiểm tra credential, tenant, account status
      |
      +---- success: trusted Authentication
      |        -> ReactiveSecurityContextHolder (Reactor Context)
      |        -> authorization và handler
      |
      +---- failure: AuthenticationException
               -> failure handler / 401
~~~

`AuthenticationWebFilter` có constructor nhận `ReactiveAuthenticationManagerResolver<ServerWebExchange>`. Filter cũng nhận `ServerAuthenticationConverter` và matcher quyết định request nào cần thử authentication.

Với OAuth2 Resource Server, DSL `ServerHttpSecurity.oauth2ResourceServer(...)` có method `authenticationManagerResolver(...)` để tích hợp resolver chuyên cho bearer token.

### ReactiveSecurityContextHolder khác ThreadLocal của Servlet

Spring Security WebFlux dùng Reactor Context và `ReactiveSecurityContextHolder` để truyền trạng thái xác thực qua reactive chain. Không nên lấy trạng thái bằng `SecurityContextHolder.getContext()` rồi giả định nó an toàn qua mọi bước async như code Servlet.

Trong handler, có thể nhận `Mono<Principal>` hoặc dùng các API Spring Security reactive phù hợp. Khi request kết thúc, không tự giữ reference `ServerWebExchange` trong singleton/cache.

## 4. Chọn context theo đâu thì an toàn?

### 4.1. Exact path do server cấu hình

Một resolver có thể chọn alpha manager cho `/api/alpha/me` và beta manager cho `/api/beta/me`. Exact matching giúp mô hình học tập rõ ràng, giảm khả năng fallback không mong muốn.

Tuy nhiên, **URL không tự chứng minh người gửi là tenant alpha**. Manager alpha phải thực sự kiểm tra credential alpha, và authorization phải bảo vệ resource của alpha.

### 4.2. Header X-Tenant

~~~http
GET /api/data HTTP/1.1
X-Tenant: beta
Authorization: Bearer some-client-supplied-value
~~~

`X-Tenant` là input từ client. Nó có thể là **gợi ý chọn manager**, nhưng phải:

1. Chỉ cho phép tenant nằm trong allowlist/registry do server quản lý.
2. Xác thực credential bằng manager thích hợp.
3. Ràng buộc principal, issuer, audience và tenant đã xác minh.
4. Kiểm tra quyền truy cập tài nguyên của tenant đó.

Nếu header do reverse proxy cung cấp, chỉ tin nó khi proxy đã **xóa/ghi đè header client** và request tới backend chỉ đi qua đường tin cậy.

### 4.3. Host, forwarded headers và subdomain

Host như `alpha.example.com` có thể chọn tenant. Nhưng header `Host`, `X-Forwarded-Host` và `Forwarded` có thể bị giả mạo nếu ingress/proxy không kiểm soát.

Cần chuẩn hóa origin/trusted proxy, map host vào tenant trên server, dùng allowlist, và test spoofing. Không biến một host bất kỳ được client yêu cầu thành issuer/JWKS URL.

### 4.4. Issuer trong JWT chưa xác minh

JWT chứa claim `iss` có thể đọc trước khi xác minh chữ ký. Khi dùng issuer để chọn decoder, `iss` chỉ là **routing hint chưa tin cậy**.

Phương án an toàn:

~~~text
Đọc JWT iss (chưa trusted)
        |
        v
So với tập issuer ĐƯỢC TIN đã cấu hình
        |
        +-- không có -> REJECT
        |
        +-- có -> chọn manager tương ứng
                    |
                    v
             xác minh JWT signature
             kiểm tra iss/exp/nbf/aud
                    |
                    v
             cấp Authentication đáng tin
~~~

**Không tạo decoder cho mọi `iss` mà client gửi.** Kẻ tấn công có thể tự lập Authorization Server, phát JWT hợp lệ với khóa của họ rồi khiến API chấp nhận; còn có thể ép backend gọi URL nội bộ qua discovery/JWKS (**SSRF**).

## 5. Mẫu runnable Java 17+: hai manager theo exact route

Ví dụ dưới đây không phụ thuộc một JWT issuer ngoài, để bạn kiểm tra resolver trực tiếp:

- `GET /api/alpha/me` dùng key demo `alpha-demo-key`.
- `GET /api/beta/me` dùng key demo `beta-demo-key`.
- Resolver xem **exact path**, chọn manager được khởi tạo từ server.
- Converter đọc Authorization Bearer và tạo token `unauthenticated`.
- Manager tương ứng kiểm tra credential, tạo principal/authority đáng tin.
- API dùng **NoOpServerSecurityContextRepository**: request sau cần cung cấp key lại.
- Header sai, thiếu hoặc key của tenant khác bị từ chối.

**Chỉ dùng key hard-coded cho training.** Production cần key sinh ngẫu nhiên entropy cao, lưu verifier an toàn, TLS, rotation/revocation, quota/rate limit và auditing. Nếu dùng JWT thật, ưu tiên OAuth2 Resource Server thay vì tự so chuỗi Bearer.

### 5.1. Gradle project

~~~text
reactive-resolver-demo/
  settings.gradle
  build.gradle
  src/main/java/example/reactive/ResolverDemoApplication.java
  src/test/java/example/reactive/ResolverDemoApplicationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-resolver-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
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
~~~

Không thêm `spring-boot-starter-web` vào demo. Khi có cả MVC và WebFlux starter, Spring Boot có thể chọn web application type **Servlet** theo cấu hình mặc định, gây nhầm lẫn giữa `HttpSecurity` và `ServerHttpSecurity`.

### 5.2. File Java hoàn chỉnh

`src/main/java/example/reactive/ResolverDemoApplication.java`:

~~~java
package example.reactive;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.Principal;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ResolverDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResolverDemoApplication.class, args);
    }

    private static ReactiveAuthenticationManager managerFor(
            String expectedKey, String principal, String authority) {

        return request -> Mono.defer(() -> {
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            Object credentials = request.getCredentials();
            if (!(credentials instanceof String supplied)) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            // Minh họa: production không hard-code API keys.
            boolean valid = MessageDigest.isEqual(
                expectedKey.getBytes(StandardCharsets.UTF_8),
                supplied.getBytes(StandardCharsets.UTF_8)
            );

            if (!valid) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            Authentication verified =
                UsernamePasswordAuthenticationToken.authenticated(
                    principal,
                    null,
                    List.of(new SimpleGrantedAuthority(authority))
                );

            return Mono.just(verified);
        });
    }

    @Bean
    ReactiveAuthenticationManagerResolver<ServerWebExchange>
            authenticationManagerResolver() {

        ReactiveAuthenticationManager alpha =
            managerFor("alpha-demo-key",
                "svc-alpha", "SCOPE_alpha.read");

        ReactiveAuthenticationManager beta =
            managerFor("beta-demo-key",
                "svc-beta", "SCOPE_beta.read");

        return exchange -> {
            String path = exchange.getRequest().getPath()
                .pathWithinApplication().value();

            // Không lấy tenant/role đáng tin từ header của client.
            return switch (path) {
                case "/api/alpha/me" -> Mono.just(alpha);
                case "/api/beta/me" -> Mono.just(beta);
                default -> Mono.error(
                    new BadCredentialsException("Unsupported route")
                );
            };
        };
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange>
                resolver) {

        AuthenticationWebFilter authenticationWebFilter =
            new AuthenticationWebFilter(resolver);

        ServerAuthenticationConverter converter = exchange -> {
            List<String> authValues = exchange.getRequest()
                .getHeaders().getOrEmpty(HttpHeaders.AUTHORIZATION);

            if (authValues.isEmpty()) {
                return Mono.empty();
            }
            if (authValues.size() != 1) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            String header = authValues.get(0);
            if (!header.regionMatches(true, 0, "Bearer ", 0, 7)) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            String rawKey = header.substring(7);
            if (rawKey.isBlank()
                    || rawKey.length() > 256
                    || rawKey.indexOf(' ') >= 0) {
                return Mono.error(
                    new BadCredentialsException("Invalid credential")
                );
            }

            return Mono.just(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "incoming", rawKey
                )
            );
        };

        authenticationWebFilter.setServerAuthenticationConverter(converter);
        authenticationWebFilter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                "/api/alpha/me", "/api/beta/me"
            )
        );
        authenticationWebFilter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
            )
        );
        authenticationWebFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        http
            .httpBasic(spec -> spec.disable())
            .formLogin(spec -> spec.disable())
            // Chỉ cho API demo header-only không dựa vào cookie.
            // App thật cần threat model CSRF tương ứng.
            .csrf(spec -> spec.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/alpha/me")
                    .hasAuthority("SCOPE_alpha.read")
                .pathMatchers("/api/beta/me")
                    .hasAuthority("SCOPE_beta.read")
                .anyExchange().denyAll()
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)
                )
            )
            .addFilterAt(authenticationWebFilter,
                SecurityWebFiltersOrder.AUTHENTICATION);

        return http.build();
    }

    @RestController
    public static class Api {
        @GetMapping("/api/{tenant}/me")
        Mono<Map<String, String>> me(
                @PathVariable String tenant,
                Mono<Principal> principal) {
            return principal.map(p -> Map.of(
                "tenant", tenant,
                "principal", p.getName()
            ));
        }
    }
}
~~~

### 5.3. Giải thích đường đi thực tế

**Bước 1 — HTTP request:** người dùng gọi `/api/alpha/me` và gửi `Authorization: Bearer alpha-demo-key`.

**Bước 2 — Converter:** chỉ parse Header, giới hạn kích thước, tạo `UsernamePasswordAuthenticationToken.unauthenticated`. Chuỗi `incoming` chỉ là nhãn ở request token, không phải principal đã xác minh.

**Bước 3 — Resolver:** đọc exact path của exchange, trả `Mono.just(alpha)`. Không xem giá trị token là bằng chứng để chọn một tenant khác hoặc tạo manager bất kỳ.

**Bước 4 — Manager:** alpha-manager kiểm tra key. Nếu khớp, trả result mới với principal `svc-alpha` và authority `SCOPE_alpha.read`. Nếu không khớp, trả `Mono.error(new BadCredentialsException(...))`.

**Bước 5 — Filter:** xử lý Authentication result trong reactive context, hoặc dùng failure handler trả 401.

**Bước 6 — Authorization:** endpoint alpha yêu cầu authority do alpha-manager cấp. Một result hợp lệ nhưng thiếu scope vẫn phải bị từ chối.

**Bước 7 — Request sau:** không có phiên đăng nhập được lưu qua `NoOpServerSecurityContextRepository`. Mỗi request phải gửi credential mới.

**Vì sao return Mono.defer?** Nó trì hoãn chạy logic kiểm tra cho tới khi subscription. Nhưng `Mono.defer` không biến blocking work thành non-blocking; ở demo toàn bộ thao tác là tính toán nhỏ trong bộ nhớ.

### 5.4. Khởi chạy và kiểm tra bằng curl

Từ thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Mặc định chạy ở `http://localhost:8080` nếu chưa đổi port.

**Key alpha gọi alpha:**

~~~bash
curl -i -H 'Authorization: Bearer alpha-demo-key' \
  http://localhost:8080/api/alpha/me
~~~

Kỳ vọng **HTTP 200**, response JSON có `tenant=alpha` và `principal=svc-alpha`. Ví dụ:

~~~json
{"tenant":"alpha","principal":"svc-alpha"}
~~~

Thứ tự trường JSON có thể khác; không viết test so chuỗi JSON nguyên văn nếu không cần.

**Key beta gọi beta:**

~~~bash
curl -i -H 'Authorization: Bearer beta-demo-key' \
  http://localhost:8080/api/beta/me
~~~

Kỳ vọng 200 với `tenant=beta` và `principal=svc-beta`.

**Key alpha gọi beta:**

~~~bash
curl -i -H 'Authorization: Bearer alpha-demo-key' \
  http://localhost:8080/api/beta/me
~~~

Kỳ vọng **401**, vì beta-manager không công nhận credential alpha.

**Thiếu header:**

~~~bash
curl -i http://localhost:8080/api/alpha/me
~~~

Kỳ vọng **401**. Converter không tạo Authentication, authorization bảo vệ endpoint.

**Header không đúng Bearer:**

~~~bash
curl -i -H 'Authorization: NotBearer something' \
  http://localhost:8080/api/alpha/me
~~~

Kỳ vọng **401**.

**Stateless:** sau một request alpha hợp lệ, gọi alpha lần nữa không có header. Request thứ hai vẫn phải bị từ chối, không tự kế thừa Authentication.

### 5.5. WebTestClient integration tests

Tạo `src/test/java/example/reactive/ResolverDemoApplicationTest.java`:

~~~java
package example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ResolverDemoApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void alphaAcceptsOnlyItsCredential() {
        client.get().uri("/api/alpha/me")
            .header("Authorization", "Bearer alpha-demo-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("alpha")
            .jsonPath("$.principal").isEqualTo("svc-alpha");
    }

    @Test
    void betaAcceptsOnlyItsCredential() {
        client.get().uri("/api/beta/me")
            .header("Authorization", "Bearer beta-demo-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("beta")
            .jsonPath("$.principal").isEqualTo("svc-beta");
    }

    @Test
    void alphaCredentialIsRejectedByBetaManager() {
        client.get().uri("/api/beta/me")
            .header("Authorization", "Bearer alpha-demo-key")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingCredentialIsRejected() {
        client.get().uri("/api/alpha/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void invalidCredentialIsRejected() {
        client.get().uri("/api/alpha/me")
            .header("Authorization", "Bearer wrong-key")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void laterRequestDoesNotReuseAuthentication() {
        client.get().uri("/api/alpha/me")
            .header("Authorization", "Bearer alpha-demo-key")
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/alpha/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Có **6 phương thức @Test**. Khi chúng chạy thành công, Gradle trả **BUILD SUCCESSFUL**; báo cáo HTML thường nằm tại `build/reports/tests/test/index.html`.

Các test này kiểm tra converter, resolver, manager và SecurityWebFilterChain **thật**, không mock một manager luôn trả success. Việc kiểm tra “alpha key không qua beta” quan trọng hơn chỉ khẳng định `resolve(exchange)` trả manager khác null.

**Giới hạn:** ví dụ không có JWT signer, IdP hay database thật; nó chứng minh dynamic manager selection, không thay thế kiểm thử JWT signature/issuer/audience hoặc secret store production.

## 6. Cấu hình thực tế: nhiều issuer JWT bằng JwtIssuerReactiveAuthenticationManagerResolver

Khi Spring Security WebFlux Resource Server nhận JWT của hai issuer được tin, không cần tự viết parsing/JWS verification.

Thêm dependency Resource Server vào project WebFlux:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

**Thay thế demo custom AuthenticationWebFilter ở trên**, không đặt hai filter cùng xử lý Authorization Bearer nếu chưa thiết kế rõ thứ tự.

Một cấu hình trích trong class Spring Configuration:

~~~java
@Bean
SecurityWebFilterChain resourceServerChain(ServerHttpSecurity http) {

    JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
            .fromTrustedIssuers(
                "https://identity.example.org/issuer-a",
                "https://identity.example.org/issuer-b"
            );

    http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(resolver)
        );

    return http.build();
}
~~~

Import điển hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
~~~

Đây là **mã tích hợp**, không phải class ứng dụng tự chạy. Cần Issuer Metadata/JWKS endpoint thật, JWT hợp lệ từ các issuer, dependency Resource Server và cấu hình Spring Boot tương ứng.

### 6.1. Cơ chế nhiều issuer

`JwtIssuerReactiveAuthenticationManagerResolver`:

1. Tìm Bearer token từ ServerWebExchange.
2. Đọc `iss` như **hint để chọn strategy**.
3. So khớp issuer với danh sách **trusted issuers**.
4. Tạo/chọn `JwtReactiveAuthenticationManager` phù hợp.
5. Manager/decoder xác minh JWT signature và claims.
6. Security chain thực hiện authorization theo kết quả đã xác thực.

Lời gọi `fromTrustedIssuers(...)` là điểm bắt buộc quan trọng trong mô hình này: không nhận tùy tiện một issuer lạ. Spring Security 6.5 ghi nhận manager theo issuer có thể được tạo **lazy** khi có request đầu tiên, giúp app startup không nhất thiết phụ thuộc ngay vào IdP đang online.

**Nhớ:** một chuỗi `iss` nằm trong JWT chưa được verify **không chứng minh** issuer đó đáng tin. Allowlist quyết định được dùng decoder nào; sau đó vẫn phải xác minh chữ ký, `iss`, thời hạn, audience và policy.

### 6.2. Kiểm tra audience là bước khác issuer

Ví dụ token được issuer A ký đúng nhưng có:

~~~text
iss = https://identity.example.org/issuer-a
aud = payment-service
exp = còn hiệu lực
signature = hợp lệ
~~~

Nếu API này là `inventory-service` và yêu cầu audience đó, token trên **không được cấp quyền**, dù issuer A nằm trong allowlist. Thiết lập `OAuth2TokenValidator<Jwt>` phù hợp cho từng decoder, hoặc cấu hình Resource Server/BOM hỗ trợ audience validation trong môi trường sử dụng.

Khi manager được chọn theo issuer, nên áp dụng policy:

- `iss` chính xác.
- Chữ ký/JWS algorithm và public key đáng tin.
- `exp`, `nbf`, clock skew hợp lý.
- `aud` và có thể token type/client binding.
- Mapping scopes/roles theo issuer nhưng không vượt mức tenant đã xác minh.

### 6.3. Issuer động và SSRF

Spring Security cho phép truyền resolver từ issuer string:

~~~java
// Mã minh họa; trustedManagers là Map đã được quản trị server-side.
ReactiveAuthenticationManagerResolver<String> lookup =
    issuer -> Mono.justOrEmpty(trustedManagers.get(issuer));

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    new JwtIssuerReactiveAuthenticationManagerResolver(lookup);
~~~

**Chỉ lookup trong map/registry do server quản trị**. Đừng tạo một `ReactiveJwtDecoder` mới bằng URL tùy ý do token gửi:

~~~java
// KHÔNG AN TOÀN nếu untrustedIssuer lấy từ JWT chưa verify:
ReactiveJwtDecoders.fromIssuerLocation(untrustedIssuer);
~~~

Có hai lớp nguy cơ: attacker khiến server truy cập URL tùy ý (**SSRF**), và attacker dựng issuer hợp lệ của riêng họ để hệ thống chấp nhận JWT không được tin.

Với dynamic tenants cần lifecycle rõ ràng: ai được thêm/xóa issuer, version cấu hình, cache eviction, giới hạn số manager, JWKS rotation, timeout và metrics. Nếu issuer bị xóa khỏi trust store mà manager cached vẫn còn, ứng dụng phải có chính sách invalidation nhất quán.

### 6.4. Hỗ trợ JWT và opaque token trong cùng ứng dụng

Một số tenant phát JWT, tenant khác phát opaque token đòi introspection. Khi đó resolver có thể chọn manager triển khai khác nhau.

Đừng phân biệt token hợp lệ chỉ theo **số dấu chấm** hoặc chuỗi có vẻ giống JWT: client có thể tạo chuỗi tùy ý. Chọn strategy từ **context/tenant đã được hạn chế**, sau đó thực hiện validation phù hợp. Với opaque token phải kiểm tra introspection response và scopes; với JWT phải kiểm tra cryptographic signature và claims.

## 7. Resolver so với nhiều SecurityWebFilterChain

Một kiến trúc có thể dùng:

**Cách A — một SecurityWebFilterChain + resolver:** thích hợp khi nhiều tenant dùng cùng loại Bearer authentication filter nhưng manager/JWT issuer khác nhau.

**Cách B — nhiều SecurityWebFilterChain:** phù hợp khi API và giao diện web có cơ chế và chính sách khác hẳn nhau, ví dụ API Bearer stateless còn giao diện web dùng form login/cookie, CSRF và session.

Mẫu định hướng (không phải class độc lập):

~~~java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(resource -> resource
            .authenticationManagerResolver(apiResolver)
        )
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain web(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Các biến và import như `apiResolver`, `@Order`, `Customizer` cần khai báo. Đây là **mẫu tổ chức**; khi có nhiều chain, bảo đảm builder được Spring cung cấp theo đúng lifecycle, `securityMatcher` và thứ tự match đã được test. Không chép vào app hiện có mà không kiểm tra chain nào thực sự xử lý URL.

**Khác biệt thực chất:** resolver đổi *manager* nhưng không mặc nhiên đổi CSRF, session, exception handler hoặc request matcher toàn chain. Nếu các chính sách này cũng khác nhau, dùng nhiều chain có thể rõ ràng hơn.

## 8. Tại sao không chặn event loop?

`Mono` không biến một API blocking thành non-blocking.

Sai:

~~~java
// blockingLookup() chạy ngay, có thể chặn thread event loop.
return Mono.just(blockingLookup(tenant));
~~~

Nếu kho cấu hình có API reactive, dùng reactive operator:

~~~java
return reactiveRepository.findByTenant(tenant)
    .map(config -> managerFactory.forTrustedConfig(config));
~~~

Mẫu này là **trích đoạn minh họa**: repository và factory cần được định nghĩa, factory phải cache/reuse manager phù hợp. Nếu chỉ có JDBC/blocking API, dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` để cô lập có giới hạn, timeout, circuit breaker và metrics thay vì `block()`.

Không tạo mới decoder/JWK client trong mỗi request; tách bước quản trị tenant/issuer khỏi hot path, dùng cache với giới hạn và invalidation.

## 9. Phân biệt WebFlux và Servlet

| Servlet | WebFlux reactive |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `AuthenticationManagerResolver<HttpServletRequest>` | `ReactiveAuthenticationManagerResolver<ServerWebExchange>` |
| `Filter` / `OncePerRequestFilter` | `WebFilter` / `AuthenticationWebFilter` |
| `SecurityContextHolder` thường thread-local | `ReactiveSecurityContextHolder` qua Reactor Context |
| `HttpServletRequest` | `ServerWebExchange` |
| `MockMvc` | `WebTestClient` |

Không dùng `ThreadLocal` để giữ tenant giữa các đoạn reactive. Nếu cần truyền ngữ cảnh nghiệp vụ qua chain, dùng Reactor Context hoặc các cơ chế WebFlux phù hợp, và xác minh không đưa dữ liệu request chưa tin vào security authority.

## 10. Status HTTP và các nhánh thất bại

| Tình huống | Kết quả điển hình | Ghi chú |
| --- | --- | --- |
| Không gửi credential, endpoint cần authentication | **401** | Chưa xác thực |
| Gửi API key sai | **401** | Selected manager từ chối |
| Key alpha vào beta | **401** | Không được fallback sang alpha |
| Credential hợp lệ nhưng thiếu scope | **403** | Authorization từ chối |
| JWT issuer không allowlist | **401** | Không tìm manager đáng tin |
| JWT sai signature/iss/exp/aud | **401** | JWT decoder/manager từ chối |
| Tenant config backend lỗi | Thường **5xx/503** theo handler | Không được fail-open |
| URL không được phép | 403 hoặc 404 theo chain/router | Không được trả resource |
| Header Authorization lặp/malformed | **401** | Không parse thành trusted token |

Trong OAuth2 Resource Server thật, entry point có thể gửi `WWW-Authenticate: Bearer ...` theo RFC; nếu thay bằng `HttpStatusServerEntryPoint` như demo thì chỉ còn status đơn giản. Không làm mất hành vi giao thức nếu API clients phụ thuộc vào header đó.

## 11. Bẫy bảo mật và lỗi lập trình

### 11.1. Cho client tự chọn issuer rồi tạo decoder

Đây là dạng **SSRF + attacker-controlled issuer trust**. Chỉ tạo/chọn manager từ allowlist server-side, không từ URL bất kỳ trong JWT.

### 11.2. Nhầm role trong header thành GrantedAuthority

`X-Role: ADMIN` không chứng minh user là admin. Converter không được tạo trusted token với authority client cung cấp.

### 11.3. Không kiểm tra aud

Chữ ký của issuer đáng tin chỉ xác nhận token do issuer đó ký; không chứng minh token được phát cho API của bạn. Validate audience và token purpose.

### 11.4. Fallback sang manager yếu

Nếu tenant không được tìm thấy, không tự dùng manager mặc định chấp nhận credential khác loại. Hãy fail closed.

### 11.5. Dùng Mono.just để bọc JDBC blocking

Gọi blocking query vẫn chặn event-loop dù kết quả được bọc trong Mono. Dùng reactive client hoặc boundedElastic có giới hạn khi cần.

### 11.6. Cache kết quả theo raw token

Không giữ Bearer secret trong map/log. Cache strategy theo issuer/tenant trust registry; nếu cache token validation, phải có expiry, revocation và giới hạn bộ nhớ.

### 11.7. Đọc Host từ Internet như nguồn tin nội bộ

Kiểm soát `Host` và `Forwarded` tại proxy; không cho client tự định tuyến tới manager quản trị chỉ bằng header.

### 11.8. Manager cấp Authentication=true trước khi check

Credential parsing không phải authentication. Chỉ tạo trusted token sau khi xác minh key/JWT và kiểm tra user/tenant status.

### 11.9. Không test cross-tenant và missing credential

Chỉ test happy path alpha→alpha vẫn có thể bỏ lọt key alpha→beta. Test negative path là bắt buộc.

### 11.10. Dùng WebFlux filter rồi đọc SecurityContextHolder Servlet

Trong WebFlux, Authentication thuộc reactive context; dùng `ReactiveSecurityContextHolder` hoặc reactive handler arguments phù hợp.

### 11.11. Tạo mới JWT manager mỗi request

JWK discovery có thể gây độ trễ/DoS. Cache theo issuer đáng tin, giới hạn concurrent initialization và xử lý outage.

### 11.12. Sai tenant trong query/body

Resolver có thể chọn đúng manager theo path nhưng controller lại đọc `tenantId` trong JSON để truy cập database tenant khác. Authorization ở domain/service phải so tenant đã xác minh với resource cần đọc.

## 12. Chiến lược kiểm thử production

| Test | Yêu cầu kiểm chứng |
| --- | --- |
| Resolver chọn alpha từ exact path | Không chọn beta |
| Resolver chọn beta từ exact path | Không chọn alpha |
| Alpha key vào beta | Bị từ chối |
| Missing/malformed/repeated Authorization | Không tạo Authentication trusted |
| Unknown path/tenant | Fail closed |
| Authenticated nhưng sai authority | 403 |
| Request tiếp theo không header | Không thừa hưởng context |
| Trusted JWT issuer A/B | Chọn decoder tương ứng |
| JWT issuer chưa đăng ký | 401 và không gọi arbitrary JWKS URL |
| JWT A ký bằng khóa B | Bị từ chối |
| JWT sai aud/exp/nbf | Bị từ chối |
| Thêm/xóa issuer động | Cache/revoke trust đúng |
| Tenant configuration store down | Không fallback thành success |
| Multi-chain routing | Đúng chain xử lý URL |

Để kiểm thử JWT nhiều issuer, tạo **hai JWK Set server/issuer giả lập với key pair khác nhau**, phát JWT test có chữ ký thực, kiểm tra audience, issuer và key rotation. Không lấy việc giải mã payload Base64 thành công làm bằng chứng token đã được xác thực.

Để unit test riêng resolver path, có thể dùng `MockServerWebExchange`:

~~~java
// Mã minh họa trong JUnit test đã có resolver bean.
MockServerWebExchange exchange = MockServerWebExchange.from(
    MockServerHttpRequest.get("/api/alpha/me")
);

StepVerifier.create(resolver.resolve(exchange))
    .assertNext(manager -> assertNotNull(manager))
    .verifyComplete();
~~~

Test này chỉ chứng minh chọn được manager, **không chứng minh manager alpha là đúng** nếu không so identity hoặc chạy nó với credential alpha. Vì vậy integration tests trong mục 5.5 mới kiểm chứng hành vi cuối cùng.

## 13. Checklist trước production

- [ ] Xác định rõ lý do dùng resolver thay vì một manager hoặc nhiều chain.
- [ ] Nguồn ngữ cảnh request đã được đánh giá trust boundary.
- [ ] Có allowlist manager/issuer và xử lý tenant không tồn tại.
- [ ] Converter tạo Authentication chưa trusted, không gán role theo header.
- [ ] Manager xác minh credential, issuer, signature, aud, exp/nbf, tenant và account status.
- [ ] Authorization kiểm tra resource ownership, không chỉ tenant route.
- [ ] Resolver không dùng blocking I/O trên event loop.
- [ ] Không tạo manager/decoder vô hạn theo request, có cache và invalidation.
- [ ] 401/403/5xx được phân biệt, không fail-open khi backend lỗi.
- [ ] NoOp/reactive security context repository phù hợp session policy.
- [ ] Không log raw Authorization/token/secret.
- [ ] Test cross-tenant, issuer không tin, JWT sai chữ ký, audience và key rotation.
- [ ] Tách rõ WebFlux API với Servlet API khi dùng ví dụ trong dự án.
- [ ] Bảo vệ CSRF theo cách client thực sự gửi credential; không tắt chỉ vì endpoint là JSON.

## 14. Tự kiểm tra

**Câu 1.** `resolve(exchange)` trả gì?  
**Trả lời:** `Mono<ReactiveAuthenticationManager>`. Nó không tự tạo Authentication thành công.

**Câu 2.** Vì sao alpha key gửi vào `/api/beta/me` phải bị từ chối?  
**Trả lời:** URL chọn beta manager, beta manager không chấp nhận alpha key; không có fallback sang alpha.

**Câu 3.** Header `X-Tenant` có phải bằng chứng user thuộc tenant đó?  
**Trả lời:** Không, nó là input chưa tin. Phải xác minh credential và tenant binding trong manager/authorization.

**Câu 4.** Có an toàn khi tạo JWT decoder từ mọi `iss` trong token?  
**Trả lời:** Không, có rủi ro chấp nhận issuer do attacker kiểm soát và SSRF. Dùng allowlist trusted issuers.

**Câu 5.** JWT ký đúng nhưng audience của API khác có nên được chấp nhận?  
**Trả lời:** Không khi API yêu cầu audience riêng; phải validate `aud` ngoài signature/issuer.

**Câu 6.** `Mono.just(jdbc.find(...))` đã non-blocking chưa?  
**Trả lời:** Chưa. JDBC chạy trước khi Mono được tạo, có thể chặn event loop.

**Câu 7.** Khi nào nhiều SecurityWebFilterChain hợp lý hơn resolver?  
**Trả lời:** Khi không chỉ manager mà cả cơ chế/cookie/CSRF/session/authorization của API và web UI khác nhau.

**Câu 8.** Vì sao WebTestClient phải thử missing credential và cross-tenant?  
**Trả lời:** Vì resolver đúng đường happy path không chứng minh credential sai hoặc tenant khác bị chặn.

**Câu 9.** `ReactiveSecurityContextHolder` có giống servlet ThreadLocal không?  
**Trả lời:** Không. Nó sử dụng Reactor Context để mang Authentication qua pipeline reactive.

**Câu 10.** Khi config store lỗi, có nên dùng manager mặc định cho mọi tenant?  
**Trả lời:** Không. Fail closed và báo lỗi phù hợp, tránh hạ mức bảo vệ.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — OAuth2 Resource Server Multi-tenancy (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security 6.5 — JWT Resource Server (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — JwtIssuerReactiveAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Security 6.5 — AuthenticationWebFilter API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
