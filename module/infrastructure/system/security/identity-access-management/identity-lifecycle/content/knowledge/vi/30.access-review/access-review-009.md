# Review decision trong Access review và quản lý vòng đời danh tính IAM

## 1. Review decision là gì?

**Review decision** là kết luận chính thức của người hoặc cơ chế có thẩm quyền đối với **một quyền truy cập đang tồn tại** trong kỳ **Access review (access certification/recertification)**. Quyết định trả lời câu hỏi: **quyền này còn cần thiết, đúng người, đúng tài nguyên, đúng phạm vi và còn hợp lệ theo chính sách tại thời điểm rà soát hay không?**

Ví dụ, một chiến dịch rà soát phát hiện nhân viên Lan đang giữ quyền **customer.export** trong ứng dụng CRM. Lan đã chuyển từ Sales sang Finance. Người rà soát cần quyết định **thu hồi** quyền này nếu không còn căn cứ công việc; không nên chỉ bấm **Approve/Certify** vì Lan vẫn là nhân viên của tổ chức.

Một review decision phải gắn với **chủ thể, quyền/entitlement, tài nguyên, phạm vi, nguồn cấp, phiên bản dữ liệu, căn cứ quyết định, người duyệt và thời điểm**. Nó không phải là tên của một nút giao diện hay một email xác nhận chung chung.

Bài thuộc chương **Access review** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, về quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo account, cấp quyền, rà soát, cập nhật và thu hồi khi quan hệ thay đổi. Nội dung liên kết **IdP, SSO, SCIM, RBAC/ABAC, service account, audit** và giảm **quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **review decision** với **access request approval**, quyết định authorization lúc gọi API và kết quả provisioning.
2. Hiểu các lựa chọn **Retain/Certify, Revoke, Modify, Investigate, Escalate, Exception** và khi nào dùng.
3. Kiểm tra **reviewer authority**, độc lập, SoD và bằng chứng công việc.
4. Đọc đúng **effective permissions**, grant trực tiếp, nhóm lồng nhau, quyền kế thừa và phạm vi tài nguyên.
5. Thiết kế quyết định có **snapshot/version**, tránh xác nhận dựa trên dữ liệu lỗi thời.
6. Chuyển quyết định thành **remediation/fulfillment**, theo dõi readback, thất bại và quyền còn tồn dư.
7. Áp dụng vào **Joiner–Mover–Leaver, contractor và non-human identities**.
8. Thiết kế audit, metrics, test cases và runbook cho chiến dịch access review.

## 2. Review decision khác access request approval thế nào?

Hai quy trình có thể đều có nút **Approve**, nhưng bản chất khác nhau:

| Khía cạnh | Access request approval | Review decision trong access review |
|---|---|---|
| **Câu hỏi** | Có nên cấp hoặc thay đổi một quyền được xin? | Quyền đang tồn tại có nên tiếp tục được giữ? |
| **Nguồn khởi phát** | Người dùng, manager, JIT request hoặc quy trình Joiner | Campaign theo lịch, thay đổi vai trò, sự kiện rủi ro |
| **Đối tượng** | Desired new entitlement hoặc change | Existing account/role/permission/grant |
| **Kết quả điển hình** | Approve/Deny/Conditional | Retain/Revoke/Modify/Investigate |
| **Thực thi** | Provision quyền nếu được duyệt | Giữ nguyên có kiểm soát, thu hồi hoặc điều chỉnh |
| **Rủi ro chính** | Cấp quyền quá rộng, sai người | Chứng nhận nhầm quyền dư hoặc không thu hồi |
| **Bằng chứng cần có** | Nhu cầu mới, policy, owner, thời hạn | Nguồn cấp, usage, quan hệ hiện hành, effective rights |
| **Hiệu lực** | Decision không tự tạo grant | Review decision không tự thay đổi grant |

**Review decision không thay thế runtime authorization.** Một quyền được chứng nhận hôm nay vẫn phải bị từ chối khi ngày mai nhân viên Leaver, quyền JIT hết hạn hoặc resource chuyển tenant. API vẫn phải đánh giá **subject–action–resource–context** tại thời điểm thực thi.

### Access review không chỉ là “gia hạn quyền”

Chiến dịch review phải phát hiện **quyền thừa, quyền trực tiếp, role quá rộng, orphan account, SoD conflict, stale group membership và quyền không còn owner**; không phải quy trình hợp thức hóa tất cả entitlement đang nhìn thấy.

## 3. Đối tượng được đưa ra review decision

Một đối tượng cần rà soát có thể là:

- **User → Role assignment:** Lan có role FINANCE_READER.
- **User → Group membership:** Lan thuộc nhóm CRM_SALES_EXPORT.
- **User → Direct permission:** account được cấp thẳng quyền database SELECT.
- **User → Privileged eligibility:** nhân viên đủ điều kiện kích hoạt admin qua PAM/PIM.
- **User → Active JIT grant:** grant có thời hạn đang bật.
- **Account access:** một account local ở SaaS có còn được phép tồn tại?
- **Workload → Cloud role:** service principal có quyền đọc bucket production.
- **Contractor → Project access:** guest còn hợp đồng/sponsor hợp lệ?
- **Relationship → Resource:** một người có còn là project editor hoặc document owner?
- **Delegation:** người dùng có còn quyền phê duyệt thay người khác?

### Những thành phần của một review item

| Trường | Ý nghĩa |
|---|---|
| **subjectId / accountId** | Ai đang nhận quyền tại IAM và hệ thống đích |
| **relationshipId / ownerId** | Quan hệ công việc hoặc owner workload làm căn cứ |
| **targetSystem / tenantId** | Đích và biên tenant |
| **entitlementId** | Role/group/permission/grant thực tế |
| **action / resourceScope** | Quyền làm gì và trên tài nguyên nào |
| **grantSource** | Cấp từ role, group, request, exception, direct grant hay JIT |
| **effectiveFrom / Until** | Cửa sổ quyền có hiệu lực |
| **riskClassification** | Rủi ro, dữ liệu nhạy cảm và đặc quyền |
| **observedState / observedAt** | Quyền thực tế đọc từ hệ thống đích khi nào |
| **desiredState** | Quyền nên có theo JML, policy và approval |
| **reviewItemVersion** | Mốc bảo vệ trước thay đổi đồng thời |
| **reviewerId** | Người hoặc hệ thống có quyền đưa quyết định |
| **decision / reasonCode** | Kết luận và căn cứ |
| **remediationState** | Tiến độ cấp lại, giảm phạm vi hoặc thu hồi sau quyết định |

**Không chỉ rà soát role name.** Một group có thể kế thừa permission của nhóm khác; một tài khoản có direct grants ngoài IAM; một quyền đọc có thể là quyền export trên toàn tenant nếu ứng dụng ánh xạ khác dự kiến.

## 4. Review decision thuộc giai đoạn nào của access review?

Một chu trình điển hình:

~~~mermaid
flowchart TD
    S[Khởi tạo campaign hoặc event-triggered review] --> INV[Inventory account, role, entitlement]
    INV --> SNAP[Snapshot và tính effective permissions]
    SNAP --> ASSIGN[Chọn reviewer có thẩm quyền]
    ASSIGN --> EVID[Trình bày evidence + rủi ro]
    EVID --> DEC{Review decision}
    DEC -->|Retain| CERT[Chứng nhận có căn cứ]
    DEC -->|Revoke| REV[Remediation: gỡ entitlement]
    DEC -->|Modify| MOD[Thay scope/role/expiry theo policy]
    DEC -->|Need info/Escalate| WAIT[Điều tra, bổ sung, chuyển cấp]
    WAIT --> EVID
    REV --> CHECK[Target readback và access validation]
    MOD --> CHECK
    CERT --> VALID[Giữ quyền và ghi kỳ chứng nhận tiếp]
    CHECK --> OUT{Desired khớp observed?}
    OUT -->|Không| FIND[Finding, owner, SLA, compensating control]
    OUT -->|Có| DONE[Closed với evidence]
    VALID --> DONE
~~~

**Quyết định là một mốc giữa quy trình**, không phải bằng chứng duy nhất để đóng campaign. Với Revoke/Modify, cần **remediation và verification**. Với Retain, cần có **căn cứ, reviewer đủ quyền và không tồn tại điều kiện mất hiệu lực mới hơn**.

### Hai trục trạng thái độc lập

- **Review status:** chưa duyệt, đã duyệt, bị từ chối, cần thông tin, quá hạn.
- **Access/remediation status:** còn active, đang gỡ, đã gỡ, đã sửa, thất bại hoặc chỉ gỡ được một phần.

Nếu hai trạng thái bị gộp làm một, hệ thống dễ hiện “Completed” dù quyền vẫn còn ở hệ thống đích.

## 5. Những kết quả quyết định cần phân biệt

Không có một bộ trạng thái bắt buộc chung cho mọi IGA/Access review product. Một mô hình hữu dụng:

| Decision | Diễn giải | Hệ quả cần xử lý |
|---|---|---|
| **RETAIN / CERTIFY** | Quyền hiện tại còn hợp lệ trong phạm vi đã xem | Ghi rationale, version, kỳ review tiếp theo |
| **REVOKE** | Quyền không còn được phép tiếp tục | Tạo tác vụ thu hồi, theo dõi readback |
| **MODIFY** | Vẫn cần một phần quyền nhưng phải giảm/đổi phạm vi | Tính desired entitlement mới và thực thi thay đổi |
| **NEED_MORE_INFO** | Chưa đủ dữ liệu để kết luận | Yêu cầu thông tin, không mặc định certify |
| **ESCALATE** | Reviewer không đủ thẩm quyền hoặc phát hiện rủi ro | Chuyển owner/security theo route hợp lệ |
| **EXCEPTION_REQUESTED** | Cần xử lý khác policy chuẩn | Đưa qua quy trình chấp nhận rủi ro có thời hạn |
| **NOT_APPLICABLE / WRONG_OWNER** | Item được route nhầm người hoặc sai đối tượng | Reassign/khôi phục mapping và review lại |
| **ABSTAIN** | Người nhận từ chối đưa quyết định do xung đột lợi ích | Chuyển reviewer độc lập |
| **OVERDUE / NO_RESPONSE** | Không có quyết định đúng hạn | Escalate hoặc xử lý theo policy đã phê duyệt |

### Tránh hiểu sai một số trạng thái

- **NEED_MORE_INFO không phải RETAIN.**
- **ESCALATE không phải APPROVE.**
- **REVOKE không chứng minh quyền đã mất hiệu lực.**
- **MODIFY không cho phép gán quyền rộng hơn mà không có approval tương ứng.**
- **OVERDUE không được tự coi là CERTIFIED**, trừ khi có quy tắc hợp lệ riêng; ngay cả khi policy quy định mặc định thu hồi, phải xét tác động, ngoại lệ nghiệp vụ và kiểm soát rủi ro.
- **EXCEPTION_REQUESTED không có nghĩa exception đã được chấp thuận.**

## 6. Reviewer là ai và có đủ thẩm quyền không?

Những reviewer thường gặp:

| Reviewer | Phù hợp khi | Giới hạn |
|---|---|---|
| **Line manager** | Xác nhận nhu cầu công việc và vai trò của nhân viên | Có thể không biết chi tiết dữ liệu/tài nguyên |
| **Resource/Data owner** | Rà soát quyền đối với dataset, project, ứng dụng | Chỉ duyệt trong phạm vi sở hữu |
| **Application owner** | Xác minh kỹ thuật role/entitlement thật | Không thay thế đánh giá SoD của Security |
| **Security/PAM owner** | Quyền đặc quyền, toxic combinations, ngoại lệ | Không tự chứng nhận nhu cầu nghiệp vụ thay owner |
| **Project sponsor** | Nhà thầu/đối tác được sponsor | Phải còn quyền bảo trợ hợp lệ |
| **Service/workload owner** | Quyền của bot, service principal và pipeline | Phải có registry và ownership hiện hành |
| **Delegated reviewer** | Người được giao review thay trong phạm vi/thời gian | Không vượt thẩm quyền gốc |
| **Policy-based reviewer** | Auto-certify một nhóm quyền rủi ro thấp có rule được duyệt | Cần policy version, test và evidence |

Một reviewer chỉ nên được phân công khi:

1. **Danh tính reviewer active** và đã được xác thực đúng mức.
2. Có **quyền review đúng target/resource/tenant**.
3. Không có **self-review hoặc conflict of interest** bị chính sách cấm.
4. Không phải người đã Leaver hoặc delegation hết hạn.
5. Có đủ **thông tin giải thích quyền** để ra quyết định.
6. Có route escalation khi người này không thể kết luận.

**Từ chối self-review không có nghĩa manager tuyệt đối không thể review quyền của một nhân viên cùng nhóm**; quy tắc độc lập phải được tổ chức định nghĩa theo risk và SoD.

## 7. Bằng chứng reviewer phải nhìn thấy

Một màn hình chỉ liệt kê **ADMIN_APP_07** mà không giải thích hiệu lực khiến review gần như hình thức.

Nên cung cấp tối thiểu:

- Danh tính chính thức của beneficiary và trạng thái **Joiner–Mover–Leaver**.
- Role/job function/department hiện hành theo nguồn HRIS/contract.
- **Tên nghiệp vụ** của quyền, cùng technical entitlement thực sự.
- **Action được phép**, ví dụ report.read, report.export, payment.approve.
- **Scope**: tenant, environment, project, dữ liệu và resource.
- **Grant source/provenance:** cấp theo baseline role, approved request, direct grant hay exception.
- **Ngày cấp, người cấp, approval và expiry**.
- Usage metadata nếu được thu thập đúng và có giá trị.
- Mức rủi ro, SoD conflict, dữ liệu nhạy cảm, quyền kế thừa.
- Quyền liên quan khác làm thay đổi effective permissions.
- Thời điểm readback cuối, độ tươi và coverage của hệ thống đích.

### Bằng chứng thiếu không tự chứng minh quyền sai hoặc đúng

Không thấy nhật ký sử dụng trong 90 ngày có thể là tín hiệu điều tra, nhưng **không tự chứng minh quyền không cần thiết**: quyền on-call hoặc khẩn cấp có thể ít dùng. Ngược lại, quyền được dùng thường xuyên **không có nghĩa được phép** nếu nhân viên đã chuyển bộ phận hoặc vi phạm SoD.

**Usage là một loại evidence, không phải nguồn chính sách duy nhất.**

## 8. Phân biệt direct grant và effective permission

Một người có thể nhận cùng một permission từ nhiều nguồn:

~~~text
User Lan
  |-- Business role: FINANCE_ANALYST
  |      |-- Group: finance-read
  |      +-- Permission: report.read
  |
  |-- Direct grant: report.export (temporary, expired?)
  |
  +-- Nested group: project-alpha
         +-- Group: analytics-export
                +-- Permission: report.export
~~~

Nếu reviewer chọn **REVOKE direct grant report.export** nhưng nested group vẫn cấp **report.export**, người dùng **chưa thực sự mất quyền export**.

### Cần xem xét những đường cấp quyền

| Nguồn quyền | Điều cần kiểm tra |
|---|---|
| **Role trực tiếp** | Assignment hiện hành và scope |
| **Role hierarchy** | Quyền kế thừa từ role cấp khác |
| **Group lồng nhau** | Membership nhiều tầng, chu trình/cấu hình đặc thù |
| **Direct permission** | Gán ngoài role catalog |
| **SCIM Group mapping** | Membership ở ứng dụng đích và rule map tới entitlement |
| **Local account grants** | Quyền tồn tại ngoài IdP/IGA |
| **Cloud IAM policy** | Resource condition, role binding, service principal |
| **Delegation/ReBAC** | Quan hệ owner/member/reviewer được kế thừa |
| **JIT/PAM** | Eligible role khác Active grant, session đã mở |
| **Token/session** | Claim cũ, local session hoặc credential độc lập |

**Review decision nên nhận diện nguồn cần chỉnh sửa**, đồng thời xác định **effective access mong muốn**. Không xóa role ở một nơi rồi mặc định tài nguyên đã từ chối action.

## 9. Review scope và sự khác biệt giữa account, role, entitlement, permission

Các chiến dịch có phạm vi khác nhau:

| Loại review | Đối tượng chính | Câu hỏi |
|---|---|---|
| **Account review** | Một account ở ứng dụng | Account này còn có owner và căn cứ tồn tại? |
| **Role assignment review** | User ↔ Role | Role còn phù hợp vị trí hiện tại? |
| **Entitlement review** | User ↔ App permission/group | Quyền này còn cần và hợp lệ? |
| **Privileged access review** | Admin, PAM/PIM/JIT | Đặc quyền có còn cần, đủ hẹp và có hạn? |
| **Resource owner review** | Người có quyền với một resource | Ai được xem/sửa/xuất tài nguyên này? |
| **SoD review** | Tập quyền xung đột | Có toxic combination hoặc tự phê duyệt? |
| **Non-human access review** | Service account/workload/device | Owner, purpose, credential và scope còn hợp lệ? |
| **External/guest review** | Contractor/partner | Hợp đồng/sponsor và thời hạn còn hiệu lực? |

Một **account review** quyết định giữ account không có nghĩa mọi **role/entitlement bên trong account** đã được chứng nhận. Tương tự, reviewer có thể giữ role đọc nhưng thu hồi quyền export riêng của cùng account.

### Tránh yêu cầu xóa account khi chỉ cần gỡ một entitlement

Quyết định **REVOKE** trên một review item nên định nghĩa rõ **quyền nào bị thu hồi**, không tự mở rộng thành xóa toàn bộ User trừ khi campaign thật sự xét sự tồn tại account hoặc JML yêu cầu.

## 10. Reviewer decision dựa trên desired state, không chỉ current state

Trong IAM, cần phân biệt:

- **Observed state:** account, role, group và permission đang tồn tại tại hệ thống đích.
- **Desired state:** quyền được phép tồn tại theo nguồn JML, role, approval, SoD, resource scope và ngoại lệ còn hiệu lực.
- **Review decision:** quyết định con người/policy xác nhận, điều chỉnh hoặc từ chối căn cứ cho desired state.

