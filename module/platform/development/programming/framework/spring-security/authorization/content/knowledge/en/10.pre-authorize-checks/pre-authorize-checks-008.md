# Combining Roles with Resource Ownership

## 1. Problem: same role, yet different permissions on an object

In Spring Security, a user may hold a valid role or permission and still **not be allowed** to read, edit, or delete a specific resource. A role describes responsibilities and functional capabilities; ownership describes the relationship between **a principal** and **a record**.

Suppose a document system has:

- Alice is the owner of document 42 in tenant A; she has `document:read` and `document:update`.
- Bob also has `document:read` and belongs to tenant A, but does not own document 42.
- Carol is an administrator of tenant A, holding `ROLE_TENANT_ADMIN` and `document:read`.
- David is an administrator of tenant B, holding the exact same role and permission names as Carol.

If the service only checks:

```java
@PreAuthorize("hasAuthority('document:read')")
public DocumentView read(UUID documentId) {
    // ...
}
```

then all four can pass **the functional permission check**, even though Bob has not been shared the document and David belongs to another tenant. If the code below calls `findById(documentId)` without tenant/owner scoping, this creates a Broken Object Level Authorization (BOLA) risk, also known as IDOR in many contexts.

The solution is to combine multiple conditions **before the method executes**:

```text
ALLOW_READ(document, actor) =
   authenticated
   AND activeAccount
   AND has(document:read)
   AND sameTenant(actor, document)
   AND (
        isOwner(actor, document)
        OR hasValidReadShare(actor, document)
        OR isTenantAdmin(actor)
   )
```

The `sameTenant` condition applies to **every branch inside the parentheses**. Thus David cannot read tenant A documents just by holding the admin role in tenant B. If the system genuinely has a global admin, that exception must be defined separately with heightened controls, never appearing accidentally through an OR clause.

**Lesson goal:** understand roles/authorities, ownership, tenants, and state; write safe `@PreAuthorize` expressions; extract policy bean logic; handle TOCTOU when data mutates; and test denied scenarios as well.

### Defense-in-depth layers diagram

```text
HTTP API / Web / GraphQL / Job
              |
              v
    Verified Authentication
              |
              v
      @PreAuthorize
       role / authority
       + object policy
              |
          +---+---+
          |       |
         DENY    ALLOW
                  |
                  v
           Service method
                  |
                  v
           Repository / DB
        tenant-scoped query
        conditional update
        version / transaction
```

HTTP-layer request matchers classify paths and actions. Method security binds policies to a use case invoked across multiple entrypoints. Repositories and transactions continue protecting data at execution time. No single layer should be assumed to replace all the others.

## 2. Concepts: roles, permissions, owners, tenants, and ACLs

### 2.1. Role / authority

A role such as `ROLE_USER`, `ROLE_EDITOR`, or `ROLE_TENANT_ADMIN` typically defines a user's assigned function. In Spring Security, roles are represented as `GrantedAuthority`; under the default prefix:

```java
hasRole('ADMIN')                  // requires ROLE_ADMIN
hasRole('TENANT_ADMIN')           // requires ROLE_TENANT_ADMIN
hasAuthority('ROLE_TENANT_ADMIN') // exact authority name
hasAuthority('document:read')     // exact permission
```

Do not assume `SCOPE_documents.read` in a JWT is identical to `document:read`. Mapping scopes/claims to authorities must be explicitly designed and rely on tokens verified for issuer, signature, audience, and expiration.

**Role hierarchy** can expand reachable authorities: for example `ROLE_ADMIN > ROLE_EDITOR`. However, a role hierarchy does not know which document belongs to Alice, nor Carol's tenant membership. It must be combined with real resource relationships.

### 2.2. Ownership

Ownership is commonly modeled by a database field:

```text
documents.owner_id == verifiedActor.userId
```

Depending on the system, ownership can be nuanced: documents belonging to a team, multiple co-owners, transferred ownership, organization-owned resources, or time-bound delegated rights. Thus object-level permission rules must reflect the **data model** rather than merely comparing `authentication.name` against a client-sent string.

A user may be the owner yet have an inactive account, revoked permissions, or a locked document. Being owner does not necessarily grant all of read, edit, approve, and delete; that is a policy decision.

### 2.3. Tenant / organization / project

A tenant is a data-scope boundary. When a principal belongs to multiple tenants, the app may let them pick an “active tenant”, but must **verify membership** before using that choice in queries.

For instance, a tenant A admin does not automatically administer tenant B. Identical role names are insufficient to express scope. Tenant-scoped grants, organization mappings, or server-side policies checking membership may be required.

### 2.4. Sharing and ACLs

A document may be shared with Bob via an ACL:

```text
document=42, recipient=bob, permission=READ, expiresAt=...
```

Sharing read access does not imply permission to edit or delete. ACL checks must verify revocation status, expiration, tenant, and grantor source. Never use a client-supplied boolean `shared=true` instead of querying the sharing table.

### 2.5. Resource state

A `DRAFT` document may be edited, whereas `APPROVED` or `LOCKED` documents cannot be modified even by the owner/admin. This is a **business invariant**, not a static authority.

| Condition | Trusted source | Scope |
| --- | --- | --- |
| `ROLE_TENANT_ADMIN` | Verified authentication/authority mapper | Functional role per tenant |
| `document:read` | Verified `GrantedAuthority` | Permission to read resource type |
| `ownerId` | DB/domain model | Specific document |
| `tenantId` | Membership + DB record | Scope boundary |
| `sharePermission` | Application ACL/DB | Object-level sharing relationship |
| `status` / `version` | DB at processing time | Validity and data concurrency |

