# Chọn vai trò trong Access request: cấp đúng quyền, đúng phạm vi và đúng thời hạn

## 1. Vì sao bước chọn vai trò quan trọng?

Trong quản lý **Identity and Access Management (IAM)**, **Access request** là quy trình một người hoặc đơn vị được ủy quyền yêu cầu cấp, thay đổi hoặc gia hạn quyền truy cập ứng dụng và tài nguyên. Bước **chọn vai trò** (*role selection*) chuyển nhu cầu nghiệp vụ thành một hoặc nhiều **role có định nghĩa quyền rõ ràng** để tổ chức kiểm tra, phê duyệt và cấp phát.

Ví dụ, nhân viên Mai cần **xem báo cáo doanh thu của Dự án Atlas**. Hệ thống có ba vai trò:

| Vai trò | Quyền chính | Có phù hợp với nhu cầu của Mai? |
| --- | --- | --- |
| **Atlas Report Viewer** | Đọc báo cáo Atlas | **Phù hợp**, nếu Mai có quan hệ công việc hợp lệ với Atlas |
| **Atlas Report Editor** | Đọc và chỉnh sửa báo cáo Atlas | Quá rộng nếu Mai chỉ cần xem |
| **Atlas Report Administrator** | Quản trị truy cập, thay đổi cấu hình, quản lý dữ liệu | Không phù hợp nếu không có trách nhiệm quản trị |

Nếu Mai chọn **Administrator** chỉ để tránh bị thiếu quyền, hệ thống có thể tạo **đặc quyền thừa** (*overprivilege*), tăng rủi ro thao tác nhầm hoặc lạm dụng tài khoản. Ngược lại, nếu ứng dụng chỉ cung cấp một vai trò quá hạn chế và Mai không thể hoàn thành công việc, bước chọn vai trò phải chỉ ra **khoảng thiếu quyền**, không tự động cho phép chọn quyền cao nhất.

Một yêu cầu đúng phải trả lời đủ **ai cần quyền gì, để làm gì, trên tài nguyên nào, thuộc tổ chức nào, từ khi nào đến khi nào và ai được phép phê duyệt**.

Trong module vòng đời danh tính **Joiner–Mover–Leaver (JML)**, việc chọn role gắn với xác minh nguồn nhân sự, tạo tài khoản, cấp quyền theo vai trò, đối soát khi chuyển công việc và thu hồi khi kết thúc quan hệ làm việc. Các hệ thống **HRIS, IdP, SSO, SCIM, RBAC/ABAC, ứng dụng đích và kiểm toán** phải phối hợp để ngăn quyền tồn dư.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **business role**, **technical role**, **entitlement** và thuộc tính chính sách.
2. Tìm role phù hợp từ **role catalog** dựa trên nhiệm vụ, chủ thể và phạm vi tài nguyên.
3. Kiểm tra **eligibility, least privilege, separation of duties (SoD), thời hạn và mức rủi ro** trước khi gửi yêu cầu.
4. Hiểu cách lựa chọn role được phê duyệt, provisioning và xác minh quyền thực tế.
5. Xử lý yêu cầu cho nhân viên mới, nhân viên đổi vị trí, đối tác và workload.
6. Phân biệt trạng thái **requested, approved, provisioned và effective access verified**.

## 2. Chọn vai trò nằm ở bước nào của Access request?

Luồng thông thường:

~~~mermaid
flowchart TD
    A["Nhu cầu công việc hoặc sự kiện JML"] --> B["Xác minh chủ thể và quan hệ hợp lệ"]
    B --> C["Chọn ứng dụng, tenant, tài nguyên"]
    C --> D["Xem role catalog và chọn vai trò tối thiểu"]
    D --> E["Xác định lý do, thời hạn và phạm vi"]
    E --> F["Kiểm tra eligibility, SoD, role hierarchy và rủi ro"]
    F --> G{"Được phép gửi yêu cầu?"}
    G -->|"Không"| X["Giải thích từ chối hoặc điều chỉnh nhu cầu"]
    G -->|"Có"| H["Phê duyệt theo owner và chính sách"]
    H --> I{"Được phê duyệt?"}
    I -->|"Không"| X
    I -->|"Có"| J["Provisioning IdP/SCIM/API hoặc JIT/PAM"]
    J --> K["Đọc lại quyền tại ứng dụng đích"]
    K --> L{"Effective access đúng?"}
    L -->|"Có"| M["Audit và đóng request"]
    L -->|"Không/Unknown"| N["Exception, owner và remediation"]
    N --> K
~~~

**Chọn vai trò không phải hành động cấp quyền.** Người dùng có thể chọn một role trên biểu mẫu, nhưng quyền chỉ có hiệu lực sau khi **policy và phê duyệt phù hợp**, hệ thống đích xử lý provisioning, và ứng dụng thực thi đúng.

Cần phân biệt bốn kết quả:

| Trạng thái | Ý nghĩa | Chưa chứng minh điều gì? |
| --- | --- | --- |
| **REQUESTED** | Người dùng đã đề nghị role | Chưa có phê duyệt |
| **APPROVED** | Người có thẩm quyền đã duyệt role và phạm vi | Chưa chắc ứng dụng đã cấp |
| **PROVISIONED** | Connector báo thao tác cấp role/nhóm thành công | Chưa chắc quyền thực sự đúng |
| **VERIFIED_EFFECTIVE** | Readback và kiểm tra quyền tại đích đạt tiêu chí | Chỉ xác minh trong phạm vi và thời điểm đã kiểm tra |

Trong vận hành, các trạng thái thất bại như **REJECTED, EXPIRED, PARTIAL, BLOCKED, UNVERIFIED** phải được giữ rõ ràng; không biến timeout thành thành công.

## 3. Role, entitlement, group và attribute khác nhau thế nào?

| Khái niệm | Ý nghĩa | Ví dụ | Vai trò trong lựa chọn quyền |
| --- | --- | --- | --- |
| **Business role** | Trách nhiệm nghiệp vụ dễ hiểu | Financial Analyst | Giúp mô tả người dùng làm gì |
| **Technical/application role** | Vai trò kỹ thuật do ứng dụng định nghĩa | ReportReader | Chuyển nhu cầu thành permission được hệ thống hỗ trợ |
| **Entitlement** | Quyền cụ thể tại một hệ thống/tài nguyên | READ report của Atlas | Kết quả cần được kiểm chứng |
| **Group** | Tập thành viên có thể ánh xạ sang quyền | atlas-analysts | Cơ chế triển khai, không luôn trùng role |
| **Subject attribute** | Thuộc tính của chủ thể | departmentId, employmentStatus | Điều kiện để được xét quyền theo ABAC |
| **Resource attribute** | Thuộc tính tài nguyên | ownerOrgId, projectId | Giới hạn tài nguyên được truy cập |
| **OAuth scope** | Khả năng mà client/token được cấp đối với API | reports:read | Điều kiện token, không thay quyền trên object |
| **Policy** | Quy tắc Permit/Deny theo ngữ cảnh | Analyst chỉ được đọc report thuộc dự án | Quyết định quyền hiệu lực |

Một nhân viên có business role **Data Analyst** không tự động được cấp technical role **Cloud Administrator** chỉ vì cùng từ “analyst” xuất hiện trên một biểu mẫu. Ánh xạ giữa business role và entitlement phải được **chủ quyền phê duyệt, tài liệu hóa và quản lý phiên bản**.

**Group và role không phải một-một trong mọi ứng dụng.** Một nhóm SCIM có thể ánh xạ tới nhiều role, một role có thể kế thừa role khác hoặc ứng dụng dùng direct ACL thay vì group. Khi chọn role cần xem **quyền thực sự được mở**, không chỉ tên hiển thị.

## 4. Một role catalog hữu ích cần chứa gì?

**Role catalog** là danh mục có thể tra cứu những vai trò được tổ chức cho phép yêu cầu. Một bản ghi role nên cho người yêu cầu và người duyệt hiểu đầy đủ tác động.

| Thuộc tính catalog | Vì sao cần? | Ví dụ |
| --- | --- | --- |
| **roleId** ổn định | Không nhầm khi đổi tên role | reports.viewer.v2 |
| **displayName** | Người dùng hiểu vai trò | Atlas Report Viewer |
| **businessDescription** | Nêu nhiệm vụ phù hợp | Đọc báo cáo của dự án được phân công |
| **targetSystem** | Xác định ứng dụng được cấp | Reports SaaS |
| **resource/tenant scope** | Giới hạn organization, project, môi trường | org-a / atlas |
| **allowedActions** | Cho thấy quyền thực tế | READ_REPORT |
| **riskTier / classification** | Định tuyến kiểm soát | LOW, MODERATE, HIGH, PRIVILEGED |
| **eligibleSubjects** | Ai có thể yêu cầu | Employee ACTIVE, contractor được sponsor |
| **roleOwner** | Ai chịu trách nhiệm định nghĩa role | Reports Product Owner |
| **approvalPolicy** | Ai duyệt và những điều kiện gì | Manager + Resource Owner |
| **SoD conflicts** | Phát hiện quyền không tương thích | Requester không tự phê duyệt |
| **maxDuration/defaultDuration** | Ngăn cấp vô thời hạn ngoài nhu cầu | 30 ngày cho quyền tạm thời |
| **provisioningMapping** | Role triển khai thành group/permission nào | SCIM Group atlas-readers |
| **status/version** | Loại role cũ hoặc chưa được công bố | ACTIVE, v2 |
| **reviewCadence** | Căn cứ tái chứng thực quyền | Theo risk tier |