Ví dụ:

| Thành phần | Quan sát | Chính sách hiện hành | Quyết định phù hợp |
|---|---|---|---|
| Lan có Sales Export | ACTIVE | Lan đã Mover sang Finance | REVOKE |
| Lan có Finance Reader | ACTIVE | Nhu cầu Finance và scope đúng | RETAIN |
| Lan có Finance Admin | ACTIVE | Chỉ cần read | MODIFY/REVOKE admin |
| Bot backup có object.read | ACTIVE | Owner/ứng dụng còn hoạt động | RETAIN có căn cứ |
| Contractor có account prod | ACTIVE | Hợp đồng hết hạn | REVOKE theo policy |
| Local admin không owner | ACTIVE | Chưa có căn cứ hợp lệ | INVESTIGATE/ESCALATE, áp biện pháp chặn phù hợp |

**Không lấy existing access làm bằng chứng đủ để giữ quyền.** Access review có mục tiêu nhận diện quyền sai lịch sử, không hợp thức hóa những gì ứng dụng đang cho phép.

## 11. Dữ liệu thời gian: snapshot, as-of và version

Trong khi campaign diễn ra, người dùng có thể thay đổi vị trí, tài khoản bị vô hiệu, group bị cập nhật hoặc một quyền được cấp thêm từ request mới. Vì vậy mỗi review item cần có **snapshot as-of**.

### Các mốc thời gian hữu ích

| Mốc | Ý nghĩa |
|---|---|
| **campaignAsOf** | Thời điểm chụp dữ liệu để tạo kỳ review |
| **observedAt** | Thời điểm đọc entitlement tại hệ thống đích |
| **sourceVersion** | Phiên bản sự kiện/nguồn JML |
| **reviewedAt** | Lúc reviewer đưa kết luận |
| **decisionEffectiveAt** | Khi quyết định bắt đầu được áp dụng nếu có |
| **fulfillmentAt** | Khi connector thực thi thay đổi |
| **verifiedAt** | Khi đối soát xác minh trạng thái đích |
| **grantExpiresAt** | Hạn độc lập của quyền tạm/JIT |
| **reviewDueAt** | Hạn kết luận của kỳ review |

### Ví dụ lỗi do quyết định lỗi thời

- Ngày 01: campaign chụp Lan là **Sales**, có nhóm SALES_EXPORT.
- Ngày 02: HRIS phát **Mover** sang Finance, IAM gỡ quyền Sales.
- Ngày 03: reviewer dựa ảnh snapshot ngày 01 bấm **RETAIN Sales Export**.
- Ngày 04: job “áp dụng review” vô tình cấp lại nhóm Sales đã được gỡ.

Đó là **stale review decision**. Quy trình phải phân biệt **quyết định trên snapshot cũ** với **trạng thái authoritative mới nhất**, kiểm version/fencing ngay trước thay đổi. **Không dùng RETAIN làm lệnh cấp lại quyền đã bị JML thu hồi.**

## 12. Khi nào nên chọn RETAIN / CERTIFY?

**RETAIN** nghĩa là reviewer xác nhận quyền trong item **vẫn có căn cứ hợp lệ**, trong phạm vi đã đánh giá.

Cần kiểm tra:

1. Beneficiary đang có **quan hệ làm việc/sponsor hợp lệ**.
2. Công việc hoặc workload vẫn thực sự cần **action/resource scope**.
3. Role/entitlement không quá rộng so với **least privilege**.
4. Nguồn quyền có approval/baseline policy còn hiệu lực.
5. Không vi phạm **Separation of Duties (SoD)**.
6. Không mâu thuẫn chính sách về dữ liệu, tenant, môi trường, time window.
7. Với quyền đặc quyền, có đủ MFA/JIT/PAM, owner và monitoring khi bắt buộc.
8. Reviewer có quyền chứng nhận item và đưa **reason code/rationale** đủ rõ.
9. Việc giữ quyền không tái kích hoạt một grant đã hết hiệu lực.
10. Kỳ review tiếp theo và mốc expiration được xác định theo risk.

### RETAIN không gia hạn vô thời hạn

Nếu quyền là **JIT grant kết thúc sau 30 phút**, quyết định RETAIN trên eligibility hoặc business need không tự cho phép kéo dài grant đang hoạt động. Nếu quyền có **expiry theo contract**, review không được tự vượt thời hạn hợp đồng.

### Không xác nhận chỉ vì “đã có lâu”

Một quyền tồn tại nhiều năm mà chưa ai phàn nàn không phải bằng chứng cần thiết. Reviewer cần dựa trên **mục đích và thẩm quyền hiện tại**.

## 13. Khi nào nên chọn REVOKE?

REVOKE là lựa chọn khi quyền không có căn cứ tiếp tục, ví dụ:

- Người đã **Leaver** hoặc hợp đồng kết thúc.
- Người **Mover** sang chức năng khác.
- Quyền bị cấp nhầm hoặc ngoài phạm vi tenant.
- Entitlement có **owner chưa xác minh** và không thể chứng minh nhu cầu hợp lệ trong thời hạn phù hợp.
- Quyền đặc quyền không còn nhu cầu hoặc có giải pháp hẹp hơn.
- Quyền vượt classification/hạn mức/SoD.
- Grant tạm hoặc delegation đã hết hạn.
- Duplicated/granted-by-mistake access mà không còn căn cứ riêng hợp lệ.

### Thu hồi phải xác định đúng đối tượng

Nếu một group chứa **nhiều thành viên** hợp lệ, reviewer chỉ quyết định thu hồi membership của Lan, không xóa group của tất cả người dùng. Nếu quyền đến từ business role, cần xác định **role assignment** nào bị gỡ mà không làm mất quyền cần thiết của một quan hệ khác.

### REVOKE không phải bằng chứng đã thu hồi

Một item có decision=REVOKE nhưng **remediationState=OPEN** chưa thể coi là hoàn tất. Phải:

1. Xác định đường cấp quyền cần gỡ.
2. Thực hiện revocation qua connector/API/PAM.
3. Readback entitlement và các đường cấp quyền tương đương.
4. Kiểm tra action bị từ chối khi chính sách yêu cầu.
5. Xử lý session/token/local credential liên quan.
6. Ghi evidence hoặc finding khi còn quyền tồn dư.

## 14. Khi nào nên chọn MODIFY?

**MODIFY** phù hợp khi quyền vẫn cần nhưng phải được **thu hẹp hoặc điều chỉnh**.

Ví dụ:

| Hiện tại | Desired sau review | Tác vụ |
|---|---|---|
| report.export toàn doanh nghiệp | report.read của Finance | Gỡ export, giữ/thiết lập read |
| Cloud Owner trên subscription | logs.read trên resource group | Thu hồi Owner, cấp role hẹp |
| project.editor ở cả 2 project | project.editor chỉ project A | Gỡ membership/binding project B |
| Quyền không có expiry | Quyền tới ngày hợp đồng hết | Gắn expiry được enforcement |
| DB superuser | Maintenance qua PAM session | Thay đặc quyền thường trực bằng JIT |
| Ủy quyền approve không hạn | Ủy quyền trong kỳ nghỉ cụ thể | Giới hạn thời gian và resource |

### MODIFY không tự được phép mở rộng quyền

Nếu reviewer chuyển **reader → admin**, đây là **cấp thêm quyền nhạy cảm**, không chỉ “điều chỉnh kỹ thuật”. Phải đánh giá theo **access request/approval workflow** phù hợp và không lấy review decision làm cách bỏ qua chính sách cấp quyền.

### Thứ tự chuyển đổi

Một thao tác MODIFY thường có hai phần:

1. Bảo đảm **desired entitlement mới** thực sự hợp lệ và có approval cần thiết.
2. Thu hồi entitlement cũ và đối soát **không còn quyền dư**.

Với thay đổi dễ gây gián đoạn, thứ tự grant/revoke có thể được thiết kế theo rủi ro và tính liên tục công việc. Tuy nhiên **không để giai đoạn overlap tạo toxic combination** mà policy cấm.

## 15. Cần thông tin bổ sung, chuyển cấp hoặc từ chối chứng nhận

Không phải item nào cũng đủ thông tin để đưa ngay quyết định.

### NEED_MORE_INFO

Dùng khi thiếu:

- Mô tả quyền thực sự cấp **action nào**.
- Resource owner hoặc sponsor của quyền.
- Trạng thái quan hệ hợp đồng.
- Thông tin usage có ý nghĩa.
- Ảnh hưởng tới business process nếu thu hồi.
- Kết quả SoD hoặc entitlement mapping.

Hệ thống cần ghi **câu hỏi cần trả lời, người chịu trách nhiệm và deadline**. Không để item nằm vô hạn ở trạng thái Pending.

### ESCALATE

Phù hợp khi:

- Role chứa quyền **root/Global Admin** vượt thẩm quyền manager.
- Có **SoD conflict**, quyền truy cập dữ liệu nhạy cảm hoặc ngoại lệ pháp lý.
- Reviewer không phải owner đúng.
- Có dấu hiệu cấp quyền trái phép/incident.
- Hai reviewer đưa quyết định xung đột.
- Công cụ không thể quan sát đầy đủ quyền nhưng báo cáo lại cần chứng nhận.

