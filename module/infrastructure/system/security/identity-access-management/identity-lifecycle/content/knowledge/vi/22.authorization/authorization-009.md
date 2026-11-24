# Authorization failure: nhận diện, xử lý và ngăn lỗi phân quyền trong vòng đời danh tính IAM

## 1. Authorization failure là gì?

Trong **Identity and Access Management (IAM)**, *authorization* là quá trình quyết định một **chủ thể** (*subject*) có được thực hiện một **hành động** (*action*) trên một **tài nguyên** (*resource*) trong **ngữ cảnh** (*context*) cụ thể hay không. **Authorization failure** là cách gọi chung cho những tình huống liên quan đến quyết định hoặc thực thi phân quyền không đạt yêu cầu. Thuật ngữ này cần được làm rõ trước khi xử lý vì không phải trường hợp nào cũng là một lỗ hổng.

Ví dụ, nhân viên An đăng nhập thành công bằng Single Sign-On (SSO), nhưng API trả HTTP 403 khi An cố xem một báo cáo ngoài phạm vi tổ chức. Nếu An thật sự không được phép đọc báo cáo đó, đây là **quyết định từ chối đúng**. Nếu An đã được cấp quyền hợp lệ mà hệ thống vẫn từ chối, đó là **lỗi cấp quyền/đồng bộ hoặc đánh giá chính sách**. Nghiêm trọng hơn, nếu API cho An đọc báo cáo của tổ chức khác chỉ vì An đăng nhập thành công, đó là **lỗi cho phép sai** có thể gây lộ dữ liệu.

### Ba trường hợp cần phân biệt

| Trường hợp | Expected | Actual | Đánh giá |
| --- | --- | --- | --- |
| **Legitimate denial** — từ chối đúng | DENY | DENY | Kiểm soát phân quyền hoạt động theo chính sách |
| **False denial** — từ chối sai | ALLOW | DENY | Lỗi chức năng hoặc provisioning, có thể làm gián đoạn công việc |
| **Unauthorized allow** — cho phép sai | DENY | ALLOW | Vi phạm bảo mật, có nguy cơ leo thang đặc quyền hoặc lộ dữ liệu |
| **Không xác minh được quyết định** | Chưa xác định | UNKNOWN/ERROR | Không được tự coi là ALLOW hoặc DENY đã được chứng minh |

Ngoài ra, HTTP 403 có thể là **kết quả của một cơ chế bảo vệ đang hoạt động**, không phải bằng chứng hệ thống bị tấn công. Một lỗi kết nối tới policy engine lại là **lỗi kỹ thuật khi quyết định quyền**; hệ thống cần có chính sách xử lý an toàn.

Trong mô hình **Joiner–Mover–Leaver (JML)**, authorization failure có thể xuất hiện khi người mới chưa được cấp quyền, người đổi vai trò vẫn giữ quyền cũ hoặc người đã nghỉ việc còn đường truy cập tồn dư. Bài học liên kết **HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và account reconciliation** để xử lý đủ cả ba dạng sai lệch.

## 2. Phân biệt authentication, authorization và provisioning

Một người có thể đăng nhập thành công nhưng không được phép thực hiện thao tác yêu cầu. Ngược lại, bảng quyền có thể ghi nhận entitlement hợp lệ nhưng người dùng chưa đáp ứng điều kiện xác thực.

| Khái niệm | Câu hỏi chính | Thành phần thường liên quan | Ví dụ |
| --- | --- | --- | --- |
| **Authentication (AuthN)** | Chủ thể là ai và đã chứng minh điều đó ra sao? | Identity Provider (IdP), authenticator, MFA, SSO | An đăng nhập bằng passkey |
| **Authorization (AuthZ)** | Chủ thể được làm gì trên tài nguyên nào? | Policy engine, API, RBAC, ABAC, ACL | An được đọc báo cáo Atlas nhưng không được xóa |
| **Provisioning** | Tài khoản/nhóm/quyền đã được tạo hoặc cập nhật ở đích chưa? | IAM/IGA, SCIM, API quản trị | Tạo account An ở ứng dụng phân tích |
| **Reconciliation** | Trạng thái thực tế có khớp quyền mong muốn không? | IAM, connector, ứng dụng đích, audit | Phát hiện role admin còn tồn tại sau Mover |

**MFA mạnh không tự tạo quyền**. Một nhân viên xác thực bằng security key vẫn không được xem dữ liệu HR nếu không có phê duyệt. **SCIM Create thành công không tự có nghĩa entitlement đã được cấp**, và **SCIM deactivate không đảm bảo token/phiên đã hết hiệu lực**.

### Tại sao phân biệt này quan trọng khi xử lý sự cố?

Nếu đăng nhập thất bại vì tài khoản bị khóa, nhóm phụ trách AuthN cần xem trạng thái IdP. Nếu đăng nhập thành công nhưng API trả 403 do thiếu role, nhóm IAM/IGA hoặc chủ tài nguyên cần xem nguồn quyền. Nếu người dùng có role đúng nhưng API vẫn từ chối do tenant không phù hợp, cần kiểm tra **ngữ cảnh tài nguyên** chứ không vội thêm role rộng hơn.

**Không khắc phục lỗi 403 bằng cách tự động cấp quyền admin**; hành động đó có thể biến một lỗi chức năng thành sự cố đặc quyền.

## 3. Mô hình quyết định và thực thi phân quyền

Một yêu cầu truy cập điển hình cần xác định:

1. **Subject:** nhân viên, đối tác, workload hoặc OAuth client nào đang hành động?
2. **Action:** READ, WRITE, DELETE, APPROVE, ADMIN hay hành động chuyên biệt nào?
3. **Resource:** báo cáo, repository, hóa đơn, hồ sơ nhân sự hoặc API object nào?
4. **Context:** tenant, organization, dự án, thời gian, trạng thái làm việc, mức xác thực, đặc tính thiết bị và môi trường?
5. **Policy/entitlement:** có role, grant, scope, approval và điều kiện nào còn hiệu lực?

Mô hình logic:

~~~text
ALLOW khi và chỉ khi:
    identity_or_client_is_valid
    AND authentication_meets_requirement
    AND access_token_is_valid_for_this_resource_server
    AND required_scope_is_granted_when_applicable
    AND subject_has_current_role_or_entitlement
    AND resource_is_within_authorized_scope
    AND contextual_policy_conditions_are_satisfied
    AND no_higher_priority_deny_applies

NGƯỢC LẠI:
    DENY hoặc báo lỗi xác minh theo chính sách
~~~

Đây là mô hình khái niệm, không phải một biểu thức chuẩn áp dụng cứng cho mọi ứng dụng. Chẳng hạn hệ thống không dùng OAuth không cần kiểm tra OAuth scope; nhưng vẫn phải xác thực chủ thể và kiểm tra quyền cụ thể trên tài nguyên.

### Các thành phần trong kiến trúc policy

