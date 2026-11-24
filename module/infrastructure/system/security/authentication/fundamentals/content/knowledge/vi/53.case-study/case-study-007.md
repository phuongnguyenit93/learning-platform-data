# Hệ thống recovery — Case study thiết kế khôi phục tài khoản nhiều tenant
 
> **Chương:** Case study  
> **Chủ đề:** Hệ thống recovery

Bài nghiên cứu tình huống này xây dựng một hệ thống khôi phục tài khoản cho một nền tảng học tập nhiều tổ chức. Nền tảng có học viên, giảng viên, nhân viên hỗ trợ, quản trị viên tenant và quản trị viên nền tảng. Người dùng đăng nhập bằng passkey hoặc password kết hợp MFA; một số tổ chức dùng SSO. Họ có thể mất điện thoại, mất security key, đổi email, không còn truy cập IdP hoặc nghi ngờ tài khoản bị chiếm. Hệ thống cần giúp người dùng hợp lệ lấy lại quyền truy cập, đồng thời ngăn attacker biến recovery thành con đường bỏ qua authentication.

Recovery là một giao dịch bảo mật xuyên suốt nhiều thành phần: account directory, identity provider, recovery service, notification provider, credential registry, session/token service, tenant authorization, helpdesk và audit pipeline. Thành công không chỉ là đổi password hoặc thêm passkey. Hệ thống còn phải ràng buộc yêu cầu với đúng principal và purpose, xác minh đủ assurance, chống enumeration/replay/race, xử lý session cũ, thông báo đúng kênh và giữ bằng chứng có thể điều tra.

Tình huống dùng dữ liệu và tên tổ chức giả định để minh họa cách phân tích yêu cầu, chọn kiến trúc, thiết kế API/state machine, xử lý ngoại lệ và kiểm thử. Các ngưỡng, thời gian chờ và policy cụ thể phải được tổ chức hiệu chỉnh theo threat model, quy định áp dụng và mức nhạy cảm dữ liệu.

## 1. Bối cảnh hệ thống

Nền tảng **LearnSpace** cung cấp dịch vụ học tập cho nhiều trường học và doanh nghiệp. Mỗi tenant có người dùng và vai trò riêng. Một người có thể là học viên ở tenant A, giảng viên ở tenant B và support operator ở tenant C thông qua các account/role được quản lý riêng.

### 1.1. Các nhóm principal

| Nhóm | Ví dụ | Đặc điểm recovery |
| --- | --- | --- |
| Learner | Học viên | Tự phục vụ là chính; dữ liệu cá nhân và tiến độ học |
| Instructor | Giảng viên | Có thể truy cập điểm, bài nộp và dữ liệu lớp |
| Tenant administrator | Quản trị viên trường/tổ chức | Quyền cao trong một tenant; cần assurance mạnh |
| Platform administrator | Quản trị viên nền tảng | Blast radius lớn; phishing-resistant MFA và approval |
| Support operator | Nhân viên hỗ trợ | Recovery thay mặt user nhưng phải có case, purpose và scope |
| Workload identity | API service, worker | Credential máy; rotation qua control plane, không dùng human recovery |

### 1.2. Các phương thức authentication hiện có

- Passkey/WebAuthn là phương thức ưu tiên cho account có hỗ trợ.
- Một số account dùng password kết hợp MFA.
- Người dùng có thể đăng ký security key hoặc authenticator dự phòng.
- Recovery code được phát khi enrollment MFA nếu policy cho phép.
- Tenant có thể cấu hình OIDC hoặc SAML SSO.
- Workload dùng short-lived credential và mTLS.
- Session được quản lý tập trung; access token có audience theo resource server.

### 1.3. Vấn đề hiện tại

LearnSpace có nhiều luồng recovery được phát triển ở các thời điểm khác nhau. Password reset chỉ kiểm tra link email; MFA reset dựa vào support; passkey replacement dùng endpoint riêng; SSO account lại hướng người dùng sang IdP. Không có một transaction model thống nhất, vì vậy hệ thống khó biết recovery nào đang chờ, credential nào đã bị thay, session nào cần revoke và ai đã phê duyệt.

Một số điểm yếu giả định trong hệ thống cũ:

- Recovery link có thời hạn dài và chưa ràng buộc purpose rõ ràng;
- Public response khác nhau giữa account tồn tại và không tồn tại;
- Helpdesk có thể thay factor sau khi hỏi một vài thông tin cá nhân;
- Password reset không luôn thu hồi refresh token;
- Passkey mới có thể được thêm trong cùng flow với email OTP yếu;
- Tenant context lấy trực tiếp từ request;
- Notification và audit chạy bất đồng bộ nhưng chưa có reconciliation;
- Không có dashboard để phát hiện recovery abuse.

## 2. Mục tiêu và phạm vi

### 2.1. Mục tiêu chức năng

1. Người dùng có thể khởi tạo recovery bằng identifier được hỗ trợ.
2. Hệ thống resolve account nội bộ mà không tiết lộ account existence công khai.
3. Recovery method chỉ gồm credential/factor đã đăng ký và được policy cho phép.
4. Người dùng có thể chứng minh quyền kiểm soát bằng phương thức phù hợp.
5. High-risk recovery có approval hoặc cooldown.
6. Recovery transaction phát hành artifact gắn subject, purpose và expiry.
7. Artifact chỉ được tiêu thụ một lần.
8. Người dùng có thể thay password, thêm passkey hoặc khôi phục factor theo policy.
9. Credential/session/token cũ được revoke hoặc đánh dấu theo policy.
10. Notification và audit được tạo với trạng thái có thể theo dõi.

### 2.2. Mục tiêu bảo mật

