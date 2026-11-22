# Kiểm tra metadata nhất quán với endpoint đã bật và tính năng thực tế

Một Authorization Server có thể vận hành bình thường khi thử thủ công một endpoint nhưng vẫn khiến OAuth2 Client hoặc Resource Server thất bại ở production. Nguyên nhân thường gặp là **metadata công bố một hợp đồng khác với những gì server thực sự hỗ trợ**: `jwks_uri` dẫn đến 404, `issuer` không khớp JWT, `grant_types_supported` liệt kê grant chưa triển khai, hoặc OpenID Provider Configuration công bố `userinfo_endpoint` nhưng thực tế lại bị chặn bởi trang login.

**OAuth 2.0 Authorization Server Metadata (RFC 8414)** và **OpenID Connect Discovery 1.0** giúp client tìm cấu hình mà không phải đoán đường dẫn. Đổi lại, metadata trở thành **giao diện công khai và hợp đồng bảo mật**. Client có thể dựa vào đó để chọn grant, thuật toán, kiểu xác thực và nơi tải JWK Set. Một JSON hợp lệ về cú pháp chưa đủ: nội dung phải khớp *endpoint, tính năng và policy thực tế*.

Bài học thuộc chương **Metadata và Discovery** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Phạm vi module là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm ở đây là thiết kế **cơ chế kiểm tra metadata nhất quán với endpoint đã bật và tính năng thực tế**, áp dụng được cho CI/CD và môi trường nhiều node.

> **Nguyên tắc:** Một khả năng chỉ được coi là hỗ trợ khi **(1)** metadata công bố đúng, **(2)** endpoint/flow thực sự hoạt động, **(3)** các ràng buộc bảo mật được thực thi và **(4)** có kiểm thử chứng minh. Thêm một claim vào discovery document không làm Spring Authorization Server tự triển khai tính năng.

## 1. Metadata là hợp đồng giao thức, không phải trang liệt kê URL

Metadata được OAuth2 Client, Resource Server hoặc Relying Party sử dụng để định cấu hình issuer và các endpoint/capabilities. Những trường quan trọng thường có:

| Nhóm | Ví dụ metadata | Ý nghĩa |
|---|---|---|
| Định danh | `issuer` | Trust boundary của Authorization Server |
| Điểm cuối | `authorization_endpoint`, `token_endpoint` | Authorization và token issuance |
| Khóa công khai | `jwks_uri` | Lấy public keys xác minh JWT/JWS |
| Protocol capabilities | `response_types_supported`, `grant_types_supported` | Response types và grants |
| Client authentication | `token_endpoint_auth_methods_supported` | Cách client được xác thực |
| PKCE | `code_challenge_methods_supported` | PKCE methods được công bố |
| Trạng thái token | `revocation_endpoint`, `introspection_endpoint` | Thu hồi và xác minh trạng thái |
| Tính năng mở rộng | Device Authorization, PAR, DPoP, mTLS, Token Exchange | Khả năng tùy chọn |
| OIDC | `userinfo_endpoint`, `id_token_signing_alg_values_supported` | Xác thực người dùng và ID Token |

Một URL xuất hiện trong JSON chỉ chứng minh nó **được quảng bá**, không chứng minh route tồn tại. Tương tự, HTTP 200 có thể chỉ là trang HTML hoặc lỗi bị proxy trả sai. Kiểm tra phải đi từ **configuration → metadata → HTTP behavior → security enforcement**.

### 1.1. Bốn lớp cần nhất quán

| Lớp | Câu hỏi | Minh chứng |
|---|---|---|
| **Cấu hình** | Filter/configurer/provider nào bật tính năng? | SecurityFilterChain, bean, settings |
| **Metadata** | Tính năng được công bố ra bên ngoài thế nào? | JSON discovery thực tế |
| **Runtime** | Flow có chạy đúng giao thức không? | HTTP integration tests |
| **Policy** | Các giới hạn được áp dụng thật không? | Negative tests và authorization checks |

### 1.2. Những dạng metadata drift

| Dạng lệch | Ví dụ | Hậu quả |
|---|---|---|
| Công bố nhưng thiếu route | `pushed_authorization_request_endpoint` dẫn tới 404 | Client không dùng PAR được |
| Công bố nhưng bị chặn | `jwks_uri` redirect đến `/login` | Resource Server không tải key |
| Công bố nhưng không hỗ trợ | `private_key_jwt` trong metadata, server chỉ chấp nhận Basic | `invalid_client` |
| Hỗ trợ nhưng không công bố | UserInfo hoạt động nhưng thiếu `userinfo_endpoint` | Client discovery không cấu hình được |
| URL sai | Public domain bị thay bằng `http://localhost:9000` | Issuer/TLS mismatch |
| Enforcement sai | Quảng bá PKCE nhưng cho đổi code bằng verifier sai | Rủi ro an ninh |
| Triển khai lệch node | Node A có grant mới, node B chưa có provider | Lỗi ngẫu nhiên sau load balancer |

## 2. Phân biệt RFC 8414 với OIDC Discovery

Hai discovery document liên quan nhưng **không đồng nhất**.

| Tiêu chí | OAuth 2.0 Authorization Server Metadata | OpenID Provider Configuration |
|---|---|---|
| Tiêu chuẩn | RFC 8414 | OpenID Connect Discovery 1.0 |
| Mục đích | Khả năng OAuth2 của AS | Khả năng OpenID Provider |
| Well-known suffix phổ biến | `/.well-known/oauth-authorization-server` | `/.well-known/openid-configuration` |
| Nội dung chủ đạo | Issuer, token/authorization endpoints, grants, client authentication | Issuer, UserInfo, ID Token signing, subject types, OIDC endpoints |
| Có tự chứng minh OIDC đã bật? | **Không** | Chỉ khi OP thực sự hoạt động |
| Có thể cùng tồn tại? | Có | Có |

Ví dụ AS chỉ cấp OAuth2 access token chưa chắc hỗ trợ OIDC ID Token, UserInfo hoặc RP-Initiated Logout. Không tự tạo OpenID Provider Configuration để “cho đủ metadata” khi các capability tương ứng chưa hoạt động.

### 2.1. Discovery URLs với root issuer

Với issuer:

~~~text
https://identity.example.com
~~~

Hai URL phổ biến là:

~~~http
GET https://identity.example.com/.well-known/oauth-authorization-server
GET https://identity.example.com/.well-known/openid-configuration
~~~

Không mặc định cả hai đều tồn tại. OIDC Provider Configuration phụ thuộc OIDC functionality được bật và cấu hình trong Spring.

### 2.2. Issuer có path: quy tắc URL cần được kiểm thử

Với issuer:

~~~text
https://identity.example.com/tenant/blue
~~~

RFC 8414 đặt well-known suffix giữa authority và path của issuer:

~~~text
https://identity.example.com/.well-known/oauth-authorization-server/tenant/blue
~~~

