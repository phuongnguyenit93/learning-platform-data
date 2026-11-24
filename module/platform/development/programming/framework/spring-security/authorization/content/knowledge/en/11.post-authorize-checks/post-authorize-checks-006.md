# Combining `@PreAuthorize` and `@PostAuthorize` on the Same Business Operation in Spring Security

## 1. The problem: allowed to read a data type, not necessarily a specific record

Suppose a multi-user document service exposes `GET /api/documents/{id}`. Alice is granted the `document:read` authority and has permission to read her own documents. Bob also has `document:read`, but may only read Bob's documents. An HTTP request from Alice using Bob's document ID:

```http
GET /api/documents/doc-bob HTTP/1.1
Authorization: Bearer <valid-token-for-alice>
```

Here **two distinct questions** must be answered:

1. **Before running the service:** is the caller allowed to use the *document reading feature*?
2. **After the service fetches the document:** does the actually found record fall within the scope the caller is allowed to read?

In Spring Security method security, an intentional way to express this is:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentView readDocument(String documentId) {
    return documentRepository.loadView(documentId);
}
```

This is an illustrative **fragment**, requiring `DocumentView` with an `ownerId` property, a repository, and a Spring-managed service. `@PreAuthorize` checks permission **before** the method body runs. `@PostAuthorize` checks the `returnObject` result **after** the method body has run, yet before the result is returned to the caller through the proxy, under the default interceptor mechanism.

Lesson objectives:

- Understand the order and effect of both annotations when attached to the same method.
- Write `@PreAuthorize` expressions checking roles/authorities, login state, and trusted parameters.
- Write `@PostAuthorize` checking `returnObject`, ownership, tenant, and policies based on **the actual returned value**.
- Know why the two annotations have **AND** semantics on the final outcome, yet **do not** run simultaneously and **do not** replace each other.
- Distinguish read-data controls from write/delete/event-emitting operations that produce side effects.
- Avoid risks around `null`, `Optional`, `List`, proxies/self-invocation, error responses, async, and transaction ordering.
- Build unit/integration tests proving both **before method**, **after method**, **no leaked results**, and **no unauthorized writes**.
- Choose safer structures when per-object or per-tenant permissions apply.

**Scope:** Spring Security Servlet/Spring MVC, Java 17+, `@EnableMethodSecurity`, JUnit 5, Spring Security Test. Some Spring examples are integration fragments; the lesson also includes a standalone Java 17 program simulating pre/body/post ordering to run without Maven.

## 2. Two authorization layers in a single method invocation

### 2.1. Execution diagram

Modern Spring Security creates two separate method interceptors, so a call through a Spring AOP proxy typically progresses as:

```text
Caller (controller or another bean)
        │
        ▼
Spring-managed proxy
        │
        ├─ @PreAuthorize expression
        │    ├─ DENY → method body DOES NOT run
        │    └─ ALLOW
        │          │
        │          ▼
        │      Method body
        │          ├─ throws exception → exception handling,
        │          │                     no normal returnObject
        │          └─ returns DocumentView
        │                  │
        │                  ▼
        └──────── @PostAuthorize expression
                     ├─ DENY → blocks return value
                     └─ ALLOW → caller receives DocumentView
```

Concrete implementation names per Spring Security documentation:

- `AuthorizationManagerBeforeMethodInterceptor` uses `PreAuthorizeAuthorizationManager` for `@PreAuthorize`.
- `AuthorizationManagerAfterMethodInterceptor` uses `PostAuthorizeAuthorizationManager` for `@PostAuthorize`.
- Both typically use a `MethodSecurityExpressionHandler` building an `EvaluationContext` to evaluate SpEL.

This is a simplified diagram and **does not** promise the order of every custom AOP advisor, transaction interceptor, logging filter, or distributed aspect. The key point is that **the pre-check can block before the body**, while **the post-check evaluates the result after the body**.

### 2.2. The most important truth table

Let `P` be the pre-check outcome; `Q` be the post-check outcome on the produced result.

| P before method | Does method body run? | Q after method | Does caller receive return value? |
| --- | --- | --- | --- |
| DENY | **No** | Not evaluated on normal flow | No |
| ALLOW | **Yes** | DENY | No; body already ran |
| ALLOW | **Yes** | ALLOW | Yes |
| ALLOW | Yes, but body throws exception | No normal return value to check | Caller receives exception per framework handling |

Writing both annotations can be thought of as **P AND Q** at the *final authorization* level, yet not `P && Q` evaluated before the body. In particular, when Q is false, **there is no automatic time-travel mechanism** to undo every side effect in the body.

### 2.3. Why don't the two annotations override each other?

In Spring Security 6.x/7.x, each annotation has its own pointcut/interceptor; when both `@PreAuthorize` and `@PostAuthorize` apply, Spring Security processes them sequentially. **Both conditions must pass** for the result to be returned along the normal path.

Example:

```java
@PreAuthorize("hasRole('AUDITOR')")
@PostAuthorize("returnObject.classification != 'SECRET'")
public ReportView readReport(String id) { /* ... */ }
```

An AUDITOR can pass `@PreAuthorize` yet still be denied if the actual report is marked SECRET. Conversely, a user lacking `ROLE_AUDITOR` cannot execute the body even if the report is PUBLIC.

**Note:** two annotations of **the same kind** cannot be repeated on one method (`@PreAuthorize` twice or `@PostAuthorize` twice). To combine multiple conditions before or after, use SpEL `and`/`or` inside one annotation, or call a policy bean.

## 3. Enabling method security and distinguishing from HTTP security

### 3.1. Activating `@PreAuthorize` and `@PostAuthorize`

In modern Spring Security, use:

```java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` enables pre/post annotation support by default. Merely declaring `spring-boot-starter-security` **does not automatically ensure** both annotations on services are enforced. For older projects using `@EnableGlobalMethodSecurity(prePostEnabled=true)`, consult the migration guide for your Spring Security version.

### 3.2. HTTP authorization remains an independent layer

Servlet filter chain fragment example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/**")
        .authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

An authenticated user can pass the HTTP rule for GET documents, yet the service still requires `document:read` and owner/tenant. If the HTTP matcher already did `denyAll()`, `@PreAuthorize("permitAll")` will not reopen that URL.

Conversely, method security protects calls from **other beans** or background use cases if invocations go through a Spring proxy; it does not replace HTTP controls, CSRF, session/token validation, CORS, or rate limits.

### 3.3. Cases to test independently

- HTTP blocks before service: body and both method expressions may never be invoked.
- HTTP allows, `@PreAuthorize` blocks: body does not run.
- HTTP allows, pre allows, post denies: body runs yet result is blocked.
- HTTP + pre + post allow: caller receives result.
- Another bean calls service via proxy (no HTTP): method security still needs enforcement and a valid Authentication.

In a typical controller, `AccessDeniedException` can be translated by `ExceptionTranslationFilter` into 403 or an authentication entry-point response. Outside HTTP, the caller must handle the exception according to the task's contract.

## 4. `@PreAuthorize`: the gate before the method body

### 4.1. Roles and authorities

```java
@PreAuthorize("hasRole('ADMIN')")
public AdminDashboard dashboard() { /* ... */ }

