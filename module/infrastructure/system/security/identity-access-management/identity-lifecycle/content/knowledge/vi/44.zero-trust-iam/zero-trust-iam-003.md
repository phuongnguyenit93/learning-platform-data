# Least privilege access — Quyền truy cập tối thiểu trong Zero Trust IAM

> **Chương:** Zero Trust IAM  
> **Chủ đề:** Least privilege access (nguyên tắc đặc quyền tối thiểu)  
> **Phạm vi:** Quản lý vòng đời danh tính IAM theo mô hình **Joiner–Mover–Leaver (JML)**: từ xác minh, tạo danh tính, cấp quyền, rà soát đến thay đổi hoặc thu hồi quyền. Bài học liên hệ IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **quyền tối thiểu**, **chỉ biết những gì cần biết (need-to-know)**, **phân tách nhiệm vụ (Separation of Duties — SoD)** và **truy cập đúng lúc (Just-in-Time — JIT)**.
2. Mô tả quyền truy cập theo **chủ thể, tài nguyên, hành động, phạm vi, điều kiện và thời hạn**, rồi xác định những quyền thừa trong một trường hợp thực tế.
3. Kết hợp **RBAC** để thể hiện năng lực công việc, **ABAC** để thu hẹp ngữ cảnh/phạm vi, và kiểm tra quan hệ tài nguyên khi cần.
4. Thiết kế cấp quyền và thu hồi qua các sự kiện **Joiner, Mover, Leaver**, có phê duyệt, đối soát và xử lý tài khoản/phiên/token tồn dư.
5. Áp dụng quyền tối thiểu cho **tài khoản đặc quyền, workload identity, service account, API, dữ liệu và cloud resource**.
6. Kiểm thử và đo lường xem hệ thống đang thực thi quyền tối thiểu hay chỉ thể hiện trên danh sách quyền được gán.

## 2. Least privilege access thực chất là gì?

**Principle of Least Privilege (PoLP)** yêu cầu mỗi người dùng, dịch vụ hoặc tiến trình chỉ được cấp **những khả năng cần thiết** để hoàn thành nhiệm vụ được ủy quyền, **trên những tài nguyên cần thiết**, **trong thời gian cần thiết**.

Một cách ghi nhớ là:

**Đúng chủ thể × đúng hành động × đúng tài nguyên × đúng phạm vi × đúng thời điểm × đúng điều kiện.**

Ví dụ: nhân viên hỗ trợ An cần xem ticket của khách hàng thuộc nhóm mình và thêm bình luận. An không tự động cần quyền xuất mọi dữ liệu khách hàng, xóa hàng loạt ticket hoặc cấu hình toàn bộ hệ thống. Khi An chuyển sang nhóm kế toán, quyền Support cũ cần được rà soát và thu hồi theo thời điểm có hiệu lực.

Quyền tối thiểu là một nguyên tắc của **Zero Trust**, phối hợp với xác minh tường minh và giả định khả năng bị xâm nhập. Nếu tài khoản bị đánh cắp, phạm vi quyền nhỏ làm giảm những gì kẻ tấn công có thể thực hiện; nếu nhân viên vô tình thao tác sai, hệ thống cũng hạn chế tác động.

### Không chỉ đếm số vai trò

Một người có một vai trò duy nhất tên **super_admin** có thể nguy hiểm hơn người có bốn quyền hẹp (xem ticket, bình luận, cập nhật trạng thái và xem báo cáo nhóm). Số lượng role không nói lên mức độ tối thiểu; phải đánh giá **hành động thực tế, tài nguyên, phạm vi và thời hạn**.

| Câu hỏi | Quyền quá rộng | Quyền tối thiểu hơn |
|---|---|---|
| Ai có quyền? | Tất cả nhân viên nội bộ | Nhóm được giao nhiệm vụ hoặc workload riêng |
| Thực hiện việc gì? | read/write/delete/admin | Chỉ read và comment |
| Với dữ liệu nào? | Mọi tenant và mọi dự án | Tenant A, ticket đã được giao |
| Trong bao lâu? | Vĩnh viễn | Theo thời hạn hợp đồng, nhiệm vụ hoặc phiên JIT |
| Trong điều kiện nào? | Bất cứ thiết bị/phiên nào | Phiên đủ mức xác thực, điều kiện thiết bị phù hợp |
| Khi đổi vai trò? | Giữ mọi quyền cũ rồi cộng quyền mới | Thu hồi quyền không còn cần, cấp bộ quyền mới |

**Điểm cần phân biệt:** quyền tối thiểu không có nghĩa giảm quyền đến mức người dùng không hoàn thành công việc. Hệ thống cần quy trình **yêu cầu, phê duyệt, cấp có thời hạn và thu hồi** đủ nhanh để đáp ứng công việc hợp lệ mà không duy trì quyền cao thường trực.

## 3. Các khái niệm thường đi cùng quyền tối thiểu

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| **Least privilege** | Giới hạn khả năng của chủ thể theo nhiệm vụ | Support chỉ được sửa ticket nhóm mình |
| **Need-to-know** | Giới hạn dữ liệu cần thấy cho mục đích đã được phép | Có quyền xử lý ticket nhưng không thấy dữ liệu thanh toán đầy đủ |
| **Separation of Duties (SoD)** | Tránh một chủ thể tự thực hiện mọi bước có thể dẫn tới gian lận/sai sót | Người tạo lệnh thanh toán không tự phê duyệt chính lệnh đó |
| **Just-in-Time (JIT)** | Cấp quyền cao trong khoảng thời gian ngắn khi thực sự cần | Trưởng ca được elevation 30 phút để xử lý sự cố |
| **Just-Enough-Administration (JEA)** | Giới hạn tập lệnh/hành động quản trị được phép | Được khởi động lại một dịch vụ, không được thay chính sách IAM |
| **Privileged Access Management (PAM)** | Quản lý việc sử dụng tài khoản/phiên đặc quyền | Phê duyệt, cấp phiên, ghi nhận, kết thúc quyền admin |
| **Time-bound access** | Quyền có thời điểm bắt đầu/kết thúc xác định | Quyền nhà thầu hết hạn cuối ngày 30 |
| **Access review / recertification** | Xác nhận quyền còn phù hợp và thu hồi phần không cần | Quản lý rà soát quyền hệ thống tài chính theo kỳ |
| **Deny by default** | Không có chính sách cho phép đủ điều kiện thì từ chối | API từ chối action export chưa được cấp |

Các cơ chế bổ sung cho nhau. Ví dụ RBAC có thể cấp quyền nền tảng ở quy mô lớn, ABAC hạn chế tenant và dữ liệu, SoD loại bỏ tổ hợp nguy hiểm, JIT giới hạn thời gian sử dụng quyền cao, còn quy trình JML bảo đảm các quyền thay đổi theo quan hệ công việc.

