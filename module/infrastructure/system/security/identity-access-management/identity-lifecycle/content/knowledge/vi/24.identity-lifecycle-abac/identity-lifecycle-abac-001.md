# ABAC là gì? Kiểm soát truy cập theo thuộc tính trong IAM Identity Lifecycle

> **Chương: ABAC.** **Attribute-Based Access Control (ABAC)** là mô hình kiểm soát truy cập trong đó quyết định cho phép hoặc từ chối một hành động được tính từ **thuộc tính của chủ thể, tài nguyên, hành động và bối cảnh**, theo những chính sách được tổ chức quản trị. ABAC đặc biệt hữu ích trong **quản lý vòng đời danh tính (Identity and Access Management — IAM)**: một người có thể đổi phòng ban, vai trò, dự án, tenant hoặc tình trạng làm việc theo mô hình **Joiner–Mover–Leaver**; quyền truy cập phải thay đổi theo những dữ liệu đó, không phụ thuộc vào việc tài khoản còn đăng nhập được hay không.

## Mục tiêu học tập

Sau khi hoàn thành bài học, bạn có thể:

1. Phát biểu đúng ABAC là gì, giải thích **subject, resource, action, environment/context attribute** và **policy**.
2. Phân biệt **authentication**, **authorization**, **identity proofing**, **provisioning** và vị trí của ABAC trong IAM.
3. So sánh ABAC với **RBAC**, hiểu vì sao hai mô hình thường được kết hợp chứ không nhất thiết thay thế nhau.
4. Diễn giải một luồng đánh giá ABAC bằng **PEP, PDP, PIP, PAP**, với kết quả Permit/Deny và xử lý dữ liệu không đủ tin cậy.
5. Xây dựng quy tắc minh họa cho truy cập theo **tenant, department, chủ sở hữu tài nguyên, mức nhạy cảm, thời hạn và mức bảo đảm đăng nhập**.
6. Liên hệ nguồn dữ liệu **HR–IAM–IdP–SSO–SCIM**, trạng thái **Joiner–Mover–Leaver** và nguy cơ dùng thuộc tính đã lỗi thời.
7. Nhận diện cách ABAC áp dụng với tài khoản dịch vụ, quyền đặc quyền, kiểm thử, kiểm toán và giảm **quyền truy cập tồn dư**.

## 1. Bài toán dẫn nhập: đăng nhập hợp lệ nhưng chưa chắc có quyền

Giả sử một hệ thống quản lý tài liệu của doanh nghiệp có:

- **Lan** là nhân viên phòng Tài chính, được xem báo cáo nội bộ của **tenant B**.
- **Minh** là nhân viên phòng Hỗ trợ khách hàng, thuộc cùng tenant B.
- **Chi** là nhân viên Tài chính nhưng thuộc **tenant A**.
- **Báo cáo R-105** thuộc tenant B, phân loại **CONFIDENTIAL** và chỉ được đọc bởi người có phạm vi công việc phù hợp.

Cả Lan, Minh và Chi đều có thể đăng nhập thành công qua **SSO**. Tuy nhiên, một hệ thống an toàn có thể ra quyết định:

| Yêu cầu | Kết quả mong muốn | Tại sao? |
| --- | --- | --- |
| Lan đọc R-105, có quyền Tài chính, đúng tenant và đủ mức xác thực. | **Permit** | Đủ điều kiện theo chính sách. |
| Minh đọc R-105, không có quyền Tài chính. | **Deny** | Sai chức năng công việc. |
| Chi đọc R-105, thuộc tenant A. | **Deny** | Không vượt ranh giới tenant. |
| Lan xuất toàn bộ báo cáo nhưng chỉ có quyền đọc. | **Deny** | Hành động export khác action read. |
| Lan đã nghỉ việc nhưng còn cookie session. | **Deny** | Trạng thái vòng đời không còn đủ điều kiện truy cập. |
| Dịch vụ không đọc được tenant của R-105. | **Không cho truy cập cho tới khi có căn cứ hợp lệ** | Không được đoán tài nguyên cùng tenant. |

Nếu chỉ có câu hỏi “User có đăng nhập không?”, hệ thống sẽ không phân biệt được các tình huống trên. **ABAC trả lời câu hỏi chi tiết hơn:** “Chủ thể này có được thực hiện hành động này trên tài nguyên này, với các thuộc tính và điều kiện hiện tại hay không?”

## 2. Định nghĩa ABAC và công thức tư duy

ABAC là cách biểu đạt và đánh giá chính sách ủy quyền bằng các **thuộc tính (attributes)**. Thuộc tính là thông tin có ý nghĩa về một đối tượng hoặc bối cảnh; ví dụ:

- Người dùng có **department=FINANCE** và **lifecycleStatus=ACTIVE**.
- Tài liệu có **tenantId=tenant-b** và **classification=CONFIDENTIAL**.
- Hành động được yêu cầu là **document.read** hoặc **document.export**.
- Phiên hiện tại có **authenticationAssurance** phù hợp và thời điểm truy cập nằm trong giới hạn dự án.

Một mô hình khái niệm:

~~~text
decision = evaluate(
    policy,
    subjectAttributes,
    actionAttributes,
    resourceAttributes,
    environmentAttributes
)

if decision == PERMIT and all required enforcement conditions hold:
    perform only the authorized operation
else:
    do not perform the protected operation
~~~

Đây là **công thức tư duy**, không phải API hoặc thuật toán bắt buộc của một tiêu chuẩn ABAC.

### Bốn nhóm thuộc tính thường dùng

| Nhóm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Subject attributes** | Ai đang yêu cầu và đang ở trạng thái nào? | identityId, department, tenantId, employmentStatus, approvedProjects, businessRole. |
| **Resource/object attributes** | Đối tượng được yêu cầu có đặc điểm gì? | document.tenantId, ownerId, projectId, classification, retentionState. |
| **Action attributes** | Đang muốn thực hiện thao tác nào? | read, edit, export, approve, delete, assignRole. |
| **Environment/context attributes** | Yêu cầu xảy ra trong hoàn cảnh nào? | requestedAt, mức xác thực của session, môi trường production/staging, trạng thái sự cố. |

**Policy** là quy tắc phối hợp các thuộc tính để ra quyết định. ABAC không có nghĩa chỉ cần gắn vài nhãn vào User là đủ: hệ thống phải biết **nguồn thuộc tính nào đáng tin**, cách so sánh các giá trị, thời điểm hiệu lực và nơi thực thi kết quả.

### Ví dụ chính sách đơn giản

~~~text
PERMIT document.read KHI
    subject.lifecycleStatus == ACTIVE
    AND subject.department == FINANCE
    AND subject.tenantId == document.tenantId
    AND "finance.read" thuộc subject.approvedPermissions
    AND document.classification <= subject.clearanceLevel
    AND session.assurance đáp ứng chính sách của document

NGƯỢC LẠI: KHÔNG CẤP QUYỀN
~~~

Ký hiệu so sánh mức phân loại chỉ có ý nghĩa khi tổ chức định nghĩa **thứ tự phân cấp rõ ràng**, ví dụ PUBLIC = 0, INTERNAL = 1, CONFIDENTIAL = 2, RESTRICTED = 3. Không được lấy thứ tự chữ cái của chuỗi làm thứ tự độ nhạy.

**ABAC không nhất thiết là “mọi policy đều động theo từng giây”.** Thuộc tính có thể lấy từ cơ sở dữ liệu, cache hoặc token, và quyền chỉ chính xác trong giới hạn độ mới mà kiến trúc bảo đảm.

## 3. Phân biệt ABAC với Authentication và Provisioning

Trong IAM, các thành phần cộng tác với nhau nhưng không đồng nghĩa:

| Hoạt động | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Identity proofing** | Danh tính khai báo có được xác minh và liên kết đúng người không? | Kiểm tra nhân viên mới trước khi cấp phương thức xác thực. |
| **Authentication** | Người/thiết bị có chứng minh quyền kiểm soát authenticator không? | Đăng nhập bằng passkey hoặc mật khẩu và MFA. |
| **Authorization (ABAC/RBAC)** | Chủ thể được thực hiện action nào trên resource nào? | Lan được đọc báo cáo tenant B nhưng không được export. |
| **Provisioning** | Account, Group và entitlement ở đích đã được tạo/cập nhật/thu hồi chưa? | SCIM thêm User vào Group FinanceReader. |
| **Access review** | Quyền đang có còn hợp lệ về nghiệp vụ không? | Người quản lý xác nhận một quyền dự án còn cần thiết. |
| **Reconciliation** | Quyền/trạng thái thực tế ở các đích có khớp desired state không? | Kiểm tra Group cũ vẫn còn sau Mover. |

**SSO thành công chỉ là đầu vào cho authorization.** Một ID token hoặc SAML assertion có thể cung cấp danh tính đã xác thực; điều đó không tự cho phép người dùng đọc mọi tài liệu. ABAC vẫn phải xét hành động, tài nguyên, tenant, trạng thái vòng đời và các điều kiện khác.

Ngược lại, một **SCIM Group** đã được cập nhật thành công không chứng minh các token/phiên hoặc quyền cục bộ ở ứng dụng đã hết hiệu lực. Cần kiểm tra thực tế ở điểm truy cập.

## 4. ABAC so với RBAC

**Role-Based Access Control (RBAC)** gán quyền theo vai trò, ví dụ FinanceViewer, SupportAgent, IdentityOperator. **ABAC** mô tả điều kiện truy cập bằng thuộc tính; role vẫn có thể là **một thuộc tính** trong chính sách ABAC.

### Ví dụ cùng một bài toán

RBAC thuần:

~~~text
PERMIT report.read nếu user có role FinanceViewer
~~~

ABAC kết hợp role và các điều kiện:

~~~text
PERMIT report.read nếu
    user có role FinanceViewer
    AND user.lifecycleStatus == ACTIVE
    AND user.tenantId == report.tenantId
    AND report.projectId thuộc user.approvedProjectIds
    AND report.classification <= user.clearanceLevel
~~~

Trong thực tế, **RBAC cũng có thể được triển khai kèm các điều kiện bổ sung**; bảng so sánh dưới đây mô tả xu hướng thiết kế, không phải ranh giới tuyệt đối giữa sản phẩm.

| Tiêu chí | RBAC | ABAC |
| --- | --- | --- |
| Căn cứ chính | Vai trò được gán. | Thuộc tính của subject, resource, action, context. |
| Quyền theo tenant/project cụ thể | Có thể phải tạo role riêng hoặc bổ sung điều kiện. | Diễn đạt trực tiếp bằng quan hệ giữa thuộc tính. |
| Thay đổi theo trạng thái nhân sự | Thường cập nhật role/membership. | Có thể đưa lifecycleStatus và effectiveAt vào rule. |
| Khả năng giải thích | Dễ nói “User có role nào”. | Cần giải thích rule, giá trị thuộc tính và nguồn dữ liệu. |
| Độ phức tạp quản trị | Có thể xuất hiện **role explosion** nếu nhiều tổ hợp phạm vi. | Có thể xuất hiện **policy/attribute complexity** nếu nguồn, schema và rule không được quản trị. |
| Nhu cầu dữ liệu hiện hành | Role/membership phải đúng. | Thuộc tính và quan hệ phải đúng, đủ mới và đáng tin. |
| Tình huống phù hợp | Quyền nền theo chức năng, hệ thống ít biến số. | Quyền theo tài nguyên, tenant, dữ liệu, ngữ cảnh thay đổi. |

### Vì sao hai mô hình thường bổ trợ?

Doanh nghiệp có thể cấp **role FinanceViewer** qua IGA và dùng ABAC để giới hạn:

- FinanceViewer chỉ đọc tài liệu **đúng tenant**.
- Chỉ đọc báo cáo của **project đã được phê duyệt**.
- Chỉ truy cập dữ liệu **phù hợp mức bảo mật**.
- Chỉ thực hiện thao tác nhạy cảm khi **MFA/assurance** đáp ứng chính sách.
- Mất quyền khi **Leaver** có hiệu lực, dù role còn ở một ứng dụng.

Vì vậy, câu hỏi “Nên chọn RBAC hay ABAC?” không phải lúc nào cũng có một lựa chọn duy nhất. Với vòng đời danh tính, thiết kế thường sử dụng **role làm một nhóm điều kiện ổn định và attribute để kiểm soát phạm vi/ngoại lệ động**.

## 5. Kiến trúc đánh giá ABAC: PEP, PDP, PAP và PIP

Mô hình kiến trúc phổ biến chia trách nhiệm như sau:

| Thành phần | Vai trò | Trong một hệ thống ứng dụng |
| --- | --- | --- |
| **Policy Enforcement Point (PEP)** | Chặn/cho thực hiện hành động theo quyết định. | Middleware API, API gateway, service hoặc truy vấn dữ liệu. |
| **Policy Decision Point (PDP)** | Đánh giá rule ABAC và trả quyết định. | Policy service hoặc thư viện thực thi policy trong ứng dụng. |
| **Policy Administration Point (PAP)** | Tạo, duyệt, sửa, phiên bản và triển khai chính sách. | Quy trình quản trị policy qua version control/IGA/security review. |
| **Policy Information Point (PIP)** | Cung cấp thuộc tính cho PDP. | IAM identity store, HR projection, resource database, IdP claims, entitlement store. |

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant PEP as API / PEP
    participant PDP as ABAC / PDP
    participant PIP as PIP / nguồn thuộc tính
    participant DB as Resource DB
    U->>PEP: GET /documents/R-105
    PEP->>DB: Lấy tài liệu và tenant/classification đáng tin
    DB-->>PEP: Resource metadata
    PEP->>PDP: subject + action + resource + context
    PDP->>PIP: Đọc lifecycle, role, project, assurance
    PIP-->>PDP: Thuộc tính, version, thời điểm quan sát
    PDP-->>PEP: Permit / Deny / không thể quyết định
    alt Permit hợp lệ
        PEP->>DB: Đọc dữ liệu theo phạm vi cho phép
        DB-->>PEP: Dữ liệu phù hợp
        PEP-->>U: Response có kiểm soát
    else Deny hoặc không đủ cơ sở Permit
        PEP-->>U: Không tiết lộ tài nguyên
    end
~~~

Một triển khai **không bắt buộc bốn microservice riêng**. PDP có thể là thư viện cục bộ và PIP có thể là cache có kiểm soát. Nhưng cần tách rõ logic:

- **Ai quyết định?** PDP.
- **Ai chịu trách nhiệm ngăn thao tác trái phép?** PEP.
- **Ai quản lý chính sách và phê duyệt?** PAP.
- **Dữ liệu nào được xem là sự thật và được lấy từ đâu?** PIP/nguồn có thẩm quyền.

**Ẩn nút trên giao diện không thay thế PEP.** Nếu API vẫn cho gọi trực tiếp `DELETE /documents/R-105`, ABAC tại frontend không bảo vệ được tài nguyên.

## 6. Một chính sách ABAC được viết như thế nào?

Về mặt tư duy, một chính sách có thể gồm:

1. **Target:** nhóm request mà policy áp dụng, ví dụ hành động document.read trên tài nguyên Document.
2. **Condition:** các phép so sánh thuộc tính và quan hệ, ví dụ subject.tenantId == resource.tenantId.
3. **Effect:** kết quả dự định, ví dụ Permit hoặc Deny.
4. **Obligations/advice (nếu hỗ trợ):** yêu cầu bổ sung khi thực thi, ví dụ ghi nhật ký bắt buộc hoặc lọc trường dữ liệu.
5. **Priority/combining:** cách gộp với policy khác khi có nhiều kết quả.

### Ví dụ policy minh họa bằng YAML

Đây là **định dạng tự đặt cho bài học**, không phải schema SCIM, OAuth, XACML, Cedar hay Rego:

~~~yaml
policyId: finance-report-read-v1
target:
  resourceType: REPORT
  action: READ
effect: PERMIT
allOf:
  - subject.lifecycleStatus == ACTIVE
  - subject.tenantId == resource.tenantId
  - FINANCE_READER in subject.approvedRoles
  - resource.projectId in subject.approvedProjectIds
  - subject.clearanceRank >= resource.classificationRank
  - context.authenticationAssurance >= resource.requiredAssurance
