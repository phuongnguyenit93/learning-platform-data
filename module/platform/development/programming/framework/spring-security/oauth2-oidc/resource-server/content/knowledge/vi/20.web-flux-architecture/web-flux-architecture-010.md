# Lỗi xác thực, từ chối truy cập và handler tương ứng phía server

Trong **Spring Security OAuth 2.0/OIDC Resource Server chạy trên WebFlux**, request được xử lý theo mô hình **reactive**: các thành phần bảo mật tham gia vào chuỗi **WebFilter**, kết quả có thể là **Mono** và thông tin xác thực được truyền qua ngữ cảnh Reactor.

Vì vậy, khi xảy ra lỗi, cần biết **lỗi xuất hiện ở bước nào**, **request đã được xác thực hay chưa** và **handler nào chịu trách nhiệm tạo phản hồi HTTP**. Chỉ nhìn một dòng log ghi 401 hoặc 403 thường không đủ.

Bốn interface/lớp cần phân biệt:

- **ServerAuthenticationEntryPoint**: bắt đầu một authentication challenge khi endpoint yêu cầu xác thực nhưng request chưa có authentication hợp lệ; điển hình trả **401**.
- **ServerAccessDeniedHandler**: xử lý **AccessDeniedException** khi truy cập bị từ chối; điển hình trả **403** nếu chủ thể đã xác thực nhưng thiếu quyền.
- **BearerTokenServerAuthenticationEntryPoint**: entry point dành cho OAuth2 Resource Server Bearer token, tạo header **WWW-Authenticate: Bearer** theo RFC 6750.
- **BearerTokenServerAccessDeniedHandler**: access denied handler dành cho Bearer, có thể phát **error="insufficient_scope"** khi biết request mang OAuth2 Authentication hợp lệ.

Các cơ chế này **không đồng nghĩa với việc xác minh JWT hoặc opaque token**. JWT được xác minh qua **ReactiveJwtDecoder**, opaque token qua **ReactiveOpaqueTokenIntrospector** và các reactive authentication managers tương ứng. Error handlers chỉ quyết định cách diễn đạt thất bại ở phía HTTP, không biến token giả thành token hợp lệ.

## 1. Bắt đầu từ mô hình WebFlux, không phải Servlet

Spring Security có hai mô hình web chính:

| Thành phần | Servlet / Spring MVC | Reactive / WebFlux |
|---|---|---|
| Cấu hình web security | **HttpSecurity** | **ServerHttpSecurity** |
| Chuỗi bảo mật | **SecurityFilterChain** | **SecurityWebFilterChain** |
| Đối tượng request/response | **HttpServletRequest/Response** | **ServerWebExchange** |
| Security filter chính | Servlet **Filter** | Reactive **WebFilter** |
| Entry point | **AuthenticationEntryPoint** | **ServerAuthenticationEntryPoint** |
| Access denied handler | **AccessDeniedHandler** | **ServerAccessDeniedHandler** |
| Exception translation | **ExceptionTranslationFilter** | **ExceptionTranslationWebFilter** |
| JWT decoder | **JwtDecoder** | **ReactiveJwtDecoder** |
| Opaque token introspector | **OpaqueTokenIntrospector** | **ReactiveOpaqueTokenIntrospector** |
| Cách lưu security context phổ biến | Thread-local **SecurityContextHolder** trong luồng Servlet | **ReactiveSecurityContextHolder** và Reactor Context |

**Không copy nguyên code Servlet AuthenticationEntryPoint/AccessDeniedHandler vào WebFlux**. Signature phương thức, đối tượng exchange, cách trả response và mô hình thực thi khác nhau.

Đây là bài về **WebFlux server-side handling**. Không nhầm nó với **WebClient** là HTTP client reactive dùng gọi các service khác.

### 1.1. Một request thông thường đi qua đâu?

~~~mermaid
flowchart TD
    R[HTTP request] --> P[WebFilterChainProxy]
    P --> C[SecurityWebFilterChain được chọn]
    C --> B[AuthenticationWebFilter / Bearer converter]
    B --> M[ReactiveAuthenticationManager]
    M --> D[ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector]
    D -->|Thất bại| AF[ServerAuthenticationFailureHandler]
    AF --> EP[BearerTokenServerAuthenticationEntryPoint]
    D -->|Thành công| SC[Authentication trong Reactor SecurityContext]
    SC --> AW[AuthorizationWebFilter]
    AW -->|Không đủ quyền| ET[ExceptionTranslationWebFilter]
    ET --> AD[BearerTokenServerAccessDeniedHandler]
    AW -->|Đủ quyền| H[Handler/Controller]
    EP --> HTTP[HTTP error + WWW-Authenticate]
    AD --> HTTP
~~~

Đây là sơ đồ **luồng trách nhiệm**, không phải thứ tự thực thi tuyệt đối của mọi filter ở tất cả phiên bản. **ExceptionTranslationWebFilter** có thể xử lý **AccessDeniedException** từ các filter downstream và quyết định dùng entry point hay access denied handler dựa trên authentication hiện tại. Một lỗi authentication được phát hiện ngay trong **AuthenticationWebFilter** có thể đi qua **ServerAuthenticationFailureHandler** trước khi entry point viết response.

## 2. Authentication failure và access denied khác nhau

Hai lớp lỗi phản ánh **hai câu hỏi khác nhau**:

1. **Authentication:** Request có cung cấp credential hợp lệ để xác định chủ thể không?
2. **Authorization:** Chủ thể đã được xác thực có được phép truy cập tài nguyên hoặc thao tác này không?

### 2.1. Authentication failure — chưa xác thực hợp lệ

Ví dụ:

- Không có Bearer token khi endpoint yêu cầu.
- JWT sai signature hoặc thuật toán không được phép.
- JWT hết hạn, chưa có hiệu lực, sai issuer hoặc audience.
- Opaque access token bị Authorization Server trả **active=false**.
- Bearer token malformed hoặc request gửi credential không đúng chuẩn.
- Authentication manager từ chối principal/credential.

Với Resource Server Bearer, những trường hợp token không hợp lệ thường được diễn đạt thành **401 Unauthorized**, có thể kèm:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

Khi request **không gửi credential nào**, server thường trả Bearer challenge **không kèm error code**, theo khuyến nghị RFC 6750.

### 2.2. Authorization failure — đã xác thực nhưng không đủ quyền

Ví dụ JWT đã được ReactiveJwtDecoder xác minh và SecurityContext có:

