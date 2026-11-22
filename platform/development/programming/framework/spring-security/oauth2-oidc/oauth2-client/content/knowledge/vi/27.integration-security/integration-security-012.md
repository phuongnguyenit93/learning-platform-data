# 27.12. Phân biệt xác thực người dùng, ủy quyền ứng dụng và bảo vệ API

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, ba trách nhiệm bảo mật thường được gọi chung là “đăng nhập OAuth”:

1. **Xác thực người dùng (User Authentication)**: Ai đang đăng nhập vào ứng dụng và người đó đã được xác thực bởi bên nào?
2. **Ủy quyền ứng dụng (OAuth2 Client Authorization)**: Ứng dụng có được Authorization Server cấp access token để truy cập API theo quyền/phạm vi cụ thể không?
3. **Bảo vệ API (Resource Server Security)**: API có chấp nhận access token và cho phép thao tác trên tài nguyên cụ thể không?

Ba hoạt động có thể xuất hiện nối tiếp trong một trải nghiệm, nhưng **không đồng nghĩa nhau**. OIDC ID token không phải access token dùng gọi API; có access token không có nghĩa mọi API đều phải chấp nhận; client credentials có thể cấp token cho một service mà không có End-User nào đăng nhập.

Bài học phân tích ranh giới giữa **Browser**, **Spring Security OAuth2/OIDC Client**, **Authorization Server/OpenID Provider**, **Resource Server**, và lớp phân quyền nghiệp vụ.

Sau bài, bạn có thể:

- Phân biệt roles của End-User, Resource Owner, Client, Authorization Server, Relying Party và Resource Server.
- Hiểu `oauth2Login()`, `oauth2Client()` và `oauth2ResourceServer()` đảm nhiệm những việc khác nhau.
- Dùng đúng ID token, access token, refresh token, authorization code và session cookie.
- Giải thích vì sao OIDC Login thành công chưa bảo đảm token phù hợp Orders API.
- Tích hợp Portal dùng session/cookie với Orders API dùng Bearer access token.
- Cấu hình Spring Security Resource Server xác minh issuer, audience, signature, expiry và scope.
- Kết hợp `SCOPE_*` với quyền tenant, owner và domain policy.
- Phân biệt authorization_code, refresh_token và client_credentials với những ngữ cảnh sử dụng riêng.
- Hiểu Token Relay, Token Exchange, BFF và SPA gọi API trực tiếp.
- Thiết kế 401/403, CSRF/CORS, logout, session/refresh và bảo mật token.
- Viết kiểm thử khẳng định authentication, token authorization và API authorization thực sự được thực hiện độc lập.

## 1. Tình huống: Alice mở Orders Portal

Giả sử hệ thống có:

- **Alice** dùng browser.
- **Employee Portal** viết bằng Spring Boot, Spring Security và OIDC Client.
- **Company OpenID Provider** vừa xác thực End-User vừa cấp OAuth2 tokens.
- **Orders API** là một OAuth2 Resource Server.
- **Orders Database** lưu đơn hàng của nhiều user và tenant.

~~~mermaid
flowchart LR
    A["Alice / Browser"] -->|"Portal session cookie"| P["Employee Portal"]
    P -->|"OIDC Authorization Code"| OP["OpenID Provider / AS"]
    OP -->|"ID token, access token"| P
    P -->|"Bearer access token"| API["Orders API"]
    API -->|"Tenant + owner checks"| DB["Orders database"]
    API -->|"Orders data"| P
    P --> A
~~~

Một trải nghiệm “Xem đơn hàng” cần ba câu trả lời:

| Câu hỏi | Bên thực hiện | Bằng chứng |
|---|---|---|
| Alice là ai? | OP xác thực; Portal kiểm tra OIDC response | ID token, issuer/subject, local Authentication |
| Portal có token để gọi Orders API không? | AS cấp token, OAuth2 Client quản lý | `OAuth2AuthorizedClient`, access token, scope |
| Alice có quyền xem đơn hàng 123 không? | Orders API và domain service | Token hợp lệ, API scope, tenant/owner policy |

**Việc Alice có thể đăng nhập Portal không tự cấp cho cô ấy quyền xem mọi đơn hàng.**

### 1.1. Mỗi bên bảo vệ một ranh giới

~~~text
OpenID Provider:
  Xác thực Alice, phát ID token.

Authorization Server:
  Cấp access token/refresh token cho OAuth client.

Employee Portal (OAuth2/OIDC Client):
  Đăng nhập browser, quản lý authorized client,
  sử dụng access token để gọi API.

Orders API (Resource Server):
  Xác minh access token của incoming request,
  áp endpoint/method authorization.

Orders domain:
  Kiểm tra order owner, tenant và nghiệp vụ.
~~~

Một sản phẩm Identity Provider có thể thực hiện cả OP và AS. Dù cùng sản phẩm, trách nhiệm **authentication** và **token authorization** vẫn khác nhau.

## 2. Xác thực người dùng bằng OIDC

**Authentication** trả lời “Ai đang đăng nhập?”. Trong OIDC, ứng dụng sử dụng OP để xác thực user theo một authentication flow.

### 2.1. Authorization Code flow

~~~mermaid
sequenceDiagram
    autonumber
    actor Alice
    participant Browser
    participant Portal as Portal / OIDC Client
    participant OP as OpenID Provider
    Alice->>Browser: Mở /dashboard
    Browser->>Portal: Request chưa login
    Portal-->>Browser: Redirect authorization endpoint
    Browser->>OP: OIDC Authorization Request
    OP->>OP: Đăng nhập/MFA/consent theo policy
    OP-->>Browser: Callback code + state
    Browser->>Portal: Callback
    Portal->>OP: Đổi code tại token endpoint
    OP-->>Portal: Token response
    Portal->>Portal: Validate ID token, tạo Authentication
    Portal-->>Browser: Session cookie và dashboard
~~~

Spring Security OAuth2 Login xử lý authorization request, state correlation, callback, token exchange và OIDC validation theo cấu hình của ứng dụng.

### 2.2. ID token dành cho Relying Party

Ví dụ claims trong ID token:

~~~json
{
  "iss": "https://id.company.example",
  "sub": "alice-123",
  "aud": "employee-portal",
  "exp": 1795000000,
  "iat": 1794999700,
  "auth_time": 1794999600
}
~~~

Đây là dữ liệu minh họa, không phải credential thật.

- `iss`: OP phát hành.
- `sub`: subject trong phạm vi issuer.
- `aud`: client/Relying Party mà ID token được phát cho.
- `exp`: thời điểm hết hạn.
- `auth_time`: thời điểm authentication nếu được đưa vào theo yêu cầu/profile.

**ID token được cấp cho Portal để xác nhận authentication**, không mặc định được cấp cho Orders API.

### 2.3. Principal trong Portal

Sau OIDC Login, Spring Security thường có:

~~~text
OAuth2AuthenticationToken
  principal: OidcUser
  authorizedClientRegistrationId: corporate
  authorities: ...
~~~

Một Servlet controller có thể lấy user:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    Profile me(@AuthenticationPrincipal OidcUser user) {
        return new Profile(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject());
    }

    record Profile(String issuer, String subject) {}
}
~~~

Ví dụ giả định endpoint chỉ hỗ trợ OIDC Login. Trong app hỗ trợ form login, OAuth2-only Login hoặc Bearer auth, principal có thể khác kiểu; không ép cast tất cả thành `OidcUser`.

### 2.4. Browser session của Portal

Một Portal truyền thống có thể giữ `SecurityContext` trong HttpSession. Browser gửi cookie cho Portal ở các requests tiếp theo.

~~~http
GET /orders HTTP/1.1
Host: portal.example.com
Cookie: SESSION=...
~~~

Cookie chứng minh browser đang mang session tại **Portal**. Nó không tự trở thành OAuth access token hợp lệ của Orders API.

### 2.5. Login đúng không đồng nghĩa đủ quyền

Alice có thể được OP xác thực chính xác nhưng:

- Không thuộc tenant được chọn.
- Không có role duyệt đơn.
- Không có scope API cần thiết.
- Đã bị thu hồi membership sau khi login.
- Không phải owner của đơn hàng đang yêu cầu.

Authentication là điều kiện cần trong nhiều workflow, **không thay thế authorization**.

## 3. OAuth2 Client Authorization: lấy token để gọi API

OAuth2 Client Authorization liên quan đến việc client được phép xin và sử dụng access token cho một Resource Server theo grant và policy của AS.

### 3.1. `ClientRegistration` khác `OAuth2AuthorizedClient`

~~~text
ClientRegistration:
  registrationId = corporate
  clientId = employee-portal
  grantType = authorization_code
  scopes = openid profile orders.read

OAuth2AuthorizedClient:
  registration = corporate
  principalName = alice-123
  accessToken = A1
  refreshToken = R1 (nếu AS cấp)
~~~

`ClientRegistration` là cấu hình client. `OAuth2AuthorizedClient` là trạng thái token đã được AS cấp, thường liên kết registration và principal.

### 3.2. Manager và provider

Trong Servlet:

~~~text
OAuth2AuthorizedClientManager
  -> OAuth2AuthorizedClientProvider
  -> ClientRegistrationRepository
  -> OAuth2AuthorizedClientRepository / Service
~~~

Trong WebFlux:

~~~text
ReactiveOAuth2AuthorizedClientManager
  -> ReactiveOAuth2AuthorizedClientProvider
  -> ReactiveClientRegistrationRepository
  -> ServerOAuth2AuthorizedClientRepository / Reactive Service
~~~

Manager điều phối token hiện có, refresh hoặc xin token mới theo grant. Mỗi lần gọi manager **không nhất thiết phát sinh token endpoint request mới**.

### 3.3. Grant và ngữ cảnh

| Grant | Ngữ cảnh phổ biến | Có xác thực End-User ngay tại mỗi token request không? |
|---|---|---|
| `authorization_code` | Browser/user tương tác với AS | Flow có authentication/consent theo AS policy |
| `refresh_token` | Client đổi refresh token lấy access token mới | Không tự tạo authentication mới |
| `client_credentials` | Service-to-service | Không có End-User authentication |
| Token Exchange | Client đổi một token lấy token khác theo AS policy | Phụ thuộc token nguồn/AS profile |

### 3.4. Consent không thay quyền trên từng object

Alice đồng ý `orders.read` cho Portal có thể giúp AS cấp access token cho Orders API.

Nhưng việc Alice có thể đọc **order 123** hay không là quyết định của Orders API/domain policy.

## 4. Bảo vệ API: Resource Server

Orders API nhận incoming request:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Resource Server có trách nhiệm xác minh token và áp quyền.

### 4.1. Các lớp kiểm tra cần thiết

1. Request có credential đúng cơ chế API.
2. JWT signature hợp lệ hoặc opaque token introspection hợp lệ.
3. Issuer là AS mà API tin cậy.
4. Token chưa hết hạn, `nbf`/time claims nếu có hợp lệ.
5. Audience/resource dành cho API này.
6. Scope/authorities đủ cho endpoint/method.
7. User/service được phép truy cập tenant và object cụ thể.
8. Các policy bổ sung như resource state, rate limit, network boundary nếu yêu cầu.

**JWT chữ ký đúng chưa đồng nghĩa user có quyền trên từng dữ liệu.**

### 4.2. Principal ở API khác principal ở Portal

Portal OIDC Login thường tạo `OAuth2AuthenticationToken` có `OidcUser`.

Orders API khi xác minh JWT access token thường tạo `JwtAuthenticationToken` với JWT claims và authorities tương ứng.

~~~text
Portal SecurityContext:
  OAuth2AuthenticationToken
  principal = OidcUser

Orders API SecurityContext:
  JwtAuthenticationToken
  principal = Jwt
  authorities = SCOPE_orders.read
~~~

Không serialize Portal SecurityContext qua mạng rồi coi nó là cơ sở xác thực ở Resource Server.

### 4.3. Ba lớp authorization

| Lớp | Ví dụ | Trách nhiệm |
|---|---|---|
| Token validity | Issuer, signature, expiry, audience | Resource Server security layer |
| Coarse-grained | `SCOPE_orders.read` | Request/method authorization |
| Fine-grained | Owner, tenant, order status | Business service/database |

## 5. So sánh trực tiếp

