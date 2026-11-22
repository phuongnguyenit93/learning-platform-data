# Bật OpenID Connect và cấu hình các endpoint OIDC

> **Chương: Cấu hình máy chủ.** Trong module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server với Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Bài này tập trung vào việc **bật OpenID Connect (OIDC)** trên Authorization Server đang hỗ trợ OAuth 2.0, hiểu các endpoint OIDC, cấu hình chúng và kiểm chứng một luồng đăng nhập từ đầu đến cuối.

## 1. Bật OIDC thay đổi điều gì?

**OAuth 2.0** chủ yếu định nghĩa cách client được cấp quyền truy cập tài nguyên; nó không tự đưa ra một giao thức chuẩn để client xác minh người dùng đã đăng nhập là ai. **OpenID Connect 1.0** xây dựng một lớp xác thực danh tính trên OAuth 2.0: request có scope `openid`, Authorization Server trở thành **OpenID Provider (OP)**, token response có thể chứa **ID Token**; client, còn gọi là **Relying Party (RP)**, phải kiểm tra ID Token theo quy tắc OIDC.

Ví dụ: ứng dụng `https://app.example.vn` muốn đăng nhập người dùng qua máy chủ `https://login.example.vn`. OAuth 2.0 Authorization Code Flow giúp ứng dụng nhận authorization code và đổi token; OIDC bổ sung cách biểu diễn thông tin xác thực bằng ID Token và các dịch vụ như discovery, UserInfo, RP-Initiated Logout.

| Thành phần | Vai trò | Ví dụ trong hệ thống |
|---|---|---|
| Authorization Server / OpenID Provider | Xác thực người dùng, xử lý consent, cấp code/token, công bố metadata và khóa công khai | `https://login.example.vn` |
| OAuth2/OIDC Client / Relying Party | Điều hướng đăng nhập, nhận authorization code, đổi token, xác minh ID Token | `https://app.example.vn` |
| Resource Server | Nhận access token, kiểm tra token và áp dụng quyền đối với API | `https://api.example.vn` |
| Issuer Identifier | Định danh OP/AS; giá trị `iss` trong ID Token phải trùng chính xác | `https://login.example.vn` |
| Redirect URI | Callback thuộc client đã được đăng ký, nơi trình duyệt quay về với code | `https://app.example.vn/login/oauth2/code/portal` |

**Phân biệt ba loại token/giá trị:**

- **ID Token:** JWT chứa thông tin xác thực và danh tính của người dùng dành cho client, gồm `iss`, `sub`, `aud`, `exp` và các claim liên quan. Không dùng ID Token để thay access token gọi API.
- **Access Token:** credential để gọi tài nguyên được bảo vệ, có thể là JWT hoặc opaque token; Resource Server phải tự xác minh và ủy quyền đúng.
- **Authorization Code:** mã dùng một lần, thời gian sống ngắn, client đổi tại token endpoint; không phải ID Token hay access token.

Bật OIDC **không** tự tạo kho người dùng, cơ chế login an toàn, RegisteredClient, signing key, consent service bền vững hoặc triển khai multi-tenant. Các thành phần đó vẫn phải được cấu hình riêng.

## 2. Bản đồ các endpoint khi OIDC được bật

Trong cấu hình mặc định của Spring Authorization Server, những đường dẫn sau có vai trò khác nhau:

| Endpoint (đường dẫn mặc định) | Phương thức chính | Chức năng | Lưu ý cấu hình |
|---|---|---|---|
| `/.well-known/openid-configuration` | GET | **OIDC Provider Configuration**: metadata issuer, endpoint, thuật toán/khả năng được công bố | Chỉ có khi bật OIDC |
| `/userinfo` | GET/POST theo giao thức/triển khai | **OIDC UserInfo**: trả claims về người dùng cho yêu cầu có access token thích hợp | Cần xác thực Bearer access token; claims thực tế phụ thuộc scope/chính sách/mapper |
| `/connect/logout` | GET/POST theo giao thức/triển khai | **RP-Initiated Logout**: RP yêu cầu kết thúc phiên tại OP | Cần xác minh `id_token_hint` và URI quay về theo chính sách |
| `/connect/register` | POST và thao tác quản lý được hỗ trợ | **Dynamic Client Registration**: đăng ký client qua API | **Tắt mặc định**; chỉ bật khi có nhu cầu và kiểm soát quyền rõ ràng |
| `/oauth2/authorize` | GET | OAuth 2.0 Authorization Endpoint; nhận `scope=openid` cho luồng OIDC | Thuộc OAuth 2.0, vẫn dùng khi bật OIDC |
| `/oauth2/token` | POST | OAuth 2.0 Token Endpoint; đổi code lấy token, có thể có `id_token` | Không phải endpoint mới riêng OIDC |
| `/oauth2/jwks` | GET | Công bố JWK Set gồm **public keys** để kiểm tra chữ ký JWT/ID Token | Đường dẫn mặc định, cần `JWKSource<SecurityContext>` |
| `/.well-known/oauth-authorization-server` | GET | OAuth 2.0 Authorization Server Metadata theo RFC 8414 | **Khác** OIDC Discovery; không thay thế toàn bộ metadata OIDC |

