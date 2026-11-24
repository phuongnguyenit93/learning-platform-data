# Identity event – sự kiện danh tính trong IAM Identity Lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **Identity event (sự kiện danh tính)** và phân biệt nó với trạng thái danh tính, yêu cầu thay đổi, command, log kỹ thuật, audit record và security alert.
- Xác định các sự kiện quan trọng trong **Joiner–Mover–Leaver (JML)**, xác minh danh tính, cấp/thu hồi tài khoản, phê duyệt quyền, xác thực, SSO, SCIM và rà soát truy cập.
- Thiết kế **event envelope và payload** có subject, actor, issuer, nguồn có thẩm quyền, tenant/relationship, event ID, thời gian, policy/schema version, correlation/causation ID và trạng thái kết quả.
- Mô tả kiến trúc thu nhận, chuẩn hóa, kiểm tính xác thực, lưu, phân phối, xử lý và đối soát identity events giữa HRIS, IdP, IGA, directory, SaaS và resource APIs.
- Xử lý **duplicate, replay, out-of-order delivery, delayed HRIS events, race condition, clock skew, partial failure và eventual consistency** mà không tạo lại quyền đã thu hồi.
- Hiểu vì sao **event được phát không đồng nghĩa target đã áp dụng thay đổi**, cần phân biệt requested, accepted, applied, observed và verified.
- Tổ chức audit và detection cho **đăng nhập, MFA, reset, session revocation, role changes, privileged access, robot/service account** với nguyên tắc bảo vệ PII và secrets.
- Liên hệ identity events với **IdP, SSO, OAuth/OIDC, SAML, SCIM, RBAC/ABAC/PBAC, PAM, tài khoản dịch vụ và kiểm toán vòng đời danh tính**.
- Áp dụng mô hình Java/Spring, truy vấn phân tích, ma trận kiểm thử và các chỉ số vận hành để giảm **quyền truy cập tồn dư**.

## 1. Identity event là gì?

**Identity event** là một bản ghi có cấu trúc biểu thị **một sự việc liên quan đến danh tính, quan hệ làm việc, trạng thái tài khoản, thông tin xác thực, quyền hoặc hoạt động truy cập đã xảy ra hay đã được ghi nhận** trong hệ sinh thái Identity and Access Management (IAM).

Ví dụ:

- HRIS ghi nhận nhân viên mới bắt đầu làm việc.
- Bộ phận nhân sự thay đổi manager hoặc phòng ban.
- IdP xác nhận một lần đăng nhập có MFA thành công.
- IGA chấp thuận yêu cầu thêm entitlement.
- SCIM connector báo đã tạo user ở SaaS.
- Hệ thống đích phát hiện một role admin vẫn còn sau khi người dùng nghỉ việc.
- Security yêu cầu thu hồi mọi session do nghi ngờ credential compromise.
- Resource owner thu hồi quyền trong một kỳ access recertification.
- Workload/service principal được thay owner, xoay vòng credential hoặc decommission.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, identity event là đầu mối kết nối chuỗi **Joiner–Mover–Leaver**: từ **xác minh và thiết lập danh tính**, **tạo tài khoản/cấp quyền**, **đăng nhập và sử dụng quyền**, **thay đổi vai trò**, tới **thu hồi, kiểm toán và chống quyền tồn dư**. Các hệ **HRIS, IdP/SSO, SCIM/API, RBAC/ABAC/PBAC, directory, PAM và service identity** đều có thể phát hoặc tiêu thụ những sự kiện liên quan.

### 1.1. Ví dụ gần với nghiệp vụ

~~~text
Ngày 01/12:
  HRIS: employee-1042 joined Sales (effective)
  IGA: tạo identity person-1042
  IdP: tạo account và MFA enrollment
  SCIM: provision SaaS CRM account
  CRM: xác nhận role SalesReader có hiệu lực

Ngày 15/12:
  HRIS: employee-1042 moved Sales -> Finance
  IGA: tính lại desired entitlements
  CRM: thu hồi SalesReader
  ERP: cấp FinanceReader sau approval
  Reconciliation: đối chiếu observed vs desired rights

Ngày 31/03:
  HRIS: employee-1042 left company
  IdP: chặn đăng nhập mới, thu hồi session/grant
  CRM/ERP: disable account và gỡ entitlement
  PAM/VPN: chấm dứt phiên nếu liên quan
  Reconciliation: phát hiện và xử lý quyền còn tồn dư
~~~

Mỗi dòng có thể là một **event khác nhau**, phát từ một **nguồn khác nhau**, vào **thời điểm khác nhau**, với mức độ chắc chắn khác nhau. Không được trộn tất cả thành một cờ “onboarding/offboarding complete” nếu các hệ đích chưa xác minh kết quả.

### 1.2. Một bản ghi sự kiện có hai giá trị

- **Giá trị vận hành:** kích hoạt workflow cấp/thu hồi quyền, làm mới policy hoặc session.
- **Giá trị chứng cứ:** cho biết ai/điều gì đã xảy ra, dựa vào nguồn nào, ở đâu và kết quả gì để phục vụ điều tra và kiểm toán.

Không phải event nào cũng cần làm thay đổi quyền; một event đăng nhập thất bại có thể chỉ được dùng cho **security detection**, trong khi HRIS Leaver event có thể kích hoạt **deprovisioning**.

## 2. Phân biệt event, state, command, log và audit evidence

| Khái niệm | Trả lời câu hỏi | Ví dụ | Điểm cần lưu ý |
| --- | --- | --- | --- |
| **Identity event** | Sự việc nào đã xảy ra/được ghi nhận? | `identity.relationship.changed` | Dữ liệu dạng sự kiện, có nguồn, thời gian và danh tính |
| **Current state** | Danh tính đang có trạng thái gì? | `employmentStatus=INACTIVE` | Trạng thái tổng hợp có thể thay theo thời gian |
| **Command/request** | Muốn hệ thực hiện điều gì? | `DisableAccountRequested` | Chưa chứng minh target đã disable |
| **Business decision** | Ai quyết định cấp/giữ/thu hồi quyền? | `AccessRequestApproved` | Chưa chứng minh quyền có hiệu lực |
| **Execution outcome** | Target đã làm gì? | `AccountDisabled` | Cần nguồn từ target hoặc readback đáng tin |
| **Technical log** | Thành phần phần mềm đã ghi thao tác/lỗi gì? | `SCIM PATCH returned 503` | Có thể chỉ mô tả retry, không phải trạng thái nghiệp vụ |
| **Audit record** | Bằng chứng truy vết hành động và kết quả? | Actor, action, policy, outcome | Có yêu cầu integrity, retention và access control |
| **Security alert** | Tín hiệu nào bị đánh giá là rủi ro? | `ImpossibleTravelDetected` | Là kết quả phân tích, chưa chắc là attack |
| **Integration message** | Dữ liệu truyền qua broker? | Kafka record | Không phải message nào cũng là sự kiện đã xảy ra |

### 2.1. Sự kiện “đã yêu cầu” khác “đã thực hiện”

~~~text
AccessRevocationRequested
  != AccessRevocationApproved
  != TargetEntitlementRemoveSent
  != TargetEntitlementRemoved
  != EffectiveAccessDenied
~~~

Ví dụ `SCIM request accepted` có thể chỉ nghĩa connector nhận command. Quyền ở target vẫn có thể **ACTIVE** do hàng đợi, lỗi, cache hoặc session còn giá trị.

### 2.2. Sự kiện là fact, không phải ý muốn

Nên đặt tên event phản ánh **điều đã được xác nhận**:

- `account.disable.requested` – yêu cầu được ghi nhận.
- `account.disable.applied` – hệ có thẩm quyền xác nhận thay đổi.
- `account.access.denied.verified` – kiểm chứng ở PEP rằng truy cập bị từ chối.

Không dùng `AccountDisabled` cho event chỉ mới được gửi tới queue.

### 2.3. Event sourcing khác event logging

**Event sourcing** là một lựa chọn kiến trúc trong đó trạng thái hệ thống có thể được xây lại bằng cách xử lý chuỗi domain events. **Identity logging** không bắt buộc dùng event sourcing: nhiều hệ IAM lưu current state trong DB/IdP rồi gửi event để workflow/audit.

Dù dùng kiến trúc nào, audit/security logs vẫn cần **bảo vệ tính toàn vẹn và được giữ theo chính sách**; event-sourced DB không tự động đáp ứng đầy đủ các yêu cầu này.

## 3. Ai phát, ai nhận và ai có thẩm quyền?

Một identity event luôn phải có **nguồn phát (producer)** và có thể có nhiều **consumer**.

| Nguồn phát | Những sự kiện tiêu biểu | Consumer |
| --- | --- | --- |
| **HRIS/HR feed** | Hire, effective start, move, terminate, leave of absence | IGA, identity registry |
| **Identity proofing** | Evidence verified, verification failed, identity link established | IGA, IdP |
| **IdP/Directory** | Account created/disabled, login/MFA, password reset, group change | SIEM, applications, IGA |
| **IGA/Access governance** | Access request/approval, recertification decision, SoD exception | Provisioning, PDP, audit |
| **SCIM/target connector** | Provision attempt, applied, failed, reconciliation drift | IGA, monitoring |
| **Resource API/PEP** | Access permitted/denied, session revoked, privileged action | SIEM, anomaly detection |
| **PAM/JIT** | Privilege activated, session opened/terminated | SOC, compliance |
| **Workload registry** | Service principal created, rotated, owner changed, retired | Cloud IAM, secret manager |
| **Security response** | Account blocked, credential compromised, session revoke commanded | IdP, PEP, IAM |
| **Audit/reconciliation** | Orphan account found, unexpected entitlement observed | Governance, remediation |

### 3.1. Producer phát được không có nghĩa producer là nguồn chân lý

Ví dụ một SaaS log hiển thị `department=Finance` có thể chỉ là bản sao từ HRIS. **HRIS** mới là nguồn có thẩm quyền về quan hệ làm việc theo thiết kế, còn **SaaS** có thẩm quyền về role/account thực tế của chính nó.

Cần một **source-of-authority matrix**: trường nào được tin từ nguồn nào, ưu tiên khi xung đột và ai được phép sửa.

### 3.2. Consumer không được tự nâng thẩm quyền

Một application nhận `managerChanged` event không tự được cấp quyền chỉnh mọi account. Consumer phải có **service identity, authorization và scope** riêng cho việc cập nhật hệ đích.

### 3.3. Event về một chủ thể có thể do người khác thực hiện

Trong `PrivilegedRoleAssigned`:

- **Subject:** người/robot được cấp role.
- **Actor:** người quản trị, approval workflow hoặc service principal thực thi.
- **Resource:** role và hệ đích.
- **Source authority:** ai có quyền cho phép thay đổi.

Ghi subject bằng actor sẽ làm mất khả năng truy vết lạm dụng.

## 4. Phân loại Identity events

Identity events có thể được phân theo **nghiệp vụ, identity lifecycle, authentication, authorization, hoạt động kiểm soát và trạng thái execution**.

### 4.1. Taxonomy đề xuất

| Nhóm | Event minh họa | Hành động phổ biến |
| --- | --- | --- |
| **Identity lifecycle** | `identity.joiner.effective`, `identity.mover.effective`, `identity.leaver.effective` | Provision/recalculate/revoke |
| **Identity proofing** | `identity.proofing.completed`, `identity.proofing.failed` | Chặn/mở onboarding theo policy |
| **Identity linking** | `identity.link.created`, `identity.link.conflict.detected` | Map HRIS/IdP/SaaS account |
| **Account lifecycle** | `account.created`, `account.disabled`, `account.deleted` | Cập nhật inventory/target |
| **Authentication** | `authentication.succeeded`, `authentication.failed` | Audit/detection |
| **MFA/credential** | `mfa.factor.enrolled`, `credential.rotated`, `credential.compromised` | Step-up, alert, revoke |
| **SSO/federation** | `federation.trust.changed`, `sso.session.established` | Rà trust/session |
| **Authorization** | `entitlement.granted`, `entitlement.removed`, `policy.changed` | PDP/PEP refresh |
| **Access approval** | `access.request.approved`, `access.request.rejected` | Provision/notify |
| **Recertification** | `access.certified`, `access.revoke.decided` | Remediation |
| **Privileged access** | `pam.elevation.activated`, `pam.session.closed` | JIT/session handling |
| **Session/token** | `session.revocation.requested`, `session.revocation.applied` | Invalidate sessions/grants |
| **Non-human identity** | `workload.created`, `service.credential.rotated`, `robot.retired` | Trust/secret/role lifecycle |
| **Reconciliation** | `access.drift.detected`, `access.removal.verified` | Remediate/report |
| **Security incident** | `identity.security.blocked`, `identity.takeover.suspected` | Containment |
| **Process observability** | `provisioning.retry.scheduled`, `connector.failed` | Ops/alert |

Tên trong bảng là **quy ước minh họa**. Các nhà cung cấp không dùng chung một bộ event names. Phải xây **mapping chuẩn hóa có phiên bản** để tránh nhầm nghĩa.

### 4.2. Tách outcome khỏi event type khi thích hợp

Một hệ có thể phát:

~~~json
{
  "eventType": "authentication.attempted",
  "outcome": "DENY",
  "reasonCode": "INVALID_CREDENTIAL"
}
~~~

Hệ khác có thể tách `authentication.succeeded` và `authentication.failed`. Cả hai cách đều hợp lệ nếu **schema, kết quả, lý do và thời gian** rõ, nhất quán.

### 4.3. Đừng để một event dùng cho hai hành vi trái ngược

