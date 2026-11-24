# Xác định role model khi thiết kế chương trình IAM

Trong **Identity and Access Management (IAM)**, việc biết một nhân viên đang làm việc và có tài khoản tại ứng dụng vẫn chưa trả lời được câu hỏi quan trọng: **người đó cần những quyền nào để hoàn thành công việc, và vì sao?** Một *role model* (mô hình vai trò) giúp tổ chức chuyển yêu cầu nghiệp vụ thành các tập quyền có thể giải thích, phê duyệt, cấp phát, rà soát và thu hồi.

Nếu không có mô hình vai trò rõ ràng, quyền thường được cấp bằng cách sao chép tài khoản của đồng nghiệp, thêm từng nhóm thủ công hoặc giữ lại quyền cũ sau khi chuyển bộ phận. Kết quả là quyền truy cập tồn dư (*privilege creep*), khó kiểm toán và khó tự động hóa vòng đời **Joiner–Mover–Leaver (JML)**.

Bài học thuộc chương **Thiết kế chương trình IAM** của module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Trọng tâm là xây dựng role model phù hợp với IdP, SSO, SCIM, **Role-Based Access Control (RBAC)**, **Attribute-Based Access Control (ABAC)**, tài khoản dịch vụ và yêu cầu kiểm toán xuyên suốt vòng đời danh tính.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **role, entitlement, permission, group, job title** và các thuộc tính danh tính.
2. Thiết kế role catalog có owner, phạm vi tài nguyên, quy tắc gán vai trò, quyền đi kèm, thời hạn và chu kỳ rà soát.
3. Chọn RBAC, ABAC hoặc mô hình kết hợp dựa trên mức độ ổn định của công việc và bối cảnh truy cập.
4. Phân tích vai trò nghiệp vụ, vai trò ứng dụng, vai trò đặc quyền, vai trò cơ sở và các xung đột **Separation of Duties (SoD)**.
5. Áp role model cho Joiner, Mover, Leaver, truy cập tạm thời, tài khoản dịch vụ và đối soát trạng thái quyền thực tế.
6. Xác định cách đo chất lượng mô hình và nhận diện **role explosion**, quyền cấp trực tiếp ngoài chính sách hoặc vai trò không còn người sở hữu.

## 2. Role model là gì?

**Role model** là tập quy tắc và cấu trúc mô tả những vai trò nào tồn tại, mỗi vai trò đại diện cho nhu cầu công việc gì, mang những quyền nào, ai được nhận vai trò, ai phê duyệt và khi nào vai trò phải được đánh giá hoặc thu hồi.

Điểm cốt lõi của role model là liên kết một quyết định cấp quyền với **lý do nghiệp vụ có thể kiểm chứng**. Ví dụ, “thành viên nhóm tài chính được xem báo cáo tổng hợp” rõ ràng hơn “cấp ba nhóm directory vì người trước đây cũng có ba nhóm đó”.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Job title / chức danh** | Thuộc tính nhân sự nói về vị trí công việc; không mặc nhiên là quyền. | `Finance Specialist`. |
| **Identity attribute** | Thông tin danh tính dùng để đánh giá chính sách. | `departmentId=FIN`, `employmentStatus=ACTIVE`, `tenantId=VN`. |
| **Permission / quyền thao tác** | Khả năng thực hiện một hành động trên tài nguyên. | `expense:approve` đối với một phiếu chi. |
| **Entitlement / quyền được cấp** | Đơn vị quyền mà hệ thống hoặc IAM có thể gán, thu hồi hoặc rà soát; có thể là role đích, nhóm, policy, scope tài nguyên. | Thành viên `expense-approvers`, vai trò IAM trong cloud. |
| **Technical / application role** | Tập entitlement ở một ứng dụng hoặc nền tảng cụ thể. | `EXPENSE_APP_APPROVER`. |
| **Business role** | Nhóm quyền biểu diễn trách nhiệm nghiệp vụ, có thể ánh xạ đến nhiều hệ thống. | `FINANCE_ANALYST`. |
| **Directory / IdP group** | Đối tượng nhóm kỹ thuật; có thể được dùng để truyền hoặc thực thi quyền nhưng không nhất thiết là role nghiệp vụ. | `grp-expense-approver-prod`. |
| **Role assignment** | Quan hệ đã được phê duyệt hoặc tính hợp lệ giữa một danh tính và một role, thường có scope/thời hạn. | Nhân viên A nhận `FINANCE_ANALYST` cho tenant VN đến ngày xét duyệt. |

Một **role không nhất thiết trùng với job title**. Hai nhân viên cùng chức danh có thể thuộc các dự án hoặc tenant khác nhau và cần phạm vi dữ liệu khác nhau. Ngược lại, nhiều chức danh có thể cần một tập quyền chung. Role model phải thể hiện nhu cầu truy cập, không sao chép nguyên xi sơ đồ tổ chức.

### Mối quan hệ giữa danh tính, vai trò và quyền

~~~mermaid
flowchart LR
    S["Nguồn danh tính<br/>HRIS / VMS / service catalog"] --> I["Identity + thuộc tính<br/>trạng thái, đơn vị, tenant"]
    I --> P["Chính sách gán role<br/>điều kiện + phê duyệt + SoD"]
    P --> B["Business role<br/>trách nhiệm công việc"]
    B --> T["Technical role<br/>ứng dụng / môi trường"]
    T --> E["Entitlement<br/>nhóm, role đích, policy"]
    E --> A["Ứng dụng / API / dữ liệu"]
    P --> G["Quyết định ABAC<br/>theo ngữ cảnh và tài nguyên"]
    G --> A
    A --> R["Đối soát quyền thực tế"]
    R --> P
~~~

Sơ đồ thể hiện một cách tổ chức **logic**. Trong triển khai thực tế, có thể gán technical role trực tiếp cho trường hợp nhỏ, hoặc ứng dụng tự thực thi ABAC mà không đồng bộ đủ mọi role qua IdP. Dù chọn cấu trúc nào, quyền cuối cùng tại hệ thống đích vẫn cần được đối soát với chính sách.