**Cần nhớ:** `/oauth2/authorize` và `/oauth2/token` vẫn là các endpoint OAuth 2.0 dùng chung. Một request OIDC thường dùng `scope=openid` và Authorization Code + PKCE; ID Token được phát tại token endpoint sau khi client đổi code hợp lệ.

Danh sách đường dẫn trên phản ánh **mặc định** của Spring Authorization Server 1.x. `AuthorizationServerSettings` cho phép cấu hình một số đường dẫn; luôn tra metadata do **instance đang chạy** trả về thay vì giả định các URI không thể thay đổi.

### 2.1. Những endpoint nào được bật ngay?

Với cấu hình OIDC mặc định:

- Provider Configuration, UserInfo và RP-Initiated Logout được kích hoạt trong khả năng hỗ trợ của Spring Authorization Server.
- **OIDC Dynamic Client Registration** không tự bật. Đây là endpoint quản trị nhạy cảm, cần quyết định cấp quyền và chính sách đăng ký riêng.
- OAuth2 Authorization, Token, JWK Set và OAuth AS Metadata vẫn do phần cấu hình authorization server chung cung cấp; endpoint JWKS phụ thuộc việc có nguồn JWK.
- Để UserInfo đọc Bearer access token, filter chain dành cho Authorization Server cần hỗ trợ xử lý Bearer JWT/OAuth2 Resource Server theo hướng dẫn của phiên bản đang dùng.

Không nên mở toàn bộ đường dẫn bằng `permitAll()` chỉ vì discovery là công khai. Provider Configuration và JWKS cần đọc được theo thiết kế; UserInfo yêu cầu access token hợp lệ và các endpoint còn lại phải tuân theo cơ chế xác thực/ủy quyền riêng.

## 3. Luồng đăng nhập OIDC chuẩn và vị trí từng endpoint

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as OIDC Client (RP)
    participant Browser as Trình duyệt
    participant OP as Spring Authorization Server (OP)
    participant API as Resource Server

    RP->>OP: GET /.well-known/openid-configuration
    OP-->>RP: issuer, authorization_endpoint, token_endpoint, jwks_uri, ...
    Browser->>RP: Chọn đăng nhập
    RP-->>Browser: Redirect tới /oauth2/authorize<br/>scope=openid profile, state, nonce, PKCE
    Browser->>OP: Authorization request
    OP->>Browser: Xác thực và consent nếu cần
    OP-->>Browser: 302 về redirect_uri?code=...&state=...
    Browser->>RP: Authorization response
    RP->>RP: Kiểm tra state
    RP->>OP: POST /oauth2/token<br/>code, redirect_uri, code_verifier, client authentication
    OP-->>RP: access_token, id_token (và token khác nếu đủ điều kiện)
    RP->>OP: GET jwks_uri khi cần
    OP-->>RP: Public JWK Set
    RP->>RP: Xác minh ID Token: chữ ký, iss, aud, exp, nonce...
    RP->>OP: GET /userinfo với access_token (tùy chọn)
    OP-->>RP: UserInfo claims, sub nhất quán
    RP->>API: Authorization: Bearer access_token
    API-->>RP: Tài nguyên nếu token/quyền hợp lệ
~~~

Yêu cầu cấp quyền ví dụ (tách dòng cho dễ đọc; URL thực tế phải là một dòng được URL-encode hợp lệ):

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=portal-web
    &redirect_uri=https%3A%2F%2Fapp.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal
    &scope=openid%20profile%20email
    &state=STATE_RANDOM_VALUE
    &nonce=NONCE_RANDOM_VALUE
    &code_challenge=PKCE_S256_CHALLENGE
    &code_challenge_method=S256
Host: login.example.vn
~~~

`state`, `nonce` và PKCE values phải sinh ngẫu nhiên/đúng thuật toán cho **mỗi giao dịch**; các chuỗi viết hoa chỉ là placeholder. Client nhận callback rồi kiểm tra `state`, sau đó gửi `code_verifier` bí mật tương ứng tới token endpoint.

Ví dụ token response OIDC ở luồng Authorization Code (đã rút gọn):

