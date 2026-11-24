# Audit IAM là gì? Kiểm toán danh tính, quyền truy cập và vòng đời Joiner–Mover–Leaver

## 1. Audit IAM là gì?

**Audit IAM (Identity and Access Management audit)** là hoạt động **thu thập, kiểm tra, đối chiếu và đánh giá bằng chứng** để xác định tổ chức có **quản lý danh tính, xác thực, cấp quyền, sử dụng quyền và thu hồi quyền** đúng chính sách hay không. Audit IAM giúp trả lời một chuỗi câu hỏi liên kết:

- **Ai** là chủ thể được quản lý, và danh tính được xác minh từ đâu?
- **Ai hoặc hệ thống nào** yêu cầu, phê duyệt hay thực hiện thay đổi?
- **Quyền gì** được cấp/giữ/điều chỉnh/thu hồi, trên **tài nguyên và phạm vi nào**?
- **Khi nào** sự kiện xảy ra, có hiệu lực và được hệ thống ghi nhận?
- **Vì sao** thao tác được chấp nhận theo business need và policy nào?
- **Kết quả** có thật sự xuất hiện tại ứng dụng/thiết bị/tài nguyên đích không?
- **Có còn quyền truy cập tồn dư** sau Mover, Leaver, expiry hoặc incident không?

Ví dụ: HRIS ghi nhận Lan chuyển từ Sales sang Finance; IAM lên kế hoạch gỡ nhóm SALES_EXPORT; SCIM connector báo đã xử lý. Audit IAM không chỉ kiểm có ticket **Completed**, mà còn tìm **bằng chứng HRIS event → policy/approval → thao tác connector → quyền đọc lại ở CRM → kiểm thử action export bị từ chối**. Chỉ khi các mắt xích phù hợp mới có cơ sở kết luận việc thu hồi đã được thực thi trong phạm vi kiểm tra.

Bài thuộc chương **Identity audit** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi mô-đun: **quản lý vòng đời danh tính trong IAM theo Joiner–Mover–Leaver**, từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi thay đổi vai trò, liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm **quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mục đích, phạm vi và những câu hỏi cốt lõi của **audit IAM**.
2. Phân biệt **audit**, **audit log**, **security monitoring**, **access review** và **compliance assessment**.
3. Nhận diện **actor, subject, target, action, policy decision, execution result và observed state** trong một audit trail.
4. Thiết kế bằng chứng liên kết **Joiner–Mover–Leaver**, authentication, SSO, SCIM và authorization.
5. Phân biệt **đã phê duyệt**, **đã gửi lệnh** và **đã xác minh quyền thực tế**.
6. Xây dựng **event schema, correlation ID, thời gian, provenance, bảo vệ tính toàn vẹn, retention và quyền riêng tư**.
7. Kiểm toán những quyền khó quan sát như **local account, service identity, token, credential và privileged session**.
8. Thiết lập **kiểm thử, chỉ số, phát hiện sai lệch và runbook** cho quy trình audit có thể chứng minh.

## 2. Vì sao IAM cần audit?

IAM không chỉ là hệ thống đăng nhập; nó là **chuỗi quyết định và thực thi** trải qua HRIS, IdP, IGA, ứng dụng SaaS, cloud IAM, PAM, directory, database và hệ thống nội bộ. Mỗi thành phần có thể ghi trạng thái **SUCCESS** cho phần việc của mình nhưng toàn chuỗi vẫn sai.

Một số tình huống:

- Account đã được tạo nhưng **không có bằng chứng identity proofing** cần thiết.
- Manager phê duyệt quyền nhưng **resource owner** chưa chấp thuận theo policy.
- Quyền được cấp qua nhóm lồng nhau hoặc local role **ngoài danh mục IAM**.
- HRIS thông báo Leaver nhưng **SaaS local session vẫn hoạt động**.
- Group đã bị gỡ ở IdP nhưng **JWT/access token cũ còn được API tin**.
- Service account thiếu owner hoặc vẫn giữ cloud role sau khi workload retire.
- Người tạo access request đồng thời có quyền **approve own request**, vi phạm SoD.
- Chiến dịch access review đã đóng nhưng các tác vụ **REVOKE vẫn Pending**.

**Audit giúp phát hiện sự khác biệt giữa điều tổ chức tin là đã xảy ra và điều thực sự được chứng minh.** Nó phục vụ bảo mật, điều tra, quản trị rủi ro, cải tiến quy trình và các yêu cầu kiểm soát áp dụng.

### Audit không có nghĩa chỉ tìm lỗi

Một kết quả audit tốt cũng chứng minh **control đang hoạt động**: quyền được cấp đúng approval, step-up MFA được yêu cầu khi cần, account được thu hồi đúng thời điểm, và target thực sự từ chối action trái policy.

## 3. Phân biệt audit, logging, monitoring và access review

| Hoạt động | Câu hỏi chính | Đầu ra điển hình |
|---|---|---|
| **Event logging** | Sự kiện nào vừa diễn ra? | Bản ghi login, grant, revoke, API call |
| **Audit trail** | Có thể nối và giải thích ai làm gì, dựa vào căn cứ nào? | Chuỗi sự kiện có provenance và correlation |
| **IAM audit** | Các kiểm soát danh tính/quyền có đúng, đầy đủ và hiệu quả? | Kết luận có bằng chứng, finding, remediation |
| **Security monitoring** | Có hành vi đáng ngờ cần cảnh báo ngay? | Alert, incident, rule detection |
| **Access review/certification** | Quyền đang tồn tại có nên tiếp tục được giữ? | RETAIN, REVOKE, MODIFY, ESCALATE |
| **Reconciliation** | Desired access có khớp observed access? | Drift/finding và trạng thái xử lý |
| **Compliance assessment** | Có đáp ứng tiêu chí kiểm soát/chuẩn/nghĩa vụ cụ thể? | Assessment và phạm vi bằng chứng |
| **Forensic investigation** | Một sự cố đã diễn ra theo chuỗi nào? | Timeline, actor, ảnh hưởng và evidence chain |

**Audit log là một nguồn bằng chứng của audit, không phải bản thân toàn bộ hoạt động audit.** Một dòng log “role removed” không cho biết quyền còn đến từ nhóm khác hay không. Ngược lại, một access review decision “Retain” không tự chứng minh runtime authorization đang đúng.

### Internal audit và operational audit

Audit nội bộ có thể đánh giá chính sách/quy trình, phân công trách nhiệm, mức độ độc lập và hiệu quả kiểm soát. Các đội Security/Platform thường kiểm toán vận hành qua log, scan, reconciliation và dashboard. Hai hình thức có thể sử dụng cùng evidence nhưng **mục tiêu, phạm vi và thẩm quyền kết luận phải được nói rõ**.

## 4. Phạm vi audit IAM cần bao phủ

| Nhóm kiểm soát | Cần xem xét |
|---|---|
| **Identity proofing** | Nguồn xác minh danh tính, mức assurance, ngoại lệ |
| **Enrollment** | Đăng ký account/credential/MFA, liên kết identity |
| **Joiner** | Birthright roles, approval bổ sung, effectiveAt |
| **Mover** | Gỡ role cũ, cấp role mới, tránh privilege accumulation |
| **Leaver** | Disable account, revoke tokens/sessions/entitlements |
| **Authentication** | MFA, passkey, failures, step-up, risk policy |
| **SSO/federation** | IdP/OP, RP/SP sessions, claim mapping |
| **Authorization** | RBAC, ABAC, PBAC, SoD, scope, decisions |
| **Provisioning** | SCIM/API tạo/sửa/vô hiệu User, Group |
| **Access request/approval** | Người yêu cầu, người duyệt, reason, thời hạn |
| **Access review** | Reviewer authority, decisions, fulfillment |
| **Privileged access** | PIM/PAM, JIT, break-glass, session termination |
| **Non-human identity** | Service account, workload, machine, credential |
| **Policy management** | Ai thay chính sách, thay đổi được duyệt không |
| **Logging/governance** | Bảo vệ log, retention, coverage, evidence integrity |

Không phải mọi audit phải kiểm toàn bộ các nhóm cùng lúc. Phạm vi cần được xác định theo **mục tiêu, tài nguyên quan trọng, risk, thời gian và khả năng quan sát**, rồi ghi rõ những điểm **không được kiểm**.

## 5. Bốn lớp bằng chứng: intent, decision, execution và effect

Một cách tư duy quan trọng là tách các lớp:

1. **Intent / Desired state:** Nhu cầu và trạng thái quyền được phép tồn tại theo HRIS/JML/policy.
2. **Decision:** Hệ thống hoặc reviewer đã Approve/Deny/Retain/Revoke theo thẩm quyền và bằng chứng nào?
3. **Execution:** Connector, IdP, API hoặc administrator đã thực hiện thao tác gì và nhận kết quả nào?
4. **Effect / Observed state:** Hệ thống đích thực sự có account/entitlement/session ở trạng thái nào; action còn được Permit không?

~~~mermaid
flowchart TD
    SOURCE[HRIS / Contract / Workload Registry] --> DES[Desired access]
    POLICY[Business policy + approvals] --> DEC[Decision: Permit / Revoke / Modify]
    DES --> DEC
    DEC --> EXEC[IdP / SCIM / PAM / Target API operation]
    EXEC --> ACK[Acknowledgement and error]
    ACK --> OBS[Target readback / effective grants]
    OBS --> ACTION[Runtime authorization validation]
    DES --> RECON[Reconciliation]
    ACTION --> RECON
    RECON --> AUDIT[Audit finding / verified closure]
~~~

### Ba câu nói dễ bị nhầm

