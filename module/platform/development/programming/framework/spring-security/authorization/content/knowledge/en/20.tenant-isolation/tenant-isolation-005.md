# Multi-Tenant Users and Workspace Context Switching

## 1. The problem: one identity, multiple workspaces

A SaaS application may allow a single user to belong to multiple organizations or workspaces (*tenants*). For example, Alice holds one account yet carries different permissions across tenants:

| User | Tenant | Role in tenant | Typical permissions |
| --- | --- | --- | --- |
| Alice | `tenant-a` | EDITOR | View, create, and edit A's documents |
| Alice | `tenant-b` | VIEWER | View permitted documents in B only |
| Bob | `tenant-b` | ADMIN | Manage B's members and data |
| Alice | `tenant-c` | Not a member | No access to C |

When Alice selects "Workspace B", this **does not turn Alice into a new user**. The authenticated identity remains Alice, but actions from that point on must be evaluated **within tenant B's scope** and Alice's VIEWER permissions in B—not Alice's EDITOR permissions in A.

Sample request:

```http
GET /api/tenants/tenant-b/documents/42
Authorization: Bearer <alice-access-token>
```

The server must independently answer three questions:

1. **Who is calling?** A valid token/session proves the caller is Alice.
2. **Which tenant is requested, and may Alice use it?** `tenant-b` is only a request selector; the server must verify Alice still holds an active membership in B.
3. **Within B, does Alice have READ permission on Document 42?** Check tenant-scoped roles/permissions, resource ownership, ACLs, and actual data state.

**Core principle:** a tenant ID in a URL, header, JWT, or session **never becomes proof of authorization on its own**. It must be bound to the authenticated subject and a trusted membership/authorization policy.

### Learning objectives

After this lesson you can:

- Distinguish principal, membership list, selected tenant, and resource permissions.
- Deliberately design tenant selection/switching via route, header, server session, or token.
- Prevent roles from tenant A from "leaking" into tenant B.
- Protect queries and writes with tenant scope, even when caching/async/transactions are used.
- Understand the difference between Spring Security Resource Server **multi-issuer authentication** and a user's **active workspace**.
- Build a sample policy/service using Java 17+ and Spring Security.
- Test tenant switching across multiple tabs, membership revocation, concurrent requests, caching, and reused database connections.

## 2. Five concepts to keep separate

| Concept | Example | Source of truth |
| --- | --- | --- |
| `subjectId` / principal | Alice, internal ID `u-101` | Verified Authentication/IdP |
| Tenant | `tenant-a`, `tenant-b` | System tenant registry |
| Membership | Alice belongs to A, B; not C | Trusted membership database/service |
| Active/selected tenant | Current request wants to work in B | Selector sent by UI, **then verified by server** |
| Tenant-scoped permission | Alice has WRITE_DOCUMENT in A, READ_DOCUMENT in B | Membership/role/ACL/policy evaluated in the verified tenant |

Visualize it like this:

```text
               Authenticated subject: alice
                          |
                          v
           Tenant memberships from trusted source
             /           |           \
         tenant-a     tenant-b     tenant-c
         EDITOR       VIEWER       none
            |            |
            +------ selection ------+
                          |
                          v
             Selected tenant for request
                          |
                          v
               Verify membership is still active
                          |
                          v
                Tenant-scoped permissions
                          |
                          v
               Authorize action + resource
                          |
                          v
               DB query with tenant boundary
```

**Common mistake:** putting `ROLE_ADMIN` into `Authentication.getAuthorities()` because Alice is an admin in A and then checking `hasRole('ADMIN')` while Alice works in B. That role lacks tenant scope and can turn Alice into an admin in B as well.

Per-tenant permissions can be modeled via database memberships, or via explicitly namespaced authorities with a strict contract such as `TENANT_A:DOCUMENT_WRITE`. Even then, never trust permission strings from the browser, and never skip resource-level scope checks. Most businesses need a `TenantAccessPolicy` that understands **subject + tenant + action**, rather than inspecting global authorities alone.

## 3. Threat model: tenant switching is a sensitive authorization boundary

Typical attacks or implementation bugs:

1. User edits `/tenants/tenant-a` to `/tenants/tenant-c` and the server uses the new ID without verifying membership.
2. Header `X-Tenant-Id` is passed straight into repositories as the tenant, letting users impersonate another tenant.
3. Session stores `activeTenant=tenant-b`, yet after Alice is removed from B, the server still trusts the stale session.
4. JWT carries a list of tenants valid at issuance; membership is later revoked before the token expires.
5. Role ADMIN from A is accepted to invoke ADMIN operations in B.
6. Cache fetches data by `documentId` without tenant, returning another tenant's record.
7. One tab switches tenant A → B, causing requests in another tab to silently run under B.
8. Tenant context is stored in a static field or an uncleaned ThreadLocal, getting reused by the next request.
9. An entity was loaded into a JPA/Hibernate session under A, then the app switches tenant on the same persistence context and reads/writes as if in B.
10. Jobs, message consumers, or executors fail to restore the proper tenant context and actor permissions.
11. Native SQL or bulk updates omit the tenant predicate even though normal repository queries include it.
12. A "cross-tenant" admin service uses overly broad DB credentials, inadvertently allowing ordinary user requests to run unscoped.

**Security mandate:** for every tenant-scoped operation, there must be verified proof that **the actor is permitted to perform the action in the selected tenant**, and that the real resource belongs to that tenant. Unpredictable tenant IDs, hiding tenant names from URLs, and frontend default selections are never authorization.

## 4. Distinguishing two meanings of “multi-tenancy” in Spring Security

Spring Security OAuth2 Resource Server documents **OAuth2 Resource Server Multi-tenancy** for a resource server validating bearer tokens from **multiple issuers/authorization servers**, such as issuer A and issuer B. It supports selecting an `AuthenticationManager` per trusted issuer via `JwtIssuerAuthenticationManagerResolver`.

Illustrative snippet from the documentation:

```java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp.example.test/issuer-a",
        "https://idp.example.test/issuer-b"
    );

http.oauth2ResourceServer(oauth2 ->
    oauth2.authenticationManagerResolver(resolver));
```

This is **component configuration** for a Spring Security Resource Server app, requiring imports, JWT dependencies, a filter chain, and real authorization configuration. The `example.test` URLs are illustrative placeholders not meant for production.

The resolver's job is: **which issuer issued the token, and who is authorized to verify its signature/claims?** It **does not automatically answer** whether Alice may switch from workspace A to B inside a system sharing **the same issuer**.

Two distinct cases:

| Architecture | Decision at Authentication layer | Decision at tenant authorization layer |
| --- | --- | --- |
| Single IdP, one user with multi-tenant memberships | Verify Alice's token/session | Which membership and permissions Alice holds in the chosen tenant |
| Multiple IdPs/issuers | Pick a **trusted** issuer/`AuthenticationManager` to verify the token | From the verified identity, map to tenant and data policies |
| Single tenant with multiple workspaces | Identity may stay the same | Workspace/project scope can be even narrower than the tenant |

**Warning:** never create a `JwtDecoder` or `AuthenticationManager` for **an arbitrary issuer declared by the request**. Spring Security docs require issuers to come from a **trusted** allowlist/registry. Reading the `iss` claim before signature verification is strictly for choosing a verification method within an allowed set—not proof that the subject may access a tenant.

## 5. How should the active tenant be selected?

No single mechanism fits every app. Four common approaches:

| Mechanism | How selected tenant is represented | Pros | Risks and requirements |
| --- | --- | --- | --- |
| **Tenant in URL** | `/api/tenants/{tenantId}/...` | Explicit per request; multiple tabs stay independent | Every endpoint must validate membership and resource tenant |
| **Tenant in header** | `X-Tenant-Id: tenant-b` | Avoids repeating ID in path | Client-modifiable header; needs middleware/server policy checks |
| **Active tenant in server session** | `session.activeTenant=tenant-b` | Natural "switch workspace" UX | Multiple tabs sharing one session conflict; stale session after revocation; CSRF |
| **Tenant in access token** | Claim `tenant_id=tenant-b` verified by issuer | Token carries explicit scope; stateless API | Must **reissue token** on switch; old token may remain valid until expiry without revocation/versioning |

**Design recommendation:** for multi-tab apps, high concurrency, or diverse API clients, using an **explicit per-request tenant selector** (such as the path) usually eliminates hidden state. For traditional session-based apps, storing active tenant in the session can still work if multi-tab behavior is defined and server-side membership is re-checked.

If two selector sources coexist—for instance path `tenant-a` and header `tenant-b`—**do not arbitrarily pick one**. Reject the mismatch, or designate one canonical source and reject/ignore the other explicitly. Using the header tenant in SQL while checking the URL tenant in policy can cause cross-tenant access.

### Never pick an arbitrary default tenant

A user has not selected a tenant and holds two memberships, A and B. Never silently pick the first tenant from an unordered collection, or fall back to `"public"`/`"default"` when context is missing. Sensible behavior:

- Return the list of tenants the caller **is permitted to see**.
- Require the user to choose, or select a "last used" tenant only after **re-verifying** membership.
- Missing tenant selector on a tenant-scoped endpoint → controlled error, never an unscoped query.
- Not a member of the requested tenant → deny; never grant via fallback.

## 6. Secure tenant-switching flow

Suppose Alice is in A and selects B in the UI.

```text
1. Browser: POST /api/me/active-tenant {"tenantId":"tenant-b"}
                       |
                       v
2. Authenticate Alice from verified cookie/session/JWT
                       |
                       v
3. Validate tenant-b is a selectable tenant
                       |
                       v
4. Verify current membership Alice -> tenant-b = ACTIVE
                       |
                       v
5. Return B's metadata/permissions/tenant context
   (or store activeTenant in session, or issue a new token
    depending on chosen architecture)
                       |
                       v
6. Browser resets A's data state, attaches tenant-b for new requests
                       |
                       v
7. EVERY subsequent request still authorizes actor + tenant-b + action + resource
```

Step 4 does more than verify tenant B exists. It must confirm **Alice belongs to B** and both membership and tenant remain active. If Alice's role in B is VIEWER, B's WRITE screens and APIs must be denied even though A granted EDITOR.

**Switching tenants is not re-logging in** if only changing the workspace selection under the same identity. However, if tenant B demands stricter MFA, step-up authentication, terms acceptance, or dedicated credentials, run that workflow before granting sensitive access. Never treat logging into A as proof that B's policies are satisfied.

### Response on successful switch

Return an explicit structure, for example:

```json
{
  "tenantId": "tenant-b",
  "displayName": "Workspace B",
  "membershipStatus": "ACTIVE",
  "permissions": ["document:read"],
  "membershipVersion": 12
}
```

This is an **illustrative response**, not a built-in Spring Security API. The frontend can use `permissions` to toggle UI controls, but the **server** still decides and must never trust a `permissions` field sent back by the frontend.

If access to tenant B is denied, return `403 Forbidden`, or `404 Not Found` if policy hides tenant existence. Return `401` for unauthenticated callers. Keep error contracts consistent per endpoint; avoid leaking customer tenant lists through detailed error messages.

## 7. Roles and authorities must be interpreted inside the **verified tenant**

Suppose Alice is EDITOR in A and VIEWER in B. The following check is dangerous if authorities are populated from all of Alice's memberships:

```java
@PreAuthorize("hasRole('EDITOR')")
public void editDocument(Long documentId) {
    // ...
}
```

If `ROLE_EDITOR` is added to `Authentication` because Alice is EDITOR in A, the check above **does not know** the document resides in B. It can allow cross-tenant edits.

Three common designs:

1. **Tenant-aware policy:** `tenantPolicy.can(authentication, tenantId, action)` looks up membership in the requested tenant.
2. **Controlled namespaced authorities:** express permissions with explicit tenant/permission segments; still verify resource tenant and avoid constructing role strings from unvalidated client input.
3. **Tenant-bound access tokens:** server/IdP issues a fresh token scoped strictly to the chosen tenant with appropriate `aud`/`iss`/expiry; APIs reject token B when accessing A's data.

For apps with dynamic memberships, request-time tenant-aware policies handle revocation far more promptly than immutable claims inside long-lived JWTs. Whichever approach you pick, **never widen a global role** into tenant admin everywhere just because a user is admin somewhere.

### Two-tier policy

```text
canAccess(subject, tenant, "document:read")
    AND
canReadResource(subject, tenant, documentId)
```

Tier one: membership/role inside the tenant. Tier two: permissions on the specific object (owner, project, ACL, share grant, classification, status). Being VIEWER in B does not guarantee reading every Document in B if project or document ACLs also apply.

## 8. Spring Boot example: per-request tenant verification

The following snippets are **components of a Java 17+ application using Spring Boot, Spring Security 6.x/7.x, and Spring Data JPA**. They are not a single standalone file compiled via `javac`; entities, schemas, migrations, authentication mapping, and application interfaces must be implemented in your project.

### 8.1. Model for the verified tenant scope

