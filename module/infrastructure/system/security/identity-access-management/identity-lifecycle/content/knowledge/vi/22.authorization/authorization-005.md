# Resource trong Authorization: định danh, phạm vi và quyền trên tài nguyên

> **Chương:** Authorization  
> **Bài:** Resource  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Bối cảnh:** IAM quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi đổi vai trò hoặc nghỉ việc. Bài học liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

## 1. Resource là gì trong Authorization?

Giả sử nhân viên An đăng nhập hợp lệ vào CRM và có role `support-agent`. Khi An gọi `GET /api/tickets/T-103`, việc đã đăng nhập và có role vẫn chưa đủ để quyết định cho phép. API phải xác định ticket `T-103` thuộc **tenant, chi nhánh, người sở hữu, mức phân loại dữ liệu** nào, và liệu quyền của An có áp dụng trên ticket đó hay không.

Trong **Authorization (phân quyền)**, **Resource** là **đối tượng hoặc phạm vi được bảo vệ**, trên đó một chủ thể yêu cầu thực hiện hành động. Resource có thể là hồ sơ khách hàng, tài liệu, file, hàng đợi, hóa đơn, một nhóm IAM, một cloud bucket, một chức năng quản trị hoặc một tập dữ liệu.

| Chủ thể | Hành động | Resource | Quyết định hợp lý |
|---|---|---|---|
| An, support Hà Nội | `ticket.read` | Ticket Hà Nội | Cho phép nếu thỏa các điều kiện khác |
| An, support Hà Nội | `ticket.read` | Ticket Đà Nẵng | Từ chối nếu không có quyền liên vùng |
| Bình, kế toán | `invoice.approve` | Hóa đơn do chính Bình tạo | Từ chối nếu chính sách cấm tự duyệt |
| Bot báo cáo | `report.aggregate.read` | Dataset tổng hợp được chỉ định | Cho phép đúng phạm vi workload |
| Nhân viên đã nghỉ | `document.download` | Tài liệu trước đây được chia sẻ | Từ chối khi quyền đã bị thu hồi |

**Điểm cốt lõi:** Một người có quyền thực hiện hành động `read` không tự động được đọc **mọi resource** thuộc cùng một loại.

### 1.1. Resource khác Resource Server

Trong OAuth 2.0, **Resource Server** là máy chủ bảo vệ tài nguyên và chấp nhận access token, thường là HTTP API. Còn **Resource** ở đây là đối tượng mà policy cần bảo vệ.

~~~text
Client gọi Billing API (Resource Server)
           |
           +-- Subject: employee-120
           +-- Action: invoice.read
           +-- Resource: invoice INV-1042
           +-- Context: tenant-A, thời điểm, phiên
           |
           v
   Authorization: PERMIT / DENY
~~~

Một Resource Server có thể bảo vệ hàng triệu resource instance. Token hợp lệ dành cho API chỉ là đầu vào; API vẫn phải kiểm tra chính sách ở **đối tượng cụ thể**.

## 2. Mô hình Subject–Action–Resource–Environment

Một quyết định phân quyền có thể khái quát:

~~~text
Decision = Evaluate(
    Subject,
    Action,
    Resource,
    Environment,
    Policy
)
~~~

- **Subject:** user, guest, application principal hoặc service account đã xác thực.
- **Action:** đọc, sửa, tạo, xóa, duyệt, xuất dữ liệu, chia sẻ, thay owner, gán quyền.
- **Resource:** object, tập object, chức năng hoặc phạm vi muốn truy cập.
- **Environment:** thời gian, trạng thái phiên, độ mạnh MFA, thiết bị, mức rủi ro, tình trạng tài khoản.
- **Policy:** các quy tắc và entitlement đã được quản trị, phiên bản hóa, phê duyệt.

Một số policy engine có thể phân biệt `PERMIT`, `DENY`, `NOT_APPLICABLE`, `INDETERMINATE`. Ứng dụng phải định nghĩa cách xử lý kết quả; với tài nguyên được bảo vệ, **không được suy ra cho phép khi không đánh giá được**.

### 2.1. Xác thực khác phân quyền

MFA và SSO giúp chứng minh danh tính. Một user hoàn thành MFA mạnh vẫn không được phép duyệt khoản thanh toán nếu không có quyền trên hóa đơn và không thỏa Separation of Duties (SoD). Ngược lại, một access token chứa `scope=invoice.read` chưa đủ để đọc hóa đơn của mọi tenant.

### 2.2. Một thực thể có thể vừa là subject vừa là resource

Tài khoản `employee-120` là **subject** khi truy cập CRM, nhưng là **resource** khi quản trị viên thực hiện `account.disable`. Một IAM role là resource của hành động `role.assign`. Một API key là resource của `credential.revoke`.

Không có nhãn “chỉ được làm subject” hoặc “chỉ được làm resource” cố định cho tất cả ngữ cảnh.

## 3. Những loại Resource cần bảo vệ

| Loại | Ví dụ | Quy tắc thường cần |
|---|---|---|
| Business object | Invoice, order, ticket, contract | Owner, tenant, hạn mức, trạng thái nghiệp vụ |
| File/document | PDF, thư mục, bản báo cáo | Classification, share link, ACL, kế thừa |
| API/function | Endpoint export, approve, admin | Role, scope, mức nhạy cảm của action |
| Database | Row, column, table, view | Row-level và field-level authorization |
| Cloud resource | Bucket, VM, queue, secret | Project/account, environment, cloud IAM policy |
| Identity/IAM resource | Account, group, role, authenticator | SoD, người phê duyệt, kiểm toán thao tác quản trị |
| Collaboration resource | Repository, workspace, board | Membership, quan hệ chia sẻ, role theo project |
| Workload resource | Service principal, credential, pipeline | Owner, trust binding, phạm vi và vòng đời |
| Derived resource | File export, dashboard, bản sao | Quyền dữ liệu nguồn, chính sách sử dụng/chia sẻ mới |

