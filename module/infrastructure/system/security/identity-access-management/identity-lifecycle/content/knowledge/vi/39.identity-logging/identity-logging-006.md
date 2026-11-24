# Access change log: nhật ký thay đổi quyền truy cập trong IAM Identity Lifecycle

> **Chương: Identity logging.** **Access change log** là tập bản ghi có cấu trúc giúp trả lời **ai hoặc thành phần nào đã yêu cầu, phê duyệt, thực hiện, phát hiện và xác minh thay đổi nào đối với quyền truy cập của chủ thể nào, trên tài nguyên nào, tại thời điểm nào, theo chính sách và căn cứ gì**. Trong IAM, nhật ký này đặc biệt quan trọng với vòng đời **Joiner–Mover–Leaver (JML)**: tạo danh tính/cấp quyền đúng thời điểm, thay quyền khi đổi công việc, thu hồi khi nghỉ việc và phát hiện quyền tồn dư. Bài học liên kết HR/IGA, IdP/SSO, SCIM, RBAC/ABAC/PBAC, PAM/PIM, service/workload identities, kiểm toán và tính toàn vẹn của bằng chứng.

**Phạm vi bài:** Tập trung vào **các thay đổi quyền truy cập và bằng chứng hội tụ** của chúng. Không đồng nhất access change log với access/activity log ghi từng lần đọc tài nguyên hoặc authentication log ghi mỗi lần đăng nhập. Những loại log đó có thể được **liên kết** để điều tra nhưng trả lời câu hỏi khác nhau.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **access change log**, phân biệt với **authentication log, authorization decision log, resource activity log và audit event**.
2. Mô hình hóa thay đổi quyền theo các giai đoạn **requested → approved/denied → provisioned/failed → observed → effective-verified**, không coi một approval là quyền đã thực thi.
3. Xác định **actor, beneficiary/subject, approver, resource, entitlement, scope, before/after, reason, authority, source version và correlation ID** để tái dựng một thay đổi.
4. Thiết kế **event taxonomy/schema** cho Joiner, Mover, Leaver, direct grant, Group/role changes, policy changes, service principal, PAM, ngoại lệ SoD và emergency access.
5. Áp dụng **idempotency, ordering, correlation, durable outbox/queue, readback, reconciliation và tamper-evident storage** cho hệ thống nhiều nguồn bất đồng bộ.
6. Bảo vệ quyền riêng tư và an toàn log: **không ghi token/password/private key**, có integrity, access control, retention và khả năng xuất chứng cứ có kiểm soát.
7. Phát hiện các tình huống **stale grant, drift, unauthorized change, privilege escalation, orphan owner, SoD violation, residual access** từ nhật ký và trạng thái thực tế.
8. Xây dựng pseudocode, ma trận kiểm thử, truy vấn điều tra, metric và bài tập áp dụng ở hệ thống thực tế.

## 1. Tình huống mở đầu: phê duyệt thu hồi nhưng quyền vẫn còn

Ngày 01/12, Lan chuyển từ Finance sang Support. Workflow IAM ghi nhận người quản lý đã chấp thuận thu hồi **FinanceExporter**. Tuy nhiên connector bị timeout, ứng dụng Finance vẫn có direct grant **report.export**, trong khi token được phát trước đó vẫn có thể được API chấp nhận.

Nếu báo cáo chỉ hiển thị:

~~~text
2026-12-01 09:00  Manager approved revoke FinanceExporter
Status: COMPLETED
~~~

thì tổ chức **không đủ bằng chứng** để kết luận Lan đã mất quyền. Access change log đáng tin cần phản ánh **chuỗi sự kiện với kết quả từng hệ thống**:

~~~text
09:00  MOVER_RECORDED             HR position Finance -> Support
09:01  ACCESS_REVOKE_REQUESTED    entitlement FinanceExporter
09:02  ACCESS_REVOKE_APPROVED     reviewer identity valid
09:03  PROVISIONING_ATTEMPTED    connector FinanceApp, operation revoke
09:04  PROVISIONING_FAILED       timeout, actual result unknown
09:05  TARGET_READBACK           direct grant report.export still present
09:06  REMEDIATION_PENDING       owner FinanceApp, deadline, incident ref
09:10  PROVISIONING_RETRIED      idempotent request
09:11  TARGET_READBACK           direct grant removed
09:12  EFFECTIVE_ACCESS_CHECK    report.export denied for tested path
09:12  ACCESS_REVOKE_VERIFIED    verified scope, token caveats recorded
~~~

**Không nhất thiết mọi sản phẩm có đúng các tên event này.** Chúng là taxonomy minh họa. Điểm cốt lõi là phân biệt **quyết định**, **thao tác đã gửi**, **trạng thái quan sát được ở đích** và **quyền truy cập thực sự còn dùng được**.

## 2. Phân biệt các loại identity/security log

| Loại log | Câu hỏi chính | Ví dụ | Không tự chứng minh |
| --- | --- | --- | --- |
| **Access change log** | Quyền nào được cấp, sửa, thu hồi; ai quyết định và kết quả thế nào? | Group membership bị xóa; role admin được cấp. | User đã thực hiện hành động nào. |
| **Authentication log** | Ai đã xác thực/đăng nhập, khi nào, bằng phương thức nào? | OIDC login success, MFA challenge denied. | Quyền nghiệp vụ nào đã được cấp hoặc gỡ. |
| **Authorization decision log** | Một request/action được Permit hay Deny theo policy nào? | API từ chối report.export sau Mover. | Cấu hình grant đã thay đổi theo workflow nào. |
| **Access/activity log** | Có hành động thực tế nào trên tài nguyên? | Tải báo cáo, thay cấu hình, gọi API. | Việc cấp quyền trước đó có được phê duyệt hợp lệ. |
| **Provisioning/connector log** | Lệnh cập nhật account/Group/role tới target thực hiện ra sao? | SCIM PATCH trả 204, GET readback sau đó. | Tất cả session/token đã bị ngắt. |
| **Configuration/policy change log** | Ai sửa RBAC/ABAC/PBAC, trust hoặc role definition? | Admin đổi policy cho phép export. | Mọi beneficiary trực tiếp đã được liệt kê. |
| **Access review log** | Reviewer giữ/giảm/thu hồi quyền theo phạm vi nào? | Resource owner chọn Revoke. | Đích đã thu hồi thành công. |

### Một hành động có thể cần nhiều log cùng lúc

Khi một admin cấp **PaymentReleaser** cho Minh, ta có thể cần:

- **Access change event:** grant mới, actor admin, Minh là beneficiary, scope là tenant B.
- **Approval event:** request nào và ai có authority duyệt.
- **PAM event:** admin có JIT role đang active từ khi nào, theo incident nào.
- **Authentication event:** admin dùng MFA/step-up nào để đăng nhập.
- **Authorization event:** API cấp role đã Permit theo policy nào.
- **Target readback:** role hoặc Group thực tế được thêm ở ứng dụng nào.

**Đừng trộn tất cả vào một dòng “user accessed system”.** Khi điều tra, các loại event cần có correlation ID, actor/subject reference và thời gian rõ ràng để tái dựng.

## 3. Đối tượng của access change: quyền, principal và phạm vi

Một access change cần mô tả **entitlement** cụ thể:

| Thành phần | Ví dụ | Vì sao quan trọng |
| --- | --- | --- |
| **Subject/beneficiary** | IAM:ID-MINH-88 | Ai sẽ có hoặc mất quyền; khác actor. |
| **Principal/account** | FinanceApp:tenant-b:user-901 | Target local ID; không đồng nhất email với personId. |
| **Entitlement** | role:ReportExporter, permission:report.export | Biết quyền thực tế cần thay. |
| **Resource** | FinanceReports-Prod | Cần resource ID, không chỉ tên hiển thị. |
| **Tenant/scope** | tenant-b, legalEntity LE-B, project P-17 | Một role tên giống nhau có thể có ý nghĩa khác nhau theo scope. |
| **Access path** | Direct ACL, nested Group, inherited role, policy grant | Xác định đường nào đang thay đổi. |
| **Effective window** | startAt/endAt, activationAt | Quyền chỉ hợp lệ trong khoảng được duyệt. |
| **Grant owner** | FinanceDataOwner | Truy trách nhiệm và quyền thay đổi. |
| **Policy version** | finance-access-v12 | Giải thích kết quả theo rule thời điểm đó. |
| **Environment** | production/staging | Tránh đánh đồng môi trường. |

### Một principal có thể có nhiều access path

~~~mermaid
flowchart LR
    H["IAM human identity"] --> U["Finance application User"]
    H --> G["IdP FinanceReaders Group"]
    G --> A["Inherited report.read"]
    U --> D["Direct report.export"]
    A --> R["FinanceReports-Prod"]
    D --> R
    C["Access change log"] -.-> G
    C -.-> D
    C -.-> R
~~~

Khi quyết định **thu hồi export nhưng giữ read**, access change log phải ghi **đường direct report.export bị gỡ**. Nó không được tuyên bố “xóa toàn bộ quyền của User” nếu Group FinanceReaders vẫn cấp read hợp lệ.

### Group membership không đồng nghĩa effective permission

Một SCIM Group có thể là nhóm danh bạ hoặc được mapping sang role ứng dụng. Chỉ khi **Group-to-permission mapping** được xác minh mới có thể kết luận thành viên Group nhận quyền gì. Ngược lại, một tài nguyên có thể được truy cập bằng **direct ACL, sharing link, ABAC policy hoặc service principal** không hiện trong Group.

## 4. Ai là actor, ai hưởng quyền và ai phê duyệt?

Một lỗi audit phổ biến là dùng duy nhất trường “user” để biểu diễn mọi vai trò. Với access change, cần tách:

| Vai trò | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Actor / initiator** | Chủ thể kích hoạt yêu cầu hoặc thao tác. | HR event producer, admin Lan. |
| **Requester** | Người yêu cầu quyền vì nghiệp vụ. | Minh xin ReportExporter. |
| **Beneficiary / subject** | Người/workload sẽ nhận hoặc mất quyền. | IAM:ID-MINH-88. |
| **Approver / reviewer** | Người có authority xét yêu cầu. | FinanceDataOwner. |
| **Executor** | Connector, service hoặc admin thực thi tại target. | provisioning-worker-3. |
| **Delegator / on-behalf-of** | Người đã ủy quyền cho actor. | Security Lead ủy quyền có thời hạn. |
| **Resource owner** | Người chịu trách nhiệm tài nguyên. | DataOwner tenant B. |
| **System of record / source authority** | Nguồn dữ liệu có thẩm quyền cho thay đổi. | HR cho Leaver; app target cho observed ACL. |

### Ví dụ tự động hóa

~~~text
HR system emits MOVER for Minh.
IGA evaluates and creates revoke task.
Provisioning bot calls SCIM to remove Group.

Initiating authority: HR MOVER event
Business beneficiary: Minh
Execution actor: provisioning bot
Resource owner: Finance Platform
Approval policy: policy-based automatic offboarding
Actual target: Finance SaaS Group membership
~~~

Ghi log “provisioning bot revoked role” là đúng ở góc kỹ thuật nhưng **chưa đủ** để giải thích **vì sao và theo thẩm quyền nào**. Không gắn bot thành người chịu trách nhiệm cho quyết định nghiệp vụ mà bot chỉ thực thi.

### Self-approval và SoD

Trong quy trình yêu cầu/cấp đặc quyền, actor và approver có thể là **hai account thuộc cùng một người**. Để kiểm tra separation of duties (SoD), log phải giữ **IAM identity ổn định và authority context**; không chỉ đếm hai email khác nhau là hai approvers độc lập.

## 5. Vòng đời của một access change

### Các trạng thái cần phân biệt

~~~mermaid
flowchart TD
    Q["REQUESTED"] --> V["VALIDATED"]
    V --> A{"Approval / policy?"}
    A -->|Deny| D["DENIED"]
    A -->|Approve| P["APPROVED"]
    P --> X["PROVISIONING_PENDING"]
    X --> T["TARGET_UPDATE_ATTEMPTED"]
    T -->|Timeout/error| F["RETRY / INVESTIGATE"]
    F --> T
    T -->|Ack| O["TARGET_OBSERVED"]
    O --> E{"Effective access verified?"}
    E -->|Yes| C["VERIFIED"]
    E -->|No/unknown| U["PARTIAL_FAILURE / UNKNOWN"]
    U --> F
    C --> Z["AUDIT + RECONCILIATION"]
~~~

Một số bước có thể được kết hợp hoặc thực hiện tự động. **Approval denied** không có nghĩa target chắc chắn không có grant (nó có thể đã tồn tại ngoài luồng). **Target ack** không đồng nghĩa effective access verified.

### Phân biệt năm tầng dữ liệu

1. **Requested:** một người hoặc policy muốn thêm/gỡ quyền.
2. **Approved/authorized:** yêu cầu đạt thẩm quyền và chính sách tại thời điểm đánh giá.
3. **Desired:** IAM/IGA mong muốn target có quyền gì sau thay đổi.
4. **Observed:** connector/API đã nhìn thấy trạng thái thực tế tại target.
5. **Effective:** Resource Server/PEP có thực sự Permit/Deny hành động trong context liên quan hay không.

Ví dụ một lệnh **Revoke** đã được approve và API trả 204, nhưng app session vẫn chấp nhận access token mang quyền cũ. **Desired = revoked**, **observed ACL = removed**, **effective access = còn**. Log phải cho thấy khác biệt này, không ép các trạng thái thành một nhãn “SUCCESS”.

### Tên event ví dụ

| Event | Ý nghĩa |
| --- | --- |
| ACCESS_CHANGE_REQUESTED | Bắt đầu một yêu cầu thay đổi quyền. |
| ACCESS_CHANGE_APPROVED / DENIED | Quyết định cấp quyền theo authority. |
| ACCESS_GRANT_APPLY_REQUESTED | Connector được yêu cầu cấp. |
| ACCESS_REVOKE_APPLY_REQUESTED | Connector được yêu cầu gỡ. |
| TARGET_CHANGE_ACKNOWLEDGED | Target phản hồi thao tác được nhận/xử lý theo contract. |
| TARGET_CHANGE_FAILED | Thao tác thất bại hoặc chưa rõ kết quả. |
| TARGET_STATE_OBSERVED | Trạng thái thực tế đã đọc lại. |
| EFFECTIVE_ACCESS_VERIFIED | Kiểm tra quyền đạt kết quả mong muốn trong scope thử. |
| ACCESS_CHANGE_SUPERSEDED | Task cũ không còn hợp lệ bởi lifecycle/policy/version mới. |
| ACCESS_DRIFT_DETECTED | Desired khác observed/effective trong phạm vi quan sát. |
| ACCESS_EXCEPTION_CREATED/EXPIRED | Ngoại lệ policy được tạo/hết hạn. |

