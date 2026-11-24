# Xác định policy model khi thiết kế chương trình IAM

Một chương trình **Identity and Access Management (IAM)** không thể quản trị vòng đời danh tính chỉ bằng việc tạo tài khoản và đồng bộ nhóm. Hệ thống còn phải trả lời nhất quán: **ai được truy cập tài nguyên nào, thực hiện hành động gì, trong điều kiện nào, trong bao lâu và ai chịu trách nhiệm cho quyết định đó?** Tập hợp quy tắc ra quyết định, dữ liệu đầu vào, thứ tự áp dụng và cơ chế thực thi được gọi là **policy model** (mô hình chính sách).

Ví dụ, một nhân viên có role `FINANCE_ANALYST` nhưng đang bị khóa vì sự cố bảo mật thì có được tải báo cáo hay không? Khi họ chuyển sang bộ phận kỹ thuật, quyền nào phải được thu hồi ngay? Nếu hệ thống không nhận được trạng thái hợp đồng của nhà thầu, chính sách sẽ xử lý thế nào? Đó là các quyết định cần có lời giải được kiểm chứng trong thiết kế policy model.

Bài học thuộc chương **Thiết kế chương trình IAM**, module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Phạm vi áp dụng bao gồm **Joiner–Mover–Leaver (JML)**, xác minh danh tính, cấp và thu hồi tài khoản/quyền, IdP, SSO, SCIM, RBAC/ABAC, danh tính dịch vụ, kiểm toán và ngăn quyền truy cập tồn dư. Không có ghi chú bổ sung riêng cho bài học này.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt policy model với role model, identity source, account scope, xác thực và cơ chế provisioning.
2. Xác định các đầu vào tối thiểu của một quyết định truy cập: chủ thể, hành động, tài nguyên, ngữ cảnh và trạng thái vòng đời.
3. Thiết kế chính sách rõ **điều kiện cho phép, điều kiện từ chối, quy tắc xung đột, mặc định khi thiếu dữ liệu** và điểm thực thi.
4. Liên kết chính sách cấp/thu hồi quyền trong JML với quyết định phân quyền tại thời điểm truy cập.
5. Kết hợp RBAC, ABAC, kiểm soát phân tách nhiệm vụ (SoD), đặc quyền có thời hạn và ngoại lệ khẩn cấp.
6. Xây dựng hợp đồng dữ liệu, ma trận kiểm thử, nhật ký kiểm toán và cơ chế quản trị phiên bản policy.

## 2. Policy model là gì và khác những thành phần IAM khác thế nào?

**Policy** là quy tắc quy định điều kiện và kết quả của một quyết định. **Policy model** mô tả cách biểu diễn, đánh giá, kết hợp, thực thi và quản trị một hoặc nhiều policy trong toàn hệ thống.

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Identity source** | Ai hoặc hệ thống nào có thẩm quyền xác nhận thông tin? | HRIS xác nhận trạng thái nhân viên; hệ thống hợp đồng xác nhận ngày hết hạn nhà thầu. |
| **Account scope** | Những tài khoản và hệ thống nào thuộc phạm vi quản trị? | Tài khoản IdP, SaaS, quản trị cloud, tài khoản local và service account. |
| **Role model** | Công việc hoặc trách nhiệm nào tương ứng những entitlement gì? | Role `FINANCE_ANALYST` gồm quyền đọc báo cáo tài chính được phê duyệt. |
| **Policy model** | Điều kiện nào cho phép/cấm gán role, cấp quyền và thực hiện hành động? | Chỉ cho phép đọc báo cáo trong tenant được phân công khi danh tính hợp lệ. |
| **IdP / SSO** | Ai được xác thực, có thể tạo phiên đăng nhập và truyền claim ra sao? | MFA, OIDC/SAML, xác thực liên kết. |
| **Provisioning / SCIM / API** | Làm thế nào áp trạng thái tài khoản và entitlement xuống hệ thống đích? | Tạo user, gán nhóm, vô hiệu hóa account hoặc gỡ quyền. |
| **Ứng dụng / API / tài nguyên** | Quyết định truy cập được thực thi ở đâu? | API từ chối đọc dữ liệu không thuộc tenant của người gọi. |

Một role hợp lệ **không tự động đồng nghĩa** với quyền truy cập đang được phép. Policy có thể yêu cầu trạng thái làm việc hợp lệ, không bị khóa bảo mật, đúng tenant, giới hạn thời gian hoặc phê duyệt bổ sung.

### Phân biệt hai thời điểm ra quyết định

Policy model nên mô tả rõ **hai tầng** thường phối hợp với nhau:

- **Chính sách vòng đời và cấp phát (provisioning/governance policy):** quyết định có nên tạo account, gán role, thu hồi entitlement hoặc yêu cầu rà soát/phê duyệt khi nhận sự kiện JML.
- **Chính sách thực thi lúc truy cập (runtime authorization policy):** quyết định có cho phép một hành động cụ thể trên tài nguyên cụ thể ở thời điểm yêu cầu được xử lý không.

Ví dụ, IAM provision role `REPORT_VIEWER` cho nhân viên tại ứng dụng. Khi nhân viên gọi API đọc báo cáo, ứng dụng vẫn phải kiểm tra báo cáo thuộc đúng tenant và người dùng không bị hạn chế bởi chính sách đang hiệu lực. Tầng provisioning và tầng runtime cần **nhất quán về chính sách** nhưng không nhất thiết chạy chung một bộ máy.

## 3. Các thành phần trong một quyết định policy

Mô hình phân quyền thông dụng có thể dùng bộ dữ liệu **subject – action – resource – environment**, bổ sung thông tin quan hệ, trạng thái vòng đời và nguồn xác minh.

| Thành phần | Ý nghĩa | Dữ liệu minh họa |
|---|---|---|
| **Subject** | Danh tính hoặc workload yêu cầu truy cập | `identityId`, `identityType`, role, tenant, trạng thái hợp đồng. |
| **Action** | Hành động được yêu cầu | `report:read`, `expense:approve`, `user:disable`, `secret:rotate`. |
| **Resource** | Tài nguyên hoặc đối tượng được truy cập | `reportId`, `tenantId`, `projectId`, độ nhạy, owner. |
| **Environment** | Ngữ cảnh thực thi | Thời gian, môi trường prod, trạng thái MFA, mức tin cậy phiên, rủi ro. |
| **Relationship** | Quan hệ giữa chủ thể và tài nguyên | Thành viên dự án, người quản lý, chủ sở hữu tài nguyên, người tạo giao dịch. |
| **Lifecycle state** | Điều kiện tồn tại và quyền truy cập của danh tính | `ACTIVE`, ngày hiệu lực, kết thúc hợp đồng, `securityHold`. |
| **Policy metadata** | Căn cứ và khả năng kiểm toán quyết định | Policy ID, phiên bản, owner, hiệu lực, approval, lý do, correlation ID. |

