# Action trong Authorization: hành động được phép thực hiện trên tài nguyên

## 1. Action là gì trong hệ thống phân quyền?

Trong **Authorization**, **action** là **hành động mà một chủ thể yêu cầu thực hiện đối với một tài nguyên**. Câu hỏi của hệ thống phân quyền không dừng ở “ai đang đăng nhập?” mà là: **chủ thể này có được thực hiện hành động cụ thể này lên tài nguyên cụ thể này, trong ngữ cảnh hiện tại hay không?**

Ví dụ, trong một ứng dụng quản lý chi phí:

- Nhân viên có thể **xem** phiếu chi phí của mình.
- Trưởng nhóm có thể **duyệt** phiếu chi phí của thành viên trong nhóm nếu đáp ứng quy trình.
- Kế toán có thể **xuất báo cáo** trong phạm vi được phân công.
- Quản trị ứng dụng có thể **quản lý cấu hình**, nhưng không nhất thiết có quyền **duyệt thanh toán**.
- Người đã nghỉ việc không còn được thực hiện các action nghiệp vụ thuộc quan hệ công việc đã kết thúc.

Các hành động *view*, *create*, *edit*, *approve*, *export*, *delete*, *assignRole* khác nhau về hậu quả nên **không thể gom mọi hành động vào một cờ “đã đăng nhập” hoặc “có quyền truy cập ứng dụng”**.

Bài học thuộc chương **Authorization** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, với mục tiêu học về **Joiner–Mover–Leaver (JML)**, xác minh và enrollment, cấp/thu hồi quyền, **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và phòng tránh **quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt action với subject, resource, permission, role, HTTP method và OAuth scope.
2. Thiết kế danh mục action có tên, ngữ nghĩa và mức rủi ro rõ ràng.
3. Diễn đạt quyết định authorization dưới dạng **subject – action – resource – context**.
4. Áp dụng RBAC, ABAC và điều kiện quan hệ vào quyết định cho từng action.
5. Kiểm tra action ở **server và tầng nghiệp vụ**, không chỉ ở giao diện.
6. Xử lý action và quyền thực thi khi danh tính trải qua **Joiner–Mover–Leaver**.
7. Kiểm toán, kiểm thử và đối soát các quyết định cho phép/từ chối.

## 2. Công thức authorization: Subject, Action, Resource, Context

Một mô hình tổng quát có thể biểu diễn yêu cầu phân quyền như sau:

\[
Decision = Policy(Subject,\ Action,\ Resource,\ Context)
\]

Trong đó:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Subject** | Ai hoặc workload nào đang yêu cầu? | Lan, identityId=person-2046 |
| **Action** | Đang muốn làm gì? | invoice.approve |
| **Resource** | Thao tác lên đối tượng nào? | Invoice INV-873 thuộc Finance |
| **Context** | Điều kiện nào đang có hiệu lực? | Tài khoản active, phiên MFA đủ mạnh, giao dịch chưa hết hạn |
| **Policy** | Quy tắc nào áp dụng? | Chỉ người được ủy quyền, không tự duyệt hóa đơn do mình tạo |
| **Decision** | Kết quả quyết định | PERMIT, DENY hoặc kết quả trung gian theo hệ thống |

Một ví dụ:

~~~json
{
  "subject": {
    "identityId": "person-2046",
    "lifecycleState": "ACTIVE",
    "roles": ["FINANCE_APPROVER"],
    "department": "Finance"
  },
  "action": "invoice.approve",
  "resource": {
    "id": "INV-873",
    "department": "Finance",
    "createdBy": "person-7812",
    "state": "PENDING_APPROVAL",
    "amount": 8500000
  },
  "context": {
    "authenticationAssurance": "PHISHING_RESISTANT_MFA",
    "requestTime": "2026-11-23T09:00:00+07:00"
  }
}
~~~

Đây là **dữ liệu minh họa**, không phải schema chuẩn của một policy engine. Chỉ định một role trong request **không làm role đó đáng tin cậy**; subject, resource và context phải được lấy hoặc xác minh từ những nguồn được quản trị.

### Phân biệt authentication và authorization

- **Authentication:** xác thực chủ thể đang sử dụng phiên hoặc credential.
- **Authorization:** quyết định chủ thể đó có được làm **action** đối với **resource** theo policy hay không.
- **Audit:** ghi lại yêu cầu, quyết định, chính sách áp dụng và kết quả thực thi.

**Đăng nhập thành công không đồng nghĩa được duyệt giao dịch, tải dữ liệu hay gán quyền.** Ngay cả chủ thể đã xác thực bằng FIDO2 security key vẫn cần kiểm tra action được phép.

## 3. Action khác permission, role, scope và HTTP method thế nào?

Những thuật ngữ này có liên hệ nhưng không đồng nghĩa.

| Khái niệm | Bản chất | Ví dụ | Không nên hiểu nhầm |
|---|---|---|---|
| **Action** | Thao tác được yêu cầu trên tài nguyên | document.publish | Không tự nói ai được làm |
| **Permission** | Quyền cho phép một hoặc nhiều action trên phạm vi tài nguyên | Cho phép publish document thuộc team A | Không nhất thiết là một chuỗi tên action thuần túy |
| **Role** | Tập nhiệm vụ/quyền gắn với chức năng | CONTENT_EDITOR | Có role không nhất thiết cho phép mọi action trên mọi object |
| **Attribute** | Đặc điểm chủ thể/tài nguyên/ngữ cảnh | department=Finance | Attribute không tự đưa ra quyết định |
| **OAuth scope** | Phạm vi ủy quyền của client đối với API theo hợp đồng | reports:read | Không thay thế object-level authorization |
| **HTTP method** | Phương thức giao thức khi gọi API | GET, POST, PATCH, DELETE | Một POST có thể là approve, export hoặc reset |
| **Business event** | Sự kiện mô tả điều đã xảy ra | InvoiceApproved | Không phải yêu cầu quyền để làm việc đó |
| **API endpoint** | Giao diện tiếp nhận request | POST /invoices/{id}/approve | Endpoint không luôn ánh xạ 1:1 với action |

Ví dụ, endpoint:

~~~http
POST /api/invoices/INV-873/approve HTTP/1.1
Host: finance.example.org
Authorization: Bearer <REDACTED_ACCESS_TOKEN>
Content-Type: application/json
~~~

HTTP method là **POST**, action nghiệp vụ là **invoice.approve**, resource là **INV-873**. Nếu policy chỉ nói “người thuộc Finance được gửi POST”, attacker có thể lợi dụng những POST khác như **invoice.refund** hoặc **user.assignRole** nếu kiểm soát không đủ chi tiết.

**Action là ngữ nghĩa nghiệp vụ; HTTP method chỉ mô tả cách trao đổi với API.**

## 4. Phân loại action theo chức năng và mức độ rủi ro

Không phải mọi hành động đều cần cùng mức phê duyệt hoặc xác thực.

