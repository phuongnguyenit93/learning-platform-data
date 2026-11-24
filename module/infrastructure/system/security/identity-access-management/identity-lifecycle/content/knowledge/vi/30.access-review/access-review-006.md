# Review theo resource: rà soát quyền truy cập lấy tài nguyên làm trung tâm trong IAM

> **Chương: Access review.** **Review theo resource (resource-centric access review)** là quy trình định kỳ hoặc theo sự kiện để **xác định ai hoặc danh tính máy nào hiện có thể truy cập một tài nguyên cụ thể, với quyền gì, qua đường cấp nào, và quyền đó có còn hợp lệ không**. Chủ sở hữu tài nguyên hoặc người được ủy quyền kiểm tra danh sách quyền theo phạm vi tài nguyên, quyết định giữ, thay đổi, thu hồi hoặc yêu cầu điều tra và theo dõi tới khi quyền thực tế ở ứng dụng đích khớp chính sách. Đây là một biện pháp quan trọng trong quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, kết hợp dữ liệu HR, IAM/IGA, IdP, SSO, SCIM, RBAC/ABAC/PBAC, tài khoản dịch vụ và nhật ký kiểm toán để giảm **quyền truy cập tồn dư (residual access)**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **review theo resource** và phân biệt với review theo user, role/entitlement và review theo ứng dụng.
2. Xác định **resource, resource owner, reviewer, subject, grant, access path và effective access**, đặc biệt khi có Group lồng, role kế thừa hoặc quyền cấp trực tiếp.
3. Thiết kế một chiến dịch review với **scope, thời điểm snapshot, completeness/freshness, tần suất, risk tier** và phân công reviewer có thẩm quyền.
4. Thu thập và chuẩn hóa quyền truy cập qua **IdP, SCIM, application API, cloud IAM, database, repository, storage, PAM** và workload identities.
5. Đưa ra quyết định có căn cứ **Keep/Retain, Revoke, Modify, Exception, Investigate**, quản lý trạng thái chưa xác minh và kiểm tra thu hồi tại đích.
6. Liên hệ review với **Joiner–Mover–Leaver**, access request/approval, least privilege, SoD, tenant isolation và phân quyền runtime.
7. Triển khai audit trail, đối soát desired–observed–effective, kiểm thử các tình huống phức tạp và đo kết quả bằng chỉ số vận hành.

## 1. Review theo resource trả lời câu hỏi gì?

Giả sử doanh nghiệp có một **bucket chứa báo cáo tài chính** tên FinanceReports-Prod tại tenant B. Những người và workload có thể truy cập bucket qua nhiều con đường:

- Lan thuộc Group FinanceReaders, được quyền đọc theo role.
- Minh được cấp trực tiếp quyền export cho một dự án cũ.
- Một tài khoản CI được cấp quyền ghi để tạo báo cáo tự động.
- Một đối tác có quyền đọc tạm thời nhưng hợp đồng sắp hết.
- Tài khoản quản trị cloud có khả năng thay bucket policy hoặc tự cấp quyền.

Nếu chỉ mở danh sách nhân viên và hỏi “Lan còn cần FinanceReader không?”, ta có thể bỏ sót **Minh, service account, đối tác, role admin và quyền cấp trực tiếp**. Review theo resource bắt đầu từ **bucket FinanceReports-Prod**, liệt kê mọi access path trong phạm vi đã định, sau đó hỏi: **Ai còn cần quyền nào trên bucket này, với mục đích gì, tới thời điểm nào?**

### Một hàng review đại diện

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| Resource | finance-reports-prod / tenant-b |
| Reviewer có thẩm quyền | Finance Data Owner |
| Subject | IAM:ID-LAN-2041 |
| Access path | IdP Group FinanceReaders → app role ReportReader |
| Effective action | report.read |
| Lý do sử dụng | Đối soát chi phí thuộc dự án P-17 |
| Trạng thái JML | ACTIVE, department=FINANCE |
| Granted until | 2026-12-31 |
| Quyết định | RETAIN tới ngày hết hạn |
| Evidence | request/approval, policy version, snapshot ID |

Đây là bản ghi **minh họa**, không phải schema chuẩn của SCIM hay một nhà cung cấp IGA. Một quyết định review phải đi tới **đối tượng quyền và đường truy cập cụ thể**, không chỉ gắn nhãn “đã xem” cho toàn bộ ứng dụng.

## 2. Phân biệt các cách tổ chức access review

Các chiến dịch review thường có cùng mục tiêu quản trị quyền nhưng khác **đơn vị bắt đầu**.

| Phương pháp | Câu hỏi trung tâm | Reviewer thường phù hợp | Điểm mạnh | Rủi ro bỏ sót |
| --- | --- | --- | --- | --- |
| **User-centric** | User này có còn cần tất cả quyền hiện có? | Manager hoặc sponsor. | Xem tổng thể quyền của một người. | Manager khó hiểu quyền kỹ thuật của từng resource. |
| **Resource-centric** | Ai đang truy cập resource này và còn cần quyền nào? | Resource/data owner. | Xét rủi ro theo dữ liệu, hệ thống, tenant cụ thể. | Inventory thiếu access path hoặc owner không nắm hết nhóm kế thừa. |
| **Application-centric** | Những ai có account/role trong ứng dụng? | Application owner. | Dễ bao phủ app, license, local account. | Scope một resource nhạy cảm có thể bị lẫn giữa nhiều role. |
| **Role/entitlement-centric** | Ai giữ role/entitlement này và định nghĩa quyền có phù hợp? | Role/entitlement owner. | Chuẩn hóa vai trò và các nhóm quyền. | Có thể bỏ sót direct grants hoặc ABAC ngoài role. |
| **Privileged access review** | Ai có khả năng admin, trực tiếp hoặc gián tiếp? | Security/PAM/platform owner. | Tập trung blast radius và escalation. | Privileged session, token và service principal ngoài inventory. |

Một chiến dịch **không nhất thiết chỉ dùng một kiểu**. Ví dụ hệ thống CRM có application-centric review cho mọi account, resource-centric review cho bộ dữ liệu nhạy cảm và privileged review cho những tài khoản có quyền export toàn bộ dữ liệu.

### Khi nào nên ưu tiên resource-centric?

- Tài nguyên đặc biệt nhạy cảm, ví dụ hồ sơ nhân sự, dữ liệu khách hàng, nguồn mã production, secrets hoặc báo cáo tài chính.
- Tài nguyên có **resource owner** rõ và quyền thường xuyên thay đổi theo project/tenant.
- Có nhiều đường cấp quyền: Group, role, ACL, resource policy, direct share, link, token hoặc delegated access.
- Cần đánh giá đúng **đối tượng dữ liệu và hành động** thay vì chỉ xét một role chung.
- Tổ chức muốn kiểm tra quyền tồn dư sau **Mover/Leaver** hoặc sau khi một dự án/ứng dụng kết thúc.

## 3. Các khái niệm nền tảng của một resource review

| Khái niệm | Định nghĩa thực hành | Ví dụ |
| --- | --- | --- |
| **Resource** | Đối tượng cần bảo vệ, được xác định bởi ID, loại và tenant. | Repository repo-A, bucket-B, database-C. |
| **Resource owner** | Đơn vị hoặc người chịu trách nhiệm rủi ro/quyền của tài nguyên. | Data owner FinanceReports. |
| **Reviewer** | Người/nhóm có thẩm quyền ra quyết định review trong chiến dịch. | Finance data owner hoặc delegate hợp lệ. |
| **Subject / principal** | Người, service principal, workload hoặc danh tính khác có thể dùng quyền. | IAM:ID-2041; workload:report-worker. |
| **Entitlement** | Một quyền, role, Group membership hoặc grant. | report.export trong tenant-b. |
| **Grant** | Quan hệ cấp quyền cụ thể từ nguồn tới subject hoặc role. | IAM role binding cho bucket-B. |
| **Access path** | Chuỗi quan hệ qua đó subject có thể đạt tới tài nguyên. | User → Group → role → resource. |
| **Direct access** | Quyền gán trực tiếp cho subject. | User Minh được chia sẻ tài liệu. |
| **Inherited access** | Quyền kế thừa từ Group, role, policy, folder, tenant hoặc parent resource. | Project Editor được đọc repository con. |
| **Effective access** | Quyền subject **có thể thực sự sử dụng** trong điều kiện hiện hành. | Đọc file qua API với token đúng audience. |
| **Desired access** | Quyền **nên có** theo policy, nhiệm vụ, phê duyệt và lifecycle. | Chỉ FinanceReader được report.read. |
| **Observed configuration** | Grant/Group/ACL đang được hệ thống đích báo cáo. | Minh còn role Exporter trong bucket policy. |

Ba lớp **desired, observed, effective** cần phân biệt: resource owner có thể quyết định Minh **không nên** có quyền export; IAM gửi lệnh revoke thành công; nhưng một local session hoặc token vẫn còn khả năng export trong thời gian nhất định.

### Resource identity cần có namespace

~~~text
Resource ref = (system, tenant, environment, resourceType, resourceId)

Ví dụ:
    system       = CLOUD-STORAGE
    tenant       = tenant-b
    environment  = production
    resourceType = BUCKET
    resourceId   = finance-reports-prod
~~~

Không kết luận hai tài nguyên cùng tên ở **tenant A** và **tenant B** là cùng resource. Tương tự, cùng một Group name tại IdP và SaaS có thể có các ID, owner và quyền khác nhau.

## 4. Từ direct grant đến effective access: vì sao cần access-path graph?

Nếu chỉ xem ACL gán trực tiếp, resource review có thể bỏ sót quyền phát sinh qua **Group lồng nhau, role delegation, inheritance, resource policy và các quyền sửa chính sách**.

~~~mermaid
flowchart LR
    U["Lan<br/>IAM identity"] --> G["IdP FinanceReaders"]
    G --> R["SaaS ReportReader role"]
    R --> D["Finance report R-105"]
    M["Minh"] --> E["Direct Export entitlement"]
    E --> D
    W["Report Worker<br/>workload identity"] --> S["Service role"]
    S --> D
    A["CloudAdmin"] --> P["Can edit resource policy"]
    P --> D
~~~

Các đường trên có mức rủi ro khác nhau:

1. **Group-based read:** Lan có thể đọc nếu app ánh xạ Group đúng và policy runtime cho phép.
2. **Direct export:** Minh có thể xuất dữ liệu ngay cả khi không thuộc FinanceReaders.
3. **Machine access:** Worker ghi báo cáo theo service identity, có thể hoạt động dù manager của một nhân viên đã Leaver.
4. **Administrative indirect capability:** CloudAdmin có thể chưa có quyền đọc dữ liệu trực tiếp, nhưng có thể **sửa resource policy** để tự cấp quyền; đây là một **privilege escalation path** cần được review.

### Tập grants không phải lúc nào cũng bằng effective permissions

Ví dụ:

~~~text
Direct grants:
    user Lan -> Group FinanceReaders
    Group FinanceReaders -> role ReportReader

Resource policy:
    Permit report.read khi tenant hợp lệ
    Deny report.read nếu lifecycleStatus != ACTIVE

Observed membership: Lan thuộc FinanceReaders
Effective permission: phụ thuộc vào cả role mapping, tenant,
                      lifecycle, session và policy tại ứng dụng
~~~

**Một bản ghi Group thành viên không bảo đảm truy cập thực tế**, và một Group vắng mặt không chứng minh không còn direct grant, service credential hoặc role cục bộ.

### Các dạng cấp quyền cần kiểm kê

| Loại | Tình huống | Cần thu thập |
| --- | --- | --- |
| Direct user role/grant | Minh được quyền export. | Local User ID, action, resource scope, grant source. |
| Directory/IdP Group | FinanceReaders được role Reader. | Group ID, membership đầy đủ, nested semantics. |
| SCIM Group | SaaS dùng Group để cấp role. | SCIM Group ID và local User ID, mapping role thực. |
| Resource ACL | File/folder chia sẻ trực tiếp. | ACL entries, inheritance, share targets. |
| Cloud IAM resource policy | Role hoặc principal có quyền trên bucket. | Policy bindings, trust, delegation, conditions. |
| Database grants | User hoặc role có SELECT/EXPORT. | Role membership, schema/table scope, inherited rights. |
| Sharing link | Tài liệu có link cho người ngoài/ẩn danh. | Scope của link, expiry, khả năng công khai. |
| Service principal/workload | Bot có quyền ghi hoặc deploy. | Workload identity, owner, audience, scope, keys. |
| Emergency/admin role | Admin có thể thay ACL/policy. | Quyền escalation và session điều khiển. |
| App-local override | Super-admin cấp role trong SaaS. | Quyền ngoài IAM/SCIM, audit và owner. |

Một số nền tảng không có API liệt kê **effective access**. Khi đó phải trình bày giới hạn thu thập và dùng kiểm tra bổ sung phù hợp, **không khẳng định đã kiểm kê đầy đủ**.

## 5. Resource owner và reviewer có thẩm quyền

Review chỉ có ý nghĩa khi **người ra quyết định hiểu tài nguyên và có thẩm quyền chịu trách nhiệm**. Không tự gán tất cả quyết định cho manager của subject, nhất là khi manager không biết ý nghĩa một role kỹ thuật hoặc mức nhạy cảm của dữ liệu.

### Các vai trò liên quan

| Vai trò | Trách nhiệm |
| --- | --- |
| **Resource owner** | Định nghĩa ai cần quyền trên resource, yêu cầu bảo mật, phạm vi và vòng đời tài nguyên. |
| **Data owner** | Đánh giá truy cập dữ liệu, phân loại, export và mục đích sử dụng. |
| **Application owner** | Hiểu mapping role/Group và quyền cục bộ của ứng dụng. |
| **Manager/sponsor** | Xác nhận quan hệ công việc, dự án và mục đích của người dùng/đối tác. |
| **Security/IAM/IGA owner** | Đặt chính sách review, risk tier, SoD, exception, luồng remediation. |
| **Reviewer** | Đưa ra quyết định Retain/Revoke/Modify/Investigate với bằng chứng. |
| **Provisioning operator/connector** | Thực hiện cập nhật entitlement sau quyết định. |
| **Auditor** | Kiểm tra quyết định, chủ thể, evidence và hiệu quả xử lý. |

**Reviewer** có thể chính là resource owner, một delegate có thời hạn, hoặc hội đồng được phân quyền theo chính sách. Nhưng họ **không được tự quyết ngoài scope được giao**.

### Đảm bảo reviewer không vi phạm SoD

- Người hưởng quyền nhạy cảm **không tự xác nhận giữ quyền của chính mình** nếu policy yêu cầu reviewer độc lập.
- Một người có account thường và admin riêng vẫn là **một identity** khi tính độc lập.
- Reviewer không được tự sửa resource owner/approval policy để duyệt rộng hơn phạm vi.
- Với Group admin, quyền owner có thể tạo quyền gián tiếp; cần Security hoặc PAM review độc lập.
- Nếu reviewer đã Leaver, Mover hoặc không còn ownership, pending tasks phải được reassign hợp lệ.
- Nếu resource owner không xác định, không tự động coi toàn bộ grants là hợp lệ.

### Quyết định Keep không phải “chứng nhận tài khoản”

Reviewer cần trả lời theo cặp **subject–resource–action** hoặc entitlement rõ ràng. “Tài khoản Minh còn làm việc” không chứng minh Minh còn cần `report.export` tại tenant B. Với workload cũng vậy: “service vẫn chạy” không chứng minh service cần `iam.policy.write`.

## 6. Xác định phạm vi và phân loại rủi ro chiến dịch review

Trước khi sinh task, chiến dịch phải định nghĩa **resource nào được review** và **đường quyền nào được tính trong scope**.

### Scope minh họa

~~~yaml
campaignId: FINANCE_REPORTS_Q4
reviewMode: RESOURCE_CENTRIC
resourceSelector:
  system: FINANCE_PLATFORM
  tenantId: tenant-b
  resourceType: REPORT_COLLECTION
  resourceIds:
    - finance-reports-prod
include:
  directGrants: true
  groupInheritedGrants: true
  servicePrincipals: true
  privilegedAndDelegatedPaths: true
  externalShares: true
ownerAuthoritySource: FINANCE_RESOURCE_REGISTRY
reviewSnapshotAt: "2026-12-01T01:00:00Z"
requiredCompleteness: VERIFIED_OR_EXCEPTION
decisionDeadline: "2026-12-15T23:59:59+07:00"
~~~

Đây là **cấu hình minh họa**, không phải schema chuẩn access review. Trường `include` chỉ thể hiện **ý định bao phủ**; phải kiểm tra từng connector có thật sự lấy được các loại grant đó hay không.

### Tiêu chí phân loại rủi ro

| Yếu tố | Ví dụ rủi ro cao |
| --- | --- |
| **Classification** | Dữ liệu tài chính, PII nhạy cảm, hồ sơ nhân sự, credentials. |
| **Action** | export, delete, admin, assignRole, rotateSecret thay vì read giới hạn. |
| **Blast radius** | Role có quyền toàn tenant/organization hoặc thay policy. |
| **External reachability** | Sharing link công khai, vendor hoặc tài khoản ngoài tổ chức. |
| **Privilege persistence** | Standing admin, API key dài hạn, grant không endAt. |
| **Ownership quality** | Owner không rõ, account mồ côi, service không sponsor. |
| **Lifecycle anomaly** | Subject TERMINATED, Mover mất vai trò hoặc contractor đã hết hạn. |
| **Access path complexity** | Nested Group, trust/delegation, role assumption khó nhìn thấy. |
| **Verification coverage** | Không đọc được policy/credential/session thực tế. |

Tần suất review nên dựa trên **rủi ro và yêu cầu tổ chức**: resource đặc quyền hoặc dữ liệu nhạy cảm thường cần review chặt và phản ứng theo sự kiện nhanh hơn một không gian cộng tác ít rủi ro. Không có một chu kỳ duy nhất đúng cho mọi hệ thống.

### Review theo sự kiện và review định kỳ

- **Periodic review:** quét theo lịch đã phê duyệt để phát hiện quyền đã trở nên không cần thiết.
- **Event-driven review:** kích hoạt khi Mover, owner change, project end, data classification tăng, grant vượt scope hoặc phát hiện bất thường.
- **Remediation-triggered review:** khi đối soát thấy drift, principal mồ côi hoặc quyền cấp trực tiếp ngoài workflow.

**Review không thay thế tự động offboarding.** Khi Leaver có hiệu lực, các quyền cần thu hồi phải được xử lý theo SLA, không chờ tới chiến dịch định kỳ tiếp theo.

## 7. Thu thập snapshot: dữ liệu phải đủ, mới và giải thích được

**Review snapshot** là tập bằng chứng về tài nguyên, principals, grants và access paths tại một mốc hoặc khoảng quan sát cụ thể. Trong hệ thống phân tán, đây có thể **không phải ảnh chụp giao dịch đồng thời**; cần ghi rõ thời điểm và độ mới từng nguồn.

### Nguồn quan sát

| Nguồn | Dữ liệu có thể thu | Giới hạn cần kiểm chứng |
| --- | --- | --- |
| **HR/contract** | Employment status, department, manager, endAt. | Không biết mọi quyền app-local và service principal. |
| **IAM/IGA** | Identity registry, desired entitlements, approvals, exceptions. | Desired không chứng minh quyền ở đích đã được thực thi. |
| **IdP/directory** | Group membership, app assignments, user state. | SSO session/Group token có thể lỗi thời, app có role riêng. |
| **SCIM Service Provider** | Users/Groups nếu API hỗ trợ, local IDs, active, members. | Không chuẩn hóa toàn bộ authorization, local ACL và token. |
| **Application API** | Roles, resource ACL, direct permissions, app sessions nếu cung cấp. | Có thể thiếu inherited/effective grants hoặc quyền export. |
| **Cloud IAM** | Role bindings, policies, trust, inherited organization/project grants. | Cần phân tích điều kiện, impersonation, service identities. |
| **Database** | Users, roles, table/schema grants, ownership. | Session active và runtime row-level security có thể khác. |
| **PAM/PIM** | Admin eligibility, activations, session, credential checkout. | Phiên ở target có thể không chấm dứt ngay khi revoke. |
| **Secret/token inventory** | API key/PAT/SSH key/certificate có scope phù hợp. | Không phải hệ thống nào cũng hỗ trợ liệt kê/revoke đầy đủ. |

### Snapshot record minh họa

