# Mô hình đe dọa và áp dụng OAuth 2.0 Security Best Current Practice

## Mục tiêu bài học

Authorization Server là thành phần bảo mật có ảnh hưởng trực tiếp đến mọi ứng dụng và API sử dụng token do nó phát hành. Một lỗi trong redirect URI validation, client authentication, signing key, refresh-token lifecycle hoặc audience validation có thể biến thành quyền truy cập trái phép trên nhiều hệ thống.

Bài học này xây dựng mô hình đe dọa cho OAuth 2.0/OpenID Connect Authorization Server và chuyển các khuyến nghị trong OAuth 2.0 Security Best Current Practice (RFC 9700) thành biện pháp thiết kế, cấu hình và vận hành với Spring Authorization Server 1.5.8 và Spring Security 6.5.x.

Trọng tâm là bảo vệ Authorization Code, client authentication, redirect, token issuance, refresh, introspection, revocation, discovery và key management. Bài cũng đề cập PKCE, Pushed Authorization Requests (PAR), DPoP, mutual TLS (mTLS), session, CSRF, CORS, rate limiting và incident response.

Sau bài học, bạn có thể:

1. Xác định tài sản, tác nhân, trust boundary và attack surface của Authorization Server.
2. Phân tích authorization code interception/injection, redirect manipulation, mix-up, CSRF, token replay, refresh-token theft và client impersonation.
3. Áp dụng Authorization Code Grant với PKCE S256 và redirect URI exact matching.
4. Phân biệt public client với confidential client và chọn client authentication phù hợp.
5. Bảo vệ access token/refresh token bằng TTL, rotation, revocation, DPoP hoặc mTLS.
6. Sử dụng PAR để giảm lộ authorization request parameters qua front channel.
7. Cấu hình Spring Authorization Server endpoints và Spring Security filter chains an toàn.
8. Bảo vệ login, consent, session, CSRF, CORS và HTTP response headers.
9. Thiết kế key lifecycle, metadata, discovery, logging, rate limit và quy trình ứng phó sự cố.
10. Xây dựng threat-based test matrix để xác minh security controls.

> Phạm vi phiên bản: ví dụ dùng Spring Authorization Server 1.5.8 và Spring Security 6.5.x. RFC 9700 được công bố tháng 01/2025 và là Best Current Practice hiện hành cho OAuth 2.0. Các yêu cầu MUST/SHOULD trong RFC được giữ theo đúng ngữ nghĩa tiêu chuẩn; ví dụ cấu hình cần được kiểm thử với deployment cụ thể.

## 1. Vì sao cần threat model cho Authorization Server?

Authorization Server không chỉ là nơi tạo JWT. Nó là bên quyết định:

- Client nào được phép yêu cầu quyền.
- Người dùng nào có thể cấp consent.
- Scope và resource nào được cấp cho client.
- Token nào được phát hành, token đó có audience nào và sống bao lâu.
- Client nào được phép đổi refresh token, revoke hoặc introspect token.
- Khóa nào được dùng để ký và Resource Server nào được phép tin khóa đó.

Khi Authorization Server bị xâm phạm, attacker có thể phát hành token hợp lệ về mặt chữ ký nhưng mang quyền trái phép. Vì vậy, xác minh chữ ký thành công chỉ chứng minh token được ký bằng một khóa được tin cậy; nó không chứng minh token có audience, scope, subject hoặc mục đích đúng.

RFC 9700 cập nhật mô hình đe dọa cũ của OAuth 2.0, làm rõ các cuộc tấn công đã xuất hiện trong triển khai thực tế và loại bỏ một số mode kém an toàn. BCP này áp dụng cho client, Authorization Server và Resource Server; bảo mật chỉ đạt được khi các thành phần phối hợp đúng.

## 2. Xác định tài sản cần bảo vệ

Trước khi chọn biện pháp, hãy liệt kê tài sản và hậu quả khi tài sản bị lộ, sửa đổi hoặc mất khả dụng.

| Tài sản | Giá trị bảo mật | Hậu quả khi bị xâm phạm |
|---|---|---|
| Authorization code | Bí mật ngắn hạn, dùng một lần | Attacker đổi code lấy token nếu thiếu PKCE/client binding |
| Access token | Credential truy cập API | Truy cập dữ liệu hoặc thực hiện hành động trái phép |
| Refresh token | Credential cấp access token mới | Chiếm quyền truy cập kéo dài và khó phát hiện |
| ID Token | Bằng chứng xác thực cho OIDC client | Giả mạo phiên đăng nhập nếu client xác minh sai |
| Client secret/private key | Credential xác thực client | Giả mạo client và xin token theo quyền client |
| Signing private key | Gốc tin cậy của JWT | Giả mạo token cho issuer bị ảnh hưởng |
| User session/cookie | Duy trì trạng thái đăng nhập và consent | Session hijacking, fixation hoặc CSRF |
| RegisteredClient/configuration | Client ID, redirect URI, grant, scope, auth method | Thay đổi policy để mở quyền hoặc chuyển code tới attacker |
| Authorization/consent store | Grant, token metadata, revocation state | Đọc/sửa authorization hoặc bỏ qua thu hồi |
| Issuer/JWKS/metadata | Định danh máy chủ và nguồn khóa xác minh | Mix-up, key substitution hoặc trust nhầm issuer |
| Audit/security events | Bằng chứng phát hiện và điều tra | Không thể xác định phạm vi sự cố |

Phân loại dữ liệu theo mức độ nhạy cảm. Không ghi raw authorization code, access token, refresh token, ID Token, client secret, private key hoặc DPoP proof vào log. Nếu cần correlation, dùng request ID, client ID, issuer, token ID đã được xử lý an toàn hoặc hash một chiều theo policy.

## 3. Tác nhân và trust boundary

### 3.1. Tác nhân

Threat model nên xét tối thiểu các tác nhân:

- Malicious client: client hợp lệ nhưng cố xin scope/audience vượt quyền hoặc lạm dụng grant.
- Compromised client: client secret, private key hoặc thiết bị lưu token đã bị đánh cắp.
- Malicious end-user: người dùng cố thao túng redirect, consent, account linking hoặc workflow.
- Network attacker: nghe lén, sửa đổi hoặc replay traffic khi TLS/proxy cấu hình sai.
- Compromised Resource Server: API nhận token sai audience hoặc làm lộ token.
- Rogue Authorization Server/IdP: issuer độc hại tìm cách gây mix-up hoặc đánh cắp code/token.
- Insider hoặc administrator bị chiếm quyền: sửa client registration, key, scope, redirect URI hoặc policy.
- Bot/DoS actor: tạo nhiều authorization, login, token, PAR hoặc introspection requests.

### 3.2. Trust boundary

