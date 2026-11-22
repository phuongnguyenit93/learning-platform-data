# OAuth2AuthenticatedPrincipal trong BearerTokenAuthentication

## 1. Sau introspection, Resource Server đang có dữ liệu gì?

Trong **Spring Security OAuth 2.0/OIDC Resource Server sử dụng WebFlux**, client gửi opaque access token qua HTTP:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer opaque-access-token
~~~

Opaque token là credential được Authorization Server (AS) quản lý. Resource Server (RS) thường không thể suy ra subject, scope hoặc expiry chỉ bằng cách parse chuỗi. RS gọi **OAuth 2.0 Token Introspection** theo RFC 7662 để xác minh token active và nhận metadata.

Ví dụ AS trả:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "iss": "https://auth.example.com/realms/shop",
  "aud": ["orders-api"],
  "exp": 1794731400,
  "iat": 1794729600
}
~~~

Khi quá trình introspection hợp lệ, hai Spring Security types xuất hiện:

- **OAuth2AuthenticatedPrincipal**: đại diện danh tính/attributes/authorities đã được xác định sau introspection.
- **BearerTokenAuthentication**: Authentication result bao bọc principal ấy, verified OAuth2AccessToken và authorities để đưa vào reactive security context.

Điểm cốt lõi: **principal không phải raw token; raw token không phải Authentication đã được xác thực; claims không tự đồng nghĩa quyền nghiệp vụ**.

Sơ đồ:

~~~text
HTTP Authorization: Bearer opaque-token
             |
             v
ReactiveOpaqueTokenIntrospector
  xác minh active và lấy token attributes
             |
             v
OAuth2AuthenticatedPrincipal
  name + attributes + authorities
             |
             v
OpaqueTokenReactiveAuthenticationManager
  tạo BearerTokenAuthentication
             |
             v
ReactiveSecurityContextHolder
             |
             v
WebFlux authorization và business handler
~~~

Bài học giải thích chính xác API, dữ liệu bên trong principal, cách đọc và tùy biến trong WebFlux cùng các ranh giới bảo mật.

## 2. Năm khái niệm khác nhau

| Đối tượng | Trách nhiệm | Đã xác thực? |
|---|---|---|
| **Raw Bearer token** | Chuỗi credential do caller gửi | Chưa |
| **BearerTokenAuthenticationToken** | Authentication request mang chuỗi token | Chưa |
| **OAuth2AuthenticatedPrincipal** | Name, attributes và authorities từ introspection thành công | Có giá trị sau trust validation |
| **BearerTokenAuthentication** | Authentication result theo opaque Bearer flow mặc định | Đã xác thực |
| **SecurityContext** | Giữ Authentication để authorization sử dụng | Theo pipeline đã xác thực |

Một ví dụ logic:

~~~text
"opaque-abc123"
  chỉ là raw credential.

BearerTokenAuthenticationToken("opaque-abc123")
  chỉ là yêu cầu xác thực.

OAuth2AuthenticatedPrincipal:
  name="user-42"
  attributes={sub, scope, client_id, aud, ...}
  authorities=[SCOPE_orders.read, SCOPE_orders.write]
  đến từ trusted introspection.

BearerTokenAuthentication:
  principal=OAuth2AuthenticatedPrincipal
  accessToken=verified OAuth2AccessToken
  authorities=...
  authenticated=true
  là kết quả authentication.
~~~

Không tự tạo BearerTokenAuthentication đã authenticated bằng một raw token chưa kiểm tra chỉ để tránh gọi AS. Đó là bỏ qua authentication.

## 3. Chuỗi xử lý reactive trong WebFlux

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as AuthenticationWebFilter
    participant X as ServerBearerTokenAuthenticationConverter
    participant M as OpaqueTokenReactiveAuthenticationManager
    participant I as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server
    participant S as Reactive Security Context
    participant Z as Authorization

    C->>F: Authorization Bearer opaque-token
    F->>X: convert(exchange)
    X-->>F: BearerTokenAuthenticationToken
    F->>M: authenticate(raw credential)
    M->>I: introspect(token)
    I->>AS: POST introspection, RS credentials
    alt active=true
      AS-->>I: Token attributes
      I-->>M: OAuth2AuthenticatedPrincipal
      M-->>F: BearerTokenAuthentication
      F->>S: Authentication success
      S->>Z: Authorities and principal
    else active=false
      AS-->>I: Inactive token
      I-->>M: Authentication error
    else upstream error
      AS-->>I: HTTP 401, 5xx, timeout
      I-->>M: Introspection failure
    end
~~~

Các thành phần:

| WebFlux component | Vai trò |
|---|---|
| **ServerWebExchange** | HTTP request/response reactive |
| **ServerBearerTokenAuthenticationConverter** | Trích raw Bearer token |
| **AuthenticationWebFilter** | Gọi authentication manager và quản lý kết quả |
| **OpaqueTokenReactiveAuthenticationManager** | Xác minh opaque Bearer token và tạo Authentication |
| **ReactiveOpaqueTokenIntrospector** | Xác minh token qua AS/trusted token store |
| **ReactiveOpaqueTokenAuthenticationConverter** | Chuyển token + authenticated principal thành Authentication |
| **OAuth2AuthenticatedPrincipal** | Attributes/authorities sau introspection |
| **BearerTokenAuthentication** | Authentication result mặc định |
| **ReactiveSecurityContextHolder** | SecurityContext trong Reactor Context |
| **SecurityWebFilterChain** | WebFilters bảo vệ request |
| **ServerHttpSecurity** | DSL cấu hình WebFlux Security |

Đừng nhầm với Servlet:

| Servlet | WebFlux |
|---|---|
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| OpaqueTokenAuthenticationProvider | OpaqueTokenReactiveAuthenticationManager |
| OpaqueTokenIntrospector | ReactiveOpaqueTokenIntrospector |
| Servlet Filter | WebFilter |
| HttpServletRequest | ServerWebExchange |
| SecurityContextHolder theo ThreadLocal thường gặp | ReactiveSecurityContextHolder theo Reactor Context |