~~~text
principal: user-123
authorities: [SCOPE_orders.read]
~~~

Nhưng endpoint yêu cầu:

~~~java
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Authentication có thật, nhưng **SCOPE_orders.write** vắng mặt. Response thường là **403 Forbidden**. Với Bearer-specific denied handler và authentication phù hợp, server có thể trả:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Không phải **mọi 403** đều là insufficient_scope: có thể do role, ownership, tenant, CSRF, policy nội bộ hoặc một handler tùy chỉnh.

### 2.3. HTTP status không thay thế phân tích lỗi

| Trường hợp | Bước chính | HTTP thường gặp |
|---|---|---|
| Không token, endpoint protected | Authentication challenge | **401** |
| JWT signature sai | ReactiveJwtDecoder/authentication | **401** |
| JWT hết hạn | ReactiveJwtDecoder/token validator | **401** |
| Opaque token inactive | Introspection/authentication | **401** |
| Bearer request vi phạm cú pháp | Bearer token conversion/validation | **400** hoặc mã do implementation định nghĩa |
| Token hợp lệ, thiếu scope | Authorization | **403** |
| Token hợp lệ, sai tenant/owner | Domain authorization | **403/404** tùy chính sách |
| CSRF token thiếu trong web session chain | CSRF web filter | **403** |
| Decoder/introspection upstream timeout | Lỗi hạ tầng xác thực | Không được fail-open; status phụ thuộc exception handling |
| Controller ném lỗi dữ liệu | Application error | 4xx/5xx theo business exception handler |

Cần **phân biệt HTTP error của SecurityWebFilterChain với lỗi business của controller**. Một response 403 không đủ để kết luận ReactiveJwtDecoder đã thất bại.

## 3. ServerAuthenticationEntryPoint

Giao diện reactive:

~~~java
package org.springframework.security.web.server;

public interface ServerAuthenticationEntryPoint {

    Mono<Void> commence(
        ServerWebExchange exchange,
        AuthenticationException exception
    );
}
~~~

Đây là dạng signature rút gọn để học, không phải bản sao toàn bộ source code/API annotations.

Ý nghĩa:

- **ServerWebExchange** cho phép thao tác request/response trong WebFlux.
- **AuthenticationException** chứa ngữ cảnh lỗi xác thực.
- **Mono<Void>** biểu diễn tác vụ bất đồng bộ hoàn tất phản hồi; handler không trả về một String body theo kiểu controller.
- Entry point thường đặt HTTP status/challenge và hoàn tất response hoặc trả một Mono viết response.

Ví dụ các implementation:

| Lớp | Cách xử lý thường gặp |
|---|---|
| **BearerTokenServerAuthenticationEntryPoint** | Bearer 401/challenge theo RFC 6750 |
| **HttpBasicServerAuthenticationEntryPoint** | HTTP Basic challenge |
| **RedirectServerAuthenticationEntryPoint** | Redirect đến login page, phù hợp một số web login flows |
| **HttpStatusServerEntryPoint** | Trả một HTTP status được cấu hình |
| **Custom ServerAuthenticationEntryPoint** | Tạo response theo hợp đồng riêng nhưng phải giữ ngữ nghĩa security |

**Resource Server API thường nên dùng Bearer entry point**, không redirect đến login HTML như một ứng dụng web có form/OIDC Login tương tác với browser.

### 3.1. Ví dụ challenge khi thiếu token

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
~~~

Có thể nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Length: 0
~~~

Header **WWW-Authenticate** là phần quan trọng của Bearer protocol. Không có requirement là mọi response lỗi phải có JSON body.

### 3.2. Ví dụ invalid_token

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <invalid-test-token>
~~~

Response thường gặp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Một số framework/version có thể bổ sung **error_description**, **error_uri** hoặc auth-param mở rộng. Không xây test exact-header quá cứng nếu API không cam kết cụ thể những field ấy.

## 4. BearerTokenServerAuthenticationEntryPoint

Class nằm trong package:

~~~text
org.springframework.security.oauth2.server.resource.web.server
~~~

Và triển khai:

~~~java
public final class BearerTokenServerAuthenticationEntryPoint
        implements ServerAuthenticationEntryPoint {
    // ...
}
~~~

Nó sử dụng thông tin từ **BearerTokenError** khi exception cung cấp loại error tương ứng, để xác định **HTTP status** và **WWW-Authenticate** theo RFC 6750.

Một API đáng chú ý:

~~~java
BearerTokenServerAuthenticationEntryPoint entryPoint =
    new BearerTokenServerAuthenticationEntryPoint();
entryPoint.setRealmName("orders-api");
~~~

**realm** giúp nhận diện một protection space, nhưng không thay thế claim issuer (**iss**), audience (**aud**) hay tenant authorization.

Đặc biệt:

- Không token: thường **401** với **Bearer** challenge nhưng không error.
- Token không hợp lệ: thường **401** với **invalid_token**.
- Bearer request bị malformed: có thể **invalid_request/400** hoặc error mapping khác từ converter/resolver tùy phiên bản và dạng lỗi.
- Entry point **không xác minh signature**. Nó nhận lỗi đã được security flow phát hiện và tạo HTTP response.

Nếu chỉ thay entry point bằng **HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)**, bạn có thể làm mất **WWW-Authenticate** và các tham số RFC 6750 mà OAuth clients mong đợi.

## 5. ServerAccessDeniedHandler

Giao diện:

~~~java
package org.springframework.security.web.server.authorization;

public interface ServerAccessDeniedHandler {

    Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException denied
    );
}
~~~

Ý nghĩa:

- Được dùng khi một request bị từ chối truy cập theo authorization policy.
- Có thể đặt **403 Forbidden** và những HTTP headers/body phù hợp.
- Trả **Mono<Void>**, không thực hiện blocking I/O.
- Không quyết định tính hợp lệ của access token; đó là trách nhiệm authentication.

Ví dụ implementation:

| Lớp | Mục đích |
|---|---|
| **BearerTokenServerAccessDeniedHandler** | Bearer-specific 403/challenge |
| **HttpStatusServerAccessDeniedHandler** | Trả HTTP status được cấu hình |
| **ServerWebExchangeDelegatingServerAccessDeniedHandler** | Chọn handler theo matcher của exchange |
| **Custom ServerAccessDeniedHandler** | Phản hồi đặc biệt theo policy; cần giữ các HTTP/Bearer contract |

