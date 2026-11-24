# Kiểm thử authorization trong IAM: chứng minh đúng quyền, đúng tài nguyên và đúng vòng đời

**Kiểm thử authorization (authorization testing)** là quá trình xác minh rằng hệ thống **chỉ cho phép** những hành động mà chính sách đã phê duyệt, đồng thời **từ chối** mọi hành động ngoài phạm vi trên đúng tài nguyên, tenant và thời điểm. Đối tượng kiểm thử không chỉ là giao diện hay vai trò được hiển thị trong token: kết quả cần được kiểm chứng tại **điểm thực thi quyền (Policy Enforcement Point – PEP)**, chẳng hạn backend API, dịch vụ dữ liệu, gateway hoặc hệ thống nghiệp vụ.

Bài thuộc chương **Authorization** trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi chung của module là quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh danh tính, tạo và cấp quyền khi gia nhập, rà soát và thay đổi quyền khi chuyển vai trò, thu hồi khi rời tổ chức. Kiểm thử authorization kết nối với **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, audit** và mục tiêu giảm **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Nam thuộc phòng Sales được phép xem khách hàng của tenant A, trong khi Lan thuộc Finance được phép duyệt hóa đơn của tenant B. Nếu Nam sửa tham số customerId để xem khách hàng tenant B, hoặc Lan dùng endpoint admin chưa xuất hiện trên giao diện để cấp quyền, **đăng nhập hợp lệ không phải lý do để API cho phép**. Khi Nam chuyển sang Finance, hệ thống còn phải chứng minh token/session cũ không giúp Nam tiếp tục xuất dữ liệu Sales ngoài thời hạn chính sách.

## 1. Authentication khác authorization

| Khía cạnh | Authentication | Authorization |
| --- | --- | --- |
| Câu hỏi | Ai đang đưa ra yêu cầu và đã chứng minh danh tính thế nào? | Chủ thể được thực hiện hành động nào trên tài nguyên nào, trong ngữ cảnh nào? |
| Ví dụ | Đăng nhập SSO với passkey và MFA. | Đọc hóa đơn thuộc tenant hiện hành, không được tự phê duyệt hóa đơn mình tạo. |
| Thành phần | IdP, authenticator, OIDC/SAML, session. | RBAC/ABAC/ReBAC, PDP, PEP, ACL, backend. |
| Kiểm thử điển hình | Token không hợp lệ, tài khoản disabled, MFA step-up. | User khác owner, sai tenant, sai role, sai trạng thái resource. |
| Rủi ro nếu chỉ kiểm tầng này | Người dùng đúng danh tính vẫn có thể vượt quyền. | Không có danh tính tin cậy để áp chính sách đúng. |

Một access token có chữ ký hợp lệ chỉ là **đầu vào** cho quyết định quyền. Với OAuth, token còn phải đúng **issuer, audience, scope và hiệu lực**. Sau đó backend vẫn cần kiểm tra người dùng/workload có quyền trên **tài nguyên cụ thể**. Với OIDC, **ID token dùng cho client xác nhận kết quả đăng nhập**, không phải quyền tự động gọi mọi API.

**Ẩn nút “Xóa”, “Duyệt” hoặc “Export” trong UI không phải authorization.** Kiểm thử bắt buộc gọi điểm thực thi thực sự trong môi trường được phép để xác minh backend từ chối hành động không đủ quyền.

## 2. Mục tiêu và phạm vi của kiểm thử authorization

Một chiến lược test cần chứng minh cả **tính đúng** lẫn **tính đầy đủ**:

1. **Allow đúng:** chủ thể đủ điều kiện thực hiện được tác vụ nghiệp vụ cần thiết, không bị chặn nhầm.
2. **Deny đúng:** user/workload thiếu quyền không thể thực hiện hành động, kể cả gọi API trực tiếp.
3. **Đúng đối tượng:** chủ thể chỉ truy cập được resource thuộc owner, nhóm, tenant hoặc quan hệ được phép.
4. **Đúng thời điểm:** quyền có ngày hiệu lực, thời hạn, phê duyệt và điều kiện trạng thái chính xác.
5. **Đúng nguồn:** role và thuộc tính được lấy từ IdP/IGA/HRIS hoặc nguồn đã xác thực, không tin client input tự khai.
6. **Đúng vòng đời:** Joiner chưa đủ điều kiện không được truy cập; Mover mất quyền cũ; Leaver bị chặn.
7. **Đúng mọi đường thực thi:** HTTP API, background job, GraphQL, batch, message consumer, file download, admin console và legacy endpoints.
8. **Đúng khi lỗi:** không mở quyền khi PDP, directory, cache hoặc service dependency lỗi, timeout hay dữ liệu thiếu.
9. **Có bằng chứng:** biết rule/version, subject, target, action, kết quả, thời điểm và đường kiểm chứng mà không lộ secret.

### Điều không thể kết luận chỉ từ một phép thử

- Một request trả HTTP 403 **không chứng minh** mọi đường truy cập khác đều an toàn.
- Một lần truy cập thất bại do DNS, HTTP 404/503 hoặc dữ liệu test không tồn tại **không chứng minh** hệ thống đã ra quyết định deny theo chính sách.
- Một group đã được gỡ khỏi IdP **không chứng minh** local role, ACL, token hoặc session cũ ở SaaS đều mất tác dụng.
- Một endpoint API đúng quyền **không chứng minh** background export, bulk endpoint hoặc direct object download thực thi cùng policy.

Vì vậy phải thiết kế **coverage**, dữ liệu kiểm thử, positive control và negative tests trước khi công bố kết quả.

## 3. Mô hình quyết định quyền: Subject – Action – Resource – Context

Có thể mô tả một request:

\[
\operatorname{Decision}=f(S,A,R,C,P)
\]

Trong đó:

- **S – Subject:** user, group, service principal hoặc workload đang hành động; danh tính phải được xác minh.
- **A – Action:** read, create, update, delete, approve, export, assignRole, rotateSecret...
- **R – Resource:** hóa đơn, tài khoản, tệp, API endpoint, môi trường, tenant, project hoặc một đối tượng cụ thể.
- **C – Context:** thời gian, trạng thái nhân sự, độ mới MFA, device posture, request purpose, môi trường hoặc trạng thái workflow.
- **P – Policy:** tập luật và phiên bản chính sách được hệ thống dùng ra quyết định.

Ví dụ:

~~~yaml
subject:
  subjectId: person-4821
  employmentStatus: ACTIVE
  department: FINANCE
  roles: [FINANCE_INVOICE_READER]
action: invoice.read
resource:
  invoiceId: inv-103
  tenantId: tenant-vn
  status: APPROVED
context:
  requestTenant: tenant-vn
  trustedAuthentication: true
  policyVersion: finance-authz-v5
expectedDecision: ALLOW
~~~

Đây là **test fixture minh họa**, không phải schema được định nghĩa bởi OAuth/SCIM hoặc một sản phẩm IAM. Test phải tạo trạng thái thực theo nguồn tin cậy rồi gửi request tới PEP; **không gửi roles/employmentStatus tùy ý trong JSON request và tin backend sẽ coi đó là thật**.

### Các nguyên tắc kiểm chứng

| Nguyên tắc | Điều phải thử |
| --- | --- |
| **Least privilege** | Mỗi role chỉ được thực hiện các action tối thiểu được phê duyệt. |
| **Deny by default** | Không có rule, attribute bị thiếu hoặc resource ngoài phạm vi phải bị từ chối. |
| **Complete mediation** | Mọi đường gọi hành động nhạy cảm đều được kiểm quyền ở phía tin cậy. |
| **Separation of Duties (SoD)** | Một người không được thực hiện hai vai trò/hành động xung đột trong cùng nghiệp vụ. |
| **Tenant isolation** | Không thể đọc/ghi dữ liệu tenant khác bằng cách thay ID hoặc header. |
| **Fresh authorization** | Thay đổi role, trạng thái HR và resource phải được phản ánh theo SLA. |
| **Ownership correctness** | Quyền cấp qua owner/delegate/nhóm phải đúng đối tượng và không còn sau khi quan hệ kết thúc. |
| **Auditability** | Quyết định allow/deny ở tài nguyên quan trọng có thể giải thích và truy vết. |

## 4. Kiến trúc PEP, PDP, PAP và PIP: kiểm thử ở đâu?

~~~mermaid
flowchart LR
    USER["User / Service client"] -->|"Request + trusted auth context"| PEP["PEP: API / Gateway / Service"]
    PEP --> PDP["PDP: Policy Decision Point"]
    PAP["PAP: Policy Admin<br/>versioned rules"] --> PDP
    PIP["PIP: HRIS / IGA / IdP<br/>attributes + resource state"] --> PDP
    PDP -->|"ALLOW / DENY / obligations"| PEP
    PEP --> DATA["Protected Resource"]
    PEP --> AUD["Audit / SIEM"]
~~~

| Thành phần | Công việc | Mẫu kiểm thử |
| --- | --- | --- |
| **PEP** | Chặn/cho request vào tài nguyên theo quyết định quyền. | Bypass bằng endpoint khác, method khác, direct resource ID, background path. |
| **PDP** | Đánh giá policy với subject/action/resource/context. | Unit tests, property-based tests, SoD, missing attributes và conflict rules. |
| **PAP** | Quản lý, phiên bản hóa, phê duyệt chính sách. | Test deploy policy, rollback, quyền chỉnh sửa policy và audit. |
| **PIP** | Cung cấp thuộc tính/dữ liệu để ra quyết định. | Kiểm trusted sources, stale data, cache, tenant scope, HR/IGA event ordering. |
| **IdP / token verifier** | Xác minh danh tính hoặc workload cùng bối cảnh. | Sai issuer/audience, token expired, subject disabled, sai loại token. |

**Không chỉ unit test PDP.** Nếu backend quên gọi PDP ở một endpoint, một bộ unit test policy có thể PASS 100% nhưng người dùng vẫn vượt quyền. Cần kết hợp **unit, integration, end-to-end và reconciliation tests**.

## 5. Các mô hình authorization thường gặp