@PreAuthorize("hasAuthority('document:read')")
public DocumentView read(String id) { /* ... */ }

@PreAuthorize("hasAnyAuthority('document:read', 'document:manage')")
public DocumentView preview(String id) { /* ... */ }
```

By default convention, `hasRole('ADMIN')` requires `ROLE_ADMIN`; `hasAuthority('document:read')` checks the exact permission string. `hasAnyAuthority` is OR, not AND.

With JWT, `scope=documents.read` may be mapped by the default converter to `SCOPE_documents.read`, **not automatically equal to** `document:read`. Authority mapping must be implemented and tested at the authentication source, never “fixed” by switching rules to `permitAll`.

### 4.2. `isAuthenticated` is not synonymous with `isFullyAuthenticated`

```java
@PreAuthorize(
    "isAuthenticated() and hasAuthority('document:read')"
)
```

`isAuthenticated()` excludes anonymous per `AuthenticationTrustResolver`, yet may accept remember-me authentication. If the business operation requires full login:

```java
@PreAuthorize(
    "isFullyAuthenticated() and hasAuthority('payment:approve')"
)
```

`isFullyAuthenticated()` excludes anonymous and remember-me, **without** automatically proving MFA, recent re-authentication, or a specific assurance level. Those requirements need additional policy based on a trusted identity source.

### 4.3. Method parameters are selectors, not proof of permission

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@readPolicy.mayRequest(authentication, #documentId)"
)
public DocumentView read(String documentId) { /* ... */ }
```

`#documentId` comes from the caller and can be altered. `@readPolicy` must check membership/tenant/ownership in the DB or a trusted source; never accept a client-declared `ownerId`. For Java parameter names, enable the `-parameters` compiler flag or use `@P` if needed.

### 4.4. Pre-check can read the DB yet still not know the final result

`@PreAuthorize` sees the invocation and arguments, not `returnObject`, because the method has not executed. If an object-level policy needs the real owner from the DB, it can call a service/repository in the pre-check. However:
- The check can increase query count.
- The resource can change between pre-check and body (TOCTOU).
- Without proper transactions/locking, a passing pre-check does not automatically guarantee permission at mutation time.
- If the result comes from another system or complex query mapping, a post-check can add defense-in-depth value — **especially for read-only methods**.

## 5. `@PostAuthorize`: the gate on the actual returned result

### 5.1. `returnObject` is the normal return value

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentView findDocument(String id) { /* ... */ }
```

The expression references the object created or loaded by the body. Spring Security can access the `ownerId` property via `DocumentView`'s JavaBean getter `getOwnerId()`.

Do not assume the result is an entity matching the request. If a method returns `DocumentSummary` having only `title` and `id`, `returnObject.ownerId` may not exist. Design return types and policies to match real data types, avoiding unexpected SpEL errors.

### 5.2. Null-safe expressions

If a method can return `null`, write:

```java
@PostAuthorize(
    "returnObject != null and " +
    "returnObject.ownerId == authentication.name"
)
public DocumentView findOrNull(String id) { /* ... */ }
```

SpEL's `and` prevents accessing `ownerId` if `returnObject` is null. With this expression, `null` causes denial; **that is a policy decision**, not the framework automatically choosing to return 404. When not found, it is usually better to throw a domain exception like `DocumentNotFoundException` or return another explicitly contracted result, and test exception mapping separately.

If the return type is `Optional<DocumentView>`, `returnObject` is **Optional** (or the corresponding wrapper) at the expression point; do not assume it has `ownerId` directly. Use a policy bean that understands the exact return type, or structure the method to return a normal view and handle absence beforehand.

### 5.3. Post-check is not redaction

`@PostAuthorize` normally decides to allow or deny **the entire return value**. It does not automatically strip fields like `internalNote`, `accessToken`, or `salary` from an allowed object. For data requiring field masking, build an allowlisted response DTO or use per-property policies.

Nor does it automatically filter individual items in a list. A method returning `List<DocumentView>` whose expression checks `returnObject.ownerId` has a type mismatch. For collections, prefer **queries scoped by principal/tenant**; only use `@PostFilter` or custom filtering when justified and evaluated for performance/security.

### 5.4. Use a policy bean for multi-condition post-check logic

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "@documentReadPolicy.canReturn(authentication, returnObject)"
)
public DocumentView find(String documentId) { /* ... */ }
```

Here `@documentReadPolicy` is a custom Spring bean; `canReturn` must check null, verified actor identity, tenant, ACL, and object state. Do not trust `returnObject.tenantId` if that data came from client JSON without passing through a trusted source.

### 5.5. The result is computed before being blocked

When `@PostAuthorize` denies, the caller receives no normal value through the proxy. **Yet** the method may already have:
- Called the DB to read data.
- Loaded files/objects from storage.
- Written logs containing sensitive data.
- Pushed the object into a shared cache.
- Called another API with side effects.
- Incremented counters, sent metrics, or emitted events.

Therefore, avoid logging/emitting/caching sensitive information before verifying permissions, even if HTTP ultimately returns 403. Blocking after the body **is insufficient** to protect internal observation channels.

## 6. Designing read operations: combining permissions and ownership

### 6.1. Illustrative data

A document repository holds:

| ID | Real Tenant | Real Owner | Title |
| --- | --- | --- | --- |
| `doc-a` | `org-1` | `alice` | Draft of Alice |
| `doc-b` | `org-1` | `bob` | Review of Bob |
| `doc-c` | `org-2` | `carol` | Private of Carol |

Alice and Bob both have `document:read`, yet permission to read each document depends on owner, membership/ACL. Changing `doc-a` to `doc-b` in the URL must not let Alice read Bob's document. This is the BOLA/IDOR problem: functional roles/permissions do not automatically grant access to arbitrary objects.

### 6.2. Minimal service using both annotations

Create `DocumentView.java` in a Spring Boot/Java 17 project:

```java
package com.example.demo;

public final class DocumentView {

    private final String id;
    private final String ownerId;
    private final String title;

    public DocumentView(String id, String ownerId, String title) {
        this.id = id;
        this.ownerId = ownerId;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public String getTitle() {
        return title;
    }
}
```

Create `DocumentReadService.java`:

```java
package com.example.demo;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReadService {

    private final Map<String, DocumentView> docs = Map.of(
            "doc-a", new DocumentView(
                    "doc-a", "alice", "Draft of Alice"),
            "doc-b", new DocumentView(
                    "doc-b", "bob", "Review of Bob"));

    // Only to illustrate execution order in tests.
    private final AtomicInteger bodyCalls = new AtomicInteger();

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize(
            "returnObject != null and " +
            "returnObject.ownerId == authentication.name"
    )
    public DocumentView read(String id) {
        bodyCalls.incrementAndGet();
        DocumentView view = docs.get(id);
        if (view == null) {
            throw new NoSuchElementException("Document not found");
        }
        return view;
    }

    public int getBodyCallsForTest() {
        return bodyCalls.get();
    }
}
```

