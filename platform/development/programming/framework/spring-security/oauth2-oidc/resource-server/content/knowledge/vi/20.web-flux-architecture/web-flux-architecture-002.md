# AuthenticationWebFilter và chuỗi xác thực phản ứng

Trong **Spring Security OAuth 2.0 / OIDC Resource Server** chạy trên **Spring WebFlux**, xác thực Bearer access token không đi theo chuỗi `Filter` của Servlet như trong Spring MVC. Thay vào đó, Spring Security dùng một chuỗi **`WebFilter` phản ứng** xây dựng từ `SecurityWebFilterChain`. Một thành phần trung tâm trong chuỗi này là **`AuthenticationWebFilter`**: nó nhận thông tin xác thực từ `ServerWebExchange`, gọi **`ReactiveAuthenticationManager`**, xử lý thành công/thất bại và đưa danh tính đã xác thực vào **Reactor Context** để authorization và nghiệp vụ dùng trong cùng luồng reactive.

Hiểu `AuthenticationWebFilter` giúp giải thích chính xác những câu hỏi thường gặp:

- Vì sao cấu hình `oauth2ResourceServer().jwt()` hoặc `opaqueToken()` có thể xác thực token mà không cần viết filter thủ công?
- Bearer token được lấy từ request ở bước nào?
- `AuthenticationWebFilter` gọi manager nào để xác thực JWT hoặc opaque token?
- Làm thế nào `Authentication` và authorities đi tới `@PreAuthorize`, `ReactiveSecurityContextHolder` và reactive service?
- Vì sao dùng `SecurityContextHolder.getContext()` kiểu Servlet hoặc gọi `block()` trong event loop có thể gây lỗi?
- Khi token thiếu, sai hoặc không đủ scope, ai trả 401/403?
- Khi cần custom converter hoặc xác thực riêng, nên tùy chỉnh ở đâu để **không nhân đôi filter** và không bỏ xác minh token?

Bài học tập trung vào **kiến trúc WebFlux**, tức luồng xử lý không chặn của Spring Security trên WebFlux, không đồng nhất với cấu hình **`SecurityFilterChain` và `BearerTokenAuthenticationFilter`** của Servlet.

> **Ngữ cảnh ví dụ:** Authorization Server phát hành JWT access token có `iss=https://login.example.com`, `aud=orders-api` và `scope=orders.read`. Orders API chạy Spring Boot 3.x / Spring Security 6.x, Spring WebFlux và nhận `Authorization: Bearer <access-token>`. Các tên miền, token và định danh đều là ví dụ minh họa.

## 1. So sánh kiến trúc Servlet và WebFlux

Spring Security hỗ trợ hai mô hình web riêng. Chúng cùng có `Authentication`, `GrantedAuthority`, `SecurityContext` và các khái niệm OAuth2, nhưng **API filter, cách lan truyền context và kiểu trả về khác nhau**.

| Thành phần / khái niệm | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Chuỗi security | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Đối tượng cấu hình | `HttpSecurity` | `ServerHttpSecurity` |
| Cơ chế chặn request | Servlet `Filter` | Reactive `WebFilter` |
| Filter Bearer chính | `BearerTokenAuthenticationFilter` | `AuthenticationWebFilter` được cấu hình cho Resource Server |
| Dữ liệu HTTP | `HttpServletRequest` | `ServerWebExchange` |
| Lấy Bearer token | `BearerTokenResolver` | `ServerAuthenticationConverter`, thường `ServerBearerTokenAuthenticationConverter` |
| Xác thực | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Lưu danh tính trong quá trình xử lý | `SecurityContextHolder`, thường dựa trên ThreadLocal | `ReactiveSecurityContextHolder` dựa trên Reactor Context |
| Trả kết quả từ xác thực | `Authentication` | `Mono<Authentication>` |
| Chuỗi authorization | `AuthorizationFilter` / method interceptor | Reactive authorization web filter / reactive method security |
| HTTP response lỗi | Servlet entry point/denied handler | `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` |

**Đừng chép nguyên đoạn `HttpSecurity` của Servlet sang WebFlux.** Ví dụ `SecurityFilterChain`, `JwtDecoder` và `BearerTokenAuthenticationFilter` không phải những thành phần thích hợp để cấu hình luồng reactive.

### 1.1. “Phản ứng” ở đây nghĩa là gì?

Spring WebFlux dùng Reactor với hai kiểu phổ biến:

- `Mono<T>`: bất đồng bộ, phát ra **0 hoặc 1** giá trị hoặc tín hiệu lỗi.
- `Flux<T>`: bất đồng bộ, phát ra **0 đến nhiều** giá trị hoặc tín hiệu lỗi.

Một `ReactiveAuthenticationManager` không trả ngay `Authentication`, mà trả:

```java
Mono<Authentication> authenticate(Authentication authentication);
```

Kết quả chỉ được xử lý khi reactive publisher được **subscribe** như một phần của request. Các bước xác thực, authorization và controller được ghép thành **reactive pipeline**, không phải một chuỗi lời gọi đồng bộ rồi chờ kết quả trên request thread.

Tuy nhiên, **API trả `Mono` không tự làm code bên trong nonblocking**. Nếu tự gọi database JDBC blocking hoặc `RestTemplate` blocking trên event loop, hệ thống vẫn có thể nghẽn dù chữ ký phương thức là `Mono<...>`.

## 2. Toàn cảnh chuỗi WebFlux Security

Ở WebFlux, Spring Security đăng ký `WebFilterChainProxy` với các `SecurityWebFilterChain`. Mỗi chain chứa những WebFilter theo thứ tự thích hợp. Một số lớp xử lý:

1. Khôi phục/đặt security context từ repository nếu cấu hình.
2. Chuyển đổi credential của request thành một authentication request.
3. Gọi authentication manager để xác minh credential.
4. Ghi nhận authentication thành công trong context của reactive chain.
5. Xử lý exception authentication/authorization.
6. Kiểm tra các quy tắc `authorizeExchange`.
7. Cho request đi tới handler/controller nếu đủ điều kiện.

### 2.1. Một luồng Bearer JWT điển hình

```mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth Client
    participant Proxy as WebFilterChainProxy
    participant Filter as AuthenticationWebFilter
    participant Converter as ServerBearerTokenAuthenticationConverter
    participant Manager as JwtReactiveAuthenticationManager
    participant Decoder as ReactiveJwtDecoder
    participant Context as Reactor Security Context
    participant Authz as Authorization WebFilter
    participant Handler as WebFlux Handler
    Client->>Proxy: GET /api/orders/42 + Authorization: Bearer JWT
    Proxy->>Filter: Trao ServerWebExchange
    Filter->>Converter: convert(exchange)
    Converter-->>Filter: Mono<BearerTokenAuthenticationToken>
    Filter->>Manager: authenticate(authenticationRequest)
    Manager->>Decoder: decode(raw JWT)
    Decoder->>Decoder: Verify signature, issuer, exp và validators
    Decoder-->>Manager: Mono<Jwt>
    Manager-->>Filter: Mono<Authentication> (JwtAuthenticationToken)
    Filter->>Context: Đưa SecurityContext vào Reactor Context
    Filter->>Authz: Tiếp tục reactive chain
    Authz->>Authz: Kiểm tra SCOPE_orders.read
    Authz->>Handler: Cho phép gọi handler
    Handler-->>Client: Kết quả được phép
```

Trong trường hợp opaque token, khối `JwtReactiveAuthenticationManager / ReactiveJwtDecoder` được thay bằng manager và introspector reactive dành cho opaque token; các bước còn lại vẫn mang mô hình Bearer.

### 2.2. Luồng thất bại

```mermaid
flowchart TD
    A["ServerWebExchange"] --> B["ServerAuthenticationConverter"]
    B --> C{"Có credential dùng được?"}
    C -->|Không có| D["Mono.empty() / tiếp tục chain"]
    D --> E{"Endpoint yêu cầu xác thực?"}
    E -->|Có| F["401 Bearer challenge"]
    E -->|Không| G["Public endpoint"]
    C -->|Credential sai cú pháp| H["Authentication error"]
    H --> F
    C -->|Có credential| I["ReactiveAuthenticationManager"]
    I --> J{"Token xác minh thành công?"}
    J -->|Không| F
    J -->|Có| K["Reactive SecurityContext"]
    K --> L{"Có authority yêu cầu?"}
    L -->|Không| M["403 Forbidden"]
    L -->|Có| N["Service kiểm tra tenant/owner/state"]
    N --> O{"Được phép trên tài nguyên?"}
    O -->|Không| P["403 / 404 theo chính sách"]
    O -->|Có| Q["Xử lý request"]
```

**Phân biệt quan trọng:** không có credential thường được biểu diễn bằng `Mono.empty()` ở converter. Điều đó **không có nghĩa public API tự được mở**: nếu endpoint đòi authenticated, authorization/exception handling sẽ trả 401.

