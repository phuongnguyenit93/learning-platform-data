# IDOR and Permission Checks per Resource Identifier

## 1. Why Can a Valid ID Still Create a Vulnerability?

Suppose Alice logs into a document management application and opens:

```http
GET /api/documents/41
Authorization: Bearer <alice-access-token>
```

Document `41` belongs to Alice. The application returns the correct data. Then Alice changes `41` to `42`, which is Bob's document:

```http
GET /api/documents/42
Authorization: Bearer <alice-access-token>
```

If the server only authenticates Alice, then calls `repository.findById(42)` and returns the record, Alice has accessed Bob's data despite **having no permission on document 42**. This is **IDOR — Insecure Direct Object Reference**, a type of access control vulnerability.

In API systems, the issue is often called **BOLA — Broken Object Level Authorization** (OWASP API1:2023). The core issue is not whether the ID is a sequential number or a UUID, but that **the system fails to verify whether the caller has permission to perform the specific action on the specific referenced object**.

Three components of an IDOR scenario:

1. There is a **protected object**: a document, invoice, order, ticket, file, report, account, record, or folder.
2. The caller can supply or modify the **object reference**: ID, UUID, slug, filename, key, nested ID, query parameter, body field, or GraphQL argument.
3. Missing or flawed **object-level permission check**: the application accepts the ID without checking the owner, tenant, sharing group, ACL, business relationship, or corresponding action permission.

**Rule to remember:** `Authentication` answers "**Who is calling?**"; endpoint permission answers "**Can they call this function?**"; object-level authorization answers "**Can they operate on this object?**" All three questions are important and do not replace one another.

## 2. How Does IDOR Differ from Missing Authentication or Missing Role?

| Scenario | Issue | Example |
| --- | --- | --- |
| Caller is not logged in | Authentication | Request has no valid session/token |
| Regular user calls an admin-only endpoint | Broken Function Level Authorization (BFLA) | `POST /api/admin/users` does not check admin role |
| User has permission for the document reading feature but reads Bob's document | **BOLA/IDOR** | `GET /api/documents/42` only checks `authenticated()` |
| User can read the document but is allowed to edit sensitive fields | Broken Object Property Level Authorization | `PATCH` allows editing `approvedBy` despite only having content edit permission |
| List query returns data from other tenants | Object/data-scope access control failure | `GET /api/documents` does not filter by tenant |

