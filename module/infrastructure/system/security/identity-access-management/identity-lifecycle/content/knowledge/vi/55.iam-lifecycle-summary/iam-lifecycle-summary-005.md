# Checklist authorization trong IAM lifecycle

> **Chương:** Tổng kết IAM lifecycle  
> **Chủ đề:** Checklist thiết kế, triển khai và kiểm chứng **authorization (phân quyền/ủy quyền truy cập)** trong hệ thống Identity and Access Management (IAM). Bài học liên kết **Joiner–Mover–Leaver (JML)**, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, rà soát quyền, kiểm toán và ngăn quyền truy cập tồn dư.

## 1. Dùng checklist authorization để làm gì?

**Authentication** trả lời “người hoặc workload đang truy cập là ai và đã được xác thực thế nào?”. **Authorization** trả lời “chủ thể đó được làm hành động nào trên tài nguyên nào, trong bối cảnh nào?”. Sau khi đăng nhập, ứng dụng vẫn phải kiểm tra quyền cho từng hành động cần bảo vệ.

Ví dụ: một nhân viên có thể đăng nhập CRM bằng SSO nhưng chỉ được **xem ticket của nhóm mình**. Việc đã đăng nhập không cho phép nhân viên sửa ticket của nhóm khác, xuất toàn bộ khách hàng hoặc thay đổi vai trò quản trị.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Lập checklist phân quyền dựa trên **chủ thể – hành động – tài nguyên – bối cảnh**.
2. Phân biệt quyền được phê duyệt (**desired entitlement**), quyền được gán và **quyền hiệu lực thực tế** tại hệ đích.
3. Kiểm soát cấp và thu hồi quyền ở các sự kiện Joiner, Mover, Leaver, nhà thầu, dịch vụ và workload.
4. Phối hợp IdP/SSO/SCIM với RBAC, ABAC, ACL, token scope và điểm ra quyết định truy cập.
5. Kiểm tra **least privilege, default deny, phân tách nhiệm vụ (SoD), quyền tạm thời, quyền quản trị**, và tránh quyền tích lũy.
6. Thiết kế các kiểm thử âm tính cho vượt quyền ngang, vượt quyền dọc, truy cập chéo tenant và API.
7. Xác minh thu hồi quyền có hiệu lực và có bằng chứng kiểm toán, thay vì chỉ tin rằng một lệnh đã thành công.

### Cách sử dụng các ô kiểm

- **PASS:** kiểm soát đã được thực hiện và có bằng chứng phù hợp.
- **FAIL:** điều kiện không đạt; phải có người xử lý và mức ưu tiên.
- **PENDING/UNKNOWN:** chưa thu thập đủ bằng chứng; không tự xem là đạt.
- **N/A:** không áp dụng, cần ghi rõ lý do và người xác nhận.

Mỗi ô kiểm nên gắn với **owner, hệ thống, phạm vi môi trường, mức rủi ro, bằng chứng, ngày kiểm tra và hạn khắc phục**. Không đánh dấu PASS chỉ vì sản phẩm có tính năng nhưng chưa bật, chưa triển khai đúng hoặc chưa kiểm thử.

## 2. Những thành phần tạo nên một quyết định phân quyền

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Subject (chủ thể)** | Ai đang yêu cầu hành động? | Nhân viên EMP-0842; service principal deploy-api |
| **Action (hành động)** | Chủ thể muốn làm gì? | ticket:read, ticket:update, payment:approve |
| **Resource (tài nguyên)** | Đối tượng cụ thể nào được tác động? | Ticket T-1742, giao dịch P-901, bucket production |
| **Context (bối cảnh)** | Điều kiện đi kèm? | Tenant, thời điểm, trạng thái nhân sự, thiết bị, mức nhạy cảm |
| **Policy** | Quy tắc nào cho phép hoặc từ chối? | Role Support-Agent; department=Support; owner=subject |
| **Entitlement** | Quyền nào đã gán hoặc đang hiệu lực? | Role CRM-Viewer, ACL trên tài liệu |
| **Decision** | Hành động được cho phép không? | PERMIT hoặc DENY, kèm policy ID |
| **Enforcement** | Thành phần nào chặn yêu cầu bị từ chối? | API gateway, backend service, database policy |
| **Evidence** | Bằng chứng và người chịu trách nhiệm? | Log quyết định, phiên bản policy, người duyệt, readback |

Phân quyền cần gắn với **đối tượng cụ thể**. Câu hỏi “user có role Support-Agent không?” thường chưa đủ. Phải trả lời tiếp: ticket này thuộc tenant nào, team nào, đã đóng hay chưa, hành động sửa có hợp lệ ở trạng thái đó hay không?

### 2.1. RBAC, ABAC, ACL và quyền hiệu lực

| Cơ chế | Cách hoạt động | Ưu điểm | Rủi ro cần kiểm tra |
| --- | --- | --- | --- |
| **RBAC** | Role ánh xạ sang tập hành động | Quản lý quyền theo vị trí công việc | Role quá rộng, role cũ chưa thu hồi |
| **ABAC** | Quyết định dựa trên thuộc tính chủ thể/tài nguyên/bối cảnh | Phân quyền tinh hơn theo dữ liệu và điều kiện | Thuộc tính sai/cũ, chính sách khó hiểu |
| **ACL** | Tài nguyên lưu danh sách chủ thể/nhóm có quyền | Phù hợp tài liệu hoặc đối tượng chia sẻ cụ thể | Grant trực tiếp khó tìm và dễ bị bỏ sót |
| **Relationship-based control** | Quyết định dựa trên quan hệ chủ thể–tài nguyên | Phù hợp owner, thành viên dự án, người được giao việc | Quan hệ cũ chưa hủy, đồ thị có đường quyền không mong muốn |
| **Scopes/claims** | Phạm vi quyền hoặc thông tin trong token | Hữu ích cho API và federation | Token còn sống, claim cũ, scope rộng hoặc audience sai |

**Quyền mong muốn (D)** là quyền hợp lệ theo chính sách và phê duyệt. **Quyền hiệu lực (A)** là những gì hệ thống thực sự cho phép sau khi đánh giá role, group, ACL, policy và token/phiên. Khi thiết kế luồng cấp/thu hồi, so sánh hai tập để phát hiện thiếu hoặc thừa quyền:

~~~text
grantCandidates  = desired - actualEffective
revokeCandidates = actualEffective - desired
unchanged        = actualEffective ∩ desired
~~~

Đây là mô hình logic. Một quyền có thể đến từ nhiều đường (hai group, một ACL và một key); **gỡ một đường grant chưa chắc làm quyền hiệu lực biến mất**. Với deny policy hoặc điều kiện ABAC, role hiện diện cũng chưa chứng minh hành động được cho phép. Cách hợp nhất policy như allow/deny precedence cần được đặc tả rõ theo sản phẩm, tránh suy đoán.

## 3. Sơ đồ kiểm soát một yêu cầu truy cập

Trong mô hình kiểm soát truy cập theo chính sách, ta thường phân biệt **PAP** (nơi quản lý policy), **PIP** (nguồn thuộc tính), **PDP** (thành phần ra quyết định) và **PEP** (thành phần thực thi). Các vai trò này có thể nằm chung một ứng dụng, không nhất thiết là bốn dịch vụ độc lập.

~~~mermaid
flowchart TD
    U["User / Service / Workload"] --> AUTHN["Xác thực: IdP / SSO / Credential"]
    AUTHN --> REQ["Yêu cầu: subject, action, resource, context"]
    REQ --> PEP["PEP: API / Backend / Resource boundary"]
    PEP --> PDP["PDP: Đánh giá chính sách"]
    PAP["PAP: Policy đã phê duyệt"] --> PDP
    PIP["PIP: HR / IdP / DB / resource ownership"] --> PDP
    PDP -->|PERMIT| PEP
    PDP -->|DENY hoặc UNKNOWN| PEP
    PEP -->|Cho phép sau kiểm tra| RESOURCE["Tài nguyên được bảo vệ"]
    PEP -->|Từ chối| REJECT["Không thực hiện hành động"]
    PEP --> AUDIT["Audit / Metrics / Đối soát"]
    PDP --> AUDIT