**Resource không nhất thiết là một bản ghi database.** Ví dụ `POST /api/reports/export` có thể tạo ra một file dẫn xuất cần được bảo vệ riêng; quyền xem dashboard không mặc định cho phép tải toàn bộ dữ liệu gốc.

### 3.1. Resource type và resource instance

`invoice` là resource type. `invoice:tenant-A:INV-1042` là resource instance.

~~~text
invoice
  ├─ tenant-A
  │    ├─ INV-1042 (owner=An, status=DRAFT)
  │    └─ INV-1043 (owner=Bình, status=APPROVED)
  └─ tenant-B
       └─ INV-1044 (owner=Chi, status=DRAFT)
~~~

Có role `invoice.viewer` thường là quyền ở mức loại chức năng; để xem `INV-1042`, phải kiểm tra thêm tenant, owner, trạng thái và những ràng buộc khác.

### 3.2. Resource dạng tập hợp

`GET /invoices` trả một tập đối tượng. Nếu user chỉ được xem hóa đơn Hà Nội, backend phải lọc đúng ở truy vấn hoặc lớp dữ liệu tin cậy. **Không trả toàn bộ dataset cho browser rồi ẩn những dòng không có quyền.**

## 4. Định danh và mô tả Resource

Mỗi tài nguyên cần đủ metadata cho authorization và audit.

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| Resource type | Loại đối tượng | `invoice` |
| Resource ID | Đối tượng cụ thể | `INV-1042` |
| Tenant/namespace | Biên dữ liệu | `tenant-A` |
| Owner/custodian | Người hoặc đơn vị chịu trách nhiệm | `finance-team-A` |
| Classification | Mức độ nhạy cảm | `confidential` |
| Parent | Container/project chứa resource | `project-budget` |
| State | Trạng thái nghiệp vụ | `DRAFT`, `LOCKED`, `ARCHIVED` |
| Attributes | Dữ liệu quyết định quyền | `region=HN`, `costCenter=F01` |
| Policy version | Quy tắc có hiệu lực | `invoice-policy-v7` |

Một ID như `1042` có thể trùng giữa tenant A và B. Khi phân quyền đa tenant, nên có khóa nội bộ hoặc namespace đủ rõ:

~~~text
resourceType = invoice
tenantId     = tenant-A
resourceId   = INV-1042
~~~

Không có định dạng chuỗi nào bắt buộc; UUID, database key hoặc cloud ARN đều có thể dùng nếu bảo đảm ánh xạ đúng đối tượng và phạm vi.

### 4.1. ID khó đoán không thay Authorization

ID dạng UUID giảm khả năng đoán, nhưng vẫn có thể lộ qua log, link chia sẻ hoặc email. Nếu user thay ID trong URL, API phải kiểm tra lại quyền trên đối tượng được trỏ tới. **Không biết ID không phải một kiểm soát truy cập đáng tin.**

### 4.2. Canonical resource

Một file có thể có nhiều URL, alias hoặc đường dẫn. Policy nên được đánh giá trên **resource thực** sau khi chuẩn hóa, thay vì kiểm tra alias A rồi thao tác lên object B. Với path, cần tránh path traversal; với cloud storage cần phân biệt đúng bucket, account, key và namespace.

## 5. Resource hierarchy và kế thừa quyền

Nhiều hệ thống tổ chức resource theo cây:

~~~mermaid
flowchart TD
    ORG[Tổ chức] --> A[Tenant A]
    ORG --> B[Tenant B]
    A --> W[Workspace Finance]
    W --> F[Folder Báo cáo]
    F --> D1[Document D-101]
    F --> D2[Document D-102]
    B --> P[Project Khách hàng]
    P --> D3[Document D-301]
~~~

Một policy có thể cho `finance-readers` quyền đọc folder và các file con, **nếu hệ thống định nghĩa cơ chế kế thừa như vậy**. Không mặc định mọi ứng dụng hỗ trợ kế thừa hoặc có thứ tự ưu tiên policy giống nhau.

Câu hỏi thiết kế:

1. Grant trên parent có áp dụng cho child không?
2. Child có được ngắt kế thừa hoặc đánh dấu restricted không?
3. Chuyển file sang folder khác có làm thay đổi quyền ngay không?
4. Có explicit deny hoặc tenant boundary nào luôn phải được bảo vệ không?
5. Ai có quyền thay parent policy?
6. Cache permission có làm chậm việc cập nhật quyền sau khi chuyển resource không?

### 5.1. Ranh giới không được vượt

Tenant isolation hoặc những ràng buộc phân loại dữ liệu bắt buộc không nên bị một grant ở folder cha vô tình vượt qua. Chuyển tài liệu từ tenant A sang B cần policy, thẩm quyền và kiểm tra dữ liệu riêng.

### 5.2. Xung đột chính sách

Một số hệ thống áp dụng deny-overrides, một số cho phép ngoại lệ được xác định rõ. Cần mô tả và kiểm thử **quy tắc kết hợp policy**. Không áp một thuật toán chung cho mọi cloud, database hoặc SaaS.

## 6. Resource và Action: chi tiết quyền quan trọng

