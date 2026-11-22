# Cài đặt Java handler cho thao tác tạo, đọc và cập nhật công việc

Một Java serverless API cần biến HTTP request thành thao tác nghiệp vụ có kiểm soát: xác thực người gọi, xác định tenant và project, kiểm tra quyền, validate dữ liệu, đọc hoặc ghi database, rồi trả response theo API contract. Handler là điểm nối giữa giao thức HTTP và application service. Nếu handler tự làm tất cả, logic quyền truy cập, transaction và xử lý lỗi dễ bị lặp hoặc bỏ sót giữa các endpoint.

Bài học này xây dựng một lát cắt API quản lý task trong project. API hỗ trợ tạo task, đọc một task, liệt kê task và cập nhật task. Ví dụ sử dụng Java 17+, Spring Boot, Spring Security Resource Server, Bean Validation và PostgreSQL. Các nguyên tắc vẫn áp dụng khi HTTP function được triển khai qua API Gateway + Lambda hoặc một nền tảng serverless container như Cloud Run.

Trọng tâm là giữ handler mỏng, để application service điều phối use case, repository thực hiện tenant-scoped persistence, và policy kiểm tra quyền trên đúng resource. Mỗi request phải có actor context riêng; client không được tự gán tenant, creator, trạng thái nội bộ hoặc version. Các thao tác ghi cần transaction, optimistic locking và khả năng retry an toàn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Thiết kế HTTP contract cho create, read, list và update task.
- Tách controller/handler, application service, domain policy và repository.
- Lấy actor từ JWT đã xác thực và tenant từ request path đã được authorize.
- Dùng request/response DTO thay vì bind trực tiếp entity database.
- Validate input ở boundary và áp dụng business validation trong use case.
- Viết tenant-scoped SQL cho đọc và ghi task.
- Kiểm tra project membership, assignee và quyền OWNER/EDITOR/VIEWER.
- Dùng transaction và optimistic locking để tránh lost update.
- Chuẩn hóa HTTP status và Problem Details khi trả lỗi.
- Thiết kế POST retry bằng idempotency key và outbox khi cần event.
- Triển khai handler stateless trên Lambda hoặc serverless container.
- Kiểm thử API, authorization, persistence, retry và concurrency.

## 1. Phạm vi API và mô hình dữ liệu

Ta xây dựng API cho một task thuộc một project và tenant. Mô hình dữ liệu giả định đã có các bảng:

- `app_user`: ánh xạ identity provider bằng `issuer + subject`.
- `tenant_membership`: user, tenant, tenant role và membership status.
- `project`: project thuộc tenant.
- `project_member`: role và status của user trong project.
- `task`: task thuộc project và tenant.

Một task có các field chính:

| Field | Nguồn giá trị | Client được sửa? |
|---|---|---|
| `tenant_id` | Tenant đã authorize từ path | Không |
| `id` | Server tạo | Không |
| `project_id` | Project đã authorize từ path | Không |
| `title` | Request | Có |
| `description` | Request | Có |
| `owner_user_id` | Assignee sau khi kiểm tra membership | Qua action được phép |
| `created_by` | Actor từ JWT | Không |
| `status` | Server đặt OPEN khi tạo; policy khi cập nhật | Có giới hạn |
| `version` | Database tăng khi update | Không |
| `created_at`, `updated_at` | Server/database clock | Không |

Client có thể chọn assignee nếu actor có quyền và assignee là thành viên hợp lệ trong project. Client không được tự gửi tenant ID trong body để quyết định nơi ghi, hoặc gửi `created_by`, `version` hay trạng thái tùy ý.

### API routes

| Method | Path | Mục đích | Thành công |
|---|---|---|---|
| POST | `/v1/tenants/{tenantId}/projects/{projectId}/tasks` | Tạo task | 201 Created |
| GET | `/v1/tenants/{tenantId}/projects/{projectId}/tasks/{taskId}` | Đọc task | 200 OK |
| GET | `/v1/tenants/{tenantId}/projects/{projectId}/tasks` | Liệt kê task | 200 OK |
| PUT | `/v1/tenants/{tenantId}/projects/{projectId}/tasks/{taskId}` | Thay thế các field được phép sửa | 200 OK |

Dùng PUT cho ví dụ update để semantics rõ: client gửi đầy đủ tập field editable. Nếu dùng PATCH, cần quy định riêng cách phân biệt field bị bỏ qua với field được đặt thành null; không dùng một DTO nullable đơn giản rồi tự đoán ý định client.

### Sơ đồ request flow

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["JWT authentication"]
    B --> C["Resolve Actor from issuer + subject"]
    C --> D["Controller validates path and DTO"]
    D --> E["Application service / use case"]
    E --> F["Tenant + project authorization"]
    F --> G["Repository: tenant-scoped SQL"]
    G --> H["Database transaction"]
    H --> I["Response DTO + HTTP status"]
    I --> J["Client"]
~~~

Gateway có thể thực hiện một phần authentication, nhưng application service vẫn phải xác minh actor và object-level authorization theo chính sách của API. Không dựa vào việc frontend đã ẩn nút hoặc gateway đã xác thực token để bỏ qua kiểm tra quyền ở resource boundary.

## 2. Thiết kế request và response DTO

DTO là hợp đồng giữa client và API. DTO không phải entity JPA và không nên kế thừa persistence model.

### Request tạo task

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record CreateTaskRequest(
        @NotBlank
        @Size(max = 300)
        String title,

        @Size(max = 10000)
        String description,

        UUID assigneeUserId) {
}
~~~

