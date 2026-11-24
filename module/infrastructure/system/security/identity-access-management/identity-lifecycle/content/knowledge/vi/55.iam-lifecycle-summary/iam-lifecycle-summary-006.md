# Bước học tiếp theo sau IAM lifecycle

> **Chương:** Tổng kết IAM lifecycle  
> **Định hướng:** Biến kiến thức quản lý vòng đời danh tính trong **Identity and Access Management (IAM)** thành khả năng thiết kế, triển khai, kiểm thử và vận hành hệ thống thực tế. Nội dung tiếp nối **Joiner–Mover–Leaver (JML)**, xác minh danh tính, cấp/thu hồi quyền, **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm **quyền truy cập tồn dư**.

## 1. Học gì sau khi đã nắm được vòng đời danh tính?

Sau khi học IAM lifecycle, người học thường có thể trình bày rằng **Joiner** tạo tài khoản/quyền cho người mới, **Mover** cập nhật và thu hồi quyền cũ, **Leaver** chặn truy cập khi quan hệ kết thúc. Bước tiếp theo là chứng minh những điều này bằng một thiết kế chạy được và bằng chứng có thể kiểm tra.

Một hệ thống IAM tốt không dừng ở lệnh “tạo user thành công”. Với mỗi sự kiện cần trả lời:

1. **Nguồn:** Sự kiện từ đâu, chủ thể được xác minh thế nào, mốc hiệu lực có đáng tin?
2. **Quyết định:** Chính sách nào xác định quyền hợp lệ, ai chịu trách nhiệm phê duyệt?
3. **Thực thi:** IdP, ứng dụng, cloud, account local, token và service identity cần đổi ra sao?
4. **Đối soát:** Trạng thái thực tế đã khớp mục tiêu chưa, có đường truy cập khác còn hiệu lực không?
5. **Bằng chứng:** Có thể giải thích ai làm gì, ở đâu, vì sao và khi nào, bao gồm các lỗi còn mở?

Nên chuyển mục tiêu học từ **ghi nhớ thuật ngữ** sang **xây được một vòng kiểm soát có thể đo và thử lại**. Người học không cần một nền tảng IAM thương mại để bắt đầu; có thể dùng mô phỏng hoàn toàn bằng dữ liệu giả, API thử nghiệm và một IdP trong môi trường lab được phép.

### 1.1. Kết quả mong đợi của lộ trình

| Cấp độ | Bạn làm được gì? | Bằng chứng cụ thể |
| --- | --- | --- |
| **Giải thích** | Phân biệt danh tính, account, credential, role, entitlement, token và session | Sơ đồ có chú thích đường xác thực và đường cấp phát |
| **Áp dụng** | Xác định quyền mục tiêu của một Joiner/Mover/Leaver | Bảng chính sách, ma trận quyền và kết quả tính chênh lệch |
| **Triển khai** | Viết workflow cập nhật account/quyền có xử lý lỗi | Chương trình hoặc mô phỏng event → desired → actual |
| **Kiểm chứng** | Chạy kiểm thử cấp, thu hồi, retry, sự kiện sai thứ tự | Kết quả test và snapshot quyền thực tế |
| **Vận hành** | Xử lý lỗi connector, app offline, quyền tồn dư, review quá hạn | Runbook, cảnh báo, hồ sơ ngoại lệ và chỉ số |
| **Thiết kế** | Giải thích lựa chọn IdP, SCIM/API, RBAC/ABAC, phương án phục hồi | Tài liệu kiến trúc, ranh giới tin cậy và quyết định thiết kế |

Không nhất thiết học tất cả trong một lần. Hãy chọn cấp độ tiếp theo dựa trên điều bạn **có thể tạo ra và kiểm chứng**, thay vì số lượng khái niệm đã đọc.

## 2. Tự đánh giá trước khi chọn bài tiếp theo

Dùng bảng dưới đây như một phép đo năng lực ban đầu. Chấm **0** nếu chưa giải thích được, **1** nếu giải thích được nhưng chưa thực hành, **2** nếu đã thực hành có kết quả, **3** nếu có thể giải thích lỗi và hướng khắc phục dựa trên bằng chứng.

| Năng lực | Bài tự kiểm tra |
| --- | --- |
| **Nguồn danh tính** | Vì sao không nên dùng email làm ID duy nhất? Người quay lại làm việc được xử lý thế nào? |
| **JML** | Với một sự kiện Mover, bạn tìm được quyền mới, quyền cũ và thời điểm phải thay đổi không? |
| **IdP & SSO** | Bạn giải thích được khác nhau giữa phiên IdP, phiên ứng dụng và access token không? |
| **SCIM & provisioning** | Bạn xác định được khả năng tạo, sửa, disable và truy vấn tài khoản của một app không? |
| **RBAC & ABAC** | Bạn thiết kế được role tối thiểu và điều kiện giới hạn theo tenant/team/dữ liệu không? |
| **Quyền hiệu lực** | Khi xóa một nhóm nhưng quyền vẫn còn, bạn tìm được direct grant hoặc đường cấp khác không? |
| **Service identity** | Bạn tìm được owner, scope và cách thu hồi credential của một pipeline không? |
| **Lỗi phân tán** | Bạn ngăn được job Mover cũ cấp lại quyền sau Leaver không? |
| **Đối soát** | Bạn chứng minh được quyền thực tế ở app khớp quyền được duyệt bằng readback không? |
| **Kiểm toán** | Bạn xác định được eventId, policyVersion, approver, target và thời điểm hoàn tất không? |

Tổng điểm tối đa minh họa là **30**. Điểm này chỉ để tự theo dõi, không phải chứng chỉ hoặc chuẩn đánh giá chính thức. Hãy chọn **hai hoặc ba hàng có điểm thấp nhất** để lên lịch thực hành.

### 2.1. Nếu chưa chắc nền tảng

Hãy làm lại ba bài nhỏ:

1. Vẽ đường từ **HRIS/sponsor → IAM/IGA → IdP → SCIM/API → ứng dụng → kiểm toán**, chỉ rõ cái gì là sự kiện, cái gì là quyết định và cái gì là trạng thái thực tế.
2. Lập bảng quyền cho **nhân viên Support, Finance và quản trị viên** với tối thiểu một ràng buộc không cho tự phê duyệt giao dịch.
3. Giải thích một Leaver đã disable ở IdP nhưng vẫn có phiên SaaS và PAT cá nhân: quyền nào còn, ai chịu trách nhiệm và kiểm tra bằng gì?

Nếu làm được cả ba và nêu rõ giới hạn của bằng chứng, bạn đã đủ nền tảng để triển khai bài lab.

## 3. Lộ trình thực hành theo bốn chặng

Thời lượng dưới đây chỉ là **gợi ý để chia việc**, có thể rút ngắn hoặc kéo dài theo trải nghiệm, quy mô lab và thời gian thực tế. Người học có thể chuyển chặng khi đạt tiêu chí hoàn thành, không cần chờ đúng số ngày.

| Chặng | Trọng tâm | Sản phẩm cần tạo | Điều kiện chuyển chặng |
| --- | --- | --- | --- |
| **A. Mô hình hóa** | Nguồn danh tính, trạng thái JML, ma trận quyền và owner | Event schema, role catalog, sơ đồ vòng đời | Xử lý bằng lời được ít nhất ba tình huống JML |
| **B. Kết nối và thực thi** | IdP, SSO, provisioning SCIM/API, RBAC/ABAC | Workflow mô phỏng và hai hệ đích thử nghiệm | Mỗi grant/revoke có thể đọc lại trạng thái đích |
| **C. Kiểm soát thất bại** | Idempotency, retry, sự kiện sai thứ tự, quyền tồn dư | Bộ ca kiểm thử và cơ chế đối soát | Lỗi không tạo account trùng hoặc cấp lại quyền sai |
| **D. Vận hành và kiểm toán** | Access review, service identity, KPI, runbook | Dashboard/ báo cáo, audit trail, runbook | Giải thích được mọi ngoại lệ còn mở và chủ sở hữu |

