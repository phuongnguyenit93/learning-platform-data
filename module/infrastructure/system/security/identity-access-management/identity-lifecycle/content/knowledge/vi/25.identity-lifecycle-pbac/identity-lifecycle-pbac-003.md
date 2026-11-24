# Policy language trong PBAC và quản lý vòng đời danh tính IAM

## 1. Policy language là gì?

**Policy language** là cách biểu diễn các **quy tắc ra quyết định phân quyền** dưới dạng có cấu trúc, đủ rõ để con người quản trị, hệ thống thực thi và công cụ kiểm thử cùng hiểu. Trong **Policy-Based Access Control (PBAC)**, một policy mô tả **ai được thực hiện hành động nào trên tài nguyên nào, trong điều kiện nào**, thay vì đặt rải rác hàng trăm câu lệnh kiểm tra quyền trong từng ứng dụng.

Ví dụ, thay vì chỉ quy định người có role **FINANCE_APPROVER** được duyệt hóa đơn, một policy có thể yêu cầu đồng thời:

- Danh tính còn **ACTIVE** và có quan hệ công việc hợp lệ.
- Người dùng có quyền nghiệp vụ **invoice.approve** tại đúng tenant.
- Hóa đơn ở trạng thái **SUBMITTED** và chưa được người yêu cầu tự tạo.
- Số tiền không vượt **hạn mức duyệt** đã được phê duyệt.
- Phiên đáp ứng **MFA/step-up** của thao tác nhạy cảm.
- Quyền được ủy quyền chưa hết hạn và không vi phạm **Separation of Duties (SoD)**.

Đây là ngữ nghĩa của **chính sách**, không phải một loại token, một tài khoản hay một role. Ngôn ngữ policy cung cấp **cú pháp**, **kiểu dữ liệu**, **cách đánh giá**, **quy tắc kết hợp** và đôi khi cả **metadata/audit** để triển khai kiểm soát nhất quán.

Bài học thuộc chương **PBAC** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mục tiêu chung của mô-đun là quản lý danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản và cấp quyền đến rà soát, thu hồi khi thay đổi vai trò; liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm **quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **ngôn ngữ policy**, **policy engine**, **role**, **permission**, **OAuth scope** và **authorization decision**.
2. Định nghĩa yêu cầu dưới dạng **subject–action–resource–context** có kiểu dữ liệu rõ ràng.
3. Hiểu hiệu ứng **Permit/Deny**, mặc định an toàn, xử lý dữ liệu thiếu và xung đột policy.
4. Đọc và viết **policy minh họa**, bao gồm một ví dụ **Rego**.
5. Phân biệt các hướng tiếp cận **Rego/OPA**, **Cedar**, **XACML** và DSL nội bộ, không nhầm cú pháp của các hệ.
6. Tích hợp **PEP, PDP, PIP, PAP**, kiểm soát token/session và quyền tại API.
7. Quản lý **policy lifecycle**: tạo, review, version, test, rollout, rollback, audit.
8. Áp policy cho các sự kiện **Joiner, Mover, Leaver**, service account và quyền có thời hạn.

## 2. PBAC khác RBAC, ABAC và ReBAC thế nào?

Một hệ thống IAM có thể dùng nhiều mô hình phân quyền cùng lúc:

| Mô hình | Trọng tâm | Ví dụ | Điểm giới hạn |
|---|---|---|---|
| **RBAC** | Quyền theo vai trò | FINANCE_READER được đọc báo cáo | Role không đủ mô tả mọi ngữ cảnh |
| **ABAC** | Quyền theo thuộc tính chủ thể, tài nguyên, ngữ cảnh | Chỉ đọc báo cáo thuộc cùng tenant và mức phân loại cho phép | Cần thuộc tính đáng tin, cập nhật |
| **ReBAC** | Quyền theo quan hệ | Owner/member/reviewer của project | Phải quản trị đồ thị quan hệ và kế thừa |
| **PBAC** | Quyết định dựa trên chính sách có thể đánh giá | Kết hợp role, tenant, SoD, MFA, thời hạn | Phải thiết kế ngôn ngữ, engine và thực thi đúng |

**PBAC không nhất thiết là mô hình loại trừ RBAC/ABAC/ReBAC.** Trong nhiều thiết kế, PBAC là **lớp điều phối biểu thức policy** sử dụng role, attribute và relationship như đầu vào. Không có một định nghĩa hay một ngôn ngữ PBAC duy nhất áp dụng cho mọi sản phẩm.

Ví dụ: RBAC cấp role **REPORT_READER**, ABAC giới hạn **department=Finance**, ReBAC yêu cầu người dùng thuộc **project-alpha**; một PBAC policy kết hợp các điều kiện để ra quyết định **Permit/Deny** cho action **report.read**.

### Policy khác cấu hình giao diện

Ẩn nút “Export” ở frontend là hành vi trình bày. **Policy được bảo vệ** phải chạy ở server hoặc điểm thực thi tin cậy, vì người dùng có thể gọi trực tiếp HTTP API, GraphQL, message consumer hoặc tác vụ nền.

## 3. Mô hình đầu vào: subject, action, resource và context

Biểu diễn căn bản:

\[
Decision = Evaluate(Policies,\ Subject,\ Action,\ Resource,\ Context)
\]

| Thành phần | Câu hỏi | Dữ liệu minh họa |
|---|---|---|
| **Subject** | Ai hoặc workload nào yêu cầu? | identityId, lifecycleState, roles, tenantId |
| **Action** | Muốn thực hiện thao tác nào? | invoice.approve, report.export |
| **Resource** | Trên đối tượng cụ thể nào? | invoiceId, ownerId, classification, state |
| **Context** | Trong điều kiện nào? | requestTime, authenticationAssurance, deviceTrust |
| **Policy** | Quy tắc nào áp dụng? | Chỉ approver cùng tenant, không tự duyệt |
| **Decision** | Có thể thực thi không? | Permit, Deny hoặc giá trị nội bộ khác |

Một yêu cầu kiểm tra phân quyền có cấu trúc minh họa:

~~~json
{
  "subject": {
    "identityId": "person-2046",
    "tenantId": "org-vn",
    "lifecycleState": "ACTIVE",
    "roles": ["FINANCE_APPROVER"],
    "approvalLimitMinor": 100000000
  },
  "action": "invoice.approve",
  "resource": {
    "invoiceId": "INV-873",
    "tenantId": "org-vn",
    "createdBy": "person-7812",
    "state": "SUBMITTED",
    "amountMinor": 8500000
  },
  "context": {
    "strongAuthentication": true,
    "requestTime": "2026-11-23T09:00:00+07:00"
  }
}
~~~

Đây là **schema nội bộ minh họa**, không phải cấu trúc được chuẩn PBAC bắt buộc. Đặc biệt, **roles, tenantId, lifecycleState, createdBy và strongAuthentication không được tin chỉ vì client gửi chúng trong JSON**. PEP hoặc backend phải nạp chúng từ token/phiên đã xác minh, kho tài nguyên và nguồn có thẩm quyền.

### Action mang ngữ nghĩa nghiệp vụ

**invoice.approve** không đồng nghĩa HTTP **POST**. Một POST có thể là **invoice.submit**, **invoice.reject**, **user.assignRole** hoặc **payment.execute**, mỗi action cần quyền và điều kiện khác nhau.

## 4. Một policy language cần những thành phần nào?

Một ngôn ngữ tốt thường có các cấu phần:

| Thành phần | Vai trò | Câu hỏi thiết kế |
|---|---|---|
| **Syntax** | Cách viết rule, biểu thức và khai báo | JSON, DSL, Rego hay XML? |
| **Data model** | Kiểu dữ liệu và cấu trúc đầu vào | String, boolean, list, timestamp, entity? |
| **Policy target** | Phạm vi rule được áp dụng | App, action, resource type, tenant |
| **Condition** | Điều kiện logic | Role, owner, SoD, MFA, giới hạn thời gian |
| **Effect** | Kết quả của rule | Permit/Deny hoặc kết quả engine tương ứng |
| **Combining algorithm** | Cách phối nhiều rule | Deny-overrides, first-applicable hoặc khác |
| **Default behavior** | Không có rule khớp thì sao? | Deny mặc định tại điểm thực thi |
| **Obligation/advice** | Yêu cầu xử lý hoặc khuyến nghị bổ sung | Audit, step-up, gắn nhãn kết quả |
| **Version/metadata** | Truy vết thay đổi | Policy ID, owner, phiên bản, hiệu lực |
| **Evaluation semantics** | Ý nghĩa chính xác của rule khi chạy | Missing field, error, unknown, time, priority |

**Cú pháp dễ đọc không đủ nếu ngữ nghĩa mơ hồ.** Ví dụ “nếu không có rule Deny thì Permit” khác hoàn toàn “chỉ Permit nếu có bằng chứng Permit hợp lệ và không có Deny xung đột”. Mọi engine cần định nghĩa minh bạch cách xử lý **thiếu thuộc tính, lỗi tra cứu, xung đột** và **quyền mặc định**.

## 5. Cú pháp và ngữ nghĩa: hai lớp khác nhau

Xét câu nghiệp vụ:

> Người dùng đang làm việc ở Finance được đọc báo cáo của tenant mình khi báo cáo không vượt mức phân loại được phép.

Một cách viết giả mã:

~~~text
rule FinanceReportReader:
    effect: PERMIT
    when:
        subject.lifecycleState == ACTIVE
        and subject.department == Finance
        and action == report.read
        and resource.tenantId == subject.tenantId
        and resource.classificationLevel <= subject.clearanceLevel
~~~

Đây là **DSL minh họa**, không phải cấu hình có thể chạy trực tiếp trong OPA, Cedar hoặc XACML.

Người thiết kế vẫn phải trả lời:

- **ACTIVE** do HRIS/IGA hay do frontend cung cấp?
- **classificationLevel** có thứ tự số định nghĩa chính thức hay chỉ là tên như PUBLIC/SECRET?
- Nếu **clearanceLevel** không có, rule trả Deny, NotApplicable hay lỗi?
- Nếu hai rule khác cùng khớp, một Permit và một Deny, quyết định cuối là gì?
- Ai kiểm tra **token, tenant, thuộc tính tài nguyên và thời hạn**?
- Decision có còn hợp lệ nếu trạng thái danh tính hoặc role đổi sau khi được tính?
- Hệ thống có phải áp **data masking, audit hoặc step-up** trước khi cho đọc không?

**Policy language phải có hợp đồng ngữ nghĩa**, không chỉ một cấu trúc điều kiện giống câu SQL.

## 6. Những kết quả đánh giá policy

Không phải engine nào cũng dùng cùng kiểu kết quả. Trong **XACML**, các giá trị như **Permit, Deny, NotApplicable, Indeterminate** có ngữ nghĩa chuẩn hóa. Một engine khác có thể chỉ trả boolean hoặc tập kết quả tuỳ chỉnh.

| Kết quả khái niệm | Ý nghĩa | Xử lý an toàn ở PEP |
|---|---|---|
| **Permit** | Các điều kiện cho phép đã được chứng minh | Chỉ thực thi sau kiểm tra nghĩa vụ và trạng thái nghiệp vụ |
| **Deny** | Có quy tắc hoặc điều kiện từ chối | Không thực thi action |
| **NotApplicable** | Không có policy/rule phù hợp | Không được tự biến thành Permit |
| **Indeterminate** | Không thể đánh giá đáng tin vì lỗi/thiếu dữ liệu | Không tự cấp quyền, ghi tín hiệu lỗi và xử lý theo chính sách |
| **RequireStepUp** | Kết quả mở rộng của hệ thống yêu cầu xác thực mạnh hơn | Không thực thi ngay; chỉ cho phép sau khi hoàn thành luồng phù hợp |

**RequireStepUp không phải một quyết định lõi của mọi policy language.** Nó có thể được mô hình hóa thành response riêng, nghĩa vụ hoặc trạng thái trung gian của ứng dụng.

Với hành động nhạy cảm, nguyên tắc thực hành là **fail closed / deny by default** khi không đủ căn cứ cho phép. Tuy vậy, cách hiển thị lỗi và chế độ khôi phục vận hành cần thiết kế riêng để tránh tạo ra tấn công từ chối dịch vụ không kiểm soát.

## 7. Xung đột policy và cách kết hợp quyết định

Ví dụ có hai chính sách:

- **Rule A – Permit:** role FINANCE_APPROVER được duyệt hóa đơn thuộc đơn vị Finance.
- **Rule B – Deny:** bất kỳ người nào cũng không được tự duyệt hóa đơn do chính mình tạo.

Nếu Lan có role approver và là người tạo hóa đơn, cả hai rule có thể khớp. Phải biết **quy tắc ưu tiên** trước khi kết luận.

### Các cách kết hợp thường gặp

| Cách kết hợp | Ý tưởng | Khi nào cần cẩn trọng |
|---|---|---|
| **Deny-overrides** | Có Deny áp dụng thì Deny chiếm ưu thế theo semantics engine | Phải phân biệt Deny thật với lỗi/không áp dụng |
| **Permit-overrides** | Permit có thể chiếm ưu thế theo semantics engine | Không thích hợp nếu guardrail Deny bắt buộc có thể bị vượt |
| **First-applicable** | Chọn rule phù hợp đầu tiên theo thứ tự | Thứ tự rule trở thành yếu tố bảo mật |
| **Only-one-applicable** | Yêu cầu tối đa một policy áp dụng | Cần kiểm soát chồng lấn và lỗi khi nhiều policy khớp |
| **Boolean allow rules + default false** | Permit nếu ít nhất một rule allow đúng, ngoài ra Deny | Cần thiết kế các deny guardrail riêng để không bị một allow khác vượt qua |

Các tên thuật toán có trong các hệ thống như XACML, nhưng **chi tiết xử lý Indeterminate và NotApplicable phụ thuộc định nghĩa của từng thuật toán**, không thể tóm tắt bằng một câu “Deny luôn thắng” cho mọi engine.

### Quy tắc an toàn cho SoD

SoD (Separation of Duties) không nên bị biểu diễn như một allow rule phụ. Nó thường là **ràng buộc bắt buộc**: khi một người là người tạo hóa đơn, thao tác tự duyệt phải bị chặn dù có role đúng.

~~~text
requiredGuards:
    identity.isActive
    resource.tenantId == identity.tenantId
    not resource.createdBy == identity.id
    resource.state == SUBMITTED

businessGrant:
    identity.hasRole(FINANCE_APPROVER)
    resource.amount <= identity.approvalLimit

decision:
    PERMIT only if all requiredGuards and businessGrant
~~~

Ví dụ là logic minh họa; điều kiện actual policy cần gắn vào dữ liệu và thời điểm giao dịch được xác minh.

## 8. Các họ ngôn ngữ policy: Rego, Cedar, XACML và DSL riêng

Không tồn tại một ngôn ngữ PBAC duy nhất bắt buộc cho mọi hệ thống.