~~~json
{
  "access_token": "ACCESS_TOKEN_REDACTED",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "SIGNED_ID_TOKEN_REDACTED",
  "scope": "openid profile email"
}
~~~

Response thực tế phụ thuộc grant, đăng ký client, scopes và chính sách token. Không log nguyên văn access token, ID Token, authorization code hay `code_verifier`.

## 4. Bật OIDC trong Spring Boot bằng SecurityFilterChain

### 4.1. Phụ thuộc và điều kiện tiên quyết

Trong ứng dụng Spring Boot sử dụng Spring Authorization Server tương thích, có thể khai báo các starter liên quan (tùy phiên bản Boot, dependency quản lý qua BOM):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-authorization-server'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Đây là ví dụ Gradle Groovy để nêu các chức năng cần có; phối hợp phiên bản Boot, Spring Security và Spring Authorization Server theo dependency management của dự án. Để chạy OIDC thực tế, cần có:

1. Một `RegisteredClientRepository` quản lý client, `redirect_uri`, scope và phương thức xác thực.
2. Một cơ chế đăng nhập người dùng (ví dụ form login và `UserDetailsService`, hoặc cơ chế tùy chỉnh).
3. `JWKSource<SecurityContext>` để ký JWT/ID Token và công bố public JWKS; `JwtDecoder` phục vụ các điểm cần giải mã/kiểm tra JWT.
4. Một `AuthorizationServerSettings` chứa issuer chính xác; các dịch vụ lưu authorization/consent tùy nhu cầu production.
5. HTTPS ở public endpoint, secret/khóa ký bền vững và đúng quyền truy cập trong production.

### 4.2. Filter chain dành riêng cho Authorization Server

Ví dụ dưới đây dùng API `OAuth2AuthorizationServerConfigurer` hiện đại trong Spring Authorization Server 1.x và Spring Security 6.x:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults())) // BẬT OIDC
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Các kiểu sử dụng trong ví dụ thuộc những gói `org.springframework.security.config.annotation.web.*`, `org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.*`, `org.springframework.security.web.authentication.*` và `org.springframework.http.MediaType` (đảm bảo IDE import đúng theo dependency thực tế).

**Ý nghĩa của từng cấu hình:**

- `@Order(1)` và `securityMatcher(authorizationServer.getEndpointsMatcher())`: chỉ áp filter chain đầu tiên cho tập endpoint của Authorization Server; tránh để login filter chain thông thường bắt và chặn sai.
- `.with(authorizationServer, server -> server.oidc(Customizer.withDefaults()))`: bật các thành phần OIDC. Nếu thiếu lệnh này, endpoint `/.well-known/openid-configuration` có thể trả 404 và client OIDC không khám phá được metadata.
- `.oauth2ResourceServer(resourceServer -> resourceServer.jwt(...))`: chuẩn bị xử lý Bearer JWT cho những endpoint như UserInfo. Đây **không** có nghĩa là cho phép mọi Bearer token truy cập mọi tài nguyên.
- `.exceptionHandling(...LoginUrlAuthenticationEntryPoint...)`: khi browser cần tương tác đăng nhập, điều hướng tới trang `/login`; request API/token cần có cơ chế trả lỗi thích hợp.
- Filter chain thứ hai thiết lập đăng nhập người dùng vào OP. Cần bổ sung `UserDetailsService` hoặc authentication provider có thật; hai chain riêng không tự tạo người dùng.

Các cấu hình trên là **khung bảo mật**; chương trình còn cần các bean ở mục 5 và 6. Spring Authorization Server có thể cung cấp mặc định một số dịch vụ trong bộ nhớ; production thường cần lưu authorization và consent bền vững. Không sao chép cấu hình mẫu vào production khi chưa có chiến lược session, CSRF, audit, persistence và quản lý khóa.

## 5. Cấu hình issuer, signing key và JwtDecoder

### 5.1. Cố định Issuer Identifier

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings(
        @Value("${app.authorization-server.issuer}") String issuer) {
    return AuthorizationServerSettings.builder()
            .issuer(issuer)
            .build();
}
~~~

Ví dụ cấu hình runtime:

~~~yaml
# application.yml
app:
  authorization-server:
    issuer: ${AUTH_SERVER_ISSUER}
~~~

~~~text
AUTH_SERVER_ISSUER=https://login.example.vn
~~~

Dòng `AUTH_SERVER_ISSUER=...` chỉ mô tả giá trị môi trường, **không** phải nội dung cần đặt thẳng trong YAML. `issuer` là định danh **công khai, ổn định** của OP; không phải bí mật. Trong ID Token, claim `iss` phải **khớp tuyệt đối** metadata `issuer` và issuer mà RP tin cậy. Đừng để issuer bị suy ra thành `http://localhost:9000` khi server chạy sau reverse proxy.