## 4. Mô hình hóa một quyền trước khi cấp

Thay vì chỉ lưu chuỗi “admin = true”, hãy mô tả **entitlement** hoặc tập quyền bằng các chiều cụ thể.

| Chiều | Cần mô tả | Ví dụ |
|---|---|---|
| **Subject** | Danh tính người, nhóm hoặc workload, chủ sở hữu | usr-204, svc-billing-reconcile |
| **Action** | Thao tác có ý nghĩa nghiệp vụ | invoice.read, invoice.approve, customer.export |
| **Resource** | Loại và định danh tài nguyên | Invoice inv-801, bucket reports-prod |
| **Scope** | Tenant, nhóm, dự án, đơn vị, môi trường | tenant = T1; environment = staging |
| **Conditions** | Mức xác thực, thiết bị, trạng thái, SoD, độ nhạy | user active, device compliant, creator != approver |
| **Time** | Hiệu lực, TTL, sự kiện kết thúc | 09:00–09:30 hoặc đến khi ticket đóng |
| **Authority / owner** | Ai có thể phê duyệt hoặc thu hồi | Quản lý nghiệp vụ, chủ sở hữu dữ liệu |

Một quyền được cấp có thể mô tả dưới dạng:

~~~yaml
# Ví dụ khái niệm để thảo luận, không phải cú pháp của sản phẩm IAM cụ thể.
grant:
  subject_id: usr-204
  action: invoice.read
  resource_type: invoice
  constraints:
    tenant_id: tenant-T1
    business_unit: finance
    environment: production
    subject_status: active
  effective_from: "2026-11-23T09:00:00Z"
  expires_at: "2026-12-23T09:00:00Z"
  approved_by: manager-12
  justification: "Đối soát hóa đơn tháng"
  request_id: access-req-731
~~~

**Chỉ lưu grant chưa đủ để bảo vệ API.** Dịch vụ phải thực thi chính sách tại thời điểm request, đối chiếu action với resource cụ thể, sử dụng thuộc tính do hệ thống đáng tin cung cấp và phản ánh trạng thái hiện hành của quyền.

### Quyền được gán, quyền có hiệu lực và quyền thực sự sử dụng

Ba tập này không hoàn toàn trùng nhau:

- **Assigned entitlements:** quyền thấy ở IdP, nhóm, role hoặc cấu hình dịch vụ.
- **Effective permissions:** khả năng thực tế khi tính cả quyền được kế thừa, group lồng nhau, resource policy, điều kiện, các đường truy cập khác và quy tắc ưu tiên deny.
- **Used permissions:** những hành động đã thực sự được ghi nhận, có thể giúp phát hiện quyền không sử dụng.

Ví dụ tài khoản nằm trong nhóm read_only nhưng lại có quyền admin qua một role kế thừa trong cloud account; thực tế tài khoản có đặc quyền cao hơn danh sách read_only cho thấy. **Đánh giá PoLP phải xem effective permissions**, không chỉ tên role trực tiếp.

“Chưa từng dùng” là tín hiệu cần rà soát, không tự chứng minh quyền phải bị xóa: có những quyền dành cho khôi phục sự cố hiếm khi dùng. Với trường hợp này, JIT/break-glass có thể là cách giảm đặc quyền thường trực.

## 5. RBAC, ABAC và kiểm soát theo quan hệ

### 5.1. RBAC: bắt đầu từ vai trò nghiệp vụ

**Role-Based Access Control (RBAC)** nhóm các hành động theo trách nhiệm công việc. Ví dụ:

| Vai trò | Hành động cơ bản | Ngoại lệ cần chú ý |
|---|---|---|
| support_agent | ticket.read, ticket.comment, ticket.update_status | Chỉ ticket được giao/đúng tenant |
| finance_analyst | invoice.read, invoice.reconcile | Không được approve payment |
| finance_approver | payment.review, payment.approve | Không phê duyệt giao dịch do chính mình tạo |
| platform_operator | service.status, service.restart | Không mặc định có quyền sửa IAM/policy |
| security_auditor | audit.read, policy.read | Không có quyền xóa log hoặc chỉnh sửa policy |

RBAC tốt cần có **role owner**, mô tả mục đích, bộ quyền chuẩn, người phê duyệt, tần suất rà soát, ngày kết thúc nếu phù hợp và quy trình thay đổi. Nếu thêm mọi ngoại lệ riêng lẻ thành role mới, có thể gặp **role explosion**: số role quá lớn khiến việc hiểu quyền thực tế khó khăn.

### 5.2. ABAC: thu hẹp theo thuộc tính

**Attribute-Based Access Control (ABAC)** bổ sung điều kiện gắn với subject, resource, action và context. Ví dụ support_agent chỉ xem được ticket khi:

- Tài khoản đang active;
- Ticket nằm trong **cùng tenant** với người dùng;
- Ticket được giao cho nhóm của người dùng hoặc có uỷ quyền hợp lệ;
- Hành động là read/comment, không phải bulk_export;
- Ngữ cảnh truy cập đạt yêu cầu bảo vệ dữ liệu.

Chính sách RBAC + ABAC phù hợp khi nhiều người có cùng vai trò nhưng phạm vi tài nguyên khác nhau. Trong hệ thống có quan hệ phức tạp giữa người dùng và tài nguyên, có thể bổ sung **relationship-based checks (ReBAC)** để kiểm tra assigned_to, owns, member_of... Việc lựa chọn không làm thay đổi nguyên tắc: chính sách phải được thực thi ở nơi thao tác xảy ra.

### 5.3. Policy mẫu có deny mặc định

~~~text
ALLOW invoice.read IF
    subject.status == "active"
    AND subject.hasRole("finance_analyst")
    AND subject.tenantId == resource.tenantId
    AND resource.businessUnit IN subject.allowedBusinessUnits
    AND request.context.meetsRequiredAssurance
OTHERWISE DENY

ALLOW payment.approve IF
    subject.status == "active"
    AND subject.hasRole("finance_approver")
    AND subject.id != resource.createdBy
    AND subject.tenantId == resource.tenantId
    AND approvalWindow.isActive
OTHERWISE DENY
~~~

Đây là **pseudocode**, không phải cú pháp engine chuẩn. SoD, tenant và thời hạn phải được ràng buộc bằng dữ liệu đáng tin: nếu client có thể tự gửi owner hoặc tenant bất kỳ, kiểm tra này mất ý nghĩa.

### 5.4. Tài nguyên, hành động và dữ liệu đều có phạm vi

