# Query Filtering vs. @PostFilter: Choosing the Appropriate Execution Layer

## 1. Goal: Placing Access Control at the Right Layer

When a method returns a list of records, there are two related but distinct questions:

1. **Is the caller allowed to perform the operation?** For example, do they have permission to open the document listing page.
2. **Among the records that could be found, which records is the caller permitted to view?** For example, only data belonging to the current tenant, documents owned by them, or validly shared documents.

In Spring Security, `@PreAuthorize` typically answers the first question. The second question can be solved in **the data query** (SQL/JPQL/Criteria/Specification, ACL join, database Row-Level Security) or at **the method's return boundary** using `@PostFilter`. The two approaches do not have the same cost, execution timing, or pagination semantics.

**Selection rule:** For large stored datasets, search queries, pagination, counting, multi-tenancy, or lists that can grow unboundedly, filter permissions directly in the query. `@PostFilter` is suitable when the candidate object set is already **small, bounded, in memory**, requires per-element filtering at the method boundary, and does not need accurate source pagination metadata.

Whichever approach you choose, **the permission policy must be enforced before data is exposed to the user**. Choosing the checking layer only determines where it is enforced and how correctness is proven.

## 2. Execution Layers and When Data Is Excluded

~~~text
HTTP request
  │
  ▼
SecurityFilterChain: authentication, URL rules
  │
  ▼
Service via Spring proxy: @PreAuthorize (permission to call operation)
  │
  ▼
Repository/Query: WHERE tenant + status + owner/ACL
  │                    │
  │                    └─ ORDER BY → LIMIT/OFFSET/cursor → COUNT in same scope
  ▼
Service result
  │
  ├─ When @PostFilter is present: evaluate each element of supported return type
  │
  ▼
Controller / serializer / client
~~~

`@PostFilter` is evaluated **after the method completes**. It does not push Spring EL expressions down to the database, does not turn `repository.findAll()` into a query with `WHERE`, and cannot restore valid records previously cut off by `LIMIT`.

Distinguish the tools:

| Tool | Timing | Proper Responsibility | Cannot Automatically Do |
|---|---|---|---|
| `@PreAuthorize` | Before calling the method | Allows/denies the operation, can reference parameters and principal | Does not automatically add row-level filters to repositories |
| Query predicate / ACL / RLS | During data retrieval | Restricts records at the source, aligns content and count | Does not replace all operation-level execution permission checks |
| `@PostFilter` | After method, before caller | Removes elements failing the expression from a supported result structure | Does not reduce queried rows; does not recompute source pagination |
| `@PostAuthorize` | After method | Accepts/denies **the entire result** based on `returnObject` | Does not filter a list down to valid elements |
| DTO/projection | Before returning response | Restricts exposed fields | Does not replace checking which records may be viewed |

Also do not confuse `@PreFilter` with query filtering: `@PreFilter` filters **input collection/array/map/stream parameters before the method runs**, and does not automatically translate into SQL conditions.

## 3. @PostFilter Mechanism and Limitations to Remember

Enable method security in Spring configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Then a service bean can declare:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class PreviewService {
    private final PreviewSource previewSource;

    public PreviewService(PreviewSource previewSource) {
        this.previewSource = previewSource;
    }

    @PostFilter("filterObject.ownerUsername == authentication.name")
    public List<DocumentPreview> preview() {
        return new ArrayList<>(previewSource.loadAtMost(40));
    }
}
~~~

This is **Spring integration code**; `PreviewSource` and `DocumentPreview` are application components that must exist, not a standalone program to compile with a single `javac` command. The example assumes the policy only allows viewing objects owned by the current username. If the policy also requires tenant, group, or ACL checks, the expression or corresponding guard layer must verify all of those conditions.

Key points:

- `filterObject` is the element being evaluated; for `Map`, it represents a `Map.Entry`, so reading a value's property typically uses `filterObject.value.ownerUsername`.
- According to Spring Security documentation, post-filtering is designed for **collections, arrays, maps, and open streams**. Do not assume every wrapper type, especially `Page<T>` and `Optional<T>`, is a supported collection. Check exact return types and versions before using.
- For collection results, filtering may mutate the returned collection; for instance, use `new ArrayList<>(...)` to decouple from shared/cached sources. Avoid directly returning immutable collections or shared mutable objects without checking filter behavior.
- The expression is evaluated per element. A permission check calling a database/API for each element creates an **N+1** risk and time proportional to result size.
- Method security usually runs through a Spring AOP proxy. Self-calling `this.preview()` within the same bean bypasses the proxy, so the annotation may be skipped. Test through a real Spring bean.
- `@EnableMethodSecurity` must be enabled in the application; adding the Spring Security dependency does not mean method security is automatically active.

