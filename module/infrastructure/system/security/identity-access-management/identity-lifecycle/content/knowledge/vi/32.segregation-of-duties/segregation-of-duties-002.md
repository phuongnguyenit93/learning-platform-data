# Xung đột quyền trong Segregation of Duties và IAM Identity Lifecycle

## 1. Xung đột quyền là gì?

**Xung đột quyền (conflicting permissions / toxic combinations)** là tình huống một chủ thể sở hữu hoặc có thể sử dụng **hai hay nhiều quyền mà khi kết hợp lại sẽ vượt ranh giới kiểm soát được tổ chức quy định**. Trong quản lý truy cập, xung đột thường xuất hiện khi cùng một người có khả năng **khởi tạo và phê duyệt**, **tạo và thanh toán**, **cấp quyền và tự chứng nhận quyền**, hoặc **triển khai và tự bỏ qua bước kiểm tra độc lập**.

Ví dụ, hệ thống tài chính tách hai hành động:

- **vendor.create**: tạo nhà cung cấp mới.
- **vendor.payment.approve**: chấp thuận thanh toán cho nhà cung cấp.

Nếu một cá nhân có cả hai quyền trong cùng phạm vi kiểm soát, họ có thể tạo nhà cung cấp giả rồi phê duyệt thanh toán cho đối tượng đó. Đây là một **tổ hợp quyền tiềm ẩn rủi ro gian lận**. Tổ chức có thể quy định **không cho cùng một cá nhân nắm cả hai quyền** hoặc áp những ràng buộc cụ thể hơn theo quy trình, hạn mức và trách nhiệm.

Trong **Segregation of Duties (SoD)**, việc nhận diện và xử lý xung đột quyền giúp tách các nhiệm vụ nhạy cảm giữa những chủ thể hoặc bước kiểm soát độc lập. **Không phải mọi trường hợp có hai role đều là xung đột**; xung đột phụ thuộc **action, tài nguyên, phạm vi, thời điểm, nguồn quyền và quy tắc SoD**.

Bài thuộc mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tìm hiểu quản lý danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo account, cấp quyền, rà soát và thu hồi sau thay đổi vai trò. Nội dung gắn với **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và mục tiêu giảm **quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích xung đột quyền và phân biệt nó với **quyền rộng, quyền dư, SoD violation và actual misuse**.
2. Phân biệt **static SoD**, **dynamic SoD** và xung đột theo quy trình.
3. Phát hiện xung đột ở mức **effective permissions**, bao gồm role hierarchy, nested group, direct grants và đa ứng dụng.
4. Xét đúng **subject, action, resource, scope, điều kiện, thời điểm và quan hệ công việc**.
5. Xây dựng **SoD rule catalog/conflict matrix** và xử lý false positive.
6. Áp dụng kiểm soát **preventive, detective, corrective và compensating**.
7. Tích hợp kiểm soát với **access request, approval workflow, access review, PAM/JIT** và quản trị policy.
8. Kiểm chứng việc gỡ quyền khi **Mover hoặc Leaver** thay vì chỉ thay cấu hình IdP.
9. Kiểm thử, theo dõi và xử lý ngoại lệ xung đột quyền trong hệ thống thực tế.

## 2. Vì sao xung đột quyền là vấn đề nghiêm trọng?

Trong nghiệp vụ nhạy cảm, một người nắm toàn bộ các bước của quy trình có thể **làm mất cơ chế kiểm tra độc lập**. Điều này làm tăng khả năng:

- **Gian lận:** tự tạo dữ liệu hoặc đối tượng rồi tự chấp thuận giao dịch.
- **Lạm dụng đặc quyền:** tự cấp role cao, thay đổi policy hoặc xóa dấu vết.
- **Sai sót không được phát hiện:** cùng một người vừa thay đổi vừa kiểm tra kết quả.
- **Quyền tồn dư sau Mover:** chuyển từ bộ phận này sang bộ phận khác nhưng giữ những action xung đột.
- **Khó quy trách nhiệm:** nhiều bước nhạy cảm không có người kiểm soát độc lập.
- **Vi phạm chính sách nội bộ hoặc nghĩa vụ kiểm soát:** chứng nhận quyền không phản ánh tập quyền thực tế.

Ví dụ, một người có thể **deploy** một bản phát hành và **approve production change** cho chính bản phát hành đó. Nếu tổ chức yêu cầu peer review độc lập, tổ hợp quyền hoặc việc thực thi này là vấn đề ngay cả khi không xảy ra tấn công.

**Có xung đột quyền không đồng nghĩa đã xảy ra gian lận.** Đây là **tín hiệu rủi ro hoặc vi phạm chính sách** cần được đánh giá và xử lý. Ngược lại, **không phát hiện cặp role xung đột không chứng minh an toàn**, vì một actor có thể lạm dụng một role quá rộng hoặc các đường truy cập khác.

## 3. SoD, least privilege và authorization liên hệ thế nào?

Ba khái niệm bổ trợ nhưng không đồng nhất:

| Nguyên tắc | Câu hỏi | Ví dụ |
|---|---|---|
| **Least Privilege** | Chủ thể có ít quyền nhất cần cho công việc chưa? | Analyst chỉ cần report.read |
| **Segregation of Duties** | Một chủ thể có nắm hoặc thực hiện đồng thời nhiệm vụ cần độc lập không? | Người tạo vendor không phê duyệt chi trả cho chính vendor |
| **Authorization** | Subject này có được thực hiện action trên resource trong context hiện tại? | invoice.approve trên INV-873 có được Permit? |
| **Access Review** | Quyền đang tồn tại còn có căn cứ hợp lệ không? | Có giữ FINANCE_APPROVER sau Mover? |
| **Audit** | Ai đã làm gì, ai đã cho phép và có tác dụng thực tế gì? | Lịch sử tạo, phê duyệt, thanh toán |

Một action có thể đáp ứng **least privilege** khi xét riêng lẻ nhưng trở thành nguy hiểm **khi kết hợp với action khác**. Ngược lại, hai action nhìn có vẻ xung đột nhưng áp dụng cho **hai tenant được tách biệt chặt** có thể không vi phạm chính sách.

### Đầu vào một quyết định SoD

\[
SoDDecision = F(Subject,\ EffectivePermissions,\ Actions,\ Resources,\ Context,\ History,\ Policy)
\]

Công thức là mô hình khái niệm, không phải chuẩn cú pháp của một policy engine. Những dữ liệu như role, department, tenant, createdBy, workflow history và grant expiration phải có **nguồn đáng tin**, không lấy mù quáng từ client.

## 4. Static SoD và Dynamic SoD

### Static Separation of Duties (SSD)

**Static SoD** thường hạn chế **việc cùng được gán** những role/permission xung đột. Hệ thống có thể từ chối cấp quyền thứ hai dù chủ thể chưa thực hiện hành động.

Ví dụ chính sách:

> Một người không được đồng thời giữ quyền **vendor.create** và **vendor.payment.approve** trong cùng phạm vi pháp nhân.

Khi Access request xin thêm vendor.payment.approve, IAM/IGA tính quyền hiện tại. Nếu user đã có vendor.create trong scope trùng nhau, yêu cầu phải **Deny, điều chỉnh hoặc đưa qua quy trình ngoại lệ có kiểm soát**.

### Dynamic Separation of Duties (DSD)

**Dynamic SoD** kiểm tra **lúc sử dụng quyền, lúc kích hoạt role hoặc khi chuyển trạng thái giao dịch**. Cùng một người có thể sở hữu hai chức năng tổng quát nhưng **không được thực hiện những bước xung đột trên cùng giao dịch**.

Ví dụ:

> Một approver có role FINANCE_APPROVER được duyệt hóa đơn của người khác, nhưng không được duyệt hóa đơn do chính mình tạo.

Điều kiện quan trọng là **invoice.createdBy != authenticatedSubject.id**, không chỉ kiểm role.

### So sánh

| Đặc điểm | Static SoD | Dynamic SoD |
|---|---|---|
| **Thời điểm** | Khi gán role/entitlement hoặc định kỳ | Khi kích hoạt/quyết định một action/giao dịch |
| **Dữ liệu chủ yếu** | Effective permissions, assignment, scope | Permission, resource state, actor history, context |
| **Ví dụ** | Không giữ đồng thời quyền create và approve trong cùng scope | Không tự approve chứng từ do chính mình lập |
| **Điểm thực thi** | IAM/IGA, access request, role assignment | API/service/PDP/PEP, workflow engine |
| **Ưu điểm** | Ngăn trước toxic role combinations | Linh hoạt khi công việc cần nhiều chức năng |
| **Giới hạn** | Có thể chặn nhầm khi scope khác nhau | Không an toàn nếu một đường thực thi bỏ qua kiểm tra |

**SSD và DSD không thay thế nhau.** Với hành động có thể gây tổn hại lớn, tổ chức có thể dùng cả hai: ngăn cấp role xung đột từ đầu và kiểm tra người thực hiện từng bước ở API.

## 5. Xung đột theo nhiệm vụ và theo lịch sử giao dịch

Nhiều quy trình cần hơn hai bước, ví dụ:

~~~mermaid
flowchart LR
    A[Tạo nhà cung cấp] --> B[Kiểm tra thông tin ngân hàng]
    B --> C[Phê duyệt nhà cung cấp]
    C --> D[Tạo lệnh thanh toán]
    D --> E[Phê duyệt thanh toán]
    E --> F[Thực thi thanh toán]
    F --> G[Đối soát và kiểm toán]
~~~

Chính sách có thể yêu cầu:

- Người **tạo vendor** không được **phê duyệt vendor đó**.
- Người **thay đổi tài khoản ngân hàng** phải khác người **xác nhận thay đổi**.
- Người **tạo lệnh thanh toán** không được **tự phê duyệt lệnh của mình**.
- Người **thực thi thanh toán** không được **tự xác nhận kết quả đối soát** khi quy trình yêu cầu kiểm soát độc lập.

Đây là **workflow-level SoD**: quyết định phụ thuộc **đối tượng cụ thể và lịch sử ai đã làm các bước trước**, không chỉ quyền tĩnh.

### Vì sao check người tạo không phải lúc nào cũng đủ?

Một hóa đơn có thể được tạo bởi service account, nhập từ hệ thống ngoài hoặc qua người được ủy quyền. Khi đó cần ghi **human actor, initiating principal, delegatedBy, responsible owner và transaction provenance** phù hợp, tránh để bot trở thành cách che giấu người phê duyệt thực.

**Dữ liệu lịch sử nghiệp vụ phải được bảo vệ khỏi sửa trái phép**, nếu không attacker có thể sửa createdBy rồi tự approve.

## 6. Phân biệt conflict ở role-level và permission-level

Nhiều hệ thống bắt đầu bằng quy tắc “role A không được đi cùng role B”. Cách này dễ triển khai nhưng có thể bỏ sót trường hợp **cùng permission được cấp từ role khác**.

Ví dụ:

| Role | Permissions |
|---|---|
| **PROCUREMENT_CREATOR** | vendor.create, vendor.edit |
| **FINANCE_APPROVER** | vendor.payment.approve |
| **PROCUREMENT_SUPERUSER** | vendor.create, vendor.edit, vendor.payment.approve |
| **AUDIT_VIEWER** | vendor.read, payment.read |

Một rule chỉ cấm **PROCUREMENT_CREATOR + FINANCE_APPROVER** không ngăn người dùng có **PROCUREMENT_SUPERUSER** được cấp cả hai quyền. Phải tính **effective permission set** của từng subject.

### Nguyên tắc thiết kế

1. Xác định **permission/action nhạy cảm thực sự**.
2. Liệt kê role, group, policy và direct grant có thể cấp chúng.
3. Kiểm cả **role hierarchy, group nesting** và mapping ở ứng dụng đích.
4. Tính **scope của từng permission**, không xem permission chỉ là một chuỗi.
5. Áp rule trước khi cấp thêm quyền **và** khi phát hiện thay đổi quyền ngoài quy trình.
6. Kiểm **dynamic SoD tại resource server** với các nghiệp vụ cần tách nhiệm vụ theo từng transaction.

**Tên role không phải căn cứ đủ để kết luận xung đột hoặc không xung đột.**

## 7. Effective permissions: quyền thực tế qua nhiều đường

Một người có thể được cấp **payment.approve** qua group A, còn **vendor.create** từ local account B, dù IGA chỉ nhìn thấy một role FINANCE_READER.

~~~mermaid
flowchart TD
    P[Person / Identity ID] --> A[IdP account]
    P --> B[Local application account]
    A --> G[Group: Finance Approvers]
    G --> R[Role: Payment Approver]
    R --> PAY[payment.approve]
    B --> DG[Direct grant: Vendor Editor]
    DG --> VEN[vendor.create]
    PAY --> SOD[SoD conflict evaluation]
    VEN --> SOD
~~~

Nếu đánh giá chỉ dựa vào role có trong **IdP token**, hệ thống có thể bỏ sót xung đột ở **SaaS local role, cloud IAM, database hoặc service account**.

### Những nguồn quyền cần inventory

| Nguồn | Ví dụ | Vấn đề |
|---|---|---|
| **RBAC role trực tiếp** | FINANCE_APPROVER | Cần biết mapping permission thật |
| **Role hierarchy** | ADMIN kế thừa FINANCE_APPROVER | Có thể cấp quyền ngầm |
| **Nested group** | Group A là member của Group B | Quyền qua nhiều tầng |
| **Direct grant** | User được cấp SELECT trực tiếp | Không nằm trong catalog role |
| **SCIM Group** | Group.members ở SaaS | Target mapping có thể khác IdP |
| **Local admin** | Account ở ứng dụng legacy | Không chịu tự động IdP disable |
| **Cloud IAM** | Role binding theo resource | Cần điều kiện và scope |
| **PAM/JIT** | Eligible + Active privileged grants | Cần phân biệt khả năng kích hoạt và quyền đang chạy |
| **Delegation/ReBAC** | Approver được ủy quyền | Quan hệ có thời hạn |
| **Token/session** | Claim cũ còn trong JWT | Quyền thực thi có thể khác desired state |

**Đánh giá xung đột đầy đủ cần nêu rõ mức độ bao phủ.** Nếu chưa đọc được local grants của một SaaS thì không thể kết luận “không còn xung đột” cho toàn bộ hệ thống.

## 8. Scope và điều kiện: hai quyền giống tên chưa chắc xung đột

Một permission thường có **action và phạm vi**:

\[
Grant = (Subject,\ Action,\ ResourceScope,\ EffectiveInterval,\ Conditions)
\]

Hai quyền có thể xung đột chỉ khi **phạm vi kiểm soát giao nhau** hoặc chính sách quy định cấm ở cấp toàn tổ chức.

Ví dụ:

| Quyền 1 | Quyền 2 | Nhận xét |
|---|---|---|
| vendor.create tại tenant A | vendor.payment.approve tại tenant A | Có thể xung đột theo static SoD |
| vendor.create tại tenant A | vendor.payment.approve tại tenant B | Không tự kết luận xung đột nếu tenant tách biệt thật |
| invoice.create tại team X | invoice.approve tại team X | Có thể cần dynamic SoD theo invoice |
| deployment.author trong dev | deployment.release ở prod | Cần xem workflow và chính sách CI/CD |
| user.assignRole cho team A | accessReview.certify cho team B | Phụ thuộc phạm vi review và SoD |
| report.read | report.export | Không mặc nhiên xung đột; nhưng export có thể cần approval riêng |

### Nguy cơ suy luận sai về tenant

Hai tenant được định nghĩa riêng trong dữ liệu nhưng **admin role có thể có phạm vi toàn organization**, hoặc hệ thống có quyền cross-tenant. Khi đó đánh giá “tenant khác nên không trùng” có thể sai.

**Scope phải được lấy từ nguồn đáng tin và thực thi tại target**, không chỉ từ trường request do client nhập.

### Điều kiện thời gian

Hai permission được cấp trong các khoảng thời gian không chồng lấn có thể không tạo **xung đột đồng thời**, nhưng vẫn cần kiểm soát **token, session, background job, credential đã phát** và lịch sử giao dịch. DSD vẫn có thể cấm một người phê duyệt chính đối tượng họ đã tạo **từ trước khi chuyển role**.

## 9. Ma trận xung đột quyền (SoD conflict matrix)

Một bước cốt lõi là xây dựng **SoD rule catalog** hoặc **conflict matrix** trên các **permission nghiệp vụ**, rồi ánh xạ tới technical entitlement.

| Rule ID | Permission A | Permission B | Loại kiểm soát | Scope và ghi chú |
|---|---|---|---|---|
| **SOD-FIN-01** | vendor.create | vendor.payment.approve | Static hoặc hybrid | Cùng legal entity |
| **SOD-FIN-02** | invoice.create | invoice.approve | Dynamic | Cùng invoice hoặc cùng chủ thể tạo |
| **SOD-IAM-01** | user.assignRole | accessReview.certifyOwnGrant | Static/workflow | Cùng subject/grant |
| **SOD-DEP-01** | release.author | release.approve | Dynamic | Cùng release |
| **SOD-SEC-01** | security.policy.edit | security.policy.publish | Workflow | Policy change cần review độc lập |
| **SOD-OPS-01** | backup.delete | backup.recovery.verify | Contextual | Cần thẩm quyền tách biệt theo chính sách |
| **SOD-PAY-01** | payment.initiate | payment.approve | Dynamic | Cùng payment/transaction |

**Ma trận chỉ là ví dụ thiết kế**, không phải tập SoD rule bắt buộc cho mọi doanh nghiệp. Tổ chức phải xác định phạm vi, mức rủi ro và đối tượng, vì một số quy trình nhỏ có thể dùng kiểm soát bù trừ được phê duyệt.

### Metadata nên có cho mỗi rule

- **ruleId, title, businessOwner, securityOwner**.
- **action/permission identifiers** và technical entitlements tương ứng.
- **type**: assignment/static, activation/dynamic, workflow, cross-system.
- **resourceScopeMatch**: same tenant, same legal entity, same invoice, same project.
- **subjectResolution**: cùng personId hay cùng account, quy tắc delegated/impersonation.
- **severity/risk, prevention requirement, response SLA**.
- **effectiveFrom/effectiveUntil** của rule.
- **approved exceptions** với owner và expiry.
- **policyVersion, test cases và audit expectations**.
- **rationale** về rủi ro nghiệp vụ, không chỉ “hai role tên giống nhau”.

Một conflict matrix không có owner hoặc không được cập nhật khi ứng dụng đổi quyền có thể tạo false positives lẫn false negatives.

## 10. Xung đột nhiều quyền, không chỉ cặp A–B

Một số rủi ro chỉ xuất hiện khi kết hợp **ba hoặc nhiều quyền**.

Ví dụ:

- **customer.bankAccount.edit**.
- **payment.initiate**.
- **payment.approve**.

Một cá nhân nắm hai quyền đầu có thể chưa đủ để hoàn tất gian lận, nhưng nếu có thêm quyền thứ ba thì **chuỗi thao tác** trở nên nguy hiểm. Policy có thể quy định một **forbidden set** gồm ba quyền, hoặc nhiều quy tắc theo bước nghiệp vụ.

