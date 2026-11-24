# Permit và deny trong Authorization của IAM Identity Lifecycle

> **Chương: Authorization.** Khi một chủ thể yêu cầu đọc, tạo, sửa hoặc xóa tài nguyên, hệ thống phải quyết định **Permit (cho phép)** hay **Deny (từ chối)** dựa trên chính sách có hiệu lực. Trong quản lý vòng đời danh tính (**Identity and Access Management — IAM**), quyết định này thay đổi khi một người gia nhập (**Joiner**), chuyển vai trò (**Mover**) hoặc rời tổ chức (**Leaver**). Cần kết hợp dữ liệu từ HR, IdP/SSO, SCIM, RBAC/ABAC và trạng thái tại ứng dụng để hạn chế quyền truy cập dư thừa; **đăng nhập thành công không tự đồng nghĩa với được phép thực hiện mọi hành động**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa và phạm vi của **Permit**, **Deny**, **NotApplicable** và **Indeterminate**; phân biệt từ chối tường minh với thiếu chính sách cho phép.
2. Áp dụng nguyên tắc **default deny / deny by default**, **least privilege** và kiểm tra quyền tại từng tài nguyên, không chỉ tại giao diện.
3. Mô tả vai trò **PEP, PDP, PAP, PIP** và cách yêu cầu, thuộc tính, policy, kết quả quyết định đi qua hệ thống authorization.
4. Thiết kế và đánh giá quy tắc Permit/Deny theo **RBAC, ABAC**, tenant, hành động, tài nguyên, bối cảnh, thời hạn và chính sách đặc quyền.
5. Hiểu các chiến lược xử lý chính sách xung đột như **deny-overrides**, **permit-overrides**, **first-applicable** và vì sao phải chọn thuật toán có chủ đích.
6. Liên hệ quyết định quyền với **Joiner–Mover–Leaver**, IdP/SSO, SCIM, session/token, tài khoản dịch vụ và thu hồi quyền tồn dư.
7. Xây dựng kiểm thử dương/âm, kiểm toán, đối soát và cơ chế ứng phó khi thiếu thuộc tính hoặc dịch vụ phân quyền gặp sự cố.

## 1. Permit và deny trả lời câu hỏi gì?

**Authentication** kiểm tra rằng chủ thể đang tương tác đã cung cấp bằng chứng xác thực phù hợp. **Authorization** kiểm tra chủ thể ấy **có được thực hiện hành động cụ thể trên tài nguyên cụ thể trong bối cảnh hiện tại hay không**.

Ví dụ: Lan đã đăng nhập SSO bằng MFA. Lan muốn xem báo cáo doanh thu của tenant B. Kết quả xác thực cho biết đó là tài khoản của Lan; nhưng quyền đọc báo cáo còn phụ thuộc vào vai trò, tenant, trạng thái làm việc, phạm vi được duyệt và mức bảo đảm phiên.

Một yêu cầu authorization thường có bốn nhóm dữ liệu:

| Thành phần | Ví dụ | Câu hỏi cần xác minh |
| --- | --- | --- |
| **Subject** | Identity ID-LAN-104, tài khoản user-782. | Ai đang yêu cầu? Định danh có đáng tin, còn hiệu lực không? |
| **Action** | report.read, invoice.approve, user.disable. | Hành động chính xác nào? |
| **Resource** | report-27 thuộc tenant-b, invoice-91. | Đối tượng nào, thuộc phạm vi/chủ sở hữu nào? |
| **Context** | Thời điểm, MFA assurance, thiết bị, request tenant, hợp đồng. | Những điều kiện nào đang có hiệu lực? |

**Permit** có nghĩa policy engine cho phép hành động được xét, theo điều kiện và nghĩa vụ đi kèm nếu có. **Deny** có nghĩa hành động không được phép trong bối cảnh đánh giá. Chúng là **kết quả quyết định**; việc request có thực sự bị chặn hay không còn phụ thuộc vào thành phần **enforcement**.

### Ví dụ trực quan

| Yêu cầu | Quy tắc liên quan | Kết quả |
| --- | --- | --- |
| Lan đọc báo cáo thuộc tenant-b, có FinanceReader và trạng thái ACTIVE. | Có role, cùng tenant, đủ MFA. | **Permit**. |
| Lan đọc báo cáo tenant-a trong khi thuộc tenant-b. | Cách ly tenant bắt buộc. | **Deny**. |
| Minh muốn phê duyệt hóa đơn do chính mình tạo. | Segregation of Duties (SoD) cấm tự duyệt. | **Deny**. |
| User đã TERMINATED muốn gọi API bằng access token cũ. | Trạng thái Leaver không còn quyền nghiệp vụ. | **Deny** nếu enforcement kiểm tra trạng thái hiện hành. |
| Một request đòi xóa dữ liệu nhưng không có policy nào cho phép. | Mặc định không cấp quyền ngoài chính sách. | **Deny** ở bước thực thi. |

**Chú ý:** Trong nhiều ngôn ngữ policy, “không có quy tắc áp dụng” và “có một quy tắc Deny áp dụng” là hai trạng thái **khác nhau về mặt đánh giá**, dù cuối cùng ứng dụng đều cần từ chối theo chính sách mặc định.

## 2. Từ chối tường minh, từ chối mặc định và trạng thái chưa xác định

Một hệ thống quyền an toàn cần phân biệt **quyết định của policy** và **kết quả ở cổng thực thi**.

### Các kết quả policy thường gặp

| Kết quả đánh giá | Ý nghĩa | Hành vi an toàn tại điểm thực thi |
| --- | --- | --- |
| **Permit** | Có chính sách áp dụng và các điều kiện cho phép đã được thỏa mãn. | Chỉ cho phép nếu điều kiện thực thi, obligation và dữ liệu còn hợp lệ. |
| **Deny** | Có chính sách áp dụng yêu cầu từ chối. | Chặn hành động; ghi nhận lý do phù hợp. |
| **NotApplicable** | Không quy tắc nào trong phạm vi đánh giá áp dụng. | Thường chuyển thành **không cho phép** bởi quy tắc default deny. |
| **Indeterminate** | Không thể xác định đúng kết quả do lỗi, dữ liệu thiếu/không tin cậy hoặc xử lý policy thất bại. | **Không tự coi là Permit**; trả lỗi hoặc từ chối theo chính sách rủi ro và giám sát. |

Các thuật ngữ **NotApplicable/Indeterminate** quen thuộc trong các mô hình policy như XACML; không phải mọi thư viện authorization đều phơi bày bốn trạng thái này. Một hệ thống đơn giản có thể trả boolean, nhưng **bên trong vẫn nên phân biệt** thiếu quyền, từ chối rõ ràng và lỗi hệ thống để kiểm toán, sửa lỗi và vận hành.

### Explicit deny và implicit/default deny

- **Explicit deny:** policy khẳng định một tình huống bị cấm. Ví dụ: mọi User có trạng thái TERMINATED đều bị từ chối thao tác nghiệp vụ.
- **Implicit/default deny:** nếu không tìm được điều kiện **Permit** hợp lệ, hệ thống không cấp quyền. Ví dụ: role MarketingReader không được khai báo quyền payroll.export nên thao tác bị từ chối.
- **Indeterminate:** policy cần thuộc tính tenantId nhưng PIP không trả được giá trị tin cậy. Đây là **không đủ thông tin**, không phải bằng chứng policy cho phép.

Ví dụ:

~~~text
Policy A: PERMIT invoice.read nếu subject.role = FINANCE_VIEWER
Policy B: DENY invoice.read nếu subject.lifecycleState = TERMINATED

User: role = FINANCE_VIEWER, lifecycleState = TERMINATED

Nếu hệ thống dùng kết hợp "deny-overrides":
    quyết định cuối = DENY
~~~

