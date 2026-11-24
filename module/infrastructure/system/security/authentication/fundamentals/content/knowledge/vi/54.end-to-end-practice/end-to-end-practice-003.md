# Chọn credential phù hợp — Bài thực hành ra quyết định cho hệ thống xác thực

## Bối cảnh bài thực hành

Bạn là thành viên nhóm thiết kế IAM cho một nền tảng SaaS tên An Tâm Cloud. Nền tảng phục vụ doanh nghiệp vừa và lớn, lưu dữ liệu khách hàng, hợp đồng và đơn hàng; hỗ trợ thanh toán, quản trị tenant, tích hợp đối tác và các workload chạy trên cloud. Hệ thống hiện dùng password cho người dùng, một số tài khoản có TOTP, service account dùng API key dài hạn và pipeline CI/CD giữ client secret trong biến môi trường.

Sau một đợt credential stuffing, nhóm phát hiện một số password bị dùng lại từ nguồn rò rỉ khác. Một nhân viên cũng bị lừa nhập OTP vào trang phishing. Trong đợt rà soát tiếp theo, nhóm phát hiện API key dùng chung giữa nhiều worker và một certificate client không có owner rõ ràng. Ban lãnh đạo yêu cầu thiết kế lại credential policy, nhưng không muốn áp dụng cùng một phương thức cho mọi chủ thể.

Nhiệm vụ của bạn là **chọn credential phù hợp theo chủ thể, tài sản, hành động và threat model**, rồi mô tả cách credential được đăng ký, sử dụng, thay thế, thu hồi và kiểm chứng. Kết quả phải giải thích vì sao một credential phù hợp trong một ngữ cảnh, những rủi ro còn lại và các control cần đi kèm.

Đây là bài thực hành tổng hợp của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Học phần bao quát credential, password, MFA, passkey, certificate, token, session, identity federation và account recovery; mục tiêu là biết mô hình hóa trust boundary, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn. Các tổ chức, số liệu, role và tình huống trong bài là giả định để luyện ra quyết định.

## 1. Mục tiêu và sản phẩm cần nộp

Sau bài thực hành, bạn có thể:

- Phân loại principal: human user, privileged user, external partner, service workload và CI/CD workload.
- Phân loại tài sản, hành động và hậu quả nếu credential bị compromise.
- Xây dựng threat model cho credential theft, phishing, replay, brute force, recovery abuse và key compromise.
- So sánh password, TOTP, push MFA, passkey/security key, client certificate, API key, managed identity và workload federation.
- Chọn credential theo assurance, phishing resistance, replay resistance, key protection, usability và operational cost.
- Thiết kế credential lifecycle từ issuance/enrollment tới rotation, revocation, recovery và decommission.
- Phân biệt authentication với authorization; xác định audience, scope, session và delegation.
- Viết test case chứng minh credential sai hoặc bị thu hồi bị từ chối.

**Sản phẩm cần nộp** là một credential decision record gồm:

1. Bảng phân loại chủ thể và hành động.
2. Threat model và trust boundary.
3. Ma trận lựa chọn credential kèm lý do.
4. Luồng enrollment/login hoặc service authentication.
5. Quy tắc session/token và authorization.
6. Kế hoạch recovery, rotation và revocation.
7. Test plan và bằng chứng chấp nhận.
8. Danh sách giả định, ngoại lệ và rủi ro còn lại.

## 2. Hồ sơ hệ thống An Tâm Cloud

### 2.1. Thành phần

| Thành phần | Chức năng | Dữ liệu/quyền |
| --- | --- | --- |
| Customer Portal | Người dùng doanh nghiệp quản lý đơn hàng | Dữ liệu thuộc tenant |
| Tenant Admin Console | Quản lý user, role và tích hợp | Quyền quản trị trong tenant |
| Platform Operations | Nhân viên An Tâm Cloud vận hành nền tảng | Có thể ảnh hưởng nhiều tenant |
| Partner API | Đối tác gửi/nhận trạng thái đơn hàng | API theo hợp đồng và scope |
| Order Service | Xử lý đơn hàng | Quyền đọc/ghi đơn hàng |
| Payment Service | Tạo payment intent và trạng thái thanh toán | Thao tác tài chính nhạy cảm |
| Reporting Worker | Tạo báo cáo bất đồng bộ | Đọc dữ liệu được cấp theo task |
| CI/CD Pipeline | Build và deploy workload | Có thể thay đổi production |

### 2.2. Chủ thể

| Principal | Trust context | Điều cần bảo vệ |
| --- | --- | --- |
| Customer user | Browser/mobile, mạng không tin cậy | Tài khoản và dữ liệu tenant |
| Tenant admin | Browser và quyền quản trị tenant | Role, user lifecycle, integration |
| Platform operator | Thiết bị nhân viên, privileged workstation | Toàn nền tảng và nhiều tenant |
| External partner client | Hệ thống ngoài tổ chức | API contract và dữ liệu được chia sẻ |
| Order/Payment workload | Runtime cloud nội bộ | Gọi đúng service và đúng scope |
| Reporting worker | Job runner/queue | Chỉ xử lý task đã được authorize |
| CI/CD workload | Pipeline và build environment | Deploy đúng repo, branch, environment |

