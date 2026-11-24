# Access review evidence: xây dựng bằng chứng kiểm toán quyền truy cập đầy đủ, truy vết được và xác minh tại hệ thống đích

**Access review evidence (bằng chứng rà soát quyền truy cập)** là tập hợp dữ liệu, quyết định, dấu vết thao tác và kết quả kiểm chứng chứng minh rằng một chương trình **access review/access recertification** đã kiểm tra đúng các quyền trong phạm vi, bởi người có thẩm quyền, tại thời điểm xác định, và đã xử lý các quyền không còn hợp lệ theo chính sách. Bằng chứng phục vụ **kiểm toán nội bộ, điều tra sự cố, quản trị rủi ro và chứng minh hiệu quả kiểm soát**. Nó không đơn thuần là ảnh chụp dashboard ghi “100% completed”.

Ví dụ: một manager chọn **REVOKE** quyền `finance.export@tenant-A` cho nhân viên đã chuyển bộ phận. Hệ thống IGA lưu quyết định và gửi lệnh gỡ group qua SCIM. Để chứng minh quyền đã bị thu hồi, cần thêm **kết quả từ ứng dụng đích**, kiểm tra các **direct grants/ACL** còn tồn tại, khả năng token/session cũ vẫn được sử dụng và **thời điểm quyền hiệu dụng thực sự bị từ chối**. Một dòng `decision=REVOKE` là bằng chứng ra quyết định, **không tự là bằng chứng hoàn tất thu hồi**.

Bài thuộc chương **Identity audit**, đề mục **Access review evidence**, của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi mô-đun là **quản lý vòng đời danh tính theo Joiner–Mover–Leaver (JML)**, từ xác minh, tạo account, cấp quyền đến rà soát và thu hồi khi đổi vai trò hoặc rời tổ chức. Bằng chứng phải liên kết các lớp **HR/VMS, IAM/IGA, IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, PAM/PIM, ứng dụng đích và hệ thống kiểm toán** nhằm phát hiện và giảm **quyền truy cập tồn dư**.

**Thông điệp cốt lõi:** **Review complete ≠ remediation complete ≠ effective access verified**. Một bộ evidence đáng tin cần chứng minh **phạm vi đã rà soát, căn cứ quyết định, thẩm quyền người quyết định, thay đổi đã thực thi và quyền thực tế sau thay đổi**, đồng thời nêu rõ những **khoảng trống chưa kiểm chứng**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa access review evidence, phân biệt **evidence artifact, audit trail, review decision, remediation ticket, readback và control attestation**.
2. Xây dựng **chuỗi bằng chứng từ population → grant snapshot → reviewer → decision → remediation → target verification**.
3. Đánh giá **tính đầy đủ, chính xác, kịp thời, nguyên vẹn, truy vết được, đúng thẩm quyền và có thể tái kiểm** của evidence.
4. Thiết kế bằng chứng cho **identity–account–role–entitlement–resource**, bao gồm role kế thừa, direct ACL và các nguồn grant ngoài hệ thống IGA.
5. Phân biệt **snapshot tại thời điểm (as-of)** với quyền hiện hành, sự kiện phát sinh sau snapshot và những khoảng trễ đồng bộ.
6. Xác minh **reviewer eligibility, delegation, independence, SoD** và trách nhiệm của business/application/data owner.
7. Lưu quyết định **KEEP/REVOKE/MODIFY/ESCALATE/EXCEPTION** cùng lý do, mốc thời gian, chính sách và bằng chứng.
8. Biết khi nào **SCIM/connector success** chưa đủ, và cách dùng **target readback/negative tests** để kiểm quyền hiệu dụng.
9. Liên hệ evidence với **Joiner–Mover–Leaver, quyền đặc quyền, service/workload account, contractor và federated identity**.
10. Xây dựng **evidence package, audit query, chỉ số, runbook, kiểm thử và checklist** không làm lộ thông tin nhạy cảm.

## 2. Access review evidence là gì và không phải là gì?

Bằng chứng review là những ghi nhận có thể dùng để trả lời câu hỏi kiểm toán:

> “Vào thời điểm cần kiểm, ai có quyền gì, tại sao quyền đó nằm trong phạm vi, ai đã quyết định giữ hay thu hồi, dựa trên dữ liệu nào, và hệ thống hiện còn cho sử dụng quyền trái chính sách hay không?”

Các hiện vật thường gồm:

- **Population/scope record:** Danh sách account, chủ thể, tài nguyên và entitlement cần review, cùng tiêu chí lựa chọn.
- **Source snapshot:** Bản chụp quyền được lấy từ target/IdP/directory và mốc thời gian thu thập.
- **Ownership/reviewer mapping:** Ai có thẩm quyền rà soát quyền nào.
- **Decision record:** KEEP/REVOKE/MODIFY, actor, thời gian, lý do và policy.
- **Approval/delegation:** Thẩm quyền quyết định, ủy quyền và kiểm SoD.
- **Remediation instruction:** Lệnh thay đổi quyền, request ID, desired state.
- **Target acknowledgement:** Phản hồi connector/ứng dụng về thao tác đã nhận hoặc xử lý.
- **Readback/effective access verification:** Quyền gán và hành động thực tế sau thay đổi.
- **Exception record:** Rủi ro, owner, kiểm soát bù trừ, hạn xử lý và chấp thuận phù hợp.
- **Audit trail/integrity metadata:** Nguồn, phiên bản, timestamp, người thao tác và tính nguyên vẹn.
- **Closure attestation:** Kết luận kiểm tra dựa trên evidence thật, không chỉ cờ `completed`.

### 2.1. Những thứ chưa đủ nếu đứng một mình

| Hiện vật đơn lẻ | Có thể chứng minh | Chưa chứng minh |
|---|---|---|
| Screenshot “Campaign 100% complete” | Dashboard báo đã xử lý theo logic sản phẩm | Population đầy đủ, quyết định hợp lệ và quyền đã thu hồi |
| Reviewer bấm KEEP | Có hành động quyết định được lưu | Người quyết định đúng thẩm quyền và quyền thực sự cần thiết |
| Reviewer bấm REVOKE | Có ý định thu hồi | Target đã gỡ grant, token/session đã mất quyền |
| Ticket “Resolved” | Workflow quản lý ticket đã đóng | Resource Server thực sự trả DENY |
| SCIM response thành công | Connector nhận/xử lý request theo contract | Mọi direct ACL, local account, PAT và session đã thu hồi |
| Log `user.active=false` tại IdP | Trạng thái account ở một hệ thống | Ứng dụng độc lập hoặc JWT chưa hết hạn bị từ chối |
| Export CSV danh sách role | Một tập quyền được xuất | Đủ scope, đúng thời điểm và không bỏ quyền ngoài catalog |
| Chữ ký/timestamp trên báo cáo | Artifact có metadata xác minh nhất định | Nội dung nguồn đã chính xác và đầy đủ |
| Không có audit event | Không thấy event trong phạm vi log đã truy vấn | Không có truy cập thực tế, nhất là khi logging gap |

**Nguyên tắc kiểm toán:** Mỗi kết luận phải được nối với **bằng chứng cụ thể và giới hạn của bằng chứng đó**.

## 3. Access review, recertification, remediation và identity audit

**Access review** là hoạt động đánh giá các quyền đang tồn tại. **Access recertification** thường là việc xác nhận lại các quyền qua chiến dịch hoặc theo rủi ro. **Remediation** là thực hiện thay đổi cần thiết. **Identity audit** là hoạt động đánh giá và thu thập bằng chứng cho thấy các kiểm soát danh tính/quyền được thiết kế và vận hành đúng.

| Hoạt động | Câu hỏi chính | Loại evidence |
|---|---|---|
| **Access inventory** | Ai hiện có quyền gì? | Export, entitlement graph, assignment records |
| **Access review** | Quyền đó còn đúng mục đích? | Reviewer decision, justification, contextual data |
| **Recertification** | Quyền đã được chứng nhận lại theo chu kỳ/sự kiện? | Campaign scope, completeness, certification records |
| **Remediation** | Quyền cần gỡ/sửa đã được thực thi? | Provisioning task, target response, change record |
| **Verification** | Quyền thực tế tại target có phù hợp? | Readback, permission check, safe negative test |
| **Audit** | Có chứng minh được phạm vi, thẩm quyền, quy trình và kết quả? | Evidence package + chain of custody |

Không nên gom sáu việc thành một cột `status=done`. Hệ thống báo cáo tốt hiển thị **số item đã review, số item chờ remediation, số đã xác minh, số ngoại lệ còn mở** riêng.

## 4. Chuỗi bằng chứng từ quyền đến kết quả

~~~mermaid
flowchart TD
    A["HR/VMS + IdP/Directory + Target APIs<br/>Identity, account và entitlement"] --> B["Scope + population baseline<br/>SnapshotId + asOf + filters"]
    B --> C["Grant provenance + context<br/>RBAC, ABAC, ACL, role inheritance"]
    C --> D["Reviewer assignment<br/>Ownership + SoD + delegation"]
    D --> E["Decision record<br/>KEEP / REVOKE / MODIFY / ESCALATE"]
    E --> F{"Action cần thay<br/>effective access?"}
    F -->|Không: KEEP hợp lệ| G["Kiểm căn cứ và độ mới<br/>Decision closure evidence"]
    F -->|Có| H["Remediation task + desired state<br/>Owner, deadline, correlation"]
    H --> I["Connector / IdP / SCIM / Target<br/>Thay role, account, ACL, key"]
    I --> J["Target readback + safe negative test<br/>Token/session/direct grant nếu cần"]
    J --> K{"Effective state<br/>đạt policy?"}
    K -->|Có| L["Verified closure<br/>Immutable audit references"]
    K -->|Không / Unknown| M["Exception / escalation<br/>Owner + risk + next action"]
    M --> H
    G --> N["Audit evidence package<br/>Scope, decisions, gaps, integrity"]
    L --> N
    M --> N
~~~

**Lưu ý:** KEEP cũng có thể trở nên lỗi thời nếu sau review có **Mover, Leaver, role change hoặc incident**. Audit cần giữ thời điểm và phạm vi hiệu lực của quyết định, không coi KEEP là sự chấp thuận vĩnh viễn.

### 4.1. Liên kết phải có ID ổn định

Một chuỗi có thể dùng:

~~~text
campaignId=CAMP-Q4-2026
  -> populationSnapshotId=SNAP-2026-1201
  -> reviewItemId=RI-00921
  -> subjectId=P-2048
  -> targetAccountId=CRM-USER-8821
  -> entitlementId=customer.export@tenant-A
  -> grantSourceId=direct-acl-399
  -> reviewerAssignmentId=RA-731
  -> decisionId=DEC-1129
  -> remediationTaskId=REM-518
  -> targetChangeRequestId=CRM-REQ-991
  -> verificationId=VER-531
  -> auditPackageId=AUD-Q4-17