| Thành phần | Vai trò | Nguy cơ nếu hoạt động sai |
| --- | --- | --- |
| **Policy Administration Point (PAP)** | Nơi quản lý/quy trình cập nhật policy | Quy tắc sai, phê duyệt thiếu hoặc thay đổi không kiểm soát |
| **Policy Decision Point (PDP)** | Đánh giá yêu cầu và trả quyết định ALLOW/DENY | Bỏ sót thuộc tính, dùng policy cũ |
| **Policy Enforcement Point (PEP)** | Thực thi quyết định tại API/gateway/service | Không chặn request dù PDP trả DENY |
| **Policy Information Point (PIP)** | Cung cấp thuộc tính/quan hệ để quyết định | HR status, organization hoặc entitlement cũ |
| **IAM/IGA** | Quản trị nguồn quyền, phê duyệt, lifecycle | Quyền mục tiêu sai hoặc chưa thu hồi |
| **Resource owner** | Xác nhận ai cần được truy cập tài nguyên | Phê duyệt vượt phạm vi hoặc không rà soát |

PEP phải thực thi ở **đường truy cập thật**. Nếu front-end ẩn nút DELETE nhưng API vẫn chấp nhận request DELETE từ tài khoản chỉ đọc, đó là lỗi **enforcement**, dù giao diện trông đúng.

## 4. Luồng yêu cầu có kiểm tra authorization

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant App as Ứng dụng
    participant IdP as IdP / Authorization Server
    participant API as API / PEP
    participant PDP as PDP / Policy Service
    participant Data as Nguồn entitlement và resource
    U->>App: Đăng nhập hoặc sử dụng phiên hiện có
    App->>IdP: SSO/OIDC khi cần xác thực
    IdP-->>App: Assertion / token đúng giao thức
    U->>App: Yêu cầu xem báo cáo
    App->>API: Request với credential hợp lệ
    API->>API: Kiểm tra token, issuer, audience, thời hạn
    API->>PDP: Subject, action, resource, context
    PDP->>Data: Lấy role, tenant, ownership, trạng thái hiện hành
    Data-->>PDP: Thuộc tính và entitlement có thẩm quyền
    PDP-->>API: ALLOW / DENY / lỗi đánh giá
    alt Được phép
        API-->>App: Trả tài nguyên đã được phép
    else Bị từ chối hoặc không thể xác minh
        API-->>App: Lỗi phù hợp, không trả dữ liệu nhạy cảm
    end
~~~

Trong thực tế, PDP có thể nằm ngay trong ứng dụng và PIP có thể là cache hoặc cơ sở dữ liệu. Không nên coi sơ đồ là yêu cầu bắt buộc phải triển khai microservice riêng. Điều bắt buộc là **quyết định được kiểm chứng, thực thi nhất quán và truy vết được**.

## 5. HTTP 401, 403 và 404: đọc đúng phản hồi

**Không phải mọi authorization failure đều trả 403**, và không phải mọi 403 là lỗi code.

| Trạng thái | Ý nghĩa điển hình | Ví dụ | Hướng điều tra |
| --- | --- | --- | --- |
| **401 Unauthorized** | Thiếu hoặc không có thông tin xác thực hợp lệ cho resource | Access token hết hạn, sai chữ ký, không gửi token | Kiểm tra AuthN/token/issuer/audience và cách phát hành |
| **403 Forbidden** | Server hiểu request nhưng không cho phép truy cập | Thiếu scope, role, tenant, entitlement hoặc bị policy từ chối | Kiểm tra policy và quyền hiệu lực |
| **404 Not Found** | Không tìm thấy tài nguyên hoặc lựa chọn che sự tồn tại tài nguyên | Report ID không tồn tại; hệ thống cố ý không tiết lộ báo cáo ngoài tenant | Kiểm tra resource ownership, tránh lộ dữ liệu |
| **400 Bad Request** | Yêu cầu không hợp lệ | Thiếu ID hoặc tham số sai định dạng | Sửa request; không tự nâng quyền |
| **409 Conflict** | Xung đột trạng thái tài nguyên | Thao tác nghiệp vụ bị xung đột phiên bản | Xử lý transaction/business constraint |
| **429 Too Many Requests** | Hạn chế tốc độ | Quá nhiều yêu cầu API | Điều chỉnh backoff và chính sách rate limiting |
| **5xx** | Server/đường phụ thuộc lỗi | PDP không kết nối được, lỗi hệ thống | Giám sát và xử lý lỗi an toàn; không tự chuyển thành ALLOW |

Tên HTTP **401 Unauthorized** có thể gây hiểu lầm: đây thường là vấn đề **authentication**. **403 Forbidden** thường gần với **authorization denial** hơn. API có thể trả **404** để không tiết lộ tài nguyên không được phép, nhưng vẫn phải thực thi kiểm tra quyền ở backend.

### OAuth Bearer token: thiếu scope

Với API dùng OAuth 2.0 Bearer token, một trường hợp token hợp lệ nhưng không có scope cần thiết có thể dùng **403** và thông tin **insufficient_scope** theo RFC 6750:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="reports", error="insufficient_scope", scope="reports:read"
~~~

Không nên trả lại chi tiết nội bộ như tên nhóm admin bí mật, danh sách role của người khác hoặc bản ghi HR trong message lỗi. Trình bày lỗi cho người dùng vừa đủ để biết cần yêu cầu quyền ở đâu, còn chi tiết chẩn đoán được ghi trong log có phân quyền.

## 6. Bốn loại nguyên nhân chính của authorization failure

Có thể phân loại theo nơi sai lệch phát sinh:

| Nhóm | Ví dụ | Cách xác minh |
| --- | --- | --- |
| **Sai dữ liệu quyền (entitlement drift)** | IAM đã duyệt role nhưng ứng dụng chưa cấp; hoặc quyền cũ chưa xóa | So sánh expected với observed ở IdP/ứng dụng |
| **Sai chính sách (policy error)** | Quy tắc cho phép quá rộng, điều kiện deny bị bỏ qua | Kiểm thử policy với bộ case có allow/deny |
| **Sai thực thi (enforcement error)** | API thiếu object-level check, route admin bỏ qua middleware | Kiểm thử ở API và đường gọi backend |
| **Sai ngữ cảnh/xác thực (context/identity error)** | Sai tenant, identity correlation nhầm, token sai audience hoặc claim cũ | Kiểm tra ID ổn định, nguồn thuộc tính và độ mới |

Trong nhiều sự cố, có hơn một nguyên nhân. Ví dụ ứng dụng có **role mapping sai** và **API không kiểm tra tenant**, khiến một thành viên của nhóm A truy cập được dữ liệu B.

Một bản ghi lỗi chỉ ghi `access_denied` không đủ để giải thích nguyên nhân. Cần lưu **policy version, target resource, action, subject, nguyên nhân từ chối ở mức an toàn và correlation ID**.

## 7. RBAC: lỗi role và quyền thừa

**Role-Based Access Control (RBAC)** tổ chức quyền dựa trên role. Role có thể được cấp bởi nhóm IdP, cấu hình IAM/IGA hoặc hệ thống ứng dụng. Một role **không nhất thiết tương đương** ở mọi hệ thống.

Ví dụ:

| Chủ thể | Role được duyệt | Hành động | Expected |
| --- | --- | --- | --- |
| An | ReportReader | READ report thuộc dự án của An | ALLOW |
| An | ReportReader | DELETE report | DENY |
| Bình | ReportEditor | UPDATE report đúng dự án | ALLOW theo điều kiện bổ sung |
| Bình | ReportEditor | READ report dự án khác | DENY |
| Quản trị viên hệ thống | SystemAdmin | Thay đổi cấu hình trong scope được phân công | ALLOW khi thỏa chính sách đặc quyền |

