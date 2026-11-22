# Bảo vệ thao tác tạo mới khi tài nguyên chưa có định danh

## 1. Bài toán: chưa có ID, vậy kiểm tra quyền trên đối tượng nào?

Trong các thao tác đọc, sửa và xóa, ứng dụng thường có thể lấy đối tượng từ ID rồi kiểm tra người dùng có quyền READ, WRITE hoặc DELETE trên chính đối tượng đó hay không:

```text
GET /documents/42
  -> tìm Document #42
  -> kiểm tra actor có READ trên #42 không?
  -> cho phép hoặc từ chối
```

Nhưng khi người dùng gọi `POST /documents` để **tạo mới**, đối tượng chưa được lưu nên thường **chưa có ID do database cấp**. Câu hỏi bảo mật không thể là “có quyền trên Document #null không?” hoặc “có sở hữu tài liệu mới không?” vì tài liệu chưa tồn tại.

Một câu hỏi đúng hơn:

> **Chủ thể đã xác thực có được phép tạo một đối tượng thuộc loại này, trong phạm vi cha/tenant/không gian làm việc này, với các thuộc tính và quan hệ được yêu cầu, ở trạng thái hệ thống hiện tại hay không?**

Ví dụ:

```http
POST /api/projects/10/documents
Content-Type: application/json

{
  "title": "Project brief",
  "content": "First version"
}
```

Trước khi server tạo Document mới, nó vẫn có nhiều dữ liệu để quyết định:

- **Actor:** ai đang đăng nhập; authority nào đã được cấp.
- **Action:** `CREATE_DOCUMENT`, khác READ và WRITE.
- **Parent resource:** Project 10 đã tồn tại; actor có phải thành viên được tạo tài liệu trong đó không?
- **Tenant:** Project 10 thuộc tenant nào; actor có quyền trong tenant đó không?
- **Requested attributes:** tiêu đề, nội dung, loại tài liệu, nhãn bảo mật, template... có được phép đặt không?
- **Business state:** project bị khóa, archived, vượt quota hay đang chờ phê duyệt không?
- **Các tài nguyên tham chiếu:** template, attachment, folder, approver hoặc parentId được client chọn có thuộc phạm vi được phép không?

Chỉ sau khi kiểm tra đúng, service mới nên tạo entity, gán owner/tenant từ **nguồn tin cậy**, lưu vào database và trả ID mới.

## 2. Phân biệt ba dạng quyền

| Quyền | Đối tượng đang được bảo vệ | Ví dụ |
| --- | --- | --- |
| Quyền gọi chức năng | Endpoint hoặc thao tác application | `document:create` |
| Quyền tạo trong một phạm vi | Tenant, project, folder, organization, account hoặc collection | Alice được tạo tài liệu trong Project 10 |
| Quyền trên tài nguyên đã tồn tại | Từng Document có ID sau khi tạo | READ/WRITE/DELETE trên Document 42 |

Một người có `document:create` không đồng nghĩa được tạo tài liệu trong **mọi project**; và một người có WRITE trên Document 42 không tự động được tạo Document 43. Đây là hai quyền khác nhau về hành động và đối tượng.

Một công thức khái niệm:

```text
allowCreate =
    authenticated(actor)
    AND hasAuthority(actor, "document:create")
    AND belongsToVerifiedTenant(actor, targetTenant)
    AND canCreateInParent(actor, parentResource)
    AND validAllowedAttributes(request)
    AND referencedObjectsAreAuthorized(actor, request)
    AND currentBusinessStateAllowsCreation(parentResource)
```

Với tài nguyên cá nhân **không có parent ID**, có thể dùng principal và tenant đã xác minh làm scope tạo. Ví dụ tạo ghi chú riêng: mỗi user được phép tạo ghi chú của chính mình, server tự gán `ownerId` bằng subject ID đã xác thực. Lúc ấy không bắt buộc có `parentId`, nhưng vẫn cần kiểm tra authority, tenant, quota, thuộc tính và các rule nghiệp vụ khác.

**Không ép quy tắc duy nhất cho mọi loại tài nguyên.** Tạo một bình luận trong issue, tạo thành viên vào organization, tạo hóa đơn, tạo chuyển khoản và tạo tài khoản quản trị có các quyền và tác dụng phụ khác nhau.

## 3. Những cách kiểm tra sai khi đối tượng chưa tồn tại

### 3.1. Chỉ kiểm tra Authentication

```java
@PreAuthorize("isAuthenticated()")
public Document create(CreateDocumentRequest request) {
    return repository.save(toEntity(request));
}
```

Đây là **anti-pattern minh họa**: mọi user đã đăng nhập đều có thể tạo ở phạm vi mà request muốn nếu không có kiểm tra khác. Lệnh `toEntity(request)` còn có nguy cơ sao chép owner/tenant từ JSON.

### 3.2. Kiểm tra quyền dựa trên ID null

```java
@PreAuthorize("hasPermission(#document.id, 'Document', 'WRITE')")
public Document create(Document document) {
    return repository.save(document);
}
```

Nếu `document.id == null`, đa số kiểm tra ACL theo ObjectIdentity không có căn cứ để xét WRITE trên tài liệu chưa được lưu. `PermissionEvaluator` có thể trả false hoặc sinh exception tùy implementation. Không nên “chữa” lỗi bằng cách cho phép mọi `id == null`, vì attacker có thể dùng ID null để vượt check.

**Đúng hướng:** kiểm tra quyền CREATE ở phạm vi **đã tồn tại** (project/folder/tenant/collection), hoặc chính sách CREATE của user đối với loại tài nguyên. Quyền trên entity mới có thể được gán **sau khi ID được tạo**, nhưng chỉ trong một quy trình đã được ủy quyền.

### 3.3. Tin các trường ownerId, tenantId hoặc role trong JSON

```http
POST /api/documents
Content-Type: application/json

{
  "title": "Quarterly report",
  "ownerId": "admin-user",
  "tenantId": "tenant-b",
  "status": "APPROVED",
  "visibility": "PUBLIC"
}
```

