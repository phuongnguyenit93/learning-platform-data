# Vẽ authentication flow — Thực hành mô hình hóa luồng xác thực đầu cuối

> **Chương:** Thực hành tổng hợp  
> **Chủ đề:** Vẽ authentication flow  
> **Phạm vi:** Security Authentication Fundamentals — thực hành mô hình hóa và kiểm tra luồng xác thực từ enrollment, sign-in, MFA/passkey, federation, token issuance, session, API access, service identity tới account recovery. Người học tạo được sơ đồ có trust boundary, message, state, security control, failure path và test case.

## Mục tiêu thực hành

Sau bài này, bạn có thể:

1. Chuyển yêu cầu nghiệp vụ thành scope và actor của authentication flow.
2. Xác định system boundary, trust boundary, principal, credential và protected resource.
3. Vẽ flow theo sequence diagram và data-flow diagram.
4. Phân biệt authentication, authorization, session establishment và token validation.
5. Mô tả password + MFA, passkey/WebAuthn và OIDC Authorization Code + PKCE.
6. Ghi rõ nonce, state, challenge, expiry, one-time consume, issuer, audience và proof-of-possession ở đúng vị trí.
7. Vẽ success path, failure path, retry, cancel, timeout, revoke và recovery path.
8. Đánh dấu trust assumptions, sensitive data, key operations và audit events.
9. Phân tích replay, phishing, token theft, session fixation, account takeover và confused-deputy risk trên sơ đồ.
10. Chuyển sơ đồ thành test case có precondition, action và expected result.

## 1. Vì sao phải vẽ authentication flow?

Authentication flow là chuỗi tương tác giữa user, client, identity provider, authenticator, token service, resource server và các dependency để chứng minh danh tính rồi cấp quyền truy cập.

Một sơ đồ tốt giúp trả lời:

- Ai khởi tạo transaction?
- Thành phần nào thu thập credential?
- Bằng chứng xác thực được gửi tới đâu?
- Thành phần nào kiểm tra bằng chứng?
- Identity provider phát hành kết quả cho recipient nào?
- Token/session được tạo và lưu ở đâu?
- Resource server kiểm tra điều gì trước khi thực hiện action?
- Điều gì xảy ra khi challenge hết hạn, dependency timeout hoặc user hủy?
- Làm sao thu hồi quyền truy cập sau compromise?

Nếu chỉ vẽ một mũi tên từ user tới login server rồi ghi “authenticated”, sơ đồ không cho thấy ranh giới tin cậy, transaction binding, token validation hoặc cách chống replay.

### Authentication flow không phải một màn hình

Một flow đầy đủ thường có nhiều phase:

1. Enrollment và identity binding;
2. Authentication transaction;
3. Factor verification;
4. Authentication result;
5. Token hoặc session establishment;
6. Authorization tại resource;
7. Refresh, reauthentication và revocation;
8. Recovery khi mất credential.

Không phải mọi hệ thống đều cần tất cả phase trong cùng một request, nhưng thiết kế phải xác định các phase và liên kết an toàn giữa chúng.

## 2. Bài toán thực hành xuyên suốt

Ta mô hình hóa một ứng dụng quản lý hồ sơ doanh nghiệp có web client và mobile client. Người dùng có thể đăng nhập bằng password + MFA, passkey hoặc SSO doanh nghiệp. Sau khi xác thực, ứng dụng gọi API để xem hồ sơ. Người dùng có thể đăng xuất, thu hồi session và khôi phục account khi mất factor.

### Yêu cầu nghiệp vụ

- Người dùng cá nhân có account trong identity provider;
- Doanh nghiệp có thể đăng nhập qua external OIDC identity provider;
- Web client và mobile client là public clients;
- API chỉ chấp nhận access token dành riêng cho API;
- Thao tác xem hồ sơ nhạy cảm cần quyền phù hợp;
- Thêm hoặc xóa factor yêu cầu xác thực gần đây;
- Recovery token phải có thời hạn và chỉ dùng một lần;
- Người dùng có thể revoke session đã tạo;
- Mọi thay đổi credential, factor và session đều có audit event.

### Giả định kỹ thuật của ví dụ

| Thành phần | Trách nhiệm |
| --- | --- |
| User | Khởi tạo sign-in và sử dụng tài nguyên |
| Browser/mobile app | Public client, hiển thị UI và điều phối transaction |
| Identity provider (IdP) | Quản lý account, credential, factor và phát hành token |
| Authenticator | Passkey, security key hoặc ứng dụng MFA |
| External enterprise IdP | Xác thực người dùng tổ chức |
| Authorization server | Thành phần token endpoint thuộc IdP |
| API gateway | Chuyển request tới resource server, áp dụng edge control |
| Profile API | Resource server bảo vệ hồ sơ |
| Session store | Lưu trạng thái session/revocation theo thiết kế |
| KMS/HSM | Bảo vệ private signing key |
| Audit pipeline | Ghi sự kiện đã giảm thiểu dữ liệu |

Trong hệ thống thật, một sản phẩm có thể gộp IdP và authorization server hoặc tách thành nhiều service. Sơ đồ cần phản ánh deployment thực tế thay vì mặc định tên component đồng nghĩa với một process riêng.

## 3. Quy ước trước khi vẽ

### Actor, component và data store

