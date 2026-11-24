# Reviewer thay thế trong Access recertification – định tuyến, thẩm quyền và kiểm toán

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **reviewer thay thế (substitute/alternate reviewer)** trong chiến dịch **Access recertification**, phân biệt với reviewer ban đầu, delegate, người được chuyển giao vĩnh viễn, người escalation và người phê duyệt quyền mới.
- Nêu các tình huống cần thay reviewer: nghỉ phép, Mover, Leaver, thay đổi manager/resource owner, tài nguyên mồ côi, SoD conflict, hết hạn và sự cố dữ liệu.
- Thiết kế tiêu chí **thẩm quyền, phạm vi, tính độc lập, thời hạn, điều kiện được chuyển việc** trước khi reviewer thay thế ra quyết định.
- Mô hình hóa **review item, campaign, reviewer assignment, reassignment event, delegated authority, decision, remediation task và audit evidence**.
- Xây dựng state machine có **deny-by-default** cho việc định tuyến, chuyển reviewer, phê duyệt, thu hồi và kiểm chứng quyền thực tế.
- Phối hợp **HRIS, IdP/SSO, IGA, SCIM, RBAC/ABAC/PBAC, PAM, ứng dụng đích và reconciliation** trong vòng đời **Joiner–Mover–Leaver**.
- Chống **self-review, rubber stamping, reviewer không đủ chuyên môn, owner cũ quyết định, phê duyệt hộ không được ủy quyền, race condition và stale decisions**.
- Thiết kế SLA/escalation, dashboard, test âm tính và tình huống thực tế để hạn chế **quyền truy cập tồn dư**.

## 1. Reviewer thay thế là gì?

Trong **Access recertification (tái chứng nhận quyền truy cập)**, **reviewer** là người có thẩm quyền đánh giá một tập quyền đã tồn tại và đưa ra quyết định theo policy: quyền đó **còn phù hợp để giữ, cần thu hồi hoặc phải chuyển xem xét thêm**.

**Reviewer thay thế** là người hoặc nhóm được workflow **chỉ định lại một cách có kiểm soát** để thực hiện một phần hoặc toàn bộ trách nhiệm review khi reviewer dự kiến ban đầu **không thể, không còn phù hợp hoặc không được phép đưa ra quyết định**.

Ví dụ: một chiến dịch quý yêu cầu quản lý trực tiếp rà soát quyền truy cập CRM của nhân viên. Trước hạn review, manager được chuyển sang bộ phận khác hoặc nghỉ việc. Nếu chiến dịch vẫn giữ người quản lý cũ làm reviewer, kết quả có thể không còn hợp lệ về thẩm quyền. Hệ thống cần xác minh **manager mới**, hoặc chuyển các review item tới **owner/nhóm giám sát có thẩm quyền**, kèm lịch sử đầy đủ.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, reviewer thay thế là mắt xích giúp việc rà soát quyền diễn ra liên tục giữa các biến động **Joiner–Mover–Leaver**, đồng thời liên kết dữ liệu **HRIS/identity registry, IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và thu hồi quyền tồn dư**.

**Điểm quan trọng:** reviewer thay thế không phải “một người bất kỳ được bấm Approve để hoàn thành chiến dịch”. Người đó phải có **thẩm quyền đối với đúng review item, đủ dữ liệu để đánh giá, không xung đột lợi ích, còn hoạt động và có dấu vết được chỉ định**.

### 1.1. Vì sao cần reviewer thay thế?

| Tình huống | Rủi ro nếu không xử lý | Hành động mong muốn |
| --- | --- | --- |
| Manager nghỉ phép dài ngày | Review treo tới hết hạn | Delegate có thời hạn hoặc fallback có thẩm quyền |
| Reviewer Leaver | Identity đã bị vô hiệu nhưng task vẫn gán | Thu hồi assignment, chuyển reviewer mới |
| Reviewer Mover | Không còn quản lý nhóm hoặc tài nguyên | Kiểm owner/manager mới, reassign |
| Owner của application đổi | Reviewer cũ thiếu thẩm quyền | Dùng ownership registry hiện hành |
| Người được review chính là reviewer | Tự đánh giá quyền của mình | Reviewer độc lập theo SoD |
| Review item sai owner | Quyền được “giữ lại” không có căn cứ | Chuyển đúng owner hoặc unresolved |
| Không có owner | Không ai chịu trách nhiệm | Escalate quy trình xác minh ownership |
| Campaign gần hết hạn | Dễ auto-approve để đạt SLA | Nhắc, escalate, exception; không tự coi là APPROVED |

## 2. Phân biệt các vai trò dễ nhầm

| Vai trò/khái niệm | Ý nghĩa | Ghi chú kiểm soát |
| --- | --- | --- |
| **Primary reviewer** | Người được policy chỉ định review item ban đầu | Có thể là manager, application owner hoặc data owner |
| **Substitute reviewer** | Người được chỉ định thay reviewer cho item/campaign | Phải xác minh thẩm quyền và SoD |
| **Delegated reviewer** | Người được primary reviewer ủy quyền trong phạm vi hợp lệ | Có hiệu lực theo delegation, không mở rộng thẩm quyền |
| **Reassigned reviewer** | Người nhận task do hệ thống/chủ sở hữu quy trình chuyển giao | Cần ghi nguyên nhân và actor thực hiện |
| **Fallback reviewer** | Người/nhóm dự phòng được policy xác định khi không giải quyết được reviewer chính | Không phải quyền mặc định của mọi IAM admin |
| **Escalation reviewer** | Người có thẩm quyền xử lý item tồn đọng hoặc rủi ro cao | Có thể chỉ phân xử/định tuyến, không tự giữ quyền |
| **Certification owner** | Người chịu trách nhiệm chiến dịch, tiêu chí, deadline và evidence | Không mặc định là reviewer đủ thẩm quyền cho mọi quyền |
| **Access request approver** | Người duyệt yêu cầu cấp quyền mới | Khác reviewer đánh giá quyền đã tồn tại |
| **Beneficiary / access holder** | Người hoặc workload đang có entitlement được rà soát | Có thể cần cung cấp bối cảnh, không mặc định tự chứng nhận |

### 2.1. Reviewer thay thế khác owner approval ban đầu

**Owner approval** trả lời “có nên cấp quyền này theo yêu cầu mới không?”. **Access recertification** trả lời “quyền đang tồn tại này có còn cần thiết và đúng policy không?”.

Một approval cấp quyền hợp lệ lúc Joiner **không bảo đảm** quyền ấy vẫn hợp lệ sau nhiều lần Mover. Ngược lại, reviewer thay thế quyết định **KEEP** trong một đợt recertification không phải quyền cấp role mới hoặc bỏ qua các chặn runtime.

### 2.2. Thay reviewer không đồng nghĩa thay người sở hữu tài nguyên

Có thể **ủy quyền thực hiện tác vụ review** cho người khác trong một thời hạn, nhưng **accountable owner** của tài nguyên không tự biến thành người được ủy quyền. Workflow nên lưu riêng **người/nhóm chịu trách nhiệm, người trực tiếp quyết định và nguồn ủy quyền**.

## 3. RACI và mô hình trách nhiệm

| Hoạt động | Accountable | Responsible | Bên liên quan |
| --- | --- | --- | --- |
| Xác định quyền nào phải review | Access governance/campaign owner | IGA team | Resource owners, security |
| Xác minh manager của beneficiary | HRIS/identity owner | HRIS/IGA connector | Manager mới |
| Xác minh owner tài nguyên | Resource governance | Resource catalog/CMDB steward | Application/data owner |
| Đề xuất reviewer thay thế | Policy/owner phù hợp | IGA workflow | Reviewer cũ, certification owner |
| Phê chuẩn thay thế khi cần | Owner hoặc authority độc lập theo policy | Workflow | Security/SoD |
| Đưa ra quyết định recertification | Reviewer hiện hành có thẩm quyền | Reviewer trực tiếp | Manager/resource owner, risk team |
| Thực hiện revoke sau quyết định | Chủ hệ thống/IAM vận hành | Connector/target admin | IGA |
| Xác minh quyền đã thay đổi | Access governance | Reconciliation/target | Auditor, resource owner |
| Kiểm tra audit và ngoại lệ | Compliance/security theo scope | Auditor/IGA | Campaign owner |

Bảng là **mẫu phân công trách nhiệm**, không phải RACI bắt buộc cho mọi doanh nghiệp. Một tổ chức có thể gộp các vai trò ở quyền thông thường nhưng vẫn cần **độc lập hợp lý cho quyền nhạy cảm**.

### 3.1. Ai phê chuẩn việc thay reviewer?

Tùy chính sách, có thể là:

- **Quy tắc tự động** từ HRIS/ownership registry (manager mới, owner mới).
- **Resource owner hiện hành** hoặc nhóm owner được ủy quyền.
- **Certification campaign owner** với quyền đổi reviewer trong scope đã được phê duyệt.
- **Security/IGA governance** khi có xung đột lợi ích, không có owner hoặc quyền đặc quyền.

Không nên cho **người bị review tự chỉ định bất kỳ đồng nghiệp nào làm reviewer mới** chỉ bằng cách thay một trường trong giao diện.

## 4. Khi nào cần thay reviewer?

### 4.1. Các nguyên nhân thông thường

1. **Absence:** nghỉ phép, nghỉ bệnh, không khả dụng trong một khoảng thời gian.
2. **Mover:** thay bộ phận, manager line, job hoặc trách nhiệm tài nguyên.
3. **Leaver:** quan hệ làm việc của reviewer đã hết hạn.
4. **Ownership change:** resource/application/data owner đổi.
5. **Delegation expired/revoked:** ủy quyền review không còn hiệu lực.
6. **SoD conflict:** reviewer là beneficiary hoặc có lợi ích trực tiếp.
7. **Unresolved ownership:** không tìm được người có thẩm quyền trong registry.
8. **Scope mismatch:** reviewer được gán quyền ngoài tenant/project mình quản lý.
9. **Competence gap:** reviewer không có đủ thông tin hoặc vai trò để đánh giá entitlement đặc thù.
10. **Campaign policy change:** chiến dịch thay định tuyến/quy tắc kiểm soát.
11. **Deadline escalation:** task quá hạn và policy cho phép chuyển tới reviewer có thẩm quyền.
12. **Account compromise:** tài khoản reviewer bị security block hoặc nghi chiếm quyền.

