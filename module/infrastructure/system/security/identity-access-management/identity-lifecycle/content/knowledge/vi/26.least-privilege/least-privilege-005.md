# Quyền theo ngữ cảnh trong Least privilege: cấp đúng phạm vi, đúng lúc và đúng điều kiện

**Quyền theo ngữ cảnh** (*context-aware access* hoặc *context-dependent privileges*) là cách áp dụng nguyên tắc **Least Privilege** để một danh tính chỉ có thể sử dụng **những quyền cần thiết cho hành động, tài nguyên và tình huống cụ thể**, trong thời gian và điều kiện được cho phép. Thay vì cấp vĩnh viễn mọi quyền có thể cần, hệ thống xem xét **chủ thể là ai, đang làm nhiệm vụ gì, muốn thao tác trên tài nguyên nào, vào thời điểm nào, với phiên xác thực/thiết bị/tín hiệu rủi ro như thế nào** trước khi cho phép.

Ví dụ, nhân viên tài chính có role `PaymentApprover` nhưng **không tự động được duyệt mọi khoản thanh toán**. Quyền duyệt có thể chỉ có hiệu lực đối với giao dịch thuộc đơn vị được giao, trong hạn mức được phê duyệt, khi người duyệt **khác người tạo**, phiên đăng nhập đã hoàn tất MFA thích hợp và hồ sơ công việc vẫn còn hiệu lực. Với quyền quản trị production, hệ thống có thể yêu cầu **Just-in-Time (JIT)** activation theo một ticket và tự hết hạn khi khung bảo trì kết thúc.

Bài nằm trong chương **Least privilege** của module **quản lý vòng đời danh tính IAM (Identity and Access Management)** theo mô hình **Joiner–Mover–Leaver (JML)**. Nội dung kết nối **HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**. Mục tiêu là biết chuyển nhu cầu nghiệp vụ thành **quyền tối thiểu có điều kiện**, hiểu nguồn ngữ cảnh đáng tin và xác minh rằng điều kiện được thực thi ở hệ thống đích, không chỉ xuất hiện trong cấu hình hoặc giao diện.

> **Nguyên tắc chính:** Quyền được gán cho một identity **không nhất thiết** là quyền được sử dụng **mọi lúc, mọi nơi và trên mọi tài nguyên**. Nhưng một điều kiện ngữ cảnh cũng **không thay thế việc thu hồi quyền khi không còn căn cứ**: quyền cũ phải được rà soát và deprovision theo JML.

## 1. Phân biệt quyền được cấp, quyền được kích hoạt và quyền thực thi

“Người dùng có quyền” là một cách nói thiếu chính xác nếu chưa nêu phạm vi. Trong một hệ thống IAM hiện đại nên tách ít nhất bốn lớp:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Eligibility / entitlement** | Người dùng có căn cứ và phê duyệt để **có thể được cấp** quyền này không? | Lan đủ điều kiện nhận `FinanceReportReader` vì có assignment Finance hợp lệ. |
| **Assignment / provisioning** | Role, group, scope hoặc policy đã được **ghi vào ứng dụng đích** chưa? | SCIM đã gán Lan vào group báo cáo tại Finance Portal. |
| **Activation / session context** | Quyền này có đang được **kích hoạt** trong phiên hoặc khoảng thời gian được phép không? | Role admin chỉ được kích hoạt sau phê duyệt JIT trong 30 phút. |
| **Request-time authorization** | Với tài nguyên và hành động **cụ thể**, hệ thống có cho thực thi không? | `GET /reports/123` chỉ thành công nếu cùng tenant/department và còn quyền. |

Một identity có thể đủ điều kiện nhưng chưa provision; có role đã provision nhưng chưa activate; có session hợp lệ nhưng bị từ chối một tài nguyên; hoặc đã gỡ role nhưng **session/token cũ vẫn còn hiệu lực** nếu ứng dụng chưa chặn.

### 1.1. Least privilege không chỉ là “ít role”

Một số hệ thống giảm số role trên giấy tờ nhưng gộp tất cả chức năng vào `SuperUser`. Khi đó người dùng “chỉ có một role” nhưng vẫn có quá nhiều quyền. Least privilege cần xét đồng thời:

1. **Hành động tối thiểu:** chỉ `read` khi không cần `update/delete`.
2. **Phạm vi tài nguyên tối thiểu:** chỉ đúng project, department, tenant hoặc dataset.
3. **Thời gian tối thiểu:** chỉ trong ca trực, ticket JIT hoặc khoảng assignment còn hiệu lực.
4. **Điều kiện an toàn cần thiết:** trạng thái identity, mức AuthN, device/risk context theo chính sách.
5. **Số lượng chủ thể tối thiểu:** chỉ người/workload thật sự cần quyền.
6. **Đường truy cập tối thiểu:** không giữ local account, token, direct grant hoặc đặc quyền dự phòng không kiểm soát.

**Tối thiểu** không đồng nghĩa luôn từ chối càng nhiều càng tốt. Quyền phải **đủ để hoàn thành nhiệm vụ hợp lệ**, trong khi giảm bề mặt và thời gian lạm dụng.

### 1.2. Ví dụ quyền đúng tên nhưng sai phạm vi

~~~text
Role:             ReportReader
Permission:       report:read
Subject tenant:   tenant-vn
Subject unit:     Finance-VN
Resource:         report-2026-Q4
Resource tenant:  tenant-sg
Resource unit:    Finance-SG

Role check:       PASS
Tenant condition: FAIL
Final decision:   DENY
~~~

Nếu hệ thống chỉ kiểm tra role mà không kiểm tra tenant và dữ liệu đích, quyền `report:read` có thể thành quyền **đọc mọi báo cáo** — vượt nhu cầu thật sự.

## 2. Bốn chiều ngữ cảnh của một quyết định truy cập

Một biểu thức truy cập theo ngữ cảnh có thể xem xét **subject, action, resource và environment**:

~~~mermaid
flowchart TD
    S["Subject: identity, assignment, role, account state"] --> P["Authorization policy"]
    A["Action: read, approve, deploy, export"] --> P
    R["Resource: tenant, owner, classification, project"] --> P
    E["Environment: time, device, assurance, risk"] --> P
    P --> D{"Permit có đủ điều kiện?"}
    D -->|Có| ALLOW["PEP cho thao tác đúng scope"]
    D -->|Không / thiếu dữ liệu đáng tin| DENY["PEP từ chối hoặc yêu cầu bước bổ sung"]
~~~

| Chiều | Thuộc tính minh họa | Tác dụng thu hẹp quyền |
| --- | --- | --- |
| **Subject** | `identityId`, `employmentStatus`, `department`, `activeAssignments`, `effectiveRoles`. | Chỉ những người/quan hệ còn căn cứ mới có quyền. |
| **Action** | `invoice:approve`, `report:read`, `cluster:restart`, `secret:rotate`. | Tránh gộp thao tác đọc và thao tác thay đổi nhạy cảm. |
| **Resource** | `tenantId`, `department`, `projectId`, `ownerId`, `classification`. | Quyền chỉ áp lên đúng đối tượng. |
| **Environment** | Giờ, mức MFA, posture thiết bị, phiên, mức rủi ro, môi trường production. | Quyền không phải lúc nào cũng khả dụng. |

Một chính sách khái niệm:

~~~text
PERMIT IF
    subject.lifecycleStatus == ACTIVE
    AND action == "report:read"
    AND "ReportReader" in subject.effectiveRoles
    AND subject.tenantId == resource.tenantId
    AND subject.department == resource.department
    AND subject.clearanceRank >= resource.classificationRank
    AND environment.authAssurance >= requiredAssurance(resource)
    AND requiredAttributesAreTrustedAndFresh
OTHERWISE DENY / UNRESOLVED according to policy model
~~~

Đây là **pseudocode**, không phải DSL chuẩn của SCIM, XACML, Cedar hay Rego. `clearanceRank` phải được xây từ **taxonomy phân loại hợp lệ**, không so sánh chuỗi `SECRET` với `CONFIDENTIAL` theo thứ tự chữ cái. Mức MFA/assurance phải có nguồn đáng tin và ngữ nghĩa được thống nhất.

### 2.1. “Ngữ cảnh” không nhất thiết là vị trí địa lý

Ngữ cảnh có thể là **quan hệ nghiệp vụ** (“người duyệt không phải người tạo”), **thuộc tính tài nguyên** (“báo cáo thuộc dự án đang tham gia”), **trạng thái JML** (“assignment còn hiệu lực”) hoặc **thời điểm yêu cầu**. Vị trí chỉ là một tín hiệu tùy chọn và có thể không đủ tin cậy.

