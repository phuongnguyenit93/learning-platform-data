# Quyền tối thiểu (Least privilege): cấp đúng khả năng cần thiết, trong đúng phạm vi và thời gian

Một nhân viên chăm sóc khách hàng chỉ cần đọc thông tin liên hệ và cập nhật trạng thái yêu cầu hỗ trợ; người đó không cần xem bảng lương hoặc thay đổi cấu hình quản trị. Một dịch vụ gửi thông báo chỉ cần quyền đọc sự kiện cần gửi, không cần tài khoản quản trị toàn bộ cơ sở dữ liệu. Khi một nhân viên chuyển sang bộ phận khác, quyền cũ phải được xem xét và thu hồi, thay vì giữ lại vì “biết đâu sau này cần”.

Các ví dụ trên minh họa **principle of least privilege – nguyên tắc quyền tối thiểu**: **mỗi danh tính, tiến trình hay thành phần chỉ được trao những quyền cần thiết để thực hiện nhiệm vụ hợp lệ, với phạm vi và thời hạn cần thiết**. Nguyên tắc này không chỉ dành cho quản trị viên; nó áp dụng từ tài khoản mới, vai trò nghiệp vụ, API, máy chủ, pipeline cho tới ứng dụng SaaS.

Bài học thuộc chương **Least privilege**, với đề tài **Quyền tối thiểu**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun tập trung quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản, cấp quyền, rà soát và thu hồi khi thay đổi vai trò; đồng thời liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Giải thích quyền tối thiểu theo **chủ thể, hành động, tài nguyên, phạm vi, ngữ cảnh và thời gian**.
- Phân biệt **authentication, authorization, role, permission, entitlement, account, session và token**.
- Thiết kế cấp quyền qua **RBAC, ABAC, phê duyệt, Separation of Duties (SoD), Just-in-Time (JIT) và Privileged Access Management (PAM)**.
- Áp dụng nguyên tắc quyền tối thiểu trong **Joiner, Mover, Leaver** và với **service account/workload identity**.
- Nhận diện **privilege creep, tài khoản mồ côi, role quá rộng, quyền trực tiếp, quyền kế thừa và phiên/token tồn dư**.
- Đối soát quyền thực tế tại IdP, directory, SCIM, ứng dụng và API; thiết lập chỉ số, cảnh báo và bằng chứng kiểm toán.

## 1. Quyền tối thiểu là gì?

**Quyền tối thiểu (Least privilege)** là nguyên tắc thiết kế và vận hành bảo mật theo đó người dùng, tài khoản kỹ thuật hoặc tiến trình **chỉ có những đặc quyền cần thiết cho nhiệm vụ được phép, không nhiều hơn và không lâu hơn yêu cầu**.

Ví dụ:

| Nhu cầu hợp lệ | Quyền phù hợp | Quyền vượt nhu cầu |
| --- | --- | --- |
| Nhân viên hỗ trợ xem ticket được giao. | `ticket.read` với scope ticket thuộc nhóm. | `ticket.admin` trên toàn tổ chức. |
| Kế toán đọc báo cáo của một đơn vị. | `report.read` trong phạm vi đơn vị. | Quyền xuất toàn bộ dữ liệu tài chính mọi công ty. |
| Ứng dụng gửi email thông báo. | Quyền gửi thư theo mẫu/địa chỉ hợp lệ. | Quyền quản trị mailbox của mọi nhân viên. |
| Job sao lưu đọc dữ liệu được chỉ định. | Read-only vào nguồn cần sao lưu; write vào đích lưu trữ. | Delete hoặc quyền tạo user quản trị trên nguồn dữ liệu. |
| Kỹ sư triển khai phiên bản ứng dụng. | Deploy vào dịch vụ/môi trường được phê duyệt trong thời gian tác vụ. | Quyền admin thường trực toàn bộ cloud account. |

Không có một bộ quyền “tối thiểu” dùng cho mọi tổ chức: **quyền cần thiết phụ thuộc nhiệm vụ, phạm vi tài nguyên, hệ thống và thời điểm**. Một quyền hợp lệ hôm nay có thể không còn hợp lệ sau sự kiện Mover hoặc Leaver.

### 1.1. Quyền tối thiểu không phải “càng ít càng tốt” một cách mù quáng

Nếu cấp quá ít quyền khiến người dùng không làm được nhiệm vụ và phải chia sẻ tài khoản quản trị để xử lý, hệ thống có thể trở nên kém an toàn hơn. Mục tiêu là **đủ quyền để hoàn thành công việc được phê duyệt**, kèm cơ chế yêu cầu/điều chỉnh quyền minh bạch khi nhiệm vụ thay đổi.

Điều này cần cân bằng giữa:

1. **Bảo mật:** giảm khả năng lạm dụng và tác động khi tài khoản bị chiếm.
2. **Khả dụng:** công việc hợp lệ vẫn được thực hiện.
3. **Truy vết:** biết ai đã được cấp quyền, lý do và kết quả.
4. **Khả năng thu hồi:** quyền hết nhu cầu phải được loại bỏ đúng thời điểm.

## 2. Các chiều của quyền tối thiểu

Chỉ giảm số lượng role là chưa đủ. Cần tối thiểu hóa **nhiều chiều đồng thời**:

| Chiều | Câu hỏi | Ví dụ tối thiểu hóa |
| --- | --- | --- |
| **Who – chủ thể** | Ai thực sự cần quyền? | Chỉ những người được duyệt, không cả phòng ban nếu chỉ một nhóm cần. |
| **What – hành động** | Cho phép read, write, approve, delete hay administer? | Chỉ read, không write/delete. |
| **Where – tài nguyên** | Trên dự án, tenant, namespace hay dữ liệu nào? | Chỉ các bucket thuộc dự án A. |
| **When – thời gian** | Quyền được dùng bao lâu? | 45 phút khi triển khai thay vì admin thường trực. |
| **Under which conditions – ngữ cảnh** | Xác thực mạnh, thiết bị, tình trạng người dùng, rủi ro? | Yêu cầu MFA chống phishing trước khi dùng quyền đặc biệt. |
| **Through which path – đường truy cập** | Có tài khoản phụ hoặc ứng dụng không qua SSO không? | Thu hẹp cả quyền local/API thay vì chỉ group IdP. |
| **Delegation – khả năng cấp tiếp** | Người có quyền được ủy quyền cho người khác không? | Không cho cấp role admin hoặc tạo API key rộng nếu không cần. |

Một vai trò tên `read-only` vẫn có thể **không tối thiểu** nếu nó cho phép đọc tất cả hồ sơ của mọi tenant. Ngược lại, `write` trong phạm vi tài nguyên rất hẹp có thể cần thiết cho một tác vụ hợp lệ.

### 2.1. Phân biệt truy cập, đặc quyền và phạm vi

- **Access**: khả năng tiếp cận một hệ thống hoặc tài nguyên.
- **Permission**: hành động được phép trên tài nguyên, ví dụ `invoice.read`.
- **Privilege**: một dạng quyền có khả năng đáng kể, thường nói tới thao tác quản trị hoặc mở rộng tác động, nhưng cách dùng thuật ngữ tùy hệ thống.
- **Entitlement**: quyền được biểu diễn trong hệ thống cụ thể, ví dụ role, group, scope, policy binding hoặc local grant.
- **Scope**: giới hạn tài nguyên/ngữ cảnh mà quyền áp dụng.

Trong thiết kế IAM, **`user can sign in` khác `user may read finance report` và khác `user may administer finance system`**.

## 3. Authentication và authorization là hai lớp riêng

**Authentication** trả lời: “Chủ thể đã chứng minh danh tính hợp lệ chưa?”. **Authorization** trả lời: “Chủ thể này có được phép thực hiện hành động này trên tài nguyên này, ở thời điểm này không?”.

Ví dụ nhân viên đăng nhập thành công qua IdP và passkey nhưng vẫn bị từ chối chức năng xóa bản ghi. Điều đó có thể là **kiểm soát quyền tối thiểu đang hoạt động đúng**, không phải lỗi đăng nhập.