Các nhãn trên là **event catalog minh họa của bài học**, không phải tên event bắt buộc trong SCIM, OIDC, SAML, cloud IAM hoặc hệ thống SIEM.

## 6. Before–after: thay đổi quyền thực sự là gì?

Một bản ghi kiểu “updated User” quá mơ hồ. Để điều tra, cần ghi được **giá trị hoặc trạng thái trước và sau của những thuộc tính liên quan đến quyền**.

### Ví dụ có kiểm soát phạm vi

~~~json
{
  "eventType": "IAM_ACCESS_CHANGE",
  "operation": "REMOVE_GRANT",
  "subjectRef": "IAM:ID-MINH-88",
  "resourceRef": "FinancePlatform:tenant-b:reports-prod",
  "accessPath": "app-direct-role",
  "entitlementRef": "ReportExporter",
  "before": {
    "grantPresent": true,
    "actions": ["report.read", "report.export"]
  },
  "after": {
    "grantPresent": false,
    "actions": []
  },
  "sourceVersion": 72
}
~~~

**Before–after phải được hiểu theo nguồn và thời điểm.** Giá trị **before** có thể là snapshot observed tại thời điểm thu thập, còn **after** là desired state. Không được trình bày hai thứ như hai trạng thái target đã kiểm chứng nếu chưa readback.

### Khi thay đổi role gián tiếp

Nếu Minh bị gỡ khỏi Group FinanceExporters nhưng còn được cấp **report.export** qua direct ACL, log Group membership sẽ đúng nhưng chưa chứng minh effective permission mất. Nên lưu **grant/path changed** và kết quả đánh giá **all relevant access paths**, hoặc liên kết tới một **effective access evaluation**.

### Khi thay đổi policy thay vì grant

Nếu admin sửa ABAC rule để tất cả người thuộc phòng Finance được quyền export, có thể **không có thay đổi Group/User riêng lẻ**. Vẫn là **access-impacting policy change** và cần log:

- Policy ID, version, actor/approval, resource/tenant scope.
- Điều kiện Permit/Deny trước và sau (hoặc diff/hashes có thể giải thích).
- Blast radius dự kiến: tập chủ thể/tài nguyên có thể bị ảnh hưởng, với giới hạn tính toán.
- Thời điểm activate/rollout, PEP nào đã nhận policy.
- Kiểm thử positive/negative và owner xác minh.

### Thuộc tính nhạy cảm không nên log nguyên văn

Nếu access được xác định bởi classification, contract status, health/clearance hoặc metadata nhạy cảm, chỉ ghi **những trường tối thiểu cần thiết** dưới dạng reference, masked value hoặc mã thay đổi theo policy. Không biến access change log thành kho trích xuất đầy đủ HR profile hay dữ liệu khách hàng.

## 7. Phạm vi, định danh ổn định và mapping xuyên hệ thống

Một User có thể xuất hiện dưới nhiều ID:

~~~text
HR employee:       HRIS:EMP-2041
IAM identity:      IAM:ID-LAN-2041
IdP account:       issuer-a/sub-88
Finance SaaS:      tenant-b/scim-user-901
Cloud admin alias: cloud-b/admin-lan
Workload bot:      workload:tenant-b:pay-runner
~~~

Trong log cần lưu **ID theo namespace, tenant, source system và bằng chứng correlation**, không chỉ email/displayName. Một email có thể được đổi hoặc tái sử dụng; một device có thể được bàn giao; một bot có service owner là người nhưng không trở thành **human identity** của người đó.

### Các quy tắc định danh

- **subjectRef** là beneficiary của thay đổi, không nhất thiết là User đang đăng nhập.
- **targetPrincipalRef** là account/service principal local tại nơi thay đổi.
- **resourceRef** cần phân biệt tenant, environment và type, tránh tên “prod” bị trùng.
- **entitlementRef** phải có namespace/role mapping version khi role tên giống nhau giữa ứng dụng.
- **actorRef** phải giữ principal thực thi và on-behalf-of/authority chain nếu có.
- **deviceRef/sessionRef** chỉ thêm khi thực sự liên quan và có nguồn tin cậy.
- Nếu mapping chưa giải quyết được, dùng trạng thái **IDENTITY_UNRESOLVED**, không tùy tiện chọn một User theo email trùng.

### Vì sao log cần access-path reference?

Một tài nguyên có thể có direct grant, inherited role và ABAC Permit. Nếu chỉ log “User X được thêm quyền đọc”, không thể biết cần gỡ **đường nào** khi Mover. Với access review/reconciliation, **grant ID/path** là khóa để truy nguyên source và xử lý phạm vi nhỏ mà không ảnh hưởng người khác.

## 8. Causality: liên kết request, approval, execution và target evidence

Thay đổi quyền thường đi qua nhiều services, queues và con người. Để tái dựng một thay đổi, cần theo dõi **căn nguyên và chuỗi hệ quả**, không chỉ sắp xếp log theo timestamp.

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IGA as IAM/IGA
    participant AP as Approver/Policy
    participant W as Provisioning Worker
    participant SP as Target SaaS
    participant AU as Audit Store
    HR->>IGA: Mover event + sourceVersion
    IGA->>AU: ACCESS_CHANGE_REQUESTED
    IGA->>AP: Evaluate SoD and approval
    AP-->>IGA: Decision + authority
    IGA->>AU: ACCESS_CHANGE_APPROVED
    IGA->>W: Command + idempotencyKey
    W->>SP: SCIM PATCH / Group change
    SP-->>W: Ack or error
    W->>AU: TARGET_CHANGE_ACKNOWLEDGED
    W->>SP: Readback current state
    SP-->>W: Actual membership / role
    W->>AU: TARGET_STATE_OBSERVED
    W->>AU: EFFECTIVE_ACCESS_VERIFIED or UNKNOWN
~~~

### Cần tối thiểu những ID nào?

| ID | Ví dụ | Vai trò |
| --- | --- | --- |
| **correlationId** | jml-mover-2041-v72 | Ghép các event cùng nghiệp vụ, không nhất thiết cùng transaction. |
| **eventId** | evt-001238 | Phân biệt từng event, hỗ trợ idempotent ingestion. |
| **requestId** | req-771 | Yêu cầu thay đổi quyền. |
| **approvalId** | approval-501 | Quyết định có căn cứ. |
| **commandId / idempotencyKey** | revoke-group-771-v2 | Nhận diện thao tác provisioning khi retry. |
| **sourceEventId/sourceVersion** | hris-event-72 | Phân biệt event hiện hành với retry cũ. |
| **targetOperationId** | scim-request-81 | Theo dõi phản hồi target/API. |
| **grantRef** | finance:direct:report-export | Định danh đường quyền cần thay. |
| **snapshotId** | snap-finance-20261201 | Bằng chứng trạng thái observed trước/sau. |
| **policyVersion** | sod-policy-v4 | Giải thích quyết định Permit/Deny. |

**Không phải mọi hệ thống có sẵn toàn bộ ID.** Khi thiếu, có thể gán ID nội bộ bền vững tại cổng tích hợp và lưu mapping. Nhưng không tạo correlation “chắc chắn” bằng cách gộp các event chỉ vì xảy ra gần nhau hoặc cùng email.

### Request và event có quan hệ một-nhiều

Một yêu cầu “thu hồi mọi quyền của Lan” có thể dẫn tới **nhiều operations** tại IdP, Finance SaaS, CRM, VPN, PAM và kho key; mỗi operation có trạng thái khác nhau. Một access change log tốt giữ **quan hệ cha–con**:

~~~text
JML Leaver request req-100
  -> revoke IdP Group 1: VERIFIED
  -> disable Finance app User: VERIFIED
  -> remove direct Finance ACL: PENDING
  -> revoke CRM PAT: FAILED
  -> terminate PAM session: VERIFIED
  -> verify old access token: UNKNOWN

Overall request: PARTIAL_FAILURE
~~~

Không dùng **một success boolean** làm mất thông tin về từng đường truy cập.

## 9. Sự kiện Joiner: đăng ký danh tính và cấp quyền ban đầu

Với **Joiner**, thay đổi quyền có thể được chuẩn bị trước ngày làm việc. Log cần phân biệt **account creation, entitlement assignment, activation và effective access**.

### Luồng điển hình

1. HR tạo nhân sự với stable ID, startAt, department, manager và sourceVersion đáng tin.
2. IAM tạo identity theo quy trình xác minh và account correlation.
3. IGA tính birthright roles/RBAC theo vị trí, hoặc ABAC dựa trên thuộc tính được xác minh.
4. Policy/SoD check từ chối những tổ hợp quyền xung đột.
5. Provisioning tạo account/Group/role, có thể **trước startAt**.
6. Hệ thống thực thi **activation boundary** để không mở quyền nghiệp vụ sớm.
7. Readback và kiểm tra resource permission theo scope.

### Ví dụ access change log

~~~text
Nov 28  USER_PROVISIONED         IdP account for Lan
Nov 28  GROUP_ASSIGNMENT_STAGED  FinanceReaders, not usable until startAt
Dec 01  IDENTITY_ACTIVATED       startAt=09:00+07, sourceVersion=18
Dec 01  ACCESS_GRANT_VERIFIED    report.read tenant-b allowed
~~~

**Không coi account tồn tại = quyền đã hợp lệ trước startAt.** Nếu Joiner bị hủy, log phải ghi chính sách đã supersede những grant/activation pending và hậu kiểm quyền còn tồn.

### Một lỗi thực tế

Worker A tạo Group assignment theo HR event v18. HR sau đó hủy onboarding ở v19, nhưng job v18 retry và vẫn cấp role. Log cần chỉ rõ:

~~~text
sourceVersion v18: JOINER
sourceVersion v19: ONBOARDING_CANCELLED
command v18 retry: BLOCKED_SUPERSEDED
reason: current HR state no longer eligible
~~~

Nếu log chỉ ghi **“SCIM POST 201”**, không có lifecycle check, tổ chức khó phát hiện quyền được cấp sai thời điểm.

## 10. Sự kiện Mover: thay quyền theo vai trò và ngăn privilege accumulation

Trong **Mover**, điều cần theo dõi không chỉ role mới được thêm mà còn **quyền cũ phải thu hồi**, approval cũ có còn hợp lệ và có toxic combination hay không.

### Ví dụ Finance → Support

| Thành phần | Trước Mover | Sau Mover mong muốn | Access change log phải thấy |
| --- | --- | --- | --- |
| HR department | FINANCE | SUPPORT | Mover effectiveAt/sourceVersion. |
| Group | FinanceExporters | Removed | Remove membership requested/applied/readback. |
| App direct ACL | report.export | Removed | Direct grant revoke và target evidence. |
| New Group | SupportReaders | Added | Approval, scope, target readback. |
| App session | Token có role cũ | Không dùng quyền Finance | Logout/authorization policy evidence nếu thuộc scope. |
| PAM activation | Có thể đang active | Kết thúc nếu không còn role | Privileged session revoke/verified. |

### Vì sao cần before/after effective date?

Một Mover có thể hiệu lực **09:00 ngày 01/12**, nhưng event tới queue **10:00** và connector xử lý **10:05**. Ghi riêng:

~~~text
businessEffectiveAt = 09:00
sourceEventAt        = 08:50
receivedAt           = 10:00
provisionedAt        = 10:05
targetVerifiedAt     = 10:06
~~~

Nhờ đó có thể phân tích **thời gian quyền cũ tồn dư sau mốc nghiệp vụ**. Không lấy receivedAt làm thời điểm HR đã ra quyết định.

### SoD và toxic combinations

Khi Mover được cấp PaymentReleaser mà còn VendorEditor qua direct role, log cần có **SoD conflict evaluation** theo capability, legal entity, tenant và quyền hiệu lực; không chỉ ghi “role added”. Nếu grant mới bị chặn do SoD, log nên giữ **ruleId/version, scope, reason code và quyết định**, tránh lộ dữ liệu không cần thiết.

## 11. Sự kiện Leaver: thu hồi và chứng minh quyền không còn dùng được

**Leaver** là trường hợp cần **evidence chi tiết nhất** cho những đường truy cập có mức rủi ro cao. Từ khi sự kiện có hiệu lực đến khi từng target hội tụ có thể xuất hiện **residual access window**.

### Những event nên liên kết

1. HR Leaver event được xác minh, mang identityId/effectiveAt/sourceVersion.
2. IAM status/eligibility thay đổi, block new grants và account activation.
3. IdP disable new sign-in hoặc xử lý session theo policy.
4. SCIM/connector cập nhật User active, Group, role membership và entitlement.
5. Các app gỡ direct ACL, PAT/API keys hoặc local roles.
6. PAM/PIM thu hồi eligibility/activation, broker sessions và credential checkout.
7. Machine/workload credential mà người rời đi biết được đánh giá rotate/revoke hoặc chuyển ownership.
8. Target readback và resource authorization verification hoàn tất trong scope.
9. Những đường UNKNOWN/PARTIAL_FAILURE được ghi owner, deadline, containment và retry.

### Ví dụ timeline

~~~text
17:00:00  HR_LEAVER_EFFECTIVE       identity=IAM:ID-MINH-88
17:00:04  SESSION_REVOCATION_REQ    IdP
17:00:06  IDP_SIGNIN_BLOCKED       new sign-ins
17:00:09  SCIM_USER_UPDATE_ACK     target app active=false
17:00:13  TARGET_GROUP_READBACK    group removed
17:00:17  APP_LOCAL_ACL_READBACK   old report.export still present
17:00:18  RESIDUAL_ACCESS_ALERT    owner assigned
17:01:25  ACL_REVOKE_VERIFIED      direct grant removed
17:01:30  API_DENY_VERIFIED        report.export denied on tested path
~~~

Không thể tuyên bố “Leaver hoàn tất lúc 17:00:09” chỉ vì SCIM trả thành công. Audit có thể báo **IdP disable nhanh**, nhưng **access closure** phải theo phạm vi bằng chứng.