This class **compiles in a Spring Boot project** with Spring Context/Spring Security and method security. It is not a standalone `javac` program because of the Spring annotations/dependencies.

Meaning of the two annotations:

1. `@PreAuthorize`: the user must have direct/effective authority `document:read` before code inside `read` executes.
2. `@PostAuthorize`: only a result whose `ownerId` equals `authentication.name` is returned through the proxy.
3. User missing permission: `bodyCalls` does not increment.
4. User has permission, and Alice requests `doc-b`: `bodyCalls` **did increment**, yet the result is blocked.
5. Alice reads `doc-a`: both pre and post allow.
6. Non-existent ID: the method throws `NoSuchElementException`; since there is no normal result, handle via exception mapping/domain contract rather than treating it as a post-authorization pass/deny.

**Intentional limitation of the demo:** `authentication.name` is used as the user ID for clarity. In production, `getName()` may be a username, email, JWT `sub`, or converter-defined identifier. If DB `ownerId` is an internal UUID, map the principal to a trusted user ID; never compare two ID types with mismatched semantics.

### 6.3. Why should the demo service only read?

It only reads an in-memory `Map` and increments a test counter. That is appropriate for demonstrating post-checks. If `read` were changed to `delete`, the body could delete the document before `@PostAuthorize` knows the result's owner; that is a broken design for write operations.

In real systems, document queries should be **scoped by tenant/owner/ACL right at the repository**, with post-checks as an additional layer if needed. Do not query all sensitive data and rely solely on post-checks to guard all internal execution paths.

## 7. Production: policy bean distinguishing actor, tenant, and real object

### 7.1. Never trust client-declared `ownerId`/`tenantId`

A request might send:

```http
GET /api/tenants/org-1/documents/doc-b
X-User-Id: alice
X-Tenant-Id: org-1
```

Header/path values are client-controlled data. Do not compare:

```java
@PostAuthorize(
    "returnObject.ownerId == #ownerIdFromRequest"
)
```

because the client can choose the request `ownerId` as well. **The real owner source** must come from loaded/verified server data; **the identity source** must come from verified authentication.

### 7.2. Post-check policy bean

Architectural pattern:

```java
package com.example.documents.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentReadPolicy")
public class DocumentReadPolicy {

    private final ActorIdentityResolver identityResolver;
    private final TenantMembershipRepository memberships;

    public DocumentReadPolicy(
            ActorIdentityResolver identityResolver,
            TenantMembershipRepository memberships) {
        this.identityResolver = identityResolver;
        this.memberships = memberships;
    }

    public boolean canReturn(
            Authentication authentication,
            DocumentView view) {

        if (authentication == null || view == null) {
            return false;
        }

        String actorId =
                identityResolver.requireTrustedActorId(authentication);

        String tenantId = view.getTenantId();
        if (!memberships.isActiveMember(actorId, tenantId)) {
            return false;
        }

        boolean owns = actorId.equals(view.getOwnerId());
        boolean shared = memberships.hasDocumentReadGrant(
                actorId, tenantId, view.getId());

        return owns || shared;
    }
}
```

**Architectural fragment:** `DocumentView` here must also expose `getTenantId()`, and the project must implement `ActorIdentityResolver`/`TenantMembershipRepository` with trusted repository logic. Method names `requireTrustedActorId`, `isActiveMember`, `hasDocumentReadGrant` are not built-in Spring Security APIs. If the identity resolver encounters an invalid token/subject mapping, it must fail closed.

If legitimate cross-tenant read access exists, define a dedicated scoped/audited policy rather than having a global `ROLE_ADMIN` bypass tenants.

### 7.3. Pre-check before querying and post-check after querying

One design:

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "hasAuthority('document:read') and " +
    "@tenantPolicy.isMember(authentication, #tenantId)"
)
@PostAuthorize(
    "@documentReadPolicy.canReturn(authentication, returnObject)"
)
public DocumentView read(
        String tenantId,
        String documentId) {

    return repository.findViewByIdAndTenantId(
            documentId, tenantId).orElseThrow(
                () -> new DocumentNotFoundException(documentId));
}
```

This is a fragment with application-written policy/repository/exception classes. The pre-check verifies the caller has read permission and membership in the requested tenant. The repository scopes by `tenantId`, and the post-check verifies the **returned object** is authorized. In production, add negative tests for both layers; do not test only “happy path” users.

### 7.4. If the repository already scopes properly, is a post-check still useful?

It can be useful as **defense in depth**: catching broken joins/filters/mappers, or data assembled from multiple sources. However, if the query already enforces strict owner/tenant constraints, adding a post-check that queries the DB again can increase latency and complexity for little gain. Decide based on threat model and testing cost rather than forcing both annotations onto every method.

If the post-check executes a new DB query, data may have changed between when the method loaded and when the policy checked (TOCTOU). For reads, understand transaction/snapshot consistency; do not treat two reads at two moments as an atomic check.

## 8. Never use `@PostAuthorize` as the sole barrier for writes/deletes

### 8.1. Anti-pattern: delete first, check owner afterward

```java
@PreAuthorize("hasAuthority('document:delete')")
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public DocumentView deleteAndReturn(String id) {

    Document entity = repository.findById(id).orElseThrow();
    repository.delete(entity);
    return mapper.toView(entity);
}
```

This **anti-pattern** is dangerous: `repository.delete(entity)` has already been called **before** the post-check evaluates ownership. If Alice's request targets Bob's document, the body may already have deleted the data. `@PostAuthorize` refuses to return the object, yet does not guarantee the DB was restored.

Do not take HTTP returning 403 as proof that nothing changed. Even if a specific transaction rolls back, emails/queues/external APIs/file deletions may already have occurred or failed to roll back.

### 8.2. `@Transactional` is not “undo magic”

Spring Security docs specifically warn against placing `@PostAuthorize` on DB-writing methods. If a method has both `@Transactional` and `@PostAuthorize`, rollback/commit depends on **AOP interceptor order**, transaction boundaries, exception propagation, transaction manager type, and non-DB side effects.

There are configurations where a post-method denial triggers a transaction rollback, yet **never rely on that** without end-to-end tests on your exact Spring version and persistence technology. More importantly, message brokers/HTTP calls/notifications outside the DB transaction generally **cannot** roll back automatically.

**Recommendation:** check object permissions **before mutation**; reinforce with DB transactions/conditional updates. `@PostAuthorize` on writes never replaces proper authorization and atomicity design.

### 8.3. Separate read/check from mutate

A more auditable design:

```java
@PreAuthorize(
    "hasAuthority('document:delete') and " +
    "@documentPolicy.canDelete(authentication, #id)"
)
@Transactional
public void delete(String id) {

    String actorId = actorResolver.requireCurrentActorId();

    Document entity = repository.findByIdWithLock(id)
            .orElseThrow(() -> new DocumentNotFoundException(id));

    // Re-check while holding lock/inside transaction.
    documentPolicy.requireMayDelete(actorId, entity);
    repository.delete(entity);
}
```

**Architectural fragment** needing application-implemented `documentPolicy`/`repository`/`actorResolver` and lock semantics. `findByIdWithLock` is not a built-in `JpaRepository` method; declare the appropriate query/locking. Pre-checking on ID and rechecking against the live entity reduces TOCTOU risk; pay attention to transaction behavior and post-commit event handling.

### 8.4. Guarded DB update when the policy fits

For owner-only updates, you can use a conditional SQL statement:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :trusted_tenant_id
  AND owner_id = :trusted_actor_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

`trusted_actor_id` comes from verified Authentication mapping, tenant from verified membership, and ID/version from the request serve purely as selectors/concurrency tokens. Check updated row count: **0** means mismatch/unauthorized/version conflict; never retry with a bare `WHERE id=:id`. For `edit:any` permissions, a separate policy/update statement with explicit scope is needed.

This approach is not mandatory for every use case; it illustrates **attaching authorization conditions to the write** instead of waiting to inspect results after side effects occur.

## 9. `@PostAuthorize` considerations by return value type

### 9.1. A DTO loaded from DB

This is the natural case:

```java
@PostAuthorize(
    "returnObject != null and " +
    "@documentReadPolicy.canReturn(authentication, returnObject)"
)
public DocumentView findOne(String id) { /* read only */ }
```

The policy bean understands the real fields of the DTO. If `id` does not exist, handle 404/exceptions per API contract rather than abusing a null post-deny as an automatic 404 response.

### 9.2. `Optional<DocumentView>`

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public Optional<DocumentView> findOptional(String id) { /* ... */ }
```

