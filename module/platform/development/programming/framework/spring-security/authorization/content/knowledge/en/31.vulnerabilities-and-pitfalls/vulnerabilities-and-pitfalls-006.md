# Trusting Client-Supplied ownerId, tenantId, role, or Status

## 1. The Vulnerability Lies at the Trust Boundary

In Spring Security, clients are allowed to **send requests** but may never **self-certify that they are authorized**. Values such as `ownerId`, `tenantId`, `role`, and `status` can appear in a JSON body, URL, query parameter, cookie, HTTP header, form field, JavaScript state, or data echoed back from the UI. Because the client controls those sources, an attacker can tamper with them using HTTP tools without using the official UI.

The bug occurs when the backend uses the client-sent value itself as proof of authorization: “`ownerId` in the body matches the logged-in account”, “`tenantId` in the header is the active tenant”, “`role=ADMIN` in the request”, or “`status=APPROVED` so the next step is allowed”. What the client claims **does not prove** ownership, tenant membership, role, or actual business state.

The consequences can include:

- **BOLA/IDOR (Broken Object Level Authorization):** reading or modifying someone else's resource by altering ID/owner.
- **Cross-tenant access:** operating on data of another organization/tenant when query conditions are not constrained by the authenticated and authorized tenant.
- **Privilege escalation:** self-promoting by sending `role=ADMIN`, `authorities=["ROLE_ADMIN"]`, or overwriting role fields on the user object.
- **Workflow bypass:** jumping from `DRAFT` to `APPROVED`, `PAID`, `ACTIVE`, `VERIFIED` without meeting conditions, or bypassing approvers.
- **Mass assignment/overposting:** the framework binds JSON directly into an entity and persists all fields, unintentionally allowing edits to sensitive fields not meant for clients.

These flaws belong to **authorization and data integrity**, distinct from SQL injection. Using an ORM, HTTPS, JWT, or `@Valid` does not automatically fix a backend trusting the wrong data source.

### Design Principle

**Client data is input/intent; facts used to make authorization decisions must be verified by the backend from authoritative sources.** Specifically:

| Attribute | What May the Client Send It For? | Authoritative Source for Decisions |
| --- | --- | --- |
| `ownerId` | Selecting a recipient/new owner if business rules permit | Current owner read from DB; actor from verified principal; ownership transfer policy on server |
| `tenantId` | Selecting a workspace/tenant among permitted tenants | Server-verified tenant membership/authorization; tenant constraints on every data operation |
| `role` | Requesting an admin assign a role to another account in an authorized workflow | `Authentication.getAuthorities()` authenticated by the security chain and/or server-stored role policy |
| `status` | Describing a desired action, e.g., “submit” or “publish” | Current status from DB, state transition rules, authorized actor/role, business preconditions |

Clients can certainly pass a **resource ID** or **selected tenant**. The problem is not forbidding these parameters, but **never interpreting them as permissions without verification**.

## 2. Example of a Vulnerable Endpoint

The following snippet illustrates an **unsafe pattern, do not use in production**. Suppose the application allows updating documents and uses a DTO containing all attributes:

```java
// UNSAFE CODE: for vulnerability analysis only.
record UpdateDocumentRequest(
        String title,
        String ownerId,
        String tenantId,
        String role,
        String status) {}

@PutMapping("/api/documents/{id}")
public void update(@PathVariable UUID id,
                   @RequestBody UpdateDocumentRequest request) {
    Document document = repository.findById(id).orElseThrow();

    if (request.ownerId().equals(requestContext.userId())
            && request.role().equals("ADMIN")) {
        document.setTitle(request.title());
        document.setOwnerId(request.ownerId());
        document.setTenantId(request.tenantId());
        document.setStatus(request.status());
        repository.save(document);
    }
}
```

The weakness is independent of specific controller styling: `request.ownerId()` and `request.role()` are both chosen by the caller; `request.tenantId()` and `request.status()` are copied directly into the entity; `findById(id)` performs no owner/tenant check; a user only needs to alter the payload to modify sensitive data.

Typical forged payload:

```json
{
  "title": "Hijacked document",
  "ownerId": "alice",
  "tenantId": "other-tenant",
  "role": "ADMIN",
  "status": "APPROVED"
}
```

Even when the backend has authenticated Alice, **authenticating Alice's identity** does not mean Alice may claim the ADMIN role, move data to another tenant, or approve a document. `@PreAuthorize("isAuthenticated()")` only confirms login, not permissions on the object/tenant/status.

If the DTO is replaced with `@RequestBody Document document` followed by `repository.save(document)`, the risk is even wider: every property with a valid setter/binding, including `ownerId`, `roles`, `approved`, or `status`, can inadvertently become writable. `@JsonIgnore` or hiding inputs on the frontend does not replace service-layer authorization protection.

## 3. Detailed Analysis by Attribute Group

### 3.1. `ownerId`: Owner Stored on Resource, Actor Taken from Principal

Common bug: `if (request.ownerId().equals(authentication.getName()))` and then allowing edits to an arbitrary document. An attacker can fill `ownerId` with their own ID regardless of who the owner **stored in the DB** actually is. If the request carries someone else's `documentId`, this check becomes meaningless.

Correct approach for owner-only resources:

1. Obtain the **trusted actor ID** from the `Authentication` established by Spring Security, per the application's identity contract.
2. Retrieve the resource's **current owner** from the DB or enforce the owner condition directly in the data query.
3. Compare actor, owner, and other policy conditions **at the appropriate read/write point**.
4. If ownership transfer is needed, create a dedicated `transferOwnership` action: actor has transfer permission, recipient is valid, tenant and status satisfy rules, update is audited and concurrency-protected.

When creating a “my own” resource, normally assign `ownerId = currentActorId` on the server. Never accept `ownerId` as self-authenticating evidence. For creating on behalf of someone else, the backend may accept `requestedOwnerId` but must verify delegation permission and recipient validity before assigning.

### 3.2. `tenantId`: A Context Selector, Not an Access Pass

Multi-tenant applications often receive `tenantId` via URL such as `/tenants/{tenantId}/documents`, subdomain, or `X-Tenant-Id` header. This value can be used to **select** a tenant, especially when a person belongs to multiple tenants. However, the backend must verify the user **currently has permission in that tenant**, and constrain resource queries by tenant.

A dangerous mistake:

```java
Document doc = repository.findById(documentId).orElseThrow();
// Only verifies request.tenantId exists,
// then updates doc without comparing doc.tenantId.
```

If the document belongs to tenant B while the request selects tenant A, checking membership in tenant A is not enough. You must simultaneously verify:

- The actor holds active membership/permissions in the **selected tenant**.
- The resource actually belongs to **that same tenant** (along with relevant parent/child relations).
- The specific operation permission is granted within that tenant, not just generic membership.
- Every read/write path, search, file download, bulk API, event handler, cache key, and export respects tenant scope.

Safer repository query examples include `findByIdAndTenantId(...)` for reads, or `UPDATE ... WHERE id = :id AND tenantId = :tenantId AND ownerId = :actorId ...` for writes, combined with membership and permission checks. For complex access or instant revocation policies, membership conditions must be coordinated with writes using appropriate transactions/locks/DB conditions to prevent races.

Never rely on a global default tenant, an uninitialized or improperly cleared `ThreadLocal`, or `X-Tenant-Id` as an automatic source of authority. If the tenant comes from a **verified JWT** or trusted IdP, you must still verify the token suits the current operation, audience, and validity window. In multi-tenant user models, signed claims can describe membership yet never make an arbitrary foreign tenant ID in the URL valid.

### 3.3. `role`: Permissions Come from Authentication and Server Policy

Faulty examples: `if ("ADMIN".equals(request.role()))`, `if (headers.get("X-Role").equals("ADMIN"))`, or accepting a list of `authorities` from the request and constructing an `Authentication` with them. Clients can assign themselves any role. Hiding admin buttons in the UI does not prevent manual HTTP requests.