### WRONG_OWNER / ABSTAIN

Một người có thể không đủ thẩm quyền hoặc có conflict of interest. Cần **reassign** cho người có quyền hợp lệ, không ép họ bấm RETAIN để “xóa backlog”.

**Không có phản hồi không được diễn giải thành chấp thuận một cách ngầm định.** Cách xử lý overdue, auto-revoke hoặc escalation phải được định nghĩa trước, đặc biệt với quyền nhạy cảm và khả năng gây gián đoạn.

## 16. Decision có điều kiện và quyền ngoại lệ

Một số trường hợp quyền cần duy trì tạm trong thời gian khắc phục:

- Ứng dụng legacy chưa hỗ trợ role hẹp.
- Quyền admin phải tồn tại trong một đợt migration được duyệt.
- Một nhà thầu hỗ trợ khẩn cấp tới hạn contract đã được gia hạn.
- Người chịu trách nhiệm cần quyền để bàn giao dữ liệu trước khi vô hiệu account.

Một **EXCEPTION_REQUESTED** cần có:

| Thông tin | Ý nghĩa |
|---|---|
| **ExceptionId** | Định danh riêng, không trùng |
| **Risk owner** | Người có thẩm quyền chấp nhận rủi ro |
| **Reason** | Vì sao không thể áp đúng policy hiện tại |
| **Affected subject/resource** | Chính xác phạm vi quyền ngoại lệ |
| **Compensating controls** | MFA, PAM, session monitoring, IP restrictions, JIT |
| **Valid until** | Hạn kết thúc, không để vô thời hạn |
| **Review trigger** | Ngày tái đánh giá hoặc sự kiện JML |
| **Remediation plan** | Cách đưa hệ thống về least privilege |
| **Approval evidence** | Ai duyệt và policy nào cho phép ngoại lệ |

**Reviewer không tự cấp ngoại lệ chỉ bằng cách gõ “OK tạm” vào ô ghi chú.** Nếu chính sách yêu cầu risk owner/Security approval riêng, request phải đi theo đúng workflow trước khi một grant có căn cứ tiếp tục.

### Không hợp thức hóa truy cập trái phép nghiêm trọng

Đối với Leaver đã hết căn cứ quan hệ, hoặc quyền tạo rủi ro không thể chấp nhận, **không nên dùng exception để kéo dài truy cập chỉ để hoàn thành campaign**. Cần cắt/chặn theo policy và tổ chức bàn giao bằng tài khoản, owner và cơ chế hợp lệ khác.

## 17. Reviewer authority, self-review và Separation of Duties

**Segregation/Separation of Duties (SoD)** yêu cầu độc lập giữa những chức năng có khả năng xung đột.

### Rủi ro self-review

- Admin tự chứng nhận quyền admin của mình.
- Người tạo direct grant cũng là người quyết định grant này hợp lệ, trong khi policy đòi review độc lập.
- Người có quyền payment.create và payment.approve tự chứng nhận cả hai.
- Reviewer cấp dưới nhận lời nhờ giữ quyền cho manager mà không có quyền phù hợp.

### Biện pháp

1. **Kiểm tra identity reviewer** từ IdP/IGA, không tin field do client tự gửi.
2. **Ngăn reviewer chứng nhận chính quyền mình** khi policy cấm.
3. **Quy định người phê duyệt độc lập** với đặc quyền/root/break-glass.
4. Đánh giá **effective permissions**, không chỉ tên role.
5. Tính **role hierarchy, nested group và direct grants**.
6. Quản lý delegation review với **scope và expiry**.
7. Ghi audit cả **người được phân công ban đầu** và người đưa quyết định cuối.
8. Với SoD nghiêm trọng, yêu cầu security/risk owner độc lập giải quyết.

**Reviewer có quyền đổi assignment của mình không đồng nghĩa có quyền tự chứng nhận tính đúng đắn của assignment đó.**

## 18. Review decision và Access review campaign

**Campaign** là đơn vị tổ chức một đợt rà soát: phạm vi, người duyệt, hạn xử lý, bằng chứng và báo cáo tổng hợp.

### Metadata campaign nên có

- **CampaignId, name, scope, owner.**
- **Review type:** manager, resource-owner, privileged, contractor, workload.
- **As-of date** và quy tắc snapshot.
- **Population:** identities/accounts/entitlements thuộc phạm vi.
- **Risk-based priority** và hệ thống ưu tiên.
- **Reviewer assignment routing** và delegation.
- **Deadline, reminder, escalation, overdue policy**.
- **Allowed decision types** và reason requirements.
- **Remediation owner / SLA**.
- **Closure criteria và reconciliation coverage**.

### Duyệt item theo từng quyền hay theo gói?

Một nhóm có thể xem nhiều entitlement cùng lúc để giảm thao tác, nhưng **quyết định phải vẫn truy vết được tới từng item cần chứng nhận**. Bulk certify không được cho phép reviewer vô tình giữ một quyền admin bị ẩn giữa hàng trăm quyền reader.

### Campaign closure

Một chiến dịch có thể đóng mặt **review collection** khi đã nhận đủ quyết định, nhưng **remediation closure** chỉ nên đạt khi các quyết định Revoke/Modify đã được xử lý hoặc còn exception được ghi nhận rõ. Báo cáo phải phân biệt hai mốc này.

## 19. Review decision trong Joiner lifecycle

**Joiner** tập trung cấp quyền ban đầu; review decision phát huy vai trò trong những **kiểm tra sau onboarding** hoặc rà soát sớm quyền nhạy cảm.

### Các câu hỏi nên hỏi

- Account có được gắn với **identity đã proofing/enroll đúng**?
- Birthright roles có khớp **job function/relationship** không?
- Access request ngoài baseline có approval và scope đúng không?
- Người mới có đang được cấp **role clone từ người tiền nhiệm** chứa quyền thừa?
- Account được chuẩn bị sớm có đang **active trước effectiveAt** không?
- App đã provision bằng SCIM có tạo **local admin mặc định** không?
- Quyền JIT chỉ ở trạng thái **eligible**, hay bị bật luôn?
- Owner có thể giải thích mọi entitlement rủi ro cao không?

Một quyết định **RETAIN birthright role** có thể hợp lệ, nhưng không được tự xem mọi entitlement “được tạo khi Joiner” đều là birthright. **Quyền ngoài nhiệm vụ phải được xử lý theo least privilege**.

### Ví dụ

Lan mới vào Sales. Access review sau 30 ngày phát hiện Lan có group **SALES_READER** và **SALES_EXPORT_ADMIN**. Manager xác nhận chỉ cần đọc: **RETAIN SALES_READER**, **REVOKE SALES_EXPORT_ADMIN**; target readback và thử export chứng minh quyền export đã bị chặn.

## 20. Review decision trong Mover lifecycle

**Mover** thay đổi department, job role, manager, project, tenant hoặc loại quan hệ. Đây là thời điểm nguy cơ **privilege accumulation** cao: thêm quyền mới mà không gỡ hết quyền cũ.

### Bảng ví dụ

| Review item | Trước Mover | Sau Mover mong muốn | Decision |
|---|---|---|---|
| CRM SALES_READER | Có | Không | REVOKE |
| CRM CUSTOMER_EXPORT | Có | Không | REVOKE, ưu tiên cao |
| Finance REPORT_READER | Không | Có | Access request/role assignment mới |
| Finance INVOICE_APPROVER | Không | Có điều kiện | Review SoD và phê duyệt riêng |
| Project Alpha editor | Có | Tùy việc còn tham gia | RETAIN hoặc REVOKE theo quan hệ mới |

### Review phải xem cả phần cấp mới và phần gỡ cũ

Một Mover hoàn tất khi **desired effective permissions** khớp observed state mới. Nếu reviewer xác nhận Finance Reader nhưng bỏ qua Sales Export, vẫn còn quyền tồn dư.

### Sự kiện đến muộn

Nếu campaign lấy snapshot trước Mover, không dùng **RETAIN** trên snapshot để tái cấp quyền đã bị JML thu hồi. Cần version/fencing, re-evaluate hoặc đánh dấu **SUPERSEDED** nếu quyền/quan hệ thay đổi đáng kể.

## 21. Review decision trong Leaver lifecycle

**Leaver là sự kiện cắt quyền**, không nên chờ một access review campaign kết thúc rồi mới deprovision nếu policy đã yêu cầu thu hồi theo effectiveAt.

### Quan hệ với review decision

- Hệ thống chủ động **disable account** hoặc thu hồi quyền theo JML.
- Mọi item đang Pending Review cho quan hệ đã kết thúc phải **được vô hiệu/re-evaluate**, không tự CERTIFY.
- Quyết định **RETAIN** trước Leaver không cho phép vượt sự kiện Leaver mới hơn.
- Quyết định **REVOKE** trong review có thể hỗ trợ kiểm toán nhưng **không phải điều kiện duy nhất để cắt quyền**.
- Đối soát **SCIM group, local account, PAM grant, cloud role, API key, token/session** và quyền direct.
- Nếu quyền còn tồn dư, tạo **finding** có owner, deadline và biện pháp giảm thiểu.

