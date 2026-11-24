# Thu hồi quyền cũ trong Mover lifecycle

Khi một nhân viên thay đổi bộ phận, chức danh, nhiệm vụ hoặc phạm vi phụ trách, hệ thống Identity and Access Management (**IAM**) phải điều chỉnh những gì người đó được làm. Trong mô hình **Joiner–Mover–Leaver (JML)**, sự kiện **Mover** không chỉ là cấp thêm quyền mới: bước đặc biệt quan trọng là **thu hồi những quyền không còn phù hợp** với vai trò sau thay đổi.

Đây là chủ đề **“Thu hồi quyền cũ”** của chương **Mover lifecycle**, thuộc module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module nghiên cứu vòng đời danh tính từ xác minh, tạo tài khoản và cấp quyền đến rà soát, điều chỉnh và thu hồi; vì vậy bài học liên kết nguồn nhân sự, IdP/SSO, provisioning/deprovisioning bằng SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và phòng chống **quyền truy cập tồn dư**.

**Tình huống xuyên suốt:** Mai trước đây làm nhân viên Kinh doanh và có quyền xem hồ sơ khách hàng vùng miền Bắc. Mai được điều chuyển sang bộ phận Tài chính, có quyền xem hóa đơn đã duyệt. Nếu IAM chỉ **thêm nhóm Finance** mà không **gỡ các quyền Sales cũ**, Mai sẽ có đồng thời hai tập quyền. Trường hợp này tạo ra **privilege creep** (tích lũy quyền qua thời gian), mở rộng nguy cơ rò rỉ dữ liệu, sai phạm phân tách nhiệm vụ và quyền tồn tại ngoài nhu cầu công việc.

## 1. Thu hồi quyền cũ là gì?

**Thu hồi quyền cũ (old entitlement revocation)** là quá trình xác định, loại bỏ và kiểm chứng việc loại bỏ những quyền mà chủ thể không còn cần hoặc không còn được phê duyệt sau một sự kiện thay đổi vai trò.

“Quyền” ở đây rộng hơn một dòng role trong IdP. Nó có thể là:

- Membership trong nhóm IdP, nhóm lồng nhau hoặc nhóm ứng dụng.
- Vai trò RBAC, quyền IAM cloud, vai trò cơ sở dữ liệu, quyền trong SaaS.
- Entitlement cấp trực tiếp cho người dùng, ACL trên thư mục/tài liệu, quyền chia sẻ dự án.
- Quyền dựa trên thuộc tính ABAC, quan hệ với tài nguyên (owner, manager, approver), đơn vị/tenant hoặc vùng dữ liệu.
- Đặc quyền tạm thời, quyền elevated access qua PAM/PIM, quyền được ủy quyền thay người khác.
- Session, token, API key, credential ứng dụng hoặc quyền truy cập offline còn hiệu lực từ vai trò trước.
- Quyền gián tiếp thông qua tài khoản dịch vụ, repository, secret manager, automation hoặc tài khoản cục bộ.

**Thu hồi thành công** không thể đo chỉ bằng thông báo “remove group succeeded”. Cần chứng minh tại **điểm thực thi cuối** rằng quyền cũ không còn giúp thực hiện hành động được bảo vệ, và xử lý rõ những đường truy cập chưa thể thu hồi tức thì.

### Khác biệt giữa sửa thông tin và thu hồi quyền