~~~

**Quan trọng:** yêu cầu bị DENY hoặc không đủ dữ liệu để chứng minh quyền hợp lệ **không được đi qua** điểm thực thi. Một hệ thống không thể chỉ ẩn nút trên giao diện; backend phải đánh giá lại quyền khi nhận request.

### 3.1. Checklist kiến trúc chính sách

- [ ] Có danh mục tài nguyên và hành động cần bảo vệ; mỗi API/luồng nghiệp vụ nhạy cảm đều có điểm kiểm tra.
- [ ] Quy tắc **default deny** được áp dụng khi không có quyền hợp lệ hoặc dữ liệu cần thiết không đáng tin.
- [ ] Có nguồn đáng tin cho các thuộc tính như status nhân sự, tenant, team, owner tài nguyên và môi trường.
- [ ] Policy được lưu phiên bản, có owner, quy trình phê duyệt, kiểm thử và khả năng khôi phục phiên bản.
- [ ] Quyết định được thực thi **phía hệ thống tin cậy** (server/API/data boundary), không chỉ trên giao diện người dùng.
- [ ] Nếu gateway đã kiểm tra scope, service phía sau vẫn xác minh quyền tài nguyên khi scope không đủ để quyết định từng object.
- [ ] Chính sách có nguyên tắc rõ về role kế thừa, nhóm lồng nhau, deny/allow và quyền cấp trực tiếp.
- [ ] Hệ thống xử lý lỗi tra cứu policy/thuộc tính theo chiến lược an toàn: không âm thầm cấp quyền vì một backend authorization tạm lỗi.
- [ ] Quyền từ token được kiểm tra tính hợp lệ, issuer, audience và scope phù hợp; không tin dữ liệu role/tenant do client tự gửi.
- [ ] Có log quyết định quan trọng và cơ chế đối soát quyền hiệu lực với nguồn được phê duyệt.

### 3.2. Pseudocode kiểm tra quyền theo từng đối tượng

~~~text
function canUpdateTicket(principal, ticket, context):
    if principal.authenticated != true:
        return DENY
    if principal.status != ACTIVE:
        return DENY
    if principal.tenantId != ticket.tenantId:
        return DENY
    if "ticket:update" not in effectivePermissions(principal, context):
        return DENY
    if principal.teamId != ticket.assignedTeamId:
        return DENY
    if ticket.state == ARCHIVED:
        return DENY
    return PERMIT

function updateTicket(request):
    principal = verifyAuthentication(request)
    ticket = loadTicketFromTrustedStore(request.ticketId)
    if ticket == null:
        rejectRequest()
    if canUpdateTicket(principal, ticket, trustedContext(request)) != PERMIT:
        rejectRequest()
    performUpdate(ticket, validatedInput(request))
~~~

Đây là **giả mã để minh họa nguyên tắc**, không phải một implementation hoàn chỉnh. Tùy hệ thống cần bảo đảm kiểm tra và cập nhật không bị race condition (chẳng hạn quyền hoặc trạng thái tài nguyên đổi giữa lúc kiểm tra và lúc ghi), đồng thời nhất quán trong giao dịch hoặc áp dụng cơ chế kiểm tra phù hợp. Client không được tự khẳng định tenant hay vai trò để vượt kiểm tra phía server.

## 4. Checklist thiết kế role, policy và quyền tối thiểu

### 4.1. Danh mục quyền (entitlement catalog)

- [ ] Mỗi entitlement có **tên ổn định**, mô tả hành động, phạm vi tài nguyên, mức nhạy cảm và owner.
- [ ] Có bảng role → entitlement được rà soát; không dùng mô tả mơ hồ như “quyền tiêu chuẩn” khi cần kiểm chứng.
- [ ] Phân tách quyền xem, tạo, sửa, xóa, phê duyệt, xuất dữ liệu và quản trị cấu hình.
- [ ] Role được giới hạn theo ứng dụng, môi trường, đơn vị kinh doanh/tenant hoặc tập dữ liệu khi cần.
- [ ] Không cấp role quản trị toàn hệ thống chỉ vì một công việc cần sửa một đối tượng.
- [ ] Quyền nhạy cảm và quyền xuất dữ liệu được quản lý khác với quyền đọc cơ bản nếu mức rủi ro đòi hỏi.
- [ ] Định nghĩa cụ thể hành vi khi một người có nhiều role/nhóm hoặc có deny policy.
- [ ] Có owner quyết định role catalog, cập nhật policy và kiểm tra tác động trước khi mở rộng quyền.
- [ ] Gỡ các role không còn chủ sở hữu, không còn ứng dụng sử dụng hoặc không còn cơ sở nghiệp vụ.

### 4.2. RBAC cần đi với bối cảnh nghiệp vụ

Ví dụ ba role trong ứng dụng quản lý thanh toán:

| Role | Quyền | Ràng buộc |
| --- | --- | --- |
| **Payment-Viewer** | Xem thông tin đã cho phép | Theo tenant và phạm vi dữ liệu |
| **Payment-Creator** | Tạo đề nghị thanh toán | Không tự phê duyệt cùng giao dịch |
| **Payment-Approver** | Phê duyệt đề nghị | Chỉ giao dịch thuộc phạm vi được ủy quyền |

Một ứng dụng có thể để một người nhận nhiều role, nhưng chính sách phân tách nhiệm vụ phải ngăn việc **tự tạo rồi tự phê duyệt** một khoản thanh toán nếu quy định yêu cầu người độc lập. Chỉ kiểm tra hai role cùng tồn tại đôi khi chưa đủ: có chính sách cho phép nhiều role nhưng kiểm tra **người tạo khác người duyệt** ở từng giao dịch. Cần xác định SoD tĩnh (trong tập role) và SoD động (khi thực hiện giao dịch).

### 4.3. ABAC cần kiểm soát nguồn thuộc tính

~~~text
Rule: canReadCustomer
  subject.employmentStatus == "active"
  AND subject.department == "Support"
  AND subject.tenantId == resource.tenantId
  AND resource.classification != "restricted"
  AND context.deviceTrusted == true
~~~

Đây là ví dụ policy, không phải cú pháp chuẩn của một sản phẩm. Nếu HR cập nhật Mover nhưng ứng dụng vẫn cache department cũ, policy có thể đưa ra quyết định sai. Cần định nghĩa **độ mới (freshness)** của thuộc tính, nguồn chính thức, cách đồng bộ, hành vi khi thiếu dữ liệu và nơi thực thi. Với dữ liệu nhạy cảm, fail-open khi thiếu nguồn thuộc tính là lỗ hổng quan trọng.

### 4.4. Checklist phân tách nhiệm vụ và ngoại lệ

- [ ] Có danh sách các cặp quyền/hoạt động xung đột SoD, được owner nghiệp vụ duyệt.
- [ ] Kiểm tra SoD trước khi grant, khi Mover và khi role catalog thay đổi.
- [ ] Kiểm tra SoD ở **quyền hiệu lực**, bao gồm nhiều account, nhóm lồng nhau và grant trực tiếp trong phạm vi kiểm soát.
- [ ] Có kiểm soát SoD động cho nghiệp vụ cần người tạo và người duyệt khác nhau.
- [ ] Quyền ngoại lệ có lý do, approver độc lập phù hợp, phạm vi, chủ sở hữu và thời hạn hết hiệu lực.
- [ ] Hết hạn quyền tạm thời kích hoạt thu hồi và kiểm chứng, không chỉ gửi email nhắc.
- [ ] Có quy trình sử dụng và hậu kiểm đặc quyền khẩn cấp (break-glass) khi áp dụng.
- [ ] Quyền quản trị dài hạn được rà soát và giảm xuống quyền JIT/PAM khi có khả năng phù hợp.

