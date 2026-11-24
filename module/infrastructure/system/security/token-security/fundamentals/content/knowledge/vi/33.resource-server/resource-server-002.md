# BearerTokenAuthenticationFilter trong Spring Security Resource Server

## 1. BearerTokenAuthenticationFilter giải quyết vấn đề gì?

Trong OAuth 2.0/OIDC, **authorization server (AS)** phát hành token, **client** mang **access token** tới API và **resource server (RS)** xác minh token trước khi cấp quyền truy cập. Với ứng dụng Java dùng **Spring Security Servlet**, lớp **BearerTokenAuthenticationFilter** là cầu nối giữa HTTP request chứa bearer token và hệ thống xác thực Spring Security.

Một request điển hình:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

**Bearer token** có nghĩa là bên nắm được giá trị token có thể sử dụng nó trong phạm vi hiệu lực và quyền đã cấp. Filter đọc credential từ request, giao cho **AuthenticationManager** xác thực rồi đặt kết quả vào **SecurityContext**. Các thành phần authorization phía sau quyết định principal đã xác thực có được truy cập endpoint hoặc đối tượng dữ liệu cụ thể hay không.

Điểm cần nhớ ngay từ đầu:

- **Filter không phát hành token**, không xử lý login/password và không thực hiện refresh token grant.
- **Filter không tự giải mã/kiểm tra chữ ký JWT**; việc này thuộc provider và decoder.
- **Filter không tự quyết định quyền nghiệp vụ**; authorization rules và service kiểm tra điều đó.
- **JWT, opaque token** là hai định dạng/kiểu kiểm tra access token khác nhau, nhưng đều có thể được đưa vào pipeline bearer.
- **Refresh token** chỉ nên gửi đến token endpoint của AS; **OIDC ID token** không mặc nhiên là access token dành cho API.
- **Bearer token bị đánh cắp có thể bị replay** nếu chưa hết hiệu lực và không có ràng buộc bổ sung.

Bài học thuộc chương **Resource server** trong module về mô hình tin cậy, JWT/opaque/access/refresh token, claims, scope, audience, lưu trữ, thu hồi và phòng chống token theft/replay. Phạm vi lớp được đề cập là **Spring Security Servlet**, không phải pipeline WebFlux reactive.

## 2. Vị trí trong SecurityFilterChain

Spring Security sử dụng **FilterChainProxy** để chọn một **SecurityFilterChain** theo HTTP request. Khi cấu hình **oauth2ResourceServer**, Spring Security đưa khả năng xác thực bearer token vào chain thích hợp. Các filter khác vẫn xử lý SecurityContext, CORS, CSRF, exception và authorization tùy cấu hình.

~~~mermaid
flowchart TD
    A[HTTP request vào API] --> B[FilterChainProxy]
    B --> C[SecurityFilterChain áp dụng]
    C --> D[BearerTokenAuthenticationFilter]
    D --> E{Có bearer token?}
    E -- Không --> F[Đi tiếp với request chưa xác thực]
    E -- Có --> G[BearerTokenAuthenticationToken]
    G --> H[AuthenticationManager]
    H --> I{Provider xác thực thành công?}
    I -- Không --> J[Failure handler / AuthenticationEntryPoint]
    I -- Có --> K[Đưa Authentication vào SecurityContext]
    F --> L[AuthorizationFilter / Method Security]
    K --> L
    L --> M{Có quyền truy cập?}
    M -- Không --> N[401 hoặc 403 theo tình huống]
    M -- Có --> O[Controller và business service]
~~~

Sơ đồ thể hiện thứ tự logic cốt lõi, không phải liệt kê đầy đủ vị trí từng filter của mọi phiên bản.

| Thành phần | Trách nhiệm |
|---|---|
| **BearerTokenAuthenticationFilter** | Nhận token, yêu cầu xác thực, công bố Authentication |
| **BearerTokenResolver** | Trích bearer token từ HTTP request |
| **BearerTokenAuthenticationToken** | Đóng gói raw token thành authentication request |
| **AuthenticationManager** | Điều phối xác thực, thường qua provider |
| **JwtAuthenticationProvider** | Xác thực access token JWT qua JwtDecoder |
| **OpaqueTokenAuthenticationProvider** | Xác thực opaque token qua OpaqueTokenIntrospector |
| **SecurityContextHolder** | Cung cấp Authentication cho phần còn lại của request |
| **AuthorizationFilter / @PreAuthorize** | Kiểm tra quyền truy cập endpoint và phương thức |
| **AuthenticationEntryPoint / AccessDeniedHandler** | Chuyển lỗi xác thực/phân quyền thành HTTP response |

**Authentication** trả lời câu hỏi “credential này có hợp lệ và đại diện cho ai?”, còn **authorization** trả lời “người/ứng dụng đó được làm gì?”.

