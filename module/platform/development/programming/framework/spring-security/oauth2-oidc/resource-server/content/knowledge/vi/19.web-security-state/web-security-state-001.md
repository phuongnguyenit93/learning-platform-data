# API xác thực Bearer theo từng yêu cầu và lựa chọn quản lý phiên

Trong **Spring Security OAuth 2.0 Resource Server**, Bearer access token là credential mà client gửi đến API để chứng minh quyền truy cập. Khác với ứng dụng web truyền thống đăng nhập một lần rồi lưu `Authentication` trong `HttpSession`, API sử dụng Bearer token có thể **xác thực từng request**, không cần session đăng nhập phía server.

Tuy nhiên, câu “Resource Server là stateless” thường bị hiểu quá rộng. API không dùng `HttpSession` để nhớ caller vẫn có **cache JWK, introspection, database, rate limit, transaction và kết nối mạng**. Một ứng dụng cũng có thể vừa phục vụ **REST API Bearer stateless** vừa phục vụ **giao diện browser session-based**; mỗi khu vực cần chính sách bảo vệ thích hợp.

Bài học giải thích quan hệ giữa Bearer authentication theo request, `SecurityContext`, `HttpSession`, `SessionCreationPolicy` và lựa chọn cho mobile, SPA, service-to-service, browser login và BFF. Các ví dụ sử dụng **Spring Boot 3 / Spring Security 6, Servlet stack**. Hành vi mặc định có thể khác theo filter chain, repository và phiên bản; cần kiểm tra đường đi HTTP thực tế của ứng dụng.

## 1. Bearer authentication theo từng request là gì?

Client gọi API:

```http
GET /api/orders/101 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Request tiếp theo **vẫn phải mang credential**:

```http
GET /api/orders/102 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Trong mô hình Resource Server stateless:

1. Spring Security đọc Bearer token từ request.
2. Authentication provider gọi `JwtDecoder` hoặc `OpaqueTokenIntrospector`.
3. Khi token được chấp nhận, framework tạo `Authentication` với principal và authorities.
4. `Authentication` được đặt trong `SecurityContext` của **request đang xử lý**.
5. Framework kết thúc và dọn ngữ cảnh theo lifecycle của request.
6. Request sau phải xuất trình token; API **không dựa vào session đăng nhập lưu từ request trước**.

**Stateless ở đây là không phụ thuộc session đăng nhập giữa các request**, không phải ứng dụng tuyệt đối không có trạng thái.

Với JWT, Resource Server thường xác minh chữ ký và claims bằng public keys đáng tin. Với opaque token, ứng dụng thường gọi introspection đến Authorization Server. Cả hai đều có thể vận hành không cần `HttpSession` để lưu principal.

## 2. Luồng xác thực hai request độc lập

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant P as AuthenticationProvider
    participant S as SecurityContext
    participant A as Orders API
    C->>F: Request 1 + Bearer token
    F->>P: authenticate(token)
    P-->>F: Authentication hợp lệ
    F->>S: Gắn Authentication cho request 1
    S->>A: Principal và authorities
    A-->>C: HTTP response 1
    Note over S: Dọn context khi request hoàn tất
    C->>F: Request 2 + Bearer token
    F->>P: authenticate(token) lần mới
    P-->>F: Authentication hợp lệ
    F->>S: Gắn Authentication cho request 2
    S->>A: Principal và authorities
    A-->>C: HTTP response 2
```

**Xác thực mỗi request không có nghĩa mỗi request tải JWKS qua mạng.** `JwtDecoder` có thể dùng JWK Set đã cache, trong khi `OpaqueTokenIntrospector` tùy chỉnh có thể cache introspection theo policy. Những cache này **không phải web login session**.

Nếu request 2 không mang Bearer token, endpoint yêu cầu authentication phải từ chối, dù request 1 vừa thành công. Đây là bất biến cần kiểm thử.

## 3. Phân biệt Bearer token, `SecurityContext`, `HttpSession` và cache

| Thành phần | Nơi tồn tại | Vai trò | Có phải login session? |
| --- | --- | --- | --- |
| **Bearer access token** | Client giữ, gửi theo request. | Credential của lời gọi API. | Không. |
| **`SecurityContext`** | Phạm vi xử lý request/thread/repository cấu hình. | Chứa `Authentication` hiện tại. | Có thể được lưu sang session khi policy cho phép. |
| **`HttpSession`** | Server hoặc distributed session store; browser giữ ID. | Duy trì trạng thái giữa các request. | Có thể. |
| **Session cookie** (`JSESSIONID`) | Browser tự gửi theo cookie policy. | Tham chiếu một session phía server. | Thường dùng cho web login. |
| **JWK/introspection cache** | Bộ nhớ pod, Redis hoặc tầng cache khác. | Giảm chi phí lấy khóa/kiểm tra token. | Không. |
| **Database, rate limit, connection pool** | Hạ tầng ứng dụng. | Dữ liệu nghiệp vụ và quản lý tài nguyên. | Không tự là login session. |

Một API Bearer stateless **vẫn tạo `SecurityContext` trong request** để controller/service đọc danh tính; điểm khác là không phục hồi authentication từ session giữa các request.

Trong Servlet stack, `SecurityContextHolder` mặc định sử dụng chiến lược dựa trên `ThreadLocal`; các kiểu xử lý bất đồng bộ cần chính sách propagation riêng, không tự thừa hưởng danh tính ở mọi thread.

## 4. `SecurityContext` và `HttpSession` không đồng nhất

Sau JWT authentication thành công:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

Trong JWT Resource Server, `auth` thường là `JwtAuthenticationToken`; với opaque token thường là `BearerTokenAuthentication`.

`HttpSession` là cơ chế khác:

```java
HttpSession existing = request.getSession(false);
```

`getSession(false)` chỉ lấy session đã tồn tại. Còn:

```java
HttpSession createdOrExisting = request.getSession();
```

có thể tạo session. `SessionCreationPolicy.STATELESS` kiểm soát cách **Spring Security** tạo/sử dụng session cho authentication, **không ngăn mọi servlet/controller/library khác gọi `getSession()`**.

Do đó, khi nói “API không dùng session”, điều quan trọng là **Spring Security có dựa vào session để lấy/lưu Authentication cho request sau hay không**, chứ không phải chỉ nhìn hệ thống có một cookie nào đó hay không.

## 5. Bốn lựa chọn `SessionCreationPolicy`

Spring Security có enum:

```java
org.springframework.security.config.http.SessionCreationPolicy
```

| Policy | Hành vi chính của Spring Security | Trường hợp phù hợp |
| --- | --- | --- |
| `ALWAYS` | Spring Security luôn tạo HTTP session. | Có nhu cầu session cụ thể; ít dùng cho Bearer API thuần. |
| `IF_REQUIRED` | Tạo session khi thực sự cần. | Web login, saved request, lưu authentication. |
| `NEVER` | Spring Security không tự tạo session, **nhưng có thể dùng session có sẵn**. | Muốn hạn chế tạo mới nhưng vẫn chấp nhận session hiện tại. |
| `STATELESS` | Spring Security không tạo và **không dùng session để lấy `SecurityContext`**. | API Bearer xác thực độc lập từng request. |

Đặc biệt:

```text
NEVER != STATELESS
```

Với `NEVER`, một session do thành phần khác tạo có thể được security logic sử dụng tùy configuration. Với `STATELESS`, API không dựa vào session đã lưu để khôi phục principal.

`IF_REQUIRED` không nhất thiết tạo session cho mọi request: còn phụ thuộc loại login, request cache và tính năng security đang hoạt động. Tương tự, `STATELESS` không bảo đảm **toàn bộ ứng dụng hoặc proxy** không bao giờ phát session cookie.

## 6. JWT Resource Server stateless với Spring Boot

Gradle:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

YAML:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
```