### 2.3. Tài sản và mức tác động

| Tài sản | Tác động nếu bị chiếm | Mức ưu tiên tham khảo |
| --- | --- | --- |
| Customer account | Lộ hoặc sửa dữ liệu trong tenant | Cao |
| Tenant admin account | Thêm user, đổi role, cấu hình integration | Rất cao |
| Platform operator account | Ảnh hưởng nhiều tenant và control plane | Critical |
| Partner API credential | Truy cập API theo hợp đồng | Cao, tùy scope |
| Payment workload identity | Tạo hoặc thay đổi payment intent | Critical |
| Reporting worker identity | Đọc/xuất dữ liệu qua nhiều tenant nếu cấu hình sai | Cao |
| CI/CD deploy identity | Thay đổi artifact hoặc production workload | Critical |

Mức ưu tiên chỉ là đánh giá ban đầu. Nhóm phải xác định owner, blast radius, data classification và hành động cụ thể trước khi chốt policy.

## 3. Bước 1 — Phân tích threat model

Trước khi chọn công nghệ, hãy trả lời các câu hỏi:

- Attacker có thể lấy password từ breach, phishing hoặc malware không?
- Attacker có thể relay OTP hoặc lừa người dùng approve push không?
- Private key có thể bị export, copy từ image hoặc lấy từ CI log không?
- Token có thể bị replay, dùng sai audience hoặc lưu trong queue không?
- Recovery email/phone có thể bị chiếm hoặc support bị social engineer không?
- Nhiều service có dùng chung một API key không?
- Credential có được cấp bởi issuer/CA đáng tin và đúng environment không?
- Có validator nào không nhận được revoke event hoặc dùng cache cũ không?

### 3.1. Threat register

| Threat | Principal/tài sản | Tín hiệu | Control cần cân nhắc |
| --- | --- | --- | --- |
| Credential stuffing | Customer user | Login failure từ nhiều nguồn, password reuse | MFA/passkey, breached password checks, rate limit |
| Phishing/OTP relay | Customer user, tenant admin | Login context bất thường, MFA challenge sequence | Passkey/security key, origin binding, step-up |
| MFA fatigue | User/admin | Nhiều push deny/timeout rồi approval | Number matching, challenge limit, alert |
| Session theft | User/operator | Session reuse từ context khác | Secure cookie, session revoke, short lifetime, device/risk checks |
| API key leakage | Partner/workload | Key xuất hiện trong repo/log hoặc request bất thường | Per-client key, secret manager, scope, rotation |
| Certificate compromise | Workload | Certificate/private key bị copy hoặc dùng từ runtime lạ | mTLS, short-lived cert, attestation, revocation |
| Token replay | User/workload | Reuse nonce, refresh token hoặc proof | One-time consume, token family, sender constraint |
| Recovery abuse | User/admin | Recovery method đổi ngay sau login rủi ro | Step-up, proofing, hold, notification |
| CI/CD trust abuse | Pipeline | Token phát hành từ branch/repo không mong đợi | Workload federation với subject/environment constraints |

### 3.2. Trust boundary

~~~mermaid
flowchart TD
    H[Human user / admin] -->|Password, passkey, MFA| IDP[Identity provider]
    P[Partner system] -->|Client credential| EDGE[API gateway]
    CI[CI/CD runner] -->|Federated workload proof| WIA[Workload identity authority]
    IDP -->|Session / access token| PORTAL[Customer and admin APIs]
    WIA -->|Short-lived workload credential| OS[Order service]
    WIA -->|Short-lived workload credential| PS[Payment service]
    EDGE --> PARTNER[Partner API]
    PORTAL --> AUTHZ[Authorization policy]
    OS --> AUTHZ
    PS --> AUTHZ
    AUTHZ --> DATA[(Tenant and payment data)]
    IDP --> AUDIT[Audit / monitoring]
    WIA --> AUDIT
    EDGE --> AUDIT
~~~

Browser, partner network, CI runner và message queue không tự động là trusted. Mỗi boundary cần xác thực caller, kiểm tra context và authorization riêng. Credential của human không dùng thay workload identity; mTLS của workload cũng không chứng minh user cuối có quyền thực hiện giao dịch.

## 4. Bước 2 — Xác định tiêu chí lựa chọn

Không chọn credential chỉ vì quen thuộc hoặc dễ tích hợp. Chấm từng phương án theo tiêu chí:

| Tiêu chí | Câu hỏi cần trả lời |
| --- | --- |
| Assurance | Credential có đáp ứng mức tin cậy cần cho principal/action không? |
| Phishing resistance | Proof có bị chuyển tiếp từ domain giả mạo không? |
| Replay resistance | Proof/challenge cũ có thể dùng lại không? |
| Key protection | Private/shared secret lưu ở đâu, có export/copy được không? |
| Binding | Credential gắn với origin, RP ID, audience, workload hoặc transaction nào? |
| Lifecycle | Enrollment, rotation, recovery và revocation có khả thi không? |
| Availability | Có phụ thuộc thiết bị, mạng, IdP hoặc nhà cung cấp duy nhất không? |
| Usability/accessibility | Người dùng có thể sử dụng và khôi phục an toàn không? |
| Scalability | Có thể quản lý ở quy mô user, service và tenant không? |
| Auditability | Có thể chứng minh ai dùng credential nào, khi nào và theo policy nào không? |
| Blast radius | Nếu credential bị lộ, phạm vi ảnh hưởng lớn đến đâu? |
| Operational cost | Đội ngũ có vận hành PKI, device fleet, key rotation và incident response được không? |

### 4.1. Ma trận so sánh credential

| Credential/phương thức | Phù hợp thường gặp | Điểm mạnh | Giới hạn/rủi ro |
| --- | --- | --- | --- |
| Password | Human login, tương thích rộng | Dễ triển khai, dễ thay | Phishing, reuse, stuffing, cần KDF và rate limit |
| TOTP | MFA chuyển tiếp hoặc môi trường chưa hỗ trợ passkey | Offline, phổ biến | OTP có thể bị phishing/relay; seed cần bảo vệ |
| Push MFA | User login nếu có number matching và context | UX thuận tiện | Fatigue, thiết bị/push channel bị chiếm |
| Passkey/WebAuthn | Human login, admin và thao tác rủi ro cao | Origin binding, chống phishing tốt | Enrollment/recovery và đồng bộ thiết bị cần policy |
| Hardware security key | Admin/operator và user rủi ro cao | Private key được bảo vệ trong thiết bị | Cần quản lý mất thiết bị và spare key |
| Client certificate/mTLS | Partner và service-to-service | Xác thực mật mã, có thể mutual | PKI, key custody, rotation/revocation |
| API key | Tích hợp legacy hoặc partner có giới hạn | Đơn giản, dễ phân quyền theo client | Bearer secret dài hạn, dễ lộ/copy |
| Managed identity | Workload trong cloud hỗ trợ | Giảm secret tĩnh, cấp credential ngắn hạn | Gắn với cloud trust/config và quyền runtime |
| Workload federation/OIDC | CI/CD và workload ngoài cloud | Credential ngắn hạn, không cần secret dài hạn | Trust condition phải giới hạn repo/branch/environment |

### 4.2. Không cộng điểm máy móc

Một bảng điểm giúp so sánh nhưng không thay thế threat model. Ví dụ, API key có thể chấp nhận cho một webhook partner chỉ có quyền ghi trạng thái trong một tenant, nhưng không phù hợp cho Payment Service có quyền tài chính rộng. Passkey có thể rất phù hợp cho admin, nhưng không phải credential tương tác dành cho một worker không có người dùng. Hãy nêu điều kiện và giới hạn thay vì tuyên bố một phương thức luôn tốt nhất.

## 5. Bước 3 — Chọn credential cho từng principal

### 5.1. Customer user

**Lựa chọn đề xuất:** passkey làm phương thức ưu tiên; TOTP được giữ như phương án MFA chuyển tiếp hoặc fallback có kiểm soát; password chỉ được duy trì nếu cần tương thích và phải đi cùng bảo vệ chống stuffing.

Lý do:

- Browser/mobile là môi trường không tin cậy và có nguy cơ phishing.
- Passkey ràng buộc proof với origin/RP ID, giảm nguy cơ credential bị nhập vào domain giả.
- TOTP tăng bảo vệ so với password-only nhưng vẫn có thể bị relay.
- Recovery phải được thiết kế đủ mạnh để không biến email đơn thuần thành đường vòng.

Control đi kèm:

- Enrollment passkey sau khi xác minh session hiện tại và step-up phù hợp.
- Challenge ngẫu nhiên, one-time, có expiry và kiểm tra origin/RP ID.
- Password KDF, breached-password screening và rate limit nếu vẫn hỗ trợ password.
- Session idle/absolute lifetime, revoke và step-up cho export/thao tác nhạy cảm.
- Thông báo khi authenticator hoặc recovery method thay đổi.

### 5.2. Tenant admin

**Lựa chọn đề xuất:** passkey hoặc hardware security key chống phishing là bắt buộc theo policy; TOTP chỉ là fallback có điều kiện, giới hạn quyền và thời hạn.

Lý do:

- Admin có thể thay đổi role, mời user và cấu hình integration.
- Một tài khoản admin bị chiếm có thể mở rộng ảnh hưởng trong tenant.
- Phishing resistance có giá trị cao hơn tiện lợi của OTP.

Control đi kèm:

- Re-authentication trước add/remove authenticator và thay đổi role.
- Session freshness ngắn hơn user thường cho hành động quản trị.
- Audit mọi role assignment, recovery override và policy change.
- Không cho phép admin tự miễn MFA cho chính mình mà không có approval.

### 5.3. Platform operator

**Lựa chọn đề xuất:** hardware-backed passkey/security key, privileged access workflow và tài khoản quản trị tách biệt.

Lý do:

- Operator có thể ảnh hưởng nhiều tenant và control plane.
- Password/TOTP fallback có thể làm giảm assurance của toàn bộ flow.
- Cần tách tài khoản công việc thường khỏi tài khoản có quyền cao.

Control đi kèm:

- Phishing-resistant MFA bắt buộc.
- Just-in-time elevation, approval và thời hạn quyền ngắn.
- Managed workstation/device posture theo risk policy.
- Break-glass account riêng, giám sát và rotation sau sử dụng.
- Session recording/audit cho thao tác đặc quyền theo chính sách.

### 5.4. External partner client

**Lựa chọn đề xuất:** ưu tiên mTLS client certificate hoặc OAuth client authentication với private key; API key chỉ dùng khi đối tác chưa hỗ trợ phương thức mạnh hơn và scope được giới hạn.

Lý do:

- Không có human interaction ở mỗi request.
- Partner cần xác thực hệ thống gọi API.
- Credential phải có owner, expiry, rotation và audit.

Control đi kèm:

- Credential riêng theo partner/environment, không dùng chung.
- Audience/resource và scope theo API operation.
- Rate limit, request signing hoặc sender constraint khi threat model yêu cầu.
- Certificate/key rotation có overlap ngắn, deadline và verification.
- Revoke partner credential khi hợp đồng hoặc quyền truy cập kết thúc.

### 5.5. Order và Payment workload

**Lựa chọn đề xuất:** cloud managed identity hoặc workload federation cấp token ngắn hạn; mTLS/workload certificate cho xác thực service-to-service theo kiến trúc.

Lý do:

- Workload không phải human user và không nên dùng password/MFA tương tác.
- Secret tĩnh trong environment dễ bị copy từ runtime, log hoặc image.
- Identity ngắn hạn giảm cửa sổ lạm dụng và giúp audit theo workload.

Control đi kèm:

- Mỗi service có workload identity riêng.
- Payment chỉ nhận token có audience Payment API và scope cần thiết.
- Order xác thực workload caller bằng mTLS/identity assertion.
- Authorization kiểm tra user subject nếu request thực hiện thay mặt user.
- Không dùng quyền của Order Service để bỏ qua quyền của user; chống confused deputy.

### 5.6. Reporting worker

**Lựa chọn đề xuất:** workload identity riêng cộng task authorization/reference. Không lưu bearer token người dùng dài hạn trong queue.

Lý do:

- Job có thể chạy sau khi user session hết hạn.
- Message có thể retry hoặc replay.
- Worker cần chứng minh workload identity và kiểm tra task đã được authorize.

Control đi kèm:

- Message envelope chỉ mang subject reference, tenant, purpose và authorization reference.
- Consumer xác thực producer/broker và worker identity.
- Quy định rõ authorize-at-enqueue hay authorize-at-consume.
- Idempotency và one-time task capability nếu cần.

### 5.7. CI/CD workload

**Lựa chọn đề xuất:** OIDC workload federation với trust condition ràng buộc repository, workflow, branch/tag và environment; không giữ cloud client secret dài hạn trong pipeline.

Lý do:

- CI runner có thể ephemeral và nằm ngoài cloud runtime.
- Identity provider có thể phát credential ngắn hạn dựa trên assertion từ pipeline.
- Trust condition giới hạn pipeline nào được deploy production.

Control đi kèm:

- Subject/audience allowlist cụ thể.
- Approval cho production environment.
- Không tin branch hoặc repository do workflow input tự khai.
- Audit artifact digest, workflow run và principal đã phát hành token.
- Revoke federation trust khi repo/runner bị compromise.

## 6. Bước 4 — Quyết định theo use case, không chỉ theo principal

Cùng một user có thể cần assurance khác nhau cho từng hành động:

| Hành động | Credential/session yêu cầu | Vì sao |
| --- | --- | --- |
| Đăng nhập và xem dashboard | Passkey hoặc password + MFA theo policy | Xác minh account với mức rủi ro cơ bản |
| Xem dữ liệu tenant | Session hợp lệ và authorization tenant-aware | Ngăn truy cập chéo tenant |
| Export dữ liệu lớn | Step-up gần thời điểm export | Giảm nguy cơ session cũ bị lạm dụng |
| Thêm passkey mới | Re-authentication mạnh | Ngăn attacker gắn credential của họ |
| Đổi email recovery | Step-up, notification và hold theo risk | Ngăn chiếm đường recovery |
| Thêm người thụ hưởng | Step-up và transaction confirmation | Gắn proof với thay đổi tài chính |
| Thay role admin | Phishing-resistant re-authentication và approval | Tác động quyền lớn |
| Order gọi Payment | Workload identity + token audience/scope riêng | Xác thực caller và giới hạn quyền downstream |
| CI deploy production | Federated workload credential + environment approval | Ràng buộc identity với pipeline được phép |