### Token/session không luôn mất ngay

- Một **JWT tự chứa** có thể còn được Resource Server chấp nhận đến expiry nếu API chỉ kiểm chữ ký/exp và không có revocation lookup.
- **Refresh token** bị revoke có thể ngăn cấp token mới, nhưng không mặc nhiên hủy mọi access token đang có.
- **App cookie/local session** có thể tồn tại nếu RP không nhận logout hoặc không revalidate quyền.
- **SSH key, PAT và service secret** có thể nằm ngoài IdP.

Access change log phải ghi **điểm thu hồi và giới hạn của việc kiểm chứng**, không tự suy “IdP disabled ⇒ toàn bộ token đã vô hiệu”.

## 12. SCIM provisioning: ghi thay đổi User và Group có căn cứ

SCIM có thể được dùng để đồng bộ **User và Group** vào ứng dụng. Access change log nên nối **ý định nghiệp vụ** với **HTTP request/response** và **trạng thái target đọc lại**.

### Ví dụ remove Group member

~~~json
{
  "eventType": "PROVISIONING_COMMAND",
  "protocol": "SCIM_2_0",
  "operation": "PATCH_GROUP_REMOVE_MEMBER",
  "target": "FinanceSaaS:tenant-b",
  "groupRef": "scim:tenant-b:group-77",
  "memberRef": "scim:tenant-b:user-901",
  "reason": "MOVER_OLD_ROLE_REMOVAL",
  "requestId": "req-771",
  "commandId": "cmd-771-02",
  "correlationId": "jml-mover-2041-v72"
}
~~~

Đây là event nội bộ, **không phải một SCIM request body**. Nếu phải ghi payload, dùng **allowlist trường cần thiết** và che/thay thế dữ liệu nhạy cảm.

### Những điểm cần lưu ý

| Tình huống | Cách hiểu đúng |
| --- | --- |
| SCIM PATCH trả 204 | Thao tác có phản hồi theo hợp đồng HTTP; chưa chắc session/token mất quyền. |
| SCIM PATCH timeout | Kết quả tại target có thể **không xác định**, không nên retry mù hoặc gắn failure chắc chắn. |
| SCIM Group lồng nhau | Không phải mọi target có semantics nested Group giống nhau. |
| SCIM User ID | Là local target resource ID, không mặc nhiên bằng HR personId. |
| 404 User khi revoke | Có thể account đã xóa, sai tenant/ID hoặc connector thiếu quyền; cần phân biệt. |
| 429 rate limit | Cần retry/backoff theo chính sách, không ghi kết quả rỗng là thành công. |
| ETag/If-Match nếu hỗ trợ | Giúp tránh ghi đè dữ liệu mới khi cập nhật đồng thời. |
| Target sửa ngoài IAM | Cần phát hiện drift bằng audit/reconciliation nguồn target. |

### Tránh lộ dữ liệu qua SCIM payload

SCIM User có thể chứa email, số điện thoại, tên, phòng ban, manager hoặc thuộc tính mở rộng. Một access change log không cần sao chép toàn bộ đối tượng User mỗi lần Group thay đổi. Lưu **target ID, operation, entitlement diff, policy/correlation, kết quả**, và tham chiếu source record được bảo vệ nếu cần.

## 13. IdP, SSO, OAuth/OIDC và SAML: ghi thay đổi đúng lớp

Không phải mọi sự kiện identity đều là thay đổi entitlement. Cần phân loại rõ:

| Sự kiện | Access change log? | Vì sao |
| --- | --- | --- |
| User đăng nhập thành công qua OIDC | Thường là authentication event. | Không có grant/role change chỉ vì login. |
| User được gán app assignment | Có. | Thay phạm vi tài nguyên ứng dụng có thể truy cập. |
| User bị gỡ khỏi IdP Group cấp quyền app | Có. | Có thay đổi entitlement, cần mapping/correlation. |
| Refresh token được rotate | Thường là token/session security log. | Không nhất thiết quyền nghiệp vụ đổi. |
| Refresh token family bị revoke do Leaver | Có thể liên kết access-revocation evidence. | Ảnh hưởng khả năng tiếp tục truy cập. |
| RP local session bị kết thúc do offboarding | Có thể là child event của access revoke. | Chứng minh một đường truy cập bị đóng. |
| OIDC client scope/policy được tăng | Có. | Thay capability mà client có thể xin hoặc sử dụng. |
| SAML app role/attribute mapping đổi | Có. | Ảnh hưởng authorization ở SP. |
| SSO logout thất bại | Không phải grant change; liên kết để chứng minh residual session. | Kết luận quyền bị thu hồi chưa đầy đủ. |

### Một IdP Group change có thể ảnh hưởng nhiều ứng dụng

Gỡ Lan khỏi FinanceAdmins có thể làm mất quyền ở Finance Portal và một hệ thống SaaS khác, **nếu mapping Group→role được cấu hình**. Access change log có thể ghi **logical entitlement change** ở IdP và các **target-specific observations** riêng. Không giả định việc gỡ Group đã tự hội tụ đến mọi ứng dụng nếu connector, token cache hoặc app session còn chưa cập nhật.

### SAML và OIDC claim cũ

Một SAML assertion hoặc JWT đã được phát trước Mover có thể còn được ứng dụng sử dụng trong session cục bộ. **Chữ ký hợp lệ không chứng minh thuộc tính quyền vẫn hiện hành**. Khi yêu cầu revoke quyền ngay, cần runtime authorization policy, session revocation hoặc TTL phù hợp; log cần thể hiện **đường kiểm chứng**.

## 14. RBAC, ABAC, PBAC: không chỉ có thay Group membership

### RBAC: role membership và role definition

RBAC thường liên quan **gán User/service principal vào role** hoặc **thay permission set của role**. Hai loại thay đổi phải được phân biệt:

~~~text
ASSIGN_ROLE:
    subject IAM:ID-LAN-2041
    role ReportReader
    scope tenant-b/reports-prod

UPDATE_ROLE_DEFINITION:
    role ReportReader
    before actions = {report.read}
    after actions  = {report.read, report.export}
    affected population potentially all current role members
~~~

Thay role definition có thể **mở quyền đồng loạt** mà không tạo event cấp role riêng cho từng User. Log cần biết **policy blast radius**, effective time và PEP rollout.

### ABAC: thuộc tính có thể thay quyền mà không có grant trực tiếp

Giả sử rule cho phép export nếu subject.department=FINANCE, resource.classification=INTERNAL và subject.tenantId=resource.tenantId. Khi HR đổi department sang SUPPORT, quyền export có thể thay đổi **ngay tại PDP** dù không có Group removal.

Access change logging nên ghi:

- Thuộc tính **access-affecting** nào thay đổi, source/version/effectiveAt.
- Policy ID/version phụ thuộc thuộc tính đó.
- Phạm vi quyền có thể bị ảnh hưởng, không khẳng định tính đầy đủ khi không mô phỏng được.
- PIP/PDP freshness và verification phù hợp.

Không tự kết luận mỗi thay đổi HR là một grant vật lý bị gỡ; có thể chỉ có **effective permission change**.

### PBAC: policy change và decision provenance

Khi policy engine đổi rule Permit/Deny, cần log **ai publish, ai review, phiên bản nào, source policy nào, rollout đến đâu, test evidence**. Log nên nối quyết định runtime về policy version đã dùng, đặc biệt khi có cache hoặc rollout theo nhiều vùng.

### Deny-overrides và phân quyền theo ngữ cảnh

Sự tồn tại của một role Permit không chứng minh User được truy cập nếu có **tenant isolation, Leaver hard guard, SoD hoặc resource-specific Deny**. Access change log nên phân biệt **grant exists** với **effective Permit**, tránh đánh giá sai khi role vẫn được lưu để phục vụ lịch sử nhưng action bị Deny theo lifecycle.

## 15. PAM/PIM, privileged access và emergency access

Với quyền đặc quyền, nhật ký cần ghi không chỉ “đã cấp Admin” mà còn **eligibility, activation, session, authority, incident và kết quả thu hồi**.

### Những event quan trọng

| Event | Ví dụ | Ý nghĩa kiểm toán |
| --- | --- | --- |
| PRIVILEGED_ELIGIBILITY_GRANTED | Minh được eligible CloudAdmin 30 ngày. | Khả năng kích hoạt trong tương lai, dù chưa active. |
| PRIVILEGED_ACTIVATION_APPROVED | Activation 20 phút được Finance/Security duyệt. | Authority và giới hạn thời gian. |
| PRIVILEGED_SESSION_STARTED | PAM session trên production resource. | Ai thực sự có một đường admin đang mở. |
| PRIVILEGED_ROLE_ACTIVATED | Role/credential đã active ở target. | Phải phân biệt ack với khả năng thực thi thật. |
| PRIVILEGED_ROLE_EXPIRED | Hết activation TTL. | Không mặc nhiên đóng mọi SSH/cloud sessions. |
| PRIVILEGED_SESSION_TERMINATED | PAM đóng broker session. | Còn phải xét direct sessions ngoài PAM. |
| EMERGENCY_ACCESS_USED | Break-glass account được dùng theo incident. | Kiểm điều kiện kích hoạt, custody, scope, hậu kiểm. |
| ADMIN_POLICY_CHANGED | Actor sửa IAM policy/trust. | Có thể tạo đường privilege escalation gián tiếp. |

### SoD và quyền tự phê duyệt

Một người có thể sở hữu **normal account, admin account và một service principal**; log cần liên kết actor, beneficiary và authority để phát hiện **self-approval, tự sửa approver list, tự cấp GlobalAdmin hoặc tắt audit**. Một approval bằng hai account của cùng một người **không tự tạo hai approvers độc lập**.

### Break-glass khi logging chính bị lỗi

Emergency access đôi khi phải hoạt động khi IdP/PAM hoặc log pipeline chính không khả dụng. Cần có **evidence/alternate logging được chuẩn bị trước**, ví dụ local protected audit và cơ chế đồng bộ sau sự cố. Điều này **không phải lý do vô hiệu mọi logging** hoặc cho requester tự xác nhận quyền vô thời hạn.

## 16. Machine identity và tài khoản dịch vụ trong access change log

Một workload không có HR employee record nhưng vẫn có quyền đọc/ghi dữ liệu hoặc deploy production. Access change log cần mô hình hóa **principal type** và **ownership**:

| Principal | Thay đổi cần log | Dữ liệu ownership |
| --- | --- | --- |
| **Service account** | API key/role được cấp, rotate/revoke, scope thay đổi. | Service owner và application/asset record. |
| **Cloud service principal** | Trust, role assignment, permission/condition thay đổi. | Tenant, workload owner, resource scope. |
| **Kubernetes service account** | Namespace/role binding, token audience, trust policy. | Cluster namespace và service owner. |
| **CI/CD runner** | Deploy permission, secret checkout, repository trust. | Pipeline/project owner và environment. |
| **Device certificate identity** | Certificate issuance/revocation, enrollment/trust thay đổi. | DeviceId, CA, asset owner hoặc site owner. |
| **Workload federation** | Issuer/subject/audience/trust conditions thay đổi. | Workload identity, host/runtime source, owner. |

### Một ví dụ quyền gián tiếp

~~~text
CI deployer service principal
    -> has permission iam.role.assign in production
    -> can assign PaymentAdmin to itself
    -> can perform privileged action
~~~

Log chỉ ghi direct role “DeployRunner” có thể bỏ sót **khả năng tự tăng quyền**. Thay đổi trust và IAM policy phải được coi là access-affecting, với risk tier và review thích hợp.

### Owner nghỉ việc không đồng nghĩa xóa service

Khi nhân viên chịu trách nhiệm bot đã Leaver, có thể cần **chuyển service ownership, revoke quyền cá nhân, rotate credential mà người cũ biết, đánh giá trust và tiếp tục service hợp lệ**. Không tự DELETE machine identity production chỉ vì HR identity người chủ đã nghỉ.

### Secret rotation phải tránh ghi secret

Event có thể ghi **secretRef, version/epoch, actor, scope, rotatedAt, previousCredentialRevokedAt và verification**. Không ghi plaintext secret, token, private key hoặc recovery phrase. Nếu phải điều tra sự cố lộ bí mật, log vẫn không được tái phát tán bí mật trong SIEM.

## 17. Thiết kế event schema cho access change log

Schema không cần sao chép toàn bộ bản ghi account hoặc permission. Nó cần **đủ để giải thích, kiểm chứng, truy vết và đối soát**.

### Các nhóm trường thiết yếu

| Nhóm | Trường minh họa | Ý nghĩa |
| --- | --- | --- |
| **Envelope** | schemaVersion, eventId, eventType | Nhận diện event và phiên bản cấu trúc. |
| **Thời gian** | occurredAt, recordedAt, effectiveAt, verifiedAt | Tách thời điểm nghiệp vụ, ghi log và xác minh. |
| **Nguồn** | sourceSystem, sourceEventId, sourceVersion | Chứng minh provenance và ordering theo nguồn. |
| **Chuỗi nhân quả** | correlationId, causationId, requestId, commandId | Nối request/approval/worker/target. |
| **Danh tính** | actorRef, beneficiaryRef, targetPrincipalRef | Phân biệt người quyết định, người hưởng và account đích. |
| **Thẩm quyền** | approverRef, authorityRef, approvalRef | Chứng minh nguồn phép và SoD. |
| **Tài nguyên** | resourceRef, tenant, environment, entitlementRef | Biết quyền nào trên đối tượng nào. |
| **Thao tác** | operation, accessPath, before, after | Diễn giải grant/revoke/modify. |
| **Quy tắc** | policyId/version, riskTier, reasonCode | Giải thích lý do thay quyền. |
| **Kết quả** | stage, result, targetStatus, errorCode | Không gộp approval với execution. |
| **Bằng chứng** | targetSnapshotRef, verificationRef, scopeCoverage | Có thể chứng minh trạng thái thực tế. |
| **Bảo vệ log** | integrityRef, logProducerIdentity, redactionPolicyVersion | Giúp đánh giá tính tin cậy và hạn chế dữ liệu. |