| Boundary | Dữ liệu đi qua | Điều phải xác minh |
|---|---|---|
| Browser ↔ Authorization Server | Cookie, login form, authorization request/response | TLS, session, CSRF, state, redirect URI, nonce |
| Client ↔ Authorization Server | Client authentication, code, token, refresh, PAR | Client identity, grant permission, PKCE, replay |
| Authorization Server ↔ Resource Owner | Authentication, consent, MFA | Local authentication policy, consent integrity |
| Authorization Server ↔ Resource Server | Access token, introspection/JWKS | Issuer, signature, audience, scope, token status |
| Authorization Server ↔ KMS/HSM | Signing operation, key metadata | Service identity, key purpose, audit, rotation |
| Authorization Server ↔ database/cache | Client, authorization, consent, replay state | Tenant isolation, access control, integrity, availability |
| Application ↔ reverse proxy/ingress | Host, scheme, forwarded headers | Trusted proxy, canonical issuer, TLS termination |

Không mặc định tin dữ liệu chỉ vì nó đến từ mạng nội bộ. Các request từ proxy, service mesh, admin console hoặc background job vẫn cần xác thực và phân quyền.

### 3.3. Nhóm hóa threat theo STRIDE

| Nhóm | Ví dụ trong Authorization Server | Biện pháp tiêu biểu |
|---|---|---|
| Spoofing | Giả mạo client, issuer hoặc Resource Owner | Client authentication, issuer validation, MFA |
| Tampering | Sửa redirect URI, scope, consent hoặc authorization request | Exact matching, signed request/PAR, integrity checks |
| Repudiation | Phủ nhận việc cấp consent hoặc thay client policy | Audit event có actor, timestamp và correlation ID |
| Information disclosure | Lộ code, token, secret hoặc signing key | TLS, redaction, KMS/HSM, no-store |
| Denial of service | Flood login, token, PAR, introspection hoặc KMS | Rate limit, quota, bounded work, circuit breaker |
| Elevation of privilege | Xin scope/audience vượt quyền hoặc dùng token sai API | Least privilege, audience/scope validation, consent |

## 4. Luồng Authorization Code và attack surface

Authorization Code Flow tách việc tương tác với người dùng khỏi việc trao token cho client:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant B as Browser
    participant AS as Authorization Server
    participant U as Resource Owner
    participant RS as Resource Server
    C->>C: Generate state, nonce and PKCE verifier
    C->>B: Redirect with client_id, redirect_uri, scope, state, code_challenge
    B->>AS: Authorization Request
    AS->>AS: Validate client, redirect URI, scope and PKCE challenge
    AS->>B: Login / consent if required
    B->>U: Authenticate and present consent
    U->>B: Complete authentication / consent
    B->>AS: Continue authorization request
    AS->>AS: Create short-lived single-use code bound to client and redirect URI
    AS->>B: Redirect to registered redirect URI with code and state
    B->>C: Authorization response
    C->>C: Validate state / issuer response and recover verifier
    C->>AS: Token Request with code and code_verifier
    AS->>AS: Validate client, code, redirect URI and PKCE
    AS-->>C: Access token (+ refresh token if policy allows)
    C->>RS: Protected request with access token
    RS->>RS: Validate issuer, signature, audience and authorization
    RS-->>C: Protected resource
~~~

Các điểm dễ bị tấn công:

1. Authorization request bị sửa trước khi tới Authorization Server.
2. Redirect URI đưa code tới domain của attacker.
3. Authorization code bị chặn hoặc tiêm vào phiên của client khác.
4. Client gửi code tới nhầm Token Endpoint do mix-up.
5. Token bị lộ trong URL, browser history, log hoặc outbound request.
6. Refresh token bị replay sau khi bị đánh cắp.
7. Resource Server xác minh chữ ký nhưng bỏ qua audience hoặc token purpose.

Authorization Code Flow không tự an toàn chỉ vì dùng HTTPS. Mỗi bước cần ràng buộc client, browser transaction, issuer và resource đích.

## 5. BCP nền tảng: chọn grant type an toàn

RFC 9700 khuyến nghị dùng Authorization Code Grant thay cho các flow trả access token trực tiếp qua authorization response.

| Grant/flow | Định hướng bảo mật |
|---|---|
| Authorization Code + PKCE | Flow ưu tiên cho user authorization, cả public và confidential clients |
| Client Credentials | Dành cho workload/service-to-service; không đại diện người dùng |
| Device Authorization Grant | Dành cho thiết bị thiếu browser/input; cần user code, rate limit và polling interval |
| Refresh Token | Chỉ cấp khi cần; ràng buộc với client/resource/scope và phát hiện replay |
| Implicit Grant | Không dùng cho triển khai mới; access token đi qua front channel |
| Resource Owner Password Credentials | Không sử dụng; client không được thu thập mật khẩu người dùng để đổi token |

Không bật grant type chỉ vì framework hỗ trợ. Mỗi client chỉ nên có các grant type thực sự cần thiết. Việc cho phép client_credentials không có nghĩa client được phép dùng authorization_code hoặc refresh_token.

## 6. Redirect URI manipulation và open redirect

### 6.1. Redirect URI phải khớp chính xác

Attacker có thể tìm cách đăng ký hoặc gửi redirect URI gần giống redirect URI thật, ví dụ:

- https://client.example/callback.attacker.example
- https://client.example.evil.test/callback
- https://client.example/callback?next=https://evil.test
- Dùng wildcard hoặc prefix matching để chấp nhận host/path không được đăng ký.

Authorization Server phải so sánh redirect URI với URI đã đăng ký bằng exact string matching theo RFC 9700, ngoại lệ về port chỉ áp dụng cho loopback redirect URI của native app. Không dùng startsWith, wildcard domain, regex lỏng hoặc chỉ kiểm tra hostname.

Ví dụ đăng ký client trong Spring Authorization Server:

~~~java
RegisteredClient portal = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("employee-portal")
        .clientSecret(passwordEncoder.encode(portalSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://portal.example.com/login/oauth2/code/internal")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .build();
~~~

Danh sách redirect URI phải được quản trị như cấu hình bảo mật. Thay đổi redirect URI production cần audit, quyền admin phù hợp và quy trình review.

### 6.2. Không xây open redirector

Open redirector là endpoint chuyển browser tới URL tùy ý lấy từ query parameter hoặc request body. Nếu client có endpoint như /continue?url=..., attacker có thể dùng endpoint đó để lấy authorization code hoặc access token qua redirect chain.

Chỉ redirect tới destination được allowlist. Nếu cần lưu trang người dùng định mở trước khi login, lưu path nội bộ đã chuẩn hóa trong session/server-side state; không chấp nhận absolute URL tùy ý.

### 6.3. Không để redirect URI trở thành SSRF

Redirect URI là đích browser, nhưng các tính năng discovery, dynamic registration, JWKS retrieval hoặc webhook có thể khiến server tự gọi URL do client cung cấp. Không dùng redirect URI làm URL để backend fetch. Với URL do client quản lý, áp dụng allowlist, chặn loopback/private/link-local IP, kiểm tra DNS rebinding và giới hạn redirect khi HTTP client follow redirect.

### 6.4. Không chuyển tiếp thông tin đăng nhập qua redirect

Sau khi browser POST username/password hoặc dữ liệu đăng nhập tới Authorization Server, response redirect không được làm browser gửi lại body chứa credential tới redirect URI của client. RFC 9700 yêu cầu Authorization Server tránh vô tình forward credential khi redirect request có thể chứa thông tin đăng nhập. Với POST login/consent, dùng response semantics chuyển sang GET (thường là HTTP 303 See Other) và kiểm thử cả browser lẫn reverse proxy; không dùng 307/308 cho redirect có thể mang credential body.

## 7. Authorization code interception và injection: PKCE

PKCE ràng buộc authorization code với một verifier do client tạo khi bắt đầu transaction. Client gửi code_challenge ở Authorization Endpoint và gửi code_verifier ở Token Endpoint.

### 7.1. Dùng S256

Client tạo code_verifier ngẫu nhiên, đủ entropy, sau đó tính:

~~~text
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

Không dùng plain trong triển khai mới. Với S256, verifier không xuất hiện trong authorization request.

### 7.2. Bắt buộc PKCE ở Authorization Server

Spring Authorization Server hỗ trợ cấu hình PKCE bằng ClientSettings.requireProofKey(true):

~~~java
RegisteredClient publicClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("mobile-public-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("com.example.app:/oauth2/callback")
        .scope(OidcScopes.OPENID)
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();
~~~

Public client không thể giữ client secret một cách bí mật. PKCE là lớp bảo vệ bắt buộc cho Authorization Code Grant của public clients. RFC 9700 cũng khuyến nghị PKCE cho confidential clients.

Authorization Server phải:

- Hỗ trợ PKCE và phương thức S256.
- Lưu challenge cùng authorization code.
- Yêu cầu verifier ở Token Endpoint khi authorization request có challenge.
- Từ chối verifier sai hoặc thiếu.
- Không chấp nhận request có verifier nếu authorization request gốc không có challenge; điều này ngăn PKCE downgrade.
- Ràng buộc code với client, redirect URI và transaction tương ứng.

Không dùng một verifier/challenge cố định cho nhiều lần đăng nhập.

## 8. CSRF, state, nonce và mix-up

### 8.1. State gắn với browser transaction

State là giá trị ngẫu nhiên do client tạo và gắn với user-agent/session khi bắt đầu authorization request. Client phải kiểm tra giá trị trả về có khớp transaction ban đầu. Không dùng state tĩnh, đoán được hoặc chỉ mã hóa một URL mà không bảo vệ integrity.

PKCE có thể cung cấp bảo vệ CSRF cho OAuth client khi client đã xác nhận Authorization Server hỗ trợ và thực thi PKCE. Trong OIDC, nonce gắn ID Token với authentication request. Tùy flow, client vẫn nên duy trì state để liên kết transaction và phục hồi application state.

### 8.2. Nonce trong OIDC

Client tạo nonce mới cho mỗi authentication request. Sau khi nhận ID Token, client xác minh chữ ký, issuer, audience, thời hạn và so sánh claim nonce với nonce đã lưu. Không tái sử dụng nonce giữa các transaction.

### 8.3. Mix-up attack khi có nhiều Authorization Server

Nếu client hỗ trợ nhiều issuer, attacker có thể khiến client gửi authorization code hoặc client credential tới Token Endpoint của issuer khác. Đây là mix-up attack.

RFC 9700 yêu cầu client có biện pháp chống mix-up. Ưu tiên:

1. Dùng authorization response iss theo RFC 9207 và so sánh chính xác với issuer đã chọn cho transaction.
2. Hoặc dùng issuer identifier đáng tin cậy trong response như ID Token/JARM theo profile phù hợp.
3. Nếu không có các phương án trên, dùng redirect URI riêng cho từng issuer và kiểm tra callback URI thực nhận.

Client phải lưu issuer đã chọn cho từng authorization request, gắn với browser session. Không lấy token endpoint từ query parameter hoặc response chưa xác minh.

### 8.4. CSRF trong giao diện Authorization Server

CSRF của OAuth redirect flow và CSRF của form login/consent là hai vấn đề liên quan nhưng khác nhau. Authorization Server có thể dùng session cookie cho login và consent UI; browser tự gửi cookie nên các thao tác thay đổi trạng thái phải được bảo vệ.

Spring Security bật CSRF protection cho servlet application theo mặc định. Không tắt CSRF toàn cục chỉ để làm Token Endpoint hoạt động. Nếu cần loại trừ endpoint back-channel, phải xác định matcher thật hẹp, kiểm tra endpoint không dùng browser cookie làm credential và giữ CSRF cho login, consent, logout, admin UI.

GET, HEAD, OPTIONS và TRACE phải không làm thay đổi trạng thái ứng dụng. Không thực hiện approve consent, logout hoặc revoke bằng GET.

## 9. Client authentication và quản lý client credentials

### 9.1. Public và confidential client

| Loại client | Có thể giữ secret? | Biện pháp |
|---|---|---|
| Native/mobile app | Không thể bảo vệ secret tĩnh trong binary | Public client, Authorization Code + PKCE, external browser |
| SPA chạy trong browser | Không thể bảo vệ secret | Public client + PKCE; cân nhắc Backend-for-Frontend |
| Server-side web application | Có thể giữ secret trong server | Confidential client, client authentication và PKCE |
| Service-to-service workload | Có thể giữ credential trong secret manager/KMS | Confidential client, private_key_jwt hoặc mTLS |

Không nhúng client secret vào JavaScript, mobile binary, desktop binary, container image hoặc repository.

### 9.2. Chọn phương thức xác thực client

| Method | Cơ chế | Khuyến nghị |
|---|---|---|
| none | Public client, không client secret | Chỉ cho public clients; kết hợp PKCE |
| client_secret_basic | Secret trong HTTP Basic Authorization header | Phù hợp confidential client khi secret được bảo vệ |
| client_secret_post | Secret trong form body | Tránh nếu có lựa chọn khác vì body dễ bị log |
| private_key_jwt | Client ký assertion JWT bằng private key | Ưu tiên khi có PKI/key lifecycle tốt |
| tls_client_auth | Client certificate được CA tin cậy xác thực | Phù hợp workload có PKI/mTLS |
| self_signed_tls_client_auth | Client dùng self-signed certificate đã đăng ký | Cần quy trình đăng ký và rotation certificate |

RFC 9700 khuyến nghị dùng asymmetric client authentication như private_key_jwt hoặc mTLS khi khả thi. Với private_key_jwt, assertion phải có issuer/subject là client ID theo profile, audience đúng Token Endpoint, thời hạn ngắn và jti chống replay.

### 9.3. Secret lifecycle

- Tạo secret ngẫu nhiên đủ entropy.
- Lưu secret đã hash bằng password encoder phù hợp; không lưu plaintext trong database.
- Không tái sử dụng cùng secret giữa client hoặc môi trường.
- Có thời hạn, quy trình rotate và overlap ngắn nếu cần.
- Thu hồi ngay khi nghi ngờ lộ secret.
- Giới hạn quyền đọc secret trong secret manager.
- Không log Authorization header hoặc client assertion.

### 9.4. Client registration là policy boundary

RegisteredClient cần giới hạn:

- Authorization grant types.
- Client authentication methods.
- Redirect URIs.
- Scopes.
- Client settings như PKCE và consent.
- Token settings như TTL, refresh-token reuse và token format.

Không cấp mọi grant type cho mọi client. Không để client tự gửi audience/resource tùy ý rồi Authorization Server phát token mà không kiểm tra policy.

## 10. Token theft, replay và refresh-token protection

### 10.1. Bearer token có rủi ro replay

Bearer access token có thể được dùng bởi bất kỳ bên nào sở hữu token. Nếu token bị copy khỏi log, browser storage, proxy trace, crash dump hoặc outbound request, attacker có thể dùng nó cho tới khi token hết hạn hoặc bị thu hồi.

Biện pháp:

- Chỉ truyền token qua TLS.
- Gửi access token trong Authorization Bearer header, không đặt trong URL/query string.
- Không ghi token vào log, tracing span, analytics hoặc error report.
- Dùng access token TTL ngắn theo risk profile.
- Giới hạn audience và scope.
- Dùng sender-constrained token cho hệ thống có rủi ro replay cao.
- Có quy trình revoke khi client/user/device bị compromise.

Toàn bộ Authorization Server endpoints, redirect URI web và back-channel phải được bảo vệ bằng TLS; không để authorization code hoặc token đi qua HTTP thường. Response chứa token phải có Cache-Control: no-store và Pragma: no-cache để browser/proxy không lưu credential vào cache.

### 10.2. Refresh token là credential dài hạn

Refresh token thường có giá trị lâu hơn access token. Nếu bị lộ, attacker có thể liên tục xin access token mới. Authorization Server chỉ nên cấp refresh token sau risk assessment và khi client thực sự cần duy trì phiên.

Refresh token phải được ràng buộc với client, scope và resource server đã được consent. Với confidential client, refresh token chỉ được sử dụng bởi đúng client đã được cấp và client phải authenticate khi refresh. Không cho refresh request mở rộng quyền vượt grant gốc.

### 10.3. Refresh token rotation

RFC 9700 yêu cầu refresh token của public clients phải được sender-constrain hoặc sử dụng rotation để phát hiện replay.

Với rotation:

1. Client gửi refresh token hiện tại.
2. Authorization Server phát access token mới và refresh token mới.
3. Refresh token cũ bị vô hiệu hóa.
4. Authorization Server giữ quan hệ lineage/family.
5. Nếu refresh token cũ bị dùng lại, server nhận diện replay và thu hồi token còn hiệu lực trong family theo policy.

Spring Authorization Server cấu hình phát refresh token mới qua TokenSettings.reuseRefreshTokens(false):

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofHours(8))
        .reuseRefreshTokens(false)
        .build();
~~~

Trong SAS, reuseRefreshTokens mặc định là true; production cần chủ động đánh giá và cấu hình. Tùy client type và phiên bản, public client không tự động được cấp refresh token; kiểm tra behavior của SAS 1.5.8 và không tự nới chính sách chỉ để giữ phiên lâu hơn.

Lưu ý: reuseRefreshTokens(false) yêu cầu SAS phát refresh token mới và vô hiệu hóa token cũ. Đây là nền tảng cho rotation, nhưng không nên mặc định rằng cấu hình này tự triển khai đầy đủ mọi chính sách phát hiện replay và thu hồi cả token family theo RFC 9700. Nếu cần family-wide revocation, hãy lưu lineage/quan hệ token và bổ sung xử lý replay trong authorization persistence/provider; kiểm thử hai request refresh đồng thời và trường hợp response bị mất.

### 10.4. Sender-constrained token

RFC 9700 khuyến nghị Authorization Server và Resource Server cân nhắc sender-constraining bằng mTLS hoặc DPoP để giảm giá trị của token bị đánh cắp. Token chỉ dùng được khi client chứng minh sở hữu khóa/certificate đã ràng buộc với token.

## 11. DPoP theo RFC 9449

DPoP là cơ chế proof-of-possession ở tầng ứng dụng. Client tạo một cặp khóa và gửi DPoP proof JWT trong HTTP header. Authorization Server ràng buộc access token với public key của proof; Resource Server yêu cầu proof tương ứng khi client dùng token.

Một DPoP proof thường chứa:

- typ=dpop+jwt.
- alg là thuật toán chữ ký bất đối xứng được cho phép.
- jwk chứa public key, không chứa private key.
- htm: HTTP method.
- htu: HTTP URI đích.
- iat: thời điểm tạo proof.
- jti: ID duy nhất chống replay.
- ath: hash access token khi proof đi kèm access token.
- nonce: nonce do server cung cấp nếu server yêu cầu.

Luồng:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Create DPoP proof with private key
    C->>AS: Token request + DPoP header
    AS->>AS: Validate typ, alg, signature, htm, htu, iat, jti and nonce
    AS-->>C: DPoP-bound access token + token_type=DPoP
    C->>C: Create a new proof with ath for this access token
    C->>RS: Authorization: DPoP token + DPoP proof
    RS->>RS: Validate proof and token key binding
    RS-->>C: Protected resource
~~~

DPoP không thay thế TLS, client authentication hoặc authorization. Nó chỉ ràng buộc token với khóa của client; attacker vẫn có thể khai thác XSS để sử dụng token gián tiếp trong browser đang giữ private key.

Khi gọi Resource Server, client gửi access token theo authentication scheme DPoP, ví dụ Authorization: DPoP <access_token>, đồng thời gửi proof trong header DPoP. Không gửi DPoP-bound token theo Bearer scheme.

Spring Authorization Server 1.5.x hỗ trợ DPoP-bound access token. Khi triển khai:

- Kiểm tra metadata công bố thuật toán DPoP được hỗ trợ.
- Chỉ cho phép thuật toán chữ ký bất đối xứng được chấp nhận.
- Kiểm tra typ, public JWK, htm, htu, iat, jti, ath và nonce.
- Giới hạn thời gian proof hợp lệ.
- Lưu jti đã dùng trong replay cache có chia sẻ giữa các node.
- Đồng bộ cách xác minh key binding giữa Authorization Server và Resource Server.
- Không chấp nhận Bearer token thay cho DPoP-bound token nếu policy yêu cầu DPoP.

Nếu replay cache chỉ nằm trong memory của một node, cùng proof có thể được gửi tới node khác trong cluster. Production cần replay store phân tán hoặc cơ chế tương đương.

## 12. Mutual TLS và certificate-bound access token

RFC 8705 định nghĩa hai khả năng liên quan:

1. Dùng client certificate để xác thực OAuth client tại Authorization Server.
2. Ràng buộc access token với certificate để Resource Server yêu cầu cùng private key khi token được sử dụng.

Hai khả năng có thể triển khai độc lập hoặc kết hợp. Với SAS 1.5.8, TokenSettings.x509CertificateBoundAccessTokens(true) bật binding access token với certificate khi client dùng tls_client_auth hoặc self_signed_tls_client_auth.

Ví dụ cấu hình TokenSettings:

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .x509CertificateBoundAccessTokens(true)
        .build();
~~~

Đoạn cấu hình trên chỉ là một phần của mTLS deployment. Hạ tầng TLS phải yêu cầu client certificate đúng endpoint; Authorization Server phải xác minh certificate theo client registration; Resource Server phải lấy certificate từ TLS layer đáng tin cậy và so sánh thumbprint với binding trong token/introspection.

Không tin X-Forwarded-Client-Cert hoặc header tương tự nếu proxy chưa được xác thực, chưa strip header do client tự gửi và chưa có contract truyền certificate rõ ràng. Rotation/revocation certificate phải được đồng bộ với client registry và Resource Server.

TokenSettings.x509CertificateBoundAccessTokens(true) chỉ có tác dụng trong luồng client authentication bằng tls_client_auth hoặc self_signed_tls_client_auth và khi hạ tầng thực sự cung cấp certificate tương ứng. Bật cờ này mà không triển khai xác minh certificate tại TLS layer và Resource Server sẽ không tạo được sender constraint hoàn chỉnh.

## 13. Pushed Authorization Requests (PAR)

PAR theo RFC 9126 cho phép client gửi authorization request trực tiếp tới PAR endpoint bằng back-channel. Authorization Server trả về một request_uri ngẫu nhiên, ngắn hạn; browser chỉ mang tham chiếu đó tới Authorization Endpoint.

Lợi ích:

- Giảm việc để scope, resource, claims và các tham số authorization nhạy cảm xuất hiện trong URL browser.
- Authorization Server xác thực client và kiểm tra request sớm.
- Request URI khó đoán, gắn với client đã gửi và có thời hạn.
- Có thể kết hợp với PKCE, signed request object và client authentication.

PAR không loại bỏ validation ở Authorization Endpoint. Authorization Server vẫn phải kiểm tra request như authorization request bình thường. request_uri cần entropy cao, gắn với client và nên dùng một lần; request hết hạn hoặc replay phải bị từ chối.

Spring Authorization Server 1.5.8 có Pushed Authorization Request Endpoint và extension points để tùy biến converter/provider/response handler. Không tự tạo request_uri dựa trên sequence number, user ID hoặc giá trị đoán được.

## 14. Token purpose, audience, scope và resource authorization

Một token hợp lệ về chữ ký vẫn có thể sai mục đích. Resource Server phải kiểm tra tối thiểu:

1. iss khớp issuer được tin cậy.
2. Chữ ký xác minh bằng key của issuer đó và thuật toán nằm trong allowlist.
3. exp, nbf, iat và clock skew hợp lý.
4. aud chứa chính Resource Server/API đang xử lý request.
5. Token type/purpose phù hợp, không nhận ID Token làm access token.
6. Scope/authority đủ cho endpoint và hành động.
7. Tenant, subject, client và resource binding phù hợp policy.

Ví dụ:

| Token | Audience | Scope | Nơi được dùng |
|---|---|---|---|
| Orders access token | https://orders.api.example | orders.read | Orders API |
| Payroll access token | https://payroll.api.example | payroll.read | Payroll API |
| OIDC ID Token | employee-portal | Không dùng như API scope | OIDC client xác minh đăng nhập |

Không phát token với audience quá rộng chỉ để giảm số lần xin token. Khi cần nhiều resource, xem xét resource indicators hoặc token exchange theo policy.

Không lấy tenant_id, role hoặc scope từ request header do client tự gửi. Các claim đó phải được tạo từ client registration, authorization context và policy đã được kiểm tra.

## 15. Cấu hình nền tảng Spring Authorization Server

### 15.1. Tách protocol filter chain

Spring Authorization Server cung cấp OAuth2AuthorizationServerConfigurer để cấu hình protocol endpoints. Ví dụ cấu hình khung:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults()))
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
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Đây là skeleton minh họa cho Authorization Server và login UI. Ứng dụng còn cần RegisteredClientRepository, OAuth2AuthorizationService, OAuth2AuthorizationConsentService, JWKSource<SecurityContext>, AuthorizationServerSettings và JwtDecoder khi bật OIDC UserInfo/client registration. Không copy cấu hình này mà bỏ qua persistence, key management hoặc session policy.