## 5. Checklist cấp quyền: từ yêu cầu đến quyền thực tế

**Grant** bắt đầu khi quyền có căn cứ; kết thúc khi app cho phép đúng hành động trong đúng phạm vi và không phát sinh quyền vượt chính sách.

### 5.1. Xác minh yêu cầu và người phê duyệt

- [ ] Yêu cầu chỉ rõ subjectId, resourceId, action/entitlement, môi trường, lý do và thời điểm hiệu lực.
- [ ] Subject có trạng thái quan hệ hợp lệ từ nguồn đáng tin (HRIS/sponsor/workload registry).
- [ ] Tài khoản ở app đích map về đúng subject; không dựa chỉ vào email/tên có thể đổi.
- [ ] Quyền đã có được kiểm tra để tránh cấp trùng hoặc tạo thêm đường grant ngoài kiểm soát.
- [ ] Người có thẩm quyền xem xét yêu cầu theo vai trò manager/chủ dữ liệu/chủ ứng dụng.
- [ ] Quyền nhạy cảm hoặc vượt role chuẩn được phê duyệt độc lập, kiểm tra SoD.
- [ ] Quyền có hạn dùng có expiresAt, owner và cơ chế xử lý khi hết hạn.
- [ ] Mọi quyết định được ghi với policy version, ai phê duyệt, phạm vi và lý do.

### 5.2. Thực thi và kiểm chứng

- [ ] IAM/IGA xác định **tập entitlement mong muốn**, không chỉ gửi lệnh “thêm user”.
- [ ] Định nghĩa kênh cấp từng quyền: nhóm IdP, SCIM Group, API ứng dụng, cloud IAM, ACL hoặc manual task.
- [ ] Tài khoản app được provision đúng user ID; không có account trùng ngoài hệ thống nguồn.
- [ ] SCIM/API request được gắn correlation ID, kết quả được lưu và lỗi được xử lý.
- [ ] Nếu app cần thao tác thủ công, có owner, hạn thực hiện và bằng chứng sau cấp.
- [ ] Các group, role, direct grant và điều kiện ABAC thực tế được **đọc lại**.
- [ ] Có kiểm tra âm tính bảo đảm user không tự động nhận quyền ngoài phê duyệt.
- [ ] Chỉ đóng workflow khi trạng thái đã xác minh; nếu app đồng bộ bất đồng bộ, giữ trạng thái chờ xác minh.

### 5.3. Ví dụ Joiner

Nhân viên mới tên Hương được HR xác minh, mã EMP-0842, vào bộ phận Support từ ngày 01/12. IAM ánh xạ subject vào account CRM và role **Support-Agent**. Role cho phép đọc/cập nhật ticket **thuộc nhóm của Hương**, không cho xuất danh sách mọi khách hàng. Một yêu cầu riêng về quyền export phải qua chủ dữ liệu và giới hạn thời gian.

**Điều kiện PASS:** danh tính đúng người, account hoạt động từ ngày được cho phép, quyền hiệu lực trên ticket hợp lệ hoạt động, ticket nhóm khác bị từ chối, chức năng export bị từ chối nếu chưa được duyệt và kết quả được lưu làm bằng chứng.

Không nên chỉ thử “đăng nhập CRM thành công”: đó là bài kiểm tra authentication; chưa chứng minh authorization.

## 6. Checklist Mover: thu hồi quyền cũ, cấp đúng quyền mới

**Mover** là sự kiện thay đổi vai trò, bộ phận, dự án, cấp bậc, phạm vi dữ liệu hoặc quan hệ hợp tác. Nếu hệ thống chỉ gán role mới mà không rà soát role cũ, người dùng tích lũy quyền qua thời gian (*privilege accumulation*).

### 6.1. Checklist nhận diện quyền cần đổi

- [ ] Sự kiện Mover được xác nhận từ nguồn có thẩm quyền, có subjectId, sourceVersion và thời điểm có hiệu lực.
- [ ] ID danh tính ổn định khi email, chức danh, tên hiển thị hoặc manager thay đổi; tránh tạo account thứ hai.
- [ ] Tính lại **toàn bộ quyền mục tiêu** theo vai trò, thuộc tính, dự án và tài nguyên sau chuyển đổi.
- [ ] Liệt kê quyền hiệu lực **trước chuyển** tại từng app, kể cả direct grant, ACL và role không đến từ IdP.
- [ ] So sánh quyền mục tiêu với quyền thực tế; xác định tập grant cần thêm và tập quyền phải thu hồi.
- [ ] Kiểm tra SoD giữa quyền cũ và mới; nhận diện rủi ro giữ đồng thời hai vai trò.
- [ ] Quyền tạm thời trong giai đoạn bàn giao có lý do, owner, approver, scope và expiresAt.
- [ ] Xác định thứ tự thực hiện revoke/grant theo mức độ rủi ro và tính liên tục nghiệp vụ.
- [ ] Xem xét token/phiên đang mở có claim, scope hoặc quyền cache cũ; áp dụng cơ chế cập nhật hoặc chặn khi cần.
- [ ] Truy vấn lại entitlement thực tế và xử lý sai lệch tới khi hoàn tất.

### 6.2. Ví dụ Mover

Hương chuyển từ Support sang Finance. Quyền cũ gồm **tickets:read**, **tickets:update** và một ACL riêng cho phép **customers:export**. Quyền mới hợp lệ là **finance:reports:read**; quyền **payments:approve** cần duyệt riêng.

~~~text
Actual before:
  CRM: tickets:read, tickets:update, customers:export
  Finance: (none)

Desired after move:
  CRM: (none)
  Finance: finance:reports:read

Plan:
  REVOKE CRM group Support-Agent
  REVOKE CRM direct ACL customers:export
  GRANT Finance role Finance-Viewer
  VERIFY effective access in both applications
~~~

**Kết luận:** Mover chưa hoàn tất nếu ACL export vẫn còn, kể cả khi nhóm Support-Agent đã bị xóa. Nếu Finance-Viewer vô tình cho phép duyệt thanh toán, cần sửa role catalog/chính sách và xử lý quyền thực tế trước khi đánh dấu hoàn thành.

### 6.3. Checklist kiểm tra thời điểm chuyển quyền

| Tình huống | Kiểm tra cần có |
| --- | --- |
| Chuyển bộ phận theo lịch | Quyền cũ hết hiệu lực đúng mốc; quyền mới bắt đầu đúng mốc |
| Chuyển sang quản trị | SoD, MFA/step-up, quyền JIT, approver và phiên đặc quyền |
| Chuyển giữa tenant/pháp nhân | Không giữ quyền đọc dữ liệu tenant cũ nếu không có căn cứ riêng |
| Vừa có role cũ vừa role mới để bàn giao | Ngoại lệ có thời hạn, hạn chế scope và tự thu hồi |
| Quay lại vai trò cũ | Quyền được tính lại theo chính sách hiện hành, không mặc nhiên khôi phục grant lịch sử |
| Có grant trực tiếp ở ứng dụng | Đối soát entitlement của app, không chỉ nhóm IdP |

## 7. Checklist Leaver: thu hồi quyền hiệu lực và tránh quyền tồn dư

**Leaver** là sự kiện kết thúc quan hệ hoặc quyền truy cập được giao. Với người lao động/nhà thầu, nguồn thường là HR hoặc sponsor. Với service account, nguồn là lifecycle của workload hoặc quyết định của owner.

