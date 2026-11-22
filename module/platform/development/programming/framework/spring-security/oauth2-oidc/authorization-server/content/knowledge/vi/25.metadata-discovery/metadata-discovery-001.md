# OAuth2 Authorization Server Metadata theo RFC 8414

> **Chương:** Metadata và Discovery  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phạm vi kỹ thuật:** RFC 8414 và Spring Authorization Server (SAS) 1.5.x trên Spring Boot 3.x/Spring Security 6.x, Servlet stack. Các ví dụ đặt issuer ở `https://auth.example.test`. Nếu dự án dùng Spring Security 7.x có tích hợp Authorization Server, cần đối chiếu lại starter/package/DSL của đúng version.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **OAuth 2.0 Authorization Server Metadata** giải quyết bài toán gì và vì sao nó thường được gọi là **OAuth Discovery**.
2. Tính đúng URL `/.well-known/oauth-authorization-server` từ issuer theo RFC 8414, kể cả trường hợp issuer chứa path.
3. Nhận diện `issuer` và các trường về endpoints, grant types, response types, PKCE, client authentication, key locations và những extension metadata.
4. Phân biệt **metadata của Authorization Server**, **JWK Set**, **OpenID Provider Configuration** và **Protected Resource Metadata**.
5. Hiểu các điều kiện `REQUIRED`, `RECOMMENDED`, `OPTIONAL`, các mặc định RFC 8414 khi một field bị bỏ qua và lý do không nên dựa mù quáng vào default cũ.
6. Cấu hình `AuthorizationServerSettings` và `OAuth2AuthorizationServerMetadataEndpointConfigurer` trong Spring Authorization Server.
7. Thiết kế issuer, HTTPS, reverse proxy, path routing, metadata caching và JWKS mà không tạo mix-up/issuer mismatch.
8. Viết bài kiểm tra tự động cho discovery endpoint, issuer consistency, metadata security, khả năng client sử dụng và triển khai nhiều môi trường.

**Điểm cốt lõi:** RFC 8414 cho phép một OAuth2 Client biết **Authorization Server ở đâu và hỗ trợ những khả năng nào** từ một tài liệu JSON chuẩn gắn với **issuer đã tin cậy**. Metadata giúp loại bỏ URL hardcode không cần thiết, nhưng **không xác thực client, không cấp quyền cho client và không chứng minh rằng mọi capability đều được cấp cho mọi RegisteredClient**.

## 2. Bài toán trước khi có Discovery

Một ứng dụng OAuth2 Client cần ít nhất:

- Issuer/định danh Authorization Server (AS).
- Authorization Endpoint để bắt đầu Authorization Code + PKCE.
- Token Endpoint để đổi authorization code hoặc refresh token.
- JWK Set URI nếu cần xác minh JWT/ID token.
- Khả năng hỗ trợ: grant types, response types, PKCE challenge method, client authentication method.
- Trong hệ thống phức tạp: Token Revocation, Token Introspection, Dynamic Client Registration, PAR, Device Authorization và các extension khác.

Nếu mọi địa chỉ được hardcode vào mỗi client, thay đổi hostname, reverse proxy, đường dẫn hoặc phương thức xác thực có thể buộc cập nhật hàng chục ứng dụng.

Ví dụ client cấu hình thủ công:

~~~yaml
oauth:
  issuer: https://auth.example.test
  authorization-uri: https://auth.example.test/oauth2/authorize
  token-uri: https://auth.example.test/oauth2/token
  jwk-set-uri: https://auth.example.test/oauth2/jwks
~~~

Nếu issuer thay đổi có kiểm soát hoặc endpoint được di chuyển, tất cả client cần được cập nhật đúng. Sai một URL có thể dẫn tới 404, lấy khóa của issuer khác hoặc rủi ro gửi authorization code/credential sai đích.

RFC 8414 định nghĩa **một tài liệu JSON chuẩn** mà client có thể truy xuất từ issuer để biết endpoint và capability thực tế.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant R as Resource Server

    Note over C,AS: Client biết issuer từ cấu hình tin cậy
    C->>AS: GET /.well-known/oauth-authorization-server
    AS-->>C: 200 JSON: issuer, endpoints, capabilities, jwks_uri
    C->>C: Verify issuer trùng giá trị đã tin cậy
    C->>AS: Authorization request / token request tùy grant
    AS-->>C: Authorization code / access token
    C->>R: Authorization: Bearer access token
    R->>R: Kiểm tra issuer, audience, signature, expiry và quyền
~~~

**Discovery không thay thế client registration.** Metadata có thể quảng bá `client_secret_basic` và `private_key_jwt`, nhưng mỗi RegisteredClient vẫn có phương thức riêng được phép dùng, các grant/scopes riêng và credential riêng.

## 3. RFC 8414 là gì?

RFC 8414, *OAuth 2.0 Authorization Server Metadata* (tháng 6/2018), định nghĩa một metadata document dạng JSON với:

- Định danh issuer.
- URL các endpoint chuẩn.
- Capability của Authorization Server.
- Cách công bố metadata tại `.well-known` URI.
- Cách client phải kiểm tra metadata trước khi sử dụng.
- Một khả năng tùy chọn mang metadata được ký dưới dạng `signed_metadata`.

Nó mở rộng ý tưởng từ OpenID Connect Discovery sang **OAuth 2.0 nói chung**, bao gồm những hệ thống **không bật OIDC**.

### 3.1. Ba thứ dễ bị nhầm

| Thành phần | Câu hỏi giải quyết | Thường truy xuất ở đâu? |
| --- | --- | --- |
| **Authorization Server Metadata** (RFC 8414) | “AS có issuer, endpoint và capability nào?” | `/.well-known/oauth-authorization-server` từ issuer |
| **JWK Set (JWKS)** (RFC 7517) | “Public key nào để xác minh JWT?” | URI được công bố trong `jwks_uri`, ví dụ `/oauth2/jwks` |
| **OpenID Provider Configuration** (OIDC Discovery) | “OpenID Provider hỗ trợ login, ID token, UserInfo, scopes/claims nào?” | `/.well-known/openid-configuration` theo OIDC |

Ngoài ra, **Protected Resource Metadata** (RFC 9728, tháng 4/2025) mô tả **Resource Server**, không phải Authorization Server. Nó có thể giúp client tìm các AS có quan hệ với tài nguyên, nhưng không thay thế metadata RFC 8414.

### 3.2. Metadata công khai không đồng nghĩa endpoint khác công khai

Tài liệu metadata nên truy cập được bằng HTTPS GET thông thường, không yêu cầu client secret hoặc user login mới biết cấu hình. Tuy nhiên:

- `/oauth2/token` vẫn yêu cầu client authentication phù hợp với grant/registration.
- `/oauth2/introspect` và `/oauth2/revoke` vẫn có authentication/authorization riêng.
- `/connect/register` không tự được mở chỉ vì metadata nói đến dynamic registration.
- `/oauth2/authorize` vẫn cần user authentication/consent khi flow yêu cầu.
- `/oauth2/jwks` chỉ công bố **public key**, không bao giờ private key.

Metadata cho biết **đường dẫn và khả năng**, không tự cấp permission.

## 4. Tạo URL well-known đúng theo issuer

### 4.1. Issuer không chứa path

Nếu issuer là:

~~~text
https://auth.example.test
~~~

URL metadata là:

~~~text
https://auth.example.test/.well-known/oauth-authorization-server
~~~

HTTP request:

~~~http
GET /.well-known/oauth-authorization-server HTTP/1.1
Host: auth.example.test
Accept: application/json
~~~

AS trả HTTP 200 JSON metadata.

### 4.2. Issuer có path: well-known được chèn trước path

Đây là điểm quan trọng của RFC 8414. Ví dụ issuer:

~~~text
https://auth.example.test/tenant/acme
~~~

URL metadata theo RFC 8414 là:

~~~text
https://auth.example.test/.well-known/oauth-authorization-server/tenant/acme
~~~

**Không phải**:

~~~text
https://auth.example.test/tenant/acme/.well-known/oauth-authorization-server
~~~

Với RFC 8414, phần `/.well-known/oauth-authorization-server` được **chèn giữa host và path của issuer**.

