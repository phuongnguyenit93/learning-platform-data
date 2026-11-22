# IDOR và yêu cầu kiểm tra quyền với từng định danh tài nguyên

## 1. Vì sao một ID hợp lệ vẫn có thể tạo lỗ hổng?

Giả sử Alice đăng nhập vào ứng dụng quản lý tài liệu và mở:

```http
GET /api/documents/41
Authorization: Bearer <access-token-cua-alice>
```

Tài liệu `41` thuộc Alice. Ứng dụng trả dữ liệu đúng. Sau đó Alice đổi `41` thành `42`, là tài liệu của Bob:

```http
GET /api/documents/42
Authorization: Bearer <access-token-cua-alice>
```

Nếu server chỉ xác thực Alice rồi gọi `repository.findById(42)` và trả bản ghi, Alice đã truy cập dữ liệu của Bob dù **không có quyền trên tài liệu 42**. Đây là **IDOR — Insecure Direct Object Reference**, một dạng lỗi kiểm soát truy cập.

Trong hệ thống API, vấn đề thường được gọi là **BOLA — Broken Object Level Authorization** (OWASP API1:2023). Điểm cốt lõi không nằm ở chuyện ID là số tuần tự hay UUID mà nằm ở việc **hệ thống không xác minh người gọi có quyền thực hiện đúng hành động trên đúng đối tượng được tham chiếu**.

Ba thành phần của tình huống IDOR:

1. Có **đối tượng cần bảo vệ**: tài liệu, hóa đơn, đơn hàng, ticket, file, báo cáo, tài khoản, bản ghi hay folder.
2. Người gọi có thể cung cấp/thay đổi **tham chiếu đối tượng**: ID, UUID, slug, filename, key, nested ID, query parameter, body field hoặc GraphQL argument.
3. Thiếu hoặc sai **kiểm tra quyền ở cấp đối tượng**: ứng dụng nhận ID nhưng không kiểm tra owner, tenant, nhóm chia sẻ, ACL, mối quan hệ nghiệp vụ hoặc quyền thao tác tương ứng.

**Quy tắc cần nhớ:** `Authentication` trả lời "**Ai đang gọi?**"; quyền endpoint trả lời "**Có thể gọi chức năng này?**"; object-level authorization trả lời "**Có thể thao tác trên đối tượng này?**" Cả ba câu hỏi đều quan trọng và không thay thế nhau.

## 2. IDOR khác với thiếu xác thực hoặc thiếu role như thế nào?

| Tình huống | Vấn đề | Ví dụ |
| --- | --- | --- |
| Caller không đăng nhập | Authentication | Request không có session/token hợp lệ |
| User thường gọi endpoint chỉ cho quản trị | Broken Function Level Authorization (BFLA) | `POST /api/admin/users` không kiểm tra role admin |
| User có quyền vào chức năng đọc tài liệu nhưng đọc tài liệu của Bob | **BOLA/IDOR** | `GET /api/documents/42` chỉ kiểm tra `authenticated()` |
| User được đọc tài liệu nhưng được sửa trường nhạy cảm | Broken Object Property Level Authorization | `PATCH` cho sửa `approvedBy` dù chỉ có quyền chỉnh nội dung |
| Query danh sách trả cả dữ liệu tenant khác | Object/data-scope access control failure | `GET /api/documents` không lọc tenant |