**Do not use this expression verbatim.** `returnObject` is the actual value returned at the method boundary; with return type `Optional<DocumentView>`, do not assume `ownerId` can be accessed directly as if it were `DocumentView`.

If the business still wants Optional, use a policy bean that understands `Optional` and gives clear outcomes for empty/present, or extract a method returning a resolved `DocumentView` and handle absence inside. Choose the option that reads clearly and minimizes SpEL type error risks.

### 9.3. `List`, `Page`, `Stream`, `Map`

Do not post-check row by row after fetching **all tenant data**, because:
- Data leaks into heap/logs before post-policy.
- Pagination/counts can disclose the number of unauthorized records.
- N+1 queries and memory overload.
- Collection return types do not have a single `ownerId`.
- Streams can be lazy, fetching data after the method returns.

**Preferred:** repository queries/filters scoped by actor/tenant/ACL, returning only permitted records with accurate pagination/counts. `@PostFilter` has specific uses but **does not** replace pagination-safe, DB-level object filtering for large datasets.

### 9.4. Asynchronous and reactive return types

A method returning `CompletableFuture<DocumentView>` or reactive `Mono<DocumentView>` has different return value/wrapper semantics and execution timing than returning a synchronous `DocumentView`. **Never** assume `@PostAuthorize("returnObject.ownerId == ...")` automatically checks the result *inside* the future/stream the same way.

Spring Security has distinct integration mechanisms for Servlet, method security, and reactive; for async/reactive, use the appropriate authorization APIs and test on the exact version, executor/Reactor context. If work runs on another thread, the default ThreadLocal-based `SecurityContextHolder` does not automatically propagate across every `Executor`.

### 9.5. Avoid using long-lived entities as `returnObject`

JPA entities have lazy associations, bidirectional graphs, and sensitive fields. SpEL property access can trigger queries outside the transaction/when the session is closed, or serialize the entire entity before ownership checks. **Prefer immutable response DTOs** containing only fields needed by the policy and API, and avoid hiding DB operations inside getters.

## 10. Security context and trust: comparing the right identity/tenant

### 10.1. Is `authentication.name` the owner ID?

Not always. `Authentication.getName()` depends on form login, JWT converters, OAuth2 principals, and custom authentication. If the database stores `ownerId` as an internal UUID while authentication name is an email, the expression:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
```

will be semantically inaccurate. Build an `ActorIdentityResolver` mapping verified issuer + subject to a stable user ID, and have the policy bean check:

```java
@PostAuthorize(
    "@documentReadPolicy.canReturn(authentication, returnObject)"
)
```

**Never** take `userId` from `X-User-Id` or a client-sent body in place of verified authentication.

### 10.2. Tenant ID in path is a selector, not proof

`GET /tenants/org-2/documents/doc-c` does not mean the caller belongs to `org-2`. Pre-check must verify membership/permission for the selected tenant, and post-check must confirm the real document belongs to that tenant. Never merely compare `#pathTenantId == #bodyTenantId`, since both are client-controlled.

### 10.3. JWT roles/scopes can be stale

A signed token may contain scopes valid at issuance that are stale after the user leaves a tenant or has permissions revoked. `hasAuthority` normally checks authorities placed into Authentication by the converter; it does not re-read the DB on every call. For sensitive actions, the policy bean must verify current membership/ACLs and pair with an appropriate revocation/TTL strategy.

### 10.4. Role hierarchy changes pre-checks

If `ROLE_ADMIN > ROLE_READER` exists in `RoleHierarchy` and the method expression handler is configured to use that graph, `hasRole('READER')` can evaluate true for a user with only direct `ROLE_ADMIN`. Yet a hierarchy only implies defined functions/authorities; it **does not** know which tenant owns which data. Object-level post-checks remain necessary if admins do not have unrestricted cross-tenant access.

### 10.5. Never rely on a client-chosen `returnObject`

A post-check is only trustworthy when the result is data created or verified by the service/repository/server, not an object merely echoed from caller-sent JSON. If a method does:

```java
public DocumentView echo(DocumentView untrusted) {
    return untrusted;
}
```

then `returnObject.ownerId == authentication.name` only confirms a field the client could set themselves. Owner/tenant must be retrieved from server-side data or a trusted policy service.

## 11. 403, 404, information leakage, and API experience

### 11.1. When the post-check denies, what does the caller receive?

In default configuration, Spring Security normally throws `AccessDeniedException` from the method interceptor. For HTTP requests through `SecurityFilterChain`, exception handling can turn this into 403 or an authentication entry-point redirect/401 depending on user state and config. There is no guarantee that the returned object “gets returned and only then hidden by the browser”; **the caller is blocked before receiving a normal return value** through the proxy.

In code not running over HTTP, handle exceptions per contract: scheduled jobs, queue consumers, gRPC layers, or test services may observe the Java exception directly.

### 11.2. 403 vs. 404 and anti-enumeration

If a non-existent `doc-a` returns 404 while Bob's `doc-b` returns 403, Alice can distinguish “whether an ID exists”. Depending on the threat model, this can leak information. You can design a **scoped repository lookup** returning 404 for objects outside the caller's scope, and add service-level policy checks.

Never return `ownerId`, `tenantId`, or metadata of a denied object in error bodies. Proper logs may keep a correlation ID and categorized reason while avoiding raw tokens/PII or sensitive content.