- Actor: người dùng, administrator, external attacker;
- Component: browser, mobile app, IdP, token endpoint, API;
- Data store: account database, credential store, session store, audit store;
- External dependency: enterprise IdP, email provider, MFA provider, KMS;
- Protected resource: hồ sơ, giao dịch hoặc API operation.

### Message

Mỗi message nên ghi:

- Sender → receiver;
- Protocol/endpoint;
- Dữ liệu hoặc proof được gửi;
- Transaction identifier;
- Validation ở receiver;
- Security property cần đạt;
- Failure result.

### Màu và ký hiệu trong sơ đồ

Trong sơ đồ thực tế, có thể quy ước:

- Mũi tên liền: request;
- Mũi tên nét đứt: response hoặc asynchronous notification;
- Khung bao: trust boundary;
- Hình trụ: data store;
- Chú thích khóa: cryptographic operation;
- Chú thích cảnh báo: untrusted input hoặc failure path.

Không dựa vào màu duy nhất; label và legend phải đủ để đọc sơ đồ ở chế độ grayscale hoặc bằng công cụ hỗ trợ.

## 4. Bắt đầu từ scope và trust boundary

Trước khi vẽ message, xác định miền tin cậy. Mỗi lần dữ liệu đi qua boundary cần biết ai có thể đọc, sửa, giả mạo hoặc replay.

### Trust boundary trong bài toán

1. User ↔ browser/mobile device;
2. Browser/mobile ↔ application backend/IdP qua Internet;
3. Client ↔ external enterprise IdP;
4. IdP ↔ account/credential/session database;
5. IdP ↔ KMS/HSM;
6. Client ↔ API gateway;
7. Gateway ↔ profile API;
8. Service ↔ audit pipeline.

### Data-flow diagram khái quát

`````````mermaid
flowchart LR
    U["User"] --> C["Browser / Mobile public client"]
    C -->|TLS requests| I["Identity Provider"]
    I --> DB[("Account and credential store")]
    I --> MFA["Authenticator / Passkey"]
    I --> KMS["KMS / HSM"]
    I -->|OIDC redirect| EIDP["Enterprise IdP"]
    C -->|Bearer access token| GW["API Gateway"]
    GW --> API["Profile API"]
    API --> DATA[("Protected profile data")]
    I --> AUD["Audit pipeline"]
    API --> AUD
`````````

### Bảng boundary

| Boundary | Dữ liệu đi qua | Rủi ro chính | Kiểm soát cần vẽ |
| --- | --- | --- | --- |
| User/device → client | Identifier, password, user gesture | Phishing, malware, shoulder surfing | TLS, trusted origin, UI context |
| Client → IdP | Authorization request, challenge response | Injection, CSRF, replay | State, nonce, PKCE, origin validation |
| IdP → database | Credential verifier, account state | Database compromise, unauthorized read | Access control, hashing, encryption, audit |
| IdP → KMS | Signing request | Key misuse, privilege escalation | Workload identity, key policy, audit |
| Client → API | Access token | Theft, replay, wrong audience | TLS, token validation, sender constraint |
| Gateway → API | Principal/context | Header spoofing, confused deputy | Strip untrusted headers, authenticated service hop |
| Component → audit | Security event | Secret leakage, log tampering | Redaction, integrity, access control |

### Câu hỏi kiểm tra

- Client có phải public client không?
- Có secret nào bị nhúng trong mobile/browser bundle không?
- API có tự validate token hay tin header từ gateway?
- KMS có chấp nhận request từ workload không được phép?
- Audit pipeline có nhận raw token hoặc password không?

## 5. Vẽ flow bằng sequence diagram

Sequence diagram cho biết thứ tự message theo thời gian. Mỗi participant là một actor/component; mỗi mũi tên là request/response hoặc event.

### Quy tắc

- Vẽ theo thứ tự thời gian từ trên xuống;
- Ghi rõ request và response;
- Đặt điều kiện trong nhánh alt/opt;
- Thể hiện retry/timeout/cancel;
- Đặt trust boundary hoặc note ở vị trí message vượt boundary;
- Đánh dấu state được tạo, consume hoặc revoke;
- Không gộp nhiều security check vào một hộp “validate”.

### Sequence diagram password + MFA

`````````mermaid
sequenceDiagram
    actor User
    participant Browser
    participant IdP
    participant CredDB as Credential Store
    participant MFA as Authenticator
    participant KMS
    User->>Browser: Enter identifier and password
    Browser->>IdP: POST sign-in over TLS
    IdP->>CredDB: Load account and password verifier
    CredDB-->>IdP: Verifier and account status
    IdP->>IdP: Verify password, rate limit, risk policy
    alt Password invalid or account denied
        IdP-->>Browser: Generic authentication failure
        Browser-->>User: Safe error and next step
    else Password valid, MFA required
        IdP->>MFA: Issue transaction-bound challenge
        MFA-->>User: Display challenge context
        User->>MFA: Approve or enter one-time proof
        MFA->>IdP: Return signed/verified result
        IdP->>IdP: Check transaction, expiry and one-time use
        alt MFA invalid, expired or denied
            IdP-->>Browser: Authentication not completed
        else MFA valid
            IdP->>KMS: Sign token using approved key
            KMS-->>IdP: Signature result
            IdP-->>Browser: OIDC result / authorization code
        end
    end
`````````