Spring Authorization Server mặc định cung cấp Authorization Endpoint, Token Endpoint, introspection, revocation, metadata và JWK Set endpoint; JWK Set endpoint chỉ được cấu hình khi có JWKSource bean. OIDC endpoints được bật khi gọi oidc(...); Client Registration endpoint bị tắt theo mặc định.

### 15.2. PKCE và client policy

Đăng ký public client:

~~~java
RegisteredClient publicClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("browser-public-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://app.example.com/oauth/callback")
        .scope(OidcScopes.OPENID)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

Với confidential client, dùng client authentication phù hợp và cân nhắc yêu cầu PKCE cho Authorization Code Grant. Không lưu client secret trong source code.

Trong ví dụ confidential client phía trên, portalSecret phải được lấy từ secret manager hoặc nguồn cấu hình được bảo vệ trước khi encode; không hard-code giá trị thật trong source. Nếu client dùng private_key_jwt hoặc mTLS, cấu hình metadata/key/certificate tương ứng thay cho client secret.

### 15.3. Token lifetime và refresh policy

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .authorizationCodeTimeToLive(Duration.ofMinutes(2))
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofHours(8))
        .reuseRefreshTokens(false)
        .build();
~~~

Các con số chỉ là ví dụ. Chọn TTL theo rủi ro, khả năng revoke, trải nghiệm người dùng và yêu cầu nghiệp vụ. Authorization code nên có lifetime ngắn; Spring Authorization Server khuyến nghị tối đa 10 phút cho authorization code.

