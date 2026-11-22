# Bật OIDC và xử lý scope openid

> **Chương: OIDC Core và ID Token.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Bài học tập trung vào cách bật OpenID Connect 1.0 (OIDC), ý nghĩa của scope bắt buộc `openid`, đăng ký scope cho client, phát hành ID Token và kiểm tra luồng OIDC Authorization Code.

## 1. OAuth 2.0 và OpenID Connect giải quyết hai bài toán khác nhau

OAuth 2.0 là framework ủy quyền. Nó cho phép client nhận access token để truy cập resource theo phạm vi đã được cấp. OAuth 2.0 tự nó không định nghĩa đầy đủ giao thức chuẩn để client xác minh danh tính người dùng đã đăng nhập.

OpenID Connect 1.0 (OIDC) xây dựng trên OAuth 2.0 và bổ sung lớp xác thực người dùng. Khi client gửi OIDC Authentication Request hợp lệ, OpenID Provider (OP, thường cũng là OAuth Authorization Server) có thể phát hành **ID Token** — JWT được ký bởi OP, chứa subject và thông tin về kết quả xác thực.

| Khía cạnh | OAuth 2.0 | OpenID Connect |
|---|---|---|
| Mục tiêu | Client được phép truy cập tài nguyên nào? | Người dùng đã xác thực là ai và kết quả đăng nhập là gì? |
| Token đặc trưng | Access token | ID Token, thường đi cùng access token |
| Audience điển hình | Resource Server/API | Client / Relying Party (RP) |
| Phạm vi | Scope và authorization cho API | Authentication và claims theo OIDC |
| Giao thức bổ sung | Authorization, token, introspection, revocation… | Provider Configuration/Discovery, UserInfo, Logout… |
| Dấu hiệu nhận biết request | OAuth authorization parameters | Scope bắt buộc `openid` trong Authentication Request |

Ví dụ xuyên suốt:

- **OpenID Provider / Authorization Server:** `https://login.example.vn`.
- **Relying Party / OAuth client:** `portal-web`.
- **End user:** `user-123`.
- **Resource Server:** `https://api.example.vn`.
- **API permission:** `orders.read`.
- **OIDC scopes:** `openid profile email`.

Khi người dùng đăng nhập vào `portal-web`, client cần xác minh kết quả xác thực và nhận định danh ổn định của user. Khi gọi Orders API, client cần access token có quyền `orders.read`. Hai mục tiêu có thể nằm trong cùng Authorization Code Flow nhưng **ID Token và access token có contract, audience và người tiêu thụ khác nhau**.

### 1.1. Phân biệt các vai trò

- **OpenID Provider (OP):** máy chủ thực hiện OIDC authentication, phát hành ID Token và cung cấp discovery/UserInfo theo cấu hình.
- **Relying Party (RP):** ứng dụng OIDC dựa vào OP để xác thực người dùng.
- **OAuth Client:** ứng dụng yêu cầu authorization và token. Một RP cũng là OAuth client.
- **Resource Server:** API nhận access token và thực thi authorization. Resource Server không dùng ID Token thay access token.

Spring Authorization Server có thể đóng vai trò OAuth Authorization Server và OpenID Provider khi ứng dụng bật OIDC và cấu hình đủ các thành phần liên quan.

## 2. Bật OIDC trong Spring Authorization Server

Spring Authorization Server hỗ trợ các OAuth 2.0 endpoints theo cấu hình của Authorization Server. **OpenID Connect 1.0 bị tắt mặc định**. Để bật OIDC, cần cấu hình OIDC configurer trong Authorization Server filter chain:

~~~java
.oidc(Customizer.withDefaults())
~~~

Trong Spring Authorization Server 1.5.x, việc bật OIDC thêm các protocol endpoints sau:

| Endpoint | Đường dẫn mặc định | Mục đích |
|---|---|---|
| Provider Configuration | `/.well-known/openid-configuration` | Công bố metadata để RP discovery |
| UserInfo | `/userinfo` | Trả claims về end user theo access token và policy |
| Logout | `/connect/logout` | Xử lý OIDC logout request |
| Client Registration | `/connect/register` | Dynamic Client Registration; disabled mặc định |

Các endpoint OAuth như authorization, token, introspection, revocation và JWK Set vẫn hoạt động theo cấu hình Authorization Server. OIDC bổ sung protocol endpoints; nó không thay thế token endpoint hay biến access token thành ID Token.