## 3. Writing proper expressions: AND, OR, and parentheses

### 3.1. Common mistake

```java
@PreAuthorize(
    "hasRole('TENANT_ADMIN') or " +
    "@documentPolicy.isOwner(authentication, #documentId)"
)
```

This expression can allow **anyone with ROLE_TENANT_ADMIN** to bypass the owner gate, including admins from other tenants, if no other guard exists. It can also skip checking `document:read` or account status.

Another mistake:

```text
(has(document:read) AND sameTenant AND isOwner)
OR has(ROLE_TENANT_ADMIN)
```

The admin branch sits outside the tenant constraint. Without an explicit business reason, this creates unintended privilege escalation.

### 3.2. Correct conditions per chosen goal

```text
has(document:read)
AND sameTenant
AND (isOwner OR sharedRead OR isTenantAdmin)
```

For update operations:

```text
has(document:update)
AND sameTenant
AND (isOwner OR isTenantEditor)
AND document.status == DRAFT
```

Parentheses clarify the scope of OR, while tenant/permission/status remain shared requirements. **Adding an admin role branch must never drop the shared constraints.**

### 3.3. When is an admin exempt from a functional permission?

An organization may require admins to view documents in their tenant even without `document:read`. The policy must express that exception explicitly:

```text
sameTenant
AND (
      (has(document:read) AND (isOwner OR sharedRead))
      OR
      (has(ROLE_TENANT_ADMIN) AND adminReadAllowed)
    )
```

Here `adminReadAllowed` is a concrete rule: it might check document class, MFA/step-up, support case, auditing, time window, or limits. Never turn the admin role into a blanket “backdoor” in every policy.

If a **global admin** is ever permitted to cross tenants, it must be a dedicated mechanism with heightened conditions and auditing, never implicitly granted by a role named ADMIN.

### 3.4. Decision table

| Caller | document:read | Same tenant | Owner/share | Tenant admin | Allow read? |
| --- | --- | --- | --- | --- | --- |
| Alice, owner | Yes | Yes | Yes | No | Yes |
| Bob, shared | Yes | Yes | Yes | No | Yes |
| Regular user, unshared | Yes | Yes | No | No | No |
| Carol, tenant A admin | Yes | Yes | No | Yes | Yes |
| David, tenant B admin | Yes | **No** | No | Yes | **No** |
| Alice, read permission revoked | No | Yes | Yes | No | **No** |
| User from another tenant forging owner | Yes | **No** | Yes (forged) | No | **No** |
| Anonymous | No | No | No | No | No |

Do not test only the ALLOW rows; DENY rows are essential to prove there are no broken ORs or missing tenant guards.

## 4. Using @PreAuthorize to block before service calls

### 4.1. Enabling method security

In Spring Security Servlet 6.x, declare:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` enables `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter` by default. Installing Spring Security Starter alone does not turn on method gates. `@Secured` and JSR-250 annotations require separate flags if used.

When a call goes through the Spring AOP proxy to a method with `@PreAuthorize`, the interceptor uses `Authentication` and method parameters to evaluate the expression. If denied, the method does not run via that intercepted path.

### 4.2. Expression pattern separating permission and object policy

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView readDocument(UUID documentId) {
    // ...
}
```

Parts:

- `hasAuthority('document:read')` requires the functional permission.
- `@documentPolicy` is the Spring bean named `documentPolicy`.
- `authentication` is the `Authentication` in the method-security evaluation context.
- `#documentId` references the method argument bound by name.
- `canRead` verifies owner/share/admin **within the verified tenant**.

Keep only a short expression on the annotation, while placing data logic in a unit-testable Java policy bean. This is **illustrative integration code**, not a standalone Java program.

### 4.3. Read and write should be separate policies

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView readDocument(UUID documentId) { ... }

@PreAuthorize(
    "hasAuthority('document:update') and " +
    "@documentPolicy.canEdit(authentication, #documentId)"
)
public void renameDocument(UUID documentId, String newName) { ... }
```

Being shared READ does not grant UPDATE. Even a user with UPDATE must be blocked if the document is LOCKED. Delete, approve, export, share, or ownership transfer should each have dedicated risk-appropriate policies.

### 4.4. Reliable SpEL parameter binding

Spring Security can discover parameter names from the `-parameters` compiler flag, Spring Security `@P`, or compatible metadata. Example independent of Java argument names:

```java
import org.springframework.security.access.method.P;

@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView readDocument(@P("documentId") UUID id) {
    return repository.readScoped(id);
}
```

`@P("documentId")` lets the expression use `#documentId` even though the Java argument is named `id`. This code fragment requires real repository/bean/domain types and will not compile standalone with `javac`. If relying on Java names directly, enable and verify `-parameters` in the production build.

### 4.5. Do not query the DB three times just to check one document

A long expression:

```java
@PreAuthorize(
    "@documentPolicy.sameTenant(authentication, #documentId) and " +
    "@documentPolicy.isOwner(authentication, #documentId) and " +
    "@documentPolicy.isEditable(#documentId)"
)
```

can cause three methods to query the DB separately and observe inconsistent states. Adding an admin OR branch compounds complexity further. Cleaner:

```java
@PreAuthorize(
    "hasAuthority('document:update') and " +
    "@documentPolicy.canEdit(authentication, #documentId)"
)
```

The policy bean loads a single appropriate access projection and combines all conditions. Even so, pre-checks do not lock the resource until the DB update; transactional guards remain necessary.

## 5. Designing a secure policy bean

### 5.1. Untrusted client inputs

Request:

```http
PUT /api/documents/42 HTTP/1.1
Content-Type: application/json
X-User-Id: alice
X-Tenant-Id: tenant-A

{"ownerId":"alice","tenantId":"tenant-A","title":"changed"}
```

**None of the lines above prove the caller is Alice or belongs to tenant A.** Headers and bodies can be forged by the client. If a controller copies `ownerId` into a request attribute and the policy reads that attribute, the data source is still unverified.

Identity comes from a verified token/session/IdP converted into `Authentication`. If a tenant is selected from the request, check membership against the verified principal and use an appropriate server-side tenant context.

### 5.2. Access facts and actor context

A project can define:

```java
record VerifiedActor(
    String userId, String tenantId,
    boolean active, Set<String> authorities
) {}

record DocumentAccessFacts(
    UUID id, String tenantId, String ownerId,
    Set<String> sharedReaders, String status, long version
) {}
```

These are **illustrative domain types**. Implement `ActorResolver` per your authentication system and `DocumentAccessRepository` against the real database. The name `VerifiedActor` is only justified when constructed after identity/tenant verification steps, never populated from request headers.

### 5.3. A policy bean with two independent methods

Example **Spring Boot 3 / Spring Security 6.x integration skeleton**, using project-implemented interfaces:

```java
import java.util.Optional;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final ActorResolver actors;
    private final DocumentAccessRepository documents;

    public DocumentPolicy(
            ActorResolver actors,
            DocumentAccessRepository documents) {
        this.actors = actors;
        this.documents = documents;
    }

    public boolean canRead(
            Authentication authentication, UUID documentId) {
        if (documentId == null) {
            return false;
        }

        Optional<VerifiedActor> resolved =
            actors.resolveVerified(authentication);

        if (resolved.isEmpty() || !resolved.get().active()) {
            return false;
        }

        VerifiedActor actor = resolved.get();
        Optional<DocumentAccessFacts> facts =
            documents.findAccessFacts(
                documentId, actor.tenantId()
            );
        if (facts.isEmpty()) {
            return false;
        }

        DocumentAccessFacts doc = facts.get();
        boolean owner =
            actor.userId().equals(doc.ownerId());
        boolean shared =
            doc.sharedReaders() != null
            && doc.sharedReaders().contains(actor.userId());
        boolean admin =
            actor.authorities() != null
            && actor.authorities()
                .contains("ROLE_TENANT_ADMIN");

        // document:read permission is checked in @PreAuthorize.
        // Tenant is already constrained in the repository query.
        return owner || shared || admin;
    }

    public boolean canEdit(
            Authentication authentication, UUID documentId) {
        if (documentId == null) {
            return false;
        }

        Optional<VerifiedActor> resolved =
            actors.resolveVerified(authentication);
        if (resolved.isEmpty() || !resolved.get().active()) {
            return false;
        }

        VerifiedActor actor = resolved.get();
        Optional<DocumentAccessFacts> facts =
            documents.findAccessFacts(
                documentId, actor.tenantId()
            );
        if (facts.isEmpty()) {
            return false;
        }

        DocumentAccessFacts doc = facts.get();
        boolean owner =
            actor.userId().equals(doc.ownerId());
        boolean editor =
            actor.authorities() != null
            && actor.authorities()
                .contains("ROLE_TENANT_EDITOR");

        return "DRAFT".equals(doc.status())
            && (owner || editor);
    }
}
```

For real deployment:

1. `ActorResolver.resolveVerified(...)` must reject anonymous/inactive/unknown principals and verify tenant membership. Do not merely read `authentication.getName()` and assume it is a globally unique user ID if the app spans multiple realms/issuers.
2. `findAccessFacts(documentId, actor.tenantId())` must query **both the ID and the verified tenant**, never a client-supplied tenant.
3. `sharedReaders` must come from active ACL/share records; the shortened example omits expiry/revocation for readability.
4. Every role issued by authentication must be properly scoped; `ROLE_TENANT_ADMIN` cannot span all tenants.
5. `canEdit` also requires `document:update` on the annotation, while reading requires `document:read`.
6. Even though the policy takes a snapshot, writes still need DB-level guards against data races.

### 5.4. No record, no access

If `documents.findAccessFacts(...)` returns empty because the ID does not exist, the tenant mismatches, or ACLs fail, the policy must deny. Never “fallback allow” on DB timeouts, missing context, or failed membership lookups. HTTP may return 403 or 404 per threat model, yet internally access must never be granted when conditions cannot be verified.

### 5.5. Scoped queries for reads

Conceptual SQL example:

```sql
SELECT id, tenant_id, owner_id, status, version
FROM documents
WHERE id = :documentId
  AND tenant_id = :verifiedTenantId;
```

For list/search/export, push owner/share/admin scoping down into the query instead of fetching all records and filtering in Java:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :verifiedTenant
  AND (
       d.owner_id = :verifiedUser
       OR EXISTS (
           SELECT 1
           FROM document_shares s
           WHERE s.document_id = d.id
             AND s.recipient_id = :verifiedUser
             AND s.permission = 'READ'
             AND s.revoked_at IS NULL
       )
       OR :verifiedTenantAdmin = TRUE
  );