| Issuer | RFC 8414 metadata URL |
| --- | --- |
| `https://auth.example.test` | `https://auth.example.test/.well-known/oauth-authorization-server` |
| `https://auth.example.test/issuer1` | `https://auth.example.test/.well-known/oauth-authorization-server/issuer1` |
| `https://auth.example.test/tenants/a` | `https://auth.example.test/.well-known/oauth-authorization-server/tenants/a` |

RFC yêu cầu loại bỏ dấu `/` kết thúc issuer path trước khi chèn suffix theo quy tắc. Khi triển khai multi-tenant, phải kiểm tra URL bên ngoài qua proxy và routing thực tế; không suy rằng một servlet context path tự động đảm bảo mọi issuer/path sẽ tuân RFC.

### 4.3. Không đoán URL từ Token Endpoint

Nếu biết:

~~~text
https://auth.example.test/oauth2/token
~~~

không thể tự suy issuer chắc chắn là `https://auth.example.test` nếu hệ thống triển khai nhiều issuer/path hay host alias. Cần nhận issuer từ cấu hình đáng tin cậy hoặc cơ chế xác định AS phù hợp, sau đó áp dụng thuật toán well-known.

### 4.4. Điều kiện với issuer

Theo RFC 8414, `issuer`:

- Là URL dùng `https`.
- Không chứa query string.
- Không chứa fragment.
- Phải nhận diện chính xác AS đang cung cấp metadata.
- Phải khớp **chính xác** với issuer identifier mà client dùng để tạo well-known URL.

Ví dụ:

~~~text
Issuer đã tin cậy: https://auth.example.test
Metadata issuer:   https://auth.example.test
=> Khớp

Issuer đã tin cậy: https://auth.example.test
Metadata issuer:   https://auth-alias.example.test
=> KHÔNG khớp

Issuer đã tin cậy: https://auth.example.test/tenant/a
Metadata issuer:   https://auth.example.test/tenant/b
=> KHÔNG khớp
~~~

Không tự “sửa” issuer bằng cách bỏ path, đổi host, ép lowercase toàn bộ URL hoặc biến alias thành issuer khác. RFC 8414 quy định **exact-match** sau khi xử lý JSON escaping, không áp dụng Unicode normalization tùy tiện.

## 5. Cấu trúc JSON của Authorization Server Metadata

Ví dụ minh họa cho một AS sử dụng Authorization Code + PKCE, Client Credentials, Refresh Token và các endpoint phổ biến:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300

{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "response_types_supported": ["code"],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ],
  "scopes_supported": ["booking.read", "booking.write"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt",
    "none"
  ],
  "token_endpoint_auth_signing_alg_values_supported": ["RS256"],
  "code_challenge_methods_supported": ["S256"],
  "revocation_endpoint": "https://auth.example.test/oauth2/revoke",
  "introspection_endpoint": "https://auth.example.test/oauth2/introspect"
}
~~~

**Lưu ý:** Đây là **tài liệu JSON minh họa một cấu hình có thể có**, không phải khẳng định Spring Authorization Server mặc định phát chính xác các field và giá trị này. Danh sách support phải được đối chiếu với phiên bản, cấu hình endpoint, authentication providers và chính sách thực tế. Không thêm `registration_endpoint` khi chưa bật/triển khai Dynamic Client Registration.

### 5.1. Ý nghĩa của issuer

`issuer` là **định danh bảo mật**, không chỉ là URL trang chủ. Nó liên quan tới:

- Discovery metadata validation.
- JWT access token `iss` nếu profile phát token có issuer.
- OIDC ID token `iss` khi bật OIDC.
- Resource Server issuer validation.
- Chống nhầm lẫn giữa nhiều Authorization Servers (authorization server mix-up).
- Tách tenant/realm có issuer khác nhau.

Nếu metadata nói issuer A nhưng JWT được ký mang `iss` là issuer B, Resource Server/OIDC Client phải từ chối theo policy. Không chấp nhận chỉ vì chữ ký JWT xác minh được bằng một public key quen thuộc.

### 5.2. Endpoint URL

Một field như `authorization_endpoint` hoặc `token_endpoint` chỉ rõ **URL đầy đủ** mà client sẽ gửi request. Client không nên nối string thủ công `issuer + "/oauth2/token"` nếu metadata đã cung cấp endpoint.

Trong deployment multi-tenant hoặc reverse proxy, endpoint có thể không nằm dưới cùng một path logic với issuer; điều bắt buộc là metadata công bố đúng URL thực tế và các ràng buộc bảo mật/HTTPS áp dụng.

### 5.3. Metadata mô tả khả năng server, không phải quyền client

Ví dụ metadata có:

~~~json
{
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ]
}
~~~

Client không được tự suy “mình có quyền dùng `client_credentials`”. Phía AS còn kiểm tra:

- `RegisteredClient.authorizationGrantTypes` có grant đó hay không.
- Client authentication method có đúng registration không.
- Scope có được đăng ký và cấp quyền không.
- Proof/PKCE/client assertion/certificate có hợp lệ không.
- Endpoint policy/tenant policy có cho phép không.

Tương tự, `scopes_supported` chỉ mô tả namespace scope mà AS hỗ trợ; không cho phép client xin mọi scope được liệt kê.

## 6. Các trường cốt lõi của RFC 8414

### 6.1. Trường bắt buộc hoặc theo điều kiện

| Metadata field | Mức yêu cầu RFC 8414 | Ý nghĩa |
| --- | --- | --- |
| `issuer` | **REQUIRED** | Định danh AS bằng HTTPS URL |
| `authorization_endpoint` | REQUIRED trừ khi không hỗ trợ grant cần authorization endpoint | URL bắt đầu authorization flow |
| `token_endpoint` | REQUIRED trừ trường hợp chỉ hỗ trợ implicit grant | URL đổi grant lấy token |
| `response_types_supported` | **REQUIRED** | Danh sách `response_type` ở authorization endpoint |
| `jwks_uri` | OPTIONAL trong chính RFC 8414 | HTTPS URL đến JWK Set của AS |
| `scopes_supported` | RECOMMENDED | Danh sách scope được hỗ trợ (có thể không công bố tất cả) |

“OPTIONAL” trong RFC 8414 không có nghĩa optional trong mọi profile khác. Ví dụ, OIDC Discovery có yêu cầu riêng cho `jwks_uri`, và nếu client cần JWT verification thì thiếu key source có thể khiến flow không hoạt động.

### 6.2. Những field mở rộng capability

| Metadata field | Mục đích |
| --- | --- |
| `response_modes_supported` | Response mode như `query`, `form_post` nếu được hỗ trợ |
| `grant_types_supported` | Authorization grant types mà AS hỗ trợ |
| `token_endpoint_auth_methods_supported` | Phương thức client authentication tại Token Endpoint |
| `token_endpoint_auth_signing_alg_values_supported` | Thuật toán JWS cho client assertion `private_key_jwt`/`client_secret_jwt` |
| `code_challenge_methods_supported` | PKCE methods như `S256` |
| `registration_endpoint` | URL Dynamic Client Registration nếu endpoint được bật |
| `revocation_endpoint` | URL Token Revocation Endpoint theo RFC 7009 |
| `introspection_endpoint` | URL Token Introspection Endpoint theo RFC 7662 |
| `revocation_endpoint_auth_methods_supported` | Client authentication tại revocation |
| `introspection_endpoint_auth_methods_supported` | Client authentication tại introspection |
| `service_documentation` | Trang tài liệu tích hợp của AS |
| `ui_locales_supported` | Locales của giao diện nếu được công bố |
| `op_policy_uri`, `op_tos_uri` | Chính sách/điều khoản sử dụng |
| `signed_metadata` | Metadata được ký, tùy chọn của RFC 8414 |

### 6.3. Không nhầm hai loại thuật toán

- `token_endpoint_auth_signing_alg_values_supported`: thuật toán mà AS chấp nhận khi **client dùng JWT assertion để xác thực tại Token Endpoint**.
- Thuật toán ký **access token/ID token của AS**: chính sách token generator/JWS signing keys, có thể được mô tả bằng field/profile khác.

Không dùng danh sách thuật toán client assertion làm allowlist để xác minh JWT access token nếu chưa có contract đúng. Tên gần giống nhưng mục đích khác nhau.