Các lỗi RBAC điển hình:

- Role được gán nhầm vì **group mapping** của SCIM/IdP không chính xác.
- Role quá rộng như `admin` được dùng để giải quyết lỗi “thiếu quyền” một cách vội vàng.
- Role lồng nhau hoặc **kế thừa** tạo quyền ngoài dự tính.
- Role cũ không được thu hồi khi Mover, dẫn tới **privilege accumulation**.
- Ứng dụng sử dụng **role lấy từ client request** thay vì nguồn tin cậy.
- Role được kiểm tra ở giao diện nhưng **không được thực thi tại API**.

**Một role chỉ có ý nghĩa khi xác định tài nguyên và phạm vi.** `ProjectAdmin` của dự án Atlas không mặc nhiên được quản trị dự án Nova hoặc tenant khác.

## 8. ABAC: thuộc tính sai, cũ hoặc thiếu

**Attribute-Based Access Control (ABAC)** quyết định quyền từ thuộc tính chủ thể, tài nguyên, hành động và ngữ cảnh. Các thuộc tính cần có **nguồn có thẩm quyền theo từng trường**.

| Thuộc tính | Nguồn gợi ý | Nguy cơ |
| --- | --- | --- |
| employmentStatus | HRIS/nguồn bảo trợ | Người đã Leaver vẫn được coi ACTIVE |
| organizationId | Nguồn organization membership đáng tin | Truy cập dữ liệu sai pháp nhân/tenant |
| projectAssignment | Hệ thống dự án có thẩm quyền | Mover giữ quyền dự án cũ |
| resourceClassification | Catalog tài nguyên/chủ dữ liệu | Cho phép xuất dữ liệu nhạy cảm sai chính sách |
| approvalUntil | IGA/quy trình phê duyệt | Quyền tạm thời không hết hạn |
| authenticationAssurance | IdP/verifier theo hợp đồng tin cậy | Cho phép thao tác đặc quyền khi chưa đủ MFA |
| deviceTrust | Nền tảng quản trị thiết bị được tin cậy | Dựa vào tín hiệu tự khai hoặc quá hạn |

**Thiếu thuộc tính** không đồng nghĩa thuộc tính có giá trị an toàn. Nếu API không xác định được `organizationId` của request, không nên tự gán organization mặc định hoặc cho phép truy cập mọi tenant. Khi nguồn policy không khả dụng, hệ thống cần tuân theo quy tắc lỗi đã được phê duyệt, ưu tiên bảo vệ tài nguyên nhạy cảm.

### Ví dụ điều kiện ABAC

~~~text
ALLOW report READ IF:
    identity.employmentStatus == ACTIVE
    AND identity.organizationId == report.organizationId
    AND report.projectId IN identity.approvedProjects
    AND identity.hasRole("Analyst", report.projectId)
    AND report.classification <= identity.clearance
    AND currentTime < identity.assignmentExpiry
    AND noExplicitDenyApplies
OTHERWISE DENY
~~~

Ký hiệu trên mang tính minh họa. Không nên dùng so sánh thứ tự chuỗi cho nhãn phân loại nếu hệ thống chưa định nghĩa **thứ bậc dữ liệu rõ ràng**. Các thuộc tính cần được cập nhật khi **Joiner/Mover/Leaver** và phải có cơ chế vô hiệu cache khi quyền cần thay đổi nhanh.

## 9. ACL và quan hệ giữa chủ thể với tài nguyên

Ngoài RBAC/ABAC, nhiều ứng dụng dùng **Access Control List (ACL)**, chủ sở hữu hoặc **Relationship-Based Access Control (ReBAC)**.

Ví dụ: tài liệu có thể được chia sẻ trực tiếp cho An dù An không ở nhóm dự án. Khi An chuyển nhóm, xóa group membership chưa chắc xóa **ACL trực tiếp**. Nếu đánh giá authorization chỉ dựa trên nhóm IdP, IAM có thể bỏ sót quyền tồn dư.

Các trường hợp cần kiểm tra:

- **Owner:** chủ sở hữu có quyền thay đổi tài nguyên, chia sẻ hay chuyển owner không?
- **Direct share:** tài khoản được chia sẻ trực tiếp, có hạn và lý do không?
- **Inherited access:** quyền kế thừa từ thư mục, nhóm cha hoặc organization nào?
- **Group nesting:** nhóm lồng nhau có làm mở thêm quyền ngoài expected không?
- **Delegated access:** người được ủy quyền có thể truy cập đúng scope và thời hạn không?
- **Cross-tenant sharing:** người dùng bên ngoài có được tổ chức sở hữu tài nguyên chấp thuận không?

**Đọc được danh sách group không đủ để kết luận quyền hiệu lực** nếu ứng dụng còn những đường quyền khác. Cần đối soát đúng cơ chế ACL/ownership mà ứng dụng thực thi.

## 10. Object-level và function-level authorization

Hai lớp kiểm tra rất dễ bị thiếu:

1. **Function-level authorization:** chủ thể có được gọi chức năng/endpoint đó không? Ví dụ nhân viên thường không được gọi API quản lý role.
2. **Object-level authorization:** chủ thể có được thực hiện hành động đó **trên đối tượng cụ thể** không? Ví dụ Analyst chỉ được đọc báo cáo thuộc dự án mình tham gia.

Lỗi phổ biến là một API kiểm tra “đã đăng nhập” rồi cho phép đọc object theo ID mà không so sánh với quyền của người gọi. Điều này thường được nhắc đến trong các chủ đề **IDOR (Insecure Direct Object Reference)** hoặc **Broken Object Level Authorization (BOLA)**.

Ví dụ về một đường API hợp lệ:

~~~http
GET /api/organizations/org-a/reports/42 HTTP/1.1
Host: reports.example.invalid
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
~~~

**org-a** và **42** do client đưa vào chỉ là **định danh tài nguyên được yêu cầu**, không phải bằng chứng có quyền. API phải xác nhận report 42 thật sự thuộc org-a và chủ thể có quan hệ truy cập hợp lệ với report đó. Thay đổi ID trong URL không được làm phát sinh quyền.

### Ma trận quyết định minh họa

| Identity | Chức năng | Đối tượng | Kết quả mong đợi |
| --- | --- | --- | --- |
| Analyst A | READ report | Report thuộc dự án A | ALLOW nếu đủ điều kiện |
| Analyst A | READ report | Report thuộc dự án B | DENY |
| Analyst A | DELETE report | Report thuộc dự án A | DENY nếu không có quyền xóa |
| ProjectAdmin A | UPDATE access | Chỉ project A | ALLOW nếu có quyền quản lý và step-up |
| ProjectAdmin A | UPDATE access | Project B | DENY |
| Identity đã Leaver | READ report | Bất kỳ report chỉ dựa vào employment đã hết | DENY |

Tổ chức nên kiểm thử **cả tình huống được phép và bị từ chối**, thay vì chỉ kiểm tra API hoạt động khi dùng account admin.

## 11. Multi-tenant isolation: lỗi phân quyền xuyên tổ chức

Trong hệ thống đa tổ chức, **tenant isolation** là giới hạn quan trọng của authorization. Một user có thể thuộc nhiều organization, nhưng membership và vai trò ở mỗi organization thường khác nhau.