| Khía cạnh | OIDC User Authentication | OAuth2 Client Authorization | Resource Server/API Protection |
|---|---|---|---|
| Câu hỏi | Ai đang đăng nhập? | Client được cấp token gì? | Request được làm gì? |
| Vai trò | OP + RP | AS + Client | Resource Server |
| Kết quả chính | Authenticated principal/session | Access token/authorized client | Allow/deny request |
| Credential liên quan | ID token | Access/refresh token | Access token |
| Spring Security DSL | `oauth2Login()` | `oauth2Client()` | `oauth2ResourceServer()` |
| Object | `OidcUser` | `OAuth2AuthorizedClient` | `JwtAuthenticationToken` |
| Có xác minh owner? | Không đủ | Không đủ | Cần ở domain |
| Refresh token | Không chứng minh MFA mới | Có thể hỗ trợ refresh | Resource Server không nhận refresh token |
| Có thể không có user? | Không cho OIDC Login của user | Có, với client_credentials | Có, API có thể nhận service token |

## 6. Dùng đúng token cho đúng bên nhận

| Token/giá trị | Mục đích | Bên nhận dự kiến |
|---|---|---|
| Authorization code | Đổi token theo Authorization Code flow | AS token endpoint |
| ID token | Xác nhận authentication End-User cho RP | OIDC Client/Relying Party |
| Access token | Truy cập protected API | Resource Server đúng audience |
| Refresh token | Xin access token mới | AS token endpoint |
| Session cookie | Nhận diện session browser tại Portal | Portal |
| Client secret | Xác thực confidential client | AS token endpoint theo client authentication |

### 6.1. ID token không phải API Bearer token

Ví dụ ID token có:

~~~json
{
  "iss": "https://id.company.example",
  "sub": "alice-123",
  "aud": "employee-portal"
}
~~~

Orders API phải không tự chấp nhận ID token như access token. Audience và token semantics dành cho RP.

### 6.2. Access token có thể opaque

OAuth2 không bắt buộc access token là JWT. AS có thể cấp opaque token.

- JWT access token: API xác minh signature/JWKS/issuer/time/audience.
- Opaque access token: API thường gọi introspection endpoint theo AS contract.

Chỉ Base64-decode JWT payload không phải xác minh chữ ký.

### 6.3. Refresh token không đến Resource Server

Client gửi refresh token tới AS token endpoint. Không gửi nó đến Orders API để “chứng minh token sắp hết hạn”.

### 6.4. Session cookie không tự hoạt động ở API độc lập

Orders API có thể hoàn toàn không biết session cookie của Portal. Nếu API nhận Bearer token, nó phải xác minh Bearer token theo policy riêng.

## 7. Kiến trúc BFF: Browser dùng cookie, Portal gọi API

Với **Backend for Frontend (BFF)**, browser dùng session cookie với Portal; OAuth tokens ở backend.

~~~mermaid
flowchart LR
    B["Browser"] -->|"Session cookie"| P["Portal BFF"]
    P -->|"OIDC Login"| AS["OpenID Provider"]
    AS -->|"Tokens"| P
    P -->|"Bearer access token"| O["Orders API"]
    O --> D["Orders DB"]
~~~

Ưu điểm:

- Browser không phải giữ raw refresh token trong localStorage.
- Portal kiểm soát outbound API destinations.
- Client có thể quản lý token refresh server-side.

Nhưng BFF vẫn cần:

- Bảo vệ session cookie.
- CSRF protection cho browser state-changing requests.
- Chống XSS/clickjacking và session fixation.
- Không log tokens.
- API authorization ở Resource Server.

### 7.1. Browser request

~~~http
GET /orders HTTP/1.1
Host: portal.example.com
Cookie: SESSION=...
~~~

### 7.2. Portal outbound request

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Đây là hai ranh giới credential khác nhau, không nên nhập làm một.

## 8. Cấu hình Portal làm OIDC Client

Dự án Spring Boot Servlet có thể dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-op
            client-id: ${PORTAL_OIDC_CLIENT_ID}
            client-secret: ${PORTAL_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-op:
            issuer-uri: https://id.company.example
~~~

OP phải thực sự cấp access token phù hợp Orders API. Chỉ yêu cầu scope `orders.read` **không tự đảm bảo audience đúng**.

### 8.1. Portal SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfiguration {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/", "/login", "/error", "/css/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

- `oauth2Login()` tạo browser authentication/session qua OP.
- `oauth2Client()` hỗ trợ authorized client/token usage.
- `authenticated()` yêu cầu Authentication cho protected Portal routes.
- Ví dụ không tắt CSRF đối với session-based UI.

### 8.2. Portal không tự trở thành API Resource Server

Cấu hình trên không đồng nghĩa Portal đã hỗ trợ incoming Bearer JWT requests. Muốn bảo vệ API Bearer, phải cấu hình Resource Server phù hợp.

## 9. Portal gọi Orders API qua access token

Với Spring Boot/Spring Framework hiện đại, Portal Servlet có thể dùng `RestClient` (Spring Framework 6.1+) cùng authorized client:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation
        .RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersPortalController {

    private final RestClient ordersApi;

    public OrdersPortalController(RestClient.Builder builder) {
        this.ordersApi = builder
                .baseUrl("https://orders-api.example.com")
                .build();
    }

    @GetMapping("/orders")
    String orders(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        return ordersApi.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(
                        client.getAccessToken().getTokenValue()))
                .retrieve()
                .body(String.class);
    }
}
~~~

Ví dụ giả định `corporate` đã có authorized client và access token phù hợp API. Nếu token hết hạn, refresh/token management phụ thuộc authorized client manager/provider và cấu hình của dự án.

### 9.1. Sai: dùng ID token

~~~java
String wrongToken =
        oidcUser.getIdToken().getTokenValue();

headers.setBearerAuth(wrongToken);
~~~

ID token dành cho Portal, không phải API access token.

### 9.2. Đúng loại token vẫn cần đúng audience

~~~java
String accessToken =
        client.getAccessToken().getTokenValue();

headers.setBearerAuth(accessToken);
~~~

API vẫn phải xác minh token này được AS cấp **cho Orders API** và có quyền tương ứng.

