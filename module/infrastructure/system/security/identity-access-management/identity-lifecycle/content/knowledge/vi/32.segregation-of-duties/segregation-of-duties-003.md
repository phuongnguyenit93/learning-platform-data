# Toxic combination: tổ hợp quyền xung đột trong Segregation of Duties (SoD)

> **Chương: Segregation of duties.** **Toxic combination** (tổ hợp quyền độc hại/xung đột) là sự kết hợp các quyền, vai trò, năng lực hoặc nhiệm vụ mà khi cùng được trao hay cùng được thực hiện bởi một chủ thể, trong **phạm vi và bối cảnh liên quan**, sẽ tạo ra rủi ro không chấp nhận được như tự phê duyệt, gian lận, thay đổi dữ liệu mà không bị kiểm tra hoặc vượt qua biện pháp bảo vệ. Đây là vấn đề trọng tâm của **Segregation of Duties (SoD)**: phân tách nhiệm vụ có xung đột để không một cá nhân hoặc chuỗi đặc quyền thiếu kiểm soát nào có thể vừa khởi tạo, vừa chấp thuận, vừa hoàn tất hoặc che giấu một giao dịch nhạy cảm. Trong **IAM Identity Lifecycle**, tổ hợp độc hại có thể xuất hiện khi Joiner được cấp sai nhóm quyền, Mover tích lũy quyền cũ và mới, hoặc sau Leaver quyền cũ tồn dư trong IdP, SSO, SCIM, ứng dụng, PAM và tài khoản dịch vụ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **toxic combination** và phân biệt với một quyền nhạy cảm đơn lẻ, sự chồng lấn role, và **SoD violation** đã xảy ra trên một giao dịch cụ thể.
2. Phân biệt **Static SoD (SSoD)**, **Dynamic SoD (DSoD)**, quy tắc theo phiên/giao dịch và các tổ hợp gồm hai hoặc nhiều năng lực.
3. Nhận diện toxic combination theo **subject, action, resource, tenant, amount, thời điểm, quan hệ nghiệp vụ và đường kế thừa quyền**.
4. Thiết kế **SoD conflict matrix/rule catalog** và mô hình phát hiện **effective permissions** thay vì chỉ dựa vào tên role.
5. Áp dụng kiểm soát **preventive, detective, corrective và compensating**, quy trình ngoại lệ, phê duyệt độc lập, JIT/PAM và audit.
6. Liên hệ SoD với **Joiner–Mover–Leaver, HR/IGA, IdP/SSO, SCIM, RBAC/ABAC/PBAC**, service identities và tài khoản đặc quyền.
7. Thiết kế test dương/âm, kiểm thử xung đột xuyên ứng dụng, xử lý cache/event đến muộn và đối soát quyền còn hiệu lực.

## 1. Tình huống dẫn nhập: một người vừa tạo vừa chi tiền

Một doanh nghiệp phân tách quy trình thanh toán thành ba nhiệm vụ:

- **VendorMasterEditor**: tạo và sửa thông tin nhà cung cấp, gồm tài khoản ngân hàng nhận tiền.
- **InvoiceApprover**: phê duyệt hóa đơn và xác nhận nghĩa vụ thanh toán.
- **PaymentReleaser**: phát lệnh chi tiền sau khi đủ điều kiện kiểm soát.

Nếu Minh được cả ba quyền và có thể sử dụng trên **cùng pháp nhân/cùng phạm vi chi trả**, Minh có thể tự tạo một nhà cung cấp không có thật, xác nhận hóa đơn và chuyển tiền mà không cần người độc lập kiểm soát.

| Chủ thể | Quyền thực tế | Phạm vi | Nhận định ban đầu |
| --- | --- | --- | --- |
| Lan | Tạo đề nghị thanh toán, không được duyệt/chuyển tiền | Tenant B | Không có tổ hợp xung đột đã định. |
| Minh | Sửa tài khoản ngân hàng nhà cung cấp + phát lệnh thanh toán | Tenant B | **Toxic combination tiềm năng** nếu thiếu chốt độc lập. |
| Chi | Duyệt hóa đơn tenant A + phát thanh toán tenant B | Hai tenant không có quan hệ | **Không kết luận chỉ từ tên role**; cần xem có khả năng vượt tenant hay không. |
| Hùng | Tạo và duyệt nhưng hệ thống cấm tự duyệt hóa đơn do mình tạo | Cùng tenant, DSoD tại giao dịch | Có role overlap; rủi ro được giảm bằng kiểm tra runtime nếu thực thi đúng. |
| service-payments | Đọc danh sách khoản đã duyệt và gửi lệnh thanh toán | Scope chỉ những khoản đã có chữ ký/approval hợp lệ | Rủi ro tùy trust, quyền override và khả năng tự tạo phê duyệt. |

**Lưu ý:** “Toxic” là **nhãn đánh giá rủi ro do tổ chức định nghĩa**; không có bảng cặp role độc hại chung cho mọi hệ thống. Kết luận cần tính **khả năng thực hiện hành động thực tế, phạm vi tài nguyên, quan hệ giao dịch, giá trị giao dịch và các kiểm soát đang vận hành**.

## 2. Các thuật ngữ cần phân biệt

| Thuật ngữ | Nội dung | Ví dụ |
| --- | --- | --- |
| **Segregation of Duties (SoD)** | Nguyên tắc phân tách những trách nhiệm có xung đột. | Người tạo khoản thanh toán không tự duyệt khoản đó. |
| **Toxic combination** | Kết hợp khả năng có thể dẫn tới rủi ro không chấp nhận được. | Đổi tài khoản ngân hàng người nhận + phát thanh toán. |
| **Conflicting entitlement** | Hai hoặc nhiều entitlement tạo vùng xung đột theo policy. | vendor.bankAccount.write + payment.release. |
| **Static SoD (SSoD)** | Ngăn một chủ thể được gán **đồng thời** các role/permission xung đột trong phạm vi chính sách. | Không ai được giữ cùng lúc PaymentCreator và PaymentApprover nếu policy cấm. |
| **Dynamic SoD (DSoD)** | Có thể giữ các role nhưng **không được kết hợp sử dụng** trong cùng phiên/giao dịch/bối cảnh bị cấm. | Người tạo hóa đơn không được duyệt chính hóa đơn đó. |
| **SoD rule/constraint** | Quy tắc mô tả tập quyền, phạm vi, điều kiện và hành vi khi vi phạm. | DENY invoice.approve nếu createdBy = subject. |
| **SoD conflict** | Một yêu cầu cấp/đang giữ quyền phù hợp điều kiện xung đột. | Request mới tạo cặp quyền bị cấm. |
| **SoD violation** | Trạng thái hoặc hành vi thực tế vi phạm ràng buộc SoD. | Người tự duyệt hóa đơn dù bị cấm. |
| **Mitigating/compensating control** | Kiểm soát khác giúp giảm rủi ro khi không thể tách nhiệm vụ hoàn toàn. | Hậu kiểm độc lập, giới hạn giá trị, dual authorization. |
| **Residual access** | Quyền vẫn còn hiệu lực sau thời điểm phải thu hồi. | Role cũ sau Mover còn trong SaaS local account. |

Một role **GlobalAdmin** có thể nguy hiểm ngay cả khi chưa ghép với quyền khác. Đó là **excessive privilege** hoặc quyền đặc quyền quá rộng; khi GlobalAdmin có khả năng tự cấp một phần của cặp xung đột, ta còn phải đánh giá **đường tăng quyền gián tiếp**.

### Tổ hợp toxic không nhất thiết là một cặp

Một quy tắc có thể yêu cầu **ba khả năng cùng hiện diện**:

~~~text
Toxic set T1:
    { vendor.create, invoice.approve, payment.release }

Toxic set T2:
    { iam.grantRole, iam.approveRoleRequest }

Toxic set T3:
    { production.deploy, audit.disable, audit.logDelete }
~~~

Đôi khi chỉ hai quyền đã đủ gây rủi ro; đôi khi **cả ba** mới hình thành chuỗi gian lận. Không nên cố biến mọi quy tắc thành cặp nếu điều đó dẫn tới **false positive** hoặc bỏ sót tổ hợp nhiều bước.

## 3. Quy trình nghiệp vụ và ranh giới tin cậy

SoD bắt nguồn từ **rủi ro trong quy trình**, không chỉ từ cách đặt tên role trong ứng dụng. Trước khi xây rule, cần mô hình hóa những nhiệm vụ mà một chủ thể **không được độc lập kiểm soát toàn bộ**.

### Ví dụ procure-to-pay

~~~mermaid
flowchart LR
    V["Tạo/sửa Vendor"] --> I["Tạo Invoice"]
    I --> A["Duyệt Invoice"]
    A --> P["Phát lệnh Payment"]
    P --> B["Đối soát sao kê"]
    G["SoD policy & independent checks"] -.-> V
    G -.-> A
    G -.-> P
    G -.-> B
~~~

Các điểm kiểm soát có thể gồm:

1. Người tạo/sửa người nhận tiền không được tự release khoản chi tới người nhận ấy.
2. Người tạo hóa đơn không được tự phê duyệt chính hóa đơn.
3. Người release payment không được tự xóa/chỉnh bằng chứng đối soát và audit.
4. Người phê duyệt phải có authority phù hợp tenant, cost center và hạn mức.
5. Thay đổi ngân hàng nhà cung cấp có thể cần xác minh độc lập trước khi khoản chi đầu tiên được gửi.

### Các miền nghiệp vụ khác

