# Thành phần phản hồi lỗi tương ứng trong Spring Security WebFlux

## 1. Mục tiêu bài học và phạm vi

Trong **Spring Security Servlet**, người học thường gặp `AuthenticationEntryPoint`, `AccessDeniedHandler`, `AuthenticationFailureHandler`, `ExceptionTranslationFilter` và các phương thức của `HttpSecurity`. Khi chuyển sang **Spring WebFlux**, tên và cách dùng không thể chỉ thay `HttpServletResponse` bằng một kiểu reactive: Spring Security có các **giao diện `Server...`**, các **`WebFilter`**, cấu hình `ServerHttpSecurity` và quy trình trả về `Mono<Void>`.

Bài học này trả lời câu hỏi: **thành phần nào chịu trách nhiệm tạo phản hồi khi truy cập chưa đăng nhập, đã đăng nhập nhưng thiếu quyền, hoặc đăng nhập thất bại trong WebFlux?** Đồng thời minh họa cách tạo status, redirect, JSON error an toàn và kiểm thử bằng `WebTestClient`.

Sau khi học, bạn có thể:

1. Ánh xạ chính xác các thành phần phản hồi lỗi từ Servlet sang WebFlux.
2. Phân biệt `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` và `ServerAuthenticationFailureHandler`; không dùng lẫn cho ba tình huống khác nhau.
3. Hiểu `ExceptionTranslationWebFilter` và `AuthenticationWebFilter` trong chuỗi bảo vệ request.
4. Cấu hình `.exceptionHandling(...)`, `.formLogin(...)`, `.httpBasic(...)` và Resource Server theo **Spring Security 6.5**.
5. Viết handler trả JSON qua `ServerWebExchange` **không blocking**, và biết khi nào không được thay header chuẩn `WWW-Authenticate`.
6. Tạo một Spring Boot WebFlux demo Java 17+ chạy được và kiểm tra 401/403/bảo vệ tài nguyên bằng `WebTestClient`.
7. Xác định ranh giới giữa **security-filter error**, **controller error**, lỗi hạ tầng và lỗi HTTP thông thường.
8. Tránh lộ thông tin về username, token, chi tiết exception và tránh các phản hồi khác biệt có thể bị dùng để dò tài khoản.

**Phạm vi:** Spring Boot 3.x + Spring Security 6.x, ứng dụng Reactive WebFlux với `spring-boot-starter-webflux`; ghi chú phiên bản 7.x ở phần sau. Ví dụ Servlet được đưa vào **chỉ để so sánh API**, không trộn hai loại security filter chain trong một ứng dụng.

## 2. Bản đồ tương ứng Servlet ↔ WebFlux

| Trách nhiệm | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Cấu hình HTTP Security | `HttpSecurity` | `ServerHttpSecurity` |
| Đối tượng cấu hình filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Dữ liệu HTTP request/response | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` chứa `ServerHttpRequest` / `ServerHttpResponse` |
| Khi chưa đăng nhập cần bắt đầu xác thực | `AuthenticationEntryPoint` | **`ServerAuthenticationEntryPoint`** |
| Khi đã xác thực nhưng không đủ quyền | `AccessDeniedHandler` | **`ServerAccessDeniedHandler`** |
| Khi một nỗ lực login thất bại | `AuthenticationFailureHandler` | **`ServerAuthenticationFailureHandler`** |
| Sau login thành công | `AuthenticationSuccessHandler` | `ServerAuthenticationSuccessHandler` |
| Chuyển lỗi security thành phản hồi | `ExceptionTranslationFilter` | **`ExceptionTranslationWebFilter`** |
| Xử lý authentication ở filter | `UsernamePasswordAuthenticationFilter` / các auth filters khác | **`AuthenticationWebFilter`** cùng converter/manager thích hợp |
| Lấy principal/auth theo ngữ cảnh | `SecurityContextHolder` (thường thread-bound) | `ReactiveSecurityContextHolder` (Reactor Context) |
| Quy tắc cho phép/không cho phép URL | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| Security test HTTP | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |
| Hàm trả kết quả của handler | Thường `void` và ghi vào servlet response | **`Mono<Void>`** phản ánh thao tác ghi response bất đồng bộ |

**Quy tắc về package:** trong WebFlux phần lớn các lớp phản hồi security nằm ở `org.springframework.security.web.server...`, không phải `org.springframework.security.web...` dành cho Servlet. Các class `HttpStatusServerEntryPoint`, `RedirectServerAuthenticationFailureHandler` hoặc `HttpStatusServerAccessDeniedHandler` có tên rất gần với bản Servlet nhưng **không cùng kiểu tham số**.

Ví dụ chữ ký giao diện WebFlux:

```java
// org.springframework.security.web.server.ServerAuthenticationEntryPoint
Mono<Void> commence(ServerWebExchange exchange,
                    AuthenticationException exception);

// org.springframework.security.web.server.authorization.ServerAccessDeniedHandler
Mono<Void> handle(ServerWebExchange exchange,
                  AccessDeniedException exception);

// org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler
Mono<Void> onAuthenticationFailure(WebFilterExchange webFilterExchange,
                                   AuthenticationException exception);