~~~mermaid
flowchart LR
    A["A. Mô hình hóa<br/>Sự kiện + policy"] --> B["B. Thực thi<br/>IdP + app + provisioning"]
    B --> C["C. Kiểm thử<br/>Lỗi + quyền tồn dư"]
    C --> D["D. Vận hành<br/>Đối soát + kiểm toán"]
    D --> E["Dự án tổng hợp<br/>JML end-to-end"]
    E -->|Cải tiến nhờ đo lường| A
~~~

Mỗi chặng có một câu hỏi kiểm tra chung: **“Nếu một yêu cầu thay đổi quyền thất bại hoặc xảy ra muộn, ta có biết quyền hiệu lực cuối cùng và đưa hệ thống về trạng thái đúng không?”**

## 4. Chặng A — Mô hình hóa danh tính và quyền

### 4.1. Dựng mô hình dữ liệu tối thiểu

Chọn một tình huống giả định: công ty có nhân viên, nhà thầu, CRM và ứng dụng tài chính. Dùng dữ liệu giả lập hoàn toàn, tránh dùng thông tin nhân sự thật.

| Thực thể | Trường gợi ý | Mục đích |
| --- | --- | --- |
| **Identity** | subjectId, type, status, managerId, sponsorId, department | Biết ai là chủ thể và thuộc quan hệ nào |
| **LifecycleEvent** | eventId, subjectId, eventType, effectiveAt, sourceVersion | Theo dõi thay đổi có nguồn, thứ tự và thời điểm |
| **AccountLink** | subjectId, targetSystem, targetAccountId | Đối chiếu một chủ thể với nhiều account |
| **Entitlement** | entitlementId, resource, action, scope, riskTier | Định nghĩa quyền có thể cấp |
| **RolePolicy** | role, entitlementIds, conditions, version | Tính quyền mong muốn |
| **Approval** | requestId, approver, decision, scope, expiresAt | Giải trình quyền ngoài role chuẩn |
| **ProvisioningTask** | eventId, target, desiredState, status, attempts | Giao việc và xử lý lỗi từng đích |
| **Evidence** | eventId, target, actualState, verifiedAt, owner | Chứng minh kết quả và sai lệch |

Chú ý ba quy tắc khi mô hình hóa:

- **subjectId** phải ổn định; email, tên hiển thị, bộ phận và manager là những thuộc tính có thể thay đổi.
- **effectiveAt** phải có thông tin múi giờ; không nhầm thời điểm nhận webhook với thời điểm nghiệp vụ có hiệu lực.
- **targetAccountId** có thể khác subjectId, vì IdP và SaaS thường có khóa tài khoản riêng.

### 4.2. Mẫu sự kiện thực hành

~~~json
{
  "eventId": "HR-LAB-0007",
  "subjectId": "EMP-LAB-042",
  "eventType": "MOVER",
  "effectiveAt": "2026-12-05T09:00:00+07:00",
  "sourceVersion": 12,
  "employmentStatus": "active",
  "attributes": {
    "department": "Finance",
    "role": "Finance-Analyst",
    "managerId": "EMP-LAB-009"
  }
}
~~~

Dữ liệu trên chỉ để học; đây là **envelope nghiệp vụ tự định nghĩa**, không phải JSON schema chuẩn của SCIM. Thêm các sự kiện Joiner, Mover và Leaver cho cùng subjectId, kèm một sự kiện trùng và một sự kiện tới trễ.

### 4.3. Thiết kế ma trận quyền có thể kiểm thử

| Role | CRM ticket | Báo cáo tài chính | Phê duyệt thanh toán | Xuất dữ liệu khách hàng |
| --- | --- | --- | --- | --- |
| **Support-Agent** | Đọc/sửa ticket thuộc team | Không | Không | Không |
| **Finance-Analyst** | Không | Đọc trong phạm vi tenant | Không | Không |
| **Payment-Approver** | Không | Đọc trong phạm vi nghiệp vụ | Được duyệt trong phạm vi, có kiểm tra SoD | Không |
| **Data-Exporter** | Chỉ theo yêu cầu riêng | Theo phạm vi phê duyệt | Không | Có hạn, có chủ dữ liệu phê duyệt |

Sau đó xác định một policy ABAC ví dụ: chủ thể phải đang hoạt động, **subject.tenantId bằng resource.tenantId**, thiết bị đáp ứng điều kiện cần thiết và resource thuộc phạm vi được giao. Role chỉ là **một phần** của quyết định quyền.

### 4.4. Câu hỏi để tự kiểm tra chặng A

1. Nếu nhân viên từ Support sang Finance, tập quyền nào cần **revoke**, tập nào cần **grant**?
2. Nếu người dùng đổi email, account CRM liên kết với danh tính có bị tạo trùng không?
3. Nếu ứng dụng hỗ trợ nhiều nhóm cùng cấp một quyền, khi gỡ một nhóm còn kiểm tra gì?
4. Nếu người dùng vừa tạo vừa duyệt cùng giao dịch, policy SoD ngăn ở lúc cấp role hay lúc xử lý giao dịch?

**Bằng chứng hoàn thành:** bảng mô hình đủ trường, ba sự kiện JML, một policy version và ma trận quyền có ca kiểm thử dương tính/âm tính.

## 5. Chặng B — Kết nối IdP, SSO và provisioning

Mục tiêu của chặng này là phân biệt ba vấn đề thường bị trộn lẫn:

- **Xác thực:** IdP/SSO trả lời ai đang đăng nhập, credential và MFA có hợp lệ không.
- **Provisioning:** SCIM/API hoặc tác vụ thủ công tạo, cập nhật và vô hiệu hóa account.
- **Authorization:** hệ đích đánh giá role, ACL, thuộc tính, hành động và tài nguyên.

### 5.1. Lab 1 — Một tài khoản, hai ứng dụng

Thiết lập hoặc mô phỏng:

1. **Nguồn HR giả lập** phát sự kiện Joiner/Mover/Leaver.
2. **IdP** lưu account, trạng thái người dùng và nhóm; có thể là mock trong lab.
3. **CRM giả lập** hỗ trợ tạo, sửa, disable user và đọc lại role.
4. **Ứng dụng Finance giả lập** giữ entitlement riêng và API đọc quyền.
5. **Bộ điều phối IAM** nhận sự kiện, tính desired state và gọi từng target.
6. **Audit store** ghi request ID, kết quả và readback.

Chưa cần xây giao diện hoàn chỉnh; một CLI hoặc tập request tự động đủ để học luồng dữ liệu. Tuy nhiên phải có cách quan sát **account và quyền thực tế** của hai hệ đích.

### 5.2. Lab 2 — Đặt đúng vai trò cho SSO và SCIM

Thực hiện tình huống:

- User có thể **đăng nhập OIDC/SAML qua IdP**, nhưng app chưa được provision account.
- User đã được SCIM tạo trong app, nhưng **chưa có role** cho chức năng cần dùng.
- User đã disable tại IdP, nhưng app vẫn có **local session hoặc token độc lập**.
- User đã bị gỡ membership SCIM Group, nhưng app vẫn có **direct grant**.

