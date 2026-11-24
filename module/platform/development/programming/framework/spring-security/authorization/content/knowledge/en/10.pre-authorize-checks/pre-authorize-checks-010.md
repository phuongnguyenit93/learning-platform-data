# Preventing Spoofing of ownerId, tenantId, or Permission Attributes in Requests with Spring Security

## 1. Real-world problem and protection goals

Suppose a SaaS application stores documents by organization (tenant). Each document has `id`, `tenantId`, `ownerId`, `title`, `content`, status, and permission metadata. Alice logs into organization `org-a` and is allowed to edit her own document `d1`. A client sends:

```http
PATCH /api/tenants/org-a/documents/d1 HTTP/1.1
Authorization: Bearer <valid-token-for-alice>
Content-Type: application/json

{
  "title": "New name",
  "ownerId": "bob",
  "tenantId": "org-b",
  "isAdmin": true,
  "roles": ["ROLE_ADMIN"],
  "permissions": ["document:delete:any"]
}
```

**The problem is not whether Alice's token is valid.** The token may be valid, yet the `ownerId`, `tenantId`, `isAdmin`, `roles`, and `permissions` fields in the request are all client-controlled. If the backend copies those values into a JPA entity or relies on them to make authorization decisions, Alice can transfer ownership, move the document to another tenant, or escalate her own privileges.

An even more dangerous variant:

```http
PATCH /api/tenants/org-a/documents/d2 HTTP/1.1
Authorization: Bearer <valid-token-for-alice>
Content-Type: application/json

{
  "title": "Modify Bob's document",
  "ownerId": "alice"
}
```

Here `d2` **actually belongs to Bob**. If a policy only compares `request.ownerId == authentication.name`, the expression evaluates to true because Alice put her own name in the body. Yet a user saying “I am the owner” does not create ownership.

**Lesson goal:** build a consistent trust boundary in which:

1. Caller identity comes from **server-verified authentication**, never from arbitrary JSON or headers.
2. A document's current `ownerId` and `tenantId` come from the **authoritative database record**, never from the update payload.
3. A client-selected tenant is a **requested target**; tenant membership is verified by the server.
4. Request DTOs contain only fields legitimately permitted to be edited.
5. `@PreAuthorize` checks **roles/authorities + ownership/tenant/ACL** before the service method; the service/database still enforces invariants at write time.
6. Administrative privileges and ownership/tenant transfers are **separate use cases** with dedicated authorization, validation, and auditing.
7. Regression tests verify zero data leakage, zero unauthorized writes, and zero privilege escalation even when clients swap IDs, inject extra fields, or use valid tokens from another tenant.

This lesson belongs to the **Pre-method checks** section of Spring Security authorization, focusing on `@PreAuthorize` and policy beans; DTOs, persistence, transactions, and testing are covered as coordinating layers rather than replacements for method security.

## 2. Threat model: three trust-boundary confusions

### 2.1. Broken Object Level Authorization (BOLA/IDOR)

A user is authorized to call the endpoint, yet operates on **an object they do not own** by changing an ID in the path, query, or payload:

```http
GET /api/documents/d1       # Alice's document
GET /api/documents/d2       # Swapped d1 for Bob's document
```

`hasAuthority('document:read')` only proves the caller may use the **document-reading function**, not that they may read **d2**. OWASP API1:2023 calls this *Broken Object Level Authorization*. Hard-to-guess UUIDs do not replace verifying owner, tenant, or ACLs.

### 2.2. Broken Object Property Level Authorization / mass assignment

The client sends extra properties they are not allowed to modify:

```json
{
  "displayName": "Alice",
  "role": "ADMIN",
  "emailVerified": true,
  "accountLocked": false
}
```

If the controller deserializes directly into an account entity and calls `save`, sensitive properties can be altered. OWASP API3:2023 covers *Broken Object Property Level Authorization*, including mass assignment risks. You must control **which properties each endpoint can read/write**, not only which objects can be accessed.

### 2.3. Tenant confusion / cross-tenant access

A SaaS has tenants `org-a` and `org-b`. A user is a member of `org-a` but tries:

```http
GET /api/tenants/org-b/documents/d9
X-Tenant-Id: org-b
```

A path or header containing a tenant ID is a **client-proposed selector**, not proof the caller belongs to that tenant. If the repository simply calls `findById(d9)` and returns the data, documents across organizations can be exposed.

**Three distinct questions:** “right user?”, “right object?”, “right property/action?” All must be answered using server-side facts.

## 3. Data-source classification table: what can be trusted?

| Source | Client-controlled? | Usable as real authority/owner/tenant? |
| --- | --- | --- |
| JSON `ownerId`, `tenantId`, `roles`, `isAdmin` | Yes | **No** |
| URL path variable `/tenants/{tenantId}` | Yes | Requested scope only; must verify membership |
| Query `?userId=...` | Yes | Target ID only; not caller identity |
| `X-User-Id` or `X-Role` headers from public clients | Yes | **No** |
| Hidden form fields, React state, localStorage | Yes | **No** |
| Session ID cookie | Sent by client, session verified by server | Identity comes from verified session, never self-claimed client text |
| JWT Bearer with verified signature/issuer/audience/expiry | Carried by client, cannot tamper valid claims | Can read trusted subject/claims, **still needs membership and revocation policies** |
| `Authentication` verified by Spring Security | Built by server-side security chain | Source of identity/authorities; must understand mapping |
| `documents.owner_id`, `documents.tenant_id` DB rows | Server-managed | Source of truth for current ownership/scope |
| Server `tenant_memberships` / ACL tables | Server-managed | Source of truth for membership and per-object permissions |
| Permission checks from trusted authorization service | Verified server-side over trusted channel | Usable per contract and data freshness |

**Golden rule:** **the client is allowed to pick the target object to act on, but never to self-certify permission on that object**.

### 3.1. “Signed token” does not automatically prove rights over every record

A valid JWT only proves claims accepted by the issuer at issuance time and valid under verification rules. It does not grant the user rights on an arbitrary `documentId`. A token can also hold stale `tenant` claims or revoked roles if the system lacks refresh/revocation controls.

Verify issuer, audience, signature, expiry, subject mapping, and authority sources. For sensitive or fast-changing multi-tenant actions, check membership/resource policies against trusted sources at action time.

### 3.2. Reverse-proxy trusted headers require a strict boundary

An internal gateway may pass a verified ID in a header, but trust that header only when the gateway **actually verified identity**, clients cannot reach the backend directly, and the gateway **strips/overwrites** any client-sent headers of the same name. Never apply this trust model to `X-User-Id` from an ordinary browser.

## 4. Typical mistakes: comparing client-sent properties directly

### 4.1. Anti-pattern #1: comparing ownerId in the body

```java
@PreAuthorize("#request.ownerId == authentication.name")
public void update(DocumentUpdateRequest request) {
    documentRepository.save(mapper.toEntity(request));
}
```

**Flawed logic:** `request.ownerId` comes from the client, not the verified owner in the DB. Alice can put `ownerId = alice` in the body to legitimize modifying Bob's document. `authentication.name` is trustworthy only when mapped from valid authentication, yet **the other side of the comparison remains untrusted**.

### 4.2. Anti-pattern #2: using tenantId from the body as a tenant-move command

```java
public void updateDocument(String id, DocumentPatch request) {
    Document doc = repository.findById(id).orElseThrow();
    doc.setTenantId(request.tenantId());
    doc.setOwnerId(request.ownerId());
    doc.setTitle(request.title());
}
```

