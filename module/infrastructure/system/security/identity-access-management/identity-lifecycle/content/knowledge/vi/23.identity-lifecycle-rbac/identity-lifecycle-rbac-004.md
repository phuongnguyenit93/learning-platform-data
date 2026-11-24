# Role assignment trong RBAC: gán vai trò đúng người, đúng quyền và đúng thời điểm

Một nhân viên vừa vào phòng Tài chính được cấp quyền đọc báo cáo chi phí. Sáu tháng sau, người đó chuyển sang Vận hành và cần quyền quản lý tác vụ triển khai, nhưng không còn được xem dữ liệu tài chính cũ. Nếu IAM chỉ thêm vai trò mới mà không thu hồi vai trò cũ, **quyền truy cập sẽ tích lũy ngoài nhu cầu công việc**. Ngược lại, nếu một hệ thống tự gán quyền chỉ dựa vào tên phòng ban chưa được xác minh, nhân viên có thể nhận quyền nhạy cảm ngay khi hồ sơ nhân sự bị cập nhật sai.

**Role assignment (gán vai trò)** là quá trình liên kết một chủ thể hoặc tài khoản với một hay nhiều **role** đã được định nghĩa trong mô hình **Role-Based Access Control (RBAC)**. Mục đích là chuyển yêu cầu công việc và quyết định phê duyệt thành quyền truy cập có giới hạn, có thể rà soát, thay đổi và thu hồi. Role assignment phải được quản lý như **một quan hệ có vòng đời**, không chỉ là thao tác đánh dấu một ô chọn trong giao diện quản trị.

Bài học thuộc chương **RBAC** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi mô-đun là quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh người dùng, tạo tài khoản, cấp quyền, rà soát và thu hồi khi thay đổi vai trò, kết hợp **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán** để giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Phân biệt **subject, account, role, permission, entitlement, session** và quan hệ gán vai trò.
- Giải thích các hình thức gán role: **birthright**, tự động theo chính sách, theo yêu cầu/phê duyệt, tạm thời và đặc quyền.
- Thiết kế **role catalog**, điều kiện đủ tư cách, chính sách phê duyệt, thời gian hiệu lực và kiểm soát xung đột **Separation of Duties (SoD)**.
- Mô tả luồng từ **HRIS/IGA → directory/IdP → SCIM/ứng dụng** và những giới hạn của đồng bộ role qua group, claim hoặc API.
- Xử lý đúng việc **thêm và thu hồi role** ở Joiner, Mover, Leaver, tái tuyển dụng, nghỉ tạm và thay đổi owner.
- Phân biệt **lệnh gán role thành công** với **quyền thực tế đã được xác minh** trong ứng dụng đích.

## 1. Role assignment là gì trong RBAC?

Trong mô hình RBAC, người dùng không nhất thiết được cấp từng permission riêng lẻ. Tổ chức định nghĩa **role** đại diện cho một nhóm trách nhiệm; mỗi role liên kết với các permission phù hợp. Sau đó, chủ thể được **gán vào role** và có thể sử dụng những permission của role theo quy tắc hệ thống.

Ví dụ:

- Role **finance-reader** cho phép xem báo cáo tài chính đã được phê duyệt.
- Role **expense-approver** cho phép phê duyệt những khoản chi trong phạm vi được giao.
- Role **release-operator** cho phép triển khai một nhóm ứng dụng cụ thể theo quy trình vận hành.

Khi An được gán **finance-reader**, điều đó không đồng nghĩa An trở thành quản trị viên toàn bộ hệ thống tài chính. Quyền có được phụ thuộc chính xác vào **permission-to-role assignment** và cơ chế thực thi tại ứng dụng.

### 1.1. Các thực thể phải phân biệt

| Thực thể | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Subject / identity** | Ai hoặc workload nào đang được quản lý? | person-1042, svc-reporting. |
| **Engagement** | Chủ thể có quan hệ lao động/hợp đồng nào? | EMP-5812, CONTRACT-827. |
| **Account** | Chủ thể có tài khoản gì ở IdP hoặc ứng dụng? | idp-account-721, expense-user-882. |
| **Role** | Tập trách nhiệm/quyền được chuẩn hóa là gì? | finance-reader. |
| **Permission** | Hành động nào trên tài nguyên nào được phép? | read:finance-report. |
| **User-role assignment** | Ai được tham gia role nào, theo căn cứ nào? | An → finance-reader. |
| **Permission-role assignment** | Role được phép thực hiện những hành động gì? | finance-reader → read:finance-report. |
| **Session / activation** | Role nào đang được kích hoạt trong phiên, nếu hệ thống có cơ chế đó? | Phiên quản trị chỉ kích hoạt operator-role. |
| **Entitlement** | Quyền cụ thể mà hệ thống đích biểu diễn và thực thi. | Membership nhóm, app role, local permission. |

Một ứng dụng có thể dùng thuật ngữ **role**, **group**, **profile**, **policy** hoặc **entitlement** khác nhau. IAM cần lập bảng ánh xạ rõ ràng, không mặc định tất cả là cùng một đối tượng kỹ thuật.

### 1.2. Mối quan hệ cốt lõi

~~~mermaid
flowchart LR
    U["Subject / User"] -->|"User-Role Assignment"| R["Role"]
    R -->|"Permission-Role Assignment"| P["Permission"]
    P --> RES["Action trên Resource"]
    U -->|"Khởi tạo"| S["Session"]
    S -->|"Role được kích hoạt<br/>nếu hệ thống hỗ trợ"| R
    HR["HRIS / JML / Approval"] -->|"Điều kiện và căn cứ gán"| U
~~~

Trong RBAC cơ bản, các quan hệ trên thường được ký hiệu:

~~~text
USERS       = tập chủ thể được quản lý
ROLES       = tập vai trò
PERMISSIONS = tập quyền thao tác trên tài nguyên

UA ⊆ USERS × ROLES          (user-role assignment)
PA ⊆ PERMISSIONS × ROLES    (permission-role assignment)

AssignedRoles(user) = những role gắn trực tiếp với user
EffectivePermissions(user) = các permission mà role hợp lệ
                             cung cấp theo hệ thống và chính sách
~~~

Các biểu thức diễn tả mô hình logic, **không phải cơ sở dữ liệu hay API RBAC bắt buộc**. Role hierarchy, session activation, SoD, hiệu lực thời gian và kiểm tra ABAC có thể làm tập quyền thực tế phức tạp hơn.

## 2. Role assignment không phải cấp quyền vô điều kiện

Điều kiện **“user có role”** chưa đủ để kết luận mọi thao tác của user đều được phép.

Hệ thống có thể còn kiểm:

1. **Trạng thái danh tính**: chủ thể còn quan hệ làm việc hợp lệ không?
2. **Trạng thái tài khoản**: user đã được provision, enable và không bị khóa?
3. **Thời gian hiệu lực**: assignment đã bắt đầu, chưa hết hạn và không bị revoke?
4. **Session**: nếu hệ thống yêu cầu kích hoạt role, role có đang active trong phiên?
5. **Scope**: role áp dụng cho dự án, tenant, tài khoản khách hàng hay môi trường nào?
6. **SoD và policy**: có xung đột với role khác hoặc điều kiện quyền đặc biệt?
7. **Dữ liệu hiện tại**: resource được yêu cầu có thuộc phạm vi mà người dùng được phép?
8. **Trạng thái ở hệ thống đích**: entitlement đã được đồng bộ và thực thi thực tế chưa?

Ví dụ **expense-approver** chỉ được phê duyệt chi phí của đơn vị A trong một khoảng thời gian. Nếu một ứng dụng chỉ hiểu role toàn cục mà không kiểm đơn vị, IAM cần **role theo phạm vi**, mapping chuyên biệt hoặc kiểm soát **ABAC** tại ứng dụng; không thể gán một role rộng rồi kỳ vọng tên role tự giới hạn dữ liệu.

## 3. Những kiểu gán role thường gặp