Hệ thống phải định nghĩa **nguồn có thẩm quyền** cho từng thuộc tính. Phòng ban có thể đến từ HRIS; owner của workload đến từ service catalog; trạng thái khóa khẩn cấp đến từ bộ phận an ninh; phân loại dữ liệu đến từ data catalog. Không nên tin trực tiếp vào giá trị tenant/role do client gửi nếu server có thể xác minh hoặc dẫn xuất chúng từ nguồn tin cậy.

### Một yêu cầu quyết định minh họa

~~~json
{
  "subject": {
    "identityId": "idn-1042",
    "identityType": "EMPLOYEE",
    "lifecycleStatus": "ACTIVE",
    "securityHold": false,
    "effectiveRoles": ["FINANCE_ANALYST"],
    "assignedTenants": ["VN"]
  },
  "action": "report:read",
  "resource": {
    "resourceId": "report-853",
    "tenantId": "VN",
    "classification": "INTERNAL"
  },
  "environment": {
    "mfaSatisfied": true,
    "sessionRisk": "LOW"
  },
  "requestId": "req-c3f8"
}
~~~

Đây là dữ liệu minh họa ở điểm quyết định, **không phải bộ claim nên nhét nguyên vào token**. Tính tin cậy và độ mới của thông tin là quan trọng: các thuộc tính vòng đời nhạy cảm có thể cần được tra cứu từ nguồn đã xác thực hoặc được duy trì qua bộ nhớ đệm có giới hạn rõ ràng.

## 4. Các lớp chính sách cần có trong chương trình IAM

Không nên gom mọi quy tắc vào một biểu thức cho phép duy nhất. Phân loại policy theo mục đích giúp xác định owner và thời điểm thực thi:

| Lớp policy | Câu hỏi ra quyết định | Điểm áp dụng thường gặp |
|---|---|---|
| **Identity eligibility** | Danh tính có hợp lệ và đúng thời điểm hiệu lực? | Lớp nhận nguồn, IGA, IdP, hệ thống quản trị vòng đời. |
| **Account lifecycle** | Khi nào tạo, khóa, vô hiệu hóa, xóa hoặc rà soát account? | Workflow JML, provisioning connector, hệ thống đích. |
| **Access assignment** | Ai đủ điều kiện nhận role/entitlement? Cần ai phê duyệt? | IGA, yêu cầu truy cập, role catalog. |
| **Authentication / session** | Cần MFA, xác thực mạnh, thời hạn phiên hay điều kiện thiết bị nào? | IdP, SSO, dịch vụ kiểm soát phiên. |
| **Runtime authorization** | Chủ thể được làm hành động nào với tài nguyên hiện tại? | Backend/API, dịch vụ, policy enforcement point. |
| **Privileged access** | Khi nào được nâng quyền, trong bao lâu, có cần PAM/JIT không? | PAM, cloud IAM, công cụ quản trị và API nhạy cảm. |
| **Separation of Duties** | Các vai trò hoặc thao tác nào không được kết hợp? | Role assignment, phê duyệt, quy trình nghiệp vụ. |
| **Access review / recertification** | Ai phải xác nhận lại nhu cầu truy cập và khi nào? | IGA, application owner, quản lý nghiệp vụ. |
| **Exception / emergency** | Ai có quyền cho phép ngoại lệ; cần điều kiện bù trừ nào? | Quy trình phê duyệt ngoại lệ, break-glass, SOC. |
| **Audit / retention** | Cần lưu quyết định và bằng chứng gì, bao lâu và ai được xem? | IAM audit pipeline, SIEM, hệ thống quản trị hồ sơ. |

Mỗi lớp có thể được triển khai bằng công cụ riêng. Điều quan trọng là chỉ rõ **các quy tắc nào có hiệu lực với đối tượng nào** và không có khoảng trống giữa “đã phê duyệt”, “đã cấp quyền” và “đã thực thi”.

## 5. Kiến trúc ra quyết định: PAP, PDP, PIP, PEP

Đối với phân quyền lúc truy cập, kiến trúc policy thường tách bốn trách nhiệm:

- **Policy Administration Point (PAP):** quản lý nội dung, phiên bản, kiểm tra, phê duyệt và phát hành policy.
- **Policy Decision Point (PDP):** đánh giá một yêu cầu cùng dữ liệu cần thiết để trả về quyết định, ví dụ `Permit` hoặc `Deny`.
- **Policy Information Point (PIP):** cung cấp thuộc tính hoặc dữ kiện cần cho việc đánh giá, như bộ phận, tenant, trạng thái hợp đồng, phân loại tài nguyên.
- **Policy Enforcement Point (PEP):** chặn hoặc cho phép hành động thực tế dựa trên quyết định, thường nằm tại API, ứng dụng, gateway hoặc lớp dữ liệu.

~~~mermaid
flowchart LR
    HR["HRIS / VMS / service catalog<br/>Nguồn vòng đời"] --> ID["Registry / IGA<br/>Identity và JML"]
    ID --> PROV["Provisioning / SCIM / API<br/>Account + entitlement"]
    PROV --> APP["Ứng dụng / tài nguyên"]
    DEV["PAP<br/>Soạn - duyệt - phát hành policy"] --> PDP["PDP<br/>Đánh giá truy cập"]
    SRC["PIP<br/>Thuộc tính đáng tin cậy"] --> PDP
    ID --> SRC
    APP --> PEP["PEP<br/>Chặn / cho phép tại điểm truy cập"]
    PEP -->|Yêu cầu quyết định| PDP
    PDP -->|Permit / Deny + lý do| PEP
    PEP --> AUDIT["Audit / giám sát"]
    PDP --> AUDIT
    PROV --> AUDIT
~~~

Một sản phẩm có thể gộp PAP/PDP/PIP/PEP, nhưng trách nhiệm vẫn cần được xác định. **PEP phải đặt tại nơi có thể ngăn hành động**: chỉ ẩn nút “Phê duyệt” trên giao diện người dùng không đủ nếu người dùng vẫn gọi được API trực tiếp.

Đối với nghiệp vụ có rủi ro cao, PEP cần xác thực rằng quyết định PDP ứng với đúng **chủ thể, hành động, tài nguyên và ngữ cảnh yêu cầu**. Không được áp kết quả cho một resource khác hoặc dùng quyết định cũ quá thời gian an toàn.

## 6. Xác định quy tắc ưu tiên và kết quả đánh giá

Nếu có nhiều policy áp dụng cùng lúc, hệ thống cần **thuật toán kết hợp quyết định** rõ ràng. Không nên để thứ tự xuất hiện trong file hoặc thứ tự hoàn thành của các dịch vụ quyết định quyền truy cập một cách ngẫu nhiên.

### 6.1. Một cách thiết kế phổ biến