| Resource | Action | Rủi ro |
|---|---|---|
| Customer | `customer.read` | Xem thông tin cá nhân |
| Customer | `customer.export` | Tải hàng loạt dữ liệu |
| Invoice | `invoice.create` | Tạo chứng từ |
| Invoice | `invoice.approve` | Phê duyệt giao dịch |
| Document | `document.share` | Cấp quyền cho người khác |
| Document | `document.changeOwner` | Chuyển người kiểm soát |
| IAM account | `account.disable` | Cắt quyền đăng nhập |
| IAM role | `role.assign` | Cấp năng lực kỹ thuật |
| Credential | `credential.revoke` | Chặn workload hoặc client |

Có quyền `read` không tự có `export`. Có quyền `update` không tự có `approve`. Một nhãn role như `editor` hoặc `admin` phải được ánh xạ thành **action + resource scope** cụ thể.

### 6.1. Phân quyền khi resource chưa tồn tại

Với `POST /invoices`, invoice mới chưa có ID. Hệ thống cần kiểm tra quyền `invoice.create` trên **tenant, đơn vị, parent và loại tài nguyên dự kiến**, rồi gán ID/owner/scope an toàn sau khi tạo.

Không lấy nguyên `ownerId`, `tenantId`, `classification=public` do client tự nhập làm chân lý nếu những thuộc tính đó quyết định quyền.

### 6.2. Chuyển owner và xóa dữ liệu

`changeOwner`, `delete` và `share` thường ảnh hưởng nhiều bên, cần quyền riêng và approval cho tài nguyên nhạy cảm. `createdBy` có thể phục vụ lịch sử, không phải bằng chứng người tạo được giữ quyền admin vĩnh viễn.

## 7. RBAC: quyền theo role phải gắn Resource Scope

**Role-Based Access Control (RBAC)** dùng vai trò để gom quyền. Nhưng role chỉ an toàn khi được định nghĩa cùng resource/action scope.

| Role | Actions | Resource scope |
|---|---|---|
| `crm.viewer` | `customer.read` | Tenant được cấp |
| `crm.support-agent` | `ticket.read`, `ticket.update` | Ticket theo nhóm phân công |
| `billing.creator` | `invoice.create` | Đơn vị của nhân viên |
| `billing.approver` | `invoice.approve` | Hạn mức, đơn vị được duyệt |
| `document.owner` | `document.share` | Document thuộc quyền quản lý |
| `iam.reader` | `account.read` | Phạm vi IAM được phân công |

### 7.1. Group không phải role, role không phải quyền vô hạn

Group trong IdP có thể là phương tiện gán role. Nhưng membership chỉ thực sự cấp quyền khi **mapping tới ứng dụng** được thiết kế và thực thi. Một group bị gỡ ở IdP chưa chắc loại bỏ role được cấp trực tiếp tại SaaS.

### 7.2. Separation of Duties theo object

Một người có thể vừa tạo vừa duyệt hóa đơn trong hai role khác nhau. Nếu policy cấm tự duyệt hóa đơn do mình tạo, API phải kiểm tra **invoice.createdBy**:

~~~text
if action == "invoice.approve"
   and invoice.createdBy == principal.id:
    DENY
~~~

SoD ở mức giao dịch không thể được thay thế hoàn toàn bằng một danh sách role.

## 8. ABAC: thuộc tính Resource tham gia quyết định

**Attribute-Based Access Control (ABAC)** xét thuộc tính của subject, resource, action và môi trường.

Ví dụ tài liệu:

~~~json
{
  "id": "doc-1042",
  "tenantId": "tenant-A",
  "ownerId": "employee-120",
  "department": "finance",
  "region": "HN",
  "classification": "confidential",
  "status": "ACTIVE"
}
~~~

Policy minh họa:

~~~text
ALLOW khi:
  principal.status == ACTIVE
  AND principal.tenantId == resource.tenantId
  AND principal.department == resource.department
  AND action == "document.read"
  AND resource.classification IN principal.allowedClassifications
  AND session.authStrength đáp ứng policy
~~~

Đây là logic dạy học, không phải ngôn ngữ policy dùng trực tiếp. Một hệ thống phải xác định cách xử lý thiếu thuộc tính, nguồn dữ liệu, policy conflict và quyền override.

### 8.1. Thuộc tính phải có nguồn có thẩm quyền

`department`, `region`, `tenantId` và `role` dùng cấp quyền phải đến từ HRIS/IdP/IAM hoặc kho dữ liệu được quản trị. **Không tin header hay JSON client tự khai `isAdmin=true`.**

Thuộc tính resource như owner/classification cần đọc từ database hoặc metadata service đáng tin, không lấy theo tham số được user tự chọn.

### 8.2. Thiếu metadata không được tự mở quyền

Nếu resource thiếu `tenantId` hoặc classification, không tự hiểu là `ALL` hay `PUBLIC`. Với tài nguyên nhạy cảm, cần deny hoặc đưa vào workflow xác minh theo chính sách.

### 8.3. Trạng thái resource làm thay đổi quyền

Invoice `DRAFT` có thể sửa, nhưng khi `APPROVED` cần đóng băng. Document `ARCHIVED` có thể chỉ đọc. Vì vậy trạng thái resource cần được đọc đủ mới cho những action nhạy cảm.

## 9. ACL và ReBAC: quyền theo quan hệ

**Access Control List (ACL)** gắn các grant trực tiếp với resource:

~~~text
document D-1042:
    owner: employee-120
    viewers:
      - employee-121
      - group-finance
    temporary-share:
      - partner-11 until 2026-12-01
~~~

**Relationship-Based Access Control (ReBAC)** diễn đạt quan hệ giữa subject, group, workspace, owner và resource.