**OpaqueTokenReactiveAuthenticationManager** là một ReactiveAuthenticationManager. Nó dùng introspector và authentication converter để tạo Authentication sau introspection thành công. Trong cấu hình mặc định, kết quả điển hình là **BearerTokenAuthentication**; một custom converter có thể thay đổi type kết quả.

## 4. RFC 7662 trả về JSON, không phải Java Authentication

Một introspection request thường có dạng:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_RS_CREDENTIALS

token=opaque-access-token&token_type_hint=access_token
~~~

AS trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1794731400
}
~~~

RFC 7662 mô tả **active boolean và metadata**, không quy định các Java types OAuth2AuthenticatedPrincipal hay BearerTokenAuthentication. Spring Security dùng response đáng tin để tạo những đối tượng đó.

Cần phân biệt kết quả:

- **HTTP 200 + active=true**: AS nói token active; introspector có thể tạo principal.
- **HTTP 200 + active=false**: token không được AS chấp nhận; không tạo authenticated principal.
- **HTTP 401/403 từ AS introspection endpoint**: có thể là credentials/quyền introspect của RS; không tự nói token caller invalid.
- **Timeout, TLS, HTTP 429/5xx, malformed JSON**: lỗi phụ thuộc/protocol, chưa biết token active hay không.

Tất cả lỗi khi chưa xác minh token phải **fail closed**: không cho protected request đi tiếp.

### Hai loại credential

**Bearer token của caller** được gửi đến Resource Server. **Client ID/client secret của Resource Server** được dùng để gọi AS introspection endpoint. Nếu AS trả 401 invalid_client sau secret rotation, Resource Server chưa có kết luận token của user không active. Không khắc phục bằng cách làm một principal giả khi introspection thất bại.

## 5. Hợp đồng ReactiveOpaqueTokenIntrospector

Interface thuộc package:

~~~java
org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector
~~~

Chữ ký khái niệm:

~~~java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
~~~

**Không tự định nghĩa lại** interface trên trong ứng dụng; ví dụ chỉ mô tả API của Spring Security.

Ý nghĩa:

~~~text
introspect(token)
   |
   +-- success -> Mono<OAuth2AuthenticatedPrincipal>
   |
   +-- inactive -> authentication/introspection error
   |
   +-- AS/network/protocol failure -> error signal
~~~

Introspector **không trả Mono<BearerTokenAuthentication>** theo API của nó. Authentication manager/converter ở lớp kế tiếp dùng principal để tạo Authentication. Khi token không active, nó phải phát lỗi phù hợp thay vì trả principal có empty authorities rồi xem như success.

### Không biến lỗi thành principal mặc định

Anti-pattern:

~~~java
// Nguy hiểm: lỗi AS biến thành authentication success.
return delegate.introspect(token)
        .onErrorResume(ex -> Mono.just(defaultUserPrincipal));
~~~

Dù defaultUserPrincipal chỉ có ít quyền, đó vẫn là bypass authentication. Nếu business endpoint chỉ yêu cầu authenticated(), token giả có thể lọt vào.

**Một custom ReactiveOpaqueTokenIntrospector phải giữ ranh giới tin cậy của token acceptance.**

## 6. OAuth2AuthenticatedPrincipal có những API nào?

Interface ở package:

~~~java
org.springframework.security.oauth2.core
    .OAuth2AuthenticatedPrincipal
~~~

Các phương thức quan trọng:

| API | Nội dung |
|---|---|
| **getName()** | Tên principal theo implementation và token profile |
| **getAttributes()** | Map<String, Object> chứa attributes |
| **getAttribute(String)** | Đọc một attribute theo tên |
| **getAuthorities()** | Collection<? extends GrantedAuthority> |

Ví dụ:

~~~java
import java.util.Map;
import java.util.Collection;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

OAuth2AuthenticatedPrincipal principal = ...;

String name = principal.getName();
Map<String, Object> attributes = principal.getAttributes();
String subject = principal.getAttribute("sub");

Collection<? extends GrantedAuthority> authorities =
        principal.getAuthorities();
~~~

**Không suy ra getName() luôn là email, username hoặc internal database user ID.** Trong token cho user, name thường ánh xạ từ sub nếu có; trong token client_credentials, principal có thể đại diện machine client và không mang human subject.

## 7. DefaultOAuth2AuthenticatedPrincipal

Spring Security cung cấp class **DefaultOAuth2AuthenticatedPrincipal** để biểu diễn name, attributes, authorities.

Ví dụ tạo principal **trong unit test**:

~~~java
import java.util.Map;
import java.util.List;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;

OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
                "user-42",
                Map.of(
                        "sub", "user-42",
                        "client_id", "shop-web",
                        "tenant_id", "tenant-blue"),
                List.of(
                        new SimpleGrantedAuthority("SCOPE_orders.read"),
                        new SimpleGrantedAuthority("SCOPE_orders.write")));
~~~

**Tự tạo class này không thực hiện introspection.** Trong production, attributes chỉ được dùng để tạo Authentication khi đã đi qua một cơ chế xác thực tin cậy. Một đối tượng tên OAuth2AuthenticatedPrincipal không tự đáng tin chỉ nhờ class name.

Các tham số:

- **name**: tên principal.
- **attributes**: metadata đã được xác minh nguồn.
- **authorities**: quyền được phép đưa vào Spring Security authorization.

Có một attribute roles trong Map không tự biến nó thành ROLE_ADMIN nếu bạn chưa có mapping đáng tin.

## 8. BearerTokenAuthentication chứa principal thế nào?

Class ở package:

~~~java
org.springframework.security.oauth2.server.resource.authentication
    .BearerTokenAuthentication
~~~

Constructor công khai điển hình:

~~~java
new BearerTokenAuthentication(
        OAuth2AuthenticatedPrincipal principal,
        OAuth2AccessToken credentials,
        Collection<? extends GrantedAuthority> authorities)
~~~

Những điểm cốt lõi:

| Thành phần/API | Ý nghĩa |
|---|---|
| **getPrincipal()** | OAuth2AuthenticatedPrincipal |
| **getTokenAttributes()** | Map attributes sau introspection |
| **getAuthorities()** | Authorities cuối cùng của Authentication |
| **getName()** | Tên Authentication, thường dựa trên principal name |
| **getToken()** | OAuth2AccessToken từ superclass, khi dùng API tương ứng |
| **isAuthenticated()** | Trạng thái xác thực |
| **OAuth2AccessToken credentials** | Credential đã được xác minh theo flow, không phải JWT claims |

Ví dụ sử dụng:

~~~java
BearerTokenAuthentication authentication = ...;

OAuth2AuthenticatedPrincipal principal =
        authentication.getPrincipal();

String name = authentication.getName();

Object subject =
        authentication.getTokenAttributes().get("sub");

boolean hasReadAuthority =
        authentication.getAuthorities().stream()
                .anyMatch(a ->
                        "SCOPE_orders.read".equals(a.getAuthority()));
~~~

**getTokenAttributes() không yêu cầu opaque token phải là JWT.** Attributes đến từ AS introspection, không phải payload tự decode từ token string.

### Authorities của principal và Authentication

Principal có authorities từ introspector. Authentication cuối cùng có authorities được authentication converter chọn, có thể giống hoặc được biến đổi từ principal. Khi kiểm tra quyền thực tế, dùng **Authentication.getAuthorities()**, vì đó là dữ liệu Spring Security authorization áp dụng.

Một số Spring Security version có thể thêm factor-related granted authority. Đừng test một Authentication chỉ có đúng số lượng scope authorities bằng cách so sánh danh sách tuyệt đối; hãy test các authorities thiết yếu hiện diện.

## 9. BearerTokenAuthentication khác BearerTokenAuthenticationToken

Hai tên dễ nhầm:

~~~text
BearerTokenAuthenticationToken
  - được converter tạo từ HTTP credential
  - chứa raw token
  - chưa authenticated

BearerTokenAuthentication
  - được manager/converter tạo sau introspection thành công
  - chứa OAuth2AuthenticatedPrincipal và OAuth2AccessToken
  - authenticated result
~~~

Một ví dụ chưa xác thực:

~~~java
BearerTokenAuthenticationToken request =
        new BearerTokenAuthenticationToken("opaque-test-token");
~~~

Không tự xây BearerTokenAuthentication từ request trên rồi đặt vào SecurityContext nếu chưa introspect. Điều đó biến một credential chưa xác minh thành danh tính được tin cậy.

## 10. So sánh với JWT Resource Server

JWT:

~~~text
Authorization: Bearer signed-JWT
   |
   v
ReactiveJwtDecoder kiểm tra JWS signature, iss, aud, exp...
   |
   v
JwtAuthenticationToken với principal kiểu Jwt
   |
   v
Authorization
~~~

Opaque:

~~~text
Authorization: Bearer opaque-token
   |
   v
ReactiveOpaqueTokenIntrospector kiểm tra active qua AS
   |
   v
OAuth2AuthenticatedPrincipal
   |
   v
BearerTokenAuthentication
   |
   v
Authorization
~~~

| Khía cạnh | JWT Resource Server | Opaque Resource Server |
|---|---|---|
| Verification | ReactiveJwtDecoder/JWKS | ReactiveOpaqueTokenIntrospector |
| Principal điển hình | Jwt | OAuth2AuthenticatedPrincipal |
| Authentication điển hình | JwtAuthenticationToken | BearerTokenAuthentication |
| Attributes | JWT claims đã được verify | Introspection metadata đã được tin |
| Authority mapping | JWT scope/claims | Introspection scope/attributes |
| AS network cho mỗi request | Không bắt buộc nếu keys cached | Thường có, trừ cache/policy |
| Revocation awareness | Có thể cần cơ chế bổ sung | AS có thể phản ánh revoke qua active=false |

Ngay cả khi access token có định dạng JWT, ứng dụng vẫn có thể quyết định dùng **opaque introspection** thay cho JWT decoding. Khi đó Java Authentication đi theo flow introspection, không dựa trên hình dạng token string.

**Đừng cast Authentication.getPrincipal() sang Jwt** nếu ứng dụng dùng opaque Resource Server.

## 11. Các introspection attributes thường gặp

RFC 7662 quy định một số attributes; AS không buộc cung cấp mọi attribute trong mỗi loại token.

| Attribute | Wire type thường gặp | Ý nghĩa | Chú ý |
|---|---|---|---|
| **active** | Boolean | Trạng thái token theo AS | false phải bị từ chối trước khi tạo principal |
| **scope** | Space-delimited String | Phạm vi quyền | Spring Security có thể chuẩn hóa thành List<String> |
| **client_id** | String | OAuth client được cấp token | Không nhất thiết là user |
| **sub** | String | Subject | Phạm vi issuer, không global unique |
| **username** | String | Tên hiển thị theo AS | Không mặc nhiên stable user key |
| **token_type** | String | Loại token | Có thể là bearer theo contract |
| **exp** | NumericDate | Hết hạn | Có thể map thành Instant |
| **iat** | NumericDate | Issued At | Không thay auth_time |
| **nbf** | NumericDate | Not Before | Temporal validity |
| **aud** | String/Array | Intended recipients | Cần kiểm tra resource binding |
| **iss** | String | Issuer identifier | Cần trust policy |
| **jti** | String | Token ID | Không phải user ID |
| **tenant_id** | Provider-specific | Tenant metadata | Không có semantics chung trong RFC 7662 |
| **groups/roles** | Provider-specific | Group/role metadata | Không tự thành GrantedAuthority |

### Đừng cast mọi attribute sang String

Ví dụ AS trả:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write",
  "exp": 1794731400,
  "aud": ["orders-api"]
}
~~~

Sau introspection, implementation có thể chuẩn hóa:

~~~text
scope -> List<String>
exp   -> Instant
aud   -> List<String>
~~~

Không chắc đoạn sau đúng:

~~~java
String scope = principal.getAttribute("scope");
~~~