### Cách mô hình hóa

~~~text
Rule SOD-PAY-CHAIN-01:
  subjectScope: sameNaturalPersonAcrossAccounts
  forbiddenCombination:
    - customer.bankAccount.edit
    - payment.initiate
    - payment.approve
  resourceConstraint: sameLegalEntityOrLinkedPaymentFlow
  response: DENY_NEW_GRANT_OR_ESCALATE
~~~

Đây là **DSL minh họa**, không phải ngôn ngữ tiêu chuẩn của một sản phẩm.

### Không chỉ kiểm tra cặp quyền mới được gán

Khi một access request xin quyền thứ ba, hệ thống phải tính **tập quyền sau khi gán**:

\[
EffectiveAfter = EffectiveBefore \cup RequestedGrants
\]

Sau đó đánh giá **tất cả rule có liên quan**, không chỉ đối chiếu role mới với một role duy nhất.

### Vai trò gián tiếp và quyền điều khiển

Một permission **user.assignRole** có thể cho phép người dùng tự cấp permission B, dù hiện chưa sở hữu B. Threat modeling nên xem cả **khả năng leo thang được ủy quyền** và quy trình phê duyệt, không chỉ danh sách quyền tĩnh.

## 11. Phát hiện xung đột theo đồ thị quyền

Tổ chức có thể mô hình quyền dưới dạng đồ thị:

- Person → Account.
- Account → Group.
- Group → Role.
- Role → Permission.
- Permission → Action/Resource.
- Person → Delegation/JIT Grant.
- Transaction → CreatedBy/ApprovedBy.
- Permission A ↔ Permission B theo SoD rule.

~~~mermaid
flowchart LR
    PERSON[Person identity] --> ACC1[IdP account]
    PERSON --> ACC2[Local account]
    ACC1 --> G[Group A]
    G --> PA[Permission A]
    ACC2 --> RB[Role B]
    RB --> PB[Permission B]
    RULE[SoD Rule: same scope] --> EVAL[Conflict evaluator]
    PA --> EVAL
    PB --> EVAL
    JML[Relationship and lifecycle] --> EVAL
    SCOPE[Tenant, project, resource] --> EVAL
    EVAL --> DEC[Conflict finding or Permit]
~~~

**Đồ thị rất hữu ích cho effective permission và provenance**, nhưng không thay thế policy runtime khi một rule phụ thuộc vào **trạng thái giao dịch hoặc người đã thực hiện bước trước**.

### Các trường hợp phức tạp

- Group lồng nhau nhiều tầng có thể có chu trình hoặc quy tắc kế thừa đặc thù.
- Một người có nhiều account ở những ứng dụng khác nhau.
- Cùng một permission tên giống nhau nhưng tác dụng khác giữa SaaS.
- Permission có scope điều kiện hoặc deny policy.
- Role có quyền tạo token, mời người dùng hoặc sửa policy để gián tiếp leo thang.

**Tính effective permissions phải phản ánh semantics của hệ thống đích**, không cộng tên group theo kiểu chuỗi thuần túy.

## 12. Quy trình phát hiện xung đột quyền

Một pipeline phát hiện có thể gồm:

1. **Inventory identities và accounts:** personId, relationshipId, workloadId, target account IDs.
2. **Thu thập grants:** role, group, direct permission, cloud policy, delegation, JIT.
3. **Chuẩn hóa permission:** ánh xạ entitlement kỹ thuật tới action nghiệp vụ.
4. **Giải quyết kế thừa:** nested groups, role hierarchy, owner/relationship, scope.
5. **Tính effective permissions:** quyền hiện hành với điều kiện và thời hạn phù hợp.
6. **Áp SoD rules:** so forbidden combinations, scope overlap, subject identity.
7. **Bổ sung workflow history:** kiểm dynamic SoD trên transaction đang xử lý.
8. **Tạo findings:** ruleId, scope, nguồn cấp, severity và evidence.
9. **Phân công owner:** Security, application owner hoặc business owner xử lý.
10. **Remediate:** deny grant mới, gỡ quyền thừa, áp JIT hoặc ngoại lệ đã được phê duyệt.
11. **Readback:** xác minh target không còn effective conflict theo policy.
12. **Giám sát drift:** lập lại khi JML, entitlement, role mapping hoặc policy thay đổi.

### Phát hiện theo sự kiện và theo chu kỳ

| Cơ chế | Thời điểm | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **Pre-grant check** | Trước khi cấp role/quyền mới | Ngăn xung đột ngay từ nguồn | Bỏ sót grant ngoài workflow |
| **Pre-activation** | Trước JIT/PAM activation | Giảm xung đột tạm thời | Phụ thuộc dữ liệu hiện hành |
| **Runtime check** | Khi user thực hiện action | Ngăn dynamic SoD tại giao dịch | Phải bao phủ mọi API/consumer |
| **Scheduled scan** | Hằng ngày/tuần/quý theo rủi ro | Phát hiện drift và tài khoản legacy | Có độ trễ |
| **Event-triggered scan** | Khi Mover/Leaver hoặc role thay đổi | Phản ứng nhanh với lifecycle | Sự kiện có thể thất lạc/đến sai thứ tự |
| **Access review** | Khi campaign/attestation | Có xác nhận business owner | Không thay thế chặn runtime |

**Một giải pháp chỉ chạy batch SoD mỗi quý không đủ bảo vệ hành động thanh toán thực thi ngay hôm nay.** Cần preventive hoặc runtime controls cho những xung đột nhạy cảm.

## 13. Giả mã kiểm tra xung đột trước cấp quyền

Ví dụ thuật toán minh họa:

~~~text
function evaluateProposedGrant(subjectId, proposedGrant):
    subject = loadTrustedSubject(subjectId)
    relationship = loadCurrentAuthoritativeRelationship(subject)

    if not relationship.isActiveFor(proposedGrant.effectiveWindow):
        return DENY_LIFECYCLE

    existing = resolveEffectiveGrantsAcrossInScopeSystems(subject)
    prospective = union(existing, [proposedGrant])

    for rule in activeSoDRules():
        applicableGrants = filterByActionsAndConditions(
            prospective, rule.requiredActions, rule.conditions
        )

        if not allRequiredActionsPresent(applicableGrants):
            continue

        if not scopesOverlapAsDefined(rule, applicableGrants):
            continue

        if not temporalConditionsConflict(rule, applicableGrants):
            continue

        if rule.type == STATIC:
            return DENY_OR_ESCALATE(rule.id, evidence(applicableGrants))

        if rule.type == DYNAMIC:
            return ALLOW_ASSIGNMENT_WITH_RUNTIME_GUARD(rule.id)

    return PERMIT_IF_OTHER_AUTHORIZATION_POLICIES_ALLOW
~~~

Đây là **giả mã khái niệm**, không tự định nghĩa semantics chuẩn của một engine. Với nhiều rule, không được **return Permit sớm** khi rule đầu tiên không khớp; phải đánh giá đầy đủ các rule liên quan và các điều kiện từ chối bắt buộc.

### Tại sao phải phân biệt DYNAMIC?

Một dynamic rule có thể **không cấm việc cùng gán hai role**, nhưng bắt buộc backend kiểm tra người tạo/người phê duyệt khi action diễn ra. Nếu ứng dụng không có runtime guard đáng tin, hệ thống có thể phải dùng static denial hoặc một thiết kế khác để tránh bypass.

### Nguyên tắc xử lý thiếu dữ liệu

Nếu không thể tải effective grants hoặc xác minh tenant/scope đối với quyền đặc biệt, **không tự cấp quyền rộng theo mặc định**. Cần ghi outcome **INDETERMINATE/NEED_REVIEW** theo quy trình và, nếu khẩn cấp, dùng đường break-glass được thiết kế trước.

## 14. Ví dụ Java: phát hiện static conflict theo scope

Đoạn Java sau minh họa cách xem xét **hai action có bị cấm đồng thời và có giao nhau về scope không**. Đây là ví dụ học thuật đơn giản, không phải implementation production.

~~~java
import java.util.List;
import java.util.Set;

record Grant(
        String subjectId,
        String action,
        String tenantId,
        String legalEntityId,
        boolean active
) {}

record ConflictRule(
        String ruleId,
        Set<String> forbiddenActions,
        boolean sameTenantRequired,
        boolean sameLegalEntityRequired
) {}

public final class SodChecker {
    public static boolean conflicts(
            List<Grant> grants, ConflictRule rule
    ) {
        for (int i = 0; i < grants.size(); i++) {
            Grant left = grants.get(i);
            if (!left.active()) continue;

            for (int j = i + 1; j < grants.size(); j++) {
                Grant right = grants.get(j);
                if (!right.active()) continue;

                if (!left.subjectId().equals(right.subjectId())) {
                    continue;
                }

                // Ví dụ chỉ xử lý forbidden pair đúng hai action.
                if (rule.forbiddenActions().size() != 2) {
                    throw new IllegalArgumentException("Pair rule required");
                }
                if (!rule.forbiddenActions()
                        .equals(Set.of(left.action(), right.action()))) {
                    continue;
                }

                if (rule.sameTenantRequired()
                        && !left.tenantId().equals(right.tenantId())) {
                    continue;
                }

                if (rule.sameLegalEntityRequired()
                        && !left.legalEntityId()
                                .equals(right.legalEntityId())) {
                    continue;
                }

                return true;
            }
        }
        return false;
    }
}
~~~

### Giới hạn cần ghi nhớ

