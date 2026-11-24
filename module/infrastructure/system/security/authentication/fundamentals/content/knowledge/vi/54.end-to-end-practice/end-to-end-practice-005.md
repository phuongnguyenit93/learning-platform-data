# Thiết kế token — Bài thực hành xây dựng kiến trúc token an toàn đầu-cuối

Một nền tảng học tập có ứng dụng web, ứng dụng mobile, API cho đối tác và nhiều workload nội bộ. Nhóm phát triển muốn dùng một JWT duy nhất cho mọi mục đích: đăng nhập web, gọi API, đọc hồ sơ, xuất chứng chỉ và gọi service-to-service. Token có lifetime 30 ngày, chứa email, role, tenant, danh sách khóa học và một số thông tin hồ sơ. Các API chỉ kiểm tra chữ ký, không kiểm tra audience; logout chỉ xóa token khỏi browser; refresh token được lưu cùng access token trong local storage. Một service staging dùng chung signing key với production.

Thiết kế này tạo ra nhiều đường tấn công: token bị lấy cắp có thể được dùng ở nhiều resource; API có thể chấp nhận token không dành cho mình; dữ liệu trong JWT bị lộ qua log hoặc browser storage; logout không thu hồi token đã phát hành; và compromise ở staging có thể ảnh hưởng production.

Bài thực hành này hướng dẫn thiết kế lại hệ thống token theo mục đích, principal, resource và trust boundary. Token là một bằng chứng có giới hạn về một lần xác thực hoặc một quyền được cấp. Nó không thay thế authorization ở resource server, không tự chứng minh người đang cầm token là chủ account, và không mặc nhiên có thể thu hồi tức thời.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học kết nối credential, password, MFA, passkey, certificate, OAuth/OIDC, session, federation và workload identity để thiết kế token lifecycle an toàn. Kết quả mong đợi là một kiến trúc có thể giải thích được: token nào được phát hành cho ai, bởi issuer nào, dành cho audience nào, mang quyền gì, sống bao lâu, được lưu ở đâu, được kiểm tra ra sao, và bị thu hồi thế nào khi credential hoặc session bị compromise.

## 1. Mục tiêu và yêu cầu của bài thực hành

Sau khi hoàn thành, người học có thể:

- Phân biệt ID token, access token, refresh token, session cookie và token nội bộ.
- Chọn JWT hay opaque token theo nhu cầu validation, privacy và revocation.
- Thiết kế issuer, subject, audience, scope, expiry và token type.
- Chọn OAuth/OIDC flow theo loại client.
- Xây dựng quy trình phát hành, validate, refresh, rotate và revoke.
- Bảo vệ signing key, JWKS, client credential và token storage.
- Giảm nguy cơ theft, replay, token substitution, confused deputy và privilege escalation.
- Xử lý token cho web, mobile, API đối tác và workload.
- Kiểm thử negative cases và xác minh revocation propagation.
- Triển khai có versioning, monitoring, rollback và incident response.

### 1.1. Bối cảnh giả định

Nền tảng có các thành phần:

| Thành phần | Mục đích | Trust boundary |
| --- | --- | --- |
| Browser web app | Người học và giảng viên sử dụng | Trình duyệt và thiết bị người dùng |
| Mobile app | Đăng nhập và học trên điện thoại | OS, app process và secure storage |
| Identity provider (IdP) | Xác thực password, MFA, passkey | Identity control plane |
| Authorization server | Phát hành access/refresh token | Token issuance boundary |
| API gateway | Kiểm tra token ở edge, rate limit | Gateway-to-service |
| Learning API | Hồ sơ, khóa học, tiến độ | Resource authorization |
| Certificate API | Xuất và xác minh chứng chỉ học tập | Resource có độ nhạy cao |
| Partner integration | Truy cập API theo hợp đồng | External client boundary |
| Workload services | Gọi service-to-service | Workload identity boundary |
| KMS/HSM | Bảo vệ signing key | Cryptographic trust boundary |
| Audit/SIEM | Ghi nhận token lifecycle và truy cập | Evidence boundary |

### 1.2. Yêu cầu chức năng

1. User đăng nhập bằng password + MFA hoặc passkey.
2. Web app truy cập Learning API và Certificate API.
3. Mobile app đăng nhập bằng browser/system authentication session.
4. Partner client gọi API đã được cấp scope.
5. Workload nội bộ gọi nhau bằng machine identity.
6. User có thể logout, đổi password, reset MFA hoặc báo mất thiết bị.
7. Admin có thể revoke session/grant khi phát hiện compromise.
8. API phải phân biệt quyền đọc hồ sơ, cập nhật tiến độ và phát hành chứng chỉ.

### 1.3. Yêu cầu phi chức năng

- Token không được dùng chéo audience hoặc environment.
- Credential và token không xuất hiện trong log, analytics hoặc URL.
- Access token có lifetime phù hợp với khả năng revocation.
- Refresh token được bảo vệ và có rotation/reuse detection khi phù hợp.
- Resource server kiểm tra cả authentication context và authorization.
- Signing key có rotation, backup và audit.
- Revocation có SLA được đo ở mọi downstream.
- Thiết kế hỗ trợ nhiều client mà không dùng một secret hoặc token chung.

## 2. Threat model và trust boundary

Trước khi chọn format token, xác định attacker có thể kiểm soát thành phần nào.

### 2.1. Tài sản

- Account, subject identifier và tenant membership.
- Password verifier, MFA factor, passkey credential và recovery channel.
- Access token, refresh token, authorization code và session cookie.
- Signing key, client credential, certificate và workload identity.
- API resource, hồ sơ, tiến độ, bài thi và chứng chỉ.
- Consent, scope, role và policy.
- Audit event và key lifecycle metadata.

### 2.2. Attacker capability

- Phishing password hoặc dụ user approve MFA.
- Đánh cắp session cookie/token qua malware, XSS hoặc thiết bị bị compromise.
- Replay refresh token hoặc authorization code.
- Lạm dụng redirect URI, audience hoặc issuer validation yếu.
- Dùng client credential bị lộ để xin token.
- Tạo token từ signing key bị compromise.
- Tấn công staging/dev để tìm đường vào production.
- Khai thác cache, clock skew, key rotation hoặc revocation delay.
- Lạm dụng token có scope rộng để truy cập resource khác.

### 2.3. Sơ đồ trust boundary

~~~mermaid
flowchart LR
    U[User] --> B[Browser / Mobile]
    B -->|Authorization request| I[IdP / Authorization Server]
    I -->|ID token to client| B
    I -->|Access token for API| B
    B -->|Bearer or bound token| G[API Gateway]
    G --> L[Learning API]
    G --> C[Certificate API]
    W[Workload identity] -->|Workload token| G
    K[KMS / HSM] --> I
    I --> A[Audit / SIEM]
    G --> A
    L --> A
    C --> A
~~~

Các đường nối biểu diễn luồng logic. Mỗi mũi tên là một ranh giới cần xác thực peer, validate input, bảo vệ transport và ghi audit phù hợp. Gateway có thể thực hiện kiểm tra token sơ bộ, nhưng resource server vẫn cần enforce authorization cho resource và tenant của mình.

### 2.4. Trust assumptions