- **“Đã gửi lệnh revoke.”** Chỉ xác nhận intent/dispatch, chưa có target outcome.
- **“SCIM trả HTTP 204.”** Thường cho thấy operation đã được xử lý theo giao thức, chưa xác nhận mọi nguồn quyền khác đều bị gỡ.
- **“API không còn cho export.”** Là một bằng chứng trực tiếp hơn về hiệu lực, nhưng vẫn phải biết **subject, resource, action, thời điểm và độ bao phủ** của phép kiểm.

**Một audit có giá trị phải chỉ ra bằng chứng thuộc lớp nào.** Không được nâng một status hành chính thành kết luận “không còn khả năng truy cập” khi chưa đủ kiểm chứng.

## 6. Các chủ thể và định danh cần phân biệt

Một sự kiện IAM có thể liên quan nhiều danh tính:

| Vai trò | Câu hỏi | Ví dụ |
|---|---|---|
| **Actor / Initiator** | Ai phát động thao tác? | Manager gửi access request |
| **Requester** | Ai yêu cầu quyền? | Lan xin Finance Reader |
| **Beneficiary / Subject** | Ai sẽ nhận hoặc mất quyền? | person-2046 |
| **Approver / Reviewer** | Ai có thẩm quyền kết luận? | Resource owner |
| **Executor / Connector** | Thành phần nào thực thi? | iam-scim-connector |
| **Target account** | Account cụ thể ở đích nào thay đổi? | crm-user-7839 |
| **Target resource** | Tài nguyên bị tác động? | CRM group hoặc finance report |
| **Policy evaluator** | Ai/engine nào trả Permit/Deny? | Authorization service |
| **Workload owner** | Ai chịu trách nhiệm cho non-human identity? | Payments Platform |

**Actor và beneficiary có thể khác nhau.** Một HRIS event cập nhật tài khoản của Lan có thể được phát bởi HRIS connector, nhưng không được ghi nhầm connector là người sở hữu quyền nghiệp vụ.

### Identifier đáng tin

Dùng **immutable subject/person ID, relationship ID, target account ID, resource ID và tenant ID** khi có thể. Email, display name và username có thể đổi/tái sử dụng; chúng hữu ích để hiển thị nhưng không phải khóa nối audit trail đáng tin trong mọi trường hợp.

## 7. Một audit event nên chứa gì?

Bản ghi tối thiểu nên giúp trả lời **who, what, when, where, why, result** và liên hệ chuỗi.

| Nhóm trường | Dữ liệu | Mục đích |
|---|---|---|
| **Event identity** | eventId, eventType, schemaVersion | Phân biệt và giải mã sự kiện |
| **Time** | occurredAt, observedAt, ingestedAt | Tái dựng timeline |
| **Actor** | actorId, actorType, authenticationContext | Ai yêu cầu/thao tác |
| **Subject** | subjectId, relationshipId, targetAccountId | Ai bị tác động |
| **Resource** | systemId, tenantId, resourceId, entitlementId | Quyền/tài nguyên nào |
| **Action** | create, grant, revoke, login, review, approve | Chuyện gì được yêu cầu |
| **Decision** | Permit/Deny, policyVersion, reasonCode | Quyết định dựa vào đâu |
| **Execution** | operationId, target status, errorCode | Thao tác tại đích |
| **Observed result** | effectiveGrantState, verifiedAt | Trạng thái thực tế |
| **Correlation** | correlationId, causationId, sourceEventId | Nối các hệ thống |
| **Governance** | approverId, approvalId, exceptionId | Căn cứ thẩm quyền |
| **Evidence** | evidenceRef, integrity metadata, coverage | Kiểm chứng và truy xuất |

Không bắt buộc mỗi loại event có tất cả trường; ví dụ **AuthenticationFailed** có thể không biết userId xác thực. Với dữ liệu thiếu, cần diễn đạt **UNKNOWN/NOT_OBSERVED** thay vì tự điền giá trị giả.

## 8. Ví dụ JSON audit event về thu hồi quyền

~~~json
{
  "eventId": "evt-iam-20261123-0182",
  "schemaVersion": "1.0",
  "eventType": "EntitlementRevocationVerified",
  "occurredAt": "2026-11-23T09:20:00+07:00",
  "ingestedAt": "2026-11-23T09:20:04+07:00",
  "actor": {
    "id": "iam-provisioning-worker",
    "type": "WORKLOAD"
  },
  "subject": {
    "identityId": "person-2046",
    "relationshipId": "employment-2046-v2",
    "targetAccountId": "crm-user-7839"
  },
  "resource": {
    "systemId": "crm-production",
    "tenantId": "org-vn",
    "entitlementId": "crm-sales-export"
  },
  "action": "REVOKE_ENTITLEMENT",
  "reasonCode": "MOVER_ROLE_CHANGED",
  "sourceEventId": "hris-mover-00931",
  "sourceVersion": 7,
  "policyVersion": "access-lifecycle-v6",
  "operationId": "scim-op-12193",
  "targetObserved": {
    "grantPresent": false,
    "observedAt": "2026-11-23T09:19:57+07:00"
  },
  "correlationId": "corr-mover-2046-7",
  "decision": "VERIFIED_WITHIN_OBSERVED_SCOPE"
}
~~~

Đây là **schema nội bộ minh họa**, không phải một chuẩn event bắt buộc của SCIM, OAuth hay hệ thống audit cụ thể.

**Chú ý sự khác biệt:** eventType nói “verified” chỉ nên được phát sau khi kiểm tra evidence phù hợp. Nếu chỉ có response của connector, nên ghi **RevocationOperationAcknowledged**, không được tự gắn nhãn Verified.

### Không ghi secrets trong log

Không ghi **password, OAuth access/refresh token, session cookie, private key, API key, OTP, recovery code hoặc toàn bộ payload nhạy cảm**. Dùng requestId, token identifier không thể dùng làm credential, fingerprint phù hợp và thông tin tối thiểu để truy vết.

## 9. Audit trail xuyên suốt Joiner–Mover–Leaver

JML làm thay đổi **căn cứ quyền truy cập**; audit cần liên kết các sự kiện thay vì chỉ xem snapshot tài khoản hiện tại.

~~~mermaid
flowchart LR
    HR[HRIS: Joiner / Mover / Leaver] --> IAM[IAM Desired State]
    IAM --> APPROVE[Policy / Approval]
    APPROVE --> PROV[Provisioning / Deprovisioning]
    PROV --> IDP[IdP / Directory]
    PROV --> APP[App / SCIM / Cloud]
    IDP --> LOG[Audit Trail]
    APP --> LOG
    HR --> LOG
    APPROVE --> LOG
    PROV --> LOG
    LOG --> REV[Access Review / Reconciliation]
    REV --> FIND[Finding / Verified Close]
~~~

### Các mốc cần có

- **Event source và effectiveAt** từ HRIS/contract authority.
- **Identity relationship** nào được thêm/đổi/kết thúc.
- **Desired access** sau thay đổi là gì.
- Policy và approval cho quyền bổ sung.
- Account/group/role nào đã được target thay đổi.
- Session/token/credential nào cần cắt.
- **Observed state** và thời điểm kiểm lại.
- Khoảng thời gian **residual access** nếu có.
- Ai chịu trách nhiệm sửa sai và deadline.

**Audit JML quan tâm cả quyền đã được cấp lẫn quyền đã được cắt**, tránh chỉ đo tốc độ onboarding.

## 10. Audit Joiner: từ xác minh đến cấp quyền

Một Joiner hợp lệ thường để lại chuỗi:

1. Nguồn nhân sự/hợp đồng tạo **identity candidate** và relationship.
2. Quy trình **identity proofing** xác nhận thuộc tính cần thiết.
3. IdP/IGA tạo identity/account mapping ổn định.
4. **Authenticator enrollment** thiết lập MFA/passwordless hoặc cơ chế được duyệt.
5. Role baseline được tính từ job function, department, scope.
6. Quyền ngoài baseline đi qua **access request/approval**.
7. SCIM/API provision account và memberships tới target.
8. Target readback xác nhận đúng role, group và phạm vi.
9. Runtime access test hoặc audit chứng minh action được Permit theo policy.
10. Audit ghi evidence, effectiveAt, owner và review trigger.

### Những câu hỏi audit

| Câu hỏi | Bằng chứng |
|---|---|
| Account được tạo cho người thật/quan hệ hợp lệ? | HRIS identity/relationship và proofing record |
| Account kích hoạt trước effectiveAt? | createdAt, activeAt, JML effectiveAt |
| Baseline role có đúng? | Role mapping/policyVersion |
| Quyền nhạy cảm có approval? | Access request, approver authority |
| Có tài khoản local duplicate? | Target account inventory và identity linking |
| MFA enrollment đáp ứng chính sách? | Authenticator enrollment metadata, không log bí mật |
| Target nhận đúng quyền? | SCIM/API result + observed entitlement |

**Account đã tồn tại trước ngày bắt đầu không tự là vi phạm** nếu được chuẩn bị hợp lệ; audit phải kiểm **khi nào nó trở nên truy cập được** và policy quy định thế nào.

## 11. Audit Mover: ngăn quyền tích lũy

**Mover** đổi job role, department, manager, project, tenant hoặc loại quan hệ. Rủi ro đặc trưng là **được cấp quyền mới nhưng vẫn giữ quyền cũ**.

Ví dụ Lan từ Sales sang Finance:

| Thành phần | Trước Mover | Desired sau Mover |
|---|---|---|
| CRM SALES_READER | Có | Thu hồi khi không còn nhiệm vụ |
| CRM SALES_EXPORT | Có | Thu hồi, ưu tiên vì dữ liệu nhạy cảm |
| Finance REPORT_READER | Không | Cấp theo baseline/approval |
| Finance PAYMENT_APPROVER | Không | Chỉ sau approval và SoD check |
| SaaS local admin | Có ngoài IdP | Điều tra và gỡ nếu không còn căn cứ |

### Một audit đầy đủ sẽ kiểm