Không phải mọi lý do đều cho phép **auto-reassign**. Ví dụ người sở hữu tài nguyên vắng ngắn hạn có thể được ủy quyền tạm, trong khi owner không xác định cần xử lý governance trước.

### 4.2. Trường hợp KHÔNG nên thay tự động

- Reviewer ban đầu từ chối quyết định giữ quyền vì có rủi ro, requester muốn “tìm người dễ duyệt hơn”.
- Chủ thể bị review muốn tự chọn reviewer.
- Owner registry mâu thuẫn, chưa rõ ai chịu trách nhiệm.
- Quyền đặc quyền/cross-tenant cần independent security review mà fallback không đủ thẩm quyền.
- Một reviewer đã DENY/REVOKE, nhưng người khác muốn “đánh giá lại” không có cơ chế appeal có kiểm soát.
- Hệ thống chưa xác minh substitute có trạng thái ACTIVE hoặc đang bị security block.

**Chuyển reviewer không được trở thành approval shopping**, tức liên tục đổi người đánh giá cho đến khi nhận được KEEP.

## 5. Xác định reviewer gốc và reviewer thay thế từ nguồn có thẩm quyền

Reviewer có thể được chọn từ **manager hierarchy**, **resource ownership registry**, **application ownership**, **data classification**, **privileged access ownership** hoặc **workload ownership**.

| Loại recertification | Reviewer thường phù hợp | Fallback phù hợp khi policy cho phép |
| --- | --- | --- |
| Quyền ứng dụng theo nhiệm vụ | Line manager hiện hành | Manager cấp trên hoặc người được ủy quyền |
| Truy cập dữ liệu nhạy cảm | Data/resource owner | Delegate có scope hoặc accountable owner mới |
| Cloud IAM / admin roles | Privileged resource owner + security | Independent PAM/IGA reviewer |
| App local roles | Application owner | Chủ thể quản lý ứng dụng được xác minh |
| Quyền theo tenant | Owner của tenant/resource | Reviewer có authority đúng tenant |
| Service account/workload | Workload owner và/hoặc resource owner | Owner team/sponsor mới được xác minh |
| SoD exception | Người chịu trách nhiệm rủi ro, security | Independent security review team |
| Quyền không rõ nguồn | Governance triage | Không tự động KEEP |

### 5.1. Dữ liệu registry quan trọng

~~~yaml
resourceId: finance-reporting-data
resourceType: DATASET
tenantId: tenant-a
classification: CONFIDENTIAL
ownerIdentityId: person-501
ownerTeamId: finance-data-stewards
ownershipVersion: 12
ownerEffectiveFrom: "2026-11-01T00:00:00+07:00"
reviewPolicyId: finance-review-policy
reviewPolicyVersion: 4
fallbackAuthority: security-data-governance
~~~

Đây là **YAML minh họa**. Không được coi `ownerTeamId` trong request body người dùng là nguồn phê duyệt đã xác minh. Cần registry có nguồn, quy trình sửa đổi và audit.

### 5.2. Phân biệt thời điểm snapshot với current owner

Một campaign có thể tạo snapshot ngày 01/11 và kết thúc ngày 30/11. Nếu owner đổi ngày 15/11:

- Snapshot cần được giữ để **giải thích vì sao item ban đầu được giao**.
- Workflow phải kiểm **thẩm quyền hiện hành** trước khi reviewer cũ quyết định.
- Item chưa quyết định có thể được chuyển tới owner mới.
- Một decision đã thực hiện hợp lệ trước khi đổi owner không được âm thầm sửa lịch sử; các ngoại lệ hoặc re-review cần event mới.

**Snapshot là bằng chứng lịch sử; current ownership mới là một đầu vào thẩm quyền tại thời điểm hành động.**

## 6. Điều kiện đủ để trở thành reviewer thay thế

Một policy có thể diễn tả điều kiện thay reviewer:

~~~text
ALLOW substitute_review_decision WHEN
    substitute.identityStatus == ACTIVE
    AND substitute.isAuthenticated
    AND substitute.hasCurrentReviewAuthority(reviewItem)
    AND substitute.authority.validAt(now)
    AND substitute.scope.contains(
        reviewItem.resource,
        reviewItem.tenant,
        reviewItem.entitlement
    )
    AND NOT substitute.securityBlocked
    AND NOT sod.conflicts(substitute, reviewItem.beneficiary)
    AND reviewItem.status == PENDING_REVIEW
    AND campaign.status == ACTIVE
    AND now <= reviewItem.decisionDeadline
ELSE DENY
~~~

Đây là **mã giả**, không phải cú pháp một engine PBAC cụ thể.

### 6.1. Những kiểm tra tối thiểu

- **Identity linking:** xác minh actor bằng ID bền vững, không chỉ email.
- **Lifecycle:** reviewer đang ACTIVE trong quan hệ làm việc/ủy quyền có hiệu lực.
- **Authority:** reviewer có sở hữu/delegation/fallback authority chính xác.
- **Scope:** đúng resource, tenant, entitlement, environment, classification.
- **Independence:** không tự review hoặc vi phạm SoD theo policy.
- **Freshness:** manager/owner/delegation đã được cập nhật đủ mới.
- **Campaign state:** item chưa đóng, chưa bị quyết định hợp lệ bởi người khác.
- **Security posture:** không bị block, đã đáp ứng step-up nếu cần.
- **Auditability:** có thể lưu vì sao người mới được quyền review.

### 6.2. Reviewer không nhất thiết cần sở hữu toàn bộ tài nguyên

Ở một số chiến dịch, manager đủ thẩm quyền xác nhận **need-to-know** cho nhân viên, còn data owner xác nhận **data classification**; do đó thay manager bằng một data owner hoặc ngược lại không mặc nhiên tương đương.

Hệ thống phải định nghĩa loại reviewer theo **mục đích review**. Nếu policy yêu cầu **hai người đánh giá độc lập**, một substitute không được thay cả hai vai trò trừ khi policy cho phép và SoD vẫn đạt.

## 7. Một chiến dịch Access recertification gồm những gì?

**Certification campaign** là tập hợp review item được tạo để kiểm lại quyền đã cấp ở nhiều hệ thống.

~~~text
Campaign
  - campaignId, riskScope, policyVersion, deadline
  - reviewerAssignmentPolicy
  - ReviewItem A: person-101 / CRM_READ / tenant-a
  - ReviewItem B: person-102 / FINANCE_EXPORT / tenant-a
  - ReviewItem C: workload-77 / SECRET_READ / production
  - evidence + remediation + completion criteria
~~~

### 7.1. Cấu trúc review item

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **campaignId** | `recert-2026-q4` | Đợt rà soát |
| **reviewItemId** | `item-8472` | Định danh bất biến từng item |
| **beneficiaryIdentityId** | `person-1042` | Người đang có quyền |
| **relationshipId** | `employment-A-204` | Quan hệ cấp quyền |
| **targetAccountId** | `crm-acc-882` | Account ứng dụng đích |
| **resourceId** | `crm-customer-data` | Tài nguyên được rà soát |
| **entitlementId** | `CRM_EXPORT` | Quyền thực tế |
| **tenant/environment** | `tenant-a / production` | Giới hạn quyền |
| **observedAt** | Timestamp | Thời điểm đọc quyền tại đích |
| **originalReviewerId** | `person-501` | Người được định tuyến ban đầu |
| **currentReviewerId** | `person-608` | Người được chỉ định hiện hành |
| **assignmentVersion** | `3` | Phát hiện item đã được chuyển |
| **reviewStatus** | `PENDING` | Trạng thái quyết định |
| **decisionDeadline** | Timestamp | Hạn theo policy |
| **riskTier** | `HIGH` | Độ nhạy và số cấp review |
| **decisionId** | Khi quyết định | Truy vết kết quả |
| **remediationRef** | Khi REVOKE | Kết nối task thu hồi |

### 7.2. Snapshot có thể cũ

Quyền được chụp ở đầu campaign có thể đã bị thu hồi bởi Mover/Leaver trong lúc reviewer chưa quyết định. Một reviewer không nên chọn KEEP để **tái cấp một quyền không còn tồn tại** chỉ vì snapshot cũ hiển thị nó.

Khi thực thi kết quả, IGA phải đối chiếu **desired access và observed access hiện hành**. Đừng biến recertification thành quy trình vô ý tái provision.

## 8. Quyết định recertification và ý nghĩa

| Decision | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| **KEEP / CERTIFY** | Quyền còn cần trong scope đã xem | Ghi căn cứ và có thể đặt lần review sau |
| **REVOKE / REMOVE** | Quyền không còn hợp lệ hoặc cần thiết | Tạo revoke task, xác minh tại target |
| **MODIFY / REDUCE** | Quyền quá rộng, cần scope hẹp | Chuyển thành thay đổi entitlement có approval đúng |
| **REASSIGN** | Reviewer hiện tại không đủ thẩm quyền đánh giá | Chuyển item sang reviewer mới |
| **ESCALATE** | Cần chuyên gia/security quyết định | Định tuyến cấp có thẩm quyền |
| **UNDECIDED / EXCEPTION** | Chưa đủ dữ liệu hoặc reviewer | Chưa kết luận KEEP |
| **NO_LONGER_EXISTS** | Quyền snapshot không còn tại target | Xác minh trạng thái và đóng theo policy |

Các decision là **mô hình minh họa**, không phải tập giá trị tiêu chuẩn thống nhất của mọi IGA platform.

### 8.1. Quyết định KEEP không cấp quyền mới

KEEP chỉ chứng nhận một entitlement đã tồn tại **trong phạm vi được xem xét**. Nếu quyền đã bị gỡ do Leaver, reviewer không thể dùng KEEP để khôi phục quyền trái policy.

### 8.2. Quyết định REVOKE không đồng nghĩa đã thu hồi

