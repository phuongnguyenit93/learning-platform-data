# Tùy chỉnh metadata của Authorization Server và OpenID Provider

## 1. Mục tiêu và tình huống thực tế

Trong mô-đun **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta thiết kế, cấu hình, bảo mật, kiểm thử và vận hành **OAuth 2.0/OpenID Connect Authorization Server** bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**. Khi một OAuth client hoặc OpenID Connect Relying Party cần kết nối với server, nó không nên phải đoán đường dẫn Token Endpoint, JWK Set Endpoint, phương thức xác thực client hay thuật toán ký ID Token.

**Metadata và Discovery** giải quyết vấn đề đó: Authorization Server công bố một tài liệu JSON máy đọc được, chứa các endpoint và khả năng giao thức mà nó thực sự hỗ trợ. Client chỉ cần biết issuer đáng tin cậy cùng các quy tắc discovery tương ứng để lấy thông tin cấu hình.

Ví dụ xuyên suốt: doanh nghiệp vận hành Authorization Server tại <code>https://auth.example.com</code>, cung cấp OAuth 2.0 cho API và OpenID Connect cho ứng dụng web. Bộ phận pháp chế yêu cầu công bố URL chính sách và điều khoản; bộ phận developer relations muốn công bố URL tài liệu; hệ thống đứng sau reverse proxy nên public issuer/endpoint phải dùng HTTPS và hostname bên ngoài, không được trỏ về <code>localhost:9000</code>. Ta sẽ cấu hình:

- **OAuth 2.0 Authorization Server Metadata** theo **RFC 8414**.
- **OpenID Provider Configuration** theo **OpenID Connect Discovery 1.0**.
- Điểm mở rộng Java DSL của **Spring Authorization Server 1.5.x** để thêm metadata mà không viết lại hai endpoint.
- Kiểm thử để chứng minh thông tin công bố khớp với tính năng đang chạy.

Sau bài học, bạn có thể:

1. Phân biệt hai tài liệu metadata, vị trí lấy chúng và các trường bắt buộc.
2. Giải thích vai trò của <code>issuer</code>, <code>authorization_endpoint</code>, <code>token_endpoint</code>, <code>jwks_uri</code>, phương thức xác thực và thuật toán được quảng bá.
3. Dùng <code>AuthorizationServerSettings</code> để khai báo issuer/endpoint thay vì thay chuỗi JSON thủ công.
4. Dùng <code>authorizationServerMetadataCustomizer(...)</code> để tùy chỉnh OAuth metadata.
5. Dùng <code>providerConfigurationCustomizer(...)</code> để tùy chỉnh OpenID Provider metadata.
6. Thêm những thuộc tính tùy chọn hữu ích mà không công bố tính năng chưa triển khai.
7. Xử lý public URL sau reverse proxy, nhiều tenant/issuer, JWKS, TLS, cache và key rotation.
8. Tạo contract test cho discovery, kiểm thử tính nhất quán giữa metadata và hành vi thực tế.

**Phạm vi phiên bản:** Ví dụ dùng Spring Authorization Server **1.5.x**, Spring Security **6.x** và Spring Boot Servlet stack. Các phiên bản Spring Security tích hợp Authorization Server trong package khác có thể dùng DSL khác. Khi nâng version, kiểm tra lại Javadoc và contract test trước khi đưa vào production.

## 2. Hai chuẩn metadata không nên đánh đồng

### 2.1. OAuth 2.0 Authorization Server Metadata — RFC 8414

RFC 8414 định nghĩa metadata cho OAuth 2.0 Authorization Server, thường được lấy tại:

~~~http
GET /.well-known/oauth-authorization-server HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

Ví dụ JSON minh họa một deployment cụ thể:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "response_types_supported": ["code"],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": ["S256"],
  "service_documentation": "https://auth.example.com/docs/oauth"
}
~~~

Đây **không phải response mặc định bảo đảm xuất hiện** với mọi phiên bản Spring Authorization Server. Những giá trị trong ví dụ chỉ hợp lệ nếu server đã cấu hình và thực sự hỗ trợ các grant, phương thức xác thực, PKCE và endpoints đó.

Tài liệu RFC 8414 giúp OAuth client biết thông tin kết nối: authorization endpoint, token endpoint, grant/response type, client authentication, JWK Set và các khả năng mở rộng.

### 2.2. OpenID Provider Configuration — OpenID Connect Discovery

OpenID Connect bổ sung **authentication layer** bên trên OAuth 2.0. Khi OIDC được bật, OpenID Provider (OP) công bố một tài liệu discovery riêng, thường tại:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

Ví dụ:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "userinfo_endpoint": "https://auth.example.com/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile"],
  "claims_supported": ["sub", "name"],
  "op_policy_uri": "https://auth.example.com/legal/privacy",
  "op_tos_uri": "https://auth.example.com/legal/terms"
}
~~~

Các trường <code>subject_types_supported</code> và <code>id_token_signing_alg_values_supported</code> liên quan trực tiếp đến **ID Token** và danh tính End-User. <code>userinfo_endpoint</code>, <code>scopes_supported</code> và <code>claims_supported</code> phải phản ánh hành vi OIDC thực tế, không được công bố chỉ vì một SDK muốn nhìn thấy chúng.

### 2.3. So sánh nhanh

| Khía cạnh | OAuth Authorization Server Metadata | OpenID Provider Configuration |
| --- | --- | --- |
| Chuẩn chính | RFC 8414 | OpenID Connect Discovery 1.0 |
| Well-known phổ biến với issuer gốc | <code>/.well-known/oauth-authorization-server</code> | <code>/.well-known/openid-configuration</code> |
| Khách hàng chính | OAuth client, công cụ cấu hình OAuth | OIDC Relying Party, ứng dụng đăng nhập |
| Trường liên quan OAuth | Issuer, authorization/token/JWKS endpoint, grants, client authentication | Nhiều trường OAuth chung |
| Trường OIDC đặc thù | Không bắt buộc ID Token/subject type | Subject type, ID Token signing algorithms, UserInfo, OIDC claims |
| Cấu hình Spring | <code>authorizationServerMetadataEndpoint(...)</code> | <code>oidc(...).providerConfigurationEndpoint(...)</code> |
| Trạng thái mặc định trong Spring Authorization Server 1.5.x | Endpoint OAuth metadata có trong cấu hình mặc định | **OIDC phải được bật tường minh** |

Đừng dùng OAuth metadata để suy ra hệ thống đã hỗ trợ OIDC. Một server chỉ phát access token cho service-to-service có thể là OAuth Authorization Server hợp lệ nhưng không phải OpenID Provider.