| Kiểu assignment | Nguồn kích hoạt | Đặc điểm | Rủi ro nếu thiết kế kém |
| --- | --- | --- | --- |
| **Birthright / baseline** | Quan hệ làm việc hợp lệ và thuộc tính chuẩn. | Quyền tối thiểu dùng chung, thường tự động theo chính sách. | Cấp trước Start date hoặc cấp rộng cho mọi nhân viên. |
| **Business-role assignment** | Job code, team, nhiệm vụ hoặc yêu cầu nghiệp vụ. | Tương ứng vai trò công việc, có điều kiện và owner. | Mapping cũ giữ quyền khi Mover. |
| **Request-based** | Người dùng/manager yêu cầu quyền. | Cần phê duyệt, lý do, thời hạn và kiểm SoD. | Tự phê duyệt hoặc role không có thời hạn. |
| **Temporary assignment** | Dự án, thay thế nhân sự, xử lý sự cố. | Có start/end hoặc TTL rõ, tự động hết hạn. | Quyền tạm tồn tại thành thường trực. |
| **Privileged/JIT assignment** | Tác vụ quản trị đã xác minh và cho phép. | Quyền cao, thường yêu cầu step-up, session và giám sát. | Admin thường trực, credential mạnh nhưng không kiểm SoD. |
| **Emergency / break-glass** | Sự cố cần hành động nhanh theo quy trình khẩn cấp. | Phê duyệt/giám sát và rà soát hậu kiểm đặc biệt. | Lạm dụng ngoại lệ, không thu hồi khi hết sự cố. |
| **Service/workload role** | Hệ thống hoặc ứng dụng cần quyền máy. | Gắn principal kỹ thuật, workload và owner vận hành. | Tài khoản máy mồ côi hoặc dùng role người dùng quá rộng. |

**Role assignment tự động không đồng nghĩa bỏ phê duyệt**. Quyền baseline có thể được phê duyệt ở cấp **chính sách và role catalog**, còn quyền nhạy cảm có thể phải được phê duyệt riêng theo yêu cầu.

### 3.1. Direct assignment và group-based assignment

**Direct assignment**: ứng dụng hoặc IAM gán trực tiếp role cho tài khoản. **Group-based assignment**: người dùng được thêm vào nhóm, rồi hệ thống đích ánh xạ nhóm đó sang role.

~~~text
Direct:
  subject → application role → permission

Group-based:
  subject → directory/IdP group → SCIM Group hoặc SSO claim
          → application role mapping → permission
~~~

Hai đường đều cần kiểm soát. Nếu IAM chỉ thu hồi group mà người dùng vẫn còn **local role được gán trực tiếp**, quyền có thể tiếp tục tồn tại. Ngược lại, nếu ứng dụng dựa trên **nested group** hoặc dynamic group, membership trực tiếp có thể không phản ánh toàn bộ quyền thực tế.

## 4. Role catalog: điều kiện tiên quyết để gán đúng

Role catalog là danh mục có quản trị, mô tả ý nghĩa, quyền, owner và điều kiện gán của từng role. Khi catalog mơ hồ, quá trình phê duyệt dễ biến thành “chọn một role có tên nghe phù hợp”.

### 4.1. Metadata nên có

| Trường catalog | Câu hỏi quản trị |
| --- | --- |
| **roleId / name** | Role nào, ID nào ổn định và namespace nào? |
| **description / purpose** | Trách nhiệm nghiệp vụ hoặc kỹ thuật chính xác là gì? |
| **roleType** | Baseline, business, application, privileged hay workload? |
| **application / environment** | Áp dụng cho app, tenant, dự án hoặc môi trường nào? |
| **permissionSet / scope** | Cung cấp chính xác những permission và giới hạn nào? |
| **roleOwner** | Ai chịu trách nhiệm ý nghĩa và quyền của role? |
| **eligibilityPolicy** | Ai có thể được gán, dựa trên nguồn thuộc tính nào? |
| **approvalPolicy** | Ai phê duyệt; có phải duyệt bởi data owner hay security không? |
| **sodConstraints** | Role nào xung đột, có điều kiện bổ sung gì? |
| **assignmentDuration** | Thời hạn mặc định/tối đa; có yêu cầu xác nhận lại? |
| **reviewFrequency** | Bao lâu rà soát catalog và assignment? |
| **provisioningMapping** | Triển khai qua SCIM Group, app API, directory group hay mapping khác? |
| **version / state** | Phiên bản role; ACTIVE, DEPRECATED hoặc RETIRED. |

### 4.2. Ví dụ catalog dạng YAML

~~~yaml
# Minh họa policy nội bộ, không phải schema RBAC/SCIM chuẩn.
roleId: finance-report-reader
displayName: Finance report reader
roleType: BUSINESS
applicationId: finance-portal
environment: production
permissions:
  - report.read
resourceScope: approved-finance-department
ownerTeam: finance-data-governance
eligibility:
  workerTypes: [EMPLOYEE]
  departmentIds: [FINANCE]
approval:
  required: true
  approvers: [manager, data-owner]
constraints:
  forbiddenConcurrentRoles: [finance-payment-issuer]
assignment:
  maxDurationDays: 180
  reviewRequired: true
state: ACTIVE
version: 4
~~~

**Giới hạn 180 ngày và các quy tắc trên chỉ mang tính ví dụ.** Mỗi tổ chức cần định nghĩa duration, phạm vi và phê duyệt theo rủi ro, pháp luật và chính sách thực tế. Việc có một roleId giống tên nhóm không có nghĩa nhóm đó tự động tồn tại hoặc được dùng như một role ở mọi provider.

### 4.3. Permission-role assignment cần rà soát riêng

Đội IAM không chỉ quản lý **ai có role** mà còn cần theo dõi **role đó chứa quyền gì**. Nếu owner bổ sung quyền xuất toàn bộ dữ liệu vào role **finance-reader**, mọi user đang có role đó có thể được mở rộng quyền mà không nộp yêu cầu mới.

Do đó, thay đổi quyền của role cần **change control, đánh giá tác động, kiểm SoD, kiểm thử và phiên bản**, kèm thông báo hoặc rà soát lại những assignment đang hoạt động khi có thay đổi đáng kể.

## 5. Nguồn có thẩm quyền và liên kết chủ thể

Trong lifecycle IAM, không nên gán role chỉ vì một email hoặc display name trùng với người được phê duyệt. Cần liên kết đúng:

~~~text
HRIS / hệ thống hợp đồng
       ↓  person ID + engagement ID + effective date
IAM / IGA
       ↓  subject ID ổn định + identity proofing
Directory / IdP account
       ↓  account ID và trạng thái
Application account / SCIM User
       ↓  application-specific user ID
Role assignment / entitlement ở ứng dụng
~~~

| Định danh | Mục đích | Lưu ý |
| --- | --- | --- |
| **personId** | Tham chiếu con người từ nguồn được xác minh. | Không đồng nhất với email. |
| **engagementId** | Giai đoạn làm việc/hợp đồng cụ thể. | Hỗ trợ Leaver, rehire và chuyển loại quan hệ. |
| **subjectId** | Định danh chủ thể nhất quán trong IAM. | Gắn với phạm vi issuer/namespace. |
| **directoryObjectId** | Định danh tài khoản directory. | DN, UPN hoặc tên đăng nhập có thể đổi. |
| **OIDC issuer + sub** | Chủ thể đã xác thực trong miền OIDC. | Không suy luận sub là ID toàn cục giữa mọi issuer. |
| **SCIM id** | User resource ID tại service provider. | Không tự dùng employeeNumber làm SCIM id. |
| **applicationRoleId** | Role thực tế ở ứng dụng. | Có thể khác tên role catalog của IAM. |

**Mỗi assignment cần gắn đúng chủ thể và đúng engagement có hiệu lực.** Khi tái tuyển dụng, việc nhận diện cùng Person không cho phép tự khôi phục các role của engagement cũ.

## 6. Quy tắc đủ điều kiện và quyết định gán vai trò

