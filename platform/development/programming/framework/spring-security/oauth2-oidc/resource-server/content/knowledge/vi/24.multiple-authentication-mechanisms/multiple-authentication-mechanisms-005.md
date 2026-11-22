# Lỗi ở một chiến lược không tự trở thành lý do thử mọi nguồn tin cậy

## 1. Bài toán: nhiều cách xác thực, nhưng không được tìm cách xác thực cho bằng được

Một API sử dụng **Spring Security OAuth 2.0/OIDC Resource Server** đôi khi cần hỗ trợ đồng thời:

- JWT Bearer token từ Authorization Server (AS) A.
- JWT Bearer token từ AS B.
- Opaque Bearer token xác minh bằng token introspection.
- HTTP Basic trên một endpoint vận hành được giới hạn.
- OIDC Login + session cookie cho giao diện trình duyệt.
- mTLS, API key hoặc identity từ một trusted reverse proxy.
- Nhiều SecurityFilterChain hay SecurityWebFilterChain cho các vùng tài nguyên khác nhau.

Sự đa dạng này **không có nghĩa** một request không xác thực được bằng chiến lược A thì Resource Server nên tự động thử B, C, D đến khi có chiến lược thành công.

Ví dụ về logic nguy hiểm:

~~~text
Authorization: Bearer TOKEN_X
           |
           v
Verify JWT bằng trusted issuer A
  -> Signature invalid
           |
           v
Thử JWT issuer B
  -> Issuer mismatch
           |
           v
Thử introspection tại AS C
  -> active=true
           |
           v
Tạo Authentication và cho request đi tiếp
~~~

Nếu endpoint chỉ cho phép access token từ issuer A, request trên **phải bị từ chối**. Việc AS C nhận diện TOKEN_X không làm nó đủ điều kiện truy cập route của issuer A.

Nguyên tắc trung tâm:

> **Lỗi xác thực ở một chiến lược không phải tín hiệu mở rộng tập nguồn tin cậy. Chọn một chiến lược được phép theo security policy trước, rồi xác thực credential bằng chiến lược đó; thất bại không tự động cho phép đổi chiến lược.**

Điều này không cấm hỗ trợ nhiều phương thức. Nó đòi hỏi cách chọn phương thức, trust boundary, loại credential và authorization contract **được định nghĩa rõ từ trước**.

## 2. Phân biệt không áp dụng, xác thực thất bại, thành công và lỗi phụ thuộc

Bốn trạng thái cần tách:

| Trạng thái logic | Mô tả | Phản ứng an toàn |
|---|---|---|
| **NOT_APPLICABLE** | Một mechanism không dành cho credential hoặc route này | Có thể dùng mechanism khác **nếu policy cho phép** |
| **AUTHENTICATION_FAILURE** | Credential thuộc mechanism đã chọn nhưng không vượt qua kiểm tra | Từ chối; không thử mọi AS/provider khác |
| **AUTHENTICATION_SUCCESS** | Credential qua các điều kiện của trust domain đã chọn | Tạo Authentication rồi xét quyền |
| **DEPENDENCY_FAILURE** | JWKS, introspection endpoint, TLS, mạng hoặc credentials nội bộ gặp lỗi | Fail closed; không biến thành success ở nguồn khác |

Ví dụ:

~~~text
Request 1:
  /api/orders
  Authorization: Bearer JWT_A
  Strategy contract: issuer A JWT
  Signature invalid
  -> AUTHENTICATION_FAILURE

Request 2:
  /api/legacy/orders
  Authorization: Bearer OPAQUE_B
  Strategy contract: AS B introspection
  active=true
  -> AUTHENTICATION_SUCCESS

Request 3:
  /api/orders
  Không có Authorization header
  -> Không có Bearer credential
  -> Protected endpoint thường 401

Request 4:
  /api/orders
  Authorization: Bearer JWT_A
  JWKS A timeout
  -> DEPENDENCY_FAILURE
  -> Không hỏi JWKS B để cứu request
~~~

**NOT_APPLICABLE không đồng nghĩa AUTHENTICATION_FAILURE.** Nếu gộp hai loại thành một fallback branch, hệ thống dễ chấp nhận credential bằng một trust domain trái hợp đồng.

## 3. Trust selection phải xảy ra trước token acceptance

Ba bước kiến trúc:

~~~text
HTTP Request
    |
    v
TRUST SELECTION
  - Route/security zone
  - Credential scheme được phép
  - Trusted issuer/tenant allow-list
  - Gateway-protected metadata nếu có
    |
    v
AUTHENTICATION
  - JWT: JWS, iss, aud, exp, nbf, typ
  - Opaque: trusted introspection + active + audience
  - Basic: password/credential verification
  - mTLS: trusted certificate chain
    |
    v
AUTHORIZATION
  - Scope/authority
  - Actor kind USER/CLIENT
  - Tenant membership
  - Ownership và business policy
~~~

Một request bị JWT signature validation từ chối không được quay lại **TRUST SELECTION** để thử một AS khác chỉ vì thất bại. Trust routing là **policy**, không phải thuật toán đoán từ exception.

### Route và issuer có vai trò khác nhau

Đường dẫn /api/orders có thể quyết định **route chỉ tin issuer A**. Claim iss trong JWT có thể giúp định tuyến bên trong nhóm issuers được phép, nhưng nó còn **chưa được xác minh**. Nó không được tự thêm issuer mới vào danh sách tin cậy.

### Authentication success chưa phải authorization success

Một AS có thể xác thực user hợp lệ nhưng user không thuộc tenant của order. Authentication tạo principal tin cậy; authorization vẫn có thể trả 403 hoặc phản hồi domain phù hợp.

## 4. Vì sao fallback tùy tiện nguy hiểm?

Giả sử code có ý tưởng:

~~~java
// Pseudo-code về ý tưởng sai, không phải đoạn Java hoàn chỉnh.
try {
    return validateJwt(token);
}
catch (AuthenticationException ex) {
    return introspectAtAnotherIssuer(token);
}
~~~

Rủi ro:

1. **Downgrade**: JWT validator mạnh từ chối nhưng backend khác áp dụng contract lỏng hơn.
2. **Token substitution**: token cấp cho API B được chấp nhận tại API A.
3. **Issuer confusion**: nhiều trusted issuers bị gộp thành một namespace.
4. **Principal confusion**: một raw credential có thể được map thành hai danh tính khác nhau.
5. **Credential leakage**: cùng token bị gửi đến nhiều introspection endpoints không có quyền nhận.
6. **Network amplification**: attacker gửi invalid token khiến RS gọi mọi backend.
7. **SSRF**: nếu key/metadata URI đến từ JWT chưa verify, request có thể hướng tới địa chỉ do attacker kiểm soát.
8. **Khó audit**: không rõ request được chấp nhận theo chính sách nào.
9. **Availability degradation**: một AS outage tạo thác retry lên các AS không liên quan.
10. **MFA/auth-factor downgrade**: request thất bại ở cơ chế yêu cầu factor cao rồi được cơ chế yếu hơn chấp nhận.