## 3. Các quyết định cần làm rõ trước khi dựng role model

### 3.1. Xác định chủ thể, tài nguyên và hành động

Một vai trò có nghĩa khi gắn với phạm vi truy cập được mô tả chính xác:

- **Chủ thể (subject):** nhân viên, nhà thầu, đối tác, service account hoặc workload nào sẽ sử dụng?
- **Tài nguyên (resource):** ứng dụng, tenant, API, cơ sở dữ liệu, dự án hoặc tập dữ liệu nào được bảo vệ?
- **Hành động (action):** đọc, tạo, sửa, phê duyệt, xuất dữ liệu, quản trị hoặc thay đổi chính sách?
- **Ngữ cảnh (context):** tenant, môi trường production, thời gian, thiết bị, mức rủi ro hoặc quan hệ sở hữu nào giới hạn quyền?
- **Nguồn điều kiện (authority):** hệ thống nào đáng tin cậy để xác nhận phòng ban, loại hợp đồng, trạng thái làm việc, chủ sở hữu dịch vụ?

Ví dụ, `REPORT_VIEWER` không nên mặc nhiên có quyền xem mọi báo cáo của mọi công ty con. Một quyết định chính xác hơn là “đọc báo cáo tài chính đã được cho phép **trong tenant mà danh tính được gán**”.

### 3.2. Thống nhất phạm vi và mức chi tiết

Role có thể được định nghĩa cho toàn tổ chức, riêng ứng dụng, tenant, khu vực dữ liệu hoặc môi trường. Cần chọn đơn vị phù hợp với mô hình trách nhiệm:

| Phạm vi | Ví dụ | Điểm cần chú ý |
|---|---|---|
| Toàn tổ chức | `ALL_EMPLOYEES` nhận quyền nội bộ cơ sở | Chỉ chứa quyền tối thiểu, không mặc định quyền dữ liệu nhạy cảm. |
| Theo chức năng nghiệp vụ | `FINANCE_ANALYST` | Owner nghiệp vụ xác nhận entitlement trong nhiều ứng dụng. |
| Theo ứng dụng | `CRM_READ_ONLY` | Owner ứng dụng chịu trách nhiệm mapping sang quyền native. |
| Theo tenant / đơn vị | `BILLING_APPROVER` với `tenantId=VN` | Ngăn quyền lan sang tenant khác. |
| Theo dự án | `PROJECT_EDITOR` của dự án A | Xử lý khi tham gia/rời dự án; tránh tạo role tĩnh cho từng tổ hợp người–dự án nếu ABAC tốt hơn. |
| Theo đặc quyền / thời gian | `PROD_DB_ADMIN` hiệu lực 1 giờ | Cần phê duyệt phù hợp, MFA/PAM/JIT và nhật ký sử dụng. |

### 3.3. Tách role khỏi trạng thái tài khoản

`employmentStatus=ACTIVE` có thể là điều kiện để một nhân viên đủ tư cách truy cập, nhưng **không tự trao role đặc quyền**. Tương tự, account đang `ACTIVE` ở IdP không chứng minh người dùng được phép giữ entitlement tại ứng dụng.

Ba lớp cần kiểm tra riêng:

1. **Danh tính hợp lệ:** có nguồn có thẩm quyền và trạng thái vòng đời phù hợp.
2. **Role assignment hợp lệ:** đáp ứng điều kiện, phê duyệt, SoD, scope và thời hạn.
3. **Quyền đang thực thi tại đích:** role/entitlement đã thực sự được cấp, còn hiệu lực hoặc được thu hồi.

## 4. Các nhóm role thường dùng

| Nhóm role | Mục đích | Ví dụ | Kiểm soát quan trọng |
|---|---|---|---|
| **Birthright / baseline** | Quyền cơ sở cần có khi thuộc một tập danh tính đã xác minh | `EMPLOYEE_BASIC` | Tối thiểu, chỉ cấp khi trạng thái hợp lệ, thu hồi khi Leaver. |
| **Business role** | Đại diện trách nhiệm nghiệp vụ | `FINANCE_ANALYST` | Owner nghiệp vụ, catalog entitlement, rà soát theo công việc. |
| **Application role** | Gắn với quyền trong một sản phẩm cụ thể | `EXPENSE_APP_APPROVER` | Mapping chính xác tới nhóm/permission tại ứng dụng. |
| **Privileged role** | Cấp quyền quản trị hoặc thay đổi dữ liệu nhạy cảm | `PROD_DB_ADMIN` | Phê duyệt, MFA/PAM, JIT, thời hạn, ghi nhật ký và SoD. |
| **Project / temporary role** | Truy cập cho một dự án, nhiệm vụ hoặc thời gian xác định | `PROJECT_A_REVIEWER` | Giới hạn scope và ngày hết hạn, gia hạn phải tái xác nhận. |
| **Machine / workload role** | Quyền cho dịch vụ hoặc tiến trình | `REPORT_JOB_READER` | Gắn workload ID, owner dịch vụ, least privilege và credential ngắn hạn khi có thể. |

**Birthright** không đồng nghĩa “mọi người nhận mọi ứng dụng”. Nó thường chỉ bao gồm những quyền nền tảng đủ an toàn, chẳng hạn truy cập cổng thông tin nội bộ theo nhóm danh tính tương ứng. Nhà thầu, khách hàng hoặc đối tác có baseline khác nhân viên; tránh cấp baseline cho tất cả tài khoản được tạo.

**Privileged role** không nên tồn tại vĩnh viễn chỉ vì người dùng từng cần quản trị. Khi điều kiện cho phép, hãy sử dụng truy cập theo phiên hoặc thời hạn rõ ràng; sau thời hạn, entitlement phải được gỡ ở hệ thống đích.