1. **Mover source event version** và effectiveAt.
2. Danh sách quyền trước thay đổi và **grant source**.
3. Desired permissions theo role mới.
4. Thời điểm thực thi **revoke old / grant new**.
5. Có cửa sổ cùng sở hữu hai quyền xung đột không?
6. SCIM group hoặc local grants nào còn sau Mover?
7. JWT/session/PAM còn claim hoặc privilege cũ không?
8. Các quyền mới có approval đúng thẩm quyền không?
9. Đã thực hiện **negative action test** cho quyền cũ chưa?
10. Finding, risk owner và SLA nếu còn tồn dư.

**Audit không kết luận Mover hoàn tất chỉ vì Finance Reader đã được cấp.** Cần chứng minh Sales Export không còn usable theo policy.

## 12. Audit Leaver: quan trọng nhất là effective denial

Khi một người **Leaver**, audit cần đo khả năng truy cập **sau effectiveAt**, không chỉ trạng thái account trong HRIS.

### Các lớp cần kiểm

| Lớp | Evidence | Giới hạn |
|---|---|---|
| **HRIS** | Leaver reason/effectiveAt/relationshipId | Event không tự cắt account |
| **IdP/Directory** | Disable account, SSO session revocation | App local sessions vẫn có thể còn |
| **SCIM/SaaS** | User active=false, group removal | App role local/direct grants có thể còn |
| **OAuth AS** | Refresh token revoke, client/session state | Access token tự chứa có thể còn hạn |
| **Resource server** | Request Deny, policy state | Cần xem coverage nhiều endpoints |
| **PAM/JIT** | Privileged grant/session termination | Terminal session độc lập có thể còn |
| **VPN/SSH/DB** | Account/key/cert/session revoke | Một số connection đang mở chưa bị ngắt |
| **Cloud IAM** | Role binding và service account access | Temporary credentials có thể còn sống |
| **Reconciliation** | Desired vs observed và test | Inventory thiếu dẫn đến kết luận hạn chế |

### Hai cột trạng thái không nên gộp

- **Workflow state:** revoke job Queued/Sent/Acknowledged/Failed.
- **Access state:** Active/Disabled/Entitlement removed/Session terminated/Action denied.

Nếu job thành công ở IdP nhưng một API key vẫn hoạt động, audit phải ghi **ResidualAccessFinding**, không đóng Leaver chỉ dựa vào IdP.

## 13. Audit identity proofing và enrollment

Audit IAM bắt đầu **trước lúc cấp quyền**. Nếu một account được gắn nhầm người, những quyền và log phát sinh sau đó có thể hợp lệ về kỹ thuật nhưng sai chủ thể.

### Identity proofing

Cần thấy:

- Nguồn dữ liệu nào được coi là **authoritative**.
- Bằng chứng xác minh cần thiết có được thu và xử lý theo policy.
- Ai thực hiện hoặc quyết định exception.
- Proofing result, assurance và thời điểm.
- Các trường hợp duplicate, merge, split identity và tái sử dụng email.
- Quyền truy cập PII của người thực hiện proofing.

Không cần và không nên sao chép toàn bộ giấy tờ danh tính vào audit log đại trà. Nên lưu **evidence reference, result và metadata tối thiểu**; dữ liệu gốc được bảo vệ trong hệ thống chuyên biệt theo retention policy.

### Authenticator enrollment

Audit sự kiện:

- Passwordless/passkey/security key/MFA factor được đăng ký hoặc xóa.
- Actor thực hiện, session assurance và step-up.
- Chính sách recovery/reset có được tuân thủ.
- Token/secret enrollment không bị log.
- Khi factor bị thay đổi bất thường, hệ thống có cảnh báo/notification và review thích hợp.

**Authenticator đã enrollment không chứng minh mọi lần đăng nhập đều đạt MFA**. Phải kiểm từng authentication/session event và assurance thực sự được sử dụng.

## 14. Audit authentication, MFA và session

Những sự kiện thường cần quan sát:

- **AuthenticationSucceeded/Failed**.
- **MFAChallengeIssued/Passed/Failed**.
- **AuthenticatorAdded/Removed**.
- **PasswordReset/RecoveryCompleted**.
- **SessionCreated/Rotated/Revoked/Expired**.
- **StepUpRequired/Completed**.
- **AccountLocked/Unlocked**.
- **RiskPolicyChanged/Blocked**.

### Metadata nên có

| Trường | Mục đích |
|---|---|
| identityId/tenantId | Nối đúng chủ thể và phạm vi |
| authEventId/sessionAuditRef | Truy vết mà không lộ cookie |
| occurredAt/auth_time | Đánh giá thời điểm xác thực |
| method/assurance | MFA/step-up theo policy |
| device reference, approximate network context | Phát hiện bất thường có giới hạn privacy |
| policy decision + reason | Vì sao Permit/Deny |
| IdP/client/applicationId | Ai phát hành hay tiêu thụ login |
| risk signal/outcome | Điều tra và monitoring |

### Thận trọng diễn giải

**AuthenticationSuccess không đồng nghĩa AuthorizationPermit.** Một user đăng nhập hợp lệ có thể bị từ chối quyền export. Ngược lại, **MFAFailed** có thể là sai thao tác hoặc tấn công, cần đối chiếu thêm nguồn bằng chứng chứ không tự kết luận người dùng ác ý.

## 15. Audit IdP, SSO và session liên kết

Trong SSO, một người có thể có **IdP/OP session và nhiều application-local sessions**.

~~~mermaid
sequenceDiagram
    participant U as User Browser
    participant IDP as IdP
    participant CRM as CRM App
    participant FIN as Finance App
    participant AUD as Audit
    U->>IDP: Login/MFA
    IDP-->>AUD: Authentication + IdP session event
    U->>CRM: SSO callback
    CRM-->>AUD: RP session created
    U->>FIN: SSO callback
    FIN-->>AUD: RP session created
    IDP-->>AUD: Global/IdP logout requested
    CRM-->>AUD: Local session revoke outcome
    FIN-->>AUD: Local session revoke outcome
~~~

### Những sự kiện phải phân biệt

1. User **đăng nhập IdP**.
2. IdP phát **federation assertion/authorization response**.
3. RP/SP tạo **local session**.
4. IdP logout/revoke session.
5. RP nhận/thực thi **federated logout**, nếu hỗ trợ.
6. App local session hoặc SaaS API token vẫn có thể còn.

**IdP báo logout thành công không chứng minh tất cả SaaS local sessions đã kết thúc**. Một audit nghiêm túc phải ghi **phạm vi và trạng thái từng tích hợp**.

### Correlation

Dùng event references, RP clientId, session audit reference, subject và request/correlation ID khi được cung cấp. Không cần đưa raw ID token, SAML assertion hay cookie vào log để liên kết.

## 16. Audit OAuth/OIDC tokens và credential lifecycle

Trong OAuth/OIDC, cần phân biệt:

| Đối tượng | Audit trọng tâm |
|---|---|
| **ID token** | RP đã validate issuer/audience/nonce và authentication context đúng? |
| **Access token** | AS phát cho client/audience/scope nào; RS kiểm gì? |
| **Refresh token** | Rotation/reuse/revocation và token family |
| **Client credentials** | Client/workload có chứng cứ xác thực gì |
| **OAuth consent/grant** | Ai/đại diện nào chấp thuận phạm vi và khi nào |
| **JWT signing key** | Key rotation, access, kid/issuer và integrity |
| **API key/PAT** | Owner, scope, expiry, revoke tại issuer/target |
| **Session cookie** | Local application session, TTL và invalidation |

### Những điểm quan trọng

- **TokenIssued** chưa có nghĩa **API action executed**.
- **TokenRevoked** tại authorization server có thể chưa khiến mọi JWT đã phát bị resource server từ chối tức thì.
- **RefreshTokenRevoked** chặn lấy token mới theo khả năng AS, nhưng access token cũ có thể còn hạn.
- **Token validation** phải xem audience, issuer, expiry, scope và authorization ở resource.
- **ID token không phải API bearer token cho mọi resource**.
- **Đã xóa credential khỏi vault** không chứng minh credential bị hủy tại SaaS/database.

### Lưu bằng chứng thay vì credential

Audit có thể ghi **clientId, token family reference, issuedAt, expiry, scope identifiers, issuer và revoke result** theo nhu cầu. Không ghi token thô hoặc private signing key.

## 17. Audit SCIM provisioning và deprovisioning

SCIM thường đồng bộ **User và Group** giữa IAM/IdP/IGA với SaaS. Audit cần kiểm:

1. **Source identity/relationship** và desired target state.
2. **Target User ID**, Group ID và tenant được map đúng.
3. Operation type: POST/PUT/PATCH/DELETE, nội dung nghiệp vụ đã thay đổi.
4. **HTTP response**, SCIM error và khả năng retry/idempotency.
5. **Group.members** sau thao tác, không chỉ User.groups read-only.
6. **Account active** hoặc trạng thái ứng dụng đã được readback.
7. Local/direct grants ngoài SCIM có được inventory không.
8. Session/token/API key còn sống có được xử lý đúng không.
9. Event version khi Mover/Leaver đan xen.
10. Finding khi target không thể kiểm chứng.

### Ví dụ tình huống timeout

Connector gửi PATCH gỡ thành viên nhóm, nhưng hết timeout trước khi nhận HTTP response. Log chỉ ghi **TIMEOUT**, không được suy là chắc chắn thất bại hay chắc chắn thành công. Thực hiện **readback** trước khi retry để tránh thao tác không cần thiết hoặc state drift.

### SCIM User.active không phải authorization engine

Một ứng dụng có thể coi active=false là chặn account, nhưng **mức độ vô hiệu local session/token và quyền qua các đường khác phụ thuộc service provider**. Audit phải xác định hành vi thực tế và các API/connector cần thêm.