- Browser/mobile không được xem là nơi giữ secret lâu dài.
- Client không được tự khai subject, role, tenant hoặc assurance.
- Issuer là authority phát hành token; API chỉ tin issuer đã cấu hình.
- Audience giới hạn resource nhận token.
- KMS/HSM bảo vệ private signing key; ứng dụng chỉ có quyền ký cần thiết.
- Resource server không tin token chỉ vì nó parse được.
- Audit log là bằng chứng cần bảo vệ, không phải nguồn xác thực thay token.

## 3. Phân biệt các loại token

Không dùng từ “token” như thể mọi token có cùng mục đích.

| Loại | Người nhận chính | Mục đích | Có gửi tới API nghiệp vụ? |
| --- | --- | --- | --- |
| ID token | OIDC client | Thông tin xác thực về user và authentication event | Không dùng thay access token |
| Access token | Resource server/API | Cấp quyền truy cập có giới hạn | Có, tới đúng audience |
| Refresh token | Authorization server | Xin access token mới | Không |
| Authorization code | Client qua token endpoint | Đổi code lấy token trong authorization flow | Không |
| Session cookie | Application/session service | Tham chiếu session phía server | Chỉ gửi tới host/path phù hợp |
| CSRF token | Web application | Ràng buộc state-changing request | Không phải bearer authorization token |
| Workload token | Service/resource cụ thể | Xác thực workload và quyền service-to-service | Chỉ tới audience đã định |
| DPoP proof | Authorization/resource server | Chứng minh request được ký bởi key gắn với token | Đi cùng access token theo profile |

### 3.1. ID token

ID token thuộc OpenID Connect và cho client biết authentication event đã xảy ra. Client kiểm tra issuer, audience là client ID, signature, expiry, nonce khi có và các claim theo profile. ID token không phải giấy phép chung để gọi mọi API.

Nếu Learning API nhận ID token thay access token, API có thể nhầm audience và semantics của token. Một token dành cho client web không tự động cấp quyền truy cập dữ liệu ở resource server.

### 3.2. Access token

Access token biểu diễn quyền được cấp cho một client/principal trên một resource. Nó có thể là JWT hoặc opaque string. Resource server kiểm tra token theo profile và sau đó áp dụng authorization cho từng action/resource.

Access token không nên chứa toàn bộ hồ sơ user hoặc dữ liệu nghiệp vụ. Claims cần tối thiểu để resource server xác định issuer, subject, audience, client, scope và thời hạn.

### 3.3. Refresh token

Refresh token là credential có giá trị cao vì có thể tạo access token mới. Chỉ authorization server nhận refresh token. Client lưu nó trong nơi phù hợp với platform, gửi qua TLS và xử lý rotation/revocation theo policy.

Refresh token không được gửi tới Learning API hoặc Certificate API. API nghiệp vụ không nên tự refresh token thay client.

### 3.4. Session cookie

Session cookie thường chứa session identifier không đoán được, tham chiếu state ở server. Nó không phải JWT mặc định và không nên dùng chung semantics với access token. Cookie có scope theo domain/path, flags Secure/HttpOnly/SameSite và CSRF protection phù hợp.

## 4. JWT hay opaque token?

Chọn format theo cách resource server cần xác minh và khả năng revocation.

| Tiêu chí | JWT access token | Opaque access token |
| --- | --- | --- |
| Validation | Local signature/claim validation | Introspection hoặc lookup |
| Latency | Có thể thấp, không cần round trip tới issuer | Phụ thuộc introspection/cache |
| Revocation | Khó tức thời nếu validate offline | Có thể kiểm tra trạng thái tập trung |
| Data exposure | Claims có thể đọc được bởi người giữ token | Không lộ claim nếu chỉ là random reference |
| Key distribution | Cần quản lý public key/JWKS | Resource server cần kết nối introspection |
| Operational coupling | Ít phụ thuộc online issuer khi validate | Phụ thuộc availability của introspection |
| Token size | Có thể lớn do claims/signature | Thường ngắn |
| Use case | Nhiều resource server cần validate phân tán | Quyền cần kiểm soát tập trung hoặc privacy cao |

### 4.1. Khi dùng JWT

JWT phù hợp khi:

- Resource server có thể validate local theo profile chuẩn.
- Issuer, audience và claims được kiểm soát chặt.
- Token lifetime ngắn phù hợp với revocation model.
- Key rotation/JWKS distribution đáng tin cậy.
- Không cần ẩn nội dung claims khỏi người giữ token.

JWT/JWS được ký để bảo vệ integrity và authenticity. Payload JWT thông thường chỉ được Base64URL encode, không được mã hóa. Người có token có thể decode và đọc claims. Không đưa password, OTP, recovery code, private data hoặc secret vào payload.

### 4.2. Khi dùng opaque token

Opaque token phù hợp khi:

- Cần revoke/disable tập trung.
- Claims nhạy cảm không nên nằm trong token.
- Issuer muốn giữ policy và state ở authorization server.
- Resource server có thể gọi introspection hoặc dùng cache có TTL phù hợp.

Opaque token vẫn là bearer credential nếu ai có token có thể dùng nó. Không vì chuỗi token không đọc được mà bỏ qua bảo vệ storage, TLS, logging và replay.

### 4.3. Không tự thiết kế token format

Ưu tiên chuẩn OAuth 2.0/OIDC và profile token đã được chuẩn hóa. Không tạo một chuỗi tự ký, tự mã hóa hoặc tự parse rồi coi đó là giao thức authentication. Nếu cần JWT access token, tuân theo profile phù hợp, ví dụ JWT Profile for OAuth 2.0 Access Tokens (RFC 9068) khi hệ thống áp dụng.

## 5. Thiết kế claims và semantics

Claims là dữ liệu có ý nghĩa trong token. Mỗi claim phải có nguồn tin cậy, semantics rõ và consumer được xác định.

### 5.1. Claims cốt lõi cho access token

| Claim | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| iss | Issuer | Exact match với issuer được cấu hình |
| sub | Subject | Stable identifier trong phạm vi issuer |
| aud | Audience | Resource server nhận token |
| exp | Expiration time | Sau thời điểm này token không được chấp nhận |
| nbf | Not before | Không chấp nhận trước thời điểm nếu có |
| iat | Issued at | Dùng để kiểm tra freshness/policy |
| jti | Token identifier | Có thể dùng correlation/replay controls theo profile |
| client_id | Client được cấp token | Phân biệt client application |
| scope | Quyền được cấp | Giới hạn action, không thay object authorization |
| cnf | Confirmation/key binding | Gắn token với key khi dùng sender-constrained token |
| tenant_id | Tenant context | Chỉ thêm nếu issuer quản lý và API cần |

Không phải mọi hệ thống cần mọi claim. Tránh nhồi nhiều trường chỉ vì thuận tiện. Token càng lớn càng tăng chi phí truyền, log leakage và nguy cơ stale authorization.

### 5.2. Subject và identity mapping

Subject cần ổn định trong phạm vi issuer. Email không phải subject tốt nếu email có thể đổi, tái sử dụng hoặc khác nhau giữa tenant. Với federation, dùng issuer + subject làm định danh; có thể dùng pairwise subject để giảm khả năng liên kết user giữa client.

Resource server không tự suy ra tenant từ email domain. Tenant membership phải được xác minh và gắn vào authorization context theo policy.

### 5.3. Audience

Audience giới hạn nơi token được dùng:

- Learning API nhận token dành cho Learning API.
- Certificate API nhận token dành cho Certificate API.
- Partner API nhận token dành cho resource contract của partner.
- Workload token chỉ dành cho service audience cụ thể.

Không dùng audience chung kiểu all-services nếu các API có trust boundary hoặc dữ liệu khác nhau. Nếu gateway chuyển tiếp token, xác định rõ token exchange hoặc delegation semantics.

### 5.4. Scope, role và object authorization

Scope biểu diễn quyền được cấp ở mức API/action, ví dụ:

- profile:read
- progress:write
- certificate:issue
- certificate:read

Role mô tả nhóm quyền của principal trong một context; scope mô tả quyền mà client được cấp. API vẫn phải kiểm tra resource ownership, tenant, object state và business rule. Claim certificate:issue không cho phép user phát hành chứng chỉ cho bất kỳ người học nào nếu họ không có quyền trên object đó.

### 5.5. Authentication context

Với OIDC, ID token có thể chứa claim như auth_time, acr và amr theo profile. Chúng giúp client hiểu thời điểm và phương thức authentication. Resource server chỉ nên dựa vào authentication context nếu issuer, semantics và policy được thống nhất; không tin claim tự gửi từ client.

## 6. Mô hình token đề xuất cho nền tảng

Tách token theo client và resource:

| Client/principal | Token | Audience | Scope ví dụ |
| --- | --- | --- | --- |
| Web user | Access token hoặc BFF session | Learning API | profile:read, progress:write |
| Web user | Access token riêng | Certificate API | certificate:read |
| Mobile user | Access token | Learning API | profile:read, progress:write |
| Partner client | Access token | Partner API | partner:course:read |
| Reporting workload | Workload access token | Reporting API | report:read |
| Certificate worker | Workload access token | Certificate API | certificate:issue |

ID token chỉ được gửi tới OIDC client. Refresh token chỉ được gửi tới authorization server. Session cookie chỉ được gửi tới web application host theo cookie scope.

### 6.1. Không dùng một token cho nhiều resource

Một access token với audience Learning API không được chấp nhận ở Certificate API. Nếu một operation cần gọi hai resource, client có thể xin token riêng cho mỗi audience hoặc dùng token exchange theo policy. Điều này giới hạn blast radius khi token bị lộ.

### 6.2. Token cho partner

Partner client có identity riêng, scope cụ thể và owner. Không phát token người dùng nếu integration chỉ cần machine-to-machine. Không chia sẻ một API key/token giữa nhiều đối tác. Có expiry, rotation, quota, revoke và audit theo client.

### 6.3. Token cho workload

Workload dùng platform identity/federation hoặc certificate thay cho static secret dài hạn khi có thể. Token có subject, audience và scope theo workload. Staging và production có issuer/subject/trust policy riêng.

## 7. Chọn OAuth/OIDC flow theo client

### 7.1. Web application có backend (BFF)

Một Backend-for-Frontend có thể giữ access/refresh token ở server-side. Browser nhận session cookie HttpOnly, Secure, SameSite theo flow. Backend gọi API với access token phù hợp. Cần CSRF protection cho request dùng cookie và kiểm soát session lifecycle.

Ưu điểm là token OAuth không cần xuất hiện trong JavaScript/browser storage. BFF không loại bỏ XSS/CSRF risk; XSS vẫn có thể thực hiện hành động trong session và CSRF cần được bảo vệ.

### 7.2. Single-page application

SPA là public client. Dùng Authorization Code + PKCE, không nhúng client secret. Hạn chế token lifetime và scope; tránh lưu refresh/access token lâu dài trong localStorage vì script cùng origin có thể đọc khi XSS xảy ra. Nếu dùng refresh token cho SPA, phải tuân thủ rotation, reuse detection và yêu cầu của authorization server; cân nhắc BFF khi phù hợp.

### 7.3. Native mobile application

- Dùng system browser/external user-agent cho authorization.
- Authorization Code + PKCE S256.
- Không nhúng client secret trong app binary.
- Dùng claimed HTTPS App Links/Universal Links hoặc redirect URI profile an toàn.
- Lưu credential trong OS secure storage như Keychain/Keystore.
- Xử lý device lock, backup/restore và app uninstall theo policy.
- Có logout/revoke flow và kiểm tra token bị thu hồi.

### 7.4. Machine-to-machine

Client credentials grant hoặc cơ chế tương đương chỉ dành cho confidential client. Ưu tiên workload identity federation, mTLS hoặc private_key_jwt thay shared static secret khi nền tảng hỗ trợ. Scope và audience phải hẹp, token ngắn hạn, key/credential có rotation và audit.

### 7.5. Authorization Code flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Client
    participant AS as Authorization Server
    participant API as Resource API
    U->>C: Chọn đăng nhập
    C->>AS: Authorization request + state + PKCE challenge + nonce
    AS->>U: Authentication / MFA / passkey
    U->>AS: Xác minh
    AS->>C: Authorization code + state
    C->>AS: Code + PKCE verifier
    AS->>C: ID token + access token + optional refresh token
    C->>C: Validate ID token và session
    C->>API: Access token đúng audience
    API->>API: Validate token và authorize resource
~~~

Code phải ngắn hạn, one-time và ràng buộc với client/redirect URI/PKCE transaction. Client kiểm tra state và OIDC nonce; authorization server kiểm tra PKCE verifier.

## 8. Ví dụ access token và ID token

Ví dụ payload access token minh họa theo profile JWT access token. Đây là JSON giả định để đọc cấu trúc, không phải token có thể sử dụng:

~~~json
{
  "iss": "https://id.example.test",
  "sub": "user-7f31",
  "aud": "https://api.example.test/learning",
  "client_id": "web-bff-prod",
  "scope": "profile:read progress:write",
  "iat": 1795300000,
  "exp": 1795300600,
  "jti": "at-9b6e2d",
  "tenant_id": "tenant-42"
}
~~~

Trong ví dụ, access token có audience Learning API và scope giới hạn. Thời gian là giá trị giả định. Không đưa email, phone, full profile, điểm thi hoặc thông tin cá nhân không cần thiết vào token.

### 8.1. Header JWT

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-11",
  "typ": "at+jwt"
}
~~~

Resource server chỉ chấp nhận algorithm nằm trong allowlist cấu hình. kid chỉ dùng chọn key từ JWKS đã tin cậy. Không lấy jku hoặc x5u tùy ý từ header token để tải key. Không cho phép algorithm downgrade hoặc unsigned token.

### 8.2. ID token khác access token

ID token có audience là client ID và có thể chứa:

~~~json
{
  "iss": "https://id.example.test",
  "sub": "user-7f31",
  "aud": "web-bff-prod",
  "iat": 1795300000,
  "exp": 1795300600,
  "nonce": "oidc-transaction-nonce",
  "auth_time": 1795299900,
  "acr": "urn:example:loa:2",
  "amr": ["passkey"]
}
~~~

Client xác minh ID token theo OIDC và kiểm tra nonce được tạo cho đúng transaction. Không gửi ID token này tới Learning API để thay access token.

## 9. JWT validation tại resource server

Resource server phải xác minh token trước khi sử dụng claims:

1. Token được nhận qua TLS từ đúng header/cơ chế.
2. Parse an toàn và giới hạn kích thước.
3. Kiểm tra token type/profile.
4. Chỉ chấp nhận algorithm đã allowlist.
5. Lấy key từ JWKS/keystore được cấu hình cho issuer.
6. Xác minh chữ ký.
7. Exact-match issuer.
8. Kiểm tra audience chứa đúng resource server.
9. Kiểm tra exp, nbf, iat và clock skew có giới hạn.
10. Kiểm tra client, scope và claims theo policy.
11. Kiểm tra revocation/denylist/introspection nếu kiến trúc yêu cầu.
12. Áp dụng authorization theo resource, tenant và action.

### 9.1. Ví dụ validation pseudocode

~~~java
public AuthenticatedPrincipal validateAccessToken(String compactToken) {
    ParsedJwt jwt = jwtParser.parse(compactToken);

    requireAllowedType(jwt.header().type(), "at+jwt");
    requireAllowedAlgorithm(jwt.header().algorithm());

    PublicKey key = trustedJwks.keyFor(
        configuredIssuer,
        jwt.header().keyId()
    );
    requireValidSignature(jwt, key);

    requireExactIssuer(jwt.claim("iss"), configuredIssuer);
    requireAudience(jwt.claim("aud"), learningApiAudience);
    requireNotExpired(jwt.claim("exp"), clock.instant(), allowedSkew);
    requireNotBefore(jwt.claim("nbf"), clock.instant(), allowedSkew);
    requireIssuedAtWithinPolicy(jwt.claim("iat"), clock.instant());

    Set<String> scopes = parseScopes(jwt.claim("scope"));
    requireNoForbiddenScopes(scopes);

    revocationService.checkIfRequired(
        jwt.claim("jti"),
        jwt.claim("sub"),
        jwt.claim("iat")
    );

    return new AuthenticatedPrincipal(
        jwt.claim("iss"),
        jwt.claim("sub"),
        jwt.claim("client_id"),
        scopes,
        jwt.claim("tenant_id")
    );
}
~~~

Đây là pseudocode, không phải thư viện JWT hoàn chỉnh. Production nên dùng thư viện được duy trì và profile đã chuẩn hóa; không tự viết cryptographic verification. Kiểm tra audience/issuer phải đúng semantics của thư viện. Xử lý duplicate JSON members, malformed token, oversized header/claim và key lookup failure theo hướng fail closed.

### 9.2. Clock skew

Máy phát hành và resource server có thể lệch thời gian. Cho phép skew nhỏ theo policy và đồng bộ clock. Không đặt skew lớn để sửa hạ tầng sai giờ vì nó kéo dài thời gian chấp nhận token hết hạn hoặc chưa có hiệu lực.

### 9.3. Claims không thay authorization

Sau khi token hợp lệ:

- Kiểm tra scope/action.
- Xác định tenant từ identity context đã xác minh.
- Kiểm tra user có quyền trên object cụ thể.
- Kiểm tra trạng thái nghiệp vụ, ví dụ khóa học còn mở hoặc chứng chỉ chưa bị revoke.
- Ghi audit event cho action nhạy cảm.

Token hợp lệ không đồng nghĩa request được phép.

## 10. Opaque token và introspection

Với opaque token, resource server gọi introspection endpoint qua kết nối server-to-server được xác thực. Response có thể chứa active, scope, client, subject, audience và expiry theo profile.

### 10.1. Introspection controls

- Chỉ resource server được phép introspect.
- Bảo vệ endpoint bằng mTLS hoặc client authentication phù hợp.
- Không để browser gọi introspection trực tiếp.
- Cache response có TTL phù hợp với revocation SLA.
- Không cache active quá lâu nếu cần revoke nhanh.
- Xử lý issuer/introspection outage theo fail policy rõ.
- Không log raw token trong request hoặc response.

### 10.2. Cache trade-off

Cache giảm latency và load nhưng làm chậm revocation. Nếu token bị revoke tại authorization server, API có thể tiếp tục chấp nhận tới khi cache hết hạn. Chọn TTL theo sensitivity và đo propagation thực tế.

### 10.3. Fail open hay fail closed

Nếu introspection không khả dụng, quyết định fail open có thể giữ availability nhưng cho phép token đã revoke tiếp tục được dùng. Fail closed bảo vệ tốt hơn nhưng có thể làm API ngừng hoạt động. Đặt policy theo resource tier, có circuit breaker, alert và degraded mode được phê duyệt; không để mỗi service tự chọn tùy ý.

## 11. Access token lifetime và refresh token design

### 11.1. Access token lifetime

Lifetime phụ thuộc:

- Độ nhạy của resource.
- Khả năng revoke hoặc introspect.
- Client có lưu token lâu không.
- Sender-constraining có được áp dụng không.
- Rủi ro thiết bị bị compromise.
- Khả năng chịu outage của authorization server.

Token ngắn hạn giảm cửa sổ lạm dụng sau theft nhưng tăng số lần refresh và phụ thuộc issuer. Không dùng một lifetime cho mọi client/resource mà không có risk analysis.

### 11.2. Refresh token rotation

Với rotation:

1. Client gửi refresh token hiện tại tới token endpoint.
2. Authorization server xác minh grant, client, session và policy.
3. Server phát access token mới và refresh token mới.
4. Refresh token cũ bị đánh dấu consumed.
5. Nếu token cũ được dùng lại sau khi rotation đã commit, server đánh giá reuse và có thể revoke token family.

### 11.3. Reuse detection và race condition

Client có thể gửi hai refresh request gần đồng thời do retry, app resume hoặc network timeout. Server cần semantics rõ:

- Dùng transaction/atomic state để chỉ một lần consume thành công.
- Phân biệt retry hợp lệ trong grace window nếu profile/policy cho phép.
- Không chấp nhận vô hạn việc dùng lại token cũ.
- Ghi audit theo token family reference.
- Khi reuse được xác nhận, revoke family và yêu cầu reauthentication.

### 11.4. Refresh token binding

Refresh token có thể được ràng buộc với client hoặc sender key. Confidential client cần xác thực client tại token endpoint; public client cần cơ chế bảo vệ phù hợp như rotation và sender-constraining khi hỗ trợ. Không giả định client ID đơn thuần là bằng chứng possession.

## 12. Token theft, replay và sender-constrained token

Bearer token có nghĩa là ai sở hữu token có thể dùng nó trong phạm vi policy. Vì vậy token theft là rủi ro trọng yếu.

### 12.1. Nguồn token theft

- XSS hoặc malicious browser extension.
- Malware/credential stealer.
- Log, crash dump, tracing hoặc analytics vô tình ghi token.
- URL/query string, referrer hoặc browser history.
- Shared device, backup hoặc insecure local storage.
- Mobile backup không an toàn.
- CI artifact, source repository hoặc environment dump.
- Proxy/debug tool và support ticket.

### 12.2. Replay

Replay là sử dụng lại một credential/proof hợp lệ trong một ngữ cảnh hoặc thời điểm khác với dự kiến. Các biện pháp:

- Authorization code one-time và PKCE.
- State/nonce gắn transaction.
- Refresh token rotation/reuse detection.
- Short-lived access token.
- Idempotency key cho action có side effect.
- Request timestamp/nonce và replay cache cho signed request.
- DPoP hoặc mTLS sender-constrained token khi phù hợp.

Không thể chống replay chỉ bằng cách thêm jti vào JWT nếu resource server không kiểm tra hoặc lưu trạng thái cần thiết.