**Đừng coi IP hoặc địa chỉ địa lý là một bằng chứng danh tính mạnh.** VPN, proxy, remote work, NAT và thay đổi mạng khiến vị trí không ổn định; một attacker trong “mạng nội bộ” vẫn có thể tấn công. Khi dùng network/geo context, cần hiểu giới hạn, dữ liệu cá nhân, nguồn tín hiệu và mức rủi ro.

### 2.2. Context trong policy và context trong request có thể khác nhau

- **Định nghĩa chính sách:** ai được phép làm gì, trên loại tài nguyên nào, trong những điều kiện nào.
- **Dữ liệu ở thời điểm yêu cầu:** account hiện có active không, action có thật sự là `approve` không, tài nguyên có thuộc tenant đã duyệt không, MFA có đủ gần thời điểm hiện tại không.

Không cho client tự khai một thuộc tính rồi coi như nguồn có thẩm quyền. Ví dụ, `request.department=Finance` không được dùng thay `resource.department` từ database tin cậy hay `subject.department` từ nguồn HR đã xác minh.

## 3. Những mô hình quyền theo ngữ cảnh thường dùng

| Mẫu kiểm soát | Ý tưởng | Ví dụ trong IAM | Hạn chế cần hiểu |
| --- | --- | --- | --- |
| **Resource-scoped role** | Role chỉ hiệu lực trên đúng phạm vi tài nguyên. | `ProjectMaintainer` cho `project-alpha`. | Role name giống nhau nhưng scope khác nhau. |
| **Time-bound grant** | Quyền có `validFrom` và `expiresAt`. | Truy cập dữ liệu dự án trong 14 ngày. | Hết hạn bản ghi không tự hủy session/token ở mọi target. |
| **Just-in-Time (JIT) elevation** | Quyền cao chỉ activate/cấp sau lý do/phê duyệt. | Admin production trong ticket bảo trì. | Cần deactivation, revoke và verification. |
| **Just-Enough Administration (JEA)** | Thao tác quản trị được giới hạn theo command/action. | Chỉ restart một service, không quản lý IAM toàn hệ thống. | Phải enforce kỹ thuật, không chỉ dặn người dùng. |
| **Risk-adaptive access** | Điều chỉnh yêu cầu theo mức rủi ro đáng tin. | Step-up MFA trước tải tập dữ liệu nhạy cảm. | Risk score có thể thiếu/đổi, phải xử lý an toàn. |
| **Device-conditioned access** | Yêu cầu thiết bị đáp ứng posture policy. | Thiết bị đã quản lý khi vào môi trường production. | “Compliant” phải đến từ nguồn đã kiểm chứng. |
| **Relationship-based condition** | Xem mối quan hệ giữa chủ thể và resource. | Người phụ trách ticket được sửa ticket của nhóm mình. | Quan hệ cần owner, thời hạn, SoD và cập nhật kịp. |
| **Transaction-level SoD** | Kiểm tra ngữ cảnh từng giao dịch. | Không tự duyệt khoản thanh toán mình tạo. | Tách role đơn thuần có thể chưa đủ. |
| **Emergency access** | Ngoại lệ khẩn cấp có giới hạn, giám sát và audit. | Break-glass khi IdP/PAM gặp sự cố. | Không phải đường bypass mặc định. |

Các mẫu này có thể kết hợp. Chẳng hạn một nhân viên **có role** `ProductionOperator`, **activate JIT** trong 60 phút, **chỉ thao tác** trên một cluster được phê duyệt, từ phiên đáp ứng **phishing-resistant MFA**, với ticket change còn hiệu lực.

## 4. RBAC làm nền, ABAC giới hạn quyền hiệu lực

**RBAC (Role-Based Access Control)** gom permission theo role; **ABAC (Attribute-Based Access Control)** đánh giá thêm thuộc tính subject/resource/action/environment. Least privilege theo ngữ cảnh thường kết hợp hai cách thay vì chỉ chọn một.

### 4.1. Một role, nhiều phạm vi hiệu lực

Giả sử `FinanceReportEditor` cho phép `report:read` và `report:update`. Không cần tạo một role riêng cho **mọi báo cáo** nếu policy có thể giới hạn phạm vi:

~~~text
user has FinanceReportEditor
AND resource.type == "FinanceReport"
AND resource.tenantId == subject.tenantId
AND resource.department in subject.authorizedDepartments
AND action in {"report:read", "report:update"}
AND resource.state != "ARCHIVED"
~~~

Phải xác định rõ `authorizedDepartments` có nguồn nào, được tính từ assignment hợp lệ nào và có thể bị thay đổi khi **Mover** hay không.

### 4.2. Role hierarchy có thể mở rộng quyền ngoài dự kiến

Nếu `Admin >= Editor >= Viewer`, một user được gán `Admin` thường kế thừa các permission của role junior. Không nên suy ra “có role admin” là được phép **mọi tenant, mọi resource**. Ngay cả permission kế thừa cũng cần **scope ABAC** và kiểm tra đối tượng.

Một thay đổi cạnh hierarchy có thể mở rộng quyền cho hàng trăm account dù không ai được gán thêm role trực tiếp. Bởi vậy cần:
- Impact analysis trên **effective permissions** và mọi đường kế thừa.
- Kiểm tra SoD, least privilege và chủ thể hưởng lợi.
- Xác minh mapping giữa IAM role, IdP group, SCIM Group và role ứng dụng.
- Thu hồi/grant theo quy trình thay đổi có phê duyệt và audit.

### 4.3. Provisioning-time condition và request-time condition

| Thời điểm | Câu hỏi | Điểm mạnh | Nguy cơ |
| --- | --- | --- | --- |
| **Provisioning-time** | User có đủ điều kiện để được cấp role/group/entitlement không? | Giảm số quyền thường trực, dễ audit access inventory. | Khi HR chuyển vai trò, connector chậm có thể giữ quyền cũ. |
| **Activation-time** | Có cho phép kích hoạt quyền cao tại thời điểm này không? | Giảm thời gian đặc quyền khả dụng. | Ticket hết hạn nhưng phiên/tokens chưa thu hồi. |
| **Request-time** | Hành động cụ thể trên resource này có đáp ứng context hiện tại không? | Phạm vi chi tiết, có thể chặn quyền theo resource. | Nếu PIP/PEP cache cũ hoặc không enforce, quyền vẫn còn. |

**Thiết kế mạnh dùng nhiều lớp**: chỉ cấp entitlement có căn cứ, chỉ activate khi cần và **kiểm tra điều kiện tại hành động/tài nguyên thực tế**.

## 5. Kiến trúc PAP, PDP, PIP, PEP và vai trò IAM/IGA

Quyền theo ngữ cảnh chỉ hiệu quả nếu một bộ phận có trách nhiệm **ra quyết định** và một bộ phận có trách nhiệm **thực thi quyết định**.

| Thành phần | Tên | Vai trò |
| --- | --- | --- |
| **PAP** | Policy Administration Point | Soạn, xem xét, phê duyệt, version chính sách. |
| **PIP** | Policy Information Point | Lấy thuộc tính có nguồn, thời hạn và ngữ nghĩa rõ. |
| **PDP** | Policy Decision Point | Tính kết quả dựa trên role/permission và các condition. |
| **PEP** | Policy Enforcement Point | Cho hoặc chặn thao tác ở API, dịch vụ hoặc resource layer. |
| **IAM/IGA** | Identity and access governance | Identity lifecycle, desired access, phê duyệt, provisioning, access review. |
| **IdP** | Identity Provider | Xác thực, MFA, session và phát bằng chứng/claim cho ứng dụng SSO. |
| **Target app** | Service provider/resource server | Account, resource state, entitlement và enforcement thực tế. |

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng / client
    participant E as PEP: API ứng dụng
    participant D as PDP: Policy engine
    participant I as PIP: HR/IAM/resource/IdP signals
    participant R as Resource store
    U->>E: Thao tác trên tài nguyên X
    E->>E: Xác minh token/session và account binding
    E->>R: Lấy metadata tin cậy của X
    R-->>E: owner, tenant, classification, state
    E->>D: Subject + action + X + environment
    D->>I: Lấy attributes, lifecycle state, policy version
    I-->>D: Nguồn và freshness của dữ liệu
    D->>D: Đánh giá role, scope, SoD và context
    D-->>E: PERMIT / DENY / other policy result
    alt Permitted và điều kiện enforcement đạt
        E->>R: Thực thi thao tác được phép đúng phạm vi
        E-->>U: Kết quả
    else Not permitted / không thể quyết định an toàn
        E-->>U: Từ chối hoặc yêu cầu bước tiếp theo phù hợp
    end