### 2.1. SecurityFilterChain bật OIDC

Ví dụ cấu hình với Spring Authorization Server 1.5.x và Spring Security 6.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                    exceptions.defaultAuthenticationEntryPointFor(
                            new LoginUrlAuthenticationEntryPoint("/login"),
                            new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http.authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ý nghĩa cấu hình:

- `OAuth2AuthorizationServerConfigurer.authorizationServer()` tạo configurer cho tập endpoint của AS.
- `securityMatcher(authorizationServer.getEndpointsMatcher())` giới hạn chain thứ nhất vào các endpoint AS, bao gồm OIDC endpoints sau khi bật.
- `oidc(Customizer.withDefaults())` khởi tạo OIDC support.
- `@Order(1)` để chain Authorization Server được xét trước chain ứng dụng.
- Entry point chuyển browser request cần user authentication tới `/login`. Request protocol không phải HTML được xử lý theo error flow thích hợp.
- Chain thứ hai cung cấp form login minh họa; production có thể dùng cơ chế xác thực người dùng khác.

Đây là filter-chain skeleton, chưa phải toàn bộ hệ thống production. Ứng dụng còn cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, `AuthorizationServerSettings`, token generator, signing keys và user authentication mechanism.

### 2.2. Bật OIDC không tự xác thực người dùng

OIDC configurer bổ sung giao thức và endpoint. Nó không tự tạo user database, password login, MFA, session hay quy trình consent. Authorization Code Flow vẫn cần xác thực resource owner qua form login, identity provider hoặc cơ chế đã tích hợp.

Consent cũng là một chính sách riêng. Nếu client yêu cầu `profile`, `email` hoặc API scopes, giao diện consent và policy phải thể hiện rõ quyền nào user đang cấp. Bật OIDC không đồng nghĩa tự động đồng ý mọi scope.

## 3. Scope openid là dấu hiệu bắt buộc của OIDC Authentication Request

Theo OpenID Connect Core 1.0, một OIDC Authentication Request **MUST** chứa scope value `openid`. Sự hiện diện của scope này đánh dấu request là OIDC Authentication Request. Nếu không có `openid`, request được xử lý như OAuth 2.0 Authorization Request, kể cả khi AS đã bật OIDC.

Ví dụ Authorization Code Request:

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20profile%20email%20orders.read&state=STATE_RANDOM&nonce=NONCE_RANDOM&code_challenge=PKCE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.vn
~~~

Các tham số quan trọng:

- `openid`: yêu cầu giao thức OIDC và kết quả xác thực bằng ID Token.
- `profile` và `email`: yêu cầu các nhóm claims OIDC tương ứng, tùy dữ liệu, consent và policy.
- `orders.read`: scope OAuth tùy chỉnh cho Orders API.
- `state`: liên kết response với authorization transaction do client khởi tạo.
- `nonce`: nếu client gửi, giá trị tương ứng phải được trả trong ID Token và được RP kiểm tra.
- `code_challenge` và `code_challenge_method=S256`: PKCE bảo vệ Authorization Code.

### 3.1. openid không phải role hoặc API permission

Không diễn giải `openid` như quyền đọc mọi thông tin user hoặc quyền gọi mọi API. Nó đánh dấu request sử dụng OIDC. Các scope `profile`, `email`, `address` và `phone` yêu cầu các nhóm claims tương ứng. API permission vẫn do scope riêng như `orders.read`, audience và authorization policy quyết định.

Ví dụ, client có thể được cấp `orders.read` nhưng không được cấp `email`. Ngược lại, client được cấp `profile` không tự động được phép đọc đơn hàng.

### 3.2. Scope đăng ký và scope được yêu cầu là hai bước

1. **Client registration:** AS khai báo các scope client được phép yêu cầu qua `RegisteredClient.getScopes()`.
2. **Authorization Request:** client gửi tập scope cụ thể trong tham số `scope`; AS kiểm tra từng scope có được registration và policy cho phép hay không.

Đăng ký `openid` trong RegisteredClient **không có nghĩa mọi request của client đều là OIDC**. Request thực tế phải chứa `openid`. Ngược lại, client gửi `openid` nhưng registration không cho phép thì AS phải từ chối theo validation, không tự mở rộng quyền.

## 4. Các OIDC scopes thường gặp

OIDC Core định nghĩa các scope chuẩn yêu cầu nhóm claims. Những scope thường dùng:

| Scope | Nhóm thông tin được yêu cầu | Ví dụ claims |
|---|---|---|
| `openid` | Đánh dấu OIDC Authentication Request | `sub` trong ID Token |
| `profile` | Hồ sơ cơ bản | `name`, `given_name`, `family_name`, `preferred_username`, `picture`, `locale` |
| `email` | Thông tin email | `email`, `email_verified` |
| `address` | Địa chỉ bưu chính | `address` |
| `phone` | Số điện thoại | `phone_number`, `phone_number_verified` |
| `offline_access` | Yêu cầu khả năng nhận refresh token khi thỏa điều kiện OIDC | Không phải user profile claim |

Scope yêu cầu không bảo đảm claim chắc chắn có giá trị. OP chỉ trả thuộc tính có dữ liệu và được policy/consent cho phép. Ví dụ user chưa khai `phone_number` thì scope `phone` không thể tự tạo số điện thoại.

### 4.1. API scopes tùy chỉnh

Ứng dụng có thể định nghĩa scope OAuth như:

- `orders.read` — đọc đơn hàng.
- `orders.write` — tạo/cập nhật đơn hàng.
- `billing.read` — đọc hóa đơn.

Đây không phải scope chuẩn OIDC. Chúng dành cho Resource Server authorization. Không dùng `openid` thay API permission hoặc đặt thông tin nghiệp vụ vào `profile`.

### 4.2. Requested scope không chắc chắn là granted scope

AS kiểm tra client registration, user consent, authorization và policy. Client phải dựa trên scope thực tế được cấp trong authorization/token context, không tự giả định tất cả scope đã gửi đều được chấp nhận.

Nếu user từ chối một số quyền hoặc policy giới hạn scope, client phải xử lý kết quả và không gọi API bằng quyền chưa được cấp.

## 5. Đăng ký OIDC client trong Spring Authorization Server

Spring Authorization Server dùng `RegisteredClient` để lưu client ID, authentication method, grant type, redirect URI, scope và client settings.

Ví dụ confidential web client:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

RegisteredClient portalWeb = RegisteredClient
        .withId("registration-portal-web")
        .clientId("portal-web")
        .clientSecret(encodedClientSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri(
                "https://portal.example.vn/login/oauth2/code/portal")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope(OidcScopes.EMAIL)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .requireProofKey(true)
                .build())
        .build();
~~~

Lưu ý:

- `OidcScopes.OPENID` là hằng số cho scope `openid`; `PROFILE` và `EMAIL` là scope OIDC chuẩn.
- `encodedClientSecret` phải được hash bằng PasswordEncoder phù hợp; không lưu secret bản rõ trong source code.
- `requireProofKey(true)` yêu cầu PKCE cho Authorization Code Flow.
- `requireAuthorizationConsent(true)` yêu cầu consent theo client settings; consent page cần hiển thị scope dễ hiểu.
- Redirect URI phải khớp chính xác registration và dùng HTTPS trong production.
- Public client phải dùng authentication method phù hợp, thường `none`, và PKCE; không nhúng client secret vào SPA.

### 5.1. Không dùng Client Credentials để đăng nhập end user

Client Credentials đại diện cho chính ứng dụng/service, không phải người dùng đã đăng nhập. Nếu mục tiêu là service-to-service, dùng scope API như `orders.read` và access token theo OAuth. Không dùng Client Credentials để giả lập user login hoặc kỳ vọng có ID Token mang danh tính end user.

### 5.2. Lưu client registration

Lưu RegisteredClient qua `RegisteredClientRepository`. In-memory repository phù hợp demo/local; production thường cần persistence như JDBC. Các scope ở registration là allowlist. Khi cập nhật scope, cần xem xét consent cũ, token đã phát và policy migration; thay registration không tự thay claims trong JWT đang còn hiệu lực.

## 6. Issuer, JWK và JwtDecoder

OIDC ID Token là JWT được ký bằng JWS. RP cần xác minh chữ ký bằng public key của đúng OP, thường lấy từ JWK Set được công bố trong discovery metadata.

### 6.1. Cấu hình issuer ổn định

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://login.example.vn")
            .build();
}
~~~