| Thành phần | Vai trò | Giới hạn |
| --- | --- | --- |
| **IdP / MFA** | Xác thực danh tính và điều kiện đăng nhập. | MFA thành công không cấp mọi entitlement ở ứng dụng. |
| **SSO / SAML / OIDC** | Chuyển bằng chứng xác thực tới ứng dụng tin cậy. | Token hợp lệ không đồng nghĩa role còn đúng sau Mover. |
| **Directory / Group** | Lưu tài khoản và membership. | Membership không luôn giống quyền hiệu lực ở API. |
| **SCIM / provisioning API** | Tạo, cập nhật, vô hiệu tài khoản và nhóm tại ứng dụng. | HTTP 200 không chứng minh mọi phiên/role cũ đã bị thu hồi. |
| **RBAC / ABAC** | Mô tả quyết định và điều kiện truy cập. | Cần thực thi tại tài nguyên; policy đúng không đủ nếu PEP bị bỏ qua. |
| **PAM / JIT** | Quản lý truy cập đặc quyền theo thời gian/phiên. | Quyền phải được xác minh thu hồi khi tác vụ kết thúc. |

**Quyền tối thiểu cần được thực thi ở nơi tài nguyên thực sự được sử dụng**, không chỉ trong giao diện đăng nhập.

## 4. Nguyên tắc liên quan: Default deny, Need-to-know và SoD

Quyền tối thiểu thường đi cùng các nguyên tắc khác:

| Nguyên tắc | Đóng góp | Điểm khác với Least privilege |
| --- | --- | --- |
| **Default deny** | Không có điều kiện cấp quyền hợp lệ thì từ chối. | Là hành vi mặc định; Least privilege xác định tập quyền cần thiết khi được cho phép. |
| **Need-to-know / Need-to-use** | Chỉ truy cập dữ liệu/chức năng cần cho nhiệm vụ. | Nhấn mạnh nhu cầu nghiệp vụ và phạm vi thông tin. |
| **Separation of Duties (SoD)** | Không cho một cá nhân nắm các bước/quyền xung đột. | Một role nhỏ vẫn có thể gây xung đột với role khác. |
| **Zero Trust** | Không tin ngầm dựa vào vị trí mạng; kiểm danh tính, ngữ cảnh và quyền liên tục phù hợp. | Là cách tiếp cận tổng thể; Least privilege là một thành phần quan trọng. |
| **Defense in depth** | Nhiều lớp kiểm soát độc lập giảm rủi ro. | Phòng vệ nhiều lớp bổ sung cho việc giới hạn quyền. |
| **Just-in-Time (JIT)** | Chỉ kích hoạt quyền khi cần trong thời gian giới hạn. | Là cách triển khai chiều thời gian của Least privilege. |

### 4.1. Ví dụ SoD

Một người được gán riêng `vendor.create` và `payment.approve`, mỗi permission đều nhỏ. Nhưng kết hợp cả hai có thể cho phép người đó tạo nhà cung cấp và phê duyệt chi trả cho chính nhà cung cấp đó. **Từng quyền có vẻ tối thiểu, tổ hợp lại có thể không an toàn**.

Do vậy, kiểm **tập quyền hiệu lực**, các role kế thừa và những quy tắc SoD trước khi phê duyệt assignment.

## 5. Thiết kế quyền theo chủ thể – hành động – tài nguyên – thời gian

Một assignment nên có đủ thông tin để kiểm chứng:

~~~json
{
  "assignmentId": "asg-9012",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "applicationId": "expense-portal",
  "permission": "report.read",
  "resourceScope": {
    "tenantId": "tenant-a",
    "departmentId": "FINANCE"
  },
  "approvalRef": "APR-501",
  "effectiveAt": "2026-12-01T08:00:00+07:00",
  "expiresAt": "2027-01-01T00:00:00+07:00",
  "status": "APPROVED"
}
~~~

Đây là **mô hình dữ liệu nội bộ minh họa**, không phải schema bắt buộc của SCIM/RBAC/OIDC. Các giá trị ID và thời gian đều giả định. Khi triển khai cần có nguồn sở hữu permission, cách phân biệt quyền **APPROVED** với quyền **PROVISIONED/VERIFIED**, và policy xử lý khi một người có nhiều nguồn assignment.

### 5.1. Phân biệt approval với activation

Các mốc thường gặp:

1. **RequestedAt:** người dùng/manager yêu cầu quyền.
2. **ApprovedAt:** owner cho phép về mặt nghiệp vụ.
3. **EffectiveAt:** quyền được phép bắt đầu có hiệu lực.
4. **ProvisionedAt:** lệnh tạo/cập nhật role tại đích đã được ghi nhận.
5. **VerifiedAt:** hệ thống đã đối soát quyền thực tế.
6. **ExpiresAt:** hạn quyền phải được thu hồi hoặc đánh giá lại.
7. **RevokedVerifiedAt:** xác nhận hệ thống đích không còn quyền.

**Được phê duyệt không đồng nghĩa quyền đã có hiệu lực**, cũng như **gửi lệnh thu hồi không đồng nghĩa đã hết khả năng truy cập**.

## 6. Bắt đầu từ nhu cầu công việc và role catalog

Để áp dụng Least privilege trên quy mô doanh nghiệp, IAM cần biết từng người/đội **làm nhiệm vụ gì** và ứng dụng có **những permission nào**.

### 6.1. Role catalog

| Trường | Ý nghĩa |
| --- | --- |
| **roleId** | Định danh role bền vững trong namespace hệ thống. |
| **purpose** | Nhiệm vụ nghiệp vụ cụ thể mà role hỗ trợ. |
| **permissionSet** | Tập permission thực tế, gồm cả quyền kế thừa. |
| **resourceScope** | Tenant, dự án, môi trường, vùng dữ liệu hoặc resource. |
| **roleOwner** | Người/nhóm chịu trách nhiệm quyền và tác động nghiệp vụ. |
| **eligibilityPolicy** | Điều kiện đủ tư cách, loại nhân sự và trạng thái JML. |
| **approvalPolicy** | Người hoặc cơ chế phê duyệt theo rủi ro. |
| **sodConstraints** | Những role/quyền không thể kết hợp. |
| **defaultDuration / maxDuration** | Thời hạn phù hợp với mức nhạy cảm. |
| **provisioningMapping** | Cách triển khai tới directory group, SCIM, app role hoặc API. |
| **reviewAt / version** | Thời điểm rà soát và phiên bản định nghĩa role. |

Một role tên `FinanceUser` không đủ thông tin để phê duyệt. Cần biết nó có cho đọc, chỉnh sửa, xuất dữ liệu, duyệt chi hay quản trị cấu hình hay không.

### 6.2. Phân biệt business role và technical role

**Business role** mô tả công việc (ví dụ nhân viên duyệt hóa đơn). **Technical role** biểu diễn quyền ứng dụng (ví dụ `invoice.approve` trên SaaS A). Một business role có thể ánh xạ tới nhiều technical entitlements ở nhiều ứng dụng.

~~~text
Business role: Finance report reader
    |
    +--> IdP group: grp-finance-reports
    +--> SaaS A: application role = report-reader
    +--> API B: scope = reports.read, tenant = A
    +--> Storage C: read-only theo prefix /finance/approved/
~~~

**Không nên coi một group IdP đã đủ để xác minh mọi role ở đích**. Từng ứng dụng có cơ chế authorization riêng.

## 7. RBAC: cấp role nhỏ, có phạm vi và không kế thừa ngoài ý muốn

**Role-Based Access Control (RBAC)** giúp gom permission theo vai trò, giảm việc cấp từng quyền thủ công cho từng người. Tuy nhiên, Role-Based **không tự động** đồng nghĩa Least privilege.

### 7.1. Tránh role quá rộng

| Role ban đầu | Vấn đề | Thiết kế hẹp hơn |
| --- | --- | --- |
| `admin` của toàn tenant | Gộp quản lý user, dữ liệu, thanh toán và cấu hình. | `user-support-admin`, `billing-reader`, `config-operator` theo nhu cầu. |
| `data-editor` mọi dự án | Không giới hạn môi trường và nhóm dữ liệu. | `project-a-data-editor` trong một tenant/môi trường. |
| `engineering` toàn công ty | Phòng ban lớn có nhu cầu khác nhau. | Vai trò theo team/workload và phạm vi dự án. |
| `all-employees` đọc tài liệu nhạy cảm | Birthright cấp quá rộng. | Nhóm được owner phê duyệt hoặc ABAC theo classification. |

### 7.2. Role hierarchy

Trong **role hierarchy**, một role cấp cao có thể kế thừa permission của role thấp hơn:

~~~mermaid
flowchart TD
    A["finance-admin"] --> B["finance-editor"]
    B --> C["finance-reader"]
    C --> D["report.read"]
    B --> E["report.update"]
    A --> F["access.manage"]
~~~

Khi gán `finance-admin`, phải tính **tập quyền hiệu lực** gồm cả permission kế thừa. Thay permission của `finance-reader` cũng có thể mở rộng quyền của những chủ thể có role cấp cao. Cần rà soát tác động trên toàn bộ assignment trước khi sửa role catalog.

### 7.3. Nguy cơ role explosion

Phân nhỏ role quá mức có thể tạo ra hàng nghìn role khó quản trị. Thay vì tạo một role cho từng kết hợp user/dự án/chức năng, có thể dùng **role rõ nhiệm vụ + scope/ABAC**. Mục tiêu là **permission chính xác mà vẫn có thể rà soát**, không phải tối đa hóa số lượng role.

## 8. ABAC: làm hẹp quyền theo thuộc tính và ngữ cảnh

**Attribute-Based Access Control (ABAC)** xét các thuộc tính của chủ thể, tài nguyên, hành động và môi trường.

Ví dụ:

~~~text
PERMIT report.read nếu:
    subject.lifecycleState == ACTIVE
    AND subject.departmentId == resource.ownerDepartmentId
    AND subject.approvedDataLevel >= resource.classificationLevel
    AND action == read
    AND environment.authStrength meets requiredStrength
~~~

Giả mã minh họa. Thứ bậc `approvedDataLevel` phải được định nghĩa; không so sánh chuỗi phân loại theo bảng chữ cái. Phải kiểm nguồn có thẩm quyền của `departmentId`, `classificationLevel` và `authStrength`.

### 8.1. RBAC và ABAC có thể kết hợp

RBAC nói người dùng được phép làm **loại thao tác** nào; ABAC thu hẹp thêm **phạm vi, thời gian, tenant và điều kiện**.

Ví dụ:

~~~text
User có role: report-reader
AND resource.tenantId == user.tenantId
AND resource.projectId IN user.approvedProjects
AND request.action == read
AND user.lifecycleState == ACTIVE
=> PERMIT
~~~

Không cho client tự gửi `user.tenantId` hoặc `user.approvedProjects` để vượt policy. Thuộc tính ảnh hưởng quyền phải được xác minh từ nguồn được ủy quyền, chú ý dữ liệu stale sau Mover/Leaver.

### 8.2. Policy Enforcement Point

Một policy ABAC đúng không đủ nếu API có đường gọi bỏ qua kiểm tra. **Policy Enforcement Point (PEP)** phải bảo đảm mỗi request nhạy cảm đi qua xác thực và authorization cho đúng **subject, action, resource, tenant, thời điểm**. Chỉ kiểm quyền ở UI không ngăn request trực tiếp tới API.

## 9. Privileged Access Management và Just-in-Time

Các quyền thay cấu hình bảo mật, tạo người dùng, quản lý khóa hoặc xóa dữ liệu production cần kiểm soát chặt hơn role nghiệp vụ thông thường.

**Privileged Access Management (PAM)** có thể giúp quản lý danh tính quản trị, session, credential và phê duyệt. **Just-in-Time (JIT)** làm ngắn cửa sổ có quyền đặc biệt.

### 9.1. Ví dụ kỹ sư cần sửa cấu hình production

Thay vì cấp `production-admin` thường trực:

1. Kỹ sư xác thực mạnh bằng phương thức phù hợp, ưu tiên chống phishing cho quyền nhạy cảm.
2. Họ nêu **ticket, tác vụ, môi trường và thời gian dự kiến**.
3. Hệ thống xác minh người đó còn quan hệ làm việc hợp lệ và đủ điều kiện thực hiện.
4. Owner hoặc policy cấp phê duyệt theo rủi ro, kiểm SoD.
5. PAM/JIT kích hoạt **role hẹp nhất** trên hệ thống cần thao tác.
6. Phiên quản trị được ghi vết theo chính sách; không phát tán credential dài hạn.
7. Quyền tự hết hạn hoặc bị thu hồi sớm khi hoàn tất, Leaver hay có dấu hiệu sự cố.
8. Hệ thống kiểm lại **permission và session thực tế** để xác nhận kết thúc.

### 9.2. Just Enough Administration

**Just Enough Administration (JEA)** là cách giảm số lượng lệnh/chức năng quản trị mà người vận hành được thực hiện trong một ngữ cảnh nhất định. Khác với chỉ rút ngắn thời hạn, JEA thu hẹp **tập thao tác**.

Least privilege tốt thường kết hợp cả:

- **Just Enough:** chỉ đúng lệnh/chức năng.
- **Just in Time:** chỉ đúng thời gian.
- **Just in Scope:** chỉ đúng tài nguyên/môi trường.
- **Just in Context:** chỉ khi đủ xác thực và điều kiện rủi ro.

### 9.3. Break-glass

Tài khoản khẩn cấp hoặc cơ chế break-glass cần đủ khả năng cứu hệ thống khi thành phần xác thực thông thường gặp sự cố, nhưng vẫn phải có **owner, quy trình kích hoạt, kiểm soát lưu trữ, giám sát sử dụng và hậu kiểm**. Không được dùng ngoại lệ khẩn làm quyền admin thường trực cho công việc thường ngày.

## 10. Least privilege trong Joiner: không cấp sớm và không cấp rộng

**Joiner** là giai đoạn nhân viên/Contractor được xác minh và chuẩn bị tài khoản. Một sai lầm là cho rằng **tài khoản đã được tạo** thì mọi quyền công việc đều nên hoạt động.

### 10.1. Một quy trình Joiner có kiểm soát

1. HRIS hoặc nguồn hợp đồng xác nhận Person/Engagement, worker type, department, Start date.
2. IAM/IGA liên kết **subject ID ổn định**, kiểm trùng và xác minh người.
3. Tạo directory/IdP account, có thể **pre-provision** trước ngày bắt đầu nhưng giữ trạng thái/phạm vi phù hợp.
4. Tính **birthright entitlements** hẹp từ chính sách đã duyệt.
5. Quyền ngoài baseline qua phê duyệt của manager/data owner/application owner nếu chính sách yêu cầu.
6. Kiểm SoD, scope, thời hạn, điều kiện MFA và thiết bị.
7. Đến `activationAt`, kiểm lại HRIS và policy hiện hành trước khi kích hoạt.
8. Đồng bộ SCIM/API tới từng ứng dụng và **đọc lại quyền**.
9. Ghi bằng chứng trạng thái và ngoại lệ chưa hoàn tất.

### 10.2. Preboarding và Start date

Giả sử hồ sơ được tạo ngày 20/11 nhưng Start date là 01/12. Có thể chuẩn bị email/tài khoản từ 25/11; điều đó **không cho phép mở quyền production ngày 25/11**. Nếu preboarding cần truy cập tài liệu hướng dẫn, nên thiết kế **role preboarding riêng** với phạm vi rất hẹp, đúng người và hạn sử dụng rõ.

**Start date là mốc nghiệp vụ**, còn `createdAt`, `provisionedAt` và `activatedAt` là các mốc kỹ thuật khác nhau. Việc trì hoãn hoặc hủy tuyển dụng phải làm thay đổi quyền kỳ vọng trước khi tác vụ cấp quyền chạy.

### 10.3. Birthright cần được rà soát

Role baseline `all-employees` dễ mở rộng theo thời gian. Khi một ứng dụng được thêm vào nhóm baseline, **mọi Employee có thể nhận thêm quyền** mà không có yêu cầu riêng. Vì vậy, quyền mặc định phải có owner, purpose, tập permission rõ, đánh giá dữ liệu nhạy cảm và kỳ rà soát.

## 11. Least privilege trong Mover: tránh privilege creep

**Mover** là thay đổi vị trí, bộ phận, quản lý, dự án, nhiệm vụ hoặc loại quan hệ. **Privilege creep** xảy ra khi quyền mới được cấp nhưng quyền cũ không được thu hồi, làm quyền tích lũy theo thời gian.

### 11.1. Ví dụ Sales → Finance