~~~

**PDP trả Permit không chứng minh PEP đã enforce đúng**. Một API có thể trả dữ liệu của tenant khác do truy vấn database sai, dù policy đã kiểm tra role của người dùng. Cần kiểm thử **object-level authorization**, query scope, bulk/export, cache và các endpoint phụ.

### 5.1. Không phải mọi hệ thống có một PDP tập trung

Có hệ thống dùng thư viện policy trong từng ứng dụng; có hệ thống áp authorization tại gateway, service mesh hoặc database. Điều cần biết là **policy nào có thẩm quyền**, **PEP nào phải tuân theo**, **nguồn ngữ cảnh nào hợp lệ** và **cách chứng minh quyết định đang thực sự áp dụng**.

### 5.2. Kết quả thiếu thông tin không được tự động trở thành Permit

Một số mô hình như XACML phân biệt `Permit`, `Deny`, `NotApplicable` và `Indeterminate`. Engine khác có thể chỉ trả boolean/lỗi. Dù hình thức nào, phải định nghĩa **combining algorithm và default behavior** cho mọi kết quả.

Không viết logic “chỉ chặn khi trả Deny; timeout thì cho qua”. Với quyền nhạy cảm, nếu thiếu nguồn thuộc tính bắt buộc hoặc policy engine không hoạt động, cần **xử lý fail-safe** theo rủi ro, không tự mở quyền.

## 6. Giới hạn theo tài nguyên: một permission không có nghĩa mọi đối tượng

### 6.1. Object-level authorization

Một API:

~~~http
GET /api/reports/123 HTTP/1.1
Authorization: Bearer <access-token>
~~~

phải kiểm tra báo cáo **123 thật** thuộc tenant, department hoặc project nào. Nếu người dùng sửa URL sang `/reports/124`, ứng dụng phải đánh giá lại điều kiện cho **124**, không dùng kết quả đã tính cho 123.

Một chính sách minh họa:

~~~text
allowed =
  subject.accountActive
  AND "ReportReader" in subject.effectiveRoles
  AND subject.tenantId == report.tenantId
  AND report.department in subject.authorizedDepartments
  AND subject.clearanceRank >= report.classificationRank
~~~

Giới hạn theo **resource ID và thuộc tính server-side** giúp phòng lỗi **Broken Object-Level Authorization (BOLA/IDOR)**. Không tin `report.department` do client gửi để quyết định.

### 6.2. Scope khi liệt kê và export

Giả sử người dùng xem danh sách `GET /api/reports`. Nếu policy chỉ kiểm tra có `ReportReader` rồi trả mọi record, quyền không còn tối thiểu. Cần áp scope vào **query/database hoặc lọc server-side có kiểm chứng** trước khi trả kết quả, bao gồm:
- Listing và tìm kiếm.
- Export toàn bộ hoặc download.
- Thống kê, count và aggregate có nguy cơ lộ thông tin.
- Batch API và background job chạy thay người dùng.
- Cache chung nhiều tenant/người dùng.

**Một endpoint được bảo vệ tốt không đủ nếu endpoint export khác bỏ kiểm tra.**

### 6.3. Scope dưới dạng token hoặc capability

Một số hệ thống dùng token chứa scope như `reports.read` hoặc role claim. Scope cho biết loại quyền/đối tượng mà token có thể mang theo **theo thiết kế của issuer/resource server**, nhưng không tự biến token thành quyền xem mọi báo cáo. Resource server vẫn cần kiểm tra **audience, issuer, resource tenant, ownership và policy hiện tại** theo mô hình triển khai.

Không dùng OIDC **ID token** thay **OAuth access token** để gọi API; mỗi loại token có mục đích và audience khác nhau.

## 7. Giới hạn theo thời gian và nhiệm vụ

### 7.1. Temporary entitlement khác JIT elevation

**Temporary entitlement** là role/quyền có hạn sử dụng, có thể được provision sẵn và chỉ còn hiệu lực trong khung thời gian xác định. **JIT elevation** yêu cầu một hành động kích hoạt/cấp quyền khi có nhu cầu, thường gắn ticket, approval và thời lượng ngắn.

| Thuộc tính | Temporary grant | JIT elevation |
| --- | --- | --- |
| Cấp lúc nào | Trước thời gian làm việc hoặc lúc phê duyệt. | Khi cần thực hiện nhiệm vụ cụ thể. |
| Thời lượng | Theo hợp đồng/dự án/ngoại lệ. | Thường ngắn và chỉ đủ cho thao tác. |
| Trạng thái mặc định | Có thể đã provision nhưng đang chờ hiệu lực. | Quyền cao **không active** nếu chưa kích hoạt. |
| Bằng chứng | Effective dates, approval, owner, readback. | Thêm request/ticket, actor, approval, activation và deactivation. |
| Rủi ro còn lại | Session/role cache sau expiration. | Quyền đã activate không bị gỡ đúng hạn hoặc scope quá rộng. |

Với cả hai, cần phân biệt **đến thời hạn** và **quyền đã thực sự bị chặn tại target**.

### 7.2. Khoảng thời gian nửa mở

Một mô hình thời gian thông dụng:

~~~text
eligibleAt(now) =
    validFrom <= now
    AND (validUntil is absent OR now < validUntil)
~~~

Cách viết này khiến quyền **hết hiệu lực ngay tại `validUntil`**. Phải chuẩn hóa instant, múi giờ và định nghĩa “cuối ngày” rõ ràng. Không dùng so sánh chuỗi thời gian tùy ý khi các hệ thống có time zone khác nhau.

### 7.3. JIT cho một lần xử lý sự cố production

Ví dụ:
- Engineer có quyền `ProductionViewer` thường trực.
- Incident cần `service:restart` trên `cluster-vn-2`.
- Người trực tạo ticket có incident ID, reason và thời hạn.
- Owner/phê duyệt tự động theo policy hoặc reviewer có thẩm quyền.
- PAM/JIT kích hoạt `RestartOperator` đúng cluster trong 45 phút.
- Engineer phải dùng MFA/step-up thích hợp.
- Sau thao tác, quyền bị deactive/revoke và ghi session/command audit.
- Readback xác minh không còn permission `service:restart` qua role cũ hay token.

~~~mermaid
flowchart TD
    A["Nhu cầu thao tác đặc quyền"] --> B["Ticket + scope + thời hạn"]
    B --> C{"Identity active, role đủ, SoD/approval đạt?"}
    C -->|Không| X["DENY + xử lý yêu cầu"]
    C -->|Có| D["Step-up AuthN nếu policy yêu cầu"]
    D --> E["JIT activate quyền tối thiểu"]
    E --> F["PEP chỉ cho action/resource được duyệt"]
    F --> G["Hết hạn / kết thúc ticket / rút yêu cầu"]
    G --> H["Deactivation + revoke session/token khi cần"]
    H --> I["Readback effective access và audit"]
~~~

**Chỉ cấp role `ClusterAdmin` toàn cục để restart một service** là ví dụ điển hình của overprivilege. Một quyền hẹp theo cluster/service và thao tác giảm thiểu hậu quả khi credential bị lộ hoặc người dùng thao tác nhầm.

## 8. Thiết bị, mạng, rủi ro và mức xác thực

### 8.1. MFA và step-up là điều kiện bổ sung, không phải quyền

Một người có role hợp lệ nhưng đăng nhập bằng phương thức chưa đủ mạnh có thể bị yêu cầu **step-up** trước khi thực hiện thao tác như phê duyệt thanh toán hoặc thay đổi quyền admin.

Ví dụ:

~~~text
mayApproveHighValuePayment =
    hasApprovedPermission("payment:approve")
    AND transactionWithinScope
    AND transactionSoDValid
    AND authentication.methodSatisfies(PHISHING_RESISTANT_POLICY)
    AND authentication.freshWithin(requiredWindow)
~~~

**MFA thành công không tự cấp role `PaymentApprover`**. Ngược lại, việc có role không tự chứng minh phiên hiện tại đã đáp ứng yêu cầu AuthN. Với OIDC, claim `amr/acr` có thể là dữ liệu tham khảo nếu IdP/RP thống nhất ngữ nghĩa và RP kiểm chứng token; không tin một chuỗi client tự gửi `mfa=true`.