**Không khẳng định “explicit deny luôn thắng” ở mọi sản phẩm.** Thứ tự ưu tiên và thuật toán gộp policy là thiết kế của hệ thống; ví dụ trên chỉ đúng nếu policy combining được cấu hình phù hợp. Một số nền tảng quyền có semantics riêng (chẳng hạn explicit deny ưu tiên), nhưng không nên sao chép giả định đó sang ứng dụng khác.

## 3. Nguyên tắc default deny và least privilege

**Default deny (deny by default)** nghĩa là **không cấp quyền khi chưa có một cơ sở cho phép hợp lệ**. Điều này ngăn một endpoint mới, API mới hoặc một role chưa được cấu hình vô tình mở quyền cho tất cả người dùng.

Ví dụ một API:

~~~text
GET    /invoices/{invoiceId}       -> invoice.read
POST   /invoices                   -> invoice.create
POST   /invoices/{invoiceId}/approve -> invoice.approve
DELETE /invoices/{invoiceId}       -> invoice.delete
~~~

Việc Lan được Permit đối với **invoice.read** không tự Permit **invoice.approve**, ngay cả khi cả hai thuộc cùng tài nguyên hoặc chung trang giao diện.

### Least privilege trong điều kiện Permit

Một quyết định cho phép cần giới hạn ít nhất:

1. **Đúng chủ thể:** identity hợp lệ và mapping account chắc chắn.
2. **Đúng hành động:** chỉ operation cần cho công việc.
3. **Đúng tài nguyên và tenant:** không cho đọc/sửa tài nguyên ngoài phạm vi.
4. **Đúng điều kiện:** trạng thái ACTIVE, thời điểm, authentication assurance, yêu cầu thiết bị hoặc độ rủi ro.
5. **Đúng thời hạn:** hết quyền dự án, hợp đồng hoặc JIT privilege thì điều kiện Permit không còn.
6. **Đúng nguồn phê duyệt:** role hoặc ngoại lệ phải được chủ sở hữu thích hợp duyệt.

Đừng thiết kế kiểu “đã đăng nhập thì mặc định cho phép, trừ vài API được chặn”. Nó khiến endpoint mới và các đường gọi API không qua UI dễ bị bỏ sót.

### Fail closed nhưng không đánh đồng mọi lỗi

Nếu PDP không thể đánh giá một hành động nhạy cảm, **không được chuyển lỗi thành Permit**. Cách ứng dụng phản hồi có thể là **403 Forbidden**, **503 Service Unavailable** hoặc lỗi tương ứng tùy ngữ cảnh: trả về 403 vì chắc chắn không có quyền khác với 503 vì dịch vụ kiểm tra quyền tạm thời không hoạt động.

Về **hành vi thực thi**, cả hai đều không được cho phép thao tác nhạy cảm. Về **vận hành**, phải giữ nguyên thông tin lỗi để tránh tưởng nhầm hệ thống không cấp quyền hợp lệ hoặc âm thầm cho vượt kiểm soát.

## 4. Kiến trúc PEP, PDP, PAP và PIP

Trong mô hình kiến trúc phân quyền thường gặp:

| Thành phần | Tên đầy đủ | Trách nhiệm |
| --- | --- | --- |
| **PEP** | Policy Enforcement Point | Chặn hoặc cho thực hiện request theo quyết định; đặt tại API gateway, service hoặc resource boundary. |
| **PDP** | Policy Decision Point | Đánh giá chính sách dựa trên subject, action, resource và context; trả quyết định. |
| **PAP** | Policy Administration Point | Quản lý policy, phiên bản, phê duyệt và triển khai thay đổi. |
| **PIP** | Policy Information Point | Cung cấp thuộc tính/ngữ cảnh cho PDP, ví dụ trạng thái JML, nhóm, owner tài nguyên, tenant. |

~~~mermaid
sequenceDiagram
    actor User as User / API Client
    participant PEP as PEP tại API
    participant PDP as Policy Decision Point
    participant PIP as Policy Information Point
    participant PAP as Policy Administration Point
    participant DB as Resource Store
    PAP-->>PDP: Policy đã được phê duyệt/phiên bản
    User->>PEP: Thực hiện action trên resource
    PEP->>PDP: subject, action, resource, context
    PDP->>PIP: Yêu cầu thuộc tính cần kiểm tra
    PIP-->>PDP: JML, role, tenant, ownership, assurance
    PDP-->>PEP: Permit / Deny / NotApplicable / Indeterminate
    alt Permit và yêu cầu bổ sung đạt
        PEP->>DB: Thực hiện thao tác đúng phạm vi
        DB-->>PEP: Kết quả
        PEP-->>User: Response thành công
    else Deny, không áp dụng hoặc không thể đánh giá
        PEP-->>User: Không thực hiện thao tác
    end
~~~

Sơ đồ là **kiến trúc khái niệm**, không bắt buộc có bốn microservice độc lập. PDP có thể nằm trong ứng dụng; PIP có thể là cache/nguồn IAM được tin cậy. Điểm quan trọng là **quyền được kiểm tra và cưỡng chế tại chỗ thực hiện hành động**, không phụ thuộc vào việc menu có hiển thị hay không.

### Ví dụ về lỗi không thực thi quyết định

Frontend ẩn nút “Delete invoice” khi User không có quyền. Nhưng API DELETE vẫn nhận request trực tiếp và thực thi vì backend không hỏi PDP hoặc không kiểm tra quyền tại resource.

Đây là lỗi **thiếu PEP hoặc PEP không bao phủ tất cả đường truy cập**. Ẩn nút trên UI có ích cho trải nghiệm, **không thay thế authorization server-side**.

## 5. RBAC, ABAC và các điều kiện tạo Permit

### RBAC: quyền theo vai trò

**Role-Based Access Control (RBAC)** liên kết vai trò với tập quyền. Người dùng có thể được gán role do công việc, nhóm hoặc phê duyệt.

Ví dụ:

| Vai trò | report.read | invoice.create | invoice.approve | identity.disable |
| --- | :---: | :---: | :---: | :---: |
| **FinanceViewer** | Permit | Deny mặc định | Deny mặc định | Deny mặc định |
| **FinanceCreator** | Permit | Permit | Deny mặc định | Deny mặc định |
| **FinanceApprover** | Permit | Deny mặc định | Permit khi đủ điều kiện | Deny mặc định |
| **IdentityOperator** | Theo nghiệp vụ riêng | Theo nghiệp vụ riêng | Theo nghiệp vụ riêng | Permit theo phạm vi được duyệt |

Bảng là ví dụ thiết kế, không phải bảng quyền của một sản phẩm cụ thể. Trong thực tế một User có thể có nhiều role, role kế thừa hoặc được cấp trực tiếp từ ứng dụng; cần xét **effective roles**, không chỉ một trường role chính trong HR.

### ABAC: quyền theo thuộc tính và ngữ cảnh

**Attribute-Based Access Control (ABAC)** đánh giá các thuộc tính của subject, resource, action và môi trường.

Ví dụ chính sách đọc báo cáo:

~~~text
PERMIT report.read KHI
    subject.lifecycleState == ACTIVE
    AND subject.department == FINANCE
    AND "FinanceViewer" in subject.effectiveRoles
    AND subject.tenantId == report.tenantId
    AND report.classification <= subject.approvedClassification
    AND session.assurance >= report.minimumAssurance

ELSE NO_PERMIT
~~~

Điều kiện **NO_PERMIT** ở đây được **PEP chuyển thành từ chối theo default deny**. Nếu hệ thống còn các quy tắc Deny cụ thể, thuật toán kết hợp phải xem xét chúng.

### Quyền phụ thuộc quan hệ và ownership

