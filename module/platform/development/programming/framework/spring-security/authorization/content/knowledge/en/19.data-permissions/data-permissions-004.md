# Protecting Create Operations When the Resource Has No Identifier Yet

## 1. The Problem: No ID Yet, So What Object Do We Check Permissions On?

In read, update, and delete operations, the application can typically fetch the object by ID and check whether the user has READ, WRITE, or DELETE permission on that exact object:

```text
GET /documents/42
  -> find Document #42
  -> check if actor has READ on #42?
  -> allow or deny
```

However, when a user calls `POST /documents` to **create** a new resource, the object has not been persisted yet and therefore usually **has no database-assigned ID yet**. The security question cannot be "do they have permission on Document #null?" or "do they own the new document?" because the document does not exist yet.

A better question is:

> **Is the authenticated subject allowed to create an object of this type, within this parent/tenant/workspace scope, with the requested attributes and relationships, in the current system state?**

Example:

```http
POST /api/projects/10/documents
Content-Type: application/json

{
  "title": "Project brief",
  "content": "First version"
}
```

Before the server creates a new Document, it still has plenty of data to decide:

- **Actor:** who is logged in; which authorities have been granted.
- **Action:** `CREATE_DOCUMENT`, distinct from READ and WRITE.
- **Parent resource:** Project 10 already exists; is the actor a member permitted to create documents in it?
- **Tenant:** which tenant does Project 10 belong to; does the actor have permission in that tenant?
- **Requested attributes:** are the title, content, document type, security label, template, etc. permitted to be set?
- **Business state:** is the project locked, archived, over quota, or pending approval?
- **Referenced resources:** do the template, attachment, folder, approver, or parentId chosen by the client fall within permitted scope?

Only after proper checks should the service instantiate the entity, assign owner/tenant from **trusted sources**, save to the database, and return the new ID.

## 2. Distinguishing Three Forms of Permission

| Permission | Protected Target | Example |
| --- | --- | --- |
| Functional invocation permission | Endpoint or application operation | `document:create` |
| Creation permission within a scope | Tenant, project, folder, organization, account, or collection | Alice can create documents in Project 10 |
| Permission on an existing resource | Individual Document with an ID after creation | READ/WRITE/DELETE on Document 42 |

Having `document:create` does not mean being allowed to create documents in **every project**; and having WRITE on Document 42 does not automatically allow creating Document 43. These are two different permissions in action and target.

A conceptual formula:

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

For personal resources **without a parent ID**, the verified principal and tenant can serve as the creation scope. For example, creating a personal note: each user is allowed to create their own notes, and the server sets `ownerId` from the authenticated subject ID. Then `parentId` is not required, though you still must check authority, tenant, quota, attributes, and other business rules.

**Do not force a single rule onto every resource type.** Creating a comment on an issue, adding a member to an organization, creating an invoice, creating a money transfer, and creating an admin account carry very different permissions and side effects.

## 3. Wrong Ways to Check When the Object Does Not Exist Yet

### 3.1. Checking Authentication Only

```java
@PreAuthorize("isAuthenticated()")
public Document create(CreateDocumentRequest request) {
    return repository.save(toEntity(request));
}
```

This is an **illustrative anti-pattern**: any logged-in user can create in whatever scope the request chooses if no other check exists. `toEntity(request)` also risks copying owner/tenant from JSON.

### 3.2. Checking Permissions Based on a Null ID

```java
@PreAuthorize("hasPermission(#document.id, 'Document', 'WRITE')")
public Document create(Document document) {
    return repository.save(document);
}
```

If `document.id == null`, most ObjectIdentity-based ACL checks have no basis to evaluate WRITE on an unsaved document. `PermissionEvaluator` may return false or throw an exception depending on the implementation. Do not "fix" this by allowing all `id == null`, because an attacker could supply a null ID to bypass checks.

**Right direction:** check CREATE permission on an **already-existing scope** (project/folder/tenant/collection), or the user's CREATE policy for that resource type. Permissions on the new entity can be assigned **after the ID is created**, but only within an already-authorized workflow.