| Nhóm | Ví dụ action | Nguy cơ chính |
|---|---|---|
| **Read** | document.view, invoice.read | Lộ dữ liệu ngoài phạm vi |
| **Search/List** | employee.search, customer.list | Liệt kê hàng loạt dữ liệu dù không biết ID |
| **Create** | invoice.create, project.create | Tạo tài nguyên trái phép, gian lận hoặc tăng chi phí |
| **Update** | invoice.edit, profile.update | Sửa nội dung hoặc thuộc tính sai thẩm quyền |
| **Delete/Archive** | document.delete, account.archive | Mất dữ liệu, gián đoạn nghiệp vụ |
| **Approve/Reject** | invoice.approve, payment.reject | Gian lận hoặc vượt quy trình bốn mắt |
| **Publish/Release** | content.publish, deployment.release | Đưa dữ liệu hoặc mã tới môi trường công khai/production |
| **Export/Download** | customer.export, report.download | Rò rỉ dữ liệu ở quy mô lớn |
| **Share/Delegate** | document.share, access.delegate | Mở rộng quyền cho chủ thể khác |
| **Manage permissions** | role.assign, group.manage | Leo thang đặc quyền |
| **Execute/Operate** | job.run, deployment.rollback | Tác động đến hệ thống và tính sẵn sàng |
| **Impersonate/Support** | user.impersonate, account.unlock | Lạm dụng danh tính và quy trình hỗ trợ |
| **Security actions** | credential.reset, token.revoke | Chiếm quyền hoặc chặn truy cập ngoài thẩm quyền |

**Read không phải lúc nào cũng ít rủi ro**: đọc hồ sơ y tế, khóa cấu hình, dữ liệu nhân sự hoặc xuất 100.000 khách hàng có thể nhạy cảm hơn một thao tác cập nhật nhỏ. Phân loại phải xét **tài nguyên, phạm vi, số lượng dữ liệu và hậu quả**.

### Action hủy dữ liệu và action thu hồi quyền

Action như **account.disable**, **credential.revoke** hoặc **user.delete** có thể phục vụ bảo mật nhưng cũng có nguy cơ phá hoại nếu được cấp quá rộng. Hệ thống cần phân quyền cho **người vận hành IAM** phù hợp, ghi audit và có kiểm soát chống chặn nhầm chủ thể.

## 5. Thiết kế danh mục Action (Action Catalog)

Để dễ quản lý, tổ chức nên có **catalog action** với tên duy nhất, ý nghĩa ổn định, owner và mức rủi ro.

### Quy ước đặt tên

Một cách thường dùng là **resource.action**, ví dụ:

~~~text
invoice.read
invoice.create
invoice.edit
invoice.submit
invoice.approve
invoice.reject
invoice.cancel
invoice.export

user.read
user.suspend
user.reactivate
user.assignRole

report.view
report.export
report.schedule

deployment.deploy
deployment.rollback
~~~

Đây là **quy ước nội bộ minh họa**, không phải cú pháp bắt buộc của OAuth, RBAC hay ABAC. Có thể dùng dạng **verb:resource**, như **read:invoice**, nếu toàn tổ chức thống nhất được cách đặt tên.

### Metadata nên có

| Trường | Ý nghĩa |
|---|---|
| **actionId** | Định danh ổn định, ví dụ invoice.approve |
| **description** | Thao tác nghiệp vụ thực sự thực hiện |
| **resourceType** | Loại tài nguyên áp dụng |
| **owner** | Chủ sản phẩm/quy trình chịu trách nhiệm |
| **riskTier** | Mức nhạy cảm của hành động |
| **defaultPolicy** | Quy tắc mặc định khi không tìm thấy policy |
| **requiredAssurance** | Điều kiện MFA/step-up nếu có |
| **approvalRequirement** | Cần phê duyệt hay SoD không |
| **auditLevel** | Mức ghi log và bằng chứng |
| **version/deprecation** | Quản trị thay đổi ngữ nghĩa action |

### Những nguyên tắc đặt tên

1. **Tên phản ánh nghiệp vụ**: dùng *invoice.approve*, không dùng *postEndpoint42*.
2. **Không gộp hành động khác rủi ro** thành một quyền *invoice.manage* nếu không có nhu cầu và kiểm soát bù trừ.
3. **Không để tên giống nhưng ngữ nghĩa khác** giữa các ứng dụng mà không có namespace.
4. **Không tự động coi action mới là quyền của role cũ**; action mới cần policy và kiểm thử riêng.
5. **Định nghĩa ranh giới tài nguyên**: quyền invoice.read của tenant A không có nghĩa được xem invoice của tenant B.
6. **Có lộ trình version hóa** khi đổi nghĩa hoặc tách action để tránh cấp quyền ngoài dự kiến.

**Catalog không thay thế thực thi.** Nếu API không kiểm tra policy, dù tên action được ghi đẹp trong tài liệu vẫn không mang lại bảo mật.

## 6. Action CRUD và giới hạn của mô hình CRUD

CRUD (*Create, Read, Update, Delete*) là cách khởi đầu hữu ích, nhưng nhiều hệ thống có **hành động nghiệp vụ vượt xa CRUD**.

Ví dụ vòng đời hóa đơn:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: invoice.create
    DRAFT --> DRAFT: invoice.edit
    DRAFT --> SUBMITTED: invoice.submit
    SUBMITTED --> APPROVED: invoice.approve
    SUBMITTED --> REJECTED: invoice.reject
    REJECTED --> DRAFT: invoice.reopen
    APPROVED --> PAID: payment.execute
    DRAFT --> CANCELED: invoice.cancel
~~~

Trong sơ đồ:

- **invoice.edit** có thể được phép khi trạng thái **DRAFT**, nhưng bị từ chối khi đã **APPROVED**.
- **invoice.approve** không chỉ là UPDATE trường status; nó có thể tạo hiệu lực pháp lý/tài chính và cần phê duyệt độc lập.
- **payment.execute** có rủi ro cao hơn **invoice.read** và thường thuộc quy trình/role khác.
- **invoice.cancel** khác **invoice.delete**, vì hủy nghiệp vụ có thể vẫn phải giữ record để kiểm toán.

### Tại sao không dùng quyền update chung cho mọi chuyển trạng thái?

Nếu client có quyền **invoice.update** và có thể tự gửi **status=APPROVED**, client đã bỏ qua policy **invoice.approve**. Vì vậy:

1. Thiết kế action nghiệp vụ riêng cho những chuyển trạng thái quan trọng.
2. Chặn cập nhật trực tiếp các trường điều khiển trạng thái/owner/role từ API chung.
3. Kiểm tra action phù hợp với **trạng thái hiện tại**.
4. Bảo đảm cập nhật và kiểm tra điều kiện nằm trong **ranh giới giao dịch** thích hợp.

Một resource có thể có hàng chục thuộc tính, nhưng không phải mọi thuộc tính được sửa bằng cùng quyền.

## 7. Action và trạng thái của tài nguyên

Authorization có thể phụ thuộc vào **state machine** của tài nguyên, không chỉ vào vai trò người dùng.

| Action | Trạng thái cho phép | Điều kiện bổ sung |
|---|---|---|
| **invoice.edit** | DRAFT, REJECTED | Người tạo hoặc người được ủy quyền chỉnh sửa |
| **invoice.submit** | DRAFT | Đã có dữ liệu bắt buộc, chủ thể hợp lệ |
| **invoice.approve** | SUBMITTED | Role phù hợp, không tự duyệt, hạn mức còn hiệu lực |
| **invoice.reject** | SUBMITTED | Approver được phân công và có lý do hợp lệ |
| **invoice.pay** | APPROVED | Vai trò thanh toán, kiểm soát SoD và ngân sách |
| **invoice.cancel** | DRAFT hoặc trạng thái được policy quy định | Có thể yêu cầu xác thực lại |
| **invoice.export** | Tùy trạng thái và độ nhạy | Phạm vi dữ liệu, số lượng, bảo vệ đầu ra |

Cần phân biệt hai câu hỏi:

- **Có quyền yêu cầu action?** Ví dụ Lan có quyền invoice.approve trên nhóm Finance.
- **Action có hợp lệ về nghiệp vụ lúc này?** Hóa đơn đã được thanh toán có thể không thể duyệt lại, kể cả bởi approver hợp lệ.

Ứng dụng nên trả lỗi phù hợp và **không sử dụng kết quả authorization như sự thay thế cho kiểm tra tính hợp lệ của trạng thái nghiệp vụ**. Cả hai phải được thực thi an toàn.

## 8. Action trong RBAC: Role → Permission → Action

**Role-Based Access Control (RBAC)** cấp quyền cho role, sau đó người dùng được gán role phù hợp. Trong một thiết kế thông dụng:

~~~mermaid
flowchart LR
    H[HRIS / JML] --> I[IAM / IGA]
    I --> R[Role assignment]
    R --> P[Permissions]
    P --> A[Actions]
    A --> X[Resource cụ thể]
    X --> D[Policy decision + enforcement]
~~~

Ví dụ role matrix:

| Role | invoice.read | invoice.create | invoice.approve | payment.execute | user.assignRole |
|---|---:|---:|---:|---:|---:|
| **EMPLOYEE** | Theo phạm vi | Theo phạm vi | Không | Không | Không |
| **FINANCE_APPROVER** | Có | Tùy phạm vi | Có điều kiện | Không | Không |
| **PAYMENT_OPERATOR** | Có | Không | Không | Có điều kiện | Không |
| **IAM_ADMIN** | Không mặc định | Không mặc định | Không | Không | Có điều kiện |
| **AUDITOR** | Chỉ đọc trong scope | Không | Không | Không | Không |

**Có một role không tự động mang lại quyền với mọi tài nguyên.** Ví dụ FINANCE_APPROVER có thể duyệt hóa đơn của **phòng mình**, dưới **hạn mức**, khi hóa đơn chưa được chính mình tạo.

### Tránh quyền “Admin làm mọi việc”

Một role ADMIN duy nhất cho toàn doanh nghiệp dễ tạo **privilege creep** và vi phạm **least privilege**. Quản trị danh tính có thể cần action **user.disable** nhưng không cần **payment.execute**. Với action nhạy cảm, tách role vận hành, role kiểm toán, role phê duyệt và role khẩn cấp theo nhu cầu.

### Role hierarchy

Nếu role kế thừa quyền, phải kiểm tra **quyền thực tế sau kế thừa**. Một role cấp cao hơn không nhất thiết được phép mọi action rủi ro cao: một số action có **separation-of-duties** hoặc ngữ cảnh bắt buộc, không nên chỉ dựa vào thứ bậc role.

## 9. Action trong ABAC: chính sách theo thuộc tính

**Attribute-Based Access Control (ABAC)** xét thuộc tính của subject, resource, action và context thay vì dựa đơn thuần vào role.

Ví dụ chính sách dạng ngôn ngữ tự nhiên:

> Cho phép action **report.export** khi người dùng đang active, thuộc cùng đơn vị với báo cáo, báo cáo không bị gắn mức nhạy cảm vượt clearance, phiên xác thực đủ mạnh và không có lệnh phong tỏa xuất dữ liệu.

Một policy minh họa:

~~~text
permit if
    subject.lifecycleState == ACTIVE
    and action == "report.export"
    and subject.department == resource.department
    and subject.clearance >= resource.classification
    and context.authenticationAssurance >= REQUIRED_FOR_EXPORT
    and context.exportVolume <= policy.allowedExportVolume
    and resource.exportHold != true
else deny
~~~

Các dấu so sánh trong giả mã biểu thị **hàm so sánh theo policy được định nghĩa**; ví dụ không khẳng định assurance hay clearance là những chuỗi có thể so sánh theo thứ tự chữ cái.

### Nhóm thuộc tính thường sử dụng

| Nhóm | Ví dụ | Lưu ý |
|---|---|---|
| **Subject** | identityId, department, employmentStatus, assignedRoles | Lấy từ nguồn có thẩm quyền |
| **Resource** | ownerId, tenantId, classification, recordState | Không tin thuộc tính do client tự gửi khi cần lấy từ DB |
| **Action** | report.export, invoice.approve | Tên/định nghĩa được quản trị |
| **Environment** | requestTime, deviceTrust, locationRisk, sessionAssurance | Từ kênh xác minh và hệ thống rủi ro đáng tin |
| **Relationship** | managerOf, memberOfProject, delegatedBy | Quan hệ phải còn hiệu lực và không bị giả mạo |

**ABAC tăng tính linh hoạt nhưng cũng tăng yêu cầu quản trị thuộc tính.** Một quyết định “đúng” theo dữ liệu department sai hoặc nguồn đã cũ vẫn có thể tạo quyền ngoài ý muốn. Reconciliation và quản lý nguồn thuộc tính quan trọng không kém biểu thức policy.

## 10. Action trong ReBAC và quyền theo quan hệ

Trong những ứng dụng chia sẻ tài liệu, dự án hoặc mạng xã hội doanh nghiệp, quyền thường phụ thuộc vào **mối quan hệ** (*Relationship-Based Access Control – ReBAC*):

- Chủ tài liệu được **document.edit**.
- Người được chia sẻ với vai trò viewer được **document.read**.
- Quản lý dự án được **project.member.add** trong dự án đang sở hữu.
- Người được ủy quyền tạm thời có thể **invoice.approve** trong thời hạn đã duyệt.
- Người bị xóa khỏi dự án không còn được **artifact.download**, dù vẫn có account IdP hợp lệ.

Một đồ thị quan hệ minh họa:

~~~mermaid
flowchart LR
    U[User Lan] -->|member_of| TEAM[Project Alpha]
    TEAM -->|owner_of| DOC[Document D-42]
    U -->|approved_delegation| DEL[Delegation record]
    DEL -->|grants: document.publish| DOC
    DOC -->|tenant| TEN[Tenant A]
~~~

ReBAC không thay thế RBAC/ABAC trong mọi trường hợp. Nhiều hệ thống kết hợp:

\[
Permit = RoleAllows \land RelationshipAllows \land AttributeConstraints
\]

Công thức trên chỉ là **một cách kết hợp policy minh họa**, không có nghĩa mọi sản phẩm luôn dùng AND. Quyết định chính thức phải xác định thứ tự và quy tắc **deny/permit**, ngoại lệ và các điều kiện bắt buộc.

### Quyền chia sẻ không được vượt quyền gốc

Nếu Lan có quyền document.read nhưng không có document.share, Lan không được tạo lời mời cấp quyền đọc cho người ngoài. Ngay cả người được phép share cũng không nên cấp **permission mạnh hơn phạm vi bản thân được ủy quyền** nếu không có chính sách cho phép rõ ràng.

## 11. Enforcement: kiểm tra action ở đâu?

Một kiến trúc authorization thường phân biệt:

- **Policy Enforcement Point (PEP):** nơi chặn request và thực thi quyết định.
- **Policy Decision Point (PDP):** thành phần đánh giá policy để trả quyết định.
- **Policy Information Point (PIP):** nơi lấy các thuộc tính đáng tin cậy.
- **Policy Administration Point (PAP):** nơi quản trị và phát hành policy.

