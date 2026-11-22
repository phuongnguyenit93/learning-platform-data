# Phối hợp nhiều provider và tránh chồng lấn phạm vi xử lý

Trong hệ thống **Spring Security OAuth 2.0/OIDC Resource Server**, một ứng dụng có thể đồng thời có API dùng JWT, API đối tác dùng opaque token, website đăng nhập qua OpenID Connect, endpoint quản trị và một số hệ thống cũ dùng HTTP Basic. Nếu chỉ thêm các **AuthenticationProvider** mà không xác định rõ phạm vi xử lý, một token có thể được chấp nhận qua cơ chế không dành cho endpoint đó.

Các câu hỏi quan trọng là:

- HTTP request đi vào **SecurityFilterChain** nào?
- Filter nào trích credential và tạo **Authentication request**?
- **AuthenticationManager** nào được gọi?
- Những **AuthenticationProvider** nào cùng hỗ trợ loại request đó?
- Nếu một provider từ chối token, provider sau có được thử không?
- Một token hợp lệ với issuer A có được dùng tại resource dành cho issuer B không?
- Cookie session hoặc Basic credentials có thể vô tình truy cập API vốn chỉ nhận Bearer token không?
- Khi ứng dụng thêm controller mới, có fallback bảo vệ URL chưa được phân loại không?

Mục tiêu của bài là phân biệt các tầng điều phối, thiết kế ranh giới tin cậy và kiểm chứng bằng những negative tests. **Authentication thành công chỉ là một bước; authorization theo scope, audience, tenant và tài nguyên vẫn bắt buộc.**

## 1. “Provider” ở đây là thành phần nào?

| Khái niệm | Ví dụ | Trách nhiệm |
|---|---|---|
| **Authorization Server / Identity Provider** | OIDC issuer A, issuer B | Phát hành access token/ID Token theo giao thức |
| **AuthenticationProvider** | JwtAuthenticationProvider, OpaqueTokenAuthenticationProvider, DaoAuthenticationProvider | Xác minh một loại Authentication request |
| **AuthenticationManager** | ProviderManager | Điều phối AuthenticationProvider |
| **AuthenticationManagerResolver** | JwtIssuerAuthenticationManagerResolver | Chọn manager thích hợp theo request/issuer |
| **SecurityFilterChain** | API chain, web-login chain, admin chain | Quyết định filters và authorization rules áp lên HTTP request |
| **Authentication mechanism** | Bearer, Basic, form login, OIDC login, mTLS | Cách client trình bằng chứng xác thực |

Một ứng dụng có thể có nhiều issuers nhưng một SecurityFilterChain. Một ứng dụng khác có nhiều SecurityFilterChain, mỗi chain chỉ dùng một provider. **Số issuer, provider, manager và chain không phải một.**

## 2. Hai cấp chọn riêng biệt

~~~mermaid
flowchart TD
    R[HTTP request] --> FC[FilterChainProxy]
    FC --> C{SecurityFilterChain đầu tiên khớp}
    C -->|JWT API| JF[BearerTokenAuthenticationFilter]
    C -->|Opaque API| OF[BearerTokenAuthenticationFilter]
    C -->|Web Login| LF[OAuth2Login và session filters]
    C -->|Không khớp| U[Không được các security chains này bảo vệ]
    JF --> JM[JWT AuthenticationManager]
    OF --> OM[Opaque AuthenticationManager]
    JM --> JP[JwtAuthenticationProvider]
    OM --> OP[OpaqueTokenAuthenticationProvider]
    LF --> WP[Web login authentication]
    JP --> A[Authentication thành công]
    OP --> A
    WP --> A
    A --> Z[Authorization: scope, role, audience, tenant]
~~~

**Cấp 1: FilterChainProxy** chọn chain theo HTTP request và thứ tự matcher. **Cấp 2: AuthenticationManager** xử lý Authentication request do filter trong chain tạo ra.

Việc đăng ký JwtAuthenticationProvider **không tự thêm BearerTokenAuthenticationFilter vào mọi URL**. Tương tự, khai báo securityMatcher không tự xác minh chữ ký JWT.

## 3. SecurityFilterChain: first match wins

Trong Servlet Spring Security, FilterChainProxy duyệt các SecurityFilterChain theo thứ tự và chọn **chain đầu tiên khớp**.