| Mô hình | Cách quyền được xác định | Loại test quan trọng |
| --- | --- | --- |
| **RBAC** | Quyền theo role và membership. | Role tối thiểu, role hierarchy, quyền bị gỡ, SoD. |
| **ABAC** | Điều kiện theo thuộc tính subject/resource/context. | Thuộc tính thiếu/sai/đã cũ, thời gian, tenant, trạng thái resource. |
| **ReBAC** | Quan hệ giữa subject và resource (owner, member, manager...). | Thêm/gỡ quan hệ, đường kế thừa, vòng lặp và quan hệ chéo tenant. |
| **ACL** | Danh sách grant/deny gắn với đối tượng. | Direct grant, group/nested grant, explicit deny và quyền chia sẻ. |
| **Policy-based / hybrid** | Kết hợp nhiều cơ chế, priority/combining rules. | Conflict allow/deny, precedence, default deny, policy version. |
| **Capability/token-scoped** | Quyền gắn với capability hoặc access token. | Audience, scope, TTL, sender constraint, token cũ sau revoke. |

Một ứng dụng thực tế có thể dùng **kết hợp**: OAuth scope cho API, RBAC cho tính năng, ABAC cho tenant/classification và ReBAC cho owner/project membership. Test phải theo **effective access**, không chỉ membership của một nhóm.

### Khi role và policy xung đột

Ví dụ một người có role **FINANCE_READER** nhưng object có classification **CONFIDENTIAL** chỉ cho Finance Manager. **Có role vẫn không được phép** nếu điều kiện phân loại chặn. Cần kiểm:

1. Tất cả điều kiện cần đều được đánh giá.
2. Quy tắc deny/allow precedence đúng như policy.
3. Thiếu attribute không bị tự thay bằng giá trị permissive.
4. Policy mới có thể được rollback/canary mà không khiến PEP bỏ kiểm quyền.

## 6. Threat model: những đường vượt quyền phải đưa vào test

| Kiểu lỗi | Ví dụ rủi ro | Cách chứng minh đã chặn |
| --- | --- | --- |
| **BOLA / IDOR** | Đổi invoiceId từ tài khoản mình sang tài khoản người khác. | API từ chối object không thuộc phạm vi subject, kể cả ID hợp lệ. |
| **Broken Function Level Authorization (BFLA)** | User thường gọi endpoint /admin/roles trực tiếp. | Backend kiểm quyền action quản trị, không chỉ menu UI. |
| **Horizontal privilege escalation** | User A xem/sửa dữ liệu của user B cùng role. | Thử 2 principal ngang cấp với tài nguyên khác owner. |
| **Vertical privilege escalation** | Role Viewer gọi hành động Approver/Admin. | Thử role thấp thực thi action cao hơn. |
| **Cross-tenant access** | Thay tenantId/path/header để lấy dữ liệu tenant khác. | PEP lấy tenant ràng buộc từ context đáng tin và kiểm resource. |
| **Mass assignment** | Client gửi thêm isAdmin/ownerId/role vào body update. | Server chỉ cập nhật field cho phép, policy chặn nâng quyền. |
| **Hidden endpoint / method bypass** | GET bị chặn nhưng HEAD/POST/GraphQL mutation lại mở. | Kiểm mọi route, method, transport và alternate code path. |
| **Stale permissions** | Role đã gỡ nhưng cache/token vẫn có quyền. | Test sau Mover/Leaver theo mốc hiệu lực và SLA. |
| **Privilege inheritance** | Nested group hoặc ACL vẫn cấp lại quyền. | Readback mọi nguồn grant và kiểm action thực tế. |
| **Confused deputy** | Service A có quyền cao bị client thấp lợi dụng gọi tài nguyên khác. | Kiểm quyền cả caller và service, audience/delegation rõ ràng. |
| **TOCTOU** | Quyền bị thu hồi giữa lúc xem thông tin và lúc commit. | Kiểm authorization tại thời điểm thay đổi có hiệu lực. |
| **Policy outage** | PDP timeout khiến API mặc định ALLOW. | Thử fault injection, đảm bảo fail-safe theo chính sách. |

**Chỉ thực hiện kiểm thử trên môi trường, tài khoản và tài nguyên được ủy quyền.** Với kiểm thử xâm nhập, dùng test tenant, dữ liệu tổng hợp và hoạt động không phá hoại; không truy xuất dữ liệu riêng của người dùng thật để chứng minh BOLA.

## 7. Xây dựng ma trận quyền từ chính sách và nghiệp vụ

Một authorization test suite tốt bắt đầu từ **permission matrix**, không chỉ từ danh sách endpoints. Mỗi dòng quy định **chủ thể, điều kiện, tài nguyên, hành động và kết quả mong đợi**.

Ví dụ hệ thống hóa đơn:

| Principal | Action | Resource | Điều kiện | Expected |
| --- | --- | --- | --- | --- |
| Finance Reader | invoice.read | Approved invoice cùng tenant | Account active. | ALLOW |
| Finance Reader | invoice.read | Invoice tenant khác | Dù biết chính xác ID. | DENY |
| Finance Reader | invoice.approve | Bất kỳ invoice nào | Không có role Approver. | DENY |
| Finance Approver | invoice.approve | Pending invoice cùng tenant | Không phải người tạo; session đủ bảo đảm. | ALLOW |
| Finance Approver | invoice.approve | Invoice do chính mình tạo | SoD self-approval. | DENY |
| Finance Approver | invoice.approve | Already approved invoice | State không hợp lệ. | DENY |
| Finance Approver | invoice.approve | Invoice tenant khác | Bất kể role. | DENY |
| Finance Admin | role.grant | User thuộc tenant quản lý | Có phê duyệt admin hợp lệ. | ALLOW theo policy |
| Finance Admin | role.grant | Chính tài khoản mình | Nếu policy cấm self-grant. | DENY |
| Suspended user | invoice.read | Invoice cùng tenant | Account bị suspended. | DENY |
| Leaver | invoice.read | Bất kỳ invoice nào | Quan hệ không còn hiệu lực. | DENY |
| Service principal sync | invoice.read | Resource trong scope workload | Đúng audience và scope. | ALLOW theo policy |
| Service principal sync | invoice.approve | Bất kỳ invoice nào | Không có nhiệm vụ phê duyệt. | DENY |

### Lập oracle: vì sao test biết ALLOW hay DENY?

**Test oracle** là nguồn xác định kết quả mong đợi. Đối với authorization, oracle phải xuất phát từ **chính sách nghiệp vụ đã phê duyệt**, không lấy trực tiếp từ code đang test. Nếu test gọi cùng hàm policy ở cả phần “expected” và hệ thống đang kiểm, cả hai có thể sai giống nhau.

Một case nên lưu:

~~~yaml
testCaseId: AUTH-INVOICE-018
policyRef: finance-authorization-v5
subjectFixture: finance-reader-tenant-a
action: invoice.read
resourceFixture: approved-invoice-tenant-b
contextFixture: active-session
expectedDecision: DENY
expectedReason: TENANT_MISMATCH
expectedSideEffects:
  - no_data_returned
  - no_write_committed
  - safe_audit_event
~~~

Mã lý do ở ví dụ có thể là **nội bộ của test/audit**; HTTP response công khai không nhất thiết phải tiết lộ policy detail. Với tài nguyên nhạy cảm, ứng dụng có thể trả **404** thay vì **403** để tránh xác nhận object tồn tại, nếu thiết kế phù hợp và nhất quán. Test cần dựa trên **decision và side effects**, không chỉ một status code cứng.

## 8. Thiết kế fixture và test principals đáng tin

Kiểm thử authorization cần ít nhất:

- **Hai user ngang quyền** thuộc cùng tenant nhưng sở hữu resource khác nhau, để thử horizontal access.
- **Hai tenant tách biệt**, mỗi tenant có resource tương tự, để thử cross-tenant isolation.
- **Các role phân cấp**: Viewer/Editor/Approver/Admin theo policy, cả vai trò trực tiếp và kế thừa.
- **Một user có xung đột SoD**, như requester đồng thời có role approver.
- **Một subject inactive/suspended/Leaver** và một subject chưa đến ngày hiệu lực Joiner.
- **Một Mover** có entitlement mới, một số quyền cũ cần thu hồi và cache/token đang sử dụng.
- **Một service principal** với scope cụ thể, không có user context.
- **Một resource trạng thái động** như DRAFT → PENDING → APPROVED → ARCHIVED.
- **Một trường hợp thiếu metadata** (tenantId, ownerId hoặc trusted attribute).

### Dữ liệu phải khớp đường thực thi thật

Tạo user test trong IdP hoặc test identity provider có cùng semantics; tạo role/group qua đường provision được hỗ trợ; lưu resource và ACL đúng cấu trúc ứng dụng. Không chỉ mock rằng request chứa header **X-Role: ADMIN** rồi gọi đó là kiểm thử authorization production.

Khi dùng mock token ở unit/integration tests, **kiểm riêng token validation production** ở bộ test khác. Mocking authentication giúp cô lập authorization, nhưng không chứng minh API chấp nhận đúng issuer, chữ ký, audience và token type ngoài đời.

### Dữ liệu âm tính (negative fixtures)

Các fixture âm tính cần bao gồm:

| Fixture | Mục đích |
| --- | --- |
| Resource của người khác cùng tenant | Horizontal BOLA. |
| Resource cùng ID pattern nhưng tenant khác | Cross-tenant isolation. |
| User có role nhưng employmentStatus=INACTIVE | Lifecycle gate. |
| User không có role nhưng token có scope rộng | Scope không thay thế quyền. |
| User có role qua nested group đã bị xóa | Privilege inheritance sau revoke. |
| Subject không có ownerId/tenantId đáng tin | Deny khi attribute thiếu. |
| Resource đang chuyển trạng thái đồng thời | TOCTOU và state-based policy. |
| Workload token không có user identity | Phân biệt machine policy và human policy. |

## 9. Kỹ thuật kiểm thử theo tầng