### 11.3. Exception translation does not protect side effects

When HTTP 403 comes from `@PostAuthorize`, the method body may still have executed. Translating an exception into a response does not undo DB writes, sent messages, or external API calls. Verify events/audits/DB in tests, not just `status().isForbidden()`.

### 11.4. Do not “fix” 403 with `permitAll`

If pre-check denies for missing permission or post-check denies for wrong owner, fix the authority source, policy object, or fixture data. Never replace `@PreAuthorize` with `permitAll` or delete `@PostAuthorize` to make a dashboard render: that can open BOLA on arbitrary objects.

## 12. AOP proxies, class-level annotations, and limits on the same operation

### 12.1. Self-invocation can bypass both pre and post

```java
@Service
public class UnsafeDocumentService {

    public DocumentView outer(String id) {
        return inner(id); // this.inner(id), bypasses proxy.
    }

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize("returnObject.ownerId == authentication.name")
    public DocumentView inner(String id) {
        return repository.loadView(id);
    }
}
```

**Anti-pattern:** `outer` calls `inner` internally on the same instance; in standard Spring AOP proxy mode, annotations on `inner` may **not be intercepted**. Both pre and post can be bypassed. The solution is moving `inner` to another Spring-managed service, injecting the proxy, and calling across the bean boundary; also enforce owner/tenant checks in the domain layer as needed.

### 12.2. Private/final/non-Spring methods

Methods not advised by Spring AOP, objects instantiated with `new`, private methods, or final/proxy-incompatible methods do not form a reliable boundary for annotations. With Kotlin/Java, check your proxy strategy and how the framework handles methods/interfaces. If using AspectJ weaving instead of proxies, behavior differs; test on the actual runtime configuration.

### 12.3. Class and method annotations

`@PreAuthorize` on a class sets a general rule that can be overridden by a method-level `@PreAuthorize` per annotation resolution rules. `@PostAuthorize` on a method is **a different annotation type**, so it can participate alongside a class-level pre-rule. Do not assume a method-level post-check cancels a class-level pre-check.

With annotations inherited from multiple interfaces or meta-annotations, Spring Security may detect conflicts; place clear rules on concrete methods and test startup/invocation.

### 12.4. Multiple advisors operate independently

When `@EnableMethodSecurity` enables `@PreAuthorize`, `@PostAuthorize`, and other advisors (`@Secured` or JSR-250 when enabled), they do not merge into a single “one-shot decision before the body”. Spring Security docs describe annotations being checked sequentially and acting as an AND on allowed outcomes. Each layer runs at its own stage.

Do not rely on arbitrary ordering of custom AOP advisors to “sneak past” policies; if exact ordering is required, use official configuration and tests.

### 12.5. Methods with `@PreAuthorize` called from `@Async`

In the Servlet stack, `SecurityContextHolder` uses ThreadLocal by default. If an invocation is dispatched to a raw executor without context propagation, pre/post methods may not see the request's Authentication. Use a context-aware executor or explicit service identity/delegation.

Nor should you assume which thread executes `@PostAuthorize` when using `CompletableFuture` or reactive wrappers without testing the exact API; the value returned at the proxy may be the wrapper rather than the completed payload.

## 13. Testing with JUnit 5 and Spring Security Test

### 13.1. Tests should not just assert ALLOW, but measure body invocations

With `DocumentReadService` from section 6, a minimal test context:

```java
@SpringBootTest
class DocumentReadSecurityTest {

    @Autowired
    DocumentReadService service;

    @Test
    @WithMockUser(username = "alice",
                  authorities = "document:read")
    void ownerCanReadHerDocument() {
        DocumentView view = service.read("doc-a");

        assertThat(view.getOwnerId()).isEqualTo("alice");
        assertThat(view.getTitle()).isEqualTo("Draft of Alice");
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = "document:read")
    void readPermissionDoesNotGrantBobsDocument() {
        int before = service.getBodyCallsForTest();

        assertThatThrownBy(() -> service.read("doc-b"))
            .isInstanceOf(AccessDeniedException.class);

        assertThat(service.getBodyCallsForTest())
            .isEqualTo(before + 1);
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = "document:write")
    void missingReadPermissionBlocksBeforeBody() {
        int before = service.getBodyCallsForTest();

        assertThatThrownBy(() -> service.read("doc-a"))
            .isInstanceOf(AccessDeniedException.class);

        assertThat(service.getBodyCallsForTest()).isEqualTo(before);
    }
}
```

This is a **test-class fragment** needing JUnit, Spring Boot Test, Spring Security Test, AssertJ, `AccessDeniedException` imports, and `@EnableMethodSecurity` configuration. If tests run in parallel against the same singleton, `bodyCalls` could be incremented by another test: run sequentially/with isolated fixtures, or spy/mock the method with stable verification. Assertions do not depend on test order, though they assume no concurrent requests during measurement.

**Points to prove:**
- Test owner is allowed to read result.
- Test wrong owner: **body ran**, yet post-check denies.
- Test missing authority: **body did not run**, pre-check denies.

If you only test status 403, you may not know whether the block came from an HTTP filter, pre-check, post-check, or CSRF.

### 13.2. `@WithMockUser` creates direct authorities

```java
@WithMockUser(roles = "USER")
```

normally grants `ROLE_USER`, whereas:

```java
@WithMockUser(authorities = "document:read")
```

grants the exact permission string `document:read`. When testing `hasAuthority('document:read')`, use a matching direct permission fixture or a real role hierarchy graph; do not expect `ROLE_ADMIN` to automatically include `document:read` without a mapping.

`@WithMockUser` does not test JWT signatures, issuers, scope converters, or production session persistence. Integration tests with real tokens/sessions or matching security test support are needed.

### 13.3. Anonymous and wrong-role tests

```java
@Test
@WithAnonymousUser
void anonymousCannotRead() {
    assertThatThrownBy(() -> service.read("doc-a"))
        .isInstanceOf(AccessDeniedException.class);
}
```

This snippet only verifies the method pre-check against an anonymous fixture; with an HTTP controller, guests may receive 401/redirect instead of 403. Add a test for a user having `ROLE_ADMIN` without `document:read` to confirm the policy grants access intentionally by permission rather than granting admins everything automatically.

### 13.4. Testing null and not-found results

With the sample implementation, `read("missing")` throws `NoSuchElementException` **after passing the pre-check yet before a normal result exists**. Test to distinguish:
- User missing permission + missing ID: normally denied by pre-check before lookup.
- User with permission + missing ID: method throws not found.
- User with permission + existing ID but wrong owner: denied by post-check.

Any difference between HTTP 404 and 403 can reveal object existence; decide the API contract per anti-enumeration and test separately.

### 13.5. Testing the real Spring proxy

Never do:

```java
var service = new DocumentReadService();
service.read("doc-b");
```

and conclude annotations don't work. An object created with `new` is not a Spring-proxied bean. Tests must inject `DocumentReadService` from the application context or set up an appropriate method-security context; ensure `@EnableMethodSecurity` and Spring AOP are active. A **negative canary** helps detect if annotation processing was disabled.

