# Quy tắc SoD trong IAM: tách biệt nhiệm vụ, ngăn xung đột quyền và giao dịch

**Separation/Segregation of Duties (SoD) – phân tách nhiệm vụ** là nguyên tắc không để một chủ thể tự mình kiểm soát toàn bộ những bước có thể dẫn tới gian lận, sai sót hoặc lạm dụng đặc quyền trong một quy trình quan trọng. Trong IAM, **quy tắc SoD** xác định **những quyền, vai trò, hành động hoặc quan hệ nào không được cùng tồn tại hoặc không được sử dụng bởi cùng một chủ thể trong cùng bối cảnh**. Quy tắc phải được đánh giá khi **cấp quyền**, khi **thay đổi quyền**, và tại **điểm thực thi nghiệp vụ** nếu xung đột phụ thuộc vào từng giao dịch.

Bài **“Quy tắc SoD”** thuộc chương **Segregation of duties**, trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi module là quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh danh tính, tạo tài khoản, cấp quyền theo vai trò, rà soát quyền khi chuyển nhiệm vụ, thu hồi khi rời tổ chức; kết nối với **IdP, SSO, SCIM, RBAC/ABAC, service account, kiểm toán** và giảm **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Nhân viên Lan đã được cấp quyền **tạo lệnh thanh toán** và nay yêu cầu quyền **duyệt lệnh thanh toán** vì vừa chuyển sang vai trò mới. Nếu ứng dụng chỉ kiểm xem Lan có role Approver thì Lan có thể tạo rồi tự duyệt giao dịch mình lập. Ngay cả khi Lan cần cả hai loại công việc trong những tình huống khác nhau, quy tắc SoD vẫn có thể yêu cầu **không được dùng cả hai vai trò cho cùng một giao dịch**, có phê duyệt độc lập và kiểm soát tại thời điểm commit. Đây là lý do SoD không chỉ là bảng liệt kê hai nhóm không được cấp cùng nhau.

## 1. Vì sao cần quy tắc SoD?

SoD nhằm giảm rủi ro khi một người hoặc một workload có khả năng **tự khởi tạo, tự phê duyệt và tự hoàn tất** một hoạt động nhạy cảm. Những ví dụ điển hình:

- **Thanh toán:** người tạo lệnh không được tự duyệt chính lệnh đó.
- **Mua sắm:** người đề nghị mua không nên đồng thời là người phê duyệt và ghi nhận nhận hàng khi chính sách cần các bước độc lập.
- **Kế toán:** người nhập bút toán không được tự kiểm duyệt bút toán do mình tạo.
- **Nhân sự:** người đề nghị thay đổi mức lương không được tự phê duyệt thay đổi của chính mình.
- **IAM:** người yêu cầu cấp quyền quản trị không được tự phê duyệt quyền đó; người quản lý policy không nên có toàn quyền sửa/xóa audit evidence của mình.
- **Phát triển phần mềm:** người thay đổi mã hoặc cấu hình có thể phải cần reviewer/phê duyệt release độc lập trước khi deploy production.
- **Quản lý dữ liệu:** người cấp quyền truy cập dữ liệu nhạy cảm không nên tự chứng nhận hoặc tự miễn trừ các kiểm soát có liên quan.

Mục đích là bảo vệ **tính độc lập của các bước kiểm soát**, không đơn thuần tối thiểu hóa số vai trò. Một hệ thống có thể có least privilege ở từng role nhưng vẫn vi phạm SoD nếu cùng người sở hữu **tập hợp role tạo thành chuỗi quyền nguy hiểm**.

### Phạm vi của SoD

| Loại kiểm soát | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Phòng ngừa khi gán quyền** | Chủ thể có được sở hữu hai entitlement này cùng lúc không? | Không đồng thời giữ RoleCreator và RoleApprover trong cùng scope. |
| **Phòng ngừa khi kích hoạt** | Chủ thể có được dùng hai vai trò trong cùng phiên/tác vụ không? | Người eligible hai vai trò chỉ được kích hoạt một vai trò phù hợp. |
| **Phòng ngừa tại giao dịch** | Chủ thể có đang xử lý tài nguyên mà chính họ đã tạo hoặc tác động ở bước trước không? | Từ chối self-approval theo invoice.requesterId. |
| **Phát hiện sau sự kiện** | Có xung đột nào chưa bị chặn hoặc phát sinh qua nguồn quyền khác không? | Phát hiện user đã tự tạo và tự duyệt một payment. |
| **Quản trị quyền** | Ai phê duyệt thay đổi và ngoại lệ? | Không tự phê duyệt request/grant thuộc chính mình. |

## 2. SoD khác least privilege, authentication và approval

| Khái niệm | Điều kiểm soát | Vì sao chưa thay thế SoD? |
| --- | --- | --- |
| **Authentication/MFA** | Ai đang truy cập và mức bảo đảm xác thực. | Người được xác thực rất tốt vẫn có thể tự duyệt việc mình tạo. |
| **RBAC** | Chủ thể có role/permission nào. | Hai role hợp lệ riêng lẻ có thể xung đột khi kết hợp. |
| **ABAC** | Thuộc tính subject/resource/context ảnh hưởng quyết định. | Cần viết rõ điều kiện cấm xung đột; ABAC không tự suy ra SoD. |
| **Least privilege** | Chỉ cấp quyền cần thiết, đúng phạm vi/thời gian. | Một người có thể cần hai quyền cho hai việc khác nhau nhưng vẫn không được dùng cùng transaction. |
| **Approval workflow** | Người có thẩm quyền đồng ý cấp quyền/tác vụ. | Nếu reviewer trùng actor hoặc API không kiểm độc lập, approval chỉ là hình thức. |
| **PAM/JIT** | Kích hoạt đặc quyền tạm và có điều kiện. | Hai vai trò xung đột vẫn có thể được kích hoạt nối tiếp để hoàn tất giao dịch trái policy. |
| **Audit** | Ghi lại các quyết định/hành động. | Audit giúp phát hiện, nhưng không tự chặn vi phạm đang xảy ra. |

**SoD cần được diễn đạt thành điều kiện có thể kiểm thử**, không chỉ gắn nhãn “rủi ro cao”. Ví dụ “người tạo hóa đơn không được phê duyệt hóa đơn đó” là một ràng buộc thực thi; “Role Approver cần MFA” là một biện pháp assurance bổ sung, không thay thế ràng buộc người tạo khác người duyệt.

## 3. SoD tĩnh (SSD) và SoD động (DSD)

### 3.1 Static Separation of Duties – SSD

**SSD** hạn chế việc **gán/giữ đồng thời** một tập role hoặc permission cho một subject theo phạm vi quy định.

Ví dụ chính sách:

~~~text
Trong tenant VN, một human principal KHÔNG ĐƯỢC
đồng thời có effective entitlements:
  payment.create
  payment.approve
~~~

SSD phù hợp khi chính sách thực sự yêu cầu **không có khả năng thực hiện cả hai nhiệm vụ**. Nó thường được kiểm trong IGA, access request và reconciliation trước khi provision.

### 3.2 Dynamic Separation of Duties – DSD

**DSD** cho phép một chủ thể có thể đủ điều kiện đối với nhiều vai trò, nhưng giới hạn **vai trò được kích hoạt đồng thời** hoặc **những hành động có thể thực hiện đối với một workflow/transaction cụ thể**.

Ví dụ:

~~~text
Lan có thể tạo một hóa đơn trong dự án A
và duyệt hóa đơn do người khác tạo trong dự án B.
Nhưng Lan KHÔNG ĐƯỢC duyệt hóa đơn có createdBy=Lan.
~~~

Một quy tắc **transaction-level SoD** như trên có thể được triển khai bằng ABAC hoặc logic nghiệp vụ tại backend. Nó **không đồng nhất** với DSD chỉ giới hạn **active roles trong phiên**: nếu user kích hoạt role Creator, logout rồi kích hoạt Approver, kiểm phiên đơn thuần vẫn có thể bị vượt. Để ngăn self-approval, backend phải kiểm **lịch sử vai trò/tác nhân trên chính resource**.

### So sánh

| Tiêu chí | SSD | DSD / transaction-level SoD |
| --- | --- | --- |
| Đối tượng kiểm soát | Cấp/giữ quyền cùng lúc. | Kích hoạt vai trò, sử dụng quyền, chuỗi thao tác. |
| Khi kiểm | Access request, provisioning, access review, JML. | Activation, API authorization, transaction commit. |
| Dữ liệu cần | Vai trò, entitlement, hierarchy, scope. | Effective role và lịch sử actor, resource, workflow state. |
| Điểm mạnh | Ngăn xung đột ngay từ khâu cấp quyền. | Linh hoạt khi một người cần nhiều vai trò nhưng không được xung đột trong một tác vụ. |
| Giới hạn | Có thể chặn quá mức trong tổ chức nhỏ. | Phức tạp hơn; cần PEP/transaction checks tin cậy. |

**Không gọi một kiểm tra tại login là đã kiểm SoD của mọi giao dịch.** Tùy policy, có thể cần đồng thời **SSD ở IAM** và **transaction-level checks tại ứng dụng**.

## 4. Mô hình hóa một quy tắc SoD

Một quy tắc nên đủ chi tiết để **PDP hoặc workflow** có thể đánh giá, reviewer hiểu được và kỹ sư viết test oracle độc lập.

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **ruleId/version** | Định danh và phiên bản. | SOD-PAYMENT-001 v3. |
| **Business purpose** | Rủi ro muốn ngăn. | Chặn gian lận tự tạo–tự duyệt thanh toán. |
| **Subject scope** | Human, contractor, workload, role/department nào. | Workforce trong Finance. |
| **Tenant/environment** | Phạm vi tenant, system, production/staging. | Finance production, từng tenant độc lập. |
| **Conflicting activities** | Chức năng bị xem là xung đột. | payment.create và payment.approve. |
| **Permission/role mapping** | Các role/grant có thể thực hiện hoạt động. | PAYMENT_CREATOR, PAYMENT_APPROVER, direct ACL. |
| **Constraint type** | SSD, DSD, transaction-level hoặc approval SoD. | Transaction-level self-approval DENY. |
| **Resource relation** | Cùng transaction, owner, requester, account hoặc project. | payment.createdBy != approver.subjectId. |
| **Time window** | Vai trò đồng thời, active session hay cùng kỳ giao dịch. | Trong toàn bộ workflow của một payment. |
| **Enforcement point** | IGA trước grant, PAM activation, API/DB commit. | Finance API approve endpoint. |
| **Combining/precedence** | Khi rule xung đột với ALLOW khác. | Non-waivable SoD deny ưu tiên. |
| **Exceptions/compensation** | Có cho ngoại lệ không; ai phê duyệt, thời hạn. | Ngoại lệ có dual control, nếu policy cho phép. |
| **Evidence/test coverage** | Test case, log, version, owner. | SOD-T12, finance-api v5. |

### YAML mô hình minh họa

~~~yaml
ruleId: SOD-PAYMENT-SELF-APPROVE
version: 3
owner: finance-risk-control
constraintType: TRANSACTION
subjectType: HUMAN
environment: production
action: payment.approve
resourceType: PAYMENT
denyWhen:
  - subjectIdEquals: resource.createdBySubjectId
  - subjectIdEquals: resource.lastMaterialEditorSubjectId