Nếu server binding trực tiếp JSON thành entity rồi `save`, user có thể tự tạo dữ liệu nhân danh admin, đặt document vào tenant khác hoặc bỏ qua bước phê duyệt. Đây là **mass assignment / broken object property level authorization**, có thể kết hợp với BOLA/IDOR.

Không được coi vì resource “chưa có ID” nên các field khác tự động đáng tin. Các trường nhạy cảm như `ownerId`, `tenantId`, `createdBy`, `approvedBy`, `role`, `isAdmin`, `status`, `permissions` phải được gán bằng logic phía server hoặc chỉ cho phép thay đổi ở workflow đã được ủy quyền.

### 3.4. Lưu trước, kiểm tra sau

```java
@Transactional
@PostAuthorize("@policy.canOwn(authentication, returnObject)")
public Document create(CreateDocumentRequest request) {
    return repository.save(toEntity(request));
}
```

**Không dùng cách này để bảo vệ tạo mới.** `@PostAuthorize` chạy sau khi method body thực hiện; với thứ tự advisor transaction/method security thông dụng, transaction có thể đã commit trước khi post-check ném `AccessDeniedException`. API trả 403 **không đảm bảo entity chưa được tạo**. Side effect như gửi email, cấp URL, đăng event hoặc transaction `REQUIRES_NEW` cũng không thể mặc nhiên rollback.

Dùng **precondition trước ghi** và ràng buộc dữ liệu trong transaction. `@PostAuthorize` hữu ích cho một số thao tác đọc nhưng không phải biện pháp chính cho create/write.

## 4. Thiết kế một create command an toàn

Thay vì nhận JPA entity từ client, dùng DTO riêng chỉ chứa **những field người gọi thực sự được đặt**.

Ví dụ REST request:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateDocumentRequest(
    @NotBlank @Size(max = 160) String title,
    @NotBlank @Size(max = 20_000) String content
) {}
```

Không có `id`, `ownerId`, `tenantId`, `createdBy`, `createdAt`, `status` hoặc `aclEntries` trong request DTO. Điều này giảm bề mặt mass assignment; riêng việc dùng record **không tự bảo đảm** Jackson sẽ từ chối mọi field JSON thừa trong mọi cấu hình. Nếu API cần reject những property không được phép, cấu hình deserializer hoặc validation theo hợp đồng API và có integration test.

### Ai xác định ID, owner, tenant và trạng thái ban đầu?

| Thuộc tính của tài nguyên mới | Nguồn khuyến nghị |
| --- | --- |
| `id` | Database-generated ID hoặc server-generated UUID đúng yêu cầu |
| `ownerId` | Principal/subject đã xác thực và policy tạo được phép |
| `tenantId` | Tenant đã xác minh membership theo actor và parent |
| `projectId` | Project có thật, trong tenant được phép, actor có CREATE |
| `createdBy` | Authenticated subject hoặc service identity hợp lệ |
| `createdAt` | Server clock/database mặc định phù hợp |
| `status` | Giá trị khởi tạo theo workflow server như `DRAFT` |
| `visibility` | Mặc định an toàn, ví dụ PRIVATE, trừ khi có quyền publish |
| `sharePermissions` | Quy trình cấp ACL được ủy quyền riêng, không từ JSON tùy ý |
| `title`, `content` | Request đã validate, sanitize theo ngữ cảnh hiển thị nếu cần |

Nếu endpoint hỗ trợ “tạo thay người khác” (`on behalf of`), đó phải là **một quyền riêng** được policy xác minh, có audit, không phải cho phép ai cũng gửi `ownerId` bất kỳ.

## 5. Nguồn tin cậy: Authentication và tenant membership

Tầng service cần biết actor và tenant được phép. Có thể định nghĩa một hợp đồng ứng dụng:

```java
public record ActorScope(String subjectId, String tenantId) {}

public interface CurrentActorService {
    ActorScope requireActorInVerifiedTenant();
}
```

Đây là **interface tự xây dựng**, không phải API Spring Security có sẵn. Implementation phải:

1. Lấy `Authentication` từ `SecurityContext` của lời gọi hiện tại.
2. Từ chối nếu không có authenticated principal hợp lệ.
3. Dùng subject ID ổn định, chẳng hạn JWT `sub` đã xác minh chữ ký hoặc principal ID nội bộ, thay vì tin username do request gửi.
4. Nếu request chọn tenant, xác minh membership/role ở phía server và xác nhận tenant còn active.
5. Trả `ActorScope` chỉ sau khi hoàn tất xác minh.

Nếu dùng JWT, **claim tenant trong một token hợp lệ không nhất thiết chứng minh membership vẫn còn hiệu lực** khi tài khoản bị thu hồi giữa chừng; tùy threat model, thời hạn token, revocation hoặc tra membership server-side phải được thiết kế. Không biến `X-Tenant-Id` thành bằng chứng tự xác thực.

Khi thao tác tạo được kích hoạt từ job/event thay vì HTTP, phải xác định service principal, delegated actor và scope một cách tường minh. Không coi thiếu user session là quyền toàn cục.

## 6. Spring Security kiểm tra quyền gọi chức năng

Ở HTTP layer:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/api/projects/*/documents")
            .hasAuthority("document:create")
        .anyRequest().denyAll()
    );
    return http.build();
}
```

Đây là **fragment trong class cấu hình Spring Security**, cần imports, authentication configuration, các endpoint khác và CSRF/CORS phù hợp. Cấu hình ví dụ chỉ cho POST vào đường dẫn tương ứng với authority `document:create`; nó **chưa kiểm tra** actor có được tạo trong một Project cụ thể hay không.

Bật method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Ở service method, thêm một kiểm tra action cơ bản:

```java
@PreAuthorize("hasAuthority('document:create')")
@Transactional
public DocumentView create(Long projectId, CreateDocumentRequest request) {
    // Sau đây còn phải kiểm tra project/tenant/membership bên trong transaction.
}
```