### 6.4. Quy tắc khi một metadata field bị bỏ qua

RFC 8414 có một số default lịch sử:

| Field vắng mặt | Default/semantics theo RFC 8414 | Lưu ý triển khai |
| --- | --- | --- |
| `response_modes_supported` | `["query","fragment"]` | Không nên tự suy form_post được hỗ trợ |
| `grant_types_supported` | `["authorization_code","implicit"]` | Default có `implicit` mang tính lịch sử; không bật implicit chỉ vì field vắng |
| `token_endpoint_auth_methods_supported` | `client_secret_basic` | Không suy private_key_jwt hay mTLS được hỗ trợ |
| `revocation_endpoint_auth_methods_supported` | `client_secret_basic` | Khác policy có thể được công bố tường minh |
| `introspection_endpoint_auth_methods_supported` | Phải xác định bằng phương thức khác | Không tự áp default của token endpoint |
| `code_challenge_methods_supported` | Theo RFC, vắng mặt biểu thị không hỗ trợ PKCE | Khi triển khai PKCE, nên công bố chính xác `S256` |
| `scopes_supported` | Không có tập scope ngầm định | Client không được suy ra mọi scope |
| `jwks_uri` | Không có default | Client cần key source phải xác định theo cơ chế hợp lệ |

**Lưu ý chuẩn và best practice:** Các giá trị mặc định là **semantics khi parse RFC 8414**, không phải khuyến nghị bật `implicit` hoặc cho phép thuật toán yếu trong hệ thống mới. Với OAuth2 Security Best Current Practice (RFC 9700), hệ thống hiện đại nên ưu tiên Authorization Code + PKCE và hạn chế các legacy flows không an toàn.

### 6.5. Danh sách rỗng có hợp lệ không?

RFC 8414 quy định những field có nhiều giá trị được biểu diễn bằng JSON array, và **array rỗng phải bị lược bỏ khỏi response**.

Không quảng bá:

~~~json
{
  "code_challenge_methods_supported": []
}
~~~

như thể đó là một giá trị bình thường; khi không có giá trị, lược bỏ field theo RFC. Tuy nhiên với `response_types_supported` bắt buộc, kiến trúc AS phải xác định profile/giá trị phù hợp, không bịa response type mà server không xử lý.

## 7. Metadata của Spring Authorization Server

### 7.1. Endpoint tích hợp

Trong Spring Authorization Server 1.5.x, `OAuth2AuthorizationServerConfigurer` hỗ trợ:

- `OAuth2AuthorizationServerMetadataEndpointConfigurer` để tùy chỉnh metadata.
- `OAuth2AuthorizationServerMetadataEndpointFilter` để phục vụ request metadata.
- `OAuth2AuthorizationServerMetadata` model/builder để tạo JSON response.
- `AuthorizationServerSettings` để định nghĩa issuer và URI của những OAuth2 endpoints chính.

Metadata endpoint thuộc các protocol endpoints mặc định của Spring Authorization Server. Không cần viết REST controller `@GetMapping("/.well-known/oauth-authorization-server")` nếu đang dùng filter/configurer của framework.

### 7.2. Cấu hình AS SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.authorizationServerMetadataEndpoint(
                    Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Ví dụ dùng SAS 1.x, giả định có những bean cần thiết như `RegisteredClientRepository`, `OAuth2AuthorizationService` và signing keys/issuer configuration khi cần phát JWT. Với OIDC, còn cần `OidcConfigurer` và các thành phần riêng.

Metadata filter thường trả JSON ngay tại endpoint trước khi user authentication logic của chain được thực thi; vì vậy metadata có thể truy cập công khai dù chain bảo vệ OAuth2 protocol endpoints còn lại. **Phải kiểm thử GET không kèm cookie/credential**; nếu custom filter, proxy hoặc rule security đổi thứ tự xử lý, không được để metadata trả HTML login/302/401 ngoài ý muốn.

### 7.3. Vì sao không để application chain bắt request trước?

Nếu một `SecurityFilterChain` tổng quát match `/**` trước AS chain, request `/.well-known/oauth-authorization-server` có thể rơi vào web application thay vì metadata filter.

Hậu quả:

- 404.
- 302 redirect `/login`.
- 401/403.
- HTML thay vì JSON.
- Metadata endpoint bị phục vụ từ controller tự viết có cấu hình không đồng bộ.

Dùng `@Order(1)` và `getEndpointsMatcher()` cho AS; kiểm tra trực tiếp request thật qua Spring Security FilterChain.

## 8. Cấu hình issuer và endpoint bằng AuthorizationServerSettings

### 8.1. Bean cấu hình issuer ổn định

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration
public class AuthorizationServerSettingsConfig {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.test")
            .authorizationEndpoint("/oauth2/authorize")
            .tokenEndpoint("/oauth2/token")
            .tokenIntrospectionEndpoint("/oauth2/introspect")
            .tokenRevocationEndpoint("/oauth2/revoke")
            .jwkSetEndpoint("/oauth2/jwks")
            .build();
    }
}
~~~

`issuer` là public URL mà clients/Resource Servers tin cậy. Không dùng tùy tiện `http://localhost:9000` hoặc internal hostname `http://auth-service:9000` trong production metadata nếu clients bên ngoài đang dùng `https://auth.example.test`.

### 8.2. Các endpoint URI khác

`AuthorizationServerSettings` hỗ trợ cấu hình nhiều endpoint path của OAuth2 và OIDC, tùy version:

| Setting | Đường dẫn thường thấy |
| --- | --- |
| `authorizationEndpoint(...)` | `/oauth2/authorize` |
| `tokenEndpoint(...)` | `/oauth2/token` |
| `tokenIntrospectionEndpoint(...)` | `/oauth2/introspect` |
| `tokenRevocationEndpoint(...)` | `/oauth2/revoke` |
| `jwkSetEndpoint(...)` | `/oauth2/jwks` |
| `pushedAuthorizationRequestEndpoint(...)` | `/oauth2/par` |
| `deviceAuthorizationEndpoint(...)` | `/oauth2/device_authorization` |
| `deviceVerificationEndpoint(...)` | `/oauth2/device_verification` |
| `oidcUserInfoEndpoint(...)` | `/userinfo` |
| `oidcLogoutEndpoint(...)` | `/connect/logout` |
| `oidcClientRegistrationEndpoint(...)` | `/connect/register` |

**Không phải tất cả endpoint đều được bật/công bố trong mọi cấu hình.** Ví dụ, OIDC disabled theo mặc định; Dynamic Client Registration trong OIDC disabled theo mặc định; JWK Set endpoint chỉ được cấu hình khi có `JWKSource<SecurityContext>` bean. Metadata phải phản ánh những endpoint thực sự phục vụ request.

### 8.3. Không có nghĩa cứ đổi issuer là endpoint tự được client chấp nhận

Thay đổi issuer là một thay đổi **security identity**. Nó ảnh hưởng tới JWT `iss`, OIDC login, issuer validation ở RS và redirect/client registration trong một số môi trường.

Để chuyển issuer cần:

1. Xác định issuer mới và HTTPS/DNS/TLS hợp lệ.
2. Công bố metadata mới ở well-known URL tương ứng.
3. Cập nhật cấu hình client/RS có cơ chế trust explicit.
4. Có kế hoạch cho token cũ ký dưới issuer cũ.
5. Kiểm tra signed JWT issuer, JWKS URI và audience.
6. Không tạo hai issuer alias tùy tiện cùng dùng một authorization state nếu chính sách không thiết kế như vậy.

### 8.4. Metadata path cố định theo RFC

`AuthorizationServerSettings` cho phép đổi **protocol endpoint paths** như token/authorization/JWKS, nhưng đường dẫn **RFC 8414 well-known** không nên xem là endpoint kinh doanh có thể đổi tùy tiện. `authorizationServerMetadataEndpoint(...)` chủ yếu tùy biến **metadata response**, không phải API tùy ý đặt tên mới.

Khi issuer có path hoặc reverse proxy rewrite phức tạp, phải route external `/.well-known/oauth-authorization-server/...` đúng theo RFC và kiểm thử public URL thực tế. Đừng dựa vào metadata endpoint nội bộ khớp nếu external path khác.