### JSON event đầy đủ minh họa

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "evt-20261201-00077",
  "eventType": "IAM_ACCESS_CHANGE_VERIFICATION",
  "occurredAt": "2026-12-01T09:05:00+07:00",
  "recordedAt": "2026-12-01T09:05:03+07:00",
  "businessEffectiveAt": "2026-12-01T09:00:00+07:00",
  "sourceSystem": "IGA-ACCESS-WORKFLOW",
  "sourceEventId": "mover-event-72",
  "sourceVersion": 72,
  "correlationId": "jml-mover-2041-v72",
  "causationId": "evt-20261201-00074",
  "requestId": "req-771",
  "commandId": "cmd-revoke-export-771",
  "actorRef": "service:iga-provisioner",
  "beneficiaryRef": "IAM:ID-LAN-2041",
  "targetPrincipalRef": "FinanceSaaS:tenant-b:user-901",
  "authorityRef": "HRIS:MOVER:72",
  "resourceRef": "FinancePlatform:tenant-b:reports-prod",
  "entitlementRef": "ReportExporter",
  "accessPath": "application-direct-role",
  "operation": "REVOKE_GRANT",
  "before": {"grantPresent": true},
  "desiredAfter": {"grantPresent": false},
  "observedAfter": {"grantPresent": false},
  "policyVersion": "finance-access-v12",
  "stage": "TARGET_READBACK",
  "result": "OBSERVED_MATCH",
  "verification": {
    "scope": ["direct-role:ReportExporter"],
    "effectiveAction": "report.export",
    "effectiveAccessResult": "NOT_TESTED",
    "reason": "APPLICATION_TEST_NOT_AVAILABLE"
  },
  "targetSnapshotRef": "snapshot-finance-991",
  "redactionPolicyVersion": "audit-redact-v3"
}
~~~

**Chú ý:** kết quả **OBSERVED_MATCH** ở ví dụ chỉ nói role direct đã mất theo API target. Trường **effectiveAccessResult = NOT_TESTED** cố ý ngăn kết luận rằng mọi token/session hoặc path khác đã bị chặn.

### Event immutable và event correction

Một event audit đã ghi thường nên được **giữ nguyên, append correction/superseding event** thay vì sửa nội dung quá khứ để nó “trông đúng”. Nếu ban đầu mapping sai subject, tạo event **CORRECTION/INVALIDATION** có reference đến event cũ, người sửa, lý do và evidence, nhưng không âm thầm xóa lịch sử quyết định.

### Schema evolution

Khi bổ sung trường mới:

- Tăng schemaVersion theo chính sách.
- Giữ tương thích với consumers hoặc có migration được quản lý.
- Đánh dấu field bắt buộc và field tùy chọn rõ ràng.
- Định nghĩa giá trị **UNKNOWN/NOT_APPLICABLE** thay vì dùng null một cách mơ hồ.
- Bảo toàn semantics thời gian, status và principal references.
- Test replay events cũ; không tự hiểu field thiếu là giá trị an toàn.

## 18. Kiến trúc thu thập, xử lý và lưu access change logs

Một ứng dụng nhỏ có thể ghi audit vào database có transaction; hệ thống IAM lớn thường phải tổng hợp event từ **HR, IGA, IdP, PAM, SCIM connectors, cloud IAM, application logs và policy engine**.

~~~mermaid
flowchart LR
    HR["HR / Identity source"] --> C["Validated collectors"]
    IAM["IAM / IGA / SCIM"] --> C
    IDP["IdP / SSO / PAM"] --> C
    T["Applications / Cloud IAM"] --> C
    C --> N["Normalize + verify provenance<br/>schema + redaction"]
    N --> Q["Durable audit stream / queue"]
    Q --> D["Immutable or protected audit store"]
    Q --> S["SIEM / Detection and correlation"]
    Q --> R["Reconciliation / JML verification"]
    D --> E["Evidence export with access controls"]
    S --> A["Alert / Incident workflow"]
    R --> A
~~~

### Các thành phần và trách nhiệm

| Thành phần | Trách nhiệm | Rủi ro |
| --- | --- | --- |
| **Event producers** | Phát event có source ID/version và actor context. | App logging khác nhau, thiếu event quan trọng. |
| **Collectors** | Nhận dữ liệu từ API/stream/log, xác minh nguồn, retry. | Bỏ mất event khi rate limit/network failure. |
| **Normalizer** | Quy đổi schema, field meanings, tenant, identity mapping. | Gộp nhầm actor/beneficiary hoặc before/desiredAfter. |
| **Durable stream/queue** | Đệm dữ liệu, xử lý bất đồng bộ, phân luồng. | Duplicate/out-of-order events, retention giới hạn. |
| **Audit store** | Lưu bằng chứng chống sửa, hỗ trợ truy vấn/retention. | Privileged admin có thể sửa/xóa log nếu thiếu bảo vệ. |
| **SIEM/detection** | Correlate và phát hiện cấp quyền bất thường. | False positives, thiếu context và alert fatigue. |
| **Reconciliation engine** | So desired với observed/effective theo scope. | Connector coverage yếu tạo cảm giác sạch giả. |
| **Reporting/export** | Cung cấp bằng chứng cho owner/auditor. | Rò rỉ PII, log secrets hoặc sai phạm vi xuất. |

### Không chỉ có “logging enabled”

Một hệ thống báo “audit enabled” nhưng log chỉ nằm trên cùng máy chủ mà admin đang có quyền xóa file có thể **không đáp ứng yêu cầu điều tra đặc quyền**. Cần xem **đường vận chuyển, tính toàn vẹn, quyền admin, chính sách retention và khả năng phát hiện mất sự kiện**.

### Sự kiện target có thể độc lập với IAM

Một admin có thể cấp direct grant trong SaaS console, **không đi qua IGA**. Nếu chỉ thu log từ IGA, thay đổi này biến mất khỏi audit IAM. Cần **target-native audit events, connector readback, cloud policy history hoặc reconciliation** theo khả năng từng hệ thống.

## 19. Bảo đảm không mất log: transaction, outbox và durability

Một câu hỏi khó: sau khi cập nhật quyền thành công, hệ thống **crash trước khi gửi log** thì sao?

### Lỗi dual-write

~~~text
1) Database UPDATE grant -> COMMIT SUCCESS
2) Application sends audit event -> NETWORK FAILURE

Result:
    Access changed, audit event missing.
~~~

Nếu làm ngược lại, hệ thống có thể ghi event “GRANTED” nhưng giao dịch cập nhật quyền rollback. Khi đó audit **khẳng định sai trạng thái thực**.

### Transactional outbox (khi cùng transactional datastore)

Một mô hình hữu ích là ghi **business change + outbox event** trong cùng transaction cục bộ:

~~~text
BEGIN TRANSACTION
    UPDATE grants SET ... WHERE version = expectedVersion;
    INSERT INTO audit_outbox(
        eventId,
        eventType,
        subjectRef,
        entitlementRef,
        sourceVersion,
        payloadReference
    );
COMMIT

OUTBOX RELAY:
    read committed outbox entries
    publish to durable audit stream
    mark publication status
    retry with same eventId when delivery uncertain
~~~

**Outbox không tự tạo giao dịch phân tán với target SaaS.** Nếu command được gửi tới SCIM API, phải log command attempt, target response/readback và reconciliation riêng. Outbox cũng không tự bảo đảm **exactly-once delivery** tới mọi consumer; nên thiết kế **at-least-once + idempotent processing** khi phù hợp.

### Nếu source không hỗ trợ outbox

- Thu **native audit log** qua API/stream, theo checkpoint/sequence/cursor có kiểm chứng.
- Nếu ứng dụng không có event, dùng **periodic snapshot/diff** để phát hiện thay đổi; ghi rõ **observedAt** và không đoán actor nếu không có dữ liệu.
- Với cloud control plane, lấy change events và policy/state readback theo tính năng có sẵn.
- Giám sát collector freshness, dead-letter queue, skipped pages, API permissions.
- Có alert nếu một nguồn bắt buộc không phát event trong khoảng được mong đợi, nhưng phân biệt **không có event** với **đường thu thập đã hỏng**.

### Thay đổi quyền và log có thể thất bại khác nhau

| Thay quyền | Ghi log | Phản ứng hợp lý |
| --- | --- | --- |
| Thành công | Thành công | Tiếp tục readback/verification. |
| Thất bại | Thành công | Giữ event FAILED/PENDING; không báo grant đã tồn tại. |
| Thành công | Ghi log thất bại | Cần durable local record/compensating reconciliation, alert nghiêm trọng. |
| Không rõ | Có event attempt | Readback và đối soát; không retry mù tác vụ không idempotent. |
| Không rõ | Không có evidence đáng tin | Điều tra nguồn và target state; không kết luận sạch quyền. |

## 20. Idempotency, out-of-order và duplicate access events

Trong kiến trúc event-driven, **duplicate messages** là tình huống bình thường có thể xảy ra. Log phải tránh biến một command retry thành **nhiều thay đổi quyền giả**.

### Ba cấp cần phân biệt

1. **Event delivery:** cùng eventId đến hai lần, consumer có thể deduplicate.
2. **Command execution:** cùng commandId retry, target có thể đã thực hiện; cần readback/idempotency.
3. **Business intent:** cùng requestId có thể hợp lệ phát nhiều command khác nhau nếu thay nhiều target.

Không dùng eventId giống commandId nếu chúng có semantics khác nhau; việc một yêu cầu sinh nhiều events không phải duplicate.

### Tình huống nhận sai thứ tự

~~~text
HR sourceVersion 101: JOINER -> grant FinanceReader
HR sourceVersion 102: MOVER  -> revoke FinanceReader
HR sourceVersion 103: LEAVER -> revoke employee access

Actual arrival:
    103, 101 retry, 102 delayed

Required:
    log all arrivals with sourceVersion and receivedAt;
    do not let v101 or v102 re-grant after v103;
    record superseded commands and actual target state.
~~~

### Quy tắc xử lý

- Giữ **sourceVersion, effectiveAt, receivedAt** theo nguồn có thẩm quyền.
- Khi có state machine, những event trạng thái cuối như revoked/terminated **không bị hồi sinh bởi retry cũ**.
- Dùng **optimistic concurrency/version guard** tại target nếu hỗ trợ.
- Không giả định tất cả nguồn dùng một global counter: HR v103 không thể đem so trực tiếp với SCIM ETag v8 như cùng loại.
- Có khả năng **replay event để tái dựng**, nhưng replay không được thực hiện lại quyền ngoài ý muốn khi job chỉ dành cho audit.
- Một event correction/retraction phải ghi liên kết với original event thay vì tự xóa.

### Event dedupe cần giữ bằng chứng

Deduplicate ở consumer để **tránh đếm hai lần cùng event**; vẫn có thể lưu số lần retry/delivery attempt trong operational metrics riêng. Nếu thật sự có hai hành động cấp quyền độc lập, chúng phải là **hai event nghiệp vụ** dù cùng beneficiary và role.

## 21. Thời gian và độ trễ trong access change log

Trong JML, **thời điểm có hiệu lực** cực kỳ quan trọng. Cần phân biệt:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **businessEffectiveAt** | Quyền đáng lẽ thay đổi theo nghiệp vụ lúc nào. | Leaver 17:00. |
| **sourceOccurredAt** | HR/IGA/target ghi sự kiện gốc lúc nào. | HR gửi 16:55. |
| **producedAt** | Producer tạo log lúc nào. | IGA phát event 16:56. |
| **ingestedAt** | Collector nhận log lúc nào. | SIEM nhận 17:05. |
| **attemptedAt** | Connector gửi lệnh lúc nào. | 17:01. |
| **targetAcknowledgedAt** | Target trả phản hồi lúc nào. | 17:01:02. |
| **observedAt** | Readback target được thực hiện lúc nào. | 17:01:10. |
| **effectiveVerifiedAt** | Kiểm tra quyền thực tế kết thúc lúc nào. | 17:03. |

### Đo lag cần nêu rõ mẫu số và loại thời gian

~~~text
Leaver required deadline = businessEffectiveAt + allowedSla

Propagation latency = targetAcknowledgedAt - attemptedAt
Observed convergence latency = observedAt - businessEffectiveAt
Verified revocation latency = effectiveVerifiedAt - businessEffectiveAt
Collector ingestion lag = ingestedAt - producedAt
~~~

Các phép đo này chỉ có nghĩa khi **đồng bộ thời gian đủ tin cậy, nguồn được xác minh và timezone nhất quán**. Log có thể chứa clock skew; không lấy chênh lệch âm bất thường làm “thu hồi trước khi có sự kiện” nếu hệ thống lệch đồng hồ.

### Event time khác processing time

Một event HR phát vào ngày trước nhưng collector chỉ nhận hôm sau có **occurredAt cũ, ingestedAt mới**. Truy vấn theo thời gian sự kiện có thể cần late-arrival handling; truy vấn theo ingestion có thể phát hiện pipeline chậm. **Cả hai có giá trị**, không gộp thành một cột time.

## 22. Tính toàn vẹn và chống sửa/xóa nhật ký

Audit log có giá trị thấp nếu người được cấp admin có thể **sửa/xóa bằng chứng về chính thao tác của họ** mà không bị phát hiện.

### Những mục tiêu cần đạt

1. **Append-only hoặc immutable retention** trong phạm vi hệ thống hỗ trợ.
2. **Tách quyền** người quản trị IAM với người được phép sửa/cấu hình audit storage.
3. **Chống xóa và sửa âm thầm** bằng cơ chế lưu trữ, quyền hệ thống và bằng chứng toàn vẹn.
4. **Kiểm soát đường ingest**: producer authentication, signing/integrity, TLS và schema validation.
5. **Kiểm chứng completeness**: sequence gaps, cursor, expected heartbeats và collector health.
6. **Giữ lịch sử thay đổi policy logging/retention** như một sự kiện đặc quyền cần review.
7. **Đảm bảo backup/DR và khả năng phục hồi** đủ cho yêu cầu điều tra.
8. **Quản lý xuất chứng cứ** có approver, scope, chain of custody và access log riêng.

### Hash chain và signatures

Một thiết kế có thể tạo chuỗi băm:

~~~text
recordHash[i] = HASH(
    canonical(event[i]) || recordHash[i-1]
)

periodically:
    sign/checkpoint trusted root hash
    store checkpoint independently
~~~

**Hash chain không tự bảo đảm log không bị xóa**: người có quyền sửa cả log và checkpoint có thể tạo lại chuỗi. Cần **trust anchor độc lập, hạn chế quyền, retention bất biến, checkpoint/backup bên ngoài và cơ chế kiểm chứng**. Tương tự, chữ ký số chỉ có giá trị khi private key và quy trình phát hành được bảo vệ.