### 8.2. Device posture và managed device

Điều kiện kiểu `device.compliant == true` chỉ hữu ích khi:
- Có danh tính thiết bị gắn đúng phiên hoặc workload.
- Kết quả posture được cung cấp bởi hệ thống quản trị thiết bị đáng tin.
- Posture có giới hạn thời gian/freshness rõ ràng.
- Ứng dụng/IdP không chấp nhận cờ “compliant” do client tự khai.
- Có hướng xử lý thiết bị lỗi hoặc đang chờ cập nhật.

Không mặc định mọi thiết bị cá nhân phải bị loại bỏ: chính sách tùy dữ liệu và nhu cầu. Nhưng tài nguyên nhạy cảm không nên hạ yêu cầu chỉ để vượt lỗi posture.

### 8.3. Rủi ro động và khả năng sai lệch

Risk scoring có thể xét bất thường phiên, thiết bị, mạng, hành vi và sự kiện bảo mật. Tuy nhiên:
- **Risk score không phải sự thật tuyệt đối**.
- Tín hiệu có thể sai, thiếu hoặc không ổn định.
- Người dùng hợp lệ có thể đăng nhập từ mạng/vị trí khác dự kiến.
- Kẻ tấn công có thể ở môi trường trông hợp lệ.

Cần định nghĩa **hành động tương ứng** với rủi ro: deny, yêu cầu step-up, hạn chế scope, đánh giá thủ công hoặc giám sát, tùy độ nhạy. Không để rủi ro “unknown” tự động trở thành “low” rồi mở quyền.

## 9. Phân biệt quyền theo ngữ cảnh với quản lý access theo vòng đời

Một quyền có thể **tạm thời không sử dụng được** do thiếu condition, nhưng role/group/credential vẫn còn trên ứng dụng. Đó chưa phải thu hồi.

| Trạng thái | Ví dụ | Hàm ý kiểm soát |
| --- | --- | --- |
| **Được cấp và được phép dùng** | User có role, trong scope, MFA đủ. | Hợp lệ nếu đúng nhiệm vụ và JML. |
| **Được cấp nhưng condition đang từ chối** | User có role Finance nhưng yêu cầu báo cáo tenant khác. | Điều kiện đang bảo vệ, nhưng role có cần tiếp tục giữ không? |
| **Quyền đã hết căn cứ nhưng vẫn được provision** | Mover rời Operations, group Operations chưa được gỡ. | **Residual entitlement**, phải deprovision dù PEP hiện từ chối một số request. |
| **Không còn entitlement nhưng session cũ vẫn dùng được** | Group đã gỡ, access token cũ còn quyền. | **Residual effective access**, cần kiểm soát session/token. |
| **Đã thu hồi và kiểm chứng** | Role, credential và đường truy cập bắt buộc đã chặn. | Kết quả cần có trong workflow JML. |

### 9.1. Bốn nguồn quyền độc lập có thể tồn tại song song

- **Role/group từ IAM/IdP**.
- **Direct grant tại ứng dụng** mà provisioning connector không biết.
- **Permission qua role hierarchy/nested group**.
- **Token, local login, session, API key** độc lập hoặc có thời gian tồn tại riêng.

Một condition chỉ kiểm tra nhóm IdP có thể bỏ qua local role trong ứng dụng. Ngược lại, xóa group IdP không đủ nếu ứng dụng không re-evaluate authorization. Thiết kế least privilege phải **inventory mọi nguồn quyền và đường thực thi**.

## 10. Joiner: cấp quyền theo nhiệm vụ và mốc bắt đầu

Trong **Joiner**, HRIS hoặc nguồn contractor có thẩm quyền tạo/báo hồ sơ nhân sự; IAM xác minh identity, xác định mốc hiệu lực và cấp những quyền chuẩn bị đủ dùng. Không nên dùng role tổng quát “AllStaffAdmin” chỉ để người mới làm onboarding.

### 10.1. Quy trình tham khảo

1. Xác nhận identity và quan hệ làm việc/sponsor đúng người, đúng tenant.
2. Xác định vị trí và **assignment có hiệu lực**, không chỉ dựa vào job title.
3. Tính **baseline entitlement** tối thiểu theo chức năng.
4. Đặt **effectiveFrom/effectiveUntil** cho quyền tạm và ngoại lệ.
5. Provision account/role/group tại IdP/target qua SCIM/API/manual theo năng lực.
6. Đăng ký và xác minh phương thức AuthN/MFA cần thiết.
7. Kiểm tra resource scope và conditional authorization tại PEP.
8. Readback target account, permission và log, giữ ticket/owner.

### 10.2. Truy cập trước ngày bắt đầu

Một nhân viên có thể cần điền giấy tờ nhân sự trước ngày chính thức. Thay vì kích hoạt quyền production, định nghĩa **pre-start access** chỉ cho tài nguyên onboarding:

~~~text
if identity.inVerifiedPreStartState
   AND now in approvedOnboardingWindow
   AND action in {"onboarding:read", "onboarding:submit"}
   AND resource.tenantId == identity.tenantId
then MAY_ALLOW_ONBOARDING_ONLY
~~~

**Không dùng pre-start làm lý do kích hoạt quyền nhạy cảm trước mốc có hiệu lực.** Khi nhân viên bắt đầu, IAM chuyển sang baseline có phê duyệt; các ngoại lệ onboarding phải được gỡ nếu không còn cần.

### 10.3. “Có account” khác “được vào mọi ứng dụng”

SCIM provisioning có thể tạo `User` và `Group`; SSO có thể xác thực thành công. Nhưng target vẫn phải kiểm tra **role/permission, resource scope và context**. Một Joiner có account IdP chưa hoàn tất MFA có thể bị chặn login/step-up đúng chính sách; một người có SSO nhưng ứng dụng chưa provision account thì lỗi ở lớp khác.

## 11. Mover: đổi ngữ cảnh phải làm thay đổi quyền hiệu lực

**Mover** là thay đổi vai trò, phòng ban, dự án, đơn vị hoặc mức trách nhiệm. Identity và account IdP có thể giữ nguyên, nhưng quyền cần được tính lại. Đây là tình huống dễ phát sinh **quyền tồn dư do dữ liệu đồng bộ hoặc session cũ**.

### 11.1. Ví dụ Operations → Finance

Lan chuyển từ Operations sang Finance. Trước khi chuyển:
- `OperationsReportReader` và `ProductionViewer` có căn cứ.
- `subject.department = Operations`.
- Một số application claims/session phản ánh department cũ.

Sau mốc Mover:
- `FinanceReportReader` có thể được cấp khi đủ approval.
- `OperationsReportReader` và `ProductionViewer` phải được gỡ nếu không còn assignment hợp lệ.
- `subject.department` chuyển thành Finance trong nguồn có thẩm quyền.
- PEP phải chặn yêu cầu đọc báo cáo Operations nếu không còn quyền ủy nhiệm hợp lệ.
- Session/token chứa department hoặc role cũ cần bị đánh giá về thời điểm thu hồi.

~~~mermaid
sequenceDiagram
    autonumber
    participant HR as HRIS
    participant IAM as IAM/IGA
    participant IDP as IdP / SSO
    participant APP as Target / PEP
    HR->>IAM: Mover effectiveAt, Operations -> Finance
    IAM->>IAM: Tính KEEP / REMOVE / GRANT và SoD
    IAM->>IDP: Cập nhật attributes, roles/groups
    IAM->>APP: SCIM/API deprovision old + provision approved new
    Note over IDP,APP: Token/claim cũ hoặc app cache có thể còn chứa Operations
    IAM->>APP: Kích hoạt invalidation/revocation nếu hỗ trợ
    APP->>APP: Kiểm tra authorization với thuộc tính hiện hành
    APP-->>IAM: Actual access + reconciliation evidence
~~~

### 11.2. Ngữ cảnh mới không tự xóa entitlement cũ

Một ứng dụng có thể sử dụng ABAC theo department và từ chối báo cáo Operations ngay sau cập nhật HR. Nhưng application group `ops-prod-deployers` vẫn tồn tại. Ứng dụng **khác** có thể cấp quyền dựa trên nhóm đó mà không áp cùng condition.

Vì vậy Mover phải:
1. Tính desired access từ mọi assignment hợp lệ.
2. Gỡ những role/group/direct grant không còn căn cứ.
3. Cấp quyền mới theo phê duyệt và SoD.
4. Kiểm tra token/session/cached authorization.
5. Chứng minh actual access ở những target quan trọng đã phản ánh thay đổi.

