# The Boundary Between Method Protection and Emitted Data Protection in Spring Security Reactive

## 1. The Problem: Permission to Call a Method Does Not Mean Permission to Receive Every Record

Suppose Alice is allowed to use the document-viewing feature. A WebFlux API calls a service returning `Flux<DocumentView>` with multiple documents. The annotation below checks one condition **at the method level**:

```java
@PreAuthorize("hasAuthority('document:read')")
public Flux<DocumentView> listDocuments() {
    return documentRepository.findAll()
        .map(DocumentView::from);
}
```

Alice holds the `document:read` authority, so the call clears the gate. However, `findAll()` may emit documents belonging to Bob or other tenants. **Being allowed to execute a method** does not mean **every value the method emits** may be sent to the caller.

This is the core boundary of this **Reactive Method Security** lesson:

- **Invocation authorization:** is the caller allowed to invoke `listDocuments`?
- **Result authorization:** may the returned value be disclosed to the caller?
- **Per-element authorization:** does each element of the `Flux` satisfy the caller's permissions?
- **Data-source authorization:** does the database, search index, or file store itself select only data the caller is allowed to see?
- **Output authorization:** is the data actually leaving the application via HTTP body, SSE, WebSocket, or another sink properly restricted?

These five layers are related yet **cannot substitute for one another**. Spring Security provides `@PreAuthorize`, `@PostAuthorize`, `@PostFilter`, and reactive method interceptors; applications still must design tenant-scoped queries, object-level permissions, field-level projections, streaming security, and tests proving **no unauthorized data is ever emitted**.

### Expected Outcomes

After this lesson, you will be able to:

1. State clearly what is and is not protected by `@PreAuthorize` with `Mono` and `Flux`.
2. Distinguish `@PostAuthorize`, `@PostFilter`, `Flux.filterWhen`, and filtering directly in SQL.
3. Explain the timing of method invocation, subscription, emission, and HTTP serialization.
4. Design REST detail, list, search, pagination, and streaming endpoints scoped strictly to readable data.
5. Know why post-checks are unsuitable for guarding writes that already produced side effects.
6. Keep `Authentication`/tenant in Reactor Context and avoid bypassing Spring AOP proxies.
7. Test counts, contents, ordering, errors, and sensitive fields across every emitted element.
8. Run a standalone Java 17 example demonstrating a permitted method whose returned dataset still requires filtering.

## 2. Reactive Specifics: Returning a Publisher Does Not Mean I/O Has Run

In Reactor, `Mono<T>` represents at most one value and `Flux<T>` represents `0..N` values. Many `Publisher`s are **cold**: creating and returning a `Flux` does not mean the DB query has run; the query normally starts when a subscriber subscribes.

Conceptual diagram:

```text
Authenticated HTTP request
        |
        v
Spring-managed service proxy
        |
        v
@PreAuthorize -> check if method may be invoked?
        |
   DENY +---> do not execute protected pipeline
        |
      ALLOW
        |
        v
Service returns Mono<T> / Flux<T>
        |
        v
Subscriber starts receiving data
        |
        v
DB / remote source emits items
        |
        +--> @PostAuthorize / @PostFilter / app operator (if present)
        |
        v
DTO serialization / HTTP response / SSE
```

This is a mental model, **not an exact AOP signal-ordering diagram across every version**. Configuration and return type determine precisely how reactive checks are woven into the publisher. Claims should be verified with integration tests rather than guessing that method body code ran completely before annotations were evaluated.

### Distinguishing Four Moments

| Moment | Meaning | Common Misconception |
| --- | --- | --- |
| **Invocation** | Calling the method through the Spring proxy | Does not mean DB data has been loaded |
| **Publisher assembly** | Building the operator chain and returning the `Publisher` | Tasks outside the `Publisher` can still run immediately |
| **Subscription / request demand** | Framework subscribes and requests elements | Cold `Publisher` I/O usually starts here |
| **Emission / serialization** | Items are sent to subscriber/HTTP body | Already-sent items cannot be "recalled" from the client |

With a long-lived `Flux` or SSE stream, **several seconds or minutes** may separate the first item from the last. The caller's permissions can be revoked during that window. An initial allowance at stream start does not automatically mean future items remain valid under business rules.

### Example of a Publisher Assembly Bug

```java
public Mono<Document> wrong(Long id) {
    auditRepository.saveBlocking("READ_ATTEMPT"); // runs synchronously immediately
    return documents.findById(id);
}
```

This is an **anti-pattern**: the side effect occurs when the method body runs, outside the reactive source where transactions and cancellation govern it. Never assume that merely returning `Mono` makes all preceding code wait for subscription. In WebFlux, blocking calls can also stall the event loop.

## 3. Mechanisms Provided by Spring Security

Spring Security Reactive documentation describes method security built on `ReactiveSecurityContextHolder`, Reactor Context, and Spring AOP. On supported Spring Security versions, enable it with:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveMethodSecurityConfig {
}
```

**Precondition:** the project must use a Spring Security dependency matching this API. Official docs note `useAuthorizationManager=true` has been supported since Spring Security 5.8. Check JavaDoc and run compile tests for your specific version; some customization APIs and syntax differ between 6.x and 7.x.

Key annotations:

| Annotation | Control Layer | Typical Scope |
| --- | --- | --- |
| `@PreAuthorize` | Before entering invocation/pipeline | Principal has required role/action/permission |
| `@PostAuthorize` | Post-check on the method result | Permission on the returned object, e.g. owner |
| `@PreFilter` | Filters elements in supported inputs | Batch inputs that may contain invalid objects |
| `@PostFilter` | Filters elements in supported result sets | Drops items the caller cannot view |
| Reactive policy in service | Actively decides during `Publisher` execution | Complex membership, ACL, time, tenant, state rules |
| Scoped repository query | Constrains right at DB read time | Fetches only scoped and authorized rows |
| Response DTO | Protects emitted fields | Never exposes sensitive internal columns |

**Keep distinct:** `@PreAuthorize` controls whether the method may be called, whereas `@PostFilter` per the filtering contract filters individual items; **never treat `@PostAuthorize` as automatic pagination or filtering across every item in a `Flux`**. Reactive interceptor implementations exist depending on version, yet you must write integration tests for your **exact return type (`Mono`, `Flux`, collection) and annotation**.

Recent Spring Security docs list `AuthorizationManagerBeforeReactiveMethodInterceptor`, `AuthorizationManagerAfterReactiveMethodInterceptor`, and `PostFilterAuthorizationReactiveMethodInterceptor` when `AuthorizationManager` mode is active. That confirms the mechanism exists, yet **does not guarantee any given expression satisfies your domain or tenant rules**.

### When to Use Which?

- **Before calling:** require an authenticated user with the functional authority (`@PreAuthorize`).
- **Single object:** enforce ID/tenant in the query and optionally post-check owner/ACL with `@PostAuthorize` as an extra layer.
- **Large lists:** constrain permissions in the DB query **before pagination**, rather than loading every object and using `@PostFilter`.
- **Small in-memory lists:** `@PostFilter` can be useful if compatible with your return type and version.
- **Long-lived `Flux`:** evaluate per item or batch along with revocation, cancellation, and error/partial-response requirements.
- **Mutations:** pre-check plus conditional database updates and transactions; never rely on `@PostAuthorize` to block side effects.

## 4. Crucial Question: Are You Protecting the Method or Each Item?

The snippet below enforces a **coarse-grained permission** while lacking data authorization:

```java
@PreAuthorize("hasAuthority('document:read')")
public Flux<DocumentView> allDocuments() {
    return documents.findAll()
        .map(this::toView);
}
```

If `findAll()` emits 100 rows across multiple tenants, the role check filters out none of them. A principal holding `document:read` only has permission to use the read feature under policy—not necessarily ownership or share grants for every document.

Adding `@PreAuthorize("hasRole('ADMIN')")` blocks non-admins, yet if that admin is only authorized **within tenant A**, tenant B data can still leak.

You need a decision model like:

```text
canView(subject, document, READ, context) =
    authenticated(subject)
    AND accountActive(subject)
    AND memberOf(subject, verifiedTenant)
    AND hasTenantAction(subject, verifiedTenant, READ)
    AND document.tenantId == verifiedTenant
    AND document.active
    AND (owner(subject, document) OR activeReadGrant(subject, document))