Không có các field `tenantId`, `projectId`, `createdBy`, `status`, `version` hay timestamp. Tenant/project đến từ path sau khi authorization; creator đến từ actor; status ban đầu do server đặt là OPEN.

### Request cập nhật task

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record UpdateTaskRequest(
        @NotBlank
        @Size(max = 300)
        String title,

        @Size(max = 10000)
        String description,

        UUID assigneeUserId,

        @NotNull
        TaskStatus status,

        @NotNull
        Long expectedVersion) {
}
~~~

Trong ví dụ PUT, `description` và `assigneeUserId` có thể null để xóa mô tả hoặc bỏ assignee. Các field khác bắt buộc. `expectedVersion` giúp phát hiện update dựa trên dữ liệu cũ. Một API có thể thay version body bằng HTTP `If-Match`/ETag; không nhận cả hai nguồn version mâu thuẫn.

Enum trạng thái:

~~~java
public enum TaskStatus {
    OPEN,
    IN_PROGRESS,
    DONE,
    CANCELLED
}
~~~

Không cho client tự chuyển trạng thái nếu policy nghiệp vụ không cho phép. Ví dụ, chỉ OWNER/EDITOR mới được đổi status; VIEWER chỉ đọc. Nếu workflow có quy tắc chuyển trạng thái, domain policy phải kiểm tra transition hợp lệ, không chỉ kiểm tra enum thuộc danh sách.

### Response DTO

~~~java
import java.time.Instant;
import java.util.UUID;

public record TaskResponse(
        UUID id,
        UUID tenantId,
        UUID projectId,
        String title,
        String description,
        UUID assigneeUserId,
        UUID createdBy,
        TaskStatus status,
        long version,
        Instant createdAt,
        Instant updatedAt) {
}
~~~

Nếu một số field nhạy cảm chỉ dành cho role nhất định, tạo response view theo policy thay vì luôn trả tất cả. Không trả entity trực tiếp vì serializer có thể lộ quan hệ, internal IDs hoặc field chưa thuộc public API.

## 3. Actor context từ JWT đã xác thực

Controller không nên nhận `userId` từ request body hoặc query parameter. Actor được xây từ principal do Spring Security cung cấp sau khi JWT được xác minh.

Một mô hình nhỏ:

~~~java
import java.util.UUID;

public record Actor(UUID userId) {
}
~~~

Resolver ánh xạ cặp issuer/subject sang user nội bộ:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public class ActorResolver {
    private final UserRepository users;

    public ActorResolver(UserRepository users) {
        this.users = users;
    }

    public Actor resolve(Jwt jwt) {
        AppUser user = users.findByIssuerAndSubject(
                        jwt.getIssuer().toString(),
                        jwt.getSubject())
                .orElseThrow(UnknownUserException::new);

        if (!user.isActive()) {
            throw new AccountDisabledException();
        }
        return new Actor(user.id());
    }
}
~~~

Resource server cần cấu hình issuer/JWK và audience theo API contract. Không chỉ decode JWT payload rồi tin các claim. Với user bị suspend hoặc membership bị thu hồi, policy phải xác định thời điểm quyền có hiệu lực; token còn hạn không tự bảo đảm membership vẫn active.

Tenant ID trong URL là tenant mà client muốn thao tác. Use case phải xác minh actor có membership ACTIVE trong tenant đó và project thuộc tenant. Không coi path parameter là bằng chứng quyền.

## 4. Cấu hình Spring Security

Ví dụ cấu hình tối thiểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Cấu hình `issuer-uri` qua environment/config deployment. Bổ sung audience validator nếu decoder chưa kiểm tra `aud` đúng với resource server. Nếu dùng cookie/session browser thay vì bearer token, cần cấu hình CSRF theo mô hình xác thực; không tắt CSRF một cách máy móc cho mọi API.

Không đặt secret, database password hoặc private key trong source code. Function dùng workload identity/secret manager để truy cập dependency.

## 5. Controller/HTTP handler mỏng

Controller nhận HTTP request, trích path, validate DTO, resolve actor và gọi application service. Controller không tự viết SQL, không tự quyết định role và không publish event trực tiếp.

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/tenants/{tenantId}/projects/{projectId}/tasks")
public class TaskController {
    private final ActorResolver actors;
    private final TaskApplicationService tasks;

    public TaskController(
            ActorResolver actors,
            TaskApplicationService tasks) {
        this.actors = actors;
        this.tasks = tasks;
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @PathVariable UUID tenantId,
            @PathVariable UUID projectId,
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody CreateTaskRequest request) {

        Actor actor = actors.resolve(jwt);
        TaskResponse created = tasks.create(
                actor, tenantId, projectId, request);

        URI location = URI.create(
                "/v1/tenants/" + tenantId
                + "/projects/" + projectId
                + "/tasks/" + created.id());

        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{taskId}")
    public ResponseEntity<TaskResponse> get(
            @PathVariable UUID tenantId,
            @PathVariable UUID projectId,
            @PathVariable UUID taskId,
            @AuthenticationPrincipal Jwt jwt) {

        Actor actor = actors.resolve(jwt);
        return ResponseEntity.ok(
                tasks.get(actor, tenantId, projectId, taskId));
    }

    @GetMapping
    public ResponseEntity<TaskPage> list(
            @PathVariable UUID tenantId,
            @PathVariable UUID projectId,
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "50") int pageSize,
            @RequestParam(required = false) String cursor) {

        Actor actor = actors.resolve(jwt);
        return ResponseEntity.ok(
                tasks.list(actor, tenantId, projectId, pageSize, cursor));
    }