| Trạng thái | Trước Mover | Sau Mover cần đạt |
| --- | --- | --- |
| **Department** | SALES | FINANCE. |
| **Business role** | sales-representative | finance-report-reader. |
| **App group** | sales-customers-editors | finance-reports-readers. |
| **Dữ liệu được xem** | Khách hàng thuộc Sales scope | Báo cáo Finance được duyệt. |
| **Quyền phải thu hồi** | Chưa phát sinh thay đổi | sales-customers-editors và local grants cũ. |
| **Session/token** | Có thể mang claim Sales | Phải xem thu hồi/kiểm quyền lại. |

### 11.2. Tính lại trạng thái mong đợi, không chỉ thêm mới

~~~text
expected = evaluateCurrentRoleAndAttributePolicy(subject, effectiveAt)
actual   = readEffectiveAccessAcrossTargets(subject)

toGrant  = expected - actual
toRevoke = actual - expected

processRevocationsAndGrantsWithControls()
verifyEffectiveAccessAtEachTarget()
~~~

Đây chỉ là **mô hình xử lý khái niệm**. Quyền thực tế còn phụ thuộc **role hierarchy, nhóm lồng nhau, quyền trực tiếp, session và nhiều nguồn assignment**. Không xóa một quyền nếu còn một căn cứ cấp hợp lệ khác, trừ khi policy lifecycle (ví dụ Leaver) yêu cầu chặn toàn bộ.

### 11.3. Hai chiều của Mover

- **Cấp đúng quyền mới:** Finance reader được phê duyệt và có hiệu lực theo thời gian.
- **Thu hồi quyền cũ:** Sales writer và quyền ứng dụng/local/API không còn chính đáng.

Nếu chỉ kiểm “Finance reader đã vào được” mà không kiểm “Sales writer đã bị từ chối”, quy trình có thể bỏ sót truy cập tồn dư.

### 11.4. Manager thay đổi không tự cấp quyền nhạy cảm

Một manager mới có thể nhận quyền phê duyệt một số yêu cầu theo cơ cấu tổ chức, nhưng không có nghĩa được quyền xem mọi dữ liệu cấp dưới. Cần kiểm **phạm vi trách nhiệm, quan hệ có hiệu lực, SoD và phê duyệt của data owner**. Đặc biệt các workflow approval đang chờ phải được xử lý theo chính sách khi manager chuyển.

## 12. Least privilege trong Leaver: chặn mọi đường truy cập còn tồn tại

**Leaver** là giai đoạn kết thúc quan hệ và thu hồi khả năng truy cập. Nguyên tắc quyền tối thiểu lúc này thường yêu cầu **không còn quyền nghiệp vụ hoạt động** cho engagement đã kết thúc, ngoài những ngoại lệ được quản trị rõ theo luật/quy định và không mở quyền truy cập cho người đã rời tổ chức.

### 12.1. Chuỗi thu hồi

~~~mermaid
flowchart TD
    A["HRIS / hợp đồng phát Leaver<br/>subject + engagement + effectiveAt"] --> B["IAM / IGA xác minh nguồn<br/>và trạng thái hiện hành"]
    B --> C["Disable IdP/directory<br/>ngăn đăng nhập mới"]
    B --> D["Thu hồi Group, Role,<br/>direct entitlement tại ứng dụng"]
    B --> E["SCIM / API deprovision<br/>các local accounts"]
    B --> F["Thu hồi sessions, tokens,<br/>PAT/API keys theo phạm vi"]
    B --> G["Chuyển owner workload<br/>và xử lý delegated access"]
    C --> H["Reconciliation theo từng đích"]
    D --> H
    E --> H
    F --> H
    G --> H
    H --> I{"Access đã được<br/>xác minh thu hồi?"}
    I -->|"Có"| J["REVOKED_VERIFIED<br/>Audit"]
    I -->|"Chưa"| K["Exception + owner<br/>giảm thiểu + hạn xử lý"]
~~~

### 12.2. Những trạng thái không được đồng nhất

| Trạng thái | Bằng chứng | Chưa chứng minh |
| --- | --- | --- |
| **HRIS = TERMINATED** | Quan hệ đã kết thúc. | IdP/SaaS đã vô hiệu hóa. |
| **IdP account disabled** | Đăng nhập mới qua IdP có thể bị chặn. | Local password, session ở app và API key đã bị thu hồi. |
| **SCIM active=false** | Provider đã nhận/áp dụng trạng thái tài khoản theo nghĩa của nó. | Mọi token/PAT/role riêng đều mất hiệu lực. |
| **Group removed** | Membership tại một hệ thống đã đổi. | Direct role hoặc token cũ không còn quyền. |
| **Application access denied verified** | Đường truy cập được kiểm tra bị từ chối. | Mọi hệ thống ngoài phạm vi đều đã được kiểm chứng. |

**Không đánh dấu Leaver hoàn tất chỉ vì lệnh vô hiệu hóa trả HTTP 200**. Cần theo dõi kết quả từng hệ thống, độ trễ, ngoại lệ và thời gian quyền thực tế còn sử dụng được.

### 12.3. Rehire và chuyển loại quan hệ

Khi người đã nghỉ được tuyển lại hoặc Contractor thành Employee:

- Xác minh cùng Person/subject nếu có căn cứ, nhưng ghi **engagement mới**.
- Không tự mở lại toàn bộ role/credential/approval từ giai đoạn cũ.
- Tính quyền theo vị trí, phạm vi và chính sách hiện hành.
- Kiểm tài khoản phụ, direct grants và nhóm cũ trước khi kích hoạt.
- Đối soát quyền tại từng ứng dụng như một quy trình Joiner/Mover hợp lệ.

## 13. Least privilege đối với service account và workload identity

Tài khoản máy thường chạy lâu dài, không có thao tác xác thực tương tác hàng ngày nên dễ bị bỏ quên. Tuy nhiên, một service principal bị lộ credential có thể truy cập dữ liệu hoặc API ở quy mô lớn.

### 13.1. Những thuộc tính cần quản lý

| Thuộc tính | Mục đích |
| --- | --- |
| **principalId / workloadId** | Xác định danh tính kỹ thuật và ứng dụng sử dụng. |
| **ownerTeam** | Có nhóm chịu trách nhiệm vận hành và cấp quyền. |
| **environment / tenant** | Phân biệt development, staging và production. |
| **permissionScope** | API, tài nguyên và hành động cần thiết. |
| **credentialType** | Managed/workload identity, certificate, secret, API key tùy hệ thống. |
| **credentialExpiry/rotation** | Quản lý rủi ro bí mật và thời gian hiệu lực. |
| **reviewAt / decommissionAt** | Không để principal tồn tại vô hạn sau khi workload ngừng. |

### 13.2. Ví dụ job đồng bộ báo cáo

Job chỉ cần đọc dữ liệu giao dịch đã tổng hợp và ghi báo cáo sang storage được chỉ định. Quyền hợp lý:

~~~text
Source database:
    SELECT trên các view báo cáo được cho phép
    không cần CREATE USER, DROP TABLE, UPDATE dữ liệu gốc

Target storage:
    WRITE vào prefix /exports/finance-report/
    không cần WRITE/DELETE toàn bucket

Secret/configuration:
    READ đúng secret của job nếu thật sự cần
    không có quyền liệt kê mọi secret tenant
~~~

Đây là mô tả permission khái niệm; cách biểu diễn SQL, IAM policy và storage prefix phụ thuộc sản phẩm. Cần kiểm **quyền thực tế** chứ không chỉ tên role `readonly`.

### 13.3. Ưu tiên credential ngắn hạn

Khi nền tảng hỗ trợ, sử dụng **workload identity federation/managed identity**, token ngắn hạn hoặc chứng chỉ có vòng đời được quản lý thay vì mật khẩu dùng chung hoặc key nằm trong mã nguồn. Quyền tối thiểu cần được áp dụng **cả cho credential và quyền API mà credential có thể sử dụng**.

Credential ngắn hạn **không tự bảo đảm permission hẹp** nếu token có scope admin; tương tự quyền API hẹp không bù được cho việc dùng secret chung bị lộ ở nhiều môi trường.

### 13.4. Khi owner Employee rời tổ chức

Khi kỹ sư sở hữu pipeline nghỉ việc, không nhất thiết phải xóa workload còn hợp lệ. Cần **chuyển owner, thay credential nếu bị chia sẻ, kiểm PAT cá nhân và rà soát permission**, sau đó xác minh workload vẫn hoạt động đúng quyền. Không duy trì tài khoản của người đã nghỉ chỉ để job tiếp tục chạy.

