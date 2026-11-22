# Thiết kế controller mỏng với service, repository và DTO

## 1. Vấn đề: controller biết quá nhiều

API quản lý task của một workspace cần tạo, đọc và đổi tên công việc. Một cách viết vội:

~~~java
// Phản mẫu: chưa có kiểm tra quyền/transaction đúng.
@PostMapping("/workspaces/{workspaceId}/tasks")
ResponseEntity<?> create(@PathVariable UUID workspaceId,
                         @RequestBody TaskEntity task) {
    if (task.getTitle() == null) {
        return ResponseEntity.badRequest().build();
    }
    task.setWorkspaceId(workspaceId);
    TaskEntity saved = taskRepository.save(task);
    emailService.sendCreatedEmail(saved);
    return ResponseEntity.ok(saved);
}
~~~

Controller này nhận/trả **JPA entity**, có nguy cơ over-posting, trộn truy xuất DB và side effect với HTTP, không kiểm tra quyền, lại trả **200** thay vì **201 Created** khi tạo tài nguyên. Khi bổ sung cập nhật đồng thời, lỗi, phân trang và kiểm thử, thiết kế càng khó duy trì.

**Controller mỏng** không có nghĩa chỉ một dòng code. Controller phụ trách **HTTP adapter**: ánh xạ method/URI, nhận DTO, validation ở biên, status/header/body. **Service** điều phối use case, quyền, transaction và invariant; **repository** truy xuất dữ liệu; **DTO** mô tả dữ liệu API cho phép đi qua biên.

Bài thuộc module **INTEGRATION_API_REST**, vận dụng resource, URI, HTTP status, xác thực/phân quyền, xử lý lỗi và kiểm thử Java/Spring.

**Mục tiêu:** phân định trách nhiệm bốn lớp; dùng DTO và Bean Validation; thiết kế Spring MVC/JPA với @Transactional, @Version; trả 201/200/304/400/404/409/412/428 đúng contract; kiểm thử riêng HTTP, nghiệp vụ và persistence.

## 2. Ranh giới trách nhiệm

~~~mermaid
flowchart LR
    C[HTTP Client] --> SEC[Spring Security]
    SEC --> CTRL[Controller + DTO]
    CTRL --> SVC[Service + transaction]
    SVC --> AUTH[Resource authorization]
    SVC --> REPO[Repository]
    REPO --> DB[(Database)]
~~~

| Thành phần | Làm gì | Tránh làm gì |
|---|---|---|
| **Controller** | Mapping URI/method/headers/body, @Valid, response 201/Location, ETag, status | SQL, transaction dài, quy tắc nghiệp vụ và gửi email |
| **Service** | Use case, phân quyền resource, domain invariant, transaction | Trả ResponseEntity hoặc phụ thuộc HttpServletRequest |
| **Repository** | Query/save theo scope, paging, optimistic locking | Quyết định HTTP status, làm orchestration |
| **DTO** | Request/response schema, validation biên, dữ liệu công khai | Expose entity/lazy association/secret hoặc chứa persistence logic |

Luồng nên đi một chiều: **request DTO → controller → service → repository/entity → service snapshot → response DTO**. Mapper thủ công hay MapStruct đều được nếu conversion có chủ đích và test được.

Không cần sinh nhiều interface/manager cho một hàm CRUD đơn giản. Một service ít phương thức vẫn có ích khi là nơi giữ transaction và quyền; với truy vấn chỉ đọc lớn, dùng projection thay vì luôn load entity. Mục tiêu là **rõ ràng, thay đổi được, kiểm chứng được**, không phải số lớp.

## 3. Tasks API theo workspace

| Endpoint | Hành vi | Success |
|---|---|---|
| **POST /workspaces/{workspaceId}/tasks** | Tạo task | **201 Created**, Location, body |
| **GET /workspaces/{workspaceId}/tasks/{taskId}** | Đọc task | **200**, ETag; **304** khi validator khớp |
| **PATCH /workspaces/{workspaceId}/tasks/{taskId}** | Đổi title có If-Match | **200** với ETag mới |

~~~http
POST /workspaces/11111111-1111-1111-1111-111111111111/tasks HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{"title":"Chuẩn bị bản phát hành"}