- Ngăn account enumeration và recovery token replay;
- Ngăn đổi recovery channel bằng chính kênh chưa được xác minh;
- Ngăn helpdesk social engineering và insider misuse;
- Ngăn cross-tenant recovery và account linking sai;
- Không hạ assurance cho privileged account;
- Không để session attacker tiếp tục hoạt động sau recovery;
- Bảo vệ secret và dữ liệu cá nhân trong log, queue, ticket và analytics;
- Duy trì trạng thái nhất quán khi provider hoặc service gặp outage.

### 2.3. Ngoài phạm vi

Case study tập trung vào recovery cho danh tính người dùng và credential được quản lý bởi LearnSpace. Quy trình proofing giấy tờ định danh của từng quốc gia, xử lý tranh chấp pháp lý và chi tiết vận hành của từng IdP bên ngoài cần được tích hợp theo policy riêng. Workload credential được đề cập ở góc độ rotation/restore service identity, không dùng human recovery.

## 3. Yêu cầu phi chức năng và nguyên tắc thiết kế

| Thuộc tính | Yêu cầu thiết kế |
| --- | --- |
| Security | Mỗi bước có trust boundary, subject binding, purpose và authorization |
| Availability | Có retry/idempotency và degraded mode có giới hạn |
| Consistency | Consume token và đổi credential có state transition nguyên tử |
| Privacy | Public response chung; dữ liệu nhạy cảm được tối thiểu hóa |
| Accessibility | Hỗ trợ keyboard, screen reader, paste/autofill và ngôn ngữ rõ |
| Observability | Có event, correlation, alert và pipeline health |
| Auditability | Có actor, subject, tenant, purpose, approver và policy version |
| Operability | Có runbook, owner, SLA, rollback và reconciliation |
| Scalability | Rate limit và queue không phụ thuộc một nguồn đơn lẻ |
| Maintainability | Policy và state machine được version hóa |

### 3.1. Nguyên tắc kiến trúc

- Recovery là một transaction có state, không phải tập hợp endpoint độc lập.
- Identity proofing, authorization và credential change là các quyết định riêng.
- Không tin identifier, tenant hoặc recovery method do client tự khai.
- Không dùng email/SMS đơn lẻ để cấp lại assurance cao.
- Mọi action nhạy cảm có actor, subject, purpose và audit.
- Mọi side effect có idempotency hoặc reconciliation.
- Khi không thể xác minh đủ mức, hệ thống từ chối có kiểm soát.

## 4. Threat model và trust boundary

### 4.1. Tài sản cần bảo vệ

- Principal identity và account mapping;
- Password verifier, passkey public key và credential registry;
- MFA seed/verifier và recovery code verifier;
- Recovery transaction và token verifier;
- Session, refresh-token family và API credential;
- Tenant membership, role và resource ownership;
- Helpdesk approval và evidence;
- Notification destination;
- Audit event và incident evidence.

### 4.2. Attacker và năng lực

Attacker có thể biết email/username công khai, kiểm soát một mailbox hoặc số điện thoại, có session cũ, gọi API trực tiếp, thử nhiều recovery code, gửi request đồng thời, giả danh người dùng với helpdesk hoặc chiếm một tenant administrator. Attacker cũng có thể khai thác outage, queue retry, stale cache hoặc lỗi đồng bộ để giữ quyền sau recovery.

### 4.3. Trust boundary

~~~mermaid
flowchart TD
    U["User / browser / mobile"] -->|TLS| G["API gateway"]
    G --> R["Recovery service"]
    R --> D["Account directory"]
    R --> P["Policy and risk engine"]
    R --> C["Credential registry"]
    R --> N["Notification queue"]
    R --> A["Approval / helpdesk"]
    R --> S["Session and token service"]
    R --> T["Tenant authorization"]
    R --> L["Audit event pipeline"]
    N --> M["Email / SMS / push provider"]
    S --> RS["Gateway and resource servers"]
~~~

Client chỉ gửi yêu cầu và bằng chứng; server resolve principal, chọn policy và xác minh transaction. Recovery service không được tự tin dữ liệu identity header từ client. Notification provider chỉ là kênh truyền tin, không phải nguồn chứng minh account ownership. Helpdesk là actor có quyền giới hạn, không phải nguồn chân lý thay thế policy.

### 4.4. Threat-to-control mapping

| Threat | Kiểm soát chính |
| --- | --- |
| Account enumeration | Response contract chung, rate limit và timing analysis |
| Token theft | Entropy, verifier storage, TTL, no-referrer và redaction |
| Replay | One-time consume nguyên tử, purpose/subject binding |
| Helpdesk social engineering | RBAC, proofing, approval và separation of duties |
| Downgrade | Assurance policy theo account/action |
| Cross-tenant recovery | Principal binding, tenant authorization server-side |
| Session persistence | Refresh-token family revocation và propagation |
| Queue redelivery | Outbox, idempotency và consumer deduplication |
| Insider misuse | Case purpose, dual control, audit và periodic review |
| Provider outage | Fail-closed/degraded policy và reconciliation |

## 5. Recovery policy theo account class

Không phải mọi account đều cần cùng một proofing path.

| Account class | Proofing dự kiến | Recovery outcome |
| --- | --- | --- |
| Learner | Backup passkey/security key, recovery code hoặc proofing phù hợp | Reset credential và review session |
| Instructor | Phương thức đã đăng ký; có thể yêu cầu step-up cho dữ liệu nhạy cảm | Khôi phục có notification và revoke credential mất |
| Tenant admin | Phishing-resistant factor dự phòng hoặc approval độc lập | Session review; có thể cooldown |
| Platform admin | Phishing-resistant factor, dual control hoặc break-glass policy | Scope/TTL chặt, alert ngay và post-use review |
| Support operator | Quy trình nội bộ có xác minh nhân viên và manager approval | Không cho tự recovery bằng quyền support |
| Workload | Identity control plane, certificate/token rotation | Cấp credential mới theo workload identity |

### 5.1. Assurance không được suy ra từ số bước