Trước khi cấp role, IAM cần xác định **người yêu cầu có đủ điều kiện** và **quyền được yêu cầu có chính đáng không**.

Ví dụ policy theo hướng điều kiện:

~~~text
ASSIGN finance-report-reader IF
    subject.engagementState == "ACTIVE"
    AND subject.workerType == "EMPLOYEE"
    AND subject.departmentId == "FINANCE"
    AND subject.identityVerified == true
    AND role.state == "ACTIVE"
    AND request.resourceScope in approvedScopes(subject)
    AND request.hasValidApproval == true
    AND not violatesStaticSoD(subject, role)
    AND request.effectiveAt <= request.expiresAt
~~~

Đây là **giả mã chính sách**, không phải câu lệnh RBAC chạy được. Hệ thống cần phân biệt tính hợp lệ của **dữ liệu HRIS**, quyết định phê duyệt, giới hạn thời gian và kết quả gán tại ứng dụng.

### 6.1. Birthright không có nghĩa tất cả Employee có cùng quyền

Quyền baseline có thể dựa vào worker type, tổ chức, khu vực hoặc trạng thái thiết bị. Tài khoản mới được tạo trước Start date thường **chưa đủ điều kiện sử dụng các quyền nghiệp vụ** trừ khi có phạm vi preboarding được phê duyệt.

Ví dụ:

- Tài khoản đang chờ kích hoạt: có entry tại IdP nhưng chưa có quyền đọc hệ thống tài chính.
- Employee ACTIVE: có các quyền cơ bản cần thiết theo policy.
- Contractor: chỉ có tập role hợp đồng và thời hạn phù hợp.
- Privileged user: quyền sản xuất yêu cầu quy trình phê duyệt và xác thực tăng cường, không tự suy ra từ phòng ban.

### 6.2. Manager không luôn là người duyệt đủ thẩm quyền

Manager hiểu nhu cầu công việc, nhưng **data owner hoặc application owner** thường hiểu phạm vi dữ liệu và rủi ro. Với role nhạy cảm, workflow có thể yêu cầu manager xác nhận nhu cầu và owner dữ liệu phê duyệt quyền, sau đó IAM kiểm SoD và thực thi.

Không để người yêu cầu **tự phê duyệt**, đồng thời tránh trường hợp manager mới có thể tự cấp quyền xem dữ liệu của toàn bộ cấp dưới chỉ vì thay quan hệ quản lý.

## 7. Separation of Duties: ngăn các tổ hợp quyền xung đột

**Separation of Duties (SoD)** là nguyên tắc phân tách những trách nhiệm mà một người không nên tự thực hiện toàn bộ, giúp giảm gian lận, sai sót và lạm quyền.

### 7.1. Static SoD (SSD)

**Static Separation of Duties** hạn chế **việc một chủ thể cùng được gán** những role xung đột.

Ví dụ:

- Role **vendor-create** cho phép tạo nhà cung cấp.
- Role **vendor-payment-approve** cho phép phê duyệt thanh toán nhà cung cấp.
- Chính sách không cho cùng một người giữ cả hai role trong phạm vi nghiệp vụ đã định.

Nếu An đang có vendor-create, yêu cầu gán vendor-payment-approve phải bị từ chối hoặc xử lý theo một ngoại lệ có kiểm soát được chính sách chấp thuận, chứ không chỉ gửi SCIM thêm group.

### 7.2. Dynamic SoD (DSD)

**Dynamic Separation of Duties** có thể cho phép một chủ thể **được gán** nhiều role nhưng **không kích hoạt hoặc sử dụng đồng thời** những role xung đột trong cùng ngữ cảnh được quy định, khi hệ thống có cơ chế session activation hoặc kiểm soát giao dịch.

Ví dụ một nhân viên được đào tạo hai vai trò hỗ trợ, nhưng không được vừa tạo vừa phê duyệt **cùng một giao dịch**. Trong nhiều ứng dụng, ràng buộc này đòi hỏi kiểm tra **transaction-level** và lịch sử người thực hiện, không thể đạt được chỉ bằng việc đồng bộ Group.

| Kiểm soát | Câu hỏi chính | Nơi thực thi thường gặp |
| --- | --- | --- |
| **SSD** | Có được gán đồng thời các role xung đột không? | IAM/IGA trước khi assignment. |
| **DSD** | Có được kích hoạt/sử dụng đồng thời trong phiên hoặc giao dịch không? | Session manager, application policy, workflow engine. |
| **Rà soát SoD theo dữ liệu** | Có một người thực hiện hai bước xung đột trong cùng giao dịch không? | Ứng dụng nghiệp vụ, audit và reconciliation. |

**Không phải ứng dụng nào cũng hỗ trợ DSD theo mô hình RBAC**. Nếu ứng dụng chỉ có nhóm tĩnh, cần bổ sung kiểm soát tại luồng phê duyệt hoặc thiết kế phân quyền khác, không tuyên bố group membership đã giải quyết đầy đủ SoD.

## 8. Role hierarchy và quyền kế thừa

Một mô hình RBAC có thể định nghĩa **role hierarchy**: role cấp cao kế thừa permission của role cấp thấp, theo quan hệ đã được định nghĩa.

~~~mermaid
flowchart TD
    ADMIN["finance-admin"] -->|"kế thừa permission"| EDIT["finance-editor"]
    EDIT -->|"kế thừa permission"| READ["finance-reader"]
    READ --> P1["report.read"]
    EDIT --> P2["report.update"]
    ADMIN --> P3["role.manage"]
~~~

Nếu gán finance-admin, tập quyền có thể bao gồm cả permission của finance-editor và finance-reader. IAM phải xem xét **effective permissions**, không chỉ tên role được gán trực tiếp.

### 8.1. Rủi ro role hierarchy

- Role cấp cao có thể thừa hưởng nhiều quyền hơn người duyệt dự tính.
- Thay permission của role thấp có thể mở rộng quyền cho mọi role cấp cao.
- Quan hệ lồng nhau có thể gây **xung đột SoD gián tiếp**.
- Chu trình kế thừa hoặc thiết kế hierarchy không được kiểm tra có thể làm việc tính quyền sai.
- Không phải nhóm lồng nhau trong directory **tương đương hoàn toàn** với role hierarchy của ứng dụng.

Khi phê duyệt gán một role có hierarchy, cần hiển thị hoặc tính **tập quyền hiệu lực**, tác động SoD và độ nhạy dữ liệu trước khi quyết định.

## 9. Quy trình gán role có kiểm soát

Một workflow role assignment nên có vòng đời riêng thay vì chỉ trạng thái “đã thêm vào nhóm”.

~~~mermaid
flowchart TD
    A["HRIS event / Access request"] --> B["Resolve subject + engagement<br/>và trạng thái hiện hành"]
    B --> C["Tra role catalog, scope,<br/>eligibility + SoD"]
    C --> D{"Đủ điều kiện?"}
    D -->|"Không"| X["DENIED / manual review<br/>ghi lý do"]
    D -->|"Có"| E["Approval theo policy<br/>owner / manager / security"]
    E --> F{"Được phê duyệt?"}
    F -->|"Không"| X
    F -->|"Có"| G["Lên lịch effectiveAt<br/>expiresAt + policy version"]
    G --> H["Provision role/group<br/>qua connector phù hợp"]
    H --> I["Đọc lại entitlement thực tế<br/>trong ứng dụng đích"]
    I --> J{"Khớp quyền mong đợi?"}
    J -->|"Không"| K["Exception + retry kiểm soát<br/>owner + hạn xử lý"]
    K --> I
    J -->|"Có"| L["ACTIVE_VERIFIED<br/>audit + review schedule"]
~~~

### 9.1. Các bước cốt lõi