### Không ghi dữ liệu chưa xác minh như bằng chứng chắc chắn

Nếu producer do attacker kiểm soát, log do chính producer tạo có thể sai dù lưu trữ bất biến. Khi điều tra quyền nhạy cảm, nên **correlate nhiều nguồn độc lập**: IGA decision, target cloud audit, session log, network/API evidence và readback.

### Không xóa dấu vết khi sửa lỗi

Nếu event sai do bug mapping hoặc timezone, thực hiện **correction event** và ghi rõ phương pháp/nguồn; không âm thầm sửa bản ghi gốc rồi tuyên bố lịch sử không đổi.

## 23. Privacy, data minimization, masking và retention

Access change log có thể chứa dữ liệu nhạy cảm về nhân viên, ứng dụng, group đặc quyền, resource và account hành chính. Việc “audit” không cho phép thu thập vô hạn mọi thứ.

### Không bao giờ vô tình log

- **Password**, security answers, recovery codes, MFA seed/OTP.
- **Raw OAuth access/refresh/ID token** hoặc bearer session cookie.
- **Private key, secret API key, SSH private key, certificate key material**.
- **Authorization header, full request body** có credential hoặc PII.
- **SCIM User object toàn bộ** khi chỉ cần Group ID và member ID.
- **Nội dung dữ liệu khách hàng/báo cáo** khi thay đổi chỉ là permission.
- **Device fingerprint/vị trí cá nhân** không phục vụ mục đích kiểm toán đã định.

### Kỹ thuật bảo vệ

| Cách làm | Ví dụ | Lưu ý |
| --- | --- | --- |
| **Allowlist logging** | Chỉ ghi entitlementRef, identityRef, operation và kết quả. | An toàn hơn thu toàn payload rồi cố redact. |
| **Pseudonymization/reference** | Dùng stable ID thay vì lặp tên/email trong mọi event. | Vẫn là dữ liệu có thể liên hệ tới cá nhân; cần bảo vệ. |
| **Masking/redaction** | Che một phần nhãn/thuộc tính nhạy cảm. | Không được làm mất khả năng điều tra cần thiết. |
| **Separate evidence store** | Log tham chiếu snapshot được bảo vệ riêng. | Kiểm soát quyền truy cập, retention và integrity riêng. |
| **Encryption at rest/in transit** | TLS và storage encryption. | Không thay thế access control. |
| **RBAC/ABAC cho người đọc log** | Auditor xem summary; incident responder xem chi tiết theo case. | Có audit cả việc truy cập/xuất log. |
| **Retention policy** | Giữ theo rủi ro, hợp đồng và nghĩa vụ áp dụng. | Không invent một thời hạn chung cho mọi pháp luật. |
| **Legal hold** | Giữ bản ghi liên quan điều tra vượt lịch xóa thông thường khi hợp lệ. | Có owner, scope và cơ chế gỡ hold đúng thẩm quyền. |

### Mâu thuẫn giữ lâu và quyền xóa dữ liệu

Log có thể phải được giữ theo nghĩa vụ kiểm toán, đồng thời dữ liệu cá nhân cần xử lý phù hợp chính sách và luật áp dụng. Cần **data classification, retention schedules, minimization, legal hold, role-based access và review định kỳ**. Không tự khẳng định “audit log không bao giờ được xóa” hoặc “mọi log phải xóa ngay khi Leaver” trong mọi bối cảnh.

### SIEM cũng là tài nguyên nhạy cảm

Một attacker đọc log có thể tìm **tên tài nguyên, role admin, quy trình approval, incident timing** để hỗ trợ tấn công. Audit system cần **least privilege, MFA, SoD, export approval, monitoring và secret detection** như các hệ thống trọng yếu khác.

## 24. Monitoring: phát hiện bất thường từ access change log

### Các mẫu đáng cảnh báo

| Mẫu | Rủi ro giả thuyết | Cần xác minh |
| --- | --- | --- |
| Grant GlobalAdmin ngoài approval workflow | Privilege escalation. | Break-glass, source authority, target audit, owner. |
| User tự approve quyền của chính mình | SoD/self-approval. | Linked IAM identities, delegation, policy exceptions. |
| Group admin cấp quyền cho Leaver | Stale grant hoặc bypass JML. | lifecycle sourceVersion/effectiveAt, target state. |
| FinanceExporter xuất hiện trở lại sau Mover revoke | Regrant/drift. | Source job/version, role mapping, direct grants. |
| Policy đổi Permit rộng hơn vào ban đêm | Unauthorized broad access. | Change window, approval, resource scope, actor. |
| Service principal được cấp tenant-wide role | Workload overprivilege. | Trust, owner, môi trường và necessity. |
| Một người cấp role rồi tắt audit | Che giấu hành vi. | Actor/SoD, log pipeline gap, independent audit. |
| Emergency access không có incident binding | Break-glass misuse. | Quy trình offline/custody hợp lệ có tồn tại không. |
| Revoke command ack nhưng readback vẫn có grant | Provisioning failure/residual access. | Target API, cache, retry, direct path. |
| SCIM Group đổi ngoài IAM | Drift hoặc thao tác admin trực tiếp. | Target-native logs và authority. |
| Số event của target giảm đột ngột | Logging outage, disable hoặc collector failure. | Health/sequence/checkpoints, không tự kết luận không có thay đổi. |
| Cấp quyền ngắn hạn liên tục sát expiry | JIT/session abuse hoặc workflow bất thường. | Nhu cầu nghiệp vụ, policy, actor, audit. |

**Cảnh báo là bằng chứng điều tra, không phải kết luận tự động rằng actor đã có hành vi gian lận.** Với các nguồn như IP, giờ hoạt động hoặc địa điểm, có thể có lý do hợp lệ. Cần kết hợp incident context, approval và target evidence.

### Risk-based prioritization

Ưu tiên cao hơn đối với **privileged roles, financial approvals, dữ liệu nhạy cảm, production access, cross-tenant trust, khả năng sửa audit hoặc tự cấp quyền**. Một thay đổi birthright Group bình thường có thể theo luồng tự động, còn grant GlobalAdmin thiếu approval nên được xem xét nhanh.

### Detection không thay preventive control

Nếu hệ thống chỉ tạo SIEM alert **sau khi** một người tự approve và release payment, nó không thay thế **SoD enforcement tại workflow/resource**. Kết hợp **preventive, detective và corrective controls**, và log kết quả của từng lớp.

## 25. Access review, reconciliation và chứng minh quyền đã hội tụ

Access review thường tạo các quyết định **Retain, Revoke, Modify, Investigate hoặc Exception**. Access change log cần bảo đảm:

1. Reviewer có authority phù hợp resource/tenant và không vi phạm SoD.
2. Quyết định gắn **reviewItemId/snapshotId/policyVersion**.
3. Remediation task có grant/path scope rõ ràng.
4. Target operation đã hoàn tất hoặc có lỗi cụ thể.
5. Target readback/verification cho biết **quyền hiệu lực** theo phạm vi cần thu hồi.
6. Nếu còn đường khác, event không được đánh dấu “toàn quyền đã thu hồi”.
7. Những quyết định trên snapshot cũ sau Mover/Leaver phải được **revalidate**, tránh tái cấp quyền trái chính sách.

### Reconciliation không phải “so hai list tên role”

~~~text
Desired:
    subject Lan has report.read only

Observed:
    IdP Group FinanceReaders -> report.read
    App direct ACL -> report.export

Effective:
    API allows report.export using app-local session

Reconciliation:
    DRIFT_DETECTED: unintended direct grant + effective export path
    Remediation: remove direct ACL and handle session/token
    Verify: export denied; read still permitted if policy allows
~~~

**Một log chỉ ghi Group removal không bắt được direct ACL tồn dư** nếu target inventory không bao phủ. Cần biết **coverage và source freshness**, không tuyên bố “zero drift” khi ứng dụng không thể cung cấp grants.

### Coverage phải đi cùng kết luận

Nếu 80% target apps có connector/audit readback, báo cáo có thể nêu **80% coverage** nhưng không được suy rằng 20% còn lại không có thay đổi trái phép. Ghi **missing sources, permissions, pagination gaps và unverifiable targets** trong audit control report.

## 26. Pseudocode: ghi access change log an toàn

Các đoạn sau là **mã giả kiến trúc**. Chúng không phải API production hoặc schema chuẩn của SCIM/OIDC/SAML.

### 26.1. Ghi quyết định cấp quyền

~~~text
requestAccessChange(actorAuthn, beneficiaryRef, grantRequest):
    actor = resolveTrustedIdentity(actorAuthn)
    beneficiary = resolveTrustedBeneficiary(beneficiaryRef)
    resource = resolveTrustedResource(grantRequest.resourceRef)

    if actor unresolved or beneficiary unresolved or resource unresolved:
        return DENY_UNVERIFIED_IDENTITY_OR_RESOURCE

    currentLifecycle = loadAuthoritativeLifecycle(beneficiary)
    policy = loadCurrentAccessAndSoDPolicy(resource)
    if not currentLifecycle.permitsRequestedChange(grantRequest):
        writeDeniedDecisionWithReason("LIFECYCLE_GUARD")
        return DENY

    decision = evaluateApprovalAndSoD(
        actor, beneficiary, resource, grantRequest, policy
    )

    begin transaction
        persistAccessRequest(
            requestId, actor, beneficiary, resource,
            grantRequest, policy.version, decision
        )
        appendAuditOutboxEvent(
            eventId = newEventId(),
            eventType = "ACCESS_CHANGE_DECIDED",
            actorRef = actor.id,
            beneficiaryRef = beneficiary.id,
            resourceRef = resource.id,
            decision = decision.safeSummary,
            correlationId = requestId,
            sourceVersion = currentLifecycle.sourceVersion
        )
    commit transaction

    if decision == APPROVED:
        enqueueProvisioningCommandWithStableIdempotencyKey(requestId)

    return decision
~~~

### Những bảo đảm của đoạn trên

- **Actor** không bị nhầm với **beneficiary** hoặc approval authority.
- **JML sourceVersion** và policy version được lưu cùng quyết định.
- **Business change + outbox** nhất quán trong một transaction cục bộ.
- Một approval không tự ghi event **TARGET_VERIFIED** trước khi đọc trạng thái target.
- Không đưa secret/token hoặc toàn bộ HR record vào payload audit.

### 26.2. Thực thi provisioning và ghi kết quả

~~~text
applyAccessChange(command):
    current = loadLatestLifecycleApprovalAndPolicy(command)
    if current.supersedes(command.sourceVersion, command.policyVersion):
        appendAuditEvent(
            "ACCESS_CHANGE_SUPERSEDED",
            command.commandId,
            reason = "STALE_JML_OR_APPROVAL"
        )
        return SUPERSEDED_WITHOUT_GRANT

    target = resolveAuthoritativeTarget(command.resourceRef)
    before = readTargetGrantWithVersion(target, command.grantRef)

    appendAuditEvent(
        "PROVISIONING_ATTEMPTED",
        command.commandId,
        expectedBefore = safeGrantSummary(before)
    )

    result = applyIdempotentlyWithConcurrencyGuard(
        target,
        command.operation,
        command.grantRef,
        command.idempotencyKey,
        expectedTargetVersion = before.version
    )

    appendAuditEvent(
        "TARGET_CHANGE_ACKNOWLEDGED_OR_FAILED",
        command.commandId,
        safeResponseMetadata(result)
    )

    observed = readBackAllRequiredTargetPaths(command)
    appendAuditEvent(
        "TARGET_STATE_OBSERVED",
        observed.safeSummary,
        observedAt = now,
        sourceVersion = observed.targetVersion
    )

    if not observed.matchesCurrentDesiredState:
        createRemediationCase(command, observed)
        return PARTIAL_FAILURE

    verification = verifyEffectiveAccessWithinApprovedScope(command)
    appendAuditEvent(
        "EFFECTIVE_ACCESS_CHECKED",
        verification.safeSummary,
        verifiedAt = now
    )

    return VERIFIED if verification.allRequiredChecksPass
           else PARTIAL_FAILURE_OR_UNKNOWN
~~~

**Nếu GET readback cũng lỗi**, không trả VERIFIED; ghi **UNKNOWN/INCOMPLETE**, phân biệt lỗi xác minh với việc target thực sự không còn grant.

### 26.3. Nhận event trùng hoặc đến muộn

~~~text
ingestAccessEvent(event):
    if not verifyProducerAndSchema(event):
        quarantineInvalidEvent(event.safeReference)
        return REJECTED

    if eventIdAlreadyCommitted(event.eventId):
        recordDuplicateDeliveryMetric(event.source)
        return IDEMPOTENT_ALREADY_INGESTED

    if event.sourceVersion olderThan currentKnownVersionForSameEntity:
        persistAsHistoricalSupersededEvent(event)
        doNotApplyAsNewDesiredState(event)
        return HISTORICAL_ONLY

    persistNormalizedEventAndCheckpointAtomically(event)
    updateDerivedViewUnderVersionGuard(event)
    return INGESTED
~~~

Một **event audit đến muộn vẫn là bằng chứng lịch sử**; không vứt bỏ mà không ghi nhận. Chỉ không được để nó **thay thế desired/current state** hoặc tái cấp quyền trái policy.

### 26.4. Đánh dấu verified có phạm vi

~~~text
verifyRevocation(caseId):
    case = loadAccessChangeCase(caseId)
    expectedPaths = case.requiredAccessPaths
    observations = collectCurrentEvidence(expectedPaths)

    if observations.incomplete:
        appendAuditEvent(
            "ACCESS_CHANGE_VERIFICATION_INCOMPLETE",
            missingPaths = observations.missingSafeRefs
        )
        return UNKNOWN_WITH_OWNER_AND_DEADLINE

    if observations.anyPathStillEffective:
        appendAuditEvent(
            "RESIDUAL_ACCESS_DETECTED",
            affectedPaths = observations.affectedSafeRefs
        )
        return PARTIAL_FAILURE_WITH_CONTAINMENT

    appendAuditEvent(
        "ACCESS_CHANGE_VERIFIED",
        scope = expectedPaths,
        evidenceRefs = observations.protectedEvidenceRefs
    )
    return VERIFIED_FOR_DECLARED_SCOPE_ONLY