Phải phân biệt:

~~~text
Reviewer decision = REVOKE
IGA remediation task = CREATED / SENT
Target entitlement = REMOVED (observed)
Effective authorization = DENIED
~~~

**Quyền vẫn có thể tồn dư** nếu SCIM/API lỗi, target còn local role, cloud credential hoặc session/token cũ. Chỉ đóng VERIFIED khi có bằng chứng đủ theo scope.

## 9. Quy trình chuyển reviewer theo mức hạt

Reviewer thay thế có thể nhận việc ở nhiều mức:

- **Một review item:** chuyển một quyền cụ thể vì SoD hoặc thiếu chuyên môn.
- **Một beneficiary:** chuyển mọi quyền của một người khi manager đổi.
- **Một resource/application:** chuyển toàn bộ các item do owner cũ sở hữu.
- **Một nhóm/tenant:** chuyển phạm vi nhóm có thẩm quyền.
- **Toàn campaign:** hiếm hơn, chỉ khi người thay đủ thẩm quyền và có kiểm soát.

### 9.1. Vì sao scope càng rộng càng rủi ro?

Chuyển **toàn campaign** từ data owners chuyên trách sang một IAM admin có thể làm mất yếu tố **người có hiểu biết nghiệp vụ**. Ngay cả khi IAM admin có quyền chỉnh workflow, họ không tự có quyền quyết định tất cả quyền truy cập.

Ưu tiên **reassign tối thiểu**: chỉ item liên quan, đúng resource, đúng tenant và đúng loại quyền.

### 9.2. Một reviewer có thể chỉ làm một phần

Với item đặc quyền, workflow có thể yêu cầu:

- Manager xác nhận nhu cầu công việc.
- Resource owner kiểm quyền trên hệ thống.
- Security rà SoD/điều kiện rủi ro.

Nếu một người nghỉ việc, **chỉ thay vai trò của người đó**, giữ những bước độc lập khác. Không sử dụng một substitute để tự nhận cả ba quyết định trừ khi policy cho phép rõ.

## 10. State machine của assignment và review item

Một workflow cần tách **trạng thái giao người review** và **trạng thái quyết định của item**.

~~~mermaid
stateDiagram-v2
    [*] --> ASSIGNED
    ASSIGNED --> PENDING_REVIEW: Campaign active
    PENDING_REVIEW --> REASSIGN_REQUESTED: Reviewer invalid / unavailable
    REASSIGN_REQUESTED --> AUTHORITY_CHECK: Resolve candidate
    AUTHORITY_CHECK --> REASSIGN_DENIED: Not authorized / SoD conflict
    AUTHORITY_CHECK --> REASSIGNED: Candidate eligible
    REASSIGNED --> PENDING_REVIEW: New assignment active
    PENDING_REVIEW --> DECIDED: Authorized reviewer decides
    PENDING_REVIEW --> ESCALATED: SLA reached
    ESCALATED --> AUTHORITY_CHECK: Resolve fallback
    DECIDED --> REMEDIATING: Decision requires revoke/modify
    DECIDED --> CLOSED: KEEP and validation complete
    REMEDIATING --> VERIFIED: Target confirms desired state
    REMEDIATING --> EXCEPTION: Target error or stale state
    VERIFIED --> CLOSED: Evidence stored
    REASSIGN_DENIED --> PENDING_REVIEW: Remains unresolved
    EXCEPTION --> REMEDIATING: Controlled retry
    CLOSED --> [*]
~~~

Sơ đồ là mô hình logic. Một số IGA engine có state khác; nguyên tắc là **không được ghi quyết định review hợp lệ khi assignment/authority chưa hợp lệ**.

### 10.1. Các invariant cần giữ

1. Một item chỉ có **một tập reviewer hợp lệ** theo loại review và policy ở một thời điểm; multi-review phải ghi vai trò rõ.
2. Reviewer cũ không được quyết định sau khi assignment đã chuyển và quyền cũ hết hiệu lực.
3. Quyết định không được **nhảy từ REASSIGN_REQUESTED sang KEEP**.
4. Reassignment không thay decision cũ một cách im lặng.
5. Item đã đóng không được reopen tùy tiện; cần quy trình appeal/re-review có audit.
6. Revoke task phải gắn với đúng **decisionId, entitlementId và observed target state**.
7. Timeout hoặc thiếu reviewer không đồng nghĩa KEEP.
8. Nếu dữ liệu policy/ownership không đủ, item vẫn unresolved hoặc escalation; không auto-certify.

## 11. Định tuyến reviewer thay thế an toàn

### 11.1. Thứ tự giải quyết gợi ý

1. **Current authoritative reviewer:** manager hoặc owner còn hiệu lực nếu policy chỉ yêu cầu làm mới assignment.
2. **Valid delegated reviewer:** người được ủy quyền đúng item/resource, thời hạn và risk tier.
3. **Configured fallback authority:** người/nhóm dự phòng được registry/policy chỉ định.
4. **Independent governance escalation:** nhóm bảo mật/IGA xử lý ownership hoặc SoD conflict.
5. **Unresolved/exception:** không tìm được reviewer phù hợp, giữ trạng thái chờ, không chứng nhận.

Đây là **ví dụ thứ tự**, không có precedence chuẩn bắt buộc. Một số quyền đặc quyền phải đưa **security reviewer** trước hoặc không cho manager delegation.

### 11.2. Resolver không dựa trên email do request gửi

~~~text
reviewerCandidate =
    authoritativeRegistry.resolve(
        item.resourceId,
        item.beneficiaryRelationship,
        item.entitlement,
        item.riskTier,
        item.tenantId,
        trustedNow
    )
~~~

**Không** nhận giá trị `newReviewerEmail` từ người bị review làm đủ căn cứ định tuyến. Hệ thống có thể cho đề xuất một người, nhưng phải **xác minh thẩm quyền ở server**.

### 11.3. Vấn đề “vòng ủy quyền”

A ủy quyền B, B ủy quyền C, C gửi lại A. Nếu không giới hạn chuỗi, reviewer có thể không còn biết ai chịu trách nhiệm và SoD có thể bị lách.

Cần quy định **độ sâu ủy quyền, quyền re-delegate, xử lý cycle, expiry và điều kiện thẩm quyền của delegator**. Cách an toàn thường là không cho ủy quyền tiếp nếu chính sách không cho phép.

## 12. Delegation tạm thời và reassignment chính thức

### 12.1. Delegation

**Delegation** thường có thời hạn, actor gốc vẫn có thể là accountable reviewer. Ví dụ manager đi nghỉ 7 ngày và ủy quyền chỉ các review item quyền read ít rủi ro.

~~~json
{
  "delegationId": "review-deleg-7001",
  "delegatorIdentityId": "person-501",
  "delegateIdentityId": "person-608",
  "allowedCampaignIds": ["recert-2026-q4"],
  "allowedResourceIds": ["crm-customer-data"],
  "allowedRiskTiers": ["LOW", "MEDIUM"],
  "validFrom": "2026-11-24T00:00:00+07:00",
  "validUntil": "2026-12-02T00:00:00+07:00",
  "status": "ACTIVE"
}
~~~

Đây là **JSON minh họa**, không phải schema chuẩn.

### 12.2. Reassignment

**Reassignment** thay người trực tiếp chịu trách nhiệm review item. Thường dùng khi owner/manager đổi hoặc reviewer cũ Leaver. Cần ghi **previousReviewer, newReviewer, reason, effectiveAt, assignmentVersion, actor/system thực hiện và chứng cứ thẩm quyền**.

### 12.3. Phân biệt lịch sử với hiện hành

Một item có thể từng qua:

~~~text
Campaign item-8472:
  Assigned to A at creation
  Delegated to B for absence
  B did not decide
  A became Leaver
  Reassigned to C as current resource owner
  C decided REVOKE
  Target confirmed removal
~~~

Lưu toàn bộ event; không chỉ ghi đè `reviewerId=C` rồi làm mất A/B và lý do thay đổi. **Lịch sử phân công là một phần bằng chứng của tính hợp lệ của decision.**

## 13. IdP/SSO và kiểm thẩm quyền người thay thế

Một reviewer thay thế phải được xác thực như một người dùng có trách nhiệm trong workflow.

- **IdP/SSO** chứng minh principal, có thể yêu cầu MFA/step-up theo mức rủi ro.
- IGA liên kết `issuer + subject` với **identityId** và quan hệ làm việc đáng tin.
- **PBAC/RBAC/ABAC** đánh giá permission `review.decision` trên review item.
- **PEP** ở backend kiểm policy tại thời điểm nhấn KEEP/REVOKE.
- Dữ liệu owner/delegation lấy từ registry hoặc API được bảo vệ.
- Audit ghi **actor thực**, không giả lập reviewer ban đầu là người đã quyết định.

### 13.1. Email deep link không tự là thẩm quyền

Email nhắc có thể dẫn tới review portal. Link bị chuyển tiếp không được cho phép người nhận khác ra quyết định chỉ vì biết URL.

Cần **authentication ở server, anti-CSRF/replay protection, session đúng audience và authorization đối với reviewItemId**.

### 13.2. Không cho thay reviewer bằng sửa payload

Ví dụ request không an toàn:

~~~json
{
  "reviewItemId": "item-8472",
  "newReviewerIdentityId": "requester-self",
  "reason": "urgent",
  "approveImmediately": true
}
~~~

Backend không được tin người gửi có quyền đổi reviewer hoặc KEEP ngay. Cần API riêng cho **request substitution**, kiểm actor được phép thực hiện reassignment, kiểm candidate và state trước khi cập nhật.

## 14. Chính sách SoD và chống self-certification

**Segregation of Duties (SoD)** ngăn các kết hợp vai trò tạo xung đột lợi ích.

### 14.1. Các xung đột điển hình