## 14. Least privilege trong cloud, container, API và dữ liệu

Các nền tảng hiện đại có nhiều lớp policy: cloud IAM, Kubernetes RBAC, database grants, object storage ACL, API scopes và network controls. Cần áp dụng quyền tối thiểu **theo từng lớp**, tránh role toàn quyền vì khó phân tích.

### 14.1. Cloud IAM

- Dùng role/policy quản lý **đúng action và resource ARN/ID** theo khả năng nền tảng.
- Giới hạn môi trường, tenant, project/subscription/account, tránh quyền tổ chức toàn cục nếu không cần.
- Phân biệt **quyền thao tác tài nguyên** với **quyền gán role hoặc tạo credential**; quyền cấp quyền cho người khác có thể mở đường nâng đặc quyền.
- Theo dõi **effective permissions**, gồm quyền kế thừa, policies ở nhiều tầng và ngoại lệ.
- Không xem cấu hình `read-only` là an toàn nếu cho xuất toàn bộ dữ liệu nhạy cảm.

### 14.2. Kubernetes và service account

Trong Kubernetes, có thể dùng **Role/ClusterRole và RoleBinding/ClusterRoleBinding** để cấp quyền API cho user hoặc ServiceAccount.

| Tình huống | Quyền hẹp hơn |
| --- | --- |
| Job đọc ConfigMap của một namespace. | Role chỉ có `get` trên ConfigMap cần thiết trong namespace. |
| CI/CD triển khai một workload. | Quyền cập nhật những resource cần triển khai, không phải cluster-admin. |
| Monitoring đọc metrics phù hợp. | Read-only trên API/resource được phê duyệt. |
| ServiceAccount trong pod. | Không tự gắn token/secret hoặc cluster role rộng khi không cần. |

**Namespace scoping** và quyền `get/list/watch` cần được đánh giá riêng: có quyền `list` toàn bộ secret trong namespace là mạnh hơn nhiều so với chỉ đọc một ConfigMap.

### 14.3. API scope và OAuth

Một access token dành cho API cần được resource server kiểm **issuer, audience, scope/role, thời hạn và ràng buộc chính sách**. Scope như `orders.read` thường hẹp hơn `orders.*`, nhưng vẫn cần kiểm **đơn hàng thuộc tenant/khách hàng nào**.

**Không dùng ID token OIDC thay access token** để cấp quyền gọi API. ID token chứng minh xác thực cho RP, không tự là vật mang quyền đến mọi resource server.

### 14.4. Database và object storage

Đối với cơ sở dữ liệu, tránh ứng dụng dùng **database superuser** chỉ vì cần đọc/ghi vài bảng. Có thể cấp quyền theo schema, view, thủ tục hoặc cơ chế kiểm hàng/dòng nếu nền tảng hỗ trợ. Đối với storage, giới hạn **bucket/prefix/object, thao tác đọc/ghi/xóa và thời hạn truy cập** theo nhu cầu.

Một API có quyền SELECT toàn bộ bảng khách hàng nhưng chỉ hiển thị một bản ghi trong UI vẫn có thể bị lộ hàng loạt qua lỗi ứng dụng. Least privilege ở database/API giúp giảm tác động khi tầng khác bị xâm nhập.

## 15. Least privilege trong SSO, SCIM và RBAC/ABAC

**Đồng bộ quyền** xuyên hệ thống thường gặp ba khoảng cách:

1. **Identity authoritative state:** HRIS/IGA nói người đó đang làm công việc gì và được duyệt quyền nào.
2. **Provisioned state:** IdP/directory/SCIM đã cập nhật User/Group/role gì.
3. **Effective access:** API/ứng dụng thực sự chấp nhận quyền nào, kể cả local grants và sessions.

~~~mermaid
flowchart LR
    HRIS["HRIS / JML<br/>Source of truth"] --> IGA["IGA / policy<br/>Expected roles + approvals"]
    IGA --> IDP["IdP / Directory<br/>Groups + SSO claims"]
    IGA --> SCIM["SCIM / API<br/>Provisioning"]
    IDP --> APP["Application / API"]
    SCIM --> APP
    APP --> PEP["PEP / Authorization<br/>Effective access"]
    IGA --> REC["Reconciliation"]
    IDP --> REC
    SCIM --> REC
    PEP --> REC
    REC -->|"Drift / stale role / residual access"| IGA
~~~

### 15.1. Những khác biệt cần nhớ

| Cơ chế | Làm tốt việc gì? | Không tự giải quyết |
| --- | --- | --- |
| **IdP/SSO** | Xác thực tập trung, MFA và cung cấp bằng chứng đăng nhập liên thông. | Quyền local/app, phiên cũ, dữ liệu ngoài phạm vi của IdP. |
| **SAML/OIDC claim** | Chuyển những thuộc tính đã được issuer xác nhận. | Tính mới của role sau Mover hoặc phạm vi quyền dữ liệu tại API. |
| **SCIM User/Group** | Cấp phát/tắt tài khoản, cập nhật nhóm tùy provider. | Mọi permission model của vendor hoặc thu hồi token/PAT tự động. |
| **RBAC** | Tập hợp permission theo vai trò. | Tự kiểm resource scope, thời gian và điều kiện nếu không thiết kế thêm. |
| **ABAC** | Kiểm quyền theo attribute/context. | Dữ liệu thuộc tính chính xác và cập nhật nếu nguồn/PIP sai. |
| **PAM/JIT** | Giới hạn quyền đặc biệt trong thời gian/phiên. | Thay thế hoàn toàn inventory, role review hoặc Leaver. |

**Không mở thêm đường đăng nhập local chỉ dùng mật khẩu để “sửa lỗi SSO”** trừ khi có thiết kế dự phòng được duyệt, được bảo vệ và theo dõi đầy đủ. Đường đó có thể tạo quyền ngoài kiểm soát IAM.

## 16. Quyền trực tiếp, quyền kế thừa và quyền ngoài catalog

Để đánh giá quyền tối thiểu, phải tính **effective access**, không chỉ assignments trực tiếp.

| Nguồn quyền | Ví dụ | Rủi ro |
| --- | --- | --- |
| **Direct app assignment** | User được gán role admin tại SaaS. | IAM thu hồi group nhưng role local vẫn hoạt động. |
| **Directory group** | User nằm trong nhóm finance-readers. | Role kế thừa hoặc nested group mở rộng ngoài dự kiến. |
| **Dynamic group** | Điều kiện `department=FINANCE`. | Attribute sai/stale dẫn đến membership sai. |
| **Role hierarchy** | Admin kế thừa Editor và Reader. | Review chỉ nhìn tên role trực tiếp mà bỏ sót quyền kế thừa. |
| **Delegated access** | User được ủy quyền đọc hộ dữ liệu. | Delegation không bị thu hồi khi Mover/Leaver. |
| **Token/PAT/API key** | Access token còn hạn sau khi account disable. | API tiếp tục cho truy cập nếu không kiểm trạng thái hiện tại. |
| **Backup/restore hoặc manual change** | User/Group cũ được khôi phục hoặc sửa ngoài IGA. | Quyền đã thu hồi bị tái xuất hiện. |

### 16.1. Không dùng email làm khóa của quyền

Email, username và distinguished name (DN) có thể đổi hoặc tái sử dụng. Cần liên kết quyền tới **subject ID, engagement ID, account ID của provider và resource scope** đúng namespace.

Đặc biệt với rehire, người quay lại có thể có cùng email nhưng **không được tự động nhận entitlement/approval của engagement cũ**.

## 17. Quyền tạm thời và kiểm soát thời hạn

Một quyền dự án có thể cần hoạt động trong hai tuần; không có lý do giữ nó một năm nếu dự án đã đóng.

### 17.1. Mẫu assignment tạm

~~~yaml
# Dữ liệu minh họa nội bộ, không phải SCIM/RBAC schema chuẩn.
assignmentId: project-read-access-910
subjectId: person-1042
engagementId: EMP-5812
roleId: project-document-reader
scope:
  tenantId: tenant-a
  projectId: project-88
effectiveAt: "2026-12-01T08:00:00+07:00"
expiresAt: "2026-12-15T18:00:00+07:00"
approvalRef: APR-992
revokeOn:
  - EXPIRES
  - MOVER_INELIGIBLE
  - LEAVER
  - SECURITY_INCIDENT
~~~