| Miền | Khả năng A | Khả năng B hoặc C | Rủi ro |
| --- | --- | --- | --- |
| **Finance** | Tạo/sửa vendor | Phát thanh toán | Chi tiền tới tài khoản sai/giả. |
| **Payroll** | Sửa bảng lương hoặc tài khoản nhận lương | Phê duyệt/chạy payroll | Tự điều chỉnh chi trả. |
| **IAM/IGA** | Tạo yêu cầu cấp GlobalAdmin | Tự phê duyệt và thực thi cấp quyền | Leo thang đặc quyền không độc lập. |
| **HR/IAM** | Sửa trạng thái HR hoặc manager | Tự duyệt quyền dựa trên dữ liệu ấy | Tự tạo căn cứ cấp quyền. |
| **Cloud/Security** | Thay firewall/production policy | Tắt/xóa audit | Che giấu thay đổi nguy hiểm. |
| **CI/CD** | Sửa mã ứng dụng | Tự duyệt merge và deploy production | Đưa thay đổi chưa kiểm soát vào sản xuất. |
| **Data governance** | Cấp quyền export dữ liệu | Tự thực hiện export hoặc xóa audit | Tăng nguy cơ xuất dữ liệu trái phép. |
| **Database** | Thay dữ liệu giao dịch | Xóa log hoặc tự xác nhận đối soát | Giấu thay đổi không hợp lệ. |
| **Secrets** | Rotate/tạo privileged credential | Thay policy cho phép sử dụng credential đó | Tự mở đường truy cập không kiểm soát. |

**Tổ hợp chỉ có ý nghĩa khi cùng khả năng kiểm soát quy trình/tài nguyên.** Người tạo hóa đơn tenant A và người phê duyệt tenant B có thể không xung đột nếu ranh giới tenant được thực thi hoàn toàn; nhưng role cloud có thể assume sang cả hai tenant khiến ranh giới trên giấy không còn hiệu lực.

## 4. Static SoD: cấm gán đồng thời quyền xung đột

**Static SoD (SSoD)** áp một ràng buộc ở **thời điểm cấp quyền hoặc trạng thái quyền được giữ**, ví dụ không cho cùng một người được gán cả VendorBankAccountEditor và PaymentReleaser trong một pháp nhân.

### Ví dụ quy tắc

~~~text
RULE SSoD-FIN-01
scope:
    legalEntity = LE-B
forbiddenCombination:
    { vendor.bankAccount.write, payment.release }
effect:
    BLOCK_NEW_GRANT
resolution:
    revoke conflicting old grant OR reject requested grant
~~~

Trước khi gán role mới, IAM/IGA tính **effective entitlements hiện hành** rồi kiểm tra nếu thêm role đó sẽ tạo tập xung đột:

~~~text
current = { vendor.bankAccount.write, report.read }
requested = { payment.release }

after = current UNION requested

if forbiddenCombination subsetOf after
   and resourceScopeOverlaps:
    DENY_OR_REQUIRE_CONTROLLED_EXCEPTION
~~~

**SSoD không tự ngăn hành động ngoài IAM** nếu một ứng dụng vẫn còn direct role, local admin hoặc phiên/token lỗi thời. Cần đối soát **observed/effective access** ở hệ thống đích.

### Khi nào SSoD phù hợp?

- Hai nhiệm vụ không bao giờ nên được người này cùng giữ trong cùng đơn vị.
- Hành động quá nguy hiểm để phụ thuộc hoàn toàn vào điều kiện runtime.
- Dữ liệu tác nghiệp không đủ để bảo đảm kiểm tra từng giao dịch.
- Có nhiều API/path khó quan sát; ngăn cấp quyền sớm là lớp phòng vệ đầu.

**Nhược điểm:** SSoD quá cứng có thể chặn người hợp lệ ở các **tenant, dự án hoặc pháp nhân khác nhau** dù không có vùng quyền giao nhau. Vì thế quy tắc nên có phạm vi rõ, không chỉ đối chiếu hai role name bất kể resource.

## 5. Dynamic SoD: một chủ thể có role nhưng không được tự hoàn tất giao dịch

**Dynamic SoD (DSoD)** thường xét **ai đã thực hiện bước trước trên cùng một đối tượng giao dịch**, phiên nào đang kích hoạt role nào và điều kiện bối cảnh.

### Ví dụ hóa đơn

~~~text
PERMIT invoice.approve KHI
    subject.hasPermission("invoice.approve")
    AND subject.lifecycleStatus == ACTIVE
    AND invoice.tenantId in subject.approvedTenants
    AND invoice.status == PENDING_APPROVAL
    AND invoice.createdByIdentityId != subject.identityId
    AND invoice.amount <= subject.approvalLimit

ELSE:
    DO_NOT_PERFORM_APPROVAL
~~~

Lan có thể tạo hóa đơn A và phê duyệt hóa đơn B do người khác tạo, nếu policy nghiệp vụ cho phép; nhưng không được duyệt **chính hóa đơn A**. Đây là DSoD theo giao dịch, không phải cấm Lan giữ hai role trong mọi hoàn cảnh.

### DSoD theo phiên

Một số hệ thống có thể cho phép một người đủ điều kiện nhiều role nhưng **chỉ kích hoạt một role trong phiên quản trị nhất định**, hoặc yêu cầu chuyển ngữ cảnh và phê duyệt độc lập trước khi làm bước tiếp theo. Điều này cần được cưỡng chế tại **PEP/PDP và phiên mục tiêu**, không chỉ bằng cách tắt nút trên giao diện.

### Phải kiểm tra danh tính, không chỉ username

~~~text
createdBy:
    SaaS user = finance-user-88
    IAM identity = IAM:ID-LAN-2041

approver:
    privileged SaaS user = admin-lan
    IAM identity = IAM:ID-LAN-2041

Kết luận: cùng một người.
~~~

SoD phải so bằng **identity correlation đáng tin**. Nếu chỉ so local username hoặc email, người dùng có thể duyệt qua account thứ hai và vượt DSoD.

## 6. Toxic combination theo cặp, nhóm và đồ thị quyền

### Ma trận xung đột đơn giản

| Quyền A | Quyền B | Ràng buộc | Lý do |
| --- | --- | --- | --- |
| VendorBankEditor | PaymentReleaser | Cùng legal entity và khả năng dùng cùng vendor. | Tránh tự đổi người nhận rồi chi tiền. |
| InvoiceCreator | InvoiceApprover | Cùng invoice, createdBy=approver. | Tránh tự duyệt giao dịch. |
| UserRoleRequester | UserRoleApprover | Cùng request và beneficiary. | Tránh tự phê duyệt quyền. |
| PayrollEditor | PayrollRunner | Cùng payroll cycle/company. | Tránh tự chỉnh rồi thanh toán. |
| ProductionDeployer | AuditDisable | Cùng production environment. | Tránh thay production và che giấu chứng cứ. |
| AccessPolicyEditor | AccessPolicyApprover | Cùng policy change. | Tránh tự thông qua policy cấp quyền rộng. |

Đây là **ma trận minh họa** cho bài học, không phải chuẩn áp dụng sẵn. Một tổ chức cần định nghĩa mức độ rủi ro, mô hình kiểm soát và exception theo quy trình của mình.

### Hyperedge: ba năng lực tạo xung đột

Nếu một giao dịch chỉ không an toàn khi một người giữ **cả A, B và C**, mô hình đôi quyền có thể báo động quá mức:

~~~text
Toxic set:
    { vendor.create, invoice.approve, payment.release }

Người X có vendor.create + invoice.approve:
    chưa chắc vi phạm toxic set ba quyền này.

Người X có cả ba trong cùng legalEntity:
    tạo conflict theo chính sách.
~~~

Có thể biểu diễn bằng **hypergraph**: mỗi nút là capability và một hyperedge là tập capability tạo xung đột. Ngoài ra, cần **predicate về scope, thời điểm và quan hệ giao dịch**; đồ thị không thể thay thế kiểm tra điều kiện nghiệp vụ.

### Access-path graph giúp tìm quyền gián tiếp

~~~mermaid
flowchart TD
    H["Human IAM identity"] --> G1["FinanceOperations Group"]
    H --> G2["ProductionSupport Group"]
    G1 --> R1["VendorBankEditor role"]
    G2 --> R2["PaymentReleaser role"]
    R1 --> V["vendor.bankAccount.write"]
    R2 --> P["payment.release"]
    H --> I["Cloud role: iam.policy.write"]
    I --> E["Có thể tự cấp role khác"]
    V --> C["SoD evaluation theo scope"]
    P --> C
    E --> C
~~~

Người dùng không nhất thiết được gán hai role trực tiếp; một quyền có thể đến từ **Group lồng nhau**, role kế thừa, delegated role hoặc quyền có thể tự gán role cho bản thân. Kiểm tra SoD cần xét **khả năng thực tế trong phạm vi policy**, không chỉ tên role được hiển thị ở màn hình User.

## 7. Phân biệt direct grant, role hiệu lực và hành động thực tế

| Lớp dữ liệu | Câu hỏi | Giới hạn |
| --- | --- | --- |
| **Requested access** | Người dùng đang xin thêm quyền gì? | Chưa chắc được duyệt. |
| **Approved access** | Có quyền nào đã được phê duyệt đúng scope/time? | Chưa chắc được provision. |
| **Provisioned/observed grant** | Hệ thống đích đang báo account/role/Group nào? | Có thể bỏ sót local ACL/token hoặc quyền từ policy động. |
| **Effective access** | Action nào thực sự được ứng dụng/resource cho phép? | Phụ thuộc context, tenant, policy, session và freshness. |
| **Executed action** | Chủ thể đã làm bước giao dịch nào? | Cần audit/transaction history chính xác cho DSoD. |

Ví dụ Minh không còn Group PaymentReleasers ở IdP sau Mover, nhưng một **app-local role** vẫn cho payment.release. SoD evaluation chỉ dựa trên IdP có thể báo không conflict, trong khi quyền thực tế vẫn toxic.

**Một vai trò đơn lẻ có thể chứa nhiều capability toxic.** Nếu role FinanceSuperUser bao gồm vendor.bankAccount.write và payment.release, việc kiểm tra “User có đồng thời hai role?” sẽ bỏ sót xung đột **nội tại role**. Cần phân rã role ra action/permission hiệu lực.

### Các cấp độ kết luận

- **Potential conflict:** tổ hợp quyền được gán và có vẻ giao nhau theo policy.
- **Confirmed access conflict:** dữ liệu đáng tin chứng minh chủ thể có thể dùng đồng thời các capability xung đột trong phạm vi liên quan.
- **Runtime SoD violation:** một hành động bị cấm đã thực sự được thực hiện trên giao dịch hoặc resource.
- **Unknown/incomplete:** chưa thể chứng minh không có xung đột vì thiếu Group, role, identity mapping hoặc quyền tại ứng dụng.