obligations:
  - AUDIT_ACCESS_TO_CONFIDENTIAL_REPORT
~~~

Các phép so sánh cần được một engine định nghĩa rõ về **kiểu dữ liệu**, **xử lý giá trị thiếu**, **nguồn tin cậy** và **nghĩa của ≥ với mức assurance**. Ví dụ, mức xác thực đôi khi là **các thuộc tính không thể xếp theo một thang số đơn nhất**, nên thực tế có thể cần một predicate như `meetsRequiredAuthenticationProfile(session, resource)` thay vì so thứ tự số.

### Quy tắc từ chối tường minh

~~~text
DENY document.* KHI
    subject.lifecycleStatus == TERMINATED

DENY document.export KHI
    resource.exportRestricted == true
    AND subject.hasExplicitExportApproval == false

DENY invoice.approve KHI
    subject.identityId == invoice.createdByIdentityId
~~~

Ví dụ cuối thể hiện **Segregation of Duties (SoD)**: người tạo hóa đơn không được tự phê duyệt. ABAC có thể diễn đạt quan hệ giữa người và tài nguyên mà không cần tạo role riêng cho từng hóa đơn.

## 7. Permit, Deny, NotApplicable và Indeterminate

Một engine ABAC có thể có nhiều kiểu kết quả; tùy nền tảng, có thể sử dụng boolean đơn giản hoặc trạng thái phong phú hơn.

| Kết quả | Diễn giải | Hành động an toàn tại PEP |
| --- | --- | --- |
| **Permit** | Chính sách có hiệu lực cho phép request với điều kiện đã thỏa. | Chỉ thực thi nếu obligation và điều kiện thực thi còn đạt. |
| **Deny** | Chính sách từ chối request. | Không thực hiện hành động. |
| **NotApplicable** | Không rule nào áp dụng trong phạm vi đang xét. | Dùng **default deny**, không tự cho phép. |
| **Indeterminate** | Không thể đánh giá đúng do thiếu/không tin được thuộc tính hoặc lỗi policy. | Không cấp quyền khi thiếu căn cứ; ghi lỗi và xử lý theo chính sách rủi ro. |

**NotApplicable/Indeterminate** là những thuật ngữ quen thuộc trong các mô hình policy như XACML. Không phải mọi engine đều trả chính xác các giá trị này, nhưng về kiến trúc cần phân biệt **bị từ chối hợp lệ**, **không có quyền** và **không đánh giá được**.

### Default deny

**Default deny (deny by default)** nghĩa là không được thực hiện thao tác khi không có **Permit hợp lệ**. Nhờ vậy, một API mới, một tài nguyên mới hoặc một tenant mới không mặc nhiên được mở cho mọi người.

~~~text
function enforce(decision):
    if decision == PERMIT and mandatoryObligationsSatisfied:
        executeProtectedOperation()
    else:
        blockProtectedOperation()
~~~

**Fail closed** không yêu cầu luôn trả cùng một mã HTTP. Nếu User chưa xác thực có thể trả 401; nếu đã xác thực nhưng thiếu quyền có thể trả 403; nếu PDP tạm mất kết nối có thể trả lỗi dịch vụ. **Điểm bất biến là thao tác bảo vệ không được thực hiện khi chưa đủ cơ sở cho phép**.

### Nếu có nhiều policy cùng áp dụng?

Một policy RBAC cho Permit vì có FinanceReader, trong khi policy lifecycle cho Deny vì User đã Leaver. Hệ thống phải chọn **chiến lược kết hợp** phù hợp, ví dụ deny-overrides hoặc dùng hard guard bắt buộc trước khi đánh giá quyền chức năng.

Không phải mọi nền tảng đều mặc định explicit Deny thắng Permit. **Cần định nghĩa, kiểm thử và quản trị semantics của policy combining**, đặc biệt với SoD, tenant isolation và Leaver.

## 8. Nguồn thuộc tính quyết định chất lượng ABAC

Một quy tắc rất chặt vẫn có thể cấp quyền sai nếu dữ liệu nó nhận đã lỗi thời hoặc thuộc về nhầm identity.

### Nguồn có thẩm quyền theo thuộc tính

| Thuộc tính | Nguồn thường phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| **employmentStatus, startAt, endAt** | HRIS/HCM hoặc nguồn hợp đồng. | Sự kiện JML, thời điểm hiệu lực và version. |
| **department, jobCode, manager** | HR và nguồn tổ chức có thẩm quyền. | Mapping mã, ngày Mover, manager thực tế. |
| **identityId và account mapping** | IAM identity registry. | Tính duy nhất, đúng User/tenant. |
| **businessRole, approvedGrant** | IGA/policy/approver được ủy quyền. | Phê duyệt, SoD, giới hạn thời gian. |
| **subject.tenantId** | IAM và quan hệ thuê bao đã xác minh. | Không lấy từ query parameter do client tự khai. |
| **resource.owner/tenant/classification** | Hệ thống sở hữu tài nguyên. | Thuộc tính đọc từ server-side và đủ mới. |
| **authenticationAssurance** | IdP/session validation có tin cậy. | Đúng issuer, phiên, phương thức và độ mới. |
| **device posture** | Hệ thống quản lý thiết bị/endpoint nếu áp dụng. | Độ tin cậy và tuổi dữ liệu, không tin header tự khai. |
| **workload environment/owner** | Service registry, workload platform. | Nguồn triển khai, project, owner, trust. |

**Không có một hệ thống duy nhất luôn là nguồn chuẩn của mọi thuộc tính.** HR có thể sở hữu department, nhưng ứng dụng tài liệu sở hữu classification của tài liệu và IdP sở hữu authentication context của phiên.

### Field ownership và độ tin cậy

Ví dụ, một request có payload:

~~~json
{
  "subject": {
    "department": "FINANCE",
    "role": "Admin",
    "tenantId": "tenant-b"
  },
  "resourceId": "R-105"
}
~~~

Nếu caller tự điền role hoặc department rồi ứng dụng tin ngay, kẻ tấn công có thể **tự tuyên bố thuộc tính để được Permit**. PEP/PDP cần xác thực subject, lấy vai trò từ nguồn đáng tin và lấy tenant/classification của resource từ datastore được bảo vệ.

### Định danh ổn định và namespace

Một người có thể đồng thời có:

- `HRIS:EMP-2041` tại HR.
- `ID-2041` trong IAM.
- `idp-user-77` tại IdP.
- `scim-user-381` tại ứng dụng SaaS.

Các ID này **không tự bằng nhau**. Muốn dùng attribute của HR để quyết định quyền cho SaaS User, phải có ánh xạ identity/account được xác minh, kết hợp issuer và tenant. Email hoặc displayName có thể đổi, trùng hoặc tái sử dụng; không dùng làm bằng chứng duy nhất để liên kết.

## 9. Chuẩn hóa giá trị và xử lý dữ liệu thiếu

ABAC thường phải kết hợp thuộc tính từ nhiều nguồn. Nếu không chuẩn hóa, cùng một ý nghĩa có thể bị xem là khác nhau; nếu chuẩn hóa sai, thuộc tính không tương đương có thể bị xem là giống nhau.

| Dạng dữ liệu | Ví dụ khác biệt | Cách xử lý |
| --- | --- | --- |
| Mã phòng ban | FINANCE, FIN, 031 | Dùng bảng mapping có phiên bản và owner. |
| Kiểu thời gian | 08:00 +07:00 và 01:00 UTC | So cùng thời điểm; xét hiệu lực nghiệp vụ. |
| Danh sách project | [A, B] và [B, A] | So như tập hợp nếu ngữ nghĩa không phụ thuộc thứ tự. |
| Tenant | tenant-a và tenant-b | Không được quy đổi thành cùng tenant. |
| Mức phân loại | INTERNAL, CONFIDENTIAL | Dùng phân cấp rõ ràng, không so thứ tự chữ cái. |
| Trạng thái lifecycle | TERMINATED, active=false | Áp mapping theo từng ứng dụng; kiểm tra nghĩa thực tế. |
| Định danh manager | HR:EMP-9 và SCIM:U-66 | Resolve cùng identity trước khi so. |
| Trường thiếu | Không trả department | Không tự coi bằng chuỗi rỗng hay department mặc định. |