Issuer phải thống nhất giữa Provider Configuration, claim `iss` trong ID Token, OAuth AS metadata và cấu hình RP. Production cần issuer HTTPS ổn định, phản ánh URL public sau reverse proxy. Không để issuer thay đổi theo hostname nội bộ hoặc header do caller không tin cậy cung cấp.

### 6.2. JWKSource và signing key

AS cần signing key để ký ID Token. Khi ứng dụng đăng ký bean `JWKSource<SecurityContext>`, Spring Authorization Server có thể công bố JWK Set endpoint để RP lấy public key.

Ví dụ cấu trúc JWKSource (việc nạp key là trách nhiệm ứng dụng):

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

@Bean
JWKSource<SecurityContext> jwkSource() {
    RSAKey signingKey = loadSigningKeyFromSecureStorage();
    JWKSet jwkSet = new JWKSet(signingKey);
    return (selector, context) -> selector.select(jwkSet);
}
~~~

`loadSigningKeyFromSecureStorage()` là hàm minh họa do ứng dụng triển khai, không phải API có sẵn. JWK Set công bố public key; private signing key phải được bảo vệ trong keystore/HSM/secret management. Không tạo key mới ngẫu nhiên ở mỗi lần khởi động production; cần kế hoạch key rollover và giữ public key cũ đủ lâu để validate token đã phát.

