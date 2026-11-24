# Hoàn thiện hồ sơ authentication

> **Chương:** Thực hành tổng hợp  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Bài thực hành:** Thiết kế, kiểm thử và chuẩn bị phê duyệt một hệ thống xác thực hoàn chỉnh, từ danh tính và credential đến session, federation, recovery và vận hành sự cố.

## 1. Mục tiêu bài thực hành

Trong bài này, người học đóng vai nhóm kỹ thuật và security của một nền tảng thương mại điện tử có cổng khách hàng, cổng nhân viên và các API nội bộ. Nhiệm vụ là hoàn thiện một **hồ sơ authentication** đủ rõ để đội phát triển triển khai, đội vận hành theo dõi và người review đánh giá.

Hồ sơ không chỉ mô tả màn hình đăng nhập. Nó phải trả lời được:

- Ai đang truy cập: người dùng, nhân viên, quản trị viên hay workload?
- Danh tính được chứng minh bằng credential nào và nguồn nào cấp credential?
- Hệ thống xác minh credential qua trust boundary nào?
- Khi nào cần MFA hoặc step-up? Yếu tố nào chống phishing?
- Token và session có audience, scope, lifetime, rotation và revocation ra sao?
- Federation và identity linking dựa trên thuộc tính nào?
- Khi mất thiết bị hoặc bị chiếm tài khoản, recovery có an toàn không?
- Làm thế nào phát hiện brute force, credential stuffing, replay và MFA fatigue?
- Khi IdP, signing key hoặc credential bị compromise, đội ứng cứu có thể containment không?
- Bằng chứng nào cần có trước khi sign-off?

### Kết quả cần đạt

Sau khi hoàn thành, người học có thể:

1. Chuyển yêu cầu sản phẩm thành yêu cầu authentication có thể kiểm thử.
2. Lập inventory principal, credential, factor và dependency.
3. Vẽ trust boundary và luồng xác thực cho người dùng lẫn workload.
4. Thiết kế password, MFA, passkey, certificate, token, session và federation.
5. Xây dựng identity linking và account recovery có kiểm soát.
6. Viết threat model, policy matrix và test matrix.
7. Xác định telemetry, privacy, incident response và rollout.
8. Tập hợp evidence và đưa ra quyết định go/no-go có trách nhiệm.

## 2. Tình huống và giả định

Nền tảng ShopSphere cung cấp:

- Cổng khách hàng để đăng ký, đăng nhập, xem đơn hàng và thanh toán.
- Cổng nhân viên để xử lý đơn, hoàn tiền và hỗ trợ khách hàng.
- Cổng quản trị để quản lý cấu hình và quyền.
- Các service nội bộ như Order, Inventory, Payment và Notification.
- Đăng nhập liên kết cho nhân viên qua Identity Provider (IdP) doanh nghiệp.
- API cho workload và đối tác tích hợp.

Hệ thống có ba nhóm principal:

| Nhóm | Ví dụ | Mức rủi ro |
|---|---|---|
| Customer | Khách hàng mua hàng | Tài khoản, thông tin cá nhân, đơn hàng và thanh toán |
| Workforce | Nhân viên hỗ trợ/vận hành | Dữ liệu khách hàng và thao tác nghiệp vụ |
| Privileged workforce | Admin, security operator | Cấu hình trust, quyền, credential và dữ liệu diện rộng |
| Workload | Order Service, Payment Service | Giao tiếp service-to-service và dữ liệu nghiệp vụ |
| Partner client | Đối tác gọi API | Phạm vi API được cấp theo hợp đồng |

Giả định ban đầu:

- Customer dùng password hoặc passkey; MFA được yêu cầu theo risk và thao tác nhạy cảm.
- Workforce đăng nhập qua OIDC với IdP doanh nghiệp; privileged workforce cần phishing-resistant MFA.
- Workload dùng identity riêng, token ngắn hạn và TLS/mTLS theo kiến trúc.
- Ứng dụng có session server-side cho browser.
- API dùng access token có audience và scope.
- Recovery phải có đường hỗ trợ khi mất thiết bị nhưng không được trở thành đường bypass MFA.

Đây là giả định để làm bài. Khi áp dụng vào hệ thống thật, thay bằng dữ liệu đã được owner xác nhận; không tự coi ví dụ là cấu hình production.

## 3. Phạm vi và ranh giới trách nhiệm

Trước khi thiết kế, ghi rõ thành phần nào thuộc hệ thống và thành phần nào là dependency.

### Trong phạm vi

- Đăng ký và xác minh danh tính ở mức phù hợp với loại tài khoản.
- Login, logout, MFA và step-up.
- Password và passkey lifecycle.
- OIDC federation cho workforce.
- Identity linking giữa tài khoản nội bộ và external identity.
- Token issuance/validation, session management và revocation.
- API/workload authentication.
- Account recovery và factor replacement.
- Authorization handoff, audit, monitoring và incident containment.

### Dependency cần owner

| Dependency | Trách nhiệm | Câu hỏi cần xác minh |
|---|---|---|
| Customer identity store | Credential và account state | Ai quản lý, backup và revoke? |
| Workforce IdP | Nhân viên và privileged authentication | Issuer, MFA policy, key rotation và incident contact? |
| Email/SMS provider | Notification và một số recovery channel | Delivery, abuse controls và data handling? |
| KMS/HSM | Signing key và secret operation | Key custody, access audit và emergency rotation? |
| Session store | Server-side session | Consistency, TTL, backup và revoke propagation? |
| API gateway | Routing và token enforcement | Trusted proxy, header handling và policy ownership? |
| Monitoring/SIEM | Detection và audit | Retention, access control và alert owner? |