### Null, absent, empty và unknown

- **Absent:** trường không có trong phản hồi; có thể do projection, schema hoặc quyền đọc.
- **Null:** nguồn thể hiện một giá trị chưa có hoặc trạng thái xóa theo contract.
- **Empty:** chuỗi/tập hợp rỗng, chỉ có nghĩa khi phép đọc đủ thông tin.
- **Unknown:** chưa thể xác định giá trị vì lỗi hoặc nguồn chưa đồng bộ.
- **Stale:** giá trị có vẻ hợp lệ nhưng không còn đủ mới cho quyết định.

Với những thuộc tính bắt buộc như `resource.tenantId`, không nên biến **unknown** thành `tenant-b` chỉ để giao diện hoạt động. Nếu không có căn cứ để so tenant, quyết định an toàn là **không cho phép**, đồng thời báo lỗi dữ liệu để phục hồi.

### Thời điểm dữ liệu quan trọng như nội dung dữ liệu

Tối thiểu nên biết:

~~~text
sourceVersion     : Phiên bản cập nhật từ nguồn có thẩm quyền
sourceEffectiveAt : Thời điểm thay đổi có hiệu lực
observedAt        : Thời điểm PIP/IdP/app đọc được giá trị
policyVersion     : Phiên bản policy được đánh giá
evaluatedAt       : Thời điểm PDP quyết định
~~~

Ví dụ HR phát Mover lúc 09:00, nhưng token của User vẫn mang department=SUPPORT từ 08:00. Chữ ký token hợp lệ chỉ chứng minh nội dung **đã được phát hành bởi nguồn tin cậy vào lúc đó**, không chứng minh department vẫn đúng ở 10:00.

## 10. ABAC trong Joiner–Mover–Leaver

ABAC giúp biểu đạt các điều kiện vòng đời trực tiếp trong quyết định truy cập. Tuy nhiên, việc quyền được cập nhật đủ nhanh còn phụ thuộc quá trình đồng bộ thuộc tính, policy và trạng thái của ứng dụng.

~~~mermaid
flowchart LR
    HR["HR / contract<br/>Joiner–Mover–Leaver"] --> IAM["IAM identity lifecycle<br/>status + role + effectiveAt"]
    IAM --> IDP["IdP/SSO<br/>authentication context"]
    IAM --> SCIM["SCIM provisioning<br/>User/Group"]
    IAM --> PIP["PIP: trusted attributes"]
    IDP --> PIP
    SCIM --> APP["Ứng dụng / resource"]
    PIP --> PDP["PDP: ABAC policy"]
    APP --> PEP["PEP: kiểm tra action/resource"]
    PEP <--> PDP
    PEP --> API["Thực thi hoặc từ chối"]
~~~

### Joiner: account tồn tại chưa đủ điều kiện Permit

Một User có thể được tạo ở IdP và SaaS trước ngày đi làm để chuẩn bị thiết bị và onboarding. Nhưng **pre-provisioning không nên tự mở quyền nghiệp vụ**.

Ví dụ:

~~~text
PERMIT onboarding.registerAuthenticator KHI
    subject.lifecycleStatus == PENDING_ACTIVATION
    AND onboardingWindowIsApproved
    AND requiredIdentityBindingIsVerified

PERMIT business.report.read KHI
    subject.lifecycleStatus == ACTIVE
    AND now >= subject.startAt
    AND otherResourceAndRoleConditionsHold
~~~

Hai policy phải có phạm vi action/resource riêng, để quyền onboarding không trở thành quyền xem dữ liệu doanh nghiệp. Quy trình thực tế có thể yêu cầu proofing, MFA và phê duyệt trước khi tài khoản được ACTIVE.

### Mover: cập nhật thuộc tính phải thay đổi quyền

Lan chuyển từ Support sang Finance. Trước khi chuyển, Lan được xem ticket hỗ trợ. Sau khi chuyển, quyền này phải giảm hoặc mất và các quyền Tài chính mới chỉ được cấp nếu đủ phê duyệt.

| Trạng thái | Thuộc tính | Yêu cầu | Quyết định mong muốn |
| --- | --- | --- | --- |
| Trước Mover | department=SUPPORT, ACTIVE | ticket.read trong project được phân công. | Permit khi đủ điều kiện. |
| Sau Mover | department=FINANCE, ACTIVE | ticket.read dựa trên quyền Support cũ. | Deny nếu quyền cũ đã hết hiệu lực. |
| Sau Mover | department=FINANCE, ACTIVE | report.read tenant phù hợp. | Permit nếu role/approval mới có hiệu lực. |
| Sau Mover | department=FINANCE, ACTIVE | payroll.export không có approval. | Deny. |

**Không chỉ thêm quyền mới.** Hệ thống phải thu hồi quyền cũ, làm mới thuộc tính và kiểm tra phiên/token/cache còn giữ kết quả trước Mover hay không. Nếu User có role thuộc tính chính xác nhưng application cache vẫn dùng nhóm cũ, đó là **quyền truy cập tồn dư**.

### Leaver: chặn truy cập dù credential còn hiệu lực

Leaver phải ngăn chủ thể tiếp tục thực hiện hành động không còn được phép, ngay cả khi ứng dụng vẫn có session hoặc access token được cấp trước khi nghỉ việc.

Một hard guard mang tính khái niệm:

~~~text
DENY businessResources.* KHI
    subject.lifecycleStatus == TERMINATED
    AND currentTime >= leaverEffectiveAt
~~~

Với trường hợp **lifecycleStatus=TERMINATED**, chính sách có thể đơn giản từ chối mọi truy cập nghiệp vụ. Nếu cần giữ một vài luồng theo quy định (ví dụ truy xuất hồ sơ cá nhân sau nghỉ việc), chúng cần **policy và kênh riêng được phê duyệt**, không phải một ngoại lệ mơ hồ cho toàn bộ ứng dụng.

**Cảnh báo:** Chỉ thêm rule Deny tại PDP không tự vô hiệu hóa mọi access token JWT đã phát. API phải thực sự thực thi rule hiện hành hoặc có cơ chế thu hồi/giới hạn token phù hợp. Các session/credential cục bộ cũng cần được kiểm soát độc lập.

### Rehire, suspension và nhà thầu

- **Rehire:** không tự tái cấp mọi role/quyền dựa trên account cũ; kiểm tra đúng identity, proofing, hợp đồng và project hiện tại.
- **Suspension:** chính sách xác định phạm vi Deny tạm thời và điều kiện khôi phục; không mặc nhiên giống Leaver vĩnh viễn.
- **Contractor:** sử dụng endAt, sponsor, project, loại hợp đồng và approval; không để quyền kéo dài chỉ vì sự kiện hết hợp đồng bị mất.
- **Tài khoản đặc quyền:** hạn JIT/PAM và session assurance phải được kiểm tra bên cạnh trạng thái ACTIVE.

## 11. ABAC kết hợp IdP, SSO và SCIM ra sao?

### IdP/SSO cung cấp danh tính và ngữ cảnh xác thực

Trong OIDC, ứng dụng có thể nhận **ID token** để xác thực danh tính theo giao thức. Với SAML, ứng dụng nhận assertion được xác minh. Một số claim có thể chứa department hoặc Group, nhưng không nên mặc định:

- Claim trong token là giá trị đang **hiện hành** sau Mover/Leaver.
- Mọi thuộc tính ứng dụng cần đều được IdP phát.
- Sự hiện diện của `mfa=true` đồng nghĩa phương thức đã đạt mọi yêu cầu chống phishing.
- Một ID token có thể dùng như access token để gọi API bất kỳ.

**Authentication context** chỉ là một nhóm thuộc tính đầu vào. Tài nguyên và quyết định quyền vẫn do ứng dụng/API chịu trách nhiệm.

### SCIM thay đổi account/Group, ABAC đánh giá quyền thực tế

