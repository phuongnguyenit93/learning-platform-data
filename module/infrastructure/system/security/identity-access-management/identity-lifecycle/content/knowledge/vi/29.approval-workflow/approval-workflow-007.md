# Separation of duties trong Approval workflow: phân tách trách nhiệm khi phê duyệt quyền IAM

Một nhân viên tự gửi yêu cầu được cấp quyền quản trị production, rồi sử dụng chính tài khoản quản lý của mình để duyệt yêu cầu. Một quản trị viên khác có thể tạo tài khoản nhân viên giả, phê duyệt quyền và tự cấp quyền cho tài khoản đó. Trong hệ thống thanh toán, một người vừa tạo nhà cung cấp vừa phê duyệt giao dịch thanh toán cho nhà cung cấp ấy. Những tình huống này có điểm chung: **người hoặc nhóm lợi ích có thể kiểm soát toàn bộ những bước vốn cần kiểm tra lẫn nhau**.

**Separation of duties (SoD) – phân tách nhiệm vụ/quyền hạn** là nguyên tắc bảo mật và kiểm soát nội bộ nhằm tránh một chủ thể có thể tự mình thực hiện, phê duyệt, hoàn tất và che giấu toàn bộ một hoạt động nhạy cảm. Trong **approval workflow** của hệ thống **Identity and Access Management (IAM)**, SoD được dùng để ngăn **tự phê duyệt, cấp quyền vượt thẩm quyền, tổ hợp quyền xung đột và việc bỏ qua kiểm tra độc lập**.