### Một người có nhiều quan hệ

Một người có thể có hai relationship hợp lệ độc lập. Khi kết thúc một relationship, phải xác định **quyền nào có nguồn từ quan hệ đó**. Không tự xóa mọi tài khoản theo email hoặc giữ mọi entitlement do một quan hệ còn hoạt động nếu **quyền cụ thể thuộc quan hệ đã hết hạn**.

### Rejoiner

Khi người đã nghỉ quay lại, **quyết định RETAIN từ kỳ review trước không tự phục hồi**. Eligibility và entitlement phải được tính lại theo role/relationship mới, proofing/enrollment hiện hành và approval phù hợp.

## 22. Privileged access review: Admin, PAM, PIM và JIT

Quyền đặc quyền có thể gây tổn hại lớn ngay cả khi chỉ tồn tại ngắn hạn.

| Đối tượng | Nội dung quyết định |
|---|---|
| **Standing admin role** | Có thể thay bằng scoped JIT hay cần giữ thường trực? |
| **PIM eligibility** | Người đó còn nên đủ điều kiện kích hoạt role đặc quyền? |
| **Active JIT grant** | Còn lý do nghiệp vụ hay phải revoke ngay? |
| **PAM privileged session** | Phiên vẫn thuộc incident hợp lệ và được giám sát? |
| **Break-glass account** | Owner, kiểm soát credential, khả năng dùng khẩn và review mỗi lần sử dụng? |
| **Cloud IAM role binding** | Quyền có giới hạn project/subscription/tenant? |
| **Database admin access** | Có vượt nhu cầu SELECT/maintenance cụ thể? |

### Không nhầm eligibility với active

Review **ELIGIBLE_ROLE=PROD_ADMIN** có thể dẫn đến REVOKE eligibility của một người; dù hiện không có grant Active, vẫn cần xử lý các grant và token đã phát trước đó theo chính sách.

### Đừng mặc định xóa break-glass

Tài khoản emergency có thể ít dùng hoặc không dùng suốt nhiều tháng nhưng vẫn có **chức năng khẩn cấp hợp lệ**. Cần kiểm tra owner, rủi ro, credential protection, drill/test và post-use review; không lấy **zero usage** làm tiêu chí duy nhất.

## 23. Review decision cho service account, workload và device identity

**Non-human identities** không có manager theo HRIS như nhân viên. Những đối tượng gồm **service account, bot, CI/CD pipeline, cloud service principal, workload identity và device identity** cần review riêng.

### Bằng chứng cần có

| Trường | Ví dụ |
|---|---|
| **Workload ID** | workload:reporting-batch |
| **Owner team / sponsor** | Analytics Platform |
| **Business purpose** | Sinh báo cáo tài chính hàng đêm |
| **System/resource** | Storage reports-prod, queue notifications |
| **Permission** | object.read, message.publish |
| **Credential type** | Workload federation, managed identity, certificate |
| **Environment/tenant** | Production, tenant org-vn |
| **Last use / execution evidence** | Job runs và API audit trong thời gian hợp lệ |
| **Review/expiry** | Ngày review tiếp, ngày workload ngừng |
| **Dependency** | Job production hoặc dịch vụ khác phụ thuộc |

### Những quyết định phù hợp

- **RETAIN** khi workload active, owner hợp lệ, quyền tối thiểu và credential được bảo vệ.
- **MODIFY** để giảm cloud role hoặc thay shared secret bằng workload federation.
- **REVOKE** khi workload đã retire hoặc quyền vượt mục đích.
- **ESCALATE** khi không còn owner hoặc không xác định được tác động của một account quan trọng.
- **EXCEPTION** có thời hạn nếu legacy application chưa hỗ trợ cơ chế an toàn hơn.

**Owner nhân viên Leaver không tự đồng nghĩa workload phải bị xóa.** Cần chuyển ownership, xem lại secret mà người cũ có thể đã biết và đánh giá quyền theo workload lifecycle.

## 24. Review decision cho contractor, partner và guest

Các account ngoài tổ chức thường có vòng đời từ **hợp đồng, sponsor và hệ thống quản lý đối tác**, không nhất thiết nằm trong HRIS nhân viên.

### Reviewer nên kiểm tra

- **Sponsor** đang active và còn thẩm quyền bảo trợ?
- Hợp đồng/engagement còn hiệu lực?
- Guest account thuộc đúng đối tác/tenant?
- Quyền có giới hạn vào project, dataset và thời hạn hợp đồng?
- Mức **MFA/federation trust** có đủ?
- Đã có action/permission vượt hợp đồng hoặc dữ liệu nhạy cảm?
- Có session/API key/local credential độc lập?
- Khi sponsor Leaver, quyền guest có được route tới owner mới?
- Khi hợp đồng hết, IAM có tự động thu hồi thay vì chờ campaign quý tiếp theo?

### Không dùng “guest” làm nhóm quyền chung

Một nhà thầu kỹ thuật production và một đối tác chỉ đọc tài liệu đều có thể là guest, nhưng **không nên cùng hưởng chính sách review và retention**. Quyết định phải theo **risk, resource scope và relationship**.

## 25. SoD và toxic combinations trong review decision

**Separation of Duties (SoD)** có thể yêu cầu người dùng không được nắm hoặc thực thi đồng thời những quyền xung đột.

Ví dụ:

~~~text
Permission A: vendor.create
Permission B: vendor.payment.approve

Policy:
  No subject may hold both A and B
  for the same financial control scope
  unless explicitly permitted by a documented control design.
~~~

**Quy tắc này là ví dụ nghiệp vụ**, không phải chuẩn bắt buộc của tất cả tổ chức.

### Những rủi ro cần nhận diện

1. Cặp quyền xung đột nằm ở **hai role khác tên**.
2. Role hierarchy kế thừa permission mà reviewer không nhìn thấy.
3. Một quyền tới từ **nested group**, quyền kia từ direct grant.
4. Người dùng có cả action **requestAccess** và **approveOwnAccess**.
5. Quyền chỉ xung đột với **một resource cụ thể**, không phải toàn app.
6. Một JIT grant tạm thời kết hợp với standing role tạo SoD conflict.
7. Người reviewer có xung đột khi chứng nhận chính quyền mình.

### Cách xử lý

- Tính **effective permission set** kèm scope.
- Xem nguồn và thời điểm của từng grant.
- Ưu tiên **thu hồi/điều chỉnh** quyền không còn cần.
- Nếu dùng **compensating control**, cần phê duyệt ngoại lệ hợp lệ, thời hạn, owner và audit.
- Không chỉ gắn nhãn **RETAIN** cho cả hai role vì hai manager khác nhau cùng duyệt.

## 26. Decision và remediation: hai state machine độc lập

Một mô hình có thể thiết kế:

~~~mermaid
stateDiagram-v2
    [*] --> PendingReview
    PendingReview --> NeedInfo: Thiếu bằng chứng
    NeedInfo --> PendingReview: Có thông tin mới
    PendingReview --> Retained: Chứng nhận có căn cứ
    PendingReview --> RevokeDecided: Yêu cầu thu hồi
    PendingReview --> ModifyDecided: Yêu cầu chỉnh quyền
    PendingReview --> Escalated: Reviewer thiếu thẩm quyền
    Escalated --> PendingReview: Reviewer hợp lệ xử lý
    RevokeDecided --> Remediating: Dispatch revoke
    ModifyDecided --> Remediating: Dispatch update
    Remediating --> Verified: Target readback khớp
    Remediating --> Partial: Còn quyền dư hoặc thao tác thất bại
    Partial --> Remediating: Remediation retry có kiểm soát
    Retained --> Closed: Quyết định hợp lệ, không có conflict mới
    Verified --> Closed
    Closed --> [*]
~~~

Sơ đồ là **workflow tham khảo**. Một hệ thống có thể có các state riêng cho deny, cancellation, exception, campaign closure và quyền hết hiệu lực. Quan trọng là **remediation chưa verified thì không đồng nghĩa item đã giải quyết quyền thực tế**.

### Tránh last-writer-wins

Không cho phép một kết luận RETAIN tới muộn ghi đè một quyết định REVOKE đã phát sinh từ Leaver/incident hoặc một source version mới hơn. Thiết kế phải có **event ordering, version checking và điều kiện commit**.

## 27. Từ REVOKE/MODIFY đến SCIM và hệ thống đích

Một quyết định cần chuyển thành thao tác tại nơi quyền thực sự tồn tại.

### Ví dụ với SCIM 2.0

- IAM/IGA xác định **target User id** và **Group id** qua mapping đáng tin.
- Nếu quyền đến từ membership, connector gửi thao tác phù hợp để **gỡ User khỏi Group.members**.
- Nếu quyết định xét cả account và Leaver, connector có thể **deactivate User** theo chính sách và khả năng provider.
- Nếu quyền qua **API riêng** của SaaS, dùng connector phù hợp.
- Sau thao tác, đọc **User/Group/entitlement** để xác minh trạng thái.