Một credential mạnh không tự cấp authorization. Payment Service vẫn cần kiểm tra subject, actor, tenant, order ownership và scope. Passkey xác minh người dùng; policy quyết định người dùng có quyền thanh toán đơn hàng đó hay không.

## 7. Bước 5 — Thiết kế credential lifecycle

Credential phù hợp phải có lifecycle có thể vận hành:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> ISSUED: policy và identity proof hợp lệ
    ISSUED --> ACTIVE: enrollment/verification hoàn tất
    ACTIVE --> ROTATION_PENDING: sắp hết hạn hoặc thay key
    ROTATION_PENDING --> ACTIVE: credential mới được xác minh
    ACTIVE --> SUSPENDED: nghi compromise hoặc risk
    SUSPENDED --> REVOKED: xác nhận cần thu hồi
    ACTIVE --> REVOKED: hết quyền / incident / offboarding
    REVOKED --> [*]
~~~

### 7.1. Enrollment/issuance

- Xác minh principal và quyền yêu cầu credential.
- Chọn issuer/authority tin cậy.
- Ràng buộc credential với subject, purpose, audience hoặc workload.
- Lưu metadata/reference an toàn; private/shared secret được bảo vệ.
- Xác minh proof-of-possession trước khi đánh dấu active.
- Ghi audit về actor, policy version và credential reference.

### 7.2. Rotation/replacement

- Tạo key/credential mới bằng entropy và thuật toán phù hợp.
- Phát hành qua authority được kiểm soát.
- Cập nhật consumer theo rollout.
- Giới hạn thời gian overlap.
- Theo dõi request dùng credential cũ.
- Revoke credential cũ và xác minh validator từ chối.

### 7.3. Revocation

Revoke phải được lan tới mọi điểm chấp nhận credential: IdP, gateway, API, service mesh, cache và downstream. Với JWT tự xác minh, issuer đánh dấu revoked không tự làm chữ ký mất hiệu lực; cần TTL ngắn, introspection, denylist, session epoch hoặc cơ chế khác theo SLA.

### 7.4. Recovery

Recovery không được yếu hơn login hoặc enrollment. Hãy xác định proof độc lập, support approval, delay, notification, session revoke và giới hạn quyền recovery session. Không dùng email/phone đang nghi bị chiếm làm bằng chứng duy nhất.

### 7.5. Decommission

Khi user nghỉ việc, partner hết hợp đồng hoặc workload bị xóa:

- Revoke credential, token family, certificate và delegated grant.
- Xóa role binding và federation trust không còn cần.
- Kiểm tra bản sao trong CI, secret manager, image, backup và config.
- Giữ audit tombstone theo retention policy.
- Xác minh không còn request được chấp nhận từ credential cũ.

## 8. Bước 6 — Thiết kế session, token và delegation

Human authentication và workload authentication thường dẫn tới token/session khác nhau:

| Luồng | Credential đầu vào | Kết quả | Ràng buộc |
| --- | --- | --- | --- |
| Human login | Passkey hoặc password + MFA | Browser session/access token | Principal, tenant, auth time, assurance |
| Admin action | Session + step-up proof | Session context được nâng assurance có thời hạn | Action, freshness, policy version |
| Partner API | Client certificate/private key | Client access token hoặc mTLS-authenticated request | Client, audience, scope |
| Service-to-service | Workload identity | Token ngắn hạn hoặc mTLS identity | Workload subject, audience, scope |
| User-delegated call | User context + workload actor | Token exchange/OBO result | Subject, actor, audience, scope |
| Async job | Authorized task reference + worker identity | Task-scoped execution | Purpose, tenant, idempotency |

### 8.1. Audience và scope

Token dành cho Order API không tự động được Payment API chấp nhận. Nếu Order cần gọi Payment, dùng token exchange hoặc flow delegation được issuer hỗ trợ để lấy token audience Payment với scope tối thiểu. Payment phải xác minh issuer, audience, expiry, scope, subject/actor và tenant.

### 8.2. Không truyền bearer token qua mọi hop

Không forward token chỉ vì nó có sẵn. Không đặt token trong URL, log hoặc message queue. Cache token phải phân biệt issuer, subject, actor, audience, scope và tenant. Refresh token không được chia sẻ giữa các service như một secret chung.

### 8.3. Authorization vẫn là bước riêng

Authentication chứng minh principal kiểm soát credential. Authorization kiểm tra quyền đối với resource/action. Không tin role hoặc tenant do client tự gửi; lấy từ policy/data đã xác minh và kiểm tra tại resource server.

## 9. Bước 7 — Ma trận quyết định tổng hợp