### 7.1. Trước thời điểm thu hồi

- [ ] Sự kiện Leaver đến từ nguồn đáng tin, có thời điểm hiệu lực và timezone rõ ràng.
- [ ] Phân biệt Leaver có kế hoạch với chấm dứt khẩn cấp; mức ưu tiên và thẩm quyền đã định nghĩa.
- [ ] Có bản đồ tài khoản IdP, SaaS, repository, cloud, database, VPN và account local.
- [ ] Inventory quyền bao gồm group, role, ACL, direct grant, API scope, PAT/API key và quyền admin.
- [ ] Xác định các tài nguyên thuộc sở hữu của Leaver cần bàn giao để không giữ account hoạt động vì mục đích lấy dữ liệu.
- [ ] Có owner và đường xử lý cho ứng dụng không hỗ trợ SCIM/API.
- [ ] Lưu phiên bản trạng thái nguồn để không cho job Joiner/Mover cũ cấp lại quyền sau Leaver.

### 7.2. Khi Leaver có hiệu lực

- [ ] Disable identity/SSO và chặn đăng nhập mới theo khả năng IdP.
- [ ] Thực thi revoke role/group/ACL tại **từng app**, kể cả quyền không phụ thuộc nhóm IdP.
- [ ] Disable hoặc deprovision account ứng dụng qua SCIM/API hoặc bước thủ công được xác nhận.
- [ ] Kiểm tra và thu hồi API token, PAT, SSH key, certificate, refresh token và session liên quan theo khả năng từng hệ.
- [ ] Chặn truy cập local, VPN, remote access và account phụ nếu chúng còn tạo ra quyền không hợp lệ.
- [ ] Chuyển owner các workflow, dashboard, repo, dữ liệu và automation.
- [ ] Xử lý chính sách lưu giữ hồ sơ/dữ liệu tách khỏi quyết định chặn truy cập.
- [ ] Với hệ đích offline, thực hiện biện pháp giảm rủi ro sẵn có và giữ ngoại lệ mở cho tới khi có bằng chứng.

### 7.3. Sau thời điểm thu hồi

- [ ] Đọc lại trạng thái IdP và từng ứng dụng; ghi rõ hệ nào xác minh thành công.
- [ ] Đối soát ngược app account, ACL và token với danh tính hợp lệ để tìm tài khoản mồ côi.
- [ ] Kiểm chứng app session và token độc lập không còn quyền truy cập không hợp lệ theo cơ chế đã định.
- [ ] Không có grant mới từ retry của job cũ; nếu có phải khắc phục và điều tra.
- [ ] Bằng chứng bao gồm eventId, effectiveAt, thao tác, target, kết quả, verifiedAt và owner.
- [ ] Những phần chưa thể xác minh giữ trạng thái PARTIAL/UNKNOWN, có deadline và người xử lý.

**Vì sao disable IdP chưa đủ?** SSO giúp xác thực liên kết, nhưng SaaS có thể giữ phiên riêng, API key hoặc account local. SCIM có thể cập nhật thuộc tính active của user nhưng không nhất thiết hủy mọi token/phiên ở hệ đích. Một entitlement có thể được gán trực tiếp không thông qua IdP. Do đó Leaver hoàn tất khi **các đường truy cập thuộc phạm vi đều được xác minh là đã chặn**, hoặc ngoại lệ được báo cáo đúng trạng thái và tiếp tục quản lý.

### 7.4. Phân biệt thu hồi quyền với xóa dữ liệu

Một ứng dụng có thể cần giữ hồ sơ không hoạt động để lưu dấu vết giao dịch, hỗ trợ bàn giao hoặc tuân thủ nghĩa vụ lưu giữ. **Disable account/revoke access** nhằm chặn hành động không hợp lệ. **Delete/purge data** là quyết định riêng có cơ sở, thời hạn và quy trình áp dụng. Không xóa dữ liệu tùy tiện chỉ vì vừa nhận sự kiện Leaver.

## 8. Checklist thực thi authorization ở ứng dụng, API và dữ liệu

Luồng IAM quyết định ai nên có quyền, nhưng **ứng dụng thực thi authorization ở từng request**. Nếu điểm kiểm tra quyền có lỗ hổng, role catalog và provisioning đúng vẫn không bảo đảm dữ liệu được bảo vệ.

### 8.1. Checklist authorization phía server

- [ ] Mỗi endpoint/hành động có kiểm tra permission phù hợp, không chỉ xác thực đăng nhập.
- [ ] Người dùng không thể thay tham số userId, objectId, tenantId để truy cập tài nguyên của người khác (*BOLA/IDOR*).
- [ ] API kiểm tra **object-level authorization** sau khi truy vấn tài nguyên có nguồn đáng tin.
- [ ] API kiểm tra **function-level authorization**: route admin, approve, export, delete, batch không thể gọi bằng role thấp.
- [ ] Thuộc tính nhạy cảm trong body (ownerId, role, price, tenantId, approvedBy) không được cập nhật chỉ vì client gửi giá trị.
- [ ] Danh sách và tìm kiếm chỉ trả dữ liệu thuộc phạm vi được phép; không chỉ lọc ở giao diện.
- [ ] Với download/export, permission và phạm vi dữ liệu được kiểm tra cả khi tạo job lẫn khi tải kết quả.
- [ ] WebSocket, GraphQL, background job, webhook và các endpoint cũ áp dụng kiểm soát tương đương REST.
- [ ] Quyền trên file, URL ký tạm và tài nguyên lưu trữ có scope/thời hạn phù hợp; không tạo đường tải bypass policy.
- [ ] Các policy tenant isolation được đánh giá trên server/data layer; tenantId từ client không phải bằng chứng chủ thể thuộc tenant.
- [ ] Khi thiếu policy/thuộc tính hoặc authorization service lỗi, ứng dụng xử lý **fail closed** đối với hành động được bảo vệ.
- [ ] Có kiểm thử âm tính khi user không có quyền, khi object không tồn tại và khi trạng thái đối tượng thay đổi.

### 8.2. Đừng nhầm kiểm tra URL với kiểm tra object

**Ví dụ sai về mặt kiểm soát:**

~~~text
GET /api/tickets/T-1742
  requireLogin()
  return findTicket("T-1742")
~~~

Nếu người dùng chỉ đổi ID trong URL là đọc được ticket tenant khác, hệ thống bị lỗi **Broken Object Level Authorization (BOLA)**. Một kiểm tra đúng hơn:

~~~text
GET /api/tickets/T-1742
  principal = verifiedPrincipal()
  ticket = findTicket("T-1742")
  require ticket is visible to principal
  require principal can "ticket:read" on ticket
  return projectionOfAllowedFields(ticket, principal)
~~~

**Chú ý:** không nhất thiết trả thông tin khác nhau cho “không có tài nguyên” và “không có quyền”, vì thông báo và timing có thể tiết lộ sự tồn tại dữ liệu. Hành vi API nên được thống nhất theo mô hình bảo mật và yêu cầu sản phẩm.

### 8.3. Checklist API token và service-to-service

- [ ] Resource server xác minh issuer/audience/chữ ký/thời hạn hoặc dùng cơ chế token introspection phù hợp.
- [ ] API kiểm tra scope/permission cần thiết **cho từng hành động**, không coi token hợp lệ là toàn quyền.
- [ ] Token của một service chỉ được dùng cho audience, tenant và môi trường đúng mục đích.
- [ ] Khi token đại diện người dùng (*on-behalf-of*), hệ thống phân biệt quyền của client với quyền của người dùng; không tự nâng scope.
- [ ] Với token machine-to-machine, có danh tính workload và owner riêng; không mượn token của nhân viên.
- [ ] Có cách revoke, rotate, kết thúc TTL và phát hiện credential không còn chủ sở hữu.
- [ ] Không tin các header như X-User-Role hoặc X-Tenant từ client trừ khi được thiết lập, bảo vệ và xác minh bởi thành phần tin cậy.
- [ ] Các đường API không có browser/SSO cũng được kiểm kê trong Leaver và incident response.