### 12.3. DPoP

Demonstrating Proof of Possession (DPoP) ràng buộc token với public key của client. Client ký proof cho request; server kiểm tra proof và token binding theo profile. Các thành phần thường được kiểm tra gồm HTTP method, target URI, thời gian, unique proof ID, access-token hash khi dùng với resource request và key thumbprint liên kết token.

DPoP giảm khả năng dùng token bị đánh cắp đơn lẻ từ thiết bị khác, nhưng không bảo vệ khỏi malware có thể sử dụng key hoặc thực hiện request trên thiết bị đã compromise. Cần quản lý key, nonce/replay cache và tương thích proxy/URI normalization.

### 12.4. Mutual TLS

mTLS sender-constrains token với certificate/client identity trong profile phù hợp. Nó hữu ích cho workload và partner integration. Cần certificate lifecycle, private key protection, SAN identity mapping và revocation propagation.

## 13. Token storage theo loại client

| Client | Lựa chọn lưu trữ | Điều cần tránh |
| --- | --- | --- |
| Web có BFF | Access/refresh token server-side; browser giữ session cookie HttpOnly/Secure/SameSite | Đưa refresh token vào localStorage |
| SPA | Token trong memory với lifetime ngắn hoặc BFF; refresh theo policy | Persistent localStorage chứa bearer token |
| Mobile | OS secure storage/Keystore/Keychain, khóa có bảo vệ phù hợp | Plain preferences, log, backup không kiểm soát |
| Desktop native | OS credential vault hoặc hardware-backed key | File config plaintext hoặc shared profile |
| Workload | Platform identity, projected token, KMS/HSM hoặc secret manager | Static shared token trong image/repository |
| Partner server | Secret/key store được quản lý, rotation và client authentication | Dùng chung API key giữa nhiều partner |

### 13.1. Browser storage

Không có nơi lưu token nào loại bỏ mọi XSS risk. Nếu JavaScript có thể đọc bearer token, XSS có thể đánh cắp token. BFF giúp giữ OAuth token server-side và browser chỉ giữ cookie session; cookie cần HttpOnly, Secure, SameSite phù hợp và CSRF defense.

### 13.2. Mobile storage

Lưu token/refresh state trong OS-protected storage. Không log token, không nhúng secret trong binary và không coi obfuscation là secret protection. Xử lý backup/restore, device migration, root/jailbreak signals và logout theo risk policy.

## 14. Signing key, JWKS và key rotation

JWT ký số chỉ an toàn khi private key và trust distribution được bảo vệ.

### 14.1. Key custody

- Private signing key nằm trong KMS/HSM hoặc secure key service phù hợp.
- Application chỉ có quyền sign cần thiết, không export private key nếu không cần.
- Tách key theo issuer, environment và token purpose khi phù hợp.
- Tách quyền key administrator, signer và auditor.
- Audit sign operation, key policy change và key export attempt.
- Có backup/recovery và incident procedure.

### 14.2. JWKS

- Publish public key qua endpoint HTTPS của issuer đã cấu hình.
- API lấy JWKS từ issuer trust configuration, không theo URL do token cung cấp.
- Cache có refresh policy và xử lý unknown kid an toàn.
- Giữ public key cũ đủ lâu để validate token còn hiệu lực trong overlap window.
- Không chấp nhận key từ issuer khác chỉ vì cùng kid.

### 14.3. Rotation sequence

1. Tạo key pair mới trong KMS/HSM.
2. Publish public key mới trong JWKS.
3. Chờ cache consumer cập nhật theo kế hoạch.
4. Chuyển issuer sang ký bằng key mới.
5. Theo dõi validation failure và consumer lag.
6. Giữ public key cũ cho tới khi token ký bằng key cũ hết hiệu lực và cache window qua đi.
7. Remove key cũ khỏi JWKS theo policy.
8. Lưu audit, key ID, activation và retirement time.

### 14.4. Khi key compromise

Rotation thông thường không đủ nếu private key bị lộ. Cần incident response: dừng ký bằng key bị compromise, publish trust update, revoke/deny token đã ký nếu có thể, buộc refresh/reauthenticate, kiểm tra downstream và bảo toàn evidence. Phải đánh giá token đã phát hành trong khoảng thời gian key bị lộ.

## 15. Revocation và logout end-to-end

Logout phải định nghĩa rõ phần nào bị kết thúc:

- Local UI state.
- Browser/application session.
- IdP session.
- Refresh token/grant.
- Access token hiện tại.
- Downstream API session/cache.
- Federated session ở external IdP.

### 15.1. JWT revocation

JWT access token validate offline có thể còn hiệu lực tới exp. Lựa chọn:

- Lifetime ngắn và chấp nhận residual window.
- Denylist theo jti cho token cần revoke.
- Subject/session version hoặc security stamp.
- Gateway lookup/introspection.
- Disable principal hoặc client.
- Sender-constrained key revocation.

Mỗi lựa chọn có chi phí state, latency và availability. Ghi rõ thời gian tối đa token đã revoke còn được chấp nhận.

### 15.2. Logout và account compromise

Logout thường kết thúc session của client hiện tại. Khi account compromise, cần revoke tất cả session/grant liên quan, reset factor, kiểm tra recovery và token descendants. Không coi thao tác xóa cookie ở client là server-side revocation.

### 15.3. Revocation propagation map

| Thành phần | Cơ chế | Bằng chứng |
| --- | --- | --- |
| Authorization server | Revoke grant/token family | Refresh bị từ chối |
| Session service | Invalidate session | Cookie/session reference không còn active |
| API gateway | Deny subject/jti hoặc introspect | Request bằng token cũ bị từ chối |
| Resource API | Check session/version/policy khi cần | Downstream không còn chấp nhận token |
| Mobile app | Xóa local credential và yêu cầu login lại | Token không còn trong secure store |
| Federation | Logout/revoke upstream/downstream theo protocol | Session state được kiểm tra |

## 16. Scope, consent và least privilege

Token không nên cấp quyền rộng hơn use case.

- Tách read, write, admin và export.
- Tách resource audience.
- Hạn chế offline_access và refresh token.
- Consent gắn client, user, scope và purpose.
- Partner scope phải có owner và expiry/review.
- Workload chỉ có scope của service cần gọi.
- Không dùng role toàn cục nếu quyền phụ thuộc tenant/course/object.
- Authorization server không cấp scope client chưa đăng ký hoặc policy không cho phép.

Ví dụ:

| Action | Scope | Kiểm tra bổ sung |
| --- | --- | --- |
| Đọc hồ sơ của chính mình | profile:read | Subject trùng owner |
| Cập nhật tiến độ | progress:write | Course membership và state |
| Đọc chứng chỉ | certificate:read | Chứng chỉ thuộc user hoặc role được phép |
| Phát hành chứng chỉ | certificate:issue | Workload/service role, course completion và approval |
| Đọc báo cáo | report:read | Tenant và reporting dataset |

Scope là một lớp authorization, không thay thế kiểm tra business rule.

## 17. Token cho workload và service-to-service

### 17.1. Workload identity

- Mỗi service có identity riêng theo environment và trust domain.
- Issuer, subject và audience trong federation policy phải giới hạn cụ thể.
- Token có TTL ngắn, scope tối thiểu.
- Không chia sẻ service account giữa staging và production.
- Kubernetes workload dùng projected service account token với audience/expiry phù hợp.
- CI/CD chỉ nhận token production từ workflow/repository/branch/environment được phê duyệt.