Hai yếu tố có thể cùng phụ thuộc vào một mailbox hoặc một thiết bị. Policy cần đánh giá phishing resistance, independence, enrollment, recovery và action. Không coi email OTP + password là tương đương passkey chống phishing cho platform admin.

### 5.2. Action-specific assurance

Người dùng có thể khôi phục quyền đọc nội dung học tập sau proofing phù hợp nhưng chưa chắc được phép thêm authenticator, thay email, xuất dữ liệu hoặc thực hiện admin action ngay. Recovery completion và privileged authorization là hai quyết định khác nhau.

## 6. Kiến trúc thành phần

~~~mermaid
flowchart LR
    UI["Recovery UI"] --> API["Recovery API"]
    API --> ORCH["Recovery orchestrator"]
    ORCH --> POLICY["Policy / risk engine"]
    ORCH --> DIR["Identity directory"]
    ORCH --> FACTOR["Factor verifier"]
    ORCH --> TX["Recovery transaction store"]
    ORCH --> CRED["Credential registry"]
    ORCH --> OUTBOX["Transactional outbox"]
    OUTBOX --> WORKER["Notification / revocation workers"]
    WORKER --> EMAIL["Notification provider"]
    WORKER --> SESSION["Session / token revocation"]
    WORKER --> AUDIT["Audit pipeline"]
    HELP["Helpdesk console"] --> API
    RS["Resource servers"] --> SESSION
~~~

### 6.1. Recovery UI

Hiển thị entry point, lựa chọn method đã được phép, trạng thái pending, next step và help path. UI không tự quyết định account existence, factor eligibility hoặc transaction completion.

### 6.2. Recovery API/orchestrator

Điều phối state machine. Nó kiểm tra caller, normalize identifier, resolve account nội bộ, lấy policy, xác minh proof và thực hiện transition. Orchestrator không chứa logic mật mã tự viết; dùng verifier/library đã được kiểm chứng.

### 6.3. Policy/risk engine

Đánh giá account class, action, tenant, factor assurance, source/device risk, recovery history và approval requirement. Policy có version và decision reason.

### 6.4. Transaction store

Lưu trạng thái recovery, subject reference, purpose, expiry, method allowlist, attempt counter, approval state và token verifier. Không lưu raw recovery secret.

### 6.5. Credential registry

Là nguồn authoritative cho passkey, MFA factor, certificate và trạng thái revoked. Credential enrollment/revocation có audit event.

### 6.6. Outbox và worker

Outbox bảo đảm event/side effect được phát sau khi transaction commit. Worker gửi notification, revoke session và tạo audit event theo idempotency key; retry không làm lặp side effect.

## 7. Data model và state machine

### 7.1. Recovery transaction

Một record khái niệm có thể gồm:

| Field | Mục đích |
| --- | --- |
| transaction_id | Định danh transaction nội bộ |
| public_reference | Handle không phải secret để UI tra trạng thái |
| subject_id | Principal được resolve server-side |
| tenant_context | Tenant đã xác minh nếu transaction cần scope |
| purpose | PASSWORD_RESET, MFA_REPLACEMENT, PASSKEY_REPLACEMENT... |
| status | Trạng thái hiện tại |
| allowed_methods | Method được policy cho phép |
| proof_level | Bằng chứng đã đạt, không tự nâng |
| token_verifier | Verifier/hash của secret nếu có |
| created_at / expires_at | Thời gian và TTL |
| attempts / risk_state | Giới hạn thử và risk |
| approval_state | Không cần, pending, approved, denied |
| policy_version | Policy đã quyết định transaction |
| consumed_at | Thời điểm consume |
| completed_at | Thời điểm hoàn tất |

Không đưa raw email, password, OTP hoặc token vào public_reference. Subject và tenant phải được lưu theo internal identifier có kiểm soát truy cập.

### 7.2. State machine

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PROOF_PENDING
    REQUESTED --> DENIED
    PROOF_PENDING --> PROOF_VERIFIED
    PROOF_PENDING --> EXPIRED
    PROOF_PENDING --> DENIED
    PROOF_VERIFIED --> APPROVAL_PENDING
    PROOF_VERIFIED --> READY
    APPROVAL_PENDING --> READY
    APPROVAL_PENDING --> DENIED
    APPROVAL_PENDING --> EXPIRED
    READY --> CONSUMED
    READY --> EXPIRED
    CONSUMED --> COMPLETING
    COMPLETING --> COMPLETED
    COMPLETING --> COMPENSATION_REQUIRED
    COMPENSATION_REQUIRED --> COMPLETED
    COMPENSATION_REQUIRED --> FAILED
    COMPLETED --> [*]
~~~

### 7.3. Transition rules

- Chỉ state hợp lệ mới được chuyển tiếp.
- Transition phải kiểm tra current state và version để chống race.
- Expired/consumed/denied không được quay lại READY.
- Cancel phải revoke artifact và ngăn side effect chưa chạy.
- Approval chỉ áp dụng cho transaction/purpose/subject cụ thể.
- Mọi transition quan trọng phát audit event.

## 8. API contract đề xuất

API chỉ là ví dụ thiết kế. Tên endpoint và schema cần được điều chỉnh theo convention của sản phẩm.

### 8.1. Khởi tạo recovery

~~~http
POST /v1/recovery/requests
Content-Type: application/json
Idempotency-Key: 9b5d...

{
  "identifier": "learner@example.invalid",
  "requested_purpose": "ACCOUNT_ACCESS"
}
~~~

Response công khai có thể giống nhau với account tồn tại và không tồn tại:

~~~http
202 Accepted
Content-Type: application/json
Cache-Control: no-store

{
  "message": "Nếu thông tin phù hợp với tài khoản, hướng dẫn sẽ được gửi qua kênh đã đăng ký.",
  "request_reference": "rcv_pub_..."
}
~~~

Public reference chỉ để tra trạng thái với quyền phù hợp; nó không đủ để consume recovery. Không trả account_exists, account_status, recovery_channel hoặc danh sách factor trước proofing.