scope:
  tenantMustMatch: true
  workflowState: PENDING_APPROVAL
enforcement:
  - FINANCE_API
  - PAYMENT_COMMIT_SERVICE
exceptionPolicy: NON_WAIVABLE_IN_ORDINARY_FLOW
audit:
  logRuleIdAndVersion: true
  logCorrelationId: true
~~~

Đây **không phải schema chuẩn** của SCIM, OAuth, XACML hay một công cụ IGA; chỉ là mẫu mô tả rule. Điều kiện **lastMaterialEditorSubjectId** phụ thuộc nghiệp vụ: có thể cần xét người sửa số tiền, người thay người thụ hưởng hoặc bất kỳ thay đổi có tác động quan trọng. Không tự coi trường minh họa là quy tắc bắt buộc cho mọi hệ thống.

## 5. Khác nhau giữa role, permission và business activity

SoD thường được định nghĩa theo **business activity** vì role có thể thay đổi tên, kế thừa nhiều quyền hoặc được cấu hình khác nhau giữa ứng dụng.

~~~text
Business activity:  APPROVE_PAYMENT
        |
        +-- FinancePortal role PAYMENT_APPROVER
        +-- ERP permission approvePayment
        +-- Legacy API endpoint POST /payments/{id}/approve
        +-- Admin override permission payment.workflow.manage
~~~

Nếu policy chỉ cấm tên role PAYMENT_APPROVER, người dùng có thể dùng một **admin override** hoặc quyền khác có cùng khả năng để vượt. Quy tắc SoD cần ánh xạ **mọi entitlement tạo ra activity**, bao gồm:

- Direct role, nested group, local ACL.
- Inherited/admin/wildcard permission.
- Delegation hoặc impersonation.
- Service account thay mặt người dùng.
- API/batch/job hoạt động không qua UI.
- Quyền emergency và temporary/JIT trong phạm vi liên quan.

### Ma trận activity–entitlement

| Business activity | Role/quyền có thể thực hiện | Tài nguyên/điều kiện |
| --- | --- | --- |
| CREATE_PAYMENT | PaymentCreator, FinanceAdmin. | Tenant, tài khoản nguồn, hạn mức. |
| MODIFY_PAYMENT | PaymentEditor, FinanceAdmin. | Payment chưa được duyệt, change history. |
| APPROVE_PAYMENT | PaymentApprover, FinanceAdmin, emergency override. | Pending state, đủ assurance, khác người tạo/sửa. |
| EXECUTE_PAYMENT | TreasuryExecutor, PaymentAdmin. | Payment đã được phê duyệt, giới hạn ngân hàng. |
| GRANT_PAYMENT_ROLE | IAMRoleAdmin, FinanceSecurityAdmin. | Approval từ owner độc lập, đúng scope. |

Một business activity có nhiều đường kỹ thuật; **ma trận SoD phải dựa trên capability đã giải nghĩa**, không chỉ group name được hiển thị trong directory.

## 6. Ma trận các cặp hoạt động xung đột

Ví dụ **ma trận policy đào tạo** cho một hệ thống thanh toán:

| Activity A | Activity B | Loại conflict | Lý do |
| --- | --- | --- | --- |
| Create payment | Approve cùng payment | **Transaction-level** | Không cho tự tạo–tự duyệt. |
| Modify beneficiary | Approve cùng payment | **Transaction-level** | Chống tự sửa người nhận rồi tự duyệt. |
| Approve payment | Execute payment | **SSD hoặc DSD theo thiết kế** | Tách người kiểm và người giải ngân nếu chính sách yêu cầu. |
| Create supplier | Approve supplier | **Transaction-level** | Tách tạo nhà cung cấp khỏi xác nhận. |
| Maintain payment policy | Audit payment policy changes | **Governance SoD** | Người sửa policy không tự chứng nhận thay đổi. |
| Request privileged access | Approve cùng access request | **Approval SoD** | Không tự cấp quyền qua luồng yêu cầu. |
| Create account | Approve privileged role grant | **Assignment SoD** | Tách chức năng khởi tạo và duyệt quyền cao. |
| Deploy release | Approve cùng release | **Transaction-level** | Kiểm soát người xây và người phê duyệt phát hành. |
| Change audit configuration | Erase audit history | **Strict restriction** | Không để một chủ thể tự che dấu vết lạm dụng. |

**Không áp dụng ma trận này máy móc cho mọi tổ chức.** Một số nghiệp vụ có các bước và quyền khác nhau; owner phải xác định **business risk, accountabilities, technical feasibility và compensating controls**, rồi chuẩn hóa thành chính sách được phê duyệt.

### Ví dụ ma trận role incompatibility

| Role | PaymentCreator | PaymentApprover | TreasuryExecutor | FinanceReader |
| --- | --- | --- | --- | --- |
| **PaymentCreator** | — | X (nếu áp SSD) | Theo policy | Không |
| **PaymentApprover** | X (nếu áp SSD) | — | X (nếu áp SSD) | Không |
| **TreasuryExecutor** | Theo policy | X (nếu áp SSD) | — | Không |
| **FinanceReader** | Không | Không | Không | — |

Trong bảng này **X** là cặp được định nghĩa xung đột **nếu tổ chức chọn mô hình SSD**; một hệ thống dùng transaction-level SoD có thể cho phép giữ cả hai role nhưng cấm hành động trên cùng payment. **Không trộn hai mô hình** khi viết test hay khi đếm vi phạm.

## 7. Tập ràng buộc và ngưỡng cardinality

Ngoài các cặp xung đột, SoD có thể định nghĩa một tập role/permission mà subject **không được giữ hoặc kích hoạt quá một số lượng nhất định**.

Ví dụ:

~~~text
Rule set:
  {PAYMENT_CREATOR, PAYMENT_APPROVER, TREASURY_EXECUTOR}
SSD cardinality:
  Subject có thể được gán tối đa 1 role trong tập
  nếu policy chọn tách ba bước hoàn toàn.
~~~

Trong các mô hình RBAC hình thức, SSD/DSD có thể có constraint dạng **(role set, cardinality)**. Cần đọc đúng **ngữ nghĩa của implementation**, vì một số đặc tả mô tả ngưỡng **k** là số role mà subject *không được đạt tới*, trong khi một giao diện quản trị lại mô tả **maxAllowed**. Tránh nhầm điều kiện “cấm từ k role trở lên” với “được phép tối đa k role”.

### Nhiều chủ thể trong quy trình

Một giao dịch có thể yêu cầu **ít nhất hai người độc lập** cho hai hoạt động. Đừng cố diễn đạt mọi quy tắc bằng số role mỗi user: ứng dụng cần lưu **actor identity** của từng bước và kiểm không trùng actor theo chính sách.

### Đơn vị scope

Một rule có thể áp cho:

- **Toàn doanh nghiệp:** vai trò security auditor và người có quyền xóa audit.
- **Cùng tenant:** người duyệt và người thực hiện thanh toán trong một đơn vị.
- **Cùng tài nguyên/giao dịch:** người tạo payment không duyệt chính payment đó.
- **Cùng khoảng thời gian/phiên:** không kích hoạt hai privileged roles đồng thời.
- **Cùng dự án hoặc hạn mức:** người thay budget không tự duyệt budget vừa thay.

**Scope rộng hơn có thể gây false deny; scope hẹp hơn có thể bỏ lọt conflict.** Vì vậy rule phải nêu rõ giới hạn và có test các trường hợp ranh giới.

## 8. Role hierarchy, nested groups và effective permissions

Quy tắc SoD không thể chỉ kiểm hai role được gán **trực tiếp**. Một người có thể nhận khả năng thực thi hoạt động xung đột từ **role kế thừa, nested group, local permission hoặc quyền quản trị tổng quát**.

~~~mermaid
flowchart TD
    U["User: person-4821"] --> GA["Group: FinanceOperations"]
    GA --> RC["Role: PaymentCreator"]
    U --> GB["Group: FinanceLeads"]
    GB --> RA["Role: FinanceAdmin"]
    RA --> PA["Permission: payment.approve"]
    RA --> GR["Permission: grantRole"]
    RC --> PC["Permission: payment.create"]
    PC --> S["SoD effective activity resolver"]
    PA --> S
    S --> C{"Conflict trong scope hiện hành?"}
    C -->|Có| D["BLOCK / REMEDIATE"]
    C -->|Không| A["Tiếp tục policy checks"]
~~~

Ở ví dụ trên, user không được gán role PaymentApprover theo tên nhưng **FinanceAdmin cung cấp permission approve**. Resolver cần phát hiện xung đột trên **capability thực tế**.

### Những nguồn quyền phải tính

| Nguồn | Rủi ro | Cách kiểm |
| --- | --- | --- |
| Direct role | Gán thẳng Approver cho subject. | Role assignment inventory và target readback. |
| Nested group | Quyền Approver từ nhóm con/cha. | Giải quan hệ kế thừa có kiểm soát, không chỉ một tầng group. |
| Role hierarchy | Senior role bao gồm junior permissions. | SoD xét permissions được kế thừa theo đúng semantics. |
| Direct ACL | Quyền approve được gắn một resource cụ thể. | Effective access theo resource, không chỉ global role. |
| Tenant-wide admin | Có thể cấp quyền hoặc điều chỉnh workflow. | Kiểm quyền trực tiếp và quyền **grant/impersonate** gián tiếp. |
| OAuth scope | Client có scope rộng tại API. | Scope không thay business authorization; kiểm actor và action. |
| Service account | User có thể assume service principal để thao tác. | Kiểm trust delegation, secret access và provenance. |
| Cached session/claim | Quyền cũ còn trong phiên. | Kiểm quyết định ở PEP sau Mover/Leaver theo SLA. |

### Quyền chưa kích hoạt có tính là xung đột SSD?

Một user **eligible** để kích hoạt role qua PAM/PIM không nhất thiết đang có role **active**. Tùy chính sách:

- SSD nghiêm ngặt có thể **cấm cả khả năng** tự kích hoạt hai role xung đột, nhất là nếu activation không cần phê duyệt.
- DSD có thể cho phép eligible cả hai, nhưng **không cho kích hoạt đồng thời**.
- Transaction-level rule vẫn phải chặn **tự duyệt** kể cả khi user đã tắt role Creator trước khi kích hoạt Approver.

Inventory nên phân biệt **ASSIGNED, ELIGIBLE, ACTIVATED, EFFECTIVE, EXPIRED/REVOKED**. Một phép kiểm chỉ đọc role active có thể bỏ lọt khả năng nâng quyền từ eligibility, impersonation hoặc secret.

## 9. Đặt quy tắc ở đâu: IGA, PDP, PEP và workflow?

Một kiểm soát SoD vững chắc thường cần **nhiều lớp**, không dồn mọi thứ vào một công cụ.

~~~mermaid
flowchart LR
    HR["HRIS / JML source"] --> IGA["IGA: request + SoD assignment rules"]
    POL["Policy Administration<br/>SoD rule inventory"] --> IGA
    IGA --> SCIM["SCIM / API Provisioning"]
    SCIM --> APP["Application roles / accounts"]
    POL --> PDP["PDP: transaction policy"]
    ATTR["PIP: identity/resource state"] --> PDP
    APP --> PEP["PEP: payment API / commit"]
    PDP --> PEP
    PEP --> DB["Protected workflow + database"]
    PEP --> AUD["Audit / SIEM"]
    IGA --> AUD