| Tầng | Đối tượng | Thế mạnh | Không thể chứng minh riêng lẻ |
| --- | --- | --- | --- |
| **Unit policy test** | Policy evaluator, RBAC/ABAC rules. | Bao phủ tổ hợp và edge cases nhanh. | Mọi endpoint đã thực sự gọi PEP. |
| **Component/integration test** | Controller/service + policy + database. | Kiểm endpoint, resource lookup, transaction. | Đúng toàn bộ IdP/SCIM và phân tán. |
| **API security test** | HTTP/GraphQL/gRPC endpoints. | Phát hiện bypass route, BOLA/BFLA và auth context. | Mọi đường async/background. |
| **End-to-end JML test** | HRIS/IGA → IdP/SCIM → API. | Kiểm propagation, token/session và reconciliation. | Có thể bao phủ ít case do chi phí chạy cao. |
| **Property/metamorphic test** | Invariants của policy nhiều input. | Phát hiện tổ hợp không lường trước. | Không tự thay thế oracle chính sách nghiệp vụ. |
| **Chaos/fault test** | PDP/PIP timeout, cache, event ordering. | Kiểm fail-safe và hành vi lúc lỗi. | Độ đúng của mọi rule nghiệp vụ. |
| **Penetration/security assessment** | Hệ thống như kẻ tấn công có ủy quyền. | Tìm đường vượt quyền mới, chuỗi lỗi. | Thay thế regression tests lặp lại trong CI. |

**Chiến lược nên bắt đầu từ unit+integration nhanh**, sau đó thêm E2E cho JML và một số luồng rủi ro cao. Không chỉ chạy scan endpoint tự động; authorization thường phụ thuộc **ngữ cảnh nghiệp vụ** mà scanner khó suy được.

## 10. Kiểm thử BOLA/IDOR: đúng người nhưng sai đối tượng

**Broken Object Level Authorization (BOLA)** xuất hiện khi backend tìm object theo ID từ request nhưng không xác minh subject có quyền đối với object đó.

Ví dụ API:

~~~http
GET /api/v1/invoices/inv-103 HTTP/1.1
Host: finance.example.org
Authorization: Bearer <access-token-for-user-a>
Accept: application/json
~~~

Một test BOLA có kiểm soát:

1. Tạo invoice **inv-103** thuộc tenant A, user A được quyền đọc.
2. Tạo invoice **inv-204** thuộc tenant B hoặc owner B, user A không có quyền.
3. Xác nhận positive control: user A đọc **inv-103** thành công.
4. Giữ **cùng danh tính user A**, thử đọc **inv-204** bằng ID đã biết của fixture test.
5. Xác nhận **không trả nội dung** và decision là DENY theo policy.
6. Kiểm thử cùng ý nghĩa trên update/delete/download/export/bulk endpoints.

**Trả về HTTP 404 hoặc 403** có thể đều phù hợp tùy thiết kế che giấu thông tin, miễn không tiết lộ dữ liệu/metadata ngoài quyền và không tạo side effect.

### Các biến thể cần test

- Thay ID trong path, query string, body, GraphQL variables hoặc message payload.
- Thay parent ID: /tenants/A/invoices/B-id; server phải đối chiếu parent–child thực tế.
- Đổi thứ tự collection, pagination cursor hoặc search filter để tránh lộ record tenant khác.
- Truy cập URL download/export đã tạo trước khi user bị thu hồi quyền.
- Thử resource thuộc nhóm đã rời, owner đã thay hoặc ACL đã hết hạn.

**Không dựa vào tính khó đoán của UUID** thay cho kiểm quyền; biết một object ID không phải bằng chứng được phép truy cập.

## 11. Kiểm thử BFLA: gọi đúng API nhưng sai chức năng

**Broken Function Level Authorization (BFLA)** xảy ra khi backend cho user thường gọi chức năng dành cho vai trò cao hơn.

| Chức năng | Principal phải thử deny | Điều kiện ALLOW hợp lệ |
| --- | --- | --- |
| Tạo user khác | Viewer hoặc người chỉ đọc. | Role user-admin, đúng tenant, approval nếu cần. |
| Gán role | Nhân viên thường, support thiếu scope. | Entitlement administrator đã duyệt, có SoD. |
| Export toàn bộ khách hàng | Sales Reader không có export permission. | Role export riêng, phạm vi dữ liệu hợp lệ. |
| Phê duyệt thanh toán | Người tạo yêu cầu hoặc Reader. | Approver hợp lệ, không self-approve, step-up khi cần. |
| Tạo API key service | User không quản lý workload đó. | Workload owner được phép, scope/time limit. |
| Thay cấu hình policy | Admin nghiệp vụ không có quyền security policy. | PAP admin chuyên trách, dual control khi có yêu cầu. |

### Các kênh không nên bỏ sót

Thử **GET, POST, PUT, PATCH, DELETE**, GraphQL mutation, gRPC method và job/admin endpoints theo chức năng thực tế. Ví dụ endpoint /users/{id}/role bị chặn nhưng endpoint /users/bulk-update vẫn cho chỉnh role là lỗi BFLA/mass assignment.

Hãy kiểm cả đường **direct service call** sau gateway. Một gateway có kiểm quyền route không đủ nếu downstream service tin rằng bất cứ request nào trong mạng nội bộ đều đã được kiểm. Cần trust boundary rõ cho service-to-service và delegated requests.

## 12. Kiểm thử ABAC, tenant và dữ liệu có điều kiện

ABAC sử dụng nhiều thuộc tính, nên test cần thay đổi **một điều kiện mỗi lần** rồi thử các tổ hợp ranh giới.

Ví dụ:

~~~text
ALLOW invoice.read WHEN
  subject.active == true
  AND subject.department == FINANCE
  AND subject.tenantId == resource.tenantId
  AND resource.classification <= subject.clearance
  AND resource.status IN {APPROVED, PAID}
  AND request.time BETWEEN assignment.start AND assignment.end
ELSE DENY
~~~

Pseudopolicy này chỉ minh họa. Không phải mọi chính sách ABAC dùng phép so sánh classification như vậy; nếu có phân cấp nhãn phải định nghĩa rõ thứ tự và nguồn dữ liệu.

### Border tests

| Điều kiện | Negative test | Positive control |
| --- | --- | --- |
| Tenant | Subject tenant A đọc object tenant B. | Cùng user đọc object A được phép. |
| Department | Department đổi, claim token cũ vẫn Finance. | Subject Finance hiện hành có quyền đọc theo policy. |
| Clearance | Classification vượt clearance. | Classification trong ngưỡng được phép. |
| Resource state | Invoice DRAFT chưa được phép xuất. | Invoice APPROVED được xuất bởi role hợp lệ. |
| Time window | Trước effectiveAt hoặc sau expiresAt. | Giữa hai mốc với thời gian kiểm thử được kiểm soát. |
| Device context | Device không đạt policy hoặc tín hiệu thiếu. | Device test đã xác minh đủ điều kiện. |
| MFA freshness | Xác thực đã quá cũ cho action nhạy cảm. | Phiên được step-up hợp lệ và vẫn đủ role. |
| Missing attribute | tenant/owner/clearance không có dữ liệu đáng tin. | Attribute hợp lệ từ PIP được tin cậy. |

**Deny by default** đặc biệt quan trọng khi attribute bị null, cache chưa cập nhật hoặc service PIP lỗi: không nên tự coi “không có tenantId” là “cùng tenant với tất cả”.

## 13. Kiểm thử ReBAC, ACL, nhóm lồng và quyền kế thừa

ReBAC hoặc ACL có thể cấp quyền từ một **quan hệ trực tiếp** hoặc đường quan hệ nhiều bước. Ví dụ tài liệu thuộc project, user thuộc team, team có quyền vào project; đồng thời resource có direct share cho một người.

Các tình huống cần thử:

1. User là **owner** thật được sửa tài liệu; người khác cùng tenant không có quyền.
2. User được chia sẻ **read-only** không được update/delete.
3. User bị gỡ khỏi team nhưng cache nhóm lồng còn dữ liệu cũ.
4. Direct ACL grant vẫn còn sau khi group grant bị thu hồi.
5. Explicit deny hoặc policy ưu tiên cao phải chặn một đường allow khác theo mô hình đã định.
6. Quan hệ owner được chuyển cho người khác nhưng owner cũ không còn quyền đặc biệt.
7. Shared link/capability đã hết hạn không được sử dụng lại.
8. Một node trong đồ thị quan hệ thuộc tenant khác không được tạo cầu nối trái phép.
9. Quan hệ vừa bị thu hồi không được khôi phục bởi event cũ/đồng bộ chậm.

### Effective permission phải kiểm ở tài nguyên

Giả sử nhân viên vừa Mover khỏi Sales:

~~~text
IdP group SalesReader      : REMOVED
CRM direct role Exporter   : STILL PRESENT
Drive folder ACL           : STILL PRESENT
Cached application session : STILL GRANTS READ
~~~

Nếu test chỉ hỏi IdP user còn thuộc SalesReader không, sẽ báo sai **PASS**. Cần thử các **đường grant còn hiệu lực**, truy vấn actual membership/ACL và gọi resource bằng một principal test có quyền đã thay đổi.

## 14. Kiểm thử tính đúng quyền xuyên suốt Joiner–Mover–Leaver

Các sự kiện JML là phép thử quan trọng nhất của **dynamic authorization** vì quyền có thể thay đổi khi session/token còn tồn tại.

~~~mermaid
sequenceDiagram
    participant HR as HRIS / Source
    participant IAM as IAM / IGA
    participant IDP as IdP / SSO
    participant SCIM as SCIM / Connector
    participant API as API PEP / PDP
    participant TEST as Verification
    HR->>IAM: Joiner/Mover/Leaver + effectiveAt + revision
    IAM->>IAM: Calculate desired entitlements
    IAM->>IDP: Update account/group/session policy
    IAM->>SCIM: Provision/revoke app accounts and roles
    SCIM-->>IAM: Applied state / target IDs
    TEST->>API: Positive and negative access probes
    API-->>TEST: Allow / Deny + evidence
    TEST->>IAM: Verified / Drift / Coverage gap
~~~

| Giai đoạn | Positive test | Negative test | Điều kiện đặc biệt |
| --- | --- | --- | --- |
| **Joiner** | Sau phê duyệt và ngày hiệu lực, có baseline access đúng vai trò. | Trước ngày hiệu lực hoặc chưa proofing/approval, không mở quyền nghiệp vụ. | Tách account creation khỏi activation. |
| **Mover** | Được thực hiện action của role mới sau khi thỏa điều kiện. | Không còn action/tenant/ACL của role cũ ngoài ngoại lệ. | Xử lý quyền chồng lấn, SoD, cache/session cũ. |
| **Leaver** | Chủ thể khác vẫn dùng hệ thống bình thường. | Người nghỉ không thể gọi API, dùng session hoặc grant cũ sau mốc thu hồi. | Kiểm local account, API key, token còn hạn. |
| **Rehire** | Chỉ được cấp quyền quan hệ mới sau xác minh. | Không tự khôi phục toàn bộ role/grants từ lần làm việc trước. | Account linking đúng stable subject ID. |
| **Suspension** | Admin hợp lệ vẫn vận hành hỗ trợ. | Subject suspended không tiếp tục truy cập. | Không nhầm suspension với deletion/retention. |