Nếu có prefix đường dẫn hoặc multi-tenant issuer, cần xác nhận chính xác metadata discovery URL theo OIDC Discovery và URL thực tế mà thư viện phát hành. Không tự sửa/trimming slash khi so sánh issuer.

### 5.2. JWKSource và JwtDecoder

Spring Authorization Server dùng `JWKSource<SecurityContext>` khi cấp token tự chứa được ký, và phát **public JWK Set** qua `/oauth2/jwks`. Khóa ký JWT/ID Token phải được chia sẻ nhất quán giữa các instance server và giữ bền vững qua restart.

Ví dụ **chỉ phục vụ local development/kiểm thử** (tạo key mới trong bộ nhớ):

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    KeyPair pair = generator.generateKeyPair();

    RSAKey rsaJwk = new RSAKey.Builder((RSAPublicKey) pair.getPublic())
            .privateKey((RSAPrivateKey) pair.getPrivate())
            .keyID(UUID.randomUUID().toString())
            .build();

    JWKSet jwkSet = new JWKSet(rsaJwk);
    return (selector, context) -> selector.select(jwkSet);
}

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Các lớp `RSAKey`, `JWKSet`, `JWKSource`, `SecurityContext` thuộc Nimbus JOSE/JWT; `JwtDecoder` thuộc Spring Security OAuth2 JWT. Import `KeyPairGenerator`, `RSAPublicKey`, `RSAPrivateKey`, `GeneralSecurityException` và `UUID` từ Java chuẩn. `jwtDecoder` trong ví dụ tạo decoder dựa trên nguồn khóa hiện có; nó cũng được những thành phần OIDC sử dụng khi cần kiểm tra JWT.

**Cảnh báo vận hành:** Nếu mỗi lần restart hoặc mỗi pod lại sinh RSA key ngẫu nhiên như ví dụ, token được ký bởi một instance có thể không xác minh được khi JWKS/instance thay đổi. Trong production, **không dùng** cách này. Lấy private key từ secret store, keystore/HSM/KMS theo chính sách và cấu hình một nguồn khóa/JWKS ổn định; bảo vệ private key, chỉ công bố public key; thiết kế `kid` và rotation để token đang hiệu lực không bị mất xác minh đột ngột.

## 6. Đăng ký một OIDC client hợp lệ

Khi client sử dụng Authorization Code + OIDC, ngoài `redirect_uri` và grant type còn cần scope `openid`. Nếu muốn redirect sau logout, đăng ký riêng `post_logout_redirect_uri`.

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder,
        @Value("${PORTAL_CLIENT_SECRET}") String clientSecret) {

    RegisteredClient portal = RegisteredClient.withId("portal-registration")
            .clientId("portal-web")
            .clientSecret(passwordEncoder.encode(clientSecret))
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://app.example.vn/login/oauth2/code/portal")
            .postLogoutRedirectUri("https://app.example.vn/logged-out")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope(OidcScopes.EMAIL)
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .build();

    return new InMemoryRegisteredClientRepository(portal);
}

@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

Đoạn code minh họa một **confidential web client**. Phải cấp giá trị `PORTAL_CLIENT_SECRET` qua secret store/biến môi trường được bảo vệ; Authorization Server lưu **hash** bằng `PasswordEncoder`. Đừng hardcode secret bản rõ hoặc dùng `{noop}` trong production. `InMemoryRegisteredClientRepository` chỉ nên dùng cho ví dụ/local; hệ thống thật cần kho dữ liệu bền vững, quy trình cấp client và thay secret.

Các điểm dễ nhầm:

1. `scope(OidcScopes.OPENID)` cho phép client yêu cầu OIDC. Nếu authorization request không có `openid`, đó không phải yêu cầu xác thực OIDC; không mặc nhiên nhận ID Token.
2. `redirectUri(...)` là callback nhận **authorization code**; `postLogoutRedirectUri(...)` là đích quay về **sau logout**. Chúng được kiểm tra riêng và không thay thế lẫn nhau.
3. `requireProofKey(true)` buộc client dùng PKCE. Ngay cả confidential client cũng nên sử dụng PKCE để giảm nguy cơ authorization code bị chặn và lạm dụng.
4. `requireAuthorizationConsent(true)` khiến OP yêu cầu sự đồng ý theo chính sách; không đồng nghĩa mọi claim thuộc scope `profile` và `email` đều tự xuất hiện trong UserInfo.
5. Với **public client** (SPA/native app), client không thể giữ bí mật dạng `client_secret`. Cần đăng ký phương thức xác thực thích hợp, dùng PKCE và ràng buộc redirect URI theo loại ứng dụng. Không lấy ví dụ confidential client ở trên áp nguyên cho SPA.