```

A list screen must return **only documents satisfying this predicate**, not merely check that `document:read` appears in the caller's authorities.

### Subject and Resource Facts Must Be Trustworthy

- Derive `subject` from verified `Authentication`, never from a client-sent `X-User-Id` header.
- Any tenant in a URL/header is a **selector**; verify membership before using it.
- Load document owner/tenant/status from the database or a trusted resource store, never from client JSON.
- Validate share grants for recipient, object, action, validity window, and revocation.
- If a mandatory condition cannot be verified, **never grant access** just because an upstream service timed out.

## 5. `@PreAuthorize` in Reactive Services: Guarding the Front Door

A coarse-grained HTTP configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class HttpSecurityConfig {
    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/documents/**").authenticated()
                .anyExchange().denyAll()
            )
            .build();
    }
}
```

This is a **config fragment** for WebFlux without JWT/HTTP Basic/CSRF/CORS setup; wire in your project's authentication mechanism. `authenticated()` here is merely a coarse rule at the HTTP layer.

Service:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
class DocumentService {
    private final DocumentRepository repository;

    DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('document:read')")
    Flux<DocumentView> listDocuments() {
        return repository.findAll()
            .map(d -> new DocumentView(d.getId(), d.getTitle()));
    }
}
```

**This example intentionally lacks data-scope checks** and must never be used as-is in production. It requires entities, repositories, and DTOs, and methods may need to be `public` depending on proxy mode and call paths; package-private methods can behave unexpectedly depending on proxy strategy, so the secure service version below uses explicit `public` methods.

### Consequences of Misunderstanding

If QA tests only:

```text
Anonymous -> 401
Alice with document:read -> 200
Bob without document:read -> 403
```

the endpoint can still leak other tenants' documents inside the `200` body. Accurate tests must assert **returned IDs, tenant IDs, field projections, and absent records**. Checking status codes alone is insufficient.

## 6. `@PostAuthorize`: Post-Checking a Single Object, Never for Guarding Writes

For a single object like `Mono<DocumentView>`, you can add a post-check:

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OwnedDocumentService {
    private final DocumentRepository documents;

    public OwnedDocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize("returnObject.ownerSubjectId == authentication.name")
    public Mono<DocumentView> read(Long documentId) {
        return documents.findById(documentId)
            .map(d -> new DocumentView(
                d.getId(), d.getTenantId(),
                d.getOwnerSubjectId(), d.getTitle()));
    }
}
```

**Illustrative Spring component**: requires entity, repository, DTO, and reactive method security config, and `DocumentView` must expose `ownerSubjectId` accessible to SpEL under actual runtime mapping. For records, test accessor mapping; projects may use JavaBean getters or a policy bean. If `authentication.name` differs from internal IDs, owner expressions will fail; map subject IDs explicitly.

Intended meaning: return the object only if the caller owns it. Yet three problems remain:

1. **The repository already loaded the object before the post-check.** That may be necessary to read the owner, yet the data must not be logged, shared-cached, or sent to another sink prior to checking.
2. **Missing tenant scope.** Colliding owner IDs/issuer strings or cross-tenant documents can slip through if logic is too simplistic.
3. **Side effects.** Post-checks do not undo earlier actions, especially `INSERT`/`UPDATE`/`DELETE`, emitted events, emails, or storage uploads.

A stronger approach for detail endpoints is querying **matching tenant + owner/ACL** directly in the repository, mapping to a DTO only after authorization is proven. `@PostAuthorize` can act as defense-in-depth on results, yet **must never be the sole barrier** for sensitive data access.

### Anti-Pattern: Write First, Post-Check Afterward

```java
@PostAuthorize("returnObject.ownerSubjectId == authentication.name")
public Mono<DocumentView> changeTitle(
        Long documentId, String newTitle) {
    return repository.updateTitle(documentId, newTitle)
        .map(this::toView);
}
```

If an update already committed or an event fired upstream, a failing post-check **does not mean** the database automatically rolled back. Whether a reactive chain is transactional depends on real transaction boundaries and isolation; never rely on an annotation to stop an unauthorized write.

**Right direction:** verify permissions **before mutation**, and keep security predicates inside the update statement/transaction against races.

## 7. `@PostFilter`: Filtering Result Sets, Not a Query Optimizer

`@PostFilter` defines an expression evaluated per element. In the newer reactive method-security mode, Spring Security provides `PostFilterAuthorizationReactiveMethodInterceptor`; verify exact behavior with `Flux`/collections on your runtime version.

Conceptual example:

```java
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Flux;

@PreAuthorize("hasAuthority('document:read')")
@PostFilter(
    "filterObject.ownerSubjectId == authentication.name"
)
public Flux<DocumentView> myOwnedDocuments() {
    return repository.findAll()
        .map(this::toView);
}
```

This is a **method fragment** requiring a Spring-managed service, imports, DTO, repository, and compatible `@EnableReactiveMethodSecurity(useAuthorizationManager=true)`. Test `Flux` outputs directly to confirm the annotation applies rather than assuming from Servlet examples. In real role/ACL systems, comparing **only owner** still misses tenant, membership, share grants, and object state.

### Severe Limitations of Post-Filtering

Suppose the database holds 1,000,000 documents, and Alice can view only 10.

Loading all rows and filtering afterward:

```text
DB -> 1,000,000 rows -> JVM / Flux -> filter -> 10 rows
```

This:

- Wastes I/O, CPU, and memory.
- Can bring unauthorized data into application memory, logs, metrics, or caches before filtering.
- Causes N+1 queries if each item looks up an ACL individually.
- With `LIMIT 20` applied **before** filtering, can leave 0–2 items on a page even when many valid objects exist further down.
- Leaks unauthorized document counts via pagination `count`/`totalElements`.
- Leaks out-of-scope stats via sorting, aggregations, and search facets.
- Does not perform per-field redaction.
- Wastes upstream bandwidth on long-lived streams while filtering per item.

**Conclusion:** `@PostFilter` is a **supplementary guard** for small datasets, never a replacement for tenant/owner/ACL predicates at the database layer.

## 8. Three Design Patterns for `Mono`, `Flux`, and Large Datasets