Quyền cấp cao ở endpoint không tự tạo quyền trên toàn bộ dữ liệu. Một API có thể chấp nhận role support_agent ở router nhưng phải kiểm tra sâu hơn khi tải từng ticket.

Ví dụ:

- GET /tickets/T-77: kiểm tra ticket T-77 thuộc tenant được phép và người dùng có quan hệ xử lý hợp lệ.
- POST /tickets/T-77/comments: kiểm tra thêm quyền comment, trạng thái ticket còn cho phép ghi.
- POST /tickets/export: yêu cầu quyền export riêng và giới hạn dữ liệu xuất theo tenant/quyền ở **từng bản ghi**.

Kiểm soát theo đối tượng giúp tránh **Broken Object Level Authorization (BOLA/IDOR)**; kiểm soát chức năng giúp tránh người dùng gọi thao tác không thuộc nhiệm vụ. Cần kết hợp cả hai.

## 6. Vòng đời Joiner–Mover–Leaver là nền tảng của quyền tối thiểu

Một tập quyền từng hợp lý có thể trở nên thừa khi nhiệm vụ thay đổi. Quyền tối thiểu vì vậy là **trạng thái phải được duy trì**, không phải công việc cấp quyền một lần.

| Giai đoạn | Mục tiêu quyền tối thiểu | Công việc quan trọng | Bằng chứng cần có |
|---|---|---|---|
| **Joiner** — gia nhập | Cấp đúng quyền nền tảng khi đủ điều kiện | Xác minh danh tính, gán role theo vị trí, phê duyệt ngoại lệ, xác định thời hạn | Nguồn nhân sự/hợp đồng, manager, scope, lịch sử phê duyệt |
| **Mover** — chuyển vai trò | Bỏ quyền cũ, cấp quyền mới theo nhiệm vụ | Tính desired state, thu hồi role không còn hợp lệ, xử lý quyền trực tiếp và token | Diff trước/sau, xác nhận ứng dụng đích, kiểm thử quyền cũ |
| **Leaver** — rời đi | Chặn truy cập và loại bỏ mọi quyền còn sử dụng được | Disable, revoke sessions/tokens, deprovision, thu hồi key và delegation | Mốc thời gian, xác nhận chặn tại từng hệ thống, alert lỗi |
| **Periodic review** — rà soát | Loại bỏ quyền thừa tích lũy | Đối chiếu job/owner với effective permissions, hỏi người chịu trách nhiệm | Quyết định keep/revoke, hành động thực tế và ngày hoàn tất |

### 6.1. Joiner: từ nghiệp vụ tới entitlement

Giả sử bạn mới tuyển Lan vào nhóm Support, làm việc với tenant A. Quy trình hợp lý:

1. **Nguồn đáng tin** xác nhận Lan là nhân viên, ngày có hiệu lực, manager, tenant và nhóm.
2. IAM tạo **subject ID ổn định**, xác minh danh tính và đăng ký xác thực mạnh theo yêu cầu.
3. Bộ quyền chuẩn support_agent tạo quyền đọc/bình luận ticket theo tenant A; hệ thống cấp tài khoản/nhóm qua IdP và SCIM/API tới ứng dụng.
4. Quyền truy cập production database, bulk export hoặc chỉnh policy cần workflow riêng có lý do, phê duyệt và thời hạn.
5. API vẫn kiểm tra mỗi tài nguyên và hành động; được tạo user trong ứng dụng không có nghĩa được truy cập mọi ticket.

Ví dụ yêu cầu “cấp quyền admin để tiện xử lý ticket” nên được tách thành các tác vụ cụ thể: xem chi tiết ticket, sửa trạng thái, khôi phục ticket lỗi. Tác vụ hiếm có thể dùng **JIT/JEA** thay vì admin thường trực.

### 6.2. Mover: đối soát desired và actual thay vì cộng dồn quyền

Bình chuyển từ Support sang Finance. Trước khi chuyển, quyền thực tế là:

~~~text
Actual trước chuyển:
  ticket.read[tenant-A]
  ticket.update[tenant-A]
  customer.export[tenant-A] (ngoại lệ tạm thời đã hết hạn)

Desired sau chuyển:
  invoice.read[tenant-A]
  invoice.reconcile[tenant-A]
~~~

Từ đó tạo **kế hoạch thay đổi**:

~~~text
To remove:
  ticket.read[tenant-A]
  ticket.update[tenant-A]
  customer.export[tenant-A]   # Quyền quá hạn, phải thu hồi

To add (sau khi đủ phê duyệt):
  invoice.read[tenant-A]
  invoice.reconcile[tenant-A]

To investigate:
  mọi quyền kế thừa, grant trực tiếp, tài khoản cục bộ,
  token/refresh token còn mang quyền cũ
~~~

Với công việc cần chuyển giao, có thể thiết kế **thời gian chồng lấp được phê duyệt**, phạm vi hẹp, có ngày kết thúc và kiểm tra SoD. Không biến “chuyển vai trò” thành quy tắc mặc định luôn giữ quyền cũ.

Một bước kỹ thuật hay bị quên là **độ trễ đồng bộ**. HR cập nhật vai trò và IdP đã gỡ group nhưng ứng dụng SaaS hoặc access token cũ vẫn chứa quyền cũ. Phải theo dõi đến khi **truy cập thực tế bị chặn**, không chỉ đến khi lệnh SCIM trả về thành công.

### 6.3. Leaver: quyền tối thiểu cuối cùng là không còn quyền

Với người rời tổ chức hoặc nhà thầu hết hợp đồng, quy trình cần chặn:

- **Đường đăng nhập:** disable tài khoản ở IdP/ứng dụng, ngăn đăng nhập mới, kết thúc phiên khi hỗ trợ.
- **Quyền ứng dụng:** xóa nhóm, role, quyền trực tiếp, chia sẻ trực tiếp và ủy quyền.
- **Token/credential:** thu hồi refresh token, API key, PAT, SSH key, secret, quyền cloud và chứng chỉ gắn với người rời đi; xử lý giới hạn của access token đã phát hành.
- **Danh tính phụ:** tài khoản local không dùng SSO, service account do người dùng sở hữu, bot và integration.
- **Cơ sở vật chứng:** audit theo nguồn sự kiện, tài khoản đích và mốc xác nhận chặn; báo động khi việc thu hồi thất bại.

**Khóa tài khoản ở IdP không nhất thiết làm access token JWT tự chứa hết hiệu lực ngay.** Nếu API chỉ kiểm tra chữ ký và expiration, token có thể tiếp tục được chấp nhận đến hết hạn. Cần lựa chọn thời hạn token, thu hồi phiên/refresh token, introspection, tra cứu trạng thái quyền hoặc cơ chế truyền sự kiện phù hợp mức rủi ro.