- Ví dụ chỉ so **hai action**, không hỗ trợ forbidden set có ba quyền, role hierarchy hay policy deny.
- Không có **time window/expiry** nên trường active phải được tính từ nguồn tin cậy trước khi gọi.
- Kiểm tra **tenantId/legalEntityId bằng equality** là đơn giản hóa; thực tế có thể dùng scope cây, wildcard hoặc cross-tenant grants.
- **subjectId phải ánh xạ person/workload đúng**. Hai local accounts cùng một người không thể bị coi là hai người chỉ vì tên tài khoản khác.
- Set.of không thể biểu diễn cặp gồm hai action trùng nhau; nếu policy cần “cùng action trên hai nguồn” thì phải thiết kế model khác.
- Không xử lý **null**, metadata sai lệch, lỗi PIP, race condition hoặc đánh giá đủ các conflict rule.
- **Runtime dynamic SoD** như không tự duyệt hóa đơn vẫn phải được kiểm ngay tại business service.

Cách tiếp cận phù hợp production là dùng **policy model có scope semantics rõ, nguồn dữ liệu đáng tin, test đầy đủ và enforcement tại tất cả đường thực thi**.

## 15. Runtime dynamic SoD: không tự phê duyệt hóa đơn

Xét một API:

~~~http
POST /api/invoices/INV-873/approve HTTP/1.1
Host: finance.example.org
Authorization: Bearer <REDACTED_ACCESS_TOKEN>
Content-Type: application/json
~~~

Một policy logic:

~~~text
permit(invoice.approve) only if
    subject.lifecycleState == ACTIVE
    and subject.hasPermission("invoice.approve")
    and subject.tenantId == invoice.tenantId
    and invoice.state == SUBMITTED
    and subject.id != invoice.createdBy
    and invoice.amount <= subject.approvalLimit
    and currentSession.meetsAuthenticationPolicy
~~~

Phải lưu ý:

1. **invoice.createdBy** lấy từ database đáng tin, không tin request JSON.
2. **subject.id/permission** lấy từ phiên/token đã xác minh và entitlement hiện hành.
3. **state SUBMITTED** phải còn đúng lúc commit, không chỉ lúc read.
4. **Không kiểm mỗi HTTP POST**; action thực tế phải là **invoice.approve** trên invoice này.
5. Nếu dùng delegation, cần biết người **đang thao tác thực** và người được đại diện.
6. Kiểm soát **concurrency/TOCTOU** bằng transaction/locking phù hợp.
7. Nếu API cho sửa trực tiếp trường **status=APPROVED**, phải chặn đường bypass đó.
8. Audit phải ghi actor, resource, outcome và policy decision.

**Một approver có quyền invoice.approve theo RBAC vẫn không được tự duyệt invoice của mình** khi dynamic SoD cấm.

## 16. Preventive, detective, corrective và compensating controls

Xung đột quyền cần nhiều lớp kiểm soát:

| Loại | Mục tiêu | Ví dụ |
|---|---|---|
| **Preventive** | Chặn trước khi cấp hoặc thực thi quyền xung đột | SoD policy từ chối grant thứ hai |
| **Detective** | Phát hiện quyền sai đã tồn tại | Scheduled conflict scan, audit alert |
| **Corrective** | Gỡ hoặc sửa quyền xung đột | Revoke role, giảm scope, invalidate token |
| **Compensating** | Giảm rủi ro khi không thể tách hoàn toàn theo cách chuẩn | Giám sát độc lập, dual approval, JIT và audit |
| **Governance** | Giữ rule catalog chính xác, có owner | SoD matrix review và role mining |
| **Verification** | Chứng minh quyền trái policy đã bị chặn | Target readback và negative action test |

### Tại sao không chỉ dùng detective?

Một phát hiện cuối ngày không ngăn được thanh toán giả xảy ra lúc 10:00. Ngược lại, chỉ preventive ở IAM có thể bỏ sót **direct grant ngoài IAM hoặc token còn claim cũ**. Cần kết hợp theo rủi ro và kiến trúc.

### Biện pháp bù trừ không phải nút bỏ qua

Khi không thể tách nhiệm vụ do quy mô đội nhỏ, tổ chức có thể dùng **review độc lập sau giao dịch, hạn mức, JIT, phê duyệt hai người hoặc nhật ký không thể sửa tùy tiện**. Nhưng phải có **risk owner, căn cứ, phạm vi, thời hạn và kiểm chứng hiệu quả**. Nếu policy quy định hard deny, không được tự thêm exception để né bắt buộc.

## 17. Exception management cho xung đột quyền

Một ngoại lệ SoD nên có dữ liệu cấu trúc thay vì chỉ ghi “được phép vì gấp”:

~~~json
{
  "exceptionId": "sod-ex-20261123-019",
  "ruleId": "SOD-FIN-01",
  "subjectId": "person-2046",
  "relationshipId": "employment-2046-v1",
  "conflictingActions": [
    "vendor.create",
    "vendor.payment.approve"
  ],
  "scope": {
    "legalEntityId": "company-vn-01",
    "maxAmountMinor": 5000000
  },
  "reason": "Chi nhánh nhỏ trong kỳ chuyển đổi quy trình",
  "riskOwnerId": "risk-owner-821",
  "securityReviewId": "sec-review-20261123-071",
  "compensatingControls": [
    "INDEPENDENT_POST_TRANSACTION_REVIEW",
    "JIT_APPROVAL_WINDOW",
    "ENHANCED_AUDIT_ALERT"
  ],
  "validFrom": "2026-11-23T09:00:00+07:00",
  "validUntil": "2026-12-07T09:00:00+07:00",
  "status": "PENDING_RISK_ACCEPTANCE"
}
~~~

Đây là **mô hình minh họa**, không phải chuẩn SCIM, OIDC hay XACML.

### Trình tự xử lý ngoại lệ

1. Xác minh rule và **vì sao không thể khắc phục ngay bằng thiết kế quyền hẹp**.
2. Phân tích tác động/tần suất và khả năng lạm dụng.
3. Xác định **risk owner có thẩm quyền** cùng Security/business owner phù hợp.
4. Đề xuất compensating controls có **điểm thực thi và cách kiểm tra**.
5. Giới hạn **resource scope, amount, thời gian và beneficiary**.
6. Phê duyệt theo chính sách; **PENDING_RISK_ACCEPTANCE chưa cho phép**.
7. Kích hoạt enforcement đúng phạm vi khi ngoại lệ được duyệt.
8. Theo dõi usage, alert và review trước khi hết hạn.
9. Thu hồi/retire ngoại lệ khi hết hạn hoặc sau Mover/Leaver.
10. Readback các quyền/phiên còn tồn dư.

**Không cho phép ngoại lệ SoD kéo dài vô hạn chỉ vì không có người xử lý**. Ngoại lệ cũng không bảo vệ một action thực tế nếu PEP/target không kiểm điều kiện áp dụng.

## 18. Xung đột quyền trong Access request và Approval workflow

Khi người dùng xin một entitlement mới, hệ thống cần kiểm **effective permissions sau khi cấp** chứ không chỉ role mới.

### Luồng minh họa

~~~mermaid
sequenceDiagram
    participant U as Requester
    participant IGA as Access Request / IGA
    participant SOD as SoD Policy Engine
    participant OWNER as Owner / Security
    participant TARGET as App / SCIM / PAM
    U->>IGA: Xin permission mới + scope + reason
    IGA->>IGA: Xác minh beneficiary / JML / eligibility
    IGA->>SOD: Existing + proposed effective grants
    SOD-->>IGA: No conflict / Conflict finding
    alt Có conflict
        IGA->>OWNER: Review / từ chối / giải pháp giảm scope
        OWNER-->>IGA: Decision và điều kiện có thẩm quyền
    end
    IGA->>SOD: Revalidate trước fulfillment
    SOD-->>IGA: Quyết định theo trạng thái mới nhất
    IGA->>TARGET: Provision nếu được phép
    TARGET-->>IGA: Kết quả API / target observed state
    IGA->>IGA: Readback + audit + reconciliation
~~~

### Trạng thái cần phân biệt

- **REQUESTED:** đã xin quyền, chưa được duyệt.
- **SOD_CHECKED:** đã tính xung đột trên một snapshot nhất định.
- **APPROVED/CONDITIONAL:** có quyết định theo điều kiện, chưa chứng minh quyền tại đích.
- **PROVISIONING:** connector đang thực thi.
- **VERIFIED:** quyền đã đúng phạm vi và không tạo xung đột bị cấm trong coverage.
- **PARTIAL/FAILED:** còn chênh lệch hoặc không thể chứng minh.

### Tránh approval stale

Nếu request được duyệt lúc 09:00 nhưng đến 09:05 subject được cấp thêm một role khác, kết quả SoD từ 09:00 có thể không còn đúng. Cần **re-evaluate trước fulfillment và dùng version/fencing** để ngăn cấp quyền trái chính sách.

**Approval từ manager không thay thế SoD check.** Manager xác nhận nhu cầu, còn rule SoD có thể yêu cầu Security/risk owner độc lập và hard denial.

## 19. Xung đột quyền trong Access review/Certification

**Access review** giúp phát hiện tổ hợp quyền đã tồn tại và xác nhận liệu mỗi quyền còn cần thiết hay không.

Reviewer nên thấy:

- **Cặp/tập permission đang xung đột** cùng SoD rule ID.
- Mỗi quyền đến từ **role/group/direct grant** nào.
- **Scope và effective dates** có giao nhau không.
- Quan hệ công việc và quyền đã thay đổi từ lần review trước.
- Action nào đã thực hiện, có liên quan cùng giao dịch không.
- Tồn tại **exception hợp lệ** hay chỉ là ghi chú chưa phê duyệt.
- Hệ thống nào chưa có readback hoặc logging đầy đủ.