### 8.4. Checklist đa tenant và quan hệ sở hữu

| Hành động | Điều kiện quyền gợi ý | Kiểm thử âm tính |
| --- | --- | --- |
| Xem ticket | Cùng tenant và team được giao | User tenant A không đọc ticket tenant B |
| Sửa ticket | Có ticket:update và ticket thuộc phạm vi | User có quyền đọc vẫn không sửa được |
| Duyệt thanh toán | Có approve trong đơn vị được giao, kiểm tra SoD | Người tạo không duyệt chính giao dịch nếu chính sách cấm |
| Xem hồ sơ nhân sự | Có permission đúng nhóm dữ liệu | Manager không đọc hồ sơ ngoài phạm vi quản lý |
| Xuất báo cáo | Có export permission và scope dữ liệu | Role viewer không truy cập endpoint export |
| Chia sẻ tài liệu | Có quyền chia sẻ và kiểm soát recipient | Không cấp quyền cho tenant hoặc email ngoài chính sách |

Đây là mẫu thiết kế để thích ứng theo sản phẩm; danh sách quyền và điều kiện cụ thể phải đến từ nghiệp vụ thực tế. Chính sách nên **tập trung quyết định** khi khả thi nhưng vẫn cần thực thi tại điểm có thể chặn hành động và hiểu tài nguyên.

## 9. Checklist tài khoản dịch vụ, nhà thầu và danh tính bên ngoài

Chính sách authorization phải bao phủ cả **con người** và **workload**. Nhân viên có sự kiện JML từ HRIS; nhà thầu có ngày kết thúc và sponsor; service account có vòng đời từ dự án, pipeline, dịch vụ hoặc nền tảng vận hành.

### 9.1. Service account, service principal và workload identity

- [ ] Mỗi workload có ID, owner, mục đích sử dụng, môi trường, resource và ngày rà soát rõ ràng.
- [ ] Ưu tiên managed identity, federation hoặc credential ngắn hạn khi hạ tầng hỗ trợ; hạn chế secret tĩnh không có ngày hết hạn.
- [ ] Service principal chỉ được cấp scope và role cần cho một workload; dev và production được phân tách theo chính sách.
- [ ] Không gán vai trò Owner/Admin toàn hệ thống chỉ vì cần triển khai một ứng dụng.
- [ ] Nếu một pipeline cần đọc secret, chỉ cấp quyền đọc đúng secret hoặc nhóm secret được duyệt.
- [ ] Có người có thẩm quyền phê duyệt thay đổi role, audience, trust relationship và scope.
- [ ] Không dùng PAT cá nhân của kỹ sư làm đường cấp quyền lâu dài cho CI/CD.
- [ ] Có cách rà soát unused permission, key, workload không còn chạy và role tích lũy.
- [ ] Khi workload đổi mục đích hoặc chuyển nhóm, thực thi **Mover**: gỡ quyền cũ, cấp scope mới, kiểm chứng.
- [ ] Khi ngừng workload, thực thi **Leaver**: revoke role, trust, key và credential không còn dùng; readback trên cloud/service.
- [ ] Khi owner nghỉ việc, chuyển owner và rà soát secret, token, trust; không để account dịch vụ mồ côi.

Ví dụ: pipeline CI chỉ cần tạo bản phát hành cho dịch vụ A. Quyền deploy toàn bộ cluster hoặc quyền đọc secret của dịch vụ B là vượt phạm vi. Khi pipeline chuyển sang dịch vụ C, cần thu hồi quyền A và cấp quyền C theo quy trình, kể cả khi pipeline vẫn chạy thành công với role cũ.

### 9.2. Nhà thầu, đối tác, khách hàng doanh nghiệp

- [ ] Danh tính bên ngoài có sponsor/owner nội bộ và nguồn xác minh được chấp nhận.
- [ ] Phạm vi dữ liệu theo hợp đồng, tenant, dự án và thời hạn được mô tả rõ.
- [ ] Quyền được thiết kế hạn chế theo công việc và không tự động kế thừa quyền nội bộ của nhân viên.
- [ ] Có ngày hết hạn và trigger thu hồi khi hợp đồng/sponsor kết thúc hoặc dự án đổi phạm vi.
- [ ] Quyền chia sẻ chéo tổ chức/tenant cần chính sách riêng và người duyệt có trách nhiệm.
- [ ] Có cách rà soát khách mời, tài khoản cộng tác và link chia sẻ ngoài tổ chức.
- [ ] Khi sponsor thay đổi, hệ thống chuyển owner hoặc thu hồi quyền nếu không còn ai xác nhận nhu cầu.
- [ ] Đối soát user app đích với danh mục đối tác để tìm tài khoản bên ngoài bị bỏ quên.

### 9.3. Break-glass và quyền quản trị đặc biệt

- [ ] Tài khoản khẩn cấp có danh mục, owner, lý do tồn tại và phạm vi tối thiểu cần cho phục hồi.
- [ ] Chỉ người được chỉ định có thể dùng credential theo runbook; hoạt động được giám sát và ghi log.
- [ ] Có giới hạn thời gian sử dụng và cơ chế thay credential/thu hồi phiên sau khi dùng theo chính sách.
- [ ] Có hậu kiểm để xác nhận hành động đã thực hiện và quyền còn tồn tại.
- [ ] Quyền khẩn cấp không trở thành lối tắt để bypass phân quyền thường xuyên hoặc bỏ qua Leaver.

## 10. Checklist access review và đối soát quyền

**Access review** là việc người có trách nhiệm xác nhận quyền hiện tại còn phù hợp hay không. Một review chỉ hoàn thành về mặt thực thi khi các quyết định **thu hồi** đã được áp dụng và xác minh.

### 10.1. Chuẩn bị dữ liệu rà soát

- [ ] Có inventory account/entitlement thực tế ở hệ đích, không chỉ danh sách nhóm trên IdP.
- [ ] Mỗi grant ánh xạ đến subjectId/workloadId hợp lệ, resource, quyền, owner và nguồn cấp nếu có thể.
- [ ] Danh sách direct grant, nhóm lồng nhau, local account, API key, service principal và quyền chia sẻ được xem xét.
- [ ] Có dữ liệu sử dụng quyền hợp pháp để hỗ trợ đánh giá nhưng không tự động coi “đã dùng” là “cần”.
- [ ] Phân loại quyền rủi ro cao, đặc quyền, export, cross-tenant và quyền không có hạn.
- [ ] Người xét có đủ thông tin nghiệp vụ, và quy trình xử lý reviewer xung đột lợi ích.
- [ ] Hệ thống cho phép reviewer chọn giữ, thu hồi, sửa scope hoặc yêu cầu bổ sung căn cứ.

### 10.2. Khi kết thúc một access review

- [ ] Quyết định “revoke” tạo thao tác thực thi được theo từng hệ đích.
- [ ] Kết quả thực tế được đọc lại; xác nhận role/ACL/token đã mất hoặc đã xử lý ngoại lệ.
- [ ] Quyền tạm thời được so với expiresAt và tự thu hồi khi hết hạn.
- [ ] User không còn trong HRIS nhưng app vẫn active được phát hiện và có owner xử lý.
- [ ] Quyền không liên kết được với chủ thể hoặc owner bị gắn nhãn **orphan/unknown** để xử lý.
- [ ] Quyền “giữ lại” có phê duyệt, căn cứ và chu kỳ rà soát tiếp theo.
- [ ] Review lưu dấu vết người xét, ngày xét, policy, quyết định, hành động khắc phục, verifiedAt.