### 15.4. Không tùy biến validator làm suy yếu mặc định

SAS cung cấp extension points cho Authorization Endpoint, Token Endpoint, PAR và các provider. Khi thêm validator tùy chỉnh:

- Giữ các validator mặc định về redirect URI, scope, PKCE, client và grant.
- Không bỏ qua client authentication.
- Không tự chấp nhận redirect URI chỉ vì domain có vẻ hợp lệ.
- Không tin audience/scope chỉ do request cung cấp.
- Không chuyển exception nội bộ hoặc secret ra OAuth error response.
- Kiểm thử cả đường thành công và mọi nhánh lỗi.

## 16. Bảo vệ login, consent, session và browser

### 16.1. Session fixation và cookie

Spring Security cung cấp session fixation protection; với Servlet 3.1+ mặc định thường dùng changeSessionId. Không tắt bảo vệ này nếu không có lý do và đánh giá rõ ràng.

Cookie session production nên có:

- Secure khi chạy qua HTTPS.
- HttpOnly để JavaScript không đọc session cookie.
- SameSite phù hợp với redirect/callback flow.
- Path/Domain tối thiểu cần thiết.
- Thời hạn và idle timeout phù hợp.

SameSite là defense-in-depth, không thay thế CSRF token. Với OIDC redirect, kiểm thử thực tế SameSite=Lax/None theo response mode và browser hỗ trợ.