### 3.3. Trusting `ownerId`, `tenantId`, or `role` Fields in JSON

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

If the server binds JSON directly into an entity and calls `save`, a user can create data on behalf of an admin, place the document into another tenant, or bypass the approval step. This is **mass assignment / broken object property level authorization**, which can combine with BOLA/IDOR.

Never assume that because the resource "has no ID yet", other fields are automatically trustworthy. Sensitive fields such as `ownerId`, `tenantId`, `createdBy`, `approvedBy`, `role`, `isAdmin`, `status`, and `permissions` must be assigned by server-side logic or modified only in an authorized workflow.

### 3.4. Save First, Check Later

```java
@Transactional
@PostAuthorize("@policy.canOwn(authentication, returnObject)")
public Document create(CreateDocumentRequest request) {
    return repository.save(toEntity(request));
}
```

**Never use this approach to protect creation.** `@PostAuthorize` runs after the method body executes; with common transaction/method-security advisor ordering, the transaction may have already committed before the post-check throws `AccessDeniedException`. The API returning 403 **does not guarantee the entity was not created**. Side effects like sending emails, issuing URLs, publishing events, or `REQUIRES_NEW` transactions cannot simply roll back by default either.

Use **pre-write preconditions** and enforce data constraints inside the transaction. `@PostAuthorize` is useful for certain read operations, not as the primary defense for create/write.

## 4. Designing a Safe Create Command

Instead of accepting a JPA entity from the client, use a dedicated DTO containing only **the fields the caller is actually permitted to set**.

Example REST request:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateDocumentRequest(
    @NotBlank @Size(max = 160) String title,
    @NotBlank @Size(max = 20_000) String content
) {}
```

There is no `id`, `ownerId`, `tenantId`, `createdBy`, `createdAt`, `status`, or `aclEntries` in the request DTO. This reduces the mass assignment surface; however, using a record **does not by itself guarantee** Jackson will reject every extra JSON field under all configurations. If the API must reject disallowed properties, configure deserialization or validation per the API contract and add integration tests.

### Who Determines ID, Owner, Tenant, and Initial State?

| New Resource Property | Recommended Source |
| --- | --- |
| `id` | Database-generated ID or server-generated UUID as required |
| `ownerId` | Authenticated principal/subject and permitted creation policy |
| `tenantId` | Tenant with membership verified for actor and parent |
| `projectId` | Real project, in permitted tenant, actor has CREATE |
| `createdBy` | Authenticated subject or valid service identity |
| `createdAt` | Server clock/appropriate database default |
| `status` | Initial value per server workflow such as `DRAFT` |
| `visibility` | Safe default, e.g., PRIVATE, unless publish permission exists |
| `sharePermissions` | Separate authorized ACL grant workflow, never arbitrary JSON |
| `title`, `content` | Validated request, sanitized per display context if needed |

If an endpoint supports "create on behalf of" (`on behalf of`), that must be **a separate permission** verified by policy with auditing, not letting anyone submit an arbitrary `ownerId`.

## 5. Trusted Source: Authentication and Tenant Membership

The service layer needs to know the actor and permitted tenant. You can define an application contract:

```java
public record ActorScope(String subjectId, String tenantId) {}

