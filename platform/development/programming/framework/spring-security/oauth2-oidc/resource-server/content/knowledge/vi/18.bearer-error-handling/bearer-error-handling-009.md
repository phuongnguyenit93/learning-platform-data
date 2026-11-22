# Không chuyển lỗi xác thực API thành trang đăng nhập HTML ngoài dự kiến

Trong một **Spring Security OAuth 2.0 / OIDC Resource Server**, client gọi API bằng **Bearer access token**. Khi token thiếu, hết hạn, sai chữ ký, sai issuer/audience hoặc không đáp ứng chính sách xác thực, phản hồi mong đợi của **API** là một lỗi HTTP phù hợp — thông thường **401 Unauthorized** với **`WWW-Authenticate: Bearer`** — chứ **không phải** một trang đăng nhập HTML hoặc phản hồi **302 Redirect** tới `/login`.

Điều này đặc biệt quan trọng khi ứng dụng Spring vừa có giao diện web đăng nhập tương tác vừa có REST API, hoặc khi các thành phần `formLogin`, `oauth2Login`, API gateway và reverse proxy cùng tham gia xử lý authentication. Nếu cấu hình security chain không rõ ràng, cùng một request API có thể bị chuyển sang cơ chế đăng nhập dành cho trình duyệt: client nhận HTML, cố parse JSON và báo lỗi khó hiểu; nguy hiểm hơn, client không biết liệu token bị từ chối hay chỉ bị điều hướng sang IdP.

**Nguyên tắc cốt lõi:** yêu cầu API dùng Bearer phải có **authentication entry point dành cho Bearer**, phản hồi HTTP 401/403 có ngữ nghĩa nhất quán, và không khởi động luồng login tương tác ngoài dự kiến. Trang login/redirect chỉ nên xuất hiện ở **những URL thực sự thuộc luồng đăng nhập cho người dùng cuối**.

> **Bối cảnh minh họa:** Orders API tại `https://api.example.com/api/**` chấp nhận JWT access token có `aud=orders-api`, do issuer `https://login.example.com` phát hành. Một ứng dụng cùng tiến trình cũng có thể phục vụ trang web `/web/**` sử dụng form login hoặc OIDC login. Ví dụ sử dụng Spring Boot 3.x, Spring Security 6.x và Servlet stack; khi dùng WebFlux, cần `SecurityWebFilterChain` và các thành phần reactive tương ứng.

## 1. Hiện tượng: request API nhận HTML thay vì Bearer challenge

Client gửi:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer EXPIRED_OR_INVALID_ACCESS_TOKEN
Accept: application/json
```

Phản hồi **không mong muốn**:

```http
HTTP/1.1 302 Found
Location: /login
```

hoặc sau khi client tự follow redirect:

```http
HTTP/1.1 200 OK
Content-Type: text/html;charset=UTF-8

<!doctype html>
<html>
  <head><title>Sign in</title></head>
  <body><form action="/login" method="post">...</form></body>
</html>
```

Đối với REST client, đây không phải một câu trả lời phù hợp cho yêu cầu đã gửi Bearer credential. Một số triệu chứng thường xuất hiện:

- Frontend gọi `response.json()` rồi gặp lỗi parse vì ký tự đầu tiên là `<` thay vì JSON.
- Ứng dụng mobile không biết phải xử lý một trang đăng nhập HTML ra sao.
- CLI hoặc service-to-service client báo “HTTP 200 thành công” nhưng body thực chất là giao diện login.
- API SDK nhận redirect tới OpenID Provider; tùy cấu hình, redirect gặp CORS hoặc thay đổi origin.
- Gateway hoặc reverse proxy hiển thị trang lỗi/login HTML dù backend đã trả 401 đúng.
- Các monitoring systems đếm 302/200 thành success, che khuất lỗi xác thực thật.

### 1.1. Phản hồi mong đợi

Khi bearer token không hợp lệ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

`Cache-Control: no-store` là một biện pháp có thể cấu hình để tránh cache nội dung nhạy cảm; **không phải mọi phản hồi Bearer 401 đều bắt buộc hiển thị header này**. Phần quan trọng là status **401** và Bearer challenge đúng nghĩa.

Khi không có bearer token cho API bảo vệ, response thường như:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Không nhất thiết có `error="invalid_token"` trong trường hợp **không có token**. Theo RFC 6750, khi request không cung cấp credential xác thực, server không nên trả thêm error code quá cụ thể chỉ vì thiếu token.

Khi token hợp lệ nhưng thiếu scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Header và error parameters chính xác phụ thuộc cách Spring Security nhận diện Authentication và cấu hình handlers. Tuy nhiên, thiếu **quyền** không phải lý do mở trang login HTML cho API caller đã authenticated.

## 2. Hai mô hình authentication phải phân biệt

| Đặc điểm | API Bearer Resource Server | Web login tương tác |
|---|---|---|
| Người gọi | SPA, mobile, backend, CLI, machine-to-machine | Trình duyệt/người dùng |
| Credential chính | `Authorization: Bearer <access-token>` | Session cookie sau form login/OIDC authorization-code |
| Khi chưa xác thực | **401** + Bearer challenge | Có thể **302** đến trang login |
| Khi token sai | **401 invalid_token** | Không phải trường hợp chính của web session |
| Khi thiếu quyền | **403** hoặc lỗi authorization tương ứng | **403** hoặc trang báo lỗi theo UX |
| Hình thức body | Có thể rỗng, JSON hoặc `application/problem+json` | Có thể là HTML |
| Cơ chế Spring | `oauth2ResourceServer().jwt()/opaqueToken()` | `formLogin()` hoặc `oauth2Login()` |
| Đích đến lỗi | Caller xử lý/refresh access token/đăng nhập lại theo flow của nó | Browser tương tác với login page/IdP |

**Resource Server không đồng nghĩa OAuth2 Login Client.**

- **OAuth2 Resource Server** xác minh **access token** được gửi để gọi API.
- **OAuth2 Login Client** khởi động luồng đăng nhập qua Authorization Server/OpenID Provider và quản lý kết quả đăng nhập cho ứng dụng web.
- Một backend có thể giữ cả hai vai trò, nhưng phải định nghĩa rõ request nào thuộc vai trò nào.
- Không nên dùng redirect OIDC authorization endpoint như phản hồi mặc định của một API bearer request.

### 2.1. Vì sao 302 không thay thế 401?

HTTP 302 mang ngữ nghĩa **chuyển hướng tài nguyên**. Nó không truyền đạt đầy đủ rằng Bearer token không hợp lệ. Các client còn có thể:

- Tự follow redirect và nhận 200 HTML, làm mất thông tin 401 ban đầu.
- Chuyển method hoặc xử lý payload khác tùy redirect status/client.
- Chặn redirect cross-origin do CORS hoặc browser security policy.
- Vô tình gửi request tới một endpoint login không thuộc hợp đồng API.

Một ứng dụng web có thể chủ động điều hướng người dùng đến trang đăng nhập **sau khi client nhận 401**. Nhưng quyết định UX đó nên thuộc **client**, không phải một redirect ngầm do API thực hiện.

## 3. Bearer error semantics theo RFC 6750

RFC 6750 mô tả cách dùng bearer access token trong HTTP và trường `WWW-Authenticate` cho lỗi liên quan.

### 3.1. Các tình huống điển hình

| Request/Token | Authentication | Phản hồi thường gặp |
|---|---|---|
| Không cung cấp token cho endpoint yêu cầu auth | Chưa authenticated | **401**, `WWW-Authenticate: Bearer` |
| Token malformed hoặc sai cách cung cấp | Không thể sử dụng credential | **400 invalid_request** hoặc error phù hợp tùy trường hợp |
| Token đã hết hạn | Không hợp lệ | **401 invalid_token** |
| JWT sai signature, issuer hoặc audience | Không hợp lệ | **401 invalid_token** |
| Opaque token introspection `active=false` | Không hợp lệ | **401 invalid_token** |
| Token hợp lệ nhưng thiếu `orders.read` | Đã authenticated, thiếu scope | **403 insufficient_scope** |
| Token hợp lệ, đủ scope nhưng order thuộc người khác | Đã authenticated, object policy từ chối | **403** hoặc **404** theo chính sách API |
| Authorization Server/JWKS/introspection endpoint outage | Không thể hoàn tất xác thực | **Fail closed**, error mapping hạ tầng theo thiết kế; không redirect login |

### 3.2. `invalid_request`, `invalid_token` và `insufficient_scope`

- **`invalid_request`:** yêu cầu cung cấp bearer token bị sai chuẩn, chẳng hạn dùng nhiều phương thức truyền token không được phép hoặc tham số không phù hợp; status có thể là 400 theo RFC 6750.
- **`invalid_token`:** token đã hết hạn, bị thu hồi, malformed về nội dung xác thực hoặc không hợp lệ theo chính sách của Resource Server; thường dùng 401.
- **`insufficient_scope`:** token được xác thực nhưng quyền được cấp không đủ để truy cập tài nguyên; thường dùng 403.

Không biến mọi exception thành `invalid_token` nếu căn nguyên là lỗi máy chủ, lỗi cấu hình client introspection, hoặc truy cập vào dữ liệu không được cấp quyền. Việc phân loại đúng giúp client và đội vận hành biết phải làm gì.

### 3.3. `WWW-Authenticate` là một phần của giao thức

Đây không chỉ là header trang trí. Ví dụ:

```http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