## 3. Luồng xử lý chi tiết của BearerTokenAuthenticationFilter

### 3.1. Trích bearer token từ request

Filter gọi một **BearerTokenResolver**. Cách chuẩn theo RFC 6750 là:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

Nếu **không tìm thấy token**, filter thường cho request đi tiếp. Điều đó hợp lý vì một endpoint public có thể không yêu cầu đăng nhập. Nếu endpoint đòi authentication, lớp authorization phía sau sẽ từ chối.

Nếu header có bearer token **sai định dạng**, nhiều cách trình credential mâu thuẫn hoặc vi phạm quy tắc resolver, hệ thống có thể ném **OAuth2AuthenticationException**. Đây khác với tình huống đơn giản là không có token.

### 3.2. Tạo và gửi authentication request

Sau khi lấy raw token, filter tạo:

~~~text
BearerTokenAuthenticationToken(rawAccessToken)
              |
              v
AuthenticationManager.authenticate(authenticationRequest)
~~~

Ban đầu đây là **Authentication chưa được xác thực**. Filter không đọc claims rồi tự đặt principal. Nó để provider được cấu hình quyết định liệu bearer credential có hợp lệ hay không.

Trong hệ thống có nhiều issuer/tenant, có thể dùng **AuthenticationManagerResolver<HttpServletRequest>** để chọn manager. Cần bảo đảm chỉ lựa chọn giữa những issuer/provider đã được tin cậy; không tải khóa của issuer tùy ý lấy từ chuỗi token chưa xác thực.

### 3.3. Provider xác thực token

Với JWT, luồng đi qua **JwtAuthenticationProvider** và **JwtDecoder**; với opaque token, qua **OpaqueTokenAuthenticationProvider** và **OpaqueTokenIntrospector**. Provider trả về một Authentication đã xác thực cùng principal/authorities hoặc ném lỗi.

### 3.4. Thiết lập SecurityContext

Khi thành công, filter tạo SecurityContext, đặt Authentication và cập nhật **SecurityContextHolderStrategy** cho request. Những lớp phía sau có thể truy cập danh tính, claims và authorities.

Với API **stateless**, việc Authentication có mặt trong SecurityContext **không có nghĩa** Spring Security tự tạo một HTTP session lâu dài. Request tiếp theo phải gửi token của riêng nó. Tùy phiên bản và cấu hình, filter có thể phối hợp với **SecurityContextRepository** để lưu context trong phạm vi request; điều này cần phân biệt với lưu session lâu dài.

Khi xác thực thất bại, cơ chế xử lý lỗi làm sạch context và trả response thích hợp, tránh để controller sử dụng một Authentication không hợp lệ.

### 3.5. Kiểm tra phân quyền

Ví dụ JWT đã được xác thực chứa:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1795403600
}
~~~

Thông thường Spring Security chuyển scope thành authority **SCOPE_orders:read**. Rule cho phép GET với authority này, nhưng POST yêu cầu **SCOPE_orders:write** có thể nhận **403 Forbidden**.

Quan trọng hơn, quyền **orders:read** không tự cho phép đọc mọi đơn hàng: service vẫn phải kiểm tra user-123 có được đọc order 42 hay không.

## 4. JWT access token và JwtAuthenticationProvider

**JWT access token** có claims nằm trong token, thường được ký bằng JWS. Filter vẫn chỉ lấy bearer value; provider mới xác minh token.

~~~text
HTTP Authorization: Bearer JWT
           |
           v
BearerTokenAuthenticationFilter
           |
           v
JwtAuthenticationProvider
           |
           v
JwtDecoder (ví dụ NimbusJwtDecoder)
  - kiểm tra chữ ký bằng khóa issuer tin cậy
  - thuật toán ký được cho phép
  - exp, nbf và thời gian
  - issuer, audience, token profile theo chính sách
           |
           v
JwtAuthenticationToken
           |
           v
SecurityContext
~~~

### 4.1. Những validator quan trọng

| Kiểm tra | Câu hỏi cần trả lời | Hậu quả khi bỏ qua |
|---|---|---|
| **Signature** | Chữ ký khớp khóa của issuer tin cậy? | Có thể nhận JWT giả |
| **Algorithm/key** | Thuật toán và key type được cấu hình chấp nhận? | Algorithm/key confusion hoặc nhận khóa không tin cậy |
| **iss** | Đúng nhà phát hành được phép cho API? | Issuer confusion, token từ IdP lạ được tin |
| **aud** | Token được cấp cho resource server hiện tại? | Token dùng cho API khác được chấp nhận |
| **exp / nbf** | Token còn hiệu lực về thời gian? | Chấp nhận token hết hạn/chưa có hiệu lực |
| **token type** | Đây là access token phù hợp? | ID token hoặc refresh token bị dùng sai |
| **scope/authorities** | Quyền có đủ cho hành động? | Cấp quyền quá rộng |
| **tenant/resource ownership** | Principal được truy cập đúng dữ liệu? | Truy cập dữ liệu tenant/người dùng khác |
| **revocation/binding nếu có** | Token đã bị thu hồi hoặc bị giới hạn bên gửi? | Token lộ có thể tiếp tục bị sử dụng |

