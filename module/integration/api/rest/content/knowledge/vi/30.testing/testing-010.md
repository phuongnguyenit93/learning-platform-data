# Kiểm thử quyền theo đối tượng, tenant, trường và chức năng

Một API có thể xác thực JWT thành công, kiểm tra vai trò `USER` hoặc `ADMIN`, chạy đúng logic nghiệp vụ, nhưng vẫn để người dùng đọc hoặc sửa dữ liệu của người khác. Ví dụ: Alice đăng nhập hợp lệ rồi đổi `projectId` trong URL thành ID dự án của Bob; một tenant admin truy cập báo cáo của tenant khác; một người dùng bình thường đưa `"role":"ADMIN"` vào JSON để tự nâng quyền; hoặc gọi trực tiếp endpoint dành cho quản trị viên dù nút chức năng đã bị ẩn trên giao diện.

Trong chương **Kiểm thử** của module **INTEGRATION_API_REST**, bài này tập trung vào cách kiểm thử **authorization** ở bốn cấp: **đối tượng (object)**, **tenant**, **trường dữ liệu (property/field)** và **chức năng (function)**. Người học xây dựng ma trận quyền, kiểm tra hợp đồng HTTP và viết kiểm thử tự động với Java, Spring Security, MockMvc và database.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt xác thực (authentication) và phân quyền (authorization), nhận diện BOLA/IDOR, quyền theo tenant, BOPLA và BFLA.
2. Thiết kế ma trận `subject × tenant × resource × action × property` với cả ca được phép và ca bị từ chối.
3. Kiểm thử object ownership, ACL, membership, vai trò theo tenant, các đường dẫn lồng nhau, batch/list và quyền đọc/ghi từng trường.
4. Xác minh HTTP `401`, `403`, `404`, `200/204`, body, các hiệu ứng lưu trữ và side effect; không chỉ kiểm tra status.
5. Dùng Spring Security Test để mô phỏng danh tính tại tầng web và tổ chức bài kiểm thử tích hợp để chứng minh quyền thực sự được thực thi.
6. Nhận ra những điểm mù do fake JWT, mock service, cache, kiểm tra quyền không nguyên tử và thay đổi membership trong lúc request đang chạy.

## 2. Bốn trục phân quyền thường bị bỏ sót

| Trục | Câu hỏi phải trả lời ở backend | Lỗ hổng thường gặp | Ví dụ kiểm thử âm tính |
|---|---|---|---|
| **Đối tượng** | Người dùng này có được thao tác trên **bản ghi cụ thể** không? | BOLA (Broken Object Level Authorization), IDOR | Alice đoán ID project riêng của Chloe trong cùng tenant |
| **Tenant** | Dữ liệu và quyền có bị giới hạn vào **tenant đang truy cập** không? | Cross-tenant data access / tenant escape | Admin tenant B đổi URL sang tenant A |
| **Trường** | Ai được **đọc** hoặc **ghi** từng thuộc tính của object? | BOPLA (Broken Object Property Level Authorization), mass assignment | Gửi `ownerId`, `tenantId` hoặc `billingAccountNumber` trong PATCH |
| **Chức năng** | Chủ thể này có được **thực hiện hành động/endpoint** không? | BFLA (Broken Function Level Authorization) | Viewer gọi `POST /reports/export` hoặc `DELETE /projects/{id}` |

Tên gọi trong OWASP API Security Top 10 (2023) thường được đối chiếu là API1:2023 **Broken Object Level Authorization**, API3:2023 **Broken Object Property Level Authorization** và API5:2023 **Broken Function Level Authorization**. Các nhóm lỗi liên quan nhau nhưng không đồng nhất: có quyền xem một project **không** mặc nhiên có quyền sửa project; có quyền sửa project **không** mặc nhiên có quyền sửa `ownerId`; admin tenant A **không** mặc nhiên là admin tenant B.

Một quyết định cho phép nên xét đủ ngữ cảnh:

```text
allow(subject, action, resource, tenant, property, context)
  = authenticated(subject)
    AND validTenantMembership(subject, tenant)
    AND resource.tenantId == tenant
    AND canAccessObject(subject, resource)
    AND canPerformFunction(subject, action, tenant)
    AND canAccessProperty(subject, action, property, resource)
    AND businessPreconditionsSatisfied
```

Công thức chỉ là mô hình tư duy, không phải lời khuyên triển khai mọi predicate bằng một biểu thức khổng lồ. Trong ứng dụng thực tế, quyền được phân tán hợp lý giữa filter/controller, service policy và câu lệnh truy vấn/cập nhật database; cần kiểm thử xuyên qua các lớp đó.

**Định danh không phải quyền:** ID ngẫu nhiên dạng UUID giúp khó đoán hơn nhưng không thay cho authorization. JWT đã ký, vai trò `USER`, URL chứa `tenantId` hay sở hữu token hợp lệ đều không tự chứng minh quyền trên từng resource.

## 3. Xây dựng fixture nhất quán trước khi kiểm thử

Xét hệ thống quản lý dự án đa tenant với các endpoint:

```http
GET    /api/tenants/{tenantId}/projects
GET    /api/tenants/{tenantId}/projects/{projectId}
PATCH  /api/tenants/{tenantId}/projects/{projectId}
GET    /api/tenants/{tenantId}/projects/{projectId}/billing
POST   /api/tenants/{tenantId}/reports/export
DELETE /api/tenants/{tenantId}/projects/{projectId}
```

**Dữ liệu mẫu cố định:**

| Nhãn | Tenant | Chủ thể | Vai trò trong tenant | Liên hệ với dự án |
|---|---|---|---|---|
| Alice | A | `alice` | `EDITOR` | Chủ dự án P1 |
| Bob | A | `bob` | `VIEWER` | Được chia sẻ quyền **đọc** P1 |
| Chloe | A | `chloe` | `EDITOR` | Chủ P2; không được chia sẻ P1 |
| Admin A | A | `admin-a` | `TENANT_ADMIN` | Quản lý các dự án của A |
| Dave | B | `dave` | `TENANT_ADMIN` | Chủ P3 thuộc B; không là thành viên A |
| Mallory | Không có | `mallory` | Không có membership | Không được truy cập A/B |

Các resource:

- **P1:** `tenantId=A`, `owner=alice`, tên `"Portal"`, mô tả thông thường và thuộc tính nhạy cảm `billingAccountNumber`.
- **P2:** `tenantId=A`, `owner=chloe`, tên `"Analytics"`.
- **P3:** `tenantId=B`, `owner=dave`, tên `"Inventory"`.

Hợp đồng quyền của ví dụ:

- `GET project`: chủ sở hữu, người được chia sẻ quyền đọc, hoặc `TENANT_ADMIN` **cùng tenant** được đọc dữ liệu công khai.
- `PATCH project`: chủ sở hữu có vai trò `EDITOR`, hoặc `TENANT_ADMIN` cùng tenant, mới được thay đổi `name`/`description`.
- `GET project/billing`: chỉ `TENANT_ADMIN` cùng tenant với scope phù hợp được đọc thông tin thanh toán đã giới hạn/mask.
- `POST reports/export` và `DELETE project`: chỉ `TENANT_ADMIN` cùng tenant, có quyền chức năng tương ứng.
- Không endpoint cập nhật thông thường nào cho phép client tự sửa `tenantId`, `ownerId`, `status`, `billingAccountNumber` hay quyền thành viên.
- Với resource ngoài phạm vi nhìn thấy, API thống nhất trả `404` để tránh tiết lộ sự tồn tại. Nếu user đã nhìn thấy object nhưng không được thực hiện một hành động, API có thể trả `403`. Đây là **chính sách hợp đồng của ví dụ**; các API khác có thể chọn `403` nhất quán, miễn là không làm rò rỉ dữ liệu và có test tương ứng.

Fixture cần phân biệt ít nhất hai tình huống: **khác tenant** và **cùng tenant nhưng không được cấp quyền object**. Nếu chỉ tạo hai user thuộc hai tenant, bạn sẽ không tìm ra lỗi kiểm tra membership nhưng bỏ sót ACL/ownership.

## 4. Thiết kế ma trận kiểm thử quyền

Ma trận tối thiểu cho P1:

| Chủ thể | GET P1 | PATCH P1 (name) | GET P1/billing | Export tenant A |
|---|---|---|---|---|
| Alice (A/EDITOR, owner) | Cho phép | Cho phép | Từ chối | Từ chối |
| Bob (A/VIEWER, read ACL) | Cho phép | Từ chối | Từ chối | Từ chối |
| Chloe (A/EDITOR, không ACL) | Từ chối | Từ chối | Từ chối | Từ chối |
| Admin A (A/TENANT_ADMIN) | Cho phép | Cho phép | Cho phép | Cho phép |
| Dave (B/TENANT_ADMIN) | Từ chối | Từ chối | Từ chối | Từ chối |
| Mallory (không membership) | Từ chối | Từ chối | Từ chối | Từ chối |
| Không có access token | `401` | `401` | `401` | `401` |

**Mỗi cặp "chủ thể + hành động" còn phải chạy trên nhiều ID:** P1 thuộc A, P2 thuộc A và P3 thuộc B. Với các quyền ghi, kiểm tra cả **trạng thái database trước/sau**. Với endpoint tạo sự kiện, xuất báo cáo hoặc gửi email, kiểm tra cả việc **không phát sinh side effect** khi bị chặn.

Nên lưu ma trận dưới dạng nguồn dữ liệu cho parameterized tests. Đừng cố đưa mọi quy tắc vào một hàm test khổng lồ: nhóm bài kiểm thử theo trục object, tenant, property và function để khi một ca thất bại có thể nhận ra loại lỗ hổng.

### 4.1. Những ca thử cần có cho mỗi resource

1. **Positive case:** người có đủ quyền gọi thành công và nhận đúng các trường được phép.
2. **Same-tenant foreign object:** chủ thể có cùng membership nhưng không là owner, không có ACL.
3. **Cross-tenant object:** chủ thể có quyền cao trong B nhưng truy cập ID resource A.
4. **Path spoofing:** `tenantId` trên URL khác `tenant_id` thật của object, kể cả user là thành viên của cả A và B.
5. **Method variation:** thử `GET`, `PATCH`, `PUT`, `DELETE`, `POST`, kể cả endpoint bulk/nested khi route hỗ trợ.
6. **Mutation denied:** DB, audit/queue, email, payment, webhook đều không bị thay đổi khi authorization từ chối.
7. **Post-change policy:** sau khi thu hồi membership/ACL hoặc chuyển owner, request mới áp dụng chính sách mới theo yêu cầu độ trễ của hệ thống.

Cũng cần kiểm tra `HEAD` nếu framework tự sinh từ `GET` và `OPTIONS` nếu có metadata nhạy cảm hoặc route tùy biến. HTTP `405 Method Not Allowed` cho phương thức không hỗ trợ **không chứng minh** rằng phương thức có hỗ trợ đã được bảo vệ.

## 5. Kiểm thử quyền theo đối tượng: BOLA/IDOR

### 5.1. Mẫu lỗi thường gặp

Controller chỉ kiểm tra đăng nhập:

```java
@GetMapping("/api/tenants/{tenantId}/projects/{projectId}")
public ProjectResponse get(@PathVariable UUID tenantId,
                           @PathVariable UUID projectId) {
    return mapper.toResponse(
            projectRepository.findById(projectId).orElseThrow());
}
```

Ở đây `tenantId` được nhận nhưng **không dùng để giới hạn truy vấn**, và không có kiểm tra owner/ACL. Người dùng bất kỳ đăng nhập thành công có thể đổi `projectId` để xem dữ liệu người khác.

Một lỗi tinh vi hơn là chỉ kiểm tra `project.tenantId == tenantId` nhưng không kiểm tra quyền của **subject** đối với tenant và project. Kể cả hai điều kiện tenant đều đúng, Chloe vẫn không được xem P1 nếu P1 không cấp ACL cho Chloe.

### 5.2. Mẫu enforcement phía service

Mã minh họa giả định có `TenantMembershipRepository`, `ProjectRepository` và `ProjectAclRepository` với các method được ứng dụng hiện thực, và Spring Security xác thực bearer token:

```java
@Service
public class ProjectQueryService {
    private final TenantMembershipRepository memberships;
    private final ProjectRepository projects;
    private final ProjectAclRepository acls;

    public ProjectQueryService(TenantMembershipRepository memberships,
                               ProjectRepository projects,
                               ProjectAclRepository acls) {
        this.memberships = memberships;
        this.projects = projects;
        this.acls = acls;
    }

    @PreAuthorize("hasAuthority('SCOPE_projects:read')")
    @Transactional(readOnly = true)
    public ProjectResponse getProject(UUID tenantId,
                                      UUID projectId,
                                      Authentication authentication) {
        String subject = authentication.getName();

        TenantRole role = memberships.roleOf(subject, tenantId)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));

        // Query đã ràng buộc tenantId trong WHERE.
        Project project = projects.findByIdAndTenantId(projectId, tenantId)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));

        boolean allowed = role == TenantRole.TENANT_ADMIN
                || subject.equals(project.getOwnerSubject())
                || acls.canRead(projectId, subject);

        if (!allowed) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        // Chỉ map field nằm trong DTO công khai.
        return new ProjectResponse(
                project.getId(),
                project.getName(),
                project.getDescription());
    }
}

public record ProjectResponse(UUID id, String name, String description) {}
```