hoặc:

```http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
```

Header có thể có `realm`, `error_description` hoặc `scope` tùy tình huống. Không bắt buộc phải công khai toàn bộ chi tiết lỗi nội bộ. Nếu thêm `error_description`, không đưa token, subject, key ID nhạy cảm, policy nội bộ hoặc bí mật ra ngoài.

**Tránh tự ghi đè `WWW-Authenticate`** bằng Basic challenge hoặc header trống khi đang xử lý bearer authentication error.

## 4. Luồng exception và authentication entry point trong Spring Security

Các thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| `BearerTokenAuthenticationFilter` | Trích Bearer token từ request, kích hoạt xác thực |
| `AuthenticationManager` | Chọn provider phù hợp |
| `JwtAuthenticationProvider` / `OpaqueTokenAuthenticationProvider` | Xác thực JWT hoặc opaque token |
| `JwtDecoder` / `OpaqueTokenIntrospector` | Xác minh token hoặc introspection |
| `ExceptionTranslationFilter` | Chuyển các `AuthenticationException` / `AccessDeniedException` phát sinh downstream thành phản hồi phù hợp |
| `AuthenticationEntryPoint` | Xử lý tình huống cần authentication: 401 hoặc redirect tùy loại |
| `AccessDeniedHandler` | Xử lý `AccessDeniedException` khi request không đủ quyền |
| `BearerTokenAuthenticationEntryPoint` | Tạo phản hồi/challenge Bearer |
| `BearerTokenAccessDeniedHandler` | Xử lý thiếu quyền trong mô hình Bearer |
| `LoginUrlAuthenticationEntryPoint` | Chuyển hướng browser sang login URL khi phù hợp |

Một điểm kỹ thuật quan trọng: `BearerTokenAuthenticationFilter` có thể **trực tiếp gọi entry point** khi xác thực bearer token thất bại. Không phải mọi lỗi đều đi qua `ExceptionTranslationFilter`. Vì vậy cấu hình đúng **entry point của Resource Server** đặc biệt quan trọng.

### 4.1. Sơ đồ phân nhánh

```mermaid
flowchart TD
    A["GET /api/orders/42"] --> B["SecurityFilterChain API"]
    B --> C{"Có Bearer token?"}
    C -->|Có| D["BearerTokenAuthenticationFilter / JwtDecoder hoặc introspection"]
    D --> E{"Token hợp lệ?"}
    E -->|Không| F["BearerTokenAuthenticationEntryPoint"]
    F --> G["401 + WWW-Authenticate: Bearer"]
    E -->|Có| H["SecurityContext và authorities"]
    C -->|Không| I["Tiếp tục chuỗi cho endpoint"]
    I --> J{"Endpoint yêu cầu auth?"}
    J -->|Có| F
    J -->|Không| K["Public endpoint"]
    H --> L{"Scope/role/ownership hợp lệ?"}
    L -->|Không| M["BearerTokenAccessDeniedHandler / domain policy"]
    M --> N["403 hoặc 404 theo hợp đồng"]
    L -->|Có| O["Xử lý nghiệp vụ"]
```

Ở đường **API**, không có nhánh mặc định tới `/login`. Đối với đường **web tương tác**, entry point khác có thể chuyển hướng browser đến login page hoặc OpenID Provider.

### 4.2. Vì sao Spring đôi khi chọn trang login?

Spring Security có thể có **nhiều cơ chế xác thực** trên cùng application:

- `formLogin()` cung cấp luồng login qua HTML form.
- `oauth2Login()` hỗ trợ đăng nhập tương tác bằng OAuth2/OIDC.
- `httpBasic()` cung cấp HTTP Basic challenge.
- `oauth2ResourceServer()` cung cấp Bearer token authentication.

Khi có nhiều authentication entry points, Spring có thể dùng **request matching** và **content negotiation** để chọn cách xử lý. Nếu cấu hình không rõ, một request API có thể bị xử lý bằng entry point dành cho form login hoặc OIDC login, dẫn tới redirect.

**Không dựa vào việc header `Accept: application/json` luôn “cứu” được API.** Một API caller có thể gửi `Accept: */*` hoặc thậm chí `text/html`; security boundary phải đến từ URL/security chain và contract xác thực, không phụ thuộc một header có thể thay đổi tùy client.

## 5. Tách SecurityFilterChain cho API và web tương tác

Giải pháp rõ ràng nhất trong ứng dụng có cả API và giao diện web là **hai security chains với đường dẫn không chồng lấn**, và chain API có thứ tự ưu tiên cao hơn.

Giả sử:

```text
/api/**   → OAuth2 Resource Server, Bearer only
/web/**   → Web app, form login hoặc OIDC login
/login    → Trang login tương tác
```

### 5.1. Dependencies minh họa