## 18. Audit RBAC, ABAC, PBAC và hiệu lực permission

**Role-based Access Control (RBAC)** gắn quyền với role; **Attribute-based Access Control (ABAC)** dùng thuộc tính subject/resource/action/context; **Policy-based Access Control (PBAC)** mô tả quyết định theo tập policy.

### Những lớp audit

| Lớp | Cần ghi nhận |
|---|---|
| **Role definition** | Role cấp những permission nào và ai quản lý? |
| **Role assignment** | Ai gán/thu hồi, căn cứ từ đâu, expiry nào? |
| **Group hierarchy** | Có nested memberships và quyền kế thừa không? |
| **Direct grant** | Có permission ngoài catalog/IGA không? |
| **ABAC attributes** | Nguồn attribute, độ tươi, integrity và version |
| **Policy evaluation** | Subject/action/resource/context, policyVersion, decision |
| **PEP enforcement** | Hành động thật có bị Permit/Deny đúng không? |
| **Resource scope** | Tenant, project, data classification và object ownership |

### Một ví dụ

Lan có role **FINANCE_READER**, nhưng **report.export** chỉ được phép khi có approval, MFA hiện hành và scope tài nguyên đúng. Nếu API trả Permit dựa duy nhất vào role name, log **role check passed** không chứng minh ABAC guard đã được áp.

### Effective permissions

Audit cần tính quyền từ **role inheritance, nested group, direct grants, resource policies, JIT eligibility/activation và local accounts**, không chỉ chụp danh sách role trong IdP.

**Một lần RoleRemoved không chứng minh action đã bị thu hồi nếu quyền vẫn được cấp từ đường khác.**

## 19. Audit access request và approval workflow

Một yêu cầu cấp quyền thường có các giai đoạn:

~~~mermaid
flowchart TD
    REQ[Access request created] --> VAL[Identity, purpose, scope validated]
    VAL --> SOD[SoD / risk / policy check]
    SOD --> APP[Manager / resource owner approval]
    APP --> DEC{Approve / Deny / Need info}
    DEC -->|Approve| PROV[Provision or JIT activation]
    DEC -->|Deny| END[Closed denied]
    DEC -->|Need info| VAL
    PROV --> READ[Target readback]
    READ --> CLOSE[Verified or remediation finding]
~~~

### Câu hỏi audit thiết yếu

- Beneficiary có **quan hệ làm việc/sponsor hợp lệ**?
- Request có **business reason, resource scope và expiry**?
- Người duyệt có **quyền theo resource/tenant**?
- Có **self-approval hoặc SoD conflict** bị cấm không?
- Approval còn giá trị sau một **Mover/Leaver event mới hơn** không?
- Provisioning có dùng đúng **approved entitlement**?
- Có thay đổi phạm vi quyền sau approval mà không duyệt lại?
- Target readback có xác nhận quyền đã được cấp đúng?

**Approval là một quyết định quản trị**, không phải bằng chứng việc cấp quyền đã thực sự xảy ra. Và một approval đã được duyệt từ trước **không vượt được chính sách JML mới hơn**.

## 20. Audit access review và entitlement certification

**Access review** là quá trình chứng nhận quyền đang tồn tại, nhưng audit phải đánh giá **chất lượng quyết định** chứ không chỉ tỷ lệ click hoàn thành.

### Một review item nên truy vết được

- Beneficiary, target account, entitlement và **effective permission**.
- Grant provenance: role, group, direct grant, request hay exception.
- Reviewer identity, authority, delegation và SoD.
- Snapshot as-of, target observedAt và policy/source version.
- Decision: RETAIN, REVOKE, MODIFY, NEED_MORE_INFO, ESCALATE.
- Reason/rationale và evidence reviewer đã được cung cấp.
- Fulfillment: các thay đổi đã gửi đi.
- Readback: quyền đích sau decision.
- Finding khi còn partial, overdue hoặc unverified.

### Ba lỗi đánh giá thường gặp

1. **Bulk certify mọi entitlement** mà không giải thích permission thật.
2. Đóng campaign khi review collection đã xong nhưng **REVOKE chưa được thực thi**.
3. Dùng RETAIN từ snapshot trước Mover để **tái cấp quyền đã bị JML gỡ**.

Một kết luận audit nên tách **review completion rate** khỏi **verified remediation rate** và chỉ rõ coverage.

## 21. Audit Separation of Duties (SoD)

**Segregation of Duties** yêu cầu các chức năng có rủi ro được thực hiện bởi những chủ thể độc lập hoặc theo kiểm soát bổ sung.

Ví dụ:

- **vendor.create** và **vendor.payment.approve**.
- **invoice.create** và **invoice.approve trên cùng invoice**.
- **user.assignRole** và **certify own grant**.
- **release.author** và **approve own release**.

### Audit static và dynamic SoD

| Loại | Bằng chứng chính |
|---|---|
| **Static SoD** | Assignment/entitlement sets, scope overlap, rule version |
| **Dynamic SoD** | Actor history, resource state, createdBy/approvedBy, runtime decision |
| **Cross-system SoD** | Person-account linking, cloud/SaaS/direct grants |
| **Exception/compensating control** | Risk owner, scope, expiry, approval, monitoring |

Một role name không đủ để phát hiện toxic combination. Audit cần **effective action set** theo scope và **history trên từng transaction** khi policy yêu cầu.

### Exception không phải cách bỏ qua chính sách

Nếu tổ chức cho phép ngoại lệ, phải có **risk owner, reason, thời hạn, phạm vi, compensating controls và bằng chứng kiểm tra**. Trạng thái **EXCEPTION_REQUESTED** chưa có nghĩa được phép thực thi.

## 22. Audit PAM, JIT, break-glass và đặc quyền

Quyền đặc quyền tạo tác động cao nên audit cần sâu hơn “user đã đăng nhập”.

| Đối tượng | Bằng chứng |
|---|---|
| **PIM eligibility** | Ai có thể xin kích hoạt role admin? |
| **JIT activation** | Ai kích hoạt, approval/step-up, scope, TTL |
| **Privileged session** | Broker/session ID audit, commands, termination |
| **Root/admin credential checkout** | Người nhận, approval, rotation sau dùng |
| **Break-glass account** | Lý do khẩn cấp, người dùng, cảnh báo, post-review |
| **Cloud admin role** | Role binding, trust, target permissions |
| **Emergency policy override** | Actor, risk owner, effective duration |

**Eligible không phải Active**. Audit cần phân biệt quyền có thể kích hoạt, quyền đang có hiệu lực, session đã mở và token/credential còn sống.

### Ví dụ

PAM cho admin role thời hạn 30 phút. Đến phút 31, event **GrantExpired** xuất hiện, nhưng phiên SSH đã mở vẫn thực thi được lệnh. Audit phải ghi **privileged session residual access**, không tự đóng vì grant metadata hết hạn.

## 23. Audit non-human identity, service account và machine identity

Non-human identities bao gồm **service account, bot, workload identity, CI/CD principal, device identity và machine certificate**. Chúng không có manager trong HRIS theo cùng mô hình nhân viên, nhưng phải có **owner team, purpose và lifecycle**.

### Kiểm tra tối thiểu

1. Workload/device có **immutable ID, registry entry và owner**?
2. Credential nào đang dùng: **managed identity, federation, API key, password, certificate**?
3. Ai có quyền **rotate, reissue, revoke hoặc change trust policy**?
4. Quyền được giới hạn đúng **environment, tenant, action và resource**?
5. Có long-lived/static credential không cần thiết?
6. Account đã retire nhưng role/secret còn active?
7. CI jobs từ fork/untrusted workflow có thể lấy production credentials không?
8. Owner human Mover/Leaver có được thu hồi quyền cá nhân và chuyển giao owner?
9. Logs có tách **workload principal** khỏi **human actor** đã khởi phát automation?
10. Target readback và runtime action có phù hợp desired state?

### Một lỗi hay gặp

Một service principal có **OWNER đã nghỉ việc** nhưng workload vẫn hoạt động hợp lệ. Audit không nên khuyến nghị xóa bừa service production. Cần **chuyển ownership, kiểm secrets người cũ biết, kiểm runtime grants và thu hồi human access**, rồi xem workload có thực sự cần quyền đó không.

## 24. Audit credential vault, key và certificate

Credential và token có nhiều vòng đời tách biệt:

| Secret/credential | Cần kiểm tra |
|---|---|
| **Vault token/lease** | Ai được lấy, TTL, scope, revoke status |
| **Static DB password** | Ai có thể đọc, rotation, target disable |
| **Dynamic DB credential** | Lease và target user/session còn không |
| **SaaS API key/PAT** | Owner, scope, last use, issuer revoke |
| **OAuth refresh token** | Token family, rotation, reuse và revoke |
| **TLS private key** | Key custody, certificate issuance, rotation |
| **Machine certificate** | Issuer, SAN, EKU, expiry, revocation/trust |
| **Cloud temporary credential** | Trust assumption, role, target validity |
| **Break-glass secret** | Custody, usage, dual control, post-review |

### Mất quyền ở vault khác mất quyền tại target

Nếu người nghỉ việc đã **đọc API key** rồi chép ra ngoài, thu hồi quyền **read secret** tại vault chỉ ngăn đọc mới. Bản copy vẫn dùng được nếu SaaS chấp nhận key. Audit cần tìm **target revoke/rotate** và bằng chứng API không còn Permit.

### Certificate revocation có giới hạn

Một certificate được CA ghi revoked không tự chấm dứt mọi **TLS session, ứng dụng legacy hoặc relying party không kiểm revocation**. Audit phải mô tả cơ chế enforcement, CRL/OCSP khi dùng, TTL và khả năng chặn ở PEP.

## 25. Event schema và nguyên tắc ghi audit có cấu trúc

