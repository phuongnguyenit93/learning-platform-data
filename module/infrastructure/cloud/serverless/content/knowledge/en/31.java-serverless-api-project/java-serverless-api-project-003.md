# Implementing Java Handlers for Creating, Reading, and Updating Tasks

A Java serverless API must turn an HTTP request into a controlled business operation: authenticate the caller, identify the tenant and project, check permissions, validate data, read or write the database, and return a response matching the API contract. The handler bridges the HTTP protocol and the application service. If the handler does everything itself, access control, transactions, and error handling are easily duplicated or missed across endpoints.

This lesson builds a vertical slice of a task management API within a project. The API supports creating a task, reading a task, listing tasks, and updating a task. Examples use Java 17+, Spring Boot, Spring Security Resource Server, Bean Validation, and PostgreSQL. The same principles apply whether the HTTP function is deployed behind API Gateway + Lambda or on a serverless container platform like Cloud Run.

The emphasis is on keeping handlers thin, letting application services orchestrate use cases, having repositories perform tenant-scoped persistence, and having policies check permissions on the exact target resource. Every request must have its own actor context; clients must never supply tenant, creator, internal status, or version fields. Write operations require transactions, optimistic locking, and safe retry semantics.

## Learning Objectives

After this lesson, you will be able to:

- Design an HTTP contract for creating, reading, listing, and updating tasks.
- Separate controllers/handlers, application services, domain policies, and repositories.
- Extract the actor from a verified JWT and the tenant from an authorized request path.
- Use request/response DTOs instead of binding directly to database entities.
- Validate inputs at the boundary and enforce business validation in use cases.
- Write tenant-scoped SQL for reading and writing tasks.
- Verify project membership, assignees, and OWNER/EDITOR/VIEWER permissions.
- Use transactions and optimistic locking to prevent lost updates.
- Standardize HTTP status codes and Problem Details for error responses.
- Design POST retries using idempotency keys and an outbox when events are needed.
- Deploy stateless handlers on Lambda or serverless containers.
- Test the API, authorization, persistence, retries, and concurrency.

## 1. API Scope and Data Model

We are building an API for tasks belonging to a project and tenant. The data model assumes the following tables exist:

- `app_user`: maps identity provider accounts via `issuer + subject`.
- `tenant_membership`: user, tenant, tenant role, and membership status.
- `project`: projects belonging to a tenant.
- `project_member`: a user's role and status within a project.
- `task`: tasks belonging to a project and tenant.

A task has the following core fields:

| Field | Value Source | Client Editable? |
|---|---|---|
| `tenant_id` | Authorized tenant from path | No |
| `id` | Server-generated | No |
| `project_id` | Authorized project from path | No |
| `title` | Request | Yes |
| `description` | Request | Yes |
| `owner_user_id` | Assignee after membership verification | Via permitted action |
| `created_by` | Actor from JWT | No |
| `status` | Server sets OPEN on creation; policy on update | Restricted |
| `version` | Incremented by database on update | No |
| `created_at`, `updated_at` | Server/database clock | No |

Clients may choose an assignee if the actor has permission and the assignee is a valid member of the project. Clients must never send a tenant ID in the body to dictate where data is written, nor send `created_by`, `version`, or arbitrary status values.

### API Routes

| Method | Path | Purpose | Success |
|---|---|---|---|
| POST | `/v1/tenants/{tenantId}/projects/{projectId}/tasks` | Create a task | 201 Created |
| GET | `/v1/tenants/{tenantId}/projects/{projectId}/tasks/{taskId}` | Read a task | 200 OK |
| GET | `/v1/tenants/{tenantId}/projects/{projectId}/tasks` | List tasks | 200 OK |
| PUT | `/v1/tenants/{tenantId}/projects/{projectId}/tasks/{taskId}` | Replace editable fields | 200 OK |

Using PUT for the update example keeps semantics explicit: the client submits the full set of editable fields. If using PATCH, define a separate convention to distinguish omitted fields from fields explicitly set to null; do not use a plain nullable DTO and guess the client's intent.

### Request Flow Diagram

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