## 7. Provider Configuration: công bố metadata để client tự khám phá

Sau khi bật OIDC, OP công bố tài liệu qua:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: login.example.vn
Accept: application/json
~~~

Một cấu trúc phản hồi **minh họa** (metadata thực tế tùy phiên bản và cấu hình):

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
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"]
}
~~~

**Lưu ý:** Không tự viết JSON này thành file tĩnh để thay endpoint built-in nếu không có thiết kế rõ ràng. Spring Authorization Server có cơ chế tạo metadata dựa trên cấu hình; khi endpoint/issuer/thuật toán thay đổi phải xem tài liệu thật do server xuất bản. Một số trường trong JSON minh họa có thể không được công bố nếu server không hỗ trợ tính năng tương ứng.

Ý nghĩa các trường quan trọng:

| Trường | Mục đích |
|---|---|
| `issuer` | Giá trị OP tự định danh; RP so khớp với issuer đã tin cậy và ID Token `iss` |
| `authorization_endpoint` | URL điều hướng browser thực hiện yêu cầu authorization |
| `token_endpoint` | URL đổi code/token bằng back-channel |
| `jwks_uri` | URL bộ **public keys** dùng xác minh chữ ký |
| `userinfo_endpoint` | URL lấy thông tin người dùng qua Bearer access token |
| `end_session_endpoint` | URL mà RP có thể dùng để yêu cầu OP logout |
| `id_token_signing_alg_values_supported` | Các thuật toán ký ID Token mà OP tuyên bố hỗ trợ |

Metadata có thể được đọc công khai; điều đó **không** cho phép client tin tưởng mọi issuer URL do người dùng nhập. RP cần có danh sách issuer tin cậy hoặc quy trình xác minh issuer được kiểm soát; tải metadata từ URL tùy ý có thể kéo theo rủi ro SSRF hoặc tin nhầm nguồn. Sau khi tải, phải kiểm tra `issuer` và xác minh ID Token theo OIDC Core.

**RFC 8414** còn định nghĩa OAuth Authorization Server Metadata ở `/.well-known/oauth-authorization-server`. Hai tài liệu discovery gần nhau nhưng phục vụ hai bộ yêu cầu khác nhau; OIDC Client thường dùng `/.well-known/openid-configuration`.

## 8. UserInfo Endpoint: lấy claims sau khi xác thực

UserInfo là tài nguyên được bảo vệ bởi **access token**, không phải endpoint công khai giống Provider Configuration. Ví dụ request:

~~~http
GET /userinfo HTTP/1.1
Host: login.example.vn
Authorization: Bearer ACCESS_TOKEN_REDACTED
Accept: application/json
~~~

Ví dụ response khi user, scope và chính sách cho phép:

~~~json
{
  "sub": "user-123",
  "name": "Nguyen Van A",
  "preferred_username": "vana",
  "email": "vana@example.vn",
  "email_verified": true
}
~~~

Đây là **dữ liệu minh họa**, không phải cam kết Spring Authorization Server luôn trả mọi claim ở trên. Mặc định UserInfo có thể chỉ có các claim cơ bản hoặc được ánh xạ từ thông tin trong authorization/ID Token; muốn lấy thuộc tính người dùng từ database/identity provider thì cần cơ chế mapping tương ứng.

### 8.1. Các kiểm tra bắt buộc

- Request UserInfo phải được xác thực bằng access token hợp lệ, thường dùng Bearer authentication. Token chỉ dành cho Resource Server khác không nên tự động có quyền đọc UserInfo.
- `sub` trả về từ UserInfo **phải trùng** `sub` trong ID Token mà client đã xác minh. Nếu khác, RP **không được** sử dụng response đó để gắn danh tính.
- Scope `openid` là nền tảng của yêu cầu OIDC. `profile`, `email` và các scope/claims khác chỉ yêu cầu quyền tương ứng, không đảm bảo dữ liệu tồn tại hoặc được phép công bố.
- Không cho phép client tự chọn `sub` bằng tham số query để đọc UserInfo của người khác. Danh tính phải được xác định từ token đã xác thực và authorization context.
- Không log toàn bộ Bearer token hoặc nội dung UserInfo chứa thông tin cá nhân không cần thiết.

### 8.2. Tùy biến claims trong Spring Authorization Server

Spring Authorization Server hỗ trợ tùy biến cách ánh xạ UserInfo qua cấu hình `oidc().userInfoEndpoint(...)` và mapper tương ứng ở phiên bản sử dụng. Khi phát triển mapper:

1. Lấy danh tính của chủ thể từ **authentication/token/authorization đã xác thực**, không từ tham số do client tự gửi.
2. Chỉ truy vấn trường từ user store mà token, scope và chính sách consent được phép đọc.
3. Luôn giữ `sub` ổn định, trùng ID Token.
4. Kiểm thử trường hợp token hết hạn, thiếu scope, user đã bị khóa, đã thu hồi quyền hoặc dữ liệu user thay đổi.

Đừng trả nguyên entity JPA (có thể chứa password hash, email nội bộ, vai trò hệ thống) dưới dạng JSON UserInfo. Nên tạo DTO/claims rõ ràng và có kiểm thử riêng.

## 9. RP-Initiated Logout: kết thúc phiên và redirect an toàn

OIDC RP-Initiated Logout cho phép client yêu cầu OP kết thúc phiên đăng nhập ở OP. Với đường dẫn mặc định của Spring Authorization Server, RP có thể điều hướng browser đến `end_session_endpoint` nếu metadata công bố:

~~~http
GET /connect/logout?id_token_hint=ID_TOKEN_REDACTED
    &post_logout_redirect_uri=https%3A%2F%2Fapp.example.vn%2Flogged-out
    &state=LOGOUT_STATE_RANDOM HTTP/1.1
Host: login.example.vn
~~~

Dòng query được ngắt cho dễ đọc; URL thực tế phải nằm trên một dòng. `id_token_hint` giúp OP xác định client/phiên liên quan; `post_logout_redirect_uri` phải phù hợp giá trị đã đăng ký và chính sách logout của OP. `state` cho phép client liên kết response quay về với yêu cầu logout.

**Các giới hạn quan trọng:**

- Logout OP không có nghĩa mọi session của client khác đã hết hạn hoặc tất cả access token/refresh token bị thu hồi. Chỉ thực hiện front-channel/back-channel logout hoặc revocation nếu giao thức, thư viện và triển khai thực tế hỗ trợ.
- Client cũng cần xóa/đóng session cục bộ đúng cách, kể cả khi không có redirect quay về.
- Không chấp nhận URI quay về tùy ý để tránh open redirect. `post_logout_redirect_uri` không phải `redirect_uri` của authorization request.
- Không đặt ID Token, client secret hay access token đầy đủ trong log, analytics URL, referrer hoặc ticket; nếu dùng `id_token_hint` trong URL, phải kiểm soát logging và xử lý dữ liệu nhạy cảm phù hợp.

## 10. Tùy biến endpoint OIDC và Dynamic Client Registration

### 10.1. Đổi đường dẫn UserInfo/Logout qua AuthorizationServerSettings

Khi có yêu cầu cụ thể về reverse proxy, kiến trúc API hoặc versioning, có thể đổi một số endpoint mặc định:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings(
        @Value("${app.authorization-server.issuer}") String issuer) {
    return AuthorizationServerSettings.builder()
            .issuer(issuer)
            .oidcUserInfoEndpoint("/oidc/userinfo")
            .oidcLogoutEndpoint("/oidc/logout")
            .build();
}
~~~

Đoạn trên **thay thế** bean `AuthorizationServerSettings` tại mục 5.1, **không được định nghĩa đồng thời hai bean kiểu này** khi cấu hình chỉ cần một bản settings. Cần cập nhật proxy/security route, kiểm thử metadata trả về `userinfo_endpoint` và `end_session_endpoint` mới. Nếu client đã lưu cứng endpoint cũ, phải có kế hoạch tương thích/migration; client mới nên đọc metadata.

Tùy biến **hành vi** khác tùy biến **đường dẫn**. Tùy biến hành vi UserInfo/Logout dùng hook của `OidcConfigurer` trong filter chain, ví dụ:

~~~java
.with(authorizationServer, server ->
    server.oidc(oidc -> oidc
        .userInfoEndpoint(Customizer.withDefaults())
        .logoutEndpoint(Customizer.withDefaults())
        .providerConfigurationEndpoint(Customizer.withDefaults())))
~~~

Đoạn trên cho thấy vị trí cấu hình các endpoint OIDC trong DSL; `Customizer.withDefaults()` **giữ hành vi mặc định**, chưa thêm custom mapper/handler. Khi thật sự cần custom claims hoặc logout response, thay bằng customizer phù hợp API và phiên bản thư viện, kèm kiểm thử bảo mật. Không tự tạo controller `/userinfo` không kiểm tra Bearer token để thay endpoint chuẩn.

### 10.2. Dynamic Client Registration: chỉ bật khi có nhu cầu vận hành

OIDC Dynamic Client Registration cho phép client đăng ký metadata của chính nó qua API. Spring Authorization Server **không bật endpoint này mặc định**. Trong môi trường cần cấp phát client động, có thể chủ động kích hoạt:

~~~java
.with(authorizationServer, server ->
    server.oidc(oidc ->
        oidc.clientRegistrationEndpoint(Customizer.withDefaults())))
~~~

Đoạn trên là **mẫu thay thế** lời gọi `server.oidc(Customizer.withDefaults())` tại mục 4.2; giữ các phần còn lại của filter chain. Trước khi bật cần xây dựng chính sách cấp quyền đăng ký (initial access token/quyền liên quan), kiểm soát client metadata, redirect URI, grant type, phương thức xác thực, quota/rate limit và audit. Tránh để bất kỳ người dùng internet nào tự đăng ký confidential client tùy ý hoặc nhận quyền vượt quá chính sách.

Endpoint Dynamic Client Registration không đồng nghĩa đăng ký người dùng cuối (sign-up), và cũng không thay thế repository/phê duyệt client được thiết kế sẵn cho nhiều hệ thống nội bộ.

## 11. Kiểm thử sau cấu hình

### 11.1. Kiểm tra discovery và public JWKS

Sau khi service thực sự chạy ở hostname public (trong local thay host/port đúng môi trường), kiểm tra:

~~~bash
curl -fsS https://login.example.vn/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri, userinfo_endpoint, end_session_endpoint}'

curl -fsS https://login.example.vn/oauth2/jwks \
  | jq '{key_count: (.keys | length), kids: [.keys[].kid]}'
~~~

Kỳ vọng: Provider Configuration trả JSON với `issuer` khớp cấu hình, `userinfo_endpoint` và `end_session_endpoint` đúng; public JWKS có khóa xác minh hợp lệ và **không** chứa thông số private key. Nếu đã tùy biến đường dẫn `jwkSetEndpoint`, phải lấy URL từ `jwks_uri` trong metadata thay vì ghim `/oauth2/jwks`.

Có thể đối chiếu thêm OAuth AS Metadata:

~~~bash
curl -fsS https://login.example.vn/.well-known/oauth-authorization-server \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'
~~~

Lệnh này chỉ kiểm tra khả năng công bố metadata, **chưa chứng minh** luồng đăng nhập, UserInfo hay logout đã hoạt động.

### 11.2. Kiểm thử luồng từ đầu đến cuối

| Tình huống | Kết quả mong đợi |
|---|---|
| `GET /.well-known/openid-configuration` khi bật OIDC | 200 JSON, issuer chính xác, các endpoint được khai báo đúng |
| `scope=openid` + Authorization Code + PKCE hợp lệ | Trả authorization code; đổi tại token endpoint nhận ID Token có chữ ký hợp lệ |
| Authorization request **không** có `openid` | Không coi đó là xác thực OIDC; không kỳ vọng ID Token |
| Callback khác URI đã đăng ký | Yêu cầu cấp quyền bị từ chối, không redirect code tới URI lạ |
| Sai `state` hoặc PKCE `code_verifier` | Client hoặc token endpoint từ chối giao dịch |
| ID Token có `iss`/`aud` sai hoặc chữ ký/nonce không hợp lệ | RP từ chối ID Token |
| `GET /userinfo` không Bearer token | Bị từ chối (thường 401); không trả claims |
| `GET /userinfo` có token hợp lệ, quyền phù hợp | JSON claims hợp chính sách, `sub` khớp ID Token |
| `post_logout_redirect_uri` chưa đăng ký | Logout không được điều hướng đến URI không đáng tin |
| Dynamic Client Registration khi chưa bật | Endpoint không được sử dụng như dịch vụ cấp client công khai |
| Đổi issuer hoặc mất JWKS sau proxy/rolling restart | Phát hiện lỗi validation/discovery; không chấp nhận token sai issuer hoặc chữ ký |

Cần thực hiện kiểm thử đăng nhập/consent qua trình duyệt hoặc OAuth2 Client test tương đương; `curl` đơn thuần đến `/oauth2/authorize` không mô phỏng đầy đủ form login, cookie session và CSRF. Token, secret và mã code trong test report phải là dữ liệu giả/đã che.