Để nối dữ liệu nhiều hệ thống, audit events nên có **schema có version, field names nhất quán và meaning rõ**.

Ví dụ phân loại:

~~~text
Identity:
  IdentityCreated
  RelationshipActivated
  RelationshipMoved
  RelationshipTerminated

Authentication:
  AuthenticationSucceeded
  AuthenticationFailed
  SessionCreated
  SessionRevoked
  AuthenticatorAdded

Access Governance:
  AccessRequested
  AccessApproved
  AccessDenied
  ReviewDecisionRecorded
  SoDConflictDetected

Provisioning:
  EntitlementGrantRequested
  EntitlementGrantAcknowledged
  EntitlementGrantObserved
  EntitlementRevokeRequested
  EntitlementRevokeAcknowledged
  EntitlementRevokeVerified

Authorization:
  PolicyDecisionEvaluated
  ResourceActionPermitted
  ResourceActionDenied

NonHuman:
  WorkloadRegistered
  CredentialIssued
  CredentialRevoked
  WorkloadRetired

Control:
  AuditPolicyChanged
  AuditSinkUnavailable
  ReconciliationFindingOpened
  ReconciliationFindingClosed
~~~

Tên event trên là **quy ước minh họa**, không phải danh sách chuẩn được mọi sản phẩm hỗ trợ. Điểm quan trọng là tránh tên chung chung như **SUCCESS** mà thiếu **operation, subject, resource và result**.

### Schema evolution

- Có **schemaVersion**.
- Dùng eventType ổn định; không thay nghĩa trường mà không version.
- Phân biệt **null / unknown / not applicable**.
- Không đặt email hoặc display name làm khóa duy nhất.
- Có bảng mapping từ **vendor log** sang canonical event.
- Kiểm unit và timezone của timestamp.
- Không bỏ qua một sự kiện chỉ vì bản ghi có field mới.

## 26. Correlation và causation: nối log từ HRIS tới API

Một sự kiện JML thường tạo nhiều tác vụ bất đồng bộ. Cần hai loại liên kết:

- **correlationId:** nối các sự kiện thuộc cùng workflow/yêu cầu nghiệp vụ.
- **causationId / sourceEventId:** chỉ ra event hoặc quyết định nào gây ra thao tác tiếp theo.

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as IAM / IGA
    participant SCIM as SCIM Connector
    participant APP as Target App
    participant AUD as Audit Store
    HR->>IAM: Mover event E1, sourceVersion 7
    HR-->>AUD: E1
    IAM->>IAM: Compute desired grants
    IAM-->>AUD: Decision D1 causedBy E1
    IAM->>SCIM: Revoke group, operation O1
    SCIM-->>AUD: O1 dispatch/ack causedBy D1
    SCIM->>APP: PATCH /Groups / membership
    APP-->>SCIM: Response
    SCIM-->>AUD: Target operation response
    IAM->>APP: Readback effective grants
    APP-->>IAM: Current state
    IAM-->>AUD: Verification V1 causedBy O1
~~~

### Không chỉ dựa vào timestamp để ghép

Hai provisioning jobs có thể chạy cùng lúc cho một người hoặc cùng target. Chỉ ghép theo **subjectId + phút gần nhất** có thể liên kết sai request. Cần request/operation IDs và version.

### Mapping nhiều hệ thống

HRIS **personId** và SaaS **targetAccountId** cần được liên kết qua identity mapping có thẩm quyền. **Email đổi, username tái sử dụng hoặc tenant khác** phải không làm ghép nhầm hai người.

## 27. Thời gian: occurredAt, effectiveAt, processedAt và observedAt

Trong hệ thống phân tán, “khi nào?” có nhiều câu trả lời.

| Thời điểm | Ý nghĩa |
|---|---|
| **occurredAt** | Sự kiện phát sinh ở nguồn |
| **effectiveAt** | Chính sách hoặc quan hệ có hiệu lực từ khi nào |
| **ingestedAt** | Hệ thống audit nhận event khi nào |
| **processedAt** | Workflow/connector xử lý khi nào |
| **approvedAt** | Reviewer/approver quyết định khi nào |
| **fulfilledAt** | Thao tác cấp/gỡ được thực thi khi nào |
| **observedAt** | Target state được đọc khi nào |
| **verifiedAt** | Bằng chứng đủ để xác nhận điều kiện kiểm toán lúc nào |
| **expiresAt** | Token/grant/session kết thúc theo thiết kế khi nào |

### Ví dụ Leaver đến muộn

HRIS ghi Leaver **effectiveAt=16:00**, nhưng webhook IAM nhận **16:03**, connector gỡ group **16:05**, và CRM cắt session **16:07**.

Nếu audit chỉ ghi **processedAt=16:05** sẽ bỏ qua **7 phút nguy cơ truy cập sau effectiveAt**. Cần timeline theo nhiều mốc và đánh giá SLA theo chính sách, không tự kết luận đó là vi phạm nếu chưa biết quy định và khả năng quan sát.

### Đồng hồ và thứ tự sự kiện

- Chuẩn hóa timestamp với timezone/UTC phù hợp.
- Đồng bộ clock và ghi nhận clock-skew khi phát hiện.
- Không giả định event ingest order là source order.
- Dùng **source version/sequence, idempotency và fencing** cho trạng thái JML quan trọng.
- Nếu timestamp mâu thuẫn, ghi uncertainty thay vì bịa timeline chính xác.

## 28. Data provenance: bằng chứng đến từ đâu và đáng tin đến mức nào?

Một event chỉ có giá trị khi biết **nguồn, tính xác thực và ngữ cảnh**.

| Nguồn | Chứng minh được | Không tự chứng minh |
|---|---|---|
| **HRIS authoritative record** | Employment/relationship state theo nguồn | SaaS session đã đóng |
| **IAM desired-state log** | Policy đề xuất quyền nào | Target thật đã áp |
| **Approval system** | Ai approved/denied | Grant đã tồn tại |
| **SCIM connector log** | Operation sent/response | Effective permission đã bị cắt toàn bộ |
| **SaaS entitlement readback** | Grant hiện diện/không hiện diện tại thời điểm đọc | Mọi token/session đều đã vô hiệu |
| **API authorization log** | Action cụ thể được Permit/Deny | Các endpoints khác cũng kiểm đúng |
| **PAM session record** | Privileged action trong phiên brokered | Credentials ngoài broker không còn |
| **Vault audit** | Principal đã lấy/generate secret | Secret chưa bị copy |
| **SIEM correlation** | Liên kết/alert theo rule | Kết luận pháp lý hoặc sự thật đầy đủ |

### Reliability của evidence

Cân nhắc **source authority, timestamp, coverage, integrity, collection error, identity mapping và policy version**. Một screenshot có thể hỗ trợ audit, nhưng **không có thông tin nguồn/thời điểm** thường yếu hơn dữ liệu API được thu có kiểm soát và đối chiếu.

**Không nên xem log nội bộ là không thể giả mạo chỉ vì nằm trong SIEM**. Cần bảo vệ pipeline và access tới log.

## 29. Kiến trúc thu thập và phân phối audit events

~~~mermaid
flowchart TD
    HR[HRIS / Contract Events] --> COL[Log Agents / Event Collectors]
    ID[IdP / SSO / MFA] --> COL
    IAM[IAM / SCIM / PAM / Vault] --> COL
    AP[Applications / APIs / Cloud] --> COL
    COL --> SAN[Schema Validation + Redaction]
    SAN --> BUS[Durable Event Transport]
    BUS --> RAW[(Protected Raw Evidence)]
    BUS --> NORM[Canonical Event Processing]
    NORM --> STORE[(Searchable Audit Store)]
    STORE --> DET[Detection / SIEM]
    STORE --> RECON[Reconciliation / Audit Queries]
    RAW --> AUDIT[Audit Evidence Review]
    RECON --> AUDIT
    DET --> RESP[Incident / Remediation]
~~~

### Những đặc tính cần có

1. **TLS/mTLS hoặc kênh xác thực** từ nguồn tới collector.
2. **Authorization và integrity** cho event producer; chống nguồn giả.
3. **Schema validation**, nhận diện event thiếu trường quan trọng.
4. **Secret redaction** trước khi ghi hoặc chuyển tiếp.
5. **Buffering, backpressure, retry** khi sink unavailable.
6. Dùng **eventId** và deduplication để chống ghi lặp.
7. Monitoring **dropped events, lag và collection coverage**.
8. Phân tách **raw evidence** khỏi dữ liệu đã chuẩn hóa để giữ provenance khi cần.
9. **Role-based access** cho người tìm kiếm hoặc xuất log.
10. Retention, archive và deletion theo policy/pháp lý áp dụng.

### Tránh hệ thống ghi log trở thành điểm rò rỉ

Các audit events chứa danh tính, IP, device, resource IDs và hành động nhạy cảm. Collector hoặc dashboard có quyền rộng có thể trở thành nguồn lộ dữ liệu lớn. Bảo vệ audit pipeline là một phần của IAM audit.

## 30. Bảo đảm tính toàn vẹn và chống sửa audit log

Một bản ghi log có thể bị thay đổi bởi người có quyền vận hành, attacker hoặc cấu hình lỗi. Để nâng giá trị chứng cứ, có thể dùng:

- **Append-only storage** và quyền không cho sửa/xóa tùy tiện.
- **WORM/retention lock** khi hệ thống và policy hỗ trợ.
- **Digital signatures/MACs** trên batch hoặc event theo trust model.
- **Hash chaining** hoặc log transparency mechanism khi cần.
- **Independent log export** tới vùng bảo vệ tách khỏi hệ thống bị kiểm toán.
- **Access controls, separation of duties và audit của chính thao tác quản lý log**.
- **Clock synchronization, schema/provenance và immutable evidence references**.
- Monitoring mất log, gap event sequence và chỉnh policy audit.