### 11.3. Multi-assignment và handover có thời hạn

Một người có thể tiếp tục hỗ trợ Operations trong 7 ngày để bàn giao. Thay vì giữ vĩnh viễn role cũ hoặc sửa lại department chính, mô hình hóa **delegated assignment**:

~~~text
delegation:
  subjectId: person-2048
  projectId: ops-handover-2026
  permissions: ["ticket:read", "runbook:comment"]
  validFrom: 2026-12-01T00:00:00+07:00
  validUntil: 2026-12-08T00:00:00+07:00
  approver: operations-owner
  reason: approved-handover
~~~

Đây là **cấu trúc dữ liệu minh họa**, không phải schema SCIM. PEP cần kiểm tra thời gian và scope, đồng thời workflow phải gỡ delegation tại thời hạn. Không mở quyền deploy production chỉ vì “hỗ trợ bàn giao” nếu thao tác đó không cần.

## 12. Leaver: từ chối đăng nhập và đóng mọi access path

Khi HRIS xác nhận **Leaver** tới mốc có hiệu lực, least privilege không còn là “giảm quyền” mà là **không còn quyền làm việc thông thường** trên các tài nguyên thuộc quan hệ đó, trừ những ngoại lệ hậu nghỉ việc được thiết kế và phê duyệt riêng.

### 12.1. Chặn theo nhiều lớp

| Lớp | Hành động thường cần | Cần xác minh |
| --- | --- | --- |
| **HRIS/IAM** | Employment/contract status kết thúc đúng effective time. | Sự kiện nguồn có thẩm quyền và mapping đúng identity. |
| **IdP/SSO** | Disable account/chặn AuthN mới, thu hồi phương thức khi cần. | Login mới bị từ chối theo policy. |
| **SCIM/API target** | Disable User, gỡ Group/role/entitlement. | Readback `active`, memberships và quyền thực tế. |
| **App sessions** | Revoke/expire session hoặc chặn khi request tiếp theo. | Không dùng được phiên cũ. |
| **Tokens/keys** | Đánh giá access/refresh tokens, PAT, API key, certificate. | Không còn đường truy cập bắt buộc. |
| **Local/privileged accounts** | Tìm và disable cả account phụ/đặc quyền. | Inventory và thử kiểm tra trạng thái hợp lệ. |
| **Delegated/JIT access** | Hủy delegation/activation đang mở. | Không còn ticket/role tạm có hiệu lực. |

**Một policy condition** `employmentStatus == ACTIVE` có thể từ chối request nếu PEP thực sự kiểm tra nguồn mới. Nhưng nó **không tự vô hiệu hóa** local session hoặc API token tại mọi target. Đóng Leaver chỉ khi quyền bắt buộc đã bị chặn và được xác minh, hoặc sai lệch có owner/kiểm soát theo quy trình.

### 12.2. Rehire không tự nối lại đặc quyền cũ

Người tái tuyển có thể cùng email hay employee ID theo chính sách HRIS. Không tự mở account cũ rồi giữ role JIT/privileged hoặc delegation chưa dọn. Cần proofing/identity correlation, tính lại desired access theo assignment hiện tại và cấp theo thẩm quyền mới.

## 13. Session, token, claim và độ trễ thực thi

### 13.1. Token chứa claim là ảnh chụp tại thời điểm phát hành

Một OIDC ID token hoặc OAuth access token có thể chứa claim như role/department. Những claim đó có thể **đúng và được ký hợp lệ lúc phát hành**, nhưng không chắc phản ánh Mover/Leaver vừa xảy ra.

Ví dụ:
- 08:00: user nhận access token có `department=Operations`, hiệu lực 60 phút.
- 08:10: HRIS xác nhận Mover sang Finance.
- 08:11: IAM gỡ Group Operations.
- 08:12: API chỉ kiểm tra chữ ký và claim trong access token cũ.

Nếu không có runtime check/revocation phù hợp, user có thể tiếp tục đọc dữ liệu Operations đến khi token hết hạn hoặc có sự kiện chặn khác. **Đó là cửa sổ quyền tồn dư**, không phải một lỗi syntax token.

### 13.2. Kiểm soát độ mới của context

Có thể cân nhắc:
- Short-lived access tokens cho hành động nhạy cảm.
- Introspection/revocation hoặc session invalidation nếu kiến trúc hỗ trợ.
- PDP/PIP truy vấn thuộc tính hiện hành cho quyền nhạy cảm.
- Cache TTL và policy-version binding.
- Back-channel/notification theo khả năng IdP/target.
- Forced re-auth/step-up khi thay đổi đặc quyền.
- Token exchange hoặc scoped tokens khi cần áp ranh giới tài nguyên.

**Không có một cơ chế đảm bảo thu hồi tức thì trên mọi ứng dụng.** Nên công bố **revocation SLA** theo mức rủi ro, kiểm thử trong target thật và dùng biện pháp containment nếu không đạt.

### 13.3. Đăng xuất không phải deprovisioning

Logout có thể đóng một session ứng dụng hoặc IdP, nhưng không tự gỡ SCIM Group, local role, personal access token hay API key. Ngược lại, gỡ role tại IAM không bảo đảm session đang tồn tại tự kết thúc. Kiến trúc cần rõ ai xử lý từng đường.

## 14. Quyền theo ngữ cảnh cho tài khoản dịch vụ và workload

**Non-human identities** như service account, job và workload có thể dùng quyền có điều kiện tương tự con người, nhưng không nên ép chúng vào HR JML hay MFA của người dùng.

Ví dụ một job `billing-etl` được phép đọc dataset chỉ khi:

~~~text
subject.kind == WORKLOAD
AND subject.workloadId == "billing-etl"
AND subject.accountState == ACTIVE
AND subject.ownerTeam == "finance-platform"
AND action == "dataset:read"
AND resource.datasetId in approvedDatasetsFor(subject.workloadId)
AND resource.tenantId == subject.tenantId
AND environment.runtimeIdentityVerified
AND environment.executionEnvironment == "production"
~~~

Ở đây `runtimeIdentityVerified` cần dựa vào **workload identity federation, mTLS, managed identity hoặc cơ chế tin cậy khác** do hệ thống thực sự kiểm chứng; một header `X-Workload-Verified: true` do client gửi là không đủ.

### 14.1. Service account không cần “global admin để chạy cho chắc”

Một job chỉ đồng bộ báo cáo không nên có quyền:
- Xóa User của tenant.
- Thay đổi policy IAM toàn hệ thống.
- Đọc mọi secret trong vault.
- Triển khai workload không liên quan.
- Truy cập dữ liệu của dự án khác.

Thay bằng **resource-scoped permission**, thời lượng credential phù hợp, rotation/revocation, workload identity binding và owner rõ ràng. Nếu có thể tránh long-lived static secret bằng cơ chế workload identity phù hợp, giảm rủi ro lộ secret.

### 14.2. Owner nghỉ việc không đồng nghĩa workload phải dừng

Khi một engineer sở hữu service account rời công ty:
1. Chuyển owner và sponsor của workload.
2. Thu hồi quyền quản trị cá nhân người cũ.
3. Đánh giá và rotation credential mà người đó từng có khả năng xem.
4. Rà soát permissions của workload có còn cần cho dịch vụ không.
5. Deprovision workload identity khi **dịch vụ** kết thúc, không chỉ khi một nhân sự rời đi.

Đó là cách tránh cả **residual privilege** lẫn **gián đoạn hợp pháp**.

## 15. Nguồn ngữ cảnh và độ tin cậy của thuộc tính

Một permission có thể đúng về logic nhưng sai vì **dữ liệu đầu vào không có thẩm quyền hoặc quá hạn**.

| Thuộc tính | Nguồn đáng tin thường gặp | Cần tránh |
| --- | --- | --- |
| `employmentStatus` / effective dates | HRIS/contractor source được IAM xác minh. | Người dùng tự khai “active”. |
| `identityId` / tenant binding | IAM registry, IdP account binding đã xác minh. | Chỉ đối chiếu email hiển thị. |
| `department` / assignment | Nguồn HR tổ chức và approval workflow. | Chấp nhận claim cũ vô hạn. |
| `role/entitlement` | IAM/IGA, target app permission store. | Trust role do frontend gửi. |
| `resource.owner/tenant` | Resource database/catalog được bảo vệ. | Trust resource owner trong request body. |
| `device posture` | Device management/risk service với ràng buộc phiên. | Tin boolean `compliant` tự khai. |
| `authentication assurance` | IdP/SSO đã kiểm chứng, policy và thời điểm. | Tin `mfa=true` từ client. |
| `risk indicator` | Risk engine có owner, version, freshness. | Coi unknown là low risk. |
| `ticket/approval` | Hệ thống ticket/approval có actor và thời hạn. | Chuỗi lý do người dùng tự nhập. |
| `time` | Đồng hồ đáng tin của server/authorization service. | Đồng hồ trình duyệt. |