| Return Shape | Primary Control | Appropriate Extra Layer |
| --- | --- | --- |
| `Mono<Document>` by ID | Query by resource ID + verified tenant + owner/ACL | `@PreAuthorize`, `@PostAuthorize`, or service policy |
| `Flux<Document>` list | Permission-filtered query before pagination | `@PreAuthorize`, per-element checks where needed |
| Long-lived `Flux<Event>` SSE | Policy at subscribe time and per emission if required | Cancellation/revocation signals, bounded caches |
| `Flux<ByteBuffer>` download | Block **before sending** file bytes | Quotas, expiry, rate limiting, stream-time policies |
| `Mono<PageDto>` | Both `COUNT` and `SELECT` carry permission predicates | Check DTO fields and total counts |
| `Mono<CommandResult>` write | Pre-check + conditional SQL mutation | Transactions, optimistic/pessimistic locking |
| Message/WebSocket output | Authorization at message/service layer | Recheck when scope, tokens, or grants change |

No single annotation handles every stream shape cleanly. Object permissions may be static within one request or change every second depending on domain requirements.

## 9. Reactive Repositories: Filtering Permissions Directly in SQL/R2DBC

Suppose the tables are:

```text
tenant_memberships(
  tenant_id, subject_id, active, can_read_documents
)
documents(
  id, tenant_id, owner_subject_id, title, deleted, classification
)
document_share_grants(
  id, document_id, tenant_id, recipient_subject_id,
  permission, valid_from, expires_at, revoked_at
)
```

A Spring Data R2DBC repository:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface DocumentRepository
        extends ReactiveCrudRepository<DocumentEntity, Long> {

    Flux<DocumentEntity>
    findByTenantIdAndOwnerSubjectIdAndDeletedFalseOrderByIdAsc(
        String tenantId, String ownerSubjectId);

    Mono<DocumentEntity>
    findByIdAndTenantIdAndDeletedFalse(
        Long id, String tenantId);
}
```

This is a **repository fragment** requiring a matching R2DBC `DocumentEntity`, connection factory, and schema. `findByIdAndTenantIdAndDeletedFalse` enforces **tenant isolation** only, not owner verification if called arbitrarily. Domain services must enforce owner/ACL checks.

An equivalent predicate for an owner list:

```sql
SELECT id, tenant_id, owner_subject_id, title
FROM documents
WHERE tenant_id = :verified_tenant
  AND owner_subject_id = :authenticated_subject
  AND deleted = FALSE
ORDER BY id;
```

**Important:** both `:verified_tenant` and `:authenticated_subject` must originate from verified sources and be passed as bind parameters. Changing `tenantId` in the URL path must never grant access to another tenant.

### With Share Grants

An SQL query can also include documents with active READ shares:

```sql
SELECT d.id, d.tenant_id, d.owner_subject_id, d.title
FROM documents d
JOIN tenant_memberships m
  ON m.tenant_id = d.tenant_id
 AND m.subject_id = :subject
WHERE d.tenant_id = :verified_tenant
  AND d.deleted = FALSE
  AND m.active = TRUE
  AND m.can_read_documents = TRUE
  AND (
       d.owner_subject_id = :subject
       OR EXISTS (
           SELECT 1
           FROM document_share_grants g
           WHERE g.document_id = d.id
             AND g.tenant_id = d.tenant_id
             AND g.recipient_subject_id = :subject
             AND g.permission = 'READ'
             AND g.revoked_at IS NULL
             AND g.valid_from <= :now_utc
             AND g.expires_at > :now_utc
       )
  )
ORDER BY d.id
LIMIT :page_size OFFSET :offset;
```

This is **logical SQL**, not an auto-generated schema or framework query. Add `classification`, project, or owner-state conditions if required by your domain, and ensure unique memberships or handle duplicate rows. `:now_utc` must come from a trusted clock; exact expiry is excluded via `expires_at > now`.

**Never infer from this SQL that every user with READ membership can view the entire tenant.** The final `AND` branch still restricts to owner or share grant. If your product has folder-level ACLs or group relationships, add those branches under controlled policy.

### `COUNT` Must Use the Exact Same Predicate

```sql
SELECT COUNT(*)
FROM documents d
JOIN tenant_memberships m
  ON m.tenant_id = d.tenant_id
 AND m.subject_id = :subject
WHERE d.tenant_id = :verified_tenant
  AND d.deleted = FALSE
  AND m.active = TRUE
  AND m.can_read_documents = TRUE
  AND (
       d.owner_subject_id = :subject
       OR EXISTS (
           SELECT 1
           FROM document_share_grants g
           WHERE g.document_id = d.id
             AND g.tenant_id = d.tenant_id
             AND g.recipient_subject_id = :subject
             AND g.permission = 'READ'
             AND g.revoked_at IS NULL
             AND g.valid_from <= :now_utc
             AND g.expires_at > :now_utc
       )
  );
```

A list with 10 valid items yet `totalElements=10,000,000` (tenant-wide) still leaks information. The `COUNT` query and `SELECT` query must share **the exact same scope policy**. If both queries run in separate transactions, data can change in between; define acceptable snapshot consistency rather than assuming `COUNT` always equals the exact current row list.

## 10. A Reactive Service Enforcing Both Invocation and Data Access

The snippet below represents **Spring Boot WebFlux + Spring Security + R2DBC components**, not a standalone `javac` program. `VerifiedSubjectService`, `TenantPermissionService`, `DocumentEntity`, and `DocumentRepository` must be supplied by the application per contract.

A combined service:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class TenantDocumentReadService {
    private final VerifiedSubjectService subjects;
    private final TenantPermissionService tenantPermissions;
    private final DocumentRepository documents;

    public TenantDocumentReadService(
            VerifiedSubjectService subjects,
            TenantPermissionService tenantPermissions,
            DocumentRepository documents) {
        this.subjects = subjects;
        this.tenantPermissions = tenantPermissions;
        this.documents = documents;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Flux<DocumentView> listOwned(
            @P("tenantId") String tenantId) {

        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                subjects.fromTrustedAuthentication(
                    ctx.getAuthentication()))
            .flatMapMany(subject ->
                tenantPermissions
                    .canReadTenant(
                        subject.subjectId(), tenantId)
                    .flatMapMany(allowed -> {
                        if (!allowed) {
                            return Flux.error(
                                new org.springframework.security.access.AccessDeniedException(
                                    "Tenant read denied"));
                        }

                        return documents
                            .findByTenantIdAndOwnerSubjectIdAndDeletedFalseOrderByIdAsc(
                                tenantId, subject.subjectId())
                            .map(doc -> new DocumentView(
                                doc.getId(), doc.getTitle()));
                    }))
            .switchIfEmpty(Flux.error(
                new org.springframework.security.access.AccessDeniedException(
                    "Missing trusted subject")));
    }

    public record DocumentView(Long id, String title) {}
}
```

**Role of each layer:**

- `@PreAuthorize` enforces the functional authority; it does not choose the tenant.
- `ReactiveSecurityContextHolder` reads the `Authentication` placed into Reactor Context by WebFlux Security.
- `VerifiedSubjectService` must validate the authenticated principal type, account status, and subject ID—never trusting request-supplied `userId`.
- `tenantPermissions.canReadTenant(...)` returns a non-blocking `Mono<Boolean>` from trusted membership data.
- If membership is `false`, the service aborts before querying documents.
- The repository receives verified tenant and owner parameters instead of calling `findAll()`.
- The DTO exposes only `id` and `title`. Never serialize raw JPA/R2DBC entities containing confidential columns.

