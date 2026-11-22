# 20.10. ServerAuthenticationSuccessHandler và ServerAuthenticationFailureHandler

## 1. Hai điểm mở rộng quyết định điều gì sau Reactive OAuth2/OIDC Login?

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client** xây dựng trên **Spring WebFlux**, người dùng thường bắt đầu đăng nhập bằng cách được chuyển đến một OpenID Provider (OP), sau đó quay về ứng dụng cùng authorization code. Spring Security xử lý giao dịch, đổi code tại Token Endpoint, xác minh ID Token theo OpenID Connect và tạo `Authentication` cho người dùng.

Đến cuối quá trình này, ứng dụng phải quyết định:

- **Nếu xác thực thành công:** trả người dùng về trang trước khi đăng nhập, chuyển đến dashboard, ghi sự kiện audit hoặc thực hiện một tác vụ hậu đăng nhập hợp lệ.
- **Nếu xác thực thất bại:** đưa người dùng tới một trang lỗi an toàn, ghi metric đã phân loại và không để lộ token, authorization code hay chi tiết lỗi của Identity Provider.

Trên **Reactive Security/WebFlux stack**, hai điểm mở rộng trực tiếp là:

1. **`ServerAuthenticationSuccessHandler`** — xử lý một lượt **authentication thành công**.
2. **`ServerAuthenticationFailureHandler`** — xử lý một lượt **authentication thất bại**.

Chúng có thể được cấu hình trên `ServerHttpSecurity.oauth2Login(...)`. Cả hai đều trả về **`Mono<Void>`** thay vì trực tiếp gọi Servlet API để thao tác `HttpServletResponse`.

Ví dụ mong muốn của portal:

~~~text
User truy cập /reports/me (cần đăng nhập)
    -> Spring Security đưa tới OIDC Provider
    -> Callback /login/oauth2/code/company

Nếu đăng nhập thành công:
    -> quay về /reports/me đã được lưu
    -> hoặc /dashboard nếu không có saved request

Nếu đăng nhập thất bại:
    -> /auth/failed
    -> trang thông báo trung tính, không hiện raw OAuth2 error
~~~

**Mục tiêu bài học** là hiểu giao diện, vị trí trong luồng OIDC, hành vi mặc định, cách thay hoặc bổ sung handler, cách xử lý reactive chain đúng nguyên tắc, đồng thời giữ được security context, saved request, session policy và các ranh giới bảo mật.

> **Phạm vi:** Tập trung vào **Reactive WebFlux server** với `ServerHttpSecurity`, `SecurityWebFilterChain` và `ServerWebExchange`. Không sử dụng `HttpSecurity`, `SecurityFilterChain`, `AuthenticationSuccessHandler` hoặc `HttpServletRequest` của Servlet để thay thế các API reactive trong bài này.

## 2. Phân biệt Reactive Login và Servlet Login

Spring Security hỗ trợ cả hai mô hình. Những tên gọi gần nhau nhưng **không phải cùng interface**:

| Khái niệm | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Security configuration | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| HTTP request/response | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| Đơn vị authentication filter | Servlet filters, ví dụ `OAuth2LoginAuthenticationFilter` | WebFilters, ví dụ các bộ lọc authentication reactive |
| Success handler | `AuthenticationSuccessHandler` | **`ServerAuthenticationSuccessHandler`** |
| Failure handler | `AuthenticationFailureHandler` | **`ServerAuthenticationFailureHandler`** |
| Giá trị trả về | Thao tác response qua Servlet API | **`Mono<Void>`** mô tả tác vụ bất đồng bộ |
| Reactive security context | Không phải cơ chế chính của Servlet | `ReactiveSecurityContextHolder` và repository tương ứng |
| Redirect abstraction | `RedirectStrategy` / Servlet response | `ServerRedirectStrategy` / `ServerWebExchange` |

Ví dụ **Servlet không phù hợp** cho Reactive WebFlux:

~~~java
// Sai ngữ cảnh: AuthenticationSuccessHandler của Servlet.
// Không thể gắn trực tiếp vào oauth2Login của ServerHttpSecurity.
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
~~~

API cần dùng trong WebFlux:

~~~java
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
~~~

Một ứng dụng WebFlux có thể sử dụng HTTP client không đồng bộ, nhưng phần quan trọng ở đây là **inbound authentication của Reactive server**, không phải OAuth2 filter của WebClient dùng cho outbound API.

## 3. Vị trí handler trong Authorization Code + OIDC flow

### 3.1. Luồng đăng nhập thành công

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant App as WebFlux OAuth2/OIDC Client
    participant OP as OpenID Provider
    participant Ctx as Reactive Security Context
    participant H as ServerAuthenticationSuccessHandler
    Browser->>App: GET /reports/me chưa có Authentication
    App-->>Browser: Redirect tới /oauth2/authorization/company
    Browser->>OP: Authorization request (state, PKCE, nonce nếu dùng)
    OP-->>Browser: Callback code + state
    Browser->>App: GET /login/oauth2/code/company?code=...
    App->>OP: Token Endpoint, đổi authorization code
    OP-->>App: Token response (ID Token, Access Token...)
    App->>App: Xác minh OIDC và xây Authentication
    App->>Ctx: Lưu/thiết lập Authentication theo cấu hình
    App->>H: onAuthenticationSuccess(exchange, authentication)
    H-->>Browser: Redirect về saved request hoặc trang đích
    Browser->>App: Request tiếp theo với session/cookie phù hợp
    App-->>Browser: Nội dung được cấp phép
~~~

Chi tiết filter và vị trí chính xác khi ghi security context có thể thay đổi theo phiên bản/cấu hình, nhưng **handler chỉ nhận thành công sau khi Spring Security đã có Authentication hợp lệ**. Không dùng handler để thay xác minh ID Token hoặc đối chiếu `state`.

### 3.2. Luồng đăng nhập thất bại

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant App as WebFlux OAuth2/OIDC Client
    participant OP as OpenID Provider
    participant H as ServerAuthenticationFailureHandler
    Browser->>App: Bắt đầu OAuth2 Login
    App-->>Browser: Redirect đến OP
    OP-->>Browser: Callback báo lỗi hoặc code không hợp lệ
    Browser->>App: OAuth2 callback
    App->>App: Xác thực thất bại / phát sinh AuthenticationException
    App->>H: onAuthenticationFailure(exchange, exception)
    H-->>Browser: Redirect /auth/failed hoặc response đã kiểm soát
    Browser->>App: GET /auth/failed
    App-->>Browser: Thông điệp chung, không chứa credential
~~~

**Không phải mọi lỗi HTTP hoặc mọi callback bất thường đều nhất thiết đi vào cùng handler.** Chẳng hạn lỗi network ngoài quá trình xử lý authentication, CSRF failure, access denied khi đã đăng nhập hoặc exception phát sinh trước/sau authentication filter có thể được xử lý bởi các thành phần khác.

## 4. Contract của ServerAuthenticationSuccessHandler

Giao diện thuộc package:

~~~java
org.springframework.security.web.server.authentication
    .ServerAuthenticationSuccessHandler
~~~

Phương thức chính:

~~~java
Mono<Void> onAuthenticationSuccess(
    WebFilterExchange webFilterExchange,
    Authentication authentication
);
~~~

Các kiểu liên quan:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
~~~

### 4.1. webFilterExchange chứa gì?

`WebFilterExchange` gói ngữ cảnh WebFlux liên quan đến authentication filter, trong đó có:

~~~java
ServerWebExchange exchange = webFilterExchange.getExchange();
~~~

Từ `ServerWebExchange` có thể lấy request, response, session (theo API reactive), attributes và những thông tin HTTP cần thiết. Đây **không phải `HttpServletRequest`**.

### 4.2. authentication là gì?

`Authentication` đại diện cho người dùng đã được xác thực. Sau OIDC Login, nó có thể là `OAuth2AuthenticationToken` với principal kiểu `OidcUser`:

~~~java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

if (authentication instanceof OAuth2AuthenticationToken login) {
    String registrationId = login.getAuthorizedClientRegistrationId();

    if (login.getPrincipal() instanceof OidcUser oidcUser) {
        String subject = oidcUser.getSubject();
        // Dùng subject theo policy, không log toàn bộ principal/claims.
    }
}
~~~