### 17.2. Client authentication

Các lựa chọn:

- Workload identity federation.
- mTLS client certificate.
- private_key_jwt theo profile.
- Client secret được quản lý nếu không có phương thức tốt hơn.

Không nhúng client secret trong mobile app, SPA hoặc container image. Với confidential client, xác thực client tại token endpoint và giới hạn credential theo client/environment.

### 17.3. Token exchange

Nếu service A cần gọi service B thay mặt user, xác định rõ:

- Actor là service A.
- Subject là user gốc.
- Audience là service B.
- Scope là quyền tối thiểu của operation.
- Delegation policy cho phép A hành động thay user.
- Token exchange có audit và lifetime giới hạn.

Không forward nguyên token của user tới mọi service. Token exchange giúp giảm quyền và giới hạn audience theo từng hop.

## 18. Token privacy và logging

Token là credential. Cần bảo vệ cả token value lẫn metadata có thể liên kết hoạt động người dùng.

- Không ghi Authorization header, cookie, access/refresh token hoặc authorization code.
- Không đặt token trong URL/query string.
- Không gửi token vào analytics, crash report hoặc support ticket.
- Không đưa PII không cần thiết vào JWT payload.
- Dùng token reference hoặc jti an toàn để correlate.
- Redact ở application, gateway, proxy, APM và SIEM.
- Giới hạn quyền đọc token issuance/revocation event.
- Retention theo mục đích và data classification.
- Có canary test để phát hiện token leakage trong log.

JWT payload có thể đọc được dù signature hợp lệ. Nếu cần confidentiality, dùng cơ chế mã hóa chuẩn phù hợp hoặc giữ dữ liệu nhạy cảm ở server; không tự mã hóa claims bằng thuật toán tự chế.

## 19. Thiết kế data model và lifecycle

Authorization server có thể cần lưu grant và refresh token state:

| Entity | Trường chính | Mục đích |
| --- | --- | --- |
| Client | client_id, type, redirect URI, auth method | Xác định application |
| Grant | subject, client, scope, audience, consent time | Quyền được cấp |
| RefreshTokenFamily | family_ref, subject, client, status, created_at | Rotation/reuse/revocation |
| RefreshToken | token_hash, family_ref, issued_at, consumed_at, expires_at | Theo dõi token one-time |
| SigningKey | kid, algorithm, status, activated_at, retired_at | Quản lý signing lifecycle |
| Session | session_ref, subject, auth_time, assurance, status | Session state |
| Revocation | token/session/subject ref, reason, time, actor | Deny state và audit |

Lưu refresh token dưới dạng hash/reference nếu kiến trúc hỗ trợ, không cần lưu plaintext token để so sánh. Dùng random token có entropy cao; so sánh hash constant-time khi phù hợp và bảo vệ database/key dùng cho token digest.

### 19.1. State machine refresh token

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> Consumed: Successful rotation
    Consumed --> ReuseDetected: Old token used again
    Active --> Revoked: Logout / admin revoke
    Consumed --> Revoked: Family revoked
    Active --> Expired: TTL reached
    ReuseDetected --> Revoked: Revoke token family
    Revoked --> [*]
    Expired --> [*]
~~~

State transition phải atomic. Nếu token cũ được dùng lại, không phát token mới trước khi quyết định reuse. Cần xử lý race/retry theo policy rõ ràng và ghi audit event.

## 20. Java: token issuance policy

Ví dụ dưới đây minh họa việc kiểm tra requested scope/audience trước khi phát access token. Không tự triển khai signing primitive; dùng authorization server/library chuẩn.

~~~java
public record TokenRequestContext(
    String subjectRef,
    String clientId,
    String requestedAudience,
    Set<String> requestedScopes,
    String tenantRef,
    String grantRef
) {}

public record AccessTokenClaims(
    String issuer,
    String subject,
    String audience,
    String clientId,
    Set<String> scopes,
    String tenantRef,
    Instant issuedAt,
    Instant expiresAt,
    String tokenId
) {}

public AccessTokenClaims buildClaims(
        TokenRequestContext request,
        ClientPolicy client,
        Instant now) {

    if (!client.allowedAudiences().contains(request.requestedAudience())) {
        throw new AccessDeniedException("Audience is not allowed");
    }

    Set<String> granted = authorizationPolicy.intersect(
        request.requestedScopes(),
        client.allowedScopes(),
        policyFor(request.subjectRef(), request.tenantRef())
    );

    if (granted.isEmpty()) {
        throw new AccessDeniedException("No permitted scope");
    }

    Duration lifetime = tokenPolicy.accessTokenLifetime(
        request.requestedAudience(),
        request.clientId()
    );

    return new AccessTokenClaims(
        configuredIssuer,
        request.subjectRef(),
        request.requestedAudience(),
        request.clientId(),
        granted,
        request.tenantRef(),
        now,
        now.plus(lifetime),
        secureIds.newTokenId()
    );
}
~~~

Ví dụ cần bổ sung kiểm tra grant/consent, client authentication, authentication context, account status, tenant membership, sender constraint và audit. Scope được cấp là giao của requested scope, client registration và policy của subject/resource.

## 21. Java: refresh rotation pseudocode

~~~java
public RefreshResult rotateRefreshToken(
        String presentedToken,
        ClientContext client,
        Instant now) {

    String tokenHash = tokenDigester.digest(presentedToken);

    return transactionManager.execute(() -> {
        RefreshTokenRecord current =
            refreshRepository.lockByHash(tokenHash);

        if (current == null || !current.clientId().equals(client.clientId())) {
            return RefreshResult.invalidGrant();
        }

        RefreshTokenFamily family =
            familyRepository.lock(current.familyRef());

        if (family.isRevoked() || family.isExpired(now)) {
            return RefreshResult.invalidGrant();
        }

        if (current.isConsumed()) {
            familyRepository.revoke(
                family.id(), "refresh_token_reuse", now
            );
            audit.recordRefreshReuse(family.safeRef(), client.safeRef());
            return RefreshResult.reauthenticationRequired();
        }

        current.markConsumed(now);
        String newRefreshToken = secureRandomTokens.create();
        refreshRepository.insert(
            tokenDigester.digest(newRefreshToken),
            family.id(),
            now,
            refreshPolicy.expiryFor(family, now)
        );

        String accessToken = accessTokenIssuer.issue(
            family.subjectRef(),
            family.clientId(),
            family.audience(),
            family.scopes()
        );

        audit.recordRefreshRotation(family.safeRef(), client.safeRef());
        return RefreshResult.success(accessToken, newRefreshToken);
    });
}
~~~

Đây là pseudocode để thể hiện transaction và token family. Production cần xác thực client, grant, sender binding, account/session status, concurrent request semantics, secure random generation, constant-time digest comparison, response handling và outbox/audit reliability. Không trả token mới nếu transaction không commit.

## 22. Java: authorization tại resource server