Annotation `@PreAuthorize` cần Spring-managed proxy và `@EnableMethodSecurity`. Kiểm tra action ở HTTP và service có thể trùng, nhưng service-level check còn bảo vệ những đường gọi từ bean khác. Không dựa duy nhất vào HTTP filter khi service được dùng lại từ batch, message listener hoặc scheduled task.

**Quan trọng về transaction order:** theo cấu hình advisor phổ biến, `@PreAuthorize` có thể chạy **trước** transaction interceptor của method. Nếu kiểm tra điều kiện tạo nhạy cảm và cần cùng transaction với việc ghi, hãy kiểm tra lại **ở trong service body sau khi transaction đã bắt đầu** hoặc thiết kế một transaction boundary bao gồm quyết định, theo yêu cầu nhất quán của dữ liệu. Đừng mặc định annotation xuất hiện trước/sau trong code quyết định thứ tự interceptor.

## 7. Ví dụ Spring Boot: kiểm tra quyền tạo trong Project đã tồn tại

Dưới đây là **các class/thành phần minh họa** trong Spring Boot, Spring Security, Spring Data JPA và Java 17+. Mã cần entity, repository, database schema và authentication infrastructure của dự án; không phải một file có thể chạy chỉ bằng `javac`.

### 7.1. Truy vấn tài nguyên cha trong tenant đã xác minh

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProjectRepository extends JpaRepository<Project, Long> {
    Optional<Project> findByIdAndTenantIdAndArchivedFalse(
        Long id, String tenantId
    );
}
```

Entity `Project` phải có `id`, `tenantId` và `archived` tương ứng. Query này tìm project theo ID **và tenant đã xác minh**. Nếu project ở tenant khác, nó trả rỗng giống như project không tồn tại. Việc "không nhìn thấy" tài nguyên cha có thể được xử lý thành một HTTP 404 trung tính nếu đó là chính sách API.

### 7.2. Membership phải có quyền CREATE, không chỉ READ

Ví dụ repository riêng của quyền thành viên:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProjectMemberRepository
        extends JpaRepository<ProjectMember, Long> {

    boolean existsByProjectIdAndSubjectIdAndCanCreateDocumentsTrue(
        Long projectId, String subjectId
    );
}
```

Giả định entity `ProjectMember` lưu `projectId`, `subjectId` và `canCreateDocuments` theo dữ liệu do server quản lý. Nếu hệ thống dùng role theo project, cần truy vấn role và tính permission phù hợp. Membership có quyền READ không nhất thiết có quyền CREATE.

