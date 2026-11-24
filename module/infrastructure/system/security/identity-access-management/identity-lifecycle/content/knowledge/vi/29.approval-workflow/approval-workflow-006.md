# Multi-level approval trong IAM: phê duyệt nhiều cấp an toàn trước khi cấp quyền

**Multi-level approval** (phê duyệt nhiều cấp) là quy trình trong đó **một yêu cầu cấp hoặc thay đổi quyền truy cập** phải được nhiều chủ thể **có thẩm quyền** xem xét theo thứ tự, song song hoặc theo một quy tắc kết hợp đã được phê duyệt. Mỗi cấp có trách nhiệm khác nhau: **xác nhận nhu cầu công việc, quyền đối với ứng dụng/tài nguyên, phân tách nhiệm vụ (SoD), mức rủi ro, phạm vi và thời gian sử dụng**. Quyền chỉ được cấp khi *tất cả điều kiện phê duyệt bắt buộc* cho yêu cầu đó đã hoàn tất và yêu cầu vẫn hợp lệ tại thời điểm provision.

Ví dụ, nhân viên Lan xin quyền `ProductionOperator` trên cụm sản xuất. Manager xác nhận công việc, resource owner xác nhận cụm và thao tác được phép, Security đánh giá đặc quyền, SoD và chính sách xác thực. Một lần bấm `Approve` của manager **không** thay thế hai quyết định còn lại. Khi đủ approval, hệ thống vẫn phải kiểm tra Lan **còn active**, chưa chuyển vai trò hoặc rời tổ chức, role không xung đột; sau đó mới dùng SCIM/API/PAM cấp quyền và **readback** tại target.

Bài nằm trong chương **Approval workflow** của module quản lý vòng đời danh tính **Identity and Access Management (IAM)** theo **Joiner–Mover–Leaver (JML)**. Nội dung liên kết **HRIS, IdP, SSO, SCIM, RBAC/ABAC, PAM, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**. Mục tiêu là phân biệt những kiểu approval, xây định tuyến đáng tin, chặn tự phê duyệt, quản lý timeout/delegation và bảo đảm **Approved ≠ Provisioned ≠ Verified**.

> **Nguyên tắc:** Phê duyệt là **một quyết định quản trị về yêu cầu cụ thể**, không phải bằng chứng đã cấp quyền hoặc đã thực thi quyền đúng. Cũng không được bắt việc **thu hồi quyền hết căn cứ do Mover/Leaver** phải đợi một yêu cầu cấp quyền mới được phê duyệt.

## 1. Vì sao cần phê duyệt nhiều cấp?

Một người thường không nắm đủ thông tin cho mọi góc độ của một quyết định IAM. Manager hiểu nhiệm vụ của nhân viên nhưng không nhất thiết hiểu permission kỹ thuật; application owner biết scope tài nguyên nhưng không quản lý HR status; Security có thẩm quyền đánh giá privilege risk, nhưng không nên tự xác nhận business need cho một dự án.

| Người/cấp | Trách nhiệm chính | Bằng chứng điển hình |
| --- | --- | --- |
| **Line manager / sponsor** | Có nhu cầu công việc hợp lệ không? | HR assignment, project, contractor sponsor. |
| **Application/resource owner** | Role, action, tenant và resource scope này có phù hợp? | Role catalog, application/resource ID. |
| **Data owner** | Có được xem dữ liệu nhạy cảm hoặc xuất dữ liệu cụ thể? | Classification, purpose, retention và phạm vi. |
| **Security / IAM governance** | Least privilege, SoD, MFA, privilege escalation có đạt policy? | Entitlement inventory, role hierarchy, risk rules. |
| **PAM/production approver** | Có nên activate quyền admin trên resource/ticket trong một khoảng ngắn? | Incident/change ticket, JIT scope và thời gian. |
| **Compliance/risk reviewer** | Yêu cầu có cần kiểm soát riêng theo quy định tổ chức? | Risk assessment, exception approval. |

**Nhiều cấp không có nghĩa nhiều click một cách hình thức.** Một baseline access được định nghĩa và phê duyệt qua chính sách có thể **auto-provision** khi Joiner đủ điều kiện. Ngược lại, quyền admin toàn tenant hoặc quyền dữ liệu hạn chế có thể cần cả manager, owner và Security với các thẩm quyền độc lập.

### 1.1. Authority khác chức danh

Một Director không mặc nhiên được phê duyệt GlobalAdmin cho hệ thống khác đơn vị. Một application owner có thể phê duyệt app A, không phải app B. Quyền phê duyệt phải gắn **role/resource/tenant/effective time**, có owner và bằng chứng.

### 1.2. Quyết định duyệt, việc ghi quyền và quyền hiệu lực

~~~text
Trường hợp A:
Approval: FINAL_APPROVED
Provisioning: FAILED
Target User/Group: CHƯA CÓ
Actual access: DENIED

Trường hợp B:
Approval: REJECTED
Existing direct grant: VẪN CÒN
Local session: ACTIVE
Actual access: CÓ THỂ VẪN ĐƯỢC CHO PHÉP
~~~

Trường hợp B không phải lý do để bỏ qua approval: nó cho thấy **target entitlement drift**, cần điều tra và thu hồi độc lập. Workflow cần có **approval status, provisioning status và verification status** riêng.

## 2. Dữ liệu đầu vào của một yêu cầu

Yêu cầu có thể do người hưởng quyền, manager hoặc automation gửi; dữ liệu phải đủ để phê duyệt **đúng đối tượng** và kiểm tra lại trước khi cấp.

| Trường | Ý nghĩa |
| --- | --- |
| `requestId`, `version` | Định danh và phiên bản bất biến của yêu cầu. |
| `requesterIdentityId` | Ai gửi request. |
| `beneficiaryIdentityId` | Ai thực sự sẽ nhận quyền, có thể khác requester. |
| `targetApplication`, `tenant`, `resourceRef` | Hệ thống và tài nguyên bị ảnh hưởng. |
| `role/permission/action` | Quyền được yêu cầu, không chỉ tên hiển thị. |
| `businessJustification`, `ticketRef` | Vì sao cần, nhiệm vụ nào được phê duyệt. |
| `validFrom`, `validUntil` | Khung hiệu lực; đặc quyền nên có hạn khi phù hợp. |
| `riskClassification`, `dataClassification` | Căn cứ chọn route và kiểm soát bổ sung. |
| `approverRoute`, `policyVersion` | Những cấp và điều kiện tổng hợp. |
| `HR/JML event` | Quan hệ công việc và mốc hiệu lực. |
| `provisioning/verification refs` | Đối chiếu quyết định với thao tác và kết quả target. |

Ví dụ:

~~~text
Beneficiary: person-2048
Target: production-platform
Resource: cluster-vn-2/service-catalog
Action: service:restart
Duration: 45 phút, theo ticket INC-2026-482
Required approvals: manager -> (resource owner AND Security)
Extra conditions: privileged MFA; no SoD conflict; JIT
~~~

Mỗi quyết định phải ràng buộc với **toàn bộ scope và phiên bản request**. Approve quyền đọc một báo cáo **không phải** Approve quyền xuất toàn bộ dữ liệu hoặc quyền admin.

### 2.1. Requester không nhất thiết là beneficiary

Một manager có thể xin quyền cho nhân viên; một người cũng có thể gửi request thay đồng nghiệp. Để chống lạm dụng phải kiểm tra self-approval với **beneficiary** và những actor khác theo policy, không chỉ so sánh người bấm nút với trường requester.

## 3. Tuần tự, song song và hỗn hợp

### 3.1. Sequential approval — tuần tự

~~~mermaid
flowchart TD
    R["Submit request"] --> M["Manager: business need"]
    M -->|Approve| O["Resource owner: resource scope"]
    M -->|Reject| X["REJECTED"]
    O -->|Approve| S["Security: risk + SoD"]
    O -->|Reject| X
    S -->|Approve| F["FINAL_APPROVED"]
    S -->|Reject| X
    F --> C["Pre-provision revalidation"]
    C --> P["Provisioning, then readback"]
~~~

Ưu điểm là mỗi cấp có thể dựa vào kết quả cấp trước; nhược điểm là **thời gian chờ cộng dồn**, và task cấp sau có thể chưa được gửi nếu cấp trước vắng mặt. Cần timeout/escalation được định nghĩa trước, **không tự chuyển timeout thành Approve**.

### 3.2. Parallel approval — song song

~~~mermaid
flowchart TD
    R["Submit request"] --> B["Parallel review stage"]
    B --> M["Manager"]
    B --> O["Resource owner"]
    B --> S["Security"]
    M --> J["Aggregate ALL_REQUIRED"]
    O --> J
    S --> J
    J -->|Tất cả Approve hợp lệ| F["FINAL_APPROVED"]
    J -->|Một mandatory Reject| X["REJECTED"]
    F --> P["Provision after revalidation"]
~~~

Các task được gửi đồng thời; điều kiện **AND** chỉ đạt khi **mọi nhánh bắt buộc** hoàn tất hợp lệ. Owner Approve không làm hệ thống được phép cấp quyền khi Security còn pending.

### 3.3. Hybrid approval — kết hợp

Có thể xác nhận nhu cầu nghiệp vụ trước rồi cho **resource owner và Security** xem xét song song; chỉ yêu cầu **data owner** khi resource thuộc loại hạn chế.

~~~mermaid
flowchart TD
    R["Request"] --> M["Manager"]
    M -->|Approve| B["Owner và Security song song"]
    B --> O["Owner review"]
    B --> S["Security review"]
    O --> J["AND join"]
    S --> J
    J --> K{"Restricted dataset?"}
    K -->|Có| D["Data owner review"]
    K -->|Không| F["Final policy check"]
    D -->|Approve| F
    F --> A["Approved -> Provisioning"]
~~~

Route phải được tính từ **risk classification/resource catalog đã được kiểm chứng**, không từ tham số client tự khai như `skipSecurity=true`.

### 3.4. Quorum, AND, OR, k-of-n

| Kiểu | Điều kiện thành công | Điểm cần tránh |
| --- | --- | --- |
| **ALL / AND** | Mọi approver **bắt buộc** đều chấp thuận. | Không gộp thành majority vote. |
| **ANY / OR** | Một trong tập approver **được ủy quyền cho cùng một cấp** đồng ý. | Không dùng để bỏ cấp Security độc lập. |
| **k-of-n** | Ít nhất `k` người độc lập hợp lệ trong `n` approver đồng ý. | Không đếm hai account của cùng người thành hai phiếu. |
| **Veto** | Một cấp có thể từ chối toàn bộ request theo policy. | Không để quorum ghi đè mandatory veto. |

Ví dụ yêu cầu **Manager AND Security** không thể được coi hoàn tất vì “2 trong 3 manager đã approve”. Quorum chỉ có ý nghĩa **trong stage mà chính sách cho phép**.

## 4. Routing approval theo quyền và mức rủi ro

| Yêu cầu | Route tham khảo | Điều kiện bổ sung |
| --- | --- | --- |
| Baseline app access cho Joiner. | Auto-approve theo policy nếu đủ điều kiện. | HR active/effectiveAt, đúng tenant và role. |
| Đọc dữ liệu nội bộ theo assignment. | Manager hoặc resource owner theo risk. | Data scope và owner. |
| Dữ liệu phân loại hạn chế. | Manager AND Data owner, có thể thêm Security. | Purpose, retention, hạn truy cập. |
| Role thay cấu hình production. | Manager → Owner AND Security. | JIT/PAM, step-up, SoD, scope/time. |
| IAM GlobalAdmin. | Privileged owner + Security governance/independent approval. | Không tự gán, tránh standing admin rộng. |
| Quyền vào secret của workload. | Service owner + secret owner, thêm Security theo risk. | Trust binding, credential lifecycle. |
| Ngoại lệ vi phạm SoD. | Exception authority được chỉ định. | Compensating controls, expiration, review. |

Các route **chỉ là ví dụ**, không phải số cấp bắt buộc cho mọi doanh nghiệp. Thực tế phải định nghĩa bằng **risk matrix**, authority và entitlement catalog do owner quản lý.

### 4.1. Không cho người dùng tự hạ risk để né cấp

`requestedRoleId` là input của request, nhưng risk phải lấy từ **catalog có thẩm quyền**. Nếu một client gửi `risk=LOW` để được route qua một manager thay vì Security, hệ thống phải từ chối tin giá trị đó.

### 4.2. Chọn approver từ nguồn đáng tin

- Manager theo **HRIS/relationship hiện hành**.
- Application owner theo **application catalog**.
- Data owner theo **data catalog**.
- Security reviewer theo **IAM/IGA policy registry**.
- PAM approver theo **privileged workflow và ca trực có thẩm quyền**.
- Workload owner/sponsor theo **service identity registry**.

Thiếu manager, owner đã nghỉ việc hoặc dữ liệu mâu thuẫn phải dẫn tới **routing review/escalation được phê duyệt**, không chọn người bất kỳ rồi tự động cấp.

## 5. No-self-approval, identity binding và SoD

### 5.1. Không chỉ kiểm tra email

Một người có thể có account `lan@example.invalid` và `lan-admin@example.invalid`. Nếu cùng một IAM identity thì **không phải hai người duyệt độc lập**. Phải đối chiếu **person/identity ID có thẩm quyền**, không chỉ username hoặc account ID.