### 8.2. Xem trạng thái

~~~http
GET /v1/recovery/requests/{public_reference}
~~~

Response chỉ hiển thị trạng thái đã được phép tiết lộ cho caller đang giữ transaction context phù hợp. Không để endpoint này thành oracle về account hoặc approval.

### 8.3. Gửi proof

~~~http
POST /v1/recovery/requests/{public_reference}/proof
Content-Type: application/json

{
  "method": "REGISTERED_SECURITY_KEY",
  "proof": {
    "challenge_response": "<proof handled by authenticator flow>"
  }
}
~~~

Proof được xác minh server-side theo method, challenge, RP/origin, transaction và policy. Placeholder không phải giá trị thực; không log proof payload.

### 8.4. Hoàn tất thay đổi credential

~~~http
POST /v1/recovery/requests/{public_reference}/complete
Content-Type: application/json
Idempotency-Key: 3d72...

{
  "change": {
    "type": "REGISTER_NEW_PASSKEY"
  }
}
~~~

Không cho client tự chọn subject, tenant hoặc assurance. Server lấy chúng từ transaction đã xác minh. Request hoàn tất phải được kiểm tra state, expiry, approval và policy ngay trước commit.

## 9. Flow 1 — Password reset self-service

1. Người dùng mở recovery từ trang login chính thức.
2. Nhập identifier; UI hỗ trợ paste và password manager.
3. API trả response chung, không tiết lộ account existence.
4. Nếu account tồn tại và policy cho phép, server tạo transaction và enqueue notification.
5. Người dùng mở link trên domain chính thức.
6. Recovery service xác minh token, subject, purpose, expiry và trạng thái transaction.
7. Người dùng đặt password mới; server kiểm tra policy và breached-password screening.
8. Server atomically consume transaction và cập nhật password verifier.
9. Outbox phát event revoke session/token theo policy và notification.
10. UI chỉ báo hoàn tất khi transaction commit; người dùng được hướng dẫn đăng nhập lại.

### 9.1. Điểm kiểm soát

- Link không được dùng cho passkey enrollment hoặc email change;
- Token không nằm trong analytics/referrer/log;
- Password không được gửi tới client telemetry;
- Retry sau timeout phải idempotent;
- Session cũ bị xử lý theo policy;
- Notification không gửi tới địa chỉ mới chưa xác minh.

## 10. Flow 2 — Mất thiết bị có passkey/MFA

Giả sử học viên mất điện thoại có passkey và TOTP. Họ còn security key dự phòng đã đăng ký trước.

1. Chọn “Tôi không còn thiết bị này”.
2. Server resolve account và policy, nhưng public response vẫn không tiết lộ account state.
3. Sau bước phù hợp, UI hiển thị security key dự phòng.
4. Recovery service tạo WebAuthn challenge ràng buộc RP ID, origin, subject và transaction.
5. Server xác minh assertion và user verification theo policy.
6. Người dùng xác nhận thiết bị bị mất và chọn credential cần revoke.
7. Server revoke passkey/TOTP reference liên quan; không giả định có thể xóa private key trên thiết bị.
8. Người dùng đăng ký passkey mới trên thiết bị hiện tại.
9. Server xác minh enrollment mới, cập nhật registry và tạo notification.
10. Session/token liên quan được revoke hoặc đánh dấu theo risk policy.

Nếu người dùng không còn authenticator dự phòng, flow chuyển sang identity proofing/assisted recovery. Không tự động hạ sang email OTP cho account có yêu cầu phishing-resistant authentication.

## 11. Flow 3 — Tenant admin và platform admin

### 11.1. Tenant administrator

- Recovery cần factor dự phòng đạt policy hoặc proofing/approval độc lập;
- Support tenant chỉ được thao tác trong tenant được cấp;
- Tenant membership và admin role được kiểm tra lại;
- Có thể áp dụng cooldown trước khi credential mới có quyền thực hiện action nhạy cảm;
- Notification tới channel đã xác minh và security contact của tenant theo policy.

### 11.2. Platform administrator

- Ưu tiên security key/passkey dự phòng đã đăng ký;
- Nếu mất mọi factor, dùng break-glass/dual control theo quy trình riêng;
- Không cấp quyền admin đầy đủ chỉ bằng email OTP hoặc thông tin cá nhân;
- Mọi recovery mở alert high priority;
- Session/token cũ được revoke theo policy;
- Có post-recovery review và xác nhận credential inventory.

### 11.3. Không để support tự phê duyệt

Requester, verifier và approver phải tách biệt khi policy yêu cầu. Support operator không được dùng quyền support để chứng minh danh tính của chính mình hoặc tự approve yêu cầu do mình khởi tạo.

## 12. Flow 4 — SSO và IdP outage

Nếu tenant dùng OIDC/SAML SSO, LearnSpace không sở hữu password của người dùng. Recovery password phải diễn ra tại IdP, không phải tại ứng dụng.

### 12.1. IdP outage

- Kiểm tra trạng thái provider và xác định đây là outage hay account-specific failure;
- Thông báo trạng thái dịch vụ ở mức đã xác nhận;
- Không tạo local password reset cho account managed-only;
- Chỉ failover sang IdP dự phòng đã được trust và mapping trước;
- Nếu không có backup IdP phù hợp, cho phép nội dung công khai và từ chối action cần authentication.

### 12.2. Subject mapping

Không tự liên kết account dựa trên email giống nhau. Mapping cần issuer + subject hoặc external identity key được xác minh. Email có thể thay đổi hoặc được tái sử dụng.

### 12.3. SAML/OIDC validation

Kiểm tra signature, issuer, audience, recipient/redirect URI, expiry, state, nonce và replay theo protocol. Không bỏ qua validation để giữ availability.

## 13. Flow 5 — Helpdesk-assisted recovery

