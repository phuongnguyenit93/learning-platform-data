# Tạo Authentication token chuyên biệt và ServerAuthenticationConverter

## Mục tiêu học tập

Bài học nằm trong **Xác thực mở rộng** của **Spring Security reactive (Spring WebFlux)**. Sau bài này bạn có thể:

- Phân biệt `Authentication`, `AbstractAuthenticationToken`, `ServerAuthenticationConverter`, `ReactiveAuthenticationManager` và `AuthenticationWebFilter`.
- Tạo một **custom Authentication token** có hai dạng rõ ràng: yêu cầu *chưa được xác thực* (credential candidate, không có quyền) và kết quả *đã xác thực* (principal + authorities do server cấp, không mang raw secret).
- Viết converter trả `Mono<Authentication>` từ `ServerWebExchange`; phân biệt **không có credential** → `Mono.empty()`, **có credential** → token unauthenticated, **header sai** → `Mono.error(AuthenticationException)`.
- Gắn converter và manager vào `AuthenticationWebFilter`, giới hạn bằng `setRequiresAuthenticationMatcher(...)` và đăng ký qua `ServerHttpSecurity.addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)`.
- Hiểu success/failure handlers, `NoOpServerSecurityContextRepository`, Reactor Context, 401 vs 403 và authorization dựa trên authorities.
- Chạy demo **Java 17, Spring Boot WebFlux** với một header API key thử nghiệm, rồi test converter/manager/filter chain bằng `StepVerifier` và `WebTestClient`.
- Tránh sai lầm tự `setAuthenticated(true)` trước khi verify, log credential, xử lý HTTP headers trùng lặp thiếu rõ ràng, dùng `block()/subscribe()` trong reactive security, đăng ký filter hai lần hoặc tắt security cho tất cả routes.

> Ví dụ dùng một **header API key nội bộ** chỉ để học cách mở rộng authentication. Key tĩnh có hạn chế replay/rotation; production nên cân nhắc OAuth2 Resource Server, mTLS hoặc signed requests theo threat model. Không dùng ví dụ này để giấu một credential trong SPA/browser. Các class trong bài thuộc **reactive stack**, không phải `HttpSecurity`, `OncePerRequestFilter` của Servlet.

## 1. Mô hình xử lý một phương thức xác thực mới

Giả sử service chỉ muốn cho internal batch worker gọi:

~~~http
GET /internal/report HTTP/1.1
Host: service.example.test
X-Internal-Key: <high-entropy-secret>
~~~

Luồng đề xuất:

~~~text
HTTP /internal/report
        |
        v
SecurityWebFilterChain
        |
        v
AuthenticationWebFilter
        |
        +-- setRequiresAuthenticationMatcher("/internal/**")
        |       request khác path -> tiếp tục, không parse key
        |
        v
ServerAuthenticationConverter
        |
        +-- không có X-Internal-Key -> Mono.empty()
        +-- malformed/multiple headers -> Mono.error(BadCredentialsException)
        +-- có đúng format -> InternalKeyAuthenticationToken unauthenticated
        |
        v
ReactiveAuthenticationManager
        |
        +-- xác minh credential với nguồn tin cậy phía server
        +-- sai -> Mono.error(BadCredentialsException)
        +-- đúng -> Authentication authenticated:
        |           principal="batch-reader"
        |           authorities=[SCOPE_internal.read]
        |           credentials=null
        |
        v
ReactiveSecurityContextHolder (trong subscription)
        |
        v
authorizeExchange: hasAuthority("SCOPE_internal.read")
        |
        +-- không đủ quyền -> 403
        +-- đủ quyền -> Controller trả JSON
~~~

Từng thành phần có trách nhiệm riêng:

| Thành phần | Đầu vào | Đầu ra | Không nên làm |
|---|---|---|---|
| `ServerAuthenticationConverter` | HTTP request/`ServerWebExchange` | Một Authentication **chưa** xác thực, hoặc empty/error | Tự tin key là đúng; tự cấp role admin |
| `ReactiveAuthenticationManager` | Authentication candidate | Authentication đã verify hoặc error | Tin X-Role/X-User do caller gửi |
| `AuthenticationWebFilter` | Request + converter + manager | SecurityContext cho downstream, success/failure | Tự viết HTTP body blocking hoặc đăng ký hai lần |
| `SecurityWebFilterChain` | HTTP request + Authentication | Quyết định endpoint được truy cập | `permitAll` cho internal endpoint |
| Business/service authorization | Principal + policy + resource data | Cho phép thao tác thực tế | Bỏ tenant/owner/ACL checks |

**Authentication ≠ Authorization:** Key hợp lệ xác minh ai đang gọi; key đó có thể **không có** quyền admin. Một route admin vẫn phải 403 dù Authentication thành công.

## 2. Thiết kế Authentication token có hai trạng thái

Interface `Authentication` trong Spring Security biểu diễn cả yêu cầu xác thực và kết quả xác thực. Các method:

| Method | Tác dụng |
|---|---|
| `getPrincipal()` | Caller identity; chỉ đáng tin sau validation |
| `getCredentials()` | Bằng chứng được đưa vào manager |
| `getAuthorities()` | Quyền đã được cấp bởi authentication/authorization policy |
| `isAuthenticated()` | Trạng thái xác thực do Spring Security nhận biết |
| `setAuthenticated(boolean)` | Mutation trạng thái; cần chặn caller tự bật true |
| `eraseCredentials()` | Loại bỏ sensitive credentials trong object sau sử dụng |
| `getDetails()` | Context khác, không tự được tin để cấp quyền |
| `getName()` | Tên principal cho logging và auditing |

`AbstractAuthenticationToken` giúp triển khai phần authorities, authenticated flag và xóa credentials, nên ta kế thừa nó thay vì tự triển khai đầy đủ interface.