**Machine/workload role** là role kỹ thuật phục vụ dịch vụ, không phải business role dựa trên phòng ban của kỹ sư tạo tài khoản. Khi kỹ sư nghỉ việc, owner của dịch vụ phải được đánh giá/chuyển giao, còn việc giữ hay thu hồi role của workload dựa trên vòng đời dịch vụ và đánh giá rủi ro.

## 5. Lựa chọn RBAC, ABAC hay mô hình kết hợp

### 5.1. RBAC — quyền đi qua vai trò

**Role-Based Access Control (RBAC)** gán quyền cho role và gán role cho chủ thể. Ví dụ:

~~~text
FINANCE_ANALYST
  -> EXPENSE_REPORT_VIEW
  -> EXPORT_APPROVED_REPORTS

EMPLOYEE_BASIC
  -> VIEW_INTERNAL_PORTAL
~~~

Khi một nhân viên được xác nhận giữ vai trò nghiệp vụ `FINANCE_ANALYST`, IAM có thể cấp các entitlement đã được duyệt trong catalog. RBAC phù hợp khi trách nhiệm công việc tương đối ổn định và nhiều người cần bộ quyền giống nhau.

**Lợi ích:** quyền được tái sử dụng, dễ phê duyệt theo vai trò, giảm cấp từng permission riêng lẻ và dễ trả lời “vì sao người này có quyền?”. **Giới hạn:** nếu cứ tạo một role cho mọi tổ hợp phòng ban, tenant, dự án và tài nguyên, số lượng role có thể tăng mất kiểm soát (*role explosion*).

### 5.2. ABAC — quyền phụ thuộc thuộc tính và ngữ cảnh

**Attribute-Based Access Control (ABAC)** quyết định truy cập dựa trên thuộc tính của chủ thể, tài nguyên, hành động và môi trường. Ví dụ một người mang role `EXPENSE_APPROVER` chỉ được phê duyệt khoản chi khi:

- người dùng có trạng thái hợp lệ và không bị khóa bảo mật;
- phiếu chi thuộc tenant mà người dùng được phân công;
- số tiền nằm trong hạn mức phê duyệt;
- người phê duyệt khác người tạo phiếu chi;
- yêu cầu đáp ứng các điều kiện kiểm soát bổ sung.

Nhờ vậy, một role chung `EXPENSE_APPROVER` có thể kết hợp với `tenantId`, `approvalLimit` và `expense.requesterId` để tránh tạo hàng trăm role chỉ khác giới hạn dữ liệu.

### 5.3. Kết hợp RBAC + ABAC

Trong nhiều chương trình IAM, mô hình thực tế là **hybrid**: RBAC mô tả *loại công việc được phép làm*, ABAC giới hạn *với tài nguyên nào và trong bối cảnh nào*.

| Vấn đề | RBAC thích hợp khi | ABAC thích hợp khi |
|---|---|---|
| Phân biệt công việc | Nhiều người cùng làm công việc ổn định | Quyền phụ thuộc điều kiện thay đổi liên tục. |
| Phân vùng tenant/dự án | Ít scope, dễ quản lý bằng role gán kèm phạm vi | Nhiều tenant, dự án, resource có thuộc tính kiểm tra được. |
| Hạn mức phê duyệt | Vài cấp quyền rõ ràng | Hạn mức theo cấp bậc, số tiền hoặc thuộc tính giao dịch. |
| Phê duyệt và rà soát | Gán quyền theo business role dễ giải thích | Cần audit thuộc tính và chính sách đã dùng khi quyết định. |
| Rủi ro | Quá nhiều role và quan hệ kế thừa | Thuộc tính sai, cũ, không có owner hoặc policy khó kiểm thử. |

Mô hình hybrid **không có nghĩa** mọi kiểm tra được thực thi ở IdP. Ứng dụng, API gateway hoặc hệ thống policy engine nơi truy cập xảy ra phải có khả năng nhận biết các thuộc tính và thực thi giới hạn tương ứng. Truyền role qua SSO chỉ cung cấp dữ kiện cho ứng dụng; ứng dụng vẫn cần tự thực thi quy tắc ủy quyền.

## 6. Ví dụ thiết kế role model cho nghiệp vụ chi phí

Giả sử doanh nghiệp dùng ứng dụng **ExpenseHub** với bốn trách nhiệm nghiệp vụ: nhân viên tạo yêu cầu chi, quản lý phê duyệt, nhân viên thanh toán và kiểm toán viên xem dữ liệu. Chính sách yêu cầu người thực hiện thanh toán không đồng thời là người phê duyệt cuối cùng cùng một khoản chi.

### 6.1. Ma trận quyền

| Role | Xem phiếu trong scope | Tạo phiếu | Phê duyệt phiếu | Thực hiện thanh toán | Xem audit log |
|---|---:|---:|---:|---:|---:|
| `EXPENSE_REQUESTER` | Có, phiếu của mình | Có | Không | Không | Không |
| `EXPENSE_APPROVER` | Có, scope được giao | Không | Có, theo hạn mức | Không | Không |
| `PAYMENT_EXECUTOR` | Có, khoản cần xử lý | Không | Không | Có | Không |
| `EXPENSE_AUDITOR` | Có, scope kiểm toán | Không | Không | Không | Có, chỉ đọc |

Trong bảng, “Có” chỉ diễn tả **loại thao tác**. Hạn chế theo chủ sở hữu phiếu, tenant, hạn mức, trạng thái workflow và thời gian truy cập vẫn phải được policy ở nơi thực thi kiểm tra.

**Hai lớp SoD cần phân biệt:**

- **Static SoD:** không cho một người giữ đồng thời các role xung đột, chẳng hạn `EXPENSE_APPROVER` và `PAYMENT_EXECUTOR` nếu đó là quy định tổ chức.
- **Dynamic SoD:** một người có thể mang một role hợp lệ nhưng không được thực hiện hai bước xung đột trên **cùng giao dịch**, chẳng hạn người tạo phiếu không được tự phê duyệt phiếu của mình. Quy tắc này cần được ứng dụng hoặc workflow thực thi lúc thao tác.

