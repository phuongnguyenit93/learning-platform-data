# Limitations of In-Memory Filtering with Large Datasets

## 1. Problem Statement and Goal

In Spring Security, **method-level data filtering** can apply an authorization expression to each element of an input parameter (`@PreFilter`) or return value (`@PostFilter`). This approach is convenient when returning documents belonging to the current user, for example: user `alice` should only see documents with `ownerUsername = "alice"`.

However, if the method loads hundreds of thousands or millions of records before running `@PostFilter`, the application still pays the cost of **querying, transferring data, instantiating objects, and holding data in memory** before unauthorized elements are removed. At scale, this becomes a problem for performance, memory, pagination correctness, and where security policies are enforced.

After this lesson, you should be able to distinguish Java-side filtering from filtering directly at the data source; explain why `@PostFilter` does not automatically add a `WHERE` clause to SQL; know how to push access control conditions into queries and verify pagination, access control, and performance.

## 2. Method Data Filtering Mechanism

Enable method-level security for Spring beans with `@EnableMethodSecurity`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

In a Spring Boot application with Spring Security, this configuration activates interceptors for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`. Spring Security Starter does not automatically enable method security just because the dependency is declared.

| Mechanism | Timing | Checked Subject | Impact on Data Loading |
| --- | --- | --- | --- |
| `@PreAuthorize` | Before calling the method | Method invocation permission, parameters | Can deny early; does not automatically filter SQL rows |
| `@PreFilter` | Before method body | Each element of collection parameter | Input elements have already been created/received; does not automatically modify data queries |
| `@PostFilter` | After method body returns result | Each element of result collection | Data has usually already been read and mapped to objects |
| Filtering with `WHERE`/ACL in database | In the query | Rows matching user, tenant, and permissions | Reduces the number of rows entering the application **before** creating results |

Example in a Spring service (illustrative snippet, assuming `Document` is a JPA entity with getter `getOwnerUsername()` and `DocumentRepository` extends `JpaRepository`):

```java
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PostFilter("filterObject.ownerUsername == authentication.name")
    public List<Document> listMine() {
        return repository.findAll();
    }
}
```

When `alice` calls `listMine()` through the Spring proxy, `repository.findAll()` still fetches **all** documents in the query scope. Spring Security then evaluates `filterObject` for each element and removes elements not belonging to `alice` from the returned result. `authentication.name` comes from the authentication context; `filterObject` is the element currently being checked. Individual elements may be protected in the final output, but the entire data-loading work has already occurred.

Note: method-level annotations are applied through Spring's interceptor/proxy mechanism; internal calls via `this.listMine()` within the same object may bypass interceptors. Place rules at clear service boundaries and test the real invocation path.

## 3. Why Do Large Datasets Make In-Memory Filtering Expensive?

Suppose a table has **2,000,000** documents, of which the user is only allowed to view **10,000** documents (0.5%). To retrieve 10,000 documents via `findAll()` followed by `@PostFilter`, the system may have to:

1. Scan/read and return 2,000,000 rows (depending on the query plan).
2. Transfer a large volume of data from the database to the JVM.
3. Instantiate Java objects, map JPA entities, and possibly hold many entities in the persistence context.
4. Evaluate the authorization expression for every element and build the retained result.
5. Garbage-collect discarded objects after they have increased heap and GC pressure.

If each row averages **1 KiB of transferred data**, raw data transfer alone is roughly **1.9 GiB**, excluding the overhead of Java objects, ORM, caches, or associations. This is a back-of-the-envelope example based on assumptions, not a fixed measurement for every system.

- **Time:** in-memory checking usually has to inspect around `N` elements, i.e. `O(N)` for the filtering step, in addition to database, network, and mapping time. Queries with conditions and appropriate indexes can transfer far fewer rows; actual scan speed depends on the database/query plan.
- **Memory:** materializing large lists usually consumes memory proportional to `N`; `@PostFilter` does not undo the initial data-loading cost. With an ORM, the persistence context may also retain references to loaded entities.
- **Latency and stability:** large loads increase GC, response times, and the risk of `OutOfMemoryError` under concurrent requests.
- **N+1 and related data:** if the SpEL condition accesses lazy relationships, each check may trigger an extra query, multiplying costs dramatically.
- **Side effects:** `@PostFilter` only processes the result after the method runs; it does not prevent code inside the method from logging sensitive content, populating caches, or performing side effects before filtering.

Do not equate `Stream` with query optimization. Spring Security supports filtering open streams, but using a stream does not guarantee the data source is constrained by database-level policy; row-by-row reading may still occur and also depends on connection/transaction lifetimes.

## 4. Common Correctness Bug: Paginating Before Filtering

Suppose the database selects `LIMIT 20 OFFSET 0` over **all** documents, of which only 3 belong to the user. If the application filters after pagination:

- The first page result contains 3 elements even though many permitted documents actually exist on subsequent pages.
- `totalElements` / `totalPages` calculated on the pre-authorization set will be wrong from the user's perspective and may leak information about dataset size.
- A page may be empty even though records the user is permitted to view exist later; sorting and pagination become unpredictable.

**Correct order:** identify the trusted user and tenant → push permission conditions into `WHERE`/query policy → stable `ORDER BY` → apply `LIMIT/OFFSET` or keyset pagination → return the page with the **authorized** total record count. With Spring Data's `Page<T>`, prefer conditional repository queries rather than expecting `@PostFilter` to handle pages; this annotation is designed for arrays, collections, maps, and streams, not to replace `Page` pagination logic.

## 5. Better Design: Filtering at the Data Layer

This example belongs to a Spring Boot application with Spring Data JPA, Spring Security, and a `Document` entity containing fields `tenantId`, `ownerUsername`, and `id`. The snippets below are **component classes**, not a standalone Java file; they require the entity, database configuration, and the application's `TenantContext` bean.

Repository pushes constraints into the query:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<Document, Long> {
    Page<Document> findByTenantIdAndOwnerUsername(
        String tenantId, String ownerUsername, Pageable pageable);
}
```