For example, the HTTP configuration:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**").authenticated()
    .anyRequest().denyAll()
);
```

only states that requests to `/api/documents/**` must be authenticated. It **does not guarantee** that a logged-in user can read every document at every ID. Similarly, `hasAuthority("document:read")` may prove the caller has permission to read documents **functionally**, but does not prove permission on each specific document.

An IDOR flaw is not fixed by adding `@PreAuthorize("isAuthenticated()")` around a method already called by an authenticated user. You need a policy binding **caller + action + resource**.

## 3. An ID Can Be Anywhere, Not Just in the Path

All references from a request can be manipulated. Commonly overlooked places:

| Location | Example | Required Check |
| --- | --- | --- |
| Path variable | `GET /documents/42` | READ on Document 42 |
| Query parameter | `GET /export?invoiceId=42` | EXPORT on Invoice 42 |
| JSON body | `PATCH /documents {"documentId":42,"note":"..."}` | WRITE on Document 42 |
| Hidden form field | `userId=42` | Permission to edit the referenced profile |
| Nested path | `GET /projects/5/tasks/42` | Project 5, Task 42, Task–Project relationship, and permissions at both levels |
| Batch IDs | `POST /documents/bulk-delete {"ids":[41,42]}` | DELETE for each ID and the whole batch |
| Filename / object key | `GET /files?key=tenant-b/invoice.pdf` | Permission to access the file/object key for the right tenant |
| Header | `X-Organization-Id: 5` | Whether the caller has membership in organization 5 |
| GraphQL argument | `document(id:"42")` | READ on the resolver for Document 42 |
| Job/event message | Message containing `documentId=42` | Identity of the processing actor and business permissions |

An ID that appears "internal" but surfaces in a response, notification, log, screenshot, or share link can still become known to others. **Do not rely on ID secrecy as the primary authorization barrier.**

### Does UUID Eliminate IDOR?

**No.** A sufficiently strong random UUID makes guessing IDs harder and serves as *defense in depth*; however, once an attacker learns a valid UUID from an email, URL, leak, or log, the server must still check permissions. Identifiers such as hashes of sequential IDs, Base64 encodings, or simply obfuscated digits also do not replace object authorization.

The right security question is: "If this person knows the exact ID of an object belonging to someone else, can the system still block it?" If the answer is no, the application still has IDOR even if the ID is hard to guess.

## 4. Policy Formula: subject + action + object + context

A decision can be modeled as:

```text
allow = policy(
    authenticatedSubject,
    action,
    resourceIdentity,
    trustedResourceState,
    trustedSecurityContext
)
```

Where:

- **Subject**: the actual authenticated user or service principal; use a stable ID from Authentication/security context, never take a client-supplied `userId` to decide who the caller is.
- **Action**: READ, WRITE, DELETE, EXPORT, APPROVE, SHARE, ADMINISTER, or another specific permission.
- **Resource identity**: the ID/UUID/slug of the exact object the client is requesting.
- **Resource state**: tenant, owner, status, classification, project, folder, ACL, soft-delete, approval state retrieved from server-managed data.
- **Security context**: tenant memberships, scopes/authorities, delegated access, time-based applicable policies.

**A minimal condition for a private document** might be:

```text
Actor is authenticated
AND Actor has authority document:read
AND Document.id = requestedId
AND Document.tenantId belongs to a tenant that Actor actually has permission for
AND (
      Document.ownerId = Actor.subjectId
      OR ACL grants READ permission to Actor
    )
AND Document is not deleted/locked per business rules
```

This formula is an **example** policy; not every system requires an owner. Some applications allow team collaboration, tenant administrator roles, time-limited share links, or delegated permissions. When expanding, each OR branch must have strict conditions and be tested so it does not create unintended privilege escalation.

### A "Tenant" Is Not Just Whatever String the Client Claims

In many SaaS systems, requests use `X-Tenant-Id` or `/tenants/{tenantId}` to select a workspace. This field only indicates the **requested tenant**, not an authorized tenant. The server must verify the principal's membership/role in that tenant from a trusted source and scope all queries by the verified tenant.

Conditions like:

```java
if (request.getHeader("X-Tenant-Id").equals(document.getTenantId())) {
    return document;
}
```

are **insufficient**: an attacker can declare the same tenant as the target object they want to read. Even adding a `ROLE_USER` role without verifying membership leaves the vulnerability open.

## 5. Insecure Example: Finding by ID and Returning Directly

This is a common **IDOR flaw** pattern in Spring Boot:

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

The snippet above is **a Spring component**, assuming the repository/entity already exists. It does not compile standalone with plain JDK. Even if the Spring Security filter chain requires authentication, the controller still uses only the client-provided ID to look up the record.

Other issues besides IDOR:

1. **Returning the entity directly** can expose internal fields or JPA relationships that were not intentionally restricted.
2. `findById` does not check tenant, owner, ACL, or soft-delete status.
3. `orElseThrow()` has no specific exception type for the API; the HTTP status may not be what is desired.
4. Going through the controller does not guarantee that all other call paths (jobs, message listeners, service beans) are safe.

Adding `@PreAuthorize("hasAuthority('document:read')")` to the controller improves functional permissions, **but still does not prevent** user A from reading document B if both have the read authority.

## 6. Preferred Defense: Query **Within the Authorized Dataset**

OWASP recommends retrieving objects from the dataset the caller **is permitted to access**, rather than fetching from the entire database and hoping no check is missed somewhere along the way.

Replace:

```java
repository.findById(requestedId);
```

with a query constrained by trusted attributes:

```java
repository.findByIdAndTenantIdAndOwnerIdAndDeletedFalse(
    requestedId,
    verifiedTenantId,
    authenticatedSubjectId
);
```

Benefits:

- **Not found** and **found but caller lacks permission** can both return `Optional.empty`, limiting existence disclosure.
- The query keeps tenant/owner as mandatory conditions, reducing the risk that subsequent logic forgets to check.
- No need to load objects belonging to another tenant into the service just to check them afterward.
- For updates/deletes, permission conditions can be placed in the write statement, avoiding checking permission first and then writing by an unconstrained ID.

Of course, this is an owner-only policy; if ACL/group sharing exists, the query must be extended according to the exact business policy—not by simply dropping the owner condition to "fix" shared users being unable to view.

## 7. Spring Boot Example: A Scoped Document Read API

The Java snippets in this section are **component classes/methods of a single Spring Boot application using Spring Security 6.x/7.x, Spring Data JPA, and Java 17+**, not a standalone `javac` program. The `Document`, `DocumentRepository`, and identity verification service classes must be fully provided by the project.

### 7.1. ActorContext Is Server-Verified Data

```java
public record ActorContext(
    String subjectId,
    String tenantId
) {}
```

`subjectId` is a **stable** user identifier issued by the authentication system, not a `userId` sent by the client in the request body. `tenantId` must be a tenant the principal is actually permitted to use. The resolution mechanism depends on the application: session, Spring Security `Authentication`, JWT with verified signature and claims, plus server-side membership.

Example contract definition:

```java
public interface CurrentActorService {
    ActorContext requireActorInAuthorizedTenant();
}
```

This interface is **application-defined**, not a built-in Spring Security API. The implementation must retrieve the principal from a trusted `SecurityContext`, verify login status and membership in the selected tenant, and reject if invalid. Do not let the controller construct `ActorContext` from JSON data supplied by the client.

### 7.2. Repository Querying Records Within Scope

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

This derived query method requires the `Document` entity to have appropriate `id`, `tenantId`, `ownerId`, and boolean/Boolean `deleted` properties. The system must actually store tenant and owner accurately; writing the method name does not automatically create columns or protect every other query.

### 7.3. Service Protecting Both Functional Authority and Object Scope

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

This pattern protects at two layers:

- `@PreAuthorize`: the caller must have `document:read`; requires `@EnableMethodSecurity` to be enabled and the call to go through a Spring-managed proxy.
- Scoped query: the caller must be the **owner** of that exact document in the verified tenant, and the document must not be deleted.

Returning `DocumentView` ensures only necessary data is exposed rather than serializing the entire entity. The snippet above does not yet allow ACL sharing, interpret other business statuses, or define the tenant selection mechanism; those are rules that must be implemented per actual requirements, rather than loosely letting every user with a READER role read any ID.

### 7.4. Controller Does Not Decide Ownership Using Client Input

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

The controller passes the requested ID to the service, **not** passing `ownerId`/`tenantId` as proof of permission. Spring Security can require authentication at the HTTP layer; the service still protects data for call paths outside the controller.

### 7.5. Enabling Method Security

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Enabling method security is a prerequisite for `@PreAuthorize`. In Spring AOP proxy mode, calling `this.read(...)` internally within the same bean typically **bypasses advice**; do not rely solely on annotations for a call path that does not go through the proxy. Scoped queries and data constraints help provide an additional layer of protection.

## 8. Not Just READ: UPDATE and DELETE Are Even More Dangerous

Many projects protect `GET` but miss `PUT/PATCH/DELETE`. For example:

```http
PATCH /api/documents/42
Content-Type: application/json

{"title":"Changed by Alice"}
```

If the server calls `findById(42)` and `save(...)` after checking only that the user has the EDITOR role, Alice can modify Bob's document. Even with no data returned, an unauthorized side effect is still IDOR.

### Permission-Conditioned UPDATE Statement

You can update by ID **and tenant and owner**:

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

Here, the update only affects a record matching ID + tenant + owner + not deleted **simultaneously**. Cases with a different tenant, different owner, non-existent ID, or deleted state will not be updated; the API can return the same 404 for invisible resources.

**Note on JPA bulk updates:** JPQL updates bypass several standard mechanisms like dirty checking/entity lifecycle, automatic optimistic version increments, and managed entity caching. If business requirements demand optimistic locking, audit fields, validation, or entity listeners, design the update accordingly: add a `version` predicate and explicitly update the version, or perform a scoped load within a transaction, modify the managed entity, and flush. For soft-deletes or ACL-based write sharing, the condition must also express the exact policy. Do not copy this bulk update if the project needs those guarantees without adding them.

### DELETE and Non-Idempotent Operations

DELETE must check **delete permission**, not just read permission; some systems allow owners to read but only administrators to delete. For money transfers, invoice approvals, order cancellations, generating download URLs, ownership transfers, and granting share permissions, require permissions per specific **action**:

```text
canRead(actor, documentId)   != canDelete(actor, documentId)
canEdit(actor, documentId)   != canShare(actor, documentId)
canView(actor, invoiceId)    != canApprove(actor, invoiceId)
```

Checking the object only on a read endpoint and assuming all other endpoints are safe is a common source of IDOR.

## 9. Alternative: `@PreAuthorize` and Policy Beans by Resource ID

One option is to use method security to invoke a policy service:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView read(Long documentId) {
    // Business logic
}
```

This is a **fragment inside a service**. `documentPolicy.canRead(...)` is a method on an application-implemented Spring bean; it must check tenant, owner, ACL, and resource state from trusted data and return a boolean. Do not build SpEL expressions by concatenating strings directly from the request.

With Spring Security, you can use `PermissionEvaluator` via `hasPermission(#documentId, 'Document', 'READ')` or `AuthorizationManager<MethodInvocation>` when shared logic is needed across multiple methods. However, any mechanism must ensure **the exact requested resource ID** is checked, not just the role.

### A Trap: Checking Correctly First, Querying Broadly Later

Example:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public Document read(Long id) {
    return repository.findById(id).orElseThrow();
}
```

If the policy queries the DB and then the service does a broad `findById`, there are at least two things to consider:

1. **TOCTOU:** permissions or owner/tenant can change between check time and fetch/write time, especially when the check runs outside the transaction.
2. **Two queries and lack of defense in depth:** a developer might later change the policy, overload the method, or add a call path that bypasses the proxy, turning the broad query into a vulnerability.

For sensitive data, still prefer a **scoped query** at the data access point along with appropriate transactions/locking. `@PreAuthorize` helps fail early, though it is not necessarily the entire defense.

### `@PostAuthorize` Is Not a Way to Prevent Write IDOR

`@PostAuthorize("returnObject.ownerId == authentication.name")` executes **after** the method body. If the method already updated the DB and the transaction committed beforehand (depending on advisor ordering), throwing `AccessDeniedException` at the end **does not guarantee rollback** of already committed changes. Therefore, do not rely on post-checks to protect writes/deletes; verify permissions before the action and enforce constraints in the transaction/query.

## 10. What Must Be Checked in Multi-Tenant Systems

For multi-organization SaaS, checking individual ownership is not enough. A user can be a member of multiple tenants, tenants can have colliding external identifiers, and roles like `ADMIN` typically only have meaning **within a single tenant**.

The model should include:

- **Authenticated subject** stably identified, never taking `userId` from the body as the principal.
- **Active tenant** selected by the request if needed, but with **membership/role verified** on the server.
- **Row isolation**: every SELECT/UPDATE/DELETE includes a tenant condition, or a carefully designed RLS mechanism.
- **Ownership/ACL**: tenant membership does not automatically grant access to every object if owner/share policies also apply.
- **Cross-reference validation**: child resources, attachments, invoice lines, comments, and parent projects must belong to the correct scope.
- **Explicit admin bypass**: if a tenant admin can read all documents in the tenant, the bypass condition must include a tenant check, specific authority, and auditing.
- **Service identity**: scheduled jobs or message consumers also need valid scope and reason to access a tenant; "no HTTP user" must not be treated as full privilege.

### Nested Resource IDs: Verify the Relationship Too

For the endpoint:

```http
GET /api/projects/5/tasks/42
```

Verifying the user has access to Project 5 is **not enough** if Task 42 actually belongs to Project 6. A safe query must verify:

```sql
SELECT t.*
FROM tasks t
JOIN projects p ON p.id = t.project_id
WHERE t.id = :task_id
  AND p.id = :project_id
  AND p.tenant_id = :verified_tenant
  AND /* task and project membership/ACL conditions */;