## 3. Discovery hoạt động như thế nào?

### 3.1. Luồng cơ bản

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth/OIDC Client
    participant M as Metadata Endpoint
    participant J as JWKS Endpoint
    participant A as Authorization/Token Endpoint
    C->>C: Biết issuer đáng tin cậy từ cấu hình
    C->>M: GET /.well-known/openid-configuration hoặc OAuth metadata
    M-->>C: JSON issuer + endpoint URLs + capabilities
    C->>C: Kiểm tra issuer khớp chính xác và kiểm tra metadata
    C->>J: GET jwks_uri (nếu cần xác minh JWT)
    J-->>C: Public JWK Set
    C->>A: Thực hiện grant hoặc OIDC flow phù hợp
    A-->>C: Authorization response / token response
    C->>C: Kiểm tra token theo issuer, audience, chữ ký, thời hạn
~~~

Client phải biết **issuer tin cậy từ trước**, ví dụ qua cấu hình quản trị. Không tự chấp nhận issuer do một token chưa xác minh, redirect không tin cậy hoặc thông tin người dùng nhập tùy ý cung cấp.

### 3.2. Metadata là hợp đồng mô tả, không phải cơ chế thực thi

Ví dụ, thêm chuỗi <code>private_key_jwt</code> vào <code>token_endpoint_auth_methods_supported</code> **không tự triển khai** xác thực JWT client. Ghi <code>authorization_code</code> vào <code>grant_types_supported</code> không tự sinh Authorization Endpoint hay consent flow.

Ngược lại, nếu server đã hỗ trợ một tính năng nhưng metadata không công bố chính xác, một số client thư viện có thể không cấu hình được hoặc chọn sai flow.

**Nguyên tắc:** <code>capabilities_advertised ⊆ capabilities_implemented_and_enabled</code>. Phần còn lại do security configuration, client registration, grant provider và token generator thực thi.

### 3.3. Cấu hình per-client và metadata toàn server là hai lớp khác nhau

Metadata công bố một **tập các khả năng chung** của Authorization Server. Một <code>RegisteredClient</code> riêng vẫn phải được phép dùng grant, redirect URI, scope và phương thức xác thực tương ứng.

Ví dụ:

- Server công bố hỗ trợ <code>authorization_code</code> và <code>client_credentials</code>.
- <code>orders-web</code> chỉ được đăng ký <code>authorization_code</code> + PKCE.
- <code>orders-worker</code> chỉ được đăng ký <code>client_credentials</code>.

Không có nghĩa <code>orders-web</code> có thể tự dùng Client Credentials vì metadata liệt kê grant này. Runtime vẫn phải kiểm tra RegisteredClient.

## 4. Các trường quan trọng và điều kiện công bố

### 4.1. Bảng trường OAuth metadata

| Trường | Ý nghĩa | Cần kiểm tra |
| --- | --- | --- |
| <code>issuer</code> | Định danh HTTPS của Authorization Server. | Trùng issuer dùng ký/phát token và giá trị client đã tin. |
| <code>authorization_endpoint</code> | URL gửi authorization request. | Endpoint có thực, hoạt động và dùng public HTTPS URL. |
| <code>token_endpoint</code> | URL đổi grant lấy token. | Đúng đường dẫn và chính sách client auth. |
| <code>jwks_uri</code> | URL công bố public signing keys. | Có endpoint, public keys đúng, không rò private JWK. |
| <code>response_types_supported</code> | Response types mà Authorization Server hỗ trợ. | Không công bố implicit/hybrid nếu chưa triển khai. |
| <code>grant_types_supported</code> | Các OAuth grant type được hỗ trợ. | Khớp converter/provider đã bật. |
| <code>token_endpoint_auth_methods_supported</code> | Cách client xác thực tại Token Endpoint. | Khớp các provider/client auth methods thực tế. |
| <code>code_challenge_methods_supported</code> | PKCE code challenge methods. | Ưu tiên <code>S256</code>; không công bố method chưa chấp nhận. |
| <code>scopes_supported</code> | Tập scope được server công bố hỗ trợ. | Không phải các scope một client đã được cấp. |
| <code>revocation_endpoint</code> | URL thu hồi token. | Endpoint và chính sách xác thực đúng. |
| <code>introspection_endpoint</code> | URL hỏi token active hay không. | Bảo vệ client xác thực introspection. |
| <code>service_documentation</code> | URL tài liệu của dịch vụ (metadata tùy chọn theo RFC 8414). | Đúng HTTPS URL và luôn công khai được. |

Các trường tùy chọn không nhất thiết có trong mọi bản triển khai. Metadata còn có thể mô tả PAR, Device Authorization, token exchange, mTLS, DPoP hoặc cơ chế khác tùy thư viện và version. Mỗi tính năng chỉ nên được công bố sau khi đã có integration test tương ứng.

### 4.2. Trường bắt buộc theo builder của Spring Authorization Server 1.5.8

Ở API Spring Authorization Server 1.5.8, <code>OAuth2AuthorizationServerMetadata.Builder</code> kiểm tra có:

- <code>issuer</code>
- <code>authorization_endpoint</code>
- <code>token_endpoint</code>
- <code>response_types_supported</code>

Đây là yêu cầu validation của **builder trong framework**; khi đọc chuẩn RFC, vẫn phải xét semantics và các ngoại lệ/điều kiện riêng của profile. Không cố xóa trường bắt buộc trong customizer rồi trả JSON tùy ý.

### 4.3. Trường bắt buộc trong OpenID Provider Configuration

<code>OidcProviderConfiguration.Builder</code> trong Spring Authorization Server 1.5.8 cần:

- <code>issuer</code>
- <code>authorization_endpoint</code>
- <code>token_endpoint</code>
- <code>jwks_uri</code>
- <code>response_types_supported</code>
- <code>subject_types_supported</code>
- <code>id_token_signing_alg_values_supported</code>

Đây là lý do không thể đơn giản bật OIDC nhưng không có signing key/JWK Set phù hợp rồi giả định mọi OIDC client sẽ hoạt động.

### 4.4. Trường nhạy cảm về ngữ nghĩa bảo mật

Một vài thay đổi metadata có tác động vượt khỏi việc “hiển thị tài liệu”:

1. Đổi <code>issuer</code> có thể làm token bị Resource Server/OIDC Client từ chối vì <code>iss</code> không trùng.
2. Đổi <code>jwks_uri</code> có thể khiến client tải key từ nguồn khác; nếu nguồn không được quản trị, nguy cơ key substitution.
3. Công bố <code>id_token_signing_alg_values_supported</code> có thuật toán không thực sự dùng có thể gây lỗi xác minh hoặc suy giảm chính sách.
4. Công bố <code>grant_types_supported</code> có grant yếu hoặc chưa bật có thể làm client chọn sai flow.
5. Công bố <code>userinfo_endpoint</code> nhưng không có UserInfo endpoint hoạt động khiến OIDC login/profile flow lỗi.

## 5. AuthorizationServerSettings là nguồn cấu hình chuẩn

### 5.1. Khai báo public issuer rõ ràng

Spring Authorization Server có bean <code>AuthorizationServerSettings</code> dùng để thiết lập issuer và các đường dẫn endpoint.

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .authorizationEndpoint("/oauth2/authorize")
        .tokenEndpoint("/oauth2/token")
        .jwkSetEndpoint("/oauth2/jwks")
        .build();
}
~~~

Các path ở đây được khai báo để minh họa; trong nhiều cấu hình chúng đã là mặc định. Giá trị <code>issuer</code> phải là URL công khai ổn định mà client và Resource Server tin cậy. Không dùng URL nội bộ kiểu <code>http://auth-service:9000</code> nếu bên ngoài chỉ biết <code>https://auth.example.com</code>.

### 5.2. Khác nhau giữa cấu hình endpoint và metadata customizer

| Muốn làm gì? | Nơi cấu hình chính |
| --- | --- |
| Đổi public issuer | <code>AuthorizationServerSettings.issuer(...)</code>. |
| Đổi đường dẫn thực của Token Endpoint | <code>AuthorizationServerSettings.tokenEndpoint(...)</code>. |
| Đổi đường dẫn thực của JWK Set Endpoint | <code>AuthorizationServerSettings.jwkSetEndpoint(...)</code>. |
| Bật OIDC | <code>OAuth2AuthorizationServerConfigurer.oidc(...)</code>. |
| Thêm đường dẫn chính sách của OP vào JSON | <code>providerConfigurationCustomizer(...)</code>. |
| Thêm URL tài liệu vào OAuth metadata | <code>authorizationServerMetadataCustomizer(...)</code>. |
| Thêm grant thật | Converter/provider, RegisteredClient policy và các thành phần grant; metadata chỉ phản ánh kết quả. |

**Không thay <code>token_endpoint</code> bằng metadata customizer để “đổi route”.** Điều đó chỉ công bố URL mới trong JSON; nếu filter thật vẫn lắng nghe path cũ thì client bị dẫn tới 404 hoặc một endpoint sai.

### 5.3. Vì sao không để issuer tự suy ra từ request tùy ý?

Trong môi trường sau load balancer/reverse proxy, request đến backend có thể mang Host hoặc Forwarded header. Nếu ứng dụng tự tin mọi giá trị do caller gửi mà tạo <code>issuer</code>, attacker có thể tìm cách gây **issuer confusion** hoặc làm metadata chứa hostname không mong muốn.

Ưu tiên cấu hình issuer tĩnh cho một Authorization Server có public hostname cố định. Nếu thật sự hỗ trợ multi-tenant/multi-issuer, phải chọn issuer theo tenant từ một registry đáng tin cậy; không biến Host header bất kỳ thành issuer hợp lệ.

## 6. Tùy chỉnh OAuth Authorization Server Metadata

### 6.1. API chính thức trong Spring Authorization Server 1.5.x

<code>OAuth2AuthorizationServerMetadataEndpointConfigurer</code> cung cấp:

~~~java
authorizationServerMetadataEndpoint(metadata -> metadata
    .authorizationServerMetadataCustomizer(
        authorizationServerMetadataBuilder -> {
            // Tùy chỉnh các claims trong OAuth2AuthorizationServerMetadata.
        }));
~~~

Callback nhận <code>OAuth2AuthorizationServerMetadata.Builder</code>. Builder có các API cho metadata chuẩn và phương thức <code>claim(...)</code>/<code>claims(...)</code> để tùy chỉnh thêm. Framework vẫn xây metadata mặc định, cho phép bạn bổ sung trường mà không phải viết một HTTP controller trả JSON riêng.

### 6.2. Ví dụ thêm service_documentation

~~~java
Consumer<OAuth2AuthorizationServerMetadata.Builder> oauthMetadataCustomizer =
    builder -> builder.claim(
        "service_documentation",
        "https://auth.example.com/docs/oauth");
~~~

Đây là tùy chỉnh ít rủi ro: <code>service_documentation</code> là metadata tùy chọn theo RFC 8414. URL phải có thật và chứa tài liệu công khai phù hợp. Nếu cần thêm metadata riêng của tổ chức, đặt tên không xung đột với trường chuẩn và tài liệu hóa semantics cho consumer.

### 6.3. Thêm hoặc sửa một capability chỉ khi đã triển khai

Builder có các API cho scope, grant, client authentication method và các thuộc tính khác. Ví dụ minh họa:

~~~java
builder.scope("orders.read");
builder.claim(
    "service_documentation",
    "https://auth.example.com/docs/oauth");
~~~

Chỉ công bố <code>orders.read</code> nếu hệ thống thực sự cấp và chấp nhận scope này theo policy. Gọi <code>scope(...)</code> không đăng ký scope cho từng RegisteredClient, không tạo Resource Server và không cấp bất kỳ quyền nào.

Nếu phải điều chỉnh một danh sách hỗ trợ, phải kiểm tra **giá trị mặc định đang có**, phương thức builder chính xác và kết quả JSON sau build. Không tự ghi đè toàn bộ <code>grant_types_supported</code> bằng danh sách hard-code vì rất dễ làm mất grant mặc định hoặc công bố giá trị không đúng.

## 7. Tùy chỉnh OpenID Provider Configuration

### 7.1. API chính thức

Khi OIDC được bật, <code>OidcProviderConfigurationEndpointConfigurer</code> cung cấp:

~~~java
oidc(oidc -> oidc
    .providerConfigurationEndpoint(provider -> provider
        .providerConfigurationCustomizer(
            providerConfigurationBuilder -> {
                // Tùy chỉnh OpenID Provider Configuration claims.
            })));
~~~

Callback nhận <code>OidcProviderConfiguration.Builder</code>. Tương tự OAuth metadata builder, nó có các method cho endpoint, signing algorithms, subject types và <code>claim(...)</code> cho trường tùy chọn.

### 7.2. Ví dụ chính sách và điều khoản