Nếu `account.updated` vừa có thể là đổi display name vừa là disable account, consumer không nên suy permission từ tên event chung chung mà không kiểm **changed fields, authoritative state và relationship**.

## 5. Ánh xạ sự kiện vào Joiner–Mover–Leaver

| JML | Event đầu vào đáng tin | Desired state | Event kết quả cần quan sát |
| --- | --- | --- | --- |
| **Joiner** | `employment.start.effective` | Identity ACTIVE, baseline rights theo approval | Account provisioned, auth enrollment, grants verified |
| **Mover** | `employment.role.changed` | Thu hồi quyền cũ, cấp quyền mới có điều kiện | Old grants removed, new grants applied, SoD checked |
| **Leaver** | `employment.end.effective` | Chặn quyền theo relationship, đóng phiên | IdP blocked, SCIM disabled, PAM sessions terminated, access denied |
| **Leave of absence** | `employment.leave.started` | Suspend/giới hạn quyền theo policy | Suspensions applied/verified |
| **Rehire** | `employment.rehire.effective` | Đánh giá lại quyền mới, không tái kích hoạt mù | New provisioning, old grants not revived |
| **Transfer across legal entities** | `relationship.ended` + `relationship.started` | Ranh giới tenant/role mới | Cross-tenant grants reconciled |

**JML là mô hình nghiệp vụ; event semantics phụ thuộc nguồn dữ liệu và chính sách.** Một sự kiện “HRIS record created” không tự chứng minh người đó đã tới ngày bắt đầu và đủ điều kiện có production access.

### 5.1. Cần phân biệt event effective với event observed

Ví dụ HRIS nhập quyết định nghỉ việc vào ngày 20/11 nhưng ngày hiệu lực là 30/11. Nếu consumer hiểu nhầm `recordUpdatedAt` là thời điểm phải revoke ngay, có thể khóa tài khoản trước lịch.

Ngược lại, nếu event Leaver phát trễ sau effectiveAt, hệ phải **xem xét hành động thực hiện trong khoảng trễ** và xử lý quyền tồn dư tương ứng.

### 5.2. Chính sách phải gắn với quan hệ làm việc

Một identity có thể có nhiều hợp đồng/tenant. `relationship.ended` của hợp đồng A không nhất thiết có nghĩa **toàn bộ identity** đã chấm dứt mọi quan hệ.

Cần mapping từ **identityId + relationshipId + tenantId + entitlement provenance** để xác định đúng quyền cần xử lý.

## 6. Identity event pipeline tổng thể

~~~mermaid
flowchart LR
    HR["HRIS / Identity proofing"] --> ING["Event ingestion"]
    IDP["IdP / SSO / Directory"] --> ING
    IGA["IGA / Approval / PAM"] --> ING
    TGT["SCIM / SaaS / Cloud / Workload"] --> ING
    ING --> VAL["Validate source, schema, identity, authority"]
    VAL --> NORM["Normalize + enrich trusted context"]
    NORM --> EVENT["Durable event store / broker"]
    EVENT --> WORK["Lifecycle / provisioning workflows"]
    EVENT --> SIEM["SIEM / security detection"]
    EVENT --> AUD["Controlled audit evidence"]
    WORK --> PEP["Target systems / PEP"]
    PEP --> RECON["Observed state + reconciliation"]
    RECON --> EVENT
~~~

### 6.1. Từng bước làm gì?

1. **Ingest:** nhận event qua webhook, CDC, message bus, API polling hoặc connector.
2. **Authenticate producer:** kiểm mTLS/service identity, signature, issuer, quyền phát event.
3. **Validate:** schema, tenant, trường bắt buộc, định dạng thời gian, event ID và độ tin cậy.
4. **Normalize:** chuyển event vendor-specific sang mô hình canonical đã định nghĩa.
5. **Enrich:** nối identity/relationship/resource từ registry đáng tin, ghi provenance.
6. **Persist:** lưu an toàn và phát vào hệ phân phối với retention/availability phù hợp.
7. **Process:** lifecycle engine xử lý chuyển trạng thái hoặc tạo command.
8. **Enforce:** IdP/SCIM/PAM/API thực thi thay đổi theo policy.
9. **Observe:** lấy kết quả từ hệ đích và kiểm effective access.
10. **Audit/reconcile:** giữ chứng cứ, alert drift, xử lý ngoại lệ.

### 6.2. Event fan-out không tự là một transaction phân tán

Một event Leaver có thể fan-out tới IdP, SaaS, VPN và PAM. IdP có thể thành công trong khi SaaS trả 503. Không có cơ sở để đánh dấu **all revoked** chỉ vì broker giao event thành công.

### 6.3. Tách control plane và data plane

- **Control plane:** ghi nhận event, quyết định access, gửi command, cập nhật grant.
- **Data plane:** endpoint/resource/phiên thực tế PERMIT hay DENY.
- **Verification plane:** kiểm readback và thử effective access có kiểm soát.

Đối với rủi ro cao, cần bằng chứng ở data plane chứ không chỉ message được nhận.

## 7. Canonical event envelope cần những trường nào?

Một mô hình event tốt phân biệt **thông tin bao ngoài (envelope)** với **payload theo loại sự kiện**.

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **eventId** | `evt-20261123-1042-9` | ID duy nhất trong scope để dedup |
| **eventType** | `identity.relationship.ended` | Semantic event name |
| **schemaVersion** | `2` | Quy tắc diễn giải payload |
| **sourceSystem** | `hris-core` | Nguồn phát, không chỉ URL |
| **sourceEventId** | `hr-termination-1881` | ID gốc để truy vết |
| **tenantId** | `tenant-a` | Ranh giới dữ liệu |
| **identityId** | `person-1042` | ID chuẩn nội bộ của subject |
| **relationshipId** | `employment-A-1042` | Quan hệ làm việc liên quan |
| **actorRef** | `hris-sync` | Ai/điều gì gây ra event |
| **subjectRef** | `person-1042` | Đối tượng bị tác động |
| **occurredAt** | Timestamp | Khi sự việc xảy ra tại nguồn |
| **effectiveAt** | Timestamp | Khi thay đổi phải có hiệu lực nghiệp vụ |
| **ingestedAt** | Timestamp | Khi hệ nhận event |
| **correlationId** | `jml-flow-5561` | Gom nhiều event cùng workflow |
| **causationId** | `evt-origin-01` | Event/command trực tiếp gây ra event này |
| **aggregateVersion** | `42` | Phiên bản thứ tự trạng thái của identity/relationship |
| **policyVersion** | `jml-access-v6` | Policy đã áp tại thời điểm decision |
| **outcome/status** | `APPLIED`, `DENIED` | Kết quả nếu event mô tả execution |
| **payload** | Object theo loại event | Dữ liệu riêng |
| **classification** | `INTERNAL_SENSITIVE` | Định tuyến/retention/masking |
| **traceRef** | `trace-9921` | Correlation kỹ thuật, không là credential |

**Không phải event nào cũng cần mọi trường.** Ví dụ authentication failure có thể chưa liên kết được với một identityId thật; không được tự gán danh tính chắc chắn từ username nhập sai.

### 7.1. Event ID và aggregate version có vai trò khác nhau

- `eventId` giúp phát hiện **message lặp**.
- `aggregateVersion` giúp quyết định **thứ tự cập nhật trạng thái** của một identity/relationship.
- `correlationId` giúp nối sự kiện cùng business workflow.
- `causationId` giúp tìm **nguồn trực tiếp** dẫn đến event.
- `traceId` phục vụ quan sát lời gọi kỹ thuật, không thay business event identity.

Một thiết kế chỉ có `timestamp` và `email` khó đảm bảo đúng thứ tự, nguồn gốc và chống replay.

## 8. Ví dụ Identity event kiểu Joiner–Mover–Leaver

### 8.1. Joiner event minh họa

~~~json
{
  "eventId": "evt-joiner-1001",
  "eventType": "identity.relationship.started",
  "schemaVersion": 2,
  "sourceSystem": "hris-core",
  "sourceEventId": "employment-event-882",
  "tenantId": "tenant-a",
  "subject": {
    "identityId": "person-1042",
    "relationshipId": "employment-A-1042"
  },
  "actor": {
    "type": "SYSTEM",
    "principalId": "hris-lifecycle-adapter"
  },
  "occurredAt": "2026-11-23T09:00:00+07:00",
  "effectiveAt": "2026-12-01T08:00:00+07:00",
  "aggregateVersion": 1,
  "correlationId": "jml-1042",
  "payload": {
    "relationshipStatus": "PENDING_START",
    "workerType": "EMPLOYEE",
    "managerIdentityId": "person-501",
    "organizationalUnitId": "sales"
  }
}
~~~

**Số liệu là minh họa.** Trường `relationshipStatus=PENDING_START` là trạng thái nguồn tại thời điểm event, khác hiệu lực Joiner tương lai. Consumer không nên tự cấp role production trước `effectiveAt` nếu policy không cho phép.

### 8.2. Mover event minh họa

~~~json
{
  "eventId": "evt-mover-1002",
  "eventType": "identity.relationship.changed",
  "schemaVersion": 2,
  "sourceSystem": "hris-core",
  "subject": {
    "identityId": "person-1042",
    "relationshipId": "employment-A-1042"
  },
  "tenantId": "tenant-a",
  "occurredAt": "2026-12-10T13:00:00+07:00",
  "effectiveAt": "2026-12-15T00:00:00+07:00",
  "aggregateVersion": 2,
  "correlationId": "jml-1042-mover",
  "payload": {
    "changedFields": ["organizationalUnitId", "managerIdentityId"],
    "previous": {
      "organizationalUnitId": "sales",
      "managerIdentityId": "person-501"
    },
    "current": {
      "organizationalUnitId": "finance",
      "managerIdentityId": "person-608"
    }
  }
}
~~~

Một số tổ chức tránh đưa `previous/current` chứa PII vào message bus rộng; có thể lưu **field codes và tham chiếu tới kho dữ liệu có phân quyền** thay vì toàn bộ giá trị.

### 8.3. Leaver event minh họa

~~~json
{
  "eventId": "evt-leaver-1003",
  "eventType": "identity.relationship.ended",
  "schemaVersion": 2,
  "sourceSystem": "hris-core",
  "subject": {
    "identityId": "person-1042",
    "relationshipId": "employment-A-1042"
  },
  "tenantId": "tenant-a",
  "occurredAt": "2027-03-25T16:00:00+07:00",
  "effectiveAt": "2027-03-31T18:00:00+07:00",
  "aggregateVersion": 3,
  "correlationId": "jml-1042-leaver",
  "payload": {
    "reasonCode": "CONTRACT_END",
    "newRelationshipStatus": "TERMINATED"
  }
}
~~~

Dữ liệu không chứa mật khẩu, token, personal ID number hay thông tin nhạy cảm không cần thiết.

### 8.4. Leaver event không phải kết quả revocation

Consumer nhận `identity.relationship.ended` phải tạo hoặc thực thi **revoke workflow** theo thời điểm hiệu lực, rồi chờ các event như `account.disabled`, `entitlement.removed`, `session.revocation.applied`, `effective.access.denied`.

## 9. Identity linking: không dùng email làm khóa duy nhất

Một identity có thể xuất hiện khác nhau ở HRIS, IdP, directory, SaaS và cloud IAM.

~~~text
HRIS: employeeId = emp-1042
Identity registry: identityId = person-1042
IdP: issuer + sub = https://idp.example.invalid + 00a18f...
AD: objectGUID / immutableId
CRM: targetAccountId = crm-user-722
Cloud: principal object ID = cloud-principal-882
~~~

### 9.1. Quy tắc nối danh tính

- Dùng **stable subject identifier** phù hợp từng nguồn, ví dụ issuer + subject của OIDC, object ID của target.
- Phân biệt **human identity** và **employment relationship**.
- Không coi `email`, `displayName`, `username` là định danh vĩnh viễn.
- Bảo vệ bảng mapping và quy trình merge/split identity.
- Khi mapping không chắc, tạo **IDENTITY_LINK_CONFLICT** để review thay vì đoán.
- Ghi provenance: nguồn mapping, thời điểm xác minh, policy và người/phương thức phê duyệt.

### 9.2. Sự kiện đăng nhập thất bại có thể chưa biết subject

Một login attempt với username `admin@example.invalid` không tự chứng minh chủ account đó đã thực hiện hành động. Log phải có **asserted identifier** và **resolved identity** riêng, với mức độ xác thực phù hợp.

### 9.3. Identity merge không được làm mất lịch sử

Nếu hai tài khoản được xác định thuộc cùng một con người, audit gốc vẫn cần giữ **original subject references** và event linking. Không sửa toàn bộ event cũ thành tên/ID mới rồi mất dấu vết tại thời điểm sự kiện.

## 10. Bốn mốc thời gian và ý nghĩa

Các hệ IAM thường nhận event có **độ trễ**, có thay đổi được nhập trước hoặc truy hồi sau.

| Mốc | Trả lời | Ví dụ |
| --- | --- | --- |
| **occurredAt** | Sự việc tại nguồn được ghi nhận lúc nào? | HR nhập thay đổi lúc 14:00 |
| **effectiveAt** | Thay đổi nghiệp vụ có hiệu lực từ lúc nào? | Role mới có hiệu lực ngày 01/12 |
| **ingestedAt** | Pipeline nhận event lúc nào? | Webhook được nhận lúc 14:03 |
| **processedAt** | Consumer xử lý xong lúc nào? | IGA tính quyền lúc 14:04 |
| **observedAt** | Hệ đích được đọc/quan sát lúc nào? | SaaS role scan lúc 14:06 |
| **verifiedAt** | Kết quả đã được kiểm theo tiêu chí nào? | PEP deny confirmed lúc 14:07 |