The gateway may handle part of authentication, but the application service must still verify the actor and object-level authorization per the API's policies. Never rely on the frontend hiding buttons or the gateway validating a token to skip permission checks at the resource boundary.

## 2. Designing Request and Response DTOs

DTOs form the contract between client and API. DTOs are not JPA entities and should not inherit from the persistence model.

### Create Task Request

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

Fields such as `tenantId`, `projectId`, `createdBy`, `status`, `version`, and timestamps are absent. Tenant and project come from the path after authorization; creator comes from the actor; initial status is set to OPEN by the server.

### Update Task Request

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

In the PUT example, `description` and `assigneeUserId` may be null to clear the description or unassign the task. All other fields are required. `expectedVersion` detects updates based on stale data. An API may replace the body version with HTTP `If-Match`/ETag; do not accept both conflicting version sources.

Status enum:

~~~java
public enum TaskStatus {
    OPEN,
    IN_PROGRESS,
    DONE,
    CANCELLED
}
~~~

Do not let clients transition statuses unless business policy permits it. For example, only OWNER/EDITOR can change status; VIEWER is read-only. If the workflow enforces transition rules, the domain policy must validate allowed transitions, not merely check that the enum value is in the list.

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

If certain sensitive fields are restricted to specific roles, create role-appropriate response views rather than always returning everything. Never return entities directly, as serialization may expose relationships, internal IDs, or fields outside the public API.

## 3. Actor Context from a Verified JWT

Controllers should never take `userId` from a request body or query parameter. The actor is constructed from the principal provided by Spring Security after JWT verification.

A minimal model:

~~~java
import java.util.UUID;

public record Actor(UUID userId) {
}
~~~

Resolver mapping the issuer/subject pair to an internal user:

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

The resource server must configure issuer/JWK and audience validation per the API contract. Never simply decode a JWT payload and trust its claims. For suspended users or revoked memberships, policy must define when access ceases; an unexpired token alone does not guarantee membership is still active.

The tenant ID in the URL indicates which tenant the client intends to act on. The use case must verify that the actor has an ACTIVE membership in that tenant and that the project belongs to the tenant. Never treat a path parameter as proof of authorization.

## 4. Configuring Spring Security

Minimal configuration example:

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

Configure `issuer-uri` via environment/deployment config. Add an audience validator if the decoder does not already verify `aud` for this resource server. If using browser cookies/sessions instead of bearer tokens, configure CSRF appropriately for the authentication model; never disable CSRF mechanically across all APIs.

Never embed secrets, database passwords, or private keys in source code. Functions should use workload identities/secret managers to access dependencies.

## 5. Thin Controller / HTTP Handler

The controller accepts the HTTP request, extracts path parameters, validates the DTO, resolves the actor, and calls the application service. The controller never writes SQL, makes role decisions, or publishes events directly.

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

This code demonstrates create, read, list, and update handlers. In a serverless API, the controller remains an HTTP adapter. Business use cases do not depend on API Gateway event classes or the underlying runtime type.

### Validation at the Boundary

Bean Validation verifies request structure:
- title is non-blank and within maximum length.
- description obeys size limits.
- status is a valid enum value.
- expectedVersion is present.

Business validation is still required at the application/domain layer:
- Project exists and is ACTIVE.
- Actor is authorized.
- Assignee is an ACTIVE project member.
- Status transition is valid.
- Task belongs to the correct tenant and project.

Validation does not replace authorization. A syntactically valid request may still be unauthorized.

## 6. Application Service for Create, Read, and Update

The application service orchestrates the use case. It enforces permissions, invokes repositories, and applies domain policies. Write methods run inside transactions to keep changes consistent.

Repository interface:

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

Access ports:

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

`ProjectAccessSnapshot` can hold the tenant role, project role, and project status read from the database. Never read roles from the request. Repositories/adapters must enforce tenant scoping in every query.

### Domain Models and Commands

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

Separating command/domain models from HTTP DTOs prevents the application service from depending on Spring MVC annotations or JSON serialization details.

### Create Use Case

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

Constructor injection makes dependencies explicit and easy to test. In production, the ID generator can be injected for deterministic testing. Events are written to the outbox within the same transaction; a worker publishes after commit. Never call a message broker or external API synchronously inside a database transaction and assume both systems commit atomically.