~~~text
@Order(1) /api/admin/**  -> JWT admin
@Order(2) /api/**        -> JWT general
@Order(3) matcher rộng   -> fallback
~~~

**GET /api/admin/reports** khớp cả hai pattern đầu, nhưng chỉ **chain 1** chạy. Các rule chain 2 không được cộng thêm.

### 3.1. securityMatcher khác requestMatchers

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    );
~~~

- **securityMatcher("/api/**")** quyết định chain có được chọn.
- **requestMatchers(...)** quyết định rule authorization khi request đã vào chain.
- **anyRequest()** chỉ bao phủ những request thuộc chain đó.

**GET /internal/export** không thuộc chain /api/**, nên anyRequest của chain đó không bảo vệ URL này.

### 3.2. Chain catch-all đặt đầu là lỗi nghiêm trọng

~~~text
@Order(1) /**               -> permitAll
@Order(2) /api/admin/**     -> hasRole ADMIN
~~~

Request admin bị chain 1 chọn trước, vì vậy chain 2 không được chạy.

Ngược lại, catch-all denyAll đặt đầu sẽ chặn mọi specialized chain. **Đặt chain chuyên biệt trước, fallback chặt cuối.**

## 4. AuthenticationProvider và supports()

Giao diện Servlet rút gọn:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication request)
        throws AuthenticationException;

    boolean supports(Class<?> requestType);
}
~~~

**supports(...)** chỉ xác nhận provider có khả năng xử lý loại Authentication request. Nó không kiểm token value, password, chữ ký hay issuer.

**authenticate(...)** mới xác minh credential và trả Authentication thành công hoặc báo lỗi.

| Authentication request | Provider thường dùng |
|---|---|
| UsernamePasswordAuthenticationToken | DaoAuthenticationProvider |
| BearerTokenAuthenticationToken với JWT | JwtAuthenticationProvider |
| BearerTokenAuthenticationToken với opaque token | OpaqueTokenAuthenticationProvider |
| PreAuthenticatedAuthenticationToken | PreAuthenticatedAuthenticationProvider |
| RememberMeAuthenticationToken | RememberMeAuthenticationProvider |

**JwtAuthenticationProvider và OpaqueTokenAuthenticationProvider đều thường supports BearerTokenAuthenticationToken.** Đây là nguồn gốc quan trọng của chồng lấn JWT/opaque.

HTTP Basic và form login thường cùng tạo UsernamePasswordAuthenticationToken; vì thế cũng không được coi supports() là công cụ phân biệt HTTP Basic với form login.

## 5. ProviderManager không hoạt động như FilterChainProxy

Theo JavaDoc của ProviderManager:

1. Providers được thử theo thứ tự.
2. Provider không supports request type thì bị bỏ qua.
3. Provider hỗ trợ nhưng trả **null** có thể nhường cho provider kế tiếp.
4. Provider trả **Authentication khác null thành công** thì manager dừng, không thử provider sau.
5. Một **AuthenticationException** ở provider trước có thể bị thay thế bằng thành công của provider sau.
6. Nếu không provider nào xử lý được, có thể phát sinh ProviderNotFoundException hoặc lỗi authentication phù hợp.
7. **AccountStatusException** là trường hợp đặc biệt khiến manager dừng, không thử providers sau.
8. Parent AuthenticationManager có thể được tham khảo theo cấu hình và semantics của ProviderManager.

**Không nói “provider đầu tiên supports là provider duy nhất được chạy”** và cũng không nói “manager luôn thử tất cả providers”. Behavior phụ thuộc kết quả/lỗi.

### 5.1. ProviderManager không cộng dồn authorities

Giả sử provider A trả **SCOPE_orders.read**, provider B có thể trả **ROLE_ADMIN**. ProviderManager **không tự chạy cả hai rồi gộp authorities**.

Muốn yêu cầu nhiều yếu tố xác thực cùng lúc, chẳng hạn **mTLS AND JWT** hoặc **password AND OTP**, phải thiết kế ràng buộc factors và một policy AND riêng. Chỉ thêm hai providers thường tạo khả năng một trong hai cơ chế được chấp nhận, không bảo đảm cả hai đã chạy.

### 5.2. Parent manager là một ranh giới khác

ProviderManager có thể có parent. Nếu local providers không xử lý được, parent có thể được gọi theo implementation. Đừng gắn một parent quá rộng rồi giả định endpoint Bearer-only không thể bị xác thực bằng cơ chế khác.

Ưu tiên manager có phạm vi rõ ràng cho từng chiến lược xác thực, đặc biệt khi chính sách issuer/audience khác nhau.

## 6. JWT và opaque token cùng dùng Bearer scheme

HTTP không đánh dấu token JWT hay opaque bằng một authentication scheme khác:

~~~http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

~~~http
Authorization: Bearer opaque-value-example
~~~

Cả hai thường được BearerTokenAuthenticationFilter chuyển thành **BearerTokenAuthenticationToken**.

Nếu tự tạo:

~~~java
AuthenticationManager manager = new ProviderManager(
    new JwtAuthenticationProvider(jwtDecoder),
    new OpaqueTokenAuthenticationProvider(opaqueTokenIntrospector)
);
~~~

cả hai providers có thể supports request type giống nhau. Khi JWT decoder từ chối token, ProviderManager **có thể** thử opaque provider tùy loại lỗi. Nếu introspection của một Authorization Server khác chấp nhận token, authentication có thể thành công dù JWT policy đã từ chối.

Đây là nguy cơ **cross-strategy fallback/trust downgrade**.

### 6.1. Không thử mọi provider đến khi có success

~~~text
JWT verification thất bại do sai issuer/audience/signature
    -> chuyển sang opaque introspection
         -> AS khác trả active=true
              -> cấp quyền
~~~

Một kết quả success theo contract khác có thể vô tình vượt qua từ chối của JWT trust policy.

**Chọn đúng manager dựa trên định tuyến/chính sách đã xác lập trước khi xác thực token, không chọn bằng cách thử hết mọi cơ chế.**

### 6.2. Hình thức token không phải nguồn tin cậy

Đếm dấu chấm để phân biệt JWT và opaque token là một heuristic không đủ an toàn. Opaque token có thể chứa dấu chấm; một access token dạng JWT vẫn có thể được yêu cầu introspect vì revocation.

Không dùng các giá trị token chưa verify như **iss**, **alg**, **jku**, **jwk** hoặc URL bên trong token để tự tạo nguồn trust ngoài allowlist.

## 7. Tách các SecurityFilterChain khi URL có ranh giới rõ ràng

Thiết kế ví dụ:

~~~text
/api/admin/**      -> JWT access token từ issuer nội bộ
/api/partners/**   -> opaque access token từ AS đối tác
/web/**            -> OIDC Login và session cookie
mọi route còn lại -> fallback denyAll
~~~

### 7.1. Servlet configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultiMechanismSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/admin/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin/reports/**")
                    .hasAuthority("SCOPE_admin.read")
                .anyRequest().hasAuthority("SCOPE_admin.manage")
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain partnerApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/partners/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/partners/**")
                    .hasAuthority("SCOPE_partner.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain webLogin(HttpSecurity http) throws Exception {
        http
            .securityMatcher(
                "/web/**", "/login/**", "/oauth2/**", "/logout")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login/**", "/oauth2/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(4)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

**Đây là mẫu minh họa phạm vi, chưa phải cấu hình production hoàn chỉnh.** Cần issuer/JWKS/JwtDecoder, introspection endpoint/credentials, OIDC client registrations, callback/logout routes, CORS, error dispatch và Actuator policies phù hợp.

Ví dụ disable CSRF ở API chains **chỉ đúng khi chúng thật sự chỉ nhận Bearer header do client chủ động gắn**, không chấp nhận session cookie, JWT cookie hoặc Basic browser-managed credentials.

### 7.2. Kết quả định tuyến mong muốn

| Request | Chain | Cơ chế | Policy |
|---|---|---|---|
| GET /api/admin/reports/month | adminApi | JWT | SCOPE_admin.read |
| POST /api/admin/jobs | adminApi | JWT | SCOPE_admin.manage |
| GET /api/partners/orders | partnerApi | Opaque | SCOPE_partner.read |
| POST /api/partners/orders | partnerApi | Opaque | denyAll |
| GET /web/profile | webLogin | OIDC/session | authenticated |
| GET /internal/export | fallback | Từ chối | denyAll |

JWT gửi vào partner API không tự làm request chuyển sang admin chain; opaque token gửi vào admin API không tự được introspect bởi partner provider.

### 7.3. Vì sao fallback cần thiết?

Khi ứng dụng khai báo SecurityFilterChain riêng, không nên giả định Spring Boot tự thêm chain catch-all.

Nếu controller mới **/internal/export** không thuộc chain nào, các Spring Security filters của những chains đã khai báo có thể không bảo vệ request. Fallback denyAll ở cuối giúp fail-closed.