### 10.3. Đối soát hai chiều

~~~mermaid
flowchart LR
    SRC["Nguồn danh tính + Chính sách quyền"] -->|So quyền mong muốn| TARGET["IdP / SaaS / Cloud / Database"]
    TARGET -->|Đọc lại user, role, ACL, token| RECON["Reconciliation"]
    SRC --> RECON
    RECON --> GAP["Sai lệch: thiếu quyền / thừa quyền / orphan / hết hạn"]
    GAP --> REMEDY["Owner xử lý, cập nhật hoặc thu hồi"]
    REMEDY --> TARGET
    TARGET --> VERIFY["Xác minh lại và lưu bằng chứng"]
~~~

**Nguồn → đích** phát hiện tài khoản/quyền hợp lệ chưa được cấp hoặc quyền cũ chưa thu hồi. **Đích → nguồn** phát hiện account local, direct grant và service identity không có chủ sở hữu. Với ứng dụng không cung cấp API đọc quyền, có thể cần kiểm tra có xác nhận thủ công và ghi rõ giới hạn.

## 11. Checklist lỗi điều phối, consistency và an toàn khi retry

Các hệ thống trong IAM không chia sẻ một giao dịch duy nhất. IdP có thể thay đổi group thành công trong khi CRM lỗi; một webhook có thể đến hai lần; một job Mover có thể chạy lại sau Leaver.

### 11.1. Mô hình trạng thái workflow

| Trạng thái mẫu | Ý nghĩa |
| --- | --- |
| **PENDING_APPROVAL** | Cần quyết định hợp lệ trước khi grant |
| **APPROVED** | Quyền đã được duyệt nhưng chưa xác minh đã có |
| **IN_PROGRESS** | Đang thực hiện thay đổi ở các hệ đích |
| **PENDING_VERIFICATION** | Hệ đích phản hồi nhưng chưa đọc lại trạng thái |
| **PARTIAL** | Một số hệ đã đạt mục tiêu, hệ khác chưa |
| **FAILED** | Thao tác không hoàn tất, cần owner/escalation |
| **COMPLETED** | Quyền thực tế đạt mục tiêu và bằng chứng đã lưu |
| **REJECTED** | Yêu cầu bị từ chối theo chính sách |

Tên trạng thái có thể khác giữa các sản phẩm. Điều quan trọng là **đã phê duyệt**, **đã gửi request**, **đã nhận ACK** và **đã xác minh quyền thực tế** không bị xem là cùng một trạng thái.

### 11.2. Các ô kiểm kỹ thuật

- [ ] Mỗi event/request có ID để **idempotent**: retry không tạo account/role trùng hoặc thêm quyền mới ngoài mục tiêu.
- [ ] Gắn sourceVersion, policyVersion và effectiveAt với quyết định quyền.
- [ ] Trước khi grant hoặc retry, kiểm tra danh tính còn hợp lệ theo trạng thái mới nhất; Leaver không được bị Mover cũ cấp lại quyền.
- [ ] Connector xử lý timeout, 429/rate limit, 5xx với retry có giới hạn và backoff.
- [ ] Lỗi account mapping, thiếu quyền thực thi, lỗi policy hoặc dữ liệu nguồn sai được chuyển xử lý có người phụ trách.
- [ ] Không coi phản hồi API thành công là readback; có bước query entitlement thực tế.
- [ ] Theo dõi trạng thái theo từng target và lưu correlation ID cho yêu cầu.
- [ ] Có thời hạn xử lý theo phân loại rủi ro, nhất là revoke quyền nhạy cảm hoặc Leaver khẩn cấp.
- [ ] Khi không thể xác minh, giữ trạng thái PARTIAL/UNKNOWN và thông báo đúng owner.
- [ ] Đối soát định kỳ phát hiện drift kể cả khi hệ thống sự kiện hoạt động bình thường.
- [ ] Connector/automation có quyền tối thiểu; credential và log không để lộ bí mật.

### 11.3. Ví dụ race condition sau Leaver

~~~text
09:00  HR phát MOVER v17: Support -> Finance
09:01  Job grant Finance v17 timeout, xếp hàng retry
09:02  HR phát LEAVER v18, có hiệu lực ngay
09:03  Leaver disable account và thu hồi các quyền
09:04  Job grant Finance v17 được chạy lại
~~~

Nếu job v17 áp dụng mù quáng, nó có thể cấp lại Finance cho người đã nghỉ. Workflow đúng phải kiểm tra **phiên bản nguồn và trạng thái mới nhất**, bỏ qua v17 hoặc tính lại mục tiêu theo v18, chặn grant khi danh tính đã chấm dứt và thực hiện đối soát sau các tác vụ chạy song song.

### 11.4. Trường hợp hệ đích không thể thu hồi ngay

Với một Leaver khẩn cấp mà SaaS offline, phải:

1. Ghi đúng hệ chưa xác nhận và mức độ rủi ro của quyền còn tồn tại.
2. Chặn các đường truy cập còn có thể chặn (IdP, VPN, gateway, token/key nếu kiểm soát được).
3. Cảnh báo owner, thực hiện escalation theo runbook và duy trì trạng thái xử lý mở.
4. Khi app phục hồi, tiếp tục thu hồi rồi **đọc lại quyền hiệu lực**.
5. Lưu thời gian thực sự xác nhận mất quyền; không lấy thời điểm gửi request thay thế.

## 12. Checklist kiểm thử authorization

Các test cần sử dụng **tài khoản và dữ liệu thử nghiệm được phép**. Luôn kiểm tra một trường hợp được cho phép và ít nhất các trường hợp bị từ chối tương ứng; kiểm thử chỉ trên UI là chưa đủ.

### 12.1. Ma trận kiểm thử cốt lõi

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| AZ-01 | User đúng tenant, đúng team, role có ticket:read | Chỉ đọc được ticket trong phạm vi |
| AZ-02 | User có role Viewer thử gọi API update | Backend từ chối, dữ liệu không thay đổi |
| AZ-03 | User thay ticketId thành ticket người khác | Không đọc/sửa được object ngoài phạm vi |
| AZ-04 | User tenant A gửi tenantId B trong request | Không có dữ liệu hoặc quyền tenant B |
| AZ-05 | User thiếu role admin gọi endpoint quản trị | Từ chối ở server, kể cả khi gọi trực tiếp API |
| AZ-06 | User có quyền create nhưng tự approve giao dịch đã tạo | Bị từ chối nếu SoD chính sách cấm |
| AZ-07 | Quyền export chưa được duyệt, gọi export API | Từ chối; không tạo hoặc tải file export |
| AZ-08 | Group đã gỡ nhưng direct grant còn | Đối soát phát hiện vẫn có quyền, revoke chưa PASS |
| AZ-09 | Mover đổi role; token chứa claim cũ | Quyền cũ bị chặn theo cơ chế làm mới/thu hồi đã thiết kế |
| AZ-10 | Leaver đã disable IdP; app có local account | Local account không còn cho truy cập |
| AZ-11 | Leaver có PAT/API key độc lập | Credential bị thu hồi/chặn và đã xác minh |
| AZ-12 | App/PDP thiếu thuộc tính ABAC quan trọng | Từ chối theo chính sách an toàn |
| AZ-13 | API trả danh sách nhiều trang | Mọi trang đều lọc đúng phạm vi dữ liệu |
| AZ-14 | Export job chạy bất đồng bộ | Có kiểm tra scope lúc yêu cầu, xử lý và tải kết quả theo thiết kế |
| AZ-15 | Quyền tạm thời hết expiresAt | Không còn hành động được phép sau hạn; có log revoke |
| AZ-16 | Job Mover cũ chạy lại sau Leaver | Không cấp lại role/account |
| AZ-17 | Service account project A gọi API project B | Bị từ chối theo scope/audience/resource |
| AZ-18 | Thay đổi owner/tenant của object cùng lúc request | Không vượt qua kiểm tra do race hoặc dữ liệu cache cũ |