```

Đây là **chữ ký minh họa** (đã bỏ khai báo interface/import), không phải một class Java độc lập.

Tại sao `ServerAuthenticationFailureHandler` nhận `WebFilterExchange`? Nó được gọi từ authentication filter; wrapper mang **`ServerWebExchange` và `WebFilterChain`**. Bạn có thể lấy `webFilterExchange.getExchange()` để ghi response. Trong khi đó, entry point và access-denied handler hoạt động trực tiếp với `ServerWebExchange`.

## 3. Ba tình huống cần phân biệt

| Tình huống | Bối cảnh | Thành phần chính | Kết quả thông dụng |
| --- | --- | --- | --- |
| **Chưa đăng nhập** mà truy cập URL bảo vệ | Không có `Authentication` phù hợp | `ServerAuthenticationEntryPoint` | API: 401/challenge; browser form: redirect login |
| **Đã đăng nhập nhưng thiếu authority** | Có principal hợp lệ, thiếu quyền cần thiết | `ServerAccessDeniedHandler` | HTTP **403 Forbidden** |
| **Nộp credential để login nhưng sai** | Authentication filter chạy, manager trả `AuthenticationException` | `ServerAuthenticationFailureHandler` | Form: redirect `/login?error`; API: 401/challenge hoặc JSON |
| Login đúng | Authentication thành công | `ServerAuthenticationSuccessHandler` | Redirect hoặc tiếp tục theo cấu hình |
| Controller gặp lỗi nghiệp vụ | Đã vào handler/controller | WebFlux exception handling/application layer | 400/404/409/500 theo contract |
| Request bị CSRF protection từ chối | Access denied ở security layer | Handler/filter tương ứng với chính sách CSRF | Thường 403; không phải login password sai |

**401 và 403 là ý nghĩa giao thức, không phải tên class:**

- **401 Unauthorized** thường có nghĩa client **cần gửi/xác thực credential hợp lệ**. Với HTTP Basic và OAuth2 Bearer, HTTP challenge trong `WWW-Authenticate` có ý nghĩa đặc biệt.
- **403 Forbidden** thường có nghĩa principal đã được nhận diện hoặc request bị chính sách bảo mật chặn nhưng **không đủ quyền**.
- Với **HTML form**, người dùng chưa login thường thấy **302/303 redirect** đến trang đăng nhập thay vì JSON 401. Đây có thể là hành vi đúng của browser flow.
- Nếu API có bearer token **sai/hết hạn**, nó thường trả 401 theo xử lý token; token hợp lệ nhưng thiếu scope cần thiết thường trả 403 với metadata theo RFC 6750.
- Một lỗi **CSRF** là lỗi authorization/security của request, không mặc nhiên biến thành một login failure như username/password sai.

Không tạo một handler duy nhất trả HTTP 200 và `{success:false}` cho mọi lỗi; điều này khiến client và monitoring khó diễn giải, và có thể lẫn với login thành công.

## 4. `ExceptionTranslationWebFilter` nằm ở đâu?

Sơ đồ khái niệm của chuỗi WebFlux:

```text
HTTP request
    |
    v
WebFilterChainProxy / SecurityWebFilterChain
    |
    +-- AuthenticationWebFilter và các authentication filters
    |      |
    |      +-- authenticate thành công -> lưu security context phù hợp
    |      |
    |      `-- authenticate thất bại -> ServerAuthenticationFailureHandler
    |
    +-- ExceptionTranslationWebFilter
    |      |
    |      `-- xử lý AccessDeniedException phía dưới
    |             |
    |             +-- chưa đủ Authentication -> ServerAuthenticationEntryPoint
    |             |
    |             `-- Authentication hợp lệ nhưng thiếu quyền
    |                               -> ServerAccessDeniedHandler
    |
    +-- AuthorizationWebFilter -> kiểm tra authorizeExchange(...)
    |
    v
Handler/controller nếu được phép
```

Đây là **sơ đồ trách nhiệm**, không phải mô tả đầy đủ mọi filter hoặc thứ tự vật lý bất biến cho mọi phiên bản.

`ExceptionTranslationWebFilter` có các phương thức cấu hình:

```text
setAuthenticationEntryPoint(ServerAuthenticationEntryPoint)
setAccessDeniedHandler(ServerAccessDeniedHandler)
```

Nó giúp đổi lỗi phân quyền thành hành động thích hợp: **bắt đầu xác thực** hoặc **từ chối quyền**. Tuy nhiên, không nên hiểu nó là bộ `catch` cho **mọi** `AuthenticationException` trong ứng dụng. Một `AuthenticationWebFilter` có thể xử lý lỗi nộp credential bằng **failure handler riêng**.

Ví dụ:
1. `GET /api/admin` không có credential, policy cần authenticated: entry point.
2. `GET /api/admin` với user có `ROLE_USER` nhưng policy cần `ROLE_ADMIN`: access-denied handler.
3. `POST /login` với sai password: form login authentication failure handler.
4. `GET /api/data` gây `IllegalStateException` trong service: lỗi ứng dụng; không tự chuyển thành 401 vì có `exceptionHandling`.

## 5. `ServerAuthenticationEntryPoint`: bắt đầu xác thực khi cần

Giao diện:

```java
Mono<Void> commence(
    ServerWebExchange exchange, AuthenticationException exception);
```

Các implementation hay gặp:

| Class | Khi nào dùng? |
| --- | --- |
| `HttpStatusServerEntryPoint` | Trả status HTTP đơn giản, chẳng hạn 401 cho JSON API/SPA |
| `RedirectServerAuthenticationEntryPoint` | Redirect tới trang login trong browser flow |
| `HttpBasicServerAuthenticationEntryPoint` | Trả challenge HTTP Basic |
| `BearerTokenServerAuthenticationEntryPoint` | Trả challenge OAuth2 Bearer theo RFC 6750 |
| `DelegatingServerAuthenticationEntryPoint` | Chọn entry point dựa trên điều kiện `ServerWebExchangeMatcher` |

**Các package cần phân biệt:**

```java
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
```

Bản thân `HttpStatusServerEntryPoint` chỉ cung cấp **status**; nếu muốn response body JSON, cần handler tự viết vào `ServerHttpResponse` như mục 9.

### Thiếu đăng nhập khác sai mật khẩu

Giả sử người dùng chưa đăng nhập nhưng mở `/dashboard`: chưa có nỗ lực nhập username/password. Entry point có thể redirect đến trang login.

Nếu browser gửi password sai tới `/login`, **form login filter** đã chạy và phải gọi failure handler. Không nên chuyển mọi trường hợp này thành `ServerAuthenticationEntryPoint` rồi mất ý nghĩa của endpoint hoặc che khuất lý do nghiệp vụ.

Một số failure handler có thể **ủy quyền** cho entry point bằng adapter `ServerAuthenticationEntryPointFailureHandler` (mục 8). Đó là thao tác tùy biến **có chủ đích**, không có nghĩa hai interface giống nhau.

## 6. `ServerAccessDeniedHandler`: authenticated nhưng thiếu quyền

Giao diện:

```java
Mono<Void> handle(
    ServerWebExchange exchange, AccessDeniedException exception);
```

Implementation đơn giản:

```java
new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)
```