### Các quyết định review

| Review decision | Khi thích hợp | Việc phải làm tiếp |
|---|---|---|
| **REVOKE** | Quyền không còn căn cứ | Gỡ grant và xác minh target |
| **MODIFY** | Giữ chức năng nhưng giảm scope | Thay role/grant, kiểm quyền dư |
| **RETAIN** | Có căn cứ và không vi phạm policy hiện hành | Lưu evidence, review kỳ tiếp |
| **NEED_MORE_INFO** | Chưa hiểu permission hoặc owner | Điều tra, không auto-certify |
| **ESCALATE** | SoD conflict hoặc privileged grant | Route tới Security/risk owner |
| **EXCEPTION_REQUESTED** | Không thể tách ngay | Workflow risk acceptance có hạn |

**Một quyết định RETAIN của kỳ review cũ không được mở lại quyền đã bị Leaver/Mover thu hồi.** Reviewer phải xem snapshot và **version JML hiện hành**.

## 20. SoD và RBAC: ngăn Role explosion nhưng không gom role nguy hiểm

RBAC có thể giúp quản lý vai trò, nhưng **role explosion** thường khiến quyền xung đột phân tán qua nhiều biến thể:

~~~text
finance_checker_north_prod
finance_checker_north_legacy
finance_checker_south_prod
payment_authorizer_special
vendor_creator_project_a
~~~

Không nên giải quyết bằng một role **FINANCE_ALL** chứa mọi permission; điều đó có thể làm tăng rủi ro SoD.

### Thiết kế đề xuất

- Xác định **business roles** theo chức năng, ví dụ PAYMENTS_CREATOR và PAYMENTS_APPROVER.
- Giữ **action và SoD rule** rõ ràng; scope tenant/region xử lý bằng policy khi hệ thống hỗ trợ.
- Tách **technical entitlement** của SaaS khỏi business role.
- Áp **ABAC/ReBAC** cho resource scope, ownership và project membership.
- Đánh giá SoD theo **permission-level after inheritance**, không chỉ tên role.
- Với nhu cầu hiếm và đặc quyền, cân nhắc **JIT/temporary access**, không tạo role cá nhân vĩnh viễn.
- Kiểm tra **role hierarchy** để tránh một role cấp cao kế thừa cả hai chức năng xung đột.

**Giảm số role không phải mục tiêu duy nhất**: mô hình role phải dễ chứng nhận và không hợp nhất những trách nhiệm được yêu cầu độc lập.

## 21. PBAC/ABAC và kiểm tra scope xung đột

Một **Policy-Based Access Control (PBAC)** engine có thể kết hợp **RBAC, ABAC, ReBAC và SoD** để ra quyết định.

Ví dụ rule khái niệm:

~~~text
deny if
    subject.lifecycleState != ACTIVE

deny if
    action == "invoice.approve"
    and resource.createdBy == subject.identityId

deny if
    action == "vendor.payment.approve"
    and subject.hasActivePermission(
        "vendor.create",
        legalEntityId = resource.legalEntityId
    )
    and policy.forbidsSameSubjectHoldingBoth

permit if
    otherAuthorizationConditionsPass
    and noMandatoryDenyApplies
~~~

Đây là **giả mã**, không phải cú pháp của Rego, Cedar hoặc XACML. Quy tắc allow/deny phải có **combining semantics** rõ, đặc biệt khi có nhiều policy.

### Attribute trust là điều kiện bắt buộc

- **createdBy** từ database bất biến/được kiểm soát.
- **identityId/relationshipId** từ IAM/IdP đã xác minh.
- **role/permission** từ entitlement hiện hành và target-aware mapping.
- **resource scope** từ resource registry/database.
- **time/expiry** theo clock server đáng tin.
- **MFA assurance** từ IdP/phiên đã kiểm tra.

**Policy không thể đúng nếu các thuộc tính quan trọng bị client giả mạo hoặc đã lỗi thời sau Mover/Leaver.**

## 22. Xung đột quyền trong JIT/PAM/PIM và quyền đặc biệt

JIT giảm **thời gian có đặc quyền**, nhưng không tự làm mất xung đột.

Một kỹ sư có thể **eligible** cho cả quyền **change.author** và **production.deploy**. Nếu policy cấm **kích hoạt đồng thời** hoặc tự approve release của mình, broker/PDP phải kiểm tra khi activation và runtime.

| Tình huống | Câu hỏi SoD | Biện pháp |
|---|---|---|
| Eligible hai role xung đột | Chỉ eligibility đã bị cấm hay chỉ khi Active? | Theo static/dynamic SoD policy |
| Activate Role B khi A active | Có scope và thời hạn chồng nhau? | Deny activation hoặc revoke A trước |
| PAM privileged session | Ai thực sự thao tác? | Session brokering, per-command audit |
| CI/CD production deploy | Người tạo change có tự approve release? | Approval độc lập và provenance |
| Break-glass | Có đường emergency được phê duyệt? | Scope, thời hạn, alert, post-review |
| Token còn role cũ | Xung đột thực tế vẫn tồn tại sau revoke? | Token/session invalidation hoặc runtime checks |

### Eligible khác Active

- **Eligible**: có thể yêu cầu kích hoạt role.
- **Active**: quyền đang có hiệu lực theo thời gian và điều kiện.
- **Expired/Revoked**: grant không còn căn cứ cho action.

Một policy **static SoD** có thể cấm cả eligibility nếu khả năng tự kích hoạt không có kiểm soát. Một policy **dynamic SoD** có thể cho phép eligible hai role nhưng cấm kích hoạt đồng thời hoặc cấm thực hiện hai bước trên cùng đối tượng.

### JIT không thay thế độc lập con người

Một người có quyền author 10 phút rồi approve trong 10 phút sau vẫn có thể vi phạm **dynamic SoD trên cùng release**, dù không từng giữ hai role đồng thời. **Lịch sử action** phải được lưu và kiểm.

## 23. Xung đột quyền trong Joiner lifecycle

**Joiner** thường cấp baseline roles, rồi cấp thêm entitlement theo nhiệm vụ. SoD nên được áp **trước** khi hoàn tất việc cấp quyền.

### Luồng an toàn

1. HRIS/contract authority xác định **personId, relationshipId, job function, effectiveAt**.
2. Identity proofing và enrollment liên kết đúng account/credential.
3. IAM/IGA tính **birthright access** và business role theo chức năng.
4. Kiểm **effective permissions sau khi gán** và SoD rules liên quan.
5. Chỉ cấp các entitlement bổ sung sau approval/SoD check cần thiết.
6. IdP/SSO xác thực người dùng; SCIM/API provisioning tài khoản/nhóm.
7. Ứng dụng thực thi runtime dynamic SoD tại action.
8. Reconciliation xác nhận quyền đúng, không có toxic combination ngoài policy.

### Không copy toàn bộ quyền đồng nghiệp

Người tiền nhiệm có thể có **direct grants, ngoại lệ hoặc JIT eligibility** từ dự án trước. Nếu copy mọi role, người mới có thể nhận quyền xung đột ngay ngày đầu dù bản mô tả công việc không yêu cầu.

### Trước effectiveAt

Tài khoản được chuẩn bị sớm không có nghĩa quyền nhạy cảm phải có thể dùng ngay. SoD và lifecycle policy cần xét **thời điểm hiệu lực**, không chỉ việc account đã được tạo.

## 24. Xung đột quyền trong Mover lifecycle

**Mover** là nguồn phổ biến của **privilege accumulation**, vì nhiều hệ thống chỉ thêm role mới mà quên gỡ role cũ.

Ví dụ Lan chuyển từ **Procurement** sang **Finance Payments**:

| Quyền | Trước Mover | Sau Mover mong muốn | Xung đột nếu không gỡ |
|---|---|---|---|
| vendor.create | Có ở Procurement | Thu hồi | Kết hợp payment.approve |
| vendor.editBankAccount | Có theo nhiệm vụ | Thu hồi | Kết hợp initiate/approve |
| payment.read | Không | Cấp | Thường cần scope Finance |
| payment.approve | Không | Chỉ sau approval | Cần SoD check với quyền cũ |
| procurement.admin | Có qua legacy group | Thu hồi | Vẫn có thể tự tạo vendor |

### Quy trình Mover kiểm xung đột

1. Nhận **Mover event** từ nguồn có thẩm quyền và sourceVersion.
2. Tính **desired permissions** theo job/relationship mới.
3. Tính **observed effective permissions** ở target, gồm group lồng nhau/direct grant.
4. Xác định quyền cũ phải gỡ và **xung đột với quyền mới**.
5. Quyết định thứ tự **revoke-before-grant** khi cần tránh thời gian hai quyền cùng tồn tại.
6. Cấp quyền mới sau approval và policy checks.
7. Kiểm token/session/PAM grants còn quyền cũ.
8. Đối soát action cũ bị chặn và action mới chỉ được phép đúng phạm vi.
9. Mở finding khi connector không thể thu hồi đầy đủ.

### Race condition

Job cấp FINANCE_APPROVER và job thu hồi PROCUREMENT_CREATOR có thể chạy bất đồng bộ. Nếu grant mới được bật trước khi revoke cũ, người dùng có một **cửa sổ toxic combination**. Với xung đột nghiêm trọng, cần sequencing, version/fencing, blocking policy tại PEP hoặc kiểm soát bù trừ tạm phù hợp.