| Ngôn ngữ/tiếp cận | Kiểu mô hình | Điểm mạnh | Điều cần lưu ý |
|---|---|---|---|
| **Rego – Open Policy Agent (OPA)** | Ngôn ngữ khai báo trên dữ liệu có cấu trúc | Rule linh hoạt, policy-as-code, test và tích hợp nhiều ngữ cảnh | Phải quy định entrypoint, input schema, default và logic deny |
| **Cedar** | Ngôn ngữ policy theo principal, action, resource và context | Phù hợp authorization theo entity, hỗ trợ policy validation theo schema | Ngữ nghĩa/evaluation theo Cedar, không phải Rego; quản lý entity/relationship |
| **XACML** | Mô hình và ngôn ngữ policy chuẩn hóa với rule, policy set, combining algorithm | Biểu diễn chính sách giàu cấu trúc, kết quả và obligations | XML/độ phức tạp triển khai, khả năng hỗ trợ engine |
| **DSL nội bộ** | Cú pháp do tổ chức thiết kế | Có thể gần với nghiệp vụ đặc thù | Dễ thiếu quy định về lỗi, kiểu, conflict, version và công cụ test |
| **Cấu hình quyền của cloud/SaaS** | Ngôn ngữ policy đặc thù sản phẩm | Tích hợp sâu với resource của nền tảng | Cú pháp và ngữ nghĩa khác nhau, khó suy ra tương đương |

**Các đoạn mẫu của một ngôn ngữ không thể được dán trực tiếp sang ngôn ngữ khác.** Khi chuyển policy engine phải kiểm thử **tính tương đương quyết định** trên các trường hợp cho phép, từ chối và dữ liệu thiếu.

## 9. Ví dụ Rego trong Open Policy Agent (OPA)

Một policy Rego minh họa cho **invoice.approve**. Ví dụ này dùng cú pháp tương thích **Rego v1** và giả định input đã được PEP làm giàu bằng dữ liệu đáng tin.

~~~rego
package iam.invoice

import rego.v1

default allow := false

allow if {
    input.subject.lifecycle_state == "ACTIVE"
    input.action == "invoice.approve"
    input.subject.tenant_id == input.resource.tenant_id
    "FINANCE_APPROVER" in input.subject.roles
    input.resource.state == "SUBMITTED"
    input.subject.id != input.resource.created_by
    input.resource.amount_minor <= input.subject.approval_limit_minor
    input.context.strong_authentication == true
}
~~~

### Giải thích

- **package iam.invoice:** namespace của policy.
- **default allow := false:** không có allow rule hợp lệ thì trả false.
- **input.subject.lifecycle_state:** điều kiện danh tính active.
- **input.action:** chỉ áp cho một action cụ thể, không cho phép các POST khác.
- **tenant_id:** kiểm tra resource cùng tenant.
- **FINANCE_APPROVER in roles:** RBAC là một yếu tố đầu vào.
- **created_by khác subject.id:** ràng buộc SoD chống tự duyệt.
- **amount_minor:** tiền được mô hình bằng đơn vị nhỏ nhất tránh sai lệch float cho hạn mức.
- **strong_authentication:** tín hiệu phiên đã được xác minh từ IdP/PEP, không phải giá trị client tự khai.

### Những điều cần bổ sung khi triển khai thật

Ví dụ này **chưa phải hệ thống authorization hoàn chỉnh**:

1. **Input schema** và nguồn dữ liệu cần được xác minh, đặc biệt lifecycleState và roles.
2. **Những thay đổi quyền đồng thời** phải có chiến lược cache và consistency.
3. Nếu cho phép nhiều rule, phải có chiến lược xử lý **hard deny** và policy combination rõ.
4. PEP phải kiểm tra token/phiên và áp quyết định ở đúng action/resource.
5. Kết quả permit không tự chuyển trạng thái hóa đơn; service phải kiểm **business state** trong giao dịch phù hợp.
6. Phải ghi policy version, reason code và correlation ID qua hệ thống logging được bảo vệ.

### Một phép thử đầu vào

~~~json
{
  "subject": {
    "id": "person-2046",
    "tenant_id": "org-vn",
    "lifecycle_state": "ACTIVE",
    "roles": ["FINANCE_APPROVER"],
    "approval_limit_minor": 100000000
  },
  "action": "invoice.approve",
  "resource": {
    "tenant_id": "org-vn",
    "created_by": "person-7812",
    "state": "SUBMITTED",
    "amount_minor": 8500000
  },
  "context": {
    "strong_authentication": true
  }
}
~~~

Với input này, policy Rego minh họa trả **allow=true**. Nếu đổi **created_by** thành **person-2046**, kết quả là **false**. Đây là phép đánh giá logic trên dữ liệu giả định, không có nghĩa việc duyệt hóa đơn đã được thực thi.

## 10. Cedar: principal, action, resource và entity relationship

Một hướng tiếp cận khác là **Cedar**, thiết kế cho những quyết định dựa trên **principal – action – resource – context**, có thể kiểm tra schema và dùng quan hệ giữa các entity.

### Các khái niệm cần hiểu

- **Principal:** chủ thể yêu cầu action.
- **Action:** thao tác được quản trị.
- **Resource:** tài nguyên cần được bảo vệ.
- **Context:** dữ liệu bối cảnh request.
- **Permit / Forbid:** hai loại hiệu ứng của policy.
- **Entity relationship:** thông tin về membership hoặc mối quan hệ cần để đánh giá.

Trong mô hình quyết định Cedar, **một policy forbid áp dụng có thể chặn dù có permit phù hợp**; không có permit hợp lệ thì mặc định không cho phép. Điều này cần được triển khai với **entity data và schema đúng**, không chỉ sử dụng tên trường mà không xác thực dữ liệu.

### Ví dụ ngữ nghĩa

Một policy permit có thể diễn đạt: “principal thuộc nhóm **DocumentEditors** được edit tài liệu thuộc dự án được ủy quyền”. Một policy forbid khác cấm **document.edit** nếu tài liệu có **legalHold=true**. Kết quả chỉ được cho phép khi điều kiện permit đạt và không có forbid áp dụng.

**Không nên nghĩ cùng một biểu thức Rego có thể chuyển thành Cedar chỉ bằng đổi từ khóa.** Cách định nghĩa entity, hành động, attribute, xử lý missing và công cụ validation có sự khác biệt.

## 11. XACML: rule, policy set và thuật toán kết hợp

**XACML (eXtensible Access Control Markup Language)** mô tả cấu trúc chính sách dựa trên những thành phần như:

- **Rule:** điều kiện và hiệu ứng Permit/Deny.
- **Policy:** tập rule với cách kết hợp.
- **PolicySet:** tập policy hoặc policy set, có thể lồng nhau.
- **Target:** điều kiện để policy/rule thuộc phạm vi đánh giá.
- **Condition:** biểu thức logic bổ sung.
- **Combining Algorithm:** cách tổng hợp nhiều kết quả.
- **Obligations/Advice:** dữ liệu gắn với quyết định để PEP xử lý theo semantics phù hợp.

Một nét nổi bật là XACML định nghĩa những trạng thái kết quả như **Permit, Deny, NotApplicable, Indeterminate**. Cần nhớ **Indeterminate** có thể mang thông tin lỗi/ngữ cảnh chi tiết theo thuật toán, nên việc chuyển chính sách sang boolean true/false một cách máy móc có thể đánh mất ngữ nghĩa bảo mật.

### Khi nào kiến thức XACML hữu ích?

- Tổ chức có hệ thống entitlement/policy engine hỗ trợ XACML.
- Cần mô tả điều kiện truy cập có nhiều policy, kết quả và nghĩa vụ.
- Cần hiểu tác động của **policy combining** và **unknown/error states** khi tích hợp PEP/PDP.