Đoạn trên giả định biến `authentication` là tham số của handler. `OidcUser` có ID Token và có thể có UserInfo; không lấy Access Token bằng cách coi `getIdToken()` là Access Token.

### 4.3. Mono<Void> đại diện cho công việc cần hoàn tất

Ví dụ:

~~~java
ServerAuthenticationSuccessHandler handler =
    (webFilterExchange, authentication) ->
        Mono.fromRunnable(() -> {
            // Thao tác cực nhẹ và không blocking, chỉ để minh họa.
        });
~~~

Trong reactive API, handler phải **trả Publisher biểu diễn toàn bộ công việc**. Đừng tự gọi `subscribe()` và sau đó trả `Mono.empty()`, vì framework có thể coi handler hoàn thành trước khi audit/redirect thực sự hoàn tất.

Một thao tác I/O như gọi database qua R2DBC hoặc gửi event qua reactive client nên được đưa vào chain bằng `flatMap`, `then` hoặc toán tử tương ứng, không dùng `block()` trên event-loop.

## 5. Contract của ServerAuthenticationFailureHandler

Giao diện:

~~~java
org.springframework.security.web.server.authentication
    .ServerAuthenticationFailureHandler
~~~

Phương thức chính:

~~~java
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception
);
~~~

Các import:

~~~java
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;
~~~

### 5.1. AuthenticationException không phải HTTP error response

`AuthenticationException` biểu diễn lỗi trong authentication pipeline. Đối với OAuth2/OIDC Login, lỗi có thể đến từ:

- Callback mang OAuth2 error được provider trả về.
- Correlation thất bại với `state` hoặc authorization request đã lưu.
- Lỗi đổi authorization code, token response không hợp lệ.
- ID Token verification bị từ chối: signature, issuer, audience, thời hạn hoặc nonce theo flow.
- User service hoặc policy authentication cố ý từ chối principal.

**Chẩn đoán chính xác phải dựa trên error type, security logs đã được redaction và hợp đồng của provider.** Không coi mọi `AuthenticationException` là “mật khẩu người dùng sai”, bởi trong OIDC Login ứng dụng không nhất thiết nhận hay kiểm tra mật khẩu.

### 5.2. Đừng trả exception.getMessage() ra browser

Phản ví dụ:

~~~java
// KHÔNG DÙNG:
String target = "/login?error=" + exception.getMessage();
~~~

Thông báo lỗi có thể chứa URL, cấu trúc provider, tên policy, chi tiết validation hoặc dữ liệu không đáng tin. Đưa nguyên vào query string dễ tạo lộ thông tin, injection hoặc URL khó kiểm soát.

Thay vào đó, chuyển người dùng đến **một trang lỗi cố định** như `/auth/failed`. Nếu cần mã lỗi để phân tích, ghi metadata đã phân loại vào log/metric nội bộ, có correlation ID không nhạy cảm.

## 6. Mặc định của OAuth2 Login trên Reactive stack

Với cấu hình:

~~~java
.oauth2Login(Customizer.withDefaults())
~~~

Spring Security đã cung cấp handlers mặc định cho OAuth2 Login.

| Tình huống | Handler mặc định | Hành vi tiêu biểu |
| --- | --- | --- |
| Authentication thành công | **`RedirectServerAuthenticationSuccessHandler`** | Redirect đến saved request nếu có, nếu không dùng location mặc định `/` |
| Authentication thất bại | **`RedirectServerAuthenticationFailureHandler`** | Redirect về `/login?error` |

Đây là hành vi mặc định của OAuth2 Login theo API Spring Security tương ứng; ứng dụng có thể đã cấu hình login page, request cache, session strategy hoặc handler khác.

### 6.1. RedirectServerAuthenticationSuccessHandler

~~~java
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
~~~

Có hai constructor quen thuộc:

~~~java
new RedirectServerAuthenticationSuccessHandler();
new RedirectServerAuthenticationSuccessHandler("/dashboard");
~~~

**Điểm dễ nhầm:** `new RedirectServerAuthenticationSuccessHandler("/dashboard")` **không có nghĩa** sẽ luôn đến dashboard. Handler mặc định có thể ưu tiên **saved request** từ `ServerRequestCache`, rồi mới dùng `/dashboard` khi không có request đã lưu.

Ví dụ:

~~~text
User mở /reports/42 trước khi login
  -> request được lưu
  -> login thành công
  -> redirect tới /reports/42

User tự nhấn nút Login ở trang chủ
  -> không có saved request
  -> login thành công
  -> redirect tới /dashboard (fallback đã cấu hình)
~~~

### 6.2. RedirectServerAuthenticationFailureHandler

~~~java
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;

ServerAuthenticationFailureHandler failure =
    new RedirectServerAuthenticationFailureHandler("/auth/failed");
~~~

Handler này tạo **redirect** tới địa chỉ được cấu hình. Đường dẫn đó phải có controller/page hoặc static resource thích hợp, đồng thời được phép truy cập **khi chưa đăng nhập**.

Nếu trang lỗi cũng yêu cầu authentication, có thể tạo **vòng lặp chuyển hướng**:

~~~text
OAuth2 Login thất bại -> /auth/failed
  -> /auth/failed bị bắt buộc đăng nhập
  -> /oauth2/authorization/company
  -> callback lỗi -> /auth/failed -> ...
~~~

## 7. Cấu hình cơ bản bằng ServerHttpSecurity

### 7.1. Dependencies Spring Boot WebFlux

Với **Spring Boot 3.x / Spring Security 6.x**, ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Trong Spring Boot 4.x, cách chia starter/security module đã thay đổi; chọn những starter WebFlux và OAuth2 Client tương ứng theo **BOM và tài liệu của phiên bản Boot đang dùng**. Không tùy ý trộn Spring Security 6.x và 7.x.

### 7.2. application.yml cho OIDC

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

URL và registration là ví dụ minh họa. OP thật cần công bố discovery metadata hợp lệ, redirect URI đã đăng ký và các claims/scopes theo hợp đồng.

`openid` làm rõ đây là OIDC Login; `profile`/`email` là yêu cầu thêm claim, **không mặc nhiên** đảm bảo OP sẽ trả mọi thông tin đó. Secret không nên hard-code trong source control.

### 7.3. SecurityWebFilterChain với redirect sau login

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/login", "/auth/failed", "/error")
                    .permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authenticationSuccessHandler(
                    new RedirectServerAuthenticationSuccessHandler(
                        "/dashboard"))
                .authenticationFailureHandler(
                    new RedirectServerAuthenticationFailureHandler(
                        "/auth/failed")))
            .build();
    }
}
~~~

**Điều diễn ra:**

1. OAuth2/OIDC Login xử lý callback qua reactive security filters.
2. Khi authentication thành công, success handler redirect về **saved request** nếu có, hoặc `/dashboard`.
3. Khi authentication thất bại và lỗi được filter chuyển tới failure handler, trình duyệt được redirect về `/auth/failed`.
4. Trang `/auth/failed` được cho phép truy cập khi chưa xác thực.

Đây là một **SecurityWebFilterChain hoàn chỉnh thay thế** các cấu hình khác trong bài. Nếu ứng dụng có nhiều chains, cần đảm bảo chain chứa `oauth2Login` thực sự match OAuth2 callback và những request liên quan.

### 7.4. Trang lỗi công khai tối thiểu

~~~java
package com.example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class AuthenticationErrorController {

    @GetMapping("/auth/failed")
    public Mono<String> failed() {
        return Mono.just(
            "Không thể hoàn tất đăng nhập. Vui lòng thử lại hoặc liên hệ hỗ trợ.");
    }
}
~~~

Trang này không đưa raw OAuth2 exception, authorization code, ID Token, Access Token, `state` hoặc session ID vào response. Với UI thực tế, có thể dùng HTML template và hướng dẫn hỗ trợ phù hợp.

## 8. Cấu hình bằng bean thay vì tạo handler trực tiếp trong DSL

