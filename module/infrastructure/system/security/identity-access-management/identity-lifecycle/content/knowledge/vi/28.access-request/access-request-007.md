# Risk của yêu cầu truy cập trong IAM: đánh giá trước khi phê duyệt và cấp quyền

**Risk của yêu cầu truy cập (access-request risk)** là mức rủi ro phát sinh nếu **một yêu cầu cấp, mở rộng, gia hạn hoặc kích hoạt quyền truy cập cụ thể** được chấp thuận trong một bối cảnh nhất định. Để đánh giá đúng, tổ chức phải xem **ai yêu cầu, cho ai, xin quyền gì, trên tài nguyên nào, vào thời điểm nào, vì mục đích gì, trong bao lâu và hệ thống sẽ thực sự cấp quyền ra sao**. Mức rủi ro không chỉ xuất phát từ số role được xin: một permission duy nhất như quản trị IAM hoặc đọc toàn bộ vault secrets có thể nguy hiểm hơn nhiều quyền đọc hạn chế.

Bài **“Risk của yêu cầu”** thuộc chương **Access request**, module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module nghiên cứu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản, cấp quyền, rà soát đến thu hồi khi thay đổi vai trò hoặc rời tổ chức. Đánh giá risk trong access request phải phối hợp với **HRIS/IGA, IdP, SSO, SCIM, RBAC/ABAC, service account, kiểm toán** và mục tiêu giảm **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Một nhân viên vừa chuyển từ Sales sang Finance yêu cầu quyền **Payment Approver** trên môi trường production trong 90 ngày để “hỗ trợ đối soát”. Nhân viên có MFA và account đang ACTIVE, nhưng trước đó vẫn giữ quyền tạo lệnh thanh toán từ nhóm cũ. Nếu hệ thống chỉ kiểm “người dùng đã đăng nhập” rồi tự phê duyệt, có thể phát sinh xung đột **Separation of Duties (SoD)**, đặc quyền quá dài và rủi ro tài chính. Một quy trình risk-aware access request phải phát hiện những điều kiện này **trước khi cấp**, định tuyến người phê duyệt phù hợp và xác minh rằng quyền chỉ có hiệu lực theo quyết định cuối cùng.

## 1. Risk của yêu cầu là gì và không phải gì?

**Risk của yêu cầu** liên quan tới **hành động thay đổi quyền** đang được đề xuất. Nó khác với các khái niệm gần gũi:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Request risk** | Nếu cấp quyền này, trong phạm vi và thời hạn này, tác động/rủi ro tăng ra sao? | Thêm quyền approve payment ở production trong 90 ngày. |
| **Identity risk** | Có tín hiệu cho thấy chủ thể hoặc thông tin đăng nhập bị xâm phạm không? | Phiên đăng nhập bất thường, account đang bị điều tra. |
| **Entitlement risk** | Một quyền có sức ảnh hưởng/khả năng lạm dụng tới đâu? | Global admin nguy hiểm hơn read-only tenant-scoped. |
| **Resource/data risk** | Tài nguyên có độ nhạy cảm và hậu quả tiềm tàng nào? | Signing key, dữ liệu khách hàng, hệ thống thanh toán. |
| **Session/transaction risk** | Ngữ cảnh của lần xác thực hoặc giao dịch hiện tại có đáng tin không? | Thiết bị chưa được quản lý, thiếu step-up cho thao tác nhạy cảm. |
| **Residual access risk** | Sau khi yêu cầu kết thúc hoặc nhân sự thay đổi, quyền có còn tồn dư? | Token cũ, ACL cục bộ, role SaaS chưa thu hồi. |

Các yếu tố trên có quan hệ, nhưng **không thể dùng một điểm identity risk thấp để tự động cho phép mọi entitlement**. Một nhân viên hoàn toàn hợp lệ vẫn có thể xin quyền quá rộng hoặc vi phạm SoD.

### Quyết định risk không thay thế quyết định authorization

Quy trình request thường quyết định **có nên cấp quyền mới**. Runtime authorization tại ứng dụng/API quyết định **yêu cầu truy cập cụ thể có được thực thi**. Một ticket được duyệt không tự cấp quyền trên mọi hệ thống; ngược lại, một entitlement đã provision thành công cũng không đồng nghĩa API phải bỏ kiểm tra role, tenant, owner, action, thời gian hoặc trạng thái JML.

**Nguyên tắc:** risk assessment hỗ trợ **quyết định cấp quyền và kiểm soát bù trừ**, còn enforcement ở **PEP/Resource Server** vẫn phải kiểm đúng chính sách khi quyền được sử dụng.

## 2. Các thành phần trong một access request

Một yêu cầu nên là đối tượng có cấu trúc, không phải email “cấp admin giúp tôi”.

| Trường | Nội dung | Vì sao ảnh hưởng rủi ro |
| --- | --- | --- |
| **requestId** | Định danh duy nhất, chống xử lý trùng. | Liên kết phê duyệt, provisioning và audit. |
| **requester** | Người/ứng dụng nộp yêu cầu. | Có thể khác người nhận quyền; ngăn self-approval hoặc giả mạo. |
| **beneficiary / subject** | Chủ thể sẽ được cấp: user, contractor, workload. | Kiểm identity, owner, quan hệ và trạng thái JML. |
| **target / resource** | Ứng dụng, tenant, project, resource group, secret path. | Phạm vi dữ liệu/tác động nếu bị lạm dụng. |
| **entitlement / action** | Role, scope, nhóm, ACL, permission, JIT activation. | Độ mạnh và khả năng leo thang quyền. |
| **environment** | Production, staging, sandbox, vùng/tenant. | Production có hậu quả và yêu cầu kiểm soát khác. |
| **business purpose** | Nhiệm vụ cụ thể, dự án, ticket thay đổi. | Xác định quyền cần thiết và nguồn phê duyệt. |
| **validFrom / validUntil** | Ngày hiệu lực và hết hạn. | Giảm quyền tồn tại quá lâu; cần tính chênh thời gian. |
| **context / assurance** | MFA/step-up, device, network, break-glass. | Xác định điều kiện bảo đảm trước activation. |
| **current access / conflicts** | Quyền hiện có, SoD, delegated grants. | Rủi ro từ **tổ hợp quyền**, không chỉ quyền mới. |
| **approval route** | Owner, manager, security, data owner, SoD controller. | Ai có thẩm quyền chấp nhận hoặc từ chối rủi ro? |
| **provisioning target** | SCIM connector, cloud IAM, PAM, SaaS local role. | Có thể cấp/thu hồi chính xác và readback được không? |
| **evidence / lifecycle** | Policy version, timestamps, reviews, revoke status. | Chứng minh quyền được cấp và gỡ đúng quyết định. |

### Ví dụ yêu cầu có cấu trúc

~~~yaml
requestId: ar-2026-0107
requestType: TEMPORARY_GRANT
requesterRef: person-842
beneficiary:
  type: WORKFORCE_USER
  subjectId: person-4821
  workforceStatus: ACTIVE
target:
  application: finance-platform
  environment: production
  tenantId: tenant-vn
entitlement:
  action: invoice.approve
  resourceScope: invoices-under-50m
  role: FINANCE_APPROVER
businessPurpose: Ho tro dot doi soat duoc phe duyet
validFrom: "2026-11-24T01:00:00Z"
validUntil: "2026-11-25T01:00:00Z"
approvalRefs:
  businessChange: change-410
  dataOwner: pending
requestRisk:
  status: NOT_YET_ASSESSED
~~~

Ví dụ này dùng **dữ liệu giả**, không phải schema của một công cụ IAM cụ thể. Trường workforceStatus trong ticket chỉ là snapshot; trước khi phê duyệt/cấp, hệ thống phải **đối chiếu lại với HRIS/IGA hiện hành**. Quyền approve vẫn phải tuân thủ SoD và policy ở runtime.

## 3. Sơ đồ luồng đánh giá risk trong Access request

~~~mermaid
flowchart TD
    R["Người dùng / Sponsor / Workload owner<br/>Gửi access request"] --> C["Chuẩn hóa: subject, action, resource, purpose, TTL"]
    C --> V["Kiểm identity, trạng thái JML, nguồn và dữ liệu bắt buộc"]
    V --> P["Tìm quyền hiện có, entitlement catalog, SoD và policy"]
    P --> S["Đánh giá risk theo scope, sensitivity, context và exposure"]
    S --> H{"Vi phạm hard policy / thiếu điều kiện bắt buộc?"}
    H -->|Có| B["BLOCK / DENY / REMEDIATE"]
    H -->|Không| A{"Tuyến phê duyệt theo risk"}
    A -->|Risk thấp, cho phép theo policy| AP["Rule-based approval có kiểm soát"]
    A -->|Cần owner/SoD/security| M["Business + Data Owner + Security Review"]
    AP --> G["Grant tối thiểu / JIT / PAM / SCIM"]
    M -->|Approve đủ điều kiện| G
    M -->|Reject| B
    G --> Q["Readback + quyền thực tế tại PEP"]
    Q --> L["Monitor, expire, revoke và audit JML"]
~~~

**Thứ tự quan trọng:** kiểm **điều kiện cấm/hard constraints** trước khi tính điểm số tổng hợp, để một điểm risk trung bình không “bù trừ” được vi phạm không thể chấp nhận như **SoD bị cấm, subject đã Leaver, sai tenant hoặc quyền ngoài phạm vi pháp lý**.

## 4. Bối cảnh IAM: Joiner–Mover–Leaver thay đổi risk thế nào?