## 9. Tùy chỉnh metadata response qua DSL

Spring Authorization Server 1.5.x có extension point:

~~~java
authorizationServer
    .authorizationServerMetadataEndpoint(metadataEndpoint ->
        metadataEndpoint.authorizationServerMetadataCustomizer(
            metadata -> {
                metadata.claim(
                    "service_documentation",
                    "https://docs.example.test/oauth2/integration");

                metadata.claim(
                    "ui_locales_supported",
                    java.util.List.of("vi-VN", "en-US"));
            }
        )
    );
~~~

Đoạn code là fragment bên trong `.with(authorizationServer, ...)`, minh họa callback của `OAuth2AuthorizationServerMetadataEndpointConfigurer`.

### 9.1. Khi nào cần customizer?

- Công bố URL tài liệu tích hợp.
- Công bố locale UI nếu AS thực sự hỗ trợ.
- Công bố extension metadata theo chuẩn mới, ví dụ một feature đã triển khai.
- Bổ sung metadata dành cho một deployment profile nội bộ có contract và namespace rõ.
- Điều chỉnh quảng bá một capability để metadata phản ánh thực tế, nhưng phải kiểm tra tính tương thích với clients.

### 9.2. Không làm lệch metadata với implementation

Một customizer có thể sửa JSON builder, nhưng **không tự thêm AuthenticationProvider, filter hoặc endpoint**.

Ví dụ sai:

~~~java
metadata.claim(
    "grant_types_supported",
    java.util.List.of("authorization_code", "password"));
~~~

Nếu AS không hỗ trợ `password` grant, client đọc metadata sẽ hiểu sai. Ngược lại, tự công bố `registration_endpoint` không làm Dynamic Client Registration endpoint xuất hiện.

Với trường bảo mật quan trọng như `issuer`, `jwks_uri`, `token_endpoint` và authentication methods, ưu tiên cấu hình các component gốc thay vì override metadata “cho đẹp”.

### 9.3. Ví dụ cấu hình hoàn chỉnh hơn

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MetadataEndpointConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as -> as
                .authorizationServerMetadataEndpoint(endpoint -> endpoint
                    .authorizationServerMetadataCustomizer(metadata -> {
                        metadata.claim(
                            "service_documentation",
                            "https://docs.example.test/oauth2/integration");
                        metadata.claim(
                            "ui_locales_supported",
                            List.of("vi-VN", "en-US"));
                    })
                )
            )
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());

        return http.build();
    }
}
~~~

**Chú ý:** Đây là một cách thay thế cấu hình AS `SecurityFilterChain` ở mục 7.2, **không copy cả hai bean `@Order(1)` vào cùng dự án**. Các bean core components/issuer/JWK và chain ứng dụng khác phải được cấu hình ở những nơi phù hợp.

## 10. Metadata, JWT và JWK Set

### 10.1. Metadata cung cấp đường dẫn tới public keys

Field:

~~~json
{
  "jwks_uri": "https://auth.example.test/oauth2/jwks"
}
~~~

trỏ tới một JWK Set, ví dụ:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "as-key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

Những giá trị trên là placeholder. JWKS được phục vụ riêng với metadata và chỉ chứa **public key material** cần công bố.

### 10.2. Metadata discovery và JWKS fetch là hai thao tác khác

~~~mermaid
flowchart TD
    ISS["Issuer đáng tin cậy"]
    META["GET /.well-known/oauth-authorization-server"]
    CHECK{"Response issuer<br/>khớp issuer đã tin cậy?"}
    JSON["Nhận URLs/capabilities"]
    JWK["GET jwks_uri đã được xác minh"]
    VERIFY["Verify JWT<br/>signature, iss, aud, exp"]
    REJECT["Từ chối metadata/token"]

    ISS --> META --> CHECK
    CHECK -->|"Không"| REJECT
    CHECK -->|"Có"| JSON --> JWK --> VERIFY
~~~

Resource Server có thể được cấu hình trực tiếp với `issuer-uri` và sử dụng discovery để lấy key location. Một số môi trường truyền `jwk-set-uri` trực tiếp để chủ động kiểm soát URL/key fetch; khi đó vẫn phải xác minh issuer bằng validator phù hợp.

### 10.3. Metadata cache và JWKS cache khác nhau

Metadata thường thay đổi ít: issuer và endpoint URLs tương đối ổn định. JWKS thay đổi trong key rotation.

- Client có thể cache metadata theo HTTP policy/SDK.
- Resource Server có thể cache JWKS trong JWT decoder.
- CDN có thể cache cả hai theo TTL riêng.
- Public key mới phải được pre-publish trước khi AS chuyển signer theo kế hoạch.
- Thay đổi `jwks_uri` cần quan tâm cả metadata cache lẫn key cache.
- Đổi key `kid` không nhất thiết phải đổi metadata nếu `jwks_uri` giữ nguyên.

Không nghĩ rằng “client refresh metadata” đã làm mới JWKS trong cache của mọi Resource Server.

## 11. OAuth Metadata khác OIDC Discovery như thế nào?

### 11.1. Hai well-known endpoints phổ biến

| Loại metadata | Đường dẫn thường gặp | Khi nào cần? |
| --- | --- | --- |
| OAuth 2.0 RFC 8414 | `/.well-known/oauth-authorization-server` | OAuth2 AS, kể cả không có OIDC |
| OpenID Provider Configuration | `/.well-known/openid-configuration` | OIDC login, ID token, UserInfo và OP capabilities |

Spring Authorization Server cung cấp cả:

- `OAuth2AuthorizationServerMetadataEndpointConfigurer` cho OAuth2 metadata.
- `OidcProviderConfigurationEndpointConfigurer` cho OIDC Provider Configuration, sau khi bật `OidcConfigurer`.

OIDC **disabled mặc định** theo SAS 1.5.x. Không tự suy `/.well-known/openid-configuration` tồn tại chỉ vì OAuth2 metadata endpoint đã hoạt động.

### 11.2. Metadata OIDC có thêm fields

OIDC thường quảng bá:

- `userinfo_endpoint`.
- `id_token_signing_alg_values_supported`.
- `subject_types_supported`.
- `claims_supported` và OIDC claim capabilities.
- `end_session_endpoint` nếu RP-Initiated Logout được hỗ trợ.
- Các trường khác theo OpenID Connect Discovery và extension profiles.

Không giả định RFC 8414 yêu cầu mọi AS phải có `userinfo_endpoint`, ID token hoặc OIDC logout.

### 11.3. Path issuer có sự khác biệt lịch sử

Với issuer có path, RFC 8414 chèn suffix trước issuer path. OIDC Discovery 1.0 historically dùng cách tạo well-known URL khác với issuer path trong một số tình huống.

Ví dụ issuer `https://auth.example.test/tenant/a`:

~~~text
RFC 8414:
https://auth.example.test/.well-known/oauth-authorization-server/tenant/a

OIDC Discovery legacy transformation:
https://auth.example.test/tenant/a/.well-known/openid-configuration
~~~

RFC 8414 có lưu ý tương thích chuyển tiếp giữa các cách biến đổi well-known khi dùng suffix `openid-configuration`. Khi vận hành cả OAuth2 và OIDC, phải kiểm tra **URL thực tế mà client SDK dùng** theo profile/thư viện, không đơn giản thay tên suffix rồi nghĩ đường dẫn luôn giống nhau.

## 12. Extension metadata: PAR, Device, DPoP, mTLS

RFC 8414 cho phép bổ sung các metadata field được các tiêu chuẩn khác định nghĩa.

### 12.1. Pushed Authorization Requests (PAR)

Khi hỗ trợ PAR (RFC 9126), AS có thể công bố `pushed_authorization_request_endpoint` để client biết nơi gửi pushed authorization request.

Tuy nhiên:

- Có field metadata không tự bật PAR filter.
- Client phải được phép sử dụng PAR theo policy.
- Authorization Endpoint phải xử lý `request_uri` đúng ràng buộc.
- Nếu có policy `require_pushed_authorization_requests`, phải đồng bộ giữa client registration và AS thực tế.

### 12.2. Device Authorization