Role catalog nên được **kiểm soát bởi chủ tài nguyên hoặc bộ phận IGA**, không để mọi người tự định nghĩa role có quyền tùy ý. Những role ngừng sử dụng cần được **deprecated**, giới hạn yêu cầu mới và có kế hoạch chuyển đổi, thay vì đổi tên rồi mất dấu quyền cũ.

### Cảnh báo với tên vai trò mơ hồ

Các nhãn như **Power User**, **Owner**, **Full Access**, **Admin** hoặc **Member** có ý nghĩa khác nhau giữa các SaaS. Catalog phải liệt kê chức năng và phạm vi. Không lấy role **Member** ở ứng dụng A làm tương đương **Member** ở ứng dụng B khi chưa có mapping đã xác minh.

## 5. Bắt đầu từ nhiệm vụ, không bắt đầu từ tên role

Người yêu cầu thường biết **mục tiêu công việc** hơn là tên permission. Biểu mẫu tốt nên dẫn dắt theo nhu cầu:

1. Bạn cần làm gì: xem, tạo, sửa, xuất, phê duyệt hay quản lý quyền?
2. Bạn làm việc với ứng dụng, dự án và organization nào?
3. Bạn cần quyền từ ngày nào và trong bao lâu?
4. Bạn đang thực hiện nhiệm vụ thường xuyên, dự án ngắn hạn hay xử lý sự cố?
5. Bạn đã có quyền nào đáp ứng một phần nhu cầu?
6. Hành động có chạm dữ liệu nhạy cảm, thay đổi cấu hình hoặc cấp quyền người khác không?

Ví dụ:

| Nhiệm vụ | Hành động tối thiểu | Role nên cân nhắc |
| --- | --- | --- |
| Xem dashboard Atlas | READ | Atlas Viewer |
| Chuẩn bị dữ liệu dự án Atlas | READ, EDIT đúng dữ liệu | Atlas Editor nếu owner duyệt |
| Xuất báo cáo nhạy cảm theo kỳ | EXPORT với phê duyệt/thời hạn | Exporter có giới hạn |
| Phê duyệt thanh toán | APPROVE theo số tiền/pháp nhân | Payment Approver có SoD |
| Xử lý incident production | Một số thao tác vận hành hẹp | JIT Operator thay vì thường trực Admin |
| Tạo account cho người khác | CREATE_USER trong phạm vi quản trị | IAM Provisioner, không mặc nhiên SystemAdmin |

**Người dùng không nên tự chọn role cao hơn chỉ vì sợ thiếu quyền**. Nếu catalog chưa có role đáp ứng chức năng tối thiểu, cần tạo yêu cầu thiết kế role hoặc ngoại lệ có kiểm soát, không coi quyền cao nhất là mặc định.

## 6. Xác định đúng chủ thể trước khi cho chọn vai trò

Trong Access request, cần phân biệt:

| Thực thể | Câu hỏi |
| --- | --- |
| **Requester** | Ai tạo yêu cầu? |
| **Beneficiary/target subject** | Ai hoặc workload nào sẽ nhận quyền? |
| **Manager/sponsor** | Ai chịu trách nhiệm với nhu cầu công việc của đối tượng? |
| **Resource owner** | Ai có thẩm quyền với dữ liệu hoặc ứng dụng? |
| **Approver** | Ai được quyền phê duyệt theo chính sách? |
| **Provisioning actor** | Automation/nhân viên nào thực hiện thay đổi? |

Người yêu cầu **có thể không phải người nhận quyền**. Ví dụ manager xin role cho nhân viên mới, sponsor xin quyền cho nhà thầu, đội DevOps xin role cho workload. Không được tự lấy identity của requester làm beneficiary nếu request có mục tiêu khác.

**Identity correlation** phải dùng ID đáng tin: personId, workerId, employmentId, IAM identityId, IdP issuer + subject và target account ID. Không tự gộp người theo email, tên hoặc số điện thoại vì những giá trị đó có thể đổi hoặc tái sử dụng.

Nếu thông tin không xác định hoặc có nhiều account ứng viên, nên đưa yêu cầu vào **NEEDS_IDENTITY_VERIFICATION**, không cấp quyền cho account đoán được.

## 7. Eligibility: ai đủ điều kiện yêu cầu vai trò nào?

**Eligibility** là điều kiện trước khi vai trò được hiển thị, cho phép chọn hoặc gửi xét duyệt. Những thuộc tính có thể liên quan:

- **identityType:** employee, contractor, partner, temporary worker hay workload.
- **employmentStatus:** ACTIVE, PENDING, SUSPENDED, TERMINATED theo nguồn có thẩm quyền.
- **organizationMemberships:** thuộc pháp nhân hoặc tenant nào.
- **jobCode/department/projectAssignment:** có nhiệm vụ phù hợp hay không.
- **employmentStart/end:** role có thể có hiệu lực trong khoảng nào.
- **training/certification:** đã đáp ứng điều kiện nghiệp vụ hoặc đào tạo bắt buộc nếu policy yêu cầu.
- **privilegedEligibility:** có được phép yêu cầu role quản trị hoặc tham gia quy trình PAM không.
- **resource sensitivity:** loại dữ liệu yêu cầu có cần duyệt mức cao hơn hay không.

Các điều kiện này phải có **source authority**. HRIS hoặc sponsor thường xác nhận quan hệ lao động; project registry xác nhận phân công; IGA/owner xác nhận entitlement; IdP xác minh phiên/assurance; resource owner xác nhận dữ liệu.

**Ẩn một role khỏi giao diện không phải biện pháp bảo mật đủ.** Backend vẫn phải kiểm tra eligibility, authorization của requester và quyền phê duyệt khi nhận API request. Người dùng có thể tự sửa request để gửi roleId không hiển thị.

### Ví dụ eligibility

~~~text
Role: atlas-report-editor
Eligible IF:
    beneficiary.identityType IN [EMPLOYEE, APPROVED_CONTRACTOR]
    AND exists active relation for organization org-a
    AND Atlas IN approvedProjects of that relation
    AND request.resourceScope == org-a/Atlas
    AND requestedDuration <= allowedDurationForRole
    AND requiredTrainingSatisfied
    AND noHardDenyCondition
~~~

Đây là **mã giả chính sách**, không phải cú pháp chạy trực tiếp của sản phẩm. Người đủ điều kiện **chưa tự có quyền**; họ mới đủ căn cứ để đi qua quy trình phê duyệt tương ứng.

## 8. Chọn vai trò theo phạm vi tổ chức và tài nguyên

Một role thường phải được hiểu cùng **scope**:

~~~text
roleId        = ReportReader
targetSystem  = ReportsSaaS
organization  = org-a
project       = atlas
resource      = report-collection
actions       = [READ]
effectiveFrom = 2026-12-01T09:00:00+07:00
effectiveTo   = 2026-12-31T18:00:00+07:00
~~~

Nếu chỉ ghi **ReportReader** mà không ghi tenant/project, người cấp quyền có thể áp dụng role ở toàn organization. Ngược lại một role “Viewer” có thể chỉ dùng ở workspace cụ thể.

### Quy tắc chống nhầm tenant

| Điều kiện | Kiểm tra |
| --- | --- |
| Người nhận có nhiều organization | Request phải chỉ rõ quyền từ quan hệ nào |
| Role chỉ hợp lệ cho project Atlas | Không được dùng role đó cho Nova nếu không có duyệt riêng |
| Người dùng có quyền Admin ở org-a | Không suy quyền Admin ở org-b |
| Resource thuộc org-b | Backend phải đối chiếu ownership, không tin tenantId client tự gửi |
| Role cần áp dụng trên nhiều tenant | Đánh giá từng tenant hoặc phê duyệt phạm vi cross-tenant rõ ràng |

Chính sách **RBAC/ABAC** tại API phải kiểm tra tài nguyên cụ thể. Một token có OAuth scope **reports:read** vẫn không tự cấp quyền đọc báo cáo của tổ chức khác.

## 9. Áp dụng Least Privilege khi chọn vai trò

**Least Privilege** không nhất thiết là “chọn role có ít permission nhất bất kể có làm được việc hay không”. Mục tiêu là chọn **tập quyền tối thiểu vẫn đáp ứng toàn bộ nhiệm vụ đã duyệt**, có phạm vi tài nguyên và thời hạn đúng.

Quy trình đơn giản:

1. Liệt kê các thao tác bắt buộc của nhiệm vụ.
2. Loại những thao tác không có nhu cầu rõ ràng.
3. Đối chiếu role catalog xem role nào bao phủ các thao tác cần thiết.
4. Tính **quyền phát sinh do kế thừa, group lồng nhau hoặc mapping ứng dụng**.
5. Ưu tiên role có **phạm vi hẹp hơn**, không phải chỉ ít tên permission hơn.
6. Nếu quyền nhạy cảm chỉ dùng thỉnh thoảng, cân nhắc **JIT/PAM hoặc role tạm thời**.
7. Kiểm tra với owner khi không có role phù hợp, tránh dùng full-admin như giải pháp mặc định.

### Ví dụ độ rộng của role

| Role | READ | EDIT | DELETE | MANAGE_ACCESS | Phạm vi |
| --- | --- | --- | --- | --- | --- |
| Viewer | Có | Không | Không | Không | Atlas |
| Editor | Có | Có | Không | Không | Atlas |
| Administrator | Có | Có | Có | Có | Toàn tenant |

Nếu nghiệp vụ chỉ là **xem báo cáo Atlas**, Viewer có thể đáp ứng đầy đủ. Nếu cần chỉnh sửa, Editor có thể phù hợp; vẫn phải kiểm tra role có bất ngờ cấp quyền ở tài nguyên khác không.

**Một quyền chưa sử dụng trong log không tự chứng minh thừa.** Log thiếu coverage, tác vụ cuối quý hoặc quyền khẩn cấp có thể cần thiết. Ngược lại quyền được dùng thường xuyên vẫn có thể quá rộng so với nhiệm vụ.

## 10. Chọn một role hay kết hợp nhiều role?

Một người có thể cần nhiều vai trò hợp lệ. Tuy nhiên, **kết hợp role** có thể tạo đặc quyền lớn hơn từng role đơn lẻ.

Ví dụ:

- Role **InvoiceCreator** cho phép tạo hóa đơn.
- Role **InvoiceApprover** cho phép phê duyệt hóa đơn.
- Nếu một người giữ cả hai, họ có thể tự tạo và tự phê duyệt nếu ứng dụng không có **Separation of Duties (SoD)**.

Một yêu cầu gồm nhiều role cần kiểm tra:

1. Mỗi role có đủ nhu cầu và approval riêng không?
2. Role nào đã được cấp, role nào thực sự mới?
3. Có **role hierarchy** khiến một role bao gồm quyền của role kia không?
4. Có xung đột **SoD tĩnh** hoặc **SoD động** không?
5. Có quyền cấp tiếp/ủy quyền/đổi cấu hình dẫn đến **privilege escalation** không?
6. Role của nhiều tenant có bị trộn quyền sai không?
7. Phê duyệt một role có tự động kéo theo role khác mà reviewer chưa được thông báo không?

**Chọn vai trò là chọn tập khả năng cuối cùng**, không chỉ từng mục riêng trên biểu mẫu. Người duyệt phải thấy **effective permission delta** khi nhiều role được kết hợp.

## 11. SoD: kiểm tra xung đột trước khi gửi và trước khi cấp

**Separation of Duties** là kiểm soát phân tách những nhiệm vụ không nên do cùng một chủ thể thực hiện độc lập.

| Role được yêu cầu | Role hiện có | Loại rủi ro | Kiểm soát |
| --- | --- | --- | --- |
| PaymentApprover | PaymentCreator | Tự tạo và phê duyệt thanh toán | Tách vai trò hoặc chặn tự duyệt giao dịch |
| IAMRoleApprover | IAMRoleProvisioner | Tự duyệt và tự cấp quyền | Phân tách phê duyệt và thực thi |
| ProductionDeployer | UnreviewedCodeApprover | Có thể bỏ qua code review | Quy tắc deployment approval |
| SecretManager | AuditLogAdministrator | Có thể truy cập secret và sửa dấu vết | Tách nhiệm vụ hoặc giám sát độc lập |
| UserAdministrator | PrivilegeGrantAdministrator | Có thể tạo account rồi cấp đặc quyền | Approval và SoD theo chính sách |

**SoD tĩnh:** không cho một chủ thể đồng thời giữ hai role xung đột trong một scope.

**SoD động:** có thể giữ hai role trong những điều kiện nhất định, nhưng không được tự phê duyệt **chính giao dịch mình tạo**. Dynamic SoD phải được thực thi tại workflow/resource server, không chỉ ở lúc người dùng gửi yêu cầu.

Nếu xuất hiện xung đột, hệ thống nên giải thích lý do, đề nghị role thay thế hoặc chuyển phê duyệt ngoại lệ đúng người. **Không tự bỏ qua SoD chỉ vì manager đã duyệt một yêu cầu thông thường**.

## 12. Role thường trực, role có thời hạn và JIT

Không phải role nào cũng nên được giữ vĩnh viễn. Khi chọn vai trò, phải xác định **thời điểm bắt đầu và thời điểm kết thúc**.

| Nhu cầu | Phương án phù hợp | Nguy cơ nếu cấp thường trực |
| --- | --- | --- |
| Đọc dashboard hằng ngày | Role thường trực được review định kỳ | Quyền có thể cũ sau Mover |
| Tham gia dự án 2 tuần | Role theo dự án, expiresAt rõ | Tiếp tục truy cập sau khi dự án kết thúc |
| Bảo trì production 1 giờ | **JIT/PAM** hoặc quyền quản trị có hạn | Standing admin tăng rủi ro |
| Xử lý sự cố khẩn cấp | Break-glass có kiểm soát, audit | Bỏ qua approval/SoD nếu thiết kế yếu |
| Xuất dữ liệu một lần | Temporary export entitlement | Giữ quyền export lâu hơn nhu cầu |

**Just-in-Time (JIT)** cấp/activate quyền khi cần và tự kết thúc sau khoảng phù hợp. **Privileged Access Management (PAM)** quản lý hoạt động đặc quyền, approval, credential hoặc session theo mô hình sản phẩm. Không được coi JIT là đủ an toàn nếu role cấp rồi **không thực sự hết hiệu lực** tại ứng dụng.

Phải phân biệt:

- **requestedStartAt/requestedEndAt** của người dùng;
- **approvedStartAt/approvedEndAt** do policy/owner quyết định;
- **provisionedAt** tại hệ thống đích;
- **revokedAt/effectiveDeniedAt** khi quyền thực sự mất hiệu lực.

Một ngày kết thúc dạng **date-only** cần quy tắc rõ về timezone và “ngày cuối còn quyền”, không tự suy một instant tùy ý.

## 13. Đánh giá rủi ro của role trước khi quyết định tuyến phê duyệt

Mức rủi ro phụ thuộc vào **role + resource scope + actor + thời hạn + những quyền hiện có**.

| Yếu tố | Ví dụ rủi ro thấp hơn | Ví dụ rủi ro cao hơn |
| --- | --- | --- |
| Loại thao tác | READ một dashboard | DELETE, EXPORT dữ liệu nhạy cảm, MANAGE_ACCESS |
| Phạm vi | Một dự án | Toàn tổ chức hoặc nhiều tenant |
| Dữ liệu | Nội dung công khai nội bộ | Tài chính, nhân sự, bí mật sản xuất |
| Thời hạn | Hết hạn sau nhiệm vụ | Standing privilege vô hạn |
| Loại chủ thể | Nhân viên đang có assignment | Account chưa rõ sponsor hoặc Leaver |
| Credential/assurance | Xác thực phù hợp, session đủ mới | Legacy password-only cho hành động quản trị |
| Quyền hiện hữu | Không có xung đột | SoD/toxic combination |
| Đường cấp quyền | IGA/SCIM được kiểm toán | Local manual grant không quản trị |

Tổ chức có thể tính **risk tier**, nhưng điểm rủi ro là **tín hiệu định tuyến** chứ không thay bằng chứng nghiệp vụ. Role đặc quyền có thể cần **resource owner, security hoặc PAM owner** duyệt, trong khi Viewer được cấp tự động nếu đủ điều kiện đã công bố.

**Một role có tên “ReadOnly” chưa chắc có rủi ro thấp**: khả năng đọc secret, khóa riêng hoặc dữ liệu nhạy cảm có thể tương đương khả năng mở đường truy cập khác.

## 14. Ai được phép chọn và ai được phép duyệt?

| Người/nhóm | Quyền hạn có thể có | Không nên được mặc định |
| --- | --- | --- |
| **Beneficiary** | Chọn role cho nhu cầu của mình nếu policy cho phép | Tự duyệt quyền rủi ro cao |
| **Manager** | Xác nhận nhiệm vụ, tổ chức, thời hạn | Duyệt mọi quyền dữ liệu ngoài thẩm quyền |
| **Sponsor** | Bảo trợ contractor/partner | Bỏ qua kiểm tra identity hoặc tenant |
| **Resource owner** | Duyệt quyền trên dữ liệu/ứng dụng mình sở hữu | Tự bỏ chính sách an ninh bắt buộc |
| **Security/IAM governance** | Kiểm tra SoD, rủi ro và chính sách | Trở thành owner nghiệp vụ thay cho tất cả |
| **PAM/privileged role owner** | Duyệt đặc quyền nhạy cảm | Cho phép standing admin không thời hạn mặc định |
| **Provisioning service** | Thực thi grant đã được phê duyệt | Tự quyết định cấp quyền cao hơn approval |