Một chain dành riêng cho API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Ở đây:

- `securityMatcher("/api/**")` giới hạn **phạm vi của chain**.
- `STATELESS` làm Spring Security không dùng session để khôi phục authentication.
- `oauth2ResourceServer().jwt()` nhận Bearer JWT và xác thực từng request.
- `hasAuthority("SCOPE_orders.read")` kiểm tra quyền chức năng được ánh xạ từ token.
- `anyRequest().denyAll()` áp dụng **trong chain này**, không bảo vệ URL ngoài `/api/**`.
- `csrf.disable()` chỉ thích hợp theo giả định **API nhận Bearer qua header, không dùng cookie/browser credential tự gửi để xác thực**.

Ứng dụng có Actuator, Swagger, browser login, webhook hoặc các route khác cần security chain/fallback và policy riêng.

## 7. Request sau không có Bearer không trở thành authenticated

Một request hợp lệ:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders/101
```

Request tiếp theo:

```bash
curl -i https://api.example.com/api/orders/101
```

phải bị từ chối nếu endpoint yêu cầu JWT, ngay cả khi cùng địa chỉ IP và request trước thành công. Server không “nhớ caller theo IP” hoặc tự phục hồi `Authentication` từ một request cũ.

Token có thể được **dùng lại hợp lệ trong thời gian còn hiệu lực**; stateless không biến token thành one-time credential và không tự giải quyết Bearer token replay khi token bị đánh cắp.

## 8. `JwtDecoder` xác minh mỗi request nhưng không nhất thiết gọi mạng

JWT Resource Server sử dụng decoder để xác minh chữ ký, issuer, các claim thời gian và validator theo chính sách API. Public keys có thể đã có trong JWK cache của pod.

```text
Mỗi request cần authentication
     !=