Không bắt buộc mọi event có đủ sáu mốc. **Điều quan trọng là không dùng lẫn nghĩa**.

### 10.1. Effective time có thể trong tương lai

Nếu HRIS thông báo Mover ngày 20/11 nhưng có hiệu lực từ 01/12, IGA nên lập kế hoạch theo policy, không tự gỡ quyền ngay khi event nhập.

### 10.2. Effective time trong quá khứ

Nếu HRIS phát Leaver muộn sau ngày hiệu lực, hệ thống cần:

- Đưa trạng thái hiện hành về đúng policy càng sớm càng khả thi.
- Kiểm API activity, session, role changes sau effectiveAt.
- Ghi **lag** và mở exception/incident nếu quyền nhạy cảm đã tồn dư.
- Không sửa `occurredAt` để che việc nhận event trễ.

### 10.3. Timezone, clock skew và thứ tự

Lưu timestamp theo định dạng rõ timezone/UTC, đồng bộ đồng hồ và định nghĩa độ tin cậy nguồn. Không đặt **event-order guarantee** dựa hoàn toàn vào thời gian của nhiều máy không đồng bộ. Ưu tiên **source sequence/aggregate version** khi có.

## 11. Phiên bản event, schema evolution và compatibility

Identity schema có thể phát triển khi thêm `relationshipId`, multi-tenant, credential source hoặc loại account mới. Nếu consumer hiểu sai phiên bản, một sự kiện có thể dẫn tới cấp quyền sai.

### 11.1. Nguyên tắc

- Có **schemaVersion** rõ và registry/schema contract.
- Phân biệt **event type version** với **identity aggregate version**.
- Thêm optional field có default/semantics rõ khi compatible.
- Thay đổi ngữ nghĩa permission hoặc status phải **có version/migration**, không lặng lẽ đổi nghĩa.
- Kiểm **producer/consumer compatibility** trước rollout.
- Đặt validation ở ingress; message sai schema tới **quarantine/dead-letter**, không tự áp thay đổi đặc quyền.
- Lưu đủ provenance để **replay có kiểm soát** mà không hiểu event theo schema sai.

### 11.2. Trường mới có thể ảnh hưởng an toàn

Ví dụ schema v1 không có `tenantId`, v2 thêm. Consumer v1 có thể tự coi event là toàn organization; consumer v2 coi là chỉ tenant-a.

Khi đổi schema, phải chỉ rõ **cách xử lý trường thiếu**. Đối với revoke/grant nhạy cảm, không nên coi thiếu tenant là wildcard.

### 11.3. Schema validation không chứng minh sự kiện thật

Một payload JSON hợp lệ vẫn có thể là **forged event** nếu producer không được xác thực. Cần kiểm **nguồn phát, chữ ký/kênh, thẩm quyền actor và semantics**.

## 12. Event ordering, duplicate và idempotency

Message broker, webhook và connectors có thể gửi **trùng**, **đến muộn**, **đến sai thứ tự** hoặc **retry** sau timeout.

### 12.1. Ví dụ sai thứ tự nguy hiểm

~~~text
v10: employee ACTIVE ở Sales
v11: employee MOVER sang Finance
v12: employee LEAVER

Giao nhận:
  Consumer xử lý v12 trước.
  Sau đó nhận lại v10 và v11 do retry.

Nếu consumer áp event cuối cùng nhận được:
  -> Người đã Leaver có thể bị kích hoạt lại quyền.
~~~

### 12.2. Quy tắc an toàn

- Dedup theo **source + event ID** có phạm vi rõ.
- Bảo vệ **monotonic state/version** cho cùng identity/relationship.
- Reject/quarantine stale update có khả năng hạ thấp security state.
- Idempotent command khi tạo/thu hồi account và role.
- Không suy exactly-once end-to-end từ tính năng của broker.
- Tách **legitimate new relationship** khỏi event cũ: rehire cần lifecycle record/approval mới.
- Với event bị thiếu, **fetch authoritative current snapshot** rồi reconcile, không tự đoán các bước bị bỏ.

### 12.3. Dữ liệu replay không phải sự kiện sống

Nếu tổ chức replay audit events để rebuild dashboard, consumer vận hành cấp quyền không được **tự thực hiện lại cấp quyền ngoài hệ** nếu không có guard. Phải phân biệt replay mode, permission và side effects.

### 12.4. Dedup key không nên chỉ là email và timestamp

Hai event của hai tenant hoặc hai relationships có thể xảy ra cùng giây. Dùng **issuer/source system, event ID và business aggregate** để tránh gộp nhầm.

## 13. Transactional outbox và tính tin cậy của event phát ra

Một service có thể vừa cập nhật DB vừa cần publish event. Nếu hai thao tác không nguyên tử, có thể xảy ra:

- DB đã đổi trạng thái account nhưng event không phát.
- Event phát rồi DB rollback.
- Event được gửi hai lần do producer retry.

### 13.1. Transactional outbox pattern

~~~mermaid
sequenceDiagram
    autonumber
    participant API as Identity lifecycle service
    participant DB as State database + outbox
    participant PUB as Outbox dispatcher
    participant BUS as Trusted event broker
    participant CON as Consumer / Connector
    participant AUD as Audit / Reconciliation

    API->>DB: Transaction: update state + append outbox
    DB-->>API: Commit
    PUB->>DB: Read pending outbox
    PUB->>BUS: Publish event with stable eventId
    BUS-->>PUB: Delivery acknowledgement
    PUB->>DB: Mark dispatch progress
    BUS->>CON: Deliver (may duplicate)
    CON->>CON: Validate, dedup, version guard
    CON->>AUD: Applied outcome + observed state
~~~

### 13.2. Điều quan trọng của outbox

- State update và outbox record được ghi trong **cùng local transaction** khi kiến trúc hỗ trợ.
- Dispatcher có thể retry nên consumer phải **idempotent**.
- Event ID ổn định qua retry.
- Cần cơ chế giám sát **outbox backlog, dead letters, poison messages**.
- Không gửi trực tiếp vào bus trước DB commit rồi mặc định mọi thứ nhất quán.
- Outbox không tự biến các target SCIM/SaaS thành **một transaction toàn cục**.

### 13.3. Outbox không thay readback

Consumer báo `AccountDisabled` sau khi gửi SCIM PATCH vẫn cần xác minh target thực sự disable hoặc resource từ chối access, tùy risk. **Delivery success khác applied và effective state**.

## 14. Event fan-out, workflow và trách nhiệm

Một HRIS Mover có thể ảnh hưởng nhiều đích:

~~~text
HRIS Mover event
  -> Identity registry updates relationship/manager
  -> IGA recalculates desired access
  -> Remove old organizational roles
  -> Request approval for new sensitive grants
  -> Update IdP groups and SaaS SCIM assignments
  -> Update ABAC subject attributes / policy caches
  -> Revoke stale sessions or prompt reauthentication
  -> Reconcile target entitlements
~~~

### 14.1. Không cấp trước rồi mới gỡ quyền cũ một cách mù quáng

Khi có SoD conflict, việc tạm đồng thời giữ quyền Sales admin và Finance approve có thể không được phép. Cần xác định **revoke-first/approve-then-grant** hoặc phương án chuyển tiếp theo risk, có phiên bản và exception.

### 14.2. Consumer phải biết nghĩa nghiệp vụ

Một event `employee.department.changed` không đủ để tự xác định mọi entitlement. IAM cần **role mapping, ownership, policy, approvals, relationship status và resource classification**.

### 14.3. Idempotency khác rollback

Retry một request đã cấp role không nên tạo duplicate; nhưng nếu trước đó cấp sai role, chỉ idempotency không khắc phục lỗi. Cần **compensating action, revoke, audit và review**.

### 14.4. Phân loại kết quả xử lý

| Trạng thái | Ý nghĩa |
| --- | --- |
| **RECEIVED** | Hệ nhận message |
| **VALIDATED** | Nguồn/schema/identity đạt điều kiện |
| **DECISION_MADE** | Policy đã tính desired change |
| **COMMAND_QUEUED** | Tạo yêu cầu thay đổi target |
| **COMMAND_SENT** | Đã gửi connector/API |
| **APPLIED** | Target có xác nhận đã áp dụng |
| **VERIFIED** | Observed/effective state đáp ứng policy |
| **PARTIAL** | Một số target thành công |
| **UNKNOWN** | Chưa xác minh được |
| **FAILED** | Lỗi xác định, cần xử lý |
| **EXCEPTION** | Rủi ro/ngoại lệ được quản lý |

Trạng thái event-processing **khác** với trạng thái account hoặc relationship; một event `Leaver` vẫn là một fact ngay cả khi target provisioning thất bại.

## 15. Sự kiện nghiệp vụ, bảo mật và hành động target

Một luồng IAM chất lượng thường có **nhiều event cho cùng một thay đổi**.

### 15.1. Chuỗi ví dụ đầy đủ

~~~text
IdentityRelationshipEnded
  source = HRIS
  effectiveAt = 18:00

AccessRecalculationCompleted
  source = IGA
  desired = no grants tied to ended relationship

SessionRevocationRequested
  source = IAM security coordinator
  targets = IdP, app, VPN

TargetAccountDisableRequested
  source = provisioning coordinator
  target = SaaS CRM

TargetAccountDisabled
  source = CRM or trusted connector readback

EffectiveAccessDenied
  source = CRM PEP / trusted verification

ReconciliationCompleted
  source = governance
  result = MATCH or RESIDUAL_ACCESS
~~~

### 15.2. Audit cần giữ cả thất bại

Nếu `SCIM PATCH 503` hoặc identity mapping conflict làm Leaver không thực thi, đó là **thông tin quan trọng hơn một dashboard success màu xanh**. Cần giữ error class, retry count, target, correlation và owner, nhưng không ghi raw access tokens/credentials.

### 15.3. Một event có thể kích hoạt nhiều điều tra

Đăng ký MFA factor mới ngay trước khi cấp role admin và export dữ liệu nhạy cảm có thể là chuỗi **bình thường hoặc đáng ngờ**. SIEM cần correlation nhiều event; không nên kết luận account takeover chỉ từ một dấu hiệu đơn lẻ.

## 16. Identity proofing và sự kiện xác minh danh tính

**Identity proofing** là quy trình kiểm chứng rằng một identity được liên kết đúng với chủ thể và nguồn danh tính cần tin, trước khi cấp quyền theo rủi ro.

### 16.1. Sự kiện tiêu biểu

| Event | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| **ProofingStarted** | Bắt đầu quy trình xác minh | Theo dõi workflow |
| **EvidenceReceived** | Hệ đã nhận bằng chứng | Không tự xem là verified |
| **EvidenceCheckFailed** | Bằng chứng không đạt một bước | Escalation/fraud review |
| **IdentityVerified** | Kết luận mức assurance theo policy | Điều kiện tạo/cấp account |
| **IdentityLinkEstablished** | Nối source identity với identityId chuẩn | Chặn tạo trùng |
| **IdentityLinkDisputed** | Phát hiện mapping mâu thuẫn | Tạm dừng grant nhạy cảm |
| **RecoveryIdentityVerified** | Xác minh người cần khôi phục access | Credential reset workflow |

### 16.2. Dữ liệu audit nên lưu

Nên lưu **phương thức/proofing workflow reference, kết quả, assurance level nếu có, nguồn, người/hệ quyết định, thời điểm, policy và evidence pointer được bảo vệ**.

Không nên phát tán **ảnh giấy tờ, số căn cước, dữ liệu sinh trắc học, bản scan hoặc selfie** vào event bus rộng. Nếu cần chứng cứ, lưu ở kho chuyên biệt có kiểm soát và truyền **reference/opaque ID**.

### 16.3. Proofing event không tự cho phép mọi quyền

Một người đã được xác minh danh tính vẫn cần **authorization dựa trên relationship, role, approval, resource và policy**. `IdentityVerified` không được hiểu là `AssignAllBaselineRoles` khi relationship chưa ACTIVE.

### 16.4. Phát hiện identity collision

Nếu HRIS event và SaaS event có email giống nhưng object ID khác, pipeline nên phát **mapping conflict**, không âm thầm merge hai account. Một merge sai có thể khiến Leaver revoke nhầm quyền người khác hoặc Joiner thừa hưởng access cũ.

## 17. Joiner event: từ HRIS tới quyền thực tế

Một Joiner hợp lệ có thể sinh chuỗi sự kiện nhiều cấp.

~~~mermaid
sequenceDiagram
    autonumber
    participant HR as HRIS
    participant IAM as Identity registry / IGA
    participant GOV as Policy / Approval
    participant IDP as IdP
    participant SAAS as SCIM SaaS
    participant REC as Reconciliation

    HR->>IAM: RelationshipStarted event (effectiveAt)
    IAM->>IAM: Validate identity/relationship and version
    IAM->>GOV: Resolve baseline rights and risk
    GOV-->>IAM: Desired permissions / approval requirement
    IAM->>IDP: Create account / assign allowed group
    IDP-->>IAM: Account created or failure
    IAM->>SAAS: Provision targeted account/entitlement
    SAAS-->>IAM: Applied / async pending
    IAM->>REC: Expected state + event lineage
    REC->>IDP: Readback account and groups
    REC->>SAAS: Readback account and roles
    REC-->>IAM: MATCH / MISSING / EXCESS / UNKNOWN
~~~

### 17.1. Các mốc khác nhau