```java
public enum TenantAction {
    DOCUMENT_READ,
    DOCUMENT_CREATE,
    DOCUMENT_WRITE,
    MEMBER_MANAGE
}

public record VerifiedTenantScope(
    String subjectId,
    String tenantId,
    java.util.Set<TenantAction> actions
) {
    public boolean can(TenantAction action) {
        return actions != null && actions.contains(action);
    }
}
```

`VerifiedTenantScope` is constructed **exclusively on the server after verification**, never deserialized straight from a request body. `subjectId` should be a stable subject ID from the authenticated principal; display names or emails can change and are not always unique across issuers.

### 8.2. Membership repository

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TenantMembershipRepository
        extends JpaRepository<TenantMembership, Long> {

    Optional<TenantMembership>
        findByTenantIdAndSubjectIdAndActiveTrue(
            String tenantId, String subjectId);
}
```

This assumes entity `TenantMembership` has `tenantId`, `subjectId`, `active`, and a trusted set of permissions or roles. The database should enforce uniqueness/constraints on the tenant + subject pair (or include issuer identity with multiple IdPs) per domain rules. If roles live in a separate relationship or mapping, the repository must fetch permissions strictly **for that exact tenant**, never merging roles across all tenants.

### 8.3. Resolving subject from Authentication

Do not assume every `Authentication.getName()` is an internal subject ID. With default JWT Resource Server, `getName()` usually maps to `sub`; with SAML/OIDC/custom Authentication, mappings can differ. Define an explicit contract:

```java
import org.springframework.security.core.Authentication;

public interface SubjectIdResolver {
    String requireSubjectId(Authentication authentication);
}
```

Implementations must reject `null`, anonymous, unauthenticated principals, and identities from untrusted issuers; with multiple issuers, namespace as `issuer + subject` so two subjects from different issuers cannot collide on string equality. Never let the browser submit `subjectId` and treat it as the actor.

### 8.4. TenantAccessPolicy: selecting a tenant does not mean access is granted

```java
import java.util.EnumSet;
import java.util.Set;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service("tenantAccess")
public class TenantAccessPolicy {
    private final TenantMembershipRepository memberships;
    private final SubjectIdResolver subjects;

    public TenantAccessPolicy(
            TenantMembershipRepository memberships,
            SubjectIdResolver subjects) {
        this.memberships = memberships;
        this.subjects = subjects;
    }

    public VerifiedTenantScope requireScope(
            Authentication authentication, String requestedTenant) {

        String subject = subjects.requireSubjectId(authentication);
        if (requestedTenant == null || requestedTenant.isBlank()) {
            throw new AccessDeniedException("Tenant is required");
        }

        TenantMembership member = memberships
            .findByTenantIdAndSubjectIdAndActiveTrue(
                requestedTenant, subject)
            .orElseThrow(() -> new AccessDeniedException(
                "Tenant is not available"));

        // Example: entity exposes only the permissions of this membership.
        Set<TenantAction> actions =
            EnumSet.copyOf(member.getTenantActions());

        return new VerifiedTenantScope(
            subject, member.getTenantId(), Set.copyOf(actions));
    }

    public boolean can(
            Authentication authentication,
            String requestedTenant,
            TenantAction action) {
        try {
            return requireScope(
                authentication, requestedTenant).can(action);
        } catch (AccessDeniedException denied) {
            return false;
        }
    }
}
```

**Limitations and completion notes:**

- `TenantMembership` and `getTenantActions()` are application types/methods. Ensure action data comes from server storage, never JSON.
- `EnumSet.copyOf(...)` throws `IllegalArgumentException` on an empty collection when the enum type cannot be inferred. For completeness, use `EnumSet.noneOf(TenantAction.class)` followed by `addAll(...)`, or guarantee memberships always hold at least one action. See the safer version below.
- `requireScope` rejects invalid tenants. Never fall back to another tenant when the caller lacks membership.
- `can` converts only **authorization denial** into `false`. Never catch broad `Exception` and swallow database outages as "no tenant"; infrastructure errors must be classified and monitored.
- `SubjectIdResolver` must handle anonymous users and issuer namespacing properly; `Authentication.isAuthenticated()` alone is insufficient.

Version handling an empty permission set:

```java
EnumSet<TenantAction> allowed =
    EnumSet.noneOf(TenantAction.class);
allowed.addAll(member.getTenantActions());

return new VerifiedTenantScope(
    subject, member.getTenantId(), Set.copyOf(allowed));
```

When implementing for real, use this safe snippet to **replace** the `EnumSet.copyOf(...)` initialization line above. The first snippet intentionally highlights a common pitfall when a membership exists with zero actions.

### 8.5. Service querying data within tenant scope

```java
import java.util.List;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentReadService {
    private final TenantAccessPolicy tenants;
    private final DocumentRepository documents;

    public DocumentReadService(
            TenantAccessPolicy tenants,
            DocumentRepository documents) {
        this.tenants = tenants;
        this.documents = documents;
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional(readOnly = true)
    public List<DocumentView> list(
            Authentication authentication, String selectedTenant) {

        VerifiedTenantScope scope =
            tenants.requireScope(authentication, selectedTenant);

        if (!scope.can(TenantAction.DOCUMENT_READ)) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Document read is not permitted");
        }

        // Tenant taken from the verified scope, not from a static field.
        return documents
            .findByTenantIdAndDeletedFalse(scope.tenantId())
            .stream()
            .map(d -> new DocumentView(d.getId(), d.getTitle()))
            .toList();
    }

    public record DocumentView(Long id, String title) {}
}
```

This is an **application class** requiring `findByTenantIdAndDeletedFalse(...)`, a `Document` entity, and real JPA mappings. The service does two critical things: checks the action **inside the selected tenant** and queries with the tenant ID from `VerifiedTenantScope`.

For data requiring per-document ACLs, include per-object owner/ACL/share-grant conditions **before returning lists and before computing counts/pagination**. Being VIEWER in B does not allow reading every document in B if product rules enforce object-level permissions.

**Why check membership inside the service body?** Under standard AOP ordering, `@PreAuthorize` can run **before** transaction advice on the same method. When membership must stay consistent with the transaction/query, checking inside the service transaction is easier to control; note that `@Transactional(readOnly=true)` alone does not guarantee snapshot/serializable semantics or instant revocation under all isolation levels.

### 8.6. Controller using an explicit tenant path

```java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {
    private final DocumentReadService service;

    public DocumentController(DocumentReadService service) {
        this.service = service;
    }

    @GetMapping
    public List<DocumentReadService.DocumentView> list(
            @PathVariable String tenantId,
            Authentication authentication) {
        return service.list(authentication, tenantId);
    }
}
```

`tenantId` in the URL is only a **tenant selection proposal**. The service still calls `tenantAccess.requireScope(authentication, tenantId)`. Never switch to `findAll()` and filter by tenant in the controller; with pagination, counts, and lazy relationships, that wastes resources and risks leaking data.

### 8.7. Note on configuring @EnableMethodSecurity

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
```