Đặc biệt, **đừng giả định audience sẽ luôn được kiểm tra đúng chỉ vì đã cấu hình issuer-uri**. API phải định nghĩa audience đích và bảo đảm có validator thực thi.

### 4.2. Chọn đúng khóa ký

Header JWT có thể có **kid**. Giá trị đó chỉ gợi ý khóa trong một **JWKS thuộc issuer tin cậy**, không phải định danh khóa toàn cầu.

~~~text
Đúng:
  trustedIssuer -> trustedJwksUri -> chọn key theo kid -> verify

Sai:
  đọc jku/x5u/iss chưa xác thực -> tải khóa tùy ý -> verify
~~~

Không cho token tự lựa chọn endpoint xác minh nó. Khi có nhiều issuer, cache nên gắn với issuer và tập khóa tương ứng, tránh chỉ dùng kid.

### 4.3. Thu hồi token JWT

Resource server có thể xác minh chữ ký JWT độc lập, không cần gọi AS mỗi request. Điều đó hiệu quả nhưng có nghĩa **token đã cấp vẫn có thể được chấp nhận tới exp** sau logout hoặc thu hồi phía AS nếu không có denylist, introspection hay cơ chế trạng thái bổ sung. Access token ngắn hạn và giới hạn audience/scope giúp thu hẹp tác động.

## 5. Opaque token và OpaqueTokenAuthenticationProvider

**Opaque access token** là chuỗi không chứa claims mà RS có thể tự giải mã theo định dạng chuẩn. Resource server thường xác thực bằng cách gọi **OAuth 2.0 Token Introspection (RFC 7662)** đến một endpoint AS được tin cậy.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <SERVICE_AUTHENTICATION>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
~~~

Phản hồi minh họa:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-portal",
  "scope": "orders:read",
  "aud": ["orders-api"],
  "exp": 1795403600
}
~~~

Đây chỉ là ví dụ; **không phải AS nào cũng trả đầy đủ aud, iss, sub, exp** trong introspection response. Resource server phải xác định chính xác AS đáng tin cậy, scope và ràng buộc resource/tenant thích hợp theo giao thức và metadata thực tế.

~~~text
BearerTokenAuthenticationToken
         |
         v
OpaqueTokenAuthenticationProvider
         |
         v
OpaqueTokenIntrospector
   - gọi endpoint của AS tin cậy
   - xác minh phản hồi và active
   - lấy metadata/authorities
         |
         v
BearerTokenAuthentication
         |
         v
SecurityContext
~~~

**active=false** nghĩa token không được chấp nhận. **active=true** là điều kiện cần, nhưng chưa thay việc kiểm tra **audience/resource, scope, client/issuer/tenant** theo chính sách. Khi introspection endpoint lỗi, resource server không nên mặc định cho qua.

| Đặc tính | JWT access token | Opaque access token |
|---|---|---|
| Xác minh điển hình | JwtDecoder và JWKS | OpaqueTokenIntrospector |
| Claims | Nằm trong JWT | Do introspection hoặc nguồn tin cậy cung cấp |
| Gọi AS mỗi request | Không bắt buộc nếu verify cục bộ | Thường có, trừ khi dùng cache/phương án khác |
| Thu hồi gần tức thời | Cần cơ chế trạng thái bổ sung | Có thể phản ánh qua introspection; phụ thuộc cache |
| Authentication mặc định | JwtAuthenticationToken | BearerTokenAuthentication |
| Lỗi phổ biến | Sai iss/aud, khóa, thuật toán, token type | Sai endpoint, tin active=true mà bỏ kiểm tra resource/scope |

Nếu cache introspection, chọn TTL phù hợp với yêu cầu thu hồi. Cache **active=true** quá lâu khiến token đã bị AS thu hồi vẫn có thể được RS chấp nhận cho đến khi cache hết hạn.

## 6. BearerTokenResolver và nơi lấy credential

**DefaultBearerTokenResolver** ưu tiên đường chuẩn **Authorization header**. Việc nhận bearer token qua **URI query parameter** hoặc **form body** thường không được bật trong cấu hình mặc định vì tăng nguy cơ lộ credential.

~~~http
# Được khuyến nghị
Authorization: Bearer <ACCESS_TOKEN>

# Không nên dùng để truyền access token trong API thông thường
GET /api/orders?access_token=<ACCESS_TOKEN>
~~~