Import:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;
```

Nó chỉ đặt HTTP status (thường 403). Muốn body JSON, viết custom handler dùng `ServerWebExchange`.

Trong OAuth2 Resource Server, **`BearerTokenServerAccessDeniedHandler`** có quy tắc đặc biệt: nếu xác định request có một OAuth2 authentication hợp lệ nhưng không đủ scope, nó có thể thêm challenge với `insufficient_scope` theo RFC 6750. Đừng tự thay nó bằng JSON 403 thuần rồi làm mất thông tin mà OAuth2 client cần.

**Authorization không đồng nghĩa xác thực:** một token JWT được giải mã và xác minh chữ ký nhưng thiếu `SCOPE_orders:read` thường thuộc nhánh thiếu quyền, không phải failure nộp password. Ngược lại, chữ ký JWT sai hay token hết hạn không bao giờ được coi là principal authenticated.

## 7. `ServerAuthenticationFailureHandler`: lỗi khi có nỗ lực login

Giao diện:

```java
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception);
```

Implementation thường dùng:

- `RedirectServerAuthenticationFailureHandler("/login?error")`: redirect đến trang nhập lại credential.
- `ServerAuthenticationEntryPointFailureHandler(entryPoint)`: chuyển từ failure handler sang entry point.
- Một lambda `ServerAuthenticationFailureHandler` tự trả JSON/status nếu API login không dùng redirect.

**Đúng vị trí cấu hình:**

```java
// Chèn vào DSL ServerHttpSecurity của ứng dụng WebFlux.
.formLogin(form -> form
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler("/login?error")
    )
)
```

Imports:

```java
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
```

Nếu dùng default form login, Spring Security WebFlux thường đã redirect về `/login?error` khi lỗi password. Không cần đăng ký riêng một handler giống hệt mặc định trừ khi bạn muốn điều chỉnh UX, thống nhất error contract hoặc audit.

**Các giao thức khác có filter riêng:** `.httpBasic(...)`, `.oauth2Login(...)`, `.oneTimeTokenLogin(...)` trong WebFlux có các hook failure cụ thể theo version. Khi cấu hình, phải xác định **thực sự request đang đi qua filter/chain nào**. Gắn custom failure handler cho form login không tự thay cách phản hồi của bearer token hoặc authorization failure từ API.

## 8. Chuyển một entry point thành failure handler

Một API đôi khi muốn mọi **nỗ lực đăng nhập thất bại** đều trả một JSON/status 401 giống entry point. Spring Security cung cấp adapter:

```java
ServerAuthenticationEntryPoint entryPoint =
    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

ServerAuthenticationFailureHandler failureHandler =
    new ServerAuthenticationEntryPointFailureHandler(entryPoint);
```

Imports:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
```

Đoạn trên là **snippet trong method**. Khi `AuthenticationWebFilter` gọi `failureHandler.onAuthenticationFailure(...)`, adapter gọi `entryPoint.commence(...)` và trả `Mono<Void>`.

Đây là trường hợp **có thể tái sử dụng hành vi**, không làm mất sự khác nhau của ba giao diện. Không tạo vòng gọi đệ quy (entry point gọi lại failure handler) hoặc tiếp tục filter chain sau khi response đã commit.

## 9. Ví dụ WebFlux tự trả JSON lỗi bằng `Mono<Void>`

Khi xây API **không cần challenge HTTP Basic/Bearer**, có thể muốn các response:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{"error":"UNAUTHENTICATED"}
```

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"error":"ACCESS_DENIED"}
```

Trong WebFlux, bạn không ghi response bằng `response.getWriter().write(...)` như Servlet. Bạn lấy `ServerHttpResponse`, tạo `DataBuffer` và **trả `Mono<Void>`** để hệ thống đăng ký thực thi.

File `src/main/java/example/reactive/JsonSecurityErrorHandlers.java`:

```java
package example.reactive;

import java.nio.charset.StandardCharsets;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class JsonSecurityErrorHandlers {

    private JsonSecurityErrorHandlers() {}

    private static Mono<Void> send(
            ServerWebExchange exchange, HttpStatus status, String code) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().set("Cache-Control", "no-store");

        // Chỉ nhận error code hằng số do server định nghĩa.
        byte[] body = ("{\"error\":\"" + code + "\"}")
            .getBytes(StandardCharsets.UTF_8);
        response.getHeaders().setContentLength(body.length);

        return response.writeWith(
            Mono.fromSupplier(() -> response.bufferFactory().wrap(body))
        );
    }

    public static ServerAuthenticationEntryPoint unauthenticated() {
        return (exchange, ex) ->
            send(exchange, HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED");
    }

    public static ServerAccessDeniedHandler denied() {
        return (exchange, ex) ->
            send(exchange, HttpStatus.FORBIDDEN, "ACCESS_DENIED");
    }

    public static ServerAuthenticationFailureHandler invalidCredentials() {
        return (filterExchange, ex) ->
            send(filterExchange.getExchange(),
                 HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS");
    }
}
```

**Điều kiện để dùng đúng:**
- Class dùng **Java 17**, Spring WebFlux/Spring Security reactive, Reactor đã có trong starter.
- Không gọi `.block()`, `Thread.sleep(...)`, `getWriter()` hoặc `HttpServletResponse`. Việc tạo buffer và trả `Mono` phù hợp reactive runtime.
- Hàm `send` ở đây chỉ dành cho error code **hằng số của server**; nếu đưa raw `exception.getMessage()` hoặc input người dùng vào JSON, phải xử lý escaping/giới hạn và loại bỏ thông tin nhạy cảm.
- Status/headers phải được đặt **trước** khi body được ghi. Nếu response đã committed (ví dụ lỗi phát sinh sau khi stream một phần nội dung), bạn không thể bảo đảm thay status/body; cần xử lý lỗi ở đúng tầng và trước khi response commit.
- `Content-Length` dùng độ dài **byte UTF-8**, không phải `String.length()`; với chuỗi ASCII trong ví dụ, kết quả trùng nhưng đừng suy rộng cho tiếng Việt.
- `Mono.fromSupplier` tạo `DataBuffer` khi publisher được subscribe; tránh tạo buffer thô từ trước rồi bỏ quên trong nhánh lỗi.
- **Không** áp dụng JSON handler này trực tiếp thay cho `BearerTokenServerAuthenticationEntryPoint`/`BearerTokenServerAccessDeniedHandler` nếu client cần header OAuth2 `WWW-Authenticate`. Hãy giữ giao thức, hoặc thiết kế một wrapper **bảo toàn header/status chuẩn**.
- Với form HTML dùng redirect, JSON 401 có thể không phù hợp UX; hãy chọn handler theo route/media và client contract.