OIDC Discovery 1.0 định nghĩa đường dẫn truyền thống bằng cách nối suffix vào issuer:

~~~text
https://identity.example.com/tenant/blue/.well-known/openid-configuration
~~~

Framework client/server có thể thử thêm các discovery fallback theo profile và version. Phải kiểm thử **URI mà client thật dùng**, nhất là multi-tenant và context-path deployment; không suy đoán bằng cách nối chuỗi URL thủ công.

### 2.3. OAuth2 không tự có OIDC semantics

Một OAuth2 metadata document quảng bá `authorization_code` không chứng minh AS phát ID Token. Với OIDC cần thử authorization request có `scope=openid` và xác minh ID Token thực tế, chữ ký, `iss`, `aud`, `nonce` khi áp dụng và các yêu cầu OIDC tương ứng.

## 3. Luồng kiểm tra từ cấu hình đến hành vi

Một bộ kiểm thử tốt coi metadata là **đầu vào của contract verification**:

~~~mermaid
flowchart TD
    A[Đọc settings, configurers, registered clients] --> B[GET OAuth2/OIDC discovery]
    B --> C[Kiểm tra issuer và public URLs]
    C --> D[Đối chiếu endpoint fields với routes đang chạy]
    D --> E[Đối chiếu grants, client auth methods, algorithms]
    E --> F[Chạy positive protocol tests]
    F --> G[Chạy negative policy/security tests]
    G --> H{Metadata, runtime, policy có khớp?}
    H -->|Có| I[Release gate PASS + contract snapshot]
    H -->|Không| J[Fail release, sửa config/deployment]
    J --> A
~~~

**Positive tests** chứng minh advertised capability hoạt động với client hợp lệ. **Negative tests** chứng minh AS từ chối request sai và thực sự enforcement. Chỉ test authorization code thành công chẳng hạn không thể chứng minh PKCE bắt buộc.

## 4. Kiểm tra `issuer` trước mọi trường khác

`issuer` là định danh Authorization Server và trust anchor cho Client/Resource Server. Trong nhiều profile, nó phải **exact-match** với issuer đã cấu hình và JWT/ID Token `iss`; khác biệt một dấu slash có thể làm validator từ chối.

Metadata:

~~~json
{
  "issuer": "https://identity.example.com"
}
~~~

Token phát thật có claim tương ứng:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1794850600
}
~~~

### 4.1. Các lỗi issuer thường gặp

- Discovery trả `http://localhost:9000` trong khi API dùng `https://identity.example.com`.
- Metadata issuer không có trailing slash nhưng JWT `iss` có trailing slash.
- Tenant A và B dùng chung issuer ngoài ý muốn, dù token store và keys khác nhau.
- Proxy thêm/bỏ context path khiến issuer không khớp.
- Rolling deployment dùng các issuer khác nhau giữa nodes.

### 4.2. Định cấu hình public issuer ổn định

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .build();
}
~~~

Giữ issuer là **public HTTPS identifier** có kiểm soát, không lấy ngẫu nhiên từ `Host` do caller cung cấp. Nếu resolve động theo tenant, phải có tenant resolver, allowed hosts, mapping ổn định và kiểm thử isolation.

### 4.3. Reverse proxy và forwarded headers

Client nhìn thấy:

~~~text
https://identity.example.com/oauth2/token
~~~

Application nội bộ có thể nhìn thấy:

~~~text
http://authorization-server:9000/oauth2/token
~~~

Đây là tình huống bình thường khi TLS termination tại ingress. Nhưng server chỉ được tin `Forwarded`/`X-Forwarded-*` từ proxy được kiểm soát; proxy phải loại header giả do client gửi từ Internet. Không để metadata bị attacker chỉnh host/scheme bằng forged forwarded headers.

## 5. Endpoint được công bố có thực sự được bật?

Các endpoint trong Spring Authorization Server phụ thuộc configurer, `AuthorizationServerSettings`, bean hỗ trợ và provider. Không suy luận capability chỉ từ class có mặt trên classpath.

| Metadata field | Endpoint/flow | Phải kiểm tra |
|---|---|---|
| `authorization_endpoint` | Browser authorization | Login, consent, redirect URI validation |
| `token_endpoint` | Token issuance | POST, client authentication, grant provider |
| `jwks_uri` | JWK Set | GET public keys, verify JWT, không lộ private keys |
| `revocation_endpoint` | Token revocation | POST + auth, token invalidation theo RFC 7009 |
| `introspection_endpoint` | Token introspection | POST + auth, `active` theo RFC 7662 |
| `device_authorization_endpoint` | Device flow | Cấp device/user code, verification và polling |
| `pushed_authorization_request_endpoint` | PAR | POST, `request_uri`, `expires_in` và client binding |
| `userinfo_endpoint` | OIDC UserInfo | OIDC được bật, token phù hợp, claims được phép |
| `end_session_endpoint` | OIDC logout | Session và post-logout redirect validation |
| `registration_endpoint` | Dynamic Client Registration | Endpoint thật và registration access policy |

### 5.1. Đúng method và request shape

Không dùng GET cho tất cả URLs rồi kết luận HTTP 405 là endpoint không hỗ trợ. Token, introspection, revocation và PAR thường là POST; một GET bị từ chối có thể cho thấy route đang tồn tại và bảo vệ đúng. Cần test **HTTP method, content type, client authentication và request fixture hợp lệ**.

### 5.2. Public endpoint không đồng nghĩa mọi endpoint public

Discovery và JWKS thường cho phép anonymous GET. Introspection/revocation/token endpoint có client authentication, registration cũng có policy riêng. Một endpoint trả 401 khi thiếu credential **không phải** metadata drift; 401 có thể chính là enforcement đúng.

## 6. `AuthorizationServerSettings`, filter chain và các bean

Spring Authorization Server dùng `AuthorizationServerSettings` để xác định issuer cùng đường dẫn protocol endpoints. Ví dụ:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .authorizationEndpoint("/oauth2/authorize")
        .tokenEndpoint("/oauth2/token")
        .jwkSetEndpoint("/oauth2/jwks")
        .tokenIntrospectionEndpoint("/oauth2/introspect")
        .tokenRevocationEndpoint("/oauth2/revoke")
        .build();
}
~~~

Ví dụ cho một nhánh Spring Authorization Server có các methods trên. Nếu thay path `/oauth2/token` bằng `/oauth2/v2/token`, metadata phải quảng bá đúng URL mới và client cần chuyển cấu hình tương ứng.

### 6.1. Ba lớp khác nhau

| Thành phần | Tác động | Không tự bảo đảm |
|---|---|---|
| `AuthorizationServerSettings` | Issuer và relative endpoint paths | Optional grant/provider được triển khai |
| `OAuth2AuthorizationServerConfigurer` | Wiring protocol filters và extension points | Custom grants hoạt động đúng |
| `SecurityFilterChain` | Matchers, authentication, ordering | URL metadata khớp reverse proxy |
| `JWKSource<SecurityContext>` | Key material/JWKS khi có signing configuration phù hợp | Public JWKS rotation/key consistency |
| `RegisteredClientRepository` | Client registration, grant và auth method từng client | Metadata toàn cục khớp tất cả clients |
| `OAuth2AuthorizationService` | Lưu authorization và token state | Revocation/introspection filter đã bật |