When using `@PreAuthorize`, enable method security and invoke services through a **Spring-managed proxy**. Self-invoking `this.securedMethod()` inside the same bean in proxy mode can bypass advice; scoped queries at the repository/domain layer provide an additional defense. Never place core checks **only** in the controller if the service is also called from async tasks, jobs, or other beans.

## 9. Context switching in a stateful session

In apps using cookies + server-side `HttpSession`, the UI might call:

```http
POST /api/me/active-tenant
Content-Type: application/json
Cookie: JSESSIONID=<session>

{"tenantId":"tenant-b"}
```

Sample controller:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ActiveTenantController {
    private final TenantAccessPolicy tenantAccess;

    public ActiveTenantController(TenantAccessPolicy tenantAccess) {
        this.tenantAccess = tenantAccess;
    }

    public record SelectTenantRequest(String tenantId) {}

    @PostMapping("/api/me/active-tenant")
    public ResponseEntity<Void> select(
            @RequestBody SelectTenantRequest command,
            Authentication authentication,
            HttpServletRequest request) {

        if (command == null || command.tenantId() == null) {
            return ResponseEntity.badRequest().build();
        }

        VerifiedTenantScope verified =
            tenantAccess.requireScope(authentication, command.tenantId());

        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.status(401).build();
        }

        session.setAttribute("ACTIVE_TENANT_ID", verified.tenantId());
        return ResponseEntity.noContent().build();
    }
}
```

This is a **session-based fragment** requiring proper HTTP security and CSRF setup. **Never disable CSRF protection on a cookie-authenticated POST just because it only switches tenants**: an attacker can hijack workspace state via CSRF even without reading data directly. Evaluate `SameSite`/`Secure` cookies and Spring Security CSRF tokens against your actual authentication mechanism.

More importantly, on the next request:

```text
selectedTenant = session.getAttribute("ACTIVE_TENANT_ID")
verifiedScope = tenantAccess.requireScope(authentication, selectedTenant)
executeService(verifiedScope)
```

**Membership must be re-verified.** A session attribute is a *selection*, not a permanent authorization grant. If Alice is removed from B after switching, new requests must not keep accessing B simply because the session still holds B.

### Multiple tabs sharing the same session

If tab 1 is on A and tab 2 clicks switch to B, overwriting `session.activeTenant=B`, a subsequent request originating from tab 1 can run under B. That is a dangerous form of **hidden mutable context**.

Options:

- Prefer **tenantId in every API route** so tabs stay independent.
- If using a session-wide active tenant, display the active tenant clearly in the UI and synchronize across tabs; requests should send a context version/tenant ID to catch stale UI state.
- Store active workspace per tab via a dedicated token/tab context, always verified server-side; never trust localStorage or tab IDs as authorization.
- For write operations, require an explicit tenant scope and/or check `expectedTenant` so a user never updates B while believing they are editing A.

For tools handling sensitive business flows, the "switch tenant" UX itself must be designed carefully, not treated as merely swapping a dropdown.

## 10. Stateless APIs: switching tenants by per-request selection or issuing a new token

When the frontend calls a resource server with a bearer JWT and no server session, a `POST /switch-tenant` endpoint **cannot** automatically make subsequent requests target the new tenant without a mechanism to carry/switch context.

Two clear approaches:

### 10.1. Keep an identity token, send the tenant on each request

```http
GET /api/tenants/tenant-a/documents
Authorization: Bearer <alice-jwt>
```

After the UI switches to B:

```http
GET /api/tenants/tenant-b/documents
Authorization: Bearer <same-alice-jwt>
```

The resource server validates the JWT and **verifies Alice is a member of B on each request**. This fits when tokens prove baseline identity/authorities while dynamic memberships come from server storage.

### 10.2. Tenant-bound tokens

The authorization server can issue a new access token after verifying Alice may select B:

```json
{
  "sub": "u-101",
  "tenant_id": "tenant-b",
  "scope": "document:read",
  "exp": 1799999999
}
```

The JSON above illustrates claims only; real JWTs require issuer, audience, signature, and architecture-mandated validations. **Clients must never tamper with the `tenant_id` claim payload** and expect the token to pass. New tokens must be issued by a trusted authority, and the resource server must verify issuer, signature, `aud`, `exp`, `nbf`, and tenant scope.

If the old token for A has not expired yet, the system must decide:

- May token A continue working in another tab?
- Does switching tenants revoke token A?
- Must revoked memberships take effect immediately, or is lag until token expiration acceptable?
- Does the resource server check membership/permission version on every request?

In particular, **tenant claims and role lists inside a JWT can go stale** after memberships change. A cryptographically valid JWT does not guarantee business authorization remains valid.

### When do you need per-tenant audience/issuer?

If A and B have distinct authorization servers, Spring Security can use `JwtIssuerAuthenticationManagerResolver` with trusted issuers. If they are simply two workspaces inside one organization and one IdP, do not invent two fake issuers. **Token verification** and **active workspace selection** are separate concerns.

## 11. Tenant-specific AuthorizationManager and @PreAuthorize

Sometimes policies are richer than a quick `if` inside a service. You can centralize them in a policy bean:

```java
@PreAuthorize(
    "@tenantAccess.can(authentication, #tenantId, " +
    "T(com.example.security.TenantAction).DOCUMENT_READ)"
)
public List<DocumentView> list(
        @P("tenantId") String tenantId) {
    // Read data with tenant predicate in repository.
}
```

This is a **method fragment**, assuming `com.example.security.TenantAction` is a real package and `TenantAccessPolicy.can(...)` is implemented. Import `org.springframework.security.access.method.P` and enable `@EnableMethodSecurity`. Adjust the enum package path when copying into another project.

In architectures with many action groups, you can write a custom `AuthorizationManager<MethodInvocation>` or `AuthorizationManager<RequestAuthorizationContext>` to resolve tenant/permissions. However, generic abstractions do not make raw inputs trustworthy: `RequestAuthorizationContext.getVariables()` reads the tenant from route matchers and `MethodInvocation.getArguments()` reads it from the caller; both remain **selectors** for the policy to verify.

### Never construct authority names from unverified input

A risky pattern:

```java
String required = "TENANT_" + tenantId + "_ADMIN";
return authentication.getAuthorities().stream()
    .anyMatch(a -> a.getAuthority().equals(required));