In Spring Security, role/authority authorization must rely on the `Authentication` produced by the security chain after **verifying the authentication source**, such as a logged-in session, a JWT verified for signature/issuer/audience/expiry, or an authoritative principal lookup. For example, `hasAuthority('DOCUMENT_PUBLISH')` or `hasRole('ADMIN')` uses authorities in `SecurityContext`; note `hasRole('ADMIN')` typically maps to authority `ROLE_ADMIN`, whereas `hasAuthority` uses the exact string.

**Valid exception:** user administration APIs may receive a `targetRole` that an admin wants to assign. However, this is a *permission change request*, not the caller's own role. The server must check that the admin has permission to assign that role within the proper tenant scope, block self-promotion/over-privilege per policy, validate the assignee, persist the change, and audit it. Never construct the current `Authentication` from `targetRole`.

A role claim inside a **valid, signature-verified JWT** differs from a `role` in a JSON body or forged header: the claim may be an authentication fact supplied by the IdP by design. Still, the system must define handling for role changes/token revocation, tenant scoping, and claim staleness; a role inside an old token does not necessarily reflect new policy immediately.

### 3.4. `status`: Client Requests Actions, Server Validates Transitions

Faulty example: `entity.setStatus(request.status())` allowing clients to submit `APPROVED`, `PAID`, `VERIFIED`, or `ACTIVE` to skip moderation, payment, or verification. Even when the actor owns the record, **permission to edit content does not mean permission to approve/finalize a workflow**.

Instead, expose **business commands** like `submit`, `approve`, `reject`, `publish`; or accept an allowlisted action enum. The service reads the current `status` from the DB, checks the transition and actor, extra rules such as separation of duties (approver cannot be creator), and executes a version-conditioned state transition.