### 6.2. Khung SecurityFilterChain

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung cấu hình, không phải ứng dụng Spring Boot hoàn chỉnh. Cần các bean như client repository, authorization services, signer/JWK source và login chain. Test phải xác minh discovery/JWKS trả JSON thay vì redirect sang trang form login.

## 7. Khi nào OpenID Provider Configuration được công bố?

**OIDC không đồng nghĩa OAuth2**. Với Spring Authorization Server, OIDC functionality cần được bật qua OIDC configurer của phiên bản tương ứng:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đoạn này chỉ minh họa cách bật OIDC protocol support; các bean và login/consent config khác vẫn cần thiết. Không quảng bá OpenID Provider Configuration chỉ vì server cấp OAuth2 access token.

### 7.1. Các field OIDC cần kiểm tra

| OP metadata field | Ý nghĩa | Test tương ứng |
|---|---|---|
| `issuer` | OP identifier | So với ID Token `iss` |
| `authorization_endpoint` | Authorization endpoint | Login và consent với `scope=openid` |
| `token_endpoint` | Token issuance | Code exchange + ID Token |
| `jwks_uri` | Public signing keys | Verify chữ ký ID Token theo `kid` |
| `userinfo_endpoint` | UserInfo | Truy cập bằng token phù hợp, claims theo consent |
| `response_types_supported` | Supported OIDC response types | Flow tương ứng thật sự hoạt động |
| `subject_types_supported` | `public`/`pairwise` | Behavior của `sub` |
| `id_token_signing_alg_values_supported` | Thuật toán ID Token | Chữ ký thực tế khớp |
| `scopes_supported` | Scope được quảng bá | Request phù hợp policy |
| `claims_supported` | Claims OP có thể cung cấp | Không over-disclose |
| `end_session_endpoint` | OIDC logout nếu có | Logout/redirect validation |
| `registration_endpoint` | Dynamic registration nếu có | Access policy của registration |

Không tự thêm ES256 nếu signer chỉ phát ID Token RS256, hoặc quảng bá pairwise subject khi OP chỉ trả một `sub` toàn cục.

### 7.2. Scope openid có ý nghĩa giao thức

`scope=openid` kích hoạt OIDC authentication semantics, bao gồm ID Token và các yêu cầu bổ sung. Nếu server nhận scope đó nhưng không phát ID Token trong flow yêu cầu, hoặc metadata công bố OIDC nhưng runtime không xử lý đúng, đó là lỗi hợp đồng.

## 8. `jwks_uri` phải xác minh được token thật

Metadata:

~~~json
{
  "issuer": "https://identity.example.com",
  "jwks_uri": "https://identity.example.com/oauth2/jwks"
}
~~~

JWKS:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "sign-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là JSON minh họa, chưa chứa public modulus RSA thật.

### 8.1. Kiểm tra tốt hơn HTTP 200

1. GET `jwks_uri` từ client ngoài cluster, không có login cookie.
2. Kiểm tra HTTPS, status 200, content type JSON và mảng `keys`.
3. Mọi JWK phải là public-only; RSA không lộ `d`/CRT, EC/OKP không lộ private `d`, không xuất bản symmetric secret `oct.k`.
4. JWT thực tế có `kid` khớp một key trong set.
5. Header `alg` khớp key type và verification allowlist.
6. Resource Server xác minh được signature, issuer, expiry và audience của token thật.

### 8.2. Key rotation cũng là contract

Không bỏ public key K1 khỏi JWKS ngay khi chuyển signer sang K2 nếu token K1 còn hạn. Nên công bố K2 trước, chờ cache consumer cập nhật, chuyển signer, giữ K1 qua overlap, sau đó mới loại K1. Test cần verify cả token K1/K2 trong giai đoạn chuyển đổi.

### 8.3. JWK Set Endpoint phụ thuộc key source

Trong Spring Authorization Server, `JWKSource<SecurityContext>` phù hợp là điều kiện quan trọng để JWK Set Endpoint hoạt động trong kiến trúc ký JWT. Không thêm `jwks_uri` bằng custom metadata khi server không có public key tương ứng để công bố.

## 9. Grants và response types: công bố đúng flow

Ví dụ:

~~~json
{
  "response_types_supported": ["code"],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ]
}
~~~

Chỉ dùng ví dụ này cho server thực sự hỗ trợ cả ba grant. Không suy ra một dependency tự triển khai mọi grant.

### 9.1. Globally supported khác per-client allowed

Metadata mô tả **khả năng toàn cục của AS**, không thay thế `RegisteredClient`. Server hỗ trợ `client_credentials` và `authorization_code`, nhưng:

- `backend-service` có thể chỉ được phép client credentials;
- `web-app` chỉ có authorization code;
- `mobile-app` chỉ có authorization code với PKCE.

Không đánh giá metadata là sai chỉ vì một client bị từ chối grant mà server hỗ trợ cho client khác. Hãy test positive với **client được đăng ký đúng grant**, negative với client không được phép.

### 9.2. Custom grant và token exchange

Nếu thêm `urn:ietf:params:oauth:grant-type:token-exchange` theo RFC 8693, cần có converter parse `grant_type`, provider xử lý policy, RegisteredClient được phép, token generator/state phù hợp và positive/negative tests. Chỉ sau đó mới chủ động quảng bá grant. Thêm chuỗi vào metadata **không tự tạo provider**.

### 9.3. Response type khác grant type

`response_types_supported=["code"]` nói authorization endpoint trả authorization code. `grant_types_supported=["authorization_code"]` nói token endpoint cho đổi code lấy token. Không tự thêm `token` hay `id_token` response type khi server chỉ hỗ trợ Authorization Code Flow.

## 10. PKCE: metadata và enforcement phải đồng hành

Metadata PKCE có thể chứa:

~~~json
{
  "code_challenge_methods_supported": ["S256"]
}
~~~

Trường này công bố các PKCE methods AS hỗ trợ; nó **không chứng minh** mọi client đều bị bắt buộc dùng PKCE. Yêu cầu PKCE có thể phụ thuộc `ClientSettings.requireProofKey`, loại client và chính sách hệ thống.

### 10.1. Positive test

1. Client hợp lệ gửi `response_type=code` với `code_challenge_method=S256`.
2. Authorization endpoint chấp nhận `redirect_uri` và `code_challenge`.
3. Token endpoint nhận `code_verifier` tương ứng.
4. AS cấp token response đúng protocol.

### 10.2. Negative tests