Để ví dụ hoạt động, cần `@EnableMethodSecurity` và một cấu hình security phù hợp. Các method `roleOf`, `findByIdAndTenantId`, `canRead` là contract của repository trong dự án, không phải mọi method đều được Spring Data tự sinh. `subject` phải xuất phát từ identity đã xác thực; không lấy `userId` tùy ý từ query param.

Điểm quan trọng cần test:

- Có scope `projects:read` chưa đủ để đọc P1. ACL/ownership và tenant membership vẫn phải được kiểm tra.
- `findByIdAndTenantId` giúp chặn trường hợp ID của P1 đi với tenant B.
- Trả về `ProjectResponse` chỉ chứa ba field; entity có `billingAccountNumber` cũng không được tự động serialize.
- Một service method được gọi bằng lối đi khác vẫn cần enforcement thích hợp; không thể dựa vào việc nút trên frontend bị ẩn.
- `@Transactional(readOnly = true)` không phải cơ chế bảo mật, chỉ là ngữ nghĩa transaction/hint về truy cập dữ liệu.

**Chú ý về điều kiện cạnh tranh:** nếu ACL hoặc owner bị thay đổi đồng thời với việc ghi dữ liệu, mô hình "đọc quyền → xử lý → UPDATE không điều kiện" có thể tạo TOCTOU. Với thao tác ghi quan trọng, dùng `UPDATE ... WHERE tenant_id=? AND ...` có điều kiện role/owner/version tại database hoặc khóa nhất quán phù hợp, sau đó kiểm tra số dòng cập nhật.

### 5.3. Nested và batch: kiểm tra cả quan hệ cha–con

Ví dụ API:

```http
GET /api/tenants/A/projects/P1/tasks/T7
POST /api/tenants/A/projects/P1/tasks
POST /api/tenants/A/projects/bulk-export
Content-Type: application/json

{"projectIds":["P1","P3"]}
```

Các phép kiểm thử phải xác nhận `T7.projectId == P1`, `P1.tenantId == A` và subject có quyền trên P1/T7. Không được chỉ gọi `taskRepository.findById(T7)` rồi tin vào URL chứa P1.

Với bulk-export, phải xác định chính sách trước: **từ chối toàn bộ batch khi có ID trái quyền**, hay **trả về riêng các item được phép** với hợp đồng rõ ràng. Dù chọn cách nào, tuyệt đối không để item ngoài tenant hoặc ngoài ACL lọt vào kết quả. Test cả request trộn `[P1, P3]`, ID không tồn tại, trùng ID, danh sách rỗng và kích thước vượt giới hạn.

Với list/search, kiểm thử pagination, search filter, sort, tổng số phần tử, cursor và thống kê. Truy vấn `SELECT COUNT(*)` hoặc cache của trang trước vẫn có thể làm lộ số lượng project tenant khác dù danh sách project đã lọc đúng.

## 6. Kiểm thử cô lập tenant

Tenant là **ranh giới bảo mật**, không chỉ là một trường `tenant_id` để lọc UI. Các lỗi phổ biến:

- Server tin `X-Tenant-Id`, query param hoặc body do client gửi mà không xác minh membership theo identity đã xác thực.
- Endpoint list có `WHERE tenant_id=?`, nhưng endpoint detail sử dụng `findById(id)`.
- Một câu join lấy `task.project_id` đúng nhưng thiếu điều kiện tenant trên bảng liên quan.
- Admin toàn cục hoặc scope `admin` được áp dụng nhầm thành `TENANT_ADMIN` ở mọi tenant.
- File/object storage, search index, Redis cache hoặc job export dùng key thiếu tenant.
- Token chứa membership cũ sau khi đã bị thu hồi, còn server không xác minh ở điểm thực thi.

### 6.1. Đừng tin tenant ID chỉ vì nó có trên đường dẫn

Một request của Dave (admin B):

```http
GET /api/tenants/A/projects/P1 HTTP/1.1
Authorization: Bearer <dave-token>
```

Phải bị chặn vì Dave không có membership A. Dave cũng phải bị chặn nếu cố dùng:

```http
GET /api/tenants/B/projects/P1 HTTP/1.1
Authorization: Bearer <dave-token>
```

Lần thứ hai, membership B là thật nhưng P1 thuộc A. **Cả membership của subject và tenant thực của object phải đúng**, không được kiểm tra một trong hai.

Với user có quyền ở nhiều tenant, đổi tenant trong URL vẫn phải làm thay đổi phạm vi authorization và query tương ứng. Nếu ứng dụng có khái niệm `activeTenant` trong session, phải kiểm tra sự nhất quán giữa activeTenant, membership, tenant URL và object; quy tắc này cần định nghĩa rõ trong hợp đồng.

### 6.2. Kiểm thử truy vấn tenant-scoped

Một cách đặt ranh giới ở repository:

```java
interface ProjectRepository extends JpaRepository<Project, UUID> {
    Optional<Project> findByIdAndTenantId(UUID id, UUID tenantId);

    Page<Project> findByTenantId(UUID tenantId, Pageable pageable);
}
```

Tuy nhiên, đặt thêm điều kiện trong repository **không tự kiểm tra** user có thuộc tenant đang truy vấn hay không. Service vẫn phải xét membership, vai trò và ACL trên từng object theo chính sách.

Với native SQL, entity associations, ORM filter, row-level security (RLS), hoặc database-per-tenant, cần tạo test phù hợp với mô hình thực tế. PostgreSQL RLS có thể là một lớp bảo vệ bổ sung; policy sai, kết nối dùng vai trò bypass RLS hoặc session tenant context bị rò qua connection pool vẫn là rủi ro. Tất cả không thay thế integration test theo danh tính cuối.

### 6.3. Leak qua cache và các API phụ

Các ca cần thử:

| Nguồn dữ liệu | Kịch bản phá vỡ cô lập |
|---|---|
| Response cache / CDN | Alice gọi GET P1, Dave dùng URL tương tự và nhận body đã cache |
| Redis | Key chỉ chứa `projectId` trong nơi có thể trùng ID giữa namespace |
| Search index | Truy vấn theo tên trả về hit từ tenant khác |
| Download/export | URL tải file hoạt động sau khi quyền bị thu hồi hoặc từ tenant khác |
| Webhook/job result | Endpoint tra cứu `jobId` không kiểm tra người tạo và tenant |
| Count/aggregate | `totalElements` hoặc thống kê doanh thu tính từ mọi tenant |
| Logs/error | Error message trả lại SQL, tên tenant khác hoặc object snapshot |