1. **Nhận yêu cầu hợp lệ:** sự kiện JML từ nguồn có thẩm quyền hoặc yêu cầu truy cập từ người được phép.
2. **Resolve chủ thể:** kiểm Person, Engagement, account đích và nguồn mapping.
3. **Kiểm quyền đủ điều kiện:** trạng thái ACTIVE, loại quan hệ, vị trí và phạm vi công việc.
4. **Tra role catalog:** role còn được dùng, permission và scope chính xác.
5. **Đánh giá SoD và least privilege:** tránh cấp role quá rộng hoặc xung đột.
6. **Phê duyệt:** dùng owner/manager/data owner phù hợp; quyết định có giới hạn thời gian và lý do.
7. **Lập lịch hiệu lực:** tính Start date, effectiveAt, expiresAt và timezone chính xác.
8. **Provision:** chuyển role tới IdP, directory group, SCIM/API hoặc ứng dụng trực tiếp.
9. **Verify:** đọc lại User/Group/role và kiểm quyền ở tài nguyên khi cần.
10. **Rà soát và thu hồi:** khi hết thời hạn, Mover, Leaver, đổi chính sách hoặc phát hiện rủi ro.

**Không dùng một HTTP 200 hoặc một ticket đã đóng làm bằng chứng role đã có hiệu lực đúng.** Cần xem ngữ nghĩa phản hồi và trạng thái đích được xác minh.

## 10. Assignment có thời điểm hiệu lực và thời hạn

Một role assignment không phải luôn kéo dài vô thời hạn. Có nhiều mốc thời gian:

| Thời điểm | Ý nghĩa |
| --- | --- |
| **requestedAt** | Lúc tạo yêu cầu. |
| **approvedAt** | Lúc đủ phê duyệt. |
| **effectiveAt** | Lúc chính sách cho phép role bắt đầu có hiệu lực. |
| **provisionedAt** | Lúc lệnh cập nhật được hệ thống đích ghi nhận. |
| **verifiedAt** | Lúc xác nhận quyền thực tế đúng. |
| **expiresAt** | Lúc assignment phải tự hết hạn hoặc được rà soát theo policy. |
| **revokedAt** | Lúc quyền bị yêu cầu hoặc thực thi thu hồi, cần định nghĩa rõ trường. |

### 10.1. Ví dụ quyền theo dự án

Một nhân viên được phép đọc báo cáo của dự án từ ngày 01/12 đến hết ngày 31/12 theo múi giờ doanh nghiệp.

- IAM lưu **thời điểm hiệu lực cụ thể**, không chỉ chuỗi ngày mơ hồ.
- Quyền có thể được cấp trước để chuẩn bị, nhưng **không được sử dụng sớm** nếu không có kiểm soát chờ activation.
- Job thu hồi khi hết hạn phải xử lý cả group/role trực tiếp trong ứng dụng.
- Nếu người dùng nghỉ việc ngày 15/12, **Leaver có hiệu lực ưu tiên**; không chờ tới 31/12.
- Nếu token ứng dụng giữ claim cũ, cần xem cách hủy session/kiểm quyền theo thời gian thực.

### 10.2. Role tạm thời có thể cần gia hạn

Gia hạn không nên được suy ra chỉ vì người dùng vẫn đang có nhiệm vụ. Nếu chính sách yêu cầu, phải có **đánh giá lại nhu cầu, owner phê duyệt, kiểm SoD và thời hạn mới**. Gia hạn phải là một quyết định mới có audit trail; không tự động đổi expiresAt thành vô hạn.

## 11. Gán role qua IdP, directory, SCIM và ứng dụng

Một role logic trong IGA thường cần được ánh xạ tới **đối tượng kỹ thuật** tại từng hệ thống.

| Điểm thực thi | Cơ chế có thể dùng | Giới hạn quan trọng |
| --- | --- | --- |
| **Directory/LDAP/AD** | Group membership, thuộc tính hoặc cơ chế quản lý đặc quyền. | Group không luôn tương đương application role; nested group có ngữ nghĩa riêng. |
| **IdP** | App assignment, group mapping, role claim, chính sách truy cập. | SSO xác thực không đồng nghĩa application authorization đã cập nhật. |
| **SCIM User** | Tạo/cập nhật tài khoản và một số thuộc tính User. | Thuộc tính roles có thể tồn tại theo schema nhưng **ý nghĩa quyền do provider định nghĩa**. |
| **SCIM Group** | Thêm/xóa thành viên nhóm nếu provider hỗ trợ. | Group có thể không ánh xạ tới role nhạy cảm hoặc bị quản lý thủ công. |
| **Application API** | Gán role cụ thể, scope hoặc local entitlement. | Cần token connector riêng, versioning, kiểm quyền ở provider. |
| **PAM/Privileged platform** | Quyền quản trị tạm thời, session và credential quản lý. | Thường yêu cầu step-up/approval riêng, không phải group thường trực. |

### 11.1. SCIM không chuẩn hóa mọi mô hình role

SCIM 2.0 (RFC 7643/7644) chủ yếu chuẩn hóa User, Group và cách thao tác qua HTTP. Một User có thể có thuộc tính **roles** trong schema, nhưng việc **gán quyền ứng dụng** không được SCIM chuẩn hóa hoàn toàn: provider có thể chỉ hỗ trợ Group, cần API riêng hoặc không hỗ trợ ghi roles.

Ví dụ quy trình Mover:

~~~text
IGA expected state:
    finance-reader = ACTIVE
    sales-editor   = REVOKED

Target A:
    mapping: SCIM Group finance-readers / sales-editors

Target B:
    mapping: application-specific Role Assignment API

Target C:
    mapping: IdP group claim + local authorization policy
~~~

Mỗi target phải được **kiểm tra capability và mapping**; không gửi một trường SCIM roles chung rồi cho rằng mọi hệ thống đã cấp quyền giống nhau.

### 11.2. Group claim trong SSO có thể bị cũ

Khi OIDC ID token hoặc SAML assertion mang thông tin nhóm, ứng dụng có thể tạo session và lưu lại vai trò trong bộ nhớ đệm. Sau khi IAM thu hồi group:

- IdP đã có membership mới nhưng **token cũ** vẫn chứa nhóm trước đó.
- Session ứng dụng có thể tiếp tục sử dụng quyền cũ tới khi hết hạn.
- Một ứng dụng có thể có role trực tiếp không bị ảnh hưởng bởi claim mới.
- Một API có thể cần kiểm authorization trực tuyến thay vì chỉ tin claim đã phát hành.

Do đó, **đồng bộ group không tự đảm bảo thu hồi quyền tức thời**. Với Leaver hoặc quyền đặc quyền, cần kế hoạch thu hồi phiên/token và xác minh đường truy cập đích theo khả năng sản phẩm.

## 12. Role assignment trong Joiner

Khi một người mới gia nhập, quyền phải xuất phát từ **quan hệ đã được xác minh** và chính sách công việc, không phải từ việc tài khoản đã được tạo sớm.

### 12.1. Luồng Joiner

1. HRIS/hệ thống hợp đồng xác nhận **Person, Engagement, workerType và Start date**.
2. IAM kiểm trùng, tạo subject ID và liên kết tài khoản đúng người.
3. IGA xác định **birthright roles** từ chính sách đã được duyệt.
4. Các quyền ngoài baseline đi qua workflow yêu cầu/phê duyệt phù hợp.
5. SoD, scope, thời hạn và hiệu lực được kiểm trước khi provision.
6. IdP/directory/ứng dụng được chuẩn bị theo khả năng; tài khoản chờ không mặc định có quyền sản xuất.
7. Tại thời điểm có hiệu lực, kiểm lại trạng thái HRIS và policy rồi kích hoạt.
8. Đối soát quyền thực tế của ứng dụng; mở case cho thiếu quyền hoặc quyền vượt phạm vi.

### 12.2. Ví dụ Joiner trước ngày làm việc

**Bối cảnh:** HRIS tạo hồ sơ ngày 20/11, Start date là 01/12. IGA đã tính quyền nhóm baseline và role **expense-submitter**.