Chỉ kiểm tra xung đột giữa tên các role là chưa đủ để đảm bảo SoD trong quy trình nghiệp vụ.

### 6.2. Phân biệt quyền nghiệp vụ và technical entitlement

Giả sử `EXPENSE_APPROVER` là business role. Để triển khai, IAM có thể ánh xạ nó sang:

~~~text
Business role: EXPENSE_APPROVER
    -> Application role: EXPENSE_APP_APPROVER
        -> Native entitlement: grp-expense-approvers
            -> Permission: expense:approve
~~~

Khi ứng dụng đổi tên group, business role có thể giữ nguyên nếu ý nghĩa nghiệp vụ không đổi. Nhóm IAM và application owner cập nhật mapping, kiểm tra kết quả và lưu lịch sử thay đổi. Không nên để bộ phận nhân sự phải biết tên mọi group kỹ thuật để phê duyệt quyền nghiệp vụ.

### 6.3. Kết hợp role và điều kiện ABAC

Một policy minh họa:

~~~text
ALLOW approve(expense) IF
    subject.authenticated == true
    AND subject.lifecycleStatus == ACTIVE
    AND subject.securityHold == false
    AND subject.hasEffectiveRole("EXPENSE_APPROVER", expense.tenantId)
    AND expense.tenantId == subject.approvalTenantId
    AND expense.amount <= subject.approvalLimit
    AND expense.requesterIdentityId != subject.identityId
    AND expense.status == PENDING_APPROVAL

DEFAULT DENY
~~~

Đây là **giả mã minh họa**, chưa phải policy có thể nạp trực tiếp vào sản phẩm. Quyết định truy cập còn có thể phụ thuộc MFA, phân quyền ủy nhiệm, rủi ro phiên, đơn vị tiền tệ và quy tắc phê duyệt nhiều cấp. Cần kiểm soát chất lượng thuộc tính `approvalLimit`, `approvalTenantId` và `requesterIdentityId`; nếu dữ liệu thiếu hoặc không đáng tin cậy, policy phải xử lý theo nguyên tắc an toàn phù hợp với tài nguyên.

## 7. Cách xây dựng role catalog

Role catalog là tài liệu quản trị chính thức cho từng role. Mỗi entry nên có ít nhất:

| Thuộc tính role | Ý nghĩa |
|---|---|
| `roleId`, `displayName` | Mã ổn định và tên dễ hiểu; không dùng tên nhóm hiện tại làm mã nghiệp vụ nếu nhóm có thể đổi. |
| `purpose`, `businessProcess` | Công việc nào cần role và quyết định nào cho phép cấp. |
| `ownerTeam`, `approver` | Ai chịu trách nhiệm nghiệp vụ và ai xét yêu cầu. |
| `scope` | Ứng dụng, tenant, tài nguyên, môi trường và giới hạn phù hợp. |
| `eligibility` | Thuộc tính danh tính và điều kiện xác minh để được đề nghị/gán role. |
| `entitlements` | Các quyền đích hoặc technical role cần provision. |
| `conflictsWith`, `constraints` | SoD, ràng buộc không cùng tồn tại và giới hạn theo giao dịch. |
| `approvalPolicy`, `duration` | Cấp tự động hay theo phê duyệt, thời hạn cấp, điều kiện gia hạn. |
| `reviewCadence`, `reviewer` | Chu kỳ rà soát và người chứng nhận quyền. |
| `riskTier`, `auditRequirements` | Mức rủi ro, bằng chứng, ghi log, MFA/PAM/JIT khi cần. |
| `lifecycleStatus`, `version` | Draft, active, deprecated, retired; quản lý thay đổi. |

Ví dụ YAML dưới đây giúp mô tả một role trong catalog. Tên hệ thống, mốc thời gian và enum chỉ là minh họa; không đại diện cho schema của công cụ IAM cụ thể.

~~~yaml
roleId: EXPENSE_APPROVER
displayName: Người phê duyệt chi phí
purpose: Phê duyệt yêu cầu chi trong phạm vi được phân công
ownerTeam: FinanceOperations
scope:
  application: ExpenseHub
  environment: production
  tenantBinding: assignmentTenantId
eligibility:
  identityTypes: [EMPLOYEE]
  employmentStatus: ACTIVE
  eligiblePositionCodes: [FIN_MANAGER, DEPT_HEAD]
assignment:
  mode: APPROVAL_REQUIRED
  approverRole: FINANCE_ACCESS_OWNER
  maxDuration: P90D
  requireReapprovalOnScopeChange: true
entitlements:
  - target: expensehub/corp-prod
    nativeRole: expense-approver
constraints:
  conflictsWith: [PAYMENT_EXECUTOR]
  denySelfApproval: true
  requireTenantMatch: true
review:
  cadence: P90D
  reviewer: FinanceOperations
riskTier: HIGH
lifecycleStatus: ACTIVE
version: 3
~~~

Ở ví dụ này, điều kiện `eligiblePositionCodes` chỉ cho biết **ai đủ điều kiện yêu cầu hoặc được xem xét**. Vì `assignment.mode=APPROVAL_REQUIRED`, việc thuộc vị trí nhân sự phù hợp **không tự cấp role**. `maxDuration` là giới hạn thời gian của assignment; khi hết hiệu lực phải thực hiện thu hồi tại đích và xác nhận kết quả.

## 8. Phương pháp phát hiện và thiết kế role

### 8.1. Top-down — bắt đầu từ nghiệp vụ

Làm việc với chủ quy trình, quản lý nghiệp vụ và owner ứng dụng để liệt kê nhiệm vụ cần thực hiện, tài nguyên bị tác động và ranh giới phê duyệt. Sau đó xác định tập entitlement tối thiểu cho mỗi nhóm nhiệm vụ.