1. Người dùng mở case qua support portal chính thức.
2. Hệ thống tạo case reference và ghi purpose.
3. Support xác minh caller theo quy trình đã phê duyệt, không hỏi password/OTP/recovery code.
4. Policy xác định cần một hay nhiều approver.
5. Verifier ghi kết quả proofing; approver độc lập quyết định.
6. Recovery service tạo transaction có scope và TTL riêng.
7. Người dùng hoàn tất factor replacement qua kênh đã xác minh.
8. Notification gửi tới channel phù hợp.
9. Audit ghi requester, support actor, approver, tenant, reason và evidence reference.
10. Case đóng sau khi kiểm tra credential/session state.

### 13.1. Support UI

UI phải hiển thị rõ:
- Principal reference đã xác minh;
- Tenant scope;
- Recovery purpose;
- Proofing status;
- Approver/status;
- Credential change được yêu cầu;
- Session/token action;
- Case owner và expiry.

Không hiển thị secret hoặc cho phép agent nhập token thay người dùng.

## 14. Session, token và credential revocation

Recovery chỉ thực sự bảo vệ account khi credential bị mất và quyền truy cập cũ được xử lý.

### 14.1. Revocation matrix

| Recovery event | Credential action | Session/token action |
| --- | --- | --- |
| Password reset do quên | Thay password verifier | Revoke theo policy; thường cần xử lý refresh-token family |
| Password compromise | Đổi password và kiểm tra credential liên quan | Revoke session/token nghi compromise |
| Mất passkey | Revoke credential ID tương ứng | Revoke session liên quan theo risk |
| MFA factor replacement | Revoke factor cũ sau khi factor mới hợp lệ | Re-evaluate session assurance |
| Email/phone change | Xác minh channel mới và giữ audit | Step-up/revoke session theo risk |
| Account takeover recovery | Revoke credential nghi bị kiểm soát | Revoke toàn bộ session/token theo incident policy |
| Workload key rotation | Revoke certificate/token cũ | Rotate workload credential và connection |
| SSO account disable | Đồng bộ deprovisioning | Revoke local session/federated session theo contract |

### 14.2. Propagation

Revoke event cần đến session store, gateway, backend, refresh-token service và cache. Có SLA propagation. Resource server không nên tiếp tục chấp nhận token cũ vô hạn chỉ vì event bus lỗi.

### 14.3. In-flight request

Với action nhạy cảm, backend có thể cần recheck account/session version trước commit. Policy phải định nghĩa request nào được phép hoàn tất sau revoke.

## 15. Data protection và secret handling

### 15.1. Recovery token

- Sinh bằng CSPRNG;
- Entropy phù hợp;
- Chỉ lưu verifier/hash khi khả thi;
- Gắn subject, purpose, transaction và expiry;
- Consume nguyên tử;
- Revoke khi cancel/complete;
- Không đưa vào URL analytics, referrer hoặc log;
- Không gửi qua support ticket.

### 15.2. Password và authenticator material

Password được xử lý bằng KDF đã kiểm chứng. Recovery code verifier được bảo vệ; TOTP seed được mã hóa và phân quyền nghiêm ngặt. Passkey private key nằm trong authenticator; RP lưu public key và metadata. Certificate private key không được đưa vào recovery database.

### 15.3. Pseudonymous references

Alert và dashboard dùng principal/credential/session reference đã pseudonymize. Mapping về danh tính thật chỉ mở trong secured console với quyền, purpose và audit.

## 16. Audit event và observability

Một recovery transaction nên tạo event cho các bước:
- Request accepted;
- Account match/no-match internal decision;
- Method offered/selected;
- Proof success/failure;
- Approval requested/approved/denied;
- Token issued/consumed/rejected;
- Credential added/removed/revoked;
- Session/token revocation requested/completed;
- Notification queued/delivered/failed;
- Transaction completed/expired/cancelled.

### 16.1. Event schema ví dụ

~~~json
{
  "event_id": "evt_01JQ...",
  "transaction_ref": "rcv_ref_...",
  "event_type": "recovery.credential.replaced",
  "event_time": "2026-11-22T08:15:00Z",
  "subject_ref": "principal_ref_...",
  "actor_ref": "user_or_support_ref_...",
  "tenant_ref": "tenant_ref_...",
  "purpose": "PASSKEY_REPLACEMENT",
  "method": "REGISTERED_SECURITY_KEY",
  "outcome": "SUCCESS",
  "policy_version": "recovery-policy-7",
  "correlation_id": "corr_..."
}
~~~

Event không chứa token, OTP, password, private key hoặc full assertion. Không ghi raw email/phone nếu pseudonymous reference đủ cho detection.

### 16.2. Metric cần theo dõi

- Recovery request/completion/abandonment;
- Proof failure và retry rate;
- Token replay/expiry rejection;
- Recovery per principal/source/tenant;
- Helpdesk override và approval latency;
- Session revocation latency;
- Notification delivery;
- Recovery abuse/false rejection;
- Queue lag và event loss;
- Credential enrollment sau recovery.

### 16.3. Alert

Alert khi admin recovery, recovery từ source bất thường, nhiều account cùng bị thử, passkey mới sau proof yếu, helpdesk override, token replay hoặc session vẫn hoạt động sau revoke. Phân biệt security alert với IdP/provider outage.

## 17. Failure mode và consistency

Recovery thường có nhiều side effect không thể commit cùng một database transaction. Thiết kế cần xử lý partial failure.

| Failure | Hành vi cần có |
| --- | --- |
| Notification provider outage | Transaction vẫn ở state đúng; retry có giới hạn; UI không báo message đã gửi nếu chưa |
| Session service outage | Ghi outbox/retry; action nhạy cảm có thể bị hạn chế |
| Audit pipeline outage | Không âm thầm bỏ evidence; fail/degraded theo policy |
| Directory timeout | Không đoán account state hoặc cho phép recovery |
| Approval service outage | Không tự coi pending là approved |
| Queue redelivery | Consumer idempotent, không lặp credential change |
| Region partition | Chỉ một transaction consume theo consistency model |
| Clock skew | TTL kiểm tra bằng clock policy và leeway giới hạn |
| Credential registry outage | Không enroll/revoke khi không xác minh được state cần thiết |
| IdP outage | Chỉ dùng backup trust path đã phê duyệt |