    @PutMapping("/{taskId}")
    public ResponseEntity<TaskResponse> update(
            @PathVariable UUID tenantId,
            @PathVariable UUID projectId,
            @PathVariable UUID taskId,
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody UpdateTaskRequest request) {

        Actor actor = actors.resolve(jwt);
        return ResponseEntity.ok(
                tasks.update(actor, tenantId, projectId, taskId, request));
    }
}
~~~

Đoạn code thể hiện các handler create, read, list và update. Với API serverless, controller vẫn là adapter HTTP. Business use case không phụ thuộc API Gateway event class hoặc loại runtime.

### Validation tại boundary

Bean Validation kiểm tra cấu trúc request:
- title không rỗng và giới hạn độ dài.
- description có giới hạn.
- status phải là enum hợp lệ.
- expectedVersion phải có.

Business validation vẫn cần ở application/domain layer:
- Project tồn tại và ACTIVE.
- Actor có quyền.
- Assignee là project member ACTIVE.
- Status transition hợp lệ.
- Task nằm trong đúng tenant/project.

Validation không thay thế authorization. Một request hoàn toàn hợp lệ về cú pháp vẫn có thể không được phép.

## 6. Application service cho create, read và update

Application service điều phối use case. Nó kiểm tra quyền, gọi repository và áp dụng domain policy. Các method ghi dùng transaction để giữ thay đổi nhất quán.

Interface repository:

~~~java
import java.util.Optional;
import java.util.UUID;

public interface TaskRepository {
    Task insert(NewTask task);

    Optional<Task> findByTenantProjectAndId(
            UUID tenantId, UUID projectId, UUID taskId);

    TaskPageData findPage(
            UUID tenantId, UUID projectId, int pageSize, String cursor);

    int updateEditableFields(
            UUID tenantId,
            UUID projectId,
            UUID taskId,
            long expectedVersion,
            TaskChanges changes);
}
~~~

Các port quyền truy cập:

~~~java
import java.util.UUID;

public interface ProjectAccess {
    ProjectAccessSnapshot requireCanRead(
            Actor actor, UUID tenantId, UUID projectId);

    ProjectAccessSnapshot requireCanCreateTask(
            Actor actor, UUID tenantId, UUID projectId);

    ProjectAccessSnapshot requireCanEditTask(
            Actor actor, UUID tenantId, UUID projectId);
}

public interface AssigneeAccess {
    void requireActiveProjectMember(
            UUID tenantId, UUID projectId, UUID assigneeUserId);
}
~~~

`ProjectAccessSnapshot` có thể chứa tenant role, project role và trạng thái project đã đọc từ database. Không lấy role từ request. Repository/adapter phải kiểm tra tenant trong mọi truy vấn.

### Domain model và command

~~~java
import java.time.Instant;
import java.util.UUID;

public record NewTask(
        UUID tenantId,
        UUID id,
        UUID projectId,
        String title,
        String description,
        UUID assigneeUserId,
        UUID createdBy,
        TaskStatus status,
        Instant createdAt) {
}

public record TaskChanges(
        String title,
        String description,
        UUID assigneeUserId,
        TaskStatus status) {
}

public record TaskPageData(
        java.util.List<Task> items,
        String nextCursor) {
}
~~~

Tách command/domain model khỏi HTTP DTO giúp application service không phụ thuộc annotation của Spring MVC hoặc JSON serialization.

### Create use case

~~~java
import java.time.Clock;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskApplicationService {
    private final TaskRepository tasks;
    private final ProjectAccess access;
    private final AssigneeAccess assignees;
    private final TaskPolicy policy;
    private final Clock clock;
    private final TaskEventOutbox outbox;

    public TaskApplicationService(
            TaskRepository tasks,
            ProjectAccess access,
            AssigneeAccess assignees,
            TaskPolicy policy,
            Clock clock,
            TaskEventOutbox outbox) {
        this.tasks = tasks;
        this.access = access;
        this.assignees = assignees;
        this.policy = policy;
        this.clock = clock;
        this.outbox = outbox;
    }

    @Transactional
    public TaskResponse create(
            Actor actor,
            UUID tenantId,
            UUID projectId,
            CreateTaskRequest request) {

        access.requireCanCreateTask(actor, tenantId, projectId);

        if (request.assigneeUserId() != null) {
            assignees.requireActiveProjectMember(
                    tenantId, projectId, request.assigneeUserId());
        }

        NewTask command = new NewTask(
                tenantId,
                UUID.randomUUID(),
                projectId,
                request.title().trim(),
                request.description(),
                request.assigneeUserId(),
                actor.userId(),
                TaskStatus.OPEN,
                clock.instant());

        Task created = tasks.insert(command);
        outbox.append(TaskCreatedEvent.from(created));

        return TaskResponse.from(created);
    }

    // Read and update methods follow below.
}
~~~

Constructor injection giúp dependency rõ và dễ test. Trong production, ID generator có thể được inject để deterministic testing. Event được ghi vào outbox cùng transaction; worker publish sau commit. Không gọi broker hoặc external API đồng bộ bên trong database transaction rồi giả định hai hệ thống commit nguyên tử.

### Read use case

~~~java
@Transactional(readOnly = true)
public TaskResponse get(
        Actor actor,
        UUID tenantId,
        UUID projectId,
        UUID taskId) {

    ProjectAccessSnapshot permission =
            access.requireCanRead(actor, tenantId, projectId);

    Task task = tasks.findByTenantProjectAndId(
                    tenantId, projectId, taskId)
            .orElseThrow(TaskNotFoundException::new);

    if (!policy.canReadTask(permission, task)) {
        throw new TaskNotFoundException();
    }
    return TaskResponse.from(task);
}
~~~