Mỗi request cần gọi Authorization Server
```

Token JWT:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

Payload này chỉ minh họa; không phải token có chữ ký. API phải kiểm tra `aud` theo hợp đồng của mình, không mặc định rằng mọi decoder cấu hình issuer đều đã kiểm tra audience.

Một số pod có thể cache JWKS khác thời điểm khi issuer rotate key. Đây là **vòng đời cache khóa**, không phải session login. Cấu hình `STATELESS` không làm các pod tự chia sẻ JWK Set hay thực hiện revocation tự động.

## 9. Opaque token cũng có thể xác thực stateless

Spring Boot opaque token:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

DSL:

```java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
```

Với opaque token, Resource Server thường gọi introspection endpoint để biết trạng thái token và nhận principal; một custom introspector có thể cache theo TTL/policy.

| Yếu tố | Bearer JWT | Bearer opaque |
| --- | --- | --- |
| Cơ chế xác minh thường gặp | Chữ ký và claims qua `JwtDecoder`. | `OpaqueTokenIntrospector` gọi upstream. |
| Principal Spring Security | Thường `JwtAuthenticationToken`. | Thường `BearerTokenAuthentication`. |
| Yêu cầu session login? | Không. | Không. |
| Có thể dùng `STATELESS`? | Có. | Có. |
| Phụ thuộc mạng khi xác thực | Fetch/refresh JWK Set theo tình trạng cache. | Thường introspection, trừ cache/policy. |
| Thu hồi token | Phụ thuộc expiry, denylist hoặc online policy. | Phụ thuộc trạng thái upstream và cache. |

**Opaque không đồng nghĩa stateful**. Nó chỉ diễn tả token không được Resource Server tự xác minh bằng nội dung JWT theo cách thông thường.

## 10. Nên dùng session khi nào?

| Kiến trúc | Credential | Session tại Resource Server? | Lưu ý |
| --- | --- | --- | --- |
| Mobile app → REST API | Bearer trong header. | Thường không. | Token storage, lifetime/refresh. |
| Backend-to-backend | Client Credentials access token. | Thường không. | Service identity, audience, scope. |
| CLI hoặc integration worker | Bearer token. | Thường không. | Xử lý 401, refresh theo OAuth Client. |
| SPA gọi API trực tiếp | Bearer header do JS thêm. | API thường không. | XSS, CORS, token storage. |
| Web server-rendered | Session cookie. | Có thể cần. | CSRF, session fixation, logout, timeout. |
| BFF/OIDC login | Browser cookie, server giữ token downstream. | Web/BFF thường có. | CSRF, cookies, server-side token lifecycle. |
| Ứng dụng kết hợp API và web | Bearer cho API; cookie cho web. | Tách theo chain. | Không để web session thay Bearer. |

Chọn policy dựa trên **cách client gửi credential**, nhu cầu giữ login và ranh giới endpoint. Không có một giá trị enum đúng cho tất cả ứng dụng.

## 11. `STATELESS` không bảo đảm toàn bộ server không tạo cookie

Một hiểu nhầm thường gặp:

> Có `STATELESS`, ứng dụng chắc chắn không bao giờ trả `Set-Cookie: JSESSIONID`.

Sai vì `STATELESS` áp dụng cho **Spring Security session usage**. Servlet/controller, một filter khác, web framework hoặc reverse proxy có thể tạo session/cookie riêng.

Ví dụ trong controller:

```java
@GetMapping("/api/debug")
public String debug(HttpServletRequest request) {
    request.getSession(); // Có thể tạo HttpSession
    return "ok";
}
```

Nếu cookie xuất hiện, cần xác định **thành phần nào tạo nó**. Chỉ nhìn thấy `JSESSIONID` không chứng minh Security đã khôi phục principal từ session.

Bằng chứng quan trọng hơn cho API Bearer-only:

```text
Request 1: có Bearer -> authenticated
Request 2: không Bearer, chỉ cookie -> vẫn phải bị từ chối
```

## 12. `SecurityContextRepository` và lưu context

Spring Security sử dụng abstraction `SecurityContextRepository` để tải/lưu security context theo cấu hình. Một số implementation:

| Repository | Vai trò |
| --- | --- |
| `HttpSessionSecurityContextRepository` | Có thể lưu/phục hồi context từ HTTP session theo policy. |
| `RequestAttributeSecurityContextRepository` | Giữ context trong **cùng request** qua request attributes/dispatch thích hợp. |
| `NullSecurityContextRepository` | Không lưu context qua repository. |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều cách tải/lưu theo thứ tự. |

Spring Security 6 có các thay đổi trong context-loading filters và chính sách explicit save. **Không nên khẳng định mọi `STATELESS` chain đều dùng đúng một class repository trong mọi phiên bản/cấu hình**. Điều cần bảo đảm là principal của API Bearer đến từ xác thực credential của request này, không từ `HttpSession` cũ.

Sự tồn tại của một context trong request attributes **không làm API trở thành session-based**, vì request attribute không dùng để nhớ user giữa hai request độc lập.

## 13. Không tắt hàng loạt filter chỉ vì muốn stateless

Ví dụ một cấu hình cực đoan:

```java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .securityContext(context -> context.disable())
    .anonymous(anonymous -> anonymous.disable())
    .requestCache(cache -> cache.disable());