Ví dụ, bộ phận tài chính phân biệt người **duyệt yêu cầu** với người **thực hiện thanh toán**. Phân tách này xuất phát từ kiểm soát nghiệp vụ trước khi nhóm IAM biết những permission kỹ thuật nào trong ExpenseHub đang thực hiện hai thao tác đó.

**Ưu điểm:** role dễ giải thích và bám trách nhiệm nghiệp vụ. **Giới hạn:** có thể bỏ sót quyền kỹ thuật đang tồn tại nếu không kiểm kê quyền thực tế.

### 8.2. Bottom-up — phân tích quyền thực tế

Thu thập group, permission, application role, access log, assignment và tần suất sử dụng từ các hệ thống trong account scope. Tìm những tập entitlement thường đi cùng nhau để đề xuất role.

**Điểm cần kiểm tra:** tập quyền phổ biến chưa chắc là tập quyền đúng. Quyền cấp nhầm từ nhiều năm trước hoặc account được sao chép sẽ xuất hiện trong dữ liệu; không được mặc nhiên đưa chúng vào role chuẩn chỉ vì nhiều người đang giữ.

### 8.3. Hybrid — khuyến nghị cho chương trình nhiều ứng dụng

Một cách làm thực tế:

1. Phân nhóm chủ thể và quy trình nghiệp vụ với owner.
2. Xác định các nhiệm vụ phải tách biệt và tài nguyên nhạy cảm.
3. Trích xuất entitlement đang tồn tại từ ứng dụng, cloud và directory.
4. Đề xuất role theo trách nhiệm, dùng dữ liệu hiện tại để kiểm tra độ đầy đủ.
5. Loại bỏ entitlement không cần thiết; rà soát quyền đặc biệt và SoD.
6. Thử role trên dữ liệu mẫu trước khi cấp tự động hoặc di chuyển quyền cũ.
7. Chốt owner, phê duyệt, mapping, vòng đời và cơ chế đối soát.

Khi một role bao gồm nhiều technical role, hãy kiểm tra **quyền hiệu lực** sau mọi quan hệ kế thừa. Một thay đổi ở role con có thể mở rộng quyền của nhiều business role; quá trình phê duyệt thay đổi phải biết được tác động này.

## 9. Quy tắc gán role và quyền thực tế

Thiết kế role model không kết thúc khi catalog đã có đủ tên. Cần mô tả đường đi từ **quyết định** đến **hành động provision** và **bằng chứng ở hệ thống đích**:

~~~mermaid
flowchart TD
    A["Sự kiện nguồn / yêu cầu quyền"] --> B["Kiểm tra identity, thuộc tính và account scope"]
    B --> C{"Đủ điều kiện role?"}
    C -- "Không" --> D["Từ chối / ghi lý do"]
    C -- "Có" --> E{"Vi phạm SoD hay policy?"}
    E -- "Có" --> D
    E -- "Không" --> F{"Cần phê duyệt?"}
    F -- "Có" --> G["Approver hợp lệ quyết định"]
    F -- "Không" --> H["Tạo role assignment có scope / expiry"]
    G -- "Được duyệt" --> H
    G -- "Từ chối" --> D
    H --> I["Tính entitlement dự kiến"]
    I --> J["Provision qua SCIM / API / PAM / IaC / manual"]
    J --> K["Đọc lại quyền thực tế ở đích"]
    K --> L{"Trạng thái khớp?"}
    L -- "Có" --> M["Ghi audit và lịch rà soát"]
    L -- "Không" --> N["Retry / xử lý sai lệch / ngoại lệ"]
    N --> K
~~~

**SSO** giúp người dùng đăng nhập liên kết qua SAML/OIDC và có thể truyền role/claim; **SCIM** giúp tạo/sửa/vô hiệu hóa tài khoản và nhóm khi hệ thống đích hỗ trợ. Chúng không tự kiểm chứng role model có hợp lệ về nghiệp vụ hoặc người dùng đã được thu hồi mọi quyền. Khi ứng dụng cấp quyền trực tiếp ngoài IdP, phải đối soát trạng thái ở ứng dụng.

### Mẫu bảng ánh xạ role sang entitlement

| Business role | Technical entitlement | Hệ thống/tenant | Phương thức | Owner xác nhận |
|---|---|---|---|---|
| `EMPLOYEE_BASIC` | `internal-portal-user` | Portal/corp | SCIM/API | Workplace IT |
| `FINANCE_ANALYST` | `reporting-finance-read` | Reporting/corp-prod | API | Finance Data Owner |
| `EXPENSE_APPROVER` | `expense-approver` | ExpenseHub/corp-prod | SCIM/API | Finance Operations |
| `PROD_DB_ADMIN` | DB privileged role theo phiên | DB/production | PAM/JIT | Infrastructure Security |

Role mapping cần bao gồm cả quyền **không** được cấp. Ví dụ `FINANCE_ANALYST` chỉ được đọc báo cáo đã duyệt và không có quyền thay đổi thông tin thanh toán. Với quyền nhạy cảm, cần thêm negative tests để chứng minh giới hạn thực thi.

## 10. Role model trong Joiner–Mover–Leaver

### Joiner — cấp đúng quyền ban đầu

Khi HRIS/VMS xác nhận quan hệ hợp lệ và đến thời điểm hiệu lực, IAM lấy thuộc tính danh tính, xác định role cơ sở, tìm business role phù hợp và gửi những yêu cầu cần phê duyệt. Cần lưu bằng chứng nguồn, role assignment và hành động đã thực thi.

Ví dụ: người mới vào bộ phận tài chính có thể được cấp `EMPLOYEE_BASIC` theo chính sách, còn `EXPENSE_APPROVER` chỉ được cấp sau phê duyệt. Không nên suy từ `departmentId=FIN` rằng ai cũng có quyền phê duyệt thanh toán.