| Tình huống | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Reviewer = beneficiary | Người giữ quyền tự chứng nhận | Reviewer độc lập |
| Reviewer là người đã cấp quyền sai trước đó | Có động cơ che lỗi | Independent second review khi policy yêu cầu |
| Delegate thuộc nhóm hưởng cùng entitlement đặc quyền | Xung đột lợi ích | SoD review |
| Manager mới không quản lý người đó tại thời điểm review | Quyết định không đúng thẩm quyền | HRIS current manager check |
| Owner của resource đã Leaver | Quyền owner không còn | Registry update/reassignment |
| Reviewer có quyền sửa owner registry | Tự nâng thẩm quyền | Governance SoD, audit thay owner |
| Một người duyệt cả need-to-know và security exception | Thiếu kiểm soát độc lập | Dual approval/role separation |
| Reviewer cố chuyển sang đồng nghiệp “dễ duyệt” | Approval shopping | Restrict candidate source và reason |
| Reviewer xóa audit/chỉnh decision của mình | Không thể truy vết | Immutable audit và quyền tách biệt |

### 14.2. Thế nào là self-review?

Không chỉ khi `reviewerIdentityId == beneficiaryIdentityId`. Với một số hệ thống, còn cần xem reviewer:

- Là **owner của service account** và cũng hưởng lợi từ quyền đó.
- Có thể sửa dữ liệu nguồn làm role hợp lệ.
- Là người quản trị chính tài khoản shared admin nhưng tự chứng nhận không độc lập.
- Có mối quan hệ đặc biệt cần kiểm soát theo policy.

**SoD phụ thuộc mức rủi ro và quy tắc tổ chức**. Không mặc định mọi self-review đều bị cấm giống nhau, nhưng những quyền đặc quyền phải có kiểm soát độc lập tương xứng.

### 14.3. Không giải quyết SoD bằng cách đổi tên account

Nếu người dùng có hai account (corporate và privileged), so sánh username khác nhau không phát hiện self-review. Cần liên kết chúng về cùng **identityId** hoặc quan hệ principal được quản trị.

## 15. Reviewer thay thế được thấy gì?

Reviewer cần **đủ ngữ cảnh để quyết định**, nhưng không phải được xem mọi dữ liệu của campaign hoặc tenant.

Một review UI nên hiển thị theo scope:

- Beneficiary, department, employment status, manager hiện hành.
- Resource/application, permission/role, tenant, environment, classification.
- Business justification/owner, lần cấp đầu, lần dùng gần nhất nếu dữ liệu đáng tin.
- Kỳ hạn quyền, dự án/hợp đồng liên quan, SoD flags.
- Decision ở lần review trước và lý do (nếu policy cho phép truy cập).
- Thông tin reviewer assignment, cơ sở substitution và expiry.
- Nút KEEP, REVOKE, REDUCE, ESCALATE tùy quyền và trạng thái.

**Last-used=never không chứng minh quyền không cần thiết**; có quyền khẩn cấp hoặc dự phòng ít dùng nhưng vẫn hợp lệ. Tương tự, việc dùng thường xuyên không tự chứng minh cần giữ quyền nếu vi phạm SoD hay security policy.

### 15.1. Tách dữ liệu nhạy cảm trong UI

Reviewer được cấp quyền đánh giá quyền truy cập một dataset **không mặc nhiên được xem dữ liệu đầy đủ trong dataset**. Cần hạn chế PII, chỉ dùng metadata cần thiết và có audit việc reviewer xem dữ liệu review.

### 15.2. Quyền xem khác quyền quyết định

Một investigator có thể được xem evidence nhưng không được KEEP/REVOKE. Một substitute có thể chỉ được đọc item thuộc một tenant, không được bulk-review quyền của người khác.

## 16. SLA, hạn review và escalation

Một campaign có thể có các mốc:

| Mốc | Ý nghĩa |
| --- | --- |
| **campaignStartAt** | Bắt đầu review |
| **reviewDueAt** | Hạn của item/nhóm |
| **reminderAt** | Mốc nhắc reviewer |
| **escalationAt** | Mốc chuyển tới authority dự phòng theo policy |
| **reassignmentEffectiveAt** | Thời điểm reviewer mới được nhận quyền |
| **decisionAt** | Thời điểm decision được đưa ra |
| **remediationDueAt** | Hạn gỡ quyền sau REVOKE |
| **verifiedAt** | Thời điểm target được xác minh |
| **campaignCloseAt** | Kết thúc đợt sau khi kiểm ngoại lệ |

### 16.1. Timeout không phải KEEP

Một sai lầm nghiêm trọng là tự coi item chưa được duyệt tới hạn thành **KEEP** vì muốn báo cáo 100% hoàn thành. Nếu có auto-certification cho quyền thấp rủi ro, phải là **policy đã được chủ sở hữu phê duyệt trước**, có scope/risk và audit rõ.

Với quyền đặc quyền/nhạy cảm, overdue có thể dẫn tới **escalation, suspension hoặc revoke theo policy**, chứ không tự cấp quyền.

### 16.2. Reviewer thay thế không được làm mất mốc SLA

Khi reassign, hệ thống cần quyết định **giữ hạn cũ hay cấp thời gian mới** theo risk. Không cho lặp thao tác reassign để tự động gia hạn vô hạn một quyền chưa được xem xét.

### 16.3. Deadline và timezone

Dùng timestamp có timezone, lịch ngày làm việc nếu cần và đồng hồ tin cậy. Đừng đánh giá reviewer đã trễ dựa vào `Date.now` ở trình duyệt hoặc timezone đoán từ tên bộ phận.

## 17. Reviewer thay thế khi reviewer ban đầu là Mover

**Mover** có thể thay bộ phận, manager, owner của ứng dụng hoặc phạm vi quản lý. Reviewer cũ vẫn ACTIVE nhưng không còn đủ thẩm quyền quyết định quyền của nhân viên/tài nguyên cũ.

### 17.1. Tình huống manager chuyển bộ phận

~~~text
Ngày 01/11:
  Manager A quản lý employee-1042
  Campaign tạo review item CRM_READ -> reviewer A

Ngày 15/11:
  HRIS cập nhật manager của employee-1042 thành B
  Reviewer A vẫn ACTIVE nhưng không còn quản lý employee-1042

Ngày 20/11:
  A mở link từ email cũ để chọn KEEP
~~~

Workflow phải **kiểm current manager authority ở thời điểm quyết định**; nếu A không còn đủ quyền, từ chối thao tác và chuyển item cho B hoặc fallback theo policy.

### 17.2. Không chỉ thay trường reviewerId

Khi chuyển reviewer:

1. Xác nhận HRIS event/ownership change đã có hiệu lực.
2. Xác định những item nào thực sự bị ảnh hưởng.
3. Kiểm người thay thuộc đúng loại reviewer (manager, owner, security).
4. Đánh giá SoD/self-certification.
5. Đặt assignment mới có version và thời điểm hiệu lực.
6. Thu hồi khả năng quyết định của reviewer cũ trên item đã chuyển.
7. Thông báo an toàn cho reviewer mới, tránh lộ dữ liệu.
8. Ghi audit lý do, nguồn sự kiện, phạm vi và deadline.
9. Đảm bảo quyết định cũ đã hợp lệ không bị thay đổi lịch sử.

### 17.3. Quyền còn tồn tại sau Mover của beneficiary

Nếu chính **người giữ quyền** Mover, item có thể cần re-evaluate ngay, không chờ kết thúc campaign. Quyền của bộ phận cũ có thể phải thu hồi. Reviewer thay thế không được chọn KEEP trên snapshot quyền đã mất căn cứ công việc.

**Mover của reviewer** liên quan đến *thẩm quyền ra quyết định*; **Mover của beneficiary** liên quan đến *tính hợp lệ của entitlement*. Hai sự kiện khác nhau và cần xử lý riêng.

## 18. Reviewer thay thế khi reviewer Leaver

Khi reviewer nghỉ việc, quyền đăng nhập và quyền quyết định cần được xử lý theo **Leaver lifecycle**, không chờ người đó hoàn tất những item còn lại.

### 18.1. Chuỗi xử lý gợi ý

~~~mermaid
flowchart TD
    H["HRIS: reviewer Leaver effectiveAt"] --> I["IGA: xác định reviewer assignments"]
    I --> R["Thu hồi quyền reviewer theo scope"]
    I --> C["Kiểm pending review items"]
    C --> V{"Giải quyết owner/manager mới?"}
    V -->|"Có"| S["Validate candidate, SoD, delegation"]
    V -->|"Không"| E["OWNER_UNRESOLVED / escalation"]
    S --> A["Reassign từng item + assignmentVersion"]
    A --> N["Thông báo reviewer mới"]
    N --> D["Review decision được xác thực"]
    D --> X["Remediation + readback"]
    R --> AUD["Audit/reconciliation"]
    E --> AUD
    A --> AUD
    X --> AUD
~~~

### 18.2. Quyền cũ và phiên cũ

- IdP vô hiệu hóa login mới nhưng local IGA session có thể còn thời gian.
- Role `CERTIFICATION_REVIEWER` có thể vẫn tồn tại ở ứng dụng.
- Email thông báo cũ vẫn chứa link item.
- Token/session đã phát trước sự kiện Leaver có thể chưa hết hạn.

PEP của review API phải kiểm **thẩm quyền hiện hành trên reviewItemId**, không chỉ xem một claim reviewer ở token cũ.

### 18.3. Quyết định đã đưa ra trước Leaver

Nếu reviewer A chọn KEEP hợp lệ **trước effectiveAt**, không tự sửa audit thành reviewer B khi A nghỉ việc. Có thể cần **re-review** nếu policy hoặc dữ liệu quyền thay đổi, nhưng phải tạo decision/event mới, bảo tồn lịch sử.

Nếu reviewer A chọn KEEP **sau khi mất thẩm quyền**, decision phải được xử lý như **unauthorized/stale**, không tự ghi nhận hợp lệ chỉ vì API trả HTTP 200.

## 19. Joiner và onboarding reviewer mới

Một reviewer thay thế cũng có vòng đời danh tính riêng. Người mới được bổ nhiệm resource owner chưa chắc đã hoàn thành onboarding và training về quyền cần đánh giá.

### 19.1. Điều kiện đưa reviewer mới vào workflow