Với từng trường hợp, ghi lại **triệu chứng, lớp gây lỗi, phương pháp kiểm tra, thay đổi cần thực hiện và điều kiện hoàn tất**.

### 5.3. Mẫu giao diện mô phỏng hệ đích

Trong lab không nhất thiết phải triển khai đầy đủ SCIM. Có thể xây một adapter đơn giản với giao diện logic:

~~~text
TargetAdapter:
  findAccount(subjectId) -> Account?
  createOrUpdateAccount(subjectId, attributes) -> Result
  setAccountActive(subjectId, active) -> Result
  setDesiredGroups(subjectId, groups) -> Result
  listActualEntitlements(subjectId) -> Entitlement[]
  revokeCredential(subjectId, credentialId) -> Result
~~~

Adapter là **giả mã**, không thay thế đặc tả SCIM. Khi nghiên cứu SCIM thật, hãy tìm hiểu resource **User**, **Group**, thuộc tính **active**, phương pháp POST/PATCH, cách ứng dụng xử lý membership và nhất là cách **đọc lại trạng thái thực tế**.

### 5.4. Lab 3 — Thử authorization tại API

Tạo một API mẫu **GET/PUT ticket**. Với một user đã đăng nhập, backend phải kiểm tra:

1. Chủ thể có trạng thái hợp lệ?
2. Chủ thể có quyền hành động (ví dụ ticket:update)?
3. Ticket có thuộc **tenant/team** của chủ thể?
4. Trạng thái ticket có cho phép cập nhật?
5. Sau Mover hoặc Leaver, quyền cũ có bị chặn dù phiên cũ vẫn mở?

Hãy thử đổi object ID trong đường dẫn để kiểm chứng **object-level authorization**; thử gọi chức năng admin bằng vai trò thấp để kiểm chứng **function-level authorization**. Các kiểm tra phải nằm ở thành phần backend tin cậy, không chỉ ẩn nút trên giao diện.

## 6. Chặng C — Kiểm thử quyền tồn dư và lỗi phân tán

Đây là bước chuyển quan trọng từ “hệ thống chạy khi mọi thứ bình thường” sang “hệ thống vẫn giữ **quyền đúng** khi có lỗi”. IAM lifecycle thường trải qua nhiều hệ thống không có giao dịch chung. Một cập nhật tại IdP có thể thành công, một SaaS thất bại và một job cũ có thể chạy lại sau khi người dùng đã nghỉ.

### 6.1. Lab 4 — Đồng bộ trạng thái mong muốn

Xây bộ tính chênh lệch:

~~~text
desired = policy(identity, role, attributes, approvals, currentTime)
actual  = readAllTargets(subjectId)

toGrant  = desired - actual.effectivePermissions
toRevoke = actual.effectivePermissions - desired
~~~

Nhưng phải bổ sung hai điều kiện:

1. **Nguồn cấp quyền:** cùng một entitlement có thể đến từ group A, group B và direct ACL. Khi revoke cần tìm đủ grant path để quyền hiệu lực biến mất.
2. **Điểm thực thi quyền:** quyền trên token, session hoặc cache có thể tồn tại đến khi hết hạn hoặc được thu hồi theo khả năng hệ đích. Cập nhật group xong chưa chứng minh một API token cũ không còn dùng được.

Với mock CRM, hãy cố ý tạo một grant trực tiếp cho **customers:export** và một membership **Data-Exporters** cũng cấp quyền đó. Gỡ membership trước, kiểm tra export vẫn được cho phép; sau đó gỡ direct grant, đọc lại và kiểm thử quyền đã bị từ chối.

**Bằng chứng:** snapshot trước và sau, danh sách nguồn cấp, thao tác revoke, kết quả kiểm tra quyền hiệu lực.

### 6.2. Lab 5 — Chống xử lý trùng và cấp lại quyền sai

Tạo chuỗi sự kiện:

~~~text
09:00  MOVER subject=EMP-LAB-042, sourceVersion=12
09:01  Grant Finance đang xử lý, một target timeout
09:02  LEAVER subject=EMP-LAB-042, sourceVersion=13
09:03  LEAVER vô hiệu danh tính và thu hồi quyền
09:04  Job MOVER phiên bản 12 được retry
~~~

**Kết quả sai:** workflow xử lý job retry như thể chủ thể còn hoạt động, làm role Finance sống lại.

**Kết quả đúng:** job Mover cũ bị bỏ qua hoặc tính lại quyền theo **trạng thái nguồn mới nhất**, không cấp lại quyền cho chủ thể đã chấm dứt. Quy trình phải lưu **eventId, subjectId, sourceVersion, effectiveAt** và kiểm tra trạng thái trước khi thực thi grant.

Các năng lực cần thực hành:

- **Idempotency:** nhận cùng event nhiều lần nhưng không tạo account/role trùng.
- **Ordering:** khi sự kiện đến sai thứ tự, không cho phiên bản cũ ghi đè phiên bản mới.
- **Retry:** thử lại lỗi tạm thời có giới hạn và backoff; lỗi dữ liệu hoặc chính sách phải chuyển owner xử lý.
- **Reconciliation:** quét định kỳ để phát hiện khác biệt do lỗi connector hoặc thay đổi thủ công.
- **Safe offboarding:** khi revoke khẩn cấp, chặn các đường đang kiểm soát được và theo dõi phần còn lại đến khi có bằng chứng.

### 6.3. Lab 6 — Mô phỏng ứng dụng ngừng hoạt động

Khi Leaver có hiệu lực, mock CRM trả lỗi trong khi IdP và Finance hoạt động:

| Thành phần | Kết quả | Trạng thái cần ghi |
| --- | --- | --- |
| IdP | Disable thành công, đọc lại inactive | VERIFIED |
| Finance | Gỡ role, đọc lại không còn quyền | VERIFIED |
| CRM | Timeout, chưa xác minh quyền còn hay mất | PENDING hoặc FAILED |
| Session/token CRM | Không có bằng chứng đã bị chặn | UNKNOWN |
| Workflow tổng | Một số bước hoàn tất, phần khác chưa | PARTIAL |

Workflow cần tạo **ngoại lệ có owner, mức rủi ro, mốc xử lý và biện pháp chặn tạm thời khả dụng**. Khi CRM phục hồi, thực hiện revoke và readback; chỉ khi điều kiện hoàn tất được đáp ứng mới đóng Leaver. Không đánh dấu thành công chỉ vì IdP đã chặn đăng nhập SSO mới.

### 6.4. Bản đồ những quyền dễ sót

| Nguồn quyền tồn dư | Câu hỏi tự kiểm tra |
| --- | --- |
| Group lồng nhau hoặc nhiều group | Đã gỡ mọi đường dẫn tới entitlement không hợp lệ? |
| Direct ACL/role trong ứng dụng | Chỉ gỡ nhóm IdP có đủ không? |
| Local account | Ứng dụng còn cách đăng nhập không qua SSO? |
| Access token/refresh token/PAT | Token còn thời hạn, có cách revoke và xác minh không? |
| Session ứng dụng | Logout IdP có kết thúc session tại app không? |
| Chia sẻ tài nguyên | Link, file, repo hoặc dashboard có quyền riêng? |
| Nhà thầu quá hạn | Sponsor và ngày kết thúc có được đối soát? |
| Service account vô chủ | Người tạo nghỉ việc, workload còn chủ sở hữu và lý do hợp lệ không? |
| Event cấp quyền cũ | Một retry có thể cấp lại sau Leaver không? |

Không nên coi **mọi account còn lưu trong hệ thống** là quyền tồn dư. Account có thể được giữ **inactive** để phục vụ lưu giữ dữ liệu, điều tra hoặc tính toàn vẹn lịch sử. Điều cần xác minh là **đường truy cập không còn hợp lệ có bị chặn thực tế hay chưa**.

