# Coordinating Multi-Layer Defense Without Gaps or Policy Conflicts

## 1. The problem: being allowed at one layer may still be insufficient permission

In a Spring Security system, permission checks at HTTP, service methods, and resources do not answer the same question. A logged-in user may hold `document:read` yet not be allowed to view documents belonging to another tenant; a controller may guard its URL properly while a background job calls the same repository without passing through HTTP filters; an already-approved method invocation may become invalid if the document changes state before the write commits.

**Multi-layer defense** means designing checkpoints so every path reaching a sensitive action satisfies the overall policy. Checkpoints can verify different conditions that jointly contribute to the final decision, without necessarily duplicating every permission statement.

A simple flow:

```text
HTTP Request
  |
  v
Authentication: who is calling?
  |
  v
FilterChainProxy selects the first matching SecurityFilterChain
  |
  v
HTTP Authorization: allowed to invoke action on this route?
  |      No -> DENY
  v
Method Security: permitted to run this business operation?
  |      No -> DENY
  v
Object Policy: permitted for this resource, in this context?
  |      No -> DENY
  v
Repository / transaction: queried in right tenant, written in right state?
  |      No -> DENY/ERROR
  v
EXECUTE + AUDIT

Non-HTTP paths (job, consumer, internal call)
  -> Start from a service/object boundary with the same policy
```

The diagram above is **conceptual**: depending on design, owner/tenant checks may live right inside queries; a service may be called from multiple entry points; and transactions may wrap business checks. The invariant is that no access path may bypass a mandatory condition.

### Three failure modes to distinguish

- **Missing a layer:** a new URL matches no `SecurityFilterChain`, an export endpoint skips tenant checks, or a job writes straight to the database.
- **Conflicting policy intent:** the controller allows "managers to edit any document", while the service allows "only owners to edit DRAFT"; two places claim to define edit rights without a unified rule.
- **Policy-consistent additional denial:** HTTP allows because the user has `document:update`, yet the service denies because the document is already APPROVED. This is the right outcome when **both permission and state** are mandatory.

Lesson goal: learn to choose and coordinate defense layers, avoid matcher and filter-chain ordering bugs, express conditions with proper AND/OR logic, guard non-HTTP paths, verify via unit/integration tests, and handle data changes/contention.

## 2. Responsibility table for each boundary

| Boundary | What should be checked | Tools/components | What never to assume |
| --- | --- | --- | --- |
| Identity | Authenticated identity, account status | `Authentication`, `SecurityContext`, authentication filters | Client-sent `userId`/`role` is authentic |
| Filter chain selection | Which chain owns the request? | `FilterChainProxy`, `SecurityFilterChain`, `@Order`, `securityMatcher` | All chains run sequentially |
| HTTP authorization | Route, HTTP method, functional permission | `authorizeHttpRequests`, `requestMatchers`, `AuthorizationFilter` | Matching URL means permission for every ID |
| Method authorization | Allowed to invoke the business operation? | `@EnableMethodSecurity`, `@PreAuthorize` | Annotations protect every call within the same instance |
| Object policy | Permitted on the specific object? | Policy service, owner/tenant/state/sharing | Having a role suffices to read all data |
| Repository | Is the query properly scoped? | SQL/JPA predicates, row-level security if properly implemented | UI filtering is safe enough |
| Transaction/data invariants | Are permissions and state still valid at write time? | Version, lock, constraints, conditional update | Pre-checks alone prevent every race |
| Non-HTTP | Under what identity does the job/consumer/RPC run? | Service entrypoint, machine identity, policy | "Internal" is automatically trustworthy |
| Audit/operations | Why allowed/denied, when did permissions change? | Event logs, traces, permission reviews | Logging replaces pre-operation checks |

An upper layer can reject clearly invalid requests early, reducing load on lower layers. However, **permissions on actual resources must be enforced where sufficient facts exist to decide**. Especially for capabilities shared across channels, the service or data layer is a boundary requiring careful definition.