SCIM cung cấp User/Group provisioning. Ví dụ, sau Mover, connector gỡ Lan khỏi Group SupportAdmin ở một SaaS. ABAC có thể kiểm tra thuộc tính Group/role hiện hành, nhưng:

- SaaS có thể có **role trực tiếp** nằm ngoài SCIM.
- Session có thể chứa claims từ trước thay đổi.
- Resource Server có thể dùng **cache** hoặc quyết định Permit đã lưu.
- SCIM `active=false` có thể không rút ngay mọi access token/PAT.

Muốn giảm residual access, cần phối hợp **provisioning + policy enforcement + session/token controls + reconciliation**. Không xem lệnh SCIM thành công là bằng chứng mọi yêu cầu API sẽ bị Deny.

### Một nguyên tắc cho các hệ thống phân tán

~~~text
HR/IGA determines:  người này nên có quyền gì, từ khi nào?
IdP/SSO verifies:   chủ thể đang xác thực là ai, mức bảo đảm nào?
SCIM provisions:   tài khoản/Group ở ứng dụng đã được cập nhật chưa?
ABAC PDP decides:  subject có được thực hiện action trên resource hiện tại?
PEP enforces:      thao tác có được chặn hoặc cho phép đúng không?
Reconciliation:    quyền thực tế có khớp desired state và chính sách không?
~~~

## 12. Ví dụ xuyên suốt: tài liệu tài chính nhiều tenant

Thiết kế một hệ thống có các loại tài nguyên:

~~~text
Document:
    id
    tenantId
    projectId
    classificationRank
    ownerIdentityId
    exportRestricted

Subject:
    identityId
    lifecycleStatus
    tenantId
    approvedProjectIds
    effectivePermissions
    clearanceRank

Context:
    authenticationProfile
    sessionAge
    requestTime
~~~

### Chính sách đọc tài liệu

~~~text
PERMIT document.read KHI
    subject.lifecycleStatus == ACTIVE
    AND "document.read" in subject.effectivePermissions
    AND subject.tenantId == document.tenantId
    AND document.projectId in subject.approvedProjectIds
    AND subject.clearanceRank >= document.classificationRank
    AND authenticationProfileMeetsPolicy(context, document)
~~~

### Chính sách xuất dữ liệu

~~~text
PERMIT document.export KHI
    tất cả điều kiện đọc tài liệu đã đạt
    AND "document.export" in subject.effectivePermissions
    AND document.exportRestricted == false
    AND exportApprovalIsActive(subject, document, requestTime)
~~~

### Chính sách chặn độc lập

~~~text
DENY document.* KHI
    subject.lifecycleStatus in [SUSPENDED, TERMINATED]

DENY document.* KHI
    resource.tenantId không xác minh được
    OR subject.tenantId không xác minh được
~~~

Ví dụ cuối biểu đạt ý tưởng **không cấp quyền nếu không đủ dữ liệu**, không nhất thiết phải hiện thực hóa bằng một rule Deny thay cho kết quả lỗi/Indeterminate. Thiết kế thực phải dùng đúng semantics của policy engine.

### Bảng quyết định thử nghiệm

| Subject | Document | Action | Điều kiện nổi bật | Kết quả |
| --- | --- | --- | --- | --- |
| Lan, ACTIVE, tenant-b, FINANCE | R-105, tenant-b, project được duyệt | read | Đủ role, clearance và assurance | Permit. |
| Lan, ACTIVE, tenant-b | R-106, tenant-a | read | Sai tenant | Deny. |
| Minh, ACTIVE, tenant-b, SUPPORT | R-105, project Finance | read | Không có quyền hoặc project phù hợp | Deny. |
| Lan, ACTIVE | R-105, exportRestricted=true | export | Rule export cấm | Deny. |
| Lan, TERMINATED | R-105 | read | Lifecycle guard | Deny. |
| Lan, ACTIVE | R-105 không đọc được tenantId | read | Resource attribute không xác minh được | Không cấp quyền, ghi nhận lỗi. |

**Bài học cốt lõi:** cùng một User, cùng một resource nhưng **action khác**, **thuộc tính khác** hoặc **thời điểm khác** có thể dẫn tới quyết định khác.

## 13. Pseudocode thực thi ABAC tại API

Một ví dụ dành cho ứng dụng backend, **không phải mã production**:

~~~text
handleDocumentRequest(request):
    authn = validateAuthentication(request)
    if not authn.valid:
        return UNAUTHENTICATED

    subject = resolveIamIdentity(
        issuer = authn.issuer,
        subjectId = authn.subject,
        tenant = authn.tenant
    )
    if subject is unresolved:
        return DENY_AND_REVIEW

    document = readDocumentMetadataFromTrustedStore(request.documentId)
    if document is absent:
        return NOT_FOUND

    action = mapEndpointToBusinessAction(request.method, request.path)
    attributes = loadTrustedPolicyAttributes(
        subject,
        document,
        authn,
        requiredFreshness = riskPolicy(document, action)
    )

    if attributes.incomplete or attributes.staleBeyondPolicy:
        audit("ABAC_UNDECIDABLE", subject, action, document)
        return BLOCK_WITH_APPROPRIATE_ERROR

    decision = evaluateApprovedPolicies(
        subject = attributes.subject,
        resource = attributes.document,
        action = action,
        context = attributes.context
    )

    if decision != PERMIT:
        audit("ABAC_DENY", subject, action, document)
        return ACCESS_DENIED

    if not enforceMandatoryObligations(decision):
        return ACCESS_DENIED

    return performOperationWithResourceAndTenantChecks(
        subject,
        document,
        action
    )
~~~

### Vì sao phải xác minh tài nguyên tại server?

Một client có thể gọi:

~~~http
GET /api/documents/R-105?tenantId=tenant-b HTTP/1.1
Authorization: Bearer [REDACTED]
~~~

Nếu ứng dụng tin `tenantId` từ query string mà không kiểm tra dữ liệu thật của R-105, người dùng có thể thay đổi ID tài liệu và tự khai tenant để truy cập chéo tenant.

**Cách đúng:** lấy `document.tenantId` từ hệ thống sở hữu tài nguyên, sau đó so với thuộc tính tenant đáng tin của subject và những quan hệ được chính sách cho phép. Đây là một lớp phòng vệ đối với **IDOR/BOLA** (truy cập trực tiếp tài nguyên mà thiếu kiểm tra quyền ở cấp đối tượng).

### Tránh lỗi TOCTOU

**Time-of-check to time-of-use (TOCTOU)** là khoảng cách giữa lúc kiểm tra quyền và lúc thực thi thay đổi. Nếu owner hoặc tenant của tài liệu đổi giữa hai thời điểm, quyết định cũ có thể không còn hợp lệ.

Với thao tác nhạy cảm, cần cân nhắc giao dịch, conditional update hoặc kiểm tra lại các điều kiện trước khi ghi. Không chỉ nhận Permit một lần rồi giữ hiệu lực bất chấp thay đổi trạng thái tài nguyên.

## 14. Cache, session, token và độ trễ cập nhật quyền

ABAC cần dữ liệu, nhưng truy vấn mọi nguồn trung tâm ở mỗi request có thể gây độ trễ. Hệ thống thường dùng **cache**, **token claims** hoặc **bản sao thuộc tính**. Đây là lựa chọn kiến trúc có đánh đổi.

### Các dạng dữ liệu có thể lỗi thời

| Dữ liệu | Vì sao có thể cũ? | Rủi ro |
| --- | --- | --- |
| Department trong ID/access token | Token phát trước Mover. | Quyền theo phòng ban cũ còn được sử dụng. |
| Group ở SaaS | SCIM connector chưa đồng bộ. | Người đã Leaver vẫn nằm trong Group cấp quyền. |
| PDP decision cache | Permit được tính trước khi project/role thay đổi. | Resource vẫn cho truy cập theo quyết định cũ. |
| Device posture | Thiết bị không còn tuân thủ nhưng PIP chưa cập nhật. | Cho phép thao tác dựa trên đánh giá cũ. |
| Resource classification | Tài liệu vừa được nâng từ INTERNAL sang RESTRICTED. | Người không đủ clearance vẫn xem tài liệu. |
| App-local session | RP chưa nhận logout hoặc không kiểm tra quyền hiện hành. | Token/session còn hiệu lực sau Leaver. |