Khi cần dùng lại handler hoặc mock/test riêng, có thể khai báo bean:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveLoginHandlerConfig {

    @Bean
    ServerAuthenticationSuccessHandler loginSuccessHandler() {
        return new RedirectServerAuthenticationSuccessHandler("/dashboard");
    }

    @Bean
    ServerAuthenticationFailureHandler loginFailureHandler() {
        return new RedirectServerAuthenticationFailureHandler("/auth/failed");
    }

    @Bean
    SecurityWebFilterChain appWebFilterChain(
            ServerHttpSecurity http,
            ServerAuthenticationSuccessHandler loginSuccessHandler,
            ServerAuthenticationFailureHandler loginFailureHandler) {

        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/", "/login", "/auth/failed").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authenticationSuccessHandler(loginSuccessHandler)
                .authenticationFailureHandler(loginFailureHandler))
            .build();
    }
}
~~~

Đây là **phương án thay thế** cho lớp `ReactiveSecurityConfig` ở phần 7, không copy cả hai cấu hình nếu chúng cùng match tất cả requests.

Tách bean hữu ích khi muốn test redirect logic hoặc injection một audit dependency. Tuy nhiên chỉ khai báo bean **không luôn có nghĩa framework tự sử dụng nó cho mọi authentication mechanism**; cần gắn bean vào `oauth2Login(...)` hoặc cấu hình filter tương ứng.

## 9. Viết custom success handler: audit rồi chuyển hướng

Tình huống: sau khi đăng nhập OIDC thành công, ứng dụng muốn ghi một sự kiện vào hệ thống audit và sau đó sử dụng quy tắc redirect của Spring Security.

Nguyên tắc:

- **Không blocking** event-loop bằng JDBC/blocking HTTP call.
- **Không tự subscribe** mà trả về chain `Mono<Void>` để framework quản lý completion.
- **Không log toàn bộ Authentication/principal**, token hoặc claims nhạy cảm.
- **Không bỏ redirect/saved request mặc định** nếu sản phẩm vẫn cần hành vi đó.
- Nếu audit thất bại, phải có policy rõ: audit bắt buộc hay chỉ là telemetry bổ trợ.

### 9.1. Interface audit minh họa

~~~java
package com.example.security;

import reactor.core.publisher.Mono;

public interface LoginAuditRecorder {

    // Không truyền token, client secret hay raw error description.
    Mono<Void> loginSucceeded(String registrationId);

    Mono<Void> loginFailed(String errorCategory);
}
~~~

Đây là **interface do ứng dụng tự định nghĩa**, không phải class có sẵn trong Spring Security. Implementation có thể ghi audit bằng một reactive database driver hoặc event publisher phù hợp. Khi triển khai cần kiểm soát việc ghi audit, tính sẵn sàng và retention.

### 9.2. Success handler giữ redirect logic mặc định

~~~java
package com.example.security;

import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import reactor.core.publisher.Mono;

public final class ReactiveLoginHandlers {

    private ReactiveLoginHandlers() {
    }

    public static ServerAuthenticationSuccessHandler success(
            LoginAuditRecorder audit) {

        RedirectServerAuthenticationSuccessHandler redirect =
            new RedirectServerAuthenticationSuccessHandler("/dashboard");

        return (webFilterExchange, authentication) -> {
            String registrationId = "unknown";

            if (authentication instanceof OAuth2AuthenticationToken oauth2) {
                registrationId =
                    oauth2.getAuthorizedClientRegistrationId();
            }

            return audit.loginSucceeded(registrationId)
                .onErrorResume(auditError -> Mono.empty())
                .then(redirect.onAuthenticationSuccess(
                    webFilterExchange, authentication));
        };
    }
}
~~~

**Cách đọc:**

1. Lấy `registrationId` từ `OAuth2AuthenticationToken` nếu có.
2. Gọi audit qua `Mono<Void>` mà không lộ token.
3. Trong ví dụ, audit lỗi sẽ được bỏ qua để login vẫn tiếp tục; đây là **policy audit không bắt buộc**, không phải lựa chọn đúng cho mọi tổ chức.
4. Khi audit đã hoàn tất hoặc được bỏ qua, `then(...)` thực hiện redirect handler.
5. Redirect handler vẫn ưu tiên saved request khi có.

Nếu tổ chức yêu cầu **audit bắt buộc trước khi hoàn tất phiên đăng nhập**, không được tùy tiện dùng `onErrorResume(... -> Mono.empty())`; cần có thiết kế chịu lỗi và giải quyết consistency phù hợp, kể cả xử lý trường hợp authentication đã được xác thực nhưng audit thất bại.

### 9.3. Gắn vào oauth2Login

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        LoginAuditRecorder audit) {

    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/", "/auth/failed").permitAll()
            .anyExchange().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .authenticationSuccessHandler(
                ReactiveLoginHandlers.success(audit))
            .authenticationFailureHandler(
                new RedirectServerAuthenticationFailureHandler(
                    "/auth/failed")))
        .build();
}
~~~

Đoạn này là **method cấu hình thay thế**, đặt trong class `@Configuration` với các import tương ứng ở phần trước; không thêm vào project bên cạnh một security chain match toàn bộ requests.

## 10. Viết custom failure handler: phân loại lỗi an toàn

Đối với login failure, ứng dụng muốn ghi metric như:

~~~text
event=oidc_login_failed
registration=company
category=provider_rejected_or_validation_failed
correlation_id=internal-a83f
~~~

Không log nguyên authorization code, token response, client secret hoặc raw `exception.getMessage()`.

### 10.1. Phân loại theo những nhãn được duyệt

`OAuth2AuthenticationException` có thể chứa `OAuth2Error` với `errorCode`. Nhưng **error code từ hệ thống bên ngoài có thể không nằm trong tập mà ứng dụng mong đợi**.

Một hàm phân loại an toàn:

~~~java
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;

public static String safeCategory(AuthenticationException exception) {
    if (!(exception instanceof OAuth2AuthenticationException oauth2)) {
        return "authentication_failed";
    }

    String code = oauth2.getError().getErrorCode();

    return switch (code) {
        case "access_denied" -> "provider_access_denied";
        case "invalid_client" -> "client_configuration";
        case "invalid_grant" -> "code_or_token_grant_rejected";
        case "invalid_request" -> "invalid_request";
        default -> "oidc_authentication_failed";
    };
}
~~~

Đoạn là **hàm minh họa** để đặt trong utility class (Java 17+). Hãy xử lý `null` nếu tích hợp của bạn cho phép error code thiếu, không mặc định thông điệp nào cũng có trong chuẩn.

Các mã như `invalid_client` hoặc `invalid_grant` không nhất thiết xuất hiện trực tiếp trong `OAuth2AuthenticationException` của mọi provider/filter; một số lỗi có thể bị biến đổi thành loại exception khác. Đây chỉ là bước **phân loại**, không thay điều tra và không phải tên lỗi được bảo đảm trong mọi phiên bản.

### 10.2. Failure handler giữ redirect, không lộ chi tiết

~~~java
package com.example.security;

import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;

public final class ReactiveLoginFailures {

    private ReactiveLoginFailures() {
    }

    public static ServerAuthenticationFailureHandler failure(
            LoginAuditRecorder audit) {

        RedirectServerAuthenticationFailureHandler redirect =
            new RedirectServerAuthenticationFailureHandler("/auth/failed");

        return (webFilterExchange, exception) -> {
            String category = categoryOf(exception);

            return audit.loginFailed(category)
                .onErrorResume(auditError -> Mono.empty())
                .then(redirect.onAuthenticationFailure(
                    webFilterExchange, exception));
        };
    }

    private static String categoryOf(AuthenticationException exception) {
        if (exception instanceof OAuth2AuthenticationException oauth2) {
            String code = oauth2.getError().getErrorCode();
            if ("access_denied".equals(code)) {
                return "provider_access_denied";
            }
            if ("invalid_client".equals(code)) {
                return "client_configuration";
            }
            if ("invalid_grant".equals(code)) {
                return "grant_rejected";
            }
        }
        return "authentication_failed";
    }
}
~~~

`ReactiveLoginFailures.failure(audit)` có thể được gắn vào:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authenticationFailureHandler(
        ReactiveLoginFailures.failure(audit)))
~~~

Ở đây, audit lỗi không cản trở redirect. **Không cần đưa category vào URL** trừ khi sản phẩm có cơ chế public error code được kiểm soát. Trang lỗi có thể luôn hiển thị thông điệp chung, còn log nội bộ sử dụng correlation ID.