Một dependency có thể nằm ngoài quyền quản trị trực tiếp nhưng vẫn nằm trong trust model. Ghi assumption, service level, owner và cách ứng phó khi dependency lỗi.

## 4. Yêu cầu chức năng và security invariant

Viết yêu cầu thành điều kiện có thể kiểm chứng. Tránh các câu chung chung như “authentication phải an toàn”.

### Yêu cầu chức năng

- Customer có thể đăng ký, xác minh kênh liên hệ và đăng nhập bằng phương thức được hỗ trợ.
- Customer có thể đăng ký, sử dụng và thu hồi passkey.
- Workforce dùng IdP được cấu hình; portal không tự chấp nhận issuer tùy ý.
- Privileged action yêu cầu assurance phù hợp, có thể bao gồm step-up.
- Workload được cấp token cho đúng resource và scope.
- User có thể logout, revoke session và khôi phục tài khoản theo policy.
- Người dùng nhận thông báo trạng thái rõ ràng, có hướng dẫn tiếp theo.

### Security invariant

1. Không có full session trước khi tất cả bước xác thực bắt buộc hoàn tất.
2. Principal chỉ được xác định từ credential hoặc assertion đã xác minh.
3. Client input không thể tự đặt user ID, role, tenant hoặc authentication context đáng tin.
4. Token chỉ được chấp nhận khi issuer, signature, audience, thời hạn và policy hợp lệ.
5. Session cũ bị vô hiệu hóa sau các sự kiện yêu cầu rotation/revocation.
6. Challenge, authorization code, nonce và recovery token có scope, lifetime và one-time semantics theo protocol.
7. Recovery không được yếu hơn đến mức attacker có thể bỏ qua kiểm soát chính.
8. Authentication thành công không tự động cấp quyền nghiệp vụ.
9. Dependency outage không biến thành xác thực thành công.
10. Secret và credential không xuất hiện trong log, trace hoặc error response.

### Traceability

Mỗi yêu cầu cần có ID, owner, test case và evidence. Ví dụ:

| Requirement | Điều kiện | Test/evidence |
|---|---|---|
| AUTH-01 | MFA pending không tạo full session | Test state transition |
| AUTH-02 | OIDC callback kiểm tra state và nonce | Integration test |
| AUTH-03 | API từ chối sai audience | Token negative test |
| AUTH-04 | Logout revoke server-side session | Multi-node test |
| AUTH-05 | Recovery token chỉ dùng một lần | Recovery test |
| AUTH-06 | Workload không có scope không được gọi API | Resource server policy test |

## 5. Identity inventory

Tạo danh sách principal và nguồn authority. Định danh cần ổn định trong phạm vi issuer và không dựa vào email thay đổi được.

| Principal | Identifier đề xuất | Nguồn authority |
|---|---|---|
| Customer | Internal customer ID | Customer identity service |
| Workforce | Issuer + subject từ IdP | Workforce IdP |
| Privileged workforce | Issuer + subject + privileged role assignment | IdP và access governance |
| Order workload | Workload principal riêng | Runtime identity provider |
| Payment workload | Workload principal riêng | Runtime identity provider |
| Partner client | Client ID trong partner registry | Authorization server/partner onboarding |

### Quy tắc định danh

- Với federated identity, dùng cặp issuer và subject ổn định theo protocol.
- Không tự động hợp nhất hai account chỉ vì email giống nhau.
- Email và số điện thoại là thuộc tính liên hệ; chúng có thể thay đổi hoặc được tái cấp.
- Internal customer ID không được lấy trực tiếp từ browser input rồi tin cậy.
- Workload principal phải gắn với workload/runtime được attestation.
- Mọi liên kết, unlink và merge identity phải có audit và quy trình recovery.

### Bài tập

Hãy xác định:

1. Principal nào có thể đăng nhập tương tác?
2. Principal nào chỉ được dùng cho API?
3. Identifier nào ổn định và ai có quyền thay đổi?
4. Nếu IdP đổi email của nhân viên, tài khoản nội bộ có còn liên kết đúng không?
5. Nếu một partner client bị thu hồi, các client khác có bị ảnh hưởng không?

## 6. Credential và factor inventory

Một hồ sơ hoàn chỉnh cần biết credential nào được phát hành, lưu ở đâu, dùng cho mục đích nào và thu hồi bằng cách nào.

| Credential/factor | Principal | Nơi giữ hoặc xác minh | Vòng đời chính |
|---|---|---|---|
| Password | Customer | Verifier trong identity service | Set, verify, reset, revoke |
| Passkey | Customer/workforce | Private key ở authenticator; public key phía server | Register, assert, revoke |
| TOTP secret | Principal đã đăng ký MFA | Authenticator và verifier | Enroll, verify, rotate/revoke |
| Push factor | Principal workforce | Authenticator/provider | Enroll, approve/deny, revoke |
| Recovery code | Customer/workforce | Người dùng; verifier lưu dạng bảo vệ | Issue, use once, rotate |
| Client certificate | Workload | Key store/KMS/HSM và verifier | Issue, renew, revoke |
| Access token | User/workload/client | Client và resource server | Issue, validate, expire, revoke |
| Refresh token | Client/user session | Client và authorization server | Rotate, reuse detection, revoke |
| Session cookie | Browser user | Browser và session store | Issue, rotate, expire, revoke |
| API key | Partner client nếu được phép | Secret manager và API gateway | Issue, scope, rotate, revoke |