HTTP/1.1 201 Created
Location: /workspaces/11111111-1111-1111-1111-111111111111/tasks/22222222-2222-2222-2222-222222222222
ETag: "task-22222222-2222-2222-2222-222222222222-v0"
Content-Type: application/json

{"id":"22222222-2222-2222-2222-222222222222","title":"Chuẩn bị bản phát hành","status":"OPEN","version":0}
~~~

Giả định: UUID do server sinh; title dài tối đa 120 ký tự, không rỗng; status mới **OPEN**; version JPA ban đầu 0 trong cấu hình minh họa. Caller phải có quyền trên workspace. Với dữ liệu riêng có thể dùng **Cache-Control: private, no-cache** hoặc **no-store** theo chính sách.

**Phân loại lỗi:** JSON/validation sai → **400**; chưa xác thực → **401**; không có quyền → **403** hoặc **404** che giấu; task không tồn tại → **404**; ARCHIVED không cho rename → **409**; If-Match stale → **412**, thiếu → **428**; Content-Type sai → **415**. Lỗi HTTP và lỗi nghiệp vụ cần được ánh xạ nhất quán, không để thành 500 mặc định.

## 4. Request DTO, response DTO và validation

Với Java 17+ / Spring Boot 3, có thể dùng **record** để định nghĩa dữ liệu bất biến ở biên:

~~~java
import java.util.UUID;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

record CreateTaskRequest(
    @NotBlank @Size(max = 120) String title
) {}

record RenameTaskRequest(
    @NotBlank @Size(max = 120) String title
) {}

record TaskResponse(
    UUID id,
    String title,
    TaskStatus status,
    long version
) {
    static TaskResponse from(TaskSnapshot snapshot) {
        return new TaskResponse(
            snapshot.id(),
            snapshot.title(),
            snapshot.status(),
            snapshot.version()
        );
    }
}
~~~

**Không nhận TaskEntity trực tiếp qua @RequestBody**. Nếu entity chứa **workspaceId, ownerId, status, version, internalNote**, client có thể cố ý gửi thêm những field đó (*mass assignment/over-posting*). Request DTO chỉ nhận title; workspaceId đi từ URI nhưng vẫn phải kiểm tra quyền; status, version và ID mới do server quản lý.

### 4.1. Validation ở biên khác validation nghiệp vụ

- **Bean Validation (@NotBlank, @Size)**: kiểu, định dạng và kích thước của input; Spring MVC thường trả **400** khi @Valid body không hợp lệ (cấu hình handler có thể chọn schema lỗi riêng).
- **Domain invariant**: một task đã ARCHIVED không được rename, limit task trong workspace, title duy nhất theo nghiệp vụ; cần được kiểm tra trong service/domain.
- **Ràng buộc DB**: unique index, khóa ngoại, optimistic version; lớp phòng vệ cuối chống race mà validation ở JVM không thể bảo đảm.

Nếu hợp đồng chọn **422 Unprocessable Content** cho dữ liệu có cú pháp đúng nhưng vi phạm quy tắc nghiệp vụ, cần ánh xạ rõ. Đừng coi mọi lỗi validation là 422 theo mặc định: Spring/Jakarta conversion/validation có hành vi riêng.

### 4.2. DTO không được vô tình kéo lazy loading

Trả JPA entity trực tiếp có thể kích hoạt lazy association khi Jackson serialize, gặp **LazyInitializationException**, tạo truy vấn N+1, lộ field nội bộ hoặc vòng tham chiếu JSON. Nên tạo **TaskSnapshot/DTO bên trong service transaction**, chọn projection khi cần và xác định rõ dữ liệu nào client được phép xem. Tránh bật Open Session in View chỉ để “chữa” DTO không có ranh giới.

### 4.3. PATCH cần quy tắc partial rõ ràng

Ví dụ này hỗ trợ PATCH **chỉ đổi title**, không phải mọi trường của Task. Body:

~~~http
PATCH /workspaces/11111111-1111-1111-1111-111111111111/tasks/22222222-2222-2222-2222-222222222222 HTTP/1.1
Content-Type: application/json
If-Match: "task-22222222-2222-2222-2222-222222222222-v0"

{"title":"Kiểm thử bản phát hành"}
~~~

