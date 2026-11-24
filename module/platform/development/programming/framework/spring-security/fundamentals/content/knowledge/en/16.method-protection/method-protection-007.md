# `@PreFilter`, `@PostFilter`, and the Limits of Post-Query Filtering

> **Scope:** Spring Security Method Security, Java 17+, Spring Security 6.x. This lesson belongs to the **Method protection** topic. The focus is on distinguishing filtering arguments **before** method execution from filtering results **after** the method returns, and understanding the security, performance, pagination, transactional, and data-integrity limits of filtering only in memory after querying.

## 1. Why Filter at the Method Level?

Suppose a service returns a list of documents. The database holds 100,000 documents owned by many users, yet Alice may only see her own documents. Three distinct concerns are easily conflated into one:

1. **Permission to invoke the method:** Is Alice allowed to invoke the "read documents" operation? `@PreAuthorize("hasAuthority('document:read')")` fits this requirement.
2. **Permission per element:** Within the returned list, which elements may Alice see? `@PostFilter` can filter the result after the method has run.
3. **Data scoping at the source:** The database should read only Alice's/valid tenant's rows before pagination, counting, joins, and transferring data into the application. This is the job of scoped queries, repositories, or data-access policies.

Most importantly: **`@PostFilter` does not stop an already-executed query from accessing rows outside the user's permission.** It can only strip elements returned through the method-security proxy for supported collection types and expressions. To protect large datasets, multi-tenant data, pagination, or side-effecting operations, enforce permissions before and inside the query itself.

```text
Caller → Spring AOP Method Security
  ├─ @PreFilter: removes input elements failing the condition
  ├─ @PreAuthorize: checks invocation permission (if present)
  ↓
  service method executes
  ↓
  repository queries / business logic runs
  ↓
  @PostAuthorize: checks permission on result (if present)
  @PostFilter: filters elements of result (if present)
  ↓
  caller receives proxy-processed result

If the repository already read too many rows, @PostFilter does not
narrow the SQL query that just ran.
```

The diagram helps explain the stages and **does not promise exact ordering among arbitrary custom interceptors**. Spring Security organizes annotations into ordered interceptors/AOP advisors; exact behavior depends on AOP config, version, and method types.

## 2. Comparing Method Security Annotations

| Annotation | Timing | Inspected target | Primary behavior | When to choose |
|---|---|---|---|---|
| `@PreAuthorize` | Before calling the method | Call permission, arguments, identity | Allows or denies the **entire call** | Required permissions or input validation before action |
| `@PreFilter` | Before target method runs | Each element of a collection parameter | Removes unmatched elements from the input seen by the method | Business logic **accepts dropping** unauthorized items |
| `@PostAuthorize` | After target method runs | Return value (usually one object) | Allows or denies the **entire result** | Authorization based on retrieved data; unsuitable to undo side effects |
| `@PostFilter` | After target method runs | Each element of a supported collection result | Removes unmatched elements before returning through proxy | Small, already-loaded results not needing accurate filtered pagination/counts |
| `@EnableMethodSecurity` | Application startup | Proxied Spring beans | Activates method authorization | Prerequisite for annotations in standard Servlet apps |

**`@PreFilter` and `@PostFilter` do not equal denying the entire access.** For example, if Alice sends 5 documents including 3 owned by Bob, `@PreFilter` may cause the service to receive only Alice's 2 documents. That can make sense for a "filter list" operation, yet is dangerously wrong for business contracts requiring "process all or fail." When you need **all-or-nothing**, check every element and reject the entire request if any element is unauthorized.

A `@PostFilter` alone on a list result can leave the caller with an empty list; it **does not automatically return HTTP 403** when every element is removed. If you need a denial error instead of an empty list, use `@PreAuthorize`, `@PostAuthorize`, or explicit policy checks per your API contract.

## 3. Enabling Method Security