Một predicate minh họa:

~~~text
canApprove(actor, task) =
    actor.identityVerified
    AND actor.accountActive
    AND actor.authority.includes(task.target, task.role, task.tenant)
    AND actor.identityId != task.beneficiaryIdentityId
    AND independentApprovalRequirementsSatisfied(actor, task)
    AND task.state == PENDING
    AND actor.delegationOrAppointmentStillValid
~~~

Không phải công thức chuẩn của IAM. Policy cụ thể có thể cấm thêm việc requester tự duyệt, người duyệt tự quyết định exception của chính mình, hoặc hai cấp độc lập dùng cùng actor.

### 5.2. Phân biệt SoD của approval và entitlement

- **Approval SoD:** người xin quyền, người hưởng quyền, owner và security reviewer phải độc lập theo rule.
- **Entitlement SoD:** các quyền beneficiary đang có và sắp nhận không được tạo tổ hợp xung đột.

Một người được nhiều cấp approve role `PaymentApprover` vẫn có thể bị chặn nếu họ đã giữ `PaymentCreator` và policy cấm kết hợp. Phải xét **role hierarchy, direct grants và permission effective**, không chỉ role được gán trực tiếp.

### 5.3. SoD trên từng giao dịch

Quyền duyệt một khoản thanh toán còn cần điều kiện `approverIdentityId != payment.createdByIdentityId` nếu maker–checker policy yêu cầu. **Approval để giữ role** không thay thế kiểm tra **người tạo khác người duyệt giao dịch**.

### 5.4. Người điều khiển workflow cũng có đặc quyền

Ai được sửa policy route, bỏ Security stage, thay beneficiary sau khi Approve, tạo delegation hoặc ghi đè `FINAL_APPROVED` là người có **đặc quyền rất nhạy cảm**. Những thao tác này cần owner, review độc lập, audit và bảo vệ khỏi self-elevation.

## 6. State machine: approval khác provisioning

Một workflow rõ ràng cần định nghĩa state và chuyển trạng thái hợp lệ.

| State approval | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| `DRAFT` | Yêu cầu chưa gửi. | Đã được phê duyệt. |
| `SUBMITTED` | Request được chốt phiên bản và tính route. | Đã đủ eligibility. |
| `PENDING_APPROVAL` | Còn stage bắt buộc chưa quyết định. | Được provision vì một phiếu Approve. |
| `NEEDS_INFORMATION` | Chờ bổ sung hoặc chỉnh request. | Approve mặc định. |
| `FINAL_APPROVED` | Tất cả yêu cầu phê duyệt đạt. | Target đã cấp quyền. |
| `REJECTED` | Bị từ chối theo policy. | Entitlement cũ tự biến mất. |
| `CANCELLED` | Đã hủy request. | Mọi job provisioning cũ đã an toàn dừng nếu không kiểm tra. |
| `EXPIRED` | Quá hạn hiệu lực của request/decision. | Được tự động cấp quyền sau timeout. |
| `SUPERSEDED` | Request có phiên bản thay thế. | Approval phiên bản cũ còn áp cho bản mới. |

Ví dụ một luồng hậu phê duyệt:

~~~text
FINAL_APPROVED
  -> PRE_PROVISION_REVALIDATION
  -> PROVISIONING
  -> PENDING_RECONCILIATION
  -> VERIFIED

Các nhánh lỗi:
  PRE_PROVISION_REVALIDATION -> BLOCKED_FOR_REVIEW
  PROVISIONING              -> REMEDIATION_REQUIRED
  PENDING_RECONCILIATION    -> REMEDIATION_REQUIRED
~~~

**Approved ≠ Provisioned ≠ Verified.** Khi SCIM trả 5xx, workflow có thể vẫn approved nhưng **chưa có quyền**. Ngược lại, khi target còn direct grant cũ, Reject một request không đồng nghĩa quyền đó đã mất.

### 6.1. Xử lý Reject, Cancel và Request More Information

Một mandatory Reject thường khiến yêu cầu **không được cấp**; những task chưa cần thiết phải đóng hoặc hủy đúng chính sách. Nếu cho phép sửa request và submit lại, phải tạo **requestVersion mới** và xét lại những approval có thể bị ảnh hưởng. **Không để Approve muộn làm hồi sinh một request đã Reject.**

## 7. Version request, snapshot và thay đổi policy

### 7.1. Approval phải gắn với payload mà approver thấy

~~~text
Request V1:
  role: ReportReader
  scope: tenant-vn
  duration: 7 ngày
Manager: APPROVE V1

Request V2:
  role: ReportAdmin
  scope: all-tenants
  duration: 365 ngày

Không hợp lệ:
  Dùng approval của V1 để cấp V2.
~~~

Nên lưu **requestVersion hoặc payload fingerprint** gồm beneficiary, target, action, resource, scope, thời gian, purpose và risk category. Một thay đổi mở rộng quyền phải **invalidate hoặc re-route** theo policy.

### 7.2. Routing policy cũng có phiên bản

Khi role được Security phân loại lại từ medium thành high trong lúc request đang chờ, workflow phải có chiến lược được duyệt: **re-route theo policy mới, invalidate/reapprove, hoặc giữ policy trước với pre-grant risk revalidation** theo yêu cầu tổ chức. Điều không được phép là **âm thầm bỏ cấp Security bắt buộc** hoặc cấp đặc quyền khi rủi ro đã thay đổi.

### 7.3. Pre-provision revalidation

Trước khi gọi SCIM/API/PAM, phải kiểm tra:
- Beneficiary còn có **quan hệ công việc/contractor sponsor hiệu lực**?
- Vai trò, department, dự án hoặc resource owner có thay đổi?
- Có **Mover/Leaver** làm request hết căn cứ?
- Đã phát sinh quyền khác gây **SoD conflict**?
- Có direct grant sẵn, hoặc target account bị khóa?
- Scope/time window còn hợp lệ?
- Các approval có còn đúng request version và required policy?

**Approval tại T0 không bảo đảm entitlement vẫn hợp lệ tại T1**. Đây là lớp giảm cấp sai rất quan trọng trong IAM lifecycle.

## 8. Delegation, alternate approver và escalation

### 8.1. Khi approver vắng mặt

Các phương án được quản trị:
- **Alternate approver** được đăng ký trước, đúng role và scope.
- **Delegation** có `validFrom`, `validUntil` và đối tượng quyền rõ.
- **Escalation** tới reviewer có authority được policy cho phép.
- **Reassignment** bởi workflow administrator, có lý do và audit.