### 15.1. Attribute freshness là một điều kiện của quyền

Một trường như `department=Finance` có thể đến qua:

~~~text
HRIS authoritative event
    -> IAM identity attribute
    -> IdP/directory update
    -> OIDC/SAML claim hoặc PIP API
    -> PDP policy evaluation
    -> PEP thực thi
~~~

Mỗi điểm có **độ trễ và cache**. Cần quy định thuộc tính nào phải gần thời gian thực; thuộc tính nào được dùng bản cache trong thời hạn ngắn; nếu không cập nhật thì từ chối hay giới hạn thao tác.

Không tự coi `signature valid` là `attribute fresh`. Chữ ký xác minh ai phát hành token, không chứng minh HRIS không thay đổi kể từ lúc token được phát hành.

### 15.2. Thiếu/nghi ngờ thuộc tính và fail-safe

Ví dụ:

~~~text
NOT subject.suspended
~~~

nếu `suspended` bị thiếu và engine ngầm chuyển thành `false` có thể làm condition thành `true`. Một chính sách an toàn hơn yêu cầu **trạng thái được xác minh rõ**:

~~~text
subject.accountState == "ACTIVE"
AND subject.accountStateSource == "TRUSTED_IDENTITY_REGISTRY"
AND subject.accountStateFreshEnough
~~~

Cú pháp là minh họa. Cần hiểu semantics null/missing/unknown của engine cụ thể để không tạo **fail-open**.

## 16. SoD và chính sách giao dịch: giới hạn quyền ngay cả khi có role

**Segregation of Duties (SoD)** ngăn một chủ thể dùng các quyền xung đột theo chính sách. Cấp role tối thiểu vẫn có thể chưa đủ nếu hai role được kích hoạt trên cùng giao dịch.

### 16.1. Maker–checker

~~~text
mayApprovePayment =
    subject.accountActive
    AND subject.hasPermission("payment:approve")
    AND transaction.status == "PENDING_APPROVAL"
    AND transaction.createdByIdentityId != subject.identityId
    AND transaction.tenantId == subject.tenantId
    AND transaction.amount <= subject.approvalLimit
    AND authentication.recentAndStrong
~~~

Các thuộc tính `createdByIdentityId`, `approvalLimit` và `tenantId` phải đến từ hệ thống giao dịch/authorization có kiểm soát. Không cho client tự thay `createdBy` để được phê duyệt.

Nếu user nhận cả `payment:create` và `payment:approve` qua **role hierarchy**, một điều kiện maker–checker tại transaction giúp chặn tự duyệt, nhưng cũng cần kiểm tra static/dynamic SoD và governance của role theo chính sách.

### 16.2. Risk of context explosion

Nếu tổ chức tạo role mới cho mọi kết hợp [department × project × action × shift × device], số role có thể bùng nổ (**role explosion**). Ngược lại, một policy ABAC quá động nhưng không có account governance sẽ khó audit.

Hướng cân bằng:
- Dùng **role ổn định** cho khả năng chức năng.
- Dùng **resource scope/attribute** cho dữ liệu và nhiệm vụ thay đổi.
- Dùng **JIT và expiration** cho đặc quyền hiếm dùng.
- Dùng **SoD** cho xung đột quyền.
- Giữ **IAM/IGA** là nguồn quản trị assignment và accountability.
- Đảm bảo **PEP thực thi** và audit mọi thay đổi.

## 17. Break-glass: ngoại lệ theo ngữ cảnh nhưng không trở thành cửa hậu

Có những tình huống IdP/PAM không khả dụng hoặc sự cố nghiêm trọng cần khôi phục dịch vụ. **Break-glass access** là một cơ chế dự phòng có kiểm soát, không phải quyền admin thường trực cho toàn bộ nhân viên.

Một thiết kế nên có:
- **Điều kiện kích hoạt được định nghĩa trước**: sự cố nghiêm trọng hoặc dependency outage theo quy trình.
- **Danh tính/account đặc biệt** được bảo vệ và tách biệt phù hợp.
- **Phạm vi/tài nguyên/hành động tối thiểu** đủ khắc phục.
- **Người chịu trách nhiệm** và giới hạn thời gian sử dụng.
- **Lưu log, giám sát và cảnh báo** khi được dùng.
- **Review sau sự cố** và xử lý credential/session/permission.
- **Kiểm thử định kỳ** tính khả dụng của phương án nhưng không làm mất kiểm soát.

Không “fail open toàn bộ API” khi PDP hoặc IdP lỗi. Nếu cần đường khẩn cấp, hãy chuẩn bị **từ trước**, giới hạn scope và kiểm toán để không biến thành một cách né MFA, SoD hay JML.

## 18. Mẫu chính sách và thao tác thực thi

### 18.1. YAML policy minh họa

~~~yaml
policyId: prod-service-restart-jit
version: 4
owner: platform-security
effect: permitWhenAllConditionsMatch
target:
  action: service:restart
  environment: production
conditions:
  subject:
    lifecycleStatus: ACTIVE
    requiredRole: ProductionOperator
  resource:
    allowedClusterBinding: approvedJitRequest.clusterId
  activation:
    ticketStatus: APPROVED
    grantActive: true
    durationMinutesMax: 60
  authentication:
    requireStepUp: true
    assurancePolicy: strong-workforce-authn
  governance:
    requireNoSoDConflict: true
    approvalEvidence: required
defaultBehavior: DENY
~~~

**Đây là cấu trúc YAML minh họa nội bộ**, không phải cú pháp chuẩn của một policy engine. Trường `durationMinutesMax` phải thực sự được hệ thống activation/enforcement triển khai, không tự có hiệu lực nhờ nằm trong YAML.

### 18.2. Pseudocode kiểm soát tại request

~~~text
function authorizeRestart(request):
    subject = authenticateAndResolveAccount(request)
    if subject is unresolved:
        return DENY

    resource = loadTrustedServiceAndCluster(request.resourceId)
    context = loadTrustedContext(subject, request)
    approvedJit = loadApprovedJitGrant(subject, resource, request.action)

    if requiredContextMissingOrStale(subject, resource, context):
        return DENY

    if subject.lifecycleStatus != ACTIVE:
        return DENY

    if not hasEffectivePermission(subject, "service:restart"):
        return DENY

    if not approvedJit.isActiveAt(context.serverTime):
        return DENY

    if approvedJit.clusterId != resource.clusterId:
        return DENY

    if not context.authentication.meetsRequiredAssurance:
        return STEP_UP_OR_DENY_BY_POLICY

    if hasSoDConflict(subject, resource, request):
        return DENY

    return PERMIT_ONLY_FOR(resource, "service:restart")
~~~

Lưu ý đây là **pseudocode, không phải production implementation**. Phần thực tế còn cần kiểm chứng request/session/token, safe handling của `STEP_UP_OR_DENY`, chống race condition và kiểm tra lại trạng thái ngay trước thao tác nếu cần.

### 18.3. Ví dụ policy dạng Rego minh họa

~~~rego
package example.context_privilege

default allow := false

allow if {
  input.subject.account_active == true
  input.action == "report:read"
  "ReportReader" in input.subject.effective_roles
  input.subject.tenant_id == input.resource.tenant_id
  input.subject.department == input.resource.department
  input.subject.clearance_rank >= input.resource.classification_rank
  input.context.verified_authentication == true
}
~~~

Đây là **minh họa ý tưởng với Rego**, chưa gồm freshness, JML effective date, scopes nhiều assignment, token revocation hay PEP integration. Input phải được xây dựng từ nguồn tin cậy; không coi dữ liệu HTTP body tự gửi là authoritative.

### 18.4. Chú ý TOCTOU

Có thể xảy ra **Time-of-Check to Time-of-Use (TOCTOU)**: hệ thống đã cho phép lúc 10:00:00, nhưng trước khi thao tác hoàn tất, ticket JIT bị thu hồi hoặc tài nguyên chuyển trạng thái.