Ví dụ, An là Analyst tại **org-a**, còn Bình là Analyst tại **org-b**. Nếu token của An có scope `reports:read`, điều đó **không cấp quyền** xem báo cáo của org-b. API phải:

1. Xác thực token đúng issuer và audience.
2. Lấy subject ổn định từ nguồn tin cậy, không lấy `userId` do body tự khai.
3. Xác định tenant mà tài nguyên thật sự thuộc về ở backend.
4. Kiểm tra membership/role/entitlement **trong chính tenant đó**.
5. Áp dụng thuộc tính tài nguyên và điều kiện ABAC bổ sung.
6. Trả DENY/404 phù hợp nếu một điều kiện không đạt.

**Không dùng một header như `X-Tenant-Id` hoặc một query parameter làm bằng chứng ủy quyền.** Chúng có thể giúp chọn ngữ cảnh được yêu cầu, nhưng phải được so sánh với danh tính và quyền đã được xác minh.

Nếu người dùng thuộc cả A và B, không nên lấy role admin ở A rồi mặc định áp dụng cho B. Một **grant có scope đúng** vẫn cần được giới hạn theo tenant/tài nguyên.

## 12. OAuth 2.0, OIDC, scope và authorization failure

**OAuth 2.0** hỗ trợ client nhận token được giới hạn bởi grant, audience/resource và scope theo khả năng authorization server. **OpenID Connect (OIDC)** hỗ trợ xác thực người dùng và truyền kết quả tới ứng dụng.

Với resource server nhận access token, các kiểm tra quan trọng:

| Kiểm tra | Lý do |
| --- | --- |
| Issuer tin cậy | Token do nguồn được phê duyệt phát hành |
| Signature hoặc introspection | Bằng chứng token hợp lệ theo mô hình đã chọn |
| Audience/resource binding | Token thực sự dành cho API này |
| Expiry/not-before khi áp dụng | Token nằm trong khoảng hiệu lực |
| Scope | Token có khả năng API yêu cầu hay không |
| Subject/client identity | Biết ai đang gọi và theo grant nào |
| Role/entitlement/tenant | Có quyền trên tài nguyên cụ thể không |
| Revocation/freshness | Token, grant hoặc quyền đã bị thu hồi chưa |

**ID token không được dùng thay access token cho API**. Scope `openid` và các scope hồ sơ `profile`/`email` không tự cấp quyền đọc dữ liệu nghiệp vụ. Access token có `reports:read` cũng không chứng minh người dùng được xem mọi báo cáo.

Một token cấp hôm qua có thể chứa role cũ khi người dùng đã Mover. Nếu API chỉ kiểm tra chữ ký và `exp` của JWT offline, token đó có thể còn hiệu lực cho tới khi hết hạn. Khi cần thu hồi sớm, có thể dùng **token introspection, denylist, security epoch, policy recheck hoặc TTL phù hợp** tùy kiến trúc.

## 13. SSO, MFA và yêu cầu xác thực tăng cường

**SSO** giúp người dùng sử dụng kết quả đăng nhập từ IdP tại nhiều ứng dụng. **MFA** nâng mức bảo đảm chủ thể kiểm soát danh tính. Nhưng việc đã SSO/MFA thành công không làm người dùng tự có quyền trên tài nguyên.

Một số hành động nhạy cảm còn yêu cầu **step-up authentication**:

| Hành động | Điều kiện xác thực minh họa | Authorization vẫn cần kiểm tra |
| --- | --- | --- |
| Xem dashboard thông thường | Phiên SSO hợp lệ | Role/tenant/dự án |
| Xuất dữ liệu nhạy cảm | MFA đủ độ mới theo chính sách | Quyền export và phân loại dữ liệu |
| Thay đổi quyền người khác | Phương thức chống phishing khi chính sách yêu cầu | Role quản trị, phạm vi tài nguyên, phê duyệt |
| Cấp quyền cloud production | Xác thực tăng cường và phiên đủ mới | Tài khoản đặc quyền, resource scope, SoD |

Với OIDC, các claim như `acr`, `amr`, `auth_time` có thể hỗ trợ đánh giá **mức đảm bảo và độ mới**, nếu IdP và ứng dụng thống nhất ngữ nghĩa. **Không tự tin bất kỳ chuỗi `acr` nào cũng chứng minh WebAuthn hoặc MFA đúng yêu cầu.**

Nếu một hành động cần step-up mà phiên chưa đạt, ứng dụng phải **từ chối hoặc khởi động quy trình xác thực tăng cường** theo giao thức, sau đó kiểm chứng kết quả. Không nên âm thầm hạ yêu cầu hoặc nâng entitlement để vượt lỗi.

## 14. Quyền được phê duyệt và quyền đang có: expected vs observed

Trong quản lý vòng đời danh tính, phải tách:

- **Expected access:** quyền IAM/IGA tính từ HRIS, vai trò, assignment, owner approval và chính sách hiện hành.
- **Observed access:** account, nhóm, role, ACL, session và entitlement đang thực sự tồn tại ở hệ thống đích.
- **Effective access:** quyết định mà API/resource server thực thi đối với subject, action, resource, context ở thời điểm kiểm tra.

Ví dụ:

| Hạng mục | Expected | Observed | Hậu quả |
| --- | --- | --- | --- |
| Nhân viên mới có quyền đọc nhóm Atlas | ALLOW READ Atlas | Chưa có role ở SaaS | False denial, gián đoạn onboarding |
| Nhân viên đổi sang Nova | DENY Atlas | ACL trực tiếp Atlas còn tồn tại | Unauthorized allow, quyền tồn dư |
| Leaver không được truy cập | DENY mọi quyền từ employment đã kết thúc | IdP disabled nhưng PAT còn dùng được | Unauthorized allow qua đường riêng |
| Quản trị viên đúng role | ALLOW admin theo scope | API chỉ đọc claim cũ, không xác minh thời điểm | Có thể false allow hoặc false deny |

**Một lần provisioning success không bằng effective access verified.** SCIM có thể đồng bộ User/Group, nhưng quyền cục bộ ở ứng dụng hoặc token vẫn khác expected. Đối soát cần đọc từ nguồn và điểm thực thi phù hợp.

## 15. Authorization failure trong Joiner lifecycle

**Joiner** thường gồm xác minh danh tính, tạo account, đăng ký authenticator, cấp quyền và nghiệm thu. Những lỗi điển hình:

1. **Missing account:** hệ thống đích chưa tạo user, khiến người mới không có đường truy cập.
2. **Missing entitlement:** user có account nhưng thiếu group/role bắt buộc.
3. **Overprivileged default:** nhóm mặc định vô tình cấp `admin` hoặc quyền dữ liệu ngoài nhiệm vụ.
4. **Wrong identity link:** tài khoản cũ được liên kết nhầm sang người mới do email giống nhau.
5. **Premature access:** tạo account trước ngày vào làm nhưng đã active hoặc được cấp quyền nhạy cảm.
6. **Insufficient assurance:** app cho phép thao tác đặc quyền dù MFA chưa được đăng ký theo chính sách.

### Cách nghiệm thu