| Mốc | Trạng thái hợp lệ |
| --- | --- |
| **20/11** | Hồ sơ HRIS tồn tại, chưa đồng nghĩa người dùng được truy cập. |
| **25/11** | IdP account được pre-provision, có thể disabled/chờ kích hoạt. |
| **01/12** | Sau xác minh nguồn và đủ điều kiện, role được kích hoạt đúng giờ. |
| **Sau kích hoạt** | Ứng dụng đích có account/role đúng; IAM xác minh kết quả và lưu audit. |

Không nên “sửa lỗi đăng nhập” bằng cách bật role trước Start date nếu người dùng chưa đủ điều kiện. Với **preboarding**, cần role riêng có phạm vi giới hạn và phê duyệt rõ.

## 13. Role assignment trong Mover: thêm mới phải đi cùng thu hồi cũ

**Mover** có thể là thay phòng ban, nhiệm vụ, người quản lý, dự án hoặc loại quan hệ khi chủ thể vẫn đang làm việc. Tập role phù hợp cần được **tính lại toàn bộ** theo trạng thái có hiệu lực, không chỉ thêm role mới.

### 13.1. So sánh trước và sau

| Hạng mục | Trước Mover | Sau Mover |
| --- | --- | --- |
| **Department** | SALES | FINANCE |
| **Manager** | manager-S | manager-F |
| **Business role mong đợi** | sales-reader, quote-editor | finance-reader |
| **Role cần thu hồi** | Không có trong trạng thái cũ | sales-reader, quote-editor |
| **Quyền mới cần phê duyệt** | Không | finance-reader theo owner/policy |
| **Session/token** | Có thể còn claim Sales | Phải xem cập nhật/quyền tồn dư |

### 13.2. Hai bước bắt buộc

1. **Grant delta:** role mới hợp lệ nào cần thêm? Kiểm eligibility, approval, SoD và effectiveAt.
2. **Revoke delta:** role nào không còn được phép? Thu hồi direct assignment, group/permission tương ứng và kiểm cache/phiên nếu có.

Một workflow Mover chỉ có **GRANT** mà không có **REVOKE** là nguồn phổ biến gây **privilege creep**.

### 13.3. Thay manager có tự thay role không?

Không nhất thiết. Thay manager có thể làm thay tuyến phê duyệt của yêu cầu quyền hoặc policy ABAC, nhưng **không tự biến người quản lý mới thành owner của mọi tài nguyên** hoặc tự gán các role đặc quyền.

Cần kiểm:

- Người quản lý mới đã có ID đáng tin cậy và quan hệ có hiệu lực?
- Những yêu cầu đang chờ có phải chuyển người duyệt không?
- Vai trò người quản lý cũ có quyền xem/phê duyệt nào cần thu hồi?
- Các assignment của nhân viên có còn đủ điều kiện sau Mover?
- Có role tạm thời trước đây nay phải hết hạn sớm hơn không?

## 14. Role assignment trong Leaver và khi tạm ngưng

Khi nguồn có thẩm quyền thông báo **Leaver**, việc thu hồi role cần được phối hợp với deprovisioning tài khoản và credential.

### 14.1. Các lớp thu hồi

| Lớp | Thao tác | Điều cần xác minh |
| --- | --- | --- |
| **IAM/IGA** | Đánh dấu engagement kết thúc; tính expected roles rỗng hoặc quyền lưu trữ tối thiểu theo chính sách. | Không có event cũ cấp lại role. |
| **Directory/IdP** | Thu hồi group/app assignment, khóa đăng nhập hoặc account theo policy. | Account và membership hiện hành đúng. |
| **SCIM/API đích** | Vô hiệu hóa User, xóa Group membership/role hoặc local entitlement. | Đọc lại trạng thái tại SaaS. |
| **Ứng dụng** | Hủy quyền trực tiếp, delegated access, quyền dự án và đặc quyền. | Authorization thực tế từ chối quyền cũ. |
| **Session/token** | Thu hồi/giới hạn phiên và token theo tính năng sản phẩm. | Không còn đường truy cập được chấp nhận ngoài ý muốn. |
| **Service/workload** | Chuyển owner và rà soát secret/quyền liên quan người nghỉ. | Không còn owner mồ côi hoặc credential người dùng sử dụng được. |

**Disable account không tự động xóa mọi local role, session hoặc API key.** Ngược lại, để giữ hồ sơ kiểm toán không cần giữ assignment đang ACTIVE.

### 14.2. Nghỉ phép, tạm đình chỉ và trở lại

Một người **ON_LEAVE** hoặc **SUSPENDED** không giống **TERMINATED**. Chính sách có thể yêu cầu tạm ngưng các role nhạy cảm, khóa phiên hoặc thu hẹp ứng dụng nhưng bảo toàn một số metadata để khôi phục sau khi xác minh.

Khi quay lại, IAM phải:

1. Kiểm nguồn HRIS và trạng thái có hiệu lực.
2. Đánh giá lại role eligibility, approval, SoD và role catalog hiện hành.
3. Không tự mở lại mọi quyền cũ chỉ vì trạng thái ACTIVE.
4. Provision lại đúng những role vẫn hợp lệ; đối soát ứng dụng.

### 14.3. Rehire

Khi người đã nghỉ được tuyển lại, có thể liên kết cùng **Person** nếu được xác minh, nhưng phải tạo/đánh giá đúng **Engagement mới**. Không tự khôi phục quyền hoặc credential đã thu hồi từ giai đoạn trước chỉ vì email giống nhau.

## 15. Tài khoản đặc quyền và Just-in-Time Role Assignment

Một số quyền có mức rủi ro quá cao để gán thường trực, ví dụ:

- Thay policy IAM toàn tổ chức.
- Quản trị cơ sở dữ liệu production.
- Cấp quyền cho người khác.
- Quản lý secret hoặc signing key.
- Vượt qua quy trình phê duyệt nghiệp vụ.

**Privileged Access Management (PAM)** hoặc cơ chế **Just-in-Time (JIT) access** có thể cấp quyền trong khoảng thời gian ngắn, cho mục đích cụ thể, với xác minh bổ sung và ghi vết.

### 15.1. Luồng JIT tham khảo

1. Chủ thể đã xác thực mạnh và có engagement hợp lệ.
2. Người dùng nêu **tác vụ, hệ thống, scope và thời hạn**.
3. IAM/PAM kiểm eligibility, SoD, hạn mức và tín hiệu rủi ro.
4. Owner hoặc hệ thống phê duyệt theo policy.
5. Yêu cầu step-up/MFA chống phishing khi phù hợp.
6. Kích hoạt role hoặc phiên đặc quyền có giới hạn.
7. Ghi audit hoạt động, quyền đã sử dụng và các hành động nhạy cảm theo chính sách.
8. Khi hết hạn hoặc có Leaver/sự cố, thu hồi role/phiên/credential và **xác minh tại đích**.

### 15.2. Rủi ro của ngoại lệ

**Break-glass** không nên trở thành con đường cấp role không cần phê duyệt cho công việc thường ngày. Ngoại lệ khẩn cần có chủ sở hữu, lý do, kiểm soát sử dụng, theo dõi sau sự kiện và hành động thu hồi bắt buộc.

Một role JIT có thể chỉ active trong một phiên, không nhất thiết được biểu diễn như một Group vĩnh viễn trong SCIM. Cần hiểu chính xác mô hình thực thi của hệ thống PAM/đích.

## 16. Service account và workload role assignment

**Role assignment cho máy** khác với role assignment cho Employee. Một service principal có thể cần quyền đọc một API để chạy công việc định kỳ, nhưng không có manager nhân sự hoặc Start date theo hợp đồng lao động.

| Thành phần | Cách quản lý |
| --- | --- |
| **Technical principal** | ID service account/workload được provider chấp nhận. |
| **Owner team** | Nhóm chịu trách nhiệm mục đích, quyền, credential và vận hành. |
| **Workload identity** | Chứng minh job/service cụ thể được phép sử dụng principal. |
| **Role/scope** | Permission tối thiểu cho tài nguyên và môi trường. |
| **Credential lifecycle** | Ưu tiên short-lived tokens/managed identity khi hỗ trợ; rotate/revoke bí mật. |
| **Review/decommission** | Rà soát định kỳ và thu hồi khi workload không còn hoạt động. |