### 9.3. Không trả raw token cho browser

Controller nên trả dữ liệu nghiệp vụ hoặc error, không serialize `OAuth2AuthorizedClient` với refresh token ra JSON.

### 9.4. Không gắn bearer vào URL tùy ý

Một endpoint:

~~~text
GET /proxy?url=https://attacker.example.net
~~~

mà backend gắn access token vào URL do user quyết định có thể gây lộ credential. Dùng HTTP client riêng theo API, whitelist host/scheme/port và kiểm soát redirects.

## 10. Orders API là một Resource Server

Maven dependencies của **Orders API**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.company.example

app:
  security:
    required-audience: orders-api
~~~

`required-audience` là property **custom của ứng dụng** được dùng trong validator minh họa tiếp theo.

### 10.1. SecurityFilterChain Bearer-only

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class OrdersApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(
                                HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

### 10.2. Vì sao ví dụ tắt CSRF?

Ví dụ API này được thiết kế **chỉ chấp nhận bearer Authorization header, không dùng cookie/session làm authentication**. Trong mô hình đó có thể vô hiệu hóa CSRF token requirement cho API.

**Không copy `csrf.disable()` sang Portal dùng session cookie hoặc API hỗn hợp.** Nếu browser tự gửi ambient credentials, cần đánh giá CSRF lại.

### 10.3. `STATELESS` không bỏ Authentication

Spring Security vẫn xác minh Bearer token cho mỗi request, tạo Authentication và áp authorization. Stateless chỉ không dùng HttpSession làm nơi lưu SecurityContext cho các request API theo cấu hình đó.

### 10.4. `SCOPE_*` đến từ scope mapping

Access token JWT có thể chứa:

~~~json
{
  "iss": "https://id.company.example",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
~~~

`JwtGrantedAuthoritiesConverter` mặc định có thể ánh xạ thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Nếu AS dùng claim khác/format khác, cần cấu hình converter phù hợp. Không mặc định mọi `roles` claim tự trở thành `ROLE_*`.

## 11. JWT audience validation

Giả sử Billing API và Orders API cùng tin issuer:

~~~text
https://id.company.example
~~~

Một token:

~~~json
{
  "iss": "https://id.company.example",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
~~~

có signature hợp lệ nhưng **không dành cho Orders API**.

### 11.1. Thêm audience validator

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${app.security.required-audience}")
            String requiredAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(requiredAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            OAuth2Error error = new OAuth2Error(
                    "invalid_token",
                    "Orders API audience is required",
                    null);
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(issuer),
                        audience));

        return decoder;
    }
}
~~~

Mẫu minh họa này bổ sung audience validation bên cạnh issuer và các kiểm tra JWT mặc định. JWK/trust configuration phải được bảo vệ; không lấy issuer/JWKS URL tùy ý từ browser request.

### 11.2. ID token audience khác access token audience

OIDC ID token `aud` thường là client ID của Portal. Access token `aud` thường phải chỉ rõ Resource Server theo AS token profile.

Đừng làm Orders API chấp nhận token chỉ vì audience bằng client ID của Portal nếu AS/API contract không quy định như vậy.

### 11.3. Token có nhiều audiences

Một token có thể có danh sách `aud`. API kiểm tra audience cho chính nó và những điều kiện bổ sung, không tự chấp nhận mọi JWT do issuer ký.

### 11.4. Signature validity chưa phải authorization

JwtDecoder kiểm tra chữ ký và một số claim validity. Sau đó authorization rules/method checks vẫn phải xác định scope và quyền domain.

## 12. Opaque access token và introspection

Nếu AS phát opaque access token, Resource Server không thể tự parse nó như JWT.

Ví dụ cấu hình Spring Security:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://id.company.example/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
~~~

Các yêu cầu:

- AS có introspection endpoint tương thích.
- Orders API có client credentials được phép introspect.
- Kết quả `active` và các claims được đánh giá đúng theo policy.
- API vẫn kiểm tra audience/scope khi metadata và contract hỗ trợ.
- Owner/tenant authorization vẫn nằm ở domain service.

### 12.1. Introspection không thay owner check

AS có thể trả `active=true`, nhưng Alice vẫn có thể không được xem order 123.

### 12.2. Caching và revocation

Nếu cache introspection response, cần cân nhắc revocation freshness và token lifetime. Cache quá lâu có thể khiến token đã bị revoke vẫn được chấp nhận trong một khoảng thời gian.

## 13. Scope không đủ để đọc mọi tài nguyên

Giả sử Alice có access token với `orders.read` và gọi:

~~~http
GET /api/orders/123 HTTP/1.1
Authorization: Bearer <ACCESS_TOKEN>
~~~

Orders API phải kiểm tra liệu order 123 thuộc tenant của Alice và Alice có quyền đọc nó.

### 13.1. Tenant/owner authorization

Ví dụ service:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public Optional<Order> findVisible(
            String verifiedTenantId,
            String verifiedUserId,
            String orderId) {

        return repository
                .findByTenantIdAndId(
                        verifiedTenantId, orderId)
                .filter(order ->
                        order.ownerUserId()
                                .equals(verifiedUserId));
    }
}
~~~

`OrderRepository` và `Order` là domain abstractions minh họa. `verifiedTenantId` và `verifiedUserId` phải đến từ validated identity/authorization context, không phải body/query do caller tự khai rồi xem là đã xác minh.

### 13.2. Method Security

Ví dụ sau sử dụng bean `orderAccess` do ứng dụng tự hiện thực:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {

    @PreAuthorize(
            "hasAuthority('SCOPE_orders.read')"
            + " and @orderAccess.canRead(authentication, #orderId)")
    public Order getOrder(String orderId) {
        throw new UnsupportedOperationException(
                "Domain implementation omitted");
    }
}
~~~

`@EnableMethodSecurity` phải được bật phù hợp và `orderAccess.canRead` cần kiểm tra tenant/owner/resource mà không rò rỉ dữ liệu.

### 13.3. IDOR/BOLA

Kẻ tấn công có thể sửa order ID trong URL. Chỉ kiểm tra bearer token + scope không ngăn việc đọc object của người khác. Đây là lý do API cần Broken Object Level Authorization protection.