### 11.3. Lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra/sửa |
|---|---|---|
| `/.well-known/openid-configuration` trả 404 | Chưa gọi `.oidc(...)`, request không vào đúng filter chain hoặc proxy sai route | Kiểm tra configurer OIDC, `securityMatcher` và route public |
| Provider Configuration có `http://localhost` | Issuer suy từ request nội bộ/reverse proxy | Đặt issuer public HTTPS qua `AuthorizationServerSettings`; cấu hình proxy tin cậy |
| OIDC Client không có `id_token` | Thiếu scope `openid`, grant/RegisteredClient sai hoặc luồng token không hợp lệ | Xem request đã được cấp scope `openid`; kiểm tra token exchange và signing setup |
| `/userinfo` trả 401 | Không có Bearer token, filter chain thiếu JWT support hoặc token invalid | Kiểm tra Authorization header, JWT decoder/keys và authentication entrypoint |
| `/userinfo` không có `email` | Chưa mapping claims, thiếu scope/consent hoặc dữ liệu user không có | Tùy biến UserInfo mapper theo policy, kiểm tra ID Token/UserInfo `sub` |
| Token bị báo `Invalid issuer` | `iss` trong JWT khác issuer client tin cậy (cả dấu `/` hoặc path) | So sánh chính xác issuer metadata/token/cấu hình RP |
| `/connect/logout` không đưa về ứng dụng | `post_logout_redirect_uri` chưa đăng ký, thiếu hint/phiên hợp lệ, sai proxy URL | Kiểm tra RegisteredClient, metadata, request logout và log đã che dữ liệu |
| JWKS đổi sau restart làm token cũ lỗi | RSA key tạo ngẫu nhiên tại startup hoặc các pod dùng khóa không nhất quán | Dùng nguồn khóa bền vững, công bố các public key cần thiết khi rotation |
| `/connect/register` không dùng được | Dynamic Client Registration chưa bật hoặc bị từ chối quyền | Chỉ bật khi có nhu cầu; cấu hình đăng ký có xác thực/ủy quyền |

## 12. Nguyên tắc bảo mật và vận hành production

- **Không nhầm OIDC với OAuth authorization:** OIDC xác thực người dùng ở RP bằng ID Token; Resource Server kiểm tra access token theo issuer, chữ ký, hạn dùng, audience, scope và chính sách riêng. ID Token không phải credential API.
- **Public HTTPS và issuer ổn định:** metadata/redirect/end-session phải dùng scheme, hostname và path công khai chính xác; reverse proxy chỉ tin forwarded headers từ hạ tầng được kiểm soát.
- **PKCE + state + nonce:** dùng Authorization Code Flow với PKCE; RP ràng buộc response bằng `state` và xác minh `nonce` trong ID Token khi đã gửi; tránh flow cũ dễ lộ token qua front channel.
- **Redirect URI chính xác:** cả callback sau authorization và URI sau logout phải được đăng ký/kiểm tra đúng; không dùng wildcard hoặc open redirect.
- **Khóa ký/JWKS:** chỉ public key được công bố, private key ở secret store/HSM/keystore; dùng `kid` và quá trình rotation bảo đảm token còn hiệu lực có thể xác minh.
- **Giới hạn UserInfo:** chỉ cấp claims mà quyền/scope/consent cho phép; không trả password hash, secret, dữ liệu quản trị hoặc thông tin người khác.
- **Dynamic registration có kiểm soát:** giữ tắt nếu không có use case, không cho đăng ký client không hạn chế; theo dõi audit.
- **Giám sát và thử nghiệm:** theo dõi availability/latency của discovery, authorization, token, UserInfo, logout, JWKS; cảnh báo lỗi issuer/JWT validation tăng bất thường; giữ log không chứa token/secret.
- **Session/logout:** quản lý cookie an toàn, session fixation, SameSite, CSRF và timeout phù hợp; phân biệt logout phiên OP, session RP và hiệu lực của access/refresh token.

### Câu hỏi tự kiểm tra

1. Bật `server.oidc(Customizer.withDefaults())` thay đổi những gì so với một OAuth 2.0 Authorization Server chưa bật OIDC?
2. Vì sao Resource Server không nên dùng ID Token làm access token?
3. Tại sao UserInfo yêu cầu Bearer access token, trong khi Discovery và public JWKS thường cho phép GET công khai?
4. `redirectUri(...)` và `postLogoutRedirectUri(...)` khác nhau ở đâu?
5. Tại sao cần một signing key ổn định giữa các pod và qua restart?
6. Dynamic Client Registration được bật mặc định hay không, và cần điều kiện bảo mật nào trước khi bật?
7. Khi đổi đường dẫn `/userinfo` qua `AuthorizationServerSettings`, cần kiểm tra các phần nào ở metadata, proxy và client?

## Tài liệu tham khảo

- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): authorization server configurer và các endpoint cấu hình.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OAuth 2.0 và OIDC endpoint configurers.
- [Spring Authorization Server — Core Model/Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, các repository và token service.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo, validation và authentication flows.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration và metadata.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): yêu cầu logout và `post_logout_redirect_uri`.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): quy tắc đăng ký client động.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, redirect URI, bảo vệ luồng authorization.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata OAuth 2.0.