### Read Use Case

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

The query already scopes by tenant, project, and task. The policy checks additional state or ownership rules if required. Returning 404 for out-of-scope resources is one strategy to reduce enumeration; the API must apply it consistently.

### Update Use Case

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

The update has two version safeguards: comparing the read version and checking the version predicate in the SQL update. If two requests both read version 4, only one updates it to version 5; the other gets an update count of 0 and receives a conflict. Membership/role checks and writes should occur inside the transaction; for policies that might be revoked concurrently, consider locking membership rows or embedding authorization predicates directly into the UPDATE statement to narrow the race window.

In the PUT example, `assigneeUserId = null` means unassigning the task. If the API needs to distinguish "field omitted" from "explicitly set to null", use a PATCH DTO with presence wrappers such as `JsonNullable<T>` or an explicit patch command.

## 7. Repository: Every Query Must Be Tenant-Scoped

The repository is the persistence layer, not a place that accepts permissions from clients. Method signatures should require the tenant ID to reduce the risk of querying globally by ID and forgetting the tenant.

### Insert Task

An insert can use named parameters:

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

Before the insert, the application service has already verified permissions and the assignee. Under strict concurrency/revocation requirements, the adapter can combine the authorization predicate and insert in the same SQL/transaction or lock the necessary membership/project rows. Composite foreign keys enforce tenant consistency, though they do not automatically guarantee that project membership is ACTIVE.

### Read Task

~~~sql
SELECT tenant_id, id, project_id, title, description,
       owner_user_id, created_by, status, version,
       created_at, updated_at
FROM task
WHERE tenant_id = :tenant_id
  AND project_id = :project_id
  AND id = :task_id;
~~~

Never define a `findById(taskId)` method for tenant-owned endpoints without an additional layer enforcing tenant authorization. Querying by all three keys reduces mistakes and makes intent explicit.

### Update Task with Optimistic Locking

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

This query protects tenant/project scope and version. The adapter must ensure authorization is checked within the same transaction or included in the update predicate. If you need to block updates after concurrent membership revocation, add an EXISTS clause verifying ACTIVE membership and role, or lock the relevant membership row.

### Updating Assignee Must Verify Project Membership

A foreign key can ensure the assignee belongs to the tenant, but not that the user participates in the project. Before assigning:
- User exists and is active.
- Tenant membership is ACTIVE.
- Project membership is ACTIVE.
- Policy permits the actor to assign others.
- Project/task is not in a state that forbids assignment.

If a user is removed from a project after a task was assigned, define a clear policy: retain historical assignment, automatically unassign, or transfer to another owner. Never delete the task merely because membership was revoked.

## 8. Task Authorization Policy

A simple policy:

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

This is an illustrative example; real domains need richer transition rules. For instance, a DONE task might be reopened by an OWNER but not an EDITOR; or only the assignee may update estimates. Place these decisions in clearly named policies rather than scattering role checks across controllers.

Default deny: if the policy cannot confirm permission, deny it. Never fall back to a default MEMBER or VIEWER role when membership data is missing.

## 9. Listing Tasks and Pagination

List endpoints require the same tenant/project scope and membership checks as detail endpoints. Never fetch all tasks and filter in Java, as that wastes memory, risks leaking data through bugs, and breaks pagination.

Keyset pagination example:

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

Before querying, the application service must authorize the actor on the project. Cursors must encode or sign the relevant sort/filter/tenant components so a cursor cannot be replayed in the wrong context. Cap page size—for example, max 100. Never trust a client-supplied page size without clamping it.

Response:

~~~java
import java.util.List;

public record TaskPage(
        List<TaskResponse> items,
        String nextCursor) {
}
~~~

The application service authorizes the project before the repository fetches the page and clamps the page size:

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

The repository adapter must decode and validate the cursor against the current tenant/project/filter, then execute a query with tenant/project predicates like the SQL example below. Never trust a client-supplied cursor if it is unverified or mismatches the query context.

With continuously changing data, keyset pagination is usually more stable than offset pagination. If consistent snapshot pagination across multiple pages is needed, design explicit watermark/snapshot semantics.