**Nhiều nguồn tin cậy không có nghĩa mọi nguồn được phép chứng thực mọi hành động.**

## 5. Định tuyến hợp lệ khác fallback sau lỗi

| Tình huống | Đúng hay sai? | Giải thích |
|---|---|---|
| /api/v2/** chọn JWT từ đầu | Đúng | Route contract rõ |
| /api/legacy/** chọn opaque từ đầu | Đúng | Route contract rõ |
| JWT sai chữ ký rồi thử introspection | Sai nếu không có policy cho phép | Credential đã bị bác theo chiến lược bắt buộc |
| JWT iss lạ rồi tạo decoder từ URL issuer đó | Sai | Mở trust source do caller kiểm soát |
| JWT issuer A sai signature rồi thử issuer B | Sai | Không được dò key khác issuer |
| User Bearer invalid nhưng cookie session còn hạn | Sai nếu route Bearer-only | Session không được cứu Bearer |
| AS A trả active=false rồi hỏi mọi AS khác | Sai | Dò tìm authority sẽ chấp nhận |
| JWKS A cache có cả key cũ và mới khi rotation | Có thể đúng | Cùng trust domain, không đổi issuer |
| Dùng JWKS cached từ issuer A khi A tạm unavailable | Có thể đúng | Key cache đáng tin và còn trong policy |
| Failover tới replica của cùng AS có TLS và policy tương đương | Có thể đúng | Resilience, không đổi authority |
| HTTP Basic cho /ops/** và JWT cho /api/** | Đúng khi tách boundaries | Hai mechanisms dùng đúng route |
| Endpoint thực sự cho phép cả session và Bearer | Cần thiết kế rõ | Phải có precedence, CSRF, collision policy |

Không phải cứ có từ **fallback** là sai. Cần phân biệt **failover hạ tầng trong cùng trust domain** với **chuyển sang authority khác để thay đổi kết quả xác thực**.

## 6. Một bước chọn chiến lược an toàn

~~~mermaid
flowchart TD
    A["Request tới API"] --> B{"Route thuộc trust zone nào?"}
    B -->|"/api/v2/*"| J["JWT issuer A policy"]
    B -->|"/api/legacy/*"| O["Opaque AS B policy"]
    B -->|"/ops/*"| H["Ops Basic/mTLS policy"]
    B -->|"Không khớp"| D["Deny"]
    J --> VJ{"JWT verified?"}
    O --> VO{"Introspection active & valid?"}
    H --> VH{"Ops credential valid?"}
    VJ -->|"No"| F["Reject, no cross-strategy fallback"]
    VO -->|"No"| F
    VH -->|"No"| F
    VJ -->|"Yes"| Z["Scope / domain authorization"]
    VO -->|"Yes"| Z
    VH -->|"Yes"| Z
~~~

Đây là **sơ đồ policy**, không phải khẳng định filter chain nào cũng chạy đúng thứ tự từng node. Các APIs/handlers thực tế phụ thuộc Servlet hay WebFlux, framework version và security configuration.

### Những tín hiệu routing có thể phù hợp

- Path hoặc security zone đã được cấu hình server-side.
- Ingress/virtual host được định tuyến và xác minh tại trusted gateway.
- HTTP authentication scheme mà route chủ đích chấp nhận.
- Issuer nằm trong allow-list được cấu hình trước.
- Tenant context được xác minh qua nguồn tin cậy và cross-check sau authentication.

### Những tín hiệu không đủ làm bằng chứng trust

- Trường iss của JWT chưa verify.
- Header jku/x5u chứa JWKS URL do caller đưa ra.
- Query parameter provider=...
- JWT token có hai dấu chấm.
- X-User/X-Role/X-Tenant header từ Internet chưa qua gateway trust.
- Payload scope=admin trước signature verification.

Các tín hiệu trên đôi khi dùng làm **routing hint**, nhưng không bao giờ tự là **proof of identity**.

## 7. Spring Security ProviderManager có thể thử provider tiếp theo

Trong **Servlet Spring Security**, ProviderManager thường duyệt danh sách AuthenticationProvider để xác thực một Authentication request.

Theo API contract:

- ProviderManager kiểm tra các providers hỗ trợ loại Authentication.
- Provider có thể trả một Authentication đã xác thực, trả null hoặc ném AuthenticationException.
- Khi một provider trả kết quả thành công, Manager thường dừng.
- Nếu một provider trả null, provider sau có thể được thử.
- **Một số AuthenticationExceptions không chặn ProviderManager thử provider sau**; nếu provider sau thành công, lỗi của provider trước có thể được bỏ qua.
- Với các ngoại lệ như **AccountStatusException**, ProviderManager có hành vi dừng sớm.
- Nếu không provider nào hỗ trợ, có thể có ProviderNotFoundException.
- Parent AuthenticationManager có thể tham gia theo contract khi được cấu hình.

Vì vậy **không thể nói mọi AuthenticationException luôn làm ProviderManager dừng ngay**.

Ví dụ cấu trúc dễ gặp:

~~~java
AuthenticationManager manager =
        new ProviderManager(List.of(
                new JwtAuthenticationProvider(jwtDecoderA),
                new OpaqueTokenAuthenticationProvider(introspectorB)));
~~~

Cả hai providers có thể hỗ trợ loại **BearerTokenAuthenticationToken**. Nếu JWT provider không xác thực được, **không được mặc định tin rằng opaque provider chắc chắn không bao giờ được gọi**. Kết quả cụ thể phụ thuộc exception/ProviderManager behavior của version đang sử dụng.

### supports(Class) không phải issuer policy

AuthenticationProvider.supports cho biết provider có khả năng xử lý **loại Authentication**, không nhất thiết biết request dành cho issuer/tenant nào.

Hai providers cùng supports(BearerTokenAuthenticationToken.class) không tự phân biệt:

~~~text
Bearer JWT issuer A
Bearer JWT issuer B
Bearer opaque AS C
~~~

Nếu cần **issuer A failure is final**, nên dùng manager riêng/resolver chọn một manager phù hợp, thay vì mong supports hay thứ tự providers giải quyết security policy.

## 8. Đừng lạm dụng null hoặc exception để “định tuyến”

Một custom provider có thể viết:

~~~java
@Override
public Authentication authenticate(Authentication authentication) {
    if (isNotMine(authentication)) {
        return null;
    }
    return doAuthenticate(authentication);
}
~~~

Nếu **isNotMine** xác định bằng routing policy chắc chắn và được phép, null có thể phản ánh provider không xử lý loại credential đó theo contract.

Nhưng nếu token đã được chọn cho provider A mà **signature invalid**, không nên:

~~~java
catch (BadCredentialsException ex) {
    return null; // Cho provider B tiếp tục thử.
}
~~~

Làm vậy biến thất bại xác thực thành **không áp dụng**, khiến ProviderManager có cơ hội cho backend khác chấp nhận.

Cũng không nên ném một **AccountStatusException giả** để ép ProviderManager dừng: exception sai semantics làm audit và behavior khó kiểm soát. Hãy thay đổi **composition/routing** thay vì dùng exception như một công tắc security policy.

## 9. Servlet: SecurityFilterChain tách ranh giới API và Ops

Cách đơn giản là dùng hai routes có hợp đồng xác thực khác nhau:

- **/api/** chỉ chấp nhận Bearer JWT.
- **/ops/** dùng HTTP Basic cho khu vận hành, ví dụ minh họa.
- Các path chưa khai báo mặc định không được truy cập.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SegmentedSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain ops(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/ops/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain remaining(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .build();
    }
}
~~~

Đây là **ví dụ về việc chọn cơ chế**, chưa phải cấu hình production hoàn chỉnh. HTTP Basic phải đi qua TLS và user/password store phù hợp; khu vận hành nên có network isolation và có thể dùng SSO/mTLS. CSRF chỉ được tắt trong ví dụ /api/** **thuần stateless Bearer**, không áp dụng bừa cho các endpoint browser cookie/session.

### Hành vi mong đợi

~~~text
GET /api/orders
   -> JWT Resource Server policy
   -> JWT invalid: reject
   -> Không thử Basic của /ops

GET /ops/health
   -> Ops Basic policy
   -> Basic invalid: reject
   -> Không thử JWT issuer của /api
~~~

FilterChainProxy chọn chain khớp theo matcher/order; **không phải cứ chain A thất bại thì chạy chain B**. Đồng thời cần chắc chắn không có path bị bỏ bảo vệ do matcher sai.

## 10. Servlet: AuthenticationManagerResolver chọn JWT hoặc opaque theo route

Nếu một API cần dùng cả JWT và opaque Bearer token, Spring Security Reference minh họa **AuthenticationManagerResolver<HttpServletRequest>**.

Một resolver có route policy tường minh:

~~~java
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Bean
AuthenticationManagerResolver<HttpServletRequest> resourceManagers(
        JwtDecoder jwtDecoder,
        OpaqueTokenIntrospector introspector) {

    AuthenticationManager jwt =
            new ProviderManager(new JwtAuthenticationProvider(jwtDecoder));

    AuthenticationManager opaque =
            new ProviderManager(
                    new OpaqueTokenAuthenticationProvider(introspector));

    AuthenticationManager rejectUnknown = auth -> {
        throw new BadCredentialsException(
                "No allowed strategy for this route");
    };

    return request -> {
        String path = request.getServletPath();

        if (path.startsWith("/api/v2/")) {
            return jwt;
        }
        if (path.startsWith("/api/legacy/")) {
            return opaque;
        }
        return rejectUnknown;
    };
}
~~~

Gắn resolver:

~~~java
@Bean
SecurityFilterChain resourceApi(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> resourceManagers)
        throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth ->
                    auth.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.authenticationManagerResolver(resourceManagers))
            .build();
}
~~~

**Điểm quan trọng:** resolver chọn một manager **trước** khi thực hiện token validation.

- **/api/v2/**: JWT fail thì **không** thử opaque.
- **/api/legacy/**: opaque fail thì **không** thử JWT.
- Route lạ: manager từ chối thay vì mặc định chọn backend dễ dàng nhất.

Đây chỉ là ví dụ về trust-routing pattern. Với servlet context path, reverse proxy rewrite và URL encoding, cần thống nhất cách lấy route giữa securityMatcher và resolver. JWT decoder phải kiểm tra signature, iss, aud, time và token purpose; opaque introspector phải kiểm tra active, audience/resource contract và issuer khi phù hợp.

## 11. Chữ ký JWT sai không phải lý do hỏi introspection

Một anti-pattern:

~~~text
tryJwtDecode(token)
  |
  +-- SUCCESS -> Authenticate
  |
  +-- JwtException -> tryOpaqueIntrospection(token)
                        |
                        +-- active=true -> Authenticate
~~~

Nếu API yêu cầu JWT validator cho route thì nhánh trên có thể cho token sai signature/issuer/audience vượt qua bằng một backend khác. Đây là **thay đổi security contract**.

### Introspection cho JWT có bao giờ hợp lệ?

Có. Spring Security opaque-token support có thể introspect bất kỳ chuỗi token nào, kể cả JWT, nếu AS hỗ trợ. Một Resource Server có thể **chủ động chọn introspection từ đầu** để AS quyết định active/revoke.

Các chính sách khác nhau:

~~~text
Policy 1:
  JWT-only validation:
    accepted = signature AND issuer AND audience AND time

Policy 2:
  Introspection-only:
    accepted = trusted introspection says active
               AND resource/token contract

Policy 3:
  JWT verification + revocation check:
    accepted = valid JWT AND positive introspection
~~~

**Policy 2 hoặc 3 không phải fallback tự động khi policy 1 thất bại.** Hãy chọn policy có chủ đích. Nếu policy 3 yêu cầu cả hai, dùng logical **AND**, không dùng OR để cứu JWT không hợp lệ.

### AS introspection active=true vẫn cần kiểm tra resource contract

Một AS có thể biết token active, nhưng API còn phải xác minh token dành cho audience/resource hiện tại nếu AS không thực hiện kiểm tra đó thay. Token active cho billing-api không tự được gọi orders-api.

## 12. Multi-issuer JWT: chỉ tin các issuer trong allow-list

Giả sử Resource Server chấp nhận:

~~~text
Issuer A: https://auth-a.example.com/
Issuer B: https://auth-b.example.com/
~~~

JWT của caller khai:

~~~json
{
  "iss": "https://attacker.example.net/",
  "sub": "admin",
  "aud": ["orders-api"]
}
~~~

Đọc iss chưa verify rồi tự tạo JWT decoder từ đó là nguy hiểm: attacker có thể tự vận hành một AS, ký token bằng key của họ và yêu cầu API tin JWKS của họ.

Thiết kế đúng:

~~~text
Unverified iss claim
  chỉ là routing hint
          |
          v
Configured trusted issuer allow-list
          |
       +--+--+
       |     |
       v     v
     Iss A  Iss B
       |     |
       v     v
   Decoder A Decoder B
       |     |
       v     v
   Verify JWS signature for selected issuer
          |
          v
    Exact iss + aud + exp/nbf + type validation
          |
          v
     Authenticated principal
~~~

JWT khai iss=A nhưng signature không verify bằng trusted key của A **không được thử B để tìm một key khớp**.

## 13. JwtIssuerAuthenticationManagerResolver trong Servlet

Spring Security có **JwtIssuerAuthenticationManagerResolver** chọn manager theo issuer, với **trusted issuer allow-list**.

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://auth-a.example.com/",
                "https://auth-b.example.com/");
~~~

Áp dụng:

~~~java
http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
~~~

Đây là **chọn issuer từ tập được tin**, không phải thử A rồi B sau khi A fail.

Chú ý:

- iss lấy từ JWT trước verification chỉ dùng làm routing hint.
- Chỉ issuer trong allow-list mới được tạo manager/decoder.
- Mỗi decoder phải verify signature và **iss chính issuer đó**.
- Audience và access-token profile cần có validator phù hợp.
- Resource Server không được liên kết các subjects chỉ vì sub trùng nhau.
- Factory fromTrustedIssuers được hỗ trợ ở các Spring Security versions thích hợp; kiểm tra API nếu dùng phiên bản cũ.

### Không gộp kid giữa issuers

Hai issuers có thể cùng kid=signing-2026 nhưng public key khác nhau. kid chỉ có ý nghĩa trong trusted JWKS của issuer được chọn. Không sử dụng kid làm khóa của một global cache không phân namespace.

## 14. WebFlux: JwtIssuerReactiveAuthenticationManagerResolver

Trong **Spring Security WebFlux**, dùng resolver reactive, không dùng HttpServletRequest-based API.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveTrustedIssuers {

    @Bean
    SecurityWebFilterChain resourceApi(ServerHttpSecurity http) {
        JwtIssuerReactiveAuthenticationManagerResolver resolver =
                JwtIssuerReactiveAuthenticationManagerResolver
                        .fromTrustedIssuers(
                                "https://auth-a.example.com/",
                                "https://auth-b.example.com/");

        return http
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.authenticationManagerResolver(resolver))
                .build();
    }
}
~~~

WebFlux resolver dùng trusted issuer allow-list. Một issuer lạ không tự mở JWKS URL mới.

### Vì sao cần phân biệt Mono.empty và Mono.error?

Ở reactive API:

- **Mono.empty()** có thể diễn đạt không có kết quả/không áp dụng theo contract cụ thể.
- **Mono.error(AuthenticationException)** là failure.
- **Mono.just(Authentication)** là thành công.

Một custom reactive manager không được:

~~~java
return jwtManager.authenticate(authentication)
        .onErrorResume(ex ->
                opaqueManager.authenticate(authentication));
~~~

**onErrorResume catch-all không hiểu security semantics.** Nó có thể bắt cả JWT invalid, JWKS timeout, lỗi cấu hình, issuer mismatch rồi âm thầm đổi nguồn trust. Đừng dùng nó để tạo cơ chế “cứ lỗi là thử backend khác”.

## 15. WebFlux: tách SecurityWebFilterChain theo route

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSegmentedSecurity {

    @Bean
    @Order(1)
    SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/api/v2/**"))
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain opaqueApi(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/api/legacy/**"))
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain denyRemaining(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth ->
                        auth.anyExchange().denyAll())
                .build();
    }
}
~~~

Đây là ví dụ kiến trúc, cần cấu hình reactive JWT decoder, opaque introspector, CORS/CSRF, token profile và error handling thích hợp.

- Route JWT thất bại: **không tự chuyển sang opaque chain**.
- Route opaque thất bại: **không tự chuyển sang JWT chain**.
- Route không khớp: **deny**, không bỏ ngỏ.

**Không dùng HttpSecurity của Servlet trong WebFlux thuần**. Tương tự, một WebFilter tự gắn Authentication mà không verify credential có thể phá ranh giới security pipeline.

## 16. Opaque active=false không được hỏi mọi AS để tìm active=true

RFC 7662 cho phép introspection endpoint trả:

~~~json
{
  "active": false
}
~~~

Nghĩa là AS được chọn **không xác nhận token active**. Điều đó không phải lời mời hỏi các AS khác.

Một anti-pattern:

~~~text
AS A introspection:
  active=false
         |
         v
AS B introspection:
  active=false
         |
         v
AS C introspection:
  active=true
         |
         v
Authenticate as principal from AS C
~~~

Điều này có thể làm lộ Bearer token đến nhiều providers và khiến API nhận credential của một issuer không được cho phép cho route.

### Khác biệt inactive và upstream error

| Kết quả tại AS | Ý nghĩa | Hành động an toàn |
|---|---|---|
| 200 + active=true | Token active theo AS | Tiếp tục resource/authorization checks |
| 200 + active=false | Token inactive | Reject, không quét AS khác |
| 401 invalid_client | RS introspection credentials có vấn đề | Fail closed, sửa secret |
| 403 | RS không được phép introspect | Fail closed |
| 429 | AS throttling | Backoff/rate-limit theo policy |
| 5xx | AS unavailable | Fail closed |
| DNS/TLS/timeout | Network/trust dependency error | Fail closed |
| 200 malformed JSON | Protocol failure | Fail closed |

HTTP 401 của AS ở **hop Resource Server -> AS** không đồng nghĩa caller token ở **hop Client -> Resource Server** hết hạn. Cần phân loại hai nguồn lỗi.

## 17. Fail closed không có nghĩa mọi lỗi đều là 401

**Fail closed** nghĩa là protected operation không được phép thực hiện nếu không có authentication/authorization hợp lệ.

| Nguyên nhân | HTTP thường gặp | Authentication có thành công? |
|---|---|---|
| Protected route thiếu Bearer | 401 challenge | Không |
| JWT signature/issuer/audience sai | 401 invalid_token | Không |
| JWT expired | 401 invalid_token | Không |
| Opaque introspection active=false | 401 invalid_token | Không |
| Bearer transport malformed | 400/401 tùy resolver error | Không |
| Token hợp lệ thiếu scope | 403 insufficient_scope khi phù hợp | Có |
| Token hợp lệ nhưng sai tenant | 403 hoặc domain policy khác | Có |
| JWKS outage | Dependency failure, có thể 503 theo contract | Không |
| Introspection timeout | Dependency failure, có thể 503 theo contract | Không |
| CSRF/CORS/gateway denial | Có thể 403 | Không nhất thiết |

Không khẳng định Spring Security mặc định luôn trả 503 khi AS unavailable; behavior tùy exception, handler và version.

Điểm không thay đổi: **Không được trả success hoặc tạo authenticated principal giả chỉ vì cơ chế xác thực thật bị lỗi.**

## 18. Audience và token purpose ngăn token substitution

Một JWT:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1794731400
}
~~~

Dù chữ ký đúng, token không được dùng tại orders-api nếu aud không chứa orders-api. Không chuyển sang backend khác có audience checking yếu để chấp nhận nó.

**OAuth scope không thay audience**, và **client_id không thay aud**.

### OIDC ID token không phải access token

Một OIDC ID token dùng cho OIDC Client/Relying Party. Nó có thể cùng issuer/JWKS với access token nhưng khác audience và token purpose. Resource Server không được nhận ID token chỉ vì một fallback introspector trả active=true nếu route yêu cầu OAuth access token.

Các token profiles cần tách:

- OAuth access token, có thể dùng RFC 9068 typ=at+jwt.
- OIDC ID token.
- Refresh token.
- OAuth client assertion.
- Logout token.
- Bearer token dành cho API khác.

**Token sai mục đích không được “cứu” bằng một authentication strategy khác.**

## 19. User identity và machine identity không tự hoán đổi

Hai token từ cùng AS:

~~~text
User-delegated token:
  iss = auth.shop
  sub = user-42
  client_id = shop-web
  scope = orders.read

Client-credentials token:
  iss = auth.shop
  client_id = billing-worker
  scope = orders.sync
~~~

Với client_credentials, token có thể không có human sub. Nếu một user endpoint yêu cầu sub mà token thiếu sub, không tự chuyển sang machine identity mapping rồi cho quyền truy cập tài nguyên user.

Một thiết kế tách:

~~~text
USER actor:
  key = issuer + subject
  delegated client
  tenant/ownership permissions

CLIENT actor:
  key = issuer + client_id
  service permissions
  không mặc định có human ownership
~~~

**Tên principal giống nhau không làm hai trust domains hoặc actor kinds trở thành một.**

## 20. Cookie session không được âm thầm cứu Bearer invalid

Một request browser có thể đồng thời mang:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer EXPIRED_TOKEN
Cookie: SESSION=VALID_BROWSER_SESSION
X-Api-Key: PARTNER_KEY
~~~

Nếu /api/orders yêu cầu Bearer-only, token expired phải bị từ chối. Cookie session và API key không tự là phương án thay thế.

Nếu một route **thật sự** chấp nhận đồng thời session và Bearer, application cần policy cụ thể:

1. Khi không có Bearer nhưng có session, có cho phép không?
2. Khi Bearer invalid và session valid, reject hay chọn session?
3. Khi Bearer user Alice khác session user Bob, ưu tiên ai?
4. Có phải thực hiện CSRF protection với cookie-based credentials không?
5. API response/WWW-Authenticate có phản ánh đúng scheme được yêu cầu không?
6. Authorization áp dụng theo principal nào?
7. Cookie/session có session-fixation và CSRF protections phù hợp không?

Không tắt CSRF chỉ vì endpoint có thể dùng Bearer nếu endpoint còn nhận ambient browser cookie. Cookie fallback có thể thay đổi threat model của API từ **explicit Bearer credential** sang **browser ambient credential**.

## 21. Gateway mTLS và private headers không phải nguồn fallback tùy tiện

Gateway có thể xác thực mTLS client rồi gắn private identity header cho backend. Điều đó chỉ an toàn khi:

- Client Internet không thể gọi trực tiếp backend.
- Gateway strip các private headers do client gửi.
- Gateway chỉ set header dựa trên authentication đã xác minh.
- Kết nối gateway -> backend có trust boundary rõ.
- Backend chỉ chấp nhận gateway identity trên những routes đã định nghĩa.

Sai:

~~~text
JWT validation failed
  -> thấy X-Verified-User: admin
  -> chấp nhận.
~~~

Nếu caller tự gửi header, đây là identity spoofing. Nếu header thực sự do trusted gateway tạo, nó vẫn không tự được dùng thay user Bearer token trên một route đòi user delegation.

Đổi nguồn credential không chỉ là đổi header name; nó là thay **security authority** và **principal semantics**.

## 22. Một request có nhiều credentials: cần collision policy

Khi request mang Bearer, Basic, API key, session cookie, hoặc Bearer header + query:

- Các credentials có thể trỏ đến **các principals khác nhau**.
- Một security mechanism có thể chạy trước mechanism khác.
- Một filter có thể bỏ qua credential không thuộc scheme của mình.
- Một custom authentication manager có thể chọn credential sau khi cái trước thất bại.

Nếu API không thiết kế rõ, một request có thể được chấp nhận dưới principal khác với client mong đợi.

Một policy tốt:

~~~text
/api/**:
  bearer-only
  invalid Bearer -> reject
  cookie/api-key không được cứu

/browser/**:
  OIDC session
  CSRF và session protections
  Bearer không tự được chấp nhận

/integrations/**:
  mTLS/API key theo partner contract
  client type/tenant/resource binding riêng
~~~

Nếu một route bắt buộc hỗ trợ nhiều schemes, phải định nghĩa precedence, error response, handling duplicate và kiểm thử sự mâu thuẫn.

### Duplicate Bearer token sources

RFC 6750 khuyến nghị không truyền Bearer token bằng nhiều phương thức trong cùng request. Nếu Authorization header, query access_token và form field có token khác nhau, không chọn “token nào qua được” như một authentication contest. Cần resolver/transport policy rõ, thường từ chối credential collision.

## 23. Chọn theo token format: có thể dùng hint, không được tin như proof

Một heuristic đơn giản:

~~~text
Token chứa hai dấu chấm:
  chọn JWT verifier.

Token không có dấu chấm:
  chọn opaque introspection.
~~~

Nhược điểm:

- Opaque token có thể chứa dấu chấm.
- Attacker có thể tự tạo chuỗi giả dạng JWT.
- Không xác định issuer/audience.
- Hình dạng token không bảo đảm token type/purpose.
- Format migration làm policy dễ không nhất quán.

Nếu AS phát token prefixes không mơ hồ theo contract, prefix có thể được dùng như routing hint có kiểm soát. **Sau routing, vẫn phải verify toàn bộ credential**; routing hint không phải chứng cứ danh tính.

Nếu không có contract chắc chắn, ưu tiên request route, trusted issuer allow-list hoặc metadata được xác minh từ một gateway đáng tin.

## 24. Multi-tenant: iss và tenant chưa verify không tự thêm trust domain

Một token tự khai:

~~~json
{
  "iss": "https://attacker.example.net/",
  "sub": "user-42",
  "tenant_id": "tenant-blue",
  "scope": "orders.admin"
}
~~~

Nếu API tự tạo decoder từ iss hoặc tenant_id tùy ý, attacker có thể khiến API truy cập JWKS do họ quản lý hoặc gắn admin role không hợp lệ.

Trust selection đúng:

~~~text
Trusted tenant/route mapping
       |
       v
Issuer allow-list for this tenant
       |
       v
Select issuer-specific verifier
       |
       v
Verify JWS signature + exact iss + aud + time/profile
       |
       v
Map (issuer, sub) to local identity
       |
       v
Verify current tenant membership/resource ownership
~~~

Nếu tổ chức hỗ trợ dynamic tenant onboarding, danh sách issuers phải được bổ sung bằng **trusted administrative workflow**, không phải vì request nào đó khai issuer lạ.

## 25. Migration từ opaque sang JWT không cần fallback theo lỗi

Giả sử cần chuyển đổi khách hàng:

~~~text
Phase 1:
  /api/legacy/** dùng AS opaque introspection.
  /api/v2/** dùng JWT issuer A.

Phase 2:
  Client migrate sang /api/v2 và xin JWT phù hợp audience.

Phase 3:
  Quan sát usage, ngừng cấp legacy token và đóng legacy routes.
~~~

Ưu điểm:

- Từng route có authentication contract rõ.
- Không cần “JWT fail thì opaque”.
- Có thể test chính xác backend được gọi.
- Có migration metric và sunset policy.
- Ít rủi ro authentication downgrade.

Nếu bắt buộc cùng một endpoint chấp nhận nhiều token formats, cần deterministic resolver với allow-list/format contract đáng tin và phải từ chối các trường hợp mơ hồ. Đừng dùng một exception chain làm thuật toán nhận diện token.

### Khi cần dùng cả JWT và introspection

Nếu chính sách muốn JWT signature validation **và** online revocation check, cần thiết kế:

~~~text
accepted =
  JWT signature/iss/aud/time valid
  AND introspection says active
~~~

Khác hẳn:

~~~text
accepted =
  JWT validation valid
  OR introspection says active
~~~

Phép OR có thể là downgrade nếu thực tế tổ chức yêu cầu cả hai.

## 26. HA failover trong cùng trust domain có thể hợp lệ

Không phải mọi failover đều nguy hiểm. AS có thể cung cấp hai endpoints phục vụ cùng một token registry:

~~~text
https://introspect-a.auth.example.com/
https://introspect-b.auth.example.com/
~~~

Nếu chúng thực sự là replicas cùng trust authority, chính sách active, client authentication và resource binding tương đương, được cấu hình sẵn trong trusted network, chuyển replica khi network failure có thể là một chiến lược availability hợp lệ.

Điều kiện:

1. Không đổi issuer/token authority.
2. Cả hai endpoints có TLS trust được xác minh.
3. Cùng credentials/policy/audience contract.
4. Timeout/retry có giới hạn, tránh thác request.
5. Lỗi inactive vẫn là inactive, không chuyển sang authority mới để tìm success.
6. Cache public keys/token state nếu có phải tuân expiration/revocation policy.

**Failover do AS replica outage khác với hỏi một AS độc lập sau khi AS đầu tiên từ chối token.**

## 27. Chữ ký, issuer, audience và lifetime sai đều không cho phép strategy hopping

| JWT failure | Nghĩa | Không được làm |
|---|---|---|
| Malformed JWT | Token sai định dạng | Thử Basic/session |
| Signature invalid | Không xác minh được với trusted key | Thử tất cả JWKS issuers |
| alg không được phép | Algorithm policy không đạt | Bật HS256/none để chữa lỗi |
| kid không tìm thấy | Không có trusted candidate key | Tải arbitrary key URL từ header |
| iss sai | Không đúng nhà phát hành | Thử issuer bất kỳ |
| aud sai | Token dành cho API khác | Thử introspection yếu hơn |
| exp expired | Credential quá hạn | Dùng cookie admin cứu request |
| nbf trong tương lai | Credential chưa có hiệu lực | Tăng skew quá lớn hoặc chuyển provider |
| typ/token purpose sai | Không phải access token đúng profile | Coi ID token là API token |
| Scope thiếu | Đã authenticated nhưng chưa đủ quyền | Tìm principal khác có quyền |

Những lỗi này phải được xử lý đúng **trong chiến lược đã chọn**. Ngay cả khi một backend khác có thể giải mã hoặc nhận diện chuỗi token, nó chưa chắc có authority trên endpoint.

## 28. Kịch bản ba security zones

Giả sử kiến trúc:

~~~text
/api/orders/**
  JWT issuer Shop
  aud=orders-api
  scopes orders.read/orders.write

/api/partner/**
  Opaque introspection của Partner AS
  aud=partner-orders-api
  scope partner.orders.read

/admin/**
  OIDC Login + session cookie
  CSRF protection
~~~

**Tình huống A:** JWT Shop hết hạn gọi /api/orders. Kết quả authentication failure, không được thử partner AS hoặc session admin.

**Tình huống B:** Opaque token Partner được gửi nhầm tới /api/orders. Route vẫn yêu cầu JWT Shop, không tự đổi backend.

**Tình huống C:** Partner opaque token tới đúng /api/partner. Introspection active=true nhưng thiếu partner.orders.read: authenticated thành công, authorization có thể 403.

**Tình huống D:** OIDC admin session hợp lệ nhưng CSRF invalid khi POST /admin. CSRF policy từ chối, không thử Bearer/api-key.

**Tình huống E:** Partner introspection timeout. Fail closed; không truy vấn AS Shop.

**Tình huống F:** Shop AS xoay signing key. Resource Server refresh trusted JWKS Shop và có thể verify key mới. Đây là cùng trust domain, không phải fallback sang Partner.

**Tình huống G:** Issuer Shop và Partner cùng sub=user-42. Hai principals không tự là một người; mapping local identity cần issuer + sub hoặc account linking đáng tin.

**Tình huống H:** Shop JWT được verify nhưng tenant membership bị thu hồi. Domain authorization từ chối, không tìm credential khác để tăng quyền.

## 29. Integration tests phải chứng minh backend không được chọn không bị gọi

Không chỉ test happy path. Các negative tests phải khẳng định **đường xác thực khác không chạy**.

| Test | Kỳ vọng |
|---|---|
| /api/v2 JWT hợp lệ | JWT manager được dùng |
| /api/v2 JWT sai signature | 401; opaque introspector không được gọi |
| /api/v2 JWT sai issuer | 401; không tải JWKS issuer lạ |
| /api/v2 JWT sai aud | 401; không thử opaque |
| /api/v2 JWT expired | 401; session cookie không cứu |
| /api/legacy opaque active=true | Opaque introspector được dùng |
| /api/legacy opaque active=false | 401; JWT decoder không được gọi |
| /api/legacy AS timeout | Fail closed; không fallback sang JWT |
| Multi-issuer iss lạ | Reject; không fetch metadata issuer lạ |
| iss=A nhưng JWT ký bằng key B | Reject; không thử B để cứu A |
| Bearer invalid + valid cookie | Reject trên Bearer-only route |
| Bearer invalid + valid API key | Reject trên Bearer-only route |
| Basic invalid tại /ops | Reject; không thử Bearer của /api |
| JWT valid, scope thiếu | 403; không dùng account từ provider khác |
| JWT valid, sai tenant | Domain denial |
| AS introspection HTTP 401 invalid_client | Fail closed, phân loại upstream config error |
| JWKS timeout | Không tự tin key lạ |
| Key rotation trong trusted JWKS | Verify với key tin cậy mới |
| Multiple credentials mâu thuẫn | Theo collision policy, thường reject |

### Kiểm tra tương tác với mock

Sau integration test qua filter chain, có thể kiểm tra:

~~~java
verify(jwtDecoder).decode(anyString());
verifyNoInteractions(opaqueIntrospector);
~~~

Với reactive WebFlux, cần để WebTestClient hoàn thành response trước khi verify interactions. Các post-processors như mockJwt() có thể tạo Authentication giả mà không chạy decoder thật; không dùng riêng chúng để khẳng định security pipeline không fallback.

Test nên bao phủ HTTP status, WWW-Authenticate, Authentication principal, không có raw token leaks và số lần backend được gọi.

## 30. Unit test ProviderManager behavior để không hiểu sai framework

Một test chuyên biệt có thể tạo hai AuthenticationProvider fixtures cùng hỗ trợ BearerTokenAuthenticationToken:

~~~text
Provider A:
  supports = true
  authenticate -> BadCredentialsException

Provider B:
  supports = true
  authenticate -> authenticated result
~~~

Nếu framework thử B và kết quả cuối thành công, test cho thấy provider list **không tự là deny-on-first-error**.

Cần test riêng các trường hợp:

- Provider A trả null.
- Provider A ném BadCredentialsException.
- Provider A ném AccountStatusException.
- Provider A thành công.
- Parent AuthenticationManager được cấu hình.
- Providers cùng supports cùng một Authentication type.

**Không dùng AccountStatusException giả để ép dừng**. Nếu chính sách cần một strategy duy nhất, dùng resolver hoặc chain separation, không hack exception class.

## 31. Reactive tests: đừng nhầm Mono.empty với Mono.error

Với reactive manager:

~~~text
Mono.just(authentication):
  success

Mono.error(authenticationException):
  failure

Mono.empty():
  no result / not-applicable theo contract cụ thể
~~~

Một anti-pattern:

~~~java
return jwtManager.authenticate(authentication)
        .switchIfEmpty(opaqueManager.authenticate(authentication));
~~~

Chỉ có thể hợp lệ nếu **empty thật sự mang semantics không áp dụng**, và opaque strategy được policy cho phép trong chính request đó. Nếu JWT manager dùng empty để giấu invalid credential thì composition này là sai.

Nguy hiểm hơn:

~~~java
return jwtManager.authenticate(authentication)
        .onErrorResume(anyError ->
                opaqueManager.authenticate(authentication));
~~~

Nó có thể nuốt signature error, issuer mismatch, JWKS outage, client configuration error và chuyển qua backend khác. **Catch-all onErrorResume không tự hiểu authentication trust boundary.**

## 32. Kiểm toán chiến lược đã chọn mà không log credential

Nên ghi:

~~~text
requestId = req-472
securityZone = api_v2
selectedAuthStrategy = jwt_issuer_shop
authenticationOutcome = failure
failureCategory = invalid_signature
crossStrategyFallbackCount = 0
status = 401
~~~

Hoặc:

~~~text
requestId = req-473
securityZone = api_legacy
selectedAuthStrategy = opaque_partner
authenticationOutcome = dependency_error
failureCategory = introspection_timeout
crossStrategyFallbackCount = 0
~~~

Không ghi:

- Raw JWT/Bearer access token.
- HTTP Authorization header.
- Introspection client secret, API key hoặc Basic password.
- Full token payload chứa PII.
- Raw iss/kid từ token chưa verify làm trusted identity.
- Unbounded strings từ JWT làm metrics labels gây high cardinality.

Dùng **strategy IDs cấu hình sẵn** để metrics có cardinality giới hạn.

### Những dấu hiệu fallback nguy hiểm

- JWT signature error nhưng cuối cùng HTTP 200.
- Một request gọi nhiều introspection endpoints độc lập.
- Principal ID thay đổi khi đảo thứ tự providers.
- Partner token được nhận cho admin route.
- API key hoặc session cookie cứu expired Bearer token.
- Khi AS outage, số lượt xác thực thành công qua mechanism yếu hơn tăng bất thường.
- Token invalid tạo tải outbound tới nhiều AS.
- Logs không xác định được chiến lược nào tạo Authentication cuối.

## 33. Danh sách câu hỏi trước khi bổ sung cơ chế mới

1. Route/security zone nào được phép nhận credential này?
2. Credential lấy từ Authorization, cookie, custom header, mTLS hay form/query?
3. Issuer/AS/certificate authority/api-key registry nào là trusted?
4. Nếu request mang nhiều credentials, áp dụng precedence/collision policy gì?
5. Khi credential không có, route nào có thể chọn strategy khác?
6. Khi credential bị từ chối, có chắc chắn dừng không?
7. Khi JWKS/introspection không sẵn, có fail closed không?
8. Audience/resource binding có bắt buộc không?
9. Token purpose/profile và thời hạn có đúng không?
10. Principal kind là user hay machine client?
11. Subject namespace có gắn issuer không?
12. Scope/role mapping của từng issuer có giống nhau không?
13. Một principal từ provider B có được quyền trên resources của A không?
14. Có thể test backend không được chọn **không bị gọi** không?
15. Có dynamic issuer onboarding từ quy trình đáng tin hay từ request tự khai?
16. HA replicas có cùng trust domain và policy không?
17. CORS/CSRF/cookie threat model thay đổi thế nào?
18. Logs có strategy ID nhưng không lộ credential không?
19. Cơ chế legacy có sunset date/monitoring để gỡ bỏ không?
20. Có negative tests cho invalid signature/issuer/audience/token type không?

Đây là những câu hỏi **thiết kế** trước khi triển khai, không phải một quy trình Content QA của bài.

## 34. Những anti-pattern và cách sửa

| Anti-pattern | Rủi ro | Hướng sửa |
|---|---|---|
| JWT fail thì introspect | Downgrade | Chọn strategy trước validation |
| Issuer A fail thì thử issuer B | Cross-issuer trust confusion | Trusted issuer resolver |
| Tạo JWKS URL từ unverified iss/jku | SSRF/key substitution | Preconfigured allow-list |
| Nhiều providers cùng supports và không hiểu ProviderManager | Silent success after failure | Tách managers theo policy |
| Provider invalid credentials trả null | Biến failure thành not-applicable | AuthenticationException đúng semantics |
| Reactive catch-all onErrorResume sang backend khác | Bypass authentication | Propagate failure, fail closed |
| AS active=false thì hỏi AS tiếp theo | Token probing/leakage | Reject theo chosen AS |
| JWKS outage thì tắt signature | Accept unverified token | Fail closed hoặc trusted cache policy |
| Bearer invalid thì dùng session | Principal confusion/CSRF | Bearer-only route hoặc explicit policy |
| API key cứu expired user token | Escalation/actor mismatch | Actor-specific routes |
| Header X-User từ Internet được tin | Spoofing | Trusted gateway strip/rewrite |
| Dùng client_id thay sub cho mọi user | Identity confusion | USER/CLIENT contracts |
| Scope từ issuer B tự thành admin issuer A | Privilege escalation | Issuer-specific authority mapping |
| Token ID token dùng gọi API | Cross-JWT confusion | Audience/token purpose checks |
| Routing chỉ theo số dấu chấm của token | Type spoofing | Trusted routing contract |
| Retry sang AS độc lập khi timeout | Vượt trust boundary | Chỉ HA replicas cùng authority |
| Chỉ test success | Không phát hiện fallback | Negative interaction tests |
| Ghi raw credentials vào logs | Secret leakage | Redacted metrics và logs |

## 35. Tổng kết

~~~text
                       HTTP REQUEST
                            |
                            v
                Choose allowed trust strategy
                  from explicit policy
                            |
                            v
                  Verify the credential
               against that strategy only
                            |
               +------------+------------+
               |                         |
               v                         v
            SUCCESS                   FAILURE
               |                         |
               v                         v
       Authenticated principal      Reject / fail closed
               |                    No unrelated fallback
               v
       Authorization:
       scope + issuer + tenant + domain policy
               |
               v
       Protected operation
~~~

Những nguyên tắc quan trọng:

1. **Nhiều cơ chế xác thực không có nghĩa thử hết đến khi thành công.**
2. **Chọn chiến lược theo chính sách tin cậy trước**, không chọn theo exception của chiến lược thất bại.
3. **NOT_APPLICABLE khác AUTHENTICATION_FAILURE**, và cả hai khác dependency failure.
4. **ProviderManager có thể thử provider sau trong một số tình huống**, nên thứ tự provider không tự bảo đảm fail-on-first-error.
5. **AuthenticationManagerResolver/SecurityFilterChain** giúp phân tách trust policies trong Servlet.
6. **Reactive resolver/SecurityWebFilterChain** thực hiện vai trò tương ứng trong WebFlux.
7. **JWT sai chữ ký, issuer, audience, thời gian hoặc purpose phải bị từ chối**; không dùng opaque/session/Basic/API key cứu nó.
8. **Opaque active=false hoặc AS outage không cho phép dò tất cả introspection endpoints**.
9. **Issuer claim chưa verify chỉ là routing hint**, không phải quyền chọn AS/JWKS tùy ý.
10. **Failover cùng trust authority có thể hợp lệ**, nhưng không được dùng authority khác để thay kết luận authentication.
11. **Một credential được chấp nhận còn phải qua authorization**, trong đúng scope, tenant và actor type.
12. **Negative tests phải xác minh backends không được chọn không bị gọi**, không chỉ nhìn HTTP status cuối.

**Kết luận:** Kiến trúc xác thực nhiều chiến lược chỉ an toàn khi mỗi request có trust path được giới hạn rõ ràng. Một lỗi trong chiến lược được chọn phải được xử lý là lỗi tương ứng, không phải bước đầu của một cuộc tìm kiếm authority khác sẽ chấp nhận credential.

## 36. Tài liệu tham khảo

- **Spring Security — OAuth 2.0 Resource Server Multi-tenancy (Servlet):** JWT và opaque bằng AuthenticationManagerResolver, trusted issuer selection. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
- **Spring Security — OAuth 2.0 Resource Server Multi-tenancy (Reactive):** JwtIssuerReactiveAuthenticationManagerResolver và trusted issuers. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- **Spring Security API — ProviderManager:** provider iteration, AuthenticationException và AccountStatusException. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html
- **Spring Security — Servlet Authentication Architecture:** AuthenticationManager, AuthenticationProvider, ProviderManager. https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- **Spring Security API — JwtIssuerAuthenticationManagerResolver:** JWT trusted issuer routing. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html
- **Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver:** WebFlux trusted issuer routing. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html
- **Spring Security — Servlet JWT Resource Server:** JWS validation, issuer, audience và timestamps. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security — Reactive JWT Resource Server:** ReactiveJwtDecoder, trusted keys và validators. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security — Servlet Opaque Token Resource Server:** introspection, opaque và JWT token introspection. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security — Reactive Opaque Token Resource Server:** ReactiveOpaqueTokenIntrospector. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security — Servlet Java Configuration:** nhiều SecurityFilterChain và securityMatcher. https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- **Spring Security — WebFlux Security:** ServerHttpSecurity/SecurityWebFilterChain. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer credentials, WWW-Authenticate và error semantics. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7662 — OAuth 2.0 Token Introspection:** active response và AS trust. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 7519 — JSON Web Token:** iss, sub, aud, exp và claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JWT Best Current Practices:** algorithms, issuer/audience và token confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access-token audience/type/profile. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 9110 — HTTP Semantics:** authentication and 400/401/403. https://www.rfc-editor.org/rfc/rfc9110
