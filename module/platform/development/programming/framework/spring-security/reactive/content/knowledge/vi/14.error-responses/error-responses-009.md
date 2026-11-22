# Không làm lộ mật khẩu, token, stack trace hoặc chi tiết tài khoản trong phản hồi lỗi

## 1. Bối cảnh và mục tiêu

Trong một ứng dụng **Spring Security reactive / Spring WebFlux**, lỗi không chỉ là việc trả HTTP `401`, `403` hay `500`. Mỗi phản hồi còn có **body, headers, thông điệp, status code, thời gian phản hồi và các thông tin liên quan**. Nếu xây dựng phản hồi thiếu kiểm soát, ứng dụng có thể vô tình tiết lộ:

- **Mật khẩu** người dùng đã gửi hoặc password hash lưu trong `UserDetails`.
- **Access token, refresh token, JWT, API key, session ID**, giá trị `Authorization` hoặc `Cookie`.
- **Stack trace**, tên lớp Java, package, đường dẫn tệp, câu SQL, địa chỉ server, chi tiết cấu hình và lỗi hạ tầng.
- **Thông tin tài khoản**: username/email có tồn tại, tài khoản có bị khóa, vô hiệu hóa, hết hạn, có role nào, lần đăng nhập cuối, loại cơ chế MFA.
- Thông tin suy ra từ **status, độ dài body, redirect, response headers hoặc thời gian xử lý khác nhau**.

Một phản hồi có vẻ “hữu ích cho người dùng” như `User alice@example.test exists but password is incorrect` lại giúp attacker dò được account. Một response 500 chứa `IllegalStateException: JWT secret=...` có thể biến lỗi ứng dụng thành sự cố lộ credential.

Mục tiêu bài học:

1. Thiết kế **hợp đồng phản hồi lỗi an toàn** cho 401, 403, 400/404 và 500, không làm mất HTTP semantics cần thiết.
2. Hiểu đúng ranh giới **authentication failure**, **authorization denied** và **application exception** trong chuỗi reactive.
3. Cấu hình `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` của WebFlux để trả JSON không chứa exception message.
4. Phân biệt `@RestControllerAdvice` và `ErrorWebExceptionHandler`; biết vì sao một handler không bao phủ mọi lỗi.
5. Cấu hình các thuộc tính `server.error.*` trong Spring Boot để tắt thông tin lỗi nội bộ.
6. Viết demo **Java 17+, Spring Boot 3.3.5, WebFlux** có người dùng mẫu, 401/403/500 được chuẩn hóa.
7. Kiểm thử sai username, sai mật khẩu, tài khoản disabled và lỗi có **canary giả** để xác minh không rò rỉ.
8. Giữ thông tin đủ dùng cho vận hành **ở kênh log có kiểm soát**, đồng thời tránh chính log/trace trở thành nơi chứa mật khẩu hoặc token.

Bài này tập trung vào **phản hồi lỗi** của Spring Security reactive; không xây dựng hệ thống quản trị user, OAuth2 hay monitoring production đầy đủ. Những secret trong ví dụ đều là **giá trị giả dành cho localhost**, không phải credential thật.

## 2. Nguyên tắc: phản hồi cho client và dữ liệu chẩn đoán là hai kênh khác nhau

Hợp đồng nên trả cho client thông tin vừa đủ để thực hiện bước tiếp theo, không trả dữ liệu nội bộ chỉ phục vụ debug.

Ví dụ phản hồi cho người dùng chưa xác thực:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store
WWW-Authenticate: Basic realm="api"

{"code":"AUTHENTICATION_FAILED","message":"Authentication failed"}
```

Với user đã xác thực nhưng thiếu quyền:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
```

Với lỗi server không mong muốn:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store

{"code":"INTERNAL_ERROR","message":"An unexpected error occurred"}
```

Các response trên chỉ là **ví dụ schema ứng dụng**, không phải Spring Security bắt buộc mọi API dùng đúng chuỗi. Một sản phẩm có thể dùng `ProblemDetail` / `application/problem+json` (RFC 9457), nhưng vẫn phải dùng **code/message đã chọn lọc**, không chép nguyên exception detail hay credentials vào `detail`/`instance`.

### Điều không được trả

```json
{
  "username": "alice@example.test",
  "password": "FAKE_PASSWORD_CANARY",
  "accessToken": "FAKE_TOKEN_CANARY",
  "status": "LOCKED",
  "roles": ["ROLE_ADMIN"],
  "exception": "org.example.security.TokenValidationException",
  "message": "Account alice@example.test is locked",
  "stackTrace": "at org.example...:123",
  "database": "postgres://internal-host/..."
}
```

Đây là **anti-pattern chứa dữ liệu minh họa giả**. Cần tránh cả trường hợp response bị lộ bằng cách đặt những giá trị này vào `error`, `details`, `debugInfo`, `causes`, `validationErrors` hoặc HTTP response header.

### Phân biệt HTTP status đúng nghĩa

| Trạng thái | Ý nghĩa điển hình | Thông tin client nên nhận | Không nên lộ |
| --- | --- | --- | --- |
| `400 Bad Request` | Cú pháp/input không hợp lệ | Mã lỗi input + hướng dẫn chung hoặc field **được allowlist** | Giá trị password/token đã nhập; raw binding result |
| `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực | Lời nhắn chung `Authentication failed`; Basic challenge khi cần | Username có tồn tại, password sai, tài khoản locked/disabled |
| `403 Forbidden` | Đã xác thực nhưng thiếu quyền; hoặc bị một rule security khác chặn | Lời nhắn chung `Access denied` | Quyền cụ thể đang thiếu nếu không cần tiết lộ, nhóm/tài khoản khác |
| `404 Not Found` | Resource không tồn tại hoặc chính sách che giấu resource | `Not found` | Xác nhận ID nhạy cảm tồn tại nhưng thuộc người khác |
| `429 Too Many Requests` | Giới hạn truy cập/thử đăng nhập | `Too many requests`, có thể có `Retry-After` phù hợp | Trạng thái brute-force riêng cho từng username |
| `500 Internal Server Error` | Lỗi xử lý phía server | `An unexpected error occurred`, support ID an toàn nếu có | Java stack trace, class names, file paths, SQL, config, tokens |

**Không gộp mọi loại lỗi thành 200 OK** chỉ để response trông giống nhau: điều đó làm hỏng hợp đồng HTTP, cảnh báo và xử lý client. Với **các trường hợp thất bại đăng nhập cùng cơ chế**, giữ status, message, cấu trúc và cách xử lý nhất quán để giảm account enumeration. Phân biệt 401 và 403 vẫn cần cho semantics của authentication/authorization.

## 3. Threat model: lộ thông tin qua những “đường phụ”

### 3.1. Body chứa exception message

Sai:

```java
// Anti-pattern: ex có thể chứa raw token, địa chỉ DB, username.
return Mono.just(Map.of("error", ex.getMessage()));
```