**This is an owner-only policy.** If shared recipients also have READ access, replace the owner-only query with a scoped ACL/share query without dropping the tenant predicate. Depending on your Spring Security version, SpEL expressions and reactive method security config may need minor adjustments; verify with integration tests.

### Do Not Let Alternate Call Paths Bypass the Service

If Controller A calls `TenantDocumentReadService` while GraphQL Resolver B calls `DocumentRepository.findAll()` directly, annotations on A do nothing for B. Place domain authorization inside contract-enforced services/APIs and restrict controllers or workers from accessing unscoped repositories.

### Never Pass Authentication as a Client-Modifiable Parameter

When a method receives `Authentication` from a Spring-managed controller, it may be a verified object. By contrast, a public service API accepting `String currentUserId` from arbitrary callers is not inherently trustworthy. Protect it by resolving the subject inside the service from a trusted context or requiring an immutable `VerifiedSubject` type constructible only by a trusted adapter.

## 11. Per-Item Filtering in `Flux` with `filterWhen`

Some data sources cannot push full ACL rules into a single SQL query—for example, an external search index or multi-source event streams. In such cases, enforce **per-element checks before emitting to the consumer**.

Illustrative pipeline:

```java
public Flux<DocumentView> listFromSearch(
        VerifiedSubject subject, String verifiedTenant) {

    return searchIndex.queryDocuments(verifiedTenant)
        .filterWhen(doc -> accessPolicy
            .canRead(subject, doc.id(), verifiedTenant))
        .map(doc -> new DocumentView(
            doc.id(), doc.title()));
}
```

`Flux.filterWhen(...)` accepts an async predicate (`Publisher<Boolean>`). This **fragment** requires `searchIndex`, `accessPolicy`, DTO, and Reactor. `canRead` should return `Mono<Boolean>` from a trusted permission source with bounded concurrency and timeouts; empty publishers must never count as allow. Test your exact Reactor version and failure semantics.

**Residual risks:** the search index still matched unauthorized documents; intermediate results can skew ranking, `totalCount`, facets, logs, or caches prior to filtering. Per-item filtering is therefore **defense-in-depth**, not a substitute for scoping inside the search query whenever the backend supports pushdown.

### `concatMap` for Pipelines Needing Strict Order and Explicit Conditions

```java
return searchIndex.queryDocuments(verifiedTenant)
    .concatMap(doc ->
        accessPolicy.canRead(subject, doc.id(), verifiedTenant)
            .flatMap(allowed ->
                allowed
                    ? Mono.just(new DocumentView(
                        doc.id(), doc.title()))
                    : Mono.empty()
            )
            .defaultIfEmpty(null)
    );
```

**The snippet above is an intentional anti-pattern:** Reactor rejects `null` values in `Mono.defaultIfEmpty(null)`. Never copy it. To write it properly, **omit `defaultIfEmpty(null)` altogether**; `Mono.empty()` simply drops unauthorized items:

```java
return searchIndex.queryDocuments(verifiedTenant)
    .concatMap(doc ->
        accessPolicy.canRead(subject, doc.id(), verifiedTenant)
            .defaultIfEmpty(false)
            .flatMap(allowed -> allowed
                ? Mono.just(new DocumentView(doc.id(), doc.title()))
                : Mono.empty())
    );
```

`concatMap` preserves item ordering and serializes evaluation by design—suitable when checking items sequentially, though at higher latency cost. If using `flatMap(..., concurrency)` for throughput, enforce backpressure and verify consistency rather than firing thousands of concurrent permission lookups unchecked.

### List Policies: Filter or Error?

Two distinct contracts exist:

- **List/search:** may omit unauthorized items and return the rest. If **the entire tenant is forbidden**, deny the whole list rather than returning a misleading empty list.
- **Detail by ID:** never silently turn a forbidden object into an empty list; return 403 or a neutral 404 per API contract without leaking owner or tenant.
- **Streaming secret bytes:** never drop invalid chunks via `Mono.empty()` without checking file-level permissions; authorize the file **before opening the stream**.

Never collapse every case into a generic `filterWhen(...)` without defining exact semantics.

## 12. Ordering of `filter`, `map`, and Side Effects Inside a Pipeline

Suppose a source returns an entity containing `privateNotes`, `apiToken`, and `title`.

Avoid:

```java
return documents.findAll()
    .doOnNext(doc -> auditLog.info("{}", doc))
    .map(doc -> new PublicDocumentView(
        doc.getTitle(), doc.getPrivateNotes()))
    .filterWhen(view -> policy.canRead(actor, view.id()));
```

This is an **illustrative anti-pattern**: it risks logging sensitive entities and copying `privateNotes` into a DTO before checking permissions. `PublicDocumentView`/`view.id()` is pseudocode highlighting the flaw, not a complete class.

Design instead:

```text
Source query already scoped
   -> verify relevant authorization facts
   -> construct minimal permitted DTO
   -> emit to caller
   -> audit outcome without leaking raw content
```

When multiple READ tiers exist (public metadata vs. confidential content), use distinct DTOs/projections per permission level; do not assume whole-document filtering suffices. Item `filter`ing protects **items**, not **fields**.

### Reactor Operators Do Not Automatically Enforce Permissions

`map(...)` only transforms data, `filter(...)` only evaluates a predicate, `doOnNext(...)` runs side effects, and `cache()` can retain results. None of these operators inherently know the request's identity or tenant. Policies must reference trusted subject/resource/context explicitly.

## 13. How Do `@PostAuthorize` and `@PostFilter` Differ?

| Scenario | `@PostAuthorize` | `@PostFilter` / Per-Item Policy |
| --- | --- | --- |
| Single-object `Mono<Document>` | Often fits owner post-checks if needed | No collection filtering needed |
| Multi-item `Flux<Document>` | Do not treat as an arbitrary per-element auto-filter | Use supported filtering mechanisms and test |
| One unauthorized item in a list | May deny the entire response under policy | Can drop individual items if the list contract allows |
| 10,000 upstream items | Post-check touches data after loading | Still expensive post-DB; prefer query pushdown |
| Write/save with side effects | **Must not** be the sole barrier | Does not solve write authorization |
| Long-lived SSE | One post-check is not perpetual re-authorization | Can check per item + handle revocation signals |
| Pagination `COUNT` | Does not fix total/count | Does not fix a `COUNT` computed in DB |
| Private DTO fields | Does not automatically redact | Item filtering does not redact fields |

**Subtle point:** `@PostAuthorize` on a returned object can stop that object from being returned. Yet if upstream already sent an email, wrote to a cache, triggered a job, or uploaded a file **before** the check, there is no guarantee those effects are undone.

With `Flux`, never infer from "HTTP returned 403 for an unprivileged user" that every item is filtered. Test a stream containing **multiple items across different owners and tenants**.

## 14. HTTP Output: Once Bytes Are Sent, They Cannot Be Recalled

In an ordinary HTTP response, the framework may buffer payloads before serialization. With `Flux` streaming, JSON streaming, SSE, or file downloads, HTTP headers/body may already be committed before a later item is denied.

Example:

```text
t0: GET /events request, method-level authorization ALLOW
t1: event #1 permitted -> sent to client
t2: event #2 permitted -> sent to client
t3: Alice's membership is revoked
t4: event #3 requires fresh permission -> DENY/error
```