### Biện pháp giảm rủi ro

1. Xác định **mức độ mới cần thiết theo loại tài nguyên/action**.
2. Gắn **TTL, policy version, source version, observedAt** với dữ liệu cache.
3. Có **invalidation** hoặc sự kiện cập nhật khi Mover/Leaver/thu hồi quyền.
4. Với action đặc quyền, cân nhắc kiểm tra trạng thái/policy gần thời điểm thực thi.
5. Không dùng một Permit cũ vô thời hạn chỉ vì PDP hoặc HR projection đang lỗi.
6. Kiểm tra **session/token đã phát**, không coi cập nhật SCIM/IdP là đủ.
7. Đo **residual access** bằng thử nghiệm và readback ở đích.

**Đặt TTL thấp không tự bảo đảm thu hồi tức thời.** Một JWT được Resource Server xác minh hoàn toàn offline vẫn có thể được chấp nhận tới khi hết hạn nếu API không có cơ chế bổ sung để xét Leaver.

### Hành vi khi PDP/PIP mất kết nối

Hệ thống nên trả lỗi hoặc từ chối thao tác khi **không thể chứng minh điều kiện Permit**, đặc biệt với thao tác nhạy cảm. Nếu có một cơ chế break-glass dành cho sự cố production, nó phải là chính sách **được phê duyệt trước**, có phạm vi/hạn, xác thực mạnh và audit độc lập, không phải quy tắc “PDP timeout thì Permit tất cả”.

## 15. ABAC với tài khoản đặc quyền và workload identity

### Privileged access

Đối với quyền quản trị production, một rule có thể cần thêm:

~~~text
PERMIT production.restart KHI
    subject.lifecycleStatus == ACTIVE
    AND subject.hasApprovedPrivilegedGrant
    AND now nằm trong JIT window được phê duyệt
    AND resource.environment == PRODUCTION
    AND subject.tenantId == resource.tenantId
    AND session đáp ứng policy MFA/step-up đặc quyền
~~~

Đây là ví dụ điều kiện, không phải cấu hình cho một PAM cụ thể. **PAM/JIT** có thể quản lý grant ngắn hạn, ghi session và giới hạn thao tác. ABAC giúp kết hợp role admin với môi trường, thời gian, scope và mức bảo đảm; **có role admin không tự khiến mọi production request được Permit**.

### Workload/service account không dùng trực tiếp HR attributes của con người

Một service account có thể dùng OAuth client credentials, mTLS, chứng chỉ hoặc workload federation. Quyết định của ABAC có thể dùng:

| Nhóm thuộc tính | Ví dụ | Lý do |
| --- | --- | --- |
| Subject máy | serviceId=payment-worker | Xác định đúng workload. |
| Trust source | issuer=trusted-cluster-issuer | Chỉ tin danh tính từ môi trường được quản lý. |
| Deployment environment | production / staging | Không cho staging gọi tài nguyên production trái chính sách. |
| Owner | team=PaymentPlatform | Có trách nhiệm quản trị và thu hồi. |
| Scope/audience | billing-api:invoice.create | Giới hạn dịch vụ và thao tác. |
| Resource | queue-payment, tenant-b | Đúng tài nguyên, tenant và project. |
| Lifecycle | workloadStatus=ACTIVE | Từ chối khi workload bị decommission. |

Ví dụ:

~~~text
PERMIT queue.publish KHI
    workload.status == ACTIVE
    AND workload.environment == PRODUCTION
    AND token.audience == "payment-queue"
    AND workload.approvedQueueIds contains queue.id
    AND workload.tenantId == queue.tenantId
~~~

**Một nhân viên nghỉ việc không đồng nghĩa mọi service account họ từng quản lý phải bị xóa ngay.** Cần xác định owner mới, thu hồi credential cá nhân, rotate secret và rà soát scope; nếu chính workload bị ngừng thì chấm dứt trust và quyền máy theo vòng đời riêng.

## 16. Thiết kế ABAC an toàn và dễ vận hành

ABAC có sức biểu đạt mạnh nhưng dễ trở thành hệ thống khó kiểm soát nếu policy và attribute không được quản trị.

### Checklist thiết kế

| Câu hỏi | Cần có câu trả lời |
| --- | --- |
| **Ai sở hữu policy?** | IAM/Security và resource owner có trách nhiệm rõ. |
| **Thuộc tính lấy từ đâu?** | Source of authority theo từng field; nguồn, độ mới, namespace. |
| **Ai được sửa thuộc tính?** | Field ownership và quyền ghi được giới hạn. |
| **Mỗi action có ý nghĩa gì?** | Từ điển action ở mức nghiệp vụ, không dựa tùy tiện vào HTTP verb. |
| **Resource được lấy từ đâu?** | Resource store phía server, đúng tenant và owner. |
| **Có rule mặc định không?** | Không có Permit hợp lệ thì Deny tại PEP. |
| **Xử lý xung đột thế nào?** | Combining semantics, hard guards, SoD được kiểm thử. |
| **Thiếu dữ liệu thì sao?** | Không tự cấp quyền; có error handling và alert. |
| **Thuộc tính thay đổi thì sao?** | Sự kiện cập nhật, cache/version invalidation, đối soát. |
| **Ai kiểm tra sau khi deploy?** | Contract tests, policy tests, audit, access review, runtime monitoring. |
| **Ngoại lệ ra sao?** | Approval, reason, scope, time-to-live, owner và review. |

### Tránh policy quá rộng

Một rule kiểu:

~~~text
PERMIT * KHI subject.department == IT
~~~

có thể vô tình cấp nhiều quyền hơn nhu cầu, đặc biệt khi hành động mới được bổ sung. Thay bằng tập action/resource cụ thể, scope theo tenant/project, mức assurance và thời hạn. **Least privilege** không chỉ là cấp đúng vai trò, mà còn là giới hạn quyền trên đúng dữ liệu và đúng khoảng thời gian.

### Policy phải có phiên bản và thử nghiệm

Quản trị rule tương tự thay đổi phần mềm:

1. Viết policy, nêu ý định và threat model.
2. Xác định owner, nguồn dữ liệu và phạm vi áp dụng.
3. Có bộ test dương/âm và các trường hợp biên.
4. Review tác động tới JML, tenant isolation, SoD và đặc quyền.
5. Triển khai theo phiên bản và quan sát kết quả.
6. Có rollback được kiểm soát; **không khôi phục một policy cho phép quá rộng mà bỏ qua thay đổi rủi ro mới**.
7. Duy trì định kỳ access certification và reconciliation để so chính sách với quyền thực tế.

## 17. Kiểm thử ABAC: chứng minh cả Permit và Deny

Kiểm thử ABAC không nên dừng ở `evaluatePolicy() == Permit`. Phải chứng minh **API thật sự cho hoặc chặn hành động ở cấp tài nguyên**.