Ví dụ một tác vụ báo cáo chỉ cần **report-read-only**. Không nên cấp role **tenant-admin** vì cấu hình nhanh hơn. Khi kỹ sư tạo job nghỉ việc, **chuyển owner và đánh giá quyền** thay vì giữ một PAT cá nhân hoặc xóa ngay service account đang vận hành hợp lệ.

### 16.1. Chống ràng buộc sai loại danh tính

Một application role được định nghĩa cho người dùng có thể không phù hợp với service principal. Cần kiểm xem API hỗ trợ **app-only authorization**, role ứng dụng cho máy hoặc scope dạng nào; không giả định claim role của OIDC ID token người dùng có thể tái sử dụng cho OAuth client credentials token.

## 17. Thực thi gán và thu hồi role an toàn trước lỗi đồng bộ

Trong hệ thống phân tán, request có thể thành công một phần hoặc được xử lý lại. Một role assignment nên được theo dõi với **nguồn và trạng thái riêng**.

### 17.1. Trạng thái gợi ý

| Trạng thái | Ý nghĩa |
| --- | --- |
| **REQUESTED** | Đã có yêu cầu hoặc sự kiện kích hoạt. |
| **ELIGIBILITY_CHECKED** | Đã xác minh subject, engagement, role và policy. |
| **APPROVED** | Đã đủ phê duyệt theo quy tắc. |
| **SCHEDULED** | Chờ effectiveAt hoặc điều kiện kích hoạt. |
| **PROVISIONING** | Đang gửi thay đổi tới hệ thống đích. |
| **ACTIVE_VERIFIED** | Đã đọc lại/kiểm tra và xác minh entitlement đúng. |
| **REVOKE_REQUIRED** | Role phải thu hồi do hết hạn, Mover, Leaver hoặc policy. |
| **REVOKING** | Đã gửi lệnh thu hồi nhưng chưa có xác minh cuối. |
| **REVOKED_VERIFIED** | Đích đã được xác minh không còn quyền liên quan. |
| **FAILED / UNKNOWN** | Thao tác lỗi hoặc chưa rõ kết quả. |
| **EXCEPTION_TRACKED** | Có owner, hạn xử lý và giảm thiểu trong khi chưa đồng bộ. |

Các trạng thái là **thiết kế gợi ý của IGA**, không phải state machine bắt buộc trong chuẩn RBAC hoặc SCIM.

### 17.2. Xử lý retry và thứ tự sự kiện

Giả sử:

~~~text
10:00  IAM nhận Mover: gán finance-reader
10:02  SCIM PATCH Group bị timeout (chưa rõ có áp dụng không)
10:05  IAM nhận Leaver có hiệu lực ngay: thu hồi toàn bộ quyền
10:10  Job retry Mover cũ chạy trở lại
~~~

Nếu job retry ở 10:10 không kiểm nguồn hiện hành, nó có thể **thêm lại finance-reader sau Leaver**. Do đó:

- Dùng **event ID**, source version và effectiveAt để chống xử lý trùng/đến muộn.
- Kiểm lại authoritative state trước những lệnh cấp quyền có tác động an ninh.
- Sau timeout, **đọc lại trạng thái đích** trước khi retry, nhất là request tạo tài nguyên.
- Với ETag/version conflict, đọc dữ liệu mới và tính lại delta, không ép ghi đè.
- Giữ trạng thái **riêng cho từng target**; không đóng toàn bộ workflow nếu một SaaS thất bại.
- Ưu tiên revoke của Leaver/incident so với grant cũ khi policy yêu cầu.

## 18. Giả mã điều phối role assignment theo JML

~~~text
onTrustedLifecycleEvent(event):
    verifySourceAuthenticityAndSchema(event)
    if alreadyProcessed(event.eventId):
        return

    subject = resolveSubjectAndEngagement(event)
    if subject is ambiguous:
        openIdentityReview(event)
        return

    current = loadLatestAuthoritativeEffectiveState(subject)
    if eventIsStaleOrSuperseded(event, current):
        recordIgnoredStaleEvent(event)
        return

    expectedRoles = evaluateRolesFromCatalogAndPolicies(current)
    expectedRoles = enforceEligibilitySoDAndApprovals(expectedRoles)
    actualAssignments = readCurrentAssignmentsAcrossTargets(subject)

    toGrant  = expectedRoles - actualAssignments
    toRevoke = actualAssignments - expectedRoles

    for assignment in toRevoke:
        enqueueRevocationWithPriority(assignment, event)
    for assignment in toGrant:
        enqueueProvisionIfStillAuthorized(assignment, event)

    verifyActualEntitlementsAndOpenExceptions(subject, expectedRoles)

onAssignmentJob(job):
    currentState = reloadAuthoritativeState(job.subjectId)
    if not stillAllowed(job, currentState):
        cancelOrRecalculate(job)
        return
    result = callTargetProviderWithMinimalDelta(job)
    recordProviderResultWithoutSecrets(result)
    actual = readBackTargetState(job)
    if actual matches expected:
        markVerified(job)
    else:
        openExceptionWithOwnerDeadlineAndMitigation(job)
~~~

**Giả mã mô tả ý tưởng, không phải code chạy ngay.** Trong triển khai thật, phải tính **role hierarchy, quyền trực tiếp, group lồng nhau, scope, assignment nhiều nguồn và thời gian hiệu lực**. Phép hiệu giữa hai tập role không đủ để đại diện toàn bộ entitlement tại các provider phức tạp.

### 18.1. Phân biệt assignment do ai sở hữu

Một user có thể nhận role từ **policy JML**, yêu cầu tự phục vụ hoặc ngoại lệ dự án. Khi một nguồn kết thúc, không nên xóa role nếu một **nguồn cấp khác vẫn còn hợp lệ và được cho phép**; ngược lại, không giữ role chỉ vì một nguồn cũ chưa được dọn.

IAM cần lưu **assignment source, approval reference, scope và expiresAt** để tính quyền mong đợi theo các căn cứ còn hiệu lực. Với Leaver, một principal không còn đủ tư cách thường phải bị chặn theo chính sách bất kể còn bao nhiêu nguồn assignment cũ.

## 19. Reconciliation: từ role mong đợi đến quyền thực tế

**Reconciliation (đối soát)** là so sánh **expected state** của IAM với **actual state** tại IdP, directory, SCIM/ứng dụng và hệ thống thực thi quyền.

### 19.1. Các dạng chênh lệch

| Chênh lệch | Ví dụ | Hành động |
| --- | --- | --- |
| **Missing assignment** | IAM đã duyệt finance-reader nhưng app chưa có role. | Kiểm connector, mapping, approval và retry có kiểm soát. |
| **Excess assignment** | App còn sales-editor dù Mover đã thu hồi. | Ưu tiên giảm quyền và xác minh mọi đường cấp. |
| **Orphan role** | Role không có owner hoặc không nằm trong catalog. | Cô lập, đánh giá rồi retire/migrate theo policy. |
| **Unknown principal** | App account có quyền nhưng IAM không xác định được subject. | Điều tra identity mapping, local account và nguồn tạo. |
| **Policy mismatch** | IAM role đúng nhưng app map tới quyền rộng hơn. | Sửa permission-role mapping và đánh giá tác động toàn bộ user. |
| **Session drift** | Group đã bị xóa nhưng token/session vẫn giữ role cũ. | Thu hồi phiên hoặc kiểm quyền hiện tại tại API theo khả năng. |
| **Connector failure** | SCIM cập nhật một app nhưng thất bại ở app khác. | Trạng thái riêng từng đích và ngoại lệ có owner. |
| **Manual drift** | Admin gán local role ngoài IGA. | Audit, xác minh căn cứ và reconcile theo governance. |

### 19.2. Phương pháp xác minh