```

`verifiedTenant`, `verifiedUser`, and `verifiedTenantAdmin` come from verified server state. The SQL is an illustrative model; exact syntax/schema depend on the DB. Functional permissions still must be checked in the service. Never use a client-supplied boolean `isAdmin` parameter.

## 6. Integrating into services without bypassing method gates

### 6.1. Service using @PreAuthorize

```java
import java.util.UUID;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public DocumentView read(@P("documentId") UUID id) {
        // Repository must enforce server-verified tenant scope.
        return repository.readScoped(id);
    }

    @PreAuthorize(
        "hasAuthority('document:update') and " +
        "@documentPolicy.canEdit(authentication, #documentId)"
    )
    public void rename(
            @P("documentId") UUID id, String newName) {
        // In practice use conditional UPDATE on tenant/status/version.
        repository.renameConditionally(id, newName);
    }
}
```

This is **skeleton code**, incomplete until `DocumentRepository` and domain types are implemented. Repository methods must accept or retrieve the verified tenant properly; `readScoped(id)` must never devolve into an unscoped `findById(id)` relying solely on the annotation.

### 6.2. Self-invocation is a common bypass path

```java
@Service
class BulkDocumentService {

    public void renameAll(List<UUID> ids) {
        for (UUID id : ids) {
            renameOne(id); // internal this.renameOne(...)
        }
    }

    @PreAuthorize(
        "@documentPolicy.canEdit(authentication, #id)"
    )
    public void renameOne(UUID id) {
        // Modifies sensitive data
    }
}
```

In common Spring AOP proxy mode, internal calls on the same instance may **bypass the proxy**, causing `@PreAuthorize` to be skipped. Design clean service boundaries, invoke through advised Spring-managed beans, and retain data-layer checks/constraints. Annotations on private methods or `new`-created objects are not reliable proxy gates.

### 6.3. Class-level override is not AND

```java
@PreAuthorize("hasAuthority('document:read')")
@Service
class DocumentQueryService {

    public DocumentView get(UUID id) { ... }

    @PreAuthorize("hasRole('TENANT_ADMIN')")
    public List<DocumentView> auditAll() { ... }
}
```

When a method has its own `@PreAuthorize`, it can **override** the same-type rule on the class. Do not expect `auditAll()` to enforce both admin role and `document:read` simply because the class is annotated. If both are needed, write a single `and` expression or use a combined policy bean.

Never stack two different `@PreAuthorize` annotations on the same method expecting the framework to AND them. Spring Security does not support repeating annotations of the same type that way.

## 7. TOCTOU: pre-method authorization vs. state at write time

### 7.1. A typical race condition

At 10:00:00.100, `@documentPolicy.canEdit(...)` checks:

```text
document=42
tenant=T1
owner=alice
status=DRAFT
version=7
ALLOW
```

Immediately afterward, another transaction moves the document to `APPROVED` or transfers ownership at version 8. Alice's update service then executes after the check. If the DB UPDATE filters only by ID, data can be modified even though state/permissions no longer qualify.

This is **Time Of Check To Time Of Use (TOCTOU)**. `@PreAuthorize` gates the call before the method, yet **does not lock DB rows or guarantee permissions remain valid until commit**.

### 7.2. Conditional update

Illustrative SQL pattern:

```sql
UPDATE documents
SET title = :newTitle,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :verifiedTenant
  AND version = :expectedVersion
  AND status = 'DRAFT'
  AND (
      owner_id = :verifiedUser
      OR :verifiedTenantEditor = TRUE
  );
```

Evaluating affected row count:

- 1: conditions held at UPDATE time and data was modified.
- 0: record missing, wrong tenant, wrong owner/editor, status no longer DRAFT, or version changed.
- Never interpret 0 as “still allowed because the earlier pre-check passed”.

With sharing, dynamic roles, or revoked memberships, additional consistent queries/locks/transactions may be required. The `verifiedTenantEditor` flag is server-side, never taken directly from the request.

### 7.3. Read policies differ from write policies

For read-only methods, locking resources may be unnecessary, though data scoping remains mandatory. For delete/payment/approve/ownership transfer, pre-method checks are **necessary yet insufficient**. Enforce transaction invariants, idempotency on retries, and valid side effects. For example, if ownership changed between request start and write, the UPDATE guard must catch it.

### 7.4. Permissions changing during long-running tasks

An export job queued while a user had permission may run 15 minutes later after revocation. Whether to re-check permissions at execution time or honor a time-bounded snapshot is a business policy choice. `@PreAuthorize` on the HTTP job-creation endpoint does not automatically protect the worker or file download URL. Background job service/data policies and principal/tenant models must be designed independently.

## 8. Standalone Java 17 program: roles, owners, and tenants

This program requires no Spring and simulates no JWT/sessions. It mirrors the exact predicates of this lesson so you can run it with JDK 17+:

- Read when active, holding `document:read`, in the same tenant, and either owner, shared reader, or tenant admin.
- Edit when active, holding `document:update`, in the same tenant, not locked, and either owner or tenant admin.
- Admins from other tenants stay out of scope.
- Owners lacking the permission cannot read automatically.
- Null/missing inputs are denied by default.

Save `DocumentRoleOwnershipDemo.java`:

```java
import java.util.Set;