| Trạng thái | Điểm cần xem trước khi cấp | Ví dụ rủi ro |
| --- | --- | --- |
| **Pre-Joiner** | Proofing, approved start date, account chưa active. | Cấp quyền production trước ngày hiệu lực. |
| **Joiner ACTIVE** | Role baseline, identity assurance, approvals và đúng tenant. | Role mặc định quá rộng hoặc tạo trùng account. |
| **Mover** | Desired role mới, quyền cũ, SoD, cửa sổ overlap. | Cấp Finance Approver khi quyền tạo payment cũ chưa gỡ. |
| **Leaver** | HR effectiveAt, disable, revoke, app-local sessions. | Ticket cũ được duyệt muộn làm hồi sinh quyền. |
| **Suspended** | Lý do và giới hạn xử lý, hiệu lực tạm khóa. | Người đang bị điều tra xin token/role mới. |
| **Rehire** | Stable identity mapping, onboarding mới, không tự khôi phục entitlement cũ. | Đổi email/subject mapping làm nối sai tài khoản đặc quyền. |
| **Contractor expiry** | Sponsor, hợp đồng, ngày hết hạn, tenant đối tác. | Quyền đối tác kéo dài vô hạn sau kết thúc hợp đồng. |
| **Service identity owner change** | Workload còn hoạt động, owner mới, secret/trust cũ. | Tài khoản kỹ thuật không có owner hoặc người cũ vẫn điều khiển workload. |

### Cổng kiểm tra trạng thái bắt buộc

Ở các bước **submission, risk assessment, approval, provisioning và activation**, hệ thống cần có cơ chế kiểm trạng thái hiện hành theo mức rủi ro. Một ticket được mở khi user còn ACTIVE **không còn đủ điều kiện** nếu tới lúc provision user đã Leaver.

**Đừng chỉ quyết định dựa trên thứ tự message arrival**. Dùng nguồn HRIS/contract registry đáng tin, subject ID ổn định, event revision, effectiveAt và xử lý idempotent để không cho event Mover cũ hoặc approval muộn tái cấp quyền đã thu hồi.

## 5. Các yếu tố làm tăng hoặc giảm risk của yêu cầu

Một khung đánh giá có thể nhóm theo **tác động (impact), xác suất/cơ hội lạm dụng (likelihood/exposure) và hiệu quả kiểm soát (controls)**. Đây là phương pháp phân loại; không tự biến thành một con số xác suất thống kê.

| Nhóm yếu tố | Tín hiệu tăng risk | Biện pháp có thể giảm risk |
| --- | --- | --- |
| **Entitlement power** | Global admin, grantRole, impersonate, xóa, export toàn bộ. | Quyền hẹp, chỉ một action/resource, không được tự nâng quyền. |
| **Data sensitivity** | PII, tài chính, secrets, signing keys, production credentials. | Resource scoping, data masking, allowlist, approval của data owner. |
| **Blast radius** | Wildcard trên nhiều tenant, project, account. | Giới hạn tenant, folder, namespace, environment. |
| **Duration** | Standing access không expiry, gia hạn lặp vô hạn. | JIT/TTL ngắn, auto-expire và kiểm revoke. |
| **Subject lifecycle** | Pre-hire, suspended, Leaver, contractor sắp hết hợp đồng. | Chặn theo HRIS, mốc hiệu lực và entitlement eligibility. |
| **Existing access/SoD** | Kết hợp quyền tạo và duyệt, quyền gián tiếp qua nhóm/ACL. | Loại quyền xung đột trước khi cấp, dual control. |
| **Request behavior** | Yêu cầu bất thường về giờ, số lượng, tốc độ hoặc scope. | Xác minh mục đích/sponsor, step-up và security review. |
| **Authentication assurance** | Thiếu MFA/reauthentication cho thao tác đặc quyền. | Phishing-resistant authentication/step-up theo policy. |
| **Endpoint/device context** | Thiết bị không được quản lý, tín hiệu posture yếu hoặc không rõ. | Trusted device/network, hạn chế session, kiểm ngữ cảnh. |
| **Provisioning/revocation capability** | SaaS thiếu API thu hồi, local session tồn dư. | Giới hạn TTL, compensating controls, owner chịu trách nhiệm readback. |
| **Principal type** | API client dùng secret lâu dài, service account không owner. | Managed/workload identity, credential rotation, audience hẹp. |
| **Approval assurance** | Người duyệt không đúng owner, tự duyệt quyền mình. | SoD trong approval, data owner/security reviewer phù hợp. |

**Thiếu dữ liệu không nên làm risk tự động giảm.** Nếu không biết resource classification, subject mapping, SoD hoặc cách thu hồi ở target, cần đánh dấu **UNKNOWN/REQUIRES_REVIEW**, áp fallback an toàn theo policy, không mặc định coi là LOW.

## 6. Bốn loại rủi ro thường bị nhầm lẫn

### 6.1 Inherent risk

**Inherent risk** là rủi ro của yêu cầu **trước khi xét các biện pháp kiểm soát giảm thiểu** theo khung đã định. Ví dụ quyền production-wide read secrets có inherent impact rất lớn, dù requester đã xác thực MFA.

### 6.2 Residual risk

**Residual risk** là phần rủi ro còn lại **sau khi đã xác minh** các kiểm soát có hiệu lực, như resource restriction, JIT, approval độc lập, MFA step-up và revocation. Nếu target không hỗ trợ revoke session hay bằng chứng PEP, không nên cho rằng residual risk đã giảm chỉ vì ticket ghi “TTL=1 giờ”.

### 6.3 Incremental risk

**Incremental risk** là rủi ro phát sinh thêm so với quyền đã có, đặc biệt do **tổ hợp quyền**. Ví dụ:

- User có role **PaymentCreator**, xin thêm **PaymentApprover** có thể tạo xung đột SoD, dù mỗi role đứng riêng là hợp lệ.
- User có quyền sửa CI/CD pipeline, xin thêm quyền đọc secret production có thể mở đường triển khai mã thay thế hoặc chiếm workload.
- Một workload có quyền assumeRole lại xin quyền sửa trust policy có thể tạo khả năng leo thang.

Không thể tính incremental risk chỉ bằng cách cộng số permission names; phải xét **chuỗi hành động, inheritance và effective access**.

### 6.4 Risk acceptance

**Risk acceptance** là quyết định có thẩm quyền chấp nhận phần rủi ro còn lại **trong phạm vi và thời hạn xác định**, với bằng chứng và trách nhiệm rõ. Nó **không phải cơ chế bỏ qua policy cấm tuyệt đối**, không đồng nghĩa với phê duyệt vĩnh viễn, và không thay thế việc theo dõi/thu hồi quyền.

Một yêu cầu bị từ chối vì hard policy không tự trở thành hợp lệ chỉ vì manager chọn “Accept Risk”; cần quy trình exception có thẩm quyền và khả năng cho phép rõ ràng, nếu chính sách tổ chức cho phép.

## 7. Các điều kiện cấm tuyệt đối và cổng kiểm tra trước scoring

Một điểm risk tổng hợp có thể hữu ích để sắp xếp hàng chờ. Nhưng không nên cho phép “điểm rủi ro thấp” bù trừ một **vi phạm bắt buộc**.

| Điều kiện kiểm tra | Ví dụ yêu cầu | Kết quả nên áp dụng theo policy |
| --- | --- | --- |
| **Subject không hợp lệ** | Account đã Leaver xin cấp admin role. | BLOCK trước provisioning, kiểm sự kiện/ticket cũ. |
| **Chưa đủ identity proofing** | Đối tác chưa xác minh danh tính xin quyền sản xuất. | CHỜ xác minh hoặc DENY tùy risk và policy. |
| **Không có sponsor/owner** | Service principal xin wildcard không có nhóm chịu trách nhiệm. | BLOCK và yêu cầu đăng ký owner. |
| **Vi phạm SoD không được phép** | PaymentCreator xin PaymentApprover trong cùng workflow. | DENY hoặc xử lý xung đột trước khi cấp; ngoại lệ chỉ khi policy cho phép. |
| **Sai tenant/trust boundary** | Nhân viên tenant A xin quyền tenant B không có hợp đồng. | DENY hoặc chuyển quy trình đối tác được ủy quyền. |
| **Quyền bị cấm theo data policy** | Xuất dữ liệu RESTRICTED tới một nơi không được phép. | DENY; không cho điểm risk “bù trừ”. |
| **Quyền cấp vượt năng lực của người phê duyệt** | Team lead tự duyệt global admin. | Không hoàn tất; chuyển đúng authority. |
| **Thời điểm không hợp lệ** | Grant trước ngày Joiner effective hoặc sau contractor expiry. | Điều chỉnh/reject, không cấp trước khi đủ điều kiện. |
| **Không thể bảo đảm thu hồi bắt buộc** | Đặc quyền cao trên SaaS không thể revoke và không có kiểm soát bù trừ được duyệt. | BLOCK hoặc escalated risk review. |

**BLOCK không luôn đồng nghĩa đóng ticket vĩnh viễn**. Với dữ liệu thiếu hoặc chưa đủ bảo đảm, hệ thống có thể yêu cầu bổ sung, step-up hoặc điều chỉnh scope. Nhưng **không provision tạm đặc quyền trái policy để tiện xử lý sau**.

## 8. Thiết kế thang đánh giá risk: minh bạch, không tạo “độ chính xác giả”

Một tổ chức có thể dùng khung **định tính LOW/MEDIUM/HIGH/CRITICAL** hoặc score để chuẩn hóa tuyến phê duyệt. Mọi con số bên dưới đều là **mô hình minh họa cần hiệu chuẩn**, không phải chuẩn bắt buộc hay xác suất thiệt hại thực tế.

### 8.1 Các điểm yếu tố

| Yếu tố | 1 điểm | 3 điểm | 5 điểm |
| --- | --- | --- | --- |
| **Action power** | Đọc dữ liệu ít nhạy cảm. | Sửa/duyệt trong phạm vi hẹp. | Quản trị IAM, secrets, mass export hoặc tiền. |
| **Resource impact** | Sandbox, dữ liệu công khai. | Nội bộ, tenant/project quan trọng. | Production critical, PII/secrets/financial control. |
| **Scope/reach** | Một resource hoặc project hẹp. | Một tenant/service. | Nhiều tenants, wildcard, cross-account. |
| **Duration/exposure** | Quyền tạm ngắn có auto-expiry. | Vài ngày với mục đích rõ. | Standing, không expiry hoặc lặp gia hạn liên tục. |
| **Existing access interactions** | Không tạo SoD/privilege chain. | Có quyền liên quan cần rà soát. | Có thể nâng quyền/impersonate; xung đột chưa xử lý. |
| **Operational uncertainty** | Attribute, owner, target và revoke đều verified. | Có một số hạn chế giám sát có bù trừ. | Mapping/revoke/telemetry không rõ; không thể kiểm sau grant. |