1. **Điều kiện chặn bắt buộc:** danh tính không hợp lệ, hết thời hạn, bị khóa bảo mật hoặc không thỏa yêu cầu xác thực cần thiết → từ chối.
2. **Điều kiện phủ định / xung đột:** thuộc diện SoD, tài nguyên bị hạn chế hoặc chính sách cấm đặc thù → từ chối.
3. **Điều kiện cho phép:** có entitlement/role hợp lệ, nằm trong scope và thỏa các điều kiện ABAC → có thể cho phép.
4. **Mặc định:** không tìm được căn cứ cho phép hợp lệ → từ chối (*default deny*).

Nhiều hệ thống biểu diễn kết quả nội bộ thành `Permit`, `Deny`, `NotApplicable` và `Indeterminate`. Khi triển khai, phải định nghĩa cách kết hợp chúng theo loại thao tác. Với hành động nhạy cảm, **không đánh đồng “không xác định được” với “cho phép”**.

| Tình huống | Kết quả dự kiến | Giải thích |
|---|---|---|
| Có role cho phép đọc, tenant khớp, danh tính hợp lệ | `Permit` | Các điều kiện cho phép đều được xác minh. |
| Có role cho phép nhưng `securityHold=true` | `Deny` | Hạn chế bảo mật có ưu tiên theo policy được phê duyệt. |
| Không có role hoặc entitlement cho hành động | `Deny` | Không có căn cứ cho phép; áp dụng default deny. |
| Có quyền phê duyệt nhưng giao dịch do chính mình tạo | `Deny` | Vi phạm SoD theo giao dịch. |
| Không xác minh được trạng thái nhà thầu khi truy cập tài nguyên nhạy cảm | Từ chối hoặc tạm dừng theo chính sách đã định | Thiếu dữ liệu quan trọng không được âm thầm cho phép. |
| Yêu cầu không nằm trong miền trách nhiệm của một policy con | `NotApplicable` ở policy đó | Bộ kết hợp tiếp tục xét những policy khác theo quy tắc được cấu hình. |
| Dịch vụ thuộc tính trả lỗi | `Indeterminate` ở tầng đánh giá | Cần quy tắc xử lý lỗi, ghi audit và lộ trình khắc phục. |

**Thứ tự ưu tiên không phải quy luật bất biến cho mọi nghiệp vụ.** Nếu một tổ chức cho phép break-glass trong một số sự cố, đó phải là đường quyết định riêng được phê duyệt với kiểm soát bù trừ, phạm vi, thời hạn và audit. Tránh tạo một rule “emergency=true → Permit mọi thứ” để vượt mọi kiểm soát.

### 6.2. Giới hạn giữa “không xác minh được” và “không còn hợp lệ”

Một sự kiện nghỉ việc hợp lệ có hiệu lực phải kích hoạt thu hồi. Nhưng **lỗi kết nối HRIS** không chứng minh rằng tất cả nhân viên đã nghỉ việc. Khi hệ thống nguồn không sẵn sàng, policy model nên phân biệt:

- Trạng thái hợp lệ đã biết gần nhất, độ mới và thời điểm hết hiệu lực của thông tin đó.
- Loại thao tác (đọc thông tin ít nhạy cảm hay thay đổi quyền quản trị production).
- Khả năng kiểm tra online, chế độ vận hành suy giảm và cơ chế ứng phó rủi ro.

Ví dụ, hệ thống có thể tạm chặn **cấp quyền mới** khi thiếu bằng chứng nhân sự, nhưng cần quy trình khả dụng riêng để duy trì một số tác vụ đã được đánh giá rủi ro. Đối với truy cập nhạy cảm, hết thời gian tin cậy của dữ liệu quan trọng thường phải dẫn tới từ chối/chờ xác minh.

## 7. Chọn cách biểu diễn chính sách: RBAC, ABAC và quan hệ

### 7.1. RBAC cho nhóm công việc ổn định

**RBAC (Role-Based Access Control)** quyết định quyền dựa trên role đã gán. Ví dụ role `SUPPORT_AGENT` cho phép xem hồ sơ yêu cầu hỗ trợ. Đây là mô hình phù hợp khi nhiều người có nhiệm vụ tương tự, dễ phê duyệt và rà soát theo vai trò.

Role là **đầu vào của policy**; việc có role chưa chắc đủ nếu yêu cầu còn phải thỏa trạng thái vòng đời, phạm vi tenant hoặc điều kiện giao dịch.

### 7.2. ABAC cho điều kiện thay đổi theo ngữ cảnh

**ABAC (Attribute-Based Access Control)** dùng thuộc tính của chủ thể, hành động, tài nguyên và môi trường. Ví dụ role `SUPPORT_AGENT` chỉ được đọc ticket khi `ticket.tenantId` khớp tenant được phân công và ticket chưa bị hạn chế theo chính sách dữ liệu.

ABAC giúp tránh tạo rất nhiều role chỉ khác tenant, dự án, hạn mức hoặc mức phân loại dữ liệu. Đổi lại, ABAC đòi hỏi nguồn thuộc tính đáng tin cậy, cách xử lý thiếu dữ liệu và kiểm thử tốt.

### 7.3. Quan hệ sở hữu và cấp quyền theo tài nguyên

Với các ứng dụng cộng tác, có thể cần quan hệ như “chủ dự án”, “thành viên nhóm”, “người được chủ tài nguyên chia sẻ”. Quan hệ này đôi khi được mô tả bằng **Relationship-Based Access Control (ReBAC)**. Nó bổ sung cho RBAC/ABAC khi quyết định truy cập phụ thuộc đồ thị quan hệ giữa người dùng, nhóm và tài nguyên.

Ví dụ một người được xem tài liệu vì là thành viên dự án A, dù không có role `DOCUMENT_GLOBAL_READER`. Quan hệ phải có nguồn và vòng đời rõ ràng; quyền chia sẻ không được tồn tại vô hạn sau khi người dùng rời dự án.

### 7.4. Mô hình kết hợp

Trong thực tế, có thể dùng:

~~~text
Role       : EXPENSE_APPROVER
Resource   : expense-123 (tenant VN, amount 12_000_000)
Attributes : approvalTenantId=VN, approvalLimit=20_000_000
Relation   : requesterIdentityId != approverIdentityId
Context    : lifecycle ACTIVE, securityHold=false

Decision   : Permit nếu tất cả điều kiện bắt buộc thỏa mãn
~~~

Role xác định **loại hành động**; thuộc tính và quan hệ xác định **tài nguyên và điều kiện**. Mô hình kết hợp phù hợp khi tổ chức vừa muốn role catalog dễ quản trị vừa cần giới hạn chi tiết tại ứng dụng.

## 8. Ví dụ policy model: ứng dụng phê duyệt chi phí

Giả sử doanh nghiệp có ứng dụng ExpenseHub phục vụ nhiều tenant. Các yêu cầu nghiệp vụ:

- Nhân viên được tạo phiếu chi cho tenant mình thuộc về.
- Người phê duyệt có role `EXPENSE_APPROVER` và hạn mức đủ lớn mới được duyệt.
- Người tạo phiếu không được tự duyệt phiếu của mình.
- Người thực hiện thanh toán không được đồng thời duyệt cùng giao dịch.
- Truy cập bị chặn nếu danh tính hết hiệu lực hoặc bị khóa bảo mật.
- Mọi hành động phê duyệt phải có log quyết định và thực thi.

### 8.1. Ma trận chính sách

| Hành động | Chủ thể/role | Tài nguyên | Điều kiện bắt buộc | Kết quả khi không đạt |
|---|---|---|---|---|
| Tạo phiếu | `EXPENSE_REQUESTER` | Phiếu mới | Đúng tenant được phép, danh tính hợp lệ | Từ chối tạo. |
| Xem phiếu | `EXPENSE_REQUESTER` | Phiếu của mình | Chủ thể trùng người tạo, đúng tenant | Từ chối xem. |
| Xem phiếu | `EXPENSE_AUDITOR` | Phiếu trong scope kiểm toán | Có assignment kiểm toán hợp lệ, chỉ đọc | Từ chối hoặc giới hạn theo phạm vi. |
| Phê duyệt | `EXPENSE_APPROVER` | Phiếu chờ duyệt | Đúng tenant, đúng hạn mức, không phải người tạo, không xung đột nhiệm vụ | Từ chối phê duyệt. |
| Thanh toán | `PAYMENT_EXECUTOR` | Phiếu đã duyệt | Đúng scope thanh toán và không phải người phê duyệt giao dịch nếu policy cấm | Từ chối thanh toán. |
| Cấu hình quyền | `EXPENSE_SECURITY_ADMIN` | Chính sách ứng dụng | Phê duyệt đặc quyền, xác thực mạnh, thời hạn phù hợp | Từ chối thay đổi. |

### 8.2. Mẫu policy có cấu trúc

~~~yaml
# Schema minh họa để thảo luận thiết kế; không chạy trực tiếp trên sản phẩm IAM.
policySet:
  id: expense-authorization
  version: 4
  ownerTeam: FinanceSecurity
  lifecycleStatus: APPROVED
  effectiveFrom: "2026-10-01T00:00:00Z"
  combiningRule: DENY_OVERRIDES
  defaultDecision: DENY
  mandatoryConditions:
    - subject.lifecycleStatus == ACTIVE
    - subject.securityHold == false
    - subject.isAuthenticated == true
  rules:
    - id: approve-expense
      effect: PERMIT
      actions: [expense:approve]
      requiredRole: EXPENSE_APPROVER
      conditions:
        - subject.approvalTenantId == resource.tenantId
        - resource.amount <= subject.approvalLimit
        - resource.requesterIdentityId != subject.identityId
        - resource.status == PENDING_APPROVAL
        - transaction.sodCheckPassed == true
      auditLevel: HIGH
    - id: deny-security-hold
      effect: DENY
      when: subject.securityHold == true
      auditLevel: HIGH
~~~

**Cảnh báo về ngữ nghĩa:** các chuỗi biểu thức chỉ minh họa ý tưởng. Triển khai thực tế cần ngôn ngữ policy, trình biên dịch/engine có kiểu dữ liệu và định nghĩa toán tử chặt chẽ. Phải xác định trường thiếu/null, cách so sánh số tiền/đơn vị tiền, đồng hồ, biểu thức logic và precedence. Đừng tin tưởng vào việc phân tích những chuỗi này bằng `eval`.

### 8.3. Giả mã cho một quyết định runtime

~~~text
authorize(subject, action, resource, context):
    facts = loadTrustedAttributes(subject, resource, context)

    if facts.missingCriticalData or facts.isStaleFor(action):
        return Deny("cannot-verify-required-facts")
    if not facts.isAuthenticated or facts.securityHold:
        return Deny("security-gate")
    if not facts.lifecycleEligibleAt(context.now):
        return Deny("lifecycle-ineligible")

    matches = findApplicablePolicies(action, resource, context)
    if violatesMandatoryRestriction(matches, facts):
        return Deny("mandatory-restriction")

    permits = evaluatePermitRules(matches, facts)
    if not permits:
        return Deny("no-applicable-permit")

    if not satisfiesTransactionSoD(subject, action, resource):
        return Deny("sod-violation")

    return Permit("policy-conditions-satisfied")
~~~

Giả mã rút gọn để giải thích đường ra quyết định, chưa thể hiện toàn bộ quy tắc kết hợp, việc xác thực nguồn dữ liệu, cache, nghĩa vụ hậu kiểm hoặc xử lý lỗi. Với các thao tác thay đổi dữ liệu, điều kiện như trạng thái phiếu và người phê duyệt cần được **kiểm tra nguyên tử cùng thao tác ghi** khi có nguy cơ tranh chấp đồng thời (*time-of-check to time-of-use*), tránh việc phiếu bị thay đổi sau khi cấp phép nhưng trước khi cập nhật.

### 8.4. Kết quả đánh giá và nghĩa vụ thực thi

Một phản hồi quyết định có thể chứa:

~~~json
{
  "requestId": "req-c3f8",
  "decision": "PERMIT",
  "policySetId": "expense-authorization",
  "policyVersion": 4,
  "reasonCode": "policy-conditions-satisfied",
  "obligations": [
    "record-expense-approval-audit",
    "verify-current-transaction-state"
  ]
}
~~~

`obligations` là hành động hoặc điều kiện mà PEP **phải thực thi** trước/khi cho phép theo thiết kế; nếu không thể thực hiện nghĩa vụ bắt buộc thì không được âm thầm tiếp tục như không có điều kiện. Dữ liệu phản hồi gửi cho client cần tối thiểu, tránh lộ điều kiện nội bộ nhạy cảm hoặc thông tin cá nhân không cần thiết.

## 9. Policy model gắn với Joiner–Mover–Leaver

### Joiner — đủ điều kiện nhưng chưa chắc được cấp mọi quyền

Khi HRIS hoặc hệ thống quản lý hợp đồng xác nhận một người bắt đầu quan hệ với tổ chức, IAM kiểm tra:

1. Danh tính đã được xác minh và có khóa nguồn ổn định chưa?
2. Thời điểm bắt đầu có hiệu lực chưa, có chặn bảo mật hoặc kiểm tra bắt buộc nào chưa hoàn tất không?
3. Account nào thuộc scope được tạo hoặc kích hoạt?
4. Role cơ sở nào được cấp theo chính sách, role nào cần phê duyệt riêng?
5. Hành động provisioning đã thực thi ở IdP/ứng dụng chưa; đã đọc lại kết quả chưa?

Ví dụ hồ sơ nhân sự được tạo ngày 01/06 nhưng bắt đầu công việc ngày 15/06. Policy có thể cho phép chuẩn bị account sớm nhưng chỉ kích hoạt đăng nhập hoặc entitlement nhạy cảm đúng thời điểm đã phê duyệt. Cần phân biệt **ngày hồ sơ được nhập** và **ngày quyền có hiệu lực**.