public class DocumentRoleOwnershipDemo {

    record Actor(
        String id, String tenant, Set<String> grants,
        boolean active
    ) {}

    record Document(
        String id, String tenant, String owner,
        Set<String> readers, boolean locked
    ) {}

    static boolean has(Actor actor, String permission) {
        return actor != null && actor.active()
            && actor.grants() != null
            && actor.grants().contains(permission);
    }

    static boolean sameTenant(Actor actor, Document doc) {
        return actor != null && doc != null
            && actor.tenant() != null
            && actor.tenant().equals(doc.tenant());
    }

    static boolean owner(Actor actor, Document doc) {
        return actor != null && doc != null
            && actor.id() != null
            && actor.id().equals(doc.owner());
    }

    static boolean shared(Actor actor, Document doc) {
        return actor != null && doc != null
            && actor.id() != null
            && doc.readers() != null
            && doc.readers().contains(actor.id());
    }

    static boolean tenantAdmin(Actor actor) {
        return has(actor, "ROLE_TENANT_ADMIN");
    }

    static boolean canRead(Actor actor, Document doc) {
        return doc != null
            && has(actor, "document:read")
            && sameTenant(actor, doc)
            && (owner(actor, doc) || shared(actor, doc)
                || tenantAdmin(actor));
    }

    static boolean canEdit(Actor actor, Document doc) {
        return doc != null
            && has(actor, "document:update")
            && sameTenant(actor, doc)
            && !doc.locked()
            && (owner(actor, doc) || tenantAdmin(actor));
    }

    static void show(String label, boolean result) {
        System.out.println(label + ": " + result);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "T1",
            Set.of("document:read", "document:update"), true
        );
        Actor bob = new Actor(
            "bob", "T1",
            Set.of("document:read"), true
        );
        Actor admin = new Actor(
            "maria", "T1",
            Set.of("ROLE_TENANT_ADMIN", "document:read",
                   "document:update"), true
        );
        Actor remoteAdmin = new Actor(
            "max", "T2",
            Set.of("ROLE_TENANT_ADMIN", "document:read",
                   "document:update"), true
        );
        Actor ownerNoRead = new Actor(
            "alice", "T1", Set.of("document:update"), true
        );
        Actor adminNoRead = new Actor(
            "maria", "T1", Set.of("ROLE_TENANT_ADMIN"), true
        );
        Actor inactive = new Actor(
            "alice", "T1",
            Set.of("document:read", "document:update"), false
        );
        Actor auditor = new Actor(
            "auditor", "T1", Set.of("document:read"), true
        );

        Document doc = new Document(
            "d1", "T1", "alice", Set.of("bob"), false
        );
        Document locked = new Document(
            "d2", "T1", "alice", Set.of(), true
        );
        Document foreignDoc = new Document(
            "d3", "T2", "foreignOwner", Set.of(), false
        );

        show("alice reads owned", canRead(alice, doc));
        show("alice edits owned", canEdit(alice, doc));
        show("bob reads shared", canRead(bob, doc));
        show("bob edits shared", canEdit(bob, doc));
        show("admin reads same tenant", canRead(admin, doc));
        show("admin edits same tenant", canEdit(admin, doc));
        show("remote admin reads", canRead(remoteAdmin, doc));
        show("remote admin edits", canEdit(remoteAdmin, doc));
        show("alice reads foreign", canRead(alice, foreignDoc));
        show("owner missing read", canRead(ownerNoRead, doc));
        show("admin missing read", canRead(adminNoRead, doc));
        show("inactive owner reads", canRead(inactive, doc));
        show("unshared auditor reads", canRead(auditor, locked));
        show("admin edits locked", canEdit(admin, locked));
        show("owner edits locked", canEdit(alice, locked));
        show("missing document", canRead(alice, null));
        show("missing actor", canRead(null, doc));
    }
}
```

Run:

```bash
javac DocumentRoleOwnershipDemo.java
java DocumentRoleOwnershipDemo
```

Designed stdout:

```text
alice reads owned: true
alice edits owned: true
bob reads shared: true
bob edits shared: false
admin reads same tenant: true
admin edits same tenant: true
remote admin reads: false
remote admin edits: false
alice reads foreign: false
owner missing read: false
admin missing read: false
inactive owner reads: false
unshared auditor reads: false
admin edits locked: false
owner edits locked: false
missing document: false
missing actor: false
```

Explanation:

1. Alice has read/update and owns an unlocked document: both actions are valid.
2. Bob has read and a READ share, yet lacks UPDATE: read true, edit false.
3. Maria has the admin role and matching permissions **within tenant T1**; can read/edit T1 documents without being owner.
4. Max is also a tenant admin yet belongs to tenant T2, so both actions on T1 documents are false.
5. An owner lacking `document:read` or an admin lacking read permission cannot read either because the sample policy mandates both permission and relationship.
6. Inactive owner is denied despite matching `id`.
7. Auditor has read permission yet is not owner/shared/admin: false.
8. LOCKED blocks updates from both owner and admin.
9. Missing actor/document: denied by default.

The standalone Java snippet uses records and Sets without Spring AOP or real JWT validation. If `grants` were constructed from client headers in a real app, security would collapse immediately; here it merely represents **simulated verified authorities** in a learning model.

## 9. @PostAuthorize, PermissionEvaluator, and authorization managers

### 9.1. Comparing pre/post method

Spring Security supports:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.owner == authentication.name")
public DocumentView readDocument(UUID id) {
    // Load record to return.
}
```