### Kiểm thử độ trễ thu hồi (revocation latency)

Định nghĩa:

\[
\operatorname{RevocationLatency} = t_{\mathrm{verified\_deny}} - t_{\mathrm{effective}}
\]

Trước khi test, xác định **SLA của từng loại quyền**. Hành động admin hoặc xuất dữ liệu nhạy cảm có thể cần được chặn nhanh hơn quyền xem một thông tin ít nhạy cảm. Test phải ghi **thời điểm mốc hiệu lực**, thời điểm thay đổi được áp tại IdP/SCIM/RS và thời điểm **đã kiểm chứng deny thực sự**. Không dùng timestamp “gửi yêu cầu revoke” thay cho kết quả.

### Event cũ đến sau event mới

Nếu một event Mover trước đó đến sau event Leaver, hệ thống không được tạo lại quyền đã thu hồi. Bài test cần gửi sự kiện **duplicate/out-of-order** trong môi trường thử và kiểm:

- Event ID/revision được sử dụng để chống replay và ghi đè trạng thái mới.
- Desired state được tính từ **nguồn có thẩm quyền hiện tại**.
- Connector idempotent, không tạo thêm duplicate account/grant.
- API không cho phép quyền cũ trong lúc đồng bộ/reconcile.

### Quyền tạm thời

Một ngoại lệ bàn giao có thể cho phép đọc tài nguyên cũ trong thời hạn ngắn, nhưng phải có **approval, scope, start/end, owner và audit**. Test negative **sau expiration** và kiểm callback/reconciliation nếu cơ chế tự thu hồi bị lỗi. Ngoại lệ hợp lệ không phải lý do cho phép quyền cũ sống vô thời hạn.

## 15. Kiểm thử liên kết IdP/SSO, OAuth/OIDC và SCIM

Authorization thường sử dụng danh tính và thông tin về quyền được cung cấp bởi hệ thống khác. Vì vậy cần kiểm tra **ranh giới tin cậy** giữa IdP, Authorization Server, IAM/IGA, SCIM connector và ứng dụng.

### Những kiểm tra đầu vào bắt buộc

| Đầu vào/luồng | Negative test | Kết quả đúng |
| --- | --- | --- |
| **OIDC ID token** | Gửi ID token như access token của API. | Resource Server từ chối nếu loại token/audience không phù hợp. |
| **OAuth access token** | Token có chữ ký hợp lệ nhưng audience dành cho API khác. | Từ chối; scope không khắc phục audience sai. |
| **OAuth scope** | Scope invoice.read hợp lệ nhưng user không có role hoặc sai tenant. | Business authorization từ chối. |
| **JWT role claim** | Claim từ token đã phát trước khi Mover, chứa role cũ. | PEP chặn quyền theo cơ chế cập nhật/thu hồi và SLA. |
| **OIDC/SAML SSO** | Login thành công, account SaaS lại suspended. | Ứng dụng không mở quyền trái trạng thái hiện hành. |
| **SCIM User** | SCIM active=false nhưng local session còn sống. | Không đánh dấu deprovision VERIFIED khi session tiếp tục truy cập. |
| **SCIM Group** | IdP group đã gỡ, local role vẫn còn. | Detect drift và từ chối effective access ngoài chính sách. |
| **Client-supplied claims** | Header X-Role=ADMIN hoặc body tenantId thay thế context. | Backend không tin và không cấp thêm quyền. |
| **Trust boundary** | Token từ issuer thử nghiệm được đưa vào production API. | Từ chối do issuer/trust không hợp lệ. |

**SSO chỉ chứng minh kết quả xác thực theo giao thức; nó không làm mọi API cấp quyền đồng thời.** Nếu OAuth token có scope nhưng ứng dụng có local ACL, phải kiểm cả hai. Nếu AS ngừng cấp token mới sau Leaver, token cũ có thể còn hạn; cần kiểm tại Resource Server.

### Khi test JWT access token tự chứa

Tách ba tình huống:

1. **Token hết hạn/sai issuer/sai audience:** lớp xác minh token phải từ chối, thường trước business authorization.
2. **Token hợp lệ nhưng không có entitlement:** lớp authorization từ chối request.
3. **Token từng hợp lệ và từng có entitlement, nhưng role/HR state đã đổi:** lớp kiểm quyền hiện hành hoặc cơ chế revoke/TTL phải từ chối theo SLA.

**Không coi một JWT còn chữ ký hợp lệ là chứng cứ quyền vẫn được cấp.** Đồng thời không khẳng định có thể thu hồi tức thời mọi JWT nếu kiến trúc không có điểm kiểm trạng thái quyền hoặc denylist. Test cần phản ánh đúng năng lực và thời hạn được cam kết.

### Kiểm thử SCIM không chỉ nhìn HTTP status

Một SCIM PATCH thành công có thể chỉ biểu thị thay đổi user/group đã được hệ thống đích chấp nhận theo hợp đồng API. Test phải:

- Đọc lại đúng **target user ID**, không tìm bằng email dễ đổi/tái sử dụng.
- Kiểm trạng thái **active**, group membership và direct role.
- Xem session, API key hoặc local login có đường độc lập không.
- Kiểm resource API từ chối quyền đã bị thu hồi.
- Đánh dấu **PARTIAL/UNVERIFIED** nếu không kiểm tra được target bắt buộc.

## 16. Service account và workload authorization

Một job nền hoặc service principal thường dùng **client credentials, managed identity, workload federation hoặc mTLS** thay vì đăng nhập SSO của nhân viên. Đừng giả lập tất cả workload như một “user admin” và bỏ qua kiểm quyền kỹ thuật.

| Trường hợp | Positive test | Negative test |
| --- | --- | --- |
| Invoice sync service | Đọc hóa đơn trong scope/tenant đã được cấp. | Không được phê duyệt thanh toán hoặc xem tenant ngoài phạm vi. |
| CI/CD deploy service | Deploy đúng application và environment. | Không deploy production từ danh tính chỉ dành cho staging. |
| SCIM connector | Tạo/disable user trong tenant mà connector quản lý. | Không tự cấp global admin cho chính connector hoặc tenant khác. |
| Backup service | Đọc dữ liệu cần backup theo role hạn chế. | Không dùng backup credential để thay quyền admin của người. |
| Webhook consumer | Xử lý event đã xác minh nguồn và scope. | Không thực hiện thao tác quyền cao từ payload chưa tin cậy. |

### Kiểm thử quyền gián tiếp

Khi nhân viên Mover/Leaver, cần kiểm họ còn:

- Quyền quản lý **service principal** và trust policy không.
- Quyền đọc **vault secrets, private keys và API keys** không.
- Quyền sửa **CI/CD pipeline, repository hoặc workload identity binding** không.
- Quyền impersonate workload hay sửa service account permissions không.
- Bản sao secret dài hạn từng biết có cần rotation/revocation không.

**Không mặc định xóa service account đang chạy khi owner nghỉ việc.** Test mong đợi quyền của **người quản lý cũ** mất hiệu lực, còn workload hợp lệ có owner mới vẫn hoạt động theo policy.

### Confused deputy và truyền danh tính

Service A có quyền gọi Service B không đồng nghĩa người dùng gọi A có quyền thực hiện mọi hành động B hỗ trợ. Test cần xác minh:

1. Service A kiểm authorization của **người dùng đầu vào** trước khi thực hiện tác vụ.
2. Service B kiểm danh tính và quyền của **caller/service** theo trust contract.
3. Nếu có delegated user context/token exchange, quyền có bị giới hạn đúng user, audience và scope không.
4. Caller không thể thay header tự khai để giả mạo subject khác.
5. Audit ghi nhận **cả actor và service** thực hiện hành động, tránh mất dấu đường ủy quyền.

## 17. Cache, đồng bộ phân tán và fail-safe authorization

Một hệ thống phân tán có thể cache:

- JWT claims hoặc kết quả introspection.
- Role/group lấy từ directory hoặc IdP.
- PDP decisions theo subject-resource-action.
- ACL, ReBAC graph, tenant metadata hoặc trạng thái resource.
- Session context, entitlement snapshot từ thời điểm login.

Cache giúp giảm latency nhưng tạo rủi ro **stale authorization** sau Mover, Leaver hoặc sự kiện thu hồi khẩn cấp.

### Các trường hợp phải thử

| Sự kiện | Sai lầm thường gặp | Kết quả kiểm thử yêu cầu |
| --- | --- | --- |
| User bị gỡ khỏi group. | Cache membership giữ quyền cũ. | Sau ngưỡng SLA, mọi PEP từ chối quyền cũ. |
| EmployeeStatus chuyển thành LEAVER. | API chỉ kiểm JWT còn hạn. | Quyền được chặn theo thiết kế và mốc hiệu lực. |
| Tenant ownership đổi. | Cache resource owner cũ. | Owner cũ không tiếp tục sửa tài nguyên. |
| PDP timeout. | Application dùng default ALLOW. | Theo policy fail-safe; không mở quyền nhạy cảm vô căn cứ. |
| PIP trả null/timeout. | Thiếu tenant được hiểu là wildcard. | DENY hoặc trạng thái chưa thể quyết định được bảo vệ. |
| Message revoke đến chậm. | Nhiều replica vẫn cấp quyền. | Quan sát cửa sổ propagation, không vượt SLA. |
| Event lặp/out-of-order. | Connector tạo lại grant đã bị gỡ. | Idempotency và revision ngăn hồi sinh quyền. |
| Circuit breaker mở. | Bypass authorization để ứng dụng “sống”. | Không chuyển lỗi policy thành quyền truy cập. |

### Quyết định khi dependency lỗi

Nên phân biệt **DENY** do policy đánh giá, **INDETERMINATE** do không thể đánh giá và **NOT_APPLICABLE** do không có rule phù hợp (tên trạng thái tùy policy engine). PEP cần áp **combining rule và fallback** đã phê duyệt, thông thường chặn hành động nhạy cảm khi không thể xác minh quyền.

**Không biến HTTP 503 thành 403 giả** chỉ để test qua; lỗi service và deny do policy cần có mã nội bộ/audit khác nhau để vận hành biết có sự cố.