- `HRRecordCreated`: hồ sơ nhân sự tồn tại.
- `RelationshipEffective`: ngày bắt đầu có hiệu lực theo policy.
- `AccountProvisionRequested`: IGA đã quyết định tạo.
- `IdPAccountCreated`: account được tạo ở IdP.
- `CredentialEnrollmentCompleted`: người dùng hoàn thành yếu tố xác thực.
- `TargetEntitlementGranted`: hệ đích báo quyền được thêm.
- `AccessProvisionVerified`: reconciliation xác nhận scope.

Không nên dùng event đầu tiên để báo **onboarding hoàn tất**.

### 17.2. Nếu Joiner bị hủy

HRIS có thể phát `StartCancelled` trước ngày effective. Workflow cần hủy các command đang chờ, revoke preboarding sessions/credentials, gỡ account đã tạo và chặn replay event Joiner cũ.

### 17.3. Tạo idempotent

Hai lần gửi Joiner event không được tạo hai identity hoặc hai SaaS accounts. Consumer nên dùng **authoritative relationship key + source event ID + current-state guard**.

### 17.4. Không tạo quyền vì display name

Một Joiner mang tên giống nhân viên đã nghỉ không được nhận local account/role cũ chỉ do username collision. Cần stable identity linking và lifecycle policy.

## 18. Mover event: thay đổi thuộc tính và entitlement provenance

**Mover** phức tạp vì một số quyền cũ phải gỡ, một số quyền mới cần approval, còn một số quyền dùng chung vẫn giữ.

### 18.1. Ví dụ chuyển Sales sang Finance

~~~text
HRIS source:
  relationshipId = employment-A-1042
  aggregateVersion = 17
  previousOrgUnit = Sales
  newOrgUnit = Finance
  effectiveAt = 2026-12-15T00:00:00+07:00

IGA desired:
  remove CRM.SalesDiscountApprove
  retain corporate-email/basic VPN
  request Finance.ReportRead approval
  deny combined SalesApprove + FinancePayApprove (SoD)
~~~

### 18.2. Event và quyết định khác nhau

- HRIS phát event rằng **thuộc tính công việc đổi**.
- IGA tính **desired entitlement** theo role mapping hiện hành.
- Resource owner phê duyệt nếu quyền mới nhạy cảm.
- Connector phát event **grant/revoke outcome**.
- PEP kiểm quyền hiện hành; session JWT/group claims cũ có thể cần làm mới/thu hồi.
- Reconciliation xác minh quyền thừa không còn.

### 18.3. Chống privilege accumulation

Nếu có event `OrgUnitChanged`, consumer chỉ thêm quyền Finance mà không gỡ Sales, người dùng sẽ tích lũy quyền. Cần **provenance của từng entitlement**: được cấp vì baseline role nào, approval nào, quan hệ nào, và liệu còn lý do khác hợp lệ để giữ quyền không.

### 18.4. Event đến trước effectiveAt

Có thể lập lịch desired state mới nhưng không kích hoạt quyền sớm. Nếu cần giai đoạn chuyển giao, phải có **time-bound overlap được policy chấp thuận** và kiểm SoD.

### 18.5. Event đến sai thứ tự

Nếu Mover v17 đến sau Leaver v18, không được tái mở role khi v18 đã là authoritative current state. Consumer xử lý stale update và reconcile.

## 19. Leaver event: từ quyết định tới chặn truy cập

Leaver là ví dụ rõ nhất cho khác biệt giữa **event được phát** và **quyền đã mất hiệu lực**.

### 19.1. Chuỗi mục tiêu

~~~text
HRIS termination event
  -> Validate relationship identity and effectiveAt
  -> IAM mark relationship no longer eligible
  -> IdP block new authentication where required
  -> Revoke IdP/SSO sessions and refresh grants
  -> SCIM/API disable target accounts and remove roles
  -> PAM/VPN/SSH terminate privileged sessions
  -> Revoke delegated access and relevant credentials
  -> Reconcile target effective access
  -> Close or manage residual exceptions
~~~

### 19.2. Không coi SCIM status là toàn bộ bằng chứng

Một SaaS có thể trả `active=false` nhưng session cookie hoặc API token đã phát vẫn hợp lệ. Cần readback và policy cho **session revocation, token expiry/introspection, resource PEP, local roles**.

### 19.3. Event phát trễ

~~~text
Leaver effectiveAt = 18:00
HRIS event ingestedAt = 18:12
IdP disabled at = 18:13
ERP last successful privileged action = 18:07
~~~

Một workflow đúng không chỉ chặn từ 18:13. Nó còn phải lưu **late-effective event** và kiểm khoảng 18:00–18:13, phân tích activity sau effectiveAt khi cần và mở exception/incident theo mức rủi ro.

### 19.4. Quyền ở nhiều relationships

Nếu một người còn quan hệ hợp lệ với pháp nhân B, các grant từ B có thể tiếp tục theo policy. Nhưng security compromise toàn identity có thể yêu cầu thu hồi rộng hơn. Event phải biểu diễn **scope và căn cứ**, tránh dùng Boolean toàn cục khi bài toán có nhiều quan hệ.

### 19.5. Phục hồi không được dùng event cũ

Một rehire sau vài tháng cần **quan hệ/approval mới**, không phát lại `AccountEnabled` từ snapshot cũ để phục hồi toàn bộ quyền và session trước Leaver.

## 20. Authentication events: đăng nhập, MFA và OIDC/SAML

IdP, authenticator và relying party có thể phát nhiều sự kiện liên quan cùng một lần đăng nhập.

| Event | Ví dụ dữ liệu hữu ích | Rủi ro diễn giải |
| --- | --- | --- |
| **LoginAttempted** | issuer, asserted identifier, client, time | Chưa chắc biết identity thật |
| **AuthenticationSucceeded** | issuer+subject, method, auth time, client | Chưa chứng minh được phép mọi action |
| **AuthenticationFailed** | result code, asserted ID, device/network context | Có thể do user nhầm, không mặc định attacker |
| **MFAChallengeIssued** | phương thức, challenge ID an toàn | Không phải MFA thành công |
| **MFAChallengeCompleted** | factor class, outcome | Cần liên kết đúng login/session |
| **CredentialResetRequested** | actor, verified recovery path | Chưa có credential mới |
| **CredentialResetCompleted** | account, method class, policy version | Có thể cần revoke sessions cũ |
| **AccountLocked** | reason, source, effectiveAt | Có thể do brute force hoặc admin |
| **RiskSignalDetected** | device anomaly, impossible travel signal | Là tín hiệu, không là bằng chứng kết luận |

### 20.1. Không ghi password hay OTP

Identity logging phải **loại bỏ raw password, passkey material, OTP, TOTP seed, recovery code, session cookie, access/refresh token và private key**. Ghi loại phương thức và kết quả, không ghi giá trị bí mật.

### 20.2. OIDC claims và event logging

Trong OIDC:

- `iss` và `sub` có thể dùng để liên kết identity theo trust domain.
- `auth_time`, `acr`, `amr` có thể hỗ trợ đánh giá authentication freshness/assurance theo profile.
- `sid` trong một số flow có thể liên quan session, không có trong mọi token.
- `client_id`, audience và session references cần mapping đúng.

**ID token không phải audit event**, không nên sao chép toàn bộ JWT vào log. Nó cũng không phải access token để API tự kiểm resource permission.

### 20.3. SAML authentication events

Một IdP có thể log assertion phát cho SP; SP có thể log local session created/ended. Cần phân biệt **SAML assertion issued**, **SP session established** và **application authorization result**; một assertion được phát không chứng minh user đã thao tác thành công.

### 20.4. Login success không phải authorization success

Một người đăng nhập thành công qua SSO nhưng bị `role.grant` từ chối ở resource PEP là điều hoàn toàn bình thường. Audit nên ghi hai event/phạm vi riêng: **authentication** và **authorization**.

## 21. Session và token-related identity events

Một identity có thể có phiên IdP, ứng dụng, OAuth grant, refresh family, PAM hoặc API token riêng.

### 21.1. Sự kiện nên phân biệt

- `session.created` – phiên bắt đầu.
- `session.reauthenticated` – xác thực lại/step-up.
- `session.logout.requested` – user/app yêu cầu logout.
- `session.revocation.requested` – security/IAM yêu cầu vô hiệu.
- `session.revocation.applied` – session store/issuer xác nhận.
- `access.token.issued` – access token được phát (không ghi token raw).
- `refresh.grant.revoked` – refresh grant/family bị chặn.
- `effective.access.denied` – PEP đã từ chối sử dụng access theo kiểm chứng.
- `session.expired` – đến idle/absolute timeout.
- `token.reuse.detected` – tín hiệu refresh token replay nếu hệ hỗ trợ.

### 21.2. RFC 7009 và RFC 7662 không giải quyết mọi session

**OAuth 2.0 Token Revocation (RFC 7009)** mô tả yêu cầu thu hồi token tại authorization server. **OAuth 2.0 Token Introspection (RFC 7662)** mô tả cách kiểm active status/metadata token.

Một issuer có thể báo refresh token đã revoke trong khi **JWT access token cũ** vẫn được resource server nhận tới `exp` nếu không có online check/denylist. Event `refresh.grant.revoked` **không tự đồng nghĩa** `access.effectively.denied`.

### 21.3. Session ID có thể là credential

Session cookie/ID có tính bearer phải được coi là **secret**. Dùng event correlation reference hoặc HMAC/token fingerprint được thiết kế an toàn thay vì log raw session ID.

### 21.4. Sign-out-all cần capability matrix

Nhiều SaaS và native apps có local sessions không bị chặn ngay khi IdP logout. Event kết quả nên nêu **target nào VERIFIED_DENIED, target nào PENDING/UNKNOWN/NOT_SUPPORTED**, thay vì một event `AllSessionsRevoked` quá rộng và không kiểm chứng.

## 22. Authorization events: RBAC, ABAC, PBAC và Policy decision

**Authentication** trả lời “caller là ai?”. **Authorization** trả lời “caller được thực hiện action này trên resource nào trong context hiện hành?”.

### 22.1. Event phân quyền mẫu

~~~json
{
  "eventId": "authz-evt-671",
  "eventType": "authorization.decision",
  "schemaVersion": 1,
  "sourceSystem": "finance-api-pep",
  "tenantId": "tenant-a",
  "subject": {
    "identityId": "person-1042",
    "relationshipId": "employment-A-1042"
  },
  "actor": {
    "principalId": "finance-portal",
    "principalType": "APPLICATION"
  },
  "action": "invoice.approve",
  "resourceRef": "invoice-992",
  "decision": "DENY",
  "reasonCode": "SOD_CONFLICT",
  "policyVersion": "finance-authz-v8",
  "occurredAt": "2026-12-10T12:05:00+07:00",
  "correlationId": "req-19388"
}
~~~

Đây là mô hình minh họa. Một số request là app-only không có human subject; một số dùng delegated subject và workload actor riêng.

### 22.2. PEP và PDP

- **PDP (Policy Decision Point)** đánh giá policy, risk, roles, attributes, resource state.
- **PEP (Policy Enforcement Point)** là nơi thực thi PERMIT/DENY tại API/gateway/ứng dụng.
- **PIP (Policy Information Point)** cung cấp thuộc tính như HRIS status, department, resource classification, tenant.

Một event `PDP_DECISION=DENY` không tự chứng minh API đã từ chối nếu PEP bỏ qua policy. Cần **enforcement outcome** tại resource.

### 22.3. Policy version phải được lưu

Khi một user bị từ chối lúc 10:00 nhưng được cấp lúc 10:10, auditor phải biết **policy/attributes đã áp ở mỗi thời điểm**. Không nên diễn giải các event cũ bằng policy hiện tại rồi kết luận sai.

### 22.4. Least privilege trong log

Không cần ghi toàn bộ bản ghi hóa đơn/PII vào mỗi authz event. Nên dùng **resourceRef, classification, action, reasonCode và các claims tối thiểu**; thông tin chi tiết chỉ truy cập trong kho bảo vệ khi điều tra được phép.

## 23. Access request, approval và SoD events

Quyền truy cập thường bắt đầu từ một request, qua approval rồi đến target provisioning.

### 23.1. Chuỗi cần phân biệt

~~~text
AccessRequested
  -> ManagerApprovalRecorded
  -> ResourceOwnerApprovalRecorded
  -> SoDPolicyEvaluated
  -> AccessApproved
  -> EntitlementProvisionRequested
  -> EntitlementAppliedAtTarget
  -> EntitlementVerified
~~~

Một workflow có thể không yêu cầu mọi bước; policy phụ thuộc resource risk. Nhưng **approval không nên bị hiểu là target grant đã được xác nhận**.

### 23.2. Bằng chứng quyết định

Một event phê duyệt cần:

- **Ai trực tiếp quyết định** (actor).
- **Ai là người hưởng quyền** (beneficiary).
- **Action/resource/tenant/expiry** được duyệt.
- **Thẩm quyền reviewer** tại thời điểm quyết định.
- **Policy và SoD result**.
- **Căn cứ, thời điểm, workflow version**.
- **Approval ID/decision ID** làm khóa correlation.

Nếu reviewer được thay thế hoặc ủy quyền, cần ghi **reviewer ban đầu, substitute/delegate, reason và assignment version** khi policy yêu cầu. Không gán decision cho reviewer cũ nếu người khác thực hiện.

### 23.3. Event chống approval shopping

Nếu một quyền đã bị từ chối, người yêu cầu không được reset history bằng cách đổi reviewer rồi dùng `AccessApproved` không kèm appeal path. Các sự kiện từ chối, reassignment và appeal phải được lưu để phát hiện lách kiểm soát.

### 23.4. SoD violation là event độc lập