~~~

**Verified luôn có phạm vi.** Một negative test tại Finance API không chứng minh mọi ứng dụng khác đã thu hồi.

## 27. Failure modes và cách ghi log trung thực

| Mã lỗi/tình huống | Kết luận sai thường gặp | Kết quả cần ghi và xử lý |
| --- | --- | --- |
| **Collector timeout** | Không có event mới nghĩa là không có thay quyền. | SOURCE_UNAVAILABLE / INGESTION_LAG, kiểm cursor. |
| **HTTP 204 từ SCIM** | Mọi quyền của subject đã mất. | ACKNOWLEDGED, chờ readback và test. |
| **Target API trả 403** | Subject chắc chắn không có quyền. | Phân biệt 403 do thiếu connector permission với 403 khi test action. |
| **SCIM 404** | Account chắc chắn đã xóa. | Kiểm đúng tenant/ID, quyền connector, trạng thái target. |
| **Response timeout sau PATCH** | Lệnh chưa được thực hiện nên cứ PATCH lại. | UNKNOWN_RESULT, GET/readback trước retry. |
| **API phân trang thiếu trang cuối** | Không còn direct grants ở trang chưa đọc. | SNAPSHOT_INCOMPLETE, không certify. |
| **Group nested không được expand** | User không có quyền kế thừa. | COVERAGE_GAP, điều tra effective mapping. |
| **Một email trùng hai identities** | Chọn identity bất kỳ để ghép log. | IDENTITY_UNRESOLVED, giữ raw namespaces an toàn. |
| **Clock skew** | Target đổi quyền trước request không thể giải thích. | Giữ eventAt/observedAt/ingestedAt và clock quality. |
| **Producer bị tấn công** | Log do producer gửi luôn đáng tin tuyệt đối. | Cross-check target state và independent evidence. |
| **Outbox relay retry** | Hai event delivery = hai grants. | Deduplicate eventId; metric retry riêng. |
| **Approval trên snapshot cũ** | Retain nghĩa là được tái cấp sau Leaver. | SUPERSEDED_BY_LIFECYCLE, không regrant. |
| **Sửa Group rộng phạm vi** | Gỡ một User bằng cách xóa cả Group. | SCOPE_VIOLATION, đánh giá blast radius. |
| **Giảm policy Permit rộng nhưng token cũ còn** | PEP đã thực thi ngay. | EFFECTIVE_ACCESS_UNKNOWN/RESIDUAL, kiểm API. |
| **PAM session terminated** | Tất cả direct admin sessions bị chấm dứt. | Kiểm broker và target sessions độc lập. |
| **Machine secret rotated** | Secret cũ không còn hoạt động ở mọi consumer. | Revocation/rollout verification, phối hợp owner. |
| **Audit storage full** | Bỏ ghi log để tiếp tục mọi thao tác admin. | Theo fail-safe chính sách, alert và degraded control. |
| **Kết nối SIEM lỗi** | Xóa local events để không làm đầy đĩa. | Durable buffer/retention, vận hành khắc phục có kiểm soát. |
| **Access review quá hạn** | Tự Retain quyền để đóng campaign. | PENDING/ESCALATED, không biến im lặng thành approval. |
| **Security policy sửa trong lúc event pending** | Dùng policy cũ vì đã có approval trước. | Revalidate version tại commit khi scope/risk đòi hỏi. |
| **Audit log có token/secret** | Giữ nguyên để phục vụ điều tra. | Contain disclosure, rotate nếu cần, redaction controls có audit. |

### Cần phân loại “unknown” là một kết quả thực tế

Khi collector không có quyền đọc direct ACL, kết quả có thể là:

~~~text
desiredAccess = REVOKED
observedGroup = REMOVED
observedDirectAcl = UNKNOWN (403 connector permission)
effectiveExport = NOT_TESTED
overall = INCOMPLETE
~~~

Không biến trạng thái này thành **SUCCESS** hay **DENIED** để đạt SLA. Cần owner xử lý quyền connector/đường kiểm chứng, hoặc ghi rõ một giới hạn rủi ro còn tồn.

## 28. Điều tra sự cố và truy vấn access change log

Một nguồn log tốt cần hỗ trợ **truy vấn theo principal, resource, entitlement, actor, time window và correlationId**, đồng thời biết coverage/retention của từng nguồn.

### Câu hỏi 1: Ai cấp GlobalAdmin cho Minh?

Truy vấn logic:

~~~text
FILTER entitlementRef = "GlobalAdmin"
  AND beneficiaryRef = "IAM:ID-MINH-88"
  AND eventType IN {ACCESS_GRANT_APPLY_REQUESTED, TARGET_STATE_OBSERVED}
  AND time BETWEEN incidentStart AND incidentEnd

JOIN by correlationId/requestId:
    requester
    approver identity and authority
    executor account
    policy/version
    target role binding
    PAM activation
~~~

Điều tra không dừng ở “service provisioner là actor” vì cần xác định **ai hoặc chính sách nào có thẩm quyền tạo command**.

### Câu hỏi 2: Người đã Leaver còn quyền nào sau mốc hiệu lực?

~~~text
FOR each authoritative Leaver identity:
    determine businessEffectiveAt
    find all required targets and access paths
    compare desired revoke vs target observed
    join API/PAM/session verification within accepted window
    report verified, residual, partial_failure and unknown
~~~

Phải phân biệt **quyền còn được gán** và **quyền còn thực sự dùng được**. Một role tồn tại trong database có thể bị hard deny bởi lifecycle policy; ngược lại, app session có thể tiếp tục dù Group đã bị gỡ.

### Câu hỏi 3: Một app có quyền được cấp ngoài quy trình không?

~~~text
TARGET_NATIVE_CHANGE:
    actor = local-admin-88
    operation = ASSIGN_ROLE
    role = ReportExporter

IGA_REQUEST_MATCH:
    none found in trusted time window/correlation

Assessment:
    POTENTIAL_UNAUTHORIZED_CHANGE
    request owner review and target evidence
~~~

**Không tìm thấy approval trong IGA** có thể vì workflow ngoại lệ hợp lệ hoặc connector không thu đủ log, nên phải điều tra trước khi kết luận. Nhưng đó là **tín hiệu drift quan trọng**.

### Câu hỏi 4: Xung đột SoD được tạo khi nào?

Tái dựng thời điểm User có **cả hai khả năng xung đột trong cùng legalEntity/tenant** từ role grants, group inheritance, policy definitions và effective access evidence. Tìm:

- Actor/approval đã thêm capability cuối cùng.
- Quyền cũ đáng lẽ thu hồi từ Mover lúc nào.
- Có exception có thời hạn và kiểm soát bù không.
- API/resource đã Permit giao dịch trái SoD hay chỉ có potential conflict.
- Thay role definition/policy có mở quyền gián tiếp không.

### Câu hỏi 5: Tại sao grant bị tái cấp sau khi đã thu hồi?

Ghép **requestId, sourceVersion, idempotencyKey và target change audit** theo thứ tự nhân quả. Nếu retry của Joiner v41 đến sau Leaver v43, log phải chỉ ra **stale command** và việc target đã chặn hoặc bị regrant; không chỉ thấy hai event grant/revoke mâu thuẫn.

### Khái niệm SQL truy vấn (không ràng buộc vendor)

~~~sql
SELECT
    beneficiary_ref,
    resource_ref,
    entitlement_ref,
    correlation_id,
    event_type,
    source_version,
    occurred_at,
    recorded_at,
    result
FROM access_change_events
WHERE beneficiary_ref = 'IAM:ID-MINH-88'
  AND occurred_at >= :start_time
  AND occurred_at < :end_time
ORDER BY occurred_at, recorded_at, event_id;
~~~

**ORDER BY timestamp không chứng minh causality tuyệt đối.** Kết hợp version, causationId và target operation ID; nhớ xử lý clock skew, out-of-order và event đến muộn.

## 29. Các chỉ số đánh giá chất lượng access change logging

| Chỉ số | Định nghĩa thực hành | Cảnh báo diễn giải |
| --- | --- | --- |
| **Source coverage** | Tỷ lệ ứng dụng/tài nguyên bắt buộc có audit access change. | Không biết target thiếu không đồng nghĩa nó không có grants. |
| **Critical-event completeness** | Mức đầy đủ event grant/revoke/policy-change từ nguồn đã xác định. | Cần kiểm cursor/sequence/expected operations, không chỉ đếm event. |
| **Ingestion lag** | Độ trễ producer → audit pipeline. | Cần tách event time và processing time. |
| **Correlation completeness** | Bao nhiêu target changes nối về request/authority đáng tin. | Không tự đoán actor bằng email/time proximity. |
| **Identity resolution success** | Bao nhiêu principals map được stable IAM/workload IDs. | Unresolved phải giữ lại để điều tra. |
| **Approval-to-provisioning latency** | Từ duyệt đến thao tác target. | Không đồng nghĩa đã có quyền. |
| **Revocation verification latency** | Từ mốc revoke bắt buộc đến effective-access verification. | Phải theo risk tier và scope. |
| **Desired–observed drift** | Grant/policy nào khác yêu cầu IAM. | Gồm direct grants và permission mapping. |
| **Residual access after Leaver/Mover** | Đường quyền còn hiệu lực ngoài mốc chính sách. | Rủi ro cao dù approval log “complete”. |
| **Out-of-band privileged changes** | Grant/policy admin không có workflow hợp lệ được liên kết. | Cần xem emergency/break-glass exceptions. |
| **Stale command blocked** | Task cũ đã bị chặn trước khi regrant. | Không coi một số lớn chỉ là thành tích: cần điều tra pipeline. |
| **Retry/duplicate rate** | Tỷ lệ event và command retry. | Tách at-least-once delivery với duplicate business action. |
| **Unverified remediation count** | Quyết định revoke đã gửi nhưng thiếu bằng chứng. | Không gộp vào verified success. |
| **Audit integrity verification** | Kiểm chứng chain/checkpoint/immutable retention. | Hash không chứng minh producer đáng tin nếu không đối soát. |
| **Log leakage detections** | Phát hiện token/secrets trong logs. | Đánh giá nguyên nhân và containment. |
| **Policy rollout consistency** | PEP/connector đã dùng cùng policy version chưa. | Version drift có thể làm quyền trái intended policy. |
| **Audit access/export anomalies** | Log bị đọc/xuất trái thẩm quyền. | Audit store cũng phải được bảo vệ. |

### Ví dụ phân tích KPI

Trong một tuần có **100 quyết định Revoke**, 98 lệnh đã gửi tới target, 93 có readback đầy đủ và 82 đã được xác minh quyền hiệu lực trong scope bắt buộc. Khi đó:

- Decision completion có thể là **100/100** trong phạm vi ra quyết định.
- Command delivery được ghi là **98/100**.
- Target readback coverage đạt **93/100**.
- Effective revocation verified là **82/100**.

Không dùng một tỷ lệ **98%** để tuyên bố “98% truy cập đã được thu hồi an toàn” khi còn những đường chưa được xác minh.

### SLO logging không nên phá availability/safety

Với thao tác quản trị rủi ro cao, tổ chức có thể yêu cầu durable audit trước commit hoặc cơ chế tương đương. Với hệ thống safety-critical và emergency recovery, quyết định khi audit pipeline lỗi cần có **degraded-mode được thiết kế trước**. Không tự áp “mọi log lỗi thì dừng mọi hoạt động” hoặc “mọi log lỗi vẫn cho admin vô điều kiện” như quy tắc chung.

## 30. Ma trận kiểm thử Access change log