**SCIM User.groups trong core schema là read-only.** Không tự coi việc cập nhật một trường groups phía User là cách chuẩn để gỡ mọi membership. Cần dùng Group.members hoặc API được nhà cung cấp hỗ trợ.

### Ví dụ PATCH /Groups/{groupId} để gỡ membership

~~~http
PATCH /scim/v2/Groups/group-finance-reader HTTP/1.1
Host: app.example.org
Authorization: Bearer <REDACTED_CONNECTOR_TOKEN>
Content-Type: application/scim+json
~~~

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"app-user-7839\"]"
    }
  ]
}
~~~

Ví dụ dựa trên cú pháp SCIM PATCH lọc phần tử của thuộc tính đa trị; cần xác nhận **PATCH, filtering trên valuePath và các hành vi triển khai** được service provider hỗ trợ. Đường dẫn **/scim/v2** là tiền tố minh họa, không bắt buộc cho mọi sản phẩm.

### Không tự suy từ HTTP 200

HTTP 200/204 có thể báo thao tác được chấp nhận theo giao thức, nhưng quyền hiệu lực có thể vẫn tới từ role khác hoặc session/token độc lập. Với quyết định rủi ro cao, cần **readback quyền và kiểm tra action** phù hợp.

## 28. IdP, SSO, OAuth và token cũ sau review decision

Access review và review decision có thể thay đổi entitlement ở IdP/IGA, nhưng người dùng có thể còn sử dụng:

- **SSO session** trong IdP hoặc relying party.
- **SAML assertion/ứng dụng local session** đã thiết lập.
- **OAuth access token** chưa hết hạn.
- **Refresh token** nếu chưa bị thu hồi/chặn.
- **API key, PAT, SSH key, certificate** ở ứng dụng khác.
- **Role/permission cache** của resource server.

### Ví dụ

Review quyết định **REVOKE role FINANCE_EXPORT** lúc 10:00. SCIM gỡ group lúc 10:01, nhưng API dùng JWT đã phát lúc 09:55 với claim export và exp=11:00. Nếu API chỉ tin token cũ và không kiểm **quyền hiện hành**, user vẫn có thể export đến lúc token hết hạn.

**Chiến lược thu hồi cần phù hợp mức rủi ro và khả năng thực tế**: invalidation cache, kiểm trạng thái quyền hiện hành, introspection/revocation, TTL thích hợp, block tại gateway/resource server hoặc thu hồi local session.

### Không nhầm ID token và access token

**OIDC ID token** phục vụ xác nhận đăng nhập cho client, không phải bằng chứng runtime authorization tới mọi API. **OAuth access token** dùng cho resource server và cũng cần kiểm audience/scope/quyền trên đối tượng; scope không tự thay thế RBAC/ABAC.

## 29. Kiểm soát concurrency, retry và idempotency của review decision

Hệ thống IGA thường có queue, batch, webhook, connector timeout hoặc chạy lại job. Cần bảo vệ tránh quyết định cũ gây tái cấp quyền.

### Các tình huống

| Tình huống | Rủi ro | Xử lý phù hợp |
|---|---|---|
| **Reviewer bấm hai lần** | Tạo nhiều tác vụ gỡ/cấp | Deduplicate theo reviewItemId + decisionVersion |
| **Connector timeout** | Không biết revoke đã áp hay chưa | Readback trước retry |
| **HTTP 429/5xx** | Thao tác thất bại tạm thời | Backoff có giới hạn và escalation |
| **Leaver sau snapshot** | RETAIN cấp lại role đã cắt | Kiểm source JML version/fencing |
| **User Mover khi đang review** | Rationale/role không còn đúng | Re-evaluate hoặc supersede |
| **Hai reviewer khác ý** | Last-writer-wins ngoài policy | Rule combining/quorum rõ |
| **Target account đổi ID** | Revoke sai account | Identity-to-target mapping verify |
| **Group đã xóa** | Operation 404 | Kiểm desired/observed, không retry vô hạn |
| **Một quyền có nhiều nguồn** | Gỡ một grant vẫn còn quyền thực tế | Tính effective permissions và revoke các nguồn không hợp lệ |
| **Remediation rollback** | Quyền đã Leaver được phục hồi | Không khôi phục trạng thái cũ vượt JML mới hơn |

### Pseudocode chống dùng quyết định cũ

~~~text
function applyReviewDecision(reviewItemId, decisionVersion):
    item = loadReviewItem(reviewItemId)
    decision = loadDecision(reviewItemId, decisionVersion)

    if decision.itemVersion != item.snapshotVersion:
        return STALE_DECISION

    identity = loadCurrentAuthoritativeIdentity(item.subjectId)
    relationship = loadCurrentRelationship(item.relationshipId)
    target = resolveVerifiedTargetAccount(item.targetAccountId)

    desired = calculateCurrentDesiredAccess(
        identity, relationship, item.entitlement, item.scope, policies
    )

    if identity.isLeaverOrDisabledFor(item.relationshipId):
        desired.mustNotRetainObsoleteAccess = true

    if newerJmlEventSupersedes(decision.sourceVersion):
        return REEVALUATE_BEFORE_ACTION

    if decision.type == RETAIN:
        if not currentPolicySupportsRetention(item, desired):
            return REEVALUATE
        recordAttestationWithoutRegrantingOldAccess()
        return CERTIFIED

    if decision.type in [REVOKE, MODIFY]:
        plan = calculateMinimalTargetChanges(decision, desired, target)
        enforceNoUnexpectedPrivilegeEscalation(plan)
        applyChangesWithIdempotentOperations(plan)
        observed = readBackTargetEffectiveAccess(target)
        if not observedMatchesDesired(observed, desired):
            createRemediationFindingWithOwnerAndDeadline()
            return PARTIAL
        return VERIFIED

    return WAIT_FOR_AUTHORIZED_RESOLUTION
~~~

Đây là **giả mã**, không phải code sản xuất; logic thực tế phải bảo vệ race condition tại thời điểm commit, nhiều quan hệ song song, đối tượng target và mọi đường cấp quyền.

### Điều kiện quan trọng

**RETAIN là một quyết định chứng nhận, không phải lệnh grant tự động.** Điều này giúp ngăn review cũ vô tình phục hồi quyền đã bị thu hồi.

## 30. Review decision phải lưu gì để phục vụ audit?

Một audit record cần giúp trả lời:

> Ai chứng nhận hoặc từ chối quyền của ai, trên tài nguyên nào, đã thấy dữ liệu gì, lúc nào, dựa vào chính sách nào; nếu quyết định yêu cầu thu hồi/chỉnh sửa thì đã thực hiện và xác minh ra sao?

### Ví dụ review decision

~~~json
{
  "decisionId": "review-dec-20261123-042",
  "campaignId": "quarterly-critical-access-2026q4",
  "reviewItemId": "item-crm-export-2046",
  "reviewItemVersion": 5,
  "subjectId": "person-2046",
  "relationshipId": "employment-2046-v1",
  "targetSystem": "crm-production",
  "targetAccountId": "crm-user-7839",
  "entitlementId": "crm-customer-export",
  "resourceScope": {"tenantId": "org-vn", "region": "north"},
  "observedAt": "2026-11-23T08:30:00+07:00",
  "reviewerId": "manager-7812",
  "decision": "REVOKE",
  "reasonCode": "ROLE_CHANGED_NO_LONGER_REQUIRED",
  "reviewedAt": "2026-11-23T09:20:00+07:00",
  "policyVersion": "access-review-v6",
  "remediationState": "PENDING",
  "correlationId": "review-corr-a013"
}
~~~

Đây là **schema nội bộ minh họa**, không phải chuẩn bắt buộc của IGA hay SCIM.

### Các trường audit cần phân biệt

- **review decision:** RETAIN/REVOKE/MODIFY cùng reason và reviewer authority.
- **remediation operation:** đã gửi lệnh gì, target, operation ID, kết quả giao thức.
- **observed result:** readback sau xử lý, thời điểm và coverage.
- **runtime evidence:** action/permission thực tế có còn cho phép không khi cần kiểm chứng.
- **exception/remediation finding:** điều chưa đạt, owner, SLA và biện pháp bù trừ.

**Không log password, access token, refresh token, API key, private key hoặc nội dung hồ sơ nhân sự vượt mức cần thiết.** Bảo vệ audit log khỏi sửa trái phép, quản lý quyền truy cập và thời hạn lưu theo chính sách.

## 31. Quản lý dữ liệu nhạy cảm và quyền riêng tư trong Access review

Một campaign có thể trình bày nhiều dữ liệu cá nhân: người quản lý, phòng ban, vai trò, lịch sử đăng nhập, ứng dụng được sử dụng và phạm vi dữ liệu.

### Các nguyên tắc

1. **Data minimization:** chỉ hiển thị thông tin cần để quyết định.
2. **Need-to-know:** manager chỉ xem item thuộc phạm vi có thẩm quyền.
3. **Tenant isolation:** không để reviewer tenant A xem dữ liệu nhạy cảm của tenant B.
4. **Pseudonymization khi phù hợp:** dùng stable ID và metadata cần thiết thay vì xuất toàn bộ PII.
5. **Protected decision logs:** không để người dùng sửa kết luận hoặc actorId sau khi ghi.
6. **Usage privacy:** dữ liệu tần suất truy cập phục vụ quản trị quyền, không tùy tiện dùng cho đánh giá cá nhân ngoài mục đích.
7. **Retention:** giữ evidence theo policy/luật áp dụng; không giữ vô hạn chỉ vì “để chứng minh”.
8. **Reviewer lifecycle:** xóa quyền truy cập campaign khi reviewer Mover/Leaver hoặc delegation hết hạn.