**Không đồng nhất thu hồi quyền với xóa dữ liệu:** hồ sơ tài chính, lịch sử thao tác và audit có thể cần lưu theo chính sách. Nên chuyển quyền sở hữu tài nguyên cần vận hành, bảo toàn bằng chứng và chặn quyền truy cập đã hết ủy quyền.

## 7. Luồng cấp, sử dụng và thu hồi quyền

Một luồng đầu cuối cần có cả **đường quản trị quyền** và **đường thực thi quyền**:

~~~mermaid
flowchart TD
    A["Sự kiện JML / yêu cầu truy cập"] --> B["Xác định công việc, action, resource, scope, thời hạn"]
    B --> C{"Chính sách quyền chuẩn hoặc cần phê duyệt?"}
    C -->|"Quyền chuẩn đủ điều kiện"| D["Tạo desired entitlements"]
    C -->|"Ngoại lệ/đặc quyền"| E["Owner dữ liệu và quản lý phê duyệt, kiểm tra SoD"]
    E --> D
    D --> F["IAM / IdP / SCIM hoặc API cập nhật quyền"]
    F --> G["Đối soát với quyền thực tế ở đích"]
    G --> H{"Có lệch hoặc lỗi cập nhật?"}
    H -->|"Có"| I["Cảnh báo, retry, xử lý thủ công có kiểm soát"]
    I --> G
    H -->|"Không"| J["Quyền sẵn sàng theo ngày hiệu lực"]
    J --> K["Request tới ứng dụng / PEP"]
    K --> L{"PDP/Backend: subject + action + resource + context"}
    L -->|"Allow"| M["Thực thi trong phạm vi cho phép và ghi audit"]
    L -->|"Deny / Step-up"| N["Chặn hoặc yêu cầu điều kiện bổ sung; ghi audit"]
    M --> O["Hết hạn, Mover, Leaver hoặc access review"]
    N --> O
    O --> P["Thu hồi quyền/phiên và xác minh chặn truy cập"]
~~~

Ở các kiến trúc cụ thể, IdP, policy engine, quyền ứng dụng và backend có thể phân tán trên nhiều nền tảng. **Provisioning thành công không thay thế kiểm tra authorization** ở service, và **một quyết định allow không thể được dùng vô hạn định** cho mọi request về sau.

### Mô hình ba lớp để chống lệch quyền

1. **Desired entitlements:** những quyền người dùng *nên có* theo vai trò, phạm vi và ngoại lệ được phê duyệt.
2. **Actual assigned/effective permissions:** quyền *đang tồn tại và có hiệu lực* trong IdP, SaaS, cloud, database và ứng dụng.
3. **Observed access:** thử nghiệm/telemetry chứng minh request có thể hoặc không thể sử dụng quyền.

Nếu desired state đã xóa quyền nhưng actual/effective state còn cho phép, quá trình thu hồi chưa hoàn tất. Nếu assigned permission đã xóa nhưng một token còn hiệu lực hoặc đường truy cập thứ cấp vẫn cho phép, cần xử lý tiếp.

## 8. JIT, JEA và PAM để giảm đặc quyền thường trực

Người vận hành đôi khi cần quyền cao để điều tra sự cố. Việc cấp **admin thường trực** làm tăng nguy cơ bị lạm dụng và phạm vi tác động nếu phiên bị chiếm.

Giải pháp là chuyển một phần quyền cao sang **quyền ngắn hạn và giới hạn chức năng**.

### 8.1. Một yêu cầu JIT minh họa

Kỹ sư Hạnh cần quyền restart dịch vụ production để xử lý sự cố INC-291:

1. Hạnh gửi yêu cầu ghi rõ **lệnh restart**, **dịch vụ**, **môi trường production**, **ticket** và **thời hạn 20 phút**.
2. Hệ thống kiểm tra Hạnh còn active, nằm trong nhóm vận hành được ủy quyền, phiên đủ mức MFA và không vi phạm SoD.
3. Người có thẩm quyền hoặc automation theo chính sách phê duyệt; PAM cấp quyền **service.restart** đúng môi trường, gắn TTL.
4. Hạnh dùng phiên hoặc token ngắn hạn để thực hiện restart; các hành động sửa IAM, đọc secret hoặc xóa database bị từ chối.
5. Khi TTL kết thúc, hệ thống gỡ quyền, chấm dứt phiên/elevation phù hợp và đối soát kết quả; log lưu subject, tài nguyên, ticket, policy và thời gian.

**JIT giới hạn thời gian; JEA giới hạn hành động.** Nên kết hợp khi có thể, thay vì chỉ rút ngắn thời gian sử dụng một vai trò admin toàn quyền.

### 8.2. Break-glass dùng khi không thể theo luồng thông thường

Với sự cố nghiêm trọng như IdP/PAM mất khả dụng, tổ chức có thể cần tài khoản hoặc quy trình **break-glass** đã được phê duyệt và bảo vệ riêng. Nguyên tắc:

- Số lượng và phạm vi quyền tối thiểu cần thiết cho tình huống khẩn cấp.
- Credential được bảo vệ mạnh, có owner, chỉ dùng khi có sự kiện cho phép; không dùng cho công việc hằng ngày.
- Truy cập có kiểm toán, cảnh báo, rà soát sau sự cố, quay vòng credential khi cần.
- Định kỳ kiểm thử khả năng khôi phục mà không mở rộng quyền thường trực.

Thiết kế break-glass không nên trở thành đường vòng để người dùng né quy trình cấp quyền hợp lệ.

### 8.3. Quyền cao và ràng buộc phân tách nhiệm vụ

Ví dụ trong hệ thống thanh toán:

- Người tạo lệnh được tạo/sửa lệnh ở trạng thái draft.
- Người phê duyệt có thể duyệt lệnh hợp lệ trong phạm vi được phân công.
- **Người tạo không được phê duyệt chính lệnh đó**, dù họ có đủ hai role trong các bối cảnh khác nhau.
- Quản trị viên hạ tầng không mặc định được sửa dữ liệu nghiệp vụ hoặc xóa audit của hệ thống thanh toán.

SoD cần được kiểm tra ở **quyền và tình huống thực tế**, không chỉ bằng tên hai role. Một tài khoản có thể có đường truy cập gián tiếp hoặc quyền kế thừa khiến quy tắc SoD bị vượt qua nếu chỉ nhìn cấu hình trực tiếp.

## 9. Quyền tối thiểu cho tài khoản dịch vụ và workload identity