Ví dụ, cấu hình HTTP:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**").authenticated()
    .anyRequest().denyAll()
);
```

chỉ nói request vào `/api/documents/**` cần được xác thực. Nó **không bảo đảm** một người đã đăng nhập được đọc mọi tài liệu ở mọi ID. Tương tự, `hasAuthority("document:read")` có thể chứng minh caller có quyền đọc tài liệu **về mặt chức năng**, nhưng chưa chứng minh quyền trên từng tài liệu cụ thể.

Một lỗi IDOR không được chữa bằng cách thêm `@PreAuthorize("isAuthenticated()")` quanh method vốn đã được gọi bởi authenticated user. Cần có quy tắc gắn **caller + action + resource**.

## 3. ID có thể nằm ở bất cứ đâu, không chỉ path

Tất cả tham chiếu từ request đều có thể bị thay đổi. Những chỗ thường bỏ sót:

| Vị trí | Ví dụ | Cần kiểm tra |
| --- | --- | --- |
| Path variable | `GET /documents/42` | READ trên Document 42 |
| Query parameter | `GET /export?invoiceId=42` | EXPORT trên Invoice 42 |
| JSON body | `PATCH /documents {"documentId":42,"note":"..."}` | WRITE trên Document 42 |
| Form field ẩn | `userId=42` | Quyền sửa profile được tham chiếu |
| Nested path | `GET /projects/5/tasks/42` | Project 5, Task 42, quan hệ Task–Project và quyền ở cả hai cấp |
| Batch IDs | `POST /documents/bulk-delete {"ids":[41,42]}` | DELETE từng ID và cả batch |
| Filename / object key | `GET /files?key=tenant-b/invoice.pdf` | Quyền truy cập file/object key đúng tenant |
| Header | `X-Organization-Id: 5` | Caller có membership trong tổ chức 5 |
| GraphQL argument | `document(id:"42")` | READ trên resolver của Document 42 |
| Job/event message | Message chứa `documentId=42` | Identity của tác nhân xử lý và quyền theo nghiệp vụ |

Một ID có vẻ "nội bộ" nhưng xuất hiện trong response, notification, log, screenshot hoặc link chia sẻ vẫn có thể bị người khác biết. **Không dùng tính bí mật của ID làm hàng rào phân quyền chính.**

### UUID có loại bỏ IDOR không?

**Không.** UUID ngẫu nhiên đủ mạnh làm cho việc đoán ID khó hơn và là biện pháp *defense in depth*; nhưng khi attacker biết một UUID hợp lệ từ email, URL, leak hay log, server vẫn phải kiểm tra quyền. Những định danh như hash của ID tuần tự, mã Base64 hoặc chữ số được mã hóa đơn giản cũng không thay thế object authorization.

Câu hỏi bảo mật đúng là: “Nếu người này biết chính xác ID của một đối tượng thuộc người khác, hệ thống còn chặn được không?” Nếu câu trả lời là không, ứng dụng vẫn có IDOR dù ID khó đoán.

## 4. Công thức chính sách: subject + action + object + context

Một quyết định có thể hình dung là:

```text
allow = policy(
    authenticatedSubject,
    action,
    resourceIdentity,
    trustedResourceState,
    trustedSecurityContext
)
```

Trong đó:

- **Subject**: người dùng hoặc service principal thực sự đã được xác thực; dùng ID ổn định từ Authentication/security context, không lấy `userId` do client tự gửi để quyết định caller là ai.
- **Action**: READ, WRITE, DELETE, EXPORT, APPROVE, SHARE, ADMINISTER hoặc quyền cụ thể khác.
- **Resource identity**: ID/UUID/slug của đúng đối tượng client yêu cầu.
- **Resource state**: tenant, owner, status, classification, project, folder, ACL, soft-delete, approval state lấy từ dữ liệu do server quản lý.
- **Security context**: tenant memberships, scopes/authorities, delegated access, policy áp dụng theo thời điểm.

**Điều kiện tối thiểu cho document riêng tư** có thể là:

```text
Actor đã xác thực
AND Actor có authority document:read
AND Document.id = requestedId
AND Document.tenantId thuộc tenant mà Actor thực sự có quyền
AND (
      Document.ownerId = Actor.subjectId
      OR ACL cấp quyền READ cho Actor
    )
AND Document không bị xóa/khóa theo quy tắc nghiệp vụ
```

Công thức này là chính sách **ví dụ**, không phải mọi hệ thống đều cần owner. Có ứng dụng cho phép cộng tác nhóm, vai trò administrator trong tenant, link chia sẻ có thời hạn hoặc quyền ủy nhiệm. Khi mở rộng, mỗi nhánh OR phải có điều kiện chặt và được kiểm thử để không tạo lỗ hổng cấp quyền ngoài ý muốn.

### “Tenant” không phải một chuỗi client khai là được

Trong nhiều hệ thống SaaS, request dùng `X-Tenant-Id` hoặc `/tenants/{tenantId}` để chọn không gian làm việc. Trường này chỉ thể hiện **tenant được yêu cầu**, không phải tenant được phép. Server phải xác minh membership/role của principal trong tenant đó từ nguồn đáng tin cậy và ràng buộc mọi truy vấn bởi tenant đã được xác minh.

Các điều kiện như:

```java
if (request.getHeader("X-Tenant-Id").equals(document.getTenantId())) {
    return document;
}
```

là **không đủ**: attacker có thể khai tenant giống đối tượng muốn đọc. Nếu chỉ thêm một role `ROLE_USER` mà không đối chiếu membership, lỗ hổng vẫn còn.

## 5. Ví dụ không an toàn: tìm bằng ID rồi trả thẳng

Đây là mẫu **lỗi IDOR** phổ biến trong Spring Boot:

```java
@RestController
@RequestMapping("/api/documents")
public class InsecureDocumentController {
    private final DocumentRepository repository;

    public InsecureDocumentController(DocumentRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public Document get(@PathVariable Long id) {
        return repository.findById(id).orElseThrow();
    }
}
```

Đoạn trên là **một thành phần Spring**, giả định repository/entity đã tồn tại. Nó không biên dịch độc lập với JDK thuần. Ngay cả khi Spring Security filter chain yêu cầu authentication, controller vẫn chỉ dùng ID từ client để tìm bản ghi.

Những vấn đề khác ngoài IDOR:

1. **Trả entity trực tiếp** có thể lộ trường nội bộ hoặc quan hệ JPA chưa chủ động giới hạn.
2. `findById` không kiểm tra tenant, owner, ACL hoặc trạng thái soft-delete.
3. `orElseThrow()` không có loại exception xác định cho API; status HTTP có thể không như mong muốn.
4. Việc truyền qua controller không đảm bảo mọi đường gọi khác (job, message listener, service bean) đều an toàn.

Thêm `@PreAuthorize("hasAuthority('document:read')")` vào controller cải thiện quyền chức năng, **nhưng vẫn không ngăn** user A đọc document B nếu cả hai đều có authority đọc.

## 6. Cách phòng vệ ưu tiên: truy vấn **trong tập dữ liệu đã được cấp quyền**

OWASP khuyến nghị lấy đối tượng từ tập dữ liệu mà caller **được phép truy cập**, thay vì lấy từ toàn bộ database rồi hy vọng có một check bị bỏ sót ở đâu đó.

Thay:

```java
repository.findById(requestedId);
```

bằng truy vấn ràng buộc các thuộc tính đáng tin:

```java
repository.findByIdAndTenantIdAndOwnerIdAndDeletedFalse(
    requestedId,
    verifiedTenantId,
    authenticatedSubjectId
);
```

Lợi ích:

- **Không tìm thấy** và **tìm thấy nhưng caller không có quyền** cùng có thể trả Optional.empty; hạn chế tiết lộ sự tồn tại.
- Query giữ tenant/owner như điều kiện bắt buộc, giảm nguy cơ logic sau đó quên kiểm tra.
- Không cần tải object thuộc tenant khác lên service để rồi mới kiểm tra.
- Với cập nhật/xóa, có thể đặt điều kiện quyền trong lệnh ghi, tránh kiểm tra quyền xong rồi ghi bằng ID rộng.

Tất nhiên đây là chính sách chỉ dành cho owner; nếu có ACL/group sharing thì truy vấn phải được mở rộng đúng business policy, không đơn giản bỏ điều kiện owner để “chữa” lỗi người được chia sẻ không xem được.

## 7. Ví dụ Spring Boot: một API đọc tài liệu theo scope

Các đoạn Java trong mục này là **các class/phương thức thành phần của cùng một ứng dụng Spring Boot dùng Spring Security 6.x/7.x, Spring Data JPA và Java 17+**, không phải một chương trình `javac` độc lập. Các lớp `Document`, `DocumentRepository` và dịch vụ xác minh danh tính phải được dự án cung cấp đầy đủ.

### 7.1. ActorContext là dữ liệu đã xác minh phía server

```java
public record ActorContext(
    String subjectId,
    String tenantId
) {}
```

`subjectId` là định danh người dùng **ổn định** do hệ thống xác thực cấp, không phải `userId` client gửi trong request body. `tenantId` phải là tenant mà principal thực sự được phép sử dụng. Cơ chế xác định tùy ứng dụng: session, Spring Security `Authentication`, JWT được xác minh chữ ký và claims, cộng với membership server-side.

Ví dụ định nghĩa hợp đồng:

```java
public interface CurrentActorService {
    ActorContext requireActorInAuthorizedTenant();
}
```

Interface này **do ứng dụng xây dựng**, không phải API có sẵn của Spring Security. Implementation phải lấy principal từ `SecurityContext` đáng tin, kiểm tra trạng thái đăng nhập, membership của tenant đang chọn và từ chối nếu không hợp lệ. Không cho controller tự tạo `ActorContext` từ dữ liệu JSON do client cung cấp.

### 7.2. Repository truy vấn bản ghi trong scope

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {

    Optional<Document> findByIdAndTenantIdAndOwnerIdAndDeletedFalse(
        Long id,
        String tenantId,
        String ownerId
    );
}
```

Method derived query này yêu cầu entity `Document` có thuộc tính `id`, `tenantId`, `ownerId` và `deleted` kiểu boolean/Boolean phù hợp. Hệ thống phải thực sự lưu tenant và owner chính xác; việc viết tên method không tự tạo cột hoặc bảo vệ mọi query khác.

### 7.3. Service bảo vệ cả authority chức năng và object scope

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentReadService {
    private final DocumentRepository documents;
    private final CurrentActorService actors;

    public DocumentReadService(
            DocumentRepository documents, CurrentActorService actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(Long documentId) {
        if (documentId == null || documentId <= 0) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found");
        }

        ActorContext actor = actors.requireActorInAuthorizedTenant();

        Document doc = documents
            .findByIdAndTenantIdAndOwnerIdAndDeletedFalse(
                documentId, actor.tenantId(), actor.subjectId()
            )
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"));

        return new DocumentView(doc.getId(), doc.getTitle());
    }

    public record DocumentView(Long id, String title) {}
}
```

Mẫu này bảo vệ theo hai tầng:

- `@PreAuthorize`: caller phải có `document:read`; cần bật `@EnableMethodSecurity` và lời gọi phải đi qua Spring-managed proxy.
- Truy vấn scoped: caller phải là **owner** của đúng document trong tenant đã được kiểm chứng và document chưa deleted.

Trả `DocumentView` giúp chỉ xuất dữ liệu cần thiết thay vì serialize toàn entity. Đoạn trên chưa cho phép chia sẻ theo ACL, chưa diễn giải business status khác, và chưa định nghĩa cơ chế chọn tenant; đó là những quy tắc phải triển khai theo nhu cầu thật, không tự nới để mọi người dùng có role READER đều đọc được mọi ID.

### 7.4. Controller không quyết định quyền owner bằng client input

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentReadService service;

    public DocumentController(DocumentReadService service) {
        this.service = service;
    }

    @GetMapping("/{documentId}")
    public DocumentReadService.DocumentView read(
            @PathVariable Long documentId) {
        return service.read(documentId);
    }
}
```

Controller truyền ID được yêu cầu vào service, **không** truyền `ownerId`/`tenantId` như một chứng nhận quyền. Spring Security có thể yêu cầu authenticated ở HTTP layer; service vẫn bảo vệ dữ liệu cho các đường gọi khác controller.

### 7.5. Bật method security

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Bật method security là điều kiện cần cho `@PreAuthorize`. Trong chế độ Spring AOP proxy, gọi `this.read(...)` nội bộ cùng bean thường **bỏ qua advice**; không dựa duy nhất vào annotation cho một đường gọi không đi qua proxy. Truy vấn scoped và các ràng buộc dữ liệu giúp tạo lớp bảo vệ bổ sung.

## 8. Không chỉ READ: UPDATE và DELETE càng nguy hiểm

Nhiều dự án đã bảo vệ `GET` nhưng bỏ sót `PUT/PATCH/DELETE`. Ví dụ:

```http
PATCH /api/documents/42
Content-Type: application/json

{"title":"Changed by Alice"}
```

Nếu server gọi `findById(42)` và `save(...)` sau khi kiểm tra user chỉ có role EDITOR, Alice có thể sửa document của Bob. Không có dữ liệu trả về cũng vẫn là IDOR nếu có side effect trái quyền.

### Lệnh UPDATE có điều kiện quyền

Có thể dùng cập nhật theo ID **và tenant và owner**:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentWriteRepository
        extends JpaRepository<Document, Long> {

    @Modifying
    @Query("""
        update Document d
           set d.note = :note
         where d.id = :id
           and d.tenantId = :tenantId
           and d.ownerId = :ownerId
           and d.deleted = false
        """)
    int changeNoteIfOwner(
        @Param("id") Long id,
        @Param("tenantId") String tenantId,
        @Param("ownerId") String ownerId,
        @Param("note") String note
    );
}
```

Service:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentWriteService {
    private final DocumentWriteRepository documents;
    private final CurrentActorService actors;

    public DocumentWriteService(
            DocumentWriteRepository documents, CurrentActorService actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:write')")
    public void changeNote(Long id, String note) {
        if (id == null || id <= 0) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found");
        }

        ActorContext actor = actors.requireActorInAuthorizedTenant();
        int changed = documents.changeNoteIfOwner(
            id, actor.tenantId(), actor.subjectId(), note
        );

        if (changed != 1) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found");
        }
    }
}
```

Ở đây update chỉ ảnh hưởng bản ghi khớp **cùng lúc** ID + tenant + owner + chưa xóa. Trường hợp khác tenant, khác owner, không tồn tại hoặc đã xóa đều không bị cập nhật; API có thể dùng cùng 404 cho tài nguyên không nhìn thấy.

**Cần lưu ý về JPA bulk update:** JPQL update bỏ qua một số cơ chế dirty checking/entity lifecycle, optimistic version auto-increment và cache entity đang được quản lý theo cách thông thường. Nếu nghiệp vụ yêu cầu optimistic locking, audit fields, validation hoặc entity listeners, cần thiết kế cập nhật phù hợp: thêm điều kiện `version` và cập nhật version có chủ đích, hoặc load có scope trong transaction, sửa entity managed rồi flush. Với soft-delete hoặc write sharing theo ACL, điều kiện còn phải biểu đạt đúng policy. Đừng copy bulk update này nếu dự án cần những bảo đảm đó mà chưa bổ sung.

### DELETE và thao tác không idempotent

DELETE phải kiểm tra **quyền xóa**, không chỉ quyền đọc; có hệ thống cho phép owner đọc nhưng chỉ administrator xóa. Đối với chuyển tiền, duyệt hóa đơn, hủy đơn, tạo download URL, chuyển ownership, cấp quyền chia sẻ, yêu cầu theo **action** cụ thể:

```text
canRead(actor, documentId)   != canDelete(actor, documentId)
canEdit(actor, documentId)   != canShare(actor, documentId)
canView(actor, invoiceId)    != canApprove(actor, invoiceId)
```

Nếu kiểm tra object chỉ ở một endpoint đọc rồi mặc định mọi endpoint khác an toàn, đó là nguồn IDOR phổ biến.

## 9. Alternative: @PreAuthorize và bean policy theo resource ID

Một lựa chọn là dùng method security gọi một service policy:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView read(Long documentId) {
    // Business logic
}
```

Đây là **fragment trong service**. `documentPolicy.canRead(...)` là method của Spring bean do ứng dụng triển khai; nó phải kiểm tra tenant, owner, ACL và trạng thái resource từ dữ liệu đáng tin, rồi trả boolean. Không tạo expression SpEL bằng cách nối thẳng chuỗi từ request.

Với Spring Security, có thể dùng `PermissionEvaluator` qua `hasPermission(#documentId, 'Document', 'READ')` hoặc `AuthorizationManager<MethodInvocation>` khi cần logic dùng chung cho nhiều phương thức. Nhưng cơ chế nào cũng phải bảo đảm **đúng resource ID được yêu cầu**, không chỉ role.

### Một bẫy: kiểm tra đúng trước, query sai sau

Ví dụ:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public Document read(Long id) {
    return repository.findById(id).orElseThrow();
}
```

Nếu policy query DB rồi service `findById` rộng, có ít nhất hai điều cần xem xét:

1. **TOCTOU:** quyền hoặc owner/tenant có thể thay đổi giữa lúc kiểm tra và lúc fetch/write, nhất là khi check ở ngoài transaction.
2. **Hai truy vấn và thiếu defense in depth:** developer có thể sau này đổi policy, overload method hoặc thêm đường gọi bypass proxy, khiến query rộng trở thành vấn đề.

Với dữ liệu nhạy cảm, vẫn ưu tiên **scoped query** ở điểm truy cập dữ liệu và transaction/locking phù hợp. `@PreAuthorize` giúp chặn sớm nhưng không nhất thiết là toàn bộ bảo vệ.

### @PostAuthorize không phải cách ngăn write IDOR

`@PostAuthorize("returnObject.ownerId == authentication.name")` thực thi **sau** thân phương thức. Nếu method đã cập nhật DB và transaction commit trước đó (phụ thuộc advisor ordering), ném `AccessDeniedException` sau cùng **không đảm bảo rollback** những thay đổi đã commit. Vì thế không dựa vào hậu kiểm để bảo vệ write/delete; xác minh quyền trước hành động và ràng buộc ở transaction/query.

## 10. Những điểm phải kiểm tra trong hệ thống đa tenant

Đối với SaaS nhiều tổ chức, kiểm tra owner cá nhân chưa đủ. Một user có thể là thành viên nhiều tenant, các tenant có ID trùng về giá trị định danh ngoại vi, và các vai trò như `ADMIN` thường chỉ có ý nghĩa **trong một tenant**.

Mô hình nên có:

- **Authenticated subject** được nhận diện ổn định, không lấy `userId` từ body như principal.
- **Active tenant** do request chọn nếu cần, nhưng phải **xác minh membership/role** tại server.
- **Row isolation**: mọi SELECT/UPDATE/DELETE có điều kiện tenant, hoặc cơ chế RLS được thiết kế kỹ.
- **Ownership/ACL**: tenant membership không tự cho quyền trên mọi object nếu còn owner/share policy.
- **Cross-reference validation**: tài nguyên con, attachment, invoice line, comments và parent project phải thuộc đúng scope.
- **Admin bypass rõ ràng**: nếu tenant admin được đọc mọi tài liệu của tenant, điều kiện bypass phải kèm kiểm tra tenant, authority cụ thể và audit.
- **Service identity**: scheduled job hoặc message consumer cũng cần scope và lý do hợp lệ để truy cập tenant, không được xem “không có HTTP user” là toàn quyền.

### Nested resource IDs: kiểm tra cả mối quan hệ

Với endpoint:

```http
GET /api/projects/5/tasks/42
```

Việc xác minh user có quyền vào Project 5 là **chưa đủ** nếu Task 42 thực ra thuộc Project 6. Truy vấn an toàn phải xác minh:

```sql
SELECT t.*
FROM tasks t
JOIN projects p ON p.id = t.project_id
WHERE t.id = :task_id
  AND p.id = :project_id
  AND p.tenant_id = :verified_tenant
  AND /* các điều kiện membership/ACL của task và project */;