### 13.4. Chỉ return data sau khi kiểm tra

Không tải toàn bộ dữ liệu mọi tenant rồi chỉ lọc ở frontend. Các truy vấn nên có tenant/owner predicates ở service/database theo kiến trúc.

## 14. Scope, role, group và domain permission khác nhau

| Dữ liệu | Nguồn | Ý nghĩa |
|---|---|---|
| `scope=orders.read` | AS cấp access token | Quyền token ở mức phạm vi |
| `SCOPE_orders.read` | Spring token-to-authority mapping | Authority trong API SecurityContext |
| `groups=[finance]` | OP/Identity Directory | Danh tính/nhóm theo provider |
| `ROLE_ORDER_ADMIN` | Application mapping | Quyền role nội bộ |
| Tenant membership | SaaS membership service | User thuộc tenant nào |
| Resource owner | Database | User có quyền trên object nào |

### 14.1. Không tự map mọi nhóm thành admin

Một nhóm có tên `admins` ở OP A không mặc định tương đương `ROLE_ADMIN` ở Orders API. Cần trust/mapping theo issuer, tenant và policy.

### 14.2. Scope là coarse-grained

Scope thường là điều kiện cần cho endpoint, nhưng không diễn tả toàn bộ quyền trên object. Domain authorization có thể xét roles, attributes, tenant và owner.

### 14.3. Authorities của Portal không đi theo HTTP request

Portal có Authentication trong session. API tạo Authentication từ Bearer access token riêng. Không tự serialize Portal authorities rồi tin chúng ở API mà không có một contract bảo mật được thiết kế.

## 15. `client_credentials`: service identity, không phải End-User

Background job dùng client credentials để gọi Reporting API.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting:
            provider: company-as
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-as:
            token-uri: https://id.company.example/oauth2/token
~~~

Token nhận được đại diện cho **OAuth client/service**. Không bắt buộc tồn tại OIDC user hoặc ID token.

### 15.1. `sub` không nhất thiết là human user

Ở client credentials, một số AS đặt client identity vào `sub` hoặc `client_id`. API phải hiểu token profile, không tự coi mọi `sub` là người dùng.

### 15.2. Không dùng service token để vượt quyền user

Nếu Portal dùng service token quyền rộng để gọi API thay Alice, nhưng bỏ kiểm tra Alice có được truy cập object không, có thể xảy ra confused deputy/privilege escalation.

### 15.3. User-delegated vs service-level actions

| Ngữ cảnh | Cần kiểm tra gì? |
|---|---|
| Alice xem đơn hàng | User identity, scope, tenant, owner |
| Job thống kê định kỳ | Service identity, allowed tenant/data scope, service policy |
| Admin tác vụ thay user | Delegation, audit, least privilege, domain policy |

Không tráo đổi token của ba ngữ cảnh này.

## 16. Token Relay, Token Exchange và Client Credentials

Ba pattern khác nhau:

### 16.1. Token Relay

Gateway/BFF chuyển tiếp access token nhận được đến API đích **nếu token được phép sử dụng tại API đó**.

Không relay token có `aud=gateway` sang Orders API chỉ vì gateway đã xác thực nó.

### 16.2. Token Exchange

Client dùng một subject token để xin token mới tại AS, có thể dành riêng cho downstream API/actor theo policy.

Token Exchange cần AS hỗ trợ và cho phép client/subject. Không tự đổi token để có quyền rộng hơn.

### 16.3. Client Credentials

Client xin service token bằng danh tính của chính nó. Token này không phải delegated identity của Alice.

### 16.4. So sánh

| Pattern | Token gửi API | User context |
|---|---|---|
| Token Relay | Token hiện có đã được cấp đúng API | Phụ thuộc token |
| Token Exchange | Token mới từ AS dành downstream | Theo subject/actor semantics |
| Client Credentials | Service access token | Không tự có End-User |

## 17. SPA gọi API trực tiếp

Một Single Page Application có thể dùng Authorization Code + PKCE để lấy access token rồi gọi API trực tiếp từ browser.

~~~mermaid
flowchart LR
    SPA["Browser SPA"] -->|"Authorization Code + PKCE"| OP["OP / AS"]
    SPA -->|"Bearer access token"| API["Orders API"]
    API --> DB["Orders database"]
~~~

### 17.1. SPA là public client

JavaScript chạy trong browser không giữ được client secret như confidential backend. Không hardcode OAuth client secret trong frontend bundle.

### 17.2. Token trong browser cần threat model riêng

Cần đánh giá XSS, CSP, token storage, lifetime, refresh token rotation, cross-tab behavior và logout.

Không khẳng định localStorage hay sessionStorage là nơi an toàn tuyệt đối cho Bearer tokens.

### 17.3. PKCE không thay API validation

PKCE bảo vệ Authorization Code flow. Resource Server vẫn phải kiểm tra Bearer token, audience, scope và owner.

### 17.4. CORS không phải authentication

CORS điều khiển browser có được đọc cross-origin response hay không. Nó không xác minh JWT, không cấp quyền user và không chặn các non-browser clients gửi HTTP requests.

## 18. Ba DSL Spring Security khác nhiệm vụ

~~~java
http.oauth2Login(...);
http.oauth2Client(...);
http.oauth2ResourceServer(...);
~~~

### 18.1. `oauth2Login()`

- Browser redirect đến AS/OP.
- Callback, state, code exchange.
- OIDC ID token validation.
- Tạo local Authentication/session.

Không thay Resource Server authorization.

### 18.2. `oauth2Client()`

- Authorized clients và token management.
- Provider chain cho các grants.
- Dùng access token để gọi outbound APIs.
- Refresh/reauthorize khi phù hợp.

Không quyết định Alice có được xem order 123.

### 18.3. `oauth2ResourceServer()`

- Xác thực incoming Bearer token của API.
- JWT hoặc opaque token verification.
- Tạo Authentication trong API.
- Kết hợp authorization rules.

Không tự thực hiện browser login hoặc giữ refresh token của client.

### 18.4. Cùng ứng dụng có thể dùng cả ba?

Có, nhưng nên xác định rõ security boundary. Một monolith có cả web UI và bearer API thường cần các filter chains riêng hoặc cấu hình matcher rõ ràng.