### 6.3. JwtDecoder cho UserInfo

Spring Authorization Server cần `JwtDecoder` bean để xử lý UserInfo endpoint và một số OIDC endpoint như Client Registration khi endpoint này được bật. Có thể dùng helper:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Trong ví dụ trên, kiểu `JWKSource` được import từ Nimbus package `com.nimbusds.jose.jwk.source.JWKSource`. Việc đăng ký JwtDecoder không tự bật OIDC; vẫn phải cấu hình `oidc(Customizer.withDefaults())`. Ngược lại, bật OIDC mà thiếu signing key hoặc decoder cần thiết có thể khiến ID Token/UserInfo flow không hoạt động đầy đủ.

## 7. Luồng OIDC Authorization Code Flow

Với OIDC Authorization Code Flow, trình tự điển hình:

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as portal-web (Relying Party)
    participant OP as OpenID Provider / AS
    participant U as End User
    participant API as Resource Server

    RP->>OP: Authorization Request (scope=openid profile orders.read)
    OP->>U: Login và consent nếu cần
    U-->>OP: Authentication thành công
    OP-->>RP: Redirect callback với code + state
    RP->>OP: POST /oauth2/token (code + client auth + PKCE verifier)
    OP-->>RP: access_token + id_token
    RP->>RP: Validate chữ ký, iss, aud, exp, nonce nếu có
    RP->>API: API request với access_token và orders.read
    API-->>RP: Resource response theo scope/policy
~~~

### 7.1. Authorization Request

RP tạo `state` ngẫu nhiên, PKCE verifier/challenge và OIDC `nonce` nếu sử dụng. Ví dụ:

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20profile%20email%20orders.read&state=STATE_RANDOM&nonce=NONCE_RANDOM&code_challenge=PKCE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.vn
~~~

OP xác minh client, redirect URI, response type, scope và policy. User được xác thực; nếu cần, consent page hiển thị scope. Trong Code Flow, OIDC `nonce` là tùy chọn; nếu request có nonce, ID Token phải chứa giá trị tương ứng và RP phải kiểm tra.

### 7.2. Authorization Response

Sau khi user authentication và consent thành công, OP trả authorization code tới redirect URI đã đăng ký:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.vn/login/oauth2/code/portal?code=AUTH_CODE_REDACTED&state=STATE_RANDOM
~~~

Trong Authorization Code Flow, authorization response front-channel chứa code (và state nếu client gửi); ID Token được trả ở token response, không phải qua redirect này.

### 7.3. Token Request và Response

Client gửi code tới token endpoint cùng PKCE verifier và client authentication theo registration:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_CREDENTIALS_REDACTED

grant_type=authorization_code&code=AUTH_CODE_REDACTED&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&code_verifier=PKCE_VERIFIER_REDACTED
~~~

Response OIDC có thể chứa access token và ID Token:

~~~json
{
  "access_token": "ACCESS_TOKEN_REDACTED",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email orders.read",
  "id_token": "SIGNED_ID_TOKEN_REDACTED"
}
~~~