- Identity đã được xác minh và liên kết đúng.
- Quan hệ làm việc/hợp đồng còn ACTIVE.
- Registry xác nhận owner/manager hoặc delegation có hiệu lực.
- Có quyền truy cập công cụ recertification nhưng không có quyền quá rộng.
- Được cung cấp metadata đủ để review (purpose, data classification, entitlement).
- Có training hoặc hướng dẫn nghiệp vụ khi policy yêu cầu.
- Biết xử lý KEEP, REVOKE, ESCALATE và UNKNOWN.
- Có cách truy cập case hỗ trợ khi thiếu thông tin.
- Được xác thực đủ mức cho quyết định nhạy cảm.

### 19.2. Preboarding và quyền reviewer

Tạo account IGA trước ngày nhận việc không đồng nghĩa người đó được quyết định quyền của người khác trước `effectiveAt`. Một reviewer đang preboarding chỉ nên được phân công quyền hoạt động sau khi đủ điều kiện, hoặc dùng fallback khác.

### 19.3. Reviewer onboarding không đồng nghĩa cấp quyền tới tài nguyên

Reviewer có thể xem **metadata của quyền** để đánh giá nhưng **không tự được truy cập nội dung dữ liệu** hoặc nhận cùng role như người đang được review. Tránh cấp thêm entitlement nhạy cảm chỉ để reviewer làm nhiệm vụ.

## 20. Reviewer thay thế và vòng đời của người bị review

Trong chiến dịch, beneficiary có thể **Joiner, Mover, Leaver, bị security block, hết hợp đồng hoặc được rehire**.

### 20.1. Review item không phải bản sao vĩnh viễn của quyền

Ví dụ:

~~~text
01/11  CRM_READ được chụp trong campaign
08/11  Beneficiary Mover khỏi CRM, IGA tạo revoke
10/11  SCIM gỡ CRM_READ
12/11  Item vẫn pending trong inbox reviewer
14/11  Reviewer mới mở item và chọn KEEP
~~~

Nếu IGA dùng KEEP để tái cấp quyền, đó là lỗi thiết kế. **Recertification không tự cấp lại entitlement** khi observed state đã thay đổi vì một sự kiện vòng đời hợp lệ.

### 20.2. Leaver trong khi chờ review

Một entitlement của Leaver phải được xử lý theo chính sách offboarding; không chờ reviewer chọn REVOKE. Review item có thể được đánh dấu **NO_LONGER_APPLICABLE / AUTO_REVOKE_PENDING** và audit theo ngữ nghĩa hệ thống, nhưng **không được biến quyền đã hết hiệu lực thành KEEP**.

### 20.3. Rehire

Một người được tái tuyển dụng có thể dùng lại identity liên kết nhưng employment relationship mới. Approval/review của quan hệ cũ không tự chuyển sang quan hệ mới. IAM phải tính entitlement từ trạng thái hiện hành và quyền được duyệt theo công việc mới.

## 21. Reviewer dự phòng cho tài nguyên và dữ liệu nhạy cảm

Các quyền cần chuyên môn có thể không phù hợp để manager hoặc IAM operator chung xem xét.

| Entitlement | Reviewer ưu tiên | Fallback / bổ sung |
| --- | --- | --- |
| Quyền đọc CRM theo nhóm | Manager hoặc CRM owner tùy policy | Manager cấp trên/CRM steward hợp lệ |
| Export dữ liệu khách hàng | Data owner có trách nhiệm | Data governance + security |
| Quyền sửa dữ liệu tài chính | Business/data owner | Finance risk/SoD reviewer |
| Cloud organization admin | Cloud platform owner | PAM/security reviewer độc lập |
| IAM role.grant | IAM resource owner và security | Privileged governance authority |
| Secret read/manage | Secret owner | Secrets platform/security |
| Production DB admin | Database owner | DBA lead và security theo policy |
| Quyền cross-tenant | Owner từng tenant / bên quản trị dữ liệu | Escalation đa bên, không auto KEEP |

### 21.1. Không đủ thẩm quyền là lý do ESCALATE

Một reviewer thay thế có thể hiểu người dùng cần truy cập nhưng không biết dữ liệu có thể chia sẻ giữa hai pháp nhân hay không. Họ nên **ESCALATE** đến người có năng lực và thẩm quyền phù hợp, thay vì chọn KEEP để hoàn thành KPI.

### 21.2. Multi-party review

Với tài nguyên rủi ro cao, workflow có thể cần **hai quyết định độc lập**:

~~~text
Need-to-know review: Manager
Resource classification review: Data Owner
Security/SoD exception: Security Reviewer (nếu phát sinh)
~~~

Nếu manager đi nghỉ, reviewer thay thế chỉ thực hiện **bước manager**, không tự hoàn tất bước data owner hay security.

## 22. Reviewer thay thế cho service account và workload

**Service account, bot, pipeline CI/CD, managed identity** có thể có quyền rất lớn nhưng không có line manager theo cách của nhân viên.

### 22.1. Cách chọn reviewer cho workload

- **Workload owner/team:** xác nhận service còn hoạt động và cần permission.
- **Resource owner:** đánh giá API, secret, database hoặc cloud resource được dùng.
- **Security/PAM:** rà privileged scopes, credential lifetime và SoD.
- **Platform owner:** kiểm cấu hình hạ tầng và vòng đời workload.

Nếu workload owner Mover/Leaver, không nên tự gán reviewer sang một admin bất kỳ. Cần xác minh **owner team hoặc người bảo trợ mới**.

### 22.2. Những thông tin reviewer cần biết

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **workloadPrincipalId** | `pipeline-prod-deploy` | Principal thực tế |
| **workloadOwner** | `platform-team` | Bên chịu trách nhiệm |
| **resource / scope** | `cluster-prod:deploy.write` | Quyền cần đánh giá |
| **environment** | `production` | Độ nhạy |
| **credentialType / expiry** | Federation / short-lived | Rủi ro credential tồn dư |
| **lastExecutionAt** | Timestamp đáng tin | Nhu cầu vận hành |
| **projectStatus** | ACTIVE / RETIRED | Căn cứ giữ quyền |
| **approvalRef** | Workload/resource owner record | Thẩm quyền |
| **rotation/revocation** | Task và outcome | Bằng chứng xử lý |

### 22.3. Không tắt nhầm workload production

Nếu reviewer không biết workload dùng làm gì, **ESCALATE** đến owner kỹ thuật trước khi quyết định thu hồi quyền gây gián đoạn. Nhưng không vì sợ ảnh hưởng mà mặc định KEEP vô hạn. Dùng quy trình đánh giá rủi ro, thời hạn và giám sát.

### 22.4. Tài khoản mồ côi

Một service principal không còn owner hoặc ứng dụng đã nghỉ có thể là **orphaned identity**. Recertification phải tìm owner, đánh giá purpose và thu hồi quyền không còn cần sau khi xác minh tác động, thay vì tự duyệt vì không ai phản hồi.

## 23. Thay reviewer trong một chiến dịch nhiều tenant

Nếu tập quyền bao gồm nhiều tenant/pháp nhân, reviewer A có thể có authority trên tenant-a nhưng không trên tenant-b.

~~~text
review item 1: CRM_READ / tenant-a
review item 2: CRM_READ / tenant-b

candidate reviewer: owner tenant-a

Kết quả:
  item 1 -> có thể được giao nếu đủ điều kiện
  item 2 -> không được tự chuyển theo item 1
~~~

### 23.1. Chặn cross-tenant assignment

- Resource/tenant context từ registry đáng tin, không lấy từ header client.
- Mỗi item gắn exact `tenantId, resourceId, entitlementId`.
- Resolver kiểm quyền ở tenant đúng.
- Backend PEP bảo vệ cả xem review metadata lẫn ra quyết định.
- Query phải lọc tenant/resource scope, tránh đưa toàn chiến dịch cho một reviewer.
- Bulk reassignment phải đánh giá từng item.

### 23.2. Chính sách khác nhau giữa pháp nhân

Một pháp nhân có thể cần data owner, trong khi pháp nhân khác cho manager review. Không áp một fallback reviewer chung mà bỏ qua các yêu cầu pháp lý/tổ chức cụ thể; lưu **policy version và jurisdiction/scope** phù hợp.

## 24. Mẫu API và policy backend cho reassignment

Các ví dụ sau là **mã giả để giải thích**. Chúng không phải API tiêu chuẩn của IGA nào và cần bổ sung xử lý transaction, session, errors, event và audit khi triển khai thật.

### 24.1. Contract đề nghị thay reviewer

~~~json
{
  "campaignId": "recert-2026-q4",
  "reviewItemIds": ["item-8472"],
  "requestedCandidateIdentityId": "person-608",
  "reasonCode": "PRIMARY_REVIEWER_LEAVER",
  "justification": "manager transition",
  "expectedAssignmentVersion": 2
}
~~~

Đây là dữ liệu **đầu vào đề nghị**, không phải quyền hợp lệ. Backend phải kiểm **requester có quyền yêu cầu reassignment**, candidate có thẩm quyền thật và item vẫn ở trạng thái cho phép chuyển.

### 24.2. Thuật toán định tuyến mẫu

~~~text
resolveSubstitute(item, trustedContext):
    require item.campaign.status == ACTIVE
    require item.reviewStatus == PENDING
    require item.resource.isManaged()
    require item.identityLinkIsVerified()

    candidates = trustedRegistry.findAuthorizedReviewers(
        resourceId = item.resourceId,
        entitlementId = item.entitlementId,
        tenantId = item.tenantId,
        relationshipId = item.beneficiaryRelationshipId,
        reviewRole = item.requiredReviewerRole,
        at = trustedNow()
    )

    candidates = filter candidates WHERE
        candidate.active
        AND candidate.authorityValid
        AND candidate.authorityScopeMatches(item)
        AND NOT candidate.securityBlocked
        AND NOT sod.conflicts(candidate, item.beneficiary)

    IF candidates is empty:
        return OWNER_UNRESOLVED

    return chooseAccordingToApprovedRoutingPolicy(candidates)
~~~