```

If `tenantId` is unvalidated, or authorities are granted without a strict tenant/role verification contract, string concatenation easily mixes scopes. Even with valid namespaced authorities, you must still verify the target resource actually belongs to that tenant.

A policy bean backed by a membership database lets the app define actor, tenant, action, and resource cleanly without forcing controller code to depend on exact authority string formats.

## 12. Tenant isolation at the data query layer

**Returning the right tenant in the UI is not enough.** Repositories, ORMs, and databases must ensure reads and writes touch only data in the verified scope.

Example shared table with a `tenant_id` column:

```sql
SELECT id, title
FROM documents
WHERE tenant_id = :verified_tenant_id
  AND deleted = FALSE
ORDER BY id;
```

For detail lookup:

```sql
SELECT id, title, owner_id
FROM documents
WHERE id = :document_id
  AND tenant_id = :verified_tenant_id
  AND deleted = FALSE;
```

For update:

```sql
UPDATE documents
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :verified_tenant_id
  AND owner_id = :authenticated_subject_id
  AND deleted = FALSE;
```

These SQL statements use placeholders **bound via prepared statements**, never raw string concatenation of the tenant. Owner conditions here are **illustrative policies**; if documents support sharing/ACLs, adapt them while preserving tenant isolation. When an update affects 0 rows, grant nothing and avoid revealing whether the ID exists elsewhere.

**Note:** tenant predicates protect the tenant boundary, *not* intra-tenant object permissions. A VIEWER in B must not automatically read Bob's private documents in B.

### Filters and bulk/native queries

ORM filter mechanisms reduce boilerplate, yet you must audit bypass paths such as native SQL, bulk JPQL, JDBC templates, stored procedures, data exports, admin reports, search indexes, and newly added repositories. Never assume a standalone Hibernate filter protects every operation.

Count/pagination/search queries must also apply tenant predicates **before** pagination rather than loading all rows and filtering in Java. Aggregate statistics can leak another tenant's document counts even when detail endpoints are locked down.

## 13. Database Row-Level Security and tenant settings

In databases supporting **Row-Level Security (RLS)** such as PostgreSQL, you can add a defense-in-depth layer alongside Spring Security policies.

Illustrative DDL **for a shared table**:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy
ON documents
FOR ALL
TO app_tenant_role
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
```

This is illustrative PostgreSQL SQL. Also check table/schema grants, owner/BYPASSRLS/superuser rules, `FORCE ROW LEVEL SECURITY` where required, related tables, and real deployment tests. A role with `BYPASSRLS` or superuser privileges **must never be used** for ordinary tenant requests.

Inside a transaction, the app can set a **transaction-local** tenant context using the equivalent of:

```sql
SELECT set_config('app.tenant_id', :verified_tenant_id, true);
```

The `true` argument scopes the setting to the current transaction. `:verified_tenant_id` is a server-verified parameter bound safely—**not** a value copied from an unverified header. When the context is unset or null, predicates must fail closed and expose zero rows.

### Why avoid arbitrary session-wide SET?

In a connection pool:

```text
Request Alice / tenant-a
  -> connection #5: SET tenant = A
  -> return connection to pool

Request Bob / tenant-b
  -> receive connection #5
  -> forgot to reset tenant
  -> SQL may execute under A -> cross-tenant leak
```

Transaction-local settings like `set_config(..., true)` tied to transaction start—and always establishing scope per transaction—reduce context leaks across pooled connections. Still test connection reuse, transaction boundaries, read-only queries, nested operations, and actual DB roles.

**RLS does not replace Authentication:** if the app sets `app.tenant_id` from a user-supplied header without checking membership, RLS simply enforces **the wrong tenant chosen by the app**. The right order is Authenticate → Verify tenant → Set DB context → Query under a restricted role.

## 14. Hibernate multi-tenancy and limits when switching tenants

Hibernate supports multi-tenancy models suited to its version, such as database/schema separation or discriminator-based tenant isolation. `CurrentTenantIdentifierResolver<T>` provides:

```java
T resolveCurrentTenantIdentifier();
boolean validateExistingCurrentSessions();
```

Javadoc explains that Hibernate invokes the resolver to determine the tenant for current/new sessions per configured strategy. `validateExistingCurrentSessions()` can ask Hibernate to verify that an already-bound session's tenant matches the resolver; **it does not silently switch the tenant on an existing session**.

A common pitfall:

```text
Open EntityManager/Session for tenant-a
          |
          v
Switch thread tenant context to tenant-b
          |
          v
Reuse still-open EntityManager/Session
          |
          v
Do NOT assume the session switched to tenant-b
```

With Hibernate, a session / first-level persistence context has a lifecycle tied to the tenant when opened or bound. When a user switches active tenant, a **new** request/transaction/session must use the new scope; never hold managed entities from A and switch context to B inside the same persistence context.

### Never use a static mutable currentTenant

```java
public static String activeTenant = "tenant-a"; // UNSAFE
```

A singleton/static field allows one request's tenant to overwrite another's. If using a request-scoped context or ThreadLocal, ensure it is populated **only after verification** and cleared in `try/finally` when the request finishes; prevent leaks across thread pools, async calls, or secondary request dispatches.

**Important:** `SecurityContextHolder` defaults to thread-local storage in many Servlet apps; it is not a tenant selector itself. A request-level `VerifiedTenantScope` should be an **explicit immutable object** passed into services rather than relying solely on global state.

## 15. ThreadLocal, @Async, queues, and microservices

An app may verify the tenant properly in the controller yet lose context when:

- Running `@Async` or `CompletableFuture`.
- Publishing messages to Kafka/RabbitMQ.
- Creating scheduled jobs, retries, or sagas.
- Calling other services via HTTP/gRPC.
- Using Reactor/WebFlux (where context propagation differs from traditional thread-locals).

Spring Security's concurrency docs provide `DelegatingSecurityContextExecutor` and related wrappers to propagate `SecurityContext` across threads. However, **propagating SecurityContext does not automatically propagate a custom business tenant scope** stored in a separate ThreadLocal. Both need safe handling.

### Solutions for background tasks

An internal command might contain:

```json
{
  "tenantId": "tenant-b",
  "documentId": 42,
  "requestedAction": "GENERATE_REPORT",
  "requestedBy": "u-101",
  "correlationId": "req-123"
}
```

This is an illustrative message. The consumer **must not treat `tenantId` in the message as proof of authorization** if the message source is untrusted. Authenticate/authorize the producer or broker path, and model service identity, tenant scope, and allowed actions.