Query đã scope tenant, project và task. Policy kiểm tra thêm trạng thái/ownership nếu cần. Trả 404 cho resource ngoài phạm vi là một lựa chọn giúp giảm enumeration; API phải áp dụng nhất quán.

### Update use case

~~~java
@Transactional
public TaskResponse update(
        Actor actor,
        UUID tenantId,
        UUID projectId,
        UUID taskId,
        UpdateTaskRequest request) {

    ProjectAccessSnapshot permission =
            access.requireCanEditTask(actor, tenantId, projectId);

    Task current = tasks.findByTenantProjectAndId(
                    tenantId, projectId, taskId)
            .orElseThrow(TaskNotFoundException::new);

    if (current.version() != request.expectedVersion()) {
        throw new StaleTaskVersionException();
    }

    if (request.assigneeUserId() != null) {
        assignees.requireActiveProjectMember(
                tenantId, projectId, request.assigneeUserId());
    }

    TaskChanges changes = new TaskChanges(
            request.title().trim(),
            request.description(),
            request.assigneeUserId(),
            request.status());

    policy.requireAllowedTransition(permission, current, changes);

    int updated = tasks.updateEditableFields(
            tenantId,
            projectId,
            taskId,
            request.expectedVersion(),
            changes);

    if (updated == 0) {
        throw new StaleTaskVersionException();
    }

    Task saved = tasks.findByTenantProjectAndId(
                    tenantId, projectId, taskId)
            .orElseThrow(TaskNotFoundException::new);

    outbox.append(TaskUpdatedEvent.from(saved));
    return TaskResponse.from(saved);
}
~~~

Update có hai lớp bảo vệ version: so sánh version đã đọc và điều kiện version trong SQL update. Nếu hai request cùng đọc version 4, chỉ một request update thành version 5; request còn lại update count 0 và nhận conflict. Việc check membership/role và write nên được thực hiện trong transaction; với policy có thể bị thu hồi đồng thời, cân nhắc khóa row membership hoặc đưa predicate authorization vào câu UPDATE để thu hẹp race window.

Trong ví dụ PUT, `assigneeUserId = null` nghĩa là bỏ gán task. Nếu API cần phân biệt “không gửi field” với “gửi null”, dùng PATCH DTO có presence wrapper như `JsonNullable<T>` hoặc một command patch rõ ràng.

## 7. Repository: mọi query phải có tenant scope

Repository là lớp persistence, không phải nơi nhận quyền từ client. Method signature nên bắt buộc tenant ID để giảm khả năng query theo ID toàn cục mà quên tenant.

### Insert task

Một insert có thể dùng named parameters:

~~~sql
INSERT INTO task (
    tenant_id, id, project_id, title, description,
    owner_user_id, created_by, status, version,
    created_at, updated_at
)
VALUES (
    :tenant_id, :id, :project_id, :title, :description,
    :owner_user_id, :created_by, :status, 0,
    :created_at, :created_at
)
RETURNING tenant_id, id, project_id, title, description,
          owner_user_id, created_by, status, version,
          created_at, updated_at;
~~~

Trước insert, application service đã kiểm tra quyền và assignee. Với yêu cầu concurrency/revocation chặt, adapter có thể thực hiện authorization predicate và insert trong cùng SQL/transaction hoặc khóa các row membership/project cần thiết. Composite foreign key bảo vệ tenant consistency, nhưng không tự bảo đảm project membership đang ACTIVE.

### Read task

~~~sql
SELECT tenant_id, id, project_id, title, description,
       owner_user_id, created_by, status, version,
       created_at, updated_at
FROM task
WHERE tenant_id = :tenant_id
  AND project_id = :project_id
  AND id = :task_id;
~~~

Không tạo method `findById(taskId)` cho endpoint tenant-owned nếu không có một lớp bắt buộc bổ sung tenant authorization. Truy vấn theo ba khóa giúp giảm nhầm lẫn và làm intent rõ.

### Update task có optimistic locking

~~~sql
UPDATE task
SET title = :title,
    description = :description,
    owner_user_id = :owner_user_id,
    status = :status,
    version = version + 1,
    updated_at = :updated_at
WHERE tenant_id = :tenant_id
  AND project_id = :project_id
  AND id = :task_id
  AND version = :expected_version;
~~~

Query này bảo vệ tenant/project và version. Adapter cần đảm bảo authorization được kiểm tra trong cùng transaction hoặc được đưa vào predicate của update. Nếu cần ngăn update sau khi membership bị thu hồi đồng thời, thêm EXISTS kiểm tra membership ACTIVE và role, hoặc khóa row membership phù hợp.

### Cập nhật assignee phải kiểm tra project membership

Foreign key có thể bảo đảm assignee thuộc tenant, nhưng không bảo đảm user tham gia project. Trước khi gán:
- User tồn tại và active.
- Tenant membership ACTIVE.
- Project membership ACTIVE.
- Policy cho phép actor assign người khác.
- Project/task chưa ở trạng thái cấm assignment.

Nếu user bị remove khỏi project sau khi task đã được gán, cần policy rõ: giữ assignment lịch sử, tự động bỏ gán, hay chuyển sang owner khác. Không xóa task chỉ vì membership bị thu hồi.

## 8. Authorization policy cho task

Một policy đơn giản:

~~~java
public final class TaskPolicy {
    public boolean canReadTask(
            ProjectAccessSnapshot access,
            Task task) {
        return access.tenantActive()
                && access.projectActive()
                && (access.tenantAdmin()
                    || access.projectRole().canRead());
    }

    public void requireAllowedTransition(
            ProjectAccessSnapshot access,
            Task current,
            TaskChanges changes) {

        if (!access.tenantAdmin()
                && !access.projectRole().canEdit()) {
            throw new TaskAccessDeniedException();
        }

        if (current.status() == TaskStatus.CANCELLED
                && changes.status() != TaskStatus.CANCELLED) {
            throw new InvalidTaskTransitionException();
        }
    }
}
~~~

Đây là ví dụ minh họa; domain thật cần quy tắc transition rõ hơn. Ví dụ, task DONE có thể được reopen bởi OWNER nhưng không bởi EDITOR; hoặc chỉ người được giao mới được cập nhật estimate. Đưa những quyết định này vào policy có tên rõ ràng thay vì viết điều kiện role rải rác trong controller.

Default deny: nếu policy không xác định được quyền, từ chối. Không dùng role mặc định MEMBER hoặc VIEWER khi dữ liệu membership thiếu.

## 9. List tasks và pagination

Endpoint list cần tenant/project scope và membership giống endpoint detail. Không lấy tất cả task rồi lọc ở Java vì điều đó tốn memory, có thể lộ dữ liệu qua bug và làm pagination sai.

Ví dụ keyset pagination:

~~~sql
SELECT t.id, t.title, t.description, t.owner_user_id,
       t.created_by, t.status, t.version, t.created_at, t.updated_at
FROM task t
WHERE t.tenant_id = :tenant_id
  AND t.project_id = :project_id
  AND (
      :cursor_created_at IS NULL
      OR (t.created_at, t.id) < (:cursor_created_at, :cursor_id)
  )
ORDER BY t.created_at DESC, t.id DESC
LIMIT :page_size;
~~~

Trước khi query, application service phải authorize actor trên project. Cursor cần encode hoặc ký các thành phần sort/filter/tenant phù hợp để không thể dùng cursor sai context. Giới hạn page size, ví dụ tối đa 100. Không dùng page size do client gửi mà không kiểm tra.

Response:

~~~java
import java.util.List;

public record TaskPage(
        List<TaskResponse> items,
        String nextCursor) {
}
~~~

Application service authorize project trước khi repository đọc page và giới hạn page size:

~~~java
@Transactional(readOnly = true)
public TaskPage list(
        Actor actor,
        UUID tenantId,
        UUID projectId,
        int requestedPageSize,
        String cursor) {

    access.requireCanRead(actor, tenantId, projectId);
    int pageSize = Math.min(Math.max(requestedPageSize, 1), 100);
    TaskPageData page = tasks.findPage(
            tenantId, projectId, pageSize, cursor);

    return new TaskPage(
            page.items().stream().map(TaskResponse::from).toList(),
            page.nextCursor());
}
~~~

Repository adapter phải giải mã và kiểm tra cursor theo tenant/project/filter hiện tại, rồi dùng truy vấn có tenant/project predicate như ví dụ SQL bên dưới. Không tin cursor do client gửi nếu nó không được xác thực hoặc không khớp query context.

Với dữ liệu thay đổi liên tục, keyset pagination thường ổn định hơn offset pagination. Nếu cần snapshot pagination nhất quán qua nhiều trang, phải thiết kế watermark/snapshot semantics riêng.

## 10. Transaction, outbox và idempotency cho POST

Client có thể timeout sau khi task đã được tạo nhưng trước khi nhận response. Nếu client gửi lại POST, server có thể tạo task thứ hai trừ khi có idempotency policy.

Với endpoint create có side effect quan trọng:
- Client gửi `Idempotency-Key` ổn định cho một thao tác logic.
- Server scope key theo tenant và operation.
- Lưu request fingerprint để phát hiện cùng key nhưng payload khác.
- Ghi task, idempotency result và outbox event trong cùng transaction.
- Retry cùng key trả lại kết quả đã lưu.
- Key được giữ đủ lâu để bao phủ client retry và các retry/replay được hỗ trợ.

Không dùng key mới khi retry cùng thao tác. Không dùng in-memory map làm nguồn idempotency trong serverless vì invocation khác có thể chạy trên instance khác.

Outbox bảo đảm task và event được ghi cùng transaction database. Worker publish event có thể retry; event ID phải ổn định và consumer cần idempotent. Không gọi broker rồi mới commit task và giả định cả hai thao tác luôn thành công cùng nhau.

## 11. Xử lý lỗi và HTTP Problem Details

API nên trả lỗi có cấu trúc, không trả stack trace hoặc SQL.

| Tình huống | HTTP status thường dùng |
|---|---:|
| JWT thiếu, sai chữ ký, hết hạn hoặc audience không hợp lệ | 401 |
| Actor hợp lệ nhưng bị từ chối quyền | 403 hoặc 404 theo anti-enumeration policy |
| Resource không tồn tại trong tenant/project | 404 |
| Request DTO không hợp lệ | 400 |
| Business rule/transition không hợp lệ | 422 hoặc 409 theo contract |
| Version đã cũ | 409 Conflict hoặc 412 Precondition Failed nếu dùng If-Match |
| Idempotency key trùng nhưng fingerprint khác | 409 |
| Database/dependency tạm thời lỗi | 503 nếu request không thể xử lý |