Phân biệt những cấp này giúp tránh vừa **false positive** vừa **false assurance**.

## 8. Thiết kế rule catalog cho toxic combination

Một rule nên được ghi thành hiện vật có owner, mô tả rủi ro, phạm vi và cách kiểm soát.

| Field | Mục đích |
| --- | --- |
| ruleId, version, owner | Định danh và quản lý thay đổi. |
| businessProcess | Procure-to-pay, payroll, IAM, CI/CD… |
| severity/riskTier | Ưu tiên xử lý theo ảnh hưởng và khả năng xảy ra. |
| conflictMode | STATIC, DYNAMIC, SESSION, TRANSACTION hoặc kết hợp. |
| forbiddenCapabilities | Tập action/permission tạo xung đột. |
| resource/tenant/legalEntity scope | Xác định điều kiện giao nhau. |
| relationPredicate | Ví dụ invoice.createdBy = subject.identityId. |
| applicability/effectiveAt | Điều kiện và thời gian rule có hiệu lực. |
| enforcement | Chặn grant, chặn action, yêu cầu approver độc lập… |
| compensatingControl | Những biện pháp giảm rủi ro có điều kiện. |
| exceptionPolicy | Ai được duyệt, scope, endAt, bằng chứng. |
| evidenceRequired | Danh mục dữ liệu và kiểm thử để kết luận. |

### YAML minh họa quy tắc SSoD

**Định dạng tự đặt cho bài học**, không phải schema chuẩn SoD, SCIM, XACML hay Cedar:

~~~yaml
ruleId: SOD-PAY-001
version: 4
owner: FinanceControl
mode: STATIC
riskTier: HIGH
businessProcess: procure-to-pay
forbiddenCapabilities:
  - vendor.bankAccount.write
  - payment.release
scope:
  sameLegalEntity: true
  overlappingResourceRights: true
effect: BLOCK_NEW_GRANT
exception:
  allowed: true
  requiresIndependentSecurityAndFinanceApproval: true
  maxDurationHours: 8
  requiresCompensatingControls: true
evidence:
  - trustedIdentityMapping
  - effectiveGrants
  - resourceScope
  - approvalAndException
~~~

### Quy tắc DSoD theo giao dịch

~~~yaml
ruleId: SOD-INVOICE-002
version: 3
owner: AccountsPayable
mode: DYNAMIC
action: invoice.approve
resourceType: INVOICE
denyWhen:
  - approverIdentityIdEqualsCreatedByIdentityId
  - approvalAmountExceedsApproverLimit
require:
  - currentIdentityIsActive
  - authorityCoversInvoiceTenant
  - invoiceIsPendingApproval
  - trustedTransactionHistory
~~~

**Lưu ý:** Ví dụ DSoD gồm cả điều kiện quyền nghiệp vụ; một policy engine thực tế cần xác định rõ **ngữ nghĩa boolean**, dữ liệu thiếu và handling để không biến lỗi PIP thành Permit.

## 9. Phát hiện tổ hợp toxic khi có nhiều nguồn dữ liệu

Một bộ phân tích SoD thường phải ghép dữ liệu từ nhiều nơi:

| Nguồn | Thuộc tính cung cấp | Rủi ro nếu bỏ sót |
| --- | --- | --- |
| **HR/contract** | identity, department, manager, trạng thái JML, endAt. | Dùng quyền theo công việc cũ hoặc account người đã nghỉ. |
| **IAM/IGA** | Desired entitlements, approval, role catalog, exception. | Chỉ biết quyền dự kiến, không thấy quyền ở đích. |
| **IdP/directory** | Group, app assignments, trạng thái sign-in. | Group token/cookie lỗi thời, local role ngoài IdP. |
| **SCIM** | User/Group provisioning, local IDs và membership nếu hỗ trợ. | Không có mọi ACL/role hoặc session/token ở ứng dụng. |
| **Application API** | Direct grants, resource roles, transaction creators/approvers. | Phân tích chỉ từ role directory có thể sai. |
| **Cloud IAM/PAM** | Trust, role assumption, privileged eligibility/session. | Đường self-escalation và JIT bị bỏ qua. |
| **Audit/transaction store** | Ai tạo/duyệt/thực hiện từng giao dịch. | Không kiểm được Dynamic SoD. |
| **Service registry** | Owner, workload identity, environment, scope. | Bot không owner có thể kết hợp quyền nhạy cảm. |

### Quy trình xác định principal

~~~text
HR person      = HRIS:EMP-2041
IAM identity   = IAM:ID-2041
IdP account    = issuer-a / sub-88
Finance user   = tenant-b / scim-user-901
Admin account  = cloud-b / admin-2041
~~~

Không gộp theo email duy nhất hoặc displayName. SoD phải tính **các account liên quan cùng một người** ở đúng namespace/tenant; với workload, phải xác định danh tính máy, owner và quyền service riêng, tránh đồng nhất một người sở hữu bot với mọi action của bot.

### Đọc đủ Group/ACL và inherited paths

Một nguồn API có phân trang, nested Group hoặc role inheritance. Nếu chỉ đọc trang đầu, hoặc connector không có quyền xem admin grants, kết quả “không conflict” là **không đáng tin**. Ghi **snapshot completeness, sourceVersion, observedAt, policyVersion** và các nguồn chưa thể kiểm.

## 10. Scope và bối cảnh giúp giảm false positive

Toxic combination không thể đánh giá chính xác chỉ bằng hai role name.

### Theo tenant và pháp nhân

~~~text
User X:
    VendorEditor tenant-A
    PaymentReleaser tenant-B

Nếu policy cấm tổ hợp trên cùng tenant/pháp nhân:
    chưa kết luận toxic nếu quyền không giao nhau.

Nhưng nếu User X có quyền cross-tenant admin hoặc assume role:
    cần kiểm tra effective tenant scope; có thể vẫn toxic.
~~~

### Theo amount và level of authority

Một nhân viên có thể được phép chuẩn bị và phê duyệt giao dịch giá trị nhỏ nhưng không được tự phê duyệt giao dịch vượt hạn mức. Hạn mức là một **điều kiện ABAC**, không phải bằng chứng mọi tổ hợp ở mức thấp luôn an toàn.

### Theo chính đối tượng giao dịch

- Tạo invoice A và duyệt invoice B không nhất thiết vi phạm DSoD.
- Tạo invoice A rồi duyệt chính invoice A thường là DSoD conflict khi policy cấm.
- Thay tài khoản ngân hàng vendor X và release payment cho vendor Y có thể có rủi ro khác với cùng vendor X.
- Quyền đọc một repository ít nhạy cảm khác với quyền thay production code và disable logging.

### Theo thời gian

Nếu User giữ vai trò A trong tháng 11 và vai trò B từ tháng 12, có thể không có **SSoD đồng thời**, nhưng nếu session/token/grant A chưa thu hồi thì **effective overlap** vẫn tồn tại. Với giao dịch kéo dài, lịch sử creator/approver có thể cần kiểm cả người từng giữ vai trò, không chỉ role hiện tại.

### Hệ thống phải giải thích quyết định

Một cảnh báo tốt cho reviewer:

~~~text
Rule: SOD-PAY-001 v4
Subject: IAM:ID-MINH-88
Capability A: vendor.bankAccount.write
    via SaaS direct role VendorEditor / legalEntity LE-B
Capability B: payment.release
    via IdP Group PaymentOperators / legalEntity LE-B
Scope intersection: LE-B
Status: POTENTIAL/CONFIRMED based on verified access paths
Owner: FinanceControl
Next step: remove grant B or initiate controlled exception
~~~

Một cảnh báo chỉ ghi “Toxic: TRUE” mà không nêu rule, scope, access path và dữ liệu nguồn sẽ khó để người chịu trách nhiệm ra quyết định.

## 11. Kiểm soát Preventive, Detective, Corrective và Compensating

| Nhóm | Thời điểm | Ví dụ | Điều cần chứng minh |
| --- | --- | --- | --- |
| **Preventive** | Trước hoặc ngay tại thời điểm cấp/dùng quyền. | IGA chặn grant tạo SSoD; API chặn tự duyệt invoice. | Quy tắc bao phủ đúng các đường cấp và PEP. |
| **Detective** | Quan sát trạng thái hoặc hành động. | Quét role xung đột, kiểm tra event người tạo cũng duyệt. | Snapshot đầy đủ và phát hiện đúng giao dịch. |
| **Corrective** | Sau khi phát hiện vi phạm. | Revoke entitlement, khóa phiên, sửa role mapping. | Readback và xác minh mất quyền thực tế. |
| **Compensating** | Khi không thể tách nhiệm vụ hoàn toàn. | Phê duyệt độc lập, giám sát tăng cường, giới hạn hạn mức, hậu kiểm. | Kiểm soát độc lập, vận hành thật và được chấp thuận. |

Một kiểm soát **detective** không tự ngăn gian lận đã xảy ra; một kiểm soát **preventive** trong IGA không tự chặn quyền app-local được cấp thủ công. Thiết kế nên phối hợp nhiều lớp theo rủi ro.

### Three-lines-of-defense theo trách nhiệm thực tế

- **Business process owner** xác định nhiệm vụ nào tạo gian lận hoặc sai lệch nghiêm trọng.
- **IAM/IGA và Security** diễn đạt rule, nguồn quyền, authority, approval, theo dõi exception.
- **Application/platform owner** thực thi kiểm tra tại API và tài nguyên thực.
- **Audit/compliance** đánh giá tính độc lập, bằng chứng và hiệu quả kiểm soát.

Tên bộ phận và mô hình trách nhiệm thay đổi theo tổ chức; điều cốt lõi là **không để một chủ thể vừa đặt rule, vừa tự bỏ rule, vừa tự xác nhận tuân thủ** mà thiếu giám sát.

## 12. Ngăn toxic combination khi cấp quyền và approval

Một yêu cầu quyền phải được kiểm tra trước khi tác vụ provisioning chạy.