~~~json
{
  "snapshotId": "snap-finance-20261201",
  "resourceRef": {
    "system": "FinancePlatform",
    "tenant": "tenant-b",
    "resourceType": "REPORT_COLLECTION",
    "resourceId": "finance-reports-prod"
  },
  "accessEntries": [
    {
      "subjectRef": "IAM:ID-LAN-2041",
      "targetUserId": "finance-user-88",
      "accessPath": [
        "idp-group:FinanceReaders",
        "app-role:ReportReader"
      ],
      "actions": ["report.read"],
      "grantSource": "SCIM_GROUP_MAPPING",
      "observedAt": "2026-12-01T01:00:21Z"
    }
  ],
  "collectionComplete": true,
  "observedThrough": "2026-12-01T01:00:21Z",
  "policyVersion": "finance-access-v12"
}
~~~

Ví dụ này là dữ liệu bài học, **không phải giao thức/tiêu chuẩn mới**. `collectionComplete=true` phải được chứng minh bằng kiểm tra pagination, permissions, sources, rate limits và các dữ liệu mà scope yêu cầu.

### Khi nào snapshot không đủ?

1. API chỉ trả trang đầu, thiếu Group hoặc ACL còn ở trang tiếp theo.
2. Connector không có quyền xem privileged policies hoặc resource share links.
3. Có Group lồng nhau nhưng ứng dụng chỉ trả direct members (thành viên trực tiếp).
4. Token/session còn quyền nhưng inventory chỉ liệt kê Group.
5. Identity mapping không chắc chắn; hai User cùng email alias.
6. Resource bị đổi owner/classification giữa hai thời điểm quan sát.
7. Thu thập thất bại do timeout/429 nhưng hệ thống chuyển thành danh sách rỗng.

**Observed empty** (đã kiểm đủ và không có grant) khác **observed unknown** (không lấy được dữ liệu). Một reviewer không nên nhận bảng rỗng khi thực tế một API đã lỗi.

## 8. Chuẩn hóa identity và access path trước khi hiển thị cho reviewer

Một người có thể có HR personId, IAM identityId, IdP subject và SCIM User ID ở nhiều namespace:

~~~text
HR person          = HRIS:EMP-2041
IAM identity       = IAM:ID-2041
IdP subject        = issuer-a/sub-92
Finance SaaS User  = tenant-b/finance-user-88
Cloud account      = tenant-b/cloud-admin-lan
~~~

Không thể ghép mọi tài khoản theo email hoặc displayName duy nhất. Review theo resource cần có **identity correlation có bằng chứng** và khi chưa xác minh phải đưa vào nhóm **UNRESOLVED/ORPHAN**, không chọn một User để thu hồi/cấp quyền ngẫu nhiên.

### Quy trình normalize

1. Tìm chính xác resource bằng **system + tenant + resource ID**; không dùng displayName độc lập.
2. Truy xuất direct ACL, Group/role binding, trust, delegation, external shares và service identities trong scope.
3. Resolve local principal đến IAM identity hoặc service registry; giữ nguyên local ID để thao tác sau này.
4. Duyệt Group/inheritance theo khả năng target, có **cycle detection** và giới hạn độ sâu.
5. Chuẩn hóa **action**, ví dụ Reader trong app A có thể không tương đương Viewer trong app B.
6. Xác minh nguồn và phiên bản của trạng thái HR/JML, approval và resource classification.
7. Gộp grant trùng **theo nghĩa quyền và access path**, nhưng lưu toàn bộ các đường còn quyền.
8. Gắn **confidence/completeness** để reviewer biết các trường hợp chưa đủ cơ sở.

### Một User có thể có nhiều đường truy cập

~~~text
Lan -> FinanceReaders -> ReportReader -> report.read
Lan -> Direct ACL                    -> report.read
Lan -> Local Exporter role           -> report.export

Nếu reviewer Revoke FinanceReaders:
    Lan vẫn có thể report.read qua Direct ACL.
    Lan vẫn có thể report.export qua Local Exporter.
~~~

Vì vậy, nếu quyết định **revoke toàn bộ quyền của Lan đối với resource**, remediation phải xác định **tất cả đường grant do tổ chức quản lý** và kiểm chứng effective permission. Nếu quyết định chỉ revoke một Group membership, phạm vi và hiệu quả phải được diễn đạt chính xác.

## 9. Thiết kế nội dung hiển thị trong một resource review

Reviewer thường không đủ thời gian đọc hàng nghìn ACL raw. Giao diện/phiếu nên trình bày **nghĩa nghiệp vụ trước**, sau đó cho phép mở bằng chứng kỹ thuật.

| Trường cần thấy | Mục đích |
| --- | --- |
| Resource name, owner, tenant, classification | Biết dữ liệu nào đang bị tác động. |
| Subject display và stable identityId | Biết ai hoặc workload nào có quyền. |
| Principal type | Human/contractor/vendor/service/built-in. |
| Role/actions thực tế | Biết quyền đọc, ghi, export, approve hay admin. |
| Access path | Direct, inherited, Group, resource ACL, trust. |
| JML/lifecycle status | Active, pending, suspended, terminated, contract expired. |
| Department, manager/sponsor, project | Xác minh nhu cầu hiện hành. |
| Grant reason, approver, last review | Có bằng chứng phê duyệt hay chỉ là cấp ngoài workflow. |
| Granted at / expires at / last used | Phát hiện quyền không dùng hoặc giữ quá hạn. |
| Effective-risk summary | Thấy SoD, cross-tenant, privileged action, external sharing. |
| Data freshness / collection status | Biết khi nào bằng chứng chưa đủ tin. |
| Available decisions | Retain, Revoke, Modify, Investigate, Exception theo policy. |

**LastUsedAt không phải bằng chứng duy nhất để giữ hoặc thu hồi.** Một break-glass identity hợp lệ có thể hiếm khi dùng; ngược lại, một quyền export được dùng thường xuyên không chứng minh nó cần thiết hoặc được phê duyệt.

### Ví dụ bảng cho Data Owner

| Principal | Đường quyền | Effective access | Lifecycle | Gợi ý xem xét |
| --- | --- | --- | --- | --- |
| Lan | Group FinanceReaders | report.read | ACTIVE, Finance | Retain nếu còn dự án và scope hợp lệ. |
| Minh | Direct app role | report.export | ACTIVE, đã Mover sang Support | Ưu tiên xem xét Revoke. |
| External partner | Shared link | report.read | Contract expired | Thu hồi/kiểm tra link và cache. |
| report-worker | Service principal | report.write | Workload ACTIVE, owner xác minh | Xem service purpose và scope. |
| unknown-user-77 | App-local ACL | report.read | UNRESOLVED | Investigate, không tự ghép theo email. |
| Cloud Admin group | Policy edit capability | Có thể thay policy resource | Privileged | Security/PAM review riêng. |

Không nên tự động chèn “Retain” làm mặc định khi reviewer chưa xem. Mọi hàng cần trạng thái rõ ràng; không trả lời và hệ thống lỗi **không phải chấp thuận**.

## 10. Quy trình review từ chiến dịch đến xác minh quyền

~~~mermaid
flowchart TD
    S["Xác định resource + owner + risk tier"] --> C["Collect resource ACL/Group/role<br/>trust, direct grants, service IDs"]
    C --> Q{"Snapshot đủ, mới,<br/>mapping đáng tin?"}
    Q -->|Không| X["DATA_INCOMPLETE / UNRESOLVED<br/>khắc phục trước khi certify"]
    Q -->|Có| N["Normalize access paths<br/>và tính effective rights"]
    N --> A["Assign reviewer hợp lệ<br/>owner, SoD, delegate"]
    A --> D["Reviewer xét từng grant<br/>Retain / Revoke / Modify / Investigate"]
    D --> P{"Đã có quyết định hợp lệ?"}
    P -->|Không| E["PENDING / ESCALATE / EXPIRE<br/>không auto-retain"]
    P -->|Có| V["Revalidate lifecycle, policy,<br/>authority và request version"]
    V --> R["Remediate via IdP / SCIM / App / PAM"]
    R --> T["Readback grant/ACL/session<br/>kiểm tra effective access"]
    T --> K{"Khớp desired?"}
    K -->|Có| F["VERIFIED + audit evidence"]
    K -->|Không| H["PARTIAL_FAILURE / DRIFT<br/>owner + compensation"]
~~~

### Các giai đoạn vận hành

1. **Plan:** chọn resource và rủi ro, định nghĩa control objective, phạm vi authority, tần suất và deadline.
2. **Collect:** lấy snapshot có provenance, completeness, freshness và phiên bản nguồn.
3. **Resolve:** ánh xạ principal, owner, entitlement và đường kế thừa.
4. **Assign:** phân task cho reviewer có thẩm quyền và phù hợp SoD.
5. **Decide:** review theo từng grant hoặc nhóm có cùng phạm vi; ghi lý do và quyết định.
6. **Revalidate:** kiểm tra thay đổi JML, quyền/reviewer và request mới so với snapshot.
7. **Remediate:** thực hiện thay đổi ở hệ thống sở hữu grant qua API/SCIM/PAM/quy trình.
8. **Verify:** readback resource, quyền hiệu lực, session/token tùy rủi ro.
9. **Close:** đóng những item đã xác minh; ghi lỗi còn tồn, exception, owner và thời hạn.

**Đóng campaign** không có nghĩa mọi tài nguyên đã an toàn nếu các item PARTIAL_FAILURE còn mở. Báo cáo cần tách rõ tỷ lệ quyết định của reviewer và tỷ lệ remediation đã xác minh.

## 11. Quyết định review: Retain, Revoke, Modify, Exception, Investigate

| Quyết định | Khi nào phù hợp | Điều kiện và hành động tiếp theo |
| --- | --- | --- |
| **RETAIN/KEEP** | Người/việc vẫn cần đúng quyền và policy cho phép. | Ghi justification, scope, owner, expiry và review sau. |
| **REVOKE** | Không còn nhu cầu, quyền hết hạn hoặc chủ thể không đủ điều kiện. | Gỡ những access path thuộc scope, readback, kiểm tra quyền tồn dư. |
| **MODIFY/REDUCE** | Cần một phần quyền nhưng grant hiện tại quá rộng. | Giảm role/action/resource/time; không tự mở rộng ngoài approval. |
| **INVESTIGATE** | Mapping không chắc, source mâu thuẫn, quyền hiệu lực không thể xác định. | Tạo case có owner; áp containment theo mức rủi ro. |
| **EXCEPTION** | Cần giữ một quyền đặc biệt không nằm trong rule thông thường, được duyệt. | Authority độc lập, lý do, scope hẹp, endAt và review. |
| **NO_RESPONSE / EXPIRED** | Reviewer chưa quyết định hoặc task quá hạn. | Escalation/expiration theo policy, không ngầm coi là Retain. |