### Hash chain minh họa

~~~text
H0 = Hash(initial_metadata)
H1 = Hash(H0 || canonical_event_1)
H2 = Hash(H1 || canonical_event_2)
H3 = Hash(H2 || canonical_event_3)
~~~

Mô hình này giúp nhận ra **sửa đổi bản ghi trong chuỗi nếu checkpoint/head hash được bảo vệ độc lập**. Nếu attacker sửa được toàn bộ chain cùng checkpoint mà không có anchor tin cậy, chỉ hash chain nội bộ chưa đủ. Kỹ thuật hashing cũng **không chứng minh event được ghi là đúng sự thật** khi producer đã bị chiếm.

### Audit log của chính audit system

Cần ghi:

- Ai đã thay đổi retention/audit policy?
- Ai được phép export/download bằng chứng?
- Có ai tắt hoặc giảm log level không?
- Hệ thống đã mất collector, clock, signing key hay storage chưa?
- Ai thay đổi quyền của SIEM/dashboard?
- Có truy vấn bất thường nhằm xem log người dùng nhạy cảm không?

**Đối tượng có thể che giấu dấu vết không nên được toàn quyền tự phê duyệt thay đổi audit controls** khi SoD policy yêu cầu độc lập.

## 31. Quyền riêng tư, giảm thiểu dữ liệu và retention

IAM audit xử lý dữ liệu cá nhân, hành vi truy cập và những thông tin có thể tiết lộ cấu trúc hệ thống. **Thu càng nhiều không đồng nghĩa càng an toàn**.

### Nguyên tắc thực hành

1. **Purpose limitation:** xác định audit/incident/compliance purpose cụ thể.
2. **Data minimization:** thu đủ để kiểm soát, không lưu raw secrets.
3. **Need-to-know:** chỉ auditor/Security/owner được phép xem phần phù hợp.
4. **Pseudonymization** khi phù hợp, nhưng giữ mapping ID có thẩm quyền trong hệ thống bảo vệ.
5. **Retention schedule** theo loại event, rủi ro và yêu cầu áp dụng; không có một thời hạn chung cho mọi tổ chức.
6. **Deletion/archival procedure** tuân theo policy và legal hold khi có.
7. **Cross-border/third-party sharing** phải qua đánh giá và kiểm soát phù hợp.
8. **Access logs of audit logs:** kiểm ai đang xem/export bằng chứng.
9. **Avoid secondary uses:** không tự dùng dữ liệu login để đánh giá năng suất cá nhân ngoài mục đích được phép.
10. **Secure exports:** giảm field, giới hạn người nhận và thời gian truy cập.

### Điều không nên log

- Raw password hoặc password reset secret.
- Session ID/cookie có thể tái sử dụng.
- OAuth access/refresh token.
- Private keys, API keys, OTP/MFA recovery codes.
- Toàn bộ giấy tờ proofing nếu không cần.
- Full payload chứa dữ liệu khách hàng hoặc nội dung nhạy cảm mà audit chỉ cần metadata.

### Mâu thuẫn giữa immutable audit và quyền xóa dữ liệu

Nếu có nghĩa vụ xóa hoặc giới hạn dữ liệu, cần **kiến trúc retention và legal hold hợp lệ**; không hứa có thể sửa/xóa một immutable record bất cứ lúc nào. Có thể dùng tokenization, cryptographic erasure hoặc tách mapping PII tùy yêu cầu, nhưng phải đánh giá hậu quả đối với khả năng kiểm chứng và chính sách áp dụng.

## 32. Coverage và giới hạn của kết luận audit

Một audit IAM có thể bỏ sót:

- Local accounts của ứng dụng legacy.
- Quyền direct grant ngoài IdP/IGA.
- Nested groups và role hierarchy không được export.
- Temporary cloud roles, API keys, PAT hoặc service principals.
- SaaS sessions chưa có logout API.
- OAuth JWT vẫn được RS chấp nhận theo cache.
- Thao tác trên WebSocket/SSH/DB session dài.
- External contractor/guest nằm ở tenant khác.
- Logs mất do collector outage.
- Data plane không ghi object-level authorization decisions.

### Không tuyên bố quá mức

Thay vì nói **“Tất cả quyền đã thu hồi”**, một báo cáo chính xác hơn có thể là:

> Target CRM User không còn membership SALES_EXPORT và API report.export từ tài khoản được kiểm đã trả Deny lúc 16:07; chưa xác minh được các PAT do ứng dụng legacy phát vì connector chưa có inventory API.

Mức kết luận phải khớp **coverage, evidence freshness và độ tin cậy của phép kiểm**.

### Sampling và mức đảm bảo

Audit có thể dùng kiểm tra toàn bộ population, sampling theo risk hoặc kiểm tra trọng điểm. Khi dùng sample, cần nêu **population, cách chọn mẫu, thời gian và giới hạn suy rộng**; không biến kết quả vài tài khoản thành bảo đảm cho mọi account.

## 33. Phát hiện an ninh từ audit events

Audit trail cũng là nguồn cho detection engineering, nhưng alert không thay kiểm toán hiệu quả kiểm soát.

| Detection use case | Dấu hiệu | Hành động |
|---|---|---|
| **Privileged grant outside workflow** | Admin role được gán không có approval reference | Alert, xem grant provenance |
| **Self-approval** | Requester cũng approve grant của mình khi policy cấm | SoD finding |
| **Leaver residual access** | Action Permit sau effectiveAt | Incident/containment |
| **Impossible privilege chain** | Create user → grant admin → disable audit | Điều tra quyền kiểm soát |
| **MFA reset anomaly** | Factor removed rồi admin action bất thường | Step-up/incident |
| **Secret exfiltration suspicion** | Workload đọc hàng loạt secrets lạ | Revoke/limit vault role |
| **SCIM deprovision failure** | Target error/timeout kéo dài | Remediation/negative test |
| **Unowned service identity** | Privileged workload không owner | Assign owner/restrict |
| **Audit logging disabled** | Tắt sink/retention, giảm scope | High-priority security alert |
| **Bulk certification anomaly** | Manager retain nhiều quyền admin rất nhanh | Review quality investigation |
| **Stale grant reappears** | Regrant sau JML revoke với sourceVersion cũ | Fencing incident |
| **Cross-tenant denial pattern** | Requests tới resource tenant khác | Điều tra mapping/abuse |

### Detection phải có context

Một login từ địa chỉ mới có thể là VPN/roaming hợp lệ; một service đọc nhiều secrets có thể là rotation job được duyệt. Cần **đánh giá business context, policy, workload purpose và false positives**, không tự suy kết luận ác ý từ một log.

## 34. Audit queries và truy vấn phân tích minh họa

Với canonical event store, có thể đặt câu hỏi như:

- Những **Leaver** nào có action Permit sau effectiveAt?
- Những role admin nào được gán **không có approval**?
- Những review item REVOKE nào chưa có **target readback**?
- Những workload **RETIRED** nào vẫn được STS cấp credential?
- Những connector nào có tỷ lệ timeout hoặc unknown outcomes cao?
- Những account ở SaaS không map được tới **person/workload identity** nào?

### Ví dụ SQL phân tích Leaver residual access

~~~sql
-- Schema và cú pháp là minh họa, không áp dụng trực tiếp mọi kho log.
SELECT
    a.subject_id,
    a.target_system,
    a.action,
    a.occurred_at,
    l.effective_at
FROM authorization_events AS a
JOIN relationship_terminations AS l
  ON a.subject_id = l.subject_id
 AND a.relationship_id = l.relationship_id
WHERE a.decision = 'PERMIT'
  AND a.occurred_at >= l.effective_at
  AND a.occurred_at < l.effective_at + INTERVAL '7 days';
~~~

Đây là ví dụ **PostgreSQL-like**, không đại diện mọi SQL dialect và mọi nguồn sự kiện.

### Cần xử lý ngoại lệ khi phân tích

- Dùng đúng **relationshipId** nếu một person có nhiều quan hệ.
- Actor/workload thay mặt người khác cần được liên kết đúng.
- Đồng bộ timezone và clock skew.
- Không tin claim **decision=PERMIT** nếu đó là kết quả policy simulation, không phải enforcement.
- Một operation có nhiều log duplicate cần deduplicate.
- Event đến muộn cần có cửa sổ watermark/reprocessing phù hợp.
- Các ngoại lệ nghiệp vụ và phạm vi access phải được xét theo policy.
- Chưa có event không có nghĩa không có action nếu **coverage thiếu**.

## 35. Reconciliation và bằng chứng quyền tồn dư

**Reconciliation** so sánh **desired state** theo JML/approval/policy với **observed state** ở target.

### Một mô hình tìm sai lệch

~~~text
desired = deriveAllowedGrants(
    identity.relationships,
    jobRoles,
    currentApprovals,
    exceptions,
    currentPolicy
)

observed = collectEffectiveAccess(
    targetAccounts,
    directGrants,
    groupHierarchy,
    resourcePolicies,
    activeSessions,
    temporaryCredentials
)

unexpected = observed - desired
missing = desired - observed

for each unexpected:
    createFinding(
        subject,
        target,
        sourceGrant,
        risk,
        owner,
        dueAt,
        evidenceRefs
    )
~~~

Giả mã chỉ thể hiện ý tưởng. **Set subtraction đơn giản chưa thể mô hình đầy đủ time/conditions/deny precedence/SoD**, nên implementation thật phải tính **effective permissions** theo semantics đích.

### Cách đóng finding

Một finding nên có:

1. Dữ liệu sai lệch được xác minh.
2. Owner/remediation plan và deadline.
3. Thao tác revoke/modify hoặc exception có thẩm quyền.
4. Target state readback sau xử lý.
5. Negative authorization test nếu rủi ro yêu cầu.
6. Tình trạng token/session/connection liên quan.
7. Audit evidence reference và người chấp thuận closure.