Giá trị ngày giờ chỉ là ví dụ. Cần thống nhất timezone, giờ bắt đầu/kết thúc và ý nghĩa mốc thời gian. **Không sử dụng `createdAt` thay cho `effectiveAt`**.

### 17.2. Gia hạn là quyết định mới

Khi cần gia hạn:

- Xác minh nhiệm vụ còn hợp lệ.
- Kiểm role owner, scope, SoD và phê duyệt.
- Ghi mốc thời gian mới và lý do.
- Bảo đảm assignment không kéo dài vô hạn do một job tự động lỗi.
- Xác minh quyền đã bị thu hồi khi không còn căn cứ.

## 18. Access request và phê duyệt theo rủi ro

Không phải mọi quyền cần cùng số bước phê duyệt. Một role đọc tài liệu nội bộ phổ biến có thể được cấp từ chính sách baseline. Quyền xuất dữ liệu nhạy cảm hoặc thay cấu hình IAM có thể cần phê duyệt nhiều bên.

### 18.1. Câu hỏi trước khi phê duyệt

1. Người yêu cầu là ai, còn engagement hợp lệ không?
2. Tác vụ cụ thể là gì, có thể hoàn thành bằng role hẹp hơn không?
3. Dữ liệu/tài nguyên thuộc owner và classification nào?
4. Scope có đang vượt tenant, bộ phận hoặc dự án cần thiết không?
5. Quyền sẽ dùng bao lâu? Có thể dùng JIT không?
6. Có tổ hợp quyền xung đột SoD hoặc khả năng cấp tiếp quyền không?
7. Có đường truy cập hiện tại đã đủ nhưng người dùng chưa biết dùng không?
8. Ai có thẩm quyền duyệt và có tránh self-approval không?
9. Làm sao xác minh việc cấp quyền và cách thu hồi khi hết nhu cầu?

### 18.2. Không cấp admin để xử lý ticket tiện hơn

Nếu người dùng bị HTTP 403 ở một chức năng, cần phân loại:

- SSO/IdP đã xác thực thành công chưa?
- Local account có tồn tại và đúng chủ thể không?
- Role/permission cần thiết là gì?
- RBAC/ABAC đang từ chối đúng policy hay provisioning bị lỗi?
- Có thiếu scope, group hoặc thuộc tính stale không?

**Cấp quyền admin để “thử” là phản ứng sai** nếu chưa xác định nguyên nhân và có phê duyệt phù hợp. Sửa lỗi quyền phải ở **lớp đúng**, không phá nguyên tắc least privilege.

## 19. Access review và recertification

Quyền có thể từng hợp lệ nhưng trở nên thừa sau thay đổi tổ chức. **Access review** giúp phát hiện và xác nhận lại nhu cầu.

### 19.1. Dữ liệu reviewer cần thấy

| Dữ liệu | Vì sao cần |
| --- | --- |
| Chủ thể, engagement, manager và trạng thái JML | Biết người còn hợp lệ và đúng nhiệm vụ. |
| Role/permission, resource scope | Hiểu chính xác quyền thay vì chỉ nhìn tên nhóm. |
| Role owner, data owner và approvalRef | Xác định thẩm quyền quyết định. |
| Assignment source, effectiveAt, expiresAt | Biết quyền do baseline, dự án hay ngoại lệ. |
| Effective access, role hierarchy và direct grants | Tránh bỏ sót quyền ngoài IGA. |
| Dấu hiệu sử dụng và dữ liệu rủi ro phù hợp | Hỗ trợ quyết định giữ/giảm/thu hồi. |
| Kết quả review kỳ trước và ngoại lệ chưa xử lý | Tránh gia hạn quyền không được kiểm chứng. |

### 19.2. Các quyết định review

- **Keep:** vẫn cần trong scope và thời hạn hiện tại.
- **Reduce:** giữ nhiệm vụ nhưng giảm action/resource/tenant.
- **Replace:** thay role quá rộng bằng role hẹp hơn.
- **Expire/Revoke:** không còn nhu cầu hoặc hết hiệu lực.
- **Investigate:** dữ liệu không đủ rõ, tạm áp dụng biện pháp phù hợp rủi ro và gán owner.

**Không sử dụng “đã đăng nhập gần đây” làm bằng chứng quyền vẫn cần thiết.** Có quyền rất ít dùng nhưng nguy hiểm; cũng có quyền được dùng thường xuyên vì lỗi quy trình, không đồng nghĩa hợp lệ.

### 19.3. Role mining và quyền sử dụng thực tế

Phân tích log và entitlement hiện có có thể giúp phát hiện role thừa, quyền không dùng và khả năng gộp hoặc tách role. Tuy nhiên, **dữ liệu sử dụng không phản ánh toàn bộ nghĩa vụ nghiệp vụ**: một tác vụ ứng cứu chỉ thực hiện khi có sự cố có thể hiếm khi xuất hiện trong log. Quyết định thay role vẫn cần owner và đánh giá rủi ro.

## 20. Phòng chống quyền tồn dư và lỗi bất đồng bộ

Hệ thống JML thường làm việc với nhiều ứng dụng qua sự kiện và connector. Một lệnh thu hồi có thể thất bại, tới muộn hoặc bị sự kiện cũ ghi đè.

### 20.1. Ví dụ retry Mover sau Leaver

~~~text
10:00  Mover: thêm role finance-reader.
10:02  SCIM Group PATCH timeout; chưa biết trạng thái đích.
10:05  HRIS gửi Leaver có hiệu lực: thu hồi quyền.
10:08  IdP đã disable người dùng.
10:10  Worker retry Mover cũ, cố thêm finance-reader.
~~~

Nếu worker không kiểm **trạng thái HRIS hiện hành**, nó có thể tái cấp quyền sau khi Leaver đã hoàn tất tại một số đích.

Cơ chế cần có:

1. **Event ID và source version** để chống xử lý trùng.
2. **EffectiveAt** để không dùng sự kiện tới trễ sai thời điểm.
3. **Kiểm lại nguồn hiện hành** trước các lệnh cấp quyền có tác động an ninh.
4. **Idempotency** và đọc lại trạng thái đích trước khi retry sau timeout.
5. **Revoke priority** cho Leaver hoặc sự cố theo policy.
6. **Reconciliation** theo từng ứng dụng, không chỉ trạng thái tổng.
7. **Exception có owner/hạn xử lý** khi chưa xác minh thu hồi quyền.

### 20.2. Cần phân biệt bốn trạng thái

| Trạng thái | Ý nghĩa |
| --- | --- |
| **DESIRED/EXPECTED** | IAM tính quyền người dùng *nên có*. |
| **SENT/ACKNOWLEDGED** | Connector đã gửi và có/không có phản hồi. |
| **PROVISIONED** | Tài khoản/nhóm/role đã được cập nhật ở đích. |
| **ACCESS_VERIFIED** | Quyền thực tế tại tài nguyên/API phù hợp policy. |

Với quyền nhạy cảm, chỉ báo cáo **thu hồi hoàn tất** khi có bằng chứng cuối ở phạm vi kiểm soát, hoặc ghi rõ hệ thống chưa xác minh và biện pháp giảm thiểu.

## 21. Kiến trúc thực thi và đối soát Least privilege

~~~mermaid
flowchart TD
    HR["HRIS / Contract<br/>Joiner-Mover-Leaver"] --> IGA["IGA<br/>Eligibility + Approval + SoD"]
    CATALOG["Role / Permission catalog<br/>Owner + Scope + TTL"] --> IGA
    IGA --> DESIRED["Expected entitlements"]
    DESIRED --> PROV["Connector / SCIM / Directory"]
    PROV --> APP["Application IAM / local roles"]
    IDP["IdP / MFA / SSO"] --> APP
    APP --> PEP["PEP: API / Resource authorization"]
    DESIRED --> RECON["Reconciliation engine"]
    APP --> RECON
    PEP --> RECON
    RECON -->|"Drift, excess, orphan, stale"| EX["Exception + owner + mitigation"]
    EX --> IGA
    RECON --> AUD["Audit / Access review"]
~~~

Một số ứng dụng không có SCIM hoặc có API role riêng; khi đó connector phải dùng cơ chế được phép của nhà cung cấp. **Không giả định một permission có tên giống nhau ở các ứng dụng mang cùng tác động**.

### 21.1. Phép đối soát khái niệm