~~~

**Email, display name và group label không phải khóa định danh bất biến**. Có thể đổi tên hoặc bị tái sử dụng; nên dùng canonical ID ổn định và mapping có version.

## 5. Những thuộc tính quyết định chất lượng evidence

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ kiểm tra |
|---|---|---|
| **Completeness – Đầy đủ** | Có bao phủ mọi subject, target, grant trong scope? | Đối soát census với số account target |
| **Accuracy – Chính xác** | Dữ liệu có phản ánh quyền thực tế? | So source snapshot với target readback |
| **Timeliness – Kịp thời** | Dữ liệu, decision, remediation đúng mốc? | `asOf`, `decisionAt`, `effectiveAt` |
| **Integrity – Nguyên vẹn** | Artifact có bị sửa, ghi đè không kiểm soát? | Append-only/controlled version/hash |
| **Authenticity – Nguồn xác thực** | Ai hoặc hệ thống nào tạo record? | Actor/workload ID, source signature/context |
| **Traceability – Truy vết** | Từ kết luận có lần ngược về grant và decision? | Correlation IDs và version |
| **Authority – Đúng thẩm quyền** | Reviewer/approver có quyền quyết định mục đó? | Role assignment/SoD/delegation evidence |
| **Reproducibility – Có thể tái kiểm** | Có thể đối chiếu lại với input/policy ban đầu? | Snapshot, query/filter version |
| **Confidentiality – Bí mật** | Evidence có bị lộ thông tin quyền/secret? | Least-privilege access, masking, encryption |
| **Availability – Khả dụng** | Khi kiểm toán cần, có tìm được artifact? | Retention, backup, retrieval tests |
| **Consistency – Nhất quán** | Các hệ thống ghi nhận cùng một identity và thời gian? | Clock skew, schema/correlation checks |
| **Objectivity – Không tự chứng nhận** | Bằng chứng có nguồn độc lập khi cần? | Target readback thay vì chỉ ticket của người làm |

**Một file được ký và không bị sửa vẫn có thể sai** nếu nó được tạo từ danh sách thiếu 30% ứng dụng. **Tính toàn vẹn của vật chứa không bảo đảm tính đầy đủ và chính xác của dữ liệu nguồn.**

## 6. Population evidence: chứng minh đã rà soát đúng phạm vi

**Population** là tập subject/account/entitlement thuộc phạm vi một campaign hoặc một kiểm soát tại thời điểm xác định. Nếu population thiếu, mọi tỷ lệ “100% review complete” đều có thể gây hiểu nhầm.

Một định nghĩa scope cần trả lời:

1. Review những **application/target/resource** nào?
2. Những subject nào: **employee, contractor, guest, privileged persona, service account, workload**?
3. Quyền nào: role, group, **direct grant, nested role, ACL, API scope, PIM eligibility, active session**?
4. Có môi trường **prod/staging**, tenant và project cụ thể nào?
5. Quyền hiệu lực tại **thời điểm as-of** nào?
6. Dữ liệu được lấy từ nguồn nào, phiên bản connector nào?
7. Những account không match được canonical identity được xử lý ra sao?
8. Loại trừ item theo tiêu chí nào, ai phê duyệt, có evidence?
9. Có hệ thống không lấy được dữ liệu hoặc connector timeout?
10. Có account/quyền được tạo sau snapshot cần event-driven review bổ sung?

### 6.1. Mẫu scope mô tả

~~~yaml
# Mẫu evidence metadata, không phải schema chuẩn của một sản phẩm.
campaignId: CAMP-Q4-2026
scopeVersion: 3
populationAsOf: "2026-12-01T00:00:00Z"
targetSystems:
  - crm-production
  - finance-reporting
subjectKinds: [EMPLOYEE, CONTRACTOR, WORKLOAD]
entitlementTypes: [ROLE, GROUP, DIRECT_ACL, API_SCOPE]
includePrivilegedGrants: true
includeOrphanAccounts: true
excludedScope:
  - target: legacy-archive
    reason: connector-not-ready
    owner: risk-owner
    exceptionRef: EXC-102
sourceSnapshots:
  - snapshotRef: CRM-SNAP-55
    collectedAt: "2026-12-01T00:10:00Z"
  - snapshotRef: FIN-SNAP-88
    collectedAt: "2026-12-01T00:12:00Z"
~~~

**Đây là ví dụ học tập.** Việc có ngoại lệ loại trừ không biến phạm vi chưa được kiểm thành “đã hoàn tất”; báo cáo phải nêu **coverage gap và kế hoạch xử lý**.

### 6.2. Census và reconciliation

Một bài kiểm toán có thể đối soát:

~~~text
Target active accounts discovered: 1.200
Linked to canonical identity:     1.130
Workload accounts with owner:         50
Unresolved/orphan accounts:           20

1.130 + 50 + 20 = 1.200

Nếu campaign chỉ có 1.130 item:
  Không được báo 100% population reviewed.
  Cần giải thích 70 account còn lại:
  50 workload đã review theo quy trình nào?
  20 orphan ai chịu trách nhiệm điều tra?
~~~

Ví dụ này dùng số giả lập. **Một account có nhiều entitlements**, nên số item review thường **khác số account**; không áp công thức một account = một quyền nếu dữ liệu thực không như vậy.

## 7. Snapshot tại thời điểm và tính toàn vẹn theo thời gian

**Point-in-time snapshot** là bản ghi quyền ở mốc `asOf`. Nó cho phép người kiểm toán biết reviewer đã nhìn thấy **trạng thái nào khi quyết định**.

Cần phân biệt:

- `sourceEffectiveAt`: Khi quyền/engagement được hệ thống nguồn coi là có hiệu lực.
- `observedAt`: Khi connector/collector nhìn thấy dữ liệu.
- `snapshotCreatedAt`: Khi dữ liệu tổng hợp được chốt.
- `reviewAssignedAt`: Khi item được đưa cho reviewer.
- `decisionAt`: Khi quyết định được ghi nhận.
- `remediationRequestedAt` và `appliedAt`.
- `verificationObservedAt`: Khi target được kiểm tra lại.

~~~text
01/12 10:00   Snapshot: role=finance.export
01/12 14:00   IAM nhận event Mover, role cần gỡ
02/12 09:00   Reviewer xem snapshot 01/12
02/12 09:05   Reviewer bấm KEEP theo dữ liệu cũ
02/12 09:10   Mover policy quyết định REVOKE

Evidence bắt buộc:
  Chứng minh quyết định KEEP dựa trên snapshot cũ,
  và vì sao policy Mover/current authorization
  phải thắng kết luận không còn hợp lệ đó.
~~~

### 7.1. Không chỉnh snapshot cũ để “khớp hiện tại”

Nếu quyền thay đổi sau snapshot, hãy lưu **change event hoặc snapshot version mới**, không sửa trực tiếp record lịch sử. Sửa snapshot khiến không còn tái dựng được câu hỏi reviewer đã nhìn thấy dữ liệu nào.

### 7.2. Eventual consistency không phải mất quyền ngay

Một target cập nhật role lúc 10:00, directory replica hoặc token cache có thể hội tụ muộn. Evidence nên lưu **mốc thay đổi, thời điểm observation, nguồn đọc và mức độ chắc chắn**, thay vì gán tất cả timestamp là “đã thu hồi”.

## 8. Identity–account–entitlement lineage

Trong IAM, một người hoặc workload có thể sở hữu nhiều account, nhiều cách được gán quyền:

~~~text
Canonical subject: P-2048
  ├─ IdP account: idp-P-2048
  │    └─ Group: Sales-Editors
  │         └─ Application role: crm.editor@tenant-A
  ├─ CRM local account: crm-P-2048
  │    └─ Direct ACL: customer.export@tenant-A
  └─ Cloud account: cloud-P-2048
       └─ Eligible PIM: project.owner@project-Z
~~~

**Review chỉ group membership có thể bỏ sót direct ACL**, và **review active PIM grant có thể bỏ sót quyền eligible kích hoạt trong tương lai**.

### 8.1. Những cột lineage tối thiểu

| Dữ liệu | Câu hỏi |
|---|---|
| **Canonical subject** | Ai là chủ thể có thẩm quyền nguồn? |
| **Target account** | Account nào tại ứng dụng có quyền? |
| **Entitlement** | Hành động, resource, tenant, environment nào? |
| **Grant source** | Role, group, policy, direct ACL, delegation hay exception? |
| **Grant chain** | Qua những nhóm/role kế thừa nào? |
| **Grant owner** | Ai chịu trách nhiệm tài nguyên/quyền? |
| **Effective time** | Quyền có từ khi nào, đến khi nào? |
| **Credential/session exposure** | Có token/PAT/key/phiên liên quan? |
| **Review status** | Ai quyết định trên quyền nào? |
| **Current access** | API/target hiện chấp nhận hành động nào? |

### 8.2. Tránh kết luận chỉ dựa group name

Tên `APP-GRP-17` không cho reviewer biết liệu nhóm cấp quyền **đọc dữ liệu hay quản trị production**. Evidence cần **entitlement dictionary** hoặc mapping role→permission/resource được version hóa để reviewer đưa ra quyết định có căn cứ.

## 9. Assigned access và effective access là hai bằng chứng khác nhau

- **Assigned access:** Những role/entitlement được cấu hình cấp.
- **Effective access:** Những hành động target/Resource Server thực sự cho phép sau khi xét role, ACL, deny policy, attributes, token/session và context.

Ví dụ:

~~~text
IGA:
  desired entitlement = NONE

Directory:
  group Sales-Editors đã gỡ

CRM:
  direct ACL customer.export = ALLOW

Resource Server:
  token hiện hành + direct ACL => PERMIT

Kết luận:
  IGA desired state đúng, nhưng access chưa được thu hồi.
~~~

**Không tự đoán quyền hiệu dụng chỉ bằng cách cộng tên role.** RBAC, ABAC/PBAC, policy deny, tenant constraint và request context có thể làm quyền thực tế khác với quyền “trên giấy”.

### 9.1. Ba lớp dữ liệu cần giữ

1. **Desired:** Quyền theo JML/access policy hiện hành.
2. **Observed assigned:** Role/group/ACL từ hệ thống đích.
3. **Verified effective:** Kết quả quyền tại PEP/Resource Server trong phạm vi đã kiểm.

Nếu không kiểm được effective access, ghi **UNKNOWN/PENDING_VERIFICATION**, không tự chuyển thành PASS.