public interface CurrentActorService {
    ActorScope requireActorInVerifiedTenant();
}
```

This is a **custom-built interface**, not a built-in Spring Security API. The implementation must:

1. Retrieve `Authentication` from the current call's `SecurityContext`.
2. Reject if there is no valid authenticated principal.
3. Use a stable subject ID, such as a signature-verified JWT `sub` or internal principal ID, instead of trusting a request-supplied username.
4. If the request selects a tenant, verify membership/role server-side and confirm the tenant is active.
5. Return `ActorScope` only after verification completes.

When using JWTs, **a tenant claim in a valid token does not necessarily prove membership is still active** if an account was revoked mid-flight; depending on the threat model, token lifetime, revocation, or server-side membership lookup must be designed. Never turn `X-Tenant-Id` into self-verifying proof.

When creation is triggered from a job/event instead of HTTP, explicitly establish the service principal, delegated actor, and scope. Never treat the absence of a user session as global privilege.

## 6. Spring Security Functional Invocation Checks

At the HTTP layer:

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

This is a **fragment inside a Spring Security configuration class**, requiring imports, authentication configuration, other endpoints, and appropriate CSRF/CORS. The example configuration only allows POST to the matching path with authority `document:create`; it **does not yet check** whether the actor can create in a specific Project.

Enable method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

On the service method, add a basic action check:

```java
@PreAuthorize("hasAuthority('document:create')")
@Transactional
public DocumentView create(Long projectId, CreateDocumentRequest request) {
    // Next, check project/tenant/membership inside the transaction.
}
```

The `@PreAuthorize` annotation requires a Spring-managed proxy and `@EnableMethodSecurity`. Action checks at HTTP and service may overlap, but the service-level check also protects calls from other beans. Do not rely solely on HTTP filters when the service is reused by batches, message listeners, or scheduled tasks.

**Important on transaction ordering:** under common advisor configuration, `@PreAuthorize` may run **before** the method's transaction interceptor. If creation conditions are sensitive and must share the same transaction as the write, re-verify **inside the service body after the transaction has started** or design a transaction boundary encompassing the decision, per data consistency requirements. Never assume the order of annotations in source code dictates interceptor order.

## 7. Spring Boot Example: Checking Create Permission in an Existing Project

Below are **illustrative classes/components** in Spring Boot, Spring Security, Spring Data JPA, and Java 17+. The code requires the project's entities, repositories, database schema, and authentication infrastructure; it is not a single file runnable via `javac` alone.

### 7.1. Querying the Parent Resource in the Verified Tenant

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProjectRepository extends JpaRepository<Project, Long> {
    Optional<Project> findByIdAndTenantIdAndArchivedFalse(
        Long id, String tenantId
    );
}
```

The `Project` entity must have matching `id`, `tenantId`, and `archived`. This query looks up the project by ID **and verified tenant**. If the project belongs to another tenant, it returns empty just like a non-existent project. "Not seeing" the parent resource can be mapped to a neutral HTTP 404 if that is the API policy.

### 7.2. Membership Must Grant CREATE, Not Just READ