Một số ứng dụng cần kiểm tra quan hệ giữa chủ thể và tài nguyên, ví dụ nhân viên chỉ sửa ticket được phân công hoặc người quản lý chỉ phê duyệt của cấp dưới trực tiếp. Có thể mô hình hóa bằng ABAC, quan hệ có chủ đích (ReBAC) hoặc rule của ứng dụng.

Ví dụ:

~~~text
PERMIT ticket.update KHI
    subject.lifecycleState == ACTIVE
    AND ticket.tenantId == subject.tenantId
    AND ticket.assigneeIdentityId == subject.identityId
    AND subject.hasPermission("ticket.update")
~~~

Nếu ticket.assigneeIdentityId thay đổi trong lúc request đang chạy, hệ thống phải cân nhắc **kiểm tra lại ở thời điểm thực thi hoặc giao dịch**, tránh việc quyền lúc kiểm tra khác quyền lúc ghi dữ liệu (**TOCTOU — time-of-check to time-of-use**).

## 6. Deny tường minh để bảo vệ những ranh giới bắt buộc

Một tổ chức có thể đặt các quy tắc Deny độc lập với role. Những quy tắc này bảo vệ các giới hạn mà các policy Permit không được tự bỏ qua.

| Quy tắc Deny | Tình huống | Lý do |
| --- | --- | --- |
| **Lifecycle deny** | User TERMINATED hoặc SUSPENDED không được thực hiện thao tác thuộc phạm vi đình chỉ. | Tránh dùng quyền tồn dư sau Leaver/suspension. |
| **Tenant isolation** | Subject tenant-a truy cập resource tenant-b không có quan hệ hợp lệ. | Ngăn truy cập chéo tenant. |
| **SoD** | Người tạo hóa đơn tự phê duyệt hóa đơn ấy. | Giảm gian lận và xung đột nhiệm vụ. |
| **Expired grant** | Membership hoặc quyền dự án đã hết hạn. | Ngăn quyền tạm trở thành quyền vĩnh viễn. |
| **Assurance requirement** | Session không đạt MFA/phishing-resistant assurance cho thao tác đặc quyền. | Tránh thực hiện hành động nhạy cảm bằng phiên yếu. |
| **Policy restriction** | Hành động xóa trên dữ liệu thuộc diện retention. | Bảo vệ dữ liệu và yêu cầu tuân thủ. |
| **Resource-state restriction** | Hóa đơn đã đóng hoặc tài nguyên đã bị khóa giao dịch. | Ngăn thao tác ngoài trạng thái nghiệp vụ cho phép. |

Các quy tắc này cần được định nghĩa theo **phạm vi nguồn và mức ưu tiên rõ ràng**. Không nên thêm một chính sách Deny quá rộng rồi hy vọng quy tắc Permit cụ thể tự “mở lại” được nếu bộ gộp đang dùng deny-overrides.

### Ví dụ SoD: phê duyệt hóa đơn

~~~text
PERMIT invoice.approve KHI
    subject.role == FinanceApprover
    AND subject.tenantId == invoice.tenantId
    AND invoice.amount <= subject.approvalLimit
    AND session.assurance >= REQUIRED_LEVEL

DENY invoice.approve KHI
    invoice.createdByIdentityId == subject.identityId

DENY invoice.approve KHI
    invoice.status != PENDING_APPROVAL
~~~

Nếu dùng **deny-overrides** cho tập quy tắc này, người có role FinanceApprover vẫn không được duyệt chính hóa đơn mình đã tạo. Nếu hệ thống dùng chiến lược khác, phải chứng minh cách kết hợp vẫn bảo vệ điều kiện SoD.

## 7. Gộp nhiều policy: deny-overrides và các chiến lược khác

Trong hệ thống lớn, một request có thể đồng thời khớp nhiều policy: role của đội Finance, policy tenant, policy dự án, policy đặc quyền và policy Leaver. Nếu một rule trả Permit còn rule khác trả Deny, hệ thống cần một **thuật toán kết hợp**.

### Những chiến lược thường gặp

| Chiến lược | Ý nghĩa cơ bản | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Deny-overrides** | Khi một quy tắc Deny áp dụng, nó được ưu tiên trước Permit theo semantics của policy engine. | Một Deny quá rộng có thể chặn User hợp lệ; lỗi/Indeterminate cần xử lý chính xác. |
| **Permit-overrides** | Một Permit có thể được ưu tiên trước Deny trong phạm vi thuật toán. | Có thể bỏ qua quy tắc hạn chế nếu dùng nhầm cho policy an ninh bắt buộc. |
| **First-applicable** | Quy tắc áp dụng đầu tiên theo thứ tự đã định quyết định kết quả. | Chỉ cần đổi thứ tự rule có thể thay đổi quyền. |
| **Only-one-applicable** | Chỉ chấp nhận khi đúng một quy tắc áp dụng theo mô hình tương ứng. | Nhiều rule cùng áp dụng có thể tạo xung đột cần xử lý. |
| **Policy ưu tiên theo tầng** | Tách hard guard bắt buộc với policy cấp quyền ở tầng sau. | Cần quản trị thứ tự, phạm vi và test không bypass guard. |

**Lưu ý về chuẩn:** XACML có những semantics chi tiết cho **Indeterminate** và policy combining, không phải chỉ là một lệnh `if deny then false` ở mọi trường hợp. Bảng trên mô tả trực giác của các chiến lược, không phải thuật toán đầy đủ để triển khai chuẩn XACML.

### Ví dụ xung đột

~~~text
Subject: Lan
Context:
  lifecycle = TERMINATED
  role = FinanceApprover
  tenant = tenant-b

Policy 1 (RBAC): Permit invoice.approve khi có role FinanceApprover
Policy 2 (JML): Deny mọi thao tác tài chính sau Leaver

Kỳ vọng theo chính sách tổ chức:
  Deny phải thắng

Yêu cầu thiết kế:
  Áp hard lifecycle guard hoặc combining algorithm phù hợp
~~~

Nếu không có cơ chế ưu tiên rõ ràng, một app có thể tình cờ Permit do kiểm tra RBAC trước mà bỏ qua Leaver. **Trạng thái vòng đời là điều kiện truy cập thực chất**, không nên chỉ được hiển thị ở giao diện quản trị IAM.

### Không dùng Permit từ cache cũ để ghi đè Deny mới

Một PDP đã Permit lúc 08:00 không chứng minh hành động lúc 10:00 cũng phải Permit. Nếu HR phát Leaver hoặc Mover lúc 09:00, policy và thuộc tính tại 10:00 có thể đã thay đổi. Cần đặt **thời hạn hiệu lực của decision cache**, invalidation theo sự kiện và cơ chế kiểm tra đủ mới cho tài nguyên nhạy cảm.

## 8. Thiết kế một quyết định authorization từ đầu đến cuối

Để quyết định chính xác, hệ thống cần chuẩn hóa dữ liệu và biết rõ nguồn quyền.

### Quy trình bảy bước

1. **Xác định subject:** kiểm tra authentication context, issuer/sub/tenant hoặc danh tính workload; liên kết tới identity IAM đáng tin.
2. **Chuẩn hóa hành động:** chuyển endpoint/HTTP method thành action nghiệp vụ như `invoice.approve`; không gộp mọi POST thành một quyền.
3. **Xác định resource thực:** lấy đối tượng từ nguồn server-side và xác minh owner/tenant/classification; không tin tenant do client tự khai nếu không được xác thực.
4. **Lấy thuộc tính hiện hành:** lifecycle state từ nguồn IAM/HR được ủy quyền, role/approval, ABAC, time-bound grant, authentication assurance.
5. **Đánh giá policy và kết hợp:** xét rule phù hợp, xử lý Permit/Deny/NotApplicable/Indeterminate theo thuật toán đã phê duyệt.
6. **Enforce tại PEP:** chỉ thao tác nếu Permit đủ điều kiện; xử lý obligation và giới hạn kết quả/dữ liệu; giữ nhất quán qua transaction.
7. **Audit và đối soát:** lưu decision, policy version, lý do, các nguồn dữ liệu, trạng thái thực thi và tín hiệu drift cần xử lý.