## 10. Transactions, Outbox, and Idempotency for POST

A client may time out after a task is created but before receiving the response. If the client retries the POST, the server may create a second task unless an idempotency policy is enforced.

For create endpoints with important side effects:
- Clients send a stable `Idempotency-Key` for one logical operation.
- The server scopes keys by tenant and operation.
- Store a request fingerprint to detect the same key reused with a different payload.
- Write the task, idempotency result, and outbox event in the same transaction.
- Retries with the same key return the saved result.
- Retain keys long enough to cover client retries and supported replays.

Never generate a new key when retrying the same operation. Never use an in-memory map as the idempotency store in serverless, because another invocation may run on a different instance.

The outbox guarantees the task and event are persisted in the same database transaction. The publishing worker may retry; event IDs must be stable and consumers must be idempotent. Never call the broker first and then commit the task assuming both operations always succeed together.

## 11. Error Handling and HTTP Problem Details

APIs should return structured errors without stack traces or SQL.

| Scenario | Common HTTP Status |
|---|---:|
| Missing, invalid signature, expired, or wrong-audience JWT | 401 |
| Valid actor denied permission | 403 or 404 per anti-enumeration policy |
| Resource does not exist in tenant/project | 404 |
| Invalid request DTO | 400 |
| Invalid business rule/transition | 422 or 409 per contract |
| Stale version | 409 Conflict or 412 Precondition Failed if using If-Match |
| Same idempotency key with different fingerprint | 409 |
| Temporary database/dependency failure | 503 if the request cannot be processed |

Spring supports Problem Details. Example exception handler:

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

In production applications, add stable error codes, correlation/trace IDs, and sanitized validation field lists. Never include internal exception messages or SQL in responses. Authentication errors from security filters should be configured with custom entry points/access-denied handlers so they also return consistent Problem Details.

## 12. ETag and If-Match for Updates

Version can be represented as an ETag:

~~~http
HTTP/1.1 200 OK
ETag: "task-v7"
Content-Type: application/json
~~~

Client sends:

~~~http
PUT /v1/tenants/t1/projects/p1/tasks/k1
If-Match: "task-v7"
~~~

If the resource has already moved to version 8, the server returns `412 Precondition Failed`. This prevents clients from overwriting someone else's changes.

When using ETags:
- Derive the ETag from the server-side version.
- Parse `If-Match` according to HTTP grammar; do not use ad-hoc string comparisons.
- Include the version in the SQL UPDATE predicate.
- Return the new ETag after a successful update.
- Define behavior when `If-Match` is omitted; for resources requiring concurrency control, make it mandatory.

Never use an ETag as proof of access rights. Users must still pass authorization even if they know the exact version.

## 13. Serverless HTTP Adapters: Lambda and Containers

Application services should not depend on the compute model. Only the HTTP adapter varies by platform.

### API Gateway + Lambda

An API Gateway HTTP API can route requests to a Java Lambda via a compatible adapter. The adapter translates method, path, headers, body, and request context into a request the application handles. Clarify where token verification happens:
- A gateway authorizer can verify the JWT and forward verified claims.
- Or the Spring Resource Server application can verify the bearer token itself.
- If the gateway injects principal headers, strip spoofed client headers and secure the internal link.

Do not create a separate handler per business use case solely to distinguish routes; a router/controller can dispatch multiple routes to the same application service. Keep use-case logic independent so it can be invoked from HTTP, queue consumers, or tests.

### Serverless Containers

With Cloud Run or serverless container platforms, the application can run Spring Boot's embedded server. The platform receives HTTP traffic and routes it to instances. The application service remains stateless; never store actor, tenant, or transaction state in static mutable fields between requests.

### Deployment Checks

- Appropriate Java runtime and memory/CPU allocation.
- Platform-matching handler/adapter entry point.
- Request/response size limits and timeouts.
- Database connection pooling sized for max instances/concurrency.
- Environment variables contain non-sensitive configuration only.
- Secrets fetched via secret manager/workload identity.
- Health/readiness endpoints expose no internal details.
- Logs include request/trace IDs without tokens or sensitive payloads.
- IAM grants least-privilege permissions to the function.

## 14. Stateless Handlers and Connection Lifecycle