Ma trận dưới đây là đề xuất cho An Tâm Cloud. Khi hoàn thành bài, hãy sửa các ô nếu threat model hoặc constraint của tổ chức giả định khác.

| Principal | Credential chính | Dự phòng/fallback | Token/session | Control bắt buộc |
| --- | --- | --- | --- | --- |
| Customer user | Passkey | TOTP hoặc password + MFA theo policy | Session có idle/absolute lifetime | Recovery an toàn, rate limit, tenant authorization |
| Tenant admin | Passkey/security key chống phishing | Fallback giới hạn, có approval | Session freshness ngắn cho admin action | Step-up, audit, notification |
| Platform operator | Hardware-backed security key/passkey | Break-glass được kiểm soát | Privileged session/JIT | PAM, approval, device posture, audit |
| Partner client | mTLS certificate/private key | API key per-client nếu tạm thời cần | Client token audience/scope hẹp | Rotation, owner, rate limit, revoke |
| Order workload | Managed identity/workload federation | Không dùng shared static secret | Short-lived token cho Order API | Workload identity riêng, mTLS nếu cần |
| Payment workload | Managed identity/workload federation | Emergency credential có thời hạn | Token audience Payment API | Scope tối thiểu, subject/actor check |
| Reporting worker | Workload identity + task reference | Task capability giới hạn | Task-scoped execution | Queue ACL, idempotency, tenant isolation |
| CI/CD workload | OIDC federation | Emergency deploy path có dual control | Short-lived deployment token | Repo/branch/environment binding, approval |

### 9.1. Quy tắc loại bỏ

Loại phương án nếu:

- Không chứng minh được principal hoặc workload nào sở hữu credential.
- Secret không có nơi lưu và rotation được kiểm soát.
- Credential không thể revoke trong thời gian yêu cầu.
- Token không giới hạn audience/scope khi đi qua nhiều resource.
- Recovery yếu hơn mức assurance cần đạt.
- Phương thức không chống được threat bắt buộc trong policy.
- Không thể thu thập bằng chứng mà không lưu secret.

## 10. Bước 8 — Ví dụ ra quyết định chi tiết

### Tình huống A: user chỉ có password

**Bối cảnh:** Customer user cần đăng nhập từ browser cá nhân; password có thể bị reuse.

**Quyết định:** Yêu cầu MFA; khuyến nghị passkey, giữ TOTP trong giai đoạn chuyển đổi. Nếu vẫn hỗ trợ password-only do constraint, giới hạn quyền và yêu cầu enrollment trước khi truy cập dữ liệu nhạy cảm.

**Rủi ro còn lại:** TOTP phishing/relay, recovery abuse, malware lấy session cookie.

**Bằng chứng:** MFA policy, enrollment report, test password-only không tạo full session, audit và alert.

### Tình huống B: tenant admin đổi role

**Bối cảnh:** Admin có session từ sáng và muốn cấp quyền quản trị cho nhân viên mới.

**Quyết định:** Re-authentication phishing-resistant trong freshness window, kiểm tra quyền hiện tại, approval nếu policy yêu cầu và audit.

**Rủi ro còn lại:** Endpoint role assignment có thể bị gọi trực tiếp hoặc tenant context bị giả mạo.

**Bằng chứng:** API test sai audience/tenant, step-up expiry test, audit actor/resource và authorization denial.

### Tình huống C: partner webhook

**Bối cảnh:** Đối tác gửi trạng thái đơn hàng theo hợp đồng.

**Quyết định:** mTLS client certificate hoặc signed request theo profile; credential riêng cho partner và environment. API key chỉ là phương án chuyển tiếp có scope hẹp.

**Rủi ro còn lại:** Private key bị copy, partner bị compromise, certificate revocation cache trễ.

**Bằng chứng:** Certificate inventory, SAN/issuer validation, rotation drill, revoked cert negative test và request audit.

### Tình huống D: Payment Service gọi từ Order Service

**Bối cảnh:** Order Service tạo payment intent thay mặt user.

**Quyết định:** Xác thực workload Order bằng managed identity/mTLS; dùng token exchange/OBO cho user delegation nếu Payment cần quyền user. Token có audience Payment API và scope payment intent tối thiểu.

**Rủi ro còn lại:** Confused deputy nếu Payment chỉ tin role của Order mà bỏ qua user authorization.

**Bằng chứng:** Wrong audience test, actor/subject audit, tenant isolation, scope downscoping và workload identity verification.

### Tình huống E: CI/CD deploy production

**Bối cảnh:** Pipeline build và deploy từ repository.

**Quyết định:** OIDC federation với subject/audience condition ràng buộc repo, workflow, branch/tag và protected environment. Không lưu client secret dài hạn.

**Rủi ro còn lại:** Pipeline hoặc dependency bị compromise, approval bị bypass, trust condition quá rộng.