### 17.1. Transactional outbox

Credential update và outbox record nên commit trong cùng transaction database. Worker đọc outbox, thực hiện revoke/notification/audit và đánh dấu kết quả. Nếu worker crash sau khi side effect thành công nhưng trước khi ack, idempotency key giúp retry an toàn.

### 17.2. Reconciliation

Job reconciliation so sánh recovery transaction với credential/session state thực tế. Ví dụ transaction COMPLETED nhưng session revoke chưa xong phải tạo task và alert; không giả định event đã được gửi chỉ vì outbox record tồn tại.

## 18. Privacy và UX

### 18.1. Public response chung

Với account tồn tại/không tồn tại, response cần nhất quán theo privacy policy. Không tiết lộ email, phone, factor count, tenant membership hoặc trạng thái suspended trước proofing.

### 18.2. Hướng dẫn dễ hiểu

Mỗi màn hình trả lời:
- Người dùng đang ở bước nào;
- Cần làm gì tiếp;
- Mã/token có hết hạn hoặc dùng một lần không;
- Điều gì xảy ra với session/credential cũ;
- Liên hệ support qua kênh chính thức ở đâu.

### 18.3. Accessibility

Hỗ trợ keyboard, screen reader, paste/autofill, thông báo trạng thái async, error summary và CAPTCHA alternative. Không chỉ dùng màu để biểu thị lỗi. Người dùng không nên phải nhập lại identifier từ đầu khi transaction vẫn hợp lệ.

### 18.4. Notification chống phishing

Thông báo không chứa secret; link dùng domain chính thức; nêu loại thay đổi, thời gian và cách báo cáo. Không yêu cầu người dùng trả lời email bằng OTP hoặc gọi số không được công bố.

## 19. Threat scenario và phân tích quyết định

### Scenario A — Attacker kiểm soát mailbox

Attacker biết email và có thể đọc mailbox. Nếu email link là proof duy nhất để thay passkey cho platform admin, attacker có thể chiếm account.

**Quyết định:** Email chỉ là notification hoặc một bước trong policy phù hợp; admin cần phishing-resistant backup factor hoặc assisted proofing/dual control. Email link không tự cấp assurance admin.

### Scenario B — Hai request consume cùng token

Người dùng double-click hoặc attacker replay đồng thời. Nếu service đọc trạng thái pending rồi update không atomic, cả hai request có thể thành công.

**Quyết định:** Atomic compare-and-set/state transition; chỉ một request thắng; request còn lại nhận kết quả đã tiêu thụ mà không tạo side effect.

### Scenario C — Recovery thành công nhưng session cũ còn sống

Password đã đổi nhưng refresh token family vẫn active ở một region.

**Quyết định:** Outbox + revocation event + propagation SLA + reconciliation. Account takeover recovery revoke theo incident policy; kiểm thử multi-region.

### Scenario D — Helpdesk bị social engineer

Attacker cung cấp thông tin cá nhân công khai và yêu cầu thêm passkey mới.

**Quyết định:** Support không tự quyết proofing; cần evidence độc lập, role scope, approval tách biệt, case purpose và notification. Không hỏi OTP/password.

### Scenario E — IdP outage

Ứng dụng muốn chấp nhận token từ issuer khác để duy trì availability.

**Quyết định:** Chỉ dùng issuer backup đã pre-register, key/audience/subject mapping và assurance context đã kiểm thử. Nếu không có trust path phù hợp, giới hạn chức năng hoặc từ chối authentication.

### Scenario F — Tenant context bị giả mạo

Client gửi tenant ID khác để recovery principal trong tenant khác.

**Quyết định:** Tenant resolve từ server-side mapping và kiểm tra membership/resource ownership hiện tại. Client selector chỉ là input không tin cậy.

## 20. Test strategy

Kiểm thử theo nhiều tầng, dùng account giả lập, IdP sandbox, email/SMS sink, fake clock và isolated tenant.

| Tầng | Phạm vi | Ví dụ |
| --- | --- | --- |
| Unit | Policy/state machine/token verifier | TTL, purpose, subject, expiry |
| Component | Recovery service + DB/outbox | Atomic consume, idempotency |
| Integration | IdP, notification, session service | Proof, delivery, revocation |
| End-to-end | Web/mobile journey | Accessibility, UX, recovery completion |
| Security negative | Replay, enumeration, tampering | Không bypass |
| Concurrency | Parallel consume/approve | Chỉ một transition |
| Resilience | Timeout, queue retry, outage | Không partial-success sai |
| Multi-tenant | Principal/membership isolation | Không cross-tenant |
| Operational | Alert, runbook, reconciliation | Phát hiện và phục hồi |

### 20.1. Test case matrix

