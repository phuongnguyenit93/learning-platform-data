# Employment status – trạng thái việc làm trong nguồn dữ liệu nhân sự và IAM lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **employment status** là gì, nguồn nào chịu trách nhiệm duy trì và tại sao trạng thái việc làm là tín hiệu quan trọng trong quản lý vòng đời danh tính.
- Phân biệt trạng thái việc làm từ HRIS với trạng thái danh tính, trạng thái tài khoản tại IdP, khả năng đăng nhập và quyền thực tế tại ứng dụng.
- Phân tích cách các trạng thái như **chờ nhận việc, đang làm việc, tạm nghỉ, bị tạm đình chỉ, đã nghỉ việc** ảnh hưởng đến quy trình **Joiner–Mover–Leaver (JML)**.
- Thiết kế ánh xạ từ dữ liệu nhân sự đến hành động IAM có xét **thời điểm hiệu lực, loại hợp đồng, chính sách và mức rủi ro**, thay vì quy đổi máy móc từ một nhãn trạng thái.
- Giải thích các biện pháp kiểm soát sai lệch dữ liệu, sự kiện trễ, quay lại làm việc, tài khoản mồ côi, phiên còn hiệu lực và kiểm toán thay đổi.

## 1. Employment status là gì?

**Employment status (trạng thái việc làm)** mô tả **tình trạng quan hệ làm việc giữa một cá nhân và tổ chức tại một thời điểm hoặc trong một khoảng thời gian**, theo hồ sơ có thẩm quyền của bộ phận nhân sự hoặc hệ thống quản lý lực lượng lao động.

Trong một hệ thống HRIS (Human Resources Information System), trường này có thể dùng để thể hiện một người **sắp nhận việc**, **đang làm**, **đang nghỉ phép/tạm nghỉ**, **đang bị tạm đình chỉ**, **đã kết thúc quan hệ làm việc** hoặc các trạng thái khác do tổ chức quy định. Có tổ chức dùng một trường đơn; nơi khác dùng kết hợp trạng thái, hành động nhân sự, ngày bắt đầu/kết thúc, loại lao động và lý do thay đổi.

Trong **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, employment status là **tín hiệu nghiệp vụ đầu vào** cho hoạt động xác minh, tạo danh tính, cấp quyền, thay đổi quyền, rà soát và thu hồi quyền truy cập theo Joiner–Mover–Leaver. Việc sử dụng đúng trạng thái giúp giảm quyền tồn dư của người đã chuyển vai trò hoặc rời tổ chức.

Tuy nhiên, **employment status không trực tiếp trả lời người đó được đăng nhập hay không**. Câu trả lời còn phụ thuộc chính sách, lịch sử phê duyệt, loại danh tính, thời điểm có hiệu lực và kết quả thực thi ở từng hệ thống.

Ví dụ: HRIS ghi một nhân viên đã nghỉ lúc 18:00. Đến 18:05, IdP đã khóa tài khoản nhưng một ứng dụng SaaS chưa nhận sự kiện SCIM và còn phiên truy cập. Khi đó:

- **Trạng thái việc làm:** đã kết thúc.
- **Trạng thái danh tính trong IAM:** đã bắt đầu hoặc hoàn tất quy trình Leaver, tùy mô hình.
- **Trạng thái tài khoản tại IdP:** bị vô hiệu hóa.
- **Trạng thái truy cập thực tế tại SaaS:** có thể vẫn còn hiệu lực.

Sự khác biệt này là lý do hệ thống cần lưu và đối soát nhiều lớp trạng thái.

## 2. Phân biệt employment status với các trường liên quan

| Trường/khái niệm | Mô tả | Nguồn thông tin thường gặp | Ví dụ |
| --- | --- | --- | --- |
| **Employment status** | Tình trạng quan hệ việc làm theo thời gian | HRIS, hệ thống quản lý nhà thầu | ACTIVE, ON_LEAVE, TERMINATED |
| **Worker type** | Loại quan hệ với tổ chức | HRIS/hợp đồng | EMPLOYEE, CONTRACTOR, INTERN |
| **Employment action/event** | Sự kiện nhân sự làm thay đổi hồ sơ | HRIS | HIRE, TRANSFER, LEAVE_START, TERMINATION |
| **Job/position status** | Trạng thái vị trí, chức vụ, đơn vị | HRIS, hệ thống tổ chức | Finance Analyst, Operations |
| **Identity lifecycle status** | Trạng thái danh tính số do IAM quản lý | Identity registry/IGA | PENDING, ACTIVE, DEACTIVATING |
| **Account status** | Tình trạng tài khoản tại một hệ thống | IdP, ứng dụng SaaS, directory | Enabled, disabled, locked |
| **Authorization/entitlement** | Quyền cụ thể đang được cấp | RBAC/ABAC, ứng dụng, cloud IAM | CanReadInvoice, VPNAccess |
| **Session/credential status** | Phiên hoặc phương tiện xác thực còn giá trị không | IdP, ứng dụng, quản lý secret | Valid, expired, revoked |

**Không nên đồng nhất các trường trên thành một cờ active duy nhất.** Ví dụ:

- Nhân viên **ACTIVE** vẫn có thể bị khóa tài khoản vì sự cố bảo mật.
- Nhân viên **ON_LEAVE** có thể cần quyền hạn chế, không nhất thiết bị vô hiệu hóa hoàn toàn.
- Nhân viên **TERMINATED** có thể còn bản ghi danh tính lưu trữ để kiểm toán, nhưng không còn quyền đăng nhập.
- Tài khoản **SCIM active = false** cho biết trạng thái của tài khoản SCIM trong ứng dụng đích, không phải định nghĩa độc lập về employment status của người lao động.
- Nhân viên **ACTIVE** không mặc nhiên cần quyền quản trị hoặc quyền ở mọi ứng dụng.

## 3. Nguồn có thẩm quyền: HRIS và phạm vi trách nhiệm

### 3.1. Vì sao HRIS thường là nguồn đáng tin cho employment status?

HRIS thường có quy trình ghi nhận tuyển dụng, thay đổi nhân sự, nghỉ phép và chấm dứt quan hệ việc làm, kèm người tạo/phê duyệt và thời điểm hiệu lực. Vì vậy, tổ chức thường chọn HRIS làm **authoritative source** cho trạng thái việc làm của nhân viên.