### 16.2. CSRF không biến mất chỉ vì API stateless

Nếu browser tự gửi cookie hoặc Basic credentials, ứng dụng có thể vẫn bị CSRF dù backend không lưu session. Giữ CSRF protection cho login form, consent form, logout và admin UI. Nếu một endpoint chỉ dùng bearer token trong Authorization header và không dùng browser cookie, có thể đánh giá CSRF khác đi, nhưng phải xác minh cách credential được gửi.

### 16.3. CORS không phải authentication

CORS kiểm soát browser có được đọc response cross-origin hay không. Nó không xác thực client và không ngăn mọi loại request từ attacker. Không dùng allowedOrigins("*") cùng credentialed requests. Chỉ cho phép origin, method và header thật sự cần thiết; phân biệt CORS policy cho Authorization Endpoint, Token Endpoint và API.

### 16.4. Security response headers

Spring Security cung cấp một số header an toàn mặc định như Cache-Control, X-Content-Type-Options, HSTS trên HTTPS và X-Frame-Options. CSP không được bật mặc định vì policy phụ thuộc ứng dụng.

Ví dụ thêm CSP cho login/consent UI:

~~~java
http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                        "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")));
~~~

Policy trên chỉ là ví dụ. Kiểm thử trang login/consent, tài nguyên static, inline scripts và identity provider integration trước khi enforce. Không tắt toàn bộ default headers để sửa một lỗi hiển thị.

## 17. Signing keys, issuer và metadata

### 17.1. Signing key là tài sản cấp cao

Nếu signing private key bị lộ, attacker có thể tạo JWT giả mang issuer hợp lệ. Biện pháp:

- Dùng asymmetric signing key.
- Giữ private key trong KMS/HSM hoặc secret store được bảo vệ.
- Giới hạn quyền ký theo service identity.
- Không commit private key vào source control.
- Không tạo key mới ngẫu nhiên mỗi lần restart.
- Dùng kid duy nhất trong JWK Set và allowlist thuật toán.
- Audit key creation, activation, rotation và revocation.

### 17.2. Rotation có overlap

Quy trình rotation an toàn:

1. Tạo key mới và public JWK mới.
2. Công bố public key mới trong JWKS.
3. Chờ Resource Server refresh cache hoặc xác minh có thể dùng key mới.
4. Chuyển signing sang key mới.
5. Giữ public key cũ cho tới khi token cuối cùng ký bằng key cũ hết hạn, cộng clock skew và JWKS cache lifetime.
6. Gỡ public key cũ và hủy private key theo retention policy.

Nếu key bị compromise, xử lý theo incident plan: ngừng ký, chuyển key, loại key bị lộ khỏi JWKS, làm mới cache, revoke token/authorization liên quan và đánh giá thời gian token có thể bị lợi dụng. Xóa key khỏi JWKS không bảo đảm mọi Resource Server đã cache key lập tức từ chối token.

### 17.3. Issuer và metadata phải ổn định

Issuer URI là định danh của Authorization Server và phải khớp chính xác giữa metadata, ID Token và access token. Không lấy issuer từ Host header tùy ý. Nếu sau reverse proxy, chỉ tin forwarded headers từ proxy đã được cấu hình và bảo vệ.

Ví dụ cấu hình issuer cố định cho một Authorization Server:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

Nếu triển khai nhiều issuer trên cùng host, dùng mô hình multi-tenant đã được thiết kế riêng và registry issuer allowlist. Không trộn issuer tĩnh với issuer suy ra từ Host header không đáng tin.

Client và Resource Server phải dùng metadata/JWKS URI lấy từ issuer đã được cấu hình tin cậy. Không tải jku hoặc x5u tùy ý từ JWT header. Không để metadata URL do người dùng tự nhập dẫn tới SSRF.

## 18. Dynamic Client Registration và administrative plane

Spring Authorization Server tắt OIDC Dynamic Client Registration endpoint theo mặc định. Nếu bật:

- Chỉ cho phép registration theo policy và quy trình kiểm duyệt.
- Giới hạn grant, redirect URI, scope, token endpoint auth method và JWKS URI.
- Không cho public registration tạo confidential client hoặc tự cấp quyền nhạy cảm.
- Có rate limit, audit, quota và ownership validation.
- Không fetch URL metadata/JWKS tùy ý mà không có SSRF protections.
- Có khả năng suspend/revoke client và rotate credential.

Administrative API để thay đổi RegisteredClient, signing key, issuer, consent hoặc token policy phải có authentication mạnh, authorization theo role, MFA/step-up cho thao tác rủi ro và audit bất biến. Không để endpoint quản trị dùng chung authorization rule với endpoint public.

## 19. Availability, abuse và rate limiting

Authorization Server có các endpoint có thể bị lạm dụng để tiêu tốn CPU, database, KMS hoặc external identity provider:

| Endpoint/hoạt động | Lạm dụng | Biện pháp |
|---|---|---|
| Login | Password spraying, credential stuffing | Rate limit theo account/IP/device, MFA, breached-password detection |
| Authorization | Request flood, consent spam | Rate limit, client policy, request validation sớm |
| PAR | Tạo request_uri liên tục | Client authentication, TTL ngắn, quota, one-time reference |
| Token | Brute-force code/secret, invalid grant flood | Client auth, PKCE, rate limit, replay detection |
| Introspection | Token guessing, CPU/database exhaustion | Bắt buộc authenticate resource server, quota và cache theo policy |
| Revocation | Request flood | Client auth, rate limit và audit |
| Device authorization | User-code guessing và polling flood | User code entropy, throttling, interval enforcement |
| JWKS/metadata | Cache-busting hoặc request flood | CDN/cache hợp lý, rate limit và availability controls |
| KMS/HSM | Signing request flood | Quota, circuit breaker, bounded queue và capacity planning |

Không chỉ rate limit theo IP. Một proxy NAT có thể đại diện nhiều người dùng, trong khi botnet có nhiều IP. Kết hợp client ID, account, device/session, IP reputation và endpoint-specific limits.

Thiết kế timeout, bounded retries, circuit breaker và bulkhead cho database/KMS/external IdP. Không retry vô hạn token exchange hoặc login request. Đảm bảo clock đồng bộ để validation iat, exp, DPoP proof và certificate có kết quả nhất quán.

## 20. Logging, monitoring và incident response