For delayed jobs, `requestedBy`'s membership may have been revoked. If policy requires permissions to **remain current** at execution time, re-check them; if the job represents a pre-approved committed command, define a dedicated, audited, strictly scoped authorization contract. No single answer fits all workflows.

### Retries, idempotency, and dead-letter queues

- Idempotency keys should be tenant-scoped (e.g., `tenant + operation + key`) to prevent collisions and cross-tenant result mixing.
- Dead-letter queues may contain tenant data/IDs; only appropriately scoped services/admins should inspect them.
- Metrics and tracing may record verified tenant IDs, but never embed tokens/secrets or sensitive personal data.
- Quotas/rate limits need both per-tenant and global limits to mitigate *noisy neighbors*.

If a background service is allowed to process multiple tenants, grant that privilege **explicitly to the service principal**, never by setting tenant context to null and skipping filters.

## 16. Caches, HTTP responses, storage, and search must separate tenants

A user with access to both A and B must never receive A's data while querying B simply because a document ID or query string matches.

### Cache keys

Wrong:

```text
document:42
document-list:page=1
policy:alice:READ
```

Better for tenant-scoped data:

```text
document:tenant-b:42
document-list:tenant-b:alice:page=1:filters-hash
policy:tenant-b:alice:42:READ:membership-version
```

These keys are illustrative; exposing raw tenant ID strings is optional when using a safe namespace/key builder. Keys may also need permissions, resource status, locale, or versions depending on the data. **A proper key still does not replace authorization:** authorize before reading protected cache entries, and invalidate when memberships/roles/ACLs change.

### HTTP and frontend caching

When the UI switches from A to B:

- Cancel or tag in-flight requests for A; never let a late response from A render inside B's view.
- Reset tenant-specific stores, query caches, selected rows, search filters, upload queues, and websocket subscriptions.
- Frontend query keys need the tenant, e.g., `["documents", tenantId, page]`.
- Never treat `activeTenant` in localStorage as a source of authority; it is purely a preference/selection.
- Sensitive tenant-scoped responses must never sit in a shared CDN cache keyed without tenant/user scope.
- When tab A and tab B are open together, avoid a session-global active tenant that causes APIs to read a hidden tenant.

### Object storage

A path such as `tenant-a/files/invoice.pdf` is not an authorization credential. Before serving files or issuing presigned URLs, the server must verify **exact object + tenant + action**. If a signed URL stays valid after a user switches or loses membership, understand the revocation limits of pre-issued URLs.

### Search, analytics, and exports

Elasticsearch, data warehouses, read replicas, reports, CSV exports, and async indexers need the exact same tenant boundary. An export generated under A must never be downloadable in context B simply because a link ID collides or jobs write to shared storage. Tenant isolation belongs in both the **data plane** and **control plane**.

## 17. Tenant switching while requests are in flight

Suppose tab 1 starts updating a document in A while tab 2 switches tenant to B:

```text
T1: request UPDATE /tenants/A/documents/10 starts
T2: user selects tenant B
T1: transaction is still in flight
T2: request GET /tenants/B/documents starts
```

If active tenant is bound and verified per request, T1 continues in A's scope and T2 in B's; both requests can validly execute concurrently as long as the user holds membership in both.

If active tenant is a shared session variable and T1 reads the session **multiple times during execution**, part of T1 can unexpectedly execute under B. Therefore:

1. Resolve the tenant once at the request boundary.
2. Verify membership/action.
3. Construct an immutable `VerifiedTenantScope` for the request/transaction.
4. Use that scope throughout business logic and database calls.
5. Never mutate scope mid-transaction.
6. If older requests must be blocked after switching, design a `contextVersion`/epoch and reject explicitly rather than mutating context silently.

**There is no universal rule that switching must cancel all older requests.** With multiple tabs, concurrent requests to A and B can be entirely valid. What must be prevented is **a single request silently changing tenants mid-flight** or exceeding current membership rights.

### Old tokens after membership removal

If Alice's membership in B is revoked, a live token carrying claim B can still pass cryptographic validation. Policy may require:

- Checking membership on every request; or
- Short-lived token B + revocation/versioning; or
- Live introspection/authorization service checks; or
- Rejecting tokens below a new policy epoch.

Do not merely remove B from a frontend dropdown; the API must reject B as soon as the revocation SLA demands.

## 18. Standalone Java 17: one user with different permissions across two tenants

The program below **does not use Spring Security**. It models the flow **request selects tenant → verify membership → check action → verify resource tenant → execute**, and demonstrates how two tabs can send requests for two different tenants without any global `activeTenant` variable.

Save as `MultiTenantSwitchDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class MultiTenantSwitchDemo {
    record Membership(
        String subject, String tenant, Set<String> actions, boolean active
    ) {}

    record Document(
        long id, String tenant, String title
    ) {}

    private static final Map<String, Membership> MEMBERS = Map.of(
        "alice|tenant-a",
            new Membership("alice", "tenant-a",
                Set.of("READ", "WRITE"), true),
        "alice|tenant-b",
            new Membership("alice", "tenant-b",
                Set.of("READ"), true),
        "alice|tenant-c",
            new Membership("alice", "tenant-c",
                Set.of("READ"), false),
        "bob|tenant-b",
            new Membership("bob", "tenant-b",
                Set.of("READ", "WRITE"), true)
    );

    private static final Map<Long, Document> DOCUMENTS = new HashMap<>(
        Map.of(
            10L, new Document(10L, "tenant-a", "A-plan"),
            20L, new Document(20L, "tenant-b", "B-budget")
        )
    );

    static Membership verify(String subject, String selectedTenant) {
        if (subject == null || selectedTenant == null) {
            return null;
        }
        Membership membership =
            MEMBERS.get(subject + "|" + selectedTenant);
        return membership != null && membership.active()
            ? membership : null;
    }

    static String read(String subject, String selectedTenant, long id) {
        Membership context = verify(subject, selectedTenant);
        if (context == null) {
            return "403 Tenant forbidden";
        }
        if (!context.actions().contains("READ")) {
            return "403 Action forbidden";
        }
        Document document = DOCUMENTS.get(id);
        if (document == null
                || !document.tenant().equals(context.tenant())) {
            return "404 Not Found";
        }
        return "200 " + document.title();
    }

    static String updateTitle(
            String subject, String selectedTenant,
            long id, String newTitle) {
        Membership context = verify(subject, selectedTenant);
        if (context == null) {
            return "403 Tenant forbidden";
        }
        if (!context.actions().contains("WRITE")) {
            return "403 Action forbidden";
        }
        Document document = DOCUMENTS.get(id);
        if (document == null
                || !document.tenant().equals(context.tenant())) {
            return "404 Not Found";
        }
        DOCUMENTS.put(
            id, new Document(id, document.tenant(), newTitle)
        );
        return "204 Updated";
    }

    public static void main(String[] args) {
        System.out.println("Alice A read 10: "
            + read("alice", "tenant-a", 10));
        System.out.println("Alice A read B20: "
            + read("alice", "tenant-a", 20));
        System.out.println("Alice B read 20: "
            + read("alice", "tenant-b", 20));
        System.out.println("Alice B write 20: "
            + updateTitle("alice", "tenant-b", 20, "Bad change"));
        System.out.println("Alice B read A10: "
            + read("alice", "tenant-b", 10));
        System.out.println("Alice C inactive: "
            + read("alice", "tenant-c", 20));
        System.out.println("Bob B write 20: "
            + updateTitle("bob", "tenant-b", 20, "B-updated"));
        System.out.println("Alice B sees updated: "
            + read("alice", "tenant-b", 20));
        System.out.println("Alice A still reads 10: "
            + read("alice", "tenant-a", 10));
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac MultiTenantSwitchDemo.java
java MultiTenantSwitchDemo
```