vì scope có thể là một List. Nếu mục tiêu là kiểm tra quyền, dùng **principal.getAuthorities()** hoặc **authentication.getAuthorities()**. Nếu cần attributes gốc, xác định kiểu theo token contract và kiểm tra type trước khi cast.

## 12. Scope sang SCOPE_ GrantedAuthority

AS trả:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

Spring Security theo mapping mặc định thường tạo:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

WebFlux policy:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Prefix **SCOPE_** là convention Spring Security, không nhất thiết xuất hiện trên wire response RFC 7662.

### Scope khác domain permission

Một token có orders.write không tự được sửa mọi order. Domain có thể cần:

~~~text
hasAuthority("SCOPE_orders.write")
AND actor belongs to order tenant
AND actor is allowed to modify this order
AND order state permits modification
~~~

**Token active** là credential check. **Scope đủ** là coarse authorization. **Ownership/tenant/workflow** là domain authorization.

### SCOPE_ khác ROLE_

- hasAuthority("SCOPE_orders.write") kiểm tra authority theo scope.
- hasRole("ADMIN") theo convention tìm ROLE_ADMIN.
- Claim roles=["ADMIN"] không mặc định được map thành ROLE_ADMIN.

Đừng tự cấp role admin từ attribute nhóm không có trust contract rõ ràng.

## 13. Cấu hình Spring Boot cho WebFlux opaque token

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: REPLACE_WITH_SECRET_MANAGER
~~~

Resource Server dùng client ID/secret để xác thực với AS introspection endpoint; đây **không phải access token của caller**.

Trong production, secret nên đến từ secret manager hoặc environment injection. Đừng commit secret thật vào repository hoặc log credentials trong error responses.

**Địa chỉ introspection URI là ví dụ, không phải path cố định của mọi AS.** Lấy endpoint từ provider contract/metadata đáng tin.

AS có thể yêu cầu mTLS/private_key_jwt thay vì Basic. SpringReactiveOpaqueTokenIntrospector mặc định theo builder clientId/clientSecret là một lựa chọn; khi AS dùng phương thức khác, cấu hình HTTP client/introspector phù hợp hợp đồng. Không tự thay authentication method mà không có căn cứ.

## 14. SecurityWebFilterChain kích hoạt opaque introspection

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
public class OrdersApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
~~~

Flow:

1. ServerBearerTokenAuthenticationConverter đọc raw credential.
2. OpaqueTokenReactiveAuthenticationManager gọi ReactiveOpaqueTokenIntrospector.
3. Token active -> OAuth2AuthenticatedPrincipal.
4. Manager/converter tạo BearerTokenAuthentication.
5. Security context có Authentication; authorization dùng authorities.
6. Handler chỉ xử lý sau security policy phù hợp.

**Không phải tự viết WebFilter để thay OAuth2 Resource Server**. Khi muốn đổi mapping principal/authorities, dùng extension points của introspector/authentication converter.

### CSRF và CORS

Một 403 do CSRF hoặc CORS không nhất thiết là insufficient_scope. API thuần Bearer stateless có thể có CSRF policy khác ứng dụng dùng browser session cookies; phải xác định trust model trước khi tắt CSRF. CORS preflight thường không mang Bearer token và cần được xử lý phù hợp.

## 15. Lấy OAuth2AuthenticatedPrincipal trong WebFlux controller

Với Spring Security principal injection:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Mono<MeView> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        String subject = principal.getAttribute("sub");
        String issuer = principal.getAttribute("iss");

        return Mono.just(new MeView(
                principal.getName(), subject, issuer));
    }

    public record MeView(
            String name, String subject, String issuer) {}
}
~~~

Code giả định token contract yêu cầu các attributes đang dùng. Nếu endpoint đòi sub hoặc iss, nên kiểm tra required attributes **trước khi tạo Authentication hoặc trước business authorization**, không để controller dùng null làm identity.

**Không trả nguyên principal.getAttributes() ra API response**. Nó có thể chứa thông tin token, client, tenant hoặc claims nhạy cảm. Trả DTO đã chọn fields phù hợp.

### Lấy BearerTokenAuthentication trực tiếp

Spring Security WebFlux cho phép controller nhận Authentication:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class SubjectController {

    @GetMapping("/api/subject")
    public Mono<String> subject(BearerTokenAuthentication authentication) {
        Object subject =
                authentication.getTokenAttributes().get("sub");
        return Mono.just(String.valueOf(subject));
    }
}
~~~

Đây là ví dụ chỉ để thấy **getTokenAttributes()**. Nếu API hỗ trợ service-client không có sub, không trả string "null" làm identity thật; phải có policy phân loại principal. Nếu custom authentication converter thay BearerTokenAuthentication, controller phải dùng type thích hợp.

## 16. ReactiveSecurityContextHolder trong service

Trong WebFlux, security context đi theo **Reactor Context**, không nên phụ thuộc ThreadLocal như một bảo đảm duy nhất.

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import reactor.core.publisher.Mono;

public final class CallerIdentityService {

    public Mono<String> currentSubject() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .filter(BearerTokenAuthentication.class::isInstance)
                .cast(BearerTokenAuthentication.class)
                .flatMap(auth -> Mono.justOrEmpty(
                        auth.getTokenAttributes().get("sub")))
                .ofType(String.class);
    }
}
~~~

Nếu Authentication không phải BearerTokenAuthentication hoặc sub thiếu, Mono có thể rỗng. Ứng dụng cần policy cho missing identity; không dùng Mono.empty() như quyền mặc định.

### Tránh block()

Không làm:

~~~java
Authentication auth =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .block();
~~~

Blocking event-loop có thể gây giảm hiệu năng hoặc lỗi runtime. Dùng map/flatMap/filter/switchIfEmpty và Reactor context propagation. Không tự đưa raw token vào ThreadLocal toàn cục để chữa tình trạng context không tìm thấy.

## 17. getName(), sub và client_id không luôn tương đương

Một token user-delegated có thể:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "shop-web",
  "scope": "orders.read"
}
~~~

Ở đây **sub** là subject; **client_id** là OAuth client được cấp token. Trong opaque flow mặc định, Authentication.getName() thường dựa vào sub khi có.