```

This is **policy-illustrating SQL**; the comment must be replaced with valid business predicates, not run verbatim as a complete SQL statement. In a real service, use repository/JPA queries or DB row-level security that fully express those conditions.

Never trust the client placing `projectId=5` and `taskId=42` side by side to mean the two objects are related. The relationship must be verified from the database.

### Share Links and Delegated Permissions

A document may be shared with non-owners. In that case, instead of removing the owner condition, the policy might allow:

```text
same_verified_tenant
AND document_is_active
AND (
  owner_id = authenticated_subject
  OR active_share_grant_for_subject
  OR approved_role_in_this_tenant
)
```

Share grants need checks for expiry, permission scope, revocation, and the specific target object. If using bearer share links, tokens must have appropriate entropy, expiration, scope, and revocation/rotation by design; a secret URL is a managed delegated capability, **not a reason to skip all checks**.

## 11. Bulk Operations and Full Result Sets

Example API:

```http
POST /api/documents/bulk-export
Content-Type: application/json

{"ids":[41,42,43]}
```

Alice has permission for 41, while 42/43 belong to others. Checking only `hasAuthority("document:export")` and calling `findAllById(ids)` is **batch-form IDOR**.

Two valid designs depending on the business contract:

1. **All-or-nothing:** require all IDs to be within the permitted scope. If even one ID is out of scope, reject the entire batch with zero side effects.
2. **Controlled partial results:** return only the objects the caller is permitted to access; define the contract clearly and avoid accidentally leaking info about skipped IDs via status, count, or error body.

If all-or-nothing is required, do not just compare the post-query item count without handling duplicate IDs:

```text
requested = distinct(validatedRequestIds)
visible = query only permitted objects for those IDs