Khi hỗ trợ OAuth 2.0 Device Authorization Grant (RFC 8628), AS có thể công bố `device_authorization_endpoint`. Client thiết bị vẫn phải được đăng ký grant type tương ứng và tuân thủ `interval`/`slow_down`.

Không nhầm `device_authorization_endpoint` (nơi thiết bị nhận device code) với `device_verification_endpoint`/verification URI người dùng mở trên trình duyệt.

### 12.3. DPoP

DPoP (RFC 9449) có metadata capabilities riêng như `dpop_signing_alg_values_supported` theo profile hỗ trợ. Không quảng bá DPoP chỉ vì AS phát JWT; DPoP yêu cầu proof verification, sender-constrained token semantics và Resource Server checks.

### 12.4. mTLS

RFC 8705 định nghĩa metadata bổ sung, bao gồm `mtls_endpoint_aliases` nếu AS cung cấp endpoint aliases dành riêng cho mTLS. Không cần đặt `mtls_endpoint_aliases` nếu deployment không thiết kế các aliases này.

### 12.5. Token Exchange và grant extension

Một grant extension như Token Exchange dùng URI `urn:ietf:params:oauth:grant-type:token-exchange`. Có thể quảng bá trong `grant_types_supported` nếu version và policy thực sự có provider xử lý.

Không tự công bố một grant trong metadata trước khi converter/provider, registration, validation và tests hoàn chỉnh.

### 12.6. Authorization Server Metadata không phải Protected Resource Metadata

RFC 9728 mô tả metadata của Resource Server để client có thông tin về protected resource và những Authorization Servers liên quan. Ví dụ resource có thể quảng bá danh sách `authorization_servers`.

Tuy nhiên:

- OAuth2 AS Metadata RFC 8414 trả capability của **AS**.
- Protected Resource Metadata RFC 9728 trả capability của **RS**.
- Cả hai có trust model và endpoint URLs riêng.

Không đưa field `authorization_servers` của RS vào AS metadata như thay thế `issuer`, cũng không suy luận rằng bất kỳ Authorization Server nào được một RS quảng bá đều được client tự động tin mà không có chính sách trust.

## 13. Bảo mật Discovery: issuer mix-up, endpoint injection và SSRF

### 13.1. Issuer validation là bắt buộc

Quy tắc RFC 8414: sau khi tải metadata, client **phải so `issuer` trong JSON với issuer đã dùng để tạo well-known URL**. Nếu không trùng chính xác, **không được sử dụng metadata**.

Vì sao? Trong hệ thống có nhiều AS, attacker có thể cố gắng khiến client gửi authorization code/token request tới nhầm AS. Issuer check là một hàng rào quan trọng chống mix-up.

### 13.2. Không tự chấp nhận issuer từ nguồn không đáng tin

Sai lầm:

~~~java
// Ý tưởng KHÔNG AN TOÀN:
// Đọc issuer bất kỳ từ HTTP request không được tin cậy,
// tải metadata tại URL đó và lập tức dùng token_endpoint
// / jwks_uri của response để gửi credentials hoặc xác minh token.
~~~

Nếu ứng dụng cho phép user/client nhập issuer tùy ý và máy chủ tự fetch URL, có thể tạo SSRF tới host nội bộ, metadata poisoning hoặc credential exfiltration.

Giải pháp:

- Danh sách issuer tin cậy hoặc quy trình onboarding issuer có phê duyệt.
- Chỉ `https`, xác minh TLS certificate/hostname đầy đủ.
- Giới hạn redirect khi fetch metadata.
- Chặn IP private/loopback/link-local và DNS rebinding theo threat model khi xử lý issuer từ nguồn ngoài.
- Kiểm tra `issuer` exact-match.
- Kiểm soát `authorization_endpoint`, `token_endpoint` và `jwks_uri` theo policy; không gửi client secret tới URL lạ.
- Bảo đảm tenant/client không thể trộn issuer và metadata của môi trường khác.

### 13.3. Metadata không phải chữ ký chứng minh quyền

Metadata là JSON qua HTTPS. Nó không phải access token, không thay chữ ký JWT và không chứng minh rằng một endpoint được phép nhận credentials bất kỳ.

Ngay cả khi `jwks_uri` hợp lệ, Resource Server vẫn phải:

- Xác minh signature của JWT theo key/alg đúng.
- Xác minh `iss` và `aud`.
- Kiểm tra `exp`/`nbf`.
- Kiểm tra scope/authority và policy ứng dụng.
- Nếu token sender-constrained, kiểm tra DPoP/mTLS proof.

### 13.4. Signed metadata là tùy chọn

RFC 8414 có `signed_metadata`: một JWT mang metadata values được ký hoặc MACed.

Những điểm cần nhớ:

- `signed_metadata` **OPTIONAL**, không phải mọi SAS deployment phát field này.
- JWT metadata có `iss` của bên xác nhận metadata.
- Client phải có trust anchor và quy trình xác minh chữ ký thích hợp, không được chấp nhận signed metadata do nguồn bất kỳ tạo.
- Nếu client hỗ trợ signed metadata, RFC 8414 yêu cầu metadata values trong bản ký được ưu tiên so với JSON elements trùng tên.
- Không nhầm `signed_metadata` với `id_token` hoặc access token.
- Không tự bật chữ ký metadata bằng cách gắn một chuỗi JWT custom vào field khi chưa thiết kế trust và signing workflow.

### 13.5. Tránh công bố metadata không đúng hoặc nội bộ

Không công bố:

~~~json
{
  "issuer": "http://auth-service:9000",
  "token_endpoint": "http://10.0.1.42:9000/oauth2/token"
}
~~~

cho clients bên ngoài trong production. Đây là URL nội bộ/HTTP không tương ứng issuer công khai và có thể phá TLS security/trust.

Cũng không công bố private JWK keys, client secrets, database addresses, session keys hoặc admin-only endpoints trong metadata.

## 14. Reverse proxy, forwarded headers và issuer ổn định

### 14.1. Kiến trúc điển hình

~~~mermaid
flowchart LR
    C["OAuth2 Client / Resource Server"]
    LB["HTTPS Reverse Proxy<br/>auth.example.test"]
    AS["Spring Authorization Server<br/>internal auth-service:9000"]

    C -->|"GET metadata HTTPS"| LB
    LB -->|"Forwarded request qua mạng tin cậy"| AS
    AS -->|"JSON issuer & public endpoints"| LB
    LB --> C
~~~

Nếu AS tự dựng URL từ request nội bộ với scheme `http` và host `auth-service:9000`, metadata có thể sai với URL public. Tệ hơn, các JWT nó phát hành có `iss` khác client/RS tin cậy.

### 14.2. Cấu hình issuer rõ ràng

Ưu tiên khai báo:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.test")
        .build();
}
~~~

Không chỉ dựa vào `Host`/`X-Forwarded-Host`/`X-Forwarded-Proto` do request chưa tin cậy cung cấp để xác định issuer.

Nếu ứng dụng cần forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Cần cấu hình proxy tin cậy **xóa forwarded headers từ client** rồi tự chèn giá trị đúng; backend không được công khai trực tiếp nếu ứng dụng tin các header này.

### 14.3. Điều cần kiểm tra sau khi deploy

1. Gọi metadata URL từ bên ngoài qua DNS/TLS thực tế.
2. Kiểm tra `issuer` là public URL đã dự kiến.
3. Kiểm tra mọi endpoint URLs dùng đúng HTTPS/host/path.
4. Kiểm tra `jwks_uri` thực sự trả public keys.
5. Dùng client theo issuer public để lấy token.
6. Kiểm tra JWT `iss` (và ID token `iss` nếu OIDC).
7. Resource Server giải mã token và validate issuer/audience.
8. Kiểm tra forwarded headers spoofing và không thể truy cập backend bypass proxy.

Một metadata endpoint trả HTTP 200 nhưng công bố internal URLs vẫn là lỗi vận hành nghiêm trọng.

### 14.4. Multi-tenant và nhiều issuer

Nếu mỗi tenant có issuer riêng:

~~~text
https://auth.example.test/tenant/a
https://auth.example.test/tenant/b
~~~