JSON là minh họa. Response thực tế phụ thuộc grant, scope được cấp, token format và client policy. Không gửi ID Token trong Authorization header để gọi API; Resource Server nhận access token theo contract của API.

## 8. ID Token và các kiểm tra bắt buộc ở RP

ID Token là chứng cứ OIDC về authentication event của end user. Nó được OP ký và chứa các claims theo OIDC Core.

Ví dụ payload minh họa (đã bỏ chữ ký):

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": "portal-web",
  "iat": 1794825600,
  "exp": 1794825900,
  "nonce": "NONCE_RANDOM",
  "name": "Nguyen An",
  "email": "an@example.vn",
  "email_verified": true
}
~~~

Không phải ID Token nào cũng có `name` hoặc `email`. Các claim profile phụ thuộc scope, dữ liệu, consent và policy. Các claim nền tảng gồm issuer, subject, audience, thời điểm phát hành và hết hạn.

RP phải validate tối thiểu:

1. **Chữ ký:** xác minh JWS bằng public key tin cậy từ JWK Set của đúng issuer và thuật toán được chấp nhận.
2. **Issuer (`iss`):** khớp chính xác issuer đã discovery/đăng ký; không dùng substring hoặc hostname gần giống.
3. **Audience (`aud`):** chứa đúng client ID của RP. Nếu có nhiều audience, áp dụng quy tắc `azp` (authorized party); nếu `azp` hiện diện, xác minh nó khớp client phù hợp.
4. **Expiration (`exp`):** token chưa hết hạn; clock skew phải được giới hạn.
5. **Issued At (`iat`):** thời điểm phát hành hợp lý theo policy.
6. **Nonce:** nếu request gửi nonce, so khớp với nonce gắn với authorization transaction hiện tại.
7. **Authentication context:** nếu yêu cầu `max_age`, `auth_time`, `acr` hoặc `amr`, xác minh claims và policy tương ứng.
8. **Hash claims:** nếu flow/response type yêu cầu `c_hash` hoặc `at_hash`, validate theo OIDC Core.

Không chỉ Base64-decode JWT rồi tin payload. Decode không xác minh chữ ký, issuer, audience hay thời hạn.

### 8.1. Dùng (iss, sub) làm subject identity

`sub` là subject identifier do OP cấp. RP nên dùng cặp `(iss, sub)` làm định danh người dùng trong phạm vi OIDC. Không mặc định email hoặc username là định danh ổn định; email có thể đổi, trùng hoặc được tái sử dụng.

Nếu OP dùng pairwise subject identifier, cùng một user có thể có `sub` khác nhau giữa các sector/client theo policy. RP không được tự nối danh tính giữa các client bằng cách so email nếu OP không cung cấp contract đó.

## 9. Phân biệt ID Token, Access Token và UserInfo

| Thuộc tính | ID Token | Access Token | UserInfo response |
|---|---|---|---|
| Người tiêu thụ | OIDC Client / RP | Resource Server hoặc UserInfo endpoint | OIDC Client / RP |
| Mục đích | Xác minh authentication và subject | Truy cập resource theo quyền | Lấy claims user bổ sung |
| Audience | Client ID | Resource Server/resource | Được bảo vệ bằng access token |
| Định dạng | JWT ký theo OIDC | JWT hoặc opaque tùy AS | JSON claims |
| Gửi trong Authorization header gọi API | **Không** | Có, theo token type/scheme | Không |
| Claims | Authentication claims và claims được phép | Authorization/resource claims | Claims theo scope và policy |

Một ID Token hợp lệ không tự chứng minh client được quyền đọc API. Access token có scope `orders.read` không tự chứng minh mọi thông tin profile sẽ có trong ID Token. Tách đúng mục đích giúp tránh token confusion và lộ dữ liệu.

### 9.1. UserInfo endpoint

Khi cần claims bổ sung, RP gọi UserInfo endpoint bằng access token:

~~~http
GET /userinfo HTTP/1.1
Host: login.example.vn
Authorization: Bearer ACCESS_TOKEN_REDACTED
Accept: application/json
~~~

UserInfo là protected resource của OP. Spring Authorization Server mặc định xử lý Bearer access token; ứng dụng có thể tùy chỉnh UserInfo mapper/handler để quyết định claims được trả theo scope, principal, authorization và policy.

