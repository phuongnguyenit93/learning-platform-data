# Pagination, Total Counts, and Skew When Filtering After Querying

## 1. Why Must Pagination and Permission Filtering Go Together?

In Spring Security, method security can check method invocation permission with `@PreAuthorize`, or post-filter individual elements in the result with `@PostFilter`. However, if the repository already applied `LIMIT/OFFSET` and the code then removes unauthorized records, the returned page no longer accurately represents the dataset the user is permitted to access.

Distinguish two sequences:

- **Correct:** filter by business conditions **and access permissions** inside the query, apply stable ordering, then paginate; compute COUNT on the same authorized set.
- **Problematic:** fetch a page from unfiltered data, then delete elements the user is not allowed to see; keep the original query's total/count/hasNext intact.

For paginated APIs, the source of truth for `content`, `totalElements`, `totalPages`, and `hasNext` must be **the exact same viewable dataset**.

## 2. Visual Example

Suppose the dataset has 12 records with IDs 1 through 12. User A is only allowed to see even IDs: `[2,4,6,8,10,12]`. The client requests page 0, size 5.

| Metric | Paginate First, Then Filter Permissions | Filter Permissions First, Then Paginate |
|---|---|---|
| Page 0 | `[2,4]` | `[2,4,6,8,10]` |
| Page 1 | `[6,8,10]` | `[12]` |
| Page 2 | `[12]` | None |
| Total records if keeping original query metadata | 12 (**wrong for user A**) | 6 |
| Total pages | 3 (**wrong**) | 2 |

The raw query for the first page might return `[1,2,3,4,5]`. After `@PostFilter`, only `[2,4]` remain; even though valid records have not run out, the page is short by three elements. You cannot conclude from `content.size() < size` that this is the last page when permissions are filtered **after** querying.

Similarly, `totalElements=12` can leak the count of records outside the access scope. You cannot fix this with `totalElements=content.size()`, because that is only the number of valid elements in one raw page, not the number of valid elements across the entire dataset.

## 3. Mechanism and Limitations of `@PostFilter`

`@PostFilter` evaluates an expression on elements of the method result after the method has executed. It does not automatically add `WHERE` to SQL, nor does it cause the database to recompute `COUNT` by permission. Therefore, it is better suited for small finite sets already in memory, rather than serving as the primary mechanism for paginated endpoints.

Illustrative example of post-filtering a list:

~~~java
@Service
class DocumentService {
    private final DocumentRepository repository;

    DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PostFilter("filterObject.ownerUsername == authentication.name")
    public List<Document> listCandidates() {
        return repository.findAll();
    }
}
~~~

The snippet above is only a Spring component, depending on the application's `Document` and `DocumentRepository` classes; it is not a standalone Java program. The annotation requires method security to be enabled, such as `@EnableMethodSecurity`. With proxy-based Spring AOP, internal calls like `this.listCandidates()` usually do not go through the interceptor, so do not rely on annotations along that call path.

Do not assume `@PostFilter` automatically supports every wrapper like `Page<Document>` or automatically adjusts `Page.getTotalElements()`. You must check the exact supported return types in the Spring Security version in use. Even when elements can be filtered, pre-built pagination metadata does not automatically become the post-authorization COUNT.

## 4. Common Skew Issues

### Under-filled Pages

Unauthorized records occupy slots in `LIMIT/OFFSET`. Subsequent valid records are not automatically pulled up to fill the gaps. Users may see empty pages sitting in between pages that still contain valid records.

### Inflated Totals and Page Counts

`COUNT(*)` using only general business conditions counts other users' or other tenants' documents as well. Metadata can be wrong while simultaneously leaking dataset size outside the permitted scope. COUNT using the exact same permission, status, and filter policy is mandatory if the API publishes exact totals.

### `hasNext` Becomes Unreliable

`hasNext` of an unauthorized set does not accurately tell whether any **viewable** elements remain on later pages. Likewise, `content.size() < size` after post-filtering does not prove valid data is exhausted.

### Skew Under Mutable Data