Với thao tác nhạy cảm, cần xác định:
- Quyết định được ràng buộc với action/resource/transaction nào.
- Trạng thái nào phải kiểm tra lại trước khi commit.
- Có thể sử dụng transaction/version check hoặc capability ngắn hạn không.
- Cách xử lý quyết định cũ khi resource hoặc quyền đã thay đổi.
- Audit quyết định và kết quả cuối cùng.

**Không coi một quyết định Permit được cache vô thời hạn là quyền sử dụng tiếp bất kể hoàn cảnh.**

## 19. Đo lường effective privilege và đối soát

### 19.1. Desired access và actual access

**Desired access**: tập role, scope, thời hạn và điều kiện mà tổ chức **phê duyệt** cho một identity/workload. **Actual access**: những hành động mà các hệ thống đích **thực sự chấp nhận** qua tất cả đường truy cập, session, token và grant.

Một mô hình khái niệm:

~~~text
DesiredPrivilege(identity, t) =
  approvedAssignments
  ∩ validTimeWindow(t)
  ∩ authorizedResourceScope
  ∩ policyConstraints

EffectivePrivilege(identity, resource, action, t) =
  actualTargetEntitlements
  ∩ activeSessionsAndCredentials
  ∩ currentPolicyDecision
  ∩ enforcedResourceScope
~~~

Ký hiệu giao tập ở đây chỉ **ẩn dụ về việc đồng thời thỏa các điều kiện**, không phải phép toán thực thi trực tiếp trên những kiểu dữ liệu không tương đồng. Trong thực tế, quyền có thể đến qua nhiều đường hợp nhau rồi bị giới hạn bởi các điều kiện. Cần **phân tích graph cấp quyền và đánh giá thực tế**, không chỉ so sánh tên role.

### 19.2. Bằng chứng cần để chứng minh đã giảm quyền

| Kiểm tra | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Identity/relationship** | Người có còn assignment hợp lệ? | HRIS event, effectiveAt, IAM identity ID. |
| **Entitlement inventory** | Role/group/direct grant nào vẫn tồn tại? | Readback IdP/SCIM/app permission store. |
| **Contextual policy** | Điều kiện tenant/project/time/device nào đang áp dụng? | Policy ID/version, owner, PIP source. |
| **Activation** | Có JIT grant/ticket đang active không? | PAM/JIT state, approval, expiration. |
| **Session/token** | Credential/phiên nào vẫn có thể sử dụng? | Session/token inventory và revocation evidence theo khả năng. |
| **PEP enforcement** | API/tài nguyên có thực sự chặn quyền sai không? | Test/decision log, API response, scoped query result. |
| **Remediation** | Sai lệch được giao ai, xử lý trước khi nào? | Ticket/incident ID, owner, verification timestamp. |

**Không ghi trạng thái `COMPLETED` chỉ vì API provisioning trả HTTP 200**. Sự kiện đó chứng minh request được chấp nhận hoặc xử lý theo contract, không chứng minh toàn bộ effective access đã cập nhật.

### 19.3. Chỉ số tham khảo

| Chỉ số | Cách đo | Lưu ý |
| --- | --- | --- |
| **Standing privileged access** | Số user/workload giữ quyền admin thường trực trong phạm vi. | Ưu tiên giảm đặc quyền không cần thiết, không tạo JIT bypass rộng. |
| **Time in elevated state** | Thời lượng role đặc quyền thực sự active. | Ghi theo activation/deactivation đã xác minh, không chỉ ticket. |
| **Over-scoped grants** | Quyền tài nguyên rộng hơn scope được duyệt. | Xét tenant, project, action và data classification. |
| **JIT expiration success** | Tỷ lệ grant hết hạn được xác minh mất quyền đúng thời hạn. | Không chỉ kiểm tra `expiresAt` trong database IAM. |
| **Mover residual-access latency** | Thời gian từ mốc phải thu hồi đến khi actual access bị chặn. | Phân biệt HR update, SCIM success và app enforcement. |
| **Leaver closure coverage** | Tỷ lệ đường truy cập bắt buộc đã kiểm chứng bị chặn. | Bao gồm local account/token và role phụ. |
| **Policy enforcement coverage** | Tỷ lệ endpoint/resource nhạy cảm dùng PEP được kiểm thử. | Không bỏ export, batch, service-to-service API. |
| **Unknown-context handling** | Tỷ lệ trường hợp thiếu thuộc tính bắt buộc không tạo Permit. | Kiểm tra timeouts, cache và partial failures. |
| **SoD exceptions** | Quyền xung đột có exception hợp lệ, owner và deadline. | Không để ngoại lệ vô hạn hoặc không giám sát. |
| **Service identity owner coverage** | Workload có owner, purpose, credential lifecycle và scope rõ. | Owner nhân sự đổi không được tạo orphan account. |

Không có một ngưỡng tuyệt đối phù hợp mọi hệ thống. Chỉ số phải phân tầng theo **độ nhạy tài nguyên, hành động, khả năng khai thác và thời gian thu hồi được chấp nhận**.

## 20. Tình huống xuyên suốt: kỹ sư vận hành và nhân viên tài chính

**Bối cảnh:** Công ty dùng HRIS, IAM/IGA, IdP hỗ trợ SSO/MFA, SCIM để đồng bộ User/Group ở một số ứng dụng, PAM/JIT cho production và ứng dụng tài chính có RBAC/ABAC.

### 20.1. An — Joiner ở bộ phận vận hành

An được xác minh danh tính và tạo account IdP. IAM cấp quyền cơ bản:
- `RunbookReader` cho runbook thuộc nhóm được giao.
- `IncidentViewer` cho ticket thuộc service ownership của An.
- Không có `ProductionAdmin` đứng thường trực.

Ngày đầu, An đăng nhập SSO thành công và có thể đọc runbook phù hợp. **Không có quyền deploy hoặc restart production** nếu chưa có assignment, ticket và phê duyệt.

### 20.2. An — JIT trong sự cố

Một dịch vụ do nhóm An phụ trách gặp sự cố. An yêu cầu quyền restart trên `cluster-vn-2` trong 45 phút, gắn ticket được duyệt. PAM kích hoạt capability hẹp `service:restart`, IdP yêu cầu MFA phù hợp. API PEP xác nhận đúng cluster và thời hạn trước khi thực thi.

Nếu An đổi URL sang `cluster-sg-9`, hệ thống phải **Deny** dù role JIT đang active vì **resource scope không khớp**.

### 20.3. An — Mover sang đội dữ liệu

HRIS gửi Mover với effectiveAt. IAM tính lại `KEEP / REMOVE / GRANT`, thu hồi role/nhóm Operations không còn căn cứ và mọi JIT grant đang mở theo policy; cấp quyền đọc dataset thuộc nhiệm vụ mới.

IdP session cũ của An có thể chứa claim Operations, nên cần đánh giá cách ứng dụng sử dụng claims/caches và xác minh các endpoint production **không còn cho thao tác** sau thời hạn quy định.

### 20.4. Bình — Finance Approver trong giao dịch

Bình được gán role `PaymentApprover` nhưng chỉ được duyệt:
- Giao dịch của tenant Finance-VN.
- Số tiền không vượt approval limit.
- Trạng thái `PENDING_APPROVAL`.
- Giao dịch do người khác tạo.
- Phiên đáp ứng step-up MFA nếu policy yêu cầu.

Role và MFA đều đúng **không đủ** nếu Bình là người đã tạo khoản thanh toán. Condition maker–checker phải Deny dựa trên `createdByIdentityId` đáng tin.

### 20.5. An — Leaver và quyền còn tồn dư

Khi An nghỉ việc, IdP chặn login mới và IAM deprovision account/roles. Tuy nhiên, một API token cũ vẫn được dịch vụ monitoring chấp nhận. **Đây là residual access**, dù dashboard JIT đã không hiện role. Workflow phải xác định owner của token, revoke/chặn đường truy cập và kiểm chứng thực tế trước khi đóng offboarding.

### 20.6. Bài học từ trường hợp

- **Đúng role** không bằng **đúng resource**.
- **Đúng resource** không bằng **đúng thời điểm**.
- **Đúng thời điểm** không bằng **đúng người/phương thức xác thực**.
- **MFA thành công** không bằng **authorization success**.
- **Group đã gỡ** không bằng **session/token đã hết quyền**.
- **Condition Deny** không bằng **mọi đường truy cập đã được deprovision**.

Một thiết kế least privilege thực sự phải kết hợp **grant governance, contextual conditions, runtime enforcement và lifecycle verification**.