### Mover — tính lại quyền khi vai trò công việc đổi

Khi phòng ban, chức danh, dự án, khu vực dữ liệu hoặc quan hệ hợp đồng thay đổi, IAM so sánh tập role **mong muốn** với tập role **hiện có**:

~~~text
previousRoles = validAssignmentsBeforeChange
desiredRoles  = evaluatePolicy(newIdentityAttributes, approvals, scope)

rolesToRevoke = previousRoles - desiredRoles
rolesToGrant  = desiredRoles - previousRoles

for each roleToRevoke:
    revokeMappedEntitlements(roleToRevoke)
    verifyRemovalAtTargets()

for each roleToGrant:
    validateEligibilityApprovalAndSoD()
    grantMappedEntitlements(roleToGrant)
    verifyGrantAtTargets()

reconcileEffectiveAccessAndRecordAudit()
~~~

Đây là giả mã. Thực tế cần xử lý nhiều role cùng cấp một entitlement: **chỉ thu hồi entitlement khi không còn căn cứ hợp lệ khác** để giữ nó. Việc tính khác biệt phải xét scope (tenant, dự án, môi trường), ngày hiệu lực, phê duyệt, quyền cấp trực tiếp và trạng thái ở đích. Với trường hợp có xung đột nguy hiểm, chính sách có thể yêu cầu **thu hồi quyền cũ và xác nhận trước khi cấp quyền mới** để tránh khoảng thời gian giữ cả hai quyền.

Ví dụ nhân viên chuyển từ người duyệt chi sang người thực hiện thanh toán. Nếu SoD không cho giữ đồng thời `EXPENSE_APPROVER` và `PAYMENT_EXECUTOR`, không thể chỉ thêm role mới rồi dự kiến xóa role cũ sau. Cần kiểm soát thứ tự thao tác và xác minh không còn quyền phê duyệt ở đích.

### Leaver — thu hồi role theo toàn bộ đường cấp quyền

Khi quan hệ lao động/hợp đồng kết thúc hoặc bị chấm dứt khẩn cấp, IAM phải xử lý tất cả assignment và entitlement thuộc account scope: vai trò tự động, vai trò phê duyệt thủ công, quyền tạm thời, nhóm IdP, quyền cloud trực tiếp và quyền trong ứng dụng cũ.

**Vô hiệu hóa IdP không chứng minh đã thu hồi mọi role.** Account local, token đã cấp, quyền trực tiếp tại ứng dụng hoặc tài khoản phụ có thể còn tồn tại. Sau hành động thu hồi cần đọc lại trạng thái ở đích hoặc có bằng chứng do owner xác nhận; trường hợp lỗi phải được theo dõi như ngoại lệ chưa hoàn tất.

### Lưu ý về tình trạng khóa bảo mật

HRIS có thể báo nhân viên vẫn `ACTIVE`, nhưng bộ phận an ninh đặt `securityHold=true`. Role assignment có thể vẫn tồn tại trong catalog cho mục đích quản trị, song quyền truy cập hiệu lực phải bị ngăn theo chính sách. Một event nhân sự mới không được tự ý gỡ khóa bảo mật; lệnh gỡ khóa phải tới từ chủ thể có thẩm quyền.

## 11. SoD, least privilege và vai trò đặc quyền

### Static và dynamic Separation of Duties

**SoD** bảo đảm một người hoặc một thực thể không có khả năng tự thực hiện toàn bộ chuỗi thao tác có xung đột lợi ích.

| Loại kiểm soát | Câu hỏi cần kiểm tra | Ví dụ |
|---|---|---|
| **Static SoD** | Có được sở hữu đồng thời hai role không? | Không cho cùng một người vừa duyệt chi vừa thanh toán nếu quy trình quy định. |
| **Dynamic SoD** | Trong giao dịch hiện tại, người này có được thực hiện hành động không? | Người tạo phiếu không được phê duyệt chính phiếu đó. |
| **Approval separation** | Người phê duyệt role có độc lập và đủ thẩm quyền không? | Người xin quyền không tự phê duyệt quyền đặc biệt của mình. |
| **Privileged elevation** | Có bắt buộc nâng quyền theo thời gian và lý do cụ thể không? | Chỉ cấp admin production trong cửa sổ bảo trì đã duyệt. |

Các kiểm tra cần bao gồm **quyền hiệu lực**, kể cả role kế thừa, quyền cấp trực tiếp và nhóm động. Nếu hai role không xung đột tên nhưng cùng dẫn tới các permission xung đột, kiểm tra tên role đơn thuần sẽ bỏ sót SoD.

### Least privilege và giới hạn theo phạm vi

Role nên cho phép **ít hành động và ít tài nguyên nhất** cần để hoàn thành nhiệm vụ. Đặc biệt, không nên tạo role `GLOBAL_ADMIN` chỉ để người dùng xem báo cáo ở một tenant. Khi có thể, kết hợp role theo chức năng với giới hạn ABAC về tenant, dự án, ownership hoặc thời gian.

Với role đặc quyền, bổ sung MFA/phương thức xác thực mạnh, quản lý phiên, cấp quyền theo nhu cầu (JIT), expiry ngắn và nhật ký. Cơ chế break-glass phục vụ khôi phục khẩn cấp thường có quản trị riêng, không thể đơn giản sao chép vai trò quản trị thông thường.

### Quyền ngoại lệ

Có thể có tình huống người dùng cần quyền ngoài role chuẩn. Ngoại lệ phải có **lý do nghiệp vụ, người phê duyệt, scope tài nguyên, thời điểm bắt đầu/kết thúc, bản ghi audit và trách nhiệm rà soát**. Không nên biến ngoại lệ tạm thời thành quyền vĩnh viễn chỉ vì không có quy trình tự thu hồi.

Đối với ngoại lệ vi phạm SoD, cần có kiểm soát bù trừ được phê duyệt rõ ràng và theo quy định quản trị của tổ chức; không phải mọi vi phạm SoD đều có thể cho phép chỉ bằng một chữ ký.