~~~mermaid
flowchart LR
    U[User An] -->|member| G[Group Finance]
    G -->|viewer| W[Workspace Budget]
    W -->|contains| D[Document D-1042]
    M[Manager Bình] -->|approver| W
    P[Partner] -->|temporary-viewer| D
~~~

### 9.1. Quyền có thể đến từ nhiều đường

Một user có thể được xem tài liệu qua group, direct ACL, parent folder và share link. Thu hồi một group **không bảo đảm** mọi đường khác đã bị loại bỏ.

### 9.2. “Owner” có thể có nhiều nghĩa

- **Business owner:** chịu trách nhiệm nội dung và phân loại dữ liệu.
- **Technical owner:** chịu trách nhiệm vận hành.
- **Access owner:** được phép chia sẻ/sửa ACL.
- **Created by:** thuộc tính lịch sử.

Không mặc định cả bốn đồng nghĩa hoặc người tạo có quyền quản trị mãi mãi.

## 10. Tenant Isolation là ranh giới Resource quan trọng

Một SaaS nhiều tenant có thể có cùng ID hóa đơn `1001` ở nhiều công ty. Nếu backend chỉ kiểm tra role `billing.viewer` mà không kiểm tra tenant, user của công ty A có thể xem dữ liệu công ty B.

~~~text
Request:
   principal.tenantId = tenant-A
   principal.role = billing.viewer
   action = invoice.read

Target:
   invoiceId = 1001
   invoice.tenantId = tenant-B

Expected: DENY
~~~

Kiểm soát cần có:

1. Tenant lấy từ principal/policy đã xác minh.
2. Resource được tra cứu đúng tenant và ID.
3. API/filter/database áp dụng tenant scoping.
4. Không cho role `admin` của tenant A tự thành global admin.
5. B2B/federation không tự mở quyền từ claim của issuer khác.
6. Audit ghi tenant của principal và target khi phù hợp.

### 10.1. ID có namespace

Cùng `resourceId=1001` không đủ để định danh object trên toàn hệ thống. Correlation, policy cache và kiểm toán cần xem cả tenant/namespace.

### 10.2. Kiểm tra ở tất cả đường truy cập

Không chỉ endpoint đọc chính: bulk APIs, export, GraphQL, report service, webhooks, job nền và presigned download URL đều cần policy phù hợp với ranh giới tenant.

## 11. BOLA/IDOR và BFLA

**Broken Object Level Authorization (BOLA)** là lỗi không kiểm tra user có quyền đối với object cụ thể. **IDOR** là một cách biểu hiện khi object reference bị sử dụng mà thiếu kiểm soát.

Ví dụ:

~~~http
GET /api/customers/CUST-102 HTTP/1.1
Authorization: Bearer <access-token>
~~~

User có scope `customer.read` nhưng `CUST-102` thuộc tenant khác. Nếu API chỉ kiểm tra scope thì dữ liệu có thể bị lộ.

**Broken Function Level Authorization (BFLA)** là lỗi cho phép gọi chức năng không thuộc quyền, ví dụ user thường truy cập `POST /admin/users/disable`.

| Kiểm tra | Chức năng | Chưa đủ để bảo vệ |
|---|---|---|
| Token/signature | Xác định credential đáng tin | Quyền trên object |
| Scope/role | Có thể gọi nhóm API nào | Tenant và owner thật |
| Resource lookup | Đọc đúng object | Có được phép xem object không |
| Object-level authz | Kiểm tra quyền với instance | SoD, MFA và chính sách dữ liệu bổ sung |
| Response filtering | Chỉ trả trường dữ liệu hợp lệ | Quyền mutation/export khác |

### 11.1. List/search/export cũng có rủi ro BOLA

Backend phải chỉ truy vấn object được phép, tránh rò qua tổng số kết quả, tìm kiếm, gợi ý, sorting hoặc export. Không trả cả dataset về client để filter bằng JavaScript.

### 11.2. Share link là một đường truy cập

Một link chứa capability token có thể tiếp tục hoạt động sau khi người tạo bị khóa IdP. Hãy có owner, TTL, revoke và audit cho link; quyền truy cập bằng link phải được xem là một hình thức grant.

## 12. PEP, PDP và nguồn dữ liệu chính sách

Một kiến trúc authorization có thể phân tách:

- **PEP (Policy Enforcement Point):** chặn hoặc cho request thực hiện tại API/service/database.
- **PDP (Policy Decision Point):** tính kết quả PERMIT/DENY.
- **PIP (Policy Information Point):** cung cấp attribute tin cậy.
- **PAP (Policy Administration Point):** quản trị và phiên bản hóa policy.

~~~mermaid
flowchart TD
    C[Authenticated Client] --> PEP[API Service / PEP]
    PEP --> PDP[PDP: Evaluate policy]
    PAP[PAP: policy owner/version] --> PDP
    IAM[IAM: subject and lifecycle] --> PIP[PIP: trusted attributes]
    DB[Resource metadata: owner/tenant/classification] --> PIP
    PIP --> PDP
    PDP -->|PERMIT or DENY| PEP
    PEP -->|PERMIT| R[(Protected Resource)]
    PEP -->|DENY| ERR[Reject]
~~~

Một ứng dụng nhỏ có thể gộp các chức năng trong cùng tiến trình, không nhất thiết cần nhiều microservices. Nguyên tắc là **quyết định phải dựa trên thông tin resource tin cậy và được thực thi phía server**.

### 12.1. Gateway không thay object authorization

Gateway có thể xác minh access token và scope, nhưng thường không biết invoice thuộc tenant nào. API nghiệp vụ phải tiếp tục kiểm tra quyền object, hoặc dùng PDP có dữ liệu đầy đủ.