Serverless platforms may reuse an execution environment. You can reuse thread-safe dependencies like HTTP clients or properly configured connection pools, but never hold request-specific state in mutable fields.

Safe:
- Singleton services hold no per-request actor/tenant state.
- Each invocation passes Actor, tenantId, and request data via method parameters.
- Transactions open and close within the use case.
- JDBC connections are managed by the pool/framework and returned after the transaction.
- Caches store only data with explicit TTL/invalidation policies.

Unsafe:
- Static `currentUserId`.
- Static `currentTenantId`.
- Holding a Connection or EntityManager past the request.
- Uncleared ThreadLocals.
- Storing idempotency keys in RAM and treating them as durable.
- Spawning unmanaged background threads to continue request work after returning the response.

For async processing, publish a message/outbox record and let another function process it. Never return an HTTP response and expect background threads in the same invocation to finish once the platform freezes or closes the request context.

## 15. Database Connections and Concurrency

When the platform scales to many instances, each instance may open a connection pool. An upper-bound estimate:

~~~text
potential database connections
  ≈ max active instances × pool size per instance
    + connections from other workloads
~~~

Pool size must be calculated alongside max instances, concurrency, database connection limits, and connection proxies. Overly large pools can exhaust database connections during scale-out; overly small pools increase request wait times.

For every handler:
- Use prepared statements/parameter binding.
- Configure appropriate query and transaction timeouts.
- Never hold a transaction open while calling external APIs.
- Avoid N+1 queries on task lists.
- Enforce page size limits.
- Use indexes aligned with tenant/project and sort keys.
- Monitor connection acquisition time, query latency, and pool saturation.

Never raise max instances indefinitely to fix latency when the database is already the bottleneck. Compute scaling must align with database and dependency capacity.

## 16. Auditing, Events, and Side Effects

Task creation/updates may need to emit events for notifications or activity feeds. Write events to the outbox in the same transaction as the task:

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

Event payloads should include necessary business metadata:
- Stable event ID.
- Tenant ID.
- Task/project ID.
- Internal actor.
- Event type and schema version.
- Occurrence timestamp.
- Minimal business data.

Never send raw JWTs, passwords, or secrets in events. Consumers verify producer/workload identity and enforce idempotency using the event ID. If an event represents an action on a user's behalf, preserve the original actor for auditing without treating actor metadata as credentials.

## 17. Testing Handlers and Use Cases

Test by layer:

| Layer | What to Verify |
|---|---|
| DTO validation | Blank/oversized title, missing status, invalid version |
| Policy unit tests | Viewer cannot edit; editor can edit; inactive membership denied |
| Application service tests | Create sets actor/status correctly; read scopes tenant; update validates transitions |
| Repository integration | Queries include tenant/project predicates; optimistic update allows only one winner |
| Controller tests | Status codes, Location, JSON responses, and validation errors |
| Security integration | JWT issuer/audience/expiry; unauthenticated requests rejected |
| End-to-end | POST → GET → PUT → GET reflects updated data |
| Serverless adapter tests | Path/header/body/claim mapping and timeout behavior |

### Unit Testing the Create Use Case

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

`Task.from` and event factories are domain components in this example. In real tests, also verify the task ID, initial version, and timestamps. Never write tests that merely assert a mock returns the exact value the test stubbed.

### Integration Testing Optimistic Locking

Create a task at version 3. Submit two concurrent updates with expectedVersion=3:
- One update succeeds and version becomes 4.
- The other update gets affected rows = 0 and receives a conflict.
- Data is not overwritten by the later request holding a stale version.

Run tests against a real database or Testcontainers to verify unique constraints, locking, and transaction semantics. Mocked repositories do not prove SQL concurrency behavior.

### Cross-Tenant Tests

- An actor in tenant A cannot read tenant B's tasks.
- A valid project ID paired with the wrong tenant path returns no data.
- Viewers cannot create/update tasks.
- Editors cannot assign users outside the project.
- Users removed from a project lose access.
- Clients sending `createdBy`, `tenantId`, or `status` in JSON cannot mass-assign those fields.
- A cursor from tenant A cannot be used to query tenant B.

## 18. Handler Observability