**Quyền được xem review dữ liệu cũng là một entitlement**, cần kiểm soát như quyền truy cập hệ thống thông thường.

## 32. Những sai lầm phổ biến trong Review decision

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| **Bulk approve vô điều kiện** | Giữ quyền thừa hàng loạt | Hiện rủi ro, giới hạn bulk action, yêu cầu reason |
| **Không hiểu tên role** | Chứng nhận nhầm quyền admin | Catalog giải thích action/effective permission |
| **Chỉ xem quyền trong IdP** | Bỏ sót local/direct grants | Target inventory và reconciliation |
| **RETAIN vì chưa có usage** | Thiếu căn cứ đúng hoặc hiểu sai | Đối chiếu nhiệm vụ, risk, owner |
| **RETAIN vì đang dùng nhiều** | Hợp thức hóa quyền trái chính sách | Desired state, SoD và scope |
| **Reviewer tự chứng nhận admin** | Xung đột lợi ích | Independent review theo SoD |
| **Thiếu source version** | Mở lại quyền sau Mover/Leaver | Snapshot/version/fencing |
| **Không phân biệt eligible/active** | Bỏ sót privileged JIT | Review cả PIM eligibility và grant đang active |
| **Chỉ gỡ direct role** | Nested group vẫn cấp cùng quyền | Effective permissions và các nguồn grant |
| **REVOKE = Completed ngay** | Quyền thực tế vẫn còn | Remediation + readback |
| **Không xử lý token cũ** | Session tiếp tục truy cập | Token/session/cache strategy |
| **Mặc định no-response là certify** | Quyền thừa được giữ không xét | Escalation/default policy rõ |
| **Xóa mọi orphan account** | Gián đoạn service/break-glass hợp lệ | Xác minh owner và mức rủi ro trước hành động |
| **Rà soát sai tenant** | Chỉnh quyền sai đối tượng | Immutable IDs và tenant constraints |
| **Quyết định Modify không có approval** | Tăng quyền qua lối tắt | Re-evaluate như request mới khi mở rộng |
| **Đóng campaign khi còn Partial** | Báo cáo tuân thủ sai | Tách review closure và remediation closure |
| **Không có owner finding** | Sai lệch kéo dài | Ticket, SLA, escalation |
| **Reviewer Mover/Leaver vẫn có quyền duyệt** | Chứng nhận trái thẩm quyền | Kiểm reviewer authority trước quyết định |

## 33. Chỉ số đánh giá Review decision và hiệu quả khắc phục

| Metric | Cách sử dụng | Lưu ý |
|---|---|---|
| **Review completion rate** | Tỷ lệ item có quyết định hợp lệ | Không đo chất lượng quyết định một mình |
| **Retain/Revoke/Modify distribution** | Phân bố kết luận theo hệ thống/rủi ro | Tỷ lệ Revoke thấp không tự chứng minh an toàn |
| **Bulk-certification rate** | Theo dõi duyệt hàng loạt | Cần giám sát item nhạy cảm |
| **Reviewer reassignment rate** | Phát hiện owner mapping yếu | Đo cả độ chính xác route |
| **Overdue aging** | Item quá hạn và rủi ro | Escalate không mặc định approve |
| **High-risk entitlement coverage** | Tỷ lệ admin/export/secret role được review | Phải tính effective grants ngoài IdP |
| **Review evidence freshness** | Độ tuổi dữ liệu target/JML | Giảm quyết định dựa snapshot lỗi thời |
| **SoD conflicts found** | Quyền xung đột cần xử lý | Giới hạn bởi coverage |
| **Revocation verified rate** | Tỷ lệ REVOKE có readback xác minh | Phân biệt HTTP ack và observed |
| **Modification verified rate** | Tỷ lệ MODIFY đạt scope/role mới | Cần xem cả quyền dư và thiếu |
| **Decision-to-revoke latency** | Từ review decision tới khi quyền bị chặn | Quan trọng với quyền rủi ro cao |
| **Leaver residual access** | Quyền còn sau effectiveAt | Không chờ campaign kế tiếp |
| **Unowned grant findings** | Grant thiếu owner hoặc nguồn approval | Cần điều tra trước khi tự xóa |
| **Reconciliation coverage** | Tỷ lệ target có thể đọc/đối chiếu đầy đủ | Ghi rõ khoảng trống |
| **Policy exception aging** | Ngoại lệ còn mở quá hạn | Chống ngoại lệ vô hạn |
| **Reviewer decision consistency** | Sai lệch giữa các reviewer trên trường hợp tương tự | Không biến thành ép toàn bộ phải RETAIN |

### Không tối ưu KPI theo hướng làm sai mục tiêu

Nếu đặt mục tiêu “review xong 100% trước thứ Sáu” mà không đo việc **thật sự thu hồi quyền dư**, nhân viên có thể bulk certify để đạt chỉ tiêu. Kết quả cần đánh giá cùng **risk reduction, remediation, evidence quality và effective access**.

## 34. Kiểm thử các quyết định và workflow

Một hệ thống access review cần kiểm **dữ liệu, authority, decision và remediation**.

| Test case | Tình huống | Kết quả mong đợi |
|---|---|---|
| **Retain hợp lệ** | Reviewer đúng owner, user ACTIVE, quyền đúng | RETAIN có evidence |
| **Leaver** | Subject đã TERMINATED | Không cho RETAIN quyền cũ trái policy |
| **Mover** | Đổi Sales → Finance | Sales export REVOKE, không tự tái cấp |
| **Reviewer không thẩm quyền** | Người ngoài scope bấm Certify | Từ chối thao tác |
| **Self-review bị cấm** | User chứng nhận chính admin role | Reassign/deny |
| **Snapshot cũ** | Event JML mới hơn review item | Re-evaluate/supersede |
| **Group lồng nhau** | Gỡ direct grant nhưng nested grant còn | Không báo VERIFIED |
| **Quyền qua hai nguồn** | Role A và Group B cùng cấp action | Tính lại effective access |
| **No response** | Reviewer hết hạn chưa quyết định | Theo overdue/escalation policy, không tự certify |
| **Role thiếu owner** | Không xác minh business purpose | Need info/escalate |
| **Modify thành quyền rộng hơn** | Reader → Admin | Yêu cầu approval tăng quyền |
| **JIT đã hết hạn** | Reviewer Retain trên item cũ | Không mở grant Active trở lại |
| **Token còn role cũ** | SCIM đã gỡ group | Resource server phải chặn theo policy thu hồi |
| **Connector timeout** | Target đã revoke nhưng response mất | Readback trước retry |
| **Partial revoke** | Một số target còn quyền | Finding và tiếp tục xử lý |
| **Cross-tenant** | Reviewer tenant A thao tác item tenant B | Deny |
| **Multiple relationships** | Một quan hệ kết thúc, quan hệ khác còn | Chỉ giữ quyền có căn cứ hợp lệ |
| **Service owner Leaver** | Workload còn hoạt động | Chuyển owner và review, không xóa bừa |
| **Break-glass unused** | Không có usage thường xuyên | Review cơ chế và nhu cầu, không tự xóa |
| **Compensating control expired** | Exception giữ quyền quá hạn | Escalate/revoke theo policy |

### Nhóm test nên có

1. **Policy unit tests**: Retain/Revoke/Modify, SoD, reviewer authority.
2. **Data quality tests**: missing owner, duplicate ID, wrong tenant, unknown grant source.
3. **Workflow tests**: reassign, overdue, version, conflict, multiple reviewer.
4. **JML regression tests**: Joiner, Mover, Leaver, Rejoiner, stale approvals.
5. **Integration tests**: SCIM, IdP, PAM, app API, cloud IAM.
6. **Concurrency tests**: decision cạnh tranh với revocation hoặc provisioning.
7. **Failure injection**: timeout, 429, 5xx, partial update, unavailable PDP.
8. **Runtime tests**: quyền bị thu hồi thực sự không còn cho phép action.
9. **Audit tests**: nối được decision–operation–readback, không lộ secret.

## 35. Runbook: khi review decision không thể hoàn tất

### A. Reviewer không hiểu quyền

1. Xác định entitlement ID, hệ thống đích, tenant và action thực tế.
2. Mở catalog description và mapping role/group/permission.
3. Kiểm effective permissions qua hierarchy và direct grants.
4. Liên hệ resource/application owner có thẩm quyền.
5. Dùng **NEED_MORE_INFO** hoặc **ESCALATE**, không bấm RETAIN vô căn cứ.
6. Ghi thiếu sót catalog để cải thiện chiến dịch sau.

### B. Reviewer không còn đủ thẩm quyền