## 10. Chọn reviewer và chứng minh thẩm quyền

Reviewer phù hợp tùy quyền:

- **Line manager:** Biết nhân viên còn cần quyền cho nhiệm vụ không.
- **Application owner:** Hiểu semantics của app role/entitlement.
- **Data owner:** Đánh giá quyền trên dữ liệu nhạy cảm.
- **Privileged access owner:** Review cloud admin, directory admin, PIM/PAM.
- **Business sponsor:** Xác nhận contractor/guest/partner có engagement.
- **Technical/service owner:** Review service account/workload identity.
- **Independent risk/security approver:** Đánh giá ngoại lệ/SoD khi policy yêu cầu.

### 10.1. Evidence của reviewer assignment

Lưu:

- `reviewerId` ổn định và `reviewerKind/role`.
- Nguồn xác định reviewer: manager hierarchy, resource ownership, service catalog.
- `assignmentAt` và snapshot thẩm quyền.
- Phạm vi được phép review: app, resource, tenant, risk tier.
- Reviewer's own **JML/active status** tại thời điểm quyết định.
- Delegation: ai ủy quyền, cho ai, lúc nào, expiry và scope.
- SoD/independence check và kết quả.
- Lịch sử reassign và lý do.

### 10.2. Một người cấp cao không tự có thẩm quyền mọi thứ

CEO, IAM admin hoặc manager của reviewer không nhất thiết có quyền chứng nhận **toàn bộ dữ liệu và role production**. Escalation/ủy quyền cần kiểm **resource ownership, policy approval matrix và xung đột lợi ích**, không chỉ cấp bậc.

## 11. Separation of Duties và self-certification

**Separation of Duties (SoD)** giúp tránh trường hợp cùng một người tùy ý **xin quyền, tự cấp quyền, tự chứng nhận và tự xác minh thu hồi**.

Ví dụ:

~~~text
Person P-51:
  Requester của production.admin
  Người cấp role production.admin
  Reviewer xác nhận KEEP quyền của chính P-51
  Người sửa log chứng minh quyền hợp lệ

Kiểm toán:
  Có record nhưng independence rất yếu.
~~~

### 11.1. Bằng chứng SoD gồm gì?

- Ma trận role/requester/approver/reviewer/remediator.
- Policy version và điều kiện ngoại lệ.
- Kết quả kiểm xung đột tại thời điểm review.
- Nếu dùng delegate, evidence ủy quyền hợp lệ.
- Nếu có exception, risk owner và expiry rõ.
- Dấu vết xác minh độc lập từ target hoặc nhóm khác.

**Không cần thiết mọi người luôn phải là bốn cá nhân khác nhau**; mức SoD phải theo policy, độ nhạy quyền và khả năng vận hành. Nhưng nếu chính sách yêu cầu independent review, một checkbox tự chứng nhận **không thay kiểm soát độc lập**.

## 12. Decision evidence: ghi cả kết quả lẫn lý do

Một record quyết định đầy đủ thường cần:

| Field | Nội dung |
|---|---|
| `reviewItemId` | Item gắn tới snapshot và grant |
| `decisionId` | ID bất biến của hành động quyết định |
| `decisionType` | KEEP, REVOKE, MODIFY, ESCALATE, EXCEPTION |
| `decisionActorId` | Reviewer/delegate thực hiện |
| `decisionAt` | Thời điểm đáng tin |
| `decisionReason` | Nhu cầu hoặc rủi ro, không chỉ “OK” |
| `referenceEvidence` | Ticket, engagement, service catalog, policy |
| `entitlementScope` | Resource, action, tenant, environment |
| `sourceVersion` | Dữ liệu reviewer dùng |
| `authorityCheckRef` | Căn cứ reviewer được phép quyết định |
| `policyVersion` | Bộ quy tắc áp dụng |
| `decisionOutcome` | Thay đổi nào cần triển khai |

### 12.1. Các quyết định có nghĩa khác nhau

| Quyết định | Nội dung evidence bắt buộc | Bước sau |
|---|---|---|
| **KEEP** | Nhu cầu hiện hành, đúng owner/scope, reviewer hợp lệ | Ghi nhận; vẫn theo dõi JML và expiry |
| **REVOKE** | Vì sao không còn cần/không đủ điều kiện | Gỡ entitlement/credential và verify |
| **MODIFY** | Scope trước/sau, reason và approval | Áp scope mới, kiểm positive/negative |
| **ESCALATE** | Chưa thể quyết định, chuyển ai và vì sao | Owner mới, deadline và triage |
| **EXCEPTION** | Rủi ro, chấp thuận, TTL, bù trừ và remediation plan | Theo dõi expiry, chưa gọi verified fixed |
| **NEEDS_INFORMATION** | Dữ liệu thiếu, nguồn, owner sửa, deadline | Bổ sung evidence trước khi quyết định |

**Blank decision hoặc thiếu phản hồi không phải KEEP.** Nếu policy có auto-close hoặc rule quá hạn, phải ghi rõ **policy engine action** thay vì giả mạo một quyết định của reviewer.

### 12.2. Lý do quyết định phải có giá trị kiểm chứng

`Keep because manager approved` là một lý do yếu nếu reviewer không biết entitlement cấp quyền gì. Tốt hơn là nêu **tác vụ cần thiết, scope tài nguyên, engagement còn hiệu lực, giới hạn thời gian và policy liên quan**, không ghi dữ liệu cá nhân vượt nhu cầu.

## 13. Mẫu JSON review decision (minh họa)

~~~json
{
  "campaignId": "CAMP-Q4-2026",
  "populationSnapshotId": "SNAP-2026-1201",
  "reviewItemId": "RI-00921",
  "subject": {
    "canonicalId": "P-2048",
    "kind": "EMPLOYEE",
    "engagementRef": "ENG-288"
  },
  "target": {
    "applicationId": "crm-production",
    "accountRef": "CRM-USER-8821",
    "tenantId": "tenant-A"
  },
  "entitlement": {
    "action": "customer.export",
    "resourceScope": "tenant-A",
    "grantSourceRef": "direct-acl-399",
    "riskTier": "HIGH"
  },
  "reviewer": {
    "actorRef": "DATA-OWNER-12",
    "authorityCheckRef": "AUTHZ-REV-665",
    "delegationRef": null
  },
  "decision": {
    "type": "REVOKE",
    "decidedAt": "2026-12-08T09:30:00+07:00",
    "reasonCode": "NO_LONGER_REQUIRED_AFTER_MOVER",
    "justificationRef": "MOVER-ENG-288",
    "policyVersion": "review-policy-v3"
  },
  "remediation": {
    "taskRef": "REM-518",
    "status": "PENDING_TARGET_VERIFICATION"
  },
  "evidenceRefs": [
    "TARGET-SNAPSHOT-882",
    "OWNERSHIP-CATALOG-42"
  ]
}
~~~

**Đây là cấu trúc học tập**, không phải một hồ sơ người dùng thật hay schema bắt buộc. Không đưa mật khẩu, access/refresh token, private key hoặc bản sao dữ liệu khách hàng vào evidence JSON.

### 13.1. Reviewer action phải là một sự kiện

Nếu reviewer đổi quyết định từ KEEP sang REVOKE sau khi phát hiện Mover, cần lưu **hai event có timestamp, reason và supersession link**. Không ghi đè record cũ để làm như chỉ có một quyết định đúng ngay từ đầu.

## 14. Remediation evidence: từ decision tới lệnh thay đổi

Đối với REVOKE/MODIFY, evidence cần chỉ rõ:

1. **Desired state:** Quyền nào cần mất hoặc giảm scope.
2. **Source grant:** Role/group/ACL nào đang tạo quyền.
3. **Remediation owner:** Đội hoặc automation được phép sửa target.
4. **Change ID:** Ticket, workflow, connector request/correlation.
5. **RequestedAt/attemptedAt:** Khi nào gửi lệnh.
6. **Target response:** Thành công, lỗi, timeout, retry, partial success.
7. **AppliedAt:** Target xác nhận đã cập nhật theo semantics của API.
8. **ReadbackAt:** Mốc kiểm quyền đã thay đổi.
9. **Residual access:** Token, session, direct ACL, credential còn không.
10. **Exception:** Nếu chưa đạt, ai chịu rủi ro và deadline tiếp.

### 14.1. Đừng nhầm “đã gửi lệnh” với “đã áp dụng”

~~~text
Decision: REVOKE role=finance.admin
  -> IGA tạo task
  -> Connector gửi PATCH /Groups
  -> HTTP 202 Accepted
  -> Queue nhận công việc, chưa chắc target áp
  -> Target cập nhật group
  -> Access token cũ / direct role có thể còn
  -> Permission check thực tế -> DENY hay PERMIT?
~~~

**HTTP 202/200** phải được hiểu theo **contract endpoint cụ thể**. Không có status code chung nào tự bảo đảm mọi quyền hiệu dụng ở các hệ thống liên quan đã mất.

## 15. Target readback: bằng chứng quyền thực tế

**Readback** là truy vấn hoặc quan sát trạng thái sau thay đổi từ hệ thống đích, không chỉ đọc lại record IGA. Nó nên kiểm những nguồn grant có liên quan:

- Role assignment tại ứng dụng/cloud.
- Group membership và nested group/role inheritance.
- Direct ACL, local permission, share link nếu scope yêu cầu.
- PAM/PIM eligibility và active grants.
- Service account, API key/PAT, certificate và secret access.
- Session/token còn được Resource Server chấp nhận.
- ABAC/PBAC policy và thuộc tính có ảnh hưởng.
- Resource/tenant/environment thực tế, không chỉ role name.

### 15.1. Bốn trạng thái readback nên phân biệt

| Trạng thái | Ý nghĩa |
|---|---|
| **VERIFIED_DENIED** | Hành động cần thu hồi đã bị target từ chối trong phạm vi kiểm |
| **VERIFIED_ALLOWED** | Hành động vẫn được cho phép theo phép thử/truy vấn đáng tin |
| **UNKNOWN** | Không thể kết luận do thiếu dữ liệu, quyền kiểm tra hoặc lỗi target |
| **NOT_APPLICABLE** | Không có phép kiểm tương ứng theo scope được phê duyệt; cần reason |

**UNKNOWN không được tự đổi thành VERIFIED_DENIED.** Và một phép thử DENY trên **một endpoint** không tự chứng minh **mọi API/tenant/credential khác** bị chặn.

### 15.2. Negative test phải an toàn

Không thực hiện xóa dữ liệu hay export dữ liệu production chỉ để thử quyền. Có thể dùng:

- Authorization-check endpoint đáng tin của target.
- API read-only được thiết kế kiểm quyền thích hợp.
- Một phép thử DENY an toàn trong môi trường kiểm thử phù hợp.
- Permission graph/readback từ policy engine có dữ liệu cập nhật.
- Session/token status check nếu hệ thống hỗ trợ.

Lưu **expected outcome, observed outcome, scope, timestamp, account/credential context và phương pháp kiểm**. Nêu rõ giới hạn của phép kiểm.

## 16. Evidence cho access review trong Joiner lifecycle

Khi một người **Joiner**, HR/VMS cung cấp nguồn xác định identity, engagement, role ban đầu và mốc hiệu lực. Nếu review phát hiện quyền cấp ban đầu sai, evidence cần liên kết:

- `identityProofingRef` hoặc onboarding approval, không chép giấy tờ định danh.
- Canonical subject và engagement `effectiveAt`.
- Birthright role/permission catalog version.
- Request/approval cấp thêm quyền, resource owner.
- Account/role provisioning tasks và target readback.
- Review decision nếu được yêu cầu theo sự kiện/rủi ro.
- Token/session nào được phát trước mốc làm việc, nếu có.
- SoD/least privilege đối với account privileged ban đầu.

**Một account đã được tạo không chứng minh nó được phép truy cập production trước `effectiveAt`.** Bằng chứng phải nối **ngày bắt đầu hợp lệ** với chính sách cấp quyền và authorization thực tế.

## 17. Evidence cho Mover: quyền cũ có thật sự biến mất?

**Mover** thay đổi trách nhiệm, bộ phận, dự án hoặc địa điểm. Account có thể còn ACTIVE, nhưng **một phần quyền phải được gỡ**.

~~~mermaid
sequenceDiagram
    autonumber
    participant H as HR / VMS
    participant I as IAM / IGA
    participant R as Reviewer / Resource owner
    participant T as Target App / SCIM / API
    participant V as Verification / Audit

    H->>I: Mover event + effectiveAt
    I->>I: Compare old/new desired entitlements
    I->>R: Review affected old/new rights
    R-->>I: REVOKE export@tenant-A
    I->>T: Remove old group / direct ACL
    T-->>I: Connector outcome
    V->>T: Readback group, ACL, token effect
    T-->>V: Access denied/allowed/unknown
    V-->>I: Verified evidence or escalation
~~~

### 17.1. Bằng chứng cần có

1. Mover event từ nguồn được tin và mốc effective time.
2. Role/engagement trước và sau, scope nghiệp vụ hiện hành.
3. Quyền cũ được tìm thấy ở **IdP group, local ACL, direct grant và privileged eligibility**.
4. Reviewer có thẩm quyền xác nhận keep/revoke/modify.
5. Remediation, target change ID và kết quả.
6. Safe negative test cho action cũ và positive check phù hợp cho quyền mới.
7. Nếu có **hai engagement**, chứng minh thu hồi đúng quyền đã hết căn cứ, không phá quyền khác hợp lệ.

**Không đợi phiên hết idle timeout** rồi gọi là đã xử lý Mover nếu policy đòi từ chối hành động cũ sớm hơn.

## 18. Evidence cho Leaver: ưu tiên mốc chặn quyền

**Leaver** cần bằng chứng chặt về mốc **không còn đủ điều kiện** và đường truy cập còn tồn dư.

Ví dụ:

~~~text
HR/VMS effectiveAt: 2026-12-15 17:00 +07
IdP disableAt:      2026-12-15 17:00 +07
SCIM target update: 2026-12-15 17:02 +07
API JWT expiresAt:  2026-12-15 17:45 +07
Verified API deny:  2026-12-15 17:06 +07

Kết luận kiểm toán:
  Target API bị chặn lúc 17:06 trong phạm vi test,
  chưa được phép ghi "revoked exactly at 17:00"
  nếu chính sách yêu cầu chặn ngay tại effectiveAt.
~~~

### 18.1. Những đối tượng cần rà

- IdP account/session, SSO connections.
- Local application accounts không dùng SSO.
- Directory group và SCIM-provisioned assignments.
- Access token/refresh token, PAT/API key, SSH certificate/key.
- PAM/PIM eligible role, active privileged sessions.
- Cloud IAM, database ACL, shared resource permissions.
- External guest/contractor engagement và sponsor.
- Service credential mà Leaver từng biết hoặc được quyền quản lý.
- Quyền qua **multiple engagements** chưa kết thúc.

### 18.2. Không hợp thức hóa quyền tồn dư bằng deadline campaign

Một reviewer có thể còn ba ngày để quyết định trong chiến dịch quý, nhưng Leaver theo policy đòi chặn quyền tại `effectiveAt`. **Evidence không được dùng “campaign not due yet” như lý do hợp thức quyền đã mất căn cứ**.

### 18.3. Leaver completion cần scope rõ

Không nên nói “đã thu hồi 100%” nếu chưa bao phủ ứng dụng local, cloud tokens hoặc privileged sessions. Kết luận cần có **hệ thống đã xác minh, đường chưa kiểm, remediation owner và deadline**.

## 19. Bằng chứng quyền đặc quyền và các đường truy cập đặc biệt

**Privileged access** có thể gồm cloud admin, directory admin, database admin, CI/CD secret authority, PAM-managed accounts, PIM eligible roles và emergency access.

| Loại đặc quyền | Evidence cần có |
|---|---|
| **Standing admin** | Role assignment, purpose, owner, reviewer độc lập, expiry nếu có |
| **PIM eligible** | Eligibility hiện tại, activation conditions, review decision |
| **PIM active/JIT** | Activation start/end, approval, action logs, target role/session status |
| **PAM shared account** | Actor–checkout–session mapping, monitoring và hậu kiểm |
| **Break-glass** | Incident/ref, reason, actor verification, monitoring, credential cleanup |
| **Admin API key/PAT** | Principal, scope, issuance/rotation/revoke và target denial |
| **Cloud root/emergency account** | Quản trị credential, giới hạn người biết, kiểm tra hoạt động, hậu kiểm |

### 19.1. “Chưa dùng role” không đồng nghĩa “không có quyền”

Một người có thể chưa kích hoạt PIM eligible role trong nhiều tháng nhưng vẫn **có khả năng kích hoạt**. Evidence review phải kiểm **eligible assignment**, không chỉ active sessions hoặc last-used logs.

### 19.2. Quyền đặc biệt có nhiều lớp TTL

JIT activation hết hạn nhưng session database vẫn có quyền? Bằng chứng phải nối **activation expiry → target role/session enforcement → effective access**, không chỉ dựa vào đồng hồ PIM.

## 20. Bằng chứng cho service account và non-human identity

Một **non-human account (NHA)** không có line manager như người dùng. Reviewer phù hợp thường là **technical/service owner**, cùng data/resource owner khi NHA truy cập dữ liệu nhạy cảm.

Bằng chứng tối thiểu:

- Canonical workload/service ID, account/service principal ID tại target.
- Owner team, backup owner, business purpose và dependency.
- Environment, tenant, resource/action scope.
- Authentication method: managed identity, workload federation, certificate, client secret...
- Credential/key/token references và rotation/expiry status; **không có secret plaintext**.
- Deployment/job ID chứng minh workload còn được sử dụng hợp lệ.
- Privileged role, SoD và external API scopes.
- Review decision + approval và căn cứ business necessity.
- Remediation/deprovision steps khi workload retire.
- Target readback; quyền cũ không còn và automation không tự regrant.
- Nếu owner Mover/Leaver, evidence **ownership transfer** và human secret access cleanup.

### 20.1. Service account không owner không tự động là unused

Một workload `svc-monthly-recovery` có thể dùng hiếm nhưng cần thiết cho phục hồi. Ngược lại, một `svc-sync` chạy hàng ngày vẫn có thể giữ quyền `cloud.admin` không hợp lệ. Evidence phải dựa **purpose + risk + dependency + scope**, không chỉ `lastLogin`.

### 20.2. Leaver của owner khác retirement của workload

Người tạo service principal nghỉ việc không có nghĩa lập tức xóa principal đang phục vụ production. Cần **gỡ quyền quản lý của người, chuyển owner, đánh giá credential từng được biết và xử lý workload theo lifecycle riêng**, có audit và readback.


## 21. Contractor, guest và danh tính liên kết từ đối tác

**Contractor/guest/federated identity** thường có nguồn xác thực và quan hệ hợp đồng khác employee. Bằng chứng cần rõ **issuer, external subject, canonical mapping, sponsor, engagement và phạm vi target**, tránh suy ra “đăng nhập SSO thành công” tức là còn quyền công việc.

| Câu hỏi | Bằng chứng có thể cần |
|---|---|
| Ai là chủ thể thật? | Issuer + stable subject ID, guest ID và target account mapping |
| Vì sao có quyền? | Engagement/sponsor và yêu cầu truy cập được duyệt |
| Khi nào hết quyền? | Effective start/end, time-bound exception nếu có |
| Được truy cập ở đâu? | Application, tenant, project, resource/action |
| Ai review? | Business sponsor, application/data owner, authority evidence |
| Đã thu hồi chưa? | Local grant, SSO/session/token và target readback |

### 21.1. Một người có nhiều engagement

Nếu contractor kết thúc dự án A nhưng còn hợp đồng ở B, evidence cần **chứng minh quyền A bị thu hồi theo mốc hiệu lực** và không xóa nhầm quyền B hợp lệ. Không chỉ nhìn `user.active=true` hoặc `false` trên một IdP rồi coi mọi permission được giải thích.

### 21.2. Federation không thay authorization cục bộ

IdP đối tác có thể xác thực guest, nhưng ứng dụng phải kiểm **sponsor/engagement và resource policy**. Khi partner ngừng cung cấp user hoặc trust thay đổi, audit cần ghi **quyền local và token/session đã cấp**, không chỉ nguồn SSO.

## 22. Giới hạn bằng chứng từ IdP, Directory, SCIM và target

| Thành phần | Bằng chứng cung cấp | Chưa tự chứng minh |
|---|---|---|
| **HR/VMS** | JML event, engagement, manager, effectiveAt | App đã thu hồi local account |
| **IAM/IGA** | Scope, review items, decisions, desired state | Mọi target đã áp quyền |
| **IdP/SSO** | Account status, authentication, SSO session, groups | Mọi local ACL và bearer token bị thu hồi |
| **Directory/AD/LDAP** | Membership, account, nested groups, replication | Quyền cấp trực tiếp trong app ngoài directory |
| **SCIM** | Users/Groups updates, request/response | PAT, API key, direct grants và session tại target |
| **Authorization Server** | OAuth grants/token issuance/revocation | JWT đã phát bị Resource Server từ chối tức thời |
| **PAM/PIM** | Eligible/active privileged role, checkout/session | Target session đã chấm dứt |
| **Resource Server/PEP** | PERMIT/DENY cho action/resource/context cụ thể | Mọi đường truy cập chưa kiểm đã an toàn |
| **SIEM/audit store** | Event có timeline/correlation | Không có hành động trong khoảng mất log |