Đây là cách phân tách khái niệm thường gặp trong các kiến trúc policy-based access control; hệ thống nhỏ có thể triển khai chúng trong cùng một ứng dụng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant PEP as API / PEP
    participant PIP as Trusted attributes
    participant PDP as PDP / Policy engine
    participant DB as Business resource store
    C->>PEP: Action invoice.approve với resourceId
    PEP->>DB: Tải invoice theo tenant đã xác minh
    PEP->>PIP: Lấy subject lifecycle, roles, MFA context
    PIP-->>PEP: Thuộc tính tin cậy
    PEP->>PDP: Subject + action + resource + context
    PDP-->>PEP: PERMIT / DENY + obligations
    PEP->>PEP: Kiểm soát trạng thái và điều kiện giao dịch
    PEP->>DB: Chỉ mutate nếu PERMIT và hợp lệ
    PEP-->>C: Kết quả + audit
~~~

### Quy tắc “deny by default”

Khi không có policy cho một action, kết quả an toàn mặc định thường là **DENY**. Nếu dữ liệu không đủ hoặc hệ thống quyết định gặp lỗi, hành động nhạy cảm không nên tự được cho phép.

Cần phân biệt:

- **PERMIT:** có đủ chứng cứ và điều kiện để thực hiện.
- **DENY:** có quy tắc hoặc trạng thái từ chối.
- **NOT_APPLICABLE:** không có rule áp dụng; hệ thống cần cách kết hợp phù hợp và mặc định an toàn.
- **INDETERMINATE:** không đưa ra kết quả đáng tin vì thiếu dữ liệu/lỗi đánh giá; không biến thành PERMIT mặc định.

### Quyết định và thực thi là hai khâu

Một PDP trả “PERMIT” nhưng API bỏ qua quyết định hoặc cập nhật sai đối tượng vẫn không an toàn. Ngược lại, API gateway chặn đúng route nhưng backend lại cho chỉnh sửa role qua một endpoint khác có thể tạo **authorization bypass**.

**Tất cả đường thực thi cùng một action phải được bảo vệ**: REST API, GraphQL, batch job, admin portal, message consumer và đường nội bộ được gọi trực tiếp.

## 12. Route-level authorization không đủ cho object-level authorization

Một endpoint REST có thể yêu cầu action **invoice.read**, nhưng người dùng vẫn chỉ được xem những invoice cụ thể trong phạm vi được cấp.

Ví dụ:

~~~http
GET /api/invoices/INV-873 HTTP/1.1
Host: finance.example.org
Authorization: Bearer <REDACTED_ACCESS_TOKEN>
~~~

Nếu controller chỉ kiểm “có quyền invoice.read” và trả bất kỳ invoice theo ID do client nhập, người dùng có thể thay **INV-873** thành invoice của phòng khác. Đây là lỗi **Broken Object Level Authorization (BOLA)** hoặc **Insecure Direct Object Reference (IDOR)** trong những bối cảnh tương ứng.

### Cách phòng tránh

1. Xác thực token/phiên từ nguồn đáng tin.
2. Liên kết subject với identity và tenant hiện hành.
3. Tải resource theo ID **kèm giới hạn phạm vi đáng tin**, tránh truy vấn xuyên tenant.
4. Kiểm tra action dựa trên **tài nguyên thực tế**, không chỉ tên route.
5. Nếu không được phép, từ chối và tránh để response lộ dữ liệu ngoài phạm vi.
6. Với danh sách hoặc tìm kiếm, áp filter authorization cho **từng record hoặc tập kết quả**, không chỉ kiểm route.
7. Kiểm tra cả export, CSV, download, bulk endpoint và background job.

**Ẩn nút trong frontend chỉ cải thiện UX, không phải kiểm soát phân quyền.** Attacker có thể gửi request trực tiếp hoặc gọi API từ một client khác.

## 13. Action cấp trường dữ liệu và chống mass assignment

Một action như **profile.update** có thể cho phép sửa tên hiển thị nhưng **không** cho sửa role, tenant, trạng thái nhân viên hay số dư.

Ví dụ request độc hại:

~~~json
{
  "displayName": "Lan Nguyen",
  "department": "Finance",
  "roles": ["SUPER_ADMIN"],
  "active": true
}
~~~

Nếu server bind toàn bộ JSON thành entity rồi lưu mà không kiểm tra **field-level authorization**, một người chỉ có quyền update profile có thể tự gán role hoặc mở lại tài khoản đã bị khóa.

### Biện pháp

- Dùng **DTO/allowlist** cho những trường được phép ghi của action.
- Tách **profile.update**, **user.assignRole**, **identity.changeDepartment** thành các action khác nhau.
- Không coi thuộc tính do client gửi như lifecycleState hoặc createdBy là nguồn đáng tin.
- Kiểm tra quyền trên **field**, **resource** và **state transition** trước khi commit.
- Với API cập nhật hàng loạt, xác minh **từng đối tượng và từng thay đổi** hoặc thiết lập cơ chế đánh giá tập hợp tương đương.
- Ghi audit thay đổi security-sensitive fields và chủ thể phê duyệt.

**Một endpoint PATCH có thể chứa nhiều action nghiệp vụ ẩn dưới các trường JSON.** Thiết kế phải phân ranh giới rõ để tránh cấp một permission quá rộng.

## 14. Action và OAuth scope: phân tầng hai lần kiểm soát

Một access token hợp lệ có thể chứa scope như **invoices:read** hoặc **invoices:approve**. Scope thể hiện **ủy quyền của client đối với API**, nhưng không tự bảo đảm chủ thể có quyền trên từng hóa đơn.

Ví dụ:

- Token có audience **invoices-api** và scope **invoices:approve**.
- Subject đang active với role **FINANCE_APPROVER**.
- Resource **INV-873** thuộc tenant B, trong khi subject chỉ thuộc tenant A.

Kết quả phải là **DENY** vì người dùng không có quyền với resource đó, dù token có scope phù hợp với loại thao tác.

### Quy trình đánh giá

~~~mermaid
flowchart TD
    REQ[Request với access token] --> TOK{Token hợp lệ cho API?}
    TOK -->|Không| UNAUTH[401 / xác thực không hợp lệ]
    TOK -->|Có| SCP{Scope/client cho phép loại action?}
    SCP -->|Không| FORB[403 / bị từ chối]
    SCP -->|Có| ID{Subject và quan hệ còn hiệu lực?}
    ID -->|Không| FORB
    ID -->|Có| RES{Resource trong đúng tenant/scope?}
    RES -->|Không| FORB
    RES -->|Có| POL{RBAC/ABAC/ReBAC và context đạt?}
    POL -->|Không| FORB
    POL -->|Có| EXEC[Thực hiện action + ghi audit]
~~~

HTTP 401/403 trong sơ đồ là minh họa cách phân loại phản hồi phổ biến, không phải yêu cầu mọi loại lỗi chính sách luôn dùng cùng một mã. Quyết định còn có thể phụ thuộc phương pháp xử lý tài nguyên không tồn tại, truy cập ẩn hoặc kết quả không xác định theo thiết kế API.

### Scope không phải bản sao toàn bộ permission

Không nên tạo hàng nghìn OAuth scope theo từng object nếu mô hình không yêu cầu và gây khó vận hành. Scope có thể là **cửa kiểm tra thô** ở API, còn **policy engine** xử lý quyền trên bản ghi và ngữ cảnh thời điểm. Ngược lại, API đặc quyền có thể cần scope hẹp hơn để hạn chế thiệt hại khi token bị lộ.

## 15. SSO và SCIM không tự quyết định action nghiệp vụ

- **IdP/SSO** xác thực chủ thể và chuyển kết quả đăng nhập theo SAML/OIDC.
- **SCIM** tạo/cập nhật/vô hiệu hóa tài khoản và nhóm ở ứng dụng đích.
- **RBAC/ABAC/ReBAC** cùng policy engine quyết định **action nào được thực hiện trên resource nào**.
- **Reconciliation** đối soát liệu tài khoản/quyền thực tế ở đích còn khớp desired state.