Không được mặc định một manager có quyền duyệt Group A có thể ủy quyền người khác duyệt GlobalAdmin cho toàn tổ chức.

### 8.2. Delegation không mở rộng authority

~~~text
delegateCanApprove =
    delegation.isActiveAt(now)
    AND delegation.scope.includes(task.role, task.resource, task.tenant)
    AND delegator.wasAuthorizedForTask
    AND delegate.identityActive
    AND delegate != beneficiary
    AND noApprovalSoDConflict
~~~

Phải ngăn delegation vòng, ủy quyền lại trái policy, một người duyệt nhiều cấp “độc lập” thông qua hai account, hoặc sử dụng delegation đã hết hạn.

### 8.3. Escalation không phải implicit approval

Nếu cấp manager chờ quá SLA, có thể nhắc nhở, chuyển alternate có thẩm quyền hoặc đánh dấu `EXPIRED`. **Không dùng timeout như một lá phiếu Approve** cho đặc quyền, dữ liệu nhạy cảm hoặc exception SoD. Nếu hệ thống hỗ trợ auto-approval ở quyền thấp, đó phải là **policy explicit** có điều kiện, không phải một mẹo timeout.

## 9. Multi-level approval trong Joiner

**Joiner** là giai đoạn danh tính mới được xác minh và cấp account/quyền theo quan hệ làm việc. HRIS/contractor source và IAM enrollment cung cấp identity, assignment và effective date.

~~~mermaid
flowchart TD
    HR["HRIS Joiner"] --> IAM["Verify identity + employment + startDate"]
    IAM --> B["Compute baseline least-privilege access"]
    B --> Q{"Extra/privileged entitlement?"}
    Q -->|Không| AUTO["Baseline policy-controlled provisioning"]
    Q -->|Có| M["Manager business need approval"]
    M --> O["Owner resource/data approval"]
    O --> S{"Security stage required?"}
    S -->|Có| SEC["Security/SoD approval"]
    S -->|Không| CHECK["Pre-provision validation"]
    SEC --> CHECK
    CHECK --> P["Provision approved entitlements"]
    AUTO --> V["Target readback + audit"]
    P --> V
~~~

Sơ đồ thể hiện các đường thành công; mọi Reject và điều kiện thiếu đều phải **chặn cấp**.

### 9.1. Quyền nền khác quyền đặc biệt

Các ứng dụng chung, quyền đọc cần thiết có thể được cấp theo **policy được phê duyệt trước** khi Joiner đủ điều kiện. Quyền admin hoặc dữ liệu nhạy cảm có thể cần manager, application/data owner và Security. Không áp ba cấp chỉ để làm đẹp thống kê approval.

### 9.2. Approval trước ngày bắt đầu

Có thể chuẩn bị account, thiết lập MFA và hoàn tất approval trước ngày đầu tiên. Nhưng quyền privileged phải tuân thủ `effectiveFrom`, trạng thái account và policy. Nếu HRIS hủy hợp đồng trước ngày bắt đầu, request không được provision chỉ vì approval đã xong. **Cần revalidation tại thời điểm thực thi.**

## 10. Multi-level approval trong Mover

Mover thường giữ nguyên IAM identity/IdP account nhưng thay đổi role, department hoặc nhiệm vụ. Một sai lầm phổ biến là chỉ route **quyền mới**, không thu hồi **quyền cũ**.

| Hành động | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **KEEP** | `AllEmployees`. | Giữ nếu assignment vẫn hiệu lực. |
| **REMOVE** | `OpsProductionOperator`. | Revoke đúng mốc, readback quyền. |
| **GRANT** | `FinanceReportReader`. | Approve theo owner/risk, cấp sau kiểm tra SoD. |
| **REVIEW** | Role CloudAdmin, JIT grant hoặc dự án tạm. | Xác minh owner, expiry và nhu cầu thật. |

### 10.1. Thu hồi quyền cũ không phụ thuộc phê duyệt quyền mới

~~~text
Mover event
  ├─ REVOKE TRACK:
  │   -> Xác định quyền Operations không còn căn cứ
  │   -> Deprovision theo effectiveAt
  │   -> Readback actual access
  └─ GRANT TRACK:
      -> Request quyền Finance
      -> Multi-level approval theo risk
      -> Revalidate / provision / verify
~~~

**Không chờ Finance manager Approve rồi mới gỡ production admin đã hết căn cứ**, trừ khi có handover exception được phê duyệt riêng với scope/thời hạn rõ.

### 10.2. Hạn chế xung đột SoD trong chuyển tiếp

Nếu Lan chuyển từ người tạo thanh toán sang người duyệt, cần kiểm tra không có khoảng thời gian mang cả `PaymentCreator` và `PaymentApprover` trái policy. Một giải pháp là **gỡ role cũ và xác minh**, rồi mới kích hoạt role mới khi đủ approval, tùy yêu cầu continuity và compensating controls.

## 11. Multi-level approval trong Leaver

Khi nguồn nhân sự có thẩm quyền xác nhận **Leaver** tới mốc hiệu lực, IAM phải thực hiện offboarding theo policy **không chờ một request phê duyệt cấp quyền mới**.

### 11.1. Phân biệt thu hồi mặc định và ngoại lệ

- HRIS/contractor source xác định sự kiện kết thúc quan hệ.
- IAM chặn AuthN và revoke target accounts/entitlements theo quy trình.
- Nếu cần gia hạn truy cập ngoại lệ, tạo **một request riêng** có owner, scope, deadline và approval phù hợp.
- Việc bàn giao dữ liệu/ownership có thể cần review, nhưng không nên làm trễ **chặn login và đặc quyền của Leaver** theo SLA.

### 11.2. Những đường truy cập phải xét

| Đường | Kiểm tra |
| --- | --- |
| IdP/SSO | Account bị chặn đúng thời điểm. |
| SCIM User/Group | Target user disabled, membership/role đã thu hồi. |
| Local/privileged accounts | Không còn đăng nhập qua đường ngoài IdP. |
| PAM/JIT eligibility và active sessions | Quyền đặc biệt không còn khả dụng. |
| OAuth access/refresh token, PAT, API key | Credential còn hiệu lực được xử lý theo policy. |
| Role hierarchy, nested groups, direct grants | Không còn quyền qua đường gián tiếp. |
| Audit/reconciliation | Target thực sự đã chặn quyền bắt buộc. |

Một request **Approved for offboarding** chỉ ghi nhận quyết định/điều phối, **không chứng minh mọi đường truy cập đã bị vô hiệu hóa**.

## 12. Phê duyệt quyền đặc biệt: PAM/JIT và hai vòng quyết định