Service retrieves the server-authenticated identity, obtains the membership-verified tenant, then calls the repository with explicit conditions:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;
    private final TenantContext tenantContext;

    public DocumentService(
        DocumentRepository repository, TenantContext tenantContext) {
        this.repository = repository;
        this.tenantContext = tenantContext;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Page<Document> myDocuments(Pageable pageable) {
        String username = SecurityContextHolder.getContext()
            .getAuthentication().getName();
        String tenantId = tenantContext.requireTrustedTenantId();

        return repository.findByTenantIdAndOwnerUsername(
            tenantId, username, pageable);
    }
}
```

Here, `TenantContext.requireTrustedTenantId()` **must** verify the tenant using authenticated information and server-side membership relationships, never accepting a client-declared tenant alone. The `hasAuthority('document:read')` rule is the method-invocation permission gate; the repository condition is the row-level access constraint. Both should be maintained if the system has both operation permissions and data access permissions.

Conceptually equivalent SQL query:

```sql
SELECT id, tenant_id, owner_username, title
FROM documents
WHERE tenant_id = :tenantId
  AND owner_username = :username
ORDER BY id ASC
LIMIT :pageSize OFFSET :offset;
```

Actual pagination syntax is determined by the JPA dialect and database. The count query for `Page` must also use **the same permission conditions**. For this query pattern, you can consider an index:

```sql
CREATE INDEX idx_documents_tenant_owner_id
ON documents (tenant_id, owner_username, id);
```

Do not add indexes blindly: use `EXPLAIN`/execution plans, data distribution, write frequency, and real metrics to decide. For very deep offsets, consider keyset pagination on a stable, indexed sort key.

### When Permissions Are More Complex Than Ownership

If a document is shared via ACLs/groups, the condition may require `EXISTS` or a `JOIN` to a permissions table. Conceptual example:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :tenantId
  AND (
    d.owner_username = :username
    OR EXISTS (
      SELECT 1
      FROM document_acl a
      WHERE a.document_id = d.id
        AND a.principal_name = :username
        AND a.can_read = TRUE
    )
  )
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
```

Parameterize queries, check tenant on ACLs, design indexes, and ensure the `COUNT` query reflects the exact permitted set. Database Row-Level Security (RLS) can add a defense layer when configured properly across sessions, transactions, and connection pools. With multi-tenant data, **do not filter by username alone** if usernames do not guarantee tenant isolation.

When data comes from a search engine, cache, or external service, push the permission filter into that query system itself (or a permission-scoped retrieval mechanism); do not fetch full results and drop unauthorized elements to serve pagination.

## 6. Standalone Runnable Java 17 Illustration

The snippet below **does not use Spring Security**; it shows why filtering after loading data does not save the initial read work. Save as `FilteringDemo.java`:

```java
import java.util.List;

public class FilteringDemo {
    record Doc(int id, String owner) {}

    public static void main(String[] args) {
        List<Doc> loaded = List.of(
            new Doc(1, "alice"),
            new Doc(2, "bob"),
            new Doc(3, "charlie"),
            new Doc(4, "alice"),
            new Doc(5, "bob")
        );

        List<Doc> visible = loaded.stream()
            .filter(doc -> doc.owner().equals("alice"))
            .toList();

        System.out.println("Rows read: " + loaded.size());
        System.out.println("Rows visible: " + visible.size());
        System.out.println("IDs: " + visible.stream().map(Doc::id).toList());
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac FilteringDemo.java
java FilteringDemo
```