### 2.1. Trước khi xác thực

~~~text
InternalKeyAuthenticationToken.unauthenticated(rawKey)

isAuthenticated = false
principal       = null
credentials     = rawKey
authorities     = []
~~~

Điều này chỉ chứng minh **client đã gửi một credential candidate**, không chứng minh key có hiệu lực.

### 2.2. Sau khi manager xác thực thành công

~~~text
InternalKeyAuthenticationToken.authenticated(
    "batch-reader", [SCOPE_internal.read])

isAuthenticated = true
principal       = "batch-reader" (server cấp)
credentials     = null
authorities     = [SCOPE_internal.read]
~~~

Principal và authorities **không lấy từ HTTP header do caller khai**. Nếu hệ thống dùng nhiều keys, manager cần tra keyId trong trusted store và lấy service identity/tenant/permission tương ứng.

### 2.3. Chặn việc tự nâng quyền

Sai:

~~~java
// PHẢN VÍ DỤ - caller có thể được tin sai trước khi verify:
InternalKeyAuthenticationToken token = ...;
token.setAuthenticated(true);
return Mono.just(token);
~~~

Một implementation an toàn nên:

1. Có factory `unauthenticated(rawKey)`, trạng thái false, không authorities.
2. Có factory tạo authenticated token chỉ được **trusted manager** gọi sau khi verify. Nếu production có nhiều modules, cân nhắc hạn chế factory access/package.
3. Override `setAuthenticated(true)` để ném `IllegalArgumentException`, chỉ private constructor tin cậy dùng `super.setAuthenticated(true)` khi tạo **object mới**.
4. Sau attempt, xóa raw credential ở request token bằng `eraseCredentials()`. Authenticated object **không giữ** raw credential.
5. Không override `toString()` để in key, hoặc chuyển key sang `getDetails()` chỉ nhằm “debug”.

Không phải mọi protocol đều cần class riêng. Spring đã có `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken`, `BearerTokenAuthenticationToken`; hãy dùng built-in khi đúng protocol để hưởng các validator/exception semantics có sẵn.

## 3. ServerAuthenticationConverter: kết quả empty/just/error

Interface Spring Security reactive:

~~~java
@FunctionalInterface
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
~~~

Đây là **chữ ký rút gọn**, không phải code cần tự khai báo lại interface. Converter đọc các phần của `ServerWebExchange` (HTTP headers, parameters, path, body theo protocol), rồi biểu diễn credential thành một Authentication candidate.

| Return | Ý nghĩa | Ví dụ |
|---|---|---|
| `Mono.empty()` | **Không có authentication attempt** để filter xử lý. | Không có `X-Internal-Key` |
| `Mono.just(unauthenticatedToken)` | Có credential đúng cấu trúc; cần manager verify. | Một key chứa ký tự hợp lệ |
| `Mono.error(BadCredentialsException)` | Credential/request sai format hay bị trùng. | Hai headers X-Internal-Key, value sai pattern |
| `Mono.error(AuthenticationServiceException)` | Hạ tầng authentication gặp lỗi thực sự (tùy policy). | Secret database unavailable |
| `Mono.just(authenticatedToken)` | **Không phù hợp trong converter này.** | Tạo quyền mà chưa verify |

### 3.1. Thiếu header không bằng header sai

Request không có key:

~~~http
GET /internal/report HTTP/1.1
Host: localhost:8080
~~~

Converter trả `Mono.empty()`; `AuthenticationWebFilter` tiếp tục chain. Authorization rule của `/internal/report` vẫn yêu cầu authority nên một anonymous caller bị **401** theo entry point.

Nếu request có:

~~~http
X-Internal-Key: wrong
~~~

Converter thấy một authentication attempt nhưng format bị từ chối → `Mono.error(BadCredentialsException)` → failure handler trả 401. Nếu format đúng nhưng secret sai, manager cũng phát BadCredentialsException.

Không nên trả empty cho key sai để các filter khác lỡ coi request là “không thử xác thực” rồi fallback sang cơ chế yếu hơn khi policy không cho phép.

### 3.2. Header trùng hoặc bị proxy nối lại

Các biến thể:

~~~http
X-Internal-Key: first-key-value
X-Internal-Key: second-key-value
~~~

~~~http
X-Internal-Key: first-key-value,second-key-value
~~~

Nếu protocol chỉ cho **một** key, đừng dùng `getFirst()` và bỏ qua phần còn lại; proxy/ingress có thể ưu tiên giá trị khác, dẫn đến header parsing ambiguity. Demo từ chối khi size khác 1, hoặc value không theo regex base64url-like `[A-Za-z0-9_-]{16,128}`.

Regex/độ dài ở đây chỉ là **format demo**, không phải tiêu chuẩn chung. Với production nên tạo key bằng CSPRNG, ví dụ **32 bytes random** được base64url không padding thành 43 ký tự, có key ID/rotation/expiry rõ ràng.

### 3.3. Không đưa key vào URL hoặc response

Sai:

~~~http
GET /internal/report?api_key=top-secret
~~~

URL thường nằm trong history, proxy logs, analytics và traces. Header qua TLS phù hợp hơn, nhưng **header cũng phải scrub** khỏi monitoring/logging. Không in giá trị key vào `BadCredentialsException("Bad key: " + raw)` hoặc JSON lỗi.

## 4. ReactiveAuthenticationManager mới được xác minh key

Interface:

~~~java
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Đây là chữ ký rút gọn để giải thích. Manager **nhận token chưa authenticated** và trả Authentication đã xác minh hoặc lỗi.

Quy tắc demo:

- Chỉ nhận `InternalKeyAuthenticationToken` chưa authenticated; nếu token loại khác, trả `Mono.empty()` để manager composition có thể quyết định.
- Không tin dữ liệu role/tenant do caller gửi.
- Xác minh raw credential với digest đã tạo từ key cấu hình trusted.
- Khi sai, trả `Mono.error(BadCredentialsException)`, không tạo Authentication authenticated.
- Khi đúng, tạo **object mới** với service principal `batch-reader` và một authority `SCOPE_internal.read`.
- Xóa raw credential khỏi request token ngay sau khi lấy giá trị cần kiểm tra.

### 4.1. Constant-time comparison không phải cả mô hình bảo mật

Demo dùng:

~~~java
byte[] expected = sha256(secretFromTrustedConfig);
byte[] presented = sha256(secretFromHeader);

boolean valid = MessageDigest.isEqual(expected, presented);
~~~

Đây là **mảnh minh họa** (cần method `sha256` ở ứng dụng hoàn chỉnh). So sánh hai digests có độ dài cố định giảm vấn đề `String.equals` ngắt sớm theo ký tự. Nhưng **không thay thế**:

- Key có đủ entropy, rotation/revocation, TTL, hạn mức requests.
- Secret storage (KMS/secret manager, hashed key database hoặc HMAC lookup).
- TLS/mTLS, network ACLs, chống key replay theo threat model.
- Giới hạn input size, rate limiting, theo dõi các attempts.
- Cấp principal/authorities theo keyId/tenant từ trusted database.
- Cơ chế fail closed khi store lỗi; không coi exception là credential hợp lệ.

Nếu secret format ngắn/dễ đoán, SHA-256 so sánh đúng vẫn không ngăn brute force. Static key không có proof-of-possession, nên ai có key có thể replay đến khi revoked.

### 4.2. Mono.error khác với Mono.empty trong manager

Với manager hỗ trợ nhiều credential types:

~~~java
if (!(authentication instanceof InternalKeyAuthenticationToken)) {
    return Mono.empty(); // không xử lý loại này
}
~~~

Nhưng khi token **đúng loại và key sai**, phải là:

~~~java
return Mono.error(
    new BadCredentialsException("Invalid credential"));
~~~

Không dùng empty cho invalid key nếu policy đòi fail-closed. Khi downstream 500/timeout từ secret store, nên xử lý thành service-authentication failure phù hợp, không đánh dấu authenticated hoặc fallback sang một default key.

## 5. AuthenticationWebFilter và SecurityWebFilterChain

Javadoc `AuthenticationWebFilter` mô tả thứ tự:

1. Kiểm tra request có khớp `setRequiresAuthenticationMatcher(...)` không.
2. Chạy `ServerAuthenticationConverter.convert(exchange)`.
3. Nếu converter empty, không authenticate, cho filter chain đi tiếp.
4. Nếu có candidate, gọi `ReactiveAuthenticationManager`.
5. Nếu thành công, success handler tiếp tục chain cùng SecurityContext trong **Reactor Context**; nếu sai, failure handler xử lý.
6. Authorization filter sau đó kiểm tra authorities/endpoint access.

Một cấu hình:

~~~java
AuthenticationWebFilter filter =
    new AuthenticationWebFilter(manager);

filter.setServerAuthenticationConverter(
    new InternalKeyAuthenticationConverter());

filter.setRequiresAuthenticationMatcher(
    new PathPatternParserServerWebExchangeMatcher(
        "/internal/**"));

filter.setSecurityContextRepository(
    NoOpServerSecurityContextRepository.getInstance());

HttpStatusServerEntryPoint unauthorized =
    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

filter.setAuthenticationFailureHandler(
    new ServerAuthenticationEntryPointFailureHandler(
        unauthorized));

http.addFilterAt(
    filter, SecurityWebFiltersOrder.AUTHENTICATION);
~~~

Đây là mảnh cấu hình, cần đặt trong `@Bean SecurityWebFilterChain`. **Không** đăng ký filter vừa như một `@Bean WebFilter` global vừa thêm qua `addFilterAt`: nó có thể chạy hai lần.

### 5.1. Matcher không phải authorization rule

- `setRequiresAuthenticationMatcher("/internal/**")` chỉ kiểm soát **thử xác thực** ở đâu.
- `authorizeExchange(...hasAuthority(...))` kiểm soát **quyền endpoint**.
- Nếu bạn dùng `anyExchange().permitAll()` cho private endpoint, chỉ có custom filter không bảo đảm quyền truy cập.
- Nếu request thiếu key, filter trả empty nhưng authorization private sẽ chặn.
- Nếu route public ở ngoài matcher, filter bỏ qua key ngay cả khi request có header sai; đây là một behavior cố ý cần test.

### 5.2. NoOp security context là stateless, không phải “không có principal”

`NoOpServerSecurityContextRepository.getInstance()` không lưu Authentication vào session cho request sau. Nhưng request hiện tại vẫn có authenticated principal trong Reactor Context. Vì vậy:

~~~text
GET /internal/report + valid key
    → manager verify
    → current request được authenticated
    → controller có principal
    → request khác không có key vẫn 401
~~~

Đối với form login/session cookies, NoOp repository thường **không phù hợp** vì login session cần persistence. Bài demo chỉ áp dụng header-only service authentication.

### 5.3. Lý do set failure handler và authentication entry point riêng

`AuthenticationWebFilter` mặc định có failure behavior phù hợp HTTP Basic. Với API key header-only, bạn có thể muốn trả **401** không kèm Basic challenge hoặc redirect form.

- Có header nhưng invalid → `ServerAuthenticationFailureHandler` của filter.
- Không có header → converter empty; authorization cần xác thực → `ServerHttpSecurity.exceptionHandling(...authenticationEntryPoint(...))`.
- Key đã đúng nhưng thiếu role trên `/internal/admin` → authorization denied (403), không phải lỗi credential.

Trong demo cả hai đường authentication failure dùng `HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)`. Khi làm JSON error body riêng, không echo key/hash/stack trace.

### 5.4. Không block trên Reactor Netty event loop