This code turns editing a title into moving documents across organizations and changing ownership. A user permitted to edit titles accidentally gains cross-tenant asset-transfer powers.

### 4.3. Anti-pattern #3: client defining principal roles

```java
if (request.isAdmin()) {
    account.setAdmin(true);
}
```

or:

```java
authentication = new UsernamePasswordAuthenticationToken(
        request.username(), null, request.authorities());
```

Client-sent permission attributes must never be turned into `GrantedAuthority`. Permissions must come from server-controlled authentication/authorization mechanisms. Nor does a valid token/session make an `isAdmin` field in JSON trustworthy.

### 4.4. Anti-pattern #4: inferring permissions from the UI

Hiding a “Delete” button in React or disabling an `ownerId` input does not protect an endpoint. Clients can invoke HTTP directly, edit requests in DevTools, use REST clients, or write scripts. UI is user experience; security enforcement lives on the server.

### 4.5. Anti-pattern #5: checking only a broad role

```java
@PreAuthorize("hasRole('USER')")
public DocumentView get(String id) {
    return repository.findById(id).map(mapper::toView).orElseThrow();
}
```

Having `ROLE_USER` does not prove a user may read **every document**. To prevent BOLA/IDOR, perform lookup/authorization by tenant, owner, or ACL, not merely functional roles.

## 5. Defining policies from identity and server data

### 5.1. Document invariants

Assumed model:

```text
Document:
  id         = document identifier
  tenantId   = owning tenant (server-managed)
  ownerId    = owning user (server-managed)
  title      = content user may edit per use case
  body       = content user may edit per use case
  status     = workflow status (server-managed)
  version    = optimistic locking version number
```

Explicit condition for an EDIT operation:

```text
ALLOW_EDIT(actor, target) =
    actor authenticated
    AND actor has "document:edit" authority
    AND actor is active member of target.tenantId
    AND target belongs to selected tenant scope
    AND target.status allows editing
    AND (
        target.ownerId == actor.userId
        OR actor has vetted "document:edit:any" within tenant
    )
```

This is a **business pseudo-policy**, not a Spring API. Systems can add ACLs, group memberships, security labels, separation of duties, and approval workflows.

### 5.2. Keep permission types separate

| Check | Source of truth | Example |
| --- | --- | --- |
| Identity | Authenticated principal | Alice has user ID `u1` |
| Functional authority | Trusted mapped `GrantedAuthority` | `document:edit` |
| Membership | DB/verified membership service | u1 belongs to org-a and is active |
| Ownership | Document row in DB | d1.ownerId = u1 |
| Tenant boundary | Document row + verified selected tenant | d1.tenantId = org-a |
| State | Row and policy | d1.status = DRAFT |
| Special privilege | Server-side policy + scope | `document:edit:any` within org-a only |

Keep these checks separate to avoid granting “role ADMIN” in one tenant and having it apply to another. A system with genuine global admins must define **explicit cross-tenant permissions** and separate auditing, never treating a generic “ADMIN” role as sufficient everywhere.

### 5.3. Why select the object first and then verify?

A `PATCH /documents/d2` request may use client-provided ID `d2` to **locate the target**. Yet after locating it, the backend must verify which tenant/owner the real document belongs to. Never substitute a comparison between two client-supplied parameters:

```java
// WRONG: both arguments can be controlled by the client.
return request.tenantId().equals(pathTenantId);
```

Satisfying that check only proves two client-sent strings match, not tenant permission.

## 6. Designing API contracts that disallow modifying security metadata

### 6.1. Using allowlist DTOs with Java records

Java 17+ example:

```java
package com.example.documents.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateDocumentRequest(
        @NotBlank @Size(max = 200) String title,
        @NotBlank String body) {
}
```

The document-creation DTO **does not** accept `ownerId`, `tenantId`, or `roles`. The controller obtains the actor from authentication, the tenant from a membership-checked selector, and sets managed fields in server code.

Update DTOs should also be narrow:

```java
package com.example.documents.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateDocumentRequest(
        @NotBlank @Size(max = 200) String title,
        @NotBlank String body) {
}
```

These two classes are **Spring Boot integration code**, not standalone Java without Jakarta Validation dependencies. Include only fields a normal caller is allowed to request changing.

### 6.2. Valid request example

```http
PATCH /api/tenants/org-a/documents/d1 HTTP/1.1
Content-Type: application/json
Authorization: Bearer <alice-token>

{
  "title": "Update guide",
  "body": "Edited content"
}
```

The server determines:

```text
actorId    = identity resolved from verified Authentication
tenantId   = verified selected tenant + target document tenant
ownerId    = current document.ownerId from database
authorities = verified Authentication / trusted permission service
```

Do not let clients dictate those fields through an ordinary PATCH.

### 6.3. Unknown JSON properties: reject or ignore?

When a body carries extra `isAdmin` or `ownerId`, two strategies are valid if applied consistently:

1. **Reject unknown fields** (e.g., HTTP 400): clear contract and easy detection of out-of-schema client fields.
2. **Ignore unknown fields**: bind only allowlisted DTO fields and prove via tests that zero side effects hit security metadata.

**Note:** Spring/Jackson behavior on unknown fields depends on `ObjectMapper`/Spring Boot settings; never assume every unknown request field automatically returns 400. `@Valid` only validates constraints on bound fields; it is **not** a mass-assignment defense if the DTO/entity already exposes sensitive fields.

### 6.4. Do not use an all-fields DTO and merely “ignore” fields in the UI

A DTO like:

```java
public record UpdateDocumentRequest(
        String title,
        String body,
        String ownerId,
        String tenantId,
        boolean isAdmin) {
}
```

exposes sensitive fields unnecessarily at the boundary, risking someone later copying them via `BeanUtils.copyProperties` or a mapper. Design minimal DTOs so the compiler and code review enforce safety, instead of relying on a promise that “the current controller won't touch that field”.

## 7. Getting identity from Spring Security, not from the request body

### 7.1. Controllers receive framework-provided Authentication

Spring MVC fragment example:

```java
@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {

    private final DocumentApplicationService service;

    public DocumentController(DocumentApplicationService service) {
        this.service = service;
    }

    @PatchMapping("/{documentId}")
    public DocumentView update(
            @PathVariable String tenantId,
            @PathVariable String documentId,
            @Valid @RequestBody UpdateDocumentRequest request) {

        // Never accept ownerId/role/isAdmin from request.
        return service.update(tenantId, documentId, request);
    }
}
```

This is a **fragment**: `DocumentApplicationService`, `DocumentView`, imports, and framework context must be supplied by the project. Crucially, the controller passes only **target selectors** and **editable fields**, never constructing an actor from JSON.

In the service/policy, retrieve current authentication:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

This Authentication is set by the security chain after authentication, **never** built from client-supplied permission fields. For async jobs, use a trusted service identity/delegation and proper propagation; never arbitrarily assign `ROLE_ADMIN` just to make a job run.

### 7.2. Is authentication.name always the internal userId?

**No.** With form login, `getName()` is usually the username; with JWT, it may be `sub` or a converter-configured principal name; with OAuth2/custom principals, it can be something else. If the database stores `ownerId` as a UUID, comparing a UUID against an email/username fails.

Define an `ActorResolver` responsible for mapping verified authentication to a **stable internal actor ID**:

```java
public interface ActorResolver {
    Actor requireCurrentActor();
}

// Project-defined pseudocode contract:
public record Actor(String userId, String selectedTenantId) {}
```