## 19. Tách browser chain và bearer API chain

Ví dụ kiến trúc Servlet ứng dụng kết hợp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HybridSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        return http
                .securityMatcher("/api/**")
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

### 19.1. Phạm vi của ví dụ

`apiChain` giả định API chỉ nhận Bearer token, không dùng cookie làm authentication. Trong production cần thêm rules scope/method/owner, error handling, actuator/CORS và kiểm tra thứ tự matcher.

### 19.2. Không để API bị redirect đến OP

Một bearer-only API thường nên trả 401/403 JSON/API response, không redirect browser tới OP login page khi token thiếu.

### 19.3. Đừng tự tin mọi path đều đi đúng chain

Integration test phải xác nhận `/api/**` không chấp nhận session cookie một cách ngoài ý muốn và browser pages vẫn dùng CSRF protection.

## 20. 401 khác 403

### 20.1. 401 Unauthorized

Thường là request chưa có **credential hợp lệ** cho protected API:

- Không có Bearer token.
- Token expired.
- Signature/issuer/audience sai.
- Opaque token inactive.
- Token format không được API hỗ trợ.

### 20.2. 403 Forbidden

Thường là request đã được nhận diện nhưng **thiếu quyền**:

- Không có scope `orders.write`.
- Alice không phải owner.
- User không thuộc tenant.
- Service client không được phép hành động.
- Business rule từ chối.

### 20.3. Không refresh vô hạn

Nếu API trả 401, cần xác định nguyên nhân. Refresh có thể giúp khi access token expired và refresh token còn hợp lệ, nhưng không sửa sai issuer/audience.

403 cũng không mặc định biến mất sau refresh vì scope/owner thường không thay đổi.

### 20.4. Retry có side effect

Với POST thanh toán hoặc tạo đơn hàng, một request timeout có thể đã được xử lý. Không tự retry vô hạn sau refresh mà không có idempotency policy.

## 21. Token lifetime, session và logout

Các vòng đời:

~~~text
Portal session:
  SecurityContext / Authentication của Alice

Access token:
  Expiry và revocation policy riêng

Refresh token:
  Expiry, rotation, invalid_grant policy riêng

OP SSO session:
  Policy của OpenID Provider
~~~

### 21.1. Session còn, access token hết hạn

Alice vẫn đăng nhập Portal nhưng A1 hết hạn. OAuth client có thể refresh A1 bằng R1 nếu được cấp.

### 21.2. Refresh không đồng nghĩa reauthentication

Refresh token grant không tự chứng minh user vừa nhập mật khẩu/MFA. Nếu cần step-up, dùng OIDC authentication request/policy và kiểm tra các claims liên quan.

### 21.3. Logout local khác revocation

Portal logout có thể xóa session; access token còn hạn vẫn có thể tồn tại ở AS/Resource Server theo policy. Nếu authorized client nằm trong service store ngoài session, local logout có thể không xóa record đó.

### 21.4. OP SSO logout

RP-Initiated Logout phụ thuộc OP hỗ trợ. Logout tại Portal không tự kết thúc mọi OP SSO sessions.

## 22. Bảo vệ token và outbound integrations

### 22.1. Không log token

Tránh log:

~~~text
Authorization: Bearer ...
access_token
refresh_token
id_token
authorization_code
code_verifier
client_secret
session_cookie
serialized authorized client
~~~

Log các metadata an toàn theo policy:

~~~text
registrationId=corporate
resource=orders
result=DENIED
reason=INSUFFICIENT_SCOPE
correlationId=...
~~~

### 22.2. HTTPS và token destinations

Dùng HTTPS cho token endpoints, API và các kết nối nhạy cảm. Không gửi token trong URL query vì URL có thể xuất hiện trong history/logs.

### 22.3. Không để URL động mang Bearer token

RestClient/WebClient gắn token cần gọi đúng Resource Server host. Giới hạn redirects và không forward Authorization header tới host lạ.

### 22.4. Secret đúng loại client

Backend confidential clients có thể dùng client secret, mTLS hoặc private_key_jwt theo AS. Browser public clients không được bảo vệ bởi secret hardcoded trong JavaScript.

### 22.5. Rotation và concurrency

Nếu AS rotate refresh token R1 → R2, hai requests cùng dùng R1 có thể gây `invalid_grant` hoặc reuse detection. Storage/manager cần concurrency strategy và không ghi R1 cũ đè R2.

## 23. Multi-tenant API protection

Một user được OIDC xác thực có thể có membership khác nhau ở mỗi tenant.

~~~text
Alice:
  Acme -> ORDER_ADMIN
  Globex -> ORDER_VIEWER
~~~

Orders API phải kiểm tra tenant và owner của từng resource.

### 23.1. Issuer + subject

OIDC `sub` chỉ unique trong issuer. Nếu hệ thống có nhiều OP, dùng identity mapping dựa `iss` + `sub` hoặc local user ID đáng tin cậy.

### 23.2. Tenant claim không tự là tenant nội bộ

Claim `tid` có thể thuộc định nghĩa riêng của OP. Không tự tin nó khớp tenant ID của SaaS nếu chưa xác minh mapping và semantics.

### 23.3. Service token trong đa tenant

Service token có thể có quyền rộng. API cần kiểm soát service được thao tác với tenant nào; không coi client_credentials là giấy phép đọc dữ liệu tất cả tenants.

### 23.4. Cache/database cũng phải tenant-aware

Một cache key chỉ theo user hoặc order ID có thể trả dữ liệu sai tenant. Dùng tenant-aware query/cache keys và kiểm tra object ownership.

## 24. API Gateway và forwarded identity

Gateway có thể xác minh access token ở edge rồi chuyển request tới internal API.

### 24.1. Backend vẫn cần trust boundary

Câu hỏi cần trả lời:

- Backend có tự verify token không?
- Chỉ gateway được phép gọi backend qua mTLS/private network?
- Gateway có strip/replace caller-supplied identity headers?
- Backend kiểm tra tenant/resource ownership ở đâu?

### 24.2. Không tin `X-User-Id` từ Internet

Nếu Orders API tin header:

~~~http
X-User-Id: admin
~~~