Với response nhạy cảm phụ thuộc user/tenant, ưu tiên `Cache-Control: private, no-store` hoặc cấu hình cache có partition quyền rõ ràng. Header `Vary: Authorization` có thể là một yếu tố của HTTP caching nhưng không nên coi là cơ chế authorization hay mặc định đảm bảo cache chia theo mọi claim/ACL.

## 7. Kiểm thử quyền theo trường: đọc và ghi là hai bài toán

Một resource có thể chứa:

```json
{
  "id": "P1",
  "tenantId": "A",
  "name": "Portal",
  "description": "Web portal",
  "ownerId": "alice",
  "status": "ACTIVE",
  "billingAccountNumber": "1234567890123456",
  "internalNotes": "Giá chiết khấu nội bộ"
}
```

Trong ví dụ, một `GET project` của Bob chỉ được nhận `id`, `name`, `description`. Một `PATCH project` của Alice chỉ được ghi `name` và `description`. Ngay cả Alice là owner cũng không được tự đổi `tenantId`, `ownerId`, `status` hoặc `billingAccountNumber` thông qua endpoint cập nhật nội dung thông thường.

### 7.1. Kiểm thử đọc trường nhạy cảm

Với mỗi vai trò, không chỉ xác nhận `200` mà còn assert **danh sách trường trả về**:

- Bob được phép xem P1, nhưng `billingAccountNumber`, `internalNotes`, `ownerId` và metadata quyền nội bộ không xuất hiện nếu hợp đồng không cho phép.
- `GET /projects/P1/billing` của Bob phải bị từ chối; admin A nhận được đúng dữ liệu được phép (ví dụ chỉ bốn chữ số cuối), không phải toàn bộ account number trừ khi có yêu cầu nghiệp vụ hợp lệ.
- Test cả collection, detail, search, export CSV, Excel, PDF, download link, error response và websocket/event payload nếu thuộc phạm vi hệ thống. Một DTO an toàn của detail không bảo đảm projection từ endpoint list cũng an toàn.
- Test việc dùng `fields=billingAccountNumber`, `include=internalNotes`, `sort=billingAccountNumber`, `filter[...]` hoặc nested `expand=...` nếu API hỗ trợ dynamic projection/query. Không để client bypass policy thông qua tham số chọn trường.

**Hạn chế kỹ thuật:** việc JSON field "không xuất hiện" không đồng nghĩa giá trị không nằm trong response khác, ví dụ chuyển sang `metadata.billing` hoặc header lỗi. Với thông tin nhạy cảm, kiểm thử cả dữ liệu ở những vị trí trả về khác theo hợp đồng.

### 7.2. Kiểm thử mass assignment và ghi trái quyền

Mẫu controller dễ gặp lỗi:

```java
@PatchMapping("/projects/{id}")
public Project update(@PathVariable UUID id,
                      @RequestBody Project incoming) {
    Project existing = repository.findById(id).orElseThrow();
    BeanUtils.copyProperties(incoming, existing);
    return repository.save(existing);
}
```

Nếu client đưa `ownerId` hoặc `tenantId` vào JSON, binding entity hoặc copy toàn bộ thuộc tính có thể cho phép sửa dữ liệu bảo mật. Kiểm tra role ở endpoint **không đủ** nếu endpoint cho phép cập nhật tất cả các field.

Mẫu rõ ràng hơn:

```java
public record UpdateProjectRequest(
        @NotBlank @Size(max = 120) String name,
        @Size(max = 1000) String description
) {}

@Transactional
public void updateProject(UUID tenantId,
                          UUID projectId,
                          Authentication actor,
                          UpdateProjectRequest request) {
    Project project = findAndAuthorizeWrite(
            tenantId, projectId, actor);
    project.setName(request.name());
    project.setDescription(request.description());
    // Không tự nhận tenantId, ownerId, role, status, billing...
}
```

`findAndAuthorizeWrite` ở trên là method nghiệp vụ minh họa: nó phải kiểm tra tenant membership, scope/action, ownership hoặc admin tenant và chống race theo yêu cầu. Code không phải service hoàn chỉnh và cần bổ sung `@Valid` trên tham số controller để kích hoạt Bean Validation.

Một payload tấn công:

```http
PATCH /api/tenants/A/projects/P1 HTTP/1.1
Authorization: Bearer <alice-token>
Content-Type: application/json

{
  "name": "Portal updated",
  "ownerId": "mallory",
  "tenantId": "B",
  "status": "APPROVED",
  "billingAccountNumber": "9999999999999999"
}
```

Có hai hợp đồng hợp lệ phổ biến:

1. **Strict allowlist:** Reject request có field không hỗ trợ, thường `400 Bad Request` và bảo đảm không ghi bất kỳ thay đổi nào.
2. **Ignore unknown fields:** Bỏ qua field không được hỗ trợ, xử lý field được phép nếu đó là hợp đồng công khai đã thống nhất; tuyệt đối không ghi field bị bỏ qua.

Trong ứng dụng cần phát hiện hành vi bất thường, strict validation thường thuận tiện hơn. Nếu dùng Jackson với DTO, phải cấu hình từ chối unknown properties (chẳng hạn bật `FAIL_ON_UNKNOWN_PROPERTIES`) hoặc dùng bộ kiểm tra field tường minh; việc có DTO **không tự đảm bảo** rằng unknown JSON sẽ bị báo lỗi. Thêm test cho cả hai dạng chính sách như đã lựa chọn, không giả định mặc định của thư viện.

### 7.3. PATCH, JSON Patch và nested property

Với `application/json-patch+json`, attacker có thể thử:

```json
[
  {"op":"replace","path":"/name","value":"Portal updated"},
  {"op":"replace","path":"/ownerId","value":"mallory"}
]
```

Phải **validate allowlist đường dẫn** cho mọi operation, kể cả `move`, `copy`, `test`, array index và nested path. Kiểm thử trường hợp một patch gồm một bước hợp lệ rồi một bước trái quyền: theo hợp đồng cập nhật nguyên tử của API, cả patch phải bị từ chối và không có thay đổi một phần. Với JSON Merge Patch, cần phân biệt null (xóa/đặt null) với field vắng mặt và bảo vệ nested object.

Nếu client gửi `PUT` thay `PATCH`, không được vì "thay thế toàn bộ resource" mà tự cho phép ghi các field hệ thống. Quyền field áp dụng cho mọi hình thức ghi, kể cả create/import/bulk-update.