In the implementation, read from trusted authentication, mapping via issuer/subject and the user identity table. Never let a request controller arbitrarily pass `new Actor(request.ownerId(), request.tenantId())`.

### 7.3. With JWT Resource Server

Controller example when using JWT:

```java
@GetMapping("/me")
public UserProfile me(@AuthenticationPrincipal Jwt jwt) {
    String verifiedSubject = jwt.getSubject();

    // Map issuer + subject to internal user ID via trusted service.
    return profileService.loadForVerifiedSubject(verifiedSubject);
}
```

This fragment requires Spring Security OAuth2 Resource Server and `Jwt`. `sub` itself is not required to be a DB ID and can collide across issuers; with multi-issuer setups, mapping must bind issuer/audience and rely on a **verifier-checked** token. Never take a `sub` string sent separately by the client in JSON as the principal source.

### 7.4. JWT claims like tenantId or roles are not permanent passes

A JWT can hold signed tenant/roles claims yet reflect **state at issuance time**. If a user just left a tenant or had permissions revoked, an old token may remain valid until expiry unless additional controls exist.

For sensitive actions, rely on active membership/ACLs in the database or a trusted policy service. When using scoped tokens with a tenant claim, verify:
- the token is validated by a trusted issuer;
- the tenant claim matches the target resource;
- the user holds active membership/permissions in that tenant;
- business policy permits the action.

### 7.5. Tenant headers are selectors, not sources of truth

`X-Tenant-Id: org-b` can help select a tenant in a multi-tenant UI. Yet the client cannot make itself a member of `org-b` through that header. Treat the selected tenant like `documentId`: a requested parameter that must be **verified against server-side membership and the target resource**.

## 8. @PreAuthorize checks before the method using a policy bean

### 8.1. Enabling method security

In modern Servlet Spring Security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` enables `@PreAuthorize` support by default. Spring Boot starter security does not enable method-level rules automatically. Annotations execute only when calls go through an appropriate Spring-managed proxy/method interceptor.

### 8.2. Anti-pattern: checking two client-supplied fields

```java
@PreAuthorize(
    "#request.ownerId == authentication.name and " +
    "#request.tenantId == #tenantId"
)
public void update(String tenantId, UpdateRequest request) { /* ... */ }
```

This expression **never looks up the document's real owner or tenant**. Alice can submit `ownerId=alice` and `tenantId=org-a` in the body to pass, while path `documentId` points to Bob's record or an `org-b` record.

### 8.3. Replacing with a trusted service policy

A semantically sound policy:

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "hasAuthority('document:edit') and " +
    "@documentAccess.canEdit(authentication, #tenantId, #documentId)"
)
public DocumentView update(
        String tenantId,
        String documentId,
        UpdateDocumentRequest request) {
    // ...
}
```

In the expression:
- `authentication` comes from the method-security expression context.
- `tenantId` and `documentId` are **untrusted target selectors** that the policy must verify.
- `@documentAccess` is an application-written bean, not a built-in Spring method.
- `canEdit` must fetch **current owner/tenant/status/ACL** from the DB and the verified actor, never taking owner from the request.
- `hasAuthority('document:edit')` checks functional permission; the bean handles object-level policy.

Do not assume `document:edit` in tenant A applies globally; if authorities are tenant-scoped, the policy must express and check the scope properly.

### 8.4. A simple, fail-closed policy bean

```java
package com.example.documents.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccessPolicy {

    private final ActorResolver actorResolver;
    private final TenantMembershipRepository memberships;
    private final DocumentRepository documents;

    public DocumentAccessPolicy(
            ActorResolver actorResolver,
            TenantMembershipRepository memberships,
            DocumentRepository documents) {
        this.actorResolver = actorResolver;
        this.memberships = memberships;
        this.documents = documents;
    }

    public boolean canEdit(
            Authentication authentication,
            String tenantId,
            String documentId) {

        if (authentication == null || tenantId == null
                || documentId == null || tenantId.isBlank()
                || documentId.isBlank()) {
            return false;
        }

        // ActorResolver must map verified Authentication
        // to an internal user ID; never take userId from request.
        String actorId = actorResolver.requireUserId(authentication);

        if (!memberships.isActiveMember(actorId, tenantId)) {
            return false;
        }

        var target = documents.findByIdAndTenantId(
                documentId, tenantId);
        if (target.isEmpty()) {
            return false;
        }

        var document = target.get();
        if (!document.canBeEditedInCurrentStatus()) {
            return false;
        }

        boolean owns = actorId.equals(document.getOwnerId());
        boolean delegated = memberships.hasDocumentEditAnyGrant(
                actorId, tenantId);

        return owns || delegated;
    }
}
```

**This is an integration/architecture class and does not compile standalone** without `ActorResolver`, `TenantMembershipRepository`, `DocumentRepository`, `Document`, and matching imports. Methods `isActiveMember`, `hasDocumentEditAnyGrant`, `findByIdAndTenantId`, and `canBeEditedInCurrentStatus` are contracts **the application must implement** using trusted data.

**Important:** `ActorResolver.requireUserId` may throw an exception on invalid token/subject mapping; policy/exception translation must fail closed. For policies needing cross-tenant handling, use a dedicated scope/permission rather than returning `true` for an unscoped ADMIN role.

### 8.5. Parameter names in SpEL

`#tenantId` and `#documentId` work only if Spring Security discovers parameter names in compiled code (via compiler `-parameters` or `@P` annotations):

```java
import org.springframework.security.access.method.P;

@PreAuthorize(
    "@documentAccess.canEdit(authentication, #tenant, #target)"
)
public DocumentView update(
        @P("tenant") String tenantId,
        @P("target") String documentId,
        UpdateDocumentRequest request) {
    // ...
}
```

This example is a **fragment**. If the expression cannot resolve a parameter, it may throw an error or evaluate wrongly; verify via integration tests, never change the expression to `permitAll` to “fix” it.

## 9. Pre-checks are insufficient if data can change between check and write

### 9.1. TOCTOU: time of check vs. time of use

Suppose:

```text
T0: canEdit reads d1.ownerId=alice => permitted.
T1: An admin changes d1.ownerId=bob.
T2: Alice's service writes d1.title after being permitted at T0.
```

If permissions are checked only in `@PreAuthorize` before the transaction/body, the check can go “stale” when data mutates. This is *time-of-check-to-time-of-use*.

**Solution:** keep `@PreAuthorize` as the entry gate, and also:
- Reload the target inside a tenant-scoped transaction.
- Re-check owner/ACL/status right before mutation.
- Use optimistic locking (`@Version`), pessimistic locks, or **guarded SQL updates** depending on the use case.
- Ensure writes and permission conditions share the appropriate transaction/isolation.

Do not assume merely adding `@Transactional` eliminates every race: method-security advice and transaction interceptors have configurable order, and concurrency can occur between reads depending on isolation. For sensitive actions, enforcing conditions in the write statement is usually stronger.

### 9.2. Guarded SQL update for owner-only operations

Illustrative PostgreSQL/SQL example:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :authorized_tenant_id
  AND owner_id = :trusted_actor_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Parameters must be bound via prepared statements/JPA queries, **never concatenating raw SQL from requests**. In particular, `trusted_actor_id` comes from the authentication identity resolver, `authorized_tenant_id` is membership-checked, and DB `owner_id` acts as a guard.

**Interpreting the result:**
- Affected rows = 1 → conditions held at update time; mutation succeeded.
- Affected rows = 0 → no matching row/wrong tenant/wrong owner/stale status/stale version; never fall back to updating by `WHERE id=:id` alone.