Mỗi tenant phải có metadata URL RFC 8414 riêng, `issuer` riêng và endpoint/token policy nhất quán.

Không để tenant A tải metadata tenant B hoặc chấp nhận JWT `iss` của tenant B chỉ vì chung signing key. Cần tách trust/registration/authorization và kiểm thử request routing theo issuer path.

Framework SAS mặc định thường được cấu hình cho một issuer trong một application context; nhiều issuer/path có thể cần routing/configuration bổ sung. Không khẳng định chỉ đổi `AuthorizationServerSettings` trong request là đủ để có multi-issuer an toàn.

## 15. Caching, versioning và backward compatibility

### 15.1. Metadata là cấu hình công khai, có thể cache có kiểm soát

Client SDK có thể cache discovery JSON để không gọi AS trên mọi OAuth2 flow. Proxy/CDN cũng có thể cache response nếu policy cho phép.

Cache cần cân bằng:

| Chính sách | Ưu điểm | Rủi ro |
| --- | --- | --- |
| TTL ngắn | Cập nhật endpoints/capabilities nhanh | Nhiều GET, tăng tải |
| TTL vừa phải | Giảm latency/tải | Có khoảng stale khi thay đổi cấu hình |
| TTL quá dài | Ít request | Client không thấy endpoint/auth method mới, migration chậm |
| ETag/conditional GET | Giảm payload nếu supported | Cần kiểm soát cache revalidation đúng |

Không có TTL bắt buộc duy nhất cho mọi deployment. Chọn TTL theo khả năng thay đổi issuer/endpoints và nhu cầu rollback.

### 15.2. Công bố capability thay đổi có thể làm client gãy

Ví dụ:

- Tắt `client_secret_basic` nhưng client cũ chưa hỗ trợ `private_key_jwt`.
- Thay `token_endpoint` mà client đã cache URL cũ.
- Di chuyển `jwks_uri` mà RS chưa refresh metadata.
- Ngừng một grant nhưng metadata vẫn liệt kê.
- Đổi issuer mà client/RS chỉ trust issuer cũ.
- Đổi `code_challenge_methods_supported` khi client hardcode `plain`.

Khi thay đổi:

1. Kiểm kê consumers và SDK versions.
2. Công bố metadata phù hợp thực tế.
3. Có compatibility window cho endpoints cũ nếu policy cho phép.
4. Đo metadata cache TTL lớn nhất.
5. Theo dõi request tới endpoint cũ và lỗi 4xx.
6. Cập nhật client onboarding docs và integration tests.
7. Không giữ capability yếu chỉ vì metadata cache nếu vi phạm security policy.

### 15.3. Metadata không giải quyết key rotation một mình

Nếu `jwks_uri` giữ nguyên, có thể publish khóa mới trong JWKS mà không đổi metadata. Nhưng RS vẫn cần refresh JWKS khi gặp `kid` mới hoặc hết cache.

Giữ public key cũ trong JWKS đủ lâu để token cũ còn hạn được xác minh theo key rollover policy. Không gỡ khóa cũ chỉ vì JSON metadata đã cập nhật.

## 16. Client sử dụng RFC 8414 thế nào?

### 16.1. Quy trình discovery an toàn

Một OAuth2 Client biết issuer đáng tin cậy:

1. Tạo well-known metadata URL đúng RFC 8414.
2. Gửi HTTPS GET.
3. Kiểm tra HTTP status 200 và `Content-Type: application/json`.
4. Parse JSON object, kiểm tra các trường cần thiết có kiểu dữ liệu đúng.
5. So `issuer` exact-match với issuer đầu vào.
6. Xác minh endpoint URLs phù hợp HTTPS/trust policy.
7. Chọn grant/response type/client auth method mà **cả server lẫn client registration** cùng cho phép.
8. Lấy `jwks_uri` nếu cần xác minh JWT.
9. Cache metadata theo policy và kiểm tra lại khi có thay đổi.
10. Thực hiện Authorization Code + PKCE, Client Credentials, Device Code, v.v. theo grant thực sự được hỗ trợ.

### 16.2. Ví dụ pseudocode client

~~~java
// PSEUDOCODE — không phải API Spring có thể biên dịch trực tiếp.
String trustedIssuer = "https://auth.example.test";

URI metadataUri = deriveRfc8414WellKnownUri(trustedIssuer);
JsonObject metadata = httpGetJsonOverVerifiedTls(metadataUri);

if (!trustedIssuer.equals(metadata.getString("issuer"))) {
    throw new SecurityException("Authorization Server issuer mismatch");
}

URI tokenEndpoint = validateTrustedHttpsEndpoint(
    metadata.getString("token_endpoint"));

List<String> supportedGrants =
    metadata.getStringList("grant_types_supported");

if (!supportedGrants.contains("authorization_code")) {
    throw new IllegalStateException(
        "Authorization Code flow not advertised");
}

// Tiếp tục kiểm tra client registration, PKCE support và
// gửi request theo giao thức; không tự bỏ qua client authentication.
~~~

Hàm `deriveRfc8414WellKnownUri` và `validateTrustedHttpsEndpoint` do ứng dụng/SDK triển khai. Với server không công bố `grant_types_supported`, RFC 8414 có default lịch sử, nên client thực tế phải parse theo profile/version thay vì dùng pseudocode này nguyên xi.

### 16.3. Spring Security OAuth2 Client

Trong Spring Boot, cấu hình client OIDC thường dựa trên issuer:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          booking:
            provider: booking-provider
            client-id: booking-client
            client-secret: __CLIENT_SECRET_FROM_SECRET_MANAGER__
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          booking-provider:
            issuer-uri: https://auth.example.test
~~~

**Phân biệt:** Khi cấu hình `issuer-uri` với OIDC scopes, Spring Security OAuth2 Client có thể sử dụng **OIDC Discovery** `openid-configuration` theo implementation của nó, không mặc định chứng minh SDK đã GET `/.well-known/oauth-authorization-server` theo RFC 8414. Nếu chỉ cần OAuth2 RFC 8414 mà không bật OIDC, hãy kiểm tra capability/version của client SDK và cấu hình endpoint URLs phù hợp.

Ví dụ chỉ minh họa client registration; `__CLIENT_SECRET_FROM_SECRET_MANAGER__` là placeholder, không đặt secret production vào source/config public. Không dùng scope `openid` nếu AS không bật OIDC.

### 16.4. Resource Server dùng issuer discovery

Spring Boot Resource Server thường cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Cấu hình issuer giúp framework tìm JWK Set URI theo discovery phù hợp và tạo validator cho `iss`. Nếu chọn cấu hình `jwk-set-uri` trực tiếp để tránh discovery dependency lúc startup, cần bảo đảm issuer validator vẫn được áp dụng.

**Không suy rằng issuer-uri tự xác minh audience cho mọi API.** Cần cấu hình audience validator theo Spring Security version/policy; Resource Server vẫn phải kiểm tra scopes và business authorization.

## 17. Kiểm thử Metadata Endpoint

### 17.1. Kiểm tra HTTP công khai

~~~bash
curl --fail --silent --show-error \
  --header "Accept: application/json" \
  https://auth.example.test/.well-known/oauth-authorization-server
~~~

Kỳ vọng:

- HTTP 200.
- Content-Type JSON.
- Có `issuer` đúng.
- Có `response_types_supported` và các URL endpoint áp dụng.
- Không redirect sang `/login`.
- Không có internal hosts, private keys hoặc client secrets.

### 17.2. Kiểm tra nhanh bằng jq

~~~bash
curl --silent --show-error \
  https://auth.example.test/.well-known/oauth-authorization-server \
  | jq '{
      issuer,
      authorization_endpoint,
      token_endpoint,
      jwks_uri,
      response_types_supported,
      grant_types_supported,
      code_challenge_methods_supported
    }'
~~~

Không chỉ dựa vào output `jq` hiển thị đẹp; cần test schema, issuer exact-match, endpoints reachable và giao thức thực tế.

### 17.3. MockMvc integration test

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

class AuthorizationServerMetadataTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void oauthMetadataIsPublicAndConsistent() throws Exception {
        mockMvc.perform(get("/.well-known/oauth-authorization-server"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.issuer")
                .value("https://auth.example.test"))
            .andExpect(jsonPath("$.token_endpoint")
                .value("https://auth.example.test/oauth2/token"))
            .andExpect(jsonPath("$.response_types_supported").isArray());
    }
}
~~~