### Kiểm thử propagation với đồng hồ đáng tin

Khi đo độ trễ, dùng timestamp được đồng bộ hóa và ghi:

~~~text
t0 = thời điểm JML policy có hiệu lực
t1 = IdP/IGA cập nhật desired state
t2 = SCIM/connector xác nhận applied
t3 = PEP/API đầu tiên trả DENY đúng lý do
t4 = mọi target bắt buộc được xác minh
~~~

Tránh dùng **t2** để tuyên bố quyền đã thực sự bị chặn nếu vẫn có PEP cache hoặc phiên riêng. Với hệ thống đa vùng, test trên các replica/zone liên quan và lặp lại trong cửa sổ được định nghĩa.

## 18. State-based authorization, workflow và race conditions

Nhiều quyết định authorization phụ thuộc trạng thái nghiệp vụ: một hóa đơn chỉ được duyệt khi **PENDING_APPROVAL**, người duyệt không phải người tạo, hạn mức chưa vượt và vẫn có role hợp lệ tại **thời điểm commit**.

~~~mermaid
flowchart LR
    D["DRAFT"] -->|submit by requester| P["PENDING_APPROVAL"]
    P -->|approve by authorized approver| A["APPROVED"]
    P -->|reject by authorized approver| R["REJECTED"]
    A -->|archive under policy| X["ARCHIVED"]
~~~

Test cần kiểm:

1. **Action × state matrix:** không thể approve DRAFT hoặc APPROVED nếu policy chỉ cho PENDING.
2. **SoD:** requester không được tự approve, kể cả khi có role Approver.
3. **Hạn mức:** approve đúng hạn mức; vượt ngưỡng cần role/quy trình khác.
4. **Time window:** assignment hết hạn đúng lúc commit thì không được dùng quyền cũ.
5. **Concurrent requests:** hai người cùng duyệt hoặc cùng sửa resource không tạo double-approval.
6. **TOCTOU:** quyền đã được kiểm trước khi read data nhưng bị thu hồi trước thao tác ghi; cần transaction/lock/re-check phù hợp.
7. **Side effect:** request bị DENY không được gửi message, cập nhật DB, gửi email hoặc thực thi downstream side effect.

### TOCTOU trong authorization

**Time-of-check to time-of-use** xảy ra khi hệ thống kiểm quyền ở thời điểm A rồi sử dụng kết quả đó ở thời điểm B, trong khi quyền hoặc resource state đã đổi. Ví dụ:

~~~text
10:00:00  API kiểm user có quyền approve = YES.
10:00:01  IAM thu hồi quyền Approver của user.
10:00:02  API ghi trạng thái APPROVED dựa trên kết quả kiểm cũ.
~~~

Kiểm thử race có thể dùng barrier/hook trong môi trường test để thu hồi quyền giữa **authorization check** và **commit**. Hướng xử lý phụ thuộc domain và mức bảo đảm: transaction isolation, optimistic locking, policy check tại commit hoặc một mô hình ủy quyền giao dịch ràng buộc với trạng thái. Không phải mọi hành động đọc đều cần transaction phức tạp, nhưng các thao tác nhạy cảm cần xác định **thời điểm kiểm soát có hiệu lực**.

## 19. Authorization trên search, bulk, export, async và URL tải xuống

Nhiều lỗi quyền không nằm ở endpoint đọc một object mà ở các chức năng tổng hợp:

| Đường truy cập | Test bắt buộc |
| --- | --- |
| **List/search** | Không trả object tenant khác dù filter, sort, pagination hoặc cursor bị đổi. |
| **Bulk read/update/delete** | Kiểm quyền cho **từng object**, không chỉ kiểm người dùng có role trên endpoint. |
| **CSV/PDF export** | Dataset và thuộc tính trong file chỉ bao gồm dữ liệu được phép. |
| **Asynchronous job** | Quyền được đánh giá phù hợp lúc enqueue và khi chạy/hoàn tất nếu trạng thái có thể thay đổi. |
| **Presigned download URL** | Link có scope, TTL và ràng buộc truy cập theo thiết kế; gỡ quyền phải xét URL đã cấp. |
| **GraphQL** | Resolver/mutation và nested field đều kiểm quyền, không chỉ top-level query. |
| **Message consumer** | Không tin tenant/role của payload chưa xác thực; kiểm caller và nghiệp vụ trước side effect. |
| **File upload / object storage** | User không ghi đè object của người khác; metadata tenant/owner do server xác định. |
| **Admin/backoffice** | UI và API quản trị có policy riêng, không mặc định bypass vì đến từ mạng nội bộ. |
| **Webhook / third-party integration** | Client identity, signature và scope liên kết đúng tài nguyên được phép. |

### Bulk request: lỗi một phần

Giả sử user gửi **100 invoice IDs**, trong đó có 2 invoice của tenant khác. Chính sách phải định nghĩa rõ **reject toàn bộ** hay **trả kết quả từng object**. Cách nào cũng được nếu có đặc tả, nhưng tuyệt đối không được xuất hai invoice trái quyền. Test xác minh cả response, dữ liệu tạo ra trong storage và side effects sau xử lý.

### Async request: quyền có thể đổi sau enqueue

Một user có quyền export lúc 09:00 nhưng bị Mover lúc 09:01; job thực thi lúc 09:05. Đừng giả định kiểm quyền ở 09:00 luôn đủ. Tổ chức phải định nghĩa **ủy quyền lúc thực thi**, thời gian cấp URL và ai được tải kết quả. Bài test phải đo đúng contract đó, nhất là tác vụ đọc/xuất dữ liệu nhạy cảm.

### Pre-signed URLs và khả năng thu hồi

Một presigned URL có thể là **bearer capability** còn hiệu lực tới hạn đã cấp, tùy backend/object storage. Nếu policy cần chặn ngay sau Leaver, phải thiết kế TTL, gateway hoặc khả năng revoke/rotate phù hợp; không tuyên bố “đã xóa role nên mọi link cũ vô hiệu” khi thực tế chưa có cơ chế.

## 20. Java: ví dụ policy evaluator có thể unit test

Ví dụ sau tập trung vào nghiệp vụ đọc hóa đơn. Dùng Java records và JUnit để minh họa test oracle độc lập. **Đây là mô hình rút gọn**, không phải service authorization đầy đủ cho production:

~~~java
import java.util.Set;

record Principal(
    String subjectId,
    String tenantId,
    boolean active,
    Set<String> roles
) {}

record Invoice(
    String id,
    String tenantId,
    String ownerId,
    boolean approved
) {}

final class InvoiceAuthorizationPolicy {
    boolean canRead(Principal subject, Invoice invoice) {
        if (subject == null || invoice == null
                || !subject.active() || subject.roles() == null) {
            return false;
        }

        return subject.roles().contains("FINANCE_INVOICE_READER")
            && subject.tenantId() != null
            && subject.tenantId().equals(invoice.tenantId())
            && invoice.approved();
    }
}
~~~

Unit tests:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Set;

class InvoiceAuthorizationPolicyTest {
    private final InvoiceAuthorizationPolicy policy =
        new InvoiceAuthorizationPolicy();

    private final Principal readerA = new Principal(
        "person-a", "tenant-a", true,
        Set.of("FINANCE_INVOICE_READER"));

    @Test
    void allowsApprovedInvoiceInSameTenant() {
        Invoice ownTenant = new Invoice(
            "inv-a", "tenant-a", "person-other", true);
        assertTrue(policy.canRead(readerA, ownTenant));
    }

    @Test
    void deniesCrossTenantEvenWhenRoleMatches() {
        Invoice otherTenant = new Invoice(
            "inv-b", "tenant-b", "person-b", true);
        assertFalse(policy.canRead(readerA, otherTenant));
    }

    @Test
    void deniesRoleWithoutPermission() {
        Principal viewer = new Principal(
            "person-a", "tenant-a", true, Set.of("PORTAL_VIEWER"));
        Invoice invoice = new Invoice(
            "inv-a", "tenant-a", "person-a", true);
        assertFalse(policy.canRead(viewer, invoice));
    }

    @Test
    void deniesInactiveSubject() {
        Principal leaver = new Principal(
            "person-a", "tenant-a", false,
            Set.of("FINANCE_INVOICE_READER"));
        Invoice invoice = new Invoice(
            "inv-a", "tenant-a", "person-a", true);
        assertFalse(policy.canRead(leaver, invoice));
    }

    @Test
    void deniesMissingTenantOrUnapprovedResource() {
        Principal missingTenant = new Principal(
            "person-a", null, true,
            Set.of("FINANCE_INVOICE_READER"));
        Invoice draft = new Invoice(
            "inv-a", "tenant-a", "person-a", false);
        assertFalse(policy.canRead(missingTenant, draft));
        assertFalse(policy.canRead(readerA, draft));
    }
}
~~~

**Đọc code đúng phạm vi:** policy trên cho phép mọi **approved invoice cùng tenant** nếu role phù hợp; nó **không yêu cầu owner trùng** vì ví dụ nghiệp vụ là Finance Reader được đọc trong tenant. Nếu yêu cầu business là “chỉ owner mới đọc”, phải bổ sung điều kiện owner và tests, không suy rằng trường ownerId xuất hiện đã được kiểm.

Một hệ thống thực còn cần:

- Đọc subject, tenant, role từ **trusted security context** đã xác minh, không nhận role/tenant tùy ý từ client.
- Kiểm chính xác **resource được tải** trong cùng transactional/security boundary.
- Kết hợp token/scope, trạng thái JML, classification, SoD, purpose và policy version.
- Phòng TOCTOU và kiểm side effects ở phương thức thao tác ghi.
- Có **API/PEP integration tests** để đảm bảo controller thực sự gọi policy, không chỉ mỗi unit test pass.

## 21. Java/Spring Security: kiểm thử endpoint và dữ liệu

Với một API dùng Spring Security, có thể kiểm response ở tầng HTTP bằng **MockMvc** và các postprocessor kiểm thử của Spring Security. Dưới đây là **đoạn minh họa cần có cấu hình ứng dụng, fixture DB và test dependencies phù hợp**, không phải lớp test có thể chạy độc lập:

~~~java
// Pseudocode gần với Spring MVC test: cần MockMvc, test fixture,
// Spring Security test dependency và endpoint ứng dụng thực tế.
@Test
void readerCannotReadInvoiceFromAnotherTenant() throws Exception {
    testFixtures.createInvoice("inv-b", "tenant-b", true);

    mockMvc.perform(get("/api/v1/invoices/{id}", "inv-b")
            .with(jwt()
                .jwt(jwt -> jwt
                    .subject("person-a")
                    .claim("tenant", "tenant-a"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_invoice.read"))))
        .andExpect(status().isForbidden());

    // Quan trọng: kiểm no data leakage và không có side effect.
    auditAssertions.assertAuthorizationDenied(
        "person-a", "invoice.read", "inv-b");
}
~~~

**Lưu ý:** Spring Security test helper **jwt()** có thể tạo authentication giả cho controller test mà **không thực hiện đầy đủ chữ ký/JWT decoder validation thực tế**. Do đó phải có một bộ test riêng với token hợp lệ/không hợp lệ, issuer/audience/signature/expiry để kiểm ranh giới OAuth. Mã trên minh họa cách tạo security context và kỳ vọng denied; với một ứng dụng che giấu resource bằng 404 cần đổi assertion theo contract.

### Vì sao phải kiểm cả side effects?

Một endpoint có thể trả 403 sau khi đã **cập nhật database**, phát event hoặc ghi file. Test chỉ so HTTP status sẽ bỏ qua lỗi nghiêm trọng. Với thao tác ghi, kiểm:

~~~text
Given: User không đủ quyền update invoice inv-b.
When : Gửi PATCH với dữ liệu thay đổi.
Then :
  - Policy decision = DENY
  - Response không tiết lộ dữ liệu nhạy cảm
  - Invoice trong database không đổi
  - Không gửi message/event cập nhật
  - Không tạo file/export hoặc thanh toán
  - Audit ghi kết quả bị từ chối, không chứa token
~~~

Đối với hệ thống có queue, test cần kiểm **trạng thái hàng đợi** và downstream side effects, không chỉ transaction của request đầu tiên.

## 22. Property-based, metamorphic và mutation testing

Authorization có nhiều tổ hợp role, attributes và resource. Viết tay mọi trường hợp có thể tốn kém; nên bổ sung các phương pháp dựa trên **invariants**.

### Invariants có ích

1. **Tenant isolation:** nếu subject tenant A không có cross-tenant permission, đổi resource sang tenant B không bao giờ tạo ALLOW.
2. **Inactive dominance:** nếu subject không còn active, thêm một role thông thường không làm một request nhạy cảm thành ALLOW.
3. **Missing attribute fails safe:** xóa một thuộc tính bắt buộc khỏi trusted context không thể chuyển DENY thành ALLOW.
4. **No unauthorized side effects:** mọi request bị DENY giữ nguyên các tài nguyên nằm ngoài quyền.
5. **Role removal:** khi loại entitlement duy nhất cấp action, effective permission phải mất trong SLA.
6. **SoD:** thêm role Approver không thể cho phép self-approve nếu chính sách cấm.
7. **Resource change:** nếu resource chuyển sang classification cao hơn ngưỡng, subject không thể tiếp tục được phép do cache cũ quá hạn.
8. **Delegation expiry:** grant có thời hạn sau expiration không tiếp tục cho phép action.

**Không mặc định quyền luôn có tính đơn điệu khi thêm role.** Chính sách SoD hoặc explicit deny có thể khiến việc thêm một role tạo ra xung đột và chuyển ALLOW thành DENY. Invariant phải được viết từ chính sách của tổ chức, không từ một giả định không đúng.

### Property-based testing

Tạo dữ liệu ngẫu nhiên có cấu trúc: nhiều tenants, owners, groups, time windows, resource states và role assignments. Kiểm các thuộc tính bất biến và lưu **seed/fixture** khi phát hiện lỗi để tái hiện.

### Metamorphic testing

Thay đổi có kiểm soát **một thuộc tính** của request vốn được phép:

- Đổi tenant từ A sang B → kỳ vọng DENY nếu không có grant chéo tenant.
- Đổi resource owner sang người khác → kỳ vọng DENY nếu policy owner-only.
- Đổi employmentStatus sang INACTIVE → DENY.
- Dời requestTime sang sau expiresAt → DENY.
- Bỏ scope bắt buộc → DENY.

### Mutation testing

Thử biến đổi **code chính sách** trong test branch, ví dụ xóa điều kiện tenant hoặc đảo toán tử kiểm active. Bộ unit/integration test phải **bắt được mutation**. Mutation testing không thay thế security review nhưng giúp tìm khoảng trống test suite chưa bao phủ.

## 23. Đo coverage và tổ chức CI/CD

Không đo coverage authorization chỉ bằng số dòng code chạy qua. Nên theo dõi ít nhất bốn trục:

\[
\text{Coverage Dimensions} =
\{\text{Principal}, \text{Action}, \text{Resource}, \text{Context}\}
\]

Với hệ thống phân tán, bổ sung **lifecycle state, channel/transport và target system**. Một bảng coverage có thể chứa:

| Phạm vi | Unit | API integration | JML/E2E | Người sở hữu |
| --- | --- | --- | --- | --- |
| Invoice read tenant isolation | PASS | PASS | PASS sau Mover | Finance team |
| Payment approval SoD | PASS | PASS | PASS sau role change | Finance + IAM |
| Admin grant/revoke role | PASS | PASS | PASS | IAM platform |
| SaaS local ACL drift | Một phần | Một phần | Chưa có readback | App owner |
| Service principal cross-env | PASS | PASS | PASS | Platform security |
| Export via asynchronous job | PASS | Đang bổ sung | BLOCKED coverage | Data platform |

**Coverage gap phải được ghi rõ**, không suy hệ thống hoàn toàn an toàn khi còn endpoint hoặc target không kiểm chứng được.

### Pipeline kiểm thử gợi ý

~~~mermaid
flowchart TD
    PR["Pull request / Policy change"] --> U["Unit tests + property checks"]
    U --> I["API integration + authz matrix"]
    I --> S["Security contract tests / token validation"]
    S --> D["Deploy staging với test identities"]
    D --> J["JML/SCIM/SSO propagation tests"]
    J --> F["Fault / cache / async tests"]
    F --> R{"Tất cả gate bắt buộc đạt?"}
    R -->|Có| A["Approve release + audit evidence"]
    R -->|Không| B["Block release / documented exception"]
~~~

Các nguyên tắc vận hành:

- Bộ test nhanh chạy **mỗi PR**; luồng E2E/JML nặng có thể chạy định kỳ và trước các thay đổi policy quan trọng.
- Test dữ liệu **cô lập**, không dùng token người dùng thật hoặc sản phẩm chứa dữ liệu khách hàng.
- Policy change có **version, reviewer và rollback plan**; các bài test tương ứng cũng được cập nhật theo yêu cầu đã phê duyệt.
- Thử cả canary/negative tests sau deploy để phát hiện PEP thiếu policy hoặc cache không đồng bộ.
- Không cho **exception test** trở thành lỗ hổng vĩnh viễn: mọi bỏ qua test cần owner, lý do, phạm vi và ngày hết hạn.

### Không làm rò rỉ dữ liệu qua test artifacts

Trace, logs, screenshots, HAR files, assertion dumps và CI artifacts có thể chứa **access token, session cookie, PII hoặc secret**. Hãy redact dữ liệu nhạy cảm, dùng tài khoản test, thiết lập retention và giới hạn người xem. Các bằng chứng cần đủ để truy vết nhưng **không biến kho test thành nơi lưu credential**.

## 24. Audit và observability của quyết định authorization

Một log tốt giúp giải thích **tại sao request được cho phép hoặc bị từ chối**, không cần lưu token và toàn bộ payload.

~~~yaml
eventType: AUTHORIZATION_DECISION
correlationId: req-2026-4821
subjectRef: test-user-a
clientRef: expense-portal
action: invoice.read
resourceRef: inv-b
resourceTenant: tenant-b
policyVersion: finance-authz-v5
decision: DENY
reasonCode: TENANT_MISMATCH
decisionSource: finance-api-pep
observedAt: "2026-11-23T03:00:00Z"
~~~

Dữ liệu này chỉ là ví dụ. Trong môi trường thực, resourceRef và tenant IDs cũng có thể mang tính nhạy cảm; log cần kiểm soát truy cập và thời hạn lưu. **Không lưu access/refresh token, authorization code, mật khẩu, API key hoặc private key**.

### Khi kết quả bất ngờ

Một request đáng lẽ DENY nhưng lại ALLOW cần lưu đủ dấu vết:

1. Subject thực tế là ai, được xác minh bởi nguồn nào?
2. Token/session thuộc client, issuer, audience và mốc thời gian nào?
3. PEP nào xử lý, policy version nào được dùng?
4. Resource thực tế thuộc tenant/owner nào ở thời điểm kiểm?
5. Có cached decision/group/ACL hoặc sự kiện IAM chưa đồng bộ không?
6. Có bypass path, admin override hay direct service call không?
7. Có side effect xảy ra trước khi từ chối không?

Những thông tin này giúp phân biệt **lỗi policy**, **lỗi enforcement**, **lỗi dữ liệu**, **sự cố propagation** và **hành vi lạm dụng**.

### Chỉ số nên theo dõi

- **Authorization test coverage:** tỷ lệ principal–action–resource–context quan trọng đã có positive/negative tests.
- **BOLA/BFLA regression incidents:** số đường vượt quyền được phát hiện theo release.
- **Cross-tenant violations:** nỗ lực hoặc lỗi trả dữ liệu sai tenant.
- **Revocation latency:** thời gian từ Mover/Leaver effectiveAt tới verified DENY ở từng PEP.
- **Decision drift:** kết quả PDP/PEP khác desired state hoặc khác giữa các vùng.
- **Unverified endpoints/targets:** số API, worker, SaaS, legacy services chưa đủ bằng chứng.
- **Policy exceptions aging:** ngoại lệ quá hạn, chưa có owner hoặc thiếu kiểm soát bù trừ.
- **False deny rate:** các tác vụ hợp lệ bị chặn sai, ảnh hưởng vận hành và khả năng sử dụng.
- **Authorization outage fail-safe compliance:** hành vi của các PEP khi PDP/PIP lỗi.

Không chạy KPI theo hướng chỉ cần **tỷ lệ DENY cao**; quyết định ALLOW hợp lệ và hoạt động nghiệp vụ là một phần của chất lượng authorization.

## 25. Tình huống thực hành: kiểm thử Mover từ Sales sang Finance

### Bối cảnh

Công ty sử dụng **IdP/SSO** tập trung, IAM/IGA quản lý role và SCIM đồng bộ tài khoản với CRM cùng ứng dụng Finance. User **An** thuộc Sales ở tenant A, trước đây được:

- Đọc và xuất khách hàng mà mình quản lý trong CRM.
- Xem tài liệu Sales chia sẻ qua group và một số direct ACL.
- Đọc secret của service account dùng cho một job tích hợp Sales.

Ngày 1/12, An chuyển sang Finance. Quyền mới gồm đọc hóa đơn Finance được phê duyệt trong tenant A; **An không được tự phê duyệt thanh toán**. Quyền Sales cũ phải thu hồi theo SLA, kể cả direct grants hoặc session/token đã phát.

### Bước 1 — Lập trạng thái mong muốn

~~~text
BEFORE MOVE:
  Sales.CRM.Customer.Read         ALLOW (theo owner/tenant)
  Sales.CRM.Customer.Export       ALLOW (theo role và scope)
  Sales.Drive.Read                ALLOW (group / ACL)
  Sales.ServiceSecret.Read        ALLOW (theo ủy quyền)
  Finance.Invoice.Read            DENY
  Finance.Payment.Approve         DENY

AFTER MOVE (khi policy có hiệu lực):
  Sales.CRM.Customer.Read         DENY
  Sales.CRM.Customer.Export       DENY
  Sales.Drive.Read                DENY (ngoại trừ handover được duyệt)
  Sales.ServiceSecret.Read        DENY
  Finance.Invoice.Read            ALLOW (đúng tenant, approved)
  Finance.Payment.Approve         DENY
~~~

Các quyền trên là giả định nghiệp vụ; test oracle phải được owner phê duyệt trước khi chạy.

### Bước 2 — Chuẩn bị fixture và baseline

Trong staging, tạo:

1. User An thuộc Sales tenant A.
2. User **Mai** thuộc Sales tenant B.
3. Khách hàng **customer-a** của An và **customer-b** của Mai.
4. Hóa đơn **invoice-a** thuộc Finance tenant A và **invoice-b** thuộc tenant B.
5. Một folder Sales được cấp bằng group và một folder cấp bằng direct ACL.
6. Service principal **sales-sync** có owner và vault access riêng.

Trước Mover, xác nhận **positive controls**: An đọc được customer-a nhưng không đọc customer-b; Mai không thể xem customer-a; An không thể duyệt hóa đơn khi chưa đủ quyền. Không sử dụng tài khoản/thông tin thật.

### Bước 3 — Kích hoạt Mover và thu thập mốc thời gian

IAM nhận sự kiện có **subject ID ổn định, revision, effectiveAt và approval**. IGA tính desired state, gỡ group Sales, thu hồi direct ACL và quyền vault, rồi cấp quyền Finance đúng phạm vi. SCIM đồng bộ SaaS. Giữ một session/token test được tạo **trước khi chuyển vai trò** để kiểm đường truy cập tồn dư.

### Bước 4 — Kiểm tra API và quyền thực tế

| Probe | Expected sau Mover | Bằng chứng |
| --- | --- | --- |
| An đọc customer-a bằng session mới. | DENY | API decision + không lộ body dữ liệu. |
| An đọc customer-a bằng token cũ trước Mover. | DENY theo SLA | Timestamp, token metadata an toàn và PEP log. |
| An gọi CRM export async. | DENY | Không tạo job, file hoặc event ngoài quyền. |
| An đọc folder Sales direct ACL. | DENY trừ ngoại lệ có hạn. | Actual ACL readback và kiểm resource. |
| An đọc secret của sales-sync. | DENY | Vault decision và quyền workload owner. |
| An đọc invoice-a APPROVED. | ALLOW | Scope/role Finance đúng tenant. |
| An đọc invoice-b tenant B. | DENY | ABAC tenant isolation. |
| An duyệt payment của chính mình. | DENY | SoD và no side effect. |
| An duyệt payment của người khác nhưng thiếu role. | DENY | Function-level authorization. |
| Mai tiếp tục đọc customer-b hợp lệ. | ALLOW | Positive control, không làm hỏng quyền user khác. |

### Bước 5 — Thử lỗi phân tán

Mô phỏng SCIM connector chậm, PDP cache chưa cập nhật và event Mover bị gửi lặp. Ghi lại thời gian đến khi từng PEP chặn quyền Sales. Nếu quyền còn được cho phép quá SLA, test **FAIL**, workflow cần alert và remediation; không đánh dấu PASS chỉ vì IdP đã gỡ nhóm.

### Bước 6 — Leaver tiếp theo

Sau một thời gian, An nghỉ việc. Kiểm tra:

- Account IdP không còn đăng nhập mới.
- Refresh token/grants bị thu hồi theo cơ chế AS.
- Access token/session cũ không còn thực hiện quyền ở Finance API theo SLA.
- Local account và ACL SaaS không còn quyền.
- Owner của service principal/secret được chuyển hoặc credential xử lý theo rủi ro.
- Mọi target bắt buộc có **readback hoặc effective-access evidence**.

**Kết luận tình huống:** kiểm thử Mover/Leaver không thể chỉ xem user còn group nào tại IdP. Phải xác minh **từng đường hành động nghiệp vụ**, dữ liệu còn có thể đọc/xuất, token/phiên và side effects.

## 26. Ma trận kiểm thử hồi quy tối thiểu

Bảng sau là khung test để tùy biến theo application và policy thực. Mỗi case cần có **test principal/resource**, expected decision, evidence và owner.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| A01 | User đúng role đọc resource hợp lệ cùng tenant. | ALLOW, đúng dữ liệu, không phát quyền dư. |
| A02 | User thiếu role đọc resource cùng tenant. | DENY, không lộ dữ liệu. |
| A03 | User có role nhưng truy cập resource tenant khác. | DENY theo tenant isolation. |
| A04 | User A đọc object của user B trong policy owner-only. | DENY BOLA. |
| A05 | User thường gọi API admin gán role. | DENY BFLA. |
| A06 | User Viewer gọi PATCH/DELETE thay vì GET. | DENY dù frontend không hiển thị hành động. |
| A07 | User gọi bulk endpoint với một ID ngoài quyền. | Không trả/cập nhật object bị cấm; xử lý phần còn lại theo contract. |
| A08 | Search/list filter/pagination hướng tới tenant khác. | Không lộ record và metadata trái quyền. |
| A09 | Export PDF/CSV gồm resource ngoài scope. | Không có hàng/cột/dữ liệu bị cấm trong artifact. |
| A10 | Resource DRAFT bị yêu cầu APPROVE. | DENY nếu workflow chỉ duyệt PENDING. |
| A11 | Requester tự phê duyệt hóa đơn mình tạo. | DENY theo SoD, không ghi side effect. |
| A12 | Role Approver đã hết hạn nhưng token còn hạn. | DENY theo thời điểm và SLA thu hồi. |
| A13 | User thiếu tenantId đáng tin trong security context. | DENY/fail-safe, không wildcard. |
| A14 | Body gửi isAdmin=true hoặc ownerId khác. | Server bỏ qua/từ chối mass assignment. |
| A15 | JWT sai audience hoặc issuer. | Token verifier từ chối request. |
| A16 | ID token OIDC được gửi thay access token. | API từ chối sai loại token. |
| A17 | Access token hợp lệ có scope nhưng thiếu business role. | DENY ở authorization layer. |
| A18 | Leaver dùng access token phát trước khi nghỉ. | Bị chặn theo SLA và cơ chế RS. |
| A19 | IdP group bị gỡ, SaaS còn direct role/ACL. | Phát hiện drift; effective access không còn trái policy. |
| A20 | Mover nhận role mới trong khi role cũ xung đột SoD. | Không có cửa sổ ALLOW hai quyền bị cấm. |
| A21 | Mover event cũ đến sau Leaver. | Không khôi phục quyền; revision/current-state bảo vệ. |
| A22 | SCIM target trả success nhưng role chưa readback. | Trạng thái chưa VERIFIED; retry/escalate. |
| A23 | PDP timeout khi truy cập dữ liệu nhạy cảm. | Không tự cho phép; phân biệt lỗi kỹ thuật và policy deny. |
| A24 | Cached role còn cũ sau revoke. | Chặn trong ngưỡng propagation/SLA đã phê duyệt. |
| A25 | Service token staging gọi API production. | DENY audience/environment/trust mismatch. |
| A26 | Workload token không có user nhưng endpoint đòi user delegation. | DENY hoặc dùng policy delegation hợp lệ, không giả user. |
| A27 | User đã mất quyền vault vẫn còn client secret cũ. | Phát hiện rủi ro credential và xác minh rotate/revoke theo policy. |
| A28 | JWT signature đúng, tài khoản hiện đã suspended. | DENY quyền nghiệp vụ dù token còn hạn. |
| A29 | GraphQL nested field hoặc mutation thiếu role. | Field/mutation không lộ hay ghi dữ liệu trái quyền. |
| A30 | Async export chạy sau khi user Leaver. | Không thực hiện/trả kết quả trái policy lúc execution/download. |
| A31 | Presigned URL cũ được dùng sau revoke. | Theo TTL/revocation contract; ghi coverage gap nếu không chặn kịp. |
| A32 | Object ACL trực tiếp còn grant dù group đã remove. | Không còn effective permission ngoài ngoại lệ. |
| A33 | Hai requests cùng approve một invoice đồng thời. | Không double-approve, kiểm trạng thái và quyền tại commit. |
| A34 | Test negative trả 503 vì service lỗi. | Không tính PASS authorization; kiểm positive control. |
| A35 | Một controller bị bỏ annotation quyền khi refactor. | API integration regression bắt bypass. |
| A36 | Exception quyền tạm đã hết hạn. | DENY sau mốc expiry, audit đúng. |
| A37 | Token có role từ header client tự khai. | Không dùng header không tin cậy làm quyết định. |
| A38 | Người dùng đúng quyền nhưng bị sai policy context. | Trả trạng thái hợp lý, log nguyên nhân và tránh false deny kéo dài. |
| A39 | Service A có admin quyền gọi Service B nhưng user caller thiếu quyền. | Không bị confused deputy; phân biệt actor và service. |
| A40 | Account mới Joiner chưa đến ngày hiệu lực. | Chưa được sử dụng quyền nghiệp vụ, kể cả đã pre-provision. |

### Cách dùng ma trận

- Ánh xạ ID test tới **requirement, policy rule, API và owner**.
- Chạy ít nhất một positive case và một negative case tương ứng cho các hành động quan trọng.
- Đảm bảo dữ liệu test **phân biệt được** quyết định sai quyền với object không tồn tại.
- Ghi **policy version, environment, client, expected/actual, thời điểm và evidence**.
- Khi một case FAIL, xác định **PEP, PDP, PIP, token, cache hay dữ liệu nghiệp vụ** gây ra khác biệt.
- Đối với JML, đo **verifiedAt** ở từng target, không chỉ trạng thái gửi request.

## 27. Những sai lầm thường gặp khi kiểm thử authorization

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ test user admin luôn thành công. | Không phát hiện quyền ngang hoặc quyền dọc bị mở. | Có principals role thấp, khác owner và khác tenant. |
| Chỉ test UI ẩn menu. | API trực tiếp vẫn gọi được. | Kiểm PEP bằng HTTP/gRPC/GraphQL và các đường async. |
| Dùng cùng policy code để tính expected. | Test sai theo code sai, tạo false confidence. | Tách oracle từ requirement/business matrix đã phê duyệt. |
| Chỉ assert HTTP 403. | Request có thể đã ghi dữ liệu trước khi trả lỗi. | Assert DB/message/file và audit side effects. |
| Dùng mock JWT cho mọi test. | Bỏ sót signature, issuer, audience hoặc token confusion. | Có bộ test JWT/introspection thực riêng. |
| Coi 404/503 là deny an toàn. | Lỗi hạ tầng bị hiểu nhầm authorization. | Positive control và policy decision evidence. |
| Chỉ kiểm IdP group membership. | Direct ACL, SaaS role, token hoặc session còn quyền. | Kiểm effective access ở tài nguyên và SP/RS. |
| Bỏ qua account máy/service account. | Workload có đặc quyền không được test. | Test service identity, client scope và delegated access. |
| Không tạo fixture nhiều tenant. | Cross-tenant BOLA khó phát hiện. | Cô lập ít nhất hai tenants với resource tương tự. |
| Không kiểm event thứ tự đảo. | Quyền Leaver có thể bị cấp lại. | Test revision/idempotency, out-of-order replay. |
| Không đo độ trễ revoke. | Mover/Leaver báo xong khi token vẫn dùng. | Test theo mốc effectiveAt và SLA. |
| Chỉ kiểm chức năng sync HTTP. | SCIM trả success nhưng quyền không cập nhật. | Readback, reconciliation và permission probe. |
| Test dùng dữ liệu/tokens thật. | Rò rỉ PII và credential, vi phạm quyền riêng tư. | Test identities, synthetic data, artifact redaction. |
| Allow khi PDP lỗi để “giữ uptime”. | Lỗi phụ thuộc mở đường truy cập nhạy cảm. | Fail-safe policy và fault tests. |
| Không có owner cho test gap. | Endpoint mới không được kiểm quyền. | Ownership matrix và release gate. |

## 28. Checklist nghiệm thu authorization test suite

Trước khi xem một bản triển khai authorization đạt yêu cầu, đối chiếu:

1. **Policy và phạm vi:** có tập requirement phiên bản hóa, action list và resource types được xác nhận không?
2. **Trust của subject:** người dùng/workload có được xác minh ở IdP hoặc auth layer đúng issuer/audience/client không?
3. **Role và attributes:** dữ liệu quyền xuất phát từ IGA/directory/PIP đáng tin hay từ client tự khai?
4. **Allow và deny:** mỗi action nhạy cảm có cả positive control và negative test không?
5. **BOLA/BFLA:** đã thử cross-owner, cross-tenant, low-to-high role, alternate HTTP methods chưa?
6. **RBAC/ABAC/ReBAC:** nested grants, direct ACL, missing attribute, SoD và resource status được test chưa?
7. **PEP coverage:** API, batch, GraphQL, background jobs, exports và admin paths đều có enforcement chưa?
8. **No side effect on DENY:** DB, queue, files và downstream actions được xác minh không thay đổi chứ?
9. **JML:** Joiner trước hiệu lực, Mover mất quyền cũ, Leaver bị chặn, rehire không tự phục hồi quyền cũ đã test chưa?
10. **Phiên/token:** access token, refresh token, SSO session và local SaaS session được xét đúng ranh giới không?
11. **SCIM và reconciliation:** readback và effective access tại các hệ thống đích có được kiểm chứng không?
12. **Service accounts:** client credentials, vault, workload delegation và quyền gián tiếp có test không?
13. **Fault handling:** PDP/PIP timeout, stale cache, out-of-order event, network partition và policy rollout được test chưa?
14. **Tính đồng thời:** action nhạy cảm được bảo vệ trước race/TOCTOU và double-commit chưa?
15. **CI/CD:** test bắt buộc tự động chạy, có owner, regression evidence và policy version không?
16. **Audit/không lộ secrets:** quyết định được ghi đủ metadata nhưng không lưu token hay PII không cần thiết chứ?
17. **Coverage gaps:** mọi endpoint/target chưa thể xác minh có owner, hạn và biện pháp bù trừ không?
18. **Đóng kết quả:** chỉ báo **VERIFIED** khi các điều kiện bắt buộc có bằng chứng độc lập, không chỉ khi connector/API trả success chứ?

**Nguyên tắc nghiệm thu:** **ALLOW đúng** phải phục vụ nghiệp vụ; **DENY đúng** phải chặn cả truy cập lẫn side effects; và **quyền đã thu hồi** phải thực sự mất hiệu lực tại điểm thực thi theo mốc thời gian đã cam kết.

## 29. Câu hỏi tự kiểm tra

**Câu 1.** Một user có token hợp lệ và scope invoice.read có được phép đọc mọi invoice không?

**Trả lời:** Không. Resource Server còn phải kiểm tra role, tenant, owner/quan hệ, trạng thái resource và chính sách hiện hành. Scope không thay thế business authorization.

**Câu 2.** Kiểm thử ẩn nút “Xóa user” cho role Viewer đã đủ chưa?

**Trả lời:** Chưa. Cần gọi backend/admin endpoint với principal Viewer trong môi trường kiểm thử và xác minh yêu cầu bị từ chối **trước** khi có side effects.

**Câu 3.** BOLA khác BFLA thế nào?

**Trả lời:** BOLA xảy ra khi chủ thể có thể truy cập **object không được phép** dù endpoint/action có thể hợp lệ. BFLA xảy ra khi user gọi được **chức năng** dành cho role cao hơn. Một ứng dụng có thể mắc cả hai.

**Câu 4.** Vì sao một HTTP 404 không chứng minh test authorization đạt?

**Trả lời:** Object có thể không tồn tại hoặc URL sai; chưa chắc policy đã từ chối. Cần fixture tồn tại, positive control và bằng chứng decision/no side effect.

**Câu 5.** User Mover đã bị gỡ nhóm Sales ở IdP. Vì sao vẫn cần gọi CRM API để kiểm?

**Trả lời:** CRM có thể còn direct role, ACL, group cache, session hoặc token đã cấp. Chỉ kiểm group IdP không chứng minh **effective access** ở CRM đã mất.

**Câu 6.** Quyết định khi PDP timeout có nên mặc định ALLOW để tránh làm gián đoạn dịch vụ?

**Trả lời:** Không nên mặc định. Cần fallback/fail-safe theo policy đã phê duyệt, thường từ chối hành động nhạy cảm nếu không thể xác minh quyền; đồng thời phân biệt outage với deny do policy.

**Câu 7.** Vì sao kiểm thử với service account khác user thường?

**Trả lời:** Workload có thể dùng Client Credentials hoặc managed identity, không có người dùng tương tác. Nó phải có client/workload policy, tenant/scope riêng và không được suy ra user role từ một token máy.

**Câu 8.** Unit test policy PASS nhưng endpoint thực tế không gọi policy, kết quả có an toàn không?

**Trả lời:** Không. Cần integration/API tests để chứng minh mọi PEP thực thi check, kể cả các alternate endpoints và background code paths.

**Câu 9.** Nếu người dùng bị thu hồi quyền trong khi một job export đang chờ xử lý, quyền cần kiểm ở đâu?

**Trả lời:** Tùy hợp đồng nghiệp vụ và rủi ro, thường cần kiểm lúc tạo job và/hoặc lúc thực thi, tạo artifact, tải kết quả. Test phải xác minh quyền không tồn tại quá thời hạn cho phép.

**Câu 10.** Có thể đánh dấu Leaver VERIFIED khi SCIM trả HTTP 204 nhưng refresh token còn dùng được không?

**Trả lời:** Không. Kết quả SCIM là một phần của quy trình. Phải kiểm credential, phiên và quyền thực tế tại AS/RS hoặc SaaS theo phạm vi và SLA.

**Câu 11.** Vì sao role mới có thể làm decision bị DENY dù user có thêm quyền?

**Trả lời:** Một số chính sách có **Separation of Duties** hoặc explicit deny. Thêm role gây xung đột không nhất thiết khiến permission tăng đơn điệu; test phải dựa vào rule đúng.

**Câu 12.** Kết quả authorization test nên ghi gì để có ích cho kiểm toán?

**Trả lời:** Test case, policy version, trusted principal reference, action/resource, environment, expected/actual, reason code, timestamp, correlation ID và trạng thái side effects. Không lưu mật khẩu, access token hay private key thật.

---

**Ghi nhớ:** **Kiểm thử authorization là chứng minh mỗi yêu cầu có đúng quyền trên đúng tài nguyên, đúng tenant và đúng thời điểm – không chỉ kiểm tra người dùng đã đăng nhập.** Chiến lược vững chắc bắt đầu từ **ma trận Subject–Action–Resource–Context**, kiểm cả **ALLOW và DENY**, test **BOLA/BFLA, RBAC/ABAC/ReBAC, session/token, workload và mọi đường API**, đồng thời đối soát trạng thái **Joiner–Mover–Leaver** tại các điểm thực thi. Chỉ khi quyền cũ thực sự bị chặn, quyền mới không vượt phê duyệt và mọi kết quả có bằng chứng an toàn, tổ chức mới kiểm soát được **quyền truy cập tồn dư**.