Exact stdout:

```text
Alice A read 10: 200 A-plan
Alice A read B20: 404 Not Found
Alice B read 20: 200 B-budget
Alice B write 20: 403 Action forbidden
Alice B read A10: 404 Not Found
Alice C inactive: 403 Tenant forbidden
Bob B write 20: 204 Updated
Alice B sees updated: 200 B-updated
Alice A still reads 10: 200 A-plan
```

Analysis:

- Alice has READ+WRITE in A but only READ in B; A's permissions **do not** carry over to B.
- When Alice selects A, B's Document 20 is invisible; when selecting B, A's Document 10 is invisible.
- Alice cannot write in B despite having WRITE in A.
- Tenant C has an inactive membership, so it is rejected at the select/verify step.
- Bob has WRITE in B and updates Document 20; Alice in B sees the updated content thanks to READ.
- A final request using A still reads Document 10: **there is no mutable global active tenant**.

**Simulation limitations:** `Map`/`HashMap` provides no transactions, concurrency safety, tenant-aware DB roles, or JWTs. The demo also omits fine-grained intra-tenant ACLs. Production code must obtain subjects from `Authentication`, memberships from a trusted store, and enforce tenant scope on queries/writes inside transactions.

## 19. Testing authorization across tenant switches

### 19.1. Minimal fixture

Prepare asymmetric test fixtures:

- Alice holds EDITOR in A and VIEWER in B.
- Bob holds ADMIN in B, no membership in A.
- Carol holds a disabled membership in C.
- Document 10 belongs to A, Document 20 belongs to B, Document 30 is private to another user in A.
- If using composite keys, seed a Document with identical external ID values in both A and B so cross-tenant queries are caught.
- Two concurrent requests, and one session open across multiple tabs.
- A cache entry previously populated under B's admin.
- A membership just revoked in the DB while the JWT/session has not yet expired.

### 19.2. Authorization matrix

| Actor | Selected tenant | Action/resource | Expectation |
| --- | --- | --- | --- |
| Alice | A | READ Document 10 in A | Allowed if object policy passes |
| Alice | A | WRITE Document 10 in A | Allowed if owner/ACL also passes |
| Alice | B | READ Document 20 in B | Allowed if object policy passes |
| Alice | B | WRITE Document 20 in B | **Deny**, even though Alice is EDITOR in A |
| Alice | C | Any | **Deny**, C has no active membership |
| Bob | A | Any | **Deny**, Bob does not belong to A |
| Bob | B | Manage B's members | Allowed only if B's role grants MEMBER_MANAGE |
| Alice | A | READ B's Document 20 | **Deny** and return zero data from B |
| Alice | B | READ A's Document 10 | **Deny** and return zero data from A |
| Alice | A | READ another user's private doc in A | Governed by object ACL, not membership alone |
| Unauthenticated | B | Any | 401/challenge per configuration |
| System service | Cross-tenant export | Only with explicit service scope and approval |

### 19.3. Context-switching and consistency matrix

| Scenario | What to verify |
| --- | --- |
| User selects a non-member tenant | Server rejects, no fallback |
| User switches A → B → A | Permissions, data, and UI restore cleanly per tenant |
| Two tabs select A and B concurrently | No mixing with explicit routes; if session-wide, behavior is well-defined |
| B membership revoked after switch | New requests to B are rejected within SLA |
| Session still holds B after revocation | Session does not grant authorization on its own |
| JWT claim B still unexpired after revocation | Authorization follows published revocation policy |
| Tenant suspended/archived | Denied based on tenant status even if membership is active |
| Token from unknown issuer | Never create an AuthenticationManager for arbitrary issuers |
| ADMIN role in A, VIEWER in B | A's ADMIN cannot be used inside B |
| Switch while an UPDATE request in A is running | Request never changes tenant mid-transaction |
| Async job retried after revocation | Re-check or apply explicit pre-approved job policy |
| Warm cache from tenant A | Never returns A when caller is in B |
| Connection pool reused between A/B | RLS/DB context never leaks tenant |
| EntityManager open for A | Never rebound to B inside the same persistence context |
| Native SQL/bulk operations | Enforce tenant predicates/RLS, no bypass |
| Search/export/count/pagination | Fetches and counts only permitted tenant data |
| CSRF against session switch endpoint | Forged requests cannot switch tenant |
| Missing tenant selector | Rejected, never falls back to an untrusted default tenant |

### 19.4. Real Spring Security tests

Use `@SpringBootTest`, `MockMvc` or HTTP integration tests, `spring-security-test`, a test database containing A/B, and production-like `Authentication` contexts.

Verify thoroughly:

1. HTTP filter chain enforces authentication properly.
2. `TenantAccessPolicy` is invoked with the **request-selected tenant ID** and verified subject ID.
3. Repository queries use **VerifiedTenantScope.tenantId**, never raw headers.
4. Response bodies contain zero data/metadata from other tenants.
5. On writes, assert the database/events remain unchanged when tenant or action is denied.
6. On paginated queries, assert counts and pages are properly scoped.
7. For users with multiple memberships, assert exact per-tenant permissions.
8. When revoking membership between requests, assert authorization does not stay stale beyond SLA.
9. For session switching, test CSRF, cookies, multiple tabs, and concurrent requests.
10. For async tasks, test that consumers/workers receive the right tenant and verify producer authorization.