```

Đây là **SQL dạng minh họa chính sách**, comment phải được thay bằng predicate nghiệp vụ hợp lệ; không phải câu SQL hoàn chỉnh để chạy nguyên văn. Với service thực, dùng repository/JPA query hoặc DB row-level security thể hiện đầy đủ những điều kiện đó.

Không bao giờ tin việc client đặt `projectId=5` và `taskId=42` cạnh nhau nghĩa là hai object liên quan. Quan hệ phải được xác minh từ database.

### Link chia sẻ và quyền ủy nhiệm

Một tài liệu có thể được chia sẻ cho người không phải owner. Khi ấy, thay vì xóa điều kiện owner, policy có thể cho phép:

```text
same_verified_tenant
AND document_is_active
AND (
  owner_id = authenticated_subject
  OR active_share_grant_for_subject
  OR approved_role_in_this_tenant
)
```

Share grant cần kiểm tra expiry, permission scope, revocation và đối tượng được chỉ rõ. Nếu dùng bearer share link, token phải có entropy phù hợp, thời hạn, phạm vi, thu hồi/rotation theo thiết kế; secret URL là một năng lực ủy quyền được quản lý, **không phải lý do để bỏ qua mọi kiểm tra**.

## 11. Các thao tác hàng loạt (bulk) và toàn bộ tập kết quả

Ví dụ API:

```http
POST /api/documents/bulk-export
Content-Type: application/json