### Ma trận kiểm thử

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| ABAC-01 | ACTIVE, đúng role, tenant, project, classification. | Permit đúng action. |
| ABAC-02 | Cùng User nhưng action khác, chưa có quyền. | Deny. |
| ABAC-03 | Cùng role nhưng resource khác tenant. | Deny, không rò rỉ dữ liệu. |
| ABAC-04 | Tài liệu nâng mức nhạy cảm vượt clearance. | Deny sau khi thay đổi có hiệu lực. |
| ABAC-05 | User không thuộc approvedProjectIds. | Deny. |
| ABAC-06 | Session không đáp ứng mức assurance yêu cầu. | Deny hoặc yêu cầu step-up theo chính sách. |
| ABAC-07 | Joiner chưa đến ngày làm nhưng IdP User đã tạo. | Không Permit truy cập nghiệp vụ. |
| ABAC-08 | Mover đổi department và mất quyền cũ. | Action thuộc vai trò cũ bị chặn sau thời hạn chính sách. |
| ABAC-09 | Leaver có session/token cũ. | Không được dùng đường cũ để truy cập trái chính sách. |
| ABAC-10 | PIP không đọc được lifecycleStatus. | Không tự Permit; ghi trạng thái lỗi. |
| ABAC-11 | Resource thiếu tenantId trong nguồn tin cậy. | Không cho phép truy cập chéo tenant bằng cách đoán. |
| ABAC-12 | Client tự khai role=Admin trong request. | Không tin claim từ payload chưa xác thực. |
| ABAC-13 | Owner tài nguyên thay đổi ngay trước thao tác ghi. | Không có TOCTOU bypass. |
| ABAC-14 | Policy Permit và hard Deny cùng áp dụng. | Kết quả đúng combining semantics đã duyệt. |
| ABAC-15 | Tác vụ batch truy cập nhiều object khác nhau. | Kiểm quyền từng tài nguyên/thuật toán lọc đúng. |
| ABAC-16 | Privileged JIT grant đã hết hạn. | Deny hành động admin. |
| ABAC-17 | Workload staging dùng token gọi production. | Deny theo trust/environment. |
| ABAC-18 | Service account bị decommission nhưng credential cũ còn. | Không Permit thao tác sau decommission. |
| ABAC-19 | Cache Permit từ trước Leaver vẫn còn. | Không vượt ranh giới thu hồi được yêu cầu. |
| ABAC-20 | PEP trả 403 nhưng database đã bị sửa. | Test phải **FAIL** vì có side effect trái phép. |

### Given–When–Then minh họa

~~~gherkin
Feature: ABAC respects identity lifecycle and resource attributes

  Scenario: A finance reader accesses an approved report
    Given an ACTIVE finance user belongs to tenant-b
    And report R-105 belongs to tenant-b and an approved project
    And the authentication session meets the report policy
    When the user requests document.read for R-105
    Then the PDP decides Permit
    And the PEP returns only authorized fields

  Scenario: A user cannot read across tenants
    Given an ACTIVE finance user belongs to tenant-b
    And report R-200 belongs to tenant-a
    When the user requests document.read for R-200
    Then no protected content is returned
    And the denial is audited

  Scenario: A former employee cannot reuse stale authorization
    Given a user had a valid application session before leaving
    And an authoritative Leaver event has become effective
    When the user requests a protected resource
    Then access is denied within the documented revocation boundary
    And the test checks the actual resource result
~~~

### Các loại test nên kết hợp

- **Policy unit tests:** kiểm tra từng biểu thức và kết quả khi thuộc tính thiếu.
- **Contract tests:** kiểm tra ánh xạ subject/action/resource/context giữa PEP, PDP và PIP.
- **Integration tests:** dùng nguồn thuộc tính và resource thử thật ở staging.
- **End-to-end tests:** xác minh truy cập trực tiếp từ API hoặc browser, kể cả JML và SSO.
- **Security regression:** IDOR/BOLA, giả mạo tenant, stale role, SoD, token sai audience và local bypass.
- **Resilience tests:** PDP timeout, PIP stale, message JML đến sai thứ tự và lỗi phân tán.

**Kết quả Deny phải được kiểm chứng bằng việc không có thao tác trái phép**, không chỉ bằng status code. Với delete/update, test nên đọc lại datastore; với export, test phải xác minh không có dữ liệu nhạy cảm bị trả ra.

## 18. Kiểm toán và giải thích một quyết định ABAC

Một hệ thống ABAC vận hành tốt cần giải thích được:

1. Request nào được xét, bởi subject nào, cho action và resource nào?
2. Policy và phiên bản nào đang có hiệu lực?
3. Thuộc tính nào đóng vai trò quyết định, được lấy từ nguồn nào và có đủ mới không?
4. Kết quả là Permit, Deny hay không thể xác định?
5. PEP có thực thi đúng kết quả và obligation hay không?
6. Có ảnh hưởng bởi Mover, Leaver, revoke group hoặc token cache không?
7. Ai chịu trách nhiệm khi tìm thấy quyền thừa hoặc lỗi source?

### Ví dụ audit event

Đây là JSON nội bộ minh họa, **không phải định dạng chuẩn của một policy engine**:

~~~json
{
  "eventType": "ABAC_AUTHORIZATION_DECISION",
  "decisionId": "decision-801",
  "identityId": "ID-LAN-2041",
  "action": "document.read",
  "resourceRef": "R-105",
  "tenantId": "tenant-b",
  "policyId": "finance-report-read-v1",
  "policyVersion": 7,
  "lifecycleStatus": "ACTIVE",
  "sourceVersion": 42,
  "decision": "Permit",
  "enforcement": "APPLIED",
  "evaluatedAt": "2026-12-01T09:10:00+07:00",
  "correlationId": "req-8812"
}
~~~

Log cần **đủ dấu vết để truy vết quyết định nhưng không lưu bí mật** như password, access/refresh token, private key hoặc cookie. Thuộc tính HR và phân loại tài liệu có thể nhạy cảm: chỉ lưu dữ liệu cần thiết, kiểm soát quyền xem log và thời hạn lưu giữ.

### Chỉ số vận hành

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Permit/Deny ratio theo action/resource** | Phát hiện policy thay đổi bất thường. |
| **Indeterminate/PIP failure rate** | Biết bao nhiêu request không thể đánh giá an toàn. |
| **Policy coverage** | Tỷ lệ API, batch job và resource path thực sự đi qua PEP. |
| **Stale attribute incidents** | Role/tenant/status cũ dẫn tới quyết định sai. |
| **Residual access after Mover/Leaver** | Quyền cũ vẫn được sử dụng sau thời điểm phải thu hồi. |
| **Cross-tenant authorization violations** | Truy cập chéo tenant trái phạm vi. |
| **Privileged action assurance compliance** | Action nhạy cảm có dùng đúng step-up/MFA/PAM không. |
| **Policy evaluation latency** | Độ trễ của PDP và các nguồn thuộc tính. |
| **Unauthorized side-effect count** | Lỗi PEP thực thi thao tác dù request phải Deny. |
| **Exception overdue count** | Quyền tạm còn hiệu lực sau ngày được phép. |

Tỷ lệ Deny cao không tự chứng minh an toàn: nó có thể cho thấy hệ thống chặn đúng, hoặc policy sai đang chặn người có quyền. Cần phân loại theo nguyên nhân, mức rủi ro, tác động nghiệp vụ và kiểm tra thực tế.

## 19. Những sai lầm thường gặp khi bắt đầu với ABAC

1. **Tin thuộc tính do client tự gửi** như role, department hoặc tenantId mà không xác minh nguồn.
2. **Đồng nhất đăng nhập thành công với Permit.** SSO/MFA là bằng chứng xác thực, không thay quyền resource.
3. **Đặt toàn bộ kiểm tra ở UI**, trong khi endpoint API vẫn thực thi được qua request trực tiếp.
4. **Chỉ kiểm role, không kiểm resource/tenant.** Dẫn tới IDOR/BOLA và truy cập chéo dữ liệu.
5. **Dùng token/claim lỗi thời** sau Mover/Leaver mà không có cơ chế cập nhật/revoke.
6. **Biến thuộc tính unknown thành giá trị mặc định cho phép.** Ví dụ resource không có tenant thì coi cùng tenant.
7. **Viết rule đặc quyền quá rộng** dựa trên `department=IT` hoặc role Admin duy nhất.
8. **Không có field ownership.** HR, IdP và app cùng ghi một thuộc tính rồi cập nhật qua lại.
9. **Không xét hành động cụ thể.** Cho phép đọc nhưng vô tình cho phép export, approve hoặc delete.
10. **Không quản trị policy version và combining.** Một rule Permit mới vô tình bỏ qua hard Deny.
11. **Không kiểm tra hiệu ứng thực thi.** PDP trả Deny nhưng API đã sửa database.
12. **Đánh dấu Leaver hoàn tất chỉ vì SCIM trả thành công.** Session, token, PAT hoặc local permission vẫn hoạt động.

ABAC không khắc phục tự động những lỗi này. Cần một kiến trúc dữ liệu tin cậy, policy quản trị đúng và điểm thực thi bao phủ mọi đường truy cập.

## 20. Tình huống thực hành

### Tình huống A — Tên role đúng nhưng sai tenant