~~~mermaid
flowchart TD
    R["Access request / Joiner / Mover"] --> I["Resolve identity, scope,<br/>existing effective grants"]
    I --> C["Simulate after-grant capabilities"]
    C --> E{"Có toxic combination<br/>trong resource scope?"}
    E -->|Không| A["Approval theo policy<br/>và lifecycle"]
    E -->|Có| D["BLOCK / REVIEW<br/>không auto-grant"]
    D --> M["Loại quyền cũ, giảm scope<br/>hoặc exception được duyệt"]
    M --> C
    A --> P["Provision via đúng connector"]
    P --> V["Readback + effective access check"]
    V --> O["Audit / Reconciliation"]
~~~

### Ba kiểm soát quan trọng tại access request

1. **Simulation:** tính trạng thái quyền sau khi cộng entitlement mới; kiểm các role và access path đã có, kể cả quyền gián tiếp.
2. **Approval authority:** nếu có xung đột, người hưởng quyền không được tự duyệt ngoại lệ; đối chiếu **IAM identity**, không chỉ username.
3. **Revalidation trước provisioning:** nếu người dùng bị Mover/Leaver hoặc quyền khác được cấp trong thời gian chờ, đánh giá lại toxic combination theo **trạng thái mới nhất**.

### Multi-stage approval không bảo đảm SoD nếu người duyệt trùng

~~~text
Required approvals:
    Manager AND FinanceControl

Resolved:
    managerAccount = lan@company
    financeAccount = admin-lan@company
Both map to IAM:ID-LAN-2041

Nếu policy đòi hai cá nhân độc lập:
    quorum = 1 person, NOT 2 persons.
~~~

Một **quorum** phải tính theo người/authority độc lập theo chính sách; việc hai tài khoản bấm Approve không tự tạo ra hai lớp kiểm soát.

## 13. SoD trong Joiner: chặn cấp quyền toxic ngay từ đầu

**Joiner** có thể được tạo account từ trước ngày vào làm, gán birthright Group hoặc cấp quyền theo vị trí. Rủi ro bắt đầu khi chính sách tự động cấp một **role tổng hợp** chứa những capability đã được xác định là xung đột.

### Kiểm soát nên có khi onboarding

1. HR/nguồn hợp đồng cung cấp **identity, job code, department, effectiveAt** có thẩm quyền.
2. IAM thực hiện proofing/account correlation để không nhầm nhân viên mới với tài khoản cũ hoặc email tái sử dụng.
3. Role catalog ánh xạ vị trí thành **capability thực tế**; không chỉ lấy danh sách Group hiển thị.
4. **Pre-grant SoD check** so quyền đang có và quyền dự định cấp, đúng tenant/resource scope.
5. Nếu phát hiện conflict, yêu cầu owner sửa nhiệm vụ, chọn role hẹp hơn hoặc từ chối grant; ngoại lệ phải theo quy trình riêng.
6. **Pre-provisioning** không được mở quyền nghiệp vụ trước ngày bắt đầu được phê duyệt.
7. Sau provisioning, đọc lại role/Group/ACL tại đích và kiểm tra quyền thực tế phù hợp.

### Ví dụ: role tổng hợp có capability ẩn

~~~text
JobCode = FINANCE_OPERATIONS
Birthright = FinanceOperationsRole

FinanceOperationsRole includes:
    invoice.create
    invoice.approve
    report.read

Rule DSoD:
    cấm invoice creator tự approve cùng invoice

Kết quả:
    Không nhất thiết phải cấm toàn role nếu runtime DSoD đáng tin;
    nhưng hệ thống phải chứng minh invoice-level PEP thực thi.
~~~

Nếu tổ chức lựa chọn SSoD không cho giữ cả hai capability, role tổng hợp phải được **tách hoặc định nghĩa lại** trước cấp. **Không tự coi DSoD là đủ** khi ứng dụng không hỗ trợ kiểm tra transaction creator.

### Sự kiện Joiner bị hủy

Nếu HR hủy onboarding, mọi task cấp quyền chưa chạy phải được vô hiệu hóa theo version/effectiveAt; đặc biệt tránh job đã có approval trước đó **retry và cấp lại** tổ hợp toxic cho một identity không còn hợp lệ.

## 14. SoD trong Mover: mối nguy tích lũy quyền cũ và mới

**Mover** là điểm phát sinh toxic combination rất thường gặp: một nhân viên chuyển sang vai trò khác nhưng hệ thống **chỉ thêm Group mới, không gỡ entitlement cũ**.

### Tình huống

Lan từng làm **VendorMasterEditor**, sau đó chuyển sang nhóm chi trả và được đề nghị cấp **PaymentReleaser**.

| Thời điểm | Quyền tại IAM | Quyền tại app đích | SoD |
| --- | --- | --- | --- |
| Trước Mover | VendorBankEditor | VendorBankEditor | Chưa có payment.release. |
| Mover bắt đầu | VendorBankEditor cần thu hồi; PaymentReleaser cần phê duyệt. | VendorBankEditor vẫn tồn vì SCIM timeout. | Xung đột tiềm năng. |
| Job cấp mới chạy trước revoke cũ | PaymentReleaser đã cấp. | Cả VendorBankEditor và PaymentReleaser. | **Toxic combination hiệu lực** nếu scope giao nhau. |
| Sau khi xử lý đúng | Chỉ PaymentReleaser hợp lệ. | Đã gỡ role cũ, kiểm tra session/token. | Không còn conflict trong scope. |

### Sequencing của Mover

Không có một thứ tự duy nhất cho mọi hệ thống, nhưng với quyền có SoD cao cần xét:

- **Revoke-before-grant**: thu hồi quyền cũ, đọc lại kết quả, sau đó mới cấp quyền mới; tránh cửa sổ overlap độc hại, có thể gây gián đoạn công việc ngắn hạn.
- **Restricted transition**: tạm chặn các action nhạy cảm ở PEP hoặc đặt guard theo trạng thái MOVER_PENDING cho tới khi hai phía hội tụ.
- **Atomic transition** nếu nền tảng hỗ trợ: thay tập quyền trong một transaction hoặc theo policy version.
- **Compensation**: nếu bước cấp mới hoàn tất nhưng bước revoke lỗi, giới hạn session/khóa action và điều tra; **không báo Mover hoàn tất**.

**Nguy cơ chính là effective overlap**, không phải chỉ nhìn dashboard IAM có hai role hay không. Access token hoặc app-local session trước Mover có thể giữ capability cũ sau khi Group đã gỡ.

### Approval cũ không được quyết định cho công việc mới

Một approval VendorBankEditor từ trước không thể dùng làm căn cứ giữ quyền sau Mover nếu nhiệm vụ mới không yêu cầu. Quy trình cần xác định **owner của entitlement** và thời hạn còn hợp lệ, gỡ những quyền không còn căn cứ.

## 15. SoD trong Leaver, suspension và rehire

**Leaver** trước hết cần **thu hồi các access paths còn hiệu lực**, không chỉ giải quyết conflict giữa hai role. Nhưng toxic combination giúp ưu tiên những đường nguy hiểm nhất.

### Đường phải kiểm tra

- IdP account, Group và app assignment.
- SCIM User/Group, direct role và local admin.
- JIT/PAM eligibility và active privilege sessions.
- OAuth access token, refresh token, PAT/API key, SSH key, certificate.
- Resource ACL, cloud trust/delegation, service impersonation.
- Shared secret mà người rời đi đã biết, nếu còn được chấp nhận.

Khi một User bị disable ở IdP, một token tự chứa còn hạn vẫn có thể được Resource Server xác nhận offline. **Kết quả SCIM thành công hoặc IdP disabled không đồng nghĩa mọi capability của toxic set đã không thể dùng**.

### Đề phòng retry sau Leaver

~~~text
v31: JOINER grants VendorBankEditor
v32: MOVER revokes VendorBankEditor, requests PaymentReleaser
v33: LEAVER revokes all employee grants

Delivery order:
    v33 completed
    v32 delayed grant tries to run

Required:
    no new PaymentReleaser grant after v33
    no restored VendorBankEditor from old v31 retry
~~~

Worker cấp quyền phải **kiểm tra lifecycle state hiện hành**, sourceVersion/effectiveAt và approval còn hiệu lực **ngay trước thao tác tại target**, không chỉ tại thời điểm nhận event.

### Suspension

Khi đình chỉ tạm thời, tổ chức có thể giữ bản ghi account và audit nhưng chặn các hành động đã định. SoD checker phải hiểu trạng thái **khả năng dùng quyền** thay vì giả định quyền quan sát được ở directory vẫn có thể sử dụng bình thường.

### Rehire

Nhân viên được tuyển lại không tự được khôi phục mọi role, exception hoặc approval cũ. Nếu người ấy từng giữ hai vai trò có conflict trước khi nghỉ, cần tính lại từ công việc mới và không tự động union lịch sử grants.

## 16. IdP/SSO, SCIM và Authorization trong SoD

SoD là kiểm soát **quyền và hành động**, còn các giao thức quản lý identity có vai trò riêng.

| Lớp | Có thể cung cấp | Không tự bảo đảm |
| --- | --- | --- |
| **HR/IGA** | JML, business role, approval, SoD rule, desired grants. | App-local role và token/phiên đã hết quyền. |
| **IdP/SSO** | Xác thực, subject, Groups/claims, MFA context. | Mọi giao dịch tại ứng dụng tuân DSoD. |
| **SCIM** | Đồng bộ User/Group qua connector. | Quyền resource và session/token được thu hồi tức thời. |
| **RBAC** | Vai trò và quyền chức năng. | Bảo vệ quan hệ creator/approver của từng invoice. |
| **ABAC/ReBAC** | Thuộc tính resource, tenant, quan hệ creator/owner. | Thuộc tính đủ mới nếu PIP lỗi/cache stale. |
| **PBAC/PDP** | Đánh giá chính sách Permit/Deny và rule combining. | API thực thi Deny nếu thiếu PEP. |
| **PAM/PIM** | Hạn/JIT/eligible/admin session, credential controls. | Mọi target session/chứng chỉ cũ đã chấm dứt. |
| **Ứng dụng/PEP** | Chặn action tại giao dịch và resource. | Quyền luôn đúng nếu dữ liệu lifecycle không đủ mới. |