**Service account, CI/CD, máy chủ, workload trong container, job xử lý dữ liệu và tích hợp bên thứ ba** cũng là các chủ thể trong IAM. Rủi ro thường gặp: token sống lâu, secret chung cho nhiều dịch vụ, quyền cloud wildcard và không có người chịu trách nhiệm.

Thiết kế quyền tối thiểu cho workload:

| Yếu tố | Phương án ưu tiên | Điều cần tránh |
|---|---|---|
| Danh tính | Mỗi workload/hệ thống và môi trường có principal riêng | Một tài khoản robot dùng chung cho production và staging |
| Xác thực | Workload identity federation, chứng thực ngắn hạn, mTLS khi phù hợp | API key admin không hết hạn trong mã nguồn |
| Scope | Chỉ audience/API, resource và action cần thiết | Wildcard toàn bộ tài nguyên hay quyền quản trị gốc |
| Ownership | Ghi owner, mục đích, thời hạn và nguồn phê duyệt | Tài khoản mồ côi sau khi dự án kết thúc |
| Vòng đời | Rotate/revoke khi đổi workload, retire service, thay owner | Để credential tồn tại sau decommission |
| Quan sát | Audit service principal, action, data scope, correlation ID | Không biết tiến trình nào dùng token |

Ví dụ một job chỉ đọc file báo cáo theo ngày cần quyền list/get trong đúng thư mục/bucket đã quy định. Không nên cho job quyền xóa toàn bộ bucket hoặc cấp role quản trị tài khoản cloud để “tránh lỗi permission”.

Cũng cần phân biệt **quyền cấp cho pipeline** và **quyền của ứng dụng sau deploy**: runner có thể được phép đẩy artifact trong release window, trong khi ứng dụng đang chạy chỉ cần đọc cấu hình hoặc tài nguyên nghiệp vụ. Đừng truyền credential cấp quyền triển khai cho container runtime.

### Quyền theo đối tượng và điều kiện trong cloud

Cloud IAM có thể hỗ trợ role, policy điều kiện, resource policy, permission boundaries, organization policies hoặc cơ chế tương tự. Hiệu lực thực tế phụ thuộc **ngữ nghĩa hợp nhất và deny** của từng nền tảng. Không kết luận “ít quyền” chỉ vì một policy mới rất hẹp nếu principal vẫn có quyền rộng qua role hoặc group khác.

Ví dụ policy minh họa (không phải policy của nhà cung cấp cụ thể):

~~~yaml
workload: svc-nightly-report
resource:
  type: object_storage
  bucket: finance-reports
  prefix: tenant-A/daily/
allow_actions:
  - object.read
  - object.list
conditions:
  environment: production
  audience: reports-api
expires_with: workload_registration
default: deny
~~~

**Thử nghiệm quyền hiệu lực** phải xác minh job đọc được đối tượng cần thiết và bị từ chối khi thử ghi/xóa hoặc truy cập prefix khác.

## 10. Thực thi ở API và tầng dữ liệu

Đặc quyền tối thiểu cần được thiết kế **từ bên trong dịch vụ**, vì tài nguyên cuối cùng thường chứa thuộc tính mà gateway không biết đầy đủ: tenant, owner, trạng thái nghiệp vụ, độ nhạy hoặc người tạo giao dịch.

### 10.1. Pseudocode cho endpoint đọc invoice

~~~java
// Ví dụ minh họa trách nhiệm kiểm tra; chưa phải mã production.
InvoiceView readInvoice(AuthenticatedPrincipal principal, String invoiceId) {
    Invoice invoice = invoiceRepository.findById(invoiceId)
        .orElseThrow(NotFoundException::new);

    SubjectState subject = identityService.currentState(principal.subjectId());
    AccessContext context = accessContextService.fromTrustedSignals(principal);

    Decision decision = authorization.decide(
        subject,
        "invoice.read",
        invoice.authorizationAttributes(),  // tenant, owner, classification...
        context
    );

    audit.recordDecision(principal.subjectId(), "invoice.read", invoiceId, decision);

    if (!decision.isAllowed()) {
        throw new AccessDeniedException("Not permitted");
    }

    return invoiceViewMapper.toAuthorizedView(invoice, subject);
}
~~~

Trong thực tế cần chọn cách trả lỗi phù hợp để không tiết lộ sự tồn tại của tài nguyên; kiểm soát race condition, transaction boundary, phân trang/filtering và việc che trường dữ liệu nhạy cảm.

Quan trọng: **không lấy tenant ID đáng tin chỉ từ header hoặc tham số do client tự truyền**. Dữ liệu phạm vi phải được xác minh qua subject và tài nguyên ở nguồn đáng tin. Nếu endpoint cho phép export hàng loạt, cần lọc từng bản ghi/tập dữ liệu theo quyền, không chỉ kiểm tra một cờ export ở đầu request.

### 10.2. “Deny by default” trong việc mở chức năng

Khi thêm action mới như invoice.bulkDelete, hệ thống không nên tự động cho tất cả user có role finance sử dụng. Chủ sở hữu chính sách cần đánh giá:

- Action này có hợp lý trong vai trò hiện tại không?
- Tài nguyên nào được phép tác động và số lượng tối đa là bao nhiêu?
- Có yêu cầu phê duyệt, step-up, SoD hoặc xác nhận hai người không?
- Việc thu hồi/quyền hết hạn được kiểm thử như thế nào?
- Audit cần lưu thông tin gì mà không lộ dữ liệu nhạy cảm?

Chính sách nên có **version** và quy trình kiểm thử trước khi phát hành để tránh cấp rộng ngoài ý muốn.

### 10.3. Phòng lỗ hổng do bypass tầng kiểm tra

Quyền tối thiểu sẽ thất bại nếu ứng dụng chặn UI nhưng API vẫn cho phép gọi trực tiếp. Cần áp dụng kiểm tra ở backend, thống nhất cho REST, GraphQL, job nền và các đường truy cập khác. Không dựa vào việc ẩn nút “Delete” hoặc “Export” trên giao diện.

Một số hệ quản trị dữ liệu có cơ chế row-level/column-level security; đây là lớp phòng thủ bổ sung, nhưng phải cấu hình chính xác identity propagation và tránh việc service dùng chung một tài khoản database đủ quyền đọc mọi tenant mà không có kiểm soát khác.

## 11. Thu hồi quyền phải tính tới token, cache và đồng bộ

Trong hệ thống phân tán, **quyền đã bị xóa ở control plane** chưa chắc đã mất hiệu lực ngay ở mọi điểm truy cập. Cần lập ngân sách thời gian thu hồi cho từng loại quyền.