OFFSET pagination can duplicate or skip data when others insert/delete records between calls. Post-filtering makes uneven short pages even harder to reason about. Sorting needs a unique tie-breaker key, such as `createdAt DESC, id DESC`, and cursor/keyset pagination can be helpful for large or frequently changing lists.

### Cost and Exposure Risks

Reading unauthorized records and checking each record in Java increases queried rows, N+1 ACL checks, CPU, and memory. It also gives unauthorized data a chance to pass through mappers, logging, or caching before being discarded. Pushing permission predicates down to the query layer reduces this surface.

## 5. How to Design Queries Safely

Permission conditions must originate from verified identity/tenant, combined with business filters before pagination. Example of a system allowing users to view active documents belonging to themselves in the current tenant:

~~~java
public interface DocumentRepository extends JpaRepository<Document, Long> {
    @Query(
        value = """
            select d from Document d
            where d.tenantId = :tenantId
              and d.ownerUsername = :username
              and d.active = true
            """,
        countQuery = """
            select count(d) from Document d
            where d.tenantId = :tenantId
              and d.ownerUsername = :username
              and d.active = true
            """
    )
    Page<Document> findVisible(
        @Param("tenantId") UUID tenantId,
        @Param("username") String username,
        Pageable pageable
    );
}
~~~

In the service, determine permissions from a trusted principal:

~~~java
@Service
public class DocumentQueryService {
    private final DocumentRepository repository;
    private final CurrentScope currentScope;

    public DocumentQueryService(
        DocumentRepository repository,
        CurrentScope currentScope
    ) {
        this.repository = repository;
        this.currentScope = currentScope;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Page<Document> listVisible(Pageable pageable) {
        return repository.findVisible(
            currentScope.requiredTenantId(),
            currentScope.requiredUsername(),
            pageable
        );
    }
}
~~~

Both snippets are illustrative integration code, assuming a `Document` entity and application abstraction `CurrentScope`. `CurrentScope` must derive trusted tenant/user from authentication, never directly reading a client-submitted `tenantId` or `username` parameter and treating it as the authorization scope.

`@PreAuthorize` decides whether the user is allowed to invoke the method; it **does not automatically** restrict individual rows. Predicates in the repository determine which data enters the Page. If the policy allows viewing shared, group, or ACL documents, the predicate must fully express those cases; the owner-only condition above is only valid for an owner-only policy.

When using `Specification`, Criteria API, or Querydsl, keep the exact same permission conditions for both content and COUNT queries. When joining multiple permission rows could produce duplicates, handle `DISTINCT` and `COUNT(DISTINCT ...)` appropriately to avoid inflating totals.

## 6. Processing Order

1. Authenticate the request and extract principal, tenant, and authorities from a trusted context.
2. Check permission to execute the list action, such as `document:read`.
3. Build the per-record permission predicate and combine it with business filters.
4. Sort stably using the primary field and a unique tie-breaker key.
5. Execute SELECT with authorized predicates, then apply OFFSET/LIMIT or cursor.
6. When `Page` is needed, execute COUNT on **the exact same set of conditions**; when totals are not needed, consider `Slice`.
7. Return content, page info, and metadata matching the viewable dataset.

~~~text
Authentication -> trusted access scope
                          |
Business filters ---------+--> WHERE (authorized AND business)
                                      |
                              stable ORDER BY
                                      |
                              LIMIT / cursor
                                      |
                              authorized content
                                      |
                    COUNT (same WHERE), if requested
~~~

If the database uses Row-Level Security (RLS), ensure the security context is set properly on the connection/session for SELECT and COUNT, and is reset per pool lifecycle; verify this with integration tests.

## 7. `Page`, `Slice`, and Cursor

| Option | What Does It Contain? | When to Use |
|---|---|---|
| `Page<T>` | Content, total elements, total pages | UI needs exact totals; permission-scoped COUNT can be resource-intensive |
| `Slice<T>` | Content and whether a next slice exists | UI only needs "Load more", avoiding COUNT |
| Keyset/cursor | Continues from a stable sort key | Large data, deep OFFSET, or frequent mutations |

All three require permission predicates at the source. With cursors, use deterministic sort keys and protect cursors from tampering when they carry sensitive info or determine access scope. Cursors do not grant extra permissions; every request must still re-verify scope.

If an unavoidable policy cannot be pushed down to the database and must be post-checked, you can scan multiple batches to find `size+1` valid elements and determine `hasNext`. In that case, track the **source scan position**, set resource limits, and account for changing data. Do not claim an exact `totalElements` without counting the entire viewable set. Usually `Slice` or cursor has clearer semantics.

## 8. Java 17 Demo: Proving Filter/Pagination Order

The standalone Java 17 example below reproduces the exact short-page bug when filtering permissions after `limit`:

~~~java
import java.util.List;

public class PaginationDemo {
    public static void main(String[] args) {
        List<Integer> ids = List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12);
        int pageSize = 5;