RP cần xác minh `sub` trong UserInfo response khớp `sub` trong ID Token. Nếu khác, RP không được sử dụng response như profile của cùng người dùng.

Không gửi ID Token vào UserInfo endpoint và không gửi refresh token vào API. Chỉ trả claims có dữ liệu và được phép theo scope/consent/policy.

## 10. Cấu hình Spring Security OAuth2 Client ở phía RP

Ở phía RP, scope `openid` trong ClientRegistration báo cho Spring Security rằng login sử dụng OIDC. Khi đó Spring Security dùng các thành phần OIDC như `OidcUserService`; nếu không có `openid`, luồng login được xử lý như OAuth2 Login với `DefaultOAuth2UserService`.

Ví dụ Spring Boot application YAML:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: login-server
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          login-server:
            issuer-uri: https://login.example.vn
~~~

Spring Boot dùng `issuer-uri` để discovery Provider Configuration và lấy authorization, token, JWK và UserInfo endpoints theo metadata. Client phải dùng issuer HTTPS chính xác. Trong production, secret cần được inject từ secret manager/environment, không commit giá trị thật vào YAML.

### 10.1. OIDC principal

Sau khi login thành công, Spring Security có thể cung cấp principal kiểu `OidcUser` và ID Token dưới dạng `OidcIdToken`.

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/me")
    ProfileView me(@AuthenticationPrincipal OidcUser oidcUser) {
        return new ProfileView(
                oidcUser.getSubject(),
                oidcUser.getFullName(),
                oidcUser.getEmail());
    }
}
~~~

`ProfileView` là DTO ứng dụng tự định nghĩa. Controller đọc claims từ principal đã được Spring Security xử lý; không tự decode raw ID Token để lấy email hoặc user ID.

### 10.2. Thiếu scope openid

Nếu ClientRegistration chỉ có `profile,email` mà thiếu `openid`, Spring Security không xem đây là OIDC login. Client không nên kỳ vọng `OidcUser`, ID Token hoặc OIDC-specific validation flow. Ngược lại, có `openid` ở client registration nhưng AS chưa bật OIDC cũng không tạo được OpenID Provider hoàn chỉnh.

## 11. Discovery và Provider Configuration

OIDC Discovery cho phép RP tìm endpoint và khả năng của OP từ issuer. Với issuer `https://login.example.vn`, URL thường dùng:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: login.example.vn
Accept: application/json
~~~

Metadata rút gọn minh họa:

~~~json
{
  "issuer": "https://login.example.vn",
  "authorization_endpoint": "https://login.example.vn/oauth2/authorize",
  "token_endpoint": "https://login.example.vn/oauth2/token",
  "jwks_uri": "https://login.example.vn/oauth2/jwks",
  "userinfo_endpoint": "https://login.example.vn/userinfo",
  "end_session_endpoint": "https://login.example.vn/connect/logout",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Đây là ví dụ, không phải metadata cố định của mọi deployment. Metadata runtime phải phản ánh endpoint public, issuer, subject type và thuật toán thật sự được cấu hình.

### 11.1. Discovery không phải Dynamic Client Registration

Provider Configuration công bố thông tin **của OP** để client discovery. Nó không tự đăng ký client mới. Dynamic Client Registration là endpoint riêng, disabled mặc định trong Spring Authorization Server; chỉ bật khi có use case, onboarding và policy bảo vệ phù hợp.

### 11.2. OIDC Discovery và OAuth AS Metadata

OAuth 2.0 Authorization Server Metadata (RFC 8414) và OIDC Provider Configuration có nhiều trường tương tự nhưng phục vụ protocol profiles khác nhau. RP OIDC nên dùng OIDC Discovery và xác minh issuer theo OIDC Core. Không lấy issuer từ một metadata document rồi lấy JWK/endpoint từ host khác nếu không có trust contract.

## 12. Lỗi thường gặp khi bật OIDC và xử lý openid

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Discovery endpoint trả 404 | Chưa bật `oidc(Customizer.withDefaults())` hoặc sai issuer/path | Kiểm tra AS filter chain và public route |
| Authorization request không có ID Token | Thiếu scope `openid`; request chỉ là OAuth2 | Thêm openid vào scope được registration cho phép và request |
| Request có openid nhưng bị invalid_scope | RegisteredClient chưa cho phép scope | Đăng ký `OidcScopes.OPENID` và kiểm tra đúng client ID |
| OIDC endpoint bật nhưng UserInfo lỗi | Thiếu `JwtDecoder` hoặc access token không hợp lệ | Đăng ký decoder từ JWKSource và kiểm tra token |
| Không có JWK Set endpoint | Chưa đăng ký `JWKSource<SecurityContext>` | Cấu hình public JWK Set và signing key |
| Client không nhận OidcUser | Client registration thiếu openid hoặc provider config sai | Kiểm tra scopes và issuer-uri |
| ID Token signature validation fail | JWKS/issuer/key rotation hoặc algorithm mismatch | Discovery đúng issuer, kiểm tra kid, signing algorithm và rollover |
| aud không chứa client ID | ID Token audience sai hoặc RP dùng nhầm OP | Kiểm tra ID Token, client registration và issuer |
| Nonce mismatch | Ghép response với transaction sai hoặc reuse nonce | Tạo nonce ngẫu nhiên theo transaction và so khớp chính xác |
| UserInfo sub khác ID Token sub | UserInfo mapper ánh xạ sai subject | Từ chối response, kiểm tra mapper |
| Có profile nhưng thiếu name | User store thiếu dữ liệu hoặc policy không trả claim | Kiểm tra user data, consent và mapper |
| API từ chối ID Token | RP gửi nhầm token | Gọi API bằng access token |
| Browser không được chuyển tới login | Thiếu user authentication chain/entry point | Cấu hình login mechanism và HTML entry point |
| Logout OP xong refresh token vẫn dùng được | OIDC logout không tự revoke mọi OAuth token | Thiết kế revocation/authorization cleanup riêng |

## 13. Ma trận kiểm thử OIDC Core và scope openid

| # | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| 1 | Gọi Provider Configuration sau khi bật OIDC | Metadata trả đúng issuer |
| 2 | Gọi Provider Configuration khi OIDC chưa bật | Endpoint chưa được công bố/không hoạt động như OIDC |
| 3 | Registration cho phép openid, request có openid | Được xử lý như OIDC Authentication Request |
| 4 | Registration cho phép openid, request không có openid | OAuth 2.0 request; không kỳ vọng ID Token |
| 5 | Request có openid nhưng registration không cho phép | Từ chối scope |
| 6 | Request openid profile email | Claims tương ứng chỉ trả khi có dữ liệu và policy/consent cho phép |
| 7 | Request openid orders.read | OIDC authentication và API scope được xử lý đúng mục đích |
| 8 | Client Credentials yêu cầu openid để login user | Không dùng grant này thay end-user OIDC login |
| 9 | Authorization Code Flow, user chưa login | Chuyển tới user authentication mechanism |
| 10 | Login thành công, consent hợp lệ | Authorization code trả về redirect URI đã đăng ký |
| 11 | Đổi code hợp lệ | Token response có ID Token |
| 12 | PKCE verifier sai | Token endpoint từ chối |
| 13 | ID Token chữ ký sai | RP từ chối token |
| 14 | iss sai | RP từ chối token |
| 15 | aud không chứa client ID | RP từ chối token |
| 16 | ID Token hết hạn | RP từ chối token |
| 17 | Request gửi nonce nhưng ID Token trả nonce khác | RP từ chối token |
| 18 | ID Token hợp lệ và nonce đúng | RP chấp nhận nếu các validation khác đạt |
| 19 | UserInfo với access token hợp lệ | Trả claims theo scope/policy |
| 20 | Gọi UserInfo bằng ID Token | Từ chối do sai credential type |
| 21 | UserInfo sub khác ID Token sub | RP từ chối response |
| 22 | Thiếu JwtDecoder | UserInfo endpoint không hoạt động đúng |
| 23 | Thiếu JWKSource/signing key | ID Token/JWK publication không hoạt động đúng |
| 24 | ClientRegistration thiếu openid | Spring Security dùng OAuth2-specific flow |
| 25 | ClientRegistration có openid | Spring Security dùng OIDC components như OidcUserService |
| 26 | Issuer sau reverse proxy không ổn định | Discovery/ID Token issuer mismatch |
| 27 | Logout OP | Kiểm tra session logout; test revocation riêng nếu policy yêu cầu |
| 28 | Dynamic Client Registration chưa bật | Không giả định /connect/register tồn tại |
| 29 | Signing key rotation | RP validate token mới và token cũ trong thời gian rollover |
| 30 | Consent từ chối email nhưng chấp nhận openid | Không trả email claims trái consent/policy |

### 13.1. Assertion quan trọng trong integration test

Integration test nên kiểm tra đồng thời:

- Metadata issuer đúng URL public.
- Request có `openid` mới đi vào OIDC flow.
- Registration và authorization request đều cho phép scopes được yêu cầu.
- Token endpoint trả ID Token sau khi đổi code hợp lệ.
- RP xác minh chữ ký, issuer, audience, expiry và nonce nếu có.
- UserInfo dùng access token và trả `sub` nhất quán.
- Resource Server chỉ dùng access token, kiểm tra audience/scope riêng.
- Logout và token revocation được kiểm tra như hai hành vi riêng biệt.

## 14. Checklist và câu hỏi tự đánh giá

- [ ] Bật OIDC bằng `oidc(Customizer.withDefaults())` trong AS SecurityFilterChain.
- [ ] Có user authentication mechanism cho Authorization Code Flow.
- [ ] RegisteredClient cho phép `OidcScopes.OPENID` và các scope cần thiết.
- [ ] Authorization Request thực tế chứa scope `openid`; không chỉ đăng ký scope ở client.
- [ ] Không dùng `openid` như role hoặc API permission.
- [ ] `profile`, `email`, `address`, `phone` chỉ trả theo dữ liệu, consent và policy.
- [ ] Có `JWKSource<SecurityContext>` và signing key được bảo vệ, có kế hoạch rollover.
- [ ] Có `JwtDecoder` cho OIDC UserInfo endpoint.
- [ ] Issuer ổn định và thống nhất với discovery/ID Token.
- [ ] RP sử dụng OIDC Discovery và xác minh issuer.
- [ ] RP validate ID Token signature, `iss`, `aud`, `exp`, `iat`, nonce và claims bổ sung khi cần.
- [ ] RP dùng `(iss, sub)` làm subject identity, không dựa duy nhất vào email.
- [ ] ID Token không được gửi tới Resource Server như access token.
- [ ] UserInfo được gọi bằng access token; `sub` phải khớp ID Token.
- [ ] Dynamic Client Registration chỉ bật khi có use case và policy riêng.
- [ ] Logout session và token revocation được thiết kế/kiểm thử riêng.

**Câu hỏi tự đánh giá**

1. Vì sao OAuth 2.0 Authorization Server không tự động là OpenID Provider đầy đủ?
2. `oidc(Customizer.withDefaults())` bổ sung những protocol endpoints nào?
3. Vì sao OIDC Authentication Request bắt buộc phải chứa scope `openid`?
4. Đăng ký `openid` trong RegisteredClient đã đủ để mọi request trở thành OIDC chưa?
5. Nếu request thiếu `openid`, client có thể kỳ vọng ID Token không?
6. Khác nhau giữa `openid`, `profile`, `email` và `orders.read` là gì?
7. Vì sao Client Credentials không phải flow đăng nhập end user bằng OIDC?
8. ID Token được trả ở authorization response hay token response trong Authorization Code Flow?
9. Những claim nào RP phải validate trước khi tin ID Token?
10. Vì sao `(iss, sub)` phù hợp làm subject identity hơn email?
11. UserInfo cần credential nào và vì sao `sub` phải khớp ID Token?
12. Vì sao SAS cần `JwtDecoder` khi bật UserInfo endpoint?
13. Discovery metadata khác Dynamic Client Registration như thế nào?
14. OIDC logout có tự động thu hồi mọi access token và refresh token không?

## Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Authentication using the Authorization Code Flow](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth): Authentication Request, scope `openid`, ID Token, nonce và validation.
- [OpenID Connect Core 1.0 — Standard Claims](https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims): claims profile, email, address, phone và ý nghĩa.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, issuer và discovery metadata.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): OIDC disabled mặc định, `oidc(Customizer.withDefaults())`, OIDC endpoints, JwtDecoder và AuthorizationServerSettings.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): UserInfo endpoint, Bearer access token và tùy chỉnh UserInfo response.
- [Spring Authorization Server — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): tùy chỉnh claims UserInfo.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/): cấu hình scope `openid`, OIDC login và các OIDC-specific components.
- [Spring Security — Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): xử lý ID Token và OIDC user authentication.