This pattern is for **owner-only editing**; `document:edit:any` requires a separate scoped and audited policy/statement branch. Never extend the SQL with `OR :isAdminFromBody`.

### 9.3. @Version and concurrent overwrites

A JPA entity with:

```java
@Version
private long version;
```

enables optimistic locking to detect concurrent data updates. However, **`@Version` does not prove owner/tenant rights by itself**. Combine versions with policy scoping and verified permission updates. When strong atomicity between membership and mutation is required, consider transaction locks, DB-level security checks, or matching consistency mechanisms.

### 9.4. Never use @PostAuthorize to “check after deleting”

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public Document deleteAndReturn(String id) {
    return repository.deleteById(id);
}
```

This is a **conceptual anti-pattern**, and `deleteById` actually has different return types depending on the repository. The core issue: `@PostAuthorize` evaluates after the method body, so a write/delete may **already have occurred**. Spring Security docs warn `@PostAuthorize` is unsuitable as the sole barrier for database-writing methods.

Use `@PreAuthorize` and verify transaction/DB invariants at mutation time. `@PostAuthorize` can fit certain read methods, though in multi-tenant apps you should still query **within scope** before building a response.

## 10. Update service: expressing two explicit control layers

### 10.1. Service fragment with pre-check and in-transaction checks

```java
package com.example.documents.service;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentApplicationService {

    private final DocumentRepository documents;
    private final ActorResolver actorResolver;
    private final TenantMembershipRepository memberships;

    public DocumentApplicationService(
            DocumentRepository documents,
            ActorResolver actorResolver,
            TenantMembershipRepository memberships) {
        this.documents = documents;
        this.actorResolver = actorResolver;
        this.memberships = memberships;
    }

    @Transactional
    @PreAuthorize(
        "isAuthenticated() and " +
        "hasAuthority('document:edit') and " +
        "@documentAccess.canEdit(authentication, #tenantId, #documentId)"
    )
    public DocumentView update(
            String tenantId,
            String documentId,
            UpdateDocumentRequest request) {

        String actorId = actorResolver.requireCurrentUserId();
        // tenantId is a selector; membership must be read from DB.
        if (!memberships.isActiveMember(actorId, tenantId)) {
            throw new AccessDeniedException("Access denied");
        }

        var document = documents.findByIdAndTenantId(
                documentId, tenantId).orElseThrow(
                    () -> new DocumentNotFoundException(documentId));

        if (!document.canBeEditedInCurrentStatus()) {
            throw new AccessDeniedException("Access denied");
        }

        boolean owns = actorId.equals(document.getOwnerId());
        boolean delegated = memberships.hasDocumentEditAnyGrant(
                actorId, tenantId);
        if (!owns && !delegated) {
            throw new AccessDeniedException("Access denied");
        }

        // Map only permitted fields.
        document.setTitle(request.title());
        document.setBody(request.body());

        // ownerId, tenantId, role/ACL, and status are not mapped.
        return new DocumentView(
                document.getId(),
                document.getTitle(),
                document.getBody());
    }
}
```

This **Spring Boot/JPA fragment** requires application classes/repositories/entities, DTO/view imports, and `DocumentNotFoundException`. `ActorResolver.requireCurrentUserId()` must read the current verified authentication, never a body `userId`. Under JPA transactions, dirty checking persists changed title/body; if the repository is not JPA or entities are unmanaged, save/flush per your persistence layer's contract.

**Does not solve every race:** the re-check protects during method execution, yet if ownership can change concurrently right after the re-check, locks, versions, or guarded writes as in section 9 are needed. Update APIs must include concurrency tests if ownership can change mid-request.

### 10.2. Why look up by both id and tenant?

`findByIdAndTenantId(documentId, tenantId)` creates an extra barrier: a document ID from `org-b` cannot be loaded as a valid target inside `org-a`. However, tenant-scoped lookup **is not enough** when Alice and Bob are both in `org-a` yet Alice cannot edit Bob's document. Owner/ACL checks remain mandatory.

### 10.3. Do not expose unauthorized metadata in responses

Even when a user may edit title/body, they may not be authorized to view sensitive fields like `internalRiskScore`, `auditApprovers`, or `tokens`. Response DTOs should allowlist returned fields rather than serializing full JPA entities by default.

This prevents **broken object property level authorization on reads**, not just mass assignment on writes.

## 11. Creating resources: owner and tenant are set server-side

### 11.1. Secure create flow

```text
Client:
  POST /api/tenants/org-a/documents
  body = { "title": "...", "body": "..." }

Controller:
  parse DTO, validate editable fields

Security:
  authenticated + document:create

Application service:
  actorId = trusted Authentication mapping
  check active membership in org-a
  document.tenantId = org-a
  document.ownerId = actorId
  document.status = DRAFT
  document.roles/ACL = server policy
  save with tenant constraints
```

### 11.2. @PreAuthorize fragment for create

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "hasAuthority('document:create') and " +
    "@tenantAccess.canCreate(authentication, #tenantId)"
)
@Transactional
public DocumentView create(
        String tenantId,
        CreateDocumentRequest request) {

    String actorId = actorResolver.requireCurrentUserId();
    tenantAccess.requireActiveMember(actorId, tenantId);

    Document created = new Document();
    created.setTenantId(tenantId);
    created.setOwnerId(actorId);
    created.setStatus(DocumentStatus.DRAFT);
    created.setTitle(request.title());
    created.setBody(request.body());

    return mapper.toView(repository.save(created));
}
```

This is a **fragment** requiring the `tenantAccess` bean and application-defined dependencies, plus entity/mapper contracts. Although `tenantId` appears on the path and sets the entity field, **membership and policy have verified it**; that is the decisive difference from taking raw `tenantId` from the body without verification.

### 11.3. Never let create honor client-claimed ownership

If the request also sends:

```json
{
  "title": "New document",
  "body": "Content",
  "ownerId": "admin",
  "tenantId": "org-b",
  "isAdmin": true
}
```

the system must reject unknown fields per contract or ignore them during DTO binding; never create documents with owner/tenant from those fields. Post-create DB tests must assert:
- owner = trusted actor;
- tenant = verified tenant;
- status = server default status;
- role/ACL not elevated;
- other users cannot gain permissions simply by sending extra fields.

## 12. Tenant selection and active membership

### 12.1. Multi-tenancy is more than USER/ADMIN roles

A user might have:

```text
Alice:
  org-a: EDITOR
  org-b: VIEWER
```

If the backend only has a global `ROLE_EDITOR`, Alice could mistakenly edit `org-b` documents. You need **per-tenant authorities** or tenant membership/role checks in the policy.

Policy example:

```text
canEdit(actor, tenant, document) =
  activeMembership(actor, tenant)
  AND membershipRole(actor, tenant) includes EDITOR
  AND document.tenantId == tenant
  AND (document.ownerId == actor OR tenantGrant allows editAll)
```

Any role hierarchy must apply within its **appropriate scope**, rather than turning an `org-a` EDITOR into a system-wide EDITOR.

### 12.2. Query path vs. selected tenant

```http
GET /api/tenants/org-b/documents/d9
```

`org-b` is only the tenant requested by the client. The policy must verify Alice has access to `org-b` and document `d9` genuinely belongs to `org-b`. Never use client `X-Tenant-Id` as a substitute for lookup verification.

### 12.3. Prevent header tenant IDs from overriding row tenantId

An interceptor might set a “current tenant context” from a header. If the repository automatically adds a tenant filter whose context came from an **unverified membership header**, tenant filtering becomes user-controlled.