Không làm:

~~~java
// PHẢN VÍ DỤ:
public Mono<Authentication> authenticate(Authentication candidate) {
    boolean valid = blockingDatabase.check(candidate).block();
    return Mono.just(...);
}
~~~

Manager nên trả reactive pipeline từ R2DBC/WebClient/secret store API. Khi bắt buộc dùng legacy blocking client, cần scheduler phù hợp và backpressure/rate limits; không dùng `subscribe()` detached khiến filter đi tiếp trước khi verify.

## 6. Ví dụ Java 17 hoàn chỉnh: header-only internal authentication

**Bài lab:** `GET /internal/report` chỉ chấp nhận một key đúng; `GET /internal/admin` yêu cầu quyền không được cấp; `GET /public/ping` public. Ví dụ dùng **Spring Boot 3.5.16** (Spring Security reactive 6.5.x theo BOM) và Java 17.

### 6.1. Cấu trúc

~~~text
reactive-custom-auth/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/CustomAuthApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/example/CustomAuthTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-custom-auth'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cần JDK 17+ và Gradle hoặc Gradle Wrapper tương thích. Demo **không** dùng `spring-boot-starter-web` Servlet, không có blocking web server.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

app:
  security:
    internal-api-key: ${INTERNAL_API_KEY}
~~~

Cú pháp placeholder trong file YAML thực là `${INTERNAL_API_KEY}`, **không** có dấu backslash trước đô-la; bản Markdown giữ cách trình bày nguyên liệu soạn. Không có env variable thì app phải fail startup thay vì fallback một key rỗng.

Với local demo, dùng một **key thử được công khai trong bài này**, không dùng trên hệ thống thật:

~~~bash
# Linux/macOS:
export INTERNAL_API_KEY='local-demo-key-only-never-use-in-prod-001'
gradle bootRun
~~~

PowerShell:

~~~powershell
$env:INTERNAL_API_KEY = 'local-demo-key-only-never-use-in-prod-001'
gradle bootRun
~~~

Production dùng key ngẫu nhiên đủ mạnh do CSPRNG sinh và secret manager quản lý, không commit key vào source hoặc chia sẻ trong terminal history.

### 6.2. Ứng dụng đầy đủ