Với từng credential, ghi owner, audience/use, storage, expiry, rotation, revoke, backup/recovery và log restrictions.

## 7. Chọn authentication method theo assurance

Không cần dùng cùng một phương thức cho mọi principal và hành động. Chọn theo rủi ro, khả năng hỗ trợ và yêu cầu vận hành.

| Use case | Phương thức gợi ý | Lý do và giới hạn |
|---|---|---|
| Customer login thông thường | Passkey hoặc password với risk control | Passkey chống phishing tốt hơn; password cần bảo vệ chống stuffing |
| Customer thanh toán hoặc đổi recovery | Step-up bằng passkey/MFA phù hợp | Tăng assurance trước hành động nhạy cảm |
| Workforce login | OIDC với IdP doanh nghiệp | Tập trung lifecycle và policy |
| Privileged workforce | Passkey/security key hoặc phương thức phishing-resistant | Giảm rủi ro phishing và MFA fatigue |
| Service-to-service | Workload identity, token ngắn hạn, mTLS khi phù hợp | Danh tính riêng và least privilege |
| Partner API | OAuth client authentication hoặc certificate theo hợp đồng | Có client identity, scope và revoke |
| Break-glass | Credential riêng, kiểm soát nghiêm và audit | Duy trì ứng cứu khi IdP lỗi |

Không tuyên bố mọi MFA đều phishing-resistant. TOTP và push có thể tăng bảo vệ so với password đơn lẻ nhưng vẫn có rủi ro phishing hoặc fatigue. Passkey/WebAuthn ràng buộc với origin/RP ID, nhưng vẫn cần bảo vệ thiết bị, recovery và account lifecycle.

## 8. Password policy và flow

### Policy đề xuất

- Dùng password hashing chuyên dụng, salt riêng và tham số phù hợp.
- Không lưu password rõ hoặc log password.
- Hỗ trợ password manager, paste và autofill.
- Cho phép password dài và Unicode theo contract nhất quán.
- Chặn password phổ biến hoặc đã bị lộ theo policy.
- Giới hạn login attempts và phát hiện credential stuffing.
- Phản hồi public không tiết lộ account existence.
- Password reset token ngẫu nhiên, scope hẹp, one-time và expiry.

### Login flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant W as Web App
    participant A as Authentication Service
    participant S as Session Store
    U->>W: Submit identifier and password
    W->>A: Login request over TLS
    A->>A: Apply rate limit and verify password
    A->>A: Check account state and MFA policy
    A-->>W: Challenge required or generic rejection
    W-->>U: Continue MFA or show safe error
    Note over U,S: Full session is created only after required factors pass
~~~

### Kiểm tra

- Account không tồn tại và password sai không tạo account enumeration.
- Password đúng nhưng MFA pending không cấp full session.
- Account suspended không đăng nhập được.
- Rate limit không khóa vĩnh viễn chỉ vì attacker cố tình tạo failure.
- Reset password xử lý session và refresh token theo policy.

## 9. MFA và step-up policy

MFA policy phải mô tả khi nào yêu cầu yếu tố bổ sung, factor nào được chấp nhận và cách xử lý mất factor.

| Hành động | Policy gợi ý |
|---|---|
| Customer xem đơn hàng | Login theo risk policy |
| Customer thay email/password | Reauthentication hoặc step-up |
| Customer đổi recovery method | Step-up và notification |
| Customer thanh toán | Step-up theo risk/transaction policy |
| Workforce mở portal | IdP policy và MFA |
| Privileged user thay đổi access policy | Phishing-resistant MFA và approval |
| Admin truy cập signing key/KMS | Strong authentication, least privilege và audit |

### MFA controls

- Challenge gắn với principal, session và action.
- Challenge có expiry, retry limit và one-time behavior.
- Push hiển thị context; người dùng có thể deny và báo cáo prompt lạ.
- TOTP window nhỏ, có rate limit và kiểm soát replay.
- Factor add/remove yêu cầu xác minh phù hợp.
- Recovery code chỉ dùng một lần, không log và có thể rotate.
- Factor enrollment/removal tạo audit event.

### Step-up

Step-up cần ràng buộc với hành động cụ thể. Một challenge hoàn tất để xem hồ sơ không tự động được dùng để phê duyệt hoàn tiền hoặc thay đổi signing key.

## 10. Passkey và WebAuthn

Passkey là credential khóa công khai/riêng; private key nằm trong authenticator hoặc hệ sinh thái đồng bộ được hỗ trợ, server giữ public key và credential metadata.

### Registration

1. Người dùng đã xác minh bắt đầu đăng ký.
2. Server tạo challenge mới và gắn với principal/session.
3. Browser thực hiện WebAuthn ceremony với RP ID và origin đúng.
4. Server kiểm tra challenge, origin, RP ID hash, credential ID, public key và user verification theo policy.
5. Server lưu public key và metadata cần thiết.
6. Audit ghi credential được thêm, không ghi private key hoặc raw assertion.

### Authentication

- Server tạo challenge mới.
- Authenticator tạo assertion.
- Server xác minh signature bằng public key đã đăng ký.
- Server xác minh challenge, origin, RP ID và user verification.
- Server xác định principal từ credential record, không từ user ID do client tự gửi.

### Lifecycle và UX