Một số role có thể **auto-approve** dựa trên policy, chẳng hạn baseline access của Joiner đã xác minh. Điều này vẫn là **quyết định theo chính sách đã phê duyệt trước**, không phải “không cần kiểm soát”.

Quy trình phê duyệt nên ngăn **self-approval** khi có xung đột lợi ích, quản lý tình huống manager vắng mặt và xác định người thay thế được ủy quyền. Nếu resource owner không còn tồn tại, không mặc định chuyển mọi yêu cầu sang Administrator toàn hệ thống.

## 15. Chọn vai trò cho contractor, partner và tài khoản bên ngoài

Nhà thầu và đối tác có thể không có bản ghi HRIS giống nhân viên. Nguồn có thẩm quyền có thể là **vendor management system** hoặc **sponsor registry**, nhưng vẫn phải cung cấp:

- Danh tính đã được xác minh và **sponsor** hợp lệ.
- Tổ chức/tenant, hợp đồng, nhiệm vụ và thời hạn.
- Role nào được phép cho **identityType** tương ứng.
- Quyền trên dữ liệu cá nhân hoặc sản xuất nếu có, với approval bổ sung.
- Cơ chế xác thực/SSO/MFA thích hợp cho phía đối tác.
- Quy trình deprovision khi hợp đồng kết thúc hoặc sponsor không còn.

Ví dụ contractor chỉ cần đọc tài liệu dự án Atlas trong 14 ngày. Role nên được **giới hạn vào Atlas, READ và 14 ngày**, thay vì cấp role Member của toàn tenant nếu Member chứa quyền truy cập các dự án khác.

Không coi **email domain** là bằng chứng đủ để nhận dạng contractor hoặc quyết định quyền; các miền email có thể dùng chung, chuyển sở hữu hoặc không phản ánh quan hệ công việc đang hiệu lực.

## 16. Chọn vai trò cho người có nhiều employment/organization

Một person có thể có nhiều quan hệ làm việc, ví dụ một hợp đồng ở **org-a** và một hợp đồng độc lập tại **org-b**. Quy trình chọn role nên gắn yêu cầu với **quan hệ đúng**.

~~~json
{
  "identityId": "iam-482",
  "employmentRelations": [
    {
      "employmentId": "emp-org-a-01",
      "organizationId": "org-a",
      "status": "ACTIVE",
      "approvedProjects": ["atlas"]
    },
    {
      "employmentId": "emp-org-b-07",
      "organizationId": "org-b",
      "status": "ACTIVE",
      "approvedProjects": ["nova"]
    }
  ]
}
~~~

Khi yêu cầu role **Atlas Viewer**, điều kiện có thể dựa trên **emp-org-a-01**. Nếu quan hệ org-a kết thúc, quyền Atlas phải thu hồi theo policy, ngay cả khi person vẫn **ACTIVE tại org-b**. Không gộp role của nhiều organization thành một tập quyền chung rồi áp dụng cho mọi tenant.

Với **rehire**, không tự khôi phục toàn bộ role/grant từ hợp đồng cũ. Cần xác minh employment mới, role catalog hiện hành và các approval cần thiết.

## 17. Role không có trong catalog hoặc yêu cầu role mới

Nhiều ứng dụng có quyền quá thô. Nếu nhu cầu READ và UPDATE hạn chế nhưng catalog chỉ có Viewer hoặc Administrator, không nên cấp Administrator như lối tắt.

Quy trình phù hợp:

1. Ghi rõ **business action**, tài nguyên, thời hạn và vì sao role hiện tại không đáp ứng.
2. Kiểm tra xem có thể **kết hợp role hẹp** mà không tạo xung đột hay không.
3. Kiểm tra **ABAC/resource policy** có thể giới hạn scope của role hiện có không.
4. Nếu cần, tạo yêu cầu **Role Design/Role Change** gửi owner và IAM governance.
5. Phân tích permission, SoD, least privilege, chi phí vận hành và phương án migration.
6. Cập nhật catalog, mapping và kiểm thử trên môi trường được phép.
7. Chỉ sau đó cho chọn role mới theo quy trình phê duyệt.

**Role creation không phải chức năng tùy ý của requester trong Access request.** Tạo role mới có thể ảnh hưởng nhiều người hiện có nếu group hoặc hierarchy thay đổi.

## 18. Thiết kế biểu mẫu chọn vai trò

Một biểu mẫu tốt nên giới hạn lựa chọn bằng **điều kiện đáng tin**, đồng thời cung cấp đủ thông tin để người dùng không phải đoán.

Các trường thường cần:

| Trường | Bắt buộc khi nào? | Giá trị ví dụ |
| --- | --- | --- |
| **beneficiaryIdentityId** | Luôn cần liên kết người nhận chính xác | iam-482 |
| **employmentRelationId/sponsorId** | Khi role phụ thuộc quan hệ | emp-org-a-01 |
| **targetSystem** | Luôn cho role ứng dụng | reports-saas |
| **roleId** | Luôn | reports.viewer.v2 |
| **targetTenant/resourceScope** | Khi role có ranh giới tài nguyên | org-a/atlas |
| **businessJustification** | Theo chính sách, đặc biệt quyền nhạy cảm | Xem báo cáo tổng kết Atlas |
| **requestedFrom/requestedUntil** | Role tạm thời/JIT hoặc chính sách yêu cầu | 01–31/12/2026 |
| **ticket/projectRef** | Khi gắn dự án hoặc incident | project-atlas |
| **requesterIdentityId** | Luôn cần audit | iam-manager-17 |
| **existingRoleContext** | Do hệ thống tính | Các role/quyền beneficiary đang có |

Giao diện có thể hiển thị **đề xuất role ít quyền nhất**, mô tả sự khác nhau giữa Viewer/Editor/Admin và đánh dấu role cần phê duyệt bổ sung.

**Không chỉ lọc ở frontend.** Backend phải xác minh:

- roleId thực sự đang **ACTIVE và requestable**;
- targetSystem và tenant nằm trong danh mục hợp lệ;
- beneficiary và requester có quyền thực hiện quy trình tương ứng;
- thời hạn không vượt policy;
- eligibility, SoD và approval chain được tính lại từ dữ liệu hiện hành;
- ID và quyền tại đích không do client tự định nghĩa.

## 19. Ví dụ dữ liệu Access request

Một bản ghi yêu cầu tối giản nhưng có kiểm soát có thể như sau:

~~~json
{
  "requestId": "ar-2026-1042",
  "requesterIdentityId": "iam-manager-17",
  "beneficiaryIdentityId": "iam-482",
  "employmentRelationId": "emp-org-a-01",
  "targetSystem": "reports-saas",
  "targetTenant": "org-a",
  "resourceScope": "project-atlas",
  "requestedRoleId": "reports.viewer.v2",
  "roleCatalogVersion": "roles-v24",
  "businessJustification": "Xem báo cáo dự án Atlas phục vụ tổng kết",
  "requestedStartAt": "2026-12-01T09:00:00+07:00",
  "requestedEndAt": "2026-12-31T18:00:00+07:00",
  "riskTier": "LOW",
  "status": "REQUESTED",
  "createdAt": "2026-11-23T09:40:00+07:00"
}
~~~

**Đây là schema minh họa**, không phải định dạng chuẩn của SCIM, OIDC hay một hệ thống access request cụ thể. RoleCatalogVersion cần được dùng để biết **role có ngữ nghĩa gì lúc người dùng chọn**. Khi quyền của role thay đổi giữa lúc gửi yêu cầu và lúc cấp, hệ thống cần đánh giá lại theo chính sách, không âm thầm áp dụng quyền mới rộng hơn approval.

**Không ghi password, token, client secret, TOTP seed hoặc private key** trong request hay audit. Nếu justification chứa dữ liệu nhạy cảm, phải có chính sách lưu giữ và phân quyền đọc.

## 20. Logic chọn role theo chính sách: pseudocode