**Mover không hoàn tất chỉ vì role mới đã xuất hiện.** Cần chứng minh những quyền cũ gây xung đột đã thực sự mất hiệu lực.

## 25. Xung đột quyền trong Leaver lifecycle

Khi một quan hệ làm việc kết thúc, mục tiêu là **ngăn toàn bộ action không còn căn cứ**, thay vì chỉ giải quyết một cặp SoD cụ thể.

### Những lớp cần thu hồi

| Lớp | Rủi ro tồn dư | Biện pháp |
|---|---|---|
| **HRIS/IGA** | Identity relationship đã kết thúc nhưng desired state chưa đổi | Xử lý Leaver event đúng version/effectiveAt |
| **IdP/SSO** | Chỉ chặn đăng nhập mới, SP session còn | Disable và xử lý sessions |
| **SCIM/App** | User/Group/direct grants còn ở đích | Deactivate/gỡ entitlement và readback |
| **PAM/PIM** | Privileged grant/session còn Active | Revoke và đóng session |
| **OAuth/JWT** | Access token cũ có role/scope | Cơ chế revocation/introspection, checks theo policy |
| **Local account** | Tài khoản không qua IdP | Disable trực tiếp và inventory |
| **API key/SSH key** | Credential độc lập | Thu hồi/rotate theo phạm vi |
| **Policy cache** | Quyền cũ vẫn Permit | Invalidate hoặc giới hạn TTL phù hợp |
| **Audit/reconciliation** | Không biết action còn dùng được không | Negative test/readback và finding |

**Không cần chờ campaign SoD hoặc access review kết thúc để xử lý Leaver** nếu chính sách yêu cầu cắt quyền từ thời điểm quan hệ kết thúc.

### Một người có nhiều quan hệ

Nếu một cá nhân có hai relationship còn hoặc hết hạn khác nhau, cần xác định **quyền nào thuộc relationship đã chấm dứt**. SoD cũng nên xét **cùng natural person** khi chính sách đòi hỏi, tránh tách thành hai account để vượt conflict rule. Tuy nhiên không được xóa nhầm quyền hợp lệ của quan hệ khác mà không đánh giá.

### Rejoiner

Người quay lại làm việc không được tự động nhận role/xung đột quyền cũ vì dùng cùng email. Phải xác minh quan hệ mới, tính lại baseline/SoD và kiểm tra tài khoản đích không tái cấp direct grants lịch sử.

## 26. Identity proofing, IdP và SSO ảnh hưởng đến SoD thế nào?

SoD muốn áp lên **cùng một cá nhân** cần giải quyết đúng việc **person–account linking**.

### Những đường có thể bị lạm dụng

- Một cá nhân có account **employee** và account **contractor**.
- Email được **đổi hoặc tái sử dụng**, tạo mapping nhầm.
- Một admin có **privileged account** tách khỏi user account.
- Người dùng có local account trong SaaS không liên kết IdP.
- Account được **ủy quyền/impersonate** để thực hiện action.
- Shared account che giấu actor thật.

### Quy tắc

1. Dùng **immutable person/identity ID** từ nguồn có thẩm quyền.
2. Liên kết đúng **target account IDs**, không chỉ username/email.
3. Lưu **relationship ID** để biết căn cứ của từng entitlement.
4. Với privileged account riêng, giữ **mối liên kết tới human owner** và session actor.
5. Không dùng **shared account** cho các bước SoD cần truy trách nhiệm người thực hiện.
6. IdP/SSO chỉ xác thực chủ thể; SoD policy vẫn cần dữ liệu quyền và lịch sử nghiệp vụ.
7. Account lifecycle và credential revocation phải theo đúng quan hệ/thời điểm.

**MFA mạnh không xóa xung đột quyền**: một người xác thực đúng vẫn không được tự chấp thuận giao dịch do mình tạo nếu policy cấm.

## 27. SCIM và entitlement mapping khi gỡ quyền xung đột

SCIM 2.0 thường được dùng để đồng bộ **User và Group**. Một xung đột có thể được khắc phục bằng cách gỡ một **Group.members** membership tại target.

Ví dụ kết quả review yêu cầu gỡ Lan khỏi nhóm VENDOR_CREATOR ở SaaS:

~~~http
PATCH /scim/v2/Groups/group-vendor-creator HTTP/1.1
Host: procurement.example.org
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
      "path": "members[value eq \"user-2046\"]"
    }
  ]
}
~~~

Cú pháp minh họa theo SCIM PatchOp; cần xác nhận **service provider hỗ trợ PATCH/valuePath filter** và đường dẫn Group thực tế. **SCIM User.groups trong core schema thường là read-only** nên không coi việc sửa trường đó là cách chung để gỡ quyền.

### Sau PATCH cần xác minh gì?

- Đúng **User ID/Group ID/tenant**.
- Membership không còn ở target.
- Quyền **vendor.create** không còn đến từ role/direct grant khác.
- Cached authorization hoặc phiên/token cũ không tiếp tục Permit.
- SoD evaluator tính lại effective permissions theo trạng thái mới.
- Nếu còn quyền, tạo **PARTIAL/OPEN finding** thay vì đóng conflict vì HTTP response thành công.

**SCIM đồng bộ nhóm không phải policy engine SoD**. Nó là một đường triển khai/thu hồi entitlement, còn quyết định xung đột phải theo policy và dữ liệu nghiệp vụ.

## 28. OAuth/OIDC, token và session ảnh hưởng đến conflict ra sao?

Một **access token** có scope hoặc claim role được phát khi user còn quyền. Sau Mover hoặc SoD remediation, JWT vẫn có thể hợp lệ về chữ ký và exp.

Ví dụ:

- 09:00 user có role VENDOR_CREATOR; được cấp access token.
- 09:05 IAM gỡ role vì phát hiện xung đột với PAYMENT_APPROVER.
- 09:06 API vẫn tin role claim từ token phát lúc 09:00.
- 09:07 user tiếp tục thực hiện **vendor.create**, tạo conflict về khả năng thực thi dù assignment ở IGA đã sạch.

### Kiểm soát cần cân nhắc

- Token TTL phù hợp rủi ro của action.
- Token **audience/scope** đúng API; scope không thay thế SoD và object-level policy.
- Kiểm trạng thái quyền **hiện hành** hoặc introspection cho action nhạy cảm.
- Cơ chế revoke/denylist, invalidation cache và session termination theo năng lực hệ thống.
- Không dùng **OIDC ID token** như credential cho resource server.
- Theo dõi local session, PAT, API key và background jobs độc lập với SSO.

**Quyền không còn được gán không tự chứng minh token hiện tại đã ngừng sử dụng được.** Với xung đột rủi ro cao, kiểm soát phải hướng tới việc **action thực tế bị chặn**.

## 29. Non-human identities và xung đột quyền

SoD cũng cần xét **service account, bot, CI/CD pipeline, workload identity, device identity và cloud service principal**.

Ví dụ pipeline triển khai vừa có quyền:

- **deployment.artifact.create**.
- **deployment.policy.override**.
- **deployment.production.release**.

Nếu cùng một pipeline có thể tự tạo artifact, sửa policy kiểm tra và release production mà không có phê duyệt độc lập, tổ chức có thể mất kiểm soát chuỗi cung ứng phần mềm.

### Những câu hỏi cần hỏi

| Thành phần | Kiểm tra |
|---|---|
| **Workload identity** | Registry, client ID, owner và phạm vi |
| **Action permissions** | Có quyền thay đổi cả bản build và cơ chế phê duyệt? |
| **Credentials** | Managed identity/federation hoặc secret dùng chung? |
| **Pipeline provenance** | Ai khởi tạo, ai approve, artifact có integrity? |
| **Approval independence** | Reviewer thực sự độc lập với actor tạo thay đổi? |
| **Resource scope** | CI/CD chỉ cho một service/environment hay toàn cloud? |
| **Time limit** | Role thường trực hay token/grant ngắn hạn? |
| **Owner lifecycle** | Khi owner Leaver, workload có owner mới và review? |

### Không áp SoD người dùng máy móc cho workload

Một batch job hợp lệ có thể cần **đọc và ghi** cùng dataset trong quy trình kỹ thuật; hai permission đó không tự cấu thành xung đột. SoD rule phải xuất phát từ **rủi ro nghiệp vụ và trust boundary**, không từ nguyên tắc “tách mọi action” chung chung.

### Khi owner Leaver

Không tự xóa một workload production còn được phê duyệt chỉ vì owner cá nhân nghỉ. Cần **chuyển owner, kiểm secret từng biết, rotate khi cần và review effective permissions**, đồng thời xử lý các human grants thuộc quan hệ cũ.

## 30. Nhà thầu, đối tác, ủy quyền và xung đột quyền

Nhà thầu có thể có **guest account, local account và federated identity**. Một người được ủy quyền có thể thay mặt manager thực hiện action.

### Rủi ro

- Nhà thầu vừa **đề xuất thay đổi** vừa **tự nghiệm thu** công việc của mình.
- Một đối tác có quyền **sửa dữ liệu** và **duyệt dữ liệu** trong cùng dự án.
- Sponsor đã Leaver nhưng vẫn tồn tại guest entitlement đặc quyền.
- Người dùng **delegated approver** xác nhận chính yêu cầu do mình tạo.
- Một cá nhân có cả **employee account và partner account**, khiến SoD scan theo từng account bỏ sót xung đột.

### Kiểm soát