~~~

| Kiểm tra | Lớp thích hợp | Vai trò |
| --- | --- | --- |
| **SSD trước cấp quyền** | Access request/IGA. | Từ chối grant gây xung đột theo effective entitlements và scope. |
| **SSD sau đồng bộ** | Reconciliation/target connector. | Phát hiện role/ACL khác nguồn, grant trực tiếp không đi qua IGA. |
| **DSD trước activation** | PAM/PIM hoặc application session manager. | Không cho kích hoạt đồng thời các vai trò không tương thích. |
| **Self-approval ở giao dịch** | Backend API/PEP và domain transaction. | So sánh trusted actor với requester/last material editor. |
| **Role/self-approval management** | IGA approval API/PEP. | Ngăn người hưởng quyền tự duyệt ticket. |
| **Policy administration SoD** | PAP/change control. | Tách người viết rule, người duyệt, người deploy/kiểm toán. |
| **Detective SoD** | Audit/SIEM, governance review. | Phát hiện biến động quyền trái policy hoặc giao dịch xung đột đã xảy ra. |

**PDP trả DENY nhưng endpoint không gọi PDP vẫn là lỗi.** Unit test policy phải được bổ sung **API/integration tests** cho từng đường thực thi và **no-side-effect assertions** khi bị từ chối.

## 10. Quy tắc SoD ở thời điểm xin và cấp quyền

Một yêu cầu truy cập không nên được đánh giá trên **role mới đứng riêng**. Phải tính **effective access before + requested grant**, bao gồm inheritance và quyền đang có ở các hệ thống liên quan.

### Luồng đề xuất

1. **Nhận request**: subject ID ổn định, requester, entitlement, tenant, scope, business reason, thời hạn.
2. **Kiểm lifecycle**: HRIS/IGA current state, effectiveAt, contractor/sponsor; Leaver hoặc suspended không được cấp quyền trái policy.
3. **Resolve grants hiện có**: roles, nested groups, ACL, eligible/active grants, JIT, delegated permissions.
4. **Ánh xạ thành business activities**: không chỉ so tên nhóm.
5. **Tính trạng thái sau cấp dự kiến**: bao gồm scope/tenant, role hierarchy và conditions.
6. **Chạy SSD/SoD rules và policy gates**: conflict nào là hard DENY, conflict nào có thể xử lý theo ngoại lệ?
7. **Nếu conflict**: giảm scope, thu hồi quyền cũ, tách tác vụ hoặc yêu cầu phương án kiểm soát được duyệt.
8. **Định tuyến approval**: data/process owner và security/SoD owner theo rủi ro, chặn self-approval.
9. **Đóng băng approved snapshot**: role/version, subject, target, tenant, validity và quyết định.
10. **Revalidate ngay trước provision**: HR state, quyền hiện có và SoD có thể thay đổi giữa lúc duyệt và cấp.
11. **Provision chính xác** qua SCIM/API/PAM và readback target.
12. **Verify effective access** cho action được phép lẫn action bị cấm; audit kết quả.

### Cách xử lý conflict

| Phát hiện | Phản ứng phù hợp |
| --- | --- |
| SSD non-waivable conflict. | **DENY** grant gây conflict hoặc thu hồi quyền xung đột trước; không bù trừ bằng risk score. |
| Vai trò mới cần nhưng vai trò cũ đã hết nhiệm vụ. | **Revoke-before-grant** khi policy yêu cầu, rồi verify không còn conflict. |
| Hai vai trò hợp lệ cho các dự án độc lập. | Xem **scope-specific** SoD; đừng chặn toàn doanh nghiệp nếu rule chỉ cấm cùng project. |
| DSD có kiểm soát session. | Eligible có thể được giữ, activation tuân thủ session constraint. |
| Transaction-level self-approval. | Để app/PEP kiểm tại mỗi giao dịch; không coi việc cấp role là miễn kiểm. |
| Target không thể áp restriction được duyệt. | Không cấp grant rộng hơn approved scope, chuyển thiết kế/exception có thẩm quyền. |

**Một approval do manager ký không làm biến mất conflict.** Approval chỉ có giá trị nếu người ký có **quyền chấp nhận rủi ro phù hợp**, ngoại lệ được policy cho phép và kiểm soát bù trừ thực sự được áp.

## 11. SoD trong Joiner–Mover–Leaver

### Joiner — baseline role và chuẩn hóa

Khi một nhân viên mới vào tổ chức, quy tắc SoD cần áp dụng cho **toàn bộ tập baseline entitlements** trước khi activation:

- Onboarding role bundle có chứa hai business activities xung đột không?
- Group nested trong IdP có mở rộng quyền ngoài mô tả role không?
- Account được pre-provision trước start date nhưng chưa active có được chặn quyền nghiệp vụ không?
- Có cấp nhầm AppAdmin vì tài khoản Joiner được gán role mặc định quá rộng?
- Mỗi role có business/data owner và approval rõ không?

### Mover — thời điểm SoD dễ phát sinh nhất

Nhân viên chuyển từ **Payment Operations** sang **Payment Control** có thể giữ role Creator cũ qua app-local ACL và nhận thêm Approver mới:

~~~text
Before Mover:
  payment.create = ALLOW
  payment.approve = DENY

Desired after Mover:
  payment.create = DENY
  payment.approve = ALLOW (với transaction safeguards)

Incorrect actual after Mover:
  payment.create = ALLOW  <-- residual
  payment.approve = ALLOW <-- newly provisioned
~~~

Quy trình phải tính **to-revoke, to-keep, to-grant**, kiểm SoD theo trạng thái thực:

1. Thu hồi role Creator ở **tất cả đường cấp** liên quan.
2. Readback application roles, ACL, nested groups và target account.
3. Kiểm bằng API rằng Creator không còn hiệu lực theo SLA.
4. Kiểm entitlement Approver mới và transaction-level self-approval logic.
5. Nếu chính sách bắt buộc không có khoảng chồng lấn, đảm bảo thứ tự/transaction/activation guard tương ứng.
6. Ghi event revision và chống Mover cũ tái tạo quyền sau Leaver.

**Cấp role mới rồi sẽ gỡ role cũ sau có thể tạo cửa sổ SoD nguy hiểm.** Với hệ thống phân tán, có thể cần trì hoãn activation role mới cho tới khi các revoke cũ bắt buộc đã VERIFIED.

### Leaver và suspended subject

Khi quan hệ kết thúc, trọng tâm là **thu hồi mọi effective access**, không chỉ loại bỏ một conflict. Các quyền của Leaver có thể còn qua:

- Session SSO/SP và cached application roles.
- OAuth access token hoặc refresh grants.
- Direct ACL, SaaS local account, PAT/API key.
- Quyền được ủy quyền, break-glass credential đã biết, workload secrets.

Một conflict có thể biến mất trong bản kê IdP vì user bị gỡ khỏi group, nhưng **PEP vẫn ALLOW** với token hoặc local session cũ. Review SoD sau Leaver cần gắn với **deprovisioning verification**, không tuyên bố an toàn chỉ nhờ trạng thái directory.

### Rehire và contractor expiry

Tuyển lại người từng làm việc không có nghĩa quyền cũ được hợp thức hóa: cần identity linking đúng, approvals mới và tính SoD với vai trò hiện hành. Nhà thầu hết hạn phải bị chặn dù một ticket cấp quyền tạm trước đó chưa được xử lý xong.

## 12. IdP/SSO, SCIM và token trong thực thi SoD

| Thành phần | Chức năng | Điều SoD phải kiểm |
| --- | --- | --- |
| **HRIS** | Trạng thái và chuyển vai trò. | Event mới nhất, effectiveAt và identity mapping. |
| **IGA** | Role requests, assignment checks và recertification. | SSD theo effective entitlements, approval SoD. |
| **IdP/directory** | Group, authentication, SSO context. | Nested group, role claims và account lifecycle. |
| **SCIM** | Provision/deprovision users/groups. | Target readback, không chỉ HTTP success. |
| **OAuth Authorization Server** | Cấp access token/client grants và refresh tokens. | Scope, client, revocation và thời hạn. |
| **Resource Server/PEP** | Quyết định request API. | Transaction actor, business activity và deny rule. |
| **PAM/PIM** | Kích hoạt quyền đặc biệt. | DSD role activation, step-up, TTL, session controls. |
| **SaaS local authz** | Direct role, object ACL, service tokens. | SoD conflicts ngoài IdP/SCIM inventory. |

### Những ranh giới cần hiểu đúng

**SSO** hỗ trợ xác thực/thiết lập phiên tin cậy; không tự đảm bảo user không thể tự duyệt payment. **SCIM** cung cấp provisioning Users/Groups, không phải giao thức thu hồi mọi session hay kiểm SoD business transaction.

**OAuth scope** có thể giới hạn loại API, nhưng không thay thế kiểm tra actor được xác minh **khác người tạo giao dịch**. **OIDC ID token** dùng cho client xác minh kết quả đăng nhập, không nên dùng thay access token để gọi protected API.

### Token cũ sau Mover

Nếu access token JWT tự chứa mang claim Creator vẫn hợp lệ về chữ ký và thời hạn, backend không nên mặc nhiên coi claim đó là trạng thái quyền vĩnh viễn. Tùy kiến trúc và mức rủi ro, có thể dùng TTL ngắn, introspection, entitlement version/current-state check, denylist hoặc revoke mechanisms. Cần kiểm **thực tế tại PEP** theo SLA.

**Không tuyên bố có thể revoke tức thời mọi JWT** nếu không có cơ chế tương ứng ở Resource Server. Đối với SoD nhạy cảm, transaction-level check phải dựa trên **trusted actor/resource history** và cập nhật chính sách kịp thời.

## 13. Quy tắc phê duyệt quyền IAM cũng cần SoD

SoD không chỉ bảo vệ ứng dụng Finance mà còn bảo vệ **chính quy trình quản trị quyền**.

~~~mermaid
sequenceDiagram
    participant R as Requester / Beneficiary
    participant I as IGA Access Request
    participant O as Business/Data Owner
    participant S as Security/SoD Reviewer
    participant C as Connector / Target
    participant A as Audit
    R->>I: Xin privileged role + scope + TTL
    I->>I: Verify subject and SSD conflicts
    I->>O: Review business need
    O-->>I: Approval/reduction/reject
    I->>S: Independent SoD/privileged review if required
    S-->>I: Approved constraints
    I->>I: Recheck state, role version, SoD
    I->>C: Apply immutable approved grant
    C-->>I: Applied target state
    I->>C: Readback + effective access probe
    I->>A: Decision, actor, policy, evidence
~~~

### Các hành vi phải cấm hoặc kiểm soát

| Hành vi | SoD control |
| --- | --- |
| Người xin admin tự bấm Approve cho chính mình. | Review authority check tại **backend approval API**. |
| Admin provisioner sửa entitlement sau khi owner duyệt. | Approved snapshot/digest và kiểm chính xác delta trước apply. |
| Người sửa policy tự ký xác nhận policy đó an toàn. | Independent change approval; audit có bảo vệ. |
| Người đang bị điều tra có thể xóa log của chính họ. | Tách audit administration và privileged operations. |
| Reviewer dùng một bot có quyền cao để bypass SoD. | Audit actor/delegation và workload permission boundaries. |
| Manager vắng mặt khiến hệ thống auto-approve quyền High. | Escalation tới authority hợp lệ, không approve do im lặng. |