### 22.1. Ví dụ chuỗi có sai lệch

~~~text
HR: 17:00 Leaver effectiveAt
IdP: 17:00 Account disabled
IGA: 17:01 Desired state REVOKE
SCIM: 17:02 Request acknowledged
Target API: 17:05 customer.export vẫn PERMIT

Kết luận:
  Quy trình điều phối đã chạy,
  nhưng chưa có bằng chứng hoàn tất thu hồi
  vì effective access còn trái policy.
~~~

**Không gán `remediationComplete=true` chỉ dựa vào response của connector**, trừ khi contract và phép kiểm đúng phạm vi thực sự bảo đảm điều đó.

### 22.2. Các đồng hồ thời gian

Lưu `requestedAt`, `acknowledgedAt`, `appliedAt`, `observedAt`, `verifiedAt`, không dùng một timestamp chung cho mọi bước. Clock skew/queue delay/replication có thể khiến timeline sai nếu không rõ nguồn giờ.

## 23. Evidence cho RBAC, ABAC và PBAC

**RBAC** gán quyền qua role; **ABAC** dùng thuộc tính subject/resource/action/context; **PBAC** áp policy tổng quát. Evidence không thể chỉ là danh sách group/role.

Ví dụ logic policy:

~~~text
PERMIT invoice.export nếu:
  subject.kind = EMPLOYEE
  AND subject.department = FINANCE
  AND subject.status = ACTIVE
  AND resource.tenant = subject.allowedTenant
  AND action = invoice.export
  AND không có explicit deny

Nếu Mover đổi department:
  Cần event nguồn có thẩm quyền, policy version,
  attribute freshness, PEP decision và target readback.
~~~

Một account đã gỡ group `FinanceReaders` nhưng vẫn có direct grant `invoice.export` có thể tiếp tục dùng quyền.

### 23.1. Dữ liệu client tự khai không phải bằng chứng

`department=FINANCE` trong request body do client gửi không đủ tin. Bằng chứng thuộc tính phải đến từ **nguồn tin cậy hoặc identity claim đã được xác minh**, kèm độ mới và ranh giới tin cậy.

### 23.2. Policy thay đổi theo thời gian

Lưu policy/attribute snapshot reviewer đã dùng, đồng thời **đánh giá policy hiện hành** khi remediation/verification. Không sửa bản ghi lịch sử để làm như policy mới đã tồn tại từ trước.

### 23.3. Token có thể giữ claim cũ

JWT đã phát có thể giữ role cũ dù IAM cập nhật role. Audit cần kiểm **Resource Server có chặn theo thời điểm chính sách yêu cầu hay không**, không suy từ token `exp` hoặc group snapshot.

## 24. Ngoại lệ, quá hạn và tình trạng chưa xác minh

Một quyết định chưa thể khắc phục ngay cần **exception** có người chịu trách nhiệm, không được đóng giả.

| Trường | Ví dụ hoặc mục đích |
|---|---|
| `exceptionId` | EXC-2026-21 |
| `linkedReviewItemId` | Item và grant bị ảnh hưởng |
| `reasonCode` | Migration dependency, target outage... |
| `riskTier` | Mức rủi ro quyền còn tồn tại |
| `riskOwner` | Người phê duyệt ngoại lệ theo policy |
| `actionOwner` | Đội thực hiện remediation |
| `compensatingControls` | Hạn chế gateway/network, cảnh báo, monitoring |
| `expiryAt` | Khi ngoại lệ phải được xử lý/rà lại |
| `originalDueAt` | Hạn gốc, không ghi đè |
| `extendedDueAt` | Hạn được phép điều chỉnh |
| `verificationRequirement` | Điều kiện để đóng |
| `escalationRef` | Chuyển cấp khi quá hạn |

### 24.1. Ba loại quá hạn

1. **Decision overdue:** Người có thẩm quyền chưa đưa quyết định hợp lệ.
2. **Remediation overdue:** Quyết định REVOKE/MODIFY có rồi nhưng target chưa đạt desired state.
3. **Verification overdue:** Thao tác đã báo hoàn tất nhưng chưa có readback đúng scope.

**Gửi email cho reviewer không chữa được connector SCIM hỏng.** Khi remediation quá hạn, cần giao target/connector owner thực hiện cùng risk escalation.

### 24.2. Approved exception ≠ verified closure

Một ngoại lệ cho phép tạm thời chấp nhận rủi ro **không chứng minh quyền đã thu hồi**. Dashboard nên hiển thị `EXCEPTION_OPEN`, risk owner, expiry và next action riêng.

### 24.3. Deadline gia hạn không xóa lịch sử

Giữ `originalDueAt`, `extendedDueAt`, reason, approver và số lần gia hạn. Không dời lịch sử để làm tỷ lệ “on-time” đẹp hơn.

## 25. Evidence integrity và chain of custody

Evidence có giá trị khi có thể chứng minh **nguồn, thời gian, lịch sử thay đổi và ai đã truy cập**. Các cơ chế:

- **Append-only event history:** Không sửa quyết định cũ mà ghi event sửa/supersede.
- **Controlled versioning:** Snapshot, policy, entitlement dictionary, query và báo cáo có version.
- **Hash/digest:** Phát hiện file bị thay so với bản tham chiếu.
- **Signature khi phù hợp:** Hỗ trợ chứng minh artifact đến từ nguồn được tin và chưa bị sửa theo mô hình khóa.
- **Separated privileges:** Reviewer hoặc target admin không tùy tiện xóa evidence của chính mình.
- **Time synchronization:** Dấu thời gian từ nguồn tin cậy, đo clock skew.
- **Storage controls:** Encryption, backup, retrieval test, retention và legal hold nếu áp dụng.
- **Audit of evidence access:** Ai xem, xuất, chia sẻ, redaction hoặc xóa.
- **Independent source checks:** So IGA events với target audit và Resource Server.
- **Completeness proof:** Đối soát toàn bộ population và log gaps.

### 25.1. Hash không chứng minh nội dung đã đúng

Một CSV thiếu 200 direct grants vẫn có thể có SHA-256 hợp lệ. Hash hỗ trợ **bảo toàn tính nguyên vẹn sau thu thập**; cần **coverage, data quality, source trust và freshness** riêng.

### 25.2. “Immutable” phải có giới hạn thực tế

Một object storage đặt retention mode có thể có các quyền quản trị hoặc đường xóa khác nhau theo cấu hình. Không gọi evidence là “tamper-proof” tuyệt đối nếu chưa kiểm threat model và cơ chế bảo vệ.

### 25.3. Metadata custody tham khảo

~~~text
artifactId: EVID-288
sourceSystem: crm-audit-api
sourceAsOf: 2026-12-10T09:18:00Z
collectedAt: 2026-12-10T09:20:00Z
collectorIdentityRef: audit-collector-prod
queryRef/version: QRY-52/v4
hashAlgorithm: SHA-256
digestRef: HASH-208
transformationRef: MASK-2
custodianRef: audit-store-prod
retentionPolicyRef: RET-ACCESS-3
accessAuditRefs: [READ-721, EXPORT-81]
~~~

**Không cần đính kèm secret hay dữ liệu cá nhân thô để chứng minh provenance**. Các reference cần được truy xuất được qua kho lưu trữ có kiểm soát.

## 26. Privacy và quyền truy cập evidence

Một báo cáo review có thể tiết lộ **ai có admin**, ứng dụng production, dữ liệu khách hàng, trạng thái nhân sự và điểm yếu chưa khắc phục. Vì vậy:

1. **Least privilege:** Reviewer xem đúng item/resource họ được giao.
2. **Need-to-know:** Audit, risk, security nhận đúng phạm vi được phê duyệt.
3. **Minimization:** Dùng stable reference thay cho hồ sơ người đầy đủ.
4. **No secrets:** Không log password, access/refresh token, session ID raw, private key, OTP.
5. **Encryption:** Bảo vệ khi lưu/truyền và quản lý key phù hợp.
6. **Retention:** Theo chính sách và nghĩa vụ pháp luật cụ thể; không đặt thời hạn chung tùy tiện.
7. **Controlled exports:** Ghi ai tải hoặc chia sẻ báo cáo, giữ bản gốc khi redaction.
8. **Reassignment:** Thu hồi quyền xem item khỏi reviewer cũ khi không còn nhiệm vụ.
9. **Audit independence:** Người sửa target không tự kiểm soát mọi audit log của chính mình.
10. **Discovery:** Không cho phép tất cả nhân viên truy vấn toàn bộ entitlement graph chỉ vì đó là “dữ liệu kiểm toán”.

### 26.1. Khác biệt giữa redaction và sửa bằng chứng

Redaction phục vụ phiên bản chia sẻ là một **transformation có ghi lịch sử**. Không thay thế bản gốc trong kho cần bảo toàn mà không để lại provenance.

## 27. Mẫu JSON kết quả xác minh quyền

~~~json
{
  "verificationId": "VER-531",
  "reviewItemId": "RI-00921",
  "remediationTaskRef": "REM-518",
  "verifiedAt": "2026-12-08T10:25:00+07:00",
  "verifierRef": "IAM-VERIFY-SVC",
  "verificationPolicyVersion": "VERIFY-POL-v2",
  "subjectRef": "P-2048",
  "target": {
    "applicationId": "crm-production",
    "accountRef": "CRM-USER-8821",
    "tenantId": "tenant-A"
  },
  "desiredState": {
    "action": "customer.export",
    "shouldPermit": false
  },
  "checks": [
    {
      "kind": "TARGET_DIRECT_ACL_READBACK",
      "observedAt": "2026-12-08T10:24:52+07:00",
      "result": "GRANT_ABSENT",
      "sourceRef": "CRM-AUDIT-REF-711"
    },
    {
      "kind": "SAFE_AUTHORIZATION_CHECK",
      "observedAt": "2026-12-08T10:25:00+07:00",
      "result": "DENY",
      "sourceRef": "AUTHZ-CHECK-55"
    }
  ],
  "status": "VERIFIED_DENIED",
  "limitations": [
    "Independent long-lived tokens require a separate check"
  ],
  "evidenceDigestRef": "HASH-REF-208",
  "correlationId": "IAM-CORR-889"
}
~~~