~~~text
Joiner access verification:
    validate authoritative employment and start date
    verify person -> identity -> account mapping
    verify required applications exist at targets
    verify expected roles and entitlements
    test permitted action on approved test resource
    test denied action outside role / tenant scope
    verify authentication policy when required
    record evidence and unresolved exceptions
~~~

**Kiểm thử cho phép và từ chối** đều cần thiết. Nếu chỉ thử xem nhân viên đăng nhập được hay không, hệ thống có thể bỏ sót một role admin vô tình được cấp. Nếu quyền bắt buộc chưa có, không nên giải quyết bằng nhóm có đặc quyền rộng hơn.

## 16. Authorization failure trong Mover lifecycle

**Mover** là lúc nhân viên đổi vai trò, phòng ban, dự án hoặc organization. Một quy trình Mover đúng thường gồm **cấp quyền mới và thu hồi quyền cũ**, có xét thời điểm hiệu lực và ngoại lệ chuyển giao.

Ví dụ, Lan chuyển từ Dự án Atlas sang Nova:

| Quyền | Trước Mover | Sau Mover mong muốn | Rủi ro nếu chỉ cộng quyền |
| --- | --- | --- | --- |
| READ Atlas | ALLOW | DENY | Lan tiếp tục đọc dữ liệu dự án cũ |
| WRITE Atlas | Tùy role trước | DENY | Quyền sửa trái nhiệm vụ tồn dư |
| READ Nova | DENY | ALLOW | Lan không làm được việc nếu chưa cấp |
| ADMIN Nova | DENY | DENY trừ khi được phê duyệt | Auto-map vai trò sai có thể nâng quyền |

Các nguồn sai lệch:

- Sự kiện HR/assignment tới muộn hoặc bị xử lý sai thứ tự.
- IdP đã cập nhật group nhưng SaaS còn role cục bộ.
- ACL trực tiếp, quyền chia sẻ hay nhóm lồng nhau chưa bị thu hồi.
- JWT access token còn claim role cũ tới khi hết hạn.
- Ngoại lệ quyền bàn giao không có expiration.

**Không coi thêm quyền Nova thành công là Mover hoàn tất** khi Atlas vẫn truy cập được. Cần so sánh toàn bộ **expected vs observed** và quyền hiệu lực.

## 17. Authorization failure trong Leaver lifecycle

**Leaver** xác định quan hệ lao động hoặc bảo trợ đã hết hiệu lực. Authorization failure đặc biệt nguy hiểm khi quyền vẫn còn sau mốc thu hồi:

- **IdP disabled nhưng ứng dụng có local account** còn hoạt động.
- **SCIM active=false** nhưng hệ thống không chấm dứt session/PAT.
- **Refresh token** tiếp tục cấp access token nếu grant chưa bị revoke.
- **JWT access token** còn hiệu lực theo chữ ký/exp vì API không kiểm tra trạng thái thu hồi.
- **Direct ACL, ownership hoặc shared credential** chưa được thu hồi.
- **Service account** có secret do người nghỉ việc từng biết, owner chưa được chuyển.

Quy trình cần:

1. Xác minh sự kiện Leaver từ **nguồn có thẩm quyền** và mốc cắt quyền.
2. Liên kết đúng identity, account, tenant, client và các quan hệ việc làm liên quan.
3. Chặn phát hành credential/phiên mới.
4. Thu hồi quyền IdP, SCIM, ứng dụng, token/session và credential cục bộ theo cơ chế thực tế.
5. Đọc lại trạng thái tại các hệ thống đích, kiểm tra không còn quyền trên tài nguyên thuộc phạm vi phải thu hồi.
6. Giữ trạng thái **PARTIAL/BLOCKED** nếu một hệ thống bắt buộc chưa được xác minh.

Nếu người dùng còn một hợp đồng hợp lệ với organization B, việc hợp đồng A kết thúc không luôn có nghĩa vô hiệu toàn bộ identity dùng chung. Phải **tính lại quyền theo quan hệ còn hiệu lực** để vừa thu hồi A vừa không phá truy cập hợp lệ của B.

## 18. Account reconciliation và độ mới của chính sách

Thực tế, dữ liệu giữa HRIS, IdP, IGA và ứng dụng **không cập nhật đồng thời**. Điều này tạo khoảng trễ dẫn tới cả false denial và unauthorized allow.

| Sai lệch | Nguồn có thể gây ra | Kiểm soát |
| --- | --- | --- |
| HR đã chuyển vai trò nhưng token còn role cũ | JWT được phát hành trước Mover | Recheck policy/token epoch hoặc TTL thích hợp |
| IAM đã duyệt nhưng SCIM chưa cập nhật group | Connector timeout hoặc queue chậm | Retry idempotent, readback target |
| PDP dùng cache entitlement cũ | Cache không được invalidation | TTL theo rủi ro, event-driven invalidation |
| IdP có nhiều account liên kết nhầm | Email bị tái sử dụng | Identity correlation theo ID đáng tin |
| App có quyền trực tiếp ngoài nhóm | ACL/owner assignment cục bộ | Reconciliation ở app, không chỉ group IdP |
| Sự kiện HR cũ ghi đè sự kiện mới | Xử lý bất đồng bộ thiếu version | Source version và effective time |

**Source of truth thường là theo từng thuộc tính.** HRIS có thẩm quyền xác nhận employment; hệ thống dự án có thể quản trị assignment; IAM/IGA quản lý phê duyệt; ứng dụng là nơi cho biết account/ACL thực tế. Không đơn giản chọn record có `updatedAt` mới nhất từ mọi nguồn mà bỏ qua thẩm quyền và ngày hiệu lực.

Khi thấy 403, xác định **policy được đánh giá trên snapshot lúc nào**, không chỉ hỏi “người dùng có role không”. Khi thấy người Leaver vẫn truy cập được, xác định **đường quyền thực tế đang được thực thi** và độ trễ đã vượt tiêu chuẩn hay chưa.

## 19. Fail-closed, deny-by-default và lỗi khi PDP không sẵn sàng

**Deny-by-default** nghĩa là không cấp quyền nếu không có quy tắc phù hợp cho phép. **Fail-closed** nghĩa là khi không thể xác minh điều kiện bảo mật bắt buộc, hệ thống không chuyển lỗi thành quyết định ALLOW.

Ví dụ:

~~~text
decision = policyEngine.evaluate(subject, action, resource, context)

if decision == ALLOW:
    enforceAllowWithObligations()
else if decision == DENY:
    enforceDeny()
else if decision == ERROR or decision == INDETERMINATE:
    doNotGrantAccess()
    alertAndRecordOperationalFailure()
~~~

Một lỗi kết nối tới PDP có thể được phản hồi cho client dưới dạng **503 Service Unavailable**, thay vì giả lập rằng policy đã DENY và trả 403, tùy contract. Điều quan trọng là **không trả tài nguyên khi chưa có quyết định hợp lệ**.

Một số hệ thống cần khả năng hoạt động offline hoặc sẵn sàng cao; có thể dùng **policy cache đã ký/được kiểm soát và thời hạn phù hợp** cho những thao tác nhất định. Nhưng phải đánh giá rõ ảnh hưởng khi quyền vừa bị thu hồi, đặc biệt với API nhạy cảm. Không biến “PDP lỗi thì allow tất cả” thành cơ chế dự phòng.