**Không** thêm fallback cuối cùng là `return campaignCreator`, vì người tạo campaign không mặc nhiên có authority trên tất cả tài nguyên.

### 24.3. Mẫu Java/Spring pseudocode

~~~java
// Kiểu dữ liệu và service minh họa, không phải mã có thể build ngay.
@Service
class ReviewReassignmentService {

    private final ReviewItemRepository items;
    private final ReviewerAuthorityService authority;
    private final SodPolicy sod;
    private final ReviewEventOutbox outbox;

    @Transactional
    public ReassignmentResult reassign(
            AuthenticatedActor actor,
            String reviewItemId,
            String candidateIdentityId,
            long expectedVersion,
            String reasonCode) {

        ReviewItem item = items.findForUpdate(reviewItemId);

        if (!item.isPending() || item.assignmentVersion() != expectedVersion) {
            return ReassignmentResult.denied("STALE_ITEM_OR_VERSION");
        }

        if (!authority.mayInitiateTransfer(actor, item)) {
            return ReassignmentResult.denied("TRANSFER_NOT_AUTHORIZED");
        }

        if (!authority.mayReview(candidateIdentityId, item)
                || sod.conflicts(candidateIdentityId, item)) {
            return ReassignmentResult.denied("CANDIDATE_NOT_ELIGIBLE");
        }

        item.transferTo(candidateIdentityId, reasonCode);
        items.save(item);
        outbox.appendReviewerTransferred(item.id(), item.assignmentVersion());

        return ReassignmentResult.accepted(item.id());
    }
}
~~~

**Các class, method và injection là mô hình hướng dẫn.** Khi triển khai:

- Dùng `authenticatedActor` từ security context, không tin actorId gửi trong body.
- `findForUpdate` hoặc optimistic concurrency phải phù hợp database.
- Ghi chuyển assignment và outbox event **nguyên tử** trong transaction.
- Không gửi email/SCIM trực tiếp trong transaction DB theo cách gây lặp side effect.
- PEP của endpoint `decideReviewItem` phải **kiểm lại quyền reviewer hiện hành**, ngay cả nếu front-end đã chuyển.
- Kiểm SoD và tenant/authority từ server; không chỉ kiểm cùng username.
- Không để actor tự đổi review item khác rồi tiếp tục dùng quyền cũ.

## 25. Concurrency, idempotency và replay

### 25.1. Race khi reviewer cũ cùng reviewer mới quyết định

~~~text
10:00:00  Reviewer A mở item ở phiên cũ
10:00:01  Campaign manager reassign item từ A sang B
10:00:02  Reviewer B mở item, quyền hợp lệ
10:00:03  Reviewer A bấm KEEP trên UI cũ
10:00:04  Reviewer B bấm REVOKE
~~~

Nếu backend chỉ kiểm user đã từng là reviewer, cả hai decision có thể được ghi, tạo mâu thuẫn. Cần:

- **Assignment version** trong request/decision.
- Check current authority tại thời điểm commit.
- Atomic compare-and-set của item status/version.
- Quy tắc xử lý conflict và audit.
- Yêu cầu refresh UI khi assignment thay đổi.
- Không để quyết định cũ tạo/recreate entitlement ngoài desired state.

### 25.2. Idempotency

Retry gửi decision có thể xảy ra vì mạng timeout. Cần idempotency key gắn với **actor, item, assignmentVersion, decision payload**.

Nếu cùng request được gửi hai lần, chỉ một lần có effect. Nhưng **idempotency không thay thế authorization**: một event REVOKE cũ gửi lại sau khi item được reopen theo quy trình vẫn phải kiểm state mới.

### 25.3. Approval shopping và decision replay

Nếu reviewer A đã REVOKE theo policy, việc chuyển item sang reviewer B để lấy KEEP phải qua **appeal/re-review có thẩm quyền**, không coi đó là reassignment thường.

Phải giữ decision cũ, lý do tranh chấp, người phê chuẩn reopen và liên kết phiên bản. Không xóa lịch sử rồi cho phép một quyết định mới trông như quyết định đầu tiên.

## 26. Thu hồi quyền sau quyết định của reviewer thay thế

Reviewer thay thế có thể chọn REVOKE một entitlement đã tồn tại. Công việc tiếp theo thuộc **remediation workflow**, không tự kết thúc tại nút quyết định.

### 26.1. Luồng REVOKE

~~~mermaid
sequenceDiagram
    autonumber
    actor R as Substitute reviewer
    participant IGA as Review/IGA
    participant PDP as Authorization policy
    participant CON as SCIM/API connector
    participant TARGET as Target application
    participant AUD as Audit/Reconciliation

    R->>IGA: REVOKE reviewItemId + assignmentVersion
    IGA->>PDP: Kiểm actor, SoD, scope, state
    PDP-->>IGA: Decision hợp lệ
    IGA->>IGA: Lưu decision và remediation task
    IGA->>CON: Remove entitlement từ đúng account
    CON->>TARGET: Revoke group/role/account theo scope
    TARGET-->>CON: Result
    CON-->>IGA: Applied / failed / unknown
    IGA->>TARGET: Read observed entitlement
    TARGET-->>IGA: Observed state
    IGA->>AUD: Decision + actual outcome + exception
~~~

### 26.2. Decision REVOKE khác quyền đã hết

~~~text
REVIEW_DECISION = REVOKE
REMEDIATION_TASK = SENT
TARGET_ROLE = STILL_PRESENT
ACCESS_TOKEN = STILL_VALID
PEP_DECISION = PERMIT (if only stale role checked)
~~~

Điều này cho thấy **quyền truy cập tồn dư**. Cần follow-up theo mức rủi ro: gỡ role, session/token invalidation khi hỗ trợ, current-state policy và kiểm target API.

### 26.3. Revoke có thể cần kiểm tác động

Với workload production hoặc tài khoản break-glass, quyết định REMOVE nên kích hoạt **change control có trách nhiệm**, nhưng không để quyền nguy hiểm tồn tại vô thời hạn. Có thể giảm scope, tạm chặn hành động đặc quyền, theo dõi exception và xác định mốc hoàn tất có owner.

## 27. Tích hợp IdP/SSO, SCIM, RBAC/ABAC và PBAC

### 27.1. Không trộn nhiệm vụ các thành phần

| Thành phần | Liên hệ với reviewer thay thế | Không tự đảm bảo |
| --- | --- | --- |
| **HRIS/identity registry** | Trạng thái, manager, quan hệ làm việc | Reviewer có authority tài nguyên nếu chưa có registry |
| **IdP/SSO** | Xác thực reviewer, MFA/step-up | Quyền recertify một item |
| **IGA campaign** | Tạo item, routing, quyết định và remediation | Target đã thực thi revoke |
| **Ownership/delegation registry** | Thẩm quyền owner/manager/delegate | App token/session đã hết quyền |
| **RBAC** | Role REVIEWER/CERTIFICATION_ADMIN có phạm vi | Tự đảm bảo không self-review |
| **ABAC/PBAC** | Policy xét identity, item, tenant, thời gian, risk | Thực thi quyền nếu API bỏ qua PEP |
| **SCIM/API/Directory** | Gỡ/cấp entitlement tại target | Quyền runtime đã chặn tức thì |
| **PAM/cloud control plane** | Phiên đặc quyền, JIT grant và resource policies | Recertification tự xử lý mọi credential |
| **Reconciliation/audit** | Đối soát quyết định và target outcome | Tự chặn truy cập khi PEP còn cho phép |

### 27.2. Policy enforcement ở backend

Khi reviewer nhấn KEEP, endpoint phải kiểm:

~~~text
canDecideReview(actor, item) =
    authenticated(actor)
    AND actor.lifecycle == ACTIVE
    AND actor.currentReviewAuthority(item)
    AND item.assignmentVersion == request.expectedVersion
    AND item.status == PENDING
    AND NOT sod.conflict(actor, item)
    AND item.tenant == actor.authorizedTenantScope
    AND policy.isActiveAt(decisionTime)
~~~

Đây là mã giả. **Không tin client gửi `reviewer=manager` hoặc `decision=KEEP` để tự mở quyền**. Kiểm trên backend ở từng request.

### 27.3. Tác động đến token và phiên

Một reviewer bị Leaver có thể còn access token hợp lệ về chữ ký, nhưng API phải chặn nếu không còn thẩm quyền. Một beneficiary có REVOKE đã được duyệt có thể còn token mang role cũ; PEP tại resource nên có chiến lược **current entitlement check, revoke/introspection/TTL, session invalidation** theo rủi ro và khả năng nền tảng.

## 28. Audit, chuỗi chứng cứ và quyền riêng tư

Mỗi thay reviewer cần **lý do, thẩm quyền, người thực hiện, trạng thái trước/sau, item scope và thời điểm**.

### 28.1. Event mẫu cho reviewer transfer

~~~json
{
  "eventType": "REVIEWER_REASSIGNED",
  "campaignId": "recert-2026-q4",
  "reviewItemId": "item-8472",
  "previousReviewerIdentityId": "person-501",
  "newReviewerIdentityId": "person-608",
  "initiatedByIdentityId": "iga-governance-operator",
  "reasonCode": "PRIMARY_REVIEWER_MOVER",
  "authoritySource": "resource-owner-registry",
  "authorityVersion": 12,
  "approvalRef": "reassign-approval-120",
  "assignmentVersionBefore": 2,
  "assignmentVersionAfter": 3,
  "policyVersion": "recert-routing-v4",
  "occurredAt": "2026-11-23T10:00:00+07:00"
}
~~~

Đây là **JSON minh họa**, không phải schema tiêu chuẩn của mọi IGA sản phẩm.

### 28.2. Event mẫu cho decision

~~~json
{
  "eventType": "ACCESS_RECERTIFICATION_DECISION",
  "campaignId": "recert-2026-q4",
  "reviewItemId": "item-8472",
  "beneficiaryIdentityId": "person-1042",
  "actorReviewerIdentityId": "person-608",
  "originalReviewerIdentityId": "person-501",
  "reassignmentRef": "reassign-120",
  "assignmentVersion": 3,
  "entitlementId": "CRM_EXPORT",
  "resourceId": "crm-customer-data",
  "tenantId": "tenant-a",
  "decision": "REVOKE",
  "reasonCode": "NO_LONGER_REQUIRED",
  "decisionAt": "2026-11-23T10:15:00+07:00",
  "remediationTaskId": "revoke-task-2882"
}
~~~