Đây là **custom PATCH contract dùng application/json** cho một thao tác đổi tên, không được tự nhận là JSON Merge Patch hay JSON Patch chuẩn. Nếu muốn dùng **application/merge-patch+json**, phải áp dụng đúng semantics của field vắng mặt, null và nội dung merge; nếu dùng **application/json-patch+json**, phải xử lý danh sách operation theo RFC 6902.

## 5. Entity và repository: dữ liệu không phải HTTP

Trong ví dụ, database lưu task và version bằng JPA:

~~~java
import java.util.UUID;
import jakarta.persistence.*;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

enum TaskStatus { OPEN, DONE, ARCHIVED }

record TaskSnapshot(UUID id, String title,
                    TaskStatus status, long version) {}

@Entity
@Table(name = "tasks")
class TaskEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private UUID workspaceId;

    @Column(nullable = false, length = 120)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private TaskStatus status = TaskStatus.OPEN;

    @Version
    private Long version;

    protected TaskEntity() {} // JPA

    TaskEntity(UUID workspaceId, String title) {
        this.workspaceId = workspaceId;
        this.title = title;
    }

    void rename(String newTitle) {
        if (status == TaskStatus.ARCHIVED) {
            throw new TaskStateConflictException();
        }
        this.title = newTitle;
    }

    TaskSnapshot snapshot() {
        return new TaskSnapshot(id, title, status, version);
    }

    UUID id() { return id; }
    Long version() { return version; }
}

interface TaskRepository extends JpaRepository<TaskEntity, UUID> {
    Optional<TaskEntity> findByIdAndWorkspaceId(
        UUID id, UUID workspaceId);
}
~~~

**TaskStateConflictException** là domain exception giả định, cần được khai báo và ánh xạ sau. Repository được đặt dưới service; nó **không biết** 404/403/412 hay HttpServletRequest. Cách query theo **id + workspaceId** giúp giới hạn phạm vi dữ liệu nhưng **chưa thay thế việc kiểm tra membership/role**; một caller có thể biết workspaceId của bên khác.

Một số quyết định quan trọng:

- **@GeneratedValue** phát ID ở persistence, không cho client quyết định ID khi tạo; nếu dùng client-provided ID thì phải có quy tắc riêng.
- **@Version Long** để JPA áp dụng optimistic locking. Khi flush cập nhật, ORM kiểm tra version cũ; request chạy sau không được âm thầm ghi đè. Giá trị khởi đầu thường là 0 với Hibernate trong ví dụ, nhưng hãy đối chiếu thực tế mapping/DB.
- **snapshot()** chuyển entity sang dữ liệu ứng dụng ngay trong transaction. Controller không giữ entity managed để Jackson tự truy xuất thuộc tính.
- Đối với collection lớn, dùng **Pageable/Sort hoặc cursor query** và projection; tránh **findAll() rồi lọc/paginate trong RAM**.
- Ràng buộc DB như **NOT NULL, unique, foreign key** vẫn cần cho invariant mà nhiều transaction có thể tranh chấp.

## 6. Service: use case, quyền và ranh giới transaction

Service nhận **giá trị ứng dụng** (workspace ID, actor, title, precondition), chứ không nhận **HttpServletRequest**. Các bước của use case có thứ tự rõ: xác minh quyền → tìm entity trong scope → kiểm tra invariant/precondition → thay đổi → lưu/flush → tạo snapshot.

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TaskService {
    private final TaskRepository repository;
    private final WorkspaceAccessPolicy access;

    TaskService(TaskRepository repository,
                WorkspaceAccessPolicy access) {
        this.repository = repository;
        this.access = access;
    }

    @Transactional
    TaskSnapshot create(UUID workspaceId, String title,
                        String actorId) {
        access.requireEditor(actorId, workspaceId);
        TaskEntity entity = repository.saveAndFlush(
            new TaskEntity(workspaceId, title));
        return entity.snapshot();
    }

    @Transactional(readOnly = true)
    TaskSnapshot get(UUID workspaceId, UUID taskId,
                     String actorId) {
        access.requireViewer(actorId, workspaceId);
        return load(workspaceId, taskId).snapshot();
    }

    @Transactional
    TaskSnapshot rename(UUID workspaceId, UUID taskId,
                        String actorId, String title,
                        TaskIfMatch precondition) {
        access.requireEditor(actorId, workspaceId);
        TaskEntity task = load(workspaceId, taskId);

        String current = TaskEtag.strong(
            task.id(), task.version());
        if (!precondition.matchesStrong(current)) {
            throw new TaskPreconditionFailedException();
        }

        task.rename(title);
        repository.flush();  // Phát hiện optimistic conflict sớm.
        return task.snapshot();
    }

    private TaskEntity load(UUID workspaceId, UUID taskId) {
        return repository.findByIdAndWorkspaceId(
            taskId, workspaceId)
            .orElseThrow(TaskNotFoundException::new);
    }
}
~~~