Token client_credentials có thể chỉ có:

~~~json
{
  "active": true,
  "client_id": "billing-worker",
  "scope": "orders.sync",
  "aud": ["orders-api"]
}
~~~

Nó có thể đại diện một **machine client**, không phải human user. Không mặc định:

~~~text
client_id == sub == internalUserId == human user
~~~

Một API có thể cần hai identity models:

- **USER actor**: issuer + subject + client + tenant context, các quyền user-delegated.
- **CLIENT actor**: issuer + client ID, các quyền machine-to-machine.

Không tự lấy client_id thay sub cho endpoint chỉ dành cho human user. Ngược lại, cũng không đòi sub cho mọi M2M flow nếu issuer contract không cung cấp nó.

### Multi-issuer subject collision

~~~text
Issuer A, sub=123
Issuer B, sub=123
~~~

có thể là hai actors khác nhau. Khi map tới local identities, nên dùng **(issuer, subject)** hoặc một quy tắc identity linking đáng tin. getName một mình không phải global identifier.

## 18. Normalizing principal thành domain identity

Ví dụ principal có:

~~~text
iss=https://auth.example.com/realms/shop
sub=user-42
client_id=shop-web
tenant_id=tenant-blue
scope=orders.read orders.write
~~~

Domain có thể cần một DTO do ứng dụng tự định nghĩa:

~~~text
CallerIdentity:
  issuer
  subject
  clientId
  tenantId
  actorKind = USER or CLIENT
~~~

Nhưng đừng dùng raw HTTP header X-Tenant-ID như một phần danh tính đáng tin mà không kiểm tra tenant membership. Có thể caller tự chọn requestedTenantId trong URL, còn authenticated principal/permission store phải chứng minh caller có quyền với tenant đó.

**Attributes là dữ liệu đầu vào authorization, không phải quyền bất biến tự động**. Với quyền cần freshness cao, domain có thể truy vấn membership/current entitlements thay vì chỉ dùng snapshot claims.

## 19. Tùy biến authorities bằng ReactiveOpaqueTokenIntrospector decorator

Khi có hợp đồng rõ rằng scope orders.write có thể map sang quyền nội bộ PERM_orders.create, bạn có thể decorate một introspector tin cậy:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    ReactiveOpaqueTokenIntrospector delegate =
            SpringReactiveOpaqueTokenIntrospector
                    .withIntrospectionUri(
                            "https://auth.example.com/oauth2/introspect")
                    .clientId("orders-api-introspector")
                    .clientSecret(
                            System.getenv("INTROSPECTION_CLIENT_SECRET"))
                    .build();

    return token -> delegate.introspect(token)
            .map(principal -> {
                List<GrantedAuthority> mapped =
                        new ArrayList<>(principal.getAuthorities());

                boolean hasWriteScope =
                        mapped.stream().anyMatch(a ->
                                "SCOPE_orders.write"
                                        .equals(a.getAuthority()));

                if (hasWriteScope) {
                    mapped.add(new SimpleGrantedAuthority(
                            "PERM_orders.create"));
                }

                return new DefaultOAuth2AuthenticatedPrincipal(
                        principal.getName(),
                        principal.getAttributes(),
                        mapped);
            });
}
~~~

Đây là minh họa với Spring Security version có builder **SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri**. Secret phải được provision qua secret manager và được kiểm tra lúc khởi động; không hardcode credential thật.

Các giả định an toàn:

1. **Delegate** đã introspect token qua AS đáng tin.
2. **SCOPE_orders.write** là scope có semantics ổn định theo issuer contract.
3. Mapping sang **PERM_orders.create** đã được bảo mật nghiệp vụ phê duyệt.
4. Giữ các authorities cũ, chỉ thêm quyền có quy tắc rõ.
5. Domain vẫn cần kiểm tra tenant/ownership và current state.
6. Error từ delegate được giữ nguyên, không biến lỗi thành success.

### Không tự map bất kỳ role attribute thành ADMIN

Nếu AS trả roles=["ADMIN"], không nên map thành ROLE_ADMIN chỉ vì tên giống nhau. Cần biết issuer, client/actor kind, claim ownership và semantics của AS. Một claim bị client tự điều khiển hoặc thiếu trust contract không được phép nâng quyền nội bộ.

### Không biến lỗi mạng thành default principal

Sai:

~~~java
return delegate.introspect(token)
        .onErrorReturn(defaultAuthenticatedPrincipal);
~~~

Khi AS 401/timeout hoặc token inactive, không có xác nhận danh tính. Phải fail closed.

## 20. ReactiveOpaqueTokenAuthenticationConverter khác Bearer converter đầu vào

Spring Security có hai converters dễ nhầm:

| Converter | Input | Output | Thời điểm |
|---|---|---|---|
| **ServerBearerTokenAuthenticationConverter** | ServerWebExchange | BearerTokenAuthenticationToken chưa authenticated | Trước introspection |
| **ReactiveOpaqueTokenAuthenticationConverter** | Raw token + OAuth2AuthenticatedPrincipal | Mono<Authentication> đã xác thực | Sau introspection thành công |

ReactiveOpaqueTokenAuthenticationConverter có chữ ký khái niệm:

~~~java
Mono<Authentication> convert(
        String introspectedToken,
        OAuth2AuthenticatedPrincipal authenticatedPrincipal);
~~~

Nó được OpaqueTokenReactiveAuthenticationManager sử dụng. Khi ứng dụng muốn thay default BearerTokenAuthentication hoặc mapping authorities ở Authentication-level, có thể custom extension point này theo framework version.

**Nhưng phần lớn ứng dụng không cần tạo Authentication type riêng**. OpaqueTokenIntrospector decorator phù hợp hơn nếu chỉ cần thêm authorities dựa trên introspection response đáng tin.

Khi custom authentication converter, phải giữ semantics của verified OAuth2AccessToken, authorities và authentication state. Những phiên bản mới có thể thêm factor-related authorities; một converter tự viết không nên vô tình làm mất security requirements của framework.

## 21. Method security sau introspection

Một method-level rule:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