- Người dùng xem và thu hồi passkey.
- Thiết bị mất có quy trình recovery.
- Thêm passkey mới yêu cầu proof/step-up phù hợp.
- Synced passkey và security key được đánh giá theo assurance và policy.
- Thông báo lỗi giúp người dùng thử thiết bị/phương thức khác mà không tiết lộ credential inventory cho unauthenticated caller.

## 11. Certificate và workload identity

Workload không nên dùng tài khoản người dùng hoặc API key dùng chung. Mỗi workload cần principal riêng và nguồn cấp credential được tin cậy.

### Thiết kế

- Runtime/identity provider xác minh workload.
- Workload nhận certificate hoặc credential ngắn hạn.
- Private key được bảo vệ bằng KMS/HSM hoặc runtime keystore.
- Resource server xác minh certificate chain, SAN/URI identity, validity và policy.
- mTLS bảo vệ kênh và xác minh peer khi được cấu hình.
- Authorization vẫn kiểm tra scope, audience và hành động.

### Vòng đời

- Issuance có owner và trust domain.
- Renewal trước expiry.
- Rotation có overlap được kiểm soát.
- Revocation được áp dụng ở mọi verifier.
- Offboarding workload thu hồi identity và secret.

Certificate hợp lệ chứng minh một identity theo trust configuration; nó không tự cấp mọi quyền nghiệp vụ.

## 12. Federation và OIDC

Workforce portal dùng OIDC với IdP doanh nghiệp. Ứng dụng cần xác minh toàn bộ protocol context.

### Flow bắt buộc

- Authorization Code Flow với PKCE theo client profile.
- state liên kết request và callback.
- nonce liên kết ID token với authentication request.
- Redirect URI khớp chính xác cấu hình.
- Authorization code one-time và có expiry.
- ID token được xác minh signature, issuer, audience, thời gian và required claims.
- JWKS/discovery chỉ lấy từ issuer được allowlist.
- Account linking dựa trên issuer + subject ổn định.

### Identity linking

Không tự hợp nhất hai account chỉ vì email giống nhau. Flow linking cần:

1. Người dùng đã đăng nhập vào account hiện tại.
2. Xác minh quyền kiểm soát external identity.
3. Kiểm tra issuer và subject.
4. Kiểm tra identity đã liên kết với account khác chưa.
5. Hiển thị kết quả và yêu cầu xác nhận khi phù hợp.
6. Ghi audit event và notification.
7. Cung cấp quy trình unlink/recovery có step-up.

### Logout

Logout cục bộ kết thúc session của relying party. Nó không tự động revoke mọi refresh token hoặc session của ứng dụng khác. Hồ sơ cần mô tả local logout, IdP logout và token/grant revocation riêng.

## 13. Token policy

Token contract phải xác định loại token, issuer, audience, scope, lifetime, storage, refresh, revocation và validation.

### Ví dụ access token

~~~json
{
  "iss": "https://identity.shopsphere.example",
  "sub": "customer-482",
  "aud": "orders-api",
  "iat": 1795341600,
  "nbf": 1795341600,
  "exp": 1795341900,
  "jti": "token-ref-7f31",
  "scope": "orders.read orders.cancel"
}
~~~

Đây là dữ liệu minh họa, không phải token production. Token thực tế phải tuân theo issuer profile và không chứa dữ liệu cá nhân không cần thiết.

### Resource server validation

- Issuer được tin cậy.
- Signature và algorithm nằm trong allowlist.
- Audience khớp API hiện tại.
- exp, nbf và các claim bắt buộc hợp lệ.
- Scope/permission đủ cho action.
- Key rotation và cache có policy.
- Token revoked/denylisted được xử lý nếu kiến trúc hỗ trợ.

Access token và ID token có mục đích khác nhau. Không dùng ID token thay access token để gọi API. Không tin JWT chỉ vì payload decode được.

### Refresh token

- Lưu và truyền qua kênh bảo vệ.
- Rotation/reuse detection theo policy.
- Revoke token family khi có dấu hiệu compromise.
- Không đưa refresh token vào browser storage/log.
- Xác minh logout/recovery có xử lý refresh token.

### Bearer và sender constraint

Bearer token có thể bị dùng bởi người sở hữu token. Với rủi ro cao, cân nhắc sender-constrained token như mTLS-bound hoặc DPoP theo kiến trúc và profile hỗ trợ. Không tuyên bố timestamp hoặc jti tự động ngăn replay nếu server không có cơ chế thực thi.

## 14. Session policy

Browser session là credential có vòng đời riêng.

| Thuộc tính | Quyết định cần ghi |
|---|---|
| Session ID | Sinh ngẫu nhiên, không chứa thông tin đoán được |
| Rotation | Rotate sau login và step-up |
| Cookie | Secure, HttpOnly, SameSite và scope phù hợp |
| Idle timeout | Hết hạn sau khoảng không hoạt động |
| Absolute timeout | Giới hạn tổng thời gian session |
| Reauthentication | Yêu cầu lại cho hành động nhạy cảm |
| Logout | Invalidate server-side session |
| Revocation | Xử lý khi password reset, compromise, disable account |
| Propagation | Đồng bộ trên node, region và downstream |

### Test session

- Session ID trước login không còn hợp lệ sau authentication.
- Cookie không xuất hiện trong URL, log hoặc analytics.
- Logout từ một node làm session cũ bị từ chối theo propagation contract.
- Session hết hạn không được gia hạn bởi background request ngoài policy.
- Account recovery xử lý session cũ và refresh token liên quan.