Cần kiểm management port/context riêng, reverse proxy rewrite, servlet path/context path, HTTP methods và dispatcher types. Response 404 trên route không có handler **không chứng minh security đã hoạt động**.

## 8. Basic và Bearer trong cùng chain: khi nào hợp lý?

Một endpoint legacy có thể **chủ động** chấp nhận:

~~~text
/integration/**:
  HTTP Basic username/password
  hoặc
  OAuth2 Bearer JWT
~~~

Ví dụ:

~~~java
@Bean
SecurityFilterChain mixedApi(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/integration/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

BasicAuthenticationFilter thường tạo UsernamePasswordAuthenticationToken; BearerTokenAuthenticationFilter tạo BearerTokenAuthenticationToken. Nếu providers xử lý đúng types, có một sự tách biệt ở cấp Authentication request.

Nhưng hỗ trợ Basic OR Bearer cần đánh giá:

- Người dùng Basic có quyền giống scope của access token không?
- Basic có bypass chính sách token audience/issuer hoặc MFA không?
- Browser có tự lưu/gửi Basic credentials, tạo CSRF risk không?
- Khi request không có credential, entry point trả Basic hay Bearer challenge?
- Nếu một request chứa cả nhiều credential, có rule nhất quán không?
- API có cần giới hạn từng mechanism theo HTTP method hoặc route không?

Khi không cần legacy compatibility thật sự, **tách path/chain** dễ kiểm soát hơn.

### 8.1. Custom provider supports quá rộng là nguy hiểm

~~~java
@Override
public boolean supports(Class<?> type) {
    return Authentication.class.isAssignableFrom(type);
}
~~~

Mẫu này khiến một provider nhận nhiều Authentication request types ngoài dự kiến. Nếu authenticate() vô tình trả success với credential chưa xác minh, hệ thống có thể bị bypass.

Chỉ supports types được thiết kế và chỉ trả Authentication thành công dựa trên một nguồn tin cậy.

## 9. AuthenticationManagerResolver: chọn đúng manager theo request

Spring Security Servlet có:

~~~java
AuthenticationManagerResolver<HttpServletRequest>
~~~

Nếu một chain thật sự phải phục vụ cả JWT và opaque token, resolver có thể chọn một manager tại thời điểm request.

### 9.1. Ví dụ ranh giới route JWT/opaque

~~~text
/api/jwt/**       -> JwtAuthenticationProvider
/api/opaque/**    -> OpaqueTokenAuthenticationProvider
ngoài hai nhóm    -> không có strategy cho phép
~~~

Java:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Bean
AuthenticationManagerResolver<HttpServletRequest> bearerResolver(
        JwtDecoder jwtDecoder,
        OpaqueTokenIntrospector opaqueTokenIntrospector) {

    AuthenticationManager jwt =
        new ProviderManager(new JwtAuthenticationProvider(jwtDecoder));

    AuthenticationManager opaque =
        new ProviderManager(
            new OpaqueTokenAuthenticationProvider(opaqueTokenIntrospector));

    AuthenticationManager reject = authentication -> {
        throw new BadCredentialsException(
            "No approved Bearer strategy for this route");
    };

    return request -> {
        String servletPath = request.getServletPath();
        if (servletPath.startsWith("/api/jwt/")) {
            return jwt;
        }
        if (servletPath.startsWith("/api/opaque/")) {
            return opaque;
        }
        return reject;
    };
}

@Bean
SecurityFilterChain routedApi(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> bearerResolver)
        throws Exception {

    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/jwt/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.GET, "/api/opaque/**")
                .hasAuthority("SCOPE_partner.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(bearerResolver));

    return http.build();
}
~~~

Ví dụ giả định DispatcherServlet mapping thông dụng. **getServletPath() có thể không match route như bạn tưởng** khi có contextPath, servlet mapping khác, proxy rewrite hoặc path normalization. Production nên dùng request matcher phù hợp deployment và test những path variants, không chỉ dựa vào startsWith.

Đối với route đã tách như trên, hai SecurityFilterChain riêng thường dễ hiểu hơn; resolver chỉ thực sự cần thiết khi policy phải chọn manager **bên trong một chain chung**.

### 9.2. Resolver không phải decoder

Nó chỉ định **manager nào sẽ xác thực**. JWT manager vẫn phải verify signature, issuer, algorithms, exp/nbf, audience và token profile. Opaque manager vẫn phải gọi introspection endpoint tin cậy và kiểm active, audience/scope/tenant theo contract.

Đừng chọn manager khác sau khi decoder từ chối. Nếu token sai trust policy của manager đã được định tuyến, request phải thất bại.

## 10. Nhiều JWT issuers: quản lý trust allowlist

Một Resource Server có thể tin hai issuers:

~~~text
https://identity-a.example.com/realms/shop
https://identity-b.example.com/realms/partners
~~~

Spring Security hỗ trợ **JwtIssuerAuthenticationManagerResolver**:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://identity-a.example.com/realms/shop",
        "https://identity-b.example.com/realms/partners"
    );

http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .authenticationManagerResolver(resolver));
~~~

Resolver có thể đọc claim **iss** chưa được xác minh để chọn candidate manager trong tập issuers đã trust. **Sau đó JwtDecoder phải xác minh chữ ký và các claims**.

### 10.1. Unverified iss chỉ là routing hint

Attacker có thể tự tạo JWT payload:

~~~json
{
  "iss": "https://identity-a.example.com/realms/shop",
  "sub": "admin",
  "scope": "all"
}
~~~

Những giá trị này chưa đáng tin trước chữ ký/validators. Issuer claim chỉ được dùng để định tuyến tới nguồn khóa/decoder **đã được allowlist**, không tự mở trust.

Anti-pattern:

~~~text
Đọc iss tùy ý từ JWT chưa verify
    -> tạo decoder tới bất kỳ issuer URL nào
    -> tải metadata/JWKS do attacker chỉ định
    -> nhận JWT được attacker tự ký
~~~

Có nguy cơ SSRF hoặc mở rộng trust boundary. Không tự động đăng ký issuer mới từ incoming token.

### 10.2. Trusted issuer không thay audience validation

Token của issuer A có **aud=billing-api** không tự được chấp nhận bởi **orders-api**, dù chữ ký và issuer đúng. Kiểm audience, token type/profile và resource binding cho mỗi manager.

### 10.3. Định danh là issuer + subject

**sub=user-123** ở issuer A không mặc định là cùng danh tính với **sub=user-123** ở issuer B. Dùng issuer+sub hoặc domain identity mapping đáng tin; không gộp tài khoản chỉ qua email chưa verify.

### 10.4. Dynamic tenant management

Có thể dùng repository issuer-to-manager để thêm/bớt tenants nhưng:

- Chỉ thêm issuer qua quy trình quản trị.
- Verify JWKS endpoint và TLS.
- Ràng buộc audience/scope theo issuer.
- Kiểm cache/lazy initialization và manager eviction.
- Không để mỗi token lạ tự tạo decoder/manager.
- Audit thay đổi trust registry.

## 11. Scope cùng tên giữa issuers chưa chắc cùng nghĩa

Giả sử issuer A và B đều cấp:

~~~text
orders.read
~~~

Một token active từ issuer B không nhất thiết có quyền tương đương issuer A.

| Yếu tố | Câu hỏi cần trả lời |
|---|---|
| **Issuer** | Token được phát bởi nguồn nào? |
| **Signature/active** | Đã được nguồn tin cậy xác minh chưa? |
| **Audience** | Dành cho Resource Server nào? |
| **Client** | Loại client được cấp có đúng mục đích không? |
| **Scope** | orders.read có cùng hợp đồng giữa issuers không? |
| **Role** | Issuer này có được quyền cấp ROLE_ADMIN không? |
| **Tenant** | Dữ liệu thuộc tổ chức nào? |
| **Ownership** | Principal được phép đọc bản ghi cụ thể không? |

Không tự map mọi claim:

~~~json
{
  "roles": ["ADMIN"]
}
~~~

từ issuer bất kỳ thành **ROLE_INTERNAL_ADMIN**. Chỉ ánh xạ authorities theo trust contract của issuer đã xác minh.

## 12. OAuth2/OIDC Login khác Resource Server Bearer

| Phần | OAuth2/OIDC Login | OAuth2 Resource Server |
|---|---|---|
| Mục tiêu | Đăng nhập browser user | Xác thực API access token |
| Cơ chế | Authorization Code/OIDC callback | Authorization Bearer |
| Token quan trọng | ID Token và session/client context | Access token dành cho API |
| Trạng thái | Thường có session cookie | Có thể stateless |
| Spring DSL | oauth2Login | oauth2ResourceServer |
| CSRF | Xét session/browser | Xét cách gửi credentials |

**ID Token không tự là access token** cho API. Một ID Token có chữ ký hợp lệ nhưng audience là OAuth client_id không đủ để dùng ở Resource Server.

Một ứng dụng dùng OAuth2AuthorizedClientManager để lấy access token khi gọi service khác đang đóng vai **OAuth2 Client**, không tự làm inbound request có Authentication hợp lệ.

### 12.1. Session cookie không được mở Bearer-only API

Browser gửi:

~~~http
POST /api/admin/jobs HTTP/1.1
Cookie: JSESSIONID=session-value
~~~

Nếu endpoint chỉ chấp nhận Bearer access token, request cookie-only phải bị từ chối. Khi API vô tình chấp nhận session hoặc Basic browser-managed auth, policy đã thay đổi và có thể phát sinh CSRF risk.

**STATELESS không tự chống CSRF** nếu custom filter vẫn lấy JWT từ cookie. Kiểm cơ chế nhận credential thật, không chỉ một property.

## 13. WebFlux: cùng nguyên tắc, khác API

| Servlet | WebFlux |
|---|---|
| SecurityFilterChain | SecurityWebFilterChain |
| HttpSecurity | ServerHttpSecurity |
| AuthenticationManager | ReactiveAuthenticationManager |
| AuthenticationManagerResolver<HttpServletRequest> | ReactiveAuthenticationManagerResolver<ServerWebExchange> |
| JwtAuthenticationProvider | JwtReactiveAuthenticationManager |
| OpaqueTokenAuthenticationProvider | OpaqueTokenReactiveAuthenticationManager |
| JwtIssuerAuthenticationManagerResolver | JwtIssuerReactiveAuthenticationManagerResolver |
| SecurityContextHolder | ReactiveSecurityContextHolder |

Không gọi blocking Servlet authentication provider trong Reactor event loop. Dùng reactive decoder/introspector/managers.

### 13.1. WebFlux tách JWT và opaque theo URL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain admin(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/admin/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasAuthority("SCOPE_admin.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain partner(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/partners/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/partners/**")
                    .hasAuthority("SCOPE_partner.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain fallback(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth.anyExchange().denyAll())
            .build();
    }
}
~~~

Decoder/introspector/validators cần được cấu hình riêng, và CSRF/CORS policy phải phù hợp browser/client.

### 13.2. Multi-issuer WebFlux

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
        "https://identity-a.example.com/realms/shop",
        "https://identity-b.example.com/realms/partners"
    );

http.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(resolver));
~~~

Issuer phải thuộc tập được quản trị, token vẫn cần verify signature/audience/expiration. Không lấy arbitrary URL trong unverified iss làm source trust.

## 14. OR, AND, SELECT-ONE: lựa chọn nào được yêu cầu?

### 14.1. OR

~~~text
Legacy endpoint:
  Basic đúng -> được phép
  Bearer đúng -> được phép
  Cả hai sai -> từ chối
~~~

Cần định nghĩa authority mapping, HTTP challenge và security requirements cho cả hai.

### 14.2. AND

~~~text
mTLS certificate hợp lệ
AND JWT access token có binding đúng client
AND SCOPE_orders.write
~~~

ProviderManager mặc định không tự hiện thực tổ hợp này. Cần policy kết hợp factors, xác minh ràng buộc giữa chúng và test thiếu yếu tố nào cũng bị từ chối.

### 14.3. SELECT-ONE

~~~text
/api/admin/** -> JWT manager
/api/partners/** -> opaque manager
JWT issuer A -> decoder A
JWT issuer B -> decoder B
~~~

Đây thường là chiến lược rõ ràng nhất khi các nguồn trust khác nhau.

**Không dùng “thử hết providers cho tới khi thành công” thay thế một chính sách lựa chọn cụ thể.**

## 15. Authorization vẫn phải đúng sau authentication

Một rule:

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
)
~~~

chỉ yêu cầu Authentication đã được thiết lập. Nó không yêu cầu **SCOPE_orders.write** cho POST, role ADMIN hoặc quyền trên bản ghi.

Khi nhiều providers có thể tạo principal, rule quá rộng khiến token từ một cơ chế vốn ít đặc quyền có thể đi qua.

Cần kiểm:

- Scope theo HTTP method/path.
- Issuer và audience/token purpose.
- Role/permission từ nguồn được phép cấp.
- Tenant/organization.
- Resource ownership và trạng thái nghiệp vụ.
- Client identity và delegation.
- Domain policies độc lập với HTTP authentication.

Không tự cộng quyền giữa hai principals khác nhau hoặc tạo một principal mới từ raw unverified token.

## 16. WWW-Authenticate khi có nhiều mechanisms

| Request | Kết quả thường gặp |
|---|---|
| Protected Bearer API, không token | 401 + WWW-Authenticate: Bearer |
| Bearer token invalid | 401, có thể error=invalid_token |
| Token hợp lệ thiếu scope | 403, có thể error=insufficient_scope |
| Basic credentials sai | 401 + Basic challenge |
| Web OIDC user chưa login | Redirect login nếu web flow dùng interactive login |

Nếu cùng một chain hỗ trợ cả Basic và Bearer, entry point có thể cần chọn challenge theo request hoặc công bố nhiều schemes theo HTTP semantics. **Provider order không tự quyết định challenge hợp lệ**.

Machine clients cần API status/challenge rõ, không phải redirect HTML mặc định.

## 17. Test chồng lấn bằng ma trận credential

Ví dụ policy mong muốn:

| Endpoint | JWT admin | Opaque partner | Basic | OIDC cookie | Không credential |
|---|---|---|---|---|---|
| GET /api/admin/reports | Cho phép nếu đủ scope | Từ chối | Từ chối | Từ chối | 401 |
| POST /api/admin/jobs | Cho phép nếu đủ scope | Từ chối | Từ chối | Từ chối | 401 |
| GET /api/partners/orders | Từ chối | Cho phép nếu đủ scope | Từ chối | Từ chối | 401 |
| POST /api/partners/orders | Từ chối | Từ chối | Từ chối | Từ chối | Từ chối |
| GET /web/profile | Theo web policy | Theo web policy | Theo web policy | Có session hợp lệ | Web challenge |
| GET /internal/export | Fallback từ chối | Fallback | Fallback | Fallback | Fallback |

Đây là **ma trận yêu cầu**, không phải kết quả mặc định Spring Security tự cung cấp.

### 17.1. Negative tests phải có

1. JWT giả chữ ký ở admin API → không được opaque manager xác thực thay.
2. JWT đúng chữ ký nhưng sai issuer → từ chối.
3. JWT đúng issuer nhưng sai audience → từ chối.
4. JWT issuer A ở endpoint chỉ tin issuer B → từ chối.
5. Issuer lạ trong JWT → resolver không tạo decoder trust URL đó.
6. Opaque token active=true ở partner AS gửi vào admin API → từ chối.
7. Basic credential gửi vào Bearer-only API → không authenticate.
8. Chỉ JSESSIONID gửi vào Bearer-only API → không authenticate.
9. Có cả Bearer và cookie → hành vi theo policy rõ, không cộng principals.
10. Token hợp lệ nhưng thiếu scope → từ chối.
11. Token đủ scope nhưng sai tenant/ownership → từ chối.
12. POST/DELETE không vô tình được xử lý bởi rule read-only.
13. Route mới ngoài chains chuyên biệt → fallback từ chối.
14. OIDC ID Token không được dùng như access token ở Resource Server.
15. Path variants, context path, proxy rewrite và management port được kiểm.

### 17.2. MockMvc .with(jwt()) không chứng minh decoder hoạt động

Ví dụ:

~~~java
mockMvc.perform(get("/api/admin/reports").with(jwt()))
    .andExpect(status().isOk());
~~~

Thông thường **jwt()** của Spring Security Test tạo Authentication mô phỏng; nó không chứng minh JWT signature đã được verify.

Để kiểm đường đi thật, dùng JWT ký bằng private test key, decoder trust public test key và gửi **Authorization: Bearer** qua filters. Với opaque token, dùng HTTP stub introspection trả active=true/false.

**MockMvc phải chạy Spring Security filters thực sự**. Không dựa vào standaloneSetup hoặc addFilters=false làm bằng chứng security. Một 404 từ route không có controller cũng không chứng minh chain đã bảo vệ endpoint.

### 17.3. Unit test ProviderManager

Tạo test doubles:

- Provider A hỗ trợ request nhưng trả null; B thành công.
- A thành công; B không được gọi.
- A ném lỗi authentication; B có thể thành công theo semantics.
- A ném AccountStatusException; không thử B.
- Không provider hỗ trợ; authentication thất bại.

Những tests này xác minh **điều phối kỹ thuật**, không chứng minh fallback JWT sang opaque là một thiết kế an toàn.

## 18. Reverse proxy, URL matcher và độ bao phủ

Một request có URL công khai:

~~~text
Public:  https://api.example.com/v1/admin/reports
Backend: /api/admin/reports
~~~

Nếu proxy rewrite path, Spring Security thường đánh giá path đã đến backend, không phải URL hiển thị bên ngoài.

Cần kiểm:

- Servlet context path và servlet mapping.
- HTTP methods, path variants và trailing slash.
- Encoded path/normalization và alias routes.
- Ingress/gateway rewrites.
- Actuator trên management port khác.
- Dispatcher types, ví dụ ERROR/FORWARD khi phù hợp.
- Fallback không mở route ngoài ý muốn.
- Filter registration thực sự áp dụng.

**Route coverage và provider coverage là hai vấn đề khác nhau**. Đúng provider nhưng request không vào chain vẫn có lỗ hổng.

## 19. Logging và quan sát điều phối

Khi điều tra 401/403, cần biết:

- Chain nào đã match?
- Filter/scheme nào đã nhận credential?
- Manager/provider logical name nào được chọn?
- Issuer nào đã được verify, không chỉ raw iss chưa verify?
- Lỗi là signature, audience, inactive token, scope hay upstream timeout?
- Rule/domain policy nào từ chối?
- HTTP challenge thuộc Bearer, Basic hay web login?

Chỉ log **logical names, request correlation ID, route template và error classes đã sanitize**. Không log raw Authorization header, JWT/opaque token, Basic credentials, client secret hoặc session cookie.

### 19.1. ProviderManager và credential erasure

Theo ProviderManager JavaDoc, sau Authentication thành công, credentials của result có thể được xóa nếu Authentication triển khai **CredentialsContainer**, được điều khiển bởi thuộc tính eraseCredentialsAfterAuthentication.

Điều này không tự xóa credential đã bị đưa vào logs, request body hoặc custom properties. Không tắt credential erasure chỉ để debug.

### 19.2. Authentication events

ProviderManager hỗ trợ **AuthenticationEventPublisher**. Khi tự cấu hình managers, cần bảo đảm publisher được wiring theo nhu cầu. Nếu có parent manager, tránh events trùng từ parent và child. Không gửi credentials vào events.

## 20. Anti-pattern dễ gặp

**Thêm JWT và opaque providers cùng hỗ trợ Bearer rồi fallback theo authentication error.** Có thể gây cross-strategy policy downgrade.

**supports(Authentication.class) ở custom provider.** Nhận nhiều request types hơn khả năng xác minh.

**ProviderManager được hiểu là AND.** Nhiều providers không tự tạo MFA.

**Chain rộng permitAll đặt trước chain chuyên biệt.** Chain quan trọng bị che khuất.

**Không có fallback.** Endpoint mới có thể không qua Spring Security.

**Tạo decoder từ iss/jku chưa verify của token bất kỳ.** Mở trust boundary/SSRF.

**Cùng scope string giữa nhiều issuers được coi là cùng quyền.** Có thể nhầm tenant/resource.

**OIDC ID Token được dùng như Bearer access token.** Sai mục đích token.

**Session cookie hoặc Basic đi vào Bearer-only API.** Phá ranh giới credential, tăng CSRF risk.

**Chỉ yêu cầu authenticated cho thao tác quản trị.** Thiếu authorization theo scope/role/domain.

**Tắt CSRF toàn ứng dụng vì có JWT.** Sai khi còn browser sessions/cookies.

**JWKS/introspection timeout thì cho qua bằng principal giả.** Không có authentication đáng tin, phải fail-closed.

**Dùng mockJwt() hoặc jwt() post-processor rồi cho rằng đã test signature.** Chỉ mô phỏng Authentication.

## 21. Quy trình triển khai có thể áp dụng

**Bước 1 — Kiểm kê endpoints:** HTTP method, public/backend path, servlet context, management port, handler và expected access.

**Bước 2 — Mô tả accepted credentials cho từng route:** Bearer JWT, opaque, Basic, session hay OIDC Login.

**Bước 3 — Xác định trust contract:** issuer/JWKS/algorithm/audience hoặc introspection URI/client authentication/active, scopes và tenant.

**Bước 4 — Chọn cơ chế điều phối:** chains riêng theo path, issuer resolver cho nhiều JWT issuers, manager resolver khi một chain thật sự có nhiều strategies, multi-factor policy riêng nếu cần AND.

**Bước 5 — Thiết kế thứ tự/matcher:** specialized chains trước, fallback denyAll cuối, tránh overlap không rõ.

**Bước 6 — Kiểm supports và result:** custom providers chỉ nhận đúng types, không tạo success từ unverified credentials.

**Bước 7 — Kiểm authorization:** method-specific scope, role, audience, tenant, ownership; authenticated không đủ cho endpoint nhạy cảm.

**Bước 8 — Viết negative integration tests:** cross-issuer, cross-token-format, Basic/session vào Bearer-only, missing/invalid token, wrong scope/audience, unknown route, path variants.

**Bước 9 — Kiểm phản hồi:** 401 Bearer challenge cho API, 403 khi thiếu quyền, interactive login handling cho website, CSRF policy theo ambient credential.

**Bước 10 — Review lại khi thêm issuer/provider/route:** một cơ chế mới có thể vô tình khiến request vốn bị từ chối trước đây trở nên hợp lệ.

## 22. Câu hỏi tự kiểm tra

**1. Hai SecurityFilterChain cùng match một request thì cả hai có chạy không?**

Không. Chain đầu tiên khớp được chọn.

**2. Hai AuthenticationProvider cùng supports BearerTokenAuthenticationToken thì provider sau có thể được thử nếu provider trước lỗi không?**

Có thể, tùy exception và ProviderManager semantics. Do đó phải tránh fallback không có trust policy.

**3. supports() có chứng minh token JWT hợp lệ không?**

Không. Nó chỉ kiểm loại Authentication request.

**4. Một JWT đúng chữ ký nhưng audience là billing-api có được dùng ở orders-api không?**

Không nếu audience policy yêu cầu orders-api.

**5. Có nên tạo decoder cho issuer bất kỳ do JWT chưa verify tự khai không?**

Không. Chỉ issuer nằm trong allowlist/kho trust được quản trị.

**6. Thêm mTLS provider và JWT provider có đủ để yêu cầu cả hai yếu tố không?**

Không. Cần policy AND và binding phù hợp.

**7. Một OIDC session cookie có nên tự authenticate Bearer-only API không?**

Không nếu policy API chỉ nhận Bearer token.

**8. Chỉ cấu hình anyRequest().authenticated() trong chain /api/** có bảo vệ /internal/export không?**

Không. Cần chain khác/fallback.

**9. Test .with(jwt()) trả 200 có chứng minh JwtDecoder đã kiểm chữ ký chưa?**

Chưa. Cần test Authorization header thật với JWT được ký/test keys.

**10. Khi đã xác thực xong có còn cần kiểm tenant và ownership không?**

Có. Authentication không tự cấp quyền trên mọi tài nguyên.

## Kết luận

**Phối hợp nhiều AuthenticationProvider** đòi hỏi phân tách ba nhiệm vụ:

1. **SecurityFilterChain** chọn phạm vi HTTP request, first-match theo thứ tự.
2. **AuthenticationManager/ProviderManager** xác minh credential thông qua providers; cùng một Authentication request type có thể được nhiều providers hỗ trợ, và một lỗi ở provider trước có thể bị thay bằng success từ provider sau.
3. **Authorization** kiểm scope, role, issuer/audience, tenant và quyền trên tài nguyên sau khi Authentication thành công.

Với JWT/opaque Bearer token, **đừng mặc định thử cả hai providers tới khi một cái chấp nhận**. Hãy dùng **SecurityFilterChain tách theo route** hoặc **AuthenticationManagerResolver** được thiết kế theo trust policy, kết hợp trusted-issuer allowlist, fallback fail-closed và negative tests giữa mọi authentication mechanisms.

### Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security API — ProviderManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security API — AuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security — Servlet Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Reactive Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Opaque Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