Sơ đồ tập trung vào trình tự. Trong thiết kế chi tiết, cần xác định MFA protocol, challenge binding, token delivery, client session và cách kiểm tra authorization code.

## 6. Mô hình hóa password + MFA flow

### Các bước

1. Client tạo transaction và gửi identifier;
2. IdP áp dụng rate limit và kiểm tra account state;
3. IdP xác minh password verifier;
4. Policy engine xác định MFA có bắt buộc không;
5. IdP tạo challenge gắn với transaction, subject và factor;
6. Authenticator xác minh user gesture/OTP/push;
7. IdP kiểm tra kết quả, expiry, attempt limit và replay;
8. IdP ghi authentication context;
9. IdP hoàn tất authorization flow và cấp code/token theo protocol;
10. Client tạo application session theo kiến trúc.

### State cần mô hình hóa

| State | Điều kiện chuyển | Ràng buộc |
| --- | --- | --- |
| Initiated | Client bắt đầu login | Transaction ID ngẫu nhiên, TTL |
| Primary verified | Password hợp lệ | Rate limit và account policy |
| MFA pending | Challenge được phát hành | Challenge gắn transaction/factor |
| MFA verified | Proof hợp lệ | Expiry, attempt limit, one-time consume |
| Authenticated | Policy hoàn tất | Authentication context được ghi |
| Denied | Credential/policy không hợp lệ | Không phát hành session/token |
| Expired | Quá TTL | Transaction không thể tiếp tục |
| Cancelled | User hủy | State được đóng và audit |

### Những lỗi thiết kế thường gặp

- Challenge không gắn với login transaction;
- MFA response được chấp nhận nhiều lần;
- Client tự quyết định MFA đã thành công;
- Challenge có TTL quá dài;
- Retry tạo nhiều challenge song song;
- Error của MFA provider bị hiểu nhầm thành password sai;
- Recovery fallback bỏ qua assurance requirement.

### Pseudocode kiểm tra challenge

`````````text
function verifyMfa(transactionId, challengeId, proof):
    tx = loadTransaction(transactionId)
    require tx exists
    require tx.state == "MFA_PENDING"
    require now < tx.expiresAt
    require challengeId == tx.challengeId
    require challenge.subject == tx.subject
    require challenge.transactionId == transactionId
    require verifyProof(challenge.factor, proof)
    require atomicConsume(challengeId)
    markTransactionAuthenticated(tx)
`````````

Pseudocode minh họa các invariant. Trong triển khai thật, verifyProof và atomicConsume phải bảo đảm tính nhất quán khi nhiều request/region xử lý đồng thời.

## 7. Mô hình hóa passkey/WebAuthn flow

Passkey flow dựa trên challenge-response bằng public-key credential. Client khởi tạo ceremony, authenticator tạo assertion, relying party server xác minh.

### Registration

1. User đã có session đủ assurance;
2. Client yêu cầu registration options;
3. Server tạo challenge ngẫu nhiên, TTL ngắn, gắn với subject;
4. Browser gọi WebAuthn create;
5. Authenticator tạo credential và trả attestation response;
6. Server xác minh challenge, origin, RP ID hash, type và các trường theo policy;
7. Server lưu credential public key và metadata cần thiết;
8. Server ghi audit và thông báo enrollment.

### Authentication

1. Client yêu cầu assertion options;
2. Server tạo challenge mới và transaction state;
3. Browser gọi WebAuthn get;
4. Authenticator xác minh user presence/verification theo policy và ký assertion;
5. Client gửi assertion tới server;
6. Server kiểm tra challenge, origin, RP ID hash, signature, credential, flags và counter/backup semantics theo loại authenticator;
7. Server consume challenge một lần và hoàn tất authentication;
8. Server cập nhật session/token theo policy.

### Sequence diagram passkey

`````````mermaid
sequenceDiagram
    actor User
    participant Browser
    participant RP as Relying Party Server
    participant Auth as Authenticator
    User->>Browser: Choose passkey sign-in
    Browser->>RP: Request assertion options
    RP->>RP: Create random challenge and transaction
    RP-->>Browser: challenge, rpId, allowCredentials, timeout
    Browser->>Auth: WebAuthn get()
    Auth-->>User: User verification prompt
    User->>Auth: Verify with local gesture
    Auth-->>Browser: Signed assertion
    Browser->>RP: Submit assertion and transaction reference
    RP->>RP: Verify origin, rpIdHash, challenge, signature, flags
    RP->>RP: Atomically consume challenge
    RP-->>Browser: Authentication result
`````````

### Invariant cần ghi

- Challenge được tạo từ server và không đoán được;
- Challenge có TTL và chỉ consume một lần;
- Origin và RP ID được kiểm tra chính xác;
- Credential phải thuộc đúng subject/allowlist;
- User verification requirement khớp assurance policy;
- Assertion không được dùng lại cho transaction khác;
- Enrollment yêu cầu session đủ mạnh;
- Xóa/revoke credential có audit và thông báo.

Không coi attestation là bắt buộc trong mọi use case. Yêu cầu attestation phụ thuộc threat model, privacy và ecosystem; phải mô tả rõ policy thay vì mặc định tin mọi authenticator.

## 8. Mô hình hóa OIDC Authorization Code + PKCE

Đối với web/mobile public client, Authorization Code Flow với PKCE giúp bảo vệ authorization code nếu code bị chặn hoặc chuyển tới client khác.