### Vì sao claim Group trong JWT chưa đủ?

Một JWT được IdP ký có thể chứa role InvoiceApprover được cấp trước Mover. Chữ ký chứng minh **claim tại thời điểm phát**, không chứng minh role vẫn còn hiệu lực sau Mover. Nếu Resource Server chỉ tin JWT mà không có guard/revocation phù hợp, có thể cho phép một bước DSoD hoặc SSoD trái chính sách.

### Vì sao SCIM Group không phải là SoD engine?

SCIM thường dùng để tạo/cập nhật User và Group. Cấu trúc SCIM không tự xác định các mối nguy nghiệp vụ giữa **vendor.bankAccount.write** và **payment.release**. IAM/IGA và ứng dụng phải có role-to-capability mapping, SoD rules và kiểm tra thực thi; đích có thể còn **direct grant** ngoài Group.

### Quyết định Permit cần điều kiện từ nhiều lớp

~~~text
Login succeeded at IdP
    does not imply
payment.release is allowed.

SCIM Group membership updated
    does not imply
every old token or direct permission is revoked.

IGA detected no toxic role pair
    does not imply
runtime transaction has no DSoD violation.
~~~

## 17. Toxic combination với privileged access và PAM

Đặc quyền tạo những **đường gián tiếp** vượt qua các cặp nhiệm vụ thông thường.

### Ví dụ xung đột về quyền quản lý IAM

~~~text
Capability A:
    accessRequest.create for GlobalAdmin

Capability B:
    accessRequest.approve for same beneficiary

Capability C:
    iam.role.assign for GlobalAdmin

Nếu một người điều khiển A, B, C:
    có thể tự yêu cầu, tự duyệt, tự cấp đặc quyền.
~~~

Một người có khả năng **sửa approver mapping** hoặc **sửa policy SoD** cũng có thể tạo đường đi vòng dù không được cấp trực tiếp capability B. Phân tích toxic set cần xét **policy administration, delegation và trust**.

### Ví dụ CI/CD

Một developer có quyền sửa mã và tự approve merge có thể gây rủi ro. Nếu đồng thời được **deploy production** và **disable audit**, khả năng che giấu sự cố cao hơn. Đây không nhất thiết là cùng một rule SoD cho mọi repository: cần xem branch protection, yêu cầu review, environment approvals, blast radius và immutable logs.

### JIT/PAM giúp giảm rủi ro nhưng không xóa bản chất xung đột

- **JIT** làm giảm **thời gian** quyền cao có thể được dùng.
- **JEA** giới hạn **hành động** và tài nguyên trong phiên.
- **PAM** có thể đặt broker, approval, credential/session monitoring.
- **SoD rule** vẫn phải quy định các role xung đột có được **eligible**, **activate**, hoặc **sử dụng trên cùng giao dịch** hay không.

Hai role có thể không active đồng thời nhưng vẫn tạo rủi ro nếu một người có thể **kích hoạt luân phiên** để thực hiện toàn bộ chuỗi nghiệp vụ mà không có kiểm tra transaction-level. Vì vậy JIT/role activation restriction **không thay thế mọi DSoD**.

### Session/certificate còn tồn tại

Nếu JIT grant đã hết hạn nhưng phiên SSH/RDP hoặc cloud token đã phát vẫn có hiệu lực, vẫn có thể có cửa sổ dùng capability cũ. Khi review toxic combination, cần xét **active credential/session** ngoài role assignment.

## 18. Non-human identities và chuỗi hành động giữa người và máy

Một hệ thống automation có thể được cấp quyền rất lớn mà không có HR manager. SoD trong môi trường service-to-service cần xem:

1. Workload nào thực hiện từng hành động?
2. Ai có quyền **thay mã nguồn, cấu hình, pipeline hoặc policy** của workload?
3. Service principal có thể tự tạo request và tự gọi approval API không?
4. Token issuer, audience, environment và resource scope có được giới hạn?
5. Có người nào có thể **impersonate workload** hoặc lấy secret để bỏ qua phân quyền của con người?
6. Workload có audit và owner kỹ thuật còn hiệu lực không?

### Ví dụ: approval service và payment executor

~~~text
payment-approval-service:
    allowed: approve payment after authorized human decision

payment-executor:
    allowed: release already-approved payments

Rủi ro:
    cùng một deployment credential có thể sửa code cả hai service;
    hoặc một principal có quyền forged approval và payment.release.
~~~

**Không kết luận rằng mọi bot cùng owner đều vi phạm SoD.** Cần xác định **quyền kiểm soát thực tế và trust boundary**; người chủ service có thể chịu trách nhiệm vận hành nhưng không nhất thiết có quyền đổi approval history hoặc secret production.

### Khi service owner Leaver

Nếu một nhân viên sở hữu service-payment nghỉ việc, không được xóa mù bot đang xử lý giao dịch. Phải:

- Chuyển service ownership.
- Thu hồi quyền con người, credential/secret mà người rời đi có thể biết.
- Rà soát role và trust của service; giảm scope nếu cần.
- Bảo toàn hoặc thay thế workload hợp lệ theo kiểm soát thay đổi.
- Kiểm tra SoD rules và effective access sau bàn giao.

### Non-human identity không nên được cấp quyền “Approve All”

Một automation có thể thực hiện **đối chiếu điều kiện** và tạo workflow, nhưng không được coi nó là người phê duyệt nghiệp vụ độc lập nếu tổ chức yêu cầu quyết định của một approver con người có thẩm quyền. Có thể có automated policy approval cho các trường hợp rủi ro thấp, nhưng phải **được tổ chức thiết kế và duyệt trước**, không phải cách tránh người duyệt.

## 19. Exception cho toxic combination: khi không thể tách nhiệm vụ hoàn toàn

Một doanh nghiệp nhỏ có thể không đủ người cho mọi bước, hoặc một tình huống khẩn cấp khiến một nhân viên phải đảm nhiệm nhiều vai trò. Điều này **không tự biến tổ hợp toxic thành an toàn**; cần kiểm soát giảm thiểu được duyệt và có hạn.

### Một exception đầy đủ

| Thuộc tính | Ví dụ |
| --- | --- |
| exceptionId | EX-SOD-2026-044 |
| ruleId | SOD-PAY-001 v4 |
| subjectIdentityId | IAM:ID-2041 |
| capabilities | vendor.bankAccount.write + payment.release |
| resource scope | tenant-b / legalEntity LE-B / vendor V-99 |
| justification | Khắc phục giao dịch bị kẹt trong cửa sổ vận hành |
| approver | FinanceControl + Security độc lập |
| startAt/endAt | 09:00–10:00 theo timezone rõ |
| compensating controls | Giới hạn value, second confirmation, immutable audit |
| monitoring owner | FinanceControl |
| review/expiry | Auto-expire + hậu kiểm ngày kế tiếp |

### Nguyên tắc xử lý

1. **Exception phải ràng buộc rule và scope**; không dùng một cờ bypassSoD vô hạn.
2. **Không self-approve:** người hưởng quyền không tự phê duyệt ngoại lệ.
3. **Không mở toàn tenant** nếu chỉ cần một đối tượng hoặc khoản giao dịch.
4. **Ưu tiên giảm thời hạn** và kiểm soát session/credential.
5. **Cơ chế bù phải độc lập thực sự**, có bằng chứng và người chịu trách nhiệm.
6. **Expiry phải được enforce**, không chỉ là trường mô tả trong ticket.
7. Sau khi hết hạn, thu hồi grants/activation, kiểm tra token/session và đóng review với evidence.

### Compensating controls phù hợp và không phù hợp

| Ví dụ | Đánh giá |
| --- | --- |
| Một approver độc lập xác nhận riêng giao dịch trước khi release. | Có thể giảm rủi ro nếu approver thật sự độc lập và có khả năng chặn. |
| Hạn mức giao dịch nhỏ, số lượng giao dịch giới hạn và audit bất biến. | Có thể giảm blast radius; vẫn cần đánh giá rủi ro còn lại. |
| Hậu kiểm độc lập mỗi ngày với cảnh báo bất thường. | Có giá trị phát hiện; không ngăn thiệt hại đã xảy ra. |
| Người có toxic quyền tự kiểm tra log của mình. | Không độc lập, kiểm soát bù yếu. |
| Admin được xóa log rồi ghi “đã được giám sát”. | Không bảo đảm bằng chứng. |
| Ngoại lệ không có ngày hết hạn “để tránh phải xin lại”. | Kéo dài standing toxic combination, rủi ro cao. |

### Break-glass

Break-glass là một quy trình cứu hộ đặc biệt khi hệ thống bình thường không khả dụng. Không nên viết logic **PDP/PAM timeout thì Permit tất cả**. Nếu emergency workflow cho phép một người làm nhiệm vụ xung đột, phải có điều kiện chặt hơn về danh tính, thời hạn, phạm vi, logging, alert và hậu kiểm.

## 20. Rủi ro false positive, false negative và chất lượng rule

**False positive:** SoD checker báo toxic nhưng không có đường dùng quyền tương ứng, ví dụ role A chỉ tenant A và role B chỉ tenant B.

**False negative:** SoD checker báo sạch vì chỉ đọc role trực tiếp, bỏ qua quyền qua local admin hoặc Group lồng nhau.

### Nguồn gây sai lệch

| Nguyên nhân | Dạng lỗi | Cách cải thiện |
| --- | --- | --- |
| So theo role name, không giải ra actions. | False negative hoặc false positive. | Role-to-capability mapping có phiên bản. |
| Bỏ qua tenant/legalEntity. | False positive. | Intersection theo resource scope đáng tin. |
| Bỏ qua Group nested/inherited. | False negative. | Effective membership và path graph. |
| Identity mapping theo email. | Cả hai dạng, có thể thu hồi sai người. | Stable identity IDs và account correlation. |
| Token/Group cũ sau Mover. | False negative nếu chỉ nhìn IAM desired. | Observed/effective access và freshness. |
| Không xét transaction creator. | False negative DSoD. | Runtime check theo object ID và actor ID. |
| Rule quá rộng cho mọi employee. | False positive, workflow bị tắc. | Phân scope theo action, tenant, rủi ro và time. |
| Resource metadata không lấy được. | Unknown bị nhầm clean. | Phân loại Indeterminate/Incomplete, không cấp quyền mới. |
| Quyền sửa policy/assume role. | False negative privilege escalation. | Xét quyền gián tiếp và trust relationships. |
| Không xét exception đã hết hạn. | False negative. | TTL/expiry và policy revalidation. |