Với Spring Boot Servlet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    // Chỉ cần khi ứng dụng đồng thời là OAuth2 Login Client.
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Nếu API là một service chỉ phục vụ Bearer token, **không cần** thêm starter OAuth2 Client hoặc `formLogin()` chỉ để xử lý 401.

### 5.2. Cấu hình JWT issuer và audience

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
```

`audiences` là thuộc tính có trên các bản Spring Boot phù hợp; nếu dùng custom decoder hoặc phiên bản khác, cần tự cấu hình audience validator. Nếu yêu cầu JWT access token theo RFC 9068, còn phải kiểm tra token type `at+jwt` và các claims theo hồ sơ.

### 5.3. Chain ưu tiên 1: API chỉ dùng Bearer

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            // API minh họa chỉ nhận Bearer header, không dùng cookie session.
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .oauth2Login(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new BearerTokenAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenAccessDeniedHandler()
                )
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/web/**", "/login", "/logout")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/web/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain remainingPaths(HttpSecurity http) throws Exception {
        // Ví dụ phòng thủ: các đường dẫn khác chưa được gán chain
        // không tự được công khai do thiếu matcher.
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .build();
    }
}
```

**Phân tích chính sách:**

- `@Order(1)` đặt chain dành cho `/api` và `/api/**` lên trước.
- `securityMatcher` xác định **chain có áp dụng cho request hay không**. Đây là ranh giới quan trọng nhất để tránh request API bị xử lý bằng login chain.
- API chain cấu hình `oauth2ResourceServer(...jwt(...))` và rõ ràng đặt `BearerTokenAuthenticationEntryPoint`.
- `formLogin`, `oauth2Login` và `httpBasic` bị vô hiệu hóa trong **chain API**, tránh cơ chế login/challenge khác xuất hiện do vô tình thêm configuration.
- `requestCache` bị tắt ở API để không có hành vi lưu request rồi chuyển hướng sau login.
- Web chain chỉ áp dụng cho `/web/**`, `/login`, `/logout`, nên có thể dùng form login tương tác.
- Chain cuối **deny all** để tránh endpoint mới nằm ngoài các matcher trở thành công khai ngoài ý muốn.

**Giới hạn cần hiểu:** ví dụ này giả định API **chỉ xác thực bằng Bearer header** và không dùng cookie/browser session cho các hành động thay đổi trạng thái. Vì vậy nó vô hiệu hóa CSRF trong API chain. Nếu cùng API còn chấp nhận cookie hoặc trình duyệt tự gửi credential, không sao chép `csrf(...disable)`; phải thiết kế bảo vệ CSRF phù hợp. Chain web vẫn giữ CSRF theo mặc định của Spring Security.

### 5.4. Vì sao cần chain cuối?

`securityMatcher("/api/**")` không có nghĩa mọi URL của ứng dụng được chain này bảo vệ. Ví dụ `/admin/export` hoặc `/internal/jobs` không khớp `/api/**`.

Nếu không có chain nào khớp một request, **Spring Security có thể không bảo vệ request ấy bằng các filter mong đợi**. Trong một hệ thống nhiều chain, cần quyết định rõ những URL còn lại được bảo vệ bởi chain nào. Một fallback `denyAll()` là lựa chọn phòng thủ cho những URL chưa phân loại, nhưng ứng dụng thật có thể cần cấu hình riêng cho health checks, static assets, management endpoints hoặc OIDC callback.

### 5.5. Nếu ứng dụng chỉ là Resource Server API