### 12.2. Policy engine không hoạt động

Khi PDP/nguồn thuộc tính gặp lỗi, không nên tự chuyển sang “allow all”. Với resource được bảo vệ, dùng hành vi an toàn theo policy, ghi nhận lỗi và cảnh báo. Resource công khai cần policy công khai được cấu hình trước, không phải mở quyền do sự cố.

## 13. Ví dụ API: kiểm tra Resource ở backend

Giả sử ứng dụng có `GET /v1/invoices/{invoiceId}`. API cần xác minh credential, rồi kiểm tra object thật.

~~~text
function getInvoice(request):
    principal = verifyAuthenticatedPrincipal(request)
    if principal is NONE:
        return HTTP_401

    invoice = loadInvoice(request.invoiceId)
    if invoice is NONE:
        return HTTP_404

    if principal.status != ACTIVE:
        return HTTP_403

    if principal.tenantId != invoice.tenantId:
        return DENY_WITH_NON_DISCLOSING_RESPONSE

    if not principal.hasPermission("invoice.read"):
        return HTTP_403

    if not policyAllows(principal, "invoice.read", invoice, request.context):
        return HTTP_403

    return allowedInvoiceFields(invoice, principal)
~~~

Đây là pseudocode; trong ứng dụng thực, cần xử lý race condition, caching, policy consistency và chọn cách trả 403/404 tránh làm lộ object theo chính sách.

### 13.1. Ví dụ Java/Spring Security có kiểm tra quyền

~~~java
@Service
public class InvoiceQueryService {
    private final InvoiceRepository repository;