**Kết quả “0 conflicts” không chứng minh hệ thống an toàn** nếu coverage thấp. Báo cáo cần ghi rule versions, data sources, số principal/resource được quét, thiếu dữ liệu và số đường chưa xác minh.

## 21. Quy trình đánh giá SoD conflict từ yêu cầu đến remediation

~~~mermaid
flowchart TD
    A["Role request / JML event / review campaign"] --> B["Resolve identity + account links<br/>và trạng thái lifecycle"]
    B --> C["Collect direct + inherited + dynamic access"]
    C --> D{"Dữ liệu đầy đủ, mới<br/>và đúng scope?"}
    D -->|Không| X["INDETERMINATE/REVIEW<br/>không tự mở quyền"]
    D -->|Có| E["Simulate capabilities after change"]
    E --> F["Match toxic sets + scope + relation"]
    F --> G{"SoD conflict?"}
    G -->|Không| H["Apply approval + policy guards"]
    G -->|Có| I["BLOCK or controlled exception"]
    I --> J["Independent review / scope reduction"]
    J --> E
    H --> K["Provision / enforce tại ứng dụng"]
    K --> L["Readback + test effective rights"]
    L --> M{"Khớp desired & SoD?"}
    M -->|Có| N["VERIFIED + audit"]
    M -->|Không| O["PARTIAL_FAILURE + containment"]
~~~

### Bảy bước triển khai

1. **Xác định nghiệp vụ cần tách:** chủ sở hữu Finance, HR, Security, Platform xác định rủi ro gian lận và trách nhiệm kiểm soát.
2. **Lập rule catalog:** định nghĩa toxic set, scope, loại SSoD/DSoD, owner, mức rủi ro, ngoại lệ.
3. **Thu thập quyền đầy đủ:** IAM desired, IdP/SCIM/app observed, roles, nested Groups, trust, PAM, transaction history.
4. **SoD evaluation:** giải capabilities, tìm vùng scope giao nhau, đánh giá điều kiện giao dịch và kiểm tra effective permissions.
5. **Ra quyết định:** deny new grant, revoke old, narrow scope hoặc xử lý exception qua approver độc lập.
6. **Thực thi và kiểm chứng:** ngăn tại PEP hoặc sửa entitlement tại target; đọc lại trạng thái và kiểm tra quyền thực tế.
7. **Audit và quan sát:** ghi rule/version, identity, resource, kết quả, lỗi, residual risk, theo dõi tới khi verified.

### Không dùng một bước duyệt để lấp đầy thiếu dữ liệu

Nếu PIP không đọc được nguồn quyền hoặc mapping User mơ hồ, một approver khó có thể ký xác nhận “không toxic”. Khi đó cần **điều tra hoặc containment theo rủi ro**, không chuyển mặc định thành “Approved because data unavailable”.

## 22. Pseudocode kiểm tra toxic combination

Mã giả dưới đây diễn đạt một thuật toán khái niệm. Không dùng trực tiếp như implementation production, vì mỗi hệ thống có semantics khác nhau cho policy, quyền gián tiếp, thời điểm và giao dịch.

### SoD check tại thời điểm xin quyền

~~~text
checkGrantForToxicCombination(subjectRef, requestedGrant):
    subject = resolveTrustedIdentity(subjectRef)
    if subject is unresolved:
        return BLOCK_MAPPING_CONFLICT

    lifecycle = loadAuthoritativeLifecycle(subject)
    if lifecycle is unavailable or lifecycle.disallowsGrant:
        return BLOCK_NO_PERMISSION_TO_GRANT

    current = collectEffectiveCapabilities(
        subject = subject,
        sources = requiredIdPAndAppAndPamSources,
        includeDirect = true,
        includeInherited = true,
        includeDelegated = true
    )
    if current.isIncomplete or current.isStaleBeyondPolicy:
        return BLOCK_INDETERMINATE_WITH_REVIEW

    simulated = simulateAfterGrant(
        currentCapabilities = current,
        requestedGrant = requestedGrant,
        roleToActionMapping = currentApprovedCatalog
    )

    findings = []
    for sodRule in approvedSoDRules:
        relevant = sodRule.appliesTo(subject, requestedGrant.context)
        if not relevant:
            continue

        if simulated.containsAll(sodRule.forbiddenCapabilities)
           and scopesOverlap(simulated, sodRule.scope)
           and sodRule.additionalConditionsHold(simulated):
            findings.add(explainConflict(sodRule, simulated))

    if findings not empty:
        audit(findings, sourceVersions, policyVersion)
        return BLOCK_OR_ROUTE_TO_CONTROLLED_EXCEPTION

    return CONTINUE_TO_NORMAL_APPROVAL
~~~

### DSoD check tại thời điểm duyệt hóa đơn

~~~text
approveInvoice(actorAuthn, invoiceId):
    actor = validateAuthnAndResolveIdentity(actorAuthn)
    invoice = loadTrustedInvoiceWithVersion(invoiceId)
    if actor unresolved or invoice unresolved:
        return NO_APPROVAL

    subject = loadCurrentLifecycleAndRoles(actor)
    if subject.lifecycleStatus != ACTIVE:
        return DENY
    if not policyAllows(actor, "invoice.approve", invoice):
        return DENY

    createdBy = resolveTrustedCreatorIdentity(invoice)
    if createdBy cannot be verified:
        return BLOCK_INDETERMINATE
    if createdBy == actor.identityId:
        audit("SOD_SELF_APPROVAL_DENY", invoiceId)
        return DENY

    return approveWithinTransactionIfUnchanged(
        invoiceId = invoiceId,
        expectedVersion = invoice.version,
        approverIdentityId = actor.identityId
    )
~~~

Giữa lúc check và commit, invoice có thể bị thay đổi (**TOCTOU**). Cần transaction hoặc conditional update để bảo đảm creator, status, amount và scope vẫn phù hợp khi thực hiện.

### Bảo vệ khi event JML đến muộn

~~~text
applyPrivilegeGrant(task):
    state = readCurrentLifecycleAndApprovedScope(task.identityId)
    if task.sourceVersion is superseded by state:
        return SUPERSEDED_NO_GRANT
    if state.lifecycleStatus != ACTIVE:
        return BLOCK
    if not approvalValidForCurrentRoleAndResource(task):
        return BLOCK
    if newGrantCreatesToxicCombination(task):
        return BLOCK
    return provisionIdempotentlyAndReadBack(task)
~~~

**Không giả định tất cả nguồn có một counter tăng toàn cục.** SourceVersion/effectiveAt phải có ngữ nghĩa theo từng nguồn/identity và các sự kiện không so sánh được cần được xử lý có kiểm soát.

## 23. Kiểm thử toxic combination và SoD

Kiểm thử phải bao phủ **được phép, xung đột, thiếu dữ liệu, thay đổi vòng đời và quyền thực sự ở đích**, bao gồm các yêu cầu cấp quyền **và** runtime actions.

### Ma trận kiểm thử

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| SOD-T01 | User chỉ có VendorEditor trong đúng scope. | Không báo toxic set cần thêm PaymentReleaser. |
| SOD-T02 | Thêm PaymentReleaser cho cùng legalEntity. | Chặn grant hoặc xử lý ngoại lệ đúng policy. |
| SOD-T03 | Hai role ở tenant hoàn toàn tách biệt và không có cross-tenant path. | Không false positive nếu rule yêu cầu cùng tenant. |
| SOD-T04 | Có cross-tenant assume-role trust dù role gán ở tenant khác. | Phát hiện vùng effective scope giao nhau. |
| SOD-T05 | User có role tổng hợp chứa cả capability A và B. | Phát hiện conflict dù chỉ có một role name. |
| SOD-T06 | Cặp conflict hình thành qua nested Group. | Phát hiện inherited entitlement. |
| SOD-T07 | Ứng dụng có direct grant ngoài IdP Group. | Phát hiện ở app; không kết luận sạch từ IdP. |
| SOD-T08 | Quy tắc toxic cần ba capability, User chỉ có hai. | Không báo vi phạm rule ba capability khi chưa đủ điều kiện. |
| SOD-T09 | User có đủ cả ba capability cùng scope. | Conflict theo rule, không bỏ sót hyperedge. |
| SOD-T10 | Creator tự approve chính invoice. | DSoD Deny; invoice không đổi trạng thái. |
| SOD-T11 | Creator duyệt invoice khác nếu policy cho phép. | Không chặn nhầm do chỉ thấy hai role. |
| SOD-T12 | Approver dùng account admin khác nhưng cùng IAM identity. | DSoD vẫn chặn self-approval. |
| SOD-T13 | User có role InvoiceApprover nhưng tenant khác. | Deny theo tenant/authority guard. |
| SOD-T14 | Chưa thể xác minh transaction creator. | Không tự Permit; ghi Indeterminate. |
| SOD-T15 | Policy mới đổi role-to-action mapping. | Re-evaluate toxic sets và chạy regression. |
| SOD-T16 | Joiner có role chuẩn bị trước startAt. | Không mở quyền nghiệp vụ sớm. |
| SOD-T17 | Mover gỡ old grant và cấp new grant đúng thứ tự. | Không tồn tại effective toxic overlap ngoài boundary. |
| SOD-T18 | Mover revoke old role thất bại, new role được cấp. | Detect, block/contain, PARTIAL_FAILURE. |
| SOD-T19 | Leaver có app session/JWT role cũ. | Chặn action theo revocation policy; đo residual path. |
| SOD-T20 | Job Joiner phiên bản cũ retry sau Leaver. | Không tái cấp quyền. |
| SOD-T21 | Rehire quay lại vai trò khác. | Không tự khôi phục exception/grant lịch sử. |
| SOD-T22 | User có quyền sửa IAM policy để tự cấp role. | Phát hiện privilege escalation path. |
| SOD-T23 | Một nhân viên có JIT eligibility cho cả hai role. | Xét khả năng activate luân phiên và DSoD theo giao dịch. |
| SOD-T24 | PAM revoke grant nhưng session admin vẫn có quyền. | Không báo verified nếu hành động vẫn thực hiện được. |
| SOD-T25 | Workload có quyền tạo approval giả và release payment. | Phát hiện machine toxic capability/trust. |
| SOD-T26 | Service owner Leaver. | Bàn giao owner, rotate secret phù hợp, tránh xóa mù service hợp lệ. |
| SOD-T27 | Exception có owner/scope/endAt, approver độc lập. | Chỉ được áp trong phạm vi đã phê duyệt. |
| SOD-T28 | Exception hết hạn nhưng token cũ còn quyền. | Chặn/thu hồi trong giới hạn yêu cầu, không tự kéo dài. |
| SOD-T29 | Một người bấm hai phiếu bằng hai account. | Không đạt quorum độc lập nếu policy cần hai người. |
| SOD-T30 | PIP không đọc được trang cuối của Group API. | INCOMPLETE; không báo No Conflict. |
| SOD-T31 | PDP lỗi khi yêu cầu privileged action. | Không tự Permit/Approve All. |
| SOD-T32 | API trả 403 nhưng DB đã ghi invoice APPROVED. | Test FAIL; có unauthorized side effect. |