The pre-gate requires the permission; the post-gate verifies ownership on the return object. Yet the method has already executed before `@PostAuthorize` runs:

- For pure reads, it can serve as an extra defense layer.
- For writes/payments/emails, post-method denial can be too late.
- Null/collection `returnObject` or proxy structures require different expressions.
- A bare owner condition still lacks tenant, sharing, and admin roles when business logic requires them.

Hence this lesson's goal is combining permissions and ownership **before the call** with `@PreAuthorize` and policy beans, while enforcing data constraints at execution time.

### 9.2. hasPermission

An alternative:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "hasPermission(#documentId, 'Document', 'read')"
)
```

`hasPermission` is a hook for a configured `PermissionEvaluator`. It **does not know your DB schema or owner/tenant** without an implementation. For systems using Spring Security ACL, this approach can be useful but requires careful caching, sharing, and scoping design. When the primary need is owner + tenant checks, a typed policy bean is usually simpler to start with.

### 9.3. Custom AuthorizationManager

Large projects may implement a custom authorization manager to reuse logic without long SpEL strings. You must wire the manager/interceptor per version and handle `Authentication`, role hierarchy, deny/abstain outcomes, and tests. Even then, a custom manager does not automatically verify object data: repositories, tenant guards, and transactions are still needed.

## 10. How do HTTP and method security coordinate?

Illustrative HTTP configuration:

```java
@Configuration
public class HttpSecurityRules {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PUT, "/api/documents/**")
                .hasAuthority("document:update")
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

This is an **integration fragment**, requiring imports, an authentication mechanism, CSRF/CORS config, and real controllers. HTTP decides access by method/path; it does not inspect `documents.owner_id`. `@PreAuthorize` in the service checks the object. The repository continues scoping queries/UPDATEs.

Sample scenarios:

| State | HTTP | Method | Repository |
| --- | --- | --- | --- |
| Lacking document:read calling GET | Denied early | May not run | Does not read |
| Has read yet wrong tenant | May pass | canRead false | Scoped query finds nothing |
| Read right tenant yet not owner/share/admin | May pass | canRead false | Returns no object |
| Tenant A admin reads tenant A document | Passes | canRead true | Returns scoped record |
| Tenant B admin reads tenant A document | May pass | canRead false | Not found when scoped |
| Edit LOCKED document | Has update | canEdit false | UPDATE status guard |
| Owner changed after pre-check | Passed earlier | Stale snapshot | UPDATE guard must reject |

Do not treat an HTTP 403 as definitive proof of your method policy: it could stem from CSRF, tokens, HTTP rules, or another interceptor. Tests must isolate which layer blocks.

## 11. Testing with Spring Security Test

### 11.1. Unit testing the policy bean

Create actor and document fixtures for these cases:

- Owner with permission;
- Owner missing permission;
- Shared read, shared edit not granted;
- Same-tenant stranger;
- Tenant admin in same tenant;
- Tenant admin in another tenant;
- Anonymous/inactive;
- Nonexistent ID;
- LOCKED state;
- Revoked share, revoked role;
- Owner/tenant changed between check and write.

Mock `ActorResolver` and `DocumentAccessRepository`, asserting the policy calls the repository with the **verified tenant**, never taking a tenant from the request. Crucially, verify no data is leaked and no side effects occur when denied.

### 11.2. Testing a Spring bean with @PreAuthorize