Ví dụ, SCIM đã đồng bộ Lan vào nhóm **FINANCE_APPROVER**. Khi Lan đăng nhập qua SSO, API vẫn phải kiểm tra action **invoice.approve** trên hóa đơn cụ thể, kèm điều kiện **không tự duyệt** và **hạn mức**. Group membership có thể là một đầu vào policy, **không phải bằng chứng đủ cho mọi yêu cầu**.

### Sự khác nhau về vòng đời

| Sự kiện | IdP/SSO | SCIM/Provisioning | Authorization action |
|---|---|---|---|
| **Joiner** | Tạo khả năng đăng nhập hợp lệ, MFA | Tạo account/group | Chỉ cho action trong phạm vi vai trò mới |
| **Mover** | Có thể giữ cùng authenticator, tăng yêu cầu MFA | Đổi group/role, thu hồi quyền cũ | Tính lại action được phép theo role/context mới |
| **Leaver** | Disable đăng nhập và xử lý phiên | Deactivate account, gỡ nhóm/quyền | **DENY** các action không còn thẩm quyền |
| **Rejoiner** | Xác minh enrollment/credential mới phù hợp | Tạo hoặc liên kết account theo quy trình mới | Không tự tái cấp action của vai trò trước đây |

**SSO thành công và SCIM thành công không tự bảo đảm authorization đã đúng** nếu ứng dụng vẫn tin role/token cũ hoặc không kiểm tra quyền ở resource cụ thể.

## 16. Action trong Joiner lifecycle

Khi một người gia nhập, tổ chức cần xây dựng **tập action tối thiểu** tương ứng với vai trò và thời điểm hiệu lực.

### Luồng mẫu

1. **HRIS/nguồn có thẩm quyền** tạo identity và quan hệ làm việc với effectiveAt.
2. **Identity proofing/enrollment** xác minh người dùng và liên kết authenticator theo yêu cầu.
3. **IAM/IGA** tính role/permission và catalog action hợp lệ cho vị trí.
4. **SCIM/API connector** tạo account và group/entitlement ở các đích liên quan.
5. **IdP/SSO** cho phép xác thực khi điều kiện bắt đầu và bảo mật được thỏa mãn.
6. **Ứng dụng** kiểm tra subject–action–resource–context ở mỗi điểm thực thi.
7. **Reconciliation** so sánh quyền dự kiến với quyền thật và khắc phục sai lệch.

### Tránh cấp action trước effectiveAt

Một tài khoản có thể được chuẩn bị sớm cho onboarding. Tuy nhiên, quyền **payment.execute**, **customer.export** hoặc **role.assign** không được tự hoạt động trước thời điểm được phê duyệt nếu chính sách chưa cho phép.

**Tạo account không đồng nghĩa cấp mọi action.** Mọi action mới phải xuất phát từ role, attribute, quan hệ, phê duyệt hoặc quyền ngoại lệ có căn cứ, không từ mặc định quá rộng của ứng dụng.

## 17. Action trong Mover lifecycle: thu hồi quyền cũ trước khi tích lũy

**Mover** là nguồn phổ biến gây **privilege accumulation**: một người chuyển bộ phận nhưng vẫn giữ action của vị trí cũ.

Ví dụ Lan chuyển từ **Sales** sang **Finance**:

| Action | Trước Mover | Sau Mover mong muốn | Rủi ro nếu đồng bộ sai |
|---|---|---|---|
| customer.export | Cho phép trong Sales | Thu hồi | Xuất dữ liệu khách hàng trái phạm vi |
| opportunity.edit | Cho phép trong Sales | Thu hồi | Tiếp tục sửa pipeline Sales |
| invoice.read | Không được cấp | Cấp theo Finance | Thiếu quyền làm việc |
| invoice.approve | Không được cấp | Chỉ sau phê duyệt và đủ điều kiện | Cấp đặc quyền thiếu SoD |
| user.assignRole | Không | Không | Leo thang quyền nếu role mapping quá rộng |

### Những bước bắt buộc

1. Nhận **sự kiện Mover mới nhất** từ nguồn có thẩm quyền.
2. Tính lại desired actions theo role/attribute và relationship hiện hành.
3. **Gỡ các action cũ** không còn hợp lệ, kể cả quyền cấp trực tiếp và ngoại lệ hết hạn.
4. Cấp action mới sau approval/SoD.
5. Đồng bộ group/role ở đích qua SCIM/API, xử lý lỗi và độ trễ.
6. Cập nhật hoặc vô hiệu cache/token chứa entitlement cũ khi policy yêu cầu.
7. Kiểm tra thực tế: request **customer.export** phải bị từ chối; **invoice.read** trong phạm vi Finance phải được chấp nhận.

**Một JWT access token còn hạn có thể giữ role cũ** nếu resource server chỉ dựa vào claim từ lúc phát token. Với action nhạy cảm cần giải pháp giới hạn tuổi token, kiểm tra quyền hiện hành, revocation hoặc cơ chế tương đương để thu hồi đúng yêu cầu.

## 18. Action trong Leaver lifecycle: ngăn thực thi sau khi hết quan hệ

Khi nhân viên nghỉ việc, mục tiêu không chỉ là làm “tài khoản ở IdP bị disable” mà là **ngăn những action không còn thẩm quyền ở mọi hệ thống thuộc phạm vi**.

### Các tầng cần xử lý

| Tầng | Nguy cơ còn lại | Hành động phòng vệ |
|---|---|---|
| IdP/SSO | Chỉ chặn đăng nhập mới | Disable và xử lý session IdP |
| SCIM User/Group | Account đích và nhóm còn active | Deactivate, gỡ entitlement, readback |
| App session | Cookie của ứng dụng vẫn dùng được | Revocation/logout theo năng lực RP |
| OAuth access token | JWT chưa hết hạn hoặc introspection cache cũ | Kiểm tra trạng thái lifecycle/revoke tại RS |
| API key/SSH key | Credential độc lập với SSO | Thu hồi hoặc xoay secret |
| Local account | Không chịu chính sách IdP | Khóa trực tiếp ở ứng dụng |
| Background job | Tác vụ tiếp tục dùng quyền cũ | Gỡ quyền tác vụ, chuyển owner hoặc dừng theo chính sách |
| Policy cache | Role/action còn được cache | Invalidate hoặc hạn chế TTL phù hợp |
| Audit/reconciliation | Không có bằng chứng thực tế đã chặn | Kiểm thử/readback action quan trọng ở đích |

### Ví dụ Leaver

- **17:00:** sự kiện Leaver có hiệu lực.
- **17:00:05:** IdP disable account.
- **17:01:** API nhận access token cũ vẫn còn exp hợp lệ.
- **17:01:02:** nếu API chỉ kiểm chữ ký/exp và role cũ, action customer.export có thể vẫn được thực thi.
- **17:01:05:** khi RS áp lifecycle policy cập nhật hoặc cơ chế thu hồi phù hợp, action bị từ chối.
- **17:03:** ứng dụng legacy còn local account; IAM cần xử lý riêng và đối soát.

Mốc thời gian chỉ là **ví dụ giả định**. Với action rủi ro cao, không thể mặc nhiên chấp nhận quyền tồn dư đến khi token hết hạn nếu chính sách yêu cầu cắt ngay.