~~~mermaid
flowchart TD
    A["Request: subject, action, resource"] --> B["Authenticate / resolve trusted subject"]
    B --> C{"Danh tính, tenant<br/>đáng tin?"}
    C -->|Không| D["DENY / REVIEW"]
    C -->|Có| E["Load resource và thuộc tính<br/>lifecycle, roles, policy"]
    E --> F{"Thuộc tính đầy đủ<br/>và đủ mới?"}
    F -->|Không| G["INDETERMINATE<br/>không cấp quyền"]
    F -->|Có| H["PDP: evaluate + combine policy"]
    H --> I{"Kết quả?"}
    I -->|Permit| J["PEP: verify obligations<br/>và transaction scope"]
    I -->|Deny| K["DENY"]
    I -->|NotApplicable| L["DEFAULT DENY"]
    I -->|Indeterminate| G
    J --> M{"Yêu cầu thực thi đạt?"}
    M -->|Có| N["Thực hiện đúng action/resource<br/>và audit"]
    M -->|Không| K
~~~

### JSON của một request nội bộ

Ví dụ minh họa, **không phải schema chuẩn OAuth/OIDC, XACML hoặc Open Policy Agent**:

~~~json
{
  "subject": {
    "identityId": "ID-LAN-104",
    "issuer": "https://id.example.org",
    "tenantId": "tenant-b",
    "lifecycleState": "ACTIVE",
    "roles": ["FinanceApprover"]
  },
  "action": "invoice.approve",
  "resource": {
    "invoiceId": "INV-91",
    "tenantId": "tenant-b",
    "createdByIdentityId": "ID-MINH-202",
    "status": "PENDING_APPROVAL",
    "amount": 5000000
  },
  "context": {
    "authenticationAssurance": "APPROVED_STRONG_METHOD",
    "requestedAt": "2026-12-01T09:20:00+07:00"
  }
}
~~~

Ví dụ response quyết định:

~~~json
{
  "decision": "Permit",
  "policyVersion": "finance-access-v9",
  "obligations": [
    "WRITE_APPROVAL_AUDIT"
  ],
  "decisionId": "dec-778",
  "evaluatedAt": "2026-12-01T09:20:01+07:00"
}
~~~

**Obligation** là điều kiện/hành động bổ sung mà thành phần thực thi phải tuân thủ theo thiết kế policy, chẳng hạn ghi audit bắt buộc hoặc giới hạn trường dữ liệu trả về. Nếu không thể đáp ứng obligation bắt buộc, **không được tự bỏ qua và tiếp tục Permit**.

## 9. Pseudocode với Permit/Deny và default deny

Một ví dụ logic ở API, tách quyết định đánh giá và bước thực thi:

~~~text
handleRequest(request):
    authn = validateTrustedAuthentication(request)
    if not authn.valid:
        return UNAUTHENTICATED

    subject = resolveIdentity(authn.issuer, authn.subject, authn.tenant)
    resource = loadResourceFromTrustedStore(request.resourceId)
    if subject.unresolved or resource.unresolved:
        audit("identity_or_resource_unresolved")
        return DENY

    attributes = loadAuthoritativeAttributes(
        subject,
        resource,
        sourceVersionAndFreshnessRequiredByRisk
    )
    if attributes.incomplete or attributes.staleBeyondPolicy:
        audit("authorization_indeterminate")
        return NO_ACCESS_UNTIL_RESOLVED

    if attributes.lifecycleStatus disallows request.action:
        return DENY
    if not tenantRelationshipAllowed(subject, resource):
        return DENY

    decision = evaluateApprovedPolicies(
        subject,
        request.action,
        resource,
        attributes,
        combiningAlgorithm = DENY_OVERRIDES
    )

    if decision != PERMIT:
        audit("authorization_denied", decision.reasonCode)
        return DENY

    if not obligationsSatisfied(decision.obligations):
        return DENY

    return executeAtomicallyWithScopeChecks(
        subject,
        request.action,
        resource
    )
~~~

Đây là **pseudocode giáo dục**, chưa gồm đầy đủ semantics của XACML, chứng thực policy source, quản lý cache phân tán, retry, xử lý tài nguyên đồng thời và hợp đồng API. Giá trị quan trọng nằm ở **deny mặc định**, kiểm tra trạng thái vòng đời, không tin dữ liệu client và cưỡng chế quyền sát tài nguyên.

### Những điểm không được nhầm

- Nếu trả **401**, hệ thống đang yêu cầu xác thực hợp lệ; nếu **403**, chủ thể đã được nhận diện nhưng không được phép. Không phải mọi trường hợp nên lộ đầy đủ lý do quyền.
- Một HTTP response **200** từ API token/introspection hoặc một API SCIM **PATCH 200/204** không tự chứng minh request nghiệp vụ phải Permit.
- Client có thể đã có role trong token nhưng thuộc tính role đó **lỗi thời** sau Mover.
- Không nên dùng dữ liệu `subject.role` gửi tự do trong JSON client làm nguồn quyết định quyền.
- Cần phân biệt **read-only**, **write**, **approve**, **delete**, **export** và **administrative operations** ngay cả khi chúng nằm cùng ứng dụng.

## 10. Permit và deny trong Joiner–Mover–Leaver

Vòng đời danh tính quyết định việc **khi nào một chủ thể còn đủ điều kiện dùng quyền**. Mỗi sự kiện JML phải cập nhật trạng thái mong muốn và ảnh hưởng tới các quyết định authorization.

### Joiner: chưa đủ điều kiện thì không Permit nghiệp vụ

Trước ngày bắt đầu, IAM có thể tạo IdP User và ứng dụng qua SCIM (**pre-provisioning**). Tuy nhiên account tồn tại không có nghĩa đã được phép đọc dữ liệu doanh nghiệp.

Ví dụ:

~~~text
DENY business-api.* KHI
    subject.lifecycleState == PENDING_ACTIVATION

PERMIT onboarding.enrollAuthenticator KHI
    subject.lifecycleState == PENDING_ACTIVATION
    AND onboardingIdentityBindingVerified
    AND currentTime within approvedOnboardingWindow
~~~

Nếu dùng những policy này, cần xác định **cách kết hợp** để Permit onboarding không bị một Deny quá rộng chặn mất, đồng thời không cho mở quyền nghiệp vụ ngoài phạm vi onboarding. Có thể tách **policy domain/endpoint** của onboarding với ứng dụng nghiệp vụ, hoặc dùng các hard guard có ngoại lệ được mô tả chặt chẽ.

Sau khi Joiner đạt ngày hiệu lực, proofing, MFA và quyền nền được xác định, API vẫn phải xét đúng role, tenant và resource thay vì cho phép toàn bộ người ACTIVE.

### Mover: quyền cũ phải được từ chối, quyền mới cần phê duyệt

**Tình huống:** Lan chuyển từ Support sang Finance lúc 09:00.

| Thời điểm | Role hợp lệ theo IAM | Request | Kỳ vọng |
| --- | --- | --- | --- |
| 08:50 trước Mover | SupportAgent | ticket.update thuộc phạm vi hỗ trợ | Permit nếu đủ điều kiện. |
| 09:10 sau Mover | FinanceViewer | ticket.update do role SupportAgent cũ | **Deny**, dù session còn claim cũ. |
| 09:10 sau Mover | FinanceViewer | report.read tenant-b | Permit nếu role và chính sách có hiệu lực. |
| 09:10 sau Mover | Chưa có phê duyệt FinanceApprover | invoice.approve | **Deny**. |