### 10.3. Vì sao không gửi thông tin exception vào query string?

Phản ví dụ:

~~~text
/auth/failed?message=invalid_nonce_for_user_xxx
~~~

URL có thể xuất hiện trong:

- Browser history.
- Reverse proxy access logs.
- Observability/tracing.
- Screenshots hoặc người dùng chia sẻ.
- Một số referrer situations nếu cấu hình không phù hợp.

**Không đưa credential hay thông tin xác thực chi tiết vào URL để thuận tiện debug.** Ghi audit an toàn và cung cấp mã tham chiếu hỗ trợ riêng nếu cần.

## 11. Tùy biến redirect và saved request

### 11.1. RedirectServerAuthenticationSuccessHandler ưu tiên saved request

~~~java
new RedirectServerAuthenticationSuccessHandler("/dashboard")
~~~

phù hợp khi muốn:

~~~text
Saved request tồn tại -> quay lại địa chỉ user từng cần truy cập
Không có saved request -> /dashboard
~~~

`RedirectServerAuthenticationSuccessHandler` có thể dùng `WebSessionServerRequestCache` theo mặc định và cho phép thay `ServerRequestCache` bằng `setRequestCache(...)`.

Nếu ứng dụng đang dùng nhiều domains, reverse proxies hoặc URL rewriting, cần kiểm tra saved request target có thuộc **origin/trust boundary phù hợp**.

### 11.2. Khi muốn luôn về một trang cố định

Đừng nghĩ constructor truyền `"/dashboard"` sẽ bỏ qua saved request. Nếu nghiệp vụ thực sự muốn **bỏ qua saved request**, có thể dùng `ServerRedirectStrategy`:

~~~java
import java.net.URI;
import org.springframework.security.web.server.DefaultServerRedirectStrategy;
import org.springframework.security.web.server.ServerRedirectStrategy;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

ServerRedirectStrategy redirect = new DefaultServerRedirectStrategy();

ServerAuthenticationSuccessHandler dashboardOnly =
    (webFilterExchange, authentication) ->
        redirect.sendRedirect(
            webFilterExchange.getExchange(),
            URI.create("/dashboard"));
~~~

Đây là phương án **unconditional redirect**. Nếu sản phẩm có saved request cần quay lại, nên giữ `RedirectServerAuthenticationSuccessHandler` mặc định thay vì bỏ qua.

### 11.3. Open redirect khi nhận returnUrl từ browser

Một thiết kế nguy hiểm:

~~~java
// PHẢN VÍ DỤ: không cho input tự do quyết định redirect.
String returnUrl = exchange.getRequest().getQueryParams()
    .getFirst("returnUrl");
return redirect.sendRedirect(exchange, URI.create(returnUrl));
~~~

Nếu attacker có thể tạo `returnUrl=https://evil.example/collect`, user vừa login có thể bị redirect tới website ngoài không đáng tin. Trường hợp khác là redirect qua path dạng `//external-host` hoặc qua encoding phức tạp.

Để triển khai redirect tùy biến:

1. Chỉ chấp nhận **đường dẫn tương đối thuộc ứng dụng** sau khi được chuẩn hóa và kiểm tra.
2. Dùng **allowlist routes** như `/dashboard`, `/profile`, `/reports`.
3. Không dùng URI từ query string để chuyển hướng tự do.
4. Không đưa token hoặc authorization code vào redirect URL.
5. Nếu cần giá trị return-to, lưu nó server-side gắn với giao dịch/phiên, có TTL và validation.

## 12. Custom success handler có thể ảnh hưởng đến concurrent session control

Một chi tiết phụ thuộc phiên bản cần lưu ý: Spring Security Reactive hỗ trợ **concurrent sessions control** cho các cơ chế authentication bao gồm Form Login và OAuth2 Login. Một số session management handlers được gắn vào **danh sách success handlers**.

Nếu thay success handler bằng:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authenticationSuccessHandler(myHandler))
~~~

ứng dụng có thể **thay thế danh sách handlers trước đó** theo semantics của API. Điều này có thể khiến các handler quản lý phiên đồng thời không còn được gọi như mong đợi.

### 12.1. Danh sách handlers trong Spring Security 6.3+

Các bản Spring Security hỗ trợ overload:

~~~java
authenticationSuccessHandler(
    Consumer<List<ServerAuthenticationSuccessHandler>> handlersConsumer)
~~~

cho phép **bổ sung** một handler thay vì chỉ thay toàn bộ cấu hình.

Ví dụ hình thức:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authenticationSuccessHandler(handlers ->
        handlers.add(myAdditionalSuccessHandler)))
~~~

Đoạn này giả định `myAdditionalSuccessHandler` là một `ServerAuthenticationSuccessHandler` đã được tạo. Dùng API phù hợp **phiên bản Spring Security hiện tại**; overload này được giới thiệu từ nhánh 6.3.

**Cẩn trọng về thứ tự:** khi có nhiều handlers, cần biết handlers nào điều khiển session và handler nào redirect/commit response. Tránh bổ sung một handler thứ hai cũng redirect hoặc viết response nếu đã có redirect handler trong danh sách.

### 12.2. Khi nào nên chọn wrapper và khi nào dùng danh sách?

| Nhu cầu | Cách tiếp cận nên đánh giá |
| --- | --- |
| Chỉ đổi fallback URL sau login | `RedirectServerAuthenticationSuccessHandler` |
| Ghi một event audit rồi redirect | Wrapper trả `audit.then(redirect.onAuthenticationSuccess(...))` |
| Muốn giữ tất cả handlers hệ thống đã cấu hình | Bổ sung vào danh sách theo API 6.3+ và kiểm soát thứ tự |
| Concurrent session control đang bật | Xác minh việc custom handler không vô hiệu hóa registration/session-control hooks |
| Cần xử lý JSON thay vì redirect | Handler khác cho đúng authentication mechanism/API contract |

Không tự kết luận “login thành công” đồng nghĩa “concurrent session limit chắc chắn được thực thi” nếu đã thay handler mà chưa kiểm tra session management configuration.

## 13. Khi nào cần JSON response thay vì redirect?

OAuth2/OIDC Authorization Code Login là một **browser redirect flow**. Vì vậy, redirect sau success/failure thường phù hợp hơn với một ứng dụng web có session.

Tuy nhiên, có ứng dụng yêu cầu API response đã kiểm soát. Có thể viết một `ServerAuthenticationFailureHandler` trả JSON thay vì chuyển trang:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;

ServerAuthenticationFailureHandler jsonFailure =
    (webFilterExchange, exception) -> {
        ServerHttpResponse response =
            webFilterExchange.getExchange().getResponse();

        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] payload =
            "{\"error\":\"authentication_failed\"}"
                .getBytes(StandardCharsets.UTF_8);

        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(payload)));
    };
~~~

Điểm cần nhớ:

- Body trả **mã lỗi cố định**, không dùng `exception.getMessage()`.
- `writeWith(...)` trả `Mono<Void>`, phù hợp reactive contract.
- Không gọi `subscribe()` thủ công hoặc gọi `setComplete()` trước khi body ghi xong.
- Một response chỉ nên có **một** handler chịu trách nhiệm status/body/redirect.
- Sau khi response đã committed, không thể tùy ý đổi sang redirect khác.

**Không nên thay mặc định OAuth2 browser login bằng JSON 401 chỉ vì frontend dùng AJAX.** Authorization Code Login vẫn cần xử lý redirect đến OP, callback và cookie/session; nếu frontend là SPA thuần hay mobile app, kiến trúc OAuth2 Client/BFF cần được lựa chọn rõ ràng.

### 13.1. Phân biệt 401, 403 và 302 trong WebFlux Security

| HTTP response | Ngữ cảnh điển hình | Thành phần liên quan |
| --- | --- | --- |
| `302` về OP/login page | Chưa đăng nhập, cần bắt đầu authentication | Authentication entry point/authorization redirect |
| `302` tới saved request/dashboard | Authentication thành công | `ServerAuthenticationSuccessHandler` |
| `302` tới `/login?error` | Authentication thất bại | `ServerAuthenticationFailureHandler` |
| `401` JSON | API authentication policy hoặc custom failure handler | Entry point hoặc failure handler tùy điểm phát sinh |
| `403` | Đã xác thực nhưng thiếu quyền | AccessDeniedHandler / authorization pipeline |