### Một quyết định Retain hợp lệ cần trả lời

- Principal nào được giữ quyền?
- Access path/entitlement nào và action thực tế nào?
- Resource nào, tenant/environment nào?
- Cần cho dự án/nhiệm vụ nào, owner xác nhận ra sao?
- Có approval hoặc entitlement policy phù hợp không?
- Quyền còn hợp lệ tới ngày nào?
- Có SoD, cross-tenant hoặc privileged condition phải chặn không?
- Snapshot và reviewer authority có đủ mới tại thời điểm quyết định không?

### Ví dụ Modify: giảm quyền thay vì xóa account

Minh vẫn cần xem dashboard nhưng không còn cần export dữ liệu:

~~~text
Before review:
    report.read + report.export

Decision:
    MODIFY to report.read only
    scope: project P-17 / tenant-b
    endAt: 2026-12-31

Remediation:
    revoke ReportExporter role/direct grant
    retain/issue narrowly scoped ReportReader
    verify no other report.export path remains
~~~

Khi Modify bao hàm **cấp quyền mới hoặc mở rộng phạm vi**, áp lại approval workflow theo chính sách. Reviewer không được tự dùng nút Modify để cấp GlobalAdmin ngoài ý định chiến dịch.

### Lưu ý về Exception

Một ngoại lệ cần có **approver có thẩm quyền**, mục đích, deadline và cơ chế thu hồi. Không dùng exception để vượt **Leaver guard, tenant isolation, legal hold hoặc hard SoD** nếu tổ chức chưa có quy trình đặc biệt đủ thẩm quyền.

## 12. Resource review trong Joiner–Mover–Leaver

Review theo resource là một lớp kiểm soát **phát hiện và xác nhận quyền**, không phải nguyên nhân duy nhất khiến hệ thống cấp/thu hồi theo JML. Những thay đổi có hiệu lực phải được xử lý qua provisioning và authorization theo SLA; review giúp tìm phần đã bị bỏ sót hoặc không còn phù hợp.

### Joiner: quyền mới cần được xác định đúng resource

Một nhân viên mới có thể có User ở IdP và tài khoản ứng dụng đã được pre-provision. Resource review phải hỏi:

- Quyền này được cấp từ **birthright policy** hay có approval riêng?
- Nếu đã có Group từ ngày chuẩn bị onboarding, quyền thực tế có mở **trước startAt** không?
- Role có scope tới đúng resource, tenant, project hay rộng ra cả hệ thống?
- Có quyền direct hoặc privileged phát sinh do sao chép từ người tiền nhiệm không?
- Identity/SCIM User mapping đã được xác minh, tránh gán quyền nhầm người?

~~~text
Joiner Lan:
    startAt = 2026-12-01T09:00:00+07:00
    resource = finance-reports-prod
    desired = report.read từ startAt, tenant-b

Nếu grant đã tồn tại từ 2026-11-28:
    Review phân biệt pre-provisioning hợp lệ
    với effective read access bị mở quá sớm.
~~~

Reviewer có thể Retain **grant chuẩn bị** chỉ khi cơ chế chặn truy cập trước startAt được xác minh. Không chấp thuận một quyền đã mở sớm chỉ vì “nhân viên sắp vào làm”.

### Mover: phát hiện quyền tích lũy theo từng resource

Lan chuyển từ Finance sang Support. Trước Mover, Lan có quyền `report.export` trên FinanceReports-Prod. Sau Mover, chính sách mới không cho Lan xuất dữ liệu tài chính, nhưng app vẫn có một direct grant.

| Lớp | Trước Mover | Sau Mover mong muốn | Điều phải kiểm tra |
| --- | --- | --- | --- |
| HR/department | FINANCE | SUPPORT | EffectiveAt và sourceVersion. |
| IAM desired entitlement | report.export | Không còn | Có quyết định revoke chưa? |
| IdP Group | FinanceExporters | Đã gỡ | Token chứa Group cũ còn dùng không? |
| App direct ACL | Minh/Lan được export trực tiếp | Không còn | Resource owner phải thấy direct grant. |
| Resource Server | Chấp nhận export theo app-local role | Phải Deny | Test effective access/authorization tại API. |

**Review theo user** có thể thấy Lan đã đổi department nhưng không biết còn direct ACL ở một bucket. **Review theo resource** giúp owner Finance nhìn toàn bộ những ai vẫn có thể xuất dữ liệu đó.

Một campaign review mới được tạo sau Mover cần biết **policy thời điểm hiện hành**, tránh dùng danh sách manager/department đã chụp từ trước như căn cứ quyết định quyền hôm nay.

### Leaver: không được đợi kỳ review mới thu hồi

Khi HR xác nhận Leaver:

1. IAM/IdP thực hiện disable hoặc chặn sign-in mới theo chính sách.
2. SCIM/connector/API thu hồi Group, role, ACL và credential thuộc phạm vi.
3. PAM/ứng dụng xử lý phiên quản trị, token hoặc quyền cục bộ khi cần.
4. Resource review kiểm tra các resource quan trọng còn chứa **Leaver, orphan identity hoặc external access path** không.
5. Kết quả phải được xác minh tại resource; không có chứng cứ thì không báo sạch quyền.

Một quyết định Retain được ký tuần trước **không thắng trạng thái Leaver mới**. Trước lúc thực hiện bất kỳ cập nhật giữ/cấp quyền nào, worker phải kiểm tra lại lifecycle.

### Sự kiện JML đến sai thứ tự

~~~text
sourceVersion=71 JOINER -> grant FinanceReader
sourceVersion=72 MOVER  -> revoke FinanceReader
sourceVersion=73 LEAVER -> revoke all active employee grants

Actual processing:
    v73 applied
    old v71 provisioning retry arrives

Required:
    No new grant from v71 can resurrect access.
~~~

Review output và remediation task nên mang identityId, resourceRef, **sourceVersion/effectiveAt**, request/review version và correlationId. Khi xử lý grant, đối chiếu **lifecycle hiện hành**, không chỉ tin kết quả Retain trên snapshot cũ.

### Rehire, suspension và hợp đồng hết hạn

- **Rehire:** không tự khôi phục toàn bộ quyền theo review trước đây; xác minh identity và cấp theo vị trí, dự án mới.
- **Suspension:** xử lý theo chính sách đình chỉ, có thể giữ bản ghi account nhưng chặn quyền sử dụng.
- **Contractor/vendor:** so hợp đồng, sponsor và endAt; quyền còn tồn tại sau khi hợp đồng hết là chỉ dấu rủi ro dù tài khoản còn đăng nhập.
- **Account orphan:** không gán lại theo email tái sử dụng; mở case điều tra hoặc containment dựa trên rủi ro.

## 13. Quyền theo RBAC, ABAC và PBAC trong resource review

**Resource review không chỉ rà soát nhóm quyền được gán.** Quyền thực tế thường là kết quả của policy gồm vai trò, thuộc tính, quan hệ và điều kiện theo thời gian.

### Role-based

Ví dụ User có role ReportReader. Reviewer cần biết:

- Role này áp dụng cho **mọi report** hay chỉ project P-17?
- Role có được gán qua Group, direct assignment hoặc kế thừa?
- Có các role khác cấp `report.export` ngoài ReportReader không?
- Một Group Admin có thể tự gán ReportExporter không?

### Attribute-based

Một policy ABAC minh họa:

~~~text
PERMIT report.read KHI
    subject.lifecycleState == ACTIVE
    AND "FinanceReader" in subject.effectiveRoles
    AND subject.tenantId == report.tenantId
    AND report.projectId in subject.approvedProjectIds
    AND subject.clearanceRank >= report.classificationRank
    AND session.authenticationProfile đáp ứng policy
~~~

Review theo resource phải kiểm tra những thuộc tính quan trọng:

- Resource thuộc tenant và project nào?
- Classification hiện hành có khác lúc grant được phê duyệt?
- Subject có còn project approval?
- Policy có sử dụng department/role cũ từ IdP token không?
- Session có đạt yêu cầu xác thực khi dùng một hành động nhạy cảm?

### Policy conflict và explicit deny

Một role có thể Permit `report.read`, còn rule Leaver hoặc tenant isolation trả Deny. **Các grant hiện diện không tự chứng minh Permit**. Tùy policy engine, cần xác định **deny-overrides, hard guard hoặc combining semantics** phù hợp.

Ngược lại, một review cho thấy không có role trực tiếp không đủ chứng minh Deny nếu app có:

- Một policy Permit theo thuộc tính.
- Một sharing link công khai.
- Một trust cho service principal.
- Một quyền được thừa hưởng từ parent resource.

### Review các nguồn cho phép ngầm

Có hệ thống sử dụng **ABAC không cần liệt kê trước từng người**. Ví dụ:

~~~text
PERMIT repository.read KHI
    subject.department == ENGINEERING
    AND subject.tenantId == repository.tenantId
~~~

Reviewer không thể chỉ đếm Group membership để biết bao nhiêu người được truy cập. Cần đánh giá **phạm vi chủ thể thỏa policy**, nguồn thuộc tính và những người hiện hành có thể đáp ứng điều kiện. Nếu không thể liệt kê hết, báo rõ scope phương pháp và kiểm tra policy đối với các nhóm/boundary quan trọng.

## 14. Resource review cho privileged access

Quyền đặc quyền có thể không nằm trên ACL thông thường của tài nguyên. Một cloud operator có quyền đổi resource policy sẽ có khả năng làm thay đổi quyền của nhiều người, dù không có `report.read` trực tiếp.

### Những quyền cần được reviewer/Security nhìn thấy

| Quyền | Tại sao rủi ro | Cách xem xét |
| --- | --- | --- |
| **Direct Admin role** | Thay cấu hình, dữ liệu hoặc quyền. | Nhu cầu, owner, scope và thời hạn. |
| **Role/Group membership admin** | Có thể thêm User khác vào Group đặc quyền. | Escalation path và SoD. |
| **Policy editor** | Có thể tự thêm Permit trong IAM/resource policy. | Khả năng self-escalation, phê duyệt độc lập. |
| **Impersonation/assume role** | Có thể hành động dưới danh tính/role khác. | Trust conditions và maximum reachable permissions. |
| **JIT eligible grant** | Chưa active nhưng có thể kích hoạt admin. | Điều kiện activation, MFA, approval, expiry. |
| **Active privileged session** | Có thể tiếp tục thao tác sau revoke. | Session revocation, command scope và audit. |
| **Break-glass credential** | Quyền rộng khi khẩn cấp. | Owner, vault, alert, diễn tập, hậu kiểm. |