### 13.6. Testing the policy bean and multi-tenancy

For `@documentReadPolicy.canReturn(...)`:
1. Actor in org-1 reading an org-1 doc they own → allow.
2. Actor in org-1 reading another user's org-1 doc without share/ACL → deny.
3. Actor in org-1 reading an org-2 doc → deny, even with valid ID.
4. Actor whose membership/permission was revoked → deny.
5. Actor with `document:read` but null view → fail closed.
6. Actor with a valid share grant for the specific doc → allow.
7. Token/admin scope in tenant A does not automatically unlock tenant B.
8. Owner changes between pre-check and post-check → logic follows trusted state; consider consistency/races.

Unit-test the policy bean with a fake repository across the decision matrix; integration-test with the Spring proxy to ensure the annotation invokes the right bean at runtime.

## 14. MockMvc: protecting HTTP output and preventing data leaks

### 14.1. Endpoint calling service through a bean

Controller fragment:

```java
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentReadService service;

    public DocumentController(DocumentReadService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DocumentView find(@PathVariable String id) {
        return service.read(id);
    }
}
```

This is a **Spring MVC fragment**; with an appropriate `SecurityFilterChain` and default exception translation, a denied result is never serialized as a successful JSON response.

### 14.2. MockMvc result-denied test

```java
@Test
@WithMockUser(username = "alice",
              authorities = "document:read")
void cannotDownloadBobsDocument() throws Exception {
    mockMvc.perform(get("/api/documents/doc-b"))
            .andExpect(status().isForbidden());
}
```

Expecting 403 applies when the mock request traverses a real `SecurityFilterChain`, has a handler, passes the pre-check, fails the post-check, and no custom exception handler alters the status. If using `@WebMvcTest`, import the service and method-security configuration properly; otherwise, the test slice may omit interceptors and give misleading results.

### 14.3. Do not check HTTP status alone

Also verify:

- The JSON body of the deny response **does not contain** `Review of Bob` or sensitive `ownerId`/`tenantId`.
- Tracing/logging middleware does not record the serialized denied result.
- Response/CDN caches do not store Bob's result under a key shared with Alice.
- Repository/business logs do not print confidential content before the post-check.
- If a method has side effects, test that a denied request **does not** modify the DB or send events/emails; if it fails, redesign toward pre-checks.

### 14.4. 403 does not guarantee it was `@PostAuthorize`

Before using body invocation counters to prove the post-check, verify:
- The HTTP rule lets the test principal through.
- `hasAuthority('document:read')` actually passes.
- The method call reaches the proxied bean.
- The method body returns a `DocumentView`.
- The post-check policy is actually what denies.

If CSRF is missing on a POST request, or an HTTP matcher denies early, 403 does not prove `@PostAuthorize` works.

### 14.5. Testing actual authentication mapping

With a JWT Resource Server, test a token verified for signature/audience/issuer or test the converter using standard test support. Ensure the `document:read` authority is genuinely produced; `@WithMockUser` only tests simulated policies. Test logout/revocation/tenant membership according to your product's threat model.

## 15. Standalone Java 17 example: illustrating pre → body → post

The program below **does not use Spring**. It simulates the three stages to show clearly:
- pre-check fails → document is not retrieved;
- pre-check passes, yet owner mismatches → data was read internally, result is denied;
- both pass → content is received;
- not found → handled as a separate “not found” outcome;
- Java only returns demo labels, not HTTP statuses or Spring exceptions.

Create `PrePostAuthorizationDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class PrePostAuthorizationDemo {

    record Caller(String name, Set<String> authorities) {}
    record Document(String id, String owner, String title) {}

    private static final Map<String, Document> DOCUMENTS = Map.of(
            "doc-a", new Document(
                    "doc-a", "alice", "Draft of Alice"),
            "doc-b", new Document(
                    "doc-b", "bob", "Review of Bob")
    );

    private static int bodyCalls;

    private static boolean preCheck(Caller caller) {
        return caller != null
                && caller.authorities().contains("document:read");
    }

    private static Document methodBody(String id) {
        bodyCalls++;
        return DOCUMENTS.get(id);
    }

    private static boolean postCheck(
            Caller caller, Document returned) {
        return returned != null
                && returned.owner().equals(caller.name());
    }

    private static String read(Caller caller, String id) {
        if (!preCheck(caller)) {
            return "PRE_DENY";
        }

        Document returned = methodBody(id);
        if (returned == null) {
            return "NOT_FOUND";
        }

        if (!postCheck(caller, returned)) {
            return "POST_DENY";
        }
        return "ALLOW:" + returned.title();
    }

    private static void show(
            String label, Caller caller, String id) {
        int before = bodyCalls;
        String result = read(caller, id);
        int bodyDelta = bodyCalls - before;
        System.out.println(label + "=" + result
                + ";bodyCalls=" + bodyDelta);
    }

    public static void main(String[] args) {
        Caller alice = new Caller(
                "alice", Set.of("document:read"));
        Caller bob = new Caller(
                "bob", Set.of("document:read"));
        Caller writerOnly = new Caller(
                "alice", Set.of("document:write"));
        Caller adminOnly = new Caller(
                "admin", Set.of("ROLE_ADMIN"));

        show("alice-own", alice, "doc-a");
        show("alice-bob", alice, "doc-b");
        show("bob-own", bob, "doc-b");
        show("bob-alice", bob, "doc-a");
        show("alice-writer-only", writerOnly, "doc-a");
        show("admin-without-read", adminOnly, "doc-a");
        show("alice-missing", alice, "missing");
        show("anonymous", null, "doc-a");

        System.out.println("total-body-calls=" + bodyCalls);
    }
}
```

Compile and run with JDK 17+:

```bash
javac PrePostAuthorizationDemo.java
java PrePostAuthorizationDemo
```

**Deterministic stdout following the synchronous program flow:**

```text
alice-own=ALLOW:Draft of Alice;bodyCalls=1
alice-bob=POST_DENY;bodyCalls=1
bob-own=ALLOW:Review of Bob;bodyCalls=1
bob-alice=POST_DENY;bodyCalls=1
alice-writer-only=PRE_DENY;bodyCalls=0
admin-without-read=PRE_DENY;bodyCalls=0
alice-missing=NOT_FOUND;bodyCalls=1
anonymous=PRE_DENY;bodyCalls=0
total-body-calls=5
```

### 15.1. Explaining the output

- Alice reads `doc-a`: permission and owner both match → allowed.
- Alice reads `doc-b`: permission passes, body is called, yet owner is Bob → post deny.
- Bob reads `doc-b` and `doc-a` with symmetric results.
- Alice only has `document:write`: pre deny → body does not run.
- Admin has `ROLE_ADMIN` without `document:read` or mapping/hierarchy → pre deny per demo policy. **Never assume ADMIN automatically has every permission.**
- Missing ID: pre passes and body runs, yet no record exists; demo returns `NOT_FOUND`. In real Spring, a domain exception can be thrown so HTTP returns 404.
- Null caller: pre deny, body does not run.
- Total `bodyCalls=5` because Alice/Bob had read permission four times plus one lookup for a missing ID, matching the flow.