~~~text
reconcileLeastPrivilege(subject, target):
    currentIdentity = loadTrustedCurrentIdentityAndEngagement(subject)
    expected = calculateApprovedScopedTimeBoundEntitlements(currentIdentity)

    actual = readEffectiveTargetAssignmentsAndPermissions(target, subject)
    if actual is unknown:
        openExceptionAndApplyRiskBasedMitigation()
        return

    excess  = actual - expected
    missing = expected - actual

    for permission in excess:
        scheduleAuthorizedRevocation(permission)

    for permission in missing:
        if stillEligibleAndApproved(permission, currentIdentity):
            scheduleAuthorizedGrant(permission)

    verifyTargetStateAndSessionRisk()
    recordAuditWithOwnerAndPolicyVersion()
~~~

**Giả mã** chỉ diễn tả nguyên lý; quyền thực tế có thể là **tập cấu trúc** gồm tenant, resource, thời hạn, role hierarchy, nhiều nguồn assignment và quyết định ABAC. Phép trừ tập hợp đơn giản có thể không phù hợp với quyền kế thừa hoặc resource condition. Triển khai thật cần hệ thống tính entitlement hiệu lực đáng tin cậy.

### 21.2. Ưu tiên thu hồi quyền thừa

Nếu đối soát phát hiện một quyền **vượt nhu cầu**, rủi ro thường khác với việc thiếu một quyền cần thiết. Với quyền admin hoặc tài nguyên nhạy cảm, cần ưu tiên cô lập/thu hồi có kiểm soát và xác minh; với quyền thông thường vẫn phải cân nhắc ảnh hưởng dịch vụ và hệ thống phụ thuộc.

Không xóa mù toàn bộ tài khoản máy đang chạy production chỉ vì owner thay đổi. Cần giải pháp giảm rủi ro đồng thời bảo đảm dịch vụ hợp lệ, với owner và lịch xử lý rõ.

## 22. Bảo vệ dữ liệu quyền, log và bằng chứng kiểm toán

Để giải trình một quyết định, IAM cần biết:

- **Ai** được cấp hoặc thu hồi quyền?
- **Từ nguồn nào** yêu cầu phát sinh?
- **Role/permission nào**, thuộc resource scope nào?
- **Ai phê duyệt**, theo policy/SoD nào?
- **Từ khi nào tới khi nào** có hiệu lực?
- **Connector đã làm gì**, nhận mã lỗi nào?
- **Ứng dụng thực tế cho phép/từ chối** thao tác nào?
- **Ngoại lệ và quyền tồn dư** đã được xử lý ra sao?

### 22.1. Bộ trường audit gợi ý

| Trường | Mục đích |
| --- | --- |
| `eventId`, `traceId`, `assignmentId` | Liên kết vòng đời và quá trình cấp/thu hồi. |
| `subjectId`, `engagementId`, `accountId` | Tránh nhầm người và tài khoản. |
| `roleId`, `permissionId`, `scope` | Biết quyền thực tế được quản lý. |
| `assignmentSource`, `approvalRef` | Chứng minh căn cứ cấp quyền. |
| `policyId`, `policyVersion`, `sodCheck` | Xác định luật đã dùng. |
| `effectiveAt`, `expiresAt`, `verifiedAt` | Truy vết hiệu lực, thời hạn và kiểm chứng. |
| `targetSystem`, `targetAccountId` | Xác định đúng đích. |
| `requestedAction`, `providerResult` | Ghi grant/revoke/failed/unknown. |
| `effectiveAccessResult` | Biết quyền tại tài nguyên đã được kiểm chứng thế nào. |
| `exceptionId`, `ownerTeam`, `dueAt` | Quản lý sai lệch còn mở. |

Ví dụ:

~~~json
{
  "eventType": "ENTITLEMENT_REVOKED_VERIFIED",
  "traceId": "mover-person-1042-20261201",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "roleId": "sales-editor",
  "scope": "tenant-a/sales",
  "assignmentSource": "BUSINESS_ROLE_POLICY",
  "policyVersion": "rbac-access-v7",
  "targetSystem": "customer-saas",
  "targetAccountId": "user-8802",
  "requestedAction": "REVOKE",
  "providerResult": "SUCCESS",
  "effectiveAccessResult": "DENIED_VERIFIED",
  "verifiedAt": "2026-12-01T01:10:00Z"
}
~~~

Log minh họa **không phải schema chuẩn bắt buộc**. Không ghi mật khẩu, OTP, access/refresh token, cookie, client secret, private key hoặc thông tin nhân sự quá mức cần thiết vào audit. Cần quyền đọc hạn chế, mã hóa, bảo vệ tính toàn vẹn và thời hạn lưu phù hợp.

### 22.2. Tách quyền và hoạt động sử dụng

Một access log cho thấy người dùng **đã truy cập** tài nguyên, còn entitlement inventory cho thấy họ **có thể truy cập** những gì. Đội IAM phải dùng **cả hai** khi đánh giá quyền thừa: không có log sử dụng không chứng minh một permission không tồn tại, và permission tồn tại không chứng minh đã có hành vi lạm dụng.

## 23. Case study: chuyển bộ phận, quyền cũ còn ở một ứng dụng

**Bối cảnh:** Mai là nhân viên Sales, được gán `customer-exporter` để xuất dữ liệu khách hàng theo scope được phê duyệt. Ngày 01/12, Mai chuyển sang Finance và chỉ cần `finance-report-reader`. HRIS cập nhật đúng; IdP group đã đổi nhưng một SaaS vẫn giữ role trực tiếp cũ.

| Thời điểm giả định | Sự kiện | Trạng thái cần quan sát |
| --- | --- | --- |
| **30/11 16:00** | HRIS thông báo Mover hiệu lực 01/12 08:00. | Person/Engagement và source version đúng. |
| **01/12 08:00** | IAM tính expected roles mới. | Finance Reader cần phê duyệt; Customer Exporter phải thu hồi. |
| **01/12 08:01** | Directory/IdP bỏ nhóm Sales. | Group IdP mới đúng, chưa chứng minh SaaS hết quyền. |
| **01/12 08:03** | SCIM thêm nhóm Finance thành công. | Sai lệch có thể vẫn tồn tại ở role trực tiếp. |
| **01/12 08:05** | Reconciliation thấy SaaS vẫn có direct role `customer-exporter`. | Quyền vượt nhu cầu; tạo cảnh báo. |
| **01/12 08:06** | Security/owner đánh giá khả năng phiên cũ đang dùng quyền. | Hạn chế xuất dữ liệu, xử lý session theo policy. |
| **01/12 08:10** | IAM/app owner thu hồi direct role. | Phải đọc lại local entitlements. |
| **01/12 08:12** | Kiểm tra được ủy quyền xác nhận Mai không còn xuất Sales. | Có bằng chứng DENIED ở API, quyền Finance hoạt động đúng. |

### 23.1. Phân tích

1. Chỉ xem **SSO và group claim** sẽ bỏ sót role cục bộ được cấp trực tiếp.
2. Quy trình Mover phải xử lý cả **grant mới** và **revoke cũ**, không ưu tiên một chiều.
3. Role `customer-exporter` đặc biệt nhạy cảm vì khả năng xuất dữ liệu hàng loạt; cần scope, lịch sử cấp và thời hạn rõ.
4. Việc ứng dụng chấp nhận login không chứng minh quyền đúng.
5. Chỉ đánh dấu hoàn tất khi **tài nguyên đích thực thi quyền mong đợi**, hoặc có ngoại lệ được quản trị và giảm thiểu.

### 23.2. Nếu Mai nghỉ việc ngày kế tiếp?

Với Leaver, hệ thống phải hủy khả năng truy cập Finance mới và mọi quyền Sales còn sót, xử lý local accounts, API key, token/phiên và các quyền ủy quyền liên quan. Retry của Mover hôm trước **không được tái cấp quyền** sau khi Leaver có hiệu lực.

## 24. Những sai lầm thường gặp khi áp dụng Least privilege

