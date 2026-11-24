# Permission Scope for Search, Count, Pagination, and Statistics in Spring Security

## 1. The Problem: Not Returning Unauthorized Records Is Not Enough

Suppose Alice belongs to tenant ALPHA, has `DOC_READ`, and can view documents she owns or that are shared with her internal team. A search API returns Alice's exact two documents, yet `totalElements` counts every document in the company, the `status` facet includes secret documents, or the dashboard displays revenue from customers outside Alice's tenant. Even though items in `content` were filtered, the system **still leaks information through counts and statistics**.

In Spring Security, `@PreAuthorize("hasAuthority('DOC_READ')")` checks whether the caller **is allowed to invoke the feature**. It **does not automatically inject a WHERE clause** to pick only records the caller may view. A system securing data lists must control **the visible resource set**, and then run search/count/pagination/statistics on that set.

Distinguish clearly:

- **Function-level authorization:** is the user allowed to call the search/count/report API?
- **Object-/row-level authorization:** among documents, invoices, orders, or user records, which rows fall within visible scope?
- **Property-level authorization:** on a visible record, which fields may be returned? For instance, allowed to see order name but not salary details.
- **Aggregate-level authorization:** is it permissible to publish counts, sums, percentiles, charts, facets, or trends derived from those records?

This lesson focuses on **data permission scope** across four operations: *search, count, pagination, statistics*. Spring Data JPA and SQL examples illustrate enforcing policies right in the query; a standalone Java 17 example shows exact results when sharing one filter.

## 2. Foundational Formula for a Safe Result Set

Notation:

- `D` is the set of all records.
- `A(u,d)` is the policy "user `u` is allowed to read record `d`".
- `F(q,d)` is the business filter requested by search query `q` (keyword, status, date range, ...).
- `R(u,q) = {d ∈ D | A(u,d) ∧ F(q,d)}` is the **valid result set**.

From this:

```text
AuthorizedScope(user) = data satisfying the permission policy
SearchResults         = AuthorizedScope ∩ BusinessFilters
TotalElements         = COUNT(SearchResults)
PageContent           = SORT(SearchResults)[offset : offset + limit]
Statistics            = AGGREGATE(SearchResults)
FacetCounts           = GROUP BY / COUNT over explicitly designed scope
```

This is the **logical** order: permission conditions must apply before `LIMIT`/`OFFSET` and before aggregation. Databases may reorder physical execution for optimization, but query semantics must equal the formula above.

Three security invariants to turn into automated tests:

1. **No resource leak:** every returned item must satisfy `A(u,d)`.
2. **No count leak:** `totalElements` and count APIs must compute over `A(u,d) ∧ F(q,d)`, never over system-wide data.
3. **No leak through derived data:** statistics, facets, charts, export counts, and search suggestions must use the same permission scope plus any aggregate-specific policies.

### Example of a Common Mistake

```java
// WRONG: the page of data is scoped, yet the total counts the entire system.
Page<Document> page = repository.findAll(allowedSpec, pageable);
long total = repository.count(); // Accidentally leaks scale of unauthorized data.
```

```java
// RIGHT DIRECTION: use the same scope and the same filters.
Specification<Document> fullSpec = allowedSpec.and(searchSpec);
Page<Document> page = repository.findAll(fullSpec, pageable);
long total = repository.count(fullSpec);
```

Both snippets are **integration code**, requiring a Spring Data JPA repository and matching Specifications. For a `Page` returned by `findAll(fullSpec, pageable)`, `getTotalElements()` is computed from count logic using that specification; normally **there is no need to call `count` separately** just to repeat that number.

## 3. Building Permission Scope from Trusted Sources

An illustrative rule:

> Caller has `DOC_READ`, sees only documents in their permitted tenant where (they are the document's owner **or** the document has `TEAM` visibility in that tenant).

Expression:

```text
CAN_READ(user, doc) =
  user.authenticated
  AND hasAuthority(user, "DOC_READ")
  AND doc.tenant_id = user.tenant_id
  AND (
       doc.owner_id = user.subject_id
       OR doc.visibility = "TEAM"
  )
```

The tenant condition sits **outside** the OR group. A dangerous mistake is:

```sql
-- WRONG: OR TEAM is no longer constrained by tenant.
WHERE d.tenant_id = :tenant_id
  AND d.owner_id = :subject_id
   OR d.visibility = 'TEAM'
```

Because `AND` has higher precedence than `OR`, the query above can return TEAM documents from other tenants. Properly wrap with parentheses:

```sql
WHERE d.tenant_id = :tenant_id
  AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
```

### Where Does Caller Scope Come From?

- `subjectId`: stable identity from a verified principal/JWT (do not default to raw username if usernames can collide or change).
- `tenantId`: a tenant the system has verified the caller belongs to or has access to; never trust a client-supplied `X-Tenant-Id` header.
- `roles`/`authorities`: from verified and properly mapped `Authentication`, never from the request body.
- Per-document sharing permissions, ACLs, and sensitivity states: from trusted server sources (DB/policy service), never accepting a client-supplied list of "allowed" document IDs.

One user may belong to multiple tenants. In that case the active tenant is a business parameter, yet **membership must be verified before use**. For cross-tenant administrator privileges, policies must explicitly define global/tenant scope, audit, and test exception branches; never add `OR isAdmin` to every query without checking the authority source.

### Fail Closed

If `Authentication` is missing, tenant is unresolved, the token lacks required claims, or the policy backend fails, **never** replace scope with a null/`unrestricted()` `Specification` or an empty SQL predicate. Reject the API call or return an appropriate operational error. In Spring Data JPA, a null specification can mean **no data filtering**; this is a failure mode that must be blocked.

## 4. Search Must Start from the Permitted Dataset

For searching "roadmap", instead of:

```text
SELECT all documents containing roadmap
  -> OFFSET/LIMIT
  -> filter by owner/tenant in Java
```

use the logic:

```text
Query DB/Search Engine
  -> tenant + owner/TEAM/ACL conditions
  -> keyword/status/date conditions
  -> stable sort
  -> LIMIT/OFFSET or cursor
  -> projection of display-permitted fields
```

### Why Is Post-Query Filtering Wrong?

Suppose the DB matches 100 results, of which the user may view 10. If you fetch the first page of 20 results and run `stream().filter(this::canRead)`, only 1–2 results may remain. You no longer know if the next page has valid records; `totalElements=100` leaks data; the user flips through sparse/empty pages; and the system has already loaded sensitive resources into application memory.

`@PostFilter` on a collection is a real Spring Security feature, yet **should not be used as the primary way** to protect large searches/pagination. It filters after the method has already fetched data; it does not recompute SQL counts, aggregates, facets, or pagination over the permitted set.

### Search Keywords and Escaping

- Use bind parameters; never concatenate raw user text into SQL/JPQL.
- When using SQL `LIKE`, `%` and `_` are wildcards; if searching literally, escape them using syntax matching your dialect.
- Bound keyword length, filter count, OR clause count, and page size to prevent resource abuse.
- When using full-text search, policy filters must apply inside the search index query with matching membership/ACL logic, **not just trimming final API results**.
- Highlights, suggestions/autocomplete, and ranking can also leak titles/terms existing in unauthorized documents.

## 5. Count Is Not Just a Harmless Number

For example, a user is permitted to see 4 documents containing "roadmap", yet `GET /documents/count?q=roadmap` returns 7 (because it also counted documents in other tenants or others' PRIVATE documents). An attacker can probe keywords and infer:

- Existence of sensitive projects.
- Customer/order counts in another tenant.
- Activity levels of other users.
- Record counts by pending, paid, or locked status.

Therefore:

```sql
SELECT COUNT(*)
FROM documents d
WHERE d.tenant_id = :tenant_id
  AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
  AND LOWER(d.title) LIKE :pattern ESCAPE '!';
```

In the SQL above, `:subject_id` and `:tenant_id` come from **verified caller scope**, and `:pattern` is a bound/escaped keyword. Using `!` as the escape character requires escaping `!`, `%`, and `_` before binding when literal matching is intended.

### `COUNT(*)` vs `COUNT(DISTINCT ...)`

When joining a sharing or tags table, one document can multiply in the result set:

```sql
SELECT COUNT(*)
FROM documents d
JOIN document_share s ON s.document_id = d.id
WHERE ...;
```

If each document has multiple share rows, `COUNT(*)` may count **joined rows**, not documents. Two common strategies:

- Use `EXISTS` to check permissions when each resource only needs to appear once.
- Use `COUNT(DISTINCT d.id)` when a genuine one-to-many join exists and you want to count unique resources.

Never rely on `COUNT(DISTINCT)` to hide a cross-tenant join bug: every join to ACL/share tables must also bind tenant and object identity.

## 6. Pagination: Apply Scope Before Offset/Limit

A `Page<DocumentDto>` response typically looks like:

```json
{
  "content": [
    {"id": 1, "title": "Roadmap platform"},
    {"id": 5, "title": "Roadmap archive"}
  ],
  "number": 0,
  "size": 2,
  "totalElements": 4,
  "totalPages": 2
}
```

Policy semantics:

- `content` contains only permitted records.
- `totalElements` counts across all **valid results**, not just items in the page, and excludes unauthorized records.
- `totalPages` must derive from valid `totalElements` and `size`; a wrong total leaks data even if content is right.
- Requesting higher page numbers must never degrade into "read raw OFFSET of the global table" bypassing scope.
- Other metadata fields like `hasNext`, `hasPrevious`, and `numberOfElements` must also remain consistent with the valid set.

### Stable Sorting Is Mandatory for Reliable Pagination

If sorting only by `ORDER BY created_at DESC` when multiple records share timestamps, pages can duplicate or skip records due to non-deterministic ordering. Add a tie-breaker key:

```sql
ORDER BY d.created_at DESC, d.id DESC
LIMIT :page_size OFFSET :offset;
```

The `WHERE` clause must still hold the **policy predicate**. Cap `page_size` (e.g., 1–100 per SLA) and guard against integer overflow in `offset = page * size`. Client-selected sort fields must be allowlisted; never allow sorting by hidden sensitive fields.

### Count Queries and Data Queries Can Observe Different Points in Time

Between the query fetching `content` and the query counting `totalElements`, records may be inserted, updated, deleted, or change permissions. Without appropriate snapshots/isolation, counts and content can temporarily diverge. This is a consistency issue **distinct from** scope bugs. For financial reports or strict snapshot pagination, pick matching transaction isolation, snapshot tokens, or immutable datasets.

### Cursor/Keyset Pagination

Cursors should be built from **valid sort keys** and bound to the query/filter, tenant, user, or scope version where needed. Never allow a cursor from tenant A to paginate tenant B. Encrypt/sign cursors to prevent tampering with sensitive values, and **re-apply the permission predicate on every page**: a cursor is not a permanent access pass.

Offset slows down on large datasets while keyset/cursor helps continuous scrolling; both must enforce the exact same authorized scope.

## 7. Statistics and Charts Can Also Leak Data

Statistics often include:

- Counts by status: ACTIVE, ARCHIVED, PENDING.
- SUM(amount), AVG(price), MIN/MAX, medians/percentiles.
- Group by team, project, department, region, month.
- Search UI facet/filter counts.
- Trend charts and aggregated data exports.

If a dashboard shows company-wide `COUNT(*)` or `SUM(invoice.amount)` to a user restricted to one tenant, that is a data leak **via aggregates**.

Correct order:

```text
Source dataset
    |
    v
AuthorizedScope(user)
    |
    v
BusinessFilters(search/query)
    |
    v
GROUP BY / SUM / COUNT / AVG / MIN / MAX
    |
    v
Aggregate disclosure policy (if needed)
    |
    v
Response
```

SQL example:

```sql
WITH visible AS (
    SELECT d.id, d.status, d.amount
    FROM documents d
    WHERE d.tenant_id = :tenant_id
      AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
      AND LOWER(d.title) LIKE :pattern ESCAPE '!'
)
SELECT status,
       COUNT(*) AS visible_count,
       COALESCE(SUM(amount), 0) AS visible_amount
FROM visible
GROUP BY status
ORDER BY status;
```

All counts/sums in this query originate from `visible`. Never read from a company-wide pre-aggregated summary table (materialized view/cache) lacking required tenant/permission dimensions.

### Filtering by Permission Is Necessary, Sometimes Still Insufficient

Even aggregates computed solely from permitted records can be sensitive. For example, if a group has only **one** employee, `AVG(salary)` reveals that person's exact salary; two queries differing by one filter can deduce a single record's value (differencing attack).

Depending on business needs, add:

- Restricting summary reports to specific roles.
- Minimum group thresholds (`k`-anonymity/suppression), keeping group subtraction/differencing in mind.
- Restricting filter combinations, time/region/group granularity, and query rates for high-risk data.
- Rounding, bucketing, or dedicated privacy guards for sensitive statistics.
- Auditing exports/reports; never assume anyone who can read documents can compute every financial metric.

These techniques are **complementary aggregate policies**, not replacements for row-level scoping.

## 8. Facets: Per-Filter Totals Must Be Consistent

Suppose searching documents for keyword "roadmap", the UI shows a `status` facet:

```text
ACTIVE   3
ARCHIVED 1
```

Those numbers must come from **permitted documents** matching the active search set.

Two common facet semantics:

1. **Conjunctive facets:** after applying all selected filters, count each group over the remaining set.
2. **Disjunctive facets:** when computing buckets for one dimension (e.g., status), you may intentionally omit the active status filter to show other options' counts; however, **never omit the authorized scope**, tenant, or non-exempt constraints.

Each endpoint must document its semantics. Under either option, a facet count must never come from an organization-wide table and return out-of-scope numbers.

All data paths must share the same scope: search results, global counts, facets, autocomplete/suggestions, analytics tabs, CSV exports, async reports, and scheduled email summaries. Even a rarely used endpoint can become a data leak.

## 9. Standalone Java 17 Demo: Search, Count, Page, and Stats Sharing One Scope

This is a **complete, Spring-free** Java 17 program demonstrating the invariant. It models `DOC_READ`, tenant, owner, and TEAM visibility.

Create `ScopedQueryDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public final class ScopedQueryDemo {

    enum Visibility { PRIVATE, TEAM }

    record UserScope(
            String subject, String tenant, Set<String> authorities) {}

    record Document(
            long id,
            String tenant,
            String owner,
            Visibility visibility,
            String status,
            String title,
            long amount) {}

    private static Predicate<Document> allowed(UserScope user) {
        return doc -> user.authorities().contains("DOC_READ")
                && doc.tenant().equals(user.tenant())
                && (doc.owner().equals(user.subject())
                    || doc.visibility() == Visibility.TEAM);
    }

    private static Predicate<Document> titleContains(String keyword) {
        String needle = keyword.strip().toLowerCase(Locale.ROOT);
        return doc -> doc.title()
                .toLowerCase(Locale.ROOT)
                .contains(needle);
    }

    private static List<Long> ids(List<Document> documents) {
        return documents.stream().map(Document::id).toList();
    }

    public static void main(String[] args) {
        List<Document> documents = List.of(
                new Document(1, "ALPHA", "alice", Visibility.PRIVATE,
                        "ACTIVE", "Roadmap platform", 100),
                new Document(2, "ALPHA", "bob", Visibility.TEAM,
                        "ACTIVE", "Release notes", 200),
                new Document(3, "ALPHA", "bob", Visibility.PRIVATE,
                        "ACTIVE", "Payroll", 300),
                new Document(4, "BETA", "alice", Visibility.TEAM,
                        "ACTIVE", "Roadmap beta", 900),
                new Document(5, "ALPHA", "alice", Visibility.PRIVATE,
                        "ARCHIVED", "Roadmap archive", 150),
                new Document(6, "ALPHA", "cara", Visibility.TEAM,
                        "ACTIVE", "Roadmap team", 50),
                new Document(7, "BETA", "bob", Visibility.TEAM,
                        "ACTIVE", "Roadmap other", 500),
                new Document(8, "ALPHA", "alice", Visibility.PRIVATE,
                        "ACTIVE", "Budget", 80),
                new Document(9, "ALPHA", "bob", Visibility.TEAM,
                        "ACTIVE", "Roadmap milestone", 400),
                new Document(10, "ALPHA", "dave", Visibility.PRIVATE,
                        "ACTIVE", "Roadmap confidential", 1000)
        );

        UserScope alice = new UserScope(
                "alice", "ALPHA", Set.of("DOC_READ"));

        List<Document> visible = documents.stream()
                .filter(allowed(alice))
                .sorted(Comparator.comparingLong(Document::id))
                .toList();

        List<Document> result = visible.stream()
                .filter(titleContains("roadmap"))
                .toList();

        List<Long> page0 = result.stream()
                .limit(2).map(Document::id).toList();
        List<Long> page1 = result.stream()
                .skip(2).limit(2).map(Document::id).toList();

        Map<String, Long> statusCounts = result.stream()
                .collect(Collectors.groupingBy(
                        Document::status,
                        TreeMap::new,
                        Collectors.counting()));
        long amountSum = result.stream()
                .mapToLong(Document::amount)
                .sum();

        System.out.println("scopeIds=" + ids(visible));
        System.out.println("searchIds=" + ids(result));
        System.out.println("page0=" + page0);
        System.out.println("page1=" + page1);
        System.out.println("totalElements=" + result.size());
        System.out.println("statusCounts=" + statusCounts);
        System.out.println("amountSum=" + amountSum);

        UserScope noReadAuthority = new UserScope(
                "alice", "ALPHA", Set.of());

        long unauthorizedCount = documents.stream()
                .filter(allowed(noReadAuthority))
                .count();
        System.out.println("withoutReadAuthority=" + unauthorizedCount);
    }
}
```

Run from the file's directory:

```bash
javac ScopedQueryDemo.java
java ScopedQueryDemo
```

Program stdout:

```text
scopeIds=[1, 2, 5, 6, 8, 9]
searchIds=[1, 5, 6, 9]
page0=[1, 5]
page1=[6, 9]
totalElements=4
statusCounts={ACTIVE=3, ARCHIVED=1}
amountSum=700
withoutReadAuthority=0
```

### Reading the Output

Alice can view six documents in tenant ALPHA: IDs 1, 2, 5, 6, 8, 9. Others' PRIVATE documents 3 and 10 are excluded; tenant BETA documents 4 and 7 are also excluded even though some have TEAM visibility.

Among the six valid documents, four contain "roadmap": IDs 1, 5, 6, 9. Pagination with size 2 yields first page [1,5] and second page [6,9], with `totalElements=4`. Statistics ACTIVE=3, ARCHIVED=1, amountSum=700 are all computed from the **four valid keyword-matching records**, excluding amounts 900, 500, and 1000 from unauthorized records.

A user lacking `DOC_READ` gets an empty scope (`withoutReadAuthority=0`). This demonstrates data filtering, **not** real authentication: in a production Spring Security service, lacking the authority should raise `AccessDeniedException`/403 before running the query rather than silently returning empty results, depending on the API contract.

### What the Demo Does Not Simulate

Java Streams are filtering an in-memory list. In a real system with millions of records, never call `repository.findAll()` and filter in Java. The `allowed(user)` condition must be translated into `WHERE`/`Specification`/RLS/search-index filters, with statistics computed in the DB or scoped engine. The next section implements that pattern.

## 10. Spring Data JPA: Combining Permission Specifications and Business Filters

Spring Data JPA provides `JpaSpecificationExecutor<T>` with key methods:

```java
Page<T> findAll(Specification<T> spec, Pageable pageable);
long count(Specification<T> spec);
List<T> findAll(Specification<T> spec);
```

These methods are confirmed in Spring Data JPA 3.5 documentation. There is also an overload accepting a separate `countSpec`; if used, **`countSpec` must still contain the exact same permission conditions** and business filters to count.

### 10.1. Entity/Repository

The snippets below are **integration code**, not a complete Maven project; they assume existing entities, columns, and Spring Data JPA configuration.

```java
@Entity
@Table(name = "documents")
class DocumentEntity {

    @Id
    Long id;

    String tenantId;
    String ownerId;
    String title;
    String status;

    @Enumerated(EnumType.STRING)
    Visibility visibility;

    // Application getters and other data mappings.
}

enum Visibility { PRIVATE, TEAM }

interface DocumentRepository extends
        JpaRepository<DocumentEntity, Long>,
        JpaSpecificationExecutor<DocumentEntity> {
}
```

### 10.2. CallerScope from Verified Identity

```java
record CallerScope(String subjectId, String tenantId) {}

@Component
class CallerScopeResolver {

    CallerScope requireScope(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Authentication required");
        }

        // In a real app, subject/tenant come from verified identity
        // and server-side membership/tenant policy, NOT query params.
        String subjectId = authentication.getName();
        String tenantId = resolveAuthorizedTenant(authentication);
        return new CallerScope(subjectId, tenantId);
    }

    private String resolveAuthorizedTenant(Authentication authentication) {
        // Bean/identity integration must be implemented for your application.
        throw new UnsupportedOperationException("Tenant identity integration");
    }
}
```

This is an **integration skeleton**: `resolveAuthorizedTenant` is not a built-in Spring API. Replace it with your system's real tenant verification before use. Never copy into production unimplemented. If callers select a tenant via URL/header, the resolver must cross-check verified membership.

### 10.3. Scope Specification

```java
final class DocumentSpecs {

    private DocumentSpecs() {}

    static Specification<DocumentEntity> visibleTo(CallerScope caller) {
        return (root, query, cb) -> cb.and(
                cb.equal(root.get("tenantId"), caller.tenantId()),
                cb.or(
                    cb.equal(root.get("ownerId"), caller.subjectId()),
                    cb.equal(root.get("visibility"), Visibility.TEAM)
                )
        );
    }

    static Specification<DocumentEntity> titleContains(String raw) {
        String needle = raw == null
                ? ""
                : raw.strip().toLowerCase(Locale.ROOT);
        if (needle.isEmpty()) {
            return (root, query, cb) -> cb.conjunction();
        }

        String escaped = needle.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");

        return (root, query, cb) -> cb.like(
                cb.lower(root.get("title")),
                "%" + escaped + "%",
                '!'
        );
    }
}
```

`DocumentSpecs.visibleTo(caller)` is **mandatory** and must never be dropped when the keyword is empty. Using `CriteriaBuilder.and` with `or` produces semantically parenthesized SQL:

```sql
WHERE tenant_id = :tenant
  AND (owner_id = :subject OR visibility = 'TEAM')
  AND LOWER(title) LIKE :keyword
```

The `LIKE` pattern escapes `!`, `%`, and `_` per SQL contract and binds via JPA Criteria; verify escaping behavior for your dialect. Requires imports for `java.util.Locale`, `org.springframework.data.jpa.domain.Specification`, JPA Criteria API, and entity classes.

### 10.4. Query Service Using One `fullSpec`

```java
@Service
class DocumentQueryService {

    private final DocumentRepository repository;
    private final CallerScopeResolver scopeResolver;

    DocumentQueryService(DocumentRepository repository,
                         CallerScopeResolver scopeResolver) {
        this.repository = repository;
        this.scopeResolver = scopeResolver;
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    @Transactional(readOnly = true)
    public Page<DocumentSummary> search(
            String keyword, int page, int size) {

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        CallerScope caller = scopeResolver.requireScope(auth);

        Specification<DocumentEntity> fullSpec =
                DocumentSpecs.visibleTo(caller)
                    .and(DocumentSpecs.titleContains(keyword));

        int safePage = Math.max(0, page);
        int safeSize = Math.max(1, Math.min(size, 100));

        Pageable pageable = PageRequest.of(
                safePage,
                safeSize,
                Sort.by("id").ascending());

        return repository.findAll(fullSpec, pageable)
                .map(DocumentSummary::fromEntity);
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    @Transactional(readOnly = true)
    public long count(String keyword) {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        CallerScope caller = scopeResolver.requireScope(auth);

        Specification<DocumentEntity> fullSpec =
                DocumentSpecs.visibleTo(caller)
                    .and(DocumentSpecs.titleContains(keyword));

        return repository.count(fullSpec);
    }
}
```

`DocumentSummary` is an application-defined projection/DTO, and `fromEntity` selects only publishable fields. This is an **integration snippet**, requiring Spring Data/JPA/Security imports and entity/DTO types. If the DTO accidentally includes `salary`/`internalNote`/`token`, row-level scoping alone still fails **property-level authorization**.

Key points:

- `@PreAuthorize` checks functional invocation permission, while `visibleTo` constrains rows.
- Never accept `CallerScope` from request body/client; the resolver must obtain verified identity.
- The exact same `fullSpec` feeds both `findAll` and `count`. You can extract a single `authorizedQuery(auth, filters)` helper to prevent copy-paste drift.
- `Page.getTotalElements()` is computed from `fullSpec`; never override it with an unscoped `repository.count()`.
- In this demo, sorting uses stable ID order. If clients can choose sort fields, allowlist fields and include an ID tie-breaker.
- `safePage` and `safeSize` are minimal illustrative clamps; production should return 400 on invalid input, cap offset/page depth, and prevent integer overflow.
- `@EnableMethodSecurity` must be enabled, and calls to `DocumentQueryService` must pass through the Spring bean proxy. Never rely solely on method security: if another path calls the repository directly, protect that boundary too.

### 10.5. Avoiding Unscoped `countSpec`

Spring Data JPA has an overload like:

```java
Page<DocumentEntity> page =
        repository.findAll(dataSpec, countSpec, pageable);
```

If `dataSpec` includes tenant/owner while `countSpec` has only the keyword, `totalElements` in the response can count unauthorized documents. If optimizing counts with a different query (e.g., skipping fetch joins), at minimum preserve **the exact same policy predicates and business semantics**, then test `totalElements` across specific tenants/users.

## 11. SQL Statistics: Using One `visible` Set Across All Aggregations

When grouped charts are needed, you can use a CTE with permission conditions:

```sql
WITH visible AS (
  SELECT d.id, d.status, d.amount, d.created_at
  FROM documents d
  WHERE d.tenant_id = :tenant_id
    AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
    AND LOWER(d.title) LIKE :pattern ESCAPE '!'
)
SELECT status,
       COUNT(*) AS number_of_documents,
       COALESCE(SUM(amount), 0) AS total_amount
FROM visible
GROUP BY status
ORDER BY status;
```

In the section 9 Java demo dataset, querying keyword "roadmap" yields:

| status | number_of_documents | total_amount |
| --- | ---: | ---: |
| ACTIVE | 3 | 550 |
| ARCHIVED | 1 | 150 |
| **Total** | **4** | **700** |

Here ACTIVE comprises IDs 1(100), 6(50), 9(400); ARCHIVED is ID 5(150).

For time-series, still filter scope inside the CTE before grouping by time:

```sql
WITH visible AS (
  SELECT d.id, d.created_at
  FROM documents d
  WHERE d.tenant_id = :tenant_id
    AND (d.owner_id = :subject_id OR d.visibility = 'TEAM')
)
SELECT DATE_TRUNC('month', created_at) AS month,
       COUNT(*) AS visible_count
FROM visible
GROUP BY DATE_TRUNC('month', created_at)
ORDER BY month;
```

`DATE_TRUNC` is PostgreSQL syntax; other databases need equivalent functions. This is an **integration SQL snippet** requiring proper parameter binding and matching table/schema definitions. Never interpolate client-supplied `ORDER BY` strings or column names directly.

### Is a Materialized Summary Table Safe Enough?

Not always. A summary table keyed by `tenant_id + month` may suit an admin viewing the **whole tenant**, but fails if a user may see only documents **they own** or a single project. Once a policy is finer-grained than the pre-aggregated dimensions, numbers in the summary table cannot be "filtered down further" to match user scope.

Options:

- Group after applying policy on the detail table.
- Materialized views carrying **all exact dimensions and entitlements** needed for scope.
- Database RLS/authorized views with aggregate queries running in the proper security context.
- Dedicated reporting systems with precomputed entitlements, TTLs, and contracted update/revocation mechanisms.

Never use a company-wide cache/report and merely hide a few columns in the UI.

## 12. Per-Object ACLs and Query-Time Filtering

Some projects use Spring Security ACLs: a document has grant/deny ACEs, an owner, and parent inheritance. `PermissionEvaluator.hasPermission(documentId, "Document", "READ")` can answer whether **one resource** is permitted. Yet scanning 10,000 documents and invoking the evaluator 10,000 times:

```text
SELECT 10,000 documents
-> for each document: ACL lookup / hasPermission
-> filter in Java
-> paginate
```

causes N+1 queries, wastes resources, and breaks totals/counts.

Choices for search/count/statistics must be co-designed with the policy:

1. **ACL-aware SQL/query predicates:** translate part or all of ACE/SID logic into queries or a materialized authorization index, and verify against real `AclPermissionEvaluator`.
2. **Entitlement/visibility projection:** maintain an index table `authorized_document(subject/role, tenant, document_id, permission)` with consistent updates/revocations and deny/inheritance resolution.
3. **Database RLS:** use DB row-level policies when architecture permits and identity/tenant mapping is trustworthy, binding `SELECT`, `COUNT`, and `GROUP BY`.
4. **Search engine document-level security:** indexes/queries must apply tenant/ACL filters inside the engine, not merely post-filtering top-N results.

**Warning:** Spring ACL supports explicit deny, multiple SIDs, ACE ordering, and inheritance; you cannot casually write `EXISTS (ACE GRANT)` and claim equivalence to `Acl.isGranted` in every case. For example, a direct deny on a child may need to block a parent grant; queries must implement exact precedence/algorithms or read from an accurately computed security index. Write contract tests comparing per-object evaluator results against query-time scope.

A very useful verification strategy: on a representative fixture set, compute `allowedIds` using the trusted ACL evaluator and compare against IDs returned by the search/ACL index query. Any mismatch signals a permission bug or missing coverage.

## 13. Joins, Shares, and Avoiding Row Multiplication

When the policy is "owner or shared", using `EXISTS` keeps one row per document:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :tenant_id
  AND (
      d.owner_id = :subject_id
      OR EXISTS (
          SELECT 1
          FROM document_shares s
          WHERE s.document_id = d.id
            AND s.tenant_id = d.tenant_id
            AND s.subject_id = :subject_id
            AND s.permission = 'READ'
            AND s.granting = TRUE
      )
  );
```

This illustrates a **simple sharing model** using a `document_shares` table; it is not the full Spring ACL inheritance/deny model. If business rules support explicit deny, add appropriate deny-precedence logic. The condition `s.tenant_id = d.tenant_id` is crucial to prevent matching share rows from another tenant.

Joining labels/tags/comments can produce duplicate document rows. Watch out for:

- `COUNT(DISTINCT d.id)` for total document count.
- Pagination queries must paginate over **unique document IDs**, not joined rows; consider two-phase ID pagination followed by fetching.
- If returning a `Page` over a JPA collection fetch join, verify ORM pagination/count behavior; never assume the ORM always pushes pagination down to SQL safely.
- Aggregate `SUM(amount)` can be multiplied by one-to-many joins. Deduplicate to unique document IDs before summing.

## 14. Caches and Search Indexes Need Scope Too

A cache key like:

```text
documents:search:keyword=roadmap:page=0:size=20
```

is insufficient if Alice and Bob see different sets. First-page results, `totalElements`, facets, and stats can be served to the wrong user.

Safe keys must account for:

- Principal/subject or entitlement hash (when policies depend on owner/share).
- Verified tenant.
- Roles/authorities/scope version affecting decisions.
- Query keyword, filters, sort, page/cursor, projection, and locale when relevant.
- Data/permission versions and appropriate TTLs.

Revoked permissions can linger in stale caches without proper invalidation. For asynchronous search indexes, establish the permission propagation lag and mitigations for sensitive documents. Never expose a cached results page from another user simply because both share the same tenant.

For sensitive statistics, sometimes **not caching per user** is the right choice; if caching aggregates, entitlement scopes must be rigorously managed and tested.

## 15. Permissions Changing After Pagination and TOCTOU

A request may experience:

```text
T1: Query page with visibility TEAM -> record 42 permitted
T2: Owner switches record 42 to PRIVATE
T3: API returns record 42 loaded at T1
```

This is a race condition between check and use (*time-of-check/time-of-use*). Mitigations by sensitivity:

- Use appropriate transaction snapshots/isolation for related queries within one response.
- For highly sensitive data, re-check current state before returning/writing, or run queries bound to access-time permissions.
- For mutations, use conditional UPDATEs, optimistic locking, or row locks to bind permissions and state inside the transaction.
- For asynchronous exports/reports, re-check scope when the job runs, not only when submitted; check permissions at download time too if needed.
- When pagination spans multiple requests, permissions can change between pages; **cursors must never grant permanent access**.

No single isolation level solves every race in distributed systems. Define how quickly permission revocations must take effect and test accordingly.

## 16. Testing Datasets: Do Not Just Check Status 200

An integration test suite must include at least two tenants, two users, PRIVATE and TEAM documents, shared/unshared documents, and a sensitive record differing only by keyword.

Sample matrix:

| Case | What to Test | Expectation |
| --- | --- | --- |
| Alice has DOC_READ, ALPHA | Keyword query "roadmap" | IDs [1,5,6,9] |
| Alice has DOC_READ, ALPHA | Total count for "roadmap" | 4 |
| Alice has DOC_READ, ALPHA | Page0 size2 | IDs [1,5] |
| Alice has DOC_READ, ALPHA | Page1 size2 | IDs [6,9] |
| Alice has DOC_READ, ALPHA | Status facet | ACTIVE=3, ARCHIVED=1 |
| Alice has DOC_READ, ALPHA | SUM(amount) | 700 |
| Alice searches keyword only in others' PRIVATE doc 10 | Search and count | Empty, count=0 |
| Alice searches "Roadmap beta" in tenant BETA | Search and count | Empty, count=0 |
| Alice lacks DOC_READ | Call search/count/stats | Denied at service/API boundary |
| Bob in another tenant | Uses Alice's cursor | Must not use Alice's scope/cursor |
| Alice passes tenant=BETA in query | Scope resolver | Rejects/ignores forged tenant without permission |
| JOIN shares has 2 valid rows for same doc | Count/total | Counted as one document, not multiplied |
| Document has ACL direct deny + parent grant | Visibility query/ACL index | Matches evaluator, not visible |
| User permissions revoked | Search/count/stats after invalidation | Revoked records and counts disappear |
| Add filter status=ACTIVE | Total and stats | Same filter and policy, no unscoped count |
| No matching visible records | Empty page | content=[], totalElements=0 |
| Sort requested on forbidden field | Validation | 400 or rejected per contract |
| Excessive page size/offset | Validation | Capped or safely rejected |

### Spring Data JPA Test Example with Seeded Fixtures

```java
@SpringBootTest
class DocumentQuerySecurityTest {

    @Autowired DocumentQueryService service;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void pageAndCountMustExcludeOtherTenantAndPrivateDocuments() {
        Page<DocumentSummary> page = service.search("roadmap", 0, 2);

        assertEquals(List.of(1L, 5L),
                page.getContent().stream().map(DocumentSummary::id).toList());
        assertEquals(4L, page.getTotalElements());
        assertEquals(2, page.getTotalPages());

        assertEquals(4L, service.count("roadmap"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void secondPageDoesNotSeeHiddenRecords() {
        Page<DocumentSummary> page = service.search("roadmap", 1, 2);
        assertEquals(List.of(6L, 9L),
                page.getContent().stream().map(DocumentSummary::id).toList());
    }
}
```

This is an **integration test snippet**, not a standalone runnable file: it requires DB fixtures matching section 9, `DocumentQueryService`, `DocumentSummary`, a real `CallerScopeResolver`, method-security configuration, and JUnit/Spring Security test imports. With default `@WithMockUser`, the username is `alice` **without a tenant claim**; in tests the resolver must look up the tenant from a corresponding verified test source (e.g., a membership table) rather than assuming the mock user carries a tenant.

Add tests for `statistics` and `facets` using the same dataset; testing with too few records can fail to catch leaks from unscoped queries. Ideally seed "trap" records: matching keyword in another tenant, or in the same tenant as someone else's PRIVATE doc, with huge amounts so any wrong SUM stands out immediately.

### Differential Policy Tests

If per-object authorization logic exists such as `PermissionEvaluator`, use it as an oracle over fixtures:

```text
expected = { id | perObjectPolicy.canRead(user, id) }
actual   = { id | searchQueryForUser(user).findAllIds() }

assert expected == actual
```

This is test pseudocode, not standalone Java syntax. Then verify `count`, pages, facets, and statistics all derive from `actual`. Include explicit denies, inheritance, multiple roles, and tenant membership changes in tests.

## 17. Performance and Indexing Must Not Compromise Security

Pushing authorization down to the DB is usually **better** than loading all records and filtering in Java, though owner/share/tenant predicates can get complex. Strategies:

- Index on `(tenant_id, owner_id, id)` and `(tenant_id, visibility, id)` when suited to query workloads; benchmark on your actual DB.
- For shares, index `(tenant_id, subject_id, document_id, permission)` or variants matching the query plan.
- Full-text search needs security filters inside the engine, never combining unscoped top-K with post-filtering.
- Use projections fetching only displayable fields; avoid eager-fetching sensitive relations.
- Group-by and counts need dedicated tuning: indexes, partitioning, **properly scoped** pre-aggregation, and read replicas with contracted permission-lag bounds.
- Exact counts on large tables can be expensive. If using `Slice` or "hasNext" instead of Page to avoid counts, **never leak an extra unauthorized record**; over-fetching by 1 to check next must still enforce scope.
- Approximate counts may be acceptable if UI allows and error bounds are clear, yet estimates must run over the **valid subset**, not the global catalog.
- Measure latency, scanned rows, query plans, and pathological search inputs without logging raw sensitive content.

Never enable `Specification.unrestricted()` when scope resolution fails or just to avoid slow queries. Performance is never an excuse to expose unauthorized data.

## 18. Common Mistakes to Avoid

**Mistake 1 — Scope applied to content only, not count.** Reading `totalElements` reveals hidden record counts.

**Mistake 2 — Paginating first, then filtering in Java or via `@PostFilter`.** Pages turn empty/truncated, counts/hasNext break, and unauthorized records are loaded before filtering.

**Mistake 3 — Unparenthesized `OR` in SQL.** `tenant = A AND owner = alice OR visibility = TEAM` exposes TEAM cross-tenant.

**Mistake 4 — Treating `@PreAuthorize("hasAuthority('DOC_READ')")` as a row-level filter.** It only decides whether the caller can execute the method.

**Mistake 5 — Taking scope from client headers/bodies.** Easily forged tenant/owner/role. Use verified principals/claims and server memberships.

**Mistake 6 — `countSpec` differing from `dataSpec`.** `Page.getTotalElements()` leaks out-of-scope counts when custom count queries drop the policy.

**Mistake 7 — Aggregating over system-wide tables.** COUNT/SUM/AVG/facets alongside search keywords must still enforce permissions.

**Mistake 8 — Permission-sharing JOINs multiplying records.** COUNT and SUM inflate, pagination duplicates; use EXISTS/DISTINCT and inspect query plans.

**Mistake 9 — Simple `EXISTS(grant ACL)` against Spring ACLs with deny/inheritance.** May expose documents with direct denies. Write policy equivalence tests.

**Mistake 10 — Caches missing caller/tenant/version.** Bob receives Alice's search results or statistics.

**Mistake 11 — Search engine fetching top-N before checking ACLs.** Results, rankings, suggestions, and facets break and can leak records.

**Mistake 12 — Returning only valid IDs while leaving title/owner/salary/internal fields in the DTO.** Row-level authorization does not replace field-level authorization.

**Mistake 13 — Allowing sort/filter on sensitive fields.** Even without returning the field, comparing sort order or counts across queries can infer values; allowlist per policy.

**Mistake 14 — Statistics on groups of size 1.** Records are in scope yet AVG/MIN/SUM can expose an individual; add aggregate-specific privacy controls.

**Mistake 15 — Assuming similar query names share security scope across all endpoints.** Exports, counts, analytics, scheduled reports, facets, and autocomplete often have separate code paths.

**Mistake 16 — Skipping permission re-checks in background jobs or stale cursors.** Entitlements can change; re-evaluate against current policy.

**Mistake 17 — Missing stable sort.** Records duplicate or vanish across pages, complicating audits and mimicking permission bugs.

**Mistake 18 — Confusing zero results with forbidden.** A valid caller seeing zero matching records differs from a caller lacking feature permission; keep the API contract consistent without leaking existence.

## 19. Secure Implementation Checklist

- [ ] Policy `A(user, record)` is defined using trusted identity and resource sources.
- [ ] Separate function-level permissions exist for search/count/stats/export.
- [ ] Scope always combines with business filters via `AND` with proper parentheses.
- [ ] Search queries push tenant/owner/ACL/visibility down to the DB or search engine.
- [ ] Count uses the **exact same policy and filters** as content; custom `countSpec` never drops scope.
- [ ] Pagination runs after filtering, with stable sorting and page size/offset limits.
- [ ] `totalPages`, `hasNext`, facets, and summaries leak zero out-of-scope counts.
- [ ] Stats GROUP BY/SUM/AVG/MIN/MAX run over the visible set; sensitive aggregates have dedicated policies.
- [ ] Share/ACL JOINs neither multiply rows nor cross tenants.
- [ ] `@PostFilter` on `Page` is not used as the primary pagination mechanism.
- [ ] When based on Spring ACL, query-time visibility is cross-checked against the evaluator for direct grants, explicit denies, and inheritance.
- [ ] Scope errors or missing Authentication never degrade into unrestricted queries.
- [ ] DTOs/projections expose only permitted fields; sort/filter fields are allowlisted.
- [ ] Caches/search indexes/keyset cursors are scoped and invalidated on permission revocation.
- [ ] Tests cover cross-tenant, owner mismatch, same-keyword hidden records, status facets, amount SUM, and zero results.
- [ ] Tests cover role/permission revocation, concurrency, and async reports/exports where applicable.
- [ ] Query plans, indexes, and latency targets are verified without trading off access policy.

**Rule to remember:** Data authorization is a **query scope**, not deleting unauthorized elements after fetching a page. The set `authorized ∩ filters` must be the **single source of truth** for search, total counts, pagination, statistics, and facets. Whenever a number or list is computed from a different set, an information leak may exist even if `content` looks right.

## Official References

- [Spring Data JPA 3.5 — JpaSpecificationExecutor JavaDoc](https://docs.spring.io/spring-data/jpa/reference/3.5/api/java/org/springframework/data/jpa/repository/JpaSpecificationExecutor.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Domain Object Security / ACLs](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP API Security Top 10 — Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/)