In a Spring Boot app using Spring Security 6.x, method security must be explicitly enabled. Example `MethodSecurityConfig.java`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` activates `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` by default. The `spring-boot-starter-security` dependency **does not automatically enable method security** simply because an HTTP `SecurityFilterChain` exists. Annotations must sit on Spring-managed beans/methods called through the appropriate proxy/AOP mechanism.

If you annotate an object instantiated with `new`, or an internal method calls `this.otherAnnotatedMethod()` bypassing the proxy, the check may **not run**. Private/final methods and specific proxy modes also need care. Test on a **Spring-injected bean** rather than creating an object with `new` and assuming annotations are active.

In reactive applications, enabling `@EnableReactiveMethodSecurity` and supporting Reactor `Context` is a different mechanism; do not treat Servlet and WebFlux configurations as directly interchangeable. The annotation examples below target standard synchronous Spring method security; reactive list handling is covered separately at the end.

## 4. `@PreFilter`: Filtering Input Elements Before Calling the Method

For a collection parameter, SpEL provides the special variable `filterObject` representing **the element currently under evaluation**. `authentication.name` retrieves the identity name from the security context's `Authentication`, established by authentication.

Example:

```java
@PreFilter("filterObject.owner == authentication.name")
public List<Document> acceptOwnedDocuments(List<Document> documents) {
    return documents;
}
```

If the authenticated caller is `alice` and passes a list of three Documents whose `owner` values are `alice`, `bob`, `alice`, the target method sees Alice's two documents. This example is an **excerpt inside a Spring bean with method security enabled**; `Document` must expose a SpEL-readable JavaBean property `owner` (such as a `getOwner()` getter). It is not a standalone runnable program.

### 4.1. Methods with Multiple Collection Parameters

When multiple filterable parameters exist, specify the target using `filterTarget`:

```java
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.core.parameters.P;

@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents"
)
public List<Document> acceptOwnedDocuments(
        @P("documents") List<Document> documents,
        List<Document> attachments,
        boolean dryRun) {
    return documents;
}
```

The `@P("documents")` annotation binds the parameter name for Spring Security's parameter name resolution. When an expression references a Java parameter name directly (e.g., `#documentId`), compiler settings keeping parameter names with `-parameters` or compatible naming techniques are critical. Never assume a name visible in Java source is guaranteed to be available at runtime.

**Supported containers per Spring Security 6.5 docs:** filtering supports arrays, collections, maps, and streams in supported contexts; with a `Map`, each evaluated element is an entry, so access the value via `filterObject.value`:

```java
@PreFilter("filterObject.value.owner == authentication.name")
public Map<String, Document> importOwned(
        Map<String, Document> documentsByCode) {
    return documentsByCode;
}
```

These snippets illustrate intent and **do not guarantee every custom or immutable collection can be filtered identically**. Use compatible containers and test against your actual Spring Security version. In particular, never rely on Spring converting `null` into an empty list. With `Stream`, handle only open streams and avoid reusing consumed streams.

### 4.2. `@PreFilter` Is a Filter, Not an All-or-Nothing Validation Gate

Suppose `POST /documents/batch-delete` receives 4 IDs: 3 belonging to Alice and 1 to Bob. If `@PreFilter` is applied to the document list, the method may receive only Alice's 3 documents and proceed. If the API promised "delete all 4 or delete nothing," **silently filtering violates the contract**, even if Bob's data wasn't deleted.

Solution for all-or-nothing:

- Validate authenticated inputs, mapping IDs to trusted entities from the database; never trust client-sent `owner`/`tenant` fields.
- Use a service policy verifying **every element** belongs to the actor's tenant, owner, or permissions.
- If any element is invalid, reject the entire request before causing side effects.
- For concurrent updates, transactions, locks, or conditional updates remain necessary so policies aren't invalidated by data changing after the check.

## 5. `@PostFilter`: Filtering Result Elements After Method Completion

Excerpt of a service returning a list of documents:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostFilter("filterObject.owner == authentication.name")
public List<Document> browseAllDocuments() {
    return documentRepository.findAll();
}
```

Correct logical order:

1. `@PreAuthorize` requires `document:read`. Callers lacking this permission are denied before the method executes.
2. The method calls `findAll()`; **the repository already read every document returned by the query**, even those not belonging to Alice.
3. `@PostFilter` evaluates each document in the result, removing elements whose owner differs from `authentication.name`.
4. The caller going through the proxy receives the filtered list. This **does not turn back time** to avoid the cost of `findAll()` or any side effects already produced inside the method.

With 5 documents (3 Alice, 2 Bob), the service may read 5 elements while the caller receives 3. If datasets are small, reading the list was already required for another reason, and security boundaries are enforced elsewhere, this can be a reasonable auxiliary filter. If lists grow to millions of rows, this design causes overload and violates data isolation at the source.

### 5.1. `@PostFilter` Is Not `@PostAuthorize`

`@PostFilter` evaluates each element of a collection result; `@PostAuthorize` checks the whole invocation based on the return value. Example returning a single Document:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Document loadOneDocument(long id) {
    return documentRepository.findRequiredById(id);
}
```