Không nhất thiết mọi hệ thống IAM đều phải triển khai XACML. Chọn language dựa trên nhu cầu, mức bảo đảm, chất lượng toolchain và khả năng vận hành.

## 12. Thuộc tính và kiểu dữ liệu phải đáng tin cậy

**Chính sách đúng nhưng dữ liệu đầu vào sai vẫn có thể đưa ra quyết định sai.** Vì vậy một policy language hữu ích cần đi cùng **schema của subject, resource, action và context**.

### Nguồn thuộc tính

| Thuộc tính | Nguồn nên có thẩm quyền | Những sai lệch cần đề phòng |
|---|---|---|
| **identityId/personId** | HRIS/IAM/IdP mapping đã xác minh | Nối nhầm do dùng email tái sử dụng |
| **lifecycleState** | HRIS + IAM/IGA theo quan hệ hiện hành | Leaver đã có hiệu lực nhưng cache vẫn ACTIVE |
| **roles/group** | IGA/IdP và đích qua provisioning | Quyền cũ chưa gỡ, nested group |
| **tenantId** | Session/trust config và database tài nguyên | Client tự gửi tenantId khác |
| **resource.ownerId** | Database ứng dụng đáng tin | Owner do client tự khai |
| **classification** | Data catalog hoặc owner đã được kiểm soát | Mức phân loại bị sửa bởi user |
| **time/expiry** | Clock và chính sách ở server | Đồng hồ client không tin cậy |
| **MFA assurance** | IdP/AS đã xác minh, session được liên kết | Claim không tin cậy hoặc phiên quá cũ |
| **deviceTrust** | MDM/EDR/đánh giá thiết bị | User-Agent tự khai |
| **delegation** | Registry ủy quyền có phê duyệt và hạn | Giấy ủy quyền giả hoặc quá hạn |

### Kiểu và phép so sánh

- **Boolean:** ACTIVE hoặc true/false theo định nghĩa rõ; không tự coi chuỗi "false" là boolean false.
- **Thời gian:** dùng timestamp có timezone và tiêu chuẩn thống nhất; kiểm tra biên **effectiveFrom/effectiveUntil**.
- **Tiền:** dùng đơn vị nhỏ nhất hoặc decimal chính xác, không dùng float tùy tiện cho hạn mức.
- **Classification:** nên ánh xạ tới **thứ bậc chính thức**; không so sánh chữ "SECRET" và "PUBLIC" theo thứ tự chữ cái.
- **List/set:** phân biệt chứa một giá trị, chứa tất cả và so sánh tập.
- **Identifier:** dùng ID ổn định kèm namespace/tenant; không dùng tên hiển thị làm khóa bảo mật.

**Missing attribute phải có hành vi được định nghĩa.** Với action nhạy cảm, thiếu chứng cứ về role, owner, tenant hay MFA thường là lý do để **không Permit** và báo nguyên nhân tương ứng.

## 13. Obligation, advice và điều kiện thực thi sau Permit

Một số thiết kế policy có thể trả về ngoài quyết định các **nghĩa vụ (obligations)** hoặc **khuyến nghị (advice)**.

Ví dụ, policy cho phép export báo cáo **chỉ với điều kiện**:

- Áp watermark chứa ID người export.
- Ghi sự kiện audit mức cao.
- Giới hạn số dòng hoặc masking các trường nhạy cảm.
- Yêu cầu step-up trước khi phát dữ liệu.
- Áp thời hạn tải xuống.

Một phản hồi policy **minh họa nội bộ**:

~~~json
{
  "decision": "PERMIT",
  "policyId": "finance-export-v4",
  "obligations": [
    {"type": "AUDIT_HIGH"},
    {"type": "MASK_FIELDS", "fields": ["taxId", "bankAccount"]},
    {"type": "WATERMARK_EXPORT"}
  ],
  "reasonCodes": ["ROLE_OK", "TENANT_OK", "MFA_OK"]
}
~~~

Đây **không phải response chuẩn chung của PBAC/OPA/Cedar**; cách biểu diễn obligations tùy engine và hợp đồng tích hợp.

**PEP không được thực thi toàn bộ action rồi bỏ qua nghĩa vụ bắt buộc.** Nếu không thể masking dữ liệu hoặc xác minh step-up theo yêu cầu, cần từ chối/hoãn action tương ứng, không coi PERMIT trần là đủ.

Lưu ý: **advice** thường có tính chất khuyến nghị khác **obligation** bắt buộc; không được nhập nhằng chúng trong implementation.

## 14. Kiến trúc policy engine: PEP, PDP, PIP và PAP

Các thành phần thường được dùng trong PBAC:

- **Policy Enforcement Point (PEP):** chặn request, tạo yêu cầu ra quyết định và thực thi kết quả.
- **Policy Decision Point (PDP):** đánh giá policy với dữ liệu đầu vào.
- **Policy Information Point (PIP):** cung cấp thuộc tính/quan hệ có thẩm quyền.
- **Policy Administration Point (PAP):** quản trị policy, review, phê duyệt và phát hành.

~~~mermaid
flowchart LR
    C[Client / API caller] --> PEP[PEP: API, service, gateway]
    PEP --> PDP[PDP: policy evaluation]
    PDP --> PIP[PIP: identity, resource, context]
    PIP --> HR[HRIS / IAM / IdP]
    PIP --> DB[Application resource store]
    PAP[PAP: policy review + release] --> PDP
    PDP -->|Decision + metadata| PEP
    PEP --> ACT[Business action nếu được phép]
    PEP --> AUDIT[Audit / correlation]
~~~

### Yêu cầu tin cậy

1. **PEP phải chặn mọi đường vào**: REST, GraphQL, gRPC, background consumer và admin API.
2. **PDP không tin input từ client** nếu chưa xác minh.
3. **PIP trả thuộc tính có căn cứ** và phải xử lý dữ liệu lỗi thời/không có.
4. **PAP quản lý người được sửa policy**; việc sửa policy là một hành động đặc quyền.
5. **Kênh PEP↔PDP và PIP** cần xác thực, bảo vệ và giới hạn quyền nếu chạy phân tán.
6. **Ứng dụng vẫn phải kiểm business state** trong ranh giới giao dịch, tránh race condition và TOCTOU.
7. **Audit ghi decision và execution riêng**, không lộ token/password/secret.

**Một gateway kiểm tra scope không đủ nếu backend có thể bị gọi trực tiếp** hoặc nếu policy cần quyền ở cấp object mà gateway không biết.

## 15. Policy-as-code: từ câu chữ đến bản phát hành được kiểm thử

**Policy-as-code** là quản lý policy như một artifact có version, review, test và quy trình triển khai. Ngôn ngữ policy cung cấp điều kiện để làm điều này, nhưng bản thân policy-as-code còn cần governance.

### Cấu trúc metadata đề xuất

~~~yaml
policyId: finance.invoice.approve
version: 6
ownerTeam: Finance-Security
resourceType: Invoice
action: invoice.approve
riskTier: HIGH
effectiveFrom: 2026-12-01T00:00:00Z
default: DENY
mandatoryChecks:
  - identity-active
  - tenant-match
  - assigned-approver-role
  - separation-of-duties
  - workflow-state
  - approval-limit
  - strong-authentication
reviewRequired: true
~~~

Đây là **YAML metadata minh họa do tổ chức tự định nghĩa**, không phải policy trực tiếp chạy được trong mọi engine hoặc schema chuẩn của Cedar/XACML/OPA.