Rủi ro thường gặp là **quyền tích lũy (privilege accumulation)**: provisioning chỉ thêm role mới mà không gỡ role cũ; hoặc SCIM đã gỡ nhóm nhưng token/cache ở ứng dụng vẫn dùng quyền trước Mover.

Cần cập nhật nguồn quyền, invalidate cache/phiên hoặc kiểm tra quyền tại request theo rủi ro. Nếu có yêu cầu step-up cho hành động mới, session cũ không tự đáp ứng chỉ vì role vừa được cấp.

### Leaver: từ chối ngay cả khi credential vẫn còn

Một Leaver có thể đã bị disable ở IdP, nhưng người dùng vẫn giữ app session, JWT access token, refresh token, PAT hoặc API key còn hạn ở ứng dụng khác.

**Mục tiêu authorization:** mọi đường truy cập thuộc phạm vi Leaver phải từ chối tại nơi thực thi theo chính sách và thời hạn thu hồi.

1. HR/nguồn hợp đồng phát Leaver có **effectiveAt** và sourceVersion đáng tin.
2. IAM/IdP chặn sign-in mới và thu hồi session/refresh token theo khả năng.
3. SCIM/connector disable account, gỡ Group và role được quản lý.
4. PEP/PDP hoặc Resource Server phải xem xét **lifecycle state đủ mới** tại điểm sử dụng; tránh tin hoàn toàn JWT chứa role cũ.
5. Từng ứng dụng cần xử lý local account, PAT, token và cache độc lập nếu có.
6. IAM đối soát truy cập thực tế, ghi phần chưa xác minh hoặc không thể thu hồi ngay.
7. Job Joiner/Mover cũ được retry không được cấp lại quyền sau Leaver.

**Deny tại PDP chỉ có giá trị nếu PEP thật sự hỏi và thực thi quyết định**. Nếu một Resource Server chỉ kiểm tra JWT offline và không nhận thông tin Leaver, token còn hạn có thể tiếp tục được chấp nhận. Đây là vấn đề kiến trúc cần giải quyết, không thể sửa chỉ bằng việc thêm một rule Deny vào IAM trung tâm.

### Rehire và contractor expiry

- **Rehire:** không tự chuyển các role/grant bị thu hồi thành Permit chỉ vì account cũ được mở lại; cần identity resolution, proofing phù hợp và quyền theo công việc hiện tại.
- **Hết hợp đồng nhà thầu:** policy phải có giới hạn thời hạn, sponsor và nguồn gia hạn đáng tin; thiếu sự kiện gia hạn không phải lý do duy trì quyền vô thời hạn.
- **Tạm đình chỉ:** phạm vi Deny có thể khác Leaver vĩnh viễn; cần mô tả chính sách cụ thể, tránh tự xóa dữ liệu hoặc mở lại quyền không được phê duyệt.

## 11. IdP/SSO, SCIM và authorization không thay thế nhau

### IdP và SSO trả lời “đã xác thực” chứ không phải “được làm mọi việc”

**OIDC ID token** có thể cho RP bằng chứng về kết quả xác thực; **SAML Assertion** có thể hỗ trợ SP thiết lập phiên. **OAuth access token** có thể mang scope hoặc thông tin ủy quyền cho Resource Server.

Ứng dụng vẫn phải kiểm tra:

- Đúng **issuer, subject, audience, tenant** và tính hợp lệ của token/assertion theo giao thức.
- Token có đúng **loại**, scope và resource server nhận hay không.
- Trạng thái account, vòng đời, role và quyền được đánh giá từ nguồn đủ mới.
- Tài nguyên được truy cập thuộc tenant/phạm vi đã duyệt không.
- Session có đáp ứng authentication assurance/reauthentication cho thao tác nhạy cảm không.

Một JWT có chữ ký hợp lệ **không tự chứng minh role/department trong token vẫn hiện hành** sau Mover. Chữ ký bảo vệ nguồn gốc và tính toàn vẹn token tại lúc phát, không biến mọi thuộc tính thành dữ liệu thời gian thực.

### SCIM provision account và Group, không tự quyết định resource policy

SCIM có thể truyền User/Group; ví dụ khi Mover, connector gỡ User khỏi Group SupportAdmin. Nhưng ứng dụng có thể còn role trực tiếp hoặc app-local session chứa quyền cũ.

Vì vậy cần thiết kế:

~~~mermaid
flowchart LR
    HR["HR / contract events"] --> IAM["IAM desired access<br/>Joiner–Mover–Leaver"]
    IAM --> IDP["IdP / SSO authentication"]
    IAM --> SCIM["SCIM User & Group provisioning"]
    IDP --> APP["Application / API PEP"]
    SCIM --> APP
    IAM --> PIP["Authoritative lifecycle & roles"]
    PIP --> PDP["Policy Decision Point"]
    APP --> PDP
    PDP --> APP
    APP --> AUD["Observed effective access<br/>audit + reconciliation"]
~~~

Mối quan hệ là khái niệm. Hệ thống thực có thể dùng policy local, PDP trung tâm, cache hoặc gateway. Điều không đổi là **quyết định Permit/Deny phải áp dụng đúng tại chỗ dùng quyền**.

## 12. Quyết định quyền theo tenant và tài nguyên

Một lỗi phổ biến là **IDOR/BOLA** (truy cập đối tượng bằng ID trực tiếp mà không kiểm tra quyền trên chính đối tượng). User có quyền gọi endpoint `GET /reports/{id}` nhưng thay id để đọc báo cáo của người khác.

### Kiểm tra ở cấp object

Sai:

~~~text
if authenticated:
    return reportRepository.findById(request.id)
~~~

Đúng về mặt ý tưởng:

~~~text
subject = validateAndResolveAuthenticatedIdentity(request)
report  = reportRepository.findById(request.id)

decision = authorize(
    subject,
    action = "report.read",
    resource = report,
    context = currentRequestContext
)

if decision != PERMIT:
    return ACCESS_DENIED

return filterResultToPermittedFields(report, subject)
~~~

Phải lấy tenant/resource ownership từ dữ liệu được tin cậy ở server, không tự tin một query parameter `tenantId` do client gửi. Với danh sách nhiều resource, kiểm tra bộ lọc truy vấn và authorization **theo từng dòng/nhóm dữ liệu** nếu chính sách yêu cầu.

### Field-level authorization

Permit `customer.read` không nhất thiết cho phép xem số định danh, lương, email riêng tư hoặc credential metadata. Ứng dụng có thể áp quyền theo **field**, sử dụng giới hạn dữ liệu trả về, projection hoặc masking có kiểm soát. Một quyết định Permit ở mức object **không tự mở mọi trường dữ liệu**.

### Batch API và background job

Các endpoint xuất dữ liệu, batch update, scheduled job hoặc message consumer cũng cần PEP:

- Một request cập nhật 100 tài nguyên phải bảo đảm **tất cả tài nguyên được phép** hoặc có chính sách partial success rõ ràng.
- Background job không nên được hưởng quyền vô hạn chỉ vì chạy trong nội bộ.
- Service-to-service API phải phân biệt identity máy với identity người dùng được ủy quyền, và giới hạn quyền.
- Bypass ở message queue hoặc internal service có thể khiến policy trên UI/API gateway mất tác dụng.

## 13. Deny khi thiếu dữ liệu và PDP không khả dụng

Đánh giá policy cần dữ liệu về subject, resource, session và thời điểm. Các nguồn PIP có thể lỗi mạng, stale cache, thiếu entitlement hoặc đồng bộ chưa xong.

### Ba trường hợp phải phân biệt