### Gắn custom JSON handlers vào `ServerHttpSecurity`

Snippet **thay thế** `exceptionHandling(...)` trong một `SecurityWebFilterChain` WebFlux:

```java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(
        JsonSecurityErrorHandlers.unauthenticated()
    )
    .accessDeniedHandler(
        JsonSecurityErrorHandlers.denied()
    )
);
```

Với form-login failure:

```java
http.formLogin(form -> form
    .authenticationFailureHandler(
        JsonSecurityErrorHandlers.invalidCredentials()
    )
);
```

Đây là **hai cấu hình minh họa** cho một web app SPA/API có thể dùng cookie/session; cần policy CSRF, session và login path nhất quán. **Không** copy cùng lúc tất cả snippet vào cấu hình Basic/Bearer demo ở mục 10, vì sẽ thay đổi header/challenge và contract mà demo đang kiểm thử.

## 10. Demo hoàn chỉnh: WebFlux HTTP Basic với 401 và 403 chuẩn

Ví dụ này dùng Spring Boot **3.x** + Spring Security **6.x** + Java 17+. Nó thật sự xác thực tài khoản demo qua HTTP Basic và trả status đúng khi client không đăng nhập hoặc đăng nhập thiếu quyền. Phần JSON custom ở mục 9 là một **phương án thay thế**, không bật trong demo này.

### 10.1. Gradle dependencies

Trong `build.gradle` của một dự án Spring Boot 3.x đã có plugin/bom quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Không thêm `spring-boot-starter-web`** vào demo nếu bạn muốn ứng dụng thuần WebFlux với reactive server. Khi có cả MVC và WebFlux trên classpath, Spring Boot thường ưu tiên mô hình Servlet/MVC; việc thêm `SecurityWebFilterChain` rồi tưởng mình đang dùng WebFlux có thể gây lỗi cấu hình/kiểm thử. Trong project WebFlux thật, dùng `@EnableWebFluxSecurity` và `ServerHttpSecurity`.

### 10.2. Security config

File `src/main/java/example/reactive/ReactiveSecurityConfig.java`:

```java
package example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/profile").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .exceptionHandling(exceptions -> exceptions
                // Giữ WWW-Authenticate: Basic ... cho HTTP Basic clients.
                .authenticationEntryPoint(
                    new HttpBasicServerAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new HttpStatusServerAccessDeniedHandler(
                        HttpStatus.FORBIDDEN
                    )
                )
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-password-for-local-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-password-for-local-demo"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

**Giải thích:**

- `SecurityWebFilterChain` là bean bảo vệ request của WebFlux, không phải `SecurityFilterChain` Servlet.
- `.authorizeExchange` áp dụng rule theo thứ tự; `/api/admin` cần `ROLE_ADMIN`. User `reader` chỉ có `ROLE_USER`, nên request tới admin phải **403** sau khi xác thực.
- `.httpBasic(withDefaults())` bật HTTP Basic cho demo; `.formLogin(...::disable)` tắt browser form login để tránh redirect không mong muốn trong ví dụ API.
- `.exceptionHandling` chọn **Basic entry point** để giữ `WWW-Authenticate`; access-denied handler trả `403`.
- `MapReactiveUserDetailsService` là **reactive** store cho demo. Ứng dụng thật dùng repository phù hợp, password encoder mạnh, rate limit và không lưu password demo trong source.
- `BCryptPasswordEncoder` phục vụ minh họa Java, không có nghĩa API Basic phù hợp mọi kiến trúc hiện đại. Thực tế thường chọn OAuth2 Bearer/mTLS/workload identity tùy use case.
- Đừng dùng Basic credentials trên HTTP không mã hóa, URL hoặc query string; bắt buộc HTTPS ở production.
- `CSRF` mặc định vẫn bật. Demo chỉ có GET endpoints; nếu thêm POST/PUT/DELETE, phải thiết kế CSRF theo loại client/authentication, không tự vô hiệu hóa toàn hệ thống.

### 10.3. Controller và main application

File `src/main/java/example/reactive/ReactiveDemoController.java`:

```java
package example.reactive;

import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveDemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return Mono.just("profile-ok");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

File `src/main/java/example/reactive/ReactiveErrorApplication.java`:

```java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveErrorApplication.class, args);
    }
}
```

Chạy:

```bash
./gradlew bootRun
```

Khi project ở máy local có Java 17+, dùng HTTP `localhost` **chỉ để demo**:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/admin
curl -i -u reader:reader-password-for-local-demo \
    http://localhost:8080/api/admin
curl -i -u admin:admin-password-for-local-demo \
    http://localhost:8080/api/admin
```

**Kết quả kỳ vọng:**

| Request | Kết quả |
| --- | --- |
| `GET /public`, không auth | HTTP 200, body `public-ok` |
| `GET /api/admin`, không auth | HTTP 401, `WWW-Authenticate` bắt đầu bằng `Basic` |
| `GET /api/admin` với `reader` | HTTP 403, không thực thi controller admin |
| `GET /api/admin` với `admin` | HTTP 200, body `admin-ok` |
| `GET /api/profile` với `reader` | HTTP 200, body `profile-ok` |
| Login bằng password sai | HTTP 401/challenge, không tạo quyền |

Kết quả ở bảng là **hành vi dự kiến từ cấu hình**; chưa có kết quả chạy thực tế trong bài. `curl -u` có thể làm lộ password demo trong history/process list; chỉ dùng credential giả ở môi trường cô lập. Trong môi trường thật, dùng secret quản lý phù hợp.

## 11. Kiểm thử bằng `WebTestClient`

WebFlux nên được kiểm thử tại ranh giới HTTP bằng `WebTestClient`, không dùng `MockMvc` cho một reactive `SecurityWebFilterChain`. Dưới đây là test của demo mục 10, **không** thay thế integration test OAuth2 hoặc SSO nếu hệ thống thực tế dùng các cơ chế đó.

File `src/test/java/example/reactive/ReactiveSecurityResponseTest.java`:

```java
package example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveSecurityResponseTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousCannotAccessAdmin() {
        client.get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists("WWW-Authenticate");
    }

    @Test
    void readerHasAuthenticationButNotAdminRole() {
        client.get()
            .uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-password-for-local-demo"
            ))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminMayAccessAdmin() {
        client.get()
            .uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-password-for-local-demo"
            ))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void publicEndpointIsAccessibleAnonymously() {
        client.get()
            .uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-ok");
    }
}
```

Lệnh:

```bash
./gradlew test --tests example.reactive.ReactiveSecurityResponseTest
```

Tại project có các dependencies tương thích, bốn test kỳ vọng pass. Chúng kiểm tra:
- 401 **và challenge** khi chưa đăng nhập.
- 403 khi đăng nhập đúng nhưng không có role.
- 200 khi có quyền.
- 200 cho URL public.

**Nếu dùng `SecurityMockServerConfigurers.mockUser(...)` trong unit/mock test**: đó là cách tạo Authentication **giả** để test authorization, không kiểm chứng việc xác thực password hoặc JWT thật. Demo trên cố ý gửi Basic credentials qua test server để đi qua authentication pipeline của ứng dụng.

### WebTestClient kiểm thử `mockUser` khi không muốn gửi credential

Snippet dưới đây minh họa test với Security test configurer:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Bên trong test đã có WebTestClient client gắn Spring Security.
client.mutateWith(mockUser("reader").roles("USER"))
    .get().uri("/api/admin").exchange()
    .expectStatus().isForbidden();
```