### 5.1. BearerTokenServerAccessDeniedHandler

Lớp nằm trong package:

~~~text
org.springframework.security.oauth2.server.resource.web.access.server
~~~

Ví dụ:

~~~java
BearerTokenServerAccessDeniedHandler denied =
    new BearerTokenServerAccessDeniedHandler();
denied.setRealmName("orders-api");
~~~

Nó chuyển một **AccessDeniedException** thành response theo RFC 6750.

Từ tài liệu API: **chỉ khi handler có đủ bằng chứng request có OAuth2 Authentication hợp lệ**, nó mới trả error **insufficient_scope**. Trong những trường hợp khác, nó có thể chỉ thông báo scheme Bearer và realm được cấu hình.

Vì vậy, không nên phát biểu:

> Hễ WebFlux ném AccessDeniedException thì luôn nhận được WWW-Authenticate: Bearer error="insufficient_scope".

Đó là kết luận sai nếu request anonymous, chưa được xác thực hoặc handler đang dùng không phải Bearer-specific.

## 6. ExceptionTranslationWebFilter: lớp điều phối giữa 401 và 403

Trong WebFlux, **ExceptionTranslationWebFilter** thuộc package:

~~~text
org.springframework.security.web.server.authorization
~~~

Nó xử lý những **AuthenticationException/AccessDeniedException** trong phần security web filter chain mà nó có thể quan sát và đưa ra quyết định phản hồi thích hợp.

Những extension points chính:

~~~java
void setAuthenticationEntryPoint(
    ServerAuthenticationEntryPoint authenticationEntryPoint);

void setAccessDeniedHandler(
    ServerAccessDeniedHandler accessDeniedHandler);
~~~

Ngoài ra còn cơ chế xác định trạng thái trust/anonymous authentication theo phiên bản.

Quyết định logic:

~~~mermaid
flowchart TD
    X[AccessDeniedException trong security chain] --> A{Authentication đáng tin và đủ?}
    A -->|Anonymous/chưa authenticated| E[ServerAuthenticationEntryPoint]
    A -->|Đã authenticated, bị từ chối| D[ServerAccessDeniedHandler]
    E --> H1[401 hoặc challenge phù hợp]
    D --> H2[403 hoặc policy-specific response]
~~~

**Quan trọng:** Không phải mọi AuthenticationException trong **AuthenticationWebFilter** đều đi qua một nhánh duy nhất của ExceptionTranslationWebFilter. AuthenticationWebFilter có **ServerAuthenticationFailureHandler** riêng. Với Resource Server, failure handler có thể chuyển lỗi đến Bearer entry point.

Do đó, nếu custom entry point không ảnh hưởng tới một lỗi Bearer token malformed, cần kiểm **authentication failure handler** của WebFlux flow, không chỉ ExceptionTranslationWebFilter.

### 6.1. Vì sao anonymous có thể dẫn tới entry point thay vì 403?

Một rule:

~~~java
.anyExchange().authenticated()
~~~

bị truy cập không token có thể tạo AccessDeniedException từ authorization. Vì principal chưa được xác thực đúng nghĩa, exception translation sẽ **khởi phát authentication challenge** qua entry point, thường trả **401** cho API Bearer.

Nếu principal đã xác thực nhưng thiếu authority, denied handler xử lý và thường trả **403**.

Đây là lý do cùng một authorization rule có thể tạo hai response khác nhau tùy Authentication.

## 7. AuthenticationWebFilter và ServerAuthenticationFailureHandler

**AuthenticationWebFilter** là một thành phần trong luồng reactive authentication. Nó thường sử dụng:

- **ServerAuthenticationConverter** để trích credential/request Authentication từ ServerWebExchange.
- **ReactiveAuthenticationManager** để xác thực.
- **ServerAuthenticationSuccessHandler** khi thành công.
- **ServerAuthenticationFailureHandler** khi authentication thất bại.

Với Bearer Resource Server, converter lấy Bearer token, manager gọi decoder/introspector tương ứng; nếu thất bại, failure handler có thể gọi Bearer authentication entry point.

Giao diện failure handler:

~~~java
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception
);
~~~

Một implementation phổ biến là **ServerAuthenticationEntryPointFailureHandler**. Nó **adapt** một **ServerAuthenticationEntryPoint** thành **ServerAuthenticationFailureHandler**.

Ví dụ mô hình:

~~~java
ServerAuthenticationEntryPoint entryPoint =
    new BearerTokenServerAuthenticationEntryPoint();

ServerAuthenticationFailureHandler failureHandler =
    new ServerAuthenticationEntryPointFailureHandler(entryPoint);
~~~

Trong cấu hình mặc định Resource Server, Spring Security lo nhiều phần wiring này. Không cần tự tạo AuthenticationWebFilter chỉ để dùng JWT Resource Server tiêu chuẩn.

### 7.1. Khác nhau giữa failure handler và entry point

| Khía cạnh | ServerAuthenticationFailureHandler | ServerAuthenticationEntryPoint |
|---|---|---|
| Ngữ cảnh | Một **lần thử authentication** đã thất bại | Cần **bắt đầu/challenge authentication** |
| Input | WebFilterExchange + AuthenticationException | ServerWebExchange + AuthenticationException |
| Output | Mono<Void> | Mono<Void> |
| Có thể delegate cho bên kia? | Có, qua ServerAuthenticationEntryPointFailureHandler | Có thể nhận lỗi được delegate |
| Dùng khi nào? | Lỗi token/password/method xác thực trong AuthenticationWebFilter | Missing authentication và những challenge cần thiết |

Không nhầm hai interface chỉ vì cả hai có thể tạo response 401.

### 7.2. Không fail-open khi authentication manager lỗi

Nếu ReactiveJwtDecoder không tải được JWKS, introspection endpoint timeout hoặc issuer service không khả dụng, đó là **lỗi không thể xác minh credential**, không phải bằng chứng token hợp lệ.

Không dùng:

~~~java
// Anti-pattern: giả định authentication thành công khi upstream lỗi.
// Không triển khai kiểu fallback này.
return authenticationManager.authenticate(token)
    .onErrorResume(error -> Mono.just(fakeAdminAuthentication));
~~~

Một policy đúng phải từ chối hoặc trả lỗi hạ tầng thích hợp, có monitoring, retry/circuit breaker theo giới hạn, nhưng **không tạo principal thành công từ token chưa xác minh**.