| ID | Scenario | Expected result |
| --- | --- | --- |
| RCV-001 | Identifier hợp lệ | Response chung; transaction nội bộ nếu đủ điều kiện |
| RCV-002 | Identifier không tồn tại | Public response tương đương |
| RCV-003 | Account suspended | Không hoàn tất ngoài policy |
| RCV-004 | Proof đúng | Chuyển state theo policy |
| RCV-005 | Proof sai | Từ chối, rate limit và audit |
| RCV-006 | Factor chưa đăng ký | Từ chối |
| RCV-007 | Token sai subject | Từ chối |
| RCV-008 | Token sai purpose | Từ chối |
| RCV-009 | Token hết hạn | Từ chối |
| RCV-010 | Token đã consumed | Từ chối replay |
| RCV-011 | Hai request consume đồng thời | Chỉ một request thành công |
| RCV-012 | Brute force code | Throttle/challenge và alert |
| RCV-013 | Password reset | Verifier cập nhật đúng |
| RCV-014 | Password reset với account bị disable giữa flow | Từ chối |
| RCV-015 | Passkey enrollment sau recovery | RP/origin/challenge/UV hợp lệ |
| RCV-016 | Assertion sai origin | Từ chối |
| RCV-017 | MFA recovery code đã dùng | Từ chối |
| RCV-018 | Push challenge cũ | Không approve transaction mới |
| RCV-019 | Helpdesk agent thiếu role | DENY |
| RCV-020 | Requester tự approve | DENY theo separation policy |
| RCV-021 | Support sai tenant | DENY |
| RCV-022 | Email giống nhau ở hai IdP | Không auto-link |
| RCV-023 | IdP backup chưa trust | Từ chối |
| RCV-024 | Wrong issuer/audience | Từ chối |
| RCV-025 | Session revoke service outage | Outbox/retry; action nhạy cảm theo policy |
| RCV-026 | Queue redelivery | Side effect idempotent |
| RCV-027 | Notification outage | Không báo đã gửi giả |
| RCV-028 | Audit pipeline outage | Fail/degraded theo policy |
| RCV-029 | Tenant membership revoked | Không khôi phục membership |
| RCV-030 | Refresh token cũ được reuse | Từ chối và alert |
| RCV-031 | Recovery cancel | Artifact bị revoke |
| RCV-032 | Recovery transaction hết hạn | Không thể tiếp tục |
| RCV-033 | Recovery thành công | Notification và audit có evidence |
| RCV-034 | Log inspection | Không có password/OTP/token |
| RCV-035 | Multi-region revoke | Propagation trong SLA |
| RCV-036 | Account admin recovery | Phishing-resistant proof/approval bắt buộc |
| RCV-037 | Degraded mode hết hạn | Tự đóng hoặc yêu cầu approval mới |
| RCV-038 | Client retry sau timeout | Idempotent result |
| RCV-039 | Credential registry outage | Không enroll khi không thể kiểm tra state |
| RCV-040 | Reconciliation phát hiện revoke pending | Tạo task/alert tới owner |

## 21. Pseudocode orchestration

~~~text
begin_recovery(identifier, requested_purpose, request_context):
    enforce_multidimensional_rate_limits(request_context, identifier)
    account = resolve_account_privately(identifier)

    if account is absent:
        record_minimized_nonmatch_event()
        return generic_public_response()

    policy = load_versioned_policy(
        account_class = account.class,
        purpose = requested_purpose,
        tenant = resolve_verified_tenant(account, request_context)
    )

    require policy.recovery_enabled
    methods = registered_nonrevoked_methods(account)
    eligible_methods = filter_by_assurance(methods, policy)

    transaction = create_pending_transaction(
        subject = account.internal_id,
        purpose = requested_purpose,
        allowed_methods = eligible_methods,
        expires_at = policy.transaction_expiry,
        policy_version = policy.version
    )

    enqueue_notification_if_allowed(transaction)
    return generic_public_response()
~~~

~~~text
complete_recovery(public_reference, proof, requested_change):
    tx = load_transaction(public_reference)
    require tx.status permits completion
    require now is before tx.expires_at
    require requested_change.purpose == tx.purpose

    account = load_account(tx.subject_id)
    require account.status permits recovery
    require verify_registered_proof(tx, proof)
    require approval_satisfied(tx)
    require current_policy_allows(tx, account, requested_change)

    atomically:
        consume_transaction_once(tx)
        apply_credential_change(account, requested_change)
        write_outbox_events(
            credential_changed,
            revoke_sessions_by_policy,
            notify_verified_channels,
            audit_recovery_completed
        )

    return completion_reference()
~~~

Pseudocode chỉ mô tả orchestration. Triển khai thực tế cần transaction isolation, compare-and-set, secure random, password KDF, WebAuthn/PKI/OIDC libraries đã kiểm chứng, idempotency, clock policy và kiểm tra quyền tại thời điểm commit.

## 22. Rollout và migration

### 22.1. Giai đoạn 1 — Inventory

- Liệt kê recovery endpoint, factor và account class;
- Xác định owner của IdP, session, credential registry và notification;
- Đo recovery volume, failure và support override;
- Tìm token TTL dài, raw token storage và shared account;
- Xác định tenant có policy riêng.

### 22.2. Giai đoạn 2 — Shadow/audit mode

Chuẩn hóa event và state model, chạy policy decision ở chế độ quan sát. So sánh kết quả policy mới với hành vi hiện tại; không tự động block trước khi hiểu false positive và user impact.

### 22.3. Giai đoạn 3 — Pilot

Bật cho một nhóm tenant và account class ít rủi ro hơn. Test password reset, backup factor, session revocation, support workflow và notification. Có rollback plan.

### 22.4. Giai đoạn 4 — Privileged rollout

Bật policy mạnh cho admin sau khi backup authenticator, helpdesk approval, break-glass và alert đã được diễn tập. Không chuyển toàn bộ admin sang flow mới nếu chưa có phương án recovery đã xác minh.

### 22.5. Giai đoạn 5 — Decommission legacy

Thu hồi endpoint cũ, token format cũ và bypass không còn cần. Kiểm tra client/version còn gọi flow cũ; giữ compatibility window có expiry và audit. Không để legacy bypass tồn tại vô thời hạn.

## 23. Vận hành và incident response

### 23.1. Dashboard

Theo dõi:
- Recovery requests và completion theo purpose;
- Proof failure và retry;
- Token replay/expiry;
- Helpdesk approval/override;
- Credential enrollment/removal;
- Session revoke latency;
- Notification delivery;
- Queue lag/outbox backlog;
- Tenant distribution;
- Recovery từ privileged account.

### 23.2. Runbook