Kiểm thử gồm **độ đầy đủ của event, tính đúng ngữ nghĩa, danh tính/authority, JML, retry, audit integrity, privacy và bằng chứng từ target**. Nên dùng test identities, roles và resources được phép; không tự cấp đặc quyền production thật chỉ để kiểm tra log.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| ACL-01 | Request cấp role được chấp thuận và thực thi. | Có request, approval, command, target readback, verification với correlation. |
| ACL-02 | Request bị DENIED do thiếu authority. | Ghi actor, beneficiary, reason/policy; không sinh grant. |
| ACL-03 | User tự phê duyệt quyền bằng admin alias. | SoD phát hiện cùng IAM identity; log actor/approver đúng. |
| ACL-04 | User có hai local accounts khác tên. | Correlation đúng stable identity; vẫn giữ target account refs riêng. |
| ACL-05 | Email bị tái sử dụng cho nhân viên khác. | Không gộp lịch sử access change của hai người. |
| ACL-06 | Cùng role name tại tenant A và B. | Event giữ đúng tenant/resource namespace. |
| ACL-07 | Grant direct report.export bị gỡ, Group report.read còn. | Log đúng path và action, không báo all-access revoked. |
| ACL-08 | Thay role definition thêm quyền export cho nhiều User. | Ghi policy/role diff, blast radius và rollout evidence. |
| ACL-09 | ABAC department từ Finance sang Support. | Ghi access-affecting attribute change, policy link và effective scope. |
| ACL-10 | Joiner pre-provision trước startAt. | Phân biệt account created với business access activated. |
| ACL-11 | Joiner bị hủy, provisioning task cũ retry. | Command bị superseded, không tự cấp grant. |
| ACL-12 | Mover rút Group cũ nhưng direct ACL còn. | Log drift và residual path, không báo verified. |
| ACL-13 | Mover cấp role mới tạo toxic combination. | Ghi SoD rule/decision và chặn hoặc exception đúng authority. |
| ACL-14 | Leaver disable IdP nhưng JWT cũ còn Permit. | Ghi residual effective access, chưa VERIFIED. |
| ACL-15 | Leaver revoke nhiều target, một app timeout. | Parent case PARTIAL_FAILURE, child states chính xác. |
| ACL-16 | HR event v103 đến trước v101 retry. | Ghi event lịch sử, không regrant do version cũ. |
| ACL-17 | SCIM PATCH trả HTTP 204. | Ghi ACK, chờ target readback/effective checks. |
| ACL-18 | SCIM PATCH timeout sau khi target đã xử lý. | Readback và retry idempotent; không duplicate grant. |
| ACL-19 | Target GET trả 403 do connector thiếu quyền. | UNKNOWN/INCOMPLETE, không báo grant vắng mặt. |
| ACL-20 | Target pagination chỉ thu một trang. | Snapshot incomplete và cảnh báo coverage. |
| ACL-21 | Group nested mapping khác nhau ở app. | Không tự suy effective permission từ Group name. |
| ACL-22 | Target admin cấp quyền trực tiếp ngoài IGA. | Native audit/reconciliation phát hiện potential unauthorized change. |
| ACL-23 | PAM JIT eligibility được cấp rồi activation hết hạn. | Log cả eligibility, activation và session closure riêng. |
| ACL-24 | PAM broker session đóng nhưng direct SSH còn. | Không đánh dấu all privileged access revoked. |
| ACL-25 | Emergency account dùng khi central logging outage. | Alternate protected evidence và post-incident reconciliation. |
| ACL-26 | Service principal được cấp tenant-wide role. | Có principalType, owner, trust/policy, scope và approval. |
| ACL-27 | Service owner Leaver, bot production vẫn cần chạy. | Log ownership handoff và credential review, không xóa mù service. |
| ACL-28 | Private key bị rotate. | Event chỉ chứa secretRef/version/outcome, không log key bytes. |
| ACL-29 | Producer gửi event trùng eventId. | Consumer deduplicate và đếm delivery retry riêng. |
| ACL-30 | Hai business changes độc lập cùng beneficiary/role. | Không gộp nhầm chỉ vì content giống nhau. |
| ACL-31 | Target UPDATE commit nhưng event publish thất bại. | Outbox/durable recovery hoặc alert/reconciliation; không mất log âm thầm. |
| ACL-32 | Event lưu trước khi UPDATE rollback. | Không ghi sai “GRANTED”; có event attempt/failed và trạng thái đúng. |
| ACL-33 | Collector down, không có event một ngày. | Health/ingestion alerts, không tuyên bố zero changes. |
| ACL-34 | Event cũ đến sau khi đã ghi revoke. | Historical event không đảo current state. |
| ACL-35 | Giờ hệ thống target lệch 5 phút. | Giữ timestamps/source clock, không dùng ordering giả. |
| ACL-36 | Sửa log cũ khi phát hiện nhầm identity mapping. | Append correction event, bảo toàn original evidence. |
| ACL-37 | Người có GlobalAdmin thử xóa audit history. | Access control/immutable storage/integrity alert chặn hoặc phát hiện. |
| ACL-38 | Audit export chứa access token. | FAIL security test, khắc phục redaction và incident containment. |
| ACL-39 | Auditor chỉ được xem tenant B nhưng query sang A. | Log access control từ chối truy cập ngoài scope. |
| ACL-40 | Resource owner chọn Revoke nhưng target không hỗ trợ readback. | Result UNVERIFIED với owner/compensating control, không CERTIFIED. |
| ACL-41 | Role approval thay đổi trong lúc command pending. | Revalidate authority và policy trước commit khi bắt buộc. |
| ACL-42 | System phát token cũ sau Leaver do worker stale. | Log nguồn, version và action; detect unauthorized regrant. |
| ACL-43 | Một đối tượng ABAC đổi classification. | Log policy-impacting resource attribute update và affected scope. |
| ACL-44 | Cùng event qua hai collectors. | Dedupe theo event identity/provenance, không double count. |
| ACL-45 | Hết retention nhưng có legal hold hợp lệ. | Giữ phạm vi liên quan theo policy, audit lifecycle của hold. |
| ACL-46 | Hết legal hold. | Áp retention/xóa theo thẩm quyền, log action không lộ nội dung. |
| ACL-47 | API deny nhưng dữ liệu đã bị thay trước authorization. | FAIL: unauthorized side effect, audit liên kết incident. |
| ACL-48 | Event nói grant revoked, positive API vẫn trả tài liệu. | Detect inconsistency desired–observed–effective. |
| ACL-49 | Event source thiếu schema field bắt buộc. | Quarantine/validate và báo missing source, không ép giả giá trị. |
| ACL-50 | Schema version mới có trường optional. | Consumer cũ không mất các trường cốt lõi hoặc sai semantics. |

### Given–When–Then

~~~gherkin
Feature: Access changes are traceable and verifiable across IAM lifecycle

  Scenario: A mover's obsolete grant is removed and verified
    Given a trusted HR event moves Lan from Finance to Support
    And Lan has an app-local ReportExporter grant
    When the approved revoke workflow runs
    Then access change events identify the HR source and beneficiary
    And the target operation and readback are correlated
    And the case is not marked verified before required effective checks

  Scenario: An old Joiner command cannot restore access after Leaver
    Given a Joiner role assignment was queued at source version 41
    And a newer Leaver event was committed at source version 43
    When the old provisioning command retries
    Then no new usable entitlement is granted
    And an audit event records that the command was superseded

  Scenario: A target timeout does not prove a successful revoke
    Given an access revoke command was sent to a SaaS target
    When the connector times out before seeing the result
    Then the event records an unknown outcome
    And target readback or controlled retry is required
    And no verified-revoked assertion is produced without evidence

  Scenario: A native target administrator bypasses the access workflow
    Given an application supports direct role assignment
    And a privileged role is assigned outside the IGA workflow
    When the target-native audit collector or reconciliation detects it
    Then a potential unauthorized access change finding is created
    And the actual actor and target grant are preserved for review

  Scenario: A delivery retry does not create duplicate business changes
    Given an event was committed with eventId EVT-77
    When the collector receives EVT-77 twice
    Then the business event is represented only once in derived views
    And duplicate delivery telemetry may still be counted separately

  Scenario: A certificate key rotation does not leak the key into logs
    Given a workload credential rotation is authorized
    When the new credential is issued and activated
    Then access change events record safe credential references and outcomes
    And no plaintext secret or private key is included in the audit payload

  Scenario: Missing audit sources are not interpreted as clean access
    Given a required SaaS access API fails to return all pages
    When the access change reconciler evaluates an offboarding case
    Then the case is marked incomplete or partially verified
    And missing access paths and accountable owners are recorded
~~~

### Cần kiểm tra hành động tại target

Một lệnh báo 200/204 hoặc một event **ACCESS_REVOKE_VERIFIED** bị phát sai không đủ chứng minh mọi quyền thực tế đã mất. Với test an toàn, hãy xác nhận target state và **khả năng thực thi action trong context tương ứng**; nếu API trả Deny nhưng có side effect trái quyền, kiểm thử vẫn **FAIL**.

## 31. Tình huống thực hành

### Tình huống A — Ai đã cấp role admin?

**Bối cảnh:** SIEM phát hiện role CloudAdmin được gán cho Minh. Log duy nhất ghi actor là provisioning-worker.

**Câu hỏi:** Có thể kết luận bot tự quyết định cấp quyền không?

**Gợi ý:** Không. Cần nối **request, approval, source HR/IGA, authority, ruleId, executor và target evidence**. Bot có thể chỉ thực thi một approval; hoặc có thể đang làm lệnh stale/không hợp lệ.

### Tình huống B — Approval thu hồi nhưng app vẫn export được

**Bối cảnh:** Reviewer chọn Revoke cho Lan, IGA hiển thị Completed, nhưng Finance API vẫn cho report.export.

**Câu hỏi:** Log đang thiếu lớp nào?

**Gợi ý:** Thiếu **target readback, app-local access path và effective authorization verification**. Decision completed không phải entitlement revoked.

### Tình huống C — Hai tài khoản cùng một người

**Bối cảnh:** Một người yêu cầu quyền bằng normal account và duyệt bằng admin account. Log ghi hai email khác nhau.

**Câu hỏi:** Vì sao không đủ chứng minh phê duyệt độc lập?

**Gợi ý:** Cần IAM identity correlation giữa các accounts và SoD rule; hai account không mặc nhiên là hai người.

### Tình huống D — Thay chính sách ABAC nhưng không thấy User grant events

**Bối cảnh:** Policy đổi từ chỉ Finance được export sang Finance và Support được export. Không có Group assignments mới.

**Câu hỏi:** Access change log có cần ghi nhận không?

**Gợi ý:** Có. Đây là **policy-level access change**, có thể mở quyền cho một tập subject; cần before/after policy, owner, approval, scope, effective time và rollout/test.

### Tình huống E — Leaver nhưng PAT vẫn còn

**Bối cảnh:** IdP của nhân viên đã nghỉ báo Disabled, SCIM báo User inactive, nhưng PAT của developer portal còn gọi API.

**Câu hỏi:** Có thể báo offboarding verified không?

**Gợi ý:** Chưa trong phạm vi phải thu hồi PAT. Audit case phải ghi đường PAT còn hiệu lực, owner, remediation và test; không gộp “IdP disabled” thành “all access gone”.

### Tình huống F — Outbox relay gửi event hai lần

**Bối cảnh:** Relay publish event EVT-77, mất acknowledgment và publish lại. Consumer tạo hai alert grant độc hại.

**Câu hỏi:** Nên sửa ở đâu?

**Gợi ý:** Tạo eventId ổn định và consumer idempotent; tách **duplicate transport delivery** khỏi **distinct access changes**. Không loại bỏ legitimate second grant có eventId khác.

### Tình huống G — Log không có actor thật

**Bối cảnh:** Mọi thay đổi role trên SaaS đều xuất hiện actor “integration-bot”; log target không có IGA requestId.

**Câu hỏi:** Có đủ cho forensic attribution không?

**Gợi ý:** Chưa. Cần correlation giữa bot commandId với initiating authority/approver và logs nguồn, đồng thời thu target-native audit cho thay đổi trực tiếp.

### Tình huống H — Sự kiện đến muộn sau Leaver

**Bối cảnh:** HR v60 Leaver, sau đó queue giao lại v58 Joiner; producer ghi v58 với ingestedAt mới hơn.

**Câu hỏi:** Có nên xem v58 là trạng thái mới nhất?

**Gợi ý:** Không. Phân biệt sourceVersion, businessEffectiveAt và receivedAt; event cũ vẫn lưu làm lịch sử nhưng không được kích hoạt grant.

### Tình huống I — Admin sửa/xóa audit log

**Bối cảnh:** Một admin có quyền sửa IAM policy và xóa file log trên cùng server.

**Câu hỏi:** Làm sao tăng độ tin cậy bằng chứng?

**Gợi ý:** Tách quyền quản trị, dùng durable/immutable hoặc tamper-evident store với checkpoint độc lập, giám sát thay đổi logging configuration và kiểm tra integrity định kỳ.

### Tình huống J — SCIM timeout, lệnh đã có thể thực thi

**Bối cảnh:** SCIM PATCH remove member timeout, bot retry ngay bằng thao tác ghi đè toàn Group từ snapshot cũ.

**Câu hỏi:** Hai rủi ro là gì?

**Gợi ý:** Kết quả ban đầu **unknown**; retry mù có thể ghi đè membership mới của người khác. Cần readback, idempotency, PATCH hẹp/version guard nếu hỗ trợ và audit rõ retry outcome.

### Tình huống K — SIEM thiếu sự kiện nhưng báo zero changes

**Bối cảnh:** Collector SaaS bị 403, không lấy được events suốt 12 giờ. Dashboard báo “0 privileged changes”.

**Câu hỏi:** Kết luận có đáng tin?

**Gợi ý:** Không. Cần báo **SOURCE_UNAVAILABLE/INGESTION_GAP** và alert collector health, không biến thiếu dữ liệu thành bằng chứng hệ thống không thay quyền.

### Tình huống L — Đổi secret của bot

**Bối cảnh:** Credential production của bot được rotate. Developer đề nghị log cả token cũ và mới để dễ đối soát.

**Câu hỏi:** Có nên ghi raw tokens?

**Gợi ý:** Không. Lưu **secretRef, key version, issuer/audience nếu cần, rotation/revocation status, owner và evidence reference**; bảo vệ log khỏi rò rỉ.

### Tình huống M — Break-glass khi pipeline logging bị lỗi

**Bối cảnh:** Incident SEV-1 khiến IdP/SIEM không hoạt động; admin phải dùng recovery account để sửa trust.

**Câu hỏi:** Có cần ghi access change log?

**Gợi ý:** Có, qua **alternate protected audit/degraded-mode đã phê duyệt**, rồi reconcile sau phục hồi. Không nên hứa rằng online SIEM đã ghi đủ nếu nó đang lỗi.

### Tình huống N — Reviewer quyết định Revoke nhưng session admin còn mở

**Bối cảnh:** IAM/PAM đánh dấu privileged eligibility revoked, nhưng cloud admin token đã cấp tiếp tục hoạt động.

**Câu hỏi:** Event nào thiếu?

**Gợi ý:** Thiếu hoặc chưa đạt **session/token revocation verification**. Phải ghi effective access boundary, trạng thái còn dùng được và thời điểm xác minh.

### Tình huống O — Hậu kiểm phát hiện role đã cấp cho sai tenant

**Bối cảnh:** Access approval nói tenant A, target command thao tác tenant B do mapping resourceRef lỗi.

**Câu hỏi:** Audit cần giúp gì?

**Gợi ý:** Giữ **requested/approved resourceRef**, actual target ID/tenant, before/after, actor/command, error và correction evidence. Phải contain grant sai, không sửa im lặng lịch sử để trông như đã đúng.

### Tình huống P — Resource review không tìm được local grant

**Bối cảnh:** Access review chỉ có IdP Groups; SaaS direct ACL không có connector nên báo mọi người đã được chứng nhận.

**Câu hỏi:** Access change log cần chỉ ra giới hạn nào?

**Gợi ý:** Phải có **coverage metadata, unresolved access paths và source completeness**. Không suy “đã review sạch” khi chưa biết target-native changes.

## 32. Những sai lầm thường gặp