Standard output:

```text
Rows read: 5
Rows visible: 2
IDs: [1, 4]
```

Even though only 2 documents are returned, the `loaded` variable already held 5 documents. In a real application, `@PostFilter` likewise cannot erase the cost of a completed query.

## 7. When Is `@PreFilter`/`@PostFilter` Still Worth Using?

| Case | Approach |
| --- | --- |
| Small list, **hard-bounded**, already in memory | `@PostFilter` can express policy clearly; measure actual cost |
| Large dataset, needing search/pagination/counting/sorting | Filter in database/search index before pagination |
| Method receives a small input set from the caller | `@PreFilter` can filter input; still verify permissions against server-side resources during processing |
| Accessing a single resource by ID | Check permissions before changing state; query by ID + tenant + permission, or `@PreAuthorize` with trusted verification logic |
| Multi-tenant data or complex ACLs | Unified policy at the data-access layer, consider RLS, and test paths across services |

`@PreFilter` is not a substitute for scoped queries: the input collection already exists before the annotation filters it. For collection parameters, verify mutability and Spring Security version behavior; do not assume an immutable list can be filtered in-place. Do not confuse `@PreFilter` (element-by-element input filtering) with `@PreAuthorize` (deciding whether to allow invoking the method).

`@PostFilter` remains valuable as an extra safeguard for small results, but when permissions determine which rows are read, **early constraints in the query are the primary measure**. Watch out for self-invocation, lazy loading, transactions, null results, collection types, and multi-tenant logic.

## 8. Testing Correctness, Authorization, and Performance

At minimum, test the following scenarios:

1. **Authorization:** user A sees only A's data; user B cannot access A's data via lists, direct IDs, exports, or other endpoints.
2. **Tenant isolation:** two tenants with identical usernames or IDs still cannot cross-read documents; a client-sent tenant does not determine access scope.
3. **Pagination:** pages contain full `pageSize` when enough valid data remains; `totalElements` and `totalPages` accurately reflect the authorized set; ordering is stable across pages.
4. **Edge cases:** empty results, revoked permissions, group/ACL permissions, ownerless records, data changing during pagination.
5. **Query structure:** use controlled integration tests/SQL logging to confirm both `WHERE` and `COUNT` include required owner, tenant, and ACL conditions. Do not only test that the response was trimmed.
6. **Heavy load:** measure actual rows returned from the database, query counts (especially N+1), p95/p99 latency, heap/GC usage, and throughput under concurrent requests.

For example, in a dataset of 100 documents where 10 belong to `alice`, requesting the first page with `size=5` must return **5 documents belonging to alice** (if the query is ordered and data is unchanged), and the valid total is **10**, not 100. That is a concrete test that catches "paginate first, filter later" bugs.

You can add rules to prevent unbounded queries: cap `pageSize`, query timeouts, permission-checked batch export limits, avoid converting a whole `Page` into a `List`, and use DTOs/projections when only a few fields are needed. These measures reduce load but **do not replace** authorization conditions at the source.

## 9. Common Misconceptions and Self-Checks

- **"With `@PostFilter`, `findAll()` is still safe and efficient."** The returned output may be filtered, but the application already loaded every row and paid the cost before filtering.
- **"Putting `LIMIT` first and then `@PostFilter` is proper pagination."** Doing so easily produces short/empty pages and wrong count metadata; you must filter by permission before pagination.
- **"Passing `ownerUsername` from the request into the query is enough."** The caller can spoof it; identity and tenant must come from server-authenticated/verified sources.
- **"`@PreAuthorize` replaces owner/tenant conditions."** A general authority like `document:read` only states permission to read that resource type; you still must check **which rows** may be read.
- **"`Stream`, caching, or batching automatically solves the problem."** They may change how data is loaded, but they do not automatically inject permission policies into queries or fix total counts.
- **"Testing that output excludes B's data is enough."** You must inspect SQL, pagination totals, caches/logs/side effects, tenants, and proxy invocation paths.

**Decision rule:** if the number of rows read before filtering can grow with total table size, or if results must be paginated/counted per permission, prioritize permission-constrained queries at the data layer. Only use in-memory filtering when the input set is small, clearly bounded, and measured/tested.

## References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): describes `@PreFilter`/`@PostFilter`, `@EnableMethodSecurity` configuration, and warnings about in-memory filtering costs.
- [Spring Data JPA — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): ways to create conditional repository queries.