~~~text
selectRole(request):
    requester = resolveVerifiedHumanIdentity(request.requesterIdentityId)
    beneficiary = resolveVerifiedSubject(request.beneficiaryIdentityId)

    if requester.isUnknown or beneficiary.isAmbiguous:
        return REJECT_OR_VERIFY_IDENTITY

    if not canRequestFor(requester, beneficiary):
        return DENY_REQUEST_CREATION

    relation = loadCurrentAuthorizedRelation(
        beneficiary,
        request.employmentRelationId,
        request.targetTenant
    )
    if not relation.isEligibleAt(request.requestedStartAt):
        return INELIGIBLE

    role = roleCatalog.getActiveRole(
        request.targetSystem,
        request.requestedRoleId,
        request.roleCatalogVersion
    )
    if not role.isRequestableFor(relation.identityType):
        return INELIGIBLE

    if not role.scopePolicy.allows(request.resourceScope, relation):
        return SCOPE_REJECTED

    if not durationPolicy.allows(role, request.requestedStartAt,
                                 request.requestedEndAt):
        return DURATION_REJECTED

    existing = readCurrentGrantsAndEffectiveAccess(beneficiary)
    delta = calculateRolePermissionDelta(role, existing, request.resourceScope)
    conflicts = evaluateSoDAndRisk(
        beneficiary, existing, delta, relation, request
    )

    if conflicts.hasHardDeny:
        return POLICY_DENIED

    return REQUIRE_APPROVAL(
        requestedRole=role,
        permissionDelta=delta,
        risk=conflicts.riskTier,
        route=approvalPolicy.selectApprovers(role, relation, request)
    )
~~~

Mã giả chỉ minh họa, **không tự cấp role sau khi chọn**. Khi role, employment, resource scope hoặc policy thay đổi trong thời gian phê duyệt, cần **revalidate trước provisioning**, không chỉ dựa trên kết quả kiểm tra ban đầu.

Nếu không đọc được effective access hoặc relation đang có, trạng thái là **NEEDS_EVIDENCE**; không mặc định không có quyền rồi cấp thêm role rộng.

## 21. Chính sách phê duyệt cho từng loại role

| Loại role | Tuyến phê duyệt ví dụ | Điều kiện bổ sung |
| --- | --- | --- |
| Baseline Viewer theo job đã xác minh | Auto-approval theo policy hoặc manager | Eligibility, resource scope và hạn |
| Editor dữ liệu nghiệp vụ | Manager + Resource Owner | Nhu cầu sửa và đánh giá data classification |
| Export dữ liệu nhạy cảm | Resource Owner + Data/Security policy approver | Thời hạn, logging, MFA/step-up |
| IAM Role Administrator | Privileged Role Owner + Security | SoD, phishing-resistant MFA, PAM |
| Production Operator JIT | Incident owner/PAM workflow | Ticket, thời lượng, phạm vi service |
| Cross-tenant role | Owner liên quan ở mỗi tổ chức | Phạm vi tenant và ranh giới dữ liệu |
| Contractor temporary role | Sponsor + resource owner khi cần | Hợp đồng, expiry, loại danh tính |

Các tuyến này là **ví dụ thiết kế**, không phải quy tắc chung cho mọi tổ chức. Một số request có thể được duyệt tự động khi role thuộc baseline đã phê duyệt. Với role rủi ro cao, cần đảm bảo **người phê duyệt không chính là beneficiary hoặc actor có xung đột lợi ích**, trừ cơ chế khẩn cấp được quy định rõ.

**Quyết định phê duyệt cần gắn với phiên bản và phạm vi role**. Một approval cho Viewer tại org-a/Atlas không thể được dùng lại để cấp Administrator tại org-b.

## 22. Sau phê duyệt: từ role sang group, ACL và entitlement

Quy trình cấp quyền có thể gồm:

1. Xác nhận **approval còn hiệu lực** tại thời điểm cấp.
2. Kiểm tra role version, beneficiary, tenant và hạn theo policy hiện hành.
3. Liên kết **identity → account tại target** bằng ID đáng tin.
4. Nếu account chưa tồn tại, xử lý **provisioning User** theo đúng quy trình.
5. Ánh xạ role sang **group, application role, ACL, entitlement hoặc policy assignment**.
6. Gửi thay đổi qua connector/SCIM/API hoặc thao tác có kiểm soát.
7. Đọc lại assigned access; tính/kiểm tra **effective access** tại resource server.
8. Tạo job expiration/revocation và audit nếu quyền có hạn.

### SCIM làm được gì?

**SCIM 2.0** thường hỗ trợ quản lý **User/Group**. Có thể thêm người vào Group.members hoặc cập nhật thuộc tính user theo contract ứng dụng. Nhưng **SCIM không quy định một chuẩn chung rằng mỗi Group tương đương một business role hay mỗi response thành công mở quyền như thế nào**.

Nếu SaaS ánh xạ Group **atlas-readers** sang ReportReader, cần kiểm tra mapping tại SaaS. **SCIM PATCH thành công không tự chứng minh RBAC/ABAC đã cho phép đúng tài nguyên**.

Với ứng dụng không hỗ trợ SCIM, dùng connector/API quản trị được phê duyệt hoặc quy trình manual có audit. Không vì thiếu connector mà cho phép provision trực tiếp bằng credential dùng chung không kiểm soát.

## 23. IdP, SSO, MFA không thay việc chọn và cấp role

**Identity Provider (IdP)** quản lý xác thực và có thể nắm group; **Single Sign-On (SSO)** cho phép ứng dụng tin kết quả đăng nhập; **Multi-Factor Authentication (MFA)** nâng độ bảo đảm chủ thể.

| Điều kiện | Vai trò trong Access request |
| --- | --- |
| Người dùng có thể đăng nhập IdP | Điều kiện xác thực, **không chứng minh** có entitlement tại SaaS |
| Đã đăng ký MFA | Bảo vệ đăng nhập, không tự cấp Viewer/Editor/Admin |
| Có phiên SSO hợp lệ | Có thể dùng để xác thực với RP/SP, vẫn phải kiểm tra quyền |
| Có role được duyệt trong IGA | Căn cứ cấp, chưa chắc target đã cập nhật |
| Có group trong IdP/SCIM | Một đường triển khai role, cần mapping và readback |
| API đang ALLOW hành động | Bằng chứng quyền hiệu lực tại thời điểm được kiểm tra |

Role đặc quyền có thể yêu cầu **phishing-resistant MFA** và phiên đủ mới trước khi thao tác. Với OIDC, các tín hiệu như **amr, acr, auth_time** có thể hỗ trợ nếu issuer/RP thống nhất ngữ nghĩa và kiểm chứng phù hợp.

**Step-up authentication không tự tạo entitlement**. Một người xác thực mạnh vẫn không được quản trị dữ liệu của tenant khác nếu không có quyền.

## 24. RBAC, ABAC và Policy-Based Access Control khi chọn role

**RBAC** giúp gán role theo trách nhiệm. **ABAC** giúp hạn chế quyền bằng thuộc tính và ngữ cảnh. **Policy-Based Access Control (PBAC)** có thể kết hợp các điều kiện thành quy tắc đánh giá tại **Policy Decision Point (PDP)**, còn **Policy Enforcement Point (PEP)** thực thi.

Ví dụ một quyết định đọc báo cáo:

~~~text
ALLOW READ(report) IF:
    user.hasRole("ReportViewer", report.organizationId)
    AND exists activeEmploymentRelation(user, report.organizationId)
    AND report.projectId IN user.approvedProjects
    AND user.authenticationMeetsPolicy(report.classification)
    AND noPriorityDeny
~~~

Ngay cả khi chọn và provision **ReportViewer**, nếu người đó đã **Mover** sang project khác, ABAC/PBAC có thể từ chối quyền trên report cũ. Ngược lại, nếu một PEP bị thiếu kiểm tra object-level authorization, role Viewer có thể trở nên rộng hơn dự kiến.

**Role selection không thể thay backend authorization**. Hệ thống phải kiểm tra resource owner, tenant và action ở API, không chỉ giới hạn danh sách role hiển thị trên portal.

## 25. OAuth scope và workload roles: đừng đánh đồng

Trong OAuth 2.0, **scope** giới hạn khả năng của token/client đối với API. Scope như **reports:read** không tự nghĩa người dùng có role ReportReader ở mọi tenant.

Hai mô hình cần phân biệt:

| Trường hợp | Chủ thể | Quyền cần lựa chọn |
| --- | --- | --- |
| Người dùng đăng nhập ứng dụng qua OIDC | Human identity và OAuth client | Role/entitlement nghiệp vụ + scope token phù hợp |
| Client thay mặt người dùng gọi API | User-delegated access | Giao quyền không vượt entitlement người dùng |
| Service-to-service bằng client credentials | Workload/service principal | Machine role, OAuth scopes, audience, tenant/resource |
| Bot chạy production | Workload identity | Quyền giới hạn theo job, service owner và môi trường |

Một request xin role cho workload cần nêu **serviceId, ownerTeam, environment, application purpose, required API actions, TTL và credential model**, thay vì tự chọn nhân viên làm người nhận quyền.

Không bắt bot phải nhờ nhân viên bấm MFA push mỗi lần gọi API. Dùng **managed identity, workload federation, certificate/khóa riêng hoặc token ngắn hạn** theo nền tảng hỗ trợ, với quyền tối thiểu và cơ chế thu hồi riêng.

## 26. Role dành cho workload và tài khoản dịch vụ