Không chỉ đọc membership tại IdP. Cần xác minh **đúng nơi quyền được thực thi**:

1. Directory/IdP có user và nhóm hiện hành đúng không?
2. SCIM provider có User, Group membership hoặc thuộc tính phù hợp không?
3. Ứng dụng có local role, delegated permission hoặc grant độc lập nào không?
4. RBAC hierarchy và ABAC có làm quyền thực tế khác quyền trực tiếp không?
5. Session/token còn sống có thể sử dụng quyền trước khi thay đổi không?
6. Các API/tài nguyên nhạy cảm có từ chối hành động không còn được phép không?

Một phản hồi **HTTP 200/204** từ request PATCH chỉ là bằng chứng ở lớp API, không mặc nhiên chứng minh mọi bước trên.

## 20. Case study: chuyển vai trò và phát hiện quyền tồn dư

**Bối cảnh:** Mai làm việc tại Sales với role **sales-editor** và có quyền xem dữ liệu khách hàng. Ngày 01/12 lúc 08:00, Mai chuyển sang Finance, cần **finance-reader**. IGA dự kiến thu hồi sales-editor đồng thời cấp finance-reader.

| Thời điểm giả định | Sự kiện | Cần xác minh |
| --- | --- | --- |
| **30/11 16:00** | HRIS ghi Mover, hiệu lực 01/12 08:00. | Đúng person/engagement, bộ phận và thời điểm. |
| **01/12 08:00** | IGA tính expected roles: finance-reader; revoke sales-editor. | Policy, SoD và các assignment ngoài role công việc. |
| **01/12 08:01** | Directory xóa nhóm Sales, thêm nhóm Finance. | Phản hồi thành công và replication. |
| **01/12 08:03** | SCIM Group Finance cập nhật thành công. | Account và role Finance ở app đích. |
| **01/12 08:04** | SCIM Group Sales trả 403 do connector thiếu quyền sửa. | Role cũ có thể còn hoạt động, tạo ngoại lệ cần xử lý. |
| **01/12 08:06** | Mai vẫn mở được báo cáo Sales bằng phiên ứng dụng cũ. | Truy cập tồn dư đã được quan sát; cần giảm thiểu ngay theo policy. |
| **01/12 08:12** | Owner sửa quyền connector theo quy trình; lệnh revoke thành công. | Đọc lại membership và local entitlements. |
| **01/12 08:15** | Ứng dụng xác minh finance-reader hợp lệ, sales-editor không còn quyền. | Kiểm session/cache, lưu bằng chứng kết quả. |

### 20.1. Phân tích nguyên nhân

1. **HRIS và IGA có thể đúng** nhưng một SCIM request lỗi khiến trạng thái đích sai.
2. **IdP đăng nhập thành công không chứng minh quyền đúng**; session ứng dụng có thể còn role Sales.
3. **Tăng quyền ở Finance không thay thế việc thu hồi Sales**.
4. Cấp role admin cho Mai để “sửa lỗi 403” sẽ tạo thêm quyền không phù hợp.
5. Workflow chỉ được đóng khi trạng thái đã khớp hoặc ngoại lệ được phê duyệt và theo dõi rõ.

### 20.2. Nếu Mai nghỉ việc ngay ngày 02/12?

Leaver yêu cầu IAM chặn cả role Finance mới, quyền Sales tồn dư và mọi local entitlement, session, token hoặc API credential thuộc phạm vi. Không được để job Mover đến muộn tiếp tục cấp role sau Leaver; cần **chặn theo trạng thái authoritative hiện tại** và đối soát mọi hệ thống đích.

## 21. Những lỗi thiết kế role assignment thường gặp

| Sai lầm | Hậu quả | Kiểm soát đề xuất |
| --- | --- | --- |
| **Gán role theo tên/email** | Có thể gắn sai người khi đổi tên, tái cấp email. | Stable subject/engagement ID và account mapping. |
| **Role không có owner** | Không ai chịu trách nhiệm phạm vi quyền hoặc rà soát. | Role catalog với business/data owner rõ. |
| **Tên role mơ hồ** | Người duyệt không hiểu permission thực sự. | Mô tả role, scope và effective permissions. |
| **Mặc định mọi Employee có role nhạy cảm** | Birthright vượt nhu cầu tối thiểu. | Eligibility theo policy và phân loại rủi ro. |
| **Chỉ thêm role khi Mover** | Privilege creep do role cũ tồn dư. | Reconcile expected/actual và revoke delta. |
| **Thiếu SoD** | Một người giữ các quyền xung đột. | SSD trước gán và DSD/workflow khi cần. |
| **Tự phê duyệt** | Role đặc quyền được cấp không độc lập. | Approval chain và separation of duties. |
| **Role tạm không có expiry** | Quyền dự án sống vĩnh viễn. | expiresAt, review, revoke tự động. |
| **Quá nhiều role đặc thù** | Role explosion, khó audit và maintain. | Role engineering, scope/ABAC và quản lý phiên bản. |
| **Tin mọi group claim từ SSO** | Claim cũ hoặc issuer không phù hợp cấp quyền sai. | Trust/claim mapping và local authorization. |
| **Chỉ dựa vào SCIM success** | App session, local role hoặc API key vẫn hoạt động. | Verify ở nơi thực thi quyền. |
| **Dùng PAT cá nhân cho workload** | Khi Leaver xảy ra phải giữ quyền người nghỉ để job chạy. | Workload principal riêng, owner và secret lifecycle. |
| **Không kiểm role hierarchy** | Quyền kế thừa rộng hơn dự định. | Tính effective permissions và SoD theo hierarchy. |
| **Retry grant cũ sau Leaver** | Tái cấp quyền đã thu hồi. | Event version, authoritative recheck và idempotency. |

## 22. Role review và access recertification

**Access review** không chỉ hỏi “người dùng có đang trong nhóm X không?”, mà phải trả lời **“còn cần role này trong công việc hiện tại không, trong phạm vi nào và có bằng chứng phê duyệt không?”**.

### 22.1. Những đối tượng cần được rà soát

- User-role assignment có thời hạn, không rõ nguồn hoặc quyền đặc quyền.
- Role catalog đã thay permission hoặc owner.
- Quyền từ nhiều nguồn, group lồng nhau hoặc local assignment.
- Contractor hết hợp đồng, Employee chuyển bộ phận, người đang nghỉ hoặc đã Leaver.
- Service account/workload thiếu owner hoặc hoạt động ngoài mô hình dự kiến.
- Ngoại lệ SoD, break-glass và quyền tạm còn hiệu lực quá hạn.

### 22.2. Quy trình review

1. Cung cấp cho reviewer **role, permissions, scope, nguồn cấp, ngày cấp, lần sử dụng có căn cứ và ngày hết hạn**.
2. Reviewer có đủ thẩm quyền quyết định **giữ, giảm scope, thay role hoặc thu hồi**.
3. Người duyệt không được chỉ dựa vào tần suất sử dụng để giữ quyền; quyền ít dùng nhưng đặc biệt nhạy cảm vẫn cần xem xét.
4. Kết quả được gửi tới IAM để thực thi thay đổi và đối soát.
5. Các assignment không được xác nhận trong thời hạn quy định phải được xử lý theo policy, không tự gia hạn.
6. Lưu dấu vết ai quyết định, căn cứ nào và bằng chứng đã thu hồi tại đích.

## 23. Audit trail của một role assignment

Để kiểm toán, cần truy từ **quyết định nghiệp vụ** đến **quyền đã thực thi**, không lưu bí mật xác thực trong hồ sơ.

### 23.1. Bộ trường cần lưu