Token trong URL có thể bị lộ qua browser history, reverse proxy, CDN, web server logs, analytics hoặc liên kết sao chép. Không nên tự viết resolver để đọc token từ bất cứ nơi nào client gợi ý.

Có thể biểu đạt chính sách bằng cấu hình:

~~~java
@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setAllowUriQueryParameter(false);
    resolver.setAllowFormEncodedBodyParameter(false);
    return resolver;
}
~~~

Để dùng resolver tùy chỉnh, gắn nó vào cấu hình:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(bearerTokenResolver())
    .jwt(Customizer.withDefaults())
)
~~~

Các false thường là mặc định, ví dụ nhằm làm rõ chủ ý. Một resolver tự viết phải tránh request có **nhiều token mâu thuẫn**, header giả mạo và việc vô tình đọc token từ cookie.

### 6.1. Vì sao cookie thay đổi mô hình bảo mật?

BearerTokenAuthenticationFilter mặc định **không coi cookie là Authorization: Bearer**. Nếu ứng dụng tự cấu hình lấy token từ cookie, browser có thể gửi cookie tự động theo chính sách cookie. Khi đó **CSRF** trở thành vấn đề phải đánh giá, ngoài XSS, SameSite, origin checks và session fixation.

Không được suy luận “token là bearer nên luôn tắt CSRF”. Một API thuần Authorization header do client chủ động gửi khác với ứng dụng nhận credential tự động từ browser.

### 6.2. Gateway và reverse proxy

Xác minh gateway thực sự chuyển Authorization header đến đúng service. Không log header tại WAF, APM, CDN, proxy hoặc ứng dụng. Nếu gateway xác thực token rồi truyền principal qua header nội bộ, backend chỉ được tin thông tin ấy khi có **kênh tin cậy và cơ chế xác thực giữa service**. Client Internet không được tự đặt X-User-Id rồi được coi là authenticated.

## 7. Cấu hình Spring Security JWT Resource Server

Ví dụ sau dùng cấu hình **Spring Boot 3 / Spring Security 6 style** cho **Servlet**. Ứng dụng thực tế cần dependency tương thích, ví dụ starter OAuth2 Resource Server và module xử lý JWT.

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            // Chỉ hợp lý cho API thuần Bearer header, không dùng
            // cookie/session tự gửi credential để xác thực.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

**Lưu ý về phạm vi bảo vệ:**

1. **securityMatcher("/api/**")** chỉ áp dụng chain cho API. Hãy bảo đảm các endpoint khác có chain hoặc chính sách riêng, tránh để tài nguyên nhạy cảm không được bảo vệ.
2. **csrf.disable()** chỉ minh họa cho API stateless thuần bearer trong Authorization header. Nếu ứng dụng sử dụng session cookie hoặc xác thực do browser tự gửi, cần thiết kế CSRF protection thích hợp.
3. **SessionCreationPolicy.STATELESS** ngăn Spring Security dùng HTTP session làm chỗ lưu Authentication cho các request. Nó **không** làm bearer token không thể bị replay.
4. Filter xử lý token, còn **authorizeHttpRequests** kiểm tra quyền. Nếu chỉ cấu hình JWT nhưng quên authorization rules, API có thể không có chính sách quyền mong muốn.

### 7.1. Chỉ định issuer tin cậy

Một cách cấu hình phổ biến:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
~~~

Framework có thể dùng metadata/JWKS của issuer này để tạo decoder phù hợp và xác minh issuer. Đây là URL minh họa, không phải endpoint có thật. Cần thiết lập danh sách issuer đáng tin cậy theo môi trường triển khai; không suy issuer từ query/header do caller cung cấp.

### 7.2. Kiểm tra audience tường minh

Nếu cần kiểm soát issuer, audience và key source rõ ràng, có thể tự khai báo **JwtDecoder**. Đoạn dưới dùng JWKS URI đáng tin cậy đã cấu hình từ trước:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfig {

    private static final String ISSUER =
        "https://identity.example.test/realms/demo";
    private static final String JWKS_URI =
        "https://identity.example.test/realms/demo/certs";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS_URI).build();

        OAuth2TokenValidator<Jwt> issuerAndTimes =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Unexpected audience", null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTimes, audienceValidator
            )
        );

        return decoder;
    }
}
~~~

Ví dụ minh họa **audience validator độc lập**; cần bổ sung token type, client binding, tenant hoặc claims khác theo policy. Cần kiểm tra chính sách thuật toán, key rotation và cấu hình môi trường thực tế. Không copy giá trị URL ví dụ sang production.

### 7.3. Ánh xạ scope thành authorities

Theo cấu hình JWT thông dụng, Spring Security có thể đọc **scope** (chuỗi các scope cách nhau bằng dấu cách) hoặc **scp** rồi tạo authorities với tiền tố **SCOPE_**:

~~~text
scope = "orders:read orders:write"
        |
        v
SCOPE_orders:read
SCOPE_orders:write
~~~

Ví dụ route dùng **hasAuthority("SCOPE_orders:read")**. **hasRole("orders:read")** không tương đương vì quy tắc ROLE_ prefix khác. Nếu AS lưu quyền ở claims tùy chỉnh, hãy dùng **JwtAuthenticationConverter/JwtGrantedAuthoritiesConverter** hoặc converter được thiết kế riêng, có kiểm soát nguồn claim và dạng authority.

**Business authorization** vẫn phải kiểm tra tài nguyên cụ thể: scope cho phép đọc danh sách đơn hàng không tự chứng minh user là chủ sở hữu mọi order.

## 8. Cấu hình opaque token qua introspection

Nếu AS phát hành opaque token, resource server dùng:

~~~java
@Bean
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .securityMatcher("/api/**")
        .csrf(AbstractHttpConfigurer::disable)
        .sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders:read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults()));
    return http.build();
}
~~~

Cấu hình introspection minh họa:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: <SECRET_FROM_SECURE_CONFIGURATION>
~~~

**Không commit client secret thật vào source code.** Hãy nạp bằng secret manager hoặc cấu hình triển khai an toàn; bảo vệ TLS và quyền introspection client. Nếu AS unavailable, không coi token là active chỉ vì cần duy trì API hoạt động.

Nếu introspection response không có aud/issuer, cần xác định cơ chế resource binding đáng tin cậy từ AS và ngữ cảnh endpoint. Không chấp nhận token do sai AS báo active=true.

## 9. Đọc Authentication ở controller và method security

Với JWT resource server, Authentication thường là **JwtAuthenticationToken**. Có thể nhận qua tham số controller:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    String whoAmI(Authentication authentication) {
        JwtAuthenticationToken jwt =
            (JwtAuthenticationToken) authentication;

        return jwt.getToken().getIssuer() + " / "
            + jwt.getToken().getSubject();
    }
}
~~~

**Đây là ví dụ dành cho cấu hình JWT.** Với opaque token, Authentication thường là **BearerTokenAuthentication** với **OAuth2AuthenticatedPrincipal**; không cast sang JwtAuthenticationToken. Ở ứng dụng thực tế nên chuyển claims đã xác thực thành domain principal rõ ràng.

Có thể dùng method authorization:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderDto findOrder(String orderId, Authentication principal) {
    // Kiểm tra thêm quyền thực tế trên orderId trong service.
    return orderService.findOrderAllowedFor(orderId, principal);
}
~~~

Muốn dùng **@PreAuthorize** cần bật method security, ví dụ **@EnableMethodSecurity** trong cấu hình Spring Security hiện đại. Chỉ scope là không đủ để thay business authorization đối với orderId.

Ở hệ thống đa issuer, **sub** phải được hiểu trong phạm vi issuer: **(iss, sub)** là một định danh an toàn hơn khi ánh xạ danh tính ngoài hệ thống, thay vì chỉ dùng sub hoặc email.

## 10. HTTP 401, 403 và WWW-Authenticate

Theo RFC 6750, Bearer Authentication có các mã lỗi phù hợp với bối cảnh.

| Trường hợp | Kết quả thường gặp | Lý do |
|---|---|---|
| Endpoint protected nhưng không có token | **401 Unauthorized** | Chưa có xác thực |
| JWT hết hạn/sai chữ ký hoặc opaque inactive | **401**, thường **invalid_token** | Credential không hợp lệ |
| Bearer request malformed/mâu thuẫn | Có thể **400 invalid_request** | Request xác thực sai cấu trúc |
| Đã xác thực nhưng scope thiếu | **403**, có thể **insufficient_scope** | Thiếu quyền |
| Resource thuộc user/tenant khác | **403** hoặc response theo chính sách che giấu tài nguyên | Business authorization từ chối |
| Endpoint public và không có token | Có thể **200** | Không yêu cầu xác thực |

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Cache-Control: no-store
~~~

Spring Security có **BearerTokenAuthenticationEntryPoint** và **BearerTokenAccessDeniedHandler** để hỗ trợ xử lý các đường lỗi tương ứng. Header cụ thể còn tùy error code, realm, cấu hình và phiên bản; không nên hardcode kiểm thử chỉ so chuỗi thông báo. Không trả raw access token, khóa, nội dung JWT nhạy cảm hoặc thông tin chi tiết về infrastructure cho caller.

**Phân biệt:** một token đã được xác thực nhưng thiếu scope không phải token giả. Ngược lại, một token không hợp lệ không nên được cấp principal chỉ để trả 403.

## 11. Replay, refresh token và sender-constrained token