### Eligible khác Active

Một người có **PAM/PIM eligibility** có thể xin activate GlobalAdmin, nhưng hiện tại chưa dùng quyền admin. Review cần lưu cả:

- **Eligible access:** có thể xin/kích hoạt quyền nào và dưới điều kiện gì.
- **Active access:** đang có quyền nào tại thời điểm snapshot.
- **Session/token access:** đã có credential/session nào có thể tiếp tục hoạt động sau khi activation hết hạn.

Chỉ nhìn role active có thể bỏ sót **khả năng mở lại quyền** qua eligibility. Chỉ nhìn eligibility cũng chưa phản ánh các phiên đã phát.

### Quyết định của resource owner không được bỏ qua security guard

Resource owner có thể xác nhận cần một operator để sửa tài nguyên, nhưng quyền production admin có thể còn đòi **Security approval, SoD, phishing-resistant MFA, JIT/JEA và session monitoring**. Phiếu Retain của owner **không tự vượt các điều kiện** này.

## 15. Resource review cho service accounts và workload identities

Không phải principal nào cũng có HR record. Một bucket, database hoặc repository thường được truy cập bởi các **service principals, bots, build agents và workloads**.

### Mô hình quyết định cho một workload

~~~text
resource       = production/payments-repository
principal      = workload:payments-deployer
serviceOwner   = Payment Platform
environment    = production
grantedAction  = repository.write + deploy.update
approval       = service owner + platform owner theo policy
credential     = workload federation / short-lived token
workloadState  = ACTIVE
~~~

Reviewer phải trả lời:

1. Workload còn phục vụ nghiệp vụ và có service owner hợp lệ không?
2. Quyền được cấp có vượt mục đích của service không?
3. Principal có đúng environment/tenant/trust source không?
4. Có thể giới hạn theo repository, namespace, queue, API audience và thời hạn không?
5. Có secret/API key lâu năm, credential dùng chung hoặc token không owner không?
6. Khi decommission, trust, role, token và secret có được thu hồi không?
7. Một nhân viên rời team có từng biết credential hoặc quản lý pipeline không?

### Owner nghỉ việc không đồng nghĩa phải xóa service ngay

Nếu chủ sở hữu nhân sự của một bot nghỉ việc, service có thể vẫn cần chạy. Quy trình đúng thường là **chuyển service ownership, rà soát grants, rotate/revoke credential bị phơi lộ, giảm scope**, rồi kiểm tra health và truy cập. Không tự xóa workload đang phục vụ production khi chưa có quyết định decommission.

### Service account được biểu diễn khác nhau

Một workload có thể là SCIM User tại một ứng dụng, cloud service principal tại nơi khác hoặc Kubernetes service account. **Không giả định mọi machine identity đều có schema User/Group SCIM**. Review cần dựa vào resource/platform IAM thực sự quản lý principal và ghi nhận namespace của nó.

## 16. IdP, SSO, SCIM, PAM và resource review có trách nhiệm khác nhau

| Lớp | Việc nó hỗ trợ review | Điều nó không tự bảo đảm |
| --- | --- | --- |
| **HR / contract source** | Trạng thái JML, manager, department, sponsor/endAt. | Tập quyền thực tế trong mọi ứng dụng. |
| **IAM / IGA** | Desired access, request approval, certifications, SoD, identities. | Grant tại mọi target đã hội tụ. |
| **IdP / SSO** | Account, app assignments, Group và authentication context. | App-local roles, ACL, session đã mất quyền. |
| **SCIM** | User/Group provisioning và một phần observed membership. | Quyền của resource hoặc session/token được chuẩn hóa hoàn toàn. |
| **RBAC/ABAC/PBAC** | Quy tắc cho phép/từ chối theo role, attribute và context. | PEP của mọi API chắc chắn được kết nối. |
| **PAM / PIM** | Admin eligibility, activation, session và credential controls. | Role hoặc token ở target luôn bị revoke ngay. |
| **Application / Resource Server** | ACL, effective permissions và thực thi API. | Desired access và phê duyệt của HR/IGA. |
| **Access review workflow** | Quyết định giữ/thu hồi/sửa, evidence và remediation. | Quyền đã thay đổi ngay khi reviewer click Revoke. |

### Phân biệt trạng thái SSO và quyền tài nguyên

Ví dụ một User đã bị disable ở IdP nhưng còn:

- Cookie session tại ứng dụng không nhận logout.
- JWT access token còn hạn được API kiểm offline.
- Personal access token (PAT), SSH key hoặc API key độc lập.
- Local admin role không qua SCIM.

Resource review có thể phát hiện các đường này nếu scope/connector hỗ trợ, nhưng không mặc định việc **IdP disabled** là bằng chứng effective access đã biến mất.

### SCIM Group và resource ownership

Một SCIM Group có thể đại diện vai trò hoặc chỉ là một đối tượng tổ chức. Chỉ khi ứng dụng đích có **mapping Group → permission** được xác minh, reviewer mới có thể dùng Group để suy ra quyền. `members[].value` thường trỏ tới **local SCIM User ID**, không phải HR personId hoặc IAM identityId.

## 17. Sau khi quyết định Revoke: xử lý quyền tồn dư tại resource

Một quyết định `REVOKE` là **chỉ thị nghiệp vụ**. Để chứng minh thu hồi, cần áp vào đúng target rồi kiểm chứng.

### Các bước

1. **Revalidate:** beneficiary và resource mapping còn đúng, lifecycle/policy/decision còn hiệu lực.
2. **Chọn đường remediation:** gỡ direct ACL, Group membership, role binding, shared link, key/trust hay privilege eligibility tương ứng.
3. **Tránh gỡ quá phạm vi:** không DELETE Group đang dùng bởi nhiều người chỉ vì một User Leaver.
4. **Xử lý đồng thời:** PATCH phạm vi nhỏ, version/ETag hoặc guard nếu target hỗ trợ; không ghi đè Group từ snapshot cũ.
5. **Readback:** GET lại role/ACL/Group đầy đủ và so với desired.
6. **Đánh giá effective access:** nếu còn đường khác, token/session cũ, delegated access hoặc policy Permit, chưa thể báo không còn quyền.
7. **Audit:** lưu request, quyết định, target response, trạng thái thực tế và thời điểm xác minh.

### Tình huống revoke một đường nhưng còn đường khác

~~~mermaid
flowchart LR
    U["Minh"] --> G["IdP FinanceReaders"]
    U --> A["Direct Export grant"]
    G --> R["ReportReader"]
    R --> D["FinanceReports"]
    A --> D
    X["Review: REVOKE report.export"] --> Y["Remove direct Export grant"]
    Y --> Z["Readback + test no export"]
    Z --> D
~~~

Nếu quyết định chỉ thu hồi `report.export`, việc Minh vẫn được `report.read` qua FinanceReaders có thể là **đúng**. Nếu quyết định là thu hồi mọi quyền, cần xử lý cả đường đọc. **Phạm vi Revoke phải được mô tả chính xác**.

### JWT, refresh token và app session

- **Access token tự chứa:** một role/permission đã được đưa vào token có thể tiếp tục được Resource Server chấp nhận tới khi hết hạn nếu không có revocation/authorization lookup phù hợp.
- **Refresh token:** có thể cần bị revoke trong các trường hợp Leaver hoặc ngừng cấp access token mới; thu hồi refresh token không tự hủy mọi access token đang có.
- **App cookie/session:** có thể duy trì quyền local nếu ứng dụng không nhận sự kiện hoặc không revalidate.
- **PAT/API key:** là một đường truy cập khác, phải được kiểm kê và thu hồi theo khả năng target.

**Readback ACL sạch không phải bằng chứng duy nhất rằng mọi session/token đã mất quyền.** Cần định nghĩa **revocation boundary** và cách đo quyền tồn dư theo loại resource.

## 18. Xử lý dữ liệu stale, conflict và lỗi giữa campaign

Từ lúc chụp snapshot đến lúc reviewer quyết định có thể xảy ra Mover, Leaver, thay đổi owner, thay classification hoặc đổi role mapping.

### Ví dụ race

~~~text
2026-12-01:
    snapshot cho biết Lan ACTIVE, role FinanceReader

2026-12-03:
    Mover chuyển Lan sang Support, revoke FinanceReader

2026-12-04:
    reviewer mở snapshot cũ, bấm RETAIN FinanceReader

Không hợp lệ:
    job tái cấp FinanceReader theo quyết định Retain cũ

Yêu cầu:
    revalidate IAM lifecycle/sourceVersion,
    policy/current grants và scope trước mọi grant;
    quyết định cũ có thể phải supersede/review lại.
~~~

### Taxonomy trạng thái minh họa

| Trạng thái | Ý nghĩa |
| --- | --- |
| **SNAPSHOT_READY** | Dữ liệu đã thu thập đủ theo scope có xác minh. |
| **SNAPSHOT_INCOMPLETE** | Thiếu nguồn, thiếu trang, không xem được Group/ACL. |
| **IDENTITY_UNRESOLVED** | Không nối được principal với người hoặc workload. |
| **OWNER_UNRESOLVED** | Không xác định được reviewer/resource owner hợp lệ. |
| **PENDING_REVIEW** | Chưa có quyết định được ký bởi reviewer có thẩm quyền. |
| **RETAIN_APPROVED** | Quyền được giữ trong scope và thời hạn đã xác nhận. |
| **REVOKE_REQUESTED** | Đã yêu cầu thu hồi nhưng target chưa xác minh. |
| **MODIFY_REQUESTED** | Đã yêu cầu giảm/đổi quyền, còn chờ thực thi. |
| **EXCEPTION_TRACKED** | Ngoại lệ có owner, approval và endAt. |
| **REMEDIATION_PARTIAL_FAILURE** | Một hoặc nhiều access path/target chưa hội tụ. |
| **REVOKED_VERIFIED** | Đã xác minh các quyền trong scope không còn theo chính sách. |
| **SUPERSEDED** | Snapshot/review cũ không còn căn cứ thực thi. |

Các tên này **không phải enum chuẩn**; mục đích là tránh dùng một trạng thái “DONE” cho cả quyết định và thực thi chưa được xác minh.

### Những lỗi cần phân biệt