**Một API trả 403 không phải authentication failure của OAuth2 Login.** Đừng chỉ sửa `ServerAuthenticationFailureHandler` để giải quyết một lỗi `@PreAuthorize` hoặc `authorizeExchange(...).hasRole(...)`.

## 14. Authentication success khác authorized-client authorization success

Một ứng dụng reactive dùng OAuth2 Login **và** OAuth2 Client để gọi downstream API có hai loại success hooks:

| Hook | Tầng sử dụng | Mục đích |
| --- | --- | --- |
| **`ServerAuthenticationSuccessHandler`** | Inbound WebFlux authentication | Xử lý người dùng vừa đăng nhập thành công, redirect/audit/session |
| **`ServerAuthenticationFailureHandler`** | Inbound WebFlux authentication | Xử lý lượt đăng nhập bị từ chối |
| `ReactiveOAuth2AuthorizationSuccessHandler` | **ReactiveOAuth2AuthorizedClientManager** | Lưu/cập nhật `OAuth2AuthorizedClient` sau khi xin hoặc refresh Access Token |
| `ReactiveOAuth2AuthorizationFailureHandler` | Reactive authorized client manager | Xử lý lỗi cấp mới/refresh token theo policy |

Một ví dụ:

~~~text
User đăng nhập OIDC thành công:
  -> ServerAuthenticationSuccessHandler -> redirect /dashboard

Sau đó portal gọi Reports API bằng WebClient:
  -> ReactiveOAuth2AuthorizedClientManager.authorize(...)
  -> Token cần refresh
  -> ReactiveOAuth2AuthorizationSuccessHandler -> lưu token mới
~~~

**Không dùng ServerAuthenticationSuccessHandler để refresh Access Token** mỗi khi gọi API. Một user có thể đăng nhập một lần nhưng WebClient refresh nhiều lần trong suốt session.

### 14.1. Hai kiểu principal và token

Trong OAuth2/OIDC Login:

- `Authentication` của user xác nhận **danh tính** theo OIDC/OAuth2 Login.
- `OAuth2AuthorizedClient` lưu Access Token/Refresh Token cho một client registration và principal.
- ID Token giúp client xác thực user; Resource Server thường nhận **Access Token**.

Không đọc ID Token từ `OidcUser` rồi dùng nó như Access Token chỉ vì login success handler có thể truy cập principal.

### 14.2. Không ghi token từ login handler nếu không có lý do

Spring Security đã có các abstraction lưu authorized client. Nếu custom success handler tự viết:

~~~java
// PHẢN VÍ DỤ ý tưởng: không tự lưu token vào session attribute tùy ý.
exchange.getSession().map(session -> {
    session.getAttributes().put("userAccessToken", tokenValue);
    return session;
});
~~~

điều này dễ tạo kho token thứ hai không thống nhất với authorized client manager, có thể bị lộ hoặc stale. Ưu tiên `ServerOAuth2AuthorizedClientRepository` hoặc `ReactiveOAuth2AuthorizedClientService` theo kiến trúc.

## 15. State, nonce, PKCE và giới hạn vai trò của handler

Trong OIDC Authorization Code flow, có nhiều kiểm tra diễn ra **trước khi thành công**:

| Cơ chế | Chức năng | Handler có thay thế được không? |
| --- | --- | --- |
| `state` | Ràng buộc authorization response với request ban đầu, chống login CSRF/correlation failures | Không |
| PKCE `code_verifier` | Ràng buộc code exchange với client đã tạo challenge | Không |
| OIDC `nonce` | Ràng buộc ID Token với authorization request trong những flow áp dụng | Không |
| ID Token signature/`iss`/`aud`/`exp` | Xác minh token từ issuer đúng và dành cho client phù hợp | Không |
| UserInfo `sub` | Đối chiếu claim hồ sơ với danh tính trong ID Token | Không |

### 15.1. Login handler không có trách nhiệm xác minh ID Token

Một success handler chạy sau khi framework xác nhận authentication thành công; nó **không nên** tự bỏ qua validation vì muốn redirect nhanh.

Failure handler chỉ quyết định cách xử lý thất bại. Nó **không thể biến ID Token sai signature thành hợp lệ** bằng cách trả 302 thay cho exception.

### 15.2. Không tự đổi thất bại thành thành công

Thiết kế nguy hiểm:

~~~text
Provider trả invalid_grant hoặc ID Token invalid
  -> custom failure handler bắt lỗi
  -> tự dựng Authentication có ROLE_USER
  -> redirect vào trang bảo vệ
~~~

Điều này phá ranh giới xác thực. Khi không thể xác minh danh tính, phải **giữ trạng thái chưa xác thực** hoặc kết thúc luồng theo chính sách hợp lệ.

### 15.3. OAuth2 error có thể đến từ callback

OP có thể trả về:

~~~text
/login/oauth2/code/company?error=access_denied&state=...
~~~

`access_denied` ở bước authorization có thể chỉ nghĩa là user từ chối consent hoặc OP không cấp quyền. Không mặc định đây là credential/password sai, không đưa raw `error_description` vào browser.

## 16. SecurityContext, WebSession và request cache

### 16.1. SecurityContext không được lưu bằng redirect URL

Trong WebFlux, security context được quản lý qua reactive security components, `ReactiveSecurityContextHolder` và `ServerSecurityContextRepository` theo cấu hình.

~~~text
OIDC Authentication thành công
  -> Authentication có principal hợp lệ
  -> SecurityContext được lưu/quản lý theo repository và policy
  -> Success handler redirect
  -> Browser request tiếp theo mang session/cookie thích hợp
~~~

Nếu ứng dụng tự viết handler chỉ trả 302, điều đó không nên thay thế cấu hình lưu SecurityContext của framework. Ngược lại, nếu hệ thống cấu hình **stateless** một cách chủ ý, login browser session và request tiếp theo phải được thiết kế tương ứng; handler không tự làm WebSession persistence.

### 16.2. Saved request dùng để làm gì?

Giả sử user mở trang cần auth:

~~~text
GET /reports/quarterly
  -> chưa authenticated
  -> được lưu trong ServerRequestCache
  -> browser thực hiện OIDC Login
  -> success redirect về /reports/quarterly
~~~

`RedirectServerAuthenticationSuccessHandler` mặc định có thể sử dụng `WebSessionServerRequestCache`. Nếu custom handler luôn redirect `/dashboard` và không dùng request cache, trải nghiệm “quay lại nơi người dùng đang làm” có thể bị mất.

### 16.3. Nhiều tabs và saved request

Trong cùng một browser session, user có thể mở nhiều tabs và bắt đầu các authorization requests khác nhau. Tùy cơ chế repository/cache, saved request có thể thay đổi hoặc chịu giới hạn.

Không nên mặc định dùng một global `returnUrl` trong cookie/local storage cho mọi giao dịch. Nếu sản phẩm đòi hỏi giữ chính xác đích cho từng flow, cần thiết kế correlation có TTL và kiểm tra origin, không gắn trust vào query string tùy ý.

### 16.4. Session management và login success

Một session login thành công có thể còn chịu chính sách:

- Session timeout.
- Concurrent sessions control.
- Session fixation policy.
- Logout và OIDC logout khi cấu hình.
- Session invalidation khi người dùng bị khóa hoặc quyền thay đổi.

**Success handler không tự thay thế những cơ chế này.** Đặc biệt, nếu thay hẳn danh sách success handlers, cần kiểm tra những thành phần registration/concurrent sessions đã được Spring Security thêm vào.

## 17. Nhiều SecurityWebFilterChain và nhiều authentication mechanisms

Ứng dụng có thể có:

- Một chain cho OAuth2/OIDC browser login.
- Một chain cho API dùng Bearer Token (Resource Server).
- Các endpoint public/health.

Nếu cấu hình OAuth2 Login success handler ở chain không match callback, handler có thể không bao giờ được gọi.

### 17.1. Phân biệt success handler cho formLogin và oauth2Login

~~~java
.formLogin(form -> form
    .authenticationSuccessHandler(formSuccess))