## 15. Account recovery

Recovery cần cân bằng khả năng lấy lại tài khoản và nguy cơ attacker dùng recovery để bypass MFA.

### Flow đề xuất

1. Người dùng bắt đầu recovery từ domain/app chính thức.
2. Public response không tiết lộ account existence.
3. Hệ thống gửi challenge tới kênh đã đăng ký nếu phù hợp.
4. Người dùng chứng minh quyền kiểm soát theo assurance policy.
5. Thay đổi password hoặc factor được thực hiện trong scope giới hạn.
6. Token recovery bị dùng một lần và hết hạn.
7. Session, refresh token và factor đáng ngờ được revoke theo policy.
8. Notification được gửi tới kênh đã xác minh.
9. Audit ghi actor, phương thức, kết quả và thời điểm.

### Helpdesk recovery

- Nhân viên hỗ trợ không yêu cầu password, OTP, recovery code hoặc private key.
- Proofing không chỉ dựa trên dữ liệu cá nhân dễ đoán.
- Reset MFA cần approval và audit theo risk.
- Break-glass có danh tính cá nhân, scope, expiry và review.
- Recovery channel bị compromise phải được xử lý trước khi reset factor.

### Recovery test

- Token sai, hết hạn hoặc đã dùng bị từ chối.
- Account enumeration không xảy ra.
- Recovery không tự cấp full session ngoài policy.
- Thay factor yêu cầu proof phù hợp.
- Session cũ được revoke theo policy.

## 16. Authorization boundary

Authentication xác minh principal; authorization quyết định principal được làm gì. Hai bước phải có policy và test riêng.

### Quy tắc

- Role không được lấy từ browser input hoặc header tùy ý.
- Gateway xóa identity header do client tự gửi trước khi thêm trusted context.
- Backend chỉ tin context từ gateway qua kênh đã xác minh.
- Role mapping dùng issuer, subject và group identifier ổn định.
- Tenant và resource ownership được kiểm tra tại server.
- Default deny cho quyền không được cấp.
- Privileged action có step-up và approval phù hợp.
- Workload principal không thể tự giả làm user principal.

### Ma trận minh họa

| Principal | Resource | Action | Kết quả |
|---|---|---|---|
| Customer A | Đơn của Customer A | orders.read | Allow |
| Customer A | Đơn của Customer B | orders.read | Deny |
| Workforce support | Hồ sơ hỗ trợ theo policy | customer.support.read | Allow |
| Workforce support | Signing key | kms.key.admin | Deny |
| Privileged admin | Identity policy | identity.policy.update | Step-up + approval |
| Order workload | Inventory reservation | inventory.hold | Allow |
| Order workload | Payment refund | payment.refund | Deny |

## 17. Threat model tổng hợp

Xác định attacker, mục tiêu, khả năng và control tương ứng.

| Threat | Attack path | Control cần có |
|---|---|---|
| Phishing | Trang giả lấy password/OTP | Passkey, origin binding, domain hygiene, user education |
| Credential stuffing | Dùng password rò rỉ | Rate limit, breached-password check, MFA/risk |
| Password spraying | Một password trên nhiều account | Detection theo nguồn và account distribution |
| MFA fatigue | Spam push đến khi user approve | Context, number matching, deny/report, rate limit |
| TOTP replay | Dùng lại mã đã chấp nhận | One-time step policy, rate limit |
| Session theft | Đánh cắp cookie | HttpOnly/Secure, XSS/CSRF controls, rotation, revoke |
| Token replay | Dùng bearer token bị lộ | Short lifetime, audience, sender constraint khi phù hợp |
| OIDC mix-up | Sai issuer/state/redirect | state, nonce, PKCE, issuer allowlist |
| Identity linking abuse | Hợp nhất account bằng email trùng | Proof cả hai identity, issuer+subject, audit |
| Recovery abuse | Chiếm email/helpdesk | Proofing, one-time token, approval, notification |
| Workload impersonation | Giả service nội bộ | Workload identity, mTLS, audience/scope |
| Privilege escalation | Giả role hoặc group claim | Verified claims, server-side mapping, default deny |
| Key compromise | Ký token giả hoặc giả peer | KMS/HSM, rotation, revoke, verifier update |
| Enumeration | Dò account qua response | Generic response, timing/status consistency |
| Dependency outage | Bỏ qua kiểm tra khi IdP lỗi | Fail closed, bounded cache, runbook |

### Risk register

Với mỗi threat, ghi:

- Asset/principal bị ảnh hưởng.
- Likelihood và impact.
- Control hiện có.
- Evidence/test.
- Residual risk.
- Owner và due date.

Không ghi “đã có MFA” như một control hoàn chỉnh nếu chưa nêu loại factor, phạm vi, recovery path và cách kiểm thử.

## 18. Authentication flow tổng hợp

### Customer login bằng passkey hoặc password + MFA

~~~mermaid
flowchart TD
    A["Open official login page"] --> B{"Choose method"}
    B -->|Passkey| C["WebAuthn challenge"]
    B -->|Password| D["Verify password"]
    D --> E{"MFA required?"}
    E -->|Yes| F["MFA challenge"]
    E -->|No| G["Apply risk and account policy"]
    C --> H["Verify assertion, origin, RP ID"]
    F --> I["Verify challenge and expiry"]
    H --> G
    I --> G
    G --> J{"All required checks pass?"}
    J -->|No| K["Safe error and audit"]
    J -->|Yes| L["Rotate session and issue session"]