If using `TenantContext`/Hibernate filters:
1. Set only after valid authentication/membership checks.
2. Clean up context properly when thread pools reuse threads.
3. Test fallbacks and async/background job paths.
4. Never rely on it as the sole barrier, especially for raw SQL, native queries, or filter-bypassing paths.
5. With DB row-level security, set session variables from trusted sources and verify connection-pool scoping.

### 12.4. Enforce object permissions before returning data

Even read-only GETs need scope checks. Never call `findAll()` and filter by tenant in the frontend; never serialize cross-tenant entities hoping the browser hides fields. Filter and authorize in the backend/database before returning responses.

## 13. Ownership transfer, tenant moves, and role grants are privileged use cases

### 13.1. Separate endpoints and DTOs

Do not allow ordinary update callers to send `ownerId`. If **transfer ownership** exists:

```http
POST /api/tenants/org-a/documents/d1/transfer-owner
Content-Type: application/json
Authorization: Bearer <trusted-token>

{ "newOwnerId": "u9" }
```

Dedicated DTO:

```java
public record TransferOwnerRequest(String newOwnerId) {}
```

**Even though the DTO has `newOwnerId`, it is still only a target selector.** The policy must verify:

- Actor holds `document:transfer-owner` in this tenant.
- Real document belongs to the active tenant.
- New owner exists and is an eligible active member of the tenant.
- Workflow/approval rules permit the transfer.
- Transactional consistency and auditing.

Similarly, “moving tenant” affects ownership, ACLs, billing, retention, and data residency. Never disguise it as an implicit `PATCH tenantId`.

### 13.2. Role assignment does not belong in profile updates

```http
PATCH /api/users/u1/profile
{ "displayName": "Alice", "roles": ["ROLE_ADMIN"] }
```

The profile endpoint should only update display name and matching fields. Role assignment needs its own use case:

```http
POST /api/admin/tenants/org-a/users/u1/grants
{ "permission": "document:review" }
```

It must verify the actor is allowed to grant **that specific permission**, cannot grant higher than delegable privileges, and checks target user/tenant, SoD, approvals, expiry, and auditing. `hasRole('ADMIN')` alone may be insufficient in multi-tenant SaaS or sensitive permission delegation.

### 13.3. Guarding against privilege escalation

If a user only holds `users:manage-basic`, they must not be able to grant `ROLE_SUPER_ADMIN` to themselves or colleagues. Policy pattern:

```text
ALLOW_GRANT(actor, target, grant) =
  actor has "user:grant:manage" in target tenant
  AND grant in actor.allowedDelegableGrants
  AND target is eligible in target tenant
  AND (actor != target OR explicit self-grant allowed)
  AND approval / separation-of-duties rules satisfied
```

This policy is **business pseudocode**. `allowedDelegableGrants` must be managed by a trusted backend/DB/policy service, never taken from the request payload.

## 14. Spring MVC binding: DTOs, @ModelAttribute, and Jackson

### 14.1. @RequestBody JSON and @ModelAttribute form data differ

- `@RequestBody` typically binds JSON/XML via `HttpMessageConverter` (usually Jackson for JSON).
- `@ModelAttribute` uses Spring `WebDataBinder` to bind form/query/path/header data into model objects per rules.
- Both must avoid binding directly into entities holding `ownerId`, `tenantId`, `roles`, `balance`, or `locked`.

Spring Framework reference recommends dedicated web-binding objects or constructor binding; when using property binding, configure a strict **allowedFields** list.

### 14.2. Using @InitBinder with an allowlist when binding form objects

```java
@InitBinder("profileForm")
public void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "timezone");
}

@PostMapping("/profile")
public String updateProfile(
        @ModelAttribute("profileForm") ProfileForm form) {
    // Prevents client from binding role, isAdmin, ownerId.
    // Still requires authorization on the user profile.
    return "redirect:/profile";
}
```

This is an **MVC fragment** with an application-defined `ProfileForm`, not standalone code. `allowedFields` shrinks the binder surface yet does not replace authorization on the target profile. If using constructor binding, inspect both constructor parameters and DTO schema.

### 14.3. Never use BeanUtils.copyProperties indiscriminately

```java
// Anti-pattern when request may carry unpermitted fields:
BeanUtils.copyProperties(request, persistentUser);
```

If the request has `roles` or `isAdmin` and the target object has matching setters, a generic helper can accidentally copy sensitive values. An explicit allowlist:

```java
user.setDisplayName(request.displayName());
user.setTimeZone(request.timeZone());
```

makes it clear to reviewers exactly which properties may change. Code-generated mappers must likewise be configured to map only valid fields; never assume MapStruct or reflection mappers know caller permissions.

### 14.4. Bean Validation is not authorization

`@NotBlank`, `@Size`, and `@Email` only validate data format and bounds. A `@Valid` DTO with a well-formed `ownerId` is **still** a client-forgeable field. Separate:
- validation: is the data syntactically valid?
- authentication: who is the caller?
- authorization: may the caller modify this resource/property?
- domain invariant: is the resulting post-update state valid?

## 15. Testing: how to prove spoofing is impossible?

### 15.1. Minimum matrix

Assume:
- Alice belongs to org-a, owns `d1`, and has `document:edit`.
- Bob belongs to org-a and owns `d2`.
- Mallory belongs to org-b and owns `d3`.
- An organization editor has `document:edit:any` in org-a.
- Viewer has `document:read`, without `document:edit`.

| Scenario | Request | Expected |
| --- | --- | --- |
| Alice edits d1 title | Valid tenant + permission + owner | ALLOW, title updated |
| Alice adds `ownerId=bob` to d1 edit JSON | Extra sensitive field | REJECT or IGNORE; DB owner unchanged |
| Alice adds `isAdmin=true`, `roles=[ADMIN]` | Extra permission fields | No privilege escalation |
| Alice edits Bob's d2 claiming `ownerId=alice` | Object-level forgery | DENY, d2 unchanged |
| Alice edits d3 in org-b | Cross-tenant | DENY/NOT_FOUND, d3 unchanged |
| Alice changes tenant path to org-b | Forged selected tenant | DENY due to missing membership |
| Bob edits Bob's document | Valid permissions | ALLOW |
| Viewer edits own document | Missing functional permission | DENY |
| User with org-a edit:any edits d2 | Scoped permission | ALLOW in org-a, does not open org-b |
| org-a admin edits roles in org-b | Wrong scope | DENY |
| Alice transfers owner via title PATCH | Wrong endpoint | Owner unchanged |
| Alice attempts to grant ROLE_ADMIN via profile | Mass assignment | Authorities unchanged |
| Alice edits d1 after leaving org-a | Revoked membership | DENY if policy requires active membership |
| Alice edits d1 after ownership moved to Bob | Stale ownership | DENY under real policy at write time |
| Request sends out-of-scope documentId d2 | Direct object reference | No d2 content leaked |
| Test uses only `@WithMockUser(roles=ADMIN)` | Over-privileged fixture | Does not prove ordinary users are blocked |

**Expected HTTP status:** 403 may be used for known resources lacking permission, or 404 to avoid disclosing cross-tenant objects, per the app's contract/anti-enumeration policy. More important than the exact code is **zero unauthorized reads/writes and zero data leakage**. When choosing 404, never return cross-tenant metadata in the error body.

### 15.2. MockMvc test for forged owner

Fragment in a Spring Boot test with `MockMvc`, `@WithMockUser`/auth mapping tests, repository fixtures, and CSRF handling:

```java
@Test
@WithMockUser(username = "alice",
        authorities = "document:edit")
void cannotEditBobsDocumentByForgingOwnerId() throws Exception {

    mockMvc.perform(patch("/api/tenants/org-a/documents/d2")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                    {
                      "title": "Overwritten",
                      "body": "Bad change",
                      "ownerId": "alice"
                    }
                    """)
            .with(csrf()))
        .andExpect(status().isForbidden());

    assertThat(documentRepository.findById("d2").orElseThrow()
            .getTitle()).isEqualTo("Bob original");
}
```

**Fragment assumptions:** fixture `d2` belongs to Bob in `org-a`, Alice has edit but not `edit:any`, and the API contract **ignores** extra JSON fields and enforces authorization before writes; if configured to reject unknown fields, the request may return 400 early. Either way, data must remain unchanged. Do not let a test “pass” merely because the JSON parser returned 400 and mistake that for testing object policy; add a test **without extra fields** still attempting unauthorized edits to `d2` and assert deny.

### 15.3. MockMvc test where body carries extra fields without altering metadata

```java
@Test
@WithMockUser(username = "alice",
        authorities = "document:edit")
void editableFieldsDoNotOverwriteOwnerOrTenant() throws Exception {

    mockMvc.perform(patch("/api/tenants/org-a/documents/d1")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                    {
                      "title": "Safe update",
                      "body": "Content",
                      "ownerId": "bob",
                      "tenantId": "org-b",
                      "isAdmin": true
                    }
                    """)
            .with(csrf()))
        .andExpect(status().isOk());

    var saved = documentRepository.findById("d1").orElseThrow();
    assertThat(saved.getOwnerId()).isEqualTo("alice");
    assertThat(saved.getTenantId()).isEqualTo("org-a");
}
```

This **fragment illustrates an ignore-unknown-fields contract** and assumes the controller returns 200 with valid fixtures and auth mapping. If the application chooses **reject unknown fields**, change the expectation to 400 and assert every field remains unchanged; never weaken `SecurityFilterChain` to let the request through. Also verify Alice's server-side `authorities` did not change, not only entity owner/tenant.

### 15.4. Testing a forged tenant path

```java
@Test
@WithMockUser(username = "alice",
        authorities = "document:edit")
void cannotUseAnotherTenantPath() throws Exception {

    mockMvc.perform(patch("/api/tenants/org-b/documents/d3")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                    { "title": "Attempt", "body": "Attempt" }
                    """)
            .with(csrf()))
        .andExpect(status().isForbidden());

    assertThat(documentRepository.findById("d3").orElseThrow()
            .getTitle()).isEqualTo("Mallory original");
}
```

A project applying anti-enumeration with 404 here should test per the 404 contract; what matters is `d3` remains unchanged. Requires a `tenant_memberships` fixture placing Alice only in `org-a`.

### 15.5. Service-level testing through the proxy

Unit tests for `DocumentAccessPolicy` can mock repositories and check:
- document in tenant `org-b` when `org-a` selected → false;
- document in `org-a` owned by Bob without `edit:any` → false;
- document in `org-a` owned by Alice with active membership → true;
- actor lacking membership → false;
- locked document → false.

Next, integration-test `@PreAuthorize` on the **Spring-managed service bean** with `@EnableMethodSecurity`. Calling `new DocumentApplicationService(...)` directly cannot test the AOP interceptor; calling `this.update(...)` inside the same bean can bypass method security.

### 15.6. Testing no-side-effect and stale state

For PATCH/DELETE, asserting 403 alone is insufficient. Check:
- Original data is untouched (`title`, `ownerId`, `tenantId`, `status`, `version`).
- No “DocumentUpdated” event or spurious notification is emitted.
- No fake audit event claiming the operation succeeded.
- No cross-tenant document info leaked in responses/logs.
- `role`/`permissions` fields on user records are unchanged.
- On concurrent ownership/membership changes between check and write, guarded updates affect 0 rows and transactions perform no unauthorized writes.

### 15.7. Testing authorization with real tokens

`@WithMockUser` tests policies yet **does not** verify JWT signature/issuer/audience/converters. Add integration tests using real security configuration:
- Valid token for Alice.
- Valid token for Bob/Mallory.
- Token with tampered payload/claims.
- Token from untrusted issuer/audience.
- Expired or revoked token per system design.
- Token holding tenant A role calling tenant B.
- Old token after membership removal.

Never store production tokens in test fixtures or logs.

## 16. Standalone Java 17: demonstrating resistance to owner/tenant/role forgery

The program below **needs no Spring**, using Java 17 to illustrate the core principle. It models server-side documents, an actor with verified memberships and authorities, and an **untrusted** request body map. Only `title` is read from the body; owner/tenant come from the server record. The policy checks functional permission, membership, object tenant, and owner/`edit:any`.

This is a **learning model**, not Spring `SecurityContextHolder`, a JWT verifier, a persistence layer, or a production policy. It has no transactions/concurrency/CSRF; those constraints must be added in real application code.

Create `OwnerTenantForgeryDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class OwnerTenantForgeryDemo {

    record Actor(
            String userId,
            Set<String> tenantMemberships,
            Set<String> authorities) {
    }

    static final class Document {
        final String id;
        final String tenantId;
        final String ownerId;
        String title;

        Document(String id, String tenantId, String ownerId, String title) {
            this.id = id;
            this.tenantId = tenantId;
            this.ownerId = ownerId;
            this.title = title;
        }
    }

    static String update(
            Map<String, Document> serverData,
            Actor actor,
            String selectedTenant,
            String documentId,
            Map<String, Object> untrustedBody) {

        if (actor == null
                || !actor.authorities().contains("document:edit")) {
            return "DENY_PERMISSION";
        }
        if (!actor.tenantMemberships().contains(selectedTenant)) {
            return "DENY_TENANT";
        }

        Document target = serverData.get(documentId);
        if (target == null || !target.tenantId.equals(selectedTenant)) {
            return "NOT_FOUND";
        }

        boolean isOwner = target.ownerId.equals(actor.userId());
        boolean mayEditAny =
                actor.authorities().contains("document:edit:any");

        if (!isOwner && !mayEditAny) {
            return "DENY_OWNER";
        }

        Object requestedTitle = untrustedBody.get("title");
        if (!(requestedTitle instanceof String title)
                || title.isBlank()) {
            return "BAD_TITLE";
        }

        // Only the title field is updated in this use case.
        // ownerId, tenantId, isAdmin, and roles from body are ignored.
        target.title = title;
        return "UPDATED";
    }

    public static void main(String[] args) {
        Map<String, Document> db = new HashMap<>();
        db.put("d1", new Document(
                "d1", "org-a", "alice", "Original Alice"));
        db.put("d2", new Document(
                "d2", "org-a", "bob", "Original Bob"));
        db.put("d3", new Document(
                "d3", "org-b", "mallory", "Original Mallory"));

        Actor alice = new Actor(
                "alice",
                Set.of("org-a"),
                Set.of("document:edit"));

        Actor bob = new Actor(
                "bob",
                Set.of("org-a"),
                Set.of("document:edit"));

        Actor viewer = new Actor(
                "alice",
                Set.of("org-a"),
                Set.of("document:read"));

        Actor manager = new Actor(
                "manager",
                Set.of("org-a"),
                Set.of("document:edit", "document:edit:any"));

        Actor mallory = new Actor(
                "mallory",
                Set.of("org-b"),
                Set.of("document:edit"));

        Map<String, Object> forged = Map.of(
                "title", "Renamed by Alice",
                "ownerId", "bob",
                "tenantId", "org-b",
                "roles", Set.of("ROLE_ADMIN"),
                "isAdmin", true);

        System.out.println("alice-owned="
                + update(db, alice, "org-a", "d1", forged));
        System.out.println("owner-after-forgery="
                + db.get("d1").ownerId);
        System.out.println("tenant-after-forgery="
                + db.get("d1").tenantId);
        System.out.println("title-after-forgery="
                + db.get("d1").title);

        System.out.println("alice-edits-bob="
                + update(db, alice, "org-a", "d2",
                        Map.of("title", "Overwritten",
                                "ownerId", "alice")));

        System.out.println("alice-cross-tenant="
                + update(db, alice, "org-b", "d3",
                        Map.of("title", "Overwritten")));

        System.out.println("alice-id-cross-scope="
                + update(db, alice, "org-a", "d3",
                        Map.of("title", "Overwritten")));

        System.out.println("viewer-edits="
                + update(db, viewer, "org-a", "d1",
                        Map.of("title", "Not allowed")));

        System.out.println("bob-edits-own="
                + update(db, bob, "org-a", "d2",
                        Map.of("title", "Bob revision")));

        System.out.println("manager-edits-bob="
                + update(db, manager, "org-a", "d2",
                        Map.of("title", "Manager revision")));

        System.out.println("foreign-tenant-view="
                + update(db, mallory, "org-b", "d2",
                        Map.of("title", "Cross-scope")));

        System.out.println("bob-final-title="
                + db.get("d2").title);
    }
}
```