    public InvoiceQueryService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@invoiceAuthorization.canRead(authentication, #invoiceId)")
    public InvoiceDto getInvoice(UUID invoiceId) {
        Invoice invoice = repository.findById(invoiceId)
            .orElseThrow(() -> new ResourceNotFoundException("Not found"));
        return InvoiceDto.fromAuthorizedInvoice(invoice);
    }
}
~~~

Đoạn mã là **sườn giải thích**, không phải giải pháp production hoàn chỉnh. Cần bật method security, triển khai `canRead` dựa trên principal và resource đáng tin, đồng thời tránh trường hợp object bị đổi owner/tenant **sau lúc kiểm tra nhưng trước lúc đọc** (*time-of-check to time-of-use, TOCTOU*).

### 13.2. Kiểm soát tenant ngay ở query

Một hướng là lấy dữ liệu qua repository có điều kiện tenant được xác minh:

~~~sql
SELECT id, tenant_id, owner_id, status
FROM invoices
WHERE tenant_id = :trustedTenantId
  AND region IN (:authorizedRegions)
  AND deleted = false
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

`:trustedTenantId` và `:authorizedRegions` phải đến từ identity/policy tin cậy. Query chỉ là **ví dụ về lọc phạm vi**, chưa thể thay role, classification, SoD hay các điều kiện khác.

## 14. Resource trong OAuth/OIDC và SSO

Một Resource Server có thể nhận access token:

~~~json
{
  "iss": "https://login.corp.example",
  "sub": "employee-120",
  "aud": "billing-api",
  "exp": 1795400400,
  "scope": "invoice.read"
}
~~~

API kiểm tra issuer, audience, signature/introspection, thời hạn, loại token và ràng buộc sender nếu có. Sau đó mới kiểm tra **scope, role và resource instance**.

Không nên:

- Dùng ID token OIDC thay access token API.
- Tin `scope=invoice.read` là quyền đọc mọi hóa đơn.
- Tin claim group/tenant không có hợp đồng rõ với issuer.
- Tin header `X-Role: admin` do browser gửi.
- Dùng việc ẩn nút giao diện để thay kiểm tra server.

### 14.1. Session/token mang quyền cũ

Một JWT được phát trước Mover/Leaver có thể mang role hoặc region cũ tới khi hết hạn. Với tài nguyên nhạy cảm, cần cân nhắc access token ngắn hạn, introspection, policy freshness, revocation hoặc đọc entitlement hiện tại. Không có một cơ chế phù hợp với mọi IdP/API.

### 14.2. MFA và step-up chỉ là điều kiện

API có thể yêu cầu MFA mới/đủ mạnh khi duyệt thanh toán. Nhưng MFA không tự cấp quyền `invoice.approve`, không thay hạn mức và SoD.

## 15. Resource trong Joiner Lifecycle

Khi nhân viên mới gia nhập, không chỉ cần tạo account mà còn **xác định phạm vi resource chính xác**.

Ví dụ Châu vào phòng hỗ trợ Hà Nội:

1. HRIS xác minh danh tính, phòng ban, chi nhánh và ngày bắt đầu.
2. IdP tạo danh tính, đăng ký SSO/MFA theo chính sách.
3. IAM cấp role `support-agent` đúng phạm vi ticket Hà Nội.
4. SCIM/API provisioning tạo account và đồng bộ group nếu ứng dụng hỗ trợ.
5. Chủ ứng dụng hoặc dữ liệu phê duyệt quyền nhạy cảm riêng.
6. API kiểm tra tenant/region trên mỗi ticket.
7. Audit lưu role, scope, thời điểm hiệu lực và readback.

**Joiner sai:** cấp role `support-agent` nhưng mapping tới toàn bộ customer data, không giới hạn tenant/region. Đây là lỗi cấp quyền quá rộng ngay từ đầu.

### 15.1. Đăng ký account trước ngày bắt đầu

Có thể chuẩn bị tài khoản trước ngày làm việc, nhưng quyền với resource phải tuân thủ thời điểm hiệu lực theo chính sách. Không suy rằng đã có user ở SaaS nghĩa là user được quyền đọc tất cả tài nguyên ngay.

## 16. Resource trong Mover Lifecycle

Mover làm thay đổi nhu cầu quyền trong khi danh tính có thể vẫn hoạt động.

Ví dụ An chuyển Hà Nội sang Đà Nẵng:

| Thành phần | Trước Mover | Sau Mover hợp lệ |
|---|---|---|
| Identity | `employee-120` | Giữ nguyên |
| Role | `crm.support-agent` | Có thể giữ nguyên |
| Scope | Ticket HN | Ticket DN |
| Attribute | `region=HN` | `region=DN` |
| Direct shares | Một số file HN | Rà soát, thu hồi nếu không còn căn cứ |
| Token/session | Có thể chứa claims HN | Hết hiệu lực theo chiến lược thu hồi |

**Role không đổi nhưng quyền trên Resource đã đổi.** Nếu chỉ so sánh role thì có thể bỏ sót quyền chi nhánh cũ.

### 16.1. Chuyển Resource owner

Trưởng dự án chuyển đội nhưng đang là owner của workspace. IAM cần quy trình để:

- Xác định owner nghiệp vụ/owner truy cập mới.
- Phê duyệt chuyển quyền.
- Kiểm tra phân loại dữ liệu và ranh giới tenant.
- Đánh giá direct grants/share links hiện có.
- Không sửa `createdBy` làm sai lịch sử.
- Ghi audit và xác minh quyền của owner cũ đã thu hồi nếu cần.

### 16.2. Quyền bàn giao có thời hạn

Có thể cho phép quyền chồng lấn ngắn để bàn giao, nhưng cần **mục đích, owner, phạm vi, approval, TTL và kiểm chứng thu hồi**. Không giữ vĩnh viễn quyền cũ vì “đề phòng sau này cần”.

## 17. Resource trong Leaver và Deprovisioning

Một nhân viên nghỉ việc có thể là owner tài liệu, thành viên workspace, người nhận direct share hoặc người quản lý API credential. Disable account tại IdP chưa chắc gỡ toàn bộ những đường truy cập đó.

Quy trình Leaver nên:

1. Nhận sự kiện nghỉ việc với identity ID và thời điểm có thẩm quyền.
2. Chặn đăng nhập mới tại IdP/SSO.
3. SCIM/API vô hiệu hóa account đích và thu hồi group/role.
4. Thu hồi direct ACL, cloud grants, share links, API keys có liên quan.
5. Đánh giá session, refresh token, access token và login cục bộ.
6. Chuyển giao ownership của resource còn phục vụ nghiệp vụ.
7. Đối soát effective permissions trên các hệ thống đích.
8. Ghi `VERIFIED`, `PARTIAL`, `ESCALATED` theo bằng chứng.

### 17.1. Leaver của Subject không phải xóa Resource

Hóa đơn, ticket và tài liệu do nhân viên tạo có thể cần giữ vì nghiệp vụ hoặc kiểm toán. Thu hồi quyền cá nhân và bàn giao owner thường phù hợp hơn xóa mọi object.

### 17.2. Deprovisioning thất bại

Một connector trả HTTP 200 nhưng role local hoặc share link vẫn còn có thể khiến resource truy cập được. **Lệnh được nhận không đủ để kết luận quyền đã hết.** Cần readback và kiểm tra đường truy cập theo mức rủi ro.

## 18. Service Account, Workload Identity và Resource

Service principal cũng là subject khi truy cập resource. Ví dụ job `svc-invoice-export-prod` đọc dataset tổng hợp rồi ghi báo cáo lên bucket.

| Phần | Ví dụ | Điều kiện |
|---|---|---|
| Principal | `svc-invoice-export-prod` | Có owner kỹ thuật/nghiệp vụ |
| Action | `report.aggregate.read` | Không cấp quyền duyệt hóa đơn |
| Source resource | Dataset tenant A | Không tự cấp đọc PII gốc |
| Destination resource | Prefix `reports/tenant-A/` | Không ghi toàn bucket |
| Credential | Workload federation hoặc client credential | Trust, rotation, TTL phù hợp |
| Environment | Production | Tách staging nếu ranh giới cần |
| Audit | Service ID, action, resource | Không log secret/token thô |

### 18.1. Không dùng tài khoản cá nhân chạy job

Workload phải có machine authentication, owner và permission độc lập. Khi chủ kỹ thuật nghỉ việc, thu hồi quyền cá nhân của họ và **bàn giao workload còn hợp lệ**, không xóa tự động một principal mà hệ thống khác đang phụ thuộc.

### 18.2. JML cho resource grants của workload

- **Joiner:** tạo service principal, trust, audience, scope tối thiểu.
- **Mover:** đổi API, tenant, môi trường, owner; thu hồi grant cũ.
- **Leaver:** thu hồi credential, role, trust binding và effective access.

## 19. Quyền tồn dư trên Resource và Reconciliation

Phân biệt:

- **Desired access:** quyền được phép theo policy, owner và trạng thái JML hiện tại.
- **Observed grants:** membership, role và ACL đang tồn tại ở target.
- **Effective access:** hành động resource thực sự chấp nhận sau khi tính inheritance, deny, session và điều kiện.

~~~text
Grants cần cấp   = Quyền kỳ vọng chưa được cấp đúng
Grants cần thu   = Các đường cấp quyền không còn căn cứ
Hoàn thành        = Effective access phù hợp với policy hiện hành
~~~

Phép trừ giữa các tập role đơn giản có thể không đúng nếu group lồng, direct grant, wildcard và deny policies cùng tồn tại.

| Nguồn quyền tồn dư | Vì sao không biến mất khi gỡ một role? |
|---|---|
| Nested group | Group khác vẫn cấp role |
| Direct ACL | Quyền riêng trên resource |
| Local SaaS role | Không thuộc connector SCIM |
| Cloud policy | Thừa hưởng từ project/resource policy |
| Database GRANT | Grant độc lập với IdP |
| Session/JWT | Claim đã phát hành còn được chấp nhận |
| Share link | Capability token không phụ thuộc membership |
| Service account | Credential riêng, owner cũ chưa xử lý |

### 19.1. Trạng thái chưa hoàn tất phải minh bạch

Nếu một target chưa xác minh thu hồi, workflow giữ `PENDING_VERIFICATION` hoặc `PARTIAL`, owner và hạn xử lý rõ ràng. Không biến tỷ lệ 9/10 hệ thống thành “Leaver đã hoàn tất” khi hệ thống còn lại có quyền production.

## 20. Audit Resource Authorization

Audit cần trả lời **“Ai đã làm hoặc cố làm gì trên tài nguyên nào, vì sao được cho phép hoặc bị từ chối?”**

Thông tin thường cần:

- Principal ID tin cậy, loại user/workload, trạng thái JML.
- Resource type, ID/namespace, tenant và classification.
- Action, thời điểm, kênh truy cập.
- Role/grant/quan hệ/thuộc tính quyết định, policy version.
- Kết quả `PERMIT`, `DENY`, `STEP_UP` hoặc lỗi đánh giá.
- Correlation ID liên kết request, IAM event và ticket.
- Kết quả revoke, target readback và ngoại lệ nếu có.

~~~json
{
  "eventId": "resource-authz-2026-005",
  "principalType": "USER",
  "principalRef": "employee-120",
  "action": "invoice.read",
  "resource": {
    "type": "invoice",
    "id": "INV-1042",
    "tenant": "tenant-B"
  },
  "policyVersion": "billing-resource-v7",
  "decision": "DENY",
  "reasonCode": "TENANT_SCOPE_MISMATCH",
  "lifecycleState": "ACTIVE",
  "observedAt": "2026-11-23T09:10:00+07:00",
  "correlationId": "IAM-AUTHZ-1842"
}
~~~

Đây là schema minh họa. Không lưu access token, password, private key, nội dung tài liệu hoặc PII không cần thiết vào log.

### 20.1. Chỉ số vận hành

| Chỉ số | Mục đích |
|---|---|
| Số request bị chặn sai tenant | Phát hiện truy cập vượt phạm vi hoặc cấu hình sai |
| Tỷ lệ endpoint kiểm tra object-level | Đo độ phủ authorization |
| Số direct grants/share links không owner/TTL | Tìm quyền tồn dư |
| Thời gian thu hồi grants sau Mover/Leaver | Đánh giá rủi ro còn mở |
| Tỷ lệ resource đủ owner/classification | Chất lượng thuộc tính policy |
| Số vụ `PARTIAL` quá hạn | Theo dõi lỗi connector/đối soát |
| Tỷ lệ audit có policy version | Truy xuất lý do quyết định |
| Số workload grants thiếu owner | Quản lý định danh phi con người |

## 21. Case Study: tài liệu tài chính chuyển Owner khi người dùng Mover

### 21.1. Trước khi thay đổi

Document `DOC-778` thuộc tenant A, classification `confidential`, owner quản lý quyền là Hòa. Hòa chuyển sang đội khác rồi nghỉ việc.

~~~json
{
  "id": "DOC-778",
  "tenantId": "tenant-A",
  "classification": "confidential",
  "businessOwner": "finance-team-A",
  "accessOwner": "employee-hoa",
  "readerGroup": "group-finance-A",
  "directShares": ["employee-hoang"]
}
~~~

### 21.2. Thực hiện trong Mover

1. HRIS ghi nhận Hòa đổi đội và thời điểm hiệu lực.
2. IAM tính lại quyền kỳ vọng; những grants từ nhóm cũ bị rà soát.
3. Chủ dữ liệu phê duyệt chuyển `accessOwner` cho Minh.
4. API kiểm tra action `document.changeOwner` trên `DOC-778`.
5. Tài liệu vẫn thuộc tenant A; metadata `createdBy` không bị ghi đè.
6. Direct shares/share links được rà soát, quyền Hòa cũ được thu hồi theo policy.
7. Hệ thống đọc lại effective access để xác minh.

### 21.3. Thực hiện trong Leaver

1. IdP chặn xác thực mới của Hòa.
2. Provisioning gỡ group/role và vô hiệu hóa account ở ứng dụng.
3. Xử lý ACL, token/session và đường truy cập còn lại.
4. Minh tiếp tục quản lý `DOC-778`; dữ liệu và audit được giữ theo chính sách.
5. Workflow đánh dấu VERIFIED khi có bằng chứng, hoặc PARTIAL nếu chưa thu hồi hết.

**Bài học:** Thay đổi vòng đời **subject** có thể buộc thay **resource grants/owner**, nhưng không đồng nghĩa phải xóa resource.

## 22. Ma trận kiểm thử Resource Authorization

| Thử nghiệm | Kết quả kỳ vọng |
|---|---|
| Không xác thực mà đọc resource nội bộ | Từ chối |
| Token hợp lệ nhưng thiếu role | Từ chối |
| Có role nhưng object thuộc tenant khác | Từ chối |
| User đổi object ID trong URL | Kiểm tra lại quyền với object mới |
| Có quyền read nhưng thử export | Từ chối nếu thiếu export |
| Search/list gồm object không thuộc quyền | Không rò dữ liệu, count sai hoặc gợi ý |
| Bulk update chứa object không đủ quyền | Kiểm tra từng object và chính sách transaction |
| User thiếu quyền nhưng đổi owner | Từ chối |
| Parent folder có quyền nhưng file restricted | Tôn trọng policy file |
| Share link hết hạn hoặc revoke | Không truy cập |
| Group bị gỡ nhưng direct ACL còn | Phát hiện quyền tồn dư |
| Mover đổi HN sang DN | Chặn dữ liệu HN sau hạn thu hồi |
| Leaver còn session cũ | Chặn theo policy và khả năng revocation |
| Service principal truy cập nhầm tenant | Từ chối |
| Gateway chặn nhưng backend có đường gọi trực tiếp | Backend không tin header tự giả |
| Policy engine lỗi | Không fail-open tùy tiện |
| Resource thiếu metadata bắt buộc | Không tự cấp quyền rộng |
| Tài liệu đúng tenant, đúng role, đúng scope | Cho phép đúng action và field |
| Tự tạo rồi tự duyệt, SoD cấm | Từ chối |
| Export sinh file download | File và link mới cũng có authorization |
| Resource đổi owner giữa check và use | Tránh TOCTOU, không cho quyền cũ vượt qua |

**Thực hành kiểm thử:** Kết hợp positive tests, negative tests, boundary tests với dữ liệu được phép dùng. Không chỉ nhìn giao diện, cần kiểm tra API trực tiếp, export, search, worker nền và thời điểm Mover/Leaver.

## 23. Những hiểu lầm thường gặp

**“Resource chính là URL.”** URL là một cách định vị; resource là object/đối tượng được bảo vệ, có thể có nhiều alias.

**“Role viewer nghĩa là đọc mọi instance.”** Không; còn owner/tenant/classification và các điều kiện khác.

**“UUID không đoán được nên không cần kiểm tra quyền.”** Sai; ID có thể lộ và không thay authorization.

**“SSO/MFA thành công thì không cần object authorization.”** Sai; authentication khác authorization.

**“Tác giả luôn là owner.”** Không mặc định; createdBy phục vụ audit, owner có thể chuyển hợp lệ.

**“Group SCIM bị gỡ thì tất cả file đều hết quyền.”** Không nếu còn direct ACL, role local hoặc share link.

**“Gateway đã kiểm tra token nên backend không cần phân quyền.”** Gateway có thể thiếu metadata resource; service phải kiểm soát object-level.

**“Leaver nghĩa là xóa mọi tài liệu nhân viên từng tạo.”** Không; phải thu hồi quyền và bàn giao/lưu dữ liệu đúng chính sách.

**“Service principal không có Mover/Leaver.”** Sai; workload thay API/môi trường/owner cũng đổi quyền resource.

## 24. Checklist thiết kế Resource Authorization

1. **Inventory:** Resource type, ID, tenant, owner, classification rõ ràng?
2. **Namespace:** Không nhầm resource giữa tenant/environment/project?
3. **Action:** Read, update, export, approve, share, admin được tách?
4. **Principal:** User, guest hay workload và nguồn xác thực tin cậy?
5. **Policy:** Có owner, version, approval và cách giải quyết xung đột?
6. **RBAC:** Role đi với resource scope và quyền tối thiểu?
7. **ABAC:** Thuộc tính subject/resource có nguồn và độ mới hợp lệ?
8. **ACL/ReBAC:** Direct grants và quyền kế thừa được tính?
9. **Tenant isolation:** Query/API kiểm tra tenant thực của object?
10. **BOLA:** Mỗi object instance đều được authorization?
11. **BFLA:** Endpoint admin/export/bulk có quyền riêng?
12. **List/search/export:** Không trả tài nguyên không thuộc quyền?
13. **Derived resources:** Download link, report và file export cũng được bảo vệ?
14. **PEP/PDP:** Không có đường bypass server-side enforcement?
15. **OAuth/OIDC:** Access token được xác minh nhưng không thay resource policy?
16. **Joiner:** Quyền mới đúng scope và thời điểm hiệu lực?
17. **Mover:** Scope, owner, group/direct shares cũ được rà soát và gỡ?
18. **Leaver:** Account, ACL, session/token, link và credential được xử lý?
19. **Workload:** Service account có owner, scopes, trust và lifecycle riêng?
20. **Cache:** Quyền cũ không sống quá thời hạn rủi ro?
21. **Readback:** Effective access tại target đã được xác minh?
22. **Audit:** Có principal/action/resource/policy/decision mà không lộ bí mật?
23. **Negative tests:** Sai tenant, sai role, đổi ID, hết hạn, bulk và download bị chặn?
24. **Ngoại lệ:** Quyền tạm có người duyệt, TTL và xác minh thu hồi?

---

**Ghi nhớ:** **Resource là đối tượng hoặc phạm vi được bảo vệ trong Authorization**, không phải bản thân token hay một bước xác thực. Quyết định an toàn kết hợp **Subject + Action + Resource + Environment + Policy**, và phải kiểm tra ở **object thực**, tenant, owner, classification và trạng thái. RBAC nhóm quyền theo vai trò; ABAC xét thuộc tính; ACL/ReBAC diễn đạt quan hệ. Trong vòng đời **Joiner–Mover–Leaver**, IdP/SSO, SCIM và hệ thống đích phải phối hợp cập nhật quyền; chỉ **đối soát quyền hiệu lực ở resource** mới chứng minh đã cấp đúng và thu hồi được **quyền truy cập tồn dư**.