~~~java
Consumer<OidcProviderConfiguration.Builder> oidcMetadataCustomizer =
    builder -> {
        builder.claim(
            "op_policy_uri",
            "https://auth.example.com/legal/privacy");
        builder.claim(
            "op_tos_uri",
            "https://auth.example.com/legal/terms");
    };
~~~

Hai trường này thuộc OpenID Provider Configuration và có mục đích tài liệu/pháp lý. Chúng không tạo màn hình consent, không khiến tất cả client tự chấp nhận điều khoản, và không tự cung cấp UserInfo.

### 7.3. Quảng bá claims_supported có điều kiện

<code>claims_supported</code> mô tả những claim OP **có thể cung cấp** trong các bối cảnh OIDC thích hợp. Chẳng hạn, nếu hệ thống đã thực sự hỗ trợ <code>sub</code>, <code>name</code> và <code>email</code> theo scope, consent và policy:

~~~java
builder.claim(
    "claims_supported",
    List.of("sub", "name", "email"));
~~~

Đừng thêm <code>email_verified</code>, <code>phone_number</code>, <code>address</code>, <code>acr</code> hoặc <code>amr</code> chỉ để tương thích một client nếu server không tạo được các claim có ngữ nghĩa đáng tin cậy. Có tên claim trong metadata không bảo đảm claim đó xuất hiện ở mọi ID Token hoặc UserInfo response.

### 7.4. Subject type và thuật toán ký ID Token

OIDC yêu cầu metadata cho:

- <code>subject_types_supported</code>, thường gồm <code>public</code>; <code>pairwise</code> chỉ công bố nếu OP đã có cơ chế pairwise subject identifier thực sự.
- <code>id_token_signing_alg_values_supported</code>, ví dụ <code>RS256</code> nếu ID Token thực tế được ký bằng RS256.

Builder của Spring Authorization Server cung cấp các phương thức phù hợp như <code>subjectType(...)</code>, <code>subjectTypes(...)</code>, <code>idTokenSigningAlgorithm(...)</code> và <code>idTokenSigningAlgorithms(...)</code>. Các phương thức dạng số nhiều cho phép điều chỉnh danh sách hiện có, nên cần tránh xóa giá trị bắt buộc hoặc quảng bá thuật toán mà <code>JwtEncoder</code>/JWKSource không hỗ trợ.

## 8. Ví dụ cấu hình hoàn chỉnh trong Spring Boot

Đoạn sau minh họa cấu hình cả OAuth metadata và OIDC discovery trong cùng Authorization Server security chain:

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerDiscoveryConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                .authorizationServerMetadataEndpoint(metadata ->
                    metadata.authorizationServerMetadataCustomizer(
                        builder -> builder.claim(
                            "service_documentation",
                            "https://auth.example.com/docs/oauth")))
                .oidc(oidc -> oidc
                    .providerConfigurationEndpoint(provider ->
                        provider.providerConfigurationCustomizer(
                            builder -> {
                                builder.claim(
                                    "op_policy_uri",
                                    "https://auth.example.com/legal/privacy");
                                builder.claim(
                                    "op_tos_uri",
                                    "https://auth.example.com/legal/terms");
                            }))))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
    }
}
~~~

Các import được lược bỏ. Ví dụ dùng API <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> của Spring Authorization Server 1.5.x, và hai customizer đúng generic builder.

**Những phần còn cần trong ứng dụng thực:**

1. <code>RegisteredClientRepository</code> để quản lý client.
2. <code>OAuth2AuthorizationService</code> và các thành phần lưu authorization.
3. <code>JWKSource&lt;SecurityContext&gt;</code>, <code>JwtEncoder</code>/token generator phù hợp để ký ID Token/JWT access token và công bố JWKS.
4. <code>JwtDecoder</code> cần thiết cho một số chức năng OIDC như UserInfo theo configuration model.
5. Security chain/login provider cho End-User nếu dùng Authorization Code/OIDC.
6. HTTPS, reverse proxy, trust configuration và database của deployment.

Không coi một security chain ví dụ như trên là một Authorization Server production-ready đầy đủ. Nên áp dụng HTTPS, key management, CSRF và các phương án client/user authentication theo mô hình hệ thống.

### 8.1. Không cần tự viết controller discovery

Khi dùng hai endpoint configurer, framework đăng ký các filter:

- <code>OAuth2AuthorizationServerMetadataEndpointFilter</code>.
- <code>OidcProviderConfigurationEndpointFilter</code> nếu OIDC được bật.

Không nên tạo thêm <code>@RestController</code> cùng well-known URL chỉ để xuất JSON. Controller trùng route có thể khiến một endpoint shadow endpoint còn lại hoặc phá sự nhất quán với <code>AuthorizationServerSettings</code>.

### 8.2. OIDC không bật mặc định

Trong Spring Authorization Server 1.5.x, cấu hình tối thiểu có OAuth metadata endpoint nhưng **OIDC bị tắt mặc định**. Phải gọi <code>.oidc(...)</code> hoặc bật configurer tương ứng thì OpenID Provider Configuration và các endpoint OIDC mới được thiết lập.

Nếu ứng dụng chỉ dùng OAuth client credentials, không phải bật OIDC để cho một OAuth client đọc thông tin Token Endpoint.

## 9. Quy tắc bắt buộc về issuer

### 9.1. Issuer phải khớp chính xác

Giả sử Authorization Server công bố:

~~~json
{
  "issuer": "https://auth.example.com"
}
~~~

JWT token do server phát hành có <code>iss</code> tương ứng và client/Resource Server đã cấu hình issuer này. Các giá trị sau **không được coi là tương đương tùy ý**:

~~~text
https://auth.example.com
https://auth.example.com/
https://auth.internal.example.com
http://auth.example.com
https://AUTH.EXAMPLE.COM
~~~

Theo RFC 8414, issuer trong response metadata phải **giống hệt** issuer mà client dùng để suy ra metadata URL; nếu không khớp thì client phải từ chối metadata. Không tự chuẩn hóa URL tùy tiện để bỏ qua khác biệt về path, trailing slash, scheme hoặc host.

### 9.2. Cùng issuer trên toàn bộ cluster

Trong môi trường nhiều Authorization Server instance:

- Mọi node phải công bố cùng issuer cho cùng một logical Authorization Server.
- Token được phát hành phải có <code>iss</code> nhất quán.
- Discovery và JWKS phải phản ánh key/endpoint của cùng issuer.
- Không để mỗi node tự suy ra issuer khác nhau theo internal address.
- Nếu sử dụng key rotation, discovery phải trỏ tới JWKS chứa public key còn cần xác minh.