| Lỗi | Không nên làm | Hướng xử lý |
| --- | --- | --- |
| Timeout khi GET ACL | Coi danh sách grant rỗng. | Snapshot incomplete; retry/backoff, giữ dấu vết. |
| 429 rate limit | Bỏ các trang cuối. | Tôn trọng giới hạn và hoàn tất collection trước khi certify. |
| Duplicate identity mapping | Gỡ quyền của User chọn ngẫu nhiên. | Điều tra identity, tenant và nguồn mapping. |
| 404 cho một target resource | Kết luận mọi tài nguyên liên quan đã xóa. | Kiểm tra resourceRef/tenant và lỗi/permission. |
| Reviewer không phản hồi | Tự Retain để đạt KPI. | Escalate/expire theo policy; ưu tiên containment theo risk. |
| SCIM PATCH timeout | POST/PUT lặp không kiểm tra. | Readback và retry idempotent. |
| Role/ACL sửa ngoài workflow | Ghi đè ngay mọi thay đổi. | Xác định ownership, exception, approval, transaction version. |
| SoD conflict | Dùng reviewer thứ hai là cùng người qua admin alias. | Identity linking và reviewer independence. |
| SourceVersion cũ | Re-grant sau Leaver. | Chặn job stale trước tác vụ cấp quyền. |
| Không thể test effective access | Báo VERIFIED chỉ từ connector 200. | Đánh dấu unverified, biện pháp bù và owner. |

### Tính đầy đủ là tiền đề của kết luận

Nếu chỉ thu được 80% grant của resource vì API thiếu quyền, không thể đưa ra kết luận **tất cả principal hợp lệ**. Có thể review phần đã quan sát với phạm vi rõ, nhưng phải báo coverage và để các nguồn chưa thu thập ở trạng thái **chưa được xác nhận**.

## 19. Pseudocode quy trình review theo resource

Ví dụ dưới đây dùng tên hàm giả định để minh họa thiết kế, **không phải API hay code production**.

### Thu thập và lập bảng review

~~~text
buildResourceReview(resourceRef, campaignPolicy):
    resource = resolveTrustedResource(resourceRef)
    if resource is ambiguous or nonexistent:
        return RESOURCE_RESOLUTION_BLOCKED

    owner = resolveCurrentResourceOwner(resource, campaignPolicy)
    if owner not verified or owner lacks review authority:
        return OWNER_UNRESOLVED

    sources = findRequiredAccessSources(resource, campaignPolicy.scope)
    collection = collectAllPagesAndAccessPaths(sources, resource)

    if collection.hasMissingSource
       or collection.hasPageGap
       or collection.hasUnverifiedScope:
        recordCollectionFailure(resource, collection)
        return SNAPSHOT_INCOMPLETE

    normalized = []
    for rawGrant in collection.grants:
        principal = resolvePrincipalWithNamespace(rawGrant.subjectRef)
        path = resolveDirectAndInheritedPath(rawGrant, resource)
        actions = translateTargetRoleToActions(rawGrant, resource)

        if principal is ambiguous or path is unverifiable:
            markForInvestigation(rawGrant)
            continue

        normalized.add({
            principalId: principal.stableId,
            localPrincipalId: rawGrant.localId,
            accessPath: path,
            actions: actions,
            sourceVersion: rawGrant.version,
            observedAt: rawGrant.observedAt
        })

    return createVersionedReviewSnapshot(
        resource, owner, normalized, collection.completenessEvidence
    )
~~~

### Ghi quyết định reviewer

~~~text
decideResourceReview(itemId, actorAuthn, decision, justification):
    actor = validateTrustedAuthentication(actorAuthn)
    item = loadReviewItemWithVersion(itemId)

    if item is not PENDING_REVIEW:
        return CONFLICT_OR_PRIOR_RESULT
    if not actor.canReview(item.resource, item.risk, item.tenant):
        return DENY
    if violatesSoD(actor, item.subject, item):
        return DENY
    if item.snapshotVersion != currentApplicableSnapshotVersion:
        return REVALIDATION_REQUIRED

    subject = loadCurrentLifecycleOrWorkloadState(item.subject)
    resource = loadCurrentResourceAttributes(item.resource)
    if stateOrAuthorityCannotBeVerified:
        return INVESTIGATE

    if decision == RETAIN and subject is not eligible:
        return DENY
    if decision == RETAIN and not policyAllows(item.accessPath):
        return DENY

    saveDecisionAtomically(
        item.id, item.version, actor.identityId,
        decision, justification, policyVersion
    )

    if decision in [REVOKE, MODIFY]:
        enqueueScopedRemediation(item)
    return DECISION_RECORDED
~~~

### Thực hiện và xác minh remediation

~~~text
remediateReviewDecision(task):
    current = loadLatestJmlPolicyAndReviewState(task.subject, task.resource)
    if task.isStaleComparedTo(current):
        return SUPERSEDED_WITHOUT_GRANT

    if task.decision == RETAIN:
        return RECORD_ONLY_NO_NEW_GRANT

    if task.decision == REVOKE:
        targetPaths = findExactAccessPathsForRevocation(task)
        if mappingOrOwnershipUncertain(targetPaths):
            return INVESTIGATE

        for path in targetPaths:
            revokeIdempotentlyWithVersionCheck(path)

        observed = readBackAllRequiredPaths(task.subject, task.resource)
        effective = verifyEffectiveAccessWhereSupported(
            task.subject, task.resource, task.decision.scope
        )
        recordEvidence(task, observed, effective)
        return VERIFIED if requiredChecksPass else PARTIAL_FAILURE

    if task.decision == MODIFY:
        ensureNoPrivilegeExpansionWithoutApproval()
        return updateNarrowScopeAndVerify(task)
~~~

**Một quyết định Retain không nên tự động tái cấp quyền** nếu quyền tại đích vừa bị thu hồi hợp lệ do Leaver/Mover sau snapshot. Review là chứng nhận nhu cầu theo thời điểm; tác vụ cấp mới phải theo **approval và chính sách hiện hành**.

## 20. Kiểm toán, bằng chứng và khả năng giải thích

Một chiến dịch resource review phải có thể giải thích không chỉ **ai đã bấm Retain/Revoke**, mà còn **trên dữ liệu nào, vì sao và kết quả thực tế**.

### Các trường audit hữu ích

| Trường | Mục đích |
| --- | --- |
| campaignId / reviewItemId / snapshotId | Liên kết chiến dịch, từng hàng và bằng chứng dữ liệu. |
| resourceRef / tenant / classification | Xác định tài nguyên có rủi ro. |
| principalRef / IAM identityId / workloadId | Xác định chủ thể và mapping namespace. |
| accessPath IDs / actions | Biết đường grant nào được chứng nhận. |
| owner/reviewer identity và authority | Người chịu trách nhiệm, SoD và delegation. |
| decision/reason/decisionAt | Biết Keep/Revoke/Modify và cơ sở quyết định. |
| source systems/versions/observedAt | Phục dựng trạng thái dữ liệu tại thời điểm review. |
| HR JML sourceVersion/effectiveAt | Giải thích thay đổi nhân sự và giới hạn grant. |
| policy/approval/exception references | Chứng minh việc cấp giữ quyền có cơ sở. |
| remediation operation/status | Xác định thay đổi nào đã gửi tới target. |
| verifiedAt / effective-access result | Biết quyền thực tế đã khớp chưa. |
| correlationId/owner/error code | Phục vụ điều tra và retry. |

### Ví dụ event

~~~json
{
  "eventType": "RESOURCE_ACCESS_REVIEW_DECISION",
  "campaignId": "FINANCE_REPORTS_Q4",
  "reviewItemId": "item-044",
  "snapshotId": "snap-finance-20261201",
  "resourceRef": "FinancePlatform:tenant-b:finance-reports-prod",
  "subjectRef": "IAM:ID-MINH-88",
  "accessPathRef": "app-direct-role:ReportExporter",
  "action": "report.export",
  "reviewerIdentityId": "IAM:ID-DATA-OWNER-51",
  "reviewerAuthority": "FINANCE_DATA_OWNER_TENANT_B",
  "decision": "REVOKE",
  "reasonCode": "MOVER_ROLE_NO_LONGER_REQUIRED",
  "jmlSourceVersion": 72,
  "policyVersion": "finance-access-v12",
  "decisionAt": "2026-12-02T09:15:00+07:00",
  "remediation": "REVOKED_VERIFIED",
  "verifiedAt": "2026-12-02T09:16:05+07:00",
  "correlationId": "review-q4-item-044"
}
~~~

Đây là **schema audit minh họa**, không phải chuẩn của SCIM/OIDC. Không lưu mật khẩu, token nguyên vẹn, secret, private key, cookie hoặc dữ liệu nhạy cảm không cần thiết. Ghi đúng **actor và beneficiary**; với service account, lưu service owner nhưng không đồng nhất service identity với owner con người.

### Evidence quality

| Mức bằng chứng | Ví dụ | Giới hạn |
| --- | --- | --- |
| **Reviewer decision only** | Owner bấm Revoke. | Chưa biết connector có thực hiện hay không. |
| **Connector acknowledgment** | API trả 200/204. | Chưa chắc target state/role đã đổi, có thể eventual consistency. |
| **Target configuration readback** | API GET cho biết grant đã mất. | Chưa chứng minh session/token hoặc đường khác đã vô hiệu. |
| **Effective access verification** | Kiểm tra có kiểm soát cho thấy action bị Deny. | Scope test cụ thể; cần tránh tuyên bố ngoài những đường đã thử. |
| **Continuous monitoring/reconciliation** | Phát hiện tái cấp quyền và drift về sau. | Không thay thế một chứng cứ point-in-time đã đúng. |

Không phải mọi hệ thống đều cho phép kiểm thử effective access mà không tạo side effect. Với quyền xóa hoặc chuyển tiền, nên sử dụng **môi trường thử nghiệm, policy simulation, dry-run đáng tin hoặc các kiểm tra không phá hoại**, công bố rõ giới hạn bằng chứng.

## 21. Chỉ số đo chất lượng resource review