Tuy nhiên, tính có thẩm quyền chỉ áp dụng **trong phạm vi thông tin được tổ chức chỉ định**:

- HRIS có thể là nguồn gốc **employment status**, ngày bắt đầu, ngày nghỉ, đơn vị công tác và người quản lý đối với **nhân viên**.
- Hệ thống hợp đồng hoặc vendor management có thể là nguồn đáng tin hơn cho **nhà thầu, cộng tác viên và đối tác**.
- Hệ thống service registry hoặc nền tảng hạ tầng mới là nguồn về **workload/service account**, vì tài khoản dịch vụ không có quan hệ tuyển dụng như con người.
- IdP giữ thông tin **tài khoản, xác thực và chính sách đăng nhập**, nhưng không nhất thiết có quyền quyết định người đó còn làm việc hay không.

Cần quy định rõ ai **được cập nhật trạng thái**, ai **phê duyệt**, tình huống nào hệ thống khác được **tạm thời áp dụng biện pháp chặn khẩn cấp**, và cách đồng bộ trở lại khi nguồn nhân sự thay đổi.

### 3.2. Chất lượng trường status không thể đánh giá độc lập

Một giá trị employment status chỉ hữu ích khi đi cùng ngữ cảnh. Ví dụ:

~~~yaml
identityId: "person-48210"
sourceSystem: "HRIS"
sourcePersonId: "hr-91422"
workerType: "EMPLOYEE"
employmentStatus: "ACTIVE"
statusEffectiveAt: "2026-11-23T08:00:00+07:00"
employmentStartAt: "2026-11-23T08:00:00+07:00"
employmentEndAt: null
organizationUnit: "Finance"
managerIdentityId: "person-00712"
sourceRecordVersion: 18
sourceUpdatedAt: "2026-11-22T17:45:00+07:00"
~~~

Đây là **mẫu dữ liệu minh họa**, không phải schema chuẩn của HRIS/SCIM. Tùy tổ chức có thể cần thêm loại hợp đồng, lịch sử thời gian hiệu lực, mã vị trí, người bảo lãnh, mức bảo đảm danh tính hoặc nguồn xác minh.

Các trường thường quan trọng gồm:

| Trường | Vai trò | Nguy cơ nếu thiếu hoặc sai |
| --- | --- | --- |
| **sourcePersonId** | Đối chiếu chủ thể với hồ sơ HRIS | Tạo danh tính trùng hoặc thu hồi nhầm |
| **identityId** | Liên kết danh tính nội bộ với nhiều tài khoản | Khó tìm mọi account liên quan khi Leaver |
| **employmentStatus** | Biết quan hệ làm việc hiện tại | Kích hoạt/thu hồi truy cập không đúng |
| **statusEffectiveAt** | Thời điểm trạng thái được áp dụng nghiệp vụ | Khóa quá sớm hoặc quá muộn |
| **employmentStartAt / EndAt** | Xác định cửa sổ làm việc | Bỏ sót người sắp nghỉ hoặc hợp đồng hết hạn |
| **workerType** | Áp chính sách theo loại quan hệ | Cấp quyền nhân viên cho nhà thầu |
| **manager/sponsor** | Xác định người chịu trách nhiệm phê duyệt | Ngoại lệ không có chủ sở hữu |
| **sourceRecordVersion** | Phân biệt sự kiện mới/cũ | Sự kiện trễ khôi phục quyền đã thu hồi |
| **sourceUpdatedAt** | Phục vụ đồng bộ, chẩn đoán độ trễ | Không phát hiện dữ liệu cũ |

Không được mặc định email là khóa danh tính: email và tên có thể thay đổi, đôi khi được cấp lại. Nên dùng **định danh nội bộ ổn định, không tái sử dụng cho người khác** và bản đồ liên kết sang ID của HRIS, IdP cùng ứng dụng đích.

## 4. Các trạng thái employment thường gặp

**Không có một tập tên trạng thái thống nhất áp dụng cho mọi HRIS.** Hệ thống có thể dùng mã số, tiếng địa phương hoặc nhiều trường kết hợp. Bảng dưới đây trình bày một **từ vựng chuẩn hóa nội bộ mang tính ví dụ**, cần ánh xạ theo chính sách tổ chức.

| Trạng thái minh họa | Ý nghĩa nghiệp vụ | Hướng xử lý IAM thường cần xét |
| --- | --- | --- |
| **PRE_HIRE / PENDING** | Có hồ sơ tuyển dụng, ngày bắt đầu chưa đến hoặc chưa hoàn tất xác minh | Chuẩn bị danh tính/account theo quyền hạn được phê duyệt; chưa mặc định mở mọi truy cập |
| **ACTIVE** | Quan hệ việc làm đang có hiệu lực | Cho phép đánh giá cấp quyền phù hợp vai trò, mức bảo đảm và chính sách |
| **ON_LEAVE** | Tạm nghỉ hoặc vắng mặt, có thể còn quan hệ việc làm | Áp chính sách theo loại nghỉ, thời hạn và mức nhạy cảm; có thể giữ, hạn chế hoặc chặn một số quyền |
| **SUSPENDED** | Bị tạm đình chỉ theo quy trình nghiệp vụ | Xem xét hạn chế/khóa truy cập kịp thời theo quyết định có thẩm quyền; giữ bằng chứng |
| **TERMINATED / SEPARATED** | Quan hệ làm việc đã chấm dứt | Kích hoạt Leaver, thu hồi quyền, xử lý account/credential/session và xác minh kết quả |
| **INACTIVE / ARCHIVED** | Có thể chỉ là trạng thái hồ sơ lưu trữ | Không dùng để suy đoán quan hệ làm việc nếu hệ thống gốc chưa định nghĩa rõ |

**Rehire (tái tuyển dụng)** thường là **sự kiện**, không nhất thiết là một trạng thái kéo dài. Một người có thể đi từ TERMINATED đến ACTIVE thông qua hồ sơ mới hoặc lịch sử quan hệ làm việc, nhưng việc khôi phục quyền phải theo phê duyệt hiện tại. Tương tự, **TRANSFER** là sự kiện thay đổi công việc và thường không làm employment status rời ACTIVE.