### Lợi ích

- **Traceability:** biết thay đổi nào tạo ra quyền.
- **Peer review:** owner nghiệp vụ, IAM và security cùng đánh giá.
- **Automated tests:** chạy ca Permit/Deny và regression.
- **Controlled rollout:** triển khai theo ứng dụng/tenant hoặc shadow mode.
- **Reproducibility:** phân tích lại quyết định theo policy version và dữ liệu tại thời điểm tương ứng.
- **Emergency rollback:** trả về policy trước theo quy trình có thẩm quyền, nhưng không tái cấp quyền đã hết theo JML.

**Quyền thay đổi policy phải được hạn chế và kiểm toán** như một quyền quản trị đặc biệt. Một thay đổi nhỏ về biểu thức hoặc priority có thể mở quyền cho toàn tổ chức.

## 16. Kiểm thử policy language: không chỉ kiểm nhánh Permit

Với policy quan trọng, phải kiểm thử **negative cases**, dữ liệu thiếu, thứ tự policy và quyền thay đổi theo thời gian.

| Test case | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Approver hợp lệ | Role đúng, cùng tenant, SUBMITTED, không tự duyệt, MFA mạnh | Permit |
| Thiếu role | Không có FINANCE_APPROVER | Deny |
| Cross-tenant | Hóa đơn tenant B, người tenant A | Deny |
| Self-approval | createdBy trùng identityId | Deny |
| Account Leaver | lifecycleState=TERMINATED | Deny |
| Role cũ sau Mover | Từng có role nhưng hiện đã thu hồi | Deny |
| Chưa đủ MFA | Phiên chỉ có phương thức yếu hơn yêu cầu | Deny hoặc step-up trước Permit |
| Hóa đơn APPROVED | Không còn SUBMITTED | Deny/do business validation từ chối |
| Vượt hạn mức | amount lớn hơn approval limit | Deny |
| Missing tenant | Không có tenant resource đáng tin | Không Permit |
| PIP timeout | Không đọc được role/quan hệ hiện hành | Không Permit mặc định |
| Policy conflict | Một allow và một hard deny áp dụng | Theo combining semantics đã phê duyệt, không bypass guardrail |
| Người dùng gửi role tự khai | Client payload chứa SUPER_ADMIN không có ở IdP/IGA | Không ảnh hưởng quyết định |
| Token sai audience | Access token không dành cho API | Request không được đi tiếp tới PDP như phiên hợp lệ |
| Grant JIT quá hạn | effectiveUntil đã qua | Deny |
| Service account không owner | Workload mất sponsor hợp lệ | Theo policy không được tự cấp rộng |
| Bulk export | Người chỉ được đọc một bản ghi muốn export toàn tenant | Deny nếu không có quyền phạm vi phù hợp |
| Action mới chưa có policy | action=invoice.refund mới triển khai | Deny by default |

### Các cấp kiểm thử

1. **Unit test policy:** đầu vào cố định, kết quả kỳ vọng rõ.
2. **Type/schema test:** thiếu/trái kiểu thuộc tính, timestamp, ID.
3. **Conflict test:** allow/deny chồng nhau, role hierarchy, hard guardrail.
4. **Property-based test:** bất biến như “không ai tự duyệt”, “không truy cập xuyên tenant”.
5. **Mutation test:** thay toán tử, xóa điều kiện, xem bộ test có phát hiện nới quyền không.
6. **Integration test:** PEP nạp đúng subject/resource, policy được gọi trên mọi route.
7. **JML test:** Joiner chưa effective, Mover gỡ quyền, Leaver khóa, Rejoiner không hồi sinh quyền cũ.
8. **Shadow test:** đánh giá policy mới không ảnh hưởng request thật, so sánh quyết định và điều tra khác biệt.
9. **Audit test:** policy version và reason code được ghi nhưng không lộ dữ liệu nhạy cảm.

**Một policy có thể vượt qua toàn bộ happy-path test mà vẫn chứa lỗi phân quyền nghiêm trọng.** Những ca từ chối và lỗi dữ liệu là trọng tâm của kiểm soát an toàn.

## 17. Phát hành policy: version, canary, shadow và rollback

Thay đổi policy có thể tác động nhiều tài khoản cùng lúc. Quy trình phát hành nên có các giai đoạn:

~~~mermaid
flowchart TD
    D[Draft policy] --> REV[Review: owner + IAM + Security]
    REV --> TEST[Unit / conflict / JML tests]
    TEST --> SHADOW[Shadow evaluation]
    SHADOW --> CANARY[Canary theo tenant/app]
    CANARY --> ROLL[Rollout có giám sát]
    ROLL --> REC[Reconciliation + audit]
    REC --> ACTIVE[Policy active]
    TEST -->|Không đạt| D
    SHADOW -->|Sai lệch nguy hiểm| D
    CANARY -->|Sai lệch nguy hiểm| RB[Rollback có kiểm soát]
    RB --> D
~~~

### Các quy tắc vận hành

- Giữ **policy ID và version** bất biến trong audit.
- Đánh giá impact lên **effective permissions**, không chỉ diff của source code.
- Nếu đổi cấu trúc thuộc tính, triển khai **PIP/schema** tương thích trước khi policy phụ thuộc.
- Có **metric Permit/Deny/Error theo action**, độ trễ PDP và cảnh báo sudden permit growth.
- Thử rollback trong môi trường kiểm soát; không coi rollback có quyền bỏ qua sự kiện **Leaver mới hơn**.
- Với change nhạy cảm, cần quy trình phê duyệt độc lập và **emergency policy** có thời hạn/giám sát.
- Chính sách không còn dùng phải được **retire**, tránh tồn tại các rule cho phép trùng lặp.

**Version policy không thay thế version nguồn JML.** Một rule cũ được triển khai lại vẫn phải đánh giá với **trạng thái identity mới nhất được chấp nhận**, không tự phục hồi role/quan hệ đã thu hồi.

## 18. Hiệu năng, cache và dữ liệu lỗi thời

Một PDP có thể chạy **embedded trong service**, ở **sidecar** hoặc dưới dạng **dịch vụ tập trung**. Mỗi lựa chọn ảnh hưởng latency, consistency và tính sẵn sàng.

| Thiết kế | Ưu điểm | Rủi ro cần xử lý |
|---|---|---|
| **Embedded policy engine** | Quyết định cục bộ nhanh, ít network | Policy/data distribution và version drift |
| **Sidecar PDP** | Tách logic policy khỏi mã ứng dụng | Tải cấu hình, health, version nhất quán |
| **Central PDP** | Quản lý tập trung, dễ audit theo kiến trúc | Độ trễ, phụ thuộc mạng, bottleneck |
| **Decision cache** | Giảm tải cho PDP/PIP | Permit tồn tại sau khi role/quan hệ đã hết |
| **Materialized attributes** | Giảm truy vấn nguồn HRIS/IGA ở runtime | Độ trễ cập nhật sau Mover/Leaver |

### Cache key phải đầy đủ

Không được cache **Permit** chỉ theo user ID nếu quyết định phụ thuộc **action, resource, tenant, role version, device state, thời gian hoặc classification**. Cache key/TTL thiếu thành phần có thể tái sử dụng kết quả trên tài nguyên khác.

### Khi Leaver có hiệu lực

Nếu người dùng bị disable tại IdP nhưng PEP vẫn dùng cache **lifecycleState=ACTIVE**, một action nhạy cảm có thể được cho phép trái policy. Giải pháp có thể là:

- Invalidating cache theo **lifecycle event/version**.
- TTL ngắn hơn với action rủi ro cao.
- Tra cứu trạng thái gần thời gian thực ở điểm thực thi.
- Chặn tạm thời tại gateway/RS cho các trường hợp khẩn cấp.
- Đối soát bằng **request thật được kiểm soát hoặc trạng thái thực tế**.

**Chỉ ghi “đã gửi sự kiện thu hồi” không chứng minh tất cả bản cache đã ngừng chấp nhận quyền cũ.**

## 19. Policy language trong Joiner lifecycle

Khi một người gia nhập, các nguồn và điều kiện có thể thay đổi theo nhiều mốc:

1. **HRIS/contract authority** tạo personId, relationshipId và effectiveAt.
2. **Identity proofing** xác minh chủ thể theo mức yêu cầu.
3. **Enrollment** liên kết authenticator/password/passkey với account.
4. **IAM/IGA** tính business role, entitlement và phạm vi theo chính sách.
5. **SCIM/API** provisioning account/group đến hệ thống đích.
6. **IdP/SSO** xác thực người dùng khi điều kiện có hiệu lực.
7. **PEP/PDP** kiểm tra policy trước mỗi action.
8. **Reconciliation** xác nhận tài khoản, role và quyền thực tế đã khớp desired state.

### Ví dụ policy Joiner

~~~text
permit(action) only if
    identity.status == ACTIVE
    and relationship.effectiveFrom <= serverTime
    and (relationship.effectiveUntil is absent
         or serverTime < relationship.effectiveUntil)
    and identity.enrollmentCompleted
    and policyAllows(identity.role, action, resource, context)
~~~

**Người dùng có account được tạo trước ngày nhận việc không tự có quyền vào dữ liệu sản xuất.** Policy có thể kiểm tra thời điểm và các điều kiện nghiệp vụ cần thiết, nhưng nếu trạng thái HRIS hoặc SCIM ở đích không cập nhật thì vẫn phải xử lý reconciliation.

### Tránh cấp role từ thông tin chưa được xác minh

Role không nên được quyết định từ trường **department** do người dùng tự sửa trong profile. Phải lấy dữ liệu từ HRIS/IGA có phê duyệt, bảo đảm quan hệ còn hiệu lực và phân tách nguồn identity proofing với nguồn ủy quyền.

## 20. Policy language trong Mover lifecycle

**Mover** có thể làm thay đổi department, manager, project, role, tenant, clearance hoặc yêu cầu MFA. Policy language giúp **tính lại quyền theo ngữ cảnh hiện hành** thay vì chỉ thêm group mới.

Ví dụ Lan chuyển từ Sales sang Finance:

| Thành phần | Trước Mover | Sau Mover mong muốn |
|---|---|---|
| Department | Sales | Finance |
| Role | SALES_READER | FINANCE_ANALYST |
| Permission | customer.read | invoice.read |
| Export | customer.export nếu từng được duyệt | Thu hồi nếu không còn nhiệm vụ |
| Approval | Không có invoice.approve | Chỉ khi có approval và SoD |
| MFA | Mức thông thường | Có thể yêu cầu step-up cho tác vụ nhạy cảm |

### Lỗi phổ biến

SCIM đã thêm nhóm **FINANCE_ANALYST** nhưng quên xóa **SALES_EXPORT**. Nếu policy chỉ kiểm group hiện có và không xét trạng thái nguồn, action customer.export có thể còn hiệu lực.

### Hướng xử lý

- Tính **desired state mới** và chênh lệch quyền trước/sau.
- Thu hồi **group, direct grants, role hierarchy và quyền tạm** không còn được phép.
- Cập nhật PIP/cache/token có claim cũ; sử dụng session step-up khi policy yêu cầu.
- Kiểm tra **authorization decision thật** cho action cũ và mới.
- Nếu có quyền tồn dư, mở finding có owner, hạn xử lý và biện pháp bù trừ.
- Chặn job Mover cũ **tái cấp quyền** sau khi có sự kiện Leaver mới hơn.

**Một policy cho phép Finance không tự thu hồi quyền Sales trong ứng dụng legacy** nếu ứng dụng không dùng PDP hoặc vẫn giữ local entitlement. PBAC cần phối hợp provisioning và reconciliation.

## 21. Policy language trong Leaver và quyền truy cập tồn dư

**Leaver** là tình huống kiểm nghiệm quan trọng nhất của policy: tài khoản ở IdP bị vô hiệu không đủ nếu **session, token, API key, local account, cache quyền hoặc connector** tiếp tục cho phép request.

### Chuỗi phòng vệ theo lớp

| Lớp | Hành động | Giới hạn |
|---|---|---|
| **Nguồn JML** | Xác minh Leaver, effectiveAt, quan hệ | Nguồn nhân sự có thể cập nhật muộn |
| **IdP/SSO** | Chặn đăng nhập mới, xử lý session | Session ở SP có thể tồn tại riêng |
| **PDP/PIP** | Lifecycle guard DENY khi quan hệ hết | Cần dữ liệu tươi và PEP thực sự gọi PDP |
| **Policy cache** | Invalidate/giới hạn TTL | Cache Permit cũ có thể còn hợp lệ kỹ thuật |
| **SCIM/API** | Deactivate user/group/role ở đích | active=false không tự thu hồi mọi token |
| **Access token** | Chặn theo revocation/introspection/lifecycle | JWT còn chữ ký và exp hợp lệ nếu RS không kiểm thêm |
| **Local credentials** | Thu hồi API key, SSH key, credential riêng | Nằm ngoài SSO |
| **Audit** | Ghi request/decision/execution và kết quả chặn | Log không đầy đủ nếu app không tích hợp |
| **Reconciliation** | So sánh desired với observed và thử các action trọng yếu | Phải công khai phạm vi chưa quan sát được |

### Guardrail minh họa

~~~text
hardDeny if
    relationship.status == TERMINATED
    and request.action is not an explicitly authorized retentionOperation

permit only if
    identity.currentRelationships authorize request.action
    and session.isValid
    and resourcePolicyAllows
~~~

Đây là **ngữ nghĩa minh họa**, không phải cú pháp policy chuẩn. Một người có thể có **nhiều quan hệ hợp lệ song song**; Leaver của một hợp đồng không nhất thiết phải xóa mọi truy cập gắn với quan hệ khác. Chính sách phải nhận diện **relationshipId và căn cứ quyền**, không cắt hoặc giữ nhầm theo email.

### Chứng minh đã cắt quyền

Không chỉ đo sự kiện disable; cần xác minh API không còn cho **report.export, invoice.approve, user.assignRole** hoặc những action nhạy cảm trong phạm vi tài khoản đã hết quyền. Nếu còn đường truy cập, workflow ở trạng thái **PARTIAL/OPEN**, có owner, deadline và biện pháp giảm thiểu.

## 22. Policy language cho service account, workload và device

**Non-human identities** không có vòng đời nhân sự giống một nhân viên. Một service account dùng batch hoặc bot CI/CD cần **nguồn có thẩm quyền riêng**:

- Workload/application registry và owner kỹ thuật.
- Tenant, environment, service identity và purpose.
- Scope/action được cấp theo nhu cầu.
- Credential quản lý bằng vault, certificate, managed identity hoặc workload federation.
- Mốc hết hạn, review và quy trình ngừng sử dụng.
- Quan hệ owner khi cá nhân quản lý workload nghỉ việc.

### Ví dụ policy cho workload

~~~text
permit if
    subject.type == WORKLOAD
    and subject.workloadId in approvedRegistry
    and subject.ownerTeam is active
    and action == "artifact.upload"
    and resource.bucket == "ci-artifacts-prod"
    and context.environment == "production"
    and subject.credential is trusted