This excerpt assumes the repository returns a non-null `Document` with `owner` as a JavaBean property. `@PostAuthorize` can refuse to return the Document to an unauthorized caller, yet the repository already ran the query and any side effects before method exit may already have happened. For sensitive data, prefer queries scoped by owner/tenant or checking permissions before acting.

### 5.2. Maps, Arrays, and Streams

Per Spring Security 6.5 docs, `@PostFilter` supports arrays, collections, maps, and streams (for open streams). With `Map<K, Document>`, `filterObject` is an entry; access the Document via `filterObject.value`:

```java
@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, Document> browseByCode() {
    return documentRepository.findByCode();
}
```

With JPA Streams or lazy collections, be careful with transactions, sessions, cursors, and consumption timing. An unconsumed stream must not be treated as "an already-filtered, completely safe list." Read/close streams cleanly within their lifecycle and prefer repository predicates for high volumes or pagination.

With `Mono<List<Document>>` or `Flux<Document>` in WebFlux, **do not treat them like plain `List`s** by copying Servlet `@PostFilter` code. Reactive designs normally use scoped queries and `filter`/`filterWhen` operators within the same Publisher when extra filtering is truly needed; authorization checks must attach properly to subscription and Reactor Context.

## 6. Core Limitations of Post-Query Filtering

### 6.1. SQL Already Ran; Data Already Left the Database

When a method runs `findAll()` followed by `@PostFilter`, the query has already read and transferred more rows than the caller may view. Filtering afterward does not save:

- Disk I/O, query CPU, buffer memory, DB-to-app network traffic, and entity hydration time.
- DTO mapping costs, lazy loading, or N+1 queries prior to filtering (if triggered inside the method).
- Cost of instantiating sensitive objects in process memory.
- Side effects inside the method such as logging full datasets, shared caching, emitting events, computing aggregates, or calling helper services.

**Do not conclude `@PostFilter` automatically leaks data to HTTP clients:** the result returned via the proxy is filtered before serialization. The issue is that **out-of-scope rows were already fetched and processed underneath**, increasing risk surface and cost while non-proxied paths or intermediate data uses must be guarded separately.

### 6.2. Filtering After Pagination Breaks Page Size and Totals

Suppose the database has 20 records, and a query fetches the first page with `LIMIT 10 OFFSET 0`. Only 3 of those 10 rows are visible to Alice. Running `@PostFilter` on those 10 rows causes:

- The caller sees only **3 items**, even though more of Alice's records sit on later pages.
- `totalElements = 20` computed by the database before filtering does not reflect the total visible to Alice.
- `hasNext`, `totalPages`, and offsets/cursors skew away from Alice's dataset.
- When returning `Page<Document>`, **do not assume** `@PostFilter` understands, filters, and recalculates Page metadata; annotation docs specify collection types like arrays/collections/maps/streams, without guaranteeing Spring Data pagination semantics.

Therefore, constraints must go into the query **before `LIMIT/OFFSET` and counting**. Semantically right statement:

```sql
SELECT id, owner_id, tenant_id, title
FROM documents
WHERE tenant_id = :trustedTenantId
  AND owner_id = :trustedUserId
ORDER BY id
LIMIT :pageSize OFFSET :offset;
```

The matching count query must carry the exact same conditions:

```sql
SELECT COUNT(*)
FROM documents
WHERE tenant_id = :trustedTenantId
  AND owner_id = :trustedUserId;
```

`trustedUserId` and `trustedTenantId` must come from verified identity and valid policy, never copied from client-editable query parameters or JSON. Stable ordering (e.g., `ORDER BY id`) and snapshot/cursor strategies under concurrent updates are also essential for real pagination.

### 6.3. Post-Query Filtering Corrupts Statistics and Aggregations

Suppose a service calculates `sum(totalAmount)` or `count(*)` across the entire table before invoking `@PostFilter`. Since the result is a number rather than individual removable Documents, `@PostFilter` cannot adjust the sum to reflect "total allowed to view." Similarly, computing rankings, statistics, top-N, or aggregates over unauthorized data leaks influence from those rows even if an output list is filtered later.