### 4.1. Các tình huống làm thay đổi cách diễn giải

**Tạm nghỉ có hưởng lương hoặc nghỉ theo chế độ:** nhân viên có thể vẫn thuộc doanh nghiệp và có quyền dùng dịch vụ nhân sự, nhưng truy cập hệ thống sản xuất hoặc dữ liệu nhạy cảm có thể cần hạn chế. Phạm vi phụ thuộc chính sách và quy định áp dụng; không nên mặc định mọi ON_LEAVE đều là Leaver.

**Tạm đình chỉ:** nếu trạng thái SUSPENDED được dùng cho quyết định nhân sự có tác động đến truy cập, IAM cần nhận sự kiện ưu tiên và có khả năng chặn nhanh. Tuy nhiên một số hệ thống dùng "suspended" để mô tả **khóa tài khoản kỹ thuật** chứ không phải trạng thái việc làm; phải xác nhận nghĩa của nguồn.

**Hết hạn hợp đồng nhà thầu:** hồ sơ có thể không nằm trong HRIS nhân viên. Nếu chỉ quét bảng nhân sự, IAM có thể bỏ sót hoàn toàn đối tượng này. Cần định nghĩa nguồn riêng và ngày hết hạn có hiệu lực.

**Nhân viên chuyển vai trò:** employment status vẫn ACTIVE nhưng bộ phận, địa điểm, người quản lý, dự án hoặc chức vụ thay đổi; đây vẫn là một sự kiện **Mover** cần tính lại quyền.

**Nghỉ việc có thông báo trước:** HRIS có thể biết ngày nghỉ trong tương lai từ nhiều ngày trước. Hệ thống cần lên lịch thu hồi tại thời điểm chính sách yêu cầu, đồng thời cho phép xử lý khẩn cấp khi có chỉ thị có thẩm quyền.

## 5. Từ employment status đến Joiner–Mover–Leaver

~~~mermaid
flowchart LR
  A["HRIS / Nguồn hợp đồng"] -->|"Trạng thái + thời điểm hiệu lực"| B["Bộ chuẩn hóa sự kiện nhân sự"]
  B -->|"HIRE / UPDATE / LEAVE / TERMINATE"| C["Điều phối JML / IGA"]
  C -->|"Quy tắc, approval, least privilege"| D["Identity registry / IdP"]
  D -->|"SSO / authentication"| E["Ứng dụng"]
  C -->|"SCIM / API provisioning"| E
  C -->|"Role / entitlement"| F["Cloud / VPN / hệ thống khác"]
  E -->|"Observed account & session state"| G["Reconciliation"]
  F -->|"Observed access state"| G
  G -->|"Sai lệch / exception"| C
  C --> H["Audit trail / SIEM"]
  D --> H
  E --> H
~~~

Có thể diễn giải quy trình thành ba loại sự kiện:

### 5.1. Joiner: trạng thái chuyển sang có hiệu lực làm việc

Với người mới gia nhập, employment status và các trường bắt đầu là cơ sở để quyết định **khi nào kích hoạt danh tính** và **có đủ điều kiện cấp quyền hay chưa**.

Các câu hỏi bắt buộc:

1. Hồ sơ nguồn có đáng tin, đã xác minh danh tính và xác định trùng hồ sơ chưa?
2. Ngày có hiệu lực là lúc nào? Việc chuẩn bị tài khoản trước ngày bắt đầu có được phép không?
3. Người đó là nhân viên, nhà thầu hay đối tác? Ai phê duyệt quyền?
4. Vai trò/thuộc tính nào được dùng làm mặc định? Quyền nhạy cảm có cần phê duyệt riêng không?
5. Ứng dụng đích đã tạo tài khoản và cấp quyền thật hay chỉ xác nhận đã nhận lệnh?

Ví dụ, HRIS chuyển một nhân viên từ PRE_HIRE sang ACTIVE lúc 08:00 ngày bắt đầu. IAM có thể kích hoạt IdP, thiết lập MFA, cấp quyền cơ bản theo RBAC và đồng bộ SCIM đến các ứng dụng. Nếu tài khoản đã được chuẩn bị trước đó thì cần **kích hoạt có kiểm soát** thay vì tạo tài khoản trùng.

### 5.2. Mover: trạng thái không đổi vẫn có thể cần thu hồi quyền

Một sai lầm thường gặp là chỉ lắng nghe thay đổi trường employmentStatus. Khi nhân viên đổi từ Support sang Finance, **employmentStatus vẫn ACTIVE**, nhưng **department/job/manager** đã đổi. Nếu bộ điều phối chỉ nhận sự kiện active → inactive, nó sẽ bỏ qua Mover.

Cách xử lý:

- Đọc sự kiện thay đổi thuộc tính có ảnh hưởng đến authorization.
- Tính lại **desired entitlements** từ vai trò hiện tại, thuộc tính ABAC, điều kiện rủi ro và các phê duyệt.
- So sánh với **observed entitlements** ở IdP, ứng dụng và hạ tầng.
- Gỡ quyền không còn cần thiết, cấp quyền mới theo chính sách và kiểm tra phân tách nhiệm vụ (Segregation of Duties – SoD).
- Xác minh các quyền cấp trực tiếp tại ứng dụng và phiên/token có thể giữ claim cũ.

**Employment status ACTIVE không đồng nghĩa bộ quyền trước đây còn hợp lệ.** Việc gỡ quyền cũ là một phần bắt buộc của Mover.

### 5.3. Leaver: trạng thái kết thúc quan hệ làm việc

Khi quan hệ làm việc kết thúc hoặc hợp đồng hết hạn, sự kiện cần kích hoạt quy trình offboarding theo mức rủi ro. Thao tác thường bao gồm:

1. Xác định thời điểm chấm dứt hiệu lực và mức ưu tiên.
2. Khóa đường đăng nhập mới ở IdP khi chính sách yêu cầu.
3. Gửi yêu cầu deprovision đến hệ thống đích qua SCIM/API hoặc quy trình thủ công.
4. Thu hồi nhóm, role, quyền cục bộ, quyền cloud, VPN, tài khoản quản trị và ngoại lệ tạm thời.
5. Xử lý session, refresh token, khóa SSH, chứng chỉ hoặc API key thuộc phạm vi người đó.
6. Đối soát trạng thái thực tế; cảnh báo và xử lý hệ thống chưa xác nhận hoàn tất.
7. Giữ bằng chứng phê duyệt, thời điểm và kết quả thu hồi cho kiểm toán.