mà attacker có thể tự gửi header đó, đây là bypass authentication. Forwarded identity phải đến từ một trust contract bảo vệ tốt, không từ untrusted client.

### 24.3. Gateway ít khi biết quyền từng order

Ngay cả khi gateway kiểm tra `orders.read`, domain service vẫn cần xác minh order/tenant/owner.

## 25. Reactive/WebFlux

Ba trách nhiệm vẫn tồn tại trong Reactive stack.

| Servlet | WebFlux |
|---|---|
| `HttpSecurity.oauth2Login()` | `ServerHttpSecurity.oauth2Login()` |
| `HttpSecurity.oauth2Client()` | `ServerHttpSecurity.oauth2Client()` |
| `HttpSecurity.oauth2ResourceServer()` | `ServerHttpSecurity.oauth2ResourceServer()` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `HttpSession` | `WebSession` |
| `SecurityContextHolder` thường ThreadLocal | `ReactiveSecurityContextHolder` / Reactor Context |

### 25.1. Reactive API chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveOrdersApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Ví dụ API chỉ nhận Bearer token; không copy CSRF disable sang ứng dụng dùng browser cookie.

### 25.2. Reactive manager trả Mono

~~~java
Mono<OAuth2AuthorizedClient> result =
        reactiveAuthorizedClientManager.authorize(request);
~~~

Phải compose bằng `flatMap`/`map`, không dùng `block()` hoặc `subscribe()` tùy tiện trong request path.

### 25.3. Không dùng Servlet principal ThreadLocal cho Reactor

Trong WebFlux, Authentication có thể được truy cập qua `ReactiveSecurityContextHolder`. Không mặc định ThreadLocal context truyền đúng qua mọi reactive operator/scheduler.

### 25.4. API authorization vẫn tách domain

Reactive Resource Server vẫn cần issuer/audience/scope validation và tenant-aware ownership checks như Servlet.

## 26. Kiểm thử từng lớp độc lập

### 26.1. OIDC authentication tests

- OIDC authorization redirect/callback đúng.
- State không khớp → reject.
- ID token signature/issuer/audience sai → reject.
- Nonce/PKCE theo policy.
- `OidcUser` issuer/subject đúng.
- Protected Portal page chưa login → login challenge/redirect.

### 26.2. OAuth Client tests

- Registration ID/grant/scopes đúng.
- Authorized client có access token đúng Resource Server.
- Token còn hạn có thể được dùng lại.
- Refresh khi cần và R1 hợp lệ.
- `invalid_grant` được xử lý theo failure policy.
- `client_credentials` không giả làm user.
- Không gửi token sai host/redirect.
- Không dùng ID token thay access token.

### 26.3. Resource Server tests

| Token/request | Kết quả mong muốn |
|---|---|
| Không có Bearer token | 401 cho protected endpoint |
| JWT signature sai | 401 |
| JWT issuer sai | 401 |
| JWT expired | 401 |
| JWT audience là `billing-api` | 401 tại Orders API |
| Token đúng nhưng thiếu scope | 403 |
| Token đúng và scope đủ, order của Alice | 200 nếu policy cho phép |
| Token đúng và scope đủ, order của Bob | 403 hoặc 404 theo API policy |
| Token đúng, tenant khác | 403 hoặc 404 |
| Service token vào user-only endpoint | Reject |
| ID token của Portal dùng làm Bearer | Reject |

### 26.4. CSRF tests cho BFF

Với Portal dùng cookie-based session, cần kiểm tra các POST/PUT/DELETE state-changing requests yêu cầu CSRF protection phù hợp.

### 26.5. Integration test AS/API

Dùng mock OP/AS hoặc test environment. Không gửi token production vào unit tests/logs và không vô hiệu các validation để test dễ qua.

## 27. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Portal login được, API 401 | Token sai issuer/audience/expiry | Access token/API validators |
| Portal login được, API 403 | Thiếu scope hoặc quyền object | API rules/domain authorization |
| Portal gửi ID token làm Bearer | Nhầm token authentication/API | OidcUser vs AuthorizedClient |
| API trả HTML login page | API dùng browser login chain | SecurityFilterChain matcher |
| CORS error | Origin/preflight config | CORS, không nhầm token verification |
| API nhận JWT Billing | Thiếu audience validation | JwtDecoder validators |
| `SCOPE_orders.read` thiếu | Claim converter không khớp | JWT scope/scp mapping |
| Service token không có user ID | Client Credentials semantics | Service authorization |
| Refresh không hoạt động | Không có R1 hoặc invalid_grant | OAuth client provider/store |
| Logout nhưng token vẫn API-call được | Local logout khác revocation | AS/RS policy |
| Browser POST bị CSRF | Session cookie không được bảo vệ | CSRF policy |
| Token xuất hiện trong logs | Logging/interceptor quá rộng | Redaction và incident response |
| API chỉ check token, không owner | BOLA/IDOR | Domain-level checks |
| Tenant A thấy dữ liệu B | Cache/repository thiếu tenant | Tenant isolation |
| Gateway identity header bị giả | Untrusted forwarded headers | Gateway trust contract |

## 28. Những nhầm lẫn phổ biến

**“OIDC Login thành công nghĩa là user được phép gọi mọi API.”**

Không. Portal authentication khác API authorization; access token phải phù hợp API và resource.

**“ID token cũng là JWT, nên dùng làm Bearer token được.”**

Không. Nó có semantics/audience của OIDC Relying Party.

**“`oauth2Login()` tự bảo vệ mọi Bearer API.”**

Không. Resource Server cần configuration và authorization rules của mình.

**“`oauth2ResourceServer()` tự mở browser login.”**

Không. Nó xác minh incoming Bearer tokens.

**“`oauth2Client()` kiểm tra owner của order.”**

Không. Nó giúp client lấy/quản lý/dùng token.

**“JWT signature hợp lệ tức là được phép.”**

Không. Cần issuer, audience, lifetime, scope và domain authorization.

**“Scope `orders.read` đủ đọc tất cả orders.”**

Không. Cần owner/tenant checks.

**“Client Credentials luôn có người dùng đăng nhập.”**

Không. Thường đại diện service/client.

**“CORS bảo vệ API khỏi mọi caller khác origin.”**