**Leaver hoàn tất khi không còn action trái thẩm quyền có thể được thực thi trong phạm vi đã xác định**, có bằng chứng từ các hệ thống đích hoặc cơ chế kiểm tra được phê duyệt. Cần phân biệt kết thúc quyền truy cập với việc **giữ dữ liệu nghiệp vụ theo chính sách lưu giữ**.

## 19. Action cho service account, bot và thiết bị

Không phải mọi subject đều là nhân viên. **Service account, workload identity, device identity, CI/CD bot và API client** cũng có action được phép, ví dụ:

- **job.run** để batch thực hiện tác vụ định kỳ.
- **report.generate** để service tạo báo cáo.
- **deployment.deploy** cho CI/CD vào môi trường cụ thể.
- **secret.read** chỉ đối với secret cần thiết.
- **message.publish** trên topic được phân quyền.
- **artifact.upload** vào bucket cụ thể.

### Không cấp toàn bộ quyền chỉ vì bot thuộc hệ thống nội bộ

Bot nên có:

1. **Owner kỹ thuật** và workload/application ID đáng tin.
2. **Action catalog và scope tối thiểu** theo nhiệm vụ, không dùng role Admin chung.
3. **Audience/resource cụ thể** khi dùng OAuth, tránh token dùng nhầm API.
4. **Credential quản lý tập trung** như workload federation, managed identity hoặc secret manager.
5. **Giới hạn môi trường** production/test và thời hạn khi phù hợp.
6. **Logging và access review** để phát hiện action không còn được sử dụng.
7. **Quy trình thu hồi** khi workload ngừng hoặc thay đổi vai trò.

Khi nhân viên là owner của bot nghỉ việc, **không mặc nhiên xóa bot** nếu workload vẫn hợp lệ. Cần chuyển owner, rà soát action, bí mật người cũ có thể biết và việc cấp quyền tại đích.

### Quyền máy–máy khác quyền người dùng

Một access token từ OAuth **client credentials** thường đại diện cho client/workload. Không tự cho phép bot thực hiện **invoice.approve** như một con người nếu nghiệp vụ yêu cầu người phê duyệt có trách nhiệm độc lập. Nếu hệ thống cần bot thực hiện một action đặc biệt, phải có chính sách, owner và bằng chứng kiểm soát phù hợp.

## 20. Action nhạy cảm: phê duyệt, SoD và quyền tạm thời

### Separation of Duties (SoD)

Một hệ thống tài chính có thể yêu cầu người **tạo** hóa đơn không được **duyệt** chính hóa đơn đó, dù họ có role approver. Đây là **dynamic SoD** theo resource và lịch sử nghiệp vụ, không giải quyết được chỉ bằng cách cho/không cho role ở cấp tài khoản.

Ví dụ:

~~~text
permit(invoice.approve) only if
    subject.hasRole("FINANCE_APPROVER")
    and subject.id != invoice.createdBy
    and invoice.state == SUBMITTED
    and invoice.amount <= subject.approvalLimit
    and approvalDelegationIsCurrent(subject, invoice)
    and authenticationMeetsPolicy(subject, context)
~~~

**Hạn mức** và **ủy quyền** phải lấy từ dữ liệu có thẩm quyền; không tin giá trị amount/approverId do client tự điền nếu có thể bị sửa.

### Just-in-Time (JIT) privilege

Action nhạy cảm như **user.assignRole** hoặc **production.deploy** có thể được cấp trong một **khoảng thời gian ngắn** sau phê duyệt, có MFA mạnh, ghi audit và thu hồi khi hết hạn.

Các trường cần quản lý:

| Trường | Ví dụ |
|---|---|
| Subject | iam-2046 |
| Action | production.deploy |
| Resource scope | service-payments, environment=production |
| Approved by | Người có thẩm quyền khác |
| Valid from/until | Cửa sổ triển khai đã duyệt |
| Authentication | Phishing-resistant MFA khi cần |
| Justification | Change request có owner |
| Review/revoke | Tự hết hạn và đối soát sau thay đổi |

**Đã có JIT approval không đồng nghĩa được bỏ qua các điều kiện khác** như tenant, SoD, change freeze hoặc kiểm tra resource state.

### Break-glass action

Quyền khẩn cấp có thể vượt quy trình thông thường trong những điều kiện được quy định chặt. Cần owner, phạm vi, lý do, thời gian, cảnh báo, giám sát và review sau sự kiện. Không biến “break-glass” thành một role tồn tại vĩnh viễn để bỏ qua mọi policy.

## 21. Ví dụ Java: kiểm tra action tại tầng nghiệp vụ

Đoạn Java dưới đây là **mẫu thiết kế minh họa**, không phải thư viện security hoàn chỉnh. Mục đích là cho thấy service không nên chỉ kiểm tra vai trò ở controller rồi cập nhật dữ liệu vô điều kiện.

~~~java
import java.time.Instant;

record SubjectContext(
        String identityId,
        String tenantId,
        boolean active,
        boolean strongAuthentication
) {}

record Invoice(
        String id,
        String tenantId,
        String createdBy,
        String state,
        long amountInMinorUnits
) {}

record AuthorizationRequest(
        SubjectContext subject,
        String action,
        Invoice resource,
        Instant now
) {}

interface PolicyEngine {
    boolean isAllowed(AuthorizationRequest request);
}

interface InvoiceRepository {
    Invoice getForUpdate(String id, String tenantId);
    void markApproved(String invoiceId, String approvedBy);
}

public final class InvoiceService {
    private final PolicyEngine policy;
    private final InvoiceRepository repository;

    public InvoiceService(PolicyEngine policy, InvoiceRepository repository) {
        this.policy = policy;
        this.repository = repository;
    }

    // Caller phải bảo đảm transaction/locking thích hợp cho cả thao tác.
    public void approve(String invoiceId, SubjectContext subject) {
        if (!subject.active()) {
            throw new SecurityException("Inactive identity");
        }

        // Không lấy tenantId/subjectId từ JSON do client tự khai.
        Invoice invoice = repository.getForUpdate(invoiceId, subject.tenantId());

        if (!invoice.tenantId().equals(subject.tenantId())) {
            throw new SecurityException("Cross-tenant access denied");
        }

        AuthorizationRequest request = new AuthorizationRequest(
                subject, "invoice.approve", invoice, Instant.now()
        );

        if (!policy.isAllowed(request)) {
            throw new SecurityException("Action not permitted");
        }

        if (!"SUBMITTED".equals(invoice.state())) {
            throw new IllegalStateException("Invalid invoice state");
        }

        if (subject.identityId().equals(invoice.createdBy())) {
            throw new SecurityException("Self-approval denied");
        }

        repository.markApproved(invoice.id(), subject.identityId());
    }
}
~~~

### Những điểm quan trọng

- **SubjectContext** phải được tạo từ phiên/token đã xác minh và nguồn lifecycle đáng tin; không nhận vai trò/tenant/active do client tự khai.
- **getForUpdate** gợi ý nhu cầu lock/concurrency control. Một hệ thống thật phải đặt các thao tác trong giao dịch phù hợp và xử lý race condition khi nhiều người cùng duyệt.
- Policy engine phải kiểm tra **role, department, tenant, hạn mức, thời hạn ủy quyền, assurance và SoD** theo yêu cầu, không phải trả true tùy tiện.
- Kiểm tra **resource.state** và người tạo giúp tránh bypass workflow.
- Nếu action thay đổi nhiều hệ thống, cần thiết kế transactional outbox/saga hoặc cơ chế nhất quán khác, không coi nhiều API calls là một giao dịch ACID mặc định.
- Ghi audit về **decision** và **business result** mà không đưa token, password hoặc dữ liệu nhạy cảm vượt nhu cầu vào log.