Một workload có thể cần role khác người dùng:

| Workload | Nhiệm vụ | Role phù hợp | Role nên tránh |
| --- | --- | --- | --- |
| report-exporter | Đọc nguồn và xuất báo cáo định kỳ | ReportExporter trên scope đã duyệt | OrganizationAdministrator |
| metrics-collector | Đọc chỉ số giám sát | MetricsReader | ClusterAdmin |
| deploy-pipeline | Triển khai một service | ScopedDeployer theo môi trường | GlobalCloudOwner |
| billing-sync | Đọc hóa đơn của một tenant | BillingReadOnly của tenant đó | BillingAdmin tất cả tenant |

Kiểm tra:

- **Owner** còn có trách nhiệm với workload không?
- **Môi trường** có bị trộn dev/test/prod không?
- Workload có cần **quyền quản lý IAM/secret** hay chỉ gọi API đọc/ghi dữ liệu?
- Có thể dùng quyền **theo tài nguyên cụ thể** thay wildcard không?
- Credential và grant có hạn, rotation/revocation và kiểm toán không?
- Người từng vận hành workload đã Mover/Leaver có giữ PAT hoặc secret cá nhân không?

Khi owner nghỉ việc, không tự xóa bot production còn nhiệm vụ; cần **chuyển ownership, rà soát secret, thu hồi PAT cá nhân và xác minh quyền máy**.

## 27. Role hierarchy, group nesting và quyền phát sinh gián tiếp

Một role có thể **kế thừa** các permission khác. Một SCIM Group có thể là thành viên nhóm khác hoặc ánh xạ đến nhiều quyền ở SaaS. Do đó, trước khi duyệt phải tính **permission expansion**.

Ví dụ:

~~~text
Business role: ProjectEditor
    -> Group: atlas-editors
    -> App role: DataEditor
    -> Permissions:
       READ_REPORT
       EDIT_REPORT
       EXPORT_REPORT
    -> Nested group: global-collaborators
       -> Permission: READ_ALL_WORKSPACES
~~~

Nếu người dùng chỉ cần chỉnh sửa Atlas, **READ_ALL_WORKSPACES** có thể là quyền phát sinh ngoài mong muốn. Trình duyệt role catalog chỉ hiển thị “ProjectEditor” nhưng không hiển thị quyền phát sinh sẽ khiến cả requester và approver quyết định trên thông tin thiếu.

Nên có **effective permissions preview** từ cấu hình role, membership và policy được kiểm chứng. Nếu không thể tính được, ghi rõ **UNVERIFIED_EXPANSION** và cần owner xác nhận thay vì khẳng định role là quyền tối thiểu.

## 28. Chọn role trong Joiner lifecycle

**Joiner** bắt đầu khi HRIS hoặc nguồn sponsor xác nhận người mới, quan hệ làm việc, vị trí và ngày bắt đầu. Access request có thể được tạo tự động từ **birthright access** hoặc do manager chọn thêm role.

Quy trình:

1. Xác minh **person, worker/employment ID, identityId**, tránh nối theo email đơn thuần.
2. Lấy **jobCode, department, organization, project assignment và start date** từ nguồn có thẩm quyền.
3. Tính **baseline role** theo chính sách được phê duyệt, không mặc định admin.
4. Nếu cần role ngoài baseline, manager/requester chọn từ catalog và cung cấp justification.
5. Kiểm tra eligibility, SoD, risk và phạm vi.
6. Phê duyệt hoặc auto-approve theo policy.
7. Provision User/Group/role tại target, cấu hình SSO/MFA nếu yêu cầu.
8. Kiểm tra **allowed actions và denied actions** trên tài nguyên kiểm thử.
9. Chỉ đóng các cổng Joiner đã có bằng chứng; hạng mục khác giữ **PENDING/BLOCKED**.

### Ngày bắt đầu chưa tới

Tài khoản có thể được tạo trước để chuẩn bị onboarding nhưng quyền nghiệp vụ chưa được phép hoạt động. Role chọn ngày 01/12 không đồng nghĩa có thể dùng ngày 23/11. Cần **time-bound policy** và kiểm tra thực tế, không chỉ đặt một ngày trên biểu mẫu.

## 29. Chọn role khi Mover và thu hồi role cũ

**Mover** là sự kiện thay đổi vai trò, dự án, đơn vị hoặc mức đặc quyền. Điều cần làm không chỉ là **chọn role mới** mà còn tính **toàn bộ tập quyền mong muốn sau thay đổi**.

| Phân công | Trước Mover | Sau Mover mong muốn |
| --- | --- | --- |
| Project Atlas | ReportEditor | Không còn quyền, trừ ngoại lệ bàn giao |
| Project Nova | Chưa có | ReportViewer |
| Organization | org-a | org-a |
| Admin privileges | Không | Không |

Một quy trình đúng:

1. Đọc thay đổi HR/project có **effectiveAt và sourceVersion**.
2. Tính role mới từ job/assignment và các approval.
3. So với **existing role và direct ACL** để xác định **grant, revoke, keep**.
4. Kiểm tra quyền bàn giao có hạn và tránh privilege accumulation.
5. Cập nhật IdP/SCIM/SaaS, không chỉ thêm nhóm Nova.
6. Xử lý JWT/refresh token/session hoặc cache còn chứa role cũ theo SLA.
7. Đối soát **READ Nova = ALLOW**, **READ Atlas = DENY** khi mốc chuyển đã có hiệu lực.

Không lấy kết quả “role mới provisioned” làm bằng chứng Mover hoàn tất nếu role cũ vẫn có thể dùng.

## 30. Leaver, quyền hết hạn và tái tuyển dụng

Khi quan hệ làm việc kết thúc, các role được cấp dựa trên quan hệ đó thường phải **hết hiệu lực theo thời điểm được duyệt**.

Các câu hỏi quan trọng:

- Role cấp theo employment nào; người đó còn quan hệ khác hợp lệ không?
- Account local, ACL, group, owner role hoặc quyền chia sẻ trực tiếp nào còn tồn tại?
- Có **OAuth grant, refresh token, access token, PAT/API key, session** nào tiếp tục dùng được?
- Có job provisioning cũ có thể **tái cấp role** sau Leaver không?
- Những quyền cần giữ vì pháp lý/nghiệp vụ có được chuyển thành **quyền của người kế nhiệm** theo quy trình, thay vì để nguyên cho Leaver?

**SCIM deactivate** và khóa IdP không mặc nhiên làm mọi ứng dụng chấm dứt session hoặc token. Với JWT offline, resource server có thể còn cho phép đến khi hết hạn nếu không có denylist, security epoch, introspection hoặc policy recheck phù hợp.

Khi **rehire**, không tự khôi phục quyền từ employment cũ. Vai trò phải được tính từ **job/organization/phê duyệt mới**, dù personId hoặc username trùng giai đoạn trước.

## 31. Phát hiện role request bất thường hoặc quá rộng

Một số tín hiệu đáng chú ý:

| Tín hiệu | Vì sao đáng xem xét | Cách xử lý |
| --- | --- | --- |
| Nhân viên chỉ cần đọc nhưng xin Administrator | Overprivilege | Gợi ý Viewer, yêu cầu justification |
| Contractor xin role không có hạn | Vượt thời hạn hợp đồng | Giới hạn theo sponsor/contract |
| Role cross-tenant ngoài assignment | Khả năng vượt tổ chức | Eligibility/owner approval theo tenant |
| Requester xin và tự duyệt cùng quyền | Xung đột phê duyệt | SoD và approver independence |
| Role có quyền IAM/secret mà không thuộc nhiệm vụ | Privilege escalation | Security review, PAM |
| User đã được cấp role tương đương | Duplicate/privilege accumulation | Đọc existing effective access |
| Request đổi roleId sau khi approval | Approval mismatch | Phê duyệt lại delta thay đổi |
| Role deprecated vẫn được yêu cầu | Catalog drift | Chặn request mới hoặc chuyển role |
| Mover xin role mới nhưng giữ role cũ | Residual access | Recompute expected access |
| Leaver hoặc sponsor hết hiệu lực vẫn xin quyền | Lỗi lifecycle | Hard deny theo nguồn có thẩm quyền |

Các tín hiệu là **căn cứ kiểm tra**, không phải bằng chứng cá nhân có ý đồ xấu. Một request có quyền cao có thể hợp lệ khi nhiệm vụ yêu cầu, nhưng phải có **đúng phê duyệt, giới hạn và kiểm soát bù trừ**.