Compile/run with **JDK 17 or later**:

```bash
javac OwnerTenantForgeryDemo.java
java OwnerTenantForgeryDemo
```

Expected stdout:

```text
alice-owned=UPDATED
owner-after-forgery=alice
tenant-after-forgery=org-a
title-after-forgery=Renamed by Alice
alice-edits-bob=DENY_OWNER
alice-cross-tenant=DENY_TENANT
alice-id-cross-scope=NOT_FOUND
viewer-edits=DENY_PERMISSION
bob-edits-own=UPDATED
manager-edits-bob=UPDATED
foreign-tenant-view=NOT_FOUND
bob-final-title=Manager revision
```

### 16.1. Interpretation

1. Body `forged` contains `ownerId=bob`, `tenantId=org-b`, `ROLE_ADMIN`, `isAdmin=true`. However, **the server only reads title** for editing; d1's owner/tenant remain Alice/org-a.
2. Alice editing Bob's d2 while claiming `ownerId=alice` in the request still gets `DENY_OWNER` because the policy compares against **d2.ownerId stored in the DB**.
3. Alice requesting tenant `org-b` gets `DENY_TENANT` because she is not a member.
4. Alice selecting `org-a` while targeting `d3` from `org-b` gets `NOT_FOUND` under scope, leaking nothing.
5. Viewer lacks `document:edit` so gets `DENY_PERMISSION` even within the assumed tenant.
6. Bob editing his own d2 is allowed; manager holding **server-granted** `document:edit:any` and `org-a` membership can also edit d2.
7. Mallory cannot edit d2 via tenant `org-b` because d2 actually belongs to `org-a`.
8. Final data for d2 is “Manager revision”; zero unauthorized updates occurred in the demo.

### 16.2. Limitations to remember

- `Actor` in the demo is trusted data constructed by the program; in Spring it must come from verified `Authentication`/policy services.
- `document:edit:any` in the demo is valid only when tenant membership matches. Production needs scoped grants in the DB.
- The Map body represents arbitrary data to illustrate mass assignment; real controllers should use **allowlist DTOs** instead of freeform `Map<String,Object>`.
- The demo HashMap lacks locks, concurrency, durable storage, business workflows, CSRF, and auditing.
- Strings `DENY_OWNER`/`NOT_FOUND` are educational labels, not automatic framework HTTP status codes.
- Demo code does not verify tokens or run Spring `@PreAuthorize`; run real Spring tests as in earlier sections.

## 17. Common implementation mistakes

| Mistake | Why dangerous | Fix |
| --- | --- | --- |
| `@PreAuthorize("#request.ownerId == authentication.name")` | `request.ownerId` can be spoofed | Fetch current owner from DB by documentId |
| `findById(id)` then check role USER | BOLA: same role can still have different owner/tenant | Query by tenant + ACL/owner |
| `BeanUtils.copyProperties(request, entity)` | Can copy permission, owner, tenant fields | Narrow DTO + explicit mapping |
| `@RequestBody UserEntity user` | Client can bind sensitive fields into entity | Separate Create/Update DTOs |
| `@Valid` on entity treated as sufficient | Validation is not authorization | Check object/attribute/tenant scope |
| Trusting `ownerId`/`tenantId` from body | Client dictates security metadata | Server creates/maintains those fields |
| Using `X-Tenant-Id` without checking membership | Easy cross-tenant requests | Verify active membership in backend |
| Treating browser `X-User-Id` as principal | Spoofed identity header | Use verified SecurityContext |
| JWT `sub` treated as enough for all documents | Token identity does not prove object rights | Domain policy per target |
| Global `ROLE_ADMIN` applied to all tenants | Privileges spill across tenants | Scope roles/grants per tenant |
| Treating hard-to-guess resource UUIDs as permission | IDOR still exploitable once ID leaks | Enforce object-level authorization |
| `@PostAuthorize` on write/delete methods | Check runs after side effects | Pre-check + guarded/transactional write |
| Checking only before transaction | TOCTOU when owner/ACL mutates | Re-check, lock/version/conditional update |
| 403 returned yet DB still mutated | Side effect happened before deny | Block before mutation and assert no side effects |
| `@PreAuthorize` skipped in tests | Method security disabled or self-invocation | `@EnableMethodSecurity` + proxied bean |
| Service returning full entity | Leaks security metadata/properties | Response DTO allowlist |
| User profile PATCH allowing role edits | Privilege escalation | Separate admin grant use case |
| Checking URL tenant ID == JSON tenant ID | Both values are client-controlled | Compare against membership + DB target tenant |
| Testing only with `@WithMockUser` ADMIN | Hides bugs affecting regular users | Test Alice/Bob/Mallory/Viewer/other tenants |
| Tenant filter using ThreadLocal without cleanup | Can leak tenants across pooled requests | Context lifecycle and scoped DB queries |
| Allowing client-set isAdmin into JWT converter | Self-elevates authorities | Converter accepts only verified issuer claims |
| Removing role in DB while old token still works | Stale claims | TTL, revocation, live policy checks |

### 17.1. Diagnostic workflow when weird 403/404 appear

1. Identify the real principal from verified `Authentication` (never log raw tokens).
2. Identify functional authorities, role prefixes, and claim converters.
3. Treat target document ID from request **strictly as a selector**.
4. Read current document tenant/owner/status from the database within the proper scope.
5. Read active tenant membership and actor ACL/grants.
6. Verify whether `@PreAuthorize` actually ran via proxy and which policy bean it called.
7. Verify whether the service performs re-checks/guarded writes.
8. Identify whether 403 came from method/HTTP/CSRF or 404 came from scoped lookup; never guess from status alone.
9. Test thoroughly for no-side-effects and zero out-of-scope data disclosure in responses.
10. If caches/JWTs/replicas exist, verify permission data is not stale.

**Never fix errors by opening `permitAll()`, disabling CSRF, or granting global ADMIN to users.**