| Trường hợp | Ví dụ | Hành vi khuyến nghị |
| --- | --- | --- |
| **Thiếu Permit hợp lệ** | User không có role invoice.approve. | Deny theo default deny. |
| **Explicit Deny áp dụng** | User đã Leaver, request vi phạm SoD. | Deny và audit lý do phù hợp. |
| **Không đánh giá được** | Không đọc được trạng thái vòng đời/tenant, PDP timeout. | Không tự Permit; trả lỗi/từ chối theo mức rủi ro, cảnh báo và phục hồi quan sát. |

### Cache decision và attribute

Caching có thể giúp giảm độ trễ, nhưng một Permit cũ rất nguy hiểm khi role, owner, tenant hoặc lifecycle state thay đổi.

Nếu cache, cần:

1. Khóa cache gồm **subject, action, resource, tenant và các yếu tố context liên quan**.
2. Đặt TTL dựa trên rủi ro, không áp một thời gian chung.
3. Có cơ chế invalidation khi Mover, Leaver, revoke grant hoặc thay đổi resource.
4. Đảm bảo cache policy version và sourceVersion phù hợp để tránh dùng kết quả cũ.
5. Không dùng cache Permit quá hạn làm fallback vô thời hạn khi PDP mất kết nối.
6. Với tài nguyên đặc quyền/nhạy cảm, cân nhắc kiểm tra trạng thái mới hơn hoặc cơ chế revocation tại điểm sử dụng.

**Fail closed** không có nghĩa phá hỏng mọi quy trình cứu hộ khẩn cấp. Một cơ chế break-glass được phê duyệt có thể tồn tại, nhưng phải là **policy riêng**, giới hạn chủ thể và thời hạn, kiểm toán mạnh và không cho phép mọi client biến lỗi PDP thành Permit.

## 14. Tài khoản đặc quyền và danh tính máy

### Quyền đặc quyền: Permit phải gắn thời hạn và điều kiện

Ví dụ một nhân viên vận hành có nhu cầu chạy lệnh bảo trì:

~~~text
PERMIT production.restart KHI
    subject.lifecycleState == ACTIVE
    AND privilegedGrant.isApproved
    AND privilegedGrant.isWithinJitWindow
    AND session.authAssurance meets privilegedPolicy
    AND resource.environment == PRODUCTION
    AND subject.tenantId == resource.tenantId

DENY production.restart KHI
    privilegedGrant.expired
    OR subject.lifecycleState in [SUSPENDED, TERMINATED]
~~~

Đây là policy minh họa; khi kết hợp nhiều rule, phải đảm bảo điều kiện Deny bắt buộc không bị bỏ qua. **PAM/JIT** có thể cấp quyền tạm thời, quản lý session và lưu audit. Nhưng một role vừa được cấp trong directory không đủ cho Permit nếu cần phê duyệt, step-up hoặc phiên PAM.

### Service account, workload identity và Permit/Deny

Máy không phải nhân viên HR theo nghĩa thông thường. Một workload có thể xác thực bằng mTLS, workload federation hoặc OAuth client credentials. Authorization cần xét:

| Thuộc tính | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Workload subject** | service/payment-worker | Đúng issuer, identity, trust relationship. |
| **Service owner** | Payment Platform team | Có owner và nguồn quản trị được ủy quyền. |
| **Environment** | staging / production | Không dùng token staging truy cập production. |
| **Audience/scope** | billing-api, invoice.create | Hạn chế API và hành động. |
| **Resource** | queue-payment, tenant-b | Đúng tài nguyên và tenant. |
| **Workload lifecycle** | ACTIVE / DECOMMISSIONED | Deny khi dịch vụ không còn hợp lệ. |
| **Credential lifetime** | Chứng chỉ hoặc token ngắn hạn | Thu hồi/rotate phù hợp, không phụ thuộc cookie người dùng. |

Khi nhân viên sở hữu workload nghỉ việc, **không xóa mù service account đang phục vụ hệ thống hợp lệ**; phải chuyển owner, giảm quyền, thu hồi/rotate credential do người rời đi biết. Khi workload bị decommission, source authority của danh tính máy phải khiến các request tiếp theo bị Deny.

## 15. Policy governance, ngoại lệ và thay đổi quyền

Quản trị Permit/Deny không chỉ là lập trình một `if`. Một policy sai có thể gây mất truy cập trên diện rộng hoặc mở đặc quyền vượt phạm vi.

### Quy trình quản trị policy

1. **Định nghĩa tài sản và hành động:** mô tả rõ resource type, action và dữ liệu nhạy cảm.
2. **Chỉ định policy owner:** team IAM, Security và resource owner theo trách nhiệm.
3. **Xác định nguồn sự thật:** HR lifecycle, role/approval, tenant, assurance, ownership.
4. **Mô tả điều kiện Permit/Deny và combining semantics**, gồm hard guard bắt buộc.
5. **Thử nghiệm thay đổi:** unit test, contract test, regression, giả lập JML và dry-run/shadow khi phù hợp.
6. **Phê duyệt và triển khai có phiên bản:** rollback phải có kiểm soát, không tự khôi phục policy cho phép quá rộng.
7. **Theo dõi tác động:** số lượng Permit/Deny, bất thường, lỗi PDP, drift, ticket người dùng và sự kiện audit.

### Ngoại lệ cần được kiểm soát

Ví dụ nhân viên cần truy cập báo cáo đặc biệt trong hai ngày. Không nên sửa policy tổng thành “mọi FinanceViewer đều Permit export”. Nên có entitlement/exception:

- Nêu **subject, action, resource/tenant, căn cứ và phạm vi cụ thể**.
- Có owner/approval và điều kiện SoD.
- Có **startAt/endAt** rõ ràng; tự hết hiệu lực.
- Giữ nguyên Deny về Leaver, tenant isolation và các hard guard khác nếu không có cơ sở ngoại lệ riêng được phê duyệt.
- Có audit và định kỳ đối soát ngoại lệ chưa thu hồi.

Ngoại lệ mở quyền phải nhỏ hơn hoặc bằng phạm vi được phê duyệt. Không dùng một cờ `isException=true` để bỏ qua mọi ràng buộc.

## 16. Kiểm thử Permit và deny

Test authorization cần bao phủ **được phép**, **bị cấm**, **không có rule**, **lỗi/thiếu thuộc tính**, **đổi trạng thái giữa request** và **đường truy cập không qua UI**.

### Ma trận test cốt lõi

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| AUTHZ-01 | User ACTIVE có role đúng, cùng tenant, MFA đủ mức. | **Permit** với action/resource cụ thể. |
| AUTHZ-02 | User ACTIVE nhưng thiếu role được duyệt. | **Deny mặc định**. |
| AUTHZ-03 | User có role nhưng request tenant khác không hợp lệ. | **Deny** do tenant isolation. |
| AUTHZ-04 | User có FinanceApprover nhưng tự duyệt hóa đơn mình tạo. | **Deny** do SoD. |
| AUTHZ-05 | Không rule nào áp dụng. | **NotApplicable → không cho phép** tại PEP. |
| AUTHZ-06 | PIP không thể lấy trạng thái Leaver. | **Indeterminate/no access** theo chính sách; không tự Permit. |
| AUTHZ-07 | PDP timeout trong lúc thao tác xóa dữ liệu. | Không thực hiện thao tác; báo lỗi và audit phù hợp. |
| AUTHZ-08 | Joiner chưa đến ngày nhưng đã có IdP/SCIM User. | Không Permit API nghiệp vụ. |
| AUTHZ-09 | Mover gỡ SupportAdmin nhưng token/session còn role cũ. | Không được thực hiện hành động SupportAdmin sau khi policy có hiệu lực. |
| AUTHZ-10 | Leaver có JWT access token còn hạn. | Ngăn truy cập trong giới hạn revocation policy; đo residual access. |
| AUTHZ-11 | Rehire mở lại account cũ. | Không tự Permit các entitlement/grant cũ. |
| AUTHZ-12 | User sửa resource ID để đọc tài nguyên của người khác. | Deny nếu không có quyền object-level. |
| AUTHZ-13 | User được đọc object nhưng không được xem trường nhạy cảm. | Chỉ trả field được cho phép. |
| AUTHZ-14 | User có role mới nhưng thiếu approval đặc quyền. | Deny thao tác privileged. |
| AUTHZ-15 | Có Permit và Deny cùng áp dụng. | Kết quả theo combining semantics đã được phê duyệt. |
| AUTHZ-16 | Nhóm trong IdP được gỡ, app-local role còn hoạt động. | Phát hiện quyền tồn dư; test effective permission tại app. |
| AUTHZ-17 | Job Joiner version cũ retry sau Leaver. | Không cấp lại Permit/entitlement trái trạng thái mới nhất. |
| AUTHZ-18 | Access token dành cho resource A dùng gọi resource B. | Không chấp nhận token sai audience/scope. |
| AUTHZ-19 | Service principal staging gọi production API. | Deny theo environment, issuer/trust và scope. |
| AUTHZ-20 | Break-glass có phê duyệt và hết hạn. | Chỉ Permit đúng scope/time; Deny sau hạn, audit đầy đủ. |