### Explicit deny và conflict

Nếu nhiều chính sách áp dụng đồng thời, cần định nghĩa **thứ tự ưu tiên** và cách kết hợp quyết định: deny-overrides, permit-overrides hoặc quy tắc đặc thù được duyệt. Khi có lệnh **thu hồi đặc quyền khẩn cấp**, chính sách không được để một role khác âm thầm ghi đè quyết định deny nếu thiết kế yêu cầu deny ưu tiên.

## 20. Lỗi phân quyền ở Java/Spring Security: kiểm soát ở đâu?

Trong ứng dụng Java sử dụng **Spring Security**, có thể kiểm tra **scope/authority** ở method hoặc request và kiểm tra thêm **quyền theo đối tượng** tại lớp service/policy. Ví dụ **minh họa**, giả sử ứng dụng đã cấu hình OAuth2 Resource Server và bật method security:

~~~java
@Service
public class ReportService {
    private final ReportRepository reports;
    private final ReportAccessPolicy accessPolicy;

    public ReportService(
            ReportRepository reports,
            ReportAccessPolicy accessPolicy) {
        this.reports = reports;
        this.accessPolicy = accessPolicy;
    }

    @PreAuthorize("hasAuthority('SCOPE_reports:read')")
    public ReportDto readReport(UUID reportId, Authentication auth) {
        Report report = reports.findById(reportId)
                .orElseThrow(ReportNotFoundException::new);

        // Kiểm tra quyền trên chính đối tượng được tải từ backend.
        if (!accessPolicy.canRead(auth, report)) {
            throw new AccessDeniedException("Access denied");
        }

        return ReportDto.from(report);
    }
}
~~~

Các lưu ý quan trọng:

- Cấu hình `@EnableMethodSecurity` và hệ thống xác thực Resource Server phải được thiết lập đúng; snippet không phải ứng dụng chạy độc lập.
- Quy ước authority `SCOPE_reports:read` phụ thuộc **mapping JWT/scope** của cấu hình Spring Security; không phải mọi issuer trả cùng claim hay tiền tố.
- `accessPolicy.canRead` phải xác minh **subject, tenant, owner, entitlement, trạng thái làm việc và điều kiện thực tế** từ nguồn đáng tin; không tin tenant do client tự khai.
- Một method có thể được gọi qua những đường khác ngoài HTTP; đặt kiểm tra quyền ở **service/policy layer** giúp giảm bỏ sót khi có background job hoặc API khác.
- **Spring method security có thể dùng proxy**; cần chú ý self-invocation và đường gọi nội bộ có thể không qua interceptor như mong đợi. Những thao tác nhạy cảm phải có kiểm tra quyền không thể bị bỏ qua tại boundary.
- `ReportNotFoundException` và `AccessDeniedException` cần được ánh xạ thành phản hồi phù hợp, không để lộ dữ liệu nội bộ.

### Ví dụ phản ví dụ cần tránh

~~~java
// KHÔNG AN TOÀN nếu chỉ kiểm tra đã đăng nhập:
public ReportDto readReport(UUID reportId, Authentication auth) {
    if (auth == null || !auth.isAuthenticated()) {
        throw new AccessDeniedException("Login required");
    }
    return ReportDto.from(reports.findById(reportId).orElseThrow());
}
~~~

Đoạn code trên **không kiểm tra người gọi có quyền với reportId hay không**. Một phiên đăng nhập hợp lệ không đủ để quyết định quyền trên báo cáo thuộc dự án hoặc tenant khác. Các mã trên mang tính giáo dục; lớp policy thật cần được thiết kế và kiểm thử theo resource model của ứng dụng.

## 21. Kiểm thử authorization: bắt cả false deny lẫn false allow

Một bộ kiểm thử phân quyền phải kiểm tra cả **positive** và **negative** case:

| Case | Chủ thể / tình huống | Expected |
| --- | --- | --- |
| T01 | Analyst A đọc report của project A | ALLOW |
| T02 | Analyst A đọc report của project B | DENY |
| T03 | Analyst A DELETE report trong project A | DENY nếu chỉ có quyền đọc |
| T04 | ProjectAdmin A thay permission của project B | DENY |
| T05 | Token đúng chữ ký nhưng sai audience | Không được xác thực cho API này |
| T06 | Token hợp lệ nhưng thiếu scope | DENY/insufficient_scope |
| T07 | Tham số tenant bị đổi trong request | Không thay được quyền đã xác minh |
| T08 | Mover vừa mất role Atlas nhưng còn token cũ | DENY Atlas theo SLA/policy |
| T09 | Leaver có local session/PAT còn hạn | Chặn theo yêu cầu Leaver |
| T10 | PDP timeout | Không được ALLOW do lỗi; thông báo vận hành phù hợp |
| T11 | Account có ACL trực tiếp ngoài role | Quyết định dựa trên mọi đường quyền hợp lệ |
| T12 | Workload client A dùng token cho API B | DENY khi audience/scope không đúng |
| T13 | User có quyền đọc nhưng chưa đáp ứng step-up | DENY hoặc STEP_UP_REQUIRED |
| T14 | User thuộc hai tenant với role khác nhau | Quyết định độc lập theo mỗi tenant |

**Không chỉ chạy test bằng account admin.** Cần dùng tài nguyên kiểm thử và nhiều nhóm chủ thể với quyền khác nhau. Test phải đảm bảo người không có quyền không thể đọc/xuất dữ liệu bằng đường khác như API mobile, batch endpoint hoặc file download đã được URL hóa.

### Policy test như một bảng quyết định

~~~text
assertAllow(analystA, READ, reportA)
assertDeny(analystA, READ, reportB)
assertDeny(analystA, DELETE, reportA)
assertDeny(projectAdminA, UPDATE_ACL, projectB)
assertDeny(leaverIdentity, READ, reportA)
assertNoAllowWhenPolicyUnavailable()
~~~

Một test chỉ chứng minh policy logic đạt yêu cầu trên dữ liệu giả lập. Cần thêm **integration test tại PEP/resource server**, vì lỗi thực thi có thể khiến policy đúng nhưng request vẫn đi vòng qua lớp kiểm tra.

## 22. Kiểm toán, telemetry và quyền riêng tư

Để điều tra một authorization failure, log nên liên kết **authentication → policy decision → enforcement → resource request → lifecycle event**.

Ví dụ JSON **minh họa**, không phải schema bắt buộc:

~~~json
{
  "eventId": "authz-event-2026-091",
  "correlationId": "req-40182",
  "identityRef": "iam-id-482",
  "clientRef": "reports-web",
  "resourceRef": "org-a/report-42",
  "action": "READ",
  "expectedTenant": "org-a",
  "observedTenant": "org-a",
  "policyVersion": "authz-v17",
  "entitlementVersion": 42,
  "authenticationState": "VALID",
  "tokenAudienceCheck": "PASSED",
  "scopeCheck": "PASSED",
  "resourceOwnershipCheck": "FAILED",
  "decision": "DENY",
  "enforcement": "BLOCKED",
  "occurredAt": "2026-11-23T09:30:00+07:00"
}
~~~

Log nên phân biệt **decision** từ PDP với **enforcement** ở PEP. Nếu PDP trả DENY mà API vẫn trả dữ liệu, đây là lỗi thực thi nghiêm trọng cần được phát hiện.