Giá trị giữa 1–3–5 có thể được định nghĩa tùy policy; bảng chỉ phác thảo các mức. Tín hiệu như **security incident**, **identity risk** hoặc **SoD hard denial** nên có các **cổng/quy tắc ưu tiên riêng**, không chỉ ép vào một điểm rồi cộng.

### 8.2 Ví dụ tính score (mang tính giảng giải)

Giả sử một request production Finance read-only, tenant hẹp trong 24 giờ, không xung đột SoD nhưng thiếu bằng chứng có thể revoke ngay:

~~~text
Action power                = 1
Resource impact             = 5
Scope                       = 1
Duration                    = 1
Existing access interaction = 1
Operational uncertainty     = 5
Illustrative total          = 14 / 30
~~~

Ví dụ tổ chức định nghĩa:

| Điểm tổng minh họa | Nhãn để định tuyến | Bước tiếp theo |
| --- | --- | --- |
| 6–10 | LOW | Policy checks và approval tối thiểu nếu đủ điều kiện. |
| 11–16 | MEDIUM | Business/resource owner approval, giảm scope nếu có thể. |
| 17–23 | HIGH | Owner và security/SoD review, kiểm soát bù trừ. |
| 24–30 | CRITICAL | Quy trình đặc biệt, đánh giá khả năng thay thế hoặc DENY. |

Với điểm 14, yêu cầu minh họa được gắn **MEDIUM** để **định tuyến**, nhưng **không tự động đủ an toàn để cấp**. Thiếu khả năng revoke có thể là **hard blocker** nếu data policy yêu cầu thu hồi ngay. Mức HIGH/CRITICAL của một yếu tố riêng (như signing key) cũng có thể yêu cầu nâng tuyến dù tổng điểm thấp.

### Giới hạn của cộng điểm

- Thang 1–5 là **thứ bậc/ordinal**; cộng số không tạo ra một ước lượng xác suất tổn thất khách quan.
- Các yếu tố có thể tương quan: quyền global admin đã bao gồm scope rộng và impact cao; cộng có thể đếm trùng.
- Điểm có thể bị thao túng nếu requestor tự khai classification hoặc duration.
- Một quyền hiếm nhưng có hậu quả nghiêm trọng không được “trung bình hóa” bằng nhiều yếu tố tốt.
- Score không thay thế **phê duyệt của người chịu trách nhiệm rủi ro**, security review hoặc policy enforcement.

**Đề xuất vận hành:** giữ **yếu tố cấu thành, cổng hard policy, lý do, độ tin cậy dữ liệu và phiên bản mô hình** bên cạnh nhãn risk, để reviewer có thể giải thích quyết định.

## 9. Inherent risk, controls và residual risk theo workflow

Trước khi cấp quyền, hệ thống nên đánh giá yêu cầu **ban đầu** và các cách giảm phạm vi:

| Phương án | Inherent exposure | Kiểm soát có thể áp | Residual concern |
| --- | --- | --- | --- |
| Standing global admin | Rất cao, ảnh hưởng nhiều tài nguyên. | Thay bằng JIT role hẹp, approval, PAM, step-up. | Phải kiểm JIT expiry và không còn token/session admin cũ. |
| Export mọi khách hàng | Rủi ro dữ liệu lớn. | Chỉ cho export một tập đã phê duyệt, masking, audit, ngắn hạn. | File sau export cần được quản lý tiếp theo data policy. |
| Read secret production | Chiếm workload nếu secret lộ. | Chuyển sang workload federation, chỉ đọc path cần thiết, không cho user download. | Phải đánh giá quyền đối với hệ thống dựa trên secret. |
| Approve payment | Rủi ro tài chính và gian lận. | SoD, giới hạn hạn mức, maker–checker, step-up. | Cần chống self-approval và race tại commit. |
| Data analyst read | Phạm vi tài nguyên có thể rộng. | ABAC theo tenant/classification, view chỉ dữ liệu cần. | Data access qua API khác/batch export có thể bypass. |

### Không giảm risk trên giấy

Nếu ticket ghi **“JIT 1 giờ”** nhưng SCIM cấp local role không có expiration và không có automation thu hồi, thời hạn thực tế có thể là **standing**. Risk sau kiểm soát chỉ được đánh giá thấp hơn nếu:

1. Điều kiện đó được thiết kế và phê duyệt.
2. Connector/target thực sự có khả năng enforcement.
3. Có cơ chế **revoke/expiry** rõ.
4. Có **readback hoặc test effective access** để xác minh.
5. Nếu kiểm soát thất bại, có alert, owner và remediation.

**Residual risk được đánh giá theo kiểm soát đã chứng minh**, không chỉ danh sách lời hứa trong ticket.

## 10. Approval matrix: ai quyết định risk của yêu cầu?

Một tuyến phê duyệt tốt dựa trên **loại quyền, dữ liệu, bối cảnh và conflict**, không chỉ chức danh quản lý hoặc ngưỡng điểm.

| Loại yêu cầu | Chủ thể tham gia | Điều kiện/kiểm soát tối thiểu |
| --- | --- | --- |
| **Baseline access đã được duyệt theo role** | Rule-based IGA workflow và owner của entitlement. | Joiner hợp lệ, đúng mốc, không xung đột SoD; audit tự động. |
| **Read-only dữ liệu nội bộ theo dự án** | Manager + application/data owner theo policy. | Project membership, tenant scope, expiry và readback. |
| **Dữ liệu nhạy cảm hoặc export rộng** | Data owner, business risk owner và security/privacy khi cần. | Mục đích rõ, scope tối thiểu, masking, audit, hạn chế lưu/xuất. |
| **Payment approval** | Business process owner, SoD controller; security nếu rủi ro cao. | Maker-checker, hạn mức, step-up và transaction authorization. |
| **Privileged production access** | System owner, security/PAM owner; dual control nếu policy yêu cầu. | JIT, TTL, strong authentication, session monitoring và revoke. |
| **Global IAM / signing key access** | Authority cao nhất được policy quy định, kiểm soát độc lập. | Xem xét thay thế, giới hạn đặc biệt và kiểm chứng hậu sử dụng. |
| **Partner/contractor access** | Sponsor, data owner, IAM/third-party risk owner. | Phạm vi hợp đồng, tenant, ngày hết hạn, trust và deprovision. |
| **Service/workload credential** | Workload owner, platform/security theo phạm vi. | Principal riêng, audience/scope, secret rotation hoặc workload identity. |

### Tách trách nhiệm để tránh self-approval

- **Requester** nêu nhu cầu và cung cấp bối cảnh, không tự tuyên bố mọi rủi ro đã được chấp nhận.
- **Beneficiary** là chủ thể nhận quyền; requester có thể là manager nộp thay.
- **Manager/sponsor** xác nhận nhu cầu công việc, không tự quyết data classification hoặc quyền security cao nếu không có thẩm quyền.
- **Data/application owner** xác nhận phạm vi dữ liệu/tài nguyên và điều kiện sử dụng.
- **Security/SoD reviewer** thẩm định các rủi ro kỹ thuật, xung đột và kiểm soát.
- **Provisioner** thực thi quyết định được phê duyệt, không tự mở rộng entitlement.
- **Verifier/auditor** kiểm hiệu lực và bằng chứng; cần độc lập phù hợp với mức rủi ro.

**Lưu ý:** không phải mọi request cần sáu chữ ký. Tuyến duyệt phải đủ mạnh nhưng có thể tự động hóa cho **quyền rủi ro thấp, mẫu chuẩn và đủ dữ liệu**, với policy và audit chặt chẽ.

## 11. Quyết định ALLOW, REDUCE, STEP_UP, REVIEW, DENY

Risk assessment hữu ích khi tạo ra **hành động cụ thể** thay vì chỉ màu đỏ/vàng/xanh:

| Decision | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **APPROVE** | Yêu cầu đủ điều kiện và có phê duyệt phù hợp. | Quyền baseline theo vai trò sau Joiner được xác minh. |
| **REDUCE_SCOPE** | Thu hẹp action/resource/tenant trước khi phê duyệt. | Thay global read bằng read 1 project. |
| **TIME_BOUND** | Giới hạn TTL và tự thu hồi, ưu tiên JIT. | Admin chỉ có hiệu lực trong change window. |
| **STEP_UP** | Yêu cầu xác thực/assurance mạnh hơn. | Activation PAM quyền production cần phishing-resistant MFA. |
| **REQUIRE_REVIEW** | Chuyển business/data/security/SoD owner. | Quyền export dữ liệu nhạy cảm hoặc owner không rõ. |
| **REQUEST_INFO** | Thiếu business reason, classification hoặc target mapping. | Không chấp nhận ticket “cần full quyền” không có giải trình. |
| **DENY/BLOCK** | Không cho cấp vì điều kiện không hợp lệ hoặc nguy cơ không thể chấp nhận. | Leaver, không đủ trust, SoD cấm, sai tenant. |
| **EXCEPTION_FLOW** | Quy trình đặc biệt được policy cho phép. | Truy cập khẩn được ghi lý do, phê duyệt và hết hạn. |

### Access request có thể thay đổi sau khi review

Nếu data owner chỉ phê duyệt **read-only tenant A trong 24 giờ** thay vì **read/write mọi tenant trong 90 ngày**, phải tạo một **version/snapshot của entitlement được duyệt**. Connector chỉ được nhận **approved scope**, không cấp theo nội dung gốc còn nằm trong form.

**Bất kỳ thay đổi trọng yếu** về beneficiary, entitlement, tenant, duration hoặc mục đích sau approval phải **đánh giá lại risk và approval route**, không dùng lại chữ ký cũ cho một yêu cầu đã đổi.

## 12. Break-glass và truy cập khẩn cấp

Khi sự cố đang diễn ra, có thể cần cấp quyền ngoài quy trình thường ngày. **Break-glass không phải “tắt hết kiểm tra”**, mà là một luồng có các biện pháp kiểm soát phù hợp tình huống khẩn cấp:

1. Xác định tình trạng khẩn, incident/change ID và lý do.
2. Xác minh danh tính requester/beneficiary bằng phương pháp được policy cho phép; dùng emergency access độc lập nếu IdP chính bị sự cố.
3. Giới hạn quyền đến mức cần để khôi phục dịch vụ và thời gian ngắn nhất hợp lý.
4. Ghi được **actor, target, startAt, expectedEnd, action** và session khi có thể.
5. Áp dual control hoặc approval hậu kiểm nếu quy trình khẩn cho phép và không thể chờ trước.
6. Thu hồi/rotate credential liên quan sau sử dụng, kiểm quyền cũ không tồn dư.
7. Review hậu sự cố, xác định có lạm dụng, mở rộng scope hay không.

**Không biến quy trình khẩn thành đường tắt thường xuyên** cho yêu cầu không chuẩn bị đủ. Đo tỷ lệ và thời lượng break-glass, và điều tra việc dùng lặp lại mà không có incident hợp lệ.

## 13. Risk khi gia hạn, nâng quyền hoặc xin nhiều quyền cùng lúc

Risk có thể tăng không chỉ khi cấp một entitlement mới mà cả khi thay đổi **thời hạn, phạm vi hoặc tổ hợp quyền**:

| Kiểu yêu cầu | Điều phải đánh giá lại |
| --- | --- |
| **Renewal** | Quyền còn cần không? Người dùng/contract còn active? Đã dùng ra sao và có còn owner? |
| **Scope expansion** | Quyền một project chuyển thành toàn tenant có ảnh hưởng gì? |
| **Privilege escalation** | Role Reader → Admin, có khả năng grant/revoke/impersonate không? |
| **Delegation** | Người được ủy quyền có thể chuyển tiếp quyền cho bên khác không? |
| **Bulk request** | Tổng hợp nhiều quyền có tạo SoD/privilege chain hoặc mở nhiều tenant không? |
| **Regrant** | Một quyền đã bị thu hồi vì Mover/Leaver/incident vì sao lại được xin? |
| **Emergency activation** | Có đúng incident, TTL, owner và logging không? |
| **Break-glass renewal** | Vì sao quyền khẩn tiếp tục tồn tại sau cửa sổ xử lý? |

### Không đánh giá từng entitlement tách rời khi chúng tương tác

Ví dụ một request xin ba quyền: **pipeline.write**, **secret.read** và **deployment.approve**. Mỗi quyền có thể chỉ là MEDIUM trong một số ngữ cảnh, nhưng cùng chủ thể có thể sửa pipeline, đọc credential và triển khai thay đổi production. Risk assessment phải kiểm **effective access after grant**, chuỗi khả năng thực hiện và đường leo thang quyền.

Với request hàng loạt, cần áp nguyên tắc:

1. Tạo **risk cho từng entitlement** ở mức cần thiết.
2. Đánh giá **risk của tổ hợp** và SoD trên toàn bộ tập, bao gồm các quyền đã có.
3. Không duyệt toàn bộ batch chỉ vì phần lớn các quyền rủi ro thấp.
4. Quyền không đạt kiểm soát phải được tách và xử lý riêng, hoặc reject batch theo contract.
5. Audit entitlement nào được APPROVE/REJECT/REDUCE, không chỉ một trạng thái cho cả ticket.

### Gia hạn không phải quyền mặc định

Yêu cầu gia hạn phải dùng **current role, current HR status, business justification và risk hiện tại**. Nếu nhân viên đã Mover, một approval cũ của manager Sales không tự chứng minh quyền Sales vẫn cần. Tránh chuỗi gia hạn vô hạn khiến quyền JIT biến thành standing privilege trên thực tế.

## 14. Kết nối risk assessment với IdP, SSO, SCIM và RBAC/ABAC

Hệ thống phân quyền chỉ an toàn nếu **đúng danh tính được cấp đúng quyền tại đúng nơi**.

~~~mermaid
flowchart LR
    HR["HRIS / Sponsor<br/>JML status"] --> IGA["IGA: Access request<br/>Risk + approval"]
    IDP["IdP / SSO / Directory"] --> IGA
    POL["RBAC/ABAC Policy<br/>SoD + entitlement catalog"] --> IGA
    IGA -->|"Approved delta"| CONN["SCIM / API / Cloud IAM / PAM"]
    CONN --> APP["Target account / role"]
    APP --> PEP["App/API PEP<br/>Effective access"]
    IGA -->|"Verification request"| PEP
    PEP --> AUD["Evidence / Audit / SIEM"]
    IGA --> AUD
~~~

### IdP/SSO: xác thực không tự cấp quyền

Một người dùng đã xác thực bằng MFA qua OIDC hoặc SAML có thể **không có quyền** trong ứng dụng cần truy cập. Nếu request đòi mức assurance cao, phải đánh giá **auth_time, phương thức xác thực, context** theo trust contract. Không coi việc đăng nhập SSO từ nhiều giờ trước là một lần **step-up mới**.

### SCIM: provisioning có thể không phản ánh mọi đường truy cập

SCIM thường hỗ trợ tạo/sửa User và Group ở hệ thống đích, nhưng ứng dụng có thể có **local roles, ACL, API keys hoặc sessions** không được SCIM quản lý. Risk của request phải tính cả khả năng thu hồi/kiểm chứng, đặc biệt với quyền production hoặc dữ liệu nhạy cảm.

### RBAC/ABAC: approved role vẫn có thể quá rộng

Role có thể chứa permission wildcard, còn ABAC giới hạn theo tenant, department, classification và thời gian. Trước cấp, cần kiểm:

- Role thực tế cho phép những **actions** nào, kể cả quyền kế thừa.
- Những **resource scopes** nào được mở, có cross-tenant không.
- Conditions có phụ thuộc thuộc tính từ nguồn đáng tin và đủ mới không.
- Có direct ACL, inherited grants hoặc quyền từ nhóm khác mở rộng phạm vi không.
- Khi Mover/Leaver, **policy runtime** có chặn phiên cũ và token cũ không.

**Một role được phê duyệt theo tên không đảm bảo least privilege nếu nội dung role đã thay đổi**. Nên lưu **version/entitlement definition** được duyệt và đánh giá lại khi permission catalog thay đổi trọng yếu.

## 15. Rủi ro token, phiên và đường truy cập còn tồn dư

Phần cấp quyền mới dễ quan sát hơn phần **thu hồi**. Risk phải xét hệ thống có thể chặn effective access sau hạn hay không.

| Đường truy cập | Điểm dễ bị bỏ sót | Kiểm soát cần xét |
| --- | --- | --- |
| **IdP SSO session** | User được cấp quyền mới nhưng session cũ chưa đáp ứng step-up. | Reauthentication/step-up và context verification. |
| **SP local session** | Leaver bị disable IdP nhưng SaaS vẫn còn cookie session. | Session revocation, SLO khi hỗ trợ, TTL và API-level checks. |
| **OAuth access token** | JWT tự chứa còn hạn với scope/role cũ. | TTL, current-state check, denylist/introspection theo kiến trúc. |
| **OAuth refresh token** | Client tiếp tục xin access token mới từ grant cũ. | Revoke grant/refresh token khi kết thúc quyền. |
| **SAML assertion cũ** | SP lập session rồi không kiểm lại quyền. | Session policy, account status và PEP authorization. |
| **Local API key / PAT** | Không nằm trong IdP/SCIM inventory. | Inventory, owner, revoke/rotate khi Mover/Leaver. |
| **Delegated ACL/share link** | Không phụ thuộc quyền group chính. | Direct grant readback, expiry và resource-level probe. |
| **Workload credential** | Secret/key cấp lâu dài, người cũ có thể từng biết. | Workload identity, rotation, owner transfer và vault checks. |

### Bài toán “TTL trên ticket” không bảo đảm TTL trên hệ thống đích

Trước phê duyệt temporary access, cần biết:

1. Connector có đặt **expiresAt** tại target thật không?
2. Nếu target không hỗ trợ TTL native, automation nào sẽ revoke?
3. Khi job revoke thất bại, alert và fallback là gì?
4. Sau revoke, **readback** chứng minh role/ACL đã gỡ chưa?
5. Access token/session cũ còn dùng được trong bao lâu?
6. Có đường API khác hoặc tài khoản cục bộ không thuộc policy không?

Một TTL 30 phút có thể giảm **intended access window**, nhưng risk vẫn cao nếu quyền còn tồn dư hàng giờ qua token hoặc local session. Khi đo residual risk, phải công bố **revoke capability và verified latency** thay vì giả định expiry tức thời.

## 16. Đánh giá risk của service account, client credentials và workload

Yêu cầu cấp quyền máy–máy cần một mô hình khác với nhân viên. Không nên dùng một user giả và mật khẩu chung cho cron/job chỉ để đơn giản hóa approval.

### Thuộc tính cần có

| Thuộc tính workload | Câu hỏi risk |
| --- | --- |
| **workloadId và provenance** | Service identity có được ràng buộc với runtime/cluster/repository đáng tin không? |
| **ownerTeam / business owner** | Ai chịu trách nhiệm khi service đổi chức năng, bị lộ key hoặc ngừng dùng? |
| **environment / namespace** | Principal staging có thể tác động tới production không? |
| **audience / resource** | Token chỉ dùng được cho API đã định hay là token nhiều mục đích? |
| **scope / permission** | Read/write/admin có giới hạn theo dữ liệu/tenant không? |
| **credential model** | Managed identity, federation, mTLS, private key hay secret dài hạn? |
| **rotation/revocation** | Có thể thay hoặc thu hồi key mà không gián đoạn bất ngờ không? |
| **deployment lifecycle** | Khi workload decommission, quyền có tự gỡ và có readback không? |
| **human control** | Ai có thể assume/impersonate principal hoặc sửa trust policy? |

### Ví dụ service account rủi ro tăng do tổ hợp quyền

Service **invoice-sync** đã có quyền **read invoice API**. Nay xin thêm **vault.secrets.read trên toàn bộ production** để “tiện cấu hình”.

Đánh giá:

- **Cần** đọc secret nào? Có thể dùng **workload identity** trực tiếp để lấy credential ngắn hạn?
- Secret vault path có chứa **key của hệ thống khác** không? Blast radius vượt invoice-sync?
- Nếu credential bị lộ, attacker có thể tạo token cho workload nào?
- Principal có thuộc môi trường chính xác và owner được xác nhận không?
- Có cách thu hẹp xuống một path, dùng read-only, TTL và rotation không?

Quyết định phù hợp thường là **REDUCE_SCOPE hoặc redesign** trước khi xin phê duyệt, không tự cho quyền toàn vault vì service đang hoạt động hợp lệ.

### Chủ sở hữu rời công ty

Khi owner là Leaver, không xóa bừa workload đang phục vụ nghiệp vụ. Cần **chuyển ownership, thu hồi quyền người cũ đối với vault/repository/trust, đánh giá rotate secret, kiểm scopes và cập nhật risk record**.

## 17. Request risk thích ứng theo thời điểm, không chỉ ở lúc submit

Một request có thể đổi mức risk giữa các trạng thái:

- Lúc submit, nhân viên còn ACTIVE; lúc provision đã LEAVER.
- Lúc approve, entitlement được định nghĩa là read-only; trước provision, admin sửa role thành read/write.
- Lúc risk assessment, môi trường staging; khi tạo grant, target được chọn nhầm production.
- Lúc phê duyệt, không có xung đột SoD; sau đó user nhận một role khác tạo xung đột.
- Lúc activation JIT, thiết bị không còn compliant hoặc có cảnh báo account compromise.
- Lúc renewal, hợp đồng nhà thầu đã kết thúc.

### Re-evaluation checkpoints

| Thời điểm | Kiểm lại điều gì? |
| --- | --- |
| **Submit** | Identity, mục đích, target, entitlement, required fields. |
| **Assessment** | SoD, quyền hiện có, resource impact, controls, score/reason. |
| **Approval** | Snapshot không đổi, người phê duyệt đúng authority, trạng thái JML còn hợp lệ. |
| **Provision** | Approved entitlement digest, subjectId/tenant, effectiveAt, role version, policy hiện hành. |
| **Activation** | MFA/step-up, device/session context, expiry, không có security hold. |
| **Renewal** | Business need, usage, owner, SoD, access currently effective, residual risk. |
| **Expiration/Revoke** | Grant thực tế bị gỡ, token/session/ACL không còn ngoài SLA. |

Với quyền nhạy cảm, nên **không cấp** nếu approved snapshot không còn khớp request hiện tại. Re-evaluate và reapprove khi entitlement, scope, duration hoặc đối tượng đã thay đổi.

### Time-of-check to time-of-use

Nếu hệ thống kiểm SoD lúc 10:00 rồi cấp quyền lúc 10:05, một quyền khác có thể xuất hiện giữa hai mốc. Cần cơ chế **đối chiếu ngay trước commit**, transaction/lock hoặc optimistic version checks theo kiến trúc, tránh quyền xung đột được cấp do race condition.

## 18. Ngăn approval hijacking, request tampering và escalation

Access-request workflow tự nó là tài nguyên có đặc quyền: kẻ tấn công có thể tìm cách **thay beneficiary, entitlement, target hoặc approver**.

Các trường hợp cần phòng:

1. **Self-approval:** requester hoặc beneficiary tự xác nhận một quyền không được tự duyệt.
2. **Approver substitution:** user thường sửa approverId thành tài khoản đồng lõa hoặc một bot.
3. **Post-approval tampering:** sửa scope từ tenant A sang wildcard sau khi được duyệt.
4. **Stale approval replay:** tái sử dụng approval cũ cho target/role/version mới.
5. **Duplicate provisioning:** retry tạo hai grant hoặc giữ một grant sau khi ticket bị hủy.
6. **Approval race:** Leaver event đến đồng thời với approve và provision.
7. **Privilege via group nesting:** xin nhóm “report-reader” nhưng nhóm lồng chứa admin entitlement.
8. **Catalog drift:** role được phê duyệt thay đổi nội dung trước lúc connector cấp.
9. **Requester masquerading:** tài khoản của manager nộp yêu cầu thay mà không xác thực quyền sponsor.
10. **Audit tampering:** người cấp quyền có thể sửa/bỏ lịch sử để che grant.

### Mẫu bảo vệ

- Server tạo request ID và **immutable approved snapshot** gắn với beneficiary, target, entitlement, scope, duration, owner và policy version.
- Approval là quyết định có thẩm quyền **trên snapshot cụ thể**, không chỉ một chuỗi ticket ID.
- Backend kiểm **role của approver** tại thời điểm phê duyệt, không tin approverId do client tự khai.
- Dùng **idempotency key, expected revision** và lifecycle checks ngay trước provision.
- Cấu hình **audit append-only/được bảo vệ**, separation of duties và alerts với thay đổi quyền nhạy cảm.
- Phải có cơ chế hủy/rollback/compensating revoke khi cấp một phần hoặc connector thất bại.

**Phê duyệt không được kiểm bằng việc nút “Approve” hiển thị hay không**; API xử lý approval cũng phải thực hiện authorization theo subject–action–resource–context và chống cập nhật request ngoài phạm vi.

## 19. State machine của yêu cầu: từ đề xuất đến thu hồi

Một trạng thái duy nhất **APPROVED** là không đủ để phản ánh rủi ro và quyền đã thực sự có hiệu lực.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED: Validate request
    SUBMITTED --> RISK_ASSESSMENT: Trusted data ready
    RISK_ASSESSMENT --> NEEDS_INFORMATION: Missing evidence
    NEEDS_INFORMATION --> RISK_ASSESSMENT: Resubmit
    RISK_ASSESSMENT --> DENIED: Hard policy / rejection
    RISK_ASSESSMENT --> AWAITING_APPROVAL: Policy route
    AWAITING_APPROVAL --> DENIED: Reviewer rejects
    AWAITING_APPROVAL --> APPROVED: All required approvals
    APPROVED --> PROVISIONING: Recheck identity and approved snapshot
    PROVISIONING --> ACTIVE: Readback + activation verified
    PROVISIONING --> REMEDIATION: Provisioning partial/failed
    REMEDIATION --> PROVISIONING: Retry after reconciliation
    ACTIVE --> EXPIRING: validUntil approaches
    EXPIRING --> REVOKING: Expiry/no renewal
    ACTIVE --> REVOKING: Leaver/cancel/compromise
    REVOKING --> REVOKED: Verified denial/removed grant
    REVOKING --> REMEDIATION: Target residual access
    DENIED --> [*]
    REVOKED --> [*]
~~~

Trạng thái có thể khác tùy công cụ; ý tưởng cốt lõi:

| Trạng thái | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| **SUBMITTED** | Có yêu cầu đầy đủ tối thiểu. | Quyền đã được cấp hoặc risk thấp. |
| **RISK_ASSESSMENT** | Đang kiểm policy, identity, impact và SoD. | Có đủ thông tin để approve. |
| **AWAITING_APPROVAL** | Cần người có thẩm quyền quyết định. | Tất cả điều kiện để cấp đã đạt. |
| **APPROVED** | Quyết định được ghi cho một scope/version cụ thể. | Connector đã provision thành công. |
| **PROVISIONING** | Đang tạo/sửa entitlement tại target. | Quyền đã có hiệu lực đúng hoặc không có side effect khác. |
| **ACTIVE** | Đã xác minh phạm vi quyền tại target theo chính sách. | Quyền sẽ tồn tại vô hạn; chỉ hợp lệ trong thời hạn. |
| **REVOKING** | Đã yêu cầu thu hồi. | Quyền không thể dùng nữa. |
| **REVOKED** | Các target bắt buộc đã được xác minh không còn quyền. | Mọi ứng dụng ngoài scope cũng đã sạch. |
| **REMEDIATION** | Có sai lệch, cấp/thu hồi một phần hoặc verification gap. | Có thể đóng ticket như thành công. |

Với một yêu cầu có nhiều entitlements, mỗi mục nên có **trạng thái riêng**; khi một grant bị từ chối hoặc provision thất bại, phải có **phương án rollback/revoke** các grant đã cấp để không tạo tổ hợp quyền rủi ro ngoài approval.

## 20. Pseudocode Java: assessment với hard gates và approved snapshot

Đoạn Java dưới là **pseudocode** nhằm thể hiện **tách quyết định policy khỏi thang score** và revalidation trước provisioning. Đây không phải SDK của một sản phẩm IAM; các interface phụ thuộc vào nền tảng triển khai.

~~~java
// Pseudocode: dữ liệu phải được lấy từ nguồn đáng tin,
// không tin role, tenant hay workforceStatus trong HTTP body.
RiskAssessment assessAccessRequest(AccessRequest request) {
    TrustedIdentity beneficiary = identityRegistry
        .resolveByStableId(request.beneficiaryId());
    TrustedTarget target = entitlementCatalog
        .resolve(request.targetId(), request.entitlementId());
    WorkforceState workforce = hrRepository.current(beneficiary.id());
    EffectiveAccess existingAccess = entitlementResolver
        .currentEffectiveAccess(beneficiary, target.environment());
    ApprovedPurpose purpose = businessWorkflow
        .validatePurpose(request.purposeRef(), beneficiary);

    HardGateResult gates = accessPolicy.checkMandatoryConstraints(
        beneficiary,
        workforce,
        target,
        existingAccess,
        request.validity(),
        purpose
    );
    if (!gates.passed()) {
        audit.recordDecision(request.id(), "BLOCKED", gates.safeReasonCodes());
        return RiskAssessment.blocked(gates.safeReasonCodes());
    }

    RiskFactors factors = riskModel.extractVerifiedFactors(
        beneficiary,
        target,
        existingAccess,
        request.validity(),
        purpose
    );
    if (factors.hasUnresolvedRequiredInputs()) {
        return RiskAssessment.needsReview("risk_inputs_unverified");
    }

    // Điểm chỉ hỗ trợ phân loại; policy có thể yêu cầu nâng tuyến
    // theo critical factor hoặc conflict dù tổng điểm không cao.
    RiskLabel label = riskModel.classify(factors);
    ApprovalRoute route = approvalPolicy.requiredRoute(
        label, factors, target, request.requestType()
    );

    // Đóng băng scope cho approval, tránh đổi entitlement sau duyệt.
    ApprovedCandidateSnapshot snapshot = snapshotService.freeze(
        request.id(),
        beneficiary.id(),
        target,
        request.validity(),
        factors,
        purpose
    );
    return RiskAssessment.awaitingApproval(label, route, snapshot.id());
}
~~~