BearerTokenAuthenticationFilter xử lý **bearer**. Nếu kẻ tấn công có bản sao access token hợp lệ, họ có thể gửi lại **Authorization: Bearer**. Filter nhìn thấy cùng credential; không thể tự suy ra người đang gửi là chủ sở hữu hợp pháp.

Biện pháp giảm thiểu:

1. Bắt buộc **HTTPS** ở mọi điểm sử dụng token; không truyền trong URL/log.
2. Giới hạn **scope, audience và thời gian sống**.
3. Dùng **denylist/introspection/thu hồi** khi cần vô hiệu hóa nhanh.
4. Bảo vệ nơi lưu token ở browser, mobile và backend; hạn chế XSS và lộ qua analytics.
5. Với refresh token của public client, áp dụng **rotation hoặc sender-constraining** theo OAuth 2.0 Security BCP (RFC 9700).
6. Giám sát bất thường có ngữ cảnh; IP/user-agent chỉ là tín hiệu, không tự chứng minh đánh cắp.
7. Khi cần, thiết kế **sender-constrained access token** qua DPoP hoặc mTLS.

### 11.1. DPoP có phải Bearer không?

**Không.** DPoP-bound token yêu cầu chứng minh quyền sở hữu khóa, thường có:

~~~http
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <SIGNED_DPOP_PROOF>
~~~

Resource server cần xác thực proof (chữ ký, htm/htu, iat, ath, nonce/jti khi áp dụng), so **cnf.jkt** của token với khóa ký proof và chống replay proof. **BearerTokenAuthenticationFilter mặc định nhận bearer header không tự thực hiện các bước này**. Không hạ cấp DPoP-bound access token thành bearer token chỉ vì chữ ký JWT hợp lệ.

Với **mTLS certificate-bound token**, RS phải kiểm tra chứng chỉ client tại kết nối TLS khớp binding **cnf.x5t#S256** trong token/metadata. Nếu gateway chấm dứt TLS, chứng cứ về chứng chỉ cần được truyền qua kênh nội bộ được bảo vệ; không tin header do người gọi bên ngoài tự đặt.

### 11.2. Tại sao refresh token không gửi tới resource server?

**Refresh token** dành cho token endpoint của AS để xin access token mới, có policy riêng về client binding, rotation, expiration và thu hồi. Nếu API nhận refresh token làm access token, ranh giới quyền bị phá vỡ, tạo cơ hội dùng credential dài hạn ở nhiều nơi không cần thiết. RS cần kiểm tra loại token/audience đúng để ngăn **token substitution**.

### 11.3. Logout và JWT tự chứa

Logout hoặc xóa SecurityContext không tự thu hồi JWT access token đang ở client. Nếu RS chỉ xác minh chữ ký và exp, JWT vẫn có thể được chấp nhận tới lúc hết hạn. Cần thiết kế TTL ngắn, revoke token nơi có thể, hoặc tra trạng thái khi nghiệp vụ đòi immediate invalidation.

## 12. Nhiều issuer/tenant với AuthenticationManagerResolver

Một resource server có thể phục vụ nhiều tổ chức hoặc nhiều AS:

~~~text
Trusted issuers:
  https://login.corp.example.test    -> JWKS_CORP
  https://partner-id.example.test    -> JWKS_PARTNER

Token iss=CORP    -> xác minh bằng keys/validator CORP
Token iss=PARTNER -> xác minh bằng keys/validator PARTNER
Issuer khác       -> từ chối
~~~

Nguyên tắc:

- **Tập issuer tin cậy phải được cấu hình/phê duyệt trước**; không tự thêm issuer dựa trên token chưa xác thực.
- Nếu đọc iss chưa xác thực để chọn manager/decoder, chỉ cho phép chọn từ **allowlist đóng**, rồi xác minh chữ ký và so khớp iss đã xác thực.
- Cache JWKS/khóa theo issuer; **kid không duy nhất toàn hệ thống**.
- Mỗi API/tenant cần whitelist issuer/audience riêng theo chính sách.
- Với opaque token, chọn introspection endpoint tin cậy từ cấu hình, không lấy URL tùy ý từ token.
- Subject cần gắn với issuer và tenant. Authentication hợp lệ không mặc nhiên được phép xem dữ liệu của tenant khác.

Spring Security cung cấp **AuthenticationManagerResolver<HttpServletRequest>** để định tuyến authentication manager; các phiên bản Spring Security có tiện ích hỗ trợ nhiều JWT issuer. Khi triển khai phải xem tài liệu của đúng phiên bản đang dùng, tránh chuyển mọi token về một manager quá rộng.