## 12. Role dành cho tài khoản dịch vụ và workload

Đối với danh tính phi con người, **owner của dịch vụ, workload ID, môi trường, tài nguyên và mục đích** thường là thuộc tính quan trọng hơn job title hoặc department của một cá nhân.

Giả sử một dịch vụ tạo báo cáo đêm cần đọc dữ liệu đã tổng hợp ở production. Role `REPORT_JOB_READER` có thể chỉ bao gồm:

- quyền đọc đúng dataset được duyệt;
- quyền ghi log xử lý vào vùng riêng;
- quyền truy cập secrets cần thiết cho công việc;
- giới hạn theo workload identity và môi trường production.

Không nên cấp quyền database administrator hoặc toàn bộ cloud project chỉ vì việc cấp dễ hơn. Nếu nền tảng hỗ trợ workload federation hoặc credential ngắn hạn, mô hình này giúp giảm phụ thuộc vào khóa tĩnh.

Khi kỹ sư từng sở hữu workload nghỉ việc, IAM phải kích hoạt **rà soát và chuyển ownership**; nếu credential gắn với người đó, cần vô hiệu hóa hoặc luân chuyển phù hợp. Quyết định dừng workload role cần dựa trên vòng đời dịch vụ hoặc rủi ro hiện hữu, bởi tự động xóa role của dịch vụ chỉ vì kỹ sư rời công ty có thể gây gián đoạn sản xuất.

## 13. Quản trị phiên bản và vòng đời của chính role

Không chỉ **người dùng** có vòng đời; **role** cũng cần được quản lý:

1. **Draft:** nêu mục đích, owner, entitlement, eligibility, SoD và đánh giá tác động.
2. **Approved:** chủ quy trình, owner ứng dụng và bộ phận kiểm soát có liên quan xác nhận.
3. **Active:** role được phép gán theo policy; mọi mapping có version.
4. **Deprecated:** ngừng cấp mới; lập kế hoạch chuyển assignment sang role thay thế.
5. **Retired:** xác nhận không còn assignment và entitlement phụ thuộc; lưu audit theo chính sách.

Thay đổi quyền trong một role có thể tác động tới **tất cả thành viên đang giữ role**, kể cả những người không gửi yêu cầu mới. Vì vậy cần phân tích tác động trước khi thêm quyền, kiểm thử SoD, có lịch triển khai, cơ chế rollback và đối soát quyền thực tế sau khi áp dụng.

Một role không có owner hoặc không còn mục đích nghiệp vụ rõ ràng là ứng viên cần xem xét ngừng sử dụng. Không nên xóa role chỉ vì không thấy login gần đây nếu nó phục vụ quy trình chạy theo kỳ; cần đối chiếu nguồn nghiệp vụ và log hoạt động liên quan.

## 14. Quy trình thực hành thiết kế role model

Một dự án triển khai có thể theo các bước sau:

| Bước | Việc thực hiện | Đầu ra |
|---|---|---|
| **1. Xác định phạm vi** | Liệt kê nhóm danh tính, ứng dụng, tenant, privileged account, service account và nguồn vòng đời. | Bản đồ chủ thể, tài nguyên, owner và account scope. |
| **2. Thu thập nhu cầu nghiệp vụ** | Phỏng vấn process owner, xác định chức năng và thao tác có xung đột. | Danh sách nhiệm vụ, action/resource và SoD. |
| **3. Kiểm kê quyền hiện tại** | Lấy user–group–permission mapping, quyền cấp trực tiếp và quyền không sử dụng. | Entitlement inventory có nguồn và chủ sở hữu. |
| **4. Đề xuất role** | Kết hợp top-down với bottom-up, phân tách business/technical/privileged role. | Role catalog ở trạng thái draft. |
| **5. Thiết kế điều kiện** | Xác định eligibility, approval, ABAC, scope, expiry, inheritance và SoD. | Chính sách gán và kiểm tra truy cập. |
| **6. Kiểm thử và pilot** | Chạy thử Joiner/Mover/Leaver, quyền hợp lệ và quyền phải từ chối. | Báo cáo test, danh sách sai lệch và đánh giá rủi ro. |
| **7. Tích hợp triển khai** | Ánh xạ role vào IdP, SCIM/API, PAM, cloud/ứng dụng; xử lý legacy manual. | Provisioning flow có readback và audit. |
| **8. Vận hành và tái đánh giá** | Rà soát role, entitlement, assignment, SoD, drift và role không còn owner. | Báo cáo governance, cải tiến và xử lý ngoại lệ. |

### Các tình huống cần kiểm thử

Ít nhất nên có:

1. Joiner có đủ thuộc tính nhưng **chưa được phê duyệt** role nhạy cảm → không được cấp role.
2. Joiner được duyệt role đọc báo cáo theo tenant A → không thể xem tenant B.
3. Mover từ `EXPENSE_APPROVER` sang `PAYMENT_EXECUTOR` → không có khoảng thời gian giữ hai quyền xung đột.
4. Leaver → role bị thu hồi tại cả IdP và ứng dụng; account local hoặc quyền cấp trực tiếp không bị bỏ sót.
5. Role assignment hết hạn → quyền ở đích được thu hồi và xác minh.
6. Đổi entitlement mapping của role → các thành viên hiện tại chỉ nhận quyền đã được owner chấp thuận.
7. HRIS báo `ACTIVE` nhưng `securityHold=true` → không có truy cập hiệu lực.
8. Workload owner nghỉ việc → yêu cầu chuyển owner và rà soát credential, không mất kiểm soát account dịch vụ.
9. Sự kiện đến trễ/trùng hoặc SCIM/API trả lỗi → IAM không lặng lẽ xác nhận quyền đã thay đổi thành công.

## 15. Chỉ số đánh giá chất lượng role model