Every aggregate query must use the **exact same authorization scope** as detail queries.

### 6.4. Does Not Protect Writes, Deletes, or Downstream Calls

Suppose a method has side effects:

```java
@PostFilter("filterObject.owner == authentication.name")
public List<Document> deleteAndReturnDeleted(long[] ids) {
    return documentRepository.deleteAndReturnDeleted(ids);
}
```

**Flawed security design:** the method already deleted records before the return list was filtered. Filtering the returned objects afterward does not restore someone else's records. For writes/deletes, permissions must be verified **before and inside** state-changing commands, alongside SQL tenant/owner constraints, transactions, and concurrency handling.

### 6.5. Multi-Tenant Isolation and Hiding Record Existence

If a database holds tenants A and B, filtering in Java after reading the full table undermines source-level isolation. Counts, timing, logs, or caches can still leak existence. Apply tenant predicates in the repository; if business rules let an admin view multiple owners within a tenant, still enforce `WHERE tenant_id = :trustedTenantId` before applying role/owner rules.

The policy deciding `403` vs. `404` for unauthorized records must be consistent and must not leak IDs or metadata in error messages. Filtering a list down to empty **is not equivalent** to enforcing single-document read authorization.

## 7. Standalone Java 17 Example: Seeing Pagination Bugs In Memory

`AfterQueryFilteringDemo.java` uses plain Java to simulate a paginated query filtered afterward for Alice. This is **not a Spring class**; its goal is demonstrating the exact paging/counting distortion without assuming annotations ran.

```java
import java.util.List;

public class AfterQueryFilteringDemo {

    record Document(long id, String owner) {}

    public static void main(String[] args) {
        List<Document> all = List.of(
            new Document(1, "alice"),
            new Document(2, "bob"),
            new Document(3, "alice"),
            new Document(4, "bob"),
            new Document(5, "alice")
        );

        // Simulate a DB page returning 3 records before checking owner.
        List<Document> dbPage = all.stream().limit(3).toList();

        // Equivalent to filtering by owner AFTER loading the page.
        List<Document> afterFilter = dbPage.stream()
            .filter(d -> d.owner().equals("alice"))
            .toList();

        long actualVisibleTotal = all.stream()
            .filter(d -> d.owner().equals("alice"))
            .count();

        System.out.println("fetchedPage=" + dbPage.size());
        System.out.println("visiblePage=" + afterFilter.size());
        System.out.println("visibleIds=" +
            afterFilter.stream().map(Document::id).toList());
        System.out.println("rawTotal=" + all.size());
        System.out.println("visibleTotal=" + actualVisibleTotal);
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac AfterQueryFilteringDemo.java
java AfterQueryFilteringDemo
```

Expected stdout:

```text
fetchedPage=3
visiblePage=2
visibleIds=[1, 3]
rawTotal=5
visibleTotal=3
```

The first page fetched 3 records, yet after filtering only 2 remain; the raw total is 5, while Alice's actual visible total is 3. If the real query does not filter ownership before `LIMIT`/`OFFSET`, pagination cannot rely on raw dataset statistics for the actor. This is a query design bug, **not solved by arbitrarily increasing page size**.

## 8. The Right Way: Enforcing Scope Inside Repository Queries