1. **Ghi access change như một dòng “User updated”.** Không biết entitlement/path/resource và before/after.
2. **Nhầm actor với beneficiary.** Bot provisioning bị coi là người yêu cầu hoặc người được cấp.
3. **Dùng email để nối mọi accounts.** Dễ gộp nhầm người, tenant và service.
4. **Ghi “Approved” là “Granted”.** Quyết định và thực thi là các giai đoạn khác nhau.
5. **Ghi SCIM 204 là “Revoked everywhere”.** App-local ACL, token và session còn tồn.
6. **Chỉ lấy log từ IGA.** Bỏ qua direct changes ở SaaS, cloud IAM và database ACL.
7. **Chỉ log membership, không log role/policy definition.** Một thay đổi role có thể mở quyền cho nhiều người.
8. **Không gắn effectiveAt/sourceVersion.** Khó phát hiện stale grant sau Mover/Leaver.
9. **Lấy ingestedAt làm thời điểm nghiệp vụ.** Lag collector làm sai timeline.
10. **Không có correlationId hoặc causationId.** Không truy nguyên được request tới target.
11. **Gộp duplicate transport thành duplicate business action.** KPI và alert bị sai.
12. **Không xử lý failure giữa business commit và audit publish.** Thay quyền không có bằng chứng.
13. **Tin nguồn log đã bị compromise là sự thật duy nhất.** Có thể ghi điều sai nhưng được lưu bất biến.
14. **Cho admin sửa/xóa audit log của chính họ.** Không bảo đảm điều tra độc lập.
15. **Log raw access token, refresh token hoặc secret.** Audit trở thành kho bí mật có thể bị đánh cắp.
16. **Chép cả SCIM User vào event.** Dư PII và tăng rủi ro tuân thủ.
17. **Bỏ qua service/workload identities.** Bot được cấp production role ngoài quy trình mà không ai phát hiện.
18. **Không kiểm completeness của API phân trang.** Snapshot thiếu bị diễn giải là tập grants rỗng.
19. **Không lưu before/after đúng loại.** Nhầm desiredAfter với observedAfter.
20. **Không lưu policy version.** Không tái dựng được vì sao quyền được phép ở thời điểm cũ.
21. **Tắt audit khi có incident.** Làm mất dấu vết thay đổi nhạy cảm.
22. **Không audit quyền xem/xuất log.** Người không có thẩm quyền có thể đọc cấu trúc đặc quyền.
23. **Tuyên bố “verified” không nêu scope.** Một API Deny bị hiểu thành mọi hệ thống đã an toàn.
24. **Không ghi correction event.** Lịch sử bị sửa im lặng, mất tính toàn vẹn.
25. **Đóng case khi còn PARTIAL_FAILURE.** Không phản ánh quyền tồn dư thực tế.
26. **Đánh đồng absence of events với absence of changes.** Collector lỗi cũng tạo khoảng im lặng.

## 33. Câu hỏi tự kiểm tra

**1. Access change log trả lời câu hỏi gì?**

Nó ghi nhận **quyền nào được yêu cầu, phê duyệt, thực hiện, quan sát và xác minh thay đổi**, bởi ai, cho ai, trên tài nguyên/phạm vi nào, theo policy và bằng chứng gì.

**2. Access change log có giống authentication log không?**

Không. Authentication log ghi sự kiện xác thực/đăng nhập; access change log ghi những biến đổi quyền, role, Group, policy, trust hoặc entitlement.

**3. Vì sao cần tách actor, beneficiary và approver?**

Vì người thực hiện kỹ thuật, người được hưởng quyền và người có thẩm quyền phê duyệt có thể khác nhau; việc phân tách cần cho attribution, approval và SoD.

**4. Một event “ACCESS_CHANGE_APPROVED” có chứng minh role đã tồn tại ở target không?**

Không. Cần provisioning outcome, target readback và, trong phạm vi rủi ro, effective authorization verification.

**5. SCIM PATCH 204 có bảo đảm mọi session/token đã mất quyền không?**

Không. SCIM cập nhật đối tượng tài khoản/Group theo khả năng target, không mặc nhiên revoke app cookie, PAT, JWT hay mọi direct grant.

**6. Before/after trong access change log cần ghi gì?**

Entitlement/grant/path/resource và trạng thái liên quan, đồng thời nói rõ giá trị nào là **desired** và giá trị nào là **observed**; tránh ghi nhầm dự kiến thành trạng thái đã kiểm chứng.

**7. Vì sao cần tenant và resource namespace?**

Vì cùng role hoặc User ID có thể tồn tại ở nhiều hệ thống/tenant. Bỏ namespace có thể dẫn đến log sai và thu hồi nhầm đối tượng.

**8. Một role definition đổi permission có phải access change không nếu không ai được gán role mới?**

Có thể có. Người đang giữ role có thể được hưởng quyền rộng hơn hoặc hẹp hơn ngay khi role/policy đổi, dù không có event membership.

**9. ABAC có thể làm thay quyền khi chỉ department thay đổi không?**

Có. PDP có thể Permit/Deny theo department/resource attributes; cần log access-affecting attribute change, policy version và phạm vi ảnh hưởng.

**10. JML sourceVersion hỗ trợ gì?**

Giúp nhận biết event/job cũ và ngăn grant bị tái cấp sau Mover/Leaver; cần hiểu version thuộc nguồn nào và effectiveAt ra sao.

**11. Vì sao eventId và commandId không phải một?**

Một command có thể tạo nhiều events theo giai đoạn, và một event có thể được giao nhiều lần. Event ID định danh bản ghi; command ID định danh thao tác provisioning.

**12. Làm sao phân biệt retry delivery với một grant thứ hai hợp lệ?**

Dựa trên eventId/provenance và business request/command identity; không dedupe chỉ vì hai event cùng User/role/timestamp gần nhau.

**13. Transactional outbox giải quyết điều gì?**

Giảm rủi ro **business change đã commit nhưng audit event không được ghi/publish** khi transaction cục bộ có thể lưu change và outbox cùng lúc. Nó không tự bảo đảm target SaaS, consumer hoặc toàn hệ thống exactly-once.

**14. Tại sao phải ghi occurredAt, recordedAt và effectiveAt riêng?**

Vì thời điểm sự kiện nghiệp vụ, thời điểm log được ghi và thời điểm quyền phải có hiệu lực có thể khác nhau, đặc biệt khi queue chậm hoặc clock lệch.

**15. Một hash chain có chứng minh log không thể bị giả không?**

Không tự đủ. Cần bảo vệ producer, checkpoint/trust anchor, quyền lưu trữ, retention, quyền kiểm chứng và đối soát nguồn độc lập.

**16. Những bí mật nào không nên có trong audit log?**

Password, access/refresh tokens nguyên vẹn, session cookies, private keys, MFA seeds/recovery codes, API keys và dữ liệu nhạy cảm không cần thiết.

**17. SIEM không nhận event trong một ngày có phải chứng minh không có quyền nào được cấp không?**

Không. Có thể collector/source down; phải kiểm event completeness, health, ingestion lag và native target audit.

**18. Vì sao Leaver cần log cả trạng thái token/session?**

Vì IdP disable và Group removal có thể chưa chặn app sessions, PAT, JWT hoặc privileged sessions; quyền tồn dư cần được quan sát và xử lý.

**19. Khi service owner Leaver, có nên xóa ngay mọi bot của họ không?**

Không. Thu hồi quyền cá nhân, chuyển service ownership, rotate credentials bị ảnh hưởng và giữ workloads hợp lệ theo chính sách.

**20. Điều gì cho thấy một quyết định Revoke đã được verified?**

Trong **phạm vi access paths và hành động bắt buộc**, target readback/kiểm tra quyền đã chứng minh không còn grant hoặc action bị Deny theo policy. Những đường chưa kiểm phải ghi UNKNOWN/PARTIAL_FAILURE.

**21. Access review log và access change log liên hệ thế nào?**

Access review ghi quyết định giữ/giảm/thu hồi dựa trên snapshot; access change log liên kết quyết định ấy với **remediation và target/effective verification**.

**22. Làm thế nào phát hiện direct grant ngoài IGA?**

Thu target-native audit events hoặc periodic reconciliation, đối chiếu request/approval có thẩm quyền và đánh dấu potential unauthorized changes cần review.

**23. Vì sao không được lấy event mới đến nhất làm trạng thái mới nhất?**

Vì retry cũ có thể đến sau, event time khác processing time; cần sourceVersion, causation, effectiveAt và authority.

**24. Việc cấp quyền có thể thành công nhưng log thất bại; phải làm gì?**

Cần durable audit/outbox khi có thể, fallback và alert, target reconciliation, phân loại gap thay vì che giấu; policy nhạy cảm có thể yêu cầu audit persistence trước commit.

**25. Vì sao phải audit cả việc truy cập audit logs?**

Vì nhật ký chứa thông tin nhạy cảm về nhân viên, vai trò và tài nguyên; truy cập hoặc export trái phép có thể gây rò rỉ và hỗ trợ tấn công.

## 34. Checklist thiết kế và nghiệm thu Access change log

### 34.1. Mô hình nghiệp vụ

| Kiểm tra | Tiêu chí đạt |
| --- | --- |
| **Định nghĩa access change** | Bao phủ direct grant, Group/role, policy, trust và effective access-affecting attribute changes theo scope. |
| **Actor và beneficiary** | Có danh tính riêng, tránh nhầm user gửi lệnh với người nhận quyền. |
| **Approval/SoD** | Có authority/approver/policy/version và các trường hợp tự duyệt bị phát hiện. |
| **Resource/tenant** | Sử dụng stable IDs có namespace, scope, environment và access path. |
| **Before/after** | Phân biệt desired vs observed, không đánh tráo trạng thái. |
| **JML** | Gắn sourceVersion/effectiveAt, chặn stale grants và đo residual access. |
| **Machine identities** | Có principalType, workload owner/trust, không đòi HR record cho bot. |

### 34.2. Kỹ thuật và vận hành

| Kiểm tra | Tiêu chí đạt |
| --- | --- |
| **Schema và provenance** | EventId, eventType, source, schemaVersion, actor, beneficiary, source version đầy đủ. |
| **Correlation** | Truy request → approval → command → target readback → verification theo ID. |
| **Durability** | Có outbox/durable buffer/recovery hoặc thiết kế tương đương phù hợp. |
| **Idempotency** | Retry/delivery trùng không làm sai số grant hoặc event business. |
| **Ordering** | Event đến muộn không đảo lifecycle/permission state hiện hành. |
| **Completeness** | Kiểm collectors, pagination, permission, checkpoints, ingestion gaps. |
| **Integrities** | Quyền lưu trữ/log retention, anti-tamper và checkpoint/independent verification theo risk. |
| **Privacy** | Allowlist/redaction, không lộ secret/token, có retention và least privilege. |
| **Access controls** | SIEM/audit store có quyền xem/xuất, SoD và ghi access events riêng. |
| **Target evidence** | Không nhầm ACK/HTTP response với observed/effective access. |
| **Reconciliation** | Có report desired–observed–effective với UNKNOWN/PARTIAL_FAILURE. |
| **Incident response** | Có alert nhạy cảm và đường logging khi một nguồn bị lỗi. |
| **Reporting** | KPI nêu mẫu số, scope coverage và thời điểm. |

### 34.3. Ví dụ tiêu chí nghiệm thu end-to-end

~~~text
Case: HR Mover Lan Finance -> Support

ACCEPT nếu:
  1. HR event có identityId, effectiveAt và sourceVersion.
  2. Access change log tạo requestId và correlationId.
  3. Old Finance grant và new Support grant có paths/scope rõ.
  4. SoD check đánh giá quyền cũ, quyền mới và policy version.
  5. Các lệnh connector có idempotencyKey và targetOperationId.
  6. Target ACK và readback được ghi tách biệt.
  7. Các app-local ACL hoặc access paths chưa kiểm được ghi UNKNOWN.
  8. Test hiệu lực trong scope cho thấy Finance export Deny.
  9. Retry command cũ không tái cấp FinanceExporter.
  10. Audit records không chứa secret/token và có integrity controls.
  11. Report nêu verifiedAt, residual paths, owner và SLA.
~~~

Nếu một trong các điều kiện bắt buộc không đạt, quy trình có thể vẫn hoàn thành **một phần**, nhưng kết quả audit không nên công bố **ACCESS_CHANGE_VERIFIED** cho toàn bộ phạm vi.

## 35. Tóm tắt một mô hình tốt

Một thiết kế **Access change log** đáng tin cần trả lời bốn lớp câu hỏi:

~~~text
WHY?
    HR lifecycle event, business request, policy, approval, exception

WHO/WHAT?
    actor, beneficiary, target principal, entitlement, resource,
    tenant, access path, before/desiredAfter

HOW?
    connector command, idempotency key, target operation,
    versions, timestamps, native audit events

DID IT REALLY CHANGE?
    target readback, effective access check, coverage,
    residual sessions/tokens, verification result and owner
~~~

Không thể biến việc ghi một event **“Access updated”** thành bảo đảm kiểm toán chỉ bằng cách thêm timestamp. Ngược lại, khi hệ thống có **các chủ thể và đường quyền đúng ID, nhân quả có thể truy lại, dữ liệu bền vững, kết quả thực thi tách bạch và xác minh theo phạm vi**, log có thể hỗ trợ cả điều tra an ninh lẫn chất lượng quản trị IAM.

## Ghi nhớ

- **Access change log** ghi **thay đổi quyền truy cập, lý do, actor/beneficiary/approver, resource, entitlement, policy và kết quả**, khác với authentication, activity và authorization decision logs.
- Tách **requested → approved → desired → provisioned/observed → effective verified**. Một approval, lệnh SCIM 204 hoặc IdP disable **không tự chứng minh quyền và token/session đã mất**.
- **Joiner** cần log pre-provisioning và startAt; **Mover** cần log quyền cũ/mới và SoD; **Leaver** cần từng đường revoke, kết quả ở đích, residual access và task stale bị chặn. Không cho approval cũ tái cấp quyền trái lifecycle.
- **IdP/SSO, SCIM, RBAC/ABAC/PBAC, PAM, tài khoản dịch vụ, machine identities và application-native ACL** cung cấp các nguồn entitlement/evidence khác nhau. Không kết luận quyền chỉ từ Group hoặc một connector đơn lẻ.
- Dùng **eventId, correlationId, causationId, commandId, stable identity/resource refs, sourceVersion, effectiveAt và observedAt** để tái dựng nguyên nhân và tránh nhầm duplicate/out-of-order events.
- Log cần **durable ingestion/outbox hoặc cơ chế tương đương, audit storage chống sửa, quyền truy cập tối thiểu, kiểm completeness, redaction và retention phù hợp**; tuyệt đối tránh biến SIEM thành kho raw secrets/tokens.
- **Desired–observed–effective reconciliation, target readback, kiểm tra quyền theo scope, cảnh báo thay đổi đặc quyền và trạng thái UNKNOWN/PARTIAL_FAILURE minh bạch** là nền tảng phát hiện drift, truy nguyên trách nhiệm và giảm quyền truy cập tồn dư trong toàn bộ vòng đời danh tính IAM.