{"ids":[41,42,43]}
```

Alice có quyền với 41, nhưng 42/43 thuộc người khác. Chỉ kiểm tra `hasAuthority("document:export")` rồi lấy `findAllById(ids)` là **IDOR ở dạng batch**.

Hai thiết kế hợp lệ tùy business contract:

1. **All-or-nothing:** yêu cầu tất cả ID đều nằm trong scope cho phép. Nếu có một ID ngoài scope, từ chối cả batch, không tạo bất kỳ side effect nào.
2. **Partial results có kiểm soát:** chỉ trả đúng những object caller được phép; giải thích rõ contract, không vô tình rò rỉ thông tin về các ID bị bỏ qua qua status, count hoặc error body.

Nếu cần all-or-nothing, không chỉ so tổng số item sau khi query mà không xử lý duplicate ID:

```text
requested = distinct(validatedRequestIds)
visible = query only permitted objects for those IDs

allow batch only if
    set(visible.ids) == set(requested)
```

Hãy đặt verification và thực thi trong transaction/snapshot phù hợp để tránh đối tượng hoặc quyền bị thay đổi giữa hai bước. Với bulk delete/update, dùng operation ràng buộc scope ở DB và kiểm tra số bản ghi ảnh hưởng; việc “đã validate danh sách trước đó” không thay thế bảo vệ khi ghi.

Một API trả danh sách `GET /api/documents` cũng phải **lọc theo quyền trước khi phân trang/tính tổng**. Nếu load mọi object rồi lọc sau ở Java, UI có thể nhận page rỗng, tổng số bản ghi sai hoặc dữ liệu nhạy cảm đã được nạp vào nơi không nên.

## 12. Các kênh khác dễ bỏ sót IDOR

### 12.1. File download và object storage

Đường dẫn object như `tenant-a/invoices/42.pdf` cũng là reference. Đừng ghép file key do client khai rồi tải thẳng từ S3/GCS/filesystem. Server phải xác định caller có quyền trên **business object** và key storage gắn với object đó.

Nếu server sinh presigned URL, hãy kiểm tra authorization **trước khi phát URL**, giới hạn TTL/permission phù hợp, và cân nhắc xử lý revocation vì URL đã cấp có thể còn hiệu lực đến hết hạn. Không để response cache chung làm rò URL của người khác.

### 12.2. GraphQL và resolver lồng nhau

GraphQL có thể dùng một endpoint `POST /graphql` chung; filter bảo vệ URL không biết mỗi query đang yêu cầu object nào. Các resolver `document(id)`, `project.tasks`, `user.invoices` cần kiểm tra quyền theo object cụ thể. Không chỉ check root user rồi trả tất cả related nodes mà không có scope.

### 12.3. WebSocket, events, async jobs

Một message chứa `documentId` cũng là request truy cập tài nguyên nếu tác nhân có thể điều khiển nó. Đừng cho job toàn quyền chỉ vì không có web session. Dùng identity/scope service phù hợp, xác định trách nhiệm service principal, và áp dụng chính sách với đúng object. Việc truyền `SecurityContext` qua thread bất đồng bộ không luôn tự động; nên kiểm thử cụ thể.

### 12.4. Cache và search index

Nếu cache key chỉ là `documentId` và kết quả được tạo dưới quyền Admin, một user thường có thể nhận bản cache chứa dữ liệu mà họ không được phép. Cache phải có scope theo tenant/principal/permission hoặc phải **kiểm tra quyền mỗi khi phục vụ** từ cache. Search index, elastic queries và denormalized projections cũng cần cùng điều kiện tenant/ACL như DB nguồn.

### 12.5. Khả năng xem dữ liệu khác với quyền thay đổi thuộc tính

Ngay cả khi user có quyền trên Document 42, không có nghĩa họ được sửa mọi field, thay owner, đổi tenant hoặc cấp quyền cho mình. Dùng DTO allowlist cho từng action, validation dữ liệu nhập và **object property authorization**; không binding toàn bộ JSON vào JPA entity rồi `save`.

## 13. Xử lý 401, 403 và 404 không làm lộ dữ liệu

Khi caller truy cập tài nguyên không được phép, ứng dụng có thể cần phân biệt nội bộ:

- **Unauthenticated**: chưa có danh tính hợp lệ.
- **Forbidden**: có danh tính, resource tồn tại nhưng không có quyền.
- **Not found**: resource không tồn tại.
- **Dependency failure**: database/identity service gặp lỗi.

Các mã HTTP thường dùng:

| Trường hợp | Phản hồi thường cân nhắc | Ghi chú |
| --- | --- | --- |
| Không đăng nhập | `401 Unauthorized` / auth challenge | Theo AuthenticationEntryPoint và loại auth |
| Đã đăng nhập nhưng thiếu authority chức năng | `403 Forbidden` | Không nhất thiết tiết lộ ID cụ thể |
| Có ID nhưng resource không tồn tại | `404 Not Found` | Tài nguyên vắng mặt |
| Resource tồn tại nhưng **không được phép biết nó tồn tại** | `404 Not Found` trung tính | Cùng body/status với trường hợp thực sự không tồn tại |
| Resource tồn tại, caller được phép biết nó có thật nhưng không được thao tác | `403 Forbidden` | Chỉ nếu product cho phép tiết lộ sự tồn tại |
| Database hỏng hoặc timeout | `5xx` phù hợp | Không gọi outage là 404 và không trả dữ liệu |

**Không nhầm** `AccessDeniedException` của `@PreAuthorize` với `ResponseStatusException(HttpStatus.NOT_FOUND)`. Một `@PreAuthorize("hasPermission(#id, ...)")` trả false thường làm method security deny trước khi body chạy; nó không tự sinh 404. Muốn chính sách che giấu tồn tại, scoped lookup và error mapping rõ ràng thường dễ kiểm soát hơn. Không đổi **toàn bộ** 403 thành 404 một cách toàn cục.

Ngoài status code, hãy giữ response body, error type, headers, cache policy và thông tin gỡ lỗi trung tính. Nếu ID bị cấm trả 404 nhưng body ghi `"owner=bob"` hoặc header chứa tenant thật, khả năng dò ID vẫn tồn tại. Timing khác biệt lớn cũng có thể rò thông tin; phân tích tùy threat model.

## 14. Java 17 chạy độc lập: xem một ID qua nhiều người dùng

Ví dụ dưới đây dùng Java thuần để **mô phỏng** scoped object authorization. Không có Spring, database, OAuth2 hay HTTP server. Mục đích là minh họa rằng cùng một ID có thể hợp lệ với owner nhưng không hợp lệ với người khác, và một operation WRITE cần quyền khác READ.

Lưu vào file `IdorDefenseDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class IdorDefenseDemo {

    record Actor(
        String subjectId,
        String tenantId,
        Set<String> authorities
    ) {}

    record Document(
        long id,
        String tenantId,
        String ownerId,
        String note,
        boolean deleted
    ) {}

    private final Map<Long, Document> documents =
        new LinkedHashMap<>();

    IdorDefenseDemo() {
        documents.put(41L,
            new Document(41L, "tenant-a", "alice", "Alice note", false));
        documents.put(42L,
            new Document(42L, "tenant-a", "bob", "Bob note", false));
        documents.put(43L,
            new Document(43L, "tenant-b", "carol", "Carol note", false));
    }

    private boolean hasObjectAccess(
            Actor actor,
            Document document,
            String authority
    ) {
        return actor != null
            && document != null
            && !document.deleted()
            && actor.authorities().contains(authority)
            && actor.tenantId().equals(document.tenantId())
            && actor.subjectId().equals(document.ownerId());
    }

    String readResult(Actor actor, long id) {
        if (actor == null) {
            return "401 Unauthorized";
        }
        Document document = documents.get(id);
        if (!hasObjectAccess(actor, document, "document:read")) {
            return "404 Not Found";
        }
        return "200 OK";
    }

    boolean changeNote(Actor actor, long id, String note) {
        Document existing = documents.get(id);
        if (!hasObjectAccess(actor, existing, "document:write")) {
            return false;
        }
        documents.put(id, new Document(
            existing.id(),
            existing.tenantId(),
            existing.ownerId(),
            note,
            existing.deleted()
        ));
        return true;
    }

    String noteOf(long id) {
        return documents.get(id).note();
    }

    public static void main(String[] args) {
        IdorDefenseDemo app = new IdorDefenseDemo();

        Actor alice = new Actor(
            "alice", "tenant-a",
            Set.of("document:read", "document:write"));
        Actor bob = new Actor(
            "bob", "tenant-a",
            Set.of("document:read"));

        System.out.println("Alice own 41: "
            + app.readResult(alice, 41));
        System.out.println("Alice Bob's 42: "
            + app.readResult(alice, 42));
        System.out.println("Alice tenant-b 43: "
            + app.readResult(alice, 43));
        System.out.println("Alice missing 99: "
            + app.readResult(alice, 99));
        System.out.println("Bob own 42: "
            + app.readResult(bob, 42));
        System.out.println("Anonymous 41: "
            + app.readResult(null, 41));

        System.out.println("Alice writes own 41: "
            + app.changeNote(alice, 41, "Updated"));
        System.out.println("Alice writes Bob 42: "
            + app.changeNote(alice, 42, "Wrong"));
        System.out.println("Bob writes own 42 without WRITE: "
            + app.changeNote(bob, 42, "Wrong"));
        System.out.println("Alice note: " + app.noteOf(41));
        System.out.println("Bob note: " + app.noteOf(42));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac IdorDefenseDemo.java
java IdorDefenseDemo
```

Stdout chính xác:

```text
Alice own 41: 200 OK
Alice Bob's 42: 404 Not Found
Alice tenant-b 43: 404 Not Found
Alice missing 99: 404 Not Found
Bob own 42: 200 OK
Anonymous 41: 401 Unauthorized
Alice writes own 41: true
Alice writes Bob 42: false
Bob writes own 42 without WRITE: false
Alice note: Updated
Bob note: Bob note
```

**Điểm quan trọng trong kết quả:**

- Alice có cả READ và WRITE nhưng **không** thể thao tác document của Bob hoặc tenant khác.
- Bob đọc được tài liệu của mình vì có READ, nhưng không sửa được vì thiếu WRITE.
- ID không tồn tại và ID có thật nhưng ngoài scope của Alice cùng trả `404` trong mô hình.
- Thử cập nhật trái quyền không thay đổi note của Bob.
- ID được kiểm tra tại **từng lần gọi READ/WRITE**, không chỉ lúc đăng nhập.

**Giới hạn:** `Map` trong Java demo không cung cấp transaction, locking, kiểm soát concurrency hoặc DB row-level security. Trong ứng dụng thực, phép kiểm tra + cập nhật phải sử dụng transaction/SQL điều kiện đúng để không có race. Không copy một service xử lý dữ liệu theo `Map` vào production thay repository thật.

## 15. Ma trận kiểm thử IDOR/BOLA

### 15.1. Chuẩn bị danh tính và tài nguyên đối chứng

Tạo dữ liệu có chủ đích:

- Alice thuộc tenant A, owner Document 41; có `document:read`, `document:write`.
- Bob thuộc tenant A, owner Document 42; có `document:read`, không có `document:write`.
- Carol thuộc tenant B, owner Document 43; có đủ quyền nhưng ở tenant khác.
- Một tài liệu đã soft-deleted, một tài liệu đã share READ cho Alice, một tài liệu không tồn tại.
- Một admin trong tenant A và một admin tenant B; quyền admin phải có scope rõ.

Không chỉ kiểm thử một user. OWASP khuyến nghị sử dụng ít nhất hai tài khoản/phạm vi quyền và **hoán đổi định danh tài nguyên giữa các session**.

### 15.2. Ma trận API

| Request | Actor | Kỳ vọng quan trọng |
| --- | --- | --- |
| `GET /documents/41` | Alice | 200, chỉ dữ liệu 41 được phép |
| `GET /documents/42` | Alice | 403 hoặc 404 theo policy, không có nội dung Bob |
| `GET /documents/43` | Alice | Bị từ chối do khác tenant |
| `GET /documents/99` | Alice | 404 hoặc contract phù hợp |
| `GET /documents/41` | Không đăng nhập | 401/flow login được thiết kế |
| `PATCH /documents/42` | Alice | Không thay đổi database của Bob |
| `DELETE /documents/42` | Alice | Không xóa/soft-delete tài liệu của Bob |
| `PATCH /documents/42` | Bob chỉ có READ | Không ghi vì thiếu quyền WRITE |
| `GET /projects/5/tasks/42` | Alice; task thuộc project khác | Từ chối; không chỉ check projectId |
| `POST /bulk-export` với IDs 41,42 | Alice | Theo contract all-or-nothing hoặc chỉ 41; không xuất 42 |
| `GET /documents` | Alice | Query, count, pagination chỉ cho dữ liệu được thấy |
| Download key của tenant B | Alice | Không cấp file/URL có quyền truy cập |
| Share/transfer owner của 41 | Alice thiếu quyền SHARE/ADMIN | Không đổi ACL/owner |
| ID là UUID thực của Bob | Alice | Vẫn bị từ chối, dù ID khó đoán |
| Truy cập từ service/job khác HTTP | Identity không đủ quyền | Policy ở service/repository vẫn áp dụng |

### 15.3. Test Spring Security thật, không chỉ mock policy

Có thể dùng `@SpringBootTest`/`MockMvc` và `spring-security-test` hoặc test HTTP qua server chạy thật. Cần assert **dữ liệu trả ra, HTTP status và side effect trong database**, không chỉ assert boolean của một helper.

Một ví dụ test fragment cho API **đã cấu hình đúng security context và actor fixtures**:

```java
mockMvc.perform(get("/api/documents/{id}", 42L)
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("document:read"))))
    .andExpect(status().isNotFound());