## 32. Lỗi kỹ thuật thường gặp trong bước chọn và cấp role

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Role không hiển thị trong portal | Không đủ eligibility, catalog bị ẩn/deprecated, dữ liệu nguồn sai | Kiểm tra role policy và thuộc tính có thẩm quyền |
| Role hiển thị nhưng submit bị chặn | Backend recheck khác dữ liệu frontend | Xem policy version, scope, SoD, employment |
| Được duyệt nhưng không có quyền | Provisioning thất bại, target mapping sai, cache chưa cập nhật | Kiểm tra connector và quyền thực tế ở SaaS/API |
| Role đã cấp nhưng không đủ hành động | Role technical thiếu permission hoặc ABAC chặn | Kiểm tra resource/action và catalog mapping |
| Role cấp rộng hơn yêu cầu | Group nesting, local default role, wildcard | Thu hẹp, sửa mapping, kiểm thử negative cases |
| Mover đã cấp quyền mới nhưng vẫn có quyền cũ | Direct ACL/PAT/token cũ còn hiệu lực | Thu hồi đúng nguồn và target |
| Cùng tên role nhưng khác tenant | Namespace/mapping nhầm | Lưu roleId + tenant + app + version |
| Request bị gửi hai lần | Retry hoặc người dùng nhấn lại | Idempotency orchestration và kiểm tra duplicate |
| Request hết hạn nhưng role vẫn active | Expiration job lỗi hoặc target không áp TTL | Reconciliation và revoke theo SLA |
| User bị từ chối 403 | Có thể là denial đúng, không luôn là lỗi | Kiểm tra expected vs effective access |

**Không xử lý mọi lỗi 403 bằng cấp Administrator**. Nếu nguyên nhân là sai tenant, thiếu MFA, token sai audience hoặc ứng dụng lỗi chính sách, cấp thêm role có thể vừa không giải quyết được vấn đề vừa tạo quyền thừa.

## 33. Request idempotency và chống cấp lại role từ sự kiện cũ

Trong hệ thống bất đồng bộ, cùng một Access request có thể được xử lý lặp do retry, timeout hoặc message redelivery. Cần ngăn:

- Tạo nhiều bản ghi approval khác nhau cho cùng một yêu cầu.
- Cấp cùng role nhiều lần qua những đường khác nhau.
- Mất thông tin role đã cấp khi response của connector bị timeout.
- **Event cũ tái cấp quyền** sau khi Mover/Leaver đã rút.
- Kéo dài expiresAt ngoài phê duyệt khi retry.

Một record orchestration nên liên kết **requestId, beneficiary, roleId, target, tenant, scope, approvedVersion, sourceVersion và effectiveAt**. Trước khi retry, đọc trạng thái mong muốn hiện tại và **target readback**. Không coi một POST/SCIM request không trả lời là chắc chắn chưa được áp dụng.

Nếu role đã được cấp trước khi một yêu cầu mới được duyệt, cần xác minh **cùng role và scope/expiry**. Không tự kết luận request mới đã hoàn tất chỉ vì thấy một role trùng tên.

## 34. Kiểm chứng effective access sau khi chọn và cấp role

**Role selection đúng chưa đủ**. Một yêu cầu chỉ được coi là đã thực hiện đầy đủ khi quyền thực tế khớp quyết định được phê duyệt.

### Ba lớp kiểm tra

| Lớp | Cần chứng minh |
| --- | --- |
| **Approval correctness** | Đúng beneficiary, role, scope, tenant, thời hạn, owner và policy version |
| **Assigned access readback** | Target lưu đúng group/role/ACL/entitlement, không phát sinh quyền ngoài phê duyệt |
| **Effective access test** | API cho phép hành động hợp lệ và từ chối hành động ngoài phạm vi tại thời điểm kiểm tra |

Ví dụ ma trận:

| Subject | Action | Resource | Kết quả mong muốn |
| --- | --- | --- | --- |
| Mai – Atlas Viewer | READ | Report Atlas | ALLOW |
| Mai – Atlas Viewer | EDIT | Report Atlas | DENY |
| Mai – Atlas Viewer | READ | Report Nova | DENY |
| Mai – Atlas Viewer | MANAGE_ACCESS | Atlas workspace | DENY |
| Người chưa ACTIVE | READ | Atlas report | DENY theo chính sách |
| Người đã Leaver org-a | READ | Report org-a | DENY |

Nếu connector không thể kiểm tra API hoặc đọc quyền target do giới hạn quyền, trạng thái phải là **UNVERIFIED**, có owner và deadline; không tự gắn nhãn VERIFIED_EFFECTIVE.

**Sự thành công của group mapping không bảo đảm JWT/phiên cũ đã mang role mới hoặc đã mất role cũ.** Cần kiểm tra cache/policy/token lifecycle theo mức rủi ro của hệ thống.

## 35. Kiểm toán lựa chọn và phê duyệt vai trò

Một bản ghi audit hữu ích cần trả lời **ai yêu cầu, cho ai, role nào, phạm vi gì, lý do, ai duyệt, thực tế đã cấp gì và quyền đã được kiểm tra ra sao**.

Ví dụ JSON audit metadata:

~~~json
{
  "accessRequestId": "ar-2026-1042",
  "requesterRef": "iam-manager-17",
  "beneficiaryRef": "iam-482",
  "employmentRef": "emp-org-a-01",
  "targetSystem": "reports-saas",
  "targetTenant": "org-a",
  "resourceScope": "project-atlas",
  "roleId": "reports.viewer.v2",
  "roleCatalogVersion": "roles-v24",
  "riskTier": "LOW",
  "decision": "APPROVED",
  "approvedByRef": "resource-owner-21",
  "approvedAt": "2026-11-23T09:50:00+07:00",
  "approvedEndAt": "2026-12-31T18:00:00+07:00",
  "provisioningStatus": "SUCCESS",
  "targetAccountRef": "saas-u-482",
  "assignedRoleReadback": "VERIFIED",
  "effectiveAccessCheck": "VERIFIED",
  "auditStatus": "RECORDED"
}
~~~

Đây là **bản ghi minh họa**, không phải schema bắt buộc. Trong thực tế nên lưu thêm correlation ID, source event/version, approval policy, trạng thái SoD, cấp phát và kết quả thu hồi. **Không ghi credential hoặc toàn bộ dữ liệu nhân sự** vào log.

Người có quyền đọc audit phải được giới hạn vì role, project, approval và tổ chức của người dùng có thể là dữ liệu nhạy cảm. Đặt thời gian lưu và quyền truy cập phù hợp chính sách.

## 36. Chỉ số đánh giá chất lượng bước chọn role

| Chỉ số | Ý nghĩa | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Least-privilege match rate** | Tỷ lệ request chọn role khớp nhu cầu đã được xác minh | Chỉ có nghĩa nếu có tiêu chí nghiệp vụ rõ |
| **Overprivileged requests detected** | Yêu cầu vượt nhiệm vụ/policy được phát hiện | Nhiều finding có thể do coverage tốt hơn |
| **SoD conflict rate** | Tỷ lệ role request xung đột | Cần phân biệt conflict hợp lệ và false positive |
| **Role selection correction rate** | Tỷ lệ người dùng phải đổi role trước approval | Giúp cải thiện catalog/UI |
| **Time to approval** | Tốc độ từ gửi request tới quyết định | Không được tối ưu bằng bỏ kiểm soát |
| **Time to verified access** | Từ approval tới effective access xác minh | Cần đo đúng các target quan trọng |
| **Expired roles still effective** | Quyền quá hạn nhưng vẫn ALLOW | Chỉ đóng sau khi quyền thật mất |
| **Mover stale roles** | Quyền cũ còn sau chuyển việc | Gắn với thời điểm hiệu lực |
| **Leaver residual roles** | Quyền còn tồn dư sau nghỉ việc | Phân loại theo độ nhạy và hệ thống |
| **Unverified role assignments** | Phần quyền không thể đọc lại tại target | Không suy UNKNOWN = an toàn |
| **Temporary vs standing privilege ratio** | Mức độ sử dụng quyền có hạn/JIT | Phải xét độ tin cậy vận hành |

KPI nên phân loại theo **role risk tier, application, tenant, identityType và JML event**, tránh trung bình che giấu một vài quyền đặc biệt nguy hiểm.

## 37. Kiểm thử workflow chọn role

| Test case | Tình huống | Kết quả mong muốn |
| --- | --- | --- |
| T01 | Nhân viên ACTIVE xin Viewer đúng project | Cho gửi request nếu đủ eligibility |
| T02 | Người chỉ cần READ xin Administrator | Cảnh báo/risk review hoặc chặn theo policy |
| T03 | Contractor xin role không có hạn | Yêu cầu giới hạn thời hạn/sponsor |
| T04 | Beneficiary đã Leaver org-a | Không được cấp quyền từ quan hệ đã hết |
| T05 | Person còn ACTIVE org-b nhưng Leaver org-a | Chỉ giữ quyền org-b hợp lệ |
| T06 | Requester sửa roleId thành admin qua API | Backend từ chối hoặc yêu cầu quy trình đặc quyền |
| T07 | Role v1 đã bị deprecated | Không cấp âm thầm theo mapping cũ |
| T08 | Role có nested group phát sinh quyền ngoài scope | Phát hiện qua effective permission preview |
| T09 | Hai role vi phạm SoD | Chặn hoặc kích hoạt quy trình ngoại lệ phù hợp |
| T10 | Requester đồng thời là approver trái chính sách | Self-approval bị ngăn |
| T11 | Approval thành công nhưng SCIM timeout | Giữ trạng thái UNKNOWN và reconciliation |
| T12 | Group đã cấp nhưng API vẫn 403 | Điều tra AuthN/scope/ABAC, không auto-admin |
| T13 | Group đã gỡ nhưng direct ACL còn ALLOW | Không coi revocation hoàn tất |
| T14 | Quyền tạm thời qua hạn nhưng vẫn active | Cảnh báo và revoke theo playbook |
| T15 | Job Mover cũ chạy sau Leaver | Không tái cấp quyền |
| T16 | Role workload dev dùng để gọi prod | DENY vì môi trường/phạm vi |
| T17 | Role read được nhưng EDIT/DELETE ngoài quyền | PEP phải DENY |
| T18 | Role được thay đổi quyền sau approval | Tái đánh giá delta và chính sách trước khi cấp |