## 7. Chặng D — Vận hành, access review và kiểm toán

Khi JML và các luồng cấp/thu hồi đã chạy đúng trong bài lab, hãy học cách duy trì chúng theo thời gian. Một thiết kế IAM chỉ đáng tin nếu biết ai chịu trách nhiệm khi có sai lệch, cách phát hiện sai lệch và cách chứng minh đã khắc phục.

### 7.1. Tạo một access review đơn giản

Với mỗi account trên CRM và Finance, lập bảng:

| Trường | Câu hỏi |
| --- | --- |
| subjectId / targetAccountId | Account gắn với chủ thể nào? |
| owner / sponsor | Ai xác nhận nhu cầu tồn tại? |
| entitlement / grant source | Được cấp quyền gì, qua role, group hay ACL trực tiếp? |
| approvedBy / policyVersion | Có căn cứ chính sách hoặc phê duyệt còn hiệu lực? |
| lastReviewedAt / expiresAt | Bao giờ phải rà soát hoặc tự thu hồi? |
| reviewerDecision | Giữ, thu hồi, giảm phạm vi hoặc yêu cầu bổ sung? |
| remediationStatus | Quyết định có được thực thi ở hệ đích? |
| verifiedAt | Lúc nào quyền thực tế đã được kiểm tra lại? |

Mô phỏng ít nhất ba quyết định: giữ quyền hợp lệ, thu hồi quyền lỗi thời và giảm một quyền quá rộng. Với quyết định thu hồi, **kết quả của reviewer chỉ là đầu vào**; workflow còn phải gỡ quyền, đọc lại và lưu bằng chứng.

### 7.2. Thiết kế runbook xử lý ngoại lệ

Một runbook cần rõ ràng để người mới nhận trực vận hành không phải đoán. Dùng khung:

1. **Trigger:** sự kiện gì xảy ra, cảnh báo hoặc chỉ số nào phát hiện?
2. **Scope:** subjectId, hệ đích, quyền đang bị ảnh hưởng và mức rủi ro.
3. **Containment:** việc nào có thể chặn hoặc giảm rủi ro ngay theo thẩm quyền?
4. **Owner:** ai nhận xử lý, ai phê duyệt ngoại lệ và ai cần được thông báo?
5. **Remediation:** cách cập nhật quyền qua connector/API hoặc thao tác thủ công.
6. **Verification:** đọc lại trạng thái gì, dùng kiểm thử nào để chứng minh kết quả?
7. **Evidence:** event, thao tác, quyết định và thời điểm được ghi ở đâu?
8. **Closure:** điều kiện đóng sự kiện, cách xử lý nếu chưa đủ bằng chứng.

**Ví dụ:** Đến thời điểm Leaver, hệ thống cảnh báo “CRM deprovision timeout”. Runbook yêu cầu xác minh IdP đã inactive, kiểm tra có thể chặn tại gateway/VPN hoặc revoke token liên quan hay không, giao việc cho app owner, tiếp tục retry an toàn, đọc lại account CRM khi dịch vụ phục hồi và cập nhật thời gian kết thúc thực tế.

### 7.3. Tạo chỉ số từ bằng chứng

| Chỉ số | Cách đo trong lab | Điều cần tránh |
| --- | --- | --- |
| **Joiner readiness** | Tỷ lệ người mới có đúng account/quyền tại thời điểm được phép bắt đầu | Chỉ đếm account đã tạo, bỏ quyền bị thiếu |
| **Mover stale entitlement** | Tỷ lệ Mover còn quyền cũ sau hạn xử lý | Chỉ kiểm tra nhóm IdP, bỏ ACL trực tiếp |
| **Leaver revoke latency** | Từ thời điểm cần khóa đến khi các hệ đích trong phạm vi xác minh mất quyền | Lấy thời gian disable IdP làm thời gian hoàn tất tất cả |
| **Provisioning failure rate** | Tỷ lệ target lỗi hoặc chưa đọc lại thành công | Che kết quả thất bại bằng trạng thái workflow tổng |
| **Orphan account count** | Account không đối chiếu được với identity/workload hoặc owner hợp lệ | Xem inactive account được giữ đúng chính sách là lỗi |
| **Temporary access overdue** | Quyền có expiry nhưng vẫn hiệu lực sau hạn | Chỉ kiểm tra ngày hết hạn trên phiếu duyệt |
| **Access review remediation** | Quyền reviewer quyết định thu hồi đã được gỡ và đọc lại | Coi thao tác “Reject” trong UI là revoke thành công |
| **Reconciliation coverage** | Tỷ lệ hệ thống có thể lấy actual user/role/ACL để đối soát | Tuyên bố bao phủ khi chỉ có dữ liệu từ IdP |

Định nghĩa rõ **mẫu số, thời gian, hệ thống trong phạm vi và tiêu chí VERIFIED**. Không có một SLA phút/giờ dùng chung cho mọi tổ chức; mốc mục tiêu cần dựa trên phân loại rủi ro và khả năng vận hành.

### 7.4. Kiểm toán có thể truy vết

Một bằng chứng tốt trả lời được: **sự kiện từ đâu, ai xác minh, chính sách phiên bản nào, ai duyệt, lệnh đã gửi tới hệ nào, trạng thái thực tế nào được xác nhận, lúc nào và ngoại lệ đang thuộc trách nhiệm của ai**.

Không ghi mật khẩu, private key, raw API token, session cookie hoặc dữ liệu cá nhân không cần thiết vào log. Bảo vệ truy cập log và áp dụng thời hạn lưu giữ theo chính sách. Dữ liệu giả trong lab nên tránh định danh người thật.

## 8. Nhánh học nâng cao: danh tính dịch vụ và quyền đặc biệt

Một chương trình IAM lifecycle không thể chỉ quản lý người có hồ sơ HR. Nhiều hệ thống còn có **service principal, workload identity, bot, tài khoản CI/CD và break-glass account**.

### 8.1. Lab service identity

Giả định pipeline CI cần deploy dịch vụ A trong môi trường thử nghiệm:

1. Tạo danh tính workload có **owner** và mục đích cụ thể.
2. Định nghĩa quyền **deploy:A** thay vì role quản trị toàn môi trường.
3. Nếu có khả năng, dùng danh tính liên kết hoặc credential ngắn hạn thay secret tĩnh.
4. Ghi tài nguyên và hành động pipeline được phép; tạo kiểm thử rằng pipeline **không** deploy được dịch vụ B.
5. Khi pipeline chuyển sang B, cấp scope B được phê duyệt và thu hồi scope A.
6. Khi pipeline ngừng hoạt động, thu hồi credential, trust và role; đối soát không còn quyền thực tế.

**Bài tập bổ sung:** Người tạo pipeline rời công ty. Không nên xóa ngay service identity đang vận hành chỉ vì account cá nhân của người đó bị vô hiệu. Thay vào đó cần **chuyển owner, rà soát token cá nhân nếu có, thay credential rủi ro và kiểm chứng** theo chính sách và mức độ khẩn cấp.

### 8.2. Quyền nâng cao theo thời gian

Học mô hình **Privileged Access Management (PAM)** và **Just-in-Time (JIT)** bằng một trường hợp: admin cần quyền sửa cấu hình production trong một khoảng thời gian được phê duyệt.