1. Xác minh **contract/sponsor relationship và expiry** từ nguồn có thẩm quyền.
2. Liên kết account với **natural person hoặc workload owner** theo nhu cầu SoD.
3. Ràng buộc delegation theo **scope, action, resource và thời gian**.
4. Phân biệt **actingAs, onBehalfOf và actual human actor** trong audit.
5. Đánh giá SoD trên **người thực thi**, không chỉ identity đại diện nếu policy yêu cầu.
6. Gỡ quyền khi hợp đồng/ủy quyền kết thúc và xác minh target.

**Delegation hợp lệ không phải quyền được phép bỏ qua SoD**: người được ủy quyền vẫn phải đáp ứng các ràng buộc độc lập.

## 31. Audit trail và bằng chứng xung đột quyền

Một bản ghi SoD finding cần trả lời:

> Xung đột nào được phát hiện, trên subject/resource/scope nào, mỗi quyền đến từ đâu, theo rule/policy phiên bản nào, đã xử lý thế nào và hiện quyền thực tế ra sao?

### JSON event minh họa

~~~json
{
  "findingId": "sod-20261123-031",
  "ruleId": "SOD-FIN-01",
  "policyVersion": "sod-finance-v7",
  "subjectId": "person-2046",
  "relationshipId": "employment-2046-v1",
  "conflictingPermissions": [
    {
      "action": "vendor.create",
      "grantSource": "group:procurement-vendor-creator",
      "targetSystem": "procurement-saas"
    },
    {
      "action": "vendor.payment.approve",
      "grantSource": "role:finance-payment-approver",
      "targetSystem": "payments-api"
    }
  ],
  "scope": {"legalEntityId": "company-vn-01"},
  "severity": "HIGH",
  "detectedAt": "2026-11-23T09:16:00+07:00",
  "sourceVersion": "relationship-2046-v4",
  "state": "OPEN",
  "remediationOwnerId": "security-team-finance",
  "correlationId": "corr-sod-8af2"
}
~~~

Đây là **schema nội bộ minh họa**, không phải SCIM event hoặc XACML response chuẩn.

### Kết nối các event

- **GrantRequested/Approved:** yêu cầu mới và actor phê duyệt.
- **SoDCheckExecuted:** rule, dữ liệu/as-of, outcome.
- **ConflictDetected:** tập permission và source.
- **ExceptionRequested/Approved/Denied:** căn cứ và thời hạn.
- **RemediationDispatched/Acknowledged:** connector, operation ID.
- **EntitlementObserved:** readback tại hệ thống đích.
- **ActionDenied/ActionExecuted:** enforcement thực tế của runtime policy.
- **ConflictClosed:** bằng chứng effective access đã an toàn theo coverage.

### Dữ liệu cần bảo vệ

Không log **password, access token, refresh token, private key, mã MFA hoặc toàn bộ dữ liệu giao dịch nhạy cảm**. Chỉ lưu metadata, quyền truy cập, retention và bảo vệ chống sửa log trái phép.

## 32. Metrics và cảnh báo cho SoD conflict management

| Chỉ số | Ý nghĩa | Cảnh báo diễn giải |
|---|---|---|
| **Open conflict findings** | Số xung đột đang mở theo severity | Ít finding không tự chứng minh scan đầy đủ |
| **New conflicts after grants** | Xung đột tạo bởi cấp quyền mới | Đánh giá pre-grant coverage |
| **Mover conflicts** | Tổ hợp quyền cũ/mới sau Mover | Chỉ số privilege accumulation |
| **Leaver residual conflicts/access** | Quyền tồn dư sau Leaver | Cần ưu tiên xác minh khả năng truy cập |
| **Prevented activation attempts** | JIT/PAM bị chặn do SoD | Có thể cho thấy policy hoạt động hoặc nhu cầu sai |
| **Dynamic SoD denied actions** | Tự duyệt hay xung đột giao dịch bị chặn | Cần xem false positive và dấu hiệu lạm dụng |
| **False positive rate** | Findings không thực sự vi phạm do scope/định nghĩa | Cải thiện rule catalog |
| **Rule coverage** | Bao nhiêu action nhạy cảm có policy SoD | Cần kết hợp endpoint coverage |
| **Unmapped entitlements** | Quyền đích chưa ánh xạ tới action | Rủi ro false negative |
| **Remediation latency** | Từ phát hiện tới chặn quyền trái policy | Đánh giá hiệu quả xử lý |
| **Verified closure rate** | Finding đóng có readback/runtime evidence | Không đồng nghĩa chỉ gỡ tên role |
| **Expired exception rate** | Ngoại lệ hết hạn nhưng chưa xử lý | Kiểm soát rủi ro tích lũy |
| **Role hierarchy drift** | Quyền kế thừa thay đổi ngoài kiểm soát | Cần đánh giá lại effective permissions |
| **Cross-system mapping coverage** | Tỷ lệ SaaS/cloud/local account được inventory | Giới hạn kết luận tổng thể |

### Metric không nên bị tối ưu sai

Một đội có thể giảm số finding bằng cách **tắt rule** hoặc tăng ngoại lệ, nhưng không giảm rủi ro thật. Nên đánh giá cùng **coverage, policy validity, time-to-revoke và kiểm thử negative authorization**.

## 33. Kiểm thử xung đột quyền: positive, negative và race

| Test case | Tình huống | Kết quả mong đợi |
|---|---|---|
| **Không xung đột** | Người dùng chỉ có vendor.create | Không finding cho cặp rule |
| **Cùng scope, hai quyền** | vendor.create + vendor.payment.approve | Conflict theo SSD |
| **Khác scope không giao nhau** | vendor.create tenant A, approve tenant B | Không conflict nếu policy/tenant isolation xác nhận |
| **Role hierarchy** | Superuser kế thừa cả hai quyền | Phải phát hiện |
| **Nested group** | Role A qua group lồng nhau | Phải phát hiện |
| **Direct + role grant** | Quyền A trực tiếp, B qua role | Phải phát hiện |
| **Hai account một người** | Employee và privileged account | Phải liên kết theo person policy |
| **User khác tạo invoice** | Approver duyệt invoice hợp lệ | Permit nếu điều kiện khác đạt |
| **Self-approval** | createdBy trùng người approve | Deny |
| **Delegated approval** | Acting human đã tạo invoice | Deny nếu SoD yêu cầu trên human actor |
| **JIT role activation** | Role A đang active, xin B xung đột | Deny/controlled transition |
| **Historical dynamic SoD** | Người tạo ở role A, chuyển role B rồi tự approve | Deny trên cùng resource |
| **Mover chưa gỡ quyền cũ** | Cấp Finance khi Procurement còn quyền | Chặn xung đột/thu hồi cũ trước |
| **Leaver** | Subject hết quan hệ nhưng token còn role | API không được Permit action trái policy |
| **Retry provisioning** | Connector timeout rồi worker retry | Readback, không duplicate/regrant |
| **Stale approval** | Phê duyệt từ trước sự kiện Mover mới | Re-evaluate trước fulfillment |
| **Exception chưa được duyệt** | PENDING_RISK_ACCEPTANCE | Không dùng để bypass |
| **Exception hết hạn** | Token còn role sau expiry | Deny/chặn action theo policy |
| **PDP unavailable** | Không có dữ liệu SoD khi action nhạy cảm | Không tự Permit |
| **Bulk action** | Một request tác động nhiều đối tượng | Đánh giá từng resource hoặc cơ chế tập hợp an toàn |
| **API bypass** | Gọi endpoint trực tiếp không qua UI | SoD vẫn được enforce |
| **Local account** | IGA gỡ role nhưng app còn direct grant | Finding còn OPEN |
| **Service identity** | Pipeline tự approve deployment | Kiểm trust boundary/human approval |
| **Cross-tenant global admin** | Quyền scope toàn org nhưng tên tenant A | Phát hiện scope thực thay vì tên |

### Các lớp kiểm thử

1. **Rule unit tests:** forbidden pairs/sets, điều kiện và scope.
2. **Schema tests:** thiếu subject ID, tenant, expiry hoặc enum không hợp lệ.
3. **Entitlement mapping tests:** role, group, direct grant và hierarchy.
4. **Integration tests:** IAM/IGA, HRIS, IdP, SCIM, PAM, app, policy engine.
5. **Workflow tests:** self-approval, createdBy, duplicate/late events.
6. **JML tests:** Joiner, Mover, Leaver, Rejoiner.
7. **Concurrency tests:** grant cạnh tranh revoke, approval cạnh tranh Mover.
8. **Adversarial tests:** đổi resource ID, payload fields, actingAs.
9. **Audit tests:** evidence đủ nhưng không lộ secrets.
10. **Reconciliation tests:** target đã thực sự chặn quyền và các đường cấp khác.

**Test chỉ xác minh các role name bị cấm là chưa đủ**. Cần kiểm **action thật trên tài nguyên cụ thể**, đặc biệt dynamic SoD.

## 34. Runbook: phát hiện và xử lý xung đột quyền

### Trường hợp A — Phát hiện conflict khi có Access request

1. Xác định **beneficiary, identity/relationship, target, action và scope**.
2. Đọc effective grants hiện tại từ các nguồn trong phạm vi.
3. Đối chiếu SoD rule ID, severity và nguyên nhân.
4. Nếu conflict thật và policy cấm, **không provision quyền mới**.
5. Cân nhắc thay bằng permission hẹp, revoke quyền cũ trước hoặc quy trình JIT.
6. Nếu cần exception, đưa tới risk owner/Security đúng thẩm quyền.
7. Revalidate ngay trước khi cấp và readback sau khi cấp.
8. Không đánh dấu fulfilled nếu còn toxic combination trái policy.

### Trường hợp B — Conflict phát hiện trong Access review