**Khóa IdP không đảm bảo mọi ứng dụng tự hủy phiên đang tồn tại.** Tương tự, SCIM không mặc nhiên quản lý mọi entitlement và token đặc thù. Vì vậy, employmentStatus = TERMINATED chỉ là **sự kiện kích hoạt**, không phải bằng chứng quyền truy cập đã bị thu hồi ở mọi nơi.

## 6. Chuẩn hóa status và chính sách ánh xạ

### 6.1. Chuẩn hóa nghĩa trước khi viết quy tắc

Hai HRIS có thể cùng dùng "INACTIVE" nhưng ý nghĩa khác nhau; một bên chỉ trạng thái nghỉ việc, bên kia chỉ bản ghi tạm ẩn. Hệ thống IAM cần một **lớp ánh xạ rõ ràng theo từng nguồn và phiên bản schema**.

Ví dụ bảng ánh xạ nội bộ:

| Raw HR value (minh họa) | Employment status chuẩn hóa | Sự kiện IAM dự kiến | Điều kiện bổ sung |
| --- | --- | --- | --- |
| Hired – future | PRE_HIRE | PREPARE_JOINER | Xác nhận nguồn, ngày bắt đầu, điều kiện cấp trước |
| Employed | ACTIVE | ACTIVATE / REVIEW | Đã đến ngày hiệu lực, kiểm tra hồ sơ |
| Leave of absence | ON_LEAVE | ACCESS_REVIEW / RESTRICT | Loại nghỉ, thời hạn, chính sách |
| Suspension | SUSPENDED | RESTRICT / SUSPEND | Phê duyệt, mức rủi ro, tính khẩn cấp |
| Separation effective | TERMINATED | START_LEAVER | Thời điểm hiệu lực, danh mục hệ thống |
| Internal transfer | ACTIVE (không đổi) | PROCESS_MOVER | Department, role, manager hoặc location thay đổi |

Đây **không phải định nghĩa tiêu chuẩn** của các từ khóa trong mọi HRIS. Đội quản trị dữ liệu nhân sự và IAM phải thống nhất nghĩa trước khi triển khai, kèm cách xử lý **unknown/missing values**.

### 6.2. Không chuyển trực tiếp status thành bật/tắt tài khoản

Một quy tắc máy móc như "ACTIVE thì enable, ngược lại disable" có thể:

- Vô hiệu hóa nhầm người đang nghỉ hợp lệ.
- Khôi phục tài khoản bị khóa do bảo mật chỉ vì HRIS vẫn ghi ACTIVE.
- Bỏ qua Mover vì trạng thái ACTIVE không thay đổi.
- Mở lại quyền cũ khi rehire mà không đánh giá mới.
- Để nhà thầu vẫn truy cập khi nguồn hợp đồng không có bản ghi HRIS.

Nên tách ít nhất **ba tầng quyết định**:

1. **Định nghĩa nghiệp vụ:** employment status, loại lao động và ngày hiệu lực nói điều gì?
2. **Quyết định IAM:** với loại danh tính và chính sách hiện hành, cần tạo/khóa account, rà soát hay điều chỉnh quyền nào?
3. **Thực thi và xác minh:** IdP, ứng dụng và hạ tầng thực tế có thực hiện đúng quyết định không?

Ví dụ mã giả minh họa:

~~~text
function evaluateEmploymentChange(oldRecord, newRecord, policy, now):
    assert sourceIsAuthorized(newRecord.source)
    assert identityLinkIsVerified(newRecord.personId)

    if eventIsStale(newRecord.version):
        return IGNORE_WITH_AUDIT

    if requiresImmediateSecurityBlock(newRecord, policy):
        return APPLY_EMERGENCY_RESTRICTION

    if newRecord.status == TERMINATED
       and newRecord.effectiveAt <= now:
        return START_LEAVER_AND_VERIFY_ALL_TARGETS

    if newRecord.status == PRE_HIRE:
        return PREPARE_JOINER_WITHOUT_UNAPPROVED_ACCESS

    if newRecord.status == ACTIVE
       and employmentJustBecameEffective(oldRecord, newRecord, now):
        return ACTIVATE_JOINER_WITH_APPROVALS

    if authorizationAttributesChanged(oldRecord, newRecord):
        return PROCESS_MOVER_RECALCULATE_AND_REVOKE

    if newRecord.status in {ON_LEAVE, SUSPENDED}:
        return EVALUATE_RESTRICTIONS_BY_POLICY

    return RECORD_AND_MONITOR
~~~

Các tên hàm và trạng thái trong đoạn mã là **mã giả**, không tương ứng với API HRIS, SCIM hay thư viện cụ thể. Quy tắc thực tế phải xem cả ngày hiệu lực tương lai, quyết định khẩn cấp, thời gian nghỉ, quyền riêng theo dự án và trạng thái thực thi đã xảy ra.

### 6.3. Trường hợp status không xác định

Nếu nhận một raw status mới mà hệ thống chưa biết, không nên âm thầm mặc định là ACTIVE. Cần:

- Ghi nhận raw value, source, mã sự kiện và phiên bản schema.
- Đánh dấu **mapping exception** để người có trách nhiệm xác định.
- Tránh tự cấp thêm quyền khi thiếu căn cứ.
- Áp dụng biện pháp an toàn theo chính sách và mức rủi ro, đặc biệt với quyền nhạy cảm.
- Bảo đảm không chặn oan hoặc ngừng dịch vụ do giá trị dữ liệu thiếu nhất thời; cần luồng xử lý ngoại lệ rõ ràng.

## 7. Thời điểm hiệu lực quan trọng hơn thời điểm hệ thống nhận dữ liệu

Một record có thể mô tả sự kiện sắp xảy ra hoặc đã xảy ra. Các mốc cần tách biệt:

| Mốc thời gian | Ý nghĩa |
| --- | --- |
| **eventOccurredAt** | Khi sự kiện nhân sự được ghi nhận hoặc phát sinh |
| **statusEffectiveAt** | Khi trạng thái mới có hiệu lực theo nghiệp vụ |
| **publishedAt** | Khi nguồn phát hành sự kiện cho hệ thống khác |
| **receivedAt** | Khi bộ điều phối IAM nhận sự kiện |
| **appliedAt** | Khi tài khoản/quyền tại hệ thống đích thực sự đổi |
| **verifiedAt** | Khi hệ thống kiểm tra và xác nhận trạng thái cuối |

Ví dụ, phòng nhân sự nhập ngày nghỉ là **30/11/2026, 18:00** vào ngày **23/11/2026**. Hệ thống IAM nhận thông báo sớm nên có thể lập lịch Leaver. Nếu khóa mọi account ngay ngày 23/11 chỉ vì có bản ghi "separation", sẽ chặn sai quyền của người vẫn đang làm việc. Ngược lại, nếu 30/11 đã qua mà ứng dụng đích chưa vô hiệu hóa, phải cảnh báo và xử lý tồn dư.

**Lưu ý múi giờ:** dùng timestamp có offset hoặc múi giờ xác định, và quy ước rõ ngày kết thúc có nghĩa là **đầu ngày**, **cuối ngày** hay **thời điểm cụ thể**. Một trường ngày không có giờ, nếu hiểu sai, có thể dẫn đến thu hồi chậm nhiều giờ.

### 7.1. Sự kiện đến muộn, lặp hoặc sai thứ tự

Chuỗi ví dụ:

~~~text
Event 101: ACTIVE, department=Support, effectiveAt=2026-11-10
Event 102: ACTIVE, department=Finance, effectiveAt=2026-11-20
Event 103: TERMINATED, effectiveAt=2026-11-23 18:00

Delivery order:
  102 -> 103 -> 101 (trễ)

Expected:
  101 không được khôi phục department cũ hoặc quyền Support
  103 phải được xử lý tại thời điểm hiệu lực theo chính sách
~~~

Để tránh phục hồi quyền sai:

- Dùng **event ID** và **version/sequence** để phát hiện sự kiện trùng hoặc cũ.
- Áp dụng **idempotency**: xử lý lại cùng sự kiện không tạo account trùng hoặc tăng quyền.
- Quản lý trạng thái theo thời gian hiệu lực và lịch sử thay đổi, không đơn giản lấy sự kiện đến sau cùng làm mới nhất.
- Retry lỗi tạm thời, có hàng đợi lỗi và người chịu trách nhiệm xử lý.
- Định kỳ **reconciliation** giữa HRIS/nguồn nhân sự, IAM và ứng dụng đích.

Không phải mọi nguồn dữ liệu đều cấp số version có tính tăng đơn điệu. Khi đó cần xác định quy tắc nhất quán từ source record, transaction ID và lịch sử phiên bản có thể kiểm tra; chỉ dùng timestamp nhận sự kiện thường không đủ.

## 8. Employment status trong IdP, SSO, SCIM, RBAC và ABAC

### 8.1. IdP và SSO

IdP có thể lưu thuộc tính employment status hoặc nhóm được dẫn xuất từ HRIS, sau đó phát hành thông tin phù hợp trong quá trình xác thực/federation. Tuy nhiên:

- **SSO** giúp ứng dụng tin vào kết quả đăng nhập từ IdP; nó không tự biết toàn bộ thay đổi HRIS.
- Nhóm/claim trong token phản ánh một thời điểm phát hành; khi HRIS chuyển trạng thái, **token đã phát hành có thể chưa đổi**.
- Tài khoản bị vô hiệu hóa tại IdP thường ảnh hưởng đăng nhập mới; phiên còn sống tại ứng dụng đích phải được đánh giá theo cơ chế riêng.
- Không nên coi một claim đơn lẻ như employmentStatus là nguồn đáng tin nếu chưa quản trị nguồn phát hành, thời gian hiệu lực và ngữ cảnh tin cậy.

### 8.2. SCIM

SCIM là cơ chế chuẩn hóa **quản lý tài nguyên người dùng/nhóm** giữa các hệ thống tương thích. Thuộc tính SCIM phổ biến như **active** thể hiện tình trạng account/user resource tại hệ thống đích, không nên hiểu là trường employment status nghiệp vụ của HRIS.

Một mapping ví dụ:

~~~text
HRIS: employmentStatus=TERMINATED
       statusEffectiveAt đã tới
          |
          v
IAM:  quyết định LEAVER được phê duyệt/áp dụng
          |
          v
SCIM: cập nhật User.active=false tại ứng dụng hỗ trợ
          |
          v
Target: kiểm tra tài khoản bị vô hiệu hóa
          |
          v
IAM:  đối soát session/token/role còn tồn tại
~~~

Cần xử lý lỗi SCIM/API, việc ứng dụng chỉ hỗ trợ một phần, khác biệt giữa vô hiệu hóa và xóa, quyền được cấp cục bộ và phiên không bị thu hồi. **SCIM trả thành công không có nghĩa mọi phương thức truy cập đã chấm dứt.**

### 8.3. RBAC/ABAC

**RBAC** dùng vai trò để cấp quyền, ví dụ người thuộc bộ phận Finance và có job role phù hợp được gán nhóm xem hóa đơn. Employment status giúp xác định danh tính còn có cơ sở nghiệp vụ để giữ role hay không.

**ABAC** dùng thuộc tính chủ thể, tài nguyên, hành động và ngữ cảnh, ví dụ:

~~~text
PERMIT invoice.read WHEN
    subject.employmentStatus == ACTIVE
    AND subject.department == resource.ownerDepartment
    AND subject.workerType IN {EMPLOYEE, APPROVED_CONTRACTOR}
    AND subject.authenticationAssurance >= requiredAssurance
    AND subject.entitlement == "INVOICE_READ"
ELSE DENY
~~~

Đây chỉ là **mã giả chính sách**. Trong hệ thống thực tế, policy còn cần xác định nguồn thuộc tính, độ mới, ngoại lệ có phê duyệt, phạm vi dữ liệu và cách xử lý nếu không tra được trạng thái.