**Testing trap:** `@WithMockUser(username="alice")` may not reproduce subject mapping from JWT `sub` or real issuer namespacing. If production uses JWT/OIDC/membership lookups, construct matching `Authentication` fixtures or test against a real resource server to avoid false assumptions.

### 19.5. DB RLS and connection reuse tests

When using PostgreSQL RLS:

- Run tests under a **production-like DB role** without `BYPASSRLS`.
- Assert cross-tenant SELECT/UPDATE/DELETE statements are blocked.
- Assert INSERT rows with a `tenant_id` differing from context are blocked by `WITH CHECK`.
- Every transaction must set the exact verified tenant ID.
- Use a real connection pool to test consecutive A/B requests over **the same physical connection**.
- Test beyond standard repository methods: cover JDBC templates, native SQL, bulk operations, and non-ORM query flows.
- Inventory all tenant-owned tables to ensure proper RLS policies; new tables are not secure automatically.
- If platform admins require cross-tenant access, use a separate authorized/audited path rather than making bypass credentials the default.

## 20. Common mistakes and fixes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Treating `tenantId` from header/path as authorization | Clients can alter selectors | Verify subject membership and tenant status on the server |
| Storing tenant in a static field | Other requests overwrite scope | Use an immutable per-request verified context |
| Uncleaned ThreadLocal tenant | Thread pool serves next request with stale context | `try/finally` clear, test reuse; prefer explicit scope passing |
| Holding ROLE_ADMIN in A and using it globally | Privilege escalation into B | Tenant-scoped permissions per membership |
| Switch changes only the UI dropdown | Server may still process old tenant | Send explicit tenant per request and verify |
| Treating session active tenant as a permanent grant | Membership can be revoked | Re-validate membership, policy versions/cache invalidation |
| Assuming JWT tenant claims never go stale | Token outlives revocation | Short TTLs, versions/introspection, or DB authorization |
| Dynamically creating decoders for any issuer | Client controls trust boundary | Trusted issuer allowlist/registry |
| `findById` query without tenant | IDOR/cross-tenant leakage | Tenant-scoped queries and DB enforcement |
| Checking tenant while skipping object owner/ACL | Same-tenant user reads private docs | Check resource permissions too |
| Reusing Hibernate Session A after switching to B | Persistence context stays bound to old tenant | New request/session/transaction for the right tenant |
| Session-local DB SET on pooled connections | Tenant A can leak to B | Transaction-local settings, resets, and reuse tests |
| Running normal requests with `BYPASSRLS` DB role | RLS provides zero protection | Least-privilege non-bypass role |
| Cache keys missing tenant | A's data returned in B | Key by tenant and permissions; authorize before cache hits |
| Frontend displays stale response after tab switch | UI renders previous tenant's docs | Reset query cache, cancel/tag in-flight requests |
| Async trusts unverified tenant field in message | Worker tricked into processing another tenant | Authenticate producer path and re-authorize in consumer |
| Global idempotency keys across all tenants | Colliding commands/responses across tenants | Key/namespace by tenant and operation |
| Not testing native SQL or exports | Isolation bypass path | Test every data access path |
| Falling back to a default tenant when context is missing | Unscoped queries or data leaks | Fail closed, require a valid selector |
| Logging raw tokens/claims or tenant data | Exposes sensitive data | Audit verified subject/tenant, redact secrets |
| Testing only single-tenant users | Misses role bleed and switch bugs | Asymmetric A/B fixtures and multi-tab tests |

## 21. Design review checklist for workspace switching

Before shipping multi-tenant switching to production, answer clearly:

1. **How is the subject identified?** Stable identity, issuer-namespaced when needed.
2. **Where do the tenant registry and memberships live?** Trusted source, unique constraints, active/suspended states.
3. **Where is the tenant selected?** URL, header, server session, or token; only one canonical source.
4. **What happens when the tenant selector is missing?** Never fall back to the wrong tenant.
5. **Which tenant are permissions bound to?** Never use global roles for tenant-scoped actions.
6. **How are resources protected?** Same-tenant owner/ACL, exact action, not membership alone.
7. **Does switching tenants require step-up authentication?** Based on target tenant sensitivity.
8. **Is membership verified on every request?** Or backed by a revocation strategy meeting SLA.
9. **Is multi-tab switching unambiguous?** Avoid mutable session state causing confusion.
10. **Do transactions and EntityManagers preserve tenant scope?** Never mutate mid-flight.
11. **Does the DB enforce a real tenant boundary?** Query predicates, schema/database isolation, or RLS.
12. **Can the connection pool leak context?** Test reuse and transaction-local settings.
13. **Are caches partitioned by tenant?** Data, authorization, session, frontend, and CDN caches.
14. **Do async and queues carry valid security context?** Service principals, producer auth, consumer re-checks.
15. **Do tokens/JWTs enforce proper issuer/audience/expiry?** Never confuse multi-issuer auth with workspace membership.
16. **Does offboarding/revocation propagate everywhere?** Tokens, sessions, caches, jobs, exports, storage.
17. **Are cross-tenant admins separately controlled?** Least privilege, auditing, approvals.
18. **Are KPIs/noisy neighbors bounded per tenant?** Rate limits, quotas, queues, connection pools.
19. **Do tests cover tenants A/B with asymmetric roles?** Negative tests and concurrency.
20. **Is auditing traceable end-to-end?** Actor, verified tenant, action, resource, outcome, and correlation ID.

**Conclusion:** A user belonging to multiple tenants does not mean **one global set of permissions**. Keep the authenticated principal, per-tenant memberships, and request tenant selector **separate**; create `VerifiedTenantScope` only after verification, enforce per-tenant permissions in services, and bind **every data query and write** to that scope. Switching workspaces must change **the selected working context**—never altering identity, elevating privileges from another tenant, or letting data/caches/transactions cross tenant boundaries.

## References

- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): multiple issuers, `AuthenticationManagerResolver`, trusted issuers, and propagation.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and bean authorization.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html): `SecurityContextHolder` and `DelegatingSecurityContextExecutor`.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signatures, issuers, expiry, principal mapping.
- [Hibernate ORM — CurrentTenantIdentifierResolver](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/context/spi/CurrentTenantIdentifierResolver.html): resolving session tenant and `validateExistingCurrentSessions()`.
- [Hibernate ORM — User Guide: Multi-tenancy](https://docs.hibernate.org/orm/8.0/userguide/html_single/): tenant identifiers, session lifetime, and Hibernate isolation.
- [OWASP — Multi Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): server-side tenant verification, data/cache/queue/storage isolation, and connection reuse testing.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, and object-level authorization.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): resource ID permission checks and scoped lookups.