public class OrdersService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<Order> readOrder(String id) {
        return repository.findById(id);
    }
}
~~~

Đây là fragment minh họa; **Order** và **repository** là types/objects của ứng dụng. Cần bật reactive method security phù hợp và dùng reactive return types để interceptor có thể thực thi policy.

**PreAuthorize không tự gọi introspection**. Nó dùng Authentication đã được pipeline đặt vào reactive context. Nếu token inactive, principal không được tạo thành authentication thành công.

### Chỉ scope chưa đủ cho object-level policy

Một user có SCOPE_orders.read có thể vẫn không được xem order của tenant khác. Policy có thể là:

~~~text
Authenticated
AND hasAuthority("SCOPE_orders.read")
AND order.tenantId == authorizedTenantForPrincipal
AND currentMembershipAllowsRead
~~~

Những checks này thuộc authorization; không cần nhồi hết vào OpaqueTokenIntrospector, đặc biệt khi chúng phụ thuộc state của order trong database.

## 22. Missing claims và sai kiểu dữ liệu

Nếu introspection trả:

~~~json
{
  "active": true,
  "client_id": "shop-web",
  "scope": "orders.read"
}
~~~

nhưng endpoint yêu cầu user subject, phải có policy rõ: thiếu sub là lỗi token contract/actor type hay endpoint chỉ cho service client?

Không làm:

~~~text
Missing sub -> dùng "anonymous" làm subject
Missing tenant -> cho truy cập tenant mặc định
Unknown role -> cấp ROLE_USER cùng nhiều quyền mặc định
~~~

Điều này có thể gây identity confusion hoặc unauthorized access.

### Tránh ClassCastException

Không giả định scope luôn là String:

~~~java
Object scopeValue = principal.getAttributes().get("scope");

if (scopeValue instanceof List<?> scopes) {
    // Kiểm tra phần tử và schema theo contract.
}
~~~

Để kiểm tra quyền, dùng authorities:

~~~java
boolean mayRead =
        authentication.getAuthorities().stream()
                .anyMatch(a ->
                        "SCOPE_orders.read".equals(a.getAuthority()));
~~~

Các field thời gian có thể là Instant sau normalization, không nhất thiết Long. Các audience có thể là collection. Cần biết Java types thực tế trước khi cast.

## 23. Khi nào principal được tin?

OAuth2AuthenticatedPrincipal là interface Java, có thể được tạo thủ công bởi bất kỳ code nào. **Trust đến từ quy trình tạo ra nó**, không từ tên class.

Một principal sử dụng để tạo Authentication cần thỏa mãn:

1. Token đến từ nguồn credential được phép.
2. Introspection URI/store thuộc trust domain của ứng dụng.
3. RS có client credentials hợp lệ và TLS certificate validation.
4. Response hợp lệ có active=true.
5. Token type và resource binding phù hợp khi API yêu cầu.
6. Subject/client/issuer/tenant attributes được kiểm tra đúng contract.
7. Các authorities chỉ được map từ claims đáng tin theo policy.
8. Multi-issuer names không bị trộn namespace.
9. AS unavailable không dẫn đến principal mặc định.
10. Cache không làm vô hiệu revocation/freshness policy.

Một custom introspector có thể hợp lệ nếu nó xác minh token qua local trusted token store thay vì HTTP AS, nhưng vẫn phải thực thi security contract tương đương.

## 24. Secret handling: BearerTokenAuthentication không phải API response

Bearer token là credential có thể được trình bày lại. BearerTokenAuthentication chứa verified OAuth2AccessToken nhưng **không có nghĩa được phép trả getToken().getTokenValue() về browser hoặc logs**.

Không ghi:

- Raw Authorization header.
- Form body token của introspection.
- Client ID/secret kết hợp thành Basic header.
- Full principal attributes chứa PII, tenant secret hoặc domain metadata.
- Authentication.toString() nếu chưa biết dữ liệu nhạy cảm được che hay chưa.
- Raw token làm correlation ID hoặc metric label.

Thay vào đó có thể dùng:

~~~text
requestId
configuredIssuerId
principalKind USER/CLIENT
introspectionOutcome active/inactive/auth_error/network_error
authenticationType
grantedAuthorityCount
httpStatus
latency
~~~

Dữ liệu chưa verify không được dùng làm fact tin cậy hoặc unbounded metric labels.

## 25. Cache principal và rủi ro revocation

Một cache có thể lưu OAuth2AuthenticatedPrincipal để giảm số HTTP introspection calls:

~~~text
T0 AS trả active=true, scope=orders.write.
T1 RS cache kết quả 60 giây.
T2 AS revoke token.
T3 RS có thể tiếp tục thấy principal cached đến khi TTL hết.
~~~

Cần xác định:

- TTL theo access token exp và revocation SLA.
- Cache key có phân tách issuer/introspection endpoint/resource context.
- Không cache timeout/AS 401 như token active=false.
- Không cache một principal theo sub rồi dùng cho mọi token của user.
- Không trả principal cached đã hết validity khi AS outage, trừ khi trust policy cho phép stale positive result trong cửa sổ hữu hạn.
- Bound cache size và chống token-flood.

**Cache principal không chỉ là tối ưu hiệu năng; nó quyết định độ trễ hiệu lực của revoke và thay đổi quyền.**

## 26. Reactive I/O và xử lý lỗi an toàn

Trong WebFlux, tránh:

~~~java
// Không nên block trong reactive event loop.
OAuth2AuthenticatedPrincipal principal =
        delegate.introspect(token).block();
~~~

Dùng reactive composition:

~~~java
return delegate.introspect(token)
        .map(principal -> adaptPrincipal(principal));
~~~

Nếu cần truy vấn database quyền hiện hành, dùng reactive data access hoặc phân lớp xử lý blocking I/O được framework hỗ trợ, không nhồi code chặn event-loop trong map.

### Retry khi introspection lỗi