### Tạo transaction

Client tạo:

- State ngẫu nhiên để binding callback với request;
- Nonce ngẫu nhiên cho ID token theo OIDC;
- Code verifier bí mật tạm thời;
- Code challenge là S256 của verifier;
- Redirect URI đã đăng ký chính xác.

Client lưu transaction state ở nơi an toàn, gắn với browser/app context và TTL.

### Authorization request

Client chuyển user tới authorization endpoint với response_type=code, client_id, redirect_uri, scope, state, nonce, code_challenge và code_challenge_method=S256.

### Callback và token exchange

1. IdP xác thực user và consent/policy;
2. IdP redirect authorization code và state về redirect URI;
3. Client so sánh state với transaction đang chờ;
4. Client gửi code, verifier, client_id và redirect_uri tới token endpoint;
5. Authorization server kiểm tra code, redirect URI, PKCE verifier, client và expiry;
6. Token endpoint phát hành token;
7. Client xác minh ID token theo OIDC requirements;
8. Client tạo local session hoặc sử dụng access token theo thiết kế.

### Sequence diagram OIDC

`````````mermaid
sequenceDiagram
    actor User
    participant Client
    participant AS as Authorization Server
    participant IdP
    participant API as Resource Server
    User->>Client: Start sign-in
    Client->>Client: Generate state, nonce, verifier and S256 challenge
    Client->>AS: Authorization request with PKCE
    AS->>IdP: Authenticate user if needed
    IdP-->>AS: Authentication result
    AS-->>Client: Redirect with code and state
    Client->>Client: Validate state
    Client->>AS: Token request with code and verifier
    AS->>AS: Validate code, redirect URI and PKCE
    AS-->>Client: ID token and access token
    Client->>Client: Validate ID token and nonce
    Client->>API: Request with access token
    API->>API: Validate access token and authorization
    API-->>Client: Protected resource response
`````````

### Phân biệt token

- ID token: kết quả authentication dành cho OIDC client;
- Access token: credential truy cập resource server;
- Refresh token: credential lấy access token mới theo policy.

Không gửi ID token tới API như access token. Không dùng access token để chứng minh login cho client nếu protocol không quy định.

## 9. Vẽ API access và authorization

Authentication thành công không tự động cho phép mọi action. Resource server phải xác minh token và authorization policy ở server-side.

### Token validation checklist

- Chọn issuer từ trust configuration;
- Kiểm tra signature bằng key được issuer công bố qua kênh tin cậy;
- Allowlist algorithm;
- Kiểm tra issuer;
- Kiểm tra audience;
- Kiểm tra expiry và not-before;
- Kiểm tra token type/profile;
- Kiểm tra scope/permission;
- Kiểm tra tenant và subject binding;
- Kiểm tra authentication context/freshness khi action yêu cầu;
- Áp dụng revocation/introspection/version policy nếu có.

### Sequence diagram API

`````````mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant API as Profile API
    participant Policy
    participant Data as Profile Store
    Client->>Gateway: HTTPS request with access token
    Gateway->>Gateway: Edge checks and request limits
    Gateway->>API: Forward request and trusted context
    API->>API: Validate token issuer, signature, audience, time
    API->>Policy: Authorize subject, scope, tenant and action
    Policy-->>API: Allow or deny
    alt Allowed
        API->>Data: Read permitted profile fields
        Data-->>API: Profile data
        API-->>Client: Success response
    else Denied
        API-->>Client: Safe authorization error
    end
`````````

### Gateway trust

Nếu gateway chuyển user/role header cho API, API phải biết header đó được gateway tạo sau khi strip mọi header cùng tên từ client. Một header như X-User-ID do client tự gửi không phải bằng chứng danh tính.

### Authorization decision

Ghi rõ:

- Subject;
- Resource;
- Action;
- Scope/role;
- Tenant boundary;
- Context/assurance;
- Policy version;
- Decision và reason code.

Không nhúng toàn bộ authorization logic vào UI hoặc tin role từ client-side state.

## 10. Vẽ session lifecycle

Session là trạng thái duy trì sau authentication. Cần thể hiện create, rotate, use, refresh, expiry và revoke.

### State model

| State | Ý nghĩa | Transition |
| --- | --- | --- |
| Anonymous | Chưa có session | Login thành công |
| Authenticated | Session mới được tạo | Request hợp lệ |
| Active | Session còn hiệu lực | Refresh/reauthentication |
| Step-up required | Action cần assurance cao hơn | Hoàn tất step-up |
| Expired | Quá idle/absolute TTL | Login lại |
| Revoked | Bị thu hồi | Không thể tái sử dụng |

### Session security

- Rotate session ID sau login và privilege elevation;
- Cookie có Secure, HttpOnly, SameSite phù hợp;
- Chống CSRF cho state-changing request;
- Idle timeout và absolute timeout;
- Revoke server-side khi logout hoặc compromise;
- Session list cho phép user quản lý thiết bị;
- Không ghi session cookie vào log;
- Không để logout chỉ xóa cookie client mà session server vẫn active.

### Refresh

Nếu dùng refresh token rotation:

- Token mới thay token cũ;
- Token cũ không được dùng lại;
- Reuse detection có thể revoke token family;
- Client xử lý concurrent refresh có kiểm soát;
- Revoke/logout cập nhật state theo SLA;
- Refresh token được lưu trong nơi phù hợp với client type.