Trong setup có thể cần `WebTestClient.bindToApplicationContext(context).apply(springSecurity()).build()` để tích hợp các security mock configurers; không mặc định mọi WebTestClient thuần túy đều hỗ trợ `mockUser` mà không thêm `spring-security-test`.

## 12. Phản hồi HTML form: redirect thay vì JSON

Một app WebFlux có trang login cho trình duyệt thường muốn:
- `GET /private` khi chưa login: redirect tới `/login`.
- `POST /login` khi password sai: redirect `/login?error`.
- `POST /login` thành công: redirect về trang thích hợp.

Ví dụ cấu hình **riêng** cho browser flow:

```java
http
    .authorizeExchange(exchange -> exchange
        .pathMatchers("/login", "/public").permitAll()
        .anyExchange().authenticated()
    )
    .formLogin(form -> form
        .loginPage("/login")
        .authenticationFailureHandler(
            new RedirectServerAuthenticationFailureHandler(
                "/login?error"
            )
        )
    )
    .exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(
            new RedirectServerAuthenticationEntryPoint("/login")
        )
    );
```

Imports cần thiết:

```java
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;
```

**Đây là snippet chèn vào `ServerHttpSecurity`**, không phải một second `SecurityWebFilterChain` mặc nhiên có thể đặt cạnh demo Basic. Khi dùng `.loginPage("/login")`, ứng dụng phải thực sự có trang `GET /login`, form và CSRF token; Spring Security không còn tự tạo trang login mặc định cho đường tùy chỉnh. Người dùng chưa login và người dùng nhập password sai đều có thể redirect, nhưng **nguyên nhân và hook xử lý khác nhau**.

Nếu thay handler redirect bằng JSON chỉ vì frontend là SPA, cần chủ động xử lý `fetch`/CSRF/session cookie, đồng thời tránh redirect loop khi request API nhận HTML login page thay vì JSON.

## 13. Reactive OAuth2 Resource Server: giữ `WWW-Authenticate`

Một sai lầm thường gặp: thêm global JSON entry point cho tất cả `/api/**`, làm mất `WWW-Authenticate: Bearer ...` và các thông tin lỗi mà OAuth2 client kỳ vọng.

Spring Security WebFlux có hai class chuyên biệt:

```java
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.server.BearerTokenServerAccessDeniedHandler;
```

- **`BearerTokenServerAuthenticationEntryPoint`**: kích hoạt phản hồi authentication challenge theo **RFC 6750**, gồm thông tin về bearer và lỗi token khi phù hợp.
- **`BearerTokenServerAccessDeniedHandler`**: khi xác nhận authentication hợp lệ nhưng thiếu scope, phản hồi access denied theo RFC, thường có `insufficient_scope`.
- Với JWT hoặc opaque token, auth failure có thể xảy ra **ngay trong authentication filter**; dùng default Resource Server wiring hoặc custom handler **tôn trọng chuẩn**.

Ví dụ cấu hình JWT **thay cho Basic demo**:

```java
http
    .authorizeExchange(exchange -> exchange
        .pathMatchers("/api/public").permitAll()
        .pathMatchers("/api/reports/**")
            .hasAuthority("SCOPE_reports:read")
        .anyExchange().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        org.springframework.security.config.Customizer.withDefaults()
    ))
    .exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(
            new BearerTokenServerAuthenticationEntryPoint()
        )
        .accessDeniedHandler(
            new BearerTokenServerAccessDeniedHandler()
        )
    );
```

Cấu hình JWT thực tế cần `spring-boot-starter-oauth2-resource-server`, `ReactiveJwtDecoder` đúng issuer/JWKs, chữ ký, `aud`, `exp`, `nbf` và security constraints. Đây **chỉ** là snippet security chain; không thể chạy end-to-end nếu chưa có Authorization Server/issuer phù hợp.

Sự khác nhau về phản hồi thường là:

| Tình trạng Bearer token | Hướng xử lý thông dụng |
| --- | --- |
| Không có token tới endpoint bảo vệ | 401 với `WWW-Authenticate: Bearer` |
| Token bị sửa hoặc hết hạn | 401 `invalid_token` theo thông tin error phù hợp |
| Token hợp lệ, thiếu scope | 403, có thể `insufficient_scope` |
| Token hợp lệ, đủ scope | Request đi vào handler, không đi vào error handler |
| IdP/decoder gặp lỗi hạ tầng | Không tự gán “user sai mật khẩu”; cần chiến lược 5xx/availability an toàn |

**Không** diễn giải `401` trong Resource Server giống `UsernameNotFoundException` của form login; bearer validation có hợp đồng giao thức riêng. Cũng không rò raw token hoặc toàn bộ exception vào JSON body/`error_description`.

## 14. Nhiều SecurityWebFilterChain và chọn response theo route

Có thể có:
- `/api/**`: JWT, phản hồi JSON và Bearer challenge.
- `/ui/**`: session cookie, form login, redirect.
- `/actuator/health`: endpoint công khai có giới hạn hoặc policy riêng.
- `/internal/**`: xác thực máy chủ/đặc thù nội bộ.