Một SoD conflict có thể được phát hiện khi **đề nghị quyền**, khi **thay role**, hoặc khi **reconciliation** phát hiện quyền thực tế. Cần phân loại giai đoạn và xử lý khác nhau.

## 24. SCIM, provisioning và events tại ứng dụng đích

**SCIM** là giao thức quản lý identity/resource thông qua API như Users/Groups (ví dụ theo các tiêu chuẩn RFC 7643/7644). **SCIM API response tự nó không định nghĩa một hệ event bus chung**; muốn có event-driven monitoring phải dùng logs/webhooks/connector outcomes hoặc API readback tùy sản phẩm.

### 24.1. Phân biệt các mốc

| Bản ghi | Nghĩa chính xác |
| --- | --- |
| **ProvisionRequested** | IGA đã yêu cầu cấp |
| **SCIMRequestSent** | Connector gửi HTTP request |
| **SCIMResponseSucceeded** | Target trả response thành công theo API contract |
| **ProvisioningObserved** | Readback nhìn thấy account/role |
| **EffectivePermissionVerified** | PEP/resource hành động đúng theo policy |
| **ReconciliationDriftDetected** | Desired và observed/effective lệch |
| **DeprovisionRequested** | Cần gỡ quyền/account |
| **DeprovisionApplied** | Target xác nhận thay đổi |
| **ResidualAccessDetected** | Sau revoke vẫn còn quyền hiệu lực |

### 24.2. Tình huống SaaS còn quyền

~~~text
18:00 Leaver event
18:01 SCIM PATCH active=false returned success
18:02 SaaS account active=false on management API
18:03 Existing SaaS browser session still permits read data
18:04 Reconciliation identifies RESIDUAL_SESSION
~~~

Không phát `AllAccessRemoved` chỉ vì SCIM management record hiển thị inactive.

### 24.3. Retry và idempotency

Một connector retry `POST /Users` sau timeout có thể tạo duplicate nếu không có matching/idempotent strategy. Cần kiểm **externalId/target ID mapping, create-vs-update semantics, authoritative match**, và không xem HTTP retry success là tạo account mới mà không readback.

### 24.4. Provisioning failures cũng là identity events hữu ích

Lỗi `HTTP 429`, `403`, schema conflict, stale ETag, unavailable target hoặc wrong tenant cần log **error code, retry class, target, correlation và remediation owner**, không log raw bearer token hoặc full sensitive payload.

## 25. Access recertification và orphan-access events

Một chiến dịch **access recertification** tạo event cho từng quyết định về quyền đang tồn tại.

### 25.1. Chuỗi ví dụ

~~~text
CampaignStarted
  -> ReviewItemAssigned
  -> ReviewerReassigned (nếu owner/Mover thay đổi)
  -> ReviewDecisionRecorded: KEEP / REVOKE / ESCALATE
  -> RemediationRequested
  -> EntitlementRemovedAtTarget
  -> RemovalVerified
~~~

### 25.2. Decision REVOKE không phải sự kiện “đã hết quyền”

`ReviewDecisionRecorded=REVOKE` là quyết định governance. Nếu SCIM không gỡ được role, event `ResidualEntitlementObserved` là bằng chứng cho **risk tồn dư** và cần follow-up.

### 25.3. Quyền mồ côi

Có thể phát `OrphanAccountDetected` khi:

- Account ở SaaS không map tới identity/relationship có hiệu lực.
- Service principal không còn owner/workload.
- Bot đã ngừng nhưng account ERP vẫn ACTIVE.
- Role admin không có approval/provenance hợp lệ.

Không tự xóa mọi orphan account ngay nếu có nguy cơ gián đoạn production; phải **triage risk, owner, dependency và remediation**. Nhưng cũng không mặc định KEEP vô hạn.

### 25.4. Certification evidence

Một event recertification phải giữ **actor reviewer, authority source, item/entitlement, decision, reason, deadline, assignment version, policy và remediation outcome**. Không ghi đè history khi đổi reviewer.

## 26. PAM/JIT, emergency access và privileged identity events

Quyền đặc quyền cần audit chặt vì tác động lớn.

| Sự kiện | Ý nghĩa | Hậu kiểm |
| --- | --- | --- |
| **ElevationRequested** | User/workload xin quyền cao | Authority, scope, risk |
| **ElevationApproved** | Reviewer cho phép một khoảng | Không phải active tại target |
| **ElevationActivated** | PAM/target cấp quyền | Thời hạn, role, session |
| **PrivilegedSessionStarted** | Shell/console/DB session mở | Actor, target, session ref |
| **PrivilegedActionPerformed** | Action thay đổi cấu hình/role | Audit target và commit |
| **ElevationExpired** | TTL kết thúc | Có active session còn không |
| **SessionTerminated** | PAM/target đóng phiên | Verify process/tunnel |
| **BreakGlassCredentialReleased** | Emergency credential được checkout | Custodian và incident ref |
| **EmergencyAccessUsed** | Account phục hồi đăng nhập | Native logs và purpose |
| **EmergencyAccessReviewed** | Hậu kiểm sau khẩn cấp | Rotation và residual grants |

### 26.1. Một event audit của PAM chưa đủ

PAM ghi session recording nhưng tài khoản có thể tạo **API key hoặc admin role mới** bên ngoài session. Sau emergency access phải phát/đối soát các event **privilege changes, token issuance, session closure, new credentials**.

### 26.2. Break-glass identity không nên bị loại khỏi logging

Để tài khoản khẩn cấp có thể phục hồi khi IdP outage, một số security controls phải có fallback; nhưng **native audit, credential custody journal và post-incident evidence** vẫn phải được bảo vệ và đồng bộ sau phục hồi.

### 26.3. Chặn lộ dữ liệu nhạy cảm

Đừng đính kèm video phiên đặc quyền hoặc toàn bộ command output chứa secret vào message bus thường; truyền **tham chiếu evidence được phân quyền**.

## 27. Non-human identities: service accounts, robots và workload

**Service-to-service identity** có OAuth client, cloud managed identity, certificate, SPIFFE ID hoặc Kubernetes ServiceAccount. **Robot/RPA** có thể dùng bot account đăng nhập UI/API. Chúng đều có lifecycle riêng với con người.

### 27.1. Event quan trọng

- `workload.registered`, `workload.owner.assigned`.
- `service.principal.created`, `service.principal.disabled`.
- `client.credential.issued`, `client.credential.rotated`, `client.credential.revoked`.
- `certificate.renewed`, `certificate.expired`, `trust.bundle.changed`.
- `federation.trust.changed`, `cloud.role.assigned`.
- `robot.job.started`, `robot.business.action.completed`, `robot.job.failed`.
- `workload.decommission.requested`, `workload.identity.removed.verified`.
- `service.owner.leaver.detected`, `orphan.workload.detected`.

### 27.2. Actor và owner khác nhau

Một API event có **actor=workload:orders-prod**, còn **technicalOwner=platform-team** và **resourceOwner=inventory-team**. Audit phải giữ sự khác biệt; không gán các API requests của robot cho developer đã tạo bot.

### 27.3. Owner Mover/Leaver không đồng nghĩa workload tự retire

Khi owner nghỉ, cần thu hồi **quyền quản trị của người cũ**, bàn giao owner và rà các credentials người đó từng tiếp cận; workload hợp lệ có thể tiếp tục hoạt động. Khi **chính workload ngừng nhiệm vụ**, cần gỡ client/trust/role và xác minh không còn access.

### 27.4. Token issuance và access còn hiệu lực

Đổi client secret có thể chặn issuance mới nhưng **access token đã phát** có thể còn dùng tới expiry hoặc khi PEP kiểm deny state. Event `client.credential.rotated` không tự chứng minh các token cũ bị vô hiệu.

### 27.5. Audit robot theo job/run

Một robot account có thể phục vụ hàng nghìn giao dịch. Cần gắn **robotId, principalId, jobId/runId, artifact revision, target transaction, tenant, action và outcome**. `runId` giúp correlation nhưng không thay **authenticated principal**.

## 28. CloudEvents, Security Event Token và sự tương thích

Khi tích hợp nhiều hệ, tổ chức có thể chọn **mô hình envelope dựa trên chuẩn đã có** thay vì tự thiết kế hoàn toàn.

### 28.1. CloudEvents

**CloudEvents** định nghĩa một tập thuộc tính envelope chung như `specversion`, `id`, `source`, `type`, có thể có `subject`, `time`, `datacontenttype` và `data`.

Ví dụ **minh họa** (không chứa định danh hay dữ liệu thật):

~~~json
{
  "specversion": "1.0",
  "id": "evt-hris-1881",
  "source": "/hris/employment",
  "type": "com.example.identity.relationship.ended.v2",
  "subject": "employment-A-1042",
  "time": "2027-03-31T18:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "identityId": "person-1042",
    "relationshipId": "employment-A-1042",
    "tenantId": "tenant-a",
    "effectiveAt": "2027-03-31T18:00:00Z",
    "aggregateVersion": 18
  }
}
~~~

Đây là CloudEvents-style message minh họa: **CloudEvents là envelope, không chuẩn hóa nội dung nghiệp vụ IAM của payload**. `source` và `type` không tự chứng minh thẩm quyền; cần producer authentication và policy.

### 28.2. Security Event Token và shared signals

Các hệ liên quan **Security Event Token (SET)**, **Shared Signals Framework, CAEP và RISC** có thể trao đổi thông tin về thay đổi security/access state tùy triển khai và profile.

Không nên giả định mọi sản phẩm hỗ trợ cùng loại tín hiệu, cùng schema, cùng thời gian xử lý hoặc cùng ngữ nghĩa thu hồi. Khi dùng, cần xác minh **sender trust, event type, subject identifiers, claims, receiver behavior và data-plane enforcement**.

### 28.3. Không chọn tiêu chuẩn chỉ vì phổ biến

Một tổ chức có thể dùng CloudEvents cho workflow nội bộ và native IdP logs cho SIEM, rồi normalize qua adapter. Điều cốt yếu là **semantic contract và mapping chính xác**, không phải đổi tên mọi payload thành một chuẩn.

### 28.4. Chuyển đổi vendor-specific events

Một vendor có thể log `user_suspended`, vendor khác là `account_disabled`. Canonical mapper phải xác định:

- Account có bị **chặn login mới** không?
- Group/role cũ có còn không?
- Session/token đã bị revoke chưa?
- Event mô tả **request** hay **observed state**?
- Timestamp là effective hay processed?
- Có target/tenant chính xác không?

Nếu chưa rõ, phân loại `UNKNOWN` và yêu cầu capability validation, không tự gộp thành `AccessRevoked`.

## 29. Bảo vệ event pipeline: xác thực, phân quyền và chống giả mạo

Identity events thường kích hoạt **cấp quyền, gỡ quyền hoặc chặn tài khoản**. Nếu attacker giả sự kiện, hậu quả có thể là **privilege escalation hoặc denial of service** diện rộng.

### 29.1. Kiểm soát bắt buộc theo rủi ro

| Rủi ro | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Forged event** | Attacker phát `AccessApproved` | Producer mTLS/token/signature, authorization |
| **Replayed event** | Gửi lại grant event cũ | Dedup, version, state guard |
| **Out-of-order event** | Joiner cũ đến sau Leaver | Monotonic state/version |
| **Cross-tenant spoof** | Event tenant-a tác động tenant-b | Tenant scoping từ trusted registry |
| **Schema injection** | Field mới thay nghĩa entitlement | Schema version/validation |
| **Log injection** | Username chứa newline giả audit record | Structured logs/escaping |
| **Queue tampering** | Consumer bị đưa nhầm topic/role | Broker ACLs, encryption, topic controls |
| **Poison message** | Payload lỗi gây retry vô hạn | Dead-letter, quarantine, backoff |
| **Privilege escalation by consumer** | Consumer có admin scope toàn tenant | Least privilege cho service identity |
| **Audit deletion** | Attacker xóa event sau grant | Tamper-evident storage, access separation |
| **PII leakage** | Payroll/ID docs vào logs | Redaction, data classification |
| **Availability attack** | Flood Leaver events | Rate limits, authority guard, incident response |

### 29.2. Không tin các trường actor do request tự khai

Một JSON có `actorRole=HR_ADMIN` không chứng minh caller là HR admin. Sử dụng **authenticated producer identity**, trusted source registry và authorization trên **event type/action/tenant**.

### 29.3. Broker ACLs là một phần IAM

Cần phân quyền:

- Producer nào được **publish** tới topic nào?
- Consumer nào được **subscribe** đến sự kiện nhạy cảm?
- Ai được **replay** hoặc reset consumer offset?
- Ai có thể **delete/alter retention policy**?
- Ai xem payload chứa employee status, failure reasons, privilege details?

Đây là quyền đặc biệt có thể dẫn đến rò rỉ danh tính hoặc kích hoạt workflow trái phép.

### 29.4. Bảo vệ trước event-driven denial of service

Một sự kiện Leaver hàng loạt giả mạo có thể khiến hệ disable hàng nghìn user. Hành động rủi ro cao nên có **source authority, anomaly thresholds, bulk action controls và chế độ manual escalation khi cần**, không mặc định trust mọi event đến bus.

## 30. Quyền riêng tư, data minimization và secret hygiene

Identity events chứa dữ liệu nhạy cảm: trạng thái nhân sự, role, authentication failures, vị trí/thiết bị, địa chỉ mạng và đôi khi thông tin về sự cố bảo mật.

### 30.1. Thiết kế theo mục đích

Một event dùng để **chặn role do Leaver** thường chỉ cần **identityRef, relationshipId, effectiveAt, event type, source và policy**. Nó hiếm khi cần lý do cá nhân chi tiết của việc nghỉ việc.