Đây là **test body cốt lõi**; class test cần `@SpringBootTest` và `@AutoConfigureMockMvc` hoặc test setup tương đương để nạp SecurityFilterChain AS thật. Nếu issuer được xác định từ request/proxy trong cấu hình test, cần đặt host/scheme hoặc dùng explicit issuer bean cho fixture.

### 17.4. Test `jwks_uri`

Nếu metadata có `jwks_uri`:

1. Truy xuất HTTPS GET.
2. Parse JWK Set có field `keys` dạng array.
3. Xác nhận các JWK ký có public key material và `kid` phù hợp.
4. Xác nhận không có tham số private key như RSA `d`, `p`, `q`.
5. Tạo JWT từ AS test fixture và xác minh chữ ký với key công bố.
6. Kiểm tra issuer/audience/expiry sau khi decode JWT.
7. Kiểm tra key rotation có overlap và consumer refresh JWKS.

Nếu không có `JWKSource<SecurityContext>` bean thì SAS mặc định không cấu hình JWK Set Endpoint; không ghi `jwks_uri` giả trong metadata.

### 17.5. Ma trận kiểm thử

| Ca | Input/Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Basic discovery | GET đúng well-known | 200 JSON |
| Anonymous discovery | Không cookie/token | Không redirect login |
| Issuer exact match | Trusted issuer = response issuer | Client chấp nhận metadata |
| Issuer mismatch | Response issuer khác | Client từ chối |
| Issuer có path | `/tenant/a` | Well-known đặt trước issuer path |
| Internal host leak | Proxy HTTP backend | Metadata không công bố internal host |
| Endpoint reachable | URL token/authorization/introspection | Đúng routing/policy |
| PKCE metadata | AS hỗ trợ S256 | `code_challenge_methods_supported` có S256 |
| Capability mismatch | Metadata quảng bá grant chưa hỗ trợ | Test fail |
| Client permission | AS hỗ trợ grant nhưng client không đăng ký | Client vẫn bị từ chối grant |
| JWK Set | Có `jwks_uri` | Chỉ public keys, verify JWT được |
| JWK Set disabled | Không có JWKSource | Không quảng bá key endpoint giả |
| OIDC disabled | OAuth2 metadata hoạt động | Không suy OIDC provider config |
| OIDC enabled | `OidcConfigurer` active | OIDC config hoạt động riêng |
| Metadata caching | CDN giữ bản cũ | Refresh/TTL tương thích rollout |
| Wrong content type | HTML/redirect | Client không parse như JSON |
| SSRF input | Issuer do user nhập ngoài allowlist | Không fetch địa chỉ không tin cậy |
| Multi-instance | Nhiều AS pods | Metadata thống nhất |
| Multi-tenant | Issuer A/B khác | Không trộn issuer/metadata |
| Unknown extension | Field mới không được client hiểu | Client xử lý theo profile, không tự bật quyền |
| Signing metadata | `signed_metadata` optional | Chỉ trust khi verify đúng signer/contract |

### 17.6. Test end-to-end cùng client thật

Một integration test có giá trị hơn chỉ so JSON:

1. Lấy metadata qua public HTTPS.
2. Chọn Authorization Endpoint từ metadata.
3. Bắt đầu Authorization Code + PKCE với client đã đăng ký.
4. Đổi code tại Token Endpoint từ metadata.
5. Nếu cần, lấy JWKS từ `jwks_uri` và xác minh access token/ID token.
6. Gửi token tới RS và xác minh issuer/audience/scopes.
7. Đổi địa chỉ endpoint trong test profile và xác minh client thích ứng đúng policy.

Không dùng `@WithMockUser` để khẳng định metadata client authentication đúng: metadata vốn không cần Resource Owner login. Cần HTTP test qua filter/proxy thực tế.

## 18. Vận hành và troubleshooting

### 18.1. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách kiểm tra |
| --- | --- | --- |
| GET well-known trả 404 | Sai path, AS chain không match, proxy rewrite sai | Routing/filter chain/issuer path |
| GET well-known trả 302 /login | Application chain bắt trước, security rule sai | `@Order`, matcher và filters |
| JSON `issuer` thành localhost | Không cấu hình issuer hoặc forwarded headers sai | `AuthorizationServerSettings.issuer` |
| JSON endpoint dùng HTTP nội bộ | Proxy offload TLS nhưng AS dựng URL nội bộ | Issuer, proxy trust, public URL |
| Client báo issuer mismatch | Metadata issuer khác issuer đã pin | So chuỗi exact, scheme/host/path |
| Client báo metadata invalid | Thiếu required field, JSON type sai | RFC schema và customizer |
| Client chọn grant không dùng được | Metadata quảng bá server-wide nhưng client registration thiếu | RegisteredClient/grant policy |
| Client POST Token Endpoint sai | Endpoint từ metadata không reachable/route sai | External URL, DNS, TLS |
| Resource Server không load key | `jwks_uri` thiếu, JWKSource bean không có, network lỗi | JWK endpoint/JWT decoder |
| RS 401 dù key đúng | JWT issuer/audience/expiry sai | JwtDecoder validators |
| OIDC client fail nhưng OAuth2 metadata OK | OIDC config disabled hoặc path khác | `OidcConfigurer`/openid-configuration |
| Chỉ tenant B fail discovery | Path insertion/routing của tenant B sai | RFC 8414 URL per issuer |
| Metadata có registration URL nhưng 404 | Công bố endpoint chưa bật | Dynamic registration config |
| Metadata cũ sau deploy | CDN/client cache quá dài | Cache-Control/ETag/purge/SDK refresh |
| OAuth2 client cho phép SSRF | Issuer URL không hạn chế | Issuer allowlist/trust/onboarding |
| Metadata thay đổi giữa instances | Config khác nhau, rolling deployment | Issuer/settings consistency |

### 18.2. Runbook chẩn đoán theo thứ tự

1. Xác định issuer tin cậy mà client/RS dùng.
2. Tạo đúng well-known URL theo RFC 8414.
3. Gọi URL qua DNS/TLS/public proxy thực tế.
4. Kiểm tra HTTP 200, Content-Type, JSON và `issuer` exact-match.
5. Kiểm tra URL các endpoints, grant types, PKCE, auth methods và JWKS.
6. Kiểm tra AS SecurityFilterChain và `AuthorizationServerSettings`.
7. Kiểm tra OIDC Discovery riêng nếu client yêu cầu `openid`.
8. Kiểm tra cache local/CDN và tình trạng rollout.
9. Test một request OAuth2 thật qua các endpoint được quảng bá.
10. Nếu RS từ chối token, chẩn đoán độc lập JWT signature/issuer/audience/expiry và client authorization.

### 18.3. Metrics và alert

| Metric | Dùng để phát hiện |
| --- | --- |
| Metadata GET volume/latency | Discovery load, proxy failure |
| Metadata 4xx/5xx | Sai routing, availability |
| Metadata issuer mismatch trong client integration | Cấu hình security identity sai |
| Client startup discovery failures | Startup dependency/DNS/TLS |
| JWKS GET/refresh failure | Key distribution errors |
| Endpoint 404 sau metadata success | Capability/URL mismatch |
| OIDC discovery errors | OIDC activation/path mismatch |
| Multi-instance metadata drift | Deployment/settings không đồng bộ |
| CDN Age và metadata cache refresh | Stale configuration |

Không ghi client secret, access token hoặc raw authorization header vào log/metrics. Metadata là thông tin công khai nhưng `issuer`/endpoint URLs cần được kiểm soát theo change management.

## 19. Các sai lầm thiết kế cần tránh