~~~

### Workforce OIDC

1. Portal tạo state, nonce và PKCE verifier/challenge.
2. Browser được chuyển tới issuer đã allowlist.
3. IdP xác thực workforce và áp dụng MFA policy.
4. Callback kiểm tra state, code và PKCE.
5. Backend đổi code, xác minh ID token và required claims.
6. Principal được xác định bằng issuer + subject.
7. Role được mapping từ nguồn đã xác minh.
8. Session mới được tạo và audit event được ghi.

### Workload API

1. Runtime attestation xác định workload principal.
2. Workload chứng minh client identity với authorization server.
3. Authorization server cấp token audience/scope cụ thể.
4. Resource server xác minh token và transport identity.
5. Service kiểm tra authorization và business invariant.
6. Request có idempotency/replay control phù hợp.

## 19. Bảng quyết định tổng hợp

Điền bảng này bằng quyết định đã được owner chấp thuận. Cột ví dụ chỉ là baseline cho bài tập.

| Chủ đề | Baseline minh họa | Quyết định của nhóm | Evidence |
|---|---|---|---|
| Customer primary auth | Passkey hoặc password | Điền | Registration/login test |
| Customer step-up | Theo action/risk | Điền | Step-up test |
| Workforce auth | OIDC với enterprise IdP | Điền | OIDC integration test |
| Privileged MFA | Phishing-resistant | Điền | MFA policy/test |
| Password storage | Dedicated password hash | Điền | Config review |
| Session | Server-side, rotate, bounded timeout | Điền | Session lifecycle test |
| Access token | Short-lived, audience/scope-bound | Điền | Token validation test |
| Refresh token | Rotation/reuse detection | Điền | Refresh test |
| Workload auth | Unique identity + token, mTLS where needed | Điền | Service integration test |
| Identity linking | Issuer + subject, proof both sides | Điền | Linking negative test |
| Recovery | One-time proof, limited scope, notification | Điền | Recovery test |
| Logging | No raw secrets, controlled audit | Điền | Secret scan/privacy review |
| Revocation | Propagation verified | Điền | Multi-node test |

Không để cột quyết định trống khi trình sign-off. Nếu một chủ đề ngoài phạm vi, ghi rõ lý do, dependency và người chấp nhận residual risk.

## 20. Kế hoạch kiểm thử end-to-end

Kiểm thử cần bao phủ hành vi hợp lệ, lỗi, ranh giới thời gian, replay, concurrency và dependency.

| ID | Scenario | Kết quả mong đợi |
|---|---|---|
| E2E-01 | Customer login bằng passkey hợp lệ | Principal đúng, session mới |
| E2E-02 | Password đúng, MFA pending | Không có full session |
| E2E-03 | Password sai/account không tồn tại | Response public không enumeration |
| E2E-04 | TOTP sai/hết hạn/replay | Challenge bị từ chối theo policy |
| E2E-05 | Push MFA bị deny | Login không hoàn tất |
| E2E-06 | WebAuthn origin/RP ID sai | Assertion bị từ chối |
| E2E-07 | OIDC state/nonce/PKCE sai | Callback không tạo session |
| E2E-08 | ID token sai issuer/audience/signature | Token bị từ chối |
| E2E-09 | Token hết hạn hoặc chưa đến nbf | Resource server từ chối |
| E2E-10 | Token audience API khác | Resource server từ chối |
| E2E-11 | Session logout/revoke | Session cũ bị từ chối trên mọi node |
| E2E-12 | Recovery token đã dùng | Request bị từ chối |
| E2E-13 | Identity linking chỉ dựa email trùng | Linking bị từ chối |
| E2E-14 | Customer truy cập đơn tenant khác | Authorization deny |
| E2E-15 | Workload gọi API ngoài scope | Authorization deny |
| E2E-16 | API key/certificate bị revoke | Credential cũ bị từ chối |
| E2E-17 | IdP hoặc KMS unavailable | Fail-safe, không bypass auth |
| E2E-18 | Clock skew vượt tolerance | Token/certificate xử lý theo policy |
| E2E-19 | Nhiều request cùng nonce | One-time claim được thực thi atomic |
| E2E-20 | Credential xuất hiện trong log/trace | Secret scan phát hiện và test fail |

### Phân tầng test

- Unit: policy, claim validation helper, state transition.
- Component: authentication service với test dependency.
- Contract: API, OIDC profile, token response và error schema.
- Integration: IdP, session store, directory, KMS và MFA adapter.
- End-to-end: browser, API, federation, recovery và logout.
- Security test: enumeration, replay, spoofing, abuse và boundary bypass.

Mock phù hợp để mô phỏng lỗi dependency, nhưng không thay thế integration test cho chữ ký, WebAuthn, OIDC callback, mTLS hoặc revocation propagation.

## 21. Test data và môi trường

- Dùng test tenant, test IdP và test principal riêng.
- Không sao chép password, TOTP seed, private key hoặc token production.
- Dùng fake clock/test harness cho expiry và clock skew.
- Tách test identity để test song song không đè state của nhau.
- Secret test được inject từ secret manager/CI protected variable.
- Không in Authorization header, cookie hoặc request body nhạy cảm vào console.
- Dọn session, token, recovery challenge và credential sau test.
- Giữ test artifact không chứa PII/secret không cần thiết.
- Ghi build, config version, environment và test data version vào report.

## 22. Monitoring và privacy