Một event dùng để **phân tích failed-login patterns** có thể cần thời điểm, client, reason code, network/device context đã được giảm nhạy cảm và subject match confidence. Không tự gộp thành profile giám sát không giới hạn.

### 30.2. Trường nên tránh trong stream/log phổ thông

- Password, OTP, TOTP seed, MFA recovery codes, passkey private material.
- Raw access/refresh tokens, signed client assertions còn dùng được, session cookies.
- Giấy tờ định danh, biometric templates, hình xác minh.
- Secrets từ vault, cloud keys, private certificates.
- Full HR record/medical/disciplinary details không cần cho IAM.
- Payload đối tượng kinh doanh đầy đủ nếu resource reference đã đủ.
- Unmasked PII không tương xứng mục đích/authorization.

### 30.3. Chiến lược tham chiếu

~~~json
{
  "eventType": "identity.proofing.completed",
  "subjectRef": "person-1042",
  "result": "VERIFIED",
  "assuranceRef": "policy-level-2",
  "evidenceRef": "protected-evidence-550",
  "policyVersion": "proofing-v4"
}
~~~

`evidenceRef` chỉ là **tham chiếu**; truy cập evidence thật yêu cầu authorization riêng, có audit và retention.

### 30.4. Retention theo loại sự kiện

Có thể phân loại:

- **Operational retry events:** retention ngắn tùy yêu cầu.
- **Authentication/security logs:** retention để phát hiện/điều tra.
- **Approval/provisioning/audit evidence:** retention theo hợp đồng/chính sách kiểm toán.
- **Sensitive proofing evidence:** bảo vệ riêng và xóa theo chính sách.
- **Aggregate metrics:** có thể giữ lâu hơn nếu không còn data cá nhân cần thiết.

Không có thời hạn retention chung cho mọi quốc gia hoặc mọi loại dữ liệu. Cần **policy hợp lệ, legal hold khi áp dụng, data minimization và quyền xử lý dữ liệu**.

### 30.5. Pseudonymization không phải biến dữ liệu thành vô danh hoàn toàn

Một identityId giả danh vẫn có thể được nối về con người qua registry; phải tiếp tục bảo vệ quyền truy cập và hạn chế chia sẻ. Không xem việc thay email bằng `person-1042` là hết mọi nghĩa vụ riêng tư.

## 31. Tính toàn vẹn của Identity event và bằng chứng kiểm toán

Những event về cấp quyền, sửa policy, reset MFA và Leaver có giá trị **chứng cứ**. Kẻ tấn công có đặc quyền có thể cố **xóa/sửa log**, làm thay đổi thứ tự, giả kết quả hoặc ngắt ghi log trong khi thực hiện thao tác.

### 31.1. Các lớp bảo vệ

- **Transport integrity:** kênh mTLS/TLS hoặc cơ chế signing phù hợp cho producer/broker.
- **Authentication/authorization:** xác minh producer identity, giới hạn publish/subscribe/replay theo topic, tenant và event type.
- **Append-only/tamper-evident:** hạn chế quyền sửa/xóa, có thể dùng digest, hash chain hoặc chữ ký theo threat model.
- **Immutable/retention controls:** vùng lưu chứng cứ chống xóa/sửa ngoài quy trình, có lifecycle chính sách.
- **Cross-source correlation:** so event từ HRIS/IGA với IdP/SaaS/PEP để phát hiện khoảng trống.
- **Monitoring of logging pipeline:** cảnh báo stream dừng, volume giảm bất thường, consumer lùi offset hoặc audit export bị lỗi.
- **Role separation:** người có thể cấp role admin không mặc nhiên có quyền xóa audit về hành động đó.
- **Incident evidence management:** quản lý access, provenance, legal hold và chuỗi bàn giao khi cần.

### 31.2. Hash không chứng minh sự kiện đã được ghi đầy đủ

Một hash chain có thể giúp phát hiện **bản ghi đã lưu bị thay đổi**, nhưng không chứng minh mọi hành động thực tế đều được ghi từ đầu. Nếu producer không phát một event, chain vẫn có thể hợp lệ.

Cần thêm **completeness checks**: sequence gap, source heartbeat, outbox backlog, target activity readback, đối soát theo số lượng và monitoring pipeline.

### 31.3. Đảm bảo nguồn và thời gian

Nếu một event được ký bởi hệ đã bị chiếm, chữ ký có thể hợp lệ nhưng nội dung vẫn độc hại. Trust vào nguồn cần đi kèm **producer hardening, authority checks, role separation, key rotation và independent reconciliation**.

### 31.4. Audit bất biến không đồng nghĩa dữ liệu vĩnh viễn

Cần phối hợp integrity với **retention, data protection, hạn chế truy cập và xóa dữ liệu theo chính sách**. Không lấy “append-only” làm lý do lưu PII hoặc secrets vô thời hạn.

## 32. Identity events trong SIEM và phát hiện rủi ro

Một sự kiện đơn lẻ hiếm khi đủ kết luận compromise. **SIEM/detection rules** tương quan theo identity, client, time, device, resource, tenant và actor.

### 32.1. Các chuỗi cần theo dõi

| Chuỗi sự kiện | Dấu hiệu | Hành động kiểm tra |
| --- | --- | --- |
| **MFA reset → new factor → privileged role** | Có thể là account takeover | Verify recovery/approval, actor và device |
| **Failed login burst → success → data export** | Credential attack / bất thường | Kiểm IP/device, risk, business context |
| **Leaver effective → API PERMIT** | Quyền tồn dư sau offboarding | Revoke session/role, review target outcome |
| **Mover → old role still used** | Stale entitlement/JWT claim | Kiểm PEP, target role và expiry |
| **Service owner Leaver → new client secret** | Người cũ/automation không còn hợp lệ | Kiểm actor, vault, CI/CD và approval |
| **Break-glass login outside incident** | Lạm dụng quyền khẩn cấp | Security escalation và native audit |
| **Role granted → audit disabled** | Có thể che giấu đặc quyền | Review change control và log integrity |
| **Privilege elevation → policy change → new token** | Privileged persistence risk | SoD, actor và credential audit |
| **Unmanaged user → SCIM disable failed** | Deprovision drift | Retry, block effective access |
| **Robot run outside schedule → export** | Automation misuse | Kiểm artifact/run ownership |
| **Refresh-token reuse detected** | Token theft hoặc client concurrency | Validate signal và issuer behavior |
| **Identity linking changed → account permissions expanded** | Merge/mapping risk | Manual review identity graph |

### 32.2. Cẩn trọng false positives

- Nhân viên công tác có thể đăng nhập từ mạng khác.
- Một hệ có thể retry MFA nhiều lần do lỗi thiết bị.
- SCIM sync chậm có thể tạo khoảng lệch nhất thời trong giới hạn policy.
- Một bot được phép chạy ngoài giờ và xuất báo cáo theo lịch hợp lệ.

Detection rule cần **risk context, allowlisted maintenance window, source confidence, business approval và response owner**; không tự khóa hàng nghìn identity vì một điều kiện mơ hồ.

### 32.3. “No event” có thể là tín hiệu

Nếu bình thường IdP tạo hàng nghìn auth events nhưng stream đột ngột dừng, có thể là **logging outage hoặc pipeline attack**. Cần heartbeat/volume anomaly alerts và kiểm các hệ nguồn thay vì xem “không có cảnh báo nghĩa an toàn”.

### 32.4. Detection không tự thực hiện remediation

Một alert `ResidualAccessDetected` cần workflow có **owner, target, policy, severity, SLA, triage, action và verification**, không chỉ thêm vào dashboard.

## 33. Correlation, causality và event-driven troubleshooting

Khi phát hiện sai lệch quyền, người vận hành cần **dò từ nguyên nhân đến kết quả** theo correlation ID, nhưng vẫn phân biệt quan hệ nhân quả thật với việc các event chỉ xảy ra gần nhau.

### 33.1. Mẫu chuỗi truy vết

~~~text
HRIS evt-1001: Mover effective
    correlationId = jml-1042-v17
    aggregateVersion = 17

IGA evt-1002: Desired roles recalculated
    causationId = evt-1001
    removed = CRM.SalesAdmin

SCIM evt-1003: Deprovision request sent
    causationId = evt-1002
    target = crm-saas

SCIM evt-1004: Target returned 429
    causationId = evt-1003
    retry = scheduled

Audit evt-1005: CRM role still observed
    correlationId = jml-1042-v17
    result = RESIDUAL_ACCESS
~~~

### 33.2. Correlation ID không thay sự kiện gốc

`correlationId` có thể chỉ mô tả workflow chung. Muốn chứng minh event nào kích hoạt command nào, dùng **causation ID và target operation ID**; muốn chứng minh account/role ở target, cần **source/target evidence**.

### 33.3. Truy vết across async boundaries

Một request ban đầu tạo outbox, worker xử lý sau vài phút và SCIM target trả 429. Trace ID theo HTTP request đầu tiên có thể không còn; consumer nên tạo trace mới nhưng mang **business correlation và causation references** để điều tra không bị đứt.

### 33.4. Không tái tạo trạng thái lịch sử bằng snapshot hiện tại

Một audit về grant tháng trước phải dùng **policy, owner, manager và entitlement provenance tại thời điểm grant**, không đơn giản dựa trên current registry vì các quan hệ có thể đã đổi.

## 34. Reconciliation: nối Identity event với trạng thái thực tế

**Reconciliation** là cầu nối giữa **sự kiện dự kiến/thực thi** và **quyền thực tế**.

### 34.1. Ba lớp cần đối chiếu

~~~text
DESIRED STATE:
  Policy/JML nói entitlement SalesAdmin cần bị gỡ.

OBSERVED STATE:
  SaaS account vẫn có group SalesAdmin.

EFFECTIVE ACCESS:
  SaaS API với session đã cấp vẫn PERMIT approve discount.

Identity event lineage:
  HRIS Mover -> IGA revoke command -> SCIM retry failed
  -> target readback EXTRA_ROLE -> PEP verification
~~~

### 34.2. Ma trận phân loại

| Desired | Observed/effective | Event nên phát | Hành động |
| --- | --- | --- | --- |
| User Leaver, no access | SaaS account ACTIVE | `residual.account.detected` | Disable, revoke, incident nếu cần |
| Old role removed | Group vẫn tồn tại | `entitlement.drift.extra` | Gỡ role, kiểm nguồn |
| Grant được duyệt | Target chưa có role | `entitlement.drift.missing` | Retry sau xác minh approval |
| Session revoked | JWT cũ vẫn PERMIT | `session.revocation.ineffective` | PEP/denylist/token strategy |
| Workload retired | OAuth client vẫn mint token | `workload.orphan.detected` | Revoke client/trust |
| Manager Mover | Owner registry vẫn chỉ người cũ | `reviewer.authority.stale` | Reassign review |
| Target không phản hồi | Không biết quyền có tồn tại không | `identity.state.unknown` | Exception và readback lại |
| Account status inactive | Access denied và roles đã gỡ | `deprovision.verified` | Close theo policy |

### 34.3. Reconciliation event là một fact về phép đo

Event `entitlement.drift.extra` cần có **observedAt, evidence source, snapshot version, target, tenant, identity mapping confidence và current desired baseline**. Nếu connector không đọc được target, **UNKNOWN** khác **NO_RIGHTS**.

### 34.4. Đừng tự provision lại vì snapshot cũ

Một quyền đã bị thu hồi hợp lệ do Leaver không được tái tạo chỉ vì một event Joiner cũ hoặc snapshot recertification đã lưu được replay. Consumer phải so **current authoritative lifecycle state** trước khi thực hiện grant.

## 35. Java/Spring: mô hình event envelope và validation

Có thể biểu diễn identity event bằng một **record bất biến** trong Java, dùng DTO để deserialize, rồi tách logic validation và policy.

### 35.1. Mô hình Java minh họa

~~~java
// Ví dụ Java hiện đại, mô hình hướng dẫn; không phải hệ thống build độc lập.
record IdentityRef(
        String identityId,
        String relationshipId,
        String tenantId) {}

record IdentityEvent<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        String sourceSystem,
        String sourceEventId,
        IdentityRef subject,
        String actorPrincipalId,
        Instant occurredAt,
        Instant effectiveAt,
        long aggregateVersion,
        String correlationId,
        String causationId,
        T payload) {}

record RelationshipEndedPayload(
        String newStatus,
        String reasonCode) {}
~~~

### 35.2. Những gì type system chưa tự đảm bảo

Một record Java hợp lệ vẫn có thể chứa:

- `sourceSystem="hris"` nhưng request đến từ caller không được phép.
- `identityId` thuộc tenant khác.
- `aggregateVersion=-5` hoặc event ID trùng.
- `effectiveAt` không hợp lệ so với policy.
- Mã event giả `AccessApproved` không có approval artifact.
- `actorPrincipalId` tự khai.

Cần **schema validation, authenticated producer, authorization, identity mapping, policy kiểm trạng thái và audit** trước khi xử lý.

### 35.3. Thứ tự kiểm tra tối thiểu

~~~text
1. Authenticate event transport/sender.
2. Validate event signature or trusted delivery channel.
3. Validate schema and supported version/type.
4. Check producer may publish this event type/tenant.
5. Resolve subject via authoritative source; check mapping.
6. Dedup event ID and compare aggregate version.
7. Evaluate effectiveAt/current policy and target scope.
8. Persist event and resulting commands atomically if possible.
9. Dispatch side effects with idempotency.
10. Read back target state, record verification.
~~~

## 36. Java/Spring: transactional outbox và idempotent consumer

### 36.1. Producer service minh họa