Một sai khác issuer rất nhỏ có thể khiến OIDC client từ chối ID Token hoặc Resource Server từ chối access token dù chữ ký đúng.

### 9.3. Đừng sửa issuer chỉ trong builder

Nếu customizer tự thay <code>issuer</code> mà <code>AuthorizationServerSettings</code> và token generator vẫn dùng issuer khác, metadata và JWT sẽ mâu thuẫn. Muốn đổi issuer thật, cần kế hoạch migration có kiểm soát, cập nhật client registrations, callbacks, JWKS/discovery, Resource Servers, session và token còn hiệu lực.

## 10. Reverse proxy, HTTPS và public endpoint URLs

### 10.1. Lỗi phổ biến sau ingress

Một deployment có thể có:

~~~text
Client --> https://auth.example.com
             |
             v
        Reverse Proxy / Ingress
             |
             v
        http://auth-service:9000
~~~

Nếu app cấu hình sai hoặc tin header forwarded không có kiểm soát, discovery có thể trả:

~~~json
{
  "issuer": "http://auth-service:9000",
  "token_endpoint": "http://auth-service:9000/oauth2/token",
  "jwks_uri": "http://auth-service:9000/oauth2/jwks"
}
~~~

Kết quả sai: client ngoài cụm không truy cập được, issuer mismatch, hoặc metadata quảng bá URL không an toàn.

### 10.2. Khuyến nghị

1. Cấu hình <code>AuthorizationServerSettings.issuer("https://auth.example.com")</code> làm nguồn sự thật.
2. Cấu hình TLS/ingress/route thực tế sao cho public URLs tồn tại.
3. Chỉ tin <code>Forwarded</code>/<code>X-Forwarded-*</code> từ proxy đã xác thực; strip header do Internet client tự gửi.
4. Nếu dùng <code>ForwardedHeaderFilter</code> hay <code>server.forward-headers-strategy</code>, giới hạn trust boundary để tránh host-header injection.
5. Kiểm tra external HTTP GET thực, không chỉ MockMvc ở backend.
6. Đặt redirect URI và OIDC callback của client đúng public URL.
7. Không công bố private host, port, đường dẫn admin hay endpoint debug trong metadata.

### 10.3. Không tin URL do caller cung cấp

Metadata là nguồn cấu hình quan trọng. Nếu attacker khiến server trả <code>jwks_uri</code> hoặc <code>token_endpoint</code> trỏ tới host do họ kiểm soát, một client có thể gửi token/secret sai nơi hoặc tải key không tin cậy.

Với client discovery, chỉ tải metadata từ issuer đã được cấu hình/cho phép. Nếu ứng dụng cho người dùng nhập issuer tự do, phải có chính sách kiểm soát URL, SSRF, redirect, DNS và network egress; không tải metadata/JWKS từ địa chỉ nội bộ hoặc metadata service của cloud.

## 11. Issuer có path và mô hình multi-tenant

### 11.1. RFC 8414 chèn well-known trước path issuer

Khi issuer là:

~~~text
https://auth.example.com/tenant-a
~~~

RFC 8414 xác định OAuth Authorization Server Metadata URL:

~~~text
https://auth.example.com/.well-known/oauth-authorization-server/tenant-a
~~~

Không mặc định nối <code>/.well-known/oauth-authorization-server</code> vào cuối issuer path.

### 11.2. OpenID Connect Discovery có quy tắc vị trí lịch sử khác

Với issuer có path, OpenID Connect Discovery 1.0 truyền thống sử dụng:

~~~text
https://auth.example.com/tenant-a/.well-known/openid-configuration
~~~

Trong khi phương thức biến đổi URL theo RFC 8414 với suffix <code>openid-configuration</code> có thể dẫn tới:

~~~text
https://auth.example.com/.well-known/openid-configuration/tenant-a
~~~

Đây là một điểm tương thích thực tế quan trọng: client library và version server có thể chọn biến thể dựa trên chuẩn/profile. Với issuer gốc không có path, hai cách cùng cho <code>https://auth.example.com/.well-known/openid-configuration</code>.

### 11.3. Yêu cầu với multi-issuer

Không bật multi-tenancy chỉ bằng cách thay trường <code>issuer</code> dựa trên Host header. Một hệ thống multi-issuer phải bảo đảm:

- Routing discovery đúng tenant và chuẩn URI.
- Issuer trong metadata đúng tenant được yêu cầu.
- Authorization/token endpoints xử lý request trong đúng tenant context.
- RegisteredClients và authorization storage được phân tách theo tenant.
- Signing keys/JWKS và token issuer khớp tenant; không cho token một tenant bị dùng ở tenant khác.
- Chính sách cookie/session/login và redirect URI không trộn tenant.
- Resource Server xác minh issuer/audience và key đúng tenant.

Đường dẫn discovery multi-tenant phải được kiểm thử với đúng Spring Authorization Server version và reverse proxy. Không giả định cấu hình một <code>AuthorizationServerSettings.issuer()</code> tĩnh sẽ tự tạo một tenant resolver.

## 12. JWKS và thuật toán phải nhất quán

### 12.1. Điều kiện công bố jwks_uri

Trong Spring Authorization Server 1.5.x, JWK Set endpoint được cấu hình khi có bean <code>JWKSource&lt;SecurityContext&gt;</code>. OIDC Provider Configuration có trường bắt buộc <code>jwks_uri</code>.

Khi bật OIDC, hãy:

1. Cung cấp nguồn public/private key phù hợp cho việc ký ID Token.
2. Bảo đảm JWKS endpoint thực sự trả các public JWK cần để verify.
3. Công bố <code>jwks_uri</code> dùng HTTPS, public hostname đúng issuer.
4. Không trả private key material trong JWKS.
5. Xác nhận ID Token thật có header <code>kid</code> tương ứng public JWK đang công bố.
6. Kiểm thử key rotation với client cache JWKS.

### 12.2. ID Token signing metadata không phải lựa chọn trang trí

<code>id_token_signing_alg_values_supported</code> phải mô tả các thuật toán OP thực sự ký ID Token. Nếu server chỉ ký bằng RSA RS256, không công bố <code>ES256</code> để làm danh sách có vẻ hiện đại hơn.

Không cho client quyết định thuật toán ký bằng cách chèn query parameter vào Discovery Endpoint; thuật toán và key selection phải thuộc chính sách server.

### 12.3. Rotation và cache