Bài học thuộc chương **Approval workflow**, chủ đề **Separation of duties**, trong mô-đun `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Mô-đun tập trung quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản và cấp quyền, thay đổi vai trò, rà soát và thu hồi quyền; đồng thời liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**.

Sau bài học, người học có thể:

- Phân biệt **SoD theo quy trình**, **Static SoD (SSD)**, **Dynamic SoD (DSD)** và cơ chế **four-eyes/maker-checker**.
- Xác định đúng các vai trò **requester, beneficiary, sponsor, manager, resource owner, approver, executor và auditor**, kể cả khi một người có nhiều tài khoản.
- Mô hình hóa **ma trận quyền xung đột**, đánh giá **effective entitlements** và phát hiện self-approval hoặc liên kết lợi ích.
- Thiết kế quy trình phê duyệt nhiều bước, **ủy quyền có kiểm soát, tái đánh giá ở thời điểm duyệt và kiểm soát hành động thực thi**.
- Áp dụng SoD khi **Joiner, Mover, Leaver**, khi thay manager, dùng **PAM/JIT**, break-glass hoặc tài khoản dịch vụ.
- Truy vết quyết định qua **HRIS/IGA/IdP/SSO/SCIM/ứng dụng**, theo dõi lỗi cấp phát và xác minh quyền thực tế.

## 1. SoD giải quyết vấn đề gì trong phê duyệt IAM?

Một approval workflow phổ biến có thể gồm:

1. Người dùng hoặc hệ thống tạo **yêu cầu truy cập**.
2. Người quản lý xác nhận **nhu cầu nghiệp vụ**.
3. Chủ sở hữu ứng dụng/dữ liệu xác nhận **phạm vi quyền**.
4. IAM/Security kiểm **điều kiện, SoD và rủi ro**.
5. Connector thực hiện **grant/revoke** tại hệ thống đích.
6. Hệ thống đọc lại quyền và lưu **audit evidence**.

Nếu một người có thể kiểm soát tất cả bước, tổ chức khó bảo đảm yêu cầu độc lập được đánh giá. SoD đặt ra **các ranh giới giữa người đề xuất, người phê duyệt, người thực thi và người đối soát**, phù hợp mức rủi ro.

### 1.1. Mục tiêu chính

| Mục tiêu | Ý nghĩa trong IAM | Ví dụ |
| --- | --- | --- |
| **Ngăn tự cấp quyền** | Người hưởng lợi không tự hợp thức hóa yêu cầu của mình. | Admin không tự duyệt vai trò quản trị của bản thân. |
| **Ngăn tổ hợp quyền xung đột** | Không để một người kiểm soát hai bước nghiệp vụ không nên kết hợp. | Tạo vendor và duyệt thanh toán cùng vendor. |
| **Bảo vệ luồng phê duyệt** | Người phê duyệt phải độc lập, đủ thẩm quyền và có dữ liệu hiện hành. | Data owner duyệt quyền dữ liệu nhạy cảm. |
| **Giới hạn người thực thi** | Quyền vận hành connector không trở thành quyền tự phê duyệt. | Service principal chỉ thực hiện yêu cầu đã duyệt. |
| **Truy vết và phát hiện ngoại lệ** | Có thể chứng minh ai đề xuất, ai quyết định, ai thực thi. | Audit phân biệt actor với beneficiary. |
| **Giảm đặc quyền tồn dư** | Thay đổi JML phải tái đánh giá các quyền và approval cũ. | Mover bỏ quyền từ phòng ban trước. |

**SoD không thay thế least privilege.** Một người có ít quyền nhưng sở hữu cả hai quyền xung đột vẫn có thể gây rủi ro; ngược lại, chia trách nhiệm cho hai người nhưng mỗi người giữ quyền quản trị toàn tenant cũng không phải thiết kế tối thiểu.

## 2. Phân biệt SoD, four-eyes, dual control và approval

| Khái niệm | Cơ chế | Cần chú ý |
| --- | --- | --- |
| **Separation of duties** | Tách những trách nhiệm hoặc quyền xung đột theo chính sách. | Có thể áp dụng cho assignment, phiên và giao dịch. |
| **Four-eyes / maker-checker** | Một người thực hiện/đề xuất, người độc lập khác kiểm tra hoặc phê duyệt. | Hai tài khoản của cùng một người **không phải** hai đôi mắt độc lập. |
| **Dual control** | Một hành động nhạy cảm cần sự tham gia của ít nhất hai chủ thể đủ thẩm quyền. | Có thể yêu cầu hai phê duyệt/điều kiện trước khi thao tác. |
| **Multi-level approval** | Yêu cầu qua nhiều cấp hoặc nhiều owner. | Nhiều bước không bảo đảm độc lập nếu cùng người duyệt mọi bước. |
| **Least privilege** | Mỗi principal chỉ được quyền cần thiết trong phạm vi/thời hạn hợp lệ. | Cần kết hợp với SoD để hạn chế tổ hợp quyền. |
| **Access review** | Rà soát quyền đang có có còn cần và hợp lệ không. | Không chỉ kiểm ticket duyệt ban đầu. |
| **PAM/JIT** | Đặc quyền được kích hoạt theo thời gian/phiên hoặc tác vụ. | Quyền đủ điều kiện kích hoạt cũng cần SoD và review. |

**Không đánh đồng số lượng nhấp “Approve” với mức độc lập**. Nếu requester tạo yêu cầu, dùng một tài khoản phụ để duyệt và tài khoản thứ ba để thực thi thì toàn bộ workflow vẫn có thể do một người điều khiển.

## 3. Ba kiểu SoD quan trọng

### 3.1. Static Separation of Duties (SSD)

**SSD** hạn chế việc **cùng một chủ thể được gán** những role/quyền có xung đột, bất kể có sử dụng chúng cùng lúc hay không.

Ví dụ chính sách:

~~~text
CONFLICT:
    role("vendor-creator")
    AND role("vendor-payment-approver")
    WITHIN same financial scope

=> Không cấp role thứ hai nếu role thứ nhất vẫn có hiệu lực.
~~~

Trong một số mô hình, conflict chỉ có ý nghĩa **trên cùng phạm vi dữ liệu/đơn vị**. Người có quyền tạo vendor ở công ty A và duyệt thanh toán ở công ty B có thể được policy đánh giá khác người có cả hai quyền trong cùng công ty. Phải mô hình hóa scope rõ, không chỉ so sánh tên role.

### 3.2. Dynamic Separation of Duties (DSD)

**DSD** có thể cho một người **đủ điều kiện giữ nhiều role**, nhưng hạn chế **những role được kích hoạt hoặc được sử dụng đồng thời** trong phiên, tác vụ hay giao dịch.

Ví dụ một nhân viên được đào tạo hai nhiệm vụ và có quyền phục vụ hai ca khác nhau, nhưng không được vừa **tạo** vừa **phê duyệt** cùng một khoản thanh toán. Hệ thống cần kiểm **transaction ID, người thực hiện bước trước, quyền đang kích hoạt và điều kiện policy tại thời điểm thao tác**.

**Không phải ứng dụng nào cũng hỗ trợ DSD ở lớp session.** Nếu ứng dụng chỉ có RBAC group tĩnh, cần kiểm soát ngay trong workflow hoặc transactional authorization; chỉ gán hai group không tự tạo SoD động.

### 3.3. Procedural SoD – phân tách nhiệm vụ trong quy trình

Ngoài SSD/DSD, approval workflow cần ngăn việc một người đảm nhiệm các bước xung đột:

~~~text
maker      = người khởi tạo thay đổi
checker    = người kiểm tra / phê duyệt độc lập
executor   = người hoặc hệ thống thực hiện thay đổi
verifier   = bên xác minh trạng thái đích

Yêu cầu:
    checker không được là maker/beneficiary
    checker phải có authority hợp lệ
    executor chỉ thực thi quyết định APPROVED còn hiệu lực
    verifier không được chỉ dựa vào lời tự khai của executor
~~~

Ví dụ: một helpdesk operator có thể nhập thông tin request, nhưng không nên tự phê duyệt **reset MFA** hoặc **cấp role quản trị** cho chính mình hoặc cho một tài khoản họ có thể kiểm soát.

### 3.4. So sánh

| Mẫu | Ngăn vấn đề gì? | Nơi thực thi |
| --- | --- | --- |
| **SSD** | Đồng thời sở hữu những quyền xung đột. | IGA/RBAC assignment engine. |
| **DSD** | Sử dụng/kích hoạt quyền xung đột trong cùng phiên/giao dịch. | Session manager, ứng dụng, transaction engine. |
| **Procedural SoD** | Tự đề xuất, tự duyệt và tự thực thi thay đổi nhạy cảm. | Workflow engine, approval policy, audit. |
| **Independent verification** | Một workflow tự tuyên bố đã thu hồi/cấp quyền mà không có bằng chứng. | Reconciliation, kiểm tra trạng thái ở provider. |

Một hệ thống rủi ro cao thường cần **kết hợp nhiều lớp**, không chọn một lớp để thay thế hoàn toàn lớp khác.

## 4. Các chủ thể trong một approval workflow

| Vai trò workflow | Trách nhiệm | Quan hệ cần kiểm |
| --- | --- | --- |
| **Requester** | Người hoặc hệ thống khởi tạo yêu cầu. | Có đang xin quyền cho chính mình? |
| **Beneficiary / target subject** | Chủ thể sẽ nhận hoặc mất quyền. | Là ai ở cấp Person/Engagement, không chỉ tài khoản? |
| **Sponsor / manager** | Xác nhận quan hệ và nhu cầu công việc. | Có còn là người quản lý hợp lệ lúc phê duyệt? |
| **Application owner** | Chịu trách nhiệm quyền của ứng dụng. | Có đủ thẩm quyền với role và môi trường cụ thể? |
| **Data/resource owner** | Đánh giá phạm vi dữ liệu được truy cập. | Có thực sự sở hữu resource/tenant được yêu cầu? |
| **Security/SoD reviewer** | Đánh giá xung đột, rủi ro và kiểm soát bổ sung. | Có độc lập và không tự hưởng lợi? |
| **Approver** | Ra quyết định được workflow chấp nhận. | Có authority và chưa bị ủy quyền sai? |
| **Executor / provisioner** | Thực hiện cấp/thu hồi tại hệ thống đích. | Chỉ làm đúng yêu cầu được duyệt và scope. |
| **Verifier / reconciler** | Đọc lại trạng thái đích và so expected/actual. | Bằng chứng có độc lập với request không? |
| **Auditor** | Đánh giá kiểm soát và bằng chứng. | Không tự thay thế vai trò phê duyệt nghiệp vụ. |

Một người có thể đảm nhiệm nhiều trách nhiệm **không xung đột**; SoD không nhất thiết yêu cầu mỗi vai trò là một nhân viên khác. Tuy nhiên, các cặp trách nhiệm xung đột phải được policy định nghĩa và kiểm tra.

### 4.1. Actor khác beneficiary

Ví dụ quản lý gửi yêu cầu cho nhân viên mới:

~~~text
Requester:     manager-A
Beneficiary:   employee-B
Approver:      data-owner-C
Executor:      scim-connector-D (service principal)
Verifier:      reconciliation-service-E
~~~

Nếu **Requester = Manager** thì không tự động vi phạm SoD. Nếu **Approver = Beneficiary** trong yêu cầu nhạy cảm thì có thể là vi phạm. Cần phân biệt rõ **ai thực hiện hành động**, **ai nhận quyền**, **ai có lợi ích**, **ai có thẩm quyền**.

### 4.2. Một người nhiều tài khoản

Ví dụ:

~~~text
PersonID: P-1042
    ├── user account: an@example.test
    ├── privileged account: an-admin@example.test
    └── secondary account: an-breakfix@example.test
~~~

Nếu tài khoản thường gửi yêu cầu và tài khoản admin của cùng Person duyệt, hệ thống phải nhận diện **cùng chủ thể**, không chấp nhận vì account IDs khác nhau.

Với service accounts, cần xác định **owner/workload** và quyền điều khiển principal. Một người vừa điều khiển requester bot vừa có quyền phê duyệt tự động cũng có thể tạo xung đột thực chất.

## 5. Ranh giới tin cậy: quyết định không được dựa vào trường tự khai

Một workflow thiếu an toàn có thể nhận payload:

~~~json
{
  "requesterId": "employee-1042",
  "approverId": "data-owner-2088",
  "role": "production-admin",
  "approved": true
}
~~~

Nếu API tin `approved=true` hoặc `approverId` do requester tự gửi, SoD chỉ tồn tại trên giao diện. **Server phải xác thực actor, xác định reviewer hợp lệ từ nguồn có thẩm quyền và tạo quyết định phê duyệt qua endpoint được bảo vệ**.

Các trường cần ràng buộc:

- **Authenticated actor:** principal được IdP/API xác thực, liên kết đúng subject/tenant.
- **Beneficiary identity:** người hoặc workload đích được resolve theo ID bền vững.
- **Requested entitlement:** role/permission chính xác trong catalog, scope và thời hạn.
- **Approval authority:** xác định từ policy và owner hiện hành, không do requester tự chọn tùy tiện.
- **Decision evidence:** người duyệt thật, thời điểm, request version và hành động được duyệt.
- **Execution authorization:** connector chỉ sử dụng quyết định còn hiệu lực cho đúng target/version.
- **Final verification:** trạng thái thực tế tại ứng dụng, không chỉ workflow status.

**JWT hoặc SAML assertion hợp lệ chỉ xác minh thông tin đăng nhập theo issuer và quy tắc validation**; nó không tự chứng minh người đó được phép phê duyệt **yêu cầu cụ thể** nếu quyền approver đã thay đổi.

## 6. Mô hình workflow có SoD và điểm kiểm tra

~~~mermaid
flowchart TD
    A["Nguồn JML / User access request"] --> B["Xác thực actor + resolve beneficiary<br/>Person/Engagement/Workload"]
    B --> C["Tra role catalog, scope,<br/>risk tier và policy SoD"]
    C --> D{"Eligibility / SSD<br/>có hợp lệ?"}
    D -->|"Không"| X["Từ chối hoặc exception review"]
    D -->|"Có"| E["Xác định approver có thẩm quyền<br/>không self-approve"]
    E --> F["Business / data-owner approval<br/>đúng thứ tự và độc lập"]
    F --> G{"Đủ phê duyệt?"}
    G -->|"Không"| X
    G -->|"Có"| H["Revalidate policy, subject,<br/>effectiveAt và request version"]
    H --> I{"Vẫn hợp lệ?"}
    I -->|"Không"| X
    I -->|"Có"| J["Provision / revoke qua<br/>IdP, SCIM, PAM, app API"]
    J --> K["Readback và kiểm<br/>effective access"]
    K --> L{"Verified?"}
    L -->|"Không"| M["Exception có owner,<br/>risk, deadline"]
    M --> K
    L -->|"Có"| N["Audit + review / expiry schedule"]
~~~

**Sơ đồ mô tả luồng logic**, không áp đặt mọi request phải có số bước giống nhau. Quyền baseline đã được chấp thuận bằng chính sách có thể dùng **policy approval trước**, trong khi quyền đặc biệt yêu cầu owner và security review riêng.

### 6.1. Điểm kiểm tra SoD không chỉ ở đầu yêu cầu

Một hồ sơ có thể hợp lệ lúc mở request nhưng không còn hợp lệ khi duyệt hoặc thực thi:

- Manager đã thay đổi.
- Beneficiary đã Mover/Leaver.
- Reviewer đã chuyển vị trí hoặc bị khóa.
- Role permission set đã được mở rộng.
- Một role xung đột được cấp trong lúc request chờ.
- Scope tài nguyên hoặc phân loại dữ liệu thay đổi.

Vì thế cần kiểm **tại lúc tạo request, lúc đưa ra quyết định quan trọng và ngay trước lúc provisioning**; quyền rủi ro cao có thể cần thêm kiểm soát tại thời điểm sử dụng.

## 7. Thiết kế ma trận SoD cho các quyền xung đột

### 7.1. Từ nghiệp vụ sang quyền kỹ thuật

Một ma trận SoD cần kết nối **hoạt động nghiệp vụ** với **role/permission thực tế**:

| Nhóm nghiệp vụ | Quyền A | Quyền B | Xung đột tiềm tàng |
| --- | --- | --- | --- |
| **Procure-to-pay** | Tạo hoặc sửa nhà cung cấp. | Phê duyệt thanh toán cho nhà cung cấp. | Tự lập bên nhận và tự trả tiền. |
| **Payroll** | Thay thông tin nhận lương. | Duyệt lệnh chi lương. | Chuyển tiền không được kiểm tra độc lập. |
| **Identity administration** | Tạo user/reset authenticator. | Tự gán admin hoặc duyệt cấp quyền. | Tạo danh tính/đường truy cập trái phép. |
| **CI/CD production** | Sửa source/pipeline artifact. | Bỏ qua release gate hoặc duyệt deployment. | Đưa mã chưa được kiểm tra vào production. |
| **Secrets management** | Đọc/đổi secret. | Tự thay access policy hoặc xóa audit. | Chiếm credential và che dấu vết. |
| **Data governance** | Hạ classification của dữ liệu. | Tự phê duyệt quyền xuất dữ liệu. | Vượt giới hạn bảo mật dữ liệu. |

Không phải cứ hai quyền xuất hiện cùng nhau là luôn phải cấm. Cần xác định **resource scope, tenant, môi trường, giá trị giao dịch, mối quan hệ beneficiary và các kiểm soát bù**. Chính sách do owner có thẩm quyền chấp nhận.

### 7.2. Mô hình rule

Một rule có thể chứa:

~~~yaml
# Chính sách nội bộ minh họa, không phải chuẩn YAML IAM.
conflictId: SOD-PAYMENT-001
description: "Không vừa tạo vendor vừa duyệt khoản chi cho cùng phạm vi"
type: STATIC_AND_TRANSACTIONAL
permissionA: vendor.create
permissionB: payment.approve
scopeMatch:
  - tenantId
  - businessUnitId
subjectMatch: canonicalPersonId
condition:
  sameVendorOrTransaction: true
severity: CRITICAL
decision: DENY_OR_INDEPENDENT_EXCEPTION
ownerTeam: finance-controls
policyVersion: 5
~~~

Giá trị là **ví dụ thiết kế**, không phải rule động thực thi ngay. Với SoD giao dịch, cần kiểm history của **cùng transaction/vendor**, không chỉ phép giao role. Nếu exception được cho phép, phải có phê duyệt độc lập, thời hạn và cơ chế phát hiện phù hợp.

### 7.3. Conflict matrix cần được quản trị như policy

Mỗi rule cần có:

- **Business rationale**, risk owner và mức nghiêm trọng.
- **ID quyền/role canonical**, điều kiện scope.
- **Kiểu SSD/DSD/procedural** và điểm thực thi.
- **Exception policy**, người có thẩm quyền chấp nhận, hạn hiệu lực.
- **Version, date-effective và review cadence**.
- **Tác động tới assignment đang tồn tại** khi role hoặc policy thay đổi.

Không nên để một nhóm kỹ thuật tùy ý xóa conflict rule để giải quyết ticket cấp quyền.

## 8. Tính effective entitlements trước khi kiểm SoD

**Role trực tiếp** không luôn là tập quyền thực tế:

~~~text
Employee A
  ├── Role: finance-reader
  ├── Directory Group: operations-support
  │      └── Nested Group: privileged-approvers
  ├── SaaS direct grant: payment-approver
  ├── Cloud role: permission to assign roles
  └── JIT eligibility: activate production-admin
~~~

Chỉ nhìn Role = finance-reader có thể bỏ qua **quyền duyệt thanh toán**, quyền admin kế thừa hoặc khả năng tự kích hoạt admin.

### 8.1. Nguồn quyền phải đánh giá

| Nguồn | Cơ chế | Nguy cơ SoD |
| --- | --- | --- |
| **RBAC direct role** | Gán role trực tiếp. | Quyền xung đột rõ ràng. |
| **Role hierarchy** | Quyền kế thừa từ role thấp/cao theo cấu trúc. | Conflict gián tiếp không hiển thị ở direct roles. |
| **Nested/dynamic groups** | Thành viên nhóm gián tiếp hoặc tính từ thuộc tính. | Quyền xuất hiện do cấu trúc nhóm/attribute. |
| **ABAC** | Quyền theo bộ phận, scope, tài nguyên và thời gian. | Conflict có thể chỉ tồn tại trên cùng resource. |
| **Local app role** | Cấp trực tiếp trong SaaS/DB. | Ngoài tầm quan sát của group IdP. |
| **PAM/JIT eligibility** | Có thể kích hoạt role đặc quyền. | Reviewer phải xem cả quyền đủ điều kiện, không chỉ phiên đã active. |
| **Delegation** | Người khác ủy quyền phê duyệt. | Người thụ hưởng có thể nhận quyền duyệt yêu cầu của mình. |
| **Credential/secret access** | Đọc PAT, key hoặc mật khẩu tài khoản mạnh hơn. | Khả năng giả danh người khác, vượt SoD nhân sự. |

### 8.2. Đường nâng đặc quyền

Một principal có thể không sở hữu role admin hiện tại nhưng có quyền **sửa role mapping, đổi approval policy, tạo API token hoặc assume role**. Đó là đường nâng đặc quyền cần phân tích, không thể kết luận an toàn từ việc role name không có chữ “admin”.

Khi đánh giá SoD cần nắm **quyền thực thi hiệu lực, điều kiện kích hoạt và khả năng cấp tiếp** trong phạm vi hệ thống. Các kiểm thử quyền phải thực hiện trên môi trường được phép, tránh tự thử thao tác phá hủy.

## 9. Chọn reviewer đúng người và đúng thời điểm

### 9.1. Tách người xác nhận nhu cầu và người hiểu quyền

Một manager thường biết nhân viên cần công việc nào, còn **application/data owner** hiểu role cung cấp permission gì. Với role nhạy cảm, workflow có thể yêu cầu:

1. **Manager/sponsor approval:** xác nhận nhu cầu công việc.
2. **Application/data owner approval:** xác nhận role, scope và tài nguyên.
3. **Security/IGA policy:** kiểm SoD, độ nhạy dữ liệu và điều kiện đặc quyền.

Đôi khi role baseline có thể được cấp qua **chính sách birthright đã duyệt trước**, thay vì gửi từng request cho nhiều người. Nhưng cơ chế tự động này phải có catalog, owner và lịch review.

### 9.2. Kiểm tra thẩm quyền thực sự

Reviewer phải:

- Có **subject ID đáng tin**, account đang hoạt động và điều kiện xác thực thích hợp.
- Không phải **beneficiary/requester** hoặc principal do beneficiary kiểm soát khi rule cấm.
- Có thẩm quyền với **ứng dụng, role, tenant và resource scope cụ thể**.
- Không phải người đang giữ **xung đột lợi ích** theo chính sách.
- Được xác định theo **cơ cấu quản lý/owner hiện hành** tại thời điểm quyết định.
- Không dùng credential bị chia sẻ khiến không xác định ai thật sự phê duyệt.

**Một email thông báo có ghi “manager” không đủ làm bằng chứng về quyền phê duyệt.** Phải xác minh nguồn quản lý, owner catalog và authorization tại endpoint quyết định.

## 10. Chống self-approval trên nhiều cấp danh tính

Một quy tắc đơn giản:

~~~text
if approver.accountId == beneficiary.accountId:
    reject
~~~

**Chưa đủ** vì cùng một người có thể có nhiều tài khoản, bao gồm privileged account và tài khoản ở các IdP khác nhau.

Nên so sánh ở cấp thích hợp:

~~~text
beneficiaryPerson = resolveCanonicalPerson(beneficiaryAccount)
requesterPerson   = resolveCanonicalPerson(requesterAccount)
approverPerson    = resolveCanonicalPerson(approverAccount)

if approverPerson == beneficiaryPerson:
    DENY self-approval

if approverPerson == requesterPerson AND policy.requiresDifferentMakerChecker:
    DENY maker-checker conflict
~~~

Đây là giả mã **minh họa**, không phải hướng dẫn truy cập tài khoản. Khi resolve Person/Engagement không chắc chắn, phải đưa vào bước xác minh thay vì mặc định hai tài khoản khác ID là hai người độc lập.

### 10.1. Proxy, ủy quyền và chủ sở hữu tài khoản

Một manager có thể ủy quyền phê duyệt cho nhân viên cấp dưới. Nếu nhân viên này xin quyền và đồng thời trở thành delegate có thể duyệt chính yêu cầu ấy, SoD bị phá dù hệ thống ghi nguồn duyệt là “manager delegated”.

Cần lưu **delegator, delegate, nguồn authorization, phạm vi quyền, thời gian hiệu lực và từng hành động thật sự của delegate**, sau đó kiểm SoD trên **người thực thi quyết định** và **người có thể hưởng lợi**.

### 10.2. Tài khoản chia sẻ

Đối với tài khoản quản trị chia sẻ, hệ thống khó chứng minh cá nhân nào đã bấm Approve nếu không có cơ chế ánh xạ session/checkout với **named identity**. Tránh dùng shared account làm reviewer cho thay đổi nhạy cảm; nếu hoàn cảnh vận hành bắt buộc, phải có cơ chế nhận diện/kiểm soát riêng và policy xử lý rủi ro.

## 11. Ủy quyền, người duyệt vắng mặt và escalation

Thực tế có thể xảy ra: manager nghỉ phép, data owner rời công ty, approver không trả lời hoặc hết thời hạn SLA. **Thiếu người duyệt không được biến thành “tự động đồng ý”** đối với quyền nhạy cảm.

### 11.1. Ủy quyền hợp lệ

| Thuộc tính delegation | Điều cần ghi |
| --- | --- |
| **delegatorId** | Ai có thẩm quyền gốc? |
| **delegateId** | Người được ủy quyền là ai? |
| **approvalScope** | Loại request, ứng dụng, role và tenant được phép duyệt. |
| **effectiveAt / expiresAt** | Từ lúc nào, đến khi nào? |
| **reason / approvalRef** | Lý do và bằng chứng phân quyền. |
| **canRedelegate** | Có được ủy quyền tiếp không, theo policy? |
| **sodConstraints** | Trường hợp nào delegate không được quyết định? |
| **revocationPolicy** | Khi delegator/nhân viên Mover/Leaver thì quyền có còn không? |

### 11.2. Escalation an toàn

Khi quá hạn:

1. Gửi nhắc nhở không làm thay đổi trạng thái phê duyệt.
2. Kiểm người duyệt hiện tại có còn đủ thẩm quyền không.
3. Chọn reviewer thay thế theo **ma trận ủy quyền/escalation đã duyệt**, không do requester tự chọn.
4. Kiểm lại self-approval, manager relationship và SoD của người được chuyển.
5. Với quyền rủi ro cao, yêu cầu cấp phê duyệt tương ứng thay vì bỏ qua bước.
6. Ghi audit việc chuyển tuyến và lý do.

**SLA quá hạn là vấn đề vận hành, không phải bằng chứng mặc nhiên request được chấp thuận**.

## 12. Role catalog và các thuộc tính dùng trong quyết định

Một request phải tham chiếu role/permission trong **catalog có quản trị**, bao gồm:

| Thuộc tính | Mục đích |
| --- | --- |
| **roleId / permissionSet** | Biết đúng chức năng và quyền hiệu lực. |
| **roleOwner / dataOwner** | Quyết định ai có thẩm quyền phê duyệt. |
| **scope** | Tenant, tài nguyên, dự án, environment. |
| **riskTier** | Xác định tuyến phê duyệt và step-up. |
| **eligibility** | Worker type, department, contract, owner và trạng thái. |
| **sodRules** | Xung đột role và workflow. |
| **approvalPolicy** | Ai duyệt, thứ tự, số người độc lập. |
| **maxDuration** | Giới hạn thời gian sử dụng quyền. |
| **provisioningMapping** | SCIM Group, app API, IdP group hoặc PAM entitlement. |
| **version / effectiveAt** | Theo dõi thay đổi quyền của role và lúc áp dụng. |

**Tại thời điểm phê duyệt phải biết role chứa quyền gì**. Nếu role definition được sửa sau khi request tạo, việc duyệt dựa trên snapshot cũ có thể chấp thuận quyền rộng hơn reviewer tưởng.

### 12.1. Thay đổi role definition

Giả sử role `finance-reader` vốn chỉ được xem báo cáo, sau đó được bổ sung quyền export toàn bộ dữ liệu. Mọi assignment đang tồn tại có thể bị mở rộng quyền mà không có yêu cầu mới.

Phải có:

- Change control của permission-role assignment.
- Tác động tới người đang giữ role và các rule SoD liên quan.
- Reviewer/owner có thẩm quyền phê duyệt thay đổi.
- Phiên bản role và khả năng tái chứng nhận khi quyền thay đổi lớn.
- Cơ chế cập nhật policy và kiểm tra đích sau triển khai.

## 13. Điều kiện dữ liệu: HRIS, IdP, IGA, owner và thời điểm hiệu lực

Quyết định SoD dựa trên dữ liệu từ nhiều hệ thống. Cần phân biệt:

| Dữ liệu | Nguồn có thẩm quyền thường gặp | Nguy cơ |
| --- | --- | --- |
| **Person/Engagement/workerType** | HRIS/hợp đồng và identity proofing. | Trùng danh tính, rehire, account chưa đủ điều kiện. |
| **Department, manager** | HRIS/org master được chỉ định. | Tuyến duyệt stale sau Mover. |
| **Role eligibility** | IGA và policy role catalog. | Người chuyển nhiệm vụ vẫn đủ điều kiện theo cache cũ. |
| **Application/data owner** | Catalog nghiệp vụ có owner xác định. | Request được duyệt bởi người không còn quản lý resource. |
| **Current assignments** | IGA + directory + app/cloud/PAM actual. | SSD bỏ sót direct/nested entitlements. |
| **Approval delegation** | Workflow/delegation registry. | Người duyệt được ủy quyền vượt phạm vi/hết hạn. |
| **Session authentication** | IdP/MFA/session authority. | Shared/expired session chấp thuận trái phép. |
| **Resource scope/classification** | Data/resource governance. | Duyệt quyền trên sai tenant hoặc dữ liệu nhạy cảm. |

**Nguồn cung cấp một thuộc tính chưa chắc là nguồn sở hữu nó**. Ví dụ IdP claim về department có thể được lấy từ HRIS đồng bộ hôm qua; token có chữ ký hợp lệ không tự chứng minh department còn đúng hôm nay.

### 13.1. Thời gian trong approval workflow

| Mốc | Ý nghĩa |
| --- | --- |
| **requestedAt** | Yêu cầu được tạo lúc nào. |
| **reviewStartedAt** | Reviewer được giao và nhận dữ liệu lúc nào. |
| **decisionAt** | Approval/rejection được xác nhận lúc nào. |
| **effectiveAt** | Quyền được phép bắt đầu có hiệu lực theo nghiệp vụ. |
| **expiresAt** | Quyền phải hết hạn hoặc được phê duyệt lại. |
| **sourceVersionAtDecision** | Phiên bản dữ liệu JML/role mà người duyệt đã sử dụng. |
| **provisionedAt** | Hệ thống đích ghi nhận lệnh lúc nào. |
| **verifiedAt** | Quyền thực tế được đọc lại và xác minh khi nào. |

**Không đồng nhất requestedAt với effectiveAt**. Người dùng có thể đề nghị quyền trước ngày bắt đầu công việc, nhưng thời điểm cấp thực tế phải dựa trên nguồn có thẩm quyền và quy tắc role.

## 14. Joiner: SoD trong tạo danh tính và cấp quyền ban đầu

### 14.1. Nguy cơ tạo hồ sơ và tự cấp quyền

Một operator có thể tạo user ở directory. Nếu cũng có quyền tự phê duyệt role admin và tự cấp quyền, họ có thể tạo một danh tính khó phát hiện rồi sử dụng.

Trong Joiner nên phân tách:

1. **HRIS/HR hoặc sponsor** xác nhận người và quan hệ làm việc.
2. **IAM/IGA** kiểm trùng và identity proofing, tạo canonical subject.
3. **Role catalog/policy** quyết định birthright roles được phép tự động.
4. **Owner độc lập** duyệt quyền nhạy cảm ngoài baseline.
5. **Connector** chỉ cấp quyền theo quyết định đã được xác thực.
6. **Reconciliation** xác minh actual và phát hiện quyền ngoài workflow.

### 14.2. Preboarding

Nếu Start date là 01/12, tài khoản có thể được pre-provision trước ngày này. Điều đó không có nghĩa role admin được sử dụng từ lúc tạo account. **ActivationAt, approval và đủ tư cách** phải được kiểm riêng. Nếu preboarding cần truy cập tài liệu, nên dùng role riêng có phạm vi hẹp.

### 14.3. Birthright có cần approval?

Các quyền baseline có thể được cấp tự động dựa trên chính sách đã được owner/Security phê duyệt trước. Đây là **phê duyệt cấp policy**, không phải “không có kiểm soát”. Role nhạy cảm hoặc quyền xung đột thường cần **quy trình yêu cầu cụ thể và đánh giá SoD**.

## 15. Mover: thay manager, bộ phận và đường phê duyệt

Mover tạo ra hai thay đổi đồng thời:

- **Quyền của beneficiary:** role cũ có thể không còn hợp lệ; role mới cần phê duyệt.
- **Tuyến phê duyệt:** manager, data owner, project sponsor hoặc reviewer có thể thay.

### 15.1. Ví dụ thay manager khi yêu cầu đang chờ

~~~text
09:00  An gửi yêu cầu quyền data-export.
09:02  Workflow xác định manager cũ là M1.
10:00  HRIS ghi An chuyển bộ phận; manager mới là M2, có hiệu lực 10:00.
10:15  M1 mở email và nhấn Approve từ đường link cũ.
~~~

Nếu workflow chỉ tin **managerId được chụp lúc 09:02**, yêu cầu có thể được phê duyệt bởi người **không còn thẩm quyền**.

Một xử lý đúng theo policy có thể:

1. Đối chiếu thời điểm có hiệu lực của thay đổi manager từ HRIS.
2. Kiểm lại M1 còn quyền phê duyệt request tại **10:15** hay không.
3. Nếu không, vô hiệu approval link/token cũ, chuyển đúng người duyệt hoặc yêu cầu tái duyệt.
4. Kiểm lại eligibility và resource scope vì bộ phận cũng có thể thay.
5. Không tự đồng ý hoặc bỏ bước phê duyệt chỉ vì manager chưa đồng bộ.
6. Ghi lý do thay tuyến và phiên bản dữ liệu nguồn.

### 15.2. Grant mới phải đi với Revoke cũ

SoD theo role có thể thay sau Mover:

| Trạng thái | Trước Mover | Sau Mover |
| --- | --- | --- |
| **Role công việc** | vendor-creator | payment-approver |
| **Quyền phải thu hồi** | Chưa có thay đổi | vendor-creator cũ (nếu không còn hợp lệ). |
| **Role mới** | Chưa cấp | payment-approver sau xét SoD. |
| **Nguy cơ** | Một chức năng | Cả hai role nếu connector chỉ thêm không xóa. |

**Chỉ cấp payment-approver mà không thu hồi vendor-creator có thể tạo SSD conflict**. Quy trình Mover cần kiểm toàn bộ **expected vs actual entitlements**, kể cả app-local grants, nested groups và token/phiên cũ.

## 16. Leaver: thu hồi và ngăn workflow cũ tái cấp quyền

### 16.1. Leaver yêu cầu hành động ngay theo policy

Khi HRIS/hợp đồng xác nhận engagement đã kết thúc, IAM cần:

1. Chặn những request đang chờ cấp quyền cho engagement đã hết.
2. Thu hồi role, group, direct grants và approvals còn hợp lệ nhưng không còn nhu cầu.
3. Vô hiệu hóa IdP/directory account, local account và quyền đích qua SCIM/API.
4. Thu hồi phiên/token, PAT/API key và credential ngoài SSO theo khả năng sản phẩm.
5. Chuyển reviewer/delegation/owner của quy trình cho người còn thẩm quyền.
6. Đọc lại trạng thái hệ thống đích; theo dõi ngoại lệ chưa thu hồi.

**Không chờ đến kỳ access review định kỳ** để xử lý quyền của Leaver khi sự kiện đã có hiệu lực.

### 16.2. Retry cũ có thể phá SoD và lifecycle

~~~text
10:00  Mover request được phê duyệt cấp role mới.
10:02  SCIM connector timeout, không rõ lệnh đã áp dụng chưa.
10:05  HRIS gửi Leaver có hiệu lực ngay.
10:06  IAM bắt đầu revoke quyền.
10:10  Worker retry grant từ request Mover cũ.
~~~

Nếu worker **không kiểm lại nguồn và request version**, nó có thể tái cấp quyền cho người đã nghỉ. Cần **idempotency, sourceVersion/effectiveAt, trạng thái authoritative hiện hành và reconciliation** trước khi chạy lại grant.

### 16.3. Reviewer cũng có thể là Leaver

Nếu người duyệt rời tổ chức, những request đang chờ và delegation của họ phải được chuyển/khóa theo policy. **Không giữ tài khoản reviewer của Leaver hoạt động chỉ để hoàn thành hàng đợi**.

## 17. Rehire, Contractor và nhiều quan hệ lao động

Một người có thể quay lại làm việc với **engagement mới**, hoặc chuyển từ Contractor sang Employee. SoD cần xác minh **đúng Person** nhưng không sử dụng lại mọi role/approval của engagement trước.

### 17.1. Tình huống rehire

- Cùng email không đủ chứng minh cùng người; cần liên kết nguồn xác minh.
- Nếu Person được xác nhận là cùng người, **engagement mới** vẫn phải được đánh giá eligibility, role và SoD hiện hành.
- Không tự phục hồi approvals, privileged roles hoặc credential đã thu hồi.
- Những tài khoản phụ còn tồn tại từ lần làm việc trước phải được kiểm kê để tránh tổ hợp quyền xung đột.

### 17.2. Contractor và sponsor

Một Contractor có thể cần sponsor nội bộ phê duyệt quyền. **Sponsor không mặc nhiên có toàn quyền với mọi ứng dụng**, và không được phép tự duyệt những yêu cầu có xung đột lợi ích theo policy. Thời hạn role cần gắn với **end date hợp đồng** và lịch rà soát.

## 18. SoD với PAM, JIT, đặc quyền và break-glass

### 18.1. JIT không tự giải quyết SoD

**Just-in-Time (JIT)** làm ngắn thời gian đặc quyền được kích hoạt, nhưng không ngăn self-approval nếu người dùng vừa yêu cầu vừa được quyền duyệt elevation.

Một workflow JIT tốt có thể yêu cầu:

1. Xác thực mạnh/step-up theo risk.
2. Ticket hoặc lý do nhiệm vụ cụ thể.
3. Kiểm **eligible role** theo công việc và lifecycle hiện hành.
4. Người duyệt độc lập đối với quyền rủi ro cao, nếu policy yêu cầu.
5. Kiểm SSD/DSD và conflict trong session/giao dịch.
6. Chỉ kích hoạt role trong **scope, thời hạn và môi trường** được duyệt.
7. Giám sát phiên và ghi audit.
8. Thu hồi role/session khi hết hạn hoặc khi Leaver/sự cố xảy ra.

### 18.2. PAM reviewer và vault access

Một operator có quyền **đọc secret từ vault** có thể thực thi hành động dưới principal khác. Vì vậy, kiểm SoD không chỉ xét role của named account; phải xét **khả năng lấy credential, quản lý secret, mở privileged session và sửa policy của PAM**.

### 18.3. Break-glass

Trường hợp khẩn cấp có thể cần quy trình **break-glass** nhằm tránh mất khả năng cứu hệ thống khi workflow thông thường không khả dụng.

Điểm cần thiết:

- Kịch bản sử dụng và authority khẩn cấp được định nghĩa trước.
- Principal/credential được bảo vệ, có người chịu trách nhiệm.
- Ghi log/cảnh báo khi sử dụng, kết hợp **post-event review** độc lập.
- Thời hạn và thu hồi quyền sau xử lý.
- Không dùng break-glass như cách vượt SoD cho các yêu cầu thường ngày.

**Ngoại lệ khẩn là đường kiểm soát riêng**, không đồng nghĩa tắt toàn bộ SoD mà không có kiểm toán.

## 19. Tài khoản dịch vụ, workload và phê duyệt tự động

SoD không chỉ áp dụng cho Employee. Một **service principal** có thể:

- Nhận yêu cầu qua API.
- Tạo hoặc sửa entitlement.
- Chạy connector SCIM.
- Cấp cloud role, phát token hoặc quản lý secret.

Nếu cùng một principal có thể **tự tạo yêu cầu, gắn trạng thái approved và tự provision role bất kỳ**, đó là xung đột chức năng nghiêm trọng.

### 19.1. Thiết kế tách trách nhiệm

| Thành phần | Quyền tối thiểu | Điều không nên có |
| --- | --- | --- |
| **Request service** | Tạo yêu cầu và ghi actor/beneficiary đã xác thực. | Tự đặt trạng thái APPROVED cho request nhạy cảm. |
| **Policy/approval service** | Kiểm eligibility, SoD, reviewer authority, ghi quyết định. | Quyền thay trực tiếp toàn bộ role của mọi app không cần thiết. |
| **Provisioning connector** | Thực hiện đúng thao tác/tenant được duyệt. | Quyền phát quyết định approval mới. |
| **Reconciliation service** | Đọc lại entitlement và báo drift. | Quyền tự sửa policy hoặc che kết quả ngoài quy trình. |
| **Audit/log service** | Lưu evidence có bảo vệ toàn vẹn. | Cho executor sửa/xóa log tuỳ ý. |

**Tách service kỹ thuật không đủ nếu tất cả dùng chung một token toàn quyền**. Phải phân quyền identity/credential, scope API, môi trường, quản lý secret và khả năng đổi policy.

### 19.2. Owner của workload

Service account cần **ownerTeam, workloadId, purpose, credential lifecycle, permission scope và reviewAt**. Khi owner Employee nghỉ việc, phải chuyển giao trách nhiệm, rà soát credential từng chia sẻ và không giữ tài khoản người nghỉ chỉ để connector chạy tiếp.

### 19.3. Phê duyệt dựa trên chính sách

Một số thay đổi ít rủi ro có thể được **auto-approved** nếu thỏa rule đã được phê duyệt và hệ thống kiểm tra độc lập:

~~~text
AUTO_APPROVE chỉ nếu:
    role thuộc approved birthright catalog
    AND subject engagement ACTIVE
    AND role không xung đột SoD
    AND scope nằm trong policy
    AND effectiveAt hợp lệ
    AND nguồn identity/attribute đáng tin
~~~

Policy automation không phải một “người duyệt giả”. Cần **owner duyệt policy, versioning, giới hạn và audit**. Các yêu cầu vượt điều kiện phải chuyển reviewer hoặc bị từ chối, không tự nới rule.

## 20. Approval API, IdP/SSO và kiểm soát phiên

Một approver có thể xác thực qua **OIDC/SAML SSO**. Giao thức giúp xác minh danh tính nhưng workflow vẫn phải kiểm **authorization**:

- Token/assertion có issuer, audience, chữ ký, thời hạn và những ràng buộc phù hợp.
- Actor ở callback được liên kết với đúng **subjectId** và tenant.
- Quyền **approve** chỉ áp dụng cho request/role/resource scope được giao.
- Reviewer chưa Mover/Leaver, chưa hết delegation.
- Quyết định phê duyệt có thể cần **step-up MFA** khi rủi ro cao.
- Một URL approval cũ không được coi là quyền phê duyệt vĩnh viễn.

### 20.1. Tránh quyết định trên token/claim stale

Một token IdP có thể mang claim `manager=true` đã phát trước khi người duyệt chuyển bộ phận. Chữ ký hợp lệ không làm claim đó luôn đúng. Với request nhạy cảm, workflow cần kiểm **thẩm quyền manager/resource owner hiện hành** từ nguồn được chỉ định.

### 20.2. Ràng buộc quyết định với request cụ thể

Một bằng chứng approval nên ràng buộc:

~~~json
{
  "requestId": "access-req-8402",
  "requestVersion": 4,
  "beneficiarySubjectId": "person-1042",
  "targetTenantId": "tenant-a",
  "targetApplicationId": "finance-portal",
  "roleId": "finance-report-exporter",
  "scope": "business-unit-3",
  "expiresAt": "2026-12-31T17:00:00+07:00",
  "decision": "APPROVED",
  "approverSubjectId": "person-2088",
  "decisionAt": "2026-12-01T02:00:00Z",
  "policyVersion": "approval-policy-v7"
}
~~~

Schema JSON trên là **minh họa sự kiện nội bộ**, không phải token tự có tính bảo mật. Cần kiểm server-side, authority, tính toàn vẹn, expiry, phạm vi và trạng thái request. Không tin client tự đưa payload `APPROVED` vào API provisioning.

## 21. SCIM và điểm kiểm chứng sau phê duyệt

**SCIM** thường cung cấp User/Group provisioning cho ứng dụng. Một quyết định SoD được duyệt có thể dẫn đến thêm user vào nhóm, sửa thuộc tính hoặc vô hiệu hóa account.

~~~text
IGA request -> approved SoD-aware decision
   -> connector (SCIM PATCH / Group membership)
   -> provider response
   -> readback User/Group
   -> kiểm application role / authorization
   -> VERIFIED hoặc EXCEPTION
~~~

### 21.1. SCIM không phải nơi tự phê duyệt

SCIM định nghĩa thao tác trên User/Group, **không thay thế chính sách SoD của approval workflow**. Một connector có bearer token hợp lệ không có nghĩa bất kỳ yêu cầu PATCH nào cũng đã được phê duyệt đúng người/đúng quyền.

### 21.2. Lỗi kỹ thuật không được làm rơi kiểm SoD

| Lỗi | Phản ứng không an toàn | Phản ứng phù hợp |
| --- | --- | --- |
| **401/403** | Dùng token admin toàn tenant cho nhanh. | Kiểm credential/scope và quyền connector theo policy. |
| **409 uniqueness** | Xóa user hiện có rồi tạo lại để grant. | Đối chiếu subject và mapping trước khi liên kết. |
| **412 version conflict** | Bỏ If-Match, ép ghi đè. | Đọc lại version và tính delta theo trạng thái hiện hành. |
| **429/5xx** | Retry grant vô hạn, bỏ xác minh. | Backoff, giới hạn retry, đọc lại trạng thái trước. |
| **Timeout unknown** | Giả định request thất bại và thực hiện lại mù. | Kiểm kết quả provider, idempotency và request version. |
| **Group updated** | Đóng ticket ngay. | Kiểm local role, quyền kế thừa, session và actual access. |

Nếu quyền rủi ro cao không thể thu hồi đúng hạn, mở **incident/exception** và đánh giá biện pháp giảm thiểu. Không tự thay status thành “completed” vì một hệ thống trung gian trả 200.

## 22. Tính nhất quán, TOCTOU và race conditions

**Time of check to time of use (TOCTOU)** là vấn đề khi điều kiện được kiểm lúc này nhưng đã thay đổi trước lúc sử dụng hoặc thực thi.

### 22.1. Tình huống SoD biến đổi

~~~text
09:00  A xin quyền payment-approver, hiện chưa có vendor-creator.
09:01  SoD precheck PASS.
09:05  Qua một request khác, A được cấp vendor-creator.
09:10  Manager duyệt payment-approver.
09:12  Connector gán payment-approver từ kết quả precheck cũ.
~~~

Nếu không tái đánh giá, A giữ **hai quyền xung đột** mặc dù kiểm tra lúc 09:01 từng PASS.

### 22.2. Cơ chế giảm race

1. **Request version** và trạng thái approval có kiểm soát cạnh tranh.
2. **Tái đánh giá entitlement/SoD ngay trước thực thi grant**.
3. Dùng **transaction/lock/optimistic concurrency** ở nơi có thể để tránh hai request đồng thời cùng vượt kiểm tra.
4. Nếu đích không hỗ trợ giao dịch xuyên nhiều ứng dụng, dùng **reconciliation và xử lý bù**.
5. Kiểm nguồn nhân sự/manager hiện hành, không dùng snapshot quá hạn.
6. Đặt **idempotency key**, chống retry trùng và out-of-order.
7. Ghi rõ thời điểm **checkedAt, approvedAt, executedAt, verifiedAt**.

Không nên dựa vào một bước **kiểm SoD ngay khi gửi form** rồi bỏ qua toàn bộ trạng thái thay đổi giữa lúc chờ duyệt và thực thi.

### 22.3. Hai request độc lập nhưng kết hợp thành xung đột

Một người có thể xin Role A và Role B ở hai workflow khác nhau. Nếu mỗi workflow kiểm trước khi role kia được cấp, cả hai có thể được duyệt. Cần cơ chế **atomic/serialized policy decision hoặc reevaluation tại execution boundary**, tùy hạ tầng, để không có khoảng trống xung đột.

## 23. Exception, compensating control và rủi ro chấp nhận

Trong tổ chức nhỏ hoặc khi ứng cứu sự cố, đôi khi không thể phân tách người theo mô hình lý tưởng. Điều này **không biến SoD thành tùy chọn**; cần chính sách ngoại lệ theo rủi ro.

### 23.1. Một exception hợp lệ nên có

| Trường | Nội dung |
| --- | --- |
| **exceptionId / conflictId** | Rule nào đang bị ngoại lệ? |
| **businessJustification** | Tại sao cần ngoại lệ, không có phương án ít rủi ro hơn? |
| **affectedSubject/resource** | Người, tenant, role, giao dịch chịu tác động. |
| **riskAssessment** | Tác động gian lận, dữ liệu, vận hành và khả năng lạm dụng. |
| **approverIndependent** | Ai có thẩm quyền chấp nhận ngoại lệ và không hưởng lợi? |
| **compensatingControls** | Giám sát, review giao dịch hậu kiểm, scope/time restriction, dual log. |
| **effectiveAt / expiresAt** | Ngoại lệ tồn tại tới khi nào? |
| **owner / remediationPlan** | Ai khắc phục nguyên nhân và khi nào? |
| **auditEvidence** | Bằng chứng quyết định và theo dõi. |

### 23.2. Ví dụ đội vận hành ít nhân sự

Một nhân viên phải tạm thay người phê duyệt trong thời gian ca trực khẩn. Nếu SoD rule cho phép exception, có thể áp dụng:

- Hạn chế scope chỉ một hệ thống hoặc nhóm giao dịch.
- Giới hạn thời gian theo ca.
- Yêu cầu supervisor độc lập phê duyệt trước hoặc hậu kiểm tùy mức rủi ro.
- Ghi log giao dịch và cảnh báo khi quyền được dùng.
- Không cho cá nhân tự chấp nhận exception của chính mình.
- Thu hồi ngay khi người phê duyệt chính trở lại.

**Compensating control không tự động tương đương SoD đầy đủ**; phải đánh giá khả năng giảm rủi ro thật và ghi nhận phần rủi ro còn lại.

## 24. Approval workflow và phân tách nghĩa vụ trong cloud, API, CI/CD

### 24.1. Cloud/IAM

Một developer có quyền sửa **IAM policy** và tạo credential có thể tự tạo admin access dù không có role Owner trực tiếp. Vì vậy:

- Tách vai trò **đề xuất policy**, **duyệt policy** và **triển khai policy** khi rủi ro yêu cầu.
- Review quyền `iam:PassRole`, assume-role, tạo user/key, chỉnh trust/policy theo ngữ nghĩa platform cụ thể.
- Không giới hạn SoD chỉ vào role name; tính đường nâng quyền.
- Dùng JIT/approval và log cho thay đổi control plane nhạy cảm.

### 24.2. CI/CD

Rủi ro xảy ra nếu cùng người vừa:

1. Sửa source code.
2. Vô hiệu hóa kiểm thử/security gate.
3. Phê duyệt release.
4. Triển khai vào production.

Một workflow có thể yêu cầu **code review độc lập**, bảo vệ nhánh, ký artifact và deploy approval riêng. Tuy nhiên, chỉ có hai nút “Merge” và “Deploy” không đủ nếu cùng principal có thể thực hiện cả hai khi policy cấm.

### 24.3. API/data governance

Ứng dụng phải kiểm **đúng action thực tế và resource scope**, không tin `action=read` do client gửi nếu endpoint đang xuất/xóa dữ liệu. Đối với ABAC, nguồn `departmentId`, `resourceClassification` và owner phải được xác minh; người yêu cầu không được tự sửa nhãn tài nguyên rồi tự duyệt quyền truy cập nhãn mới.

## 25. Runbook điều tra vi phạm SoD

### Bước 1 – Xác định tín hiệu

Vi phạm có thể là:

- Người hưởng lợi tự duyệt quyền của mình.
- Một người giữ hai role xung đột theo SSD.
- Một người làm hai bước trên cùng giao dịch bị DSD/procedural SoD cấm.
- Quyền approver không còn hợp lệ do Mover/Leaver nhưng vẫn được dùng.
- Connector cấp quyền không có approval có hiệu lực.
- Log cho thấy approval và execution cùng do một tài khoản chia sẻ không thể quy về cá nhân.

### Bước 2 – Xác minh danh tính, scope và policy

Resolve **requester, beneficiary, approver, executor** về subject ID/engagement và owner/workload, đúng tenant. Tra **policy version tại thời điểm quyết định**, role catalog và effective permissions.

Không kết luận chỉ từ trùng displayName hoặc email; cũng không kết luận an toàn chỉ vì account IDs khác nhau.

### Bước 3 – Đánh giá hành động đã diễn ra

Một vi phạm SoD có thể là **cấu hình quyền xung đột chưa sử dụng**, hoặc đã có giao dịch/phiên thực thi. Phân biệt:

1. Quyền đã được **ASSIGNED**?
2. Quyền đã được **ACTIVATED**?
3. Hành động xung đột đã được **EXECUTED**?
4. Kết quả có ảnh hưởng tới dữ liệu/tài chính/cấu hình không?
5. Có credential, session hoặc direct grant ngoài workflow không?

### Bước 4 – Giảm thiểu theo rủi ro

Nếu có nguy cơ cấp quyền trái phép, cần thực hiện theo quy trình ứng cứu hoặc remediation được ủy quyền: hạn chế role, ngăn thực thi giao dịch, tạm ngưng approval route, bảo vệ evidence và gọi owner/Security.

**Không xóa ngay log, ticket hoặc account đang điều tra chỉ để làm biến mất cảnh báo.** Hành động thu hồi cần vừa an toàn vừa giữ bằng chứng theo chính sách.

### Bước 5 – Khắc phục nguyên nhân hệ thống

Kiểm rule SSD/DSD, identity linking, approval routing, delegated authority, concurrency, role hierarchy và local grants. Nếu lỗi bắt nguồn từ **source stale**, sửa pipeline HRIS/IGA. Nếu do **connector bypass**, phân tách service principals và authorization.

### Bước 6 – Xác minh và báo cáo

Đọc lại quyền đích, kiểm luồng approval từ chối self-approval và conflict, kiểm event ordering. Ghi owner, thời gian, tác động, ngoại lệ, kết quả và những đường truy cập chưa thể kiểm tra.

## 26. Giả mã kiểm SoD trong approval workflow

~~~text
submitAccessRequest(actor, beneficiary, role, scope, duration):
    requester = resolveTrustedSubject(actor)
    target = resolveTrustedBeneficiary(beneficiary)
    request = createImmutableVersionedRequest(
        requester, target, role, scope, duration
    )
    policy = loadCurrentApprovalPolicy(role, scope)

    if not isEligible(target, policy):
        return DENY

    if wouldCreateStaticConflict(
        target, role, scope, readEffectiveAssignments(target)
    ):
        return DENY_OR_INDEPENDENT_EXCEPTION_REVIEW

    approvers = resolveAuthorizedIndependentApprovers(
        request, authoritativeManagerAndOwnerSources()
    )
    return PENDING_APPROVAL(request, approvers)

approveRequest(authenticatedActor, requestId, decision):
    request = loadCurrentVersionOfRequest(requestId)
    approver = resolveTrustedSubject(authenticatedActor)

    if not hasCurrentApprovalAuthority(approver, request):
        return DENY
    if isSelfApprovalOrConflictOfInterest(approver, request):
        return DENY
    if requestIsStaleOrBeneficiaryIneligible(request):
        return RESTART_OR_REEVALUATE

    persistDecisionWithActorPolicyVersionAndTime(
        approver, request, decision
    )
    if independentApprovalsComplete(request):
        enqueueConditionalProvisioning(request)

executeApprovedGrant(job):
    latest = reloadAuthoritativeIdentityAndRoleState(job.beneficiary)
    if not requestApprovalAndEligibilityStillValid(job, latest):
        return CANCEL_OR_REEVALUATE
    if conflictsWithCurrentEffectiveAccess(job, latest):
        return DENY_OR_EXCEPTION
    response = executeMinimalAuthorizedChange(job)
    actual = readBackTargetAndEffectiveAccess(job)
    if actual matches expected:
        markVerifiedWithAudit(response, actual)
    else:
        openTrackedExceptionWithOwnerAndMitigation(job)
~~~

Giả mã chỉ minh họa **logic kiểm soát**, không phải chương trình sẵn sàng chạy. Trong hệ thống thật cần kiểm concurrency/transaction boundary, phiên bản role/policy, nhiều approval sources, retry idempotent, thời hạn, chữ ký request và khả năng provider không hỗ trợ cập nhật nguyên tử.

### 26.1. Không tin một boolean “approved”

Đường provisioning không nên chỉ nhận `approved=true`. Nó phải xác minh **request ID, approver có thẩm quyền, phiên bản request, role/scope, expiry, trạng thái JML và tất cả approval bắt buộc**. Nếu bất kỳ yếu tố quan trọng nào không thể kiểm chứng, không tự cấp quyền.

## 27. Audit trail và bằng chứng SoD

Một quyết định cần giải trình **người khởi tạo, người hưởng lợi, người duyệt thực, lý do, quyền, policy và trạng thái cuối**.

| Thuộc tính audit | Vì sao cần |
| --- | --- |
| **requestId / eventId / traceId** | Nối workflow với lệnh provisioning và ứng dụng. |
| **requestVersion / policyVersion** | Biết đúng dữ liệu/quy tắc đã duyệt. |
| **requesterSubjectId** | Ai gửi yêu cầu? |
| **beneficiarySubjectId / engagementId** | Ai được nhận quyền và còn quan hệ hợp lệ không? |
| **approverSubjectId / delegationRef** | Ai quyết định thực sự, có được ủy quyền không? |
| **roleId / permissionSet / scope** | Đúng quyền và tài nguyên nào? |
| **sodRuleIds / sodOutcome** | Rule nào được kiểm và kết quả gì? |
| **requestedAt / approvedAt / effectiveAt / expiresAt** | Mốc thời gian nghiệp vụ. |
| **executorPrincipalId / providerRequestId** | Connector nào thực thi? |
| **targetSystem / targetAccountId** | Đích nào nhận thay đổi? |
| **provisioningResult / verifiedAt** | Có kết quả đích và bằng chứng hay chưa? |
| **exceptionId / riskOwner / dueAt** | Những trường hợp chưa đáp ứng policy. |

Ví dụ log nội bộ **không chứa credential**:

~~~json
{
  "eventType": "IAM_ACCESS_APPROVAL",
  "eventId": "iga-approval-20261201-102",
  "traceId": "trace-access-8402",
  "requestId": "access-req-8402",
  "requestVersion": 4,
  "requesterSubjectId": "person-1042",
  "beneficiarySubjectId": "person-1042",
  "beneficiaryEngagementId": "EMP-5812",
  "approverSubjectId": "person-2088",
  "roleId": "finance-report-exporter",
  "targetSystem": "finance-portal",
  "scope": "business-unit-3",
  "policyVersion": "approval-policy-v7",
  "sodRuleIds": ["SOD-SELF-APPROVAL-001", "SOD-FINANCE-003"],
  "sodOutcome": "PASSED",
  "decision": "APPROVED",
  "decisionAt": "2026-12-01T02:00:00Z",
  "provisioningState": "PENDING"
}
~~~

Đây là **schema minh họa**, không phải phản hồi SCIM hoặc audit format chuẩn. `provisioningState=PENDING` nghĩa là **chưa chứng minh quyền đã cấp**, dù approval hợp lệ. Nên lưu thêm sự kiện provisioning và readback riêng.

### 27.1. Bảo mật và riêng tư

Không lưu mật khẩu, OTP, raw SAML response, access/refresh token, private key, session cookie hoặc toàn bộ hồ sơ HRIS vào audit/ticket. Lưu ID tham chiếu, timestamp, version, reason code và các metadata cần thiết; áp dụng phân quyền, bảo vệ tính toàn vẹn, retention và kiểm soát xuất dữ liệu.

### 27.2. Audit phải phân biệt ba sự thật

1. **Approval decision:** ai đã chấp thuận, có đúng thẩm quyền không?
2. **Provisioning action:** connector đã gửi và provider phản hồi thế nào?
3. **Effective access:** user/workload thực tế có hay không có quyền tại tài nguyên?

Ba sự thật có thể khác nhau do lỗi connector, nested group, direct role hoặc session/token stale.

## 28. Case study: xung đột tạo nhà cung cấp và duyệt thanh toán

**Bối cảnh giả định:** nhân viên An làm nhiệm vụ tạo hồ sơ nhà cung cấp, có role `vendor-creator` trong đơn vị A. An được đề cử làm người phê duyệt thanh toán trong cùng đơn vị do thiếu nhân sự.

### 28.1. Nếu chỉ duyệt theo manager

1. Manager xác nhận An cần hỗ trợ thanh toán.
2. Role `payment-approver` được cấp mà không kiểm SSD.
3. An giữ cả quyền tạo vendor và duyệt thanh toán.
4. Tổ chức tạo ra đường tự tạo bên nhận rồi chấp thuận khoản chi.

### 28.2. Thiết kế có SoD

| Bước | Kiểm soát |
| --- | --- |
| Nhận yêu cầu | Resolve đúng Person/Engagement, role, tenant và đơn vị A. |
| Đánh giá quyền hiện hành | Phát hiện An đã có `vendor-creator` trực tiếp hoặc gián tiếp. |
| SSD | Xác định xung đột trong cùng business unit. |
| Quyết định | Từ chối role mới, hoặc yêu cầu **thu hồi role cũ trước** nếu nhiệm vụ đã thay. |
| Nếu cần ngoại lệ | Chỉ owner đủ thẩm quyền, giới hạn thời gian/phạm vi và kiểm soát bù. |
| Provision | Thực hiện grant/revoke với điều kiện trạng thái vẫn hợp lệ. |
| Reconciliation | Kiểm quyền thực tế không đồng thời cho phép cả hai thao tác xung đột. |

### 28.3. Khi Mover

Nếu An chuyển hoàn toàn sang vị trí duyệt thanh toán, workflow cần **thu hồi vendor-creator trước hoặc trong kế hoạch thay đổi bảo đảm không có cửa sổ xung đột ngoài chính sách**. Chỉ thêm payment-approver rồi chờ kỳ review để bỏ role cũ là không đủ.

## 29. Case study: IAM administrator tự duyệt quyền đặc biệt

**Bối cảnh giả định:** một helpdesk operator có quyền tạo User ở IdP và sử dụng tài khoản quản trị phụ. Họ gửi yêu cầu cấp `identity-policy-admin` cho chính mình.

Các điểm rủi ro:

- Requester account khác approver account nhưng cùng Person.
- Role identity-policy-admin có thể sửa chính sách cấp quyền hoặc MFA.
- Operator có quyền sửa một phần approval routing.
- Connector cấp role theo flag approved do client gửi.

### 29.1. Phân tách đúng

1. **Identity linking** nhận diện requester và approver phụ là cùng chủ thể.
2. Workflow **từ chối self-approval** dựa Person/Engagement.
3. Approval authority được lấy từ Security/Identity Governance owner, không từ form request.
4. Role catalog có risk tier cao; yêu cầu kiểm SoD/step-up/expiry hoặc JIT.
5. Executor dùng principal riêng chỉ có quyền cập nhật role trong scope cho phép.
6. Trạng thái role được đọc lại ở IdP/PAM và kiểm session còn quyền.
7. Audit ghi cả account và canonical subject để phát hiện vượt kiểm soát qua tài khoản phụ.

**Bài học:** một thiết kế có nhiều tài khoản và nhiều bước không tự tạo độc lập nếu cùng một người có thể điều khiển tất cả.

## 30. Case study: Mover đổi manager khi approval đang chờ

**Bối cảnh giả định:** Bình làm việc trong Sales, yêu cầu quyền export báo cáo. Lúc nộp, manager là Mai. Sau đó Bình chuyển sang Finance và manager thành Hà trước khi Mai phê duyệt.

| Thời điểm giả định | Sự kiện | Quyết định cần kiểm |
| --- | --- | --- |
| **08:00** | Bình tạo yêu cầu export với scope Sales. | Request gắn department/role/manager hiện hành. |
| **09:00** | Manager Mai được giao approval. | Mai đang có thẩm quyền lúc giao. |
| **10:00** | HRIS phát Mover có hiệu lực ngay: Finance, manager Hà. | Scope Sales và manager cũ có thể không còn phù hợp. |
| **10:10** | Mai nhấn Approve từ link cũ. | Revalidate current authority; không tự chấp thuận. |
| **10:11** | Workflow từ chối quyết định cũ, yêu cầu đánh giá lại. | Ghi lý do và phiên bản HRIS. |
| **10:20** | Bình gửi hoặc cập nhật request theo nhiệm vụ Finance. | Role/owner/scope/SoD được kiểm mới. |
| **10:30** | Hà và data owner phù hợp duyệt theo policy. | Đủ người có thẩm quyền, không xung đột lợi ích. |
| **10:35** | Connector provision và hệ thống đối soát. | Không còn quyền Sales tồn dư hoặc local grant ngoài ý muốn. |

**Bài học:** SoD workflow phụ thuộc **thẩm quyền tại thời điểm ra quyết định**, không chỉ người đã được gán làm reviewer khi ticket mở. Mover có thể làm cả **phê duyệt cũ** lẫn **quyền mục tiêu cũ** mất hiệu lực.

## 31. Chỉ số đo chất lượng SoD và approval workflow

| Chỉ số | Cách đo gợi ý | Rủi ro phản ánh |
| --- | --- | --- |
| **Self-approval attempts blocked** | Lần cố phê duyệt cho chính Person/beneficiary bị chặn. | Nỗ lực hoặc lỗi cấu hình self-approval. |
| **SoD conflict detection coverage** | Role/entitlement xung đột được engine bao phủ ÷ toàn bộ loại quyền thuộc phạm vi. | Mức đầy đủ của policy. |
| **SSD violations open** | Các chủ thể đang đồng thời giữ quyền xung đột chưa xử lý. | Privilege creep và rủi ro gian lận. |
| **DSD/procedural SoD exceptions** | Vi phạm trong phiên/giao dịch có owner và quyết định. | Bỏ kiểm trong thực thi nghiệp vụ. |
| **Independent reviewer coverage** | Request rủi ro cao có reviewer độc lập hợp lệ ÷ tổng thuộc phạm vi. | Chất lượng maker-checker. |
| **Reviewer authority drift** | Request dùng owner/manager stale tại lúc decision. | Rủi ro Mover và delegation. |
| **Approval revalidation success** | Quyết định còn hợp lệ ở thời điểm execution ÷ số được thực thi. | Khả năng chống TOCTOU. |
| **Time to revoke conflict** | Từ phát hiện conflict tới xác minh quyền xung đột bị thu hồi. | Thời gian phơi lộ. |
| **Provisioning verification rate** | Quyết định Grant/Revoke có readback đúng ÷ tổng cần thực hiện. | Tránh ticket hoàn tất giả. |
| **Exceptions overdue** | Ngoại lệ SoD quá hạn, thiếu owner hoặc kiểm soát bù. | Nợ rủi ro. |
| **JML approval hygiene** | Joiner/Mover/Leaver khiến route/role được cập nhật đúng hạn. | Reviewer cũ hoặc grant sau Leaver. |
| **Credential/automation bypass findings** | Đường direct API/service principal có thể vượt workflow. | Quyền executor/secret quá rộng. |
| **Audit linkage completeness** | Request → approval → SoD check → provider → readback liên kết được. | Khả năng truy vết và giải trình. |

Không dùng duy nhất **số approval hoàn tất** làm KPI chất lượng. Một workflow duyệt rất nhanh nhưng cho phép self-approval hoặc không kiểm SoD khi thực thi có thể làm rủi ro cao hơn.

### 31.1. Phạm vi số liệu

Cần nêu rõ **ứng dụng, tenant, role, loại principal, khoảng thời gian, dữ liệu có thể quan sát và những đường cấp quyền ngoài workflow**. Không kết luận “0 vi phạm SoD” nếu chỉ kiểm nhóm IdP mà bỏ qua app-local roles, cloud IAM hoặc PAM.

## 32. Sai lầm thường gặp khi triển khai

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| **Kiểm self-approval bằng account ID** | Cùng Person dùng hai account để tự duyệt. | So sánh canonical subject/Person và quyền điều khiển. |
| **Cho requester tự điền approver bất kỳ** | Chọn người dễ đồng ý hoặc chính tài khoản phụ. | Resolve reviewer từ owner/manager policy có thẩm quyền. |
| **Tin trường approved từ client** | Bypass approval API. | Quyết định server-side gắn request/version và actor. |
| **Chỉ kiểm SSD khi tạo request** | Quyền xung đột xuất hiện trước execution. | Revalidation và concurrency control. |
| **Không tính nested groups/local roles** | Bỏ sót effective conflict. | Inventory và effective entitlement reconciliation. |
| **Nhiều bước nhưng cùng người duyệt** | Four-eyes giả. | Xác minh độc lập theo Person/authority. |
| **Escalation tự động APPROVE khi quá hạn** | Cấp quyền rủi ro cao do vắng reviewer. | Escalation sang người đủ thẩm quyền, không tự đồng ý. |
| **MFA thành công được coi là approve authorization** | Người có thể đăng nhập nhưng không đủ quyền duyệt. | Kiểm authorization của decision endpoint. |
| **Thay manager nhưng không cập nhật pending approvals** | Manager cũ duyệt request không còn phù hợp. | Route revalidation theo JML. |
| **Cấp role mới khi Mover mà giữ role cũ** | Tổ hợp quyền xung đột. | Grant/revoke delta và kiểm effective roles. |
| **Chỉ disable IdP khi Leaver** | Session, token hoặc quyền local vẫn hoạt động. | Deprovision đa đích và xác minh. |
| **Retry grant cũ sau Leaver** | Tái cấp quyền cho người nghỉ. | Source state/version check trước execution. |
| **Connector có quyền tự duyệt** | Service principal vượt SoD và tạo quyền tùy ý. | Tách decision/provisioning với least privilege. |
| **Ngoại lệ không expiry** | Xung đột SoD kéo dài vô hạn. | Exception có owner/approval/TTL và review. |
| **Đóng ticket sau SCIM 200/204** | Local role hoặc session có thể còn sai. | Readback và kiểm effective access. |
| **Log raw token/password để debug** | Lộ credential, tạo đường truy cập mới. | Lưu trace/reference, che bí mật. |

## 33. Checklist thiết kế và vận hành Separation of duties

1. Đã phân biệt **SoD, SSD, DSD, procedural SoD, four-eyes và dual control** chưa?
2. Có xác định các cặp trách nhiệm **requester, beneficiary, approver, executor, verifier** xung đột không?
3. Self-approval có được kiểm theo **canonical Person/subject**, thay vì chỉ email hoặc account ID không?
4. Với workload/service accounts, có xác định **owner và quyền điều khiển principal** không?
5. Có catalog **role/permission/risk tier, scope, role owner và approval policy** đáng tin cậy không?
6. Ma trận SSD/DSD có xác định **same tenant, business unit, resource hoặc transaction** khi cần không?
7. Có tính **effective entitlements** qua direct role, nested/dynamic group, hierarchy, local grant và PAM eligibility không?
8. Có xét quyền **sửa policy, cấp role, assume role và quản lý credential** như đường nâng đặc quyền không?
9. Reviewer có **đúng authority** đối với role/resource/tenant và không hưởng lợi trái policy không?
10. Có bảo vệ approval API khỏi request giả `approved=true` và không tin client tự khai approver không?
11. Có áp dụng **step-up MFA/JIT/PAM** phù hợp cho request và quyền rủi ro cao không?
12. Delegation có scope/TTL/owner/revocation, không cho delegate duyệt request của chính họ không?
13. Khi reviewer vắng mặt, có escalation tới người độc lập đủ thẩm quyền thay vì auto-approve không?
14. Khi **Joiner**, có tách xác minh danh tính, cấp baseline và approval đặc quyền không?
15. Khi **Mover**, có cập nhật manager/reviewer, revalidate pending request và **thu hồi quyền cũ** không?
16. Khi **Leaver**, có hủy request pending, thu hồi role/privilege và không giữ account reviewer cũ hoạt động không?
17. Khi rehire, có xét **engagement mới** và không tự khôi phục approval/role cũ không?
18. Có tái đánh giá SoD **ở lúc request, lúc decision và trước provisioning** để chống TOCTOU không?
19. Có xử lý concurrency, duplicate event, retry, expired decision và stale request version không?
20. Connector SCIM/API có **least privilege** và không có quyền tự thay trạng thái approval không?
21. Có phân biệt **approved, provisioned, verified** và kiểm actual tại ứng dụng/API không?
22. Có xử lý token/phiên/credential ngoài SSO khi quyền bị thu hồi không?
23. Exception/break-glass có **owner độc lập, reason, risk, compensating controls, expiry và hậu kiểm** không?
24. Có lưu audit request/decision/SoD/execution/verification với **ID, version và timestamp** mà không lộ bí mật không?
25. Có KPI về **self-approval blocked, SoD conflicts, authority drift, revoke latency, exception aging và verification coverage** không?
26. Khi scope không thể kiểm tra đầy đủ, có công bố **giới hạn quan sát và rủi ro tồn dư** thay vì khẳng định an toàn tuyệt đối không?

**Ghi nhớ:** **Separation of duties trong approval workflow bảo đảm không một chủ thể hoặc nhóm lợi ích có thể tự khởi tạo, tự phê duyệt, tự cấp và tự hợp thức hóa quyền nhạy cảm**. SoD phải kiểm ở **cấp Person/Engagement và quyền hiệu lực**, kết hợp **SSD, DSD, maker-checker, reviewer độc lập, role catalog, SoD matrix và revalidation theo thời điểm**. Trong **Joiner–Mover–Leaver**, thay đổi chủ thể, manager hoặc quyền có thể làm phê duyệt cũ mất hiệu lực; hệ thống cần thu hồi quyền không còn phù hợp, ngăn retry cũ tái cấp quyền và **đối soát trạng thái thực tế qua IdP, SSO, SCIM, PAM, RBAC/ABAC và ứng dụng**. Giá trị của approval workflow không nằm ở số lượt bấm Approve mà ở **quyền được cấp đúng thẩm quyền, xung đột được ngăn chặn và bằng chứng kiểm toán đáng tin cậy**.