~~~text
09:00  HRIS/manager duyệt chuyển vai trò
09:01  IAM tính quyền mới và yêu cầu gỡ quyền cũ
09:02  IdP cập nhật group
09:05  SCIM cập nhật ứng dụng đích (hoặc lỗi và cần retry)
09:10  Người dùng gọi API bằng token phát hành lúc 08:50
10:00  Token cũ hết hạn nếu không có cơ chế chặn sớm
~~~

Nếu API chỉ tin role trong JWT, việc gỡ group lúc 09:02 có thể không ngăn request lúc 09:10. Hệ thống cần chọn một hoặc nhiều cơ chế: access token có tuổi phù hợp, hủy refresh token/phiên, introspection, tra cứu trạng thái/role hiện tại, thông báo thay đổi quyền, policy cache có TTL giới hạn hoặc deny list phù hợp.

### SLA thu hồi nên bám theo rủi ro

- Với quyền production administrator hoặc xuất dữ liệu nhạy cảm: yêu cầu thu hồi nhanh, đường chặn đủ mạnh và kiểm chứng tại điểm truy cập.
- Với quyền xem dữ liệu ít nhạy cảm: có thể cân nhắc chiến lược cache có hạn nếu đáp ứng yêu cầu đã phê duyệt.
- Với nhà thầu hoặc tài khoản tự động: ngày kết thúc phải có hiệu lực ngay cả khi không có người gửi sự kiện thu hồi thủ công.
- Với hệ thống SaaS offline hoặc tích hợp lỗi: cần theo dõi ngoại lệ, chặn bằng phương án phụ nếu khả thi và không tự đánh dấu hoàn tất.

**SCIM hỗ trợ provisioning/deprovisioning**, nhưng không là công cụ duy nhất ra quyết định quyền trên mỗi request. Tính đúng của quyền tối thiểu cần được xác nhận ở **nơi hành động thực sự được thực thi**.

### Nếu nguồn policy hoặc identity không khả dụng

Không mặc định “allow” khi PDP/nguồn quyền bị lỗi. Tùy phân loại thao tác, hệ thống có thể fail closed, yêu cầu step-up hoặc áp dụng cache đã được phê duyệt trong thời hạn và phạm vi rất hẹp. Các phương án này phải được diễn tập, đo lường và ghi audit để tránh vô tình mở rộng quyền khi hạ tầng sự cố.

## 12. Rà soát quyền và quản lý ngoại lệ

Dù đã có tự động hóa JML, quyền vẫn tích lũy qua dự án tạm thời, nhóm lồng nhau, cấp quyền thủ công, tích hợp SaaS và credential cá nhân. Cần rà soát quyền thường xuyên theo độ nhạy, tránh xác nhận hình thức.

### Quy trình access review có hiệu quả

1. **Thu thập effective permissions** từ IdP, SaaS, cloud, database, ứng dụng và hệ thống quản lý secret; nhận diện quyền gián tiếp, role kế thừa, grant trực tiếp.
2. **Đối chiếu desired entitlements:** vị trí, hợp đồng, dự án, owner, ngày hết hạn, phân tách nhiệm vụ và ngoại lệ.
3. **Đưa cho người hiểu nhu cầu nghiệp vụ** danh sách grant có ngữ cảnh: subject, action, resource, dữ liệu nhạy cảm, lần sử dụng gần đây và lý do cấp.
4. **Ghi quyết định:** keep/revoke/modify, người phê duyệt, lý do, thời điểm hoàn tất và thời hạn xem lại.
5. **Thực thi và xác minh:** thực sự gỡ quyền, xác nhận hệ thống đích và kiểm thử những đường truy cập quan trọng.
6. **Cải tiến role/policy chuẩn:** nếu thường xuyên cấp ngoại lệ giống nhau, đánh giá lại role hoặc cơ chế JIT, không nhân bản grant thủ công.

Những quyền không sử dụng lâu ngày là ứng viên để rà soát. Tuy nhiên, nếu quyền phục vụ cứu hộ/khôi phục hiếm dùng, nên thiết kế **đường khẩn cấp được bảo vệ** thay vì xóa tùy tiện.

### Ngoại lệ phải có vòng đời riêng

Mọi ngoại lệ nên ghi ít nhất:

| Trường | Câu hỏi |
|---|---|
| Request ID / ticket | Vì sao cần cấp quyền? |
| Requestor, owner, approver | Ai yêu cầu, ai chịu trách nhiệm, ai chấp thuận? |
| Action, resource, scope | Cụ thể được làm gì ở đâu? |
| Business justification | Nhiệm vụ và rủi ro nào đã được đánh giá? |
| Effective window | Có hiệu lực từ khi nào đến khi nào? |
| SoD / compensating control | Có xung đột nhiệm vụ không, có biện pháp kiểm soát bù không? |
| Audit & revocation confirmation | Đã dùng ra sao, đã thu hồi thật chưa? |

Quyền tạm thời thiếu thời hạn dễ trở thành quyền vĩnh viễn. Phê duyệt của quản lý cũng không tự biến quyền cấp quá rộng thành an toàn; chính sách nên kiểm tra phạm vi tài nguyên và sự cần thiết của action.

## 13. Các anti-pattern cần nhận diện

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| Gán admin để “đỡ lỗi permission” | Mở rộng khả năng thao tác và phạm vi tấn công | Xác định permission thiếu thực sự, cấp action/resource hẹp |
| Role duy nhất cho mọi nhân viên | Không tách nhiệm vụ và phạm vi dữ liệu | Thiết kế role theo công việc, gắn ABAC/resource checks |
| Giữ quyền sau Mover | Tích lũy quyền, SoD bị phá vỡ | So sánh desired–actual, thu hồi quyền cũ có xác nhận |
| Chỉ disable user tại IdP khi Leaver | Phiên, API key, local account hoặc SaaS vẫn hoạt động | Thu hồi đa kênh, đối soát và kiểm thử đường truy cập |
| Cấp quyền dựa vào tenant do client gửi | Có thể truy cập chéo tenant/BOLA | Lấy tenant từ nguồn backend đáng tin |
| Chỉ ẩn chức năng trên UI | API vẫn bị gọi trực tiếp | Kiểm tra AuthZ ở backend/PEP cho mỗi action cần thiết |
| Một service account cho nhiều job | Khó truy nguồn và thu hồi; blast radius lớn | Workload principal riêng, scope tối thiểu, credential quản lý tốt |
| Dùng JWT role cũ làm nguồn sự thật mãi | Quyền đã gỡ vẫn được thực thi | Giới hạn lifetime, thu hồi hoặc kiểm tra trạng thái hiện tại |
| Rà soát quyền bằng cách “approve all” | Quyền tồn dư bị hợp thức hóa | Cung cấp ngữ cảnh và buộc xử lý quyền mồ côi/quá hạn |
| Không log chính sách và kết quả deny | Không chứng minh được kiểm soát | Ghi policy version, resource/action và correlation ID |
| Dùng root/admin để chạy workload | Lộ credential dẫn đến tác động toàn hệ thống | Role riêng theo job, giới hạn quyền triển khai và runtime |