~~~java
// PSEUDOCODE: các repository, services và type là mô hình riêng.
@Service
class IdentityLifecycleService {

    private final IdentityRepository identities;
    private final IdentityEventOutbox outbox;

    @Transactional
    public void applyAuthoritativeMover(
            VerifiedHrisEvent event) {

        IdentityRecord current =
            identities.lockByRelationship(event.relationshipId());

        if (event.aggregateVersion() <= current.sourceVersion()) {
            return; // duplicate/stale; record diagnostics elsewhere
        }

        if (!current.matchesTenant(event.tenantId())) {
            throw new IdentityMappingConflict();
        }

        current.applyVerifiedRelationshipChange(event);
        identities.save(current);

        outbox.append(
            IdentityEventFactory.moverApplied(event, current)
        );
    }
}
~~~

**Nguyên tắc:** một local transaction lưu **identity state + outbox record**, nhưng không coi event đã tới SaaS hoặc role đã thay.

### 36.2. Consumer pseudo có dedup và target commands

~~~java
// PSEUDOCODE: đơn giản hóa transaction/locking/exception strategy.
@Service
class IdentityEventHandler {

    private final ProcessedEventRepository processed;
    private final IdentityRegistry registry;
    private final PolicyEngine policy;
    private final CommandOutbox commands;

    @Transactional
    public void onEvent(VerifiedIdentityEvent event) {

        if (processed.alreadySeen(
                event.sourceSystem(), event.eventId())) {
            return;
        }

        IdentityState state = registry.current(
            event.identityId(), event.relationshipId());

        if (event.aggregateVersion() < state.sourceVersion()) {
            processed.markIgnoredStale(event);
            return;
        }

        PolicyDecision decision =
            policy.calculateDesiredChange(state, event);

        commands.appendAuthorizedActions(
            event.eventId(),
            decision.targetOperations()
        );

        processed.markAccepted(event);
    }
}
~~~

**Ví dụ không phải mã chạy ngay**. Triển khai thực tế cần xử lý:

- Race giữa `alreadySeen` và `markAccepted`: **unique constraint/transaction**.
- Version bằng nhau nhưng event khác nhau: conflict handling, không âm thầm gộp.
- Atomicity giữa result state, processed marker và outbox.
- Authorization của target connector trên **resource/tenant/action**.
- Trường hợp thiếu event trung gian: snapshot refresh/quarantine, không áp quyền từ dữ liệu không chắc.
- Retry/backoff, dead-letter và phân biệt transient/permanent failure.
- Bảo vệ audit khi bỏ qua event stale.
- `Leaver` state guard để một async Joiner command cũ không tái provision.

### 36.3. Không thực hiện side effect không được kiểm soát trong DB transaction

Một HTTP SCIM request thực hiện bên trong transaction DB có thể thành công ở SaaS rồi DB rollback; retry làm sai lệch quyền. **Command outbox** giúp tách commit nội bộ với external side effects và hỗ trợ reconciliation.

### 36.4. Mô hình consumer có thể phân thành hai loại

- **Operational consumer:** có quyền điều phối account/role theo policy, thường cần current-state check và idempotency.
- **Analytics/audit consumer:** chỉ đọc/lưu/phân tích events, không được quyền cấp lại access khi replay.

Tách quyền hai loại tránh việc người phân tích log vô tình có capability provision/revoke trong production.

## 37. SQL: kiểm tra sự kiện trùng, trễ và chênh lệch quyền

Giả sử data warehouse có bảng đã được **chuẩn hóa, time zone rõ và giới hạn PII**:

~~~sql
-- Schema minh họa, không phải lệnh DDL triển khai thật.
-- identity_event_log(
--   event_id, source_system, event_type,
--   subject_identity_id, relationship_id, tenant_id,
--   occurred_at, effective_at, ingested_at,
--   aggregate_version, correlation_id, outcome
-- )
~~~

### 37.1. Phát hiện event ID trùng trong cùng source

~~~sql
SELECT
    source_system,
    event_id,
    COUNT(*) AS occurrences
FROM identity_event_log
GROUP BY source_system, event_id
HAVING COUNT(*) > 1;
~~~

**Trùng khi thu nhận** không nhất thiết là bug nghiệp vụ; broker có thể at-least-once. Điều cần kiểm là consumer không gây **side effect lặp**.

### 37.2. Tìm sự kiện Leaver được nhận trễ

~~~sql
SELECT
    event_id,
    subject_identity_id,
    relationship_id,
    effective_at,
    ingested_at,
    (ingested_at - effective_at) AS effective_to_ingest_lag
FROM identity_event_log
WHERE event_type = 'identity.relationship.ended'
  AND ingested_at > effective_at
ORDER BY effective_to_ingest_lag DESC;
~~~

Cú pháp chênh lệch timestamp trên đây theo **PostgreSQL-style SQL**, có thể cần điều chỉnh theo warehouse. Không dùng chênh lệch này làm bằng chứng duy nhất của rủi ro: event có thể được nhập theo policy, hoặc source timestamps có độ chính xác khác nhau.

### 37.3. Phát hiện account observed nhưng không có desired entitlement

~~~sql
SELECT
    o.identity_id,
    o.tenant_id,
    o.target_account_id,
    o.entitlement_id
FROM observed_entitlement AS o
LEFT JOIN desired_entitlement AS d
    ON d.identity_id = o.identity_id
   AND d.tenant_id = o.tenant_id
   AND d.target_account_id = o.target_account_id
   AND d.entitlement_id = o.entitlement_id
WHERE d.identity_id IS NULL;
~~~

Đây chỉ là **truy vấn minh họa** cho quyền thừa. Hệ thật cần chuẩn hóa **snapshot time, group-derived permissions, role expansion, deny policies, lifecycle effectiveAt, multi-relationship và identity linking confidence**.

### 37.4. Không dùng SQL analytics làm authority cấp quyền

Một bảng log có thể đến trễ hoặc chứa dữ liệu chưa kiểm. Hệ provision/revoke phải dựa vào **identity registry/approval/current policy có thẩm quyền**, không tự cấp role chỉ vì data warehouse hiển thị một row.

## 38. Case study A: Leaver event đến trễ và SaaS chưa thu hồi quyền

### 38.1. Bối cảnh

Một nhà thầu dùng IdP SSO, SaaS ERP và VPN. HRIS kết thúc hợp đồng lúc 18:00 nhưng webhook có sự cố, event chỉ đến IGA lúc 18:12.

### 38.2. Event timeline

~~~text
18:00  HRIS relationship ended (effectiveAt)
18:03  ERP local session performs invoice.read
18:07  VPN connection still active
18:12  HRIS event ingested by IAM
18:13  IGA security block + revoke commands
18:14  IdP denies new sign-in
18:15  SCIM marks ERP user inactive
18:16  ERP browser session still permits read
18:17  Reconciliation emits RESIDUAL_SESSION
18:20  SaaS session terminated via supported method
18:21  Effective denial verified
~~~

### 38.3. Phân tích

- `Leaver` là **nghiệp vụ có hiệu lực lúc 18:00**, không phải 18:12.
- IdP disabled không chặn ngay local session ERP.
- `SCIM active=false` không tự chứng minh no effective access.
- Điều tra phải xem hoạt động 18:00–18:21 theo mức rủi ro.
- `RESIDUAL_SESSION` cần owner/remediation và evidence, không xóa khỏi dashboard khi nhận SCIM 200.

### 38.4. Bài học

**Identity event giúp kết nối thời gian nghiệp vụ, các command thực thi và trạng thái quyền thực tế.** Nếu mất phân biệt các tầng này, offboarding có thể được báo hoàn tất sai.

## 39. Case study B: Mover, event sai thứ tự và quyền admin tồn dư

### 39.1. Bối cảnh

Một nhân viên chuyển Sales → Finance. HRIS phát Mover version 10 rồi Leaver version 11 do hợp đồng kết thúc ngay sau đó. Broker giao v11 trước v10.

### 39.2. Hành vi sai

~~~text
Consumer handles v11:
  disable account + revoke SalesAdmin

Consumer later handles v10:
  add FinanceReader + enable account

Result:
  Leaver becomes ACTIVE again.
~~~

### 39.3. Thiết kế đúng

- **Aggregate version/current authoritative state** cho biết v10 đã stale khi v11 được áp dụng.
- Consumer không re-enable identity chỉ từ Mover event cũ.
- Các target commands chứa identity relationship/version guard.
- IGA reconcile với HRIS current state và observed roles.
- Event stale được audit/quarantine nếu cần, không tự xóa bằng chứng.
- Nếu có rehire thật, phải có **new relationship/effective event** và approval thích hợp.

### 39.4. Bài học

**Event ordering và identity lifecycle guard** là kiểm soát bảo mật, không chỉ vấn đề message queue reliability.

## 40. Case study C: Service account owner Leaver và robot còn chạy

### 40.1. Bối cảnh

Robot `rpa-invoice-prod` dùng account ERP và secret trong vault. Technical owner chuyển bộ phận rồi nghỉ việc, nhưng robot vẫn chạy hàng đêm.

### 40.2. Sự kiện cần nối

~~~text
HRIS: owner Mover
IGA: owner responsibility changed
Vault: old owner access removed
Robot Registry: new owner assigned
Security: credential previously exposed? risk review
RPA: approved job continues
ERP: robot role still scoped correctly
Reconciliation: no unauthorized human access or orphan bot
~~~

Nếu robot nghỉ hoạt động:

~~~text
RobotRetirementApproved
  -> Scheduler disabled
  -> Credentials revoked
  -> ERP account disabled
  -> Local sessions/token issuance blocked
  -> Target readback verified
  -> Audit archived under retention policy
~~~

### 40.3. Bài học

**JML của người sở hữu và lifecycle của non-human identity là hai dòng sự kiện khác nhau.** Owner Leaver không có nghĩa lập tức xóa bot production; cũng không cho phép người cũ giữ credential/vault role.

## 41. Ma trận kiểm thử Identity events và pipeline

| Ca kiểm thử | Điều kiện đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| 1. Valid HRIS Joiner | Identity/relationship đúng, future effectiveAt | Không cấp production sớm |
| 2. Joiner duplicate | Cùng sourceEventId giao hai lần | Một lần state transition/side effect |
| 3. Joiner canceled | Event cancel đến trước start effective | Chặn pending grants |
| 4. Mover đúng hạn | Sales → Finance | Gỡ quyền cũ, đánh giá cấp quyền mới |
| 5. Late Mover | Event v10 sau Leaver v11 | Stale event không re-enable |
| 6. Missing aggregate version | Source sequence không đầy đủ | Current-state validation/quarantine theo policy |
| 7. Same email, different identity | Hai subjects có email giống | Không merge mù |
| 8. Unresolved subject | Mapping source → identity không chắc | CONFLICT, không cấp role |
| 9. Cross-tenant event | Producer tenant-a gửi event tenant-b | DENY |
| 10. Forged producer | Caller không có quyền phát Leaver | Reject và alert |
| 11. Replayed signed event | Event cũ được phát lại | Idempotent/stale guard |
| 12. Invalid schema version | Consumer không hiểu payload | Reject/quarantine, không side effect |
| 13. Event with secret | Password/access token trong payload | Schema/privacy validation hoặc redaction |
| 14. Malicious log string | Username có newline/control chars | Structured logging, không log forging |
| 15. HRIS effectiveAt future | Termination nhập sớm | Áp thay đổi đúng thời điểm |
| 16. HRIS event ingested late | Leaver hiệu lực 12 phút trước | Revoke và review exposure window |
| 17. Two relationships | Một hợp đồng kết thúc | Revoke đúng scoped grants |
| 18. SCIM 200 but target role remains | Connector response thành công | Residual state, không VERIFIED |
| 19. SaaS local session persists | Account inactive nhưng session còn | Session exception/revocation |
| 20. PEP permits after revoke | Old JWT/group claim còn | Residual-access alert |
| 21. Authentication failure | Asserted username không verified | Không gán chắc actor vào identity |
| 22. OIDC login success | User auth thành công | Không tự coi mọi API được phép |
| 23. Authorization DENY ignored | PDP deny, target vẫn chạy | PEP enforcement gap |
| 24. Reviewer reassignment | Reviewer cũ mất quyền | Audit actor thật và version |
| 25. SoD exception | Bot tự tạo và tự approve | Chặn/truy vết theo policy |
| 26. PAM recording gap | Privileged session có action nhưng thiếu log | Evidence gap và remediation |
| 27. Break-glass usage | Emergency login không có incident | Alert và security review |
| 28. Service owner Leaver | Bot vẫn cần chạy | Thu hồi human rights, bàn giao owner |
| 29. Robot retired | ERP account vẫn enabled | Orphan/residual event |
| 30. Outbox crash after commit | DB đã ghi, broker chưa nhận | Dispatcher retry đúng event ID |
| 31. Broker duplicate | Consumer nhận hai bản ghi | Idempotency và no duplicate provisioning |
| 32. Broker out-of-order | Event v12 trước v11 | Monotonic state/refresh |
| 33. Consumer crash after target call | Target đã áp, ack mất | Retry safe + readback |
| 34. Poison message | Payload malformed gây retry mãi | Quarantine, alert, không tắc queue |
| 35. SIEM stream silent | Không có auth events bất thường | Heartbeat/volume alert |
| 36. Missing target readback | Connector không trả dữ liệu | UNKNOWN, không tự PASS |
| 37. Audit tampering | Cố xóa quyền grant event | Tamper detection / access separation |
| 38. Source signing key compromised | Event signature vẫn hợp lệ | Independent trust/risk response |
| 39. Analytics replay | Đọc lại event lịch sử | Không tự gọi SCIM grant |
| 40. Data retention expired | Event chứa PII hết hạn giữ | Lifecycle xử lý theo policy và legal hold |
| 41. Concurrent role commands | Revoke và grant tới cùng target | Ordering/current policy guard |
| 42. Wrong effective-time zone | Chênh lệch UTC/local | Test timezone và clock handling |