At t4, the server can **terminate the stream** or emit a protocol error event, yet it **cannot retract event #1 or #2**. Once status/headers are sent, you cannot reliably switch the response to HTTP 403 for already-emitted items. This is why streaming tests must assert the **emitted sequence and terminal signal**, not status alone.

### Two Different Revocation Policies

1. **Authorize at subscribe:** verify once when the stream starts and allow it to continue. Fits domains that accept a bounded snapshot/session lease.
2. **Authorize per emission/period:** re-verify grants/memberships per item or interval; fits sensitive streams, at higher I/O cost and with a small delay between revocation and the next check.

No single default policy fits all streams. Define revocation SLAs, cache freshness, event rates, PDP costs, and connection termination rules.

### A Per-Event Permission-Checking Pipeline

```java
public Flux<EventDto> subscribeEvents(
        VerifiedSubject subject, String tenantId) {

    return eventSource.forTenant(tenantId)
        .concatMap(event ->
            permission.canSeeEvent(
                subject, tenantId, event.resourceId())
                .flatMap(allowed -> allowed
                    ? Mono.just(new EventDto(
                        event.id(), event.type(), event.payloadSummary()))
                    : Mono.error(
                        new org.springframework.security.access.AccessDeniedException(
                            "Event permission revoked")))
        );
}
```

This is a **component fragment** requiring an event source, policy, DTO, and resource-scoped inputs. It chooses to **terminate on encountering an unauthorized item**. Another app might skip the item and continue; make that contract explicit. Either way, subscribe to a tenant-scoped source rather than opening a cross-tenant stream and filtering at the end.

### SSE / WebSocket / GraphQL

- **SSE**: a single HTTP subscription can emit many events; address permissions both at subscribe time and per event.
- **WebSocket**: protecting the HTTP handshake does not automatically protect every message, room, or channel; implement message-level authorization.
- **GraphQL**: the route is often just `/graphql`; per-resolver, per-resource, and per-field permissions cannot be inferred from route authentication alone.
- **File downloads**: authorize the **entire file** before issuing a presigned URL or streaming bytes. Once an active presigned URL is handed out, revoking DB rows does not disable URL downloads until expiry.
- **Async exports**: permissions at export request time, job read time, and artifact download time may all need enforcement.

## 15. HTTP Security Does Not Replace Service/Domain Security

In WebFlux, a `SecurityWebFilterChain` may enforce authentication:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
);
```

This rule does not verify which tenant Document 42 belongs to. Meanwhile, `@PreAuthorize` on a service can also be bypassed if:

- A GraphQL resolver calls the repository directly.
- A worker/batch job calls another service bypassing the annotated method.
- A method in the same bean calls `this.securedMethod()`, bypassing the Spring AOP proxy via self-invocation.
- Code constructs instances with `new` instead of injecting Spring-managed beans.
- A custom `WebFilter` or new route lands in a different filter chain due to `@Order`/matchers.
- Execution jumps to `CompletableFuture` or a callback lacking Reactor `SecurityContext` where policy falls back to another subject.

**Defense in depth:** authentication/route guards at HTTP, domain action policies at services, tenant+ACL predicates at repositories/DB, DTO projections at output, and tests covering each call path.

## 16. Reactor Context, Authentication, and Tenant Scope

Reactive Spring Security uses `ReactiveSecurityContextHolder` backed by Reactor Context, differing from Servlet's `ThreadLocal`-only model.

Example reading `Authentication` inside a publisher:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> authMono =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication());
```

In a WebFlux app with Spring Security enabled, the context is populated along the reactive chain per authenticated request. Still, **never assume** `Authentication.getName()` is always a stable subject ID: OAuth2/JWT, OIDC, and multi-issuer setups need explicit mapping.

### `contextWrite` in Tests

```java
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

var auth = new TestingAuthenticationToken(
    "alice", "unused", "document:read");

Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
```

This is a **test fragment** needing proper types, imports, and context. At runtime, you can verify with `StepVerifier` that the publisher emits `"alice"`. However, `TestingAuthenticationToken` does not represent real JWT verification and must only be used deliberately in unit/integration tests.

### A Tenant Selector Is Not Authorization

If the path is `/tenants/tenant-b/documents`, `tenant-b` is chosen by the client. Verify Alice's membership in B before querying, rather than trusting `tenant-b` directly. Never store the active tenant in a mutable `static` field or uncleared ThreadLocal between requests; concurrent subscribers can span multiple threads and tenants simultaneously.

An immutable `VerifiedTenantScope` should carry the verified subject, tenant, and permissions, or service policies should resolve tenant membership from a trusted source at operation time.

## 17. Empty, Error, and Cancellation: Never Fail Open by Accident

A `Mono<Boolean>` can emit:

```text
Mono.just(true)  -> explicit ALLOW when sufficient evidence exists
Mono.just(false) -> explicit DENY
Mono.empty()     -> no result
Mono.error(e)    -> authorization evaluation failure
```

**Never convert empty or error into `true`.** When membership or the document is missing, policies must deny or return a non-disclosing response. When the DB/PDP times out, **never grant access**, and typically return HTTP 503/5xx with infrastructure failure metrics instead of treating all users as unauthorized.

Example:

```java
return permission.canRead(subject, resourceId)
    .defaultIfEmpty(false);
```

And never:

```java
return permission.canRead(subject, resourceId)
    .onErrorReturn(true); // Wrong: outage opens access.
```

### Cancellation Mid-Pipeline

Subscriber cancellation stops further items from being received, yet **does not automatically undo**:

- Already-committed SQL updates.
- Already-sent emails/events.
- Items already HTTP-serialized.
- Files already written to storage.
- Background tasks spawned on detached subscriptions.

Consequently, no "post-check then cancel" strategy guarantees undoing all side effects. Mutation authorization must precede the operation or be enforced atomically within the operation itself.

## 18. The Boundary Between Pre-Checks and Mutations

A race:

```text
T1: @PreAuthorize EDIT -> ALLOW
T2: admin revokes Alice's EDIT permission
T1: SQL UPDATE docs SET ...
```

Method pre-annotations can run **before** transactional advice, and authorization data can change after the check. A standalone `@Transactional` with default isolation does not automatically guarantee absolute protection against revocations.

A conditional SQL `UPDATE`:

```sql
UPDATE documents
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :verified_tenant
  AND owner_subject_id = :authenticated_subject
  AND deleted = FALSE
  AND status = 'DRAFT';
```

If the domain permits edits via ACLs, include an `EXISTS` ACL condition **inside the statement or transaction**. Verify affected row counts; zero rows must never be treated as success and must avoid disclosing resource existence per API contract.

### Reactive `TransactionalOperator`

```java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<Boolean> rename(
        VerifiedSubject actor,
        long documentId,
        String newTitle) {

    return writeRepository
        .renameIfAuthorized(
            actor.subjectId(), actor.tenantId(),
            documentId, newTitle)
        .map(affectedRows -> affectedRows == 1L)
        .as(transactionalOperator::transactional);
}
```

**Illustrative fragment**: requires a `TransactionalOperator` configured with a `ReactiveTransactionManager`, a `writeRepository` binding tenant/owner/ACL/status constraints, and a driver-matching `affectedRows` type (assumed `long` above); omits controller/DTO. If the method returns `false`, the service must translate it into a denial or not-found outcome—never `200 OK` when no update occurred.