## 11. Vẽ account recovery và factor replacement

Recovery là flow xác minh lại quyền sở hữu account khi credential hoặc factor không còn khả dụng.

### Recovery flow

1. User yêu cầu recovery;
2. Service áp dụng rate limit và response chống enumeration;
3. Proof được gửi qua kênh đã đăng ký hoặc quy trình identity proofing;
4. User hoàn tất xác minh độc lập;
5. Server kiểm tra token purpose, TTL, signature/reference và single-use;
6. User thiết lập credential/factor mới;
7. Server revoke factor/session/token cũ theo policy;
8. Gửi notification và ghi audit;
9. Theo dõi risk sau recovery.

### Sequence diagram recovery

`````````mermaid
sequenceDiagram
    actor User
    participant App
    participant Recovery
    participant Channel as Verified Recovery Channel
    participant Account as Account Service
    User->>App: Request account recovery
    App->>Recovery: Submit identifier
    Recovery->>Recovery: Rate limit and generic response
    Recovery->>Channel: Send one-time recovery reference
    Channel-->>User: Recovery instructions
    User->>App: Open recovery page and prove ownership
    App->>Recovery: Submit recovery proof
    Recovery->>Recovery: Verify purpose, expiry and one-time state
    Recovery->>Account: Replace credential/factor and revoke old state
    Account-->>Recovery: State updated
    Recovery-->>User: Recovery completed and security notice
`````````

### Recovery threats cần gắn trên sơ đồ

- Email mailbox bị compromise;
- Link bị lộ trong URL/log/referrer;
- Email scanner consume link;
- Token bị replay;
- Factor reset không có reauthentication;
- Support social engineering;
- Session cũ không bị revoke;
- Recovery response tiết lộ account existence.

## 12. Vẽ service-to-service authentication

Không chỉ user mới cần authentication. Workload/service cũng phải chứng minh identity với service nhận request.

### Ví dụ client credentials

1. Workload có identity được cấp bởi platform;
2. Workload xác thực với authorization server bằng phương thức client authentication đã đăng ký;
3. Authorization server kiểm tra client identity và scope;
4. Token được cấp với audience của service đích;
5. Workload gọi API;
6. Resource server kiểm tra signature/issuer/audience/scope và workload policy.

### Sequence diagram

`````````mermaid
sequenceDiagram
    participant Workload
    participant AS as Authorization Server
    participant KMS
    participant API as Internal API
    Workload->>AS: Client authentication
    AS->>AS: Validate workload identity and policy
    AS->>KMS: Sign audience-bound access token
    KMS-->>AS: Signature
    AS-->>Workload: Short-lived access token
    Workload->>API: Request with access token
    API->>API: Validate token and workload scope
    API-->>Workload: Allow or deny
`````````

### Ràng buộc

- Client credential không được nhúng trong public client;
- Workload identity gắn với service/account/environment;
- Token có audience hẹp và lifetime ngắn;
- Scope theo action cần thiết;
- Private key/secret nằm trong secret manager hoặc HSM/Keystore phù hợp;
- Rotation/revocation có inventory và owner;
- Không tin source IP như identity duy nhất.

## 13. Vẽ failure path, retry và degraded mode

Sơ đồ chỉ có success path thường bỏ sót phần dễ gây bypass hoặc outage.

### Failure cần thể hiện

- Invalid credential;
- Account disabled/locked;
- MFA denied/expired/provider timeout;
- Passkey unavailable/origin mismatch;
- OIDC state/nonce/PKCE failure;
- Token signature/issuer/audience failure;
- JWKS/KMS/database/session store unavailable;
- API authorization denied;
- Recovery proof invalid/replayed;
- User cancel và transaction timeout.

### Failure semantics

| Lỗi | Hành vi an toàn |
| --- | --- |
| Credential invalid | Từ chối, rate limit, message không enumeration |
| MFA invalid/expired | Không hoàn tất authentication; challenge cũ không dùng lại |
| MFA provider timeout | Service error/degraded policy đã duyệt; không tự bỏ MFA |
| Unknown signing key | Refresh JWKS có giới hạn; không bỏ qua signature |
| JWKS unavailable | Dùng key cache còn tin cậy theo policy; key chưa biết bị từ chối |
| Introspection timeout | Fail-closed sau cache TTL hoặc policy degraded đã phê duyệt |
| Database unavailable | Không giả định account/credential hợp lệ |
| KMS signing unavailable | Không phát hành token bằng key trái phép |
| Session store unavailable | Không tạo session giả hoặc coi cookie không xác minh là trusted |
| Recovery token replay | Từ chối và ghi event |

### Retry

- Retry chỉ với lỗi tạm thời và operation có semantics an toàn;
- Dùng deadline, backoff, jitter và retry budget;
- Không retry vô hạn password/MFA submission;
- Không tạo challenge mới khi transaction cũ còn pending;
- Idempotency key cần được binding với operation và principal;
- Ghi retry count để phát hiện retry storm.

### Degraded mode

Với từng action, ghi:

- Dependency nào unavailable;
- Action nào có thể tiếp tục;
- Bằng chứng nào còn đủ để quyết định;
- TTL của cache/last-known-good;
- Điều kiện fail-closed;
- Người phê duyệt và audit.