Spring hỗ trợ Problem Details. Ví dụ exception handler:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(TaskNotFoundException.class)
    ProblemDetail notFound(TaskNotFoundException error) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Task was not found");
    }

    @ExceptionHandler(TaskAccessDeniedException.class)
    ProblemDetail forbidden(TaskAccessDeniedException error) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.FORBIDDEN, "Action is not permitted");
    }

    @ExceptionHandler(StaleTaskVersionException.class)
    ProblemDetail conflict(StaleTaskVersionException error) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT, "Task was changed by another request");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail invalid(MethodArgumentNotValidException error) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, "Request validation failed");
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ProblemDetail unreadable(HttpMessageNotReadableException error) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, "Request body is malformed or has an invalid value");
    }
}
~~~

Trong ứng dụng thật, bổ sung error code ổn định, correlation/trace ID và danh sách field validation đã được lọc. Không đưa exception message nội bộ hoặc SQL vào response. Các lỗi authentication từ security filter cần được cấu hình entry point/denied handler riêng để trả Problem Details nhất quán.

## 12. ETag và If-Match cho update

Version có thể được biểu diễn thành ETag:

~~~http
HTTP/1.1 200 OK
ETag: "task-v7"
Content-Type: application/json
~~~

Client gửi:

~~~http
PUT /v1/tenants/t1/projects/p1/tasks/k1
If-Match: "task-v7"
~~~

Nếu resource đã lên version 8, server trả `412 Precondition Failed`. Điều này giúp client tránh ghi đè thay đổi của người khác.

Nếu dùng ETag:
- Tạo ETag từ version server-side.
- Parse `If-Match` theo grammar HTTP; không so sánh chuỗi tùy tiện.
- Dùng version trong điều kiện UPDATE SQL.
- Trả ETag mới sau update thành công.
- Quy định hành vi khi client không gửi If-Match; với resource cần concurrency control, có thể bắt buộc.

Không dùng ETag làm quyền truy cập. Người dùng vẫn phải qua authorization dù họ biết version chính xác.

## 13. Serverless HTTP adapter: Lambda và container

Application service không nên phụ thuộc vào loại compute. Chỉ HTTP adapter thay đổi theo nền tảng.

### API Gateway + Lambda

Một API Gateway HTTP API có thể chuyển request đến Java Lambda thông qua adapter tương thích. Adapter chuyển method, path, headers, body và request context thành request mà ứng dụng xử lý. Cần xác định rõ nơi xác thực token:
- Gateway authorizer có thể xác minh JWT và chuyển claims đã xác thực.
- Hoặc ứng dụng Spring Resource Server tự xác minh bearer token.
- Nếu gateway inject principal headers, phải chặn header giả từ client và bảo vệ đường kết nối nội bộ.

Không tạo một handler riêng cho mỗi business use case chỉ để phân biệt route; router/controller có thể dispatch nhiều route đến cùng application service. Giữ logic use case độc lập để có thể gọi từ HTTP, queue consumer hoặc test.

### Serverless container

Với Cloud Run hoặc nền tảng container serverless, ứng dụng có thể chạy Spring Boot embedded server. Platform nhận HTTP và route đến instance. Application service vẫn stateless; không lưu actor, tenant hoặc transaction state trong static mutable field giữa request.

### Những điểm cần kiểm tra khi deploy

- Runtime Java và memory/CPU phù hợp.
- Handler/adapter entry point đúng với nền tảng.
- Request/response size limit và timeout.
- Database connection pooling theo max instance/concurrency.
- Environment variables chỉ chứa config không nhạy cảm.
- Secret lấy qua secret manager/workload identity.
- Health/readiness endpoint không lộ thông tin nội bộ.
- Logs có request/trace ID nhưng không có token/payload nhạy cảm.
- IAM chỉ cấp quyền tối thiểu cho function.

## 14. Stateless handler và connection lifecycle

Serverless platform có thể tái sử dụng một execution environment. Có thể tái sử dụng dependency thread-safe như HTTP client hoặc connection pool được cấu hình phù hợp, nhưng không giữ request-specific state ở field mutable.

An toàn:
- Singleton service không chứa actor/tenant của request.
- Mỗi invocation truyền Actor, tenantId và request data qua method parameter.
- Transaction được mở/đóng theo use case.
- JDBC connection được quản lý bởi pool/framework và trả về pool sau transaction.
- Cache chỉ lưu dữ liệu có policy TTL/invalidation rõ.

Không an toàn:
- Static `currentUserId`.
- Static `currentTenantId`.
- Giữ Connection hoặc EntityManager sau request.
- ThreadLocal không clear.
- Lưu idempotency key trong RAM rồi coi là durable.
- Tạo một thread background không được platform quản lý để tiếp tục request sau khi response trả về.

Với async processing, publish message/outbox và để một function khác xử lý. Không trả HTTP response rồi kỳ vọng process nền trong cùng invocation luôn được chạy đến hết sau khi platform đóng request context.

## 15. Database connection và concurrency

Nếu platform scale lên nhiều instance, mỗi instance có thể mở pool connection. Một ước lượng upper bound:

~~~text
potential database connections
  ≈ max active instances × pool size per instance
    + connections from other workloads
~~~

Pool size phải tính cùng max instances, concurrency, database connection limit và connection proxy. Pool quá lớn có thể làm database cạn connection khi scale-out; pool quá nhỏ làm request chờ lâu.

Với mỗi handler:
- Dùng prepared statement/parameter binding.
- Đặt query timeout và transaction timeout phù hợp.
- Không giữ transaction trong lúc gọi API ngoài.
- Tránh N+1 query cho task list.
- Giới hạn page size.
- Dùng index theo tenant/project và sort key.
- Theo dõi connection acquisition time, query latency và pool saturation.