Không đưa **access token, refresh token, cookie, client secret, mật khẩu, seed OTP, dữ liệu hồ sơ nhạy cảm** vào log. Có thể lưu mã tham chiếu, token identifier hoặc hash được quản lý phù hợp. Log phân quyền thường tiết lộ cấu trúc tổ chức, resource và role nên cần **phân quyền đọc, tối thiểu hóa và thời gian lưu**.

Các trường quan trọng:

- Subject/client/issuer/account reference và kết quả identity correlation.
- Action, resource type, resource ID, tenant và phạm vi yêu cầu.
- Policy ID/version, nguồn entitlement/attribute và độ mới.
- Authentication/assurance và scope check khi liên quan.
- Decision, nguyên nhân từ chối an toàn, response status và enforcement result.
- Request timestamp, correlation ID, service/node và trạng thái phụ thuộc.
- Event HR Joiner/Mover/Leaver hoặc phê duyệt đặc biệt tạo nên quyết định.

## 23. Giám sát các chỉ số authorization failure

| Chỉ số | Mục tiêu |
| --- | --- |
| **Unexpected deny rate** | Phát hiện người đủ quyền nhưng không làm được việc |
| **Unauthorized allow findings** | Ghi nhận sai lệch nghiêm trọng phát hiện qua test/audit |
| **Policy evaluation errors** | Số lần PDP lỗi/không xác định, nhất là hành động nhạy cảm |
| **Cross-tenant access denials** | Theo dõi yêu cầu không đúng tenant, phân biệt lỗi ứng dụng và hành vi đáng ngờ |
| **Missing entitlement after Joiner** | Đo khoảng trống provisioning |
| **Stale entitlement after Mover** | Tìm quyền cũ không thu hồi |
| **Residual access after Leaver** | Tìm account, token, session, ACL vẫn có thể dùng |
| **Time to verified remediation** | Thời gian từ phát hiện tới lúc đọc lại target và xác minh |
| **Authorization coverage** | Tỷ lệ endpoint/operation có PEP và policy test |
| **Unverified target ratio** | Đích không thể chứng minh quyền hiệu lực do giới hạn connector |

**Nhiều 403 không luôn là dấu hiệu xấu**: có thể hệ thống đang từ chối đúng nhiều request không hợp lệ. Ngược lại, **không có 403** không chứng minh an toàn nếu API bỏ qua authorization.

Các KPI nên được phân loại theo **ứng dụng, tenant, mức nhạy cảm và loại danh tính**. Một tỷ lệ tổng thể đẹp có thể che lấp một endpoint quản trị chưa có kiểm tra quyền.

## 24. Quy trình ứng phó khi phát hiện cho phép truy cập sai

**Unauthorized allow** cần được xử lý như một vấn đề bảo mật có thể ảnh hưởng dữ liệu; mức ưu tiên phụ thuộc tài nguyên, phạm vi và bằng chứng thực tế.

~~~mermaid
flowchart TD
    A["Phát hiện authorization anomaly"] --> B["Xác định subject, action, resource, tenant"]
    B --> C{"False deny hay unauthorized allow?"}
    C -->|"False deny"| D["Kiểm tra nguồn entitlement, policy, provisioning"]
    D --> E["Sửa dữ liệu/logic theo phê duyệt, đọc lại"]
    C -->|"Unauthorized allow"| F["Chặn đường quyền không hợp lệ theo quy trình"]
    F --> G["Điều tra API, PEP/PDP, token, session, ACL"]
    G --> H["Khắc phục policy/enforcement và quyền tồn dư"]
    H --> I["Kiểm thử allow/deny, đối soát mọi target liên quan"]
    E --> I
    I --> J{"Bằng chứng xác minh đạt?"}
    J -->|"Không"| K["Giữ case mở, owner và deadline"]
    K --> I
    J -->|"Có"| L["Audit, đóng case và bài học phòng ngừa"]
~~~

### Các bước ưu tiên

1. **Xác nhận phạm vi:** token nào, account nào, endpoint nào, tài nguyên nào, tenant nào và khoảng thời gian nào bị ảnh hưởng.
2. **Chặn tác động tiếp diễn:** thu hồi quyền không hợp lệ, vô hiệu đường truy cập hoặc áp dụng biện pháp cô lập theo mức rủi ro đã được ủy quyền.
3. **Giữ chứng cứ:** thu thập log request, policy version, trạng thái HR, grant/role/ACL và hành vi truy cập trong giới hạn quyền riêng tư.
4. **Tìm nguyên nhân gốc:** mapping sai, thiếu object-level check, stale JWT, ACL tồn dư, lỗi định danh hoặc policy quá rộng.
5. **Khắc phục:** sửa enforcement, policy hoặc dữ liệu nguồn; không chỉ đổi tên role hay che nút UI.
6. **Kiểm thử hồi quy:** có cả case được phép, bị từ chối, xuyên tenant, session/token cũ và đường API phụ.
7. **Đối soát:** xác nhận mọi hệ thống bắt buộc áp dụng và các credential/tài nguyên liên quan đã được bảo vệ.
8. **Báo cáo và cải tiến:** ghi mức ảnh hưởng, biện pháp và owner; cải thiện policy test, alert và quy trình JML.

Nếu bằng chứng không đầy đủ, **không khẳng định chắc chắn không có dữ liệu bị truy cập**. Trạng thái điều tra phải phản ánh giới hạn của log và dữ liệu hiện có.

## 25. Tình huống thực hành: chuyển dự án nhưng API vẫn cho quyền cũ

**Bối cảnh:** Tại doanh nghiệp, nhân viên Hòa đang dùng SSO qua IdP và truy cập ứng dụng báo cáo bằng access token JWT. Hòa được chuyển từ dự án **Atlas** sang **Nova** lúc 09:00 ngày 23/11. HRIS và hệ thống phân công dự án đã xác nhận thay đổi; IAM tính quyền mục tiêu:

- Hòa được **READ báo cáo Nova**.
- Hòa không còn được **READ báo cáo Atlas**.
- Hòa không được thực hiện **DELETE** báo cáo ở cả hai dự án.

Ở thời điểm 09:05, account vẫn có thể mở báo cáo Atlas dù nhóm IdP đã chuyển sang Nova.

### Phân tích nguồn sai lệch

| Thành phần | Trạng thái quan sát | Điều cần kiểm tra |
| --- | --- | --- |
| HRIS/assignment | Đã chuyển sang Nova | Phiên bản và thời điểm hiệu lực |
| IAM/IGA | Expected access đã thay đổi | Đã phát yêu cầu revoke/cấp quyền chưa |
| IdP | Group Atlas đã xóa | Token đang lưu có role/project cũ không |
| SaaS | Có thể còn ACL Atlas | Đọc lại account và quyền trực tiếp |
| Reports API | Vẫn ALLOW Atlas | API kiểm tra current entitlement hay chỉ claim cũ? |

**Một nguyên nhân có thể** là API chỉ đọc claim `projects=["Atlas"]` từ token cấp trước Mover, không hỏi trạng thái quyền hiện hành. Một nguyên nhân khác là ứng dụng còn ACL Atlas độc lập. Cần kiểm chứng nguyên nhân thực, không suy đoán chỉ từ response thành công.