Dữ liệu chỉ minh họa. **VERIFIED_DENIED chỉ áp dụng cho action/resource/tenant/context đã kiểm**; không suy rằng mọi đường truy cập khác cũng bị chặn khi chưa kiểm.

## 28. Evidence package manifest mẫu

~~~yaml
# Ví dụ học tập, không phải schema chuẩn của sản phẩm.
packageId: AUDIT-ACCESS-2026-Q4-17
controlId: ACCESS-RECERTIFICATION
campaignId: CAMP-Q4-2026
createdAt: "2026-12-20T08:00:00Z"
asOf: "2026-12-01T00:00:00Z"
scopeVersion: 3
population:
  snapshotRefs: [CRM-SNAP-55, FIN-SNAP-88]
  includedItemCount: 1290
  unresolvedAccounts: 20
  exclusions:
    - exceptionRef: EXC-102
review:
  decisionEventRefs: [DECISION-BATCH-11]
  reviewerAuthoritySnapshotRef: REVIEWER-SNAP-15
  sodCheckRef: SOD-CHECK-8
remediation:
  taskRefs: [REMEDIATION-BATCH-20]
  verificationBatchRefs: [VERIFY-BATCH-24]
exceptions:
  openRefs: [EXC-102, EXC-118]
integrity:
  manifestVersion: 1
  digestRef: HASH-REF-208
  provenanceRef: COLLECTOR-TRACE-90
retention:
  policyRef: RET-ACCESS-3
  protectedStoreRef: AUDIT-STORE-3
closure:
  result: PARTIALLY_VERIFIED
  unresolvedRiskOwnerRef: IAM-RISK-OWNER
~~~

Các số và ID giả lập. **PARTIALLY_VERIFIED** hữu ích khi minh bạch coverage gaps; tốt hơn báo “PASS 100%” dù còn account không owner hoặc item chưa có readback.

## 29. SQL minh họa đối soát quyết định và verification

Giả sử hệ thống phân tích có các bảng:

~~~text
review_item(item_id, campaign_id, snapshot_id,
            subject_id, target_id, entitlement_id, due_at)
decision(item_id, decision_type, reviewer_id,
         decided_at, authority_valid)
remediation(item_id, task_id, status, requested_at)
verification(item_id, status, observed_at)
~~~

Truy vấn minh họa tìm item **REVOKE/MODIFY chưa có verification đạt yêu cầu**:

~~~sql
-- SQL minh họa, cần điều chỉnh schema, event version,
-- policy và quyền truy vấn trước khi dùng thực tế.
SELECT
    r.campaign_id,
    r.item_id,
    r.subject_id,
    r.target_id,
    r.entitlement_id,
    d.decision_type,
    m.status AS remediation_status,
    v.status AS verification_status
FROM review_item AS r
JOIN decision AS d
  ON d.item_id = r.item_id
LEFT JOIN remediation AS m
  ON m.item_id = r.item_id
LEFT JOIN verification AS v
  ON v.item_id = r.item_id
WHERE r.campaign_id = 'CAMP-Q4-2026'
  AND d.decision_type IN ('REVOKE', 'MODIFY')
  AND (
      v.item_id IS NULL
      OR v.status NOT IN ('VERIFIED_DENIED', 'VERIFIED_DESIRED_SCOPE')
  );
~~~

**Giới hạn cực kỳ quan trọng:** Nếu một item có nhiều decision hoặc verification theo thời gian, join thô có thể tạo duplicate hoặc dùng kết quả cũ. Hệ thống audit thật phải xác định **current effective decision, supersession, verification mới nhất đúng scope, snapshot/version và target state**.

### 29.1. Phép đối soát population

~~~text
Entitlement edges phát hiện tại target theo asOf
  MINUS
Entitlement edges có review item trong campaign cùng asOf
  =
Candidate coverage gaps

Mỗi gap cần phân loại:
  Connector freshness?
  Exclusion đã duyệt?
  Direct grant ngoài catalog?
  Non-human/orphan account?
  Identity correlation sai?
~~~

**Không xóa các gap khỏi mẫu số** chỉ vì không giải thích ngay được.

## 30. Mã giả đánh giá bằng chứng một review item

Đoạn Python chỉ minh họa logic, không thay thế hệ thống kiểm toán thật:

~~~python
def classify_evidence(item, sources):
    # sources phải đáng tin và cung cấp source version/timestamp.
    population = sources.population_snapshot(item.snapshot_id)
    if population is None or not population.contains(item.item_id):
        return "POPULATION_EVIDENCE_MISSING"

    decision = sources.current_effective_decision(item.item_id)
    if decision is None:
        return "DECISION_MISSING"

    authority = sources.reviewer_authority(decision.reviewer_id,
                                            decision.decided_at)
    if not authority or not authority.valid_for(item):
        return "DECISION_AUTHORITY_UNVERIFIED"

    if not sources.is_consistent_with_current_jml(item, decision):
        return "STALE_OR_INVALID_DECISION"

    if decision.kind == "KEEP":
        if sources.keep_reason_is_sufficient(item, decision):
            return "DECISION_EVIDENCE_COMPLETE"
        return "KEEP_JUSTIFICATION_INSUFFICIENT"

    if decision.kind in ("REVOKE", "MODIFY"):
        remediation = sources.remediation(item.item_id)
        if remediation is None:
            return "REMEDIATION_EVIDENCE_MISSING"

        verification = sources.latest_scoped_verification(item.item_id)
        if verification is None:
            return "VERIFICATION_MISSING"
        if verification.status == "UNKNOWN":
            return "PENDING_TARGET_VERIFICATION"
        if verification.matches_desired_state:
            return "VERIFIED_CLOSED"
        return "RESIDUAL_ACCESS_REQUIRES_ESCALATION"

    if decision.kind in ("ESCALATE", "EXCEPTION"):
        return "OPEN_ACTION_OR_EXCEPTION"

    return "UNCLASSIFIED_DECISION"


# Production cần thêm: anti-tamper, supersession, SoD,
# grant-source completeness, concurrency/idempotency,
# target scope, time skew, authorization state,
# privacy/retention và exception policy.
~~~

**Nguyên tắc:** Nếu target/connector không phản hồi, không có chứng cứ không đồng nghĩa DENY. Ghi **UNKNOWN** và giao owner xử lý.

## 31. Metrics đo chất lượng evidence

| Chỉ số | Cách hiểu | Bẫy |
|---|---|---|
| **Population coverage** | Item review hợp lệ / quyền thuộc scope cùng as-of | Inventory thiếu khiến mẫu số nhỏ |
| **Identity correlation coverage** | Target account gắn đúng subject/owner | Unknown owner không phải out-of-scope |
| **Reviewer authority coverage** | Decision có evidence về thẩm quyền | Authenticated ≠ authorized reviewer |
| **Decision completion** | Item có decision hiện hành hợp lệ | Auto-KEEP không phải business validation |
| **Reason quality** | Decision có lý do, scope và căn cứ đủ | “OK” hàng loạt có giá trị thấp |
| **Decision timeliness** | Decision trước hạn theo policy | Gia hạn không xóa original due |
| **Remediation closure** | Target báo đã áp thay đổi cần thiết | Connector ACK chưa là effective DENY |
| **Verified closure** | Có readback đúng action/resource/context | Một phép test không bao phủ mọi path |
| **Residual access age** | Thời gian còn quyền trái policy | Phải lấy mốc JML effectiveAt nếu liên quan |
| **Privileged evidence coverage** | Standing/eligible/JIT role đủ dữ liệu | Chỉ active session dễ bỏ PIM eligible |
| **NHA ownership coverage** | Service accounts có owner/purpose | Last-used không tự chứng minh hợp lệ |
| **Exception aging** | Thời gian ngoại lệ chưa khắc phục | Approved exception không phải fixed |
| **Data quality gap rate** | Item thiếu snapshot/reviewer/verification | Tách unknown khỏi pass |
| **Evidence integrity coverage** | Artifact có provenance/version/digest | Digest không chứng minh completeness |
| **Regrant incidence** | Quyền đã revoke xuất hiện lại | Cần sửa IaC/directory source |
| **Audit retrieval success** | Evidence truy được theo retention | Link hỏng làm audit khó tái dựng |

### 31.1. Công thức minh họa

~~~text
DecisionCompletionRate =
  COUNT(items có current valid decision)
  / COUNT(items thuộc population và đã đến hạn)

VerifiedRemediationRate =
  COUNT(REVOKE/MODIFY items có target desired state verified)
  / COUNT(REVOKE/MODIFY items cần target change)

PopulationCoverage =
  COUNT(target entitlement edges có review item hợp lệ)
  / COUNT(target entitlement edges thuộc scope cùng asOf)
~~~

Cần công bố **mẫu số, as-of, exclusions và nguồn dữ liệu**. Đừng so kỳ này với kỳ khác chỉ bằng tỷ lệ nếu danh sách ứng dụng/entitlement đã khác.

## 32. Runbook thu thập evidence package

1. **Chốt scope/as-of:** Campaign ID, source systems, target, subject kinds, entitlement kinds.
2. **Lấy source snapshots:** HR/VMS, IdP/directory, IGA, cloud, app local, PAM/PIM, workload registry.
3. **Đối soát population:** Group/nested role, direct ACL, ownerless account, coverage gaps.
4. **Chuẩn hóa identity lineage:** Mapping subject/account/role/resource với stable IDs.
5. **Lấy reviewer authority:** Manager hierarchy, service/data owner, delegation và SoD.
6. **Lấy decision events:** Actor, reason, action, time, source/policy version.
7. **Tìm item thiếu quyết định:** Escalate theo risk, không auto-KEEP.
8. **Lấy remediation:** Desired state, request IDs, connector responses, partial failures.
9. **Xác minh target:** Readback, safe permission check, token/session nếu policy yêu cầu.
10. **Lấy exceptions/overdue:** Risk owner, bù trừ, deadline và escalation.
11. **Tạo manifest:** Artifact refs, digest/provenance/version, coverage limitations.
12. **Bảo vệ dữ liệu:** Redaction, access control, retention, không export credential.
13. **Peer review:** Kiểm mẫu ngẫu nhiên và các privileged/high-risk items.
14. **Bàn giao audit:** Có khả năng truy xuất nguồn cùng quyền truy cập được kiểm soát.

### 32.1. Nên lưu reference thay vì bản copy tràn lan

Một evidence package không cần chứa hàng triệu dòng log hay bí mật người dùng khi kho nguồn có kiểm soát có thể truy lại được. Tuy nhiên **reference phải còn khả dụng và có retention thích hợp** khi audit diễn ra.

## 33. Runbook xử lý mismatch: desired khác effective