### Phân biệt một số nhầm lẫn

**“Deny all” không đồng nghĩa với least privilege.** Nếu người dùng bị từ chối mọi thao tác hợp lệ, hệ thống không thực hiện được công việc. Mục tiêu là **mức quyền nhỏ nhất đủ để hoàn thành nhiệm vụ được phép**, cộng khả năng nâng quyền có kiểm soát khi phát sinh nhu cầu.

**“Đã phê duyệt” không tự chứng minh scope đúng.** Người phê duyệt có thể đồng ý về mục tiêu nghiệp vụ nhưng không nhận ra role “admin” rộng hơn nhiều so với action thực tế. Workflow nên hiển thị **effective permissions** mà grant sẽ tạo ra.

**“Có quyền đọc API” không tự suy ra quyền xem mọi dữ liệu.** Tenant, ownership, classification và quan hệ phải được xét khi truy vấn tài nguyên, đặc biệt khi ứng dụng đa thuê bao (multi-tenant).

## 14. Kiểm toán và chỉ số xác nhận quyền tối thiểu

Một chương trình PoLP cần trả lời được **ai có quyền, vì sao có, dùng ở đâu, ai duyệt, khi nào hết hạn và đã thu hồi thành công chưa**.

### Event audit minh họa

~~~json
{
  "timestamp": "2026-11-23T10:35:00Z",
  "event_type": "entitlement_revoked",
  "subject_id": "usr-204",
  "action": "customer.export",
  "resource_scope": "tenant-A",
  "reason": "mover_role_change",
  "request_id": "jml-847",
  "approved_by": "manager-12",
  "target_system": "crm",
  "target_confirmed": true,
  "effective_at": "2026-11-23T10:34:52Z",
  "correlation_id": "evt-912d"
}
~~~

Bản ghi này chỉ là minh họa. **target_confirmed = true** nghĩa ứng dụng đích đã xác nhận yêu cầu cập nhật, nhưng chưa tự chứng minh token hoặc đường truy cập thứ cấp đã hết khả năng sử dụng. Cần kiểm tra quan sát runtime với các quyền trọng yếu.

Audit nên ghi policy ID/version, subject ID, action, resource/scope, kết quả allow/deny, reason code, thời hạn quyền và mốc thu hồi; đồng thời **không ghi mật khẩu, access token, private key, secret hay nguyên văn dữ liệu nhạy cảm**.

### Chỉ số nên có

| Chỉ số | Định nghĩa thực dụng | Vì sao hữu ích |
|---|---|---|
| **Privileged access footprint** | Số principal có quyền cao thường trực, phân theo hệ thống | Phát hiện bề mặt đặc quyền lớn |
| **Just-in-Time coverage** | Tỷ lệ phiên/quyền cao được cấp có thời hạn qua JIT | Đo mức giảm đặc quyền thường trực |
| **Unused/high-risk entitlement rate** | Quyền rộng hoặc lâu không sử dụng, đã phân loại rủi ro | Ưu tiên rà soát, không tự động kết luận thừa |
| **Desired–actual drift** | Chênh lệch giữa quyền đáng có và quyền đang hiệu lực | Phát hiện provisioning lỗi, cấp quyền thủ công, role kế thừa |
| **Revocation latency** | Thời gian từ Mover/Leaver/hết hạn đến lúc quyền không thể dùng | Đo chất lượng thực thi thu hồi, gồm p95/p99 |
| **Orphaned identities/credentials** | Danh tính/credential thiếu owner hoặc quan hệ hợp lệ | Phát hiện quyền tồn dư dễ bị bỏ quên |
| **Exception expiry compliance** | Tỷ lệ ngoại lệ được gỡ đúng hạn và xác nhận | Kiểm soát quyền tạm thời |
| **SoD violation count** | Trường hợp có tổ hợp quyền/xử lý giao dịch xung đột | Đo rủi ro gian lận và sai sót |
| **Denied cross-scope attempts** | Yêu cầu vượt tenant/owner/scope bị chặn | Chứng minh kiểm soát chạy tại điểm truy cập |

Đặt mục tiêu theo độ nhạy và SLA của tổ chức, có owner và kế hoạch xử lý ngoại lệ. Không đánh giá chất lượng quyền tối thiểu chỉ bằng “100% ứng dụng dùng SSO” hoặc “đã mở màn hình access review”.

## 15. Ma trận kiểm thử thực tế

Có thể kiểm tra một policy bằng các trường hợp **được phép** và **phải bị từ chối**:

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| P1 | support_agent đọc ticket được giao, đúng tenant | **Allow** |
| P2 | support_agent đọc ticket tenant khác | **Deny** |
| P3 | support_agent gọi bulk_export dù có quyền ticket.read | **Deny** |
| P4 | finance_approver phê duyệt payment do chính mình tạo | **Deny** theo SoD |
| P5 | Kỹ sư có elevation JIT service.restart trong thời hạn | **Allow** chỉ action/resource đã duyệt |
| P6 | Kỹ sư thử user.manage khi chỉ có JIT service.restart | **Deny** |
| P7 | Sau TTL JIT, lặp lại service.restart với phiên/token cũ | **Deny** trong SLA thu hồi đã định |
| P8 | Mover dùng role/token cũ truy cập hệ thống trước đây | **Deny** sau thời điểm thu hồi có hiệu lực/SLA |
| P9 | Leaver dùng local account hoặc API key còn lưu | **Deny** sau thu hồi; cảnh báo nếu tìm thấy đường còn mở |
| P10 | Workload đọc đúng prefix nhưng thử xóa bucket | **Deny** hành động delete |
| P11 | SCIM thất bại khi gỡ role | Ghi lỗi, retry/cảnh báo, không ghi nhận đã thu hồi hoàn tất |
| P12 | PDP mất khả dụng khi yêu cầu export nhạy cảm | **Deny/fail closed** theo thiết kế |

Trong thử nghiệm, cần kiểm tra **effective permission và dữ liệu trả về**, không chỉ HTTP status của endpoint. Ví dụ API export trả 200 nhưng xuất cả dữ liệu tenant khác thì chính sách vẫn thất bại.