Matrix example (illustrating one workflow's policy):

| Current Status | Action | Role/Context to Check | New Status |
| --- | --- | --- | --- |
| `DRAFT` | `submit` | Owner within tenant and valid data | `SUBMITTED` |
| `SUBMITTED` | `approve` | Authorized approver; no separation-of-duties violation | `APPROVED` |
| `SUBMITTED` | `reject` | Authorized approver | `REJECTED` |
| `APPROVED` | `editDraft` | Per workflow, may require creating a new revision | Does not silently revert to `DRAFT` |

If valid status can change from another transaction between check and write, use optimistic versioning, conditional updates, or locks to prevent acting on stale state. `@Valid` on `status` only checks format/enum membership; **it has no idea whether the transition is permitted for the current actor and resource**.

## 4. Spring Boot / Spring Security Implementation Pattern

The snippets below are **fragments** in a Spring Boot 3.x / Spring Security 6.x application with entities `Document`, `DocumentStatus` (`DRAFT`, `PUBLISHED`), `TenantMembershipRepository`, and `@EnableMethodSecurity` already configured. They are not a standalone Java file. Assume `Authentication.getName()` is a stable actor ID matching the DB `ownerId`/membership keys; if the application uses a username or subject distinct from the user key, a trusted identity mapping step is required.

Instead of accepting arbitrary `ownerId`, `role`, and `status`, the “publish” endpoint accepts only **version**:

```java
public record PublishRequest(
        @jakarta.validation.constraints.NotNull
        @jakarta.validation.constraints.Positive
        Long expectedVersion) {}
```

```java
@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {
    private final DocumentPublishService publishService;

    public DocumentController(DocumentPublishService publishService) {
        this.publishService = publishService;
    }

    @PatchMapping("/{documentId}/publish")
    public ResponseEntity<Void> publish(
            @PathVariable UUID tenantId,
            @PathVariable UUID documentId,
            @jakarta.validation.Valid @RequestBody PublishRequest request) {

        publishService.publish(tenantId, documentId, request.expectedVersion());
        return ResponseEntity.noContent().build();
    }
}
```

The repository updates conditionally by **resource ID, tenant, owner, status, and version**. Every condition comes from server-verified parameters or DB data, never from client claims of owner/role/status:

```java
public interface DocumentRepository extends JpaRepository<Document, UUID> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Document d
           set d.status = :nextStatus,
               d.version = d.version + 1
         where d.id = :documentId
           and d.tenantId = :tenantId
           and d.ownerId = :actorId
           and d.status = :expectedStatus
           and d.version = :expectedVersion
        """)
    int publishIfAllowed(
            @Param("documentId") UUID documentId,
            @Param("tenantId") UUID tenantId,
            @Param("actorId") String actorId,
            @Param("expectedStatus") DocumentStatus expectedStatus,
            @Param("nextStatus") DocumentStatus nextStatus,
            @Param("expectedVersion") long expectedVersion);
}
```

The service retrieves the actor from Spring Security (never passing `actorId` from the request), checks the authority and membership in the selected tenant:

```java
@Service
public class DocumentPublishService {
    private final DocumentRepository documents;
    private final TenantMembershipRepository memberships;

    public DocumentPublishService(DocumentRepository documents,
                                  TenantMembershipRepository memberships) {
        this.documents = documents;
        this.memberships = memberships;
    }

    @Transactional
    @PreAuthorize("hasAuthority('DOCUMENT_PUBLISH')")
    public void publish(UUID tenantId, UUID documentId, long expectedVersion) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        String actorId = authentication.getName();

        if (!memberships.existsActiveByTenantIdAndUserId(tenantId, actorId)) {
            throw new AccessDeniedException("Not permitted");
        }

        int affected = documents.publishIfAllowed(
                documentId, tenantId, actorId,
                DocumentStatus.DRAFT, DocumentStatus.PUBLISHED,
                expectedVersion);

        if (affected != 1) {
            // Per API contract: 403, 404, or 409; avoid disclosing resource existence.
            throw new AccessDeniedException("Not permitted or state changed");
        }
    }
}
```

For illustration, `existsActiveByTenantIdAndUserId` assumes the membership repository has a field of that name. Real applications must verify **publish permission in the tenant**, not merely membership if different memberships carry different permissions; for example `hasPermission(actor, tenant, DOCUMENT_PUBLISH)` backed by trusted role/permission data. `@PreAuthorize` is the coarse permission check; the service/repository conditions enforce the resource check.

A `tenantId` in the path remains an **untrusted selector**: the service verifies membership, and then the `UPDATE` statement also forces `Document.tenantId` to match the selector. Current `ownerId` is matched in the DB. `role` comes from `SecurityContext`. Source `status` is compared against `DRAFT` before transitioning to `PUBLISHED`.

**Concurrency limitations to resolve per contract:** if membership/role is revoked in *another table* right between `existsActiveBy...` and `publishIfAllowed`, the snippet above does not inherently guarantee instant revocation. Enforce/lock policy near the write point with the chosen consistency mechanism: lock policy rows, SQL queries joining membership conditions, or permission-versioning/transaction architectures. Similarly, paths changing owner/status must increment version and obey locking policy. JPQL bulk updates **do not automatically run `@Version` optimistic checks/increments like entity updates**, so the example checks and increments version explicitly.

Do not automatically return 403 for every real case; `affected=0` could mean non-existent, wrong tenant, not owner, wrong status, or stale version. Design consistent 403/404/409 mapping without leaking object existence to unauthorized callers.

## 5. Java 17+ Program Demonstrating Trusted Facts

The following standalone example shows the difference between checking a client's “claim” vs checking an authoritative actor and document. This is an in-memory learning model; real integration tests must still verify DB, Spring Security, tokens, and transactions.

Save file `ClientTrustDemo.java`:

```java
import java.util.Set;

public class ClientTrustDemo {
    record Actor(String id, Set<String> tenantIds,
                 Set<String> permissions) {}
    record Document(String tenantId, String ownerId,
                    String status) {}
    record Input(String ownerId, String tenantId,
                 String role, String status) {}

    // WRONG: uses client-supplied values as evidence.
    static boolean unsafe(Actor actor, Input input) {
        return input.ownerId().equals(actor.id())
                && input.role().equals("ADMIN")
                && input.status().equals("PUBLISHED");
    }

    // RIGHT DIRECTION: actor/permission authenticated by backend,
    // current owner/tenant/status managed by backend.
    static boolean safeToPublish(Actor actor, String selectedTenant,
                                 Document document) {
        return actor.tenantIds().contains(selectedTenant)
                && document.tenantId().equals(selectedTenant)
                && document.ownerId().equals(actor.id())
                && actor.permissions().contains("DOCUMENT_PUBLISH")
                && document.status().equals("DRAFT");
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", Set.of("tenant-a"), Set.of("DOCUMENT_PUBLISH"));
        Document belongsToBob = new Document(
                "tenant-b", "bob", "DRAFT");
        Input forged = new Input(
                "alice", "tenant-b", "ADMIN", "PUBLISHED");

        System.out.println("Trust client: " + unsafe(alice, forged));
        System.out.println("Check real resource: "
                + safeToPublish(alice, forged.tenantId(), belongsToBob));

        Document ownedByAlice = new Document(
                "tenant-a", "alice", "DRAFT");
        System.out.println("Valid own resource: "
                + safeToPublish(alice, "tenant-a", ownedByAlice));
    }
}
```

Compile/run with JDK 17 or newer:

```bash
javac ClientTrustDemo.java
java ClientTrustDemo
```

Exact stdout:

```text
Trust client: true
Check real resource: false
Valid own resource: true
```

The first line demonstrates the vulnerability: `forged.ownerId=alice`, `role=ADMIN`, and `status=PUBLISHED` are all client-declared and trick the faulty check into accepting. The second line denies because Alice does not belong to `tenant-b` and does not own Bob's document. The third line shows a document genuinely owned by Alice in an allowed tenant can still be published. Production must still execute conditional updates and check concurrent changes in the DB, not merely use an in-memory `safeToPublish` function.

## 6. Testing Against Forgery and Privilege Escalation

A solid test suite must **alter each client-controlled field**, combine principal/DB state differing from the payload, and verify both the HTTP response **and final data state**. Have `MockMvc`/integration tests with active security filters, an isolated test DB, and data for Alice/Bob in tenants A/B. Use `@WithMockUser` or test JWT `jwt()` for logic once `SecurityContext` exists; testing real JWT signature/issuer/audience verification requires separate tests at the authentication layer. Never populate `Authentication` from a JSON body in those tests.

| Test Case | Principal and Real Data | Forged Payload / Action | Expected Result |
| --- | --- | --- | --- |
| Spoofed `ownerId` | Alice logged in, Bob's document | `ownerId="alice"` with Bob's document ID | Cannot read/write; owner/content unchanged |
| Spoofed `tenantId` | Alice only in tenant A; document in B | URL/header/body switched to tenant B | Denied; tenant B document not disclosed |
| Resource/tenant mismatch | Alice in A and B; document actually in B | URL selects A with document ID from B | No cross-tenant operation even though actor has membership in both |
| Spoofed `role` | Alice has only `DOCUMENT_READ` | JSON/header sends `ADMIN`, `DOCUMENT_PUBLISH` | Cannot publish or assign roles |
| Valid role | User with real permission in right tenant | Valid publish command | Succeeds once, without needing a role field in the request |
| Self-escalation | Alice has limited member-management rights | `targetRole=SUPER_ADMIN` or assigning to self | Denied per delegation/role-assignment matrix |
| Spoofed `status` | Document `DRAFT`, actor can only edit | Sends `status=APPROVED` or calls approve | Cannot approve; status remains unchanged |
| Invalid transition | Document `DRAFT` | Calls `approve` when valid only from `SUBMITTED` | Denied even if actor has approval permission |
| Stale version | Document changed from v1 to v2 | Request with `expectedVersion=1` | Does not overwrite; appropriate conflict response |
| Revoked permission | Membership/authority revoked mid-request | Continues action from old request | Obeys permission-effective contract; does not bypass policy |
| Mass assignment | User permitted to edit profile name | Payload includes `roles`, `tenantId`, `verified` | Only allowlisted fields updated |
| Bulk endpoint / export | Actor in A, ID list has both A and B | Sends mixed IDs from two tenants | Does not return/write B's resources; clear error/atomicity behavior |

Tests must assert concrete invariants: `ownerId`, `tenantId`, `status`, `role`, `version` in the DB remain unchanged when a request is denied; no “success” event/outbox entry is emitted; resources from other tenants do not appear in responses, statistics, exports, or client-returned logs. For allowed updates, assert exactly one record changed and sensitive fields were not silently overwritten. Do not rely solely on `assertThrows` or verifying a mock policy was called.

To reproduce permission/state changes while a request is in flight, use two real transactions and a `CountDownLatch`/barrier between precheck and write. Commit the revocation/ownership-transfer transaction before letting the older request proceed, then re-read in a fresh transaction. Do not use `Thread.sleep` as proof of ordering. If using pessimistic locks, test real lock ordering rather than creating artificial deadlocks.

## 7. API Design and Data Control Checklist

### Input and DTOs

- **Allowlist editable fields:** use a dedicated request DTO per use case; never bind sensitive entities directly; avoid `BeanUtils.copyProperties(request, entity)` without an explicit field allowlist.
- **Separate commands from state:** `publish`, `submit`, `approve`, `transferOwner` are actions with distinct policies; do not expose a generic `setStatus` to all actors.
- **Data validation is necessary but insufficient:** `@NotNull`, enums, `@Positive` validate shape; policy services must validate permissions and business state.
- **Never accept `role` to identify the caller:** a role field in admin APIs, if present, is the **target role to be approved**, never the request's authority.

### Principal, Policy, and Scope

- Use `Authentication` from properly configured Spring Security; session/JWT/OAuth2 resource server must verify the authentication source. Define a mapping from subject/name to a stable user ID.
- Check **action permissions on the exact resource and tenant**, not just `isAuthenticated()` or holding a generic role.
- Use DB row ownership and membership as authoritative facts; if caching permissions, define permission-change effective time/TTL/revocation.
- Do not rely on unverified self-declared headers/claims, client-side route guards, hidden buttons, or signed values that no longer match current policy.

### Data Operations and Side Effects

- Embed tenant/owner/status/version predicates into write queries, or use locking/transactions suited to the concurrency model. Ownership/role/status transfer paths must follow the same mechanism.
- For multi-tenancy, consider DB constraints, composite keys/FKs, or PostgreSQL Row-Level Security as an additional defense layer if architecturally appropriate. If using RLS with connection pools, set/reset DB context safely per transaction; RLS does not replace authenticating the principal and membership.
- For success events, use an outbox in the same transaction when appropriate; never send emails/events first and expect a DB rollback to undo side effects.
- Ensure batch jobs, schedulers, message consumers, file downloads, caches, audits, and searches always enforce tenant scope; test paths that are commonly overlooked.

### Responses and Observability

- Return 403/404/409 per a consistent contract; you may mask resource existence with 404 to prevent enumeration. Never reveal “document belongs to Bob/tenant B” to unauthorized users.
- Internal logs/audits include verified actor ID, checked tenant, action, and decision; never log client-forged values as if they were authoritative identities.
- Monitor anomalies such as repeated probing of out-of-tenant resource IDs or requests containing extra schema fields like `role`; never turn logging into an authorization decision.

## 8. Before – After Scenario for Self-Assessment

**Before:** frontend sends `{ "ownerId": "alice", "tenantId": "tenant-a", "role": "ADMIN", "status": "APPROVED" }`; service calls `save` after checking role/owner from the request. Simply editing JSON lets an actor self-elevate, switch tenants, or bypass workflow.

**After:** frontend sends only the allowed action and business payload, e.g., `PATCH /api/tenants/tenant-a/documents/d-123/publish` with `{ "expectedVersion": 7 }`. Server retrieves actor/authority from the verified context, verifies membership and permission in tenant A, checks document d-123 truly belongs to tenant A and the actor has permission on it, current status is `DRAFT`, version is 7; performs the conditional update, audits, and emits a success event only after transaction commit.

**Completion criteria:** altering `ownerId`, `tenantId`, `role`, `status` in any client-controlled input cannot create new permissions; legitimate permissions still operate; concurrent owner/tenant/permission/status changes cannot be bypassed; database and side effects remain invariant across all processing paths.

Self-check question: **“Which value in this allow decision was self-declared by the client, and where did the server verify it against an authoritative source?”** If the answer is merely “the frontend sent it correctly”, “the user is logged in”, or “`@Valid` ran”, authorization still has a vulnerability.
