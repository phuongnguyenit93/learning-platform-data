# BearerTokenAuthenticationFilter và lấy token từ yêu cầu

Trong một ứng dụng **Spring Security OAuth 2.0 Resource Server chạy trên Servlet stack**, client thường gọi API với access token trong HTTP header:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Một request mang token **chưa tự động được xác thực**. Chuỗi filter cần tìm credential, chuyển nó tới bộ xác thực phù hợp, kiểm tra tính hợp lệ và đưa thông tin đã xác thực vào `SecurityContext` trước khi xét quyền.

**`BearerTokenAuthenticationFilter`** là thành phần xử lý yêu cầu Bearer trong Spring Security Servlet Resource Server. Trách nhiệm chính của filter là **lấy bearer token từ request và bắt đầu quá trình xác thực**. Nó không tự giải mã mọi loại JWT, không tự kiểm tra chữ ký hoặc introspection và không trực tiếp quyết định client có quyền đọc đơn hàng hay không. Các công việc ấy thuộc những thành phần phía sau.

Ví dụ sử dụng xuyên suốt:

- Authorization Server: `https://login.example.com`.
- Resource Server: Orders API ở `https://api.example.com`.
- Resource/audience mong đợi: `orders-api`.
- Quyền đọc đơn hàng: OAuth scope `orders.read`, được ánh xạ thành authority `SCOPE_orders.read`.
- Ứng dụng chạy Spring Boot 3.x / Spring Security 6.x với Servlet/Spring MVC; API và phiên bản cụ thể cần được kiểm tra khi tích hợp.

## 1. Các thành phần của Servlet Security Filter Chain

Trong Servlet, Spring Security được kết nối với Servlet container thông qua `DelegatingFilterProxy` dẫn vào `FilterChainProxy`. `FilterChainProxy` chọn một `SecurityFilterChain` phù hợp với request và thực thi các security filter được cấu hình trong chain đó.

| Thành phần | Nhiệm vụ |
|---|---|
| `DelegatingFilterProxy` | Kết nối chuỗi lọc Servlet với các bean Spring Security. |
| `FilterChainProxy` | Chọn security filter chain đầu tiên khớp request. |
| `SecurityFilterChain` | Xác định những security filter áp dụng cho một nhóm URL. |
| `BearerTokenAuthenticationFilter` | Lấy Bearer token bằng `BearerTokenResolver`; gọi cơ chế xác thực, cập nhật `SecurityContext` khi thành công. |
| `BearerTokenResolver` | Quyết định Bearer token được lấy từ header hoặc nguồn đã cấu hình nào. |
| `BearerTokenAuthenticationToken` | Đối tượng `Authentication` ban đầu, mang chuỗi token **chưa xác thực**. |
| `AuthenticationManager` / `AuthenticationProvider` | Điều phối và thực hiện xác thực token. |
| `JwtDecoder` | Xác minh chữ ký và các claim của JWT access token theo hợp đồng issuer/RS. |
| `OpaqueTokenIntrospector` | Kiểm tra opaque access token thông qua introspection hoặc cơ chế tùy chỉnh phù hợp. |
| `SecurityContextHolder` | Cung cấp `Authentication` đã xác thực của request. |
| `AuthorizationFilter` | Đánh giá quyền được gọi endpoint sau khi đã có authentication phù hợp. |

Bài học này thuộc **Servlet stack**. Ứng dụng **WebFlux** sử dụng `SecurityWebFilterChain` và cơ chế reactive khác; không dùng trực tiếp Servlet `BearerTokenAuthenticationFilter`.

### 1.1. Từ request tới controller

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant F as BearerTokenAuthenticationFilter
    participant R as BearerTokenResolver
    participant M as AuthenticationManager
    participant P as Jwt/opaque Provider
    participant A as AuthorizationFilter
    participant API as API Controller
    C->>F: GET /api/orders, Authorization: Bearer token
    F->>R: resolve(request)
    R-->>F: token hoặc null / lỗi
    alt Có Bearer token
        F->>M: BearerTokenAuthenticationToken
        M->>P: authenticate(...)
        P->>P: JWT verification hoặc introspection
        P-->>M: Authentication đã xác thực
        M-->>F: Authentication đã xác thực
        F->>F: Đặt vào SecurityContext
    else Không có Bearer token
        F->>F: Không tạo Bearer Authentication
    end
    F->>A: Tiếp tục filter chain
    A->>A: Kiểm tra authenticated/scope/authority
    alt Được phép
        A->>API: Chạy controller
    else Không được phép
        A-->>C: 401 hoặc 403 tùy tình huống
    end