Đây là fragment trong error handler giả định đã có biến `ex`. Không dùng `ex.getMessage()`, `ex.toString()` hoặc `ExceptionUtils.getStackTrace(ex)` làm nội dung API response. Ngay cả `BadCredentialsException` đôi khi mang thông tin authentication request hoặc cause; không trả nó về client.

### 3.2. Chi tiết tài khoản gây enumeration

Ba kịch bản sau phải **không tiết lộ nguyên nhân riêng biệt** khi client đang thử login:

1. User `ghost` không tồn tại.
2. User `reader` tồn tại nhưng password sai.
3. User `disabled` tồn tại nhưng bị vô hiệu hóa.

Nếu response là `No such user`, `Wrong password` và `Account disabled`, attacker có thể dò username hợp lệ. OWASP khuyến nghị phản hồi authentication **chung**, kể cả account locked hoặc disabled.

Tuy nhiên **chung một body chưa chắc đã đủ**: status code, `Location` redirect, `WWW-Authenticate`, độ dài response hoặc độ trễ khác nhau vẫn có thể tiết lộ. Dùng chung policy ở mọi điểm kiểm tra đăng nhập và thêm rate limiting, phát hiện credential stuffing, kiểm soát lockout/MFA phù hợp.

### 3.3. Token, claims và chữ ký

Ví dụ không an toàn:

```text
Invalid JWT "eyJhbGciOi..." signed with key id=prod-key-04
Token expired for alice@example.test at internal-host
Refresh token FAKE_TOKEN_CANARY rejected
```

Các token có thể mang bearer privilege hoặc chứa claims/PII. Không phản hồi toàn bộ JWT, raw token, refresh token, JWK private key, client secret, session ID hoặc claims nhạy cảm. Với bearer token, challenge/header tuân thủ OAuth2 có thể mang `error`/`error_description` theo tiêu chuẩn; chọn mô tả tối thiểu và **không đặt raw token** vào đó.

### 3.4. Debug/stack trace và đường dẫn nội bộ

Một stack trace có thể để lộ:
- Spring Security/Spring Framework versions, package names, class names.
- Tên module, paths, file names, dòng code.
- Loại database/driver, SQL, topology mạng hoặc địa chỉ dịch vụ nội bộ.
- Exception cause chứa token/password/query params và dữ liệu người dùng.

Không dựa vào “frontend sẽ giấu” vì attacker đọc HTTP response trực tiếp. Các thuộc tính `server.error.*` của Spring Boot giúp hạn chế error attributes, nhưng vẫn cần rà **custom handlers, gateway, WebFilter và tracing**.

### 3.5. Header, URL và cache cũng có thể tiết lộ

- `Location`/redirect query có thể mang username, email, reason hoặc token.
- `WWW-Authenticate` nên mang challenge chuẩn; không đặt mật khẩu/token vào `realm`.
- `Set-Cookie` không được chứa raw password và không nên bị phản hồi trong lỗi theo cách lộ session ID.
- Query/path trong `instance`, `path` hoặc raw URL có thể chứa identifier nhạy cảm. Đừng đưa toàn bộ URL vào error payload khi hệ thống từng cho phép secret trong query.
- Với lỗi xác thực, nên dùng `Cache-Control: no-store` để tránh response nhạy cảm bị lưu ngoài ý định; cấu hình cache/proxy còn phụ thuộc loại tài nguyên.
- Các header debug như `X-Exception-Class`, `X-Stacktrace`, `X-Sql` hoàn toàn không phù hợp cho public API.

## 4. Ba tầng xử lý lỗi trong Spring Security WebFlux

```text
Client request
     |
     v
SecurityWebFilterChain
     |
     +-- AuthenticationWebFilter / HTTP Basic
     |        |
     |        +-- failure -> ServerAuthenticationEntryPoint
     |
     +-- Authorization / ExceptionTranslationWebFilter
     |        |
     |        +-- cần xác thực -> ServerAuthenticationEntryPoint -> 401
     |        +-- thiếu quyền  -> ServerAccessDeniedHandler      -> 403
     |
     v
WebFlux Handler / Controller / Service
     |
     +-- Controller exception -> @ExceptionHandler / @RestControllerAdvice
     |
     +-- Lỗi chưa được giải quyết -> ErrorWebExceptionHandler /
                                     Spring Boot reactive error handling
     |
     v
HTTP response
```

Sơ đồ có mục tiêu phân biệt **đường xử lý**, không cam kết thứ tự mọi WebFilter trong từng phiên bản. Thực tế có thể có exception ở decoder, CORS, CSRF, resource server, gateway hoặc một WebFilter riêng; đừng suy đoán một `@RestControllerAdvice` sẽ bắt hết.

### 4.1. `ServerAuthenticationEntryPoint`

Import: `org.springframework.security.web.server.ServerAuthenticationEntryPoint`.

Hợp đồng khái niệm:

```java
Mono<Void> commence(
        ServerWebExchange exchange,
        AuthenticationException exception);
```

Khi cần yêu cầu client xác thực hoặc xử lý sai credentials, entry point quyết định response thích hợp (thường 401). Với HTTP Basic, nên có `WWW-Authenticate: Basic realm="api"` để client hiểu cách xác thực; **không chép exception message** vào body.

### 4.2. `ServerAccessDeniedHandler`

Import: `org.springframework.security.web.server.authorization.ServerAccessDeniedHandler`.

Hợp đồng khái niệm:

```java
Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException denied);
```

Khi user đã xác thực nhưng không đủ role/authority, handler trả 403 chung. Không trả danh sách roles, chính sách nội bộ hoặc tên account sở hữu resource.

### 4.3. `@RestControllerAdvice`

Advice bắt exception từ controller/handler mapping tương ứng, không phải cơ chế xử lý mọi lỗi trong WebFilter hoặc trước khi controller được gọi. Nó hữu ích để chuẩn hóa 400/404/500 trong controller, nhưng **không thay cho `exceptionHandling(...)` của Spring Security**.

Nếu có method security `@PreAuthorize` hoặc reactive errors từ service, cần kiểm thử thứ tự và đường xử lý thực tế. Một `@ExceptionHandler(Exception.class)` viết ẩu có thể nuốt `AccessDeniedException` và biến lỗi 403 thành 500, hoặc tệ hơn trả 200. Chỉ xử lý những exception thuộc phạm vi rõ ràng và không làm mất semantics security.

### 4.4. `ErrorWebExceptionHandler` và Boot error attributes

Spring Boot WebFlux có xử lý lỗi ngoài controller. Thuộc tính `server.error.include-message`, `include-stacktrace`, `include-exception`, `include-binding-errors` và `include-path` kiểm soát các trường trong default error response. Không nên bật các lựa chọn “always” trên production chỉ để dễ debug.