Một số lỗi có thể phát sinh:

- Tài khoản vẫn mang role cũ dù HRIS đã chuyển department.
- ABAC dùng thuộc tính đã lưu từ token cũ sau khi người dùng đổi trạng thái.
- Policy coi **ACTIVE** là đủ để có quyền, bỏ qua yêu cầu phê duyệt hoặc điều kiện tài nguyên.
- Luồng rehire bật lại toàn bộ role cũ của giai đoạn làm việc trước.

**Least privilege** và **đối soát entitlement** cần áp dụng ngay cả khi employment status đang hợp lệ.

## 9. Những trường hợp nghiệp vụ khó cần thiết kế rõ

### 9.1. Nhân viên nghỉ dài hạn

Giả sử HRIS có employmentStatus = ON_LEAVE trong 4 tháng. Tổ chức cần trả lời: họ còn được vào hệ thống HR tự phục vụ không? Quyền dự án và VPN có cần tạm chặn? Người nào phê duyệt việc giữ quyền? Khi quay lại làm việc, quyền nào được khôi phục?

Một thiết kế hợp lý thường tách:

- **Những quyền cần duy trì** theo chính sách và nhu cầu chính đáng.
- **Những quyền tạm ngưng** vì rủi ro hoặc không còn nhiệm vụ.
- **Ngày dự kiến quay lại** và quy trình xác minh trước khi tái kích hoạt.
- **Quyền đặc quyền** được đánh giá riêng, không tự động khôi phục khi hết kỳ nghỉ.

### 9.2. Thay đổi trạng thái giữa các pháp nhân hoặc đơn vị

Một người chuyển sang công ty con có thể được HRIS cũ ghi TERMINATED và HRIS mới ghi ACTIVE. Nếu identity matching thiếu quy tắc, IAM có thể xóa nhầm toàn bộ truy cập hoặc tạo hai danh tính không liên kết.

Cần phân biệt **chấm dứt một quan hệ việc làm** với **chấm dứt mọi quan hệ với toàn bộ tổ chức**. Mô hình có thể cho phép một chủ thể có nhiều employment relationships, mỗi quan hệ có trạng thái và thời gian hiệu lực riêng. Quyết định truy cập cần dựa trên quan hệ hiện tại phù hợp với tài nguyên.

### 9.3. Rehire – quay lại làm việc

Nhân viên nghỉ rồi quay lại sau sáu tháng. Dù cùng số hồ sơ hoặc có thể đối chiếu được chủ thể, IAM cần:

1. Xác minh lại identity matching và thông tin bắt buộc.
2. Xác nhận quan hệ làm việc mới và ngày bắt đầu.
3. Xác định nên dùng lại hay tạo mới account theo chính sách vòng đời.
4. Cấp lại **quyền theo vai trò hiện tại**, không tự động bật role/credential cũ.
5. Kiểm tra lịch sử vô hiệu hóa, khóa/token cũ, các phiên đã hết hạn và audit.

Việc **tái sử dụng bản ghi danh tính** không có nghĩa **tái sử dụng mọi quyền**.

### 9.4. Nhà thầu hết hạn hoặc thiếu ngày kết thúc

Nhà thầu có thể được quản lý qua sponsor thay vì HRIS. Nếu trường endDate rỗng, không nên mặc định hợp đồng kéo dài vô hạn. Hệ thống cần chính sách gia hạn, ngày review, owner phê duyệt và cảnh báo trước hạn. Khi đến ngày kết thúc thực tế, chạy Leaver và đối soát tương tự nhân viên, với phạm vi phù hợp.

### 9.5. Sự kiện nghỉ việc khẩn cấp

Một số trường hợp cần chặn ngay theo quyết định của bộ phận có thẩm quyền, bất kể HRIS chưa kịp cập nhật. Cần có luồng **emergency restriction** được ủy quyền, ghi lý do và thời điểm, phát cảnh báo, sau đó đối chiếu với hồ sơ chính thức. Không để đồng bộ HRIS thông thường vô tình mở lại tài khoản đang bị chặn theo quyết định bảo mật.

### 9.6. Service account không có employment status

Tài khoản dịch vụ/workload không phải nhân viên nên **không nên gán employmentStatus=ACTIVE chỉ để tái sử dụng workflow nhân sự**. Thay vào đó, quản lý lifecycle riêng như provisioning, activation, owner transfer, credential rotation và retirement. Khi người chịu trách nhiệm dịch vụ nghỉ việc, cần chuyển owner, rà soát quyền và secret liên quan mà vẫn xử lý các phụ thuộc để tránh gián đoạn sản xuất.

## 10. Thiết kế dữ liệu và luồng xử lý có thể kiểm toán

### 10.1. Event contract tối thiểu

Một event làm đầu vào cho IAM nên mang thông tin về **chủ thể, loại quan hệ, loại thay đổi, trạng thái và thời gian**, ngoài thông tin truy vết:

~~~json
{
  "eventId": "hr-event-10329",
  "sourceSystem": "HRIS",
  "sourceRecordId": "worker-91422",
  "identityId": "person-48210",
  "workerType": "EMPLOYEE",
  "eventType": "EMPLOYMENT_STATUS_CHANGED",
  "previousStatus": "ACTIVE",
  "newStatus": "TERMINATED",
  "statusEffectiveAt": "2026-11-30T18:00:00+07:00",
  "publishedAt": "2026-11-23T09:15:00+07:00",
  "sourceRecordVersion": 19,
  "correlationId": "jml-7a42f"
}
~~~

Đây là **JSON minh họa, không phải hợp đồng sự kiện chuẩn**. Có thể cần cả thay đổi thuộc tính của Mover và nguồn owner nhà thầu.

Không nên nhúng giấy tờ định danh, mật khẩu, token hay dữ liệu cá nhân không cần thiết trong luồng sự kiện. Các hệ thống phải xác thực nguồn, bảo vệ tính toàn vẹn và kiểm soát quyền nhận sự kiện.

### 10.2. Luồng xử lý đề xuất