Không dùng một cờ global “auth bypass” cho toàn hệ thống.

## 14. Gắn threat và security control lên flow

Mỗi message vượt trust boundary cần có threat/control tương ứng.

| Message/step | Threat | Control | Test |
| --- | --- | --- | --- |
| Password submit | Credential theft, brute force | TLS, password hashing, rate limit | Invalid/repeated attempt |
| MFA challenge | Push fatigue, OTP replay | Transaction binding, TTL, one-time consume | Deny/replay/expiry |
| Passkey assertion | Origin confusion, replay | Origin/RP ID/challenge/signature validation | Wrong origin/reused challenge |
| OIDC redirect | CSRF, code interception | State, nonce, PKCE, exact redirect URI | State/verifier mismatch |
| Token issuance | Key misuse, overbroad scope | KMS policy, audience/scope restriction | Unauthorized signing/scope |
| API request | Token theft, confused deputy | Issuer/audience/signature/authz | Wrong issuer/audience/tenant |
| Session refresh | Token reuse | Rotation, family detection | Reuse old refresh token |
| Recovery | Account takeover | Independent proof, single-use, notify | Replay and enumeration |
| Service call | Workload spoofing | Workload identity, mTLS/token audience | Wrong identity/credential |

### Threat annotation

Trên sơ đồ có thể gắn ID như T-01, T-02. Bên cạnh mỗi threat ghi:

- Attacker precondition;
- Action;
- Impact;
- Preventive control;
- Detective signal;
- Response/revoke action;
- Evidence/test reference.

Điều này giúp reviewer truy từ sơ đồ sang risk register và test suite.

## 15. Dữ liệu nhạy cảm và logging trong flow

Sơ đồ nên phân biệt dữ liệu đi qua message với dữ liệu được phép ghi log.

### Data classification

| Dữ liệu | Classification tham khảo | Logging |
| --- | --- | --- |
| Password | Restricted secret | Không log |
| OTP/TOTP seed/recovery code | Restricted secret | Không log |
| Access/refresh/ID token | Restricted credential | Không log raw value |
| Session cookie | Restricted credential | Không log |
| Authorization code | Sensitive short-lived credential | Không log raw value |
| Subject reference | Confidential/pseudonymous | Chỉ log khi cần và có access control |
| Client ID/audience | Internal metadata | Có thể log theo policy |
| Outcome/reason code | Operational/security metadata | Log có cấu trúc |
| Request ID | Correlation metadata | Log theo policy |
| IP/device context | Personal/security data | Minimize, retention và access control |

### Ví dụ event

`````````json
{
  "event_name": "auth.login.succeeded",
  "event_time": "2026-11-22T07:15:20Z",
  "subject_ref": "sub-hmac-31a9",
  "client_id": "web-portal",
  "auth_method": "passkey",
  "assurance": "policy-defined",
  "session_ref": "sess-ref-01",
  "request_id": "req-7d11",
  "outcome": "success"
}
`````````

Event minh họa không chứa raw credential. Pseudonymous reference vẫn là dữ liệu có thể liên kết và cần retention/access policy.

## 16. Từ flow diagram tới test plan

Mỗi message và state transition cần có test positive, negative và boundary.

### Test case template

| Trường | Nội dung |
| --- | --- |
| Test ID | ID duy nhất |
| Flow/Threat ID | Bước hoặc threat trên sơ đồ |
| Precondition | Account, client, key, session, policy |
| Input/action | Request hoặc thao tác cần kiểm tra |
| Expected decision | Allow/deny/challenge |
| Expected state | State trước/sau |
| Side effect | Token/session/record có được tạo không |
| Evidence | Log, response, audit event, trace |
| Cleanup | Revoke session/token hoặc reset fixture |

### Ví dụ: sai audience

`````````yaml
test_id: AUTH-FLOW-API-007
flow_step: API token validation
precondition:
  token_signature: valid
  issuer: trusted-issuer
  audience: another-api
action: Call profile API with the token
expected:
  decision: deny
  protected_action: not_executed
  session_created: false
  audit_reason: wrong_audience
`````````

### Ví dụ: replay MFA challenge

`````````text
Given a valid MFA challenge bound to transaction A
When the same proof is submitted a second time
Then the second submission is rejected
And transaction A cannot be completed twice
And no second session or token is issued
And an audit event records the replay attempt
`````````

## 17. Quy trình thực hành từng bước

Thực hiện theo thứ tự sau để tạo một authentication flow có thể review.

### Bước 1 — Viết context

Ghi:

- Business action cần bảo vệ;
- User/service principal;
- Client type;
- Identity provider;
- Authentication method;
- Protected API/resource;
- Assurance requirement;
- Recovery requirement.

### Bước 2 — Inventory component

Liệt kê browser/mobile, IdP, authenticator, token endpoint, API gateway, resource server, session store, database, KMS và audit pipeline.

### Bước 3 — Vẽ trust boundary

Vẽ các miền sở hữu và trust. Đánh dấu external IdP, browser, device, network, KMS và resource API.

### Bước 4 — Vẽ success sequence

Vẽ message theo thứ tự. Ghi dữ liệu và transaction reference tại từng bước. Tách authentication result khỏi authorization decision.

### Bước 5 — Thêm state và invariant

Ghi state transition, TTL, one-time consume, issuer/audience, proof binding, session rotation và revoke.

### Bước 6 — Thêm failure branch