Reactive transactions use Reactor Context for resource binding. They do not wrap remote HTTP PDP calls, emails, or file storage in the same ACID transaction. For non-DB side effects, consider an outbox or post-commit compensating strategy.

### Never Use `@PostAuthorize` as a Rollback Manager

Even when reactive method security emits an error after an item is created, there is no guarantee transactions, caches, storage, and external effects rolled back. Review **transaction advisor vs. security advisor ordering** with integration tests instead of trusting annotations blindly.

## 19. Pagination: Where Post-Filtering Commonly Breaks Business Logic

Suppose a query requests page 1 with `LIMIT 10` out of 100 documents, yet Alice can view only 5 documents at positions 20–30.

Wrong approach:

```text
DB: ORDER BY created_at LIMIT 10 OFFSET 0
   -> 10 documents (none belonging to Alice)
@...PostFilter:
   -> 0 documents
API response:
   items=[]
   totalElements=100
```

Alice sees an empty page with `total=100` despite valid records on another page. If the UI interprets an empty page as "no more results", Alice never sees her 5 accessible documents. Meanwhile `totalElements=100` leaks how many documents others own.

Right approach:

```text
DB: WHERE tenant=verifiedTenant
    AND (owner=alice OR active ACL/share grant)
    AND deleted=false
    ORDER BY created_at DESC, id DESC
    LIMIT 10
   -> only documents Alice is permitted to see
COUNT:
   -> same tenant/ACL predicate
API:
   -> items & totalElements within Alice's scope
```

Push authorization predicates into the query before `LIMIT`/`OFFSET`, or use cursor/keyset pagination with permission predicates. Fall back to per-item filtering only when a data source truly lacks pushdown support, and redefine pagination/count semantics explicitly.

### Search, Aggregations, and Facets

Even after filtering item bodies, search metadata can still leak:

- Total hits.
- Facet counts by status/project.
- Search snippets from unauthorized documents.
- Autocomplete suggestions.
- Rankings or sort keys derived from confidential data.
- File names and owner identifiers.

Enforce data authorization **before generating metadata** whenever possible, rather than slapping `Flux.filter(...)` onto precomputed search results.

## 20. Does `@PostFilter` Support Every Return Type?

Never infer from Java Servlet examples that every reactive return type behaves identically. Spring Security's Reactive Method Security docs confirm `PostFilterAuthorizationReactiveMethodInterceptor` and pre/post annotations exist, yet before shipping production code you must verify:

1. Exact Spring Security runtime version.
2. `@EnableReactiveMethodSecurity` configuration and `AuthorizationManager` mode.
3. Actual return type: `Flux<T>`, `Mono<T>`, `Mono<List<T>>`, collections, Kotlin coroutines/Flow.
4. Annotation/SpEL property resolution on DTOs/records.
5. Behavior with empty, null, error, and multi-item streams.
6. Whether the AOP proxy actually wraps the `Publisher`.
7. Interactions with transactions, caching, and serialization.

A sound test:

```text
Given Flux(Doc1 owner=alice, Doc2 owner=bob, Doc3 tenant=B)
When Alice calls the method through the Spring proxy
Then emitted IDs contain only Doc1
And Doc2/Doc3 do not appear in subscriber signals
And zero side effects occur for Doc2/Doc3
```

Treat `@PostFilter` as a **conditional tool**, and **repository-scoped queries** as the proactive way to eliminate unauthorized data at the source.

## 21. Standalone Java 17 Example: Method ALLOW Yet Items Still Need Filtering

The following example **does not use Spring Security or Reactor** because both require external dependencies beyond the JDK. It uses Java 17 `CompletableFuture` to simulate async calls and compare three layers: (1) method invocation permission, (2) flawed owner-only filtering missing tenant checks, and (3) complete tenant, owner, and state filtering before emitting results.

Never call `join()` on the WebFlux event loop. In a standalone `main` file, `join()` is used solely to print results deterministically.

Save `ReactiveEmissionBoundaryDemo.java`:

```java
import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ReactiveEmissionBoundaryDemo {

    enum Action { READ, WRITE }

    record Actor(
        String id,
        String tenant,
        Set<Action> actions,
        boolean active
    ) {}

    record Document(
        int id,
        String tenant,
        String owner,
        boolean deleted
    ) {}

    private static final List<Document> ALL = List.of(
        new Document(1, "tenant-a", "alice", false),
        new Document(2, "tenant-a", "bob", false),
        new Document(3, "tenant-b", "alice", false),
        new Document(4, "tenant-a", "alice", true),
        new Document(5, "tenant-a", "alice", false)
    );

    static boolean canInvoke(Actor actor, Action action) {
        return actor != null
            && actor.active()
            && actor.actions().contains(action);
    }

    static List<Integer> naiveOwnerOnly(
            Actor actor, List<Document> source) {
        return source.stream()
            .filter(doc -> doc.owner().equals(actor.id()))
            .map(Document::id)
            .toList();
    }

    static List<Integer> safeVisible(
            Actor actor, List<Document> source) {
        return source.stream()
            .filter(doc -> doc.tenant().equals(actor.tenant()))
            .filter(doc -> !doc.deleted())
            .filter(doc -> doc.owner().equals(actor.id()))
            .map(Document::id)
            .toList();
    }

    static CompletionStage<List<Integer>> emittedReadIds(Actor actor) {
        if (!canInvoke(actor, Action.READ)) {
            return CompletableFuture.completedFuture(List.of());
        }

        // Simulates an already-completed async source. Not R2DBC.
        return CompletableFuture.completedFuture(ALL)
            .thenApply(rows -> safeVisible(actor, rows));
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "tenant-a", Set.of(Action.READ), true);
        Actor bob = new Actor(
            "bob", "tenant-a", Set.of(Action.READ), true);
        Actor carol = new Actor(
            "carol", "tenant-b", Set.of(), true);

        System.out.println("Alice method READ: "
            + canInvoke(alice, Action.READ));
        System.out.println("Unscoped source size: " + ALL.size());
        System.out.println("Naive owner-only IDs: "
            + naiveOwnerOnly(alice, ALL));
        System.out.println("Safe emitted Alice IDs: "
            + emittedReadIds(alice).toCompletableFuture().join());
        System.out.println("Safe emitted Bob IDs: "
            + emittedReadIds(bob).toCompletableFuture().join());
        System.out.println("Carol method READ: "
            + canInvoke(carol, Action.READ));
        System.out.println("Carol emitted IDs: "
            + emittedReadIds(carol).toCompletableFuture().join());
        System.out.println("Alice method WRITE: "
            + canInvoke(alice, Action.WRITE));
    }
}
```

Compile/run commands:

```bash
javac ReactiveEmissionBoundaryDemo.java
java ReactiveEmissionBoundaryDemo
```

Exact stdout on Java 17+:

```text
Alice method READ: true
Unscoped source size: 5
Naive owner-only IDs: [1, 3, 4, 5]
Safe emitted Alice IDs: [1, 5]
Safe emitted Bob IDs: [2]
Carol method READ: false
Carol emitted IDs: []
Alice method WRITE: false
```

**Observations:**