Với privileged access có thể có:
1. **Eligibility approval:** người dùng được phép **xin** một loại đặc quyền.
2. **Activation approval:** quyền được phép **kích hoạt ngay lúc này** theo ticket/scope/duration.

Hai loại có thể do approver khác nhau xác nhận. Eligibility là **căn cứ được xét**, không đồng nghĩa một phiên admin đang hoạt động.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Engineer
    participant P as PAM/JIT
    participant IAM as IAM policy
    participant O as Resource owner
    participant S as Security
    participant IDP as IdP/MFA
    participant T as Target
    U->>P: Xin service:restart trên service X, 45 phút
    P->>IAM: Check identity, eligibility, ticket, SoD
    IAM-->>P: Required route và scope
    P->>O: Owner approve
    O-->>P: Approve service X
    P->>S: Security approve nếu mandatory
    S-->>P: Approve theo policy
    P->>IDP: Step-up authentication
    IDP-->>P: Assurance hợp lệ
    P->>T: Activate scope hẹp có expiration
    T-->>P: Readback
    P->>T: Deactivate/revoke khi hết hạn
    T-->>P: Verify actual access denied
~~~

**Đến hạn 45 phút** chưa đủ để chứng minh token/session đã vô hiệu hóa. PAM và target phải kiểm soát hiệu lực permission/credential, re-evaluate hoặc terminate theo khả năng.

### 12.1. Break-glass là một luồng riêng

Khi IdP/PAM mất khả dụng, tổ chức có thể cần break-glass được thiết kế sẵn: account/credential bảo vệ riêng, phạm vi tối thiểu, cảnh báo/audit, post-incident review. **Không biến approver timeout thành tự động GlobalAdmin** hoặc tắt MFA/audit toàn hệ thống.

## 13. Multi-level approval cho tài khoản dịch vụ

**Service account/workload identity** không nhất thiết có manager trong HRIS. Approver phải đến từ **service/workload owner registry**, resource/data owner và security authority.

Ví dụ workload `billing-etl` yêu cầu đọc dữ liệu hạn chế:

| Cấp | Cần xác nhận |
| --- | --- |
| Service owner | Job và mục tiêu nghiệp vụ còn cần, owner/team hợp lệ. |
| Data owner | Dataset, tenant, trường dữ liệu và mục đích hợp lệ. |
| Security | Credential/trust binding, risk, least privilege và thời hạn. |
| Platform operator | Chỉ triển khai theo request đã approved, không tự duyệt thay. |

Workload có thể dùng managed identity, workload identity federation, mTLS hoặc credential khác thay human SSO. Không áp dụng **human MFA** máy móc cho job. Khi owner con người Mover/Leaver, phải **bàn giao owner và gỡ quyền quản trị cá nhân**, không tự xóa workload còn phục vụ nghiệp vụ.

### 13.1. Không cho automation tự cấp quyền

Một pipeline có thể submit request và một provisioning bot có thể thực thi, nhưng bot đó **không tự động có authority duyệt GlobalAdmin cho chính nó**. Cần tách **submitter, approver, executor** và kiểm soát quyền của hệ thống approval/provisioning.

## 14. Kết nối IdP, SSO, SCIM, RBAC/ABAC và ticket

~~~mermaid
flowchart TD
    HR["HRIS / JML"] --> IAM["IAM/IGA request + policy"]
    USER["Requester / beneficiary"] --> IAM
    IAM --> ROUTE["Approval engine"]
    ROUTE --> M["Manager"]
    ROUTE --> O["Resource/data owner"]
    ROUTE --> S["Security"]
    M --> A["Aggregate decisions"]
    O --> A
    S --> A
    A --> CHECK["Pre-provision eligibility + SoD"]
    CHECK --> PROV["SCIM / API / PAM / manual"]
    PROV --> IDP["IdP groups/app assignment"]
    PROV --> APP["Target account/roles/grants"]
    IDP --> SSO["SSO AuthN"]
    SSO --> APP
    APP --> PEP["RBAC/ABAC enforcement"]
    PEP --> V["Target readback + audit"]
    V --> IAM
~~~

- **IdP/SSO** chứng minh đăng nhập, có thể cung cấp claims theo trust.
- **SCIM** có thể đồng bộ User/Group, nhưng không chuẩn hóa mọi privileged role.
- **RBAC/ABAC** quyết định hành động trên resource cụ thể.
- **Approval engine** xác nhận authority và điều kiện cấp quyền.
- **PAM** quản lý privileged eligibility/activation/session khi hỗ trợ.
- **Reconciliation** so desired access với actual access.

Một người duyệt có MFA tốt **không tự nhiên có quyền duyệt mọi role**; login success là **authentication**, approval authority là **authorization cho thao tác duyệt**.

### 14.1. ITSM ticket không thay bằng chứng IAM

Ticket chứa “Approved” có thể là business approval, nhưng chưa chắc đã có approval của resource owner hoặc Security, chưa chắc gắn đúng requestVersion/scope. IAM cần lưu **actor, authority, policy, target, decision và timestamp** cho từng cấp.

## 15. JSON dữ liệu yêu cầu minh họa

Dưới đây là **schema nội bộ minh họa**, không phải định dạng chuẩn SCIM/OIDC/ITSM:

~~~json
{
  "requestId": "AR-2026-1042",
  "requestVersion": 3,
  "correlationId": "IAM-MOVER-2048",
  "requesterIdentityId": "person-104",
  "beneficiaryIdentityId": "person-2048",
  "target": {
    "applicationId": "production-platform",
    "tenant": "tenant-vn",
    "resourceRef": "cluster-vn-2/service-catalog",
    "roleRef": "ScopedRestartOperator",
    "action": "service:restart"
  },
  "validity": {
    "from": "2026-12-02T10:00:00+07:00",
    "until": "2026-12-02T10:45:00+07:00"
  },
  "approvalPolicy": {
    "id": "privileged-jit-v5",
    "version": 5,
    "route": "MANAGER_THEN_OWNER_AND_SECURITY",
    "stages": [
      {
        "stageId": "business",
        "authority": "MANAGER",
        "decision": "APPROVE",
        "actorIdentityId": "person-300",
        "decisionRequestVersion": 3
      },
      {
        "stageId": "risk",
        "requiredAuthorities": ["RESOURCE_OWNER", "SECURITY"],
        "join": "ALL_REQUIRED",
        "status": "PENDING"
      }
    ]
  },
  "sourceLifecycleEventId": "HR-MOVER-2026-088",
  "state": {
    "approval": "PENDING_APPROVAL",
    "provisioning": "NOT_STARTED",
    "reconciliation": "NOT_STARTED"
  }
}
~~~

Một production system cần thêm **immutable audit events, actor authentication, idempotency, approval time, reason, version hash và error handling**. Không ghi secret hoặc token vào approval record.