### 12.2. Cặp kiểm thử dương tính và âm tính

Giả sử chức năng **duyệt giao dịch** có chính sách: người duyệt phải ở tenant hợp lệ, có permission approve, được giao hạn mức và không là người tạo giao dịch.

| Kiểm thử | Điều kiện | Kết quả |
| --- | --- | --- |
| Positive | Approver đúng tenant, trong hạn mức, khác người tạo | PERMIT |
| Negative 1 | Viewer đúng tenant, không có approve | DENY |
| Negative 2 | Approver đúng role nhưng khác tenant | DENY |
| Negative 3 | Approver cũng là người tạo | DENY |
| Negative 4 | Approver quá hạn mức | DENY |
| Negative 5 | Đã Mover, quyền approve phải thu hồi | DENY |
| Negative 6 | Authorization backend không có dữ liệu tenant đáng tin | DENY hoặc xử lý chặn an toàn |

Mục tiêu là kiểm tra **điều kiện quyết định** thay vì chỉ kiểm tra xem endpoint trả mã thành công hay thất bại. Cũng cần xác minh dữ liệu không bị thay đổi trong các trường hợp DENY.

### 12.3. Những bẫy thường bị bỏ sót

- **UI ẩn nút, API không chặn:** user gọi trực tiếp API và vẫn thực hiện hành động.
- **BOLA/IDOR:** thay một ID trong URL là đọc được dữ liệu của người khác.
- **BFLA:** người dùng thấp quyền gọi chức năng vốn dành cho admin.
- **Mass assignment:** body yêu cầu ghi chứa role hoặc ownerId và ứng dụng cập nhật theo client.
- **Leak qua search/list:** endpoint chi tiết có kiểm tra nhưng tìm kiếm, export hoặc số đếm tiết lộ dữ liệu ngoài phạm vi.
- **Cache stale:** role hoặc thuộc tính đã đổi nhưng phiên, token hoặc cache quyết định vẫn dùng quyền cũ.
- **Background job:** lúc yêu cầu tạo export hợp lệ, nhưng khi job chạy hoặc download kết quả lại thiếu kiểm tra scope và người nhận.
- **Group nesting:** quyền còn đi qua một nhóm khác sau khi gỡ nhóm đầu.

## 13. Checklist kiểm toán, giám sát và chỉ số

Authorization cần một chuỗi bằng chứng nối từ **nguồn quyết định** đến **trạng thái thực tế**. Không nên chỉ đếm số request được thực thi, vì quyền bất hợp lệ có thể được giữ lâu và không có sự kiện đăng nhập nào mới.

### 13.1. Dữ liệu bằng chứng tối thiểu

| Trường | Mục đích |
| --- | --- |
| requestId / eventId / subjectId | Liên kết yêu cầu, danh tính và sự kiện JML |
| source / sourceVersion / effectiveAt | Nguồn có thẩm quyền, phiên bản, mốc hiệu lực |
| resourceId / action / scope | Xác định chính xác quyền nào trên tài nguyên nào |
| policyId / policyVersion | Giải thích quy tắc đã đánh giá và kết quả |
| requestedBy / approvedBy / businessOwner | Truy trách nhiệm và phê duyệt |
| desiredBefore / desiredAfter | Mục tiêu cấp, cập nhật hoặc thu hồi |
| targetAccountId / connectorRequestId | Nối quyết định với thao tác hệ đích |
| actualAfter / verifiedAt | Quyền thực tế sau thay đổi và thời điểm kiểm chứng |
| exceptionOwner / expiresAt / resolvedAt | Theo dõi ngoại lệ, quyền tạm thời và khắc phục |

Ví dụ một bản ghi kiểm chứng quyền sau Mover:

~~~yaml
reviewId: IAM-MOVER-2026-0183
subjectId: EMP-0842
sourceEventId: HR-2026-0279
sourceVersion: 18
effectiveAt: "2026-11-23T09:00:00+07:00"
targetSystem: crm-production
action: REVOKE
entitlement: customers:export
grantSourcesBefore:
  - group: Data-Exporters
  - directAcl: customer-export
desiredAfter: DENY
operationResult: SUCCESS
actualAfter: DENY
verifiedAt: "2026-11-23T09:03:10+07:00"
verifiedBy: iam-reconciler
exception: null
~~~

Đây là bản ghi **minh họa nghiệp vụ**, không phải schema chuẩn của SCIM, RBAC hoặc một sản phẩm IGA cụ thể. Giá trị *actualAfter: DENY* cần có phương pháp xác minh phù hợp, chẳng hạn đọc lại entitlement và kiểm thử API đã được cho phép trong môi trường phù hợp; chỉ ghi DENY từ một kết quả update chưa đủ.

### 13.2. Các câu hỏi cho người vận hành và kiểm toán

- [ ] Mỗi grant/revoke có chủ thể, người yêu cầu hoặc nguồn JML, owner và policy version?
- [ ] Có thể truy xuất vì sao một user hiện có quyền và **đường nào tạo ra quyền**?
- [ ] Mỗi quyền nhạy cảm có phê duyệt còn hiệu lực và thời hạn hoặc chu kỳ review?
- [ ] Access review có chứng minh hành động revoke đã thực thi không?
- [ ] Quyền tạo từ manual grant, ACL và token có nằm trong kiểm kê?
- [ ] Hệ thống ghi nhận các quyết định từ chối quan trọng hoặc truy cập bất thường, với thông tin vừa đủ để điều tra?
- [ ] Log được bảo vệ, có thời hạn lưu và người được truy cập theo chính sách?
- [ ] Không lưu mật khẩu, private key, raw access token hoặc dữ liệu cá nhân không cần thiết trong log?
- [ ] Kết quả sai lệch có owner, mức ưu tiên, deadline, thời gian khắc phục và readback?
- [ ] Báo cáo Leaver phân biệt *IdP disabled* với *tất cả app và token đã xác minh thu hồi*?

### 13.3. Chỉ số cần theo dõi

| Chỉ số | Cách diễn giải |
| --- | --- |
| **Grant correctness** | Tỷ lệ entitlement thực tế khớp quyền được phê duyệt |
| **Mover stale-entitlement rate** | Tỷ lệ Mover còn quyền cũ sau thời hạn xử lý |
| **Revoke latency** | Từ mốc cần thu hồi đến khi hệ đích cuối xác minh mất quyền |
| **Orphan account/grant count** | Account/quyền không ánh xạ được với danh tính/workload hoặc owner hợp lệ |
| **Temporary access overdue** | Quyền tạm thời còn hiệu lực sau expiresAt |
| **SoD violation count** | Quyền hoặc giao dịch xung đột chưa được xử lý theo chính sách |
| **Direct grant coverage** | Tỷ lệ hệ thống có thể kiểm kê và đối soát ACL/quyền cấp ngoài role |
| **Review remediation completion** | Tỷ lệ quyền bị từ chối trong access review đã được thu hồi thực tế |
| **Authorization test coverage** | Phần tài nguyên/hành động nhạy cảm có kiểm thử âm tính phù hợp |
| **Partial/failed workflow rate** | Tỷ lệ thay đổi chưa xác minh xong tại tất cả hệ đích cần thiết |
| **Policy drift** | Mức lệch giữa policy mong muốn với policy/permission đang áp dụng |

Mỗi chỉ số cần xác định **mẫu số, phạm vi, thời điểm và nguồn đo**. Đặt SLA theo độ nhạy tài nguyên, khả năng hệ đích và mức độ rủi ro; không dùng một ngưỡng cứng cho mọi hệ thống. Không lấy tốc độ xử lý IdP làm thời gian thu hồi toàn bộ quyền nếu ứng dụng khác chưa xác minh.