Trong WebFlux, việc chọn chain phụ thuộc `securityMatcher` và thứ tự (`@Order`). Mọi security configurer liên quan đến response lỗi cũng thuộc **chain đã chọn**, không phải cấu hình toàn cầu có thể áp dụng tùy ý mọi route.

Ví dụ **sơ đồ**, không phải project đầy đủ:

```text
@Order(1) API chain:
   securityMatcher("/api/**")
   oauth2ResourceServer(jwt)
   exceptionHandling(Bearer entry point, Bearer denied handler)

@Order(2) UI chain:
   securityMatcher("/ui/**")
   formLogin(...)
   exceptionHandling(redirect entry point, denied page)

Catch-all:
   default deny unless explicitly allowed
```

Nếu `/api/reports` lọt vào UI chain, API client có thể nhận `302 /login` thay vì `401 Bearer`. Ngược lại, `/ui/profile` rơi vào JWT chain có thể trả JSON 401 thay vì trang login. Cả hai có thể phá UX hoặc tạo bypass policy. Kiểm thử **matcher/chain** cho từng route nhạy cảm.

Nếu ứng dụng vừa có HTML lẫn API, ưu tiên **chia chain theo route có ownership rõ ràng** hơn là đoán dựa vào header `Accept` do client tự khai. Khi sử dụng conditional entrypoint, đừng để một header client-controlled thay đổi yêu cầu **xác thực hoặc phân quyền**; nó chỉ được phép ảnh hưởng hình thức phản hồi.

## 15. Không nhầm `@RestControllerAdvice`, `ErrorWebExceptionHandler` và security handlers

Trong WebFlux, lỗi có thể đến từ các tầng:

| Tầng lỗi | Ví dụ | Nơi xử lý đúng |
| --- | --- | --- |
| **Security WebFilter** | Chưa đăng nhập, thiếu role, form login sai | `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` / `ServerAuthenticationFailureHandler` |
| **Controller/service** | Request JSON sai, validation, lỗi nghiệp vụ | `@RestControllerAdvice`, `@ExceptionHandler`, WebFlux app exception mappings |
| **Global WebFlux error** | Lỗi không được controller xử lý | `ErrorWebExceptionHandler` / Spring Boot error infrastructure |
| **Upstream/network** | Gateway timeout, DNS, IdP unavailable | Hạ tầng/gateway/đường error phù hợp; không tự sửa thành 401 |
| **CSRF** | POST thiếu CSRF token trong cookie session flow | Security policy; thường 403 hoặc handler liên quan |

`@RestControllerAdvice` thường chỉ thấy exception **sau khi request đã được chuyển vào tầng controller**. Filter security chặn request trước controller nên exception chưa chắc đi tới advice. Nếu cố xử lý bằng `@ControllerAdvice` mà request vẫn 302/401/403 khác kỳ vọng, hãy xem **chuỗi security WebFilter**.

Tương tự, `ErrorWebExceptionHandler` không được dùng để làm lại toàn bộ semantics của Spring Security. Nó không thay thế `ServerAuthenticationEntryPoint` hay `ServerAuthenticationFailureHandler`.

### Lỗi hệ thống khác AuthenticationException

Ví dụ:
- `AuthenticationException`: credential/token hoặc quá trình authentication không hợp lệ.
- `AccessDeniedException`: policy authorization từ chối.
- `DataAccessResourceFailureException`: database unavailable.
- `TimeoutException`: gọi IdP/remote server quá deadline.
- `IllegalArgumentException`: request hoặc code không hợp lệ.

Không `onErrorResume(Throwable.class, e -> response401())` cho cả chuỗi reactive: một backend lỗi sẽ bị hiểu nhầm thành sai credential, làm che monitoring và có thể tạo đường bypass logic. Chỉ translate đúng loại lỗi, tại vị trí phù hợp, giữ error signal cho hệ thống khi không thể an toàn viết response.

## 16. Reactive programming: vì sao phải trả `Mono<Void>`?

Các reactive handlers không nên chặn thread bằng I/O đồng bộ:

```java
// SAI trong event loop: network/database I/O blocking.
Thread.sleep(500);
mailService.sendBlockingEmail(...);
return Mono.empty();
```

`ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` và `ServerAuthenticationFailureHandler` đều trả `Mono<Void>` đại diện cho **hoàn tất việc ghi phản hồi**.

Một handler chuẩn có thể chỉ đặt status:

```java
ServerAuthenticationEntryPoint entryPoint = (exchange, ex) -> {
    exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
    return exchange.getResponse().setComplete();
};
```

Đây là **snippet trong method** (có import `ServerAuthenticationEntryPoint`, `HttpStatus`). Nếu viết body, trả publisher từ `response.writeWith(...)` như mục 9. Đừng gọi `.subscribe()` thủ công rồi lập tức trả `Mono.empty()`: response có thể commit sai thứ tự hoặc bị bỏ qua khi request kết thúc.

### Tình trạng response đã commit

HTTP status và headers thường phải được quyết định **trước byte đầu tiên của body**. Nếu đã stream data rồi phát hiện thiếu quyền:
- Bạn không thể biến một response đã gửi 200 + body một phần thành response 403 hoàn chỉnh một cách đáng tin.
- Hãy thực hiện authentication/authorization **trước** khi bắt đầu streaming dữ liệu nhạy cảm.
- Với SSE/streaming, sau khi subscription đã bắt đầu, lỗi phát sinh cần có giao thức event/error và đóng stream phù hợp.
- Không đẩy exception class, token, session ID hoặc private data vào body lỗi.

## 17. Authentication và SecurityContext trong Reactor

Trong Servlet, nhiều ví dụ đọc:

```java
SecurityContextHolder.getContext().getAuthentication();
```

Trong WebFlux, `SecurityContext` được truyền qua **Reactor Context**, không dựa đơn thuần vào `ThreadLocal`. Nếu viết custom error handler cần tham chiếu principal, dùng reactive access phù hợp:

```java
ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .defaultIfEmpty("anonymous");
```

Import:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

Đây là **snippet tạo `Mono<String>`**, không phải chương trình hoàn chỉnh. Trong error handler, đôi khi không có authenticated context; đừng `block()` để lấy username và đừng yêu cầu principal tồn tại trong nhánh chưa authenticated.