### Cách xử lý

1. Xác nhận account/token thuộc đúng Hòa, đúng tenant, không nhầm ID.
2. Đánh giá rủi ro và **chặn quyền Atlas** bằng kiểm soát tại nơi thực thi, không chỉ ẩn đường dẫn.
3. Kiểm tra và thu hồi **direct ACL, nhóm kế thừa, grant/token/phiên** liên quan theo chính sách.
4. Cập nhật hoặc sửa PDP/PEP để kiểm tra quyền hiệu lực theo dự án tại thời điểm request nếu yêu cầu.
5. Kiểm thử: **READ Nova = ALLOW**, **READ Atlas = DENY**, **DELETE Atlas/Nova = DENY**.
6. Đọc lại hệ thống đích, ghi thời điểm quyền cũ mất hiệu lực và người chịu trách nhiệm.

### Câu hỏi tự kiểm tra

**Câu 1:** Hòa đăng nhập thành công bằng MFA có đủ căn cứ để đọc Atlas không?

**Trả lời:** Không. MFA chứng minh xác thực, không chứng minh quyền truy cập theo dự án sau Mover.

**Câu 2:** Token chứa scope `reports:read` nghĩa là Hòa đọc được báo cáo của mọi tổ chức?

**Trả lời:** Không. API vẫn phải kiểm tra audience, tenant, project membership và entitlement.

**Câu 3:** Nhóm IdP đã xóa quyền Atlas, vì sao API vẫn có thể ALLOW?

**Trả lời:** Có thể do token/claim cũ còn hạn, cache policy chưa cập nhật, ACL trực tiếp hoặc enforcement lỗi; cần đọc trạng thái thực tế.

**Câu 4:** API trả 403 cho quyền DELETE là authorization failure hay đúng?

**Trả lời:** Nếu Hòa không có quyền DELETE, đó là từ chối đúng và cần được giữ nguyên.

**Câu 5:** Nếu PDP timeout, API có thể mặc định ALLOW để tránh gián đoạn?

**Trả lời:** Không nên. Cần xử lý theo fail-closed và chính sách dự phòng được phê duyệt, đặc biệt cho tài nguyên nhạy cảm.

## 26. Tài khoản dịch vụ và authorization failure

**Service account** và **workload identity** có thể sử dụng client credentials, certificate, managed identity hoặc workload federation thay vì đăng nhập tương tác của con người. Chúng cũng cần authorization theo tài nguyên.

| Tình huống | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Một OAuth client có scope admin trên toàn API | Token máy bị lộ có phạm vi lớn | Scope tối thiểu, audience/resource binding và review |
| Workload test gọi API production | Chéo môi trường | Phân tách danh tính, client, role và endpoint |
| Bot được cấp quyền qua group chung quá rộng | Privilege accumulation | Role riêng theo workload và owner |
| PAT cá nhân dùng trong CI/CD | Phụ thuộc tài khoản người đã Mover/Leaver | Chuyển sang workload identity, thu hồi PAT cá nhân |
| Owner workload đã nghỉ việc | Không ai rà soát grant/secret | Chuyển owner, đánh giá và xoay/thu hồi credential |
| Service đã ngừng nhưng account vẫn active | Quyền truy cập tồn dư | Deprovision workload, token và entitlement |

**Không buộc bot dùng MFA push của nhân viên** cho mỗi API call. Workload cần cơ chế chứng thực máy và quyền theo **serviceId, owner team, môi trường, resource, thời hạn**; sau đó API thực thi quyết định như với chủ thể con người.

Một người nghỉ việc có thể từng sở hữu bot sản xuất hợp lệ. Không tự xóa bot nếu vẫn có nhiệm vụ; cần **chuyển owner và thu hồi đặc quyền cá nhân**, đồng thời đánh giá những secret mà người đó có thể đã biết.

## 27. Checklist kiểm soát authorization failure

| Câu hỏi | Điều cần xác minh |
| --- | --- |
| Chủ thể đã được xác thực đúng? | Issuer, subject, MFA/SSO khi yêu cầu, trạng thái phiên |
| Có tách authentication và authorization? | Đăng nhập không tự đồng nghĩa có quyền tài nguyên |
| Policy định nghĩa subject/action/resource/context? | Decision matrix có positive và negative cases |
| PEP kiểm tra tại mọi đường API? | Không chỉ ẩn nút frontend; không bỏ qua trong internal calls |
| RBAC có đúng role và phạm vi? | Không có group mặc định/admin quá rộng hoặc role kế thừa sai |
| ABAC dùng thuộc tính đáng tin và đủ mới? | HR/assignment/tenant/owner theo authority matrix |
| Có kiểm tra object-level authorization? | Chặn IDOR/BOLA và quyền trên resource cụ thể |
| Có cô lập tenant/organization? | Token scope và header không tự xác nhận quyền tenant |
| Có kiểm tra OAuth token và scope đúng? | Issuer, audience, signature/introspection, exp, scope, revoke |
| Có phân biệt 401/403/404/5xx hợp lý? | Error contract không lộ bí mật, phân biệt denial và lỗi hệ thống |
| Khi PDP lỗi có fail-closed? | Không allow do timeout; policy dự phòng có kiểm soát |
| Joiner có kiểm tra thiếu/thừa quyền? | Expected vs observed, quyền thực tế tại target |
| Mover có thu hồi quyền cũ? | Group, ACL, JWT/phiên và entitlement cũ |
| Leaver có xử lý mọi đường tồn dư? | IdP, SCIM, local login, token/session, PAT, API keys |
| Workload có quyền theo môi trường và owner? | Client scope, resource isolation, secret lifecycle |
| Có chính sách ưu tiên deny và ngoại lệ? | SoD, emergency role, approval và hạn dùng |
| Có audit quyết định và thực thi riêng? | Policy version, correlation ID, target, ALLOW/DENY, readback |
| Có regression test cho lỗ hổng từng xảy ra? | Cross-tenant, IDOR/BOLA, function-level, stale token và fail-closed |

## 28. Tổng kết

**Authorization failure** không chỉ là thông báo **403 Forbidden**. Cần phân biệt **từ chối đúng chính sách**, **từ chối nhầm người có quyền**, **cho phép truy cập trái phép** và **lỗi không thể xác minh quyết định**. Trong đó, unauthorized allow là rủi ro bảo mật nghiêm trọng, thường bắt nguồn từ role/entitlement sai, thuộc tính cũ, thiếu kiểm tra quyền theo đối tượng, lỗi cô lập tenant hoặc PEP không thực thi chính sách.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** cung cấp căn cứ nhân sự; **IAM/IGA** tính quyền mục tiêu; **IdP/SSO/MFA** xác thực danh tính; **SCIM/API provisioning** cập nhật account và group; **OAuth scope** giới hạn quyền token; **RBAC/ABAC, ACL và resource server** quyết định quyền hiệu lực theo chủ thể, hành động, tài nguyên và ngữ cảnh. Tài khoản dịch vụ có vòng đời quyền và credential riêng. Một hệ thống an toàn phải **deny-by-default, fail-closed khi không thể xác minh, kiểm tra authorization tại backend**, đối soát đúng hệ thống đích và lưu bằng chứng kiểm toán để phát hiện, xử lý **quyền truy cập tồn dư**.