Không tăng max instances vô hạn để chữa latency nếu database đã là bottleneck. Scale compute phải đi cùng capacity của database và dependency.

## 16. Audit, event và side effects

Create/update task có thể cần phát event để notification hoặc activity feed. Ghi event vào outbox cùng transaction với task:

~~~sql
INSERT INTO outbox_event (
    event_id, aggregate_type, aggregate_id,
    event_type, payload, created_at
)
VALUES (
    :event_id, 'Task', :task_id,
    'TaskCreated', :payload, now()
);
~~~

Payload event nên chứa metadata nghiệp vụ cần thiết:
- event ID ổn định.
- tenant ID.
- task/project ID.
- actor nội bộ.
- event type và schema version.
- occurred time.
- business data tối thiểu.

Không gửi raw JWT, password hoặc secret trong event. Consumer xác minh producer/workload identity và áp dụng idempotency bằng event ID. Nếu event đại diện hành động thay mặt user, giữ actor gốc để audit nhưng không dùng metadata actor làm credential.

## 17. Kiểm thử handler và use case

Kiểm thử theo tầng:

| Tầng | Điều cần xác minh |
|---|---|
| DTO validation | title rỗng/quá dài, status thiếu, version sai |
| Policy unit test | viewer không sửa; editor sửa; membership inactive bị từ chối |
| Application service test | create gán actor/status đúng; read scope tenant; update kiểm tra transition |
| Repository integration | query có tenant/project predicate; optimistic update chỉ một request thành công |
| Controller test | status, Location, JSON response và validation errors |
| Security integration | JWT issuer/audience/expiry; unauthenticated request bị chặn |
| End-to-end | POST → GET → PUT → GET phản ánh dữ liệu mới |
| Serverless adapter test | mapping path/header/body/claim và timeout behavior |

### Unit test create use case

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class TaskApplicationServiceTest {
    @Test
    void createUsesActorAndServerOwnedFields() {
        TaskRepository tasks = mock(TaskRepository.class);
        ProjectAccess access = mock(ProjectAccess.class);
        AssigneeAccess assignees = mock(AssigneeAccess.class);
        TaskPolicy policy = new TaskPolicy();
        TaskEventOutbox outbox = mock(TaskEventOutbox.class);

        UUID tenantId = UUID.randomUUID();
        UUID projectId = UUID.randomUUID();
        UUID userId = UUID.randomUUID();
        Actor actor = new Actor(userId);

        when(tasks.insert(any(NewTask.class))).thenAnswer(invocation -> {
            NewTask value = invocation.getArgument(0);
            return Task.from(value);
        });

        TaskApplicationService service = new TaskApplicationService(
                tasks, access, assignees, policy,
                Clock.fixed(
                        Instant.parse("2026-11-17T10:00:00Z"),
                        ZoneOffset.UTC),
                outbox);

        TaskResponse response = service.create(
                actor,
                tenantId,
                projectId,
                new CreateTaskRequest("  Review release  ", null, null));

        assertEquals(userId, response.createdBy());
        assertEquals(tenantId, response.tenantId());
        assertEquals(projectId, response.projectId());
        assertEquals("Review release", response.title());
        assertEquals(TaskStatus.OPEN, response.status());
        verify(access).requireCanCreateTask(actor, tenantId, projectId);
        verify(outbox).append(any(TaskCreatedEvent.class));
    }
}
~~~

Các factory `Task.from` và event factory là thành phần domain của ví dụ. Trong test thật, kiểm tra thêm task ID, version ban đầu và timestamp. Không viết test chỉ xác nhận mock trả lại đúng giá trị do test tự cấu hình.

### Integration test optimistic locking

Tạo task version 3. Gửi hai update đồng thời cùng expectedVersion=3:
- Một update thành công và version thành 4.
- Update còn lại có affected rows = 0 và nhận conflict.
- Dữ liệu không bị ghi đè bởi request đến sau dựa trên version cũ.

Chạy test trên database thật hoặc Testcontainers để xác minh unique/locking/transaction semantics. Mock repository không chứng minh concurrency của SQL.

### Cross-tenant tests

- Actor thuộc tenant A không đọc task tenant B.
- Project ID đúng nhưng tenant path sai không trả dữ liệu.
- Viewer không tạo/update task.
- Editor không tự gán assignee ngoài project.
- User bị remove khỏi project không còn quyền.
- Client gửi `createdBy`, `tenantId`, `status` trong JSON không thể mass-assign field.
- Cursor tenant A không dùng để truy vấn tenant B.

## 18. Observability cho handler

Structured log nên có:
- trace/request ID.
- route template và HTTP method.
- tenant ID đã mask hoặc định danh nội bộ phù hợp policy.
- actor ID theo chính sách log.
- task ID khi cần điều tra.
- status code, duration và error category.
- deployment revision.

Không log bearer token, cookie, secret, raw request body hoặc description có thể chứa dữ liệu cá nhân. Không đưa tenant ID, user ID hoặc task ID có cardinality cao vào metric labels. Metrics nên dùng operation/outcome/status class.

Các metric hữu ích:
- `task_api_requests_total` theo operation/outcome.
- `task_api_duration` histogram.
- `task_create_conflicts_total`.
- `task_update_version_conflicts_total`.
- `task_authorization_denied_total`.
- `database_connection_acquire_duration`.
- `outbox_oldest_unpublished_age`.