~~~mermaid
flowchart TD
    A["Mismatch detected<br/>Desired != Observed/Effective"] --> B["Xác nhận đúng subject, target<br/>scope, asOf và policy"]
    B --> C{"JML/incident rủi ro cao<br/>cần chặn khẩn?"}
    C -->|Có| D["Security/Risk escalation<br/>Giảm quyền theo policy"]
    C -->|Không| E["Tìm grant provenance<br/>Group, role, ACL, token, session"]
    D --> E
    E --> F["Remediation owner tại target<br/>Sửa source + áp quyền"]
    F --> G["Target readback<br/>Safe negative/positive checks"]
    G --> H{"Effective access<br/>đạt desired state?"}
    H -->|Có| I["Verified closure + evidence"]
    H -->|Không/Unknown| J["Exception/owner/deadline<br/>Monitor + retry"]
    J --> F
~~~

Các bước:

1. Kiểm identity/account mapping và authorization state, tránh thao tác nhầm user.
2. Xác định grant source thực: role, group lồng nhau, direct ACL, attribute policy.
3. Kiểm connector job, response và timestamp.
4. Xác định token/session/local account có còn cho action.
5. Chuyển remediation tới owner có thẩm quyền; policy incident nếu cấp bách.
6. Áp thay đổi đúng scope, bảo vệ engagement khác vẫn hợp lệ.
7. Test readback, ghi `observedAt` và nguồn.
8. Theo dõi regrant từ directory/IaC/controller.
9. Giữ ngoại lệ khi chưa đạt; không đóng do ticket `Resolved`.

**Target outage ≠ authorization DENY.** Nếu API không phản hồi, trạng thái bằng chứng là **UNKNOWN**, không được gọi là VERIFIED_DENIED.

## 34. Kiểm thử chất lượng evidence pipeline

| Tình huống test | Kỳ vọng |
|---|---|
| Target có direct ACL ngoài IGA | Population reconciliation phát hiện gap |
| Nested group tạo quyền | Grant lineage thể hiện đường cấp |
| Reviewer Leaver trước decision | Decision authority invalid hoặc cần reassign |
| Reviewer tự KEEP privileged role trái SoD | Chặn hoặc yêu cầu independent review |
| Decision được sửa sau khi bấm KEEP | Lưu cả hai event và supersession |
| Mover sau snapshot nhưng trước decision | Detect stale context và re-evaluate |
| Leaver trước campaign due date | JML revoke ưu tiên, không chờ deadline |
| SCIM trả 202 nhưng target chưa áp | Không tự đổi thành verified |
| JWT cũ vẫn cho PERMIT sau revoke | Readback báo residual access |
| PIM eligible chưa active | Scope vẫn có eligible assignment |
| NHA không owner còn production role | Finding + assign owner/risk review |
| Một contractor có hai engagements | Thu hồi grant hết căn cứ, giữ phần hợp lệ |
| Connector không lấy được data một ngày | UNKNOWN/coverage gap, không pass |
| Snapshot CSV bị sửa sau export | Integrity check thất bại |
| Evidence log chứa raw token | Vi phạm bảo vệ credential, cần xử lý |
| Gia hạn dueAt thiếu approver | Audit policy validation failure |
| Negative test sai tenant/target | Không được tính là verified đúng scope |
| Readback PASS rồi quyền tái cấp | Reconciliation phát hiện regrant |
| Quyền cuối kỳ thay đổi trong lúc review | Giữ đúng as-of và change events |
| Hai collection sources lệch timezone | Hiển thị nguồn giờ và clock skew |
| Role semantics không rõ | Không ép reviewer KEEP khi thiếu dữ liệu |
| Service account recovery ít dùng | Không tự xóa vì last-login |
| Artifact có hash nhưng census thiếu | Evidence quality vẫn fail completeness |

**Kiểm thử schema JSON và checksum thôi chưa đủ**. Phải test logic population, authority, SoD, remediation và effective authorization.


## 35. Tình huống A — Campaign 100% nhưng bỏ sót direct ACL

**Bối cảnh:** Campaign CRM gồm 800 item, tất cả đã có decision. Dashboard báo 100%. Kiểm toán phát hiện 70 direct ACL cấp `customer.export` không được IGA import vì connector chỉ lấy group-based roles.

**Phân tích:**

- **Decision completion có thể đúng trong population 800 item**.
- Nhưng **population không đầy đủ**; coverage của toàn CRM chưa được chứng minh.
- Screenshot “100% complete” không giải thích 70 grants bỏ sót.

**Hướng xử lý:**

1. Đối chiếu entitlement census của CRM và danh sách IGA.
2. Bổ sung direct grants, role inheritance, source and target mapping.
3. Báo coverage gap, quyền high-risk và owner điều tra.
4. Giao data/application owner review 70 grants.
5. REVOKE/MODIFY quyền không hợp lệ và đọc lại target.
6. Cải thiện connector và quy tắc phát hiện grant ngoài catalog.
7. Lưu kết quả mới như **bổ sung có provenance**, không sửa lịch sử campaign cũ.

**Bài học:** **100% trong mẫu được chọn không đồng nghĩa 100% quyền thực tế được review.**

## 36. Tình huống B — Reviewer đã Leaver trước khi bấm KEEP

**Bối cảnh:** Reviewer được gán theo manager hierarchy đã nghỉ việc. Account workflow còn phiên đăng nhập hợp lệ và có decision KEEP cho `finance.admin` sau mốc Leaver.

**Rủi ro:** Record có actor, timestamp nhưng thẩm quyền **không còn hợp lệ**, thậm chí có thể có dấu hiệu account/session trái policy.

**Hướng xử lý:**

1. Kiểm HR/VMS status tại `decisionAt`.
2. Đánh dấu decision `AUTHORITY_UNVERIFIED`, không auto-certify.
3. Bảo vệ log và xem lại việc deprovision reviewer.
4. Reassign cho reviewer độc lập có thẩm quyền.
5. Review lại quyền privileged theo policy và business need.
6. Xử lý phiên và account của reviewer Leaver.
7. Giữ event cũ cùng correction/supersession, không xóa dấu vết.

**Bài học:** **Authenticated actor chưa chắc là authorized reviewer**.

## 37. Tình huống C — REVOKE đã duyệt nhưng JWT vẫn cho export

**Bối cảnh:** Data owner quyết định REVOKE `customer.export@tenant-A`. IGA gỡ group qua SCIM, dashboard báo remediation “Success”, nhưng CRM có direct ACL và access token JWT còn hạn. API vẫn PERMIT export.

**Hướng xử lý:**

- Giữ decision REVOKE và request ID làm bằng chứng đã ra lệnh.
- Phân loại remediation **PARTIAL/NOT_VERIFIED**.
- Truy lineage: directory group, direct ACL, local account, token/session.
- Gỡ grant ngoài căn cứ và xử lý token hiệu dụng theo policy.
- Kiểm Resource Server bằng safe DENY check trên đúng tenant/action.
- Ghi timeline: `effectiveAt`, `SCIM appliedAt`, `verifiedAt`.
- Nếu chưa chặn được, giữ exception/risk owner/mitigation.

**Bài học:** **Success của một connector không chứng minh mọi đường tới target đã bị khóa.**

## 38. Tình huống D — NHA mồ côi có quyền production

**Bối cảnh:** `svc-payments-recovery` ít dùng nhưng có `vault.secret.admin`. Người tạo đã Leaver; nhóm chưa tìm được owner mới. Review item bị KEEP do “recovery job phải luôn chạy”.

**Hướng xử lý:**

1. Xác định workload có còn hợp lệ từ deployment, runbook và thử nghiệm DR.
2. Giao technical owner và risk/data owner có thẩm quyền.
3. Đánh giá quyền tối thiểu cần cho recovery.
4. Kiểm credential đã được nhân viên nghỉ việc biết và rotation plan.
5. Hạn chế scope, JIT và monitoring khi phù hợp.
6. Lưu decision cùng căn cứ, expiry/review trigger.
7. Nếu service retire, deprovision có kiểm dependency và readback.
8. Không xóa chỉ vì hiếm dùng, cũng không giữ đặc quyền vô thời hạn.

**Bài học:** Evidence của NHA cần **service purpose, owner và credential lifecycle**, không chỉ last-login.

## 39. Tình huống E — Ngoại lệ quá hạn nhưng được đánh dấu Closed

**Bối cảnh:** Cloud owner role cần gỡ nhưng hệ thống phụ thuộc migration. Security cho ngoại lệ 7 ngày. Sau 30 ngày role vẫn còn; campaign tự hiển thị Completed vì exception đã approved.

**Hướng xử lý:**

- Phân biệt `APPROVED_EXCEPTION` và `VERIFIED_CLOSED`.
- Đọc originalDueAt, expiry và lịch sử gia hạn.
- Escalate risk owner khi ngoại lệ hết hạn.
- Xác minh biện pháp bù trừ còn hiệu quả không.
- Lập kế hoạch giảm quyền/thu hồi role và kiểm target.
- Theo dõi PIM eligibility, cloud sessions và secret access.
- Báo tuổi rủi ro tồn dư trong audit package.

**Bài học:** **Risk acceptance có thời hạn không tự là bằng chứng remediation đã hoàn tất.**

## 40. Tình huống F — Snapshot cũ dẫn đến KEEP sai sau Mover

**Bối cảnh:** Snapshot được chốt 01/12. User Mover khỏi Sales ngày 02/12. Reviewer dùng snapshot cũ quyết định KEEP `sales.export` ngày 05/12; policy Mover yêu cầu gỡ quyền từ 02/12.

**Hướng xử lý:**

1. Bảo toàn snapshot 01/12 và decision 05/12.
2. Đối chiếu event Mover và effectiveAt 02/12.
3. Gắn finding `STALE_DECISION` hoặc supersession.
4. Revoke scope Sales còn tồn dư; kiểm group/direct ACL/token.
5. Readback API cho DENY theo target tenant.
6. Cải tiến event-driven review và reviewer routing.
7. Không sửa snapshot cũ thành trạng thái hiện tại.

**Bài học:** **Evidence lịch sử cần giữ nguyên, nhưng current JML policy có thể làm quyết định cũ không còn hợp lệ.**

## 41. Tình huống G — Có hash nhưng log chưa đầy đủ

**Bối cảnh:** Audit nhận CSV có SHA-256 và 500 dòng action. Tuy nhiên source collector mất dữ liệu hai ngày; target admin có quyền sửa database tạo ra CSV và có thể tạo lại hash.

**Hướng xử lý:**