You can use `@PostFilter("hasPermission(filterObject, 'read')")` once an appropriate permission model such as `PermissionEvaluator` is configured. However, the expression does not automatically generate efficient ACL queries; if each `hasPermission` call hits the DB, bound the set and consider batching/pushdown.

## 4. Decision Table: Which Layer to Choose?

| Scenario | Layer That Should Own Primary Filtering | Explanation |
|---|---|---|
| List/search API over tables with thousands to millions of rows | Query/repository | Avoids loading denied records, allows proper indexing and pagination |
| Has `Pageable`, `Page<T>`, `Slice<T>`, cursor, or COUNT | Query/repository | Data and metadata must come from the same authorized set |
| Multi-tenant data needing strict isolation | Query with tenant predicate; consider DB RLS | Prevents cross-tenant reads at the source, applies across multiple access paths |
| Permissions by owner, group, share table, or ACL expressible via JOIN/EXISTS | Query/ACL-aware repository | Accurate counts, avoids per-object permission checks |
| List of a few dozen objects already validly loaded, unpaginated | `@PostFilter` can fit | Readable expression, data already bounded before checking |
| Aggregated list from multiple non-DB sources, small normalized dataset | Filter in service; `@PostFilter` if return type and lifecycle are clear | Not every source supports predicates; still bound object count and avoid exposing intermediate data |
| Reading **one** document by ID | Query by ID + scope; `@PreAuthorize`/`@PostAuthorize` when appropriate | A single object is not a collection of elements for `@PostFilter` |
| Only want to hide sensitive fields within an object | DTO/projection or field-level policy | `@PostFilter` filters **elements**, it does not strip internal properties |
| Policy depends on computed results that cannot be pushed to query | Service/domain authorization; can post-check small sets | Needs a clear model for pagination, cost, and handling denials |
| Shared policy across multiple clients/workers/direct DB queries | Enforce at data layer, optionally combined with RLS | Protects read paths that do not pass through one specific service |

**A useful diagnostic question:** If the `@PostFilter` step were removed, would the current query be reading thousands of records the user is not authorized to view? If yes, you should normally fix the design at the data layer rather than just scaling post-filtering.

## 5. Example 1 — Query-First for Paginated APIs

Suppose there is a JPA entity `Document` with properties `id`, `tenantId`, `ownerUsername`, and `deleted`. Example policy: a user only sees their own non-deleted documents within the current tenant.

The repository enforces authorization **in both the content query and COUNT**:

~~~java
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository extends JpaRepository<Document, Long> {

    @Query(
        value = """
            select d from Document d
            where d.tenantId = :tenantId
              and d.ownerUsername = :username
              and d.deleted = false
            """,
        countQuery = """
            select count(d) from Document d
            where d.tenantId = :tenantId
              and d.ownerUsername = :username
              and d.deleted = false
            """
    )
    Page<Document> findVisible(
        @Param("tenantId") UUID tenantId,
        @Param("username") String username,
        Pageable pageable
    );
}
~~~

The service passes only **verified scope** down to the repository:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;
    private final CurrentAccessScope accessScope;

    public DocumentQueryService(
        DocumentRepository repository,
        CurrentAccessScope accessScope
    ) {
        this.repository = repository;
        this.accessScope = accessScope;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Page<Document> findMine(Pageable pageable) {
        return repository.findVisible(
            accessScope.requiredTenantId(),
            accessScope.requiredUsername(),
            pageable
        );
    }
}
~~~

The snippets above are illustrative code for a Spring Data JPA project that already has a `Document` entity and application bean `CurrentAccessScope`. This scope bean must obtain information from a **verified** principal/token, deny if principal or tenant is missing, and never accept arbitrary tenant/user from HTTP query parameters. `@PreAuthorize` checks operation execution permission; the query checks **per-row** permission.