**Hậu kiểm có thể phù hợp một số tình huống khẩn**, nhưng không nên mặc định thay thế approval trước quyền nhạy cảm; cần policy emergency riêng, scope/TTL và audit.

## 14. DSD và SoD theo transaction: kiểm tại thời điểm commit

Một rule thường gặp:

~~~text
DENY payment.approve IF
  currentActor == payment.createdBy
  OR currentActor == payment.lastMaterialEditor
  OR payment.status != PENDING_APPROVAL
  OR currentActor not authorized by current policy
~~~

**Không tin actorId do client tự khai.** Actor phải lấy từ security context đã xác minh; trường createdBy/lastMaterialEditor phải lấy từ **bản ghi tài nguyên ở backend** với integrity thích hợp.

### Vì sao cần check ở commit?

Ví dụ:

~~~text
10:00:00  API xác minh Lan có Approver role = true.
10:00:01  Lan hoặc dịch vụ khác thay đổi payment beneficiary.
10:00:02  Role Approver của Lan bị gỡ theo Mover.
10:00:03  API ghi APPROVED dựa trên dữ liệu cũ.
~~~

Đây là rủi ro **TOCTOU (time-of-check to time-of-use)**: quyền hoặc trạng thái tài nguyên đổi giữa lúc kiểm và lúc dùng. Với thao tác tài chính nhạy cảm, cần thiết kế transaction boundary:

- Tải **payment hiện tại** và actor history trong transaction đáng tin.
- Kiểm state, SoD, limit và authorization ngay trước quyết định ghi.
- Có **optimistic locking/version check** hoặc transaction isolation phù hợp.
- Không gửi downstream event/thanh toán trước khi các điều kiện đã đạt.
- Đảm bảo retry không tự tạo double approval hoặc bypass SoD.
- Audit cả actor thực và **on-behalf-of principal** nếu có delegation.

**Không phải mọi nghiệp vụ đều phải khóa database theo cùng cách**; mức nhất quán cần xác định từ hậu quả và đặc tả giao dịch. Nhưng nếu transaction-level SoD có ý nghĩa, chỉ kiểm tại UI hoặc lúc login là không đủ.

## 15. Quy tắc SoD trong hệ thống phân tán và nhiều ứng dụng

Một người có thể thực hiện **bước tạo** ở ứng dụng A và **bước duyệt** ở ứng dụng B:

~~~mermaid
flowchart LR
    U["Human actor"] --> A["Procurement App<br/>Create supplier"]
    U --> B["ERP Finance<br/>Approve invoice"]
    A --> E["Shared business object<br/>supplier/payment provenance"]
    B --> E
    E --> S["Cross-application SoD evaluation"]
    S --> D{"Same actor or conflicting chain?"}
    D -->|Có| N["DENY / require independent reviewer"]
    D -->|Không| Y["Continue policy + workflow checks"]
~~~

Nếu mỗi ứng dụng chỉ xét role nội bộ, SoD xuyên quy trình có thể bị bỏ lọt. Cần:

1. **Activity catalog** chung ánh xạ các chức năng ở các ứng dụng.
2. **Stable subject identity** giữa IdP, SCIM target và ứng dụng, tránh ghép theo email.
3. **Correlation IDs/resource references** kết nối cùng giao dịch hoặc chuỗi nghiệp vụ.
4. **Audit/event integrity** cho actor của mỗi bước.
5. **Cross-system conflict detection** ở IGA hoặc domain coordinator và chặn tại điểm quyết định cuối.
6. **Propagation SLA** khi event/role thay đổi và khả năng chống event đến trễ.
7. **Phân biệt allow quyết định trong engine với enforcement tại mỗi PEP**.

### Event ordering và replay

Giả sử event Mover cũ cập nhật nhóm Creator **sau** event Leaver hoặc sau khi quyền đó đã được thu hồi. Cần revision/idempotency/current-state checks để không **hồi sinh conflict**. Quy tắc SoD nên được đánh giá lại khi target state khác desired state, không coi connector response thành công là kết quả cuối.

### Consistency gap

Khi IGA ghi role đã REVOKED nhưng ứng dụng vẫn giữ direct role hoặc cache ALLOW, **SoD conflict ở thực tế còn tồn tại**. Giải pháp gồm reconciliation, target readback, PEP probes và ưu tiên chặn các quyền critical theo SLA.

## 16. SoD với service accounts, workload và delegated operations

Service identities có thể dùng **client credentials, managed/workload identity, mTLS, API keys** hoặc trust federation. Chúng không nhất thiết có department, manager hay MFA tương tác như người dùng.

| Tình huống | Xung đột SoD tiềm ẩn | Kiểm soát phù hợp |
| --- | --- | --- |
| Một bot tạo và duyệt payment. | Không có người kiểm độc lập. | Tách service principals/permissions; transaction approval bởi actor khác theo policy. |
| CI bot tạo release và ký phê duyệt production. | Bỏ qua independent review. | Tách signing/approval authority khỏi build account. |
| Service có quyền sửa IAM policy và xóa audit. | Có thể tự che dấu thao tác. | Tách control-plane access và audit administration. |
| User có quyền assume cả Creator và Approver service identities. | Tách account trên giấy nhưng không độc lập thực tế. | Đánh giá trust/impersonation edges và human controller. |
| Connector có quyền grantRole và tự approve grant. | Tự cấp quyền cho mình. | Approval API riêng, connector chỉ apply approved delta. |
| Workload owner đã Leaver nhưng còn secret. | Chủ sở hữu cũ tiếp tục điều khiển hai bước. | Chuyển owner, revoke vault access, rotate credential khi cần. |

### Phân biệt số tài khoản với số người kiểm soát

Tách tác vụ ra **hai service accounts** không đảm bảo SoD nếu cùng một người hoặc hệ thống có thể sửa code, lấy secrets và điều khiển cả hai account. Cần đánh giá:

- Ai có quyền **impersonate/assumeRole** hai identities?
- Ai có thể **sửa pipeline/workflow** thực thi hai hành động?
- Có **approval độc lập** thực sự không?
- Có audit cho cả **technical actor** và **originating human/business requester** không?
- Credential được bảo vệ và có thể revoke/rotate theo chính sách không?

SoD thường đòi **sự độc lập về thẩm quyền và khả năng kiểm soát**, không chỉ sự khác biệt của hai username.

## 17. SoD trong RBAC/ABAC và ngữ cảnh tài nguyên

Một hệ thống hybrid có thể kết hợp:

~~~text
Role allows candidate action: PAYMENT_APPROVER
AND ABAC checks:
  subject.active == true
  subject.tenant == payment.tenant
  payment.status == PENDING_APPROVAL
  payment.amount <= subject.approvalLimit
  subject.id != payment.createdBy
  subject.id != payment.lastMaterialEditor
  requiredStepUpIsFresh == true
AND policy has no applicable non-waivable DENY.
~~~

Rule trên chỉ minh họa. **Mức giới hạn, sự kiện nào được xem là chỉnh sửa trọng yếu và thời hạn step-up** phải được owner nghiệp vụ xác định, không giả định chung.

### Attribute phải tin cậy

- **subject.id** từ identity/session đã xác minh, không từ body request.
- **payment.createdBy** và **lastMaterialEditor** từ backend dữ liệu có kiểm soát.
- **subject.tenant** và **payment.tenant** từ mapping đáng tin, không do client tùy ý chọn.
- **subject.approvalLimit** từ nguồn phân quyền được phê duyệt, có version/expiry.
- **time/authentication freshness** từ server và IdP/session contract, không dùng timestamp do browser tự khai.

**Missing attribute** không nên làm biến mất điều kiện SoD. Nếu createdBy hoặc trusted actor không xác định được đối với thao tác nhạy cảm, quyết định nên **DENY/INDETERMINATE rồi fail-safe theo policy**, thay vì coi hai người mặc nhiên khác nhau.

### SoD và dữ liệu đa tenant

Một rule có thể cấm người tạo và người duyệt trong **cùng tenant**, nhưng không cần chặn cùng hai role trên hai tenant độc lập nếu policy chỉ phạm vi đó. Ngược lại, người dùng có quyền chuyển tenant hoặc một global admin có thể vẫn thực hiện cả hai bước qua nhiều đường; review phải xét **effective cross-tenant permissions**.

### Conflict giữa các rules

Nếu RBAC permit approve nhưng SoD deny self-approval, **permit không được vượt qua SoD DENY** nếu chính sách xác định ràng buộc SoD là non-waivable. Policy engine phải thể hiện rõ **combining algorithm, precedence, NotApplicable/Indeterminate semantics**, và PEP cần thực thi đúng quyết định cuối.

## 18. Phân loại xung đột SoD và quyết định xử lý

Một hệ thống SoD có thể trả **conflict** nhưng không phải mọi tình huống đều cùng bản chất:

| Loại | Định nghĩa | Ví dụ | Hành động |
| --- | --- | --- | --- |
| **Actual assignment conflict** | Subject đang có tập grants trái SSD. | Gán Creator + Approver trong cùng scope. | Thu hồi/điều chỉnh quyền hoặc chặn activation. |
| **Potential conflict** | Yêu cầu sắp cấp sẽ tạo conflict. | Mover xin role mới khi role cũ chưa mất. | Block approval/provision hoặc revoke-before-grant. |
| **Transaction violation attempt** | Actor cố thực hiện action trái transaction SoD. | Duyệt payment do mình tạo. | DENY trước side effect; audit phù hợp. |
| **Confirmed transaction violation** | Hành động xung đột đã được thực thi. | Cùng actor tạo và duyệt payment đã chuyển trạng thái. | Incident, điều tra, kiểm soát hậu quả và khắc phục PEP. |
| **Policy mapping gap** | Role/permission mới chưa ánh xạ tới activity catalog. | Admin override bypass role Approver. | Bổ sung mapping, tests, review role definition. |
| **Data quality conflict** | Không thể quyết định vì actor/resource identity thiếu hoặc sai. | createdBy không có, account mapping mơ hồ. | Fail-safe, sửa nguồn, không khẳng định an toàn. |
| **Approved exception** | Conflict được cho phép theo quy trình đặc biệt có giới hạn. | Tổ chức nhỏ dùng dual control bù trừ. | Theo dõi scope/TTL, independent approval, evidence. |

### Trạng thái cần tách biệt

**DETECTED** không phải **REMEDIATED**. **REMEDIATION_APPLIED** không phải **VERIFIED**. Một quy tắc đạt chỉ khi kết quả ở IGA/target và hành vi API tương ứng **đã được kiểm chứng**.

## 19. Ngoại lệ SoD và kiểm soát bù trừ

Một số tổ chức nhỏ không có đủ người để tách hoàn toàn mọi nhiệm vụ. Có thể phải thiết kế **compensating controls**, nhưng ngoại lệ phải được giới hạn và được phê duyệt bởi authority phù hợp.

### Ví dụ kiểm soát bù trừ