Đoạn ví dụ không giải quyết đầy đủ exception handling, idempotency, audit, database transaction, authorization caching, tenant isolation hoặc chống giả mạo subject. Khi triển khai cần dùng framework và thư viện có kiểm soát thay vì sao chép như code production.

## 22. Test action: kiểm tra cả trường hợp cho phép và từ chối

Một hệ thống authorization tốt phải kiểm thử **action + resource + context**, đặc biệt những trường hợp dễ bỏ sót khi chuyển vai trò hoặc thay dữ liệu.

| Test case | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Cấp quyền hợp lệ | Approver active, cùng tenant, invoice SUBMITTED, hạn mức đạt | PERMIT |
| Thiếu role | User active nhưng không có quyền approve | DENY |
| Tự duyệt | createdBy bằng subject | DENY |
| Khác tenant | Invoice thuộc tenant B, subject thuộc A | DENY |
| Tài khoản Leaver | identity lifecycleState=TERMINATED | DENY |
| Role cũ sau Mover | Cache còn role Sales nhưng nguồn hiện hành đã Finance | DENY action Sales đã thu hồi |
| MFA không đạt | Action yêu cầu step-up nhưng phiên chưa đủ | REQUIRE_STEP_UP hoặc từ chối theo hợp đồng |
| Hóa đơn đã duyệt | resource.state=APPROVED | Từ chối chuyển trạng thái lại |
| Token sai audience | Token cho API khác | Reject authentication/authorization |
| Chỉ có scope | Access token có invoices:approve nhưng user không có approval role | DENY |
| Update mass assignment | Client sửa roles trong profile.update | Reject hoặc bỏ qua trường không được phép theo thiết kế |
| Group cấp trực tiếp | Role SCIM chưa đồng bộ ở app nhưng IdP login thành công | Không cấp action khi thiếu điều kiện |
| Quyền JIT hết hạn | Action production.deploy sau thời gian được duyệt | DENY |
| PDP unavailable | Policy engine lỗi khi đánh giá action nhạy cảm | Không cho phép mặc định |
| Bulk export | User có read một record nhưng không có export toàn bộ | DENY export ngoài scope |
| Job máy thiếu owner | Workload vẫn dùng action rộng sau khi ngừng hợp đồng | Từ chối/cảnh báo theo lifecycle workload |

### Các lớp test nên có

1. **Unit test policy:** tập trung vào truth table của điều kiện và conflict.
2. **Integration test:** xác minh identity, resource, group và claim được nạp đúng.
3. **API test:** gửi request trực tiếp, không phụ thuộc việc frontend ẩn nút.
4. **Multi-tenant test:** cố truy cập ID của tenant khác.
5. **Workflow test:** thử chuyển trạng thái bất hợp lệ, tự phê duyệt và race condition.
6. **JML test:** thay role, chấm dứt quan hệ, hủy quyền tạm và token cũ.
7. **Negative/adversarial test:** thay resource ID, trường JSON, scope và client grant.
8. **Audit test:** xác minh log đủ thông tin nhưng không lộ bí mật.

**Không chỉ kiểm “user hợp lệ có thể làm được”.** Những đường từ chối mới là lớp giúp chứng minh quyền tối thiểu.

## 23. Lỗi thiết kế phổ biến dẫn đến authorization bypass

| Sai lầm | Hậu quả | Phòng tránh |
|---|---|---|
| Chỉ kiểm tra đã login | Mọi người đăng nhập đều có thể thực thi action | Server-side policy theo action/resource |
| Chỉ ẩn nút ở UI | Người dùng gọi API trực tiếp | PEP tại server/backend |
| Chỉ kiểm tra HTTP GET/POST | Bỏ sót approve/export/assignRole trong cùng method | Action catalog theo nghiệp vụ |
| Chỉ kiểm role mà không kiểm resource | BOLA/IDOR, truy cập cross-tenant | Object-level và tenant policy |
| Tin role/tenant do client gửi | Leo thang quyền | Thuộc tính từ nguồn đáng tin |
| Kiểm scope nhưng không kiểm ABAC | Token có scope rộng truy cập dữ liệu người khác | Phân quyền theo object và ngữ cảnh |
| Cập nhật tùy ý trường của entity | Mass assignment, tự gán admin | DTO allowlist và field-level action |
| Không kiểm workflow state | Approve/undo lặp trái quy trình | State machine và transaction |
| Không áp SoD | Người tạo tự duyệt | Điều kiện tách nhiệm vụ theo resource |
| Cache quyền quá lâu | Mover/Leaver còn quyền cũ | TTL, invalidation và lifecycle checks |
| Chỉ thu hồi tại IdP | API token/local account vẫn thực thi action | Deprovision + session/token revoke + readback |
| Trường hợp PDP lỗi được permit | Thực thi action khi thiếu quyết định đáng tin | Deny-safe theo risk policy |
| Action mới tự vào role cũ | Phát sinh quyền không được duyệt | Default deny và review policy |
| Quyền admin dùng chung cho nhiều người | Mất khả năng quy trách nhiệm | Danh tính riêng, PAM/JIT và audit |
| Audit không có resource/action | Không thể giải thích quyết định sau sự cố | Log subject-action-resource-policy |

**Không đánh giá authorization chỉ từ cấu hình IdP.** Một ứng dụng có SSO tốt nhưng thiếu kiểm tra object/action ở backend vẫn có thể chứa lỗ hổng nghiêm trọng.

## 24. Kiểm toán và giám sát các action

Một bản ghi audit tốt cần cho phép trả lời:

> Ai yêu cầu thực hiện action nào, trên resource nào, vào lúc nào, theo policy nào, hệ thống quyết định gì, và thao tác thực tế có thành công hay không?

### Ví dụ log metadata, không chứa token thô

~~~json
{
  "eventId": "authz-20261123-0189",
  "correlationId": "req-7af20",
  "subjectId": "person-2046",
  "tenantId": "org-vn",
  "action": "invoice.approve",
  "resourceType": "Invoice",
  "resourceId": "INV-873",
  "decision": "DENY",
  "reasonCode": "SELF_APPROVAL_FORBIDDEN",
  "policyVersion": "invoice-authz-v6",
  "authenticationAssurance": "PHISHING_RESISTANT_MFA",
  "decisionAt": "2026-11-23T09:16:00+07:00",
  "execution": "NOT_EXECUTED"
}
~~~

Đây là **schema minh họa**, không phải định dạng bắt buộc. Dữ liệu audit có thể chứa thông tin nhạy cảm; chỉ lưu mức cần thiết và phân quyền truy cập, thời hạn lưu trữ theo quy định. **Không log access token, password, private key hoặc payload nghiệp vụ nhạy cảm không cần cho việc điều tra**.

### Phân biệt quyết định và thực thi

- **Decision = PERMIT:** chính sách cho phép yêu cầu theo dữ liệu đã đánh giá.
- **Execution = FAILED:** thao tác thật có thể vẫn lỗi do database, timeout hoặc điều kiện nghiệp vụ.
- **Decision = DENY:** phải không có tác dụng phụ từ action được từ chối.
- **Policy engine error:** cần có trạng thái riêng, tránh ghi thành permit hoặc business success.