**Không đóng finding chỉ vì ticket của connector chuyển Done**. Closure phải phản ánh đúng điều kiện đã kiểm.

## 36. Event ordering, retry, duplicate và stale decision

Dòng sự kiện IAM có thể đến muộn hoặc lặp do webhook, queue và connector retry.

| Tình huống | Rủi ro đối với audit | Kiểm soát |
|---|---|---|
| **Duplicate event** | Đếm thừa grant/revoke | Event ID/deduplication |
| **Out-of-order** | Mover cũ ghi đè Leaver mới | Source version và event fencing |
| **Timeout unknown outcome** | Báo Failed dù target đã thay đổi | Readback trước retry |
| **Source clock skew** | Timeline sai | Multiple timestamps, clock monitoring |
| **Partial failure** | Một target gỡ, target khác còn | Per-target outcome/finding |
| **Delayed ingestion** | Alert/truy vấn thiếu dữ liệu mới | Ingestion lag/watermark |
| **Log loss** | Sai kết luận “không có sự kiện” | Gap detection, durable transport |
| **Rollback** | Phục hồi role/token đã revoke | Desired state version check |
| **Rejoiner** | Dùng lại account/email nhầm role cũ | Stable IDs và relationshipVersion |
| **Concurrent decisions** | Approval/revoke chồng nhau | Conflict handling và policy revalidation |

### Giả mã kiểm audit một quyết định revoke

~~~text
function verifyRevocation(item, decision):
    if not validDecisionAuthority(decision.reviewer, item):
        return FINDING_UNAUTHORIZED_DECISION

    current = loadAuthoritativeLifecycle(item.subjectId)
    if newerLifecycleEvent(current, decision.sourceVersion):
        return REEVALUATE_CURRENT_STATE

    observed = readTargetEffectivePermissions(
        item.targetAccountId,
        item.entitlement,
        item.resourceScope
    )

    if observed.unavailable:
        return FINDING_UNVERIFIED_TARGET

    if observed.permissionStillEffective:
        return FINDING_RESIDUAL_ACCESS

    if item.riskRequiresRuntimeTest:
        result = safeNegativeAuthorizationTest(item)
        if result != DENY:
            return FINDING_RUNTIME_ACCESS_STILL_PERMITTED

    return VERIFIED_WITHIN_TESTED_COVERAGE
~~~

**Đây là giả mã**. Một permission bị gỡ khỏi role A nhưng vẫn có từ group B cần được xem **vẫn effective**. Một quyết định audit không tự sửa role; remediation cần workflow riêng và kiểm rủi ro của thao tác.

## 37. Audit chất lượng dữ liệu danh tính và account mapping

Một hệ thống IAM có thể chứa dữ liệu sai dẫn tới log “đúng kỹ thuật, sai chủ thể”.

### Những vấn đề cần phát hiện

- **Duplicate identity**: một người có hai person IDs không được liên kết.
- **Merged identity sai**: hai người bị gộp quyền hoặc lịch sử.
- **Username/email reuse**: account cũ gắn nhầm người mới.
- **Orphan account**: account ở target không có owner/relationship hợp lệ.
- **Unmapped workload**: service principal không có registry entry.
- **Wrong tenant**: assignment ở tenant không đúng.
- **Stale job/department**: policy tính role theo HRIS field cũ.
- **Group mapping drift**: nhóm IdP đổi semantics ở SaaS.
- **Missing grant provenance**: không tìm được request/baseline/exception.
- **Broken correlation**: event bị nối nhầm do thiếu immutable ID.

### Tại sao không thể audit chỉ bằng email?

Một email có thể bị đổi khi nhân viên chuyển tên, đổi domain, hoặc tái sử dụng sau khi người khác nghỉ. Audit nên gắn **identity ID bền vững** và **target account ID cụ thể**, kèm khoảng thời gian hiệu lực của mapping. Tránh suy ra người dùng chỉ từ display name.

## 38. Các chỉ số đánh giá hiệu quả audit IAM

| Metric | Ý nghĩa | Giới hạn |
|---|---|---|
| **Audit event coverage** | Tỷ lệ hệ thống/loại action có log | Có log chưa chắc đủ field |
| **Identity mapping coverage** | Tỷ lệ target accounts liên kết được identity | Mapping sai vẫn có thể báo 100% |
| **JML processing latency** | Thời gian từ source event tới xử lý | Khác runtime revoke latency |
| **Leaver residual access window** | Khoảng thời gian quyền còn Permit sau effectiveAt | Cần chứng cứ target |
| **Verified revocation rate** | Revoke có target readback/test đạt | Không được tính HTTP ack là verify |
| **Access review completion** | Review items có quyết định hợp lệ | Không phản ánh remediation |
| **Review remediation closure** | REVOKE/MODIFY đã khắc phục | Cần đọc hiệu lực quyền |
| **Privileged access coverage** | Admin/JIT/PAM events được kiểm | Có thể thiếu direct grants |
| **SoD conflicts detected** | Toxic combinations được phát hiện | Phụ thuộc độ phủ rule |
| **Orphan accounts/identities** | Tài khoản không owner/căn cứ | Cần phân biệt service hợp lệ |
| **Authentication anomaly rate** | Login/MFA unusual events | Có false positives |
| **Audit ingestion lag** | Độ trễ event tới SIEM/store | Ảnh hưởng timeline và alert |
| **Dropped/invalid event rate** | Mất hoặc lỗi schema | Tác động reliability |
| **Policy changes with approval** | Thay đổi nhạy cảm có review | Approval không tự chứng minh policy an toàn |
| **Evidence freshness** | Tuổi dữ liệu target/source khi audit | Snapshot cũ có thể gây sai |
| **Open high-risk findings** | Những rủi ro chưa xử lý | Phải có owner và SLA |

### Tránh KPI hình thức

Một campaign **100% review completed** nhưng 20 quyền admin vẫn còn sau REVOKE không phải kết quả kiểm soát thành công. Metrics nên ưu tiên **khả năng chứng minh giảm quyền trái phép**, không chỉ số thao tác hành chính.

## 39. Kiểm thử hệ thống audit IAM

| Test case | Kịch bản | Kết quả mong đợi |
|---|---|---|
| **Joiner** | Account tạo đúng người và role | Chuỗi source → approval → provision → readback |
| **Mover** | Sales → Finance | Ghi quyền cũ bị gỡ và quyền mới được cấp |
| **Leaver** | Disable IdP nhưng SaaS token còn | Finding residual access |
| **Rejoiner** | Cùng email, relationship mới | Không nối sai quyền lịch sử |
| **Multiple relationships** | Một quan hệ hết, quan hệ kia còn | Đúng relationship scope |
| **Self-approval** | User approve own admin request khi cấm | SoD finding và Deny |
| **Bulk review** | Manager certify role nhạy cảm hàng loạt | Có audit reason, risk flag |
| **SCIM timeout** | PATCH chưa biết outcome | Không tự báo verified; readback |
| **Nested groups** | Gỡ direct role, nested role vẫn cấp quyền | Effective permission vẫn bị phát hiện |
| **JWT stale claim** | Role đã revoke, token còn hạn | Audit/runtime kiểm action Deny theo policy |
| **PAM expiry** | Admin grant hết nhưng SSH session còn | Phát hiện session residual |
| **Workload retire** | Service principal vẫn có cloud role | Finding |
| **Untrusted CI** | Fork job lấy production token | Deny và ghi action |
| **Secret leakage** | Raw token xuất hiện trong log | Redaction/test ngăn lưu |
| **Wrong tenant** | Account A truy cập resource B | Deny + auditable target |
| **Out-of-order JML** | Mover event cũ đến sau Leaver | Version/fencing chống regrant |
| **Duplicate event** | Queue gửi lại cùng eventId | Không đếm/thao tác nhầm |
| **Clock skew** | Producer lệch clock | Timeline có error metadata |
| **Audit sink outage** | Collector không nhận được log | Buffer/gap alert; không silently drop |
| **Log tampering** | Thử sửa/xóa bản ghi | Detect hoặc chặn theo thiết kế |
| **Unauthorized audit read** | User khác xem log người dùng | Deny |
| **Evidence export** | Auditor tải dữ liệu | Đúng permission, redaction và audit |
| **Retention expiry** | Bản ghi tới hạn lưu | Xử lý theo retention/legal hold policy |
| **Policy change** | Admin tắt logging | Approval/audit/alert theo risk |
| **Negative runtime test** | Grant bị revoke nhưng API vẫn Permit | Không đóng finding |
| **Partial coverage** | SaaS không có entitlement API | Báo unverified, không giả định sạch |

### Nhóm kiểm thử

1. **Event schema & serialization:** required fields, enum, version.
2. **Provenance & identity mapping:** stable IDs, target mapping.
3. **End-to-end JML:** proofing, entitlement, session/token termination.
4. **Access governance:** approval, SoD, reviews và remediation.
5. **Distributed systems:** retry, duplicates, ordering, clock skew.
6. **Security of logs:** tamper evidence, role separation, export.
7. **Privacy:** masking, retention, no raw secrets.
8. **Reconciliation & negative access:** target Deny sau revoke.
9. **Failure injection:** collector outage, target unavailable, stale cache.
10. **Compliance/control evidence:** reproducible queries và scope.

## 40. Runbook: khi audit không đủ bằng chứng hoặc phát hiện sai lệch

### A. Không tìm thấy event cần thiết

1. Xác định **event type, source system, subject/account và time window**.
2. Kiểm logging configuration, schema mapping và collection coverage.
3. Kiểm collector lag, dead-letter queue, dropped events và permission.
4. Kiểm timezone, clock skew và source version.
5. Truy xuất raw source evidence nếu có và được phép.
6. Đánh dấu **UNVERIFIED/EVIDENCE_GAP**, không giả định event không xảy ra.
7. Khắc phục pipeline và tạo test chống mất log.