.oauth2Login(oauth2 -> oauth2
    .authenticationSuccessHandler(oidcSuccess))
~~~

Hai handler trên phục vụ **hai cơ chế authentication khác nhau**. Chỉ cấu hình `formLogin` không làm OIDC Login tự sử dụng cùng success handler.

### 17.2. Một chain cho API có thể không cần browser redirect

API token authentication thường muốn HTTP 401/403 theo hợp đồng, không phải redirect browser tới `/login`. Với `ServerHttpSecurity.oauth2ResourceServer(...)`, việc xác thực Bearer Token và policy khác với `oauth2Login(...)`.

Không tái sử dụng một failure redirect handler cho mọi loại authentication mà không cân nhắc client; máy gọi API có thể không hiểu HTML login page.

### 17.3. Matcher và thứ tự

Nếu nhiều chains được đăng ký:

~~~text
/api/**             -> API resource server policy
/login/oauth2/**    -> OAuth2 login callback chain
/oauth2/authorization/** -> OAuth2 login initiation chain
/**                 -> Web UI chain
~~~

Đây là sơ đồ khái niệm, không phải route map bắt buộc. Cần kiểm tra `securityMatcher(...)`, thứ tự chains, redirect URI thật và endpoint của Spring Security để không vô tình đặt callback vào chain không có OAuth2 Login.

## 18. Reactivity: không block(), không subscribe() thủ công

### 18.1. Tại sao Mono<Void> quan trọng?

Một handler có thể gọi audit repository/reactive client và redirect:

~~~java
return audit.loginSucceeded(registrationId)
    .then(redirect.onAuthenticationSuccess(
        webFilterExchange, authentication));
~~~

Nếu audit là publisher **cold**, nó chỉ chạy khi được subscribe bởi framework. Bằng cách trả chain, Spring Security có thể đợi công việc hoàn tất.

### 18.2. Tránh subscribe() tách luồng

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: side effect chạy độc lập, không có lifecycle bảo đảm.
audit.loginSucceeded(registrationId).subscribe();
return Mono.empty();
~~~

Rủi ro:

- Audit có thể mất khi request hoàn tất hoặc app shutdown.
- Error có thể không được xử lý đúng.
- Thứ tự audit/redirect không được bảo đảm.
- Khó đo latency/correlation và test.

### 18.3. Tránh blocking IO

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ trên Reactor event-loop:
repository.saveToJdbcBlocking(authentication.getName());
Thread.sleep(500);
~~~

Nếu dùng legacy blocking I/O, cần thiết kế adapter/scheduler phù hợp hoặc chuyển sang reactive driver, không chỉ đặt code blocking trong lambda của handler. Chỉ thực hiện các side effects cần thiết; login callback không nên bị chặn bởi một mạng dịch vụ không ổn định nếu không thuộc yêu cầu bảo mật bắt buộc.

### 18.4. Không giữ ServerWebExchange ngoài vòng đời request

`ServerWebExchange`, response và WebSession tương ứng có vòng đời gắn với inbound HTTP request. Không đưa nguyên exchange vào queue để thao tác sau khi redirect đã gửi; với audit, chỉ trích xuất **metadata được phép** cần ghi và xử lý theo contract.

## 19. Xử lý lỗi khi redirect/audit thất bại

### 19.1. Failure của audit không phải luôn là authentication failure

Giả sử ID Token đã được xác minh, Authentication hợp lệ, nhưng hệ thống audit tạm thời unavailable. Có thể chọn:

- Audit là **best-effort**: ghi metric/log an toàn về lỗi audit, tiếp tục redirect.
- Audit là **bắt buộc theo tuân thủ**: phải có chính sách rõ ràng, thiết kế bền vững như outbox hoặc quy trình quản lý lỗi; không âm thầm bỏ qua.

Không xem mọi lỗi phụ trợ sau authentication là lỗi xác thực credential của user. Cần phân biệt “identity validation failed” với “post-login side effect failed”.

### 19.2. Redirect URL sai

Nếu handler trỏ đến `/dashboard` nhưng route này không tồn tại, login vẫn có thể thành công; browser nhận 404 sau redirect. Lỗi đó không có nghĩa OIDC token invalid.

### 19.3. Redirect loop

Nếu trang `/auth/failed` bị bảo vệ, hoặc `/dashboard` tự redirect ngược về `/login` vì SecurityContext không được lưu đúng, browser có thể lặp chuyển hướng.

Điều tra:

1. URL nào là callback thật của OP?
2. Có handler nào tạo redirect tới URL cũng cần auth không?
3. Session cookie có được browser gửi về không?
4. Cookie `SameSite`/`Secure`/proxy/HTTPS có phù hợp callback mode không?
5. SecurityWebFilterChain và context repository có đúng không?

### 19.4. Provider callback lỗi nhưng failure handler không chạy

Không phải mọi lỗi từ provider đi đúng một luồng `AuthenticationException` của authentication WebFilter. Có thể gặp:

- Callback URL không match authentication matcher.
- Proxy rewrite path sai.
- Authorization request/session correlation thất bại ở thành phần trước filter.
- Exception kỹ thuật ngoài auth exception handler.
- Cấu hình nhiều chains làm callback không được xử lý.

Vì vậy, đừng bắt đầu bằng cách thay failure handler ngay. Xác minh **request đã đi tới đúng OAuth2 Login filter** và exception thuộc loại được failure handler xử lý.

## 20. Bảo mật: handler phải làm ít việc nhưng đúng việc

### 20.1. Không log credential hoặc toàn bộ principal

Không ghi:

- Authorization code trên callback URL.
- Access Token, Refresh Token hoặc ID Token.
- `client_secret`, client assertion, private key.
- PKCE `code_verifier`, OIDC `nonce` hoặc `state`.
- Toàn bộ `Authentication` hoặc `OidcUser.getClaims()`.
- Raw `OAuth2AuthenticationException.getMessage()` / provider error description.

Một bản ghi audit an toàn có thể chứa:

~~~text
event=oidc_login_completed
registration_id=company
outcome=success
timestamp=server_time
correlation_id=internal-9d83
~~~

Đây là định dạng minh họa. Nếu cần subject/tenant cho audit compliance, áp dụng chính sách dữ liệu cá nhân, kiểm soát quyền truy cập và retention.

### 20.2. Không cấp role trong failure handler

Failure handler là nơi xử lý thất bại, **không phải fallback authentication provider**. Không tự đánh dấu user authenticated để “không làm gián đoạn trải nghiệm” khi ID Token invalid hoặc `state` sai.

### 20.3. Không nhận external redirect tùy ý

Chỉ redirect tới route được tin cậy hoặc URL đã được kiểm tra nghiêm ngặt. Không dùng unchecked `returnUrl` trong query hoặc cookie để quyết định destination.

### 20.4. Không dùng exception để lộ thông tin tài khoản

Một trang lỗi cho phép attacker phân biệt “email tồn tại”, “tài khoản khóa”, “nonce sai” hoặc “consent bị từ chối” có thể tạo thêm kênh enumeration. Với browser UX phổ thông, nên dùng thông điệp trung tính và mã hỗ trợ riêng.

### 20.5. Kiểm soát login event side effects

Sau login không nên tự động:

- Gán quyền admin chỉ vì claim username có chữ “admin”.
- Liên kết tài khoản theo email chưa xác minh.
- Gửi token đến endpoint analytics bên ngoài.
- Lưu raw ID Token trong cookie tự tạo.
- Gọi API nhạy cảm thay user trước khi kiểm tra scope/audience và authorization.

Sử dụng `issuer + subject` làm nền tảng định danh OIDC và policy nội bộ cho account linking/authorization.

## 21. Những lỗi dễ nhầm với handler

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
| --- | --- | --- |
| Login thành công nhưng không về dashboard | Saved request được ưu tiên | Kiểm tra `RedirectServerAuthenticationSuccessHandler` và request cache |
| Login lỗi nhưng vẫn thấy `/login?error` | Custom failure handler chưa gắn đúng chain | Kiểm tra `oauth2Login(...).authenticationFailureHandler(...)` |
| Vòng lặp về trang lỗi | `/auth/failed` không permitAll | Cho phép trang lỗi public hoặc thay response policy |
| Trang dashboard nhận 401 sau redirect | Session/security context không tồn tại ở request mới | Kiểm tra repository, cookie, proxy, session |
| Success handler log hai lần | Nhiều authentication attempts hoặc nhiều handlers/filter chains | Kiểm tra matcher, list handlers, event deduplication |
| Custom handler làm session limit không hoạt động | Đã thay danh sách success handlers | Xem overload thêm handler và concurrent session control |
| Audit record chưa ghi nhưng browser đã redirect | Handler tự `subscribe()` rồi trả sớm | Trả `Mono<Void>` chain bằng `then`/`flatMap` |
| Login treo vì audit | Blocking call trong reactive thread hoặc upstream audit chậm | Dùng reactive I/O, timeout/policy |
| Failure handler không chạy với 403 | 403 là authorization failure, không phải authentication failure | Xem `ServerAccessDeniedHandler`/authorization rules |
| Failure handler không chạy với API 401 | API entry point khác OAuth2 Login callback | Xem authentication entry point và API security chain |
| OAuth2 callback 404 | Redirect URI/matcher/proxy sai | Kiểm tra `/login/oauth2/code/{registrationId}` |
| ID Token verification lỗi | Issuer, audience, signature, exp, nonce ... | Điều tra OIDC config/metadata, không bypass validation |
| Login success handler được gọi nhưng token API không có | Authorized client store khác hoặc scope không phù hợp | Xem reactive authorized client manager/repository |
| Browser bị đưa đến domain lạ | Open redirect qua returnUrl | Sử dụng URL allowlist và saved request đã kiểm tra |
| Error page lộ nội dung provider | Đưa exception message vào query/body | Ghi mã lỗi an toàn, thông báo trung tính |
| Chỉ lỗi khi deploy nhiều pods | Session không chia sẻ, cookie key/route thay đổi | Session architecture, reverse proxy, distributed store |

### 21.1. Quy trình debug khi “không về trang dự kiến”

~~~text
User hoàn tất OIDC Login
  |
  +-- Callback đã đến đúng SecurityWebFilterChain?
  |
  +-- ID Token validation và Authentication có thành công?
  |
  +-- Success handler có thực sự được gắn vào oauth2Login?
  |
  +-- Saved request có được lưu không?
  |
  +-- Redirect strategy chọn saved request hay fallback location?
  |
  +-- Target URL có tồn tại và thuộc trusted origin?
  |
  +-- Browser có gửi session cookie ở request tiếp theo?
  |
  +-- Authorization của trang đích có cho phép principal này?
~~~

Không kết luận “success handler hỏng” chỉ vì trang sau redirect báo 403 — đó có thể là một bước phân quyền sau xác thực.

## 22. Kiểm thử Success/Failure Handler

Để kiểm tra hành vi, nên phân loại test theo mục tiêu:

| Loại test | Mục tiêu |
| --- | --- |
| Unit test trực tiếp handler | Kiểm tra `Mono<Void>` hoàn tất, redirect URL/status hoặc JSON body |
| Test tích hợp Reactive Security | Xác nhận đúng `SecurityWebFilterChain`, OAuth2 Login config và handler |
| Test flow với fake OIDC Provider | Authorization Code callback, ID Token validation, saved request, lỗi provider |
| Test session/redirect | SecurityContext và request cache hoạt động đúng khi browser chuyển trang |
| Test observability | Audit không có token/secret, lỗi được phân loại an toàn |
| Test nhiều sessions | Custom success handler không phá chính sách concurrent sessions |

### 22.1. Unit test redirect behavior

Với Spring WebFlux test infrastructure, có thể tạo mock `ServerWebExchange` và `WebFilterExchange`, truyền một `Authentication` test vào handler rồi dùng `StepVerifier`:

~~~java
StepVerifier.create(
    successHandler.onAuthenticationSuccess(
        testWebFilterExchange,
        testAuthentication))
    .verifyComplete();
~~~

Đây là **test skeleton**, giả định đã tạo `testWebFilterExchange`/`testAuthentication`. Sau đó assert status/`Location` hoặc trạng thái saved request như cấu hình. Không cần gọi provider thật để test một handler đơn giản.

### 22.2. Failure test với lỗi giả

~~~java
import org.springframework.security.authentication.BadCredentialsException;
import reactor.test.StepVerifier;

StepVerifier.create(
    failureHandler.onAuthenticationFailure(
        testWebFilterExchange,
        new BadCredentialsException("TEST_ONLY_FAILURE")))
    .verifyComplete();
~~~

Kiểm tra response:

- Redirect đến `/auth/failed` hoặc JSON `401` cố định.
- Không chứa `TEST_ONLY_FAILURE`/error message trong `Location` hay body.
- Không tạo Authentication hợp lệ sau lỗi.
- Không có raw credential trong audit.

`BadCredentialsException` chỉ là exception test thuận tiện; **OIDC Login failure thực tế có thể là loại exception khác**.

### 22.3. WebTestClient không tự chứng minh cả OIDC flow

`WebTestClient` có thể kiểm tra Spring WebFlux HTTP behavior và Spring Security. Những test dùng mock login (chẳng hạn mock OIDC principal) giúp test authorization của controller, nhưng **không tự xác minh callback thật, token exchange, `state`, PKCE hay nonce**.

Muốn test end-to-end cần một mock OP/Authorization Server phù hợp, lập authorization request, xử lý callback và kiểm tra ID Token/token response. Tách rõ:

~~~text
Handler unit test
  -> redirect/audit logic

SecurityWebFilterChain integration test
  -> matcher, context, request cache, response policy

OIDC protocol integration test
  -> discovery, authorization code, state, PKCE, ID Token, nonce
~~~

### 22.4. Kịch bản cần bao phủ

| Kịch bản | Kỳ vọng |
| --- | --- |
| Login thành công không có saved request | Redirect tới fallback `/dashboard` |
| Login thành công có saved request | Redirect tới trang đã lưu nếu policy cho phép |
| User chủ động từ chối consent | Thông báo lỗi chung, audit theo loại được duyệt |
| ID Token không hợp lệ | Không gọi success handler như đăng nhập hợp lệ |
| State/correlation thất bại | Không tạo session xác thực hợp lệ |
| AuthenticationException chứa message nhạy cảm | Message không xuất hiện trong URL/response |
| Audit thành công | Redirect diễn ra sau audit theo chain thiết kế |
| Audit best-effort bị lỗi | Hành vi tiếp tục đúng policy, không treo login |
| Handler custom viết body JSON | HTTP status, Content-Type và body chính xác |
| API authorization trả 403 | Không nhầm thành OAuth2 Login failure |
| Hai browser sessions | Session/identity không bị lẫn |
| Concurrent sessions control bật | Custom success handler không bỏ các session handlers cần thiết |
| Redirect target lạ hoặc absolute URL | Bị từ chối bởi allowlist/policy |
| Callback URL vào chain sai | Test phát hiện redirect/matcher sai |
| Browser không gửi cookie sau callback | Test xác định session continuity issue |

## 23. Tình huống thực hành

### Tình huống A — Trở về trang đang xem sau login

User muốn xem `/reports/2026`, nhưng chưa authenticated. Spring Security lưu request và đưa user tới OP.

**Giải pháp:** dùng `RedirectServerAuthenticationSuccessHandler("/dashboard")`; saved request có thể được ưu tiên. Không tự override bằng redirect dashboard cố định nếu muốn giữ trải nghiệm này.

### Tình huống B — Luôn đưa user tới dashboard

Sản phẩm chủ động bỏ hành vi quay lại trang trước đó.

**Giải pháp:** custom `ServerAuthenticationSuccessHandler` dùng `ServerRedirectStrategy.sendRedirect(exchange, URI.create("/dashboard"))`. Phải kiểm soát redirect URL và chấp nhận đánh đổi việc không dùng saved request.

### Tình huống C — Ghi audit đăng nhập nhưng không muốn chậm trải nghiệm

Audit system đôi khi không phản hồi.

**Giải pháp:** tạo handler trả chain `audit.loginSucceeded(...).onErrorResume(...).then(redirect...)` nếu audit best-effort; giới hạn latency và dùng hệ thống audit bền vững theo policy. Không gọi `subscribe()` trong handler rồi mặc kệ lỗi.

### Tình huống D — OAuth2 provider trả access_denied

Người dùng từ chối chia sẻ quyền cho client.

**Giải pháp:** failure handler đưa về trang chung, audit category an toàn. Không tự tạo Authentication cho user để vượt consent.

### Tình huống E — Dashboard redirect thành công nhưng API trả 403

User đã đăng nhập, nhưng không có `ROLE_REPORT_EDITOR` hoặc thiếu tenant permission.

**Giải pháp:** xem authorization rules, role mapping và API/resource policy. Không đổi success handler vì authentication đã thành công.

### Tình huống F — Đổi success handler làm session concurrent limit bị bỏ qua

Ứng dụng đã cấu hình session management nhưng thay handler duy nhất cho OAuth2 Login.

**Giải pháp:** kiểm tra phiên bản Spring Security và cách danh sách success handlers hoạt động. Cân nhắc overload thêm handler (6.3+) để giữ concurrent-session hooks, không lặp redirect.

### Tình huống G — Error page tạo vòng lặp login

Failure handler redirect `/auth/failed` nhưng route đó được bảo vệ.

**Giải pháp:** thêm `/auth/failed` vào `permitAll` của chain đúng và không bắt đầu OAuth2 Login tự động tại trang lỗi.

### Tình huống H — Callback từ OP không vào failure handler

OP redirect đến `/login/oauth2/callback/company` nhưng Spring Security mặc định nghe `/login/oauth2/code/{registrationId}`.

**Giải pháp:** đồng bộ redirect URI đã đăng ký tại OP, `ClientRegistration.redirectUri` và authentication matcher trong Reactive OAuth2 Login. Không giải quyết bằng cách thêm catch ở controller khác.

### Tình huống I — OIDC ID Token bị từ chối nhưng app vẫn hiển thị trang chính

Một custom failure handler trả redirect `/dashboard` dù login thất bại.

**Vấn đề:** URL thành công có thể tạo hiểu nhầm; nếu dashboard không bảo vệ sẽ lộ dữ liệu public nhầm trạng thái, nếu bảo vệ có thể lặp login. **Giải pháp:** chuyển tới trang lỗi public và giữ trạng thái chưa authenticated.

### Tình huống J — Background job cần refresh token

Job không có browser session, muốn gọi API sau khi user từng đăng nhập.

**Giải pháp:** đây là bài toán **ReactiveOAuth2AuthorizedClientManager**, lưu token và user delegation, không phải `ServerAuthenticationSuccessHandler`. Thiết kế quyền/offline access và lifecycle/token retention rõ ràng.

### Tình huống K — Trang lỗi hiển thị error_description của OP

Provider trả mô tả dài chứa chi tiết nội bộ. Ứng dụng nối chuỗi đó vào query để support team nhìn dễ hơn.

**Giải pháp:** không đưa raw mô tả vào response/browser logs. Phân loại mã lỗi nội bộ, ghi correlation ID và sử dụng thông điệp chung.

### Tình huống L — Đăng nhập từ hai nhà cung cấp OIDC

Registration `company` và `partner` đều có `preferred_username="admin"`.

**Giải pháp:** khi audit, tách namespace theo registration và **issuer + subject** của ID Token đã xác minh nếu nghiệp vụ cần, không map quyền admin từ username giống nhau trong success handler.

## 24. Câu hỏi ôn tập

**1. Khi nào `ServerAuthenticationSuccessHandler` được gọi?**

Sau khi authentication pipeline reactive tạo được `Authentication` thành công và chuyển kết quả đến handler theo cấu hình. Nó không phải hook cho mọi HTTP request.

**2. Vì sao handler trả `Mono<Void>`?**

Để biểu diễn việc ghi response/redirect và side effects bất đồng bộ trong reactive chain; Spring Security quản lý việc subscribe và completion.

**3. `RedirectServerAuthenticationSuccessHandler("/dashboard")` có luôn redirect dashboard không?**

Không. Saved request có thể được ưu tiên; `/dashboard` thường là fallback.

**4. Failure handler có xử lý một HTTP 403 khi user đã login không?**

Thông thường không. Đó là authorization failure, cần xem `ServerAccessDeniedHandler` hoặc policy tương ứng.

**5. Có nên log `exception.getMessage()` khi OIDC thất bại không?**

Không ghi raw vào browser hoặc log không kiểm soát. Phân loại lỗi, redaction và correlation ID.

**6. Custom success handler có thể gây vấn đề gì cho concurrent sessions?**

Việc thay danh sách handlers có thể loại bỏ hooks quản lý phiên; cần kiểm tra semantics của version và dùng cơ chế thêm handlers khi thích hợp.

**7. Có nên dùng login handler để lưu Access Token vào một WebSession attribute tự tạo không?**

Không nếu đã có authorized client repository/service; tạo kho token riêng dễ gây lỗi bảo mật và thiếu đồng bộ.

**8. Với OIDC Login, những gì phải xác minh trước khi coi user đã authenticated?**

Giao dịch OAuth2/OIDC cần kiểm tra correlation, token response, ID Token issuer/audience/signature/thời hạn và nonce theo điều kiện flow, cùng các ràng buộc giao thức khác.

## 25. Tài liệu tham khảo

- Spring Security — Reactive OAuth2 Login Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html
- Spring Security — Reactive OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html
- Spring Security — `ServerHttpSecurity.OAuth2LoginSpec` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2LoginSpec.html
- Spring Security — `ServerAuthenticationSuccessHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationSuccessHandler.html
- Spring Security — `ServerAuthenticationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationFailureHandler.html
- Spring Security — `RedirectServerAuthenticationSuccessHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html
- Spring Security — `RedirectServerAuthenticationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationFailureHandler.html
- Spring Security — Reactive Concurrent Sessions Control: https://docs.spring.io/spring-security/reference/reactive/authentication/concurrent-sessions-control.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700

## 26. Tổng kết

~~~text
Reactive OAuth2/OIDC Login
  |
  +-- Bắt đầu Authorization Code flow
  |     state / PKCE / OIDC nonce theo flow
  |
  +-- OP callback
  |     đổi code -> validate ID Token -> tạo Authentication
  |
  +-- Authentication THÀNH CÔNG
  |     ServerAuthenticationSuccessHandler
  |       -> audit nếu cần (non-blocking)
  |       -> saved request nếu có
  |       -> hoặc /dashboard
  |
  +-- Authentication THẤT BẠI
        ServerAuthenticationFailureHandler
          -> phân loại lỗi an toàn
          -> audit/metrics nếu cần
          -> redirect /auth/failed hoặc response chung

Không nhầm:
  ServerAuthenticationSuccessHandler
    != ReactiveOAuth2AuthorizationSuccessHandler của client manager

  ServerAuthenticationFailureHandler
    != ServerAccessDeniedHandler cho một request đã authenticated

  WebFlux ServerWebExchange/Mono<Void>
    != Servlet HttpServletRequest/HttpServletResponse
~~~

**Bốn điều cần ghi nhớ:**

1. **`ServerAuthenticationSuccessHandler` xử lý authentication thành công trên Reactive WebFlux**, thường là redirect về saved request hoặc một route fallback. `RedirectServerAuthenticationSuccessHandler` giúp giữ hành vi browser-login nhất quán.
2. **`ServerAuthenticationFailureHandler` xử lý authentication thất bại**, thường redirect về trang lỗi công khai. Không chuyển raw exception/error description hoặc credential ra browser.
3. **Handler phải trả về reactive chain đầy đủ**, không tự `subscribe()`, không block event-loop và không ghi nhiều responses cho cùng request.
4. **Tùy biến phải giữ các ranh giới bảo mật và lifecycle**: validation OIDC trước handler, SecurityContext/WebSession, saved request, concurrent session control, open redirect prevention và tách biệt OAuth2 authorized-client/token refresh.

Khi hiểu đúng hai giao diện này, ứng dụng WebFlux có thể tùy biến trải nghiệm hậu đăng nhập OIDC, audit và thông báo lỗi mà không vô tình làm suy yếu xác thực, phá session management hoặc trộn lẫn trách nhiệm OAuth2 Login với việc gọi API bằng Access Token.