| Trường hợp | Kết quả |
|---|---|
| Authorization code bind challenge nhưng thiếu verifier | Bị từ chối |
| Verifier không khớp challenge | Bị từ chối |
| Method ngoài allowlist của deployment | Bị từ chối |
| Client bắt buộc PKCE nhưng request không có challenge | Bị từ chối |
| Authorization code dùng lại | Bị từ chối |

Nếu metadata quảng bá `plain`, cần xác minh policy thực sự cho phép method đó. Nếu tổ chức chỉ cho S256, không nên quảng bá method ngoài allowlist chỉ vì thư viện có thể parse.

## 11. Client authentication methods và algorithms

Ví dụ OAuth2 metadata:

~~~json
{
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "token_endpoint_auth_signing_alg_values_supported": [
    "RS256",
    "PS256"
  ]
}
~~~

Đây chỉ là một deployment minh họa. Cần tách **cách xác thực OAuth2 Client** với **thuật toán ký client assertion**.

### 11.1. Ma trận phương thức

| Metadata value | Đặc điểm | Kiểm thử |
|---|---|---|
| `client_secret_basic` | Client credentials trong HTTP Basic | Secret đúng/sai, client ID đúng |
| `client_secret_post` | Client secret trong form body | Registration cho phép, log body được redaction |
| `client_secret_jwt` | JWT client assertion ký bằng shared secret | `aud`, `iss`, `sub`, `exp`, signature và replay |
| `private_key_jwt` | Client assertion ký bằng private key | Public JWK, signature, alg allowlist |
| `tls_client_auth` | mTLS với certificate theo registration | Certificate identity và chain validation |
| `self_signed_tls_client_auth` | Registered self-signed certificate | Certificate match và policy |
| `none` | Public client không có secret | Chỉ trong grant/endpoint cho phép |

Không quảng bá phương thức không có AuthenticationProvider/configuration hỗ trợ hoặc mà mọi RegisteredClient đều bị policy từ chối.

### 11.2. Token endpoint vs introspection endpoint

`introspection_endpoint_auth_methods_supported` và `revocation_endpoint_auth_methods_supported` (nếu có) không nhất thiết giống `token_endpoint_auth_methods_supported`. Ví dụ AS có public client cho Authorization Code + PKCE, nhưng introspection chỉ dành cho confidential Resource Server.

Không tự copy danh sách token endpoint auth methods sang introspection khi policy khác. Một endpoint trả 401 cho client thiếu credentials có thể hoàn toàn đúng.

### 11.3. ID Token signing không phải client assertion signing

`id_token_signing_alg_values_supported` (OIDC) mô tả thuật toán AS dùng ký ID Token. `token_endpoint_auth_signing_alg_values_supported` nói về thuật toán client assertion được chấp nhận ở token endpoint. DPoP proof signing lại là lớp khác. Mỗi danh sách phải phản ánh đúng implementation và allowlist của **mục đích tương ứng**.

## 12. Revocation và introspection: route phải đúng semantics

### 12.1. Token Revocation theo RFC 7009

Nếu metadata có `revocation_endpoint`, kiểm thử:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.com
Authorization: Basic REGISTERED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN_TO_REVOKE&token_type_hint=access_token
~~~

Chỉ thấy HTTP 200 chưa chứng minh token bị invalidated. Cần introspection hoặc thử gọi API sau revoke để xác minh state thay đổi đúng policy. Theo RFC 7009, token không tồn tại thường vẫn cho response thành công để giảm token enumeration.

### 12.2. Token Introspection theo RFC 7662

Nếu metadata công bố `introspection_endpoint`, kiểm thử:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.com
Authorization: Basic RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

Introspection response với token còn active:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "portal-web",
  "sub": "user-42",
  "exp": 1794850600
}
~~~

Sau revoke/expiry, request introspection được xác thực hợp lệ thường nhận `active=false`, không kèm claim nhạy cảm. Phải phân biệt lỗi `invalid_client` với **token không active**: một bên là lỗi client authentication, một bên là trạng thái token.

### 12.3. Một route được bảo vệ không phải route bị mất

Không gửi GET/anonymous vào introspection hoặc revocation rồi kết luận chúng không tồn tại chỉ vì 401/405. Chạy POST đúng dạng, client credential hợp lệ và credential sai; xác minh cả success semantics lẫn security enforcement.

## 13. PAR: công bố endpoint và yêu cầu bắt buộc

**Pushed Authorization Requests (RFC 9126)** cho phép client gửi authorization parameters qua back channel, nhận một `request_uri` ngắn hạn rồi redirect browser với `request_uri` đó.

Metadata khi hỗ trợ PAR có thể chứa:

~~~json
{
  "pushed_authorization_request_endpoint":
    "https://identity.example.com/oauth2/par",
  "require_pushed_authorization_requests": false
}
~~~

Hai thông tin khác nhau:

- `pushed_authorization_request_endpoint`: PAR endpoint được quảng bá.
- `require_pushed_authorization_requests`: yêu cầu authorization requests phải sử dụng PAR theo metadata/policy.

**Có PAR endpoint không đồng nghĩa mọi client đều bắt buộc dùng PAR.** Nếu công bố `require_pushed_authorization_requests=true`, negative test phải chứng minh direct authorization request không dùng PAR bị từ chối theo policy bắt buộc.

### 13.1. Kiểm thử PAR thật

1. Client được đăng ký đúng method/grant gửi POST tới PAR.
2. AS xác minh client, redirect URI, PKCE và các authorization parameters.
3. AS trả `201 Created` kèm `request_uri` và `expires_in`.
4. Browser chuyển tới authorization endpoint với `client_id` và `request_uri`.
5. AS từ chối `request_uri` hết hạn, sai client hoặc không hợp lệ.

Đừng chỉ assert rằng JSON metadata có URL PAR; phải chạy flow và kiểm tra ràng buộc bảo mật của reference.

## 14. Device flow, Token Exchange, DPoP, mTLS và các extension

| Capability | Điểm metadata | Kiểm tra thực tế |
|---|---|---|
| **Device Authorization (RFC 8628)** | `device_authorization_endpoint`, device grant | Device code/user code, verification, polling/expiry |
| **Token Exchange (RFC 8693)** | Token exchange trong `grant_types_supported` | Converter/provider, subject/actor token policy |
| **DPoP (RFC 9449)** | `dpop_signing_alg_values_supported` khi được công bố | Proof signature, `htm`/`htu`/`iat`/`jti`/`ath`, `cnf.jkt`, RS verification |
| **mTLS (RFC 8705)** | mTLS auth methods và `tls_client_certificate_bound_access_tokens` khi có | Certificate binding và verification |
| **Authorization response issuer (RFC 9207)** | `authorization_response_iss_parameter_supported` | `iss` trong authorization response khớp issuer |
| **JWT-Secured Authorization Request (RFC 9101)** | Request Object capabilities | Signed Request Object, validation/precedence |
| **RP-Initiated Logout (OIDC)** | `end_session_endpoint` | Session/redirect allowlist |

### 14.1. DPoP advertised vs enforced