~~~mermaid
flowchart LR
    REQ["Yêu cầu admin<br/>Lý do + phạm vi + thời hạn"] --> AUTH["Xác thực mạnh<br/>Kiểm tra SoD"]
    AUTH --> APPROVE["Phê duyệt có dấu vết"]
    APPROVE --> ENABLE["Kích hoạt quyền JIT"]
    ENABLE --> WORK["Thao tác có log"]
    WORK --> EXPIRE["Hết hạn / thu hồi sớm"]
    EXPIRE --> CHECK["Kiểm tra role, phiên, token"]
~~~

**Câu hỏi bắt buộc:** sau khi quyền JIT hết hạn, role có biến mất không? Session đang mở có còn khả năng thực thi thao tác nâng cao không? Hệ thống có kiểm tra lại quyền ở lúc hành động không?

### 8.3. Break-glass có kiểm soát

Tài khoản khẩn cấp có thể cần tồn tại ngoài SSO để khôi phục khi IdP sự cố, nhưng phải có owner, cách bảo quản credential, log, cảnh báo, quy trình sử dụng, hậu kiểm và xoay credential phù hợp. Hãy viết runbook cho một ca khẩn cấp và nêu cách chứng minh không biến tài khoản này thành lối bỏ qua chính sách hàng ngày.

## 9. Dự án tổng hợp: xây hệ thống IAM lifecycle thu nhỏ

Đây là bài thực hành chính để kết nối các chặng. Mục đích không phải tạo một IdP thương mại đầy đủ mà là **chứng minh luồng quản lý danh tính và quyền hoạt động đáng tin trong môi trường mô phỏng**.

### 9.1. Bối cảnh và yêu cầu

Giả định doanh nghiệp thử nghiệm **DemoCo** có ba bộ phận Support, Finance, Engineering; hai ứng dụng **CRM** và **Billing**; một IdP; và một pipeline triển khai. Nhân viên có thể đổi vai trò hoặc nghỉ việc. Nhà thầu có sponsor và ngày hết hạn. Một số hệ đích có SCIM/API, một số cần xử lý thủ công.

Các thành phần tối thiểu:

| Thành phần | Chức năng |
| --- | --- |
| **Identity Source** | Lưu nhân viên/nhà thầu, status, manager/sponsor, thời điểm hiệu lực |
| **Event Ingestor** | Nhận Joiner/Mover/Leaver, chống trùng, theo dõi version |
| **Policy Engine** | Tính desired account state và entitlements theo role/attribute |
| **Approval Workflow** | Phê duyệt quyền đặc biệt, SoD, expiry |
| **IdP Adapter** | Tạo/cập nhật/disable user, quản lý nhóm và trạng thái phiên mô phỏng |
| **CRM/Billing Adapters** | Provision/disable, cấp/thu hồi role, trả về quyền thực tế |
| **Reconciler** | So desired với actual theo cả hai chiều, tạo nhiệm vụ khắc phục |
| **Audit Store** | Lưu eventId, policyVersion, request, kết quả và xác minh |
| **Operations View** | Danh sách event chưa hoàn tất, lỗi, ngoại lệ quá hạn, KPI |

Không cần chọn một ngôn ngữ cụ thể. Có thể triển khai bằng Java, Kotlin, Python, JavaScript hoặc công cụ thích hợp với môi trường học, miễn là người khác có thể **chạy lại dữ liệu thử và kiểm chứng đầu ra**.

### 9.2. Sơ đồ dự án

~~~mermaid
flowchart TB
    HR["HRIS / Sponsor giả lập"] --> EVENTS["Event Ingestor<br/>Idempotency + Version"]
    EVENTS --> POLICY["Policy + Approval<br/>Desired State"]
    POLICY --> ORCH["IAM Orchestrator"]
    ORCH --> IDP["IdP giả lập<br/>Users + Groups"]
    ORCH --> CRM["CRM<br/>Account + Role + ACL"]
    ORCH --> BILL["Billing<br/>Account + Role"]
    ORCH --> MACHINE["Workload IAM<br/>Identity + Scope"]
    IDP --> READ["Reconciler<br/>Actual State"]
    CRM --> READ
    BILL --> READ
    MACHINE --> READ
    POLICY --> READ
    READ --> EX["Exceptions / Remediation"]
    EX --> ORCH
    EVENTS --> AUDIT["Audit Trail"]
    ORCH --> AUDIT
    READ --> AUDIT
~~~

### 9.3. Dữ liệu thử nên có

Tạo tối thiểu năm chủ thể giả:

| Chủ thể | Kiểu | Tình huống |
| --- | --- | --- |
| **EMP-LAB-001** | Nhân viên | Joiner Support, rồi Mover sang Finance, sau đó Leaver |
| **EMP-LAB-002** | Nhân viên | Được phê duyệt quyền export có hạn |
| **EXT-LAB-003** | Nhà thầu | Sponsor, ngày kết thúc và gia hạn hợp lệ |
| **EMP-LAB-004** | Nhân viên | Role Finance tạo xung đột SoD khi yêu cầu approve |
| **WORKLOAD-LAB-005** | Service identity | Deploy dịch vụ A, chuyển sang B, rồi decommission |

Thêm trường hợp tạo **account app không có subjectId hợp lệ** và một **direct grant** được cấp ngoài workflow. Hai dữ liệu lệch này giúp kiểm thử đối soát ngược và phát hiện orphan/residual access.

### 9.4. Hợp đồng tối thiểu cho một lifecycle event

~~~json
{
  "eventId": "HR-LAB-0101",
  "subjectId": "EMP-LAB-001",
  "eventType": "JOINER",
  "effectiveAt": "2026-12-01T08:00:00+07:00",
  "sourceVersion": 1,
  "attributes": {
    "employmentStatus": "active",
    "department": "Support",
    "role": "Support-Agent",
    "managerId": "EMP-LAB-MGR"
  }
}
~~~

Tiếp theo tạo **MOVER v2** đổi sang Finance và **LEAVER v3** có ngày hiệu lực rõ ràng. Dữ liệu trên không thuộc chuẩn giao thức cụ thể; workflow cần ánh xạ sang API của hệ đích.

### 9.5. Pseudocode điều phối

~~~text
handle(event):
  validateTrustedSource(event)

  if alreadyProcessed(event.eventId):
    return previousResult(event.eventId)

  latest = loadLatestAuthoritativeState(event.subjectId)
  if eventIsSuperseded(event, latest):
    recordSkipped(event, "superseded")
    return SKIPPED

  desired = deriveDesiredState(latest, policyVersion, approvals)
  targets = discoverManagedTargets(event.subjectId)

  for target in targets:
    actual = target.readActualState(event.subjectId)
    plan = planChanges(desired.forTarget(target), actual)
    applyIdempotently(target, plan)
    verifyTargetState(target, desired.forTarget(target))

  if everyRequiredTargetVerified():
    recordAudit(event, desired, VERIFIED)
    return COMPLETED

  recordExceptionsWithOwner(event)
  return PARTIAL
~~~

Đây là **giả mã thiết kế**, không bao gồm đầy đủ xử lý đồng thời, race condition giữa bước kiểm tra và ghi, giao dịch hay khôi phục sau crash. Khi triển khai thực, cần đảm bảo **không thể cấp lại quyền sai từ một job cũ** ngay cả khi nhiều worker đang chạy: có thể cần điều phối tuần tự theo subjectId, kiểm tra phiên bản lúc ghi, điều kiện cập nhật và readback.

### 9.6. Tiêu chí nghiệm thu dự án

Một dự án hoàn thành tốt cần minh chứng:

1. **Joiner:** tạo đúng account và quyền tối thiểu, không mở quyền nhạy cảm khi chưa duyệt.
2. **Mover:** xóa quyền không còn hợp lệ kể cả direct grant, cấp quyền mới và xử lý SoD.
3. **Leaver:** disable đăng nhập, revoke quyền và credential thuộc phạm vi, giữ trạng thái PARTIAL khi app chưa xác minh.
4. **Expiry:** quyền tạm thời bị thu hồi theo thời hạn thực tế.
5. **Idempotency:** gửi lại cùng event không tạo thêm account hoặc quyền.
6. **Ordering:** Mover cũ không cấp lại quyền sau Leaver có phiên bản mới hơn.
7. **Reconciliation:** phát hiện account mồ côi và quyền được cấp ngoài workflow.
8. **Service identity:** workload có owner và role tối thiểu; khi ngừng hoạt động có đường revoke.
9. **Auditability:** truy được nguồn, phê duyệt, policy version, thao tác, readback và ngoại lệ.
10. **Documentation:** người khác có thể chạy dữ liệu mẫu, hiểu giới hạn và kiểm chứng kết quả.

## 10. Ma trận kiểm thử dành cho dự án tổng hợp

Thiết kế test theo cả **đường hợp lệ** và **đường bị từ chối**. Không kiểm thử trên hệ thống hoặc tài khoản không được phép.

| ID | Dữ liệu đầu vào/tình huống | Điều kiện PASS |
| --- | --- | --- |
| **J01** | Joiner Support với đủ thông tin | IdP và CRM có đúng account/role; quyền ngoài scope bị từ chối |
| **J02** | Joiner gửi lại cùng eventId | Không tạo duplicate account hoặc thêm grant |
| **J03** | Joiner chưa tới effectiveAt | Không mở quyền sớm ngoài chính sách pre-hire |
| **J04** | Joiner bị hủy trước khi bắt đầu | Account chuẩn bị không trở thành đường truy cập mồ côi |
| **J05** | Joiner yêu cầu export không có phê duyệt | Chức năng export bị từ chối |
| **M01** | Mover Support → Finance | Gỡ quyền Support và cấp quyền Finance đúng mục tiêu |
| **M02** | Direct ACL còn sau khi gỡ role | Phát hiện sai lệch và tiếp tục revoke |
| **M03** | Mover phát sinh SoD | Chặn grant nguy hiểm hoặc áp dụng ngoại lệ có kiểm soát đúng chính sách |
| **M04** | Mover được gửi trùng | Không có quyền nhân đôi hoặc grant ngoài mục tiêu |
| **M05** | Mover từ v2 đến sau Leaver v3 | Không kích hoạt lại account hoặc quyền cũ |
| **L01** | Leaver đúng effectiveAt | Các target bắt buộc xác minh mất quyền |
| **L02** | Leaver trong lúc CRM offline | Workflow ở PARTIAL, có owner và biện pháp xử lý |
| **L03** | Disable IdP nhưng SaaS còn local session | Phát hiện và xử lý theo khả năng app, không kết luận sai |
| **L04** | Token cá nhân còn tồn tại | Có bước revoke/rotate và readback phù hợp |
| **L05** | Leaver có dashboard cần bàn giao | Owner mới được xác nhận, không cần giữ account active |
| **P01** | Quyền export có expiresAt | Hết hạn thì entitlement không còn hiệu lực |
| **P02** | User tenant A đọc ticket tenant B | Backend từ chối |
| **P03** | Viewer gọi chức năng admin | API từ chối, không thay đổi dữ liệu |
| **P04** | ABAC thiếu thuộc tính quan trọng | Hành động được bảo vệ không bị tự động cho phép |
| **R01** | App có account không map được tới nguồn | Reconciler báo orphan có owner xử lý |
| **R02** | Admin tạo manual grant ngoài chính sách | Reconciler tìm được drift |
| **R03** | Access review từ chối một quyền | Quyền được revoke thật và lưu verifiedAt |
| **W01** | Workload A gọi tài nguyên B | Không được quyền ngoài scope |
| **W02** | Workload đã decommission | Key/role/trust thuộc phạm vi được thu hồi và xác minh |
| **A01** | Bản ghi kiểm toán của một event | Có thể truy ngược từ kết quả đến nguồn, policy và approver |

Sau mỗi ca, ghi **Expected, Actual, PASS/FAIL, Evidence, Owner và thời gian**. Nếu không thể kiểm chứng vì giới hạn của mock hoặc API, ghi **UNKNOWN** và mô tả thiếu gì; không tự đổi thành PASS.

### 10.1. Mẫu báo cáo một ca kiểm thử

~~~yaml
testCase: M05
subjectId: EMP-LAB-001
input: "MOVER v2 arrives after LEAVER v3"
expected: "No grant or reactivation"
actual: "Old event rejected as superseded"
result: PASS
verifiedTargetStates:
  idp: inactive
  crm: inactive
  billing: no-active-roles
evidenceRef: "lab://tests/M05"
verifiedAt: "2026-12-03T09:12:00+07:00"
~~~

Các giá trị là ví dụ giả định và **evidenceRef** không trỏ đến kho thật. Trong sản phẩm thực tế, nên tách log kiểm toán, dữ liệu cá nhân và credential để bảo vệ truy cập đúng chính sách.

## 11. Chọn hướng đào sâu theo công việc

Sau khi làm dự án tổng hợp, nên chọn nhánh theo nhu cầu thực tế. Một người có thể học nhiều nhánh nhưng không cần cùng lúc.

### 11.1. Nhánh phát triển phần mềm và backend

Ưu tiên:

- **OIDC/OAuth 2.0:** flow, client, access token và ID token, audience/scope, session management.
- **Object-level authorization:** quyền theo tài nguyên, tenant, team, owner, trạng thái nghiệp vụ.
- **Policy-as-code:** lưu policy có phiên bản, test dương tính/âm tính, kiểm soát rollout/rollback.
- **API security:** BOLA/IDOR, function-level authorization, lọc dữ liệu theo quyền, export và background jobs.
- **Consistency:** cache, token TTL, sự kiện đến sai thứ tự, kiểm tra quyền sát lúc thực thi.

**Sản phẩm gợi ý:** một API có policy tests chứng minh người dùng tenant A không thể đọc/sửa tài nguyên tenant B, kể cả khi thay ID trong request.

### 11.2. Nhánh IAM engineer / platform

Ưu tiên:

- **Provisioning/deprovisioning:** mapping account, SCIM, connector, reconciliation hai chiều.
- **Federation:** cấu hình SAML/OIDC, key/certificate rotation, logout và phiên.
- **Identity governance:** access request, SoD, review, expiry, approver và ownership.
- **Reliability:** event bus, retry, idempotency, thao tác thủ công được kiểm soát, runbook.
- **Automation:** service identity, workload federation, secrets lifecycle, least privilege cho connector.

**Sản phẩm gợi ý:** hai ứng dụng dùng cách provision khác nhau nhưng có cùng tiêu chí xác minh JML, xử lý được connector lỗi và ghi cảnh báo rõ ràng.

### 11.3. Nhánh security engineer và ứng cứu

Ưu tiên:

- **Threat modeling cho IAM:** account takeover, privilege escalation, residual access, credential leak.
- **Zero Trust access:** đánh giá liên tục danh tính, thiết bị và ngữ cảnh khi truy cập phù hợp kiến trúc.
- **Privileged access:** PAM, JIT, break-glass, log phiên và hậu kiểm.
- **Detection:** bất thường khi login, thay MFA, cấp role bất thường, quyền tạm thời quá hạn.
- **Incident response:** revoke token, xử lý phiên, lock account, điều tra và phục hồi an toàn.

**Sản phẩm gợi ý:** một tabletop exercise về nhân viên nghỉ khẩn cấp nhưng còn API key và session SaaS, kèm các bước containment, remediation và evidence.