### 28.3. Giữ chuỗi thời gian và authority

Một điều tra cần chứng minh:

1. Ai được giao ban đầu, theo policy nào?
2. Vì sao phải thay reviewer?
3. Ai và theo thẩm quyền nào được phép đổi?
4. Reviewer mới có đủ quyền và không có SoD conflict lúc ra quyết định không?
5. Decision nào được ghi, trên entitlement/resource nào?
6. Target đã thực thi quyết định ra sao?
7. Nếu quyền tồn dư, exception được xử lý lúc nào?

Không lưu raw ID/access/refresh token, session cookie, mật khẩu, OTP, private key hoặc dữ liệu không cần thiết vào audit. PII cần retention và phân quyền phù hợp.

### 28.4. Không ghi đè actor

Nếu manager A là reviewer ban đầu nhưng B được ủy quyền và trực tiếp chọn REVOKE, **actorReviewerIdentityId phải là B**. Giữ A ở trường original/delegator nếu cần; không gán decision cho A để trông như không có thay thế.

## 29. Reconciliation và kiểm soát quyền tồn dư

**Reconciliation** so sánh quyền mong muốn, quyền đích và bằng chứng thực thi.

| Review decision / desired state | Observed state | Kết luận |
| --- | --- | --- |
| KEEP hợp lệ | Quyền đúng scope, chủ thể ACTIVE | MATCH theo scope |
| REVOKE | Role còn trên SaaS | RESIDUAL_ACCESS |
| REVOKE | Role đã gỡ nhưng session đặc quyền còn | SESSION_RESIDUAL |
| KEEP từ reviewer không thẩm quyền | Quyền còn | INVALID_DECISION cần xử lý |
| Item PENDING đã quá hạn | Quyền vẫn tồn tại | OVERDUE_RISK, không tự KEEP |
| Beneficiary Leaver | Account SaaS ACTIVE | LIFECYCLE_VIOLATION |
| Service owner không xác định | Service principal còn role admin | OWNER_GAP |
| Target không phản hồi | Không xác minh quyền thực tế | UNKNOWN, không PASS |
| Reviewer cũ vẫn có decision privilege | API cho quyền trên item đã chuyển | REVIEWER_AUTHORITY_DRIFT |

### 29.1. Khi nào đóng item và campaign?

- Quyết định được đưa bởi actor đủ thẩm quyền.
- Nếu REVOKE/MODIFY, remediation có bằng chứng hoặc exception có owner theo tiêu chí campaign.
- SoD, lifecycle và phạm vi đúng.
- Mọi item chưa kết luận được ghi rõ, không ép thành KEEP.
- Audit lưu được assignment, quyết định và các trạng thái đích.
- Những quyền đặc quyền/quyền tồn dư được xử lý theo rủi ro.

Một campaign có thể kết thúc nghiệp vụ với **exception đã được chấp thuận và theo dõi**, nhưng không nên báo “100% quyền đã được xác minh an toàn” khi các quyền còn UNKNOWN/RESIDUAL.

## 30. KPI của reviewer thay thế

| Chỉ số | Ý nghĩa | Điều cần tránh |
| --- | --- | --- |
| **Reassignment rate** | Tỷ lệ item đổi reviewer | Không mặc định càng thấp càng tốt |
| **Correct substitute authority rate** | Reviewer thay có authority xác minh được | Chỉ đếm trạng thái chuyển thành công |
| **Reassignment latency** | Thời gian từ nguyên nhân tới assignment hợp lệ | Để review treo sau Leaver |
| **Owner-unresolved count** | Item không xác minh được owner | Auto-approve để xóa backlog |
| **Self-review blocked** | Trường hợp SoD chặn đúng | Không nhìn beneficiary identity link |
| **Stale reviewer decision attempts** | Reviewer cũ cố quyết định sau reassignment | Cần PEP/caching fix |
| **Overdue unreviewed items** | Review quá hạn mà chưa có quyết định | Gộp UNKNOWN thành KEEP |
| **Decision reversal/appeal rate** | Số decision bị tranh chấp | Xóa lịch sử decision cũ |
| **Reviewer workload distribution** | Tập item theo reviewer và risk | Bulk assign quá nhiều quyền nhạy cảm |
| **REVOKE-to-verified latency** | Từ quyết định tới quyền thực sự bị gỡ | Chỉ đo thời gian connector nhận lệnh |
| **Leaver reviewer reassignment coverage** | Tỷ lệ task của reviewer Leaver được xử lý | Đếm tài khoản IdP disabled là hoàn tất |
| **Audit evidence completeness** | Có đủ actor, reason, owner, policy, outcome | Ghi quá nhiều PII/secrets |
| **Privileged entitlement residual count** | Quyền đặc biệt còn sau REVOKE | Chỉ nhìn quyết định trên portal |
| **Workload ownership coverage** | Service accounts có reviewer phù hợp | Dồn tất cả cho IAM admin |

KPI nên có **mẫu số rõ** và phân loại theo rủi ro, không chỉ đo số lần reviewer mới bấm KEEP.

## 31. Case study: thay reviewer giữa campaign quý

Một doanh nghiệp có chiến dịch recertification **Q4/2026** cho CRM, Finance và cloud. HRIS là nguồn manager, resource catalog giữ owner; IdP/SSO xác thực reviewer và SCIM/API thực thi revocation.

### 31.1. Case A – manager nghỉ phép

- Campaign tạo 120 review items cho Manager A.
- A nghỉ phép hai tuần; chính sách cho delegation tạm các item quyền thấp/trung bình thuộc CRM.
- Delegated reviewer B đã được xác minh, không là beneficiary của các item.
- Workflow reassign chỉ 100 item CRM trong scope, giữ 20 item cloud admin cho security escalation.
- B chọn KEEP/REVOKE với actor identity riêng.
- Các item không được quyết định trong hạn vẫn giữ trạng thái pending và được escalate theo policy.

**Bài học:** delegation chỉ dùng trong **phạm vi hợp lệ**, không tự mở quyền cho mọi entitlement.

### 31.2. Case B – resource owner Mover

- Finance Data Owner C chuyển bộ phận và mất ownership lúc 10:00.
- C có 18 item Finance đang pending; session browser của C vẫn mở.
- Ownership registry chỉ định D làm owner mới.
- Workflow reassign có audit và tăng assignmentVersion từ 2 lên 3.
- C bấm KEEP lúc 10:05 trên trang cũ; backend **DENY STALE_ASSIGNMENT**.
- D review, REVOKE 3 quyền không còn cần; connector thực thi và readback ở target.

**Bài học:** đổi reviewer phải kèm **chặn quyết định cũ**, không chỉ gửi email mới.

### 31.3. Case C – reviewer Leaver và beneficiary Mover

- Reviewer E nghỉ việc; IdP disabled.
- Beneficiary F vừa Mover khỏi Operations nhưng cloud role cũ còn tồn tại.
- Fallback reviewer cloud security được xác minh để xem item đặc quyền.
- Reviewer không chọn KEEP từ snapshot mà yêu cầu kiểm current role/approval; quyết định REVOKE.
- PAM/cloud IAM gỡ role theo scope, xử lý phiên/token, reconciliation xác minh không còn effective access.

**Bài học:** quyền được review và thẩm quyền reviewer **đều có lifecycle**, không được sử dụng trạng thái cũ.

### 31.4. Case D – service account mồ côi

- Pipeline production có role đọc secrets nhưng workload owner đã Leaver.
- Campaign thấy owner team không còn hiệu lực.
- Không tự assign reviewer là người tạo chiến dịch.
- IGA đưa item `OWNER_UNRESOLVED`, yêu cầu platform team xác nhận owner mới, security review tác động.
- Sau khi xác minh purpose, owner ra quyết định scope hẹp và expiry; các quyền thừa được revoke, nhưng không tắt nhầm pipeline production.

**Bài học:** reviewer thay thế phải gắn với **accountability và nghiệp vụ thật**, không phải chỉ hoàn thành campaign.

## 32. Ma trận kiểm thử âm tính và end-to-end

| Case | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 1 | Reviewer A là beneficiary của item | DENY self-review nếu SoD cấm |
| 2 | Reviewer thay không thuộc tenant | DENY view/decision |
| 3 | Reviewer Leaver còn SSO token | DENY quyết định |
| 4 | Reviewer Mover mất owner role | DENY trên item cũ, reassign |
| 5 | Delegate đã hết hạn | DENY |
| 6 | Candidate không được quyền xem classification | DENY hoặc limited context theo policy |
| 7 | Candidate có group IAM Admin nhưng không có review authority | DENY |
| 8 | Requester tự gửi `newReviewerIdentityId=self` | DENY nếu không có authority |
| 9 | Thay toàn campaign cho manager chỉ có scope một nhóm | Chặn items ngoài scope |
| 10 | Reviewer cũ bấm KEEP sau khi assignmentVersion đổi | DENY stale action |
| 11 | Hai reviewer cùng quyết định lúc race | Một commit hợp lệ, conflict được audit |
| 12 | Owner registry không đọc được | OWNER_UNRESOLVED/exception, không auto KEEP |
| 13 | Item đã REVOKE bị chuyển sang reviewer khác để KEEP | Chặn/re-review có approval riêng |
| 14 | Item đã CLOSED được submit lại | DENY replay |
| 15 | Reviewer không trả lời tới deadline | Escalate/exception, không tự KEEP |
| 16 | Beneficiary Leaver khi item pending | Không dùng KEEP để tái cấp |
| 17 | Beneficiary Mover, role cũ đã bị gỡ | Không tái provision từ snapshot |
| 18 | SCIM trả timeout khi revoke | UNKNOWN, retry có idempotency và readback |
| 19 | Target role đã gỡ nhưng API session vẫn hoạt động | Đánh dấu residual session và xử lý |
| 20 | Service account thiếu owner | Triage owner; không giả định quyền hợp lệ |
| 21 | Review item multi-tenant, chỉ có owner tenant-a | Không thấy/duyệt tenant-b |
| 22 | Bulk-review có một item SoD conflict | Item đó không được KEEP |
| 23 | Approval delegation bị revoke trong lúc reviewer mở UI | Recheck authority, DENY |
| 24 | Network mất khi ghi reassignment | Không mất/mâu thuẫn assignment và audit |
| 25 | Reviewer mới dùng link email forward từ người cũ | Xác thực và kiểm quyền lại |
| 26 | Resource đã bị xóa trong campaign | Reconcile, không tái cấp role |
| 27 | Quyền admin JIT hết hạn nhưng phiên còn | Session policy tiếp tục xử lý, không coi KEEP là đủ |
| 28 | Policy bắt buộc dual review nhưng chỉ substitute manager hoàn tất | Không đóng item nếu thiếu owner/security review |