| Trường | Ý nghĩa |
| --- | --- |
| **assignmentId, eventId, traceId** | Liên kết yêu cầu, sự kiện và các thao tác. |
| **subjectId, engagementId, accountId** | Gán đúng chủ thể và quan hệ có hiệu lực. |
| **roleId, roleVersion, scope** | Biết chính xác role nào và phạm vi nào. |
| **assignmentSource** | Birthright, workflow request, Mover, temporary hay emergency. |
| **policyId, policyVersion** | Quy tắc eligibility và SoD được áp dụng. |
| **approverIds, approvalRef** | Bằng chứng người có thẩm quyền phê duyệt. |
| **effectiveAt, expiresAt** | Thời gian có hiệu lực và kết thúc. |
| **targetSystem, targetAccountId** | Ứng dụng/đối tượng thực thi. |
| **requestedAction, providerResult** | Grant/revoke và kết quả API. |
| **verifiedAt, verificationMethod** | Khi nào và bằng cách nào trạng thái thực được xác minh. |
| **exceptionId, ownerId** | Sai khác, người chịu trách nhiệm và thời hạn xử lý. |

### 23.2. Ví dụ log không chứa credential

~~~json
{
  "eventType": "ROLE_ASSIGNMENT_VERIFIED",
  "eventId": "iga-evt-20261201-042",
  "traceId": "mover-person-1042-20261201",
  "assignmentId": "role-asg-9042",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "roleId": "finance-report-reader",
  "roleVersion": 4,
  "scope": "finance-department",
  "assignmentSource": "MOVER_POLICY",
  "policyId": "workforce-access-v7",
  "approvalRef": "access-request-810",
  "targetSystem": "finance-portal",
  "targetAccountId": "app-user-882",
  "action": "GRANT",
  "result": "VERIFIED",
  "effectiveAt": "2026-12-01T08:00:00+07:00",
  "verifiedAt": "2026-12-01T01:04:00Z"
}
~~~

Các trường, ID và dữ liệu trên là **schema minh họa**, không phải chuẩn event của RBAC, SCIM hay một IdP cụ thể. Khi cần lưu thông tin cá nhân hoặc quyền nhạy cảm, áp dụng chính sách **tối thiểu hóa dữ liệu, phân quyền xem, mã hóa, bảo vệ tính toàn vẹn và lịch lưu giữ hợp lệ**.

Không lưu mật khẩu, API token, refresh token, private key, cookie hoặc mã MFA để chứng minh một assignment. Audit cần tham chiếu được **lệnh và kết quả**, không cần giá trị credential có thể sử dụng lại.

## 24. Chỉ số đánh giá chất lượng role assignment

| Chỉ số | Cách đo gợi ý | Mục tiêu |
| --- | --- | --- |
| **Tỷ lệ role có owner và permission rõ** | Role có business owner, phạm vi và mapping hợp lệ ÷ role trong catalog. | Giảm role mồ côi/mơ hồ. |
| **Tỷ lệ assignment có căn cứ hợp lệ** | Role đang ACTIVE với source, eligibility, approval phù hợp ÷ tổng assignment cần kiểm. | Ngăn cấp quyền ngoài quy trình. |
| **Tỷ lệ assignment đã xác minh** | Assignment có entitlement ở đích đúng trạng thái mong đợi ÷ tổng assignment phải xử lý. | Phân biệt gửi lệnh và thực thi. |
| **Độ trễ cấp quyền Joiner** | Từ thời điểm được phép kích hoạt tới lúc quyền đích được xác minh. | Đảm bảo sẵn sàng đúng hạn. |
| **Độ trễ thu hồi Mover** | Từ effectiveAt tới khi role cũ bị xác minh không còn quyền. | Giảm privilege creep. |
| **Độ trễ thu hồi Leaver** | Từ thời điểm kết thúc tới khi account/role ở đích đã được xác minh theo phạm vi. | Giảm truy cập tồn dư. |
| **Số assignment quá hạn** | Role hết thời hạn nhưng vẫn active mà không có căn cứ gia hạn. | Giảm quyền tạm tồn dư. |
| **Số xung đột SoD** | Các tổ hợp role/hoạt động xung đột được phát hiện và chưa xử lý. | Kiểm soát gian lận/nâng quyền. |
| **Tỷ lệ review hoàn tất đúng kỳ** | Assignment được rà soát có quyết định và xử lý ÷ tổng đến hạn. | Đảm bảo quyền còn cần thiết. |
| **Số role/app drift** | Chênh lệch expected vs actual assignment và effective permissions. | Phát hiện sửa thủ công/connector lỗi. |
| **Tỷ lệ quyền workload có owner** | Role máy có principal, owner, mục đích và scope hợp lệ ÷ tổng trong phạm vi. | Ngăn service account mồ côi. |
| **Ngoại lệ provisioning quá hạn** | Lệnh grant/revoke lỗi hoặc chưa verified quá hạn xử lý. | Giảm nợ an ninh. |

Chỉ số phải được báo cáo kèm **phạm vi hệ thống, định nghĩa mẫu số, cách kiểm chứng và ngoại lệ**. Không nên tuyên bố “100% quyền đã thu hồi” nếu còn ứng dụng chưa có connector hoặc không quan sát được session/API credential.

## 25. Checklist thiết kế và vận hành Role assignment

1. Đã phân biệt **subject, engagement, account, role, permission, session và entitlement** chưa?
2. Mỗi role có **ID bền vững, owner, mô tả permission, scope, policy và phiên bản** chưa?
3. Việc gán role có dựa vào **nguồn HRIS/hợp đồng đáng tin cậy**, đúng chủ thể và thời gian hiệu lực không?
4. Có tách **birthright**, quyền theo yêu cầu, temporary, privileged và workload roles không?
5. Quy trình có kiểm eligibility, least privilege, **SSD/DSD**, phê duyệt độc lập và nguy cơ self-approval không?
6. Khi dùng role hierarchy, có tính **effective permissions** và tác động SoD của quyền kế thừa không?
7. Có phân biệt direct role assignment với directory/IdP Group và application-local entitlement không?
8. SCIM connector có hỗ trợ đúng Group hoặc thuộc tính role của provider; có cơ chế riêng khi ứng dụng cần API khác không?
9. **Joiner** có kích hoạt đúng Start date, đúng người và đúng quyền baseline không?
10. **Mover** có **thêm role mới và thu hồi role cũ**, bao gồm local assignment và session/token liên quan không?
11. **Leaver** có chặn tài khoản, thu hồi role, group, quyền đặc quyền và các đường truy cập ngoài SSO không?
12. Temporary/JIT assignments có **effectiveAt, expiresAt**, cơ chế thu hồi và review định kỳ không?
13. Service account và workload có owner kỹ thuật, role tối thiểu, credential lifecycle và quy trình decommission không?
14. Có xử lý stale event, duplicate, timeout, ETag/concurrency và **ngăn retry cũ cấp lại role sau Leaver** không?
15. Có đối soát **expected assignments với actual roles, nhóm, session và quyền hiệu lực** tại từng ứng dụng không?
16. Các trường hợp chưa verified có **owner, mức rủi ro, hạn xử lý và biện pháp giảm thiểu** không?
17. Có thể truy từ HRIS event/access request tới policy, phê duyệt, lệnh provision/revoke và bằng chứng ở đích mà không lưu raw credential không?
18. Có đo quyền tồn dư, role quá hạn, SoD conflict, thời gian JML và chất lượng access review không?

**Ghi nhớ:** **Role assignment trong RBAC là quan hệ có điều kiện và có vòng đời giữa chủ thể với vai trò**, chứ không chỉ là thêm người vào một nhóm. Muốn cấp quyền đúng, IAM phải xác minh **đúng người, đúng engagement, đúng role, đúng scope, đúng phê duyệt và thời hạn**. Khi có **Joiner–Mover–Leaver**, hệ thống phải tính lại quyền mong đợi, gán quyền mới và **thu hồi quyền cũ**, kiểm SoD, đối soát qua **IdP, directory, SCIM/ứng dụng**, đồng thời xử lý session/token và quyền dịch vụ có liên quan. Chỉ khi quyền thực tế tại hệ thống đích khớp chính sách và có bằng chứng kiểm toán, tổ chức mới có thể khẳng định đã quản trị role assignment và giảm quyền truy cập tồn dư.