## 8. Kiểm thử quyền chức năng: BFLA

BFLA xảy ra khi API cho phép gọi chức năng mà chủ thể không đủ quyền, ví dụ:

```http
POST /api/tenants/A/reports/export
DELETE /api/tenants/A/projects/P1
POST /api/tenants/A/users/bob/promote
POST /api/internal/jobs/rebuild-index
```

Frontend có thể ẩn các nút `Export`, `Delete`, `Promote`; attacker vẫn có thể gọi URL trực tiếp. Cần kiểm tra ở backend cho **từng route và HTTP method**.

Một cấu hình Spring Security có thể chặn scope ở tầng HTTP, đồng thời service xét vai trò theo tenant và đối tượng:

```java
@Configuration
@EnableMethodSecurity
class ApiSecurityConfiguration {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable()) // Chỉ khi API stateless dùng bearer.
            .sessionManagement(sm -> sm.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST,
                    "/api/tenants/*/reports/export")
                    .hasAuthority("SCOPE_reports:run")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

**Không dừng ở `SCOPE_reports:run`.** Một JWT có scope đó chỉ thể hiện quyền API tương ứng theo issuer; service xuất báo cáo còn phải xác nhận subject đang là `TENANT_ADMIN` của tenant trong URL. Dave là admin tenant B, có `SCOPE_reports:run` vẫn không được export tenant A. Quyền tenant không nên suy từ role toàn cục `ROLE_ADMIN` nếu mô hình nghiệp vụ chỉ cấp admin theo tenant.

`csrf.disable()` chỉ thích hợp khi xác thực bearer token qua header và không có xác thực tự động dựa trên cookie; API dùng session/cookie vẫn cần CSRF protection thích hợp.

Các ca bắt buộc cho function-level:

- Viewer gọi export/delete/promote và bị chặn, không có job mới hoặc thay đổi database.
- Tenant admin A thực thi chức năng tại A thành công; dùng quyền đó ở tenant B thất bại.
- User thiếu scope chức năng bị chặn **dù** có object ACL.
- User có scope nhưng không có role tenant tương ứng vẫn bị chặn.
- Người dùng thử một method khác trỏ vào cùng logic: `POST`, `PUT`, `PATCH`, `DELETE`, version cũ của route, bulk route, internal/admin route.
- Quản trị viên bị thu hồi quyền không thể tiếp tục thực thi hành động mới sau khi membership được cập nhật.

Nếu một chức năng chạy bất đồng bộ, kiểm tra cả quyền **khi tạo job**, quyền **khi đọc/tải kết quả** và bối cảnh quyền mà worker dùng để xử lý. Một job ID khó đoán vẫn cần authorization.

## 9. Hợp đồng HTTP khi bị từ chối

| Trường hợp | Mã HTTP thường dùng | Điều phải test |
|---|---|---|
| Không có token/credentials hợp lệ | `401 Unauthorized` | Không trả dữ liệu; với bearer có thể có `WWW-Authenticate` phù hợp |
| Token hợp lệ nhưng thiếu scope/quyền chức năng | `403 Forbidden` | Không tạo side effect; nội dung lỗi không rò tên resource |
| Resource không tồn tại **hoặc bị che giấu theo policy** | `404 Not Found` | Cùng cấu trúc lỗi, không lộ khác biệt qua body |
| Payload sai schema hoặc có field cấm theo strict DTO | `400 Bad Request` | Không ghi bất kỳ field nào |
| Method HTTP không được hỗ trợ | `405 Method Not Allowed` | Không xem đó là chứng cứ có bảo vệ action tương ứng |
| Xung đột phiên bản hoặc trạng thái nghiệp vụ | `409 Conflict` hoặc `412 Precondition Failed` | Chỉ xử lý sau khi đã vượt qua authorization theo chính sách chống lộ thông tin |

`401` nghĩa là chưa xác thực được; `403` là đã biết chủ thể nhưng thiếu quyền. Có API cố ý trả `404` cho object không thuộc phạm vi nhìn thấy, nhưng cần thống nhất error body, logging và quan sát để không lộ object qua thông báo, header hoặc thời gian phản hồi. Không nên ép tất cả API phải dùng `404`: chọn quy tắc rồi kiểm chứng nhất quán.

Ví dụ lỗi theo `application/problem+json`:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404
}
```

Không trả `"projectId P1 belongs to tenant A owned by Alice"` cho caller ngoài tenant. Với trường hợp bị từ chối, còn phải kiểm tra header `Location`, `Link`, redirect, ETag và các body được serialize bởi exception handler không chứa thông tin ngoài quyền.

## 10. Viết kiểm thử Spring Security và MockMvc

Dùng `spring-boot-starter-test` và `spring-security-test` phù hợp phiên bản Spring Boot trong dự án. Có thể dùng `@SpringBootTest` + `@AutoConfigureMockMvc` để đi qua security filter, controller và service; dùng database test có dữ liệu fixture cụ thể để giữ nguyên enforcement thật.