## 13. Bảng lỗi vận hành và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Mọi request trả 401 | Proxy xóa header, chain sai, issuer/JWKS sai | Filter chain, Authorization forwarding, decoder config |
| JWT ký đúng nhưng trả 401 | Sai iss/aud, hết hạn, nbf hoặc token type | Validators và claims từ token đã xác thực |
| Chỉ một số instance trả 401 | Cấu hình issuer/JWKS cache, clock skew khác nhau | Đồng bộ cấu hình, đồng hồ, cache |
| Đã login nhưng 403 | Thiếu authority, hasRole/hasAuthority mismatch | Scope mapping và authorization policy |
| API trả 403 cho POST trên web | CSRF filter hoặc method authorization | Credential ở cookie hay header, CSRF rule |
| Opaque token ngẫu nhiên mất hiệu lực | Introspection lỗi, token inactive, timeout hoặc cache | AS logs không chứa token, network, TTL |
| Browser báo CORS error | Preflight OPTIONS hoặc Access-Control headers thiếu | CORS filter và gateway, không nới quyền nghiệp vụ |
| Token từ staging dùng được ở production | Issuer/audience allowlist quá rộng | Environment isolation |
| API nhận ID token thay access token | Không kiểm tra audience/token type | Token profile và issuer policy |
| Người dùng xem đơn hàng người khác | Thiếu business authorization | Ràng buộc resource owner, tenant, permission |

### 13.1. Không log raw bearer token

Nên ghi các event như **bearer_token_missing**, **token_invalid**, **issuer_mismatch**, **audience_mismatch**, **scope_denied**, **introspection_unavailable**. Dữ liệu phù hợp có thể là request ID, issuer đã xác minh, API, loại lỗi và fingerprint an toàn của token nếu cần điều tra. Tránh ghi **Authorization header**, raw token, client secret, private key hoặc toàn bộ JWT claims nhạy cảm vào log.

### 13.2. Stateless không thay session security của ứng dụng khác

Một hệ thống có thể vừa có API stateless bearer vừa có trang web đăng nhập qua cookie. Hãy tách SecurityFilterChain và các chính sách tương ứng. Bật **STATELESS** cho API không có nghĩa cookie phiên ở giao diện web được bảo vệ khỏi CSRF/session fixation. Bảo vệ theo credential thực tế được dùng ở mỗi endpoint.

## 14. Kiểm thử BearerTokenAuthenticationFilter

### 14.1. Ma trận kiểm thử

| Ca | Kỳ vọng |
|---|---|
| GET /api/orders/42, JWT hợp lệ, orders:read, đúng owner | Request được phép |
| Không token, endpoint protected | 401 qua entry point |
| Không token, endpoint public | Có thể được phép |
| JWT sai chữ ký | 401 |
| JWT sai issuer | 401 |
| JWT thiếu audience orders-api | 401 khi validator được cấu hình |
| JWT hết hạn hoặc nbf trong tương lai | 401 |
| OIDC ID token gửi nhầm làm access token | Bị từ chối theo token profile/audience |
| JWT hợp lệ chỉ có orders:read, gọi POST cần orders:write | 403 |
| Có scope nhưng tài nguyên không thuộc principal | Business authorization từ chối |
| Opaque token active=false | 401 |
| Opaque active=true nhưng scope không đủ | 403 |
| Introspection timeout hoặc AS không tin cậy | Không cấp quyền |
| Token truyền trong query khi resolver không cho phép | Không được dùng làm credential |
| Header chứa token sai định dạng | Bị xử lý lỗi theo RFC 6750 |
| Token bị thu hồi | Bị từ chối theo denylist/introspection/TTL policy |
| Hai issuer trùng kid nhưng khác khóa | Chọn khóa theo đúng issuer |
| Request kế tiếp không gửi token | Không kế thừa Authentication request trước |
| Preflight OPTIONS | CORS phù hợp; không cấp quyền nghiệp vụ ngoài ý muốn |
| DPoP-bound JWT gửi như Bearer nhưng không có proof | Không được coi là sender-constrained authentication hợp lệ |

### 14.2. MockMvc kiểm tra authorization

Với **spring-security-test**, có thể giả lập JWT principal để kiểm tra scope:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().jwt(token -> token.claim("scope", "orders:read"))))
    .andExpect(status().isOk());
~~~

Đoạn này cần import static phù hợp, controller và dữ liệu thử nghiệm. **Điểm rất quan trọng:** **jwt()** của Spring Security Test có thể đưa Authentication giả vào test context và **không chạy qua xác minh chữ ký/issuer/audience thật của JwtDecoder**. Vì vậy test này chỉ chứng minh phần authorization/mapping dự kiến.

Cần thêm integration tests gửi **Authorization: Bearer <SIGNED_JWT>** qua filter chain thật, sử dụng JWKS test server và token có chữ ký sai, iss/aud sai, hết hạn, nbf, token type sai. Với opaque token, dùng introspection server thử nghiệm để kiểm tra active, scope, audience và lỗi network.