| Trạng thái AS | Có retry không? |
|---|---|
| 200 active=false | Không retry mong token trở thành active |
| 401 invalid_client | Không retry vô hạn với cùng secret |
| 403 thiếu quyền introspect | Sửa IAM/config |
| 400 invalid_request | Sửa request/protocol |
| 429 rate limit | Bounded backoff, tôn trọng quota |
| 502/503/504 | Có thể retry giới hạn |
| DNS/connect/read timeout | Có thể retry giới hạn theo deadline |
| TLS certificate validation failure | Sửa truststore/cert, không tắt TLS |

Một error ở hop RS -> AS **không được biến thành OAuth2AuthenticatedPrincipal thành công**. Fail closed là yêu cầu tối thiểu.

## 27. Unit test BearerTokenAuthentication structure

Test này chỉ chứng minh cấu trúc Java, không thực hiện HTTP introspection:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

class BearerAuthenticationStructureTest {

    @Test
    void exposesPrincipalAttributesAndAuthorities() {
        OAuth2AuthenticatedPrincipal principal =
                new DefaultOAuth2AuthenticatedPrincipal(
                        "user-42",
                        Map.of("sub", "user-42",
                               "client_id", "shop-web"),
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_orders.read")));

        Instant now = Instant.now();

        OAuth2AccessToken credential =
                new OAuth2AccessToken(
                        OAuth2AccessToken.TokenType.BEARER,
                        "synthetic-test-token",
                        now,
                        now.plusSeconds(300),
                        Set.of("orders.read"));

        BearerTokenAuthentication auth =
                new BearerTokenAuthentication(
                        principal, credential, principal.getAuthorities());

        assertThat(auth.isAuthenticated()).isTrue();
        assertThat(auth.getPrincipal()).isSameAs(principal);
        assertThat(auth.getName()).isEqualTo("user-42");
        assertThat(auth.getTokenAttributes().get("sub"))
                .isEqualTo("user-42");
        assertThat(auth.getAuthorities())
                .extracting("authority")
                .contains("SCOPE_orders.read");
    }
}
~~~

**Không coi test này là bằng chứng raw token đã qua introspection**. Nó tự tạo principal và Authentication. Test integration thực tế còn phải xác minh active=false, AS credentials, network errors, scope mapping và WebFlux SecurityWebFilterChain.

## 28. Bộ kịch bản kiểm thử reactive introspection

Đây là các tình huống **kỳ vọng thiết kế**, không phải kết quả tests đã chạy:

| Stub AS / input | Kỳ vọng Resource Server |
|---|---|
| HTTP 200 active=true, scope=orders.read | Tạo OAuth2AuthenticatedPrincipal/BearerTokenAuthentication |
| HTTP 200 active=true, thiếu orders.write | GET có thể pass, POST thường 403 |
| HTTP 200 active=false | Không authenticated, thường 401 |
| HTTP 200 malformed JSON | Fail closed, protocol error |
| HTTP 401 invalid_client | Không kết luận user token invalid; dependency/config failure |
| HTTP 403 từ AS | Không kết luận user thiếu OAuth scope |
| HTTP 429/503 | Fail closed, bounded retry/circuit breaker |
| DNS/TLS/timeout | Fail closed, giữ nguyên nhân network |
| sub missing nhưng user endpoint bắt buộc sub | Reject theo token/actor contract |
| client_credentials không có sub | Dùng machine actor policy, không giả user |
| scope là List sau normalization | Mapping authorities hoạt động |
| roles provider-specific | Không tự map ROLE_ADMIN |
| Principal có SCOPE_orders.read | Authentication có authority để authorize |
| Principal active, sai audience | Reject nếu audience/resource binding bắt buộc |
| Principal active, tenant mismatch | Domain authorization từ chối |
| Multi-issuer cùng sub | Không trộn identity |
| Cached active result stale sau revoke | Hành vi đúng TTL/invalidation policy |

Nên tách các tầng:

1. **Unit test principal object/mapping**: DefaultOAuth2AuthenticatedPrincipal và BearerTokenAuthentication.
2. **Introspection contract test**: HTTP stub cho RFC 7662, active, attributes, credentials và errors.
3. **WebFlux SecurityWebFilterChain test**: Bearer filter, manager, 401/403, WWW-Authenticate và authorities.
4. **Domain authorization test**: tenant/ownership/actor kind và quyền hiện hành.

Spring Security Test **mockOpaqueToken()** thuận tiện cho authorization tests nhưng có thể tạo authentication giả mà không gọi AS thật; không dùng nó làm bằng chứng introspection HTTP đã đúng.

## 29. Những vấn đề thường gặp khi gỡ lỗi

### Vì sao principal không phải Jwt?

Vì ứng dụng cấu hình **opaque token Resource Server**. Principal mặc định là OAuth2AuthenticatedPrincipal trong BearerTokenAuthentication. Nếu controller cast sang Jwt, sẽ sai type. Dùng đúng abstraction hoặc normalize một domain identity sau authentication.

### Vì sao getName không bằng username?

AS có thể định nghĩa sub khác username, hoặc token là client_credentials. Không dùng getName làm email/global user key nếu chưa có contract.

### Vì sao scope attribute có nhưng hasAuthority false?

Có thể scope đã được chuẩn hóa thành List, custom mapper sai type, converter thay prefix SCOPE_, policy dùng ROLE_ thay SCOPE_, hoặc SecurityWebFilterChain khác đang xử lý. Kiểm tra **Authentication.getAuthorities()**, không chỉ raw scope attribute.

### Vì sao principal thiếu sub?

Token có thể là client_credentials hoặc AS không công bố subject. User endpoint phải có required-sub policy; M2M endpoint có actor contract riêng.

### Vì sao getTokenAttributes khác JSON nguyên văn?

Introspection implementation có thể chuẩn hóa scope, exp, iat, aud và các Java types. Custom decorator cũng có thể đổi attributes. Đừng giả định wire JSON type giống Java type.

### Vì sao mọi token cùng bị 401 sau deploy?

Có thể RS introspection client secret hoặc endpoint bị cấu hình sai. AS HTTP 401 invalid_client **không chứng minh** mọi user token inactive. Phân biệt upstream status và client-facing status.

### Vì sao token active nhưng vẫn 403?

Có thể thiếu scope, tenant membership, ownership hoặc permission hiện hành. active=true chỉ là kết quả token validity, không phải domain authorization.

## 30. Những anti-pattern thường gặp

| Sai lầm | Vấn đề | Cách làm đúng |
|---|---|---|
| Coi BearerTokenAuthenticationToken là verified Authentication | Token chưa được kiểm tra | Introspection trước khi tạo Authentication |
| Tạo OAuth2AuthenticatedPrincipal từ HTTP header chưa tin | Identity spoofing | Trusted introspector |
| active=false nhưng tạo principal mặc định | Fail open | Giữ authentication failure |
| AS timeout nhưng tự cho qua | Bypass token validation | Fail closed |
| Cast opaque principal sang Jwt | Sai type | OAuth2AuthenticatedPrincipal |
| Dùng getName như global user ID | Collision giữa issuers và machine clients | issuer + subject/client contract |
| Map roles tùy tiện thành ROLE_ADMIN | Privilege escalation | Mapping theo trusted issuer |
| Kiểm tra scope attribute nhưng bỏ GrantedAuthority | Authorization không nhất quán | Authentication.getAuthorities |
| active=true là đủ mọi endpoint | Bỏ domain policy | Scope + tenant + ownership |
| Bỏ audience/resource binding | Token của API khác có thể được dùng | Token contract validation |
| Trả toàn bộ principal attributes về browser | Rò metadata/PII | DTO chọn fields |
| Log access token từ BearerTokenAuthentication | Credential exposure | Sanitized telemetry |
| Dựa ThreadLocal SecurityContext trong WebFlux | Context propagation sai | ReactiveSecurityContextHolder |
| block() trong request pipeline | Chặn event-loop | Mono/Flux composition |
| Dùng mock introspector trong production | Bỏ AS verification | Fake chỉ dành cho unit tests |
| Cache principal theo sub, bỏ token/issuer | Trộn sessions/trust domains | Cache key theo token và issuer |
| Custom converter làm mất factor authorities | Thay đổi authentication semantics | Giữ version-specific contract |
| Dùng Servlet Provider/HttpSecurity cho WebFlux | Sai integration | Reactive manager/ServerHttpSecurity |

## 31. Tổng kết

~~~text
Client Bearer opaque token
          |
          v
ReactiveOpaqueTokenIntrospector
  trusted active=true response
          |
          v
OAuth2AuthenticatedPrincipal
  - getName()
  - getAttributes()
  - getAuthorities()
          |
          v
OpaqueTokenReactiveAuthenticationManager
  + ReactiveOpaqueTokenAuthenticationConverter
          |
          v
BearerTokenAuthentication
  - OAuth2AuthenticatedPrincipal principal
  - verified OAuth2AccessToken
  - authorities
  - token attributes
          |
          v
ReactiveSecurityContextHolder
          |
          v
Scope / tenant / business authorization
~~~

Những nguyên tắc chính:

1. **ReactiveOpaqueTokenIntrospector trả OAuth2AuthenticatedPrincipal sau introspection thành công**, không trả Authentication result.
2. **OpaqueTokenReactiveAuthenticationManager** tạo Authentication, mặc định **BearerTokenAuthentication**, qua converter phù hợp.
3. **BearerTokenAuthenticationToken là request chưa xác thực**, khác BearerTokenAuthentication đã xác thực.
4. **Attributes khác authorities**; scope thường được ánh xạ thành SCOPE_ authorities.
5. **getName, sub và client_id khác semantics**; có user token và machine-client token.
6. **Trong WebFlux dùng @AuthenticationPrincipal hoặc ReactiveSecurityContextHolder** để đọc trusted principal, không block.
7. **Không biến active=false hoặc AS outage thành principal hợp lệ**; luôn fail closed.
8. **Token active chưa đủ quyền hành động**; cần kiểm tra audience, scopes, tenant và domain policy.
9. **Bearer token và introspection credentials là secrets**, không log hoặc trả ra response.
10. **Tách unit tests của principal, contract tests của introspection và SecurityWebFilterChain integration tests**.

**Kết luận:** Trong opaque-token Resource Server WebFlux, OAuth2AuthenticatedPrincipal là kết quả danh tính và thuộc tính từ introspection đáng tin; BearerTokenAuthentication là Authentication bao bọc principal cùng verified access token và authorities. Hiểu đúng hai đối tượng giúp mở rộng mapping an toàn và giữ ranh giới rõ ràng giữa authentication và authorization.

## 32. Tài liệu tham khảo

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Opaque Token:** introspection, principal, BearerTokenAuthentication, authority mapping và custom introspector. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security API — OAuth2AuthenticatedPrincipal:** name, attributes và authorities. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html
- **Spring Security API — DefaultOAuth2AuthenticatedPrincipal:** implementation và constructors. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html
- **Spring Security API — BearerTokenAuthentication:** principal, OAuth2AccessToken và getTokenAttributes. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html
- **Spring Security API — BearerTokenAuthenticationToken:** authentication request Bearer. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthenticationToken.html
- **Spring Security API — ReactiveOpaqueTokenIntrospector:** Mono<OAuth2AuthenticatedPrincipal>. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
- **Spring Security API — SpringReactiveOpaqueTokenIntrospector:** AS introspection client. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html
- **Spring Security API — OpaqueTokenReactiveAuthenticationManager:** reactive opaque Authentication manager. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html
- **Spring Security API — ReactiveOpaqueTokenAuthenticationConverter:** chuyển principal thành Authentication. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenAuthenticationConverter.html
- **Spring Security Reference — WebFlux Security:** SecurityWebFilterChain/ServerHttpSecurity. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **Spring Security Reference — Reactive Method Security:** @EnableReactiveMethodSecurity và @PreAuthorize. https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- **RFC 7662 — OAuth 2.0 Token Introspection:** active và metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer credentials và HTTP errors. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 6749 — OAuth 2.0 Framework:** OAuth client, scope và access token. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 7519 — JWT:** đối chiếu JWT claims với opaque introspection attributes. https://www.rfc-editor.org/rfc/rfc7519