~~~java
public Response readCertificate(
        AuthenticatedPrincipal principal,
        String certificateId) {

    authorization.requireScope(principal, "certificate:read");

    Certificate certificate = certificateRepository.find(certificateId)
        .orElseThrow(NotFoundException::new);

    authorization.requireTenant(
        principal.tenantRef(), certificate.tenantRef()
    );
    authorization.requireCanReadCertificate(
        principal.subjectRef(), certificate
    );

    audit.recordCertificateRead(
        principal.safeRef(), certificate.safeRef()
    );
    return Response.ok(certificate.publicView());
}
~~~

Ví dụ nhấn mạnh rằng token hợp lệ và scope đúng vẫn cần object-level authorization. Không trả private metadata chỉ vì token có scope chung.

## 23. Threat scenarios và cách giảm thiểu

| Kịch bản | Lỗ hổng thường gặp | Kiểm soát |
| --- | --- | --- |
| Token theft qua XSS | Token đọc được từ localStorage | BFF, CSP/XSS defense, token lifetime ngắn |
| Token gửi nhầm API | Audience không được validate | Audience-specific token và exact validation |
| ID token dùng như access token | Nhầm token semantics | Type/audience validation |
| Refresh token replay | Không rotation/reuse detection | Token family, atomic rotation và revoke |
| Authorization code replay | Code không one-time hoặc thiếu PKCE | Code binding, PKCE S256 và short TTL |
| Algorithm confusion | Server tin alg từ token | Algorithm allowlist và library chuẩn |
| JWKS key substitution | Tải key URL từ token header | Issuer-bound JWKS configuration |
| Staging compromise | Dùng chung issuer/key/client | Environment isolation |
| Scope escalation | Tin requested scope từ client | Server-side policy intersection |
| Cross-tenant access | Tin tenant header | Verified identity context và object policy |
| Logout không revoke | Chỉ xóa local token | Server-side session/grant revocation |
| Clock skew abuse | Skew quá rộng | Clock sync và bounded skew |
| Secret leakage qua log | Authorization header được ghi | Redaction ở mọi layer |
| Workload impersonation | Shared static client secret | Workload identity, mTLS/federation |
| Token replay ở API side effect | Không có idempotency/replay policy | Nonce, idempotency key và transaction state |

## 24. Kế hoạch triển khai theo giai đoạn

### Giai đoạn 1 — Inventory và contract

- Liệt kê client, API, issuer, audience, grant, scope và workload.
- Xác định loại token cho từng luồng.
- Chọn JWT/opaque theo revocation và privacy.
- Chốt claim contract và token type.
- Xác định data owner và API authorization rules.

### Giai đoạn 2 — Authorization server

- Cấu hình client registration theo loại client.
- Bật Authorization Code + PKCE cho public client.
- Giới hạn redirect URI và grant.
- Thiết kế token lifetime, refresh rotation và reuse detection.
- Đưa signing key vào KMS/HSM và chuẩn bị JWKS rotation.
- Cấu hình issuer/audience và consent/scope policy.

### Giai đoạn 3 — Resource server

- Validate signature, issuer, audience, expiry, type và scope.
- Thực thi object/tenant authorization.
- Thêm introspection/denylist nếu cần.
- Bảo vệ log và error response.
- Thêm audit event cho issuance, refresh, revoke và resource action.

### Giai đoạn 4 — Client storage và session

- BFF cookie cho web khi phù hợp.
- SPA không nhúng secret; token storage có threat model.
- Mobile dùng system browser + PKCE + OS secure storage.
- Workload dùng platform identity và short-lived token.
- Xây dựng logout, recovery và compromise flow.

### Giai đoạn 5 — Verification và rollout

- Chạy positive/negative test.
- Kiểm tra revocation propagation ở mọi API.
- Canary theo client/environment.
- Theo dõi login success, 401/403, refresh failure và token validation errors.
- Chuẩn bị rollback và incident runbook.
- Mở rộng sau khi metrics ổn định và finding được xử lý.

## 25. Ma trận kiểm thử thiết kế token

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| ID token gửi tới Learning API | API từ chối sai token type/audience |
| Access token đúng audience Learning API | Learning API validate và tiếp tục authorization |
| Access token Learning API gửi Certificate API | Certificate API từ chối audience mismatch |
| Issuer không nằm allowlist | Token bị từ chối |
| Signature sai | Token bị từ chối |
| Algorithm không allowlist | Token bị từ chối |
| Unknown kid | Refresh JWKS từ issuer tin cậy; nếu vẫn không có key thì fail closed |
| Token hết hạn | Token bị từ chối |
| Token chưa tới nbf | Token bị từ chối |
| Clock skew lớn hơn policy | Token bị từ chối hoặc cảnh báo theo rule |
| Token thiếu audience | Token bị từ chối |
| Scope không được client đăng ký | Authorization server không cấp scope đó |
| Scope đúng nhưng object thuộc tenant khác | Resource server từ chối |
| Token chứa PII không cần thiết | Claim review/policy test fail |
| JWT payload bị sửa | Signature validation fail |
| JWT payload bị đọc | Không lộ secret vì payload không chứa secret |
| Authorization code dùng lần hai | Token endpoint từ chối |
| PKCE verifier không khớp | Token endpoint từ chối |
| State/nonce không khớp | Client từ chối callback/ID token |
| Refresh token được rotate | Token cũ chuyển consumed, token mới hoạt động |
| Refresh token cũ bị reuse | Token family bị revoke theo policy |
| Hai refresh request đồng thời | Chỉ một transition hợp lệ hoặc xử lý grace semantics rõ |
| User logout | Session/grant được revoke theo policy |
| Account bị compromise | Tất cả session/token family liên quan được xử lý |
| JWT đã revoke nhưng chưa hết hạn | Gateway/resource policy chặn trong SLA đã cam kết |
| Opaque token bị revoke | Introspection trả inactive sau propagation/cache window |
| Token bị lấy nhưng thiếu DPoP key | Resource server từ chối sender binding |
| DPoP proof bị replay | Replay detection từ chối |
| mTLS certificate sai identity | Client authentication thất bại |
| Staging token gửi production | Production từ chối issuer/audience/environment |
| Workload xin scope ngoài policy | Authorization server từ chối hoặc giảm scope |
| Signing key rotation | Token mới validate; token cũ chỉ validate trong overlap được phê duyệt |
| Signing key compromise | Key bị ngừng tin cậy, token liên quan được xử lý theo IR |
| Authorization header canary trong log | Redaction test fail trước release |
| Introspection unavailable | Hệ thống thực thi fail policy đã phê duyệt và alert |
| Revocation event bị mất | Reconciliation/completeness alert phát hiện |

## 26. Tình huống thực hành tổng hợp

Nền tảng có ba client: web BFF, mobile app và partner integration. Learning API chứa tiến độ học tập; Certificate API có thể phát hành chứng chỉ; Reporting workload tổng hợp dữ liệu theo tenant. Hiện tại hệ thống dùng một JWT chung với audience platform, scope all, lifetime 30 ngày và signing key dùng chung cho dev/staging/prod. Refresh token được lưu ở localStorage trên web và mobile app tự lưu trong preferences. Khi user logout, client chỉ xóa token khỏi thiết bị.

**Yêu cầu:** đề xuất kiến trúc token mới, mô tả luồng phát hành và thu hồi, và lập test plan.

### 26.1. Thiết kế mục tiêu