### 11.4. Nhánh governance, risk và audit

Ưu tiên:

- **Access certification:** phân loại rủi ro entitlement, vai trò reviewer, remediation sau review.
- **Chứng cứ:** từ HR event, phê duyệt đến readback hệ đích, phân tách nhiệm vụ và bảo vệ log.
- **Chỉ số:** thời gian revoke thực tế, orphan account, stale entitlement, exception overdue.
- **Dữ liệu cá nhân:** tối thiểu hóa thuộc tính, mục đích sử dụng và thời hạn lưu theo chính sách.
- **Kiểm soát bên thứ ba:** sponsor, thời hạn hợp đồng, quyền truy cập đối tác và tài khoản local.

**Sản phẩm gợi ý:** bộ bằng chứng cho một kỳ access review, chứng minh mọi quyền bị từ chối đều được xử lý thật, có danh sách ngoại lệ chưa hoàn tất.

### 11.5. Nhánh cloud và danh tính máy

Ưu tiên:

- **Workload federation/managed identity:** giảm secret tĩnh và quản lý trust.
- **Cloud IAM:** role, policy, resource scope, temporary credential và account phân tách môi trường.
- **Kubernetes/CI/CD identity:** service account, quyền triển khai tối thiểu, secret management.
- **Lifecycle:** tạo, thay đổi, đổi owner, decommission workload và cleanup tài nguyên.
- **Quan sát:** audit credential usage, orphan principal, quyền không sử dụng.

**Sản phẩm gợi ý:** pipeline không dùng PAT cá nhân, chỉ được phép deploy một dịch vụ đã định, và có thể chứng minh revoke khi pipeline dừng.

## 12. Tài liệu và tiêu chuẩn nên tìm hiểu tiếp

Khi cần đi từ lab sang hệ thống thật, hãy đọc **đặc tả chính thức** cho giao thức và tài liệu tích hợp của hệ đích. Nên đọc theo câu hỏi đang giải quyết thay vì cố học thuộc toàn bộ thông số.

| Chủ đề | Nguồn/nhóm tài liệu gợi ý | Nên tìm câu trả lời gì? |
| --- | --- | --- |
| **SCIM** | RFC 7643 (Core Schema), RFC 7644 (Protocol) | User/Group, PATCH, thuộc tính active, cơ chế provisioning và API chuẩn |
| **OIDC** | OpenID Connect Core và hướng dẫn của IdP đang dùng | ID token, issuer/audience, login flow, quản lý phiên và xác thực client |
| **OAuth 2.0** | Đặc tả OAuth 2.0 và các hướng dẫn bảo mật liên quan | Authorization code/PKCE, scope, refresh/access token, giới hạn client |
| **SAML** | Đặc tả và profile SAML được sản phẩm hỗ trợ | Assertion, issuer, audience, signature, thời gian và logout |
| **Xác thực số** | Bộ hướng dẫn NIST SP 800-63 về digital identity | Assurance, authenticator, MFA, proofing và recovery theo rủi ro |
| **WebAuthn** | Chuẩn W3C Web Authentication / FIDO2 | Đăng ký và xác thực bằng khóa công khai, phishing resistance |
| **Authorization ở API** | OWASP API Security Top 10 | BOLA, BFLA, object/property authorization, kiểm tra phía server |
| **Zero Trust** | NIST SP 800-207 | Xác định điểm quyết định/thực thi policy, tín hiệu ngữ cảnh, ranh giới tin cậy |
| **Cloud IAM** | Tài liệu IAM của nền tảng cloud được chọn | Policy evaluation, role/scope, temporary credentials, audit |
| **IGA/PAM** | Tài liệu sản phẩm hoặc quy trình tổ chức | Access request/review, SoD, JIT, expiry, break-glass và audit |

Tên tài liệu nêu hướng nghiên cứu. Khi áp dụng sản xuất, cần đối chiếu phiên bản đặc tả, best practice và giới hạn thực tế của sản phẩm đang triển khai. Ví dụ ứng dụng hỗ trợ SCIM không đồng nghĩa mọi semantics session/token đều giống nhau; phải kiểm chứng hợp đồng tích hợp.

### 12.1. Cách đọc tài liệu kỹ thuật hiệu quả

Với mỗi chuẩn, hãy tự điền bốn ô:

1. **Nó giải quyết lớp vấn đề nào?** Xác thực, truyền kết quả login, provision hay thực thi quyền?
2. **Giới hạn là gì?** Ví dụ SCIM không tự quyết định ai xứng đáng quyền nào.
3. **Dữ liệu đầu vào/đầu ra ra sao?** Định danh, token, resource, policy, status.
4. **Kiểm tra kết quả bằng gì?** Readback từ app, request bị từ chối, log và test.

Nếu không trả lời được ô thứ tư, bạn có thể mới hiểu cách **gửi lệnh** mà chưa hiểu cách **chứng minh hệ thống đã đạt mục tiêu**.

## 13. Lịch tự học mẫu theo bốn chu kỳ

Đây là lịch gợi ý cho người học đã nắm kiến thức nền và muốn tạo một sản phẩm lab. Có thể trải qua bốn tuần, bốn buổi chuyên sâu hoặc các đợt dài hơn tùy lịch cá nhân.

| Chu kỳ | Việc thực hành ưu tiên | Kết quả cần nộp/tự lưu |
| --- | --- | --- |
| **1. Thiết kế** | Dựng nguồn danh tính, event schema, account mapping, role catalog, trạng thái JML | Sơ đồ, dữ liệu giả, ma trận quyền, 3 tình huống JML |
| **2. Tự động hóa** | Thực thi Joiner/Mover/Leaver với hai ứng dụng, có readback và audit | Luồng chạy được, log trước–sau, quyền đúng theo từng target |
| **3. Làm hệ thống thất bại có kiểm soát** | Retry, event trùng, Mover muộn, app offline, direct grant, token còn sống | Bộ ca test âm tính, báo cáo PARTIAL, cách khắc phục |
| **4. Vận hành và đánh giá** | Access review, service identity, metrics, runbook, dự án tổng hợp | Hồ sơ bằng chứng, dashboard đơn giản, tài liệu vận hành |

Mỗi chu kỳ nên dành thời gian cho ba hoạt động:

- **Thiết kế:** trả lời vấn đề gì xảy ra, quyền mong muốn là gì và ai chịu trách nhiệm.
- **Thực hành:** chạy event hoặc request trên mô phỏng, ghi trạng thái đích.
- **Rút kinh nghiệm:** một lỗi đã thấy, nguyên nhân, cách khắc phục và một test ngăn tái diễn.

Không nên chuyển sang cấu hình SSO phức tạp hoặc đặc quyền production khi còn chưa phân biệt rõ **IdP account, SaaS account, entitlement, session và token**. Khi tự học hãy ưu tiên môi trường giả lập, tài khoản thử nghiệm và quyền do bạn quản lý hợp pháp.

## 14. Bộ sản phẩm đầu ra để chứng minh đã học xong

Một người khác nên có thể đọc tài liệu bạn tạo và tự kiểm tra kết quả. Bộ sản phẩm tối thiểu gồm:

| Sản phẩm | Nội dung cần có | Dấu hiệu đạt |
| --- | --- | --- |
| **Sơ đồ kiến trúc** | Nguồn identity, IdP, SSO, connector, target app, audit | Thấy rõ đường xác thực và đường cấp/thu hồi |
| **Ma trận entitlement** | Role, action, resource, context, owner, SoD | Có ít nhất một quyền bị DENY trong kiểm thử âm tính |
| **Event fixtures** | Joiner, Mover, Leaver, trùng, sai thứ tự, expiry | Có ID và thời điểm hiệu lực rõ ràng |
| **Workflow** | Validate → desired → apply → readback → close/exception | Không đóng COMPLETED khi một target chưa verified |
| **Target adapters** | Create/update/disable và query actual entitlements | Có thể kiểm tra trạng thái trước và sau |
| **Automated tests hoặc kịch bản lặp lại** | Luồng thường và failure cases | Người khác có thể chạy lại và so kết quả |
| **Reconciliation report** | Sai lệch desired/actual, orphan và direct grant | Mỗi sai lệch có owner hoặc action tiếp theo |
| **Audit trail** | Event, phê duyệt, policy version, thao tác, thời điểm, kết quả | Truy được từ sự kiện đến target và ngược lại |
| **Runbook** | Phản ứng khi target offline, token tồn dư, JML sai thứ tự | Có điều kiện xác minh và đóng sự cố |
| **Tự đánh giá** | Điểm trước/sau và 2–3 hạn chế cần học tiếp | Nêu được năng lực đã chứng minh và chưa có bằng chứng |

### 14.1. Checklist bàn giao dự án

- [ ] Không dùng dữ liệu cá nhân thật, mật khẩu hoặc token thật trong ví dụ.
- [ ] EventId và subjectId được phân biệt; người đổi email không tạo danh tính trùng.
- [ ] Có quyền mục tiêu dựa trên role/attribute và phê duyệt.
- [ ] Phân biệt login/SSO với account provisioning và authorization tại tài nguyên.
- [ ] Joiner không được cấp quyền trước mốc cho phép nếu chính sách không cho.
- [ ] Mover thu hồi quyền cũ, bao gồm direct grant và quyền tạm thời.
- [ ] Leaver xử lý account, role, token/phiên và đường truy cập ngoài SSO theo phạm vi.
- [ ] Retry/idempotency và kiểm tra phiên bản ngăn job cũ cấp lại quyền.
- [ ] Mỗi target có phương pháp đọc lại và trạng thái VERIFIED/PARTIAL/FAILED rõ.
- [ ] Có mô phỏng app offline và đường escalation cho phần chưa hoàn tất.
- [ ] Có đối soát ngược phát hiện account mồ côi và grant ngoài workflow.
- [ ] Workload identity có owner, scope tối thiểu và đường decommission.
- [ ] Bằng chứng đủ truy nguồn sự kiện, phê duyệt, policy, target và thời điểm.
- [ ] Có kết quả kiểm thử dương tính/âm tính và hướng chạy lại.
- [ ] Có danh sách giới hạn của lab, giả định và việc cần làm trước khi áp dụng thật.

**Không nhất thiết mọi ô đều PASS** để tài liệu hữu ích. Một ô FAIL được mô tả đúng, có owner và kế hoạch kiểm chứng tốt hơn một kết quả PASS thiếu bằng chứng.

## 15. Những ngộ nhận cần tránh khi học nâng cao

| Ngộ nhận | Cách hiểu và hướng kiểm chứng |
| --- | --- |
| **“SSO bật rồi thì không cần provisioning.”** | SSO giúp xác thực; tài khoản app, role và ACL vẫn cần cơ chế quản lý, kiểm tra thực tế. |
| **“SCIM disable user là xóa sạch mọi quyền.”** | Hiểu semantics theo app; session, API key và credential ngoài SCIM có thể cần xử lý riêng. |
| **“Chỉ cần xóa nhóm cũ khi Mover.”** | Tìm direct grant, nhóm khác, ACL và token scope; đo quyền hiệu lực, không chỉ membership. |
| **“Một lệnh API trả thành công nghĩa là workflow hoàn tất.”** | Phân biệt ACK với readback; app có thể xử lý bất đồng bộ hoặc thất bại một phần. |
| **“Cứ xóa mọi account của Leaver là an toàn.”** | Có thể cần giữ account inactive và dữ liệu theo chính sách, bàn giao và nghĩa vụ áp dụng. |
| **“Service account không có JML.”** | Workload vẫn cần tạo, thay đổi, chuyển owner và ngừng hoạt động với grant/revoke tương ứng. |
| **“Role đúng thì API chắc chắn an toàn.”** | Cần kiểm tra object, tenant, hành động, context và điều kiện nghiệp vụ tại điểm thực thi. |
| **“Access review xong khi người duyệt đã bấm xác nhận.”** | Quyết định revoke còn phải được thực thi, đọc lại và lưu bằng chứng. |
| **“Đo tốc độ Leaver bằng thời gian disable IdP là đủ.”** | Độ trễ thu hồi phải xét target/credential thuộc phạm vi và thời điểm mất quyền thực tế. |

### 15.1. Tự trả lời trước khi kết thúc

1. Bạn có thể cho thấy **dữ liệu đầu vào** và **trạng thái thực tế sau mỗi JML event** không?
2. Một quyền có nhiều đường grant được thu hồi thế nào để chứng minh không còn hiệu lực?
3. Nếu SCIM/API thất bại hoặc một token còn sống, workflow báo trạng thái gì?
4. Làm sao phân biệt một app account **inactive được lưu đúng chính sách** với account mồ côi còn khả năng truy cập?
5. Có cách chứng minh một Mover cũ không thể **cấp lại quyền** sau Leaver mới hơn không?
6. Khi một chủ sở hữu workload nghỉ việc, làm sao chuyển giao an toàn mà không bỏ qua thu hồi credential cá nhân?
7. Quyết định access review có nối được đến thao tác revoke và readback ở đích không?
8. Bạn sẽ cho một người khác thấy những bằng chứng gì để họ độc lập kiểm tra kết luận của bạn?

Nếu chưa trả lời được, hãy chọn một câu và thiết kế **một kiểm thử có kết quả quan sát được**. Đây là cách tiếp tục học hữu ích hơn việc chỉ đọc thêm khái niệm.

## 16. Hành động tiếp theo ngay sau bài học

Chọn **một chủ thể giả và hai hệ đích giả**, thực hiện chuỗi sau:

1. **Joiner:** tạo danh tính EMP-LAB-001, cấp role Support-Agent và đọc lại quyền CRM.
2. **Mover:** chuyển sang Finance, tính chênh lệch, gỡ Support và ACL cũ, cấp Finance-Analyst, kiểm thử quyền ngoài phạm vi bị DENY.
3. **Leaver:** disable identity, app accounts và các credential thuộc phạm vi; xác minh quyền thực tế.
4. **Gây lỗi:** để một target timeout, nhận lại cùng event, gửi Mover cũ sau Leaver; kiểm tra hệ thống không tuyên bố sai hoặc cấp lại quyền.
5. **Báo cáo:** ghi eventId, policyVersion, owner, actual state, verifiedAt, ngoại lệ và bài học rút ra.

Khi làm được chuỗi này với các ca âm tính và bằng chứng lưu đầy đủ, hãy chọn nhánh đào sâu phù hợp ở phần 11: **federation và API authorization, IAM platform/IGA, security/PAM, governance/audit hoặc cloud workload identity**.

Điểm tiếp nối quan trọng nhất của **IAM lifecycle** là chuyển từ “đã biết quy trình Joiner–Mover–Leaver” sang **“có thể chứng minh người hoặc workload được cấp đúng quyền ở đúng thời điểm, và mọi quyền không còn lý do đã được thu hồi hoặc đang được xử lý minh bạch”**. Một hệ thống học tập hay sản xuất đều có giá trị hơn khi **quyết định, hành động và trạng thái thực tế** được liên kết bằng bằng chứng có thể kiểm tra lại.