### Đường provision phải kiểm tra lại

~~~java
// Pseudocode: chỉ provision quyết định đã duyệt,
// không sử dụng payload sửa đổi từ request gốc.
ProvisionResult provisionApprovedAccess(String requestId) {
    ApprovedSnapshot approved = approvalStore.requireApprovedSnapshot(requestId);

    if (!approvalStore.allRequiredSignaturesValid(approved)
            || approved.isExpired()
            || !approved.matchesCurrentRequestRevision()) {
        throw new AccessRequestRejectedException("approval_invalid_or_stale");
    }

    WorkforceState workforce = hrRepository.current(approved.beneficiaryId());
    EffectiveAccess currentAccess = entitlementResolver
        .currentEffectiveAccess(approved.beneficiaryId(), approved.environment());
    if (!lifecyclePolicy.isEligible(workforce, approved.validity())
            || !sodPolicy.permits(currentAccess, approved.entitlement())
            || !policyVersionGuard.isStillCompatible(approved)) {
        throw new AccessRequestRejectedException("risk_changed_reassess");
    }

    // Cần idempotency và kiểm concurrency ở tầng implementation.
    ProvisionJob job = connector.applyExactlyApprovedScope(
        approved, approved.idempotencyKey()
    );

    // API success chỉ là một bước, chưa đồng nghĩa quyền đã đúng.
    VerifiedTargetAccess observed = verifier.readAndProbeTarget(job);
    if (!observed.matchesApprovedScopeAndExpiry(approved)) {
        remediationQueue.open(requestId, observed.safeDifference());
        return ProvisionResult.partial("verification_required");
    }
    audit.recordGrantVerified(requestId, approved.id(), observed.evidenceRef());
    return ProvisionResult.verified();
}
~~~

### Ranh giới cần triển khai thực

- **Concurrency:** quyết định SoD và thay đổi role không được chạy song song tạo race ngoài policy.
- **Audit integrity:** chỉ lưu safe reason codes và refs, không lưu access token, secret hoặc nội dung tài chính nhạy cảm.
- **Idempotency:** retry không cấp trùng, không biến approval hết hạn thành grant mới.
- **Target failure:** khi tạo quyền một phần, phải reconcile hoặc rollback theo workflow.
- **Scope verification:** đọc lại đúng user/tenant/role, không xác minh bằng email dễ đổi/tái sử dụng.
- **Revocation:** cần workflow riêng đến **verified DENY**, không chỉ đặt trạng thái EXPIRED trong IGA.

## 21. Risk rules dưới dạng policy có thể kiểm thử

Một số quy tắc nên được thiết kế như **guardrails có thể kiểm thử**. Ví dụ policy model minh họa:

~~~yaml
policyId: access-request-risk-v4
hardConstraints:
  requireTrustedIdentity: true
  requireEligibleLifecycleState: true
  denyUnapprovedSodConflicts: true
  denyUnapprovedCrossTenantGrants: true
  denyMissingOwnerForPrivilegedWorkload: true
riskFactorSource:
  subjectState: HRIS
  resourceSensitivity: DATA_CATALOG
  entitlementDefinition: IAM_ENTITLEMENT_CATALOG
  effectiveAccess: TARGET_RECONCILIATION
  verificationCoverage: TARGET_CONNECTOR_CAPABILITY
decisions:
  baselineLowRisk:
    allowedRoute: POLICY_APPROVAL
    requireProvisioningReadback: true
  highRisk:
    requireApprovers: [BUSINESS_OWNER, SECURITY_REVIEWER]
    preferTimeBoundAccess: true
    requireStepUpAtActivation: true
  criticalRisk:
    requireExplicitRiskAcceptance: true
    requireIndependentApproval: true
    failClosedIfRevocationCannotBeVerified: true
whenRequiredDataMissing: NEEDS_REVIEW
~~~

Ví dụ không phải cú pháp chuẩn của OPA, XACML hay IGA vendor. Khi hiện thực policy, cần đưa **exception scope, overriding rules, policy version** và risk ownership vào quy trình change control.

### Unit tests cho guardrail

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| Leaver xin role read-only. | BLOCK dù score thấp. |
| ACTIVE user xin tenant khác không có trust/approval. | BLOCK hoặc chuyển quy trình được ủy quyền. |
| PaymentCreator xin PaymentApprover, SoD cấm. | BLOCK cho tới khi giải quyết xung đột. |
| Production admin trong 1 giờ, owner hợp lệ. | Chuyển privileged/JIT route, không auto-approve theo TTL ngắn. |
| Workload không owner xin đọc toàn vault. | BLOCK/request owner và scope hẹp. |
| Thiếu classification tài nguyên nhạy cảm. | NEEDS_REVIEW; không tự xếp LOW. |
| Quyền được duyệt nhưng role catalog thay đổi tăng scope. | Reassess/reapprove trước provision. |
| SCIM applied nhưng local role vượt approved scope. | Không VERIFIED, khắc phục. |

Mọi rule phải có **positive control** tương ứng để chứng minh tổ chức vẫn cấp được quyền hợp lệ. Một hệ thống deny mọi request có thể giảm số grants, nhưng không phải quy trình IAM đúng mục tiêu.

## 22. Audit, metrics và tín hiệu phát hiện risk

Một access request nên tạo dòng bằng chứng từ **gửi yêu cầu → đánh giá → phê duyệt → cấp → sử dụng → hết hạn/thu hồi**.

| Sự kiện | Metadata an toàn cần ghi | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Submitted** | Request ID, requester, beneficiary ref, target, time, version. | Ai yêu cầu cấp quyền cho ai? |
| **Assessed** | Risk model version, factors, hard gate results, unknowns. | Vì sao request được xếp mức risk đó? |
| **Approval** | Approver ref, authority, scope/version, decision, timestamp. | Người nào có thẩm quyền chấp nhận grant? |
| **Provisioning** | Connector, target user ID, entitlement, result, idempotency key. | Quyền nào thực sự được tạo ở đâu? |
| **Verification** | Target/PEP refs, desired-vs-observed, verifiedAt, safe evidence. | Cấp đúng scope và không tạo quyền ngoài approval không? |
| **Activation** | PAM/JIT activation ref, TTL, step-up assurance, context. | Người nhận đã đáp ứng điều kiện để dùng quyền chưa? |
| **Usage** | Subject/service, action, resource class, allowed/denied, time. | Có dùng quyền vượt purpose/ngoài policy không? |
| **Expiration/Revoke** | effectiveAt, requestedAt, appliedAt, verifiedDenyAt, exceptions. | Quyền hết hiệu lực trên tất cả target khi nào? |

**Không ghi access/refresh tokens, mật khẩu, private key, OTP, session cookie hoặc nội dung secret** trong ticket, risk factors hoặc audit event. Một số thuộc tính risk có thể là dữ liệu nhân sự nhạy cảm, nên cần data minimization, role-based log access và retention rõ.

### Các KPI hữu ích

- **High/Critical request share:** phần yêu cầu rủi ro cao theo nhóm entitlement và target; không đánh đồng biến động score với tăng rủi ro thực nếu model thay đổi.
- **Hard-gate violation count:** yêu cầu bị chặn vì lifecycle, SoD, tenant hoặc thiếu owner.
- **Unknown-data share:** yêu cầu có yếu tố quan trọng không đủ bằng chứng, cần review.
- **Risk-reduction rate:** tỷ lệ request được thu hẹp scope, chuyển JIT hoặc thay thiết kế sau đánh giá.
- **Overprivileged grant rate:** grants thực tế rộng hơn approved snapshot.
- **Approval segregation compliance:** tỷ lệ approval tuân thủ đúng authority/SoD.
- **Time to approve by risk tier:** thời gian chờ theo risk, nhận diện nút thắt chứ không thúc ép auto-approve high risk.
- **Provisioning verification coverage:** tỷ lệ target/entitlement có readback hoặc PEP evidence.
- **Time-bound expiration compliance:** tỷ lệ quyền hết hạn thực sự được revoke trong SLA.
- **Post-Leaver residual access:** số request/grant vẫn cho quyền sau Leaver.
- **Repeated emergency grants:** tín hiệu cần tối ưu baseline hoặc phát hiện lạm dụng break-glass.

### Không tối ưu sai KPI

“Approve nhanh hơn” không đồng nghĩa an toàn hơn nếu nguy cơ tăng; “reject nhiều hơn” không đồng nghĩa least privilege tốt hơn nếu nghiệp vụ bị gián đoạn; “score trung bình giảm” có thể do thay model hoặc bỏ target rủi ro khỏi measurement scope. Nên báo **policy version, coverage, false-deny và các findings còn tồn** cùng các chỉ số.

## 23. Tình huống thực hành: Mover xin quyền phê duyệt thanh toán

### Bối cảnh

Một nhân viên tên **Ngân** chuyển từ bộ phận Sales sang Finance. HRIS đã ghi Mover với effectiveAt ngày 23/11. IGA dự kiến gỡ quyền Sales và cấp baseline Finance theo role mới.

Ngân gửi yêu cầu:

~~~yaml
requestId: ar-demo-024
requesterRef: ngan-test
beneficiaryRef: ngan-test
requestType: TEMPORARY_GRANT
target: finance-payment-prod
tenant: tenant-vn
requestedRole: PAYMENT_APPROVER
requestedScope: all-invoices
requestedDurationDays: 90
reason: Ho tro doi soat cuoi ky
~~~

Các dữ liệu minh họa được cấu trúc cho bài học; không chứa danh tính hay quyền thật.

### Bước 1 — Xác minh danh tính và lifecycle