Các lớp **WorkspaceAccessPolicy, TaskIfMatch, TaskEtag** và exception là abstraction để tách quyền/HTTP validator khỏi persistence. Chúng cần được triển khai và kiểm thử; đoạn code là **skeleton có chủ đích**, không phải toàn bộ project chạy ngay. **TaskIfMatch** phải parse/đánh giá điều kiện HTTP theo chuẩn strong comparison (bao gồm trường hợp danh sách ETag và **\*** nếu hợp đồng hỗ trợ); với yêu cầu chống lost update mạnh, contract có thể yêu cầu ETag cụ thể thay vì chỉ điều kiện “tài nguyên tồn tại”.

### 6.1. Vì sao đặt @Transactional ở service?

- **create** và **rename** thực hiện một use case có thay đổi dữ liệu: transaction bao quanh kiểm tra invariant và ghi.
- **get** dùng **readOnly=true** để diễn đạt intent đọc, nhưng **không phải cơ chế kiểm soát quyền** và không bảo đảm mọi truy vấn trong mọi hệ quản trị có snapshot nhất quán tuyệt đối.
- JPA dirty checking ghi thay đổi của managed entity khi flush/commit; **repository.flush()** trong ví dụ giúp bắt optimistic conflict trước khi service tạo snapshot.
- Transaction có thể còn thất bại ở **commit**, ngay cả sau khi flush. Spring proxy thường hoàn tất commit trước khi controller nhận giá trị trả về của phương thức service. Không gửi HTTP success hoặc gọi side effect bên ngoài khi transaction chưa chắc thành công.

**Không đặt @Transactional ở controller như một thói quen**, rồi để toàn bộ serialization, network call và thời gian chờ client nằm trong transaction. Transaction nên bao quanh **đơn vị công việc DB/nghiệp vụ** đủ ngắn, không bao quanh toàn bộ HTTP request.

### 6.2. @Version không xử lý mọi loại xung đột

**@Version** hữu ích khi nhiều writer sửa **cùng entity**. Nó không tự bảo vệ invariant trên **nhiều hàng**, không cho phép retry không kiểm soát, và không khiến hệ thống message broker gửi event đúng một lần. Với cập nhật tồn kho, chuyển tiền hoặc booking, có thể cần **conditional UPDATE, unique constraint, locking hoặc transaction isolation** phù hợp.

Nếu một request đã gửi **If-Match v0**, khi bị optimistic conflict server **không nên tự đọc v1 rồi âm thầm áp dụng lại** như thể điều kiện client vẫn đúng. Đối với endpoint conditional PATCH đã công bố, lỗi này thường được ánh xạ thành **412**, trả quyền quyết định cho client.

### 6.3. Side effects không được bỏ mặc trong transaction

Khi tạo task xong cần phát thông báo, tránh:

~~~text
inside @Transactional:
    save task
    call external email/payment/webhook
    commit transaction
~~~

Nếu external call thành công nhưng commit DB thất bại, email đã gửi không được rollback. Dùng **transactional outbox** hoặc một cơ chế publish-after-commit phù hợp khi yêu cầu nhất quán cao; worker có thể retry nhưng phải xử lý duplicate. Những chi tiết này thuộc cách hoàn thành use case của service, **không nên đặt trong controller**.

## 7. Controller mỏng: chuyển HTTP sang service và quay lại

Ví dụ ghép các phần trên, sử dụng Spring MVC. API có cấu hình Spring Security để yêu cầu xác thực; **Authentication.getName()** được ví dụ dùng làm actor ID đã xác thực, nhưng trong dự án thực cần mapping đúng subject/registered user ID từ security principal, không tin tên do client tự gửi.

~~~java
import java.net.URI;
import java.util.UUID;
import jakarta.validation.Valid;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/workspaces/{workspaceId}/tasks")
class TaskController {
    private final TaskService service;

    TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<TaskResponse> create(
            @PathVariable UUID workspaceId,
            @Valid @RequestBody CreateTaskRequest body,
            Authentication auth) {

        TaskSnapshot created = service.create(
            workspaceId, body.title(), auth.getName());
        URI location = URI.create(
            "/workspaces/" + workspaceId + "/tasks/" + created.id());

        return ResponseEntity.created(location)
            .eTag(TaskEtag.strong(created.id(), created.version()))
            .body(TaskResponse.from(created));
    }

    @GetMapping("/{taskId}")
    ResponseEntity<TaskResponse> get(
            @PathVariable UUID workspaceId,
            @PathVariable UUID taskId,
            Authentication auth,
            WebRequest request) {

        // Phải kiểm tra quyền ở service TRƯỚC khi đánh giá 304.
        TaskSnapshot task = service.get(
            workspaceId, taskId, auth.getName());
        String etag = TaskEtag.strong(task.id(), task.version());
        CacheControl cache = CacheControl.noCache().cachePrivate();

        if (request.checkNotModified(etag)) {
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                .eTag(etag).cacheControl(cache).build();
        }
        return ResponseEntity.ok()
            .eTag(etag).cacheControl(cache)
            .body(TaskResponse.from(task));
    }

    @PatchMapping(path = "/{taskId}",
                  consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<TaskResponse> rename(
            @PathVariable UUID workspaceId,
            @PathVariable UUID taskId,
            @Valid @RequestBody RenameTaskRequest body,
            @RequestHeader(name = "If-Match", required = false)
                String ifMatch,
            Authentication auth) {

        if (ifMatch == null || ifMatch.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.PRECONDITION_REQUIRED,
                "If-Match is required");
        }

        TaskIfMatch condition = TaskIfMatch.parse(ifMatch);
        TaskSnapshot renamed = service.rename(
            workspaceId, taskId, auth.getName(),
            body.title(), condition);
        return ResponseEntity.ok()
            .eTag(TaskEtag.strong(renamed.id(), renamed.version()))
            .body(TaskResponse.from(renamed));
    }
}
~~~

**Độ mỏng ở đây là trách nhiệm, không phải số dòng:** controller có mapping URI, @Valid, if header, Location, ETag, Cache-Control và status; nó **không tự truy vấn repository hoặc chạy nghiệp vụ**. Các thành phần helper được lược bỏ ở phần service cần có implementation riêng, đặc biệt parser **If-Match** đúng RFC và mapping lỗi.

### 7.1. Tại sao dùng 201, 200, 304 ở những vị trí này?

- **POST** tạo task trả **201 Created**, **Location** trỏ tới member URI và body mô tả resource mới.
- **GET** trả **200** với representation và ETag; conditional GET khớp có thể trả **304** không chứa response content. Đánh giá **authorization trước** khi trả 304, để cache không trở thành đường lộ dữ liệu.
- **PATCH** đã hoàn tất cập nhật trả **200** với body và ETag mới. Nếu API không cần body, có thể chọn **204**, nhưng phải công bố và không trả JSON trong 204.
- **If-Match** thiếu trả **428**, sai/stale trả **412** theo contract; không dùng 409 thay thế tự động mọi lỗi version. **409** thích hợp khi trạng thái ARCHIVED không cho đổi tên dù validator còn đúng.

### 7.2. URI và DTO là hợp đồng dài hạn

Không hardcode các đường dẫn trong nhiều lớp: **Location** có thể được dựng qua URI builder/reverse proxy-aware configuration để phản ánh base URL công khai, nhất là sau API gateway. Tương tự, **response DTO** có thể tiến hóa độc lập với thay đổi cột DB, nhưng việc đổi tên/xóa field công khai vẫn là thay đổi hợp đồng cần review, không tự coi là an toàn vì entity đã đổi.

## 8. Ánh xạ lỗi tập trung với Problem Details

Service ném exception nghiệp vụ; **@RestControllerAdvice** diễn giải chúng theo HTTP/RFC 9457. Ví dụ cho **stale version**:

~~~java
@RestControllerAdvice(assignableTypes = TaskController.class)
class TaskErrorAdvice {
    @ExceptionHandler(TaskPreconditionFailedException.class)
    ResponseEntity<ProblemDetail> stale(RuntimeException ignored) {
        ProblemDetail p = ProblemDetail.forStatus(
            HttpStatus.PRECONDITION_FAILED);
        p.setTitle("Precondition Failed");
        p.setDetail("Task đã thay đổi, hãy tải lại");
        p.setProperty("code", "STALE_TASK");
        return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
            .contentType(MediaType.valueOf("application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

Các domain exception **TaskPreconditionFailedException**, **TaskNotFoundException**, **TaskStateConflictException** là kiểu ứng dụng tự khai báo; tương ứng **412, 404, 409**. Lỗi optimistic lock từ @Version cần chuyển thành **412** ở use case PATCH có điều kiện này; **không** gán 412 cho mọi lỗi locking của mọi endpoint. **428** khi thiếu If-Match được controller phát hiện.

Các lỗi **@Valid/JSON parsing/UUID conversion** thường xuất hiện khi Spring MVC resolve argument; **401/403** có thể đến từ Security filter trước controller/advice. Nếu cần đồng nhất schema lỗi, cấu hình handler và **AuthenticationEntryPoint/AccessDeniedHandler** cho những lớp tương ứng. Không phản chiếu raw SQL, stack trace hoặc token vào Problem Details.

## 9. Bảo mật xuyên tầng: xác thực chưa đủ

Một client có thể thay **workspaceId** hoặc **taskId** trong URL. Mặc dù token hợp lệ, server vẫn phải bảo vệ tài nguyên đích:

- **Filter chain** xác thực token, xử lý 401/403 và quy tắc route-level.
- **Controller** nhận identity đã được xác minh; không tin **X-User-Id** hoặc **workspaceId** như bằng chứng quyền.
- **Service/WorkspaceAccessPolicy** kiểm tra caller có thể xem/sửa workspace và task. Nếu quy tắc yêu cầu owner, kiểm tra quyền trên chính task.
- **Repository** tìm theo **taskId + workspaceId** hoặc scope tin cậy, giúp hạn chế truy cập nhầm dữ liệu; không trả entity ở tenant khác.
- **DTO** chỉ trả trường hợp lệ với quyền hiện tại, không lộ internalNote, audit flags, owner credentials hay relationship không được phép.

Đừng dùng kiểm tra trong controller duy nhất: các luồng **scheduler, message consumer, command nội bộ** có thể gọi service mà không qua controller. Với multi-tenant phức tạp, có thể cần scope query theo tenant, row-level security, audit và test đổi identity liên tục.

Khi dùng browser với cookie/session, **CSRF protection** phải được thiết kế đúng; khi dùng bearer token, cần chống rò token, xác thực audience/scope và CORS hợp lý. **CORS không phải kiểm soát phân quyền**, và việc biết URL/UUID không cấp quyền truy cập.

## 10. Kiểm thử từng lớp, không kiểm tất cả bằng một mock

**@WebMvcTest(TaskController.class)** kiểm tra mapping, JSON, @Valid, status/headers và delegation với service mock (tùy phiên bản Spring Boot dùng @MockBean hoặc cơ chế mock bean hỗ trợ). Ví dụ trong test đã có MockMvc, Mockito và Spring Security Test:

~~~java
UUID workspaceId = UUID.randomUUID();
UUID taskId = UUID.randomUUID();
TaskSnapshot result = new TaskSnapshot(
    taskId, "Viết tài liệu", TaskStatus.OPEN, 0L);

when(service.create(
        eq(workspaceId), eq("Viết tài liệu"), eq("alice")))
    .thenReturn(result);

mockMvc.perform(post("/workspaces/{w}/tasks", workspaceId)
        .with(user("alice")).with(csrf())
        .contentType("application/json")
        .content("{\"title\":\"Viết tài liệu\"}"))
    .andExpect(status().isCreated())
    .andExpect(header().string("Location",
        "/workspaces/" + workspaceId + "/tasks/" + taskId))
    .andExpect(header().exists("ETag"))
    .andExpect(jsonPath("$.status").value("OPEN"));

mockMvc.perform(post("/workspaces/{w}/tasks", workspaceId)
        .with(user("alice")).with(csrf())
        .contentType("application/json")
        .content("{\"title\":\"\"}"))
    .andExpect(status().isBadRequest());

verify(service, times(1)).create(
    eq(workspaceId), eq("Viết tài liệu"), eq("alice"));
~~~

Các imports JUnit/Mockito/MockMvc được lược bỏ; đây là đoạn trong phương thức test. **@Valid phải chặn** body sai trước khi gọi service. Thêm test **GET ETag/304 không body**, PATCH thiếu If-Match **428**, stale **412** và lỗi có **Problem Details code** đúng.

| Lớp test | Điều cần chứng minh |
|---|---|
| **MVC** | 201/Location, request validation 400, 304/412/428, response DTO không lộ internal field |
| **Service** | Membership/role, task ARCHIVED không được rename, scope workspace và invariant |
| **Repository + DB** | @Version/unique/foreign key, query theo workspace, transaction và cập nhật đồng thời |
| **HTTP integration** | Token/tenant thực, serializer, error handler, cache headers, URI sau gateway |

Service unit test dùng fake/mocks có thể chứng minh quy tắc và delegation, **không thể chứng minh @Version hoạt động trong DB**. Để kiểm lost update, dùng database engine sát production với **hai transaction độc lập** và fixture đã commit; xác minh một cập nhật thắng, trạng thái cuối/version đúng. **@DataJpaTest** cho persistence; **@SpringBootTest(RANDOM_PORT)** cho HTTP end-to-end. Khi test có Security, cần CSRF/token theo cấu hình; @WithMockUser không thay thế kiểm thử credential production ở gateway.

## 11. Bài tập tái cấu trúc controller

Một API **POST /workspaces/{id}/tasks** đang nhận entity, query repository, kiểm role từ header tự khai, tính quota và gửi thông báo ngay trong controller.

**Yêu cầu:** (1) đề xuất **CreateTaskRequest/TaskResponse**, nói rõ field client không được sửa; (2) phân vai controller/service/repository/access policy; (3) chọn status khi tạo, title rỗng, thiếu quyền, vượt quota; (4) viết test 201+Location, 400, 403/404 và xung đột quota; (5) giải thích cách chống **hai request cùng vượt quota**.

**Gợi ý:** Controller nhận @Valid DTO và trusted principal; service kiểm quyền/quota và transaction; repository truy cập đúng scope; database cần ràng buộc hoặc conditional update/locking để giữ quota khi cạnh tranh. Trả **201** khi tạo; **400** input sai; **403/404** theo policy; quota nghiệp vụ có thể là **409/422**, còn **429** dành cho rate limiting. Kiểm tra **dữ liệu cuối**, không chỉ HTTP status.

## 12. Checklist và nguồn tham khảo

- [ ] Controller chỉ xử lý **HTTP adapter** và tạo status/header/representation; không chứa transaction/SQL/side effect.
- [ ] Service điều phối **use case, quyền, invariant, transaction**; không trả ResponseEntity hoặc phụ thuộc Servlet.
- [ ] Repository chỉ truy xuất dữ liệu theo scope, không quyết định business HTTP error.
- [ ] Request/response DTO tách entity; không chấp nhận field nhạy cảm hoặc vô tình lazy serialize.
- [ ] Validation biên và domain rules được tách; DB constraints bảo vệ race.
- [ ] POST/GET/PATCH trả 201/200/304/412/428 đúng hợp đồng, Location/ETag phù hợp.
- [ ] Authentication, workspace/tenant authorization và lỗi 401/403/404 có chính sách rõ.
- [ ] Optimistic locking, transaction commit và side effects được kiểm thử với DB thật khi cần.
- [ ] MockMvc/WebMvcTest, service tests và integration tests kiểm tra đúng trách nhiệm từng lớp.
- [ ] OpenAPI mô tả URI, DTO schema, status, error và header; không để ví dụ lệch runtime.

Tài liệu: [Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html); [Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/); [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html); [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/); [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110); [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457); [OpenAPI Specification](https://spec.openapis.org/oas/latest.html).

**Ghi nhớ:** Thiết kế controller mỏng là giữ **HTTP ở controller, use case và transaction ở service, dữ liệu ở repository, hợp đồng qua DTO**. Ranh giới đúng giúp API dễ thay đổi, an toàn trước dữ liệu không đáng tin và dễ kiểm thử hơn — không phải tạo nhiều lớp cho đẹp sơ đồ.