## 3. AuthenticationWebFilter làm những công việc nào?

`AuthenticationWebFilter` là một **WebFilter tổng quát cho authentication**. Nó không chỉ dành riêng cho JWT; các cơ chế WebFlux khác có thể dùng nó với converter và manager khác nhau.

Đường xử lý khái niệm:

```text
AuthenticationWebFilter.filter(exchange, chain)
   |
   +-- requiresAuthenticationMatcher.matches(exchange)?
   |       |
   |       +-- false -> chain.filter(exchange)
   |
   +-- ServerAuthenticationConverter.convert(exchange)
   |       |
   |       +-- Mono.empty() -> chain.filter(exchange)
   |       +-- Mono.error(...) -> authentication failure
   |       +-- Mono<Authentication request>
   |
   +-- ReactiveAuthenticationManager.authenticate(request)
   |       |
   |       +-- Mono<Authentication success> -> success handler
   |       +-- Mono.error(AuthenticationException) -> failure handler
   |       +-- Mono.empty() -> no matching authentication outcome
   |
   +-- Lưu/lan truyền SecurityContext cho phần sau
   |
   +-- chain.filter(exchange) dưới Reactor Context phù hợp
```

Đây là mô tả kiến trúc ở mức logic; các bước chi tiết và cách triển khai success/error được quyết định bởi phiên bản Spring Security, `ServerAuthenticationSuccessHandler`, `ServerAuthenticationFailureHandler` và `ServerSecurityContextRepository` được gắn.

### 3.1. `requiresAuthenticationMatcher`

Matcher xác định **khi nào filter nên thử xác thực**. Trong Resource Server, Spring DSL sẽ gắn filter vào chain/đường xử lý phù hợp. Nếu tự tạo filter, có thể đặt matcher để tránh thử xác thực ở đường không liên quan.

Ví dụ:

```java
authenticationWebFilter.setRequiresAuthenticationMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**")
);
```

Đây là một lựa chọn **bên trong filter**. Nó không thay thế `securityMatcher(...)` của toàn `SecurityWebFilterChain`. Nếu chain không được chọn, filter trong chain đó không chạy dù matcher nội bộ có khớp.

### 3.2. `ServerAuthenticationConverter`

Converter đọc `ServerWebExchange` và tạo yêu cầu xác thực:

```java
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
```

Với Bearer Resource Server, converter phổ biến là `ServerBearerTokenAuthenticationConverter`. Nó đọc Bearer credential theo quy tắc cấu hình và tạo một `BearerTokenAuthenticationToken` **chưa được xác thực**.

Đừng nhầm converter ở đây với `JwtAuthenticationConverter`:

- **`ServerBearerTokenAuthenticationConverter`:** request HTTP → raw Bearer authentication request.
- **JWT authentication converter:** `Jwt` đã được decoder xác minh → principal/authorities trong `Authentication`.

Hai converter giải quyết **hai tầng khác nhau**. Cái thứ nhất không đọc hay xác minh chữ ký JWT. Cái thứ hai không lấy token trực tiếp từ HTTP header.

### 3.3. `ReactiveAuthenticationManager`

Manager nhận authentication request chưa xác minh và phát ra một authentication hợp lệ hoặc lỗi:

```java
Mono<Authentication> authenticate(Authentication authentication);
```

Trong Resource Server:

- JWT: `JwtReactiveAuthenticationManager` phối hợp `ReactiveJwtDecoder`.
- Opaque token: manager reactive cho opaque token phối hợp `ReactiveOpaqueTokenIntrospector`.

Manager **không nên** chỉ đặt `authenticated=true` cho bất kỳ chuỗi Bearer nào. Nó phải dựa vào kết quả giải mã/xác minh hoặc introspection đáng tin, kiểm tra điều kiện hợp đồng và tạo principal/authorities đúng chính sách.

### 3.4. Success handler và failure handler

Khi authentication thành công, `AuthenticationWebFilter` dùng cơ chế success handling để đưa security context vào pipeline và tiếp tục chain. Khi có `AuthenticationException`, failure handling có thể gửi response 401/challenge phù hợp.

Các interface liên quan:

- `ServerAuthenticationSuccessHandler`.
- `ServerAuthenticationFailureHandler`.
- `ServerSecurityContextRepository`.
- `ServerAuthenticationEntryPoint`.
- `ServerAccessDeniedHandler`.

Nếu tùy chỉnh chúng, cần giữ logic Bearer challenge, không vô tình redirect sang HTML login, không lưu token trong session ngoài ý muốn và không tiếp tục cho phép request khi xác thực thất bại.

## 4. Bearer token được lấy từ HTTP request ra sao?

Request thông thường:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

`ServerBearerTokenAuthenticationConverter` xử lý chuỗi credential theo hợp đồng Bearer. Kết quả là authentication request chứa raw token value.

**Đừng diễn giải Bearer token được gửi từ client là dữ liệu đã đáng tin.** Một request có thể gửi token sai chữ ký, hết hạn, token do issuer khác phát hành, hoặc thậm chí một chuỗi ngẫu nhiên.

### 4.1. Token trong query string là một lựa chọn nguy hiểm

Truyền token bằng:

```text
GET /api/orders?access_token=...
```

có thể làm lộ token qua URL, proxy logs, browser history, monitoring, referer hoặc cache. Các converter thường ưu tiên cơ chế `Authorization: Bearer` và không nên bật nhận token query parameter trừ khi có ngoại lệ được đánh giá kỹ.

Không “sửa lỗi mobile client không gửi header” bằng cách bật nhận token từ bất kỳ query/body tùy ý nào. Hãy thống nhất client sử dụng Bearer header.

### 4.2. Converter không tạo quyền từ header tùy ý

Những header như:

```http
X-User: admin
X-Roles: ORDER_MANAGER
X-Tenant: tenant-a
```

không phải nguồn authentication đáng tin chỉ vì chúng có mặt. Nếu converter tự tạo principal/authorities từ các header do caller kiểm soát, nó bỏ qua các bước xác minh token và tạo nguy cơ leo thang quyền.

Nếu gateway gửi identity headers, phải có cơ chế xác thực gateway–service và ranh giới tin cậy riêng, không áp quy tắc đó mặc định cho một Resource Server công khai.

## 5. Cấu hình WebFlux JWT Resource Server cơ bản

### 5.1. Dependencies

Ví dụ Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Đây là **WebFlux stack**, không dùng `spring-boot-starter-web` để minh họa vì starter MVC có thể làm thay đổi kiểu web application được Boot chọn khi cả hai framework có mặt.

### 5.2. Cấu hình issuer và audience

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

Giải thích:

- `issuer-uri` chọn issuer mà Resource Server tin cậy.
- Cơ chế auto-configuration có thể sử dụng metadata/JWKS của issuer để tạo `ReactiveJwtDecoder`.
- `audiences` là property do những phiên bản Spring Boot tương ứng hỗ trợ; nếu dùng phiên bản khác hoặc decoder tùy chỉnh, phải cấu hình validator audience riêng.
- JWT decoder xác minh token theo các validators đã cấu hình (signature, thời hạn, issuer, audience và điều kiện khác).
- Việc xác minh chữ ký/claims là điều kiện tiên quyết trước khi converter tạo authentication.

Một JWT truy cập dành cho Billing API có `aud=billing-api` không nên được Orders API nhận chỉ vì tên scope tình cờ là `orders.read`.