## 21. Lỗi thiết kế và vận hành thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cấp role `Admin` toàn cục cho nhiệm vụ chỉ cần xem log. | Privilege escalation và thiệt hại lớn nếu credential lộ. | Tách `logs:read` đúng scope, hạn sử dụng. |
| Chỉ giảm số role mà không giảm permission. | Người dùng vẫn quá quyền. | Đo effective permissions/resource/action. |
| Chỉ ẩn nút UI theo ngữ cảnh. | API trực tiếp vẫn hoạt động. | Server-side PEP và object authorization. |
| Dùng địa chỉ IP hoặc vị trí làm bằng chứng danh tính duy nhất. | Có thể bị né/giả mạo hoặc cản người hợp lệ. | Kết hợp AuthN, device, risk với nguồn tin cậy. |
| Tin department/role do frontend gửi. | User tự mở rộng scope. | PIP/IdP/HRIS/target attributes đã kiểm chứng. |
| JIT grant hết hạn nhưng session/token vẫn còn. | Đặc quyền tồn dư sau ticket. | Deactivation, revoke và readback. |
| Tạo ngoại lệ vĩnh viễn cho truy cập khẩn cấp. | Break-glass trở thành cửa hậu. | Thời hạn, owner, audit, review. |
| Chỉ dựa vào IAM role, bỏ direct grants tại app. | Bỏ sót quyền phụ. | Reconciliation actual target access. |
| Chỉ kiểm tra danh sách group SCIM. | Bỏ nested/dynamic group, role nội bộ, token. | Inventory mọi đường và effective access. |
| Dùng JWT claim cũ sau Mover. | Tiếp tục được phép do department cũ. | Freshness, session/token policy, re-evaluate. |
| PDP/PIP timeout thì Permit. | Fail-open. | Fail-safe handling và break-glass được quản trị. |
| Không phân biệt unknown/false. | `NOT suspended` tạo quyền khi thiếu dữ liệu. | Explicit state và validation. |
| Role Approver không kiểm tra creator. | Tự tạo–tự duyệt giao dịch. | Transaction-level SoD. |
| Đồng nhất IdP logout với offboarding. | Local sessions/tokens vẫn có thể hoạt động. | Deprovision/verify tất cả target. |
| Chỉ áp policy cho single resource, bỏ bulk/export. | Rò rỉ hàng loạt dữ liệu ngoài scope. | PEP cho mọi endpoint và query-level constraints. |
| Owner dịch vụ nghỉ việc thì xóa credential workload ngay. | Gián đoạn dịch vụ hợp lệ. | Handover owner, rotation và least privilege riêng. |
| Đánh dấu ticket hoàn tất khi SCIM trả 200. | Actual access chưa chắc đã chặn. | Readback, test enforcement, remediation owner. |

## 22. Checklist và bài tập tự kiểm tra

### 22.1. Checklist áp dụng quyền theo ngữ cảnh

- [ ] Mọi entitlement có **business purpose, owner, scope, approval và effective dates** phù hợp.
- [ ] Phân biệt quyền **eligible**, đã **provision**, đang **active** và đã được **PEP cho thực thi**.
- [ ] Định nghĩa các chiều **subject/action/resource/environment** và thuộc tính cần thiết.
- [ ] Role/permission chỉ đủ cho nhiệm vụ; phân tích role hierarchy/multiple grants và quyền effective.
- [ ] Tài nguyên có tenant/owner/classification đáng tin và PEP kiểm tra từng resource.
- [ ] JIT/PAM cấp quyền đặc quyền hẹp, có approval/ticket, thời hạn và revoke/readback.
- [ ] MFA/step-up dùng signal đã kiểm chứng; không xem AuthN như giấy phép truy cập mọi tài nguyên.
- [ ] Device/network/risk signals có owner, freshness và hành vi khi thiếu dữ liệu.
- [ ] Điều kiện logic xử lý đúng `AND/OR/NOT`, missing/null/unknown và ranh giới thời gian.
- [ ] Static/dynamic/transaction SoD được xét, nhất là quyền phê duyệt.
- [ ] PAP/PDP/PIP/PEP và bộ phận IAM/target có trách nhiệm rõ ràng.
- [ ] Tất cả API, export, batch và background jobs có enforcement phù hợp.
- [ ] Session/token/claims được quản lý khi role/department/account thay đổi.
- [ ] Joiner chỉ nhận quyền đúng thời điểm; Mover gỡ quyền cũ; Leaver đóng mọi access path bắt buộc.
- [ ] Tài khoản dịch vụ có owner, phạm vi resource và credential lifecycle riêng.
- [ ] Định nghĩa revocation SLA, xử lý eventual consistency và bước containment khi quá hạn.
- [ ] Reconciliation kiểm tra **desired access và actual effective access**.
- [ ] Policy/ticket/access decisions có version, correlation ID, audit và verification outcome.
- [ ] Không ghi password, OTP, token đầy đủ hoặc dữ liệu riêng tư không cần thiết vào log.

### 22.2. Tình huống A — Role rộng hơn scope

Người dùng có `ReportReader`, nhưng cố truy cập báo cáo tenant khác bằng cách đổi ID trong URL. Hãy xác định những thuộc tính resource mà PEP phải đọc từ server, lý do role check đơn thuần không đủ và cách kiểm thử API chống BOLA/IDOR.

### 22.3. Tình huống B — JIT hết hạn

Engineer được JIT `service:restart` trong 30 phút. Ticket đã hết hạn nhưng một access token còn claim `ProductionOperator`. Hãy xác định các bước **deactivation, token/session handling, policy re-evaluation, readback** cần làm trước khi đánh dấu verified.

### 22.4. Tình huống C — Mover và claim cũ

Lan chuyển bộ phận từ Operations sang Finance. HRIS cập nhật đúng nhưng IdP token cũ vẫn mang `department=Operations`. Vì sao chữ ký token hợp lệ không bảo đảm quyền cũ đã chặn? Đề xuất TTL/revocation/PIP freshness và bước kiểm chứng tại application PEP.

### 22.5. Tình huống D — Maker–checker

Bình vừa tạo vừa có role phê duyệt giao dịch. Hãy thiết kế condition dùng `createdByIdentityId`, `approvalLimit`, tenant và trạng thái giao dịch; chỉ ra lý do Static SoD hoặc một role name không tự giải quyết toàn bộ yêu cầu.

### 22.6. Tình huống E — Break-glass khi IdP lỗi

IdP không khả dụng trong lúc cần khắc phục production. Một đề xuất là tắt MFA và mở admin API cho tất cả nhân viên trong 2 giờ. Hãy giải thích rủi ro fail-open và mô tả break-glass có scope/owner/audit/review được quản trị trước.

### 22.7. Tình huống F — Service identity owner nghỉ việc

Job `billing-etl` chạy hàng ngày, owner rời công ty. Có nên xóa workload account ngay lập tức không? Trình bày kế hoạch **bàn giao owner, thu hồi quyền cá nhân, đánh giá/rotation secret, rà soát resource scope và deprovision khi dịch vụ kết thúc**.

### 22.8. Tình huống G — Phân biệt Deny với deprovision

Một policy ABAC từ chối user đã đổi phòng ban, nhưng target vẫn có local role `OpsAdmin` và API key không ràng buộc cùng policy. Hãy chỉ ra **lớp đang bảo vệ**, **đường quyền còn tồn dư**, và những kiểm tra reconciliation phải chạy trước khi đóng Mover.

### 22.9. Tình huống H — Quyền dự án có hạn

Một chuyên gia được quyền đọc báo cáo dự án trong đúng 14 ngày với phạm vi `project-alpha`. Hãy xác định `effectiveFrom`, `effectiveUntil`, scope/action, approval, attribute source và cách ngăn session/token tiếp tục truy cập sau thời hạn.

**Điểm cần ghi nhớ:** **Least privilege theo ngữ cảnh** không chỉ giảm số role mà còn **giới hạn hành động, tài nguyên, thời gian, điều kiện xác thực và nguồn quyền có thể thực thi**. RBAC cung cấp quyền nền tảng; ABAC, JIT/PAM, SoD và chính sách phiên giúp quyền **chỉ hiệu lực khi đúng nhiệm vụ**. Trong IAM **Joiner–Mover–Leaver**, cần đồng bộ IdP/SSO, SCIM provisioning và các ứng dụng đích, kiểm soát token/session, rồi **readback/reconciliation actual access** để chứng minh quyền không còn căn cứ đã bị chặn.