Khi alert recovery abuse:
1. Xác định transaction, subject reference, tenant và purpose;
2. Kiểm tra proofing/approval và source context;
3. Kiểm tra credential mới và session/token sau recovery;
4. Xác định có account takeover hay chỉ request không thành công;
5. Revoke session/credential có liên quan theo incident policy;
6. Thông báo người dùng qua channel đã xác minh;
7. Bảo toàn evidence reference;
8. Kiểm tra các account/tenant khác có cùng pattern;
9. Ghi disposition và root cause.

### 23.3. Không phản ứng quá mức

Không khóa toàn bộ tenant chỉ vì một account có recovery request bất thường. Containment cần scope đúng principal, session, credential hoặc source. Hành động có blast radius lớn cần approval theo policy.

## 24. Những quyết định thiết kế và trade-off

| Quyết định | Lợi ích | Chi phí/rủi ro cần quản lý |
| --- | --- | --- |
| Public response chung | Giảm enumeration | Người dùng ít feedback tức thời; cần notification tốt |
| Recovery transaction stateful | Chống replay/race và dễ audit | Tăng lưu trữ/state management |
| Backup authenticator | Giảm lockout | Người dùng phải enrollment và cất giữ |
| Approval/cooldown cho admin | Giảm social engineering | Recovery chậm hơn, cần support capacity |
| Outbox/reconciliation | Xử lý partial failure | Tăng độ phức tạp vận hành |
| Pseudonymous telemetry | Giảm lộ PII | Cần secured mapping cho điều tra |
| Fail closed cho action nhạy cảm | Bảo vệ assurance | Có thể giảm availability trong outage |
| Degraded mode có TTL | Duy trì một số chức năng | Cần owner, review và auto-expiry |

### 24.1. Trade-off không thể loại bỏ

Không thể đồng thời tối đa hóa self-service convenience, zero lockout, phishing resistance và chi phí support thấp trong mọi tình huống. Tổ chức phải chọn mức chấp nhận rủi ro theo account class và action, rồi giải thích lựa chọn bằng policy và evidence.

## 25. Bài tập phân tích

Một tenant lớn báo rằng nhiều giảng viên không thể recovery vì đã đổi điện thoại. Helpdesk đề xuất cho phép reset MFA bằng email OTP. Cùng lúc, monitoring phát hiện một số admin recovery từ network mới; notification provider đang chậm; session revoke event bị trễ ở một region.

**Yêu cầu:**

1. Phân loại các vấn đề thành usability, security, availability và operational.
2. Xác định account class nào có thể dùng email OTP, nếu có, và action nào vẫn phải bị hạn chế.
3. Thiết kế flow cho giảng viên còn security key dự phòng và flow cho người mất mọi factor.
4. Đề xuất response cho admin recovery từ network mới.
5. Xác định cách xử lý khi notification chậm nhưng recovery transaction đã được tạo.
6. Thiết kế reconciliation cho session revoke bị trễ.
7. Chọn metric/alert để đánh giá tình trạng tenant mà không tạo enumeration.
8. Viết test case cho replay, race, wrong tenant, helpdesk abuse và degraded mode.

**Gợi ý phân tích:** Không áp một phương thức fallback cho mọi account; ưu tiên factor đã đăng ký và đạt assurance; admin cần proofing/approval mạnh; notification state phải trung thực; session revoke cần outbox/reconciliation; không coi email OTP là tương đương passkey.

## 26. Checklist đánh giá hệ thống recovery

1. **Identity:** Principal được resolve từ nguồn authoritative?
2. **Purpose:** Transaction gắn đúng purpose và action?
3. **Policy:** Account class và assurance requirement được áp dụng?
4. **Proof:** Factor đã đăng ký, còn hiệu lực và được xác minh server-side?
5. **Token:** Entropy, TTL, verifier, subject binding và one-time use?
6. **Replay/race:** Consume nguyên tử và idempotency?
7. **Enumeration:** Public response và timing không tiết lộ account state?
8. **Helpdesk:** RBAC, purpose, approval và separation of duties?
9. **Tenant:** Membership/resource ownership được kiểm tra hiện tại?
10. **Credential:** Credential mới/old state cập nhật đúng?
11. **Session:** Refresh token, session và cache revoke theo SLA?
12. **Notification:** Gửi đúng channel, không chứa secret, retry idempotent?
13. **Audit:** Actor, subject, tenant, purpose, policy version và evidence?
14. **Privacy:** Log, queue, ticket, analytics đã giảm thiểu dữ liệu?
15. **Resilience:** Outage/partial commit/reconciliation được kiểm thử?
16. **UX/accessibility:** State, error, cooldown và next step rõ?
17. **Monitoring:** Abuse, completion, proof failure và revoke latency có alert?
18. **Governance:** Owner, runbook, exception expiry và periodic review?

## 27. Kết luận tình huống

LearnSpace cần một recovery service thống nhất điều phối state machine, policy theo account/action, proofing bằng authenticator đã đăng ký, approval cho trường hợp rủi ro cao và side effect qua outbox. Public response được tối thiểu hóa để giảm enumeration; recovery artifact gắn subject/purpose/expiry và chỉ consume một lần; credential/session cũ được xử lý theo policy; tenant authorization được kiểm tra lại; helpdesk có scope và separation of duties; audit và notification có thể theo dõi mà không lưu secret.

Giải pháp không giả định mọi outage đều có thể vượt qua bằng một factor yếu hơn. Khi không còn trust path đáp ứng assurance, hệ thống giới hạn action hoặc từ chối có kiểm soát. Cách tiếp cận này giữ được trải nghiệm self-service cho tình huống thông thường, đồng thời bảo vệ account đặc quyền, tenant data và workload identity trong các trường hợp recovery phức tạp.

Hệ thống recovery trưởng thành khi **người dùng hợp lệ có thể lấy lại quyền kiểm soát theo một hành trình rõ ràng, còn mọi thay đổi danh tính và credential đều có bằng chứng, giới hạn và khả năng thu hồi**.