### 15.2. Limitations of the program

- No Spring `@PreAuthorize`/`@PostAuthorize`/SpEL/proxy.
- No Servlet filters, HTTP statuses, JWT validation, sessions, or CSRF.
- No database, transactions, ORM, tenant scope, ACL, or auditing.
- Uses an immutable in-memory `Map`; body only reads, never writes data.
- `PRE_DENY`/`POST_DENY` labels are defined by this lesson, **not** built-in `AuthorizationResult` types or HTTP codes.
- Its sole goal is clarifying that post-checks occur **after** the method body is invoked.

## 16. Advanced scenarios and architectural choices

### 16.1. Must `@PreAuthorize` and `@PostAuthorize` always be paired?

No. If `findByIdAndOwnerId(id, actorId)` already enforces object scope using a trusted identity and the service only returns an authorized DTO, `@PreAuthorize("hasAuthority('document:read')")` plus the repository check may be sufficient. An added post-check is optional defense in depth depending on business needs.

Conversely, a read method whose output depends on multiple post-load conditions can benefit from `@PostAuthorize`, provided it has no side effects and data is not leaked internally before the check.

**Do not apply both annotations as a mandatory template for every method**. Choose based on when trusted information is available and the risk of executing the body.

### 16.2. Is a pre-check by object ID enough?

If `canRead(authentication, #id)` already queries real owner/tenant from the DB, it can deny upfront so the body does not load sensitive unauthorized data. Still, if status/ownership changes after the pre-check, the body may read the new state; a post-check or scoped query/transaction consistency can help. For writes, always verify at mutation time.

### 16.3. Post-checks on cached data

If the body reads from a shared cache, the value could belong to another user if the cache key omits tenant/actor. A post-check can deny returning it to the caller, yet the cache still holds an object loaded/stored under the wrong scope, and another unguarded path could expose it.

Design cache keys around tenant/object/policy visibility or cache raw data only inside a trusted boundary, and check permissions **before** exposing responses. Never treat `@PostAuthorize` as a cure for cache isolation bugs.

### 16.4. Custom denied-result handling

Recent Spring Security versions offer mechanisms like `@HandleAuthorizationDenied` and `MethodAuthorizationDeniedHandler` to customize behavior on denial. This is **opt-in/version-specific behavior**, not the default. If a project uses a return-null/masked-result handler, tests must verify:
- The real object is not leaked.
- A post-deny is not accidentally turned into returning the whole object.
- The caller receives a signal/response matching the contract.
- Custom handlers do not suppress denial logging/auditing.

Never use masking mechanisms as an excuse to let a write operation run before checking permissions.

### 16.5. `@PostFilter` and `@AuthorizeReturnObject` differ from `@PostAuthorize`

- `@PostAuthorize`: evaluates the entire **return value** after the method and allows/denies returning it.
- `@PostFilter`: filters collection elements via an expression; has consequences for already-loaded data/pagination and should not replace scoped DB queries.
- `@AuthorizeReturnObject` (modern mechanism): can proxy a returned object to apply method security to members/getters of that object; not an alias for `@PostAuthorize`.

These APIs have distinct boundaries and version requirements. This lesson focuses on **combining pre + post checks on a single method invocation**; when field-level redaction or collection filtering is needed, pick the right mechanism and test it separately.

### 16.6. Object authorization via `PermissionEvaluator`

Some projects use `hasPermission(#id, 'Document', 'read')` with a `PermissionEvaluator`/ACL service inside `@PreAuthorize`. This can check object-level permissions **before the body**, avoiding sole reliance on post-checks. It requires a configured `PermissionEvaluator` and trusted data sources, not a built-in function that magically works for every app.

Fragment example:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "hasPermission(#id, 'Document', 'read')"
)
public DocumentView read(String id) { /* ... */ }
```

If lookup uses a global ID while resources are tenant-scoped, the evaluator must still check tenant/ACL; never rely on a generic “USER” role for every object.

## 17. Common errors and fixes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Both `@PreAuthorize` and `@PostAuthorize` exist yet method is not blocked | Method security not enabled or not called via proxy | `@EnableMethodSecurity`, test injected bean |
| Having `document:read` lets you read Bob's document | Missing object-level rule or post-check didn't run | Test owner/tenant, verify interceptor |
| HTTP 403 yet DB deleted the document | Post-check denied after write | Move authorization to pre/service/guarded DB write |
| `@Transactional` assumed to always roll back post-deny | Complex advisor ordering and side effects | Redesign write; test real transactions |
| SpEL `returnObject.ownerId` errors | Return type lacks `ownerId`, null/Optional | Pick right property and null guard; policy bean |
| `@PreAuthorize` cannot see `returnObject` | Result does not exist yet before body | Use params/DB policy in pre, result in post |
| `@PostAuthorize` cannot see method parameter | Missing `#id` name/discovery | Enable `-parameters` or `@P` |
| `@WithMockUser` ADMIN gets denied | Role does not auto-map permissions | Grant/map exact authority, test `RoleHierarchy` |
| Principal name differs from UUID `ownerId` | Comparing two incompatible ID types | Trusted actor resolver |
| Checking only `pathTenantId` vs. `bodyTenantId` | Both strings are client-controlled | Read real membership and record tenant |
| Wrong owner denied yet audit log contains Bob's data | Body logged before post-check | Never log sensitive data; pre-scope query |
| 403 test passes even without method security | 403 came from HTTP/CSRF | Test direct service proxy and `bodyCalls` |
| `@PostAuthorize` on Optional/List fails | `returnObject` is wrapper/collection | Use type-appropriate policy, scoped DB query |
| Self-invocation skips annotations | Spring AOP proxy bypassed | Separate service boundary or AspectJ/tests |
| JWT resource server has scope yet SpEL misses it | Authority prefix `SCOPE_`/different mapping | Test `JwtAuthenticationConverter` |
| Background task lacks context | ThreadLocal doesn't follow raw executors | Context-aware executor/service identity |
| Guest reaches service yet HTTP route gives 401 | HTTP `SecurityFilterChain` requires auth | Review HTTP and method layers separately |
| User sees some secret fields despite post-check allow | `@PostAuthorize` does not mask individual fields | Response DTO allowlist/field policy |
| Denied post-check returns unexpected masked value | Custom denied handler/version behavior | Test custom handler and zero result leakage |
| 403 error reveals object exists | 403 vs. 404 differs for foreign IDs | Scoped lookup, anti-enumeration contract |
| Owner changes between check and use | TOCTOU | Transactions/locking/guarded updates |
| Method body throws exception yet test expects post result | No normal return result exists | Test exception path separately |

### Seven-step debugging workflow