Risk engine xác minh **subject ID từ HRIS/IdP**, trạng thái ACTIVE hiện hành và Mover effectiveAt. Không nhận department từ body request làm nguồn chính. So với hệ thống nguồn, IGA thấy Ngân vẫn có một direct entitlement **PAYMENT_CREATOR** từ dự án cũ chưa được gỡ.

**Kết quả:** cần giải quyết SoD trước khi cấp quyền Payment Approver; không thể chỉ dựa vào score.

### Bước 2 — Đánh giá risk của yêu cầu gốc

| Yếu tố | Nhận xét |
| --- | --- |
| Action power | Approve payments — đặc quyền nghiệp vụ nhạy cảm. |
| Resource impact | Production financial transactions. |
| Scope | Mọi hóa đơn trong tenant VN, chưa giới hạn hạn mức. |
| Duration | 90 ngày, dài so với đợt đối soát nêu trong lý do. |
| Existing access | Có PAYMENT_CREATOR, gây conflict SoD. |
| Uncertainty | Chưa rõ khả năng revoke local session/approval role trên target. |

**Cổng hard policy FAIL do SoD**; vì thế **không cấp quyền**, kể cả nếu công thức score cho kết quả MEDIUM.

### Bước 3 — Đề xuất scope giảm rủi ro

Business owner điều chỉnh nhu cầu:

- Gỡ quyền PAYMENT_CREATOR không còn phù hợp; kiểm tại Finance API đã **DENY**.
- Chỉ cho **PAYMENT_APPROVER** đối với invoices dưới một hạn mức được phê duyệt.
- Thời hạn **24 giờ**, kích hoạt qua PAM/JIT hoặc quy trình time-bound được hỗ trợ.
- Yêu cầu **step-up** trước activation nếu policy định nghĩa.
- Cần approval của **Finance process owner** và người kiểm SoD; security reviewer nếu model/target yêu cầu.
- API phải kiểm **requesterId khác approverId** và trạng thái PENDING tại thời điểm commit.

### Bước 4 — Risk reassessment và phê duyệt

Sau khi loại xung đột và giảm scope, risk engine chấm lại risk **dựa trên những thuộc tính đáng tin và entitlement version mới**, lưu cả risk trước/sau cùng lý do. Những yếu tố residual chưa giải quyết, ví dụ **khả năng thu hồi token cũ**, phải được trình bày cho reviewer.

Approval chỉ có giá trị cho **role, tenant, hạn mức và 24 giờ đã được đóng băng trong approved snapshot**. Nếu requester sửa lại từ 24 giờ thành 90 ngày sau khi duyệt, hệ thống phải yêu cầu đánh giá và phê duyệt mới.

### Bước 5 — Provision có xác minh

SCIM/API/PAM connector áp quyền lên đúng account target với request ID/idempotency key. Sau khi target trả kết quả, hệ thống:

1. Readback **role thực tế** và thời hạn.
2. Probe một payment dưới hạn mức được phép và không do Ngân tạo: ALLOW nếu đủ điều kiện.
3. Probe payment do chính Ngân tạo: DENY theo SoD.
4. Probe thanh toán vượt hạn mức: DENY.
5. Probe tenant khác: DENY.
6. Ghi evidence, policy version và approver IDs.

Nếu API target không hỗ trợ giới hạn hạn mức, cần **không cấp như đã duyệt** hoặc áp một kiểm soát thực thi tương đương được xác minh; không ghi approved scope hẹp trên ticket nhưng grant quyền rộng ở backend.

### Bước 6 — Hết hạn và thu hồi

Đến 24 giờ, workflow phải revoke quyền, kết thúc phiên có liên quan theo khả năng và kiểm **không còn approve được ở API**. Ticket chỉ được đánh dấu **REVOKED/VERIFIED** khi bằng chứng của các target bắt buộc đạt; nếu còn local role hoặc session cho phép approve, status phải là REMEDIATION.

**Kết luận:** risk scoring hữu ích khi giúp sửa đề xuất ban đầu thành một yêu cầu nhỏ, có kiểm soát và xác minh được. Quyết định đúng **không phải nhất thiết từ chối mọi quyền nhạy cảm**, mà là cấp quyền hợp lệ với **scope, approval, thời hạn và enforcement phù hợp**.

## 24. Tình huống thứ hai: yêu cầu API access của service account

### Bối cảnh

Ứng dụng **data-sync** chạy trong môi trường staging xin quyền gọi Finance API production với scope **invoice.read**. Service principal đang dùng **client secret tĩnh** có tuổi cao và owner team chưa rõ; mục đích là thử tích hợp trước production cutover.

### Đánh giá

- **Cross-environment:** token/credential của staging không nên tự có quyền production.
- **Owner:** không rõ ai chịu trách nhiệm cho credential và grant; thiếu điều kiện governance.
- **Target sensitivity:** Finance API production có thể chứa dữ liệu nhạy cảm.
- **Scope:** invoice.read nghe có vẻ nhỏ nhưng nếu RS không kiểm tenant thì blast radius lớn.
- **Credential model:** secret lâu đời làm tăng nguy cơ lộ và khó thu hồi.
- **Lifecycle:** service dự kiến decommission sau thử nghiệm; phải có ngày hết hạn và deprovision.

### Quyết định phù hợp

**REQUEST_INFO hoặc BLOCK** cho tới khi có owner, trust và mục đích rõ. Phương án giảm risk có thể:

1. Tạo **workload identity riêng** cho production với owner hợp lệ và trust binding hẹp.
2. Chọn sandbox/test data nếu không cần production.
3. Nếu production bắt buộc, cấp quyền **resource/tenant hẹp**, audience Finance API, TTL và kiểm soát IP/workload provenance phù hợp.
4. Tránh secret hard-code; ưu tiên managed/workload federation hoặc credential được bảo vệ/luân chuyển theo nền tảng.
5. Có phê duyệt của API owner và security/platform theo policy.
6. Sau triển khai, test scope đúng và cross-tenant denied; sau decommission, verify token/credential cũ không còn hoạt động.

**Một client hợp lệ không mặc nhiên đủ điều kiện dùng mọi API**. Risk của yêu cầu máy–máy gắn chặt với workload identity, credential lifecycle và effective scope.

## 25. Ma trận kiểm thử Risk của yêu cầu

Bộ test sau cần thực hiện **với danh tính và tài nguyên thử được cấp phép**, không gửi request làm thay đổi đặc quyền production ngoài phạm vi kiểm thử.

| ID | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| Q01 | Joiner hợp lệ xin baseline role đúng ngày hiệu lực. | Đi đúng route và được cấp sau approval/rule checks. |
| Q02 | Pre-hire xin production admin trước ngày bắt đầu. | BLOCK/DEFER tới khi đủ điều kiện. |
| Q03 | Leaver có ticket APPROVED trước ngày nghỉ nhưng chưa provision. | Revalidate và BLOCK. |
| Q04 | Mover xin quyền mới khi role cũ gây xung đột SoD. | Chặn cho tới khi giải quyết conflict. |
| Q05 | Role read-only một tenant được yêu cầu trong thời gian ngắn. | Phân loại theo policy, không tự coi LOW khi data impact cao. |
| Q06 | Global admin được requestor gắn “low risk” trong body. | Server dùng catalog/trusted risk factors, không tin nhãn client. |
| Q07 | Requester không phải beneficiary và không có quyền sponsor. | Từ chối hoặc yêu cầu sponsor hợp lệ. |
| Q08 | Người yêu cầu tự approve privileged grant của mình. | Block self-approval theo SoD. |
| Q09 | Client đổi approverId trong request body. | API không chấp nhận approver không được authorize. |
| Q10 | Request bị sửa tenant A thành B sau approval. | Reassess và reapprove; không provision scope mới. |
| Q11 | Request đổi TTL 24 giờ thành 90 ngày sau duyệt. | Approved snapshot mismatch, chặn. |
| Q12 | Role catalog tăng permissions sau khi được approve. | Phát hiện drift, yêu cầu đánh giá lại. |
| Q13 | Bulk request có một role SoD cấm. | Không cấp role cấm; xử lý batch theo contract. |
| Q14 | Hai quyền đơn lẻ hợp lệ nhưng kết hợp tạo privilege escalation. | Nhận diện incremental risk, escalated review. |
| Q15 | Data classification thiếu hoặc không đáng tin. | NEEDS_REVIEW/SAFE BLOCK, không mặc định LOW. |
| Q16 | Account ACTIVE nhưng bị security hold. | Chặn theo policy, không cho score bù trừ. |
| Q17 | Yêu cầu cross-tenant không có hợp đồng trust. | DENY/chuyển đúng quy trình đối tác. |
| Q18 | Access request chỉ cần đọc một secret path nhưng xin toàn vault. | Đề xuất REDUCE_SCOPE hoặc DENY. |
| Q19 | JIT role hết hạn nhưng target vẫn ALLOW. | Không VERIFIED, tạo incident/remediation. |
| Q20 | SCIM trả success nhưng local role rộng hơn approval. | Detect drift, không đóng ACTIVE. |
| Q21 | OAuth JWT cũ vẫn cho phép action sau expiry grant. | Đánh giá residual risk và chặn theo SLA. |
| Q22 | PAM step-up thất bại trước activation. | Không kích hoạt đặc quyền. |
| Q23 | Privileged request có manager approval nhưng thiếu data/security owner bắt buộc. | Không APPROVED đầy đủ. |
| Q24 | Request owner không còn active tại thời điểm provision. | Revalidate, không thực thi approval cũ. |
| Q25 | Service principal không có owner xin production permission. | BLOCK/request owner. |
| Q26 | Staging workload xin production API với sai audience. | Deny trust/audience, không mở scope. |
| Q27 | Client secret cũ đã rotate nhưng credential cũ vẫn lấy được token. | FAIL revocation verification. |
| Q28 | Grant hết hạn, job revoke retry trùng nhiều lần. | Idempotent; trạng thái cuối vẫn REVOKED, không regrant. |
| Q29 | Event Mover cũ đến sau Leaver. | Không kích hoạt lại account/quyền. |
| Q30 | Approval và Leaver xảy ra đồng thời. | Transaction/revision guard ngăn cấp trái trạng thái. |
| Q31 | PDP hoặc PIP lỗi khi đánh giá request nhạy cảm. | Không tự APPROVE; phân loại lỗi và fallback an toàn. |
| Q32 | Risk score tổng thấp nhưng một hard constraint FAIL. | BLOCK, không cho score ghi đè policy. |
| Q33 | Access request bị DENIED nhưng connector vẫn tạo grant. | Phát hiện unauthorized grant; thu hồi và audit. |
| Q34 | Expired grant đã revoke nhưng SP local session vẫn có quyền. | Chưa REVOKED VERIFIED; remediation. |
| Q35 | User được cấp role đúng nhưng tenant/resource sai. | Không ACTIVE; sửa mapping và reverify. |
| Q36 | Requester xin quyền hiếm dùng nhưng có DR runbook/owner hợp lệ. | Đánh giá JIT/eligible, không auto-reject chỉ vì dormant. |
| Q37 | API review trả 503 thay vì policy decision. | Không tính PASS DENY; xác định outage. |
| Q38 | Reviewer bấm APPROVE mà API không kiểm role reviewer. | Security test phát hiện BFLA, chặn. |
| Q39 | Temporary access được gia hạn nhiều lần không re-review. | Yêu cầu đánh giá nhu cầu/SoD/risk hiện hành. |
| Q40 | Service account owner Leaver nhưng workload còn chạy hợp lệ. | Chuyển owner, thu hồi quyền cá nhân, kiểm credential; không xóa bừa. |