## 14. Bài thực hành tổng hợp: quyền tài chính đi qua JML

Giả sử hệ thống có HRIS, IdP dùng SSO OIDC, CRM có SCIM, ứng dụng Finance dùng API quản lý role riêng và một pipeline CI sử dụng service principal.

**Nhân viên:** Hương, subjectId EMP-0842. **Role ban đầu:** Support-Agent; được xem và sửa ticket thuộc team Support. **Vai trò mới:** Finance-Analyst; chỉ đọc báo cáo tài chính trong tenant thuộc phạm vi. **Quyền nhạy cảm:** payments:approve cần người duyệt độc lập và giới hạn nghiệp vụ.

### 14.1. Tình huống A — Joiner

HR xác minh ngày bắt đầu, IAM tạo account IdP và provision CRM. Policy cấp Support-Agent; Hương chỉ được đọc ticket team mình. Khi Hương gọi API sửa ticket tenant khác, PEP/PDP từ chối và backend không thực hiện thay đổi. Một yêu cầu export toàn bộ dữ liệu khách hàng phải được chủ dữ liệu duyệt riêng.

**Checklist cần chứng minh:** identity đúng, account map đúng, quyền thực tế khớp role được duyệt, object-level và tenant-level authorization hoạt động, request vượt quyền bị DENY.

### 14.2. Tình huống B — Mover

Hương chuyển sang Finance. IAM tính lại D theo role mới, gỡ Support-Agent và mọi direct grant còn liên quan, cấp Finance-Analyst. Nếu Hương từng có một ACL riêng cho phép customers:export, việc gỡ group Support **không giải quyết ACL**; phải truy vấn và thu hồi grant trực tiếp.

Trong ứng dụng Finance, Hương được phép xem báo cáo tenant mình nhưng không thể duyệt thanh toán. Nếu cần approve, owner phải phê duyệt, kiểm tra SoD và xác định phạm vi, thời hạn. Kiểm thử âm tính phải xác minh Hương không thể dùng API approve chỉ bằng cách đổi role trong body hoặc gọi endpoint trực tiếp.

**Checklist cần chứng minh:** quyền cũ hết hiệu lực, quyền mới đúng mức, SoD đạt chính sách, không còn session/token duy trì quyền cũ ngoài thiết kế.

### 14.3. Tình huống C — Leaver

HR ghi ngày chấm dứt hợp tác. Đến thời điểm hiệu lực, IAM disable IdP, deprovision CRM qua SCIM, vô hiệu role Finance qua API, kiểm tra direct ACL, PAT và session có liên quan. Dashboard Hương sở hữu được chuyển owner. Nếu CRM offline, workflow vẫn ở PARTIAL và owner nhận cảnh báo; không ghi COMPLETED chỉ vì IdP đã khóa.

**Checklist cần chứng minh:** không còn quyền truy cập hợp lệ ở các hệ thuộc phạm vi; token/credential độc lập đã xử lý; dữ liệu/owner bàn giao theo chính sách; readback và log đủ để truy vết.

### 14.4. Bài tập áp dụng

Hãy tự trả lời bốn câu hỏi sau trước khi xem gợi ý:

1. Hương đã bị gỡ nhóm Support nhưng còn ACL customers:export. Mover hoàn tất chưa?
2. Hương có Finance-Analyst, cố sửa số tài khoản ngân hàng của người khác bằng cách thay objectId trong API. Cần kiểm tra ở đâu?
3. IdP bị disable nhưng PAT cũ vẫn gọi API được. Leaver hoàn tất chưa?
4. Một job grant Finance từ Mover phiên bản 7 chạy sau khi Leaver phiên bản 8 đã khóa Hương. Nên xử lý thế nào?

**Gợi ý đối chiếu:**

1. **Chưa.** Phải gỡ ACL và xác minh quyền hiệu lực, không chỉ gỡ group.
2. Kiểm tra quyền **theo object**, tenant và hành động tại backend/API/PEP, không tin objectId hoặc role client gửi.
3. **Chưa.** Phải chặn/revoke PAT theo cơ chế ứng dụng, kiểm tra mọi đường độc lập và lưu bằng chứng.
4. Từ chối hoặc bỏ qua job cũ theo sourceVersion/trạng thái mới nhất, ngăn grant lại và đối soát toàn bộ đích.

## 15. Checklist bàn giao và ghi nhớ

### 15.1. Checklist cuối cho một ứng dụng

| Nhóm | Điều kiện PASS cần có | Owner thường gặp |
| --- | --- | --- |
| **Nguồn danh tính** | Có subjectId ổn định, trạng thái JML đáng tin | HR/sponsor, IAM |
| **Tài nguyên & hành động** | Đủ inventory và phân loại độ nhạy | Product/app owner |
| **Policy** | Có RBAC/ABAC/ACL rõ ràng, default deny, version | IAM governance, chủ dữ liệu |
| **SoD & phê duyệt** | Đặc quyền được duyệt và không tạo xung đột | Chủ nghiệp vụ, kiểm soát |
| **Thực thi** | Backend kiểm tra object, function, tenant, context | App/API owner |
| **Cấp phát** | IdP/SCIM/API/manual grant đồng bộ và có readback | IAM/platform, app owner |
| **Mover** | Quyền cũ đã thu hồi, quyền mới đạt mục tiêu | IAM + manager mới |
| **Leaver** | Account/role/ACL/token độc lập được xử lý và xác minh | IAM + app owner |
| **Service identity** | Có owner, scope, vòng đời và phương án revoke | Platform/workload owner |
| **Review** | Quyền hết hạn, mồ côi, cấp trực tiếp được phát hiện | Data owner, IGA |
| **Kiểm thử** | Có positive/negative tests cho truy cập trái phép | Engineering, QA, Security |
| **Bằng chứng** | Có quyết định, thực thi, readback và ngoại lệ | Audit, Security, IAM |

### 15.2. Quy tắc kết thúc

**Authorization đáng tin** cần đáp ứng đồng thời:

1. Danh tính đã được xác minh và đúng trạng thái vòng đời.
2. Chính sách quyền phù hợp công việc, tài nguyên, thời điểm và bối cảnh.
3. Quyền chỉ được cấp theo kênh có phê duyệt và kiểm soát cần thiết.
4. Mọi hành động quan trọng được thực thi kiểm tra quyền ở hệ thống tin cậy.
5. Khi lý do cấp quyền thay đổi hoặc chấm dứt, toàn bộ đường cấp quyền không hợp lệ được thu hồi.
6. Trạng thái thực tế được đọc lại và có bằng chứng kiểm toán; sai lệch có owner xử lý.

Trong **Joiner–Mover–Leaver**, Joiner cấp **đúng người, đúng quyền và đúng thời điểm**; Mover **tính lại, thu hồi quyền cũ và cấp quyền mới có căn cứ**; Leaver **chặn các đường truy cập không còn hợp lệ**. IdP/SSO giúp xác thực, SCIM/API giúp cấp phát/thu hồi tài khoản, còn RBAC/ABAC/ACL và PEP/PDP quyết định quyền trên từng tài nguyên. Đối soát và kiểm toán giúp phát hiện **quyền truy cập tồn dư** và chứng minh các thay đổi đã có hiệu lực.

Hãy giữ chuỗi kiểm soát: **Nguồn đáng tin → Quyền mong muốn → Phê duyệt → Thực thi trên hệ đích → Kiểm tra hành động thực tế → Thu hồi khi hết căn cứ → Đọc lại và lưu bằng chứng**. Một checklist chỉ thật sự có ý nghĩa khi kết luận PASS dựa trên **quyền hiệu lực đã được kiểm chứng**, không chỉ trên việc gửi lệnh hay bật một tính năng.