Trace root span cho HTTP request và child spans cho authorization query, task repository và outbox insert. Không gọi external broker trong request transaction nếu có thể dùng outbox.

## 19. Ví dụ gọi API

Tạo task (các UUID trong ví dụ là giá trị minh họa hợp lệ):

~~~http
POST /v1/tenants/7d3e6b54-1a2b-4c3d-8e9f-001122334455/projects/2a1f0b6c-7d8e-4f90-a123-456789abcdef/tasks HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "title": "Review serverless release",
  "description": "Check alarms and rollback plan",
  "assigneeUserId": "d44e1234-5678-4abc-9def-0123456789ab"
}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Location: /v1/tenants/7d3e6b54-1a2b-4c3d-8e9f-001122334455/projects/2a1f0b6c-7d8e-4f90-a123-456789abcdef/tasks/9bcf1234-5678-4abc-9def-0123456789ab
Content-Type: application/json
~~~

~~~json
{
  "id": "9bcf1234-5678-4abc-9def-0123456789ab",
  "tenantId": "7d3e6b54-1a2b-4c3d-8e9f-001122334455",
  "projectId": "2a1f0b6c-7d8e-4f90-a123-456789abcdef",
  "title": "Review serverless release",
  "description": "Check alarms and rollback plan",
  "assigneeUserId": "d44e1234-5678-4abc-9def-0123456789ab",
  "createdBy": "a12b1234-5678-4abc-9def-0123456789ab",
  "status": "OPEN",
  "version": 0,
  "createdAt": "2026-11-17T10:00:00Z",
  "updatedAt": "2026-11-17T10:00:00Z"
}
~~~

Đọc task:

~~~http
GET /v1/tenants/7d3e6b54-1a2b-4c3d-8e9f-001122334455/projects/2a1f0b6c-7d8e-4f90-a123-456789abcdef/tasks/9bcf1234-5678-4abc-9def-0123456789ab
Authorization: Bearer <access-token>
~~~

Cập nhật task bằng version:

~~~http
PUT /v1/tenants/7d3e6b54-1a2b-4c3d-8e9f-001122334455/projects/2a1f0b6c-7d8e-4f90-a123-456789abcdef/tasks/9bcf1234-5678-4abc-9def-0123456789ab
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "title": "Review serverless release",
  "description": "Review completed",
  "assigneeUserId": null,
  "status": "DONE",
  "expectedVersion": 0
}
~~~

Sau update thành công, server trả version 1. Nếu client gửi lại version 0, server trả conflict/precondition failure theo contract. Mọi request đều cần token hợp lệ và quyền trên đúng tenant/project/task.

## 20. Checklist triển khai Java task handlers

- [ ] Route/method/path được định nghĩa và version hóa.
- [ ] Request DTO chỉ chứa field client được phép gửi.
- [ ] Bean Validation kiểm tra input ở HTTP boundary.
- [ ] Actor được resolve từ JWT đã xác thực, issuer + subject.
- [ ] Audience của token được kiểm tra theo API.
- [ ] Tenant membership và project membership được xác minh hiện hành.
- [ ] Mọi repository method bắt buộc tenant/project scope.
- [ ] Create tự gán ID, tenant, creator, status và timestamps phía server.
- [ ] Assignee được kiểm tra là active project member.
- [ ] Read áp dụng object-level authorization và DTO projection.
- [ ] Update dùng allowlist field và domain transition policy.
- [ ] Optimistic locking/If-Match ngăn lost update.
- [ ] Transaction bao trùm business write và outbox record.
- [ ] POST có idempotency strategy nếu retry có thể tạo duplicate.
- [ ] Error mapping không lộ SQL, stack trace hoặc resource ngoài tenant.
- [ ] Function stateless; không lưu actor/tenant trong mutable static state.
- [ ] Connection pool được tính theo max instances/concurrency.
- [ ] Secret và database access dùng workload identity/secret manager.
- [ ] Có unit, controller, repository, security và concurrency tests.
- [ ] Logs/metrics/traces không chứa token hoặc dữ liệu nhạy cảm.

## Tự kiểm tra

1. Vì sao controller không nên chứa SQL và business authorization?
2. Tenant ID và creator ID nên được lấy từ đâu?
3. DTO tạo task nên loại bỏ những field nào để tránh mass assignment?
4. Khác biệt giữa PUT và PATCH trong việc xử lý field null là gì?
5. Vì sao repository method nên nhận tenantId và projectId cùng taskId?
6. Assignee thuộc tenant có đủ điều kiện để được gán vào project không?
7. Optimistic locking giải quyết lost update như thế nào?
8. Vì sao update phải kiểm tra affected row count?
9. Transactional outbox bảo vệ tính nhất quán giữa task và event ra sao?
10. Idempotency key cần được giữ như thế nào khi client retry POST?
11. Vì sao không giữ actor hoặc tenant trong static field của Lambda/container?
12. Database connection budget liên hệ thế nào với max instances và pool size?
13. Khi nào API nên trả 404 thay vì 403?
14. Những integration test nào chứng minh handler không cho truy cập chéo tenant?

Một Java serverless handler tốt làm ít việc ở lớp HTTP: nhận request, xác thực principal, validate DTO và gọi use case. Application service quyết định quyền và điều phối nghiệp vụ; repository giới hạn tenant/project và bảo vệ concurrency; database transaction cùng outbox giữ thay đổi nhất quán. Khi function được scale hoặc tái sử dụng, thiết kế stateless, idempotency, connection budget và authorization theo từng object giúp API tạo, đọc và cập nhật task an toàn.