## 3. Write the unified policy before attaching annotations

Suppose a multi-tenant document management app has fields: `id`, `tenantId`, `ownerId`, `status`, and `version`. Server-side identity includes `userId`, verified tenant, and active authorities.

Define an illustrative policy:

| Action | Permission | Data condition | State condition |
| --- | --- | --- | --- |
| Read document | `document:read` | Same tenant and is owner or validly shared | Per read rules |
| Update document | `document:update` | Same tenant and is owner | `DRAFT` |
| Approve document | `document:approve` | Same tenant, approver differs from creator | `PENDING` |
| Delete document | `document:delete` | Same tenant and granted object delete rights | Per deletion workflow |

This is an **example model**, not a default Spring Security policy. Sharing, approval, and deletion branches must be fully defined if the application implements them.

### 3.1. Expressing with explicit conditions

```text
canRead =
  authenticated
  AND hasAuthority(document:read)
  AND sameTenant
  AND (isOwner OR validReadShare)

canUpdate =
  authenticated
  AND hasAuthority(document:update)
  AND sameTenant
  AND isOwner
  AND (status == DRAFT)
```

Here, `AND` means **all mandatory conditions are met**, whereas `OR` only allows **business-approved alternative branches**. If parentheses are misplaced into:

```text
(hasAuthority(document:read) AND sameTenant AND isOwner)
OR validReadShare
```

then someone with a share grant could bypass the permission and tenant checks, unless that was genuinely intended. Write the complete policy out as sentences, tables, and tests to avoid confusion when translating into Java/SpEL expressions.

### 3.2. Default deny and exceptions

Logged-in users lacking a specific permission must be denied. A new operation without a rule must never be allowed automatically. Unknown state, undetermined owner, or untrusted policy-service results must never turn into "allowed".

This does not mean every network error returns HTTP 403; dependency failures may require 5xx or bounded retries. **Sensitive actions must not proceed when permissions cannot be verified**, regardless of which HTTP code represents the error.

### 3.3. What is a real conflict?

Two forms must be resolved:

1. **Different general permissions used with mismatched meaning:** HTTP requires `ROLE_EDITOR` while the service requires `document:update`, without an accurate role-to-permission mapping. Outcomes can diverge due to configuration/privilege drift.
2. **Two places expressing different object rules:** the controller enforces "same tenant", while another service lets "any manager read any tenant" without a unified exception model.

The fix is placing functional permissions in one catalog, documenting `role → authorities` mappings, and centralizing object policies in a reusable component; then testing every path. Never resolve a conflict by deleting a denying layer before knowing what condition it guards.

## 4. HTTP layer: pick the right SecurityFilterChain before checking requestMatchers

### 4.1. `securityMatcher` vs. `requestMatchers`

In Spring Security Servlet apps, `FilterChainProxy` selects the **first `SecurityFilterChain` matching the request** by priority order. **Only the selected chain executes**; other chains do not automatically apply as extra conditions.

- `http.securityMatcher("/api/**")` defines **the applicability scope of the entire chain**.
- `http.authorizeHttpRequests(auth -> auth.requestMatchers(...))` defines **access rules inside the chain**.
- `anyRequest().denyAll()` only handles requests **that entered that chain** without matching an earlier rule; it does not protect URLs outside the chain.

A very common mistake: having a single chain with `securityMatcher("/api/**")`, then assuming `anyRequest().denyAll()` also blocks `/admin/export`. If no chain matches `/admin/export`, that request may not be protected by Spring Security at all.

### 4.2. Configuring two chains with a fallback

The following is **Spring Boot Servlet integration code**, matching Spring Security 6 configuration style and not a standalone Java program. Real applications must configure an appropriate authentication mechanism (session, OAuth2 Resource Server, etc.).

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class AuthorizationConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                    .hasAuthority("document:update")
                .anyRequest().denyAll()
            );
        return http.build();
    }

    @Bean
    SecurityFilterChain fallbackSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping")
                .permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Point-by-point reading:

1. The API chain is evaluated first due to `@Order(1)` and applies only to `/api/**`.
2. Inside the API chain, `GET /api/documents/101` requires `document:read`, while `PATCH /api/documents/101` requires `document:update`. Other API paths/methods are denied.
3. The fallback declares no `securityMatcher`, so its scope matches remaining requests. Only the approved GET route is public; everything else is denied.
4. The two `anyRequest()` rules have **different scopes**. They do not run sequentially for the same request.
5. `@EnableMethodSecurity` enables method security for eligible methods/beans; it does not automatically attach permissions to every method.
6. The sample does not configure authentication, CSRF, or CORS. Configure them per your architecture; in particular, never disable CSRF casually when using cookies/sessions.

**Remember:** if a higher-priority chain matches `/**`, a lower-priority API chain may never be selected. A later chain "requiring admin rights" cannot fix an overly broad earlier chain that already allowed the request. Test chain ordering with concrete requests.

### 4.3. Matcher ordering within the same chain

`authorizeHttpRequests` rules are generally evaluated in declaration order to pick the first matching rule. Place narrow and sensitive rules ahead of broad rules.

```text
Dangerous:
  /api/**            -> authenticated
  /api/admin/**      -> hasRole("ADMIN")  (may never be selected)

Strict:
  /api/admin/**      -> hasRole("ADMIN")
  /api/documents/**  -> permissions per HTTP method
  anyRequest         -> denyAll
```

Do not assume the admin rule will be checked "one more time" after a broad matcher already allowed it. Likewise, never assume `authenticated()` suffices for a business action meant only for a specific permission.

### 4.4. Commonly missed HTTP surface points

Consider all `GET/POST/PATCH/PUT/DELETE` methods, path variants, static assets, file download endpoints, actuator, login/logout, CORS preflight, gateway rewrites, and error paths. Never widen `permitAll()` unconditionally across all endpoints simply because the system has some public endpoints.

With multiple chains, each chain can have different filters and authentication mechanisms. Effects of `csrf()`, authentication filters, security headers, and exception handlers must be verified on **the chain actually selected**.

## 5. Service layer: uphold policy across every business call path

HTTP is the first boundary, yet a service can be called by a second controller, a background job, batch import, or an event handler. Any service handling sensitive data needs clear checkpoints.

### 5.1. Method security in Spring

Method security must be enabled with `@EnableMethodSecurity`. With standard Spring AOP proxies, a public method called through a Spring bean/proxy can be protected:

```java
@PreAuthorize("hasAuthority('document:update')")
public void updateDraft(long documentId, UpdateDocumentCommand command) {
    // Business logic and object-level permissions.
}
```

However, this annotation only checks **functional permission**. It does not know which tenant `documentId` belongs to, who owns it, whether it is already approved, or whether the request is locked.

When combining method-security annotations, each checker can execute sequentially and all applicable conditions must pass. Do not repeat the same `@PreAuthorize` twice on one method; for complex conditions, write one clear expression or delegate to a policy bean.

### 5.2. Service protecting a concrete resource