| Chỉ số | Cách hiểu |
| --- | --- |
| **Resource coverage** | Tỷ lệ tài nguyên thuộc scope đã có snapshot đủ theo yêu cầu. |
| **Access-path coverage** | Bao nhiêu loại direct/inherited/service/privileged/share đã được quan sát. |
| **Reviewer resolution rate** | Tỷ lệ resource có reviewer hợp lệ, không phải owner mồ côi. |
| **Decision completion rate** | Bao nhiêu review item đã có quyết định hợp lệ trước deadline. |
| **Revoke/Modify rate** | Tỷ lệ grant cần giảm hoặc thu hồi sau review. |
| **Remediation verification rate** | Quyết định cần sửa đã được xác minh tại target bao nhiêu. |
| **Residual access rate** | Quyền còn hoạt động sau thời điểm phải thu hồi. |
| **Orphan principal count** | Subject không map được người/workload owner. |
| **Cross-tenant/sensitive access anomalies** | Quyền vượt ranh giới hoặc classification. |
| **Privileged standing grant count** | Số grant đặc quyền thường trực và có thể bị khai thác. |
| **Exception expiry violations** | Ngoại lệ còn hoạt động sau endAt. |
| **Stale snapshot decisions** | Reviewer ký trên nguồn dữ liệu không còn đủ mới. |
| **Provisioning drift after review** | Quyền bị cấp lại ngoài ý định reviewer. |
| **Time to verified revocation** | Từ quyết định/thời điểm bắt buộc đến khi target xác minh mất quyền. |
| **Unverifiable target count** | Hệ thống chưa thể cung cấp bằng chứng quyền thực tế. |

Ví dụ: chiến dịch có 1.000 item, 980 item đã có quyết định, nhưng chỉ 60/100 lệnh Revoke được readback thành công. Khi đó **decision completion = 98%**, còn **verified revocation = 60%**, không thể công bố “98% quyền đã được xử lý an toàn”.

### Các kết luận sai từ số liệu

- **Retain rate cao** không tự chứng minh mọi quyền cần thiết; có thể là phê duyệt hình thức.
- **Revoke rate cao** không tự chứng minh an toàn nếu token/session vẫn dùng được.
- **Zero orphan users** không có nghĩa đúng nếu identity mapping đã bỏ qua những kết quả API không resolve được.
- **Access-path coverage 100%** chỉ có giá trị nếu danh mục nguồn và khả năng connector được kiểm chứng.

## 22. Ma trận kiểm thử resource-centric access review

Kiểm thử gồm **thu thập dữ liệu, identity resolution, reviewer authority, quyết định, remediation, quyền thực tế, JML và lỗi đồng thời**.

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| RAR-01 | Resource có direct grants, Group và role kế thừa. | Snapshot biểu diễn đủ các access paths đã khai báo trong scope. |
| RAR-02 | Một User có hai đường report.read. | Không mất đường thứ hai khi chỉ gỡ một grant. |
| RAR-03 | Nested Group có chu kỳ hoặc đích không hỗ trợ. | Không vòng lặp; đánh dấu giới hạn và không suy quyền sai. |
| RAR-04 | Identity ở SaaS và HR có email trùng. | Không gộp nhầm; dùng stable mapping. |
| RAR-05 | Resource cùng tên ở hai tenant. | Review tách đúng resource identity. |
| RAR-06 | API ACL phân trang, trang cuối lỗi. | SNAPSHOT_INCOMPLETE, không chứng nhận đủ. |
| RAR-07 | GET grants trả 403 do thiếu connector privilege. | Không coi tập rỗng; mở điều tra nguồn dữ liệu. |
| RAR-08 | Resource owner đã Leaver. | Task không giao cho owner cũ; reassign hợp lệ. |
| RAR-09 | Reviewer tự chứng nhận GlobalAdmin của mình. | SoD ngăn nếu cần reviewer độc lập. |
| RAR-10 | Một người dùng account phụ để làm reviewer thứ hai. | Không đếm hai người độc lập. |
| RAR-11 | Reviewer Retain quyền thiếu approval hoặc vi phạm tenant. | Không tự coi là được cấp hợp lệ; guard vẫn áp. |
| RAR-12 | Reviewer chọn Modify report.export → report.read. | Giảm quyền đúng scope, không mở rộng ngoài approval. |
| RAR-13 | Reviewer Revoke direct ACL, còn role kế thừa. | Báo quyền còn tồn, không đánh dấu full revoke. |
| RAR-14 | Leaver có app session/JWT cũ. | Kiểm tra revocation boundary và residual access. |
| RAR-15 | Joiner pre-provisioned trước ngày đi làm. | Không mở quyền nghiệp vụ trước startAt. |
| RAR-16 | Mover đã đổi department sau snapshot. | Retain cũ không cấp lại quyền không còn hợp lệ. |
| RAR-17 | Retry Joiner version cũ sau Leaver. | Không tạo lại access path. |
| RAR-18 | Service principal có owner đã nghỉ việc. | Bàn giao service owner, rotate/giảm scope khi cần. |
| RAR-19 | Workload staging có quyền production. | Phát hiện và từ chối/thu hồi theo trust policy. |
| RAR-20 | Privileged role có quyền tự sửa policy. | Xét indirect escalation path, không chỉ direct read. |
| RAR-21 | JIT eligibility đã revoke, session admin còn mở. | Không báo full verified nếu policy đòi chặn session. |
| RAR-22 | Sharing link public chưa hết hạn. | Review xác định phạm vi link và khả năng truy cập. |
| RAR-23 | Resource classification nâng mức nhạy cảm. | Trigger re-review theo risk/guard. |
| RAR-24 | Reviewer không phản hồi quá SLA. | Escalate/expire, không tự Retain. |
| RAR-25 | SCIM PATCH timeout sau khi đã gỡ. | Readback, idempotent retry, không gỡ nhầm cả Group. |
| RAR-26 | Hai worker cùng thay ACL. | Version guard/recompute tránh ghi đè thay đổi mới. |
| RAR-27 | App báo xóa role nhưng vẫn chấp nhận token. | Phát hiện session/token residue. |
| RAR-28 | API trả 403 nhưng vẫn ghi dữ liệu. | Test FAIL vì unauthorized side effect. |
| RAR-29 | Reviewer chọn Exception không endAt. | Không nhận ngoại lệ trái chính sách thời hạn. |
| RAR-30 | Chỉ có bằng chứng connector 200/204. | Trạng thái là provisioning acknowledged, chưa phải verified effective. |

### Given–When–Then

~~~gherkin
Feature: Resource-centric access reviews track real access paths

  Scenario: A mover loses obsolete direct access
    Given resource finance-reports-prod has a direct export grant for Minh
    And Minh moved to Support and no longer needs Finance export
    When the authorized data owner selects Revoke
    Then the direct export grant is removed from the target
    And any other export access paths are evaluated
    And verified access reflects the approved scope

  Scenario: Leaver cannot regain access from a stale review decision
    Given the review snapshot was taken before a Leaver event
    And a reviewer selected Retain on the old snapshot
    When the provisioning worker processes the decision after Leaver
    Then no new grant is issued
    And the decision is superseded or re-evaluated under current policy

  Scenario: An incomplete snapshot cannot be certified as complete
    Given the resource ACL API returns only the first results page
    When the campaign collects resource entitlements
    Then the snapshot is marked incomplete
    And no complete-coverage certification is produced

  Scenario: A service principal is reviewed with its own owner
    Given a production workload has a scoped repository write role
    And its original human owner left the organization
    When the review is routed
    Then the current service owner is resolved from a trusted registry
    And access is assessed by workload purpose and environment
    And unrelated production service operation is not deleted blindly
~~~

### Test phải kiểm tra hiệu ứng thật

Với hành động READ/EXPORT, kiểm tra dữ liệu có bị trả trái quyền không. Với WRITE/DELETE/APPROVE, xác minh không có side effect. Với quyền admin hoặc service principal, kiểm tra grants/trust và session nếu policy yêu cầu. Tránh thực thi thao tác phá hoại trên production chỉ để chứng minh Deny; dùng test environment hoặc phép mô phỏng được phê duyệt.

## 23. Các sai lầm thường gặp

1. **Chỉ dùng danh sách User trong IdP làm tập người có quyền.** Bỏ qua local accounts, service principals, resource ACL và direct grants.
2. **Không xác định resource ID + tenant.** Hai bucket/file trùng tên bị gộp nhầm.
3. **Mặc định người đang giữ role vẫn cần quyền.** Review biến thành thao tác bấm Retain hình thức.
4. **Không kiểm tra nested Group, role inheritance và delegation.** Effective access bị đánh giá thấp.
5. **Dùng email làm khóa identity duy nhất.** Alias và email tái sử dụng có thể dẫn đến thu hồi sai người.
6. **Tự chọn manager làm reviewer cho mọi tài nguyên.** Manager có thể không có data ownership/authority.
7. **Cho owner tự chứng nhận quyền đặc quyền của mình trái SoD.** Review không độc lập.
8. **Tự Retain khi reviewer im lặng hoặc task quá hạn.** Không có quyết định có căn cứ.
9. **Dùng snapshot cũ để tạo grant mới sau Leaver/Mover.** Quyền đã thu hồi có thể bị tái cấp.
10. **Xem lệnh SCIM/API thành công là quyền đã bị thu hồi.** App session/token, direct grant hoặc policy khác có thể còn.
11. **Gỡ cả Group vì một người cần mất quyền.** Làm mất quyền hợp lệ của các thành viên khác.
12. **Không review workload/service identity.** Bot có thể giữ credential production không owner.
13. **Không kiểm tra admin có khả năng tự sửa policy.** Bỏ sót quyền gián tiếp và escalation.
14. **Biến lỗi API thành danh sách rỗng.** Review báo giả là không còn quyền.
15. **Không gắn quyết định với snapshot/policy version.** Không thể tái dựng vì sao quyền được giữ hoặc gỡ.
16. **Đóng campaign khi remediation còn lỗi.** Số liệu hoàn tất không phản ánh effective access.

## 24. Tình huống thực hành

### Tình huống A — Cùng người, hai đường đọc

**Bối cảnh:** Lan có Group FinanceReaders và một direct share trên cùng báo cáo. Resource owner quyết định gỡ Lan khỏi Group vì Lan chuyển dự án, nhưng direct share vẫn tồn tại.

**Câu hỏi:** Có thể kết luận Lan không còn quyền đọc?

**Gợi ý:** Không. Phải kiểm tra cả direct share, quyền kế thừa và policy. Nếu yêu cầu là mất mọi report.read thì phải gỡ **tất cả access path phù hợp**, readback và xác minh effective permission.

### Tình huống B — Resource owner đã Leaver

**Bối cảnh:** Owner của bucket FinanceReports đã nghỉ việc. Campaign tự gửi email review tới owner cũ và quá hạn.

**Câu hỏi:** Có nên tự động Retain mọi quyền để đóng campaign?

**Gợi ý:** Không. Resolve owner hiện hành từ resource registry, phân quyền reviewer mới, xem xét SoD và escalation. Đánh dấu OWNER_UNRESOLVED nếu chưa xác minh.