Integration tests live in a Spring context with `@EnableMethodSecurity`, the real service, and actor fixtures:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DocumentMethodSecurityTest {

    @Autowired
    DocumentService documents;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"document:read"}
    )
    void ownerCanRead() {
        UUID ownedId = UUID.fromString(
            "00000000-0000-0000-0000-000000000042");
        // Fixture defines Alice in tenant A, owner of ownedId.
        assertNotNull(documents.read(ownedId));
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = {"document:read"}
    )
    void strangerCannotRead() {
        UUID ownedId = UUID.fromString(
            "00000000-0000-0000-0000-000000000042");
        assertThrows(
            AccessDeniedException.class,
            () -> documents.read(ownedId)
        );
    }
}
```

This is **skeleton test code**, requiring Spring beans, entity fixtures, and an `ActorResolver` compatible with mock users. `@WithMockUser` only creates a test principal; it does not verify production JWT signatures, real user memberships, or role mappers. For JWTs, separately test decoders and authority conversion.

### 11.3. Testing the right denial reason

If a REST GET returns 403, it could be an HTTP authority; if a PUT returns 403, it could be CSRF before reaching the service. When testing **owner-based method authorization**, set up HTTP/authentication/CSRF fixtures so the request can reach the service, or test the proxied bean directly.

For POST/PUT/DELETE in cookie/session apps, send a valid CSRF token while testing authorization; dedicate a separate test to missing CSRF tokens. For bearer-only APIs, verify the architecture does not accidentally accept cookie authentication.

### 11.4. Negative tests are the completion criteria

A minimal security suite should prove:

1. Alice (owner) can read a document in the same tenant.
2. Bob has read permission yet is not owner/shared and is denied.
3. Carol (tenant admin) in the same tenant can read if permitted.
4. David (tenant admin) in another tenant is denied.
5. Alice (owner) with revoked read permission is denied.
6. Shared READ does not permit editing.
7. EDIT when status is LOCKED is denied.
8. Anonymous/inactive callers are denied.
9. API requests sending forged `ownerId` or `tenantId` do not alter results.
10. Stale version causes DB UPDATE to affect 0 rows.
11. Service calls go through a real Spring proxy with the interceptor.
12. Jobs/GraphQL/messaging do not bypass policies or query constraints.

### 11.5. Self-invocation and testing outside HTTP

If a service calls `this.rename()`, the method-security interceptor can be bypassed. Therefore test an entrypoint matching real call paths: REST controller → service bean, job → service bean, event consumer → service bean. Background jobs need an appropriate actor/service principal; never access `SecurityContextHolder` from an already-ended HTTP thread.

**Data gates** remain the last line of defense if a caller bypasses the service method.

## 12. Returning 403 vs. 404 and protecting information

If a client reads a nonexistent or cross-tenant ID, many APIs choose **404** to avoid revealing whether the document exists. If the caller is authenticated yet lacks a functional permission, **403** may be chosen. That is an application/threat-model choice, never meaning 404 eliminates the need for authorization.

- Never return bodies containing `ownerId`/`tenantId`/metadata of a blocked document.
- Never return detailed errors revealing that a cross-tenant document exists.
- Internal logs can distinguish NOT_FOUND, WRONG_TENANT, NOT_OWNER, MISSING_PERMISSION, and LOCKED without leaking secrets.
- Distinguish 401 unauthenticated from 403 unauthorized in appropriate APIs.
- On DB errors, never turn exceptions into ALLOW or expose sensitive details in 500 bodies.

## 13. Roles and ownership in special workflows

### 13.1. Approve: the owner may be the one prohibited

In a two-person workflow:

```text
CAN_APPROVE =
  has(document:approve)
  AND sameTenant
  AND assignedApprover
  AND document.creatorId != actor.id
  AND document.status == PENDING
```

The document creator **must not self-approve**, even if also the owner and holding high roles. This is Separation of Duties (SoD). Ownership is not always an additive right: sometimes it is a **disqualifying** condition for sensitive actions.

### 13.2. Transferring ownership and revoking shares

Transferring ownership alters permission relationships. Within one transaction, verify the actor has `document:transfer`, the document belongs to the tenant, the current owner matches, the recipient is valid, and the record version matches. Update the owner and consistently update ACLs/caches/audits; never trust a new owner from the payload as an existing tenant member without verification.

Revoking a share must take effect per business requirements, including caches and async downloads. Do not merely update the ACL table while leaving a public file URL valid indefinitely.

### 13.3. Export/list/search

Permission to read individual documents does not automatically permit exporting all of them. Exporting may require `document:export`, field filtering, result limits, and tenant/sharing scoping. Queries should apply tenant/owner/ACL predicates **before returning data**, rather than loading 10,000 records into memory and calling `canRead` on each object.

### 13.4. Global admin and break-glass

If emergency cross-tenant access is needed, require dedicated permissions, MFA, session step-up, reason/ticket tracking, time-limited access, and independent auditing. Never put global exceptions into `hasRole('ADMIN') or isOwner` and silently bypass tenants. Every override needs a policy owner and boundary tests.

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using only `hasRole('USER')` | Users read others' IDs | Object policy by ID |
| Using only `document:read` | BOLA/IDOR | Add tenant and owner/share |
| Admin OR owner without tenant bound | Tenant B admin reads tenant A | `sameTenant` as a shared condition |
| Trusting client-sent `ownerId`/`tenantId` | Forged authorization data | Verified principal + DB |
| Treating role hierarchy as ownership | Inherited authority becomes object privilege | Keep the two permission types separate |
| Shared READ permitting UPDATE | Privilege abuse via ACL | Separate READ/WRITE |
| Checking only `isOwner` | Wrong admin/share behavior or missing permission check | Clear `canRead` policy |
| `@PreAuthorize` not enabled | Annotation never executes | `@EnableMethodSecurity` |
| `#documentId` unbound | Expression error or unexpected deny | `@P` / `-parameters` |
| Self-invocation | Bypasses AOP interceptor | Proper bean/proxy boundaries |
| `@PostAuthorize` on write methods | Denial after side effects | Pre-check + DB guard |
| Unscoped queries | Cross-tenant data reads | `WHERE verifiedTenant` |
| Pre-check then UPDATE by ID | TOCTOU | Conditional update/version |
| N+1 ownership checks per item | Poor performance/memory exposure | Scoped queries |
| Unintended global admin role | Overly broad access | Tenant-scoped roles |
| Fixing 403 with `authenticated()` | Drops resource authorization | Debug the right layer |
| Revoked role/ACL lingering in stale cache | Access persists too long | TTL/revocation |
| Testing only happy path | Misses privilege escalation bugs | Negative cases |
| Background job calling repository directly | Bypasses method security | Use cases + data guards |
| Audit logs containing tokens/content | Sensitive data leakage | Minimal logs + reason codes |

## 15. Project adoption workflow