Suppose the app uses Spring Data JPA and users belong to tenants. You can define repository methods so SQL enforces owner and tenant boundaries prior to pagination:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<DocumentEntity, Long> {

    Page<DocumentEntity> findByTenantIdAndOwnerId(
        String tenantId, String ownerId, Pageable pageable);

    Page<DocumentEntity> findByTenantId(
        String tenantId, Pageable pageable);
}
```

This is an **interface template** requiring `DocumentEntity` with `tenantId` and `ownerId` properties plus Spring Data JPA setup; it is not standalone runnable. Derived queries must emit proper tenant/owner clauses; inspect generated SQL, indexes, and test with multi-tenant data. When read access is richer than simple ownership, design explicit predicates/ACLs per policy.

The service branches using **trusted identity and verified authorities**, keeping tenant scoping in both branches:

```java
// Excerpt inside an @Service; AccountPrincipal is application-defined.
@PreAuthorize("hasAuthority('document:read')")
public Page<DocumentEntity> findVisibleDocuments(
        Authentication authentication,
        Pageable pageable) {

    AccountPrincipal actor =
        (AccountPrincipal) authentication.getPrincipal();

    if (authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_REVIEWER"))) {
        return documentRepository.findByTenantId(
            actor.getTenantId(), pageable);
    }

    return documentRepository.findByTenantIdAndOwnerId(
        actor.getTenantId(), actor.getUserId(), pageable);
}
```

In a real app, `Authentication` should come from a Spring Security-controlled source (such as an `@AuthenticationPrincipal` or trusted context inside the service), **never constructed by the caller from a request body**. Allowing reviewers to see every document in the tenant is a testable business assumption, not an inherent Spring privilege. If the principal type is wrong, or tenant, userId, or authority is missing, **deny access** instead of dropping SQL predicates.

Even for administrative users not allowed across tenants, repositories must enforce tenant filters. For richer rules (group ownership, shares, ACLs, parent organizations), predicates must express "allowed" accurately via joins/subqueries or equivalent data-access policies. Use identical predicates for both data and `COUNT` queries while preserving ordering and resource bounds.

### 8.1. Where Should Authorization Live?

| Check | Appropriate location |
|---|---|
| Can the user invoke the read feature? | `@PreAuthorize("hasAuthority('document:read')")` |
| Which tenant/user is calling? | Trusted Authentication/principal |
| Which records may be read? | Queries/repositories scoped by tenant, owner, or ACL |
| May a record be edited/deleted? | Service policy + conditional update/delete at data layer |
| Small pre-loaded result needs a few auxiliary items hidden? | `@PostFilter` can act as an extra layer |
| Batch input allows dropping invalid elements? | `@PreFilter` can work with an explicit contract |
| Batch must be atomic and reject if any element lacks rights? | Validate all inputs + transaction, not `@PreFilter` alone |

## 9. Spring Service Example Using Both `@PreFilter` and `@PostFilter`

The sample below uses a `Document` type with a `getOwner()` getter so SpEL `filterObject.owner` resolves as a JavaBean property. The code requires Spring Security + Spring Context and an application-implemented `DocumentStore` bean. It illustrates wiring and semantics; it is not a standalone Spring Boot app.

File `DocumentFilterService.java`:

```java
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentFilterService {

    private final DocumentStore store;

    public DocumentFilterService(DocumentStore store) {
        this.store = store;
    }

    // Filters elements of the input collection before saveBatch runs.
    @PreAuthorize("hasAuthority('document:write')")
    @PreFilter("filterObject.owner == authentication.name")
    public List<Document> saveBatch(List<Document> documents) {
        return store.saveBatch(documents);
    }

    // Example for a small result set only; findAll does not suit large data.
    @PreAuthorize("hasAuthority('document:read')")
    @PostFilter("filterObject.owner == authentication.name")
    public List<Document> listVisibleSmallSet() {
        return store.findAll();
    }

    public interface DocumentStore {
        List<Document> saveBatch(List<Document> documents);
        List<Document> findAll();
    }

    public static final class Document {
        private final long id;
        private final String owner;

        public Document(long id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public long getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }
}
```

**How to read this:**

- `saveBatch` carries `@PreFilter`: the target service sees elements whose `owner` matches `authentication.name`; **however, filtering a property on an input object does not prove the caller owns that record in the database**. If a caller sends `Document{id=7, owner="alice"}` when ID 7 belongs to Bob in the DB, trusting caller-supplied fields breaks authorization. Load/verify authoritative DB records before writing.
- `@PreAuthorize("document:write")` acts as an overall gate on the method and does not replace per-record owner checks. Never assume holding the permission suffices for every ID.
- `listVisibleSmallSet` demonstrates `@PostFilter` clearly; avoid using this pattern with `findAll()` on large datasets, paged/cursor APIs, or multi-tenant data requiring source isolation.
- Supporting element removal depends on `List` mutability/compatibility; supply a mutable collection in tests and verify your exact Spring Security version and storage behavior.
- Examples can invoke policy beans from `@PreFilter`/`@PostFilter`, such as `@documentAccess.canRead(filterObject, authentication)` for complex checks; that bean must rely on trusted identity and data. Per-item SpEL callbacks can trigger N+1 queries; evaluate N+1 and caching carefully.

If business logic requires **all-or-nothing batch saves**, do not expose `saveBatch` above as an atomic endpoint; instead verify every ID and wrap inside a transaction to fail the entire batch if any element violates policy.

## 10. Testing Exact Semantics, Including Negative Cases

To confirm annotations take effect, tests must invoke the **Spring-managed bean through its proxy**, with `@EnableMethodSecurity`, configured authentication/authorities, and mocked repositories. With `@WithMockUser` (from `spring-security-test`), you can model users for synchronous Servlet tests; the annotation supports security expressions tied to the request/test context.

Minimum test matrix:

| Case | Raw input/result | Expected outcome | Reason |
|---|---|---|---|
| Alice calls method with `document:read` | 2 Alice, 1 Bob | `@PostFilter` returns Alice's 2 | Verifies per-element filtering |
| Alice lacks `document:read` | Any list | Method denied before repo runs | Verifies `@PreAuthorize` |
| Alice calls `saveBatch` | 2 Alice, 1 Bob in input list | Method receives Alice's 2 if container valid | Verifies `@PreFilter` |
| Alice lacks `document:write` | Any batch | Write forbidden | Whole-method authority gate |
| List contains zero Alice items | 3 Bob | Filtered result can be empty, no auto-403 | Understand filtering semantics |
| Alice queries page of 10, only 3 hers | DB returns page of 10 then filters | Test exposes short page and wrong count | Proves query-level filtering is needed |
| Tenant A vs. tenant B | Same owner string, different tenant | No tenant B data leaks in tenant A query | Tenant isolation |
| Bob updates Alice's ID forging owner=Bob | Forged request object | Rejected when checked against DB | Prevents trusting client attributes |
| Internal call via `this` | Inner method annotated | Test catches advice bypass | Proxy boundary limitation |
| Closed stream or immutable collection | Special inputs | Test against real container/contract | Avoids assuming every type filters cleanly |

Example JUnit 5 test excerpt with a Spring-injected bean (requires proper test class imports and fixtures):

```java
@WithMockUser(username = "alice", authorities = {"document:read"})
@Test
void postFilterRemovesOtherOwners() {
    List<Document> actual = filterService.listVisibleSmallSet();

    assertThat(actual).extracting(Document::getOwner)
        .containsOnly("alice");
}
```

This is only a test excerpt: `filterService` is an injected Spring bean, `Document` is the fixture type, `assertThat` is AssertJ, and `DocumentStore` is mocked to return both Alice and Bob documents. If the fixture only returns Alice's documents, the test never genuinely verifies `@PostFilter`.

**For `@PreFilter`:** pass an `ArrayList` or verified compatible collection containing both Alice's and Bob's entries, and mock the store to inspect the arguments the method actually received. Do not assume immutable `List.of(...)` inputs work without verifying framework filtering semantics. Also assert tests do not modify Bob's DB row just because SpEL filtered a request DTO copy.

**For repository queries:** write integration tests against a test database holding multiple owners/tenants, checking `content`, `totalElements`, `hasNext`/`totalPages`, ordering, and performance. For native SQL/JPA queries, verify owner/tenant predicates appear before `LIMIT/OFFSET`; never assert only "HTTP 200."

## 11. Common Pitfalls

1. **Using `@PostFilter` to hide `findAll()` costs:** eager list queries still fetch all rows before in-memory filtering.
2. **Using `@PostFilter` on `Page<T>` as automatic permission paging:** metadata/offsets/counts are not reliably recomputed.
3. **Confusing filtering with denial:** an empty list from `@PostFilter` differs from an authorization error; `@PreFilter` may allow partial batches through.
4. **Trusting client-supplied fields:** `owner` inside a DTO can be forged; verify against authoritative entities and the principal.
5. **Ignoring tenants:** `owner="alice"` does not prove the record belongs to the allowed tenant, especially when usernames are not globally unique.
6. **Placing `@PostFilter` after side-effecting methods:** does not undo writes, deletes, sent emails, or published events.
7. **Forgetting `@EnableMethodSecurity`:** annotations look right yet no interceptor runs.
8. **Self-invocation:** calling `this.someMethod()` inside the same bean can bypass AOP proxies.
9. **Wrong SpEL property:** `filterObject.owner` needs a readable property; map entries need `filterObject.value.owner`.
10. **Incompatible containers:** nulls, immutable collections, consumed streams, or unsupported return types cause errors or unexpected behavior.
11. **Per-item DB queries inside expressions:** hitting the DB per element creates N+1 overhead.
12. **Wrong identity source:** reading tenant from client headers instead of the verified principal leads to BOLA/IDOR.
13. **Ignoring transaction and stream timing:** reading after a transaction/session closes can fail; holding sessions open too long incurs overhead.
14. **Skipping boundary tests:** testing only admins or one user without cross-owner/cross-tenant data misses negative cases.
15. **Using `@PreFilter` as a security gate for atomic batches:** drops unauthorized items and still writes the rest, breaking all-or-nothing contracts.
16. **Protecting only controllers:** other entry points (jobs, message consumers, other services) can call methods outside HTTP rules; put policies on services and repositories.

## 12. Reactive Stacks and Safe Strategies for Large Datasets

In WebFlux / reactive Spring Security, enable reactive method security (`@EnableReactiveMethodSecurity`) and obtain identity from Reactor `Context` when needed. Functions returning `Mono`/`Flux` must not be treated as synchronous `List`s; **never call `block()` or manual `subscribe()`** inside policies or filters to force a decision.

Illustrative **excerpt**: `ReactiveDocumentRepository` exposes a method returning `Flux<Document>` implemented to scope queries by tenant/user at storage level:

```java
return reactiveDocumentRepository
    .findByTenantIdAndOwnerId(actor.tenantId(), actor.userId())
    .filter(document -> document.isVisible())
    .map(this::toDto);
```

Here `actor` is the authenticated principal inside the reactive pipeline, never taken from untrusted input. `filter` is only extra logic **after the repository has scoped results**; reactive `filter` is not a SQL predicate and does not fix precomputed pages/counts. When policies need async per-item checks, `filterWhen`/`flatMap` can work with bounded concurrency and proper error handling, yet still never replaces source-level ACL/tenant queries.

For large lists, the stronger approach is usually:

1. **Data-layer predicates** for tenant, owner, share grants, and ACLs.
2. **Pagination and counts inside the exact same permission scope**.
3. **Minimal projections/DTOs** to avoid loading unneeded sensitive columns.
4. **Method-level authorization** for overall features, plus resource policies verifying ID/owner/state on writes.
5. **Post-query filtering** only on already-bounded, appropriately sized datasets with explicit contracts.

## 13. Implementation Checklist

- [ ] `@EnableMethodSecurity` or stack-appropriate method security is active; real calls go through Spring proxies.
- [ ] Decided clearly between **denying the whole method**, **filtering partial input**, or **filtering output**.
- [ ] Used `@PreAuthorize`/`@PostAuthorize` when whole-call ALLOW/DENY is required, avoiding filter misuse.
- [ ] `filterObject` and `authentication` expressions read valid properties and trusted principals.
- [ ] With multiple input collections, `filterTarget` selects the right parameter and parameter names are preserved/annotated.
- [ ] Post-query filtering is not used as the sole defense for multi-tenant or million-row datasets.
- [ ] Repositories apply `WHERE`/ACL clauses before `LIMIT/OFFSET` and keep `COUNT` aligned.
- [ ] Never used `@PostFilter` to fix aggregates, paging metadata, or roll back side effects.
- [ ] Batch writes define explicit all-or-nothing vs. partial contracts with transactions/optimistic locking where needed.
- [ ] Tested both visible and restricted rows, multiple tenants, pages, self-invocation, and stream/collection edge cases.
- [ ] In WebFlux, never detached subscriptions; kept security context inside the Reactor pipeline.

## 14. References

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): guide to `@PreFilter`, `@PostFilter`, `filterObject`, supported collection types, and `@EnableMethodSecurity`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor `Context` and reactive methods.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): request/HTTP authorization vs. method-level authorization.
- [OWASP API1:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): why ID-based queries and per-resource permissions must be checked.

**Key takeaway:** `@PreFilter` filters argument elements **before** the target method executes; `@PostFilter` filters return elements **after** the target method runs. They are useful at method boundaries, yet **do not replace data-layer authorization**: pagination, statistics, tenants, ownership, side effects, and large datasets must be constrained in queries/transactions and verified with real data.