Nếu quảng bá DPoP proof algorithms, AS cần xác minh proof ở token endpoint và phát token sender-constrained phù hợp, chẳng hạn `token_type=DPoP` với confirmation binding `cnf.jkt`. Resource Server cũng phải thực thi proof verification khi nhận access token. Metadata của AS **không tự bật DPoP ở mọi Resource Server**.

Thử proof sai chữ ký, sai `htm`/`htu`, proof quá cũ, replay và access token binding mismatch. Nếu chỉ kiểm tra chuỗi algorithm trong metadata, ta chưa chứng minh DPoP hoạt động.

### 14.2. Token Exchange advertised vs provider

Nếu `grant_types_supported` liệt kê `urn:ietf:params:oauth:grant-type:token-exchange`, token endpoint cần thực sự có converter, provider, RegisteredClient grant permission và policy cho subject/actor token. Test thêm audience ngoài allowlist và invalid subject token.

### 14.3. Capability phụ thuộc phiên bản

Các extension được Spring Authorization Server/Spring Security bổ sung theo từng phiên bản; API có thể đổi khi Spring Authorization Server được tích hợp sâu hơn vào Spring Security. Không lấy tài liệu “latest” rồi sao chép vào BOM cũ. Kiểm tra version dependency, configuration, runtime metadata và positive/negative tests.

## 15. Custom metadata: dùng đúng extension point

Spring Authorization Server có điểm tùy chỉnh cho OAuth2 AS Metadata và OIDC Provider Configuration trong các phiên bản hỗ trợ. Có thể thêm custom claim, nhưng **không thể chỉ dùng customizer để bật endpoint/provider còn thiếu**.

### 15.1. OAuth2 Authorization Server Metadata customizer