1. Identify the action: read, update, approve, delete, export, or transfer.
2. Identify trusted identity: issuer/session/JWT, actor ID, tenant membership.
3. Identify functional roles/permissions and their scopes.
4. Identify resource relationships: owner, share, assigned reviewer, state.
5. Write out the logical predicate before coding; place AND/OR parentheses clearly.
6. Choose enforcement points: HTTP rules, `@PreAuthorize`, policy bean, and repository.
7. Extract verified actor from Authentication, never from arbitrary headers or bodies.
8. Query access facts by document ID **and verified tenant**.
9. Check role + owner/share + state with default deny on missing data.
10. For writes, use transactions/conditional updates/version guards.
11. Write unit tests for policies; integration tests through proxies and HTTP.
12. Add negative cases: wrong tenant, missing permission, inactive, revoked share, locked.
13. Review list/export and non-HTTP entrypoints.
14. Design auditing, TTL/caching, and permission revocation mechanisms.
15. Review policy changes as security changes, not simple refactors.

## 16. Exercises and self-check

### Exercise 1 — Analyzing AND/OR

An expression currently uses `hasRole('TENANT_ADMIN') or @policy.isOwner(authentication,#id)`. Create tests for a cross-tenant admin, an owner lacking read, a same-tenant stranger, and a shared reader. Rewrite the predicate so the tenant boundary is a shared condition.

### Exercise 2 — Java 17

Run `DocumentRoleOwnershipDemo.java` and verify the 17 lines of stdout. Add an actor with role `TENANT_EDITOR` and a document in tenant T2; explain which conditions are missing if only roles are checked.

### Exercise 3 — Policy bean

Implement `DocumentPolicy.canRead(authentication,documentId)` using `ActorResolver` and an ID+tenant query. Create a mock repository returning empty on wrong tenant; test that an actor with the same role in another tenant is denied.

### Exercise 4 — Conditional update

Start with a DRAFT document at version 7. After the pre-check, another transaction transitions it to APPROVED at version 8. Execute an UPDATE requiring `expectedVersion=7` and status DRAFT; prove 0 rows are updated and data remains unchanged.

### Exercise 5 — Sharing permissions

Bob is shared READ, not WRITE. Design an ACL with revocation/expiry; test `canRead` and `canEdit` separately. After revocation, Bob cannot read even with functional `document:read`.

### Exercise 6 — SoD

Alice created a document and is assigned as approver. Even with `ROLE_TENANT_ADMIN` and `document:approve`, the policy must deny if creator and approver must differ. Write tests for another assigned user, wrong tenant, and APPROVED status.

### Exercise 7 — Integration test

Enable `@EnableMethodSecurity`, create a service with `@PreAuthorize` and a policy bean. Test through the Spring bean with a principal holding read permission and ownership. Add a self-invocation caller to observe the proxy-bypass risk; fix the design and test that the bypass is gone.

### Exercise 8 — Cross-tenant export

Design a list/export query returning only documents in the same tenant within owner/share/tenant-admin scope. Never use `findAll()` followed by Java filtering. Test that a tenant A account never sees tenant B document metadata even with matching ID patterns.

### Self-check

1. **Is a role alone enough to decide permission to read a record?** No; an object policy per business model is needed.
2. **How does ownership differ from authority?** Authority applies to an action type; ownership applies to a specific object.
3. **Why is an admin from another tenant still denied?** A tenant-scoped role does not automatically permit cross-tenant access.
4. **What is the core logic pattern of this lesson?** Permission AND sameTenant AND (owner OR share OR admin), plus action-appropriate state checks.
5. **Can permissions be skipped if the user is owner?** Only if business logic explicitly intends so, never by assumption.
6. **When does `@PreAuthorize` run?** Before the method body intercepted by Spring AOP.
7. **What does `@documentPolicy` mean?** A Spring bean handling resource permission logic.
8. **Where does `#documentId` come from?** A method parameter bound by name/`@P`/`-parameters`.
9. **Does an `X-User-Id` header prove ownership?** No.
10. **Does `findById` protect tenants?** Not without a dedicated guard or query scope.
11. **Why doesn't a pre-check eliminate TOCTOU?** Permissions/owner/status can change before the DB UPDATE.
12. **Is `@PostAuthorize` suitable as the sole gate for payments?** No, because side effects can happen before denial.
13. **Can a `ROLE_TENANT_ADMIN` bypass the LOCKED state?** Only if business policy explicitly states so; this lesson's pattern forbids it.
14. **Why are negative tests important?** They catch broken ORs, missing tenant checks, and privilege escalation.
15. **Does a 403 prove the method gate ran?** No; it could come from HTTP/CSRF or another gate.
16. **Is self-invocation guaranteed to run `@PreAuthorize`?** No under normal Spring proxy mode.
17. **Does a role hierarchy make a user an owner?** No.
18. **Is a job bypassing the HTTP chain safe thanks to service annotations?** Only if called through the proxy with an appropriate actor/context; data invariants are still required.
19. **Can 404 be returned instead of 403 for cross-tenant requests?** Yes if designed to hide existence, without replacing permission checks.
20. **What are the baseline conditions for a safe update?** Permission + tenant + owner/editor + state + transaction/version guard.

**Remember:** `@PreAuthorize` helps combine functional permissions with **ownership or permitted resource relationship** checks before business code executes. Write policies with tenant as a shared boundary, never trust client-sent owner/tenant fields, never use an admin role as an OR branch bypassing all constraints, and re-verify critical invariants in the DB when writing. Security outcomes must be proven by tests for both **allowed** and **denied** cases.

### References

- [Spring Security – Method Security, @PreAuthorize, parameters and bean expressions](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security Tests](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [OWASP – API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)