1. Xác minh reviewer có quyền và dữ liệu review còn mới.
2. Phân tích **grant source/provenance** và scope của mỗi permission.
3. Kiểm tra nhu cầu công việc, role/department hiện tại.
4. Chọn **REVOKE/MODIFY** với quyền không còn cần, hoặc escalate.
5. Thực hiện cleanup ở SCIM/API/PAM/cloud/local app.
6. Đối soát effective permissions sau thay đổi.
7. Kiểm session/token còn quyền cũ.
8. Đóng finding chỉ khi có evidence phù hợp.

### Trường hợp C — Hệ thống vẫn cho thực hiện action bị cấm

1. **Ưu tiên chặn action rủi ro tại PEP/RS** theo khả năng.
2. Xác định actor, action, resource, transaction history và policy version.
3. Kiểm runtime SoD hook có được gọi ở mọi API/consumer không.
4. Xác minh role, group, direct grant, session/token và cache.
5. Kiểm xem resource.createdBy hoặc other attributes có bị client sửa không.
6. Mở incident và kiểm tra các giao dịch đã thực hiện nếu có nguy cơ lạm dụng.
7. Sửa kiểm soát, test negative, ghi audit và đối soát.
8. Không coi chỉnh UI ẩn nút là đã khắc phục.

### Trường hợp D — Conflict sau Mover hoặc Leaver

1. Lấy source JML event mới nhất với version và effectiveAt.
2. Chặn job grant/regrant từ request hoặc approval lỗi thời.
3. Thu hồi role cũ và các active JIT grants không còn căn cứ.
4. Xử lý local sessions, JWT/PAT/API key và external account.
5. Kiểm target account mapping, tránh dùng email làm ID duy nhất.
6. Thử action có kiểm soát để xác nhận không còn Permit ngoài chính sách.
7. Ghi finding có owner/SLA nếu một hệ thống chưa thu hồi được.

## 35. Tình huống xuyên suốt: từ Joiner đến Leaver

Giả sử **Lan** vào doanh nghiệp ở bộ phận Procurement, sau đó chuyển sang Finance Payments và cuối cùng nghỉ việc. Tổ chức dùng **HRIS, IAM/IGA, IdP SSO, SCIM và API tài chính có RBAC/ABAC**.

### Giai đoạn 1 — Joiner

HRIS tạo personId và relationshipId cho Lan. IAM cấp role **VENDOR_READER** và **VENDOR_CREATOR** vì Lan cần quản lý nhà cung cấp. SoD engine kiểm catalog; Lan chưa có quyền payment.approve nên không phát hiện forbidden pair tương ứng. App vẫn kiểm tenant và resource scope ở runtime.

### Giai đoạn 2 — Access request ngoài baseline

Lan xin **PAYMENT_APPROVER** để hỗ trợ một dự án ngắn. IAM tính tập quyền dự kiến và phát hiện tổ hợp **vendor.create + vendor.payment.approve** trong cùng legal entity. Manager xác nhận nhu cầu nhưng Security yêu cầu **không cấp đồng thời**. Giải pháp là tìm approver độc lập hoặc thu hồi quyền vendor.create trước khi cấp role mới, tùy nghiệp vụ.

### Giai đoạn 3 — Mover

Sau một thời gian, Lan chính thức chuyển từ Procurement sang Finance Payments. IAM nhận Mover, tính lại desired state: **gỡ VENDOR_CREATOR**, cấp **PAYMENT_READER** và, sau approval hợp lệ, cấp **PAYMENT_APPROVER**. Do SCIM chậm, group VENDOR_CREATOR còn tồn tại vài phút. Với rule static nghiêm ngặt, hệ thống cần **chặn/đợi cấp PAYMENT_APPROVER** hoặc chặn quyền ở API cho tới khi revoke cũ được xác minh; không báo Mover hoàn tất khi cả hai quyền vẫn effective.

### Giai đoạn 4 — Dynamic SoD

Lan được cấp quyền approve nhưng thử duyệt một giao dịch do Lan khởi tạo từ trước. API kiểm **transaction.createdBy** và actor hiện tại nên trả **DENY** theo dynamic SoD, dù tại thời điểm này quyền vendor.create đã được thu hồi.

### Giai đoạn 5 — Access review

Campaign quý hiển thị entitlement Finance và một direct grant từ hệ thống legacy. Reviewer phát hiện direct grant **VENDOR_EDIT_BANK_ACCOUNT** không thuộc desired state. Quyết định **REVOKE**, connector thu hồi, readback kiểm tra cả group/role khác có cấp cùng action hay không. Finding chỉ đóng sau khi action bị chặn.

### Giai đoạn 6 — Leaver

Lan nghỉ việc hiệu lực ngay. IdP disable login, SCIM deprovision nhóm và tài khoản, PAM thu hồi sessions, IAM xử lý OAuth token, PAT/API key và local accounts theo phạm vi. Một reviewer không thể dùng quyết định RETAIN trước đó để mở lại quyền. SoD check và access reconciliation cùng xác minh không còn quyền trái căn cứ JML.

### Giai đoạn 7 — Rejoiner

Nếu Lan quay lại ở vị trí Data Analyst, IAM xác minh relationship mới và cấp role cần thiết, **không tự khôi phục VENDOR_CREATOR/PAYMENT_APPROVER**. SoD engine tính lại effective permissions và policy theo công việc mới.

### Kết luận tình huống

**Xung đột quyền không chỉ nằm trong một bảng cặp role.** Nó hình thành từ quyền thực tế qua nhiều nguồn, scope và lịch sử giao dịch, có thể thay đổi ở mỗi sự kiện JML. Kiểm soát hiệu quả phải đi từ **preventive assignment check đến dynamic enforcement và reconciliation**.

## 36. Checklist thiết kế kiểm soát xung đột quyền

1. **Định nghĩa:** mỗi conflict rule có mục đích nghiệp vụ và owner rõ?
2. **Phân loại:** đã phân biệt static, dynamic và workflow SoD?
3. **Permission-level:** kiểm action nghiệp vụ thay vì chỉ cặp tên role?
4. **Scope:** tenant, legal entity, project, resource và environment được kiểm đáng tin?
5. **Natural person:** cùng người qua nhiều account/relationship có được liên kết đúng?
6. **Effective grants:** role hierarchy, nested group, direct grant, delegation, JIT được tính?
7. **Multi-action:** có hỗ trợ forbidden set trên hai quyền và nhiều quyền khi cần?
8. **Mapping:** technical entitlement của app/cloud/DB có nghĩa hành động rõ?
9. **Catalog:** SoD matrix có rule ID, version, severity, expiry và test cases?
10. **Least privilege:** role mới không mở quyền rộng ngoài nhu cầu?
11. **Access request:** có check conflict trước cấp và revalidate trước fulfillment?
12. **Approval:** manager không tự override hard deny; Security/risk owner có thẩm quyền?
13. **Exceptions:** có scope, owner, thời hạn, compensating control và review?
14. **Dynamic enforcement:** API/transaction kiểm createdBy/actor và trạng thái nghiệp vụ?
15. **SoD across time:** người đã tạo giao dịch không tự approve sau khi chuyển role?
16. **JIT/PAM:** phân biệt eligible/active, activation conflict và session revocation?
17. **Joiner:** baseline/role assignment được kiểm SoD trước khi có hiệu lực?
18. **Mover:** revoke quyền cũ trước hoặc đồng thời với cấp mới có kiểm soát?
19. **Leaver:** không chờ campaign để cắt quyền, xử lý token/session/local credential?
20. **Rejoiner:** không phục hồi quyền và ngoại lệ theo relationship cũ?
21. **Service account:** workload có owner, permission hẹp và trust boundary rõ?
22. **Contractor:** hợp đồng, sponsor và delegation được đưa vào policy?
23. **IdP/SSO:** session/claims không được coi là chứng cứ duy nhất về effective quyền?
24. **SCIM:** gỡ membership ở đúng Group/target, có readback?
25. **Policy input:** identity, tenant, resource và time không tin client tự khai?
26. **Concurrency:** retry/version/fencing tránh job cũ tái cấp quyền?
27. **Authorization:** có default deny cho action nhạy cảm nếu thiếu dữ liệu?
28. **Review:** reviewer có thấy SoD findings và grant provenance?
29. **Audit:** lưu rule, subject, actions, source, scope, time và remediation evidence?
30. **Metrics:** đo finding, coverage, false positives và verified closure?
31. **Testing:** có negative, cross-tenant, dynamic/self-approval và race tests?
32. **Reconciliation:** đã xác minh quyền thực tế ở đích, gồm đường ngoài IAM?
33. **Risk closure:** exception/partial findings có owner, deadline và không bị che bởi KPI?

### Ghi nhớ

**Xung đột quyền là rủi ro do một chủ thể sở hữu hoặc thực hiện kết hợp các quyền mà chính sách yêu cầu phải được phân tách.** **Static SoD** kiểm việc gán quyền đồng thời; **dynamic SoD** kiểm hành vi, tài nguyên và lịch sử giao dịch tại thời điểm thực thi. Phát hiện xung đột phải dựa trên **effective permissions, scope, nhiều tài khoản, role hierarchy, nested groups, direct grants, JIT và dữ liệu nghiệp vụ đáng tin**, không chỉ tên role. Trong quản lý **Joiner–Mover–Leaver**, cần **kiểm trước khi cấp, thu hồi quyền cũ khi Mover, chặn truy cập sau Leaver và xác minh tại hệ thống đích**. Kết hợp **RBAC/ABAC/PBAC, IdP/SSO, SCIM, PAM/JIT, approval, SoD rules, audit và reconciliation** mới giúp ngăn **quyền truy cập tồn dư và thao tác trái trách nhiệm phân tách**.