Các kiểm thử concurrency hoặc nhiều instance nên xác minh rằng một request không bao giờ “thừa hưởng” Authentication của request trước đó khi không gửi token.

## 15. Những hiểu nhầm thường gặp

**“BearerTokenAuthenticationFilter kiểm tra chữ ký JWT.”** Sai. Filter chuyển bearer token tới AuthenticationManager; JwtAuthenticationProvider/JwtDecoder chịu trách nhiệm xác minh JWT.

**“Token ký hợp lệ thì API phải chấp nhận.”** Sai. Phải kiểm tra đúng issuer, audience, token type, thời gian, scope và quyền trên tài nguyên.

**“Không gửi token luôn bị filter trả 401.”** Không. Filter có thể cho request đi tiếp; endpoint public vẫn được truy cập, còn endpoint protected bị authorization/entry point từ chối.

**“JWT có scope orders:read là đọc được mọi order.”** Sai. Service phải kiểm tra chủ sở hữu hoặc policy theo đối tượng.

**“Opaque token active=true là đủ.”** Không mặc nhiên. Cần đúng AS, resource, scope, tenant và hạn dùng theo metadata/chính sách.

**“Có bearer header thì CSRF không bao giờ quan trọng.”** Sai. Nếu credential được browser gửi tự động qua cookie, CSRF vẫn phải được xem xét.

**“STATELESS nghĩa là access token không thể bị replay.”** Sai. Stateless chỉ nói về cách lưu Authentication ở server; bearer token bị lộ vẫn có thể bị sử dụng lại.

**“Filter tự hỗ trợ mọi dạng DPoP/mTLS token.”** Sai. Token ràng buộc người gửi đòi kiểm tra key/proof/certificate riêng.

**“MockMvc jwt() PASS chứng minh decoder production an toàn.”** Sai. Phải có integration test thực sự kiểm tra chữ ký, issuer, audience và lỗi.

## 16. Câu hỏi tự kiểm tra

1. BearerTokenAuthenticationFilter có trách nhiệm gì, và JwtAuthenticationProvider xử lý phần nào?
2. Vì sao không có Authorization header chưa chắc là lỗi ngay trong filter?
3. JWT và opaque token khác nhau ở provider và cách lấy claims như thế nào?
4. SecurityContextHolder được dùng ở các bước phía sau filter ra sao?
5. Vì sao cần kiểm tra audience ngay cả khi JWT có chữ ký đúng?
6. Khi scope = orders:read, Spring Security thường tạo authority nào?
7. Phân biệt **401 invalid_token** và **403 insufficient_scope**.
8. Vì sao OIDC ID token không mặc nhiên dùng như API access token?
9. Caching introspection có thể ảnh hưởng việc thu hồi opaque token như thế nào?
10. Vì sao không được tải JWKS tùy ý từ claim iss hoặc header jku chưa xác thực?
11. Trong hệ thống đa tenant, tại sao subject cần gắn với issuer?
12. Khi dùng token trong cookie, những biện pháp CSRF nào cần xem xét?
13. Khi nào cần sender-constrained token, và vì sao Bearer-only chưa đủ?
14. Vì sao mock JWT principal trong MockMvc chưa chứng minh JwtDecoder hoạt động đúng?
15. Nếu API vẫn cho phép dùng token sau logout, nên kiểm tra những cơ chế nào?

**Ghi nhớ:** **BearerTokenAuthenticationFilter** là đầu vào của việc xác thực bearer credential trong **Spring Security Servlet Resource Server**. Nó trích token, giao cho authentication provider, đặt Authentication vào SecurityContext rồi chuyển quyền quyết định cho authorization layer. Hệ thống chỉ an toàn khi đồng thời bảo vệ **nguồn khóa/AS, issuer, audience, token type, thời hạn, scope, quyền nghiệp vụ, cơ chế thu hồi và chống token bị đánh cắp/phát lại**.

## Tài liệu tham khảo

- **Spring Security Reference — OAuth 2.0 Resource Server / Bearer Tokens:** luồng xác thực bearer, JWT và opaque token.
- **Spring Security API — BearerTokenAuthenticationFilter, DefaultBearerTokenResolver, JwtAuthenticationProvider, OpaqueTokenAuthenticationProvider:** API và trách nhiệm thành phần.
- **Spring Security Reference — Authorize HTTP Requests, Session Management, Method Security:** authorization, SecurityFilterChain và quản lý SecurityContext.
- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage:** Authorization header, WWW-Authenticate và lỗi token.
- **RFC 7519 — JSON Web Token (JWT):** claims JWT và mô hình xác minh JWT.
- **RFC 7662 — OAuth 2.0 Token Introspection:** active, metadata và xác minh opaque token.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** JWT access token, issuer, audience và token profile.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ access/refresh token và biện pháp chống replay.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** key binding và DPoP proof.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** token ràng buộc mTLS.