### Test phải kiểm cả quyết định và side effects

Với một yêu cầu bị DENY, cần xác nhận **không có grant, role, group, ACL, token hoặc event cấp quyền trái phép** được tạo. Với một yêu cầu được APPROVE, cần xác nhận chỉ **approved delta** được áp. Một HTTP 200/204 từ connector chỉ cho biết một bước hoàn tất, chưa chứng minh scope/expiry của quyền thực tế.

### Positive control

Trước khi kết luận negative test PASS, xác nhận một request hợp lệ trên cùng endpoint/tenant vẫn được xử lý đúng. Nếu target down và trả 503, không được coi đó là kiểm soát authorization hay risk gate đã hoạt động.

## 26. Checklist để đưa risk-aware access request vào production

1. **Request schema:** có requester, beneficiary, stable ID, action, target, tenant, scope, purpose và TTL rõ ràng.
2. **Trusted sources:** HRIS/IdP/IGA, catalog, data classification, SoD và resource mapping được xác thực.
3. **Hard constraints:** lifecycle, tenant, SoD, approval authority, data policy và owner được kiểm trước scoring.
4. **Risk model version:** yếu tố, trọng số, threshold, unknown handling và chính sách nâng tuyến minh bạch.
5. **Inherent/residual risk:** có giải thích kiểm soát nào thực sự được áp và phần nguy cơ nào còn.
6. **Approval matrix:** manager/business/data/security theo entitlement; chặn self-approval.
7. **Least privilege:** quyền hẹp nhất đủ phục vụ mục đích; không gán wildcard khi có phương án an toàn hơn.
8. **Time-bound access:** JIT/TTL/auto-expire với **khả năng revoke có kiểm chứng**, không chỉ có ngày hết hạn trên ticket.
9. **Immutable approved scope:** entitlement digest, target, tenant, thời hạn và version được gắn với approval.
10. **Lifecycle revalidation:** kiểm JML/SoD/target state ngay trước provision và trước activation quyền cao.
11. **Secure provisioning:** idempotency, concurrency guard, partial failure handling và approved delta.
12. **Readback/PEP verification:** không chỉ tin connector response; kiểm entitlement thực và action-level access.
13. **Token/session coverage:** local sessions, OAuth grants, access tokens, SAML/OIDC sessions và PAT nếu thuộc scope.
14. **Service/workload:** owner, trust, scopes, environment, secret rotation và decommission.
15. **Emergency route:** break-glass có thời hạn, justification, audit và post-incident review.
16. **Exceptions:** risk acceptance đúng authority, scope, owner, expiry và compensating controls.
17. **Monitoring:** anomalies, repeated renewals, hard-gate violations và residual access được cảnh báo.
18. **Metrics:** risk-tier approvals, unknown-data, scope reduction, overgrant, revoke latency và coverage.
19. **Privacy:** không thu thập/log quá mức dữ liệu nhân sự; không lưu token, mật khẩu, secret trong ticket.
20. **Evidence & sign-off:** chỉ báo **VERIFIED** khi grant/revoke đáp ứng đúng scope, thời gian và target bắt buộc.

Các quyền **Critical/High** cần xác định rõ cách xử lý nếu target không có khả năng xác minh hiệu lực/thu hồi. Không thể xem là đạt least privilege chỉ bằng cam kết thủ công chưa kiểm chứng.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Risk của một yêu cầu truy cập khác gì identity risk?

**Trả lời:** Request risk đánh giá tác động/cơ hội lạm dụng khi **cấp quyền cụ thể** cho một chủ thể trong bối cảnh nhất định. Identity risk đánh giá mức tin cậy hoặc dấu hiệu xâm phạm của danh tính/phiên. Identity risk thấp không tự chứng minh quyền nguy hiểm là hợp lệ.

**Câu 2.** Vì sao không thể duyệt quyền Global Admin chỉ vì điểm tổng được xếp MEDIUM?

**Trả lời:** Score mang tính định tuyến, không thay thế hard policy, phê duyệt đặc quyền cao và đánh giá blast radius. Quyền có khả năng tác động cực lớn cần rule nâng tuyến/cấm riêng.

**Câu 3.** Một nhân viên Mover có quyền PaymentCreator và xin PaymentApprover. Rủi ro chính là gì?

**Trả lời:** Có thể tạo xung đột SoD và cho người đó tự tạo rồi duyệt giao dịch. Phải kiểm **effective access after grant**, gỡ quyền xung đột hoặc áp kiểm soát nghiệp vụ phù hợp trước khi cấp.

**Câu 4.** Gia hạn một quyền tạm đã được cấp năm ngoái có thể auto-approve vì approval cũ không?

**Trả lời:** Không mặc định. Cần kiểm lại mục đích, owner, trạng thái JML, SoD, role/version, scope và duration. Approval phải gắn với request snapshot hiện hành.

**Câu 5.** Nếu grant có expiresAt sau một giờ, có chắc quyền bị thu hồi đúng một giờ?

**Trả lời:** Không. Target có thể thiếu native TTL, connector revoke thất bại hoặc token/session cũ còn hiệu lực. Cần readback và quyền thực tế bị PEP từ chối theo SLA.

**Câu 6.** Vì sao một access request có thể rủi ro hơn tổng của từng entitlement riêng lẻ?

**Trả lời:** Vì quyền kết hợp có thể tạo privilege escalation, impersonation hoặc SoD conflict dù từng quyền đứng riêng có vẻ phù hợp.

**Câu 7.** Với service principal không có manager cá nhân, ai nên duyệt?

**Trả lời:** Cần workload/application owner, business/API owner và platform/security reviewer theo policy. Phải có trách nhiệm rõ cho scope, môi trường, credential và decommission.

**Câu 8.** Data classification của target bị thiếu. Có thể coi tài nguyên ít nhạy cảm để không chậm approval không?

**Trả lời:** Không nên. Thiếu yếu tố bắt buộc cần REQUEST_INFO, NEEDS_REVIEW hoặc fail-safe theo policy. Không tự cho risk LOW khi không có nguồn đáng tin.

**Câu 9.** Người duyệt nhấn APPROVE rồi requester sửa quyền từ read-only thành admin. Hệ thống phải làm gì?

**Trả lời:** Từ chối provisioning theo snapshot không khớp; đánh giá lại risk và approval mới cho entitlement/target/scope đã thay đổi.

**Câu 10.** SCIM đã trả success và IdP đã gỡ role, có thể đóng ticket thu hồi không?

**Trả lời:** Chưa chắc. Cần kiểm local role, ACL, session/API key, access token và khả năng truy cập thực tế tại target theo SLA.

**Câu 11.** Break-glass có được miễn toàn bộ risk assessment và audit không?

**Trả lời:** Không. Luồng khẩn có thể dùng tuyến approval khác hoặc hậu kiểm theo policy, nhưng vẫn cần xác minh, scope, thời hạn, theo dõi, revoke và kiểm toán.

**Câu 12.** Vì sao phải xác minh trạng thái JML ngay trước provision nếu đã kiểm lúc submit?

**Trả lời:** Trạng thái subject, quyền hiện có và policy có thể đổi giữa hai mốc. Kiểm lại ngăn việc ticket cũ/approval muộn tái cấp quyền cho Leaver hoặc tạo xung đột SoD mới.

**Câu 13.** Risk acceptance có nghĩa yêu cầu chắc chắn phải được cấp không?

**Trả lời:** Không. Acceptance phải đúng thẩm quyền, phạm vi và policy; một hard prohibition hoặc yêu cầu không thể được target thực thi an toàn vẫn có thể bị DENY.

**Câu 14.** Những bằng chứng nào chứng minh request đã được xử lý đúng?

**Trả lời:** Request/scope/version, trusted JML state, risk factors và hard gates, approvals hợp lệ, approved snapshot, target provisioning/readback, PEP allow/deny probes, thời hạn, revoke result, timestamps, owner và audit không chứa credential.

---

**Ghi nhớ:** **Risk của access request là rủi ro do cấp một quyền cụ thể trong một ngữ cảnh cụ thể**, không phải chỉ một điểm số hay tình trạng đăng nhập của người yêu cầu. Quy trình IAM an toàn phải **kiểm hard constraints, tính quyền hiệu lực và SoD, đánh giá phạm vi/tài nguyên/thời hạn, định tuyến phê duyệt đúng thẩm quyền, ưu tiên least privilege/JIT, bảo vệ approved snapshot và xác minh grant/revoke tại điểm thực thi**. Khi **Joiner–Mover–Leaver** làm thay đổi trạng thái, risk và điều kiện cấp quyền phải được đánh giá lại để không mở ra **quyền truy cập tồn dư**.
