# Servlet, WebFlux và các thành phần tương ứng trong Spring Security

Trong một ứng dụng **OAuth 2.0 Resource Server**, Spring Security nhận access token do Authorization Server phát hành, xác thực token rồi quyết định request có được truy cập tài nguyên hay không. Spring Security có hai mô hình bảo vệ ứng dụng web: **Servlet** (thường dùng với Spring MVC) và **Reactive** (thường dùng với Spring WebFlux). Hai mô hình thực hiện cùng mục tiêu nhưng có kiểu request, chuỗi filter, API cấu hình và cách lưu ngữ cảnh bảo mật khác nhau.

Bài học đối chiếu các thành phần liên quan đến JWT và opaque token, luồng xử lý, cách cấu hình Java/Spring Boot và những điểm cần lưu ý khi chọn kiến trúc. Các URI và token trong ví dụ đều là dữ liệu minh họa.

## 1. Resource Server trong OAuth 2.0 và OIDC

Một hệ thống OAuth 2.0 thường gồm:

- **Authorization Server / OpenID Provider (OP)**: xác thực người dùng hoặc client, phát hành token.
- **OAuth 2.0 Client**: lấy access token theo luồng được cấp phép và gửi token khi gọi API.
- **Resource Server**: cung cấp API và kiểm tra access token cho các tài nguyên cần bảo vệ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server / OIDC Provider
    participant RS as Resource Server
    C->>AS: Xin access token
    AS-->>C: Access token
    C->>RS: GET /api/orders + Authorization: Bearer ...
    RS->>RS: Xác thực token và kiểm tra quyền
    RS-->>C: Dữ liệu hoặc HTTP 401/403
~~~

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

**OIDC là tầng định danh dựa trên OAuth 2.0.** OpenID Provider có thể cung cấp metadata và JWK Set cho Resource Server kiểm tra JWT. Tuy nhiên, API phải nhận **access token hợp lệ dành cho API**. **ID token** phục vụ việc định danh người dùng cho OIDC client, không phải token thay thế access token để truy cập API. Cấu hình `oauth2ResourceServer()` và `oauth2Login()` phục vụ các vai trò khác nhau.

## 2. Hai mô hình xử lý HTTP

| Tiêu chí | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Hạ tầng HTTP | Jakarta Servlet, thường có Tomcat/Jetty/Undertow dạng Servlet | Spring WebFlux + Reactor, thường dùng Reactor Netty |
| Request/response | `HttpServletRequest`, `HttpServletResponse` | `ServerWebExchange`, `ServerHttpRequest`, `ServerHttpResponse` |
| Cách lập trình phổ biến | Luồng gọi tuần tự, cho phép blocking | Publisher `Mono<T>` / `Flux<T>`, hỗ trợ non-blocking |
| Builder cấu hình bảo mật | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Lớp chặn HTTP | Servlet `Filter` | Spring WebFlux `WebFilter` |
| Truy cập security context | `SecurityContextHolder`, mặc định dựa trên `ThreadLocal` | `ReactiveSecurityContextHolder`, Reactor `Context` |
| Kiểm tra JWT | `JwtDecoder` | `ReactiveJwtDecoder` |
| Introspection opaque token | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

**Blocking/non-blocking là đặc điểm xử lý và sử dụng tài nguyên, không quyết định mức an toàn OAuth 2.0.** Cả hai đều có thể kiểm tra chữ ký JWT, thời hạn, issuer, scope và phân quyền. Với WebFlux, lợi ích non-blocking chỉ phát huy nếu chuỗi controller → service → repository/HTTP client không chặn event loop bởi lời gọi blocking.

Không nên phân biệt HTTP stack dựa trên việc thấy `WebClient` hay `Mono` ở một file bất kỳ. Ứng dụng Spring MVC vẫn dùng được `WebClient`. Nếu khai báo cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn ứng dụng Servlet/MVC nếu không có cấu hình thay đổi loại ứng dụng.

## 3. Bản đồ các thành phần Spring Security