1. Kiểm reviewer identity, lifecycle, delegation và owner assignment.
2. Đối chiếu resource owner/team hiện hành.
3. Reassign cho đúng người hoặc policy review authority.
4. Vô hiệu quyết định chưa hợp lệ.
5. Ghi sự kiện reassignment và thông báo thời hạn mới.
6. Không tự đưa người xin quyền thành reviewer thay thế.

### C. Reviewer đã REVOKE nhưng người dùng vẫn truy cập được

1. Xác định **decisionId, reviewItem, target account và entitlement**.
2. Xem connector đã gửi thao tác đến đúng hệ thống/tenant chưa.
3. Readback role/group/direct permission, gồm nested/role hierarchy.
4. Kiểm session, JWT/access token, refresh token, local account và API key.
5. Chặn action rủi ro ở PEP/RS khi có thể.
6. Mở finding owner, SLA, compensating controls và evidence.
7. Đóng khi **effective access** đã khớp desired state trong phạm vi xác minh.

### D. RETAIN bị ghi sau Leaver hoặc Mover

1. Dừng các tác vụ grant/regrant dựa decision lỗi thời.
2. Lấy nguồn JML hiện hành cùng version/effectiveAt.
3. Xác định account/entitlement nào đã bị mở lại.
4. Thu hồi/chặn những quyền trái policy.
5. Sửa logic snapshot/version/fencing và kiểm thử race condition.
6. Ghi incident/audit nếu có khả năng truy cập dữ liệu trái thẩm quyền.

### E. Revoke gây gián đoạn dịch vụ

1. Xác định quyền bị gỡ, target và phụ thuộc của workload/người dùng.
2. Đối chiếu review rationale và owner nghiệp vụ.
3. Xem có **grant khác hợp lệ** hoặc một giải pháp scoped/JIT được phê duyệt không.
4. Không phục hồi global-admin mù quáng để “chạy lại”.
5. Cấp lại đúng quyền nếu có **approval mới hoặc policy hợp lệ** và không vi phạm JML.
6. Bổ sung dependency mapping, owner và test vào kỳ review tiếp theo.

## 36. Tình huống xuyên suốt: Review decision qua JML

Giả sử **Lan** gia nhập công ty ở vị trí Sales, sau đó chuyển sang Finance và cuối cùng nghỉ việc. Doanh nghiệp dùng **HRIS, IAM/IGA, IdP SSO/MFA, SCIM** cho CRM và một ứng dụng Finance có RBAC/ABAC.

### Giai đoạn 1 — Joiner

HRIS tạo identityId **person-2046** và quan hệ làm việc có effectiveAt. IAM provision account ở IdP và nhóm Sales Reader ở CRM. Lan xin thêm quyền export theo dự án; request có owner và approval riêng. Trong đợt post-onboarding review, manager thấy hai item: **SALES_READER** và **CUSTOMER_EXPORT**. Manager chọn **RETAIN Reader**, yêu cầu Security kiểm quyền export và thời hạn.

### Giai đoạn 2 — Review quyền export

Security thấy quyền export chỉ cần cho một đợt migration. Quyết định **MODIFY** từ entitlement export thường trực sang **JIT export** trên dataset đã duyệt trong cửa sổ ngắn. Connector gỡ role export rộng và cấu hình grant có hạn; target readback xác minh không còn export ngoài scope.

### Giai đoạn 3 — Mover

Lan chuyển sang Finance. HRIS phát sự kiện Mover, IAM tính quyền Finance Reader và thu hồi Sales permissions. Trong lúc đó, campaign access review dùng snapshot cũ vẫn hiển thị **SALES_READER**. Một reviewer bấm RETAIN trên item cũ; workflow phát hiện sourceVersion JML mới hơn và **không tái cấp role Sales**.

### Giai đoạn 4 — SoD review

Lan được yêu cầu tham gia approval hóa đơn. Trước khi cấp role mới, IGA tính effective permissions để kiểm tra khả năng Lan vừa tạo vừa duyệt cùng giao dịch. Reviewer có đủ quyền chỉ chứng nhận role nếu không vi phạm SoD, và runtime authorization vẫn chặn **invoice.approve** trên chính hóa đơn Lan tạo.

### Giai đoạn 5 — Leaver

Lan nghỉ việc hiệu lực ngay. IAM disable IdP và deprovision qua SCIM/API, đồng thời xử lý session/token và quyền local. Một item review từ campaign cũ có decision RETAIN không thể vượt sự kiện Leaver. Security và application owner kiểm chứng CRM không còn cho **customer.export**, Finance không còn cho **invoice.approve**, và những API key/direct grants đã được xử lý.

### Giai đoạn 6 — Rejoiner

Lan quay lại với công việc khác. IAM có thể liên kết identity lịch sử theo chính sách, nhưng phải xác minh relationship mới, quyền mới và scope. **Không tự kích hoạt lại decision RETAIN, approval hay JIT grant cũ**. Access review sau onboarding kiểm đúng các entitlement của công việc hiện tại.

### Kết luận tình huống

**Review decision chỉ có giá trị khi gắn với đúng người, đúng quyền, đúng phiên bản dữ liệu, đúng người duyệt và đúng nguồn công việc còn hiệu lực.** Việc thu hồi/chỉnh quyền phải được kiểm chứng tại đích, không dừng ở hồ sơ review.

## 37. Checklist để một Review decision đáng tin cậy

1. **Khái niệm:** đã tách review decision khỏi access request approval, authorization và provisioning?
2. **Item scope:** có subjectId, target account, entitlement, action, resource/tenant rõ?
3. **Nguồn cấp:** đã biết grant đến từ business role, group, direct permission, exception hay JIT?
4. **Effective permissions:** đã tính nested groups, role hierarchy, grant kép, direct grants và scope?
5. **JML:** identity/relationship hiện hành, effectiveAt và source version đã được xác minh?
6. **Reviewer authority:** người duyệt có quyền theo resource/tenant, không self-review trái SoD?
7. **Evidence:** reviewer nhìn thấy purpose, owner, approval, expiry, usage và data freshness?
8. **Risk:** đã phân loại quyền admin, export, secret, cross-tenant và SoD conflict?
9. **Decision types:** RETAIN, REVOKE, MODIFY, NEED_MORE_INFO, ESCALATE, EXCEPTION được tách rõ?
10. **Retain:** có căn cứ công việc và không biến thành cấp lại/renew vô hạn?
11. **Revoke:** xác định đúng grant source/đối tượng, không xóa nhầm account/group khác?
12. **Modify:** nếu tăng quyền, có đưa qua access request approval tương ứng?
13. **Exceptions:** có risk owner, thời hạn và controls, không hợp thức hóa quyền đã hết căn cứ?
14. **Overdue:** no-response không tự được tính là Certified?
15. **Campaign:** snapshot as-of, observedAt và review item version được lưu?
16. **Stale decision:** Mover/Leaver mới hơn có chặn RETAIN/regrant?
17. **SCIM/API:** thao tác gỡ group/role đúng tenant và target ID được kiểm chứng?
18. **Token/session:** quyền cũ có thể còn trong JWT, IdP/SP session, local account hoặc PAT?
19. **PAM/PIM:** có review eligibility khác với Active grant và break-glass?
20. **Service/workload:** non-human identity có owner/purpose và lifecycle riêng?
21. **Contractor/guest:** sponsor và contract expiry có trong desired state?
22. **Security/privacy:** reviewer chỉ xem dữ liệu cần thiết; audit được bảo vệ, không lộ secrets?
23. **Idempotency:** retry/timeout/double decision không tạo regrant trái policy?
24. **Remediation:** REVOKE/MODIFY có operation, owner, SLA và readback?
25. **Effective denial:** target thực sự từ chối action đã bị thu hồi khi chính sách yêu cầu?
26. **Metrics:** đo completion và verified revocation riêng, không chỉ số lượt bấm?
27. **SoD:** review phát hiện toxic permission combinations ở quyền hiệu lực?
28. **Audit:** có decisionId, reviewerId, reasonCode, policyVersion, snapshot và correlation?
29. **Coverage:** những quyền local, cloud hoặc ứng dụng legacy chưa quan sát được được báo rõ?
30. **Closure:** chỉ kết luận khắc phục hoàn tất khi desired và observed khớp hoặc ngoại lệ được quản lý có căn cứ?

### Ghi nhớ

**Review decision là kết luận có căn cứ về việc một quyền truy cập đang tồn tại nên được giữ, thu hồi, điều chỉnh hay cần điều tra thêm.** Một quyết định tốt phải dựa trên **danh tính và quan hệ hiện hành, nhu cầu công việc, effective permissions, risk, SoD, scope, reviewer authority và evidence có thời điểm/phiên bản rõ ràng**. **RETAIN không phải lệnh tái cấp quyền; REVOKE không chứng minh quyền đã bị cắt; MODIFY không được trở thành đường tắt tăng đặc quyền.** Trong **Joiner–Mover–Leaver**, quyết định phải chịu kiểm soát bởi sự kiện JML mới hơn và được thực thi qua **IdP/SSO, SCIM, PAM, RBAC/ABAC, session/token controls và reconciliation** để bảo đảm **quyền không còn căn cứ không tiếp tục tồn dư**.