Example dedicated repository for membership permissions:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProjectMemberRepository
        extends JpaRepository<ProjectMember, Long> {

    boolean existsByProjectIdAndSubjectIdAndCanCreateDocumentsTrue(
        Long projectId, String subjectId
    );
}
```

Assumes the `ProjectMember` entity stores server-managed `projectId`, `subjectId`, and `canCreateDocuments`. If the system uses per-project roles, query the role and compute the appropriate permission. Membership with READ permission does not necessarily grant CREATE permission.

### 7.3. Create Service: Check Before Saving

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

        // Server-side ActorScope built from Authentication + membership.
        ActorScope actor = actors.requireActorInVerifiedTenant();

        Project project = projects
            .findByIdAndTenantIdAndArchivedFalse(
                projectId, actor.tenantId())
            .orElseThrow(DocumentCreateService::notVisible);

        // Check create permission on the parent project before any write operation.
        boolean canCreate = members
            .existsByProjectIdAndSubjectIdAndCanCreateDocumentsTrue(
                project.getId(), actor.subjectId());

        if (!canCreate) {
            // Example API chooses to hide existence of out-of-scope projects.
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

        // Project, owner, tenant, and status are taken only from trusted data.
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

**Assumptions and boundaries:**

- `Document`, `DocumentStatus.DRAFT`, `Project`, `ProjectMember`, and `DocumentRepository` are application data types that must be declared per the real model.
- `CurrentActorService.requireActorInVerifiedTenant()` only returns an authenticated actor and a membership-verified tenant.
- `@PreAuthorize` requires the general `document:create` authority. For a logged-in caller lacking the authority, Spring Security typically denies before the method body; the response can be 403.
- The service looks up the project by **ID and tenant**; the actor cannot simply change `projectId` to another tenant.
- `canCreateDocuments=true` must be present in trusted membership, not merely permission to view the Project.
- The new entity is created via an empty constructor and selective setters; `id` is assigned by persistence, `ownerId` and `tenantId` are assigned by the server, and status is DRAFT.
- `@Transactional` wraps loading the project, verifying membership, and saving the document in one **logical transaction**, though this **does not by itself solve every race** if concurrent membership/parent state changes under default isolation.
- `documents.save` is not guaranteed to generate the ID on that exact line under every persistence strategy: a flush or commit may be needed to catch constraint violations. Never send emails or "created successfully" notifications outside the transaction before commit.
- Returning 404 for both non-existent and invisible projects is an **API policy choice**, not default behavior of every Spring Security implementation.

### 7.4. Controller Creating and Returning Location

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

In the controller, `@Valid` triggers Bean Validation if validation infrastructure is provided. `CreateDocumentRequest` has only title/content so the client cannot directly assign owner/status through the DTO. Still, test JSON with extra fields, lengths, Unicode, content types, and deserialization; never implicitly assume extra fields are rejected.

`Location` contains the ID **returned by the server after creation**, not an ID chosen by the caller to bypass permissions. The response body should be a DTO with publishable fields, never serializing the full JPA entity.

### 7.5. HTTP Configuration and Service Configuration Are Two Different Layers

`SecurityFilterChain` blocks requests missing the authority at the HTTP boundary. `@PreAuthorize` on the service blocks under-privileged service calls even from other sources. **Scoped lookup and membership queries in the service** verify permission on the exact selected Project. These are three complementary layers, not three identical ways of saying the same thing.

## 8. When Checking via `@PreAuthorize` Against a Parent Resource

Another option is calling a policy bean directly in the expression:

```java
@PreAuthorize(
    "hasAuthority('document:create') and " +
    "@projectPolicy.canCreateDocument(authentication, #projectId)"
)
public DocumentView create(
        @P("projectId") Long projectId,
        CreateDocumentRequest request) {
    // Save after verifying and continue enforcing permissions in the transaction.
}
```

The snippet above is a **method fragment**, requiring a `projectPolicy` bean, `import org.springframework.security.access.method.P`, and Spring Security infrastructure. The policy bean must:

1. Obtain the caller from verified Authentication.
2. Check tenant membership from a server source.
3. Verify the Project by ID and tenant, ensuring it is not archived/locked.
4. Verify the caller has **CREATE_DOCUMENT** permission in the Project.
5. Return an explicit boolean, defaulting to deny if data is missing.

The `@P("projectId")` annotation binds the parameter in SpEL even if the code is not compiled with parameter name metadata.

**Timing note:** `@PreAuthorize` checks may execute **before the transaction** of the same method under default advisor ordering. Thus, for sensitive creations, checking via a policy bean at pre-auth **does not replace** maintaining invariants during the transactional insert. Alternatively, you can **pre-check only the general authority**, then fetch project/membership inside the transaction as in the previous example to avoid querying the DB twice.

### Using `hasPermission` with ACLs

If document creation permission is modeled as an ACL on the **existing parent Project**, you can use the idea:

```java
@PreAuthorize(
    "hasAuthority('document:create') and " +
    "hasPermission(#projectId, 'com.example.Project', 'CREATE')"
)
public DocumentView create(@P("projectId") Long projectId,
                           CreateDocumentRequest request) {
    // Check tenant, business state, and mutation boundary here.
}
```

This is only an **option if** Spring ACL's `PermissionEvaluator`, `AclService`, and Project's `ObjectIdentity` are properly configured. `CREATE` here applies to the **parent Project**, not the ID-less Document. `BasePermission.CREATE` is just an ACL permission; the right decision still depends on SIDs, ACEs, and verified resource data. Do not use a Project's CREATE ACL and skip tenant boundaries or workflows/quotas.

**Do not make this mistake:** `hasPermission(#newDocument, 'CREATE')` when `newDocument.id == null` is not a standard way to prove permission to create an entity in a given project. Check permissions on an **existing scope** or a create policy using known data before inserting.

## 9. When There Is No Parent ID: Creating in a Personal Space

For `POST /api/me/notes`, a user may create personal notes if:

- The principal is authenticated.
- They have authority `note:create` or a policy permitting personal note creation.
- The account is active and not locked.
- Quota/billing/plan allows it.
- The content is valid.
- The server assigns `ownerId` and tenant scope.

Diagram:

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

For a product with only personal notes, the endpoint does not need to accept `ownerId`. Adding `POST /api/users/{userId}/notes` solely so the client can pick an owner creates a new attack surface. If business genuinely needs assistants to create notes for others, check a separate `note:create:on-behalf-of` permission, delegation relationship, expiry, and audit.

A creation policy can rely on **resource type** and **verified tenant/account state**, without needing an ID for the entity about to be created. This is no weaker than checking an object ID, because the protected target at that moment is **the create action within a scope**.

## 10. Referenced Resources in the Request Still Need Per-ID Checks

A create request may carry no ID for the new object yet contain **IDs of several existing objects**:

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

Here you must check:

- User is allowed **CREATE_TASK** in Project 10.
- Assignee 52 can be assigned tasks in Project 10 and the caller is permitted to assign.
- Template 18 is within usable scope; no leaking templates from other tenants.
- Parent task 7 belongs to the right project and the caller has permission to act on it.
- Links between IDs actually exist and are valid per workflow.

**A database foreign key only proves an ID exists**, not that the caller has permission to use that ID. Whether the ID is sequential or a UUID does not change the authorization obligation.

### Watch Out for Cross-Tenant Links

If a new task in tenant A is assigned a template ID belonging to tenant B, checking general CREATE_TASK is still not enough. Creation can become a vehicle for **unauthorized reference binding** or **data leakage via relationships**.

A safe query pattern for templates:

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

This is **illustrative SQL**, to be adapted to the real schema; table/column names are not default Spring Security schema. The query only returns a template when the caller has permission in the verified tenant.

## 11. Quotas, Quantity Limits, and Concurrent Creation Races

Many applications allow a user to create at most 10 workspaces or a project at most 100 documents. Checking quota like:

```java
if (repository.countByProjectId(projectId) < maxDocuments) {
    repository.save(newDocument);
}
```

**is not concurrency-safe**: two requests can both read count=99 and both insert, exceeding the quota. Even when the method has `@Transactional`, default isolation usually does not make check-then-insert atomic.

Solutions depending on limit type:

- **Atomic reservation/counter** in the database, e.g., conditionally updating a counter `used < quota` and only inserting when the update succeeds, in the same transaction.
- **Controlled row lock** on the quota-holding record to serialize checking and slot allocation.
- **Serializable isolation** if workload permits, paired with proper retries for serialization failures.
- **Unique constraints** for invariants like "only one record may exist with this key".
- **Versioning/optimistic locking** with proper retry logic, never treating concurrent errors as granted permission.

**Quota limits differ from authorization yet are often part of the create policy.** A user permitted to create this resource type may be denied **at the moment** due to quota or billing status. Handle error messages clearly without leaking another tenant's data counts.

### Membership Revoked Between Check and Insert

Example:

1. Request A verifies Alice is an editor of Project 10.
2. Admin revokes Alice's editor permission.
3. Request A proceeds to insert.

If security requirements demand revocation take effect **before the insert commits**, consider transaction isolation, locking the membership/project row, version/authorization epochs, or membership-predicated inserts. A transaction wrapping queries does not automatically prevent races under `READ_COMMITTED`. Mechanism choice depends on DB, revocation SLA, and actual load.

Never promise "I put `@Transactional` so all permissions and quotas are atomic" without concurrency test evidence.

## 12. ID Assignment and Post-Creation Side Effects

### Who Generates the Identifier?

- **Database identity/sequence:** ID appears on insert/flush or per generator strategy.
- **Server-generated UUID:** can be generated before persisting, still controlled by the trusted system.
- **Client-generated ID:** some systems support it, but must handle namespaces, ownership, uniqueness, idempotency, and overwrite/upsert protection.

For normal creation, never take a client-sent ID and silently call `save` on an entity whose key already exists, because ORMs handle insert/merge differently depending on state. If an API genuinely allows PUT with a client-chosen ID to create resources, clearly separate **create-only** (fail if present) from **replace/update** (requires permission on existing object), backed by unique/conditional DB writes.

### Do Not Emit Side Effects Before Permissions and Transaction Succeed

Creating a Document may also require:

- Creating owner ACL/ACE.
- Generating an audit record.
- Publishing a domain event.
- Sending email/notifications.
- Creating folders/object storage.
- Search indexing.

Determine which side effects **must be atomic with the database**, and which need **outbox/after-commit** with retry/idempotency. Never send a "document created" email only for the transaction to roll back later because a permission check or constraint failed.

If creating an ACL for the new ID, do so only after obtaining the ID inside **an authorized workflow**; ensure proper ACL persistence/transactions and cache invalidation. If ACLs and documents live in separate stores, use an explicit consistency strategy rather than assuming JDBC/JPA `@Transactional` spans external systems automatically.

## 13. HTTP 401, 403, 404, 409, and 422 in Create Operations

Exact status codes are an API contract. Do not let `PermissionEvaluator` or `@PreAuthorize` dictate every business status code automatically.

| Situation | HTTP Code to Consider | Notes |
| --- | --- | --- |
| No valid principal yet | `401 Unauthorized` / auth challenge | Per AuthenticationEntryPoint |
| Has identity but lacks `document:create` | `403 Forbidden` | Lacks permission for the function |
| Project does not exist or is outside visible scope | `404 Not Found` | Hides existence when needed |
| Project exists and caller may know it, but cannot create | `403 Forbidden` | Only when exposing resource existence is allowed |
| Malformed JSON / validation error | `400 Bad Request` or `422 Unprocessable Content` | Per API contract |
| Slug or idempotency key conflict | `409 Conflict` or designed idempotent response | Depends on business logic |
| Project archived / business state forbids creation | `409`/`403` depending on semantics | Consistent across routes |
| Created successfully | `201 Created` with Location and appropriate DTO | Server-guaranteed ID |
| Database/quota service failure | Appropriate `5xx` | Do not create or expose false data |

If policy requires hiding another tenant's Project, return the same `404` and neutral response body for both non-existent and invisible projects. However, a user missing a functional role may receive `403` without revealing a specific ID.

Do not convert all `AccessDeniedException`s application-wide into 404; hiding choices must bind to resource types and the API contract. Never log or expose tokens, secret tenant memberships, full request bodies, or stack traces to clients.

## 14. Standalone Java 17: Creating Without Knowing an ID Ahead of Time

This program **uses no Spring Security/database**, yet illustrates a creation policy: checking subject, functional permission, parent tenant, membership with CREATE permission, and parent status; only then does the server issue an ID and assign owner/tenant. It also intentionally passes forged owner/tenant inputs to prove the server **does not trust self-declared values**.

Create `SecureCreationDemo.java`:

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

        // Completely ignore client's claimedOwner/claimedTenant.
        // ID, owner, and tenant are determined server-side after checks.
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

Run with JDK 17 or later:

```bash
javac SecureCreationDemo.java
java SecureCreationDemo
```

Exact stdout:

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

Explanation:

- Alice has create permission in Project 10; even though the request claims owner=bob and tenant-b, the Document is saved with **owner=alice, tenant-a**.
- Alice cannot target Project 20 in another tenant.
- Bob has functional create authority, yet is not in the creator list for Project 10 → denied.
- Guest lacking authority, archived projects, and non-existent projects all fail to create.
- A request with a blank title is not saved.
- Only **one** Document is created and receives a new server-generated ID.

**Demo limitations:** this is in-memory within one JVM, lacking a real authenticated SecurityContext, transactions, concurrent writes, quotas, DB constraints, or referenced resources. Use the example to understand the **decision order**, not as production-sufficient. In a real application, actor/tenant are verified by trusted authentication/membership infrastructure.

## 15. Testing Create Security: Mandatory Cases

### Preparing Control Data

Create:

- Alice in Tenant A, with `document:create` and CREATE in Project 10.
- Bob in Tenant A, with `document:create` but **READ only** in Project 10.
- Carol in Tenant B, with CREATE in Project 20.
- A user lacking functional authority.
- An archived project, and a non-existent project.
- A project near quota.
- A template/assignee/attachment from another tenant to test cross-referencing.

### Security Test Matrix

| Scenario | Expectation |
| --- | --- |
| Alice creates in Project 10 | 201, new document has owner Alice and tenant A |
| Alice changes path to Project 20 | No resource created, no tenant B data leaked |
| Bob has general authority but lacks CREATE in Project 10 | Denied; no new row |
| Unauthenticated | 401/appropriate auth flow; no write |
| Lacks `document:create` | 403; no write |
| Project archived/locked | Not created; status per API contract |
| Project does not exist | 404/appropriate contract; no write |
| JSON sends `ownerId=bob` | Does not assign Bob as owner; may reject extra field |
| JSON sends `tenantId=tenant-b` | Does not set wrong tenant |
| JSON sends `status=APPROVED` | Does not bypass workflow; server status is DRAFT |
| JSON picks template from another tenant | Does not create unauthorized relation |
| JSON picks assignee outside project | Denied or filtered per business rule |
| Two concurrent requests exceeding quota | Quota not exceeded; verify DB/invariant |
| Membership revoked before commit | Outcome matches designed consistency requirement |
| DB fails after assigning temporary ID | Does not falsely return "created", side effects rolled back/compensated |
| Repeating request with same idempotency key | Does not create duplicates beyond contract |
| Tenant A admin role creates in tenant B | Not allowed because roles are scoped |
| Non-HTTP service create call | Still checks actor/action/tenant/membership |

### Integration Tests with Spring

Use `@SpringBootTest` and `MockMvc` or real HTTP tests, with the Spring Security filter chain, controller, service proxy, transactions, and test database. Do not just unit-test `canCreate(...)` or stub repositories to return true.

Example **test fragment** for an endpoint hiding out-of-scope projects:

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

This snippet needs `MockMvc`, static imports, and matching `CurrentActorService`/tenant membership fixtures for Alice; it does not run standalone. If the API contract returns 403 instead of 404, adjust the expectation accordingly. **More important than status:** assert no Document is saved in tenant B, no unauthorized ACL or email/event is created, and owner is not spoofed.

A good test swaps Project IDs between two users in two tenants, including the case where Bob holds the general authority and only lacks CREATE on that specific project. This catches bugs that "unauthenticated user must be rejected" tests miss.

### Testing Check Timing

- Spy on the repository to verify **deny paths never call `save`**.
- Test transaction rollback when validation/business rules fail before commit.
- Test concurrent quota reservations/unique constraints against a real database, not just mocks.
- Test membership/ACL revocation and cache invalidation.
- Test cross-tenant nested references.
- Test direct service invocations via the Spring-managed bean, not a manually instantiated `new Service()`, when verifying `@PreAuthorize`.
- Test request bodies with extra fields, sensitive fields, nulls, long text, and wrong JSON types.
- Test post-commit side effects, outbox, and retry idempotency.

## 16. Common Bugs and Fixes

| Bug | Cause | Fix |
| --- | --- | --- |
| Waiting for Document to have an ID before checking CREATE | Too late or no object to check | Check actor + action + parent/tenant before insert |
| Treating `hasPermission(null, 'CREATE')` as allow | Missing object does not prove permission | Check CREATE on parent or resource-type policy |
| Only `isAuthenticated()` on POST | Normal user can create in wrong scope | Add CREATE authority and resource/tenant policy |
| Only `hasAuthority('document:create')` | Has functional right but lacks permission on chosen Project | Check permission on Project/folder/tenant |
| Letting client send `ownerId` and using it as-is | Owner spoofing or unauthorized impersonation | Server sets owner from verified identity |
| Letting client send `tenantId` and trusting it | Cross-tenant creation | Verify tenant membership server-side |
| Binding JSON directly to JPA entity | Mass assignment into status, ACL, owner | Allowlist DTO, server-set protected fields |
| Using READ on Project as CREATE | Overly broad permission | Define separate CREATE_DOCUMENT |
| Creating first, then using `@PostAuthorize` | Insert may commit before deny | Precondition before side effects, proper transaction/query |
| Checking `parentId` without checking `templateId`/`assigneeId` | Cross-tenant or unauthorized relations | Verify every referenced object and relation |
| Treating FK as guaranteeing authorization | FK only checks existence/key relation | Combine with principal and tenant policy |
| Checking quota via COUNT then INSERT | Race exceeds limit | Atomic reservation, locks/constraints, or serializable |
| Assuming `@Transactional` prevents all races | READ_COMMITTED is not serializable | Design locking/conditional writes per invariant |
| Creating ACL grant for owner from JSON | Unauthorized privilege grant | Set owner from verified actor, create ACL after approval |
| Sending email before commit | Creation notification sent despite DB rollback | Outbox/after-commit and idempotency |
| Letting client choose ID and calling `save` as create | May overwrite/merge or conflict | Create-only semantics, uniqueness, update policy if existing |
| Testing only 201, skipping negative tests | Misses cross-tenant/role escalation | Swap parent IDs, forged fields, revocation, races |
| Leaving non-HTTP services unprotected | Jobs/listeners can bypass endpoint filters | Policy at service/domain/data access |

## 17. Review Checklist for a Resource-Creating POST

Before merging a CREATE endpoint, check:

1. **Who is the actor?** Principal retrieved from verified `Authentication`, never from JSON or self-declared request headers.
2. **What is the action?** `CREATE_DOCUMENT`/`CREATE_TASK`, not confused with READ/WRITE.
3. **What is the scope?** Project/folder/tenant/organization/collection, or personal scope when there is no parent.
4. **Parent permissions?** Are membership, create permission, and Project state verified from the database?
5. **Which fields can the client set?** Does the allowlist DTO omit owner/tenant/status/ACL/createdBy?
6. **Who generates the new resource ID?** Server/database-assigned, or client ID with a create-only contract?
7. **Are nested references checked?** Template, assignee, attachment, parent task, folder.
8. **Is the tenant verified?** Are admin roles scoped strictly to the right tenant?
9. **Do business state/quotas allow creation now?** Are there concurrent creation races?
10. **Is the policy in the service/domain?** Not relying solely on URL protection.
11. **Is a new ACL needed?** Issue ACEs only for the verified actor and after creation is permitted.
12. **Is the transaction boundary right?** Avoid post-creation checks and pre-commit side effects.
13. **Does the HTTP response match the contract?** 201 + Location on success; appropriate 401/403/404/409/422 on error.
14. **Are out-of-scope resources kept hidden?** Never leak tenant/owner/policy details in error bodies to unauthorized callers.
15. **Tested with two users/tenants?** Not just valid users, but also swapped project IDs, forged JSON, and concurrency.
16. **Is auditing monitored?** Log create attempts, denials, quota failures, and successful commits without logging secrets.
17. **Are caches/events/indexes properly scoped?** Never create share grants, publish events, or index without authorization.

**Conclusion:** When a new object **does not have an ID yet**, never use the missing ID as an excuse to skip authorization. Check **CREATE permission on the action and an existing scope**, use server-verified identity/tenant, let clients set only permitted fields, and validate every referenced resource. **Generate the ID and persist data only after the creation policy is satisfied**, while protecting invariants in transactions/DB and testing concurrency, revoked permissions, and forged inputs.

## References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy beans, and `@PostAuthorize` warnings with database writes.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP request authorization by method/path/authority; does not replace resource policies.
- [Spring Security — ACLs](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): `BasePermission.CREATE`, `ObjectIdentity`, ACE/SID, and checking permissions on existing resources.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, checking permissions on every request and resource access.
- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html): input DTOs, allowlisting assignable properties.
- [OWASP API Security Top 10 — API1:2023 BOLA](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): per-referenced-object authorization, not just URL checks.
- [OWASP API Security Top 10 — API3:2023 Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/): mass assignment and field protection.
- [Spring Data JPA — Repository Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries to look up parents scoped by tenant/ownership.