### 5.3. Tạo SecurityWebFilterChain

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOrdersSecurity {

    @Bean
    SecurityWebFilterChain ordersApiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api", "/api/**")
            )
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new BearerTokenServerAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenServerAccessDeniedHandler()
                )
            )
            .build();
    }
}
```

**Quan trọng về CSRF:** `csrf(...disable)` trong ví dụ chỉ dành cho **API nhận Bearer header, không dựa vào session cookie tự gửi từ browser**. Nếu API còn chấp nhận cookie hoặc mô hình đăng nhập browser khác, cần thiết kế CSRF theo thực tế, không tắt toàn ứng dụng.

**Quan trọng về URL:** `securityMatcher("/api", "/api/**")` chọn chain cho các URL này. Các đường khác phải được bảo vệ bởi chain phù hợp hoặc fallback. Một `SecurityWebFilterChain` có matcher hẹp không bảo vệ toàn ứng dụng.

### 5.4. AuthenticationWebFilter xuất hiện ở đâu?

Bạn không thấy câu lệnh:

```java
new AuthenticationWebFilter(...)
```

trong cấu hình trên, bởi Spring Security **tạo và nối các thành phần xác thực Bearer** khi DSL `oauth2ResourceServer(...jwt(...))` được bật. Theo kiến trúc Resource Server, filter xác thực được cấu hình với một converter đọc Bearer token và manager xác minh JWT.

Đây là cách nên ưu tiên khi dùng JWT/Opaque token chuẩn: **cấu hình bằng DSL** và chỉ tùy chỉnh manager/converter/decoder nơi thật sự cần. Tự tạo một AuthenticationWebFilter bổ sung trong cùng chain có thể gây xác thực lặp, tranh chấp handler hoặc sai thứ tự xử lý.

### 5.5. Cấu hình stateless nghĩa là gì?

`NoOpServerSecurityContextRepository` thể hiện không lưu/đọc SecurityContext từ repository session theo cấu hình đó. Trong Bearer API, caller thường gửi access token **cho mỗi request**.

Dù stateless, request hiện tại vẫn có `Authentication` trong **Reactor Context** sau khi xác thực thành công. “Không lưu session” không đồng nghĩa “không có SecurityContext”.

## 6. JWT đi qua ReactiveJwtDecoder và manager như thế nào?

Ví dụ payload JWT đã được ký:

```json
{
  "iss": "https://login.example.com",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a",
  "exp": 2000000000
}
```

Luồng xử lý:

```text
ServerBearerTokenAuthenticationConverter
    → BearerTokenAuthenticationToken(raw JWT)
    → JwtReactiveAuthenticationManager
    → ReactiveJwtDecoder.decode(raw JWT)
    → Jwt đã xác minh hoặc AuthenticationException
    → Converter từ Jwt sang Authentication
    → JwtAuthenticationToken với authorities
    → Reactor SecurityContext
```

### 6.1. Decode payload khác verify token

Một JWT có thể được Base64URL-decode bởi bất kỳ client nào, nhưng điều đó **không chứng minh** token được phát hành bởi issuer đáng tin.

`ReactiveJwtDecoder` phải xác minh chữ ký và các điều kiện bắt buộc như thời hạn, issuer, audience. Nếu token bị sửa `scope` nhưng chữ ký không còn đúng, decoder từ chối trước khi tạo authorities.

**Không gọi `Jwt.withTokenValue(...)` với chuỗi do client gửi rồi tự đặt authenticated=true trong production.** API builder này có thể hữu ích cho test nhưng không thay verification.

### 6.2. Kết quả Authentication

Với converter JWT thông thường:

```text
Principal object:
  Jwt

Authentication type:
  JwtAuthenticationToken

Authentication name:
  sub (mặc định)

Granted authorities:
  SCOPE_orders.read
  SCOPE_orders.write
```

Các scope từ `scope` hoặc `scp` thường được ánh xạ thành authorities có tiền tố `SCOPE_`. `Authentication.getName()` mặc định thường dùng `sub`; không mặc định là email, `UserDetails` hoặc entity customer trong database.

### 6.3. Token hợp lệ không có nghĩa quyền trên mọi đơn hàng

Một JWT có `SCOPE_orders.read` chỉ cho phép loại thao tác được thỏa thuận. Service còn phải kiểm tra:

- Đơn thuộc tenant nào?
- Subject có quyền sở hữu hoặc được ủy quyền không?
- Endpoint có chấp nhận client credentials hoặc chỉ user-delegated?
- Đơn có trạng thái cho phép thao tác không?
- Quyền role/tenant membership có còn hiệu lực theo hợp đồng không?

**AuthenticationWebFilter xác thực credential, không thay thế object-level authorization.**

## 7. Tùy chỉnh authorities và tên principal trong WebFlux

Spring Security cho phép tùy chỉnh converter từ `Jwt` đã xác minh thành authentication.

Ví dụ Authorization Server phát hành:

```json
{
  "sub": "customer-42",
  "preferred_username": "lan.nguyen",
  "permissions": ["orders.read", "orders.export"],
  "scope": "orders.read"
}
```

Nếu `permissions` là claim quyền nghiệp vụ đáng tin theo hợp đồng, có thể tạo một converter JWT tương thích và bọc bằng **`ReactiveJwtAuthenticationConverterAdapter`**.

### 7.1. Adapter từ JwtAuthenticationConverter sang reactive

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import reactor.core.publisher.Mono;

@Configuration
public class JwtAuthoritiesConfiguration {

    @Bean
    Converter<Jwt, Mono<AbstractAuthenticationToken>> jwtToAuthentication() {
        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();

        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERMISSION_");

        JwtAuthenticationConverter blockingStyleConverter =
            new JwtAuthenticationConverter();

        // Chỉ đổi getName() khi hợp đồng bảo đảm claim thích hợp.
        // Nếu cần identity ổn định, giữ sub thay vì username/email.
        blockingStyleConverter.setPrincipalClaimName("sub");
        blockingStyleConverter.setJwtGrantedAuthoritiesConverter(
            permissions
        );

        return new ReactiveJwtAuthenticationConverterAdapter(
            blockingStyleConverter
        );
    }
}
```

Cấu hình Resource Server sử dụng bean converter:

```java
@Bean
SecurityWebFilterChain customJwtChain(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>>
            jwtToAuthentication) {

    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        )
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/export/**")
                .hasAuthority("PERMISSION_orders.export")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtToAuthentication)
            )
        )
        .build();
}
```

Hai đoạn cấu hình ở đây là **biến thể thay thế** cho cấu hình `ordersApiChain` trước, không phải gợi ý đăng ký hai chain cùng matcher không có kiểm soát.

### 7.2. Cẩn thận khi thay authorities converter

Khi gọi `setJwtGrantedAuthoritiesConverter(permissions)`, converter mặc định đọc `scope/scp` **bị thay thế** bằng converter đọc `permissions`. Vì vậy `SCOPE_orders.read` không còn tự xuất hiện nếu bạn không hợp nhất.

Nếu API cần cả scope và permissions:

1. Giữ converter scope riêng để đọc `scope/scp` thành `SCOPE_*`.
2. Xây converter tùy chỉnh hợp nhất kết quả scope và claim permission được phê duyệt.
3. Dùng `GrantedAuthority` names có namespace phân biệt, ví dụ `SCOPE_*`, `PERMISSION_*`.
4. Không cấp quyền từ mọi chuỗi role/permission không nằm trong allowlist.
5. Chỉ dùng những claims mà issuer/audience contract bảo đảm, không suy từ dữ liệu user tự khai.

### 7.3. “Reactive” adapter có làm mọi converter thành nonblocking không?

**Không.** `ReactiveJwtAuthenticationConverterAdapter` có thể bọc một converter đồng bộ trả authentication thành `Mono`; nó **không biến** một đoạn JDBC blocking hoặc HTTP blocking bên trong converter thành thao tác I/O nonblocking.

Nếu cần tải quyền từ database ở bước authentication:

- Cân nhắc có nên đưa quyền động vào authentication hay kiểm tra ở service/method security.
- Nếu cần I/O reactive, sử dụng converter hợp đồng reactive phù hợp thay vì gọi `block()`.
- Chú ý timeout, quyền sở hữu dữ liệu, cache và việc revoke quyền.
- Không tạo nested `subscribe()` để “đợi sau”; Spring Security cần nhận đúng `Mono<Authentication>` đã hoàn tất để đưa kết quả vào SecurityContext.

## 8. Reactive opaque token cũng dùng AuthenticationWebFilter

Khi Authorization Server phát hành opaque token, API có thể dùng introspection:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Reactive DSL:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Luồng tổng quát:

```text
ServerBearerTokenAuthenticationConverter
    → BearerTokenAuthenticationToken
    → Reactive authentication manager for opaque token
    → ReactiveOpaqueTokenIntrospector.introspect(token)
    → HTTPS POST tới Authorization Server
    → active=true + attributes hoặc lỗi
    → BearerTokenAuthentication
    → Reactor SecurityContext
```

**Khác biệt chính so với JWT:**

| Vấn đề | JWT | Opaque |
|---|---|---|
| Cơ chế kiểm tra | `ReactiveJwtDecoder` xác minh signature/claims | `ReactiveOpaqueTokenIntrospector` hỏi AS |
| Thông tin nhận về | `Jwt` đã verify | `OAuth2AuthenticatedPrincipal`/attributes từ introspection |
| Authentication thường gặp | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Network dependency | Có thể tải/discover JWKS, sau đó xác minh local | Thường gọi AS cho introspection theo policy |
| Hiệu lực revoke | Cần thiết kế riêng nếu chỉ xác minh JWT offline | Có thể phản ánh khi introspect lại, tùy AS/cache |
| Truyền danh tính qua reactive pipeline | Reactor SecurityContext | Reactor SecurityContext |

Opaque token không làm WebFlux tự “bớt reactive”. Nếu custom introspector gọi `RestTemplate` blocking trực tiếp trong event-loop, nó gây nguy cơ nghẽn. Dùng `ReactiveOpaqueTokenIntrospector` và HTTP client reactive phù hợp.

### 8.1. Introspection vẫn phải fail closed

Nếu AS trả `active=false`, client secret sai, TLS lỗi hoặc endpoint timeout, không tự tạo authenticated principal cho token chưa được kiểm tra.

Một token `active=true` cũng chưa chứng minh có quyền trên mọi tài nguyên: scope, audience/resource contract, tenant và ownership vẫn cần được kiểm tra.

## 9. Khi nào nên tạo AuthenticationWebFilter thủ công?

**Thông thường không cần** cho Resource Server chỉ dùng JWT hoặc opaque token chuẩn. `ServerHttpSecurity.oauth2ResourceServer(...)` đã cấu hình đường xác thực Bearer.

Việc tự tạo `AuthenticationWebFilter` hữu ích khi có **một cơ chế xác thực riêng**, ví dụ:

- Một API endpoint nội bộ dùng credential do tổ chức định nghĩa, không phải OAuth Bearer.
- Một thiết kế multi-tenant/multi-issuer với quản lý authentication khác cần custom routing có kiểm soát.
- Một chain riêng có yêu cầu authentication converter/manager không thể biểu diễn an toàn qua DSL chuẩn.
- Một lớp bảo mật giao thức đặc thù đã được thẩm định.

Tuy nhiên, không nên dùng custom filter để tự parse JWT payload rồi cấp authorities mà bỏ `ReactiveJwtDecoder`.

### 9.1. Ví dụ cấu hình filter JWT thủ công — hiểu cấu trúc

Ví dụ dưới đây minh họa các điểm nối. Nó là **một cách thay thế cho DSL Resource Server**, không được đặt thêm cạnh `oauth2ResourceServer().jwt()` trên cùng chain nếu không có thiết kế rất cụ thể để tránh hai filter Bearer cùng thử xác thực.

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.web.server.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
public class ManualBearerFilterConfiguration {

    @Bean
    SecurityWebFilterChain manualApiChain(
            ServerHttpSecurity http,
            ReactiveJwtDecoder decoder) {

        var manager = new JwtReactiveAuthenticationManager(decoder);

        AuthenticationWebFilter bearerFilter =
            new AuthenticationWebFilter(manager);

        bearerFilter.setServerAuthenticationConverter(
            new ServerBearerTokenAuthenticationConverter()
        );

        bearerFilter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        );

        bearerFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        bearerFilter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                new BearerTokenServerAuthenticationEntryPoint()
            )
        );

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**")
            )
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated()
            )
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .csrf(csrf -> csrf.disable())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new BearerTokenServerAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenServerAccessDeniedHandler()
                )
            )
            .addFilterAt(
                bearerFilter,
                SecurityWebFiltersOrder.AUTHENTICATION
            )
            .build();
    }
}
```

**Giới hạn kỹ thuật:** ví dụ trình bày cách kết nối các API WebFlux/Spring Security 6.x phổ biến, nhưng cần điều chỉnh đúng version, matchers, error handling, token validators và các chain khác khi áp dụng. Ở production, **DSL `oauth2ResourceServer().jwt()` là đường cấu hình ưu tiên** vì nó bao gồm các integration/handler chính thức của Spring Security.

### 9.2. Giải thích từng nút trong ví dụ

- `ReactiveJwtDecoder` vẫn là bộ **xác minh** JWT; không bỏ qua signature, issuer, audience, timestamps.
- `JwtReactiveAuthenticationManager` chuyển Bearer authentication request thành `Mono<Authentication>` qua decoder và converter.
- `ServerBearerTokenAuthenticationConverter` đọc Bearer credential từ `ServerWebExchange`.
- `AuthenticationWebFilter` điều phối converter, manager và success/failure.
- `NoOpServerSecurityContextRepository` tránh lưu authentication vào web session.
- `ServerAuthenticationEntryPointFailureHandler` điều hướng lỗi xác thực đến Bearer entry point.
- `SecurityWebFiltersOrder.AUTHENTICATION` xác định vị trí của custom filter trong reactive filter chain.
- `authorizeExchange(...authenticated())` vẫn cần thiết để request **không có token** không được phép vào protected handler.

Nếu filter bị đặt sai thứ tự so với authorization hoặc exception translation, kết quả 401/403 có thể không đúng như mong đợi. Đừng suy ra thứ tự execution bằng vị trí các lệnh gọi DSL trong Java; sử dụng `SecurityWebFiltersOrder` và cấu hình chính thức.

## 10. AuthenticationWebFilter và ReactiveAuthenticationManagerResolver

Một số hệ thống nhận token từ **nhiều issuer**, môi trường hoặc tenant có hợp đồng riêng. Trong trường hợp này, authentication manager có thể cần được chọn theo ngữ cảnh request đáng tin.

Spring Security cung cấp cơ chế resolver cho reactive authentication manager trong `AuthenticationWebFilter`, cho phép lựa chọn manager trong quá trình xử lý exchange.

Mô hình:

```text
ServerWebExchange
    |
    v
Resolver chọn ReactiveAuthenticationManager phù hợp
    |
    +--> Manager for trusted issuer A
    +--> Manager for trusted issuer B
    |
    v
Manager xác minh token theo issuer/keys/audience chính xác
```

**Cảnh báo:** thông tin chưa được xác minh từ JWT payload **không phải bằng chứng tin cậy về issuer**. Nó có thể được dùng như *hint* để chọn một manager từ **allowlist cố định**, nhưng manager được chọn vẫn phải thực sự xác minh chữ ký, issuer, audience và các token profiles.

Không lấy claim `iss` hoặc HTTP header do client tự gửi rồi tùy ý tạo HTTP client gọi JWKs/introspection URL từ đó. Làm vậy dễ gây SSRF, lộ token hoặc nhầm issuer.

### 10.1. Hai sai lầm thiết kế phổ biến

**Sai lầm 1 — Một manager mặc định dùng chung toàn hệ thống nhưng không kiểm tra issuer/audience.** Token hợp lệ của API khác có thể bị chấp nhận do key/trust configuration quá rộng.

**Sai lầm 2 — Resolver tạo manager mới và tải JWKS theo URL do token tự khai ở mỗi request.** Điều này làm mất allowlist, tạo network/resource exhaustion và có nguy cơ kết nối tới host do kẻ tấn công chỉ định.

Với multi-issuer, cần quản lý **trust configuration theo issuer được phép**, cache decoder/keys phù hợp và kiểm tra audience của từng Resource Server.

## 11. Reactor Context: SecurityContext được mang đi đâu?

Một khác biệt quan trọng nhất so với Servlet là cách lưu **SecurityContext**.

### 11.1. Servlet: ThreadLocal theo đường xử lý thông thường

Trong Spring MVC đồng bộ, nhiều code đọc:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

Dưới một số cấu hình Servlet, context gắn với thread đang xử lý request. Mô hình này **không nên được áp dụng trực tiếp** cho WebFlux.

### 11.2. WebFlux: Reactor Context

Trong reactive flow:

```java
Mono<SecurityContext> contextMono =
    ReactiveSecurityContextHolder.getContext();
```

`ReactiveSecurityContextHolder` dựa vào **Reactor Context**, gắn với subscriber/pipeline. Vì một pipeline có thể chuyển thread giữa các scheduler, gắn identity vào một ThreadLocal “cố định” sẽ không đáng tin.

```text
Reactive HTTP request
    |
    +--> AuthenticationWebFilter tạo Authentication
    |
    +--> SecurityContext được gắn vào Reactor Context
    |
    +--> Authorization WebFilter
    |
    +--> Controller trả Mono/Flux
    |
    +--> Service, repository reactive
           |
           +--> Cùng subscription/context: đọc identity được
```

Các operator Reactor như `flatMap`, `publishOn` và `subscribeOn` có cơ chế truyền Reactor Context trong chuỗi phù hợp; tuy nhiên **manual subscribe**, callback ngoài pipeline hoặc tích hợp thư viện không tuân context propagation có thể làm mất identity.

### 11.3. Đọc Authentication trong reactive service

```java
package com.example.orders.security;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public final class ReactiveCaller {

    public static Mono<Authentication> currentAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication required"
                )
            ));
    }

    private ReactiveCaller() {
    }
}
```

Đoạn này là helper minh họa; nó không cần thiết nếu controller/service đã có cách lấy Authentication phù hợp. `isAuthenticated()` chưa đủ bảo đảm đúng **loại principal** hay có quyền tài nguyên: service vẫn phải kiểm tra scope, issuer, audience, tenant và ownership.

### 11.4. Đừng tạo Authentication giả để đi qua policy

Không nên dùng:

```java
// Ví dụ cố ý không an toàn: tự tạo quyền admin.
Mono<Result> unsafe = performOperation()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            forgedAdminAuthentication
        )
    );
```

Việc `contextWrite` có thể đính kèm một Authentication **không làm Authentication đó đáng tin**. Chỉ trust boundary thực sự xác thực credential hoặc một workload identity được quản trị rõ ràng mới được tạo context dùng cho phân quyền.

Trong **unit tests**, việc tạo Authentication thử nghiệm là bình thường; trong production, tự giả danh user/admin để “fix missing context” là anti-pattern.

## 12. Đừng block hoặc subscribe thủ công trong pipeline xác thực

### 12.1. `block()` trên event loop

Ví dụ sai:

```java
public String currentUserBlocking() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .block(); // Không dùng trong luồng xử lý WebFlux
}
```

Vấn đề:

- `block()` làm thread đợi, trái mục tiêu nonblocking của WebFlux.
- Reactor có thể cảnh báo/throw khi block trên thread nonblocking.
- Việc subscribe độc lập để block có thể khiến Reactor Context không còn giống pipeline request.
- Ở mức tải cao, blocking làm nghẽn event loop và tăng latency toàn hệ thống.

Đúng hơn:

```java
public Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
```

Sau đó kết hợp bằng `flatMap`, `map` hoặc reactive service methods khác.

### 12.2. Tự `subscribe()` trong controller/service

Ví dụ không nên:

```java
public Mono<Void> cancelOrder(String orderId) {
    checkAuthorizationReactive()
        .subscribe(); // Chạy riêng, không chặn mutation bên dưới

    return repository.cancel(orderId);
}
```

Check và mutation không còn một pipeline có thứ tự đảm bảo, có thể tách context và để mutation chạy trước khi quyền được xác nhận.

Đúng hơn:

```java
public Mono<Void> cancelOrder(String orderId) {
    return checkAuthorizationReactive()
        .then(repository.cancel(orderId));
}
```

`checkAuthorizationReactive()` phải phát ra lỗi hoặc giá trị phù hợp khi không được phép, không được trả `Mono.empty()` như tín hiệu “cho phép” ngoài ý muốn nếu policy chưa kiểm tra.

### 12.3. Khi tích hợp thư viện blocking

Một số ứng dụng cần gọi legacy JDBC/SDK blocking. Nếu bắt buộc, tách khỏi event loop bằng scheduler phù hợp và giới hạn concurrency:

```java
Mono<LegacyResult> result = Mono
    .fromCallable(() -> legacyBlockingClient.call())
    .subscribeOn(Schedulers.boundedElastic());
```

Đây là biện pháp thích nghi, không phải làm I/O thật sự nonblocking. Cần quản lý thread pool, timeout và ranh giới authentication context; tốt hơn là dùng R2DBC/WebClient hoặc client reactive khi có thể.

Không dùng scheduler chuyển thread như một lý do bỏ kiểm tra security hoặc truyền token trong ThreadLocal thủ công.

## 13. Ví dụ reactive service: scope đủ vẫn phải kiểm tra chủ đơn

Giả sử request đã xác thực JWT và yêu cầu:

```http
GET /api/orders/order-9001 HTTP/1.1
Authorization: Bearer <valid-jwt>
```

Token có `scope=orders.read` và subject `customer-42`. Service cần kiểm tra order thuộc đúng tenant và owner trước khi trả về.

### 13.1. Domain model và reactive repository

```java
package com.example.orders.domain;

public record Order(
    String id,
    String tenantId,
    String ownerIssuer,
    String ownerSubject,
    String status
) {}
```

```java
package com.example.orders.domain;

import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository {
    Mono<Order> findByIdAndTenantId(String id, String tenantId);
}
```

Repository adapter phải **thực sự ràng buộc tenant trong truy vấn**; tên method interface không tự áp policy nếu implementation bỏ qua điều kiện đó.

### 13.2. Policy cho subject và object

```java
package com.example.orders.security;

import com.example.orders.domain.Order;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public final class ReactiveOrderPolicy {

    public boolean canRead(Jwt jwt, Order order) {
        if (jwt == null || order == null
                || jwt.getIssuer() == null
                || jwt.getSubject() == null) {
            return false;
        }

        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            return false;
        }

        return tenant.equals(order.tenantId())
            && jwt.getIssuer().toString().equals(order.ownerIssuer())
            && jwt.getSubject().equals(order.ownerSubject());
    }
}
```

Đây là **policy minh họa cho user-delegated token**. Với client_credentials, subject có thể đại diện service, không phải customer; cần policy client/job riêng. Claim `tenant_id` chỉ đáng tin khi do issuer được tin cậy phát hành theo hợp đồng.

### 13.3. Service đọc Reactor Context rồi kiểm tra quyền

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import com.example.orders.domain.ReactiveOrderRepository;
import com.example.orders.security.ReactiveOrderPolicy;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public final class ReactiveOrderQueryService {

    private final ReactiveOrderRepository repository;
    private final ReactiveOrderPolicy policy;

    public ReactiveOrderQueryService(
            ReactiveOrderRepository repository,
            ReactiveOrderPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    public Mono<Order> getOrder(String orderId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication())
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "No security context"
                )
            ))
            .flatMap(authentication ->
                readAuthorizedOrder(orderId, authentication)
            );
    }

    private Mono<Order> readAuthorizedOrder(
            String orderId,
            Authentication authentication) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !jwtAuth.isAuthenticated()) {
            return Mono.error(
                new AccessDeniedException("JWT principal required")
            );
        }

        boolean hasScope = jwtAuth.getAuthorities().stream()
            .anyMatch(authority ->
                "SCOPE_orders.read".equals(authority.getAuthority())
            );

        if (!hasScope) {
            return Mono.error(
                new AccessDeniedException("Missing orders.read scope")
            );
        }

        Jwt jwt = jwtAuth.getToken();
        String tenant = jwt.getClaimAsString("tenant_id");

        if (tenant == null || tenant.isBlank()) {
            return Mono.error(
                new AccessDeniedException("Missing trusted tenant")
            );
        }

        return repository.findByIdAndTenantId(orderId, tenant)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                if (!policy.canRead(jwt, order)) {
                    return Mono.error(
                        new AccessDeniedException("Not allowed")
                    );
                }
                return Mono.just(order);
            });
    }
}
```

`OrderNotFoundException` là exception domain tùy ứng dụng; mapping nó sang HTTP 404 do error handler quyết định. Nếu dùng DTO, nên chỉ trả những trường client được phép xem, không trả toàn bộ entity.

Cần chú ý:

1. Authentication lấy từ **Reactor Context**, không phải ThreadLocal.
2. Service kiểm tra **đúng loại Authentication** và authority.
3. Lấy tenant từ JWT đã được xác minh theo hợp đồng.
4. Repository truy vấn trong tenant; policy so lại issuer/subject và tenant.
5. Nếu scope hoặc object policy không đạt, phát `Mono.error(...)` — không tiếp tục trả dữ liệu.
6. Không gọi `block()` hoặc `subscribe()` trong method.
7. Với hệ thống thật, còn cần membership/delegation, trạng thái, data minimization và phân biệt user/service tokens.

### 13.4. WebFlux controller trả Mono

```java
package com.example.orders.api;

import com.example.orders.application.ReactiveOrderQueryService;
import com.example.orders.domain.Order;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public final class ReactiveOrderController {

    private final ReactiveOrderQueryService service;

    public ReactiveOrderController(ReactiveOrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{orderId}")
    public Mono<Order> getOrder(@PathVariable String orderId) {
        return service.getOrder(orderId);
    }
}
```

Controller **trả publisher**, không tự subscribe. WebFlux quản lý subscription; Spring Security context gắn với request pipeline có thể được service sử dụng.

Nếu caller đã có `SCOPE_orders.read` nhưng order nằm ngoài tenant hoặc thuộc người khác, service vẫn từ chối. Điều này tránh **Broken Object Level Authorization (BOLA/IDOR)**.

## 14. Authentication qua tham số controller hoặc @AuthenticationPrincipal

WebFlux cũng hỗ trợ lấy principal từ request khi đã authenticated. Ví dụ:

```java
@GetMapping("/api/me")
public Mono<Map<String, String>> me(
        @AuthenticationPrincipal Jwt jwt) {

    String subject = jwt.getSubject();
    String issuer = jwt.getIssuer().toString();

    return Mono.just(Map.of(
        "subject", subject,
        "issuer", issuer
    ));
}
```

Các imports cần thiết gồm `java.util.Map`, `org.springframework.security.core.annotation.AuthenticationPrincipal`, `org.springframework.security.oauth2.jwt.Jwt` và `reactor.core.publisher.Mono`.

**Giới hạn:** ví dụ giả định endpoint được bảo vệ và JWT hợp lệ có `sub`/`iss`. Nếu ứng dụng dùng opaque token, principal không mặc định là `Jwt`; cần dùng `OAuth2AuthenticatedPrincipal` hoặc `Authentication` phù hợp.

### 14.1. Nên truyền principal hay đọc context trong service?

Cả hai cách có thể phù hợp:

- **Đọc `ReactiveSecurityContextHolder`:** tiện khi service được gọi trong một authenticated reactive chain và cần security context.
- **Truyền một actor context đã kiểm chứng qua tham số:** rõ hơn khi service dùng cả HTTP, message và job, nhưng phải kiểm soát ai được tạo actor đó.
- **Dùng method security:** có thể biểu diễn điều kiện scope/role trên bean method, nhưng vẫn cần object policy khi truy cập dữ liệu.

Đừng lấy `userId` hoặc `tenantId` trực tiếp từ path/body rồi coi nó là danh tính đã xác thực. Parameter là **đầu vào yêu cầu**, không phải bằng chứng quyền.

## 15. Reactive method security và quan hệ với filter chain

Trong WebFlux có thể bật:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
```

Sau đó bảo vệ các phương thức reactive:

```java
@Service
public class ReactiveOrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> getOrder(String orderId) {
        return repository.findAuthorizedOrder(orderId);
    }
}
```

`OrderDto`/`repository.findAuthorizedOrder` thuộc domain của ứng dụng, đoạn code chỉ minh họa vị trí annotation.

Điểm khác biệt:

- Web-layer `authorizeExchange` bảo vệ URL và scope theo HTTP route.
- Reactive method security bảo vệ **Spring bean method invocation** trong reactive pipeline.
- Cả hai cần Authentication trong **Reactor Context**.
- Self-invocation trong cùng bean có thể bỏ qua AOP proxy; cần thiết kế ranh giới method rõ.
- Scope tại method **không thay** kiểm tra owner/tenant/resource và trạng thái nghiệp vụ.
- Không dùng `@PostAuthorize` như lớp bảo vệ duy nhất cho mutation đã gây side effect.

### 15.1. Vì sao method security vẫn cần trong WebFlux?

Một use case có thể được gọi từ:

- REST controller.
- GraphQL resolver.
- Reactive message handler.
- Workflow hoặc service khác.
- Internal application adapter.

Nếu chỉ đặt `hasAuthority` ở route REST, những đường gọi không đi qua route đó không tự chịu cùng điều kiện.

Tuy nhiên, **message consumer hoặc scheduled job không mặc định có HTTP security context**. Chúng cần workload identity hoặc actor context được xác thực theo trust boundary riêng; không tạo `JwtAuthenticationToken` admin giả để “fix missing context”.

### 15.2. Đặc điểm của phương thức reactive

Nếu một method trả `Mono<OrderDto>` và được kiểm tra bởi reactive method security, cần giữ công việc thực thi trong publisher. Nếu method tự gây side effect trước khi trả `Mono`, việc authorization xảy ra ở đâu có thể không bảo vệ side effect ngoài pipeline theo kỳ vọng.

Ví dụ không nên:

```java
public Mono<Void> unsafeCancel(String id) {
    legacyRepository.cancelNow(id); // Side effect đồng bộ ngay
    return Mono.empty();
}
```

Hãy sử dụng repository/domain operation reactive và policy theo pipeline, có transaction/concurrency control phù hợp.

## 16. Exception translation và phản hồi 401/403 trong WebFlux

Lỗi authentication/authorization cần được xử lý qua thành phần **reactive**:

- `ServerAuthenticationEntryPoint`: xử lý request cần xác thực, thường HTTP 401.
- `ServerAccessDeniedHandler`: xử lý thiếu quyền, thường HTTP 403.
- `BearerTokenServerAuthenticationEntryPoint`: Bearer challenge.
- `BearerTokenServerAccessDeniedHandler`: lỗi thiếu quyền cho Bearer.
- `ExceptionTranslationWebFilter`: xử lý một số exception security từ các filter phía sau.
- Authentication failure handler trong `AuthenticationWebFilter`: xử lý lỗi phát sinh ở bước xác thực.

### 16.1. 401 khi không có hoặc token sai

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Khi token sai có thể có:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Thông số header phụ thuộc lỗi cụ thể và cấu hình entry point. Không phải mọi 401 đều bắt buộc có cùng `error`.

### 16.2. 403 khi token đúng nhưng thiếu quyền

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Nếu owner/tenant policy từ chối, API có thể trả 403 hoặc 404 theo hợp đồng nghiệp vụ. Không được trả login HTML hoặc 302 đến OIDC authorization endpoint chỉ vì Bearer token thiếu quyền.

### 16.3. Lỗi ngoài mạng JWT/opaque

Nếu `ReactiveJwtDecoder` phải tải JWKs nhưng endpoint unavailable, hoặc opaque introspection timeout:

- Không coi token tự động hợp lệ.
- Không fallback `permitAll()`.
- Phân biệt lỗi token không hợp lệ với lỗi phụ thuộc/hạ tầng trong metrics và exception mapping.
- Một số cấu hình có thể trả 401 hoặc 5xx tùy exception; nếu sản phẩm yêu cầu 503 cho dependency outage, phải cài đặt và test logic mapping rõ.
- Không log raw access token hoặc credentials introspection.

## 17. Tách nhiều SecurityWebFilterChain cho API và web login

Một ứng dụng WebFlux có thể vừa phục vụ API Bearer vừa có web session login. Khi đó nên tách các chain theo URL và thứ tự.

### 17.1. API chain được ưu tiên

```java
@Bean
@Order(1)
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .formLogin(form -> form.disable())
        .httpBasic(basic -> basic.disable())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
```

### 17.2. Web chain cho login tương tác

```java
@Bean
@Order(2)
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                "/web/**", "/login", "/logout"
            )
        )
        .authorizeExchange(ex -> ex
            .pathMatchers("/web/public/**", "/login").permitAll()
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Đoạn trên là các bean minh họa đặt trong class cấu hình có imports `@Order`/`ServerHttpSecurity` cần thiết. Nếu ứng dụng dùng OAuth2/OIDC login thật, thay chain web bằng `oauth2Login(...)` và bảo đảm các URL `/oauth2/**`, callback phù hợp nằm trong chain tương ứng.

**Lưu ý:** nhiều chain có matcher chồng nhau cần thứ tự `@Order` rõ ràng; WebFlux chọn chain phù hợp, không áp tất cả các chain lên một request. Cần fallback/deny-all cho các URL ngoài phạm vi nếu ứng dụng có endpoint khác.

### 17.3. Không redirect API sang trang login

Với API Bearer:

```text
No token       -> 401 Bearer
Invalid token  -> 401 invalid_token
Missing scope  -> 403
```

Với web login tương tác:

```text
No session -> có thể redirect /login
```

Không dùng `Accept: text/html` từ browser làm tín hiệu để thay cơ chế xác thực của API. Việc URL thuộc API hay web phải được cấu hình theo trust boundary, không chỉ dựa vào content negotiation.

## 18. Filter order trong WebFlux: vì sao addFilterAt quan trọng?

Spring Security WebFlux dùng enum `SecurityWebFiltersOrder` cho các vị trí như:

- `REACTOR_CONTEXT`.
- `AUTHENTICATION`.
- `ANONYMOUS_AUTHENTICATION`.
- `EXCEPTION_TRANSLATION`.
- `AUTHORIZATION`.

Vị trí giữa các filter ảnh hưởng đến việc:

1. Authentication có được thiết lập trước authorization không?
2. SecurityContext có được đưa vào Reactor Context cho handler và service không?
3. Exception được filter nào chuyển thành HTTP response?
4. Một custom filter có vô tình chạy trước khi có authentication hoặc sau khi authorization đã kiểm tra không?

Nếu bạn viết custom `WebFilter` để kiểm tra principal, nó phải được đặt ở vị trí phù hợp và nên sử dụng `ReactiveSecurityContextHolder` chứ không dùng `ThreadLocal`. Nhưng nếu chỉ muốn kiểm tra scope, **hãy sử dụng `authorizeExchange` hoặc method security**, không viết một filter mới cho mỗi endpoint.

### 18.1. Nhân đôi authentication filters

Một lỗi thiết kế:

```text
Chain:
  - AuthenticationWebFilter tùy chỉnh đọc Bearer
  - AuthenticationWebFilter do oauth2ResourceServer().jwt() tạo
  - AuthorizationWebFilter
```

Có thể dẫn đến:

- Token được xác minh hai lần.
- Custom failure handler cạnh tranh với handler chuẩn.
- Bị ghi đè SecurityContext.
- Token JWT và opaque bị thử nhầm manager.
- Lỗi 401/403 khó chẩn đoán.
- Tốn tài nguyên hoặc làm phát sinh calls introspection dư thừa.

Cần **chọn một đường cấu hình xác thực rõ ràng** cho cùng credential/chain, hoặc có thiết kế hỗ trợ nhiều loại credential có phân nhánh minh bạch và kiểm soát thứ tự.

### 18.2. Không dùng filter riêng để thay OAuth claims validation

Một custom `WebFilter` đọc header và phân tích payload JWT để quyết định `scope` trước khi decoder verify là không an toàn. Claim chỉ đáng tin sau bước signature/issuer/audience validation; nếu cần claim validator, hãy cấu hình `ReactiveJwtDecoder`/validators. Nếu cần mapping authority, hãy cấu hình converter.

## 19. Định nghĩa rõ sự khác nhau giữa authentication và authorization

| Giai đoạn | Câu hỏi | Ví dụ thất bại |
|---|---|---|
| Lấy credential | Có `Authorization: Bearer` hợp lệ về cú pháp? | Header sai định dạng |
| JWT/opaque authentication | Token có đáng tin/active không? | Sai signature, hết hạn, `active=false` |
| Principal và authorities | Ai đang gọi, token có scope gì? | Claim thiếu hoặc mapping không đúng hợp đồng |
| Endpoint authorization | Token có quyền gọi thao tác này? | Thiếu `SCOPE_orders.read` |
| Object authorization | Subject có quyền trên **order 42**? | Order của tenant khác |
| Business policy | Trạng thái hiện tại cho phép hành động? | Hủy đơn đã giao hàng |

`AuthenticationWebFilter` thuộc những giai đoạn đầu. `authorizeExchange` và service policy thuộc những giai đoạn sau.

### 19.1. Scope chỉ là một phần của quyền

Nếu token có `orders.read`, WebFlux authorization có thể cho endpoint GET đi qua, nhưng service vẫn cần kiểm tra `(issuer, sub)`, tenant, quyền sở hữu và trạng thái. Không dùng `hasAuthority("SCOPE_orders.read")` làm bằng chứng được truy cập mọi hàng trong database.

### 19.2. Client credentials không đồng nghĩa user

Trong token máy-máy:

```json
{
  "sub": "nightly-worker",
  "client_id": "nightly-worker",
  "scope": "orders.export",
  "aud": ["orders-api"]
}
```

`sub` có thể là service identity, không phải customer. Reactive SecurityContext vẫn chứa Authentication nhưng policy nghiệp vụ cần phân biệt **user-delegated** và **service/client**. Không dùng `authentication.getName()` một cách mù quáng làm user ID để lấy dữ liệu cá nhân.

## 20. Test AuthenticationWebFilter và SecurityWebFilterChain với WebTestClient

`WebTestClient` là công cụ phổ biến để kiểm thử WebFlux. Spring Security Test cung cấp các configurers hỗ trợ đặt mock Authentication trong request test.

Dependencies ví dụ:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

### 20.1. Test bằng mockJwt()

Với `WebTestClient` gắn vào application context:

```java
package com.example.orders.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void validMockAuthenticationWithReadScopeCanReachHandler() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt
                    .subject("customer-42")
                    .claim("tenant_id", "tenant-a"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                ))
            .get()
            .uri("/api/orders/order-42")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void missingScopeIsForbidden() {
        client.mutateWith(mockJwt()
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_unrelated")
                ))
            .get()
            .uri("/api/orders/order-42")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void missingAuthenticationGetsUnauthorized() {
        client.get()
            .uri("/api/orders/order-42")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Điều kiện:** test cần một handler và repository fixture cho `order-42` mà subject `customer-42` được phép đọc; nếu không, first test có thể trả 404/403 vì **object policy** — đó không phải lỗi của mock authentication. Đây là test minh họa API web chain, không phải project chạy độc lập.

**Cảnh báo quan trọng:** `mockJwt()` tạo Authentication thử nghiệm, **không gửi JWT thật qua `ServerBearerTokenAuthenticationConverter` và không chứng minh `ReactiveJwtDecoder` đã xác minh chữ ký**. Dùng nó để kiểm tra authorization/handler, không coi đây là end-to-end token-validation test.

### 20.2. Test bằng Bearer header và ReactiveJwtDecoder thật/test double

Một integration test xác thực luồng đầy đủ cần:

1. Gửi HTTP header `Authorization: Bearer <TEST_JWT>`.
2. Để `AuthenticationWebFilter` chạy thực, converter đọc header.
3. Dùng `ReactiveJwtDecoder` hoặc fake issuer/JWKS server **được kiểm soát**.
4. Token đúng chữ ký/issuer/audience đi qua authentication.
5. Token sai signature/expired/wrong issuer/wrong audience bị 401.
6. Token hợp lệ nhưng thiếu scope bị 403.
7. Không có token bị 401 trên URL bảo vệ.
8. Xác nhận `WWW-Authenticate` dùng Bearer và không redirect login.
9. Kiểm tra service object policy tiếp tục từ chối cross-tenant/cross-owner.

Nếu dùng decoder test double luôn trả JWT hợp lệ, test **không chứng minh signature validation** thật; để test chữ ký cần bộ khóa/test issuer phù hợp.

### 20.3. Test reactive security context

Có thể tạo test Authentication riêng để kiểm tra context propagation:

```java
Jwt testJwt = Jwt.withTokenValue("test-only")
    .header("alg", "RS256")
    .claim("sub", "customer-42")
    .claim("iss", "https://login.example.com")
    .claim("scope", "orders.read")
    .build();

JwtAuthenticationToken testAuthentication =
    new JwtAuthenticationToken(
        testJwt,
        List.of(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    );

Mono<String> identity = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            testAuthentication
        )
    );

StepVerifier.create(identity)
    .expectNext("customer-42")
    .verifyComplete();
```

Đoạn fragment cần imports `Jwt`, `JwtAuthenticationToken`, `SimpleGrantedAuthority`, `List`, `Mono` và `StepVerifier` trong test class.

Ở đây test **chủ động tạo Authentication** nên có thể kiểm tra Reactor Context, nhưng không có nghĩa production được phép tạo principal từ dữ liệu chưa xác minh.

### 20.4. Đối với opaque token

Spring Security Test có hỗ trợ mock opaque principal cho WebFlux. Test logic authorization có thể dùng mock token/principal theo phiên bản test library, nhưng để test **introspection HTTP**, phải gửi Bearer header thật và dùng fake introspection endpoint phản hồi `active=true/false`, lỗi Basic credentials, timeout hoặc malformed responses.

### 20.5. Các ca test cần có

| Tình huống | Mục tiêu |
|---|---|
| GET endpoint bảo vệ không gửi token | 401 Bearer |
| JWT sai signature | Decoder từ chối |
| JWT sai issuer/audience | Decoder/validator từ chối |
| Token hết hạn | Xác thực thất bại |
| Token hợp lệ, thiếu scope | Authorization trả 403 |
| Token hợp lệ, đủ scope | Handler nhận Authentication |
| Token đủ scope, khác tenant/owner | Service từ chối |
| Converter không thấy Bearer header | Không tạo authenticated principal |
| Header malformed hoặc nhiều bearer credentials | Lỗi đúng RFC/policy |
| Trong pipeline dùng `ReactiveSecurityContextHolder` | Lấy được principal |
| Detached `subscribe()`/callback ngoài pipeline | Không được mặc định có context |
| Opaque `active=false` | Không cấp quyền |
| AS/JWKS/introspection outage | Fail closed, xử lý lỗi hạ tầng |
| Nhiều security chains | API không bị web login chain chiếm |
| Custom filter | Không trùng authentication hoặc bypass |
| Đường method security trên reactive service | Quyền được kiểm tra cả khi gọi ngoài controller |

## 21. Chẩn đoán sự cố trong thực tế

### 21.1. API nhận token nhưng authentication luôn null

Các khả năng:

- Request không đi qua `SecurityWebFilterChain` mong đợi.
- `securityMatcher` hoặc route rewrite sai.
- Converter không thấy Bearer header.
- Decoder/introspector từ chối token.
- Code đọc `SecurityContextHolder` của Servlet thay vì `ReactiveSecurityContextHolder`.
- Code chạy trong detached subscription/thread không có Reactor Context.
- Controller là một component bên ngoài pipeline được WebFlux quản lý.

**Cách tìm:** kiểm tra filter chain matcher, inbound header ở mức an toàn, lỗi decoder, và nơi Reactor Context bị tách. Không log raw token.

### 21.2. Bean AuthenticationWebFilter có nhưng không chạy

Có thể do:

- Không được gắn vào `SecurityWebFilterChain`.
- Chain không khớp request.
- `requiresAuthenticationMatcher` không khớp.
- Filter ở thứ tự không phù hợp.
- Dùng nhầm Servlet `Filter` API trong WebFlux.
- Application chạy MVC vì có `spring-boot-starter-web` và cấu hình web application type chưa như dự kiến.

Đặt filter làm Spring bean **không tự bảo đảm** nó được chèn đúng vào mọi chain của WebFlux; cần gắn bằng DSL/`addFilterAt` với một chain xác định.

### 21.3. Bị 403 dù token có scope

Kiểm tra:

- `scope` là chuỗi hay `scp` là danh sách?
- Authority thực tế có tên `SCOPE_orders.read` hay prefix khác?
- Custom JWT converter đã vô tình thay converter scope mặc định?
- Matcher endpoint yêu cầu authority nào?
- Lỗi đến từ web filter, method security hay object policy?
- Token có audience đúng và được decoder chấp nhận không?

Không tắt signature/audience validation hoặc `permitAll()` để “sửa” 403 thiếu quyền.

### 21.4. Một số requests chạy được, một số mất principal

Dấu hiệu này có thể đến từ:

- Code gọi `subscribe()` thủ công.
- Chuyển từ reactive code sang callback/executor không nối cùng pipeline.
- Library blocking dùng ThreadLocal nhưng không truyền context phù hợp.
- Async scheduling hoặc message consumer chạy ngoài request.
- Test dùng mocked authentication không phản ánh đường chạy production.

Thiết kế theo **reactive composition** thay vì tạo pipeline rời.

### 21.5. Dùng `block()` khiến hệ thống treo khi tải cao

WebFlux có ít event-loop threads, nên blocking có thể làm mọi request chậm. Đừng đặt blocking lookup, JDBC hoặc HTTP client sync trong converter/manager reactive mà không kiểm soát scheduling. Ưu tiên I/O reactive và đo event-loop latency.

### 21.6. API trả HTML login thay vì 401 Bearer

Nguyên nhân phổ biến:

- API request rơi vào web login chain do thứ tự matcher.
- Custom failure handler redirect `/login`.
- OAuth2 Login được cấu hình chung mà không tách đường API.
- Gateway/ingress rewrite 401 thành 302/HTML.
- Client tự follow redirect, che mất response đầu.

Cấu hình Bearer entry point và kiểm tra từng hop. Resource Server không nên biến lỗi token thành trang login HTML ngoài dự kiến.

## 22. Bảo mật và khả năng vận hành

### 22.1. Không log bearer credential

Một bearer access token là credential: ai có token có thể cố dùng nó trong thời gian token còn hiệu lực. Tránh đưa raw token vào:

- HTTP access logs.
- Trace span attributes hoặc baggage.
- Exception details trả frontend.
- Metrics labels.
- Query parameters/URL.
- Debugger dumps công khai.

Nên log request ID, issuer ID đã được xác minh, outcome `authenticated/denied`, mã lỗi nội bộ đã phân loại và latency; tối thiểu hóa dữ liệu cá nhân.

### 22.2. Token active không thay quyền nghiệp vụ

Dù `AuthenticationWebFilter` chạy hoàn toàn đúng, một token `SCOPE_orders.read` không đủ để đọc mọi đơn. Service cần xác minh owner, tenant, delegated rights và trạng thái của từng resource, đặc biệt với GraphQL, batch jobs và nested resources.

### 22.3. Rate limiting trước khi xác thực

Một kẻ tấn công có thể gửi nhiều Bearer token vô nghĩa để kích hoạt decoder/network fetch hoặc opaque introspection. Cần:

- Rate limit tại edge/gateway.
- Giới hạn độ dài header/token.
- Pool/timeout/concurrency cho outbound introspection.
- JWKS cache và key rotation policies phù hợp.
- Chống retry storm và fail closed khi dependency không sẵn sàng.
- Không cho client chọn JWKS/introspection URL bằng dữ liệu chưa xác minh.

### 22.4. Observability

Đo những thông tin như:

- Số request authentication thành công/thất bại.
- Thời gian JWT decode và introspection.
- Lỗi signature/issuer/audience/exp ở mức mã lỗi không nhạy cảm.
- Tỷ lệ 401 vs 403 theo endpoint group.
- Reactor Netty event-loop delay hoặc blocking warnings.
- Opaque introspection HTTP timeout và pool saturation.
- Số lần custom filter gọi authentication manager.
- Tỷ lệ lỗi ngoài phạm vi authority hoặc object policy.

Không dùng raw token hoặc `sub` làm metric tag có cardinality cao.

### 22.5. Bảo đảm ranh giới tải và fail closed

Trong WebFlux, nonblocking giúp xử lý nhiều request đồng thời, nhưng **không bảo đảm downstream Authorization Server/JWKs/DB có đủ capacity**. Nếu opaque token phải introspect cho mỗi request, cần timeout, connection pooling, backpressure/admission control và cache có cân nhắc revocation.

Khi thiếu bằng chứng xác thực hợp lệ, **không mở quyền** để “giữ API sống”. Phân biệt lỗi dependency và lỗi token để vận hành đúng nhưng vẫn từ chối hành động được bảo vệ.

## 23. Thiết kế chuẩn nên ưu tiên

Một hướng thực tế khi xây WebFlux Resource Server:

1. Bắt đầu bằng **`@EnableWebFluxSecurity` + `SecurityWebFilterChain` + `ServerHttpSecurity.oauth2ResourceServer`**.
2. Chọn một đường xác thực: **JWT qua `ReactiveJwtDecoder`** hoặc **opaque qua `ReactiveOpaqueTokenIntrospector`** theo hợp đồng.
3. Đặt issuer, audience, token profile và claim validators cần thiết; không chỉ decode payload.
4. Dùng `ServerBearerTokenAuthenticationConverter` chuẩn cho Bearer header, tránh chấp nhận token tùy ý qua URL.
5. Dùng `JwtAuthenticationConverter`/reactive adapter hoặc converter chính thức để ánh xạ authority khi cần, không viết filter chỉ để đổi prefix scope.
6. Dùng `authorizeExchange` cho quyền chức năng theo HTTP route.
7. Dùng reactive method security và domain policy cho quyền service, tenant, owner và trạng thái tài nguyên.
8. Dùng `ReactiveSecurityContextHolder` hoặc actor context đã xác thực, **không giả định ThreadLocal**.
9. Giữ mọi bước trong một Reactor pipeline, không `block()` hoặc `subscribe()` tùy tiện.
10. Tách API chain và web login chain nếu ứng dụng có hai mô hình authentication.
11. Dùng Bearer 401/403 responses, không redirect HTML login cho API.
12. Kiểm thử cả filter integration qua Bearer header, mocked authorization, object policy và context propagation.
13. Chỉ tự tạo `AuthenticationWebFilter` khi DSL chuẩn không phù hợp và đã thiết kế rõ filter order, failure handler, security context và không trùng lọc.

## 24. Tóm lược trách nhiệm của các thành phần

| Thành phần | Input | Output | Có trách nhiệm gì? |
|---|---|---|---|
| `SecurityWebFilterChain` | `ServerWebExchange` | Chuỗi WebFilter phù hợp | Chọn các filter để bảo vệ request |
| `AuthenticationWebFilter` | Exchange, converter, manager | Xác thực thành công/thất bại và context | Điều phối authentication trong reactive pipeline |
| `ServerBearerTokenAuthenticationConverter` | `Authorization: Bearer ...` | `Mono<BearerTokenAuthenticationToken>` | Trích credential; chưa xác minh JWT |
| `JwtReactiveAuthenticationManager` | Bearer auth request | `Mono<Authentication>` | Gọi JWT decoder và chuyển Jwt thành Authentication |
| `ReactiveJwtDecoder` | Raw JWT string | `Mono<Jwt>` | Xác minh token bằng keys và validators |
| `ReactiveOpaqueTokenIntrospector` | Raw opaque token | `Mono<OAuth2AuthenticatedPrincipal>` | Xác thực token qua introspection |
| `ReactiveSecurityContextHolder` | Reactor Context | `Mono<SecurityContext>` | Truy cập security identity trong pipeline |
| Reactive authorization web filter | Authentication, endpoint rules | Allow/deny | Kiểm tra `authorizeExchange` |
| Reactive method security | Authentication, method invocation | Allow/deny | Bảo vệ lời gọi service |
| Domain policy | Actor, resource, action | Allow/deny | Quyền trên đối tượng/tenant và nghiệp vụ |
| `ServerAuthenticationEntryPoint` | Authentication error | HTTP error | Ví dụ 401 Bearer challenge |
| `ServerAccessDeniedHandler` | Access denied | HTTP error | Ví dụ 403 Forbidden |

## 25. Nguồn tham khảo

- [Spring Security Reference — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `@EnableWebFluxSecurity`, `SecurityWebFilterChain` và `ServerHttpSecurity`.
- [Spring Security Reference — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): Bearer JWT, `ReactiveJwtDecoder`, validators và JWT authorities.
- [Spring Security Reference — Reactive OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector` và opaque authentication.
- [Spring Security API — AuthenticationWebFilter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): converter, authentication manager resolver, success/failure, context repository.
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): SecurityContext trong Reactor Context.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` và method authorization.
- [Project Reactor Reference — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): context propagation trong reactive pipelines.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token, 401 và 403.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): các yêu cầu của JWT access token theo hồ sơ OAuth.

**Ghi nhớ:** `AuthenticationWebFilter` là **đầu mối xác thực trong chuỗi WebFlux**, nhưng nó không “tự tin” một token chỉ vì tìm được chuỗi Bearer. Converter lấy credential, reactive manager và decoder/introspector **xác minh** credential, còn Spring Security đặt kết quả vào **Reactor Context** để authorization tiếp tục. Ở các tầng sau, `authorizeExchange`, reactive method security và domain policy quyết định request có được thao tác lên tài nguyên cụ thể hay không. Thiết kế đúng các ranh giới này giúp WebFlux Resource Server vừa **nonblocking**, vừa **đúng mô hình OAuth2**, vừa **không bỏ sót bảo mật nghiệp vụ**.