The following is an **integration example**, requiring project-defined domain/repository classes, not a complete standalone program.

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final DocumentRepository repository;
    private final CurrentActor currentActor;

    public DocumentService(
            DocumentRepository repository, CurrentActor currentActor) {
        this.repository = repository;
        this.currentActor = currentActor;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(long documentId) {
        var actor = currentActor.requireAuthenticated();

        var document = repository.findByIdAndTenantIdAndOwnerId(
            documentId, actor.tenantId(), actor.userId()
        ).orElseThrow(() -> new DocumentNotFoundException(documentId));

        return DocumentView.from(document);
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:update')")
    public void updateDraft(
            long documentId, UpdateDocumentCommand command) {

        var actor = currentActor.requireAuthenticated();

        var document = repository.findByIdAndTenantIdAndOwnerId(
            documentId, actor.tenantId(), actor.userId()
        ).orElseThrow(() -> new DocumentNotFoundException(documentId));

        if (!document.isDraft()) {
            throw new AccessDeniedException("Update denied");
        }

        document.applyAllowedChanges(command);
        // Must also design stale-version write protection.
    }
}
```

Permissions are enforced across layers:

- **HTTP**: requester must have `document:read` or `document:update` to reach the corresponding endpoint.
- **Method**: the same functional permission is checked when the service is called from another entry point, provided the call goes through the method-security mechanism.
- **Data**: queries fetch only documents matching ID, tenant, and owner. In a sharing model, query policies must include valid share grants.
- **Workflow**: only DRAFT documents may be edited.
- **Transaction**: data must remain valid at write time, handling concurrent updates.

Note that the code above is not a complete solution for optimistic locking, limits, auditing, or sharing rights. Its goal is to show each condition placed where trusted data resides.

### 5.3. Avoid self-invocation and non-proxied calls

Spring AOP proxies can be bypassed if a method on the same object calls another annotated method directly:

```java
@Service
class BadApprovalService {
    void process() {
        approve(); // Direct call within the same instance.
    }

    @PreAuthorize("hasAuthority('document:approve')")
    public void approve() {
        // Sensitive operation
    }
}
```

When a call bypasses the proxy, annotations may not execute. Design entry points to go through Spring beans/proxies properly, put policies where they are always invoked, and enforce invariants at the data layer. Never rely on `@PreAuthorize` as automatic protection for same-instance calls.

A class instantiated manually with `new` outside the Spring container also receives no method-security advice. For background tasks, define an explicit execution identity or system permission rather than assuming an HTTP principal always exists.

## 6. Data layer: preventing IDOR/BOLA and scope leaks

### 6.1. Queries must scope to the right object

For an API taking an ID from the URL, checking `document:read` and then calling plain `findById(id)` can expose someone else's document. This is an **IDOR/BOLA** vulnerability.

```sql
-- Insufficient to prove permission to read the record:
SELECT * FROM documents WHERE id = :id;

-- Owner model within the same tenant:
SELECT *
FROM documents
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :userId;
```

Apply equivalent scoping to `list/search/pagination/download/export`; never filter only after returning data to the client. In a sharing model, queries must express the owner or share-grant branch **while preserving mandatory invariants**.

### 6.2. TOCTOU: checked right, written with stale data

Suppose two requests both read a DRAFT document. Request A approves the document, while request B still holds stale data and issues an update. If B's write does not re-check state/version, the outcome can violate "approved documents cannot be edited".

Common mitigations:

- **Optimistic locking** via a `version` column and conflict handling.
- **Pessimistic locking** when access to certain records must be serialized.
- **Conditional UPDATE** including tenant, state, and version in the `WHERE` clause; verify affected row count.
- Database constraints for invariants expressible in data.

Illustrative example:

```sql
UPDATE documents
SET title = :newTitle, version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :userId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
```

If affected rows equals 0, do not report success. Determine whether the user lost access, the record changed state, or the version became stale per the API contract; never retry indefinitely in a way that alters user intent.

`@Transactional` alone does not eliminate every race if isolation levels or write predicates are insufficient. For side effects outside the DB, consider idempotency/outbox if business rules require them.

### 6.3. Avoid mass assignment

If the client sends `tenantId`, `ownerId`, `approvedBy`, or `status`, never bind all fields straight into the entity just because they have `document:update`. Use DTOs exposing only editable fields and dedicated business methods for state transitions. Someone permitted to edit content is not necessarily permitted to change ownership or self-approve.

## 7. Standalone Java 17: multi-layer decision via AND

The small example below has no Spring dependencies. It demonstrates how a request can be **allowed by HTTP** due to having the right authority, yet **denied by the service** because the caller is not the owner, or denied by data scope for wrong tenant.

Save file `LayeredAuthorizationDemo.java`:

```java
import java.util.Set;

public class LayeredAuthorizationDemo {
    enum Action { READ, UPDATE }
    enum Status { DRAFT, APPROVED }

    record Actor(long id, long tenantId, boolean active,
                 Set<String> authorities) {}

    record Document(long id, long tenantId, long ownerId,
                    Status status) {}

    static boolean httpAllowed(Actor actor, Action action) {
        if (actor == null || action == null || !actor.active()
                || actor.authorities() == null) {
            return false;
        }
        return switch (action) {
            case READ ->
                actor.authorities().contains("document:read");
            case UPDATE ->
                actor.authorities().contains("document:update");
        };
    }

    static boolean serviceAllowed(
            Actor actor, Action action, Document document) {
        if (actor == null || action == null || document == null) {
            return false;
        }
        boolean owner = actor.id() == document.ownerId();
        return switch (action) {
            case READ -> owner;
            case UPDATE ->
                owner && document.status() == Status.DRAFT;
        };
    }

    static boolean dataScopeAllowed(
            Actor actor, Document document) {
        return actor != null
            && document != null
            && actor.tenantId() == document.tenantId();
    }

    static boolean allowed(
            Actor actor, Action action, Document document) {
        return httpAllowed(actor, action)
            && serviceAllowed(actor, action, document)
            && dataScopeAllowed(actor, document);
    }

    static void show(String name, boolean result) {
        System.out.println(name + ": " + result);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            10, 1, true,
            Set.of("document:read", "document:update")
        );
        Actor bob = new Actor(
            20, 1, true, Set.of("document:read")
        );
        Actor outsider = new Actor(
            30, 2, true, Set.of("document:read")
        );
        Actor inactive = new Actor(
            10, 1, false, Set.of("document:read")
        );

        Document draft = new Document(101, 1, 10, Status.DRAFT);
        Document approved = new Document(102, 1, 10, Status.APPROVED);
        Document outsiderDoc =
            new Document(103, 2, 30, Status.DRAFT);

        show("alice reads own",
            allowed(alice, Action.READ, draft));
        show("bob reads alice",
            allowed(bob, Action.READ, draft));
        show("other tenant reads alice",
            allowed(outsider, Action.READ, draft));
        show("alice edits draft",
            allowed(alice, Action.UPDATE, draft));
        show("alice edits approved",
            allowed(alice, Action.UPDATE, approved));
        show("bob edits draft",
            allowed(bob, Action.UPDATE, draft));
        show("inactive reads",
            allowed(inactive, Action.READ, draft));
        show("anonymous reads",
            allowed(null, Action.READ, draft));
        show("tenant two owner reads own",
            allowed(outsider, Action.READ, outsiderDoc));
        show("http allows bob read",
            httpAllowed(bob, Action.READ));
        show("service denies bob read",
            serviceAllowed(bob, Action.READ, draft));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac LayeredAuthorizationDemo.java
java LayeredAuthorizationDemo
```

Expected output:

```text
alice reads own: true
bob reads alice: false
other tenant reads alice: false
alice edits draft: true
alice edits approved: false
bob edits draft: false
inactive reads: false
anonymous reads: false
tenant two owner reads own: true
http allows bob read: true
service denies bob read: false
```

**Notable point:** Bob has `document:read`, so he is allowed at the **functional permission layer**, yet he is not the owner and is denied at the **object policy layer**. This is the consistent result of a policy requiring multiple conditions, not a bug caused by two layers disagreeing.

This program only simulates policy. In a real app, `Document` data must be loaded from a trusted server/repository; never accept owner and tenant fields from client payloads as authoritative. When applied to a database, tenant filtering must occur right inside the corresponding queries.

## 8. Protecting non-HTTP paths too

An application can have multiple paths to the same action:

| Path | Risk when using only HTTP filters | Required safeguard |
| --- | --- | --- |
| REST GET/PATCH/DELETE | Undeclared URL/method | Matchers and object-level policy |
| File download API | Download URL differs from metadata endpoint | File permission bound to owning resource |
| CSV/PDF export | Filtered on screen yet exports whole DB | Query scope and export permission check |
| GraphQL resolver | Different entry point from REST | Permissions at resolver/service/data |
| WebSocket message | Once connected, sends any action | Check each message/action |
| Message consumer | Bypasses `AuthorizationFilter` | Identity/service policy at handler |
| `@Async` or scheduled job | Lacks the same `SecurityContext` | Machine permissions/delegation and explicit context propagation |
| Internal RPC | "Called internally" assumed always trusted | Service-to-service auth and object policy |
| Admin scripts | Can write straight to DB | DB scoping, audit, operational procedures |

In Servlet apps, `SecurityContextHolder` typically relies on `ThreadLocal`. Never assume a task running on another thread inherits the principal; if context must be propagated, use controlled mechanisms and bound permission lifetimes. A job running under a service account needs minimal permissions for that task.

If a microservice architecture enforces authorization at an API gateway, downstream services must still trust identity claims properly and protect data. A gateway cannot verify every owner/tenant/state without the corresponding business data, and internal channels may bypass the gateway.

## 9. Avoiding conflicts with unified policies and permissions

### 9.1. Permission catalog and role mapping

Example:

```text
ROLE_READER  -> document:read
ROLE_EDITOR  -> document:read, document:update
ROLE_APPROVER -> document:read, document:approve
```

When an IdP sends groups/roles, the application mapper must produce exact `GrantedAuthority` strings. Under standard Spring Security conventions, `hasRole("EDITOR")` checks `ROLE_EDITOR`; `hasAuthority("document:update")` matches the exact string `document:update`. If different places use different names without a mapping table, users may face unintended denials or accidental grants.

**Scoped permissions** must also be represented clearly: an editor in tenant A does not automatically edit documents in tenant B. Functional authorities alone do not encode object relationships, so tenant/owner policies must still be evaluated at the service/data layer.

### 9.2. Deny overrides do not appear automatically everywhere

A design may stipulate that mandatory denials (cross-tenant, locked account, forbidden state) override a general permit. However, Spring Security does not automatically collect results across all layers and run a global "deny overrides" engine. Authorization managers and combinators are explicitly configured; request matchers typically **select** one rule, whereas multiple checks across distinct boundaries may **all need to be satisfied**.

When writing custom multi-branch policies, clarify when `AND` vs. `OR` applies. When facts are insufficient to evaluate, never turn that into `ALLOW` by guesswork. Separate exception branches (such as temporary admin break-glass) into approved, time-bounded, audited policies.

### 9.3. How far should logic be split?

Keep URL/method rules at HTTP; keep task/object rules in services or policy beans; keep data scoping in queries. When an object condition is needed from multiple places, extract it into a reusable policy instead of duplicating divergent versions across controllers.

For sensitive actions, state conditions may need protection via **conditional write statements** even when already checked in policy. This defends the same invariant at different moments, not redundant duplication.

## 10. Evidence-based testing: which layer blocked?

### 10.1. Minimum matrix

| Test case | Layer being proven | Expectation |
| --- | --- | --- |
| User has permission, owner, same tenant, DRAFT | Full flow | Valid operation allowed |
| Missing permission | HTTP/method | Denied, DB untouched |
| Has permission but wrong owner | Object/service | Denied, no data returned |
| Has permission but wrong tenant | Repository/data | Denied, no record leaked |
| Has permission but status APPROVED | Workflow/data | Update disallowed |
| Unauthenticated | Authentication | Protected operation not executed |
| URL outside `securityMatcher("/api/**")` | Chain selection | Fallback handles, does not slip through |
| Two chains both match | `FilterChainProxy` | Higher-priority chain selected |
| Admin rule after overly broad matcher | HTTP rule order | Test catches exposure bug |
| Service called from another controller | Method security | Permissions not bypassed |
| Internal self-invocation | AOP boundary | Test uncovers proxy-bypass path |
| Download/export | Object/data | Returns only in-scope data |
| Two concurrent updates | Transaction/version | Never writes based on stale state |
| Policy service failure | Fail closed | No unauthorized side effects emitted |

### 10.2. Unit tests and integration tests

- **Policy unit tests:** test actor, action, and resource; cover valid conditions, missing data, wrong owner, wrong tenant, share grants, and state transitions.
- **HTTP tests with `MockMvc` and `spring-security-test`:** verify methods/paths/chains, principals, role prefixes, responses, and default-deny routes.
- **Method security integration tests:** invoke Spring beans through proxies to confirm annotations execute; include calls from alternate entry points.
- **Repository tests:** use at least two tenants and two owners; list/detail/export queries must never return out-of-scope records.
- **Transaction/concurrency tests:** use realistic data or production-like test DBs; verify versions/conflicts and ensure side effects never duplicate.

An illustrative test call with `mockMvc` and fixtures already set up:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Inside a @Test method with MockMvc and fixtures configured:
mockMvc.perform(patch("/api/documents/101")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("document:update")))
        .with(csrf())
        .contentType("application/json")
        .content("{\"title\":\"Updated\"}"))
    .andExpect(status().is2xxSuccessful());
```

In this example, `SimpleGrantedAuthority` is `org.springframework.security.core.authority.SimpleGrantedAuthority`; a 2xx response only succeeds if the controller, fixtures, and real state are valid. This is **not a standalone Java class**. For POST/PATCH/DELETE with CSRF enabled, include a valid CSRF token when testing authorization policies; otherwise 403 may come purely from CSRF and prove nothing about owner/tenant rules.

Beyond HTTP status codes, verify database state, record counts, messages/outbox, and audits afterward. A test returning 403 while data was already mutated is still a security failure.

### 10.3. Diagnosing when one layer allows yet another denies

1. Confirm which chain the request matched per `securityMatcher` and `@Order`.
2. Confirm which matcher in `authorizeHttpRequests` was selected.
3. Inspect the actual identity/authorities in `Authentication`, including `ROLE_` vs. permission naming differences.
4. Verify method security is enabled, calls go through proxies, and beans are Spring-managed.
5. Check tenant, owner, share grants, state, and version of the object from server data.
6. Inspect query/list/export conditions rather than relying only on one endpoint's response.
7. Check CSRF, authentication entry points, exception handlers, and tokens/sessions/caches.
8. Check whether the transaction had side effects; use correlation IDs to link logs.

In APIs, **401** usually indicates unauthenticated, **403** usually indicates missing permissions (or CSRF error), **404** may intentionally hide object existence, **409** may indicate state/version conflict, and infrastructure errors may be **5xx**. Identify the **true reason**; never treat one status code as proof that every layer works properly.

## 11. Common mistakes

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Having only a chain for `/api/**` | Routes outside API may be unprotected | Fallback chain and test coverage |
| High-priority chain matches too broadly | Later chains never run | Define explicit matchers and order |
| `authenticated()` before admin rule | Regular users can hit admin route | Narrow rules first, default deny |
| Checking only roles/authorities | Changing ID accesses other objects | Tenant/owner/share/state policy |
| Calling `findById(id)` and returning directly | IDOR/BOLA | Scoped queries |
| Relying on `@PreAuthorize` over self-invocation | AOP does not run | Proper service/proxy boundaries |
| Job calling repository directly | Bypasses HTTP/service checks | Business-layer guard at entry point |
| Combining permissions carelessly with `OR` | Weak branch bypasses mandatory checks | Parenthesized AND/OR and tests |
| Writing after checking stale status | TOCTOU and state corruption | Versioning/locking/conditional updates |
| Testing 403 while forgetting CSRF | Misdiagnosing policy | Separate security and CSRF tests |
| Inconsistent `ROLE_`/permission mapping | False denials or unintended grants | Reviewed catalog + mapping |
| Letting policy-service errors pass | Infrastructure errors open holes | Fail closed |
| Filtering lists on the frontend | Can leak full dataset | Enforce data scope server-side |

## 12. Hands-on exercises

**Exercise 1 — Map checkpoints.** For a document read/edit REST API, download endpoint, and export job, mark where principal, permission, tenant, owner, and state are checked. Done when no path reaches sensitive data without mandatory conditions.

**Exercise 2 — Configure two chains.** Create an API chain and a fallback. Test GET/PATCH/DELETE requests, public endpoints, unregistered URLs, and URLs outside `/api/**`. Deliberately place a `/**` chain at high priority to watch tests catch the mistake.

**Exercise 3 — Run Java 17.** Compile `LayeredAuthorizationDemo.java`. Add a share-grant branch for READ without bypassing tenant/authority checks. Write cases for valid owner, wrong owner, wrong tenant, missing permission, and locked state.

**Exercise 4 — Test the service.** Add `@PreAuthorize` on a service, enable method security, and test calling via a Spring bean vs. self-invocation. Refactor so sensitive calls always cross a policy enforcement boundary.

**Exercise 5 — Data layer.** Write a query scoped by ID/tenant/owner, then add optimistic locking or `version`-checked UPDATE. Create two concurrent requests and confirm an approved document cannot be updated.

**Exercise 6 — Regression testing.** When adding a new role able to read shared documents, update the permission matrix, mapper, policy, queries, and tests. Re-run download/export/job paths to ensure the new permission does not leak out-of-scope data.

## 13. Pre-deployment checklist

- [ ] Every sensitive action has a clear actor/action/resource/context policy.
- [ ] Every HTTP route is protected by an appropriate chain; fallback chain tested.
- [ ] `securityMatcher`, `requestMatchers`, and `@Order` are ordered correctly.
- [ ] Undeclared new endpoints are denied by default.
- [ ] HTTP permissions, role mappings, and method permissions align.
- [ ] Object/tenant/owner/sharing rules are reused where needed.
- [ ] List/detail/export/download queries scope the dataset accurately.
- [ ] No non-HTTP call or self-invocation bypasses policy.
- [ ] State/version is checked at write time, handling concurrency.
- [ ] DTOs prevent clients from modifying tenant, owner, status, or sensitive fields.
- [ ] Tests cover allow/deny and verify DB state and side effects.
- [ ] Decision reasons are logged/audited and permission revocation is managed.

## 14. Self-check

1. **Do two `SecurityFilterChain`s matching the same request run sequentially?** No; `FilterChainProxy` selects the first matching chain.
2. **Does `anyRequest().denyAll()` in an `/api/**` chain block `/admin/export`?** No, if the request never enters that chain; a fallback or full coverage is needed.
3. **Does having `document:read` allow reading someone else's ID?** No; tenant/owner/share/state still apply.
4. **Is HTTP allowing while object policy denies a contradiction?** No, if the policy requires both conditions.
5. **Why is self-invocation risky?** It can bypass the Spring AOP proxy so annotations do not run.
6. **Why must export queries be scoped?** HTTP only decides whether to invoke the endpoint, not which records get filtered.
7. **Why does versioning matter on updates?** To detect state/data changes between check and write.
8. **Is 403 enough to prove object policy blocked properly?** No; 403 could come from CSRF or another matcher.
9. **When the policy service fails, can sensitive operations be allowed temporarily?** No; fail closed and return an appropriate error.
10. **What must be done when adding a new endpoint?** Review policy, chain coverage, method/object/data enforcement, and tests.

**Remember:** effective multi-layer defense is not about adding the most annotations. The system must **cover every access path**, **place each condition where data is trustworthy**, **state clearly how decisions combine**, and **verify through tests that a functionally permitted path still cannot bypass object scope, state, or data constraints**.

### Official documentation

- [Spring Security – Java Configuration and multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)