| Trách nhiệm | Servlet | WebFlux / Reactive |
|---|---|---|
| Khai báo rule HTTP | `HttpSecurity` | `ServerHttpSecurity` |
| Chain được cấu hình | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Điều phối các chain | `FilterChainProxy`, được nối với Servlet qua `DelegatingFilterProxy` | `WebFilterChainProxy` |
| Chặn và xác thực Bearer token | `BearerTokenAuthenticationFilter` | `AuthenticationWebFilter` cấu hình cho Resource Server |
| Trích xuất Bearer token | `BearerTokenResolver` / `BearerTokenAuthenticationConverter` tùy phiên bản và mức tùy biến | `ServerBearerTokenAuthenticationConverter` (`ServerAuthenticationConverter`) |
| Token biểu diễn credential chưa xác thực | `BearerTokenAuthenticationToken` | `BearerTokenAuthenticationToken` |
| Điều phối xác thực | `AuthenticationManager` (thường `ProviderManager`) | `ReactiveAuthenticationManager` |
| Xác thực JWT | `JwtAuthenticationProvider` | `JwtReactiveAuthenticationManager` |
| Kiểm tra và giải mã JWT | `JwtDecoder`, ví dụ `NimbusJwtDecoder` | `ReactiveJwtDecoder`, ví dụ `NimbusReactiveJwtDecoder` |
| Chuyển JWT thành Authentication | `JwtAuthenticationConverter` | Reactive converter; có thể dùng `ReactiveJwtAuthenticationConverterAdapter` |
| Kết quả xác thực JWT | `JwtAuthenticationToken` | `JwtAuthenticationToken` |
| Xác thực opaque token | `OpaqueTokenAuthenticationProvider` | `OpaqueTokenReactiveAuthenticationManager` |
| Kiểm tra opaque token | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Kết quả xác thực opaque token thường gặp | `BearerTokenAuthentication` | `BearerTokenAuthentication` |
| Context người dùng hiện tại | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Kiểm tra quyền theo URL | `authorizeHttpRequests()` và `requestMatchers()` | `authorizeExchange()` và `pathMatchers()` |
| Bảo vệ method | `@EnableMethodSecurity` và `@PreAuthorize` | `@EnableReactiveMethodSecurity` và `@PreAuthorize` |
| Chưa xác thực | `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| Không đủ quyền | `AccessDeniedHandler` | `ServerAccessDeniedHandler` |
| Test HTTP API | `MockMvc` | `WebTestClient` |

Các loại dữ liệu như `Jwt`, `Authentication`, `GrantedAuthority` có thể dùng chung; **điểm khác chính là nơi tích hợp vào HTTP runtime và kiểu API sync/reactive**. Không thể dùng `SecurityFilterChain` như bean cấu hình an ninh của một ứng dụng WebFlux chỉ bằng cách đổi import.

## 4. Luồng nhận JWT trên Servlet

~~~mermaid
flowchart TD
    A["Request + Bearer JWT"] --> B["DelegatingFilterProxy / FilterChainProxy"]
    B --> C["SecurityFilterChain"]
    C --> D["BearerTokenAuthenticationFilter"]
    D --> E["BearerTokenAuthenticationToken"]
    E --> F["AuthenticationManager / ProviderManager"]
    F --> G["JwtAuthenticationProvider"]
    G --> H["JwtDecoder: chữ ký, exp, nbf, iss"]
    H --> I["JwtAuthenticationConverter"]
    I --> J["JwtAuthenticationToken + authorities"]
    J --> K["SecurityContextHolder"]
    K --> L["Authorization → Controller"]
~~~

1. Servlet container chuyển request qua Spring Security; `FilterChainProxy` chọn `SecurityFilterChain` khớp request.
2. `BearerTokenAuthenticationFilter` lấy token từ header `Authorization: Bearer ...` và tạo `BearerTokenAuthenticationToken`.
3. `AuthenticationManager` giao việc cho `JwtAuthenticationProvider`; provider sử dụng `JwtDecoder` để kiểm tra chữ ký và validator liên quan.
4. `JwtAuthenticationConverter` ánh xạ claims/scope sang `JwtAuthenticationToken` với principal và authorities.
5. Xác thực thành công được lưu trong `SecurityContext`; Spring kiểm tra rule truy cập rồi mới tới controller nếu được phép.

Với cấu hình `issuer-uri` mặc định, Resource Server kiểm tra issuer `iss`, thời điểm `exp` / `nbf` và chữ ký theo khóa tin cậy. **Audience `aud` cần có validator riêng khi API phải giới hạn token được cấp cho chính nó**. Chữ ký hợp lệ và đúng issuer chưa bảo đảm access token được phát hành cho đúng API.

## 5. Luồng nhận JWT trên WebFlux

~~~mermaid
flowchart TD
    A["Request + Bearer JWT"] --> B["WebFilterChainProxy"]
    B --> C["SecurityWebFilterChain"]
    C --> D["AuthenticationWebFilter"]
    D --> E["ServerBearerTokenAuthenticationConverter"]
    E --> F["BearerTokenAuthenticationToken"]
    F --> G["ReactiveAuthenticationManager"]
    G --> H["JwtReactiveAuthenticationManager"]
    H --> I["ReactiveJwtDecoder: Mono<Jwt>"]
    I --> J["JwtAuthenticationToken + authorities"]
    J --> K["Reactive SecurityContext (Reactor Context)"]
    K --> L["Authorization → WebFlux handler"]
~~~

Luồng nghiệp vụ vẫn là **lấy token → xác thực → tạo principal/authorities → phân quyền**, nhưng các hợp đồng trong pipeline nhận/trả publisher, chẳng hạn `Mono<Authentication>` và `Mono<Jwt>`. Context bảo mật được lưu trong Reactor `Context`, theo subscription thay vì giả định gắn cố định với một thread như code Servlet thông thường.

Trong reactive service, dùng `ReactiveSecurityContextHolder.getContext()`, hoặc để framework inject principal cho handler phù hợp. Tránh đọc `SecurityContextHolder.getContext()` rồi tin rằng nó sẽ đại diện đúng cho request bất kể thay đổi thread; đồng thời tránh ép kết quả reactive bằng `block()` trong request pipeline.

## 6. Cấu hình JWT cho Servlet / Spring MVC

Dependency điển hình:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

Giá trị `issuer-uri` phải trùng với claim `iss` của JWT; đường dẫn trên chỉ là ví dụ.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ServletResourceServerSecurity {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));

        return http.build();
    }
}
~~~

Ví dụ controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletOrderController {
    @GetMapping("/api/orders/me")
    String myOrders(@AuthenticationPrincipal Jwt jwt) {
        return "Orders for subject: " + jwt.getSubject();
    }
}
~~~

Đoạn này minh họa cách lấy `sub` sau xác thực. Với tài nguyên riêng của từng người dùng, service vẫn phải kiểm tra quyền sở hữu đơn hàng; chỉ có scope `orders.read` chưa mặc nhiên được đọc đơn hàng của người khác.

## 7. Cấu hình tương ứng cho WebFlux

Dependency:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Property `spring.security.oauth2.resourceserver.jwt.issuer-uri` vẫn giữ nguyên cấu trúc như Servlet. Spring Boot cung cấp `ReactiveJwtDecoder` ở WebFlux, trong khi ở Servlet là `JwtDecoder`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveResourceServerSecurity {
    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ReactiveOrderController {
    @GetMapping("/api/orders/me")
    Mono<String> myOrders(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just("Orders for subject: " + jwt.getSubject());
    }
}
~~~

Hai cấu hình bảo vệ endpoint theo cùng scope nhưng dùng các thành phần HTTP bảo mật khác nhau. Để khai thác WebFlux, phần nghiệp vụ và I/O phía sau nên hỗ trợ reactive; controller trả về `Mono` mà bên trong gọi JDBC/HTTP blocking không tự chuyển đường xử lý thành non-blocking.

Trong reactive service, có thể đọc authentication theo Reactor Context:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
}
~~~

Tương ứng trong code Servlet ở vị trí đã thiết lập security context:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
String principalName = authentication.getName();
~~~

Trong đoạn Servlet, import `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`. Trong WebFlux, phương thức trả về `Mono<String>` để kết hợp vào pipeline; không tự chạy trước khi được subscribe.

## 8. Nếu access token là opaque token thì thành phần nào thay đổi?

**JWT** thường tự chứa claim và chữ ký, vì vậy Resource Server có thể kiểm tra chữ ký cục bộ sau khi nhận JWK/public key đáng tin cậy. **Opaque token** là chuỗi mà Resource Server không cần tự giải mã. Cách phổ biến để xác thực nó là gọi **introspection endpoint** của Authorization Server, kiểm tra `active` và sử dụng thông tin principal/scope được trả về.

| Công đoạn | Servlet opaque token | WebFlux opaque token |
|---|---|---|
| Cấu hình | `oauth2ResourceServer(o -> o.opaqueToken(...))` trên `HttpSecurity` | Cùng DSL `opaqueToken(...)` trên `ServerHttpSecurity` |
| Cơ chế xác thực | `OpaqueTokenAuthenticationProvider` | `OpaqueTokenReactiveAuthenticationManager` |
| Lời gọi introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Thuộc tính principal | `OAuth2AuthenticatedPrincipal` | `OAuth2AuthenticatedPrincipal` |
| Authentication thường gặp | `BearerTokenAuthentication` | `BearerTokenAuthentication` |

Ví dụ `application.yml` có cấu trúc giống nhau ở cả hai stack; Spring Boot sẽ tự cấu hình introspector thích hợp với kiểu ứng dụng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: resource-server-api
          client-secret: ${RESOURCE_SERVER_INTROSPECTION_SECRET}
~~~

`${RESOURCE_SERVER_INTROSPECTION_SECRET}` minh họa biến môi trường/secret; không lưu mật khẩu introspection thực trong repository.

Nếu giữ các rule ở ví dụ trước, chỉ cần thay đoạn kích hoạt JWT bằng:

~~~java
// Trong cấu hình HttpSecurity dành cho Servlet:
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))

// Trong cấu hình ServerHttpSecurity dành cho WebFlux:
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))
~~~

Không đặt hai dòng chain rời rạc này thành class Java độc lập; đây là **các đoạn DSL thay thế** dòng `.jwt(withDefaults())` ở hai ví dụ trước.

Với introspection, chi phí mạng và tính sẵn sàng của Authorization Server có thể ảnh hưởng mỗi request. Nếu cần kiểm tra trạng thái thu hồi token gần thời gian thực, introspection là một lựa chọn; caching dài hạn có thể làm giảm hiệu lực của việc thu hồi. WebFlux cần triển khai giao diện reactive để tránh chặn event loop khi gọi introspection.

## 9. Authentication, authorization và scope

Hai công đoạn cần phân biệt:

1. **Authentication (xác thực)**: token có hợp lệ không, principal là ai, token được phát hành và sử dụng đúng quy tắc chưa?
2. **Authorization (phân quyền)**: principal hợp lệ có authority/scope cần thiết và có được phép truy cập *tài nguyên cụ thể* không?

Ví dụ JWT chứa claim minh họa (đã bỏ thời gian và chữ ký cho gọn):

~~~json
{
  "sub": "user-123",
  "iss": "https://idp.example.test/realms/demo",
  "aud": ["orders-api"],
  "scope": "orders.read profile"
}
~~~

Theo mapping mặc định phổ biến của Resource Server, `scope` hoặc `scp` được chuyển thành các `GrantedAuthority` có tiền tố `SCOPE_`:

| Claim / điều kiện | Authority / yêu cầu |
|---|---|
| `scope: "orders.read profile"` | `SCOPE_orders.read` và `SCOPE_profile` |
| Rule `hasAuthority("SCOPE_orders.read")` | Chấp nhận principal có scope `orders.read` |
| `hasRole("ADMIN")` | Thường tìm `ROLE_ADMIN`, không đồng nhất với scope `admin` |
| Custom claim `roles`, `realm_access.roles` | Cần converter hoặc chính sách ánh xạ do ứng dụng thiết lập |

Trong Servlet, `JwtAuthenticationConverter` kết hợp `JwtGrantedAuthoritiesConverter` là điểm tùy chỉnh thường gặp khi issuer dùng claim scope khác hoặc định dạng quyền riêng. Trong WebFlux, converter đưa vào DSL phải có kiểu phù hợp reactive; có thể bọc logic đồng bộ thuần ánh xạ claim bằng `ReactiveJwtAuthenticationConverterAdapter`. Nếu phải truy vấn cơ sở dữ liệu/dịch vụ qua mạng để phân quyền, cần thiết kế thành phần reactive riêng và tránh gọi blocking trên event loop.

Có thể kiểm soát cả HTTP endpoint và service method:

~~~java
// Ví dụ trên Servlet service; cần bật @EnableMethodSecurity ở cấu hình.
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderView findOrder(String orderId) {
    return loadOrder(orderId);
}
~~~

WebFlux sử dụng `@EnableReactiveMethodSecurity` và các method phù hợp với reactive return type. Kiểm tra scope chỉ xác định loại hành động được phép; service vẫn phải kiểm tra quyền sở hữu, tenant, trạng thái dữ liệu hoặc điều kiện nghiệp vụ khác khi cần.

### Vì sao cần kiểm tra `aud`?

Một Authorization Server có thể phát hành token cho nhiều API. Token có cùng issuer và chữ ký hợp lệ nhưng claim `aud` dành cho một API khác không nên được chấp nhận ở API hiện tại. Hãy cấu hình `OAuth2TokenValidator<Jwt>` hoặc cơ chế validation phù hợp với phiên bản Spring Security để yêu cầu audience dự kiến, bên cạnh validator mặc định cho thời hạn và issuer. Đừng chỉ kiểm tra `aud` trong controller sau khi token đã vượt qua security chain.

## 10. Khi nào trả 401, khi nào trả 403?

| Tình huống | HTTP thường gặp | Ý nghĩa |
|---|---|---|
| API yêu cầu xác thực nhưng không gửi Bearer token | `401 Unauthorized` | Chưa có thông tin xác thực hợp lệ |
| Token không hợp lệ, hết hạn, chữ ký sai, issuer sai, hoặc introspection báo inactive | `401 Unauthorized` | Xác thực thất bại |
| Token hợp lệ nhưng thiếu `SCOPE_orders.read` | `403 Forbidden` | Đã xác thực nhưng thiếu quyền |
| Token hợp lệ, đủ quyền và dữ liệu được phép truy cập | Do controller quyết định (thường 2xx) | Bước bảo mật HTTP đã cho request đi tiếp |

Header `WWW-Authenticate: Bearer ...` có thể được gửi theo tiêu chuẩn xử lý Bearer token, kèm thông tin lỗi thích hợp. Servlet sử dụng `AuthenticationEntryPoint` và `AccessDeniedHandler`; Resource Server thường cung cấp `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler`. WebFlux có các điểm mở rộng tương ứng `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler`.

Các lỗi xác thực thường được giải quyết **trong security chain trước controller**. Không nên đưa logic đọc chữ ký JWT vào từng controller hay biến mọi lỗi này thành HTTP 500. Tránh log toàn bộ Bearer token, vì ai có token còn hiệu lực có thể sử dụng nó như credential.

## 11. Cách chọn đúng họ class khi triển khai

| Câu hỏi kiến trúc | Khi dùng Servlet | Khi dùng WebFlux |
|---|---|---|
| HTTP security bean nào? | `SecurityFilterChain(HttpSecurity)` | `SecurityWebFilterChain(ServerHttpSecurity)` |
| Decoder JWT tùy biến? | Bean `JwtDecoder` | Bean `ReactiveJwtDecoder` |
| Introspection tùy biến? | Bean `OpaqueTokenIntrospector` | Bean `ReactiveOpaqueTokenIntrospector` |
| Lấy principal trong pipeline? | Từ injection hoặc `SecurityContextHolder` | Từ injection hoặc `ReactiveSecurityContextHolder` |
| Rule cho đường dẫn? | `requestMatchers(...)` | `pathMatchers(...)` |
| Rule tại service? | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| Test HTTP API? | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |

Một số tình huống thực tế:

- Ứng dụng CRUD sử dụng Spring MVC, Spring Data JPA/JDBC blocking: **Servlet là lựa chọn tự nhiên**; xây Resource Server không bắt buộc chuyển sang WebFlux.
- Ứng dụng streaming với WebFlux, repository và outbound HTTP reactive: chọn security reactive để giữ cùng mô hình xử lý.
- Chỉ muốn gọi dịch vụ ngoài bằng `WebClient`: chưa đủ lý do thay đổi servlet security chain.
- Có nhiều issuer hoặc tenant: dùng cơ chế chọn authentication manager tương ứng request, ví dụ `AuthenticationManagerResolver<HttpServletRequest>` (Servlet) hoặc `ReactiveAuthenticationManagerResolver<ServerWebExchange>` (WebFlux), đồng thời chỉ chấp nhận issuer/tenant đã được tin cậy rõ ràng.
- API cần token bị thu hồi có hiệu lực nhanh: cân nhắc introspection, khả năng chịu lỗi và caching. JWT tự xác minh thường giảm lời gọi mạng trực tiếp nhưng cần chính sách TTL/revocation phù hợp.

Nếu chuyển Spring MVC sang WebFlux, có thể giữ **ý nghĩa** của rule (issuer, audience, scope và quyền nghiệp vụ) nhưng phải chuyển cách tạo security chain, decoder/introspector, method security và context. Chỉ sửa import class hoặc trả `Mono` ở controller không giải quyết những khác biệt đó.

## 12. CSRF và session: tránh suy luận từ tên Resource Server

OAuth 2.0 Bearer token trong header thường được dùng cho API không dựa vào session cookie. Với API thuần Bearer token, có thể cân nhắc vô hiệu hóa CSRF **trong phạm vi được đánh giá an toàn**, tùy mô hình client. Tuy nhiên, ứng dụng có endpoint trình duyệt, xác thực cookie hoặc session vẫn có thể cần CSRF protection. Không nên mặc định tắt CSRF chỉ vì cấu hình `oauth2ResourceServer()`.

Việc JWT được kiểm tra ở mỗi request không đồng nghĩa với việc mọi thành phần session hoặc context persistence đã tự bị vô hiệu hóa. Nếu mục tiêu là API stateless, cần xem toàn bộ cơ chế authentication, request caching, session management và các cơ chế đăng nhập khác đang bật, sau đó cấu hình thống nhất theo stack.

## 13. Các lỗi nhận thức phổ biến

### “Issuer hợp lệ thì access token đã được kiểm tra đầy đủ”

Chưa đủ. Issuer xác nhận nguồn phát hành; audience xác nhận đối tượng nhận token; scope/authority xác định quyền. Có thể cần thêm tenant, token type, client hoặc validator theo hồ sơ token của hệ thống.

### “WebFlux cũng dùng `BearerTokenAuthenticationFilter` như Servlet”

Không. Filter dành cho Servlet được thay bằng cơ chế `AuthenticationWebFilter` trong pipeline reactive. Mặc dù tên class `Authentication`/`Jwt` có thể dùng chung, HTTP integration là hai hệ riêng.

### “JWT lúc nào cũng cần gọi introspection”

Không. Resource Server có thể xác thực JWT cục bộ bằng chữ ký và JWK tin cậy; opaque token thường dựa vào introspection. Nếu có yêu cầu thu hồi token đặc biệt, hệ thống có thể chọn cơ chế bổ sung.

### “ID token là token của Resource Server”

Không. Trong OIDC, ID token phục vụ việc định danh cho client; API kiểm tra access token phù hợp với chính tài nguyên API đó.

### “Có `@AuthenticationPrincipal` thì không cần kiểm tra quyền nghiệp vụ”

Không. Tham số principal cho biết người dùng hoặc client đã được xác thực. Nó không bảo đảm họ sở hữu đơn hàng được truyền trong `/api/orders/{id}`.

### “Dùng `SecurityContextHolder` trong mọi `Mono` đều đúng”

Không. Reactive pipeline có thể chuyển thread, do đó dùng Reactor Context và `ReactiveSecurityContextHolder` cho dữ liệu security trong pipeline. `ThreadLocal` thông thường không tự bảo đảm context chính xác ở mọi operator.

### “Claim `roles` tự thành `ROLE_*`”

Không mặc định. Resource Server thường đưa `scope`/`scp` thành `SCOPE_*`; claim role tùy nhà cung cấp cần converter riêng.

## 14. Đọc kết quả một request: so sánh trực tiếp

Giả sử hai ví dụ cấu hình đều yêu cầu `SCOPE_orders.read` cho `GET /api/orders/**`.

**A. Access token hợp lệ có scope `orders.read`**

~~~http
GET /api/orders/me HTTP/1.1
Authorization: Bearer <valid-access-token-with-orders.read>
~~~

- Servlet: `BearerTokenAuthenticationFilter` → `JwtAuthenticationProvider` → `JwtAuthenticationToken` → `SecurityContextHolder` → MVC controller.
- WebFlux: `AuthenticationWebFilter` → `JwtReactiveAuthenticationManager` → `JwtAuthenticationToken` → Reactor SecurityContext → WebFlux handler.
- Kết quả: vượt qua rule HTTP, rồi controller/service tiếp tục xử lý quyền nghiệp vụ.

**B. Access token hợp lệ, chỉ có scope `profile`**: xác thực thành công nhưng thiếu authority yêu cầu, vì vậy response thường là `403`.

**C. Access token đã hết hạn**: decoder từ chối credential; request thường nhận `401` và không vào controller.

**D. JWT có chữ ký hợp lệ, issuer đúng, nhưng `aud` thuộc API khác**: nếu chưa cấu hình audience validation, bộ xác thực mặc định có thể không từ chối vì lý do audience. Cần bổ sung validator cho resource server.

## 15. Gợi ý kiểm thử và quan sát hệ thống

Các kịch bản kiểm thử nên thể hiện hợp đồng bảo mật: thiếu token, token sai/hết hạn, token hợp lệ thiếu quyền, token hợp lệ đủ quyền, sai issuer và sai audience. Trên MVC có thể dùng `MockMvc`, trên WebFlux dùng `WebTestClient` với thư viện `spring-security-test`. Việc mock JWT phù hợp để kiểm thử **rule cấp quyền**, nhưng chưa thay thế được kiểm thử tích hợp liên quan đến JWK discovery, kiểm tra chữ ký hoặc introspection endpoint thật.

Khi chẩn đoán sự cố:

- Nếu security bean không được áp dụng, xác nhận ứng dụng thực chạy trên Servlet hay Reactive.
- Nếu mọi token đều bị `401`, kiểm tra issuer, loại token, thời gian hệ thống, JWK/introspection URL và cấu hình trusted algorithms.
- Nếu chỉ bị `403`, kiểm tra authorities đã được converter tạo và tên scope trong rule.
- Nếu WebFlux gặp lỗi `block()` hoặc chậm bất thường, kiểm tra việc dùng I/O blocking trong converter, introspector tùy chỉnh và service.
- Nếu token dành cho API khác vẫn được chấp nhận, kiểm tra audience validation trước khi phân quyền.

## 16. Ghi nhớ kiến trúc

Ở **Servlet**, dòng xử lý có thể hình dung:

~~~text
HttpSecurity
  → SecurityFilterChain
  → BearerTokenAuthenticationFilter
  → AuthenticationManager
  → JwtDecoder / OpaqueTokenIntrospector
  → SecurityContextHolder
  → Authorization → MVC Controller
~~~

Ở **WebFlux**:

~~~text
ServerHttpSecurity
  → SecurityWebFilterChain
  → AuthenticationWebFilter
  → ReactiveAuthenticationManager
  → ReactiveJwtDecoder / ReactiveOpaqueTokenIntrospector
  → ReactiveSecurityContextHolder
  → Authorization → WebFlux Handler
~~~

Hai mô hình đều bảo vệ OAuth 2.0 Resource Server. Chọn mô hình theo HTTP runtime thực tế, xác thực **access token** đúng issuer/audience, ánh xạ quyền rõ ràng và giữ cùng chính sách truy cập tài nguyên ở các tầng ứng dụng.

## Tài liệu tham khảo

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