Tệp `src/main/java/example/CustomAuthApplication.java`:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class CustomAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomAuthApplication.class, args);
    }

    public static final class InternalKeyAuthenticationToken
        extends AbstractAuthenticationToken {

        private final String principal;
        private String credentials;

        private InternalKeyAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean trusted) {

            super(authorities);
            this.principal = principal;
            this.credentials = credentials;
            super.setAuthenticated(trusted);
        }

        public static InternalKeyAuthenticationToken unauthenticated(
            String rawKey) {

            return new InternalKeyAuthenticationToken(
                null, rawKey, List.of(), false);
        }

        public static InternalKeyAuthenticationToken authenticated(
            String serviceId,
            Collection<? extends GrantedAuthority> authorities) {

            return new InternalKeyAuthenticationToken(
                serviceId, null, authorities, true);
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
        public void eraseCredentials() {
            super.eraseCredentials();
            credentials = null;
        }

        @Override
        public void setAuthenticated(boolean trusted) {
            if (trusted) {
                throw new IllegalArgumentException(
                    "Use the trusted authenticated factory");
            }
            super.setAuthenticated(false);
        }
    }

    public static final class InternalKeyAuthenticationConverter
        implements ServerAuthenticationConverter {

        @Override
        public Mono<Authentication> convert(
            ServerWebExchange exchange) {

            List<String> headers = exchange.getRequest()
                .getHeaders().getOrEmpty("X-Internal-Key");

            if (headers.isEmpty()) {
                return Mono.empty();
            }

            if (headers.size() != 1) {
                return Mono.error(new BadCredentialsException(
                    "Invalid credential"));
            }

            String raw = headers.get(0);
            if (raw == null
                || !raw.matches("[A-Za-z0-9_-]{16,128}")) {
                return Mono.error(new BadCredentialsException(
                    "Invalid credential"));
            }

            return Mono.just(
                InternalKeyAuthenticationToken.unauthenticated(raw));
        }
    }

    public static final class InternalKeyAuthenticationManager
        implements ReactiveAuthenticationManager {

        private final byte[] expectedDigest;

        public InternalKeyAuthenticationManager(String expectedKey) {
            if (expectedKey == null
                || !expectedKey.matches("[A-Za-z0-9_-]{16,128}")) {
                throw new IllegalArgumentException(
                    "Missing or malformed server secret");
            }
            this.expectedDigest = sha256(expectedKey);
        }

        private static byte[] sha256(String value) {
            try {
                return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            } catch (NoSuchAlgorithmException error) {
                throw new IllegalStateException(
                    "SHA-256 is unavailable", error);
            }
        }

        @Override
        public Mono<Authentication> authenticate(
            Authentication authentication) {

            if (!(authentication instanceof
                    InternalKeyAuthenticationToken request)
                || request.isAuthenticated()) {
                return Mono.empty();
            }

            String raw = (String) request.getCredentials();
            request.eraseCredentials();

            boolean valid = raw != null
                && MessageDigest.isEqual(
                    expectedDigest, sha256(raw));

            if (!valid) {
                return Mono.error(new BadCredentialsException(
                    "Invalid credential"));
            }

            return Mono.just(
                InternalKeyAuthenticationToken.authenticated(
                    "batch-reader",
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_internal.read"))));
        }
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        @Value("${app.security.internal-api-key}")
        String key) {

        var manager =
            new InternalKeyAuthenticationManager(key);

        var filter = new AuthenticationWebFilter(manager);
        filter.setServerAuthenticationConverter(
            new InternalKeyAuthenticationConverter());

        filter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/internal/**"));

        filter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());

        var unauthorized =
            new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

        filter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                unauthorized));

        return http
            // Only correct for this header-only, cookie-free API.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(unauthorized))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/internal/report")
                    .hasAuthority("SCOPE_internal.read")
                .pathMatchers(HttpMethod.GET, "/internal/admin")
                    .hasAuthority("ROLE_INTERNAL_ADMIN")
                .anyExchange().denyAll())
            .addFilterAt(
                filter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }

    @RestController
    static class Endpoints {

        @GetMapping("/public/ping")
        Mono<Map<String, String>> ping() {
            return Mono.just(Map.of("status", "ok"));
        }

        @GetMapping("/internal/report")
        Mono<Map<String, String>> report(
            Mono<Principal> principal) {

            return principal.map(p -> Map.of(
                "service", p.getName(),
                "result", "report-ready"));
        }

        @GetMapping("/internal/admin")
        Mono<Map<String, String>> admin() {
            return Mono.just(Map.of("result", "admin-only"));
        }
    }
}
~~~

### 6.3. Phân tích code theo từng lớp

**Token** — `InternalKeyAuthenticationToken.unauthenticated(raw)` giữ raw key, principal null, state false, authorities empty. Khi manager verify xong, factory authenticated tạo object **mới**, principal server `batch-reader` và duy nhất quyền read. `setAuthenticated(true)` từ caller bị chặn; `eraseCredentials()` xóa key.

**Converter** — đọc header một lần, thiếu header → empty; duplicate hoặc sai format → error; hợp format → token false, **không tự cho quyền**. Regex `[A-Za-z0-9_-]{16,128}` chỉ dành cho lab, không chứng minh key đủ entropy.

**Manager** — prehash trusted key ở constructor; khi có candidate, xóa raw credential sau khi lấy bản local, so digest cố định; sai → `BadCredentialsException`; đúng → authenticated token có `SCOPE_internal.read`. Với production nhiều keys, lookup keyId từ trusted store và cấp quyền theo metadata thực.

**Filter** — matcher chỉ `/internal/**`; failure handler gửi 401, không dùng Basic form challenge. `NoOpServerSecurityContextRepository` giữ stateless qua requests; within-request principal vẫn đến controller qua Reactor Context.

**Chain** — public `/public/ping`, private `/internal/report` scope read, `/internal/admin` cần role không được cấp bởi key demo, còn lại deny. `SecurityWebFiltersOrder.AUTHENTICATION` bảo đảm filter chạy trước authorization. CSRF disable chỉ đúng vì demo **không** dùng browser session cookies; app có cookie auth phải đánh giá CSRF lại.

**Controller** — dùng `Mono<Principal>` reactive, không tự đọc key. Response chỉ chứa tên service và report placeholder; không echo credential.

### 6.4. curl thử các nhánh

Khi backend chạy:

~~~bash
# Public:
curl -i http://localhost:8080/public/ping

# Missing credential:
curl -i http://localhost:8080/internal/report

# Wrong key:
curl -i \
  -H 'X-Internal-Key: wrong-local-demo-key-123456789' \
  http://localhost:8080/internal/report

# Correct local-demo credential:
curl -i \
  -H 'X-Internal-Key: local-demo-key-only-never-use-in-prod-001' \
  http://localhost:8080/internal/report

# Correct key, insufficient admin authority:
curl -i \
  -H 'X-Internal-Key: local-demo-key-only-never-use-in-prod-001' \
  http://localhost:8080/internal/admin
~~~

**Kết quả HTTP kỳ vọng** (field order/headers/status line tùy runtime):

~~~text
GET /public/ping             -> 200 {"status":"ok"}
GET /internal/report no key  -> 401
GET /internal/report bad key -> 401
GET /internal/report good    -> 200 {"service":"batch-reader","result":"report-ready"}
GET /internal/admin good     -> 403
~~~

Trên PowerShell, có thể dùng `curl.exe`. **Không** đưa key production vào command line/shell history hoặc log. Những chuỗi secret ở đây chỉ là public demo values. Mã Java được review về cấu trúc nhưng **chưa thực thi build trong lúc soạn bài**, nên cần chạy trên JDK/Gradle tương thích để xác nhận.

## 7. Kiểm thử: real HTTP filter chain và unit tests

Dùng hai tầng test:

1. `WebTestClient` gửi HTTP header thật → đi qua converter, manager, filter và authorization trong Spring WebFlux.
2. `StepVerifier` kiểm tra trực tiếp token state, converter empty/just/error, manager success/failure và credential erasure.

**Không chỉ dùng `mockAuthentication()`** để tuyên bố converter hoạt động: test mutator tạo sẵn Authentication trong SecurityContext có thể **bypass** custom authentication filter. Các phép thử HTTP ở đây không mock Authentication.

Tệp `src/test/java/example/CustomAuthTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "app.security.internal-api-key=local-demo-key-only-never-use-in-prod-001")
@AutoConfigureWebTestClient
class CustomAuthTest {

    private static final String KEY =
        "local-demo-key-only-never-use-in-prod-001";

    @Autowired
    WebTestClient client;

    private CustomAuthApplication.InternalKeyAuthenticationConverter
        converter() {
        return new CustomAuthApplication
            .InternalKeyAuthenticationConverter();
    }

    @Test
    void publicRouteNeedsNoKey() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void missingKeyReturns401() {
        client.get().uri("/internal/report")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongKeyReturns401() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", "wrong-key-for-this-demo-12345")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedHeaderReturns401() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", "short")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void duplicateHeadersReturn401() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", KEY, "second-key-value")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void commaJoinedHeadersReturn401() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", KEY + ",second-key-value")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void correctKeyCreatesTrustedIdentity() {
        client.get().uri("/internal/report")
            .header("X-Internal-Key", KEY)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.service").isEqualTo("batch-reader")
            .jsonPath("$.result").isEqualTo("report-ready");
    }

    @Test
    void correctKeyDoesNotCreateAdminAuthority() {
        client.get().uri("/internal/admin")
            .header("X-Internal-Key", KEY)
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void publicMatcherDoesNotValidateKey() {
        client.get().uri("/public/ping")
            .header("X-Internal-Key", "not-a-valid-value")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void converterReturnsEmptyWhenNoHeader() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/internal/report").build());

        StepVerifier.create(converter().convert(exchange))
            .verifyComplete();
    }

    @Test
    void converterCreatesOnlyUnauthenticatedRequestToken() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/internal/report")
                .header("X-Internal-Key", KEY).build());

        StepVerifier.create(converter().convert(exchange))
            .assertNext(authentication -> {
                assertInstanceOf(
                    CustomAuthApplication
                        .InternalKeyAuthenticationToken.class,
                    authentication);
                assertFalse(authentication.isAuthenticated());
                assertTrue(authentication.getAuthorities().isEmpty());
                assertEquals(KEY, authentication.getCredentials());
                assertNull(authentication.getPrincipal());
            })
            .verifyComplete();
    }

    @Test
    void converterRejectsDuplicateHeaderDirectly() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/internal/report")
                .header("X-Internal-Key", KEY, "second-key-value")
                .build());

        StepVerifier.create(converter().convert(exchange))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unauthenticatedTokenCannotBeUpgradedBySetter() {
        var token = CustomAuthApplication
            .InternalKeyAuthenticationToken.unauthenticated(KEY);

        assertFalse(token.isAuthenticated());

        assertThrows(IllegalArgumentException.class,
            () -> token.setAuthenticated(true));

        assertFalse(token.isAuthenticated());
    }

    @Test
    void managerGrantsReadAuthorityAndErasesRawKey() {
        var request = CustomAuthApplication
            .InternalKeyAuthenticationToken.unauthenticated(KEY);

        var manager = new CustomAuthApplication
            .InternalKeyAuthenticationManager(KEY);

        StepVerifier.create(manager.authenticate(request))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("batch-reader", auth.getName());
                assertNull(auth.getCredentials());
                assertNull(request.getCredentials());
                assertTrue(auth.getAuthorities().contains(
                    new SimpleGrantedAuthority("SCOPE_internal.read")));
                assertFalse(auth.getAuthorities().contains(
                    new SimpleGrantedAuthority("ROLE_INTERNAL_ADMIN")));
            })
            .verifyComplete();
    }

    @Test
    void managerRejectsBadKeyAndErasesRawCredential() {
        var request = CustomAuthApplication
            .InternalKeyAuthenticationToken.unauthenticated(
                "wrong-key-for-this-demo-12345");

        var manager = new CustomAuthApplication
            .InternalKeyAuthenticationManager(KEY);

        StepVerifier.create(manager.authenticate(request))
            .expectError(BadCredentialsException.class)
            .verify();

        assertNull(request.getCredentials());
        assertFalse(request.isAuthenticated());
    }

    @Test
    void managerReturnsEmptyForUnsupportedTokenType() {
        Authentication other =
            new org.springframework.security.authentication
                .UsernamePasswordAuthenticationToken(
                    "someone", "password");

        var manager = new CustomAuthApplication
            .InternalKeyAuthenticationManager(KEY);

        StepVerifier.create(manager.authenticate(other))
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Dùng `./gradlew test` hoặc `gradlew.bat test` khi có wrapper. **Kỳ vọng 16 tests pass**, nhưng phải chạy thực tế với toolchain trên máy để xác nhận. Tests không cần IdP/database. Test HTTP dùng real WebFlux chain; tests riêng converter/manager kiểm tra lifecycle của token.

### 7.1. Giới hạn cần biết

- `@SpringBootTest` với key public demo không test key entropy/secret manager.
- Test chứng minh HTTP status 200/401/403 theo cấu hình, chưa chứng minh TLS hoặc API gateway parse headers giống app.
- Test trực tiếp manager không kiểm tra timing constant-time trên thực tế. So digest là một bước, không thay threat modeling.
- Test không chứng minh key rotation/revocation, expiry, rate limiting, per-tenant permissions hoặc secret store availability.
- Khi nâng cấp Spring Security, phải chạy regression suite cho filter order/matcher/success/failure handlers.
- Test `mockAuthentication()` hữu ích để test authorization độc lập, nhưng **không** chứng minh Header → Converter → Manager hoạt động.

### 7.2. Những negative tests cần mở rộng

- Key revoked, expired, keyId không tồn tại, service bị disable → 401.
- Key hợp lệ của service A không có quyền tenant B → 403/404 theo policy.
- Header chứa newline/control chars, whitespace, Unicode không mong muốn, quá 128 ký tự → từ chối.
- Gateway nối duplicate headers thành một value có dấu phẩy → từ chối.
- Internal API vô tình nhận Bearer JWT và API key cùng lúc → policy rõ ràng.
- Thiếu key ở mỗi request sau khi request trước đã thành công → 401 (stateless).
- Monitoring/logging không ghi credential; errors body không echo raw value.
- Khi nhiều keys hoạt động song song, manager không dùng mutable global principal/authorities giữa calls.

## 8. Mở rộng sang cơ chế xác thực phức tạp

### 8.1. Nhiều SecurityWebFilterChain

Một app có thể dùng JWT cho API người dùng và custom API key cho services nội bộ:

~~~text
/api/**             -> oauth2ResourceServer.jwt()
/internal/**        -> custom AuthenticationWebFilter
/actuator/health    -> policy health riêng
other routes        -> fallback deny
~~~

Ưu tiên khai báo các `SecurityWebFilterChain` với `securityMatcher(...)` và `@Order` cụ thể. Mỗi request chỉ dùng **chain đầu tiên match**. Với `/internal/**`, chỉ gắn custom filter trong internal chain; JWT chain dùng built-in resource server. Không dựa vào key để tự vượt quyền của JWT routes.

Đoạn cấu trúc sau **không phải ứng dụng hoàn chỉnh**:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain internal(
    ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/internal/**"))
        .addFilterAt(keyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
        .authorizeExchange(ex -> ex
            .anyExchange().hasAuthority("SCOPE_internal.read"))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .oauth2ResourceServer(oauth ->
            oauth.jwt(jwt -> {
                // trusted issuer/JWKS config here
            }))
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated())
        .build();
}
~~~

Code trên là **mảnh minh họa** với biến `keyFilter` đã cấu hình sẵn; không copy vào demo mục 6. Production phải có fallback chain cho những URL không match; bảo vệ actuator, quản lý role, CSRF và exception handlers từng chain, cũng như bảo đảm filter không chạy hai lần.

### 8.2. ReactiveAuthenticationManagerResolver

Khi cần manager khác nhau theo tổ chức/issuer/tenant, `AuthenticationWebFilter` cũng có constructor nhận `ReactiveAuthenticationManagerResolver<ServerWebExchange>`. Tuy nhiên **không chọn một manager cấp quyền mạnh chỉ dựa trên header `X-Tenant` chưa được xác minh**. Nếu dùng JWT đa issuer, framework có resolver chuyên dụng đáng tin hơn là tự parse token.

### 8.3. DelegatingServerAuthenticationConverter và fallback

Spring Security có `DelegatingServerAuthenticationConverter` cho nhiều converter. Khi có nhiều protocols:

- Converter A `Mono.empty()`: không có credential của A; B có thể thử nếu policy cho phép.
- Converter A `Mono.error(AuthenticationException)`: credential A đã gửi **nhưng sai**; tránh fallback sang cơ chế yếu hơn vô tình.
- Hai credentials cùng hiện diện: có policy ưu tiên hoặc reject, đừng ngẫu nhiên chấp nhận cái đầu.
- Manager chỉ xử lý token types được thiết kế; không nhận mọi Authentication rồi đặt true.
- Mọi successful authenticated token phải gắn đúng principal/authorities.

### 8.4. Khi nào dùng OAuth2/JWT/mTLS thay custom API key?

| Mechanism | Điểm mạnh | Giới hạn/đánh giá |
|---|---|---|
| Header API key | Đơn giản cho nội bộ, dễ prototyping | Static bearer proof, khó granularity/rotation nếu thiết kế sơ sài |
| OAuth2 client_credentials JWT | Scopes/audience, TTL, token issuance và standard framework | Phải quản lý Authorization Server, keys, policies |
| OAuth2 opaque introspection | Dễ revoke theo server-side state | Cần network/introspection availability |
| mTLS client certificate | Possession của private key và identity transport | Cần PKI/cert lifecycle, trusted proxies |
| HMAC signed request với timestamp/nonce | Ràng buộc request, replay controls | Canonicalization, clock sync, nonce cache phức tạp |
| Session/form login | Phù hợp web người dùng | Cookies/CSRF/session lifecycle, không như M2M header-only |

Đừng tự viết JWT cryptographic validation trong converter khi `oauth2ResourceServer(jwt)` đã có; custom Security nên tập trung vào domain-specific case thật sự cần.

## 9. Những lỗi thường gặp

**1. Converter tạo Authentication authenticated:** bypass manager; chỉ tạo unauthenticated candidate.

**2. Tin `X-User` hay `X-Role` từ client:** phải dùng trusted mapping bên server, không nâng quyền theo header.

**3. Dùng `Mono.empty()` cho key sai:** có thể tạo fallback không chủ đích; invalid credential nên fail.

**4. Dùng `Mono.error(...)` cho mọi request không có key:** public routes có thể bị 401 sai nếu matcher rộng; phân biệt missing và malformed.

**5. Token request có sẵn authorities admin:** phải empty trước verify; cấp quyền trong manager.

**6. Không chặn `setAuthenticated(true)`:** code khác có thể tăng quyền ngoài luồng.

**7. Đăng ký filter hai lần:** vừa global WebFilter bean vừa `addFilterAt` làm double processing.

**8. Đặt filter sau authorization:** security context chưa có khi rule chạy; dùng AUTHENTICATION order.

**9. Không cấu hình matcher:** parser được gọi trên mọi endpoint, có thể làm public routes lỗi.

**10. Dùng `anyExchange().permitAll()` trên internal routes:** dù có filter, anonymous vẫn có thể vào.

**11. Dùng Servlet `HttpSecurity` hoặc `OncePerRequestFilter` trên WebFlux:** cần reactive APIs.

**12. Dùng `block()` hoặc `subscribe()` trong manager:** có thể deadlock/block event-loop hoặc mất Reactor Context.

**13. Không xóa key sau verify:** raw credential có thể được giữ trong object/traces; erase sớm.

**14. Log raw key/error includes submitted key:** data leak; dùng generic errors và keyId audit.

**15. Hardcode secret trong source/application.yml:** dùng secret manager/environment, rotation.

**16. Dùng key ngắn/dễ đoán:** SHA-256 digest không tăng entropy; dùng CSPRNG.

**17. Dùng `String.equals` để so secrets:** có timing issues; dùng fixed-length digest + MessageDigest.isEqual hoặc primitive phù hợp.

**18. Tin digest check chống replay:** static API key vẫn có thể bị replay; TLS/PoP/revocation cần thiết.

**19. Đặt key vào query string:** nguy cơ leak qua URL/history/Referer/logs.

**20. Bỏ qua duplicate headers:** gateway/app có thể parse khác, tạo ambiguity.

**21. Tắt CSRF trong app có browser cookies:** chỉ cân nhắc disable cho header-only API không có automatic credentials.

**22. NoOp repository trên app cần persistent login session:** request sau không có Authentication nếu không gửi lại credential.

**23. Test chỉ bằng `mockAuthentication()`:** bypass converter/manager; test real header → filter pipeline.

**24. Chỉ test happy-path 200:** cần 401/403, missing/duplicate/malformed, nonmatching path, secret revoke.

**25. Trả 401 khi thiếu admin authority dù key đúng:** Authentication đã qua, thiếu quyền nên 403.

**26. Static key trong SPA/browser:** không thể bảo mật source bundle; dùng OIDC/PKCE/BFF.

**27. Cấp mọi permissions cho mỗi key:** nên key-scoped principal, tenant, granted authorities và least privilege.

**28. Không có key lifecycle:** production cần issue, rotate, expire, revoke, audit, monitoring.

## 10. Checklist review production

1. Có lý do kỹ thuật rõ ràng để tạo custom mechanism thay vì built-in Basic/JWT/OAuth2/mTLS?
2. Converter chỉ parse HTTP, không tự verify hoặc set authenticated true?
3. Missing → empty, malformed/duplicate → AuthenticationException, valid format → unauthenticated token?
4. Key format/rate/size được kiểm soát, không chấp nhận nhiều headers hoặc control chars?
5. Token unauthenticated có authorities rỗng và credentials candidate?
6. `setAuthenticated(true)` từ caller bị chặn; only trusted manager grants identity?
7. Manager chỉ nhận token type của mình và có proper error semantics?
8. Secret đủ entropy, được cấp qua secret manager, có rotation/revocation/expiry?
9. Credential không nằm ở query string, log, error, metrics, traces?
10. Comparison/trusted key lookup không tạo timing leak không cần thiết?
11. Filter được gắn một lần vào đúng SecurityWebFilterChain?
12. Matcher giới hạn endpoint nào dùng mechanism này?
13. Filter ở `SecurityWebFiltersOrder.AUTHENTICATION` và trước authorization?
14. Private paths có rule authority/role rõ, fallback deny?
15. Thiếu/invalid credential trả 401, thiếu quyền trả 403?
16. Success request có principal trong Reactor Context, không persist session nếu stateless?
17. CSRF phù hợp cookie/session model, không disable vô điều kiện?
18. Không xử lý blocking I/O trên Netty event loop; không detached subscribe?
19. HTTPS/mTLS/network ACLs, trusted gateway header handling, reverse proxy policies đúng?
20. Với multi-tenant, service principal/permissions gắn dữ liệu server-side và kiểm tra resource ownership?
21. Tests unit converter/manager/token và HTTP integration đủ negative branches?
22. Tests concurrency, revocation, storage outage và rotation phù hợp production?
23. Framework/API package/version được pin/kiểm chứng và có bảo trì security patches?

## 11. Câu hỏi tự đánh giá

**1.** Tại sao converter không được gọi `setAuthenticated(true)`?

**Đáp án:** Vì converter chỉ có HTTP input chưa được tin; manager mới verify secret và tạo authenticated result.

**2.** `Mono.empty()` trong converter là “đã xác thực anonymous” hay “không có attempt”?

**Đáp án:** Là **không có authentication attempt** cho filter này; security chain vẫn có thể từ chối request private.

**3.** Khi credential có mặt nhưng sai format hoặc bị duplicate, nên trả gì?

**Đáp án:** `Mono.error(BadCredentialsException)` để failure handler trả 401.

**4.** Manager nên gán authorities từ `X-Role` không?

**Đáp án:** Không. Authority phải xuất phát từ chính sách/server-side identity sau verify.

**5.** Vì sao cần matcher và authorizeExchange cùng lúc?

**Đáp án:** Matcher giới hạn *khi nào parse/verify credential*; authorizeExchange quyết định *ai được gọi endpoint*.

**6.** NoOp security context có làm principal biến mất trong request hiện tại không?

**Đáp án:** Không. Nó chỉ không persist qua requests; Authentication vẫn nằm trong Reactor Context của request đang xử lý.

**7.** Trường hợp key đúng nhưng thiếu admin authority có response gì?

**Đáp án:** 403 Forbidden; Authentication thành công nhưng không đủ quyền.

**8.** Có thể test converter chỉ bằng `mockAuthentication()` không?

**Đáp án:** Không. Mock bypass converter; cần unit test converter và HTTP integration test gửi credential header thật.

**9.** Tại sao key trong browser JavaScript không được xem là secret?

**Đáp án:** Người dùng có thể xem bundle/DevTools và trích xuất key; dùng OAuth2/OIDC/PKCE hoặc backend session thay cho static shared secret.

**10.** Vì sao static key còn có replay risk dù so hash constant-time?

**Đáp án:** Digest compare chỉ kiểm tra trùng credential; bất kỳ ai lấy được raw key đều có thể dùng lại đến khi key bị revoke/expire.

**11.** Có cần tạo class custom nếu đang dùng Bearer JWT chuẩn?

**Đáp án:** Thường không; dùng Spring Security OAuth2 Resource Server để hưởng chuẩn signature/issuer/expiry/audience validation.

**12.** Manager trả `Mono.empty()` khi gặp Authentication type khác có nghĩa gì?

**Đáp án:** Nó không hỗ trợ loại token đó, để hệ thống composition quyết định; không có nghĩa credentials đó đã hợp lệ.

## Tài liệu tham khảo

- Spring Security 6.5 — `AuthenticationWebFilter` Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security 6.5 — `ServerAuthenticationConverter` Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
- Spring Security 6.5 — `ServerHttpSecurity.addFilterAt(...)` and exception handling: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 — `SecurityWebFiltersOrder`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html
- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 — Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — `ServerAuthenticationEntryPointFailureHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html
- Spring Security — `HttpStatusServerEntryPoint`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/HttpStatusServerEntryPoint.html
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