1. Verify the actual user/principal/authorities (without printing raw tokens).
2. Verify Spring method security is enabled and the service is a Spring-managed proxy.
3. Classify whether the block came from an HTTP filter, pre-check, body exception, or post-check.
4. If pre-denied, check role/permission and actor/parameter policies.
5. If post-denied, check result type/null/ownerId/tenant and policy bean.
6. If it is a write operation, immediately inspect the database/side effects, not just the response.
7. Test against the real Spring/`SecurityFilterChain` runtime, not manually instantiated Java classes.

## 18. Architecture checklist, testing checklist, and self-check questions

### 18.1. Pre-production checklist

**Configuration**
- [ ] `@EnableMethodSecurity` genuinely activates both pre and post advisors.
- [ ] Methods are called through Spring-managed proxies, never via `this.inner()`.
- [ ] `@PreAuthorize` checks permissions/roles from a trusted Authentication source.
- [ ] `@PostAuthorize` checks the exact result type carrying needed ownership/tenant data.
- [ ] `authentication.name` is used only when matching the internal actor ID; otherwise an `ActorResolver` is used.
- [ ] Returned DTOs do not expose unauthorized fields.
- [ ] HTTP matchers/authentication/CSRF are tested independently of method security.

**Policy**
- [ ] Client-supplied tenant selectors/paths are checked against real membership and target tenant.
- [ ] Owner/ACL are fetched from DB/trusted services, never trusting body `ownerId`.
- [ ] Functional permissions and per-object permissions are clearly separated.
- [ ] Pre-checks prevent running the body for users lacking permissions.
- [ ] Post-checks are never treated as a rollback barrier for writes/deletes.
- [ ] Side effects only occur after proper authorization and transaction/DB guards.
- [ ] An anti-enumeration policy exists for 403/404 on out-of-scope documents.

**Tests**
- [ ] Pre-deny → body does not run.
- [ ] Post-deny → body ran yet return result does not leak.
- [ ] Pre+post allow → returns exact object.
- [ ] Missing record/null → valid exception handling without crashing SpEL.
- [ ] Anonymous, wrong role, wrong authority, stale JWT, and different tenant.
- [ ] Test HTTP and service proxy independently, checking CSRF if method writes.
- [ ] Test that side effects do not occur when write commands are denied.
- [ ] Test concurrent ownership/membership changes if data can mutate.
- [ ] Test lists/pages/Optional returning the right contract if used.
- [ ] Test on the real Spring Security version and custom denied handlers if any.

### 18.2. Self-check questions

**Q1.** A method has `@PreAuthorize` and `@PostAuthorize`. Is that OR or AND?

**Answer:** Both checks are applied sequentially and both must allow for a successful return, so the outcome is effectively AND. However, post only runs after the body; they do not both run before the body.

**Q2.** If the pre-check denies, does the body run?

**Answer:** Not under default method-security interception when called through a proxy. If the body still runs, check proxy wiring, method-security config, and self-invocation paths.

**Q3.** Pre allows, body updates the DB, post denies. Is rollback guaranteed?

**Answer:** No. Transaction ordering and side-effect sources determine that; never use a post-check as a write-protection mechanism. Check before mutating and enforce DB constraints.

**Q4.** What is `returnObject`?

**Answer:** The value the method actually returns after successful execution, before it is handed to the caller through the proxy. Its type must match the SpEL expression or be handled by a policy bean.

**Q5.** Does `returnObject.ownerId == authentication.name` always verify the right owner?

**Answer:** No. You need `ownerId` from server data and `authentication.name` matching the internal actor ID type; otherwise use an actor resolver + policy bean.

**Q6.** Why shouldn't `@PostAuthorize` be used as the final check on an email-sending command?

**Answer:** The email may already have been sent when the post-check runs, and cannot be recalled merely by throwing `AccessDeniedException`. Pre-checks and domain policies are required before external side effects.

**Q7.** A method returns `Optional<DocumentView>`. Can you write `returnObject.ownerId` just like a normal `DocumentView`?

**Answer:** You should not. The return value is a wrapper; use a policy that understands Optional or change the API contract. Test null/empty/present separately.

**Q8.** Does a `@PostAuthorize` deny automatically scrub secret data from shared caches/logs?

**Answer:** No. The body already ran; avoid caching/logging/emitting unverified data, and use scoped queries and DTO allowlists.

**Q9.** Does a user with `ROLE_ADMIN` automatically satisfy `hasAuthority('document:read')`?

**Answer:** Not by default. It requires a direct authority, mapping, or `RoleHierarchy` applied by the handler.

**Q10.** Why is testing status 403 insufficient to prove the post-check is running?

**Answer:** 403 can come from an HTTP filter, CSRF, or pre-check. You must test the proxied service and measure body calls/policy verification.

**Q11.** For tenant-scoped data, is checking `returnObject.ownerId` alone enough?

**Answer:** No, if an owner can belong to multiple tenants, if shared ACLs exist, or if tenant boundaries are independent. Policies must verify tenant, membership, and object scope.

**Q12.** Is a method called via `this.method()` inside the same bean protected by both pre and post?

**Answer:** Likely not in Spring AOP proxy mode. Call through a bean proxy and design service boundaries properly.

**Q13.** Why is `@PostAuthorize` not synonymous with `@PostFilter`?

**Answer:** PostAuthorize evaluates the entire result for allow/deny. PostFilter filters elements of a collection; the two mechanisms are not interchangeable.

**Q14.** When can a read-only method use both pre and post?

**Answer:** When pre checks permissions/state before querying, and post checks real ownership/tenant determinable only from the result; ensure the method has no sensitive side effects and the policy operates on trusted objects.

**Q15.** If `@PreAuthorize` already checks permission by ID from the DB, is `@PostAuthorize` mandatory?

**Answer:** No. If scoped queries and policies are already complete, post may only be defense in depth; weigh consistency, query cost, and threat model.

**Q16.** Getting 403 from a post-check—should you fix it by returning null instead of throwing an exception?

**Answer:** Only if the API policy explicitly designs denied-result handling; you must check for data leakage and ensure callers understand the contract. Never use masking/null to hide authorization bugs.

### 18.3. Summary

**`@PreAuthorize` and `@PostAuthorize` complement each other but are not interchangeable.**

- `@PreAuthorize`: checks beforehand, preventing users lacking permissions from entering the method.
- `@PostAuthorize`: checks the result after the body ran, able to block returning out-of-scope objects.
- Combined: **both checks must pass** to receive the result; however, a post-check does not automatically undo what the method already did.
- Protecting real data: verify identity and functional permissions from Spring Security; owner, tenant, ACL from server data; all write commands should have pre-checks and transaction/DB invariants.
- Testing: include negative cases and prove **whether the body ran or not**, **no result leaked**, and **no side effects occurred** on writes.

## References

- Spring Security — Method Security, `@PreAuthorize` + `@PostAuthorize` sequence, AND semantics, `returnObject`, and write/transaction warnings: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0 — Method Security: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security — Authorization Architecture, roles and `GrantedAuthority`: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — `SecurityContextHolder` and `Authentication`: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Method security testing: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Framework — Declarative Transaction Management and transaction advisor: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- OWASP — Broken Object Level Authorization (API1:2023): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