### 20.1. Security event cần quan sát

Ghi nhận có cấu trúc:

- Login success/failure và MFA outcome.
- Client authentication failure.
- Redirect URI mismatch.
- PKCE missing/invalid/downgrade.
- Authorization code replay.
- Refresh token reuse/replay.
- Invalid issuer/audience/signature.
- DPoP proof invalid/replay/nonce failure.
- mTLS certificate mismatch/expiry.
- PAR invalid, expired hoặc replayed request URI.
- Client registration/update/suspension.
- Signing key activation/rotation/revocation.
- Consent grant/revoke.
- Administrative policy change.

Log nên có timestamp, request/correlation ID, issuer, client ID, endpoint, grant type, error category và kết quả. Không ghi raw token, code, secret, password, DPoP proof hoặc private key.

### 20.2. Alert theo hành vi

Thiết lập alert khi:

- Tỷ lệ invalid_client, invalid_grant hoặc PKCE failure tăng đột biến.
- Một client xin scope/audience bất thường.
- Refresh-token replay xuất hiện.
- Có nhiều redirect URI mismatch.
- DPoP jti replay hoặc nonce downgrade.
- KMS signing error, JWKS fetch failure hoặc issuer metadata mismatch.
- Admin thay đổi redirect URI, grant, scope hoặc signing key ngoài change window.

### 20.3. Runbook sự cố

**Lộ client secret/private key:** disable client hoặc credential, tạo credential mới, rotate theo quy trình, rà soát token/authorization đã phát hành và kiểm tra log.

**Lộ signing key:** ngừng ký bằng key bị lộ, activate key mới, cập nhật JWKS, xử lý cache Resource Server, revoke token/authorization liên quan và đánh giá phạm vi issuer.

**Refresh-token replay:** revoke token family/grant liên quan, yêu cầu người dùng xác thực lại, kiểm tra client/device và giữ bằng chứng audit.

**Issuer/metadata bị giả mạo:** chặn nguồn discovery, kiểm tra DNS/TLS/proxy, xác minh issuer/JWKS trust configuration và rotate key nếu có khả năng compromise.

**Client bị lạm dụng:** suspend client, giới hạn token issuance, thu hồi refresh token/authorization và thông báo cho owner theo incident policy.

## 21. Threat matrix và kiểm thử bảo mật

| Threat | Điều kiện khai thác | Security control | Kiểm thử |
|---|---|---|---|
| Redirect URI manipulation | AS chấp nhận wildcard/prefix | Exact matching | Redirect URI khác một ký tự phải bị từ chối |
| Open redirect | Client/AS redirect URL tùy ý | Destination allowlist | next=https://evil.test không được redirect |
| Authorization code interception | Code bị chặn | PKCE S256, TLS, code single-use | Code không đổi được nếu thiếu/sai verifier |
| Code injection | Attacker inject code của transaction khác | PKCE, state/nonce, client binding | Code khác transaction phải thất bại |
| PKCE downgrade | Token request bỏ qua challenge | Enforce verifier only if challenge existed | Gửi verifier cho code không có challenge phải bị từ chối |
| CSRF | Attacker tạo callback/form request | State/nonce/PKCE và CSRF token | State sai, nonce sai, CSRF token thiếu đều thất bại |
| Mix-up | Client hỗ trợ nhiều issuer | RFC 9207 iss hoặc distinct redirect URI | Response issuer sai phải abort |
| Client impersonation | Secret/key bị lộ hoặc auth yếu | private_key_jwt/mTLS, credential rotation | Credential sai/expired/cert mismatch bị từ chối |
| Token replay | Bearer token bị đánh cắp | Short TTL, DPoP/mTLS, audience | Token không có proof hoặc sai key bị từ chối |
| Refresh-token replay | Token cũ được dùng lại | Rotation hoặc sender constraint | Reuse token cũ revoke family theo policy |
| Audience confusion | API chỉ kiểm tra signature | Audience validator | Token đúng chữ ký nhưng aud sai bị từ chối |
| Scope escalation | Tin scope từ request | Client/resource policy | Scope ngoài allowlist không được cấp |
| ID Token as access token | API nhận mọi JWT | Token purpose/type/audience validation | ID Token gửi tới API phải bị từ chối |
| DPoP proof replay | Proof bị gửi lại | jti replay cache, iat window, nonce | Cùng proof dùng lần hai bị từ chối trên nhiều node |
| mTLS binding bypass | Proxy/header giả certificate | TLS layer binding và trusted proxy | Certificate không khớp token bị từ chối |
| PAR replay | request_uri bị đoán hoặc dùng lại | Entropy, client binding, TTL, one-time use | request_uri hết hạn/sai client/replay bị từ chối |
| SSRF via metadata/JWKS | URL không tin cậy được fetch | Allowlist, IP/network policy | URL tới loopback/private IP bị chặn |
| Key compromise | Private signing key lộ | KMS/HSM, rotation, least privilege | Rotation và cache invalidation được diễn tập |
| CSRF qua cookie | Browser tự gửi session cookie | CSRF token, SameSite defense-in-depth | POST không có CSRF token bị từ chối |
| CORS misconfiguration | Wildcard origin + credentials | Exact origin allowlist | Origin không được phép không nhận CORS headers |
| DoS | Endpoint bị flood | Rate limit, quota, bounded work | Load test không làm cạn pool/KMS/database |

### 21.1. Kiểm thử PKCE

Với client yêu cầu PKCE:

1. Gửi Authorization Request có challenge S256.
2. Đổi code bằng verifier đúng và xác nhận thành công.
3. Đổi code bằng verifier sai và xác nhận invalid_grant.
4. Bỏ verifier và xác nhận thất bại.
5. Gửi verifier cho authorization code được tạo không có challenge và xác nhận bị từ chối.
6. Thử code đã đổi lần thứ hai và xác nhận replay bị từ chối.

### 21.2. Kiểm thử redirect và issuer

- Redirect URI exact match thành công.
- Thay scheme, host, path, port hoặc query theo cách không được đăng ký phải thất bại.
- Response từ issuer khác phải bị client abort.
- Không được forward code tới URL lấy từ query parameter.
- Host header giả mạo không làm thay đổi issuer nội bộ.

### 21.3. Kiểm thử token và Resource Server

- Token hết hạn, sai chữ ký, sai issuer, sai audience hoặc sai token purpose đều bị từ chối.
- Token scope thiếu không được gọi API nhạy cảm.
- ID Token không được chấp nhận như access token.
- DPoP-bound token phải đi kèm proof đúng key, URI, method, time, jti và ath.
- mTLS-bound token phải được trình qua đúng client certificate.

### 21.4. Kiểm thử vận hành

- Refresh-token reuse phát hiện replay và revoke đúng family.
- Key rotation có overlap và Resource Server nhận key mới.
- Revocation/introspection hoạt động qua nhiều node.
- Rate limit và circuit breaker không tạo retry storm.
- Audit log không chứa credential hoặc token.
- Backup/restore authorization store và key metadata giữ đúng integrity.