**Bằng chứng:** Token exchange từ branch không được phép bị từ chối; production environment yêu cầu approval; audit gắn workflow run và artifact digest.

## 11. Bước 9 — Test plan chứng minh credential được chọn đúng

Một quyết định credential chỉ hoàn chỉnh khi có test. Hãy kiểm tra cả positive, negative, lifecycle và abuse.

| Nhóm | Test | Kết quả mong đợi |
| --- | --- | --- |
| Password | Sai password, unknown user, verifier hỏng | Không tạo full session; public error không enumerate |
| MFA | OTP sai, hết hạn, replay | Từ chối; challenge consume tối đa một lần |
| Passkey | Origin/RP ID/challenge/signature sai | Assertion bị từ chối |
| Enrollment | Thêm authenticator khi session cũ/weak | Yêu cầu re-authentication theo policy |
| Recovery | Mất mọi factor, email nghi compromise | Không dùng email đó làm proof duy nhất |
| Session | Session revoked hoặc quá freshness | Protected action bị từ chối/step-up |
| Token | Sai issuer/audience/scope/expiry | Resource server từ chối |
| Delegation | Workload hợp lệ nhưng user thiếu quyền | Payment authorization từ chối |
| Certificate | Expired/revoked/wrong SAN | mTLS/client authentication thất bại |
| API key | Key cũ sau rotation | Key cũ bị từ chối sau deadline |
| Workload | CI branch không allowlist | Không cấp deployment token |
| Async | Message replay hoặc consumer retry | Idempotency ngăn side effect lặp |
| Revocation | Validator cache stale | Propagation test phát hiện; không đánh dấu complete trước SLA |
| Privacy | Log/trace chứa secret marker | Redaction test phải pass |
| Resilience | IdP/KMS/replay store timeout | Không fail-open ngoài policy |

### 11.1. Test oracle

Không chỉ kiểm tra HTTP 401/403. Với request bị từ chối, xác minh:

- Không tạo session/access token/refresh token hoặc grant.
- Không thay đổi authenticator/recovery mapping.
- Không gọi downstream operation trái phép.
- Không có cross-tenant data access.
- Audit ghi reason category và correlation reference.
- Không có password, OTP, token, cookie hoặc private key trong log.

### 11.2. Kiểm thử rotation/revocation

1. Phát hành credential test.
2. Dùng credential để gọi resource hợp lệ.
3. Revoke credential tại authority.
4. Đợi propagation theo SLA đã định.
5. Thử lại tại từng gateway/resource server/worker.
6. Xác minh mọi validator từ chối credential cũ.
7. Kiểm tra credential mới hoạt động đúng scope.

## 12. Kế hoạch rollout và vận hành

### Giai đoạn 1: inventory và policy

- Lập inventory human, partner, service và CI/CD principal.
- Gắn owner, purpose, scope, expiry và nơi lưu credential.
- Phân loại action theo rủi ro.
- Chọn authenticator profile và định nghĩa fallback.
- Xác định session/revocation SLA và audit evidence.

### Giai đoạn 2: pilot

- Pilot passkey với nhóm customer user và admin tự nguyện.
- Enforce phishing-resistant MFA cho operator.
- Chuyển một partner sang mTLS.
- Chuyển một workload và một CI pipeline sang short-lived identity.
- Chạy negative tests, recovery drill và revoke drill.

### Giai đoạn 3: enforce và migrate

- Bắt buộc policy theo tenant/role/action.
- Loại bỏ shared API key và secret dài hạn theo lịch.
- Thu hẹp fallback, ghi exception có expiry.
- Theo dõi enrollment, login success, recovery volume và support load.

### Giai đoạn 4: review liên tục

- Review credential owner và scope định kỳ.
- Kiểm tra certificate/key expiry và rotation.
- Đo revocation propagation.
- Diễn tập account takeover, token theft và workload compromise.
- Review alert false positive/false negative.
- Cập nhật policy theo incident, threat model và yêu cầu mới.

## 13. Credential decision record — Mẫu điền

Sử dụng mẫu sau để ghi quyết định cho từng principal/action:

~~~yaml
decision_id: AUTH-CRED-EXAMPLE
principal_type: tenant_admin
action: change_role
asset: tenant_access_control
threats:
  - phishing
  - session_theft
  - privilege_escalation
primary_credential: phishing_resistant_passkey
fallback:
  method: controlled_recovery
  allowed: true
  restrictions:
    - require_independent_proof
    - notify_existing_contact
    - temporary_action_hold
session:
  max_authentication_age: policy_defined
  require_step_up: true
authorization:
  tenant_binding: required
  resource_scope: tenant_role_management
lifecycle:
  owner: IAM_team
  rotation_or_replacement: on_compromise_or_policy
  revocation_sla: defined_by_risk
evidence:
  - enrollment_inventory
  - authentication_audit
  - negative_test_report
  - revocation_verification
exceptions:
  allowed: false
  approval: none
~~~