### Mover — tính lại quyền theo trạng thái mới

Khi phòng ban, dự án, vai trò công việc, người quản lý hoặc phạm vi tenant thay đổi, IAM tính lại **trạng thái quyền mong muốn** từ các policy đang hiệu lực:

~~~text
desiredEntitlements = evaluateAssignmentPolicies(newIdentityFacts)
actualEntitlements  = observeEntitlementsAtTargets(identity)

toGrant  = desiredEntitlements - actualEntitlements
toRevoke = actualEntitlements - desiredEntitlements

checkSoDAndApproval(toGrant, actualEntitlements, toRevoke)
executeRiskAwareRevokeAndGrantPlan()
reconcileTargetsUntilConfirmedOrEscalated()
~~~

Phép so sánh mang tính khái niệm: khi một entitlement được nhiều role hợp lệ cùng cấp, không được gỡ nó nếu vẫn còn một nguồn cấp quyền hợp lệ khác. Phải xét **nguồn gốc cấp quyền, scope, thời hạn và quyền trực tiếp**.

Ví dụ nhân viên chuyển từ nhóm phê duyệt chi sang nhóm thanh toán. Nếu SoD cấm đồng thời hai quyền, quy trình Mover cần thu hồi và xác nhận quyền phê duyệt trước khi cấp quyền thanh toán, hoặc áp một cách xử lý nguyên tử/tạm khóa an toàn tương đương. Chỉ thêm role mới rồi chờ lần đồng bộ tiếp theo xóa role cũ có thể tạo khoảng trống kiểm soát.

### Leaver — xác định điều kiện chấm dứt toàn bộ truy cập

Khi nguồn có thẩm quyền phát sự kiện nghỉ việc/hết hợp đồng với thời điểm hiệu lực, policy cần quyết định:

- Chặn đăng nhập và phiên còn hiệu lực bằng những kênh khả dụng.
- Thu hồi các assignment và entitlement tại **mọi account thuộc scope**, kể cả local account và quyền được cấp trực tiếp.
- Thu hồi hoặc luân chuyển các credential gắn với cá nhân như token, API key, SSH key khi cần.
- Giữ bản ghi kiểm toán hoặc dữ liệu theo thời hạn pháp lý, tách biệt với quyền truy cập đã vô hiệu hóa.
- Theo dõi lỗi connector và tiếp tục đối soát cho đến khi quyền ở đích được xác nhận đã thu hồi.

**“Đã gửi lệnh SCIM disable” chưa đồng nghĩa “Leaver hoàn tất”.** Cần bằng chứng từ ứng dụng đích hoặc quy trình thao tác có xác nhận. Một account có thể hết quyền đăng nhập qua SSO nhưng vẫn có token cũ, quyền direct hoặc lối đăng nhập local.

### Danh tính phi con người có vòng đời riêng

Service account và workload identity không nên phụ thuộc hoàn toàn vào `employeeId` của kỹ sư từng tạo chúng. Policy model cần gắn chúng với `serviceId`/`workloadId`, môi trường, mục đích, chủ sở hữu dịch vụ và lịch rà soát.

Khi owner là nhân viên nghỉ việc, policy có thể kích hoạt **chuyển giao ownership, rà soát quyền và luân chuyển credential**; quyết định thu hồi toàn bộ account còn phụ thuộc việc workload đã ngừng hoạt động hay chưa và đánh giá rủi ro. Khi dịch vụ ngừng triển khai, sự kiện từ hệ thống quản lý workload mới là căn cứ trực tiếp cho thu hồi danh tính máy.

## 10. Chất lượng thuộc tính và độ trễ của IdP/SSO

Policy chỉ đáng tin cậy khi dữ liệu dùng để đánh giá chính xác và đủ mới.

| Thuộc tính | Nguồn/owner thường gặp | Rủi ro nếu sai hoặc cũ |
|---|---|---|
| `employmentStatus`, ngày hiệu lực | HRIS | Người đã nghỉ có thể tiếp tục truy cập hoặc người mới bị chặn nhầm. |
| `contractEndAt` | Hệ thống hợp đồng/VMS | Nhà thầu hết hạn vẫn giữ quyền. |
| `departmentId`, `managerId` | HRIS hoặc dữ liệu tổ chức có thẩm quyền | Gán nhầm role, người phê duyệt sai. |
| `securityHold` | SOC/IdP theo quy trình bảo mật | Lệnh khóa khẩn cấp bị bỏ qua. |
| `assignedTenantIds` | Hệ thống phân công/owner nghiệp vụ | Rò rỉ dữ liệu giữa các tenant. |
| `resource.classification` | Data owner/data catalog | Cho phép truy cập vượt mức nhạy cảm. |
| `workloadId`, `serviceOwnerId` | Service catalog/cloud inventory | Không xác định được chủ thể chịu trách nhiệm. |
| `mfaSatisfied` hoặc mức xác thực | IdP/session infrastructure | Truy cập nhạy cảm được phép khi chưa đủ xác thực. |

**IdP phát token không có nghĩa các claim còn mới đến hết phiên.** Nếu quyền thay đổi giữa chừng, claim role hoặc nhóm trong token đã phát hành có thể chưa phản ánh quyết định mới. Với tài nguyên nhạy cảm, cần lựa chọn một hoặc nhiều cơ chế phù hợp như token thời hạn ngắn, đánh giá policy phía backend, kiểm tra trạng thái online, thu hồi phiên/token được hỗ trợ và tín hiệu vô hiệu hóa khẩn cấp.

Không nên dựa hoàn toàn vào claim client có thể tự sửa. PEP phải xác thực token và các thuộc tính đáng tin cậy; tài nguyên thực tế được truy cập phải được xác minh từ server, nhất là tenant ID hoặc owner ID nằm trong URL.

### Chính sách thiếu dữ liệu và mất kết nối

Với từng thuộc tính quan trọng, ghi rõ:

1. Nguồn có thẩm quyền và giao diện lấy dữ liệu.
2. Định dạng, trường bắt buộc, version/thời điểm hiệu lực.
3. Thời gian dữ liệu còn được coi là đáng tin và điều kiện làm mới.
4. Hành động khi trường không có, không khớp hoặc nguồn không sẵn sàng.
5. Người nhận cảnh báo, cách khôi phục và sự kiện cần audit.

Việc tiếp tục sử dụng cache là **quyết định rủi ro** phải được viết thành policy, không mặc định áp dụng cho mọi hành động. Với việc cấp quyền cao hoặc thao tác dữ liệu nhạy cảm, thường cần xác minh lại khi thuộc tính cốt lõi quá hạn.

## 11. SoD, least privilege, JIT và truy cập có thời hạn

### Separation of Duties

**Separation of Duties (SoD)** hạn chế một cá nhân tự thực hiện các bước có xung đột lợi ích:

- **Static SoD:** không cho giữ đồng thời hai role xung đột, ví dụ người duyệt chi và người thực hiện thanh toán nếu quy định tổ chức cấm.
- **Dynamic SoD:** kiểm tra ở giao dịch cụ thể, ví dụ người tạo phiếu không được tự phê duyệt phiếu đó, kể cả khi có role người phê duyệt hợp lệ.
- **Approval separation:** người xin quyền đặc biệt không tự phê duyệt yêu cầu của mình.

SoD phải xét **quyền hiệu lực** từ mọi đường: role kế thừa, nhóm động, quyền gán trực tiếp và ngoại lệ. Chỉ so sánh tên role có thể bỏ sót entitlement gây xung đột.

### Least privilege và role có phạm vi

Nguyên tắc **least privilege** yêu cầu chỉ cấp quyền cần thiết, trong tài nguyên cần thiết và thời gian cần thiết. Ví dụ, vai trò đọc báo cáo tenant VN không nên cho phép đọc tenant khác hoặc quyền quản trị hệ thống báo cáo.

Nếu tổ chức sử dụng quyền truy cập đặc quyền, policy nên xác định rõ:

- Điều kiện đủ tư cách và người phê duyệt độc lập.
- MFA hoặc mức xác thực mạnh hơn khi cần.
- Phạm vi tài nguyên, hành động và khoảng thời gian cho phép.
- Cơ chế **Privileged Access Management (PAM)**, nâng quyền **Just-in-Time (JIT)** hoặc **Just-Enough-Access** khi nền tảng hỗ trợ.
- Ghi nhật ký và kiểm tra quyền đã thu hồi khi thời hạn kết thúc.

Một phiên quản trị hết hạn phải dẫn tới **kết thúc quyền hiệu lực** tại hệ thống thực thi. Chỉ ghi ngày hết hạn trong catalog nhưng để quyền cloud tồn tại vô hạn là thiết kế chưa hoàn chỉnh.

## 12. Chính sách ngoại lệ và break-glass

Trong vận hành có thể phát sinh ngoại lệ, ví dụ ứng dụng cũ không hỗ trợ MFA hoặc khi IdP gặp sự cố cần sử dụng **break-glass account** để khôi phục dịch vụ. Policy model phải quy định:

| Điều kiện | Yêu cầu quản trị |
|---|---|
| Lý do ngoại lệ | Ghi rõ nhu cầu nghiệp vụ, sự cố hoặc hạn chế kỹ thuật. |
| Chủ thể và phạm vi | Account/người được phép, hệ thống, tài nguyên, quyền và giới hạn thời gian. |
| Quyền phê duyệt | Owner và bộ phận chịu trách nhiệm rủi ro; không tự phê duyệt tùy tiện. |
| Biện pháp bù trừ | PAM, bảo vệ credential, giám sát phiên, giới hạn mạng hoặc review bổ sung. |
| Thời hạn và kết thúc | Ngày hết hiệu lực, tiêu chí gia hạn, xác nhận thu hồi sau khi kết thúc. |
| Kiểm toán | Ai kích hoạt, lúc nào, thao tác gì, kết quả, điều tra sau sự kiện. |

**Break-glass** không phải lệnh cho phép toàn quyền vĩnh viễn. Account khẩn cấp có thể cần tồn tại độc lập với hệ thống xác thực đang gặp sự cố, nhưng phải được bảo vệ và giám sát nghiêm ngặt, chỉ hoạt động trong kịch bản đã phê duyệt. Cần diễn tập khả năng khôi phục, rà soát người giữ quyền và luân chuyển credential sau sử dụng theo chính sách.

Khi một ngoại lệ hết hạn, việc thu hồi quyền phải được xác nhận ở đích. **Không tự động gia hạn** chỉ vì không nhận được phản hồi từ owner.

## 13. Quản trị vòng đời của chính policy

Policy cũng phải trải qua một vòng đời được kiểm soát, vì một thay đổi có thể mở rộng hoặc thu hẹp quyền của hàng nghìn danh tính cùng lúc.

~~~mermaid
flowchart LR
    D["Draft<br/>Mục đích, owner, điều kiện"] --> R["Review<br/>Bảo mật + nghiệp vụ"]
    R --> T["Test<br/>Positive / negative / SoD"]
    T --> A["Approve<br/>Có bằng chứng"]
    A --> P["Publish<br/>Version + rollout"]
    P --> M["Monitor<br/>Quyết định + drift"]
    M --> C["Change / retire<br/>Đánh giá tác động"]
    C --> D
~~~

Mỗi policy quan trọng cần một hồ sơ gồm:

| Thuộc tính quản trị | Mục đích |
|---|---|
| `policyId`, `version` | Truy xuất đúng phiên bản đã quyết định một lần truy cập. |
| `purpose` và `owner` | Ai chịu trách nhiệm nội dung và mục tiêu bảo vệ. |
| `target`, `scope` | Đối tượng, ứng dụng, tenant, môi trường, action/resource được áp. |
| `effect`, `combiningRule` | Cách đánh giá, kết hợp Permit/Deny, mặc định. |
| `sourceContracts` | Nguồn thuộc tính, độ tin cậy, độ mới, xử lý lỗi. |
| `approvals`, `SoD` | Điều kiện phê duyệt và kiểm tra xung đột. |
| `effectiveFrom`, `effectiveUntil` | Thời điểm hiệu lực và kết thúc. |
| `tests`, `rolloutPlan`, `rollbackPlan` | Bằng chứng kiểm tra, triển khai và phục hồi. |
| `reviewAt`, `lifecycleStatus` | Chu kỳ tái đánh giá; draft, active, deprecated, retired. |

### Thay đổi policy phải kiểm tra tác động

Ví dụ thêm quyền `report:export` vào role `FINANCE_ANALYST` không chỉ tác động người yêu cầu mới: **toàn bộ người đang có role** có thể nhận quyền xuất dữ liệu. Trước khi publish cần xác định:

1. Những người, workload và tài nguyên nào sẽ được phép thêm hoặc bị chặn?
2. Có vi phạm SoD, giới hạn tenant hoặc chính sách dữ liệu không?
3. Ứng dụng và connector nào cần cập nhật entitlement thực tế?
4. Có cần phê duyệt lại, thông báo hoặc hướng dẫn sử dụng không?
5. Nếu rollout sai, rollback policy có đủ hay phải thu hồi entitlement đã provision ở đích?

Trong hệ thống lớn, có thể chạy **dry-run/simulation**, so sánh quyết định policy mới với bản đang chạy, triển khai theo nhóm nhỏ và giám sát số lần từ chối/cho phép thay đổi bất thường. Các kết quả kiểm tra chỉ có ý nghĩa khi tập yêu cầu mẫu đại diện cho môi trường thật, kể cả trường hợp âm tính.

## 14. Kiểm thử policy model bằng decision table

Chính sách cần có **kiểm thử mong đợi** trước khi đưa vào sản xuất. Mỗi test phải mô tả dữ kiện đầu vào, quyết định dự kiến và, nếu có, hành động provisioning cần xảy ra.