| Nguy cơ | Kiểm soát bù trừ có thể cân nhắc | Giới hạn |
| --- | --- | --- |
| Không đủ người duyệt trực tiếp ở một chi nhánh. | Phê duyệt từ xa của owner độc lập. | Phải có người độc lập thật và kiểm tại API. |
| Một admin khẩn cần hai nhiệm vụ khi phục hồi. | Break-glass có thời hạn, dual control khi khả thi, session audit, hậu kiểm. | Không biến emergency role thành standing global admin. |
| User eligible cả Creator và Approver. | JIT activation tách thời điểm, độc lập approval, transaction self-check. | Chỉ tách phiên không đủ chặn self-approval. |
| Quy trình legacy không có SoD API. | Giới hạn role, manual independent reconciliation, alerts và lộ trình nâng cấp. | Manual review sau sự kiện không tương đương phòng ngừa. |
| Automation cần chuẩn bị một lệnh thanh toán. | Bot tạo, một người độc lập xác nhận/duyệt trên PEP. | Người kiểm soát bot không nên tự vượt bước duyệt. |

### Hồ sơ ngoại lệ tối thiểu

~~~yaml
exceptionId: sod-exc-2026-031
ruleId: SOD-PAYMENT-CREATOR-APPROVER
status: REQUESTED
beneficiaryRef: person-4821
applicationId: finance-portal
tenantId: tenant-vn
activities: [payment.create, payment.approve]
scope: emergency-recovery-only
reason: Xu ly su co duoc duyet
validFrom: "2026-11-23T03:00:00Z"
validUntil: "2026-11-23T04:00:00Z"
approverRefs: [finance-process-owner, security-duty-owner]
compensatingControls:
  - independent_post_action_review
  - privileged_session_recording
  - tight_transaction_limit
revokeProof: PENDING
~~~

Đây là schema **minh họa**. Ngoại lệ chỉ có thể được chấp nhận nếu **policy cho phép waive rule cụ thể**. Nếu rule tự duyệt bị xác định là **non-waivable**, không tạo exception để vòng qua; phải thay đổi quy trình để có reviewer độc lập.

### Trách nhiệm phê duyệt

- **Business process owner** xác nhận nhu cầu và hậu quả nghiệp vụ.
- **Security/SoD owner** đánh giá rủi ro xung đột và hiệu quả kiểm soát.
- **Application owner** xác nhận target thực sự hỗ trợ scope/time-bound enforcement.
- **Independent reviewer** không phải beneficiary hay người đã thực hiện các bước xung đột.
- **Auditor** xác minh bằng chứng và theo dõi ngoại lệ; không tự trở thành approver duy nhất khi thiếu authority.

### Hết hạn ngoại lệ

Sau validUntil, connector/PAM/PEP phải thực sự thu hồi hoặc chặn quyền ngoại lệ. Kiểm cả **token/session cũ, direct ACL, API key và background jobs** liên quan theo policy. Ticket hiển thị EXPIRED **không chứng minh** quyền hiệu lực đã hết.

## 20. Phân tích rủi ro quy tắc SoD và ưu tiên khắc phục

Một rule SoD cần gắn với **mục đích kiểm soát**, tác động nếu vi phạm và phạm vi business process:

1. **Fraud potential:** actor có thể tự chuyển tiền, đổi người thụ hưởng hoặc chiếm account không?
2. **Data impact:** actor có thể tự cấp quyền rồi export dữ liệu nhạy cảm không?
3. **Control-plane power:** actor có thể sửa cả policy và audit, tạo đường ẩn đặc quyền?
4. **Blast radius:** ảnh hưởng một payment, một tenant hay toàn doanh nghiệp?
5. **Exploitability:** dùng từ Internet, secret dài hạn, thiếu độc lập approval hay không?
6. **Time/propagation:** conflict xuất hiện trong bao lâu sau Mover hoặc JIT activation?
7. **Compensating controls:** có được triển khai thực tế, có kiểm được hiệu quả?
8. **Detection capability:** log có đủ actor history, correlation và transaction IDs không?

Không có công thức cộng điểm nào tự quyết tất cả quy tắc. Với **hard SoD prohibition**, không được lấy những yếu tố ít rủi ro khác để bù một conflict bị cấm. Nếu dùng risk tier, phải công bố model, owner, rule version và điều kiện escalation.

### Trình tự ưu tiên gợi ý

| Mức độ | Ví dụ | Phản ứng |
| --- | --- | --- |
| **Critical** | Tự tạo–tự duyệt–tự thực hiện thanh toán; tự cấp global admin và xóa audit. | Chặn ngay theo quy trình được duyệt; incident/security review. |
| **High** | Mover giữ quyền admin cũ và được cấp role xung đột mới. | Revoke/chặn activation, xác minh target theo SLA ngắn. |
| **Medium** | Role catalog thiếu mapping SoD nhưng chưa có giao dịch xung đột được xác nhận. | Điều tra nhanh, cập nhật policy/tests, hạn chế cấp mới. |
| **Low/Informational** | Permission có tên tương tự nhưng phạm vi dự án hoàn toàn tách biệt. | Xác minh scope, giảm false positive và lưu quyết định. |

**Một conflict chưa được xác minh** phải mang trạng thái **POTENTIAL/UNVERIFIED**, không bị xóa khỏi báo cáo và cũng không tự xem là gian lận đã xảy ra.

## 21. Quy tắc SoD như policy-as-code (OPA/Rego)

Ví dụ minh họa một rule ngăn user tự duyệt payment. Rego sau dùng cú pháp dành cho **OPA/Rego v1** và giả định input đã được tạo **bởi backend từ nguồn đáng tin**:

~~~rego
package finance.payment

import rego.v1

default allow := false

sod_conflict if {
    input.subject.id == input.payment.createdBySubjectId
}

sod_conflict if {
    input.subject.id == input.payment.lastMaterialEditorSubjectId
}

allow if {
    input.action == "payment.approve"
    input.subject.active == true
    "PAYMENT_APPROVER" in input.subject.roles
    input.subject.tenantId == input.payment.tenantId
    input.payment.status == "PENDING_APPROVAL"
    input.payment.amount <= input.subject.approvalLimit
    input.context.stepUpSatisfied == true
    not sod_conflict
}
~~~

### Input kiểm thử

~~~json
{
  "action": "payment.approve",
  "subject": {
    "id": "person-a",
    "active": true,
    "tenantId": "tenant-vn",
    "roles": ["PAYMENT_APPROVER"],
    "approvalLimit": 10000000
  },
  "payment": {
    "id": "pay-201",
    "tenantId": "tenant-vn",
    "createdBySubjectId": "person-a",
    "lastMaterialEditorSubjectId": "person-b",
    "amount": 3000000,
    "status": "PENDING_APPROVAL"
  },
  "context": {
    "stepUpSatisfied": true
  }
}
~~~

Kết quả mong đợi: **allow=false** vì actor trùng createdBy, dù role, tenant, hạn mức và step-up đều hợp lệ. Đổi subject.id thành một approver độc lập (và bảo đảm actor đó không phải lastMaterialEditor) thì request **có thể** được phép khi tất cả điều kiện khác đạt.

### Giới hạn của ví dụ

- Rule chưa xét **người thay đổi tài khoản thụ hưởng trong lịch sử**, approval chain nhiều cấp hoặc override khẩn.
- Không tự giải quyền qua **nested groups/role hierarchy**; input roles phải do backend/tầng IAM giải nghĩa đúng.
- Không kiểm khả năng **TOCTOU** của database khi duyệt; PEP/transaction service phải đảm bảo state và actor history được kiểm nhất quán.
- OPA không tự provision role hoặc revoke JWT, cũng không tự ghi audit bảo đảm đầy đủ nếu PEP không tích hợp.
- Nếu input payment được client tự khai, một client ác ý có thể sửa createdBy để vượt rule. Chỉ dùng **trusted resource state**.

### Tách assignment rule khỏi transaction rule

Một SSD rule ở IGA cần đánh giá **effective activities sẽ có sau khi cấp grant**. Không dùng mỗi policy Rego approve endpoint ở trên làm bằng chứng rằng **quy tắc SSD tại cấp quyền** đã được kiểm.

## 22. Java: ví dụ kiểm SSD từ effective business activities

Mô hình đơn giản sau xem một tập business activities trên **cùng scope**, nhằm minh họa cách kiểm cặp xung đột. Trong thực tế, resolver cần giải nghĩa role inheritance, ABAC conditions, delegated grants, tenant và thời gian:

~~~java
import java.util.Set;

record SoDPair(String activityA, String activityB) {
    boolean conflictsWith(Set<String> activities) {
        return activities.contains(activityA)
            && activities.contains(activityB);
    }
}

final class SoDAssignmentPolicy {
    private static final Set<SoDPair> FORBIDDEN_PAIRS = Set.of(
        new SoDPair("payment.create", "payment.approve"),
        new SoDPair("supplier.create", "supplier.approve")
    );

    boolean mayAssign(Set<String> proposedEffectiveActivities) {
        if (proposedEffectiveActivities == null) {
            return false; // Không đánh giá được => không cho qua.
        }
        return FORBIDDEN_PAIRS.stream()
            .noneMatch(p -> p.conflictsWith(proposedEffectiveActivities));
    }
}
~~~

Unit test minh họa:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Set;

class SoDAssignmentPolicyTest {
    private final SoDAssignmentPolicy policy = new SoDAssignmentPolicy();

    @Test
    void rejectsCreatorAndApproverInSameScope() {
        assertFalse(policy.mayAssign(
            Set.of("payment.create", "payment.approve")));
    }

    @Test
    void acceptsIndependentReadOnlyActivity() {
        assertTrue(policy.mayAssign(
            Set.of("invoice.read", "payment.create")));
    }

    @Test
    void failsSafeWhenEffectiveActivitiesUnknown() {
        assertFalse(policy.mayAssign(null));
    }
}
~~~

**Quan trọng:** code trên **không thực thi scope**. Nó giả định đầu vào đã được resolver lọc cho **cùng tenant/project và thời điểm**. Nếu lấy union activities trên toàn doanh nghiệp, có thể **false positive** khi hai role ở hai môi trường không liên quan. Nếu không giải được wildcard hoặc admin override, có thể **false negative**.

## 23. Java pseudocode: chặn tự duyệt giao dịch

Đối với giao dịch cần **transaction-level SoD**, một phương thức backend có thể theo luồng sau:

~~~java
// Pseudocode minh họa, phụ thuộc transaction manager và domain model.
ApprovalOutcome approvePayment(String paymentId, TrustedPrincipal actor) {
    if (actor == null || !actor.isAuthenticated()) {
        return ApprovalOutcome.denied("UNAUTHENTICATED");
    }

    return paymentRepository.inTransaction(() -> {
        Payment payment = paymentRepository.loadForUpdate(paymentId);

        if (payment == null
                || !payment.isPendingApproval()
                || !actor.isActive()
                || !actor.tenantId().equals(payment.tenantId())) {
            return ApprovalOutcome.denied("INELIGIBLE_CONTEXT");
        }

        // createdBy/lastMaterialEditor lấy từ storage đáng tin.
        if (actor.subjectId().equals(payment.createdBySubjectId())
                || actor.subjectId().equals(
                    payment.lastMaterialEditorSubjectId())) {
            audit.recordDenied(actor.subjectId(), payment.id(),
                "SOD-SELF-APPROVAL");
            return ApprovalOutcome.denied("SOD_CONFLICT");
        }

        // Đánh giá quyền hiện hành và policy tại thời điểm thay đổi.
        if (!authorization.canApprove(actor, payment)
                || !sessionPolicy.stepUpFreshEnough(actor)) {
            return ApprovalOutcome.denied("NOT_AUTHORIZED");
        }

        payment.approveBy(actor.subjectId());
        paymentRepository.saveWithVersionCheck(payment);
        outbox.recordPaymentApproved(payment.id(), actor.subjectId());
        return ApprovalOutcome.approved();
    });
}
~~~