Nếu một ứng dụng muốn tất cả lỗi đều theo một schema JSON riêng, có thể triển khai/customize `ErrorWebExceptionHandler` / `ErrorAttributes`, nhưng cần bảo toàn status đúng và bảo vệ khỏi vòng lặp lỗi. Đó là phần mở rộng sau khi đã kiểm thử đường 401/403/500 cơ bản.

## 5. Thiết kế error contract ít rò rỉ

Dùng các **mã lỗi ổn định do server kiểm soát** thay vì phản chiếu nguyên văn exception:

| Code ứng dụng | Status HTTP | Message cho client |
| --- | --- | --- |
| `AUTHENTICATION_FAILED` | 401 | `Authentication failed` |
| `ACCESS_DENIED` | 403 | `Access denied` |
| `BAD_REQUEST` | 400 | `Invalid request` |
| `NOT_FOUND` | 404 | `Not found` |
| `RATE_LIMITED` | 429 | `Too many requests` |
| `INTERNAL_ERROR` | 500 | `An unexpected error occurred` |

Nếu sản phẩm cần localization, có thể trả **code ổn định** và để frontend dùng bảng dịch. Không lấy nguyên `ex.getLocalizedMessage()` làm bản dịch công khai.

### Correlation ID: hữu ích nhưng phải an toàn

`requestId` có thể giúp support tra cứu log nếu:
- Do server/gateway đáng tin sinh ra, ví dụ UUID hoặc ID ngẫu nhiên với độ dài có giới hạn.
- Không bằng username, session ID, JWT, email, API key, database key hay fingerprint nhạy cảm.
- Nếu nhận ID từ client, cần validate/normalize và không dùng nó làm chứng cứ danh tính.
- Log có quyền truy cập kiểm soát và dữ liệu đã redact.

Ví dụ:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "An unexpected error occurred",
  "requestId": "req-7f39a21e"
}
```

Đây là schema minh họa, không phải yêu cầu phải công khai mọi request ID. Nếu chưa có hệ thống correlation ID đáng tin, bỏ trường này còn tốt hơn tự nhét raw request URL hoặc token vào.

## 6. Ví dụ chạy được: Java 17+, Spring Boot 3.3.5, WebFlux

Dự án dùng HTTP Basic ở localhost để dễ quan sát 401/403 và có endpoint phát sinh lỗi server **chủ đích** để thử không lộ thông tin. Với triển khai thật, **HTTP Basic phải chạy qua HTTPS/TLS có xác minh certificate**.

Cấu trúc:

```text
safe-reactive-errors/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/safeerrors/
    │   │   ├── SafeErrorsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── SafeApiErrorWriter.java
    │   │   ├── DemoController.java
    │   │   └── SafeControllerAdvice.java
    │   └── resources/application.properties
    └── test/java/dev/example/safeerrors/
        └── SafeErrorResponsesTests.java
```

### 6.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'safe-reactive-errors'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` vào demo nếu muốn Spring Boot chọn WebFlux reactive. Boot quản lý phiên bản Spring Security qua dependency management, không pin lẻ các dependency bảo mật để tránh lệch version.

### 6.2. Spring Boot properties: không bật trace ra client

`src/main/resources/application.properties`:

```properties
server.port=8080

server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false
server.error.include-path=never

logging.level.org.springframework.security=INFO
```

Những giá trị này phù hợp với Spring Boot 3.3.x. `include-path=never` còn giảm khả năng phản hồi raw URL/path chứa dữ liệu không nên công khai. Một số thuộc tính có default an toàn, nhưng việc khai báo rõ giúp tránh một cấu hình profile khác vô tình bật trace.

**Giới hạn:** `server.error.*` điều chỉnh **default Boot error attributes**, không tự scrub JSON do controller custom trả, không ngăn log của proxy/APM và không override một handler cố ý phản hồi `ex.getMessage()`. Vì vậy ta vẫn cần hai lớp handler dưới đây.

### 6.3. Main application

`src/main/java/dev/example/safeerrors/SafeErrorsApplication.java`:

```java
package dev.example.safeerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeErrorsApplication.class, args);
    }
}
```

### 6.4. Bộ ghi JSON lỗi dành riêng cho security

`src/main/java/dev/example/safeerrors/SafeApiErrorWriter.java`:

```java
package dev.example.safeerrors;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class SafeApiErrorWriter {

    public static final String AUTHENTICATION_JSON =
            "{\"code\":\"AUTHENTICATION_FAILED\",\"message\":\"Authentication failed\"}";

    public static final String ACCESS_DENIED_JSON =
            "{\"code\":\"ACCESS_DENIED\",\"message\":\"Access denied\"}";

    private SafeApiErrorWriter() {
    }

    public static Mono<Void> authenticationFailure(ServerWebExchange exchange) {
        return write(exchange, HttpStatus.UNAUTHORIZED,
                AUTHENTICATION_JSON, true);
    }

    public static Mono<Void> accessDenied(ServerWebExchange exchange) {
        return write(exchange, HttpStatus.FORBIDDEN,
                ACCESS_DENIED_JSON, false);
    }

    private static Mono<Void> write(
            ServerWebExchange exchange,
            HttpStatus status,
            String safeJson,
            boolean basicChallenge) {

        ServerHttpResponse response = exchange.getResponse();

        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().setCacheControl("no-store");
        response.getHeaders().set("X-Content-Type-Options", "nosniff");

        if (basicChallenge) {
            response.getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"api\"");
        }

        byte[] bytes = safeJson.getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
```

Điểm then chốt:
- Response JSON là **hằng số do server định nghĩa**, không chứa exception, username, token hay password.
- Hai phương thức chọn status tương ứng 401 và 403. Không trả `AccessDeniedException.getMessage()` hoặc `AuthenticationException.getMessage()`.
- Header `WWW-Authenticate` chỉ chứa realm `api`, không chứa định danh user hay credentials. Đây là yêu cầu tương tác phù hợp HTTP Basic.
- `Cache-Control: no-store` tránh lưu các error responses theo cách không mong muốn; vẫn cần đánh giá cache/proxy toàn hệ thống.
- `DataBuffer`/`Mono<Void>` được trả cho WebFlux; không gọi `block()`/`subscribe()`.
- `MediaType.APPLICATION_JSON` cho biết JSON; không cần thiết kế framework riêng nếu muốn schema đơn giản và cố định.

Vì JSON là hằng số nên không có nguy cơ JSON injection từ exception message. Khi chuyển sang giá trị động như request ID, sử dụng JSON serializer, validate input và **chỉ cho phép trường được định nghĩa rõ**; không tự ghép raw exception vào JSON.

### 6.5. Kết nối entry point và access-denied handler với Spring Security

`src/main/java/dev/example/safeerrors/SecurityConfig.java`:

```java
package dev.example.safeerrors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encoder.encode("disabled-pass"))
                .roles("USER")
                .disabled(true)
                .build();

        return new MapReactiveUserDetailsService(
                reader, admin, disabled);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {

        ServerAuthenticationEntryPoint entryPoint =
                (exchange, exception) ->
                        SafeApiErrorWriter.authenticationFailure(exchange);

        ServerAccessDeniedHandler deniedHandler =
                (exchange, denied) ->
                        SafeApiErrorWriter.accessDenied(exchange);

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(entryPoint)
                        .authenticationFailureHandler(
                                new ServerAuthenticationEntryPointFailureHandler(
                                        entryPoint)))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler))
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Giải thích:
1. `MapReactiveUserDetailsService` giữ ba tài khoản **thử nghiệm**. `reader` và `admin` enabled, `disabled` có `isEnabled() == false`. Password được encode bằng BCrypt; không dùng cleartext password trong storage thật.
2. `ServerAuthenticationEntryPoint` nhận `AuthenticationException`, nhưng lambda **cố ý không đọc `exception`**. Thay vào đó, trả body `AUTHENTICATION_FAILED`.
3. `ServerAccessDeniedHandler` nhận `AccessDeniedException`, nhưng **cố ý không phản chiếu `denied.getMessage()`**.
4. `HttpBasicSpec.authenticationEntryPoint(...)` dùng entry point chung cho cơ chế Basic. `authenticationFailureHandler(...)` với `ServerAuthenticationEntryPointFailureHandler` xác định phản hồi khi trình xác thực Basic phát lỗi credentials.
5. `ExceptionHandlingSpec.authenticationEntryPoint(...)` và `accessDeniedHandler(...)` xử lý trường hợp được yêu cầu xác thực hoặc bị từ chối khi authorize.
6. `formLogin(form -> form.disable())` tắt form login để client nhận lỗi JSON thay vì redirect HTML đến `/login`.
7. `/public` không yêu cầu đăng nhập; `/admin` yêu cầu `ROLE_ADMIN`; các endpoint còn lại cần authenticated user.

**Chú ý production:** `ServerAuthenticationEntryPointFailureHandler` có chính sách chuyển tiếp `AuthenticationServiceException` (lỗi dịch vụ) theo implementation; đừng cố chuyển mọi lỗi database/identity provider thành “bad password” chỉ để API luôn 401. Thất bại hạ tầng cần được xử lý và giám sát như sự cố hệ thống, nhưng response công khai vẫn phải sanitized.

**Lưu ý CSRF:** Demo chỉ sử dụng GET, nên không cần thay đổi CSRF mặc định. Đừng thêm `csrf(csrf -> csrf.disable())` chỉ để một POST test chạy; việc có cần CSRF phụ thuộc cơ chế client, browser và authentication.

### 6.6. Controller: một route công khai, hai route bảo vệ và một lỗi giả

`src/main/java/dev/example/safeerrors/DemoController.java`:

```java
package dev.example.safeerrors;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(Principal principal) {
        return Mono.just(Map.of("user", principal.getName()));
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }

    @GetMapping("/explode")
    public Mono<String> simulatedFailure() {
        // Dữ liệu giả chỉ để kiểm tra không lộ qua phản hồi 500.
        return Mono.error(new IllegalStateException(
                "FAKE_SECRET_CANARY_042 in internal stack trace"));
    }
}
```

`/explode` chỉ dùng trong demo cục bộ. Không đưa một endpoint cố ý gây lỗi vào sản phẩm. Thực tế, lỗi có thể đến từ database, HTTP client, parser, service hoặc external API; không cần cố ý chứa secret trong exception để test production.

Với `/me`, chỉ trả username **cho chính principal đã xác thực**, không trả `UserDetails.getPassword()` hoặc authorities khi không có nhu cầu. Nếu API có endpoint query user khác, phải tách DTO/profile và áp dụng authorization theo ownership.

### 6.7. Controller advice: không phản chiếu lỗi 500

`src/main/java/dev/example/safeerrors/SafeControllerAdvice.java`:

```java
package dev.example.safeerrors;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SafeControllerAdvice {

    public record SafeError(String code, String message) {
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<SafeError> handleDemoInternalFailure(
            IllegalStateException ignored) {

        SafeError safe = new SafeError(
                "INTERNAL_ERROR", "An unexpected error occurred");

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .cacheControl(CacheControl.noStore())
                .body(safe);
    }
}
```

Ở đây `ignored` là exception đã được xử lý **nhưng không được trả nguyên văn**. Đoạn code trả một DTO an toàn, status 500 và Cache-Control no-store. Dù message của exception chứa chuỗi giả `FAKE_SECRET_CANARY_042`, response chỉ chứa `INTERNAL_ERROR`.

**Phạm vi cần hiểu:** Advice đang bắt `IllegalStateException` từ controller demo. Nó **không phải** một blanket catch-all cho mọi lỗi tầng WebFilter/Netty, và không hứa biến mọi exception hạ tầng thành đúng một schema. Spring Boot `server.error.*` cung cấp lớp bảo vệ mặc định cho những lỗi còn lại. Muốn chuẩn hóa toàn bộ hệ thống, thiết kế thêm `ErrorWebExceptionHandler`/`ErrorAttributes`, kiểm thử security filters, CORS, CSRF, rate limiter và gateway.

Đừng thêm bừa `@ExceptionHandler(Exception.class)` để trả 200 hoặc 500 cho `AccessDeniedException`: làm vậy có thể che mất trạng thái 401/403 của Spring Security. Nếu cần catch-all, cần bảo đảm xử lý riêng các ngoại lệ bảo mật, giữ HTTP semantics và rà mọi đường đi của lỗi.

## 7. Chạy ứng dụng và quan sát các nhóm phản hồi

Từ thư mục `safe-reactive-errors`:

```bash
gradle bootRun
```

Nếu dùng Gradle Wrapper, chạy `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Ở localhost, lệnh curl có thể thử HTTP; **không dùng HTTP Basic trên mạng công cộng nếu không có HTTPS/TLS**.

Các lệnh minh họa:

```bash
# Endpoint công khai:
curl -i http://localhost:8080/public

# Endpoint cần xác thực, thiếu credentials:
curl -i http://localhost:8080/me

# Sai username:
curl -i -u ghost:guess http://localhost:8080/me

# Sai mật khẩu:
curl -i -u reader:wrong http://localhost:8080/me

# Tài khoản có tồn tại nhưng disabled:
curl -i -u disabled:disabled-pass http://localhost:8080/me

# Đúng credentials, có role USER:
curl -i -u reader:reader-pass http://localhost:8080/me

# Reader thiếu role ADMIN:
curl -i -u reader:reader-pass http://localhost:8080/admin

# Admin có role ADMIN:
curl -i -u admin:admin-pass http://localhost:8080/admin

# Demo lỗi 500 với message chứa canary giả:
curl -i -u reader:reader-pass http://localhost:8080/explode
```

**Lưu ý cho công cụ:** Các password trên là chuỗi **giả** dành cho localhost. Với secret thực tế, không đặt mật khẩu sau `-u user:password` trong shell history/process arguments. Sử dụng `curl --user reader` để curl hỏi password tương tác và luôn dùng HTTPS với certificate validation.

### Ma trận kết quả dự kiến

| Request | Status | Response chính |
| --- | --- | --- |
| `GET /public`, không đăng nhập | 200 | `public` |
| `GET /me`, thiếu Basic | 401 | `AUTHENTICATION_FAILED` |
| `GET /me`, username không tồn tại | 401 | `AUTHENTICATION_FAILED`, message giống trường hợp khác |
| `GET /me`, reader sai password | 401 | `AUTHENTICATION_FAILED`, message giống trường hợp khác |
| `GET /me`, disabled đúng password | 401 | `AUTHENTICATION_FAILED`, không tiết lộ trạng thái tài khoản |
| `GET /me`, reader đúng password | 200 | JSON chứa `user=reader`, không có password/hash |
| `GET /admin`, reader đúng password | 403 | `ACCESS_DENIED` |
| `GET /admin`, admin đúng password | 200 | `admin-ok` |
| `GET /explode`, reader đúng password | 500 | `INTERNAL_ERROR`, không có `FAKE_SECRET_CANARY_042` |

Đây là **kết quả kỳ vọng theo ví dụ**, không phải tuyên bố đã chạy Gradle trên máy của bạn. Status/body của một số đường (đặc biệt ngoài controller) có thể thay đổi nếu bạn dùng filter/error handler khác. Hãy dựa vào test thực tế để xác nhận khi nâng version Spring Security.

### Tại sao 401 dùng challenge nhưng 403 không?

HTTP Basic client cần biết cơ chế xác thực nên 401 có `WWW-Authenticate: Basic realm="api"`. Người dùng đã xác thực nhưng không có quyền ở `/admin` thường nhận 403. 403 không nên tiết lộ “Bạn thiếu ROLE_SUPER_ADMIN trong tenant 42” nếu đó là thông tin nội bộ.

## 8. Kiểm thử tự động với WebTestClient

Test không chỉ xem status; phải kiểm tra **không có thông tin nhạy cảm trong body**, và các lỗi đăng nhập khác nhau trả thông điệp nhất quán.

`src/test/java/dev/example/safeerrors/SafeErrorResponsesTests.java`:

```java
package dev.example.safeerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SafeErrorResponsesTests {

    @Autowired
    WebTestClient client;

    private static void assertNoLeak(String body) {
        assertNotNull(body);
        assertFalse(body.contains("FAKE_SECRET_CANARY_042"));
        assertFalse(body.contains("reader-pass"));
        assertFalse(body.contains("disabled-pass"));
        assertFalse(body.contains("TokenValidationException"));
        assertFalse(body.contains("IllegalStateException"));
        assertFalse(body.contains("stackTrace"));
        assertFalse(body.contains("org.springframework."));
        assertFalse(body.contains("at dev.example."));
    }

    private String unauthorizedBody(String username, String password) {
        String body = client.get().uri("/me")
                .headers(h -> h.setBasicAuth(username, password))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody(String.class)
                .returnResult().getResponseBody();

        assertNoLeak(body);
        return body;
    }

    @Test
    void publicEndpointIsAvailable() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsReturnSanitized401() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueMatches(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"api\"")
                .expectBody()
                .jsonPath("$.code").isEqualTo("AUTHENTICATION_FAILED")
                .jsonPath("$.message").isEqualTo("Authentication failed");
    }

    @Test
    void wrongUserWrongPasswordAndDisabledHaveSamePublicError() {
        String missingUser = unauthorizedBody("ghost", "guess");
        String wrongPassword = unauthorizedBody("reader", "wrong");
        String disabled = unauthorizedBody("disabled", "disabled-pass");

        assertEquals(SafeApiErrorWriter.AUTHENTICATION_JSON, missingUser);
        assertEquals(missingUser, wrongPassword);
        assertEquals(missingUser, disabled);
    }

    @Test
    void successfulLoginReturnsIdentityOnly() {
        String body = client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult().getResponseBody();

        assertNotNull(body);
        assertTrue(body.contains("reader"));
        assertFalse(body.contains("reader-pass"));
        assertFalse(body.contains("password"));
        assertFalse(body.contains("ROLE_ADMIN"));
    }

    @Test
    void readerCannotAccessAdminAndReceivesGeneric403() {
        String body = client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody(String.class)
                .returnResult().getResponseBody();

        assertEquals(SafeApiErrorWriter.ACCESS_DENIED_JSON, body);
        assertNoLeak(body);
    }

    @Test
    void adminIsAuthorized() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void unexpectedControllerExceptionDoesNotLeakCanary() {
        String body = client.get().uri("/explode")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().is5xxServerError()
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody(String.class)
                .returnResult().getResponseBody();

        assertNotNull(body);
        assertTrue(body.contains("INTERNAL_ERROR"));
        assertNoLeak(body);
    }

    @Test
    void invalidPasswordDoesNotReflectInput() {
        String canaryPassword = "FAKE_SECRET_CANARY_042";
        String body = unauthorizedBody("reader", canaryPassword);
        assertFalse(body.contains(canaryPassword));
    }
}
```

Chạy test:

```bash
gradle test
```

**Dự kiến:** 8 test thành công khi dùng đúng dự án và dependency trên. Đây là kết quả dự kiến từ code; **chưa có bằng chứng Gradle đã được chạy** trong repository của bạn.

### Test đảm bảo điều gì?

1. Route public vẫn hoạt động.
2. Không có Basic → 401 JSON an toàn và có challenge Basic.
3. Username không tồn tại, password sai, tài khoản disabled có **cùng status/body**; tránh lộ nguyên nhân qua response content.
4. Login đúng không trả password/hash.
5. Người thiếu role nhận **403 chung**, không nhận quyền được bảo vệ hoặc exception class.
6. Admin đủ quyền vẫn vào được endpoint hợp lệ.
7. Lỗi controller giả có canary trong exception nhưng body 500 **không chứa canary/stack trace**.
8. Password giả do client tự điền không được phản chiếu trong response.

**Giới hạn cần nhớ:** Test body bằng equality không chứng minh hoàn toàn không có account enumeration. Attacker còn có thể phân tích **thời gian xử lý, response size, headers khác nhau, rate-limit behavior và các kênh login/password reset**. Cần test thêm bằng phép đo có kiểm soát, nhưng không khẳng định “constant time” chỉ vì response body bằng nhau.

### Mở rộng test bằng canary

Trong môi trường thử **không có secret thật**, có thể gửi những giá trị phân biệt như `FAKE_SECRET_CANARY_042` trong password/header và tạo lỗi chủ đích với cùng canary, rồi kiểm tra:
- HTTP response body/headers không chứa canary.
- Error log, proxy log, APM spans không chứa raw canary ở các trường bị cấm.
- Không có class name, SQL, password hash, token payload và raw Authorization trong response.
- API gateway không trả stack trace khi upstream trả 500.
- Test 401/403/500 từ WebFilter và error handler ngoài controller nếu hệ thống đã custom.

Khi kiểm thử log, không dùng token/password production. Dùng một **credential giả hoặc tài khoản thử có thể thu hồi**, xác nhận chính sách log và xóa sau test.

## 9. Làm thế nào để vừa chẩn đoán lỗi vừa không tiết lộ?

### 9.1. Log các trường được allowlist

Một log vận hành có thể chứa:
- `event=AUTH_FAILURE` / `event=ACCESS_DENIED` / `event=SERVER_ERROR`.
- Timestamp, route tag do server cấp, status, latency, service, trace ID không nhạy cảm.
- Account identifier đã được giảm thiểu theo chính sách, nếu cần cho audit và có quyền truy cập phù hợp.
- Category của nguyên nhân ở hệ thống giám sát có kiểm soát, **không public cho client**.

Ví dụ ý tưởng:

```java
// Fragment nằm trong thành phần có logger và context an toàn.
log.warn("event={} route={} outcome={}",
        "AUTH_FAILURE", "api-login", "DENIED");
```

Ngược lại, **không log**:

```java
// ANTI-PATTERN: KHÔNG DÙNG.
log.error("Authentication failed: {}", exception.getMessage());
log.debug("Headers: {}", exchange.getRequest().getHeaders());
log.info("Credentials: {}", authentication.getCredentials());
```

Đây chỉ là các **anti-pattern**, biến `exception`, `exchange` và `authentication` là các đối tượng minh họa trong ngữ cảnh Spring Security. Chúng có thể chứa raw password/token; ngay cả `toString()` đôi khi không an toàn nếu bạn không kiểm soát implementation.

### 9.2. Nếu cần stack trace nội bộ thì sao?

Một số tổ chức cho phép ghi stack trace vào **kênh log có kiểm soát**, phục vụ forensics. Nhưng stack trace có thể chứa exception message nhạy cảm hoặc dữ liệu từ request. Chính sách cần:
- Giới hạn logger/package, sampling, quyền truy cập và retention.
- Redact/không ghi nguyên message của exception không tin cậy.
- Không gửi raw `Authorization`, `Cookie` hoặc bearer token vào log aggregator.
- Không in body có password, OTP hoặc refresh token.
- Không đính stack trace vào API response cho mọi lỗi 500.
- Kiểm tra cấu hình APM/tracing vì nó có thể tự thu exception attributes ngoài logger của ứng dụng.

**Quan trọng:** “Không có stack trace trong HTTP” không đồng nghĩa “không có secret trong logs”. Hai bề mặt tấn công cần review độc lập.

### 9.3. Redaction phải diễn ra tại nguồn

Che một header trong dashboard APM sau khi raw value đã được gửi đến collector **không ngăn được** lộ tại collector/export. Nên dùng allowlist fields được thu từ đầu và drop:
- `Authorization`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie` khi chứa session token.
- `X-API-Key`, custom auth headers, bearer/refresh tokens.
- Mật khẩu, password confirmation, OTP, recovery codes trong body/query.
- Thông tin nhạy cảm được encode trong URL, metadata hoặc nested JSON.

Header names không phân biệt hoa/thường; cơ chế redaction phải nhận diện mọi biến thể. Khi giá trị có thể là secret dưới một field name tự đặt, dùng allowlist an toàn hơn chỉ dựa trên denylist vài key phổ biến.

### 9.4. Bảo vệ thông tin hỗ trợ điều tra

Đừng đưa email, phone, account state, roles hoặc token của người dùng vào issue public để “chứng minh lỗi”. Nếu có request ID, dùng nó tra thông tin chi tiết qua hệ thống nội bộ có RBAC/audit, rồi chia sẻ chỉ những gì được phép.

### 9.5. Log và response là dữ liệu cần policy riêng

Kiểm soát access, encryption at rest, retention, export, backup, log search và hỗ trợ sự cố. Nếu đã lộ secret trong log, **rotate/thu hồi** secret và rà các bản sao; chỉ xóa một dòng log không lấy lại được credential bị tiết lộ.

## 10. Chống dò tài khoản (user enumeration)

OWASP nhấn mạnh rằng “username không tồn tại”, “password sai” và “account disabled/locked” nên có phản hồi công khai **chung** trong ngữ cảnh đăng nhập.

### 10.1. Vì sao chỉ sửa message vẫn chưa đủ?

Attacker có thể thử hàng nghìn username khác nhau và so:
- 401 vs 403 vs 404.
- Body length, JSON fields, headers, redirect destination.
- Thời gian phản hồi trung bình cho user tồn tại/không tồn tại.
- Có/không gửi email ở password reset và nội dung công khai của response.
- Số lần thử trước khi rate limiter, captcha hoặc lockout kích hoạt.
- Thời điểm và kết quả do UI/JS phản ánh.

Để giảm rủi ro:
- Giữ status/body/headers nhất quán cho các loại login failure cùng lớp.
- Thực hiện password verification qua `PasswordEncoder` đáng tin, không tự so hash bằng equals.
- Khi username không tồn tại, thiết kế bảo vệ timing ở tầng authentication phù hợp; **đừng viết một cơ chế fake BCrypt thủ công rồi tuyên bố constant-time**.
- Áp dụng rate limiting / throttling theo IP, account, device hoặc tổ hợp có cân nhắc chống DoS.
- Sử dụng MFA, cảnh báo login bất thường, credential stuffing defense khi phù hợp.
- Thiết kế password reset với thông điệp kiểu “Nếu tài khoản tồn tại, chúng tôi sẽ gửi hướng dẫn”, không xác nhận email tồn tại.
- Trong registration, cân bằng UX và chống enumeration theo risk model; chú ý các khác biệt response không cần thiết.

### 10.2. Không dùng phản hồi chi tiết cho mọi 403

Một business API đôi khi cần trả field-level validation hints như “email format invalid” hoặc “name quá dài”. Chúng có thể được công khai **nếu input không nhạy cảm và thiết kế cho phép**. Nhưng không trả:
- “Account 42 exists but belongs to user B”.
- “User admin@example.test is disabled”.
- “Your password matched, but you lack finance:approve in tenant secret”.
- “JWT signature failed using private key ID ...”.

Khi quyền sở hữu resource cần được che giấu, có thể chọn 404 thay 403 cho một số trường hợp; phải nhất quán và có test tránh resource enumeration. Không tự thay đổi tất cả 403 thành 404 nếu điều đó làm hỏng semantics API và kiểm toán.

## 11. Tránh lộ qua validation error và JSON serialization

Các lỗi của `@Valid`, binding, decoding JSON và enum conversion có thể chứa **giá trị đầu vào** trong exception. Không trả raw:
- `BindingResult.toString()`.
- `WebExchangeBindException.getMessage()`.
- `MethodArgumentNotValidException.getMessage()` theo ví dụ Servlet.
- Request body/payload đã parse nếu chứa mật khẩu, token hoặc giấy tờ nhạy cảm.

Với validation an toàn, chỉ trả một danh sách field **được allowlist** và code do server xác định:

```json
{
  "code": "BAD_REQUEST",
  "message": "Invalid request",
  "fields": [
    {"name":"displayName","code":"TOO_LONG"}
  ]
}
```

Nếu `password` không đạt yêu cầu độ dài, có thể hiển thị thông tin về **quy tắc độ dài** nhưng không trả **giá trị password đã nhập**. Không gửi `rejectedValue` hay nguyên DTO chứa credentials.

Nếu dùng `ProblemDetail`, đừng gán `problem.setDetail(ex.getMessage())` một cách máy móc. Chỉ chọn detail đã được phê duyệt; `instance` không nên phản chiếu raw path/query có secret.

## 12. Lỗi WebFilter, CSRF, CORS, JWT và gateway

### 12.1. `@RestControllerAdvice` không phải chốt chặn cho mọi lỗi

Một `WebFilter` tùy chỉnh có thể phát `Mono.error(...)` **trước controller**. Tương tự, CORS, CSRF và resource-server authentication có thể trả lỗi từ các bộ lọc khác nhau.

Khi muốn một error schema nhất quán trên toàn stack:
1. Liệt kê nguồn lỗi tại từng tầng.
2. Cấu hình entry point/denied handler của Spring Security ở nơi phù hợp.
3. Cấu hình/error attributes hoặc `ErrorWebExceptionHandler` cho unexpected errors ngoài controller.
4. Cấu hình error mapping của gateway/reverse proxy cho trường hợp upstream chết, timeout hoặc body không thể gửi.
5. Kiểm thử phản hồi thật; không chỉ test một controller có `throw new RuntimeException(...)`.

### 12.2. CSRF 403 không nhất thiết là thiếu role

POST thiếu CSRF token có thể nhận 403 **trước** khi logic controller được chạy. Đừng phản chiếu token expected/actual hoặc session ID để debug. Trong demo chỉ có GET, nhưng production có state-changing endpoints phải đánh giá CSRF và test response sanitized trong trường hợp thất bại.

### 12.3. JWT và OAuth2 resource server

Với bearer token, Spring Security có thể dùng OAuth2-specific entry point và `WWW-Authenticate: Bearer ...`. Đừng áp dụng mù quáng `Basic realm="api"` cho API bearer-only; điều đó vi phạm kỳ vọng client. Hãy giữ challenge đúng giao thức, đồng thời chọn `error`/`error_description` không chứa raw JWT, refresh token hoặc claims nhạy cảm.

### 12.4. Gateway trả lỗi khác với ứng dụng

Nếu reverse proxy/Gateway tự phát 502/503/504, `@RestControllerAdvice` của WebFlux **không thấy request/exception đó**. Phải cấu hình gateway error page/body, tắt server banner/debug pages khi thích hợp, scrub headers và test lỗi upstream thực.

### 12.5. Response đã commit

Trong reactive stack, nếu server đã gửi một phần response body rồi publisher phát lỗi, error handler không phải lúc nào cũng có thể thay toàn bộ bằng JSON 500 mới. Không cố ghi thêm stack trace/exception vào response đang stream; thiết kế streaming protocol, logging nội bộ và chính sách partial response hợp lý. Test lỗi giữa chừng với `Flux` hoặc SSE nếu sản phẩm dùng streaming.

## 13. Checklist QA bảo mật cho phản hồi lỗi

1. **401:** cùng thông điệp và cấu trúc cho username không có, password sai, locked/disabled trong cùng flow; Basic/Bearer challenge đúng giao thức.
2. **403:** không trả danh sách authorities, resource ownership hoặc internal rule expression khi không cần thiết.
3. **500:** không có exception class, stack trace, SQL, hostnames, internal file paths, version hoặc secret.
4. **400:** không phản chiếu `rejectedValue` của password/token/OTP.
5. **404:** không tiết lộ resource thuộc user/tenant khác qua status/body khác biệt.
6. **Headers:** không có raw `Authorization`, `Cookie`, `Set-Cookie` chứa secret trong thông điệp hỗ trợ; `WWW-Authenticate`/`Location` được kiểm tra.
7. **URL:** không echo raw query string hoặc request URI có secret.
8. **Cache:** áp dụng cache policy phù hợp; lỗi auth demo dùng `Cache-Control: no-store`.
9. **Error tiers:** thử security filter, controller advice, Boot default handler và gateway riêng.
10. **Timing/enumeration:** không chỉ so body; xem status, headers, độ dài, redirect, throughput/timing và rate limits.
11. **Logging:** không in raw authentication object, request body, headers hay exception message có thể chứa credential.
12. **Observability:** APM/tracing/exporter lọc secrets ngay tại nguồn; không chỉ che ở dashboard.
13. **Security context:** không bịa rằng user đã xác thực thành công khi là anonymous; không biến `AccessDeniedException` thành fallback 200.
14. **Tests:** dùng canary giả, không dùng credential thật; xác minh cả request HTTP và log/trace trong môi trường kiểm soát.
15. **Production flags:** kiểm tra `server.error.include-*` và profile-specific config, không bật trace từ query parameter.
16. **Incident:** nếu credential đã lộ, rotate/thu hồi và kiểm kê mọi bản sao/log/artifact.

## 14. Những anti-pattern cần loại bỏ

| Anti-pattern | Hậu quả | Thay bằng |
| --- | --- | --- |
| `return ex.getMessage()` | Rò rỉ username, token, stack hoặc SQL | Generic code/message |
| `return exception.toString()` | Lộ class/package và cause | Allowlist response DTO |
| 401 “user not found”, 403 “wrong password” | Account enumeration | Một chính sách login-failure thống nhất |
| 500 chứa `stackTrace`/`exception` | Lộ cấu trúc runtime | `server.error.*=never/false` và handler an toàn |
| `@ExceptionHandler(Exception.class)` luôn trả 200 | Che lỗi bảo mật, hỏng HTTP semantics | Handler phân loại đúng; không nuốt `AccessDeniedException` |
| Log nguyên `HttpHeaders` | Lộ Authorization/Cookie | Allowlist metadata an toàn |
| Log nguyên `Authentication` | Có thể lộ credentials/details | Event code và identity đã giảm thiểu |
| `ProblemDetail.detail = ex.getMessage()` | Rò rỉ qua RFC problem details | Detail đã phê duyệt |
| `error.path` chứa query nhạy cảm | Lộ resource identifier/secret | Không echo raw URL; Boot flags |
| Tin frontend giấu response | Attacker vẫn xem raw HTTP | Sanitization ở server/gateway |
| Chỉ kiểm tra status 401 | Body/header vẫn có thể lộ | Kiểm tra toàn bộ response và timing |
| Test dùng password production | Test tự tạo sự cố dữ liệu | Canary giả và tài khoản thử thu hồi |
| Debug APM tự lưu exception | Token trong tracing platform | Scrub ở instrumentation/source |
| Phản hồi 403 tiết lộ role thiếu | Lộ policy/tổ chức nội bộ | `ACCESS_DENIED` chung |
| “Không log stack” nên không cần incident | Secret có thể nằm trong nhiều bản sao khác | Rotation, log inventory, RBAC |

## 15. Câu hỏi ôn tập

**1. Vì sao không nên trả `BadCredentialsException.getMessage()` cho client?**  
Vì exception có thể chứa thông tin chẩn đoán, username, chi tiết tài khoản hoặc dữ liệu nội bộ; nên trả mã/message an toàn do server định nghĩa.

**2. Cần phản hồi như thế nào khi username không tồn tại và khi password sai?**  
Trong cùng flow đăng nhập, dùng status/body/headers nhất quán, tránh tiết lộ nguyên nhân riêng biệt.

**3. `401` khác `403` ở đâu?**  
401 là cần xác thực hoặc credentials không hợp lệ; 403 thường là đã xác thực nhưng không được phép (cũng có thể do rule khác như CSRF).

**4. Header nào cần cân nhắc ở 401 của HTTP Basic?**  
`WWW-Authenticate: Basic realm="api"`, nhưng không chứa credential, user hay secret.

**5. `@RestControllerAdvice` có bắt được mọi exception từ WebFilter không?**  
Không. Cần xử lý tại security entry point/denied handler và Boot reactive error pipeline khi phù hợp.

**6. `server.error.include-stacktrace=never` có tự ngăn custom controller trả stack trace không?**  
Không. Nó chỉ điều chỉnh default error attributes tương ứng; custom code vẫn phải được sửa.

**7. Vì sao body của lỗi auth bằng nhau chưa chứng minh chống enumeration hoàn toàn?**  
Vì có thể vẫn khác status, headers, redirect, timing hoặc rate-limit behavior.

**8. Có thể trả nguyên raw JWT để client tự phân tích lỗi không?**  
Không nên; token có thể mang bearer privilege/PII. Chỉ trả mã lỗi/challenge tối thiểu phù hợp giao thức.

**9. Có nên log nguyên `Authorization` để dễ support không?**  
Không. Nó có thể chứa Basic password hoặc bearer token; thay bằng event code và metadata đã chọn lọc.

**10. Làm thế nào để thử an toàn việc không lộ secret?**  
Dùng canary/credential **giả** trong test và kiểm tra response body/headers, log/APM trong phạm vi được cấp quyền.

**11. Nếu lỗi 500 đến từ gateway chứ không phải WebFlux thì handler nào của app bắt được?**  
Không có handler WebFlux nào chắc chắn bắt được lỗi gateway tự tạo; phải cấu hình/test gateway riêng.

**12. Đặt `ProblemDetail.detail` bằng `ex.getMessage()` có an toàn mặc định không?**  
Không; need allowlist nội dung và tránh cause/instance/path nhạy cảm.

**13. Vì sao không nên dùng `onErrorResume(ex -> Mono.just(secret))` khi authorization fail?**  
Vì nó có thể nuốt `AccessDeniedException` và biến request bị từ chối thành phản hồi thành công chứa dữ liệu nhạy cảm.

**14. Vì sao response errors nên có `Cache-Control: no-store` trong demo?**  
Để giảm nguy cơ cache lưu thông tin lỗi authentication hoặc metadata nhạy cảm; vẫn cần cấu hình toàn bộ hệ thống phù hợp.

### Bài tập thực hành

1. Chạy dự án và so body 401 cho `ghost`, `reader` sai password và `disabled`. Khẳng định chúng giống nhau **về response body**, rồi đề xuất kiểm tra thêm timing/headers.
2. Thêm một cookie test/Authorization header chứa `FAKE_TOKEN_CANARY` ở request demo; kiểm tra response không phản chiếu giá trị này.
3. Cố ý thay `SafeControllerAdvice` bằng `ex.getMessage()` trong môi trường học, chạy test canary để thấy test fail; sau đó hoàn nguyên bản an toàn.
4. Thêm endpoint `GET /admin/details` được bảo vệ role ADMIN và test reader nhận 403 generic, không có tên role hay thông tin account.
5. Dùng `server.error.include-stacktrace=always` trong môi trường test riêng để quan sát rủi ro; **không đưa cấu hình đó vào production**, sau đó khôi phục `never`.
6. Tạo validation error cho body có `password`, thiết kế response `BAD_REQUEST` chứa field name allowlist nhưng không có `rejectedValue`.
7. Thiết kế request ID ngẫu nhiên, đưa vào response và log đã redact để hỗ trợ debug mà không truyền username/token.
8. Thử một `WebFilter` phát lỗi và một controller phát lỗi để giải thích tại sao `@RestControllerAdvice` không thay thế Spring Security exception handling.
9. Nếu dùng bearer token thay HTTP Basic, sửa `WWW-Authenticate` thành Bearer challenge đúng giao thức; kiểm tra không có raw token/claims trong response.
10. Viết checklist cho API gateway: response 502/503/504 không chứa upstream hostname, stack trace, server banner hay raw headers.

## 16. Tài liệu chính thức

- [Spring Security API — ServerHttpSecurity.HttpBasicSpec](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html): custom entry point và failure handler cho Basic.
- [Spring Security API — ServerHttpSecurity.ExceptionHandlingSpec](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html): `authenticationEntryPoint` và `accessDeniedHandler`.
- [Spring Security API — ServerAuthenticationEntryPointFailureHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html): bridge từ authentication failure sang entry point.
- [Spring Framework — WebFlux Controller Advice](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-advice.html): phạm vi của `@RestControllerAdvice` và `@ExceptionHandler`.
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.error.include-*` và logging.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication response, account enumeration.
- [OWASP — Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): thông tin lỗi công khai vs chẩn đoán nội bộ.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): không ghi passwords, session IDs, access tokens và dữ liệu nhạy cảm.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): chuẩn JSON problem details khi API chọn sử dụng.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cấu hình security chain và authentication.

**Ghi nhớ:** Khi xử lý lỗi trong Spring Security reactive, **giữ đúng HTTP status**, trả **error code/message chung có chủ đích**, không phản chiếu `ex.getMessage()`, raw credentials, account state, token hay stack trace. Cấu hình bảo vệ tại **HTTP Basic entry point, access-denied handler, controller advice, Boot error handler và gateway**, đồng thời lọc log/APM. Test với **canary giả** và **các account case khác nhau** để đảm bảo error response không trở thành nguồn dữ liệu cho attacker.