| Luồng | Credential/token | Audience | Lưu trữ |
| --- | --- | --- | --- |
| Web user | OIDC login, BFF session cookie | Web BFF | Cookie HttpOnly/Secure; token ở server |
| Web BFF → Learning API | Access token riêng | Learning API | Server-side |
| Web BFF → Certificate API | Access token riêng | Certificate API | Server-side |
| Mobile user | Authorization Code + PKCE | Mobile client / API resource | OS secure storage |
| Partner integration | Confidential client token | Partner API | Secret/key store của partner |
| Reporting workload | Federated workload token | Reporting API | Token ngắn hạn, không lưu lâu |

### 26.2. Claim và scope

- Tách issuer/key theo environment.
- Mỗi API có audience riêng.
- Subject là stable user/workload reference.
- Scope tách read/write/issue.
- Tenant context do issuer/policy xác minh.
- Không đưa email, profile hoặc dữ liệu học tập vào token nếu API có thể tra cứu theo subject.
- ID token chỉ phục vụ client authentication context.
- Refresh token chỉ gửi tới authorization server.

### 26.3. Refresh và revocation

- Bật refresh token rotation và reuse detection cho client phù hợp.
- Revoke token family khi reuse được xác nhận.
- Logout BFF kết thúc server-side session và revoke grant theo policy.
- Account compromise kích hoạt revoke session/token family, disable principal và deny downstream.
- JWT access token có lifetime ngắn phù hợp; gateway có cơ chế deny hoặc introspection cho incident.
- Đo propagation từ IdP tới từng API.

### 26.4. Rollout

1. Tạo client registration, issuer, key và audience mới song song.
2. Cập nhật API validators để chấp nhận token contract mới; không chấp nhận token cũ vô thời hạn.
3. Chuyển web BFF trước, kiểm tra cookie/CSRF và downstream authorization.
4. Chuyển mobile bằng release có hỗ trợ migration/reauthentication.
5. Chuyển partner theo versioned contract và deadline.
6. Chuyển workload sang federation identity.
7. Theo dõi token validation/refresh/revocation metrics.
8. Revoke signing key/client credential cũ sau khi consumer migration hoàn tất.
9. Xác minh staging không thể xin token production.
10. Đóng migration khi legacy token không còn được chấp nhận.

## 27. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Một token cho mọi mục đích | Confused deputy và blast radius lớn | Token type/audience riêng |
| Dùng ID token gọi API | Nhầm authentication với authorization | Access token dành cho resource |
| JWT chứa profile đầy đủ | PII exposure và stale claims | Claims tối thiểu, lookup server-side |
| JWT ký được coi là mã hóa | Ai giữ token cũng đọc payload | Không đưa secret; dùng encryption chuẩn khi thật sự cần |
| Chỉ kiểm tra signature | Token đúng chữ ký nhưng sai issuer/audience | Validate full profile |
| Tin alg/kid/jku tùy token | Algorithm/key substitution | Allowlist và issuer-bound JWKS |
| Refresh token sống quá lâu | Cửa sổ theft lớn | Rotation, TTL, binding và revoke |
| Logout chỉ xóa local storage | Token cũ còn hoạt động | Server-side session/grant revocation |
| Lưu bearer token trong URL/log | Rò rỉ qua history/referrer/telemetry | Header/secure storage và redaction |
| Một key cho mọi environment | Staging compromise ảnh hưởng production | Trust/key separation |
| Scope all | Privilege quá rộng | Least privilege và resource-specific scope |
| Tin tenant header | Cross-tenant access | Verified identity context và object policy |
| Không xử lý refresh race | False positive hoặc double issuance | Atomic state và retry semantics |
| Cache introspection quá lâu | Revocation chậm | TTL theo SLA và invalidation |
| Tự viết JWT parser/crypto | Lỗi protocol/crypto | Dùng thư viện chuẩn, maintained |
| Không kiểm thử downstream | Token bị revoke ở IdP nhưng API vẫn chấp nhận | End-to-end revocation test |

## 28. Checklist nghiệm thu

### Kiến trúc và semantics

- [ ] Có inventory client, issuer, resource, audience và token type.
- [ ] ID token, access token, refresh token và session cookie có semantics riêng.
- [ ] Mỗi access token có audience phù hợp.
- [ ] Scope và role không thay object-level authorization.
- [ ] Token không chứa secret hoặc PII không cần thiết.

### Issuance và validation

- [ ] Public client dùng Authorization Code + PKCE S256.
- [ ] Redirect URI exact-match.
- [ ] State/nonce được ràng buộc transaction.
- [ ] Issuer/audience/signature/algorithm/type/expiry được validate.
- [ ] JWKS chỉ lấy từ issuer trust configuration.
- [ ] Client authentication và consent được kiểm soát.

### Lifecycle và storage

- [ ] Access token lifetime theo risk.
- [ ] Refresh token rotation/reuse policy rõ.
- [ ] Logout và compromise có server-side revoke.
- [ ] Token storage phù hợp web/mobile/workload.
- [ ] Signing key nằm trong KMS/HSM hoặc secure key service.
- [ ] Rotation, overlap, revocation và recovery đã được test.

### Abuse resistance và operations

- [ ] Replay controls phù hợp authorization code, refresh token và API operation.
- [ ] DPoP/mTLS được cân nhắc cho token theft risk.
- [ ] Dev/staging/prod tách issuer, key, client và workload identity.
- [ ] Log redaction bao phủ app, gateway, proxy, APM và SIEM.
- [ ] Revocation propagation SLA được đo ở mọi resource.
- [ ] Monitoring, incident playbook và rollback đã sẵn sàng.

## 29. Câu hỏi tự kiểm tra

1. **ID token khác access token thế nào?** ID token cung cấp authentication information cho OIDC client; access token cấp quyền truy cập resource server.
2. **Vì sao JWT không mặc nhiên bí mật?** JWS payload chỉ được encode, không được encrypt; người có token có thể đọc claims.
3. **Audience bảo vệ điều gì?** Ngăn token dành cho một resource bị dùng ở resource khác.
4. **Refresh token có nên gửi tới API nghiệp vụ không?** Không; chỉ authorization server nhận refresh token.
5. **JWT revoke có tức thời không?** Không nếu API validate offline và không có denylist/introspection hoặc cơ chế chặn khác.
6. **Vì sao cần refresh rotation?** Giúp phát hiện reuse token cũ và giới hạn tác động khi refresh token bị đánh cắp.
7. **DPoP giải quyết điều gì?** Ràng buộc token với proof-of-possession key để giảm việc dùng token bị đánh cắp đơn lẻ.
8. **Scope có đủ để authorize object không?** Không; resource server còn kiểm tra tenant, ownership và business rule.
9. **Vì sao tách signing key theo environment?** Giảm blast radius và ngăn token staging được tin ở production.
10. **Điều kiện hoàn tất thiết kế token là gì?** Có semantics, trust boundary, lifecycle, storage, validation, revocation, tests và operational evidence rõ ràng.

**Ghi nhớ:** Thiết kế token bắt đầu từ principal, client, resource và trust boundary. Tách ID/access/refresh/session; giới hạn issuer, audience, scope và lifetime; chọn JWT hoặc opaque theo nhu cầu validation/revocation; bảo vệ key và token storage; rotate/revoke có semantics; và kiểm tra end-to-end ở mọi downstream. Token hợp lệ chỉ chứng minh issuer đã phát hành một credential theo policy; resource server vẫn phải xác minh đúng audience và quyết định quyền trên từng hành động, tenant và object.