        List<Integer> rawPage = ids.stream().limit(pageSize).toList();
        List<Integer> postFiltered = rawPage.stream()
                .filter(id -> id % 2 == 0).toList();

        List<Integer> visible = ids.stream()
                .filter(id -> id % 2 == 0).toList();
        List<Integer> authorizedPage = visible.stream()
                .limit(pageSize).toList();

        System.out.println("After pagination: " + postFiltered);
        System.out.println("Before pagination: " + authorizedPage);
        System.out.println("Authorized total: " + visible.size());
    }
}
~~~

Save as `PaginationDemo.java`; run:

~~~bash
javac PaginationDemo.java
java PaginationDemo
~~~

Stdout:

~~~text
After pagination: [2, 4]
Before pagination: [2, 4, 6, 8, 10]
Authorized total: 6
~~~

The demo only simulates operation order on Java Streams; it does not itself run Spring Data JPA or a method security proxy.

## 9. Tests That Should Exist

- With 12 records and user A allowed to view only 6 even IDs, `size=5`: page 0 `[2,4,6,8,10]`, page 1 `[12]`, `totalElements=6`, `totalPages=2`, `hasNext=true/false` respectively.
- User B has a different permission set; verify both content and COUNT count only B's viewable set.
- Test guessing IDs, switching tenants, altering query parameters, deep page queries, and different sorts; users cannot read rows outside their permissions or infer out-of-scope metadata.
- Test partial last page, out-of-range page, empty set, permission changes, and records added/deleted between queries.
- When ACL JOIN produces multiple rows, test duplicate records and COUNT distinct.
- If using method security annotations, test through the real Spring bean/proxy, not just internal Java calls.
- Check query plans and indexes on tenant, owner/ACL, filter, and sort columns as data grows.

## 10. Common Mistakes

**Mistake: `@PostFilter` on an already-queried page.** Valid elements outside the page are not pulled in to fill the current page. **Fix:** push policy down to the query before pagination.

**Mistake: whole-table COUNT while content is permission-filtered.** Totals/page counts are wrong and may leak metadata. **Fix:** use identical permission predicates in SELECT and COUNT.

**Mistake: `totalElements = content.size()`.** That is only the record count of one page. **Fix:** run an accurate COUNT or switch to `Slice` if totals are not needed.

**Mistake: using `content.size() < pageSize` to conclude no more data exists after post-filtering.** An under-filled page does not mean valid data is exhausted. **Fix:** compute `hasNext` over the authorized set.

**Mistake: letting the client choose tenant/owner to gain view access.** Allows crossing data boundaries. **Fix:** authorization scope is derived server-side from authentication, and client filters can only narrow scope.

**Mistake: unstable sorting or COUNT differing from SELECT.** Causes duplicates/skips or wrong totals. **Fix:** ORDER BY with a unique key and aligned predicates.

## 11. Checklist

A secure paginated API must demonstrate: (1) SELECT sees only permitted rows; (2) COUNT has the same predicate; (3) pagination occurs after permission conditions; (4) sorting is stable; (5) scope comes from authentication; (6) `totalElements`, `totalPages`, `hasNext` reflect viewable data; (7) tests cover multiple principals, tenants, and multiple pages; (8) unauthorized data is not exposed through logs, caches, or mappers.

When ensuring the same permission scope from query to metadata, the frontend can paginate consistently without leaking the count of denied records.