```

Đây là **fragment** trong test, không biên dịch độc lập; cần static imports `get`, `user`, `status`, bean `mockMvc` và mapping `CurrentActorService` phù hợp. Với policy che giấu tồn tại, 404 là kỳ vọng; nếu chính sách dùng 403 cho tài nguyên bị cấm, test phải thay tương ứng. Quan trọng là không trả dữ liệu trái quyền.

**Không dùng `@WithMockUser(username="alice")` rồi giả định identity token trong ứng dụng production cũng map thành subjectId `alice`**. Nếu production dùng JWT `sub`, custom principal, tenant membership database hoặc service token, test cần khởi tạo context/claims phù hợp để kiểm tra đúng đường đi thật.

### 15.4. Test negative và race

Các kiểm thử nên bao gồm:

1. Dùng object ID hợp lệ nhưng thuộc **người khác cùng tenant**.
2. Dùng ID thuộc **tenant khác**, kể cả khi user có authority chung.
3. Dùng ID xuất hiện trong link, email hoặc response của người khác.
4. Với nested IDs, thay ID **ở từng cấp**; Task không thuộc Project trong URL vẫn phải bị chặn.
5. Với batch, chèn **một** ID trái quyền vào tập ID hợp lệ.
6. Với DELETE/PATCH/APPROVE/EXPORT, kiểm tra database, event và file storage **không có side effect** nếu deny.
7. Với pagination, filter và count, không lộ số lượng resource trái quyền.
8. Với cache hit, kết quả vẫn bị kiểm tra quyền; không phục vụ từ cache của admin cho user thường.
9. Với quyền đã bị revoke, cache và token không duy trì quyền quá thời hạn thiết kế.
10. Với đồng thời thay đổi owner/tenant/ACL và update, đảm bảo transaction/locking/conditional DML chặn race.
11. Khi DB/authorization service bị lỗi, ứng dụng **không fail open**; trả lỗi an toàn và giám sát đúng.
12. Khi gọi service bằng bean khác hoặc message listener, policy vẫn áp dụng; không bỏ qua vì không đi qua HTTP filter.
13. Với optimistic locking, update sai version không được ghi đè thay đổi mới.
14. Nếu API hỗ trợ share link/temporary token, thử link hết hạn, bị revoke, khác resource/action.

### 15.5. Kiểm thử bảo mật tự động ở CI

Mỗi khi thêm endpoint nhận một object reference, tạo ít nhất một test **swap ID** giữa hai principal có thật trong test fixture. Cách này dễ review hơn một test chỉ xác minh happy path. Có thể kết hợp SAST/DAST để tìm luồng `@PathVariable` → repository `findById` hoặc các endpoint có body IDs, nhưng automation không thay thế phân tích business policy.

Mức tốt hơn là kiểm thử **invariant**: đối với mọi actor A, resource B mà A không có quyền, mọi action READ/WRITE/DELETE/EXPORT đều không được trả dữ liệu hay gây side effect trái quyền.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| “Đã đăng nhập thì được xem object theo ID” | Authentication không chứng minh quyền object | Kiểm tra subject + action + resource |
| “Đã có ROLE_USER/EDITOR nên sửa được mọi ID” | Role chỉ mang quyền chức năng | Thêm owner/tenant/ACL/membership và đúng action |
| Dùng `repository.findById(id)` trên đường dữ liệu riêng tư | Đọc/ghi object không nằm trong scope | Scoped repository query hoặc policy trước khi trả dữ liệu |
| Nhận `ownerId` từ JSON rồi so sánh với document | Client có thể khai owner tùy ý | Lấy subject từ Authentication đã xác minh |
| Tin `X-Tenant-Id` là bằng chứng thuộc tenant | User có thể tự đổi header | Xác nhận tenant membership phía server |
| Đổi ID tuần tự sang UUID rồi dừng | UUID có thể bị lộ/được chia sẻ | Kiểm tra object authorization với mọi ID |
| Chỉ bảo vệ GET, bỏ PATCH/DELETE/EXPORT | Vẫn có khả năng sửa/xóa/lấy file người khác | Audit toàn bộ action có object reference |
| Chỉ check parent ID của nested route | Child ID có thể thuộc parent khác | Join đúng quan hệ và quyền trên từng cấp cần thiết |
| Chỉ check một ID đại diện trong batch | ID khác trong batch có thể trái quyền | Validate toàn bộ tập và bảo vệ lúc thực thi |
| Dùng `@PostAuthorize` để bảo vệ write | Side effect có thể commit trước khi deny | Pre-check + scoped mutation/transaction |
| Dùng method security nhưng gọi `this.securedMethod()` | Bypass Spring AOP proxy | Gọi qua Spring bean, đặt policy tại data access |
| Dùng cache key chung cho nhiều tenant | Kết quả hoặc file của tenant khác bị trả lại | Partition cache/kiểm tra quyền trên hit |
| Trả 404 nhưng body chứa lý do “belongs to Bob” | Vẫn lộ sự tồn tại và owner | Error contract trung tính, audit lý do nội bộ |
| Nuốt lỗi DB rồi cấp quyền cho user | Fail open | Fail closed và xử lý lỗi hạ tầng riêng |
| Serialize trực tiếp JPA entity | Có thể lộ trường nhạy cảm/relations | DTO allowlist và field-level authorization |
| Lọc dữ liệu sau khi phân trang | Count/page có thể chứa tín hiệu trái quyền | Scope ngay trong query và count |
| Tin mọi service invocation có HTTP SecurityContext | Job/async/thread khác không có auth như mong đợi | Thiết kế service identity và context propagation rõ |

## 17. Checklist review mỗi endpoint có định danh tài nguyên

Trước khi merge một API hoặc service method, trả lời được những câu hỏi:

1. **Resource reference xuất hiện ở đâu?** Path, query, body, form, header, GraphQL, event hay object storage key?
2. **Subject lấy từ đâu?** Authentication/session/token đã được server xác minh, hay từ giá trị caller tự gửi?
3. **Action thực tế là gì?** Read, edit, delete, approve, export, share, move, transfer ownership?
4. **Quyền chức năng đã có chưa?** Ví dụ `document:read` không tự thay cho `document:write`.
5. **Quyền object cụ thể đã có chưa?** Kiểm tra đúng ID, tenant, owner, membership, ACL, trạng thái.
6. **Tài nguyên con có thực thuộc parent trong request không?** Không chỉ tin hai ID xuất hiện trong cùng URL.
7. **Query có bị ràng buộc theo dữ liệu được phép không?** Tránh `findById` rộng cho private resources.
8. **Kiểm tra quyền có còn đúng khi dữ liệu thay đổi đồng thời không?** Transaction, conditional update, version/locking.
9. **Tất cả đường gọi có qua bảo vệ không?** Controller, service khác, batch, job, async, cache hit.
10. **Nếu ID sai quyền, có side effect hoặc dữ liệu bị lộ không?** Test response, DB, file, events.
11. **HTTP 403/404 có phản ánh chính sách công bố sự tồn tại không?** Không rò qua body/header/count.
12. **Đã test bằng ít nhất hai user/tenant và hoán đổi ID chưa?** Không chỉ happy path.
13. **Có dùng UUID như bổ sung chứ không thay thế authorization không?** Đoán khó không đồng nghĩa không truy cập được.
14. **Có hành động điều hành/khẩn cấp nào được miễn kiểm tra?** Quyền override phải có scope, approval và audit riêng.
15. **Thay đổi role/ACL có được phản ánh ngay trong data/cache ở mức yêu cầu không?** Thu hồi quyền cũng là một đường kiểm thử.

**Tóm tắt:** IDOR/BOLA xuất hiện khi ứng dụng tin rằng biết một **định danh tài nguyên** nghĩa là được phép truy cập tài nguyên đó. Phòng vệ đúng là **kiểm tra quyền cho từng đối tượng và từng hành động, ở phía server, bằng identity và dữ liệu đáng tin cậy**, đồng thời ràng buộc truy vấn/ghi với scope tenant/owner/ACL. Authentication, role, UUID, việc giấu ID hoặc 404 trung tính đều có ích nhưng **không thay thế** yêu cầu object-level authorization.

## Tài liệu tham khảo

- [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): định nghĩa IDOR, scoped lookup, ví dụ Java/Spring và kiểm thử nhiều tài khoản.
- [OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): yêu cầu kiểm tra quyền trên từng object ID ở mọi endpoint.
- [OWASP REST Assessment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Assessment_Cheat_Sheet.html): thử hoán đổi ID giữa session, đặc biệt GET/PUT/PATCH/DELETE và nested routes.
- [OWASP Web Security Testing Guide — Broken Object Level Authorization](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/12-API_Testing/02-API_Broken_Object_Level_Authorization/): mô hình kiểm thử BOLA.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, custom policy bean và method proxy.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP request authorization không tự thay thế resource policy.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived query và `@Query` để ràng buộc dữ liệu được trả về.