**Kiểm thử thu hồi phải có mốc thời gian:** event JML xảy ra lúc nào, các đích được cập nhật lúc nào, request cuối cùng còn được allow lúc nào, và quyền bị chặn hoàn toàn lúc nào. Đó là cách chứng minh SLA thu hồi có ý nghĩa.

## 16. Bài tập tình huống: tìm và sửa quyền thừa

### Bối cảnh

Công ty quản lý ba hệ thống: CRM, Finance và Cloud Console. Người dùng Trâm từng là trưởng nhóm Support của tenant A. Ngày 23/11, Trâm chuyển sang Finance. Hệ thống ghi nhận:

- Group mới: finance_analyst; các quyền **invoice.read** và **invoice.reconcile** được phê duyệt cho tenant A.
- Group cũ: support_manager đã được gỡ ở IdP, nhưng ứng dụng CRM chưa đồng bộ nhóm mới.
- Token CRM của Trâm được phát hành trước giờ chuyển vai trò và còn hạn 60 phút.
- Một quyền **customer.export** đã cấp thủ công sáu tháng trước và chưa có ngày hết hạn.
- Trâm còn quyền **cloud.admin** vì từng hỗ trợ một sự cố production.
- Một script đối soát do Trâm tạo đang dùng API key cá nhân để đọc dữ liệu hằng đêm.

### Nhiệm vụ

1. Xác định quyền nào **cần giữ**, quyền nào **cần thu hồi** và quyền nào cần **chuyển sang danh tính workload**.
2. Nêu tối thiểu bốn kiểm tra để chắc chắn quyền CRM cũ không còn sử dụng được.
3. Thiết kế quyền JIT/JEA thay cho cloud.admin thường trực nếu Trâm đôi khi phải xử lý sự cố.
4. Mô tả dữ liệu cần lưu để một lần rà soát sau này biết tại sao các quyền hiện tại tồn tại.
5. Đặt hai chỉ số theo dõi để phát hiện quyền truy cập tồn dư sau Mover.

### Lời giải tham khảo

**1. Phân loại quyền.** Giữ quyền Finance đã được phê duyệt và giới hạn theo tenant A. Thu hồi support_manager, customer.export thủ công không còn nhu cầu và cloud.admin thường trực; kiểm tra mọi quyền kế thừa/cấp trực tiếp khác. Script nên được chuyển sang workload identity riêng, có owner và chỉ có quyền **đọc phạm vi dữ liệu cần đối soát**. Thu hồi API key cá nhân sau khi chuyển an toàn, có xác minh script hoạt động bằng principal mới.

**2. Xác nhận CRM đã chặn.** Đối soát quyền actual tại CRM; thử token CRM cũ gọi endpoint được phép trước đây; kiểm tra refresh token/phiên CRM và tài khoản cục bộ nếu có; thử export/ticket API theo tenant và action; theo dõi quyết định allow/deny cùng thời gian xử lý. Đặt alert cho lỗi SCIM và thực thi biện pháp chặn bổ sung nếu cần.

**3. Thiết kế quyền quản trị tạm thời.** Tách action cần dùng như service.restart hoặc view_logs.production, yêu cầu ticket sự cố, MFA đạt chính sách, người phê duyệt phù hợp, giới hạn scope và TTL; tự thu hồi khi hết hạn và ghi audit. Không cấp quyền quản trị toàn cloud chỉ để đọc log.

**4. Lưu bằng chứng.** Subject ID, role, action, resource/scope, nguồn sự kiện JML, lý do nghiệp vụ, ticket, approver, thời điểm hiệu lực/hết hạn, policy version, owner, xác nhận provisioning và revocation.

**5. Chỉ số.** Đo **revocation latency p95** từ Mover đến khi CRM từ chối quyền cũ; theo dõi **số quyền lệch desired–actual/quyền cao thường trực chưa có owner hoặc expiry**. Dùng kết quả để cải thiện chính sách và tự động hóa.

## 17. Checklist áp dụng và tài liệu tham khảo

### Checklist

- [ ] Mỗi role có **mục đích, owner, actions, resource scope và người phê duyệt** rõ ràng.
- [ ] Hành động nhạy cảm và tài nguyên có giới hạn quyền riêng; mặc định từ chối khi không đủ điều kiện.
- [ ] Quyền ở tầng API được kiểm tra theo **subject + action + resource + context**; backend không tin tenant/client tự khai báo.
- [ ] Joiner chỉ nhận quyền chuẩn cần thiết; ngoại lệ có lý do, phê duyệt và TTL.
- [ ] Mover gỡ quyền cũ, xử lý SoD, privilege kế thừa và token/quyền tồn dư.
- [ ] Leaver chặn đăng nhập, phiên, token, local account, key và quyền ở ứng dụng đích.
- [ ] Có đối soát desired entitlements với assigned/effective permissions và kiểm chứng runtime.
- [ ] Quyền cao dùng JIT/JEA/PAM khi phù hợp; break-glass có kiểm soát và audit.
- [ ] Service account/workload có danh tính riêng, quyền hẹp, owner, vòng đời và credential được quản lý.
- [ ] Access review xử lý quyền quá hạn, quyền thừa và ngoại lệ thay vì “approve all”.
- [ ] Có kiểm thử cross-tenant, BOLA, SoD, token cũ, SCIM lỗi và fail-closed cho tác vụ nhạy cảm.
- [ ] Theo dõi revocation latency, privilege footprint, quyền mồ côi và lỗi đối soát.

### Nguồn tham khảo để học sâu

- **NIST SP 800-207 — Zero Trust Architecture:** nguyên tắc truy cập dựa trên chính sách, kiểm tra tường minh và giới hạn quyền.
- **NIST SP 800-53 — Security and Privacy Controls:** nhóm kiểm soát AC, đặc biệt AC-2 (Account Management), AC-5 (Separation of Duties) và AC-6 (Least Privilege).
- **NIST SP 800-63 — Digital Identity Guidelines:** khái niệm định danh và xác thực phù hợp với mức rủi ro.
- **RFC 7643 / RFC 7644 — SCIM:** mô hình và giao thức đồng bộ người dùng/nhóm.
- **OWASP API Security Top 10:** các lỗi ủy quyền ở cấp đối tượng/chức năng và quản lý truy cập API.

**Điều cần nhớ:** Least privilege access là khả năng chứng minh rằng **mỗi người dùng và workload chỉ có quyền cần cho nhiệm vụ hiện tại, chỉ trên tài nguyên được phép, trong phạm vi và thời hạn hợp lý**. Muốn đạt mục tiêu này, IAM phải cấp quyền theo vai trò/ngữ cảnh, **thu hồi kịp thời qua JML**, thực thi ở điểm truy cập thực tế và đo lường được quyền còn tồn dư.