**Unit test catalog/policy chưa đủ**; cần integration test ở provisioning connector và API/PEP. Những test có thể gây thay đổi quyền nên dùng account/tài nguyên kiểm thử được ủy quyền, không can thiệp người dùng sản xuất.

## 38. Tình huống thực hành: chọn role cho một nhân viên chuyển dự án

**Bối cảnh:** Huy là nhân viên kỹ thuật thuộc **org-a**, chuyển từ Dự án Atlas sang Nova từ **01/12/2026, 09:00 +07:00**. Huy chỉ cần xem dashboard giám sát Nova và chạy một tác vụ khôi phục dịch vụ trong những đợt trực được phân công.

Catalog có:

- **Nova Viewer**: READ dashboard thuộc Nova, role thông thường.
- **Nova Operator**: READ và RESTART một số service Nova, có điều kiện.
- **Global Platform Administrator**: MANAGE_ACCESS, DELETE và thao tác rộng toàn môi trường production.

### Bước 1: Tách nhiệm vụ thường xuyên và nhiệm vụ đặc quyền

Huy cần READ dashboard hàng ngày, nên **Nova Viewer** phù hợp cho công việc thường xuyên. Quyền RESTART chỉ cần khi trực xử lý sự cố, nên cân nhắc **Nova Operator qua JIT/PAM**, với ticket và thời hạn đã duyệt. **Global Administrator** quá rộng so với hai nhiệm vụ.

### Bước 2: Kiểm tra căn cứ chọn role

IAM xác minh Huy có employment ACTIVE tại org-a và assignment Nova bắt đầu đúng mốc; role catalog chỉ cho phép các role thuộc tổ chức. Resource owner/PAM owner duyệt Operator theo policy.

### Bước 3: Tính quyền mới và quyền phải rút

| Quyền | Trước Mover | Sau Mover mong muốn |
| --- | --- | --- |
| READ dashboard Atlas | Có | DENY khi assignment cũ hết |
| RESTART Atlas | Có trong ca trực cũ | DENY trừ ngoại lệ bàn giao |
| READ dashboard Nova | Không | ALLOW sau khi cấp Viewer |
| RESTART Nova | Không | ALLOW chỉ khi JIT Operator được activate hợp lệ |
| Global Admin | Không | DENY |

### Bước 4: Phê duyệt và triển khai

Access request **Nova Viewer** được duyệt/cấp theo chính sách baseline nếu đủ eligibility. Operator được đưa qua workflow đặc quyền có approval, step-up phù hợp và expiration. SCIM/API provisioning cập nhật group/entitlement theo mapping của ứng dụng; IAM đồng thời thu hồi vai trò Atlas hết căn cứ.

### Bước 5: Kiểm chứng

Trong tài nguyên kiểm thử, hệ thống xác nhận:

~~~text
READ Nova dashboard          -> ALLOW
READ Atlas dashboard         -> DENY
RESTART Nova without JIT     -> DENY
RESTART Nova with valid JIT  -> ALLOW khi đủ điều kiện
MANAGE_ACCESS production     -> DENY
RESTART Atlas                -> DENY
~~~

Nếu **READ Atlas** vẫn ALLOW vì JWT claim/ACL cũ, không được coi Mover hoàn tất. Phải kiểm tra quyền tồn dư và token/session theo chính sách.

### Câu hỏi tự kiểm tra

**Câu 1:** Vì sao không chọn Global Platform Administrator cho Huy?

**Trả lời:** Quyền đó vượt nhiệm vụ READ/RESTART đã mô tả, có phạm vi production quá rộng và có thể cho phép MANAGE_ACCESS/DELETE không cần thiết.

**Câu 2:** Nova Viewer có đủ cho một lần RESTART khi incident không?

**Trả lời:** Không. Nếu RESTART thực sự là nhiệm vụ hợp lệ, cần một entitlement/role phù hợp, có thể qua JIT/PAM với approval và thời hạn.

**Câu 3:** Cấp Nova Viewer thành công có nghĩa quyền Atlas đã bị thu hồi?

**Trả lời:** Không. Phải đối soát riêng role, ACL, token, session và effective access của Atlas.

**Câu 4:** Người đã đăng nhập bằng MFA mạnh có được tự chọn Admin?

**Trả lời:** Không. Xác thực không thay eligibility, SoD, phê duyệt và resource authorization.

**Câu 5:** Role request đã APPROVED nhưng SaaS chưa xác nhận có quyền thì nên đóng request chưa?

**Trả lời:** Chưa. Cần provisioning/readback và effective access test trong phạm vi bắt buộc; nếu chưa rõ phải giữ PARTIAL/UNVERIFIED.

## 39. Checklist chọn vai trò trong Access request

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Có xác định đúng requester và beneficiary? | Stable identity/account mapping, đúng subject |
| Quan hệ lao động/bảo trợ đang hợp lệ? | HRIS/sponsor, employmentId, status, effectiveAt |
| Đã chọn đúng app và resource owner? | Target system, tenant, project, owner |
| Role có trong catalog đang ACTIVE? | roleId, roleVersion, mô tả và allowed actions |
| Business need đã rõ? | Task, justification, business outcome |
| Role có theo least privilege? | Permission delta so với nhiệm vụ, không cấp admin mặc định |
| Phạm vi tenant/resource có đúng? | Organization/project/resource binding và role scope |
| Có kiểm tra group nesting/role hierarchy? | Effective permissions preview |
| SoD và kết hợp role đã được đánh giá? | Conflict matrix và approved exception nếu có |
| Role đặc quyền có yêu cầu bổ sung? | PAM/JIT, approver, MFA/assurance và hạn |
| Thời hạn cấp quyền hợp lý? | startAt/endAt, expiration job và policy |
| Đã phê duyệt đúng người? | Manager, sponsor, resource/security owner theo risk tier |
| Có chống tự duyệt sai chính sách? | SoD giữa requester, beneficiary và approver |
| Có phân biệt approval với provisioning? | Trạng thái workflow và target results |
| Có xác minh role tại target? | Readback User/Group/ACL/role và session/token khi cần |
| Có kiểm thử ALLOW/DENY trên tài nguyên? | Effective access được kiểm tra ở PEP/API |
| Joiner có được cấp baseline đúng? | Account, MFA/SSO readiness và role phù hợp |
| Mover có thu hồi role cũ? | Expected rights mới và residual access checks |
| Leaver có ngăn quyền còn lại? | Local role, PAT, token, session và revocation |
| Workload có identity/owner riêng? | serviceId, purpose, environment, scope, expiry |
| Có audit và lịch review/expiration? | RequestId, approvals, grant, verifiedAt, owner |

## 40. Tổng kết

**Chọn vai trò** trong quy trình **Access request** là bước chuyển **nhu cầu công việc** thành một **role và phạm vi truy cập có thể kiểm tra, phê duyệt và triển khai**. Vai trò phù hợp không phải vai trò có quyền cao nhất hoặc dễ cấp nhất, mà là vai trò có **permission, tài nguyên, tenant, thời hạn và điều kiện xác thực vừa đủ** để hoàn thành nhiệm vụ hợp lệ. Việc chọn role phải xét **role catalog, eligibility, least privilege, SoD, role hierarchy, risk tier và người có thẩm quyền phê duyệt**.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** cung cấp căn cứ về người và quan hệ việc làm; **IAM/IGA** quản lý catalog, yêu cầu và approval; **IdP/SSO/MFA** xác thực; **SCIM/API** provision User/Group hoặc entitlement; **RBAC/ABAC/PBAC** quyết định quyền theo vai trò và ngữ cảnh; còn **PEP/resource server** kiểm soát hành động thực tế. **Service/workload identities** có role, owner và credential riêng. Chỉ khi **role được chọn đúng, phê duyệt đúng, cấp đúng và đối soát effective access tại hệ thống đích**, tổ chức mới duy trì được **least privilege**, tránh cấp quyền quá rộng và giảm **quyền truy cập tồn dư** khi nhiệm vụ hoặc quan hệ làm việc thay đổi.