Bảo mật vận hành: log thông tin vừa đủ từ server (trace ID, endpoint, reason code nội bộ) mà không ghi password, JWT, session cookie, raw OAuth2 error hoặc toàn bộ stack trace vào response công khai.

## 18. Giảm rò rỉ thông tin và dò sự tồn tại của tài khoản

Một API login trả:
- `UNKNOWN_USER` khi username không có.
- `BAD_PASSWORD` khi username tồn tại nhưng password sai.

Có thể biến thành **account enumeration oracle**. Dùng `ServerAuthenticationFailureHandler` để chuẩn hóa **public response** như `INVALID_CREDENTIALS` cho các trường hợp không nên phân biệt trước khi chứng minh quyền sở hữu.

Không chỉ đồng nhất JSON body; cần cân nhắc:
- HTTP status, `Location`, `WWW-Authenticate`, `Set-Cookie`.
- Thời gian xử lý `ReactiveUserDetailsService`/password hash.
- Account locked/disabled/expired; đặc biệt sau khi thực hiện custom status mapping.
- Rate limit có khác biệt theo username tồn tại hay không.
- MFA enrollment, SSO/home-realm discovery và recovery endpoints.
- Không biến lỗi IdP/database hỏng thành “username sai” khi cần 5xx/giám sát.

Cẩn thận: **cùng response trên login failure khác với việc giấu lỗi giao thức Bearer**. OAuth2 clients có quyền mong đợi `invalid_token`/`insufficient_scope` và các challenge RFC 6750. Hãy chuẩn hóa trong giới hạn protocol và threat model của từng luồng, không dùng một universal JSON handler.

### So sánh thời gian phản hồi

Trong reactive application, một nhánh có gọi password hash, nhánh không có có thể gây timing side channel. Không chữa bằng `Thread.sleep` trong event loop; dùng authentication provider chuẩn và kiểm tra `ReactiveUserDetailsService`/encoder. Nếu phải gọi nguồn dữ liệu blocking, cách tốt nhất là dùng driver/reactive API không chặn; hoặc chuyển I/O blocking sang bounded scheduler có giới hạn và cân nhắc capacity. Không dùng `.block()` trong handler bảo mật.

## 19. Kiểm thử kết hợp HTTP contract và đường filter

Ma trận tối thiểu cho ứng dụng WebFlux:

| Case | HTTP/handler mong đợi |
| --- | --- |
| Anonymous mở route bảo vệ trong API Basic | `ServerAuthenticationEntryPoint` → 401 `WWW-Authenticate: Basic` |
| Anonymous mở route bảo vệ trong HTML form | Entry point → redirect login |
| User authenticated thiếu role | `ServerAccessDeniedHandler` → 403 |
| User password sai ở form | `ServerAuthenticationFailureHandler` → redirect lỗi hoặc JSON 401 |
| JWT sai chữ ký/hết hạn | Resource Server authentication error → 401 Bearer theo protocol |
| JWT hợp lệ thiếu scope | Resource Server denied → 403, `insufficient_scope` khi phù hợp |
| Token đủ scope | Controller chạy bình thường |
| POST thiếu CSRF trong session/cookie flow | 403/security-denied theo policy |
| Controller ném exception nghiệp vụ | Application/controller error response, không tự là 401 |
| Server DB/IdP timeout | Xử lý lỗi hạ tầng, không giả mạo sai password |
| JSON body tùy chỉnh | `Content-Type`, `Cache-Control`, status và body khớp contract |
| Response đã committed | Không ghi thêm status/body hoặc leak thông tin |
| Có hai security chains | Mọi request được match vào chain/handler đúng |
| User có status locked/disabled | Public login response không tiết lộ account existence |
| Header Accept bị sửa | Không làm thay đổi **yêu cầu xác thực/authorization** |

### Những kiểm thử hay bị hiểu sai

- `WebTestClient.mutateWith(mockUser())` cho phép giả lập principal, **không** chứng minh password/JWT verifier đã chạy.
- Một `@WebFluxTest` chỉ dựng controller có thể không nạp toàn bộ filter chain hoặc authentication backend như production.
- Status 401 không đủ với Bearer/Basic; hãy kiểm tra **`WWW-Authenticate`**, realm/scopes khi có contract.
- Mock decoder bằng token giả có thể thử policy/authorization nhưng **không** chứng minh signature/issuer/audience verification.
- Một test HTTP Basic có password sai không xác minh failure handler của **form login** nếu form login đã bị disabled.
- Unit test `JsonSecurityErrorHandlers.send` không xác minh endpoint nào đang sử dụng handler; cần integration test ở đúng chain.

## 20. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân phổ biến | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy `AuthenticationEntryPoint` khi dùng WebFlux | Import nhầm Servlet interface | Dùng `ServerAuthenticationEntryPoint` |
| Cố trả `void` từ reactive error handler | Copy code Servlet | Trả `Mono<Void>` từ `setComplete`/`writeWith` |
| API client nhận `302 /login` thay vì 401 | Form-login/default entrypoint hoặc chọn sai chain | Kiểm tra `securityMatcher`, thứ tự chain và entry point |
| API HTTP Basic trả 401 nhưng thiếu challenge | Ghi đè Basic entry point bằng `HttpStatusServerEntryPoint` | Giữ `HttpBasicServerAuthenticationEntryPoint` |
| JWT invalid trả 401 nhưng không có `WWW-Authenticate: Bearer` | Ghi đè Bearer entry point bằng JSON generic | Dùng `BearerTokenServerAuthenticationEntryPoint` |
| Token hợp lệ thiếu scope nhưng nhận JSON 401 | Đánh đồng authorization denied với authentication failure | Sửa `ServerAccessDeniedHandler` và rule |
| Login form sai password vẫn redirect dù đã sửa accessDeniedHandler | Lỗi nằm trong `AuthenticationWebFilter` | Cấu hình `formLogin.authenticationFailureHandler` |
| `@RestControllerAdvice` không bắt lỗi security | Request chưa vào controller | Cấu hình security handlers, không chỉ controller advice |
| App chạy MVC thay vì WebFlux | Có `spring-boot-starter-web` cạnh webflux | Kiểm tra `WebApplicationType` và dependency tree |
| `mockUser` test pass nhưng HTTP Basic thật fail | Test đã bỏ qua password verification | Thêm integration test với credentials thực trong môi trường test |
| `block()` khiến request treo/độ trễ tăng | I/O blocking trên Netty event loop | Dùng reactive publisher và scheduler phù hợp |
| Thông báo login khác theo username tồn tại | Failure handler trả raw exception | Chuẩn hóa public response, log reason nội bộ |
| Lỗi 500 bị biến thành 401 | `onErrorResume` quá rộng | Chỉ map security exceptions; giữ lỗi hạ tầng rõ ràng |
| Response đã commit rồi handler cố ghi 403 | Authorization diễn ra quá muộn hoặc streaming sai | Kiểm tra security trước khi stream |
| Cấu hình entrypoint tùy biến chạy không đúng | Có nhiều WebFilter chains/DSL khác override | Rà order/matcher và test theo HTTP flow |