```

Đây không phải hướng dẫn mặc định để tạo API tốt. `STATELESS` liên quan đến session, trong khi SecurityContext, anonymous authentication, exception handling và request cache có trách nhiệm khác. Tắt bừa có thể làm filter chain khó đoán hoặc thay đổi hành vi authorization.

Với API thuần Bearer, thông thường nên bắt đầu bằng `STATELESS`, `oauth2ResourceServer`, scoped authorization, CSRF/CORS theo threat model và fallback chain rõ ràng. Chỉ tùy chỉnh repository/filter khác khi có nhu cầu được kiểm chứng.

## 14. `401` và `403` khi API không có session

| Request | Authentication | Authorization | Kết quả thường gặp |
| --- | --- | --- | --- |
| Không Bearer ở protected API | Thiếu principal. | Không thể cho phép. | `401`. |
| JWT sai chữ ký/issuer/expiry/audience | Xác thực thất bại. | Không dùng claims của token. | `401`. |
| JWT hợp lệ, thiếu `orders.read` | Có principal. | Thiếu authority. | `403`. |
| JWT đúng scope nhưng sai tenant/owner | Thành công. | Domain policy từ chối. | `403` hoặc `404`. |
| JWT đủ điều kiện và object hợp lệ | Thành công. | Được phép. | `2xx` nếu nghiệp vụ thành công. |
| Chỉ có web session cookie | API STATELESS Bearer-only không dùng session để khôi phục principal. | Protected API từ chối. | Thường `401`. |

Spring Security OAuth 2.0 Bearer thường trả header `WWW-Authenticate: Bearer`; lỗi token không hợp lệ có thể có `invalid_token`. Mã thực tế phụ thuộc entry point, access denied handler, chain và exception mapping.

Với REST API, **không nên mặc nhiên redirect tới HTML login page** thay vì gửi 401 phù hợp cho client. Web login session lại có thể cố ý redirect đến `/login`.

## 15. CSRF phải đánh giá theo cách browser gửi credential

CSRF (*Cross-Site Request Forgery*) khai thác việc trình duyệt **tự đính kèm credential** như session cookie đến server khi được yêu cầu từ một website khác.

Với API nhận `Authorization: Bearer` do code tin cậy chủ động thêm, một website tùy ý không thể tự làm browser gửi đúng Bearer token chỉ bằng một form HTML nếu không biết token. Vì vậy Bearer API **chỉ dùng Authorization header, không dùng cookie làm authentication** thường không cần CSRF theo mô hình truyền thống.

Nhưng một ứng dụng có:

```http
Cookie: access_token=<token>
```

hoặc `JSESSIONID` vẫn có credential được browser tự gửi; cần cân nhắc CSRF, dù Spring Security đang dùng `STATELESS` cho một phần ứng dụng.

| Cách gửi credential | Tự đính kèm? | Kết luận |
| --- | --- | --- |
| Bearer header do client thêm | Không theo cách cookie tự gửi. | CSRF truyền thống thường ít áp dụng, nhưng vẫn có XSS/token theft. |
| Session cookie | Có. | Cần CSRF protection cho state-changing requests. |
| JWT trong `HttpOnly` cookie | Có thể theo cookie policy. | `HttpOnly` **không giải quyết CSRF**. |
| BFF session cookie | Có. | Cần CSRF protection và cookie attributes. |
| HTTP Basic Auth browser tự nhớ | Có thể tự đính kèm. | Cần đánh giá CSRF. |

**Stateless không tự động đồng nghĩa chống CSRF.** Nếu API dùng cookies làm credential, đừng sao chép `.csrf(csrf -> csrf.disable())` chỉ vì token có định dạng JWT.

## 16. Cookie `HttpOnly`, `Secure`, `SameSite` và web session

Khi browser dùng session cookie:

- `HttpOnly` giúp hạn chế JavaScript đọc cookie, giảm một đường lộ session qua XSS.
- `Secure` yêu cầu cookie chỉ được gửi qua HTTPS.
- `SameSite=Lax` hoặc `Strict` giảm các tình huống cross-site tùy sản phẩm.
- `Domain` và `Path` nên hạn chế đúng phạm vi.
- Đăng nhập nên có session fixation protection/rotation session ID.
- Session phải có timeout, logout và invalidation theo chính sách.

Các biện pháp này bổ sung lẫn nhau, **không thay thế CSRF token và kiểm tra origin khi cần**. SameSite không phải một lời hứa rằng mọi biến thể CSRF đều bị chặn.

Trong Spring Boot, nhiều thuộc tính cookie nằm ở `server.servlet.session.cookie.*`; cần kiểm tra support/version và hành vi sau reverse proxy/TLS termination.

## 17. SPA trực tiếp gọi Resource Server

Một SPA có thể:

```text
Browser SPA
  -> Authorization Code + PKCE với IdP
  -> nhận access token theo kiến trúc client
  -> tự thêm Authorization: Bearer vào request API
  -> Resource Server xác thực mỗi request
```

Quyết định lưu token ở đâu cũng rất quan trọng:

| Token storage | Lợi ích | Rủi ro |
| --- | --- | --- |
| JavaScript memory | Không tồn tại lâu sau reload. | XSS ở runtime vẫn có thể dùng/lấy token. |
| Local/session storage | Thuận tiện qua reload/tab. | JavaScript cùng origin, kể cả XSS, có thể đọc. |
| `HttpOnly` cookie | JavaScript không đọc trực tiếp token. | Browser tự gửi cookie: cần CSRF, cookie policy. |
| BFF giữ token phía server | Hạn chế token lộ cho browser JS. | Cần session store, CSRF, refresh/rotation phía server. |

API `STATELESS` không quyết định client phải giữ token ở đâu. Nó chỉ xác định cách Resource Server dùng session để nhận diện request.

## 18. BFF có session nhưng downstream Resource Server vẫn stateless

Mô hình **Backend for Frontend**:

```mermaid
flowchart LR
    B["Browser"] -->|"Session cookie"| F["BFF / Web backend"]
    F -->|"Bearer access token"| A["Orders Resource Server"]
    F <-->|"OIDC/OAuth login và refresh"| I["Authorization Server"]