~~~

Một workload có thể hợp lệ dù không có personId trong HRIS. **Không gắn quyền của bot vào vai trò nhân viên rồi chia sẻ mật khẩu SSO của họ**. Ngược lại, nếu owner kỹ thuật Leaver, cần **chuyển ownership và rà soát secret/permission**, không xóa mù quáng mọi workload production.

### Phân biệt máy–máy và người dùng

OAuth **client credentials** thường đại diện cho client/workload, không cho biết một người đang bấm nút Approve. Action cần trách nhiệm con người như **payment.approve** có thể yêu cầu authenticator và actor con người theo SoD; không nên cho bot thực hiện chỉ vì token có scope rộng.

## 23. SoD, JIT và quyền có thời hạn trong policy language

### Separation of Duties

SoD ngăn một người thực hiện các thao tác xung đột. Với hóa đơn:

- Người tạo không được **tự duyệt** hóa đơn đó.
- Người quản lý tài khoản không được tự chứng nhận chính quyền mình đã cấp nếu policy cấm.
- Người tạo deployment có thể không được tự release production, tùy quy trình.

Policy cần đánh giá **effective permissions và lịch sử hành động trên resource**, không chỉ danh sách role. Khi role kế thừa hoặc user có nhiều role, một điều kiện hard deny có thể vẫn cần thiết.

### Just-in-Time privilege

Quyền đặc biệt như **production.deploy** hoặc **user.assignRole** có thể được cấp tạm theo:

| Điều kiện | Ví dụ |
|---|---|
| **Subject** | iam-2046 |
| **Action** | production.deploy |
| **Resource scope** | service-payments, prod |
| **Approver** | Người có thẩm quyền độc lập |
| **Time window** | 09:00–10:00 theo timezone chuẩn |
| **Strong authentication** | Phishing-resistant MFA trước thao tác |
| **Justification** | Change request có owner |
| **Revocation** | Hết hạn hoặc sự kiện JML ưu tiên cao hơn |

**Một grant hết hạn phải được PEP/RS thực thi là hết hạn**, kể cả nếu role/group của ứng dụng đích còn chưa gỡ được. Ngược lại, policy deny không nên trở thành lý do bỏ qua việc dọn entitlement ở đích.

### Break-glass policy

Quyền khẩn cấp có thể có ngoại lệ được quy định cụ thể, nhưng cần **owner, lý do, phạm vi tối thiểu, thời hạn, MFA/kiểm soát bù trừ, giám sát và review sau sự kiện**. Không tạo một Permit-all vô thời hạn rồi gọi đó là break-glass.

## 24. Threat modeling cho policy language

| Lỗi hoặc kiểu tấn công | Hậu quả | Phòng tránh |
|---|---|---|
| **Default Permit** khi không có rule | User mới hoặc action lạ được phép | Deny by default |
| **Thiếu tenant guard** | Truy cập chéo khách hàng | Mọi object-level request kiểm tenant đáng tin |
| **Role do client tự khai** | Tự nhận admin | Subject attributes từ IdP/IGA đã xác minh |
| **Policy conflict không được xác định** | Hard deny bị allow khác vượt | Combining semantics rõ, conflict tests |
| **Null/missing input bị coi thành hợp lệ** | Thiếu owner/MFA vẫn Permit | Schema validation, fail closed |
| **So sánh classification theo chuỗi** | SECRET được xếp sai mức | Dùng thứ bậc chính thức kiểu số/enum |
| **PIP đọc dữ liệu cũ** | Mover/Leaver còn quyền | Invalidation, version và reconciliation |
| **Token scope được coi là quyền đầy đủ** | Truy cập bản ghi người khác | RBAC/ABAC/ReBAC tại resource |
| **PEP chỉ ở gateway** | Backend/consumer bị gọi vòng tránh | Enforcement tại mọi đường |
| **Policy injection** | Dữ liệu người dùng bị thực thi như policy | Tách policy code khỏi input data; không eval chuỗi không tin cậy |
| **Policy tampering** | Attacker sửa luật, cấp quyền rộng | PAP control, signed/approved releases, audit |
| **TOCTOU** | Resource đổi trạng thái sau khi check | Transaction/locking hoặc kiểm lại lúc commit |
| **Role explosion** | Quyền khó hiểu, chồng chéo | Business roles + ABAC + governance |
| **Không theo dõi obligations** | Cho export dù chưa masking | PEP thực thi nghĩa vụ hoặc không cho hành động |
| **Cache key thiếu resource/action** | Permit bị dùng lại cho đối tượng khác | Cache key đủ context, TTL/invalidation |
| **Rollback tái cấp quyền cũ** | Leaver được mở lại | Rollback policy không rollback lifecycle |
| **Policy test chỉ happy path** | Lỗi Deny không được phát hiện | Test negative, mutation, SoD và JML |

### Nguy cơ riêng của policy engine

Ngôn ngữ policy có thể hỗ trợ function, import hoặc external data lookup. **Không cho dữ liệu không tin cậy quyết định đường dẫn module, code cần chạy hoặc nguồn URL tin cậy**. Giới hạn CPU/memory/thời gian cho evaluation để tránh rule quá tốn tài nguyên. Cần có quy trình review policy như review code bảo mật.

## 25. Kiểm toán, giải thích quyết định và dữ liệu riêng tư

Khi xảy ra sự cố, tổ chức cần trả lời:

> Chủ thể nào đã yêu cầu action nào, trên tài nguyên nào, theo policy phiên bản nào, dữ liệu nào làm căn cứ và thao tác có thực sự xảy ra không?

### Bản ghi minh họa

~~~json
{
  "eventId": "authz-20261123-0261",
  "correlationId": "req-441d",
  "identityId": "person-2046",
  "relationshipId": "employment-2046-v1",
  "action": "invoice.approve",
  "resource": {
    "type": "Invoice",
    "id": "INV-873",
    "tenantId": "org-vn"
  },
  "policyId": "finance.invoice.approve",
  "policyVersion": 6,
  "decision": "DENY",
  "reasonCode": "SELF_APPROVAL_FORBIDDEN",
  "decisionAt": "2026-11-23T09:16:00+07:00",
  "execution": "NOT_EXECUTED"
}
~~~

Đây là **schema audit minh họa**, không phải chuẩn bắt buộc của policy engine. Hệ thống nên ghi metadata có giá trị kiểm toán nhưng không log **password, token thô, private key, dữ liệu sinh trắc hoặc toàn bộ hồ sơ nhân sự nhạy cảm**.

### Decision và execution là hai trạng thái khác nhau

- **PDP Permit:** policy có đủ điều kiện cho phép theo input được cung cấp.
- **PEP execution failed:** business operation có thể vẫn lỗi.
- **PDP Deny:** action phải không gây tác động nghiệp vụ.
- **PDP error/indeterminate:** phải ghi lỗi, không giả thành Permit.
- **Obligation failed:** không được đánh dấu action thành công khi nghĩa vụ bắt buộc chưa hoàn thành.

### Chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| **Policy decision coverage** | Tỷ lệ API/action/resource có gọi policy đúng cách |
| **Unexpected Permit** | Những quyết định mở quyền trái desired state |
| **Denied action rate** | Lượng từ chối theo reason và application |
| **Indeterminate/error rate** | Thiếu dữ liệu, PIP/PDP lỗi, schema mismatch |
| **Decision latency** | Hiệu năng đánh giá policy |
| **Policy version drift** | Service/sidecar dùng phiên bản cũ |
| **Unowned policies** | Policy không có chủ thể chịu trách nhiệm |
| **JML revocation latency** | Độ trễ chặn action sau Mover/Leaver |
| **Stale attribute findings** | Role/tenant/lifecycle không còn đúng |
| **SoD violations prevented** | Yêu cầu xung đột bị chặn |
| **JIT expiry compliance** | Quyền tạm hết hạn và ngừng thực thi đúng |
| **Reconciliation coverage** | Tỷ lệ quyền/action có thể kiểm chứng ở đích |