### 32.1. Chuỗi test end-to-end

~~~text
HRIS/resource registry transition
  -> candidate reviewer resolution
  -> authority/SoD validation
  -> assignment version transition + audit
  -> old reviewer API decision rejected
  -> new reviewer authenticated decision
  -> remediation task (if REVOKE/MODIFY)
  -> SCIM/API/PAM/cloud target
  -> observed entitlements and sessions
  -> reconciliation evidence
~~~

Chỉ thấy UI đổi reviewer từ A sang B **không chứng minh** reviewer A đã bị vô hiệu khả năng ra quyết định, hoặc quyết định REVOKE được thực thi ở target.

## 33. Checklist thiết kế và vận hành

| Câu hỏi | Bằng chứng |
| --- | --- |
| Có phân biệt reviewer gốc, substitute, delegate, fallback? | Policy/RACI và UI rõ vai trò |
| Có nguồn đáng tin cho manager và resource owner? | HRIS/registry version |
| Có tính reviewer eligibility theo loại item? | Resource/action/tenant/risk policy |
| Reviewer mới đang ACTIVE, không bị security block? | Current identity validation |
| Có kiểm SoD/self-review bằng identity ID chung? | Negative test, identity linking |
| Có hạn chế delegation scope và thời hạn? | Delegation record |
| Có ngăn delegate tự re-delegate trái policy? | Chain/cycle validation |
| Thay reviewer chỉ đúng item/tenant được phép? | Assignment filtering |
| Có xử lý owner unresolved thay vì auto-KEEP? | Escalation/exception |
| Assignment version tăng khi chuyển? | Atomic state transition |
| Reviewer cũ không quyết định được sau transfer? | Backend PEP tests |
| Có giữ lịch sử A→B→C và lý do? | Immutable event log |
| Có chính sách cho overdue/reassignment deadline? | SLA/campaign routing |
| Có ngăn tăng deadline vô hạn bằng reassign? | Audit và limit |
| Có tách reviewer xem metadata và xem dữ liệu gốc? | Least privilege for review UI |
| Campaign snapshot có được phân biệt current state? | Source timestamps/current readback |
| Beneficiary Mover/Leaver có trigger revalidation? | JML workflows |
| Quyền service account có workload owner? | Non-human inventory |
| Quyền privileged có independent reviewer? | PAM/SoD controls |
| Policy engine và PEP kiểm reviewer trên từng decision? | Decision API authorization |
| Có chống concurrent decisions/replay? | Version, idempotency, transactions |
| Có quy trình appeal/re-review decision? | Governance state và audit |
| REVOKE có remediation, not just status update? | Connector task, target readback |
| Có kiểm token/session tồn dư sau revoke? | Effective access checks |
| Có đủ reason, actor, owner source, policy version? | Audit fields |
| Có bảo vệ PII và secret trong review evidence? | RBAC/retention/redaction |
| Campaign không auto-certify khi thiếu reviewer? | Negative tests |
| Có báo cáo exception và residual access? | KPI dashboard, owner |

## 34. Những nhầm lẫn thường gặp

1. **“Reviewer thay thế là bất kỳ người nào trong nhóm IAM.”** Phải có thẩm quyền trên item.
2. **“Chuyển reviewer là chuyển ownership của tài nguyên.”** Assignment và ownership khác nhau.
3. **“Một email chuyển tiếp đủ để người khác review.”** API phải xác minh actor hiện hành.
4. **“Manager mới luôn là resource owner mới.”** Hai quan hệ khác nhau.
5. **“Cùng group reviewer thì được xem mọi tenant.”** Scope phải được kiểm theo item.
6. **“Reviewer nghỉ thì toàn bộ item tự KEEP để kịp SLA.”** Timeout không tự chứng nhận.
7. **“Reviewer cũ có thể quyết định vì UI vẫn mở.”** Phải recheck assignment version.
8. **“Reviewer chỉ cần chọn KEEP, không cần biết resource.”** Cần metadata đáng tin.
9. **“Người đang giữ quyền có thể tự xác nhận.”** SoD có thể cấm self-review.
10. **“Delegate có thể ủy quyền tiếp vô hạn.”** Phải có policy và chống cycle.
11. **“Chuyển một item giúp reviewer có quyền với mọi item khác.”** Chỉ scope được giao.
12. **“KEEP là cấp quyền mới.”** Recertification đánh giá quyền đang có, không tự provision.
13. **“REVOKE nghĩa quyền đã hết.”** Phải kiểm connector, target và session.
14. **“SCIM success nghĩa effective access đã chặn.”** Local role/token có thể tồn dư.
15. **“Policy mới làm token cũ tự bị vô hiệu.”** Token/session có cơ chế riêng.
16. **“Một service account không có reviewer thì cứ giữ quyền.”** Cần owner/triage.
17. **“Đổi reviewer thì ghi đè actor lịch sử cho gọn.”** Mất accountability.
18. **“Các item đều có cùng deadline sau reassign.”** SLA phải theo policy/risk.
19. **“Reviewer của cloud admin có thể thay reviewer của data classification.”** Chuyên môn/authority khác nhau.
20. **“Chiến dịch 100% quyết định nghĩa 100% quyền an toàn.”** Cần remediation/reconciliation.

## 35. Câu hỏi tự đánh giá

1. Reviewer thay thế là ai và khác primary reviewer như thế nào?
2. Delegation tạm thời khác reassignment chính thức ở đâu?
3. Vì sao manager approval và resource owner review không phải lúc nào cũng thay nhau được?
4. Tại sao reviewer Leaver cần chặn API decision, không chỉ vô hiệu hóa email?
5. Một người dùng muốn tự chọn đồng nghiệp làm reviewer của chính quyền admin mình đang giữ. Có rủi ro nào?
6. Những trường dữ liệu nào quan trọng để kiểm reviewer có authority trên một review item?
7. Vì sao owner registry snapshot không đủ khi owner đổi trong campaign?
8. Review item đã REVOKE nhưng SCIM báo timeout: trạng thái nào nên ghi?
9. SoD theo identityId giúp phát hiện tự review khi một người có hai account như thế nào?
10. Vì sao không được auto KEEP item không được review trước hạn?
11. Một quyền cloud admin cần những reviewer/role độc lập nào theo mức rủi ro?
12. Khi delegate hết hạn giữa lúc đã mở UI, backend phải làm gì?
13. Vì sao reviewer mới không nên tự có quyền xem dữ liệu gốc của resource?
14. Assignment version xử lý race giữa hai reviewer ra sao?
15. Gắn quyết định với actor gốc hay substitute? Cần lưu thông tin gì về cả hai?
16. Beneficiary Mover khỏi bộ phận cũ nhưng snapshot còn quyền: KEEP có được tái cấp không?
17. Làm thế nào xử lý service principal mồ côi mà vẫn bảo vệ tính liên tục production?
18. Quyền khác nhau giữa review.decision và review.reassign là gì?
19. Cách kiểm cross-tenant khi người được giao chỉ là owner tenant-a?
20. Một item có manager review và security review: thay manager có hoàn tất cả hai không?
21. Vì sao một quyết định KEEP hợp lệ ở thời điểm trước Leaver vẫn được giữ trong audit?
22. Khiếu nại decision REVOKE phải dùng workflow nào để tránh approval shopping?
23. Nêu ít nhất năm trường cần có trong reviewer reassignment audit event.
24. Chỉ số nào đánh giá chất lượng reviewer thay thế thay vì chỉ đếm số quyết định?
25. Nêu ba negative tests cho reassignment, self-review và stale token.

## 36. Ghi nhớ

**Reviewer thay thế** trong **Access recertification** là người hoặc nhóm được chỉ định để **đánh giá quyền đã tồn tại thay reviewer ban đầu khi reviewer gốc không khả dụng, mất thẩm quyền hoặc có xung đột**. Việc thay thế chỉ hợp lệ khi có **nguồn owner/manager đáng tin, danh tính reviewer ACTIVE, authority đúng resource/tenant/entitlement, SoD không xung đột, hiệu lực delegation và audit phân công rõ ràng**. Phải tách **reviewer gốc, người được giao hiện tại, người thực sự đưa decision, người chịu trách nhiệm tài nguyên** và bảo vệ mọi thay đổi bằng **assignment version, kiểm quyền tại backend và lưu lịch sử**.

Trong IAM **Joiner–Mover–Leaver**, **HRIS/identity registry** xác định trạng thái người đánh giá và người giữ quyền; **IdP/SSO** xác thực reviewer; **IGA/RBAC/ABAC/PBAC** quyết định thẩm quyền và điều phối campaign; **SCIM/API/PAM** thực thi thu hồi; **PEP** chặn quyết định hoặc truy cập trái quyền; **reconciliation/audit** xác minh kết quả thực tế. **Thay reviewer không tự gia hạn một entitlement, KEEP không cấp lại quyền đã thu hồi và REVOKE không chứng minh target đã chặn truy cập**. Thiết kế tốt phải ngăn **self-certification, reviewer cũ quyết định sau Mover/Leaver, cross-tenant review, timeout auto-approve, replay và quyền truy cập tồn dư**.