| Hoạt động | Ví dụ | Đã đủ để thu hồi chưa? |
| --- | --- | --- |
| Đổi chức danh trong HRIS | \`department=Finance\`. | Chưa: hệ thống đích có thể vẫn giữ quyền Sales. |
| Gỡ nhóm trong IdP | Xóa \`Sales-North\` khỏi membership. | Chưa chắc: có quyền trực tiếp, phiên cũ, tài khoản cục bộ hoặc nhóm lồng nhau. |
| Tắt ứng dụng trên launcher SSO | Ẩn biểu tượng CRM. | Chưa: API/session CRM có thể vẫn nhận request. |
| Gỡ role tại ứng dụng | Xóa \`crm.customer-reader\`. | Cần kiểm chứng effective permission và các grant khác. |
| Thu hồi session/token | Kết thúc phiên hoặc vô hiệu refresh token. | Cần kết hợp với gỡ entitlement; không thay thế quyền ở hệ thống đích. |
| Đối soát quyền cuối đường | Thử truy cập bị từ chối, truy vấn trạng thái thực tế. | Là bằng chứng quan trọng, nhưng còn phải phủ đủ tài nguyên và đường truy cập. |

## 2. Vì sao Mover khó hơn Joiner và Leaver ở góc độ quyền?

Ở **Joiner**, hệ thống thường bắt đầu từ tập quyền cơ sở mới; ở **Leaver**, mục tiêu thường là ngừng mọi truy cập doanh nghiệp của danh tính nghỉ việc theo chính sách. **Mover** phức tạp hơn vì phải **giữ đúng những quyền còn hợp lệ**, **gỡ đúng những quyền cũ** và **bổ sung quyền mới** mà không làm gián đoạn phần công việc hợp pháp.

Một người chuyển từ vị trí A sang vị trí B có thể có:

1. **Quyền chung** của toàn tổ chức, cần giữ lại (ví dụ cổng thông tin nhân viên).
2. **Quyền chỉ hợp lệ với vai trò A**, phải thu hồi.
3. **Quyền chỉ hợp lệ với vai trò B**, phải cấp mới sau phê duyệt.
4. **Quyền dùng chung A và B**, giữ nguyên nếu điều kiện vẫn đáp ứng.
5. **Ngoại lệ tạm thời** để bàn giao, phải có chủ sở hữu và hạn hết hiệu lực.
6. **Quyền không rõ nguồn gốc**, cần điều tra trước khi quyết định.

Vì vậy, Mover phải được xử lý như **tái tính toán quyền mong muốn** dựa trên nguồn danh tính và chính sách hiện hành, thay vì thao tác thủ công “thêm một vài nhóm”.

## 3. Nguồn sự kiện và mốc hiệu lực của Mover

Sự kiện thay đổi có thể đến từ HRIS, hệ thống quản lý nhà thầu, hệ thống tổ chức nội bộ hoặc workflow phê duyệt. Mỗi sự kiện cần mang thông tin đủ để IAM quyết định quyền phải đổi **khi nào**.

| Trường dữ liệu | Mục đích |
| --- | --- |
| \`subjectId\` ổn định | Ghép đúng chủ thể, không dựa hoàn toàn vào email có thể thay đổi. |
| \`eventId\` và phiên bản sự kiện | Phát hiện sự kiện lặp, tránh áp bản cũ lên trạng thái mới. |
| \`effectiveAt\` | Thời điểm việc chuyển vai trò có hiệu lực theo nguồn có thẩm quyền. |
| \`previousRole\`, \`newRole\` | Mô tả thay đổi; là thông tin đầu vào để tính lại quyền. |
| Phòng ban, đơn vị, tenant, manager, địa bàn | Thuộc tính ABAC và phạm vi tài nguyên liên quan. |
| Người phê duyệt/nguồn yêu cầu | Bằng chứng thay đổi là hợp lệ và có người chịu trách nhiệm. |
| Hạn bàn giao/ngoại lệ | Cho phép quyền cũ trong một khoảng được kiểm soát, nếu chính sách cho phép. |
| Correlation ID | Nối sự kiện HR, IAM, IdP, SCIM, SaaS và audit. |

**Không nên kích hoạt quyền mới chỉ vì một dòng HR đã được nhập trước ngày hiệu lực.** Tương tự, nếu sự kiện đến muộn, cần có quy tắc xử lý để không kéo dài quyền cũ một cách vô hạn.

### Ví dụ sự kiện Mover

~~~json
{
  "eventId": "mover-2026-1042",
  "type": "workforce.mover.effective",
  "subjectId": "person-4821",
  "previousDepartment": "SALES_NORTH",
  "newDepartment": "FINANCE",
  "effectiveAt": "2026-11-25T00:00:00Z",
  "source": "trusted-hris",
  "revision": 12,
  "approvalRef": "approval-872"
}
~~~

Đây là sự kiện **minh họa**. Consumer không được tin một JSON đến từ nguồn bất kỳ: cần xác thực nguồn, quyền phát hành, tính toàn vẹn, phiên bản và thứ tự. Sự kiện trùng phải được xử lý **idempotent**; sự kiện cũ đến muộn không được tự ý khôi phục role đã thu hồi.

## 4. Tính quyền mong muốn trước khi thu hồi

Trọng tâm của quy trình là phân biệt:

- **Actual entitlements:** những quyền đang thực sự có trên IdP, ứng dụng, hệ thống dữ liệu và các đường truy cập.
- **Desired entitlements:** những quyền người dùng **nên có** sau Mover, theo vai trò mới, thuộc tính, phê duyệt và ngoại lệ hợp lệ.

Ký hiệu:

\[
\text{RevokeCandidates} = \text{Actual} \setminus \text{Desired}
\]

\[
\text{GrantCandidates} = \text{Desired} \setminus \text{Actual}
\]

\[
\text{Keep} = \text{Actual} \cap \text{Desired}
\]

Các tập hợp là mô hình khái niệm; thực tế, một quyền có thể được tạo bởi **nhiều đường cấp**. Ví dụ \`read.customer\` vừa được gán qua nhóm \`Sales\` vừa qua ACL trực tiếp. Gỡ nhóm nhưng quyền vẫn tồn tại qua ACL, nên phải tính **effective access** và **nguồn cấp quyền**, không chỉ đối chiếu nhãn role.

### Ma trận trước/sau của Mai

| Quyền | Trước Mover | Sau Mover mong muốn | Xử lý |
| --- | --- | --- | --- |
| Đăng nhập SSO, email nội bộ | Có | Có | Giữ, vẫn áp policy xác thực. |
| Xem CRM vùng Bắc | Có qua nhóm Sales-North | Không | Gỡ nhóm/role và kiểm tra ACL/phiên CRM. |
| Xuất toàn bộ khách hàng từ CRM | Có theo ngoại lệ cũ | Không | Thu hồi ngoại lệ trực tiếp, API token, quyền export. |
| Xem hóa đơn Finance đã duyệt | Không | Có | Cấp sau phê duyệt và điều kiện truy cập. |
| Phê duyệt thanh toán | Không | Không | Không cấp chỉ vì vào Finance. |
| Truy cập kho tài liệu chung | Có | Có | Giữ nếu vẫn thuộc baseline chung. |
| Quyền bàn giao CRM trong 3 ngày | Không có mặc định | Chỉ khi được duyệt | Cấp ngoại lệ riêng, phạm vi hẹp, tự hết hạn. |

**Quyền mong muốn là quyết định nghiệp vụ được mã hóa thành chính sách**, không thể suy ra đầy đủ từ chuỗi tên bộ phận. Cùng là nhân viên Finance, một người có thể chỉ đọc hóa đơn, người khác được thực hiện duyệt chi và người thứ ba có quyền kiểm toán.

## 5. Phân loại nguồn quyền cần thu hồi

Muốn thu hồi đúng, cần biết quyền được cấp từ đâu và có thể bị tái tạo bởi cơ chế nào.

| Nguồn quyền | Ví dụ | Cách thu hồi phù hợp |
| --- | --- | --- |
| **RBAC role theo nhóm** | Membership \`Sales-Reader\` cấp quyền CRM. | Cập nhật nhóm/role tại nguồn có thẩm quyền, đồng bộ tới ứng dụng, kiểm tra quyền cuối. |
| **Nhóm lồng nhau** | Nhóm \`Regional-Sales\` nằm trong \`CRM-Users\`. | Phân tích đường membership; gỡ một liên kết có thể chưa loại toàn bộ đường cấp. |
| **Direct entitlement** | Role \`Export-All-Customers\` gán trực tiếp. | Thu hồi grant trực tiếp tại nơi quản lý, không đợi đồng bộ nhóm. |
| **ACL và chia sẻ** | Quyền đọc folder, dashboard hoặc tài liệu khách hàng. | Gỡ ACL, link chia sẻ, ownership/delegation không còn phù hợp. |
| **ABAC/attribute-based** | \`department=Sales\` mở quyền theo policy. | Cập nhật thuộc tính tin cậy và vô hiệu cache/chính sách còn dựa trên giá trị cũ. |
| **Quyền tạm thời** | PAM/PIM activation, emergency role, break-glass được cấp sai phạm vi. | Kết thúc activation và thu hồi eligibility nếu không còn hợp lệ; xác minh session. |
| **Quyền trong hệ thống dữ liệu** | Database role, row-level permission, BI workspace. | Thu hồi grant/role cục bộ, policy và các account phụ. |
| **API token/credential cục bộ** | API key của CRM, personal access token, SSH key. | Revoke token/key và kiểm tra service/automation còn phụ thuộc. |
| **Quyền điều khiển service account** | Có thể đọc secret hoặc thay trust policy của tích hợp. | Thu hồi quyền vault, repository, cloud role và CI/CD; đánh giá rotation credential. |
| **Phiên đăng nhập còn sống** | SSO session hoặc SaaS session có claim nhóm cũ. | Session invalidation/token revocation hoặc đánh giá quyền lại theo mô hình ứng dụng. |

Không phải mọi quyền đều do IdP trực tiếp quản lý. Nếu ứng dụng cho phép quản trị viên cấp vai trò thủ công, cần **kiểm kê và đối soát** quyền tại ứng dụng đó. Nếu một quyền đến từ quyền sở hữu tài nguyên, cần chuyển giao ownership đúng quy trình trước khi thu hồi.

## 6. Quy trình chuẩn thu hồi quyền cũ

~~~mermaid
flowchart TD
    HR["Sự kiện Mover được xác minh"] --> ID["Xác định subject, hiệu lực, thuộc tính mới"]
    ID --> SNAP["Chụp actual entitlements và nguồn cấp"]
    SNAP --> CALC["Tính desired entitlements"]
    CALC --> DIFF["Phân loại KEEP / REVOKE / GRANT / EXCEPTION"]
    DIFF --> SOD["Kiểm tra xung đột nhiệm vụ và phê duyệt"]
    SOD --> EXEC["Thu hồi theo nguồn quyền và ứng dụng đích"]
    EXEC --> SESS["Xử lý phiên, token, cache, credential"]
    SESS --> REC["Đối soát effective access / readback"]
    REC --> DEC{"Có quyền cũ còn dùng được?"}
    DEC -->|Có| FIX["Retry / escalation / compensating control"]
    FIX --> REC
    DEC -->|Không| AUDIT["Lưu bằng chứng và đóng Mover"]
~~~

Quy trình thao tác đề xuất:

1. **Xác minh sự kiện:** bảo đảm thay đổi đến từ HRIS hoặc nguồn được ủy quyền, đúng \`subjectId\`, đúng thời điểm và revision.
2. **Chụp hiện trạng:** thu thập role, group, entitlement, ACL, key/phiên liên quan ở các hệ thống trong phạm vi. Ghi lại nguồn cấp quyền để có cơ sở đối chiếu.
3. **Xác định quyền đích:** tính baseline vai trò mới, điều kiện ABAC, ngoại lệ đã phê duyệt, phân tách nhiệm vụ.
4. **Lập kế hoạch chênh lệch:** chia quyền thành **KEEP, REVOKE, GRANT, INVESTIGATE, TEMPORARY**; xác định chủ sở hữu từng hành động.
5. **Thẩm định xung đột:** tránh cho phép đồng thời hai role có thể gây sai phạm; với quyền nhạy cảm, chặn xung đột trước khi mở quyền mới.
6. **Thu hồi quyền cũ:** gỡ ở nguồn quản trị và từng hệ thống đích, sử dụng API/connector/SCIM hoặc cơ chế nội bộ tương ứng.
7. **Xử lý phiên và credential:** xác định truy cập nào còn hiệu lực từ token/cached claims, session, personal token hoặc key.
8. **Đối soát và thử quyền:** kiểm tra trạng thái ở hệ thống đích cùng hành động thực tế; phát hiện nguồn quyền còn sót.
9. **Xử lý lỗi và ngoại lệ:** retry an toàn khi lỗi tạm, escalation khi bị từ chối hoặc thiếu connector, áp kiểm soát bù trừ nếu cần.
10. **Đóng hồ sơ Mover:** chỉ khi có bằng chứng trạng thái cuối hoặc ngoại lệ còn mở đã được phê duyệt và quản trị theo SLA.

Tổ chức có thể ưu tiên thứ tự thu hồi/cấp mới theo mức rủi ro và yêu cầu liên tục công việc, nhưng **không được để xung đột nhiệm vụ nguy hiểm tồn tại chỉ để tránh gián đoạn**.

## 7. IdP, SSO, SCIM và ranh giới đồng bộ

### IdP và nhóm

IdP thường quản lý danh tính, nhóm và một phần entitlement. Gỡ \`Sales\` khỏi IdP là bước quan trọng nhưng chưa kết luận được quyền đã biến mất ở mọi ứng dụng. Một số ứng dụng duy trì **nhóm cục bộ**, có chu kỳ đồng bộ riêng hoặc cấp quyền ngoài IdP.

### SCIM provisioning/deprovisioning

**SCIM** hỗ trợ các thao tác đồng bộ user/group đối với ứng dụng triển khai phù hợp. Trong Mover, connector có thể cập nhật thuộc tính người dùng, gỡ membership khỏi nhóm cũ và thêm nhóm mới. Tuy nhiên:

- SCIM không phải giao thức đăng nhập hoặc xóa session/token.
- Không phải ứng dụng nào cũng ánh xạ nhóm SCIM trực tiếp sang mọi role/ACL.
- Việc API trả kết quả thành công cần được **đọc lại** và kiểm tra ý nghĩa tại hệ thống đích.
- Một số quyền cấp trực tiếp tại ứng dụng sẽ tồn tại dù membership SCIM đã đổi.
- Hệ thống cần xử lý lỗi tạm thời, retry, giới hạn tốc độ, version/ETag hoặc concurrency khi có hỗ trợ.

Ví dụ minh họa thao tác SCIM **PATCH Group** để loại một member:

~~~http
PATCH /scim/v2/Groups/group-sales-north HTTP/1.1
Host: apps.example.org
Authorization: Bearer <valid-scoped-connector-token>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"user-4821\"]"
    }
  ]
}
~~~

Đây là **request minh họa**, không phải lệnh triển khai: cú pháp path/filter và cách server hỗ trợ cần kiểm tra theo cấu hình SCIM thực tế. Giá trị \`user-4821\` phải là **ID thành viên mà hệ thống đích hiểu**, thường ánh xạ qua inventory của connector; không tự dùng \`subjectId\` nội bộ nếu ID đích khác. Token connector phải có quyền vừa đủ và không đặt bí mật thật vào tài liệu hoặc log.

Sau PATCH cần đọc lại Group/User hoặc entitlement tương ứng, kiểm tra quyền trong ứng dụng rồi đối soát. Nếu membership bị tái tạo bởi rule đồng bộ khác, cần sửa **nguồn có thẩm quyền**, không chỉ gỡ thủ công ở đích.

### SSO, token và claims cũ

Một phiên SSO có thể đã xác thực thành công khi nhân viên còn thuộc Sales. Ứng dụng có thể đã tạo **session cục bộ** và ghi roles/claims vào cookie hoặc token. Kể cả sau khi IdP gỡ nhóm, phiên này có thể tiếp tục sử dụng quyền cũ cho tới khi token hết hạn hoặc ứng dụng đánh giá lại.

**Cần phân biệt bốn trạng thái:**

| Trạng thái | Ví dụ | Điều phải kiểm tra |
| --- | --- | --- |
| Danh tính/nhóm tại IdP | Sales group đã bị gỡ. | Đúng giá trị thuộc tính và membership mong muốn. |
| Tài khoản/role trong ứng dụng | CRM đã nhận thay đổi. | Actual role/ACL tại CRM không còn grant cũ. |
| Session/refresh token | Phiên CRM hoặc refresh token vẫn hoạt động. | Hỗ trợ revoke/logout, thời hạn, khả năng tái tạo session mới. |
| Access token tự chứa/cache quyền | Token hoặc cache lưu quyền Sales cũ. | Token lifetime, revocation/version/introspection hoặc kiểm tra quyền hiện hành ở API. |

**Không thể khẳng định “thu hồi ngay” chỉ nhờ đổi nhóm IdP** khi ứng dụng chỉ tin token tự chứa còn hạn mà không kiểm tra trạng thái hiện hành. Hệ thống cần thiết kế SLA thu hồi theo độ nhạy tài nguyên, token ngắn hạn hợp lý và cơ chế chặn/kiểm tra lại khi rủi ro cao.

## 8. RBAC, ABAC và kiểm tra quyền mức đối tượng

Một số quyền biến mất ngay sau khi cập nhật RBAC, nhưng một số phụ thuộc ABAC, quan hệ với đối tượng hoặc dữ liệu nghiệp vụ. Phân quyền thực tế thường kết hợp:

- **RBAC:** loại bỏ vai trò \`SALES_CUSTOMER_READER\`, giữ \`EMPLOYEE_BASIC\`, thêm \`FINANCE_INVOICE_READER\` nếu được duyệt.
- **ABAC:** thay \`department\`, \`costCenter\`, \`region\`, \`employmentCategory\` theo nguồn HR đáng tin; policy tự đánh giá quyền mới.
- **Resource ownership/relationship:** gỡ Mai khỏi danh sách owner của báo cáo Sales, khỏi ACL khách hàng và nhóm reviewer cũ.
- **Segregation of Duties (SoD):** nếu quyền Finance mới xung đột với quyền Sales cũ, phải tránh giai đoạn chồng lấn nguy hiểm hoặc yêu cầu cơ chế kiểm soát độc lập.

### Ví dụ policy trước/sau

~~~yaml
policyId: crm-customer-read
effect: allow
when:
  subjectEmploymentStatus: ACTIVE
  subjectRoleContains: SALES_CUSTOMER_READER
  subjectRegionEqualsResourceRegion: true
  subjectTenantEqualsResourceTenant: true
fallback: deny
~~~

Đây là pseudoconfiguration để minh họa ý nghĩa quyền. Sau Mover, \`SALES_CUSTOMER_READER\` không còn; API phải từ chối ngay theo hiệu lực chính sách, kể cả khi người dùng còn biết URL hoặc ID khách hàng.

**Tránh lỗi broken object level authorization (BOLA/IDOR):** gỡ một nhóm nhưng API vẫn trả dữ liệu khi người dùng đoán \`customerId\` là chưa đạt. Điểm thực thi phải kiểm tra đúng subject, action, tenant, vùng dữ liệu và đối tượng, không chỉ ẩn menu.

### Khi một quyền có nhiều đường cấp

Giả sử Mai có quyền CRM qua hai đường:

\[
P_{\text{CRM}} =
(\text{SalesGroup} \rightarrow \text{CRMReader})
\;\cup\;
(\text{DirectGrant} \rightarrow \text{CRMReader})
\]

Gỡ \`SalesGroup\` không loại \`DirectGrant\`. Cần truy vết **effective permission** và loại mọi đường cấp không còn được phép. Trong hệ thống có group nesting, inherited ACL hoặc policy động, việc phân tích phải bao gồm đường kế thừa tương ứng.

## 9. Thu hồi các quyền đặc quyền và tránh xung đột nhiệm vụ

Mover sang vai trò nhạy cảm hoặc chuyển khỏi vai trò đặc quyền cần được xử lý thận trọng hơn quyền đọc thông thường.

Ví dụ một nhân viên cũ có quyền **tạo nhà cung cấp** và vai trò mới có quyền **phê duyệt thanh toán**. Tổ chức có thể có chính sách **SoD** không cho một người vừa tạo vừa phê duyệt một đối tượng. Nếu cấp quyền mới trước khi gỡ quyền cũ, dù chỉ vài phút, người đó có thể thực hiện chuỗi tác vụ không được phép.

Các kiểm soát cần cân nhắc:

1. Xác định **toxic combinations** và chính sách phân tách nhiệm vụ từ trước.
2. Lập kế hoạch cắt quyền cũ trước khi mở quyền mới có xung đột.
3. Kết thúc quyền \`active\` lẫn quyền \`eligible\` trong PAM/PIM khi không còn hợp lệ.
4. Thu hồi session đặc quyền, quyền sudo/admin, console/cloud role và quyền điều khiển secret.
5. Chặn thiết lập lại quyền qua nhóm, automation hoặc tài khoản dự phòng không còn hợp lệ.
6. Giám sát bất thường trong thời gian chuyển giao và lưu bằng chứng phê duyệt.

**Break-glass account** hoặc quyền ứng cứu khẩn cấp phải được quản trị riêng. Không coi quyền ứng cứu là một “ngoại lệ thuận tiện” để giữ đặc quyền cũ; cần owner, log, giới hạn sử dụng và review.

## 10. Bàn giao công việc nhưng không tích lũy quyền

Đôi khi người chuyển vai trò cần đọc dữ liệu cũ để hoàn tất bàn giao. Cấm tuyệt đối mọi quyền ngay lập tức có thể làm gián đoạn vận hành; giữ toàn bộ quyền cũ vô thời hạn lại gây privilege creep.

**Cách xử lý phù hợp:** dùng **temporary exception** riêng với scope nhỏ nhất, lý do rõ và hạn hết hiệu lực tự động.

Ví dụ Mai cần xem **chỉ 20 hồ sơ khách hàng đã được giao**, trong vòng ba ngày, để chuyển trách nhiệm cho người thay thế:

~~~yaml
exceptionId: handover-2026-019
subjectId: person-4821
reason: "Bàn giao danh sách khách hàng trước khi chuyển Finance"
approvedBy: sales-manager-17
resourceScope:
  crmCustomerListRef: approved-handover-20
allowedActions:
  - crm.customer.read
deniedActions:
  - crm.customer.export-all
  - crm.customer.delete
validFrom: "2026-11-25T00:00:00Z"
validUntil: "2026-11-28T00:00:00Z"
autoRevoke: true
reviewOwner: iam-governance
~~~

Đây là **ví dụ mô tả chính sách**, không phải YAML chạy trực tiếp. Lựa chọn sử dụng ngoại lệ phải dựa trên phân loại dữ liệu và SoD; với quyền xung đột nghiêm trọng có thể cần phương án bàn giao khác, chẳng hạn người thay thế thực hiện công việc hoặc chia sẻ báo cáo đã lọc.

**Không nên giữ nguyên role Sales đầy đủ chỉ vì cần xem vài hồ sơ.** Nếu có thể, dùng cấp quyền mức đối tượng, read-only, có hạn và ghi audit. Khi đến \`validUntil\`, quyền phải tự hết hiệu lực ở điểm thực thi, không chỉ gửi email nhắc quản trị viên gỡ.

### Khi nào không nên kéo dài quyền cũ?

- Vai trò cũ và mới tạo xung đột nhiệm vụ không thể chấp nhận.
- Tài nguyên chứa dữ liệu nhạy cảm không còn cơ sở xử lý theo nhiệm vụ mới.
- Nhân viên đã có dấu hiệu lạm dụng hoặc đang chịu điều tra.
- Quyền cũ là đặc quyền quản trị cao không còn nhu cầu chính đáng.
- Không có cách bảo đảm tự thu hồi hoặc không có người chịu trách nhiệm đối soát.

## 11. Thu hồi quyền liên quan tới tài khoản dịch vụ

Một nhân viên có thể không dùng **service account** trực tiếp để đăng nhập, nhưng vẫn có quyền:

- Đọc/rotate client secret hoặc private key trong vault.
- Sửa trust policy của workload identity federation.
- Triển khai container/job vốn được cấp quyền production.
- Thay đổi repository, CI/CD variables hoặc Kubernetes service account binding.
- Đọc access token ở log/artifact hoặc dùng credential tích hợp SaaS.
- Phê duyệt yêu cầu cấp quyền hoặc sử dụng PAM để truy cập service identity.

Khi người đó chuyển vai trò, phải gỡ **quyền điều khiển và quyền tiếp cận credential** dù danh tính dịch vụ vẫn cần hoạt động. Nếu nhân viên đã từng biết bí mật dài hạn, cần đánh giá **rotation** và thu hồi secret/token theo rủi ro; chỉ gỡ quyền đọc vault hiện tại không xóa bản secret họ có thể đã sao chép.

**Không tự động xóa service account chỉ vì người sở hữu cũ chuyển bộ phận.** Dịch vụ có vòng đời riêng; cần bàn giao ownership, người phê duyệt, quyền vận hành và kiểm tra không còn đường can thiệp của chủ thể cũ.

## 12. Thứ tự thực thi, xử lý lỗi và tính nhất quán

Mover thường trải qua nhiều hệ thống khác nhau, không có một transaction ACID chung cho HRIS, IdP, SaaS và cơ sở dữ liệu. Vì vậy việc cập nhật có thể hoàn tất **một phần**.

Ví dụ:

1. HRIS xác nhận Mai đã vào Finance.
2. IAM gỡ Sales group thành công.
3. SCIM connector cập nhật CRM thất bại do giới hạn API.
4. Finance app đã cấp role mới.
5. CRM vẫn giữ session và ACL cũ.

Nếu chỉ nhìn bước 2 và 4, báo cáo có thể sai rằng Mover hoàn tất. Cần **theo dõi từng hệ thống**, retry hợp lệ, áp biện pháp hạn chế khi có quyền nhạy cảm còn tồn và không đóng workflow sớm.

### Mô hình trạng thái công việc thu hồi

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| \`PLANNED\` | Quyền cần thu hồi đã được xác định. | Chờ hiệu lực và điều kiện bắt đầu. |
| \`IN_PROGRESS\` | Đang gọi connector/API. | Lưu attempt và correlation ID. |
| \`APPLIED\` | Hệ thống đã chấp nhận thay đổi. | Chưa đóng; phải readback/đối soát. |
| \`VERIFIED\` | Trạng thái cuối đường đạt yêu cầu. | Có thể tính bước này hoàn tất. |
| \`RETRYABLE_FAILURE\` | Lỗi tạm: timeout, rate-limit, service unavailable. | Retry có backoff/idempotency. |
| \`BLOCKED\` | Lỗi quyền, mapping không rõ, policy xung đột, dữ liệu không nhất quán. | Escalate, điều tra, không tự bỏ qua. |
| \`EXCEPTION_APPROVED\` | Quyền giữ tạm có căn cứ và hạn rõ. | Theo dõi expiry, kiểm toán và tự thu hồi. |

**Chú ý điều kiện ghi đè:** một API lỗi timeout có thể đã thực hiện thao tác trước khi phản hồi thất bại. Retry phải đọc lại trạng thái hoặc sử dụng idempotency/cơ chế so sánh phiên bản để tránh cấp lại quyền ngoài ý muốn.

### Sự kiện đến sai thứ tự

Mai chuyển từ Sales → Finance, sau đó Finance → Audit trong cùng tháng. Nếu event Sales → Finance đến muộn sau event Finance → Audit, hệ thống không được phục hồi nhóm Finance. Thực thi cần kiểm tra **revision/effectiveAt từ nguồn có thẩm quyền** và tính quyền dựa trên trạng thái hiện hành, không tin cậy hoàn toàn thứ tự nhận message.

### Rollback có giới hạn

Nếu cấp quyền Finance mới thất bại, **không mặc định khôi phục tất cả quyền Sales đã thu hồi**. Quyền Sales có thể đã không còn được phép từ ngày hiệu lực; khôi phục sẽ tạo rủi ro. Một phương án phục hồi phải được phê duyệt theo nguyên tắc quyền tối thiểu, và có thể cấp chế độ tạm thời an toàn để xử lý công việc bị gián đoạn.

## 13. Pseudocode tính chênh lệch và thi hành thu hồi

Ví dụ dưới đây minh họa quy tắc “tính quyền mong muốn, xác định quyền cần gỡ, thực thi và đối soát”. Đây **không phải Java triển khai trực tiếp**, vì API và mô hình entitlement phụ thuộc nền tảng:

~~~java
// Pseudocode: dữ liệu HR, policy, entitlement được lấy từ nguồn đáng tin.
MoverResult processMover(MoverEvent event) {
    verifyTrustedEvent(event);
    if (event.revision() <= moverState.lastAppliedRevision(event.subjectId())) {
        return MoverResult.ignoredDuplicateOrStale();
    }

    WorkforceState workforce = hrRepository.currentState(event.subjectId());
    if (!workforce.matchesApprovedMove(event)) {
        return MoverResult.blocked("HR source/approval mismatch");
    }

    EntitlementSnapshot actual = entitlementReader.readEffectiveGrants(
        event.subjectId()
    );
    DesiredAccess desired = policyEngine.calculateDesiredAccess(
        workforce,
        approvals.forSubject(event.subjectId()),
        exceptions.validAt(event.subjectId(), event.effectiveAt())
    );

    RevocationPlan revocations = accessPlanner.findRevocations(actual, desired);
    GrantPlan grants = accessPlanner.findNewGrants(actual, desired);
    sodPolicy.assertNoProhibitedOverlap(actual, desired, grants);

    // Chỉ xử lý các hành động cần thiết, trong thứ tự kiểm soát rủi ro.
    for (RevocationAction action : revocations.orderedByRisk()) {
        connectorFor(action.target()).revokeIdempotently(action);
        revocationVerifier.verifyEffectiveAccessRemoved(action);
    }

    tokenSessionController.invalidateOrReevaluateAffectedAccess(
        event.subjectId(), revocations
    );

    for (GrantAction action : grants.afterRevocationBarriers()) {
        approvalPolicy.assertAllowed(action);
        connectorFor(action.target()).grantIdempotently(action);
    }

    reconciliation.assertDesiredAccess(event.subjectId(), desired);
    moverState.markVerified(event.subjectId(), event.revision());
    audit.recordMoverCompletion(event, actual, desired);
    return MoverResult.completed();
}
~~~

Các yêu cầu thực tế cần bổ sung:

- Connector lỗi phải tạo **trạng thái chưa hoàn tất** với retry/escalation; không để một exception thoát ra rồi mất công việc.
- \`readEffectiveGrants()\` phải bao gồm các nguồn grant trực tiếp, kế thừa, ACL và quyền từ hệ thống đích trong phạm vi; nếu không đủ nguồn, kết quả phải ghi nhận **coverage gap**.
- \`revokeIdempotently()\` và \`grantIdempotently()\` cần idempotency key/concurrency control, xử lý lỗi đã áp nhưng không trả lời.
- \`verifyEffectiveAccessRemoved()\` chỉ PASS khi kiểm tra được quyền phù hợp tại điểm thực thi, không chỉ mã HTTP 200.
- \`markVerified()\` chỉ nên chạy sau khi tất cả quyền bắt buộc đã được xác minh hoặc ngoại lệ hợp lệ đã được ghi nhận theo chính sách.

Nếu một hệ thống không có API thu hồi tự động, có thể tạo công việc cho owner ứng dụng thực hiện thủ công **với bằng chứng readback và hạn xử lý**. Không đánh dấu \`VERIFIED\` chỉ vì ticket đã tạo.

## 14. Xác minh cuối đường: từ “đã gỡ” đến “không còn truy cập”

Một bài kiểm tra tốt đối với quyền cũ cần trả lời cả **trạng thái cấu hình** và **khả năng thực thi hành động**.

| Kiểm tra | Ví dụ | Kết quả yêu cầu |
| --- | --- | --- |
| **IdP membership** | Mai không còn \`Sales-North\`. | Membership cũ đã gỡ. |
| **SCIM/app roles** | CRM không còn group/role Sales của Mai. | Readback đúng, không bị rule khác gán lại. |
| **Direct grants/ACL** | Mai không còn quyền export khách hàng qua ACL hoặc grant thủ công. | Không có đường cấp còn hoạt động. |
| **Policy ABAC** | Mai thuộc Finance theo nguồn HR và API dùng thuộc tính mới. | Không còn quyết định dựa trên department cũ. |
| **Session/token** | Phiên CRM từ trước Mover không còn dùng được quyền Sales. | Bị thu hồi hoặc API đánh giá lại quyền đúng. |
| **Đường API trực tiếp** | Request đọc khách hàng bằng ID hợp lệ và phiên cũ. | Bị từ chối theo policy, không rò rỉ dữ liệu. |
| **Vault/service account** | Mai không thể đọc key hoặc sửa pipeline của nhóm cũ. | Quyền quản lý/secret đã gỡ; credential biết trước được xử lý. |
| **Quyền ngoại lệ** | Quyền bàn giao chỉ đọc và tự hết hạn sau 3 ngày. | Scope và thời hạn được thực thi thật. |

**Kiểm thử truy cập phải được tổ chức có kiểm soát**, sử dụng principal/test fixture hoặc phép thử được cho phép, tránh đọc dữ liệu nhạy cảm thật chỉ để chứng minh quyền đã gỡ. Khi không thể thử trực tiếp, cần có bằng chứng cấu hình và cơ chế xác nhận tương ứng.

### Vì sao kiểm tra một API chưa đủ?

Một người không mở được giao diện CRM vẫn có thể gọi API bằng personal access token; mất quyền \`customer.read\` nhưng vẫn có \`customer.export\`; bị gỡ nhóm chính nhưng còn quyền ở nhóm lồng hoặc ACL. Vì vậy cần chọn các **đường truy cập có ý nghĩa bảo mật** để kiểm tra, nhất là quyền export, approve, admin, secret-read và data-write.

## 15. Kiểm toán và bằng chứng cần lưu

Mỗi Mover nên tạo ra một **audit trail nối được từ sự kiện nhân sự tới quyết định ở hệ thống đích**:

| Bằng chứng | Thông tin gợi ý | Ý nghĩa |
| --- | --- | --- |
| Nguồn Mover | Event ID, subject ID, old/new role, effectiveAt, revision, approval. | Vì sao quyền cần thay đổi? |
| Trước/sau | Snapshot entitlement, nguồn grant, thời điểm đọc, desired state. | Quyền nào cần gỡ/giữ/cấp? |
| Quyết định policy | Policy version, SoD result, ngoại lệ, người phê duyệt. | Vì sao một quyền được giữ hoặc loại? |
| Thao tác revoke | Target system, entitlement, actor/connector, attempt, timestamp, kết quả. | Đã yêu cầu hệ thống nào làm gì? |
| Readback | Effective permission, trạng thái app, phiên/token, kiểm tra API thích hợp. | Thu hồi có hiệu lực thật không? |
| Lỗi và xử lý | Mã lỗi, retry, escalation, owner và SLA. | Có đường truy cập nào còn tồn? |
| Kết thúc | Thời gian hoàn thành, ngoại lệ còn hiệu lực, reviewer. | Mover có đạt chính sách hay còn nợ xử lý? |

Không đưa mật khẩu, private key, client secret, access token hoặc refresh token vào log. Mọi ID tài khoản và thông tin nhân sự phải được phân quyền và lưu theo chính sách bảo vệ dữ liệu. Dùng correlation ID và đồng hồ đồng bộ để tái dựng thứ tự sự kiện.

### Chỉ số theo dõi

- **Revocation latency:** thời gian từ mốc Mover có hiệu lực tới lúc quyền cũ thực sự không còn hiệu lực tại từng đích.
- **Residual entitlement count:** số quyền còn tồn mà không có căn cứ role mới hoặc ngoại lệ hợp lệ.
- **Mover completion rate:** tỷ lệ sự kiện có đủ readback và không còn blocker.
- **Reconciliation drift:** chênh lệch giữa desired entitlement và effective access thực tế.
- **Exception aging:** số ngoại lệ bàn giao đã quá hạn nhưng vẫn còn quyền.
- **Privilege creep rate:** xu hướng tích lũy entitlement ngoài baseline qua nhiều lần chuyển vai trò.
- **SoD violations:** số trường hợp cặp quyền xung đột xuất hiện hoặc chưa được xử lý.
- **Orphaned ownership:** tài khoản dịch vụ, thư mục, repository, tài nguyên còn owner thuộc vai trò cũ và chưa bàn giao.

Không nên đặt một chỉ số duy nhất cho tất cả hệ thống. Thời gian thu hồi quyền phê duyệt thanh toán có thể cần ngắn hơn nhiều so với quyền đọc tài liệu chung; mỗi nhóm tài nguyên nên có mức ưu tiên và SLA được phê duyệt.

## 16. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Mover chỉ thêm role mới. | Quyền cũ tích lũy, có thể xung đột nhiệm vụ. | Tính desired state và chênh lệch revoke/grant. |
| Chỉ thay trường \`department\` trong HRIS. | Group và quyền tại ứng dụng cũ không đổi. | Liên kết event tới IAM/connector và readback cuối. |
| Chỉ gỡ IdP group. | Quyền trực tiếp, ACL, nested group vẫn tồn tại. | Thu thập nguồn grant và kiểm tra effective permission. |
| Ẩn biểu tượng ứng dụng. | Phiên/API token cũ vẫn truy cập. | Thu hồi quyền ở backend và xử lý session/token. |
| Dùng token chứa role cũ quá lâu. | API tiếp tục cho phép từ claims stale. | Token TTL phù hợp, revoke/version/introspection hoặc re-evaluation. |
| Cấp quyền mới trước khi gỡ quyền xung đột. | Tạo cửa sổ SoD violation. | Thiết kế barrier thu hồi trước cấp theo rủi ro. |
| Giữ role Sales đầy đủ để bàn giao vài dữ liệu. | Quyền quá rộng tồn tại lâu. | Ngoại lệ giới hạn tài nguyên, chỉ đọc, có hạn tự thu hồi. |
| Không quản lý quyền secret/pipeline. | Người chuyển nhóm vẫn điều khiển workload cũ. | Rà soát vault, CI/CD, repo, service account ownership. |
| Đánh dấu xong khi API trả 200. | Đích có thể chưa áp hoặc quyền được tái tạo. | Readback và kiểm thử quyết định quyền. |
| Retry sự kiện cũ mà không kiểm tra revision. | Khôi phục vai trò đã thu hồi. | Idempotency, ordering và tính quyền theo nguồn hiện hành. |
| Khôi phục toàn bộ quyền cũ khi cấp quyền mới lỗi. | Vi phạm chính sách sau ngày hiệu lực. | Escalation/kiểm soát bù trừ, phê duyệt quyền tạm nếu thật sự cần. |

## 17. Tình huống thực hành: chuyển từ Sales sang Finance

**Bối cảnh:** Mai chuyển sang Finance lúc 00:00 UTC ngày 25/11. Trước đó Mai có role \`Sales-North\`, quyền \`crm.customer.export\` gán trực tiếp, quyền xem một thư mục được chia sẻ, token CRM và quyền xem một secret phục vụ job của Sales. Finance yêu cầu đọc hóa đơn đã duyệt nhưng không được phê duyệt thanh toán.

### Bước 1 – Kiểm kê quyền đang có

~~~text
SSO / basic employee access                     KEEP
Sales-North group                               REVOKE
crm.customer.read (inherited from Sales-North)  REVOKE
crm.customer.export (direct grant)              REVOKE
Sales shared folder ACL                         REVOKE
Sales integration secret-reader                 REVOKE
CRM session and personal API token              INVALIDATE / REEVALUATE
Finance invoice.approved.read                   GRANT AFTER APPROVAL
Finance payment.approve                         DO NOT GRANT
~~~

### Bước 2 – Quyết định thứ tự

Trước thời điểm hiệu lực, tổ chức xác nhận quyền Finance và xác định SoD. Tại mốc chuyển, IAM gỡ quyền Sales nhạy cảm, đặc biệt \`export\` và \`secret-reader\`, trước khi mở Finance entitlement có khả năng xung đột. Các quyền nhân viên cơ sở được giữ.

### Bước 3 – Thực thi và đối soát

Connector gỡ membership/role tại IdP và CRM, xóa direct grant/ACL, khóa quyền đọc vault và thu hồi personal token phù hợp. Một giao dịch SCIM có thể thất bại: workflow ghi rõ \`RETRYABLE_FAILURE\`, thử lại theo chính sách và không báo hoàn tất cho CRM khi chưa đọc lại.

API CRM phải từ chối request xem/xuất khách hàng của Mai, kể cả từ một phiên được tạo trước Mover. API hóa đơn chỉ cho xem những bản ghi nằm trong phạm vi Finance được phép; không tự cấp \`approve\`.

### Bước 4 – Trường hợp cần bàn giao

Quản lý Sales đề nghị Mai xem ba hồ sơ đang bàn giao trong hai ngày. Chủ sở hữu dữ liệu và IAM kiểm tra mức nhạy cảm/SoD; nếu được phép thì cấp **ngoại lệ read-only cho ba hồ sơ**, tự hết hạn, có log. Quyền export toàn bộ CRM không được khôi phục.

### Bước 5 – Điều kiện đóng hồ sơ

Hồ sơ được đóng khi mọi quyền \`REVOKE\` đã có trạng thái \`VERIFIED\`, quyền mới đúng phê duyệt, các ngoại lệ còn mở đều có thời hạn/owner và không có cửa sổ xung đột nhiệm vụ chưa được xử lý. Log lưu dấu thời gian và nguồn chứng thực.

## 18. Bộ kiểm thử cần có

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Sales → Finance, nhóm Sales đã gỡ nhưng quyền export gán trực tiếp còn sống. | Mover chưa hoàn tất; truy ra direct grant và thu hồi. |
| Nhân viên có cả membership trực tiếp và qua nested group. | Không còn quyền từ bất kỳ đường cấp không hợp lệ nào. |
| CRM nhận SCIM PATCH nhưng API vẫn cho đọc khách hàng qua session cũ. | Coi revocation chưa đạt yêu cầu; xử lý session/token hoặc đánh giá quyền lại. |
| Finance role cần phê duyệt, HR đã đổi department nhưng chưa có approval. | Không tự cấp quyền nhạy cảm. |
| Quyền Sales và Finance xung đột SoD. | Ngăn chồng lấn; gỡ quyền xung đột trước khi cấp. |
| Event Mover cũ đến sau một event Mover mới hơn. | Không khôi phục quyền cũ; kiểm tra revision và nguồn hiện hành. |
| Connector CRM timeout sau khi đã thực hiện revoke. | Retry an toàn bằng readback/idempotency; không tạo thay đổi ngược. |
| Người dùng còn quyền vào vault chứa secret của nhóm cũ. | Gỡ quyền vault; đánh giá rotation credential đã có thể bị sao chép. |
| Ngoại lệ bàn giao quá hạn. | Tự thu hồi ở điểm thực thi; báo lỗi nếu vẫn truy cập được. |
| Cấp Finance thất bại sau khi gỡ Sales. | Không tự khôi phục Sales; dùng workflow xử lý/ngoại lệ được phê duyệt. |
| Giao diện ẩn CRM nhưng API gọi trực tiếp vẫn trả dữ liệu. | Kiểm thử thất bại; bổ sung server-side authorization. |
| Mai giữ quyền chung như email, SSO, cổng nhân viên. | Không thu hồi nhầm baseline hợp lệ. |
| Identity của job Sales vẫn hoạt động nhưng owner chuyển phòng ban. | Chuyển owner và gỡ quyền điều khiển của Mai, không xóa job nếu vẫn cần. |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Một nhân viên chuyển từ Sales sang Finance, IAM đã cấp Finance role. Vì sao chưa thể coi Mover hoàn tất?

**Trả lời:** Phải xác định và thu hồi các role, group, ACL, token và quyền cấp trực tiếp từ Sales không còn cần thiết; đồng thời đối soát quyền ở hệ thống đích để tránh privilege creep.

**Câu 2.** Đã gỡ người dùng khỏi nhóm Sales ở IdP. Điều đó có chứng minh không thể truy cập CRM nữa không?

**Trả lời:** Không. CRM có thể còn direct grant, nhóm lồng nhau, session hoặc token cũ. Cần kiểm tra effective access tại ứng dụng và đường API liên quan.

**Câu 3.** Trong Mover, vì sao nên tính tập quyền mong muốn trước khi thực thi?

**Trả lời:** Vì có quyền cần giữ, quyền phải gỡ và quyền mới cần cấp. Nếu chỉ xóa mọi quyền của vai trò cũ theo tên, có thể thu hồi nhầm baseline hoặc bỏ sót quyền cấp ngoài nhóm.

**Câu 4.** Khi cần bàn giao công việc, nên giữ nguyên toàn bộ quyền Sales của nhân viên trong một tháng không?

**Trả lời:** Không mặc định. Nếu thật sự cần, cấp ngoại lệ nhỏ nhất về hành động, tài nguyên và thời gian, có phê duyệt, kiểm toán, giới hạn SoD và tự thu hồi.

**Câu 5.** Tại sao API trả HTTP 200 cho yêu cầu SCIM remove chưa đủ chứng minh thu hồi thành công?

**Trả lời:** Hệ thống đích có thể còn cấp quyền từ nguồn khác hoặc chưa áp vào authorization/session. Cần readback trạng thái và kiểm tra quyết định truy cập có ý nghĩa.

**Câu 6.** Một service account vẫn phục vụ tích hợp cũ, nhưng nhân viên quản lý nó chuyển bộ phận. Phải làm gì?

**Trả lời:** Giữ danh tính dịch vụ nếu tích hợp còn cần; chuyển owner, gỡ quyền quản trị/vault/pipeline của nhân viên cũ và đánh giá rotation credential mà người đó có thể biết.

**Câu 7.** Nếu cấp quyền Finance thất bại sau khi gỡ Sales, hệ thống có nên tự trả lại mọi quyền Sales để tránh gián đoạn?

**Trả lời:** Không. Quyền Sales có thể không còn hợp lệ từ mốc chuyển vai trò. Cần xử lý lỗi, escalation hoặc phương án tạm có phê duyệt, scope/hạn rõ và không vi phạm SoD.

---

**Ghi nhớ:** Thu hồi quyền cũ trong Mover là quá trình **tính lại quyền mong muốn, tìm mọi đường cấp quyền không còn hợp lệ, thu hồi thực sự tại hệ thống đích và kiểm chứng bằng effective access**. IAM phải nối HRIS, IdP/SSO, SCIM, RBAC/ABAC, ACL, session/token và tài khoản dịch vụ để vừa giữ đúng quyền công việc còn cần thiết vừa ngăn **privilege creep, xung đột nhiệm vụ và quyền truy cập tồn dư**.