Đây là cấu trúc minh họa, không phải schema cấu hình để nạp trực tiếp vào hệ thống. Giá trị như policy_defined hoặc defined_by_risk phải được thay bằng thông số đã phê duyệt trước triển khai.

## 14. Các quyết định sai thường gặp

| Quyết định sai | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chọn một credential cho mọi principal | Không phù hợp human, admin, partner và workload | Chọn theo principal/action/threat |
| Coi TOTP là phishing-resistant | Đánh giá assurance quá cao | Ghi rõ OTP có thể bị relay |
| Dùng API key dài hạn cho mọi service | Secret bị copy, blast radius lớn | Per-workload identity và token ngắn hạn |
| Chỉ đổi password sau incident | Session/token cũ có thể còn hiệu lực | Revoke session/token/factor liên quan |
| Recovery chỉ cần email | Attacker chiếm email có thể bypass MFA | Proofing độc lập và controlled recovery |
| Token dùng chung mọi audience | Confused deputy và token substitution | Token exchange, audience/scope hẹp |
| Tin header user/role do client gửi | Identity spoofing và privilege escalation | Server-side verified context |
| Không có owner cho certificate/key | Credential orphaned không được rotate | Inventory, owner và expiry |
| Allowlist fallback vô thời hạn | Fallback trở thành đường yếu thường trực | Exception có scope, expiry và review |
| Đánh dấu revoke thành công ngay sau API 200 | Validator có thể vẫn accept credential cũ | Probe từng validator và đo propagation |

## 15. Rubric đánh giá kết quả

| Tiêu chí | Đạt | Cần bổ sung |
| --- | --- | --- |
| Principal và action | Phân biệt human, admin, partner, workload, CI/CD và hành động | Gộp mọi principal thành một nhóm |
| Threat model | Có phishing, replay, theft, recovery abuse và blast radius | Chỉ liệt kê password sai |
| Credential selection | Có lý do theo assurance, binding, lifecycle và vận hành | Chọn theo độ phổ biến hoặc tiện lợi |
| MFA/passkey | Phân biệt OTP với phishing-resistant authenticator | Gọi mọi MFA là chống phishing |
| Workload identity | Không dùng MFA tương tác/shared password cho service | Dùng chung API key dài hạn |
| Session/token | Có audience, scope, freshness, revoke và delegation | Chỉ mô tả login |
| Recovery | Không yếu hơn mức bảo đảm cần khôi phục | Chỉ gửi reset link qua email |
| Lifecycle | Có owner, expiry, rotation, revoke và decommission | Không có vòng đời |
| Testing | Kiểm tra response, state, side effect, replay và fail-closed | Chỉ kiểm tra status code |
| Evidence | Có audit, test report, inventory và revoke proof | Chỉ có screenshot cấu hình |
| Exceptions | Có owner, approval, expiry và compensating controls | Allowlist không thời hạn |

## 16. Bài tập tự kiểm tra

Hãy hoàn thiện quyết định cho các tình huống sau:

1. Một customer user chỉ có điện thoại cũ không hỗ trợ passkey; người dùng vẫn cần truy cập dữ liệu cá nhân.
2. Một tenant admin muốn dùng SMS OTP vì không muốn mang security key.
3. Một partner chỉ hỗ trợ API key nhưng cần ghi trạng thái đơn hàng.
4. Payment Service đang dùng API key chung với Order Service.
5. Reporting Worker nhận message có access token người dùng và xử lý sau vài giờ.
6. CI pipeline có client secret production được lưu trong biến môi trường.
7. Một certificate đã hết hợp đồng nhưng vẫn được API gateway chấp nhận.
8. Một user báo mất thiết bị sau khi phát hiện refresh token reuse.

Với mỗi tình huống, ghi:

- Principal, action, asset và threat.
- Credential được chọn hoặc bị từ chối.
- Assurance/phishing/replay property cần đạt.
- Enrollment/issuance và binding.
- Session/token/authorization context.
- Fallback/recovery và exception.
- Rotation/revocation/decommission.
- Test và evidence chứng minh quyết định.

**Gợi ý đánh giá:** một câu trả lời tốt không chỉ nêu tên credential. Nó phải giải thích credential phù hợp với principal/action nào, threat nào còn tồn tại, lifecycle vận hành ra sao và bằng chứng nào cho thấy hệ thống thực sự thực thi policy.

---

**Ghi nhớ:** chọn credential là quyết định dựa trên **chủ thể, hành động, tài sản, threat model và lifecycle**. Human user có thể cần passkey/MFA; privileged user cần phishing-resistant authentication và kiểm soát đặc quyền; partner cần credential riêng, có owner/scope/rotation; workload và CI/CD cần identity ngắn hạn, audience hẹp và trust condition rõ. Không có credential nào tự giải quyết authorization, recovery, session theft hoặc revocation. Quyết định chỉ hoàn chỉnh khi có threat rationale, fallback có kiểm soát, test negative và bằng chứng vận hành.