## 21. Ghi chú theo phiên bản

| Phiên bản | Điều cần ghi nhớ |
| --- | --- |
| **Spring Security 5.x** | WebFlux security đã có các thành phần `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, `ServerAuthenticationFailureHandler` |
| **Spring Security 6.x / Spring Boot 3.x** | Dùng Java 17+, lambda DSL của `ServerHttpSecurity` và `SecurityWebFilterChain`; kiểm tra chính xác Javadoc 6.x |
| **Từ Spring Security 6.1** | Nhiều API cấu hình no-arg chained `.exceptionHandling()`/`.httpBasic()` được deprecated; ưu tiên `Customizer`/lambda |
| **Spring Security 7.x / Spring Boot 4.x** | API chuyên biệt reactive tiếp tục tồn tại; rà migration/deprecation và các tùy biến authentication/authorization theo minor |
| **Servlet khác Reactive** | Không dùng `HttpSecurity`, `SecurityFilterChain`, `HttpServletResponse` và `ExceptionTranslationFilter` Servlet thay cho WebFlux |

Đặc biệt, chỉ vì một lớp có tên gần giống `HttpStatusEntryPoint` không có nghĩa nó dành cho WebFlux. `HttpStatusEntryPoint` thuộc Servlet; `HttpStatusServerEntryPoint` thuộc WebFlux.

## 22. Câu hỏi tự kiểm tra

**Câu 1:** Trong WebFlux, người dùng chưa login mở `/api/private`. Chọn handler nào?

**Đáp:** `ServerAuthenticationEntryPoint`, thông qua exception translation/entrypoint của chain. Với API thường trả 401/challenge; với browser HTML có thể redirect login.

**Câu 2:** Người dùng đã login nhưng thiếu `ROLE_ADMIN`. Chọn handler nào?

**Đáp:** `ServerAccessDeniedHandler`, thường 403. Không coi đây là password sai.

**Câu 3:** Người dùng gửi sai password ở `POST /login`. Vì sao `ServerAccessDeniedHandler` không nhất thiết chạy?

**Đáp:** Lỗi xảy ra **ngay trong authentication attempt**, thường do `AuthenticationWebFilter` gọi `ServerAuthenticationFailureHandler`.

**Câu 4:** `ServerAuthenticationEntryPointFailureHandler` làm gì?

**Đáp:** Adapter cho phép dùng một `ServerAuthenticationEntryPoint` làm `ServerAuthenticationFailureHandler`.

**Câu 5:** Muốn gửi JSON từ handler reactive, có dùng `HttpServletResponse#getWriter()` không?

**Đáp:** Không. Dùng `ServerWebExchange`, `ServerHttpResponse.writeWith(Publisher<DataBuffer>)` và trả `Mono<Void>`.

**Câu 6:** Vì sao thay `BearerTokenServerAuthenticationEntryPoint` bằng JSON 401 thuần có thể sai?

**Đáp:** Vì có thể làm mất header/challenge `WWW-Authenticate` mà OAuth2 client cần để xử lý `invalid_token`/chuẩn RFC 6750.

**Câu 7:** Vì sao response `401` cho một `IllegalStateException` trong service có thể không đúng?

**Đáp:** Đó không phải bằng chứng credential sai; cần xử lý lỗi ứng dụng/hạ tầng theo tầng thích hợp và không che sự cố dưới dạng authentication failure.

**Câu 8:** `@RestControllerAdvice` có thay thế cấu hình `.exceptionHandling(...)` không?

**Đáp:** Không. Lỗi Spring Security có thể được xử lý trong WebFilter trước khi controller chạy.

## 23. Tóm tắt

Ba giao diện quan trọng nhất cho **phản hồi xác thực/phân quyền trong WebFlux** là:

- **`ServerAuthenticationEntryPoint`** — khi cần bắt đầu xác thực hoặc xử lý request chưa có Authentication thích hợp.
- **`ServerAccessDeniedHandler`** — khi request đã có Authentication nhưng không đủ quyền.
- **`ServerAuthenticationFailureHandler`** — khi một quá trình authentication (form/Basic/OAuth2 login hoặc filter tùy chỉnh) thất bại.

`ExceptionTranslationWebFilter` kết nối các thất bại authorization với entry point/denied handler. `AuthenticationWebFilter` có failure/success handlers cho quá trình login. Các thành phần dùng `ServerWebExchange`, `Mono<Void>` và Reactor, thay vì `HttpServletRequest`/`HttpServletResponse`/`void` trong Servlet.

Hãy cấu hình qua `ServerHttpSecurity.exceptionHandling(...)` và DSL của cơ chế authentication tương ứng, giữ HTTP 401/403/redirect đúng ý nghĩa, bảo toàn challenge Basic/Bearer, không lộ lý do nội bộ và kiểm thử bằng `WebTestClient` ở đúng reactive security chain.

## 24. Tài liệu tham khảo chính thức

- Spring Security 6.5 — Reactive Web Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — WebFlux Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html
- Spring Security 6.5 API — `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security 6.5 API — `ServerHttpSecurity.FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security 6.5 API — `ServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html
- Spring Security 6.5 API — `ServerAuthenticationFailureHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationFailureHandler.html
- Spring Security 6.5 API — `ServerAuthenticationEntryPointFailureHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html
- Spring Security 6.5 API — `HttpStatusServerAccessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security 6.5 API — `ExceptionTranslationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html
- Spring Security 6.5 — Reactive WebTestClient Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 API — `BearerTokenServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html
- Spring Security 6.5 API — `BearerTokenServerAccessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