Metric phải định nghĩa rõ attempt, challenge và terminal outcome. Không đếm mỗi HTTP retry thành một login mới nếu đó là cùng operation.

### Metric cần có

- Login attempts, completions, success/failure và abandoned.
- Failure reason group: credential, challenge, policy, rate limit, dependency.
- Login processing latency và MFA challenge duration.
- Token issuance/validation failure theo reason group.
- Session create/revoke/expiry.
- OIDC callback và JWKS refresh failure.
- Workload principal/audience/scope denial.
- Recovery request và factor replacement.
- Rate-limit, credential stuffing và MFA fatigue signal.

### Privacy

- Không log password, OTP, recovery code, raw token, cookie hoặc private key.
- Metric label dùng tập hữu hạn như method, outcome, region và dependency.
- Không dùng email, username, IP đầy đủ, token ID hoặc request ID làm label.
- Audit có principal reference pseudonymous khi cần.
- Log access được giới hạn, audit và retention.
- Không đưa authentication secret vào analytics/trace baggage.

## 23. Incident response và containment

Hồ sơ phải mô tả hành động khi credential hoặc trust infrastructure bị compromise.

### Account takeover

- Hạn chế/suspend principal theo incident policy.
- Revoke mọi session và refresh token liên quan.
- Kiểm tra passkey/factor/recovery method mới.
- Revoke OAuth grant và downstream session nếu cần.
- Bảo vệ email/phone recovery.
- Xác minh credential cũ bị từ chối ở mọi node.

### Workload credential compromise

- Cô lập workload.
- Revoke identity, certificate, token hoặc key.
- Kiểm tra request downstream và quyền đã sử dụng.
- Cấp credential mới qua trust path đã xác minh.
- Triển khai lại workload từ image/config sạch.

### IdP/signing key compromise

- Bảo vệ admin plane và kênh break-glass.
- Ngừng dùng signing key bị compromise.
- Cập nhật verifier, gateway, JWKS cache và federation partner.
- Đánh giá token đã phát hành trong khoảng bị ảnh hưởng.
- Thu hồi session/grant và xác minh propagation.

### Evidence

Giữ authentication audit, factor changes, token metadata cần thiết, IdP admin events, KMS/HSM audit, gateway/workload logs và timeline. Không lưu raw credential trong incident ticket.

## 24. Rollout và migration

Thay đổi authentication cần rollout theo giai đoạn để giảm outage và tránh để lại đường cũ không kiểm soát.

1. Inventory flow, client, credential, dependency và owner.
2. Chốt policy và threat model.
3. Triển khai ở test/staging với identity riêng.
4. Chạy contract, integration, negative và end-to-end test.
5. Shadow/observe nếu phù hợp để phát hiện client chưa tương thích.
6. Enforce theo nhóm user/service/region.
7. Theo dõi login success, dependency, denial, latency và abuse.
8. Có rollback plan không làm suy yếu trust boundary.
9. Thu hồi credential cũ sau khi mọi consumer đã chuyển.
10. Cập nhật runbook, support content và evidence.

Không duy trì shared secret hoặc legacy flow vô thời hạn chỉ để tránh thay đổi client. Mỗi ngoại lệ cần owner, scope, compensating control và expiry.

## 25. Evidence package và sign-off

Hồ sơ cuối cần có:

- Scope, owner, build và environment.
- Identity/credential inventory.
- Architecture và trust boundary diagrams.
- Authentication flow diagrams.
- Policy matrix cho principal, factor, token, session và recovery.
- Threat model và risk register.
- Test plan, test report và evidence reference.
- Monitoring dashboard, alert owner và runbook.
- Privacy/logging/retention decision.
- Incident containment và recovery plan.
- Findings, residual risk và exception.
- Quyết định approve, conditional approval hoặc no-go.

### Quyết định

| Trạng thái | Điều kiện |
|---|---|
| Approve | Control bắt buộc đạt, evidence đủ, residual risk trong ngưỡng |
| Conditional approval | Có điều kiện cụ thể, owner, deadline, compensating control và release gate |
| No-go | Có finding không chấp nhận hoặc thiếu evidence trọng yếu |
| Deferred | Chưa đủ thông tin để quyết định |

Không coi sign-off là bảo đảm không có lỗ hổng. Quyết định chỉ áp dụng cho scope, build, cấu hình và thời điểm đã ghi.

## 26. Mẫu hồ sơ authentication

Ví dụ YAML minh họa cấu trúc hồ sơ. Dữ liệu phải được thay bằng quyết định thực tế và lưu trong hệ thống governance của tổ chức.

~~~yaml
profile:
  name: shopsphere-authentication
  version: 1.0
  environment: production
  owner: identity-platform
principals:
  - type: customer
    identifier: internal-customer-id
    methods: [passkey, password]
  - type: workforce
    identifier: issuer-and-subject
    methods: [oidc, phishing-resistant-mfa]
  - type: workload
    identifier: attested-workload-principal
    methods: [workload-identity, short-lived-token, mtls]
session:
  browser: server-side
  rotate_after_login: true
  idle_timeout: defined-by-risk-policy
  absolute_timeout: defined-by-risk-policy
token:
  issuer: approved-identity-provider
  audience: explicit-per-resource
  lifetime: short-lived
  refresh_rotation: enabled
recovery:
  one_time_token: true
  public_response: generic
  revoke_related_sessions: true
controls:
  phishing_resistant_for_privileged: required
  default_deny: true
  secrets_in_logs: prohibited
  revocation_propagation_test: required