Client thường cache metadata và JWKS. Trong rotation:

- Pre-publish public key mới trước khi ký token bằng key mới.
- Giữ public key cũ đến khi token tương ứng hết hạn, trừ tình huống key compromise cần revocation khẩn cấp.
- Theo dõi cache TTL của JWKS tại OIDC client và Resource Server.
- Không tự đổi <code>jwks_uri</code> mỗi lần rotation nếu endpoint ổn định có thể công bố nhiều keys.
- Kiểm tra metadata/JWKS từ bên ngoài cluster qua đúng ingress/CDN.

Metadata ổn định và JWKS cập nhật là hai lớp quản trị khác nhau; thay key không nhất thiết cần thay issuer hay endpoint.

## 13. Metadata về tính năng nâng cao

Một số trường liên quan đến tính năng nâng cao:

| Tính năng | Trường metadata thường gặp | Điều kiện quảng bá |
| --- | --- | --- |
| PKCE | <code>code_challenge_methods_supported</code> | Server hỗ trợ phương thức được liệt kê; ưu tiên S256. |
| Device Authorization | <code>device_authorization_endpoint</code> | Endpoint hoạt động và grant có provider phù hợp. |
| Token Revocation | <code>revocation_endpoint</code> | Endpoint tồn tại, client auth và revocation service hoạt động. |
| Token Introspection | <code>introspection_endpoint</code> | Endpoint hoạt động, có chính sách client authorization. |
| Pushed Authorization Requests (PAR) | <code>pushed_authorization_request_endpoint</code> | PAR đã được bật; request flow tương ứng đã kiểm thử. |
| mTLS | <code>mtls_endpoint_aliases</code>, <code>tls_client_certificate_bound_access_tokens</code> | Có TLS endpoint alias thực và verification/binding end-to-end. |
| DPoP | <code>dpop_signing_alg_values_supported</code> | Server và client thực sự xử lý DPoP proof/binding. |
| OIDC UserInfo | <code>userinfo_endpoint</code> | Endpoint đã bật, token được xác thực và claims theo consent/policy. |
| RP-Initiated Logout | <code>end_session_endpoint</code> | Có endpoint logout và session/logout policy. |
| Dynamic Client Registration | <code>registration_endpoint</code> | Đã bật registration và bảo vệ initial access token/registration policy. |

Spring Authorization Server 1.5.x **không bật Dynamic Client Registration mặc định**. Đừng thêm <code>registration_endpoint</code> vào metadata chỉ vì mong muốn có khả năng đó.

### 13.1. Chú ý mTLS endpoint aliases

RFC 8705 cho phép công bố các endpoint alias dành riêng cho client mTLS, giúp tránh bắt trình duyệt người dùng trình chứng thư ở Authorization Endpoint. Tuy nhiên, thêm <code>mtls_endpoint_aliases</code> vào JSON không tạo TLS listener mới. Phải cấu hình ingress, hostname, certificate trust và routing trước.

### 13.2. Chú ý PAR và yêu cầu bắt buộc PAR

Nếu metadata công bố PAR endpoint hoặc bắt buộc sử dụng PAR, client phải gửi request theo flow phù hợp. Không công bố cờ bắt buộc PAR nếu Authorization Endpoint vẫn đang tiếp nhận request thông thường theo policy khác hoặc client chưa tương thích.

### 13.3. Chú ý OIDC claims và scope

<code>scopes_supported</code> mô tả scope mà OP hỗ trợ; <code>claims_supported</code> mô tả những claim có thể cung cấp. Consent và quyền của từng client vẫn quyết định kết quả thực tế. Không coi công bố <code>profile</code> là lời hứa trả mọi claim hồ sơ cho mọi client.

## 14. Kiểm thử metadata bằng HTTP và MockMvc

### 14.1. Smoke test qua curl

Từ một máy ngoài cluster:

~~~bash
curl --fail --show-error --silent \
  https://auth.example.com/.well-known/oauth-authorization-server

curl --fail --show-error --silent \
  https://auth.example.com/.well-known/openid-configuration

curl --fail --show-error --silent \
  https://auth.example.com/oauth2/jwks
~~~

Chỉ truy vấn endpoint OpenID Provider khi OIDC đã bật. Nếu JWKS endpoint không có hoặc trả lỗi, phải kiểm tra nguồn JWK và cấu hình server. Không dùng <code>--insecure</code> để vượt qua lỗi TLS.

### 14.2. MockMvc kiểm tra OAuth metadata

Giả sử Spring Boot test đã khởi tạo Authorization Server security chain:

~~~java
@Test
void oauthMetadataPublishesExpectedPublicUrls() throws Exception {
    mockMvc.perform(get("/.well-known/oauth-authorization-server"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.issuer")
            .value("https://auth.example.com"))
        .andExpect(jsonPath("$.authorization_endpoint")
            .value("https://auth.example.com/oauth2/authorize"))
        .andExpect(jsonPath("$.token_endpoint")
            .value("https://auth.example.com/oauth2/token"))
        .andExpect(jsonPath("$.service_documentation")
            .value("https://auth.example.com/docs/oauth"));
}
~~~

Đoạn test giả định <code>mockMvc</code> đã được inject bằng <code>@AutoConfigureMockMvc</code> hoặc cấu hình tương đương. Đây là kiểm thử metadata chứ không chứng minh Token Endpoint đã cấp được token thật; cần thêm integration test cho từng grant được quảng bá.

### 14.3. MockMvc kiểm tra OpenID Provider Configuration

~~~java
@Test
void oidcDiscoveryPublishesRequiredAndLegalMetadata() throws Exception {
    mockMvc.perform(get("/.well-known/openid-configuration"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.issuer")
            .value("https://auth.example.com"))
        .andExpect(jsonPath("$.jwks_uri")
            .value("https://auth.example.com/oauth2/jwks"))
        .andExpect(jsonPath("$.subject_types_supported")
            .isArray())
        .andExpect(jsonPath("$.id_token_signing_alg_values_supported")
            .isArray())
        .andExpect(jsonPath("$.op_policy_uri")
            .value("https://auth.example.com/legal/privacy"))
        .andExpect(jsonPath("$.op_tos_uri")
            .value("https://auth.example.com/legal/terms"));
}
~~~

Test này yêu cầu OIDC đã được bật và JWKSource đã được cấu hình. Nếu deployment sử dụng issuer có context path hoặc multi-tenant URL, điều chỉnh request path và expected URLs cho đúng profile.

### 14.4. Kiểm thử nhất quán giữa metadata và runtime

Không chỉ dùng JSON snapshot test. Với mỗi capability quan trọng:

1. Đọc metadata thực.
2. Xác nhận URL endpoint nằm trong expected public origin.
3. Gửi request đúng protocol để kiểm tra endpoint hoạt động.
4. Kiểm tra request không hợp lệ bị từ chối đúng OAuth/OIDC error.
5. Nếu công bố PKCE S256, hoàn tất Authorization Code + PKCE thực.
6. Nếu công bố một grant mới, kiểm tra client được phép dùng và client khác bị từ chối.
7. Nếu công bố JWK Set, dùng public JWK để verify token thật.
8. Nếu công bố UserInfo, gọi bằng access token hợp lệ, kiểm tra subject và scope/claims.
9. Nếu công bố mTLS/DPoP, kiểm tra xác thực/proof ở Token Endpoint và Resource Server.

## 15. Ma trận kiểm thử hồi quy

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| OAuth metadata endpoint trên HTTPS | Trả JSON, issuer đúng và public URLs dùng HTTPS. |
| OIDC chưa bật | Không quảng bá OpenID Provider Configuration như thể OIDC hoạt động. |
| OIDC đã bật | OpenID discovery trả metadata OIDC hợp lệ. |
| Custom OAuth documentation | <code>service_documentation</code> đúng URL, không làm mất trường bắt buộc. |
| Custom OIDC policy/ToS | <code>op_policy_uri</code>, <code>op_tos_uri</code> có mặt. |
| <code>issuer</code> metadata khác token <code>iss</code> | Test thất bại; phải sửa configuration. |
| Issuer với trailing slash sai | Client phải phát hiện mismatch, không tự bỏ qua. |
| Backend nằm sau ingress | Không có <code>localhost</code>, internal hostname hoặc HTTP URL trong metadata. |
| Client gửi Host giả | Không thể làm metadata công bố issuer tùy ý. |
| JWKS endpoint | Chỉ công bố public keys, không có private material. |
| JWT ký bằng key mới | JWKS chứa public key khớp <code>kid</code>. |
| OAuth metadata công bố grant mới | Provider/converter xử lý grant đúng và kiểm tra RegisteredClient. |
| OIDC công bố <code>claims_supported</code> | Claims thực sự được hỗ trợ theo scope/consent/policy. |
| Công bố <code>private_key_jwt</code> | Client đã đăng ký có thể dùng đúng phương thức JWT assertion. |
| Công bố dynamic client registration | Chỉ khi endpoint đã bật và được bảo vệ. |
| Metadata issuer path/tenant A | Discovery, token issuer, key và client đều thuộc tenant A. |
| Metadata tenant A yêu cầu bằng tenant B | Không rò endpoint/keys/issuer hoặc authorization giữa tenant. |
| Proxy/CDN cache metadata cũ | Có refresh/invalidation phù hợp khi thay capability/URL. |
| Không có JWKSource nhưng bật OIDC | Test cấu hình khởi động/discovery phải phát hiện sai hoặc thiếu JWKS. |
| Endpoint trả 200 nhưng callback/redirect sai | Contract test client flow phát hiện mismatch. |

### 15.1. Security test với client library thật

Nên thực hiện một bài test sử dụng Spring Security OAuth2 Client hoặc một OIDC SDK đã được chọn cho production:

- Chỉ cấu hình issuer của Authorization Server.
- Để thư viện tự discovery URL và lấy JWK Set.
- Hoàn tất một flow thật.
- Xác minh token signature/issuer/audience/time và scope.
- Thử thay issuer trong metadata giả để xác nhận client từ chối.

Việc kiểm thử qua một SDK thực giúp phát hiện khác biệt về chuẩn hóa URL, JWKS cache, path-based issuer và các trường bắt buộc mà MockMvc snapshot test có thể bỏ qua.

## 16. Lỗi thường gặp và cách xử lý

### Lỗi 1: Thêm capability vào JSON nhưng không có endpoint thật

**Triệu chứng:** Discovery trả endpoint hợp lệ về mặt cú pháp nhưng request thật nhận 404 hoặc unsupported grant.

**Nguyên nhân:** Coi metadata builder như cơ chế bật tính năng.

**Cách sửa:** Cấu hình endpoint/filter/provider trước, rồi quảng bá metadata và viết integration test.

### Lỗi 2: Metadata dùng địa chỉ nội bộ sau reverse proxy

**Triệu chứng:** OIDC client bên ngoài không tới được Token Endpoint hoặc báo invalid issuer.

**Nguyên nhân:** Issuer bị suy ra từ internal host/scheme.

**Cách sửa:** Cấu hình issuer public, kiểm tra trusted forwarded headers và test qua ingress thật.

### Lỗi 3: OIDC discovery không tồn tại

**Triệu chứng:** GET <code>/.well-known/openid-configuration</code> trả 404.

**Nguyên nhân:** OIDC chưa bật trong Authorization Server configurer hoặc request không đi vào đúng security chain.

**Cách sửa:** Bật <code>.oidc(...)</code>, kiểm tra matcher/filter chain và JWT/endpoint dependencies.

### Lỗi 4: jwks_uri trỏ sai hoặc không có public key

**Triệu chứng:** Client lấy được ID Token nhưng không xác minh được chữ ký.

**Nguyên nhân:** Thiếu JWKSource, JWKS endpoint sai, key ID không khớp hoặc key rotation chưa đồng bộ.

**Cách sửa:** Đăng ký nguồn key đúng, công bố public JWK và test JWT với đúng public key.

### Lỗi 5: issuer của JWT không bằng issuer trong discovery

**Triệu chứng:** SDK từ chối token dù chữ ký hợp lệ.

**Nguyên nhân:** Chỉ sửa <code>issuer</code> trong builder hoặc nhiều node dùng settings khác nhau.

**Cách sửa:** Dùng một nguồn issuer tin cậy cho metadata và token generation; test mọi instance.

### Lỗi 6: Công bố thuật toán ID Token không thực sự hỗ trợ

**Triệu chứng:** Client chọn thuật toán nhưng token encoder/JWK Set không tương thích.

**Nguyên nhân:** Tùy ý thêm phần tử vào <code>id_token_signing_alg_values_supported</code>.

**Cách sửa:** Kiểm tra signing algorithms của token generator và test token thật; không quảng bá thuật toán yếu/chưa hỗ trợ.

### Lỗi 7: Nhầm OAuth metadata với OIDC Discovery

**Triệu chứng:** Client OIDC đọc RFC 8414 metadata rồi chờ những trường OIDC không có.

**Nguyên nhân:** Dùng sai well-known URL/profile.

**Cách sửa:** Chọn đúng tài liệu và bật OP config endpoint khi triển khai OIDC.

### Lỗi 8: Issuer chứa path nhưng dùng sai biến đổi well-known URL

**Triệu chứng:** Multi-tenant client gặp 404 hoặc issuer mismatch.

**Nguyên nhân:** Ghép URL <code>/.well-known/...</code> không theo RFC/profile của consumer.

**Cách sửa:** Áp dụng quy tắc RFC 8414 và OpenID Connect Discovery tương ứng; test trên issuer path thật.

### Lỗi 9: Dùng metadata để quảng cáo dynamic client registration không bảo vệ

**Triệu chứng:** Client lạ có thể tạo registration không theo policy.

**Nguyên nhân:** Bật nhầm endpoint hoặc công bố URL registration mà không có access control.

**Cách sửa:** Chỉ bật khi có yêu cầu và chính sách authorization/initial access token rõ ràng.

### Lỗi 10: Tự viết controller trả JSON, bỏ qua settings mặc định

**Triệu chứng:** Metadata và endpoint thực ngày càng khác nhau sau những lần upgrade.

**Nguyên nhân:** Hard-code JSON không dùng builder/framework.

**Cách sửa:** Dùng endpoint configurer + builder; lưu contract tests làm hàng rào hồi quy.

## 17. Vận hành production

### 17.1. Quy trình thay đổi metadata

Một thay đổi metadata có thể làm SDK/client đổi flow hoặc endpoint. Quy trình an toàn:

1. Xác định trường và behavior thực tế sẽ thay đổi.
2. Kiểm tra backward compatibility với client hiện có.
3. Cập nhật cấu hình endpoint/grant/key thật trước hoặc đồng thời.
4. Cập nhật builder customizer, không thay JSON ngoài hệ thống.
5. Chạy test metadata và test flow với SDK thật.
6. Phát hành qua staging/rolling deployment, theo dõi lỗi 4xx/5xx và login failure.
7. Xử lý cache metadata/CDN, đồng bộ tất cả node.
8. Có rollback plan cho capability, endpoint URLs và client config nếu phát sinh lỗi.

### 17.2. Cache metadata hợp lý

Discovery metadata chủ yếu là public configuration nên có thể được cache theo HTTP policy được cấu hình đúng. Tuy nhiên:

- Thời gian cache quá dài làm client chậm nhận endpoint hoặc capability mới.
- Thời gian cache quá ngắn tăng tải không cần thiết.
- Key rotation thường chỉ cần cập nhật JWKS, không nhất thiết thay metadata URI.
- Với thay issuer hoặc thay public host, cần kế hoạch migration; giảm cache TTL đơn lẻ không giải quyết được toàn bộ token/session cũ.

Không khẳng định mọi client tuân theo TTL giống nhau. Kiểm thử hành vi cache của SDK và reverse proxy/CDN thực tế.

### 17.3. Metrics và audit

Theo dõi:

- Số request và status code của hai well-known endpoints.
- Lỗi metadata schema/issuer mismatch từ integration tests.
- Lỗi client token validation liên quan issuer/JWKS/algorithm.
- Thay đổi public endpoint URLs và capability list sau deploy.
- Thời điểm JWKS thay đổi và key rotation.
- Những client vẫn dùng discovery URL cũ sau migration.

Không cần log bearer token, ID Token, client secret hoặc request body nhạy cảm chỉ để chẩn đoán metadata. Đối với document public, log request ID, endpoint, status, version/config hash và origin phù hợp là đủ.

## 18. Bài tập tự thực hành

Bạn đang xây dựng Authorization Server cho ba nhóm client: <code>orders-web</code> dùng Authorization Code + PKCE/OIDC, <code>orders-worker</code> dùng Client Credentials, và <code>partner-service</code> dùng private_key_jwt. Server public tại <code>https://auth.example.com</code>, backend sau ingress tại <code>http://auth:9000</code>.

1. Cấu hình <code>AuthorizationServerSettings</code> với issuer công khai và xác minh metadata không chứa URL nội bộ.
2. Bật OIDC và tạo hai metadata endpoints theo chuẩn tương ứng.
3. Tùy chỉnh OAuth metadata với <code>service_documentation</code>.
4. Tùy chỉnh OpenID Provider Configuration với <code>op_policy_uri</code> và <code>op_tos_uri</code>.
5. Kiểm tra <code>response_types_supported</code>, <code>grant_types_supported</code> và <code>token_endpoint_auth_methods_supported</code> khớp server thật.
6. Đăng ký JWKSource; đọc <code>jwks_uri</code> và xác minh một ID Token bằng public JWK.
7. Bảo đảm client credentials token không bị coi là OIDC ID Token và OIDC <code>claims_supported</code> không hứa claims chưa triển khai.
8. Giả lập Forwarded/Host header độc hại để kiểm tra issuer không bị thay tùy ý.
9. Tạo issuer tenant <code>https://auth.example.com/tenant-a</code>, tính well-known URL theo RFC 8414 và OpenID Connect Discovery; giải thích khác biệt.
10. Viết MockMvc + HTTP integration test sử dụng một OIDC client SDK thật để xác minh discovery, token issuer, JWKS, audience và refresh hành vi cache.

**Tiêu chí đạt:** Hai JSON metadata có cấu trúc đúng chuẩn, URL public/issuer nhất quán, các capability được quảng bá **đều được server triển khai thực sự**, và SDK có thể discovery/cấp/kiểm tra token mà không cần hard-code endpoint URLs.

## 19. Tài liệu đối chiếu

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): trường metadata, quy tắc well-known URL, issuer validation và bảo mật.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider Configuration, metadata bắt buộc, discovery URL và OIDC client validation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo, subject type và claims.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): <code>OAuth2AuthorizationServerMetadataEndpointConfigurer</code> và <code>OidcProviderConfigurationEndpointConfigurer</code>.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): bật OIDC, AuthorizationServerSettings, JWK Set endpoint và các core beans.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationServerMetadata.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationServerMetadata.Builder.html): claim builder và required fields.
- [Spring Authorization Server 1.5.8 — OidcProviderConfiguration.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcProviderConfiguration.Builder.html): policy/claims/subject/signing metadata và required fields.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): định dạng public key được công bố qua JWKS.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS endpoint aliases và certificate-bound token metadata.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): PAR endpoint và behavior.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): OAuth/OIDC client configuration và discovery.