~~~mermaid
flowchart TD
  A["Nhận sự kiện HRIS / hợp đồng"] --> B{"Nguồn hợp lệ và mapping rõ?"}
  B -->|"Không"| X["Ghi ngoại lệ, cảnh báo, xử lý theo chính sách"]
  B -->|"Có"| C["Xác định identity, version, effectiveAt"]
  C --> D{"Sự kiện còn hiệu lực mới?"}
  D -->|"Không"| Y["Bỏ sự kiện trùng/cũ, lưu audit"]
  D -->|"Có"| E["Tính desired access theo JML + policy"]
  E --> F["Phê duyệt / thực thi tại IdP, SCIM, ứng dụng"]
  F --> G["Đọc observed access và trạng thái phiên"]
  G --> H{"Khớp trạng thái mong muốn?"}
  H -->|"Không"| I["Retry, alert, remediation, exception owner"]
  I --> G
  H -->|"Có"| J["Lưu bằng chứng và hoàn tất event"]
~~~

Điểm cần lưu ý:

- Một event chỉ nên được xem là hoàn tất khi **các hệ thống trong phạm vi yêu cầu** xác nhận đã áp dụng thay đổi, hoặc có ngoại lệ được giải quyết theo chính sách.
- Trạng thái **cần có (desired state)** và **trạng thái đang có (observed state)** phải được lưu riêng.
- Phần việc chưa xong cần owner rõ ràng và thời hạn xử lý; không làm mất dấu vì một request trả thành công.
- Dữ liệu có thể thay đổi khi chạy workflow; cần chính sách xử lý event mới hơn đến trong lúc event cũ đang thực thi.
- Thao tác khóa/thu hồi khẩn cấp cần độ ưu tiên phù hợp, tránh bị chặn bởi chuỗi thao tác cấp quyền thông thường.

### 10.3. Ví dụ phát hiện tài khoản mồ côi

Một truy vấn dữ liệu minh họa để tìm **account con người vẫn được bật** trong khi hồ sơ nguồn đã chấm dứt:

~~~sql
SELECT
    a.system_name,
    a.account_id,
    a.identity_id,
    e.employment_status,
    e.status_effective_at
FROM iam_application_accounts AS a
JOIN employment_relationships AS e
  ON e.identity_id = a.identity_id
WHERE a.account_type = 'HUMAN'
  AND a.enabled = TRUE
  AND e.employment_status = 'TERMINATED'
  AND e.status_effective_at <= CURRENT_TIMESTAMP;
~~~

Đây là **SQL giả định mô hình đơn giản một quan hệ việc làm**, không áp dụng trực tiếp cho mọi hệ thống. Trên thực tế cần xử lý nhiều employment relationships, quyền của nhà thầu, account đặc biệt, quan hệ pháp nhân khác nhau, các bản ghi không liên kết được và ngoại lệ đã phê duyệt. Tài khoản mồ côi cũng bao gồm trường hợp **không còn identity/source owner hợp lệ**, vốn có thể không xuất hiện trong phép JOIN ở ví dụ này.

## 11. Đánh giá rủi ro và chỉ số vận hành

| Rủi ro | Cơ chế gây lỗi | Kiểm soát |
| --- | --- | --- |
| Employment status cập nhật muộn | Người đã nghỉ vẫn được nhìn nhận ACTIVE | Đồng bộ theo sự kiện, đo độ trễ, đối soát định kỳ |
| Dùng trạng thái mà không xét thời điểm hiệu lực | Khóa người còn làm việc hoặc thu hồi quá trễ | effectiveAt, lịch chạy và kiểm tra múi giờ |
| Sai mapping giữa HRIS và IAM | Trạng thái nghỉ phép bị hiểu là nghỉ việc | Data contract, mapping được duyệt và kiểm thử thay đổi |
| Chỉ nghe thay đổi status | Bỏ qua Mover vì người chuyển phòng ban vẫn ACTIVE | Theo dõi thuộc tính ảnh hưởng quyền và tính lại entitlement |
| Dùng email để đối chiếu chủ thể | Nhầm người hoặc tài khoản trùng | identityId ổn định, kiểm soát match/merge |
| Không quản lý nhà thầu ngoài HRIS | Hết hạn hợp đồng mà vẫn truy cập | Nguồn thẩm quyền theo workerType, owner và endDate |
| Khóa IdP mà không thu hồi ứng dụng | Residual session/token hoặc local account | SCIM/API và xác minh trạng thái thực tế |
| Sự kiện cũ đến sau sự kiện Leaver | Cấp lại quyền đã thu hồi | Version/order, idempotency, trạng thái ưu tiên bảo mật |
| Rehire khôi phục quyền quá rộng | Quyền cũ tồn dư dù công việc mới khác | Xác minh lại và cấp quyền theo vai trò hiện tại |
| Không có audit | Không xác định được ai thay đổi/quyền tồn dư từ bao giờ | Correlation ID, logs thao tác và kết quả hệ thống đích |

Các chỉ số hữu ích:

1. **Độ trễ dữ liệu HRIS → IAM:** từ thay đổi nghiệp vụ đến khi IAM nhận sự kiện hợp lệ.
2. **Thời gian thu hồi thực tế sau Leaver:** từ thời điểm hiệu lực đến lúc hệ thống đích xác nhận quyền đã hết.
3. **Tỷ lệ sự kiện JML hoàn tất:** số workflow được xác minh đủ mục tiêu trên tổng số workflow có hiệu lực.
4. **Tỷ lệ mapping exception:** số bản ghi có giá trị status không hiểu hoặc mâu thuẫn.
5. **Số account đang bật của người đã nghỉ:** xét theo thời gian hiệu lực và danh mục account quản lý.
6. **Số quyền tồn dư sau Mover:** entitlement hiện hữu vượt quá desired entitlement.
7. **Số nhà thầu quá hạn vẫn có account:** đối chiếu với nguồn hợp đồng và ngoại lệ.
8. **Tỷ lệ sự kiện trùng/cũ và lỗi đồng bộ:** giúp theo dõi độ tin cậy của pipeline.

Các chỉ số cần tách theo **hệ thống đích, mức rủi ro và loại chủ thể**. Ví dụ một SaaS không hỗ trợ thu hồi phiên tức thời phải được đánh giá theo giới hạn thực tế và biện pháp bù trừ; không được diễn giải "đã gửi lệnh" thành "đã hoàn tất".