Vẽ invalid credential, MFA deny, timeout, cancel, replay, dependency outage và authorization deny.

### Bước 7 — Gắn threat/control

Gắn threat ID, preventive control, detective event, response và owner.

### Bước 8 — Tạo test matrix

Mỗi trust boundary và transition có positive/negative test. Kiểm tra side effect, không chỉ HTTP status.

### Bước 9 — Review và version

Ghi owner, version, date, assumptions, unresolved risk và approval. Cập nhật khi protocol, client, issuer, key hoặc recovery policy thay đổi.

## 18. Bài thực hành tổng hợp: vẽ flow cho ứng dụng hồ sơ

### Đề bài

Vẽ một sơ đồ đầu cuối đáp ứng các yêu cầu:

1. User đăng nhập bằng passkey hoặc password + MFA;
2. Nhân viên có thể chọn enterprise SSO qua OIDC;
3. Public client dùng Authorization Code + PKCE;
4. API chỉ chấp nhận access token có audience riêng;
5. Thao tác xem hồ sơ kiểm tra scope và tenant;
6. Session có expiry, logout và revoke;
7. User có thể recovery khi mất passkey;
8. Credential/factor change tạo audit event;
9. MFA provider outage không tự động bỏ MFA;
10. Token/secret không xuất hiện trong log.

### Sơ đồ tham chiếu

`````````mermaid
flowchart TD
    U["User"] --> APP["Web / Mobile public client"]
    APP --> CHOOSE{"Choose authentication method"}
    CHOOSE --> PK["Passkey ceremony"]
    CHOOSE --> PW["Password verification"]
    CHOOSE --> SSO["OIDC Authorization Code + PKCE"]
    PW --> MFA["MFA challenge if policy requires"]
    PK --> IDP["Identity Provider"]
    MFA --> IDP
    SSO --> IDP
    IDP --> TOKEN["Issue audience-bound tokens"]
    TOKEN --> APP
    APP --> GW["API Gateway"]
    GW --> API["Profile API"]
    API --> AUTHZ["Validate token and authorize scope/tenant"]
    AUTHZ --> DATA[("Profile data")]
    APP --> SESSION["Session management"]
    APP --> REC["Account recovery"]
    REC --> IDP
    IDP --> AUD["Audit and monitoring"]
    API --> AUD
`````````

### Điểm cần bổ sung trước khi phê duyệt

- Sequence riêng cho từng authentication method;
- OIDC state, nonce, verifier/challenge và exact redirect URI;
- Passkey origin, RP ID, challenge, signature và user verification;
- MFA transaction binding, expiry, rate limit và replay;
- Token issuer, audience, algorithm, expiry và key rotation;
- Gateway strip untrusted identity headers;
- API authorization theo subject, tenant, scope và action;
- Session ID rotation, idle/absolute timeout và revoke;
- Recovery proof, one-time token, notification và revoke old sessions;
- Failure path cho KMS, database, JWKS, MFA và IdP;
- Logging redaction và audit event;
- Owner và test evidence cho từng control.

## 19. Lỗi thường gặp khi vẽ authentication flow

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Một mũi tên “login” duy nhất | Không thể review proof hoặc trust boundary | Vẽ từng request/response |
| Không phân biệt authn/authz | Login success bị hiểu là được phép mọi action | Tách token validation và policy decision |
| Bỏ qua enrollment | Factor có thể được thêm bởi attacker | Vẽ enrollment và recovery |
| Không có failure path | Không biết hệ thống phản ứng khi dependency lỗi | Thêm alt/timeout/cancel/retry |
| Không ghi issuer/audience | Token có thể dùng sai resource | Ghi rõ validation ở recipient |
| Không có state/nonce/PKCE | Transaction có thể bị CSRF/interception | Vẽ binding values và validation |
| Không có one-time consume | Challenge/code/recovery có thể replay | Ghi atomic consume |
| Tin header từ client | Có thể spoof principal | Chỉ tin context được gateway tạo và bảo vệ |
| Không vẽ session lifecycle | Logout/revoke không được xác minh | Vẽ create/rotate/expire/revoke |
| Không vẽ recovery | Recovery trở thành bypass | Review như authentication flow riêng |
| Không ghi KMS boundary | Signing key bị dùng sai | Vẽ signer identity và key policy |
| Không ghi logging | Secret có thể rò vào telemetry | Phân loại event và redaction |
| Chỉ test success | Bỏ sót replay, wrong audience và outage | Test negative, concurrency và failure |
| Không có owner/version | Sơ đồ nhanh lỗi thời | Version, owner, review trigger |

## 20. Bộ kiểm thử chấp nhận