## 8. RFC 6750 và WWW-Authenticate trong WebFlux

HTTP header **WWW-Authenticate** là phần của giao thức **Bearer Token Usage**.

| Trường hợp | Status thông dụng | Challenge |
|---|---|---|
| Protected endpoint, không token | **401** | **Bearer**; thường không có error |
| Token invalid/expired/revoked | **401** | **error="invalid_token"** |
| Request Bearer sai cấu trúc | **400** theo khuyến nghị RFC | **error="invalid_request"** nếu được xử lý như vậy |
| Token hợp lệ nhưng thiếu scope | **403** | **error="insufficient_scope"** khi handler nhận diện OAuth2 Authentication hợp lệ |

Một challenge có thể gồm:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Các auth-param RFC 6750:

- **realm**: protection space theo HTTP.
- **error**: invalid_request, invalid_token, insufficient_scope.
- **error_description**: mô tả ngắn, không tiết lộ secrets.
- **error_uri**: URI tài liệu lỗi.
- **scope**: scope cần thiết, nếu muốn công bố.

**Không có token** không đồng nghĩa **invalid_token**. RFC 6750 khuyến nghị không đưa error information khi request chưa gửi bất kỳ authentication credential nào.

**Không phải mọi 403 đều mang sufficient scope metadata.** Ví dụ role ADMIN thiếu, tenant không khớp hoặc business policy deny không nhất thiết có cách chuyển thành OAuth2 scope.

### 8.1. Tránh yêu cầu client tự “sửa” JWT scope

Nếu endpoint yêu cầu **orders.write** và client chỉ có **orders.read**, client không được tự sửa JWT payload để thêm scope. Scope phải được Authorization Server cấp theo policy. Resource Server chỉ kiểm token đã xác thực và authorization policy của mình.

### 8.2. Không tự tiết lộ lỗi signature quá chi tiết

Thông tin công bố cho client nên giới hạn ở mức cần xử lý. Không đưa raw token, JWK private key, đường dẫn file, stack trace hoặc chi tiết cấu hình issuer vào **error_description**.

## 9. Cấu hình WebFlux JWT Resource Server cơ bản

Ví dụ **Spring Boot 3.x/Spring Security 6.x** với WebFlux, áp dụng tương tự trên các version mới khi API tương thích.

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

**issuer-uri** giúp thiết lập trust với issuer theo metadata/JWKS thích hợp. **audiences** là cấu hình validation audience trên các Spring Boot version hỗ trợ; với version khác cần cấu hình ReactiveJwtDecoder validators tương ứng.

Một SecurityWebFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Điểm khác Servlet:

- Dùng **ServerHttpSecurity**, không dùng HttpSecurity.
- Dùng **SecurityWebFilterChain**, không phải SecurityFilterChain.
- Dùng **authorizeExchange** và **pathMatchers**, không phải authorizeHttpRequests/requestMatchers.
- Không đưa JwtDecoder blocking vào luồng reactive; sử dụng **ReactiveJwtDecoder** qua cấu hình đúng.
- Default Bearer-specific handlers sẽ xử lý các challenge tương ứng nếu không bị custom config thay thế.

Với API chỉ chấp nhận Bearer header và không có browser-managed authentication, có thể cân nhắc CSRF policy riêng. Không tự tắt CSRF chỉ vì WebFlux hoặc JWT; nếu browser dùng session/JWT cookie, rủi ro CSRF vẫn có thể có.

### 9.1. Khi WebFlux nhận opaque token

Thay:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
)
~~~

và cấu hình introspection endpoint/client credentials phù hợp. Authentication đi qua **ReactiveOpaqueTokenIntrospector** thay cho ReactiveJwtDecoder, nhưng Bearer challenge 401/403 vẫn dựa trên nguyên tắc tương tự.

## 10. Tùy chỉnh Bearer entry point và denied handler