Khi không có web login, dùng một chain duy nhất cũng hợp lý:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().authenticated()
        )
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint(
                new BearerTokenAuthenticationEntryPoint()
            )
            .accessDeniedHandler(
                new BearerTokenAccessDeniedHandler()
            )
        )
        .build();
}
```

Mẫu này không cài form login/OIDC login. Nếu API là bearer-only và có yêu cầu CSRF/session cụ thể, bổ sung cấu hình tương ứng. Không nên vô hiệu hóa bảo vệ bảo mật khác chỉ vì muốn 401 thay vì HTML.

## 6. Nếu web dùng oauth2Login() thay vì formLogin()

Ứng dụng giao diện web có thể dùng **OAuth2 Login** để redirect người dùng tới OpenID Provider:

```java
@Bean
@Order(2)
SecurityFilterChain oidcWebSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher(
            "/web/**",
            "/oauth2/**",
            "/login/oauth2/**",
            "/logout"
        )
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/web/public/**", "/oauth2/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .build();
}
```

Đoạn này **thay thế web chain formLogin** của ví dụ trước, không đăng ký song song hai bean cùng `@Order(2)` và matcher chồng lấn. Muốn dùng thực tế cần `ClientRegistrationRepository`/OIDC client config đúng và xác định lại callback routes, CSRF, logout, public assets.

**Không để route `/api/**` rơi vào chain này.** Một API không có Bearer credential không nên tự sinh redirect:

```http
Location: /oauth2/authorization/<registration-id>
```

Nếu frontend SPA cần người dùng đăng nhập lại, frontend nên tự thực hiện **OIDC Authorization Code + PKCE** với cơ chế client thích hợp sau khi xử lý lỗi API, không để Resource Server tự biến 401 thành login flow.

## 7. Khi nào cần BearerTokenAuthenticationEntryPoint?

`BearerTokenAuthenticationEntryPoint` của Spring Security chuyên tạo phản hồi authentication theo mô hình Bearer, dựa vào `AuthenticationException` mà nó nhận được.

Các trường hợp:

- Endpoint yêu cầu authentication nhưng request không có Bearer token.
- Token sai/đã hết hạn khiến provider/decoder từ chối.
- Một lỗi Bearer xác định được `OAuth2Error` để điền `WWW-Authenticate` khi phù hợp.

Thay vì:

```java
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(
        new LoginUrlAuthenticationEntryPoint("/login")
    )
)
```

ở chain API, nên dùng:

```java
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(
        new BearerTokenAuthenticationEntryPoint()
    )
)
```

**Không nên tự trả redirect trong `AuthenticationEntryPoint` của API** để “giúp client đăng nhập”. Điều đó phá hợp đồng lỗi Bearer và gây khó cho mobile/CLI/backend.

### 7.1. BearerTokenAccessDeniedHandler xử lý gì?

Khi token hợp lệ nhưng thiếu authority:

```java
.exceptionHandling(ex -> ex
    .accessDeniedHandler(
        new BearerTokenAccessDeniedHandler()
    )
)
```

Handler hỗ trợ tạo phản hồi **403** và, khi authentication đủ thông tin theo mô hình OAuth2 token, có thể điền thông tin `insufficient_scope` vào Bearer challenge.

Không nhầm:

- **AuthenticationEntryPoint:** chưa được xác thực hoặc credential không hợp lệ → hướng tới 401.
- **AccessDeniedHandler:** request đã có ngữ cảnh authentication nhưng không có quyền được yêu cầu → hướng tới 403 hoặc domain response.

Trong trường hợp authentication anonymous/insufficient, `ExceptionTranslationFilter` có thể khởi động entry point thay vì access-denied handler. Vì vậy status cần dựa trên trạng thái xác thực và lỗi thực tế.

## 8. Tách lỗi authentication khỏi lỗi authorization

Ví dụ API GET cần `SCOPE_orders.read`:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
)
```

Có ba tình huống:

| Bearer token | Quyền | Phản hồi |
|---|---|---|
| Không gửi token | Không có Authentication hợp lệ | **401**, Bearer challenge |
| JWT có chữ ký sai | Không có Authentication hợp lệ | **401 invalid_token** |
| JWT hợp lệ, chỉ có `orders.write` | Thiếu `orders.read` | **403** (thường `insufficient_scope`) |

Nếu service còn kiểm tra ownership, một JWT hợp lệ có `orders.read` vẫn có thể bị từ chối vì order thuộc tenant khác. Đây là **object-level authorization**, không phải lý do trả trang đăng nhập.

### 8.1. Thiếu scope không nên biến thành “mời login”

Đăng nhập lại có thể hoặc không giúp client lấy scope mới; việc cấp quyền phụ thuộc Authorization Server, consent, role, client registration và policy. API không nên suy đoán rằng mọi `403` đều sửa được bằng login lại.

SPA nên xử lý hai nhóm lỗi khác nhau:

- **401:** token thiếu/không hợp lệ; có thể thử cơ chế lấy token mới nếu client được phép, hoặc yêu cầu user đăng nhập theo luồng OIDC riêng.
- **403:** token hợp lệ nhưng thiếu quyền; hiển thị thông báo quyền hoặc hướng dẫn theo nghiệp vụ, không tự động lặp login vô hạn.

## 9. Có cần trả JSON body cho 401/403 không?

**Không bắt buộc.** Với Bearer, HTTP status và `WWW-Authenticate` là hợp đồng cốt lõi. Một API có thể chọn body rỗng.

Tuy nhiên nhiều frontend/mobile mong muốn thông báo JSON nhất quán, ví dụ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401
}
```

Hoặc:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403
}
```

`application/problem+json` là dạng mô tả lỗi HTTP chuẩn hóa (RFC 9457). Cần giữ thông điệp ngắn, không lộ token/raw claims, không giải thích nội bộ về khóa, tenant, user tồn tại hay không.

### 9.1. Custom entry point JSON nhưng giữ Bearer challenge

Nếu muốn body JSON, **đừng thay toàn bộ phản hồi Bearer bằng một ResponseEntity từ controller**. Lỗi xác thực ở filter chain thường xảy ra **trước khi controller chạy**.

Có thể dùng một wrapper `AuthenticationEntryPoint`: để Spring tạo Bearer challenge trước, rồi thêm body.

```java
package com.example.orders.security;

import java.io.IOException;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;

public final class JsonBearerAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint bearer =
        new BearerTokenAuthenticationEntryPoint();

    private final ObjectMapper objectMapper;

    public JsonBearerAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        // Bảo toàn status/header WWW-Authenticate theo Bearer.
        bearer.commence(request, response, exception);

        if (response.isCommitted()) {
            return;
        }

        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE
        );
        response.setCharacterEncoding("UTF-8");

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "type", "about:blank",
                "title", "Unauthorized",
                "status", 401
            )
        );
    }
}
```

Một wrapper tương tự cho `AccessDeniedHandler`:

```java
package com.example.orders.security;

import java.io.IOException;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

public final class JsonBearerAccessDeniedHandler
        implements AccessDeniedHandler {

    private final BearerTokenAccessDeniedHandler bearer =
        new BearerTokenAccessDeniedHandler();

    private final ObjectMapper objectMapper;

    public JsonBearerAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException {

        // Giữ status và Bearer challenge từ handler chuẩn.
        bearer.handle(request, response, exception);

        if (response.isCommitted()) {
            return;
        }

        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE
        );
        response.setCharacterEncoding("UTF-8");

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "type", "about:blank",
                "title", "Forbidden",
                "status", 403
            )
        );
    }
}
```

Gắn hai handler này vào **chain API**:

```java
@Bean
SecurityFilterChain apiChain(
        HttpSecurity http,
        ObjectMapper objectMapper) throws Exception {

    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint(
                new JsonBearerAuthenticationEntryPoint(objectMapper)
            )
            .accessDeniedHandler(
                new JsonBearerAccessDeniedHandler(objectMapper)
            )
        )
        .build();
}
```

Đây là **biến thể thay thế** của API chain ở phần 5, không phải một bean có thể đăng ký song song trên cùng `/api/**` mà không kiểm soát `@Order`. Nếu dùng nhiều filter chains, giữ một cấu hình duy nhất bao phủ đường dẫn API.

**Lưu ý về custom error body:**

- Không gọi `sendRedirect(...)` hoặc trả view template HTML.
- Không ghi body khi response đã committed.
- Giữ `WWW-Authenticate` được tạo bởi handler chuẩn.
- Đảm bảo status thực tế tương ứng với body (401/403).
- Không tự đưa `exception.getMessage()` ra client nếu nó có thể chứa thông tin nhạy cảm.
- Không serialise toàn bộ `Authentication`, `Jwt` hoặc `OAuth2AuthenticatedPrincipal` vào error response.
- Test bằng `curl -i` để xem header/status thật, không chỉ kiểm tra JSON body.

### 9.2. Vì sao không chỉ dùng @RestControllerAdvice?

`@RestControllerAdvice` rất hữu ích cho lỗi xuất phát từ **controller/service**, như dữ liệu không hợp lệ, domain exception hoặc lỗi nghiệp vụ. Nhưng nhiều lỗi authentication xảy ra trong **Spring Security filter chain trước DispatcherServlet** nên không đi qua controller advice như lỗi MVC thông thường.

Muốn thay response cho thiếu/sai Bearer token, dùng **`AuthenticationEntryPoint` / `AccessDeniedHandler`** hoặc thành phần security tương ứng, không chỉ thêm:

```java
@ExceptionHandler(AuthenticationException.class)
```

và mong nó bắt được mọi lỗi trong `BearerTokenAuthenticationFilter`.

Một lỗi khác: middleware của API gateway hoặc global error handler có thể **ghi đè status/header** sau khi Spring Security đã tạo phản hồi đúng. Cần kiểm tra toàn bộ đường đi.

## 10. Không dùng request cache và saved-request redirect cho API

Web login thường có luồng:

```text
Browser gọi /web/account
       |
       v
Chưa đăng nhập
       |
       v
Lưu request /web/account vào RequestCache
       |
       v
302 /login
       |
       v
User đăng nhập
       |
       v
Chuyển browser về /web/account
```

Luồng đó hợp lý cho một ứng dụng web session-based. Nhưng đối với API bearer-only:

```text
Client gọi /api/orders/42 bằng token lỗi
       |
       v
401 WWW-Authenticate: Bearer
       |
       v
Client quyết định lấy access token mới/đăng nhập lại
       |
       v
Client tự gọi lại request khi có credential hợp lệ
```

API không cần lưu request vào HTTP session để redirect sau login. Trong chain API có thể cấu hình:

```java
.requestCache(AbstractHttpConfigurer::disable)
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
)
```

**`STATELESS` không tự nói lên mọi lựa chọn bảo mật khác.** Nó mô tả không dùng HTTP session để lưu/truy xuất security context theo chính sách cấu hình. Nếu ứng dụng còn dùng cookie credentials, vẫn phải xem xét CSRF và các stateful mechanisms tương ứng.

### 10.1. Nếu API vẫn redirect mặc dù đã đặt STATELESS?

Có thể do:

- Chain `formLogin`/`oauth2Login` vẫn khớp trước API chain.
- Authentication entry point custom vẫn là `LoginUrlAuthenticationEntryPoint`.
- API gateway hoặc reverse proxy thêm redirect.
- MVC/controller tự trả `redirect:/login`.
- Request URL không khớp `securityMatcher` mà bạn nghĩ.
- SPA/client đã tự chuyển hướng sau 401; kết quả quan sát không phải response gốc từ API.

`STATELESS` **không phải** một nút “tắt redirect login” thay cho thiết kế security chain và entry point.

## 11. Thứ tự filter chains: lỗi thường xuất hiện ở đây

Spring Security chọn **SecurityFilterChain đầu tiên khớp request** trong `FilterChainProxy`. Một URL API nếu vô tình khớp chain web trước đó có thể bị đối xử như browser.

Ví dụ chưa phù hợp:

```java
@Bean
@Order(1)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .build();
}
```

Chain web đầu tiên **không có `securityMatcher` riêng**, nên có thể khớp mọi URL; chain API thứ hai không bao giờ được chọn cho `/api/orders`. Kết quả là response có thể giống web login thay vì Bearer.

Sửa bằng cách:

1. Đặt `@Order(1)` cho API chain với matcher `/api/**`.
2. Đặt matcher cụ thể cho web chain hoặc fallback có chủ đích.
3. Không dùng nhiều chain có `anyRequest()` matcher bao trùm ở trước API.
4. Kiểm tra biến thể URL `/api` và `/api/**`.
5. Kiểm tra context-path và reverse proxy path rewrites.
6. Test request thiếu token, sai token và Accept `text/html`.

### 11.1. Phân biệt securityMatcher với requestMatchers

```java
.securityMatcher("/api/**")
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
)
```

- `securityMatcher` chọn **SecurityFilterChain** áp dụng cho request.
- `requestMatchers` bên trong `authorizeHttpRequests` chọn **authorization rule** khi chain đã được chọn.

Nếu chain đang sai, thêm `requestMatchers("/api/**").authenticated()` trong chain web **không tự thay entry point** thành Bearer. Cần sửa đúng tầng chọn chain và authentication mechanism.

## 12. Content negotiation: Accept không phải ranh giới an ninh

Một số client gửi:

```http
Accept: application/json
```

nhưng cũng có client gửi:

```http
Accept: */*
```

hoặc browser đang truy cập API trực tiếp gửi:

```http
Accept: text/html,application/xhtml+xml
```

Nếu API contract là Bearer, cả ba trường hợp thiếu access token vẫn cần phản hồi theo Bearer. Đừng dựa vào loại Accept để quyết định **có redirect login hay không**.

### 12.1. Vì sao API bị chuyển HTML khi gọi từ browser?

Spring Security hỗ trợ content negotiation cho các entry points theo cấu hình. Một chain kết hợp `formLogin` và `oauth2ResourceServer` có thể chọn handler khác nhau tùy loại request/matcher. Browser cũng có thể tự follow redirects, tạo cảm giác API trả 200 HTML.

Giải pháp ổn định là **chain API riêng, Bearer entry point rõ ràng**. Content negotiation nên dùng để chọn **format lỗi** (JSON hay problem+json) trong cùng hợp đồng API, không để chọn một luồng login tương tác khác hẳn.

## 13. Client-side: nhận 401 rồi xử lý đăng nhập ở nơi phù hợp

Một SPA có thể gọi:

```javascript
async function loadOrders(accessToken) {
  const response = await fetch("/api/orders", {
    method: "GET",
    headers: {
      Authorization: "Bearer " + accessToken,
      Accept: "application/json"
    }
  });

  if (response.status === 401) {
    // Caller xử lý credential: refresh hoặc khởi động login flow riêng.
    throw new Error("ACCESS_TOKEN_INVALID_OR_MISSING");
  }

  if (response.status === 403) {
    throw new Error("ACCESS_DENIED");
  }

  if (!response.ok) {
    throw new Error("API_REQUEST_FAILED");
  }

  return response.json();
}
```

Đây là ví dụ phản ứng với status, **không phải hướng dẫn tự lưu access token trong localStorage**. Cách lưu token và refresh phụ thuộc kiến trúc browser security: SPA OAuth client, Backend-for-Frontend (BFF), cookie/session và PKCE.

**Điểm cần tránh:** API trả 302 HTML khiến `response.ok` trở thành true sau redirect, client cố parse HTML. Khi API trả 401 đúng, frontend có thể phân biệt lỗi auth với lỗi domain/permission.

### 13.1. Refresh token không thuộc Resource Server endpoint

Nếu client được cấp refresh token, việc làm mới access token thuộc **OAuth client và Authorization Server token endpoint** theo flow hợp lệ, không phải việc Orders API nhận refresh token rồi “đổi lấy Bearer khác” tùy ý.

API chỉ nên nhận access token được cấp cho resource này. Không chấp nhận ID token hoặc refresh token như access token để tránh lỗi.

### 13.2. Tránh vòng lặp login vô hạn

Một quy tắc frontend hợp lý:

- Thấy **401**: nếu có cơ chế refresh hợp lệ, thử tối đa theo chính sách và tránh nhiều request đồng thời cùng refresh; nếu thất bại, điều hướng user tới login thông qua client.
- Thấy **403**: thông báo thiếu quyền hoặc workflow quyền; không liên tục login lại.
- Thấy **503** hay lỗi network: thể hiện sự cố dịch vụ; không xóa phiên/tự đăng xuất tất cả user khi AS đang tạm lỗi.
- Không chuyển mọi response non-200 thành `window.location='/login'`.
- Không tự theo dõi redirect HTML như kết quả thành công của JSON API.

## 14. CORS preflight không phải yêu cầu bearer authentication

Với SPA cross-origin, browser có thể gửi **OPTIONS preflight** trước request dùng `Authorization`:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflight thông thường **không mang bearer access token** của request thật. Nếu Spring Security yêu cầu Bearer cho OPTIONS preflight rồi redirect tới login, browser sẽ báo lỗi CORS khó hiểu.

Cần cấu hình CORS phù hợp và cho preflight đi qua cơ chế đúng. Ví dụ cho ứng dụng có frontend ở `https://app.example.com`:

```java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(
            List.of("https://app.example.com")
        );
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
        );
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type")
        );

        // API minh họa chỉ dùng Authorization Bearer, không cookie.
        cors.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
```

Trong API chain:

```java
.cors(Customizer.withDefaults())
```

Khi có `CorsConfigurationSource` phù hợp, Spring Security có thể xử lý CORS preflight trước khi yêu cầu xác thực cho request thật. CORS policy phải được điều chỉnh theo origin/method/header thực tế. Nếu sử dụng cookie cross-origin, cần thêm các yêu cầu credentials, SameSite và CSRF phù hợp; không sao chép ví dụ bearer-only.

**Không coi mọi 401 khi OPTIONS là do token sai**. Đó có thể là CORS integration lỗi. Không thêm `permitAll()` cho toàn bộ API chỉ để preflight qua.

## 15. Gateway, reverse proxy và ingress có thể tự thêm HTML redirect

Có trường hợp backend Spring Security trả đúng:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

nhưng client thực tế nhận:

```http
HTTP/1.1 302 Found
Location: /auth/login
```

hoặc:

```http
HTTP/1.1 200 OK
Content-Type: text/html

<html>Gateway sign-in</html>
```

Đây có thể là hành vi của:

- API gateway áp login policy chung cho toàn domain.
- Reverse proxy `auth_request` hoặc forward-auth module.
- Service mesh/ingress access policy.
- CDN/WAF custom error page.
- Load balancer/web SSO proxy.
- Frontend dev server proxy hoặc service worker.
- Một lớp `ErrorPageFilter`/application error forwarding khác trong hệ thống.