### B. IAM báo REVOKE nhưng target vẫn Permit

1. Lấy **source event, approval/decision, connector operation ID**.
2. Kiểm đúng target account, tenant, entitlement và scope.
3. Readback direct grants, nested group, role inheritance và local accounts.
4. Kiểm OAuth token, refresh token, SaaS session, PAM và credentials độc lập.
5. Chặn action nhạy cảm ở PEP/resource server nếu khả thi.
6. Tạo finding/incident có owner, SLA và bằng chứng.
7. Đóng sau khi target Deny đúng theo phạm vi kiểm thử.

### C. Nghi có log bị sửa hoặc xóa

1. Bảo toàn nguồn evidence và giới hạn thay đổi tiếp theo.
2. Kiểm IAM quyền quản lý audit sink, storage và retention.
3. So sánh hash/signature/checkpoints hoặc independent export khi có.
4. Kiểm source raw logs, sequence gaps và thao tác quản trị.
5. Xử lý incident và phân biệt **log tampering** với lỗi ingestion/retention hợp lệ.
6. Không sửa/xóa bản gốc để làm “timeline đẹp hơn”; ghi correction event riêng.

### D. Quyền được cấp không có approval

1. Xác định grant source: birthright, policy auto, direct, exception hay manual.
2. Kiểm account/identity mapping và thời điểm grant.
3. So policy/SoD và yêu cầu approval cho entitlement đó.
4. Kiểm actor thực hiện, delegated authority, role policy version.
5. Nếu grant trái policy, hạn chế hoặc revoke theo quy trình/rủi ro.
6. Đối soát target, mở finding và ngăn tái phát.

### E. Leaver còn quyền ở một hệ thống legacy

1. Lấy HRIS effectiveAt, relationshipId và target account ID.
2. Xác định hệ thống không hỗ trợ SCIM/session API hay chỉ connector lỗi.
3. Ưu tiên disable account/credential bằng kênh được phép.
4. Kiểm local session, API key, SSH/VPN/DB connection.
5. Dùng compensating control ở gateway/network/resource policy khi phù hợp.
6. Readback và thử action Deny.
7. Ghi rõ **coverage, risk, owner và deadline**, không tuyên bố sạch nếu chưa chứng minh.

## 41. Tình huống xuyên suốt: hành trình audit của Lan

Giả sử doanh nghiệp sử dụng **HRIS, IAM/IGA, IdP hỗ trợ MFA và SSO, CRM provision bằng SCIM, Finance API dùng RBAC/ABAC, PAM**, đồng thời có CI/CD và service principals.

### Giai đoạn 1 — Joiner

HRIS tạo identityId **person-2046** và relationship với effectiveAt. IAM/IdP tạo account; MFA enrollment thành công. Business role SALES_READER được cấp theo policy. Một quyền export bổ sung có approval resource owner.

Audit trail liên kết **HRIS identity event, proofing reference, MFA enrollment metadata, role mapping policy, approval và target SCIM readback**. Không ghi mã MFA hoặc password vào log.

### Giai đoạn 2 — Access request và authorization

Lan xin CUSTOMER_EXPORT để hoàn thành dự án. Manager duyệt nhu cầu nhưng resource owner yêu cầu phạm vi chỉ trên tenant A. Quyền được cấp với expiry, API kiểm **subject, action, resource, tenant, authentication assurance và policyVersion**. Audit không chỉ thấy grant SUCCESS, mà còn ghi rõ **phạm vi đã được phê duyệt**.

### Giai đoạn 3 — Mover

Lan chuyển Sales → Finance. IAM tính desired state mới và gỡ Sales Export. Connector SCIM trả acknowledgement, nhưng CRM local group khác vẫn cấp **customer.export**. Reconciliation phát hiện observed effective permission chưa khớp desired. Audit mở **ResidualAccessFinding**, không đóng Mover vì job đã báo Done.

### Giai đoạn 4 — Khắc phục

Owner xác định group local bị cấp trực tiếp trước đây. IAM/app admin gỡ group đó, resource server test **customer.export** trên tài nguyên kiểm soát trả Deny. Audit kết nối finding → remediation → readback → negative test, với verifiedAt và coverage.

### Giai đoạn 5 — Access review và SoD

Campaign quý review quyền Finance. Reviewer có đủ thẩm quyền xác nhận **REPORT_READER**, nhưng không thể tự chứng nhận chính quyền **PAYMENT_APPROVER** nếu SoD policy cấm self-review. Audit kiểm reviewer identity, decision, snapshot/sourceVersion, reason và fulfillment, không chỉ count Certified.

### Giai đoạn 6 — Leaver

Lan nghỉ việc hiệu lực 16:00. IdP chặn login và revoke sessions; SCIM disable account; OAuth AS xử lý refresh token; PAM terminate sessions. Một SaaS legacy chưa hỗ trợ global logout và còn PAT. Audit kiểm đến **target API action** và ghi finding cho PAT chưa được revoke; Security xử lý issuer key và xác minh Deny sau đó.

### Giai đoạn 7 — Owner chuyển giao cho service

Lan trước đó là người quản lý một bot báo cáo. Khi Lan Leaver, quyền cá nhân trên vault/CI bị gỡ, nhưng bot production hợp lệ được chuyển owner team. Audit xác minh workload principal riêng, secret rotation theo exposure risk và target grants còn phù hợp; không tự xóa workload chỉ vì human owner đã nghỉ.

### Điều học được

**Audit IAM là chuỗi bằng chứng có thể kiểm tra lại**, không phải một báo cáo “mọi job thành công”. Quan hệ JML, approval, quyền hiệu lực, log session/token, trạng thái ở hệ thống đích và kiểm thử hành vi phải được nối bằng định danh, thời gian và policy rõ ràng.

## 42. Checklist xây dựng Audit IAM đáng tin cậy

1. **Mục đích:** audit đang đánh giá kiểm soát/rủi ro nào?
2. **Phạm vi:** đã xác định systems, tenants, time window và population?
3. **Định nghĩa:** phân biệt log, audit trail, access review, monitoring và compliance?
4. **Source of truth:** HRIS/contract và workload registry đáng tin?
5. **Identity linking:** personId/relationshipId/targetAccountId ổn định?
6. **Actor:** tách requester, beneficiary, approver, connector và resource owner?
7. **Event schema:** eventId/type/version, action, outcome, policy version?
8. **Correlation:** có sourceEventId, causationId, operationId và correlationId?
9. **Timestamp:** occurredAt, effectiveAt, observedAt và ingestedAt?
10. **Joiner:** proofing, enrollment, baseline và approval có evidence?
11. **Mover:** quyền cũ bị gỡ trước/khi quyền mới được cấp theo risk?
12. **Leaver:** target action thực sự Deny sau effectiveAt?
13. **Rejoiner:** quyền cũ không tự hồi sinh theo email lịch sử?
14. **SSO:** IdP session và local RP sessions được tách rõ?
15. **OAuth:** token issued/revoked khác resource action enforced?
16. **SCIM:** connector ack khác target readback?
17. **RBAC:** role/group/direct grants và hierarchy được tính?
18. **ABAC:** thuộc tính, source và freshness đáng tin?
19. **SoD:** static/dynamic conflicts có rule, scope và evidence?
20. **Access request:** approver authority, business need, expiry hợp lệ?
21. **Access review:** decision có provenance và version; revoke có fulfillment?
22. **PAM/JIT:** eligible/active/session/credential được audit riêng?
23. **Non-human:** service/workload/device có owner, purpose, lifecycle?
24. **Vault/secrets:** raw credential không bị log; rotation/revoke tại target?
25. **Audit pipeline:** source authenticity, schema, redaction và delivery?
26. **Availability:** collector lag, dropped events và sink outage có alert?
27. **Integrity:** append-only/WORM/signing/checkpoint theo risk?
28. **Audit of audit:** ai đổi log policy, retention hoặc export?
29. **Privacy:** chỉ thu đủ, access control và retention rõ?
30. **Versioning:** sự kiện JML tới sai thứ tự không tạo regrant?
31. **Reconciliation:** desired vs observed và runtime access?
32. **Evidence quality:** biết nguồn, timestamp, completeness và confidence?
33. **Coverage:** thiếu local SaaS/API/PAT hay target logs nào được nêu rõ?
34. **Testing:** có end-to-end positive/negative JML, SoD, revocation?
35. **Metrics:** theo dõi verified revocation, residual window, review completion riêng?
36. **Findings:** mỗi vấn đề có risk, owner, SLA, control và evidence?
37. **Closure:** đã chứng minh control hiệu quả trong phạm vi được kiểm?
38. **Limits:** báo cáo không khẳng định rộng hơn dữ liệu có thể quan sát?

### Ghi nhớ

**Audit IAM là quá trình kiểm toán danh tính và quyền truy cập dựa trên bằng chứng để xác định ai được cấp quyền gì, bởi ai, theo chính sách nào, khi nào và liệu quyền thực tế có đúng hay không.** Điểm cốt lõi là **không nhầm logging với audit, approval với provisioning, connector success với target state, hoặc session bị đóng với mọi credential đã bị thu hồi**. Một hệ thống đáng tin cần **event schema, stable identity mapping, correlation, timestamp/provenance, bảo vệ log, quyền riêng tư, reconciliation và negative authorization tests**. Trong **Joiner–Mover–Leaver**, audit phải bao phủ **IdP/SSO, SCIM, RBAC/ABAC/PBAC, SoD, access review, PAM/JIT, service/workload identities, token và credential**, đồng thời đánh giá **quyền truy cập tồn dư** bằng bằng chứng ở hệ thống đích thay vì chỉ nhìn trạng thái công việc hành chính.