Ví dụ sau **giả định** đã seed fixture A/B, user và P1/P2/P3 giống mục 3. UUID bên dưới là ID minh họa cho fixture; khi áp dụng vào dự án cần tạo fixture tương ứng. Đoạn code tập trung vào các assertion bảo mật, không thay thế toàn bộ file test/repository.

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProjectAuthorizationIT {
    private static final UUID TENANT_A =
        UUID.fromString("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    private static final UUID TENANT_B =
        UUID.fromString("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
    private static final UUID P1 =
        UUID.fromString("11111111-1111-4111-8111-111111111111");

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;

    private RequestPostProcessor actor(String subject, String scope) {
        return jwt()
            .jwt(token -> token.subject(subject))
            .authorities(new SimpleGrantedAuthority("SCOPE_" + scope));
    }

    @Test
    void unauthenticatedRequestIsRejected() throws Exception {
        mvc.perform(get("/api/tenants/{t}/projects/{p}", TENANT_A, P1))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadProjectWithoutSensitiveFields() throws Exception {
        mvc.perform(get("/api/tenants/{t}/projects/{p}", TENANT_A, P1)
                .with(actor("alice", "projects:read")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(P1.toString()))
            .andExpect(jsonPath("$.name").value("Portal"))
            .andExpect(jsonPath("$.billingAccountNumber").doesNotExist())
            .andExpect(jsonPath("$.internalNotes").doesNotExist())
            .andExpect(jsonPath("$.ownerId").doesNotExist());
    }

    @Test
    void sameTenantWithoutObjectAclCannotRead() throws Exception {
        mvc.perform(get("/api/tenants/{t}/projects/{p}", TENANT_A, P1)
                .with(actor("chloe", "projects:read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void tenantAdminCannotEscalateToAnotherTenant() throws Exception {
        mvc.perform(get("/api/tenants/{t}/projects/{p}", TENANT_A, P1)
                .with(actor("dave", "projects:read")))
            .andExpect(status().isNotFound());

        // Tenant trên URL là B nhưng object P1 thực sự thuộc A.
        mvc.perform(get("/api/tenants/{t}/projects/{p}", TENANT_B, P1)
                .with(actor("dave", "projects:read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void viewerCannotPatchAndDatabaseRemainsUnchanged() throws Exception {
        String before = jdbc.queryForObject(
            "SELECT name FROM projects WHERE id = ?",
            String.class, P1);

        mvc.perform(patch("/api/tenants/{t}/projects/{p}", TENANT_A, P1)
                .with(actor("bob", "projects:write"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Hacked"}
                    """))
            .andExpect(status().isForbidden());

        String after = jdbc.queryForObject(
            "SELECT name FROM projects WHERE id = ?",
            String.class, P1);
        assertThat(after).isEqualTo(before);
    }
}
```

Trong ví dụ: `jwt()` được import từ `SecurityMockMvcRequestPostProcessors.jwt`, `get/patch` từ `MockMvcRequestBuilders`, các matcher từ `MockMvcResultMatchers`, `assertThat` từ AssertJ. Imports thông thường được IDE thêm khi triển khai.

**Quan trọng:** `jwt()` trong Spring Security Test mô phỏng một `JwtAuthenticationToken` đã được xác thực cho request, nhờ đó test được rule scope và policy object/tenant bên trong ứng dụng. Cơ chế này **không kiểm thử việc kiểm tra chữ ký, issuer, audience, thời hạn hoặc thuật toán JWT thật**. Phải có nhóm integration test riêng gửi bearer token được ký từ issuer test/IdP hoặc kiểm thử cấu hình `JwtDecoder` để xác minh xác thực đầu vào. `@WithMockUser` cũng hữu ích cho kiểm thử role đơn giản nhưng không đại diện cho claim/tenant của JWT thật.

### 10.1. Bộ kiểm thử trường bất hợp lệ

Nếu hợp đồng PATCH chọn **strict allowlist**, gửi payload chứa field cấm:

```java
@Test
void cannotMassAssignSecuritySensitiveProperties() throws Exception {
    mvc.perform(patch("/api/tenants/{t}/projects/{p}", TENANT_A, P1)
            .with(actor("alice", "projects:write"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Portal renamed",
                  "ownerId": "mallory",
                  "tenantId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                  "status": "APPROVED"
                }
                """))
        .andExpect(status().isBadRequest());

    // Đọc DB sau request để chứng minh không field nào bị thay đổi.
}
```

Đây là một method bổ sung cho lớp `ProjectAuthorizationIT` ở trên. Muốn `400` đúng, server phải cấu hình từ chối các property ngoài DTO; nếu hợp đồng cho phép bỏ qua field lạ, điều chỉnh expected status và bắt buộc kiểm tra DB không thay đổi các field bị cấm. Cần thêm ca `PATCH` hợp lệ chỉ cập nhật `name`/`description` để xác minh rằng policy không chặn nhầm chức năng chính.

### 10.2. Bộ kiểm thử chức năng quản trị

```java
@Test
void scopeAloneDoesNotGrantCrossTenantExport() throws Exception {
    mvc.perform(post("/api/tenants/{t}/reports/export", TENANT_A)
            .with(actor("dave", "reports:run")))
        .andExpect(status().isNotFound());

    // Thêm assert không có export job mới trong DB/queue.
}

@Test
void tenantRoleAloneDoesNotReplaceRequiredScope() throws Exception {
    mvc.perform(post("/api/tenants/{t}/reports/export", TENANT_A)
            .with(actor("admin-a", "projects:read")))
        .andExpect(status().isForbidden());
}
```

Kiểm thử route/function ngoài filter là đặc biệt cần thiết: bài test chỉ mock service xuất báo cáo bằng `when(service.export(...)).thenReturn(...)` có thể bỏ qua logic authorization đặt tại service, và sẽ báo xanh ngay cả khi chính sách backend thực đang sai. Cần ít nhất một đường kiểm thử tích hợp đi qua code enforcement thật.

### 10.3. Parameterized test theo ma trận

```java
@ParameterizedTest
@CsvSource({
    "alice,    200",
    "bob,      200",
    "chloe,    404",
    "admin-a,  200",
    "dave,     404",
    "mallory,  404"
})
void readPermissionMatrix(String subject, int expectedStatus)
        throws Exception {
    mvc.perform(get("/api/tenants/{t}/projects/{p}", TENANT_A, P1)
            .with(actor(subject, "projects:read")))
        .andExpect(status().is(expectedStatus));
}
```

Test này sử dụng helper/constants của lớp ở mục 10; với fixture giống bảng và endpoint áp dụng chính sách `404` cho object bị ẩn, nó bảo vệ đầy đủ hai ranh giới object/tenant. Tuy nhiên, status-only vẫn là một lớp kiểm tra: mỗi quyền quan trọng phải có thêm test body và side effect.

Cần lưu ý việc kiểm tra status của `@PreAuthorize` và repository chạy qua Spring proxy. Test gọi trực tiếp method trong cùng object khi tự tạo instance, hoặc mock service/policy thay cho code thật, có thể không thấy aspect security như production.

## 11. Kiểm thử sâu: Không rò rỉ dữ liệu và không có side effect

Một case "bị từ chối đúng HTTP code" có thể vẫn là lỗ hổng nếu server đã xử lý một phần trước khi từ chối. Với write/export/charge, thứ tự xử lý nên là xác thực → phân quyền → validate có tính đến chính sách chống lộ thông tin → mutation, và các cập nhật cần được transaction hóa phù hợp.

Bảng kiểm tra hậu điều kiện:

| Hành động trái quyền | Status chưa đủ; cần xác minh thêm |
|---|---|
| `PATCH P1` bởi Bob | Tên, owner, tenant, status, version và audit event không bị thay đổi ngoài hành vi ghi nhận từ chối hợp lệ |
| `DELETE P1` bởi Dave | Project vẫn tồn tại; liên kết/tác vụ nền không bị xóa |
| `POST /reports/export` bởi Viewer | Không có export job mới, không tạo file, không gửi email |
| Bulk edit với `[P1, P3]` | Không sửa P3; nếu chọn all-or-nothing thì P1 cũng không được đổi |
| GET detail bởi user ngoài ACL | Không có tên project, owner, billing data trong body/header/error |
| GET list từ tenant B | Không có P1/P2 trong `items`, `count`, `nextCursor`, `facets` và cache |
| GET báo cáo sau khi bị thu hồi quyền | Không tải được file cũ qua URL hoặc object storage token ngoài thời hạn/chính sách đã định |

Việc ghi security audit "user bị từ chối" có thể là side effect **được phép** của hệ thống bảo mật; test không nên đòi mọi bảng log đều bất biến. Hãy định nghĩa "không có side effect nghiệp vụ" cụ thể.

### 11.1. Property-based và mutation testing

Sau khi ma trận cơ bản ổn định, có thể sinh ngẫu nhiên kết hợp:

```text
subjects      = [alice, bob, chloe, adminA, dave, mallory]
tenants       = [A, B]
resources     = [P1, P2, P3, randomUnknownId]
actions       = [read, patch, delete, export, readBilling]
properties    = [name, description, ownerId, tenantId, status, billing]
```

Với mỗi tổ hợp, dùng oracle quyền độc lập từ policy đã được định nghĩa để so expected. Tránh sao chép nguyên điều kiện production vào oracle: nếu implementation sai, oracle giống hệt cũng sai theo. Những bất biến mạnh có thể viết trực tiếp:

- Không tenant nào đọc object của tenant khác.
- Chỉ owner có role phù hợp hoặc tenant admin mới sửa nội dung cho phép.
- Không thể thay `tenantId`/`ownerId` qua endpoint nội dung.
- Mọi request từ chối không tạo hiệu ứng nghiệp vụ.
- Khi quyền bị thu hồi, những request mới không được tiếp tục thao tác.

Trong mutation testing, thử cố ý bỏ điều kiện `tenant_id`, bỏ `canRead` hoặc nới allowlist field: bộ test phải thất bại. Đây là cách kiểm tra chất lượng **bộ test**, không chỉ chất lượng mã nguồn.

### 11.2. Kiểm tra race, revoke và cache

Kiểm thử các luồng đồng thời:

1. Alice bắt đầu update P1; admin thu hồi quyền Alice trước thời điểm ghi.
2. Bob vừa bị xóa khỏi ACL nhưng tiếp tục gọi GET qua cache.
3. Hai yêu cầu cùng chuyển owner/status khi `version` đã thay đổi.
4. Job export được tạo khi user có quyền, nhưng quyền bị thu hồi trước khi tải file.

Hợp đồng cần quy định điểm kiểm tra quyền: thời điểm bắt đầu request, thời điểm commit thay đổi, thời điểm thực hiện job hay thời điểm tải kết quả. Với giao dịch ghi nhạy cảm, ràng buộc quyền tại thao tác cập nhật/commit bằng điều kiện nguyên tử giúp giảm TOCTOU; với job dài, tái kiểm tra ở bước thực thi hoặc tải xuống tùy mô hình nghiệp vụ.

Nếu application cache metadata quyền, phải test thời gian vô hiệu hóa sau revoke. Với membership nhúng trong JWT, vai trò cũ có thể còn tới khi token hết hạn trừ khi có kiểm tra server-side hoặc cơ chế thu hồi. Cần xác định SLA chấp nhận được và test theo SLA đó, không giả định revoke sẽ tức thì khi kiến trúc chưa hỗ trợ.

## 12. Những lỗi thường làm bộ test "xanh" giả

| Cách kiểm thử | Khoảng trống còn lại | Cách bổ sung |
|---|---|---|
| Chỉ thử API không token và token của admin | Không kiểm tra object ownership, tenant A/B, role thấp | Dùng nhiều user/resource đối chứng trong cùng tenant và khác tenant |
| Chỉ assert `403`/`404` | Mutation có thể đã thực thi trước khi trả lỗi | Assert database, queue/job, side effect không đổi |
| Dùng mock service trả `403` | Không chứng minh policy thật của service/repository | Integration test qua security filter, service và DB |
| Dùng `jwt()` là cho rằng JWT validator đã an toàn | MockJwt bỏ qua signature/issuer/audience/expiration | Test JWT thực với decoder/issuer test |
| Chỉ test detail GET | List, count, export, search, cache, nested bị quên | Test mọi bề mặt có đọc dữ liệu |
| Chỉ test field ở response | Mass assignment qua POST/PUT/PATCH chưa được kiểm tra | Tấn công input với field cấm, assert persisted state |
| Chỉ test URL hiển thị ở frontend | Route quản trị có thể gọi trực tiếp | Gọi endpoint/HTTP method trực tiếp từ test |
| Dùng fixture cùng tenant và cùng ACL cho mọi user | Không phát hiện BOLA | Tạo same-tenant foreign object |
| Test với H2 trong khi production dùng PostgreSQL RLS | Isolation/locking/RLS khác | Dùng Testcontainers hoặc DB giống production khi cần kiểm chứng SQL/policy |
| Để `@Transactional` bao cả test và chỉ đọc data trong transaction đó | Dễ gây hiểu sai về commit, event, worker và transaction khác | Kiểm tra trạng thái sau commit ở transaction độc lập |

Ngoài các test tự động, có thể dùng công cụ proxy để đổi ID, tenant, method, JSON field và scope trong môi trường test được phép. Dù dùng công cụ gì, cần giữ log trace và dữ liệu fixture đủ rõ để tái hiện.

## 13. Quy trình triển khai test trong dự án

Một lộ trình thực dụng:

1. **Đọc hợp đồng API/OpenAPI**: liệt kê endpoint, method, role/scope, resource hierarchy, request/response schema, field nhạy cảm, hành vi `401/403/404`.
2. **Vẽ permission matrix**: tạo ít nhất hai tenant, hai object cùng tenant với owner/ACL khác nhau, một admin của tenant khác, một user không có membership.
3. **Gắn oracle độc lập**: từ yêu cầu nghiệp vụ, viết expected allow/deny và expected visible/writable fields, không copy nguyên implementation.
4. **Chạy happy path**: Alice, Bob, Admin A được các quyền đã mô tả; tránh viết toàn test âm tính rồi bỏ sót API bị khóa quá mức.
5. **Chạy negative cases**: IDOR, đổi tenant URL, mixed batch, role thấp, scope thiếu, extra fields, nested ID mismatch, method variation.
6. **Xác minh hậu điều kiện**: response body/header an toàn, database và side effect không bị thay đổi.
7. **Chạy tích hợp với security thật**: kiểm tra JWT signature/claims, DB policy, transaction và cache/RLS nếu có; thử revoke và concurrency.
8. **Đưa vào CI**: test ma trận ổn định mỗi thay đổi, test concurrency/cache nặng hơn ở pipeline thích hợp, báo rõ fixture và endpoint gây thất bại.

### 13.1. Ví dụ bảng theo dõi test trong PR

| ID | Mục tiêu | Input chính | Expected |
|---|---|---|---|
| AUTHZ-01 | Chặn chưa đăng nhập | No token → GET P1 | `401` |
| AUTHZ-02 | Chủ sở hữu đọc được | Alice/A/P1 | `200`, chỉ field công khai |
| AUTHZ-03 | Same-tenant IDOR | Chloe/A/P1 | `404` |
| AUTHZ-04 | Cross-tenant bằng URL A | Dave/A/P1 | `404` |
| AUTHZ-05 | Path tenant khác resource | Dave/B/P1 | `404` |
| AUTHZ-06 | ACL chỉ đọc không sửa | Bob/PATCH P1 | `403`, DB không đổi |
| AUTHZ-07 | Không được mass assignment | Alice/PATCH P1 có `ownerId` | `400` strict, DB không đổi |
| AUTHZ-08 | Field nhạy cảm không lộ | Bob/GET P1 | Không có `billingAccountNumber`/`internalNotes` |
| AUTHZ-09 | Billing chỉ cho tenant admin | Bob/GET P1/billing | `403` theo hợp đồng, không lộ |
| AUTHZ-10 | Chức năng export giới hạn tenant | Dave có scope/export A | Bị chặn, không tạo job |
| AUTHZ-11 | Thiếu scope | Admin A không có scope export | `403` |
| AUTHZ-12 | Mixed bulk | Alice export `[P1,P3]` | Không xuất dữ liệu P3 |
| AUTHZ-13 | Revoke ACL | Bob mất ACL P1 | Request mới bị chặn theo SLA |
| AUTHZ-14 | Caching | Sau Alice đọc P1, Dave đọc URL | Không lấy body/cache của Alice |

Nếu API có thêm phân quyền dựa trên trạng thái (ví dụ `DRAFT` mới cho sửa, `CLOSED` chỉ cho đọc), bổ sung trạng thái vào ma trận. **Authorization là hàm của dữ liệu và ngữ cảnh hiện tại**, không chỉ một bảng role bất biến.

## 14. Bài tập thực hành

### Bài tập 1 — Tìm lỗ hổng BOLA và tenant leak

Cho service:

```java
@GetMapping("/tenants/{tenantId}/invoices/{invoiceId}")
public InvoiceDto getInvoice(@PathVariable UUID tenantId,
                             @PathVariable UUID invoiceId) {
    return invoiceMapper.toDto(
        invoiceRepository.findById(invoiceId).orElseThrow());
}
```

Hãy viết ít nhất sáu test theo ba user: một owner invoice, một user cùng tenant không có quyền invoice, một admin tenant khác. Cần kiểm tra gì ngoài status? Phác thảo phiên bản service có membership, `tenantId` và object ACL; mô tả liệu câu SQL `findByIdAndTenantId` đã đủ hay chưa.

*Đối chiếu:* SQL tenant-scoped là cần nhưng chưa đủ cho membership và quyền object; response phải lọc field; negative tests xác minh không lộ tổng tiền, thông tin khách hàng và metadata của tenant khác.

### Bài tập 2 — Bảo vệ field và mass assignment

Một endpoint `PATCH /users/{id}` nhận trực tiếp `UserEntity` gồm `displayName`, `email`, `role`, `tenantId`, `isVerified`. Người dùng chỉ được đổi `displayName` của chính mình. Hãy:

1. Thiết kế `UpdateProfileRequest` chỉ chứa field cho phép.
2. Chọn hợp đồng xử lý extra field: reject hay ignore; giải thích.
3. Viết test gửi `role: "ADMIN"`, `tenantId` mới, `isVerified: true` và assert persistent state không đổi.
4. Viết test một update hợp lệ vẫn thành công.

### Bài tập 3 — Chặn BFLA trong báo cáo

Tenant A có viewer, admin; tenant B có admin. Endpoint `POST /tenants/{id}/reports/export` tạo export job bất đồng bộ và `GET /exports/{jobId}/download` trả file đã tạo. Hãy thiết kế ca test chứng minh viewer A không tạo được job, admin B không thể tạo job cho A, và admin B không thể tải báo cáo do admin A tạo ra khi biết `jobId`.

*Gợi ý:* cần kiểm tra quyền **cả hai thời điểm**: tạo job và tải file, đồng thời khẳng định không có metadata/file từ tenant A lộ trong error response.

### Bài tập 4 — Viết property-based authorization test

Tạo danh sách 2 tenant × 3 role × 3 object × 5 action. Viết oracle quyền từ bảng policy độc lập, sinh ngẫu nhiên 500 case, ghi lại seed để tái hiện và assert không có cross-tenant success. Thử cố ý bỏ điều kiện tenant trên repository và chứng minh ít nhất một test phải đỏ.

## 15. Checklist trước khi kết luận API đủ bảo vệ

- [ ] Có fixture nhiều tenant, nhiều subject, nhiều object cùng tenant và ACL khác nhau.
- [ ] Mỗi endpoint/action có test positive và negative theo permission matrix.
- [ ] Query/detail/list/nested/bulk/search/aggregate/export/download đều bị giới hạn theo tenant và object.
- [ ] Quyền admin được ràng buộc đúng tenant; scope/JWT không được coi là toàn bộ quyết định ủy quyền.
- [ ] Field đọc được và field ghi được được whitelist độc lập; test mass assignment, PATCH/PUT/JSON Patch.
- [ ] Status `401/403/404`, body/header và thông báo lỗi tuân thủ hợp đồng, không tiết lộ dữ liệu ngoài quyền.
- [ ] Những thao tác bị từ chối không thay đổi trạng thái nghiệp vụ, không tạo export job hay gọi dịch vụ ngoài.
- [ ] Đã kiểm tra cache/DB query/RLS, thay đổi membership, race condition và job bất đồng bộ khi có liên quan.
- [ ] Có test qua security filter/controller/service/database thật; có test xác thực JWT độc lập với `jwt()` mock.
- [ ] Kịch bản regressions chạy được trong CI với fixture và policy rõ ràng.

**Nguyên tắc cần nhớ:** Test "người dùng đã đăng nhập có thể gọi API" không chứng minh phân quyền đúng. Một bộ test REST API có giá trị phải chứng minh đồng thời **ai**, **trong tenant nào**, **trên đối tượng nào**, **thực hiện hành động gì**, **được đọc/ghi trường nào**, và quan trọng nhất là **việc bị từ chối không để lại dữ liệu hay hiệu ứng nghiệp vụ trái phép**.