### Gherkin minh họa

~~~gherkin
Feature: SoD toxic combinations remain blocked across lifecycle

  Scenario: A mover cannot hold toxic finance permissions
    Given Minh has vendor bank-account edit access in legal entity B
    And a Mover event requests payment release access in entity B
    When IAM evaluates the proposed grant
    Then the toxic combination rule is triggered
    And conflicting access is revoked before incompatible access is usable
    And target effective permissions are verified

  Scenario: The creator cannot approve the same invoice
    Given Lan created invoice INV-91
    And Lan has a technically valid InvoiceApprover role
    When Lan attempts to approve INV-91
    Then the action is denied by dynamic SoD
    And the invoice remains unapproved

  Scenario: A second account does not bypass independent approval
    Given a privileged request benefits identity IAM-ID-2041
    And the user signs in with another account linked to that identity
    When the user attempts to approve their own request
    Then the approval is rejected
    And no valid independent approval is recorded

  Scenario: An incomplete role snapshot never certifies no conflicts
    Given an app role endpoint omits inherited permissions
    When the SoD scanner builds a conflict assessment
    Then it marks evidence coverage incomplete
    And it does not certify a clean result
~~~

### Positive và negative assertions

- **Positive:** người dùng hợp lệ, không conflict, đúng tenant/resource vẫn làm việc được; tránh giảm availability vì rule quá rộng.
- **Negative:** tình huống toxic bị chặn **trước khi có side effect**, cả qua API trực tiếp, batch job và session cũ.
- **Idempotency:** retry request không làm grant được cấp trùng hoặc bypass pre-grant SoD.
- **Race:** concurrent grants của hai role khác nhau không thể cùng thành công nếu trạng thái hợp nhất vi phạm SSoD.
- **Readback:** lệnh revoke hoàn tất và quyền hiệu lực được kiểm chứng, không chỉ có phản hồi API thành công.

## 24. Race condition và tính nhất quán của SoD

Một lỗi phổ biến là hai workflow riêng biệt cùng cấp quyền:

~~~text
Time T0:
    User không có A và B.

Worker W1:
    check User has no B -> PASS
    prepare grant A

Worker W2:
    check User has no A -> PASS
    prepare grant B

Time T1:
    both grants succeed
    final User has A + B -> TOXIC
~~~

Đây là **write skew/race** khi từng bước kiểm riêng nhưng không bảo vệ trạng thái hợp nhất. Các lựa chọn:

1. **Serialize** những thay đổi entitlement theo identity/resource conflict domain.
2. **Optimistic concurrency** bằng version/ETag và retry có re-evaluation.
3. **Atomic constraints** ở kho grant nếu kiểm soát nằm cùng transaction.
4. **Guard tại Resource Server** chặn action xung đột ngay cả khi provisioning chưa hội tụ.
5. **Continuous detection/containment** phát hiện nhanh conflict còn lại do phân tán.

### Policy version mismatch

Nếu PDP A dùng SoD rule v4 còn app B dùng v3, hai nơi có thể cho kết quả khác. Cần quản lý **rule version, rollout strategy, compatibility, invalidation và audit**. Đặc biệt không cho một policy version cũ bỏ qua hard guard đã có hiệu lực tại nguồn có thẩm quyền.

### Missing PIP và fail-closed

Khi không đọc được creatorIdentityId của invoice, API không thể khẳng định chủ thể **khác người tạo**. Với action có DSoD bắt buộc, không được giả định khác người để Permit. Có thể trả 403 hoặc lỗi hệ thống tùy contract, nhưng **không thực hiện phê duyệt** và phải ghi nhận lỗi nguồn.

## 25. SoD review, audit và metrics

Một hệ thống SoD cần bằng chứng về **rule, dữ liệu, quyết định và thực thi**:

| Trường audit | Mục đích |
| --- | --- |
| ruleId/version, severity | Giải thích chính sách xung đột. |
| identityId, accountRefs, principalType | Xác định đúng người/workload và các account liên quan. |
| capabilities và access paths | Chứng minh từng quyền xuất phát từ đâu. |
| resourceRef, tenant, legalEntity | Xác định vùng scope giao nhau. |
| transactionId/creator/approver | Chứng minh DSoD tại giao dịch. |
| lifecycle status/effectiveAt/sourceVersion | Chứng minh thay đổi JML. |
| grant source, observedAt, data completeness | Đánh giá độ mới và tin cậy của dữ liệu. |
| requestedGrant/approver/approvalVersion | Biết quyền mới được yêu cầu hoặc duyệt ra sao. |
| conflict determination và reason | Phân biệt potential, confirmed, unknown. |
| exception/mitigating control/expiry | Xác định ngoại lệ và residual risk. |
| remediation và effective verification | Chứng minh conflict đã được giải quyết tại đích. |
| correlationId/review owner | Liên kết sự kiện nhiều hệ thống. |

### Event minh họa

~~~json
{
  "eventType": "IAM_SOD_TOXIC_COMBINATION",
  "ruleId": "SOD-PAY-001",
  "ruleVersion": 4,
  "identityId": "IAM:ID-MINH-88",
  "capabilities": [
    "vendor.bankAccount.write",
    "payment.release"
  ],
  "scope": {
    "legalEntity": "LE-B",
    "tenant": "tenant-b"
  },
  "accessPaths": [
    "SaaS:VendorEditor:direct",
    "IdP:PaymentOperators:inherited"
  ],
  "lifecycleState": "ACTIVE",
  "assessment": "CONFIRMED_CONFLICT",
  "decision": "BLOCK_NEW_GRANT",
  "rulePolicyVersion": "sod-catalog-2026-v4",
  "observedAt": "2026-12-01T09:31:00+07:00",
  "correlationId": "access-request-771"
}
~~~

Đây là schema nội bộ minh họa. Không lưu mật khẩu, access/refresh token nguyên vẹn, cookie, private key hoặc bí mật MFA; giới hạn quyền đọc log, bảo vệ tính toàn vẹn và thời hạn lưu giữ.

### Chỉ số vận hành

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Potential/confirmed SoD conflicts** | Số conflict theo rule, risk, tenant và trạng thái. |
| **False-positive review rate** | Có rule nào quá rộng hoặc dữ liệu scope không đủ chuẩn? |
| **Unknown/incomplete coverage rate** | Bao nhiêu principal/entitlement chưa thể khẳng định sạch? |
| **Blocked toxic grant attempts** | Số yêu cầu được preventive SoD chặn trước cấp. |
| **Runtime DSoD violation attempts** | Số lần tự approve hoặc hành động bị PEP chặn. |
| **Unauthorized SoD side effects** | Số thao tác xung đột thực sự hoàn tất trái policy. |
| **Mover toxic overlap duration** | Thời gian old/new quyền giao nhau sau chuyển vai trò. |
| **Residual access after Leaver** | Quyền còn dùng được sau mốc thu hồi. |
| **Exception count and overdue rate** | Ngoại lệ quá hạn hoặc không còn control bù. |
| **Compensating-control effectiveness** | Bằng chứng kiểm soát độc lập phát hiện/chặn được rủi ro. |
| **Policy/version drift** | Các ứng dụng còn dùng quy tắc cũ. |
| **Time to verified remediation** | Thời gian từ conflict tới khi quyền hiệu lực được xử lý. |

**Không dùng “số conflict bằng 0” làm KPI duy nhất.** Có thể hệ thống không thu đủ nguồn. Cần tách **conflict được chặn hợp lệ**, **conflict đang cần xử lý**, **risk exception có kiểm soát** và **vi phạm thực tế**.

## 26. Tình huống thực hành

### Tình huống A — Hai role khác tenant

**Bối cảnh:** Lan có VendorEditor ở tenant A và PaymentReleaser ở tenant B; không có quyền quản trị xuyên tenant trong inventory.

**Câu hỏi:** Có tự động coi là toxic không?

**Gợi ý:** Chưa đủ. Nếu rule yêu cầu cùng tenant, phải chứng minh scope có giao nhau. Kiểm tra trust, role assumption và khả năng cross-tenant thực tế trước khi kết luận.

### Tình huống B — Mover giữ quyền cũ

**Bối cảnh:** Minh chuyển từ Procurement sang Treasury. IAM đã phê duyệt PaymentReleaser nhưng SaaS vẫn giữ VendorBankEditor do connector lỗi.

**Câu hỏi:** Rủi ro và hành động ưu tiên?

**Gợi ý:** Effective overlap tạo toxic combination trong cùng legal entity. Áp guard chặn quyền xung đột, thu hồi quyền cũ và kiểm chứng target; không đánh dấu Mover hoàn tất dựa vào trạng thái desired.

### Tình huống C — Tự duyệt qua admin account khác