Structured logs should include:
- Trace/request ID.
- Route template and HTTP method.
- Masked tenant ID or internal identifier per policy.
- Actor ID per logging policy.
- Task ID when needed for investigation.
- Status code, duration, and error category.
- Deployment revision.

Never log bearer tokens, cookies, secrets, raw request bodies, or descriptions that may contain personal data. Never place high-cardinality tenant IDs, user IDs, or task IDs into metric labels. Metrics should use operation/outcome/status class.

Useful metrics:
- `task_api_requests_total` by operation/outcome.
- `task_api_duration` histogram.
- `task_create_conflicts_total`.
- `task_update_version_conflicts_total`.
- `task_authorization_denied_total`.
- `database_connection_acquire_duration`.
- `outbox_oldest_unpublished_age`.

Trace a root span for the HTTP request and child spans for authorization queries, task repository calls, and outbox inserts. Never call an external broker inside the request transaction when an outbox can be used.

## 19. API Call Examples

Creating a task (UUIDs in the example are valid illustrative values):

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

Reading a task:

~~~http
GET /v1/tenants/7d3e6b54-1a2b-4c3d-8e9f-001122334455/projects/2a1f0b6c-7d8e-4f90-a123-456789abcdef/tasks/9bcf1234-5678-4abc-9def-0123456789ab
Authorization: Bearer <access-token>
~~~

Updating a task with version:

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

After a successful update, the server returns version 1. If the client resubmits version 0, the server returns a conflict/precondition failure per the contract. Every request requires a valid token and permissions on the exact tenant/project/task.

## 20. Checklist for Implementing Java Task Handlers

- [ ] Routes, methods, and paths are defined and versioned.
- [ ] Request DTOs contain only client-allowed fields.
- [ ] Bean Validation validates inputs at the HTTP boundary.
- [ ] Actor is resolved from a verified JWT via issuer + subject.
- [ ] Token audience is validated against the API.
- [ ] Tenant membership and project membership are verified at current state.
- [ ] Every repository method enforces tenant/project scope.
- [ ] Create assigns ID, tenant, creator, status, and timestamps server-side.
- [ ] Assignees are verified as active project members.
- [ ] Reads enforce object-level authorization and DTO projection.
- [ ] Updates use field allowlists and domain transition policies.
- [ ] Optimistic locking / If-Match prevents lost updates.
- [ ] Transactions wrap both business writes and outbox records.
- [ ] POST has an idempotency strategy when retries could create duplicates.
- [ ] Error mapping never leaks SQL, stack traces, or out-of-tenant resources.
- [ ] Functions are stateless; actor/tenant state is never stored in mutable static state.
- [ ] Connection pools are sized for max instances and concurrency.
- [ ] Secrets and database access use workload identity/secret managers.
- [ ] Unit, controller, repository, security, and concurrency tests are in place.
- [ ] Logs, metrics, and traces exclude tokens and sensitive data.

## Self-Check

1. Why should controllers avoid holding SQL and business authorization?
2. Where should tenant ID and creator ID come from?
3. Which fields should a create-task DTO exclude to prevent mass assignment?
4. What is the difference between PUT and PATCH when handling null fields?
5. Why should repository methods take tenantId and projectId alongside taskId?
6. Is belonging to the tenant sufficient for an assignee to be assigned to a project task?
7. How does optimistic locking solve lost updates?
8. Why must updates check the affected row count?
9. How does a transactional outbox protect consistency between tasks and events?
10. How should idempotency keys be retained when clients retry POST requests?
11. Why must actor or tenant state never be kept in static fields in Lambda or containers?
12. How does the database connection budget relate to max instances and pool size?
13. When should an API return 404 instead of 403?
14. Which integration tests prove the handler blocks cross-tenant access?

A well-designed Java serverless handler does minimal work at the HTTP layer: it receives the request, authenticates the principal, validates the DTO, and delegates to the use case. The application service enforces permissions and coordinates business logic; the repository scopes by tenant/project and protects concurrency; and database transactions together with an outbox keep changes consistent. As functions scale or get reused, stateless design, idempotency, connection budgets, and per-object authorization keep task creation, reading, and updating secure.