When the policy also covers shared documents, expand the predicate accurately per permission: e.g., `owner = currentUser OR EXISTS(permission for currentUser)` in **both SELECT and COUNT**. With one-to-many joins, check for duplicates and how `DISTINCT/COUNT(DISTINCT ...)` is used. Do not put obscure logic into SpEL if database JOIN/EXISTS solves it more efficiently.

If business conditions vary based on client filters, build a shared predicate builder for business conditions + permissions, and apply it consistently to both content and count queries. With Spring Data JPA, you can use `Specification`/Criteria/Querydsl for dynamic policies; verify the exact version when using a separate countSpec API.

**Conditions for trustworthy results:** `WHERE` by permission, stable `ORDER BY` (prefer adding a unique key), pagination, and COUNT must all agree on the same dataset. Only use `Page` when totals are truly needed; `Slice` or keyset/cursor fits when the UI only needs load-more.

## 6. Example 2 — `@PostFilter` for a Small Bounded Set

Suppose a method needs to return at most 40 previews already loaded into memory and does not publish totals/pages. When the source lacks an efficient owner-filtering method or the list is aggregated from multiple sources, post-filtering at the service boundary can be clear enough.

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class SmallPreviewService {
    private final PreviewSource source;

    public SmallPreviewService(PreviewSource source) {
        this.source = source;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @PostFilter("filterObject.ownerUsername == authentication.name")
    public List<DocumentPreview> previewForCurrentUser() {
        return new ArrayList<>(source.loadAtMost(40));
    }
}
~~~

In this example, `loadAtMost(40)` is **the source's actual contract**: it must enforce the maximum data volume; do not merely name the method that way while still loading the entire table. If elements in caches or shared sources contain sensitive data, protect intermediate/read paths (logs, traces, cache keys, lifecycle), rather than relying solely on removing items before the controller.

Suppose the source has data `[(A, "an"), (B, "binh"), (C, "an")]`; user `an` receives `[A, C]`. The result is a **filtered list**, not a `Page` with accurate metrics. If the UI requires "return a full 20 viewable elements" while the source only loads 20 raw elements, `@PostFilter` does not automatically fetch more valid elements from subsequent batches.

You can use `@PostFilter` as an additional verification layer after query-first when the set is already small, but weigh the cost and potential policy duplication. If query policy and annotation policy diverge, one might miss a permission or wrongly drop data. Maintain a shared policy specification and cross-check tests.

## 7. Choosing Enforcement Points Across System Boundaries

### Controller and Spring Security Filter Chain

The controller receives input, validates business filters, and calls the service. Spring Security at the HTTP layer checks authentication/URL rules. Do not write `stream().filter(...permission...)` in the controller as the primary data authorization layer, because the service may be called from jobs, message consumers, or other endpoints.

### Service and Method Security

The service represents **use cases** and protected boundaries: who can invoke the operation, which policy applies, and step order. `@PreAuthorize` is usually convenient for blocking operations before reading the DB. For loading by ID, you can use scoped queries `WHERE id=:id AND tenant=:tenant AND ...`; `@PostAuthorize` fits when checking an entire single result after the method is needed, keeping in mind data has already been retrieved by that time.

### Repository, Search Engine, Remote Data Source

The repository should receive a normalized permission scope and translate it into filtering conditions executed directly at the data level. Same for Elasticsearch or remote services with filtering APIs: send permission filters as part of the query if the trusted source enforces them properly. However, an arbitrary client-sent parameter **does not** represent permission. If the source cannot guarantee authorization, the service must post-check thoroughly and choose appropriate pagination/counting, or reject API styles requiring exact results that the source cannot fulfill.

### Database Row-Level Security

RLS can be an extra layer of defense when multiple code paths read the same table. However, the session/connection must receive the right identity and tenant, especially with connection pooling; test data, COUNT, and reset behavior when connections are reused. RLS does not automatically replace use-case invocation checks, sensitive field access checks, or authorization in non-DB systems.

## 8. Complex Permissions: Do Not Push N+1 Down to Individual Elements

Policies often go well beyond `owner == username`:

- Users can view documents belonging to groups they are members of.
- Users have permissions through a sharing table.
- Administrators have view permission within a tenant, but not across tenants.
- Documents in sensitive states require separate extra permissions.

With large lists, an expression like `@PostFilter("hasPermission(filterObject, 'read')")` can trigger many independent ACL checks, even one query per object. When permissions can be expressed in the DB, use `EXISTS`/JOIN predicates combined with scope so the database evaluates the set once, with indexes and consistent COUNT. If the policy relies on a remote authorization service, consider batch authorization decisions and bound the candidate set; set clear load limits and error reporting.

**Avoid policy drift:** the same "read document" permission should not have different meanings between list APIs and detail APIs. Write tests sharing scenarios across query predicates, service decisions, and per-ID detail access. If two layers cannot be guaranteed to share identical policies, clarify which layer is primary enforcement and which is defense-in-depth.

## 9. What @PostFilter Does Not Solve

### Cannot Fix Pagination Metadata

Suppose the database fetches a page of 5 raw records, and only 2 are viewable. Post-filtering leaves 2 records, unable to pull the next valid records from the database to fill the page; the original `COUNT` may also include unauthorized data. If `Page<T>` is needed, permissions must be applied in both the content query and COUNT. Never use `filteredPage.size()` as `totalElements` of the entire dataset.

### Does Not Guarantee Field-Level Authorization

A `Document` may be viewable while containing a `secretToken` field or internal info that must not be exposed. `@PostFilter` only decides to keep or drop **the whole element**. Use DTOs/projections and serialization controls tailored to each use case.

### Does Not Control Side Effects Before Returning Results

Before `@PostFilter` runs, the method may have already queried the database, written logs, cached data, or called other systems. Therefore, restrict access as early as possible, protect logs/caching, and do not treat post-filtering as the sole measure in every case.

### Does Not Automatically Resolve Consistency or Race Conditions

If an object's permissions change between querying and serialization, define consistency/transaction boundaries appropriate to business rules and sensitivity. Every subsequent endpoint/detail call must still check permissions against current state. Cache by tenant/user/scope and invalidate on permission changes when data is personalized.

### Not Suitable by Default for All Result Types

`Page<T>`, `Optional<T>`, or custom wrappers are not the default supported types documented for `@PostFilter`. Do not attach the annotation by guesswork assuming metadata will be fixed; use query filtering, `@PostAuthorize`, or a service guard matching the result type.

## 10. Standalone Java 17 Demo: Same Policy, Two Timings

The example simulates fetching the first page before and after applying permissions. It uses in-memory Java Streams to illustrate **order of operations**, not to simulate a SQL optimizer or real database cost.

File `FilteringLayerDemo.java`:

~~~java
import java.util.List;

public class FilteringLayerDemo {
    record Doc(int id, String tenant, String owner) { }

    private static boolean canRead(Doc doc) {
        return doc.tenant().equals("north")
                && doc.owner().equals("an");
    }

    public static void main(String[] args) {
        List<Doc> database = List.of(
                new Doc(1, "north", "binh"),
                new Doc(2, "north", "an"),
                new Doc(3, "south", "an"),
                new Doc(4, "north", "binh"),
                new Doc(5, "north", "an"),
                new Doc(6, "north", "an")
        );
        int size = 2;

        List<Integer> queryFirst = database.stream()
                .filter(FilteringLayerDemo::canRead)
                .limit(size)
                .map(Doc::id)
                .toList();

        List<Integer> postFilter = database.stream()
                .limit(size)
                .filter(FilteringLayerDemo::canRead)
                .map(Doc::id)
                .toList();

        long visibleTotal = database.stream()
                .filter(FilteringLayerDemo::canRead)
                .count();

        System.out.println("Query-first page: " + queryFirst);
        System.out.println("Post-filtered page: " + postFilter);
        System.out.println("Authorized total: " + visibleTotal);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac FilteringLayerDemo.java
java FilteringLayerDemo
~~~

Exact stdout:

~~~text
Query-first page: [2, 5]
Post-filtered page: [2]
Authorized total: 3
~~~

Here, user `an` in tenant `north` has three documents: IDs 2, 5, 6. If policy is applied before taking at most two elements, the first page is correctly `[2,5]`. If taking two raw elements first and then filtering, only `[2]` remains. For an unpaginated preview of a few objects, the latter may make sense; for paginated lists, the example shows why query-first must be chosen.

## 11. Testing the Execution Layer Choice

A meaningful test suite must test **permission behavior on real data**, not just check that annotations are present:

1. **Query-first:** with two tenants, two users, and shared records, verify list + COUNT + `Page`/`Slice` reflect only viewable records; test empty pages, last pages, and sorting with a unique tie-breaker key.
2. **Method security:** test through the Spring bean/proxy with principals having and lacking authorities; make direct internal bean calls to catch proxy-bypass scenarios; test `@PostFilter` with lists containing both valid and invalid elements.
3. **Return types and sources:** test mutable collections, maps (`filterObject.value`), and open streams if actually used; confirm shared caches/lists are not mutated and do not assume `Page` is supported.
4. **Complex ACLs:** owner, shared, member, tenant-scoped admin, revoked permissions; both list queries and ID lookups must be consistent. Use data with multiple permission records pointing to one document to detect duplicates/wrong COUNT.
5. **Performance:** monitor rows read, query counts, permission evaluator N+1s, and query times as dataset size grows; test the case where 100% of records are denied while the client requests the first page.
6. **Security:** do not leak unauthorized content or totals, do not use client-supplied tenants as scope, do not expose sensitive fields, and do not share personalized cached data across users.

If permissions are enforced in both the query and `@PostFilter`, have cross-check tests running the same policy cases to avoid "query passes it but annotation drops it" or "annotation passes it when an access path forgets the query filter".

## 12. Wrong Choices and How to Fix Them

**Attaching `@PostFilter` to a service returning `Page<Document>` thinking the annotation will also filter totals.** This relies on a return type outside the documented post-filterable collection types and does not solve count/pagination. **Fix:** put permission predicates into the `Page` query and COUNT query.

**Using `repository.findAll()` then `@PostFilter` on a large table.** Loads excessive unnecessary data, increases memory, CPU, and intermediate data exposure risks. **Fix:** filter by scope in the repository; only post-filter very small sets when needed.

**Using `@PreAuthorize("hasRole('USER')")` and assuming every row is safe.** The annotation allows calling the method; it does not automatically restrict individual rows. **Fix:** add per-object permission conditions at the source.

**Letting the controller build a client-supplied tenant condition.** Users can alter the tenant in requests. **Fix:** derive scope from verified authentication/identity and enforce scope on all read paths.

**Using the same cached mutable list as the return value of `@PostFilter`.** Collection filtering can mutate shared lists, corrupting subsequent requests' results. **Fix:** isolate collections, prefer immutable DTOs after filtering, and design caches by scope.

**Filtering per element with `hasPermission` without measuring query counts.** On large lists, N+1 causes slowness and scales load with data volume. **Fix:** push ACLs down to query predicates or batch permission decisions.

**Filtering only the list while forgetting detail APIs or nested fields.** Can allow direct access by ID or leak data via serialization. **Fix:** protect ID-based queries and projections/field policies as well.

## 13. Execution Layer Selection Checklist

Before finalizing a design, answer all of these questions:

- Can the result set size grow unboundedly, or does it have pagination, total counts, or cursors? **Yes → prefer query-first.**
- Can permission conditions be expressed via owner/tenant/group/ACL in the query? **Yes → push down to the data layer and verify COUNT with the same predicate.**
- Is the set already small, bounded, without pagination metadata, and needing per-object post-checking at the method boundary? **Yes → consider `@PostFilter`.**
- Are you controlling use-case invocation permission or per-record permission? **Invocation permission → `@PreAuthorize`; per-record permission → appropriate predicate or post-filtering.**
- Is there a single object or fields that need hiding? **Use object-level authorization and DTOs/projections**, not `@PostFilter` as a substitute.
- Are principal/tenant obtained from trusted sources, and are multiple users/tenants, method security proxies, and performance tested? **Must be yes.**

**Practical conclusion:** Choose query filtering as the primary permission enforcement layer when searching, counting, or paginating stored data. Use `@PostFilter` intentionally for a small, bounded result set at the method boundary. Combine `@PreAuthorize` to block unauthorized operations and verify other access paths with the same policy.

## References

- [Spring Security Reference – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostFilter`, `filterObject`, result types, and in-memory costs.
- [Spring Data JPA Reference – Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html): building composable query predicates.
- [Spring Data JPA Reference – Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): `Page`, `Slice`, COUNT, and pagination semantics.