| Sai lầm | Hậu quả | Nguyên tắc đúng |
| --- | --- | --- |
| Đoán issuer từ Token Endpoint | Có thể sai khi multi-tenant/proxy | Issuer phải đến từ trust config |
| Bỏ check `issuer` sau discovery | AS mix-up/metadata injection | Exact-match theo RFC 8414 |
| Ghép `issuer + "/.well-known/..."` khi issuer có path | Sai well-known URL | Chèn suffix giữa host và issuer path |
| Nhầm OAuth2 metadata với OIDC config | Client login/ID token fail | Dùng profile đúng, bật OIDC khi cần |
| Công bố JWKS trong metadata | Lộ key hoặc sai contract | Metadata chứa `jwks_uri`, JWKS chứa public keys |
| Công bố private JWK | Lộ signing key | Chỉ công bố public key |
| Công bố `registration_endpoint` chưa bật | Client nhận 404 hoặc lỗi bảo mật | Metadata phản ánh endpoint thật |
| Công bố grant chưa có provider | Client gọi grant sai | Kiểm tra implementation/capability |
| Xem `grant_types_supported` là quyền của mọi client | Bỏ qua RegisteredClient policy | Client registration vẫn kiểm soát quyền |
| Không công bố PKCE S256 dù hỗ trợ | Client SDK có thể cấu hình sai | Metadata đúng với protocol |
| Dùng HTTP/internal host trong production | Sai trust/issuer và phá client | HTTPS public issuer cố định |
| Tin forwarded headers từ internet | Host/issuer poisoning | Proxy tin cậy strip/set headers |
| Fetch issuer tùy ý từ user | SSRF/credential leak | Issuer allowlist hoặc onboarding kiểm soát |
| Xem metadata là authorization | Bỏ client authentication/consent | Metadata chỉ mô tả capabilities |
| Đổi issuer mà không migrate client/RS | JWT `iss` mismatch, login fail | Kế hoạch issuer migration |
| Cache metadata vô hạn | Endpoint/capability cũ tồn tại lâu | TTL, revalidation và rollout plan |
| Coi `signed_metadata` là luôn có | Client không tương thích | Optional, có trust model rõ |
| Chỉ test HTTP 200 | Metadata có thể sai issuer/URL | Validate schema, HTTPS, issuer và flow thực |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** RFC 8414 dùng để làm gì?

**Đáp án:** Công bố metadata JSON chuẩn để OAuth2 Client tìm endpoint URLs và capability của Authorization Server gắn với một issuer tin cậy.

**Câu 2.** Issuer `https://auth.example.test/tenant/a` có metadata URL nào theo RFC 8414?

**Đáp án:** `https://auth.example.test/.well-known/oauth-authorization-server/tenant/a`, không phải suffix đặt sau path tenant.

**Câu 3.** Vì sao phải so exact-match `issuer` sau khi tải metadata?

**Đáp án:** Để tránh dùng metadata của AS khác, giảm nguy cơ authorization server mix-up và credential/authorization code gửi sai đích.

**Câu 4.** `grant_types_supported` có cho phép mọi RegisteredClient dùng tất cả grant được liệt kê không?

**Đáp án:** Không. Đây là khả năng server. Mỗi client còn chịu `RegisteredClient.authorizationGrantTypes` và policy riêng.

**Câu 5.** `jwks_uri` và `issuer` có vai trò giống nhau không?

**Đáp án:** Không. `issuer` là định danh AS; `jwks_uri` là URL lấy public keys để xác minh JWT. Public keys không thay issuer validation.

**Câu 6.** RFC 8414 có bắt buộc `jwks_uri` không?

**Đáp án:** Không, `jwks_uri` là OPTIONAL trong chính RFC 8414; các profile như OIDC và nhu cầu JWT validation có yêu cầu riêng.

**Câu 7.** Nếu `grant_types_supported` bị bỏ qua, RFC 8414 có default gì?

**Đáp án:** `authorization_code` và `implicit` là default lịch sử theo RFC. Không nên vì vậy mà tự bật implicit trong hệ thống mới.

**Câu 8.** Có thể tùy biến metadata bằng cách viết controller mới không?

**Đáp án:** Spring Authorization Server đã có `OAuth2AuthorizationServerMetadataEndpointConfigurer` và customizer. Nên dùng DSL/builder để giữ metadata đồng bộ thay vì tạo controller song song.

**Câu 9.** OAuth2 Metadata Endpoint và OIDC Provider Configuration Endpoint có tự cùng bật không?

**Đáp án:** Không. SAS bật OAuth2 metadata theo cấu hình Authorization Server, nhưng OIDC disabled mặc định và phải được bật riêng.

**Câu 10.** Vì sao reverse proxy có thể làm metadata sai dù endpoint trả 200?

**Đáp án:** Nếu issuer/endpoint URLs được dựng từ internal HTTP host/scheme hoặc forwarded headers không tin cậy, JSON có thể công bố URL sai.

**Câu 11.** Metadata cache và JWKS cache có phải một không?

**Đáp án:** Không. Metadata chứa endpoint/key-set URI; JWKS chứa public keys. Cả hai có TTL và refresh độc lập.

**Câu 12.** Có nên để client tải metadata từ issuer do người dùng nhập tùy ý không?

**Đáp án:** Không nên khi chưa có trust/onboarding policy vì có SSRF, endpoint injection và credential leak; cần allowlist/validation/TLS/issuer exact-match.

## 21. Checklist triển khai production

- [ ] Có issuer HTTPS ổn định, không chứa query/fragment và khớp identity của AS.
- [ ] Well-known URL được tạo đúng RFC 8414, kể cả issuer chứa path.
- [ ] GET metadata trả HTTP 200, `application/json`, không redirect login.
- [ ] `issuer` trong JSON khớp chính xác issuer tin cậy.
- [ ] Các endpoint URLs công bố là URL public HTTPS thực sự hoạt động.
- [ ] `response_types_supported` và các field bắt buộc theo profile đầy đủ.
- [ ] `grant_types_supported`, client auth methods, PKCE phản ánh implementation thật.
- [ ] `scopes_supported` không bị hiểu nhầm là quyền của mọi client.
- [ ] `jwks_uri` có public JWK Set, không lộ private key.
- [ ] JWK Set endpoint chỉ được công bố khi có cấu hình keys tương ứng.
- [ ] OIDC Provider Configuration được bật riêng nếu có OIDC; không nhầm hai URL.
- [ ] Dynamic Client Registration chỉ được quảng bá khi thực sự bật.
- [ ] PAR/Device/DPoP/mTLS metadata chỉ quảng bá nếu feature đang hoạt động.
- [ ] `AuthorizationServerSettings` được cấu hình issuer/endpoint paths chính xác.
- [ ] AS SecurityFilterChain bắt metadata request đúng trước application chain.
- [ ] Proxy xóa forwarded headers không tin cậy và giữ HTTPS external URLs.
- [ ] Có kế hoạch cache TTL, refresh, rollout và rollback endpoint/capability changes.
- [ ] Có tests cho exact issuer match, well-known path, JSON fields, JWKS, OIDC và flow thực.
- [ ] Có kiểm soát issuer từ nguồn ngoài để ngăn SSRF và mix-up.
- [ ] Có monitoring cho discovery failures, issuer mismatch, endpoint 404, cache drift.
- [ ] Không nhầm metadata discovery với client authentication hoặc authorization.

## 22. Tài liệu tham khảo và kết luận

Tài liệu chuẩn và chính thức:

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8414, Section 2 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414#section-2)
- [RFC 8414, Section 3 — Obtaining Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414#section-3)
- [RFC 8414, Section 3.3 — Metadata Validation](https://www.rfc-editor.org/rfc/rfc8414#section-3.3)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8705 — Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9126 — Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126)
- [RFC 9449 — Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)

**Kết luận:** RFC 8414 chuẩn hóa cách OAuth2 Client khám phá issuer, endpoint URLs và capability của Authorization Server qua JSON tại một well-known URL. Giá trị bảo mật quan trọng nhất là **issuer nhất quán và được kiểm tra chính xác**, chứ không chỉ là giảm các URL hardcode. Trong Spring Authorization Server, `AuthorizationServerSettings` xác định issuer/endpoint và `OAuth2AuthorizationServerMetadataEndpointConfigurer` tùy biến response. Khi triển khai thực tế, phải phối hợp Discovery với HTTPS, reverse proxy, client registration, JWKS, OIDC profile, metadata cache và integration tests. Metadata đúng giúp client tích hợp dễ dàng hơn mà không làm giảm yêu cầu xác thực và phân quyền của OAuth 2.0/OpenID Connect.