### Given–When–Then minh họa

~~~gherkin
Feature: Authorization decisions follow IAM lifecycle

  Scenario: Permit valid read inside the assigned tenant
    Given an active FinanceViewer with tenant-b membership
    And a report owned by tenant-b
    When the user requests report.read
    Then the policy decision is Permit
    And the PEP exposes only permitted report fields

  Scenario: Deny access to another tenant
    Given an active FinanceViewer belongs to tenant-b
    And a report belongs to tenant-a
    When the user requests report.read
    Then the policy decision is Deny
    And the report is not returned

  Scenario: Leaver cannot keep a stale permission
    Given the user previously had SupportAdmin
    And an authoritative Leaver event has become effective
    When the user calls a privileged API using an old session
    Then the operation is denied according to revocation policy
    And access is checked at the resource enforcement point

  Scenario: Missing lifecycle data cannot become Permit
    Given the lifecycle provider is unavailable
    When the client requests a protected destructive action
    Then no protected action is performed
    And the failure is audited as indeterminate
~~~

### Kiểm thử negative phải kiểm tra hiệu ứng thực

Một response 403 chưa chứng minh hệ thống an toàn nếu dữ liệu đã bị sửa trước khi trả response. Với thao tác ghi, test cần:

- Đọc lại tài nguyên để chứng minh **không có side effect trái phép**.
- Kiểm tra audit ghi hành động bị từ chối, không ghi bí mật.
- Kiểm tra cả direct API, batch job, async consumer và admin endpoint.
- Thử thay subject, action, resource ID, tenant, phiên bản policy và thời điểm hiệu lực.
- Thử các lỗi thiếu thuộc tính, cache stale, sự kiện JML sai thứ tự và race giữa permission check với write.

## 17. Kiểm toán, quan sát và đối soát quyết định

Một hệ thống IAM cần chứng minh được **vì sao một hành động bị Permit hoặc Deny**, và quan trọng hơn, **quyết định có được thực thi đúng hay không**.

### Hồ sơ quyết định tối thiểu

| Trường | Mục đích |
| --- | --- |
| decisionId/correlationId | Liên kết request, PDP, PEP và thao tác thực tế. |
| identityId, issuer/sub, tenant | Xác định đúng chủ thể và ranh giới tin cậy. |
| action, resource type/ID | Biết quyền nào được xét trên tài nguyên nào. |
| decision và reason code | Phân biệt Permit, Deny, NotApplicable, Indeterminate. |
| policy ID/version, combining algorithm | Chứng minh tập quy tắc và cách ưu tiên đã áp dụng. |
| attribute source/version/observedAt | Đánh giá dữ liệu có đủ mới và tin cậy không. |
| JML event, sourceVersion/effectiveAt | Giải thích quyền tại thời điểm Joiner/Mover/Leaver. |
| authentication context/assurance | Chứng minh điều kiện MFA/step-up theo chính sách. |
| enforcement result/verifiedAt | Kiểm tra thao tác bị chặn hay đã thực thi đúng. |
| exception/approval reference | Truy vết các quyền tạm hoặc quyền đặc biệt. |

Ví dụ event nội bộ, **không phải schema chuẩn XACML/OIDC/SCIM**:

~~~json
{
  "eventType": "AUTHORIZATION_DECISION",
  "decisionId": "authz-dec-901",
  "identityId": "ID-LAN-104",
  "tenantId": "tenant-b",
  "action": "invoice.approve",
  "resourceRef": "INV-91",
  "decision": "Deny",
  "reasonCode": "SEPARATION_OF_DUTIES",
  "policyVersion": "finance-access-v9",
  "combiningAlgorithm": "deny-overrides",
  "lifecycleSourceVersion": 52,
  "evaluatedAt": "2026-12-01T09:20:01+07:00",
  "enforced": true,
  "correlationId": "req-77182"
}
~~~

Không log mật khẩu, access/refresh token nguyên vẹn, cookie, private key, thông tin tài chính hoặc dữ liệu cá nhân không cần thiết. Log cần giới hạn quyền đọc, tính toàn vẹn, thời hạn lưu giữ và có thể cần pseudonymization khi phù hợp.

### Những chỉ số cần theo dõi

| Chỉ số | Câu hỏi nó trả lời |
| --- | --- |
| **Permit/Deny rate theo action/resource** | Có thay đổi bất thường hoặc policy mở rộng ngoài dự kiến không? |
| **Indeterminate / PIP failure rate** | Bao nhiêu request không đánh giá được vì thiếu dữ liệu? |
| **Default deny hits** | Endpoint/role mới có bị thiếu policy hay đang bị truy cập trái phép? |
| **Explicit deny conflicts** | Bao nhiêu Permit bị hard guard/SoD chặn, cần chỉnh rule hay hành vi? |
| **Policy decision latency** | PDP có đáp ứng độ trễ ứng dụng không? |
| **Stale decision/cache incidents** | Có quyết định Permit từ dữ liệu cũ sau Mover/Leaver không? |
| **Residual access after Leaver** | Có hành động nào vẫn thành công sau mốc thu hồi không? |
| **Cross-tenant denial violations** | Có request chéo tenant bị thực thi trái policy không? |
| **Unapproved privilege grants** | Có Permit nào thiếu approval hoặc step-up bắt buộc không? |
| **Policy coverage** | Bao nhiêu endpoint, queue consumer và API đã có PEP? |

**Tỷ lệ Deny cao không tự chứng minh hệ thống tốt hoặc xấu**: có thể là dấu hiệu chặn tấn công, nhưng cũng có thể do rule sai chặn người dùng hợp lệ. Phải kết hợp bằng chứng, tác động nghiệp vụ và threat model.

### Reconciliation và đánh giá quyền thực tế

Một policy có thể Deny chính xác nhưng ứng dụng vẫn Permit vì:

1. Một endpoint không tích hợp PEP.
2. App dùng local role không đồng bộ từ IAM.
3. Cache giữ quyết định cũ sau Mover.
4. JWT access token cũ vẫn được API chấp nhận offline.
5. Job nền dùng service credential quá rộng và không kiểm tra authorization.

Vì thế, reconciliation phải so sánh **desired access** với **observed effective access**, không chỉ xác nhận User/Group ở IdP hoặc SCIM. Cần test thực sự tại tài nguyên trong môi trường được phép, kết hợp log và inventory để xác minh chặn truy cập đúng phạm vi.

## 18. Tình huống thực hành

### Tình huống A — User đăng nhập thành công nhưng thiếu quyền