### Những điều phải bổ sung trong production

1. **Nguồn actor:** trusted security context; không nhận ID người duyệt từ client.
2. **History integrity:** không cho user sửa createdBy/lastMaterialEditor để “xóa” SoD.
3. **Transaction consistency:** state/role change/concurrent approve cần isolation hoặc version checks phù hợp.
4. **No side effects on DENY:** không ghi thanh toán, tạo file/job hoặc phát message nếu bị chặn.
5. **Idempotent retries:** yêu cầu trùng không dẫn tới double approval.
6. **Delegated action:** ghi cả originating human actor và service executor nếu quy trình dùng workload.
7. **Audit:** version rule, correlation, reason code, không ghi bearer token hoặc secret.
8. **SoD cross-step:** nếu rule cấm người đã chỉnh người thụ hưởng, cần dùng lịch sử sửa đầy đủ theo thiết kế, không chỉ một trường tùy ý.

**Pseudocode không thay thế kiểm thử integration với database/API thực**, vì unit test logic có thể PASS nhưng endpoint khác, async consumer hoặc bulk approval vẫn bỏ qua PEP.

## 24. SQL minh họa: phát hiện ứng viên xung đột SSD

Giả sử ứng dụng quản trị có bảng snapshot:

- **effective_activity_snapshot**: các business activities mà một subject có thể thực hiện trong một scope, sau khi role/ACL được phân giải.
- **sod_conflict_pair**: các cặp hoạt động cấm, có ruleId/version và tenant scope.

Đây là mô hình SQL **minh họa**, không phải schema SQL chuẩn của directory/IGA. Mục tiêu là phát hiện **ứng viên** cùng giữ hai business activities xung đột trong một snapshot đã chuẩn hóa:

~~~sql
SELECT
    a.measurement_id,
    a.subject_id,
    a.application_id,
    a.tenant_id,
    a.scope_id,
    r.rule_id,
    r.activity_a,
    r.activity_b
FROM effective_activity_snapshot a
JOIN sod_conflict_pair r
  ON a.activity_id = r.activity_a
JOIN effective_activity_snapshot b
  ON b.measurement_id = a.measurement_id
 AND b.subject_id = a.subject_id
 AND b.application_id = a.application_id
 AND b.tenant_id = a.tenant_id
 AND b.scope_id = a.scope_id
 AND b.activity_id = r.activity_b
WHERE a.measurement_id = :measurement_id
  AND a.is_effective = TRUE
  AND b.is_effective = TRUE
  AND r.rule_type = 'SSD'
  AND r.is_active = TRUE;
~~~

### Diễn giải kết quả

- Một dòng kết quả cho thấy **trong cùng snapshot/scope**, subject có hai activities thuộc cặp SSD cấm.
- Nó **không chứng minh** chủ thể đã tự duyệt một giao dịch. Với transaction-level SoD, cần đối chiếu actor history của **từng payment**.
- Nếu policy là **DSD session-level**, phải xét roles **được kích hoạt đồng thời**, không dùng mọi role eligible để kết luận vi phạm thực.
- Nếu các hoạt động ở **hai hệ thống khác nhau**, SQL có thể cần business-process correlation thay vì application_id bằng nhau.
- Nếu role hierarchy, conditional ABAC hoặc delegated grants chưa được resolver xử lý, kết quả có thể thiếu hoặc sai.
- Một application không cung cấp snapshot phải được ghi **UNVERIFIED**, không coi là không có conflict.

### SQL kiểm dấu hiệu tự duyệt giao dịch

Nếu bảng nghiệp vụ có actor được xác minh, một báo cáo **detective** có thể trích các giao dịch đáng điều tra:

~~~sql
-- Minh họa, phải có integrity cho trường actor và transaction state.
SELECT
    p.payment_id,
    p.tenant_id,
    p.created_by_subject_id,
    p.approved_by_subject_id,
    p.approved_at
FROM payment_audit_view p
WHERE p.status = 'APPROVED'
  AND p.approved_by_subject_id IS NOT NULL
  AND p.approved_by_subject_id = p.created_by_subject_id;
~~~

Truy vấn này không thay thế **chặn trước commit**. Nếu ứng dụng có bước sửa vật chất hoặc delegation, cần các phép so phù hợp với rule nghiệp vụ, không chỉ một cặp createdBy/approvedBy.

## 25. Thiết kế ma trận kiểm thử quy tắc SoD

Kiểm thử SoD phải có **positive controls, negative tests, boundary conditions và trạng thái JML**. Kiểm ở cả **chính sách cấp quyền**, **PAM/DSD activation** và **API giao dịch**.

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| S01 | User chỉ có PaymentCreator trong scope A. | Grant hợp lệ; không false conflict. |
| S02 | User xin PaymentApprover khi có Creator, SSD cấm cùng scope. | BLOCK trước provisioning. |
| S03 | User có Approver và Creator trong hai tenant độc lập, rule chỉ cấm cùng tenant. | Không false positive do nhầm scope. |
| S04 | Role FinanceAdmin kế thừa payment.approve, user có Creator. | Resolver phát hiện effective conflict. |
| S05 | Approver tới từ nested group hai tầng. | SSD phát hiện, không chỉ check direct group. |
| S06 | Một ACL direct cấp approve dù role Approver đã gỡ. | Conflict vẫn được phát hiện từ effective access. |
| S07 | User eligible Creator và Approver, policy DSD chỉ cấm đồng kích hoạt. | Eligibility được phân biệt với activation. |
| S08 | User cố kích hoạt hai role xung đột cùng lúc. | DSD deny activation thứ hai. |
| S09 | User ngừng Creator rồi kích hoạt Approver và duyệt payment do mình tạo. | Transaction-level SoD vẫn DENY. |
| S10 | Approver duyệt payment do actor độc lập tạo, role/tenant/state hợp lệ. | ALLOW; positive control. |
| S11 | Approver duyệt chính payment họ tạo. | DENY trước side effect. |
| S12 | Approver sửa người thụ hưởng rồi tự duyệt cùng payment. | DENY theo rule material editor. |
| S13 | Approver đã role nhưng payment ở tenant khác. | DENY tenant isolation. |
| S14 | Approver đã role nhưng payment không PENDING. | DENY state guard. |
| S15 | Actor được user gửi tùy ý trong body khác security principal. | Server không tin giá trị giả mạo. |
| S16 | Backend thiếu createdBy trên payment nhạy cảm. | DENY/fail-safe, không mặc định người tạo khác approver. |
| S17 | Role catalog thêm approve vào Viewer. | Policy mapping drift được phát hiện/review. |
| S18 | Endpoint approve chính có PEP, bulk approve thì không. | Integration/security regression bắt bypass. |
| S19 | API trả HTTP 403 sau khi ghi APPROVED. | FAIL no-side-effect invariant. |
| S20 | API trả 503 do database down. | Không tính là SoD DENY đúng; test phải phân loại outage. |
| S21 | Mover được cấp Approver trong khi Creator cũ còn qua CRM ACL. | Revoke-before-grant/chặn activation theo policy. |
| S22 | SCIM báo role Creator đã gỡ nhưng API vẫn ALLOW. | Chưa VERIFIED, cần remediation. |
| S23 | JWT trước Mover còn claim Creator. | Kiểm revoke/current state theo SLA tại PEP. |
| S24 | Leaver có request Approver được approve trước đó, nay provision trễ. | Lifecycle revalidation BLOCK. |
| S25 | Event Mover cũ đến sau Leaver. | Không tái cấp quyền xung đột. |
| S26 | Rehire trùng email với account cũ. | Identity link xác minh, không tự khôi phục role lịch sử. |
| S27 | Contract expiry đã qua nhưng role vẫn active. | Revoke/verify, không giữ theo approval cũ. |
| S28 | Requester tự duyệt access request của chính mình. | Backend approval API từ chối. |
| S29 | Người provision sửa entitlement sau khi owner ký. | Snapshot/digest mismatch, không apply scope sai. |
| S30 | Người sửa SoD policy tự phê duyệt chính policy change. | Independent governance control. |
| S31 | Break-glass activation có hạn và audit đầy đủ. | Chỉ cho theo quy trình khẩn được duyệt. |
| S32 | Ngoại lệ SoD đã hết hạn nhưng API vẫn ALLOW. | FAIL, revoke và verified DENY. |
| S33 | Rule non-waivable bị gắn ngoại lệ do manager tự tạo. | DENY, không cho bypass hard policy. |
| S34 | CI bot tạo và duyệt release bằng cùng principal. | Detect/deny theo SoD của release. |
| S35 | Hai service accounts khác nhau nhưng cùng user có quyền impersonate cả hai. | Đánh giá effective controller, không coi tách username là đủ. |
| S36 | Production service token có audience staging. | Token verifier DENY; không mở quyền vì service trusted ở nơi khác. |
| S37 | PDP timeout tại approve endpoint. | Fail-safe theo policy, không default ALLOW. |
| S38 | Hai requests cùng approve payment đồng thời. | Không double-approve, race/TOCTOU được kiểm. |
| S39 | Hai vùng chạy hai phiên bản SoD policy khác nhau. | Detect drift và xử lý theo rollout/incident. |
| S40 | Đã gỡ direct role nhưng nested grant vẫn cho effective approve. | Không đóng remediation cho tới khi PEP DENY đúng. |

### Oracle kiểm thử: xác định đúng/sai từ đâu?

**Expected decision** phải lấy từ **business rule được duyệt, SoD matrix và current lifecycle policy**, không dùng chính hàm production đang được test làm oracle. Nếu hàm production thiếu check self-approval, bộ test copy cùng logic sẽ tạo **false confidence**.

### Các mức kiểm thử

| Mức | Cần chứng minh |
| --- | --- |
| **Policy unit test** | Conflict pair, precedence, missing data, scope, expiry. |
| **Role resolver test** | Hierarchy, nested groups, ACL, privilege delegation, wildcard. |
| **IGA integration test** | Approval route, immutable snapshot, revalidation trước grant. |
| **PAM/DSD test** | Eligible vs active roles, activation/expiry, step-up. |
| **Application API test** | Transaction self-check, tenant, resource state, no side effects. |
| **JML E2E test** | Mover/Leaver role updates, token/session, SCIM, target readback. |
| **Fault/chaos test** | PDP/PIP timeout, cache stale, connector partial failure, event đảo thứ tự. |
| **Audit/reconciliation test** | Violation detection, log completeness, escalation, verified remediation. |

**Chỉ kiểm giao diện ẩn nút Approve là không đủ**. Backend/API phải từ chối chủ thể không đủ quyền, kể cả request trực tiếp, job chạy nền hoặc một endpoint khác có cùng activity.

## 26. Tình huống thực hành: Mover từ Payment Operations sang Control

### Bối cảnh