## 12. Tình huống tổng hợp: nghỉ việc có hiệu lực trong tương lai

Một nhân viên thuộc Finance thông báo nghỉ việc, hồ sơ HRIS được cập nhật ngày **23/11/2026** với ngày nghỉ có hiệu lực **30/11/2026 lúc 18:00**. Nhân viên có account IdP, tài khoản ERP, hệ thống báo cáo, VPN và một quyền truy cập kho mã.

**Ngày 23/11 – tiếp nhận thông báo**

- IAM nhận event từ HRIS và xác thực nguồn, identityId, version.
- Hệ thống ghi lại thời điểm Leaver dự kiến; chưa suy luận mọi truy cập phải bị khóa ngay khi đã có thông báo.
- Các quyền nhạy cảm có thể được đánh giá sớm theo chính sách; các ngoại lệ và nhu cầu bàn giao được xử lý có phê duyệt.

**Đến 18:00 ngày 30/11 – thời điểm hiệu lực**

- Workflow thực thi thu hồi/khóa theo danh mục hệ thống.
- ERP, VPN và báo cáo trả kết quả, nhưng kho mã trả lỗi do API bị giới hạn.
- IdP đã khóa nhưng vẫn phải xét session/token và tài khoản được quản lý độc lập.
- IAM giữ trạng thái xử lý chưa hoàn tất, alert cho owner kho mã, retry hoặc dùng quy trình có thẩm quyền để thu hồi.

**Sau khi xác minh**

- Kiểm tra các account và quyền thực tế, thời gian quyền còn tồn tại so với effectiveAt.
- Ghi lại thời điểm hoàn tất và các ngoại lệ đã xử lý.
- Duy trì hồ sơ tối thiểu phục vụ kiểm toán theo chính sách, đồng thời ngăn truy cập của người đã rời tổ chức.

**Bài học:** employment status, đặc biệt khi là **sự kiện có ngày hiệu lực trong tương lai**, là đầu vào để điều phối quyền theo thời điểm. Thành công của quy trình phải được xác nhận ở các **hệ thống đích**, không chỉ từ trạng thái HRIS hoặc IdP.

## 13. Bảng kiểm tra khi tích hợp employment status

| Câu hỏi kiểm tra | Dấu hiệu đáp ứng |
| --- | --- |
| Nguồn nào có quyền cập nhật trạng thái nhân viên? | Chủ sở hữu dữ liệu, quy trình phê duyệt và khả năng truy vết |
| Nhà thầu/đối tác nằm ở đâu? | Nguồn hợp đồng/sponsor và quy trình hết hạn riêng |
| Các giá trị status có được định nghĩa rõ? | Bảng ánh xạ từng hệ thống và tài liệu phiên bản |
| Có phân biệt status với event và ngày hiệu lực? | Dữ liệu và workflow hỗ trợ future-effective changes |
| Có xử lý Mover khi status vẫn ACTIVE? | Theo dõi department/role/manager/project và tính lại quyền |
| Có tách account status khỏi employment status? | Bản ghi desired/observed theo hệ thống |
| Có xử lý unknown status, trùng, trễ, sai thứ tự? | Exception owner, version, idempotency, reconciliation |
| Có chống khôi phục account bị khóa do bảo mật? | Quy tắc ưu tiên restriction và phê duyệt mở lại |
| Có kiểm tra SCIM, token, session, quyền local? | Kiểm tra đích, retry và báo cáo quyền tồn dư |
| Có thể chứng minh Leaver hoàn tất? | Audit với effectiveAt, appliedAt, verifiedAt |
| Có chính sách rehire và nhiều quan hệ việc làm? | Quy tắc identity matching và cấp lại quyền mới |
| Có đánh giá tài khoản dịch vụ khi owner nghỉ? | Chuyển owner, rà soát quyền và credentials |

## 14. Câu hỏi tự đánh giá

1. Vì sao employment status = ACTIVE không đảm bảo một tài khoản được phép đăng nhập hoặc còn cần mọi quyền đã cấp?
2. Một nhân viên chuyển từ Support sang Finance nhưng employment status vẫn ACTIVE. IAM phải theo dõi trường và sự kiện nào để phát hiện Mover?
3. Khác nhau giữa HRIS employment status = TERMINATED và SCIM User.active = false là gì?
4. Nếu HRIS gửi thông báo ngày nghỉ trước một tuần, IAM nên phân biệt những thời điểm nào để tránh khóa quá sớm?
5. Một giá trị ON_LEAVE được đồng bộ từ HRIS mới nhưng mapping chưa rõ nghĩa. Điều gì có thể xảy ra nếu mặc định ON_LEAVE là TERMINATED?
6. Tài khoản IdP đã bị khóa nhưng refresh token của SaaS vẫn dùng được. Có thể khẳng định offboarding hoàn tất chưa?
7. Một người được tái tuyển dụng ở vị trí mới. Vì sao không được tự động khôi phục toàn bộ role và credential cũ?
8. Vì sao không nên đặt employment status theo kiểu nhân sự cho service account? Khi chủ sở hữu dịch vụ nghỉ việc cần làm gì?

## 15. Ghi nhớ

**Employment status là thuộc tính nghiệp vụ có nguồn, nghĩa và thời gian hiệu lực**, giúp IAM nhận biết quan hệ làm việc của một cá nhân. Để quản lý vòng đời danh tính an toàn, tổ chức phải kết hợp trạng thái này với loại lao động, sự kiện JML, thuộc tính công việc, nguồn xác minh, phê duyệt và chính sách truy cập.

Trong mô hình **Joiner–Mover–Leaver**, HRIS và nguồn hợp đồng cung cấp tín hiệu; IAM/IGA điều phối cấp hoặc thu hồi quyền; **IdP/SSO** quản lý xác thực và quan hệ tin cậy; **SCIM/API** hỗ trợ cập nhật tài khoản; **RBAC/ABAC** quyết định quyền; còn đối soát và kiểm toán xác minh trạng thái thực tế. Việc phân biệt **employment status**, **identity status**, **account status** và **entitlement/session** giúp giảm tài khoản mồ côi và quyền truy cập tồn dư, nhất là khi nhân sự thay đổi vai trò hoặc rời tổ chức.