### Các chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| **Denied actions by reason** | Tỷ lệ từ chối theo action, policy, tenant, lý do |
| **Unexpected permit findings** | Trường hợp policy cho phép action vượt desired quyền |
| **Privileged action usage** | Tần suất deploy, assignRole, export, reset, impersonate |
| **Separation-of-duties violations** | Yêu cầu tự duyệt hoặc xung đột phê duyệt |
| **Policy decision latency** | Độ trễ PDP/PEP và rủi ro timeout |
| **Policy coverage** | Action/API/resource đã có kiểm tra quyết định hay chưa |
| **Stale-role access** | Action vẫn được thực thi sau khi role/quan hệ đã thay đổi |
| **Leaver action-block latency** | Thời gian từ effectiveAt đến khi action trái thẩm quyền bị chặn |
| **JIT privilege expiration** | Quyền tạm đã được gỡ đúng hạn chưa |
| **Orphan privilege findings** | Quyền không có owner/phê duyệt còn hiệu lực |
| **Unauthorized export attempts** | Dấu hiệu xuất dữ liệu ngoài scope |
| **Reconciliation coverage** | Tỷ lệ quyền thực tế có thể đọc/đối chiếu |

Một chỉ số **0 lượt bị từ chối** không tự chứng minh an toàn; có thể policy không được gọi hoặc logging chưa bao phủ. Cần theo dõi **coverage của điểm thực thi** và có kiểm thử chủ động.

## 25. Tình huống xuyên suốt: Joiner → Mover → Leaver

Giả sử **Minh** gia nhập tổ chức với vai trò Sales, chuyển sang Finance rồi nghỉ việc. Hệ thống có IdP SSO, SCIM provisioning cho CRM và ứng dụng hóa đơn.

### Giai đoạn 1 — Joiner

HRIS xác minh danh tính và ngày bắt đầu, IAM/IGA tạo account IdP và đăng ký MFA theo chính sách. SCIM tạo User trong CRM, gán nhóm Sales-Reader. Action **customer.read** chỉ được phép với khách hàng thuộc đơn vị Sales; action **customer.export** chưa được cấp vì yêu cầu phê duyệt riêng.

Minh đăng nhập SSO thành công nhưng thử gọi **POST /customers/export**. API kiểm action **customer.export** và từ chối. Trải nghiệm đăng nhập không có quyền vượt role baseline.

### Giai đoạn 2 — Mover

Minh chuyển sang Finance. IAM nhận sự kiện Mover mới, gỡ quyền **customer.read** ngoài phạm vi, cấp quyền **invoice.read** theo role mới, và cho phép **invoice.approve** chỉ sau phê duyệt cùng điều kiện SoD.

Một access token từ trước vẫn có claim nhóm Sales. Nếu API CRM chỉ tin token cũ đến khi hết hạn, Minh có thể còn **customer.read** trái policy. Tổ chức xử lý bằng kiểm tra lifecycle/role hiện hành và cơ chế thu hồi/token lifetime phù hợp; reconciliation xác minh action cũ đã bị chặn.

### Giai đoạn 3 — Phê duyệt hóa đơn

Minh xin duyệt hóa đơn **INV-873**. API kiểm **invoice.approve**, tenant, role, trạng thái SUBMITTED, hạn mức, MFA và người tạo. Nếu hóa đơn do chính Minh lập, policy trả **DENY** theo SoD dù Minh có role Finance-Approver.

### Giai đoạn 4 — Leaver

Đến ngày nghỉ có hiệu lực, IAM disable IdP, thu hồi phiên/token và deprovision entitlement tại CRM, ứng dụng hóa đơn và hệ thống liên quan. Khi Minh dùng API key cũ, resource server phải từ chối **report.export** nếu quyền không còn hợp lệ. Một tài khoản local legacy chưa bị khóa phải được ghi thành ngoại lệ và xử lý, không coi việc disable IdP là hoàn tất.

### Giai đoạn 5 — Rejoiner

Sau một thời gian, Minh được tuyển lại ở vị trí kiểm toán. Identity record cũ có thể được dùng để liên kết lịch sử theo chính sách nhưng **action Sales/Finance cũ không tự phục hồi**. Quyền mới như **report.read** được tính theo quan hệ mới, không mặc định có **invoice.approve**.

**Bài học:** action quyết định **thao tác thực tế** chứ không chỉ quyền vào ứng dụng. JML phải thay đổi cả việc API có thể thực thi action trên dữ liệu cụ thể ở đúng thời điểm.

## 26. Checklist thiết kế và quản lý Action an toàn

1. **Định nghĩa:** action có tên, ý nghĩa, loại resource, owner và mức rủi ro rõ chưa?
2. **Phân biệt:** đã tách action nghiệp vụ khỏi HTTP method, OAuth scope, role và event chưa?
3. **Granularity:** đã tách read/export, edit/approve, quản trị danh tính/quản trị nghiệp vụ khi khác rủi ro chưa?
4. **Subject:** danh tính và trạng thái lifecycle được lấy từ IdP/nguồn có thẩm quyền, không tin client tự khai chưa?
5. **Resource:** tenant, owner, classification, state đã được đọc/xác minh trước quyết định chưa?
6. **Context:** MFA/step-up, thời hạn, risk, device trust được kiểm tra từ nguồn đáng tin chưa?
7. **Policy:** có deny-by-default, version, phê duyệt và quy tắc xử lý conflict/error rõ chưa?
8. **RBAC/ABAC:** role và attribute được kết hợp với quan hệ và phạm vi resource đúng không?
9. **Object-level:** controller/service có chặn IDOR/BOLA, list/search/export và cross-tenant access không?
10. **Field-level:** profile.update không thể tự sửa roles, account active, tenant hoặc approval state chứ?
11. **Workflow:** approve/publish/pay/rollback có kiểm tra trạng thái, hạn mức và SoD không?
12. **Enforcement:** mọi REST/GraphQL/batch/consumer/admin path đều được bảo vệ ở server không?
13. **OAuth:** API kiểm token/audience/scope nhưng không coi scope là đủ mọi quyền trên object chứ?
14. **Joiner:** action chỉ được cấp khi nguồn, role, phê duyệt và thời điểm có hiệu lực phù hợp?
15. **Mover:** quyền cũ và cache/token của role cũ đã được thu hồi/kiểm tra lại đúng hạn?
16. **Leaver:** IdP, SCIM, local session, API key, token và credential độc lập đã ngừng cho thực thi action không còn được phép?
17. **Non-human:** bot/workload có owner, action tối thiểu và lifecycle riêng, không dùng danh tính nhân viên thay thế?
18. **Privileged access:** action nhạy cảm có JIT, MFA, SoD, approval, audit và giới hạn thời gian khi cần?
19. **Observability:** log được subject, action, resource, policy, decision và outcome mà không lộ secret?
20. **Verification:** đã test negative cases và đối soát trạng thái quyền thực tế sau JML chưa?

### Ghi nhớ

**Action là thao tác nghiệp vụ mà một subject yêu cầu thực hiện trên một resource trong một context.** Authorization phải đánh giá **đúng hành động, đúng đối tượng, đúng thời điểm và đúng chính sách**, thay vì chỉ kiểm tra đăng nhập, role chung, HTTP method hoặc OAuth scope. Trong hệ thống IAM theo **Joiner–Mover–Leaver**, tập action được phép phải được cấp theo vai trò, phê duyệt và quan hệ hiện hành; **được tính lại khi Mover** và **bị ngăn thực thi khi Leaver** ở mọi đường truy cập. Kiểm tra tại **PEP/PDP và tầng nghiệp vụ**, kết hợp RBAC/ABAC/ReBAC, SoD, audit và reconciliation là nền tảng giảm **leo thang đặc quyền, truy cập chéo tài nguyên và quyền truy cập tồn dư**.