**Bối cảnh:** Lan tạo invoice bằng normal account rồi mở admin-lan để approve cùng invoice; hai tài khoản liên kết về một IAM identity.

**Câu hỏi:** Có phải vi phạm DSoD không?

**Gợi ý:** Có nếu policy cấm creator tự duyệt. So actor theo stable identity; không chỉ so username hoặc issuer claim chưa được correlation.

### Tình huống D — Một role chứa cả hai quyền

**Bối cảnh:** Role FinanceAllActions bao gồm vendor.bankAccount.write và payment.release. Hệ thống SoD chỉ so cặp **tên role** nên báo không conflict.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** Cần phân tích **role-to-action mapping**, effective permissions và scope. Một role có thể nội tại độc hại.

### Tình huống E — Quorum hai cấp cùng một người

**Bối cảnh:** Workflow yêu cầu Manager và Security approval độc lập. Cả hai task được cùng một người thực hiện qua hai tài khoản.

**Câu hỏi:** Có được tính quorum = 2 không?

**Gợi ý:** Không khi policy yêu cầu hai cá nhân độc lập. Correlate về cùng IAM identity và kiểm tra SoD theo người thực.

### Tình huống F — JIT luân phiên để vượt kiểm soát

**Bối cảnh:** Một admin không thể kích hoạt VendorEditor và PaymentReleaser cùng lúc, nhưng có thể kích hoạt VendorEditor để đổi ngân hàng, tắt role rồi kích hoạt PaymentReleaser để chuyển tiền.

**Câu hỏi:** Tại sao SSoD theo active session chưa đủ?

**Gợi ý:** Chuỗi giao dịch có thể tiếp tục dù role không active đồng thời. Cần DSoD theo vendor/transaction history, kiểm tra độc lập hoặc tách quyền theo nghiệp vụ.

### Tình huống G — Workload có đường tự phê duyệt

**Bối cảnh:** Payment service có quyền gửi lệnh chi tiền. Một deployment bot có quyền sửa code service và ký thông điệp approval đầu vào.

**Câu hỏi:** Có cần xem SoD của workload không?

**Gợi ý:** Có. Đánh giá trust boundary, ai kiểm soát code/credential, nguồn chứng thực approval và quyền máy thực tế; không chỉ xem HR roles.

### Tình huống H — Ngoại lệ không hết hạn

**Bối cảnh:** Đội Finance có exception cho một người giữ hai quyền xung đột khi thiếu nhân lực; không có endAt và người này được tự hậu kiểm log.

**Câu hỏi:** Vì sao kiểm soát bù yếu?

**Gợi ý:** Không có expiry, không độc lập và khó đo residual risk. Cần approval độc lập, scope hẹp, time bound, giám sát và hậu kiểm thực chất.

### Tình huống I — PDP timeout, API vẫn approve

**Bối cảnh:** API không đọc được creatorIdentityId vì datastore timeout, nhưng trả Permit nếu User có InvoiceApprover.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Hệ thống bỏ qua điều kiện DSoD bắt buộc khi thiếu dữ liệu. Không thực hiện approval, ghi lỗi/Indeterminate và retry sau khi nguồn phục hồi.

### Tình huống J — Thu hồi SCIM không hủy token

**Bối cảnh:** Leaver bị gỡ PaymentReleaser Group bằng SCIM; JWT cũ còn scope payment.release và API kiểm offline.

**Câu hỏi:** Đã ngăn được xung đột/đặc quyền tồn dư chưa?

**Gợi ý:** Chưa chắc. Kiểm tra Resource Server, token TTL, revocation/policy lookup và quyền thực tế; không suy từ SCIM PATCH thành công.

### Tình huống K — Hai worker cùng cấp quyền

**Bối cảnh:** Worker 1 kiểm tra trước cấp VendorEditor, Worker 2 kiểm tra trước cấp PaymentReleaser. Mỗi worker thấy User chưa có quyền đối nghịch, rồi cả hai cấp thành công.

**Câu hỏi:** Kiểm soát cần ở đâu?

**Gợi ý:** Cần serialized/atomic constraint hoặc version guard có re-evaluation, cùng runtime PEP và continuous detection để chống write skew.

## 27. Câu hỏi tự kiểm tra

**1. Toxic combination có nghĩa một role luôn nguy hiểm không?**

Không. Nó thường mô tả tổ hợp năng lực tạo rủi ro theo rule, scope và ngữ cảnh; một quyền nhạy cảm đơn lẻ vẫn có thể nguy hiểm nhưng thuộc đánh giá đặc quyền riêng.

**2. SSoD và DSoD khác nhau như thế nào?**

SSoD ngăn việc **giữ/gán đồng thời** các quyền xung đột; DSoD ngăn **kết hợp sử dụng trên cùng giao dịch, phiên hoặc context** dù người dùng có thể giữ các role.

**3. Vì sao phải xét capability thay vì chỉ tên role?**

Vì role khác nhau có thể chứa cùng quyền, và một role tổng hợp có thể chứa trọn toxic set.

**4. Hai role xung đột trên hai tenant có luôn toxic không?**

Không tự động. Phải xem điều kiện overlap của rule và khả năng cross-tenant/delegated quyền thực tế.

**5. Một nhân viên có thể tự duyệt hóa đơn mình tạo bằng admin account khác không?**

Không nếu DSoD cấm. SoD phải dùng identity correlation ổn định giữa các account.

**6. Tại sao Mover dễ gây toxic combination?**

Vì quyền cũ có thể chưa thu hồi trong khi quyền mới được cấp, tạo privilege accumulation và effective overlap.

**7. Pre-grant SoD check có đủ nếu ứng dụng còn local admin role không?**

Không. Cần observed/effective access, connector coverage và runtime PEP tại app.

**8. SCIM Group đã gỡ sau Leaver có nghĩa JWT cũ mất quyền ngay không?**

Không mặc định. Access token tự chứa hoặc app session có thể còn hiệu lực theo thiết kế Resource Server.

**9. Tại sao JIT không hoàn toàn thay thế DSoD?**

Một người có thể kích hoạt hai role ở các thời điểm khác nhau để hoàn tất chuỗi giao dịch xung đột; cần ràng buộc theo transaction/history.

**10. Một toxic rule luôn phải là cặp hai quyền không?**

Không. Có thể là tập ba hoặc nhiều capability, cần mô hình hóa điều kiện thật để tránh false positive.

**11. Khi nguồn role inventory bị thiếu trang, có được báo No Conflict không?**

Không. Đây là trạng thái incomplete/unknown; cần sửa thu thập hoặc bổ sung kiểm soát.

**12. Một ngoại lệ SoD hợp lệ nên có những gì?**

Rule, subject, scope, rationale, approver độc lập, start/end, giảm thiểu rủi ro, owner, audit và kiểm chứng expiry.

**13. Vì sao không được tự hậu kiểm giao dịch mà mình có quyền gây ra?**

Vì kiểm soát bù thiếu độc lập và có thể bị thao túng; cần reviewer/cơ chế kiểm tra độc lập có khả năng phát hiện/chặn.

**14. Chỉ số conflict bằng 0 có chứng minh an toàn không?**

Không. Phải xét coverage, hiệu lực policy, dữ liệu nguồn và đường quyền gián tiếp; 0 có thể do scanner thiếu dữ liệu.

**15. Xử lý thế nào khi không đọc được người tạo hóa đơn?**

Không tự cho phép DSoD-protected approval. Chặn action, phân loại lỗi, audit và phục hồi nguồn dữ liệu.

**16. Vì sao hai job cấp quyền có thể tạo toxic dù đều đã kiểm tra?**

Vì race/write skew: mỗi job kiểm khi role đối nghịch chưa xuất hiện; cần atomicity/serializing hoặc version guard và kiểm lại.

**17. Service account có thể tham gia SoD không?**

Có. Workload có capability nhạy cảm và trust/credential cho phép chuỗi hành động xung đột; phải xem owner, điều khiển code và dữ liệu phê duyệt, không chỉ HR user.

**18. Kết luận SoD sạch ở IAM có thay thế runtime test không?**

Không. App có local roles, direct grants hoặc token/session cũ; phải kiểm tra điểm thực thi và quyền hiệu lực.

## Ghi nhớ

- **Toxic combination** là tổ hợp quyền hoặc khả năng tạo rủi ro theo **quy trình nghiệp vụ, chủ thể, resource, tenant, thời điểm và quan hệ giao dịch**; không chỉ là hai tên role trong danh mục.
- **SSoD** ngăn gán/giữ quyền xung đột, trong khi **DSoD** ngăn kết hợp sử dụng chúng trên cùng giao dịch hoặc phiên. Một tổ hợp có thể gồm **hai hoặc nhiều capability**, kể cả quyền gián tiếp.
- Phải kiểm tra **effective permissions** từ Group lồng nhau, role kế thừa, local ACL, service principal, trust, role assumption, JIT/PAM và phiên/token còn hạn; không suy No Conflict chỉ từ IdP/SCIM.
- **Joiner** cần pre-grant SoD và ngày kích hoạt; **Mover** cần thu hồi quyền cũ trước hoặc đồng thời kiểm soát khi cấp quyền mới; **Leaver** cần chặn mọi đường truy cập trong giới hạn chính sách và chống job cũ tái cấp; **rehire** không tự phục hồi lịch sử grant.
- **RBAC/ABAC/PBAC, IdP/SSO, SCIM, IAM/IGA, PAM, PIP/PDP/PEP** có trách nhiệm khác nhau: quyết định chính sách chỉ có giá trị khi ứng dụng thực sự **enforce** đúng giao dịch/tài nguyên.
- Ngoại lệ SoD phải **có scope hẹp, approval độc lập, thời hạn, kiểm soát bù và audit**; break-glass không đồng nghĩa tự động Permit khi hệ thống lỗi.
- **Rule catalog, sourceVersion/effectiveAt, kiểm thử tình huống giao nhau, idempotent remediation, readback, giám sát và đối soát desired–observed–effective** là nền tảng để giảm tổ hợp toxic và quyền truy cập tồn dư trong toàn bộ vòng đời danh tính IAM.