allow batch only if
    set(visible.ids) == set(requested)
```

Place verification and execution in an appropriate transaction/snapshot to prevent objects or permissions from changing between the two steps. For bulk delete/update, use a DB-scoped operation and verify the affected row count; "having validated the list beforehand" does not replace write-time protection.

A list-returning API like `GET /api/documents` must also **filter by permission before pagination/counting**. If you load all objects and filter afterward in Java, the UI may receive empty pages, wrong total counts, or sensitive data loaded where it should not be.

## 12. Other Channels Where IDOR Is Easily Missed

### 12.1. File Downloads and Object Storage

Object paths like `tenant-a/invoices/42.pdf` are also references. Do not concatenate a client-supplied file key and fetch directly from S3/GCS/filesystem. The server must determine whether the caller has permission on the **business object** and the storage key bound to that object.

If the server generates presigned URLs, check authorization **before issuing the URL**, limit TTL/permissions appropriately, and consider revocation handling since an issued URL may remain valid until expiry. Do not let shared response caches leak another user's URL.

### 12.2. GraphQL and Nested Resolvers

GraphQL may use a single shared `POST /graphql` endpoint; URL-protecting filters do not know which objects each query requests. Resolvers like `document(id)`, `project.tasks`, and `user.invoices` need object-specific permission checks. Do not just check the root user and return all related nodes without scope.

### 12.3. WebSockets, Events, Async Jobs

A message containing `documentId` is also a resource access request if an actor can control it. Do not give a job full privilege just because it lacks a web session. Use an appropriate service identity/scope, establish service principal accountability, and apply policies to the specific object. Propagating `SecurityContext` across asynchronous threads is not always automatic; test it explicitly.

### 12.4. Caches and Search Indexes

If a cache key is only `documentId` and the result was generated under Admin privileges, a regular user could receive a cached entry containing data they are not allowed to see. Caches must be scoped by tenant/principal/permission or must **check permissions on every cache hit**. Search indexes, Elasticsearch queries, and denormalized projections also need the same tenant/ACL constraints as the source DB.

### 12.5. Viewing Data Differs from Modifying Properties

Even when a user has permission on Document 42, that does not mean they can edit every field, change the owner, switch the tenant, or grant themselves permissions. Use per-action DTO allowlists, input validation, and **object property authorization**; never bind raw JSON directly into a JPA entity and call `save`.

## 13. Handling 401, 403, and 404 Without Leaking Data

When a caller accesses an unauthorized resource, the application may need to distinguish internally:

- **Unauthenticated**: no valid identity yet.
- **Forbidden**: valid identity, resource exists, but no permission.
- **Not found**: resource does not exist.
- **Dependency failure**: database/identity service error.

Common HTTP status codes:

| Case | Typical Response to Consider | Notes |
| --- | --- | --- |
| Not logged in | `401 Unauthorized` / auth challenge | Depends on AuthenticationEntryPoint and auth type |
| Logged in but missing functional authority | `403 Forbidden` | Does not necessarily reveal a specific ID |
| ID given but resource does not exist | `404 Not Found` | Resource absent |
| Resource exists but **caller is not allowed to know it exists** | Neutral `404 Not Found` | Same body/status as actually non-existent resource |
| Resource exists, caller is allowed to know it exists but cannot operate | `403 Forbidden` | Only if the product permits existence disclosure |
| Database failure or timeout | Appropriate `5xx` | Do not treat outages as 404 and do not return data |

**Do not confuse** `AccessDeniedException` from `@PreAuthorize` with `ResponseStatusException(HttpStatus.NOT_FOUND)`. A `@PreAuthorize("hasPermission(#id, ...)")` returning false typically causes method security to deny before the body runs; it does not automatically produce a 404. If an existence-hiding policy is desired, scoped lookup and explicit error mapping are usually easier to control. Do not globally convert **all** 403s into 404s.

Beyond status codes, keep response bodies, error types, headers, cache policies, and debug info neutral. If a forbidden ID returns 404 but the body says `"owner=bob"` or a header contains the real tenant, ID enumeration still exists. Large timing differences can also leak information; analyze per your threat model.

## 14. Standalone Java 17: Viewing One ID Across Multiple Users

The example below uses plain Java to **simulate** scoped object authorization. There is no Spring, database, OAuth2, or HTTP server. The goal is to illustrate that the same ID can be valid for the owner yet invalid for others, and that a WRITE operation requires a different permission from READ.

Save to `IdorDefenseDemo.java`:

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

Compile and run with JDK 17 or later:

```bash
javac IdorDefenseDemo.java
java IdorDefenseDemo
```

Exact stdout:

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

**Key takeaways from the output:**

- Alice has both READ and WRITE yet **cannot** operate on Bob's document or another tenant's document.
- Bob can read his own document because he has READ, but cannot edit it because he lacks WRITE.
- Non-existent IDs and real IDs outside Alice's scope both return `404` in this model.
- Unauthorized update attempts do not alter Bob's note.
- The ID is checked on **each READ/WRITE call**, not only at login.

**Limitation:** An in-memory `Map` in a Java demo provides no transactions, locking, concurrency control, or DB row-level security. In a real application, checking + updating must use proper transactions/conditional SQL to prevent races. Do not copy a `Map`-backed service into production instead of a real repository.

## 15. IDOR/BOLA Testing Matrix

### 15.1. Preparing Control Identities and Resources

Create intentional test data:

- Alice in tenant A, owner of Document 41; has `document:read`, `document:write`.
- Bob in tenant A, owner of Document 42; has `document:read`, does not have `document:write`.
- Carol in tenant B, owner of Document 43; has full permissions but in another tenant.
- One soft-deleted document, one document shared with READ to Alice, one non-existent document.
- One admin in tenant A and one admin in tenant B; admin privileges must have clear scope.

Do not test with only one user. OWASP recommends using at least two accounts/permission scopes and **swapping resource identifiers between sessions**.

### 15.2. API Matrix

| Request | Actor | Key Expectation |
| --- | --- | --- |
| `GET /documents/41` | Alice | 200, only permitted data for 41 |
| `GET /documents/42` | Alice | 403 or 404 per policy, none of Bob's content |
| `GET /documents/43` | Alice | Denied due to different tenant |
| `GET /documents/99` | Alice | 404 or matching contract |
| `GET /documents/41` | Unauthenticated | 401 / designed login flow |
| `PATCH /documents/42` | Alice | Does not modify Bob's database record |
| `DELETE /documents/42` | Alice | Does not delete/soft-delete Bob's document |
| `PATCH /documents/42` | Bob with READ only | Does not write because WRITE permission is missing |
| `GET /projects/5/tasks/42` | Alice; task belongs to another project | Denied; do not only check projectId |
| `POST /bulk-export` with IDs 41,42 | Alice | Per contract all-or-nothing or only 41; must not export 42 |
| `GET /documents` | Alice | Query, count, and pagination reflect only visible data |
| Download tenant B's key | Alice | Does not issue accessible file/URL |
| Share/transfer owner of 41 | Alice lacking SHARE/ADMIN | Does not change ACL/owner |
| ID is Bob's real UUID | Alice | Still denied, even though ID is hard to guess |
| Access from non-HTTP service/job | Insufficiently privileged identity | Policy at service/repository still applies |

### 15.3. Testing Real Spring Security, Not Just Mocking the Policy

You can use `@SpringBootTest`/`MockMvc` and `spring-security-test`, or HTTP tests against a running server. Assert **returned data, HTTP status, and database side effects**, not merely the boolean return value of a helper.

An example test fragment for an API **with security context and actor fixtures properly configured**:

```java
mockMvc.perform(get("/api/documents/{id}", 42L)
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("document:read"))))
    .andExpect(status().isNotFound());