### 7.3. Service tạo mới: kiểm tra trước khi lưu

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentCreateService {
    private final ProjectRepository projects;
    private final ProjectMemberRepository members;
    private final DocumentRepository documents;
    private final CurrentActorService actors;

    public DocumentCreateService(
            ProjectRepository projects,
            ProjectMemberRepository members,
            DocumentRepository documents,
            CurrentActorService actors) {
        this.projects = projects;
        this.members = members;
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize("hasAuthority('document:create')")
    @Transactional
    public DocumentView create(
            Long projectId, CreateDocumentRequest request) {

        if (projectId == null || projectId <= 0L) {
            throw notVisible();
        }

        // ActorScope do service phía server xây từ Authentication + membership.
        ActorScope actor = actors.requireActorInVerifiedTenant();

        Project project = projects
            .findByIdAndTenantIdAndArchivedFalse(
                projectId, actor.tenantId())
            .orElseThrow(DocumentCreateService::notVisible);

        // Kiểm tra quyền tạo tại project cha trước bất kỳ thao tác ghi nào.
        boolean canCreate = members
            .existsByProjectIdAndSubjectIdAndCanCreateDocumentsTrue(
                project.getId(), actor.subjectId());

        if (!canCreate) {
            // Ví dụ API chọn che giấu sự tồn tại của project ngoài scope.
            throw notVisible();
        }

        if (request == null
                || request.title() == null
                || request.title().isBlank()
                || request.content() == null
                || request.content().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid document");
        }

        // Project, owner, tenant và trạng thái chỉ lấy từ dữ liệu tin cậy.
        Document document = new Document();
        document.setProject(project);
        document.setTenantId(actor.tenantId());
        document.setOwnerId(actor.subjectId());
        document.setTitle(request.title());
        document.setContent(request.content());
        document.setStatus(DocumentStatus.DRAFT);

        Document saved = documents.save(document);
        return new DocumentView(saved.getId(), saved.getTitle());
    }

    private static ResponseStatusException notVisible() {
        return new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Project not found");
    }

    public record DocumentView(Long id, String title) {}
}
```

**Giả định và ranh giới:**

- `Document`, `DocumentStatus.DRAFT`, `Project`, `ProjectMember` và `DocumentRepository` là các loại dữ liệu của ứng dụng, cần được khai báo theo model thực.
- `CurrentActorService.requireActorInVerifiedTenant()` chỉ trả actor đã xác thực và tenant đã kiểm tra membership.
- `@PreAuthorize` yêu cầu authority chung `document:create`. Với caller đã đăng nhập nhưng không có authority, Spring Security thông thường từ chối trước method body; response có thể là 403.
- Service tìm project bằng **ID và tenant**; actor không thể chỉ đổi projectId sang tenant khác.
- Phải có `canCreateDocuments=true` trong membership đáng tin, không chỉ có quyền nhìn thấy Project.
- Entity mới được tạo bằng constructor trống và setters có chọn lọc; `id` do persistence cấp, `ownerId` và `tenantId` do server gán, status là DRAFT.
- `@Transactional` bao việc tải project, xác nhận membership và lưu document trong cùng **logical transaction**, nhưng điều này **chưa tự giải quyết mọi race** nếu concurrent membership/parent state thay đổi dưới isolation mặc định.
- `documents.save` không chắc tạo ID ngay tại dòng đó trong mọi chiến lược persistence: có thể cần flush hoặc commit để phát hiện constraint violations. Không gửi email hoặc thông báo “tạo thành công” ra ngoài transaction trước khi commit.
- Ví dụ 404 cho project không tồn tại và project không được phép biết là một **API policy lựa chọn**, không phải hành vi mặc định của mọi Spring Security implementation.

### 7.4. Controller tạo và trả Location

```java
import java.net.URI;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/projects/{projectId}/documents")
public class DocumentCreateController {
    private final DocumentCreateService service;

    public DocumentCreateController(DocumentCreateService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<DocumentCreateService.DocumentView> create(
            @PathVariable Long projectId,
            @Valid @RequestBody CreateDocumentRequest request) {
        var result = service.create(projectId, request);
        URI location = URI.create(
            "/api/projects/" + projectId + "/documents/" + result.id());
        return ResponseEntity.created(location).body(result);
    }
}
```

Ở controller, `@Valid` kích hoạt Bean Validation nếu hạ tầng validation đã được cung cấp. `CreateDocumentRequest` chỉ có title/content nên client không thể gán trực tiếp owner/status qua DTO. Nhưng hãy kiểm thử JSON chứa field thừa, độ dài, Unicode, content type và deserialization; không ngầm kết luận mọi field thừa bị reject.

`Location` chứa ID **được server trả về sau khi tạo**, không phải một ID được caller chọn để vượt quyền. Response body nên là DTO với các trường được phép công bố, không serialize toàn bộ JPA entity.

### 7.5. Đoạn cấu hình HTTP và service là hai lớp khác nhau

`SecurityFilterChain` chặn request thiếu authority ở biên HTTP. `@PreAuthorize` trên service chặn những lần gọi service không đủ authority dù đi từ nguồn khác. **Scoped lookup và membership query trong service** kiểm tra quyền trên chính Project được chọn. Đó là ba lớp bổ trợ, không phải ba cách diễn đạt giống hệt.

## 8. Khi kiểm tra bằng @PreAuthorize theo tài nguyên cha

Một lựa chọn khác là gọi bean policy trực tiếp trong expression:

```java
@PreAuthorize(
    "hasAuthority('document:create') and " +
    "@projectPolicy.canCreateDocument(authentication, #projectId)"
)
public DocumentView create(
        @P("projectId") Long projectId,
        CreateDocumentRequest request) {
    // Lưu sau khi đã xác minh và tiếp tục ràng buộc quyền trong transaction.
}
```

Đoạn trên là **method fragment**, cần bean `projectPolicy`, import `org.springframework.security.access.method.P` và hạ tầng Spring Security. Policy bean phải:

1. Lấy caller từ Authentication đã xác thực.
2. Kiểm tra tenant membership từ nguồn server.
3. Xác minh Project theo ID và tenant, project chưa archived/locked.
4. Xác minh caller có quyền **CREATE_DOCUMENT** trong Project.
5. Trả boolean minh bạch, mặc định deny nếu thiếu dữ liệu.

Cú pháp `@P("projectId")` giúp định danh tham số trong SpEL ngay cả khi code không được biên dịch với metadata tên tham số.

**Lưu ý thời điểm:** kiểm tra `@PreAuthorize` có thể chạy **trước transaction** của cùng method theo thứ tự advisor mặc định. Do đó với create nhạy cảm, kiểm tra quyền bằng policy bean ở pre-auth **không thay thế** việc giữ invariant khi thực hiện insert trong transaction. Cũng có thể chọn **chỉ pre-check authority chung**, rồi tra project/membership trong transaction như ví dụ trước để tránh query DB trùng hai lần.

### Dùng hasPermission theo ACL

Nếu quyền tạo tài liệu được biểu diễn bằng ACL trên **Project cha đã tồn tại**, có thể dùng ý tưởng:

```java
@PreAuthorize(
    "hasAuthority('document:create') and " +
    "hasPermission(#projectId, 'com.example.Project', 'CREATE')"
)
public DocumentView create(@P("projectId") Long projectId,
                           CreateDocumentRequest request) {
    // Kiểm tra tenant, business state và mutation boundary tại đây.
}
```

Đây chỉ là một **tùy chọn nếu** Spring ACL `PermissionEvaluator`, `AclService` và `ObjectIdentity` của Project đã cấu hình đúng. `CREATE` ở đây áp dụng cho **Project cha**, không phải Document chưa có ID. `BasePermission.CREATE` chỉ là permission trong ACL; quyết định đúng còn phụ thuộc SID, ACE và dữ liệu tài nguyên đã xác minh. Không dùng ACL CREATE của Project rồi bỏ qua tenant boundary hoặc workflow/quota.

**Không được nhầm:** `hasPermission(#newDocument, 'CREATE')` khi `newDocument.id == null` không phải cách chuẩn để chứng minh quyền tạo entity trong một project bất kỳ. Hãy kiểm tra quyền trên **scope có thật** hoặc một policy create dùng dữ liệu đã biết trước khi insert.

## 9. Khi không có parent ID: tạo trong không gian cá nhân

Với endpoint `POST /api/me/notes`, người dùng có thể được tạo ghi chú riêng nếu:

- Principal đã xác thực.
- Có authority `note:create` hoặc policy cho phép tạo note cá nhân.
- Tài khoản còn active, không bị khóa.
- Quota/billing/plan cho phép.
- Nội dung hợp lệ.
- Server tự gán `ownerId` và tenant scope.

Sơ đồ:

```text
POST /api/me/notes
  |
  v
Authentication -> verified subjectId
  |
  v
check note:create, account state, quota
  |
  v
new Note(ownerId = subjectId, private = true)
  |
  v
repository.save -> new generated ID
```

Đối với sản phẩm chỉ có note cá nhân, endpoint không nhất thiết nhận `ownerId`. Việc thêm `POST /api/users/{userId}/notes` chỉ để client tự chọn owner tạo ra một bề mặt tấn công mới. Nếu nghiệp vụ thật sự cần trợ lý tạo note hộ người khác, kiểm tra riêng quyền `note:create:on-behalf-of`, quan hệ ủy nhiệm, thời hạn và audit.

Một chính sách tạo mới có thể dựa trên **resource type** và **verified tenant/account state**, không cần ID của chính entity sắp tạo. Điều này không yếu hơn kiểm tra object ID, vì đối tượng bảo vệ tại thời điểm đó chính là **hành động tạo trong một phạm vi**.

## 10. Tài nguyên tham chiếu trong request vẫn cần kiểm tra từng ID

Một create request có thể không mang ID của đối tượng mới nhưng lại chứa **ID của nhiều đối tượng đã tồn tại**:

```http
POST /api/projects/10/tasks
Content-Type: application/json

{
  "title": "Prepare release",
  "assigneeId": 52,
  "templateId": 18,
  "parentTaskId": 7
}
```

Ở đây phải kiểm tra:

- User được **CREATE_TASK** trong Project 10.
- Assignee 52 là người có thể được giao task trong Project 10 và caller được phép assign.
- Template 18 thuộc phạm vi có thể sử dụng; không lộ template tenant khác.
- Parent task 7 thuộc đúng project và caller có quyền thao tác.
- Các liên kết giữa IDs có thật và hợp lệ theo workflow.

**Database foreign key chỉ chứng minh một ID tồn tại**, không chứng minh caller có quyền dùng ID đó. Việc ID là số tuần tự hay UUID không thay đổi nghĩa vụ authorization.

### Chú ý liên kết cross-tenant

Nếu task mới của tenant A được gán template ID thuộc tenant B, kiểm tra CREATE_TASK chung vẫn chưa đủ. Việc tạo có thể trở thành công cụ **ghi tham chiếu trái quyền** hoặc **lộ dữ liệu qua quan hệ**.

Một mẫu truy vấn an toàn cho template:

```sql
SELECT t.*
FROM templates t
WHERE t.id = :requested_template_id
  AND t.tenant_id = :verified_tenant_id
  AND t.active = TRUE
  AND EXISTS (
      SELECT 1
      FROM template_permissions p
      WHERE p.template_id = t.id
        AND p.subject_id = :authenticated_subject
        AND p.can_use = TRUE
  );
```

Đây là **SQL minh họa**, cần đối chiếu schema thật; các tên bảng/cột không phải schema Spring Security mặc định. Truy vấn chỉ trả template khi caller có quyền trong tenant đã xác minh.

## 11. Quota, giới hạn số lượng và race khi tạo đồng thời

Nhiều ứng dụng chỉ cho một user tạo tối đa 10 workspace hoặc một project tạo tối đa 100 tài liệu. Kiểm tra quota kiểu:

```java
if (repository.countByProjectId(projectId) < maxDocuments) {
    repository.save(newDocument);
}
```

**không an toàn về tính đồng thời**: hai request có thể cùng đọc count=99 và cùng insert, vượt quota. Ngay cả khi method có `@Transactional`, isolation mặc định thường không bảo đảm check-then-insert là atomic.

Các giải pháp tùy loại giới hạn:

- **Reservation/counter atomic** trong database, ví dụ cập nhật counter có điều kiện `used < quota` rồi chỉ insert khi update thành công, cùng transaction.
- **Row lock** có kiểm soát trên bản ghi chứa quota để serialize phép kiểm tra và cấp suất tạo.
- **Serializable isolation** nếu phù hợp tải, kết hợp retry đúng cách cho serialization failures.
- **Unique constraints** đối với bất biến dạng “chỉ được có một bản ghi với key này”.
- **Versioning/optimistic locking** với logic retry phù hợp, không coi lỗi concurrent là quyền được cấp.

**Giới hạn quota khác authorization nhưng thường là điều kiện của chính sách create.** Một user được phép tạo loại đối tượng này có thể bị từ chối **ở thời điểm hiện tại** vì quota hoặc trạng thái billing. Phải xử lý thông báo lỗi rõ, nhưng không leak số lượng dữ liệu của tenant khác.

### Quyền membership bị thu hồi giữa check và insert

Ví dụ:

1. Request A xác minh Alice là editor Project 10.
2. Admin thu hồi quyền editor của Alice.
3. Request A tiếp tục insert.

Nếu yêu cầu an ninh đòi revocation có hiệu lực **trước khi insert commit**, hãy xem xét transaction isolation, locking hàng membership/project, version/authorization epoch hoặc điều kiện insert dựa trên membership phù hợp. Một transaction bao các thao tác query chưa chắc tự ngăn được race ở `READ_COMMITTED`. Việc chọn cơ chế tùy DB, SLA thu hồi quyền và tải thực tế.

Đừng hứa “đã đặt `@Transactional` nên mọi quyền và quota tự atomic” nếu không có bằng chứng test đồng thời.

## 12. Gán ID và các side effect sau khi tạo

### Ai tạo định danh?

- **Database identity/sequence:** ID xuất hiện khi insert/flush hoặc theo chiến lược generator.
- **Server-generated UUID:** có thể sinh trước khi persist nhưng vẫn do hệ thống tin cậy kiểm soát.
- **Client-generated ID:** có hệ thống hỗ trợ, nhưng phải xử lý namespace, ownership, uniqueness, idempotency và bảo vệ overwrite/upsert.

Với create bình thường, không dùng ID do client gửi để âm thầm gọi `save` trên entity có khóa đã tồn tại, vì ORM có thể xử lý insert/merge khác nhau tùy state. Nếu API thực sự cho phép PUT với ID do client chọn để tạo tài nguyên, hãy định nghĩa tách bạch **create-only** (fail nếu đã có) và **replace/update** (cần quyền trên object hiện có), có unique/conditional write ở DB.

### Không phát side effect trước khi quyền và transaction thành công

Khi tạo Document còn cần:

- Tạo ACL/ACE owner.
- Sinh bản ghi audit.
- Phát domain event.
- Gửi email/notification.
- Tạo thư mục/object storage.
- Lập chỉ mục search.

Hãy xác định side effect nào **phải atomic cùng database**, side effect nào cần **outbox/after-commit** và cơ chế retry/idempotency. Không gửi email “tài liệu đã tạo” rồi sau đó transaction rollback vì check quyền hoặc constraint thất bại.

Nếu tạo ACL theo ID mới, chỉ thực hiện sau khi có ID trong **quy trình đã được ủy quyền**; đảm bảo ACL persistence/transaction và cache invalidation phù hợp. Nếu ACL và document nằm ở các store khác nhau, cần chiến lược nhất quán rõ thay vì giả định `@Transactional` JDBC/JPA sẽ tự bao mọi hệ thống ngoài.

## 13. HTTP 401, 403, 404, 409 và 422 trong thao tác create

Status cụ thể là hợp đồng API. Không để `PermissionEvaluator` hoặc `@PreAuthorize` tự quyết định mọi mã theo nghiệp vụ.

| Tình huống | Mã HTTP thường cân nhắc | Ghi chú |
| --- | --- | --- |
| Chưa có principal hợp lệ | `401 Unauthorized` / auth challenge | Theo AuthenticationEntryPoint |
| Có danh tính nhưng thiếu `document:create` | `403 Forbidden` | Không có quyền thực hiện chức năng |
| Project không tồn tại hoặc ngoài phạm vi hiển thị | `404 Not Found` | Che giấu sự tồn tại khi cần |
| Project tồn tại và caller được biết, nhưng không thể tạo | `403 Forbidden` | Chỉ khi được phép công bố resource |
| Dữ liệu JSON sai format/validation | `400 Bad Request` hoặc `422 Unprocessable Content` | Theo API contract |
| Slug hoặc idempotency key xung đột | `409 Conflict` hoặc phản hồi idempotent đã thiết kế | Phụ thuộc nghiệp vụ |
| Project bị archived / business state không cho tạo | `409`/`403` tùy ý nghĩa | Nhất quán giữa các route |
| Tạo thành công | `201 Created` với Location và DTO phù hợp | ID do server bảo đảm |
| Database/quota service gặp lỗi | `5xx` phù hợp | Không tạo hoặc công bố dữ liệu sai |

Nếu policy cần che giấu Project của tenant khác, trả cùng `404` và response body trung tính cho cả không tồn tại và không được phép biết. Nhưng user thiếu role chức năng có thể nhận `403` mà không lộ ID cụ thể.

Không đổi toàn bộ `AccessDeniedException` của ứng dụng thành 404; lựa chọn che giấu phải gắn với loại tài nguyên và API contract. Không log token, tenant membership bí mật, toàn bộ request body hoặc stack trace ra client.

## 14. Java 17 chạy độc lập: tạo mới mà không cần biết ID trước

Chương trình này **không dùng Spring Security/database**, nhưng minh họa một chính sách tạo mới: kiểm tra subject, quyền chức năng, tenant của parent, membership có quyền CREATE, trạng thái parent; sau đó server mới phát ID và gán owner/tenant. Nó còn cố tình cho đầu vào chứa owner/tenant giả để chứng minh server **không tin các giá trị tự khai**.

Tạo file `SecureCreationDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class SecureCreationDemo {

    record Actor(String id, String tenant, Set<String> authorities) {}
    record Project(long id, String tenant, Set<String> creators,
                   boolean archived) {}
    record ClientDraft(String title, String claimedOwner,
                       String claimedTenant) {}
    record Document(long id, long projectId, String owner,
                    String tenant, String title) {}
    record Result(String outcome, Document document) {}

    private final Map<Long, Project> projects = Map.of(
        10L, new Project(10L, "tenant-a", Set.of("alice"), false),
        20L, new Project(20L, "tenant-b", Set.of("carol"), false),
        30L, new Project(30L, "tenant-a", Set.of("alice"), true)
    );
    private final Map<Long, Document> saved = new LinkedHashMap<>();
    private long nextId = 100L;

    Result create(Actor actor, long projectId, ClientDraft draft) {
        if (actor == null) {
            return new Result("DENY:no-actor", null);
        }
        if (!actor.authorities().contains("document:create")) {
            return new Result("DENY:missing-authority", null);
        }

        Project parent = projects.get(projectId);
        if (parent == null
                || parent.archived()
                || !parent.tenant().equals(actor.tenant())
                || !parent.creators().contains(actor.id())) {
            return new Result("NOT_VISIBLE", null);
        }
        if (draft == null || draft.title() == null
                || draft.title().isBlank()) {
            return new Result("INVALID", null);
        }

        // Bỏ qua hoàn toàn claimedOwner/claimedTenant của client.
        // ID, owner, tenant được xác định từ server sau kiểm tra.
        long generatedId = ++nextId;
        Document document = new Document(
            generatedId, projectId, actor.id(),
            parent.tenant(), draft.title());
        saved.put(generatedId, document);
        return new Result("CREATED", document);
    }

    private static void print(String label, Result result) {
        System.out.print(label + ": " + result.outcome());
        if (result.document() != null) {
            Document d = result.document();
            System.out.print(" id=" + d.id()
                + " owner=" + d.owner()
                + " tenant=" + d.tenant());
        }
        System.out.println();
    }

    public static void main(String[] args) {
        SecureCreationDemo app = new SecureCreationDemo();
        Actor alice = new Actor("alice", "tenant-a",
            Set.of("document:create"));
        Actor bob = new Actor("bob", "tenant-a",
            Set.of("document:create"));
        Actor guest = new Actor("guest", "tenant-a", Set.of());

        ClientDraft forged = new ClientDraft(
            "Team document", "bob", "tenant-b");

        print("Alice permitted", app.create(alice, 10L, forged));
        print("Alice other tenant", app.create(alice, 20L, forged));
        print("Bob no CREATE in project", app.create(bob, 10L, forged));
        print("Guest no authority", app.create(guest, 10L, forged));
        print("Archived parent", app.create(alice, 30L, forged));
        print("Missing parent", app.create(alice, 999L, forged));
        print("Invalid title", app.create(alice, 10L,
            new ClientDraft(" ", "bob", "tenant-b")));

        System.out.println("Stored documents: " + app.saved.size());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac SecureCreationDemo.java
java SecureCreationDemo
```

Stdout chính xác:

```text
Alice permitted: CREATED id=101 owner=alice tenant=tenant-a
Alice other tenant: NOT_VISIBLE
Bob no CREATE in project: NOT_VISIBLE
Guest no authority: DENY:missing-authority
Archived parent: NOT_VISIBLE
Missing parent: NOT_VISIBLE
Invalid title: INVALID
Stored documents: 1
```

Giải thích:

- Alice có quyền tạo ở Project 10; dù request tự khai owner=bob và tenant-b, Document được lưu với **owner=alice, tenant-a**.
- Alice không thể chọn Project 20 thuộc tenant khác.
- Bob có authority create ở cấp chức năng, nhưng không thuộc danh sách những người có quyền tạo tại Project 10 → bị từ chối.
- Guest không có authority, project bị archive hoặc project không tồn tại đều không được tạo.
- Request có title rỗng không được lưu.
- Chỉ có **một** Document được tạo và nhận ID mới do server phát.

**Giới hạn của ví dụ:** đây là bộ nhớ trong một JVM, không có authenticated SecurityContext thực, transaction, concurrent writes, quota, DB constraints hay các tài nguyên tham chiếu. Dùng ví dụ để hiểu **thứ tự quyết định**, không coi nó đủ cho production. Trong ứng dụng thật, actor/tenant được xác minh bởi hạ tầng authentication/membership đáng tin.

## 15. Kiểm thử an toàn tạo mới: những ca bắt buộc

### Chuẩn bị dữ liệu đối chứng

Tạo:

- Alice thuộc Tenant A, có `document:create` và CREATE trong Project 10.
- Bob thuộc Tenant A, có `document:create` nhưng **chỉ READ** Project 10.
- Carol thuộc Tenant B, có CREATE trong Project 20.
- Một user thiếu authority chức năng.
- Một project archived, một project không tồn tại.
- Một project gần quota.
- Một template/assignee/attachment thuộc tenant khác để thử tham chiếu.

### Ma trận security test

| Tình huống | Kỳ vọng |
| --- | --- |
| Alice tạo trong Project 10 | 201, document mới có owner Alice và tenant A |
| Alice đổi path thành Project 20 | Không tạo resource, không lộ dữ liệu tenant B |
| Bob có authority chung nhưng thiếu CREATE trong Project 10 | Bị từ chối; không có row mới |
| Không authenticated | 401/auth flow phù hợp; không ghi |
| Không có `document:create` | 403; không ghi |
| Project archived/locked | Không tạo; status theo API contract |
| Project không tồn tại | 404/contract phù hợp; không tạo |
| JSON tự gửi `ownerId=bob` | Không gán owner Bob; có thể reject field thừa |
| JSON tự gửi `tenantId=tenant-b` | Không đặt tenant sai |
| JSON tự gửi `status=APPROVED` | Không bypass workflow; trạng thái server là DRAFT |
| JSON chọn template khác tenant | Không tạo quan hệ trái quyền |
| JSON chọn assignee ngoài project | Từ chối hoặc lọc theo business rule |
| Hai request đồng thời vượt quota | Không vượt quota; kiểm chứng DB/invariant |
| Membership bị thu hồi trước commit | Kết quả theo yêu cầu nhất quán đã thiết kế |
| DB thất bại sau khi cấp ID tạm | Không trả “created” sai, side effect được rollback/compensate |
| Lặp lại request cùng idempotency key | Không tạo trùng vượt hợp đồng |
| Role admin tenant A tạo trong tenant B | Không tự được phép vì role có scope |
| Create qua service call không HTTP | Vẫn kiểm tra actor/action/tenant/membership |

### Integration test với Spring

Dùng `@SpringBootTest` và `MockMvc` hoặc test HTTP thật, có Spring Security filter chain, controller, service proxy, transaction và database test. Không chỉ test hàm `canCreate(...)` hoặc giả lập repository trả true.

Ví dụ **test fragment** cho endpoint che giấu project ngoài scope:

```java
mockMvc.perform(post("/api/projects/{id}/documents", 20L)
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("document:create")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"title":"Attempt","content":"Not authorized"}
            """))
    .andExpect(status().isNotFound());
```

Đoạn này cần `MockMvc`, static imports và fixture `CurrentActorService`/tenant membership đúng cho Alice; không chạy độc lập. Nếu API contract trả 403 thay vì 404, thay expectation tương ứng. **Quan trọng hơn status:** assert không có Document được lưu ở tenant B, không có ACL hoặc email/event trái quyền, và owner không bị giả mạo.

Một test tốt thực hiện hoán đổi Project ID giữa hai user trong hai tenant, gồm trường hợp Bob đã có authority chung nhưng chỉ thiếu CREATE trên đúng project. Đây là lỗi mà test “người không đăng nhập phải bị từ chối” không phát hiện.

### Test thời điểm kiểm tra

- Đặt spy cho repository để kiểm tra **đường deny không gọi `save`**.
- Test transaction rollback khi validation/business rule thất bại trước commit.
- Test concurrent quota reservation/unique constraint bằng database thực, không chỉ mock.
- Test revocation membership/ACL và cache invalidation.
- Test cross-tenant nested references.
- Test direct service invocation qua Spring-managed bean, không dùng `new Service()` tự tạo nếu cần kiểm tra `@PreAuthorize`.
- Test request body chứa field thừa, field nhạy cảm, null, text dài và loại JSON sai.
- Test side effect sau commit, outbox và idempotency khi retry.

## 16. Các lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Chờ Document có ID mới kiểm tra CREATE | Đã quá muộn hoặc không có object để check | Kiểm tra actor + action + parent/tenant trước insert |
| `hasPermission(null, 'CREATE')` được coi là allow | Thiếu object không chứng minh quyền | Kiểm tra CREATE trên parent hoặc policy resource-type |
| Chỉ có `isAuthenticated()` ở POST | User thường có thể tạo ở scope sai | Thêm authority CREATE và resource/tenant policy |
| Chỉ có `hasAuthority('document:create')` | Có quyền chức năng nhưng không có quyền trên Project được chọn | Kiểm tra quyền ở Project/folder/tenant |
| Cho client gửi `ownerId` và dùng nguyên giá trị | Giả mạo owner hoặc tạo thay người khác | Server gán owner từ identity đã xác thực |
| Cho client gửi `tenantId` rồi tin | Cross-tenant creation | Xác minh tenant membership phía server |
| Binding JSON trực tiếp vào JPA entity | Mass assignment vào status, ACL, owner | DTO allowlist, server-set protected fields |
| Dùng READ trên Project làm CREATE | Quyền quá rộng | Định nghĩa CREATE_DOCUMENT riêng |
| Tạo xong mới dùng `@PostAuthorize` | Insert có thể đã commit trước deny | Precondition trước side effect, transaction/query phù hợp |
| Kiểm tra parentId nhưng không kiểm tra templateId/assigneeId | Tạo quan hệ cross-tenant hoặc trái quyền | Xác minh từng referenced object và relation |
| Coi FK bảo đảm authorization | FK chỉ kiểm tra tồn tại/quan hệ khóa | Kết hợp policy theo principal và tenant |
| Chỉ check quota bằng COUNT rồi INSERT | Race vượt hạn mức | Atomic reservation, lock/constraint hoặc serializable |
| Coi `@Transactional` ngăn mọi race | Isolation READ_COMMITTED không đồng nghĩa serializable | Thiết kế locking/conditional write theo invariant |
| Tạo ACL grant cho owner do JSON khai | Cấp quyền trái phép | Gán owner từ actor đã xác minh, tạo ACL sau khi được phép |
| Gửi email trước commit | Email thông báo tạo dù DB rollback | Outbox/after-commit và idempotency |
| Cho client chọn ID rồi `save` như create | Có thể overwrite/merge hoặc conflict | Create-only semantics, uniqueness, policy update nếu existing |
| Chỉ test 201, bỏ negative test | Không phát hiện cross-tenant/role escalation | Swap parent IDs, forged fields, revoke, race |
| Không bảo vệ service ngoài HTTP | Job/listener có thể bypass endpoint filter | Policy ở service/domain/data access |

## 17. Checklist review một POST tạo tài nguyên

Trước khi merge endpoint CREATE, kiểm tra:

1. **Ai là actor?** Principal lấy từ `Authentication` được xác minh, không từ JSON hoặc request header tự khai.
2. **Hành động nào?** `CREATE_DOCUMENT`/`CREATE_TASK`, không nhầm với READ/WRITE.
3. **Phạm vi nào?** Project/folder/tenant/organization/collection, hoặc scope cá nhân khi không có parent.
4. **Quyền trên parent?** Đã kiểm tra membership, quyền tạo và trạng thái Project từ database chưa?
5. **Trường nào client được đặt?** DTO allowlist có bỏ owner/tenant/status/ACL/createdBy không?
6. **ID tài nguyên mới ai tạo?** Server/database cấp hay client ID có create-only contract?
7. **Nested references có được kiểm tra?** Template, assignee, attachment, parent task, folder.
8. **Tenant đã được xác minh chưa?** Role admin có được giới hạn đúng tenant không?
9. **Business state/quota có cho phép tạo lúc này không?** Có race khi tạo đồng thời không?
10. **Policy nằm ở service/domain chưa?** Không chỉ dựa vào bảo vệ URL.
11. **Cần ACL mới không?** Chỉ cấp ACE theo actor đã xác thực và sau khi create được chấp nhận.
12. **Có transaction boundary đúng không?** Tránh hậu kiểm tạo mới và side effect trước commit.
13. **HTTP response có đúng contract không?** 201 + Location khi thành công; 401/403/404/409/422 phù hợp khi lỗi.
14. **Không lộ resource ngoài scope?** Không đưa tenant/owner/chi tiết policy vào error body cho người không được phép.
15. **Đã test với hai user/tenant chưa?** Không chỉ kiểm tra user hợp lệ, mà còn đổi project ID, forged JSON và concurrency.
16. **Có giám sát audit không?** Ghi nhận create attempts, denied, quota failures và commit thành công mà không log secrets.
17. **Cache/event/index có đúng scope không?** Không tạo share grant, publish event hoặc index trái quyền.

**Kết luận:** Khi đối tượng mới **chưa có ID**, đừng lấy việc thiếu ID làm lý do bỏ qua authorization. Hãy kiểm tra **quyền CREATE trên hành động và phạm vi đã tồn tại**, dùng danh tính/tenant được server xác minh, chỉ cho client đặt những field được phép, và kiểm tra mọi tài nguyên tham chiếu. **Sinh ID và ghi dữ liệu chỉ sau khi chính sách tạo đã được thỏa**, đồng thời bảo vệ các invariant trong transaction/DB và kiểm thử các tình huống cạnh tranh, quyền bị thu hồi, dữ liệu giả mạo.

## Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy bean và cảnh báo `@PostAuthorize` với database writes.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): phân quyền HTTP request theo method/path/authority; không thay thế resource policy.
- [Spring Security — ACLs](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): `BasePermission.CREATE`, `ObjectIdentity`, ACE/SID và kiểm tra quyền trên tài nguyên đã tồn tại.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, kiểm tra quyền trên mỗi request và truy cập tài nguyên.
- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html): input DTO, allowlist các thuộc tính được phép gán.
- [OWASP API Security Top 10 — API1:2023 BOLA](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): phân quyền từng đối tượng được tham chiếu, không chỉ kiểm tra URL.
- [OWASP API Security Top 10 — API3:2023 Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/): mass assignment và bảo vệ field.
- [Spring Data JPA — Repository Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries để truy vấn parent theo tenant/ownership có scope.