## 22. Bài tập thực hành

**Bối cảnh:** triển khai Authorization Server cho employee-portal, mobile-app, orders-api và payroll-api. Browser/mobile dùng Authorization Code; workload dùng Client Credentials. Hệ thống có hai issuer ngoài cho federation và một internal issuer.

### Yêu cầu

1. Liệt kê tài sản và trust boundary của hệ thống.
2. Xác định threat actor có thể truy cập browser, client secret, reverse proxy và KMS.
3. Đăng ký public client với Authorization Code + PKCE S256.
4. Đăng ký confidential client dùng client authentication phù hợp.
5. Thiết lập redirect URI exact matching và test open redirect.
6. Kiểm tra state, nonce và issuer mix-up cho client hỗ trợ nhiều IdP.
7. Cấu hình PAR cho client phù hợp và kiểm thử request_uri binding/replay.
8. Bật DPoP hoặc mTLS cho một API có rủi ro token replay cao.
9. Cấu hình access token TTL, refresh-token rotation và replay detection.
10. Cấu hình Resource Server kiểm tra issuer, audience, token type và scope.
11. Bảo vệ login/consent/admin UI bằng session, CSRF và security headers.
12. Thiết lập rate limit cho login, token, introspection, PAR và device authorization.
13. Viết audit event và alert cho client auth failure, replay và key rotation.
14. Tạo threat matrix và integration tests cho các kịch bản tấn công.
15. Viết runbook cho lộ client secret, refresh-token replay và signing-key compromise.

**Tiêu chí hoàn thành:** mọi client có policy rõ ràng; Authorization Code được bảo vệ bằng PKCE; redirect URI exact; Resource Server từ chối token sai issuer/audience/purpose; refresh-token replay được phát hiện; secret/key không xuất hiện trong log; các endpoint nhạy cảm có rate limit và audit.

## 23. Checklist trước production

- [ ] Có threat model ghi rõ tài sản, actor, trust boundary và attack surface.
- [ ] Chỉ bật grant type cần thiết; không dùng Implicit hoặc Resource Owner Password Credentials.
- [ ] Authorization Code được bảo vệ bằng PKCE S256; confidential clients cũng được cân nhắc yêu cầu PKCE.
- [ ] Redirect URI exact match; không có wildcard hoặc open redirector.
- [ ] State/nonce transaction-specific và được ràng buộc với browser session.
- [ ] Client nhiều issuer có mix-up defense theo RFC 9207 hoặc distinct redirect URI.
- [ ] Public client không chứa client secret.
- [ ] Confidential client dùng authentication method và credential lifecycle phù hợp.
- [ ] Client chỉ được cấp grant, scope, resource và audience cần thiết.
- [ ] Authorization code ngắn hạn và single-use.
- [ ] Access token TTL phù hợp; không truyền token trong URL.
- [ ] Refresh token chỉ cấp khi cần; có rotation hoặc sender constraint cho public client.
- [ ] DPoP/mTLS được cân nhắc cho API có rủi ro token replay cao.
- [ ] PAR được bật cho client phù hợp; request_uri có entropy, binding, TTL và replay policy.
- [ ] Resource Server kiểm tra issuer, signature, audience, thời hạn, token purpose và scope.
- [ ] Signing key nằm trong KMS/HSM hoặc secret store được bảo vệ; có rotation runbook.
- [ ] Issuer/metadata/JWKS URI ổn định; forwarded headers chỉ tin từ proxy được quản trị.
- [ ] CSRF vẫn bảo vệ login, consent, logout và admin UI.
- [ ] CORS dùng allowlist origin; không coi CORS là authentication.
- [ ] Session fixation protection, Secure/HttpOnly/SameSite cookie và timeout được cấu hình.
- [ ] Security headers được giữ; CSP được thiết kế và kiểm thử riêng.
- [ ] DCR/admin endpoints bị giới hạn và audit.
- [ ] Login/token/PAR/introspection/device/JWKS có rate limit và capacity plan.
- [ ] Log/trace không chứa token, code, password, secret hoặc private key.
- [ ] Có alert cho replay, issuer/audience mismatch, client auth failure và key event.
- [ ] Có test matrix và runbook incident response đã diễn tập.

## 24. Tổng kết

OAuth 2.0 Security Best Current Practice yêu cầu thiết kế bảo mật dựa trên toàn bộ luồng, không dựa riêng vào chữ ký JWT hay một cấu hình framework.

Các nguyên tắc cốt lõi:

1. Dùng Authorization Code Grant và PKCE S256; loại bỏ flow kém an toàn.
2. So sánh redirect URI chính xác và loại bỏ open redirector.
3. Ràng buộc authorization response với client, browser transaction và issuer.
4. Xác thực confidential client bằng credential được bảo vệ; public client không có secret.
5. Giảm nguy cơ token replay bằng TTL, refresh rotation, DPoP hoặc mTLS.
6. Giới hạn scope, audience, resource và token purpose.
7. Bảo vệ login/session/consent bằng CSRF, cookie policy và security headers.
8. Bảo vệ signing key, metadata, client registry và administrative plane.
9. Chống abuse bằng rate limit, quota, bounded work và monitoring.
10. Kiểm thử các kịch bản tấn công và diễn tập incident response.

Spring Authorization Server 1.5.8 cung cấp các extension point và protocol support cần thiết cho nhiều biện pháp như PKCE, PAR, DPoP, mTLS, token settings và endpoint customization. Tuy nhiên, ứng dụng vẫn phải định nghĩa client policy, key lifecycle, Resource Server validation, CSRF/session, rate limit, logging và vận hành phù hợp với threat model của mình.

### Tài liệu tham khảo

1. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): threat model và các yêu cầu BCP về redirect, PKCE, mix-up, token replay, refresh token, client authentication.
2. [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): code verifier, challenge và S256.
3. [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207.html): iss trong authorization response để chống mix-up.
4. [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html): PAR endpoint, request_uri, client binding và replay.
5. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): proof JWT, ath, nonce và replay protection.
6. [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): mTLS client auth và certificate-bound tokens.
7. [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): issuer, endpoint và capability metadata.
8. [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): default endpoints, JWKSource và OIDC configuration.
9. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Authorization Endpoint, Token Endpoint, PAR và DPoP.
10. [Spring Authorization Server 1.5.8 — How-to: Authenticate using a Single Page Application with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): public client, PKCE và BFF guidance.
11. [Spring Authorization Server 1.5.8 — ClientSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.Builder.html): requireProofKey và consent settings.
12. [Spring Authorization Server 1.5.8 — TokenSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html): access/refresh/code TTL, refresh token reuse và mTLS binding.
13. [Spring Security 6.5 — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF token và SPA integration.
14. [Spring Security 6.5 — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html): default headers, HSTS và CSP.
15. [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation, session persistence và concurrent session controls.