**Spring Security trong backend không thể tự sửa response đã bị gateway thay đổi**. Cần kiểm tra từng hop và thống nhất rằng **API routes giữ nguyên 401/403, Bearer challenge và format lỗi**, trong khi web routes có thể có interactive login.

### 15.1. Cách xác định redirect đến từ đâu

So sánh:

1. Request gọi trực tiếp **backend instance/service endpoint** trong mạng nội bộ được phép.
2. Cùng request đi qua ingress/gateway.
3. Quan sát status, `Location`, `WWW-Authenticate`, `Content-Type` và request ID.
4. Kiểm tra gateway authentication policy có áp dụng cho `/api/**` không.
5. Kiểm tra proxy có rewrite path trước khi Spring chọn chain không.
6. Kiểm tra 401/403 response body có bị thay thành branded HTML error page không.

Không bỏ xác thực gateway hoặc backend chỉ để hết redirect; hãy gắn **chế độ xử lý Bearer/API** phù hợp với các route API.

### 15.2. Lưu ý với forwarded prefix/context path

Ví dụ bên ngoài gọi:

```text
https://example.com/orders-api/api/orders/42
```

nhưng proxy chuyển backend thành:

```text
/api/orders/42
```

Nếu Spring nhìn thấy path khác so với securityMatcher mong đợi, request có thể đi vào chain web/fallback. Khi debug, kiểm tra **path mà FilterChainProxy thực sự nhận được** thay vì chỉ URL bên ngoài.

## 16. CSRF và browser cookies: đừng tắt một bảo vệ để sửa lỗi redirect

Một API bearer-only, stateless thường không dựa vào cookie được browser tự gửi, nên có thể thiết kế CSRF policy riêng. Nhưng một ứng dụng vừa có login session vừa có API cần cẩn trọng:

- Nếu endpoint có **cookie-based authentication**, browser có thể tự gửi cookie trên cross-site requests → cần xem xét CSRF.
- Nếu endpoint **chỉ** nhận Bearer token trong `Authorization` header do JavaScript/client chủ động gắn, rủi ro CSRF cổ điển có thể khác.
- Nếu vừa nhận Bearer vừa chấp nhận session cookie, không được mặc định tắt CSRF cho toàn application.
- CORS không thay thế CSRF; chúng giải quyết các vấn đề khác nhau.
- `SessionCreationPolicy.STATELESS` không tự chứng minh mọi credential đều không bị browser gửi tự động.

Khi chia chain, cấu hình CSRF phải căn cứ **credential và browser interaction thực tế** của từng chain. Việc tạo 401 Bearer đúng không yêu cầu tắt toàn bộ CSRF protection.

## 17. Một số cấu hình gây nhầm lẫn

### 17.1. Đặt formLogin trong chain bao phủ tất cả URL

```java
http.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
).formLogin(Customizer.withDefaults());
```

Nếu đây là chain đầu tiên khớp `/api/**`, Spring có thể dùng entry point login cho API. Tách chain API trước và web sau.

### 17.2. Trộn oauth2Login và resource server mà không chỉ định entry point

```java
http
    .oauth2Login(Customizer.withDefaults())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults())
    );
```

Cấu hình như vậy không **tự** bảo đảm request API luôn nhận Bearer challenge. Cơ chế chọn entry point phụ thuộc request matcher và các cấu hình còn lại. Khi cùng ứng dụng làm browser client và API RS, đặt rõ matcher/chain và entry point.

### 17.3. Dùng `.exceptionHandling().authenticationEntryPoint(loginEntryPoint)` chung

Một entry point login tùy chỉnh ở phạm vi quá rộng có thể được áp cho cả API Bearer. Đặt nó vào **web chain**; với API chain dùng `BearerTokenAuthenticationEntryPoint`.

### 17.4. Chỉ sửa @ControllerAdvice

Lỗi Bearer token thường xảy ra trước controller. Cần sửa Spring Security entry point/handlers thay vì chỉ thêm `@RestControllerAdvice`.

### 17.5. Luôn redirect khi user chưa authenticated

Một helper chung kiểu “anonymous → /login” hợp lý với HTML page nhưng không với API. Dựa trên **route/authentication model**, không chỉ dựa trên `Authentication.isAuthenticated()`.

### 17.6. Gửi 200 HTML error page vì “trang lỗi thân thiện”

Một API đã trả status 200 khiến client và monitoring hiểu sai. Giữ status 401/403/5xx phù hợp và body đúng media type nếu cần; trang HTML là lựa chọn UI, không phải hợp đồng lỗi API.

### 17.7. Dùng HTTP Basic challenge thay Bearer

Nếu Resource Server chấp nhận Bearer, một response:

```http
WWW-Authenticate: Basic realm="App"
```

có thể khiến browser bật hộp thoại Basic Authentication, không phù hợp với OAuth Bearer API. Không bật `httpBasic` trên chain bearer-only nếu không có mục đích được định nghĩa rõ.

## 18. OAuth2 opaque token cũng phải trả Bearer, không phải HTML login

Sự khác biệt JWT/opaque nằm ở **cách Resource Server xác thực access token**, không phải ngữ nghĩa phản hồi lỗi Bearer.