approval:
  status: pending
  risk_owner: assigned-approver
  evidence_reference: review-package-id
~~~

Các giá trị như timeout, lifetime và method phải được xác định từ threat model, protocol profile và khả năng vận hành; không dùng placeholder trong production.

## 27. Bài tập hoàn thiện hồ sơ

Thực hiện lần lượt và lưu từng quyết định trong hồ sơ của nhóm:

### Bước 1 — Inventory

- Liệt kê principal, identifier, credential, factor và dependency.
- Ghi owner, source of truth, expiry, rotation và revoke.
- Xác định account nào có privileged access.

### Bước 2 — Architecture

- Vẽ browser, gateway, application, IdP, session store, token issuer và resource server.
- Đánh dấu trust boundary và đường truyền credential.
- Thể hiện workload identity và federation riêng.

### Bước 3 — Flow

- Vẽ customer login, workforce OIDC, passkey enrollment, step-up, workload token và recovery.
- Ghi điều kiện chuyển trạng thái và điểm tạo session/token.
- Chỉ rõ failure path và retry.

### Bước 4 — Policy

- Chọn authentication method theo principal/action.
- Xác định MFA/step-up, token audience/scope, session timeout và recovery proof.
- Ghi authorization boundary và default deny.

### Bước 5 — Threat model

- Chọn ít nhất mười threat có liên quan.
- Ghi attack path, impact, control, test và residual risk.
- Xác định threat nào yêu cầu phishing-resistant authentication.

### Bước 6 — Test

- Viết ít nhất hai positive và hai negative test cho mỗi flow chính.
- Thêm boundary test cho expiry, replay, rotation và revoke.
- Kiểm tra multi-node, dependency outage và privacy.

### Bước 7 — Operations

- Xây dashboard và alert.
- Viết runbook cho account takeover, workload compromise và IdP/key compromise.
- Xác định owner, escalation và break-glass.

### Bước 8 — Sign-off

- Thu thập evidence.
- Phân loại finding.
- Ghi residual risk và approver.
- Đưa ra approve, conditional approval hoặc no-go.

## 28. Rubric đánh giá

| Tiêu chí | Điểm tối đa | Điều kiện đạt điểm cao |
|---|---:|---|
| Identity/credential inventory | 10 | Principal và vòng đời rõ, owner xác định |
| Trust boundary/architecture | 10 | Luồng và trust assumption không mơ hồ |
| Authentication method/policy | 10 | Phù hợp assurance, phishing và risk |
| Token/session/federation | 15 | Audience, scope, expiry, state, nonce và revoke đúng |
| Linking/recovery | 10 | Không dựa email đơn thuần, recovery không bypass |
| Authorization boundary | 10 | Least privilege, tenant/resource checks, default deny |
| Threat model | 10 | Attack path, control và residual risk cụ thể |
| Test evidence | 10 | Positive/negative/boundary/integration đủ |
| Monitoring/incident/privacy | 10 | Có metric, runbook, containment và data controls |
| Sign-off/traceability | 5 | Owner, evidence, finding và quyết định rõ |
| **Tổng** | **100** | |

Điều kiện tối thiểu: không được đạt yêu cầu nếu còn đường bypass xác minh issuer/signature, session không thể revoke, recovery cho phép takeover không kiểm soát hoặc secret production bị đưa vào test/evidence.

## 29. Checklist cuối cùng

- [ ] Phạm vi, owner, environment và dependency được ghi.
- [ ] Principal và identifier ổn định; human và workload identity tách biệt.
- [ ] Credential inventory có issuance, storage, expiry, rotation và revoke.
- [ ] Password verifier, rate limit và enumeration control được kiểm tra.
- [ ] MFA/step-up gắn với principal, session và action.
- [ ] Passkey/WebAuthn xác minh challenge, origin, RP ID và signature.
- [ ] Certificate/mTLS có trust chain, identity mapping và revocation.
- [ ] OIDC xác minh state, nonce, PKCE, issuer, audience và redirect URI.
- [ ] Identity linking dựa trên issuer + subject và proof phù hợp.
- [ ] Token có audience, scope, lifetime và validation đầy đủ.
- [ ] Session rotate, timeout, logout và revocation hoạt động.
- [ ] Recovery token one-time, expiry và notification phù hợp.
- [ ] Authorization kiểm tra tenant, resource và business invariant.
- [ ] Replay, clock skew, concurrency và retry được kiểm thử.
- [ ] Logging, metrics, trace và error message không lộ secret.
- [ ] Dashboard, alert, incident containment và recovery có owner.
- [ ] Test data tách biệt, secret test được quản lý và cleanup.
- [ ] Evidence gắn đúng build/configuration.
- [ ] Findings, residual risk và exception có owner/deadline.
- [ ] Sign-off có thẩm quyền, scope và trigger review lại.

## Ghi nhớ

Một hồ sơ authentication hoàn chỉnh phải nối liền danh tính, credential, factor, token, session, federation, identity linking, recovery, authorization và vận hành. Mỗi luồng cần xác định principal, trust source, trạng thái, audience/scope, thời hạn, failure path và cách thu hồi.

Hãy dùng threat model để chọn control, test để chứng minh hành vi, monitoring để phát hiện sai lệch và incident response để giới hạn thiệt hại. Chỉ sign-off khi evidence gắn đúng phiên bản, residual risk có owner và mọi đường truy cập quan trọng đều có cách xác minh, thu hồi và khôi phục.