Doanh nghiệp có Finance Portal và ERP kết nối với IdP/SSO và SCIM. Nhân viên **Mai** đang làm Payment Operations, có quyền tạo payment và sửa thông tin nhà cung cấp. Mai được điều chuyển sang Payment Control từ 09:00 để làm Approver. Chính sách tổ chức áp:

- **SSD** cấm cùng chủ thể có effective Creator và Approver trong **cùng tenant VN**.
- **Transaction-level SoD** cấm approver duyệt payment họ từng tạo hoặc chỉnh sửa trọng yếu.
- **SoD approval** cấm Mai tự duyệt access request cấp Approver.

### Bước 1 — Tính desired state

~~~text
Before 09:00:
  payment.create = ALLOW
  payment.approve = DENY
  supplier.edit = ALLOW

Desired after 09:00:
  payment.create = DENY
  supplier.edit = DENY nếu không còn nhiệm vụ
  payment.approve = ALLOW
    chỉ với payment của người khác, đúng tenant/state/limit
~~~

### Bước 2 — SoD preflight

IGA phát hiện Mai còn:

| Grant | Nguồn | Actual | Xử lý |
| --- | --- | --- | --- |
| PAYMENT_CREATOR | IdP group qua SCIM. | ACTIVE. | Revoke và readback. |
| PAYMENT_CREATOR_OVERRIDE | Direct role trong ERP. | ACTIVE. | Revoke tại app, không chỉ gỡ IdP group. |
| SUPPLIER_EDITOR | App-local ACL. | ACTIVE. | Xác định SoD/business need rồi xử lý. |
| PAYMENT_APPROVER | Access request được manager chấp nhận. | NOT YET ACTIVE. | Không activate cho tới khi SSD gate đạt. |

**Cần chặn activation Approver** khi Creator còn effective trong ERP. Một approval từ manager không bù được SSD rule cấm.

### Bước 3 — Revoke và xác minh

1. Gỡ nhóm Creator tại IdP/SCIM.
2. Gỡ direct role Creator tại ERP và ACL SupplierEditor không còn cần.
3. Readback đúng target account IDs/tenant, kiểm phiên/token cũ theo cơ chế hỗ trợ.
4. Dùng probe không phá hoại xác nhận **payment.create DENY** ở các PEP bắt buộc.
5. Ghi timestamp khi VERIFIED, không dùng thời điểm connector trả 200/204.

### Bước 4 — Cấp Approver và giữ transaction-level rule

Chỉ khi SSD không còn conflict mới provision Approver đúng scope. Mai có thể duyệt payment do **An** tạo nếu dữ liệu thử thỏa các điều kiện, nhưng phải DENY payment do **Mai** tạo trước Mover. Đây là chỗ **SSD và transaction-level rule bổ sung nhau**: gỡ Creator từ hiện tại **không xóa sự thật Mai đã là creator của payment lịch sử**.

### Bước 5 — Thử các đường xung đột

| Probe | Kỳ vọng |
| --- | --- |
| Mai tạo payment mới với token trước Mover. | DENY theo SLA. |
| Mai duyệt payment do chính Mai tạo trước Mover. | DENY vì createdBy còn là Mai. |
| Mai duyệt payment do An tạo cùng tenant, đúng trạng thái. | ALLOW khi đủ điều kiện. |
| Mai duyệt payment tenant SG. | DENY, dù role Approver hợp lệ ở VN. |
| Mai dùng admin endpoint để tự gán lại Creator. | DENY nếu không có authority và SoD gate. |
| Bot do Mai kiểm soát gọi API create sau Mover. | Kiểm delegated/workload access; không tự coi khác actor. |
| Event cũ gán Creator đến sau revoke. | Không regrant nhờ revision/reconciliation. |

### Bước 6 — Đóng hồ sơ

Audit lưu **policy version, expected decisions, target IDs, role mapping, reviewer/approval, revoke/activate timestamps, test evidence và các ngoại lệ**. Chỉ đánh dấu VERIFIED khi các kênh cấp quyền bắt buộc đã đúng và cả positive/negative probes đạt.

**Bài học:** SoD phải bảo vệ **khả năng được cấp** và **cách quyền được sử dụng**. Một Mover đã mất role Creator vẫn **không được tự duyệt giao dịch từng tạo**; và một user được manager duyệt Approver vẫn không được activate khi Creator còn effective.

## 27. Quản trị thay đổi quy tắc SoD

SoD rule không phải cấu hình bất biến. Nó cần được quản trị như **policy có phiên bản và có người chịu trách nhiệm**, vì chức năng ứng dụng, role definitions và quy trình nghiệp vụ thay đổi liên tục.

### Quy trình thay đổi an toàn

~~~mermaid
flowchart TD
    A["Business process hoặc role catalog thay đổi"] --> B["Đề xuất SoD rule / mapping version mới"]
    B --> C["Business & security risk review"]
    C --> D["Conflict matrix + allow/deny test cases"]
    D --> E["Policy simulation / staging integration tests"]
    E --> F{"Đạt positive và negative tests?"}
    F -->|Không| R["Sửa rule, mapping hoặc workflow"]
    R --> D
    F -->|Có| G["Independent approval"]
    G --> H["Canary / policy rollout có kiểm soát"]
    H --> I["PEP/IGA readback + production-safe probes"]
    I --> J{"Version và quyết định khớp?"}
    J -->|Không| K["Containment / rollback có kiểm soát"]
    J -->|Có| L["Audit + monitor drift và false deny"]
~~~

### Kiểm soát thay đổi bắt buộc

1. **Rule ID/version cố định** và mô tả business conflict.
2. **Business owner** xác nhận tác vụ nào thực sự xung đột.
3. **Security/SoD owner** xác định hard DENY, khả năng exception và xử lý conflict.
4. **Permission mapping version** cập nhật khi role được thêm action, kế thừa role hoặc có API mới.
5. **Test oracle độc lập**, gồm positive, negative, scope boundaries và JML.
6. **Separation of duties trong deploy**: người viết rule không tự động là người duy nhất phê duyệt/deploy/xác nhận.
7. **Canary và rollback** xem xét khả năng tái mở một lỗ hổng cũ.
8. **Actual deployed version** được đọc lại tại IGA/PDP/PEP, không chỉ nhìn Git.
9. **Audit/metrics** cho false allow, false deny, conflict backlog và propagation.

### Cảnh báo về shadow evaluation

Một rule chạy **shadow mode** có thể phát hiện “would DENY” nhưng chưa chặn giao dịch. Dữ liệu shadow phù hợp để đánh giá ảnh hưởng trước deploy, **không phải bằng chứng quy tắc đã được thực thi**. Sau triển khai cần kiểm PEP và kiểm giao dịch trong phạm vi cho phép.

### Không rollback về chính sách kém an toàn vô điều kiện

Khi SoD mới đang chặn self-approval, một rollback đơn giản về bản policy cũ có thể **mở lại đường tự duyệt**. Phương án rollback cần bảo đảm tiếp tục kiểm soát rủi ro bằng feature gate, rule tối thiểu hoặc biện pháp bảo vệ tương đương được duyệt.

## 28. Audit, chỉ số và bằng chứng thực thi SoD

Audit SoD cần giúp trả lời **ai có thể làm gì, policy nào áp dụng, quyết định ở đâu, giao dịch đã ghi gì, và quyền đã được thu hồi thực sự chưa**.

~~~yaml
eventType: SOD_DECISION
correlationId: req-2026-4821
policyRuleId: SOD-PAYMENT-SELF-APPROVE
policyRuleVersion: 3
subjectRef: person-4821
application: finance-portal
action: payment.approve
resourceRef: pay-201
tenantRef: tenant-vn
decision: DENY
reasonCode: SOD_SELF_APPROVAL
enforcementPoint: finance-api-approval
observedAt: "2026-11-23T03:12:00Z"
sideEffectsCommitted: false
~~~

Ví dụ trên chỉ minh họa schema. IDs và actor history cũng có thể là dữ liệu cá nhân; cần hạn chế quyền xem, thời gian lưu và data minimization. **Không lưu access token, refresh token, mật khẩu, private key, secret hoặc toàn bộ payload nhạy cảm**.

### Những loại evidence cần lưu

| Evidence | Mục đích |
| --- | --- |
| SoD rule ID/version + business owner | Chứng minh rule nào có hiệu lực và vì sao. |
| Role-to-activity catalog version | Biết conflict resolver đã phân giải quyền nào. |
| Current HRIS/IGA state revision | Liên kết đúng JML và mốc thời gian. |
| Stable subject/target identity mapping | Không gộp nhầm user hoặc workload. |
| Access request/approved snapshot | Biết điều gì được duyệt, bởi ai, trên scope nào. |
| Policy decision tại IGA/PDP | Biết expected allow/deny theo rule. |
| PEP/API response và no-side-effect check | Chứng minh enforcement thật. |
| Target role/group/ACL readback | Chứng minh revoke/grant đã áp tại hệ thống đích. |
| Event/transaction actor history | Phát hiện self-approval, impersonation và chain xung đột. |
| Exception/compensation/expiry | Phân biệt vi phạm trái phép và ngoại lệ được kiểm soát. |
| Incident/remediation verifiedAt | Biết tình trạng xử lý và độ trễ thu hồi. |

### KPI có ích

| KPI | Cách hiểu | Không nên nhầm với |
| --- | --- | --- |
| **SSD conflict count** | Số subject–scope có bộ entitlement xung đột đã xác minh. | Tổng số role trong directory. |
| **Potential conflict requests blocked** | Số yêu cầu gây conflict bị chặn trước cấp. | Số giao dịch gian lận đã xảy ra. |
| **Transaction SoD denied events** | Số yêu cầu bị từ chối theo SoD ở PEP. | Vi phạm thành công; một số denial có thể là lỗi người dùng. |
| **Confirmed SoD violations** | Giao dịch xung đột thực sự được commit, có evidence. | Những request chỉ bị deny. |
| **SoD remediation verification rate** | Xung đột đã xử lý và kiểm chứng tại target. | Số ticket đã được mark resolved thủ công. |
| **Mover overlap duration** | Thời gian hai hoạt động SSD cấm cùng có hiệu lực sau Mover. | Thời gian tới SCIM response. |
| **Unreviewed exception count** | Ngoại lệ thiếu owner/approval hoặc quá hạn. | Số ngoại lệ hợp lệ có hạn. |
| **Policy mapping coverage** | Activities/roles/endpoints quan trọng được ánh xạ và test. | Phần trăm dòng code được cover. |
| **Cross-system detection coverage** | Số luồng nghiệp vụ nhiều ứng dụng có correlation/SoD check. | Chỉ số coverage của một app. |
| **False denial impact** | Tác vụ hợp lệ bị chặn vì rule/scope sai. | Chỉ số SoD ngăn được gian lận. |
| **Critical unverified paths** | Đường API/worker/token không thể xác minh enforcement. | Zero conflicts; không có dữ liệu không phải an toàn. |

### Đừng xếp hạng thành công chỉ bằng số lượt DENY

Một hệ thống luôn trả DENY có thể chặn mọi giao dịch nhưng không phục vụ nghiệp vụ. Cần đánh giá **positive authorized workflow vẫn chạy**, các đường **xung đột bị từ chối** và các trường hợp **chưa đủ bằng chứng**.