```

Sơ đồ diễn tả **quan hệ xử lý** chứ không ràng buộc vị trí tuyệt đối của từng filter. Các filter như CORS, CSRF, Anonymous, ExceptionTranslation có mặt và thứ tự cụ thể tùy cấu hình/phiên bản. Cốt lõi là xác thực Bearer cần diễn ra **trước** bước cấp quyền cho endpoint.

### 1.2. Vì sao phải biết chain nào khớp request?

Khi ứng dụng cấu hình nhiều `SecurityFilterChain`, `FilterChainProxy` chọn **chain đầu tiên có matcher phù hợp**, không lần lượt chạy tất cả.

Ví dụ `/api/**` dùng JWT và `/web/**` dùng session/OIDC login: Bearer filter chỉ được dùng cho request mà chain phù hợp bật `oauth2ResourceServer(...)`. Nếu một chain rộng hơn được đặt trước và khớp `/api/orders`, API có thể không đi qua Bearer filter như kỳ vọng.

## 2. BearerTokenResolver: lấy token từ request

Filter không tự suy ra vị trí credential. Nó gọi:

```java
String token = bearerTokenResolver.resolve(request);
```

Đây là cách diễn đạt nhiệm vụ của interface `BearerTokenResolver`. Kết quả:

- **Có chuỗi token:** chuyển sang xác thực.
- **`null`:** không tìm thấy Bearer credential được chấp nhận, filter để request tiếp tục.
- **`OAuth2AuthenticationException`:** request có lỗi theo quy tắc Bearer, filter xử lý lỗi xác thực.

Spring Security dùng `DefaultBearerTokenResolver` theo mặc định. Nguồn token tiêu chuẩn được bật sẵn là:

```http
Authorization: Bearer ACCESS_TOKEN_VALUE
```

Bearer được mô tả trong **RFC 6750**. Filter không yêu cầu client đưa các claim `sub` hoặc `scope` vào header riêng; claims phải đến từ token/metadata đã được xác minh.

### 2.1. Token trong Authorization header

Ví dụ:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
```

Các phần:

- `Authorization`: tên HTTP header.
- `Bearer`: authentication scheme.
- `ACCESS_TOKEN_VALUE`: credential để đưa đến AuthenticationManager.
- Không thêm dấu nháy tùy ý hoặc tiền tố khác vào giá trị token.

Với Bearer token không ràng buộc người gửi, **ai có token còn hiệu lực đều có thể sử dụng nó** trong phạm vi quyền. Vì vậy luôn dùng TLS/HTTPS, che token trong log và giới hạn scope, audience, thời gian sống.

### 2.2. Mặc định không đọc token từ URL hay form

| Nguồn | Ví dụ | Được bật mặc định? | Nhận xét |
|---|---|---|---|
| Authorization header | `Authorization: Bearer abc` | **Có** | Nguồn chuẩn, dễ tích hợp, ít nguy cơ lọt vào access log hơn URL. |
| URI query parameter | `/orders?access_token=abc` | **Không** | Dễ rò qua log, history, referrer và liên kết chia sẻ. |
| Form-encoded body | `access_token=abc` trong form body | **Không** | Chỉ áp dụng khi đáp ứng các điều kiện giao thức, không nên dùng tùy tiện. |
| Cookie tùy ý | `Cookie: access_token=abc` | **Không** | Cookie-authenticated flow kéo theo các cân nhắc CSRF khác. |
| Header tùy chỉnh | `X-Token: abc` | **Không** | Cần resolver/chính sách riêng; không có hợp đồng chung với OAuth Bearer mặc định. |

`DefaultBearerTokenResolver` có thể được cấu hình bằng:

```java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowFormEncodedBodyParameter(false);
resolver.setAllowUriQueryParameter(false);
```

Hai giá trị `false` trên đã là chính sách mặc định, được viết rõ để nhấn mạnh rằng API chỉ nhận token qua header chuẩn.

**Không bật query token chỉ để sửa một lỗi client.** Trong URL, token dễ bị proxy, CDN, analytics hoặc access logger ghi lại dù HTTP request đã được gửi qua TLS.

### 2.3. Không có token khác với token bị lỗi

Một request hoàn toàn không có Bearer:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
```

thường khiến `resolve()` trả `null`. Filter **không tự tạo xác thực**; nó tiếp tục chain. Nếu endpoint yêu cầu authenticated principal, các bước authorization sẽ từ chối request (thường `401`).

Ngược lại:

```http
Authorization: Bearer TOKEN_SAI
```

có thể được resolver trích xuất hợp lệ về cú pháp nhưng bị decoder/provider từ chối vì signature, issuer, audience hoặc hạn dùng. Đó là **lỗi authentication**, thường `401 invalid_token`.

Header không đúng cú pháp Bearer hoặc cung cấp nhiều kênh credential mâu thuẫn có thể tạo `invalid_request` và phản hồi lỗi cú pháp tương ứng. Không nên mặc định tất cả lỗi Bearer đều ra `401`.

## 3. Diễn biến bên trong BearerTokenAuthenticationFilter

Luồng có thể diễn giải thành các bước:

1. Filter nhận `HttpServletRequest` và `HttpServletResponse`.
2. Gọi `BearerTokenResolver.resolve(request)`.
3. Nếu không có token, gọi `filterChain.doFilter(...)` mà không xác thực Bearer.
4. Nếu resolver báo lỗi, chuyển lỗi sang cơ chế xử lý xác thực.
5. Nếu có token, tạo `BearerTokenAuthenticationToken`.
6. Chọn `AuthenticationManager` và gọi `authenticate(...)`; Spring cũng có thể dùng `AuthenticationManagerResolver<HttpServletRequest>`.
7. Nếu provider thành công, đưa `Authentication` đã xác thực vào `SecurityContext` cho request và tiếp tục chain.
8. Nếu provider thất bại, xóa context xác thực liên quan và chạy failure handler/entry point.

Mã giả sau **không phải mã triển khai chính thức của Spring**, chỉ giúp hiểu trách nhiệm:

```java
String bearer = bearerTokenResolver.resolve(request);

if (bearer == null) {
    chain.doFilter(request, response);
    return;
}

try {
    Authentication candidate =
        new BearerTokenAuthenticationToken(bearer);

    Authentication authenticated =
        authenticationManager.authenticate(candidate);

    SecurityContext context = createEmptyContext();
    context.setAuthentication(authenticated);
    setCurrentSecurityContext(context);
    saveContextIfConfigured(context, request, response);

    chain.doFilter(request, response);
} catch (AuthenticationException ex) {
    clearContext();
    authenticationFailureHandler.onAuthenticationFailure(
        request, response, ex
    );
}
```

Trong code thực tế còn có `AuthenticationDetailsSource`, `SecurityContextHolderStrategy` và `SecurityContextRepository`. Chỉ tin `Authentication` do provider trả về sau khi xác minh token, không tin object candidate.

### 3.1. BearerTokenAuthenticationToken là đầu vào

`new BearerTokenAuthenticationToken(token)` tạo `Authentication` **chưa authenticated**. Nó giữ token để provider quyết định tính hợp lệ. Trạng thái này không tự mang các authority như `SCOPE_orders.read`.

Với JWT:

```text
BearerTokenAuthenticationToken
  → AuthenticationManager
  → JwtAuthenticationProvider
  → JwtDecoder / JWT validators
  → JwtAuthenticationToken
  → SecurityContext
```

Với opaque token:

```text
BearerTokenAuthenticationToken
  → AuthenticationManager
  → OpaqueTokenAuthenticationProvider
  → OpaqueTokenIntrospector
  → BearerTokenAuthentication
  → SecurityContext
```

Cả hai dùng chung việc **trích xuất Bearer**, nhưng kiểm tra token ở các provider khác nhau.

### 3.2. JWT validation và mapping authorities

Với JWT, `JwtDecoder` cần xác minh chữ ký bằng khóa issuer đã tin cậy, thời hạn (`exp`, `nbf`), `iss`, `aud` và các claim/token profile thuộc hợp đồng giữa AS và RS. Chữ ký hợp lệ chưa đủ: token cấp cho API khác phải bị từ chối vì sai `aud`.

`JwtAuthenticationConverter` chuyển scope thành authorities. Với mapping mặc định thường gặp:

```text
JWT claim:    "scope": "orders.read orders.write"
Authorities:  SCOPE_orders.read
              SCOPE_orders.write
```

Nếu issuer biểu diễn scope/role theo cách khác, cần converter phù hợp. `BearerTokenAuthenticationFilter` không trực tiếp hiểu quyền nghiệp vụ `orders.read`.

### 3.3. Opaque token introspection

Nếu access token là chuỗi opaque, `OpaqueTokenAuthenticationProvider` dùng `OpaqueTokenIntrospector` kiểm tra với Authorization Server (hoặc cách tùy chỉnh tương ứng). Metadata trả về có thể gồm `active`, scope, subject, expiration và các thuộc tính khác theo khả năng của server.

Resource Server vẫn phải xét **đích nhận/audience và quyền** phù hợp với hợp đồng, không suy ra rằng token `active=true` sẽ được mọi API chấp nhận. Việc introspection qua mạng còn cần thiết kế khả dụng, timeout, cache và bảo vệ credential introspection.

### 3.4. Khi một API phục vụ nhiều issuer

Có trường hợp filter chọn manager bằng `AuthenticationManagerResolver<HttpServletRequest>` theo tenant hoặc issuer đã cho phép. Điều này hữu ích khi mỗi Authorization Server có issuer, JWKS và policy khác nhau.

**Không tin dữ liệu chưa xác minh chỉ vì nó nằm trong header/payload JWT.** Resolver có thể sử dụng thông tin ấy để định tuyến sơ bộ nhưng phải chỉ chọn từ tập issuer/tenant đã tin cậy; manager được chọn vẫn phải thực sự xác minh issuer, chữ ký, audience và quyền.

## 4. SecurityContext và trạng thái request

Sau xác thực thành công, Spring Security tạo hoặc đặt `SecurityContext` chứa `Authentication` đã được xác thực cho request hiện tại. Các bước sau trong chain, đặc biệt `AuthorizationFilter`, sử dụng thông tin đó.

| Loại access token | Authentication sau xác thực | Principal thường gặp |
|---|---|---|
| JWT | `JwtAuthenticationToken` | `Jwt` đã được decoder xác minh |
| Opaque | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` |

Ví dụ controller chỉ dành cho JWT:

```java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentSubjectController {

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }
}
```

Ví dụ giả định endpoint được bảo vệ và issuer phát hành `sub`. Nếu Resource Server chuyển sang opaque token, kiểu principal có thể khác, nên không còn giả định `@AuthenticationPrincipal Jwt` là phù hợp.

### 4.1. Bearer authentication và HttpSession

Trong API dùng bearer, thông thường client gửi access token **mỗi lần gọi**. Điều này khác việc trình duyệt có session cookie và server lưu trạng thái đăng nhập truyền thống.

Spring Security có tích hợp `SecurityContextRepository`; tuy nhiên việc filter có cơ chế lưu context không đồng nghĩa mọi Bearer request sẽ tự tạo `HttpSession`. Để API chạy stateless, cấu hình session policy và filter chain phù hợp; nếu cùng ứng dụng có cả session/cookie và bearer, thiết kế ranh giới rõ ràng.

## 5. Cấu hình Resource Server với JWT

Giả sử dự án dùng **Spring Boot 3.x, Spring Security 6.x, Spring MVC**.

### 5.1. Gradle dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

### 5.2. application.yml

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

`issuer-uri` cung cấp nguồn issuer/JWKS tin cậy theo discovery thích hợp. `audiences` được các phiên bản Spring Boot 3.x có hỗ trợ thuộc tính này dùng để kiểm tra audience; nếu dự án không hỗ trợ, cần `OAuth2TokenValidator<Jwt>` tùy chỉnh. Với access token có hồ sơ riêng (như RFC 9068), vẫn phải xác minh token type và các claim bắt buộc theo hợp đồng.

### 5.3. SecurityFilterChain

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurity {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {

        DefaultBearerTokenResolver bearerResolver =
                new DefaultBearerTokenResolver();
        bearerResolver.setAllowFormEncodedBodyParameter(false);
        bearerResolver.setAllowUriQueryParameter(false);

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(bearerResolver)
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Cấu hình:

- Áp dụng chain cho `/api/**`.
- Đọc token qua `Authorization: Bearer ...`; query và form body bị tắt.
- Dùng JWT decoder/provider để xác minh access token.
- Dùng authorities để quyết định quyền gọi các endpoint.
- Xem API theo mô hình không dựa vào session để nhận diện người dùng.

**Các URL ngoài `/api/**`** cần chain khác hoặc fallback policy. Lệnh `anyRequest().authenticated()` ở chain này chỉ áp dụng trong phạm vi `securityMatcher` tương ứng.

### 5.4. Tại sao không đăng ký Bearer filter bằng FilterRegistrationBean?

Cấu hình `oauth2ResourceServer(...)` **đã thêm BearerTokenAuthenticationFilter vào Spring Security chain**. Nếu tự đăng ký cùng filter ở Servlet container hoặc tự add thêm trong `HttpSecurity`, nó có thể chạy sai thứ tự, nằm ngoài `FilterChainProxy` hoặc xử lý một request lặp hai lần.

Cách mở rộng chuẩn là cấu hình `BearerTokenResolver`, `JwtDecoder`, `OpaqueTokenIntrospector`, converter hoặc `AuthenticationManagerResolver` theo yêu cầu.

## 6. Đổi nơi lấy token khi có gateway

### 6.1. Đổi sang header Proxy-Authorization

`DefaultBearerTokenResolver` có phương thức `setBearerTokenHeaderName(String)`. Ví dụ:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION);
```

Sau đó truyền resolver cho DSL:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .jwt(Customizer.withDefaults())
)
```

Thiết kế này chỉ phù hợp khi hệ thống gateway/proxy có hợp đồng rõ ràng. Nếu backend công khai trực tiếp, client có thể tự gửi header mà gateway dự kiến kiểm soát. Gateway phải xóa hoặc ghi đè header giả mạo từ client, kiểm soát đường truyền đến backend và đảm bảo API vẫn xác minh token đúng.

### 6.2. Custom BearerTokenResolver

Khi cần thêm logic đặc biệt, có thể triển khai interface:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

public final class RestrictedBearerResolver implements BearerTokenResolver {
    private final BearerTokenResolver delegate =
            new DefaultBearerTokenResolver();

    @Override
    public String resolve(HttpServletRequest request) {
        // Minh họa một extension có thể kiểm soát.
        // Tại đây giữ nguyên hành vi chuẩn.
        return delegate.resolve(request);
    }
}
```

Khi mở rộng để đọc header khác, phải quy định trường hợp request mang **hai credential** ở hai nguồn, tránh tự chọn một token tùy tiện. Không lấy token từ URL, cookie hoặc header “nội bộ” nếu chưa có threat model và trust boundary rõ ràng.

Custom resolver **chỉ có quyền quyết định token được lấy ở đâu**; không nên kiểm tra quyền bằng cách đọc claim từ chuỗi chưa xác minh hay trả về object đã authenticated giả.

## 7. Request thiếu, sai và đủ quyền

Giả sử `GET /api/orders/42` yêu cầu `SCOPE_orders.read`.

| Tình huống | Điều xảy ra | Kết quả thường gặp |
|---|---|---|
| Không có Authorization header | Filter không tìm thấy Bearer; endpoint cần authentication | `401 Unauthorized` |
| Header Bearer có token giả/sai chữ ký | Resolver nhận chuỗi; provider từ chối | `401` / `invalid_token` |
| Header Bearer có JWT sai issuer/audience/hết hạn | Decoder/validator từ chối | `401` / `invalid_token` |
| Header Bearer hợp lệ, thiếu `orders.read` | Xác thực thành công; authorization từ chối | `403 Forbidden`, có thể `insufficient_scope` |
| Bearer hợp lệ, scope đủ | Qua kiểm tra route; service còn kiểm tra quyền trên đơn hàng cụ thể | Có thể `200` nếu được phép |
| Token chỉ nằm trong query `?access_token=...` | Resolver mặc định không đọc | Với endpoint bảo vệ, thường `401` |
| Endpoint `permitAll` nhưng request mang Bearer **không hợp lệ** | Filter vẫn có thể thử xác thực trước bước `permitAll` | Có thể trả `401` |

Ví dụ gọi API đúng:

```bash
curl -i \
  -H "Authorization: Bearer ACCESS_TOKEN_VALUE" \
  https://api.example.com/api/orders/42
```

Không gửi refresh token hoặc ID token vào Orders API chỉ vì chúng cũng là các chuỗi token do Authorization Server tạo ra. **Access token** mới là credential dành cho resource server.

### 7.1. permitAll không buộc filter bỏ qua token

Điểm này rất dễ gây nhầm: `permitAll()` cho biết **authorization rule** không đòi authenticated principal để tới endpoint. Nó **không ngăn các authentication filter chạy** trước đó.

Nếu gọi `/api/public/info` không có bearer token, filter bỏ qua và request được cho phép. Nếu cố tình thêm token sai, Bearer filter có thể trả lỗi trong bước authentication, dù authorization rule sau đó là `permitAll`.

Nếu có yêu cầu endpoint công khai phải bỏ qua xử lý Bearer ngay cả khi header lỗi, cần thiết kế filter chain hoặc matcher riêng một cách có chủ đích. Không giải quyết bằng cách “nuốt hết lỗi token” trong toàn API.

## 8. BearerTokenAuthenticationEntryPoint và lỗi HTTP

Resource Server có thể dùng `BearerTokenAuthenticationEntryPoint` để gửi challenge theo RFC 6750:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Với access token không hợp lệ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Một request sai cú pháp theo Bearer specification có thể nhận `invalid_request` và mã trạng thái lỗi tương ứng. Mã chính xác phụ thuộc `OAuth2Error` và cấu hình entry point/failure handler; không nên coi mọi lỗi đều là `401`.

Khi token được xác thực nhưng không đủ scope, `BearerTokenAccessDeniedHandler` hỗ trợ phản hồi thiếu quyền, ví dụ:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

**Quy tắc thực hành:**

- **401:** chưa xác thực hoặc credential không hợp lệ.
- **403:** đã xác thực hợp lệ nhưng thiếu quyền cho hành động.
- **400 / invalid_request:** một số request Bearer sai cú pháp/nguồn theo RFC.

Không trả raw token, claims nhạy cảm, secret, stack trace hay chi tiết cấu hình khóa trong lỗi HTTP.

## 9. JWT và opaque token: cùng Bearer filter

### 9.1. JWT

Ví dụ cấu hình JWT:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
```

`BearerTokenAuthenticationFilter` trích xuất token, sau đó `JwtAuthenticationProvider` gọi `JwtDecoder` để xác minh. JWT thường được xác thực bằng chữ ký và các claim cục bộ dựa trên khóa đã tin cậy từ JWKS. Nếu JWT còn hiệu lực, việc AS thu hồi token hoặc thay đổi quyền không nhất thiết được RS nhận biết ngay trừ khi có cơ chế bổ sung.

### 9.2. Opaque token

Ví dụ cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: CHANGE_ME_USING_SECRET_MANAGER
```

DSL Java:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Credential introspection phải được lấy từ biến môi trường hoặc secret manager; ví dụ `CHANGE_ME_USING_SECRET_MANAGER` chỉ là placeholder, **không được đưa secret thật vào repository**.

Filter vẫn sử dụng resolver Bearer tương tự. Sự khác nhau là provider dùng `OpaqueTokenIntrospector` để xác minh và trả metadata, sau đó resource server ánh xạ quyền phù hợp. Khi chuyển giữa JWT và opaque token, cần thay đổi cơ chế xác minh, **không nhất thiết phải thay đổi header Bearer mà client gửi**.

## 10. Multi-chain và matcher

Một ứng dụng có thể tách API bearer khỏi các endpoint khác:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultipleSecurityChains {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth ->
                auth.anyRequest().denyAll()
            )
            .build();
    }
}
```

Đây là **ví dụ bảo vệ API và từ chối tất cả URL khác**, chưa phải cấu hình giao diện đăng nhập hoàn chỉnh. Nếu có `/web/**` với session hoặc OIDC login, tạo chain và callback phù hợp. `@Order` ảnh hưởng thứ tự thử matcher; chain quá rộng đặt trước `/api/**` có thể khiến Bearer filter không bao giờ chạy ở endpoint dự định.

## 11. CORS, CSRF và request trước khi vào API

### 11.1. CORS preflight không mang Bearer như request chính

Frontend gọi API khác origin với header `Authorization` có thể làm trình duyệt gửi preflight:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflight `OPTIONS` thông thường không có token Bearer. CORS cần được xử lý đúng trước khi security authorization chặn request. Spring có thể tích hợp:

```java
http.cors(Customizer.withDefaults());
```

với `CorsConfigurationSource` phù hợp, giới hạn origins, methods, headers và credentials theo nhu cầu. Không bật origin wildcard một cách tùy tiện khi có cookie/credential.

### 11.2. CSRF với API Bearer

Một API chỉ xác thực bằng bearer token trong `Authorization` header do client chủ động gắn vào thường có mô hình CSRF khác cookie session, bởi browser không tự động gửi access token từ JavaScript storage như cách tự gửi cookie. Tuy nhiên nếu ứng dụng đồng thời sử dụng cookie để xác thực request thay đổi trạng thái thì vẫn cần đánh giá CSRF đầy đủ.

Đừng tắt CSRF máy móc chỉ vì có `oauth2ResourceServer()`; hãy thiết kế trên cơ sở cơ chế xác thực thực tế của từng SecurityFilterChain.

### 11.3. Proxy làm mất Authorization header

Nếu client gửi bearer nhưng backend thấy chưa authenticated:

- Proxy/gateway có thể đã xóa header `Authorization`.
- Proxy có thể đổi sang header khác không được resolver đọc.
- Header gửi tới một chain không bật Resource Server.
- Resolver tùy chỉnh có thể trả `null` do điều kiện sai.

Cần kiểm tra đường đi của header trong môi trường test, nhưng **không log raw bearer token**. Có thể log kết quả “có header/không có header” hoặc mã request ID mà không ghi credential.

## 12. Sử dụng Authentication trong controller và service

Sau khi xác thực, controller có thể nhận `Authentication`:

```java
package com.example.orders.api;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
class IdentityController {

    @GetMapping("/api/whoami")
    Map<String, String> whoami(Authentication authentication) {
        return Map.of("principal", authentication.getName());
    }
}
```

`Authentication.getName()` không mặc định là email hay tài khoản người dùng trong database. Với JWT mặc định có thể dựa vào `sub`; trong `client_credentials`, subject thường đại diện client/application chứ không phải người dùng cuối. Không dùng tên này một cách mù quáng để cấp quyền dữ liệu.

Quy tắc quyền route:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

chỉ chứng minh client/subject có quyền **gọi chức năng đọc đơn hàng**. Tầng service vẫn phải kiểm tra chủ sở hữu, tenant, trạng thái đơn và mọi điều kiện nghiệp vụ khác trước khi trả bản ghi cụ thể.

## 13. Kiểm thử việc lấy token và xác thực

Các trường hợp cơ bản:

| Request | Kết quả theo luồng xử lý |
|---|---|
| Không có header trên endpoint công khai | Bearer filter bỏ qua; `permitAll` có thể cho phép. |
| Không có header trên endpoint bảo vệ | Bearer filter bỏ qua; authorization thường trả `401`. |
| Bearer header với JWT hợp lệ | Resolver đọc token, provider xác minh, context chứa `JwtAuthenticationToken`. |
| Bearer header với JWT sai chữ ký/issuer/audience/hết hạn | Provider từ chối; thường `401`. |
| Bearer token đúng nhưng thiếu scope | Authentication thành công; authorization trả `403`. |
| Token đặt trong `?access_token=...` | Resolver mặc định không đọc từ query. |
| Endpoint `permitAll` với Bearer token lỗi | Vẫn có thể nhận `401` do Bearer filter chạy trước rule. |
| Browser preflight `OPTIONS` | CORS phải xử lý đúng để request chính được gửi. |

### 13.1. Phân biệt test authorization với test extraction

Trong Spring Security Test, MockMvc `jwt()` có thể đặt một principal đã xác thực để kiểm tra quyền:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void userWithoutReadScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/orders/42").with(jwt()))
        .andExpect(status().isForbidden());
}
```

Ví dụ cần `spring-security-test` và test setup phù hợp; endpoint giả định yêu cầu `SCOPE_orders.read`. `jwt()` trong Spring Security Test tạo authentication thử nghiệm, hữu ích để kiểm tra **authorization** nhưng **không chứng minh header được BearerTokenAuthenticationFilter trích xuất thật hoặc JWT signature đã được verify**.

Muốn kiểm tra filter/extraction/decoder, tạo integration test gửi request mang header `Authorization: Bearer ...` tới filter chain thật, với issuer/JWKS hoặc `JwtDecoder` kiểm soát trong test, rồi thử missing header, malformed header, token sai chữ ký, token sai audience và token đủ scope.

## 14. Chẩn đoán 401 và 403 theo từng lớp

Khi gặp lỗi, nên xét theo thứ tự:

**(1) Request có vào đúng SecurityFilterChain không?** Kiểm tra `securityMatcher`, thứ tự `@Order` và đường dẫn thực tế. Một chain khác có thể đã khớp trước.

**(2) BearerTokenResolver có đọc được token không?** Kiểm tra header chuẩn, proxy forwarding, các nguồn token bị tắt mặc định và lỗi cú pháp. Không hiển thị credential thật trong log.

**(3) Token đã được provider xác minh chưa?** Với JWT, kiểm tra `iss`, `aud`, chữ ký, thuật toán, thời hạn và token profile. Với opaque, kiểm tra introspection, credential của RS và metadata.

**(4) Đã xác thực nhưng thiếu quyền gì?** Kiểm tra mapping `scope`/`scp` sang `SCOPE_*`, converter role, policy endpoint và quyền nghiệp vụ.

| Triệu chứng | Lớp cần tập trung |
|---|---|
| Có token ở client nhưng API nói chưa authenticated | Chain matcher, proxy, resolver |
| `401 invalid_token` dù payload JWT đọc được | Decoder/issuer/audience/signature/expiration |
| `403` dù token được chấp nhận | Authorities, scope, phân quyền đối tượng |
| `permitAll` nhưng request kèm token sai vẫn bị từ chối | Authentication filter chạy trước authorization |
| Token query không hoạt động | Mặc định `DefaultBearerTokenResolver` không bật query token |
| `@AuthenticationPrincipal Jwt` không có giá trị với opaque token | Khác kiểu Authentication/principal |

## 15. Những quy tắc bảo mật cốt lõi

1. **Dùng HTTPS** và giữ `Authorization: Bearer` làm nguồn token mặc định.
2. **Không đưa token vào URL** hoặc ghi nguyên credential vào log, tracing, crash report.
3. **Không tự decode rồi tin claims**; chỉ cấp quyền theo authentication do provider đã xác minh.
4. **Kiểm tra issuer, audience, signature, expiration và quyền**; token hợp lệ ở API A không được tự dùng ở API B.
5. **Không dùng ID token, refresh token hoặc authorization code** thay cho access token để gọi Resource Server.
6. **Chú ý chain matcher**: token chỉ được Bearer filter xử lý trong chain đã bật Resource Server.
7. **Không tự đăng ký filter trùng** bên ngoài `FilterChainProxy` khi DSL đã cài nó.
8. **Không tùy tiện bật query/form token**; nếu cần tương thích đặc biệt phải có chính sách rõ.
9. **Phân quyền ở cả route và đối tượng dữ liệu**: scope đủ chưa chắc được đọc mọi đơn hàng.
10. **Phân biệt 401 với 403**: token thiếu/sai là xác thực; token đúng nhưng quyền thiếu là phân quyền.

## 16. Ghi nhớ luồng Servlet Bearer

```text
HTTP request: Authorization: Bearer <access_token>
       |
       v
Servlet SecurityFilterChain
       |
       v
BearerTokenAuthenticationFilter
       |
       +--> BearerTokenResolver.resolve(request)
               |
               +--> null: tiếp tục chain (chưa authenticated)
               |
               +--> lỗi cú pháp: failure handler / entry point
               |
               +--> token: BearerTokenAuthenticationToken
                              |
                              v
                       AuthenticationManager
                              |
                 +------------+-------------+
                 |                          |
         JwtAuthenticationProvider   OpaqueTokenAuthenticationProvider
                 |                          |
             JwtDecoder             OpaqueTokenIntrospector
                 |                          |
                 +-----------+--------------+
                             |
                    Authentication hợp lệ
                             |
                        SecurityContext
                             |
                       AuthorizationFilter
                             |
                  đủ quyền --> Controller
                  thiếu quyền --> 403
```

Khi phân tích request ở Spring Security Servlet Resource Server, hãy kiểm tra lần lượt **chain phù hợp → token extraction → token authentication → endpoint authorization**. `BearerTokenAuthenticationFilter` là mắt xích biến bearer credential trong HTTP request thành đầu vào xác thực; các lớp phía sau mới xác định token có hợp lệ và request có đủ quyền hay không.