**Bối cảnh:** Minh đăng nhập CRM bằng MFA. Minh có role CRMReader nhưng gọi API xóa khách hàng.

**Câu hỏi:** Kết quả và lớp kiểm soát nào quyết định?

**Gợi ý:** Authentication có thể thành công, nhưng authorization phải Deny `customer.delete` theo default deny/role policy. PEP tại API ngăn mọi side effect; ẩn nút Delete ở UI là chưa đủ.

### Tình huống B — Mover giữ role trong token

**Bối cảnh:** Lan chuyển từ Support sang Finance; IAM/SCIM đã gỡ SupportAdmin. Access token JWT cũ vẫn chứa role đó và API kiểm chữ ký offline.

**Câu hỏi:** Vì sao policy trung tâm Deny nhưng API vẫn có thể cho thao tác?

**Gợi ý:** API không quan sát trạng thái JML/quyền hiện hành và tiếp tục tin claim lỗi thời. Cần đánh giá token TTL, policy lookup, cache invalidation/revoke và kiểm tra effective authorization tại resource.

### Tình huống C — Mâu thuẫn Permit và Deny

**Bối cảnh:** Lan có FinanceApprover nên policy RBAC Permit invoice.approve, nhưng hóa đơn do chính Lan tạo nên SoD Deny.

**Câu hỏi:** Kết quả đúng là gì?

**Gợi ý:** Nếu chính sách yêu cầu không tự duyệt, kết quả phải Deny. Thiết kế combining rule/hard guard phải bảo đảm Deny bắt buộc thắng trong phạm vi này; test conflict trực tiếp.

### Tình huống D — Thiếu tenant thuộc resource

**Bối cảnh:** PDP nhận request đọc báo cáo nhưng PIP không lấy được tenantId của báo cáo vì database timeout.

**Câu hỏi:** Có nên Permit vì User có role FinanceViewer không?

**Gợi ý:** Không. Tenant isolation chưa được chứng minh; phân loại Indeterminate, không thực hiện đọc dữ liệu, retry/cảnh báo và trả lỗi phù hợp.

### Tình huống E — Leaver và endpoint thiếu PEP

**Bối cảnh:** HR phát Leaver, IdP khóa login và PDP trung tâm có rule Deny. Tuy nhiên endpoint export dữ liệu cũ không gọi PDP mà chỉ kiểm tra API key.

**Câu hỏi:** Đã thu hồi quyền chưa?

**Gợi ý:** Chưa đầy đủ. Quy tắc chỉ có hiệu lực tại PEP thực thi; phải bảo vệ endpoint export, thu hồi API key, kiểm tra session/token và audit truy cập sau Leaver.

### Tình huống F — Công việc khẩn cấp và break-glass

**Bối cảnh:** PDP mất kết nối khi đội vận hành cần xử lý sự cố production. Kỹ sư đề nghị “cho Permit mọi request admin khi PDP timeout”.

**Câu hỏi:** Có chấp nhận được không?

**Gợi ý:** Không. Cần quy trình break-glass được phê duyệt trước, phạm vi và thời hạn nhỏ, xác thực mạnh, audit độc lập và cơ chế cưỡng chế riêng, không tự biến mọi lỗi PDP thành quyền admin.

### Tình huống G — Đối tượng đổi owner trong lúc ghi

**Bối cảnh:** Người dùng được Permit cập nhật một ticket vì đang được phân công, nhưng trước khi transaction ghi, ticket được chuyển cho người khác.

**Câu hỏi:** Rủi ro nằm ở đâu?

**Gợi ý:** TOCTOU giữa kiểm tra quyền và thực thi. Cần transaction/conditional update hoặc kiểm tra lại ownership ở thời điểm ghi theo mô hình dữ liệu và mức rủi ro.

## 19. Câu hỏi tự kiểm tra

**1. Permit có chứng minh User đã xác thực đúng và còn trạng thái ACTIVE không?**

Không tự động. Permit chỉ đáng tin khi policy input đã được xác thực, còn hiệu lực và đầy đủ; authentication và lifecycle là các điều kiện hoặc nguồn dữ liệu phải được kiểm tra rõ.

**2. NotApplicable khác gì Deny?**

NotApplicable nghĩa không có policy áp dụng; Deny là kết quả của rule từ chối. Ở điểm thực thi dùng default deny, cả hai đều không được cấp quyền, nhưng log và nguyên nhân khác nhau.

**3. Khi PDP không lấy được tenantId, có được Permit vì role phù hợp không?**

Không. Khi thuộc tính cần thiết không xác minh được, phải từ chối/thông báo lỗi theo chính sách, không tự cấp quyền.

**4. Một role có quyền invoice.read có mặc nhiên được invoice.approve không?**

Không. Hành động khác nhau cần quyền và điều kiện riêng, kể cả SoD hoặc step-up.

**5. Explicit deny có luôn thắng Permit trong mọi hệ thống policy không?**

Không. Nó phụ thuộc policy combining và semantics của nền tảng; muốn Deny ưu tiên phải thiết kế/kiểm thử rõ.

**6. Vì sao ẩn nút Delete ở frontend không bảo vệ đủ?**

Vì client có thể gọi API trực tiếp; PEP ở server/resource boundary phải kiểm tra và cưỡng chế quyền.

**7. SCIM gỡ Group của User sau Mover thì token cũ có tự mất role không?**

Không mặc định. Token/phiên có thể chứa claim lỗi thời; cần kiểm soát authorization đủ mới tại ứng dụng.

**8. Sau Leaver, rule Deny trung tâm đã có, nhưng API dùng JWT offline và không hỏi trạng thái. Có an toàn chưa?**

Chưa. Phải xử lý đường thực thi, token/session, revocation boundary và xác minh quyền truy cập thực tế.

**9. Vì sao service account cần policy Permit/Deny riêng?**

Vì workload có chủ thể, owner, trust, scope, environment và vòng đời riêng; không dùng máy móc HR role hoặc browser session của con người.

**10. Một quyết định Permit có obligation ghi audit bắt buộc nhưng hệ thống log không hoạt động. Có được tiếp tục không?**

Không được tự bỏ obligation bắt buộc. Hệ thống phải làm theo chính sách thực thi, có thể chặn hành động hoặc áp cơ chế dự phòng được thiết kế và phê duyệt trước.

## Ghi nhớ

- **Permit** cho phép một **subject** thực hiện **action** trên **resource** theo **context** và chính sách; **Deny** chặn yêu cầu. Authentication thành công không tự đồng nghĩa Permit.
- **Deny tường minh**, **default deny**, **NotApplicable** và **Indeterminate** khác nhau về ý nghĩa; khi không đủ cơ sở cho phép, **PEP không được tự mở quyền**.
- **PDP** quyết định, **PEP** thực thi, **PAP** quản trị policy và **PIP** cung cấp thuộc tính đáng tin. Quyết định trung tâm không hữu ích nếu API không cưỡng chế nó.
- **RBAC/ABAC, tenant isolation, SoD, thời hạn và authentication assurance** phải được đánh giá trên đúng tài nguyên; combining semantics phải được lựa chọn và kiểm thử có chủ đích.
- **Joiner** chỉ nhận quyền đúng ngày và đúng phạm vi; **Mover** mất quyền cũ và cần phê duyệt quyền mới; **Leaver** phải bị từ chối kể cả qua token, phiên hoặc account cục bộ còn tồn.
- **IdP/SSO, SCIM, session, token và policy cache** thuộc các lớp khác nhau; không thể suy ra quyền thực tế chỉ từ login thành công hoặc một API provisioning trả thành công.
- **Least privilege, default deny, fail-closed có kiểm soát, readback, kiểm thử âm, kiểm toán và reconciliation** là nền tảng để authorization thay đổi chính xác cùng vòng đời danh tính và giảm quyền truy cập tồn dư.