### Tình huống C — Role của User đã thay đổi

**Bối cảnh:** Snapshot lấy ngày 01/12 ghi Minh ACTIVE ở Finance. Ngày 03/12 Minh Mover sang Support. Ngày 05/12 reviewer bấm Retain export vì nhìn thông tin cũ.

**Câu hỏi:** Quyết định có được tái cấp export không?

**Gợi ý:** Không. Revalidate lifecycle, policy, grant và sourceVersion hiện hành; quyết định dựa trên snapshot cũ cần supersede hoặc review lại.

### Tình huống D — Workload owner nghỉ việc

**Bối cảnh:** Service account report-worker có quyền write vào bucket production. Người từng sở hữu service đã nghỉ nhưng bot vẫn vận hành bình thường.

**Câu hỏi:** Resource review nên xử lý thế nào?

**Gợi ý:** Xác minh service identity trong registry, chỉ định owner mới, đánh giá service purpose/scope, rotate credential mà người cũ có thể biết; không xóa mù workload nếu chưa decommission.

### Tình huống E — Group admin với quyền gián tiếp

**Bối cảnh:** Một account không có role BucketReader nhưng có quyền thay cloud bucket policy, do đó có thể tự cấp quyền đọc.

**Câu hỏi:** Có được coi account đó không có privileged access tới resource?

**Gợi ý:** Không. Phải review quyền policy edit, delegation/trust và khả năng self-escalation, kể cả khi không có direct read grant.

### Tình huống F — SCIM cho thấy đã gỡ nhưng phiên còn dùng được

**Bối cảnh:** User Leaver bị gỡ khỏi Group SaaS bằng SCIM, song một app-local session vẫn export được.

**Câu hỏi:** Có thể đặt trạng thái REVOKED_VERIFIED chưa?

**Gợi ý:** Chưa trong phạm vi yêu cầu chặn export. Cần session/token revocation hoặc resource authorization lookup, đo residual access và theo dõi đến khi hội tụ.

### Tình huống G — API chỉ trả trang đầu

**Bối cảnh:** /Groups hoặc ACL API có 3 trang nhưng connector chỉ lấy trang 1 rồi đưa reviewer danh sách 20 người, trong khi còn 80 người.

**Câu hỏi:** Kết luận review sai ở đâu?

**Gợi ý:** Snapshot không đầy đủ. Không đánh dấu coverage 100%; hoàn thiện pagination, quota/retry và chứng cứ completeness trước khi certify.

### Tình huống H — Quyền export vẫn được sử dụng thường xuyên

**Bối cảnh:** Minh thường xuyên export báo cáo, nhưng policy hiện hành chỉ cho phép đọc vì role Mover đã thay đổi.

**Câu hỏi:** LastUsedAt gần đây có chứng minh cần Retain không?

**Gợi ý:** Không. Dùng nhiều có thể là tín hiệu nghiệp vụ hoặc lạm quyền; cần approval, role, SoD, classification và policy hiện hành.

### Tình huống I — Exception không có ngày hết hạn

**Bối cảnh:** Resource owner muốn giữ quyền vendor qua một sharing link vì “có thể sẽ cần hỗ trợ lại”, nhưng hợp đồng đã kết thúc.

**Câu hỏi:** Hành động phù hợp?

**Gợi ý:** Không Retain vô thời hạn chỉ dựa trên khả năng. Thu hồi theo chính sách, hoặc tạo exception có sponsor, scope, hợp đồng/approval và endAt phù hợp khi có nhu cầu hợp lệ.

### Tình huống J — Một người có nhiều tài khoản

**Bối cảnh:** Lan có normal account, admin account và một tài khoản SaaS địa phương; ba tên khác nhau cùng truy cập resource.

**Câu hỏi:** Resource review nên hiển thị và xử lý như thế nào?

**Gợi ý:** Gắn các local IDs về cùng IAM identity khi đã xác minh, nhưng giữ **từng access path và principal riêng** để xử lý revoke. Không xem ba tài khoản là ba người độc lập khi áp SoD.

### Tình huống K — Quyết định Revoke nhưng quyền bị thêm lại

**Bối cảnh:** Resource owner gỡ quyền ReportExporter, nhưng job dựa trên approval cũ liên tục thêm lại quyền.

**Câu hỏi:** Vấn đề ở đâu?

**Gợi ý:** Tranh chấp desired state và nguồn cấp. Xem ownership của grant, approval/policy, sourceVersion và cơ chế reconciliation; job stale phải không tái cấp quyền trái quyết định mới.

## 25. Câu hỏi tự kiểm tra

**1. Review theo resource khác gì review theo user?**

Resource-centric bắt đầu từ tài nguyên và hỏi **mọi principal/access path nào đang có quyền trên tài nguyên này**; user-centric bắt đầu từ một người và xem tập quyền họ có ở nhiều nơi.

**2. Vì sao chỉ xem SCIM Group.members có thể bỏ sót quyền?**

Vì ứng dụng có thể có direct grants, local roles, ACL, trust, sharing links và session/token không phản ánh đầy đủ qua SCIM Group.

**3. Direct access và inherited access khác nhau ra sao?**

Direct được gán trực tiếp cho principal; inherited đi qua Group, role, parent resource hoặc trust/policy khác. Một User có thể có cả hai.

**4. Resource identity cần chứa thành phần nào?**

Ít nhất một namespace đáng tin gồm **system, tenant, loại tài nguyên và resource ID**, có thể thêm environment; tên hiển thị đơn lẻ không đủ.

**5. Ai nên review một báo cáo tài chính nhạy cảm?**

Người có thẩm quyền về dữ liệu/tài nguyên, có thể cần manager/Security độc lập tùy policy; không mặc định manager của mọi User là người duyệt duy nhất.

**6. Một reviewer bấm Retain có chứng minh quyền hiện tại hợp lệ với mọi resource/action không?**

Không. Quyết định chỉ có phạm vi, thời gian và căn cứ cụ thể; runtime authorization vẫn phải kiểm tra policy.

**7. Vì sao không được coi lỗi API/thiếu trang là tập grants rỗng?**

Vì dữ liệu **unknown/incomplete** khác với **verified empty**; kết luận sai có thể che quyền tồn dư.

**8. Sau Mover, một quyết định Retain trên snapshot cũ có thể tái cấp quyền không còn hợp lệ không?**

Không được. Trước grant cần revalidate lifecycle, sourceVersion, policy và review version; nếu stale phải supersede/review lại.

**9. Tại sao Leaver không được chờ review định kỳ?**

Vì offboarding cần thu hồi theo thời điểm/SLA có hiệu lực; review là lớp xác nhận và phát hiện sai lệch, không thay quy trình chặn truy cập.

**10. Vì sao cần đưa service principal vào campaign?**

Vì máy có thể đọc/ghi resource hoặc quản trị production dù không có HR user; cần service owner, trust, scope và vòng đời riêng.

**11. JIT eligible quyền admin có đáng review nếu hiện tại chưa active không?**

Có. Eligibility tạo khả năng kích hoạt quyền sau này; cần review cả điều kiện activate, role, scope và active sessions.

**12. SCIM PATCH 204 có chứng minh quyền đã bị thu hồi khỏi mọi phiên không?**

Không. Cần readback role/Group và kiểm tra token/session hoặc authorization runtime trong phạm vi rủi ro.

**13. Nếu reviewer muốn gỡ quyền export nhưng vẫn giữ quyền read, nên quyết định gì?**

MODIFY/REDUCE theo scope, sau đó xác minh `report.export` không còn và `report.read` hợp lệ vẫn hoạt động.

**14. Vì sao tỷ lệ completion của reviewer và verified remediation là hai KPI khác nhau?**

Vì decision được ghi nhận không chứng minh connector đã thay đổi target; phải phân biệt quyết định với quyền thực tế đã hội tụ.

**15. Một User không có BucketReader nhưng có quyền sửa bucket policy có được coi là không có đặc quyền không?**

Không. Họ có thể có **đường escalation gián tiếp** để tự cấp quyền; cần review khả năng này.

**16. Exception hợp lệ cần những thông tin nào?**

Subject, action, resource, tenant, lý do, approver/owner, start/end, điều kiện security và bằng chứng audit.

**17. Khi hai tài khoản thuộc cùng người dùng, reviewer nên làm gì?**

Liên kết qua stable IAM identity nếu có bằng chứng, xét SoD theo người thực, nhưng vẫn giữ từng local account/access path để thu hồi đủ.

**18. Resource review có thể bảo đảm tuyệt đối không còn quyền nếu không có API effective-access không?**

Không. Phải công bố giới hạn nguồn và khả năng kiểm chứng, lưu trạng thái unverified/exception có owner thay vì khẳng định sạch quyền tuyệt đối.

## Ghi nhớ

- **Review theo resource** bắt đầu từ **tài nguyên** và rà soát **tất cả principals, grants, access paths và quyền có thể sử dụng**, không chỉ một danh sách User/Group.
- **Direct ACL, nested Group, role inheritance, resource policy, trust, sharing link, privileged access và workload identity** đều có thể tạo quyền; identity/resource phải được ánh xạ bằng ID và namespace đáng tin.
- **Reviewer phải có thẩm quyền trên đúng resource**, tuân thủ SoD, ownership, freshness và policy. **Retain, Revoke, Modify, Investigate, Exception** phải gắn với scope và bằng chứng.
- **Joiner** cần tránh mở quyền sớm; **Mover** phải rà soát quyền cũ và quyền mới; **Leaver** phải thu hồi theo lifecycle mà **không đợi** chiến dịch định kỳ; job/snapshot cũ không được tái cấp quyền.
- **IdP/SSO, SCIM, RBAC/ABAC/PBAC, PAM và Resource Server** cung cấp các lớp thông tin khác nhau. **Approved/reviewed không đồng nghĩa provisioned hoặc effective access đã thay đổi**.
- **Desired–observed–effective access**, snapshot đầy đủ, sourceVersion/effectiveAt, idempotent remediation, readback, kiểm thử an toàn và audit là nền tảng để chứng minh quyền khớp chính sách.
- **Không coi dữ liệu thiếu là quyền không tồn tại, không coi timeout là Retain, không coi một kết quả API thành công là đã thu hồi xong**. Chỉ báo VERIFIED cho những kết quả trong phạm vi thật sự được kiểm chứng, nhằm giảm quyền truy cập tồn dư suốt vòng đời IAM.