Ví dụ cho hệ thống phê duyệt chi:

| Ca kiểm thử | Dữ kiện chính | Kết quả mong đợi |
|---|---|---|
| 1. Phê duyệt hợp lệ | Role đúng, tenant khớp, hạn mức đủ, người tạo khác, danh tính active | `Permit` và ghi audit. |
| 2. Chênh tenant | Có role nhưng resource ở tenant khác | `Deny`, không lộ nội dung. |
| 3. Không đủ hạn mức | `expense.amount > approvalLimit` | `Deny`. |
| 4. Tự phê duyệt | `requesterIdentityId == identityId` | `Deny` theo SoD. |
| 5. Người dùng bị khóa | `securityHold=true` | `Deny` dù role vẫn tồn tại. |
| 6. Nhà thầu hết hạn | `now >= contractEndAt` | Không đủ điều kiện truy cập; kích hoạt thu hồi theo JML. |
| 7. Thiếu dữ liệu cốt lõi | Không xác minh được tenant hoặc trạng thái vòng đời | Từ chối/chờ xác minh theo chính sách an toàn. |
| 8. Claim role đã lỗi thời | Token còn role nhưng assignment đã bị thu hồi | Không cho phép trên hệ thống nhạy cảm khi nguồn quyết định hiện hành báo đã thu hồi. |
| 9. Role chồng lấp | Hai role cùng cấp một entitlement, chỉ một role bị gỡ | Giữ quyền nếu nguồn cấp hợp lệ khác vẫn còn; đồng thời kiểm tra SoD. |
| 10. Quyền trực tiếp ngoài role | App còn permission nhưng role catalog không còn căn cứ | Đối soát phát hiện drift và xử lý thu hồi/ngoại lệ. |
| 11. Hết phiên nâng quyền | JIT expiry đã qua | Chặn truy cập quản trị và xác minh role đích đã hết hiệu lực. |
| 12. Mất kết nối thuộc tính | PIP lỗi giữa lúc phê duyệt | Không tự cho phép; trả kết quả lỗi/từ chối theo chính sách, có cảnh báo. |

### Kiểm thử cả điểm thực thi

Không chỉ chạy unit test cho biểu thức policy. Cần kiểm tra end-to-end:

- Backend/API có thật sự chặn một yêu cầu bị `Deny`, kể cả khi gửi URL hoặc resource ID trực tiếp?
- Application có dùng đúng tenant và resource thật thay vì thuộc tính tùy ý từ request không?
- Việc thu hồi vai trò qua SCIM/API có được kiểm tra bằng trạng thái thực tế tại đích?
- Kiểm tra có bắt được permission được gán trực tiếp hoặc group lồng nhau không?
- Ứng dụng có ghi và theo dõi được sự cố không thực hiện nghĩa vụ bắt buộc của PEP?
- Thao tác nhạy cảm có xử lý race condition giữa quyết định Permit và cập nhật giao dịch không?

Một policy trả về `Deny` đúng nhưng API vẫn thực hiện thay đổi là **lỗi thực thi truy cập**, không phải một hệ thống IAM an toàn.

## 15. Audit và giám sát chính sách

Để điều tra sự cố hoặc rà soát quyền, hệ thống cần trả lời được **ai yêu cầu gì, trên tài nguyên nào, thời điểm nào, quyết định theo policy nào và hành động thực tế ra sao**.

Một sự kiện audit nên có ít nhất:

- Request/correlation ID; thời điểm yêu cầu, quyết định và thực thi.
- Identity hoặc workload ID ổn định; loại danh tính, tài khoản/tenant liên quan.
- Action và resource ID; phân loại độ nhạy nếu cần.
- Policy ID, version, decision và reason code; nguồn/phiên bản các thuộc tính cốt lõi.
- Kết quả PEP hoặc provisioning: thành công, bị từ chối, đang chờ, lỗi hay không đối soát được.
- Phê duyệt, ngoại lệ và người chịu trách nhiệm nếu quyết định liên quan nâng quyền.

Nhật ký không nên chứa password, bearer token, bí mật hoặc toàn bộ dữ liệu cá nhân khi không cần thiết. Chỉ lưu các thuộc tính tối thiểu đủ để giải thích quyết định, bảo vệ log khỏi bị sửa trái phép và quy định thời gian lưu theo yêu cầu của tổ chức.

### Chỉ số giúp phát hiện policy model có vấn đề

| Chỉ số | Điều cần quan sát |
|---|---|
| **Authorization decision drift** | Tỷ lệ quyết định khác giữa phiên bản policy mới và đang chạy trên cùng tập yêu cầu. |
| **Deny/Permit anomaly** | Bất thường về tỷ lệ cho phép/từ chối theo ứng dụng, role, tenant, tài nguyên. |
| **Policy coverage** | Hành động/tài nguyên nhạy cảm nào chưa có PEP và policy có owner. |
| **Attribute freshness/error rate** | Tần suất thuộc tính nguồn quá hạn, thiếu, lỗi hoặc không khớp. |
| **SoD violation rate** | Xung đột role/permission hoặc giao dịch bị chặn/được xử lý ngoại lệ. |
| **Provisioning reconciliation drift** | Sai lệch giữa entitlement mong muốn và quyền thực tế. |
| **Leaver revocation latency** | Thời gian từ mốc nghỉ việc có hiệu lực đến khi quyền tại đích được xác nhận đã thu hồi. |
| **Exception aging** | Số ngoại lệ quá hạn hoặc không còn owner, đặc biệt đặc quyền. |
| **Policy review compliance** | Policy nhạy cảm được rà soát đúng hạn và có bằng chứng chấp thuận. |

Chỉ số cần được phân tích theo mức rủi ro. Tỷ lệ từ chối cao có thể là dấu hiệu tấn công, nhưng cũng có thể phản ánh policy hoặc dữ liệu thuộc tính triển khai sai; cần đối chiếu log và bối cảnh thay vì kết luận ngay.

## 16. Quy trình xác định policy model cho dự án IAM

Một nhóm triển khai có thể đi theo lộ trình sau:

1. **Thống nhất mục tiêu kiểm soát:** liệt kê hành động cần bảo vệ, dữ liệu nhạy cảm, rủi ro, yêu cầu SoD và nghĩa vụ kiểm toán.
2. **Xác định ranh giới:** loại danh tính, account scope, hệ thống/tenant và tài nguyên nào thuộc giai đoạn đầu.
3. **Xác nhận nguồn dữ liệu:** owner, độ tin cậy, độ mới, thời điểm hiệu lực cho thuộc tính nhân sự, nhà thầu, workload, tenant, resource và security hold.
4. **Thiết kế các policy family:** eligibility, assignment, runtime authorization, privileged, exception, review và audit. Chỉ rõ policy nào chạy khi JML, policy nào chạy tại API.
5. **Chốt ngữ nghĩa ra quyết định:** Permit/Deny, mặc định, quy tắc kết hợp, xử lý missing/error, thứ tự SoD và ràng buộc bắt buộc.
6. **Chọn nơi thực thi:** PAP/PDP/PIP/PEP, IdP/SSO, provisioning qua SCIM/API, PAM và điểm kiểm tra nội bộ của ứng dụng.
7. **Thử và mô phỏng:** decision table, negative tests, sự kiện JML, thiếu dữ liệu, quyền cấp trực tiếp, nhiều tenant, lỗi connector và quyền đã hết hạn.
8. **Phát hành theo phiên bản:** owner duyệt, rollout có kiểm soát, theo dõi khác biệt và có cơ chế rollback/thu hồi entitlement phát sinh.
9. **Vận hành liên tục:** đo độ trễ thu hồi, drift, SoD, ngoại lệ, trạng thái PEP, review policy và kiểm soát khi thay đổi hệ thống.

**Đầu ra tối thiểu:** policy inventory/catalog; bảng authority của thuộc tính; ma trận subject/action/resource/context; quy tắc combining/default; mapping policy–enforcement point; bộ test quyết định; hồ sơ owner/phê duyệt; phương án audit và ứng phó khi hệ thống không sẵn sàng.

## 17. Những sai lầm thường gặp

- **Cho rằng đã có role là đã có policy hoàn chỉnh.** Role không giải quyết hết trạng thái vòng đời, tenant, thời gian, SoD và hạn chế bảo mật.
- **Để mặc định allow khi không có rule phù hợp.** Một hành động nhạy cảm có thể được phép chỉ vì lập trình viên quên thêm policy.
- **Tùy ý chọn rule nào chạy trước.** Khi nhiều rule xung đột, hành vi có thể thay đổi theo thứ tự triển khai hoặc câu lệnh.
- **Dùng thuộc tính do client tự gửi làm căn cứ phân quyền.** Người dùng có thể sửa tenant ID hoặc role trong payload nếu server không xác minh.
- **Chỉ kiểm tra phân quyền ở giao diện.** API hoặc đường truy cập trực tiếp vẫn có thể thực thi hành động.
- **Không kiểm soát độ mới của claim và cache.** Role đã bị thu hồi nhưng token/phiên cũ vẫn được coi là hợp lệ.
- **Chỉ kiểm tra SoD khi gán role.** Bỏ sót xung đột xảy ra trên một giao dịch cụ thể hoặc do quyền trực tiếp.
- **Không gắn owner và version cho policy.** Không biết ai chấp thuận quy tắc hoặc bản nào đã quyết định một sự kiện.
- **Trộn quy trình provisioning với kiểm tra runtime.** Gán nhóm thành công không có nghĩa mọi tài nguyên đã được bảo vệ đúng.
- **Đánh dấu Leaver thành công khi đã gửi yêu cầu.** Quyền local, token, đặc quyền và tài khoản phụ có thể tồn tại.
- **Cho service account kế thừa quyền của người tạo.** Khi người tạo chuyển việc, vòng đời workload trở nên mơ hồ.
- **Ngoại lệ không có hạn hoặc audit.** Truy cập tạm thời trở thành quyền tồn dư lâu dài.

## 18. Bài tập thực hành: xây dựng policy model cho tổ chức đa tenant

Một doanh nghiệp có nhân viên, nhà thầu, tài khoản dịch vụ và ứng dụng quản lý chi phí. Nhân viên phòng tài chính có thể xem báo cáo; trưởng bộ phận được phê duyệt khoản chi trong hạn mức; nhà thầu chỉ được truy cập dự án được phân công đến ngày hết hợp đồng. Hệ thống có hai tenant VN và SG. Một role quản trị production chỉ được nâng quyền tạm thời khi có sự cố được phê duyệt.

Hãy thiết kế một policy model và trả lời:

1. Với các action `report:read`, `expense:approve` và `cloud:admin`, subject, resource, environment và thuộc tính nguồn nào bắt buộc?
2. Viết **ba policy Permit** và **hai policy Deny** có scope, thời hạn và điều kiện cụ thể. Khi nhiều policy cùng áp dụng, kết quả nào ưu tiên?
3. Áp ABAC để ngăn đọc dữ liệu tenant SG khi người dùng chỉ có assignment tenant VN.
4. Xác định cả **static SoD** (role xung đột) và **dynamic SoD** (tự duyệt phiếu) trong quy trình chi phí.
5. Vạch quy trình Joiner cho nhà thầu bắt đầu sau bảy ngày, Mover của nhân viên từ Finance sang Engineering, và Leaver khẩn cấp của một quản trị viên.
6. Thiết kế cơ chế xử lý khi PIP không trả được trạng thái hợp đồng hoặc khi IdP token mang claim role cũ.
7. Chỉ rõ PAP, PDP, PIP, PEP, ứng dụng đích, điểm provisioning và dữ liệu audit cần lưu.
8. Đề xuất ít nhất tám test, gồm cả ca hợp lệ, sai tenant, thiếu dữ kiện, SoD, hết hạn và lỗi thu hồi quyền ở đích.

**Gợi ý đầu ra:** một bảng policy gồm `policyId`, `subject`, `action`, `resourceScope`, `conditions`, `effect`, `owner`, `effectiveUntil` và `enforcementPoint`; thêm một decision table và sơ đồ luồng JML → provisioning → runtime authorization → reconciliation.

### Tiêu chí nghiệm thu

Một policy model đủ rõ để nhóm kỹ thuật bắt đầu triển khai cần chứng minh được:

- Có định nghĩa và nguồn đáng tin cậy cho các thuộc tính quyết định.
- Có điều kiện Permit, Deny, default và cách xử lý xung đột/thiếu dữ liệu.
- Quyền theo role kết hợp đúng với giới hạn tài nguyên, tenant, thời gian và SoD.
- Điểm thực thi có khả năng chặn hành động thực tế, kể cả truy cập API trực tiếp.
- JML có các sự kiện, thời điểm hiệu lực và quy trình thu hồi quyền được đọc lại từ đích.
- Đặc quyền, tài khoản dịch vụ và break-glass có chính sách riêng, owner và audit phù hợp.
- Mọi thay đổi policy có version, kiểm thử, phê duyệt và kế hoạch khôi phục.
- Nhật ký và chỉ số có thể giải thích quyết định, phát hiện sai lệch và đo quyền tồn dư.

**Policy model tạo ra ngôn ngữ quyết định chung cho IAM:** nguồn danh tính cung cấp sự thật, role model mô tả trách nhiệm, account scope xác định nơi quản lý, còn policy quyết định khi nào một hành động được phép và hệ thống phải thực thi/kiểm chứng điều gì. Khi những thành phần này nhất quán, tổ chức mới có thể quản trị quyền truy cập xuyên suốt Joiner–Mover–Leaver một cách giải thích được và kiểm toán được.