### 15.1. Lưu event, không chỉ boolean

~~~text
REQUEST_SUBMITTED
ROUTE_EVALUATED(policyVersion, stageIds)
TASK_ASSIGNED(stageId, approverAuthority)
DECISION_RECORDED(stageId, actor, decision, requestVersion)
REQUEST_REVALIDATED(lifecycleState, SoD, risk, scope)
FINAL_APPROVAL_REACHED
PROVISIONING_STARTED(target, idempotencyKey)
PROVISIONING_RESULT(success/failure, targetAccountId)
TARGET_READBACK(desired, actual, timestamp)
REQUEST_VERIFIED(evidenceRef)
~~~

**Một cờ `approved=true` không cho biết ai đã duyệt, dựa trên quyền gì, hay quyền có được cấp đúng scope không.**

## 16. Pseudocode tính final approval an toàn

~~~text
function recordDecision(requestId, stageId, actorId, decision, expectedVersion):
    request = loadRequestWithConcurrencyControl(requestId)

    require request.version == expectedVersion
    require request.state == PENDING_APPROVAL
    require stageId belongs to active approval route
    require decision in {APPROVE, REJECT, NEEDS_INFORMATION}

    actor = loadVerifiedIdentity(actorId)
    require actor.active
    require actor.authorizedFor(stageId, request.role, request.target, request.tenant)
    require actor.satisfiesApprovalSoD(request)
    require actor.authenticationAssuranceMeetsPolicy
    require actor.delegationIfAnyIsCurrentlyValid

    require actor has no existing counted vote for this distinct-person requirement
    recordImmutableDecisionEvent(request, stageId, actor, decision)

    if decision == REJECT and stageHasMandatoryVeto(stageId):
        closeOutstandingTasks(request)
        transition(request, REJECTED)
        return

    if decision == NEEDS_INFORMATION:
        pauseOrInvalidateTasksAccordingToPolicy(request)
        transition(request, NEEDS_INFORMATION)
        return

    if not allRequiredStagePredicatesSatisfied(request.route):
        return PENDING_APPROVAL

    latest = loadCurrentLifecycleAndEntitlements(request.beneficiary)
    require request.payloadMatchesApprovedSnapshot
    require latest.identityActiveAndEligible
    require latest.resourceAndScopeStillValid
    require latest.noSoDConflictAfterProposedGrant
    require policyVersionRequirementsStillSatisfied

    transition(request, FINAL_APPROVED)
    enqueueProvisioningOnce(
        requestId,
        request.version,
        idempotencyKeyFor(requestId, request.version)
    )
    return FINAL_APPROVED
~~~

Pseudocode chỉ mô tả kiến trúc; phải dùng framework/thư viện IAM thực tế, transactions/outbox, audit integrity, xử lý network failure và race condition. Đặc biệt, **đừng thực hiện lệnh cấp quyền trong cùng một transaction database dài** mà không có chiến lược phục hồi khi connector timeout.

## 17. Concurrency, idempotency và rủi ro chạy đua

| Race condition | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Beneficiary thành Leaver đúng lúc manager Approve. | Cấp quyền sau khi quan hệ đã chấm dứt. | Revalidate JML trước grant. |
| Hai người Approve gần như đồng thời. | Hai worker provision cùng role/account. | Atomic finalization, version check, idempotency. |
| Request bị sửa scope sau khi một cấp duyệt. | Reuse approval cho quyền rộng hơn. | Snapshot hash/version, invalidate/re-route. |
| Security Reject, manager Approve muộn. | Request bị “hồi sinh”. | Terminal state transition và task cancellation. |
| Delegation hết hạn trong lúc quyết định gửi. | Phiếu do actor hết authority. | Recheck authority tại thời điểm ghi quyết định. |
| Role risk policy được nâng trước khi provision. | Thiếu cấp bắt buộc. | Policy revalidation hoặc reapproval. |
| SCIM timeout nhưng target đã tạo account. | Retry tạo trùng. | Idempotency, target readback, reconcile. |
| Mover remove và grant chạy đồng thời. | Xung đột SoD hoặc gỡ nhầm quyền. | Desired-state planner và sequencing. |

### 17.1. Bốn loại thời hạn khác nhau

1. **Approval-task SLA**: bao lâu reviewer nên quyết định.
2. **Decision validity**: approval còn được phép dùng để provision đến khi nào.
3. **Entitlement effective window**: quyền active từ ngày nào đến ngày nào.
4. **Credential/session expiry**: khi nào target ngừng chấp nhận token hoặc session.

Một approval cho GlobalAdmin **không tự vẫn hợp lệ sau nhiều tháng** chỉ vì decision record còn trong database. Cần expiration/revalidation theo risk và policy.

### 17.2. Retry an toàn

Cần có `idempotencyKey` gắn request/version/target/action. Nếu worker gặp timeout, phải kiểm tra **target account/group/role state** trước khi retry. Không mặc định HTTP 5xx chứng minh không có side effect; cũng không mặc định HTTP 200 chứng minh quyền đã thực sự effective.

## 18. Audit, accountability và bảo vệ dữ liệu

| Nhóm bằng chứng | Câu hỏi phải trả lời |
| --- | --- |
| **Identity binding** | Requester, beneficiary và approver thật là ai? |
| **Approver authority** | Vì sao từng người được quyền duyệt role/resource đó? |
| **Request snapshot** | Họ đã duyệt chính xác bản/version nào? |
| **Routing policy** | Vì sao những cấp này là bắt buộc? |
| **Decision events** | Ai Approve/Reject, lúc nào, có delegation không? |
| **SoD/risk review** | Có tự duyệt, đặc quyền và xung đột không? |
| **Finalization** | Khi nào toàn bộ điều kiện required đạt? |
| **Provisioning** | Connector đã thao tác tại target nào, thành công hay lỗi? |
| **Target readback** | Actual access có khớp desired access không? |
| **Revocation/expiry** | Quyền tạm đã thực sự mất vào đúng hạn? |
| **Remediation** | Nếu sai lệch, ai xử lý và trạng thái ra sao? |

Audit của quyền nhạy cảm nên có chính sách lưu trữ, phân quyền xem/sửa, bảo vệ tính toàn vẹn và theo dõi administrator thay policy. Không đưa password, OTP, private key, full token hoặc PII không cần thiết vào log.

### 18.1. Evidence độc lập

~~~text
APPROVAL EVIDENCE:
  Manager approved request V3
  Resource owner + Security approved required stage
  No self-approval or authority gap
  Pre-grant eligibility/SoD valid

PROVISIONING EVIDENCE:
  Target connector command linked request V3
  Account/entitlement readback matches approved scope
  Unauthorized actions denied by target
  Expiration/revocation control registered and verified when due