**Bối cảnh:** Lan có role FinanceViewer tại tenant B. Lan sửa ID báo cáo trong URL thành báo cáo của tenant A. API chỉ xét role FinanceViewer.

**Câu hỏi:** ABAC cần thêm điều kiện nào?

**Gợi ý:** Lấy tenantId thực của báo cáo từ dữ liệu server-side, so với phạm vi tenant được cấp cho Lan; không chỉ kiểm tra role hoặc tin tenantId do browser gửi. Nếu quan hệ tenant không hợp lệ thì Deny.

### Tình huống B — Mover nhưng token còn department cũ

**Bối cảnh:** HR chuyển Lan từ Support sang Finance, IdP đã cập nhật hồ sơ. Nhưng access token trong app chứa department=Support và còn hạn.

**Câu hỏi:** Vì sao ABAC vẫn có thể Permit sai?

**Gợi ý:** PDP/PEP đang dùng attribute stale từ token. Cần xác định giới hạn độ mới, cập nhật cache/claim, kiểm tra lifecycle/authorization hiện hành và đo quyền tồn dư ở API.

### Tình huống C — Leaver nhưng ứng dụng vẫn có phiên

**Bối cảnh:** HR xác nhận Minh nghỉ việc. SCIM User active=false, nhưng một session trong ứng dụng còn dùng được.

**Câu hỏi:** Chỉ có rule Deny trong IAM đã đủ chưa?

**Gợi ý:** Chưa nếu app không thực thi rule. Cần PEP kiểm tra trạng thái, xử lý session/token và local access, readback từ đích và test truy cập thực tế theo giới hạn thu hồi.

### Tình huống D — Thiếu classification của tài liệu

**Bối cảnh:** Chính sách chỉ cho đọc tài liệu có classification phù hợp, nhưng API đọc metadata tài liệu bị timeout.

**Câu hỏi:** Có thể coi classification mặc định là PUBLIC không?

**Gợi ý:** Không nếu không có quy tắc đáng tin và được phê duyệt chứng minh điều đó. Cần giữ trạng thái không đủ dữ liệu, không cấp quyền, ghi cảnh báo để khôi phục PIP.

### Tình huống E — Một người được role nhưng thiếu approval

**Bối cảnh:** Nhân viên IT được gán role CloudAdmin từ một script cũ. Nhưng quyền production yêu cầu JIT và phishing-resistant MFA.

**Câu hỏi:** ABAC có thể ngăn gì?

**Gợi ý:** Thêm điều kiện về phê duyệt đặc quyền hiện hành, thời hạn JIT, environment/resource, authentication assurance và trạng thái JML. Không Permit chỉ bằng role.

### Tình huống F — Workload owner nghỉ việc

**Bối cảnh:** Chủ sở hữu service payment-worker nghỉ việc, nhưng workload vẫn phục vụ khách hàng và có token production.

**Câu hỏi:** Có nên Deny mọi request của workload ngay chỉ vì manager HR nghỉ không?

**Gợi ý:** Không suy diễn máy móc. Cần xác định service registry, owner mới, trust và vòng đời workload; rotate credential mà người nghỉ việc biết, giảm scope và thu hồi khi dịch vụ thực sự không còn được phê duyệt.

### Tình huống G — API trả 403 nhưng cập nhật đã diễn ra

**Bối cảnh:** Người không được quyền sửa hồ sơ nhận HTTP 403, song dữ liệu trong database đã thay đổi.

**Câu hỏi:** Kiểm soát đang hỏng ở đâu?

**Gợi ý:** PEP thực thi quyết định quá muộn hoặc transaction không chặn side effect. Test authorization phải đọc lại dữ liệu, sửa thứ tự kiểm tra và bảo đảm quyền tại thời điểm ghi.

## 21. Câu hỏi tự kiểm tra

**1. ABAC là viết tắt của gì?**

Attribute-Based Access Control — kiểm soát truy cập dựa trên thuộc tính và chính sách.

**2. Bốn nhóm thuộc tính thường xuất hiện trong một quyết định ABAC là gì?**

Thuộc tính **subject, resource/object, action và environment/context**.

**3. ABAC có thay thế hoàn toàn RBAC không?**

Không bắt buộc. Role có thể là một thuộc tính trong ABAC; RBAC và ABAC thường bổ trợ để kiểm soát chức năng và phạm vi.

**4. Nếu người dùng đã đăng nhập thành công bằng MFA, có mặc nhiên được đọc dữ liệu của tenant khác không?**

Không. Authentication và authorization khác nhau; ABAC cần kiểm tra tenant/resource/action và các điều kiện của chính sách.

**5. Vì sao không thể lấy `department` trực tiếp từ JSON request của client để Permit?**

Vì client có thể giả mạo thuộc tính. PDP phải nhận dữ liệu từ nguồn có thẩm quyền hoặc claim đáng tin đã được kiểm chứng.

**6. PDP trả Permit nhưng API không thực thi nghĩa vụ bắt buộc thì có nên cho tiếp tục không?**

Không tự bỏ obligation bắt buộc. PEP phải bảo đảm các điều kiện thực thi trước khi cho phép thao tác.

**7. Khi không đọc được resource.tenantId, kết quả an toàn là gì?**

Không tự Permit. Cần ghi nhận lỗi không đủ dữ liệu, chặn thao tác và khôi phục nguồn thuộc tính.

**8. Sau Mover, tại sao một access token được ký hợp lệ vẫn có thể tạo quyền dư?**

Vì claim có thể chứa vai trò/phòng ban cũ. Chữ ký không chứng minh thuộc tính luôn hiện hành; cần chính sách độ mới và kiểm soát session/cache/token.

**9. SCIM cập nhật Group thành công có chứng minh quyền ứng dụng đã được thu hồi ngay không?**

Không. Ứng dụng có thể có quyền trực tiếp, session hoặc token cũ; phải kiểm chứng tại điểm thực thi.

**10. Khác biệt giữa PDP và PEP là gì?**

**PDP đánh giá và ra quyết định**; **PEP cưỡng chế quyết định** để thao tác chỉ được thực hiện khi có Permit hợp lệ.

**11. ABAC với service account nên dựa vào thuộc tính nào?**

Workload identity, issuer/trust, service owner, environment, audience/scope, resource và trạng thái vòng đời dịch vụ; không tự áp toàn bộ thuộc tính HR dành cho người.

**12. Vì sao cần test cả action export hoặc delete dù test read đã Permit?**

Vì mỗi action có phạm vi và mức rủi ro khác nhau; quyền đọc không mặc nhiên bao gồm quyền xuất hay xóa dữ liệu.

## Ghi nhớ

- **ABAC là mô hình phân quyền theo thuộc tính**, đánh giá chủ thể, hành động, tài nguyên và ngữ cảnh bằng những policy có hiệu lực.
- **Permit/Deny không phải kết quả của đăng nhập đơn thuần.** Authentication, provisioning và authorization là các lớp khác nhau; **PEP** phải thực thi quyết định của **PDP** tại tài nguyên.
- **RBAC và ABAC bổ trợ nhau:** role giúp diễn đạt chức năng, thuộc tính giúp giới hạn tenant, project, classification, owner, trạng thái và thời điểm.
- **Thuộc tính phải có nguồn có thẩm quyền, mapping danh tính đáng tin và độ mới phù hợp.** Dữ liệu thiếu hoặc không xác minh được không được biến thành Permit.
- **Joiner** chỉ được truy cập sau khi đủ điều kiện; **Mover** cần mất quyền cũ và nhận quyền mới theo approval; **Leaver** phải bị chặn kể cả khi còn token hoặc session.
- **IdP/SSO, SCIM, RBAC/ABAC, PAM, tài khoản dịch vụ và reconciliation** cùng tham gia nhưng có trách nhiệm khác nhau; cập nhật User/Group không thay thế kiểm tra quyền hiệu lực.
- **Least privilege, default deny, kiểm thử dương/âm, kiểm toán, version policy và kiểm tra truy cập thực tế** là nền tảng để ABAC giảm quyền truy cập tồn dư trong toàn bộ vòng đời danh tính.