Ví dụ DSL của Spring Authorization Server 1.5.x:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .authorizationServerMetadataEndpoint(metadata -> metadata
                .authorizationServerMetadataCustomizer(builder -> builder
                    .claim("service_documentation",
                        "https://docs.example.com/authz"))
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

`service_documentation` là custom metadata field minh họa, không phải claim bắt buộc của RFC 8414. Cần kiểm tra kiểu builder/method theo BOM thực tế. Không dùng customizer để sửa một URL không tồn tại thành một URL khác chỉ nhằm làm bài test pass.

### 15.2. OIDC Provider Configuration customizer

Khi OIDC được bật, có thể tùy chỉnh OP document:

~~~java
http.with(authorizationServer, server -> server
    .oidc(oidc -> oidc
        .providerConfigurationEndpoint(provider -> provider
            .providerConfigurationCustomizer(builder -> builder
                .claim("service_documentation",
                    "https://docs.example.com/oidc"))
        )
    )
);
~~~

Đây là fragment để đưa vào SecurityFilterChain đầy đủ, không phải toàn bộ ứng dụng. Không gọi OIDC customizer rồi cho rằng UserInfo hoặc Dynamic Client Registration đã tự động được bật.

### 15.3. Những thay đổi metadata không được làm tùy tiện

Không hardcode:

- `userinfo_endpoint` khi chưa bật UserInfo;
- `registration_endpoint` khi Dynamic Client Registration vẫn tắt;
- `id_token_signing_alg_values_supported` khác signing algorithm thực tế;
- `token_endpoint_auth_methods_supported` khác Client Authentication Provider thực tế;
- `grant_types_supported` chứa grant chưa deploy;
- `issuer` khác `AuthorizationServerSettings` và JWT `iss`;
- `jwks_uri` trỏ tới set không chứa public key đang ký.

**Sửa đúng:** bật hoặc sửa feature implementation, chứng minh behavior rồi cập nhật metadata nếu cần.

## 16. Smoke test qua public reverse proxy

MockMvc kiểm tra bên trong ứng dụng nhưng không chứng minh ingress, TLS và public DNS hoạt động đúng. Cần một bài smoke test từ môi trường giống client thật:

~~~bash
curl --fail-with-body -sS \
  https://identity.example.com/.well-known/oauth-authorization-server

curl --fail-with-body -sS \
  https://identity.example.com/.well-known/openid-configuration

curl --fail-with-body -sS \
  https://identity.example.com/oauth2/jwks
~~~

Chỉ gọi OIDC document nếu OP thực sự được bật; các URL còn lại phải lấy theo public metadata của deployment.

### 16.1. Kiểm tra redirect, TLS và JSON

- Status 200 cho discovery/JWKS hợp lệ.
- Content type JSON, không phải HTML hoặc `302 /login`.
- Public issuer là HTTPS URL ổn định.
- Không lộ internal hostname, port hoặc private IP.
- TLS hostname/certificate hợp lệ.
- Không đòi browser session hay cookie để tải metadata/JWKS.
- Endpoint URL đã công bố có thể truy cập được từ Resource Server bên ngoài cluster.

### 16.2. Context path phải khớp

Với public issuer `https://identity.example.com/auth`, các URL được công bố có thể như:

~~~json
{
  "issuer": "https://identity.example.com/auth",
  "authorization_endpoint":
    "https://identity.example.com/auth/oauth2/authorize",
  "token_endpoint":
    "https://identity.example.com/auth/oauth2/token",
  "jwks_uri":
    "https://identity.example.com/auth/oauth2/jwks"
}
~~~

Đây là ví dụ deployment; cần kiểm tra route thật trên proxy và servlet context, không mặc định settings relative path tự chèn prefix đúng.

### 16.3. Không tin forwarded header của caller

Public endpoint URLs phải lấy từ cấu hình hoặc proxy-trust-aware resolver, không phụ thuộc `X-Forwarded-Host` tùy ý do client gửi. Gateway phải strip/rewrite header từ Internet, AS chỉ tin proxy đã allowlist. Test Host-header injection để tránh metadata poisoning.

## 17. Kiểm thử metadata bằng MockMvc

Integration test nên đi qua SecurityFilterChain thật và beans config thật, không mock toàn bộ JSON metadata.

### 17.1. Kiểm tra OAuth2 metadata cơ bản

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationServerMetadataTests {

    @Autowired
    MockMvc mvc;

    @Test
    void oauth2MetadataMatchesConfiguredIssuerAndEndpoints()
            throws Exception {
        mvc.perform(get("/.well-known/oauth-authorization-server"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.issuer")
                .value("https://identity.example.com"))
            .andExpect(jsonPath("$.authorization_endpoint")
                .value("https://identity.example.com/oauth2/authorize"))
            .andExpect(jsonPath("$.token_endpoint")
                .value("https://identity.example.com/oauth2/token"));
    }
}
~~~

Đây là khung test yêu cầu đầy đủ beans AS/issuer. Nếu deployment dùng endpoint custom, expected value phải lấy từ contract chính thức thay vì hardcode route mặc định.

### 17.2. OIDC metadata khi bật OIDC

~~~java
@Test
void oidcProviderMetadataContainsJwksAndIdTokenAlgorithms()
        throws Exception {
    mvc.perform(get("/.well-known/openid-configuration"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.issuer")
            .value("https://identity.example.com"))
        .andExpect(jsonPath("$.jwks_uri")
            .value("https://identity.example.com/oauth2/jwks"))
        .andExpect(jsonPath("$.id_token_signing_alg_values_supported")
            .isArray());
}
~~~

Test chỉ áp dụng profile có OIDC. Cần lấy ID Token thật, so `alg`/`kid` với JWKS và verify chữ ký; việc mảng algorithms không rỗng chưa chứng minh signer đã khớp.

### 17.3. Vắng mặt của feature không bật

Ví dụ OIDC bật nhưng Dynamic Client Registration tắt:

~~~java
@Test
void metadataDoesNotAdvertiseDisabledRegistration()
        throws Exception {
    mvc.perform(get("/.well-known/openid-configuration"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registration_endpoint").doesNotExist());
}
~~~

Với profile không bật OIDC, không dùng test này như thể OP discovery luôn phải có.

### 17.4. Kiểm tra PKCE advertised method

~~~java
@Test
void metadataAdvertisesS256() throws Exception {
    mvc.perform(get("/.well-known/oauth-authorization-server"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.code_challenge_methods_supported")
            .isArray());
}
~~~

Sau đó parse mảng methods và assert có `S256` nếu đây là capability đã xác nhận. Một test khác phải chạy Authorization Code + PKCE thật và test sai verifier. Không phụ thuộc hoàn toàn vào snapshot JSON.

## 18. Bộ kiểm thử dựa trên capabilities đã công bố

| Metadata field | Bài test phải có khi field xuất hiện |
|---|---|
| `authorization_endpoint` | Authorization + invalid redirect negative |
| `token_endpoint` | POST grant thành công và auth sai |
| `jwks_uri` | GET public JWKS, chữ ký JWT, private-key leak scan |
| `revocation_endpoint` | POST revoke, kiểm tra token state sau revoke |
| `introspection_endpoint` | POST active/inactive, client auth |
| `pushed_authorization_request_endpoint` | PAR success, `request_uri` binding/expiry |
| `device_authorization_endpoint` | Device code, user verification, polling/expiry |
| `userinfo_endpoint` | UserInfo token/scope/consent |
| `registration_endpoint` | Registration authorization và validation |
| `dpop_signing_alg_values_supported` | DPoP proof/binding/nonce/RS |
| `code_challenge_methods_supported` | PKCE success + verifier negative |
| `token_endpoint_auth_methods_supported` | Một client fixture cho mỗi auth method advertised |

### 18.1. Tập clients đại diện

~~~text
web-client          -> authorization_code, confidential auth
mobile-public       -> authorization_code + PKCE, no secret
machine-client      -> client_credentials
private-key-client  -> private_key_jwt
resource-server     -> introspection credentials
device-client       -> device grant, nếu có
par-client          -> PAR, nếu có
~~~

Một test phải chứng minh thành công cho client được phép và từ chối client không được phép. Đây là cách đối chiếu global metadata với per-client policy.

### 18.2. Không kiểm thử mọi endpoint bằng GET

Token, introspection, revocation và PAR có semantics POST. Một GET trả 401/405 không đủ để kết luận capability absent. Hãy dùng đúng protocol request fixture, không suy luận từ status code đơn lẻ.

### 18.3. Test thuật toán bằng token hoặc proof thật

Nếu OP metadata có RS256, lấy ID Token thật và verify chữ ký. Nếu công bố `private_key_jwt`, tạo client assertion ký thật và thử bad audience/expired assertion. Nếu công bố DPoP, thử proof sai method/URI/token binding. Chỉ so chuỗi algorithm trong JSON là chưa đủ.

## 19. Metadata consistency trong cluster và rolling deployment

Authorization Server production thường chạy nhiều nodes, nhiều availability zones và qua load balancer. Một node mới có endpoint/grant mới trong khi node cũ chưa cập nhật có thể khiến metadata **đúng trên node A nhưng sai trên node B**. Client discovery được ở node A nhưng request tiếp theo lại đến node B và nhận lỗi.

### 19.1. Những thuộc tính cần đồng bộ

- Public `issuer` và endpoint URLs;
- Các metadata fields và danh sách capabilities công bố;
- Signing key set, current `kid` và key rotation policy;
- RegisteredClient registrations, client authentication methods;
- Grant converters/providers, OIDC/PKCE/PAR/DPoP policy;
- Token/authorization persistence và revocation state;
- Proxy settings, context path, TLS routing và ingress rules.

### 19.2. So sánh node bằng canonical metadata

Một health check có thể GET discovery trên từng node qua một kênh test nội bộ được bảo vệ, parse JSON rồi canonicalize thành cùng thứ tự field/mảng theo semantics. So sánh những trường được kỳ vọng giống nhau; không so raw JSON string nếu serializer đổi thứ tự mà ý nghĩa không thay đổi.

~~~text
node-a:
  issuer = https://identity.example.com
  grants = authorization_code, refresh_token, client_credentials
  jwks_uri = https://identity.example.com/oauth2/jwks

node-b:
  issuer = https://identity.example.com
  grants = authorization_code, refresh_token
  jwks_uri = https://identity.example.com/oauth2/jwks

=> DRIFT: node-b chưa hỗ trợ hoặc chưa quảng bá client_credentials
~~~

Phát hiện mismatch là điểm khởi đầu; vẫn phải dùng runtime tests xác định tính năng thiếu ở node nào.

### 19.3. Release order khi thêm một capability

Một trình tự an toàn:

1. Triển khai converter/provider/endpoint và chính sách bảo mật cho capability mới ở tất cả nodes hoặc canary được kiểm soát.
2. Kiểm thử protocol positives và security negatives.
3. Chạy smoke tests qua proxy/load balancer, xác minh rollout nhất quán.
4. Sau khi capability sẵn sàng, mới **quảng bá metadata**.
5. Giám sát lỗi client và cho phép rollback metadata nếu cần.

Khi loại bỏ một capability, làm ngược lại theo deprecation/migration plan: ngừng quảng bá có kiểm soát, thông báo client, đợi giai đoạn chuyển đổi rồi mới xóa endpoint/provider. Không xóa route ngay khi còn client dựa vào metadata cũ.

### 19.4. Cache metadata và JWKS

Client/Resource Server có thể cache discovery và JWKS. Nếu thay endpoint URLs hoặc algorithms trong một lần deploy, metadata mới có thể chưa đến tất cả client. Cần compatibility window, cache headers phù hợp và kế hoạch rollout. Riêng key rotation phải công bố public key mới trước khi ký bằng key mới và giữ public key cũ trong thời gian overlap.

## 20. Security review cho discovery và metadata

Metadata là dữ liệu thường được công khai, nhưng nội dung có thể ảnh hưởng trực tiếp đến trust decisions của client và việc gửi token/credential.

### 20.1. Metadata poisoning và Host-header injection

Nếu AS tự dựng `issuer` hoặc `token_endpoint` từ `Host`/`X-Forwarded-Host` không được kiểm soát, attacker có thể khiến discovery công bố domain của họ. Client thiếu kiểm tra trust anchor có thể gửi client secret, authorization code hoặc token đến URL không đáng tin.

Kiểm soát:

- Cấu hình public issuer/endpoint URLs ổn định;
- Allowed hosts và trusted proxies rõ ràng;
- Gateway loại bỏ forwarded headers do client tự khai;
- Không dùng URL do token header, query parameter hoặc metadata khác không đáng tin chỉ định làm issuer;
- Resource Server/Client chỉ tải metadata từ issuer đã được cấu hình tin cậy.

### 20.2. Không quảng bá thuật toán không an toàn

Không tuyên bố `none` là thuật toán ký ID Token trong deployment yêu cầu signed token. Không để JWT header tùy ý quyết định algorithm; verifier cần allowlist. Nếu metadata khai RS256 nhưng token thực tế được ký theo algorithm ngoài policy, cần sửa signer/configuration chứ không nới lỏng verifier để cho qua.

### 20.3. Public discovery khác public administrative API

Discovery/JWKS có thể public GET, còn introspection/revocation cần client authentication, Dynamic Client Registration cần policy riêng, quản trị key/clients cần phân quyền nghiêm. Không suy ra rằng “metadata public” đồng nghĩa toàn bộ endpoints trong metadata được phép truy cập anonymous.

### 20.4. False assurance từ metadata

Metadata có thể nói hỗ trợ PKCE, DPoP, PAR hoặc mTLS nhưng không đảm bảo:

- PKCE được bắt buộc cho client thuộc policy;
- DPoP proof được xác minh và access token có `cnf.jkt` đúng;
- PAR bắt buộc khi `require_pushed_authorization_requests` được công bố true;
- mTLS-bound access token được Resource Server verify certificate binding;
- Token exchange được kiểm tra actor/subject/audience đúng policy.

Chỉ negative tests và end-to-end protocol validation mới chứng minh enforcement thật.

## 21. Vận hành và cảnh báo metadata drift

| Tín hiệu | Ý nghĩa | Cảnh báo/kết quả cần theo dõi |
|---|---|---|
| Discovery status/latency | Endpoint discovery có sẵn không? | 5xx, TLS error, latency tăng |
| Unexpected `issuer` | Sai domain/tenant/proxy | Exact mismatch với expected contract |
| Metadata URL 404/302 | Route hoặc filter chain sai | Smoke check failed |
| Missing active `kid` in JWKS | Key publish/rotation lỗi | JWT signature failures |
| `unsupported_grant_type` tăng | Grant advertised nhưng provider/registration thiếu | So metadata và logs |
| `invalid_client` tăng | Advertised auth method không khả dụng | Phân nhóm theo phương thức |
| PKCE verification failures | Client config/policy lệch | Spike `invalid_grant` |
| PAR `request_uri` errors | PAR store/TTL/cluster lỗi | `invalid_request_uri` tăng |
| DPoP binding failures | AS/RS support lệch | 401 và proof errors tăng |
| Introspection after revoke còn active | Cache/store consistency | Vượt revocation freshness SLA |
| Per-node metadata mismatch | Rolling deployment/config drift | Contract fingerprint khác nhau |

### 21.1. Không log thông tin nhạy cảm

Có thể ghi metadata version, issuer, endpoint names và hash của contract. Không ghi raw access token, authorization code, client secret, private key, DPoP proof, JWT assertion hay request body chứa credential. Với introspection, chỉ ghi correlation ID và aggregate metrics theo privacy policy.

### 21.2. Contract fingerprint

Một hệ thống có thể canonicalize các trường metadata quan trọng rồi tính hash để phát hiện thay đổi:

~~~text
contractFields = {
  issuer,
  authorization_endpoint,
  token_endpoint,
  jwks_uri,
  response_types_supported,
  grant_types_supported,
  token_endpoint_auth_methods_supported,
  code_challenge_methods_supported,
  optional_feature_endpoints
}

fingerprint = sha256(canonical_json(contractFields))
~~~

Đây là pseudocode; phải định nghĩa canonicalization rõ ràng, bao gồm cách xử lý arrays không có thứ tự ý nghĩa. Hash giúp phát hiện drift nhưng **không thay thế behavior tests**, vì hai nodes có thể công bố metadata giống nhau dù provider của một node bị lỗi.

## 22. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Client báo issuer mismatch | Discovery issuer khác expected hoặc JWT `iss` | Exact string, public issuer settings, proxy |
| Resource Server không tạo JwtDecoder | `jwks_uri` thiếu hoặc URL không tải được | JWKSource, GET JWKS, issuer trust |
| JWKS redirect login | Wrong SecurityFilterChain/matcher/order | Public JWKS route, entry point |
| Grant advertised nhưng token endpoint báo unsupported | Provider chưa có, sai converter hoặc rollout lệch | Converter/provider/registration + per-node tests |
| `private_key_jwt` advertised nhưng `invalid_client` | Client assertion validation hoặc auth method sai | JWK, `aud`/`exp`/alg/registration |
| OIDC Client không tìm được UserInfo | OIDC chưa bật hoặc metadata thiếu route | `oidc(...)`, UserInfo integration test |
| ID Token chữ ký không verify được | Active signing key vắng trong JWKS | `kid`, key source, rotation/cache |
| PAR URL có nhưng trả 404 | Filter hoặc proxy route chưa triển khai | POST PAR với client credentials |
| PAR bắt buộc nhưng direct request vẫn thành công | Metadata requirement không được enforce | Direct authorization negative test |
| PKCE method advertised nhưng code exchange không kiểm verifier | Policy/provider customization sai | Wrong/missing verifier negative test |
| localhost OK nhưng production lỗi | Public host/path/TLS mismatch | External smoke test qua ingress |
| Metadata cũ sau deploy | Client/CDN/cache stale | Cache-Control, rollout, compatibility |
| Node A OK, node B lỗi ngẫu nhiên | Metadata/providers/key set khác node | Per-node contract + flow tests |
| Revoked token vẫn `active:true` | Introspection cache quá lâu hoặc authorization store lệch | Cache TTL, shared persistence, revocation SLA |

### 22.1. Quy trình tìm nguyên nhân

1. Lấy discovery document từ **public URL** mà client đang dùng.
2. So sánh issuer, endpoint URLs và capabilities với expected deployment contract.
3. Tái tạo một HTTP request đúng protocol bằng client test được đăng ký phù hợp.
4. Kiểm tra response/body/header, không chỉ status.
5. Chạy negative test tương ứng để kiểm tra enforcement.
6. So sánh các nodes và kiểm tra cache/rolling deployment.
7. Sửa implementation/settings/metadata ở tầng phù hợp rồi chạy lại release gate.

Không vội sửa metadata JSON khi thực chất route/filter/provider đang thiếu; làm vậy có thể che giấu lỗi bảo mật.

## 23. Checklist trước khi phát hành production

1. **Issuer:** OAuth2/OIDC metadata `issuer` khớp public HTTPS identifier và JWT/ID Token `iss`?
2. **Discovery:** Well-known URLs trả JSON hợp lệ, không chuyển hướng login?
3. **OIDC:** Chỉ công bố OP Configuration khi OIDC thực sự bật và ID Token hoạt động?
4. **URLs:** Từng endpoint trong metadata trỏ đến route đúng qua reverse proxy?
5. **Methods:** Kiểm tra GET/POST, form body, client auth và response theo giao thức?
6. **JWKS:** Public GET, không lộ private fields, có public key cho `kid` đang ký?
7. **Grants:** Mỗi grant advertised có converter/provider thật và client được phép để test?
8. **Response types:** AS trả đúng type; không quảng bá implicit/hybrid nếu không triển khai?
9. **PKCE:** S256 hoạt động, sai/missing verifier bị từ chối khi áp dụng?
10. **Client auth:** Mỗi method advertised được thử với client fixture tương ứng?
11. **Introspection:** Xác thực Resource Server client, active/inactive semantics và claim disclosure đúng?
12. **Revocation:** Có client auth, token bị invalidate và phản ánh đúng ở introspection?
13. **PAR:** Endpoint, `request_uri` TTL/client binding và required-PAR policy khớp metadata?
14. **Device/Exchange:** Optional flow có provider/policy và E2E tests trước khi công bố?
15. **DPoP/mTLS:** AS issuance và RS token-binding validation tương thích?
16. **Algorithms:** ID Token signing/client assertion/DPoP methods khớp allowlist thực tế?
17. **Client policy:** Test phân biệt global server support với per-RegisteredClient grants?
18. **Proxy:** Trusted forwarded headers, không lộ internal hostname, không host-header injection?
19. **Cluster:** Các nodes có issuer/capabilities/keys nhất quán?
20. **Rollout:** Có contract snapshot, smoke tests và compatibility/deprecation window?
21. **Monitoring:** Alert metadata drift và key/flow errors, không log credential?
22. **Security:** Có negative tests redirect URI, PKCE, client auth, PAR, DPoP và unsupported grant?

## 24. Bài tập tình huống

**Tình huống A — OIDC chưa bật nhưng discovery vẫn công bố.** Một nhóm tạo route trả `/.well-known/openid-configuration` bằng JSON tự dựng, có `userinfo_endpoint`, trong khi application không bật OIDC configurer. Hãy liệt kê các test cần chạy, giải thích vì sao metadata sai và đề xuất trình tự sửa.

**Tình huống B — Reverse proxy sai issuer.** AS chạy nội bộ tại `http://as:9000`, nhưng client dùng `https://login.example.com`. Metadata công bố internal URL. Hãy thiết kế cấu hình `AuthorizationServerSettings`, proxy trust boundary và kiểm tra JWT `iss`.

**Tình huống C — PKCE advertised nhưng không enforce.** Metadata có `code_challenge_methods_supported=["S256"]`. Một public client vẫn đổi được code thành token dù `code_verifier` sai. Vì sao chỉ test authorization endpoint HTTP 302 không đủ?

**Tình huống D — PAR rollout lệch.** Node A quảng bá PAR, node B chưa có filter. Khi client follow metadata và requests bị load balancing, những lỗi nào có thể xuất hiện? Thiết kế release gate và rollout.

**Tình huống E — JWKS thiếu key mới.** OP metadata công bố RS256, ID Token mang `kid=K2`, JWKS hiện chỉ có K1. Hãy thiết kế thứ tự publish K2, signer switch, overlap và cache validation.

**Tình huống F — Token Exchange quảng bá quá sớm.** Server thêm token-exchange grant vào `grant_types_supported` nhưng chưa có `AuthenticationProvider` xử lý. Vì sao client gặp `unsupported_grant_type` và cần sửa theo trình tự nào?

**Tình huống G — Device flow cho một client nhưng metadata thiếu.** AS cho một kiosk client dùng device grant, nhưng metadata không công bố device authorization endpoint. Phân biệt giới hạn per-client với global capability và đưa ra cách test discovery.

**Gợi ý:** A cần bật và kiểm thử OP trước khi quảng bá; B cần public issuer ổn định và trusted proxy; C cần negative verifier tests; D cần deploy capability đồng đều trước khi advertise; E cần publish public K2 trước khi ký K2, giữ K1 đủ overlap; F cần converter/provider/registration/policy trước; G cần đồng bộ discovery với global capability thật trong khi vẫn giữ per-client restrictions.

## 25. Tổng kết

**Metadata nhất quán** nghĩa là discovery document mô tả chính xác các endpoint, grants, client authentication methods, algorithms và extensions **thực sự hoạt động trong deployment hiện tại**. Metadata là một giao diện tin cậy dành cho OAuth2 Clients, Resource Servers và OIDC Relying Parties; nó không tự triển khai giao thức.

Với Spring Authorization Server, cần đối chiếu **`AuthorizationServerSettings`, `OAuth2AuthorizationServerConfigurer`, OIDC configurer, `SecurityFilterChain`, `JWKSource`, `RegisteredClientRepository` và các token/grant providers**. Kiểm thử phải đi từ public issuer và metadata URLs tới protocol flows, security negatives, JWT/JWKS verification, per-client permissions và hoạt động nhiều node.

OAuth 2.0 Authorization Server Metadata theo RFC 8414 và OpenID Connect Discovery 1.0 là hai tài liệu liên quan nhưng khác mục đích; không quảng bá OIDC khi chỉ bật OAuth2. Với PKCE, PAR, DPoP, mTLS hoặc Token Exchange, phải chứng minh **enforcement thật**, không chỉ kiểm tra một field JSON.

Để duy trì nhất quán, hãy coi metadata như một **versioned release contract**: test trong CI, smoke test qua reverse proxy, so sánh cluster, kiểm soát issuer/host trust và có kế hoạch rollout/rollback/deprecation cho mọi thay đổi.

## 26. Tài liệu tham khảo

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): well-known discovery, issuer, endpoints, grants và authentication methods.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider Configuration, issuer, UserInfo và ID Token algorithms.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code Flow, ID Token và UserInfo.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization/token endpoints, grant types và client authentication.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): PKCE methods và code verifier.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Set/public keys.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection `active` semantics.
- [RFC 9126 — Pushed Authorization Requests (PAR)](https://www.rfc-editor.org/rfc/rfc9126): PAR metadata, `request_uri` và bắt buộc PAR.
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): device authorization.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange grant.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof và sender-constraining.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS token binding.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): authorization response issuer.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` và protocol configuration.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): AS metadata, OAuth2/OIDC endpoint configurers.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer discovery, JWKS URI và JWT validation.