**Không suy rằng ít lượt Deny nghĩa là an toàn.** Có thể PEP không được gắn vào API hoặc logging chưa đầy đủ. Cần test chủ động và đo **coverage**.

## 26. Tình huống xuyên suốt: Policy language qua Joiner–Mover–Leaver

Giả sử **Lan** vào công ty ở bộ phận Sales, sau đó chuyển sang Finance và cuối cùng nghỉ việc. Tổ chức dùng IdP SSO, SCIM provisioning, một API báo cáo và một PDP dựa trên policy language.

### Giai đoạn A — Joiner

HRIS phát Joiner với identity ID và ngày hiệu lực. IAM kiểm tra proofing/enrollment, IdP cho Lan đăng ký security key và thực thi MFA. SCIM tạo tài khoản ở ứng dụng báo cáo và nhóm **SALES_READER**.

Policy **report.read** yêu cầu account active, role SALES_READER, cùng tenant và classification hợp lệ. Lan có thể xem báo cáo Sales của đơn vị mình nhưng không thể xem báo cáo Finance dù đoán đúng resource ID.

### Giai đoạn B — Cấp quyền tạm

Lan được phê duyệt export một số báo cáo Sales trong 7 ngày. Thay vì tạo role vĩnh viễn, IAM cấp grant **report.export** với scope và thời hạn rõ. PDP chỉ Permit khi grant còn hiệu lực, phiên đáp ứng MFA và không vượt classification/volume. PEP áp watermark và audit bắt buộc.

### Giai đoạn C — Mover

Lan chuyển sang Finance. IAM thu hồi role Sales, cấp role **FINANCE_ANALYST** và cập nhật thuộc tính department. SCIM đồng bộ quyền ở đích. Một token SSO cũ vẫn chứa claim Sales, nhưng policy tại API dựa trên trạng thái role/quan hệ hiện hành và chặn **report.export** của Sales. Nếu PIP có cache chưa cập nhật, vận hành phải invalidate hoặc chặn tạm theo rủi ro.

### Giai đoạn D — Quyền duyệt

Lan nhận thêm role Finance Approver sau phê duyệt. Policy **invoice.approve** kiểm hạn mức, tenant, state SUBMITTED và SoD. Khi Lan thử duyệt hóa đơn do chính Lan tạo, PDP trả Deny bất kể role và MFA đủ mạnh.

### Giai đoạn E — Leaver

HRIS chấm dứt quan hệ có hiệu lực. IdP disable, IAM gửi SCIM active=false, thu hồi phiên/token và các quyền ứng dụng. Chính sách API dùng lifecycle guard, nên một JWT chưa hết hạn vẫn không được phép thực thi action nếu PEP/PIP có trạng thái mới nhất theo yêu cầu. Đội vận hành kiểm tra thêm local account, API key và ứng dụng không tích hợp PDP; kết quả chưa xác minh được phải để **PARTIAL/OPEN**.

### Giai đoạn F — Rejoiner

Nếu Lan quay lại ở một vị trí khác, identity lịch sử có thể được liên kết theo chính sách nhưng **policy chỉ Permit dựa trên quan hệ mới được xác minh**. Không tự cấp lại grant export, vai trò approver hay session cũ.

### Kết luận tình huống

Policy language giúp quy tắc quyền rõ ràng, kiểm thử được và nhất quán hơn, nhưng **không tự bảo đảm dữ liệu đầu vào tươi, PEP bao phủ mọi đường truy cập hoặc SCIM đã thu hồi quyền thật**. Một quy trình IAM hoàn chỉnh cần cả **policy, identity lifecycle, provisioning, session/token control và reconciliation**.

## 27. Checklist khi thiết kế Policy language cho PBAC

1. **Phạm vi:** policy đang kiểm soát action/resource nào và owner nghiệp vụ là ai?
2. **Mô hình:** đã tách subject–action–resource–context và dùng ID bền vững chưa?
3. **Ngữ nghĩa:** đã xác định kết quả, default, missing data và lỗi PDP/PIP chưa?
4. **Xung đột:** có quy tắc kết hợp Permit/Deny rõ, không để hard deny bị vượt?
5. **RBAC/ABAC/ReBAC:** policy sử dụng role, attribute và relationship theo nguồn đáng tin không?
6. **SoD:** có chặn tự duyệt và các quyền xung đột ở effective permission level?
7. **Schema:** kiểu timestamp, classification, money và enum được định nghĩa nhất quán?
8. **Trusted input:** lifecycle, role, tenant, MFA assurance và resource owner không lấy mù quáng từ client?
9. **PEP coverage:** tất cả API/GraphQL/gRPC/batch/admin path có enforcement?
10. **PDP/PIP security:** kênh nội bộ, dữ liệu, timeout và độ trễ được kiểm soát?
11. **Obligations:** masking, audit hoặc step-up bắt buộc được PEP thực thi hoặc từ chối?
12. **Policy-as-code:** policy có version, owner, review, CI tests và release log?
13. **Regression:** có test Permit, Deny, NotApplicable/Indeterminate hoặc trạng thái engine tương đương?
14. **Negative tests:** có kiểm cross-tenant, missing field, token sai, SoD, action mới và race condition?
15. **Cache:** key, TTL, invalidation và version đã cân nhắc thay đổi role/JML?
16. **Joiner:** account chuẩn bị trước ngày bắt đầu không tự có quyền sớm?
17. **Mover:** policy được tính lại theo vai trò mới, quyền cũ và token/cache cũ được xử lý?
18. **Leaver:** chặn access token/phiên/local account bên ngoài policy engine?
19. **Non-human:** workload/device có owner, policy và vòng đời credential riêng?
20. **Privileged access:** grant tạm, step-up/JIT, approval và SoD phù hợp?
21. **Role explosion:** có dùng attribute/resource binding thay vì tạo role cho mọi tổ hợp?
22. **Migration:** có shadow/canary/rollback và không khôi phục quyền bị thu hồi bởi JML?
23. **Audit:** log được policy version, decision, execution và reason code không chứa secret?
24. **Reconciliation:** quyền thực tế tại hệ thống đích đã được xác minh, ghi rõ giới hạn coverage chưa?

### Ghi nhớ

**Policy language là ngôn ngữ biểu diễn và đánh giá những quy tắc phân quyền trong PBAC**, giúp làm rõ **subject, action, resource, context, điều kiện, kết quả, xung đột và nghĩa vụ thực thi**. Rego/OPA, Cedar, XACML và DSL nội bộ có **cú pháp, kiểu dữ liệu và ngữ nghĩa riêng**, nên phải chọn theo yêu cầu chứ không coi chúng là các cách viết thay thế trực tiếp. Một policy an toàn phải **deny by default, dựa trên thuộc tính đáng tin, kiểm tra ở PEP và resource cụ thể, được version/test/audit như code bảo mật**. Trong **Joiner–Mover–Leaver**, policy cần được đánh giá với trạng thái danh tính và quyền **hiện hành**, phối hợp **IdP/SSO, SCIM, RBAC/ABAC, session/token revocation và reconciliation** để ngăn **quyền truy cập tồn dư** ở hệ thống đích.