## 18. Deployment checklist, self-check questions, and conclusion

### 18.1. Pre-deployment checklist

**Input and identity**
- [ ] Controllers use create/update DTOs containing only fields users may change.
- [ ] Never bind requests directly into JPA entities holding owner/tenant/roles.
- [ ] Unknown fields are intentionally rejected or ignored; tests enforce that decision.
- [ ] Authentication is verified by Spring Security; actor ID mapping is clear and stable.
- [ ] Never trust `X-User-Id`, `X-Role`, `ownerId`, or `isAdmin` from public clients.
- [ ] JWT issuer/audience/signature/expiry/scopes are verified per version.

**Authorization**
- [ ] `@EnableMethodSecurity` is active with `@PreAuthorize`.
- [ ] `hasAuthority`/`hasRole` act only as functional entry gates, never replacing object policies.
- [ ] `@documentAccess` uses current DB owner/tenant/membership/ACL.
- [ ] Path tenant selectors are verified against membership and target resources.
- [ ] Methods are invoked via Spring-managed proxies; negative tests exist for self-invocation.
- [ ] Tenant A admin is never treated as tenant B admin.
- [ ] Ownership transfer, tenant moves, and role grants are separate use cases and grants.
- [ ] All service call paths (HTTP, queues, cron, batch, GraphQL) enforce matching policies.

**Persistence**
- [ ] Create sets `ownerId`/`tenantId`/`status` server-side.
- [ ] Update maps only editable fields using an allowlist.
- [ ] Scoped queries enforce tenant + object-level checks.
- [ ] Re-checks/guarded updates/optimistic locking exist when ownership can change concurrently.
- [ ] Every DENY produces zero side effects, including queue events or false business-success audits.
- [ ] Response DTOs do not leak internal unauthorized fields.

**Tests and operations**
- [ ] Tested Alice own, Alice→Bob, Alice→tenant B, Viewer, scoped editor.
- [ ] Tested injecting `ownerId`, `tenantId`, `roles`, `isAdmin` into requests.
- [ ] Tested valid token with another user's ID.
- [ ] Tested role revocation, membership revocation, stale tokens.
- [ ] Tested 400/403/404 per contract and no-side-effects.
- [ ] Tested concurrency when owner/tenant permissions can change.
- [ ] Audited actor, target, action, tenant, and outcome without excessive token/PII logging.
- [ ] Policies underwent code review and regression testing before deployment.

### 18.2. Self-check questions

**Q1.** Alice is authenticated and holds `document:edit`. May she edit every document?

**Answer:** No. The document must belong to an allowed tenant, satisfy owner/ACL rules, and be in an editable business state.

**Q2.** The body says `"ownerId":"alice"`, matching `authentication.name`. Does that prove Alice is the owner?

**Answer:** No. The client typed `ownerId`. Fetch the target document's owner from the DB or a trusted server source.

**Q3.** Does path `/tenants/org-b/...` prove the user belongs to `org-b`?

**Answer:** No. The path only selects a target scope. Verify active membership and resource tenant server-side.

**Q4.** Is replacing numeric IDs with hard-to-guess UUIDs enough to stop BOLA?

**Answer:** No. IDs can leak via logs, URLs, emails, notifications, or clients; every object operation needs authorization.

**Q5.** Why is `UpdateDocumentRequest(title, body)` better than binding `DocumentEntity`?

**Answer:** The DTO exposes only fields meant to be edited, preventing accidental binding of `ownerId`, `tenantId`, roles, audit fields, or sensitive metadata.

**Q6.** Does `@Valid` prevent a user from setting role ADMIN on an entity?

**Answer:** No. Bean Validation checks structural/value validity and does not know which fields the caller may edit. DTO allowlists and authorization are required.

**Q7.** Should `@PostAuthorize` serve as the sole authorization check after deleting data?

**Answer:** No. The method body may already have deleted data before the check. Use pre-authorization and verify in transaction/DB before mutating.

**Q8.** Why re-check before writing even after `@PreAuthorize` passed?

**Answer:** Owner/tenant/ACL/status can change between check and write; prevent TOCTOU using scoped lookups, locking/versions, or guarded updates as required.

**Q9.** Does a valid JWT holding an `org-a` role allow editing `org-b` data?

**Answer:** No. Check scope/membership and per-resource/tenant permissions rather than turning one tenant's role into global access.

**Q10.** Is `authentication.name` always the DB user UUID?

**Answer:** No. It depends on the provider/converter and may be username/email/JWT subject. Map reliably to a stable internal actor ID.

**Q11.** If an API ignores unknown fields, is a payload with `isAdmin=true` always safe?

**Answer:** Safe only if DTOs/mappers **genuinely never touch** that field and tests prove DB/permissions stay unchanged. Rejecting unknown fields can make the contract stricter.

**Q12.** A user changes `tenantId` in JSON without changing the path. The backend checks only that path and body strings match. Is that enough?

**Answer:** No. Both path and body are client-controlled. Compare against active membership and the record's actual tenant.

**Q13.** A manager has `edit:any` in `org-a` and wants to edit `d3` in `org-b`. Is it allowed?

**Answer:** No if the grant is scoped to `org-a`; explicit cross-tenant permissions and appropriate business approval are required.

**Q14.** Does testing only a 403 response status prove data was not modified?

**Answer:** No. Assert DB, event queues, and side effects remain untouched; sometimes code writes before throwing access denied.

**Q15.** Is custom `@documentAccess.canEdit(authentication,#tenantId,#documentId)` sufficient if the service calls `this.update`?

**Answer:** No under normal Spring AOP proxies; self-invocation can bypass the interceptor. Structure service boundaries/proxy tests properly and keep invariants in service/DB.

**Q16.** Can a browser send `X-User-Id` to choose an identity?

**Answer:** No. Only a trusted gateway behind a boundary guaranteeing authentication, header overwriting, and anti-bypass can supply identity per a dedicated contract; public clients cannot self-declare identity.

**Q17.** When business rules allow ownership transfer, should `ownerId` be reopened inside the title PATCH?

**Answer:** No. Use a dedicated transfer-owner use case with its own permissions, target validation, workflow, transaction, and audit.

**Q18.** The system has a `RoleHierarchy` `ADMIN > USER`; must owner/tenant still be checked?

**Answer:** Yes. A hierarchy only infers functional permissions if configured; it does not know who owns a record or which tenant it belongs to.

### 18.3. Summary

A secure API never trusts `ownerId`, `tenantId`, or any permission field just because it appears in a request or matches a familiar string. **Identity comes from verified authentication; ownership, tenant, and ACLs come from server data; requests carry only selectors and legitimately editable fields.**

Use `@PreAuthorize` as the **pre-method** gate, combining `hasAuthority` with object-checking policy beans. To prevent BOLA, privilege escalation, and races, place invariants in services/transactions/databases, use narrow DTOs, and apply guarded updates where needed. Tests must prove **no reads, no writes, and no privilege escalation** when clients forge any ID or sensitive property.

## References

- Spring Security — Method Security, `@PreAuthorize`, custom bean SpEL, method parameters, and `@PostAuthorize` write caveat: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — HTTP request authorization, `hasRole`/`hasAuthority`/`denyAll`: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication architecture and `SecurityContextHolder`: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Framework — `@ModelAttribute` binding and `allowedFields`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API Security Top 10 — API3:2023 Broken Object Property Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP Cheat Sheet Series — Mass Assignment: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
- OWASP Cheat Sheet Series — Authorization: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP Cheat Sheet Series — IDOR Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