### 41.1. Kiểm thử end-to-end

~~~text
Authoritative source emits identity event
  -> Transport/producer authenticated
  -> Schema/semantic/tenant/identity validated
  -> Current version and effectiveAt evaluated
  -> Event stored and outbox/command recorded
  -> Consumer processes idempotently
  -> IdP/SCIM/PAM/target applies authorized change
  -> Target observed state read back
  -> Effective access verified where required
  -> Audit/KPI/exception updated
~~~

Một test chỉ xác nhận message xuất hiện trên broker **không chứng minh IAM đã cấp hoặc thu hồi đúng quyền**.

## 42. KPI cho Identity logging và event quality

| KPI | Đo điều gì? | Tránh nhầm |
| --- | --- | --- |
| **Authoritative event coverage** | Các source JML/IdP/SCIM/PAM có event mapping | Đếm event messages thay vì coverage |
| **Event validation failure rate** | Schema/authority/mapping invalid | Không gộp mọi reject là lỗi IAM |
| **Source-to-ingest latency** | Chậm từ nguồn đến pipeline | Không lẫn effectiveAt với occurredAt |
| **Effective-to-denial latency** | Leaver/revoke có hiệu lực tới lúc PEP DENY | Không chỉ đo SCIM 200 |
| **Event dedup effectiveness** | Duplicate không tạo side effect lặp | Không cố loại mọi duplicate ở broker |
| **Out-of-order event count** | Event tới không theo aggregate version | Không tự áp stale state |
| **Identity mapping conflict rate** | Subject chưa map chắc chắn | Không gán nhầm bằng email |
| **Outbox/backlog age** | Event/chỉ thị chưa phát hoặc đang treo | Không che consumer outage |
| **Dead-letter unresolved age** | Message hỏng chưa xử lý | Không xóa DLQ vô căn cứ |
| **Provisioning-to-verified latency** | Từ approval tới target match | Không coi request sent là complete |
| **Residual entitlement count** | Quyền còn sau revoke/Mover/Leaver | Phân rủi ro và target |
| **Audit evidence completeness** | Actor, source, policy, target, outcome đủ | Không ghi secrets để “đầy đủ” |
| **Event integrity incidents** | Tamper/gap/unauthorized publish | Không dựa hash duy nhất |
| **Security signal detection delay** | Event rủi ro tới alert triage | False positives cần theo dõi |
| **Privileged action coverage** | PAM/cloud/admin changes có audit | Session recording không đủ |
| **Non-human ownership coverage** | Service/robot principal có owner hợp lệ | Không coi người từng deploy là owner mãi |
| **Reconciliation unknown rate** | Target không xác minh được | UNKNOWN khác NO_ACCESS |
| **Privacy policy conformance** | Redaction, retention, access enforcement | Giữ nhiều dữ liệu không phải chất lượng |

Chỉ số cần phân đoạn theo **tenant, risk tier, source, target, loại identity và thời gian**, tránh một trung bình tốt che một hệ privileged access đang không có log.

## 43. Checklist thiết kế Identity event

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Event type phản ánh fact/request/outcome đúng? | Event taxonomy và contract |
| Có xác định source authority cho từng thuộc tính? | Ownership/provenance matrix |
| Có identityId/relationshipId/tenant scope? | Canonical schema |
| Có tách subject, actor, resource và target? | Event DTO và audit test |
| Có eventId/sourceEventId cho dedup? | Producer/consumer contract |
| Có aggregate version hoặc current-state guard? | Out-of-order tests |
| Có effectiveAt khác occurredAt/ingestedAt? | Lifecycle time semantics |
| Có schemaVersion và backward-compatibility plan? | Schema registry/contract test |
| Producer có được xác thực và phân quyền event type? | mTLS/token/signature và ACL |
| Có validation khi source identity chưa link? | Conflict queue/workflow |
| Có outbox hoặc delivery strategy đáng tin? | State/outbox transaction tests |
| Consumer có idempotent và replay guard? | Retry test |
| Có dead-letter và alert khi consumer không xử lý? | Monitoring và remediation |
| Có phân biệt command sent, target applied và verified? | State machine |
| Có cảnh báo Leaver nhận trễ và residual access? | Latency/PEP evidence |
| Có bảo vệ các session/token còn hiệu lực? | Session/issuer/PEP integration |
| IdP login event có tách from authz decision? | Authentication/authorization logs |
| SCIM capability có được kiểm từng target? | Connector matrix |
| Có liên kết access approval/recertification decisions? | Decision correlation refs |
| PAM/JIT/break-glass có native evidence? | Privileged audit |
| Robot/service account events có owner/run? | Workload inventory |
| Có hỗ trợ lifecycle owner Mover/Leaver? | JML delegation and custody tests |
| Có chống cross-tenant event spoof/replay? | Negative tests |
| Có chống log forging/injection và audit tamper? | Structured logs, integrity controls |
| Có heartbeat và completeness check khi stream im lặng? | Pipeline monitoring |
| Có privacy/data minimization cho HR/proofing/MFA? | Redaction, classification |
| Có retention/hold/deletion đúng policy? | Log governance |
| Có bảo vệ quyền replay/delete/subscribe? | Broker/storage ACLs |
| Có đối chiếu desired vs observed vs effective access? | Reconciliation |
| Event thất bại/UNKNOWN có owner và SLA? | Exception tickets |
| Có lưu policy/source versions để điều tra lịch sử? | Audit lineage |
| Có runbook khi event pipeline unavailable? | Fault-handling exercise |
| Có kiểm event replay không gây provision lại? | Analytics-vs-operational separation |

## 44. Những nhầm lẫn thường gặp

1. **“Identity event là mọi dòng log có chữ username.”** Event phải có semantic contract, source và subject context.
2. **“Event từ HRIS luôn có hiệu lực ngay khi nhập.”** Cần effectiveAt và policy.
3. **“Email là ID duy nhất của một người.”** Email có thể đổi, trùng hoặc tái sử dụng.
4. **“Actor và subject luôn cùng một người.”** Workflow/admin/service có thể hành động lên người khác.
5. **“SCIM 200 là user đã mất mọi quyền.”** Session/token và local role có thể tồn dư.
6. **“AccessApproved nghĩa entitlement đã có.”** Approval khác execution/verification.
7. **“REVOKE decision nghĩa role đã gỡ.”** Cần target outcome và readback.
8. **“Broker giao event exactly once nên target không cần idempotency.”** End-to-end side effects vẫn có thể lặp.
9. **“Event đến sau thì luôn mới hơn.”** Có duplicate/replay/out-of-order delivery.
10. **“Timestamp đủ thay sequence/version.”** Các nguồn có clock skew và retry.
11. **“Cùng correlationId là chứng minh nhân quả.”** Cần causation/evidence.
12. **“CloudEvents tự định nghĩa toàn bộ nghiệp vụ IAM.”** Chỉ định nghĩa envelope chung.
13. **“Có chữ ký nên event không thể chứa thông tin sai.”** Signed compromised producer vẫn rủi ro.
14. **“Audit store có hash chain là toàn bộ hoạt động đã được log.”** Không chứng minh completeness.
15. **“Đẩy logs vào SIEM là đã audit an toàn.”** Cần integrity, retention, authorization và event quality.
16. **“Log đầy đủ là phải ghi token/password.”** Secrets không nên xuất hiện trong log.
17. **“ID token OIDC là audit record.”** Token khác sự kiện và có PII/rủi ro replay.
18. **“Login success nghĩa người dùng có quyền đọc mọi dữ liệu.”** AuthN khác AuthZ.
19. **“SIEM alert chứng minh tài khoản đã bị chiếm.”** Alert cần triage và ngữ cảnh.
20. **“Không có event đáng ngờ nghĩa không có sự cố.”** Logging gap có thể che sự cố.
21. **“Robot không có người thì không cần owner.”** Non-human identity cần accountability.
22. **“Owner Leaver thì mọi workload do họ tạo phải xóa ngay.”** Cần chuyển owner và đánh giá purpose.
23. **“SCIM quản lý mọi client secret/certificate.”** Không mặc định như vậy.
24. **“Một event không hợp lệ có thể bỏ qua không cần log.”** Cần quarantine/correlation bảo mật.
25. **“Event cũ replay trong analytics an toàn cho provisioning.”** Phải tách side-effect consumers.
26. **“Mọi error đều có thể retry vô hạn.”** Poison message cần DLQ và xử lý riêng.
27. **“Target UNKNOWN nghĩa không còn quyền.”** UNKNOWN phải được theo dõi.
28. **“Chỉ cần xoá log khi hết hạn, không cần policy.”** Retention/hold/privacy cần quản trị.
29. **“Một tài khoản đã disable IdP là không còn access API.”** PEP có thể còn nhận JWT hoặc local session.
30. **“Đếm số event là KPI chất lượng IAM.”** Phải đo độ tin cậy và hiệu lực thay đổi.

## 45. Câu hỏi tự đánh giá

1. Identity event là gì? Khác current identity state, command và log như thế nào?
2. Vì sao `AccountDisableRequested` không đồng nghĩa `EffectiveAccessDenied`?
3. Một event IAM cần phân biệt những vai trò actor, subject, source và target nào?
4. Kể năm loại sự kiện liên quan Joiner–Mover–Leaver.
5. Vì sao `effectiveAt` khác `occurredAt` và `ingestedAt`?
6. Nếu HRIS Leaver event đến muộn 15 phút, cần kiểm những gì?
7. Tại sao email không đủ để liên kết HRIS với IdP và SaaS?
8. Một person có hai relationships: làm sao tránh revoke sai tenant?
9. EventId, correlationId, causationId và aggregateVersion khác nhau thế nào?
10. Vì sao cần idempotency khi broker có at-least-once delivery?
11. Khi Leaver v11 đến trước Mover v10, consumer nên xử lý thế nào?
12. Transactional outbox giải quyết rủi ro nào? Nó có làm SaaS transaction atomic không?
13. Vì sao replay event để phân tích có thể gây lỗi nếu cùng consumer được phép provision?
14. CloudEvents chuẩn hóa điều gì và không chuẩn hóa điều gì cho Identity event?
15. OIDC authentication succeeded có chứng minh API authorization PERMIT không?
16. Vì sao không log raw JWT, OTP, session cookie và proofing evidence?
17. Phân biệt actor application và human subject trong delegated operation.
18. Policy version trong event giúp điều tra điều gì?
19. Vì sao SoD events cần liên kết cả approval và target entitlement?
20. SCIM API response có thể đảm bảo session SaaS bị chấm dứt không?
21. Những event nào liên quan thu hồi phiên khi người dùng Leaver?
22. Service account owner Leaver khác workload retired ở điểm nào?
23. Một event authorization DENY từ PDP nhưng API vẫn chạy là lỗi ở đâu?
24. Một audit hash chain có bảo đảm mọi privileged action đã được ghi không?
25. Cách phát hiện pipeline logging bị tắt hoặc bỏ sót một khoảng thời gian?
26. Reconciliation phân biệt desired, observed và effective access ra sao?
27. Vì sao permission drift không nên tự sửa bằng cách grant thêm role?
28. Những thuộc tính nào giúp SIEM nối một lần MFA reset với role admin được cấp?
29. Nêu ba negative tests cho forged event, cross-tenant event và out-of-order event.
30. Java event consumer cần kiểm gì ngoài DTO schema validation?
31. Thiết kế một event cho `workload.credential.rotated` mà không lộ secret.
32. Một target SCIM trả UNKNOWN trong lúc offboarding: report thế nào?
33. KPI nào đo **effective revocation** thay vì chỉ số lượng lệnh đã gửi?
34. Vì sao event log cần retention, data minimization và quyền truy cập riêng?
35. Khi nào có thể coi Leaver workflow được xác minh hoàn tất?

## 46. Ghi nhớ

**Identity event** là bản ghi có cấu trúc về **sự việc liên quan đến danh tính, quan hệ làm việc, account, xác thực, session, quyền hoặc kiểm soát truy cập**. Một event đáng tin phải có **ngữ nghĩa rõ, nguồn phát có thẩm quyền, subject/actor được phân biệt, định danh bền vững, scope tenant/relationship, thời gian đúng nghĩa, event/schema/version IDs và bằng chứng kết quả**. **Event được phát không đồng nghĩa command đã thực hiện, command được chấp nhận không đồng nghĩa quyền đã có hoặc đã mất, và target báo thành công không phải lúc nào cũng chứng minh effective access.**

Trong mô hình **Joiner–Mover–Leaver**, các Identity events nối **HRIS/identity proofing, IdP/SSO/OIDC/SAML, IGA/approval, SCIM, RBAC/ABAC/PBAC, PAM/JIT, service/robot accounts và resource PEP** thành một chuỗi có thể kiểm toán. Để tránh **quyền truy cập tồn dư**, hệ thống cần **schema/source validation, identity linking, versioning, idempotency, transactional outbox, chống giả mạo và replay, bảo vệ PII/secrets, audit integrity, SIEM correlation và reconciliation giữa desired–observed–effective state**. Kết quả mong muốn là **đúng chủ thể, đúng quyền, đúng thời điểm, đúng nguồn và có bằng chứng rằng thay đổi đã thực sự được thực thi**, chứ không chỉ có một dòng log “SUCCESS”.