| Sai lầm | Vì sao gây rủi ro | Cách cải thiện |
| --- | --- | --- |
| **Mọi người dùng có quyền admin để giảm ticket** | Tăng thiệt hại khi bị chiếm tài khoản hoặc thao tác nhầm. | Role theo nhiệm vụ, cơ chế request/JIT. |
| **Role tên read-only nhưng scope toàn tổ chức** | Lộ dữ liệu vượt phạm vi công việc. | Scope theo tenant/dự án/đơn vị. |
| **Birthright cấp nhiều ứng dụng nhạy cảm** | Quyền được cấp trước khi có nhu cầu thực tế. | Giảm baseline, owner và review. |
| **Chỉ thêm role khi Mover** | Privilege creep. | Tính expected và revoke delta. |
| **Chỉ disable IdP khi Leaver** | App local password, session/PAT còn hoạt động. | Deprovision đa đích và xác minh API. |
| **Tin role trong token vô thời hạn** | Claim stale sau thu hồi. | TTL, invalidation và policy hiện hành phù hợp. |
| **Không kiểm role hierarchy/nested group** | Quyền kế thừa lớn hơn role trực tiếp. | Tính effective access. |
| **Cho ứng dụng dùng database superuser** | Ứng dụng bị chiếm có thể sửa/xóa toàn bộ DB. | Quyền riêng theo job/schema/view. |
| **Service account không owner** | Secret và entitlement máy tồn dư. | Inventory, owner, rotation và decommission. |
| **Token API có scope wildcard** | Mọi endpoint chấp nhận cùng credential. | Phân tách scope theo API/action/resource. |
| **Không có expiry cho quyền dự án** | Quyền tạm trở thành quyền vĩnh viễn. | TTL/recertification và revoke tự động. |
| **Chỉ xem SCIM HTTP success** | Quyền local/session có thể chưa đổi. | Readback và kiểm hiệu lực tại API. |
| **Grant dựa vào email trùng** | Rehire/tái cấp email dẫn tới cấp nhầm người. | Stable subject/engagement mapping. |
| **Tắt authorization để sửa 403** | Vượt qua kiểm soát đang hoạt động đúng. | Điều tra nguồn role, policy và provisioning. |

## 25. Chỉ số đánh giá Least privilege

| Chỉ số | Cách đo gợi ý | Câu hỏi quản trị |
| --- | --- | --- |
| **Tỷ lệ quyền có owner và scope rõ** | Role/permission được quản trị đầy đủ ÷ tổng trong phạm vi. | Ai chịu trách nhiệm và quyền bao phủ gì? |
| **Tỷ lệ assignment có căn cứ hợp lệ** | Role đang hoạt động có source/approval/eligibility hợp lệ ÷ tổng assignment cần kiểm. | Có quyền ngoài quy trình không? |
| **Quyền thừa được xác minh** | Số entitlement vượt expected theo reconciliation. | Mức độ privilege creep? |
| **Tỷ lệ quyền đặc biệt đang thường trực** | Privileged assignments không có giới hạn thời gian/điều kiện ÷ tổng role đặc biệt. | Có thể chuyển sang JIT không? |
| **Độ trễ cấp quyền Joiner** | Từ activationAt tới khi quyền hợp lệ được xác minh. | Nhân viên mới có đủ quyền đúng hạn không? |
| **Độ trễ thu hồi Mover** | Từ effectiveAt tới khi role cũ không còn hiệu lực. | Quyền bộ phận cũ sống bao lâu? |
| **Độ trễ thu hồi Leaver** | Từ mốc kết thúc tới khi truy cập trong phạm vi đã được xác minh chặn. | Cửa sổ truy cập tồn dư bao lâu? |
| **Tỷ lệ quyền tạm hết hạn đúng hạn** | Assignment tới expiresAt được thu hồi và xác minh ÷ tổng đến hạn. | Quyền tạm có thành vĩnh viễn? |
| **Số vi phạm SoD chưa xử lý** | Các tổ hợp quyền xung đột hiện có. | Có đường gian lận hoặc tự phê duyệt? |
| **Tỷ lệ access review hoàn tất** | Quyền đến kỳ review có quyết định và thực thi ÷ tổng phải review. | Recertification có thực chất? |
| **Tỷ lệ service principal có owner** | Workload identities có owner/scope/review hợp lệ ÷ tổng workload. | Có tài khoản máy mồ côi không? |
| **Tỷ lệ entitlement đã đối soát** | Hệ thống/assignment có expected-vs-actual verification ÷ tổng phải quản lý. | Có đo quyền thực tế không? |
| **Ngoại lệ thu hồi quá hạn** | Revoke chưa verified có owner/hạn xử lý vượt SLA. | Có quyền tồn dư chưa được xử lý không? |

Mỗi số liệu phải nêu **phạm vi ứng dụng, tenant, loại tài khoản, mẫu số, chu kỳ và khả năng quan sát**. Không báo “100% quyền đã thu hồi” nếu vẫn có ứng dụng không được inventory hoặc không có cách xác minh session/PAT.

## 26. Checklist tự đánh giá

1. Đã định nghĩa **quyền tối thiểu** theo chủ thể, hành động, tài nguyên, scope, thời gian và điều kiện chưa?
2. Có phân biệt **authentication/SSO** với **authorization/effective access** không?
3. Mỗi role có **owner, permission set, scope, version, eligibility và review cycle** chưa?
4. Birthright roles có thật sự chỉ chứa quyền cần thiết cho nhóm người đủ điều kiện không?
5. Có phân biệt **business role, technical role, direct role và group-based assignment** không?
6. Có tính role hierarchy, nested groups, local grants và delegated access khi xác định quyền hiệu lực không?
7. Có dùng **RBAC kết hợp ABAC** để giới hạn tenant, dữ liệu, action và ngữ cảnh thay vì gán role toàn cục không?
8. Đã kiểm **SoD** và quyền cấp tiếp quyền/credential trước khi duyệt role nhạy cảm chưa?
9. Quyền quản trị có cơ chế **JIT/PAM, step-up MFA, time-bound scope và kiểm sử dụng** khi phù hợp không?
10. Quyền dự án/ngoại lệ có **effectiveAt, expiresAt, gia hạn có phê duyệt và auto-revoke** không?
11. **Joiner** có xác minh người và Start date trước khi bật quyền, tách preboarding khỏi production không?
12. **Mover** có tính cả **quyền cần cấp mới và quyền phải thu hồi**, không chỉ thay nhóm IdP không?
13. **Leaver** có khóa IdP, thu hồi quyền local, group, role, phiên/token/PAT và API key theo phạm vi không?
14. Rehire có được đánh giá theo **engagement mới**, không tự khôi phục entitlement cũ không?
15. Service/workload accounts có **principal riêng, owner, credential vòng đời và quyền API tối thiểu** không?
16. Cloud, Kubernetes, database, storage và API có giới hạn quyền theo action/resource/namespace và môi trường không?
17. Có phân biệt **SCIM User/Group success** với **app role và session đã thực sự mất quyền** không?
18. Có kiểm **source event version, effectiveAt, idempotency và retry cũ sau Leaver** để ngăn tái cấp quyền không?
19. Có inventory toàn bộ tài khoản phụ, role ngoài catalog, local passwords và trực tiếp gán quyền không?
20. Access review có hiển thị **effective permissions, scope, owner, nguồn cấp, expiry và SoD** không?
21. Audit có truy từ **HRIS event/approval → policy → assignment → connector → kết quả đích** mà không lưu credential không?
22. Có đo **privilege creep, JML revoke latency, permanent admins, access-review coverage và residual access** không?
23. Quy trình hỗ trợ có tránh **cấp admin hoặc tắt policy chỉ để xử lý ticket 403** không?
24. Các ngoại lệ chưa thu hồi/xác minh có **owner, thời hạn, biện pháp giảm thiểu và bằng chứng đóng** không?

**Ghi nhớ:** **Quyền tối thiểu là cấp đủ quyền cho nhiệm vụ hợp lệ nhưng không hơn, không rộng hơn và không lâu hơn cần thiết**. Muốn thực hiện được, IAM phải thiết kế **role/permission/scope rõ ràng**, áp dụng **RBAC/ABAC và SoD**, dùng **JIT/PAM** cho quyền đặc biệt, đồng bộ thay đổi qua **IdP, directory, SCIM và ứng dụng**, rồi **đọc lại quyền thực tế**. Trong vòng đời **Joiner–Mover–Leaver**, trọng tâm không chỉ là cấp quyền mới mà còn **thu hồi quyền không còn lý do tồn tại**, xử lý phiên/token/tài khoản máy và lưu bằng chứng kiểm toán để giảm truy cập tồn dư một cách có thể đo lường và giải trình.