```

This is a test **fragment**, not standalone compilable; it requires static imports `get`, `user`, `status`, a `mockMvc` bean, and appropriate `CurrentActorService` mapping. Under an existence-hiding policy, 404 is expected; if the policy uses 403 for forbidden resources, the test must adjust accordingly. What matters is never returning unauthorized data.

**Do not use `@WithMockUser(username="alice")` and assume production identity tokens also map to subjectId `alice`**. If production uses JWT `sub`, a custom principal, a tenant membership database, or service tokens, tests must initialize matching context/claims to exercise the real code path.

### 15.4. Negative and Race Tests

Tests should include:

1. Using a valid object ID belonging to **someone else in the same tenant**.
2. Using an ID belonging to **another tenant**, even when the user holds the general authority.
3. Using an ID that appeared in someone else's link, email, or response.
4. For nested IDs, swapping the ID **at each level**; a Task not belonging to the Project in the URL must still be blocked.
5. For batches, injecting **one** unauthorized ID into a set of valid IDs.
6. For DELETE/PATCH/APPROVE/EXPORT, verifying the database, events, and file storage have **no side effects** on deny.
7. For pagination, filters, and counts, ensuring unauthorized resource counts are not leaked.
8. For cache hits, verifying permissions are still enforced; never serve an admin's cached result to a regular user.
9. For revoked permissions, ensuring caches and tokens do not retain permissions beyond the designed window.
10. For concurrent changes to owner/tenant/ACL and updates, ensuring transactions/locking/conditional DML prevent races.
11. When the DB/authorization service fails, ensuring the application **does not fail open**; return a safe error and monitor properly.
12. When a service is called by another bean or message listener, verifying the policy still applies; never skip it just because it bypassed the HTTP filter.
13. For optimistic locking, ensuring an update with a stale version cannot overwrite newer changes.
14. If the API supports share links/temporary tokens, testing expired, revoked, wrong-resource, and wrong-action links.

### 15.5. Automated Security Testing in CI

Whenever adding an endpoint that accepts an object reference, write at least one **ID-swap** test between two real principals in the test fixture. This is easier to review than a test that only verifies the happy path. You can combine SAST/DAST to detect `@PathVariable` → repository `findById` flows or endpoints with body IDs, though automation does not replace business policy analysis.

An even better level is testing the **invariant**: for every actor A and resource B for which A has no permission, every READ/WRITE/DELETE/EXPORT action must return no unauthorized data and cause no unauthorized side effect.

## 16. Common Mistakes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| "Logged in means allowed to view objects by ID" | Authentication does not prove object permission | Check subject + action + resource |
| "Has ROLE_USER/EDITOR so can edit any ID" | Roles only convey functional privileges | Add owner/tenant/ACL/membership and exact action |
| Using `repository.findById(id)` on private data paths | Reads/writes objects outside scope | Scoped repository query or policy before returning data |
| Accepting `ownerId` from JSON and comparing with document | Client can claim any owner | Derive subject from verified Authentication |
| Trusting `X-Tenant-Id` as proof of tenant membership | User can tamper with the header | Verify tenant membership server-side |
| Switching sequential IDs to UUIDs and stopping there | UUIDs can be leaked or shared | Enforce object authorization for every ID |
| Protecting only GET while skipping PATCH/DELETE/EXPORT | Attackers can still edit/delete/fetch others' files | Audit all actions carrying an object reference |
| Checking only the parent ID of a nested route | Child ID may belong to a different parent | Join the exact relationship and check permissions at every required level |
| Checking only one representative ID in a batch | Other IDs in the batch may be unauthorized | Validate the entire set and enforce at execution time |
| Using `@PostAuthorize` to protect writes | Side effects may commit before deny | Pre-check + scoped mutation/transaction |
| Using method security but calling `this.securedMethod()` | Bypasses Spring AOP proxy | Call via Spring bean, enforce policy at data access |
| Sharing cache keys across multiple tenants | Another tenant's result or file gets returned | Partition cache / enforce permission check on hit |
| Returning 404 with a body saying "belongs to Bob" | Still leaks existence and owner | Neutral error contract, audit internal reason |
| Swallowing DB errors and granting access | Fail open | Fail closed and handle infrastructure errors separately |
| Serializing JPA entities directly | May expose sensitive fields/relations | DTO allowlist and field-level authorization |
| Filtering data after pagination | Counts/pages may leak unauthorized signals | Scope directly inside the query and count |
| Assuming every service invocation has an HTTP SecurityContext | Jobs/async/other threads lack the expected auth | Explicitly design service identity and context propagation |

## 17. Review Checklist for Every Endpoint with a Resource Identifier

Before merging an API or service method, be able to answer these questions:

1. **Where does the resource reference appear?** Path, query, body, form, header, GraphQL, event, or object storage key?
2. **Where does the subject come from?** Server-verified Authentication/session/token, or a caller-supplied value?
3. **What is the actual action?** Read, edit, delete, approve, export, share, move, transfer ownership?
4. **Is the functional permission checked?** For example, `document:read` does not substitute for `document:write`.
5. **Is the specific object permission checked?** Verify exact ID, tenant, owner, membership, ACL, and state.
6. **Does the child resource actually belong to the parent in the request?** Do not merely trust two IDs appearing in the same URL.
7. **Is the query constrained to permitted data?** Avoid broad `findById` for private resources.
8. **Does the permission check remain valid under concurrent data changes?** Transactions, conditional updates, version/locking.
9. **Do all call paths pass through protection?** Controllers, other services, batches, jobs, async tasks, cache hits.
10. **If the ID is unauthorized, are there any side effects or leaked data?** Test responses, DB, files, and events.
11. **Do HTTP 403/404 responses reflect the existence-disclosure policy?** Do not leak via body/headers/counts.
12. **Was it tested with at least two users/tenants and swapped IDs?** Not just the happy path.
13. **Are UUIDs used as defense in depth rather than replacing authorization?** Hard to guess does not mean inaccessible.
14. **Are any administrative/emergency actions exempt from checks?** Override privileges require separate scope, approval, and audit.
15. **Are role/ACL changes reflected immediately in data/caches at the required level?** Permission revocation is also a test path.

**Summary:** IDOR/BOLA occurs when an application assumes that knowing a **resource identifier** means being allowed to access that resource. Proper defense means **checking permissions for each object and each action, server-side, using trusted identity and data**, while constraining queries/writes to tenant/owner/ACL scope. Authentication, roles, UUIDs, hiding IDs, and neutral 404s all help, but **do not replace** object-level authorization.

## References

- [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): IDOR definition, scoped lookup, Java/Spring examples, and multi-account testing.
- [OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): requirement to check permissions on every object ID across all endpoints.
- [OWASP REST Assessment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Assessment_Cheat_Sheet.html): ID swapping across sessions, especially GET/PUT/PATCH/DELETE and nested routes.
- [OWASP Web Security Testing Guide — Broken Object Level Authorization](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/12-API_Testing/02-API_Broken_Object_Level_Authorization/): BOLA testing model.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, custom policy beans, and method proxies.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP request authorization does not automatically replace resource policies.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries and `@Query` to constrain returned data.