Không. CORS là browser response-read policy, không thay authentication.

**“Session của Portal tự dùng được ở Orders API.”**

Không mặc định. Orders API có credential/trust boundary riêng.

**“Refresh token thành công đồng nghĩa user vừa MFA.”**

Không.

**“Logout Portal đồng nghĩa access token đã bị AS revoke.”**

Không.

## 29. Tình huống thực hành

### A. Portal login đúng, Orders API trả 401

Portal gửi ID token `aud=employee-portal` thay vì access token dành cho Orders API.

**Xử lý:** dùng access token từ OAuth2AuthorizedClient với audience/scope phù hợp; API kiểm tra token.

### B. Token hợp lệ nhưng API trả 403

Alice có `orders.read` nhưng gọi order của Bob.

**Xử lý:** domain authorization từ chối vì owner/tenant. Refresh không tự giải quyết.

### C. Job không có End-User

Job báo cáo chạy mỗi giờ.

**Xử lý:** client_credentials, service identity và service authorization; không tạo OidcUser giả.

### D. API trả redirect login page

Mobile API client thiếu bearer nhưng nhận HTML 302.

**Xử lý:** tách bearer-only API chain, trả 401 theo API contract.

### E. Access token expired, Portal session còn sống

Portal có Authentication nhưng A1 hết hạn.

**Xử lý:** OAuth client có thể refresh R1 hợp lệ, hoặc thực hiện authorization mới khi cần. Không dùng ID token thay.

### F. Audience sai

Orders API nhận JWT ký đúng nhưng `aud=billing-api`.

**Xử lý:** thêm/giữ audience validation; từ chối.

### G. Tenant role trộn nhau

Alice admin Acme và viewer Globex.

**Xử lý:** roles và resource checks theo active tenant, không tái dùng admin role của Acme tại Globex.

### H. BFF tắt CSRF vì “đã dùng OAuth2”

Browser dùng cookie Portal cho POST.

**Xử lý:** giữ CSRF protection vì cookie là ambient credential.

### I. Gateway đã verify token nhưng backend tin header bất kỳ

Backend nhận `X-User-Id` từ Internet.

**Xử lý:** bảo vệ gateway/backend trust boundary, strip/replace headers và kiểm tra quyền domain.

### J. Service token quyền rộng dùng thay Alice

Portal dùng token service để lấy mọi order không kiểm tra user.

**Xử lý:** áp user delegation/least privilege/object authorization và audit phù hợp.

## 30. Câu hỏi tự kiểm tra

**1. OIDC user authentication trả lời câu hỏi gì?**

Ai được OP xác thực và đang đăng nhập vào RP.

**2. OAuth2 Client Authorization trả lời câu hỏi gì?**

Client được AS cấp access token cho phạm vi và Resource Server nào.

**3. Resource Server trả lời câu hỏi gì?**

Incoming request có credential hợp lệ và đủ quyền trên resource không.

**4. ID token có nên gửi làm Bearer access token tới API không?**

Không theo mô hình OAuth2 Resource Server thông thường.

**5. Session cookie Portal có tự xác thực tại Orders API không?**

Không nếu API không có cơ chế session trust riêng được thiết kế.

**6. `OAuth2AuthorizedClient` là gì?**

Trạng thái OAuth access/refresh token gắn với ClientRegistration và principal.

**7. `oauth2Login()` dùng làm gì?**

Xử lý browser OAuth2/OIDC Login và tạo local Authentication.

**8. `oauth2Client()` dùng làm gì?**

Hỗ trợ authorize/manage/use access tokens trong outbound calls.

**9. `oauth2ResourceServer()` dùng làm gì?**

Xác thực Bearer token vào API.

**10. JWT signature hợp lệ có đủ quyền không?**

Không. Cần issuer, audience, lifetime, scope và owner/tenant authorization.

**11. `SCOPE_orders.read` cho xem mọi order?**

Không.

**12. Client Credentials có End-User login không?**

Không bắt buộc, thông thường không có.

**13. Token Relay và Token Exchange giống nhau không?**

Không. Relay chuyển token hợp lệ hiện có; Exchange xin token mới tại AS.

**14. CORS thay JWT validation được không?**

Không.

**15. Bearer-only API và cookie-based Portal có CSRF threat model giống nhau không?**

Không. Cookie-based browser session cần CSRF protection; API chỉ Bearer header có thể khác.

**16. Refresh token chứng minh MFA vừa xảy ra không?**

Không.

**17. 401 và 403 khác nhau thế nào?**

401 thường thiếu credential hợp lệ, 403 thường thiếu quyền.

**18. Logout Portal có tự revoke access token tại AS không?**

Không.

**19. Vì sao phải kiểm tra audience?**

Để API không nhận token phát cho API/client khác.

**20. Vì sao có scope vẫn cần tenant/owner check?**

Scope chưa mô tả quyền trên từng object.

## Ghi nhớ

- **OIDC xác thực người dùng**, **OAuth2 Client quản lý quyền dùng access token**, **Resource Server xác minh token và áp quyền API**. Ba trách nhiệm liên quan nhưng không thể thay thế nhau.
- **ID token thuộc OIDC Relying Party, access token thuộc Resource Server, refresh token thuộc AS token endpoint**. Không tráo đổi token.
- **`oauth2Login()`, `oauth2Client()` và `oauth2ResourceServer()` phục vụ các nhu cầu khác nhau** trong Spring Security.
- **API phải kiểm tra issuer, audience, expiry, scopes và domain permissions**; signature JWT đúng không đủ để được truy cập mọi object.
- **Client Credentials là service identity**, không mặc định có user. Không dùng service token quyền rộng để bypass quyền của End-User.
- **Scope không thay ownership/tenant checks**; Resource Server và business layer phải áp authorization cho tài nguyên cụ thể.
- **Session cookie và Bearer token có trust/CSRF/error semantics khác nhau**. Tách web UI và bearer API boundaries khi cần.
- **Token Relay, Token Exchange, refresh và logout là các cơ chế riêng**; không tự tăng quyền hoặc coi refresh là reauthentication.
- **Không log tokens, không gửi Bearer token đến host tùy ý**; dùng HTTPS, dedicated HTTP client, destination allowlist và kiểm thử âm tính.