## 29. Các sai lầm thường gặp khi viết hoặc áp dụng quy tắc SoD

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ cấm hai tên role. | Bỏ sót admin override, nested groups, ACL và role inheritance. | Rule gắn business activities, resolver tính effective access. |
| Nhầm SSD với transaction-level SoD. | User logout/chuyển role rồi tự duyệt giao dịch cũ. | Kiểm actor history tại resource, không chỉ session roles. |
| Coi MFA là thay thế SoD. | Người xác thực mạnh vẫn tự tạo–tự duyệt. | Tách độc lập actor/approval và kiểm transaction. |
| Chỉ chặn nút Approve trong UI. | Gọi backend trực tiếp vẫn thực thi. | PEP authorization và integration tests. |
| Chỉ kiểm khi xin role, không kiểm trước provision. | Quyền thay đổi tạo conflict sau approval. | Revalidation với HR/IGA current state và revision. |
| Coi SCIM/IdP success là conflict đã mất. | Local roles/cache/token vẫn ALLOW. | Readback và effective access probes tại target. |
| Chỉ kiểm direct role. | Nested group hoặc direct ACL vẫn cho action. | Giải toàn bộ nguồn grant relevant. |
| Không xét đối tượng/tài nguyên của giao dịch. | Chặn sai những người làm việc ở dự án độc lập hoặc bỏ lọt self-approval. | Scope đúng tenant/resource/actor history. |
| Dùng actorId do client tự gửi. | Có thể giả mạo người duyệt khác. | Actor từ verified principal; provenance bất biến. |
| Rule không xử lý missing createdBy. | Null được coi là “khác”, mở self-approval. | Fail-safe khi thuộc tính quan trọng thiếu. |
| Không xét người sửa giao dịch trọng yếu. | Actor sửa người thụ hưởng rồi tự duyệt. | Rule phù hợp với material edit history. |
| Hai service accounts khác tên coi là độc lập. | Một người vẫn điều khiển cả hai qua secrets/trust. | Kiểm effective controllers và delegation. |
| Ngoại lệ không expiry/owner. | Quyền khẩn trở thành quyền thường trực. | TTL, approval độc lập, compensation và verified revoke. |
| Cho phép risk score bù hard SoD. | Rule cấm bị bypass bởi điểm trung bình. | Hard gates trước scoring và policy precedence rõ. |
| Không kiểm concurrency. | Hai giao dịch/phê duyệt đi qua race window. | Transaction/version guards và tests. |
| Đánh dấu remediation thành công khi connector trả 204. | Vi phạm vẫn xảy ra tại PEP. | Verify DENY/no side effect và target readback. |
| Coi HTTP 503 là deny đúng policy. | Sự cố hạ tầng bị lẫn với kiểm soát SoD. | Positive controls và reason-code evidence. |
| Không cập nhật mapping khi role thay đổi. | Policy bảo vệ tên role cũ, bỏ qua permission mới. | Versioned entitlement catalog và change gates. |
| Dùng email làm stable identity. | Có thể map sai khi rehire hoặc nhiều tenant. | Stable subject ID và verified target mapping. |
| Bỏ qua Mover/Leaver khi điều tra conflict. | Quyền cũ tồn dư làm sai hoặc hồi sinh conflict. | Event-driven reconciliation và measured latency. |
| Chỉ nhìn số vi phạm, không nhìn coverage. | False confidence vì legacy/async paths chưa đo. | Hiển thị UNVERIFIED và risk-based coverage. |

## 30. Checklist nghiệm thu một bộ quy tắc SoD

1. **Business purpose rõ:** mỗi rule giải thích rủi ro thực, owner và hệ thống áp dụng.
2. **Rule identity/version:** ID, version, policy precedence và change approval đã được lưu.
3. **Activity mapping:** mọi role, inherited/nested group, ACL, admin override và delegated capability quan trọng được bao phủ.
4. **Loại constraint đúng:** SSD, DSD, transaction-level, approval SoD hoặc detective rule được phân biệt rõ.
5. **Scope đúng:** tenant, project, resource, environment, thời gian và actor history được định nghĩa.
6. **Trusted identity:** subject ID ổn định và mapping HRIS/IdP/SCIM/target đáng tin.
7. **Trusted resource:** createdBy, last editor, transaction state và hạn mức đến từ backend, không từ input không tin cậy.
8. **Assignment gate:** access request/provisioning đánh giá SoD dựa trên effective rights sau grant dự kiến.
9. **Activation gate:** PAM/DSD hạn chế các role active và TTL đúng policy.
10. **Runtime enforcement:** mọi API/bulk/async/commit path quan trọng gọi PEP và chặn self-approval.
11. **Concurrency:** không có TOCTOU/double approval/partial transaction bypass.
12. **JML:** Joiner baseline, Mover overlap, Leaver revoke, rehire và contractor expiry được kiểm.
13. **Token/session:** không kết luận hết quyền khi chỉ gỡ IdP group/SCIM membership.
14. **Workload/impersonation:** service identities và người có thể điều khiển chúng được đưa vào rule scope.
15. **Exceptions:** non-waivable rules không bị bypass; ngoại lệ được phép có authority, scope, TTL và controls.
16. **Positive tests:** nghiệp vụ hợp lệ vẫn được thực hiện, không có false deny do scope sai.
17. **Negative tests:** assignment conflict, self-approval, cross-tenant, missing attributes và privilege bypass bị chặn.
18. **Fault tests:** PDP/PIP outage, stale cache, event replay, role drift và connector failures đều được xử lý an toàn.
19. **Remediation proof:** chỉ đánh dấu VERIFIED sau khi quyền thực tế ở PEP/target đúng desired state.
20. **Audit:** policy reason, actor, resource, correlation và timestamps đủ tra cứu, không ghi secrets.
21. **Coverage reporting:** target/endpoint/role chưa kiểm được công bố là UNVERIFIED, có owner và deadline.
22. **Continuous review:** role catalog changes, release, access review, JML và incidents đều kích hoạt reevaluation phù hợp.

**SoD đạt yêu cầu khi rule được mô tả, được cấp đúng và được thực thi đúng**, chứ không chỉ khi một danh sách cặp role đã được cấu hình trong IGA.

## 31. Câu hỏi tự kiểm tra

**Câu 1.** SoD khác least privilege thế nào?

**Trả lời:** Least privilege giới hạn quyền tới mức cần thiết; SoD ngăn **một chủ thể kiểm soát các bước xung đột**. Hai role đều cần cho công việc không chứng minh được phép dùng chúng cho cùng giao dịch.

**Câu 2.** SSD và DSD khác nhau ở thời điểm nào?

**Trả lời:** SSD hạn chế **gán/giữ quyền đồng thời**; DSD hạn chế **kích hoạt/sử dụng các role** theo phiên hoặc ngữ cảnh. Transaction-level SoD còn xem actor history của từng resource.

**Câu 3.** Vì sao user đã logout khỏi role Creator vẫn không được tự duyệt payment cũ?

**Trả lời:** Lịch sử createdBy vẫn trỏ tới user đó. Transaction-level SoD kiểm chủ thể tạo/sửa payment, không chỉ active role của phiên mới.

**Câu 4.** Vì sao không chỉ so role PaymentCreator và PaymentApprover?

**Trả lời:** Quyền có thể đến từ FinanceAdmin, nested group, direct ACL, delegation hoặc workload. Cần ánh xạ business activities và tính effective access.

**Câu 5.** Một người có role Creator ở tenant A và Approver ở tenant B. Có phải vi phạm không?

**Trả lời:** Phụ thuộc **scope của rule**. Nếu SSD chỉ cấm trong cùng tenant và không có cross-tenant control, chưa chắc conflict. Nếu rule doanh nghiệp cấm toàn cục, kết quả khác.

**Câu 6.** SoD đã kiểm trước access request, vì sao cần kiểm lại ngay trước provision?

**Trả lời:** HR state, role/ACL, entitlement definition hoặc SoD policy có thể thay đổi giữa approval và cấp; kiểm lại tránh cấp quyền gây conflict mới.

**Câu 7.** IdP báo user đã mất Creator group, có đủ để bật Approver role không?

**Trả lời:** Chưa. Phải xét app-local role, ACL, token/session và effective action tại PEP, nhất là nếu SSD yêu cầu revoke-before-grant.

**Câu 8.** User có MFA mạnh có được tự approve giao dịch do mình tạo không?

**Trả lời:** Không nếu policy SoD cấm. MFA xác minh danh tính; không tạo sự độc lập của người kiểm soát.

**Câu 9.** Hai service accounts khác nhau có bảo đảm SoD không?

**Trả lời:** Không nếu cùng người/workload có thể kiểm soát cả hai qua secrets, assume-role hoặc pipeline. Phải xét controller và delegation thực tế.

**Câu 10.** Nếu một rule SoD không có createdBy đáng tin, nên mặc định ALLOW không?

**Trả lời:** Không. Với dữ liệu quan trọng để quyết định, phải fail-safe theo policy và đánh dấu thiếu dữ liệu để sửa, thay vì suy người tạo khác người duyệt.

**Câu 11.** SCIM trả success khi gỡ role nhưng API còn ALLOW. Trạng thái remediation là gì?

**Trả lời:** Chưa VERIFIED; cần xử lý cache, session, direct grants hoặc đường quyền khác, rồi kiểm negative probe tại target.

**Câu 12.** Một manager có thể chấp nhận risk của mọi SoD conflict không?

**Trả lời:** Không. Các **non-waivable constraints** không thể bị bỏ qua bằng approval thông thường; ngoại lệ chỉ tồn tại nếu policy cho phép, đúng authority và có kiểm soát bù trừ.

**Câu 13.** Vì sao chặn self-approval ở UI là chưa đủ?

**Trả lời:** Người dùng có thể gọi endpoint trực tiếp, qua bulk API hoặc async job. Backend/PEP và transaction commit phải kiểm SoD, không phụ thuộc giao diện.

**Câu 14.** Quy tắc SoD nên được kiểm bằng những bộ test nào?

**Trả lời:** Policy unit, effective role resolver, IGA approval/provisioning, PAM activation, transaction-level API, JML/SCIM, concurrency/fault tests và audit/reconciliation với positive/negative controls.

**Câu 15.** Chỉ số nào chứng minh quy tắc SoD thực sự được áp?

**Trả lời:** Bằng chứng **verified DENY** cho hành động xung đột, no unauthorized side effects, quyền hợp lệ vẫn ALLOW, role/ACL readback, policy version và dữ liệu actor/resource đáng tin. Số lượt request bị chặn riêng lẻ chưa đủ.

---

**Ghi nhớ:** **Quy tắc SoD không chỉ là một bảng cấm hai vai trò tồn tại cùng nhau.** Cần phân biệt **SSD khi cấp quyền, DSD khi kích hoạt và transaction-level SoD khi thực hiện nghiệp vụ**, dựa trên **business activities, quyền có hiệu lực, phạm vi tài nguyên, actor history và nguồn dữ liệu đáng tin**. Trong IAM **Joiner–Mover–Leaver**, quy tắc phải được kiểm lại trước provision, khi vai trò đổi và tại API thực thi; phải xét **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, phiên/token và quyền truy cập tồn dư**. Chỉ khi **quyền hợp lệ được phục vụ và hành động xung đột thật sự bị chặn**, có bằng chứng kiểm toán và xử lý ngoại lệ minh bạch, tổ chức mới đạt được mục tiêu phân tách nhiệm vụ.