~~~

**Thiếu bằng chứng provisioning thì chưa thể kết luận workflow đã hoàn tất ở ứng dụng đích.**

## 19. Ma trận test multi-level approval

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **T1** | Sequential: đủ manager/owner/Security. | Final approval rồi pre-provision checks. |
| **T2** | Chỉ manager Approve. | Pending, không provision. |
| **T3** | Parallel AND: owner Approve, Security chưa. | Pending. |
| **T4** | Security mandatory Reject. | Rejected, không cấp. |
| **T5** | Quorum 2-of-3 với hai người khác nhau. | Stage đạt nếu authority/SoD đúng. |
| **T6** | Cùng một người dùng hai account bỏ hai phiếu. | Không được tính hai approver độc lập. |
| **T7** | Beneficiary tự duyệt request. | Bị chặn. |
| **T8** | App owner của A duyệt GlobalAdmin của B. | Bị chặn sai scope. |
| **T9** | HR manager thiếu/đã nghỉ. | Authorized fallback/routing review. |
| **T10** | Task quá SLA. | Remind/escalate/expire; không auto-grant. |
| **T11** | Delegation đã hết hạn. | Reject decision. |
| **T12** | Request đổi read → admin sau approval. | Invalidate/reapprove. |
| **T13** | Beneficiary thành Leaver lúc pending. | Block/cancel grant, revoke JML. |
| **T14** | Mover tạo conflict Maker/Checker. | SoD block/route review. |
| **T15** | Hai approvals cuối đồng thời. | Finalize và provision hữu hiệu một lần. |
| **T16** | SCIM lỗi sau approval. | Approved but provisioning failed. |
| **T17** | Target role gỡ nhưng token cũ còn admin. | Residual access, không Verified. |
| **T18** | PAM JIT đến expiry. | Hành động privileged bị chặn. |
| **T19** | Workload owner chuyển người. | Route theo owner có hiệu lực, không theo manager cũ. |
| **T20** | Direct API gọi provision mà không có approval. | Chặn nếu không có authority/approved work item. |

### 19.1. Invariants cần bảo đảm

- Không có grant mới nếu các **required approval predicates** chưa đạt.
- Approval không có hiệu lực cho request khác version/scope.
- Một người không được tính hai lần khi cần hai ý kiến độc lập.
- Reject/cancel/expire không dẫn tới grant theo cùng request.
- Timeout không thay thế mandatory approval.
- Mover/Leaver làm request hết căn cứ phải chặn grant mới.
- Final Approved vẫn cần current eligibility, SoD và scope.
- Retry không tạo duplicate side effects.
- Revocation JML không phụ thuộc approval quyền mới.
- `VERIFIED` đòi target actual state/effective access được chứng minh.

## 20. Tình huống xuyên suốt: Operations → Finance với JIT

**Bối cảnh:** Lan có IAM identity `person-2048`, account IdP và quyền vận hành Operations. HRIS thông báo Lan sẽ chuyển sang Finance lúc 10:00 ngày 02/12. Lan xin JIT `service:restart` trên `cluster-vn-2/service-catalog` trong 45 phút để hỗ trợ sự cố bàn giao.

### 20.1. Yêu cầu và route

Policy yêu cầu:
1. Manager xác nhận business need.
2. Resource owner và Security **cùng** phê duyệt, độc lập.
3. IAM revalidate JML/SoD.
4. PAM activate đúng scope/time sau step-up.
5. Target verify, khi hết hạn thì revoke.

### 20.2. Quyết định trước mốc Mover

Manager và owner Approve lúc 09:00. Security kiểm tra role Operations sẽ hết căn cứ vào 10:00. Nếu JIT window từ 10:15 đến 11:00, một approval trước đó **không đủ** để cấp quyền sau Mover. Phải có handover exception hợp lệ hoặc request được từ chối/chỉnh scope.

Nếu Security Reject, manager + owner không thể “bỏ phiếu 2-1” để vượt mandatory Security stage.

### 20.3. Khi approved nhưng provisioning chạy chậm

Nếu cả ba Approve lúc 09:30 nhưng worker bắt đầu provision lúc 10:05, **pre-provision revalidation** phát hiện Lan đã chuyển bộ phận. Không có exception mới thì không cấp quyền; workflow có thể bị `BLOCKED_FOR_REVIEW` hoặc `SUPERSEDED` tùy policy.

### 20.4. Khi có handover exception hợp lệ

Một exception được review lại:
- Chỉ cho `service:restart` trên service X.
- Có resource owner + Security approval theo risk.
- Hạn 45 phút, không tạo standing GlobalAdmin.
- PAM/JIT thực thi role/credential đúng phạm vi.
- Hết hạn, session/token và target permission được kiểm tra lại.

### 20.5. Khi Lan trở thành Leaver

Sau này Lan nghỉ việc. HRIS phát Leaver có hiệu lực; IdP và target accounts/roles, local privileges, PAM/JIT, tokens/keys cần được xử lý theo deprovisioning. Không đợi một approval vòng mới để chặn quyền đã hết căn cứ. **Quyết định approval là điểm kiểm soát cấp mới, không thay thế vòng đời thu hồi**.

## 21. KPI và các sai lầm cần tránh

| KPI | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| **Approval lead time** | Submit đến final decision theo risk. | Nhanh hơn luôn an toàn hơn. |
| **Stage SLA compliance** | Từng cấp quyết định đúng hạn. | Timeout được phép auto-approve. |
| **Routing correctness** | Request đúng approver có authority. | Chỉ đủ số người bấm là đủ. |
| **Self-approval blocked** | Hệ thống phát hiện actor xung đột. | Hai account khác nhau chắc là hai người. |
| **SoD detected pre-grant** | Conflict bị chặn trước khi cấp. | Chỉ cần xem role direct. |
| **Approved-not-provisioned** | Approval đạt nhưng target chưa có quyền. | User đã có access. |
| **Provisioned-without-approval** | Actual grant không có quyết định hợp lệ. | Đây là lỗi nhẹ về process. |
| **Revocation latency** | Từ mốc quyền hết căn cứ tới khi target chặn. | Thời điểm ticket close = actual revocation. |
| **JIT expiry verified** | Grant tạm thực sự mất sau hạn. | Chỉ nhìn expiry ở database IAM. |
| **Approval policy bypass** | Request bị gán scope/risk thấp sai hoặc bỏ stage. | Không phải rủi ro bảo mật. |
| **Service owner coverage** | Workload request có owner/sponsor hợp lệ. | Manager HRIS luôn phù hợp. |