Khi muốn một realm tường minh cho Orders API, sử dụng các handler Bearer chuẩn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class BearerChallengeConfig {

    @Bean
    SecurityWebFilterChain ordersApi(ServerHttpSecurity http) {
        BearerTokenServerAuthenticationEntryPoint entryPoint =
            new BearerTokenServerAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenServerAccessDeniedHandler deniedHandler =
            new BearerTokenServerAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Ở WebFlux, **ServerHttpSecurity.OAuth2ResourceServerSpec** cung cấp:

~~~java
authenticationEntryPoint(ServerAuthenticationEntryPoint)
accessDeniedHandler(ServerAccessDeniedHandler)
authenticationFailureHandler(ServerAuthenticationFailureHandler)
~~~

Đây là những extension points của **Bearer Resource Server**. Việc dùng handler riêng đúng nhánh hỗ trợ giữ RFC 6750 semantics.

### 10.1. Tùy chỉnh rộng qua exceptionHandling

WebFlux cũng có:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(entryPoint)
    .accessDeniedHandler(deniedHandler)
);
~~~

Cách này ảnh hưởng xử lý exception của security chain ở phạm vi rộng hơn. Trong ứng dụng có nhiều authentication mechanisms hoặc nhiều SecurityWebFilterChain, cần xác định rõ **nơi phát sinh lỗi** và **handler nào thực tế được chọn**.

Không đặt một generic entry point trả JSON/302 ở chain API Bearer rồi vô tình làm mất **WWW-Authenticate**.

### 10.2. Nếu có nhiều SecurityWebFilterChain

Ví dụ thiết kế:

~~~text
@Order(1) /api/**:
   Bearer Resource Server
   401 WWW-Authenticate: Bearer
   403 insufficient_scope khi phù hợp

@Order(2) /web/**:
   OIDC Login + session cookie
   Có thể redirect tới login page
   CSRF protection cho unsafe methods

Fallback:
   denyAll hoặc policy cho các path khác
~~~

**Chain đầu tiên khớp request** mới điều khiển authentication/authorization. Nếu một chain web-login matcher rộng đặt trước chain API, request API có thể nhận redirect 302/HTML thay vì Bearer challenge.

Không cho rằng chỉ cần cấu hình Bearer entry point trong một bean là nó tự áp cho mọi URL/port.

## 11. Khi nào dùng generic HttpStatus handlers?

WebFlux có các handler đơn giản chỉ đặt HTTP status:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;

ServerAuthenticationEntryPoint plain401 =
    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

ServerAccessDeniedHandler plain403 =
    new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);
~~~

Chúng hữu ích trong một số application protocols hoặc test, nhưng **không tự xây Bearer WWW-Authenticate header theo RFC 6750**.

Với OAuth2 Resource Server, ưu tiên các **BearerTokenServer*** handlers trừ khi custom response được thiết kế để vẫn giữ đầy đủ scheme, error code, HTTP status và thông tin an toàn cho client.

### 11.1. Redirect entry point không phù hợp cho mọi API

Ứng dụng web có OIDC Login có thể sử dụng **RedirectServerAuthenticationEntryPoint**, chuyển browser sang trang login. Nhưng một machine-to-machine API client muốn nhận 401 + Bearer challenge, không phải 302 đến HTML login.

Khi triển khai chung web UI và API, cân nhắc security chain hoặc request matcher phân biệt rõ thay vì một entry point chung cho mọi endpoint.

## 12. Custom JSON error body: phản hồi reactive đúng cách

Có hệ thống muốn chuẩn hóa lỗi thành JSON hoặc **Problem Details** (RFC 9457) như:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required"
}
~~~

Đây là một **response-body contract**, khác với **WWW-Authenticate**. Đối với Bearer API, **không được chỉ trả JSON rồi đánh mất challenge header**.

Một custom reactive handler cần:

1. Đặt **HTTP status** đúng.
2. Giữ **WWW-Authenticate: Bearer** và error parameters phù hợp nếu đây là Bearer challenge.
3. Đặt **Content-Type** đúng, ví dụ application/problem+json hoặc application/json.
4. Tạo body theo định dạng cố định, không phản chiếu exception/token.
5. Trả **Mono<Void>**, dùng nonblocking response write.
6. Không viết response hai lần nếu một handler khác đã commit.
7. Không tự biến lỗi authentication thành response 200 hoặc redirect không đúng cho API.

### 12.1. Ví dụ ServerAccessDeniedHandler JSON tổng quát

Ví dụ một **non-Bearer domain endpoint** cần trả JSON 403:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import reactor.core.publisher.Mono;

ServerAccessDeniedHandler jsonDenied = (exchange, denied) -> {
    var response = exchange.getResponse();

    if (response.isCommitted()) {
        return Mono.error(denied);
    }

    response.setStatusCode(HttpStatus.FORBIDDEN);
    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

    byte[] bytes = (
        "{\"code\":\"ACCESS_DENIED\",\"message\":\"Access denied\"}"
    ).getBytes(StandardCharsets.UTF_8);

    return response.writeWith(
        Mono.just(response.bufferFactory().wrap(bytes))
    );
};
~~~

Đây là ví dụ **cách viết response reactive**, không phải khuyến nghị thay BearerTokenServerAccessDeniedHandler ở mọi Resource Server chain.

Nếu lắp global handler này cho Bearer API, response có thể **mất error="insufficient_scope"**. Nếu cần cả JSON và RFC 6750 challenge, hãy thiết kế một handler chuyên biệt có logic xử lý BearerTokenError/WWW-Authenticate và bảo đảm chỉ một thành phần sở hữu việc ghi response. Tương tự, muốn tùy biến 401 cần một **ServerAuthenticationEntryPoint** phù hợp.

### 12.2. Không block trong handler

**Không** dùng:

~~~java
// Anti-pattern trong WebFlux event loop:
String value = remoteClient.call().block();
response.getOutputStream().write(...);
~~~

Trong WebFlux, dùng **Mono/Flux**, reactive HTTP clients và API response thích hợp. Blocking I/O trên event loop có thể gây nghẽn luồng, tăng latency và ảnh hưởng toàn hệ thống.

Cũng không subscribe thủ công để viết response rồi trả Mono.empty() ngay, vì lifecycle/commit có thể diễn ra ngoài kiểm soát của pipeline. Hãy **return Publisher mô tả toàn bộ thao tác**.

### 12.3. Response có thể đã committed

Khi response đã ghi headers/body, handler có thể không đổi được status. Một downstream reactive flow có thể phát lỗi **sau khi bắt đầu streaming body**.

Cần phân biệt:

- **Lỗi trước commit**: có thể đổi status/header và viết error body.
- **Lỗi sau commit**: không thể bảo đảm chuyển response thành 401/403 đẹp; cần xử lý bằng streaming protocol, kết thúc kết nối, log/metrics phù hợp.

Điều này đặc biệt quan trọng với **Server-Sent Events**, **Flux response body** hoặc những API streaming.

## 13. Reactor Context và SecurityContext

WebFlux không nên dựa trên giả định “một HTTP request luôn chạy trên một Thread duy nhất”.

Spring Security reactive đưa authentication qua **Reactor Context**, có thể truy cập bằng **ReactiveSecurityContextHolder** hoặc thông qua các integration của Spring Security method/controller.

Ví dụ service:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
}
~~~

Trong thực tế cần xử lý trường hợp context trống hoặc principal anonymous theo policy ứng dụng.

### 13.1. Vì sao không dùng SecurityContextHolder.getContext() như Servlet?

**SecurityContextHolder** truyền thống dùng ThreadLocal trong nhiều trường hợp Servlet. Với Reactive pipelines có scheduling/thread hops, truy cập ThreadLocal ngẫu nhiên có thể trả security context sai hoặc rỗng.

Khi viết **ReactiveAuthorizationManager**, WebFilter hoặc service xử lý authentication reactive, dùng context-aware API và Publisher composition. Không tự tạo global static Authentication hoặc đưa principal từ request khác vào Reactor context.

### 13.2. Không coi một JWT claim là authorization decision trước khi verify

JWT JSON payload có thể được Base64URL-decoded mà không có signature verification. Không tự đọc **scope/roles** rồi tạo Authentication từ input chưa xác minh trong custom WebFilter.

Quy trình đúng:

~~~text
Bearer string chưa được tin
 -> ReactiveJwtDecoder hoặc introspector tin cậy
 -> Authentication
 -> Reactive authorization
 -> Domain policy
~~~

Entry point và denied handler chỉ biểu diễn **thất bại của quy trình**, không thay thế bước verify.

## 14. Authorization WebFilter và method security

Một rule WebFlux:

~~~java
.authorizeExchange(auth -> auth
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers("/api/admin/**")
        .hasRole("ADMIN")
    .anyExchange()
        .authenticated()
)
~~~

- **hasAuthority("SCOPE_orders.read")** so khớp authority scope.
- **hasRole("ADMIN")** thường kiểm **ROLE_ADMIN** theo convention.
- **authenticated()** đòi principal đã xác thực, không tự kiểm tenant/owner.
- **anyExchange()** chỉ bao phủ những request thuộc SecurityWebFilterChain được chọn.

Method security cũng có thể hoạt động với reactive methods qua cấu hình **@EnableReactiveMethodSecurity** tương ứng phiên bản, thường dùng **@PreAuthorize** trên method trả Mono/Flux.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderView> findOrder(String orderId) {
    return repository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)));
}
~~~

Các kiểu **OrderView**, **repository** và **OrderNotFoundException** là phần ứng dụng giả định. Khi cần tenant/ownership, phải kiểm thêm trong reactive domain policy.

### 14.1. Lỗi method security có đi qua same HTTP handler?

Nếu reactive method security phát **AccessDeniedException** trong Publisher được thực thi trong HTTP pipeline và chưa commit response, **ExceptionTranslationWebFilter** hoặc cơ chế xử lý exception tương ứng có thể chuyển lỗi theo security policy.

Nhưng nếu method được gọi ngoài HTTP request (background job/message consumer) hoặc error được xử lý bằng **onErrorResume** ở tầng service/controller, không được giả định ServerAccessDeniedHandler luôn tự chạy.

**Không nuốt AccessDeniedException** rồi trả một giá trị bình thường chỉ để tránh 403 nếu điều đó làm người gọi tưởng thao tác đã thành công.

## 15. Lỗi của controller khác lỗi bảo mật từ WebFilter

Ví dụ controller:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderView> getOrder(@PathVariable String id) {
    return orderService.getOrder(id);
}
~~~

Có nhiều loại lỗi:

| Lỗi | Nguồn | Handler thường liên quan |
|---|---|---|
| Bearer JWT sai signature | Authentication pipeline | Bearer entry point/failure handler |
| Thiếu scope tại HTTP matcher | AuthorizationWebFilter | ExceptionTranslationWebFilter + denied handler |
| @PreAuthorize từ chối | Reactive method security | Security exception path nếu truyền qua pipeline |
| Dữ liệu request invalid | WebFlux binding/validation | Controller advice/WebExceptionHandler |
| Không tìm thấy đơn | Domain service | Application exception mapping |
| Database timeout | Reactive service/repository | 5xx/application error handling |
| Response streaming đã commit mới lỗi | Reactive response pipeline | Không chắc đổi được status/header |

**@RestControllerAdvice** và **WebExceptionHandler** phục vụ nhiều loại lỗi ứng dụng, nhưng không nên được xem là thay thế tự động của Bearer authentication entry point. Một custom global error handler bắt tất cả AuthenticationException/AccessDeniedException và chuyển thành JSON tùy ý có thể làm mất header RFC 6750 hoặc làm sai status.

### 15.1. Khi nào dùng @RestControllerAdvice?

Dùng cho validation, resource not found hoặc business exceptions phù hợp:

~~~java
@RestControllerAdvice
class DomainErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<Map<String, String>> notFound(
            OrderNotFoundException error) {
        return ResponseEntity.status(404)
            .body(Map.of("code", "ORDER_NOT_FOUND"));
    }
}
~~~

Ví dụ rút gọn, cần imports và domain exception của ứng dụng thật.

Không tùy tiện thêm một handler **@ExceptionHandler(Exception.class)** chuyển mọi lỗi thành HTTP 200, hoặc bắt AuthenticationException rồi trả 401 không WWW-Authenticate. Với security lỗi ở WebFilter, controller advice cũng có thể **không được gọi** vì request chưa đến controller.

## 16. Kiểm thử WebFlux bằng WebTestClient

Trong reactive stack, dùng **WebTestClient**, không dùng Servlet MockMvc để kiểm luồng SecurityWebFilterChain.

Ví dụ test kết hợp Spring Security:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class BearerErrorWebFluxTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        this.client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void noTokenIsUnauthorized() {
        client.get().uri("/api/orders/42")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, ".*Bearer.*");
    }

    @Test
    void validAuthenticationButMissingScopeIsForbidden() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.write")))
            .get().uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Đoạn test giả định ứng dụng có controller handler thật tại **/api/orders/42** và cấu hình API JWT Resource Server với rule **SCOPE_orders.read**. Khi thiếu scope, kết quả có thể là 403 trước khi controller được gọi.

**mockJwt()** thường đưa authentication mô phỏng để kiểm authorization; **không chứng minh chữ ký JWT đã được xác minh**. Cần integration test riêng với ReactiveJwtDecoder/JWKS test để kiểm token giả bị từ chối.

### 16.1. Kiểm invalid token bằng Authorization header thật

Một test authentication thực sự cần đưa raw Bearer token vào request:

~~~java
client.get()
    .uri("/api/orders/42")
    .header(HttpHeaders.AUTHORIZATION, "Bearer rejected-test-token")
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Điều kiện: test context phải có **ReactiveJwtDecoder** hoặc introspector được cấu hình để chắc chắn từ chối token đó. Nếu mock decoder được setup trả Authentication hợp lệ cho mọi input, test không chứng minh gì về invalid token.

Có thể mock/stub decoder để ném lỗi tương ứng cho một test error handling, và thêm integration test với khóa ký test để kiểm cryptographic validation.

### 16.2. Kiểm insufficient_scope header

Nếu ứng dụng sử dụng BearerTokenServerAccessDeniedHandler và Authentication mà handler nhận diện là OAuth2 hợp lệ, có thể kiểm response:

~~~java
client.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.write")))
    .get().uri("/api/orders/42")
    .exchange()
    .expectStatus().isForbidden()
    .expectHeader().valueMatches(
        HttpHeaders.WWW_AUTHENTICATE, ".*insufficient_scope.*");
~~~

Nếu handler/configuration tùy biến, chính xác header có thể khác; phải kiểm yêu cầu của ứng dụng và loại Authentication do test mutator tạo. Đừng kết luận mọi 403 trong WebFlux đều phải có insufficient_scope.

### 16.3. Test cả phản hồi qua proxy thật

WebTestClient bound to ApplicationContext phù hợp để kiểm web filters và authorization, nhưng không kiểm đầy đủ TLS, gateway, CORS, ingress rewrite hoặc port management production.

Nên có smoke/integration tests trên môi trường test triển khai cho:

- 401 không token.
- 401 invalid_token.
- 403 thiếu scope.
- HTTP header WWW-Authenticate giữ nguyên qua reverse proxy.
- Không redirect HTML khi API cần Bearer challenge.
- Sai issuer/audience và JWKS unreachable.
- Opaque token active=false hoặc introspection upstream error.
- CORS preflight và frontend có thể đọc WWW-Authenticate khi policy cho phép.

## 17. WebFlux có nhiều SecurityWebFilterChain

WebFlux cho phép nhiều **SecurityWebFilterChain**, mỗi chain có matcher và thứ tự.

Ví dụ:

~~~text
@Order(1)
  path /api/**
  OAuth2 Resource Server
  Bearer entry point
  Bearer access denied handler

@Order(2)
  path /web/**
  OAuth2/OIDC login + session
  Redirect entry point khi cần

@Order(3)
  fallback
  denyAll hoặc các ngoại lệ đã xét
~~~

Cần nhớ:

1. **WebFilterChainProxy** chọn chain đầu tiên khớp request.
2. Handler của một chain không tự áp vào chain khác.
3. Nếu URL không khớp chain nào, Spring Security không thể bảo đảm xử lý authentication/authorization.
4. Một catch-all chain mở permitAll đặt trước có thể làm API Bearer chain bị bypass.
5. Một chain login đứng trước API chain có thể khiến API trả 302 thay vì 401.
6. Actuator/management port hoặc context khác có thể cần security policy riêng.

Khi debug 401/403 bất thường, hãy xác định **chain nào thực sự được chọn**, không chỉ mở một configuration class rồi suy đoán.

## 18. Lỗi CSRF trong WebFlux không phải lỗi JWT scope

WebFlux có thể chạy cả OAuth2 Resource Server và CSRF protection. Nếu trình duyệt dùng session cookie/BFF, CSRF có thể cần thiết. Nếu API chỉ có Bearer header chủ động và không có ambient credentials, CSRF threat model khác.

Một POST trả 403 có thể do:

- **CsrfWebFilter** phát hiện CSRF token thiếu/sai.
- AuthorizationWebFilter thấy principal thiếu authority.
- Reactive method security từ chối.
- Domain policy của service từ chối.

**Không sửa mọi 403 bằng cách thêm SCOPE_*** hoặc tắt CSRF bừa bãi.

### 18.1. Kiểm thử CSRF riêng

Spring Security reactive test hỗ trợ **csrf()** configurer để mô phỏng CSRF token trên WebTestClient. Khi chain yêu cầu CSRF token, một test POST chỉ có mockJwt có thể bị 403 trước khi chạm rule scope.

Cần xác định CSRF được bật/tắt theo cách browser gửi credential, không theo tên JWT/opaque hoặc mặc định của một test.

## 19. Opaque token và những lỗi upstream khó chẩn đoán

Khi dùng **ReactiveOpaqueTokenIntrospector**, không phải lỗi nào cũng có nghĩa token active=false.

Ví dụ:

| Trường hợp | Kết luận thích hợp |
|---|---|
| AS trả token active=false | Token không được chấp nhận |
| AS trả active=true, scope thiếu | Token hợp lệ, authorization từ chối |
| AS trả 401 cho introspection client | Credentials/quyền gọi introspection có vấn đề |
| AS timeout/DNS/TLS failure | Không có kết quả xác thực tin cậy |
| AS trả metadata sai contract | Introspector/policy có thể từ chối |
| Cache result active=true còn hiệu lực | Có thể chấp nhận theo TTL đã thiết kế, cần xét revocation latency |

Không “sửa” outage introspection bằng cách chuyển mọi token thành authenticated. Handler nên phân biệt invalid credential với lỗi cấu hình/hạ tầng, không tiết lộ secret hoặc raw token ra client.

### 19.1. ReactiveJwtDecoder cũng có phụ thuộc ngoài

JWT verification thường có thể dùng public keys đã cache, nhưng JWKS rotation, discovery, network outage hoặc metadata sai vẫn có thể gây lỗi tải khóa. Cần thiết lập cache, timeouts, monitoring và quy trình rotation phù hợp.

**Signature failure** khác **JWKS server unavailable** về nguyên nhân, dù phản hồi ngoài có thể cùng bị từ chối để giữ bảo mật.

## 20. Thiết kế lỗi JSON chung nhưng không phá Bearer protocol

Một số hệ thống muốn cả 401/403 đều có response:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Permission required",
  "requestId": "req-123"
}
~~~

Điều này có thể hữu ích cho frontend, nhưng cần nguyên tắc:

- HTTP **status** vẫn đúng.
- **WWW-Authenticate** vẫn có cho OAuth Bearer challenge khi cần.
- **error_description** không chứa thông tin nhạy cảm.
- JSON body không trả credential, claim private, stack trace hoặc đường dẫn nội bộ.
- **requestId** lấy từ request-tracing infrastructure đáng tin cậy, không phản chiếu chuỗi chưa được kiểm trong header.
- Response được viết qua **Mono<Void>** trong reactive pipeline.
- Không tái sử dụng nội dung lỗi bất biến cho mọi trường hợp nếu client cần phân biệt 401 vs 403.
- Không viết JSON ở controller advice rồi kỳ vọng bắt được lỗi authentication ở filter trước controller.

Nếu muốn giữ đủ RFC 6750 auth-params và body JSON, nên thiết kế một **Bearer-aware entry point/access denied handler** với tests contract, thay vì thay handlers mặc định bằng một lambda chỉ đặt HttpStatus.

## 21. Checklist điều tra lỗi xác thực và từ chối truy cập

Khi thấy WebFlux API trả 401/403, có thể điều tra theo thứ tự:

1. **Endpoint/path/method nào?** Có đúng SecurityWebFilterChain không?
2. **Có Authorization: Bearer?** Có token hay chỉ thiếu header?
3. **Bearer token được converter chấp nhận cú pháp?** Có malformed header hoặc nhiều credential không?
4. **JWT được ReactiveJwtDecoder xác minh?** Signature, issuer, audience, exp, nbf, thuật toán/key source?
5. **Opaque token được introspect?** active, AS endpoint, client credentials, TLS/timeout?
6. **Authentication có authorities nào?** SCOPE_*, ROLE_* và mapping custom?
7. **Rule nào được match?** authorizeExchange pathMatchers/anyExchange, method security?
8. **Principal đã authenticated hay anonymous?** Điều này ảnh hưởng entry point/denied handler.
9. **403 có phải CSRF/domain policy không?** Không mặc định là insufficient_scope.
10. **Handler nào viết response?** Bearer entry point, Bearer denied, generic status handler hay global WebFlux handler?
11. **WWW-Authenticate còn nguyên qua gateway?** Có bị proxy loại bỏ hoặc browser CORS che không?
12. **Response đã committed chưa?** Streaming body có thể không đổi status được.
13. **Log có an toàn không?** Không ghi raw token, Authorization, cookies, secrets.
14. **Test có chạy security web filters thật?** Không chỉ mock controller.
15. **Sự cố chỉ xảy ra trên production?** So cấu hình chain, profile, issuer/JWKS, reverse proxy và certificate.

### 21.1. Những anti-pattern cần tránh

- Bắt tất cả exception rồi trả **200 OK** với JSON lỗi.
- Mọi 403 đều bị đổi thành 401 để “client refresh token”.
- Mọi 401 bị redirect 302 đến trang đăng nhập khi API là Resource Server.
- Thay Bearer entry point bằng generic status handler và mất WWW-Authenticate.
- Tự map tất cả AccessDeniedException thành insufficient_scope.
- Đọc JWT claims trước khi verify để quyết định role.
- Gọi **block()** trong WebFilter, entry point hoặc denied handler.
- Dựa vào ThreadLocal security context trong Reactor pipeline.
- Tự subscribe để ghi response ngoài reactive chain.
- Cố thay HTTP status khi response đã commit.
- Dùng MockMvc Servlet để kiểm WebFlux SecurityWebFilterChain.
- Test 404 của một URL không có handler rồi cho rằng authorization đã hoạt động.
- Tắt CSRF toàn hệ thống mà không xét browser cookie authentication.
- Bật CORS quá rộng để “sửa” 401/403.
- Fail-open khi introspection/JWKS upstream không truy cập được.

## 22. Bài tập tự kiểm tra

**Câu 1. Một request GET protected endpoint không có Authorization header. Handler nào nên xử lý?**

Authentication entry point, thường là **BearerTokenServerAuthenticationEntryPoint**, trả Bearer challenge **401**, không bắt buộc có error code.

**Câu 2. JWT hợp lệ nhưng thiếu SCOPE_orders.read. Kết quả nào đúng?**

Authorization từ chối; thường **403**. BearerTokenServerAccessDeniedHandler có thể thêm **insufficient_scope** nếu nhận diện OAuth2 Authentication hợp lệ.

**Câu 3. ServerAuthenticationFailureHandler khác ServerAuthenticationEntryPoint ở đâu?**

Failure handler xử lý **một lần thử authentication đã thất bại** trong AuthenticationWebFilter. Entry point bắt đầu một **authentication challenge**; failure handler có thể ủy quyền cho entry point qua adapter.

**Câu 4. Có nên dùng HttpStatusServerEntryPoint để trả 401 cho mọi OAuth2 Resource Server?**

Không mặc định. Nó có thể thiếu **WWW-Authenticate** theo RFC 6750. Dùng Bearer-specific entry point hoặc custom implementation giữ contract.

**Câu 5. Trong WebFlux có thể lấy principal an toàn từ SecurityContextHolder ThreadLocal như Servlet không?**

Không nên dựa vào đó. Với reactive pipelines, dùng **ReactiveSecurityContextHolder** và những integration Reactor-aware.

**Câu 6. Tại sao một POST dùng mockJwt vẫn trả 403?**

Có thể **CsrfWebFilter** đang yêu cầu CSRF token, hoặc thiếu authority, hoặc bị domain policy từ chối. Phải xác định nguyên nhân thật trước khi sửa.

**Câu 7. Opaque token introspection timeout có được coi là active=true không?**

Không. Không xác minh được token thì không được tạo authenticated principal theo kiểu fail-open.

**Câu 8. Có phải mọi lỗi controller đều đi qua Bearer access denied handler?**

Không. Validation, not found và database errors thường được xử lý bởi application/WebFlux exception mapping. Bearer denied handler chủ yếu dùng cho security access denial trong pipeline tương ứng.

**Câu 9. WebFlux có hai SecurityWebFilterChain, cả hai khớp một URL. Cả hai handler đều chạy không?**

Không. Chain được chọn theo thứ tự, chain đầu tiên khớp được dùng. Cấu hình thứ tự ảnh hưởng handler/challenge.

**Câu 10. Vì sao không trả error_description là toàn bộ exception.getMessage()?**

Vì exception message có thể chứa raw token, dữ liệu nội bộ, ký tự không hợp lệ trong HTTP header hoặc thông tin giúp attacker dò trạng thái token. Cần thông điệp tối thiểu và phù hợp RFC.

## Kết luận

Trong **Spring Security WebFlux Resource Server**, lỗi xác thực và từ chối truy cập là hai nhánh khác nhau:

- **Authentication failure**: credential thiếu/không hợp lệ; thường đi qua **ServerAuthenticationEntryPoint**, trong Bearer API là **BearerTokenServerAuthenticationEntryPoint**, trả **401** và header **WWW-Authenticate: Bearer**.
- **Authorization failure**: Authentication đã được thiết lập nhưng không đủ scope/role/quyền; đi qua **ServerAccessDeniedHandler**, trong Bearer API thường là **BearerTokenServerAccessDeniedHandler**, trả **403** và có thể có **insufficient_scope**.
- **AuthenticationWebFilter** có **ServerAuthenticationFailureHandler** riêng; **ExceptionTranslationWebFilter** điều phối những lỗi security downstream. Không phải mọi error chỉ đi qua một handler.
- **ReactiveSecurityContextHolder** và **Mono<Void>** phản ánh mô hình Reactor; không dùng blocking I/O hoặc ThreadLocal assumptions khi tùy biến handlers.

Thiết kế đúng là **xác minh token bằng nguồn tin cậy → tạo Authentication reactive → kiểm authority/domain policy → trả 401/403 với challenge thích hợp khi thất bại**. Không hy sinh RFC 6750, không tiết lộ credential và không fail-open để biến lỗi thành response dễ nhìn.

### Tài liệu tham khảo

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth2 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — Reactive OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security API — ServerHttpSecurity.OAuth2ResourceServerSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2ResourceServerSpec.html)
- [Spring Security API — ExceptionTranslationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [Spring Security API — BearerTokenServerAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenServerAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html)
- [Spring Security API — ServerAuthenticationEntryPointFailureHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html)
- [Spring Security API — ServerAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