- Alice can invoke READ, yet the raw source holds **5** records including Bob's doc, tenant B's doc, and a deleted doc.
- Naive owner-only post-filtering fails: `Doc3` (tenant B) and `Doc4` (deleted) slip through.
- Full filtering emits only IDs `[1, 5]`.
- Bob has READ and receives only ID `2`; Carol lacks READ authority and receives zero items.
- Alice lacks WRITE; read permission never implies write permission.

**Transparent limitation:** `CompletableFuture.completedFuture(ALL)` performs no real I/O, and `safeVisible(...)` still filters **after materializing 5 documents**. It explains logical boundaries and is **not** a DB pushdown implementation. In production, to reduce risk and load, replace `ALL` with a **predicated R2DBC query** before items enter the `Publisher`.

## 22. `WebTestClient`: Asserting Returned Data, Not Just HTTP Status

A WebFlux integration test needs the Spring Security WebFilter chain and service proxies loaded from the application context.

Setup example:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

class DocumentHttpSecurityTest {
    @Autowired ApplicationContext applicationContext;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

This is a **test class fragment**: it requires a test context/runner annotation (`@SpringBootTest` or equivalent), controllers/services, `spring-security-test`, repository fixtures, and WebFlux dependencies. Using `bindToController(new Controller())` without the security chain can bypass method/security filters.

### Checking Body IDs

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("alice"))
        .authorities(
            new SimpleGrantedAuthority("document:read")))
    .get()
    .uri("/api/tenants/tenant-a/documents")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(DocumentView.class)
    .hasSize(2);
```

This is a **fragment**: `SimpleGrantedAuthority`, `DocumentView`, and fixtures must be defined; the test expects Alice to receive exactly two records. Beyond count, extract the body and assert **exact IDs**, confirming Bob's, tenant B's, and deleted IDs **are absent**. `mockJwt` does not verify real token signatures, issuers, or audiences; add real decoder tests to verify authentication boundaries.

### A Dangerous Case

A test checking only:

```java
.expectStatus().isOk();
```

passes even if the response contains 100 out-of-scope documents. Testing data authorization always requires **asserting body contents and absent records**, not status alone.

## 23. `StepVerifier`: Checking Publisher Signals

With Reactor Test:

```java
import reactor.test.StepVerifier;

StepVerifier.create(
    documentService.listOwned("tenant-a")
)
    .expectNextMatches(doc -> doc.id().equals(1L))
    .expectNextMatches(doc -> doc.id().equals(5L))
    .verifyComplete();
```

This is a **test fragment** needing a real Spring-managed service, `Long` `DocumentView.id()`, `Authentication` in Reactor Context (or test security support), and fixtures. Crucially, no extra items slip in between.

### Checking Deny Signals

```java
StepVerifier.create(securedService.listOwned("tenant-c"))
    .expectError(
        org.springframework.security.access.AccessDeniedException.class)
    .verify();
```

This expectation holds when the service chooses an **error** for unmapped tenant memberships. If the API contract specifies 404 or an empty list, test accordingly while never granting access. Never collapse all unauthorized cases into empty without defining what information must remain hidden.

### Verifying a Publisher Emits Zero Unauthorized Values

```java
StepVerifier.create(
    Flux.just(
        new Doc(1, "alice"),
        new Doc(2, "bob"),
        new Doc(3, "alice")
    ).filter(doc -> "alice".equals(doc.owner()))
)
    .expectNextMatches(doc -> doc.id() == 1)
    .expectNextMatches(doc -> doc.id() == 3)
    .verifyComplete();
```

This is a **Reactor unit test fragment** requiring `Doc`, `Flux`, and JUnit context. It illustrates per-emission verification yet **does not test Spring Security interceptors**, because it uses plain `filter`. To test real `@PostFilter`/`@PostAuthorize`, invoke the annotated Spring bean.

### Reactive `SecurityContext` in Tests

```java
var authentication = new TestingAuthenticationToken(
    "alice", "unused", "document:read");

StepVerifier.create(
    securedService.listOwned("tenant-a")
        .contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(authentication))
)
    .expectNextCount(2)
    .verifyComplete();
```

This is a **fragment** needing `TestingAuthenticationToken`/Reactor imports and service fixtures. `expectNextCount(2)` checks only quantity; add per-item assertions to prevent out-of-scope ID leaks.

### Testing Source Subscriptions and Side Effects

Prove that on PRE DENY:

- Repositories/sources are not unexpectedly subscribed to.
- Zero SQL mutations occur.
- Zero emails/events are sent.
- Zero presigned URLs are issued.
- Zero raw entities are cached.
- Zero items emit downstream.

Use `doOnSubscribe`/mock subscriber counters or integration mocks to verify. Also test post-check denials occurring **after** a read source may have run—confirming post-checks cannot guard side effects.

## 24. Minimum Test Matrix

| Condition | Invocation | Data/Item Outcome to Protect |
| --- | --- | --- |
| Anonymous calls READ | DENY | Zero items |
| Alice lacks `document:read` | DENY | Zero items |
| Alice has READ authority, owns Doc1 in same tenant | ALLOW | Doc1 emitted |
| Alice has READ authority, Bob's Doc2 | ALLOW list | Doc2 **not** emitted |
| Alice has READ in A, Doc3 belongs to B | ALLOW list A | Doc3 **not** emitted |
| Alice owns deleted Doc4 | ALLOW list A | Doc4 **not** emitted |
| User B has READ, modifies URL `tenant=A` | No verified membership | Zero tenant A docs emitted |
| Active READ share on Doc5 | ALLOW per domain policy | Only Doc5 and permitted fields |
| Expired or revoked READ share | Not guaranteed blocked at method level | Doc5 absent |
| READ grant calls EDIT | DENY at action | Zero data written |
| List has 10 valid objects out of 1000 | ALLOW | Pagination/count reflects only the 10 permitted objects |
| SSE emits 2 events then revokes | Define per-stream policy | Subsequent unauthorized events blocked per SLA |
| `Flux` item 3 denied after 2 items sent | Partial response already sent | Never assume HTTP status flips to 403 post-commit |
| DB permission timeout | No proof of permission | Never ALLOW; error/5xx per contract |
| Remote PDP returns `Mono.empty()` | No decision | Never ALLOW |
| `SecurityContext` lost on scheduler switch | Caller unverifiable | DENY, never fall back to admin |
| Service called from GraphQL/worker | HTTP guard may not run | Domain policy still mandatory |
| `@PreAuthorize` bypassed via self-invocation | May skip interceptor | Query/data layer still requires scoping |
| `Flux`/`Mono` cache shared across actors | Cross-user leak risk | Key cache by actor/tenant/action/version or skip caching |
| `privateNotes` field on `DocumentView` | List item may be valid | Omit field without field-level authority |

Beyond the matrix, test detail, batch, search, export, and download endpoints along actual production call paths. For data leaks, the absence of a record or field often matters more than whether a request returned 200.

## 25. Performance: Do Not Turn Per-Item Authorization into N+1

A list of 1,000 items where each item calls `canRead` to query an ACL triggers 1,000 I/O operations even when non-blocking. Non-blocking utilizes threads better, yet **does not eliminate queries**.

Priorities:

1. **Predicate pushdown**: filter owner, tenant, and ACL in SQL/search right at the source.
2. **Batch fetching**: load ACL/resource facts in bulk for a set of verified IDs.
3. **Coarse action pre-check**: reject requests clearly lacking authority before large queries.
4. **Bounded concurrency**: if `filterWhen`/`flatMap` is unavoidable, cap concurrent permission lookups.
5. **Backpressure**: never collect an entire `Flux` when only a few elements are needed.
6. **Scoped caching**: key by subject/tenant/resource/action/policy version/ACL epoch with invalidation.
7. **Observability**: track p50/p95/p99 latency, query counts, denied item counts, cache-hit safety, source errors, and stream cancellations.
8. **DB DTO projections**: avoid loading password hashes, tokens, or classified text into application objects unnecessarily.
9. **Align `COUNT` and list predicates**: avoid leaking out-of-scope statistics.
10. **Clear revocation semantics**: never cache ALLOWs past share expiry or revocation SLAs.

### Permission-Unaware `Flux.cache()`

If a singleton service holds a `Publisher` built for Alice:

```java
private final Flux<DocumentView> cachedResult =
    rawDocuments.findAll().map(this::toView).cache();