| Chỉ số | Ý nghĩa quản trị |
|---|---|
| **Role coverage** | Tỷ lệ entitlement/assignment nằm trong role được phê duyệt so với quyền cấp trực tiếp chưa giải thích được. |
| **Owner coverage** | Tỷ lệ role có owner nghiệp vụ và owner kỹ thuật còn hiệu lực. |
| **Role assignment accuracy** | Tỷ lệ assignment đang tồn tại thỏa eligibility, scope, phê duyệt và expiry. |
| **Privilege creep / Mover drift** | Quyền cũ còn lại sau thay đổi vai trò; đo cả số lượng và thời gian tồn dư. |
| **SoD violation rate** | Các xung đột quyền thực tế hoặc giao dịch chưa được xử lý và phân loại rủi ro. |
| **Role proliferation** | Số role mới, role chỉ có một thành viên, role gần trùng nhau hoặc role không có người dùng. |
| **Access review completion** | Tỷ lệ review hoàn thành đúng hạn và hành động thu hồi được thực thi thật. |
| **Leaver deprovision latency** | Thời gian từ mốc Leaver hiệu lực đến khi entitlement ở các đích được xác minh đã thu hồi. |
| **Provisioning/reconciliation drift** | Chênh lệch giữa role/entitlement mong muốn và quyền thực tế tại ứng dụng. |

Không nên tối ưu **số role càng ít càng tốt** mà bất chấp ý nghĩa nghiệp vụ; cũng không nên tối ưu **số role càng nhiều càng chi tiết**. Tiêu chí chính là các role đủ rõ để kiểm toán, ít trùng lặp, phản ánh công việc và có thể thực thi ổn định.

## 16. Sai lầm thường gặp

- **Role bằng chức danh nhân sự:** tự động gán đặc quyền cho mọi người có cùng job title, dù nhiệm vụ thực tế khác nhau.
- **Role bằng group kỹ thuật:** không biết group cấp quyền gì, ai chịu trách nhiệm và vì sao một role cần nó.
- **Sao chép entitlement hiện tại để tạo role chuẩn:** hợp thức hóa cả những quyền tồn dư từ lịch sử.
- **Gộp mọi scope vào một role rộng:** `ADMIN` có quyền trên nhiều tenant hoặc production dù chỉ cần một môi trường.
- **Role explosion:** mỗi tổ hợp chức danh–đơn vị–dự án thành một role riêng thay vì dùng ABAC hoặc role assignment có scope.
- **Kế thừa role không kiểm tra quyền hiệu lực:** role cha hoặc nhóm lồng nhau có thể mang thêm quyền nguy hiểm.
- **Chỉ kiểm tra SoD lúc cấp role:** bỏ sót xung đột phát sinh từ role kế thừa, quyền trực tiếp và giao dịch thực tế.
- **Chỉ thêm role khi Mover:** quyền của vị trí cũ không được thu hồi, tích lũy thành privilege creep.
- **Đánh dấu thu hồi thành công khi đã gửi SCIM:** ứng dụng đích có thể lỗi, chưa xử lý hoặc vẫn còn account local.
- **Dùng role người dùng cho service account:** thay đổi nhân sự làm gián đoạn workload hoặc bỏ qua vòng đời đặc thù của dịch vụ.
- **Không quản trị thay đổi role:** thêm một entitlement vào role có thể mở rộng quyền của hàng trăm người mà không có phê duyệt.

## 17. Bài tập áp dụng

Một công ty có hệ thống yêu cầu chi phí, công cụ báo cáo tài chính và môi trường cloud. Các nhóm người dùng gồm nhân viên thông thường, trưởng bộ phận, nhân viên thanh toán, kiểm toán nội bộ và kỹ sư vận hành. Doanh nghiệp có quy định người tạo khoản chi không được tự phê duyệt và người phê duyệt không được đồng thời thực hiện thanh toán. Một kỹ sư vận hành chỉ cần quyền quản trị cloud production trong thời gian khắc phục sự cố.

Hãy thiết kế role model ở mức đủ để đưa vào catalog:

1. Đề xuất **5–7 role** với `roleId`, mục đích, owner, entitlement và scope rõ ràng; tách ít nhất một business role và một technical role.
2. Quy định vai trò nào cấp theo birthright, vai trò nào phải phê duyệt và vai trò nào cần expiry ngắn.
3. Viết ít nhất **hai ràng buộc SoD**, gồm một static SoD và một dynamic SoD trên từng giao dịch.
4. Minh họa điều kiện ABAC cho phê duyệt khoản chi theo tenant, hạn mức và người tạo phiếu.
5. Trình bày quy trình Mover khi một nhân viên chuyển từ phê duyệt sang thanh toán, bảo đảm không giữ hai quyền xung đột trong quá trình chuyển.
6. Mô tả cách IAM xác minh Leaver đã thu hồi quyền tại IdP, ứng dụng hỗ trợ SCIM và cloud cấp quyền trực tiếp.
7. Đề xuất ba chỉ số đo lường để phát hiện role drift, SoD và quyền tồn dư.

**Tiêu chí đánh giá:** mọi role có mục đích nghiệp vụ, owner, scope và tập quyền tối thiểu; eligibility không bị nhầm với phê duyệt; giới hạn tenant/tài nguyên được thực thi; có kiểm soát xung đột nhiệm vụ; Mover/Leaver dẫn đến thay đổi quyền thực tế và bằng chứng đối soát; account đặc quyền và phi con người có vòng đời phù hợp.

Role model hoàn chỉnh giúp chương trình IAM giải thích **ai có quyền gì, vì sao có quyền đó, ai chịu trách nhiệm và khi nào quyền phải chấm dứt**. Khi các quy tắc này gắn chặt với nguồn danh tính, account scope và luồng JML, tổ chức mới có nền tảng đáng tin cậy để tự động hóa cấp quyền, kiểm toán và giảm quyền truy cập tồn dư.