### 21.1. Anti-patterns

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ba cấp đều do một người duyệt bằng ba account. | Không có độc lập thực chất. | Person-level identity correlation và SoD. |
| Owner Approve được coi thay Security Approve. | Bỏ qua mandatory risk gate. | AND/route rõ ràng. |
| Auto-approve do quá SLA. | Cấp đặc quyền khi không ai đánh giá. | Escalation/reassign theo authority. |
| Đổi scope sau approval nhưng giữ decision cũ. | Cấp quyền khác dữ liệu đã duyệt. | Versioned immutable request. |
| Route dựa trên risk do client khai. | Dễ hạ cấp bảo vệ. | Risk từ role/resource catalog. |
| Approver đã Mover/Leaver vẫn được tính authority. | Decision không còn hợp lệ. | Authority revalidation/delegation. |
| Không kiểm tra HR status trước provision. | Cấp quyền cho Leaver. | Pre-provision JML check. |
| Chờ quyền mới duyệt mới thu hồi quyền Mover cũ. | Privilege accumulation. | Tách revoke/grant tracks. |
| Chỉ kiểm tra Group SCIM, bỏ direct grant. | SoD/effective access sai. | Reconciliation đa nguồn. |
| Ticket `Approved` được coi là target đã cấp. | Người dùng thiếu quyền hoặc cấp quá rộng. | Trạng thái approval/provisioning/verification riêng. |
| JIT kết thúc nhưng token/session còn hoạt động. | Residual privileged access. | Revocation + readback. |
| Automation tự phê duyệt rồi tự cấp GlobalAdmin. | Bypass mọi cấp. | SoD/privileged approval engine governance. |

## 22. Checklist và bài tập tự kiểm tra

### 22.1. Checklist triển khai

- [ ] Có `requestId/version`, requester, beneficiary, identity binding và target.
- [ ] Xác định đúng entitlement/action/resource/tenant/scope/time.
- [ ] Routing theo risk/owner authority, không theo tham số client chưa tin.
- [ ] Biết stage nào sequential, parallel, all-of, any-of, k-of-n, veto.
- [ ] Quorum không ghi đè mandatory stages.
- [ ] Có kiểm tra self-approval, distinct-person rule và SoD.
- [ ] Approver, delegation và fallback có effective time/scope hợp lệ.
- [ ] Approval gắn request snapshot/policy version; thay đổi nhạy cảm phải reapprove.
- [ ] State machine xử lý Reject, Cancel, Needs Info, Expire, Supersede.
- [ ] Không provision khi pending hoặc timeout.
- [ ] Pre-provision kiểm tra JML, SoD, current scope và existing grants.
- [ ] Provisioning với concurrency control, idempotency và retry/readback an toàn.
- [ ] Approval, provisioning và verification là các trạng thái độc lập.
- [ ] Joiner baseline có policy; quyền đặc biệt duyệt theo risk.
- [ ] Mover thu hồi quyền cũ độc lập khỏi phê duyệt quyền mới.
- [ ] Leaver chặn truy cập đúng mốc, không chờ approval cấp mới.
- [ ] JIT/PAM có step-up, scope, time limit, session/token revocation.
- [ ] Workload/service account có owner team và approval/credential lifecycle riêng.
- [ ] IdP/SSO, SCIM/API và RBAC/ABAC đúng vai trò.
- [ ] Audit đủ actor, authority, version, decision, target và verification evidence.
- [ ] Reconciliation kiểm chứng quyền còn tồn dư hoặc grant thiếu approval.

### 22.2. Bài tập A — Sequential và parallel

Một request production cần Manager, Owner và Security. Thiết kế cả **Manager → Owner → Security** và **Manager → (Owner AND Security)**. Khi Owner Reject còn Security Approve, hệ thống có được provision không? Vì sao?

### 22.3. Bài tập B — k-of-n và identity độc lập

Nhóm 3 approver cần 2 phiếu. Một người dùng hai account để duyệt hai lần. Hãy giải thích vì sao cần đếm theo IAM identity/person, không theo email/account; mô tả cách phát hiện và từ chối.

### 22.4. Bài tập C — Mover đang chờ approval

Lan xin `OpsAdmin`, manager và owner đã duyệt, Security chưa. HRIS phát Mover sang Finance. Các phiếu cũ có đủ để provision không? Cần revalidate những gì?

### 22.5. Bài tập D — Leaver và workflow offboarding

Một Leaver đang chờ manager duyệt ticket. Vì sao chặn IdP/privileged account và deprovision entitlement theo policy không nên chờ? Ngoại lệ bàn giao sau nghỉ phải được xử lý như thế nào?

### 22.6. Bài tập E — SoD qua role hierarchy

Beneficiary đã có `FinanceSuperUser` kế thừa `payment:create` và xin `PaymentApprover`. Manager và owner Approve. Điều gì phải xảy ra ở pre-provision SoD check, và tại sao approval không thay thế maker–checker?

### 22.7. Bài tập F — JIT token còn sống

JIT `service:restart` hết hạn sau 45 phút nhưng access token vẫn gọi API thành công. Phân biệt **approval expiry, role activation expiry, token validity và PEP enforcement**. Bằng chứng nào cần để đánh dấu Verified?

### 22.8. Bài tập G — Scope bị sửa sau khi duyệt

Manager duyệt quyền đọc một dataset trong 7 ngày; requester đổi thành export toàn bộ dữ liệu 90 ngày mà giữ approval cũ. Nêu yêu cầu đối với snapshot hash, request version và route lại.

### 22.9. Bài tập H — Service owner nghỉ việc

Workload `billing-etl` cần mở quyền mới, nhưng owner nhân sự đã nghỉ. Ai nên phê duyệt: manager cũ, service owner/team mới, data owner, Security? Vì sao không thể tự xóa workload đang chạy?

### 22.10. Bài tập I — Race condition hai approvals cuối

Hai approver gửi phiếu đồng thời khiến hai worker cùng nhận đủ quorum và chạy SCIM. Trình bày cách dùng **atomic finalization, version check, idempotency key và target readback** để không tạo duplicate.

**Điểm cần ghi nhớ:** **Multi-level approval** phối hợp những quyết định **đúng authority, đúng scope và độc lập khi cần** trước khi cấp quyền. Phải quản lý **sequential/parallel/quorum, no-self-approval, SoD, delegation, timeout, requestVersion và risk-based routing**. Trong IAM **Joiner–Mover–Leaver**, quyền mới chỉ được cấp **sau các phê duyệt bắt buộc và revalidation**, còn quyền hết căn cứ phải được **thu hồi đúng hạn**. Workflow chỉ thật sự hoàn tất khi **IdP/SSO, SCIM/API, PAM và ứng dụng đích** đã phản ánh desired access và được chứng minh bằng **readback, effective-access verification và audit**.