```

This is an **anti-pattern** for user-specific data: the cache stores raw data and replays it across multiple subscribers. Never use `Flux.cache()` as a multi-user authorization cache lacking keys, expiry, and invalidation. For sensitive responses, also audit browser/CDN caches and file/object storage.

## 26. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `@PreAuthorize('document:read')` filters `Flux` items | Leaks Bob's / other tenants' data | Data-scoped queries or per-element policies |
| Testing only 401/403/200 | Response body leaks go undetected | Assert IDs, fields, counts, and absences |
| Calling `findAll()` then `@PostFilter` over entire store | Massive I/O, broken pagination | Query ACL/tenant before `LIMIT` |
| Filtering owner while forgetting tenant | Cross-tenant leak | Enforce `subject+tenant+action+resource` |
| Filtering items without filtering private fields | Field-level data leak | Per-permission DTOs/projections |
| Using `@PostAuthorize` for writes | Side effects may already commit | Pre-check + conditional updates/transactions |
| Thinking `@PostAuthorize` recalls sent SSE bytes | Client already received data | Recheck per event + termination/lease semantics |
| Counting whole DB then filtering list | Leaks `totalElements` | `COUNT` with the same predicate |
| Treating `Mono.empty()` or dependency errors as allow | Fail-open | Default deny / 5xx |
| Manual `subscribe()` outside pipeline to "check later" | Request may proceed before decision | Compose `Publisher` into security chain |
| Calling `block()` in reactive policies | Stalls event loop | R2DBC / `WebClient` / `Mono` composition |
| Method calls `this.read()` internally | Bypasses AOP proxy | Call via Spring bean + scoped data queries |
| Service instantiated with `new` | Annotations not intercepted | Use Spring-managed beans |
| Passing raw tenant header straight to DB | IDOR / BOLA | Verify membership, trusted tenant scope |
| Caching `Flux` on singleton | Cross-user replay | Cache by subject/tenant or avoid caching |
| Using `onErrorContinue` to skip permission errors | Hides dependency failures, hurts audits | Classify errors; never grant access |
| Streaming response body first, checking afterward | Partial leakage | Verify before emission and define termination |
| Using `mockJwt` to conclude JWT signatures are safe | Mock skips decoder | Test Resource Server with real tokens |
| Filtering after search facets | Leaks metadata/counts | Filter at search/index source |
| Skipping multi-item `@PostFilter` tests | Unsure if annotation executes properly | `StepVerifier` through Spring proxy |
| Missing ACL version in cache keys | Serves ALLOW after revocation | Keyed caching / invalidation / freshness |
| Protecting HTTP layer only | GraphQL, jobs, workers bypass it | Service/domain/DB policies |
| Treating status 404 as proof of zero leaks | Metadata/streams may still leak | Inspect full bodies, timings, logs, side effects |

## 27. Code Review Checklist for Reactive Method Security

1. Does the method return `Mono` or `Flux`? Does the system have long-lived subscriptions/streams?
2. Is `@EnableReactiveMethodSecurity` enabled with the right version and mode?
3. Is the service called through a Spring proxy, not `this.` or `new`?
4. Does `@PreAuthorize` guard a **functional action**, or was it mistaken for an object check?
5. Are caller and tenant verified from trusted sources?
6. Does the repository filter by resource type, tenant, owner/ACL, and status before reading?
7. If using `@PostAuthorize`, have source side effects and version behavior been verified?
8. If using `@PostFilter`, has multi-item `Flux` across owners/tenants been tested?
9. If using `filterWhen`/`concatMap` per item, how are empty and error signals handled?
10. Is data ever logged, cached, emitted as events, or serialized **before** policy checks?
11. Does the response DTO strip unauthorized fields?
12. Do pagination, `COUNT`, search facets, and exports share the same authorization predicates?
13. Do mutations enforce checks close to the DB update, inside transactions, with row-count verification?
14. Do streams define policies for mid-stream revocation or expiry?
15. If a response has already committed, how does the app handle late denials?
16. Have cold/hot sources, cancellation, cache replay, and multiple subscribers been tested?
17. Are `block()`, blocking JDBC on the event loop, and manual `subscribe()` avoided?
18. Does `Authentication` stay in Reactor Context across scheduler switches?
19. Are direct service calls outside the HTTP chain tested?
20. Are caches keyed by actor/tenant/action/resource/version and invalidated on revocation?
21. Do DB/PDP failures avoid ALLOW and emit proper monitoring signals?
22. Do `StepVerifier`/`WebTestClient` tests assert **exact content** rather than status codes alone?
23. Do negative tests include items from other users, other tenants, deleted, expired, and confidential records?
24. Have limit/offset/cursor pagination and count leakage been tested?
25. Has behavior been verified on the exact Spring Security version running in production?

**Conclusion:** In Spring Security Reactive, protecting **permission to invoke a method** is necessary but **insufficient** to protect **data emitted from `Mono`/`Flux`**. `@PreAuthorize` blocks unauthorized calls; `@PostAuthorize` and `@PostFilter` assist with post-checks/filtering within supported bounds; yet a sound design **constrains data at the source**, validates items and fields before emission, handles streaming and revocation, avoids side effects prior to post-checks, and explicitly tests that forbidden elements **never reach the client**.

## References

- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity`, `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter`, reactive interceptors.
- [Spring Security API — PostFilterAuthorizationReactiveMethodInterceptor](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/PostFilterAuthorizationReactiveMethodInterceptor.html): post-filtering interceptor in reactive method security.
- [Spring Security API — PostAuthorizeReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/PostAuthorizeReactiveAuthorizationManager.html): post-check evaluation and `MethodInvocationResult`.
- [Spring Security — Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): HTTP enforcement points and `authorizeExchange`.
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `ReactiveSecurityContextHolder` mechanism and `SecurityContext` in Reactor.
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): integrating `WebTestClient` with the Spring Security chain.
- [Spring Security — Reactive OAuth2/JWT Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt` and limits of test mocks.
- [Spring Data R2DBC — Reference](https://docs.spring.io/spring-data/relational/reference/r2dbc.html): reactive repositories/data access and query predicates.
- [Spring Framework — Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionalOperator` and reactive transaction boundaries.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): `Flux`, `Mono`, `filterWhen`, `concatMap`, Context, backpressure, error/cancellation, and testing.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and object-level checks.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): per-ID permissions and scoped data queries.