```

Tách hai mối quan hệ:

1. **Browser ↔ BFF**: web session, cookie, CSRF, login/logout và server-side token storage.
2. **BFF ↔ Resource Server**: mỗi downstream request mang access token dành cho API, có issuer/audience/scope đúng.

Điều này không mâu thuẫn. `SessionCreationPolicy.IF_REQUIRED` có thể phù hợp tại BFF, trong khi Resource Server downstream dùng `STATELESS`.

BFF không được biến session cookie của browser thành quyền vô điều kiện trên API: nó phải chọn access token đúng và không bỏ qua domain authorization của Resource Server.

## 19. `oauth2Login()` khác `oauth2ResourceServer()`

| Cấu hình | Vai trò | Đối tượng authentication |
| --- | --- | --- |
| `.oauth2ResourceServer(o -> o.jwt(...))` | API xác minh Bearer JWT access token. | Thường `JwtAuthenticationToken`. |
| `.oauth2ResourceServer(o -> o.opaqueToken(...))` | API introspect opaque access token. | Thường `BearerTokenAuthentication`. |
| `.oauth2Login(...)` | OAuth 2.0/OIDC Client login bằng authorization code. | Web Authentication có thể lưu trong session. |
| `.formLogin(...)` | Web login bằng biểu mẫu. | Authentication được giữ theo web session policy. |

OIDC **ID Token** phục vụ OIDC Client nhận biết End-User; không tự là access token dành cho Resource Server. BFF dùng `oauth2Login()` cần `spring-boot-starter-oauth2-client`, client registration/provider, session và logout theo OIDC flow.

Resource Server có thể chỉ dùng `spring-boot-starter-oauth2-resource-server` mà không có login page hay web session.

## 20. Kết hợp web session và API Bearer bằng hai `SecurityFilterChain`

Ví dụ một Spring Boot ứng dụng vừa có `/api/**` vừa có website dùng form login:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DualSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/assets/**", "/error"
                ).permitAll()
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Trong ví dụ:

- Chain **1** khớp `/api/**`, yêu cầu Bearer JWT và không dùng session để khôi phục authentication.
- Chain **2** là **fallback** cho URL còn lại; dùng web login và có thể tạo session khi cần.
- CSRF của web chain **vẫn bật** vì không có cấu hình tắt.
- `/login` do web chain xử lý; ứng dụng cần cấu hình user authentication source phù hợp với form login.
- Khi dùng OIDC Client, có thể thay `.formLogin(...)` bằng `.oauth2Login(...)` cùng dependency/cấu hình OAuth Client.

**Không áp dụng đoạn này mù quáng** cho hệ thống có API cũng nhận cookie, BFF routes, Actuator trên cổng khác hoặc những flow cần CSRF khác. Phải xác định credential được phép trên mỗi nhóm endpoint.

## 21. Chain đầu tiên khớp sẽ được chọn

Spring Security `FilterChainProxy` chọn **chain đầu tiên khớp request**, không chạy tất cả chain theo thứ tự. Với cấu hình trên:

```text
GET /api/orders/101 -> chain @Order(1)
GET /account        -> chain @Order(2)
GET /login          -> chain @Order(2)
```

Một `anyRequest().denyAll()` bên trong chain `/api/**` **không bảo vệ** `/admin`, `/actuator` hoặc `/swagger-ui` nằm ngoài matcher. Nếu chỉ tạo một bean chain cho `/api/**`, Spring Boot có thể nhường chỗ phần auto-configuration web security mặc định, khiến URL khác không có chain bảo vệ.

Do đó cần một **fallback chain hoặc chính sách tương đương** cho những đường nằm ngoài API. Trong test, phải xác minh đúng chain/entry point cho cả route được bảo vệ lẫn route không tồn tại.

## 22. Cookie web không thay được Bearer access token của API

Người dùng đăng nhập web, có:

```http
Cookie: JSESSIONID=...
```

Gọi API:

```http
GET /api/orders/101
Cookie: JSESSIONID=...
```

với Bearer-only API chain `STATELESS` **không được tự cho phép** chỉ vì browser đã đăng nhập. Đó là một ranh giới cần kiểm thử:

1. Login web thành công, lấy session cookie.
2. Dùng **chỉ cookie** gọi protected `/api/orders/101`.
3. API phải từ chối vì thiếu Bearer token.
4. Gửi Bearer JWT hợp lệ có scope phù hợp.
5. Authentication/endpoint policy cho phép, sau đó vẫn xét tenant/owner.

Nếu API cho phép ở bước 3, cần kiểm tra `securityMatcher`, session repository, reverse proxy identity và logic authentication bổ sung.

## 23. Proxy/gateway cũng có thể tạo session ngoài Spring Security

Ngay cả khi chain API stateless, cần hiểu:

- Ingress có forward cookie web đến API không?
- Gateway có dùng SSO session rồi thêm header `X-User` hoặc `Authorization` không?
- Reverse proxy có session cookie riêng khác `JSESSIONID` không?
- API có chủ động tin một identity header chỉ nên được proxy thiết lập không?
- Có tách rõ public web origin, BFF route và protected API origin không?

Cookie xuất hiện ở một request không nhất thiết được **dùng để xác thực** request. Nhưng nếu gateway hoặc adapter biến cookie thành principal, đó là một authentication mechanism khác cần trust boundary, strip spoofed headers và policy riêng.

Đừng coi cấu hình `STATELESS` trong Spring Security là bằng chứng mọi tầng trước nó đều stateless.

## 24. Request cache/redirect phù hợp web hơn REST API

Web session login thường có:

```text
GET /account
  -> chưa login
  -> lưu original request
  -> redirect /login
  -> login
  -> redirect /account
```

Đây là luồng thích hợp với browser và có thể dùng `HttpSession`/`RequestCache`.

API Bearer thường có:

```text
GET /api/orders/101 không token
  -> 401 Unauthorized
  -> client tự xử lý lấy token/login
```

Không cần lưu request API vào session để redirect HTML. Nếu ứng dụng kết hợp web/login và Bearer, `AuthenticationEntryPoint` và request cache cần được lựa chọn theo loại chain để mobile/server-side client không gặp `302 /login` ngoài dự kiến.

## 25. CORS preflight có thể không mang Bearer

SPA từ `https://app.example.com` gọi `https://api.example.com` có thể gửi preflight:

```http
OPTIONS /api/orders/101 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflight thường **không mang Bearer của request chính**. Nếu authentication chạy trước CORS policy, browser có thể báo lỗi CORS thay vì gọi được API.

Ví dụ `CorsConfigurationSource`:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of(
        "https://app.example.com"
    ));
    config.setAllowedMethods(List.of(
        "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
    ));
    config.setAllowedHeaders(List.of(
        "Authorization", "Content-Type"
    ));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

Trong security chain:

```java
.cors(Customizer.withDefaults())
```

CORS điều khiển browser theo origin, **không thay authentication hoặc authorization**. Curl và server-to-server clients vẫn có thể gọi HTTP; mọi request nghiệp vụ phải dùng Bearer đúng.

## 26. Access token expiry khác session timeout

Ví dụ một sản phẩm có:

```text
Web session timeout: 30 phút không hoạt động
Access token lifetime: 10 phút
Refresh token lifetime: theo chính sách Authorization Server
```

Ba đồng hồ này **không tự đồng bộ**:

- BFF web session còn sống nhưng downstream access token hết hạn: BFF cần refresh nếu được ủy quyền.
- Browser session hết hạn nhưng token đã copy vẫn còn hạn: Resource Server có thể tiếp tục chấp nhận token nếu không có cơ chế revoke liên kết.
- Resource Server `STATELESS` không tự gia hạn claim `exp`.
- OAuth Client/Authorization Server quản lý refresh token theo grant và policy; business API thông thường không nhận refresh token thay access token.

**Không lấy thời gian của `JSESSIONID` làm thời hạn của JWT**, hoặc coi JWT là session ID. Chúng có mục đích, validation và lifecycle khác.

## 27. Logout session không đồng nghĩa revoke Bearer

**Web session:**

```text
Browser -> logout theo CSRF policy
Server -> invalidate session và clear context
Browser -> session cookie không còn login hợp lệ
```

**Bearer stateless:**

```text
Client xóa access token khỏi storage
Resource Server không có login session để invalidate
Bản sao token đã bị lấy trước đó vẫn có thể còn hiệu lực
  đến khi exp hoặc cơ chế revocation/denylist có tác dụng
```

Với yêu cầu thu hồi gần realtime, có thể cần opaque introspection, denylist, token version, access token lifetime ngắn hoặc online policy. Các biện pháp đó là **token authorization/revocation design**, không tự xuất hiện khi đặt `SessionCreationPolicy`.

`SecurityContextHolder.clearContext()` ở cuối request cũng **không revoke token**.

## 28. Session fixation và Bearer replay là hai mối đe dọa

| Mô hình | Mối đe dọa | Biện pháp |
| --- | --- | --- |
| Web session | Session fixation. | Thay/rotate session ID sau login; bảo vệ session fixation. |
| Web session | Cookie/session ID bị lấy cắp. | `Secure`, `HttpOnly`, SameSite, TLS, giới hạn cookie, timeout và logout. |
| Bearer API | Access token bị lộ/replay. | TLS, bảo vệ token storage, lifetime ngắn, revocation khi cần. |
| Bearer API | Token sai issuer/audience. | JWT/opaque validation đúng hợp đồng protected resource. |
| Cả hai | Caller hợp lệ nhưng truy cập sai tenant/owner. | Functional scope + domain-level authorization. |

Spring Security có cơ chế bảo vệ session fixation cho web login theo cấu hình phiên bản. Nó **không làm Bearer token thành proof-of-possession**. Các cơ chế sender-constrained token như mTLS-bound access token hay DPoP đòi hỏi kiến trúc hỗ trợ riêng.

## 29. Nhiều pod: session store khác JWK/introspection cache

```text
Load balancer
  -> API pod A
  -> API pod B
  -> API pod C
```

API Bearer stateless không cần tìm `HttpSession` cũ ở pod A khi request sau đến pod B. Mỗi pod xác thực credential theo policy của mình.

Ứng dụng web session-based có thể cần sticky sessions hoặc shared session store như Spring Session + Redis để phục hồi login state khi đổi pod.

| Tiêu chí | Bearer API stateless | Web session stateful |
| --- | --- | --- |
| Session replication cho authentication | Thường không. | Có thể cần. |
| Scale replica | Không cần di chuyển login session giữa pod. | Cần nghĩ đến store, timeout, sticky routing. |
| Logout | Không tự revoke access token. | Có thể invalidate session. |
| IdP outage | JWT có key có thể hoạt động cục bộ; opaque tùy introspection. | Session đang có có thể hoạt động tùy cấu hình. |
| Redis session store down | Không ảnh hưởng trực tiếp nếu API không dùng nó để xác thực. | Có thể ảnh hưởng web session. |

`STATELESS` không xóa nhu cầu cân nhắc JWKS refresh, introspection cache, DNS/TLS, clock skew hay tenant membership.

## 30. Stateless không nghĩa là quyền nghiệp vụ luôn mới nhất

Một JWT còn hạn:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "alice",
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

có thể vẫn được gửi sau khi Alice bị thu hồi membership tenant-a. API xác thực Bearer mỗi request nhưng **không tự hỏi database rằng membership đã bị thu hồi hay chưa**.

```text
Bearer authentication mỗi request
   !=
Domain authorization luôn kiểm tra realtime
```

Nếu yêu cầu thu hồi quyền tenant sớm, cần policy kiểm tra membership hiện tại hoặc cache quyền TTL/invalidation phù hợp. JWT validation, OAuth scope, tenant membership và owner checking là các lớp độc lập.

## 31. `@Async`, scheduler và context propagation

Trong Servlet stack, SecurityContext thường nằm trong thread xử lý request. Một method:

```java
@Async
public void runExport() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
}
```

không được tự giả định `auth` sẽ là principal JWT từ request gốc. Spring Security có các cơ chế `DelegatingSecurityContext...` để propagation khi cần, nhưng truyền cả context/credential sang background work phải cân nhắc vòng đời, privacy và revoke.

Một hướng có thể phù hợp:

1. Xác thực và phân quyền **trước khi enqueue job**.
2. Truyền `CallerIdentity` tối thiểu hoặc capability đã xác minh, không truyền raw Bearer token không cần thiết.
3. Khi job chạy, kiểm tra domain policy phù hợp với trạng thái hiện hành nếu cần.
4. Phân biệt người yêu cầu job và **service identity** thực thi.
5. Không tự dựng `JwtAuthenticationToken` từ giá trị `userId` trong message.

Bật `HttpSession` không giải quyết identity propagation cho scheduler.

## 32. Các phản ví dụ thường gặp

### 32.1. Giữ `Authentication` vào static variable

```java
static Authentication currentUser;
```

Không làm vậy: concurrent requests có thể ghi đè và làm lẫn danh tính. Dùng request context hoặc identity truyền tường minh.

### 32.2. Dùng `JSESSIONID` để truy cập API Bearer-only

Nếu API xác thực theo Bearer, cookie login web không thay token. Test route `/api/**` khi browser đã login.

### 32.3. Tắt CSRF chỉ vì `STATELESS`

JWT trong cookie vẫn được browser tự gửi. Quyết định CSRF phụ thuộc credential transport.

### 32.4. Tự dùng JWT làm session ID

Token và session ID có lifecycle, validation, revocation và security semantics khác nhau.

### 32.5. Gửi refresh token đến business API

Refresh token chỉ dùng ở token endpoint với OAuth Client hợp lệ, không thay access token.

### 32.6. Dùng `NEVER` rồi khẳng định không bao giờ đọc session

`NEVER` có thể dùng session đã tồn tại; `STATELESS` mới là policy không dùng session cho SecurityContext.

### 32.7. Tạo session để giảm xác minh JWT

Nếu cần giảm network JWKS/introspection, thiết kế cache đúng contract. Đừng chuyển Bearer token thành session login mà bỏ expiry/audience/revocation.

### 32.8. Quên fallback chain ngoài `/api/**`

Một chain hẹp không tự bảo vệ `/actuator`, `/swagger-ui` hoặc `/admin`.

### 32.9. Tin `getSession(false) != null` là đã login

Session tồn tại không đồng nghĩa `Authentication` đáng tin có mặt.

### 32.10. Logout web được hiểu là revoke JWT

Token đã bị sao chép trước khi logout có thể vẫn hoạt động cho đến khi policy thu hồi/expiry áp dụng.

## 33. MockMvc test: request sau vẫn cần Bearer

Spring Security Test có thể tạo principal JWT giả lập:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiStatelessTest {

    @Autowired MockMvc mvc;

    @Test
    void bearerAuthenticationDoesNotCarryToNextRequest()
            throws Exception {
        mvc.perform(get("/api/orders/101")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());

        mvc.perform(get("/api/orders/101"))
            .andExpect(status().isUnauthorized());
    }
}
```

Test giả định controller/service fixture cho phép request đầu có `200`. **`jwt()` của Spring Security Test thường tạo authentication giả lập** và **không chạy `JwtDecoder` production để xác minh JWT ký thật**. Nó giúp kiểm tra authorization/chain behavior, không đủ để chứng minh JWT signature, issuer, audience và expiry.

Để chứng minh **session thực sự không được dùng**, cần kiểm thử bổ sung bằng HTTP có token ký thật, kiểm tra cookie/session và request không Bearer nhưng mang session cookie từ web login.

## 34. Ma trận test hai chain web và API

| Kịch bản | Kỳ vọng |
| --- | --- |
| `GET /api/orders/101` không Bearer | `401`, không redirect HTML login. |
| API có Bearer hợp lệ + `orders.read` | Qua authentication/endpoint policy, còn xét owner. |
| API có Bearer hợp lệ nhưng thiếu scope | `403`. |
| Web đã login, gọi API chỉ với `JSESSIONID` | Không thay JWT authentication. |
| Web chưa login, gọi `/account` | Web entry point/login flow phù hợp. |
| Web login rồi gọi `/account` bằng session cookie | Hoạt động theo web session policy. |
| Web logout rồi dùng cookie cũ | Không còn web authentication. |
| Bearer token đã cấp sau web logout | Không tự bị revoke nếu không có mechanism khác. |
| Preflight `OPTIONS /api/orders/101` với origin cho phép | CORS xử lý đúng mà không đòi Bearer trên preflight. |
| URL ngoài API như `/actuator` và `/swagger-ui` | Có chain/fallback bảo vệ theo thiết kế. |

Nếu muốn kiểm thử session cookie/redirect thật, dùng embedded-server HTTP integration test hoặc test browser. Ngoài GET, phải thử POST/PUT/DELETE trên web session route để bảo đảm CSRF vẫn có hiệu lực.

## 35. JWT integration test và web session test cần tách

**JWT end-to-end test:**

1. Chuẩn bị test issuer/JWK Set đáng tin và JWT được ký bằng private key test.
2. Gửi Bearer token qua HTTP để kiểm chứng `JwtDecoder`.
3. Kiểm tra chữ ký, `iss`, `aud`, `exp`, `nbf` và authority mapping.
4. Gửi request **không Bearer** sau request hợp lệ.
5. Gửi chỉ cookie web nếu ứng dụng có web session; API phải không chấp nhận thay Bearer.

**Web session integration test:**

1. Login bằng form/OIDC Client ở web route.
2. Nhận session cookie.
3. Gửi cookie qua request tiếp theo và kiểm chứng web authentication.
4. Kiểm tra CSRF, session fixation, timeout và invalidation khi logout.
5. Kiểm tra browser session không thể vượt qua API chain Bearer-only.

Mỗi test chứng minh một phần: JWT cryptography không chứng minh web session logic; web session login không chứng minh audience của access token dành cho API.

## 36. Chẩn đoán 200, 401, 403, 302 và CORS error

| Hiện tượng | Khả năng | Điều tra |
| --- | --- | --- |
| Request 1 có Bearer được 200, request 2 không header được 401 | Client không gắn Bearer cho request sau; stateless hoạt động đúng. | Inspect HTTP client/interceptor, không log token. |
| Cùng JWT request sau bị 401 | Token hết hạn/revoke, clock skew, JWKS/issuer/introspection lỗi. | Kiểm tra decoder, IdP, pod config và thời gian. |
| Request API trả `302 /login` | Đường đi vào web chain hoặc entry point sai. | Security matcher/order và entry point. |
| API trả 403 với JWT hợp lệ | Scope, role, CSRF hoặc domain policy từ chối. | Phân biệt rule và CSRF theo route. |
| GET được nhưng POST bị 403 từ browser | Có thể thiếu authority hoặc CSRF token. | Xem credential transport và filter chain. |
| Browser báo CORS error | Preflight/origin/headers bị từ chối. | Kiểm tra CORS config và OPTIONS flow. |
| Session login chỉ hoạt động trên một pod | Session store/sticky routing không đúng. | Kiểm tra HA, Redis/Spring Session và LB. |
| JWT chỉ hoạt động trên một pod | Khác JWKS cache, issuer config, version hoặc clock. | Kiểm tra từng pod, không mặc định lỗi session. |

Không ghi raw access token, refresh token, `Authorization`, session ID hoặc client secret vào log. Dùng trace ID, endpoint, loại authentication, issuer alias và nguyên nhân lỗi ở mức an toàn.

## 37. Bảng lựa chọn nhanh theo mục tiêu hệ thống

| Mục tiêu | Cách tiếp cận |
| --- | --- |
| REST API cho mobile hoặc M2M | `oauth2ResourceServer`, `STATELESS`, Bearer trong header, `401/403` rõ ràng. |
| JWT API scale nhiều pod | Stateless authentication và JWKS cache có kiểm soát, không cần sticky login session. |
| Opaque API cần trạng thái thu hồi | Stateless + introspection; timeout/cache/revocation policy tách biệt. |
| Browser web app có form login | `IF_REQUIRED` hoặc session policy phù hợp, CSRF và cookie security. |
| Browser muốn tránh giữ access token trong JS | BFF với browser session + server-side token storage; downstream API vẫn Bearer. |
| Cùng ứng dụng có web và API | Nhiều chain, `@Order`, matcher hẹp và fallback bảo vệ mọi URL. |
| Muốn “đăng xuất ngay” trên mọi thiết bị | Cơ chế revocation/session management/token status theo product requirements; `STATELESS` không tự làm. |
| Muốn bảo vệ owner/tenant | Domain authorization, membership và scoped data operations; độc lập session. |

## 38. Quy trình quyết định chính sách quản lý phiên

Trước khi xây một endpoint:

1. **Caller là ai?** Mobile, browser, BFF, service account, CLI?
2. **Credential đi bằng gì?** Authorization header hay cookie tự gửi?
3. **Đường này là OAuth Resource Server hay web login/OAuth Client?**
4. **Có cần nhớ login giữa requests?** Nếu không, `STATELESS`; nếu có, quản lý session riêng.
5. **Ứng dụng có cả web và API không?** Tách SecurityFilterChain và fallback.
6. **CSRF có áp dụng không?** Dựa trên browser credential, không dựa tên session policy.
7. **CORS có cần không?** Cấu hình origin/preflight cho SPA cross-origin.
8. **Expiry/refresh/revoke thế nào?** Định nghĩa lifecycle access token, refresh token và session riêng.
9. **JWT/opaque validation đã có issuer/audience/scope chưa?**
10. **Domain authorization đã xét tenant/owner chưa?**
11. **Async/jobs có cần trusted identity propagation không?**
12. **Đã test request không Bearer sau request có Bearer và cookie web vào API chưa?**

```mermaid
flowchart TD
    A["Request tới hệ thống"] --> B{"Client gửi credential nào?"}
    B -- "Authorization: Bearer" --> C["Resource Server JWT/opaque"]
    C --> D["Xác thực token từng request"]
    D --> E["Không cần login HttpSession: STATELESS"]
    E --> F["Kiểm tra scope, audience, tenant, owner"]
    B -- "Browser session cookie" --> G["Web/BFF login"]
    G --> H["Session policy phù hợp, ví dụ IF_REQUIRED"]
    H --> I["Cookie security, CSRF, logout, timeout"]
    I --> J{"Cần gọi API downstream?"}
    J -- "Có" --> K["BFF gửi access token phù hợp"]
    K --> C
    J -- "Không" --> L["Xử lý web use case theo domain policy"]
```

## 39. Nguyên tắc kết luận

- **Bearer xác thực theo request**: Protected API phải có credential phù hợp trên mỗi lời gọi, không dựa IP hay request trước.
- **`SecurityContext` không đồng nghĩa `HttpSession`**: context có thể tồn tại trong phạm vi request mà API vẫn stateless.
- **`STATELESS` và `NEVER` khác nhau**: `NEVER` có thể dùng session có sẵn, còn `STATELESS` không dùng session để lấy context.
- **Stateless không loại bỏ cache/JWK/introspection hoặc cookie do thành phần khác tạo.**
- **JWT và opaque khác ở cơ chế xác minh**, cả hai đều có thể dùng API stateless.
- **CSRF phụ thuộc cách browser gửi credential**; JWT trong cookie khác Bearer header.
- **BFF có thể stateful, downstream API vẫn stateless**.
- **Logout session không tự revoke Bearer token**; access token expiry, refresh token và web session có lifecycle riêng.
- **Nhiều SecurityFilterChain phải có matcher/fallback rõ**, tránh cookie web vô tình được chấp nhận trong API Bearer-only.
- **Test security ở đúng tầng**: JWT chữ ký thật, no-token request, cookie web, session login/logout, CSRF/CORS và domain authorization.

**Điểm cốt lõi:** `SessionCreationPolicy.STATELESS` là lựa chọn tự nhiên khi **Spring Security Resource Server nhận Bearer access token trên từng HTTP request** và không cần phục hồi authentication từ `HttpSession`. Khi có browser login, cookie hoặc BFF, hãy quản lý phiên tại **đúng đường đi cần session**, giữ CSRF và session lifecycle tương ứng; đừng đánh đồng authentication của Bearer, phiên đăng nhập web, token refresh/revocation và quyền nghiệp vụ.