| Test | Input/tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| Flow completeness | Review toàn bộ sơ đồ | Có enrollment, login, token, API, session, recovery |
| Trust boundary | Gửi request qua từng boundary | Có validation/control ở receiver |
| Password success | Credential hợp lệ | Authentication tiếp tục theo policy |
| Password failure | Credential sai | Không tạo session/token |
| Password spraying | Nhiều account bị thử | Rate limit/detection hoạt động |
| MFA success | Challenge hợp lệ | Transaction hoàn tất đúng một lần |
| MFA replay | Gửi lại proof | Từ chối, không tạo token thứ hai |
| MFA expiry | Submit sau TTL | Từ chối |
| MFA provider outage | Provider timeout | Không bypass assurance |
| Passkey success | Assertion hợp lệ | Xác minh đúng subject |
| Passkey origin | Origin sai | Từ chối |
| Passkey RP ID | RP ID hash sai | Từ chối |
| Passkey replay | Challenge đã consume | Từ chối |
| Passkey enrollment | Session yếu thêm factor | Yêu cầu reauthentication |
| OIDC state | State mismatch | Callback bị từ chối |
| OIDC nonce | Nonce mismatch | ID token bị từ chối |
| PKCE verifier | Verifier sai | Token endpoint từ chối |
| Redirect URI | URI không đăng ký | Authorization server từ chối |
| Code replay | Authorization code dùng lần hai | Token endpoint từ chối |
| ID/access confusion | Gửi ID token tới API | Resource server từ chối |
| JWT signature | Signature sai | Resource server từ chối |
| JWT issuer | Issuer ngoài trust | Resource server từ chối |
| JWT audience | Audience API khác | Resource server từ chối |
| JWT expiry | Token hết hạn | Resource server từ chối |
| Scope | Scope thiếu | Authorization deny |
| Tenant | Tenant không khớp | Cross-tenant access bị từ chối |
| Gateway header | Client tự gửi trusted header | Gateway strip/overwrite |
| Session fixation | Session ID trước login | Session ID được rotate |
| Session logout | Dùng session sau revoke | Server từ chối theo SLA |
| Refresh reuse | Dùng refresh token cũ | Family reuse policy kích hoạt |
| Recovery enumeration | Account tồn tại/không tồn tại | Response công khai nhất quán |
| Recovery replay | Dùng token đã consume | Từ chối |
| Recovery session | Hoàn tất recovery | Session/token cũ bị xử lý theo policy |
| Service identity | Workload identity sai | Resource server từ chối |
| KMS permission | Workload không được phép ký | KMS từ chối và audit |
| JWKS outage | Không tải được key set | Chỉ dùng key cache còn tin cậy; unknown key fail-closed |
| Session store outage | Store unavailable | Không tạo session giả |
| Logging | Marker secret đi qua flow | Marker không xuất hiện trong log |
| Audit | Credential/factor change | Event có actor, subject, time và outcome |
| Retry | Dependency timeout | Deadline/backoff giới hạn retry |
| Cancel | User hủy MFA/SSO | Transaction đóng, không cấp session |
| Concurrent consume | Hai request dùng cùng challenge | Chỉ một request thành công |

## 21. Checklist hoàn thiện authentication flow

- **Scope:** Business action, user, client, IdP và resource đã rõ?
- **Actors:** User, client, authenticator, service, admin và external provider được vẽ?
- **Trust boundary:** Mọi miền tin cậy và data flow đã đánh dấu?
- **Credential:** Enrollment, verification, rotation và revoke có mặt?
- **MFA/passkey:** Challenge, origin/RP ID, expiry, user verification và replay được mô tả?
- **Federation:** Issuer, redirect URI, state, nonce, PKCE, audience và signature được xác minh?
- **Token:** ID/access/refresh phân biệt rõ; scope/audience/lifetime đúng?
- **API:** Resource server validate token và authorization ở server-side?
- **Session:** Create, rotate, refresh, expire, logout và revoke được vẽ?
- **Recovery:** Proof, one-time token, factor replacement và session revoke?
- **Service identity:** Workload principal, client auth, audience và secret lifecycle?
- **Failure:** Invalid, denied, timeout, outage, retry, cancel và degraded mode?
- **Privacy:** Sensitive claim, password, OTP, token và log được bảo vệ?
- **Audit:** Event, actor, subject, request ID và outcome?
- **Threat:** Phishing, replay, theft, fixation, confused deputy và privilege escalation?
- **Testing:** Positive, negative, replay, concurrency, tenant isolation và outage?
- **Ownership:** Sơ đồ có owner, version, date, assumption và review trigger?

### Câu hỏi tự kiểm tra

1. Một authentication flow cần những actor và component tối thiểu nào?
2. Vì sao trust boundary quan trọng hơn việc chỉ vẽ network topology?
3. State, nonce và PKCE verifier bảo vệ những mối liên kết nào?
4. Vì sao passkey challenge phải được consume một lần?
5. Resource server cần kiểm tra những trường nào của access token?
6. Vì sao ID token không phải access token?
7. Session revoke khác xóa cookie ở client như thế nào?
8. Recovery có thể tạo ra đường bypass MFA ra sao?
9. Vì sao API gateway không được tin header identity do client gửi?
10. Cần bổ sung những nhánh nào để sơ đồ phản ánh outage và degraded mode?

## Kết luận

**Một authentication flow có thể review phải cho thấy ai gửi bằng chứng gì qua trust boundary nào, thành phần nào xác minh, state nào được tạo và quyền nào được cấp hoặc thu hồi.** Bắt đầu từ scope, actor và tài sản; vẽ success sequence cho password/MFA, passkey và federation; sau đó tách token validation, API authorization, session lifecycle và recovery. Mỗi bước cần transaction binding, expiry, one-time semantics, issuer/audience validation, audit và failure behavior phù hợp. Cuối cùng, gắn threat/control/test vào từng boundary để sơ đồ trở thành tài liệu thiết kế và kiểm chứng, không chỉ là hình minh họa luồng đăng nhập.