- Kiểm collector health, coverage gap và clock/source details.
- Phân biệt “không có event được quan sát” với “không có action”.
- Đối chiếu nguồn độc lập: IGA, target/API logs, change records, SIEM.
- Tăng bảo vệ append-only/independent audit phù hợp threat model.
- Kiểm entropy? Không: vấn đề chính là **source completeness và provenance**.
- Kiểm account/entitlement bị ảnh hưởng trong khoảng mất log.
- Báo finding và mức độ chắc chắn của bằng chứng, không tự điền event.

**Bài học:** **File có hash hợp lệ vẫn có thể chứa dữ liệu thiếu hoặc không đáng tin.**

## 42. Tình huống H — Quyền đã gỡ nhưng bị tự tái cấp

**Bối cảnh:** Reviewer REVOKE `project.editor` và target readback cho DENY. Đêm hôm sau, sync directory hoặc IaC controller tạo lại role assignment cũ.

**Hướng xử lý:**

1. Gắn regrant event với review item cũ và quyền phát sinh.
2. Xác định source-of-truth thực tế cấp role.
3. Sửa group mapping, deployment policy hoặc IaC source.
4. Thu hồi lại permission và kiểm scope tại target.
5. Giám sát/reconcile để phát hiện tiếp nếu quyền tái xuất hiện.
6. Ghi rõ readback trước đó **đúng tại thời điểm kiểm**, không bảo đảm vĩnh viễn.
7. Đánh giá SLA và control design tránh regrant sau Leaver/Mover.

**Bài học:** **Verified closure tại một thời điểm cần kiểm soát nguồn tái cấp và theo dõi phù hợp rủi ro.**

## 43. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao screenshot “100% reviewed” không đủ chứng minh access review hiệu quả?

**Gợi ý:** Cần kiểm population, authority, decision, remediation và target effective access.

**Câu 2.** KEEP có cần justification không?

**Gợi ý:** Có. Cần nhu cầu hiện tại, scope, owner, policy và mốc review phù hợp.

**Câu 3.** REVOKE decision khác `VERIFIED_DENIED` như thế nào?

**Gợi ý:** REVOKE là quyết định; VERIFIED_DENIED là bằng chứng target từ chối quyền trong scope đã kiểm.

**Câu 4.** SCIM trả 200/202 có tự chứng minh mọi token/local ACL bị vô hiệu không?

**Gợi ý:** Không; phụ thuộc contract và cần readback/resource check.

**Câu 5.** Vì sao cần `asOf` trong population snapshot?

**Gợi ý:** Phân biệt trạng thái quyền lúc thu thập với thay đổi xảy ra sau đó.

**Câu 6.** Reviewer là manager nhưng đã Leaver khi ra quyết định, có thể tự công nhận KEEP không?

**Gợi ý:** Không; cần thẩm quyền tại decisionAt và điều tra account/session.

**Câu 7.** Vì sao một service account cần technical owner trong bằng chứng?

**Gợi ý:** Để có trách nhiệm về mục đích, quyền, credential, dependency và lifecycle.

**Câu 8.** SHA-256 của CSV có chứng minh export đầy đủ quyền trong target không?

**Gợi ý:** Không; chỉ hỗ trợ integrity của artifact, không chứng minh completeness/accuracy.

**Câu 9.** Target bị timeout khi readback, có được ghi quyền đã bị chặn không?

**Gợi ý:** Không. UNKNOWN/PENDING_VERIFICATION với owner và risk.

**Câu 10.** Vì sao cần review direct ACL khi đã gỡ role group?

**Gợi ý:** Direct grants có thể tiếp tục cho effective access.

**Câu 11.** Contractor hết hợp đồng A nhưng còn B; evidence cần thể hiện gì?

**Gợi ý:** Quyền A bị chặn, B được giữ nếu hợp lệ theo policy.

**Câu 12.** PIM eligible chưa từng active có nằm trong review scope không?

**Gợi ý:** Có thể có, vì khả năng kích hoạt đặc quyền vẫn tồn tại.

**Câu 13.** Approved exception có được coi VERIFIED_CLOSED không?

**Gợi ý:** Không; còn rủi ro và kế hoạch/expiry xử lý riêng.

**Câu 14.** Vì sao không ghi đè quyết định KEEP khi reviewer đổi sang REVOKE?

**Gợi ý:** Audit cần timeline, supersession, actor và lý do của từng event.

**Câu 15.** Leaver lúc 17:00, phép test DENY lúc 17:06. Có thể khẳng định quyền mất đúng 17:00 không?

**Gợi ý:** Không chỉ dựa vào phép test đó; cần ghi đúng thời điểm quan sát và giới hạn chứng minh.

**Câu 16.** Tại sao cần kiểm regrant sau khi role đã thu hồi?

**Gợi ý:** Directory sync/IaC automation có thể tái cấp, làm quyền tồn dư trở lại.

**Câu 17.** Thiếu hai ngày audit log có thể kết luận không có hành động bất thường trong hai ngày đó không?

**Gợi ý:** Không. Absence of evidence khác evidence of absence.

**Câu 18.** Vì sao reviewer cần biết semantics của `APP-GRP-17`?

**Gợi ý:** Phải biết role cho phép action trên resource nào mới có thể quyết định KEEP/REVOKE có căn cứ.

## 44. Checklist triển khai Access review evidence

- [ ] **Scope:** Campaign/control có application, tenant, resource, environment, subject kinds, asOf?
- [ ] **Population:** Entitlement census bao gồm role, group lồng nhau, direct ACL, cloud grants và target accounts?
- [ ] **Coverage gaps:** Hệ thống bỏ sót, unknown owner và connector lỗi được nêu rõ?
- [ ] **Identity mapping:** Canonical subject ↔ target account ↔ grant có ID ổn định?
- [ ] **Snapshot:** Có collectedAt, observedAt, asOf, query/filter version, source reference?
- [ ] **Entitlement semantics:** Reviewer hiểu role cho quyền gì, trên resource nào?
- [ ] **Assigned/effective:** Báo cáo tách assigned access và effective permission?
- [ ] **Reviewer:** Có authority theo manager/resource/service owner tại decisionAt?
- [ ] **Delegation:** Có ai ủy quyền, scope, expiry và history?
- [ ] **SoD:** Có kiểm reviewer tự chứng nhận quyền của mình và exception cần thiết?
- [ ] **Decision:** KEEP/REVOKE/MODIFY/ESCALATE/EXCEPTION có actor, time, reason, policy?
- [ ] **Event history:** Decision bị sửa có supersession, không ghi đè?
- [ ] **KEEP:** Có business necessity và scope hợp lệ, không auto-KEEP do thiếu phản hồi?
- [ ] **Remediation:** Có desired state, owner, target change/request IDs?
- [ ] **Connector:** Phân biệt request/ack/applied, partial failure và retry?
- [ ] **Readback:** Kiểm action/resource/tenant tại target, không chỉ IGA desired state?
- [ ] **Unknown:** Không coi lỗi target hoặc thiếu log là DENY?
- [ ] **Token/session:** Kiểm JWT/refresh token/PAT/local session theo scope policy?
- [ ] **IdP/SSO/SCIM:** Không coi disable/group removal là full deprovision tự động?
- [ ] **RBAC/ABAC/PBAC:** Có policy, attribute freshness và PEP enforcement evidence?
- [ ] **Joiner:** Role cấp ban đầu đúng effectiveAt và approval?
- [ ] **Mover:** Quyền cũ bị chặn, quyền engagement khác không bị phá?
- [ ] **Leaver:** Thu hồi theo mốc HR/VMS, không chờ campaign deadline?
- [ ] **Contractor/guest:** Sponsor/engagement và federation mapping đúng?
- [ ] **Privileged:** Standing/JIT/PIM eligible/PAM/emergency grants đều được xem?
- [ ] **Non-human:** Workload có technical owner, credential reference và lifecycle riêng?
- [ ] **Exceptions:** Có risk owner, approval, expiry, bù trừ và escalation?
- [ ] **Overdue:** Phân biệt decision, remediation và verification overdue?
- [ ] **Regrant:** Theo dõi IaC/directory/automation tái cấp quyền?
- [ ] **Integrity:** Có append-only/versioning/digest/provenance phù hợp?
- [ ] **Chain of custody:** Ghi ai thu, truy cập, export, transform evidence?
- [ ] **Privacy:** Không lưu password/token/private key hoặc PII vượt nhu cầu?
- [ ] **Audit package:** Có manifest, scope, coverage, limitation, closure status?
- [ ] **Metrics:** Tách decision completion, verified closure và residual access age?
- [ ] **Validation:** Có test thiếu population, reviewer sai, stale snapshot, connector fail, target PERMIT?
- [ ] **Independent evidence:** Có peer review hoặc nguồn target độc lập theo risk?
- [ ] **Reporting:** Không ghi “100% revoked” nếu vẫn có unknown/excluded scope?
- [ ] **Kết quả cuối:** Có thể lần từ population tới decision, target change, readback và risk chưa đóng?

## 45. Kết luận

**Access review evidence** là chuỗi bằng chứng có thể kiểm tra độc lập chứng minh một đợt rà soát quyền đã **xác định đúng population, sử dụng dữ liệu đủ tin cậy, giao đúng reviewer, lưu decision có căn cứ và xử lý thay đổi quyền tại target**. Bằng chứng cần bao gồm **snapshot, identity/account/entitlement lineage, reviewer authority và SoD, decision event, remediation, target readback, exceptions, provenance, integrity và audit trail**.

**Không đồng nhất review complete, remediation complete và verified effective access.** Một campaign báo đầy đủ quyết định vẫn có thể bỏ sót direct ACL, quyền đặc quyền/PIM eligible, tài khoản dịch vụ không owner, session/token còn sống hoặc quyền tái cấp từ IaC. Cần công bố rõ **giới hạn coverage và các item chưa xác minh**, với owner, rủi ro và hạn xử lý.

Trong vòng đời **Joiner–Mover–Leaver**, bằng chứng phải nối **HR/VMS events** với **IAM/IGA desired state, IdP/SSO, SCIM, RBAC/ABAC, PAM/PIM, non-human account và enforcement thực tế tại Resource Server/target**. Khi quyền mất căn cứ do thay vai trò, kết thúc engagement hoặc quyết định review, việc thu hồi chỉ được coi là **đã xác minh** trong phạm vi cụ thể khi quyền không còn được chấp nhận theo policy và có evidence hỗ trợ.

**Một hồ sơ Access review evidence tốt không chỉ trả lời “ai đã duyệt”, mà còn trả lời được “đã rà soát quyền nào, vì sao quyết định hợp lệ, điều gì đã xảy ra tại target và rủi ro nào vẫn còn mở”.**