JWT:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults())
)
```

Opaque:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Cả hai đều thường nhận access token qua `Authorization: Bearer ...`. Nếu token không hợp lệ, API cần phản hồi theo Bearer authentication semantics, không chuyển tới `/login`.

Với opaque token introspection:

- `active=false` thường dẫn tới token không hợp lệ, trả 401.
- `active=true` nhưng thiếu scope dẫn tới 403.
- AS introspection timeout, sai client secret hoặc TLS lỗi là sự cố dependency/cấu hình; phải **fail closed**, không chấp nhận token theo suy đoán và không redirect user để che lỗi.
- Nếu muốn map lỗi AS thành 503 thay vì 401 trong một số trường hợp, cần phân loại exception và test; **không phải mọi lỗi mạng đều được Spring tự map 503**.

## 19. Kiểm thử: chứng minh API không trả HTML login

Một số test chỉ kiểm tra `status().isUnauthorized()` vẫn chưa phát hiện lỗi nếu response 401 có body HTML ngoài hợp đồng. Nên kiểm tra đồng thời **status, header, redirect và Content-Type** khi cần.

### 19.1. MockMvc: thiếu token nhưng Accept text/html vẫn phải nhận 401

Ví dụ test Spring Boot có `MockMvc`:

```java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiBearerErrorTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiNeverRedirectsToHtmlLoginWhenTokenIsMissing()
            throws Exception {
        mvc.perform(get("/api/orders/42")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")
            ))
            .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }
}
```

Điều cần thấy:

- Dù client gửi `Accept: text/html`, API chain vẫn xử lý như **Bearer API**.
- Không có `Location: /login` hoặc `Location: /oauth2/authorization/...`.
- `WWW-Authenticate` bắt đầu bằng `Bearer`.

Test này kiểm tra **cấu hình filter chain với request thiếu token**, không chứng minh JwtDecoder xác minh signature đúng. Với token thật, cần integration test riêng.

### 19.2. MockMvc: token hợp lệ nhưng thiếu scope phải 403

Với `spring-security-test`:

```groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.http.MediaType;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void validJwtWithWrongScopeDoesNotOpenLoginPage() throws Exception {
    mvc.perform(get("/api/orders/42")
            .accept(MediaType.APPLICATION_JSON)
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_unrelated")
            )))
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
}
```

Đây là một test fragment đặt trong test class `MockMvc` đầy đủ. `jwt()` tạo authentication giả lập, **không kiểm tra chữ ký JWT thật**. Nó phù hợp để kiểm tra authorization và response handling, không thay thế test decoder.

### 19.3. MockMvc: web page có thể redirect login

Trong chain web riêng, một request browser tới trang được bảo vệ có thể mong đợi redirect:

```java
@Test
void webPageMayRedirectToLogin() throws Exception {
    mvc.perform(get("/web/account")
            .accept(MediaType.TEXT_HTML))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            HttpHeaders.LOCATION,
            startsWith("http")
        ));
}
```

**Chú ý:** `Location` trong MockMvc/Spring có thể là đường dẫn tương đối `/login` thay vì absolute URL. Vì vậy ví dụ khẳng định `startsWith("http")` không phải luôn đúng nếu cấu hình redirect tương đối. Khi áp dụng, nên kiểm tra đích redirect phù hợp ứng dụng, ví dụ dùng matcher cho `/login` hoặc `redirectedUrlPattern("**/login")` theo test framework.

Mục đích của test là chứng minh **web và API có hành vi lỗi khác nhau đúng thiết kế**, không yêu cầu mọi web redirect có cùng dạng Location.

### 19.4. Integration test token sai/chữ ký sai

Với end-to-end authentication test:

1. Gửi HTTP request có header `Authorization: Bearer <TEST_JWT>`.
2. Dùng issuer/JWKS giả lập tin cậy trong test environment.
3. Kiểm tra token hết hạn/sai issuer/sai audience/sai chữ ký đều bị từ chối.
4. Đảm bảo response **401 Bearer**, không có `Location` login.
5. Kiểm tra scope sai trả **403**, không redirect.
6. Test cả `Accept: application/json`, `Accept: text/html` và `Accept: */*`.
7. Test qua **gateway thực hoặc staging ingress** để phát hiện 401 bị viết lại thành HTML.
8. Kiểm tra không lộ raw token/claims nhạy cảm qua body, header, logs.

Nếu dùng opaque token, thay JWKS giả bằng introspection test server phản hồi `active=true/false` và các lỗi client credential/network được kiểm soát.

## 20. Kiểm tra thực tế bằng curl

`curl` mặc định không tự follow redirect nếu không bật `-L`, nên thuận tiện để xem phản hồi **gốc**.

### 20.1. Không có token

```bash
curl --include \
  --header "Accept: application/json" \
  "https://api.example.com/api/orders/42"
```

Kỳ vọng endpoint bảo vệ:

```text
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Không mong muốn:

```text
HTTP/1.1 302 Found
Location: /login
```

### 20.2. Token sai và client chấp nhận HTML

```bash
curl --include \
  --header "Accept: text/html" \
  --header "Authorization: Bearer INVALID_TEST_TOKEN" \
  "https://api.example.com/api/orders/42"
```

Kỳ vọng vẫn là 401 theo Bearer, không có HTML login.

### 20.3. Kiểm tra gateway có rewrite response

So sánh các header giữa backend trực tiếp và URL public:

```bash
# URL public qua ingress/gateway:
curl --include \
  "https://api.example.com/api/orders/42"

# URL nội bộ bên trong môi trường được phép, dùng trong debug:
curl --include \
  "http://orders-api.internal:8080/api/orders/42"
```

Ví dụ nội bộ `http://...` chỉ dùng để minh họa debug trong mạng được bảo vệ; môi trường có yêu cầu mTLS/TLS nội bộ phải dùng HTTPS tương ứng. Không mở rộng endpoint nội bộ ra Internet hoặc bypass authentication để thử.

Quan sát:

- `HTTP status`.
- `WWW-Authenticate`.
- `Location`.
- `Content-Type`.
- `Server`, request ID hoặc proxy headers nếu an toàn.
- Nếu có 302, target là `/login`, `/oauth2/authorization/...` hay login host của gateway?

**Không đặt access token thật lên command line nếu log/shell history có nguy cơ lộ credential.** Dùng test token vô hại hoặc cách truyền credential được tổ chức phê duyệt.

## 21. Phân biệt 401 từ API với 401 của hệ thống khác

Một ứng dụng có nhiều hop:

```text
OAuth Client
    |
    v
CDN / WAF
    |
    v
API Gateway / Ingress
    |
    v
Spring Security Resource Server
    |
    +--> JWT JWKs endpoint hoặc opaque introspection endpoint
    |
    v
Domain service
```

Mỗi hop có thể tạo 401/403 hoặc HTML error response. Cần hỏi:

- Ai đã phát hành **status đầu tiên**?
- Có response nào bị gateway đổi thành redirect?
- Bearer challenge còn nguyên không?
- Lỗi là **access token của caller** hay **client secret của Resource Server** khi introspect?
- Có request trace/correlation ID để đối chiếu hai tầng không?
- Policy nào áp dụng cho path được backend nhìn thấy?

Một HTTP 401 từ introspection endpoint có thể nghĩa **Resource Server dùng client secret sai**, không phải caller cần mở browser login. API phải fail closed và báo lỗi vận hành đúng, không chuyển toàn bộ caller sang trang đăng nhập ngoài dự kiến.

## 22. Những trường hợp đặc biệt

### 22.1. API public

Endpoint có `permitAll()` thực sự public có thể trả 200 khi không có token. Không ép mọi request `/api/**` phải 401 nếu authorization policy cho phép anonymous.

Tuy nhiên, với bearer token **được cung cấp nhưng không hợp lệ**, `BearerTokenAuthenticationFilter` vẫn có thể cố xác thực và trả lỗi trước khi đánh giá `permitAll()`, tùy security filter chain. Nếu public endpoint có yêu cầu chấp nhận caller không token, test cả không token và token sai để có hành vi rõ ràng.

### 22.2. API “health” không cần Bearer

`/actuator/health` hoặc đường health riêng có thể thuộc chain khác. Cần quyết định endpoints nào cho phép unauthenticated, endpoints nào chứa thông tin nhạy cảm phải bảo vệ. Đừng đưa tất cả Actuator vào `permitAll()` chỉ vì muốn load balancer health check chạy được.

### 22.3. API dùng cookie qua BFF

Nếu frontend gọi BFF bằng session cookie, BFF có thể là web application sử dụng 302 login cho **trang HTML**, nhưng endpoint JSON của BFF cũng thường nên có **hợp đồng lỗi JSON/401 riêng** để SPA không nhận HTML ngoài dự kiến. Lúc này không nhất thiết dùng Bearer challenge ở browser-to-BFF layer, vì credential thực tế là cookie session. Phải phân biệt **credential ở từng hop**.

Ví dụ:

```text
Browser --cookie--> BFF --Bearer access token--> Orders API
```

Orders API vẫn trả Bearer 401 khi access token BFF dùng không hợp lệ. BFF có thể ánh xạ lỗi phù hợp cho browser theo hợp đồng riêng, nhưng không nên vô tình trả trang HTML cho một request JSON.

### 22.4. WebSocket, SSE, GraphQL

Các giao thức hoặc endpoint đặc biệt có thể dùng security context và error framing riêng:

- GraphQL có thể trả `200` với `errors` theo hợp đồng GraphQL ngay cả khi authorization resolver thất bại, nhưng authentication ở HTTP handshake cần được thiết kế rõ.
- WebSocket handshake và message-level auth cần cơ chế phù hợp, không chỉ áp một controller REST rule.
- SSE là HTTP stream; lỗi authentication trước khi stream bắt đầu cần status phù hợp, tránh mở stream HTML login.

Dù thế nào, **đừng tự chuyển token failure thành trang login HTML** nếu endpoint được định nghĩa là API tiêu thụ bởi máy.

### 22.5. OIDC login callback không phải API nghiệp vụ

Các route `/login/oauth2/code/{registrationId}` và `/oauth2/authorization/{registrationId}` phục vụ **OAuth2 Login Client**. Chúng có thể hợp lệ khi redirect; chỉ không nên để các route ấy trở thành entry point mặc định cho `/api/orders/**`.

## 23. Một ma trận chẩn đoán nhanh

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `/api/**` trả 302 `/login` khi không token | Form-login entry point khớp API | API chain riêng + Bearer entry point |
| API trả 302 `/oauth2/authorization/...` | OAuth2 login chain khớp API | Phân tách web client và RS matcher |
| `/api/**` trả `200 text/html` | HTTP client đã follow redirect hoặc error page rewrite | Xem response đầu tiên, gateway và Location |
| API Accept JSON hoạt động, Accept HTML redirect | Content negotiation đang chọn login entry point | Cấu hình Bearer API chain không phụ thuộc Accept |
| API 401 nhưng browser báo CORS | Preflight/CORS config sai hoặc gateway chặn | Cấu hình CorsConfigurationSource và chain |
| JWT sai bị 401, nhưng scope sai redirect | AccessDeniedHandler/exception translation không đúng | BearerTokenAccessDeniedHandler và authorization mapping |
| Controller advice không bắt được lỗi JWT | Lỗi ở security filter trước MVC | AuthenticationEntryPoint/AccessDeniedHandler |
| Backend 401, gateway trả HTML | Gateway custom auth/error page | Chỉnh API-route handling ở gateway |
| Không có token ở `/api/**` lại được trang login | Chain order/matcher sai | `@Order`, `securityMatcher`, fallback deny-all |
| 401 client introspection sai bị coi user sai | Lỗi outbound RS→AS | Phân loại dependency/client-auth failure |
| SPA liên tục refresh/login khi 403 | Client coi 403 giống 401 | Phân biệt unauthorized vs forbidden |
| 302 xuất hiện chỉ ở production | Proxy/ingress khác staging hoặc path rewrite | So sánh cấu hình route/hop và response headers |

## 24. Nguyên tắc thiết kế dài hạn

**1. Một endpoint API phải có hợp đồng lỗi rõ ràng.** Quy định status 401/403/5xx, `WWW-Authenticate` và body JSON/problem+json nếu có.

**2. HTTP Bearer và web login là hai cơ chế khác nhau.** Có thể tồn tại trong cùng application, nhưng phải tách trust boundaries và request matchers.

**3. Đặt API security chain trước chain web.** Kiểm tra `@Order`, `securityMatcher` và fallback chain; đừng chỉ sửa `requestMatchers` bên trong chain đang sai.

**4. Dùng BearerTokenAuthenticationEntryPoint và BearerTokenAccessDeniedHandler.** Không redirect API sang form login hoặc OIDC authorization endpoint.

**5. Không phụ thuộc Accept header để xác định authentication type.** API phải xử lý nhất quán cả các client gửi `text/html` hoặc `*/*`.

**6. Không dùng @ControllerAdvice thay thế security exception handling.** Những lỗi xuất hiện trước MVC cần xử lý tại security filters/handlers.

**7. API không tự refresh bearer token.** Client hoặc BFF thực hiện OAuth flow hợp lệ ở đúng boundary.

**8. Đừng gộp 401 và 403.** Invalid/missing authentication khác với valid token thiếu quyền hoặc không có quyền trên object.

**9. CORS, CSRF và session phải được thiết kế theo mô hình credential.** Sửa redirect không có nghĩa tắt mọi bảo vệ.

**10. Quan sát response qua tất cả hop.** Gateway/CDN/ingress có thể viết lại status/header thành HTML ngay cả khi Spring Security đúng.

**11. Không tiết lộ thông tin nhạy cảm trong lỗi.** Bearer token, signing key, claims cá nhân, secret và policy nội bộ không được nằm trong JSON error, HTML page hay log.

**12. Test cả token thiếu, token sai, token hợp lệ nhưng thiếu scope.** Kiểm tra status/header/Location/Content-Type với `Accept` khác nhau và qua proxy thật.

## 25. Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, `WWW-Authenticate`, `invalid_request`, `invalid_token` và `insufficient_scope`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa của HTTP 401, 403, 302, `Location` và challenge.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng `application/problem+json` cho lỗi API.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): xác thực Bearer, filter/provider và xử lý lỗi.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình `jwt()` và validation.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): cấu hình `opaqueToken()` và introspection.
- [Spring Security Reference — Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): nhiều `SecurityFilterChain`, thứ tự matcher và cách chọn chain.
- [Spring Security Reference — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler`.
- [Spring Security Reference — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): xử lý CORS trước security khi phù hợp.

**Ghi nhớ:** một **Resource Server API nhận Bearer access token** nên trả **401 Bearer challenge** khi thiếu/sai token và **403** khi đã xác thực nhưng thiếu quyền. **302/login HTML là hành vi của luồng browser login**, không phải phản hồi thay thế cho lỗi Bearer. Tách `SecurityFilterChain` theo route, dùng entry point và access-denied handler phù hợp, rồi kiểm tra status/header qua cả backend và gateway sẽ giúp API giữ đúng hợp đồng xác thực ngay cả khi ứng dụng đồng thời phục vụ web login.
